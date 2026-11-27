# SecurityContext in DataLoader

DataLoader helps Spring for GraphQL batch multiple related data loads into a single call to reduce N+1 queries. However, a batch loader typically accesses data by ID and executes asynchronously. If the data depends on the currently logged-in user, tenant, or access permissions, the loader must preserve the GraphQL request's security context.

For example, a query loads a list of documents, and each document has fields like owner, comments, or privateNotes. Two users may query the same document ID while only one is allowed to view private notes. The batch loader must filter data according to the current request's identity and permissions, and must never allow the cache to return results loaded under a different permission scope.

**SecurityContext in DataLoader** is the practice of ensuring authentication details and access scope are propagated to batch loading functions so every data fetch continues to enforce proper authorization. Spring for GraphQL supports this via Principal in annotated controllers, GraphQLContext and BatchLoaderEnvironment, and context propagation mechanisms for MVC and WebFlux.

## Distinguishing SecurityContext, Authentication, Principal, and GraphQLContext

These concepts are related but not interchangeable:

| Component | Role |
| --- | --- |
| SecurityContext | Holds security information for the current execution, typically containing Authentication |
| Authentication | Represents the authenticated identity and granted authorities |
| Principal | Interface representing an identity; in Spring GraphQL it can be injected from the Spring Security context |
| GraphQLContext | Key/value context attached to a GraphQL execution, used to pass metadata to resolvers and batch loaders |
| BatchLoaderEnvironment | GraphQL Java context passed to BatchLoaderWithContext; provides the shared GraphQLContext and per-key local contexts |

Spring for GraphQL allows annotated controllers to accept java.security.Principal or @AuthenticationPrincipal. With @BatchMapping, methods can also accept Principal, GraphQLContext, @ContextValue, or BatchLoaderEnvironment.

GraphQLContext is not automatically synonymous with SecurityContext. GraphQLContext is a vehicle for execution metadata; identity and permissions remain managed by Spring Security. When a batch loader needs the tenant or subject, put the required information into GraphQLContext or the key in a controlled manner, and continue checking permissions in the service.

## Why do batch loaders need a security context?

Suppose the application has this schema:

~~~graphql
type Query {
  documents: [Document!]!
}

type Document {
  id: ID!
  title: String!
  privateNotes: [Note!]!
}

type Note {
  id: ID!
  content: String!
}
~~~

A user may view a document, yet only view privateNotes if they are the owner or an authorized member. The resolver loading notes for multiple documents can use DataLoader to reduce queries:

~~~java
public record NoteGroup(List<Note> notes) {
}

@SchemaMapping
public CompletableFuture<List<Note>> privateNotes(
        Document document,
        DataLoader<String, NoteGroup> notesLoader) {
    return notesLoader.load(document.id())
            .thenApply(NoteGroup::notes);
}
~~~

If the batch loader simply queries by document ID without checking the user, it could return private notes to anyone who knows the ID. Using DataLoader does not create authorization by itself; it only batches and caches data loading results.

An important principle: **authorization must be enforced on the data access path itself**. Do not rely on clients not knowing IDs, do not merely hide fields in the UI, and do not assume a parent resolver already checked permissions for every child field.

## Receiving Principal directly in @BatchMapping

For straightforward cases, Spring for GraphQL lets you accept Principal directly in a @BatchMapping method. This is often the clearest approach because the method explicitly shows the identity used to filter the batch:

~~~java
import java.security.Principal;
import java.util.List;
import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;

@Controller
public class DocumentBatchController {

    private final NoteService noteService;

    public DocumentBatchController(NoteService noteService) {
        this.noteService = noteService;
    }

    @BatchMapping(typeName = "Document", field = "privateNotes")
    public Map<Document, List<Note>> privateNotes(
            List<Document> documents,
            Principal principal) {

        if (principal == null) {
            throw new AccessDeniedException("Authentication is required to view notes");
        }

        return noteService.findVisibleNotes(
                documents,
                principal.getName());
    }
}
~~~

Spring retrieves Principal from the Spring Security context if present. NoteService receives the document list and subject ID to query only the notes the user is permitted to see. The batch handler returns a map from each Document to its corresponding list of Notes.

The service must still perform authorization and filter data:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;

@Service
public class NoteService {

    private final NoteRepository noteRepository;
    private final DocumentAccessService accessService;

    public NoteService(
            NoteRepository noteRepository,
            DocumentAccessService accessService) {
        this.noteRepository = noteRepository;
        this.accessService = accessService;
    }

    public Map<Document, List<Note>> findVisibleNotes(
            List<Document> documents,
            String subjectId) {

        Set<String> documentIds = documents.stream()
                .map(Document::id)
                .collect(Collectors.toSet());

        Set<String> allowedIds =
                accessService.findReadableDocumentIds(subjectId, documentIds);

        if (allowedIds.isEmpty()) {
            Map<Document, List<Note>> emptyResult = new HashMap<>();
            documents.forEach(document -> emptyResult.put(document, List.of()));
            return emptyResult;
        }

        Map<String, List<Note>> notesByDocument =
                noteRepository.findVisibleByDocumentIdsAndSubject(
                                allowedIds, subjectId)
                        .stream()
                        .collect(Collectors.groupingBy(Note::documentId));

        Map<Document, List<Note>> result = new HashMap<>();
        for (Document document : documents) {
            result.put(
                    document,
                    allowedIds.contains(document.id())
                            ? notesByDocument.getOrDefault(document.id(), List.of())
                            : List.of());
        }
        return result;
    }
}
~~~

This code illustrates the workflow: determine the set of accessible documents, query notes in one batch by subject, and build results for each source object. If Document is an entity class, ensure equals and hashCode are stable because @BatchMapping uses source objects as map keys. Depending on API policy, unauthorized resources may return an empty list, null, or emit a FORBIDDEN error. Choose consistent semantics and avoid disclosing whether a resource exists if that is sensitive information.

## When you need a principal with application-specific attributes

If the application has a custom principal type, you can place an authenticated context object into GraphQLContext at the request boundary, then read it with @ContextValue in the batch mapping:

~~~java
public record CurrentUser(
        String userId) {
}
~~~

~~~java
@BatchMapping(typeName = "Document", field = "privateNotes")
public Map<Document, List<Note>> privateNotes(
        List<Document> documents,
        @ContextValue("currentUser") CurrentUser currentUser) {

    return noteService.findVisibleNotes(
            documents,
            currentUser.userId());
}
~~~

CurrentUser must be constructed from the authenticated Authentication, never bound from client-sent arguments. A WebGraphQlInterceptor or security integration layer can place the verified subject ID and tenant into GraphQLContext. If no custom attributes are needed, accepting Principal directly remains simpler.

Avoid passing the entire Authentication or raw tokens down to every repository. Extract the needed subject ID, tenant ID, and authorities into small, clear data structures.

## Passing metadata with GraphQLContext and @ContextValue

Batch mapping methods can accept GraphQLContext or @ContextValue. This is a good choice when the application normalizes request metadata such as tenant ID, locale, or correlation ID in a WebGraphQlInterceptor.

Example schema and resolver:

~~~java
@BatchMapping(typeName = "Document", field = "privateNotes")
public Map<Document, List<Note>> privateNotes(
        List<Document> documents,
        @ContextValue("tenantId") String tenantId,
        Principal principal) {

    return noteService.findVisibleNotes(
            documents,
            principal.getName(),
            tenantId);
}
~~~

The tenantId value must come from a trusted source, such as the tenant bound to the authenticated principal or a verified token. Never use an arbitrary client argument or header as proof of which tenant the user may access.

If you need to read multiple metadata entries, accept GraphQLContext:

~~~java
@BatchMapping(typeName = "Document", field = "privateNotes")
public Map<Document, List<Note>> privateNotes(
        List<Document> documents,
        GraphQLContext context,
        Principal principal) {

    String tenantId = context.get("tenantId");
    String locale = context.get("locale");

    return noteService.findVisibleNotes(
            documents,
            principal.getName(),
            tenantId,
            locale);
}
~~~

The GraphQLContext in a batch mapping is the context from BatchLoaderEnvironment and is the same context provided to DataFetchingEnvironment. Populate metadata before resolvers run and prefer reading it in batch handlers rather than mutating context while fields are executing.

## BatchLoaderRegistry and BatchLoaderEnvironment

When registering a DataLoader directly, Spring for GraphQL recommends using BatchLoaderRegistry instead of manually creating DataLoaders in an unmanaged location. The registry registers loaders and creates a DataLoader per GraphQL request. The batch loading function can receive BatchLoaderEnvironment:

~~~java
import graphql.GraphQLContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;

@Configuration
public class DocumentDataLoaderConfiguration {

    public DocumentDataLoaderConfiguration(
            BatchLoaderRegistry registry,
            NoteService noteService) {

        registry.forTypePair(String.class, NoteGroup.class)
                .registerMappedBatchLoader((documentIds, environment) -> {
                    GraphQLContext context = environment.getContext();
                    String tenantId = context.get("tenantId");

                    return noteService.findGroupsForTenant(
                            documentIds,
                            tenantId);
                });
    }
}
~~~

Here NoteGroup is the DTO wrapping a list of Notes declared in the earlier example. The findGroupsForTenant method returns a publisher, such as Mono<Map<String, NoteGroup>>, matching the registerMappedBatchLoader contract.

Resolver invoking the DataLoader:

~~~java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;

@SchemaMapping(typeName = "Document", field = "privateNotes")
public CompletableFuture<List<Note>> privateNotes(
        Document document,
        DataLoader<String, NoteGroup> notesLoader) {

    return notesLoader.load(document.id())
            .thenApply(NoteGroup::notes);
}
~~~

The example above illustrates reading the tenant from GraphQLContext. If the batch function needs user identity, you can use Principal in @BatchMapping, pass the subject ID via the key, or use the SecurityContext propagated to the execution according to your web stack. GraphQLContext only contains SecurityContext if the application explicitly puts it there; do not assume it appears automatically in the context.

BatchLoaderEnvironment provides:

- context: the shared GraphQLContext of the execution, identical to the context visible from DataFetchingEnvironment.
- keyContexts: local context attached to each DataLoader.load call.

keyContexts is useful when each parent field has distinct metadata. For example, a child resolver passes a local context containing the scope or policy computed for its parent. Because a single batch can combine load calls from different fields, the batch function must read the local context corresponding to each key rather than taking one shared value for the entire batch.

## Propagating SecurityContext across MVC and WebFlux

GraphQL Java can execute data fetchers and batch loaders asynchronously, on a thread different from the HTTP request thread. Therefore, do not assume SecurityContextHolder always holds a value simply because the initial controller received a Principal.

Spring for GraphQL supports context propagation from the transport to GraphQL Java and invoked components:

- With Spring MVC, ThreadLocal context can be propagated to threads executing data fetchers. Spring for GraphQL provides SecurityContextThreadLocalAccessor, which registers automatically via ServiceLoader when Spring Security is on the classpath.
- With Spring WebFlux, the security context lives in Reactor Context. Reactive data fetchers and batch loading functions must read it inside the reactive pipeline, rather than relying on a fixed thread's ThreadLocal.

Context propagation only works when the corresponding libraries and accessors are on the classpath and the pipeline is preserved properly. If a batch loader switches to a self-managed executor or calls subscribe() manually, the context may no longer remain attached to that work. Prefer returning Mono/CompletableFuture from batch functions and letting Spring manage dispatching.

### Spring MVC: SecurityContextHolder

In MVC applications, a synchronous batch loader can read Authentication from SecurityContextHolder when context propagation is configured and active:

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

registry.forTypePair(String.class, AccountSummary.class)
        .registerMappedBatchLoader((accountIds, environment) -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return CompletableFuture.failedFuture(
                        new AccessDeniedException("No valid identity"));
            }

            String subjectId = authentication.getName();
            return CompletableFuture.completedFuture(
                    accountService.findVisibleAccounts(accountIds, subjectId));
        });
~~~

This is an example for an imperative batch loader. It is only safe when SecurityContext is propagated to the execution thread. If the batch loader switches to another executor without context propagation, SecurityContextHolder may be empty or hold an unexpected value. In that case, pass the subject ID explicitly via the key or context instead of relying on ThreadLocal.

### Spring WebFlux: ReactiveSecurityContextHolder

With WebFlux, read SecurityContext from Reactor Context inside the publisher:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;

registry.forTypePair(String.class, AccountSummary.class)
        .registerMappedBatchLoader((accountIds, environment) ->
                ReactiveSecurityContextHolder.getContext()
                        .switchIfEmpty(Mono.error(
                                new AccessDeniedException(
                                        "No SecurityContext")))
                        .flatMap(securityContext -> {
                            Authentication authentication =
                                    securityContext.getAuthentication();

                            if (authentication == null
                                    || !authentication.isAuthenticated()
                                    || authentication instanceof AnonymousAuthenticationToken) {
                                return Mono.error(new AccessDeniedException(
                                        "No valid identity"));
                            }

                            return accountService.findVisibleAccounts(
                                    accountIds,
                                    authentication.getName());
                        }));
~~~

This code must run inside a reactive pipeline where Spring for GraphQL and Spring Security propagate context. Never call block() to retrieve SecurityContext, and never switch arbitrarily to another thread and read ReactiveSecurityContextHolder outside the publisher.

If services need the principal in many places, consider passing the subject ID as an explicit parameter. This makes the security dependency explicit and easier to test than having every layer read context implicitly.

## DataLoader keys must reflect security scope

DataLoader caches results by key for the duration of a GraphQL request. If the same key always yields the same result within a request, the cache can reuse it safely. However, if the result also depends on tenant, subject, locale, or policy, the key must capture the dimensions that change the result.

Example with insufficient scope:

~~~java
DataLoader<String, AccountSummary> accountLoader;
~~~

If accounts can be queried across different tenants or under different permissions within the same execution, using only accountId can cause the cache to return a result from the wrong scope.

Use an immutable composite key:

~~~java
public record AccountAccessKey(
        String accountId,
        String subjectId,
        String tenantId) {
}
~~~

The resolver constructs the key from the authenticated principal and trusted tenant:

~~~java
@SchemaMapping(typeName = "Document", field = "account")
public CompletableFuture<AccountSummary> account(
        Document document,
        Principal principal,
        @ContextValue("tenantId") String tenantId,
        DataLoader<AccountAccessKey, AccountSummary> accountLoader) {

    AccountAccessKey key = new AccountAccessKey(
            document.accountId(),
            principal.getName(),
            tenantId);

    return accountLoader.load(key);
}
~~~

The batch loader receives keys that already include scope:

~~~java
registry.forTypePair(AccountAccessKey.class, AccountSummary.class)
        .registerMappedBatchLoader((keys, environment) ->
                accountService.findVisibleAccounts(keys));
~~~

Composite keys must use minimal, immutable identifying data with stable equals/hashCode. Never put access tokens, passwords, or the entire Authentication into a key. A key is part of cache identity, not a substitute for authorization.

If every load in a GraphQL request is guaranteed to use the same principal and tenant, keys only need to include dimensions that can vary within that request. Even so, the service must still check permissions; never treat a composite key as the sole security layer.

## Per-request cache is not an application-wide cache

DataLoaders registered via BatchLoaderRegistry are created per GraphQL request and have per-request caches. This ensures the same key is loaded once within an operation, but does not make results automatically safe for a global cache.

Distinguish them:

| Cache type | Scope | Security notes |
| --- | --- | --- |
| DataLoader cache | Single GraphQL request | Still must design keys accurately if results vary by context/key |
| Application cache | Multiple requests | Keys must include tenant/subject/policy when data depends on permissions; requires TTL and invalidation |
| Database query cache | Depends on persistence/provider | Never use cache as an authorization layer |

Never retain a DataLoader in a singleton service, static field, or global cache. Never register a DataLoader shared across users. Spring for GraphQL manages the registry per request to avoid sharing caches across GraphQL executions.

If the application has a shared service cache, clearly identify which data is public, which depends on tenant, and which depends on individual subjects. For sensitive data, cache only after defining cache keys and invalidation that match the permission model.

## Never trust tenant or user IDs from the client

GraphQL arguments are client-submitted data. For example:

~~~graphql
query {
  account(id: "acc-10", tenantId: "tenant-admin") {
    balance
  }
}
~~~

The server must not assume tenantId in an argument is a tenant the user has permission to access. If the API needs a tenant argument to select a resource, compare it against the authenticated tenant or check permissions explicitly.

Similarly, never use a client-sent userId to determine the current user. Identity must come from the Authentication/Principal verified by Spring Security. Client-provided data is only a target resource or filter, never a credential.

At the service or repository layer, enforce tenant and subject restrictions directly in the query when possible:

~~~java
List<Document> findVisibleDocuments(
        String tenantId,
        String subjectId,
        Collection<String> documentIds);
~~~

This avoids loading unauthorized data and filtering afterward in Java. If using database row-level security, the tenant context must also be set safely within the transaction and cleared when the transaction finishes.

## Service authorization and method security

You can use Spring Method Security to protect services:

In the security configuration, enable method security with @EnableMethodSecurity if not already enabled:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Then apply annotations to the service:

~~~java
@Service
public class AccountService {

    @PreAuthorize("@accountAuthorization.canRead(authentication, #accountId)")
    public AccountSummary findById(String accountId) {
        return accountRepository.findSummaryById(accountId);
    }
}
~~~

Method security lets you reuse permission policies across multiple entry points. For batch methods, design authorization around a set of IDs to avoid invoking checks once per element and recreating N+1 at the security layer.

For example, a batch service takes a subject ID and a set of account IDs, then queries the list of accounts the subject is allowed to view in a single call. If using @PreAuthorize on a batch method, the expression should guard the overall call; per-ID checks can live in the repository query or a policy service.

Never rely on fields being hidden in the schema or clients not selecting fields. GraphQL authorization must be enforced at the resolver, service, or data layer for every access path that can reach the data.

## Handling unauthorized and non-existent data

A batch may contain:

- Valid keys the user is authorized to access.
- Existing keys the user lacks permission to access.
- Non-existent keys.
- Keys belonging to another tenant.

The application must decide on consistent semantics. For sensitive data, returning NOT_FOUND for both non-existent and unauthorized resources avoids disclosing existence. For internal APIs, FORBIDDEN may be more suitable so clients know additional permissions are needed.

Never make a batch loader return a substitute object just to match the element count. With MappedBatchLoader, keys absent from the map resolve to null; schema nullability dictates how GraphQL proceeds. With list-based BatchLoader, result positions must align with input keys.

If one key is denied without failing the entire batch, handle it per key or key group and return corresponding results. If the entire operation cannot continue due to policy, emit a classified error without leaking internal details in the response.

## Testing SecurityContext and DataLoader

Tests must verify more than the loader being called once. They must prove data cannot leak between principals or tenants:

| Scenario | What to verify |
| --- | --- |
| User A reads documents A owns | Batch returns notes A is allowed to view |
| User B queries the same document ID | Does not receive A's private notes |
| Two tenants use the same ID format | Data is restricted by tenant |
| Multiple keys in one batch | Repository receives the proper key set and scope |
| Same key loaded multiple times in a request | Cache is reused only within the same permission scope |
| Batch loader runs asynchronously | SecurityContext or Reactor Context remains intact |
| Unauthorized principal | No sensitive data is returned |
| Non-existent key | Result follows null/NOT_FOUND semantics |
| Client sends fake tenantId | Service rejects or ignores untrusted value |

Example testing a service by subject:

~~~java
@Test
void shouldOnlyLoadNotesVisibleToCurrentSubject() {
    List<Document> documents = List.of(documentA, documentB);

    Map<Document, List<Note>> result =
            noteService.findVisibleNotes(documents, "user-17");

    assertThat(result.get(documentA))
            .extracting(Note::id)
            .containsExactly("note-1");
    assertThat(result.get(documentB)).isEmpty();

    verify(noteRepository).findVisibleByDocumentIdsAndSubject(
            Set.of("doc-a"),
            "user-17");
}
~~~

At the GraphQL integration test level, create two requests with two different users, execute the same query containing a batch-loaded field, and verify each response contains only authorized data. You can use Spring Security test support to set Authentication for each request. Running two requests concurrently helps expose bugs where SecurityContext is stored in a singleton or caches are wrongly scoped.

Beyond responses, verify the batch service is called in groups rather than once per parent. Authorization and batching must work together; never optimize queries by skipping permission checks.

## Common issues

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Principal present in controller but null in batch loader | Context not propagated to execution thread | Use BatchLoaderRegistry, verify context propagation, or pass subject explicitly |
| WebFlux reads SecurityContextHolder but gets nothing | Reactive security context lives in Reactor Context | Use ReactiveSecurityContextHolder inside publisher |
| Batch returns another tenant's data | Tenant taken from client or omitted from query | Use authenticated tenant and filter in service/repository |
| Same ID returns wrong-scope result | DataLoader key lacks tenant/subject/filter affecting output | Use an immutable composite key |
| Cache persists across multiple requests | Manually holding DataLoader in singleton/static field | Use BatchLoaderRegistry to register per-request loaders |
| @BatchMapping does not receive Principal | Missing Spring Security context or unauthenticated request | Check security chain and authentication configuration |
| Loader cannot read metadata | Key missing in GraphQLContext or interceptor ran out of order | Populate metadata before execution and verify key names |
| Batch query loads too much data | Filtering permissions after loading all records | Push tenant/subject conditions into the batch query |
| Using Authentication as cache key | Key holds unnecessary or mutable objects | Use immutable subject ID and tenant ID |
| SecurityContext lingers after request | Self-managed ThreadLocal not reset properly | Use Spring's context propagation and avoid singleton state |

## Design principles for SecurityContext in DataLoader

When using DataLoader with Spring for GraphQL, apply these practices:

1. **Use Principal directly when possible.** @BatchMapping supports Principal; for custom principal metadata, use @ContextValue after context has been populated from the verified identity.
2. **Use BatchLoaderRegistry for custom loaders.** The registry creates per-request DataLoaders and supports GraphQLContext and context propagation.
3. **Distinguish GraphQLContext from SecurityContext.** GraphQLContext only contains what is explicitly put into it; never assume it holds Authentication automatically.
4. **Read context matching your web stack.** MVC uses SecurityContextHolder when propagation is configured; WebFlux uses ReactiveSecurityContextHolder inside reactive pipelines.
5. **Include necessary scope in keys.** Include subject ID, tenant ID, or immutable filters whenever they affect results.
6. **Authorize in services or data queries.** DataLoader only batches and caches; it does not check permissions on its own.
7. **Keep caches per request.** Never use singleton DataLoaders or caches shared across users.
8. **Never trust identifying data from clients.** Principals and tenants must come from authenticated sources.
9. **Handle missing and forbidden consistently.** Avoid disclosing the existence of sensitive resources.
10. **Test isolation.** Run multiple principals and tenants to prove no data leaks between requests.

SecurityContext in DataLoader ensures batch loading executes under the right identity and permission scope of the GraphQL request. For standard cases, @BatchMapping can accept Principal directly. For custom loaders, BatchLoaderRegistry provides BatchLoaderEnvironment and GraphQLContext while supporting context propagation. Choose the right way to read SecurityContext for MVC or WebFlux, design keys and caches by tenant and subject when results depend on permissions, and always enforce authorization in services or the data layer. DataLoader can eliminate N+1 queries while keeping data secure when batching, caching, and security are designed as one cohesive mechanism.

## References

- [Spring for GraphQL - Annotated Controllers: Principal and BatchMapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - Request Execution: BatchLoaderRegistry and Context Propagation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL - SecurityContextThreadLocalAccessor API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/execution/SecurityContextThreadLocalAccessor.html)
- [Spring Security - SecurityContextHolderThreadLocalAccessor](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/SecurityContextHolderThreadLocalAccessor.html)
- [Spring Security - ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)

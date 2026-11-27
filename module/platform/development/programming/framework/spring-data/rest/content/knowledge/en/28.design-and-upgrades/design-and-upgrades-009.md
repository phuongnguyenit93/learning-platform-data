# Identifying and Fixing Over-Exposure, Business Logic in Listeners, and Hardcoded URLs

## Objectives

As a Spring Data REST application grows, certain early decisions can introduce maintenance and security risks:

- **Over-exposure:** repositories, associations, or attributes are exported more broadly than the API requires.
- **Business logic in listeners:** critical rules only execute when requests pass through the Spring Data REST repository event pipeline.
- **Hardcoded URLs:** controllers or clients concatenate path/host strings manually, making the API brittle when base paths, resource mappings, proxies, or versions change.

The remedy is to explicitly define the permitted API surface, place invariants in the application/domain layer, and use hypermedia links or link builders instead of manually concatenated URL strings.

## 1. Recognizing Over-Exposure

Spring Data REST can automatically generate collection resources, item resources, search resources, and association links from exported repositories and domain models. This is a fast way to get a CRUD API, but it can also expose more operations than the product actually needs.

Warning signs to review:

- Internal repositories appear in the root resource even though clients do not need access.
- The API permits POST/PUT/PATCH/DELETE on resources that should be read-only.
- Internal search methods are exposed under `/search`.
- Association links allow clients to modify relationships forbidden by business rules.
- Entity responses contain internal fields, sensitive data, or administrative details.
- Clients can invoke URIs directly even though the UI does not display the link.

Do not assess exposure solely by the list of links rendered by the frontend. Inspect the root resource, profiles, search resources, association resources, and direct invocation of every HTTP method.

## 2. Exporting Only Necessary Repositories

You can disable export at the repository level using `@RepositoryRestResource(exported = false)`:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

The repository can still be injected and used internally by services. This annotation prevents Spring Data REST from exposing the repository as a REST resource.

If the application has many repositories, you can switch to a strategy that detects only explicitly annotated repositories:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setRepositoryDetectionStrategy(
            RepositoryDetectionStrategies.ANNOTATED
        );
    }
}
~~~

When using the `ANNOTATED` strategy, only repositories annotated per convention are exported. Audit existing repositories and explicitly annotate resources that are genuinely public APIs; otherwise, valid endpoints may disappear after changing the strategy.

Another approach is keeping the current strategy while marking internal repositories with `exported = false`. Choose the option that fits the application's scale and API governance model.

## 3. Restricting Query Methods and Associations

Not every finder method should become an HTTP endpoint. You can disable export for a specific query method:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(exported = false)
    List<Person> findByInternalReviewStatus(String status);
}
~~~

The method can still be called internally from Java code via the repository, but Spring Data REST will not publish a search link for it.

Associations are also part of the API surface. If clients are not permitted to modify a relationship, you can disable exporting the association with configuration/annotations suited to the domain mapping:

~~~java
@ManyToOne
@RestResource(exported = false)
private Department department;
~~~

Annotation syntax and placement must match the association type and Spring Data REST version in use. After configuring, check both item representations and association resources; do not assume hiding a field in JSON blocks the association endpoint.

## 4. Projections Do Not Replace Access Control

Projections and excerpts help shape responses:

~~~java
@Projection(name = "publicSummary", types = Person.class)
public interface PersonPublicSummary {

    String getFirstName();

    String getLastName();
}
~~~

An excerpt projection can be configured on the repository:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonPublicSummary.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Projections can reduce the number of fields serialized for a representation, but they do not determine who may read a resource or write a field. Clients can call other endpoints or send payloads directly.

For sensitive data, combine:

- DTOs/response models containing only fields permitted to be public.
- Security policies checking read permissions by principal and resource.
- Write DTOs/commands accepting only fields allowed by the use case.
- Testing direct requests, not just UI views or projections.

Do not use projections as the sole security barrier.

## 5. Separating Three Layers: Representation, Authorization, and Business Rules

When reviewing a field or operation, ask three separate questions:

| Responsibility | Question | Suitable Mechanism |
|---|---|---|
| Representation | Which fields/links may the client see? | Projections, DTOs, assemblers, resource mappings |
| Authorization | What is this principal allowed to do on this resource? | Spring Security, method security, ownership/tenant policies |
| Business rules | Is the change valid given domain state and invariants? | Application services, domain methods, transactions |

For example, omitting a `salary` field from a public projection only addresses representation. Permission to view salary requires authorization. Updating salary must be validated against business rules and the editor's permissions.

Similarly, hiding a DELETE link does not protect the delete operation. The server must reject direct requests if the principal lacks permission or the entity is in a non-deletable state.

## 6. Securing Endpoints with Spring Security

URL-level rules are the first line of defense for HTTP methods and paths:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/people/**")
                .hasAuthority("people:read")
            .requestMatchers(HttpMethod.POST, "/api/people")
                .hasAuthority("people:create")
            .requestMatchers(HttpMethod.PUT, "/api/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.PATCH, "/api/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.DELETE, "/api/people/**")
                .hasAuthority("people:delete")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

Matchers must align with the actual base path, methods, and endpoint structure. When changing `spring.data.rest.base-path`, context paths, or reverse proxies, review rules and integration tests.

Permissions can also depend on the specific record or tenant. In that case, check them in the service via method security:

~~~java
@Service
public class PersonService {

    @PreAuthorize("@personAccess.canUpdate(authentication, #personId)")
    public Person update(Long personId, UpdatePersonCommand command) {
        // Load the authorized Person and apply permitted changes.
        return null;
    }
}
~~~

The `personAccess` bean must check ownership/tenant against actual data. Checking only a broad authority like `people:update` may not be enough to allow editing any Person.

Hiding links in HAL can improve user experience, yet every request must still be authorized on the server. Do not rely on the frontend or metadata to enforce permissions.

## 7. Recognizing Business Logic Placed Inside Repository Event Listeners

Spring Data REST repository event handlers are useful for logic tied to the HTTP repository resource lifecycle. Example:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        person.setFirstName(person.getFirstName().trim());
    }

    @HandleBeforeSave
    public void beforeSave(Person person) {
        person.setLastName(person.getLastName().trim());
    }
}
~~~

Listeners like this work well for thin operations tied to the REST boundary, such as normalizing input data or delegating to an application service.

However, if a listener contains entire workflows or invariants, the application runs into issues:

- Logic runs only when operations go through the Spring Data REST event pipeline.
- Batch jobs, message consumers, or other services can write to the repository without triggering the same handlers.
- Rules are hidden away from the main use cases and harder to locate during debugging.
- Execution order across multiple listeners can make outcomes depend on registration/ordering.
- Side effects like sending emails or making HTTP calls may become inconsistent with the database transaction.
- Domain unit tests end up having to instantiate event handlers rather than testing services/use cases.

A typical smell is a listener performing multiple repository queries, state transitions, permission checks, pricing calculations, order creation, message publishing, or calls across multiple services to complete a workflow.

## 8. Moving Invariants into Application Services or Domain Models

Rules that must hold across all entry points belong in the application service/domain layer. Listeners should remain thin adapters when Spring Data REST integration is still required.

Example service executing a use case:

~~~java
@Service
public class PersonApplicationService {

    private final PersonRepository repository;

    public PersonApplicationService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Person create(CreatePersonCommand command) {
        Person person = new Person();
        person.setFirstName(normalize(command.firstName()));
        person.setLastName(normalize(command.lastName()));

        validateNewPerson(person);
        return repository.save(person);
    }

    private String normalize(String value) {
        return value == null ? null : value.trim();
    }

    private void validateNewPerson(Person person) {
        if (person.getFirstName() == null
                || person.getFirstName().isBlank()) {
            throw new IllegalArgumentException("First name is required");
        }
    }
}
~~~

The service orchestrates transactions, business validation, and persistence. Domain methods can enforce local entity/aggregate invariants; application services coordinate multiple repositories or external systems.

If Spring Data REST still requires an event handler, have the handler delegate to shared logic where appropriate:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    private final PersonRestAdapter restAdapter;

    public PersonEventHandler(PersonRestAdapter restAdapter) {
        this.restAdapter = restAdapter;
    }

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        restAdapter.prepareForCreate(person);
    }
}
~~~

This adapter should invoke reusable logic and avoid implementing a separate workflow of its own. Do not call `repository.save(person)` again on the object currently being processed inside a before-save listener; doing so can trigger recursion or unpredictable side effects.

## 9. Distinguishing Listeners, Validation, and Domain Events

Three mechanisms are frequently conflated:

| Mechanism | Role |
|---|---|
| Spring Data REST repository event handler | Hooks into the REST repository request lifecycle |
| Spring Validator / Bean Validation | Validates data and records validation errors |
| Domain/application event | Notifies other components that a business event occurred |

For example:

- Normalizing names from a request can live in an adapter/service.
- Checking required fields belongs to validation.
- Checking whether a Person state transition is valid belongs to domain/business rules.
- Notifying other systems of `PersonCreated` is an application/domain event.

Do not rely on `@HandleAfterCreate` as the sole place to emit business notifications if a Person can also be created by a batch job or message consumer. Emit domain/application events from shared use cases.

## 10. Handling Side Effects and Transactions

A listener running after a repository operation does not automatically guarantee external side effects align with database commits.

For example, sending an email directly inside `@HandleAfterSave` can result in an email being sent even if the database transaction rolls back. Conversely, the database may commit while the external system call fails.

Options depending on requirements:

- Use `@TransactionalEventListener(phase = AFTER_COMMIT)` for work that must run only after transaction commit.
- Use a transactional outbox when events must be persisted atomically with the transaction and workers need retries.
- Design idempotent consumers to handle duplicate messages.
- Record logs/correlation IDs for error tracing and retries.

Do not assume after-save callbacks are always equivalent to after-commit. Verify actual transaction boundaries before placing side effects.

## 11. Recognizing Hardcoded URLs

Hardcoded URLs appear when code manually concatenates hosts, base paths, plural names, or identifiers:

~~~java
String url = "https://api.example.com/api/people/" + person.getId();
~~~

Or when clients construct paths manually:

~~~javascript
const url = baseUrl + "/api/people/" + personId;
~~~

These strings break when:

- Switching hosts between local, staging, and production.
- Changing `spring.data.rest.base-path` or the servlet context path.
- Changing repository paths via `@RepositoryRestResource(path = "...")`.
- Adding a reverse proxy or API gateway prefix.
- Changing pluralization or resource naming.
- Updating version prefixes.
- Moving an endpoint to a custom route.

Hardcoded URLs also couple clients to deployment topology instead of server-published relations.

## 12. Using Hypermedia Links Instead of Concatenating URLs

With HAL, clients should start from a known entry point and follow relations in `_links`:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/people/42"
    },
    "people": {
      "href": "https://api.example.com/api/people"
    }
  }
}
~~~

Clients use URIs from `self` or corresponding relations rather than reconstructing `/api/people/{id}`. For search resources, follow the `search` link and then pick the query method's relation. For associations, follow the association link returned by the server.

In server-side controllers, use Spring HATEOAS link builders for application routes:

~~~java
Link personLink = linkTo(
        methodOn(PersonController.class).getPerson(personId)
    ).withSelfRel();
~~~

For Spring Data REST repository resources, prefer link/entity assembler infrastructure matching configured mappings. Do not assume collection names or base paths are always `/api/people`.

### Generating Location for New Resources

When a custom endpoint creates a resource, build the URI using a link builder:

~~~java
URI location = linkTo(
        methodOn(PersonController.class).getPerson(saved.getId())
    ).toUri();

return ResponseEntity.created(location).body(response);
~~~

This binds the URI to the controller mapping rather than a string literal. If the endpoint returns a Spring Data REST resource, use the link builder/EntityLinks matching the application's resource mappings.

## 13. When Are URL Strings Still Appropriate?

Not every URL can be eliminated from configuration. Some addresses are external service endpoints or callback URLs supplied by the deployment environment.

In those cases:

- Move host/base URLs into configuration or environment variables.
- Do not hardcode production URLs in source code.
- Use a URI builder to encode path/query parameters.
- Validate schemes/hosts if URLs are user-supplied.
- Do not manually concatenate query strings when values contain special characters.
- Use hypermedia links for internal API resources when the server already publishes them.

Example building a URL with query parameters:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString(externalServiceBaseUrl)
        .path("/v1/people")
        .queryParam("status", status)
        .build()
        .encode()
        .toUri();
~~~

`externalServiceBaseUrl` comes from configuration; the path and query must match the external service contract. URI builders properly encode values, but they do not replace input URL validation if the host comes from untrusted data.

## 14. Step-by-Step Remediation Process

When auditing a Spring Data REST API:

1. Inventory all currently exported repositories, finder methods, and associations.
2. Determine which resources genuinely need to be public; disable export for internal repositories/methods/associations.
3. Consider a repository detection strategy requiring explicit export if appropriate.
4. Separate representations via projections/DTOs and inspect for sensitive fields.
5. Verify URL-level, method-level, and resource-level authorization.
6. Find `@RepositoryEventHandler` classes containing workflows or invariants; move shared logic into application services/domain.
7. Keep listeners thin and avoid side effects lacking transaction/retry policies.
8. Search for URL string literals in source code, templates, and clients; replace them with hypermedia relations, link builders, or configuration.
9. Check `Location`, ETag, Cache-Control, and other headers when custom endpoints build responses.
10. Write integration tests directly targeting HTTP endpoints, including requests bypassing the UI.

## 15. Testing After Refactoring

Tests must prove that behavior and contracts are under control:

- **Exposure:** internal repositories/methods/associations are no longer exported.
- **Read representations:** public responses contain no sensitive fields.
- **Authorization:** unprivileged users are rejected even when calling URIs directly.
- **Resource policies:** other tenants/owners cannot access or modify resources.
- **Business rules:** invariants still execute when called from REST, services, batch jobs, or message entry points.
- **Listeners:** listeners act only as intended adapters and do not double-save.
- **Transactions:** rollbacks leave no external side effects; retries are idempotent.
- **Links:** clients can still follow self/search/association links after changing base paths or resource paths.
- **Location:** newly created URIs match current mappings.
- **Environment:** staging/production use configured base URLs rather than source literals.

You can use MockMvc/WebTestClient for HTTP contracts, unit tests for service/domain logic, and integration tests for the transaction/event pipeline.

## 16. Common Misconceptions

- **No visible link means the endpoint is unreachable.** Clients can call URIs directly; security must block them on the server.
- **A projection hides a field, so it cannot be written.** Projections primarily shape responses; write contracts and authorization need separate protection.
- **Listeners are the right place for all business logic.** Listeners belong only to the repository REST lifecycle; shared logic belongs in services/domain.
- **After-events always run after commit.** Verify transaction boundaries; use AFTER_COMMIT/outbox when needed.
- **Calling repository.save inside a before-save listener is harmless.** It can cause recursive calls or lifecycle loops.
- **Hardcoded URLs are only an issue when changing hosts.** Base paths, reverse proxies, repository mappings, and versioning can also break URLs.
- **Using a link builder covers every URL.** External service URLs still require configuration and validation.
- **Disabling a repository locks down all data.** Also inspect custom controllers, query methods, associations, and other access paths.
- **Unit testing listeners proves every entry point executes the logic.** Verify service/domain logic across all entry points.

## 17. Key Takeaways

- Export only repositories, methods, and associations that belong to the API contract.
- Use `exported = false` and repository detection strategies to bound the Spring Data REST surface.
- Projections/DTOs control representations; Spring Security and resource policies control access.
- Place shared invariants and workflows in application services/domain models.
- Keep repository event listeners thin, avoiding duplicate saves and unguarded side effects.
- Use `@TransactionalEventListener(AFTER_COMMIT)` or a transactional outbox when side effects must align with commits.
- Follow HAL links from the server and use Spring HATEOAS link builders for internal URLs.
- Load external base URLs from configuration and construct URIs with builders.
- Directly test exposure, authorization, business rules, links, headers, and transactions after refactoring.

## References

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST Reference — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
- [Spring HATEOAS Reference — Building links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring Security Reference — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Framework Reference — Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
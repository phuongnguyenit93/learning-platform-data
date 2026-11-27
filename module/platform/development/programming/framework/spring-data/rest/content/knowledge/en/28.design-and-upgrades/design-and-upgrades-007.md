# Comparing API, Annotation, and Configuration Default Changes During Upgrades

## Objectives

When upgrading Spring Boot, Spring Data, or Spring Data REST, changes are not limited to dependencies. A new version can alter Java APIs, annotations, configuration styles, media types, HAL/ALPS metadata, pagination behavior, validation, events, or how requests are secured. An application that still compiles is not guaranteed to preserve the HTTP contract clients rely on.

The goal of this comparison is to clearly identify three layers of changes:

- **Public API:** URLs, HTTP methods, status codes, headers, media types, HAL links, projections, and response structures.
- **Programming API:** packages, method signatures, annotations, extension interfaces, and event handlers.
- **Runtime defaults:** configuration values, transactions, serialization, security, and repository behavior.

Do not infer changes solely from major version numbers. Compare the exact source and target versions present in the build, read the corresponding release notes and migration guides, and confirm with application tests.

## Identifying Exact Source and Target Versions

Before editing code, record the actual versions of:

- Spring Boot and Spring Framework.
- Spring Data release train, Spring Data REST, Spring Data Commons, and the repository module in use (e.g., Spring Data JPA).
- Spring Security, Hibernate/JPA provider, Jackson, and Bean Validation provider.
- JDK, Gradle, or Maven.

Do not read only the versions declared in one file. Dependency management or a BOM can determine the final version. With Maven, inspect the dependency tree:

    ./mvnw dependency:tree

With Gradle:

    ./gradlew dependencies --configuration runtimeClasspath

You can inspect a specific module:

    ./gradlew dependencyInsight --dependency spring-data-rest-webmvc --configuration runtimeClasspath

Record the results before and after upgrading. Prefer Spring Boot dependency management to keep Spring modules compatible with one another; override a single Spring Data module only when justified and verified for compatibility.

## Building a Comparison Table Before Making Changes

Create a table for each component used by the application:

| Component | Source Version | Target Version | What to Compare |
| --- | --- | --- | --- |
| Spring Data REST | Actual runtime version | New runtime version | Repository export, REST endpoints, events, metadata |
| Spring Data Commons | Actual runtime version | New runtime version | `Pageable`, `Sort`, domain events, repository API |
| Spring Data JPA / repository module | Actual runtime version | New runtime version | Query derivation, persistence behavior, transactions |
| Spring Boot / Framework | Actual runtime version | New runtime version | Auto-configuration, property binding, bean lifecycle |
| Jackson / validation | Actual runtime version | New runtime version | JSON binding, nulls, unknown fields, validation |
| JPA provider / JDK | Actual runtime version | New runtime version | `javax`/`jakarta`, mapping, optimistic locking |

Mark each item as unchanged, renamed, signature changed, deprecated, removed, or default changed. Also note which endpoints or clients depend on that behavior.

## Comparing Annotations and Extension Points

Review the annotations and interfaces the application uses to expose or customize repositories:

| Component | Behavior to Confirm After Upgrading |
| --- | --- |
| `@RepositoryRestResource` | Collection name, path, exported state, excerpt projection |
| `@RestResource` | Path, relation name, and method/association export |
| `@Projection` | Projection name, domain type, scanned packages, and published metadata |
| `@Param` | Query parameter name for finder/search resources |
| `@RepositoryEventHandler` | Domain type accepted by handler and whether handler is registered |
| `@HandleBeforeCreate`, `@HandleBeforeSave`, `@HandleBeforeDelete` | Whether events fire properly for corresponding REST operations |
| `@HandleBeforeLinkSave`, `@HandleBeforeLinkDelete` | Association events and object types passed into handlers |
| `@Version` | Optimistic locking and ETag/conditional requests |

Do not just verify that annotations still compile. Test the actual endpoints or events after the application starts. For example, a repository may still exist yet no longer be exported under new configuration; a projection may compile yet not appear in the ALPS profile.

Example repository configuration preserving the collection path contract:

    @RepositoryRestResource(
        collectionResourceRel = "orders",
        path = "orders")
    public interface OrderRepository
            extends JpaRepository<Order, Long> {
    }

Verify both the relation name and path by reading the API root and collection resource. Clients should follow HAL `href` links rather than constructing URLs from Java repository names.

## Comparing `RepositoryRestConfigurer`

Applications often use `RepositoryRestConfigurer` to set base paths, pagination, media types, CORS, or other REST options. Compare method signatures and package imports against the target version; do not copy an old example without verifying the current compile API.

Example implementing the interface on versions supporting the two-parameter signature:

    @Configuration
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {
            config.setDefaultPageSize(25);
            config.setMaxPageSize(100);
        }
    }

If the target version provides different overloads or default methods, use the signature from that version's Javadoc. Verify imports for `RepositoryRestConfigurer` and `RepositoryRestConfiguration`, as classes with the same name or packages may differ across modules.

Prefer implementing `RepositoryRestConfigurer` rather than continuing to rely on legacy adapters from outdated guides. After upgrading, confirm the configurer bean is loaded by Spring and that values take effect via HTTP requests.

## Comparing Configuration and Default Values

Check properties across `application.properties`/`application.yml`, environment variables, profiles, config servers, and Java config. A renamed property or one that no longer binds can cause the application to silently fall back to defaults.

Spring Data REST properties commonly requiring review include:

| Property | Behavior to Check |
| --- | --- |
| `spring.data.rest.base-path` | Base path for API root, collections, and profiles |
| `spring.data.rest.default-page-size` | Number of items when the client omits `size` |
| `spring.data.rest.max-page-size` | Upper limit for page size |
| `spring.data.rest.page-param-name` | Page query parameter name |
| `spring.data.rest.limit-param-name` | Page size query parameter name |
| `spring.data.rest.sort-param-name` | Sort query parameter name |
| `spring.data.rest.return-body-on-create` | Whether to return the representation after creation |
| `spring.data.rest.return-body-on-update` | Whether to return the representation after update |

Verify this list against configuration metadata for your Spring Boot/Spring Data REST version; do not assume every property exists or has identical semantics in all versions. Check configuration metadata, release notes, and runtime output. If a value affects the API contract, set it explicitly rather than relying on defaults.

Example configuring explicit page sizes:

    spring.data.rest.default-page-size=25
    spring.data.rest.max-page-size=100

Test requests without `size`, requests with `size` below the default, and requests exceeding the max. Inspect `page.size`, `totalElements`, `totalPages`, and `next`/`prev` links in the HAL response.

## Changes That Can Affect API Clients

### URLs and HAL Links

Check the API root, collection paths, item paths, association paths, search links, and the `profile` link. Changes to `base-path`, `collectionResourceRel`, or `@RestResource(path=...)` can prevent older clients from locating resources.

Do not compare URLs purely as strings. Inspect HAL responses and verify relations, URI templates, query parameters, and navigation links remain appropriate. If clients follow HATEOAS, update link-following logic when relations or templates change.

### Media Types and Representations

Verify supported `Accept` and `Content-Type` values: HAL JSON, plain JSON, ALPS profiles, JSON Patch, and JSON Merge Patch if used by the application. Confirm response bodies, `_embedded`, `_links`, `page`, error representations, and `Location`/`ETag` headers.

Do not assume responses always contain a body after POST or PUT. Body-return settings, status codes, and headers can affect clients; document the exact behavior of the target version.

### Pagination and Sorting

Check default page size, max page size, query parameter names, and `sort` syntax. If defaults change, clients omitting `size` may receive a different record count than before. Set default/max explicitly and inspect page metadata.

### Projections, Excerpts, and ALPS

Verify projection names still appear in ALPS metadata and still work with `?projection=...`. Check collection excerpt projections, nested projections, and sensitive fields. Metadata only describes published choices; authorization must still be enforced server-side.

### PATCH and Null Values

Verify JSON Patch with `application/json-patch+json` and JSON Merge Patch with `application/merge-patch+json` if supported by the API. Confirm semantics for omitted fields, `null`, `remove`, nested objects, and arrays. Version changes in Jackson or patch handlers can alter binding behavior; read back the saved entity in tests.

### ETag and Optimistic Locking

If an entity has `@Version`, verify GET returns an ETag and conditional PUT/PATCH/DELETE handle `If-Match` properly. Confirm requests using stale ETags receive `412 Precondition Failed` and do not overwrite newer data.

## Comparing `javax` and `jakarta` Namespaces

When upgrading across the Spring Framework/Spring Boot generation that migrates to Jakarta EE, inspect imports and dependencies for persistence, validation, servlet, and related annotations. For example:

- `javax.persistence.*` moves to `jakarta.persistence.*`.
- `javax.validation.*` moves to `jakarta.validation.*`.
- `javax.servlet.*` moves to `jakarta.servlet.*`.

Do not blindly search-and-replace every string starting with `javax`: several Java SE packages retain the `javax` namespace, and third-party libraries may still use different APIs. Use the compiler, dependency tree, and migration guides to identify which packages need migration.

Confirm that `@Entity`, `@Id`, `@Version`, `@Valid`, and validation constraint annotations are imported from the exact namespace supported by the target provider/runtime. An annotation with the same name from the old namespace may be ignored by the new persistence or validation provider.

## Comparing Events and Validation

Review repository event handlers against their corresponding REST operations:

- `beforeCreate` for creation.
- `beforeSave` for updates.
- `beforeDelete` for deletion.
- `beforeLinkSave` and `beforeLinkDelete` for association changes.

Check bean naming conventions if using event-based validators, or validator registration via `RepositoryRestConfigurer`. Confirm handlers run only within the corresponding Spring Data REST pipeline; direct repository calls from services, batches, or message listeners do not automatically trigger REST events.

Business rules that must apply to all entry points belong in the domain/service layer. REST events serve as an integration layer for auto-generated endpoints. After upgrading, test both HTTP requests and direct service calls to catch bypassed logic.

## Comparing Transactions, Security, and CORS

Verify service/repository transaction boundaries, optimistic locking, auditing, and domain events. In particular, ensure external side effects run only after commit if business requirements demand it.

With Spring Security, review URL matchers, method security, authentication principals, CSRF, and CORS. Security configuration may change across Spring Security generations; do not trust old tests if they no longer execute through the security filter chain.

Verify:

- Anonymous requests receive 401 or redirect according to the API contract.
- Insufficiently privileged users receive 403/404 and cannot read or edit out-of-scope records.
- POST/PUT/PATCH/DELETE include valid CSRF tokens when CSRF protection is enabled.
- CORS preflight returns the expected allow-origin, allow-methods, and allow-headers.
- `ETag`/`Location` are exposed if browser clients need to read those headers.

## Controlled Upgrade Process

1. Record the dependency tree and runtime configuration of the source version.
2. Select a compatible target version from the Spring Boot BOM/release train; read release notes and migration guides for that exact version span.
3. Inventory annotations, configurers, event handlers, custom repository methods, and endpoints used by the application.
4. Compare property names and defaults; explicitly configure values that affect clients.
5. Update `javax`/`jakarta` packages and method signatures to match target APIs.
6. Compile and fix deprecated/removed APIs per target version guidelines.
7. Run HTTP integration tests covering HAL links, statuses, headers, pagination, projections, PATCH, validation, and events.
8. Run security tests covering authentication, record-level authorization, CSRF, and CORS.
9. Compare sample responses before/after upgrading; document intentional differences and update client contracts.
10. Run smoke tests using production-like configuration/profiles before release.

## Minimum Regression Test Suite

| Area | Pre/Post-Upgrade Checks |
| --- | --- |
| API root | Base path, collection links, and `profile` link |
| Repository export | Collection/item/search/association endpoints |
| Representation | HAL media type, `_embedded`, `_links`, error body |
| Pagination | Default/max size, page/sort parameters, metadata |
| Projections | Projection names, excerpts, and nested fields |
| PATCH | JSON Patch, Merge Patch, omitted fields, nulls, and arrays |
| Validation/events | Create, save, delete, link, and unlink handlers |
| Concurrency | `@Version`, ETag, `If-Match`, 412 |
| Security | Authentication, authorization, CSRF, CORS |
| Configuration | Property binding and runtime values per profile |

For every write request, verify both status/headers and database state after the request. For failed requests, verify data was not modified unintentionally. Save representative HAL/ALPS responses as fixtures to catch contract drift in future upgrades.

## Principles for Concluding Changes

Do not label behavior a breaking change merely because old and new documentation have different examples. Identify actual versions, check API signatures or configuration metadata, execute requests against the application, and compare results. If a default is unconfirmed in the target version's documentation, mark it unverified and configure it explicitly to avoid relying on it.

A safe upgrade must prove all three layers: code uses the target version's APIs/annotations properly, runtime loads the expected configuration, and the HTTP contract seen by clients remains accurate or was changed intentionally.
# API Contract Versioning and Client Migration Strategies

## Objectives

An API contract describes what clients can rely on when communicating with a server: resource paths and relations, HTTP methods, parameters, request/response structures, data types, status codes, error rules, authentication, and business semantics. Versioning is the practice of publishing and maintaining different contract versions as an API evolves.

With Spring Data REST, repositories can automatically generate collection resources, item resources, search resources, and hypermedia links. This reduces the number of controllers you have to write, but it does not eliminate the responsibility of managing compatibility. A change to an entity, projection, repository exposure, or relation name can still break existing clients.

The goal of versioning is to allow an API to continue evolving while giving clients clear timelines and guidance to migrate to the new contract.

## 1. Distinguishing API Version from Application Version

Do not equate an API version with the application's build version or deployment version.

- **Application version** describes the server software build and deployment version, e.g., `2.8.1`.
- **API version** describes the contract visible to clients, e.g., `v1` or `v2`.
- **Resource representation version** describes a specific representation shape of a resource.
- **Schema version** describes the version of a schema or data structure used for exchange.

A server can ship many builds while preserving the exact v1 API contract. Conversely, a single deployment can serve both API v1 and v2 concurrently during a transition period.

Contract versioning must consider all observable behavior, not just JSON field names:

- URIs, relation names, and resource discovery mechanisms.
- HTTP methods, query parameters, pagination, and sorting.
- Request/response fields, data types, nullability, and formats.
- HTTP statuses, error structures, and retry rules.
- Authentication, authorization, rate limits, and operation semantics.
- Default ordering, filtering rules, and the meaning of returned data.

## 2. Identifying Compatible Changes and Breaking Changes

A compatible change allows existing clients to continue working with the new server without immediate modification. A breaking change can prevent existing clients from compiling, cause response parsing failures, or alter behavior.

| Change | Typical Assessment | Reason |
|---|---|---|
| Add optional response field | Compatible | Older clients can ignore unknown fields. |
| Add new endpoint or relation | Compatible | Older clients do not need to use the new capability. |
| Add optional query parameter with a behavior-preserving default | Compatible | Older requests retain the same meaning. |
| Remove or rename field/endpoint/relation | Breaking | Older clients can no longer find the element they depend on. |
| Change field type, unit, or format | Breaking | Clients may misparse or miscalculate values. |
| Make an optional request field required | Breaking | Older requests may be rejected. |
| Change business meaning while keeping field name | Behaviorally breaking | Clients still parse it but receive different results. |
| Change status code or error structure | Potentially breaking | Clients may branch logic based on status or error code. |
| Add enum value | Potentially breaking | Clients with closed enums or exhaustive switches may fail to handle the new value. |
| Change default sort, page size, or page indexing convention | Potentially breaking | The same request may return a different result set or order. |

Do not use field count alone to evaluate compatibility. For example, changing `amount` from đồng to thousands of đồng keeps the numeric type while altering the meaning; this is a contract-breaking change.

For responses, clients should ignore unrecognized fields and relations whenever possible. For enums, handle unknown values with a fallback branch or map them to a default state. For requests, the server still needs clear validation and structured error messages.

## 3. Strategies for Selecting an API Version

There are several ways for clients to specify which contract they want to use. Pick one consistent convention across the API and document it clearly.

### 3.1. Version in the URI

Example:

~~~http
GET /api/v1/people/42
GET /api/v2/people/42
~~~

Pros:

- The version is immediately visible in the URL.
- Easy to configure routes, gateways, logs, caches, and monitoring.
- Clients can explicitly pin a version.
- Two versions can be deployed side by side during transition.

Cons:

- Must maintain multiple routes and often multiple representations.
- Hypermedia links must point to the correct version's URI space.
- May create additional mapping code between the domain model and each version's DTOs.

This is the easiest option to observe and operate when multiple versions must coexist. Do not create a new version solely for each server release.

### 3.2. Version via Media Type

The client specifies the version in the `Accept` header:

~~~http
GET /api/people/42
Accept: application/vnd.example.person-v2+json
~~~

The server returns the corresponding representation if it supports that media type. For requests with a body, `Content-Type` describes the media type of the submitted payload.

Pros:

- Resource URIs can stay unchanged.
- Versions are tied to negotiated representations or contracts.
- Fits REST designs centered on content negotiation.

Cons:

- Harder to observe than URI versioning when looking only at URLs.
- Caches and proxies must account for the `Accept` header; responses need `Vary: Accept` when representations change by header.
- Clients must send the exact media type and handle unsupported media type responses.

When using vendor media types, publish the exact accepted media types, such as `application/vnd.example.person-v1+json` and `application/vnd.example.person-v2+json`.

### 3.3. Version via Custom Header

Example:

~~~http
GET /api/people/42
Api-Version: 2
~~~

This keeps URIs clean but requires clients and servers to agree on the header name, valid values, default version, and behavior when the header is missing. Caches must distinguish responses by the version header, typically via `Vary: Api-Version`. Gateways and debugging tools must also understand this header.

Custom headers do not automatically become a universal versioning standard. Choose this approach only when your organization's infrastructure already has conventions and full support for it.

### 3.4. Version via Query Parameter

Example:

~~~http
GET /api/people/42?version=2
~~~

This is easy to test but can make the API harder to standardize when every endpoint must carry a version parameter. It also increases the risk of cache mix-ups if cache keys do not include query parameters. Use this only with a clear rationale and well-defined rules across all resources.

### 3.5. Which Strategy Should You Choose?

| Criterion | URI | Media Type | Custom Header | Query Parameter |
|---|---|---|---|---|
| Visibility in logs | High | Medium | Medium | High |
| Preserves resource URI | No | Yes | Yes | Yes |
| Cache must vary by | URI | `Accept` | Version header | Query parameter |
| Client configuration needed | URL | Accept/Content-Type | Custom header | Query |
| Running multiple versions concurrently | Clear | Supported | Supported | Supported |

No single option fits every system. URI versioning is usually the simplest to implement and operate when many clients need explicit version selection. Media type versioning fits organizations already using content negotiation consistently. Whichever approach you choose, avoid allowing the same request to be interpreted under two different contracts without the client realizing it.

## 4. How Far Does Spring Data REST Support Versioning?

Spring Data REST focuses on exposing repositories and hypermedia representations. Relevant capabilities include:

- `@RepositoryRestResource(path = "people")` sets the collection resource path.
- `@RestResource(path = "...", rel = "...")` customizes a method's path or relation.
- `@Projection` defines a view of an entity.
- `excerptProjection` selects the projection used for items in a collection.
- `RepositoryRestConfigurer` configures base path, exporter, media types, converters, and other integrations.
- `@BasePathAwareController` and `@RepositoryRestController` support custom endpoints within the URL space associated with Spring Data REST.

These features help build representations and routes, but they do not provide a complete multi-version contract management lifecycle. A projection selects a representation shape; it is not automatically equivalent to API v1/v2. ALPS profiles describe API semantics; they are likewise not a request version selection mechanism.

Changing a repository's `path` or `rel` currently used by clients can be a breaking change. When v1 must remain available alongside v2, you must actively maintain both contracts and corresponding routes, or use content negotiation with explicit conventions.

## 5. Organizing v1 and v2 in a Spring Data REST Application

A practical approach is keeping repositories and domain services as shared data/business sources, then creating separate representations for each API version.

For example, the domain model may continue storing `firstName` and `lastName`, while v2 wants to expose `displayName`:

~~~java
public record PersonV1(
        Long id,
        String firstName,
        String lastName,
        String email) {
}

public record PersonV2(
        Long id,
        String displayName,
        String emailAddress) {
}
~~~

Mappers convert the domain model into the respective contracts:

~~~java
public final class PersonApiMapper {

    private PersonApiMapper() {
    }

    public static PersonV1 toV1(Person person) {
        return new PersonV1(
                person.getId(),
                person.getFirstName(),
                person.getLastName(),
                person.getEmail());
    }

    public static PersonV2 toV2(Person person) {
        return new PersonV2(
                person.getId(),
                person.getFirstName() + " " + person.getLastName(),
                person.getEmail());
    }
}
~~~

With URI versioning, a custom v2 endpoint can live under Spring Data REST's base path:

~~~java
import org.springframework.data.rest.webmvc.BasePathAwareController;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@BasePathAwareController
@RequestMapping("/v2/people")
public class PersonV2Controller {

    private final PersonRepository repository;

    public PersonV2Controller(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public ResponseEntity<PersonV2> findById(@PathVariable Long id) {
        Person person = repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));

        return ResponseEntity.ok(PersonApiMapper.toV2(person));
    }
}
~~~

If Spring Data REST's base path is `/api`, the example route will be `/api/v2/people/{id}`. This is an illustrative skeleton for a GET endpoint; corresponding methods, statuses, validation, error mappings, links, and security policies for the full v2 contract must be added before publishing.

Key principles:

1. **Keep domain logic shared:** v1 and v2 invoke the same application service when business rules have not changed.
2. **Separate DTOs by version:** do not modify entities directly just to match a new representation.
3. **Separate mappers:** v1/v2 mappers explicitly express field names, formats, and conversion rules.
4. **Keep routes independent:** avoid mapping v1 and v2 to the same handler with ambiguous request interpretation.
5. **Keep hypermedia consistent:** self links, relations, and navigation links must stay within the URI space or contract selected by the client.
6. **Verify permissions and validation:** v2 must not accidentally bypass security policies enforced by v1.

Do not register two repository interfaces managing the same domain type solely to create two versions and expect Spring Data REST to distinguish them automatically. When multiple representations are needed, intentionally design routes/controllers, projections, and mappers, then verify all actual mappings.

## 6. Using Projections Without Confusing Them with Versioning

Projections can help restrict which properties appear in a representation:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    Long getId();

    String getFirstName();

    String getLastName();
}
~~~

Clients can request a projection using the mechanism exposed by the repository, for example:

~~~http
GET /people/42?projection=personSummary
~~~

Projections are helpful when clients need multiple views of the same resource. However, if a projection is removed, has fields changed, or changes semantics, clients can still be affected. Projections do not inherently provide:

- Separate version namespaces and support policies.
- Independent status/error semantics.
- Deprecation and sunset processes.
- Parallel v1/v2 routes.
- Contract tests and migration guides.

Use projections for selecting representations within the same contract. When two clients require different compatibility commitments over an extended period, manage versions explicitly.

## 7. Process for Migrating Clients from v1 to v2

Version migration is a process with a timeline, owners, and completion criteria. A workflow can be executed in the following phases.

### Phase 1 — Inventory Clients and Usage

Identify:

- Which clients call v1: web frontends, mobile apps, partners, batch jobs, or internal services.
- Client application versions, owners, and environments in use.
- Endpoints, relations, fields, projections, and operations each client depends on.
- Call frequency and critical business flows.
- Which clients can upgrade quickly and which have long release cycles.

You can use API gateway logs, request metrics, or telemetry with client identifiers. Do not log access tokens, personal data, or sensitive payloads solely for version tracking.

### Phase 2 — Design and Publish the v2 Contract

Before rollout:

1. Write a v1 → v2 changelog listing every change and its rationale.
2. Publish schemas, request/response examples, statuses, and error formats.
3. Define the version selection mechanism and default behavior.
4. Document authentication, authorization, pagination, sorting, rate limits, and retry policies.
5. Provide a migration guide with before/after examples.
6. Specify the deprecation start date and expected v1 sunset date if policy permits.

OpenAPI can describe HTTP contracts, operations, schemas, and responses. With Spring Data REST, ALPS profiles provide semantic and link metadata; use documentation suited to how the API is actually published. Do not assume ALPS alone replaces OpenAPI or describes every request/response constraint.

### Phase 3 — Deploy in Parallel and Verify

Keep v1 running while bringing v2 online. Before general client adoption:

- Run contract tests for both v1 and v2.
- Verify DTO serialization/deserialization.
- Verify status codes, errors, access permissions, and pagination.
- Verify HAL links and relations point to the right version.
- Check cache keys, `Vary`, and gateway routing if versions are selected via headers.
- Run integration tests over real HTTP instead of only calling mappers or repositories directly.

You can roll out v2 to a small group of clients first using feature flags or gateway configuration. Where feasible, compare v1/v2 outputs in staging/test environments; do not execute duplicate real write operations just to compare because that can cause duplicate side effects.

### Phase 4 — Support Client Migration

Provide:

- Instructions for updating URLs or headers.
- Mapping tables from old fields to new fields.
- Request/response examples and error handling guidance.
- Details on changes to pagination, sorting, relations, and projections.
- SDKs or client libraries if maintained by the organization.
- Support channels and designated owners for each client.

Clients should pin their chosen version rather than relying on a default version that may change over time. Hypermedia clients should follow published relations and avoid concatenating URL strings when the server provides appropriate links.

### Phase 5 — Deprecation, Monitoring, and Sunset

Once v2 is ready and clients have a migration path:

1. Announce that v1 is deprecated with a clear timeline and reason.
2. Notify owners of clients still calling v1.
3. Monitor v1 traffic by client, route, and environment.
4. Send reminders ahead of the sunset deadline.
5. Decommission v1 only when migration criteria are met and support policies allow.
6. Keep archived documentation and handling guidance in case old clients still call after the cutoff date.

Standard HTTP response headers can be used to communicate lifecycle information:

~~~http
Deprecation: @1798761600
Link: <https://api.example.com/docs/deprecations/people-v1>; rel="deprecation"
Sunset: Wed, 30 Jun 2027 00:00:00 GMT
~~~

- `Deprecation` is defined in RFC 9745. Its value is a Structured Field Date (Unix timestamp prefixed with `@`), indicating when the API or element was marked deprecated.
- `Link` with relation `deprecation` can point to documentation explaining the change and migration instructions.
- `Sunset` is defined in RFC 8594, using an HTTP-date to announce when the resource is expected to become unavailable.

Dates in the example are format illustrations only, not default sunset schedules. Deprecation headers do not automatically block requests, and sunset headers do not automatically delete routes; the server still needs enforcement policies and direct client notifications.

## 8. Designing Change-Tolerant Clients

Clients also need to be designed so they do not break easily when the server adds capabilities:

- Ignore unrecognized JSON fields if they do not affect required logic.
- Handle unknown enums with a fallback branch rather than assuming a closed set of values.
- Follow HAL relations and server-returned links instead of hardcoding every path.
- Do not depend on JSON field ordering.
- Handle status codes, error bodies, and retry policies properly.
- Only retry safe or idempotent requests when justified; do not automatically retry resource-creating POSTs without an idempotency key or duplicate-prevention mechanism.
- Pin the API version and upgrade intentionally.
- Use contract tests to detect unexpected changes.

Client tolerance does not replace compatibility guarantees from the server. The server must still clearly document which fields are required, which may be absent, and the semantics of every operation.

## 9. Contract Testing and Multi-Version Monitoring

Each API version should be tested as an independent product.

| Test Layer | What to Verify |
|---|---|
| Contract test | Requests/responses, fields, media types, statuses, and error formats match specification. |
| Integration test | Routes, repositories, mappers, controllers, and hypermedia links work together. |
| Authorization test | v1 and v2 permissions are not unintentionally relaxed. |
| Compatibility test | Existing clients continue running when compatible server changes ship. |
| Consumer-driven contract | Critical client assumptions are automatically verified. |
| Regression test | Core business flows do not change outside the new version's scope. |

Dashboards should break down metrics by API version, client identity, route, and status code. Track at least:

- Request counts and error rates per version.
- Clients still calling deprecated versions.
- Routes or relations being used.
- Latency and timeout rates.
- Notable validation or deserialization errors.

Set measurable migration completion thresholds—for example, all clients confirmed migrated, v1 traffic at zero over a defined period, and no critical business flows depending on v1. Do not delete v1 merely because v2 deployed successfully.

## 10. Common Pitfalls in API Versioning

| Symptom | Causes to Investigate |
|---|---|
| Old client cannot parse new response | Fields renamed/retyped, new enum values, or nested structures changed. |
| v1 URL unexpectedly returns v2 representation | Default version or gateway routing changed; version not explicitly pinned. |
| HAL links direct clients to incompatible routes | Hypermedia links generated from default routes or mappings not bound to the version. |
| Cache serves a response from another version | Cache key missing the URI/header/query parameter used for version selection, or missing `Vary`. |
| Projections treated as contract versions | Projections only alter representation; they lack independent lifecycles and compatibility policies. |
| v2 alters v1 business behavior | Both versions share a service without isolating new rules; separate mapping from domain behavior. |
| Unsure which clients still use v1 | Missing telemetry, client identification, or per-version dashboards. |
| v1 shut down while clients still call it | Sunset unannounced/unmonitored or lacking clear migration criteria. |
| Retries create duplicate resources | Clients retry POST without an idempotency key or deduplication mechanism. |

## Key Takeaways

Versioning is a commitment about contracts and support windows. Classify changes before releasing; keep compatible changes within the same version when possible; create a new version for breaking changes; and run versions in parallel long enough for clients to migrate. In Spring Data REST, repositories and projections help build representations, while controllers, DTOs, mappers, configurers, and hypermedia links implement intentional contract versions. Deprecation, telemetry, migration guides, contract tests, and sunset policies complete each version's lifecycle.

## References

- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9745 — The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745)
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594)
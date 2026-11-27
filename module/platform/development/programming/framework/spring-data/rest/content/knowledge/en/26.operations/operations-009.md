# Reviewing the Published API Surface After Every Release

## Objective

Spring Data REST generates REST APIs from Spring Data repositories. Consequently, changes to repository interfaces, entities, associations, projections, export configurations, or Jackson settings can alter the API seen by clients even when no new controller is added. After every version upgrade or application release, the entire published HTTP contract must be reviewed to catch added/removed endpoints, representation changes, permission changes, or behavioral shifts.

The review must answer three questions:

1. Which resources can clients currently discover and invoke?
2. Have request/response structures, HTTP methods, media types, status codes, or metadata changed compared to the released version?
3. Are those changes compatible with existing clients, explicitly approved, and verified by tests?

The API surface is the externally observable contract. It includes HAL links, URI templates, ALPS/JSON Schema, query parameters, headers, and response statuses, not just a list of URLs.

## 1. Identifying Versions to Compare

Before testing, record the currently running versions and the versions planned for release:

- Spring Boot and Spring Framework versions.
- Spring Data release train and Spring Data REST version.
- Versions of Spring Data modules in use (Commons, JPA, MongoDB, JDBC, ...).
- Java, Jackson, and integration libraries that affect serialization or HTTP handling.
- Application settings that can alter exporting: repository detection, base path, repository visibility, `@RepositoryRestResource`, `@RestResource`, projections, excerpts, custom controllers, serializers, and security.

Spring Data modules do not necessarily share the same version number. Use the Spring Data release train BOM to select a compatible set of versions; never upgrade a single module independently just because version numbers look close.

When upgrading, read the upgrade guide and release notes from your current version to the target version. If skipping multiple release trains, read the release notes for every intermediate version as well. Spring Data notes that upgrade instructions appear at the top of release notes. Record changes affecting Spring Data REST, Spring Data Commons, store modules, and Spring Framework/Boot.

Do not treat library version numbers as the service's API contract version. A new release train may leave the published API unchanged; conversely, changing a repository or projection in the application can change the API even when dependencies stay the same.

## 2. Inventorying the Actual API Surface

Do not infer the entire API from source code alone. Start the application with the exact profile, feature flags, security, and configuration intended for release, then discover the API over HTTP.

### 2.1. Root Resource and HAL Links

Call the root URL and save the response along with headers:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
~~~

Spring Data REST uses HAL by default to represent links. Inside `_links`, each relation indicates a discoverable next resource. Check:

- Which relations appear and which relations disappear.
- Whether `href` changed its path, base path, scheme, host, or context path.
- Which links are URI templates and whether template variables changed.
- Whether `profile` is still published and points to the right metadata.
- Whether new resources appeared unintentionally because a new repository was discovered.

Do not hard-code a metadata URL based on old examples. Follow the `profile` link returned at the root, then follow each resource's links. Base path configuration and Spring Data REST versions can produce different concrete URIs.

### 2.2. Collection, Item, Association, and Search Resources

For each exported repository, inspect at least these resource types:

| Resource Type | What to Record |
|---|---|
| Collection | relation, URI, `GET`/`POST`, pagination, sorting, media type, status |
| Item | URI template, `GET`/`PUT`/`PATCH`/`DELETE`, response fields, ETag |
| Association | relation and URI, `GET`/`PUT`/`POST`/`DELETE`, `text/uri-list`, linking rules |
| Search | `search` relation, query method name/path, parameters, pagination, return type |
| Profile | metadata links, ALPS descriptors, JSON Schema |
| Custom endpoint | controller path, method, request/response, security, and errors |

Spring Data REST typically derives collection paths from the uncapitalized, pluralized domain type name. `@RepositoryRestResource` can customize the path or relation. Association paths default to the property name and can be customized with `@RestResource`.

Whether an HTTP method is exported depends on existing repository methods and export configuration. Removing a method or annotating `@RestResource(exported = false)` can make an operation disappear. Verify with actual requests; do not assume every repository exposes full CRUD.

The search resource appears only when a repository exposes query methods. Query resource names and paths can also be customized via `@RestResource` on the method. When comparing, record parameter names, parameter types, URI templates, and query results.

Discovery check examples:

~~~bash
curl -sS -H "Accept: application/hal+json" http://localhost:8080/orders
curl -sS -H "Accept: application/hal+json" http://localhost:8080/orders/search
curl -i -H "Accept: application/hal+json" http://localhost:8080/orders/1
~~~

The URLs above are examples only. Use actual links from your application's root/collection responses.

### 2.3. Request, Response, and HTTP Semantics

For every published operation, record:

- HTTP method and preconditions allowed for invoking it.
- Supported request `Content-Type` and response `Accept` media types.
- Required, optional, nullable, and read-only fields, plus data types.
- How associations are represented: inline data or URI links.
- Status codes for success, validation failure, not found, conflict, unsupported method, and authentication/authorization errors.
- Headers such as `Location`, `ETag`, `Last-Modified`, `Allow`, `Cache-Control`, and headers added by the application/proxy.
- Rules for `page`, `size`, `sort`, filters, and custom query parameters.

Spring Data REST may return `201 Created` for creations and `200 OK` or `204 No Content` for certain updates/deletes depending on configuration and headers. Do not document a single status code for the entire API; verify each operation and actual configuration.

Also test invalid requests: missing fields, wrong types, unsupported media types, nonexistent association URIs, disabled methods, and unauthorized users. Changes in status codes or error structures can also break clients.

### 2.4. Representation, Projections, and Excerpts

Inspect the JSON/HAL of collections and items. Pay particular attention to:

- Field names, types, date/time formats, numeric precision, enums, and `null` handling.
- Added or removed fields.
- Associations switching from links to inline objects or vice versa.
- Changes caused by Jackson serializers/deserializers, mixins, `@JsonIgnore`, or `ObjectMapper` configuration.
- Added, removed, or renamed projections.
- Excerpt projections applied by default in collections.

Projections can change returned fields when clients send the `projection` parameter. Excerpt projections are applied automatically to resources embedded in collections or associations per repository configuration; they are not automatically applied to item resources. Changing a default excerpt can be a breaking change for clients reading collections.

Do not assume newly added fields are always harmless: clients deserializing with strict schemas may reject unknown fields. Removed, renamed, or retyped fields—or fields changed from nullable to required—usually carry higher risk. Evaluate changes against how real clients parse responses.

### 2.5. ALPS and JSON Schema Metadata

Spring Data REST provides an ALPS document for every exported repository. The metadata describes representations, properties, and transitions/operations. Published projections can also appear in ALPS.

Follow the `profile` link at the root to retrieve each repository's profile resource:

~~~bash
curl -i -H "Accept: application/alps+json" http://localhost:8080/profile/orders
curl -i -H "Accept: application/schema+json" http://localhost:8080/profile/orders
~~~

The `/profile/orders` path follows the default documentation example. In real applications, follow links returned from root/profile and send the proper `Accept` headers.

Compare:

- ALPS descriptors for representations and operations.
- Descriptor names and types: `SEMANTIC`, `SAFE`, `IDEMPOTENT`, `UNSAFE`.
- Parameters such as `projection` and projection choices.
- JSON Schema `properties`, `type`, `format`, `readOnly`, nested structures, and schema version.
- Business description metadata declared via `rest.description.*`.

Metadata is part of the API surface if clients or automated tools rely on it for discovery and request generation. Do not ignore metadata merely because CRUD endpoints still return `200`.

## 3. Creating a Comparable Baseline

Store the baseline of the currently running release in the source repository or pipeline artifacts. A baseline should include:

1. Root HAL response.
2. List of repository relations and discovered links.
3. Representative collection/item/association/search responses.
4. ALPS and JSON Schema for each published repository.
5. Headers and statuses of key operations.
6. Responses for important projections/excerpts.
7. Access control matrix across primary roles.
8. Dependency versions and profile/feature flag configurations that produced the snapshot.

Example collecting a baseline with `curl`:

~~~bash
mkdir -p api-baseline
curl -fsS -H "Accept: application/hal+json" http://localhost:8080/ > api-baseline/root.json
curl -fsS -H "Accept: application/alps+json" http://localhost:8080/profile/orders > api-baseline/orders.alps.json
curl -fsS -H "Accept: application/schema+json" http://localhost:8080/profile/orders > api-baseline/orders.schema.json
~~~

These are sample commands; replace hosts and URIs with your application's addresses/links. When URIs are discovered through HAL, automate link traversal rather than hard-coding repository names or paths.

For collection/item responses with dynamic data, use deterministic fixtures in a test environment. Normalize non-contract values such as host/port, auto-generated IDs, timestamps, and arrays without guaranteed ordering. Never strip or normalize meaningful differences such as relations, URI templates, fields, data types, statuses, or headers.

Keep the raw original responses alongside normalized snapshots so diffs can be traced back to real outputs. Never include tokens, cookies, personal information, or sensitive production data in snapshots.

## 4. Classifying Changes After Each Release

Diff the baseline against the new build and classify every difference:

| Change | Client Risk |
|---|---|
| Removed/renamed URI, relation, or query method | High: clients cannot locate the resource |
| Removed field, renamed/retyped field, or changed association structure | High: clients parse or process incorrectly |
| Disabled HTTP method or changed request media type | High: operation can no longer be executed |
| Changed status code or error structure | Medium to high: retry/error handling logic may break |
| Changed pagination, sort, filter, or default size | Medium to high: returned data differs |
| Changed ETag/Last-Modified or `If-Match` precondition | High for clients doing concurrent updates/caching |
| Changed default projection/excerpt | High if clients rely on the old representation |
| Added field, relation, or query method | Usually additive, though strict parsers may still be affected |
| Tightened permissions or changed CORS | Can prevent existing clients from calling the API |
| Changed ALPS/JSON Schema metadata | Can affect clients doing auto-discovery or form generation |

Do not automatically label every difference as breaking or non-breaking. Consider how clients consume responses, whether they follow HAL relations or hard-code URIs, whether they apply strict schema validation, and whether they rely on default behavior.

For every difference, document:

- Old and new snapshots.
- Affected resources/operations.
- Client impact and compatibility level.
- Reason for the change.
- Migration path or deprecation window.
- Approving owner.

If a change breaks the published contract, consider keeping old aliases/fields during a transition period, adding a new endpoint/representation, or releasing a new API version per service policy. Never silently change a contract simply because newer dependencies compiled cleanly.

## 5. Contract Testing with MockMvc

Use `@SpringBootTest` with `@AutoConfigureMockMvc` to test the complete Spring Data REST configuration inside the application context. MockMvc executes requests through Spring MVC without starting a real HTTP server, making it well suited for verifying routes, statuses, media types, HAL links, and JSON bodies.

Example verifying root and collection:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PublishedApiContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rootPublishesOrdersAndProfileLinks() throws Exception {
        mvc.perform(get("/")
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith("application/hal+json"))
            .andExpect(jsonPath("$._links.orders.href").exists())
            .andExpect(jsonPath("$._links.profile.href").exists());
    }

    @Test
    void ordersCollectionPublishesExpectedContract() throws Exception {
        mvc.perform(get("/orders")
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.profile.href").exists())
            .andExpect(jsonPath("$._links.search").exists());
    }
}
~~~

This example assumes the repository is exported with relation `orders`, query methods are published, and the root path has no other prefix. If your application configures different relations/paths, update expectations to match the agreed contract.

Add tests for:

- Item resources: fields and association links.
- Search resources: query method names, parameters, and return types.
- Association resources: methods and `text/uri-list` when updating links.
- Projections/excerpts: returned fields for each selection.
- ALPS/JSON Schema: descriptors and key properties.
- Content negotiation: `Accept` and `Content-Type`.
- Status codes, `Location`, ETags, and conditional requests.
- Anonymous/user/various roles: read, create, update, and delete permissions.
- Error requests: validation, not found, unsupported method, and access denied.

Do not check only that endpoints return `200`. A `200` response can still be missing relations, fields, or metadata that clients depend on.

For tests that create/modify data, use fixtures with unique keys and clean up/roll back according to transaction boundaries. When using `RANDOM_PORT`, client requests and server handling run in separate threads/transactions; `@Transactional` on the test does not automatically roll back server operations. When verifying behavior against a live server, use independent cleanup for committed data.

## 6. Diff Testing in the Release Pipeline

An API surface verification pipeline can run in this sequence:

1. Build the application with the dependencies and configuration intended for release.
2. Start the application under the test profile with an isolated database/fixture.
3. Wait for the health check and verify the expected build/version is running.
4. Collect root, collection, search, profile, ALPS, JSON Schema, and sample responses.
5. Normalize dynamic values while preserving all contract attributes.
6. Diff the new snapshot against the released baseline.
7. Run MockMvc contract tests, integration tests, and security tests.
8. Produce a diff report and require API owner approval for risky changes.
9. Update the baseline only after the new release is approved.

You can use `curl`/JSON parser scripts in CI to generate snapshots. If the project has an OpenAPI document generated by a separate library, add an OpenAPI diff step as well. Spring Data REST provides HAL and ALPS/JSON Schema metadata; do not assume it automatically generates OpenAPI for every repository.

Illustrative test commands:

~~~bash
./mvnw test
./gradlew test
~~~

If the project uses the Maven/Gradle wrapper, pick the corresponding command and test profile. Add the contract snapshot step to the release pipeline rather than running unit tests alone.

## 7. Pre-Release Approval Checklist

- [ ] Recorded Spring Boot, Spring Framework, Spring Data release train, and Spring Data REST versions.
- [ ] Read upgrade notes/release notes for every release train between the old and new versions.
- [ ] Started the application using the exact profile/configuration intended for deployment.
- [ ] Compared root HAL links and repository relations.
- [ ] Verified collection, item, association, and search resources.
- [ ] Compared HTTP methods, media types, query parameters, statuses, and headers.
- [ ] Compared fields, data types, associations, projections, and excerpts.
- [ ] Saved and diffed ALPS and JSON Schema.
- [ ] Verified access permissions and error responses by role.
- [ ] Classified, explained, and approved all differences.
- [ ] Contract tests and snapshot pipeline all pass.
- [ ] New baseline updated only after changes are approved.

## 8. Common Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| A collection relation disappeared | Repository no longer discovered/exported or `exported` changed | Check repository interface, package scan, `@RepositoryRestResource`, and root HAL |
| Collection exists but `POST`/`PUT` returns `405` | Repository method missing or export disabled | Check the corresponding method and `@RestResource(exported = false)` |
| Search link disappeared | Query method not exported or name/path changed | Check repository methods, `@RestResource` annotations, and `/search` response |
| JSON field missing/structure changed | Projection, excerpt, Jackson config, or model changed | Compare item/collection responses and ALPS |
| Collection differs from item | Excerpt projection is applied by default only to embedded resources | Check `excerptProjection` and call the item directly |
| Schema/ALPS differs while CRUD still runs | Metadata or projection descriptors changed | Follow `profile` link, verify `Accept` headers, and diff descriptors |
| Returned URIs have wrong host/path | Base path, servlet context path, proxy forwarded headers, or link config | Check root links in the deployment environment and proxy configuration |
| Tests pass but production clients fail | Tests used mocks lacking security/proxy/container or unrealistic fixtures | Add integration tests through a live server/ingress for infrastructure-dependent parts |
| Snapshot changes on every run | Unstable IDs, timestamps, hosts, ordering, or fixture data | Isolate fixtures and properly normalize dynamic values |
| Dependency upgrade causes module version skew | Manually managing individual versions instead of using the release train BOM | Check dependency tree and imported BOM |

When encountering a difference, preserve the exact request, response, headers, versions, and configuration that produced it. That makes reproducing the issue straightforward and separates real contract changes from environment differences.

## Official Documentation

- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/): feature overview, repository resources, representations, conditionals, metadata, security, and customization.
- [Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection/item/association/search resources, method exposure, media types, and status codes.
- [Metadata: ALPS and JSON Schema](https://docs.spring.io/spring-data/rest/reference/metadata.html): profile links, ALPS descriptors, projection metadata, and JSON Schema.
- [Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): projections, excerpt projections, and impact on representations.
- [Upgrading Spring Data](https://docs.spring.io/spring-data/rest/reference/introduction/upgrade.html): upgrade instructions and requirement to review intermediate release notes.
- [Spring Data release notes and supported versions](https://github.com/spring-projects/spring-data-commons/wiki): release trains, supported versions, and release notes.
- [Spring Data dependencies and release train BOM](https://docs.spring.io/spring-data/rest/reference/data-commons/dependencies.html): selecting compatible Spring Data versions via BOM.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, mock/live web environments, and transaction boundaries.
- [Spring Framework — MockMvc](https://docs.spring.io/spring/reference/testing/mockmvc.html): testing Spring MVC requests/responses without a real server.
- [Spring Framework — Spring MVC Test](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): setup, assertions, and MockMvc limitations.
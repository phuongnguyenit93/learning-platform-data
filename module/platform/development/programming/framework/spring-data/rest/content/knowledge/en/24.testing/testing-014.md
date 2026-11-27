# Regression Testing Unintended Exposure When Adding Repositories or Methods

## 1. Goal

Spring Data REST can automatically publish repositories as REST resources. As a project grows, a new repository or a new public method can introduce additional collections, items, search endpoints, or association links that the development team did not intend to expose.

This constitutes an API surface change, even when new code was added solely for internal use. Without regression tests, a new endpoint might inadvertently:

- Leak internal entities or data.
- Allow clients to create, edit, or delete data via exported CRUD methods.
- Publish a query method as a search endpoint.
- Add association links pointing to sensitive resources.
- Alter the hypermedia contract relied upon by existing clients.

This hands-on lab builds tests verifying exactly which repositories, HTTP methods, search methods, and association links are permitted to be published. The goal is catching unexpected API surface changes right in CI.

## 2. Why Can Adding a Repository Change the API?

Spring Data REST discovers repositories according to a repository detection strategy. When a repository is detected and exported, the framework can create:

- A collection resource to read or create entities.
- An item resource per entity.
- A search resource if the repository has exported query methods.
- Association resources for linkable persistent associations.

Example new repository:

    public interface InternalAuditRepository
            extends JpaRepository<InternalAudit, Long> {
    }

If the repository is detected and exported under current configuration, it may expose a collection endpoint like `/internalAudits` along with item resources. Simply intending for the repository to be used by internal services does not automatically hide it from REST.

Similarly, adding a public repository for batch jobs or admin tasks can expose endpoints without a single new controller being written. Therefore, code reviews must examine changes to repository interfaces and export settings too.

## 3. Repository Detection Strategy

Spring Data REST supports several repository detection strategies. Exact strategies must be checked against your application version and configuration. Common options include:

- DEFAULT: Spring Data REST's default strategy, applying default detection rules.
- ALL: exports all detected repositories.
- ANNOTATED: exports only repositories annotated with RepositoryRestResource, excluding those with `exported=false`.
- VISIBILITY: relies on repository interface visibility per framework rules.

You can configure the strategy via RepositoryRestConfiguration:

    @Configuration
    public class RepositoryRestConfig
            implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            config.setRepositoryDetectionStrategy(
                RepositoryDetectionStrategy.RepositoryDetectionStrategies.ANNOTATED
            );
        }
    }

With the ANNOTATED strategy, repositories require explicit opt-in:

    @RepositoryRestResource(
        collectionResourceRel = "customers",
        path = "customers"
    )
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

Unannotated internal repositories can still be injected and used by services, while remaining unexported under this strategy.

Enum names, packages, and default behavior can differ across Spring Data REST generations. Cross-reference the API of your actual dependency before applying settings. Regression tests should check the root response and endpoints directly, rather than merely trusting that a strategy was configured.

## 4. Hiding Internal Repositories with exported=false

An explicit opt-out approach is:

    @RepositoryRestResource(exported = false)
    public interface InternalAuditRepository
            extends JpaRepository<InternalAudit, Long> {
    }

The repository remains a Spring Data bean usable by services. `exported=false` prevents Spring Data REST from publishing the corresponding repository resource.

Use this annotation for repositories holding internal data or system-only tasks whenever the active detection strategy might export them.

If the project uses the ANNOTATED strategy, only annotated repositories are exported; you can still keep `exported=false` as an explicit signal of non-public intent. Agree on team conventions so developers do not copy-paste export annotations without evaluating the data.

## 5. Adding New Methods Can Also Expand the API

Repository methods are not purely internal code. Spring Data REST can publish CRUD methods and query methods depending on declared methods, exposure configuration, and annotations.

Example:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        List<Customer> findByCity(String city);

        @RestResource(exported = false)
        List<Customer> findInternalByEmail(String email);
    }

Method `findByCity` can appear in the search resource under its corresponding finder relation. Clients can call the query endpoint over HTTP GET and pass the `city` parameter.

Method `findInternalByEmail` is marked `exported=false` so that finder is not published. The method can still be invoked from services or internal Java code.

When adding a new public method, determine:

1. Does the method become a REST endpoint?
2. Does it introduce a new relation inside the search resource?
3. Does the query return sensitive data or bypass tenant/owner filters?
4. Does the method allow unintended write or delete operations?
5. Does it require `exported=false` or a custom security policy?

Never treat a method being created for internal service use as proof that it will not be exported.

## 6. HTTP Method Exposure Is Also Part of the API Contract

A collection resource typically supports GET and POST if the repository provides matching methods. Item resources typically support GET, PUT, PATCH, and DELETE based on exported CRUD methods. Association resources may support GET, PUT, POST, and DELETE depending on the association and configuration.

A small change such as adding `deleteById`, `save`, or extending `CrudRepository` can alter which HTTP methods are supported.

You can disable specific methods by marking the repository method `exported=false` when appropriate:

    @RestResource(exported = false)
    @Override
    void deleteById(Long id);

Check exact method signatures and behavior against your current Spring Data version. For broader exposure control, Spring Data REST provides `RepositoryRestConfiguration` exposure configuration to disable HTTP methods by domain type or resource type.

Regression tests should check individual methods, for example:

- Collection GET is permitted.
- Collection POST is rejected if the API is read-only.
- Item GET is permitted.
- Item PUT/PATCH/DELETE are rejected if outside the contract.
- Search publishes only approved finders.
- Association mutations are enabled only for required relations.

Do not test only successful GETs. An endpoint can look safe for reads while unintentionally leaving PUT or DELETE open.

## 7. New Associations Can Expose Additional Links

When an entity adds a persistent association, Spring Data REST may add a relation to the parent resource's HAL representation.

For example, Customer initially has only `name` and `email`. Later a developer adds:

    @ManyToOne
    private InternalProfile internalProfile;

The HAL response may gain an `internalProfile` link if the association is exported and linkable. This is an API change even though Customer's collection path did not change.

If the association should not be public, annotate it:

    @ManyToOne
    @RestResource(exported = false)
    private InternalProfile internalProfile;

Regression tests should verify sensitive relations do not appear in `_links` and also call the association URL directly to ensure the endpoint is not unintentionally open. Hiding a link in a representation does not replace authorization on the target endpoint.

When adding an association, also check whether the target entity has an exported repository, whether the association path/rel is customized, and whether clients could follow links to read out-of-scope data.

## 8. Defining the Expected API Surface

Before writing tests, list the contract permitted for publication. Example:

| Resource | Allowed | Disallowed |
|---|---|---|
| `/customers` | GET, POST | Do not allow DELETE on collection |
| `/customers/{id}` | GET, PATCH | Do not allow PUT or DELETE if API forbids them |
| `/customers/search` | Only `byCity` finder | Do not publish `internalByEmail` finder |
| `/customers/{id}/address` | GET, PUT | Do not publish internal associations |
| `/internalAudits` | Not exported | No collection/item/search resources |

This table is an example. Derive the list from the actual API contract, security requirements, and repository exposure configuration.

You can store expected relation names in tests to compare against HAL responses. When a new repository or association appears, the test fails because an unapproved relation is present.

## 9. Testing API Root to Detect New Repositories

The API root typically publishes collection resources via HAL links. You can use MockMvc:

    @SpringBootTest
    @AutoConfigureMockMvc
    class RepositoryExposureRegressionTest {

        @Autowired
        private MockMvc mockMvc;

        @Test
        void rootExposesOnlyApprovedRepositories()
                throws Exception {

            mockMvc.perform(get("/")
                    .accept("application/hal+json"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                    "$._links.customers.href"
                ).exists())
                .andExpect(jsonPath(
                    "$._links.internalAudits"
                ).doesNotExist());
        }
    }

The test confirms the `customers` collection relation exists and `internalAudits` does not appear in the root representation.

If the API uses a base path, adjust the request path accordingly. If profiles, environments, or security filters vary, run tests with configuration closest to production.

Root tests only detect relations at the entry point. Add direct URL tests as well to guarantee a repository was not accidentally exported while omitted from root due to special configuration or link assembly.

## 10. Testing Search Resources and Query Methods

Read Customer's search resource:

    mockMvc.perform(get("/customers/search")
            .accept("application/hal+json"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links.findByCity.href"
        ).exists())
        .andExpect(jsonPath(
            "$._links.findInternalByEmail"
        ).doesNotExist());

If path or rel is customized via RestResource, use the actual rel/path in assertions.

You can verify internal finders cannot be called over HTTP. Depending on framework behavior, unexported endpoints may return 404 or omit the search relation; assert the contract confirmed on your running version.

Do not check only that the link is hidden. Call known finder paths directly to confirm the server refuses to execute internal queries over REST.

## 11. Testing HTTP Method Exposure

Use MockMvc to confirm unintended methods are not open:

    @Test
    void internalRepositoryDoesNotAcceptCrudRequests()
            throws Exception {

        mockMvc.perform(get("/internalAudits")
                .accept("application/hal+json"))
            .andExpect(status().isNotFound());

        mockMvc.perform(post("/internalAudits")
                .contentType("application/json")
                .content("{\"message\":\"test\"}"))
            .andExpect(status().isNotFound());
    }

This example assumes the repository is completely unexported. If the repository is exported while a specific method is disabled, the response may be 405 Method Not Allowed instead of 404. Verify status against your specific exposure configuration.

For a read-only repository, verify POST/PUT/PATCH/DELETE are disallowed:

    @Test
    void customerResourceDoesNotExposeDelete()
            throws Exception {

        mockMvc.perform(delete("/customers/{id}", 42L))
            .andExpect(status().isMethodNotAllowed());
    }

Do not blindly copy example statuses if the project has custom exception handlers or different exposure settings. The goal is confirming the method performs no data modifications.

## 12. Testing Association Links and Direct Endpoints

Read a Customer:

    mockMvc.perform(get("/customers/{id}", 42L)
            .accept("application/hal+json"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links.address"
        ).exists())
        .andExpect(jsonPath(
            "$._links.internalProfile"
        ).doesNotExist());

Then try the direct URL of the internal association if the path is known:

    mockMvc.perform(get(
            "/customers/{id}/internalProfile", 42L)
            .accept("application/hal+json"))
        .andExpect(status().isNotFound());

If the endpoint is protected by security rather than completely hidden, status may be 401 or 403 per policy. What matters is that unauthorized callers cannot read data simply by typing the URL directly.

When adding a new association, test both the parent HAL representation and the association endpoint. A new link can open traversal paths to resources clients previously could not reach.

## 13. Testing with Controlled Contract Snapshots

You can maintain an expected list containing:

- Relations at the API root.
- Relations inside each item resource.
- Relations inside search resources.
- Permitted HTTP methods for each resource.
- Expected statuses for hidden endpoints or forbidden methods.

Tests can extract keys inside `_links` and compare the relation set against the expected list. When the API changes intentionally, reviewers update the contract alongside the code change.

Do not snapshot entire JSON responses when responses contain IDs, timestamps, ETags, or dynamic data. Prefer snapshotting the stable API surface: relation names, href patterns, supported methods, and status behaviors.

If using snapshot files, keep contents small and reviewable. Never auto-approve new snapshots in CI; updating the expected contract must be reviewed as an API change.

## 14. Distinguishing API Exposure from Authorization

An unexported repository, an omitted association link, and an endpoint rejected by Spring Security are three distinct states:

- Export configuration decides whether Spring Data REST creates the resource/HTTP method.
- Association configuration decides whether the relation and association resource are published.
- Spring Security decides whether the caller has permission to access the endpoint.

A missing link does not prove the target endpoint is secured. A hidden repository likewise does not protect another custom controller or service exposing the same data.

A regression suite should verify:

1. Are expected resources/relations published properly?
2. Are expected HTTP methods enabled properly?
3. Are callers lacking permissions rejected when hitting direct URLs?
4. Can authorized callers still access valid resources?

Do not treat 404, 403, and link omission as interchangeable if the API contract assigns distinct meanings to each case.

## 15. Organizing the Regression Suite in CI

Divide tests into small groups:

**Repository exposure tests**

Verify the API root publishes only approved repositories and internal repositories lack collection/item/search resources.

**Method exposure tests**

Verify GET/POST/PUT/PATCH/DELETE per collection, item, and association resource contracts.

**Search exposure tests**

Verify public query finders appear in search resources; internal finders are hidden and direct URLs do not execute.

**Association exposure tests**

Verify HAL links match the approved list; new associations do not expose internal entities.

**Authorization tests**

Verify anonymous, under-privileged, and privileged callers against direct URLs.

**Persistence safety tests**

After disallowed requests, confirm repositories/databases show no changes. This prevents tests from passing solely on response status while data still got written.

Run these tests in CI whenever repository interfaces, entity associations, `RepositoryRestConfigurer`, security configurations, or Spring Data REST dependencies change.

## 16. Sample Review Checklist for Repository Changes

When a pull request adds a repository or method, reviewers can check:

1. Does the new repository genuinely need to be exported over REST?
2. If export is needed, are collection path and rel set explicitly?
3. If export is not needed, does the repository have `exported=false` or an appropriate detection strategy?
4. Do new public query methods appear in search resources?
5. Do new CRUD methods open additional POST/PUT/PATCH/DELETE operations?
6. Do new associations appear in HAL `_links`?
7. Do any fields or associations contain internal data/PII?
8. Do security rules cover collection, item, search, and association endpoints?
9. Do integration tests probe direct URLs?
10. Were API contracts or snapshots updated intentionally?

The checklist helps reviewers spot API changes even when diffs reside mainly in repository interfaces or entity mappings.

## 17. Common Mistakes

**Checking only new controllers**

Spring Data REST generates endpoints from repository metadata; no new controller is needed for the API surface to change.

**Assuming internal repositories are not exported**

A public repository may be picked up by the active detection strategy. Check the strategy and root links.

**Forgetting query methods**

Adding a finder can expose a relation in the search resource. Check both links and direct finder URLs.

**Checking only links without checking endpoints**

A hidden link does not automatically secure a URL. Send direct requests in tests.

**Checking only GET**

Repository method exposure can alter write/delete methods. Test POST, PUT, PATCH, and DELETE.

**Overlooking new associations**

Adding a persistent property can introduce a new link in HAL representations. Check item `_links`.

**Asserting only status in tests**

An error response does not guarantee data was untouched. Check repository/database state after the request.

**Auto-updating snapshots**

New snapshots can accidentally bless sensitive endpoints. Require review for API surface changes.

**Running tests with configuration differing from production**

Repository detection, base path, security, and profiles can vary across environments. Use test configurations reflecting production.

## 18. Hands-On Exercise

Given an exported `CustomerRepository` and an internal-only `InternalAuditRepository`:

1. Configure the active repository detection strategy and record its behavior.
2. Create a new `InternalAuditRepository`; run the API root test and verify the repository does not appear.
3. Mark the internal repository `exported=false` or switch to an opt-in detection strategy.
4. Add a `findByCity` finder and confirm the search relation appears properly.
5. Add a `findInternalByEmail` finder with `exported=false`; confirm the finder does not appear and direct URLs do not execute.
6. Add an `InternalProfile` association to `Customer`; confirm the relation does not appear when unexported.
7. Add a public CRUD method or override a method; inspect how HTTP method exposure changes.
8. Write tests for GET/POST/PUT/PATCH/DELETE per contract.
9. Have an unprivileged caller hit collection, item, search, and association URLs directly.
10. Verify the database remains unchanged after rejected requests.
11. Build an expected relation set and compare against API root/search/item HAL links.
12. Run the full regression suite in CI.

Self-check questions:

- Why can adding a repository alter the REST API even without adding a controller?
- How does `RepositoryDetectionStrategy` affect export?
- Why can a new query method appear inside a search resource?
- How does `exported=false` on a repository differ from `exported=false` on a method/association?
- Why is it necessary to test both HAL relations and direct URLs?
- How do you detect newly exposed unintended CRUD methods?
- Why do API surface snapshots require manual review?
- Why should persistence state be verified after a rejected request?

## 19. Takeaways

- Spring Data REST can automatically generate collection, item, search, and association resources from repository metadata.
- Adding a repository or public method can alter the API surface.
- The repository detection strategy determines which repositories are discovered and exported.
- Use `RepositoryRestResource` and `exported=false` to make publishing intent explicit.
- Query methods can appear in search resources; verify both relations and direct endpoints.
- CRUD method exposure affects supported HTTP methods.
- New associations can add relations to HAL `_links`.
- Test API root, items, search, associations, and each HTTP method.
- Hidden links do not replace authorization; probe direct URLs.
- Regression tests must confirm data remains unchanged after rejected requests.
- Updating API snapshots is a contract change requiring review.

## References

- Spring Data REST Reference — Repository resources and repository method exposure: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST Reference — Getting started and repository detection: https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html
- Spring Data REST Reference — Customizing repository exposure and supported methods: https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html
- Spring Security Reference — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html

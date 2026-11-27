# Verifying API Root, Resource Paths, Rels, and HAL Structure in Spring Data REST

Spring Data REST publishes repositories as HTTP resources and uses hypermedia to describe how clients discover and navigate the API. A good test should verify the API entry point, the links advertised by the server, the target URI of each link, and the HAL structure received by the client.

Do not guess endpoints solely from entity names or repository names. The API root and `rel` relations in HAL form the discovery contract of the API. Clients and tests should start from the links returned by the server, then verify the URIs and representations they lead to.

## 1. Distinguishing API Root, Resource Path, and Link Relation

These three concepts are related but serve distinct roles:

- **API root** is the entry point of Spring Data REST. From here clients discover published repository resources.
- **Resource path** is the HTTP path used to access a collection, an item, an association, or a search resource.
- **Link relation (rel)** is the relation name describing the meaning of a link in a hypermedia document. Clients use the rel to locate the right link without knowing the specific path ahead of time.

For example, the API root might return:

    {
      "_links": {
        "orders": {
          "href": "https://api.example.com/api/orders"
        },
        "customers": {
          "href": "https://api.example.com/api/customers"
        },
        "profile": {
          "href": "https://api.example.com/api/profile"
        }
      }
    }

In this example, `orders` and `customers` are rels; the `href` values are resource paths/URIs that clients can access. `profile` leads to metadata describing the API.

If the application configures `spring.data.rest.base-path=/api`, the API root resides under that base path. When no base path is configured, the entry point is usually at the application root. Check the environment configuration and use the matching base path when writing integration tests.

Do not assume the rel always matches the class name, repository name, or final URL segment. They can be customized independently.

## 2. Discovering the API from the Root

A hypermedia client begins with a request to the API root and reads the published links:

    GET /api
    Accept: application/hal+json

A HAL response typically contains a `_links` object. Each relation has an `href`; some links may have a `templated: true` attribute when the URI contains variables requiring substitution.

Example root response:

    {
      "_links": {
        "orders": {
          "href": "http://localhost:8080/api/orders"
        },
        "customers": {
          "href": "http://localhost:8080/api/customers"
        },
        "profile": {
          "href": "http://localhost:8080/api/profile"
        }
      }
    }

The discovery workflow should be:

1. Call the API root under the configured base path.
2. Find the rel of the desired repository, such as `orders`.
3. Extract `href` from that link.
4. Call the retrieved URI to read the collection.
5. From the collection, follow links to item, search, or profile resources as needed.

If a repository does not appear at the root, check whether the repository is exported by Spring Data REST, whether `exported = false` is set, and whether exposure restrictions are configured. Do not fabricate fallback URLs before determining if the repository is intentionally exposed.

## 3. Customizing Rel and Path

Spring Data REST allows customizing the collection rel and resource path via `@RepositoryRestResource`:

    @RepositoryRestResource(
        path = "customer-records",
        collectionResourceRel = "customers"
    )
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

With this configuration, the collection path is `customer-records`, while the rel clients use to find the link at the API root is `customers`.

For example, the root may return:

    {
      "_links": {
        "customers": {
          "href": "http://localhost:8080/api/customer-records"
        }
      }
    }

The relation name and URI can differ while still satisfying the contract. Therefore tests need to verify both:

- Does the root publish the rel the API commits to providing?
- Does the `href` of that rel lead to the right endpoint and does the endpoint return the expected representation?

Do not merely assert a fixed URL string if the application can run under different hosts, ports, or base paths. Prefer checking the path relative to test configuration or following the URI returned by the server.

## 4. Verifying Collection Resources and HAL

When a client follows a collection link, Spring Data REST typically returns a HAL collection. For a repository with data and pagination enabled, the typical structure includes:

- `_embedded`: contains the items, grouped under the collection rel.
- `_links`: contains self, profile, search, and pagination navigation links when applicable.
- `page`: contains pagination metadata such as size, totalElements, totalPages, and number.

Example:

    {
      "_embedded": {
        "orders": [
          {
            "id": 42,
            "description": "Order example",
            "_links": {
              "self": {
                "href": "http://localhost:8080/api/orders/42"
              }
            }
          }
        ]
      },
      "_links": {
        "self": {
          "href": "http://localhost:8080/api/orders"
        },
        "profile": {
          "href": "http://localhost:8080/api/profile/orders"
        },
        "next": {
          "href": "http://localhost:8080/api/orders?page=1&size=20"
        }
      },
      "page": {
        "size": 20,
        "totalElements": 21,
        "totalPages": 2,
        "number": 0
      }
    }

This is an illustrative example of a multi-page collection; pagination links appear only when applicable to the result set. An empty collection may not contain the item array shown in the example, so tests verifying item structure should prepare fixtures to ensure at least one record exists.

The key name inside `_embedded` is typically tied to the collection rel. If the rel is customized, the embedded key must also be checked against the configured rel, not an entity name guessed by the test.

### Verifying item resources

An item resource typically contains entity data and its own `_links`. The `self` link points to the item itself; association links may lead to related resources:

    {
      "id": 42,
      "description": "Order example",
      "_links": {
        "self": {
          "href": "http://localhost:8080/api/orders/42"
        },
        "customer": {
          "href": "http://localhost:8080/api/orders/42/customer"
        }
      }
    }

Tests should confirm that the self link exists, the URI is accessible, and required association rels are published. Whether an association appears depends on mappings, export configuration, and access permissions.

## 5. Verifying Association and Search Links

Association links allow clients to navigate from an item to its relationships without manually assembling URLs:

    GET /api/orders/42
    Accept: application/hal+json

From the response, the client reads the `customer` rel, extracts `href`, and then calls that URI to read the related Customer. Association paths can be customized; rels can also be customized via `@RestResource` on the association.

Search resources are typically discovered via the `search` rel on the collection:

    GET /api/orders

The client follows the `search` link, then reads the query links published at the search resource. For example, a query method might be defined as:

    public interface OrderRepository
            extends JpaRepository<Order, Long> {

        @RestResource(path = "by-status", rel = "byStatus")
        List<Order> findByStatus(@Param("status") OrderStatus status);
    }

The search resource can publish the `byStatus` rel alongside a URI template for the `status` parameter. Tests should confirm that the search link exists and that the URI template includes the parameter advertised by the API; then call the endpoint with a valid value and verify the results.

Do not confuse the `search` rel with the rel of an individual query method. `search` leads to the search resource; rels such as `byStatus` are published inside the search resource to describe individual queries.

## 6. Media Type and HAL Structure

When you want to verify HAL, explicitly send the header:

    Accept: application/hal+json

The HAL JSON media type is `application/hal+json`. The Accept header helps tests confirm the hypermedia representation that clients actually request. If a test only checks plain JSON, it may miss missing `_links` or `_embedded` errors.

Important HAL components:

| Component | Meaning | What to verify |
|---|---|---|
| `_links` | Hypermedia links of the resource | Required rels and valid hrefs |
| `_embedded` | Resources embedded in the representation | Collection rel and item structure |
| `self` | Link to the current resource itself | URI points to the right resource |
| `profile` | Link to profile/metadata description | Followable when metadata discovery is needed |
| `search` | Link to the search resource | Published query rels |
| `page` | Pagination metadata of the collection | number, size, and element totals when pagination is enabled |
| `templated` | Indicates href is a URI template | Clients substitute variables following URI template conventions |

A HAL document can contain business data properties alongside hypermedia components. Do not check a single entity field and conclude the HAL representation is correct. Verify the media type, link relations, and embedded structure appropriate for the endpoint.

## 7. Writing Integration Tests with MockMvc

The following example illustrates testing the API root and collection. Assume the repository is published with rel `orders` and default collection path `orders`; if the project customizes these, substitute expected values matching the real contract:

    import org.junit.jupiter.api.Test;
    import org.springframework.beans.factory.annotation.Autowired;
    import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
    import org.springframework.boot.test.context.SpringBootTest;
    import org.springframework.hateoas.MediaTypes;
    import org.springframework.test.web.servlet.MockMvc;

    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

    @SpringBootTest
    @AutoConfigureMockMvc
    class SpringDataRestHypermediaTest {

        @Autowired
        MockMvc mockMvc;

        @Test
        void apiRootPublishesOrdersRelation() throws Exception {
            mockMvc.perform(get("/api")
                    .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content()
                    .contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.orders.href").exists());
        }

        @Test
        void ordersCollectionHasHalStructure() throws Exception {
            mockMvc.perform(get("/api/orders")
                    .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content()
                    .contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._embedded.orders").isArray())
                .andExpect(jsonPath("$.page.size").exists());
        }
    }

If no base path is configured, replace `/api` with the actual API root. If the collection rel is customized, replace `orders` in JSONPath with the corresponding rel. Collection tests require fixture data if you want to verify item structure inside `_embedded`; page metadata tests only apply when the repository uses pagination.

### Verifying items and associations

You can verify an item by a fixed URI from a fixture:

    @Test
    void orderItemPublishesSelfAndCustomerLinks() throws Exception {
        mockMvc.perform(get("/api/orders/42")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content()
                .contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.customer.href").exists());
    }

In real applications, create fixtures with deterministic IDs or retrieve IDs from test data. If the API customizes the association rel, use the customized rel in JSONPath. To avoid tying tests to auto-generated IDs, you can read the URI from a collection or root response and then follow that link in the next test step.

## 8. Checking Rel and Href Without Host Dependency

A brittle test often compares the full URL against a string containing a fixed host or port:

    assertEquals(
        "http://localhost:8080/api/orders",
        actualHref
    );

This approach can fail when tests run on a random port, behind a reverse proxy, or under a different base path. If the host is not part of the contract, check:

- The required rel exists.
- The href has a valid scheme/host if it is an absolute URI, or is a relative URI resolvable from the API root.
- The path of the href matches the configured resource path.
- Following that href yields the expected status and media type.

Example of reading a link from a response:

    MvcResult result = mockMvc.perform(get("/api")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andReturn();

    String body = result.getResponse().getContentAsString();
    String ordersHref = JsonPath.read(
        body, "$._links.orders.href"
    );

In multi-step tests, use the `ordersHref` extracted from the response to call the collection instead of reconstructing the URL manually. With MockMvc, convert the path and query of that URI into a request URI appropriate for the test context; with `TestRestTemplate` or `WebTestClient`, you can follow the URI against the actual base URL.

If the API returns a URI template, check the `templated` flag and populate variables using an appropriate URI template builder. Do not send a raw template containing curly braces as if it were a complete URL.

## 9. Verifying Custom Configurations

When an API uses the following annotations or configurations, tests must reflect the declared contract:

- `@RepositoryRestResource(path = ..., collectionResourceRel = ...)`: check collection path and root rel independently.
- `@RestResource(path = ..., rel = ...)`: check path and rel of the corresponding association or query resource.
- `spring.data.rest.base-path`: send requests to the right API root under the base path.
- `exported = false`: confirm the repository or association is not published if intended.
- Projections and excerpt projections: representations may add or alter visible properties; still verify important hypermedia links.
- Pagination configuration: check navigation links and the `page` object when endpoints return paginated collections.

When a link disappears or a path changes, cross-reference annotations, Spring Data REST configuration, and the actual response. Do not fix tests by changing rels/paths based on guesswork before confirming whether the change reflects the intended contract.

## 10. Common Mistakes When Testing Hypermedia

| Symptom | Possible cause | How to check |
|---|---|---|
| API root lacks expected rel | Repository is not exported, custom rel, or wrong base path | Check repository annotations and root response |
| Rel exists but href differs from expected path | Path is customized or application runs under a base path/proxy | Follow href and inspect the actual endpoint |
| Collection lacks expected `_embedded` key | Different collection rel, empty data, or different representation | Check rel and fixture, explicitly request HAL |
| Response lacks `_links` | Request did not ask for HAL or endpoint does not return hypermedia as expected | Send `Accept: application/hal+json` and check Content-Type |
| Association link does not appear | Association is not exported or mapping does not expose a link | Check mapping and `@RestResource` |
| Search link lacks query rel | Query method is not exported or rel/path is customized | Check repository method and search resource |
| Tests fail when changing ports | Test hard-codes absolute URLs | Read href from response or compare URI paths |
| Page metadata does not appear | Endpoint does not return a paginated collection | Check repository configuration and return type |

## 11. Recommended Testing Workflow

An integration test for Spring Data REST should follow the journey a real client takes:

1. Call the API root with `Accept: application/hal+json`; confirm status, media type, and key rels.
2. Follow the repository rel to obtain the collection URI; confirm href and collection response.
3. Check `_embedded`, `_links.self`, and page metadata if pagination is enabled.
4. Follow the self link of an item; check data and association rels.
5. Follow association links to confirm relationships lead to the right resources.
6. Follow the search link if the API exposes query methods; confirm query rels and results.
7. Run tests with custom base paths, rels, and paths to ensure clients do not depend on default names.
8. Check unexported repositories/associations to ensure they do not accidentally appear in the API root.

Tests should use stable fixtures and verify HTTP status, Content-Type, JSON structure, and link traversal. For links with dynamic URIs, verify relations and targets against configuration rather than hard-coding full URLs.

## 12. Key Principles to Remember

The API root is the starting point for discovering resources. Rel indicates the meaning of a link; href provides the URI to follow; paths can be customized independently of rels. HAL expresses links in `_links`, embedded resources in `_embedded`, and pagination metadata in `page` when applicable.

When tests start from the API root, follow the links published by the server, and verify both media type and HAL structure, the test suite protects the hypermedia contract that clients actually rely on.
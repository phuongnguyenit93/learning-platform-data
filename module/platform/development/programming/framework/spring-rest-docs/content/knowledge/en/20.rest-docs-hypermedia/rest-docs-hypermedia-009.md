# Verifying Actual Links with Snippets

## 1. Link snippets and link verification are two separate tasks

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. With hypermedia APIs, responses contain relations such as `self`, `next`, `orders`, or `profile`, paired with target URIs in `href`. Spring REST Docs extracts these links to produce snippets, which are then included into Asciidoctor/Markdown and run through build and CI.

Distinguish two goals:

- **Documenting links:** describing the relations and meanings of links present in the response using `links(...)`, `linkWithRel(...)`, or `linkWithHref(...)`.
- **Verifying links:** confirming the response has the right relations, right `href`, right path/query, and right appearance conditions per the API contract.

Example HAL response:

~~~json
{
  "id": 42,
  "name": "Mechanical keyboard",
  "_links": {
    "self": {"href": "https://api.example.test/api/products/42"},
    "reviews": {"href": "https://api.example.test/api/products/42/reviews"}
  }
}
~~~

The descriptor `linkWithRel("reviews")` helps Spring REST Docs locate the relation and generate the links table. To ensure the link leads to the right resource, the test also needs to verify `href` against the contract, for instance using JSONPath. A clean snippet alone does not prove the URL is accurate.

## 2. Confirming the response is genuinely hypermedia

Before checking links, confirm that the endpoint returns the right media type and hypermedia structure. With HAL, the media type is typically `application/hal+json`.

~~~java
mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links").exists());
~~~

These assertions confirm the expected status, a HAL media type compatible with the client, and that the body contains a `_links` region. If the endpoint only returns `application/json` with plain data, do not assume `links(...)` can extract a HAL structure. When a matcher fails, print the response with `andDo(print())` or inspect `MvcResult` to view the actual received body.

## 3. Verifying relations with linkWithRel(...)

`linkWithRel(...)` selects a link based on its relation name. When passed into `links(...)`, the descriptor lets Spring REST Docs verify that the documented relation exists and write it into the snippet.

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andDo(document("products-get",
                links(
                        linkWithRel("self").description("Current product"),
                        linkWithRel("reviews").description("Product reviews"))));
~~~

In strict mode, default descriptors require the described relation to be present in the response. If `reviews` is unexpectedly removed or renamed, the documentation test can fail instead of silently generating a table missing the link.

Confirming that `rel` exists is not enough to guarantee the link points to the right URL. Verify `href` separately when the URI is a meaningful part of the contract for clients.

## 4. Verifying href with JSONPath

With HAL, links are serialized as objects inside `_links`, typically with an `href` attribute. JSONPath checks the existence and URI value:

~~~java
mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href")
                .value("http://localhost/api/products/42"))
        .andExpect(jsonPath("$._links.reviews.href")
                .value("http://localhost/api/products/42/reviews"))
        .andDo(document("products-get",
                links(
                        linkWithRel("self").description("Current product"),
                        linkWithRel("reviews").description("Product reviews"))));
~~~

The URLs in the example are illustrative. The actual URI may depend on host, port, context path, proxy, or link builder configuration. Check the exact URI form guaranteed by the API.

Compare the entire `href` exactly when the API guarantees a stable URI structure, when links contain explicitly specified queries, or when links target specific endpoints. If host/port are environment-provided, comparing the full absolute URL can make tests brittle. In that case, verify the path and query accurately while ensuring the URI is parseable.

## 5. Checking path and query in links

A link can have the right relation but wrong path parameters or query parameters. For example, pagination links must preserve the right `page` and `size`:

~~~json
{
  "_links": {
    "self": {"href": "/api/products?page=1&size=20"},
    "next": {"href": "/api/products?page=2&size=20"},
    "prev": {"href": "/api/products?page=0&size=20"}
  }
}
~~~

If query parameter order is normalized, you can compare directly:

~~~java
.andExpect(jsonPath("$._links.next.href")
        .value("/api/products?page=2&size=20"))
~~~

If query order is not guaranteed, avoid depending on the exact raw URL string. Extract `href`, parse it with `URI`, and inspect `getPath()` and query parameters by name/value.

~~~java
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

static Map<String, String> queryParameters(URI uri) {
    if (uri.getRawQuery() == null) {
        return Map.of();
    }
    return Arrays.stream(uri.getRawQuery().split("&"))
            .map(part -> part.split("=", 2))
            .collect(Collectors.toMap(
                    pair -> URLDecoder.decode(pair[0], StandardCharsets.UTF_8),
                    pair -> URLDecoder.decode(
                            pair.length == 2 ? pair[1] : "",
                            StandardCharsets.UTF_8)));
}
~~~

After extracting `href` from the response into a `URI`:

~~~java
assertThat(uri.getPath()).isEqualTo("/api/products");
assertThat(queryParameters(uri))
        .containsEntry("page", "2")
        .containsEntry("size", "20");
~~~

The helper above illustrates how to check queries independently of parameter order. For queries with repeated keys or complex encoding, use your project's proper parser instead of a `Map` storing only one value per key.

## 6. Combining linkWithHref(...) when identifying by target URL

`linkWithRel(...)` is generally stable and meaningful because the relation expresses the link's role:

~~~java
linkWithRel("reviews").description("Product reviews")
~~~

If you need to select a link by its `href` itself, Spring REST Docs also provides `linkWithHref(...)`:

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithHref;

links(
        linkWithHref("/api/products/42/reviews")
                .description("Product reviews page"))
~~~

This approach is useful when the target URI is the identification criterion fitting the documentation goal. However, URLs can change by host, port, version, or data; using relations generally produces less environment-dependent documentation. Regardless of which descriptor you pick, write separate assertions when you need to verify the actual `href`.

## 7. Checking required and optional links by state

Links may appear depending on resource state or collection page:

- `self`: required for identified resource representations.
- `next`: present only when a next page exists.
- `prev`: present only when not on the first page.
- `reviews`: may depend on publication policy or resource capabilities.

Descriptors use `optional()` when a link may be absent in valid responses:

~~~java
links(
        linkWithRel("self").description("Current page"),
        linkWithRel("prev").optional().description("Previous page"),
        linkWithRel("next").optional().description("Next page"))
~~~

`optional()` only relaxes the presence requirement for that relation. If the link appears, it is still documented. To verify pagination logic, write tests for specific states:

~~~java
@Test
void firstPageHasNextButNoPrevious() throws Exception {
    mockMvc.perform(get("/api/products?page=0&size=20")
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.next.href").exists())
            .andExpect(jsonPath("$._links.prev").doesNotExist())
            .andDo(document("products-page-first",
                    links(
                            linkWithRel("self").description("Current page"),
                            linkWithRel("prev").optional().description("Previous page"),
                            linkWithRel("next").optional().description("Next page"))));
}

@Test
void lastPageHasPreviousButNoNext() throws Exception {
    mockMvc.perform(get("/api/products?page=5&size=20")
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.prev.href").exists())
            .andExpect(jsonPath("$._links.next").doesNotExist())
            .andDo(document("products-page-last",
                    links(
                            linkWithRel("self").description("Current page"),
                            linkWithRel("prev").optional().description("Previous page"),
                            linkWithRel("next").optional().description("Next page"))));
}
~~~

Optional descriptors do not assert that `next` is present on the first page or `prev` is present on the last page. It is the JSONPath assertions in each test that verify those specific conditions.

## 8. Checking nested links in embedded resources

When a response contains embedded resources, the same relation can exist at the root and inside items:

~~~json
{
  "_embedded": {
    "stores": [
      {
        "id": 11,
        "_links": {
          "self": {"href": "/api/stores/11"},
          "products": {"href": "/api/stores/11/products"}
        }
      }
    ]
  },
  "_links": {
    "self": {"href": "/api/stores"}
  }
}
~~~

Checking links on the first item:

~~~java
.andExpect(jsonPath("$._embedded.stores[0]._links.self.href")
        .value("/api/stores/11"))
.andExpect(jsonPath("$._embedded.stores[0]._links.products.href")
        .value("/api/stores/11/products"))
~~~

Document relations inside each embedded resource using a subsection extractor:

~~~java
links(
        beneathPath("_embedded.stores[]"),
        linkWithRel("self").description("Current store"),
        linkWithRel("products").description("Products of the store"))
~~~

Root links use `links(...)` without a subsection extractor; nested links use the overload with `beneathPath(...)`. The two levels must be verified and documented separately. Checking only root `_links.self.href` says nothing about the `self` URL of each embedded store.

## 9. MockMvc example combining assertions and links snippet

The following example asserts status, media type, payload, link presence, and target URIs, then generates the `links` snippet:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class ProductLinkVerificationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void productLinksMatchTheContract() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$._links.self.href")
                        .value("http://localhost/api/products/42"))
                .andExpect(jsonPath("$._links.reviews.href")
                        .value("http://localhost/api/products/42/reviews"))
                .andDo(document("products-get",
                        links(
                                linkWithRel("self").description("Current product"),
                                linkWithRel("reviews").description("Product reviews"))));
    }
}
~~~

URLs in the example must be adjusted according to how the application constructs its base URI. If a random port or proxy changes the host, check path/query using a URI parser or configure a stable base URI for tests. Do not weaken assertions to merely checking `href` existence if the contract requires exact targets.

## 10. Verifying links are reachable

Checking that an `href` string is well-formed does not guarantee the target resource actually works. You can test navigation across two requests:

1. Call the initial collection or resource endpoint.
2. Retrieve the `href` link for the relation to follow.
3. Send a request to the target endpoint in the test.
4. Verify status, media type, and target content.

With MockMvc, a test can perform two requests with known URIs:

~~~java
@Test
void productReviewsLinkLeadsToReviewsEndpoint() throws Exception {
    mockMvc.perform(get("/api/products/{id}", 42)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.reviews.href")
                    .value("/api/products/42/reviews"));

    mockMvc.perform(get("/api/products/{id}/reviews", 42)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON));
}
~~~

This is an illustrative navigation test; the second request uses a known URI. If you want to verify that a client can use the exact `href` value returned, extract `href` from the first response and convert it into a URI/path for the next request. With MockMvc, do not send production absolute URLs over the network; convert `href` values matching the test host into local request URIs.

Example extracting the value:

~~~java
MvcResult first = mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andReturn();

String href = JsonPath.read(
        first.getResponse().getContentAsString(),
        "$._links.reviews.href");
~~~

Then extract path/query from `href`, confirm the host is within test scope, and invoke MockMvc with the corresponding URI. Do not take arbitrary URLs from responses and make external network calls in automated tests.

## 11. Identifiers and snippets reflecting verified links

Name identifiers clearly per operation:

~~~java
document("products-get",
        links(
                linkWithRel("self").description("Current product"),
                linkWithRel("reviews").description("Product reviews")))
~~~

Spring REST Docs writes the `links.adoc` snippet under the corresponding operation directory. An Asciidoctor page can include the snippet alongside the HTTP response:

~~~adoc
== View product

include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/http-response.adoc[]

=== Hypermedia relations

include::{snippets}/products-get/links.adoc[]
~~~

`links.adoc` explains relations and meanings; `http-response.adoc` shows the returned response; test assertions ensure links have values matching the contract. The three parts support one another and do not replace each other. With Markdown, default snippets are usually AsciiDoc, so an appropriate conversion or embedding step is needed.

## 12. Common errors when verifying links

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `links(...)` cannot find relation | Relation missing or wrong `rel` name | Check `_links` in body and descriptor. |
| Relation exists but link goes to wrong resource | Checked only `rel`, did not verify `href` | Add JSONPath assertion or URI check. |
| Absolute URL changes between dev and CI | Host/port generated per environment | Check URI path/query or configure a stable base URI. |
| Pagination link has wrong query | Link builder generates wrong page/size/filter | Check query with a URI parser and test first/last pages. |
| Test expects `next` on last page | Did not account for collection state | Verify contract; use optional descriptor and per-state assertions. |
| Root link is right but item link is wrong | Checked only root `_links` | Use JSONPath into embedded items and a subsection link descriptor. |
| Snippet misses new link | Strict links catches undocumented relation | Decide if relation is public; describe or intentionally ignore it. |
| Links snippet exists but target endpoint fails | Test only checked `href`, never called target URI | Add navigation test and check the related endpoint's response. |
| Asciidoctor missing `links.adoc` | Identifier or output path mismatch | Check snippet directory and include path. |

When troubleshooting errors, do not weaken strict links or drop assertions just to get the pipeline green. First determine whether the actual response violates the contract or the test describes the contract incorrectly.

## 13. Practice exercises

1. Create a HAL product detail endpoint with `self` and `reviews`; verify both relations and `href` values.
2. Change the base URI or run tests with a random port; adjust checks so they are host-independent while still verifying the right path.
3. Create pagination tests for first, middle, and last pages; verify `self`/`prev`/`next` along with query parameters.
4. Create a collection with embedded stores; verify `products` links on at least two items using JSONPath and a subsection link descriptor.
5. Using the `reviews` `href` from the response, verify that the target endpoint returns the expected status and media type.
6. Include `links.adoc` into Asciidoctor and wire the compile step after snippet-generating tests in CI.

**Completion criteria:** distinguish documenting links from verifying links; confirm exact `rel` and `href`; verify path/query, optional links, and nested links; verify target endpoints; snippets and documentation are generated from the current test run.

## 14. Checklist before publishing links

- [ ] Response has the proper hypermedia media type and link structure used by clients.
- [ ] `links(...)` describes the right relations and appropriate strict/optional mode.
- [ ] Assertions confirm required links actually exist.
- [ ] `href` is verified against the path/query or URI contract to protect.
- [ ] Dynamic host/port does not make tests brittle.
- [ ] Root links and links inside embedded resources are checked at the proper level.
- [ ] Key target endpoints have been verified for reachability.
- [ ] `links.adoc`, identifiers, and include paths match actual output.
- [ ] Build/CI runs snippet-generating tests before compiling and publishing.

**Key takeaway:** `links(...)` and `linkWithRel(...)` help document the relations present in a response; assertions are what verify the actual links have the right `href`, path, query, and navigation behavior. Combining these two parts lets Spring REST Docs snippets reflect a hypermedia contract that is both easy to understand and verified by tests.

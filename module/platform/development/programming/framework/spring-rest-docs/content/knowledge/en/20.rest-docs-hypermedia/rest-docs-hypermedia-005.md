# Content Types: HAL, Atom, and Other Hypermedia Formats

## 1. Why does Content-Type matter when documenting hypermedia?

Spring REST Docs generates REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. For responses with hypermedia links, REST Docs needs to know how to parse the link structure inside the payload. The same `rel` and `href` semantics can be represented differently depending on the format: HAL uses a `_links` object in JSON, Atom uses `<link>` XML elements, and other formats may use their own JSON/XML structures.

The HTTP `Content-Type` header indicates the format of the actual response. Spring REST Docs uses this information to choose the appropriate link extractor when generating the `links.adoc` snippet. If the media type is insufficient to determine the format, you can pass an extractor explicitly. For custom formats, you can supply a custom `LinkExtractor`.

Three options to distinguish:

| Response type | Commonly used media type | Link location |
| --- | --- | --- |
| HAL JSON | `application/hal+json` | `_links` object, where each relation maps to a link object or list of links. |
| Atom | `application/atom+xml` | `<link>` XML elements inside a feed or entry. |
| Other hypermedia format | Media type defined by the format/API | Custom structure; requires a corresponding extractor to generate the links table. |

```mermaid
flowchart TD
    A[HTTP response] --> B[Read Content-Type]
    B --> C{Format?}
    C -->|HAL| D[halLinks()]
    C -->|Atom| E[atomLinks()]
    C -->|Other / unrecognized| F[Custom LinkExtractor]
    D --> G[REST Docs extracts rel and href]
    E --> G
    F --> G
    G --> H[links.adoc]
```

Do not infer the format solely from filenames, endpoints, or URL extensions. Check the actual response headers and payload returned by the server.

## 2. HAL: links reside in `_links`

HAL (Hypertext Application Language) represents links inside the `_links` JSON property. A simple HAL response:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "payment": {
      "href": "/api/orders/42/payment",
      "title": "Pay for order"
    },
    "next": {
      "href": "/api/orders?page=1"
    }
  }
}
```

In HAL:

- `_links` is the container for links.
- Keys such as `self`, `payment`, and `next` are relations (`rel`).
- `href` points to the target URI; it can be a relative or absolute URI.
- Some link objects also include `title`, `type`, `hreflang`, `templated`, `deprecation`, `name`, or `profile` depending on the format and API contract.

With media type `application/hal+json`, Spring REST Docs can use the HAL link extractor. REST Assured example:

```java
given(this.specification)
        .accept("application/hal+json")
        .filter(document("orders-get",
                links(
                        linkWithRel("self").description("Current order"),
                        linkWithRel("payment").description("Open payment flow"),
                        linkWithRel("next").description("Next page of results"))))
.when()
        .get("/api/orders/42")
.then()
        .statusCode(200)
        .contentType("application/hal+json");
```

Static imports:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
```

If the format is already recognized from Content-Type, you can use `links(...)` directly. When you want to specify the extractor explicitly or the server returns a non-standard media type while the payload still follows HAL, use:

```java
links(halLinks(),
        linkWithRel("self").description("Current order"),
        linkWithRel("payment").description("Open payment flow"))
```

`halLinks()` specifies how to extract links from `_links`; it does not change the response Content-Type and does not turn arbitrary JSON into HAL. The payload must still follow the HAL structure for the extractor to read it properly.

## 3. Atom: links reside in XML elements

Atom is an XML syndication format. In an Atom feed or entry, a link is represented by a `<link>` element with attributes such as `rel`, `href`, `type`, `hreflang`, `title`, and `length`.

Example response:

```http
HTTP/1.1 200 OK
Content-Type: application/atom+xml;type=feed;charset=UTF-8
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>urn:example:orders</id>
  <title>Orders</title>
  <updated>2026-11-17T08:00:00Z</updated>
  <link rel="self" href="/api/orders" type="application/atom+xml"/>
  <link rel="next" href="/api/orders?page=1" type="application/atom+xml"/>
  <entry>
    <id>urn:example:orders:42</id>
    <title>Order 42</title>
    <link rel="self" href="/api/orders/42" type="application/atom+xml"/>
  </entry>
</feed>
```

When the response uses `application/atom+xml`, Spring REST Docs can select the Atom link extractor based on the media type. You can also specify it explicitly:

```java
given(this.specification)
        .accept("application/atom+xml")
        .filter(document("orders-feed",
                links(atomLinks(),
                        linkWithRel("self").description("Current orders feed"),
                        linkWithRel("next").description("Next feed page"))))
.when()
        .get("/api/orders")
.then()
        .statusCode(200)
        .contentType("application/atom+xml");
```

Additional static import:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.atomLinks;
```

The Atom link extractor reads `<link>` elements according to the Atom structure, not HAL's `_links` property. If the actual response is custom XML that does not follow Atom, `atomLinks()` is not the right choice merely because the payload is XML.

An Atom response may have multiple links with the same relation but different `hreflang`, `type`, or `title`. Read the raw response snippet so meaningful link variants are not overlooked. The standard `links.adoc` snippet focuses on relations and descriptions; it does not replace the full XML response.

## 4. Content-Type and content negotiation

A client can send an `Accept` header to express its preferred format; the server chooses a suitable representation and returns `Content-Type` describing the actual format. These two headers have different roles:

| Header | Direction | Meaning |
| --- | --- | --- |
| `Accept` | Request | Which format the client wants to receive, e.g. `application/hal+json` or `application/atom+xml`. |
| `Content-Type` | Response | Which format representation the server actually returns. |

Do not just set `Accept` on the request and assume the response is HAL. Verify the actual `Content-Type`:

```java
given(this.specification)
        .accept("application/hal+json")
.when()
        .get("/api/orders/42")
.then()
        .statusCode(200)
        .contentType("application/hal+json");
```

If the server returns `application/json` even when the client requests HAL, the endpoint may not have registered a HAL converter, Spring HATEOAS may not be enabled, or negotiation may be configured differently than expected. Do not force `halLinks()` to mask a server bug if the actual payload does not follow HAL.

With REST Assured, `.accept(...)` sets the request `Accept` header. With MockMvc, use `.accept(MediaType.parseMediaType("application/hal+json"))`; with WebTestClient, use `.accept(...)` accordingly. In all three cases, documentation must reflect the media type the server actually returns.

## 5. Other hypermedia formats: when do you need a custom `LinkExtractor`?

Not every response with links uses HAL or Atom. Some APIs may use:

| Format | Example link representation | Notes |
| --- | --- | --- |
| Collection+JSON | `collection.links` or links in items | Custom JSON structure, not HAL `_links`. |
| Siren | `links` and `actions` arrays | `actions` describe submittable operations, distinct from plain navigation links. |
| JSON:API | `links` at top-level/resource/relationship | Links can appear at multiple locations depending on resource level. |
| UBER or custom formats | Objects/arrays describing links and actions | Requires understanding the semantics of that specific format. |

The list above shows examples of other hypermedia formats; it does not mean Spring REST Docs automatically recognizes all of them. If the structure or Content-Type is not among the built-in extractors, provide an appropriate `LinkExtractor`.

`LinkExtractor` converts the payload and media type into a set of links by relation that Spring REST Docs can use. Conceptually, an extractor needs to:

1. Receive the response content together with `Content-Type`.
2. Parse the format properly (JSON/XML) using an appropriate parser.
3. Locate links according to the format's rules, including nested resource or relationship links if needed.
4. Extract relation, href, and title (if any) into Spring REST Docs link objects.
5. Return the result as a structure mapping relations to links.

Register the extractor in the snippet using the overload:

```java
links(customLinkExtractor,
        linkWithRel("self").description("Current resource"),
        linkWithRel("related").description("Related resource"))
```

Here `customLinkExtractor` is a project-provided implementation of `LinkExtractor`. Do not pass a format name or Content-Type string in place of an extractor. Write dedicated tests for the extractor with valid sample payloads, payloads missing links, multiple links with the same `rel`, URI templates, and invalid content.

Do not use regex to parse JSON/XML structures. Use Jackson or a safe XML parser that supports namespaces and escaping. For untrusted XML, avoid configuring the parser to allow external entities (XXE).

## 6. Conceptual example of a custom extractor

Suppose an API uses an internal JSON format:

```json
{
  "resource": { "id": 42 },
  "navigation": [
    { "relation": "self", "url": "/api/resources/42", "label": "Resource" },
    { "relation": "related", "url": "/api/resources/42/related", "label": "Related resource" }
  ]
}
```

Unlike HAL, this format places links under `navigation` and uses keys `relation`/`url`/`label`. A custom `LinkExtractor` needs to map:

| JSON key | Value to extract |
| --- | --- |
| `relation` | Relation name |
| `url` | Href |
| `label` | Title or payload-sourced link description |

Once the extractor converts these elements into Spring REST Docs `Link` objects, standard descriptors can be used:

```java
links(customLinkExtractor,
        linkWithRel("self").description("Current resource"),
        linkWithRel("related").description("Related resource"))
```

The exact implementation code depends on the `LinkExtractor` signature in the Spring REST Docs version your project uses. Consult the Javadoc for your exact version and keep the implementation small and unit-tested. The `linkWithRel(...)` descriptors still validate relations just like with HAL/Atom; only the payload extraction step changes.

## 7. Documenting the same API supporting multiple representations

An endpoint may support both HAL and Atom depending on `Accept`. In that case, write separate tests because the response Content-Type and link structure differ:

```java
@Test
void documentOrdersAsHal() {
    given(this.specification)
            .accept("application/hal+json")
            .filter(document("orders-hal",
                    links(halLinks(),
                            linkWithRel("self").description("Orders feed"),
                            linkWithRel("next").description("Next page"))))
    .when()
            .get("/api/orders")
    .then()
            .statusCode(200)
            .contentType("application/hal+json");
}

@Test
void documentOrdersAsAtom() {
    given(this.specification)
            .accept("application/atom+xml")
            .filter(document("orders-atom",
                    links(atomLinks(),
                            linkWithRel("self").description("Orders feed"),
                            linkWithRel("next").description("Next page"))))
    .when()
            .get("/api/orders")
    .then()
            .statusCode(200)
            .contentType("application/atom+xml");
}
```

The two tests use separate identifiers (`orders-hal`, `orders-atom`) so snippets do not overwrite each other. Descriptors can be shared if the API guarantees the same relation semantics in both representations. If the Atom response has different links from the HAL response, create separate appropriate descriptors.

When you want to verify specific payloads, add assertions and document the response body. Do not check `Content-Type` alone: the server could return the right media type while the payload lacks a relation clients need.

## 8. Combining the links snippet with HTTP response and payload

`links.adoc` presents relations alongside descriptions; `http-response.adoc` or `response-body.adoc` keeps an example of the actual representation. With HAL, readers need both to see what `rel` means and what values `href`/metadata hold. With Atom, the raw XML response reveals `href`, `type`, `hreflang`, or repeated links per relation.

Asciidoctor example:

```asciidoc
== Orders API - HAL representation

=== HTTP response
include::{snippets}/orders-hal/http-response.adoc[]

=== Link relations
include::{snippets}/orders-hal/links.adoc[]

== Orders API - Atom representation

=== HTTP response
include::{snippets}/orders-atom/http-response.adoc[]

=== Link relations
include::{snippets}/orders-atom/links.adoc[]
```

The `{snippets}` attribute must point to the test output directory. Plain Markdown does not natively process `include::...[]` syntax; if the project uses Markdown, an appropriate conversion step or embedding mechanism is needed.

## 9. Common errors when handling Content-Type and link extractors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `links.adoc` is empty or has no links | Extractor did not find the expected structure in the response. | Check Content-Type, payload, and select `halLinks()`/`atomLinks()` or a suitable extractor. |
| HAL response is not recognized | Server returns `application/json` instead of a HAL media type, or structure is not HAL. | Check the contract; only use explicit `halLinks()` when the payload truly follows HAL. |
| Atom extractor fails to extract links | XML does not follow Atom structure or has custom namespace/format. | Check `application/atom+xml` and `<feed>`, `<entry>`, `<link>` structure. |
| Client requests HAL but server returns Atom | Content negotiation or endpoint configuration is misconfigured. | Assert response `Content-Type`, check converters and supported media types. |
| Relation is in response but reported as undocumented | Strict `links(...)` has not described that relation yet. | Add a descriptor, or use optional/ignored/relaxed intentionally. |
| Descriptor has relation but reported as not found | Payload lacks the relation or extractor cannot read it. | Inspect raw response; check relation name and extractor. |
| Custom format does not generate snippet | Spring REST Docs lacks a built-in extractor for it. | Implement a custom `LinkExtractor` and unit-test it independently. |
| HAL/Atom table does not show needed metadata | The links snippet focuses on `rel` and description. | Include raw HTTP response/body or write a custom snippet for metadata. |

## 10. Practice checklist

- [ ] Inspected the actual response `Content-Type`, rather than guessing from request `Accept`.
- [ ] HAL uses `application/hal+json` and an appropriate `_links` structure.
- [ ] Atom uses `application/atom+xml` and `<link>` elements with proper namespace/structure.
- [ ] Selected `halLinks()` or `atomLinks()` when an explicit extractor is needed.
- [ ] Other formats have a custom `LinkExtractor` tested against multiple representative payloads.
- [ ] `links(...)` descriptors cover all important relations.
- [ ] Kept `http-response.adoc`/`response-body.adoc` so readers can see raw hrefs and metadata.
- [ ] Tests verify `Content-Type` and required relations.
- [ ] HAL/Atom tests use separate identifiers if the same endpoint supports multiple representations.
- [ ] Build/CI compiles and publishes snippets only from passing tests.

HAL and Atom may express the same hypermedia link concept while using different payload structures and media types. Spring REST Docs provides built-in extractors for these formats; for custom formats, implement an appropriate extractor rather than forcing responses into a HAL/Atom structure. Reviewing `Content-Type`, the links snippet, and the raw response together ensures the documentation reflects the exact representation clients receive.

## References

- [Spring REST Docs – Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs – HypermediaDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/HypermediaDocumentation.html)
- [Spring REST Docs – LinkExtractor API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/LinkExtractor.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [Atom Syndication Format RFC 4287](https://www.rfc-editor.org/rfc/rfc4287)

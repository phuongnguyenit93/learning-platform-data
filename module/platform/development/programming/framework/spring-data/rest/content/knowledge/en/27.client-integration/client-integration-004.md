# Navigating by rel and Safely Expanding URI Templates

Spring Data REST uses HAL to describe resources and the links available to follow next. Clients should look up links by **rel** (link relation) in the response and invoke the URI provided by the server. When a link has **templated: true**, href is a URI template and must be expanded with variables per RFC 6570 before sending the request.

This approach reduces client coupling to specific URLs. The server can change paths or base paths while the client continues navigating through stable relations.

## 1. HAL describes links by rel

A HAL response typically contains data and a **_links** object:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "collection": {
      "href": "https://api.example.com/orders"
    },
    "customer": {
      "href": "https://api.example.com/orders/42/customer"
    }
  }
}
~~~

Each key in **_links** is a relation:

- **self** points to the current resource.
- **collection** points to the collection containing the resource.
- **customer** points to the association resource of the related customer.

Rel describes a relationship, not necessarily a Java class name or database property name. The server can customize rel; clients should use the rel published by the API rather than inferring endpoints from entity names.

A link object can carry metadata such as **type**, **title**, **hreflang**, **profile**, or **deprecation**. These fields help clients understand the media type, title, language, or deprecation status of the link.

## 2. Navigating by rel instead of hardcoding URLs

The client starts from a known entry point URI:

~~~http
GET https://api.example.com/
Accept: application/hal+json
~~~

The response may provide links to collections:

~~~json
{
  "_links": {
    "orders": {
      "href": "https://api.example.com/orders"
    },
    "people": {
      "href": "https://api.example.com/people"
    }
  }
}
~~~

The client extracts the href of rel **orders** and calls that URI:

~~~javascript
const rootResponse = await fetch("https://api.example.com/", {
  headers: { Accept: "application/hal+json" }
});

if (!rootResponse.ok) {
  throw new Error("Cannot load API entry point");
}

const root = await rootResponse.json();
const ordersLink = root._links.orders;

const ordersResponse = await fetch(ordersLink.href, {
  headers: { Accept: "application/hal+json" }
});
~~~

If the server changes the collection path from **/orders** to **/sales-orders**, the client keeps working as long as rel **orders** continues to be published with the new href.

Do not concatenate URLs as baseUrl plus a fixed path. Reading href from the response keeps the client aligned with the server's mappings, base path, and API version.

## 3. Handling single links, multiple links, and CURIEs

A relation can point to a single link or multiple links. Example:

~~~json
{
  "_links": {
    "related": [
      {
        "href": "https://api.example.com/orders/42/invoice",
        "type": "application/pdf",
        "title": "Invoice"
      },
      {
        "href": "https://api.example.com/orders/42/receipt",
        "type": "application/pdf",
        "title": "Receipt"
      }
    ]
  }
}
~~~

Clients need to handle both forms: if the relation is an object, use that link; if it is an array, select a link based on metadata such as **type**, **title**, or **hreflang**.

~~~javascript
function linksForRel(links, rel) {
  const value = links?.[rel];
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

const documents = linksForRel(order._links, "related");
const invoice = documents.find(link => link.title === "Invoice");
~~~

HAL also supports compact URIs (CURIEs) to shorten relation names:

~~~json
{
  "_links": {
    "curies": [
      {
        "name": "ex",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "ex:approval": {
      "href": "https://api.example.com/orders/42/approval"
    }
  }
}
~~~

Rel **ex:approval** is a name expanded under the **ex** CURIE. CURIEs are used to namespace relation names; they are different from URI templates used to build endpoint URLs. Follow the href of the actual relation such as **ex:approval**, and do not call the CURIE href as a business endpoint.

## 4. URI templates and the templated property

A URI template is a URI containing variables that must be supplied before calling. For example, Spring Data REST can publish a search link:

~~~json
{
  "_links": {
    "findByStatus": {
      "href": "https://api.example.com/orders/search/findByStatus{?status,page,size,sort}",
      "templated": true
    }
  }
}
~~~

The **templated: true** property indicates that href is not yet a complete URI. Variables in this example include **status**, **page**, **size**, and **sort**.

RFC 6570 defines common expressions:

| Expression | Meaning |
|---|---|
| **{id}** | Inserts variable into the path |
| **{?q,page}** | Expands a query string with q and page |
| **{&size,sort}** | Appends variables to an existing query string |
| **{+path}** | Reserved expansion, preserving certain reserved characters |
| **{#fragment}** | Expands into a fragment |

With the template:

~~~text
https://api.example.com/orders/search/findByStatus{?status,page,size}
~~~

and values:

~~~json
{
  "status": "PAID",
  "page": 0,
  "size": 20
}
~~~

the expanded URI looks like:

~~~text
https://api.example.com/orders/search/findByStatus?status=PAID&page=0&size=20
~~~

If values contain special characters, the URI Template library encodes each variable appropriately for its position. For example, the string **C++ & Spring Data** must be encoded when placed in a query string.

## 5. Expanding templates with an RFC 6570 library

Use an RFC 6570-compliant library rather than writing your own placeholder replacement function. In Java and Spring HATEOAS, you can use **org.springframework.hateoas.UriTemplate**:

~~~java
import java.net.URI;
import java.util.Map;
import org.springframework.hateoas.UriTemplate;

String href =
    "https://api.example.com/orders/search/findByStatus{?status,page,size,sort}";

URI target = UriTemplate.of(href).expand(Map.of(
    "status", "PAID",
    "page", 0,
    "size", 20,
    "sort", "createdAt,desc"
));
~~~

If you already have a Link from Spring HATEOAS, get its href and expand it:

~~~java
Link searchLink = orderCollection.getRequiredLink("findByStatus");

URI target = UriTemplate.of(searchLink.getHref()).expand(Map.of(
    "status", "PAID",
    "page", 0,
    "size", 20
));
~~~

In JavaScript, choose an RFC 6570-compatible URI Template library. The following snippet illustrates conceptual usage; exact function names depend on the package:

~~~javascript
const href = orderCollection._links.findByStatus.href;

const target = uriTemplate.expand(href, {
  status: "PAID",
  page: 0,
  size: 20,
  sort: "createdAt,desc"
});

const response = await fetch(target, {
  headers: { Accept: "application/hal+json" }
});
~~~

Do not use manual string replacement. That approach easily misses query expansion, optional variables, commas, spaces, plus signs, ampersands, and position-specific encoding rules.

## 6. Distinguishing regular links and templated links

Clients must check the **templated** property:

~~~javascript
function resolveHref(link, variables, expandTemplate) {
  if (!link || typeof link.href !== "string") {
    throw new Error("HAL link has no href");
  }

  if (link.templated === true) {
    return expandTemplate(link.href, variables);
  }

  return link.href;
}
~~~

- If **templated** is true, use RFC 6570 to expand it.
- If **templated** is absent or false, use href as a complete URI.
- If the template requires a variable that the client does not have, fail clearly rather than sending a URI with unexpanded placeholders.

Do not assume every href is a template or that every template only has simple path variables.

## 7. Variable encoding and avoiding double encoding

Pass raw values to the URI Template library. Do not URL-encode values beforehand and pass them into the library, as this can cause double encoding.

Example value:

~~~text
C++ & Spring Data
~~~

Pass the exact raw string for the query variable. The library will encode spaces, plus signs, and ampersands according to RFC 6570 rules.

Important notes:

- Do not concatenate user input directly into href.
- Do not manually replace spaces with plus signs or percent-encoded sequences prior to expansion.
- Do not encode the entire URI after it has already been expanded.
- Distinguish variables inside paths from variables inside queries.
- Do not use reserved expansion for user-supplied data unless necessary.
- Validate that the expanded result is a valid URI before invoking it.

If a library only implements a subset of RFC 6570, verify the operators and variables published by the API. Do not assume every package has the same level of support.

## 8. Navigating with next, prev, and search

Spring Data REST commonly provides navigation links in collection representations:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.com/orders?page=1&size=20"
    },
    "profile": {
      "href": "https://api.example.com/profile/orders"
    },
    "search": {
      "href": "https://api.example.com/orders/search"
    }
  }
}
~~~

Clients should follow **next** to retrieve the next page rather than incrementing page numbers manually. Similarly, use **prev** if published by the server. When the server changes pagination strategy or introduces cursors, clients still rely on the relation without computing URLs themselves.

Rel **search** leads to the search resource. Clients can read the search resource response to discover query methods and their URI templates.

Navigation flow:

1. GET the entry point.
2. Follow rel **orders** to the collection.
3. Follow rel **search** to discover queries.
4. Select the rel of the desired query method.
5. If the link is templated, expand it with an RFC 6570 library.
6. Call the resulting URI and continue following rels in the response.

## 9. Validating and restricting link destinations

Links returned by a server are input data to the client. Do not send tokens or cookies to an arbitrary host simply because a response contains that href.

Before invoking a link, especially in clients carrying bearer tokens or cookies:

- Accept only allowed schemes, typically HTTPS in production.
- Verify the host and port belong to a trusted API origin allowlist.
- If href is relative, resolve it against the URI of the received response.
- Never forward Authorization headers automatically to another origin.
- Do not follow links with dangerous schemes such as javascript or data.
- Do not allow template variables to alter the host unexpectedly.
- Handle redirects according to the client's security policy.

For server-side clients, fetching arbitrary hrefs can also introduce SSRF. Validate destinations before sending requests and enforce an appropriate network egress policy.

HAL makes APIs discoverable, but it does not mean every URI in a response is safe to call with all credentials.

## 10. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Client calls wrong URL after server changes path | Client hardcoded endpoints | Navigate by rel and href |
| Request still has curly braces in the URL | Did not check templated or did not expand | Use a URI Template library when templated is true |
| Query value with ampersand splits parameters | Manual string concatenation without encoding variables | Pass raw values to an RFC 6570 expander |
| Value is encoded twice | Encoded manually before expanding | Perform encoding only once via the library |
| Expected rel not found | Custom relation, CURIE, or different rel name than expected | Read _links and follow the exact name published by the server |
| Relation returns multiple links | Client assumed links are always single objects | Normalize object/array and select using metadata |
| Token sent to another host | Trusted href without origin validation | Allowlist origins and never forward credentials indiscriminately |
| Pagination skips or repeats URLs | Computed next manually instead of following server links | Use the returned next/prev rels |

## 11. Client checklist

- Send an appropriate Accept header, typically **application/hal+json**.
- Start from the entry point or officially configured URI.
- Look up links in **_links** by relation name.
- Support relations containing either a single link or multiple links.
- Follow **self**, **next**, **prev**, **search**, and association rels as needed.
- Check **templated: true** before expanding href.
- Use an RFC 6570 library to expand URI templates.
- Pass raw variables and let the library handle encoding.
- Do not hardcode paths or manually substitute placeholders.
- Validate scheme, host, and port before sending credentials.
- Resolve relative URIs against the response URI.
- Handle link deprecation and media types per server-published metadata.

Official references:

- [Spring Data REST — Repository resources and HAL links](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring HATEOAS — Traverson and client-side navigation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS — URI templates](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/UriTemplate.html)
- [RFC 6570 — URI Template](https://www.rfc-editor.org/rfc/rfc6570)
- [HAL specification](https://stateless.group/hal_specification.html)

# `text/uri-list` and How to Represent One or More URIs

In REST APIs, clients usually send resource data as JSON. However, when referencing existing resources, sending the entire object can be redundant and can easily create inconsistent sources of truth. `text/uri-list` solves this with a simple plain-text body: each line contains a URI pointing to a resource.

In Spring Data REST, this media type is especially useful when working with **association resources**. Instead of sending a full Customer object or a full array of Product objects, the client sends the URIs of the resources to be linked to the current entity.

## 1. Objectives

After this lesson, you can:

- Explain what `text/uri-list` is and distinguish it from JSON.
- Represent a single URI or multiple URIs in the same request body.
- Set the `Content-Type` HTTP header properly.
- Locate association links in a Spring Data REST HAL response.
- Use `PUT`, `POST`, and `DELETE` appropriately when updating relationships.
- Recognize common mistakes when sending URI lists.

## 2. URIs, URLs, and the Role of the Media Type

A **URI (Uniform Resource Identifier)** is a string that identifies a resource. A URL is a kind of URI that specifies how to locate the resource, for example:

~~~text
https://api.example.com/customers/42
~~~

In a typical REST example, this URI identifies the customer with ID `42`. A client can use that URI to ask the server to read the resource, or send the URI to another endpoint to establish a relationship with that resource.

The media type describes the structure of the HTTP body. `text/uri-list` tells the server that the body is a plain-text list of URIs. It does not mean the server will automatically fetch every URI over the Internet; the receiving application decides how to resolve and validate each URI.

Two headers must be distinguished:

- `Content-Type`: the format of the body the client is sending.
- `Accept`: the response format the client wants to receive.

When sending a URI list to an association resource, the critical header is:

~~~http
Content-Type: text/uri-list
~~~

If the client wants a HAL response, it can also send:

~~~http
Accept: application/hal+json
~~~

Do not use `Accept` in place of `Content-Type`: the two headers describe opposite directions of the HTTP exchange.

## 3. Syntax of `text/uri-list`

This is a line-oriented format. Each URI sits on its own line.

### 3.1. A Single URI

The body has only one line:

~~~text
https://api.example.com/customers/42
~~~

The server receives a reference to customer 42. There is no need to wrap the URI in quotes or build a JSON object.

### 3.2. Multiple URIs

When you need to send multiple resources, put each URI on its own line:

~~~text
https://api.example.com/products/10
https://api.example.com/products/11
https://api.example.com/products/12
~~~

Three lines correspond to three URIs. This is how the list is represented; do not use commas, semicolons, or square brackets as separators.

### 3.3. Comment Lines

According to the format described in RFC 2483, a line beginning with `#` is a comment line and is ignored during processing:

~~~text
# Alternative URIs for the original resource
https://cdn.example.com/files/manual.pdf
https://backup.example.com/files/manual.pdf
~~~

The `#` character only starts a comment when it is the first character on the line. If `#` appears inside a URI, such as in a fragment identifier, it remains part of the URI:

~~~text
https://docs.example.com/guide#installation
~~~

For association update requests in Spring Data REST, send the URIs to link directly and avoid adding comment lines to the body. This keeps the payload clean and avoids relying on how a specific parser handles comments.

### 3.4. Rules to Remember

| Aspect | Rule |
|---|---|
| Separation | One URI per line |
| Comment lines | Lines starting with `#` per the RFC format |
| Line breaks | The RFC specifies CRLF for lines in `text/*` formats |
| Long URIs | Never insert a line break inside a URI |
| Delimiters | Do not use commas or semicolons |
| Structure | Do not wrap the list in a JSON array |
| Request header | Use `Content-Type: text/uri-list` |

A very long URI is still a single line. If you break a line in the middle of a URI, the server may treat the two halves as two separate URIs or reject the payload.

In files containing multiple URIs, ensure each line is terminated properly. The RFC specifies CRLF (`\r\n`) for this text format. When generating payloads in code, explicitly use CRLF rather than relying on the operating system's default line ending.

## 4. `text/uri-list` in Spring Data REST

Spring Data REST exposes repositories as REST resources. For a repository managing an `Order` entity, the API typically exposes:

- Collection resource: list of orders, e.g., `/orders`.
- Item resource: a specific order, e.g., `/orders/1`.
- Association resource: a resource representing the order's relationship with another entity, e.g., `/orders/1/customer` or `/orders/1/products`.

Association resources are generated from the associations of the domain object. Default names and paths are derived from property names and can be customized with `@RestResource` on the property. Therefore, clients should read the links returned by the server instead of guessing URLs.

### 4.1. Discovering Association Links via HAL

Send a `GET` request to the item resource:

~~~http
GET /orders/1 HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

The response may contain links similar to the following example:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/1"
    },
    "customer": {
      "href": "http://localhost:8080/orders/1/customer"
    },
    "products": {
      "href": "http://localhost:8080/orders/1/products"
    }
  }
}
~~~

This is an illustrative example. Actual relation names and URLs depend on the domain model, repository configuration, and application customizations. The client extracts the `href` of the desired relation and sends the request to that exact association resource.

### 4.2. HTTP Methods on an Association Resource

| Method | Meaning | Body |
|---|---|---|
| `GET` | Read the association state | No `text/uri-list` needed; Spring Data REST docs list HAL/JSON |
| `PUT` | Bind the resource(s) specified by URI to the association | `text/uri-list` |
| `POST` | Collection associations only; add new items to the collection | `text/uri-list` |
| `DELETE` | Unbind the association | Typically no body needed |

One distinction to keep in mind: `POST /orders` creates a new `Order` on the collection resource; `POST /orders/1/products` adds a `Product` to Order 1's collection association. The two endpoints have different meanings despite both using HTTP `POST`.

### 4.3. To-One Associations: Sending Exactly One URI with PUT

Suppose an `Order` has one `Customer`. To link Order 1 to Customer 42, send the Customer's URI to the association link:

~~~http
PUT /orders/1/customer HTTP/1.1
Host: localhost:8080
Content-Type: text/uri-list

http://localhost:8080/customers/42
~~~

This can be executed with `curl`:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data-binary "http://localhost:8080/customers/42" \
  "http://localhost:8080/orders/1/customer"
~~~

The body is the Customer's URI, not the Customer's JSON. Spring Data REST uses that URI to resolve the resource and bind it to the association.

For a to-one association, send only one URI. If the body contains multiple URIs, Spring Data REST returns `400 Bad Request` because the relationship accepts only a single target.

### 4.4. Collection Associations: Sending Multiple URIs

Suppose an `Order` has many `Product`s. Create a `products.uris` file with the following contents:

~~~text
http://localhost:8080/products/10
http://localhost:8080/products/11
http://localhost:8080/products/12
~~~

To add these Products to the collection association, send `POST` to the `products` link:

~~~bash
curl -i -X POST \
  -H "Content-Type: text/uri-list" \
  --data-binary @products.uris \
  "http://localhost:8080/orders/1/products"
~~~

Each line in the file is a resource to add. `POST` on an association resource applies only to collection associations and adds items to the collection.

If you need to send a set of URIs to bind to the association using `PUT`, use the same body format but change the HTTP method:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data-binary @products.uris \
  "http://localhost:8080/orders/1/products"
~~~

`PUT` and `POST` are not synonymous: `PUT` binds the specified resources to the association; `POST` adds new items to the collection association. Choose the method based on your update goal and the semantics exposed by the API.

### 4.5. Unbinding an Association

`DELETE` on an association resource unbinds the association:

~~~bash
curl -i -X DELETE \
  "http://localhost:8080/orders/1/customer"
~~~

Unbinding does not mean deleting the target entity from its repository. For instance, unlinking a Customer from an Order does not delete Customer 42. Deleting an entity is a separate operation on that entity's item resource.

Whether a method is permitted also depends on the association and the application's export configuration. If a method is unsupported or the association does not allow that operation, the server may return `405 Method Not Allowed`.

## 5. Building the Payload from a Java Client

When the client already has a list of `URI` instances, it can join them into a multi-line string. Example with Spring `WebClient`:

~~~java
import java.net.URI;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

List<URI> productUris = List.of(
    URI.create("http://localhost:8080/products/10"),
    URI.create("http://localhost:8080/products/11"),
    URI.create("http://localhost:8080/products/12")
);

String uriListBody = productUris.stream()
    .map(URI::toASCIIString)
    .collect(Collectors.joining("\r\n", "", "\r\n"));

WebClient client = WebClient.create();

client.post()
    .uri("http://localhost:8080/orders/1/products")
    .contentType(MediaType.parseMediaType("text/uri-list"))
    .bodyValue(uriListBody)
    .retrieve()
    .toBodilessEntity()
    .block();
~~~

Key points in this snippet:

1. Each element of the list becomes a separate line.
2. `URI` is used to represent and validate URI syntax on the client side.
3. `toASCIIString()` produces a URI string suitable for HTTP transmission.
4. `contentType(...)` sets the proper media type for the request body.
5. The list is not serialized as JSON before sending.

If you use `RestClient` or another HTTP client, the principle is the same: the body is a line-delimited string of URIs and the `Content-Type` header is `text/uri-list`.

For custom endpoints built with `@RestController`, do not assume that a `@RequestBody List<URI>` parameter will be handled automatically by Spring Data REST. Spring Data REST's `UriListHttpMessageConverter` is meant for reading and writing Spring Data REST representation models. A custom endpoint needs to explicitly define how to read the body, parse each line, and handle errors, or register a converter suited to the endpoint's parameter type.

## 6. Verifying Requests and Troubleshooting Errors

When a request does not behave as expected, check the following in order:

1. **Is the association link right?** Read the item resource and take the exact `href` from the HAL response. Do not guess paths from property names when the API provides links.
2. **Is the Content-Type right?** A URI list body must be accompanied by `Content-Type: text/uri-list`.
3. **Is the body structured properly?** Each line is one URI; no JSON brackets, commas, quotes, or line breaks inside a URI.
4. **Do the URIs point to resources the API can resolve?** Use URIs of exported resources and verify access permissions.
5. **Does the method match the cardinality?** `PUT` on a to-one association only accepts one URI; `POST` is supported only for collection associations.
6. **Is the method exported?** Repository and association configuration may restrict allowed HTTP methods.

Common indicators:

| HTTP status / symptom | Causes to check |
|---|---|
| `400 Bad Request` | Invalid body or multiple URIs sent to a to-one association |
| `405 Method Not Allowed` | Method not exported or association does not allow the operation |
| `415 Unsupported Media Type` | `Content-Type` header does not match a body format supported by the endpoint |
| Target resource not found | Wrong URI, resource does not exist, or API cannot resolve the URI |

Exact status codes beyond the cases documented by Spring Data REST also depend on the endpoint, converter, configuration, and application exception handlers. Read the response body and server logs rather than relying on status codes alone.

After a successful update, you can `GET` the item resource or association resource again to confirm the relationship changed as intended.

## 7. Common Design and Usage Mistakes

### Sending a JSON array while declaring `text/uri-list`

The following payload is not `text/uri-list`:

~~~json
[
  "http://localhost:8080/products/10",
  "http://localhost:8080/products/11"
]
~~~

This is a JSON array. If the endpoint expects `text/uri-list`, convert it into plain URI lines.

### Sending multiple URIs on the same line

The following payload is not a valid URI list in this format:

~~~text
http://localhost:8080/products/10, http://localhost:8080/products/11
~~~

The server may treat the entire line as a single invalid URI. Put each URI on its own line.

### Using the wrong endpoint

Sending URIs to `/orders` is not equivalent to sending URIs to `/orders/1/products`. The first endpoint is the collection resource for creating Orders; the second is the association resource of Order 1.

### Sending multiple URIs for a to-one relationship

A to-one association has only one target. Sending two URI lines for an association like `customer` produces `400 Bad Request`. If the domain model actually needs multiple targets, check the association cardinality and use the corresponding collection endpoint.

### Treating a URI as authorization

A syntactically valid URI does not prove that the caller is permitted to link that resource. The server must still verify that the resource exists, is within the supported API scope, and that the caller has permission to perform the operation. Never blindly trust arbitrary client-supplied URIs.

## 8. Security Considerations

A URI list can direct clients or servers toward sensitive resources. RFC 2483 warns about risks of forged URIs, malicious redirects, and information disclosure through URI lists. When implementing APIs:

- Authenticate and authorize access to every referenced resource.
- If the API only allows internal URIs, validate the scheme, host, and path according to application policy.
- Do not automatically make outbound HTTP requests to user-submitted URIs without SSRF protections.
- Avoid logging full URIs that contain tokens or sensitive data in query strings.
- Do not treat successful URI parsing as proof that a resource is valid or that the caller is authorized to use it.

## 9. Pre-Request Checklist

- [ ] Read the item resource and retrieved the association `href` from HAL.
- [ ] Selected the right HTTP method for a to-one or collection association.
- [ ] Set `Content-Type: text/uri-list`.
- [ ] Placed each URI on its own line.
- [ ] Did not send a JSON array, commas, or quotes around URIs.
- [ ] Included exactly one URI for a to-one association.
- [ ] Confirmed target URIs belong to the API and the caller is permitted to link them.
- [ ] Checked the response and re-fetched the association after updating.

## 10. Conclusion

`text/uri-list` is a compact plain-text format for passing one or more resource references. The core rules are **one URI per line** and setting the proper `Content-Type`. In Spring Data REST, retrieve association links from HAL, send URIs to the association resource, and choose `PUT`, `POST`, or `DELETE` according to the relationship's semantics. When the boundary between collection resources, item resources, and association resources is clear, linking entities over REST becomes straightforward and less error-prone.

## References

- [RFC 2483 — URI Resolution Services Necessary for URN Resolution, Section 5](https://www.rfc-editor.org/rfc/rfc2483.html#section-5): defines the `text/uri-list` format, comments, and the one-URI-per-line rule.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): describes collection, item, and association resources, as well as supported HTTP methods and media types.
- [Spring Data REST — UriListHttpMessageConverter API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/convert/UriListHttpMessageConverter.html): converter used to render links in representation models as `text/uri-list` and parse requests of this media type.

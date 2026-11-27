# Multi-Valued Headers, Special Characters, and URI Encoding

In a microservices system using **Spring Cloud LoadBalancer**, callers can invoke `inventory-service` through RestClient, WebClient, or OpenFeign using a logical URI such as `http://inventory-service/api/items/{sku}`. LoadBalancer picks a `ServiceInstance` based on service ID, discovery, health checks, and routing policies. Yet picking the right instance **does not guarantee the HTTP request matches the contract**: many 400, 401, 404, 414, or 431 errors stem from misjoined multi-valued headers, special characters in SKUs or queries being parsed as URI structure, or proxies and HTTP clients disagreeing on encoding rules.

This lesson in the **Contracts and Errors** chapter focuses on three tightly coupled areas:

1. **Multi-valued headers:** when a field can carry multiple values, when comma-joining is permitted, and the `Set-Cookie` exception.
2. **Special characters:** the boundary between data and syntax; controlling CR/LF, commas, semicolons, Unicode, header sizes, and sensitive data.
3. **URI encoding:** distinguishing paths, path segments, queries, reserved characters, UTF-8 percent-encoding, and encoding once at the right layer.

The goal is not memorizing a single `encode` function, but establishing a **wire contract** that callers, proxies, LoadBalancer, and downstream services interpret identically—and knowing which component is at fault when an error occurs.

## 1. An HTTP Contract Spans Multiple Layers

~~~mermaid
flowchart LR
    A["Business code"] --> B["RestClient / WebClient / OpenFeign"]
    B --> C["Header & URI builder"]
    C --> L["Spring Cloud LoadBalancer"]
    D["Discovery / ServiceInstance"] --> L
    L --> E["HTTP transport"]
    E --> P["Gateway / proxy (if present)"]
    P --> S["Inventory endpoint"]
~~~

A single request carries independent layers of data:

| Layer | Example | Who decides? |
|---|---|---|
| Service ID | `inventory-service` | Logical name in the URI or `@FeignClient(name)` |
| Physical address | `localhost:8082` | LoadBalancer after selecting an instance |
| Path template | `/api/items/{sku}` | API contract |
| Path variable | `SKU/A&B` | Caller data; must be encoded per path-segment semantics |
| Query key/value | `tag=red blue` | Search/filter contract; must be encoded as a query component |
| Request headers | `Accept`, `Authorization`, `X-Correlation-Id` | HTTP protocol + application policy |
| Response headers | `Cache-Control`, `Set-Cookie`, `Vary` | Downstream/gateway |
| Body | UTF-8 JSON | Content-Type, codec, DTO/validation |

Replacing the hostname `inventory-service` with an instance's host/port only solves **routing**. It does not repair malformed headers or request-targets. Every HTTP hop in the chain must agree on how to parse values that may contain delimiters.

## 2. HTTP Fields Can Appear on Multiple Lines or Contain Lists

Per **RFC 9110, Sections 5.2–5.3**, a field name can appear across multiple field lines. For fields whose *grammar permits list syntax*, multiple lines may be interpreted equivalently to a single comma-separated line preserving value order.

Example of two equivalent forms for a header with list grammar:

~~~http
Accept: application/json
Accept: application/problem+json
~~~

~~~http
Accept: application/json, application/problem+json
~~~

However, this rule **does not hold for every header**. Comma-joining is safe only when the field definition allows list syntax and parsers respect commas inside quoted strings or structured syntax.

| Header | Meaning/type | Notes |
|---|---|---|
| `Accept` | List of media ranges | Can be parsed as multiple items, respecting `q` and order |
| `Accept-Language` | Weighted language list | Do not split blindly on commas if parser ignores quoted/quality syntax |
| `Cache-Control` | List of directives | Parse per field definition, not arbitrary string splitting |
| `Vary` | List of header names affecting caching | Important for content negotiation |
| `X-Request-Tag` | Application-defined field | Must **explicitly specify** repeated lines vs. CSV and quoting/escaping |
| `Authorization` | Credential; usually single effective value | Duplicates or conflicting values must be handled safely |
| `Content-Type` | Single media type | Never interpret multiple arbitrary `Content-Type`s |
| `Set-Cookie` | Multiple independent cookie directives | **Never join into a single comma-separated header** |
| `Cookie` (request) | Specialized cookie syntax, usually `;`-delimited | Do not apply generic list-field rules to cookies |

**Never equate** "two lines with the same name," "one line with two elements," and "one value containing a literal comma." All three can surface in an HTTP library as `List<String>` without having the same meaning.

### Why Commas Are Easily Misinterpreted

Application-defined example:

~~~http
X-Display-Name: Nguyen, An
~~~

Without an explicit contract, this could be **one full name** or **two list members**. When passing free-form data that may contain commas, prefer a JSON body, a field with standardized quoting/escaping rules, or a well-defined encoding scheme.

For multi-element values, do not assume `split(",")` is safe. Syntaxes like `Accept: application/json;q=0.9, text/plain;q=0.7` or quoted strings require parsers aligned with the RFC/field grammar.

## 3. Set-Cookie Is an Exception That Must Be Handled Separately

A response can contain:

~~~http
HTTP/1.1 200 OK
Set-Cookie: session=abc; Path=/; HttpOnly; Secure; SameSite=Lax
Set-Cookie: theme=dark; Path=/; Max-Age=3600
~~~

Two `Set-Cookie` lines represent **two distinct cookies**. Never merge them into:

~~~http
Set-Cookie: session=abc; Path=/; HttpOnly, theme=dark; Path=/
~~~

Commas also appear inside a cookie's `Expires` attribute (such as weekday names followed by a comma), making naive `,`-splitting especially broken.

Example of a Spring MVC downstream returning multiple cookies:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;

ResponseCookie session = ResponseCookie.from("session", "abc")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .build();

ResponseCookie theme = ResponseCookie.from("theme", "dark")
        .path("/")
        .maxAge(java.time.Duration.ofHours(1))
        .build();

return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, session.toString())
        .header(HttpHeaders.SET_COOKIE, theme.toString())
        .body("ok");
~~~

`ResponseEntity.HeadersBuilder.header(...)` supports appending multiple values; verify at the response layer that the actual wire output keeps each `Set-Cookie` header separate.

When a service acts as a proxy, **never join `Set-Cookie` headers with `String.join(",")`**. Nor should you forward every `Set-Cookie` indiscriminately: domain, path, `SameSite`, `Secure`, and trust scope may not fit the gateway's domain.

## 4. HttpHeaders in Spring: add Differs from set

`org.springframework.http.HttpHeaders` is a multi-valued map abstraction. It lets you work with multiple values per field, though it **does not itself enforce** whether a field is allowed to repeat under the RFC.

~~~java
import org.springframework.http.HttpHeaders;

HttpHeaders headers = new HttpHeaders();

// Append to the value list.
headers.add(HttpHeaders.ACCEPT, "application/json");
headers.add(HttpHeaders.ACCEPT, "application/problem+json");

// Overwrite existing values for this field.
headers.set("X-Correlation-Id", "2d907f2d-bf7e-447b-a35d-6db7bd0f1eae");

// Read only the first element.
String firstAccept = headers.getFirst(HttpHeaders.ACCEPT);

// Read values stored at the HttpHeaders layer.
java.util.List<String> rawValues = headers.get(HttpHeaders.ACCEPT);
~~~

Key points:

- `add(name, value)` appends a value to the field.
- `set(name, value)` replaces existing values with a single value.
- `getFirst(name)` returns the first element or `null`; it **does not imply the header only had one value**.
- `get(name)` returns field-line values at the abstraction layer; it **does not guarantee** an upstream server/proxy did not fold them in transit.
- For structured headers with dedicated helpers, prefer typed APIs such as `setAccept`, `getAccept`, `setContentType`, and `setBearerAuth` to reduce formatting mistakes.
- Header names are **case-insensitive** in HTTP. Never treat `X-Trace-Id` and `x-trace-id` as two independent fields.

Never use `getFirst("Authorization")` to **silently accept** a request carrying conflicting credentials. At authentication boundaries, check for duplicates per contract and account for proxy folding/rewriting, rejecting ambiguous requests rather than picking one credential at random.

### Use MultiValueMap When the Contract Needs Multiple Values

~~~java
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

MultiValueMap<String, String> filters = new LinkedMultiValueMap<>();
filters.add("tag", "red");
filters.add("tag", "blue");
~~~

`MultiValueMap` works well as an internal multi-value structure, while **its wire representation must be specified separately**: repeated query parameters, CSV, JSON arrays, and multiple HTTP header lines are different contracts.

## 5. Receiving Multi-Valued Headers in Spring MVC

Example where inventory receives a custom filter header:

~~~java
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogController {

    @GetMapping("/api/catalog")
    String catalog(
            @RequestHeader HttpHeaders headers) {

        List<String> rawTags = headers.get("X-Item-Tag");

        // Parsing and validation per the X-Item-Tag contract.
        return rawTags == null ? "no tags" : "tags received";
    }
}
~~~

If the contract defines `X-Item-Tag` as a **single field** with its own grammar, validate and parse it strictly according to that grammar. If you want multiple independent tags, consider query parameters `?tag=red&tag=blue` or a JSON body where appropriate; they generally offer clearer binding than an unstandardized multi-valued custom header.

For a single required header, validate count, length, character set, and normalized value, and guard against duplicate ambiguity behind proxies. Never assume a controller `String[]` parameter preserves the exact wire framing across every HTTP client and proxy.

## 6. Special Characters in HTTP Headers: CRLF and Unicode

An HTTP header name is an **HTTP token**, not an arbitrary Unicode string. Header values also restrict control characters. In particular, carriage return (`\r`) and line feed (`\n`) introduce **HTTP response/request splitting** risks if mishandled.

Example of *unsafe data*, shown purely for recognition:

~~~text
X-Display-Name = "Alice" + CR + LF + "X-Injected: yes"
~~~

Never concatenate user-supplied values directly into raw HTTP header strings. Modern HTTP libraries typically validate and reject newlines, yet applications must still validate inputs at boundaries and never assemble HTTP requests from raw strings.

Example validator for a UUID-based correlation ID:

~~~java
import java.util.UUID;

public final class CorrelationIds {

    private CorrelationIds() {
    }

    public static String normalize(String incoming) {
        if (incoming == null || incoming.length() != 36) {
            return UUID.randomUUID().toString();
        }

        try {
            return UUID.fromString(incoming).toString();
        } catch (IllegalArgumentException ex) {
            return UUID.randomUUID().toString();
        }
    }
}
~~~

This sample normalizes/mints IDs for **one specific header**, not as a generic validator for all headers. UUIDs are easily bounded and contain no newlines, commas, or spaces.

### Vietnamese Diacritics in Headers?

A value like `Tên khách: Nguyễn An` should not be placed directly into arbitrary headers by default. Header strings traverse HTTP/1.1 stacks, HTTP/2 stacks, proxies, and client libraries with differing byte/encoding rules. Safer, more portable options:

- Free-form text data: place in a UTF-8 JSON body.
- Values belonging to a URI: use a URI builder and UTF-8 percent-encoding.
- Standard headers supporting internationalization parameters, such as `Content-Disposition`: use standard APIs and matching encoding conventions like RFC 8187 for `filename*` when appropriate.
- Custom headers: design a safe ASCII format or explicitly specified encoding; never rely on "it happened to work" on one transport.

For example, `filename*=UTF-8''...` is a convention for **parameters of specific headers**, not advice to arbitrarily percent-encode every HTTP header value.

## 7. Proxy-Forwarded Headers: Identity and Trust Boundaries

Headers such as `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, and `X-Forwarded-Proto` affect how an application infers client addresses or public URLs.

~~~mermaid
flowchart LR
    C["Internet client"] --> P["Trusted gateway"]
    P --> O["order-service"]
    O --> L["LoadBalancer"]
    L --> I["inventory-service"]
~~~

Dangerous mistake: trusting an external client's `X-Forwarded-Host` directly to construct redirect URLs or downstream calls. If the gateway fails to strip or overwrite untrusted headers, the application is exposed to **host header injection, open redirects, or SSRF**.

In Spring, `ForwardedHeaderFilter` or Boot's forward-headers settings help the framework interpret proxy-supplied headers. However, the framework does not verify the header's trustworthiness on its own: configure your proxy/ingress to strip spoofed client headers before forwarding.

Never blindly relay `Authorization`, `Cookie`, `Host`, `Content-Length`, `Connection`, or all inbound headers to target services. Forward only an explicit allowlist of normalized context; tenant/role headers must derive from verified authentication, and downstream services must still enforce authorization.

### Bounding Header Size and Count

HTTP specifies no single universal field size limit; servers, proxies, and clients impose their own. Oversized headers can trigger `431 Request Header Fields Too Large` or another 4xx status. Oversized URIs can trigger `414 URI Too Long`.

Never stuff hundreds of item IDs, payloads, or large JSON blobs into custom headers. Use a request body or a schema-defined filter resource API. When diagnosing failures, check server/proxy logs before raising limits: oversized requests often signal uncontrolled input.


## 8. URIs Have Distinct Components, Not an Arbitrary String

General URI form:

~~~text
scheme://authority/path?query#fragment

http://inventory-service/api/items/SKU-001?tag=red&tag=blue
  |           |                |                |
 scheme   host/service ID     path            query
~~~

Characters `/`, `?`, `&`, `=`, `#`, and `%` carry **syntactic roles** depending on component:

- `/` separates **path segments**.
- `?` separates path from query.
- `&` and `=` commonly delimit query parameters by convention.
- `#` starts the fragment; fragments are **not** sent in HTTP request-targets to backends.
- `%` introduces a percent-encoded octet sequence.
- `+` can have special meaning under **form-style query decoding** (some stacks decode plus signs into spaces).
- `;` can denote matrix/path parameters under certain routing conventions.

Examples:

~~~text
Actual sku value:      SKU/A&B
Inserted raw into path: /api/items/SKU/A&B
                       -> slash creates an extra path segment

Actual q value:        red & blue
Concatenated raw:      ?q=red & blue
                       -> & is parsed as a query separator

Actual note value:     a#b
Concatenated raw:      ?note=a#b
                       -> #b is treated as a fragment and never reaches the server
~~~

**Never construct URIs via string concatenation** such as `baseUrl + "/items/" + sku + "?q=" + q` when variables may hold arbitrary characters. Use `UriBuilder`/`UriComponentsBuilder` and bind variables as data rather than URI syntax.

## 9. Percent-Encoding: Encoding UTF-8 Octets per Component

Percent-encoding represents an octet as `%HH` (two hex digits). For Unicode data in URIs, the standard approach encodes the string to UTF-8 and escapes the necessary octets.

| Data value | When strictly encoded as a variable | Scenario |
|---|---|---|
| Space | `%20` | `Nón xanh` containing a space |
| `+` character | `%2B` | Query searching for literal `C++` |
| `&` character | `%26` | Query value `red&blue` |
| `=` character | `%3D` | Query value `a=b` |
| `/` character | `%2F` | An item code containing a slash defined as one path segment |
| `?` character | `%3F` | Question mark as data, not starting a query |
| `#` character | `%23` | Hash mark as data |
| `%` character | `%25` | Literal percent sign |
| `;` character | `%3B` | Semicolon as data in a path variable |

These outputs illustrate **strictly encoded URI variables**, not a claim that every one of these characters must be escaped everywhere in a complete URI.

For example, `Nón xanh` UTF-8 encoded as a URI variable becomes:

~~~text
N%C3%B3n%20xanh
~~~

A Vietnamese diacritic character is not encoded into a single arbitrary `%xx`; the output reflects the UTF-8 byte sequence of that character.

### Plus and Space Are Not Equivalent

For the search input `C++`:

~~~text
Intended meaning: q = "C++"

If sent as ?q=C++
  -> a server/form decoder may read it as "C  "

If sent as ?q=C%2B%2B
  -> unambiguously represents literal plus signs
~~~

Therefore, pass `q` as a URI variable with strict encoding instead of raw concatenation. For spaces, `%20` fits URI components; `+` comes from `application/x-www-form-urlencoded` to represent spaces. The two encoding standards serve different purposes.

## 10. Spring URI Encoding: TEMPLATE_AND_VALUES vs. URI_COMPONENT

Spring Framework provides `DefaultUriBuilderFactory` and `UriComponentsBuilder` with these encoding modes:

| EncodingMode | Behavior | When to use |
|---|---|---|
| `TEMPLATE_AND_VALUES` | Encodes template and **strictly encodes URI variables** on expand | Suitable default for most user/external inputs |
| `VALUES_ONLY` | Strictly encodes only URI variables before expand | When the template is controlled and pre-ready |
| `URI_COMPONENT` | Expands first, then encodes per URI component; preserves component-valid reserved chars | When intentionally preserving meaningful reserved chars |
| `NONE` | No encoding | Only when inputs are already fully normalized and controlled |

Spring example:

~~~java
import java.net.URI;
import java.util.Map;
import org.springframework.web.util.UriComponentsBuilder;

String sku = "SKU/A&B";
String q = "C++";

URI uri = UriComponentsBuilder
        .fromUriString("http://inventory-service")
        .pathSegment("api", "items", "{sku}")
        .queryParam("q", "{q}")
        .encode()
        .buildAndExpand(Map.of("sku", sku, "q", q))
        .toUri();

System.out.println(uri);
~~~

Expected URI output:

~~~text
http://inventory-service/api/items/SKU%2FA%26B?q=C%2B%2B
~~~

Explanation:

- `pathSegment("api", "items", "{sku}")` expresses discrete **segments** instead of manual `/` concatenation.
- `{sku}` and `{q}` are placeholders; their values expand as data.
- `encode()` on `UriComponentsBuilder` is called **before** `buildAndExpand(...)` to apply strict encoding to variables.
- `toUri()` produces an already-encoded `java.net.URI`. When passing this `URI` to an HTTP client, **do not encode it a second time**.

### Why Not Always Use URI_COMPONENT?

Within a path component, `;` is syntactically valid yet carries matrix-parameter meaning. `URI_COMPONENT` mode can leave `;` unescaped inside a URI variable, whereas `TEMPLATE_AND_VALUES` treats variables as opaque data and escapes reserved chars like `;`. The latter is usually safer when callers accept user input or arbitrary item codes.

Similarly, `+` in a query may be valid per RFC 3986 yet decoded as a space by servers applying form decoding. Strict variable encoding avoids surprises.

## 11. RestClient: Using a URI Builder Before LoadBalancer Picks an Instance

Example caller configuring a load-balanced `RestClient` with explicit encoding:

~~~java
package com.example.order.http;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

@Configuration(proxyBeanMethods = false)
public class InventoryRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {

        DefaultUriBuilderFactory uriFactory =
                new DefaultUriBuilderFactory(
                        "http://inventory-service"
                );
        uriFactory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES
        );

        return builder.clone()
                .uriBuilderFactory(uriFactory)
                .build();
    }
}
~~~

Calling via URI template with variables:

~~~java
import java.util.Map;
import org.springframework.http.HttpHeaders;

String sku = "SKU/A&B";
String query = "C++";

ItemResponse item = inventoryRestClient.get()
        .uri(uriBuilder -> uriBuilder
                .pathSegment("api", "items", "{sku}")
                .queryParam("q", "{q}")
                .build(Map.of("sku", sku, "q", query)))
        .headers(headers -> {
            headers.set("X-Correlation-Id", correlationId);
            headers.setAccept(java.util.List.of(
                    org.springframework.http.MediaType.APPLICATION_JSON));
        })
        .retrieve()
        .body(ItemResponse.class);
~~~

`ItemResponse` and `correlationId` are application DTO/values. `DefaultUriBuilderFactory` applies strict encoding to URI variables; HTTP headers still follow their own schema and **do not pass through the URI encoder**.

If you already hold a properly built and encoded `java.net.URI`, pass `.uri(uri)`. With `URI`-accepting overloads, Spring uses the given `URI` **without re-encoding**, so `%2F` is not turned into `%252F`.

### Multi-Valued Headers with RestClient

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

inventoryRestClient.get()
        .uri("/api/catalog")
        .headers(headers -> {
            headers.setAccept(java.util.List.of(
                    MediaType.APPLICATION_JSON,
                    MediaType.valueOf("application/problem+json")
            ));

            headers.set("X-Correlation-Id", correlationId);

            // Illustrated only when the X-Item-Tag contract allows repetition.
            headers.add("X-Item-Tag", "red");
            headers.add("X-Item-Tag", "blue");
        })
        .retrieve()
        .body(String.class);
~~~

Prefer structured `setAccept(...)`, use `set(...)` for single-valued logical fields, and use `add(...)` only when the contract permits multiple values. Clients and proxies may fold/unfold list-based headers between single and multiple lines; **verify the parsed values at the backend rather than comparing raw HTTP text**.

## 12. WebClient: URIs and Headers in a Reactive Chain

`WebClient` uses the same `UriBuilderFactory`, while execution occurs only upon subscription. Configure a load-balanced builder with explicit encoding:

~~~java
package com.example.order.http;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

@Configuration(proxyBeanMethods = false)
public class InventoryWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient inventoryWebClient(
            @LoadBalanced WebClient.Builder builder) {

        DefaultUriBuilderFactory uriFactory =
                new DefaultUriBuilderFactory(
                        "http://inventory-service"
                );
        uriFactory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES
        );

        return builder.clone()
                .uriBuilderFactory(uriFactory)
                .build();
    }
}
~~~

Invoking the API:

~~~java
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import reactor.core.publisher.Mono;

Mono<ItemResponse> result = inventoryWebClient.get()
        .uri(builder -> builder
                .pathSegment("api", "items", "{sku}")
                .queryParam("q", "{q}")
                .build(Map.of("sku", "SKU/A&B", "q", "C++")))
        .headers(headers -> {
            headers.set("X-Correlation-Id", correlationId);
            headers.setAccept(java.util.List.of(
                    MediaType.APPLICATION_JSON
            ));
        })
        .retrieve()
        .bodyToMono(ItemResponse.class);
~~~

`result` is a `Mono<ItemResponse>`; no HTTP request is sent without a subscriber. In Spring Cloud, `@LoadBalanced WebClient.Builder` integrates `ReactorLoadBalancerExchangeFilterFunction`; the LoadBalancer filter resolves the **logical hostname** after the URI is built.

### Observing Multi-Valued Response Headers

Sometimes callers need to inspect `Set-Cookie` to verify downstream behavior in a lab:

~~~java
Mono<java.util.List<String>> cookieHeaders =
        inventoryWebClient.get()
                .uri("/demo/cookies")
                .exchangeToMono(response -> {
                    java.util.List<String> values =
                            response.headers()
                                    .header(HttpHeaders.SET_COOKIE);
                    return response.releaseBody()
                            .thenReturn(java.util.List.copyOf(values));
                });
~~~

`response.headers().header(...)` returns the values exposed by the HTTP client; never use `String.join(",")` or `split(",")` on `Set-Cookie`. In production APIs, internal services rarely need to forward `Set-Cookie` externally; let the gateway manage session/cookie contracts at a consistent trust boundary.

When using `exchangeToMono`, consume or release the response body properly to prevent resource leaks; `releaseBody()` above handles the case where the body is not needed.


## 13. OpenFeign: @RequestParam, @PathVariable, and CollectionFormat

OpenFeign is a declarative interface-based HTTP client. With Spring Cloud OpenFeign and `@FeignClient(name = "inventory-service")`, the hostname/service ID resolves via LoadBalancer when no static URL is set.

Example:

~~~java
package com.example.order.inventory;

import java.util.List;
import org.springframework.cloud.openfeign.CollectionFormat;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;

@FeignClient(name = "inventory-service")
public interface InventoryFeignClient {

    @CollectionFormat(feign.CollectionFormat.EXPLODED)
    @GetMapping("/api/items/{sku}")
    ItemResponse search(
            @PathVariable("sku") String sku,
            @RequestParam("q") String query,
            @RequestParam("tag") List<String> tags
    );
}
~~~

Spring Cloud OpenFeign supports `@CollectionFormat` taking a `feign.CollectionFormat` value. Per documentation, `EXPLODED` is the default in many scenarios, whereas `CSV` formats multiple elements into a single comma-separated string.

With a repeated-key query contract, the intended request is:

~~~http
GET /api/items/SKU-001?q=C%2B%2B&tag=red&tag=blue HTTP/1.1
Host: inventory-service
~~~

Switching to `CSV` sends `tag=red,blue` instead of two occurrences `tag=red&tag=blue`. The two are **not equivalent** when an actual value contains a comma or server binding differs.

| Input | Desired contract | Verification |
|---|---|---|
| `tags = ["red","blue"]` | `tag=red&tag=blue` | Use `EXPLODED` and inspect the real wire URL |
| `tags = ["red,blue"]` | Single element containing a comma | Must not split into two tags |
| `query = "C++"` | Literal plus signs | Verify backend receives `C++` |
| `sku = "SKU/A"` | Item ID containing a slash | Test Feign + server encoding/routing; never assume |
| `tags = []` | No tags | Define absent field vs. empty value in contract |

**Version note:** `@PathVariable` encoding can vary across Spring Cloud OpenFeign, Feign core, HTTP clients, and slash encode/decode settings. Never assume `/` in an arbitrary path variable always becomes an accepted `%2F` on the server. If IDs need slashes or many reserved characters, consider moving them to query parameters, the request body, or safe opaque identifiers.

### Feign @SpringQueryMap

For multi-field filters, Spring Cloud OpenFeign supports `@SpringQueryMap`:

~~~java
import org.springframework.cloud.openfeign.SpringQueryMap;

public record SearchFilter(String q, Integer page) {}

@GetMapping("/api/search")
SearchResult search(@SpringQueryMap SearchFilter filter);
~~~

This snippet illustrates a method inside a Feign client interface; `SearchResult` is application-defined. When custom query-map encoding or multiple values per key are needed, configure a tested `QueryMapEncoder`; never rely on `Map<String, String>` to represent multiple values for the same key name.

### Headers in OpenFeign Also Need an Explicit Contract

~~~java
@GetMapping("/api/items/{sku}")
ItemResponse getItem(
        @PathVariable("sku") String sku,
        @org.springframework.web.bind.annotation.RequestHeader(
                "X-Correlation-Id") String correlationId
);
~~~

A correlation ID should carry one validated value. Multi-valued business fields belong in an explicit API contract; never assume a `List<String>` `@RequestHeader` parameter preserves its exact **physical line count** through proxies and load balancing.

`feign.RequestInterceptor` can inject headers into `RequestTemplate`, but restrict it to client-specific headers rather than copying all inbound headers or percent-encoding header values. Also note that Feign logging `FULL` can print `Authorization`, cookies, and sensitive queries; enable it only in controlled environments with redaction.

## 14. One Multi-Valued Query Key Is Not a CSV String

A multi-tag filter endpoint can choose one of these contracts:

| Style | Example | Characteristics |
|---|---|---|
| **Exploded / repeated key** | `?tag=red&tag=blue` | Each item is its own occurrence |
| **CSV** | `?tag=red,blue` | Must specify escaping/quoting if items contain commas |
| **Indexed** | `?tag[0]=red&tag[1]=blue` | Depends on framework/server key-name binding |
| **JSON body** | `{"tags":["red","blue"]}` | Fits complex or lengthy filters |

Pick one style and lock it into the API contract/OpenAPI spec. Specifically:

- `?tag`, `?tag=`, and **omitting `tag`** can have distinct meanings.
- Repeated parameters may arrive in order at the server, yet if business logic treats tags as a set, never depend on order for authorization or cache keys.
- If a value contains commas, equals signs, or plus signs, callers must encode the **value**, not alter the contract's delimiter.
- Before upgrading Spring/Feign or swapping HTTP clients, test the raw query against a real server/`MockWebServer` rather than asserting only a Java `List`.
- With many items, query strings can exceed server/proxy URI limits; move to a body/filter resource.

## 15. Double Encoding and Double Decoding

A classic mistake is **double encoding**:

~~~text
Original data:        SKU/A
Encoded once:         SKU%2FA
Encoded % again:      SKU%252FA

Server decodes once:
    SKU%252FA -> SKU%2FA
    => not SKU/A
~~~

Conversely, if a server or proxy **double decodes**, a data value `%2F` can turn into a literal slash, causing misrouting or validation bypasses when decoding layers disagree.

Rules to follow:

1. Identify **unencoded raw data** at the application boundary.
2. Choose the right component (path segment vs. query value).
3. Encode once when building the URI via a builder.
4. Never pass an already-encoded `%2F` as a variable meant to represent a slash if the builder will encode it again.
5. Never take an already-encoded `URI` and run a raw-data encoder over it again.
6. On the server, validate the **contract-decoded value**; never apply arbitrary extra decode passes.
7. Test through proxies, since reverse proxies and servlet containers enforce their own policies on encoded slashes.

### Slashes Inside Path IDs Are a High-Risk Contract

Even when a caller emits valid `/api/items/SKU%2FA`, a proxy may block encoded slashes or a routing layer may decode it into two path segments. If user-controlled IDs can contain `/`, `..`, `%2e%2e`, semicolons, or Unicode equivalents, consider:

- Using path-safe IDs such as UUIDs, ULIDs, or opaque keys from a restricted alphabet.
- Moving complex values into query parameters or JSON bodies per API design.
- Rejecting invalid input at the boundary after normalization rather than trying to "sneak past" routing via extra encoding.
- Checking path-traversal and dot-segment normalization across gateways and downstreams.
- Never turning user-supplied absolute URLs into outbound HTTP targets, to prevent SSRF.

## 16. Unicode Normalization and Data Comparison Contracts

Two Vietnamese strings can look visually identical while having different code-point representations: precomposed accented character vs. base letter + combining mark. When UTF-8 percent-encoded, **the wire bytes differ** despite nearly identical appearance.

When using such values as cache keys, signatures, or IDs requiring exact comparison, both sides must agree on a Unicode normalization policy—typically NFC where appropriate.

Java example:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(
        userInput,
        Normalizer.Form.NFC
);

// Only after normalizing and validating, pass it as a URI variable.
~~~

Never normalize arbitrarily **after signing** a request or alter signed strings before signature verification. For signed URLs or request signing, agree on canonical path/query representation, percent-encoding, parameter order, and Unicode normalization. If gateway and backend canonicalize differently, valid requests fail or security gaps open.

A system must not blindly treat different encodings as two distinct products just because raw URIs differ; conversely, if an ID is defined byte-for-byte, never normalize in a way that alters identity. **The business contract decides**; the HTTP encoder merely executes it.

## 17. URI Encoding Never Changes LoadBalancer's Service ID

When using `@LoadBalanced RestClient.Builder`, `@LoadBalanced WebClient.Builder`, or `@FeignClient(name="inventory-service")`, Spring Cloud LoadBalancer looks up `ServiceInstance` candidates by the **logical service name**.

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant C as HTTP Client
    participant L as Spring Cloud LoadBalancer
    participant S as Inventory replica

    O->>C: sku = "SKU/A&B", query = "C++"
    Note over C: Encode path/query variables
    C->>L: URI host = inventory-service
    L-->>C: ServiceInstance localhost:8082
    C->>S: GET /api/items/SKU%2FA%26B?q=C%2B%2B
    S-->>C: HTTP response
~~~

**Never encode the service ID as a path variable**, and never put an SKU into the host authority. LoadBalancer rewrites the authority to the chosen instance's host/port via Spring Cloud; **path and query must keep their data meaning intact** through that step.

Common bugs:

- URI becomes `http://inventory-service%2Fapi/...`: invalid host because the slash was encoded into the authority.
- Client sends an absolute URL `https://external.example/api` instead of a service-ID URL: can **bypass LoadBalancer** or hit unintended destinations.
- Feign has a fixed `url=...`: Spring Cloud OpenFeign calls that URL directly, skipping discovery even when `name` is set.
- LoadBalancer picks the right instance yet the path is double-encoded: backend still returns 404/400—not a Round Robin/Random algorithm bug.

If a gateway or reverse proxy sits between caller and backend, verify the contract **at every hop**, since proxies can normalize paths, decode, rewrite routes, or alter headers before reaching inventory.

## 18. HTTP Errors: Read the Right Signal Before Retrying

Header and URI bugs surface under various statuses:

| Status / error | Likely cause | What to do |
|---|---|---|
| `400 Bad Request` | Bad URI percent-encoding, invalid header value, query binding failure | Check raw request-target, schema, and parser logs |
| `401 Unauthorized` | Missing/invalid credentials, ambiguous duplicate `Authorization` | Check token source; never log tokens |
| `403 Forbidden` | Valid credentials, insufficient permissions or policy block | Check scope/audience/authorization |
| `404 Not Found` | Path segment split/decoded differently, missing route, or missing data | Compare raw URI against route and contract |
| `414 URI Too Long` | Query too long or malformed URL assembly | Move large filters to body or shorten URI |
| `431 Request Header Fields Too Large` | Too many or oversized headers | Check allowlist and proxy/server size limits |
| `502 Bad Gateway` | Gateway/proxy received invalid upstream response | Inspect gateway logs and actual request/response |
| `503 Service Unavailable` | No `ServiceInstance`, overloaded/down backend or proxy | Check discovery, LoadBalancer, and status origin |
| `504 Gateway Timeout` | Proxy waited too long for upstream | Check per-hop timeouts |
| HTTP client encode exception | Input contains illegal characters; URI builder failed | Validate input *before sending* and check redacted stack trace |

**Never unconditionally retry** 400/414/431 errors. When a caller keeps sending a bad URL or header, retrying other instances only wastes load without fixing the contract. Retries on 503 or timeouts also require bounds, idempotency, and time budgets; not every 503 indicates an unhealthy replica.

When OpenFeign throws `FeignException`, RestClient throws `RestClientResponseException`, or WebClient emits `WebClientResponseException`, the adapter layer must normalize errors into a uniform model **without erasing original status/cause** needed for diagnosis.

## 19. Designing Structured Error Responses

An HTTP contract error should return an accurate status code and actionable details rather than 200 with a generic message. Spring Framework supports `ProblemDetail` representing Problem Details (RFC 9457).

Example endpoint rejecting an invalid filter value:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.server.ResponseStatusException;

// Inside a service method / controller validation:
if (query != null && query.length() > 200) {
    ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.BAD_REQUEST
    );
    problem.setTitle("Invalid search query");
    problem.setDetail("Query parameter q is too long");
    problem.setProperty("errorCode", "INVALID_QUERY");
    throw new org.springframework.web.ErrorResponseException(
            HttpStatus.BAD_REQUEST,
            problem,
            null
    );
}
~~~

This snippet illustrates `ErrorResponseException` in Spring Framework; serialization depends on the app's exception-handling config. Alternatively, use `@RestControllerAdvice` returning `ResponseEntity<ProblemDetail>`.

**Never expose raw URIs, `Authorization`, queries containing PII, or full header values in error details.** Use stable error codes, normalized correlation IDs, and safe client messages. Separate input validation errors from dependency failures so circuit breakers and metrics do not confuse 400s with infrastructure outages.


## 20. Hands-On Lab: Verifying Wire Behavior Across Two Replicas

Build a local environment:

~~~text
order-service :8080
    |
    | RestClient / WebClient / OpenFeign
    | Logical URI: http://inventory-service/debug/echo
    v
Spring Cloud LoadBalancer
    +--- inventory :8081
    +--- inventory :8082
~~~

### 20.1. Declaring Instances in order-service

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

The caller needs `spring-cloud-starter-loadbalancer` and a LoadBalancer-integrated builder or Feign client. Run two inventory processes on ports 8081 and 8082, each exposing an echo endpoint to inspect **decoded** queries and headers.

### 20.2. Echo Endpoint in inventory-service

~~~java
package com.example.inventory;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    private final Environment environment;

    public EchoController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/debug/echo")
    public EchoResult echo(
            HttpServletRequest request,
            @RequestParam("q") String query,
            @RequestParam(name = "tag", required = false)
                    List<String> tags,
            @RequestHeader(name = "X-Correlation-Id", required = false)
                    String correlationId) {

        return new EchoResult(
                environment.getProperty("server.port", "unknown"),
                request.getQueryString(),
                query,
                tags == null ? List.of() : tags,
                correlationId
        );
    }

    public record EchoResult(
            String instancePort,
            String rawQuery,
            String query,
            List<String> tags,
            String correlationId
    ) {}
}
~~~

This echo endpoint is for a **local lab**—never expose request metadata publicly in production. It intentionally omits `Authorization`, `Cookie`, and any secrets.

### 20.3. Proxy Controller in order-service

Use the `inventoryRestClient` bean configured with `@LoadBalanced RestClient.Builder` and `DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES`.

~~~java
package com.example.order.web;

import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class EchoProxyController {

    private final RestClient inventory;

    public EchoProxyController(
            @Qualifier("inventoryRestClient") RestClient inventory) {
        this.inventory = inventory;
    }

    @GetMapping("/proxy/echo")
    public EchoResult echo(
            @RequestParam("q") String query,
            @RequestParam("tag") List<String> tags) {

        if (tags.size() != 2) {
            throw new IllegalArgumentException(
                    "Lab requires exactly two tag values"
            );
        }

        return inventory.get()
                .uri(b -> b.path("/debug/echo")
                        .queryParam("q", "{q}")
                        .queryParam("tag", "{tag1}")
                        .queryParam("tag", "{tag2}")
                        .build(Map.of(
                                "q", query,
                                "tag1", tags.get(0),
                                "tag2", tags.get(1)
                        )))
                .headers(h -> h.set(
                        "X-Correlation-Id",
                        "e41c139f-8057-4e88-84bc-af4fc1c414a2"
                ))
                .retrieve()
                .body(EchoResult.class);
    }

    public record EchoResult(
            String instancePort,
            String rawQuery,
            String query,
            List<String> tags,
            String correlationId
    ) {}
}
~~~

The hardcoded correlation ID is for the lab only; in production, mint or normalize IDs at ingress and propagate them via safe context. Exception handling is omitted above to focus on URI encoding.

Invoke multiple times from PowerShell:

~~~powershell
1..8 | ForEach-Object {
    Invoke-RestMethod -Uri "http://localhost:8080/proxy/echo?q=C%2B%2B&tag=red&tag=blue"
}
~~~

Verify:

- `query` seen by the backend is `C++`, **not** `C  `.
- `tags` contains two values: `red` and `blue`.
- `rawQuery` typically contains `q=C%2B%2B&tag=red&tag=blue`; specifics may be normalized by proxies.
- `instancePort` shows requests reaching `8081` or `8082` via LoadBalancer.
- `correlationId` matches the attached UUID regardless of query.
- Replica ordering depends on algorithm, concurrency, and retries—it is not itself proof of encoding behavior.

Next, test `Nón xanh`, `red&blue`, and literal `100%`. Use the URI builder for each value and compare the **original value** against the backend's decoded value, not just raw query text.

### 20.4. Testing a Response with Two Set-Cookie Headers

Create a test endpoint returning two `Set-Cookie` headers via two calls to `ResponseEntity.header(HttpHeaders.SET_COOKIE, ...)`. Use an HTTP test client to read each cookie individually; never use `String.split(",")` because `Expires` attributes can contain commas. Behind a reverse proxy, verify cookie attributes, domain/path, and whether forwarding cookies externally is permitted.

## 21. Unit and Integration Tests for URI/Header Contracts

URI encoding can be unit-tested independently without starting service discovery:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.web.util.UriComponentsBuilder;

class UriAndHeaderContractTest {

    @Test
    void encodesVariablesStrictly() {
        URI uri = UriComponentsBuilder
                .fromUriString("http://inventory-service")
                .pathSegment("api", "items", "{sku}")
                .queryParam("q", "{q}")
                .encode()
                .buildAndExpand(Map.of(
                        "sku", "SKU/A&B",
                        "q", "C++"
                ))
                .toUri();

        assertEquals(
                "/api/items/SKU%2FA%26B",
                uri.getRawPath()
        );
        assertEquals("q=C%2B%2B", uri.getRawQuery());
        assertEquals("inventory-service", uri.getHost());
    }

    @Test
    void keepsSetCookieValuesSeparateInMemory() {
        HttpHeaders headers = new HttpHeaders();
        headers.add(HttpHeaders.SET_COOKIE, "session=abc; Path=/");
        headers.add(HttpHeaders.SET_COOKIE, "theme=dark; Path=/");

        assertEquals(
                2,
                headers.get(HttpHeaders.SET_COOKIE).size()
        );
        assertTrue(
                headers.get(HttpHeaders.SET_COOKIE)
                        .get(1)
                        .startsWith("theme=")
        );
    }
}
~~~

The URI test checks only the builder; the `HttpHeaders` test checks only Java in-memory storage. Neither **proves** proxies, connectors, servlet containers, and backends handle wire formats identically. Write integration tests with `MockWebServer`, WireMock, or two real servers, comparing actual raw queries, decoded values, and HTTP header lines.

| Test scenario | Input | Expected |
|---|---|---|
| Unicode/space | `Nón xanh` | UTF-8 percent-encoding, consistent decode |
| Literal plus | `C++` | Does not turn into two spaces |
| Reserved in path | `SKU/A&B` | URI builder encodes; proxy has explicit encoded-slash policy |
| Raw percent | `100%` | `100%25`, no double encoding |
| Hash in query | `a#b` | `#` stays data, not fragment |
| Repeated query | `["red","blue"]` | Two occurrences or chosen contract |
| Comma in one value | `"red,blue"` | Not split into two elements |
| Empty vs. absent | `tag=` vs. no `tag` | Distinguished per API contract |
| Two `Set-Cookie`s | Two cookies | Never joined into one comma-separated string |
| Duplicate `Authorization` | Two credentials | Rejected or handled per security policy |
| CR/LF in header | Contains control chars | Rejected or safely normalized |
| Encoded slash | `%2F` | Clear proxy/server behavior |
| Oversized URI/header | Exceeds limit | Appropriate error, no retry loop |
| Two `ServiceInstance`s | 8081/8082 | Identical encoding contract across both backends |
| Feign format | `EXPLODED` vs. `CSV` | Raw query matches each style's definition |


## 22. Common Troubleshooting Table

| Symptom | Common cause | Resolution |
|---|---|---|
| `C++` becomes `C  ` | Literal plus in query was not percent-encoded | Use strict URI variable encoding (`C%2B%2B`) |
| Search `red&blue` splits into two query params | Query string concatenated with `&` | Use `queryParam("q", "{q}")` and expand |
| SKU `SKU/A` returns 404 | Slash treated as path separator or encoded slash blocked by proxy | Change API contract/ID or set controlled routing rules |
| Backend receives `SKU%2FA` instead of `SKU/A` | Double encoding `%252F` | Encode URI variables exactly once |
| `tag=red,blue` treated as one tag | Caller used CSV while server expects repeated keys | Use `EXPLODED` and verify on the wire |
| Client loses a cookie | Joined `Set-Cookie` with commas | Keep both `Set-Cookie` values separate |
| Repeated correlation header | Used `add` on a single-value field | Use `set` and normalize the ID |
| 400 occurs before backend | Control chars or URI parser/proxy rejected request | Check client/gateway logs and validate input |
| Persistent 431 | Oversized headers or too many custom fields | Move to body/filter resource; check limits |
| 414 when sending ID list | Query exceeds URI limit | Design POST search/body if contract permits |
| 401 despite bearer token attached | Duplicate `Authorization`, wrong scope/audience, or proxy rewrite | Inspect boundary; never print tokens in logs |
| Wrong host after encoding | Encoded the authority instead of URI variables | Separate scheme/host/path/query via URI builder |
| `UnknownHostException` for `inventory-service` | Load-balanced HTTP client not configured | Check `@LoadBalanced`, Feign, and discovery |
| One replica returns 400, another returns 200 | Skewed schema/parser versions | Run consumer-driven contract tests; deploy compatibly |
| Cache keys differ for visually identical SKU | Different Unicode normalization/URI canonicalization | Align normalization and key generation |
| Retries still return 400 | Contract violation is not transient | Fail fast, fix caller, do not retry |

### On-the-Wire Isolation Workflow

When errors strike, follow one correlation ID and verify each hop:

1. **Caller input:** does raw data before URI encoding satisfy the contract?
2. **HTTP client:** are the encoded URL, header values, and HTTP method right? Never log secrets or full URIs containing PII.
3. **LoadBalancer:** does the logical host match the service ID and was a `ServiceInstance` selected?
4. **Proxy/gateway:** were the request-target or header fields rewritten, decoded, folded, or blocked?
5. **Backend:** do routing, query binding, HTTP decoding, and validation interpret values properly?
6. **Error mapping:** are original 400/404/414/431/503 statuses preserved instead of turning into 200 or a generic "timeout"?

Do not rely on comparing header casing or the order of unrelated headers. Compare the **semantics** of each field/query/path, plus ordering only in field lists where the spec requires order preservation.

## 23. Pre-Production Contract Checklist

- [ ] Explicitly define each header as singleton, list field, or special case like `Set-Cookie`.
- [ ] Use `HttpHeaders.set` for single-valued headers and `add` only when field/contract allows multiple values.
- [ ] Never use `getFirst` to silently accept duplicate credentials.
- [ ] Prefer typed APIs for `Accept`, `Content-Type`, and `Authorization`.
- [ ] Never parse `Set-Cookie` with `split(",")`; verify domain/path/`SameSite`/`Secure`.
- [ ] Block/normalize CRLF, control characters, and oversized header values.
- [ ] Never send arbitrary Unicode in custom headers without an encoding contract.
- [ ] Never relay `Host`, `Cookie`, `Authorization`, and all inbound headers blindly downstream.
- [ ] Trust forwarded headers only from trusted proxies after stripping client-spoofed headers.
- [ ] Use URI builders, separating path segments from query values.
- [ ] Encode URI variables with appropriate strict encoding exactly once.
- [ ] Distinguish URI percent-encoding from `application/x-www-form-urlencoded`.
- [ ] Never assume encoded slashes are accepted by every gateway/backend.
- [ ] Standardize repeated query keys, CSV, or JSON arrays in OpenAPI/API contracts.
- [ ] With OpenFeign, test `@CollectionFormat` and `@PathVariable` with real HTTP requests.
- [ ] Never use unvalidated dynamic URLs for downstream calls, avoiding SSRF and LoadBalancer bypasses.
- [ ] Never retry 400, 414, or 431 errors as transient failures.
- [ ] Return structured errors with accurate statuses and messages free of tokens or sensitive queries.
- [ ] Align Unicode normalization when comparing IDs, cache keys, or signatures.
- [ ] Maintain unit tests for encoding and integration tests across gateway, LoadBalancer, and at least two replicas.
- [ ] Re-verify contracts when upgrading Spring Framework, OpenFeign, or changing HTTP connectors/proxies.

## References

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.3): HTTP field semantics, conditions for combining field lines, and the `Set-Cookie` exception.
- [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): reserved characters, URI components, and percent-encoding.
- [RFC 8187 — HTTP Header Field Parameters](https://www.rfc-editor.org/rfc/rfc8187): character encoding and language in certain HTTP header parameters.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): structured HTTP error model.
- [Spring Framework — URI Links](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html): `UriComponentsBuilder`, `DefaultUriBuilderFactory`, and encoding modes.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, URI templates, and HTTP headers.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): building URIs, handling responses, and reactive HTTP client usage.
- [Spring Cloud OpenFeign — Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): `@CollectionFormat`, `@SpringQueryMap`, Feign clients, and LoadBalancer.
- [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): discovery, `ServiceInstance`, selection, health checks, and retries.

**Conclusion:** picking the right service ID and `ServiceInstance` only answers **where to send the request**. A reliable HTTP contract must also specify **how many values a header can hold, which characters are syntax vs. data, how URIs are encoded per component, and how errors are handled**. When RestClient, WebClient, OpenFeign, proxies, and backends share a tested contract, systems suffer fewer 400/404/431 errors, avoid leaking sensitive headers, eliminate pointless retries, and diagnose incidents far more easily.

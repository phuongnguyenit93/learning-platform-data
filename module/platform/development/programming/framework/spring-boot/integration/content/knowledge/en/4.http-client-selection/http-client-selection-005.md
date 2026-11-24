# Configuring Base URL, URI, Query Parameters, and Headers

In **SPRING_BOOT_INTEGRATION**, an HTTP adapter often calls multiple endpoints of the same partner—such as fetching a catalog, checking an order, or submitting a payment request. Even after selecting the right `RestClient`, `WebClient`, or HTTP interface, an application can still call the **wrong host**, build broken URIs when an order ID contains `/`, drop repeated query parameters, or leak partner A's Bearer token to partner B. These bugs hurt both reliability and security.

This lesson belongs to the **HTTP Client Selection** chapter and focuses on **configuring the base URL, URIs, query parameters, and HTTP headers**. We will construct URLs with URI builders rather than string concatenation, manage per-environment configuration, understand encoding/escaping, separate shared headers from per-request headers, and verify actual requests across Spring Boot HTTP layers. The topic connects directly to DTO/JSON contracts, deadlines, idempotency, testing, observability, and HTTP adapters within integration flows involving databases, caches, brokers, or Spring Integration.

> Examples target **Java 17+, Spring Boot 3.x, Spring Framework 6.x**. `RestClient` was added in Spring Framework 6.1 (commonly aligned with Spring Boot 3.2+); on Boot 3.0/3.1 without this API, use `RestTemplate` or `WebClient` per your version. We do not assume every server interprets URIs, query values, or headers under the exact same contract.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **URI, URL, origin, base URL, path, path segment, query string, fragment**, and hostname.
2. Configure an HTTP adapter's `baseUrl` from `application.yml` or `@ConfigurationProperties` without hardcoding endpoints in application services.
3. Use `UriBuilder`, `pathSegment`, and **URI template variables** to safely construct paths for IDs containing spaces, slashes, Unicode, and special characters.
4. Build optional, repeated, paginated, temporal, and filtered query parameters per contract rather than concatenating `?`/`&` manually.
5. Understand **percent-encoding**, `+` versus `%20`, and how to avoid under-encoding or double-encoding.
6. Distinguish `Accept`, `Content-Type`, `Authorization`, `If-Match`, `Idempotency-Key`, correlation/trace headers, and the ordering of default vs. per-request headers.
7. Use `RestClient`, `WebClient`, and declarative HTTP interfaces intentionally with validation, target allowlists, and input bounds.
8. Test methods/paths/queries/headers on real HTTP requests and observe normalized endpoints without leaking tokens or sensitive data.

## 2. What are the components of an HTTP URI?

Example request to a catalog service:

```text
https://catalog.example.org:8443/api/v1/products/PRD-107?lang=vi&tag=java&tag=spring#details
└─┬──┘ └─────────┬────────┘└┬─┘└───────────┬───────────┘└─────────────┬────────────┘└──┬──┘
 scheme       host         port          path                  query            fragment
```

| Component | Example | Role |
| --- | --- | --- |
| Scheme | `https` | URL-level protocol and connection security requirement. |
| Authority/host/port | `catalog.example.org:8443` | Network destination; may traverse DNS, proxies, TLS, and load balancers. |
| Origin | `https://catalog.example.org:8443` | Scheme + host + port; useful when configuring per-partner clients. |
| Base URL | `https://catalog.example.org:8443` or `https://catalog.example.org:8443/api` | Shared anchor for resolving relative URIs; path joining rules must stay consistent. |
| Path | `/api/v1/products/PRD-107` | Resource path. |
| Path segment | `api`, `v1`, `products`, `PRD-107` | Units separated by `/`; a dynamic ID should be treated as **one segment** if the contract specifies so. |
| Query | `lang=vi&tag=java&tag=spring` | Parameters; may carry multiple values with the same name and order sensitivity if required by server. |
| Fragment | `#details` | Used by the user agent to identify a sub-resource; **never sent in the HTTP request-target to the server**. |

**A URI is not just a path:** a URI can be absolute (`https://...`) or relative (`/api/v1/...`). `baseUrl` gives callers a common anchor; do not confuse `baseUrl` with the `Host` header. The HTTP engine chooses the destination from the URI and connection config; overriding `Host` arbitrarily does not guarantee routing to a different host and can conflict with TLS/SNI, proxies, or HTTP/2 authority.

### 2.1. Do not hardcode URLs in every application service

This is an anti-pattern:

```java
// Easy to get the wrong host across environments, hard to update consistently.
String url = "https://catalog.example.org/api/products/" + productId;
```

With 20 endpoints, hardcoding host/path across many files makes switching from sandbox to production error-prone. Separate:

- **Configuration:** per-partner origin/base URL, TLS, proxy, timeouts, credentials.
- **Adapter:** API paths, URI templates, query parameters, and headers matching the contract.
- **Application service:** business operations like `findProduct` or `submitOrder`, without assembling URLs manually.

This separates **connection routing** from **business semantics**. HTTP clients also involve connection pools, retries, and transaction interactions, yet those topics do not replace the responsibility of building valid URLs.

## 3. Configuring base URL with Spring Boot

Spring Boot has no universal `spring.http.partner.base-url` property automatically understood per partner. Define an application namespace using `@ConfigurationProperties`.

```yaml
app:
  partners:
    catalog:
      base-url: ${CATALOG_BASE_URL:https://catalog.example.org}
      audience: products-v1
    billing:
      base-url: ${BILLING_BASE_URL:https://billing.example.org}
      audience: payments-v1
```

`audience` here is purely illustrative application metadata; it is not automatically sent as a header or used to configure OAuth. If using real JWT/OAuth audiences, design the token issuance mechanism properly.

Validated configuration record:

```java
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.partners.catalog")
public record CatalogApiProperties(
        @NotNull URI baseUrl,
        String audience
) {
    public CatalogApiProperties {
        if (baseUrl != null && (
                !"https".equalsIgnoreCase(baseUrl.getScheme())
                || baseUrl.getHost() == null
                || baseUrl.getRawUserInfo() != null
                || baseUrl.getRawQuery() != null
                || baseUrl.getRawFragment() != null
                || (baseUrl.getRawPath() != null
                    && !baseUrl.getRawPath().isEmpty()
                    && !"/".equals(baseUrl.getRawPath())))) {
            throw new IllegalArgumentException(
                    "catalog base-url must be an HTTPS origin");
        }
    }
}
```

In this example, the policy accepts only an **HTTPS origin** so all business paths are constructed from `/v1/...`, avoiding prefix-joining ambiguities when the base already includes `/api`. You may relax the policy for local development via separate profile/test properties, yet **never** allow a variable supplied by an HTTP caller to pick an arbitrary host. `@Validated` requires Bean Validation infrastructure, typically `spring-boot-starter-validation` when validation is used.

Enable properties via `@ConfigurationPropertiesScan` on the application or:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogApiProperties.class)
public class CatalogPropertiesConfiguration {}
```

### 3.1. Shared base URL across multiple endpoints

| Environment | `base-url` setting | Endpoint built by adapter |
| --- | --- | --- |
| Local test | `https://catalog.test.example.org` | `/v1/products/{id}` |
| Staging | `https://catalog-staging.example.org` | `/v1/products/{id}` |
| Production | `https://catalog.example.org` | `/v1/products/{id}` |

The application service does not change across environments. Hostname changes are managed via deployment config; never embed credentials in the base URL like `https://user:password@host`, never log credentials, and never connect to a URL returned by an external source without allowlist/SSRF checks.

### 3.2. When the base URL includes a path prefix

Some partners require a base like `https://api.example.org/gateway/catalog`. In that case, **relative paths, leading/trailing `/`, and `UriBuilderFactory` settings** can affect how prefixes are joined. Do not assume from browser resolution rules that every Spring overload joins paths identically.

Pick **one convention**:

1. Configure **origin-only** and have every adapter provide the full API path like `/gateway/catalog/v1/products/{id}`; or
2. Allow a prefix in the base and verify the actual request-target with integration tests against your exact builder/engine version.

Avoid specifying the prefix in both the base and `path(...)`, which produces `/gateway/catalog/gateway/catalog/...`. Also avoid assuming an absolute URI passed to the client keeps the base URL—an **absolute URI** can bypass the configured base.

## 4. Building URIs with templates and `UriBuilder` instead of string concatenation

Suppose you need to call:

```text
GET /v1/products/{productId}
```

`productId` might be `PRD-107`, `SKU A&B`, or an ID containing `/`. With string concatenation:

```java
// Wrong if productId contains /, ?, #, %, spaces, or special Unicode.
String path = "/v1/products/" + productId;
```

a `/` inside the ID can be interpreted as a **path separator**, `?` can start a query, and `#` can start a fragment. Better options are URI template variables and `pathSegment` per the identifier contract:

```java
import java.net.URI;
import org.springframework.web.util.DefaultUriBuilderFactory;

public final class CatalogUriExamples {
    private final DefaultUriBuilderFactory factory =
            new DefaultUriBuilderFactory("https://catalog.example.org");

    public CatalogUriExamples() {
        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);
    }

    public URI productUri(String productId) {
        return factory.builder()
                .pathSegment("v1", "products", "{productId}")
                .build(productId);
    }
}
```

With `TEMPLATE_AND_VALUES`, URI variables are treated as **data values requiring encoding**; when `productId = "SKU A/B"`, the `/` inside the ID is encoded as part of a **single segment** rather than splitting into two segments. Never call `URLEncoder.encode(...)` manually on a path and pass the encoded value into a template; that easily produces `%252F` (encoding `%2F` a second time).

### 4.1. `path(...)` vs. `pathSegment(...)`

| Approach | Intent | Risk |
| --- | --- | --- |
| `path("/v1/products/{id}")` | Use a path template with fixed separators | Valid if URI variables are encoded with the right policy. |
| `pathSegment("v1","products","{id}")` | Build segments where ID is **one segment** | Clearly expresses intent when IDs contain `/`; verify whether the backend accepts `%2F`. |
| `path("/v1/products/" + id)` | Interpolate dynamic value directly into path structure | Can alter path semantics or cause malformed URLs/injection. |
| `URI.create(base + "/v1/products/" + id)` | Create URI from concatenated string | Does not know which part is data to escape; breaks on spaces, `?`, and `#`. |

**No encoding mode can fix a mismatched API contract.** Some gateways reject encoded slashes (`%2F`) in paths due to security or routing policies. If the partner forbids slashes in product IDs, **validate and reject such IDs**; if slashes are valid in IDs, test end-to-end through the actual gateway in use.

### 4.2. Never use fragments to send data to the server

`https://catalog.example.org/v1/products/123#private` does not send `private` to the server in the HTTP request-target. To pass filters or server-side identifiers, use path, query, headers, or body per contract; never expect the server to receive a fragment.

### 4.3. Percent signs in URI variables and double encoding

Three distinct forms:

```text
Raw identifier:            A/B
Encoded path segment:      A%2FB
Double-encoded segment:    A%252FB
```

If a service receives the raw ID `A/B`, pass the raw ID into the builder **once** and let the builder encode it. If upstream passed `A%2FB` and that literally is a **raw ID containing a percent sign**, encoding it to `A%252FB` is actually right. What matters is defining the **input data representation** (raw vs. pre-encoded) and encoding ownership rather than layering `URLDecoder.decode` and re-encoding arbitrarily. For values already decoded from an inbound HTTP request, standardize on treating them as **raw business values** before passing them to outbound adapters.

## 5. Query parameters: filters, pagination, lists, and special characters

The query string is the portion after `?` in a URI. It can carry filters, pagination, language codes, page sizes, and repeated parameters with the same name. Example:

```text
GET /v1/products?category=book&lang=vi&page=0&size=20&tag=java&tag=spring
```

A query pair is not like an HTTP header. `category` may be required by contract; `tag` may carry multiple values. Queries should be **built by name/value** rather than concatenating `"?category=" + category + "&..."`.

### 5.1. `queryParam` for single and repeated values

```java
import java.net.URI;
import org.springframework.web.util.DefaultUriBuilderFactory;

public final class ProductSearchUris {
    private final DefaultUriBuilderFactory factory;

    public ProductSearchUris(String baseUrl) {
        factory = new DefaultUriBuilderFactory(baseUrl);
        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);
    }

    public URI search(
            String phrase, int page, int size) {

        if (phrase == null || phrase.isBlank()
                || page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid search arguments");
        }

        return factory.builder()
                .pathSegment("v1", "products")
                .queryParam("q", "{phrase}")
                .queryParam("page", page)
                .queryParam("size", size)
                .build(phrase);
    }

    public URI searchByTags() {
        return factory.builder()
                .pathSegment("v1", "products")
                .queryParam("tag", "java", "spring")
                .build();
    }
}
```

Meaning of `queryParam("tag", "java", "spring")`: a single name **`tag`** appears multiple times, producing `tag=java&tag=spring` in many APIs. Do not replace it with `tag=java,spring` if the partner contract specifies a **repeated parameter**. Nor assume a server supports comma-separated lists simply because a framework has a `List<String>` converter.

For dynamic values containing `&`, `?`, `=`, or `#`, use a **URI template variable** such as `"{phrase}"` and pass it to `build(phrase)`. Never embed user values directly into a URI template string before building:

```java
// Risks altering query semantics when user enters &, #, =, or ?.
String uri = "/v1/products?q=" + phrase;

// Separate structure and data so the encoder handles escaping.
builder.path("/v1/products")
       .queryParam("q", "{phrase}")
       .build(phrase);
```

### 5.2. Optional parameters: difference between absent, empty, and literal `null`

Three requests can carry different meanings:

```text
GET /v1/products
GET /v1/products?category=
GET /v1/products?category=null
```

| Query | Server may interpret as | Note |
| --- | --- | --- |
| No `category` | Do not filter by category | Standard way when an optional parameter is absent. |
| `category=` | Filter present with empty string value | Some APIs reject as invalid; others treat as empty category. |
| `category=null` | Literal string `"null"` | **Not** automatically equivalent to Java/JSON null. |
| `category` without `=` | Flag/presence parameter | Semantics depend on API; do not blindly rewrite to `category=true`. |

Build optional parameters **intentionally**:

```java
import java.net.URI;
import org.springframework.web.util.UriBuilder;
import org.springframework.web.util.DefaultUriBuilderFactory;

public final class OptionalProductUris {
    private final DefaultUriBuilderFactory factory;

    public OptionalProductUris(String baseUrl) {
        factory = new DefaultUriBuilderFactory(baseUrl);
    }

    public URI list(String category, Integer size) {
        UriBuilder builder = factory.builder().path("/v1/products");

        if (category != null && !category.isBlank()) {
            builder.queryParam("category", "{category}");
        }
        if (size != null) {
            if (size < 1 || size > 100) {
                throw new IllegalArgumentException("Invalid size");
            }
            builder.queryParam("size", size);
        }

        return (category != null && !category.isBlank())
                ? builder.build(category)
                : builder.build();
    }
}
```

Here, blank `category` is simply **omitted** per the assumed contract. If the partner distinguishes an "empty filter" from an "absent filter," represent both explicitly in the input model instead of passing `String`/`null` loosely.

**An important limitation of this example:** the URI template variable `{category}` is part of the query; when expanding multiple URI templates in the same builder, use `Map.of("category", category)` to avoid positional parameter mismatches. With many optional fields, an explicit expansion map or dedicated URI factory method is easier to maintain than positional arguments.

### 5.3. Dynamic query structures via allowlists

If an HTTP API accepts `sort`, `fields`, `page`, and `size` from callers, never forward raw input unchecked into a partner URI. For instance, `sort=price,desc` must match allowed fields:

```java
import java.util.Set;

public final class ProductSortPolicy {
    private static final Set<String> SORT_FIELDS =
            Set.of("name", "price", "createdAt");

    public static String validateSort(String field, boolean descending) {
        if (!SORT_FIELDS.contains(field)) {
            throw new IllegalArgumentException("Unsupported sort field");
        }
        return field + (descending ? ",desc" : ",asc");
    }
}
```

A builder only guarantees **URI syntax/encoding**, not that the caller is authorized to request arbitrary fields, filters, or page sizes. Validate business values and cap page sizes; prevent a caller from causing the adapter to pull millions of rows from a partner and `collectList()` into RAM.

### 5.4. Timestamps, decimals, and locales

A `from`/`to` query needs a clear contract:

```text
GET /v1/orders?from=2026-11-21T00%3A00%3A00Z&to=2026-11-22T00%3A00%3A00Z
```

Example formatting `Instant` as ISO-8601 UTC:

```java
import java.net.URI;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import org.springframework.web.util.UriBuilderFactory;

public URI ordersInWindow(
        UriBuilderFactory factory, Instant from, Instant to) {
    if (from == null || to == null || !from.isBefore(to)) {
        throw new IllegalArgumentException("Invalid time window");
    }
    String fromIso = DateTimeFormatter.ISO_INSTANT.format(from);
    String toIso = DateTimeFormatter.ISO_INSTANT.format(to);

    return factory.builder()
            .path("/v1/orders")
            .queryParam("from", "{from}")
            .queryParam("to", "{to}")
            .build(java.util.Map.of("from", fromIso, "to", toIso));
}
```

A contract may require epoch milliseconds, timezone offsets, date-only, or another format; never rely on `Date.toString()` or the server's default `Locale`. For monetary amounts, use `BigDecimal.toPlainString()` when an API expects decimal text with defined scale/currency rules, never passing through `double` and risking unexpected rounding.

## 6. Percent-encoding: a tiny discrepancy can break filtering

In URIs, certain characters are **reserved** because they carry structural meaning (`/`, `?`, `#`, `&`, `=`, ...). **Percent-encoding** represents bytes as `%HH` where needed. Many URI builders encode Unicode characters as UTF-8; never assume "one Java `char` = one byte."

| Raw value | Encoded as URI data | What to watch out for |
| --- | --- | --- |
| `A B` | Typically `A%20B` in URI encoding | Do not replace every space with `+` unless the contract uses form encoding. |
| `C++` | `C%2B%2B` when literal `+` must be preserved in query value | Many servers form-decode `+` into a space. |
| `A&B` | `A%26B` inside a single query value | With string concatenation, `&` starts a new query parameter. |
| `R&D=1` | `R%26D%3D1` when the whole string is a value | `=` must not create a new name/value pair. |
| `A/B` | `A%2FB` when it is **one path segment** with appropriate encoding | Encoded slashes may be rejected or specially handled by proxies/servers. |
| `100%` | `100%25` | Re-encoding a pre-encoded value mistakenly yields `%2525`. |
| `cà phê` | UTF-8 percent-encoded in the actual URI | Test through real client and server instead of guessing from Unicode logs. |

### 6.1. `URLEncoder` is for HTML forms, not all URI components

In Java:

```java
String encoded = java.net.URLEncoder.encode(
        "C++ basics", java.nio.charset.StandardCharsets.UTF_8);
// Form-style encoding may contain + to represent spaces.
```

`URLEncoder` follows `application/x-www-form-urlencoded` rules: **spaces become `+`**. Using it to encode a path segment and then passing the result to `UriBuilder` can violate the contract and cause double-encoding. Use Spring's URI builder, and test values with plus signs, spaces, percent signs, and Unicode against the server that actually receives them.

### 6.2. Encoding modes of `DefaultUriBuilderFactory`

Spring supports configuring `DefaultUriBuilderFactory.EncodingMode`. Key modes to understand:

| Mode | Intent | When to consider |
| --- | --- | --- |
| `TEMPLATE_AND_VALUES` | Encodes the URI template and **strictly encodes URI variables** as data | Safe/common choice for IDs, keywords, and query values from the app. |
| `VALUES_ONLY` | Does not pre-encode the template like above, yet strictly encodes variables | When the template is already normalized and you want independent template encoding control. |
| `URI_COMPONENT` | Expands variables first, then encodes URI components; may leave certain reserved chars valid in that component | Must thoroughly understand behavior when values contain reserved chars and backend semantics. |
| `NONE` | Performs no automatic encoding | Only suited for data/templates **guaranteed to be properly encoded**; never use on untrusted input. |

Exact defaults can vary by class, configuration path, and Spring version; when designing a shared client, **set the encoding mode intentionally** to avoid upgrade surprises. Never set `NONE` globally to "fix a double-encoding bug" if upstream callers still pass raw user input. Fix the raw/pre-encoded boundary and write tests asserting the actual request-target.

### 6.3. Avoiding double encoding when passing a pre-built `URI`

There is a difference between:

```java
client.get().uri("/v1/products/{id}", rawProductId);
```

and:

```java
URI alreadyBuilt = uriBuilderFactory.builder()
        .pathSegment("v1", "products", "{id}")
        .build(rawProductId);
client.get().uri(alreadyBuilt);
```

The overload taking a **`URI`** indicates: "the URI is already built, send it as-is"; the overload taking a **String template + variables** gives the framework the responsibility to expand/encode. Avoid converting `alreadyBuilt.toString()` back into a string and passing it through a second builder expecting it not to encode again. Have **a single component own encoding** in the outbound adapter and test every character that matters to the partner.

## 7. A query string is not a simple `Map<String,String>`

Contract subtleties to preserve:

- One name can appear multiple times: `tag=java&tag=spring`.
- Absent name, name without value, and name with empty value differ.
- Servers may care about **parameter order**, especially for HMAC signatures or canonical requests.
- Parameter names can be case-sensitive per contract, whereas HTTP header names are case-insensitive.
- Some APIs use bracket notation like `filter[status]=ACTIVE` or `ids[]=1&ids[]=2`; never assume all servers support it.
- Query values may contain Unicode/`+`/`&`, requiring contract-compliant encoding.

**Do not convert queries into a plain map and lose repeated values.** If reading/holding repeated params in Spring Web, use a type like `MultiValueMap<String,String>` instead of `Map<String,String>`. When sending outbound, call `queryParam` per value or use an appropriate multi-value API.

### 7.1. Why do HMAC signatures break even when a URL still works?

Some partners require a signature computed over a canonical request comprising **path, query, headers, and body hash**. If you sign:

```text
tag=java&tag=spring
```

but an interceptor reorders parameters, turns `%20` spaces into `+`, or drops duplicates, the signature breaks even though a caller sees the same filter. Read the partner's **exact canonicalization specification**: whether to sort or keep order, how to percent-encode, which headers to sign, which bytes to hash, and which timestamp/window applies.

A URI builder alone **does not implement** HMAC signing. If request signing is required, build/canonicalize the request before signing, ensure the HTTP engine sends the exact signed representation, and test the canonical string against the partner's official fixtures.

## 8. `RestClient`: configuring URI builders and default headers once

`RestClient` in Spring Framework 6.1+ provides a fluent synchronous HTTP client. In Spring Boot, inject the Boot-managed `RestClient.Builder` to inherit customizers, message converters, and observations, then build **one client per partner** at startup instead of calling `RestClient.create()` per request.

### 8.1. Spring bean holding the URI policy

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

@Configuration(proxyBeanMethods = false)
public class CatalogHttpClientConfiguration {

    @Bean
    RestClient catalogRestClient(
            RestClient.Builder bootBuilder,
            CatalogApiProperties properties) {

        var uriFactory = new DefaultUriBuilderFactory(
                properties.baseUrl().toString());
        uriFactory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

        return bootBuilder
                .uriBuilderFactory(uriFactory)
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
```

`CatalogApiProperties` is the bean registered in section 3. Here **`uriBuilderFactory(...)` owns both the base URL and encoding rules**; do not also call `baseUrl(...)` and guess which takes precedence. `defaultHeader(Accept, application/json)` is a **static** policy containing no user data or rotating tokens.

When using multiple `RestClient` beans:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CatalogProductAdapter {
    private final RestClient client;
    private final PartnerTokenProvider tokenProvider;

    public CatalogProductAdapter(
            @Qualifier("catalogRestClient") RestClient client,
            PartnerTokenProvider tokenProvider) {
        this.client = client;
        this.tokenProvider = tokenProvider;
    }

    public ProductDto findProduct(
            String productId, String language, String correlationId) {

        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("Missing productId");
        }
        if (!java.util.Set.of("vi", "en").contains(language)) {
            throw new IllegalArgumentException("Unsupported language");
        }

        return client.get()
                .uri(uri -> uri
                        .pathSegment("v1", "products", "{id}")
                        .queryParam("lang", "{lang}")
                        .build(java.util.Map.of(
                                "id", productId,
                                "lang", language)))
                .headers(headers -> {
                    headers.setBearerAuth(
                            tokenProvider.tokenForCatalog());
                    headers.set("X-Correlation-ID", correlationId);
                })
                .retrieve()
                .body(ProductDto.class);
    }
}

public record ProductDto(String id, String name) {}

public interface PartnerTokenProvider {
    String tokenForCatalog();
}
```

In a real project, place `public` top-level types in separate Java files. `PartnerTokenProvider` is an **application-implemented** interface: it may read an app token or integrate with OAuth2 Authorized Client policies. It must return a token **without the `Bearer ` prefix** so `setBearerAuth` adds the prefix exactly once. `correlationId` must be validated against null/control characters and sourced from a trusted trace/edge policy; never pass arbitrary inbound HTTP headers to partners unfiltered.

**Why is `@Qualifier` important?** When both `catalogRestClient` and `billingRestClient` exist, the application must not rely on default bean names and accidentally inject a client pointing at the wrong host or credentials. Selecting beans explicitly by **partner and role** makes request routing clear in code reviews.

### 8.2. HTTP status errors must be mapped in the adapter

`retrieve().body(...)` throws exceptions on 4xx/5xx responses under default handling. The adapter must not silently return `null` for all errors:

- `404` during product lookup may mean **does not exist** per contract, requiring `ProductNotFoundException`.
- `429` may signal **rate limiting** with `Retry-After`; do not retry immediately without bounds.
- `401/403` usually indicates auth/permission issues; enlarging the pool or resending the same token will not help.
- `5xx` and network timeouts may be transient; enforce deadlines and bounded retries when the operation is safe.
- A 2xx body violating the schema is a **contract error**, never silently mapped to an empty DTO.

In the adapter, use `onStatus(...)` or exception mapping per the Spring API. Whatever the error, avoid logging raw responses containing PII or tokens; truncate error bodies before logging or recording metrics.

## 9. `WebClient`: similar URI policy, different reactive lifecycle

`WebClient` uses Reactor/Reactive Streams and receives a Boot-configured `WebClient.Builder` when WebFlux is present. It uses the same concepts of **base URL, URI templates, query parameters, and headers** as `RestClient`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

@Configuration(proxyBeanMethods = false)
public class CatalogWebClientConfiguration {

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder bootBuilder,
            CatalogApiProperties properties) {

        var factory = new DefaultUriBuilderFactory(
                properties.baseUrl().toString());
        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

        return bootBuilder
                .uriBuilderFactory(factory)
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
```

Fetching a product by `id` and `lang`:

```java
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class ReactiveCatalogProductAdapter {
    private final WebClient client;
    private final PartnerTokenProvider tokens;

    public ReactiveCatalogProductAdapter(
            @Qualifier("catalogWebClient") WebClient client,
            PartnerTokenProvider tokens) {
        this.client = client;
        this.tokens = tokens;
    }

    public Mono<ProductDto> findProduct(
            String id, String lang, String correlationId) {
        if (id == null || id.isBlank()) {
            return Mono.error(new IllegalArgumentException("Missing id"));
        }

        return client.get()
                .uri(uri -> uri
                        .pathSegment("v1", "products", "{id}")
                        .queryParam("lang", "{lang}")
                        .build(Map.of("id", id, "lang", lang)))
                .headers(headers -> {
                    headers.setBearerAuth(tokens.tokenForCatalog());
                    headers.set("X-Correlation-ID", correlationId);
                })
                .retrieve()
                .bodyToMono(ProductDto.class);
    }
}
```

This illustrates **URI and header policy**, not a complete OAuth2 token-refresh implementation. `tokens.tokenForCatalog()` executes while constructing the request at subscription time; if issuing a token performs HTTP or blocking storage I/O, **never** block on the Reactor event loop. For OAuth2, prefer Spring Security OAuth2's reactive authorized client/filter mechanisms matching your version.

**Never call `subscribe()` freely and return "processed"** inside Kafka/AMQP/Spring Integration consumers: the HTTP call may fail after the message is already acked. Keep the publisher inside a managed lifecycle with timeouts/deadlines and business idempotency.

### 9.1. Two clients can share a contract without sharing resource policies

`RestClient` and `WebClient` both understand URI templates, but their transports/pools and threading models differ. A `WebClient` on `Reactor Netty` uses an event loop and `ConnectionProvider`; `RestClient` may use Apache HttpClient or the JDK engine. **Pick the client by caller model**, then unify the **URI + header contract** via adapters/tests; never assume identical base URL configuration implies a shared TCP connection pool.

## 10. HTTP headers: which ones and where to set them?

Headers carry HTTP message metadata. Header names are **case-insensitive** in principle, while values can have complex semantics; some headers may appear multiple times or carry lists. Never treat headers as an unconstrained text map.

| Header | Common role | Recommended policy |
| --- | --- | --- |
| `Accept` | Which media type the client wants the server to return | E.g., `application/json`; does not describe the outgoing request body. |
| `Content-Type` | Media type of the **request body** when present | E.g., `application/json` on POST/PUT; no need to attach arbitrarily on bodyless GETs. |
| `Authorization` | Request authentication, typically Bearer/Basic per contract | Scope per partner/request; **never log** or leak tokens to the wrong client. |
| `Accept-Language` | Preferred content language | Per contract and allowlisted languages; never auto-trust raw input. |
| `Idempotency-Key` | Identifies one logical operation so partners handle retries safely when supported | Keep the **same key across attempts** of one command. |
| `X-Correlation-ID` / `X-Request-ID` | Links logs/traces across systems | Standardize naming/source/format; never use as a deduplication key if semantics differ. |
| `traceparent` / `tracestate` | W3C distributed tracing | Let instrumentation propagate per policy; avoid manually overwriting trace headers. |
| `If-Match` | Optimistic concurrency condition based on ETag | Use on updates requiring resource version checks. |
| `If-None-Match` | Conditional fetch/cache validation with ETag | Handle `304 Not Modified` per contract. |
| `User-Agent` | Identifies client application/library | Set a stable app identifier without user data. |
| `Cookie` | Session state under a protocol | Never forward user cookies to partner APIs unless required and authorized. |
| `Host` / HTTP/2 `:authority` | Authority name at HTTP routing layer | Let the transport construct it consistently with URI/TLS; never spoof to reroute. |

### 10.1. `Accept` vs. `Content-Type`

GET request expecting JSON:

```http
GET /v1/products/PRD-107?lang=vi HTTP/1.1
Host: catalog.example.org
Accept: application/json
```

POST request sending JSON and expecting JSON:

```http
POST /v1/orders HTTP/1.1
Host: billing.example.org
Accept: application/json
Content-Type: application/json
Idempotency-Key: pay-req-892

{"orderId":"ORD-892","amount":125000}
```

`Accept: application/json` specifies the **desired response representation**; `Content-Type: application/json` specifies the **request body representation**. If the server returns `Content-Type: application/problem+json` on errors, the client must read/map errors per that media type/contract rather than assuming every JSON response is a success DTO.

### 10.2. Default headers vs. per-request headers

**Default headers** fit client/partner-wide static values such as `Accept: application/json`. **Per-request headers** are for tokens, correlation IDs, idempotency keys, ETags, or tenant contexts that change.

In Spring HTTP APIs, `defaultHeader(...)` supplies a **default value** when a request lacks that header per builder contract. Note the difference between `header(name, value)` (which may **append** values) and `headers(h -> h.set(name, value))` (**sets/replaces**); when a header must have only **one** value, prefer `set(...)` per request:

```java
client.get()
        .uri("/v1/products/{id}", productId)
        .headers(h -> {
            h.setAccept(java.util.List.of(
                    org.springframework.http.MediaType.APPLICATION_JSON));
            h.set("X-Correlation-ID", correlationId);
        })
        .retrieve()
        .body(ProductDto.class);
```

Avoid ending up with two `Authorization` values on one request because a default Bearer token coexists with `header("Authorization", ...)` elsewhere. With multiple tokens/tenants, **never store a dynamic Bearer token as a global default header** on a singleton client and mutate it on each call.

### 10.3. Multi-value headers and case-insensitivity

Header names `accept`, `Accept`, and `ACCEPT` mean the same header per HTTP semantics, even if libraries display differing casing in logs. When inspecting headers, use `HttpHeaders.getFirst("...")` or `get(...)` rather than case-sensitive raw string matching. Certain headers permit comma-separated lists, but **do not** merge arbitrary headers with commas—especially those with special grammar or security semantics. Test multi-value headers against the HTTP specification and partner contract.

## 11. Security headers: Bearer, Basic, API keys, and certificates

**Authentication** for outbound requests is not always an `Authorization` header. Depending on the partner API:

- **Bearer token:** usually `Authorization: Bearer <token>`, often an OAuth2 access token needing refresh before expiration.
- **Basic authentication:** only when required by the partner over a TLS-protected connection; username/password are encoded per spec, not encrypted secrets.
- **API key:** may live in `X-API-Key` or a custom header per spec; do not rename it or move keys into query strings unless explicitly permitted.
- **mTLS:** client identity lives at the **TLS certificate/handshake** layer, not in an application Spring header.
- **HMAC signing:** requires canonicalizing method, path, query, headers, and body hash per contract; there is no universal `Authorization` format across providers.

### 11.1. Per-request Bearer tokens

```java
String token = tokenProvider.tokenForCatalog();

ProductDto response = catalogRestClient.get()
        .uri(uri -> uri
                .pathSegment("v1", "products", "{id}")
                .build(productId))
        .headers(headers -> headers.setBearerAuth(token))
        .retrieve()
        .body(ProductDto.class);
```

**Never** initialize a singleton `RestClient` with a short-lived token expecting it to refresh itself after 60 minutes. With OAuth2 client credentials, use Spring Security's token management/authorized client support with controlled caching and refresh, rather than injecting a static `@Value("${PARTNER_TOKEN}")` at startup that never rotates.

### 11.2. Headers and URIs must belong to the same partner

Risk:

```text
catalogRestClient has Authorization: Bearer catalog-token
caller passes an absolute URI: https://attacker.example/path
=> request may leave the catalog host while still carrying credentials
```

Base URLs **can be overridden** when callers pass an absolute URI in many Spring APIs. Therefore:

1. Never allow HTTP input to supply arbitrary outbound URLs.
2. Restrict destinations to configured/allowlisted origins; use relative paths controlled by the adapter.
3. If calling a completely different URL via redirect or presigned URL is necessary, use a **dedicated client/credential policy**.
4. Verify redirect policies in the HTTP transport. Never rely on "the library probably strips `Authorization` on cross-origin redirects" without verifying your engine and version.
5. With mTLS, separate HTTP engines/pools when client certificates or trust policies differ across partners.

**Never log Bearer tokens, Basic credentials, API keys, or HMAC signatures** in request debug logs, trace attributes, metric tags, or error bodies. Query strings can also appear in server/proxy access logs; if an API supports passing secrets in headers rather than queries, follow the safer option permitted by contract.

### 11.3. Never forward inbound headers wholesale

When a Spring Boot controller receives a user request and calls a partner:

```java
// DANGEROUS: forwards all inbound headers to another system.
outbound.headers(h -> h.addAll(inboundHeaders));
```

This can leak `Authorization`, `Cookie`, internal debug headers, unverified tenant IDs, or proxy headers. Build an **explicit allowlist**—for instance, a validated correlation ID, an allowlisted language, and a dedicated client credential for that partner. If distributed tracing auto-instrumentation is active, rely on its supported propagation rather than copying raw headers blindly.

## 12. Business headers: idempotency, ETag, conditional requests, and locale

Certain headers affect **business correctness**, not just technical metadata.

### 12.1. `Idempotency-Key` protects retries for side-effecting POSTs

Example creating a payment from an HTTP call:

```java
import java.math.BigDecimal;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public record CreatePaymentRequest(
        String orderId,
        BigDecimal amount
) {}

public record PaymentResponse(
        String paymentId,
        String status
) {}

public PaymentResponse createPayment(
        RestClient billing,
        CreatePaymentRequest body,
        String stableOperationId) {

    if (stableOperationId == null || stableOperationId.isBlank()) {
        throw new IllegalArgumentException("Missing operation ID");
    }

    return billing.post()
            .uri("/v1/payments")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .headers(h -> h.set("Idempotency-Key", stableOperationId))
            .body(body)
            .retrieve()
            .body(PaymentResponse.class);
}
```

Suppose the request is sent and the partner commits the payment, but the client times out before receiving the response. If a retry sends a **new key**, the partner may treat it as a separate payment. If the retry sends the same key and **the partner contract supports idempotency**, the target system can replay the prior result or reject conflicting payloads per policy.

**The header alone does not create idempotency.** You must know whether the partner supports it, key retention duration, tenant/account scoping, handling of mismatched bodies with the same key, and status inquiry after timeouts. For producers writing to a DB and emitting broker events, you still need a transactional outbox; for consumers receiving redeliveries, you need an inbox/unique constraint. Never infer system-wide exactly-once from a header.

### 12.2. ETag and conditional updates

Partner returns:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v7"

{"id":"ORD-89","status":"PENDING"}
```

When updating status, the caller only wants the edit to apply if the version still matches:

```http
PUT /v1/orders/ORD-89 HTTP/1.1
Host: catalog.example.org
Content-Type: application/json
If-Match: "order-v7"

{"status":"ACCEPTED"}
```

The server may return `412 Precondition Failed` if the ETag changed. This is **optimistic concurrency at the HTTP boundary**, analogous to database versioning yet distinct from JPA/Mongo `@Version`. The client must re-read current state and decide rather than blindly retrying `PUT` with the stale ETag.

For GETs, `If-None-Match` can yield `304 Not Modified` so the client reuses its cached copy. When using Redis or HTTP caches, cache keys/variants and freshness rules must account for URI, query, `Accept`/`Accept-Language`, and relevant `Vary` headers. Never share cached responses for access-controlled data without isolating identity/tenant scopes.

### 12.3. Correlation ID is not an idempotency ID

`X-Correlation-ID` links inbound HTTP, database transactions, outbound HTTP, and Kafka events, whereas one **business operation** may be retried multiple times or split across multiple messages. Separate conventions clearly:

| Identifier | Meaning | Across retries |
| --- | --- | --- |
| Correlation/trace ID | Traces a journey and its spans/requests | May stay the same or change per tracing propagation; not a business dedup key. |
| Idempotency key | One **logical side effect** at the partner | Must stay stable across attempts belonging to the same operation per contract. |
| Event ID | Identity of a broker/outbox event | Preserved across republishes of the same event. |
| Order/payment ID | Identity of a business entity | May legitimately undergo multiple valid events and API operations. |

When W3C Trace Context instrumentation is active via Spring Boot/Micrometer, never fabricate `traceparent` from a random UUID: trace headers follow specific formats and semantics. Use the tracer/propagator tools to preserve context accurately.

## 13. Interceptors/filters: adding consistent headers without leaking data

When a partner requires `User-Agent` and a client-version header on every call, set them as **default headers** when constructing the client. When per-request logic like tracing or redacted logging is needed, use an interceptor or filter.

### 13.1. RestClient interceptor for non-sensitive metadata

```java
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

ClientHttpRequestInterceptor agentHeader = (request, body, execution) -> {
    request.getHeaders().set("X-Client-Name", "order-integration");
    return execution.execute(request, body);
};

RestClient client = bootBuilder
        .requestInterceptor(agentHeader)
        .build();
```

`bootBuilder` is a Spring-managed builder (e.g., inside a `@Bean` factory), not a global static variable. This interceptor sets a **fixed** header and logs neither bodies nor tokens; every interceptor needs an exception policy and must never trigger unintended retries. Spring Boot interceptors may already attach metrics/tracing; never replace the whole builder/request factory and drop pre-registered customizers.

### 13.2. WebClient filter for controlled logging

```java
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;

ExchangeFilterFunction logOperation = (request, next) -> {
    // Log allowlisted operation/host name; do not log raw URI,
    // Authorization, Cookie, query with PII, or request body.
    return next.exchange(request);
};

WebClient client = bootBuilder
        .filter(logOperation)
        .build();
```

This snippet intentionally **logs nothing** because real logging needs a logger, redaction rules, and timing/response measurement at the proper point. Its goal is to show where a filter intercepts/observes requests; do not copy it expecting built-in logging/metrics. For tracing, prefer Spring Boot/Micrometer instrumentation, since manually injecting trace headers in custom filters can break propagation.

### 13.3. Ordering of header/URI customizations and testing

If a client combines default `Accept`, an interceptor, an OAuth filter, and per-request `Authorization`, actual ordering determines the final headers. Never assume from method names which "always wins" across all Spring/engine versions. **Test on-wire requests** with the exact builder/configuration used in production to verify:

1. No duplicate Bearer tokens or duplicate `Idempotency-Key` values appear.
2. Dynamic tokens match the right partner/tenant and are not sent on cross-origin redirects.
3. `Content-Type` and `Accept` match the body/response contract.
4. Correlation/trace headers are well-formed and do not overwrite context unexpectedly.
5. Templated URIs preserve the exact base host, path segments, and query.

**Never use a mutable shared header map** as a static field updated per user and passed into a singleton client. Concurrent requests in a multi-threaded environment would read each other's headers; build per-request headers from the current call context.

## 14. Declarative HTTP interfaces: URI/header contracts directly on methods

Spring Framework provides **HTTP interfaces** to declare outbound APIs with annotations, then generate proxies backed by a configured `RestClient` or `WebClient`. They fit well when a partner exposes many stable endpoints, yet **they do not replace** `baseUrl`, transport, token management, or error handling.

Example interface using synchronous `RestClient`:

```java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(url = "/v1")
public interface CatalogHttpApi {

    @GetExchange("/products/{id}")
    ProductDto getProduct(
            @PathVariable("id") String productId,
            @RequestParam("lang") String language,
            @RequestHeader("X-Correlation-ID") String correlationId);
}
```

Creating the proxy from the selected client:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
public class CatalogProxyConfiguration {

    @Bean
    CatalogHttpApi catalogHttpApi(
            @Qualifier("catalogRestClient") RestClient client) {
        var adapter = RestClientAdapter.create(client);
        return HttpServiceProxyFactory
                .builderFor(adapter)
                .build()
                .createClient(CatalogHttpApi.class);
    }
}
```

This expresses method/path/query/headers **declaratively**. `CatalogHttpApi` still relies on `RestClient` configuration (host, URI factory, JSON converter, TLS, timeouts, observability), and the adapter must still:

- Validate `productId` and `lang` against the contract before calling.
- Attach `Authorization` via a token manager, interceptor, or dedicated adapter layer.
- Handle 404, 429, 5xx, timeouts, and empty/invalid DTOs.
- Test actual **encoded URIs**—especially IDs with slashes—because annotations do not automatically understand partner access rules or schemas.

When building a proxy via `WebClientAdapter`, methods can return `Mono<T>`/`Flux<T>` per adapter/interface capabilities. Do not change a synchronous interface built over `RestClientAdapter` to return `Mono` expecting reactive network I/O to appear automatically.

### 14.1. Avoid creating proxies per request

HTTP interface proxies, `RestClient`, and `WebClient` should typically be created **once** as Spring beans and reused. Never instantiate `HttpServiceProxyFactory` for each Kafka message or inbound HTTP request just to swap `baseUrl` dynamically: that breaks pool control, credential scoping, and observability. If multiple valid partners exist, declare a configured registry/bean per allowlisted partner rather than accepting arbitrary URLs from callers.

## 15. URL/header security: SSRF, redirects, path traversal, and injection

A URI builder handles **syntactic encoding**, not a **complete security boundary**. Primary risks in outbound integration are **Server-Side Request Forgery (SSRF)** and leaking sensitive data.

### 15.1. Base URL is not a barrier if absolute URIs are accepted

Suppose the application intends to always call catalog:

```java
RestClient catalog = RestClient.builder()
        .baseUrl("https://catalog.example.org")
        .build();
```

If a method later executes:

```java
// Do NOT do this with a URL supplied by an HTTP caller.
catalog.get().uri(userSuppliedAbsoluteUrl).retrieve().toBodilessEntity();
```

an absolute URI can **override the base URL**, routing the request to another host—even internal endpoints if the network permits. Combined with default `Authorization` or token-injecting interceptors, credential-leakage risk escalates.

**Required policy:**

1. Keep origin/base URLs in server-side configuration, never from user query/body inputs.
2. Accept **business IDs or filter values** as data, then construct relative paths/queries using templates.
3. If calling multiple hosts is required, enforce an exact allowlist of scheme, hostname, port, and TLS policy; also validate redirect targets.
4. For untrusted URLs, address DNS resolution, private/loopback/link-local IP ranges, DNS rebinding, and proxy routing; naive substring checks like `endsWith("example.org")` are insufficient.
5. Restrict outbound traffic with egress/firewall policies and workload permissions, not solely application regexes.

For webhooks or presigned download URLs from a trusted partner, use a **separate client** with restricted redirect/credential policies; still validate targets and enforce size/timeout caps. Never send catalog's token to a third-party host merely because catalog returned a `Location` header.

### 15.2. Encoded paths can become path traversal after decoding

A raw ID:

```text
../admin
```

contains slashes and traversal sequences. Templates/`pathSegment` encode it as **one segment**, yet gateways or backends may decode multiple times or normalize paths differently. If IDs must never contain `..` or `/`, **validate the ID format** before building the URI. Never treat `%2E%2E` or `%2F` as "guaranteed safe" when downstream servers post-process paths.

**Two-layer defense:** contract-based input validation plus syntactically safe URI builders, paired with server/gateway routing policies and integration tests. Never assemble paths from untrusted values to select file resources or internal admin endpoints.

### 15.3. Header injection and control characters

Header values must never contain arbitrary CR/LF characters; if an unvalidated trace/correlation ID from inbound HTTP is forwarded, attackers may try header injection or log forging on weak libraries. Modern HTTP engines validate headers, yet applications should still enforce format and length—e.g., accepting only normalized request IDs.

**Never manually set `Host` or HTTP/2 `:authority` to "bypass" hostname allowlists.** The transport must stay consistent across DNS/TCP destination, TLS SNI, certificates, and HTTP authority; changing headers does not make a target trusted.

### 15.4. Sensitive data in query strings

Query strings routinely appear in reverse-proxy logs, APM tools, browser histories, and monitoring dashboards. Never put passwords, access tokens, API keys, or PII into queries just for easier debugging; use headers or bodies per API contract over HTTPS/TLS. If a partner strictly requires sensitive query parameters, enforce redaction, log retention limits, and strict access controls.

## 16. Outbound HTTP adapters in Spring Integration and asynchronous flows

Spring Integration can make HTTP calls via outbound gateways/adapters or service activators backed by a dedicated `RestClient`/`WebClient`. Rules for base URLs, encoding, and headers remain **identical to standard HTTP calls**, while also accounting for message lifecycles, error channels, and broker acknowledgments.

```mermaid
flowchart LR
    A[(Kafka / RabbitMQ)] --> B[Inbound adapter]
    B --> C[Validate event + map DTO]
    C --> D[HTTP outbound call]
    D --> E[Catalog RestClient / WebClient]
    E --> F[URI template + query + headers]
    F --> G[Partner API]
    G --> H[Map result / error]
    H --> I[(DB / outbox / cache)]
```

**A controllable layered design:**

- The inbound broker adapter reads the message/event contract and extracts `orderId`/correlation ID.
- The application service determines the operation, idempotency key, and deadline.
- The HTTP adapter builds the **relative URI** from validated IDs/filters and attaches the partner token and required headers.
- Results/errors return to the flow to decide DB transactions, ack/offset commits, retries, or DLQ routing.

### 16.1. Never copy all `MessageHeaders` onto an HTTP request

A Spring Integration `Message<?>` carries internal headers like message IDs, timestamps, routing metadata, or broker headers. These are neither valid outbound HTTP headers nor safe to disclose.

```java
// Anti-pattern: forwarding all MessageHeaders to an HTTP partner.
// httpRequest.headers(h -> h.addAll(message.getHeaders()));
```

Instead, build an explicit **header allowlist** per contract: e.g., a normalized correlation ID, business `Idempotency-Key`, and verified tenant context if genuinely required by the partner. Never leak Kafka headers, broker credentials, Spring internal Message IDs, or inbound client JWTs as unfiltered HTTP headers.

### 16.2. Deadlines and retries when one message triggers multiple HTTP calls

If one Kafka message triggers 3 HTTP calls, giving each call a 2-second timeout can blow past processing deadlines and cause rebalances or delayed acks. Budget the **total message processing time**, cap each individual call, and avoid retry storms.

Example consumer receiving `PaymentRequested`:

```text
Message(eventId=evt-55, operationId=pay-55)
  -> HTTP GET /v1/customers/{id}  (catalog token, lang)
  -> HTTP POST /v1/payments       (billing token, stable Idempotency-Key)
  -> DB update + outbox event
  -> ack broker per processing policy
```

Never share **the same HTTP client/token** for catalog and billing merely because both run in the same flow. If the payment POST times out after the server committed, never retry with a fresh key or treat the client status as definitive proof. Query by operation ID and persist state durably, avoiding acknowledging success before business work actually completes.

### 16.3. Cache keys and URI queries must stay aligned

A flow caching catalog data in Redis must not key solely on `productId` if the response varies by `lang`, `currency`, `Accept`, `Accept-Language`, tenant permissions, or API version.

Example:

```text
catalog:v1:product:PRD-107:lang:vi
catalog:v1:product:PRD-107:lang:en
```

Two URIs with different queries can return different representations. Cache keys must capture **every dimension affecting content or authorization**, not just URL paths. HTTP caching relies on `Vary` and `Cache-Control`; application Redis caches must enforce equivalent rules explicitly.

## 17. Testing URIs and headers: inspect the actual request sent

Unit tests for URI construction catch template bugs, yet a Spring HTTP adapter also applies default headers, interceptors, OAuth filters, and transport adjustments. Thus, for important contracts, verify the **wire representation**: method, target path, query, header names/values, media type, and body.

### 17.1. Types of tests to maintain

| Test | Tool | Guarantees verified |
| --- | --- | --- |
| URI builder unit test | `DefaultUriBuilderFactory`, JUnit | Raw IDs produce exact URIs, single-pass encoding, repeated queries preserved. |
| RestClient request test | `MockRestServiceServer` bound to `RestClient.Builder` | Method/URI/headers generated by Spring API match contract, no real network needed. |
| WebClient request test | Mock HTTP server or controlled fake `ExchangeFunction` | URI, query, dynamic headers, and response mapping. |
| Real transport test | WireMock/OkHttp `MockWebServer`, real localhost HTTP server | Request-target, percent-encoding, headers across real transport, redirect policy. |
| Spring Boot context test | `@SpringBootTest` or appropriate slice | `ConfigurationProperties`, Boot-managed builders, filters/interceptors/credentials. |
| Contract/E2E test | Partner sandbox/test fixtures, DB/broker/cache flow | URI/headers against real API version; timeouts, idempotency, side effects, and recovery. |

**`MockRestServiceServer` does not prove** TLS, proxies, DNS, connection pooling, or real HTTP engine redirect behavior. Conversely, a fake HTTP server verifies on-wire URI/header bytes without proving business contract compliance on the production partner.

### 17.2. URI unit tests: IDs with slashes, plus signs, and Unicode

Example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.net.URI;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.web.util.DefaultUriBuilderFactory;

class CatalogUriTest {
    private final DefaultUriBuilderFactory factory =
            new DefaultUriBuilderFactory("https://catalog.example.org");

    CatalogUriTest() {
        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);
    }

    @Test
    void encodesSlashSpaceAndPlusInsideProductId() {
        URI uri = factory.builder()
                .pathSegment("v1", "products", "{id}")
                .build(Map.of("id", "SKU A/B++"));

        assertEquals(
                "/v1/products/SKU%20A%2FB%2B%2B",
                uri.getRawPath());
    }

    @Test
    void keepsRepeatedQueryParameters() {
        URI uri = factory.builder()
                .path("/v1/products")
                .queryParam("tag", "java", "spring")
                .build();

        assertEquals("tag=java&tag=spring", uri.getRawQuery());
    }

    @Test
    void escapesQueryValueInsteadOfCreatingNewParameter() {
        URI uri = factory.builder()
                .path("/v1/products")
                .queryParam("q", "{term}")
                .build(Map.of("term", "C++ & Spring"));

        assertEquals("q=C%2B%2B%20%26%20Spring",
                uri.getRawQuery());
    }
}
```

Assertions use `getRawPath()` and `getRawQuery()` to inspect percent-encoding rather than decoded strings. For Vietnamese IDs or multi-byte UTF-8, add exact fixtures and verify what the server receives after a single decode; never compare via `String.toLowerCase()` or rely on the test runner's default locale.

### 17.3. Network integration test with `MockWebServer`

Assume the project includes JUnit 5, Spring Web, and a compatible `com.squareup.okhttp3:mockwebserver` test dependency:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

class CatalogRequestWireIT {

    @Test
    void sendsExpectedEncodedPathQueryAndHeaders() throws Exception {
        var server = new MockWebServer();
        server.start();

        try {
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "application/json")
                    .setBody("""
                            {"id":"SKU A/B++","name":"Demo"}
                            """));

            var factory = new DefaultUriBuilderFactory(
                    server.url("/").toString());
            factory.setEncodingMode(
                    DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

            var client = RestClient.builder()
                    .uriBuilderFactory(factory)
                    .defaultHeader(HttpHeaders.ACCEPT,
                            MediaType.APPLICATION_JSON_VALUE)
                    .build();

            ProductDto result = client.get()
                    .uri(uri -> uri
                            .pathSegment("v1", "products", "{id}")
                            .queryParam("tag", "java", "spring")
                            .build(Map.of("id", "SKU A/B++")))
                    .headers(h ->
                            h.set("X-Correlation-ID", "corr-123"))
                    .retrieve()
                    .body(ProductDto.class);

            assertNotNull(result);
            assertEquals("SKU A/B++", result.id());

            RecordedRequest request =
                    server.takeRequest(2, TimeUnit.SECONDS);
            assertNotNull(request);
            assertEquals("GET", request.getMethod());
            assertEquals(
                    "/v1/products/SKU%20A%2FB%2B%2B?tag=java&tag=spring",
                    request.getPath());
            assertEquals("application/json",
                    request.getHeader("Accept"));
            assertEquals("corr-123",
                    request.getHeader("X-Correlation-ID"));
            assertNull(request.getHeader("Authorization"));
        } finally {
            server.shutdown();
        }
    }
}
```

In this test, `RestClient.builder()` is created directly **to verify URI/transport behavior in isolation**. It does not prove Spring Boot applied all production customizers. To test the real application bean, start the Spring context with `CatalogApiProperties` overridden in tests to point at the mock server and inject the actual bean or proxy.

The test uses `http://localhost` emitted by the test server; that is **not** a reason to relax `HTTPS origin` policy in production. Never use a MockWebServer URL in production config or disable hostname verification. For tests involving TLS containers or proxies, configure dedicated test certificates rather than disabling verification.

### 17.4. Test case matrix

| Case | Input/action | Key assertions |
| --- | --- | --- |
| Normal ID | `PRD-107` | Clean path, no extra `/` or query appended. |
| ID with slash | `A/B` | Single encoded segment if contract permits; gateway does not misroute. |
| ID with spaces/Unicode | `SKU A`, `cà phê` | Correct UTF-8 encoding and server receives expected decoded value. |
| ID with percent sign | `100%` | Neither unencoded nor double-encoded. |
| Query with plus sign | `C++` | Literal plus preserved, not turned into spaces on decode. |
| Query with `&` or `=` | `R&D=1` | Remains **one value** of one parameter. |
| Repeated query | `tag=java&tag=spring` | Not collapsed into `Map<String,String>` or comma string. |
| Optional parameter | null, empty, absent | Matches policy distinguishing absent vs. empty. |
| Offset/date | ISO-8601 UTC, epoch, or custom format | Format/precision understood by server, independent of machine locale. |
| Media type headers | GET vs. POST JSON | `Accept`/`Content-Type` align with body and contract. |
| Tokens and correlation | Two concurrent callers/tenants | Headers or credentials never bleed across requests or partners. |
| POST retry | Same operation retried multiple times | `Idempotency-Key` stays unchanged; payload semantics unchanged. |
| Conditional update | Stale ETag in `If-Match` | Handles 412 without overwriting newer state. |
| Redirect | 302/307 to another host | No token leakage; redirect/allowlist policy enforced. |
| Absolute URI input | Caller tries passing `http://127.0.0.1/...` | Adapter rejects it or provides no path for external URLs to reach transport. |
| Base URL with prefix | `https://host/gateway` | Final endpoint neither duplicates nor drops the path prefix. |

For asynchronous tests, use bounded timeouts on `server.takeRequest(...)` instead of arbitrary sleeps. With WebClient, subscribe via `StepVerifier` or the appropriate test framework and verify requests and cancellation/error paths; never call `block()` on a Reactor event loop just to simplify a test.

## 18. Troubleshooting common base URL, URI, query, and header issues

| Symptom | Possible cause | Diagnosis and fix |
| --- | --- | --- |
| Request hits the **wrong host** despite `baseUrl` | Caller passed an absolute URI or client/proxy misconfigured | Log allowlisted partner/origin name; check URI overloads and redirects. |
| `404` when path ID contains `/` | Path split into multiple segments or gateway rejects encoded slash | Inspect `getRawPath()`/recorded request; use `pathSegment` and verify server contract. |
| Path contains `/api/api/...` | Base URL already has prefix and adapter adds it again | Standardize on origin-only or a single base prefix and test real URLs. |
| Path loses `/gateway` | Base/path joining behaves unexpectedly with leading slash | Test the request-target with your running Spring version's factory. |
| Query `C++` turns into `C  ` | `+` was form-decoded as space by server | Encode literal plus (`%2B`) with the right URI variable mode; test receiver. |
| `%252F` appears instead of `%2F` | Already-encoded value passed through encoding again | Define raw vs. pre-encoded ownership; encode in only one layer. |
| Search for `R&D` splits into two params | Query string concatenated with `&` manually | Use `queryParam("q", "{q}")` with a URI variable. |
| Server receives only one tag | `Map<String,String>` dropped repeated values | Use repeated `queryParam`/`MultiValueMap` per contract. |
| Absent filter treated as non-absent | Client sent `category=null` or `category=` | Distinguish absent/empty/null; add param only when valid. |
| Results vary with server timezone | `LocalDateTime`/`Date` serialized to query without timezone | Pin ISO-8601 UTC/offset or epoch per contract; test across timezones. |
| Returns `415 Unsupported Media Type` | Wrong request `Content-Type` or serializer mismatch | Check actual request body and `Content-Type`, not just `Accept`. |
| Returns `406 Not Acceptable` | `Accept` incompatible with server's supported response formats | Compare against media types supported by the API. |
| Returns `401` after running for a while | Singleton client cached expired token in default header | Use a token manager/OAuth client per call; verify refresh path. |
| Returns `400` or auth fails due to duplicate headers | `header()` appended instead of replacing, or interceptor added again | Inspect full on-wire HTTP headers; use `HttpHeaders.set(...)` for single-value headers. |
| Token A appears on requests to B | Wrong client qualifier reused, redirect, or absolute URL overrode base | Isolate clients/credentials, allowlist hosts, test cross-origin redirects. |
| Invalid HMAC signature | Parameter order, header canonicalization, or percent-encoding differs from signer | Test sent bytes against official canonical request fixtures. |
| Duplicate payment created after timeout | Retry generated a new `Idempotency-Key` or partner lacks semantics | Stabilize operation ID, query outcome, use inbox/outbox when needed. |
| HTTP cache serves wrong language/tenant | Cache key omitted `lang`/`Vary`/authorization scope | Key caches by all dimensions determining representation and identity. |
| Observability explodes time series | Raw URL with `orderId`/query used as metric label | Use normalized URI template/operation name; keep IDs in secured traces/logs. |
| Spring WebClient call never executes | Publisher was never subscribed to | Return `Mono`/`Flux` to caller lifecycle; avoid fire-and-forget. |

### 18.1. Layered isolation workflow

When receiving an unexpected response, analyze in order:

1. **Destination:** which scheme/host/port did the request actually hit? Were there redirects or proxies?
2. **URI structure:** how was the base URL joined? What are the actual `getRawPath()` and query?
3. **Encoding:** are business values raw or pre-encoded? Are there `+`, `%`, `&`, slashes, or Unicode?
4. **Headers:** are `Accept`/`Content-Type`, tokens, ETags, correlation IDs, and idempotency keys accurate and single-valued?
5. **API contract:** HTTP method (GET/POST/PUT/PATCH), DTO types, status codes, and how the server interprets queries/headers.
6. **Transport/policy:** how are proxy, TLS, redirects, timeouts, and observability configured in Boot or custom clients?
7. **Business impact:** could the server have committed despite client timeout? Is there an operation-ID lookup/reconciliation path?

**Never fix bugs at the wrong layer.** Increasing the connection pool will not turn `tag=java,spring` into two query params; changing retry policy will not stop `C++` from decoding into spaces; adding `Content-Type` to a GET will not fix a wrong base URL.

## 19. Observing URIs and headers without leaking data

Spring Boot Actuator/Micrometer provides HTTP client observability when using compatible builders, connectors, and instrumentation. The key is **tagging by operation/template rather than raw URLs**.

| Data | Record/measure | Avoid |
| --- | --- | --- |
| Partner | `partner=catalog` / `billing` | Raw hostname if it contains tenant/secrets or arbitrary caller input. |
| Operation | `get_product`, `create_payment` | URLs containing per-request IDs. |
| URI pattern | `/v1/products/{id}` | `/v1/products/PRD-107?...` as metric labels. |
| HTTP method | GET, POST, PUT… | Merging reads and writes in a way that obscures retry safety. |
| Status/outcome | 2xx, 4xx, 5xx, timeout, decode error, rejected | Counting only sent requests while ignoring pre-send rejections. |
| Latency | Total call and phase timings when transport exposes them | Treating client timeout as proof the server did not process. |
| Retry attempts | Attempt count, retry reason, remaining budget | Logging full request/response bodies or credentials. |
| Correlation/trace | Trace ID in secured tracing systems | Tokens, Cookies, or personal IDs in metric tags. |
| Idempotency ID | Permitted in access-controlled audit logs if needed | Printing raw `Idempotency-Key` headers in unrestricted logs/monitoring. |
| URI encoding errors | Classify template/invalid input errors | Logging raw queries containing PII or secrets directly. |

### 19.1. Why templates form the boundary of metric cardinality

Suppose the application calls:

```text
GET /v1/products/PRD-107?lang=vi
GET /v1/products/PRD-108?lang=vi
GET /v1/products/PRD-109?lang=en
```

If a meter tags the **full URL**, every product, page, and filter spawns a new time series. If it tags **`/v1/products/{id}`**, requests group cleanly by operation for meaningful error rates and latencies. Verify in runtime whether HTTP client observations are active; not every custom request factory/connector emits full tags automatically.

A safe observability pattern is assigning a **fixed operation name** in the adapter, such as `catalog.get_product`. Keep correlation IDs in access-controlled traces/logs and URI templates in metrics. Never place `Authorization`, `Cookie`, `X-API-Key`, or raw queries into trace attributes.

### 19.2. Testing instrumentation is part of the operational contract

In an app using Boot's `RestClient.Builder`/`WebClient.Builder`, add an integration test sending a request to MockWebServer and asserting the actual metric/observation in a test registry. If metrics are missing:

- Actuator/Micrometer dependencies may be missing.
- The client may have been built directly with `RestClient.create()`, bypassing observation customizers.
- Transport/connector-specific metrics may not be enabled or may use different names in your version.
- Instrumentation may have been replaced when customizing builders, filters, or request factories.

Do not invent high-cardinality meters to "compensate" for a missing metric. Stick to a bounded tag set, standard tracing, and consistent redaction policies.

## 20. Implementation checklist for base URL, URI, query, and headers

Before deploying an HTTP adapter to production, verify:

1. **Base URL:** sourced from per-partner environment/secret config; scheme/host/port allowlisted; never accepts arbitrary outbound URLs from HTTP callers?
2. **Client ownership:** `RestClient`/`WebClient`/HTTP interface is a single-created bean using the proper builder/config, with per-partner qualifiers and credentials?
3. **Path prefix:** if base contains a prefix, URI joining rules are standardized and verified on your exact Spring Framework version?
4. **URI templates:** path variables use `pathSegment`/templates where appropriate; never concatenate `"/orders/" + orderId` from raw input?
5. **Encoding:** raw vs. pre-encoded ownership is explicit; `/`, `+`, `%`, `?`, `#`, spaces, and Unicode tested without double-encoding?
6. **Query semantics:** repeated params, optional/empty/absent handling, sort/page-size bounds, date/time, numeric formatting, and canonicalization match the API contract?
7. **Default headers:** contain only stable client-wide values; never hold short-lived tokens or tenant-specific state?
8. **Per-request headers:** `Authorization`, correlation/trace, `Idempotency-Key`, `If-Match`, and `Accept-Language` come from trusted sources without duplicates?
9. **Media types:** `Accept` (response) and `Content-Type` (request body) distinguished; JSON/XML/problem responses properly mapped?
10. **Security:** policies and tests cover SSRF, redirects, cross-origin token forwarding, post-decode path traversal, header injection, and query PII?
11. **Retries/idempotency:** side-effecting POST/PATCH never retried blindly; stable business keys, reconciliation, and inbox/outbox when crossing DB/brokers?
12. **Integration:** Spring Integration/Kafka/RabbitMQ forward metadata to HTTP via allowlist rather than copying raw inbound `MessageHeaders`/`Authorization`?
13. **Caching:** cache keys and TTLs incorporate query, language, permissions, and relevant `Vary` dimensions?
14. **Testing:** unit tests cover raw URI encoding, repeated/optional queries, real HTTP request-targets, headers, dynamic credentials, redirects, 4xx/5xx, and timeouts?
15. **Observability:** metrics keyed by template/operation without raw URLs/IDs/sensitive headers; correlation and error taxonomy suffice to isolate faults?

**Takeaway:** **Base URL** anchors the destination, **URI builders/templates** build structurally valid paths and queries, and **headers** express media types, authentication, tracing, conditional writes, and idempotency. All three layers must be configured **consistently with clear ownership**: inputs are data rather than URL syntax, client credentials never follow arbitrary hosts, and dynamic requests never mutate shared state. In Spring Boot Integration, accurate URLs and headers are not just about making HTTP calls succeed—they underpin data contracts, safe retries, context-aware caching, duplicate-free messaging, and end-to-end observability across HTTP, databases, brokers, and Spring Integration.

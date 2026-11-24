# Building URIs with UriBuilder and encoding parameters properly

## 1. Why use a URI builder?

A Spring WebFlux application often builds URLs from a base URL, path, query parameters, and values supplied by users or systems. For example:

~~~text
https://api.example.test/v1/search/C%2B%2B?tag=reactive%20webflux&page=2
~~~

When building a URI, two things need to be solved:

1. Assembling the scheme, host, port, path, query, and fragment properly.
2. Encoding each value according to the exact URI component so data does not inadvertently become a delimiter.

If you concatenate strings manually, a value like `C++ & Java` can break the query structure because `&` normally separates query parameters. A path value containing `/` can create an extra segment. A `#` character can start a fragment, causing the trailing part not to be sent to the server.

Spring provides these APIs:

- **`UriBuilder`**: an interface describing how to build a URI.
- **`UriComponentsBuilder`**: an implementation for assembling scheme, host, path, query, fragment, and URI variables.
- **`UriBuilderFactory`**: a factory that creates UriBuilders with shared configuration.
- **`DefaultUriBuilderFactory`**: the default implementation, based on UriComponentsBuilder and configurable with an encoding mode.
- **`WebClient`**: the reactive HTTP client, supporting URI templates and UriBuilder.

**Principle:** keep the URI template fixed in code, pass dynamic data as URI variables, and let the builder encode them per component. Do not concatenate input into a full URL and hope a parser will guess your intent.

## 2. URI structure according to RFC 3986

A general URI has the structure:

~~~text
scheme://userinfo@host:port/path?query#fragment
~~~

Example:

~~~text
https://alice@example.test:8443/v1/orders/42?status=PAID&page=2#details
~~~

| Component | Example | Meaning |
| --- | --- | --- |
| Scheme | `https` | Protocol |
| User info | `alice` | User info in authority; credentials should rarely be put in a URL |
| Host | `example.test` | Target host |
| Port | `8443` | Connection port |
| Path | `/v1/orders/42` | Resource path |
| Query | `status=PAID&page=2` | Query parameters |
| Fragment | `details` | Location inside the resource on the client side; not sent in an HTTP request |

Not every URI has all components. A relative URI may contain only path and query, for example `/orders/42?expand=items`.

### 2.1. Unreserved and reserved characters

RFC 3986 divides important characters into two groups.

**Unreserved** consists of letters, digits, and:

~~~text
- . _ ~
~~~

**Reserved** consists of:

~~~text
:/?#[]@!$&'()*+,;=
~~~

Reserved characters can act as delimiters or carry special meaning in a URI:

- `/` separates path segments.
- `?` starts the query.
- `#` starts the fragment.
- `&` commonly separates query parameters.
- `=` commonly separates query name and value.
- `;` can separate subcomponents in some URIs.
- `+` is a reserved character in the sub-delimiters group.

A reserved character does not always have to be encoded. If it is acting as a delimiter in the template, keep it as is. If that same character is **data of a variable**, encode it so it does not alter the URI structure.

For example, `&` in a query template is a delimiter:

~~~text
/search?q={term}&page={page}
~~~

But if `term` has the value `java & reactor`, the `&` inside the data must become `%26`.

### 2.2. Percent-encoding

Percent-encoding represents an octet with three characters:

~~~text
%HH
~~~

`HH` is the two hexadecimal digits of the byte. Example:

| Data | Percent-encoding |
| --- | --- |
| Space | `%20` |
| `&` | `%26` |
| `+` | `%2B` |
| `/` in an opaque path variable | `%2F` |
| `#` in data | `%23` |
| `%` literal | `%25` |

Non-ASCII characters are usually encoded from **UTF-8 bytes**, not from a Unicode code point into a single hex number. For example, `é` has UTF-8 bytes `C3 A9`, so it is represented as `%C3%A9`.

### 2.3. Encoding is not encryption

Percent-encoding is only a way to represent data in a URI. It does not hide passwords, tokens, or personal information. URLs can appear in browser history, proxy logs, access logs, tracing, and cache keys. Do not put credentials or sensitive data in query/path just because they have been percent-encoded.

## 3. Encoding per URI component

A character may be valid in one component yet be a delimiter in another component.

~~~text
Path:  /files/a%2Fb.txt
Query: ?q=C%2B%2B%20Java%26Spring
~~~

| Data to pass | Location | Representation |
| --- | --- | --- |
| `report 2026.pdf` | A path segment | `report%202026.pdf` |
| `folder/a.txt` | An opaque path variable | `folder%2Fa.txt` if it needs to remain one segment |
| `C++ & Java` | Query value | `C%2B%2B%20%26%20Java` |
| `a=b` | Query value | `a%3Db` if `=` is data |
| `x#section` | Query value | `x%23section` |
| `100%` | Query value | `100%25` |

Do not use `URLEncoder` to encode an entire URI. `URLEncoder` is designed for `application/x-www-form-urlencoded`, commonly used for form data. It represents spaces with `+`, whereas regular URI percent-encoding uses `%20`. Applying it to a whole URL can also turn structural delimiters `/`, `?`, and `&` into data and corrupt the URI.

## 4. Distinguishing path, pathSegment, and queryParam

### 4.1. path and pathSegment

`path(String)` appends a path fragment. It fits application-controlled path templates:

~~~java
builder.path("/v1/orders/{orderId}");
~~~

`pathSegment(String...)` adds each segment separately:

~~~java
builder.pathSegment("v1", "files", "{fileName}");
~~~

If a dynamic value contains a slash, `pathSegment` helps express that the value belongs to a single segment. With strict encoding, a slash in a variable can be encoded as `%2F`.

Do not do this:

~~~java
String url = "/files/" + userSuppliedName;
URI uri = URI.create(url);
~~~

If `userSuppliedName` is `a/b.txt?download=true`, the input can alter the path or query structure.

Prefer:

~~~java
URI uri = UriComponentsBuilder.fromPath("/files/{name}")
        .encode()
        .buildAndExpand(userSuppliedName)
        .toUri();
~~~

Or:

~~~java
URI uri = UriComponentsBuilder.fromUriString("https://api.example.test")
        .pathSegment("files", "{name}")
        .encode()
        .buildAndExpand(userSuppliedName)
        .toUri();
~~~

**Note on encoded slashes:** proxies, gateways, and servers may decode `%2F` before routing. If an identifier genuinely needs to contain a slash, test the entire HTTP path; you may choose a Base64URL ID or a query parameter to avoid depending on how infrastructure handles it.

### 4.2. queryParam and queryParams

`queryParam(name, value...)` adds one or more values for a query key:

~~~java
builder.queryParam("page", "{page}")
       .queryParam("tag", "{tag1}", "{tag2}");
~~~

The result looks like:

~~~text
?page=2&tag=spring&tag=reactive
~~~

Values with the same name can repeat. The target API must interpret multi-value semantics properly.

Related APIs:

- `queryParam(name, values...)`: adds values.
- `queryParamIfPresent(name, Optional)`: adds only when the Optional has a value.
- `replaceQueryParam(name, values...)`: replaces existing values for the key.
- `queryParams(MultiValueMap)`: adds query parameters from a multi-value map.

Do not concatenate query strings manually:

~~~java
String query = "?q=" + term + "&page=" + page;
~~~

Use the builder to keep keys/values clear and apply encoding in the right places.

### 4.3. fragment

`fragment(value)` builds the fragment part:

~~~java
URI uri = UriComponentsBuilder.fromUriString("https://example.test/docs")
        .fragment("install")
        .build()
        .toUri();
~~~

The displayed URI is `https://example.test/docs#install`. The fragment is not sent in the HTTP request; it mainly serves client-side handling or referencing a position in a document.

## 5. UriComponentsBuilder: building a URI from a template

Basic example:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://example.com/hotels/{hotel}")
        .queryParam("q", "{q}")
        .encode()
        .buildAndExpand("Westin", "123")
        .toUri();
~~~

Process:

1. `fromUriString` creates a builder from a URI template.
2. `queryParam` adds a query component and placeholder.
3. `encode()` requests encoding the template first, then strictly encoding URI variables during expansion.
4. `buildAndExpand` replaces placeholders with actual values.
5. `toUri()` creates a `java.net.URI`.

You can use a map so variable names are clearer:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://example.com/hotels/{hotel}")
        .queryParam("q", "{q}")
        .encode()
        .buildAndExpand(Map.of(
                "hotel", "Westin",
                "q", "foo+bar"))
        .toUri();
~~~

This snippet requires importing `java.util.Map`. Spring also lets you shorten this with `build(...)`:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://example.com/hotels/{hotel}")
        .queryParam("q", "{q}")
        .build("Westin", "123");
~~~

If you want the encoding policy to be clearly visible in code reviews, the `encode().buildAndExpand(...).toUri()` chain is easier to spot.

### 5.1. Do not mix data into the template

The template is an application-controlled structure:

~~~text
https://api.example.test/v1/customers/{customerId}/orders
~~~

Dynamic value:

~~~text
customerId = "A/B?C"
~~~

Keeping template and values separate lets the builder treat `/`, `?` in the template as syntax, and `/`, `?` in values as data to encode.

Do not build a template by inserting untrusted input into the string:

~~~java
// Avoid: input has become part of the template.
String template = "/search/" + userInput + "?page={page}";
~~~

Instead:

~~~java
URI uri = UriComponentsBuilder.fromPath("/search/{term}")
        .queryParam("page", "{page}")
        .encode()
        .buildAndExpand(userInput, page)
        .toUri();
~~~

## 6. Two encoding approaches of UriComponentsBuilder and UriComponents

This is the most important difference when working with URI variables.

1. **`UriComponentsBuilder.encode()`**: encodes the template first, then strictly encodes URI variables upon expansion.
2. **`UriComponents.encode()`**: expands variables first, then encodes each component according to the characters disallowed in that component.

### 6.1. Builder encode before expand

~~~java
URI strict = UriComponentsBuilder.fromPath("/codes/{value}")
        .encode()
        .buildAndExpand("A;B")
        .toUri();
~~~

Result:

~~~text
/codes/A%3BB
~~~

`;` is data of the `value` variable, so it is encoded as `%3B`. This approach treats URI variables as **opaque data**: values are not allowed to alter the URI structure.

This is the right choice for most cases of passing IDs, search terms, customer codes, filter strings, or user data.

### 6.2. Component encode after expand

~~~java
URI componentEncoded = UriComponentsBuilder.fromPath("/codes/{value}")
        .buildAndExpand("A;B")
        .encode()
        .toUri();
~~~

Result:

~~~text
/codes/A;B
~~~

The `;` character is valid in the path component and is preserved. This approach is useful when a URI variable intentionally contains reserved characters with component structural meaning.

| Variable value in path | Builder encode before expand | Component encode after expand |
| --- | --- | --- |
| `A B` | `A%20B` | `A%20B` |
| `A;B` | `A%3BB` | `A;B` |
| `A/B` | `A%2FB` | `A/B` if slash belongs to path syntax after expansion |
| `A?B` | `A%3FB` | `A%3FB` because `?` is invalid as path segment data |
| `A#B` | `A%23B` | `A%23B` |

With `A/B`, the difference is especially important: after expansion, a slash can become a segment delimiter. If the variable must be an opaque value, use builder `encode()` before expansion or `pathSegment(...)`.

**Recommendation:** default to `UriComponentsBuilder.encode()` before expansion. Encode after expansion only when the URI contract genuinely needs reserved characters preserved inside a component and you have tested how the server parses it.

## 7. DefaultUriBuilderFactory and EncodingMode

`DefaultUriBuilderFactory` provides one place to configure a shared base URL and encoding strategy. It is used by `WebClient` and other Spring HTTP clients via `UriBuilderFactory`.

Four main modes:

| EncodingMode | How it works | When to consider |
| --- | --- | --- |
| `TEMPLATE_AND_VALUES` | Encodes the template first and strictly encodes variables during expansion | Fits most dynamic values |
| `VALUES_ONLY` | Does not encode the template; strictly encodes URI variables before expansion | The template is already controlled/specially formatted |
| `URI_COMPONENT` | Expands first, encodes each component afterward | When reserved characters in a variable must be kept if valid |
| `NONE` | Does not encode automatically | Use only when the caller already creates properly encoded URIs |

In Spring Framework 7.0.8, `WebClient` uses `TEMPLATE_AND_VALUES` by default through `DefaultUriBuilderFactory`. If an application uses multiple clients, different Spring versions, or needs an explicit contract, configure the mode explicitly.

Example:

~~~java
DefaultUriBuilderFactory factory =
        new DefaultUriBuilderFactory("https://api.example.test");

factory.setEncodingMode(
        DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

URI uri = factory.uriString("/search/{term}")
        .queryParam("q", "{q}")
        .build("C++ & Java", "reactive webflux");
~~~

The factory holds the base URL and encoding preferences. When multiple services call the same API, they can share a factory or use it to configure a common WebClient.

**Do not pick `NONE` just to avoid `%25` or `%2F`.** If the output is wrong, check whether input was pre-encoded, which component is being built, and which encoding mode is being applied.

## 8. WebClient: passing URI variables properly

`WebClient` supports several ways to supply a URI:

- A URI template string together with variables.
- An already-built `URI`.
- A function taking `UriBuilder` and returning `URI`.

Template usage:

~~~java
Mono<ProductPage> response = webClient.get()
        .uri("/products/{category}?page={page}",
                category, page)
        .retrieve()
        .bodyToMono(ProductPage.class);
~~~

UriBuilder function usage:

~~~java
Mono<ProductPage> response = webClient.get()
        .uri(builder -> builder
                .path("/products/{category}")
                .queryParam("q", "{q}")
                .queryParam("page", "{page}")
                .build(category, searchTerm, page))
        .retrieve()
        .bodyToMono(ProductPage.class);
~~~

The second approach is convenient when there are many query parameters, optional parameters, or conditional URI structures.

Configuring an encoding factory:

~~~java
DefaultUriBuilderFactory factory =
        new DefaultUriBuilderFactory("https://api.example.test");

factory.setEncodingMode(
        DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

WebClient webClient = WebClient.builder()
        .uriBuilderFactory(factory)
        .build();
~~~

Usage:

~~~java
Mono<String> result = webClient.get()
        .uri(builder -> builder
                .path("/search/{term}")
                .queryParam("page", "{page}")
                .build(searchTerm, page))
        .retrieve()
        .bodyToMono(String.class);
~~~

These are illustrative snippets in a service; `webClient`, response types, input values, and Spring WebFlux dependencies need to be declared. `WebClient` is designed to be non-blocking and uses Reactor to compose requests/responses; building URIs properly does not require calling `block()`.

If you pass an already-built `java.net.URI` to the client API, the caller must ensure the URI already has proper encoding. Do not re-encode a complete URI if the `%HH` sequences are already valid octet escapes.

## 9. Query parameters: plus signs, spaces, and URLEncoder

### 9.1. `+` is not a universal URI space representation

In generic URI syntax, `+` is a reserved sub-delimiter. In some query decoding rules under `application/x-www-form-urlencoded`, `+` is interpreted as a space.

Therefore:

- Literal data `C++` should be represented as `C%2B%2B` when the builder strict-encodes variables.
- A space in a generic URI component is represented as `%20`.
- Form encoding can represent a space as `+`.

Do not assume every server, framework, or decoder handles `+` the same way. When a plus sign is data, encoding it as `%2B` avoids having a form decoder turn it into a space.

### 9.2. URLEncoder is for form encoding

Java example:

~~~java
String encoded = URLEncoder.encode(
        "C++ & Java",
        StandardCharsets.UTF_8);
~~~

Result:

~~~text
C%2B%2B+%26+Java
~~~

The `+` in this output represents a space under form encoding. It is not how to encode a URI path segment, nor is it an operation for encoding an entire URL.

Use `URLEncoder` when you genuinely need values per the `application/x-www-form-urlencoded` contract. With Spring's URI builder, use `queryParam` and URI variables.

### 9.3. Query values containing `&`, `=`, `#`

Suppose you search by the string:

~~~text
C++ & Spring=WebFlux #1
~~~

If concatenated manually:

~~~text
/search?q=C++ & Spring=WebFlux #1
~~~

The URL may be parsed wrongly:

- `&` may open the next query parameter.
- `#` starts the fragment; the trailing part is not sent to the server.
- `=` may be interpreted as a key/value separator.
- `+` may be interpreted as a space by a form decoder.

Using the builder:

~~~java
URI uri = UriComponentsBuilder.fromPath("/search")
        .queryParam("q", "{q}")
        .encode()
        .buildAndExpand("C++ & Spring=WebFlux #1")
        .toUri();
~~~

The query value is encoded so those characters remain data of a single parameter.

## 10. Multiple query values, Optional, and empty query parameters

### 10.1. Multiple values with the same key

~~~java
URI uri = UriComponentsBuilder.fromUriString("https://api.example.test/products")
        .queryParam("tag", "{first}", "{second}")
        .encode()
        .buildAndExpand("spring", "reactive")
        .toUri();
~~~

The result looks like:

~~~text
https://api.example.test/products?tag=spring&tag=reactive
~~~

This is a repeated-key query. The target API may interpret it as a list of two values. If the contract requires comma-separated or JSON, encode per that contract rather than altering the structure yourself.

### 10.2. Optional parameter

When a query parameter should be present only if an Optional contains a value, you can use `queryParamIfPresent`:

~~~java
Optional<String> status = Optional.of("PAID");

URI uri = UriComponentsBuilder.fromUriString("https://api.example.test/orders")
        .queryParamIfPresent("status", status)
        .build()
        .toUri();
~~~

If the Optional is empty, `status` is not added. Distinguish three cases:

| Construction | Meaning |
| --- | --- |
| Not adding the key | The parameter is not sent |
| `queryParam("q", "")` | Key `q` is present with an empty value |
| Placeholder `{q}` with null | Null semantics must be determined per API and builder; avoid letting null become implicit behavior |

Define the contract clearly for absent, empty, and null; they are not always equivalent.

### 10.3. Ordering and request signing

Normally a server should not depend on query parameter ordering. However, some request-signing APIs or caching systems may canonicalize queries according to specific rules.

If a request is signed:

- Follow the provider's canonicalization rules exactly.
- Specify key ordering, repeated keys, percent-encoding hex case, and how spaces are handled.
- Do not re-normalize or decode/re-encode the URI after signing.
- Use the same algorithm to generate the canonical URI and send the actual request.

A URI that is resource-equivalent can still have a different byte sequence and cause an HMAC signature to fail.

## 11. Double encoding: why does `%2F` turn into `%252F`?

Suppose the original data really is:

~~~text
a/b
~~~

If the builder strict-encodes a URI variable, the slash is encoded as `%2F`. This is the desired result when the slash belongs to the data.

But if you pass the **already-encoded** string `a%2Fb` into the builder as a raw value, the `%` character is also data and gets encoded as `%25`:

~~~text
a%252Fb
~~~

When decoded once, it becomes the string `a%2Fb`, not `a/b`. This is **double encoding**.

Rules:

1. Keep the original unencoded data in variables.
2. Call the builder once to produce an encoded URI.
3. Do not call URLEncoder or UriUtils encode before passing values to the builder.
4. Do not decode and re-encode repeatedly in interceptors/filters without a clear contract.
5. If the input is a complete already-encoded URI, treat it as a URI that needs parsing/validation rather than treating the whole string as a raw variable.

Do not fix double encoding by switching the mode to `NONE` without identifying the component and the data source. Doing so can open injection vulnerabilities into the URI structure.

## 12. Unicode and charsets

URIs transfer data as octets, so character encoding must be agreed upon. Spring URI builders use UTF-8 by default in standard examples; you can specify a charset via the appropriate encoding overload.

~~~java
URI uri = UriComponentsBuilder.fromPath("/search/{term}")
        .queryParam("q", "{q}")
        .encode(StandardCharsets.UTF_8)
        .buildAndExpand("Hồ Chí Minh", "cà phê sữa")
        .toUri();
~~~

Vietnamese characters are converted into UTF-8 bytes and then percent-encoded. Do not replace a Vietnamese character with a similar-looking ASCII character yourself; that is changing the data, not encoding it.

A few notes:

- Unicode normalization (NFC/NFD) can make strings look identical while having different bytes; if IDs or signatures depend on bytes, agree on normalization.
- Do not decode a URI before the parser splits components.
- Do not assume one `%HH` maps directly to one Unicode character; a UTF-8 code point can span multiple bytes.
- When displaying a URI to users, you can decode it for UI readability; when sending HTTP, keep the valid encoded URI form.

## 13. Reading existing URIs and parser types

`UriComponentsBuilder` supports an RFC-based parser and a WHATWG URL Standard-based parser. The RFC parser requires input conforming to RFC 3986 syntax and handles it strictly; the WHATWG parser is more lenient with some non-standard URLs browsers commonly accept.

In Spring Framework 7.0.8, `WebClient`, `RestClient`, and `RestTemplate` use the RFC parser by default. You can customize `UriBuilderFactory` if the application has a specific reason to use a different parser.

If parsing a user-supplied URI:

1. Parse into a URI structure.
2. Check allowed schemes, usually `https` or a very small set of schemes.
3. Check host, port, and path against policy.
4. Do not believe that successful parsing means the URL is safe.
5. When sending a request from the server, check network destinations and redirects per SSRF policy.

Do not accept a full user-controlled URL, merely call `UriComponentsBuilder.fromUriString(...)`, and send it. The parser helps read the structure; **it does not decide which hosts the application is allowed to connect to**.

## 14. Security: encoding does not replace validation and SSRF protection

### 14.1. SSRF when the host is client-controlled

A feature such as a webhook, image import, or fetch URL may let the client enter a URL. If the server calls that URL, an attacker can try to access internal services, localhost, metadata endpoints, or private addresses.

**Percent-encoding does not prevent SSRF.** The builder can produce a syntactically completely valid URI while the host is still a disallowed target.

If the business logic only allows calling certain services:

- Do not accept an entire URL if unnecessary.
- Accept an identifier or a hostname restricted by an allowlist.
- Have the application choose the scheme, port, and base path itself.
- Validate DNS resolution and allowed IPv4/IPv6 addresses.
- Control redirects so they do not transition to another host/address outside policy.
- Apply the same policy to retries, proxies, and fallbacks.

### 14.2. Open redirect

If a response returns `Location` based on a user-submitted URL, validate the host and scheme against an allowlist. Encoding the URL does not stop the browser from navigating to a malicious host.

### 14.3. Path traversal

If a path variable represents a filename, values such as `../secret.txt` or percent-encoded forms can become traversal after decoding at the server layer.

- Validate according to the business contract.
- Normalize paths at the filesystem boundary.
- Confine paths within the allowed root.
- Check symlinks and access permissions.
- Do not rely solely on `%2E` or `%2F` already being encoded.

### 14.4. Do not put secrets into URIs

Tokens, API keys, passwords, or personal data should not be placed in the query string. Use headers or body per the API standard. Percent-encoding does not protect them from access logs or history.

## 15. WebClient: service example calling an API with path and query variables

The following example illustrates building a request; it assumes a WebClient bean and a response type exist:

~~~java
public Mono<SearchResponse> search(
        String category,
        String term,
        int page) {

    return webClient.get()
            .uri(builder -> builder
                    .path("/v1/categories/{category}/search")
                    .queryParam("q", "{term}")
                    .queryParam("page", "{page}")
                    .build(category, term, page))
            .retrieve()
            .bodyToMono(SearchResponse.class);
}
~~~

With `category` and `term` supplied as input, the URI builder handles each variable per component. Do not concatenate term into the query string.

A shared client configuration:

~~~java
@Configuration
class PartnerClientConfiguration {

    @Bean
    WebClient partnerWebClient() {
        DefaultUriBuilderFactory factory =
                new DefaultUriBuilderFactory("https://partner.example.test");

        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

        return WebClient.builder()
                .uriBuilderFactory(factory)
                .build();
    }
}
~~~

This is a Spring Boot WebFlux configuration example, requiring imports for `Configuration`, `Bean`, `WebClient`, and `DefaultUriBuilderFactory`. Base URL is an application-controlled setting; do not take an entire user-submitted URL and attach it as the base URL.

## 16. Runnable Java 17+ program: observing URI builder output

The following program uses only the Spring Web module and does not need to run an HTTP server. It demonstrates:

1. Spaces, pluses, ampersands, and Unicode in path/query.
2. A slash inside a path segment value.
3. DefaultUriBuilderFactory with TEMPLATE_AND_VALUES.
4. The difference between encoding before expansion and encoding after expansion.
5. Double encoding when passing an already percent-encoded value into the builder.
6. The difference between URI percent-encoding and URLEncoder form encoding.

Requirements: **JDK 17+**, **Maven 3.6.3+**, **Spring Framework 7.0.8**. In a real project, use the Spring version line managed by the Spring Boot BOM if the application uses Boot.

Structure:

~~~text
uri-builder-demo/
  pom.xml
  src/main/java/example/uri/UriBuilderDemo.java
~~~

### 16.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>uri-builder-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
            <version>7.0.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 16.2. UriBuilderDemo.java

~~~java
package example.uri;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.net.URLEncoder;

import org.springframework.web.util.DefaultUriBuilderFactory;
import org.springframework.web.util.UriComponentsBuilder;

public final class UriBuilderDemo {

    private static void printAndCheck(
            String name, URI actual, String expected) {

        String value = actual.toASCIIString();

        if (!expected.equals(value)) {
            throw new AssertionError(
                    name + " expected=" + expected + ", actual=" + value);
        }

        System.out.println(name + "=" + value);
    }

    public static void main(String[] args) {
        // 1) Strict encoding of path and query variables.
        URI search = UriComponentsBuilder
                .fromPath("/hotel list/{city}")
                .queryParam("q", "{q}")
                .encode()
                .buildAndExpand("New York", "foo+bar & café")
                .toUri();

        printAndCheck(
                "search",
                search,
                "/hotel%20list/New%20York?q=foo%2Bbar%20%26%20caf%C3%A9");

        // 2) A slash inside a path-segment variable is encoded as data.
        URI file = UriComponentsBuilder
                .fromUriString("https://api.example.test/v1")
                .pathSegment("files", "{fileName}")
                .encode()
                .buildAndExpand("guide 1/2.pdf")
                .toUri();

        printAndCheck(
                "file",
                file,
                "https://api.example.test/v1/files/guide%201%2F2.pdf");

        // 3) A shared UriBuilderFactory with an explicit encoding policy.
        DefaultUriBuilderFactory factory =
                new DefaultUriBuilderFactory("https://api.example.test");

        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

        URI fromFactory = factory.uriString("/search/{term}")
                .queryParam("tag", "{tag}")
                .queryParam("page", "{page}")
                .build("C++ & Java", "spring boot", 2);

        printAndCheck(
                "factory",
                fromFactory,
                "https://api.example.test/search/C%2B%2B%20%26%20Java"
                        + "?tag=spring%20boot&page=2");

        // 4) Strict variable encoding versus component encoding.
        URI strict = UriComponentsBuilder
                .fromPath("/codes/{value}")
                .encode()
                .buildAndExpand("A;B")
                .toUri();

        URI component = UriComponentsBuilder
                .fromPath("/codes/{value}")
                .buildAndExpand("A;B")
                .encode()
                .toUri();

        printAndCheck("strict", strict, "/codes/A%3BB");
        printAndCheck("component", component, "/codes/A;B");

        // 5) Passing an already encoded value encodes the percent sign again.
        URI doubleEncoded = UriComponentsBuilder
                .fromPath("/files/{name}")
                .encode()
                .buildAndExpand("a%2Fb")
                .toUri();

        printAndCheck("doubleEncoded", doubleEncoded, "/files/a%252Fb");

        // 6) URLEncoder is form encoding: a space becomes plus.
        String formEncoded = URLEncoder.encode(
                "C++ & Java", StandardCharsets.UTF_8);

        System.out.println("form=" + formEncoded);
    }
}
~~~

### 16.3. Running the program

From the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.uri.UriBuilderDemo
~~~

**Exact stdout of the program:**

~~~text
search=/hotel%20list/New%20York?q=foo%2Bbar%20%26%20caf%C3%A9
file=https://api.example.test/v1/files/guide%201%2F2.pdf
factory=https://api.example.test/search/C%2B%2B%20%26%20Java?tag=spring%20boot&page=2
strict=/codes/A%3BB
component=/codes/A;B
doubleEncoded=/files/a%252Fb
form=C%2B%2B+%26+Java
~~~

Interpretation:

- `search`: space becomes `%20`, `+` becomes `%2B`, `&` becomes `%26`, and `é` becomes `%C3%A9`.
- `file`: a slash inside a path-segment variable is encoded as `%2F`.
- `factory`: the factory uses TEMPLATE_AND_VALUES for path and query variables.
- `strict`: `;` in the variable is treated as data and encoded as `%3B`.
- `component`: encoding after expansion keeps `;` because that character is valid in the path component.
- `doubleEncoded`: `%` of the already-encoded string is encoded as `%25`, so `%2F` becomes `%252F`.
- `form`: URLEncoder represents space as `+`, following form encoding semantics.

The program does not send an HTTP request over the network. It tests how Spring builds URIs and verifies the output strings with assertions before printing.

## 17. Common mistakes and how to fix them

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Concatenating query strings with `+` | `&`, `#`, `=` can alter the structure | Use `queryParam` with URI variables |
| Concatenating user input into the path | A slash or `?` can create unintended segments/queries | Use `pathSegment` or a path template |
| Using URLEncoder for an entire URL | Structural delimiters `/`, `?`, `&` are turned into data | Use form encoding only for form values; use UriBuilder for URIs |
| Pre-encoding a value before passing to the builder | `%2F` becomes `%252F` | Pass the raw value and encode once |
| Using `URI_COMPONENT` without understanding reserved characters | `;`, `/`, or reserved chars may keep structural meaning | Use TEMPLATE_AND_VALUES when variables are opaque data |
| Using `NONE` to sidestep double encoding | Data characters can become delimiters | Find the source that pre-encoded it and fix at the boundary |
| Using `path()` with input containing slashes | Input may add path segments | Use `pathSegment()` and test encoded slashes across the entire infrastructure |
| Assuming `+` is always a space | A literal plus may be turned into a space | Encode literal plus as `%2B` |
| Thinking fragment `#details` is sent to the server | The fragment is not in the HTTP request | Use path/query/body per contract |
| Encoding the whole URI instead of each component | URI structure is broken | Build each component using the builder |
| Checking only whether the URL parses | The URL may still point to a disallowed host | Validate scheme, host, port, and destination policy |
| Treating percent-encoding as security | Sensitive data still appears in logs/history | Do not put secrets in URLs |
| Testing only ASCII URLs | Unicode and UTF-8 bugs are missed | Test Vietnamese and reserved characters |
| Not testing proxy/server decoding | `%2F` may be handled differently across layers | Integration test across the entire path |
| Normalizing the URI after signing | The request signature no longer matches | Canonicalize per contract before signing and send the same URI |

## 18. Verification checklist when a URI is wrong

When a request does not reach the right endpoint or the server receives the wrong value, check in this order:

1. **Print the final URI** with `toASCIIString()` in a test environment; do not log tokens or sensitive information.
2. **Split components** with `URI.getScheme()`, `getHost()`, `getPath()`, `getRawPath()`, `getQuery()`, and `getRawQuery()`.
3. **Check the template**: are dynamic variables placed as placeholders?
4. **Check builder placement**: was the path variable added with `pathSegment`? Was the query added with `queryParam`?
5. **Check the encoding mode**: TEMPLATE_AND_VALUES, VALUES_ONLY, URI_COMPONENT, or NONE?
6. **Check raw input**: was the value already encoded before entering the builder?
7. **Check UTF-8**: does the server decode with the same charset and same normalization?
8. **Check the network path**: does a proxy/gateway decode `%2F`, normalize dot-segments, or rewrite the query?
9. **Check the server contract**: does the server accept repeated keys, empty values, and pluses per the expected semantics?
10. **Check signing/caching** if the URI participates in canonical requests or cache keys.

A URI printed accurately on the client does not guarantee proxies and servers handle it the same way. For characters with structural impact such as `%2F`, `%2E`, and `%25`, test from the client to the real server.

## 19. Checklist before putting a URI builder into production

- [ ] Base URL, scheme, host, and port come from trusted configuration or a destination allowlist.
- [ ] Path/query templates are written in code or controlled.
- [ ] All dynamic data is passed via URI variables.
- [ ] Path values use `pathSegment` when they must stay within a single segment.
- [ ] Queries are built with `queryParam`/`queryParams`.
- [ ] The encoding mode is understood and consistent.
- [ ] Raw data is encoded only once.
- [ ] Literal `+` is encoded as `%2B` when it is data.
- [ ] Spaces, `&`, `=`, `#`, `%`, `/`, and Unicode have tests.
- [ ] Repeated query keys, empty parameters, and absent parameters match the contract.
- [ ] Do not put tokens/passwords/PII in URIs.
- [ ] User-controlled URLs are checked for SSRF, redirects, and destinations.
- [ ] Encoded slashes/path traversal are tested across proxies/servers.
- [ ] Request signing and cache canonicalization use the same URI rules.

## 20. Self-check

**Question 1.** Why should `?q=` not be concatenated with an arbitrary search string?

Because the string can contain `&`, `#`, `=`, or other reserved characters that alter the query structure. Use `queryParam("q", "{q}")` and pass the value separately.

**Question 2.** How do `UriComponentsBuilder.encode()` and `UriComponents.encode()` differ?

Builder encode encodes the template first and strictly encodes URI variables during expansion; component encode happens after expansion and can preserve reserved characters that are valid in the component.

**Question 3.** When a path variable contains `A;B`, why does TEMPLATE_AND_VALUES produce `A%3BB`?

Because `;` belongs to the variable's data and is strictly encoded so it does not carry reserved meaning in the path.

**Question 4.** Why does `URLEncoder.encode("A B", UTF_8)` return `A+B`?

Because URLEncoder uses `application/x-www-form-urlencoded` semantics, in which spaces are represented with `+`. Regular URI percent-encoding uses `%20`.

**Question 5.** If the original value is `a/b`, what does strict-encode builder produce when it is a path variable?

`a%2Fb`, so that the slash belongs to the variable's data rather than acting as a path delimiter.

**Question 6.** Why can passing `a%2Fb` into the builder produce `a%252Fb`?

Because `%` is treated as a data character and encoded as `%25`; the builder does not know the string was already encoded beforehand.

**Question 7.** Is the fragment `#details` sent to the server in an HTTP request?

No. The fragment is a client-side locator and is not part of the request target sent to the server.

**Question 8.** What can WebClient share a UriBuilderFactory for?

To share the base URL, encoding mode, and URI preparation options across requests.

**Question 9.** Does using UriBuilder automatically prevent SSRF if the host is sent by the client?

No. The builder creates a syntactically valid URI; the application still has to validate scheme, host, port, DNS/addresses, and redirects per policy.

**Question 10.** When is an integration test for encoded slashes needed?

When a path variable can contain slashes or encoded data; proxies, gateways, and servers may decode/normalize differently before routing.

## 21. Official references

- [Spring Framework — URI Links (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/uri-building.html): UriComponentsBuilder, UriBuilderFactory, parser types, and the two levels of URI encoding.
- [Spring Framework — UriComponentsBuilder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html): API for building, expanding, encoding, and creating URIs.
- [Spring Framework — UriBuilder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriBuilder.html): path, pathSegment, queryParam, build, and URI variables.
- [Spring Framework — DefaultUriBuilderFactory JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/DefaultUriBuilderFactory.html): EncodingMode and configuring UriBuilderFactory.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): configuring uriBuilderFactory for WebClient.
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986.html): reserved/unreserved characters, URI components, and percent-encoding.
- [Java 17 — URLEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html): form URL encoding and charsets.
- [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): destination allowlist, URL checking, and redirect control when the server calls external URLs.

**Key takeaway:** Use `UriComponentsBuilder` or `UriBuilderFactory` to assemble URIs component by component. Keep templates fixed, pass raw values via URI variables, choose an explicit encoding mode, and encode exactly once. Use `pathSegment` for data belonging to one segment, `queryParam` for query values, distinguish `%20` from `+`, and validate destinations separately when users influence URLs.
# UriComponentsBuilder: Building Paths, Parameters, and URI Templates in Spring MVC

## 1. The problem: why shouldn't you concatenate URLs as strings?

A Spring MVC application often needs to construct URIs for many tasks:

- Returning a `Location` header when `POST` successfully creates a new resource.
- Generating pagination, search, filter, sort links, and repeated parameters.
- Filling `{id}`, `{slug}`, `{version}` into a URI template.
- Creating links that accurately reflect the scheme, host, port, and context path when the application sits behind a reverse proxy.
- Encoding data containing Vietnamese characters, spaces, `+`, `&`, `/`, or `#` in the proper context.
- Migrating from `/api/v1` to `/api/v2` without duplicating URL-building logic across dozens of controllers.

If you concatenate strings:

```java
// ANTI-EXAMPLE: unencoded input that can break the URI structure.
String url = "https://api.example.test/search?q=" + keyword
        + "&page=" + page;
```

with `keyword="C++ & Spring"`, the result contains `&`, causing the query to split into unintended extra parameters. With a keyword containing `#`, everything after that sign may be interpreted as a URI fragment and not sent to the server. If arbitrary input is used to build the path or host, the consequences are even more severe (path manipulation, open redirect, SSRF, authorization boundary confusion).

Spring provides `org.springframework.web.util.UriComponentsBuilder`: a structured builder that understands scheme, authority, path, path segments, query parameters, fragment, and **URI template variables**. Instead of concatenating directly, model each component, choose a consistent encoding strategy, and only grant host/path control to trusted input.

**Scope:** Spring Framework Web 6.1.x, Spring MVC Servlet stack, Java 17, and Spring Boot 3.3.5. This lesson belongs to the **URI and API Versioning** group. The examples present API/syntax compatible with the Spring 6.1 branch; differences in WebFlux or Spring 7 should be reviewed separately.

### Learning objectives

1. Understand URI structure, absolute/relative URIs, and the meaning of reserved characters.
2. Know how to use `newInstance()`, `fromUriString()`, `fromPath()`, and `fromUri()`.
3. Distinguish between `path()` and `pathSegment()`, and append vs. replace.
4. Use `queryParam()`, `queryParams()`, `replaceQueryParam()`, and `queryParamIfPresent()`.
5. Know when to use `encode()`, `build()`, `buildAndExpand()`, `toUri()`, and `toUriString()`.
6. Use `ServletUriComponentsBuilder` for the `Location` header in Spring MVC.
7. Self-test bytes/percent-encoding, URI templates, and host/query input security.

## 2. What components make up a URI?

Consider an illustrative URI:

```text
https://api.example.test:8443/api/v1/books/42?lang=vi&page=2#reviews
└─┬─┘ └────────┬────────┘└───────┬───────┘└───────┬─────┘└─┬───┘
scheme       authority           path             query     fragment
```

- **Scheme**: `https` identifies the URI protocol.
- **Authority**: host `api.example.test` and port `8443`. Some URIs also include user-info, but never put credentials in a URL.
- **Path**: hierarchical string `/api/v1/books/42`. The `/` character separates segments.
- **Query**: `lang=vi&page=2`, which can contain multiple values for the same key.
- **Fragment**: `reviews`; in standard HTTP, the fragment is **not sent in the request target** to the server. Browsers use the fragment for client-side navigation.

An **absolute** URI has a scheme (e.g., `https://api.example.test/api/v1/books/42`); a **relative reference** URI such as `/api/v1/books/42` has no scheme/host and is resolved relative to a base URI. Choose the form that matches the contract: `Location` can be a valid URI reference, whereas links in API documentation may need an absolute URL so clients can call them directly.

**A URI is not necessarily an Internet URL.** A URI can use another scheme (e.g., `mailto:`); here we focus on HTTP/HTTPS and REST paths. A URI-building library does not verify that the actual endpoint exists or that the user has permission to access it.

### Reserved characters and percent encoding

Certain characters have structural roles:

| Character | Possible role | Risk if data is concatenated directly |
| --- | --- | --- |
| `/` | Separates path segments | An ID `a/b` is interpreted as two segments |
| `?` | Starts the query | Data may be treated as a query |
| `&` | Usually separates query parameters | A search term splits into parameters |
| `=` | Usually separates query name and value | Query structure deviates from intent |
| `#` | Starts the fragment | The query/path portion after `#` may not reach the server |
| `+` | Valid in query per URI spec, but often decoded as space by form decoders | `C++` may turn into `C  ` |
| `%` | Starts a percent-encoded octet | Easy double encoding if encoded multiple times |
| `;` | Reserved, meaningful in some path contexts | Template variables may change semantics |

**Percent encoding** represents bytes as `%HH`, e.g., space → `%20`, `&` inside a strictly encoded query value → `%26`, and `+` → `%2B`. For Unicode text, first encode to UTF-8 and then percent-encode the corresponding bytes. Do not use `URLEncoder` for an entire URL: that API serves `application/x-www-form-urlencoded`, so spaces usually become `+`, which is not how a multi-component URI is constructed.

## 3. What is UriComponentsBuilder?

The central class is `org.springframework.web.util.UriComponentsBuilder`, which creates a **mutable** builder. You initialize it, modify each component, and then build the URI.

Typical factories:

```java
UriComponentsBuilder.newInstance();
UriComponentsBuilder.fromUriString("https://api.example.test");
UriComponentsBuilder.fromPath("/api/v1/books");
UriComponentsBuilder.fromUri(URI.create(
        "https://api.example.test/api/v1/books"));
```

These are **snippets** requiring imports `org.springframework.web.util.UriComponentsBuilder` and `java.net.URI`. The builder has methods:

```java
scheme("https")
host("api.example.test")
port(8443)
path("/api/v1/books")
pathSegment("api", "v1", "books", "{id}")
queryParam("lang", "vi")
replaceQueryParam("page", 2)
fragment("reviews")
encode()
build()
buildAndExpand(...)
toUriString()
```

The list above shows **method names called on the builder**, not a standalone Java program, and not all of them are called sequentially on a real URL. `build()` returns `UriComponents`; `toUriString()` returns a string; `toUri()` on `UriComponents` returns `java.net.URI` for use with `ResponseEntity.location(...)`.

### Structured example instead of string concatenation

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .pathSegment("api", "v1", "books", "{id}")
        .queryParam("lang", "vi")
        .encode()
        .buildAndExpand(Map.of("id", 42L))
        .toUri();
```

Imports:

```java
import java.net.URI;
import java.util.Map;
import org.springframework.web.util.UriComponentsBuilder;
```

Resulting URI:

```text
https://api.example.test/api/v1/books/42?lang=vi
```

`{id}` is a placeholder; `buildAndExpand(Map.of("id",42))` fills in the value before generating the URI. When the author wants links for different resources, only the data changes, not the template literal.

**`Map.of(...)` requires Java 9+**; the examples in this lesson use Java 17, so it is valid.

## 4. path() and pathSegment(): the most important difference

### 4.1. path(): appending a path part that already carries structure

`path(String)` **appends** the string to the existing path. It does not automatically add a `/` between every call:

```java
String path = UriComponentsBuilder
        .fromPath("/api")
        .path("/v1")
        .path("/books")
        .build()
        .toUriString();
```

Result:

```text
/api/v1/books
```

If you write `.path("v1")` right after `"/api"`, the strings can join into `/apiv1`, which differs from the intent. Therefore, for explicit path parts, the author must actively keep the `/`.

Spring has a step that normalizes some duplicate slashes in the full path, but you should not rely on it to automatically fix structurally broken URLs from untrusted sources.

### 4.2. pathSegment(): adding individual segments with separators

`pathSegment(String...)` appends segments and inserts the appropriate `/`:

```java
String path = UriComponentsBuilder
        .newInstance()
        .pathSegment("api", "v1", "books", "42")
        .build()
        .toUriString();
```

Result:

```text
/api/v1/books/42
```

Empty segments can be ignored. When a value **is truly a single segment**, `pathSegment` models the intent better than `path`.

### 4.3. Data containing slashes

An identifier with content `a/b` may mean **one ID**, not two path levels. Use a strictly encoded template variable:

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .pathSegment("api", "v1", "files", "{key}")
        .encode()
        .buildAndExpand(Map.of("key", "a/b"))
        .toUri();
```

The typical result is:

```text
https://api.example.test/api/v1/files/a%2Fb
```

The `/` inside a **variable value** is percent-encoded as `%2F`, without opening an additional path segment. In real HTTP configurations, a reverse proxy, Servlet container, or firewall may **reject/decode encoded slashes** differently; producing a URI containing `%2F` does not guarantee the endpoint receives the ID `a/b` intact across every infrastructure. If an opaque ID often contains slashes, consider a URL-safe identifier or move it into the query/body per contract.

A static `pathSegment("a/b")` also has the semantics of encoding the slash in the segment when the builder encodes. **Do not treat percent-encoding as input validation or authorization**: path segments still need business rule and security checks.

### 4.4. replacePath() instead of path()

`path("/v2")` **appends** to the existing path; `replacePath("/v2")` **replaces the entire path**.

```java
String replaced = UriComponentsBuilder
        .fromUriString("https://api.example.test/old/path")
        .replacePath("/api/v2/books")
        .build()
        .toUriString();
```

Result:

```text
https://api.example.test/api/v2/books
```

This is especially useful when keeping the host/scheme of a trusted URI while needing to point to a specific path. However, if the original URI has unwanted query or fragment parts, replacing the path **does not automatically clear** the query/fragment; use `replaceQuery(null)` and `fragment(null)` when a clean target is needed.

## 5. Query parameters: adding, replacing, removing, and repeated values

### 5.1. queryParam() adds a parameter

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/api/v1/books")
        .queryParam("page", 2)
        .queryParam("size", 20)
        .queryParam("sort", "createdAt,desc")
        .encode()
        .build()
        .toUri();
```

Expected URI:

```text
https://api.example.test/api/v1/books?page=2&size=20&sort=createdAt,desc
```

A comma is an allowed character in some query contexts; whether valid reserved characters are kept or percent-encoded varies depending on the encoding choice. Do not hardcode expected raw text for every reserved character without determining the strategy. The numeric parts `page=2`/`size=20` have clear semantics.

**Important:** `queryParam("page",2)` adds a value. If the builder already has `page=1`, adding `page=2` can produce **two** params `page=1&page=2` instead of overriding; use `replaceQueryParam()` to replace.

### 5.2. replaceQueryParam() and removal

```java
String result = UriComponentsBuilder
        .fromUriString("https://api.example.test/books?page=1&legacy=true")
        .replaceQueryParam("page", 3)
        .replaceQueryParam("legacy")
        .build()
        .toUriString();
```

Result:

```text
https://api.example.test/books?page=3
```

- `replaceQueryParam("page",3)` replaces old values of the same key.
- `replaceQueryParam("legacy")` with no value **removes that key**.
- `replaceQuery(String)` replaces the **entire query**, while `replaceQuery(null)` removes the query; `query(String)` appends/parses query text.
- `replaceQueryParams(MultiValueMap<String,String>)` can replace the entire set of query params.

### 5.3. A parameter with multiple values

An HTTP query can repeat a key:

```text
?tag=java&tag=spring
```

In the builder:

```java
List<String> tags = List.of("java", "spring");

URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/books")
        .queryParam("tag", tags)
        .encode()
        .build()
        .toUri();
```

Result:

```text
https://api.example.test/books?tag=java&tag=spring
```

This is a snippet importing `java.util.List` and `java.net.URI`. The `queryParam(String, Collection<?>)` overload lets you pass multiple values under the same name. When a Spring MVC controller receives them, `@RequestParam List<String> tag` can be used, though the server needs a clear contract for duplicate values and ordering if filtering depends on them.

### 5.4. queryParamIfPresent() for Optional

```java
Optional<String> language = Optional.of("vi");

String uri = UriComponentsBuilder
        .fromPath("/api/v1/books")
        .queryParamIfPresent("lang", language)
        .build()
        .toUriString();
```

Result:

```text
/api/v1/books?lang=vi
```

If the Optional is empty, `lang` is not added. There can be different null/empty semantics between omitting the param, `?lang`, and `?lang=`; choose according to the API contract instead of assuming they are identical. `queryParam("flag")` with no values creates a parameter with a name and no equals sign.

### 5.5. queryParams() with MultiValueMap

When many keys/values are already available in Java:

```java
MultiValueMap<String, String> params =
        new LinkedMultiValueMap<>();
params.add("tag", "java");
params.add("tag", "spring");
params.add("page", "2");

URI uri = UriComponentsBuilder
        .fromPath("/api/v1/books")
        .queryParams(params)
        .encode()
        .build()
        .toUri();
```

Imports:

```java
import java.net.URI;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.util.UriComponentsBuilder;
```

Described URI:

```text
/api/v1/books?tag=java&tag=spring&page=2
```

`MultiValueMap` differs from `Map<String,String>`: one key can have multiple values. For pagination APIs, if page/sort is server-controlled, do not automatically accept and forward **every** user query param from the previous request; filter with an allowlist to avoid duplicate tokens or unwanted filters.

## 6. URI template: placeholders and expanding data

### 6.1. Template variables in path

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .path("/api/{version}/books/{id}")
        .encode()
        .buildAndExpand(Map.of(
                "version", "v1",
                "id", 42))
        .toUri();
```

Result:

```text
https://api.example.test/api/v1/books/42
```

In `buildAndExpand(Map)`, variable names must match the names in the template. Missing a variable can lead to an exception during expansion. `buildAndExpand(Object...)` also has a positional form: values are used in the order variables appear. When a template has many variables, **Map helps avoid ordering mistakes**.

A variable can appear multiple times:

```java
URI uri = UriComponentsBuilder
        .fromPath("/api/{version}/reports/{version}")
        .encode()
        .buildAndExpand(Map.of("version", "v2"))
        .toUri();
```

Result:

```text
/api/v2/reports/v2
```

### 6.2. Template variables in query

**Recommended approach for user data containing reserved characters:** make the **query value a template variable**, enable `builder.encode()`, and then expand. For example:

```java
String term = "C++ & Spring";

URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .path("/api/v1/books")
        .queryParam("q", "{q}")
        .queryParam("page", 2)
        .encode()
        .buildAndExpand(Map.of("q", term))
        .toUri();
```

Result:

```text
https://api.example.test/api/v1/books?q=C%2B%2B%20%26%20Spring&page=2
```

Here:
- `C++` → `C%2B%2B`.
- Space → `%20`.
- `&` inside the search term → `%26`, **not** split into a separate query parameter.
- The `&` between `q` and `page` is preserved as the **separator created by the template/builder**.

### 6.3. Why can queryParam("q", term).encode() behave differently?

For example:

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/search")
        .queryParam("q", "C++")
        .encode()
        .build()
        .toUri();
```

Notably, `+` **is allowed in the URI query component**, so the builder's regular encoding method does not necessarily replace a literal `+` with `%2B`. In many server frameworks, query/form decoders can decode `+` into a space. To avoid turning `C++` into `C  `, use a template variable `"{q}"` and `builder.encode().buildAndExpand(...)` to strict-encode dynamic data.

**Do not assume `queryParam()` automatically treats every reserved character as plain text**. It organizes components; the encoding strategy determines the final bytes. This is the most important point when sending user queries, especially `+`, `&`, `=`, `;`.

### 6.4. encode() before build and encode() after build

Spring has two encoding paths:

1. `UriComponentsBuilder.encode()`: pre-encodes the **URI template** and **strictly encodes URI variables upon expansion**. In particular, reserved characters that carry meaning inside **variable values** are also percent-encoded.
2. `UriComponents.encode()`: encodes **components after variables have been expanded**; it mainly encodes invalid/non-ASCII characters, while potentially keeping reserved characters that are valid in that component position.

Conceptual example:

```java
URI strict = UriComponentsBuilder
        .fromPath("/books/{key}")
        .encode()
        .buildAndExpand("a;b")
        .toUri();

URI componentOnly = UriComponentsBuilder
        .fromPath("/books/{key}")
        .buildAndExpand("a;b")
        .encode()
        .toUri();
```

With the strict-encoding path, `;` in the variable can become `%3B`; with component-level encoding, `;` which is valid in a path may be preserved. This rule is explained in Spring's URI Encoding documentation. **Prefer builder-level encode when values are opaque data**; choose component-level when you intentionally allow reserved characters that carry structural meaning.

### 6.5. Avoiding double encoding

If `id` is already `"a%2Fb"` but you treat it as **raw data** and strict-encode it, `%` can become `%25`, producing `"a%252Fb"`. When the client/server decodes it, it may receive a different value than intended.

Set a clear rule:
- For normal user input, store **un-percent-encoded data**, then encode exactly once when building the URI.
- For a URI that is **already fully encoded**, use the APIs intended for encoded/raw components according to the contract, avoiding a second encoding pass.
- Do not use arbitrary decode-reencode on user-supplied URLs as a security mechanism; it can open the door to bypassing multiple layers of encoding.

## 7. build(), build(true), toUri(), and toUriString()

### 7.1. Common steps

```java
UriComponentsBuilder builder =
        UriComponentsBuilder.fromPath("/api/v1/books/{id}");

UriComponents components = builder
        .encode()
        .buildAndExpand(42);

URI uri = components.toUri();
String text = components.toUriString();
```

Imports:

```java
import java.net.URI;
import org.springframework.web.util.UriComponents;
import org.springframework.web.util.UriComponentsBuilder;
```

Both `uri` and `text` represent the URI `/api/v1/books/42`. When passing a URI to `ResponseEntity.location(URI)`, use the `URI` object instead of manually assembling the `Location` header as a String.

`toUriString()` on the builder can follow a different internal build/encode path when URI template variables have been/are being declared; therefore **choose one clear pipeline and test tricky characters** rather than mixing multiple encode/build calls.

### 7.2. build(true) is not a security mode

`build(true)` tells Spring that the components are already encoded. It is appropriate when the builder is initialized from a URI already in raw/encoded form:

```java
URI original = URI.create(
        "https://api.example.test/search?q=C%2B%2B");

URI copied = UriComponentsBuilder
        .fromUri(original)
        .build(true)
        .toUri();
```

The logical result remains:

```text
https://api.example.test/search?q=C%2B%2B
```

**Warning from the Spring 6.1 Javadoc:** `fromUri(URI)` expects components in **fully encoded/raw form**. If you modify this builder, any added values must also adhere to that encoded state (for example, using `UriUtils` for the corresponding component). Do not add an unencoded string to a raw builder and then call `build(true)` or blindly encode the whole thing again. If you want to construct a **new URI from raw data**, initializing from a known template and strict-encoding variables is usually much less error-prone.

### 7.3. toUri() vs. toASCIIString()

`URI.toString()` represents the URI as a Java String; `URI.toASCIIString()` can escape non-ASCII characters when an ASCII representation is needed. When generating an HTTP `Location`, Spring/the HTTP layer will use the `URI` object and appropriate encoding; do not try to “decode so the URI looks pretty” before sending. In tests, `URI.getRawPath()` and `URI.getRawQuery()` are useful for asserting percent encoding; `getPath()`/`getQuery()` may decode, which is suitable for logic checks but does not directly detect double encoding in the raw string.

## 8. Fragments and queries do not live in the same processing layer

Adding a fragment:

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://docs.example.test/guide")
        .queryParam("lang", "vi")
        .fragment("examples")
        .encode()
        .build()
        .toUri();
```

URI:

```text
https://docs.example.test/guide?lang=vi#examples
```

When a browser visits it, the `#examples` part is normally handled on the client and **is not sent to the Spring MVC server** in the HTTP request target. Therefore, do not build routing or security assuming the server receives the URL fragment. The server must use path/query/headers/body to receive necessary information.

If a fragment is provided by a client and may contain reserved characters, it also needs appropriate encoding/validation. Fragments are useful for deep links in documentation/SPAs, not for securely sending passwords/tokens: they still appear in browser history, client-side logs, extensions, or shared URLs.

## 9. ServletUriComponentsBuilder: building Location with the right context path

`UriComponentsBuilder` takes a base provided by code; whereas `org.springframework.web.servlet.support.ServletUriComponentsBuilder` can extract scheme, host, port, path, and query from the currently processed **HttpServletRequest**.

Spring MVC 6.1 factories worth remembering:

| Factory | What information does it take? | Use when |
| --- | --- | --- |
| `fromCurrentContextPath()` | Scheme, host, port, **context path** | Building a URI for another resource in the same application |
| `fromCurrentServletMapping()` | Context path and servlet mapping if present | App has a custom DispatcherServlet mapping |
| `fromCurrentRequestUri()` | Scheme, host, port, **request URI path**, no query | Appending a sub-segment to the current resource |
| `fromCurrentRequest()` | Same as above, **including query string** | Wanting to preserve the current query and edit/add params |
| `fromRequestUri(request)` | From HttpServletRequest, no query | When an explicit request object is available |
| `fromContextPath(request)` | From request object, context root only | Creating an absolute link to a different endpoint |

Example for request `POST https://example.test/app/api/v1/books?draft=true`:

- `fromCurrentContextPath()` starts from `https://example.test/app`.
- `fromCurrentRequestUri()` starts from `https://example.test/app/api/v1/books` (does not keep `draft=true`).
- `fromCurrentRequest()` still includes `?draft=true`; if you append path `/{id}` without replacing the query, `draft` remains — which may not be the right URI for the newly created resource.

Therefore, to build `Location` for a new resource, `fromCurrentContextPath().pathSegment("api","v1","books","{id}")` is usually the most explicit, or use `fromCurrentRequestUri().path("/{id}")` when the mapping aligns. **Do not blindly attach a raw `Host` header or client-provided origin URL as an absolute redirect** without a trust boundary.

### Why is this important with server.servlet.context-path?

If the application runs at `/catalog` instead of `/`, a hardcoded URI `http://localhost:8080/api/v1/books/42` will omit the `/catalog` prefix. `ServletUriComponentsBuilder.fromCurrentContextPath()` reads the request's context path to produce `http://localhost:8080/catalog/api/v1/books/42` when the application receives a request in that context.

In a gateway/reverse proxy environment, the public path might be `/public-api`; in that case, proper forwarded-headers handling must be configured, not just the internal context path.

## 10. Complete runnable Maven Spring Boot 3.3.5 example

This application provides:

- `POST /api/v1/books`: creates a book in memory, returning `201 Created` and `Location` pointing to the book.
- `GET /api/v1/books/{id}`: reads the newly created book.
- `GET /api/v1/links/search?q=...`: builds a search URL containing a strictly encoded template query value.
- `GET /api/v1/links/category?value=a/b`: a category ID containing a slash must become `a%2Fb` in a single path segment.
- `GET /api/v1/links/tags?tag=java&tag=spring`: builds a URI with duplicate query keys.
- `GET /api/v1/links/page`: replaces an existing query param using `replaceQueryParam`.

Data is kept in memory; restarting the server loses the data. There is no database, Spring Security, or reverse proxy integration; the purpose is to verify URI construction.

### 10.1. Project tree

```text
uri-builder-demo/
├── pom.xml
└── src/
    ├── main/java/demo/uri/
    │   ├── UriBuilderApplication.java
    │   └── BookController.java
    └── test/java/demo/uri/
        └── BookControllerTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>uri-builder-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/uri/UriBuilderApplication.java`**

```java
package demo.uri;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UriBuilderApplication {
    public static void main(String[] args) {
        SpringApplication.run(UriBuilderApplication.class, args);
    }
}
```

### 10.2. Controller with URI templates, query params, and Location

**`src/main/java/demo/uri/BookController.java`**

```java
package demo.uri;

import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/api/v1")
public class BookController {

    public record CreateBookRequest(String title) {}
    public record Book(long id, String title) {}
    public record LinkResponse(String url) {}

    private final AtomicLong ids = new AtomicLong();
    private final Map<Long, Book> books = new ConcurrentHashMap<>();

    @PostMapping("/books")
    public ResponseEntity<Book> create(
            @RequestBody CreateBookRequest input) {

        if (input == null || input.title() == null
                || input.title().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Title is required");
        }

        Book book = new Book(
                ids.incrementAndGet(), input.title().strip());
        books.put(book.id(), book);

        URI location = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .pathSegment("api", "v1", "books", "{id}")
                .encode()
                .buildAndExpand(Map.of("id", book.id()))
                .toUri();

        return ResponseEntity.created(location).body(book);
    }

    @GetMapping("/books/{id}")
    public Book find(@PathVariable long id) {
        Book book = books.get(id);
        if (book == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Book not found");
        }
        return book;
    }

    @GetMapping("/links/search")
    public LinkResponse search(@RequestParam String q) {
        URI uri = UriComponentsBuilder
                .fromUriString("https://api.example.test")
                .pathSegment("api", "v1", "books")
                .queryParam("q", "{q}")
                .queryParam("page", 2)
                .encode()
                .buildAndExpand(Map.of("q", q))
                .toUri();

        return new LinkResponse(uri.toASCIIString());
    }

    @GetMapping("/links/category")
    public LinkResponse category(@RequestParam String value) {
        URI uri = UriComponentsBuilder
                .fromUriString("https://api.example.test")
                .pathSegment("api", "v1", "categories", "{category}")
                .encode()
                .buildAndExpand(Map.of("category", value))
                .toUri();

        return new LinkResponse(uri.toASCIIString());
    }

    @GetMapping("/links/tags")
    public LinkResponse tags(@RequestParam List<String> tag) {
        URI uri = UriComponentsBuilder
                .fromUriString("https://api.example.test")
                .pathSegment("api", "v1", "books")
                .queryParam("tag", tag)
                .encode()
                .build()
                .toUri();

        return new LinkResponse(uri.toASCIIString());
    }

    @GetMapping("/links/page")
    public LinkResponse changePage() {
        URI uri = UriComponentsBuilder
                .fromUriString(
                        "https://api.example.test/books?page=1&legacy=true")
                .replaceQueryParam("page", 3)
                .replaceQueryParam("legacy")
                .build()
                .toUri();

        return new LinkResponse(uri.toASCIIString());
    }
}
```

**Key points to understand:**

1. `@RestController` returns JSON; therefore `LinkResponse` is an object with a `url` field, not a view name or redirect.
2. `create()` writes a `Book` to `ConcurrentHashMap`; `AtomicLong` is only for generating IDs in the demo, not a persistent ID strategy.
3. `ResponseEntity.created(location)` produces HTTP `201 Created` + `Location`. There is no need to concatenate strings into the header manually and do not use 302 for a REST resource creation contract.
4. `ServletUriComponentsBuilder.fromCurrentContextPath()` obtains the request's scheme/host/port/context path when running in Spring MVC, so it is more accurate than hardcoding a `localhost` origin in the book creation endpoint.
5. `search` uses `queryParam("q","{q}")` and `encode()` **before expanding**, so `C++ & Spring` is placed into **one query value** properly.
6. `category` shows `a/b` inside a single path segment as `a%2Fb`; the example returns a link string and does not require the Servlet container to accept/route encoded-slashes in the path to run the demo.
7. `tags` illustrates repeated query keys. With multiple values, `queryParam(String, Collection)` avoids manually joining `tag=java,spring`.
8. `changePage` shows `replaceQueryParam` replacing `page` and removing `legacy`. Do not use `queryParam("page",3)` here because it would append a duplicate.
9. The domain `api.example.test` is used for **illustrative links, not a real Internet endpoint**. Clients should not attempt to fetch it in the demo; the app running on localhost simply returns strings for testing.
10. Dynamic URLs in the API currently only take input to generate text, not to fetch or redirect to external hosts. If changed to make HTTP calls, an SSRF allowlist/network policy must be added; encoding alone is insufficient.

### 10.3. Running and observing

In the `uri-builder-demo` directory containing `pom.xml`, use JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

These are two commands run **sequentially**. With the default configuration, the application listens on `localhost:8080`.

**Create a book:**

```bash
curl -i -X POST 'http://localhost:8080/api/v1/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Spring Web"}'
```

First response when the server has just started and has no books yet:

```http
HTTP/1.1 201
Location: http://localhost:8080/api/v1/books/1
Content-Type: application/json

{"id":1,"title":"Spring Web"}
```

`Location` may reflect the actual origin/context path of the HTTP request; if behind a reverse proxy, the public scheme/host depends on the forwarded headers policy. On a freshly started server, the first ID is 1; then 2, 3... (not reset within the same JVM).

**Read the newly created book:**

```bash
curl -i 'http://localhost:8080/api/v1/books/1'
```

Expected body:

```json
{"id":1,"title":"Spring Web"}
```

**Search with reserved characters:**

```bash
curl -G -i 'http://localhost:8080/api/v1/links/search' \
  --data-urlencode 'q=C++ & Spring'
```

Expected JSON body:

```json
{
  "url": "https://api.example.test/api/v1/books?q=C%2B%2B%20%26%20Spring&page=2"
}
```

`curl -G --data-urlencode` encodes the request sent to localhost, while the returned content is a URI built **again** by the server for the illustrative host. Do not concatenate URL query strings by writing `?q=C++ & Spring` on the client, because `+` and `&` will be misinterpreted.

**Path segment containing a slash:**

```bash
curl -G -i 'http://localhost:8080/api/v1/links/category' \
  --data-urlencode 'value=a/b'
```

Body:

```json
{
  "url": "https://api.example.test/api/v1/categories/a%2Fb"
}
```

**Repeated tags:**

```bash
curl -i 'http://localhost:8080/api/v1/links/tags?tag=java&tag=spring'
```

Body:

```json
{
  "url": "https://api.example.test/api/v1/books?tag=java&tag=spring"
}
```

**Replace query param:**

```bash
curl -i 'http://localhost:8080/api/v1/links/page'
```

Body:

```json
{
  "url": "https://api.example.test/books?page=3"
}
```

The illustrative output formats JSON nicely for readability; Jackson may return a single line and does not guarantee field order in large DTOs. The demo code here only has `url`, making it easy to verify.

### 10.4. Testing with MockMvc

**`src/test/java/demo/uri/BookControllerTest.java`**

```java
package demo.uri;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void searchQueryEncodesPlusAmpersandAndSpaces() throws Exception {
        mvc.perform(get("/api/v1/links/search")
                    .param("q", "C++ & Spring"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.url").value(
                "https://api.example.test/api/v1/books"
                + "?q=C%2B%2B%20%26%20Spring&page=2"));
    }

    @Test
    void categoryIsExactlyOneEncodedPathSegment()
            throws Exception {
        mvc.perform(get("/api/v1/links/category")
                    .param("value", "a/b"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.url").value(
                "https://api.example.test/api/v1/categories/a%2Fb"));
    }

    @Test
    void repeatedQueryValuesRemainRepeated()
            throws Exception {
        mvc.perform(get("/api/v1/links/tags")
                    .param("tag", "java", "spring"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.url").value(
                "https://api.example.test/api/v1/books"
                + "?tag=java&tag=spring"));
    }

    @Test
    void replaceQueryParamDoesNotAppendDuplicate()
            throws Exception {
        mvc.perform(get("/api/v1/links/page"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.url").value(
                "https://api.example.test/books?page=3"));
    }

    @Test
    void createdBookHasLocationPointingToGetResource()
            throws Exception {
        MvcResult created = mvc.perform(post("/api/v1/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Spring Web\"}"))
           .andExpect(status().isCreated())
           .andExpect(jsonPath("$.title").value("Spring Web"))
           .andReturn();

        String location = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);

        URI uri = URI.create(location);
        assertTrue(uri.getRawPath().matches(
                "/api/v1/books/[1-9][0-9]*"));

        mvc.perform(get(uri.getRawPath()))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.title").value("Spring Web"));
    }

    @Test
    void missingBookReturns404() throws Exception {
        mvc.perform(get("/api/v1/books/99999999"))
           .andExpect(status().isNotFound());
    }

    @Test
    void invalidTitleReturns400() throws Exception {
        mvc.perform(post("/api/v1/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"   \"}"))
           .andExpect(status().isBadRequest());
    }
}
```

Run:

```bash
mvn test
```

The class has **7 test methods**. If all pass, Maven exits with code `0` and a summary similar to `Tests run: 7, Failures: 0, Errors: 0, Skipped: 0`. The tests verify percent encoding, repeated queries, query replacement, and `Location`. They use `MockMvc` without a real TCP server; they do not test forwarded-headers semantics when passing through a CDN/reverse proxy.

**Test design point:** The book creation test does not hardcode ID 1 because in-memory state can change when tests run in arbitrary order. It reads the actual `Location`, verifies the path starts with `/api/v1/books/` followed by a numeric ID, and then calls GET on that path. Thus the test protects the contract without depending on ordering.

## 11. MvcUriComponentsBuilder: links based on controller mappings

When an application has many controllers, writing the string `"/api/v1/books/{id}"` in multiple places easily drifts when refactoring `@RequestMapping`. Spring also provides `MvcUriComponentsBuilder` to build URIs from controller/method `@RequestMapping` metadata.

Conceptual **snippet** example:

```java
UriComponentsBuilder builder =
        MvcUriComponentsBuilder
                .fromMethodName(BookController.class, "find", 42L);
URI uri = builder.build().toUri();
```

This is **not code to add directly to the demo project without testing**: `MvcUriComponentsBuilder` imports and mapping/request context rules must match; method names/parameters can change during refactoring. In projects with controller type-level mappings, the method/call approach can help reduce hardcoding, but you must still verify context path, encoding, and forwarded headers. Depending on the `MvcUriComponentsBuilder` API, `fromMethodCall(on(...))` can be used when linking via a method proxy rather than just by method name.

**Do not use `MvcUriComponentsBuilder` as a way to bypass authorization**: it only helps generate links and does not guarantee the recipient of the link has permission to read the resource.

## 12. UriComponentsBuilder and API versioning

A REST API's URI can carry the version in the path such as `/api/v1/books` and `/api/v2/books`, or via headers/media types under another policy. When using path versioning:

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .pathSegment("api", "{version}", "books", "{id}")
        .encode()
        .buildAndExpand(Map.of("version", "v2", "id", 42))
        .toUri();
```

Result:

```text
https://api.example.test/api/v2/books/42
```

Do not take a version/path prefix directly from the client and concatenate it into a target host or redirect without validation. Systems usually have a fixed set of versions, e.g. `v1`/`v2`, which must be restricted to supported versions. Encoding does not prevent a client from choosing a **non-existent** version, does not restrict data exposure, and does not automatically transform schemas.

### Distinguishing base URL, API root, and resource route

A separation-of-concerns pattern:

- **Base origin**: `https://api.example.test`, determined by deployment config/trusted request metadata.
- **API root**: `/api/v1`, defined by routing/versioning policy.
- **Resource route**: `/books/{id}`, defined by the controller.
- **Query**: `?include=author&lang=vi`, determined by the contract and validated inputs.

When port/context path changes across dev, staging, and production, these parts should not be mixed together in business logic. Likewise, do not pass an unvalidated base origin into `UriComponentsBuilder.fromUriString(input)` because it can easily create phishing/SSRF links.

## 13. Reverse proxies, forwarded headers, and host-header security

An application running behind a load balancer:

```text
Client:
https://api.example.test/catalog/api/v1/books

Proxy forwards internally:
http://127.0.0.1:8080/app/api/v1/books
```

If the server takes scheme/host/port directly from the internal request, `Location` can become:

```text
http://127.0.0.1:8080/app/api/v1/books/42
```

instead of the desired public URL:

```text
https://api.example.test/catalog/api/v1/books/42
```

Spring supports `Forwarded` (RFC 7239), `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`, and `X-Forwarded-Prefix` to reconstruct the original URL; the Servlet stack has `ForwardedHeaderFilter` and Spring Boot has the `server.forward-headers-strategy` policy (chosen based on topology/hosting).

**Crucial security point:** These headers **can be spoofed by clients**. A reverse proxy at the trust boundary must **strip untrusted `Forwarded`/`X-Forwarded-*` headers** from the Internet and then set the proxy's own authoritative values. Do not blindly enable accepting forwarded headers just to make URLs in `Location` look right; without control, users can trick the server into building links/redirects to a fake host, enabling phishing or web cache poisoning.

### Example configuration to test

In a deployment with a trusted proxy that sanitizes forwarded headers, Spring Boot can be configured with:

```properties
server.forward-headers-strategy=framework
```

This is an **optional deployment configuration**, not required in the runnable project. It allows the framework to perform appropriate forwarded-header processing for the stack. Use it only after verifying ingress/proxy security policy and without configuring duplicate handling that yields wrong results.

When you do not want to trust forwarded headers but want to strip them, Spring's `ForwardedHeaderFilter` has a `removeOnly` mode. Actual deployment details vary by Servlet container, filter chain, and host allowlist policy.

### Host header injection

Even without forwarded headers, the host from an HTTP request is data influenced by the client/proxy. If you build an absolute `Location` or email/reset link directly from an unvalidated Host, phishing URLs can be generated. For critical callbacks/payments/emails, use a **canonical public base URL from trusted configuration** instead of an arbitrary request host, or apply a strict host/scheme allowlist.

## 14. A URI builder does not replace validation and destination encoding

### 14.1. SSRF

If the server receives:

```text
?callback=http://169.254.169.254/latest/meta-data/
```

and uses `UriComponentsBuilder.fromUriString(callback)` to build a URI and call an HTTP client to it, the builder does not prevent **SSRF**. You must restrict scheme, host, port, DNS resolution, redirects, internal addresses, and outbound network policy. If the builder is only used to format a URI and return text, no network request is made; the risk arises when the server **uses** the URI to access resources or redirect.

### 14.2. Open redirect

```java
// ANTI-EXAMPLE: do not return Location from a client-chosen URI.
@GetMapping("/go")
public String go(@RequestParam String next) {
    return "redirect:" + next;
}
```

This is **unsafe code** in `@Controller` if an allowlist is missing. Attackers can abuse a trusted endpoint to redirect browsers to a phishing page. Use server-controlled destination keys or allowlist paths/hosts, canonicalization, and origin policies. `UriComponentsBuilder.encode()` does not make a malicious host trustworthy.

### 14.3. Path traversal and encoded slashes

If an application builds URLs from a user's filename, encoding `/` may help preserve a segment, yet `..`/`%2e%2e` data and double-decoding differences between proxy/Servlet can still cause the path to be interpreted differently. Do not use a URI path directly as a filesystem path; map IDs to server-owned storage keys and verify authorization.

### 14.4. Query parameter pollution

If a builder accepts an existing query and calls `queryParam("role","viewer")`, a client might supply `role=admin&role=viewer`. Different frameworks/servers may pick the first, last, or list value. When overriding a server-controlled parameter, use `replaceQueryParam()` rather than appending; better yet, reconstruct the query from an allowlist.

### 14.5. Sensitive data in URIs

Query strings can appear in browser history, reverse proxy access logs, analytics, referrer headers in certain scenarios, and screenshots. Do not put passwords, bearer tokens, refresh tokens, session secrets, or unnecessary PII in the query just because `queryParam` can encode them. Encoding **ensures syntax**, not security encryption.

## 15. Common errors and how to diagnose them

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| `/apiv1` instead of `/api/v1` | `path("v1")` appends without a slash | Use `path("/v1")` or `pathSegment` |
| An ID `a/b` splits into two levels | Treating identifier as a raw path string | Use a template variable + strict encoding or URL-safe ID |
| `C++` is read as `C  ` | Literal `+` in query, form-decoded by server as space | Use `queryParam("q","{q}")`, `encode()`, then expand |
| Input `A&B` creates two query params | Concatenating raw input into `?q=...` | Builder + strict template variable encoding |
| `page` appears twice | `queryParam` appends instead of replacing | `replaceQueryParam("page",value)` |
| URL still keeps `legacy=true` | Only replaced path, did not clear query | `replaceQueryParam("legacy")` or `replaceQuery(null)` |
| URI has `%252F` instead of `%2F` | Encoding an already percent-encoded value | Standardize raw-data pipeline → encode once |
| `buildAndExpand` reports missing variable | `{id}` name missing from Map | Match template and keys, use a complete Map |
| Location lacks context path | Hardcoding `/api/v1` or wrong absolute URL | `ServletUriComponentsBuilder.fromCurrentContextPath()` |
| Location has `http://localhost:8080` in production | Reverse proxy not forwarding/handling origin metadata properly | Configure proxy, forwarded headers, or canonical base |
| Location points to unknown host | Trusting client `Host` or `X-Forwarded-Host` | Sanitize at trusted proxy, allowlist/canonical base |
| Broken query despite calling encode | `Builder.encode` does not strict-encode raw literal reserved chars | Put dynamic values into URI template variables |
| URI does not reach the right controller | Encoded slash arrived, but Servlet/proxy rejected it | Check path policy and use URL-safe IDs |
| URI loses fragment on server | Fragment is not sent in HTTP request | Do not expect `#...` in Spring MVC |
| Query link leaks token in logs | Queries are not for secrets | Use header/body/session per threat model |
| Link has valid URI but user is unauthorized | URI construction does not perform authorization | Check principal/resource/tenant |
| MockMvc tests pass, CDN URL is wrong | Forwarded headers/path rewrite differ at runtime | Integration tests at origin and public proxy |
| Reusing builder across requests accumulates query | Builder is mutable and shared/singleton | Create a new builder per request or use `cloneBuilder()` |
| Building URI from raw URL with unknown encode state | `fromUri(URI)` takes raw encoded components | Use `build(true)` per contract or build from a fresh template |

A debugging workflow:

1. Safely log the **URI template** and component names; do not log queries containing secrets.
2. Compare `URI.getRawPath()` / `getRawQuery()` against `getPath()` / `getQuery()` to check encoding.
3. Check whether input data is **raw or already encoded**; avoid encoding twice.
4. Confirm `pathSegment()` is used for identifiers that must stay a single segment.
5. For query values containing `+`, `&`, `#`, check strict variable encoding.
6. If duplicate keys occur, check `queryParam` vs. `replaceQueryParam`.
7. For `Location`, verify context path, public host, scheme, and forwarded headers at the trusted proxy.
8. Test the URI against both HTTP clients and the Servlet container because encoded-slash/path normalization may differ.
9. For links used in redirects/fetches, check the SSRF/open redirect allowlist.
10. When changing API versions, test both `v1`/`v2` and link consistency.

## 16. Pre-release checklist for APIs building dynamic URIs

1. URI base/scheme/host is controlled or validated against an allowlist.
2. Path prefix and version are governed by routing policy, not appended arbitrarily from client input.
3. Identifiers are placed into `{variables}` or `pathSegment`, not concatenated as arbitrary raw strings.
4. Dynamic query values use template variables with strict encoding when reserved characters may appear.
5. Server-controlled queries use replace rather than accidentally appending duplicates.
6. Already-encoded data is not passed through encoding again; clear rules exist for raw/encoded components.
7. Absolute `Location` or redirects respect context path and trusted proxy deployment.
8. Tests inspect raw percent-encoding of `+`, `&`, space, `/`, `%`, and Unicode.
9. Generating a link does not equate to granting resource access permissions.
10. Secrets are never placed in URI path/query/fragment.
11. The API distinguishes public versioned routes from personal data/cache behavior.
12. Forwarded headers and Host are never accepted unconditionally from clients.
13. Mutable singleton builders are not shared as state across requests.
14. Contract tests cover repeated, optional, missing/blank request parameters, and invalid inputs.
15. Switch to `MvcUriComponentsBuilder` only when refactor-safe mapping is needed and verified against the specific version/framework.

## 17. Self-check exercises

1. What path bug can `path("/api").path("v1")` produce? How is `pathSegment("api","v1")` different?
2. How do `queryParam("page",2)` and `replaceQueryParam("page",2)` differ when the query already has `page=1`?
3. How should a query value `C++ & Spring` be placed into a URI template and encoded?
4. Why is builder-level `encode()` usually more suitable than post-expansion `UriComponents.encode()` when URI variables are opaque data?
5. What encoding will `pathSegment("files","{id}")` with `id="a/b"` use? Is it guaranteed that all proxies accept encoded slashes?
6. What does `build(true)` mean? When should `fromUri(URI)` be used with extra care?
7. In which component does `ServletUriComponentsBuilder.fromCurrentRequest()` differ from `fromCurrentRequestUri()`?
8. When creating a REST resource, why is `201 Created` + `Location` usually better than a JSON response containing a manually concatenated URL string?
9. If a service runs behind a proxy, why might the generated `Location` use HTTP/localhost instead of public HTTPS?
10. Why should `X-Forwarded-Host` from the Internet not be trusted to construct absolute URIs?
11. Does the browser send a `URI fragment` in an HTTP request to Spring MVC?
12. Does `UriComponentsBuilder` prevent SSRF, open redirects, or path traversal if the client controls the host/path?
13. When should `queryParamIfPresent` be used? When should `queryParams(MultiValueMap)` be used?
14. Why does `UriComponentsBuilder` producing a valid URI not mean the path exists or the user has permission to access it?
15. When migrating `/api/v1` to `/api/v2`, at which layer should you manage the version so links remain consistent?

**Hints:** (1) It can produce `/apiv1`; `pathSegment` adds separators. (2) Append can create duplicates, while replace replaces all existing values. (3) Template `{q}` + encode before expand produces `C%2B%2B%20%26%20Spring`. (4) Strictly encodes reserved characters in data instead of letting them be parsed as structure. (5) `%2F`, though proxies/containers still have their own policies. (6) Marks components as already encoded; `fromUri` holds raw components. (7) The `Request` factory keeps the query, while `RequestUri` does not. (8) HTTP `Location` is the standard contract for locating the resource; easy to follow. (9) Missing/untrusted forwarded metadata and context mapping. (10) Spoofing the host leads to phishing. (11) No. (12) No; allowlist/auth/validation are required. (13) Optional params and multiple repeated values. (14) A URI is only a reference. (15) Routing/config/template/controller mapping under a clear policy.

## 18. References

- [Spring Framework 6.1 — UriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html)
- [Spring Framework — URI Links and URI Encoding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html)
- [Spring Framework 6.1 — UriBuilder API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/util/UriBuilder.html)
- [Spring Framework 6.1 — UriComponents API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/util/UriComponents.html)
- [Spring Framework 6.1 — ServletUriComponentsBuilder](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html)
- [Spring Framework — Forwarded Headers Security Considerations](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Spring Framework 6.1 — MvcUriComponentsBuilder](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/MvcUriComponentsBuilder.html)
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986.html)
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html)

**Summary:** `UriComponentsBuilder` helps build scheme, host, path, query, and URI templates **component by component**, avoiding error-prone string concatenation. `pathSegment` preserves the notion of a single segment; `queryParam` appends values while `replaceQueryParam` replaces/removes them; `builder.encode().buildAndExpand(...)` is well-suited for strictly encoding data variables, especially `+`, `&`, and `/`. In Spring MVC, `ServletUriComponentsBuilder` can construct the `Location` header from the request/context path, while proxy forwarded headers, host trust boundaries, authorization, and versioning policies still require independent control.

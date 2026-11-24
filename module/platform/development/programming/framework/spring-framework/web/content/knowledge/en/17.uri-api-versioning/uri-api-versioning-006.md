# API Versioning Strategies by Path, Header, Parameter, or Media Type in Spring MVC

## 1. Why is API versioning needed?

A web, mobile, or partner application may depend on a REST API contract for years. If an endpoint returned:

~~~http
GET /api/v1/customers/42 HTTP/1.1
Accept: application/json
~~~

~~~json
{"id":42,"fullName":"Nguyen An"}
~~~

and the server suddenly changed the JSON to:

~~~json
{"id":42,"givenName":"An","familyName":"Nguyen","active":true}
~~~

old clients could no longer read `fullName`. **API versioning** groups breaking changes into contracts that clients can select, while supporting v1 and v2 during a transition period.

The topic of this lesson is **the four places where a version can be expressed**:
1. **URI path:** `/api/v1/customers/42`.
2. **Request header:** `API-Version: 1`.
3. **Query parameter:** `/api/customers/42?version=1`.
4. **Media type:** `Accept: application/vnd.demo.customer.v1+json` or a media type parameter.

Each choice affects routing, API documentation, cache keys, CORS, proxies, client SDKs, and debugging. No single option is always best. **API version is not synonymous with JAR version, Spring Boot version, database migrations, or Git tags.** A single deployment can serve multiple API versions; a single API version can span many deployments.

### What will you learn?

- Distinguish breaking vs. non-breaking changes and version-bump policies.
- Compare path, header, query param, and media type by HTTP semantics.
- Configure `@GetMapping`/`@RequestMapping` on **Spring MVC 6.x** and test on **Spring Boot 3.3.5 / Java 17**.
- Distinguish `Accept` from `Content-Type`, `produces` from `consumes`, and mapping conditions from parameter binding.
- Understand that **Spring Framework 7** has native API versioning (`ApiVersionConfigurer`, `version` in mappings) which **does not exist in Spring 6.x**.
- Determine behavior on missing/unsupported versions, 400/404/406/415, error responses, and contract tests.
- Manage CDN caching, `Vary`, CORS preflight, authorization, migration/deprecation/sunset.

This lesson focuses on the **Spring MVC Servlet stack**, not Spring WebFlux. When upgrading framework versions, always consult the exact documentation for the Spring Framework/Spring Boot version used by your dependency manager.

## 2. What does an API contract include?

An API contract is not just JSON fields. It also includes:
- Resource URI, path variables, HTTP method, and action semantics.
- Request query/header/body, content type, validation, required/default values.
- Response field names, types, nullability, collection envelopes, timestamps, pagination, sorting.
- HTTP statuses, error codes, retry/idempotency rules.
- Authentication/authorization, ownership/tenant scoping, CORS/CSRF, and data protection.
- Business semantics: exchange rates, rounding rules, filtering semantics, point-in-time data.
- Operational behavior that can be contractual: rate limits, max page size, deprecation dates.

Thus renaming `fullName` is an obvious breaking change, yet changing a page index from zero-based to one-based can also break clients even when the JSON schema stays identical.

| Change | Typical assessment | Why |
| --- | --- | --- |
| Adding an optional JSON field | Usually compatible | Though strict deserializers may reject unknown fields |
| Renaming/removing a field | Breaking | Old clients no longer see the property |
| Changing a number to a string | Breaking or high risk | Type/format changes |
| Adding an enum value | Potentially breaking | Exhaustive client switches may fail |
| Adding a new endpoint | Usually compatible | Does not affect old endpoints unless conflicting |
| Changing default sort/filter/page size | Potentially breaking | Behavior changes |
| Replacing 200 + body with 204 | Potentially breaking | Clients expecting to parse a body |
| Requiring a new request header | Breaking | Old clients do not send it |
| Optimizing queries, swapping internal libraries | Usually non-breaking | If output/semantics do not change |
| Patching an authorization flaw in v1 | May impact clients | Never preserve a vulnerability just for compatibility |

**You do not need to bump the major API version for every added field**; use contract tests and the real consumer list to decide. Conversely, bumping the number to v2 does not automatically make v2 secure or business-correct.

### 2.1. Choosing a version representation

Some APIs use `1`/`2`, some use `1.0`/`1.1`, and some use dates like `2026-10-01`. You must define the format, parser, comparison rules, supported versions, and major/minor meaning. Do not compare `1.10` and `1.9` as floating-point numbers, and do not mix `v1` in headers with `1.0` in URLs without clear mapping rules.

## 3. Comparing the four approaches

| Criterion | Path | Header | Query param | Media type |
| --- | --- | --- | --- | --- |
| Example | `/api/v1/orders` | `API-Version: 1` | `?version=1` | `Accept: application/vnd.demo.v1+json` |
| Version visible directly in URL | Yes | No | Yes | No |
| Try with a plain browser URL | Easy | Requires setting header | Easy | Requires setting Accept |
| Gateway/LB routing by version | Very convenient | Must forward/read header | Must preserve query param | Must inspect Accept |
| Cache key by standard URI | Separate paths | Needs `Vary`/CDN key | Query is part of URI | Needs `Vary: Accept` |
| Browser CORS custom header | Not from version | Can trigger preflight | Not from version | Less often for valid Accept, subject to rules |
| OpenAPI/codegen tooling | Easy to split specs by base path | Must model header | Must model param | Must model media types |
| Drawbacks | Multiplies routes/links and URLs | Hidden from URL; CORS/proxies | Easy to omit; CDN may strip query | Negotiation and Accept tooling complexity |
| Strengths | Easy to operate and debug | Stable resource URIs | Shareable links | Version tied to representation |

**Selection hint:** for public APIs with many consumers/standard gateways, path major versioning is usually easiest to explain and operate. If you have a unified HTTP SDK and want stable URIs, headers are a reasonable choice. Query suits simple/transitional APIs with clear policies. Media type suits cases where versions mainly change **representations** and the system is already built around content negotiation.

Do not pick a strategy merely for fewer lines in a controller; consider supporting legacy v1 as well as client caching/CORS/debugging.

## 4. Strategy 1: version in the path

Example:

~~~text
GET /api/v1/customers/42
GET /api/v2/customers/42
~~~

Simple Spring MVC 6.x mapping:

~~~java
@RestController
@RequestMapping("/api/v1/customers")
class CustomerV1Controller {
    @GetMapping("/{id}")
    CustomerV1 find(@PathVariable long id) {
        return service.findV1(id);
    }
}
~~~

The v2 controller uses `@RequestMapping("/api/v2/customers")` and returns `CustomerV2`. This is a **fragment** referencing undefined service/DTO types; the full program is in section 9.

### Advantages

- The URL displays the version, easy to copy into curl/browsers/documentation.
- CDNs and reverse proxies see two distinct URIs; URL-based routing is explicit.
- v1 and v2 can be deployed to separate clusters or within the same application.
- Each version easily gets its own OpenAPI spec; links/`Location` are easy to verify.
- Easy to identify v1 consumers via path-aware metrics.

### Limitations

- Resource logic can be duplicated across multiple controllers and deep links.
- Upgrading clients usually have to change base paths and update SDKs.
- Having multiple URIs for the same resource requires deciding canonical links.
- v1 does not stay stable automatically if you modify DTOs or behavior inside the v1 controller.
- URL `/api/v99/...` may return 404 from normal routing rather than automatically returning 400 “unsupported version”.

When using path versioning, one major version in the base path usually suffices. Do not bump to `/v1.0.1` for every patch deployment if the old contract remains compatible.

## 5. Strategy 2: version in a request header

Client calls the same URL:

~~~http
GET /api/header/customers/42 HTTP/1.1
API-Version: 1
Accept: application/json
~~~

and the new version:

~~~http
GET /api/header/customers/42 HTTP/1.1
API-Version: 2
Accept: application/json
~~~

With **Spring 6**, place the version in the mapping condition:

~~~java
@GetMapping(path = "/api/header/customers/{id}",
            headers = "API-Version=1",
            produces = "application/json")
CustomerV1 readV1(@PathVariable long id) {
    return v1(id);
}

@GetMapping(path = "/api/header/customers/{id}",
            headers = "API-Version=2",
            produces = "application/json")
CustomerV2 readV2(@PathVariable long id) {
    return v2(id);
}
~~~

`headers="API-Version=1"` is used by Spring to **select the method**. It is completely different from:

~~~java
@RequestHeader("API-Version") String version
~~~

The parameter annotation only **reads the version after a handler has been selected**; it does not dispatch between v1/v2 methods.

### Advantages and trade-offs

Resource URIs stay stable, and HTTP SDKs can attach the version header automatically. However, the version is invisible in the URL, making it easy to miss when sharing links or testing manually. Gateways must forward the header, CORS must permit the custom header for cross-origin frontends, and cache keys must account for the version.

If public responses vary by `API-Version` on the same URL, consider:

~~~http
Cache-Control: public, max-age=60
Vary: API-Version
~~~

`Vary` informs HTTP caches that this header affects the representation. It is **not added automatically** just by using `@GetMapping(headers=...)` and **does not replace authorization**. If an endpoint returns personalized data, use `private` or `no-store` plus proper authentication/tenant scoping, not `Vary`, to protect secrets.

### CORS preflight

A browser frontend on `https://app.example.test` calls a cross-origin API and attaches `API-Version`:

~~~javascript
fetch("https://api.example.test/api/header/customers/42", {
  headers: { "API-Version": "2" }
});
~~~

Because custom headers are not CORS-safelisted request headers, browsers usually send a preflight:

~~~http
OPTIONS /api/header/customers/42 HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: api-version
~~~

The server must allow the origin/method/header in its **CORS policy**, and the actual request still undergoes authentication/authorization. A successful CORS preflight does not mean the version is valid or the user is allowed to read the data.

## 6. Strategy 3: version via query parameter

~~~text
GET /api/query/customers/42?version=1
GET /api/query/customers/42?version=2
~~~

Spring 6.x:

~~~java
@GetMapping(path = "/api/query/customers/{id}", params = "version=1")
CustomerV1 v1ByQuery(@PathVariable long id) {
    return v1(id);
}

@GetMapping(path = "/api/query/customers/{id}", params = "version=2")
CustomerV2 v2ByQuery(@PathVariable long id) {
    return v2(id);
}
~~~

`params` on `@GetMapping` is a **mapping condition**. `@RequestParam("version")` only binds the value inside an already-selected handler; it does not create two versions.

Advantages: easy for clients to run in browsers/curl, explicit version in links, no custom headers. However:
- Clients omitting or repeating `version` can cause unintended routing.
- URL query strings can be stripped/normalized during gateway rewrites.
- CDNs may be configured to **ignore query params** in cache keys, mixing `?version=1` and `?version=2`.
- If the URL also carries tokens/other PII, raw query logs are sensitive; avoid logging full URLs blindly.
- If `version` is also used as a domain query filter, rename to avoid collisions.

**Policies that must be defined:** is `version` required? Is there a fixed default? Is `v1` allowed or only `1`? Does an unknown version return 400 or 404? Are duplicate values `?version=1&version=2` rejected or normalized? Never rely on incidental handler-matching side effects instead of an explicit error contract.

## 7. Strategy 4: version via media type

### 7.1. Vendor media type in `Accept`

Request for v1:

~~~http
GET /api/media/customers/42 HTTP/1.1
Accept: application/vnd.demo.customer.v1+json
~~~

Request for v2:

~~~http
GET /api/media/customers/42 HTTP/1.1
Accept: application/vnd.demo.customer.v2+json
~~~

Spring MVC 6:

~~~java
@GetMapping(path = "/api/media/customers/{id}",
            produces = "application/vnd.demo.customer.v1+json")
CustomerV1 mediaV1(@PathVariable long id) {
    return v1(id);
}

@GetMapping(path = "/api/media/customers/{id}",
            produces = "application/vnd.demo.customer.v2+json")
CustomerV2 mediaV2(@PathVariable long id) {
    return v2(id);
}
~~~

`Accept` expresses the **desired representation from the server**, while `produces` lets Spring select the handler/converter and response `Content-Type`. With Jackson on standard Spring Boot Web, the `+json` suffix is supported for vendor media types.

### 7.2. Distinguishing `Accept`, `Content-Type`, `produces`, and `consumes`

| Element | Description | Typical usage |
| --- | --- | --- |
| `Accept` request header | What representation the client wants to **receive** | GET/POST/... |
| `Content-Type` request header | What format the client is **sending in the body** | POST/PUT/PATCH |
| `produces` mapping | Representation the server can return | Response negotiation |
| `consumes` mapping | Request body representation the server accepts | Request conversion |

Example POST versioned request:

~~~http
POST /api/media/customers HTTP/1.1
Content-Type: application/vnd.demo.customer.v2+json
Accept: application/vnd.demo.customer.v2+json

{"givenName":"An","familyName":"Nguyen"}
~~~

If the input contract also differs, matching DTOs and `consumes` are needed. Do not read `Content-Type` to decide the version of a bodyless GET. Mismatching `Accept` can result in 406 Not Acceptable; an unsupported body `Content-Type` usually yields 415 Unsupported Media Type.

### 7.3. Media type parameters rather than vendor suffixes

Another form:

~~~http
Accept: application/json;v=2
~~~

This is a **media type parameter `v=2`**, not a distinct subtype name `application/vnd.demo.customer.v2+json`. Spring Framework 7 supports dedicated resolvers for media type parameters. On Spring MVC 6.x, simply adding `produces="application/json;v=2"` without understanding media type matching may fail to distinguish every case, especially when requests omit the `v` parameter. Test thoroughly or use vendor media types as demonstrated for Spring 6.

### 7.4. Trade-offs and caching

Media type versioning enables multiple representations at one URI, fitting systems built around HTTP content negotiation. It is more complex for sharing links, managing `Accept` defaults, q-values, vendor types in proxies, OpenAPI/codegen, and CDNs. If public responses are cacheable under the same URI:

~~~http
Cache-Control: public, max-age=60
Vary: Accept
~~~

For personalized data, `Vary: Accept` does not replace `private/no-store` or user authorization. CORS has rules for safelisted `Accept` request headers; a conforming `Accept` header generally does not trigger preflight solely due to versioning, yet Fetch value/length constraints still apply, so do not claim every `Accept` header is “simple”.

## 8. Spring MVC 6.x: mapping conditions are not an API versioning system

Attributes available in Spring Framework 6.x:

~~~java
@GetMapping(
    path = "/api/customers/{id}",
    params = "version=1",
    headers = "X-Channel=mobile",
    produces = "application/json")
~~~

Requests must satisfy the corresponding conditions. This mechanism is very useful, yet **does not automatically provide**:
- An application-wide registry of supported versions.
- Semantic version parsing or baseline version routing.
- Uniform missing/unknown version handling across controllers.
- Automatic deprecation/sunset headers.
- Client compatibility, DTO conversion, or database migration.
- Per-version cache safety, CORS, authorization, or OpenAPI docs.

**Crucially important:** `@GetMapping(version="1.0")` and `WebMvcConfigurer.configureApiVersioning` are new APIs in **Spring Framework 7**. They **do not compile on Spring MVC 6.1/6.2** used by Spring Boot 3.x. Do not grab a Spring 7 snippet and try bumping only the `spring-webmvc` dependency in Boot 3: a compatible framework/platform stack is required.

## 9. Complete example: four strategies on Spring Boot 3.3.5

A sample application running Java 17, Spring MVC 6.1.x (managed by Boot 3.3.5), Gradle, and MockMvc. It uses response fixtures to **demonstrate version selection**, without a database or login security.

v1 contract:

~~~json
{"id":42,"fullName":"Nguyen An"}
~~~

v2 contract:

~~~json
{"id":42,"givenName":"An","familyName":"Nguyen","active":true}
~~~

Structure:

~~~text
api-version-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/apiversion/
    │   ├── ApiVersionDemoApplication.java
    │   └── web/CustomerVersionsController.java
    └── test/java/com/example/apiversion/web/
        └── CustomerVersionsControllerTest.java
~~~

### 9.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'api-version-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.2. Main application

`src/main/java/com/example/apiversion/ApiVersionDemoApplication.java`:

~~~java
package com.example.apiversion;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiVersionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiVersionDemoApplication.class, args);
    }
}
~~~

### 9.3. Controller with eight mappings

`src/main/java/com/example/apiversion/web/CustomerVersionsController.java`:

~~~java
package com.example.apiversion.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CustomerVersionsController {

    public record CustomerV1(long id, String fullName) {}

    public record CustomerV2(
            long id, String givenName, String familyName, boolean active) {}

    private CustomerV1 v1(long id) {
        return new CustomerV1(id, "Nguyen An");
    }

    private CustomerV2 v2(long id) {
        return new CustomerV2(id, "An", "Nguyen", true);
    }

    @GetMapping("/api/v1/customers/{id}")
    public CustomerV1 pathV1(@PathVariable("id") long id) {
        return v1(id);
    }

    @GetMapping("/api/v2/customers/{id}")
    public CustomerV2 pathV2(@PathVariable("id") long id) {
        return v2(id);
    }

    @GetMapping(path = "/api/header/customers/{id}",
            headers = "API-Version=1", produces = "application/json")
    public CustomerV1 headerV1(@PathVariable("id") long id) {
        return v1(id);
    }

    @GetMapping(path = "/api/header/customers/{id}",
            headers = "API-Version=2", produces = "application/json")
    public CustomerV2 headerV2(@PathVariable("id") long id) {
        return v2(id);
    }

    @GetMapping(path = "/api/query/customers/{id}",
            params = "version=1", produces = "application/json")
    public CustomerV1 queryV1(@PathVariable("id") long id) {
        return v1(id);
    }

    @GetMapping(path = "/api/query/customers/{id}",
            params = "version=2", produces = "application/json")
    public CustomerV2 queryV2(@PathVariable("id") long id) {
        return v2(id);
    }

    @GetMapping(path = "/api/media/customers/{id}",
            produces = "application/vnd.demo.customer.v1+json")
    public CustomerV1 mediaV1(@PathVariable("id") long id) {
        return v1(id);
    }

    @GetMapping(path = "/api/media/customers/{id}",
            produces = "application/vnd.demo.customer.v2+json")
    public CustomerV2 mediaV2(@PathVariable("id") long id) {
        return v2(id);
    }
}
~~~

There are **two distinct public DTO records** so tests can verify the old field disappears only in v2. Each handler has a distinct routing condition; do not use Spring 7's `version=` in a Boot 3 project.

**Example limitation:** the controller returns a fixture for any ID without querying a DB or checking permissions. Production must return 404 if the resource does not exist and authenticate/authorize by principal; **selecting a version does not grant read permission**.

### 9.4. Calling the API with curl

Run the project with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows you can use `.\gradlew.bat bootRun`.

Path:

~~~bash
curl -i 'http://localhost:8080/api/v1/customers/42'
curl -i 'http://localhost:8080/api/v2/customers/42'
~~~

Header:

~~~bash
curl -i 'http://localhost:8080/api/header/customers/42' \
  -H 'API-Version: 1' -H 'Accept: application/json'

curl -i 'http://localhost:8080/api/header/customers/42' \
  -H 'API-Version: 2' -H 'Accept: application/json'
~~~

Query:

~~~bash
curl -i 'http://localhost:8080/api/query/customers/42?version=1'
curl -i 'http://localhost:8080/api/query/customers/42?version=2'
~~~

Media type:

~~~bash
curl -i 'http://localhost:8080/api/media/customers/42' \
  -H 'Accept: application/vnd.demo.customer.v1+json'

curl -i 'http://localhost:8080/api/media/customers/42' \
  -H 'Accept: application/vnd.demo.customer.v2+json'
~~~

The expected result for each request is HTTP **200**, with v1 returning:

~~~json
{"id":42,"fullName":"Nguyen An"}
~~~

and v2 returning:

~~~json
{"id":42,"givenName":"An","familyName":"Nguyen","active":true}
~~~

On the media endpoint, `Content-Type` returns the matching vendor MIME type when the converter is active. Unmatched header/query URLs can return different routing errors depending on the scenario, **not guaranteeing a single 400 code automatically**. For unsupported versions, define an explicit error handler/strategy if the contract requires a standardized body.

## 10. MockMvc: testing schema too, not just HTTP status

`src/test/java/com/example/apiversion/web/CustomerVersionsControllerTest.java`:

~~~java
package com.example.apiversion.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CustomerVersionsControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void pathV1ReturnsLegacyShape() throws Exception {
        mvc.perform(get("/api/v1/customers/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.fullName").value("Nguyen An"))
                .andExpect(jsonPath("$.givenName").doesNotExist());
    }

    @Test
    void pathV2ReturnsNewShape() throws Exception {
        mvc.perform(get("/api/v2/customers/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.givenName").value("An"))
                .andExpect(jsonPath("$.familyName").value("Nguyen"))
                .andExpect(jsonPath("$.active").value(true))
                .andExpect(jsonPath("$.fullName").doesNotExist());
    }

    @Test
    void headerV1SelectsLegacy() throws Exception {
        mvc.perform(get("/api/header/customers/42")
                        .header("API-Version", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.fullName").value("Nguyen An"));
    }

    @Test
    void headerV2SelectsNew() throws Exception {
        mvc.perform(get("/api/header/customers/42")
                        .header("API-Version", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.givenName").value("An"))
                .andExpect(jsonPath("$.fullName").doesNotExist());
    }

    @Test
    void queryV1AndV2SelectCorrectDtos() throws Exception {
        mvc.perform(get("/api/query/customers/42")
                        .param("version", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.fullName").value("Nguyen An"));

        mvc.perform(get("/api/query/customers/42")
                        .param("version", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.active").value(true))
                .andExpect(jsonPath("$.fullName").doesNotExist());
    }

    @Test
    void mediaV1UsesVendorJsonType() throws Exception {
        mvc.perform(get("/api/media/customers/42")
                        .accept(MediaType.parseMediaType(
                                "application/vnd.demo.customer.v1+json")))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.parseMediaType(
                                "application/vnd.demo.customer.v1+json")))
                .andExpect(jsonPath("$.fullName").value("Nguyen An"));
    }

    @Test
    void mediaV2UsesVendorJsonType() throws Exception {
        mvc.perform(get("/api/media/customers/42")
                        .accept(MediaType.parseMediaType(
                                "application/vnd.demo.customer.v2+json")))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.parseMediaType(
                                "application/vnd.demo.customer.v2+json")))
                .andExpect(jsonPath("$.givenName").value("An"))
                .andExpect(jsonPath("$.fullName").doesNotExist());
    }

    @Test
    void unknownVendorTypeIsNotAcceptable() throws Exception {
        mvc.perform(get("/api/media/customers/42")
                        .accept(MediaType.parseMediaType(
                                "application/vnd.demo.customer.v3+json")))
                .andExpect(status().isNotAcceptable());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

Do not use `@AutoConfigureMockMvc(addFilters=false)` if you later add Spring Security and want to test authentication. The tests above focus on MVC mappings, response shapes, and media negotiation; they **do not** prove CDNs, browser CORS, or API gateways forward versions correctly. In real deployments, add E2E tests through the reverse proxy and contract tests from SDKs/consumers.

## 11. Spring Framework 7 has dedicated API versioning

Starting in **Spring Framework 7**, MVC has `ApiVersionStrategy` to resolve, parse, validate versions, and support deprecation. Spring Framework 7 extends `@RequestMapping` and its shortcut annotations with a `version` attribute.

**This is code specifically for Spring 7/Boot 4 compatibility, not part of the Spring Boot 3 demo above.**

### 11.1. Selecting a header resolver

~~~java
package com.example.modernversion;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ApiVersionConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ApiVersionConfig implements WebMvcConfigurer {

    @Override
    public void configureApiVersioning(ApiVersionConfigurer configurer) {
        configurer.useRequestHeader("API-Version");
    }
}
~~~

Spring 7 controller:

~~~java
package com.example.modernversion;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ModernCustomerController {

    @GetMapping(path = "/api/customers/{id}", version = "1.0")
    public Map<String, String> v1() {
        return Map.of("fullName", "Nguyen An");
    }

    @GetMapping(path = "/api/customers/{id}", version = "2.0")
    public Map<String, String> v2() {
        return Map.of("givenName", "An", "familyName", "Nguyen");
    }
}
~~~

Spring 7 resolves the version from `API-Version: 1.0` or `2.0`, then selects the mapping. `@GetMapping(version=...)` cannot be used in Spring 6.x. This is a conceptual fragment illustrating the mechanism, which can be placed into a compatible Spring 7 project with component scanning.

### 11.2. Built-in resolution strategies

`ApiVersionConfigurer` supports:
- `useRequestHeader("API-Version")`: version in a header.
- `useRequestParam("version")`: version in a query param.
- `usePathSegment(index)`: version in a path segment, e.g. `/api/{version}/customers`; the segment **must be a URI variable** in the mapping/path prefix, not just hardcoded `v1`.
- `useMediaTypeParameter(compatibleMediaType, "v")`: extracts `v` from media type in Accept/Content-Type where applicable.

Query resolver example:

~~~java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useRequestParam("version");
}
~~~

Media type parameter example:

~~~java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useMediaTypeParameter(
            org.springframework.http.MediaType.APPLICATION_JSON, "v");
}
~~~

Each fragment here is an **alternative option inside the callback**, not two overrides copied into the same class. With path versioning, the segment index is 0-based; e.g. `/api/{version}/...` is typically index 1. Read the actual version's documentation to configure the path resolver and prefixes.

### 11.3. Spring 7 version rules

- By default, the parser handles `major.minor.patch` semantic version components; minor/patch may default to 0.
- The parser can be replaced if using calendar versions or enterprise formats.
- Supported versions are normally gathered from declared mappings, or configured via an explicit list.
- When a version is unsupported, `InvalidApiVersionException` typically results in **400**.
- A version is required by default when the strategy is enabled; a missing version throws `MissingApiVersionException`, typically **400**, unless a default/optional version is configured.
- Mappings accept a **fixed version** like `"1.2"` or a **baseline version** like `"1.2+"`, useful when a handler remains compatible for subsequent versions.
- `ApiVersionDeprecationHandler` helps emit deprecation/sunset metadata when configured.

**Spring 7 does not automatically version JSON DTOs, business logic, or authorization.** It provides building blocks for routing and lifecycle; it does not decide for your team how long to keep v1 or what schemas fit.

### 11.4. Boot 3 → Boot 4 migration notes

Do not bump only `spring-webmvc` to 7.x in a Boot 3.3 project while bypassing dependency management. Check the Java baseline, Servlet/Jakarta namespaces, Spring Security, springdoc, starters, integration tests, and deployment runtime against the official compatibility matrix. If you cannot upgrade yet, using `path`, `headers`, `params`, and `produces` in Spring 6 still serves versioned APIs well when you thoroughly test error behavior and compatibility.

## 12. Missing/unknown versions, errors, and defaults

Regardless of the chosen approach, answer these questions:
- Should omitting the version be rejected, or fixed to a v1 default?
- If `v99` or an unparseable string is sent, what status/body is returned?
- How is `version=1&version=2` handled?
- Do major 1.0 and minor 1.1 share the same handler?
- Which version do clients sending `Accept: */*` or omitting `Accept` receive?
- Does a retired API version return migration documentation?

**Do not default to the latest version if you want to protect older clients.** If `GET /api/customers` without a version returns v1 today and silently switches to v2 tomorrow, old requests break even though client code did not change. If a default must exist, keep it fixed and document deadlines clearly.

### 12.1. Inconsistent HTTP statuses across strategies

| Scenario | Typical / expected status to verify |
| --- | --- |
| `/api/v99/...` has no MVC mapping | 404 under normal routing |
| Header/query mapping conditions fail to match | 404 or 400 depending on conditions and MVC exception handling |
| `Accept` incompatible with `produces` | Usually 406 Not Acceptable |
| Request `Content-Type` incompatible with `consumes` | Usually 415 Unsupported Media Type |
| Spring 7 native missing version | Usually 400 via `MissingApiVersionException` |
| Spring 7 native unsupported version | Usually 400 via `InvalidApiVersionException` |
| Request blocked by Security before MVC | 401 or 403 per auth/authorization |
| Version sunset per policy | Status/domain error decided by product; may be 400/410 |

Do not assert that every unknown version must be 404 or every 406 means an unsupported API version. If clients need **consistent** machine-readable errors, use explicit version validation/exception mapping and integration tests.

Example application-defined RFC 9457 error body:

~~~json
{
  "type": "about:blank",
  "title": "Unsupported API version",
  "status": 400,
  "detail": "Requested API version is not supported.",
  "code": "UNSUPPORTED_API_VERSION",
  "supportedVersions": ["1", "2"]
}
~~~

`supportedVersions` should only list public/allowed versions for the client, without exposing internal betas or tenant-private features. This is **not an automatic body in every Boot 3/4 project**.

## 13. Caching, `Vary`, and personalized data

### 13.1. Path/query vs. header/media type

Under standard HTTP caching, the target URI includes path/query, so `/api/v1/items` and `/api/v2/items`, or `?version=1` vs. `?version=2`, are distinguished. However, CDNs can be configured to **ignore query params**, rewrite URLs, or use custom cache keys, so test in practice.

For header-versioned responses at the same URI, cacheable responses should emit:

~~~http
Cache-Control: public, max-age=60
Vary: API-Version
~~~

For media type versioning at the same URI:

~~~http
Cache-Control: public, max-age=60
Vary: Accept
~~~

HTTP `Vary` tells caches to consider request headers when selecting stored representations. Do not forget other variants such as `Accept-Language`/`Accept-Encoding` if present. Never strip `Vary` headers from CORS/proxies when the controller adds its own `Vary`.

### 13.2. `Vary` is not user protection

Two users Alice and Bob may use the same API v2, same origin, and same `Accept`/version header. Caching can still leak data if private responses enter a shared cache. For `/api/me` or principal/tenant-scoped resources, choose `Cache-Control: private` or `no-store` depending on sensitivity, and enforce authentication/authorization at the origin. `Vary: API-Version` or `Vary: Accept` does not replace access control.

Spring's `@Cacheable` at the service layer is another layer that does not automatically understand HTTP versions/`Vary`. If domain caching keys on `id` while results depend on tenant/role, fix the cache key/scope or skip caching; versioning does not automatically prevent leaks inside services.

## 14. API gateways, OpenAPI, and client SDKs

### 14.1. Gateway

- Path: proxy routes/strips/rewrites `/api/v1`/`/api/v2` without losing the version during upstream selection.
- Header: forward `API-Version`, without dropping or mis-normalizing its value.
- Query: preserve `version` in the URL during rewrites; ensure the CDN cache key includes it.
- Media type: preserve `Accept`/`Content-Type` and support vendor `+json` MIME types.
- Also test `OPTIONS` preflight if browsers send custom version headers.
- Across multiple instances, the same version must always return the same contract during rolling deployments.

### 14.2. OpenAPI

Path versioning easily splits base paths/specs. Header/query versioning sharing the same path/method may require separate OpenAPI documents, schema alternatives, and generator configuration so SDKs do not assume a single response type. Vendor media types can use multiple media-type keys under `responses.content`, though code generators must be verified.

For each version, publish:
- How to pass the version and supported values.
- Request/response schemas and examples.
- Error codes/statuses.
- Authentication, CORS, pagination, validation, sorting, and idempotency rules.
- Missing/invalid version policy and caching rules.
- Deprecation/sunset dates and migration guide.

### 14.3. Observability

Logs/traces should record the validated **effective version** (e.g., `1`/`2`). Do not put raw unbounded version headers/queries into metric labels to avoid high cardinality and log injection. Track adoption, 4xx/5xx rates, latency, and usage per version and authorized consumer segment.

## 15. Deprecation and Sunset

A versioning strategy is incomplete without a retirement plan:
1. Release v2 alongside v1.
2. Publish contract differences, e.g., replacing `fullName` with `givenName/familyName`.
3. Provide docs/SDKs/client adapters for v2.
4. Monitor real v1 traffic, especially slow-releasing mobile apps/partners.
5. Mark v1 deprecated and notify consumers well in advance.
6. Establish a target Sunset date, support channels, and a rollback plan.
7. Retire the version only after evaluating impact, security, and compliance.

Standard HTTP signals include `Deprecation` (RFC 9745), `Sunset` (RFC 8594), and `Link` pointing to migration docs. Spring Framework 7 includes `ApiVersionDeprecationHandler` to emit these headers when configured; in Spring MVC 6, add them via responses/filters/interceptors per policy. Do not assume Spring generates sunset dates or migration docs on its own.

**Deprecation differs from Sunset:** deprecated means clients are advised to migrate away; sunset is the scheduled milestone when the API stops operating/being supported. Even older versions still need security patches; never keep a vulnerability just for “compatibility”.

## 16. Organizing code without duplicating business logic

A common architecture:

~~~text
GET /api/v1/customers -> V1 controller / DTO --\
                                               \
                                                -> Shared service / domain
                                               /       |
GET /api/v2/customers -> V2 controller / DTO --/        v
                                                     repository
~~~

Controllers/adapters handle HTTP mapping and per-version DTOs; services/domain hold shared business logic when semantics do not change. If business rules genuinely change, design explicit policies and tests rather than merely renaming fields.

V1 and v2 should use separate DTOs when breaking schema changes occur. Never expose JPA entities directly: changing tables/entity graphs can accidentally break public responses in both versions. If the v1 DTO still needs `fullName`, an adapter can build it from domain `givenName` and `familyName` per documented rules.

For mutating operations, both versions may touch the same database. Preserve transactions, optimistic locking, idempotency, auditing, and field defaults. Use expand/contract database migrations when rolling out multiple server/client versions; do not drop columns immediately when v2 deploys.

## 17. Common errors and how to diagnose them

| Error | Cause | Fix |
| --- | --- | --- |
| `@GetMapping(version=...)` fails to compile in Boot 3 | Mixing Spring 7 API with Spring 6 | Use mapping conditions or upgrade to a matching platform |
| `@RequestHeader` receives version, handler stays unchanged | Only binds, does not select mapping | `headers=...` or Spring 7 version strategy |
| V2 receives v1 response via CDN | Cache key ignores header/query version | `Vary` and CDN rules; test real cache |
| Vendor POST `Content-Type` works, GET misses | `Content-Type` describes request body | Use `Accept`/`produces` for response selection |
| `API-Version` header triggers `OPTIONS` | Custom header is not safelisted | CORS allow origin/method/header; handle `OPTIONS` before auth |
| `Accept` v3 returns 406 | No matching `produces` | Add supported type or return contract error |
| Method mappings conflict at startup | Overlapping conditions | Compare path/method/params/headers/produces |
| Defaulting to latest breaks old mobile apps | Contract shifts when version omitted | Use a fixed default or required version |
| A v1 endpoint adopts v2 schema after refactoring | Shared DTO was modified | Contract tests and separate adapters |
| Authorization exists only on v2 | Missed legacy security rules | Check all versions, object/tenant authorization |
| V1 stays alive forever | No sunset roadmap | Support policy, adoption metrics, announcements |
| CORS 403 mistaken for unsupported version | Preflight blocked before actual request | Inspect DevTools `OPTIONS` and filters |
| Route v99 returns 404 instead of 400 | Mapping conditions are not a version parser | Explicit error policy; Spring 7 native where appropriate |
| OpenAPI shows only one response type | Header/query versions share a path | Split specifications and test codegen |
| v1/v2 silently diverge in semantics | Versioning applied only to DTO names | Explicit versioned behavior/service policies |

### Ordered debugging workflow

1. Verify the **exact Spring Framework major version** and whether the annotation attribute exists.
2. Log actual method/URL/query/version header/`Accept`/`Content-Type`, never copying secret tokens into logs.
3. Inspect reverse proxy rewrites and forwarded headers.
4. Inspect Spring handler mappings and `params`/`headers`/`produces` conditions.
5. For cross-origin frontends, separate `OPTIONS` preflight from the actual request.
6. Check whether authentication/authorization blocked the request before MVC.
7. If a CDN is present, check cache keys, `Vary`, freshness, and `private` directives.
8. Test JSON field presence/absence alongside HTTP status/media type.
9. Test across multiple nodes during rolling deployments and across versions with the same fixture.
10. Compare the contract against OpenAPI, migration docs, and consumer tests.

## 18. Implementation checklist

- [ ] Choose version format, define breaking changes and supported versions.
- [ ] Pick **one** primary version transport: path, header, query, or media type.
- [ ] Define missing/unknown/duplicate version policies; never silently upgrade to latest.
- [ ] Use `path`, `headers`, `params`, `produces` in Spring 6; Spring 7 has a native version strategy.
- [ ] Give each version independent DTOs/mappings when schemas differ; share services sensibly.
- [ ] Test response bodies, statuses, 406/415, unknown/missing versions, auth, and tenant ownership.
- [ ] Test CORS if custom headers come from browsers.
- [ ] Test URL/query/header/`Accept` cache keys at CDN/proxy; `Vary` does not replace `no-store` for private data.
- [ ] Write OpenAPI specs, consumer tests, curl, and SDK examples.
- [ ] Monitor adoption, announce deprecation/sunset, and prepare migration/rollback plans.
- [ ] Never omit security fixes or leak data in older versions.

### Self-check questions

**1.** Does `@RequestHeader("API-Version")` route between v1 and v2 automatically?

**Answer:** No. Spring MVC 6 selects handlers via mapping conditions; Spring 7 has resolvers + the `version` attribute.

**2.** Is `?version=2` always cached separately from v1 by a CDN?

**Answer:** Not necessarily. Standard URIs differ, yet CDNs can ignore query params; verify cache-key policies.

**3.** How do `Accept` and `Content-Type` differ?

**Answer:** `Accept` requests the representation type to receive back; `Content-Type` describes the body type being sent.

**4.** With the same URL and `API-Version`, what should a cacheable public response include?

**Answer:** `Vary: API-Version` or compatible custom cache keys; personal data requires `private`/`no-store` independently.

**5.** Why can't Boot 3.3.5 use `@GetMapping(version="1.0")`?

**Answer:** Because Boot 3.3.5 uses Spring Framework 6.1.x, whereas the `version` attribute was added in Spring Framework 7.

**6.** Does a CORS preflight allowing `API-Version` prove the user is authorized to read the data?

**Answer:** No. CORS is a browser control; authentication and authorization must be enforced separately.

**7.** Does v2 require separating the database from v1?

**Answer:** No. You can use a shared domain/repository with separate adapters/DTOs and backward-compatible data migrations.

**8.** Why shouldn't missing versions default to latest?

**Answer:** Because the exact same request from old clients would change contracts whenever the server releases a new latest version.

## 19. Official reference documentation

- [Spring Framework 6.2 — RequestMapping Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html): `path`, `params`, `headers`, `consumes`, `produces`.
- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): mapping mechanics, Accept/Content-Type; Spring 7 includes `version`.
- [Spring Framework 7 — API Versioning](https://docs.spring.io/spring-framework/reference/web/webmvc-versioning.html): `ApiVersionStrategy`, parser, resolver, supported versions, and deprecation.
- [Spring Framework 7 — API Version Configurer](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/api-version.html): request header/query/path/media type parameter resolvers.
- [Spring Blog — API Versioning in Spring (2025)](https://spring.io/blog/2025/09/16/api-versioning-in-spring/): goals and changes in Spring Framework 7.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): Accept, Content-Type, statuses, and representation negotiation.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): `Vary`, cache keys, and shared/private caching.
- [RFC 8594 — Sunset Header](https://www.rfc-editor.org/rfc/rfc8594.html): sunset signal.
- [RFC 9745 — Deprecation Header](https://www.rfc-editor.org/rfc/rfc9745.html): deprecation signal.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): custom header preflight and security boundaries.

**Takeaway:** versioning is a **long-term contract commitment** between server and client. Path, header, query param, and media type are all viable, yet must be decided alongside caching, CORS, gateways, documentation, security, error behavior, and migrations. On Spring MVC 6.x use mapping conditions; Spring Framework 7 provides native versioning—do not mix code between the two platforms.

# HTTP 405 Method Not Allowed and the Allow Header When HTTP Methods Are Disabled in Spring Data REST

## 1. Meaning of 405 and the Allow header

According to RFC 9110 §15.5.6, `405 Method Not Allowed` occurs when the server recognizes the HTTP method in the request, but the target resource does not support that method. When returning 405, the origin server **MUST** send an `Allow` response header containing the list of methods currently supported by the resource. Example:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, PUT, DELETE
Content-Type: application/json
```

The example above only illustrates the format; actual values depend on the resource, repository, and running configuration. If PATCH has been disabled on the item resource, PATCH must not appear in that resource's Allow list.

`Allow` is per-resource information, not a global list of methods across the whole application. The list may vary depending on configuration or current state. RFC 9110 §10.2.1 also specifies that an empty Allow value indicates the resource currently allows no methods.

Distinguishing common statuses:

| Status | Meaning when diagnosing |
| --- | --- |
| `405` | The method is recognized but not supported by the target resource. Check the URI, resource type, repository methods, and ExposureConfiguration. |
| `501` | The server does not recognize or does not implement the submitted method. |
| `404` | The resource/route is not found, or the resource is configured not to be exported. |
| `401` / `403` | The request was blocked by authentication or authorization; this is not evidence that the method was disabled in Spring Data REST. |
| `400` / `415` | There is an issue with the request body or media type; check payload and Content-Type after confirming the method is supported. |

## 2. Default methods by resource type

Spring Data REST creates collection resources and item resources from repositories. For example, `OrderRepository extends CrudRepository<Order, Long>` typically provides `/orders` and `/orders/{id}`. Which methods are exposed depends on the CRUD methods the repository has and allows to be exported.

| Resource | Commonly supported methods | Behavior |
| --- | --- | --- |
| Collection `/orders` | `GET`, `HEAD`, `POST` | GET lists; POST creates an entity. Other methods typically return 405. |
| Item `/orders/{id}` | `GET`, `HEAD`, `PUT`, `PATCH`, `DELETE` | GET reads; PUT replaces; PATCH partially updates; DELETE deletes the entity. |
| Association `/orders/{id}/customer` | `GET`, `PUT`, `POST`, `DELETE` | PUT binds the association; POST applies only to collection associations; DELETE unlinks when the association permits. |
| Search `/orders/search` and query resources | `GET`, `HEAD` | Read-only resources that expose and execute exported query methods. |

Do not infer supported methods solely from the repository name. Identify the exact resource type before comparing the Allow header. For example, DELETE on `/orders/42` may be valid while DELETE on the collection `/orders` still returns 405 by design.

### Which repository methods determine HTTP methods?

Important mappings in Spring Data REST documentation:

- `findAll(...)` provides GET/HEAD for collection resources.
- `findById(...)` provides GET/HEAD for item resources.
- `save(...)` is used for POST on collections and PUT/PATCH on items.
- Appropriate `delete(...)` methods provide DELETE on items.

If a repository does not declare the required method, or the method is marked `@RestResource(exported = false)`, the corresponding HTTP method will not be exposed. A repository extending `CrudRepository` typically has all default CRUD methods. For a repository extending only `Repository` and declaring a subset of methods, exposure follows exactly those declared methods.

Be careful with `save(...)`: hiding this method with `@RestResource(exported = false)` can simultaneously disable collection POST and item PUT/PATCH. If the requirement is to disable only a single HTTP verb, use ExposureConfiguration to restrict the scope precisely.

## 3. Disabling methods with ExposureConfiguration

Since Spring Data REST 3.1, `RepositoryRestConfiguration.getExposureConfiguration()` provides a lambda API to filter HTTP methods globally or by domain type. The example below disables PATCH on all item resources:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.http.HttpMethod;

@Configuration
public class RestMethodExposureConfiguration {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return RepositoryRestConfigurer.withConfig(config ->
            config.getExposureConfiguration()
                .withItemExposure((metadata, methods) ->
                    methods.disable(HttpMethod.PATCH)));
    }
}
```

Some other options:

```java
// Disable DELETE only on Order item resources.
config.getExposureConfiguration()
    .forDomainType(Order.class)
    .withItemExposure((metadata, methods) ->
        methods.disable(HttpMethod.DELETE));

// Disable POST on all collection resources.
config.getExposureConfiguration()
    .withCollectionExposure((metadata, methods) ->
        methods.disable(HttpMethod.POST));

// Disable PUT on all item resources.
config.getExposureConfiguration().disablePutOnItemResources();

// Disable PATCH on all item resources.
config.getExposureConfiguration().disablePatchOnItemResources();

// Prevent PUT from creating new items specifically for domain type User.
config.getExposureConfiguration()
    .forDomainType(User.class)
    .disablePutForCreation();
```

Distinguish `disablePutForCreation()` from `disablePutOnItemResources()`: the former prevents creating new items with PUT; the latter disables PUT on item resources. `withCollectionExposure` only filters collection methods; `withItemExposure` only filters item methods; `withAssociationExposure` is used for association resources.

If you only want to hide a single repository method, you can override the inherited method and place `@RestResource(exported = false)` on it. Check all CRUD overloads/variants that your Spring Data version may call. In particular, `save(...)` may control multiple HTTP verbs as noted above. `@RepositoryRestResource(exported = false)` at the repository level hides the entire repository resource, typically causing the route not to be exported rather than disabling a single method.

The configuration example above uses `RepositoryRestConfigurer.withConfig(Consumer)`, available since Spring Data REST 3.1. If overriding `configureRepositoryRestConfiguration(config, cors)` directly, the signature with `CorsRegistry` is supported since 3.4. Match the Javadoc to the exact Spring Data REST version in your project's dependencies; do not copy signatures from newer documentation into older applications without verifying.

## 4. Reading and interpreting Allow

Call the exact URL with the exact method and inspect all response headers:

```bash
curl -i -X PATCH http://localhost:8080/orders/42 -H "Content-Type: application/merge-patch+json" -d '{"status":"SHIPPED"}'
```

If PATCH is disabled on the item resource, the expected result is status 405 and an Allow header not containing PATCH. For example, the header might be:

```http
Allow: GET, HEAD, PUT, DELETE
```

The exact value depends on the actual configuration. Use `curl -i` instead of reading only the response body, because the Allow header is crucial evidence for this error.

You can check whether a method is allowed with its corresponding request, for example:

```bash
curl -i http://localhost:8080/orders/42
curl -i http://localhost:8080/orders
```

GET item only returns 200 if the item exists and GET is exposed. GET collection checks the collection route. For collections, POST is the operation that creates entities; PUT/PATCH/DELETE do not automatically become valid just because those methods are supported on item resources.

### Allow is not Access-Control-Allow-Methods

The two headers serve two different purposes:

- `Allow` describes the HTTP methods supported by the target resource; RFC 9110 requires this header in 405 responses.
- `Access-Control-Allow-Methods` belongs to CORS, indicating which methods are accepted in the context of cross-origin requests from a browser.

Configuring CORS with `@CrossOrigin` or `CorsRegistry.allowedMethods(...)` does not automatically enable Spring Data REST PUT/PATCH/DELETE routes. Conversely, a route may support PATCH yet the browser still blocks the request because CORS preflight does not allow PATCH.

To inspect preflight, send an OPTIONS request with Origin and Access-Control-Request-Method:

```bash
curl -i -X OPTIONS http://localhost:8080/orders/42 -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: PATCH"
```

Read `Access-Control-Allow-Methods` and the CORS headers of this response. Afterward, still send an actual PATCH request to confirm the method is exposed. A successful preflight does not prove the endpoint supports that method.

## 5. Procedure for troubleshooting 405 errors

1. **Capture the full response intact.** Use `curl -i` or the Network tab to save status, URL, method, Allow, Content-Type, and response body.
2. **Verify the exact URL.** Distinguish collection, item, association, search resource, and query resource. Check the base path, custom paths via `@RepositoryRestResource`, ID, and association name.
3. **Match the method to the resource type.** For example, POST is used on collections; PUT/PATCH/DELETE are used on items. Search resources are read-only. Associations have their own rules.
4. **Check the repository.** Confirm the repository has the corresponding backing method; check whether the method has `@RestResource(exported = false)`. Also check repository exposure configuration and `RepositoryDetectionStrategy` if the route does not appear.
5. **Check exposure configuration.** Search for `RepositoryRestConfigurer` beans, `ExposureConfiguration`, `withCollectionExposure`, `withItemExposure`, `withAssociationExposure`, `forDomainType`, `disablePutOnItemResources()`, and `disablePatchOnItemResources()`.
6. **Separate CORS issues from exposure.** If only the browser fails, inspect OPTIONS requests and `Access-Control-Allow-Methods`. Use curl from the same environment to confirm whether the endpoint actually returns 405.
7. **Identify the layer generating the response.** If 405 lacks Allow, check reverse proxies/API gateways, servlet filters, Spring Security, and custom exception handlers. Per RFC 9110, the origin server must generate Allow in a 405 response; an intermediary layer may alter the response before it reaches the client.
8. **Re-verify after fixing.** Resend the disabled method and at least one still-allowed method; verify both status and Allow. Do not rely solely on the response body or an OPTIONS request.

Common symptoms:

- `Allow` omits PATCH: current configuration does not advertise PATCH for that resource; 405 when calling PATCH is expected.
- `Allow` includes PATCH yet PATCH requests still return 405: verify URL, host, proxy, deployed configuration, and whether responses come from the same origin.
- 405 without Allow: determine whether the response was generated by the application or a gateway/filter; check custom exception handling and whether headers are stripped.
- Only the browser fails while curl succeeds: prioritize checking CORS preflight, origin, credentials, and Access-Control-Allow-Methods.
- 404 instead of 405: check whether the repository/resource is exported, the base path, and whether the route is right.
- 401/403: check authentication/authorization before changing exposure.

## 6. Integration testing

Test both client-facing behavior and advertised headers. With Spring Boot, you can use `@SpringBootTest` + `@AutoConfigureMockMvc`; prepare an existing entity using your project's fixtures and substitute `orderId` with that ID:

```java
mockMvc.perform(patch("/orders/{id}", orderId)
        .contentType("application/merge-patch+json")
        .content("{\"status\":\"SHIPPED\"}"))
    .andExpect(status().isMethodNotAllowed())
    .andExpect(header().exists("Allow"))
    .andExpect(header().string("Allow",
        not(containsString("PATCH"))));
```

The test snippet above assumes PATCH was disabled via ExposureConfiguration and the fixture created `orderId`. Import the `not` and `containsString` matchers from Hamcrest. Do not hard-code the entire Allow string if the application might change other valid methods; assert that the header exists, the disabled method is absent, and methods that should remain are still supported.

Add a test for a valid method, for example:

```java
mockMvc.perform(get("/orders/{id}", orderId))
    .andExpect(status().isOk());
```

Testing checklist:

- PATCH on item resource returns 405 when disabled.
- 405 response includes the Allow header and Allow does not contain PATCH.
- GET item still succeeds if still exposed and fixture exists.
- GET/POST on collection are tested separately; do not infer from item resource results.
- If using `@RestResource(exported = false)`, test all HTTP verbs served by that backing method.
- If the client runs in a browser, test CORS preflight separately with Origin and Access-Control-Request-Method.
- Re-run integration tests after upgrading Spring Data REST or the Spring Data release train.

## 7. Official documentation

- [RFC 9110 §15.5.6 — 405 Method Not Allowed](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.6)
- [RFC 9110 §10.2.1 — Allow](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.1)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing supported HTTP methods](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST API — ExposureConfiguration](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/mapping/ExposureConfiguration.html)
- [Spring Data REST API — RepositoryRestConfigurer](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data REST — Configuring CORS](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html)
- [Spring Data REST API — ConfigurableHttpMethods](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/mapping/ConfigurableHttpMethods.html)
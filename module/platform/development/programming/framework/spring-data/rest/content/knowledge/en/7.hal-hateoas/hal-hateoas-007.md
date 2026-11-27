# Distinguishing application/hal+json and application/json by Spring Data REST Configuration

## Objectives

After this lesson, you will be able to distinguish plain JSON from HAL JSON; understand how Spring Data REST negotiates media types via HTTP headers; configure the default media type; and control whether a request asking for `application/json` receives HAL or a legacy Spring Data representation.

## 1. Where Do JSON and HAL JSON Differ?

`application/json` is the generic media type for JSON data. It indicates that content is transmitted using JSON syntax, but this media type itself does not prescribe a hypermedia structure or how clients discover related resources.

`application/hal+json` is the media type for HAL (Hypertext Application Language), a JSON-based hypermedia format. HAL adds conventions for representing links and embedded resources within a document:

- `_links` contains links such as `self`, `profile`, or links to related resources.
- `_embedded` contains other resources embedded in the representation, such as a list of customers in a collection.
- Relation names describe the meaning of links, helping clients discover the API via links instead of assembling every URL manually.

Abbreviated HAL example:

```json
{
  "_links": {
    "self": { "href": "http://localhost:8080/customers" },
    "profile": { "href": "http://localhost:8080/profile/customers" }
  },
  "_embedded": {
    "customers": [
      {
        "name": "Ada",
        "_links": {
          "self": { "href": "http://localhost:8080/customers/1" }
        }
      }
    ]
  }
}
```

This is still valid JSON, but it includes HAL structure and navigation information. A plain JSON representation might contain domain properties like `id`, `name`, `email` without `_links` or `_embedded`. Thus, both media types use JSON syntax, yet they are not equivalent in representation contract.

## 2. Spring Data REST Supports Both Media Types

Spring Data REST repository resources support `application/hal+json` and `application/json` for many operations such as reading collections, reading items, creating, and updating resources. With HAL, responses include hypermedia links so clients can discover the API. With plain JSON, representations do not necessarily carry HAL hypermedia controls.

Spring Data REST uses content negotiation to select a representation based on request headers and configuration. Distinguish these two headers:

- **`Accept`** is sent by the client to inform the server which media type it wants to receive in the response.
- **`Content-Type`** describes the media type of the body the client sends to the server, commonly seen in `POST`, `PUT`, or `PATCH` requests.

Example of a client requesting HAL:

```http
GET /customers HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
```

Client requesting generic JSON:

```http
GET /customers HTTP/1.1
Host: localhost:8080
Accept: application/json
```

For a request creating a customer, `Content-Type` describes the outgoing body, while `Accept` describes the desired response:

```http
POST /customers HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{"name":"Ada"}
```

In this example, the submitted body is plain JSON; the client wants the server to return a HAL representation after creating the resource. When permitted by the endpoint and configuration, these two choices can differ within the same request.

## 3. Default Behavior When a Client Sends Accept: application/json

Spring Data REST has a `useHalAsDefaultJsonMediaType` setting. Its default value is `true`.

When set to `true`, requests sending `Accept: application/json` are still served using HAL as the default JSON representation. The response typically has `Content-Type: application/hal+json` and a body containing the HAL structure.

When set to `false`, requests sending `Accept: application/json` receive the legacy Spring Data representation instead of HAL. This is a compatibility option when older clients expect the earlier JSON format and do not process HAL hypermedia structures.

You can picture the outcome as follows:

| Client Accept | `useHalAsDefaultJsonMediaType=true` | `useHalAsDefaultJsonMediaType=false` |
| --- | --- | --- |
| `application/hal+json` | HAL JSON | HAL JSON |
| `application/json` | HAL is used as the default JSON representation | Legacy Spring Data JSON |
| No `Accept` sent | Uses configured default media type | Uses configured default media type |

This setting only controls how Spring Data REST handles `application/json` requests by default. If a client explicitly requests `application/hal+json`, that is a direct request for HAL.

## 4. Configuring via Spring Boot Properties

There are two properties to distinguish:

- `spring.data.rest.default-media-type` specifies the default media type when a request does not indicate a matching media type.
- `spring.hateoas.use-hal-as-default-json-media-type` decides whether requests accepting `application/json` are served as HAL. The default is `true`.

To prioritize HAL for a Spring Data REST API:

```properties
spring.data.rest.default-media-type=application/hal+json
spring.hateoas.use-hal-as-default-json-media-type=true
```

With this configuration, requests without an `Accept` header use HAL as the default media type; requests with `Accept: application/json` are also served using HAL by default.

If you need to preserve legacy JSON for clients sending `Accept: application/json`:

```properties
spring.data.rest.default-media-type=application/json
spring.hateoas.use-hal-as-default-json-media-type=false
```

Then requests without an `Accept` header use JSON as the default media type; requests with `Accept: application/json` are handled using the legacy Spring Data representation. Clients needing HAL can still explicitly request `Accept: application/hal+json`.

The property name `spring.hateoas.use-hal-as-default-json-media-type` belongs to Spring HATEOAS configuration in Spring Boot. Use the property available in your project's Spring Boot/Spring Data REST version; for applications not using Spring Boot or needing direct configuration, you can use the Java API shown in the next section.

## 5. Configuring via RepositoryRestConfigurer

In Java configuration, use `RepositoryRestConfiguration`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDefaultMediaType(MediaType.parseMediaType(
                "application/hal+json"));
        config.useHalAsDefaultJsonMediaType(true);
    }
}
```

To use the legacy Spring Data representation when clients send `application/json`, change the configuration to:

```java
config.setDefaultMediaType(MediaType.APPLICATION_JSON);
config.useHalAsDefaultJsonMediaType(false);
```

The two methods have distinct roles:

- `setDefaultMediaType(...)` selects the fallback media type when a request does not specify a media type.
- `useHalAsDefaultJsonMediaType(...)` controls whether `application/json` is mapped to HAL.

Do not confuse these two settings with enabling or disabling Spring Data REST, changing repository paths, or changing the contents of domain objects stored in the database.

## 6. Inspecting Actual Responses with curl

You can test the same endpoint with both `Accept` values. Add `-i` to see both the status line and response headers:

```bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/customers
```

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/customers
```

Read the `Content-Type` header in the response to determine which representation the server chose. With HAL, the body usually contains `_links` and may contain `_embedded`. With legacy JSON, the body is rendered in Spring Data REST's traditional JSON representation.

If you want to test the case without sending `Accept`, call the endpoint without adding that header:

```bash
curl -i http://localhost:8080/customers
```

The result will depend on `spring.data.rest.default-media-type` or `RepositoryRestConfiguration.setDefaultMediaType(...)`.

## 7. Common Mistakes

**Client sends Accept: application/json but still receives HAL**

This is the default behavior when `useHalAsDefaultJsonMediaType=true`. Check `spring.hateoas.use-hal-as-default-json-media-type` or configure `RepositoryRestConfiguration.useHalAsDefaultJsonMediaType(false)` if clients require the legacy representation.

**Client wants HAL but response has no links**

Explicitly send `Accept: application/hal+json`, then check the response `Content-Type`. If the body still does not match expectations, check converter configuration, Spring HATEOAS version, and whether the endpoint is actually a resource managed by Spring Data REST.

**Confusing Content-Type with Accept**

Setting `Content-Type: application/json` only describes the request body. It does not ask for the response to be JSON. To request a response format, set `Accept` accordingly.

**Receiving 406 Not Acceptable**

The server cannot find a representation matching the `Accept` header requested by the client. Check media types supported by the endpoint, the `Accept` header, and default configuration.

**Receiving 415 Unsupported Media Type**

The media type of the request body is not accepted by the endpoint. Check `Content-Type` and endpoint documentation. Some association endpoints may require specialized media types like `text/uri-list`; not every request body uses `application/json`.

## 8. Choosing a Representation Based on Client Needs

- Prefer **`application/hal+json`** when clients need to discover the API via links, follow relations, and reduce coupling to hard-coded URLs.
- Use **`application/json` with HAL by default** when clients send the generic JSON media type yet the application still wants to preserve hypermedia.
- Only switch to **`useHalAsDefaultJsonMediaType=false`** when there is an explicit compatibility requirement for clients depending on the legacy Spring Data representation.
- Set a **default media type** so requests without `Accept` receive an expected representation; still guide clients to send an explicit `Accept` header so the API contract stays clear.

Switching from legacy JSON to HAL can affect clients that directly parse the response structure. Before changing the configuration, verify how clients deserialize responses and whether they rely on legacy field names or JSON structures.

## Summary

- `application/json` is generic JSON; `application/hal+json` is JSON following HAL hypermedia conventions.
- `Accept` selects the response representation; `Content-Type` describes the request body.
- `useHalAsDefaultJsonMediaType` defaults to `true`: `Accept: application/json` requests are served with HAL.
- Set this value to `false` so `Accept: application/json` requests receive the legacy Spring Data representation.
- `spring.data.rest.default-media-type` or `setDefaultMediaType(...)` specifies the default media type when the client does not send a specific requirement.

## References

- [Spring Data REST — Repository resources and supported media types](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [RepositoryRestConfiguration — API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Boot — Common application properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring HATEOAS — Spring Boot](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)

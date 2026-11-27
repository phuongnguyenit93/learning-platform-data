# Configuring `returnBodyOnCreate`, `returnBodyOnUpdate`, and the Effect of `Accept`

Spring Data REST automatically publishes Spring Data repositories as REST resources. When a client creates an entity with `POST` or updates an existing entity, the server can return the entity's representation in the response body. The two settings `returnBodyOnCreate` and `returnBodyOnUpdate` determine whether the response includes that representation.

## 1. Which operations do the two settings control?

| Configuration | Operation | Meaning |
|---|---|---|
| `returnBodyOnCreate` | Creating a resource, typically via `POST` on a collection resource | Determines whether to return the representation of the newly created entity |
| `returnBodyOnUpdate` | Updating an existing resource, typically via `PUT` | Determines whether to return the representation after updating |

The two options are independent. You can enable the body for creation while disabling it for updates, or vice versa. They control only the response body; they do not enable/disable repository endpoints, alter how data is saved, or determine whether entity creation or update succeeded. Responses for deletion have a separate configuration: `returnBodyOnDelete`.

In the Java API, distinguish configuration setters from request-level evaluation methods:

- `setReturnBodyOnCreate(Boolean)` and `setReturnBodyOnUpdate(Boolean)` configure the policy.
- `returnBodyOnCreate(String acceptHeader)` and `returnBodyOnUpdate(String acceptHeader)` evaluate whether to return a body for a request based on the policy and the `Accept` value.

## 2. Meaning of the three Boolean values

The setters take `Boolean` (the wrapper type), so there are three states:

| Value | Outcome |
|---|---|
| `true` | Always request returning the representation in the response body |
| `false` | Do not return the representation in the response body |
| `null` | Let Spring Data REST decide based on the presence of the `Accept` header |

When these two properties are not declared, the default configuration preserves `Accept`-based behavior: if the request has an `Accept` header, Spring Data REST can return a body; if the request has no `Accept` header, it does not render a body. This is why the same endpoint can return a body for one HTTP client and no body for another.

The table below applies separately to each create or update operation. Assume the media type requested by the client is supported by the server:

| Configuration value | Request with `Accept` | Request without `Accept` |
|---|---|---|
| `null` | Body returned | No body |
| `true` | Body returned | Body returned |
| `false` | No body | No body |

## 3. Configuration with Spring Boot

You can declare them directly in `application.yml`:

~~~yaml
spring:
  data:
    rest:
      return-body-on-create: true
      return-body-on-update: true
~~~

The example above asks to return the representation for both creation and update operations. If you only want to return a body on creation, set `return-body-on-create: true` and `return-body-on-update: false`. If you want to keep the decision dependent on `Accept`, omit the corresponding property from configuration instead of setting `false`.

The corresponding property keys are:

- `spring.data.rest.return-body-on-create`
- `spring.data.rest.return-body-on-update`

Spring Boot binds these keys into the Spring Data REST configuration. You can place them in profile-specific configuration files, such as `application-dev.yml` or `application-prod.yml`, so each environment has the appropriate response policy.

## 4. Java configuration with RepositoryRestConfigurer

When Java configuration is needed, register a `RepositoryRestConfigurer` bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
class SpringDataRestConfiguration {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return RepositoryRestConfigurer.withConfig(config -> {
            config.setReturnBodyOnCreate(true);
            config.setReturnBodyOnUpdate(true);
        });
    }
}
~~~

Change either value to `false` if you want to omit the response body for that operation. If both operations need the same policy, you can use the convenience method:

~~~java
config.setReturnBodyForPutAndPost(true);
~~~

This convenience method sets the return-body policy for both `POST` and `PUT`. Use the two individual setters when you need independent control over creation and updates.

## 5. How does the Accept header affect this?

The following two HTTP headers have different purposes:

- `Content-Type` describes the format of the data the client sends to the server, such as `application/json`.
- `Accept` describes the response format the client can receive, such as `application/hal+json`.

When the body policy is `null`, the presence of `Accept` is the signal for Spring Data REST to decide whether to render a representation. Once `true` or `false` is explicitly set, that policy determines whether a body is returned; `Accept` still participates in content negotiation to choose the response media type.

Example:

~~~http
POST /items
Content-Type: application/json
Accept: application/hal+json
~~~

The client sends JSON to create an entity and asks to receive the response in HAL JSON format. If `returnBodyOnCreate` is `null` or `true`, the response can contain the representation of the newly created resource. If set to `false`, the body is disabled even when the request includes `Accept`.

Sending only `Content-Type: application/json` does not mean the client asked for a response body. Conversely, some HTTP clients automatically add `Accept: */*` even if the user did not configure this header in the UI. Therefore, when verifying default behavior, inspect the actual headers on the outgoing request.

If `Accept` requests a media type the server cannot produce, content negotiation can fail (typically HTTP `406 Not Acceptable`). That case is different from configuration intentionally disabling response bodies.

## 6. Testing with curl

The paths `/items`, `/items/42`, and the JSON fields below are examples only. Replace them with the resource paths published by your application's repository and the actual entity properties.

**Create an entity and request the representation:**

~~~bash
curl -i -X POST "http://localhost:8080/items" -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"name":"Keyboard","status":"ACTIVE"}'
~~~

**Create an entity while omitting the Accept header:**

~~~bash
curl -i -X POST "http://localhost:8080/items" -H "Content-Type: application/json" -H "Accept:" -d '{"name":"Keyboard","status":"ACTIVE"}'
~~~

In curl, `-H "Accept:"` removes the default `Accept` header. When the two configuration properties remain `null`, these two requests let you observe the difference in response bodies.

**Update an entity and request the representation:**

~~~bash
curl -i -X PUT "http://localhost:8080/items/42" -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"name":"Keyboard Pro","status":"ACTIVE"}'
~~~

Compare the responses across the three configuration states `null`, `true`, and `false`. When a body is returned, the representation may include HAL links such as `_links`, depending on the media type and your application's serialization configuration.

## 7. Reading responses and handling missing bodies

Do not conclude an operation failed just because the response body is empty. For creation operations, Spring Data REST typically returns a `Location` header containing the URI of the new resource. The client can use that URI to send `GET` and retrieve the representation. For update operations, the client can `GET` the updated resource's URI if it needs the latest data.

When a body is expected but not received, check in order:

1. The effective value of `spring.data.rest.return-body-on-create` or `spring.data.rest.return-body-on-update` in the active profile.
2. Whether the actual HTTP method is a create or update operation; the two policies do not substitute for each other.
3. The actual `Accept` header on the request, including headers added automatically by Postman, browsers, or HTTP libraries.
4. Whether the media type in `Accept` is supported by the server.
5. Whether the response body was stripped by a gateway, proxy, or client wrapper.

If bodies are intentionally disabled, inspect the status and `Location` header (for creation), then call `GET` on the resource when the representation is needed. Response bodies may also follow projections, Jackson mappings, and HAL formatting; do not assume they are always flat JSON containing only entity fields.

## 8. Choosing the right policy

- **Client needs data immediately after creation:** enable `returnBodyOnCreate`; the client sends `Accept` with a server-supported media type and can use the returned representation to update the UI.
- **Client needs data after updating:** enable `returnBodyOnUpdate` if you want to avoid a follow-up `GET` request.
- **Prefer lightweight responses:** set `false` for operations that do not need representations; clients call `GET` only when they need to re-read data.
- **Want per-client behavior:** keep `null`, then explicitly send or omit `Accept` depending on client needs. Note that HTTP libraries may automatically send `Accept: */*`.

## References

- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/docs/4.4.x/api/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html): setters, `Accept`-based decision methods, and combined policy for `POST`/`PUT`.
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/docs/4.3.5/api/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html): Java configuration registration and `withConfig`.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): keys `spring.data.rest.return-body-on-create` and `spring.data.rest.return-body-on-update`.
- [Spring Guide — Accessing JPA Data with REST](https://spring.io/guides/gs/accessing-data-rest): `POST` response examples, `Location` header, and options to return representations.
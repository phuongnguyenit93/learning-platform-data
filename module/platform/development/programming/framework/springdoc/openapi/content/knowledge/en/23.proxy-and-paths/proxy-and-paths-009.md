# ServerBaseUrlCustomizer when generated URLs need adjustment

When running Spring Boot directly, springdoc-openapi can infer the server URL from the request fetching the documentation. However, when the application sits behind a reverse proxy, ingress, or API gateway, the request received by the application may carry a different scheme, host, port, and path than the URL used by external clients. Swagger UI may then display an internal server URL or send Try it out requests to the wrong address.

You should first have the proxy forward original URL metadata via forwarded headers and configure Spring Boot to process them. `ServerBaseUrlCustomizer` is springdoc's extension point to fine-tune the computed base URL string—for example, stripping a port that should not appear in documentation. It does not replace configuring a reverse proxy, context path, or securing forwarded headers.

This lesson focuses on when to use `ServerBaseUrlCustomizer`, how to write a safe customizer, how to handle forwarded headers, document caching, and verifying the final server URL in OpenAPI JSON.

## Objectives

After this lesson, you will be able to:

- Explain how springdoc infers the server URL from a request.
- Identify scheme, host, port, and path mismatches when running behind a proxy.
- Distinguish forwarded-header handling from `ServerBaseUrlCustomizer`.
- Configure `server.forward-headers-strategy` for the servlet or reactive stack.
- Write a `ServerBaseUrlCustomizer` bean to conditionally adjust generated URLs.
- Know when to declare static `servers` using an OpenAPI annotation or bean.
- Handle context paths and `X-Forwarded-Prefix` without duplicating paths.
- Understand caching behavior when documentation is accessed across multiple hostnames.
- Protect the application against forwarded headers sent by untrusted clients.
- Inspect URLs in Swagger UI and `/v3/api-docs`.

## 1. Where is the Server URL used?

In OpenAPI, `servers` defines the base address clients use to call described paths. For example, if an operation has path `/api/products` and the server URL is `https://api.example.com/catalog`, the complete call URL is:

~~~text
https://api.example.com/catalog/api/products
~~~

Swagger UI uses the server URL to construct requests when users click Try it out. SDK generators and integration tools may also use this server list to configure base URLs.

If `servers` contains an internal address like `http://product-service:8080`, external clients may be unable to reach it. If the scheme is generated as `http` while the public gateway uses `https`, browsers may block mixed-content requests or clients may use the wrong protocol. If the gateway path prefix is missing, requests may hit nonexistent routes.

### Architecture example

~~~text
Client
  |
  | https://api.example.com/catalog
  v
Reverse proxy / API Gateway
  |
  | http://product-service:8080
  v
Spring Boot + springdoc-openapi
~~~

Clients see only `https://api.example.com/catalog`. The Spring Boot application receives an internal connection from the proxy at `product-service:8080`. Without forwarded-header handling, the request URL seen by springdoc may reflect the internal address.

The goal is for the documentation to publish a server URL that clients can actually use:

~~~yaml
servers:
  - url: https://api.example.com/catalog
~~~

## 2. How springdoc builds the server URL

When no explicit server URL is declared, springdoc can automatically generate a base URL from the request hitting the documentation endpoint. For Web MVC, the default JSON endpoint is `/v3/api-docs`; default YAML is `/v3/api-docs.yaml`. The base URL is derived from the request URL after stripping the documentation endpoint path and internal path segments springdoc knows about.

For example, a request to:

~~~text
http://localhost:8080/store/v3/api-docs
~~~

can produce the base URL:

~~~text
http://localhost:8080/store
~~~

If requests pass through a proxy without the application knowing the original URL, the base URL may contain:

- `http` instead of `https`.
- An internal host or container IP address.
- An internal port such as `8080`.
- A missing public prefix such as `/catalog`.
- A missing or duplicated context path.

### When servers are declared explicitly

If OpenAPI has servers declared via `@OpenAPIDefinition(servers = ...)`, `@Server`, or an OpenAPI bean, springdoc uses the declared servers instead of an auto-generated URL. When you want a fixed address for every request, declare a static server directly in the OpenAPI definition.

Example:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/catalog",
            description = "Public API"
        )
    }
)
class PublicApiDefinition {
}
~~~

The address in the example is illustrative. For release, replace it with the public URL approved by the API owner. With a fixed server configuration, you do not need `ServerBaseUrlCustomizer` just to recreate the same URL.

## 3. What do forwarded headers solve?

A reverse proxy can pass the original URL in the RFC 7239 `Forwarded` standard header or common `X-Forwarded-*` headers.

| Header | Information |
|---|---|
| `Forwarded` | Can carry `proto`, `host`, and node metadata per RFC 7239 |
| `X-Forwarded-Host` | Host called by the external client |
| `X-Forwarded-Proto` | External scheme, usually `https` |
| `X-Forwarded-Port` | External port, e.g. `443` |
| `X-Forwarded-Prefix` | Public path prefix stripped by the proxy before forwarding |
| `X-Forwarded-For` | Client IP address or proxy chain; not the API host |

Spring Boot must be configured to read these headers. When handled properly, the request seen by Spring reflects the external URL more accurately; springdoc can then generate a suitable server URL without parsing headers itself.

### Choosing a forwarded-headers strategy

In Spring Boot 3, the commonly used configuration is:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Key values:

| Value | Behavior |
|---|---|
| `NONE` | Ignore forwarded headers |
| `NATIVE` | Use the web server/container's forwarded-header handling |
| `FRAMEWORK` | Use Spring Framework's mechanism |

`NATIVE` may suffice if the container properly handles the headers sent by the proxy. When `X-Forwarded-Prefix` support or behaviors unsupported by the container are required, `FRAMEWORK` uses `ForwardedHeaderFilter` for the servlet stack and `ForwardedHeaderTransformer` for the WebFlux stack.

Usually configuring `server.forward-headers-strategy` is enough; Spring Boot registers the corresponding mechanism. Avoid manually registering a duplicate `ForwardedHeaderFilter` when auto-configuration already handles forwarded headers.

### Identifying which headers are actually needed

If only the scheme or host is wrong, check `Forwarded` or the `X-Forwarded-Proto`/`X-Forwarded-Host` pair. If only the port is wrong, check `X-Forwarded-Port`. If the URL has the right host yet misses the gateway path, check `X-Forwarded-Prefix`.

Do not use `X-Forwarded-For` to fix server URLs. That header is for client addresses, not the hostname Swagger UI needs to call.

## 4. Configuring the proxy to pass the original URL

The application can only process metadata accurately if the proxy sends it. The proxy must set forwarded headers according to the public request and strip forged values previously sent by clients.

Example Nginx configuration when public prefix `/catalog` is stripped before forwarding to the application:

~~~nginx
location /catalog/ {
    proxy_pass http://product-service:8080/;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-Prefix /catalog;
}
~~~

With the trailing `/` on `proxy_pass` in the example, the location prefix is removed from the forwarded path. `X-Forwarded-Prefix: /catalog` tells Spring the public prefix that needs to reappear in URLs.

Service names and proxy settings here are illustrative. Adjust them for your actual gateway, especially when multiple proxies are chained or the gateway does not strip the path prefix.

### Proxy must overwrite client headers

Do not let Internet clients dictate `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`, or `X-Forwarded-Prefix` that the application trusts. The edge proxy must strip or overwrite untrusted values and emit fresh headers from the request it verifies.

If the application can be reached directly bypassing the proxy, callers can send forwarded headers themselves to make the generated server URL point to another host or scheme. Enable forwarded-header handling only once access paths and trusted proxies are controlled.

## 5. Context path and forwarded prefix

`server.servlet.context-path` is the context path of the Spring Boot application itself. `X-Forwarded-Prefix` describes a public prefix stripped by the proxy before the request reaches the application. These two values represent two distinct path layers.

Example:

- Public URL: `https://api.example.com/gateway/catalog`.
- Gateway strips `/gateway` before forwarding.
- Application has context path `/catalog`.
- Internal request reaching the application retains context path `/catalog`.

The public server URL then needs to contain `/gateway/catalog`, assuming the proxy routes according to this structure. Inspect the actual URL clients call and the request path after each layer.

### Avoiding duplicate prefixes

If the proxy does not strip `/catalog` yet still sends `X-Forwarded-Prefix: /catalog`, Spring may prepend the prefix to a path that already has it, producing duplicates like `/catalog/catalog`.

Conversely, if the proxy strips the prefix without sending `X-Forwarded-Prefix`, documentation may miss the `/catalog` segment.

Do not fix this by unconditionally appending path strings in a customizer before confirming whether the proxy preserves or strips the prefix. Trace the path at each hop and ensure only one place restores a stripped prefix.

## 6. What is ServerBaseUrlCustomizer?

`ServerBaseUrlCustomizer` is a springdoc interface for adjusting the base URL string computed by springdoc before placing it in the document. The interface has one method:

~~~java
String customize(String serverBaseUrl);
~~~

The parameter is the generated URL string. The method returns the adjusted URL. It can be used to strip an undesired port, normalize a known host, or modify part of a URL following clear rules.

Interface package in springdoc-openapi v2:

~~~java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
~~~

The example below strips port `8080` only when the scheme and host match the defined public endpoint exactly. The path is preserved:

~~~java
import java.net.URI;

import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public class PublicServerBaseUrlCustomizer
        implements ServerBaseUrlCustomizer {

    @Override
    public String customize(String serverBaseUrl) {
        try {
            URI uri = URI.create(serverBaseUrl);

            boolean expectedPublicHost =
                "https".equalsIgnoreCase(uri.getScheme())
                && "api.example.com".equalsIgnoreCase(uri.getHost());

            if (expectedPublicHost && uri.getPort() == 8080) {
                return UriComponentsBuilder.fromUri(uri)
                    .port(-1)
                    .build(true)
                    .toUriString();
            }
        } catch (IllegalArgumentException ex) {
            // Keep the generated value if the URL cannot be parsed.
        }

        return serverBaseUrl;
    }
}
~~~

This example assumes the application already received the right public host `api.example.com`, yet the base URL still contains internal port `8080`. The customizer strips that port while keeping the existing scheme, host, context path, and path. Replace the example host and port with values confirmed in your real architecture.

`UriComponentsBuilder.fromUri(uri).port(-1)` removes the port. Do not perform this operation if the port is part of the public endpoint—for example, if the public API actually runs on `8443`.

The example keeps the original string if the URI cannot be parsed to illustrate conditional transformation. Under strict release policies, you may throw an exception and halt document generation on invalid URLs rather than continuing with an unknown value.

### Registering with @Bean

If you prefer not to use `@Component`, register the interface via a bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiServerConfiguration {

    @Bean
    ServerBaseUrlCustomizer serverBaseUrlCustomizer() {
        return new PublicServerBaseUrlCustomizer();
    }
}
~~~

When using this `@Bean` approach, remove `@Component` from `PublicServerBaseUrlCustomizer` in the previous example. Choose one registration method to avoid creating multiple customizers modifying the same URL. If multiple customizers exist, define their order and ensure transformations do not conflict.

## 7. When should you use ServerBaseUrlCustomizer?

Consider this interface when:

- The generated URL is nearly right but needs an internal port removed that should not be published.
- A specific public hostname requires normalization under a stable rule.
- Part of the generated URL needs conditional adjustment based solely on the base URL string.
- The discrepancy cannot be resolved by forwarded-header handling or application server settings alone.

For instance, the proxy sends accurate `X-Forwarded-Host` and `X-Forwarded-Proto`, yet the container still inserts an unwanted port into the URL. A customizer can strip that specific port when the host matches an allowlist.

### When a customizer is not needed

You do not need `ServerBaseUrlCustomizer` if:

- Forwarded headers are already sent properly by the proxy and handled properly by Spring.
- Context path and `X-Forwarded-Prefix` are configured accurately.
- The application always uses one fixed public base URL; in that case, declare `servers` explicitly.
- The server URL is wrong due to bad proxy routing or a misconfigured application context path.
- Swagger UI points to the wrong OpenAPI document URL; that is Swagger UI configuration, not the server base URL.

Do not use a customizer to mask gateway routing mistakes. The URL displayed in OpenAPI might look right while the gateway still fails to route requests to the application.

## 8. Limitations of ServerBaseUrlCustomizer

The `customize` method receives only a `serverBaseUrl` string. It does not receive `HttpServletRequest`, `ServerHttpRequest`, or request headers. Therefore:

- You cannot directly read `X-Forwarded-Prefix` from the interface parameters.
- You should not inject request-scoped objects into a singleton customizer.
- Do not use `ThreadLocal` to pass request context into the customizer.
- Do not assume the customizer can choose URLs per user, tenant, or per-request gateway header.

If needed values live in forwarded headers, let Spring process forwarded headers before springdoc computes the URL. If server URLs are fixed per audience or group, declare them in the OpenAPI definition or use an OpenAPI-level customizer for that group.

### Do not blindly append a prefix

Code like the following easily breaks if the request already contains the prefix:

~~~java
return serverBaseUrl + "/catalog";
~~~

Results can duplicate `/catalog/catalog`, miss a `/`, or corrupt URLs with another context path. If path adjustment is needed, parse the URI, inspect the current path, and add only when the prefix is absent. Still, for strip-prefix proxies, prefer `X-Forwarded-Prefix` and a forwarded-header strategy.

### Do not swap hosts based on arbitrary incoming requests

Never pull `Host` or `X-Forwarded-Host` from an arbitrary request and substitute it directly into the OpenAPI URL unless the proxy is trusted. That can cause the documentation to emit caller-chosen hostnames. Use a proxy allowlist and validate permitted public hosts.

## 9. ServerBaseUrlCustomizer vs. static OpenAPI servers

These two configuration styles address different goals:

| Approach | Scope | When appropriate |
|---|---|---|
| `ServerBaseUrlCustomizer` | Adjusts request-derived base URL | Generated URL is close and needs a minor deterministic transformation |
| `@OpenAPIDefinition(servers = ...)` | Declares fixed servers in OpenAPI | Public URL does not vary per request |
| OpenAPI bean | Builds server list in Java | Need to read deployment config or construct a server list |
| `GroupedOpenApi` + `OpenApiCustomizer` | Adjusts servers per group | Public, partner, and internal groups have different base URLs |
| Forwarded headers | Restores original URL info from proxy | Wrong scheme, host, port, or prefix caused by proxy |

Example of a group with a fixed server:

~~~java
import java.util.List;

import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(openApi ->
            openApi.setServers(List.of(
                new Server().url("https://partner-api.example.com")
            ))
        )
        .build();
}
}
~~~

The server list in the example is attached to the partner group. Do not assume a `ServerBaseUrlCustomizer` can distinguish groups, audiences, or tenants; its interface receives only the base URL string.

## 10. OpenAPI caching when URLs vary per request

By default, springdoc computes the OpenAPI description and caches the result. This is suitable when the server URL is identical for every request.

Some systems serve the same Swagger UI through both internal and external proxies. Two requests may arrive with different hostnames or schemes. If the document is cached after the first request, subsequent requests may receive the earlier request's server URL.

When recalculating the document per request is genuinely needed, caching can be disabled:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Disabling caching increases document generation overhead. Enable it only when the server URL truly depends on the request and the impact has been measured. If the public base URL is always fixed, declare a static server URL instead of disabling caching.

Caching cannot fix wrong forwarded headers. If the proxy sends the wrong host or prefix, every regeneration of the document will still yield the wrong URL.

## 11. Testing the server URL

Verify the final URL from the OpenAPI endpoint rather than testing only the customizer code. Expected results must cover scheme, host, port, and path.

### Testing with MockMvc and forwarded headers

Example test when the application uses `server.forward-headers-strategy=framework`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "server.forward-headers-strategy=framework",
    "springdoc.cache.disabled=true"
})
@AutoConfigureMockMvc
class OpenApiForwardedUrlTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void usesExternalSchemeHostAndPrefix() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .header("Forwarded", "proto=https;host=api.example.com")
                .header("X-Forwarded-Prefix", "/catalog"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.servers[0].url")
                .value("https://api.example.com/catalog"));
    }
}
~~~

This example is for the servlet stack; load the application configuration and filters just as in the real environment. If the proxy keeps the prefix in the request path rather than stripping it, adjust headers and assertions to match real routing.

### Unit testing the customizer

You can test the port-removal rule independently:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PublicServerBaseUrlCustomizerTest {

    private final PublicServerBaseUrlCustomizer customizer =
        new PublicServerBaseUrlCustomizer();

    @Test
    void removesOnlyTheExpectedInternalPort() {
        String result = customizer.customize(
            "https://api.example.com:8080/catalog"
        );

        assertEquals(
            "https://api.example.com/catalog",
            result
        );
    }

    @Test
    void keepsPortForAnotherHost() {
        String input = "https://internal.example.net:8080/catalog";

        assertEquals(input, customizer.customize(input));
    }
}
~~~

The first test verifies the port is removed only when host and port match the rule. The second test ensures the customizer does not modify another host.

### Manual verification

After starting the application:

1. Access `/v3/api-docs` externally through the proxy.
2. Check `servers[0].url` in the JSON.
3. Open Swagger UI and verify the displayed server.
4. Use Try it out on a safe read endpoint to confirm requests pass through the public gateway.
5. Check YAML at `/v3/api-docs.yaml` if the application publishes both formats.
6. Test both internal and external access if both audiences are supported.

Do not check only that the Swagger UI page loads; the UI can load while the server URL inside OpenAPI is still wrong.

## 12. Diagnosing common errors

| Symptom | Possible cause | Where to check |
|---|---|---|
| Swagger UI shows `http` instead of `https` | Missing or unprocessed `X-Forwarded-Proto`/`Forwarded` | Check proxy and `server.forward-headers-strategy` |
| Host is service name or internal IP | Missing `X-Forwarded-Host` or `Forwarded host` | Verify headers proxy sends to the application |
| URL contains port `8080` | Proxy does not send public port or container generates internal URL | Check `X-Forwarded-Port`, then consider a conditional customizer |
| URL is missing `/catalog` | Proxy strips prefix without sending `X-Forwarded-Prefix` | Configure proxy and framework forwarded-header handling |
| URL contains `/catalog/catalog` | Prefix already exists in path yet added again | Verify whether the proxy strips the prefix |
| URL duplicates context path | Application context path and proxy prefix configured redundantly | Compare paths in public request and upstream request |
| Only first request gives right URL | OpenAPI cache retains previous request's server URL | Consider `springdoc.cache.disabled` if URL must depend on request |
| Customizer does not change URL | OpenAPI declares static servers or customizer is not registered as a bean | Check `servers` annotation/bean and Spring context |
| URL altered wrongly in all environments | Customizer modifies every host/port unconditionally | Restrict strictly by scheme, host, and port |
| Swagger UI loads yet Try it out fails | Wrong server URL or gateway route; CORS or auth may mismatch | Check `servers`, network request, gateway, and CORS |

### Step-by-step investigation procedure

1. Record the public URL the browser calls for `/v3/api-docs`.
2. Record the upstream URL the proxy sends to the application.
3. Inspect the forwarded headers the proxy actually sends.
4. Confirm Spring Boot processed those headers.
5. Read `servers` in the OpenAPI JSON.
6. If the URL is still wrong, determine whether the error is in scheme, host, port, or path.
7. Add `ServerBaseUrlCustomizer` only if the error is a deterministic URL transformation.
8. Re-check caching and call the endpoint through the right proxy.

## 13. Securing forwarded headers

Forwarded headers can alter how the application interprets the original URL. If the application trusts headers sent by untrusted clients, callers can spoof the host, scheme, or prefix.

Apply these principles:

- Trust forwarded headers only from controlled reverse proxies or load balancers.
- The edge proxy must strip or overwrite client-sent values.
- Do not allow internal endpoints to be called directly from untrusted networks if the application trusts forwarded headers.
- Restrict the trusted proxy list in web server/container settings when using the native strategy.
- Never reflect arbitrary hosts into OpenAPI or redirects.
- Allow only valid public hosts; a customizer may check an allowlist, though it does not replace proxy trust configuration.
- Do not log full URLs if query strings may contain credentials.

`ServerBaseUrlCustomizer` should be a pure, clearly conditioned transformation that does not depend on shared mutable state. Avoid storing a previous request's URL in a singleton bean field.

## 14. Comprehensive hands-on exercise

Deploy a Spring Boot API behind a reverse proxy with public URL:

~~~text
https://api.example.com/catalog
~~~

The proxy forwards requests to the application at an internal address and strips the `/catalog` prefix before forwarding. Perform:

1. Identify the public URL, upstream URL, context path, and stripped path prefix.
2. Configure the proxy to send `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`, and `X-Forwarded-Prefix`.
3. Configure `server.forward-headers-strategy=framework`.
4. Call `/v3/api-docs` through the proxy and verify the server URL.
5. If only an internal port remains wrong, create a `ServerBaseUrlCustomizer` stripping the port solely for the right public host.
6. Write unit tests for the customizer covering the matching host, a different host, a different scheme, and a different port.
7. Write a MockMvc integration test checking `Forwarded` together with `X-Forwarded-Prefix`.
8. Open Swagger UI and use Try it out to confirm requests go through the public gateway.
9. Try fetching the documentation via an internal path if supported by the environment and verify cache behavior.
10. Re-enable caching if the public server URL is fixed; disable caching only if URLs must be computed per request.
11. Try sending forged forwarded headers from a client and verify the edge proxy overwrites them.
12. Document permitted host/port/path rules so operators can verify them at deployment.

### Completion criteria

- [ ] Can distinguish request-derived server URLs from statically declared servers.
- [ ] Identified headers required for scheme, host, port, and prefix.
- [ ] Spring Boot processes forwarded headers with the appropriate strategy.
- [ ] `X-Forwarded-Prefix` is properly configured when the proxy strips paths.
- [ ] No duplicate context path or gateway prefix.
- [ ] `ServerBaseUrlCustomizer` modifies only the targeted host/port/path.
- [ ] URLs of other hosts or environments are not altered unintentionally.
- [ ] Caching is configured based on whether URLs vary between requests.
- [ ] `/v3/api-docs` and Swagger UI show the same intended server URL.
- [ ] Proxy strips or overwrites untrusted forwarded headers.
- [ ] Unit and integration tests exist for proxied URLs.

## Continue learning

After this lesson, combine forwarded headers with context paths, gateway routes, grouped documentation, and deployment testing. Whenever a generated URL is wrong, pinpoint the exact layer causing the discrepancy before adding a customizer; a correct base URL must accurately reflect scheme, host, port, and path as actually used by clients.

## References

- [springdoc-openapi v2 – FAQ: deploy behind a reverse proxy](https://springdoc.org/v2/)
- [Spring Boot 3.5 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot – ForwardHeadersStrategy](https://docs.spring.io/spring-boot/docs/3.2.x/api/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html)
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)

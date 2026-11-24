# Server URL inferred from request or declared explicitly

OpenAPI uses the Server object to tell clients which host and base path to call the API at. When users open Swagger UI, this server selection determines the target URL combined with an operation's path during Try it out.

springdoc-openapi can generate the server URL based on information from the HTTP request serving the documentation. This is convenient when running locally or deploying behind a proxy with properly configured forwarded headers. If the API has a fixed public address, or needs to publish multiple environments, servers can be declared explicitly using annotations or an OpenAPI bean.

An application behind a reverse proxy typically receives internal requests with a different host, scheme, port, or path than the URL used by external clients. Without handling forwarded headers, the documentation may expose an internal address like http://10.0.0.12:8080 instead of https://api.example.com. This guide explains how to choose the server URL source, configure the proxy, handle prefixes, customize URLs, and verify the results.

## 1. Where does the Server URL live in OpenAPI?

In OpenAPI, the servers field contains a list of Server Objects. Each server has a base URL and may include a description and URL variables.

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
servers:
  - url: https://api.example.com/v1
    description: Production API
paths:
  /orders:
    get:
      summary: List orders
      responses:
        '200':
          description: Success
~~~

Clients combine the server URL with the operation path. In the example, the API call URL is:

~~~text
https://api.example.com/v1/orders
~~~

The /v1 part belongs to the server's base path. The /orders part belongs to the path described in OpenAPI.

The Server URL is not the URL of the documentation file. Distinguish carefully:

| Component | Role |
|---|---|
| /v3/api-docs | Endpoint serving the OpenAPI JSON |
| /swagger-ui.html | Path to open the Swagger UI interface |
| servers[].url | API address that clients call |
| springdoc.swagger-ui.url | URL for Swagger UI to load an OpenAPI file |

Changing springdoc.swagger-ui.url does not automatically change servers[].url. Conversely, changing the server URL does not alter where the documentation is loaded from.

## 2. Inferred server URL vs. explicit server URL

There are two primary ways to provide the server URL:

| Approach | Data source | Suitable when |
|---|---|---|
| Inferred from request | Scheme, host, port, and context/prefix seen by the application | Multiple hostnames or different proxies serve the same application |
| Declared explicitly | Annotation or OpenAPI bean | Public base URL is fixed or environments need to be listed clearly |

springdoc can automatically generate a server URL when the document does not declare servers explicitly. If server annotations are present, those declarations are used instead of inferring from the request.

Distinguish springdoc's behavior from the default of a plain OpenAPI document: per the specification, if the servers field is absent or an empty list, the default server has the relative URL /. springdoc can generate a server URL based on the request when producing the document. Therefore, inspect the servers field in the output JSON rather than inferring solely from controller code.

Accordingly, decide which source is authoritative. If a fixed server is declared while expecting the URL to change dynamically based on proxy headers, results may not match expectations. If you want a request-derived server URL, do not inadvertently put a static servers list in your configuration.

## 3. How is the server URL inferred from the request?

When generating documentation, springdoc can use the current request information to construct the server URL. Key components include:

- Scheme: http or https.
- Host: domain name or IP address.
- Port: port used by the client.
- Context path or public prefix if present.

For example, an application running directly at:

~~~text
http://localhost:8080
~~~

Documentation requested from this address can publish the corresponding server URL. When running behind a proxy, internal requests may arrive at:

~~~text
http://10.0.0.12:8080
~~~

Whereas external clients use:

~~~text
https://api.example.com
~~~

If the application only sees the internal request without being given the original metadata, springdoc may infer an incorrect server URL for clients. This is why forwarded headers need to be configured on both the proxy and Spring Boot.

## 4. Headers describing the original request

There are two common groups of headers:

- Forwarded: the standard header defined in RFC 7239.
- X-Forwarded-*: a widely adopted set of header conventions predating Forwarded.

Headers commonly sent by proxies:

| Header | Information |
|---|---|
| Forwarded | Standard header that can carry proto, host, and proxy information |
| X-Forwarded-Host | Public host called by the client |
| X-Forwarded-Proto | Public scheme, typically http or https |
| X-Forwarded-Port | Public port |
| X-Forwarded-Prefix | Public prefix added by or rewritten by the proxy |
| X-Forwarded-For | Client IP address through the proxy chain |

For the server URL, the most important values are usually host, proto, port, and prefix. X-Forwarded-For primarily describes the client's IP address, not the API's hostname.

An example proxy-forwarded request may include:

~~~http
Forwarded: proto=https;host=api.example.com
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /gateway
~~~

The application must be configured to process these headers. Simply sending the headers from the proxy without Spring Boot reading them can still leave the inferred URL using the internal host and scheme.

## 5. Enabling forwarded-header processing in Spring Boot

Spring Boot provides the server.forward-headers-strategy property. To configure Spring Framework to process forwarded headers:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Or in application.properties:

~~~properties
server.forward-headers-strategy=framework
~~~

Common options:

| Value | Meaning |
|---|---|
| none | Do not apply forwarded headers |
| native | Use the web server/container's built-in handling |
| framework | Use Spring Framework's mechanism |

NATIVE depends on the container's capabilities. FRAMEWORK uses Spring Framework components to adjust request information according to forwarded headers.

For the Servlet stack, Spring Framework provides ForwardedHeaderFilter. For WebFlux, Spring Framework uses ForwardedHeaderTransformer. When choosing server.forward-headers-strategy=framework, Spring Boot manages the mechanism matching the web stack; you do not need to manually register an extra filter or transformer if Boot configuration already handles it.

Property names and default behaviors can change across Spring Boot releases. Always consult the documentation for your project's exact version, especially during major version upgrades.

## 6. Configuring the proxy to send public details

Nginx example forwarding requests from public prefix /gateway to an application running at the root path:

~~~nginx
location /gateway/ {
    proxy_pass http://order-service:8080/;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-Prefix /gateway;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
~~~

In this example:

- The client calls https://api.example.com/gateway/orders.
- The proxy forwards the request to http://order-service:8080/orders.
- The proxy supplies the public host, scheme, port, and prefix.
- The application processes forwarded headers to learn that the public URL has the /gateway prefix.

Actual proxy configuration depends on how proxy_pass rewrites paths, TLS termination, and the number of proxy layers. If the proxy does not strip the prefix from the path, or the application already has a matching context path, do not add the prefix a second time.

Do not copy sample configurations without checking the post-rewrite URL. Clearly identify the path the client calls, the path the proxy sends to the application, and the path Spring MVC/WebFlux receives.

## 7. Handling X-Forwarded-Prefix

X-Forwarded-Prefix is essential when a gateway adds a path segment on the public URL but removes that segment before forwarding the request to the backend.

Example:

~~~text
Public URL:
https://api.example.com/platform/orders

Backend URL:
http://order-service:8080/orders
~~~

The proxy can send:

~~~http
X-Forwarded-Prefix: /platform
~~~

The application processes the prefix so that generated URLs point to the public /platform path.

Without this header, the server URL in OpenAPI might simply be:

~~~text
https://api.example.com
~~~

Swagger UI would then call /orders instead of /platform/orders and receive a 404.

If the prefix appears twice, the URL can become:

~~~text
https://api.example.com/platform/platform/orders
~~~

Duplicate prefix errors usually occur when the proxy preserves the prefix in the request path while also sending X-Forwarded-Prefix, or when the application already configures a context path and adds the prefix again.

Test an actual request through the gateway to confirm precisely whether the prefix belongs to the server URL or the operation path.

## 8. Servlet and WebFlux handling of forwarded headers

The same Spring Boot configuration can apply to both web stacks, though the underlying components differ:

| Web stack | Spring Framework component |
|---|---|
| Spring MVC / Servlet | ForwardedHeaderFilter |
| Spring WebFlux / Reactive | ForwardedHeaderTransformer |

ForwardedHeaderFilter wraps the Servlet request so downstream components observe the forwarded scheme, host, port, and related metadata. ForwardedHeaderTransformer performs the corresponding role in WebFlux during ServerHttpRequest processing.

When using Spring Boot, prefer configuring the appropriate server.forward-headers-strategy. If registering components manually, understand the processing order and avoid registering duplicates alongside what Boot creates.

For WebFlux, if declaring the transformer directly under Spring Framework configuration, the bean is typically named forwardedHeaderTransformer to be recognized. Do not add a manual bean if Boot is already configuring the framework strategy.

## 9. Declaring server URLs explicitly with @OpenAPIDefinition

If the public base URL is fixed, servers can be declared in @OpenAPIDefinition:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/v1",
            description = "Production API"
        ),
        @Server(
            url = "https://sandbox-api.example.com/v1",
            description = "Sandbox API"
        )
    }
)
@Configuration
class OpenApiConfiguration {
}
~~~

OpenAPI will contain two servers for users to select in Swagger UI. Client generators can also use the server list as supported by the tool.

Once servers are explicitly declared, springdoc uses those servers instead of inferring URLs from the request. This is suitable when you want exact control over the public host and base path.

Avoid hard-coding production URLs across all environments if development or staging use different hostnames. Move URLs into environment configuration or use server variables where appropriate.

## 10. Declaring servers with an OpenAPI bean

You can create an OpenAPI bean and set servers using swagger-models:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import java.util.List;

@Configuration
class OpenApiServerConfiguration {

    @Bean
    OpenAPI customOpenAPI(Environment environment) {
        String publicBaseUrl =
            environment.getRequiredProperty("api.public-base-url");

        return new OpenAPI()
            .servers(List.of(
                new Server()
                    .url(publicBaseUrl)
                    .description("Public API")
            ));
    }
}
~~~

Configuration in application.yml:

~~~yaml
api:
  public-base-url: https://api.example.com/v1
~~~

application-dev.yml can replace it with:

~~~yaml
api:
  public-base-url: https://dev-api.example.com/v1
~~~

The advantage of an OpenAPI bean is that the URL can be sourced from properties, environment variables, or a config server. As a result, the same application artifact can run across multiple environments with the corresponding server URL.

When declaring an OpenAPI bean yourself, preserve other metadata such as Info, Components, security schemes, and tags if the application needs them. Do not accidentally create an empty OpenAPI definition that wipes out existing custom configuration.

## 11. Using ServerBaseUrlCustomizer to adjust the inferred URL

If the inferred URL is close but needs partial adjustment, springdoc provides ServerBaseUrlCustomizer. This extension point receives the generated server base URL and returns the modified value.

Example replacing an internal host with a public host in a specific deployment setup:

~~~java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ServerUrlCustomizationConfiguration {

    @Bean
    ServerBaseUrlCustomizer serverBaseUrlCustomizer() {
        return serverBaseUrl -> {
            String internalBase = "http://order-service:8080";
            String publicBase = "https://api.example.com";

            if (serverBaseUrl.startsWith(internalBase)) {
                return publicBase
                    + serverBaseUrl.substring(internalBase.length());
            }

            return serverBaseUrl;
        };
    }
}
~~~

This example illustrates replacing a known base URL while preserving the remainder of the path. In practice, only use string replacement when the mapping is unambiguous and environment-managed.

ServerBaseUrlCustomizer is suitable for normalizing URLs, such as stripping an internal port or adjusting the host. It does not replace configuring the proxy to send forwarded headers. If you need to infer the exact public URL from the request, handle forwarded headers first; the customizer should only perform supplemental adjustments.

Interface and extension point packages may vary across springdoc major versions. Check the API of your exact version before copying imports.

## 12. Choosing between proxy headers, explicit servers, and customizer

| Scenario | Suitable approach |
|---|---|
| One application served across multiple public hostnames | Forwarded headers from a trusted proxy |
| Fixed public URL per environment | OpenAPI bean reading the URL from properties |
| Need to publish both production and sandbox simultaneously | Explicit servers list |
| Inferred URL is mostly right but needs host/port normalization | ServerBaseUrlCustomizer |
| Gateway rewrites paths | X-Forwarded-Prefix or appropriate server base path configuration |
| Multiple proxies serve the same document with URLs varying per request | Forwarded headers and consider caching |
| Only want to change the URL from which Swagger UI loads the spec file | springdoc.swagger-ui.url, not servers |

Do not use a customizer to compensate for a proxy that fails to send proper headers. Likewise, do not declare static servers and expect the server URL to vary according to the request hostname.

## 13. Using multiple Server Objects for environments

OpenAPI allows listing multiple servers:

~~~yaml
servers:
  - url: https://dev-api.example.com/v1
    description: Development
  - url: https://staging-api.example.com/v1
    description: Staging
  - url: https://api.example.com/v1
    description: Production
~~~

Swagger UI can display a server dropdown for users to choose from. This is useful when users have access to multiple environments and want to test the same operation against each server.

Include only servers that are actually permitted to be published in the documentation. Do not expose internal hostnames, private IPs, or management URLs in a public spec if they are not meant for external clients.

If each environment has different auth, data, or policies, clearly document the differences and verify the corresponding security schemes. Switching servers does not automatically change credentials or access permissions.

## 14. Server Variables for URLs with variable parts

If URLs share a structure where one segment varies by environment, you can use server variables:

~~~yaml
servers:
  - url: https://{environment}.api.example.com/{basePath}
    description: API server
    variables:
      environment:
        default: api
        enum:
          - api
          - sandbox
      basePath:
        default: v1
~~~

Server variables avoid repeating multiple URLs with the same structure. Each variable requires a default; to restrict choices, you can declare an enum.

The example above builds the production URL https://api.api.example.com/v1 and sandbox URL https://sandbox.api.example.com/v1. If the real hostnames are api.example.com and sandbox-api.example.com, the two hostnames have different structures; listing two Server Objects is usually clearer.

A Server URL must be a valid URI and must not contain query strings or fragments. Do not use server variables to conceal complex mappings that clients cannot understand.

## 15. Server URLs at root, path, and operation levels

OpenAPI allows servers at multiple levels:

- Root OpenAPI Object: applies by default to the entire document.
- Path Item Object: applies to all operations under that path.
- Operation Object: applies specifically to a single operation.

A lower-level server overrides higher-level servers for its corresponding scope.

~~~yaml
servers:
  - url: https://api.example.com/v1

paths:
  /orders:
    get:
      responses:
        '200':
          description: Success

  /reports:
    servers:
      - url: https://reports.example.com
    get:
      responses:
        '200':
          description: Report
~~~

Operation /orders uses the root server https://api.example.com/v1. Path /reports uses its dedicated server https://reports.example.com.

When investigating Swagger UI calling the wrong host, inspect servers not only at the root. An operation or path may have overridden the global server.

## 16. Combining server URL with path and avoiding duplicate context path

Suppose the public API has the base URL:

~~~text
https://api.example.com/platform/v1
~~~

The path in OpenAPI should be:

~~~yaml
paths:
  /orders:
    get:
      responses:
        '200':
          description: Success
~~~

The final URL is:

~~~text
https://api.example.com/platform/v1/orders
~~~

Do not put /platform/v1 in the server URL and also declare path /platform/v1/orders, as the URL can end up with a duplicated prefix.

If the application has a context path or WebFlux base path, determine whether that segment is already included in the inferred server URL. Similarly, if the proxy sends X-Forwarded-Prefix, do not re-add the prefix in @Server or an OpenAPI bean without inspecting the resulting output.

An easy debugging technique is to write down three values: the public URL the user calls, the internal URL the proxy forwards to the backend, and the server URL inside the OpenAPI JSON.

## 17. Context path and springdoc endpoint path are two different settings

Spring Boot can run an application under a context path. Servlet stack example:

~~~yaml
server:
  servlet:
    context-path: /shop
~~~

In this case, the direct public URL can be https://api.example.com/shop. Swagger UI and the OpenAPI endpoint also sit under the context path unless configured otherwise.

API docs paths can be customized separately:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /internal/docs
~~~

api-docs.path adjusts the documentation endpoint. swagger-ui.path adjusts the UI path. They are not the operation server URL.

When changing the context path or springdoc paths, update proxy routing and security matchers accordingly. Do not assume changing documentation paths automatically adds a prefix to the API's server URL.

## 18. Handling server URLs across multiple proxies

A request may pass through a CDN, load balancer, ingress, and reverse proxy before reaching Spring Boot:

~~~text
Browser
  -> CDN
  -> API Gateway
  -> Kubernetes Ingress
  -> Spring Boot service
~~~

Each layer can modify the host, scheme, port, or path. Designate which proxy is the final authoritative source for writing forwarded headers.

Recommendations:

- The proxy at the trust boundary strips client-sent forwarded headers.
- The proxy creates or overwrites Forwarded/X-Forwarded-* with verified values.
- Downstream proxies carry forward only the controlled chain of metadata.
- The backend accepts traffic only from trusted proxies or networks.
- Do not expose the application publicly while trusting every forwarded header.

If each layer appends its own header values, the application may pick the wrong host or scheme. Establish clear infrastructure rules and inspect actual requests.

## 19. Security risks when trusting forwarded headers

Forwarded headers can be spoofed if clients send them directly to the application and the application trusts those values. An attacker can cause the documentation to generate an unintended host or influence absolute URLs built from the request.

To protect against this:

- Accept forwarded headers only from trusted proxies.
- The proxy at the trust boundary must strip or overwrite both Forwarded and X-Forwarded-* from external requests.
- Do not strip only one group of headers while letting the other group pass through.
- Restrict network access so clients cannot bypass the proxy and call the backend directly.
- Do not use an arbitrary client-sent Host header as the public base URL without validation.
- Verify redirects, absolute links, and OpenAPI server URLs after deployment.

ForwardedHeaderFilter and ForwardedHeaderTransformer can apply header information or solely remove headers in remove-only mode. Header processing does not replace configuring a trust boundary at the proxy.

## 20. OpenAPI caching and per-request changing server URLs

By default, springdoc computes the OpenAPI description and caches the result. This is usually appropriate when the server URL is stable.

However, if the same application is served across multiple hostnames or different proxies, the server URL inferred from the first request can remain cached. Subsequent requests through another hostname may receive the document containing the earlier URL.

If you need to recompute the OpenAPI description per request, caching can be disabled:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Or:

~~~properties
springdoc.cache.disabled=true
~~~

Enable this only when per-request dynamic URLs are genuinely required. Disabling caching can cause the OpenAPI document to be regenerated more frequently and increase processing overhead.

If servers are declared explicitly and do not vary by request, there is generally no need to disable caching solely for server URLs.

## 21. ServerBaseUrlCustomizer does not replace cache policy

ServerBaseUrlCustomizer adjusts the base URL value generated by springdoc. However, if the document is cached, changing requests or configuration will not necessarily trigger document regeneration on every call.

When URLs depend on the request:

1. The proxy sends accurate forwarded headers.
2. Spring Boot processes the forwarded headers.
3. springdoc infers the base URL from the adjusted request.
4. If needed, ServerBaseUrlCustomizer normalizes the URL.
5. Caching is configured appropriately if the URL must vary per request.

Do not add a customizer before verifying that the request already has the right host/scheme/prefix. If the input is wrong, a customizer may only mask part of the problem and make the configuration harder to maintain.

## 22. Distinguishing server URL from springdoc.swagger-ui.url

Two properties are commonly confused:

~~~yaml
springdoc:
  swagger-ui:
    url: /v3/api-docs
~~~

springdoc.swagger-ui.url specifies the URL from which Swagger UI loads the OpenAPI document. It does not determine the server URL used to send API requests.

Meanwhile, OpenAPI servers:

~~~yaml
servers:
  - url: https://api.example.com/v1
~~~

defines the base URL for operations when clients make requests.

For example, Swagger UI might load the spec from https://docs.example.com/specs/orders.json while the API server inside the spec is https://api.example.com/v1. This is a valid configuration. Documentation can be hosted on a separate domain describing an API on another domain.

## 23. Checking the server URL in OpenAPI JSON

After the application is running, fetch the document via the public URL:

~~~bash
curl -fsS https://api.example.com/gateway/v3/api-docs -o openapi.json
~~~

Inspect the server list:

~~~bash
jq '.servers' openapi.json
~~~

Inspect the first URL:

~~~bash
jq -r '.servers[0].url' openapi.json
~~~

Check whether an operation has its own server:

~~~bash
jq '.paths["/orders"].get.servers' openapi.json
~~~

Check whether a path item has its own server:

~~~bash
jq '.paths["/reports"].servers' openapi.json
~~~

Verify each component:

- Is the scheme https when clients connect over TLS?
- Is the host the public hostname?
- Is the port accurate or omitted when using the default port?
- Are the context path and X-Forwarded-Prefix both accounted for?
- Is the prefix duplicated?
- Are any internal hostnames or private IPs exposed?
- Does any path-level or operation-level server override the root?

Do not inspect the document only at localhost. Fetch the spec through the public hostname behind the reverse proxy because that is the URL real clients use.

## 24. Verifying with requests through the proxy

Call the public URL directly:

~~~bash
curl -i https://api.example.com/gateway/v3/api-docs
~~~

Save the spec and inspect servers:

~~~bash
curl -fsS https://api.example.com/gateway/v3/api-docs -o openapi.json
jq '.servers' openapi.json
~~~

If the application is served across multiple hosts, check each hostname:

~~~bash
curl -fsS https://api.example.com/gateway/v3/api-docs -o public.json
curl -fsS https://internal.example.com/gateway/v3/api-docs -o internal.json
~~~

If the server URL should vary per request, compare the servers field of both documents. If they match unexpectedly, inspect caching and the source of forwarded headers.

Do not use curl sending X-Forwarded-* directly from the Internet as a substitute for testing the proxy. Testing through the real proxy proves that the proxy sets headers properly and the backend trusts only the appropriate source.

## 25. Testing forwarded headers with WebTestClient

You can write an integration test that sends simulated forwarded headers to a test application with forwarded-header handling enabled:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ForwardedServerUrlTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void usesPublicForwardedServerAddress() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .header("X-Forwarded-Host", "api.example.com")
            .header("X-Forwarded-Proto", "https")
            .header("X-Forwarded-Port", "443")
            .header("X-Forwarded-Prefix", "/gateway")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.servers[0].url")
            .isEqualTo("https://api.example.com/gateway");
    }
}
~~~

Expected output depends on context path configuration, proxy rewrites, and the Spring Boot version. If the prefix is not processed in the test configuration, check properties and transformers rather than loosening the assertion to match a wrong URL.

This test verifies that the application interprets forwarded headers. It does not prove that the production proxy strips spoofed headers or writes correct headers. Deployment verification through the real gateway is still required.

## 26. Testing multiple requests and caching

If the same app is called through two hosts, you can write a test making consecutive requests with different headers. When URLs are required to vary per request, caching configuration must reflect that.

| Request | Forwarded host | Expected server result |
|---|---|---|
| Request A | api.example.com | https://api.example.com |
| Request B | partner.example.com | https://partner.example.com |
| Request C | api.example.com | https://api.example.com |

If Request B still receives Request A's server URL, check springdoc.cache.disabled and how documents are cached per request. If the system has only one public host, do not introduce unnecessary dynamic variants.

Cache tests should run against an application context configured like production. Do not test only the first request because cache bugs only surface when a second request arrives via another host.

## 27. Checking Swagger UI Try it out

Swagger UI uses the server URL in OpenAPI when sending requests. After loading the document via the public hostname:

1. Open Swagger UI at the public URL.
2. Check whether the server selector shows the intended URL.
3. Pick a safe GET operation.
4. Click Try it out and Execute.
5. Open the browser's Network tab.
6. Verify the request goes to the expected scheme, host, port, and prefix.
7. Check the response status and any CORS or path-related 404 errors.

If the server URL is wrong, Swagger UI may call an internal address unreachable by the browser. If the URL is right yet the request still fails, inspect CORS, authentication, API paths, and proxy routing separately.

Swagger UI may load the documentation successfully while Try it out still calls the wrong server. Therefore, /v3/api-docs endpoint tests should be paired with browser tests or checks of the actual request URL.

## 28. Common errors

| Symptom | Causes to check |
|---|---|
| OpenAPI publishes http while public site uses https | Missing or unprocessed X-Forwarded-Proto |
| Server URL contains internal hostname | X-Forwarded-Host not processed or wrong server declaration |
| Server URL contains internal port | Proxy header or container does not reflect public port |
| Missing /gateway prefix | Proxy does not send X-Forwarded-Prefix or Spring does not process it |
| Prefix appears twice | Prefix is already in request path/context path yet added again |
| Swagger UI calls localhost | Document generated from internal request or bad explicit server |
| Host changes but servers stay the same | OpenAPI document is cached |
| Customizer changes URL for wrong environment | Hard-coded host mapping or incorrect profile configuration |
| Root server is right but one operation is wrong | Path Item or Operation overrides servers |
| Changed swagger-ui.url but API still calls wrong host | Confusing spec load URL with servers[].url |
| Works locally but fails in production | Forwarded headers not tested through real proxy |
| Only one proxy works properly | Proxy layers overwrite forwarded headers inconsistently |

## 29. Environment-by-environment configuration workflow

When deploying, follow this order:

1. Identify the public URL and base path clients use.
2. Identify the request path and host the backend receives after proxy rewrite.
3. Configure the proxy to overwrite Forwarded or X-Forwarded-* with verified values.
4. Enable server.forward-headers-strategy matching the container and web stack.
5. If the server URL is fixed, declare servers via annotations or an OpenAPI bean.
6. If the server URL varies by request, let springdoc infer it from the forwarded-header-processed request.
7. Use ServerBaseUrlCustomizer only for controlled supplemental adjustments.
8. Configure caching if the same application is accessed through multiple public hosts.
9. Fetch /v3/api-docs via the public URL and inspect servers.
10. Test Try it out from Swagger UI and verify the request URL.
11. Audit hostnames, prefixes, and forwarded-header spoofing in deployment.

Do not mix multiple URL override mechanisms without knowing their precedence. When the documentation has explicit server annotations or an OpenAPI bean, verify whether that configuration is intentionally replacing the inferred server.

## 30. Checklist

- [ ] Determined whether the server URL comes from the request or explicit configuration.
- [ ] If using request-derived URLs, the proxy sends accurate host, proto, and port.
- [ ] If path rewriting is used, X-Forwarded-Prefix reflects the public prefix.
- [ ] Spring Boot processes forwarded headers according to the web stack.
- [ ] Forwarded headers from untrusted clients are never trusted.
- [ ] Boundary proxy strips or overwrites external Forwarded and X-Forwarded-*.
- [ ] Context path and forwarded prefix are not added twice.
- [ ] If using @OpenAPIDefinition, servers match the environment.
- [ ] If using an OpenAPI bean, the URL comes from an appropriate property.
- [ ] ServerBaseUrlCustomizer performs only controlled adjustments.
- [ ] Caching has been checked when URLs must vary per request.
- [ ] springdoc.swagger-ui.url is distinguished from servers[].url.
- [ ] servers have been checked at root, path, and operation levels.
- [ ] OpenAPI JSON does not leak internal hostnames or ports.
- [ ] Swagger UI Try it out calls the correct public URL.
- [ ] Verified through a real proxy, not only localhost.
- [ ] Tested multiple hostnames if the application serves multiple domains.

## 31. References

- [springdoc-openapi FAQ – Reverse proxy and ServerBaseUrlCustomizer](https://springdoc.org/faq.html)
- [Spring Boot – Embedded Web Servers and forwarded headers](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html)
- [Spring Framework – Forwarded Headers in Servlet stack](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Spring Framework – Forwarded Headers in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object)
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)

The Server URL determines the address clients and Swagger UI use to call operations. When inferred from the request, ensure the proxy forwards the accurate scheme, host, port, and prefix, and trust headers only from trusted proxies. When the URL is fixed or multiple environments are needed, declaring servers explicitly is easier to control. Always inspect the servers field in OpenAPI JSON via the public URL and verify that Try it out requests actually reach the right address.

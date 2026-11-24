# Context path, servlet path, and custom documentation paths

When deploying Spring Boot with springdoc-openapi, the URL that users see may differ from the URL that the application receives internally. A system can run behind a reverse proxy, sit under a context path, use custom servlet mapping, or configure custom OpenAPI/Swagger UI paths. If these layers are combined incorrectly, the Swagger UI page may open yet fail to load the OpenAPI JSON, redirect to an internal host, or send Try it out requests to the wrong prefix.

To configure this properly, you need to identify which layer is responsible for each part of the URL:

1. Reverse proxy determines the public host, scheme, and port, and may add or strip a path prefix.
2. Context path sets the prefix for the entire servlet application.
3. Servlet path sets the prefix for Spring MVC's DispatcherServlet.
4. WebFlux has its own base path for web handlers.
5. springdoc configures separate paths for the OpenAPI document and the Swagger UI page.

These layers can be combined, but the same prefix should not be declared in multiple places if requests do not actually pass through all of those layers.

## 1. Viewing a URL by its components

A complete URL looks like:

~~~text
https://api.example.com/platform/shop/mvc/api/orders
|      host       |proxy |context|servlet|controller
~~~

In this example:

| Component | Value | Where configured |
| --- | --- | --- |
| Scheme | https | TLS at the proxy and forwarded headers |
| Host | api.example.com | DNS, reverse proxy, Forwarded or X-Forwarded-Host |
| Proxy prefix | /platform | Routing/rewrite at the reverse proxy; can be passed via X-Forwarded-Prefix if the proxy stripped the prefix |
| Context path | /shop | server.servlet.context-path on the Servlet stack |
| Servlet path | /mvc | spring.mvc.servlet.path for DispatcherServlet |
| Controller mapping | /api/orders | @RequestMapping, @GetMapping, or the corresponding route |

Not every application needs all of these components. Most applications only need a controller mapping and possibly a context path or proxy prefix.

## 2. Distinguishing context path and servlet path

These two concepts are often confused because both appear as a prefix segment in the URL.

**Context path** is the root path of a web application within a servlet container. It applies to the entire servlet application, including controllers, static resources, Swagger UI, and the OpenAPI endpoint.

**Servlet path** is the path where a specific servlet is registered to receive requests. In Spring MVC, spring.mvc.servlet.path sets the prefix for DispatcherServlet; it is not the context path of the entire application.

| Criterion | Context path | Servlet path |
| --- | --- | --- |
| Scope | Entire servlet web application | DispatcherServlet or the mapped servlet |
| Spring Boot property | server.servlet.context-path | spring.mvc.servlet.path |
| Affects springdoc? | Yes; UI and OpenAPI live under the context path | May affect MVC mapping; actual compatibility must be verified |
| Use when | You want the application to run under a shared prefix | You need to map DispatcherServlet under a separate prefix |
| Used for WebFlux? | Does not use servlet context path | Does not use servlet path |

If the goal is simply to place the entire application under /shop, start with the context path. Do not add spring.mvc.servlet.path just to create another URL segment without an actual servlet mapping requirement.

## 3. Setting context path for Spring MVC

For a Spring Boot servlet application, configure server.servlet.context-path:

~~~yaml
server:
  servlet:
    context-path: /shop
~~~

Suppose a controller has the mapping:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    List<OrderResponse> list() {
        return orderService.findAll();
    }
}
~~~

The external path of the operation becomes:

~~~text
http://localhost:8080/shop/api/orders
~~~

springdoc also sits under the context path. With the default configuration, the URLs are typically:

| Resource | URL |
| --- | --- |
| Swagger UI | /shop/swagger-ui.html |
| OpenAPI JSON | /shop/v3/api-docs |
| OpenAPI YAML | /shop/v3/api-docs.yaml |
| Swagger UI config | /shop/v3/api-docs/swagger-config |

These are the default URLs; if the application changes the springdoc paths or configures a management port, the actual URLs will differ.

The springdoc FAQ also confirms that Swagger UI is placed under the context path—for example, with context path /foo, the UI URL is /foo/swagger-ui.html.

## 4. Setting servlet path for DispatcherServlet

In Spring MVC, you can set a servlet mapping prefix with:

~~~yaml
spring:
  mvc:
    servlet:
      path: /mvc
~~~

In that case, requests to DispatcherServlet typically take the form:

~~~text
/mvc/api/orders
~~~

If context path /shop is also set, the servlet URL may take the form:

~~~text
/shop/mvc/api/orders
~~~

However, spring.mvc.servlet.path has an important limitation: Spring Boot uses PathPatternParser as the default matching strategy, and this strategy is incompatible with configuring DispatcherServlet with a path prefix. Do not switch to a servlet path without thoroughly verifying the impact with the Spring Boot, Spring MVC, and springdoc versions in use.

If a separate servlet mapping is required, verify:

- The application starts up with the chosen path matching strategy.
- Controller mappings work at URLs with the servlet prefix.
- /v3/api-docs or the custom OpenAPI path is still mapped properly.
- Swagger UI loads swagger-config and WebJar resources.
- Security routes in Spring Security match the actual servlet path.

For a simple requirement of adding a prefix for the whole application, context path is usually more predictable than servlet path.

## 5. Using base path for Spring WebFlux

Reactive applications do not use server.servlet.context-path or spring.mvc.servlet.path. Spring Boot provides spring.webflux.base-path to set the base path for web handlers:

~~~yaml
spring:
  webflux:
    base-path: /shop
~~~

If a WebFlux application has route /api/orders, the URL will sit under base path /shop/api/orders. The springdoc endpoints registered in the same web application also need to be verified under this base path.

Do not mix Servlet and WebFlux configurations in the same guide:

| Stack | Application prefix |
| --- | --- |
| Spring MVC / Servlet | server.servlet.context-path |
| DispatcherServlet in Spring MVC | spring.mvc.servlet.path |
| Spring WebFlux | spring.webflux.base-path |

If a WebFlux application runs behind a proxy, forwarded headers are handled by the web server mechanism or ForwardedHeaderTransformer, not the Servlet stack's ForwardedHeaderFilter.

## 6. Changing the OpenAPI JSON/YAML path

By default, springdoc serves OpenAPI JSON at /v3/api-docs. This can be changed using springdoc.api-docs.path:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

The JSON document is then served at the custom path /openapi, relative to the application's context path or base path. For example, with context path /shop:

~~~text
/shop/openapi
~~~

springdoc also serves YAML. When changing the API docs path, verify the exact YAML URL generated by your springdoc version instead of assuming the old path still exists. With path /openapi, the YAML endpoint is typically served as /openapi.yaml.

You can disable the documentation endpoint with:

~~~yaml
springdoc:
  api-docs:
    enabled: false
~~~

Disabling the OpenAPI endpoint does not disable Swagger UI via the same property. If you want to disable both, configure springdoc.swagger-ui.enabled separately and verify the actual endpoints.

## 7. Changing the Swagger UI page path

To change the HTML URL of Swagger UI, use springdoc.swagger-ui.path:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs.html
~~~

With context path /shop, the UI page opens at:

~~~text
/shop/docs.html
~~~

You can combine the OpenAPI path and the Swagger UI path:

~~~yaml
server:
  servlet:
    context-path: /shop

springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs.html
~~~

Expected public URLs:

| Resource | URL |
| --- | --- |
| Swagger UI | /shop/docs.html |
| OpenAPI JSON | /shop/openapi |
| OpenAPI YAML | Check the YAML endpoint corresponding to the custom docs path |
| Swagger config | Check the config endpoint generated for the docs path |

springdoc.swagger-ui.path changes the HTML URL of the UI; it does not change business API paths and does not automatically change the reverse proxy's public URL.

## 8. Distinguishing UI custom path and OpenAPI document URL

Swagger UI needs to know where to load the OpenAPI document. Normally springdoc generates the Swagger UI configuration pointing to the corresponding OpenAPI endpoint.

The two properties serve different roles:

| Property | Effect |
| --- | --- |
| springdoc.swagger-ui.path | HTML URL that users open to view the UI |
| springdoc.api-docs.path | JSON URL of the OpenAPI contract |
| springdoc.swagger-ui.config-url | URL for fetching Swagger UI configuration |
| springdoc.swagger-ui.url | URL of a directly specified OpenAPI document |

Setting only swagger-ui.path does not change the JSON endpoint. Setting only api-docs.path does not necessarily change the UI HTML URL either.

If you need to point Swagger UI to an external OpenAPI file or a document hosted elsewhere, you can use springdoc.swagger-ui.url or configure multiple URLs via the Swagger UI feature. In that case, you must check CORS and browser access permissions to that document source.

If you set config-url manually, make sure the URL points to an existing Swagger UI config endpoint. A stale config-url can cause the UI HTML to open while displaying an error stating it cannot load the configuration.

## 9. Combining context path and custom docs path

Full example for Spring MVC:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /inventory

springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs.html
~~~

Assuming the controller mapping is /api/products, the internal URLs are:

~~~text
GET http://localhost:8080/inventory/api/products
GET http://localhost:8080/inventory/openapi
GET http://localhost:8080/inventory/docs.html
~~~

If there is a group named admin, the OpenAPI group typically sits under the docs path, for example:

~~~text
http://localhost:8080/inventory/openapi/admin
~~~

Verify the group endpoint after changing springdoc.api-docs.path; do not hard-code /v3/api-docs/{group} in portals or scripts if the path has been customized.

## 10. A reverse proxy can add or strip a path prefix

A reverse proxy often exposes a public URL and forwards requests to a different backend URL.

Example:

~~~text
Client:
https://api.example.com/platform/openapi

Proxy forwards:
http://spring-app:8080/openapi
~~~

In this case, the proxy stripped the /platform prefix before forwarding the request. The application only sees /openapi, so if it needs to generate correct public links, the proxy must pass the original prefix information via X-Forwarded-Prefix.

Common forwarded headers:

| Header | Meaning |
| --- | --- |
| Forwarded | Standard RFC 7239 header carrying host/proto and proxy information |
| X-Forwarded-For | Original client IP or proxy chain |
| X-Forwarded-Host | Host used by the client on the public side |
| X-Forwarded-Port | Public port |
| X-Forwarded-Proto | Public scheme, e.g. https |
| X-Forwarded-Prefix | Public path prefix stripped by the proxy before forwarding |

X-Forwarded-Prefix is not a header for arbitrarily adding a new path. It represents the original prefix that was removed along the forwarding path.

If the proxy keeps the prefix intact in the request sent to the application, do not send the same prefix again as if it had been stripped. If the prefix is kept and the application also appends the forwarded prefix, URLs can become duplicated as /platform/platform/....

## 11. Nginx example stripping prefix and passing forwarded headers

Example where a proxy exposes the application under /platform and strips the prefix before sending the request to the backend:

~~~nginx
location /platform/ {
    proxy_pass http://spring-app:8080/;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Prefix /platform;
}
~~~

With the proxy_pass configuration having URI / above, Nginx replaces the path portion matching the location with the proxy_pass URI, so /platform/openapi is forwarded to the backend as /openapi. Check the actual rewrite configuration if your project's location or proxy_pass differs from the example.

From the client side:

~~~text
https://api.example.com/platform/openapi
https://api.example.com/platform/docs.html
~~~

From the backend side:

~~~text
http://spring-app:8080/openapi
http://spring-app:8080/docs.html
~~~

The proxy needs to strip or overwrite forwarded headers sent by clients from the Internet before setting trusted values. Do not allow clients to pick X-Forwarded-Host, X-Forwarded-Proto, or X-Forwarded-Prefix and let the application use them to generate URLs.

## 12. Handling forwarded headers by Spring Boot version

Spring Boot and Spring Framework have changed property names and forwarded-header handling across versions. Use the configuration that matches your application's dependency version.

**Spring Boot 2.2 through Boot 3.x lines** typically use:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

The framework value uses Spring Framework's forwarded-header handling mechanism. For the Servlet stack, that is ForwardedHeaderFilter; for the reactive stack, Spring Framework uses ForwardedHeaderTransformer. Depending on the web server and header types, the native strategy can be chosen if the server supports it fully.

**Current Spring Boot 4.x** uses a new namespace for forwarded headers:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server
        use-prefix: true
~~~

strategy: web-server uses the embedded web server's forwarded-header support. use-prefix: true enables X-Forwarded-Prefix handling; according to Spring Boot 4.2 documentation, this prefix header is ignored by default.

If the web server does not provide full support or you need Spring Framework's generic mechanism, you can use:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: framework
        use-prefix: true
~~~

Do not mix the two generations of properties in the same configuration without checking the version. The springdoc FAQ documentation still shows server.forward-headers-strategy; newer Spring Boot documentation uses server.request.header.forwarded.*. Always prioritize the property reference matching the Boot version you are running.

## 13. ForwardedHeaderFilter and ForwardedHeaderTransformer

Spring Framework provides two mechanisms depending on the web stack:

| Web stack | Spring Framework mechanism |
| --- | --- |
| Servlet / Spring MVC | ForwardedHeaderFilter |
| Reactive / Spring WebFlux | ForwardedHeaderTransformer |

They adjust request information to reflect the public scheme, host, port, and prefix based on forwarded headers. This allows the framework and springdoc to generate redirects, links, and server URLs matching the address the client sees.

In Spring Boot, prefer the built-in forwarded-header configuration properties before registering a filter or transformer manually. Avoid registering two mechanisms that process the same set of headers unless you understand their ordering and impact.

If you only want to strip forwarded headers without trusting their values, Spring Framework provides a removeOnly mode on the corresponding components. This is a useful option when the application is not behind a trusted proxy yet still needs to strip forged headers sent by clients.

## 14. Security risks of forwarded headers

An application cannot tell on its own whether a forwarded header was added by a trusted proxy or sent directly by a malicious client. If the backend is directly reachable from the Internet and still trusts X-Forwarded-Host, an attacker can influence the generated URLs.

Risk examples:

- OpenAPI server URL is generated with an attacker-controlled host.
- Redirects point to an unintended host.
- Links on the Swagger UI page point to a spoofed domain.
- Logs or audits record an incorrect original IP/protocol.
- Policies based on host or scheme are bypassed.

Countermeasures:

1. Only trust forwarded headers from proxies/load balancers within the trust boundary.
2. The proxy must strip client-sent forwarded headers and write canonical values itself.
3. Restrict direct access to the backend via network policy or firewall where appropriate.
4. Configure trusted proxy/IP ranges on the web server if that mechanism supports it.
5. Do not allow arbitrary client-supplied host or prefix values to be used for building public URLs.
6. Verify generated URLs in OpenAPI and redirects in staging environments.

## 15. When is ServerBaseUrlCustomizer needed?

springdoc provides ServerBaseUrlCustomizer to adjust the server base URL inferred when generating documentation. It can be used when forwarded headers are already handled properly but custom rules are still required, such as removing an internal port or normalizing the base URL.

Example:

~~~java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiServerUrlConfig {

    @Bean
    ServerBaseUrlCustomizer serverBaseUrlCustomizer() {
        return serverBaseUrl -> {
            if (serverBaseUrl.startsWith("http://spring-app:")) {
                return serverBaseUrl.replace(
                    "http://spring-app:8080",
                    "https://api.example.com"
                );
            }
            return serverBaseUrl;
        };
    }
}
~~~

This is an example illustrating the principle, not a rule for replacing proxy configuration. In production, avoid hard-coding the host if the application has multiple domains or environments. The public base URL can be read from environment-managed configuration.

If the customizer has to split host/port strings with complex logic, consider using the URI/URL API and inspecting scheme, host, port, and path separately. Do not use a broad replace that could accidentally alter valid paths or hosts.

## 16. Separating public URL from OpenAPI server URL

OpenAPI has servers to describe the base URL that clients use when calling the API. When springdoc infers the server URL from the request, forwarded headers can affect the generated host, scheme, port, and prefix.

Example of a desired public contract:

~~~yaml
servers:
  - url: https://api.example.com/platform
    description: Public API gateway
paths:
  /api/orders:
    get:
      responses:
        '200':
          description: List of orders
~~~

When Swagger UI sends a request, the URL is assembled by combining the server URL and the operation path. If the server URL is missing /platform, Try it out requests may bypass the proxy route. If the server URL contains /platform/platform, requests will duplicate the prefix.

Do not add the context path or proxy prefix to both servers.url and the operation path if the operation path already contains that prefix. Decide which part belongs to the server base URL and which part belongs to the API path.

If you use an OpenAPI bean to declare static servers, static values may not reflect multiple hosts or multiple environments. In that case, configure per profile or use an appropriate customization mechanism; do not expect forwarded headers to alter a servers object that has been fixed by the application's own configuration.

## 17. Verifying URLs after deployment

Testing should be performed in both places: calling the backend directly and calling through the public proxy.

Example configuration:

- Context path: /shop
- OpenAPI path: /openapi
- Swagger UI path: /docs.html
- Public proxy prefix: /platform and the proxy strips the prefix before forwarding

Expected URLs:

| Location | URL |
| --- | --- |
| Backend OpenAPI JSON | http://localhost:8080/shop/openapi |
| Backend Swagger UI | http://localhost:8080/shop/docs.html |
| Public OpenAPI JSON | https://api.example.com/platform/shop/openapi |
| Public Swagger UI | https://api.example.com/platform/shop/docs.html |

Test requests:

~~~bash
curl -i http://localhost:8080/shop/openapi
curl -i http://localhost:8080/shop/docs.html

curl -i https://api.example.com/platform/shop/openapi
curl -i https://api.example.com/platform/shop/docs.html
~~~

If the proxy strips /platform, the backend receives /shop/openapi; the X-Forwarded-Prefix: /platform header helps the framework reconstruct the public URL. If the proxy preserves /platform when forwarding, the mapping must be redesigned so the prefix is not added a second time.

Checking Swagger UI in the browser:

1. The HTML page opens at the public URL.
2. The request loading swagger-config returns 200.
3. The OpenAPI JSON URL in the config is the public URL, not the backend hostname or port.
4. OpenAPI JSON loads in the browser.
5. JS/CSS/WebJar resources do not return 404.
6. The server URL in the document uses https and the correct public host.
7. Try it out sends requests to the URL with the correct proxy/context prefix.
8. There are no missing or duplicated prefixes.

## 18. Common issues and how to isolate them

| Symptom | Common cause | How to check |
| --- | --- | --- |
| /swagger-ui.html returns 404 when context path is set | Forgot to include context path | Open the URL with /context-path/swagger-ui.html |
| UI page opens but spec is 404 | UI config still points to the old docs path | Check swagger-config and springdoc.api-docs.path |
| OpenAPI JSON contains backend host | Forwarded host/proto not handled | Check forwarded headers and strategy |
| OpenAPI server URL uses http even though public is https | Proxy does not pass X-Forwarded-Proto or app does not process it | Check proxy and forwarded-header strategy |
| Public URL is missing prefix | Proxy strips prefix without sending X-Forwarded-Prefix or app ignores the header | Check headers and prefix support configuration |
| URL has /platform/platform | Prefix is already preserved in request yet added again from forwarded header | Choose one consistent way to handle the prefix |
| UI opens but JS/CSS return 404 | Base path or proxy rewrite is inconsistent with WebJar paths | Check Network tab and resource requests |
| MVC controller returns 404 after adding servlet path | DispatcherServlet mapping and path matching are incompatible | Check PathPatternParser and spring.mvc.servlet.path |
| Backend works but proxy returns 502/404 | Incorrect proxy location, rewrite, or upstream mapping | Record paths before/after the proxy and check access logs |
| Swagger UI Try it out calls localhost | Server URL or OpenAPI config was generated from an internal request | Check servers, forwarded host, and customizer |
| Redirect switches to an unfamiliar host | Forwarded headers are not filtered at the trust boundary | Strip client-sent headers and only trust reliable proxies |

When debugging, record three distinct URLs: the URL the client calls, the URL the proxy sends to the backend, and the URL generated by OpenAPI/Swagger UI. This helps pinpoint which layer adds or drops a prefix.

## 19. Checklist before changing paths

- [ ] Identify whether the application runs Spring MVC or Spring WebFlux.
- [ ] Determine whether a context path or WebFlux base path is needed.
- [ ] Use servlet path only when you genuinely need a separate DispatcherServlet mapping.
- [ ] Check PathPatternParser limitations if using spring.mvc.servlet.path.
- [ ] Set springdoc.api-docs.path for OpenAPI JSON.
- [ ] Set springdoc.swagger-ui.path for HTML UI.
- [ ] Check the swagger-config URL after changing the docs path.
- [ ] Determine whether the proxy keeps or strips the public prefix.
- [ ] Configure X-Forwarded-Prefix only when the prefix has been stripped.
- [ ] Choose the forwarded-header strategy matching your Spring Boot version.
- [ ] Configure the proxy to strip untrusted forwarded headers.
- [ ] Verify that servers in OpenAPI use the public host, scheme, and prefix.
- [ ] Test UI, JSON/YAML spec, and Try it out through the public proxy.
- [ ] Test backend URLs as well to separate application errors from proxy errors.

## 20. Recommended deployment workflow

1. Run the application locally with default URLs and verify /v3/api-docs along with /swagger-ui.html.
2. Add a context path or WebFlux base path if the application needs an internal prefix.
3. Change the OpenAPI path and Swagger UI path with springdoc properties when needed.
4. Re-verify JSON, YAML, swagger-config, and UI resources locally.
5. Configure the reverse proxy and explicitly define whether the prefix is kept or stripped.
6. Pass Forwarded or X-Forwarded-* from a trusted proxy.
7. Enable forwarded-header support matching the Spring Boot version and web stack.
8. Verify OpenAPI servers and links in Swagger UI from the public URL.
9. Run tests through the proxy to confirm redirects, docs endpoints, and Try it out.
10. Maintain trust boundary controls so clients cannot spoof forwarded headers.

When each layer is responsible only for its own portion of the prefix, controller URLs, the OpenAPI document, and Swagger UI remain consistent across local, staging, and production. springdoc can generate accurate documentation behind a proxy without hard-coding every URL in annotations or controller code.

## References

- [springdoc-openapi – FAQ: Deploy behind a reverse proxy](https://springdoc.org/faq.html)
- [springdoc-openapi – Getting Started and default/custom paths](https://springdoc.org/getting-started.html)
- [springdoc-openapi – Core Properties](https://springdoc.org/core-properties.html)
- [Spring Boot – Embedded Web Servers: Forwarded Headers and Prefix Support](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Boot – Servlet Web Applications and Path Matching](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot – Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Framework – ForwardedHeaderTransformer](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)

# Forwarded Headers, HTTPS, and Absolute Link Correctness in Spring Data REST

## Goal

When Spring Data REST runs behind a reverse proxy or load balancer, the request reaching the application often no longer preserves the information that the client sees. A client may call:

~~~text
https://api.example.com/api/products
~~~

but the proxy forwards it to:

~~~text
http://10.0.0.12:8080/products
~~~

If the application only sees the internal request, HAL links such as `_links.self.href`, `_links.profile.href`, or the `Location` header after creating a resource may contain `http`, an internal hostname, port `8080`, or be missing the public path prefix. External clients cannot reliably use those URLs.

Spring Data REST generates links based on the current request. To generate absolute URLs accurate from the external perspective, the proxy must pass the original information via forwarded headers, and the application must be configured to trust and process those headers.

## 1. Key Forwarded Headers

There are two common groups of headers:

- Standard RFC 7239 header: `Forwarded`.
- Convention-based header group: `X-Forwarded-*`.

Example of the standard header:

~~~http
Forwarded: for=203.0.113.10;proto=https;host=api.example.com
~~~

Example of the `X-Forwarded-*` group:

~~~http
X-Forwarded-For: 203.0.113.10
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /api
~~~

Common meanings:

| Header | Information Restored |
| --- | --- |
| `Forwarded` | Attributes such as `proto`, `host`, and `for` in a single standard header |
| `X-Forwarded-Proto` | Public scheme, for example `https` |
| `X-Forwarded-Host` | Public host, for example `api.example.com` |
| `X-Forwarded-Port` | Public port, for example `443` |
| `X-Forwarded-Prefix` | Public URL prefix added, stripped, or replaced by the proxy |
| `X-Forwarded-For` | Original client address; typically used for logging and access control, does not determine link scheme/host |

Spring Framework supports both `Forwarded` and `X-Forwarded-*`. The `X-Forwarded-Host`, `X-Forwarded-Port`, `X-Forwarded-Proto`, and `X-Forwarded-Prefix` headers are common conventions, not RFC 7239 standard headers.

## 2. Why Do Spring Data REST Links Break Behind a Proxy?

Spring Data REST is a Spring MVC application and typically returns HAL representations with absolute links. For example, a response when running directly on a local machine might contain:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/products"
    }
  }
}
~~~

In a production environment, clients need the public URL:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/products"
    }
  }
}
~~~

Proxies alter the scheme, host, port, or path along the forwarding path. Spring Framework can restore the original details from forwarded headers before Spring Data REST/Spring HATEOAS generates links. For the Servlet stack, the primary component is `ForwardedHeaderFilter`; for WebFlux, the corresponding component is `ForwardedHeaderTransformer`.

Without enabling forwarded header handling, the request may be perceived as `http://10.0.0.12:8080`, even though the client actually called HTTPS on `api.example.com`.

## 3. Spring Boot Configuration

With current Spring Boot versions, choose `server.forward-headers-strategy` based on your environment's capabilities:

| Value | Meaning |
| --- | --- |
| `NATIVE` | Uses the running web server/container's native forwarded-header support. Exact behavior depends on Tomcat, Jetty, or Undertow. |
| `FRAMEWORK` | Uses Spring Framework's support; the Servlet stack handles this with `ForwardedHeaderFilter`. |
| `NONE` | Ignores forwarded headers. |

If you need Spring Framework to handle host, port, scheme, and prefix completely, you can configure:

~~~properties
server.forward-headers-strategy=FRAMEWORK
~~~

Or YAML:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Spring Boot uses this setting to install the forwarded-header mechanism appropriate for the web stack. If the proxy only sends common headers like `X-Forwarded-For` and `X-Forwarded-Proto`, `NATIVE` may suffice when the container supports them. When `X-Forwarded-Host`, `X-Forwarded-Port`, or `X-Forwarded-Prefix` are also needed, check the container's capabilities; choose `FRAMEWORK` if Spring's handling is required.

Do not rely on the default value: Spring Boot may select `NATIVE` on certain supported cloud platforms and `NONE` in other environments. Configure it explicitly per deployment.

When using Tomcat with TLS terminated at the proxy, Spring Boot notes you may need:

~~~properties
server.tomcat.redirect-context-root=false
~~~

This setting ensures `X-Forwarded-Proto` is honored before Tomcat performs a redirect at the context root.

### 3.1. Without Spring Boot

In a self-configured Spring MVC application, register `ForwardedHeaderFilter` as a Servlet filter. For example, when configuring via a Spring bean:

~~~java
@Bean
ForwardedHeaderFilter forwardedHeaderFilter() {
    return new ForwardedHeaderFilter();
}
~~~

If registering manually via `FilterRegistrationBean`, `web.xml`, or a Servlet initializer, place the filter before filters that need to read the modified request, such as `RequestContextFilter`. When manually declaring dispatcher types, consider including `REQUEST`, `ASYNC`, and `ERROR` so async requests and error dispatches are handled properly.

For WebFlux, use `ForwardedHeaderTransformer` instead of a Servlet filter:

~~~java
@Bean
ForwardedHeaderTransformer forwardedHeaderTransformer() {
    return new ForwardedHeaderTransformer();
}
~~~

Spring Data REST uses Spring MVC, so configuring the Servlet filter is the appropriate path for exported REST repositories.

## 4. Proxy Configuration and Path Prefixes

The proxy must send the exact details that the external client used. For example:

- The client calls `https://api.example.com/api/products`.
- The proxy terminates TLS at the edge, then forwards the request to the service over HTTP.
- The proxy sends `X-Forwarded-Proto: https`, `X-Forwarded-Host: api.example.com`, and `X-Forwarded-Port: 443`.
- If the proxy strips the `/api` prefix before forwarding, it also sends `X-Forwarded-Prefix: /api`.

Spring Data REST has its own base path configuration. For example:

~~~properties
spring.data.rest.basePath=/api
~~~

Or configured via `RepositoryRestConfigurer` and `RepositoryRestConfiguration.setBasePath("/api")`. This base path defines Spring Data REST's export path; it does not replace the scheme, host, or port details provided by forwarded headers.

Distinguish three concepts:

- `spring.data.rest.basePath`: prefix for Spring Data REST resources.
- `server.servlet.context-path`: context path of the entire Servlet application.
- `X-Forwarded-Prefix`: public prefix that the proxy needs restored when internal and external URLs differ.

Choose the configuration matching the exact transformation the proxy performs:

**Case A — Proxy preserves the prefix**

If the proxy forwards `/api/products` as `/api/products` and Spring Data REST is also configured with `basePath=/api`, do not mechanically add `X-Forwarded-Prefix: /api` again. Check the final link to avoid producing `/api/api/products`.

**Case B — Proxy strips the prefix before forwarding**

If the public URL is `/api/products` while the service receives `/products`, the proxy must provide the original prefix via `X-Forwarded-Prefix: /api`. Configure the filter and internal routes so requests still map properly while generated links use the public path.

**Case C — Proxy replaces the prefix**

Spring Framework supports scenarios where a prefix is replaced, stripped, or added. For example, public path `/api/{path}` may be forwarded to internal path `/app1/{path}`; the proxy sends `X-Forwarded-Prefix: /api` so returned links use the public prefix.

Do not stack prefixes across the proxy, context path, Spring Data REST base path, and forwarded prefix without verifying the actual output.

## 5. Request and Response Examples

Suppose a Spring Data REST application receives internal requests at `localhost:8080`, while clients access it via `https://api.example.com`. With `FRAMEWORK` configured, try sending the following headers:

~~~bash
curl -i http://localhost:8080/products \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: api.example.com' \
  -H 'X-Forwarded-Port: 443'
~~~

The HAL links generated from the restored request might look like:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/products"
    }
  }
}
~~~

If the proxy also strips the `/api` prefix before forwarding, additionally send:

~~~http
X-Forwarded-Prefix: /api
~~~

When the prefix is configured correctly, the public link must contain `/api` exactly once. If the public port is the default HTTPS port (`443`), the URI may omit `:443`; what matters is that the scheme and authority point to the public host.

Also check:

- `_links.self.href` on collection and item resources.
- Navigation/search/profile links generated by Spring Data REST.
- The `Location` header after a POST that creates a resource.
- The `Location` header or target URL of redirects if the application performs redirects.

## 6. Testing

### 6.1. Verifying HAL Links with a Forwarded Origin Using MockMvc

Enable the strategy in your test configuration:

~~~properties
server.forward-headers-strategy=FRAMEWORK
~~~

Then send a request with forwarded headers and verify that links use HTTPS with the public host:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ForwardedLinksIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void halLinksUseThePublicOrigin() throws Exception {
        mvc.perform(get("/products")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "api.example.test")
                .header("X-Forwarded-Port", "443"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href",
                    startsWith("https://api.example.test/")));
    }
}
~~~

A repository and test data are needed for the `/products` endpoint to return a HAL representation. Ensure MockMvc has the filter installed; if the test configuration excludes filters, the test only checks the internal request and does not verify forwarded-header behavior.

### 6.2. Verifying Prefixes

If the deployment uses proxy rewrites, add a test with `X-Forwarded-Prefix`:

~~~java
mvc.perform(get("/products")
        .header("X-Forwarded-Proto", "https")
        .header("X-Forwarded-Host", "api.example.test")
        .header("X-Forwarded-Prefix", "/api"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href",
            containsString("/api/products")));
~~~

Adjust the request URL and base path configuration to match your project's internal routes. Assert that the link contains the prefix once, not merely that `/api` appears somewhere.

### 6.3. Verifying Location After POST

Send a POST request to create an entity via MockMvc with the same forwarded headers. Assert that the `Location` header starts with `https://api.example.test/` and contains the public path. This test catches cases where HAL links are right but the URL in the response header still uses the internal host.

### 6.4. Verifying Behind a Real Proxy

MockMvc verifies the application's filter, not the reverse proxy configuration. In staging or an integration environment:

1. Call the endpoint using the public HTTPS URL.
2. Inspect the HAL response and `Location` header.
3. Confirm there is no internal hostname, internal port, or `http` scheme.
4. Check that the prefix is neither missing nor duplicated.
5. Try sending forged `Forwarded`/`X-Forwarded-*` headers from the client and confirm the edge proxy overwrites/strips untrusted headers.

Run tests using your project's build command, such as `./mvnw test` or `mvn test`.

## 7. Troubleshooting

**Links still use `http://` even though the client accesses HTTPS**

- Confirm the proxy sends `X-Forwarded-Proto: https` or `Forwarded: proto=https`.
- Check that `server.forward-headers-strategy` is not `NONE`.
- If using `NATIVE`, verify the running container properly supports the header; try `FRAMEWORK` when Spring handling is needed.
- With Tomcat terminating TLS at the proxy, check `server.tomcat.redirect-context-root=false` if the issue occurs during context root redirects.

**Links use an internal host or `localhost`**

- Check `X-Forwarded-Host` or the `host` attribute in `Forwarded`.
- Check whether the proxy overwrites client-supplied headers.
- Verify the forwarded filter/strategy is enabled before Spring Data REST generates links.

**Links contain an internal port like 8080 or the wrong port**

- Check `X-Forwarded-Port` and `X-Forwarded-Host`.
- Confirm the container or Spring Framework is processing the original port.
- Note that the default port `443` may be omitted in a valid HTTPS URI.

**Links are missing a prefix or duplicate `/api/api`**

- Write down the public path, the path the proxy forwards to the service, `server.servlet.context-path`, `spring.data.rest.basePath`, and `X-Forwarded-Prefix`.
- Determine whether the proxy preserves, strips, or replaces the prefix.
- Keep only one configuration representing each rewrite step; verify using the final URL in HAL and `Location`.

**Some links are right, while others are still wrong**

- Check which links are generated by Spring Data REST/Spring HATEOAS from the request and which are manually concatenated by application code.
- Do not hard-code `http://localhost`, internal hostnames, or container ports in custom link builders.
- Use URI/link builders backed by the request processed by the forwarded filter, or configure a public base URI in a controlled way if a link is genuinely not tied to the request.

**Headers appear in request logs but the application ignores them**

- Check whether the filter is registered and runs before `RequestContextFilter`.
- Check whether the application uses Servlet or WebFlux; choose `ForwardedHeaderFilter` for Servlet and `ForwardedHeaderTransformer` for WebFlux.
- If registering the filter manually, check dispatcher types for `ASYNC` and `ERROR` when the application uses async/error dispatches.
- Confirm the header format sent by the proxy matches the format Spring is configured to process.

**Behavior varies across environments**

- Do not rely on the default for `server.forward-headers-strategy`; some cloud platforms have different defaults than self-managed environments.
- Set explicit configuration per environment and test after every proxy/container change.
- Check both direct requests to the service and requests through the proxy; the two paths may have different schemes, hosts, and prefixes.

## 8. Security When Trusting Forwarded Headers

Forwarded headers can alter the scheme, host, port, and base URL that the application uses to build links. If the application accepts these headers directly from the Internet without a trusted proxy enforcing control, clients can spoof the host or scheme and cause the application to generate malicious or misleading URLs.

Follow these principles:

- Proxies at the trust boundary must strip or reset both `Forwarded` and `X-Forwarded-*` sent by clients, then set the trusted values themselves.
- Do not expose direct access paths to the backend if the architecture requires all requests to pass through a trusted proxy.
- Only enable forwarded header processing when the deployment has a trusted proxy and it is clear which headers are used.
- Do not configure the application to trust all proxies in production.
- If you only need to strip forwarded headers without using their values, Spring Framework provides a `removeOnly` mode for the filter.

Spring Framework notes that proxies at the trust boundary should reset both the standard `Forwarded` header and the `X-Forwarded-` group to protect applications that may inspect both types.

## 9. Official Documentation

- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): `server.forward-headers-strategy`, choosing `NATIVE`/`FRAMEWORK`, HTTPS proxies, and Tomcat.
- [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring/reference/web/webmvc/filters.html): meaning of `Forwarded`, `X-Forwarded-*` headers, host/port/scheme/prefix handling, filter ordering, and security.
- [Spring Data REST — Configuring the REST URL Path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html): HAL examples with absolute hrefs, repository path, and `rel`.
- [Spring Data REST — Getting Started / Changing the Base URI](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): `spring.data.rest.basePath` and `RepositoryRestConfigurer.setBasePath(...)`.
- [Spring HATEOAS — Forwarded header handling](https://docs.spring.io/spring-hateoas/docs/2.5.1/reference/html/): example registering `ForwardedHeaderFilter`, sending `X-Forwarded-Proto/Host/Port`, and resulting HAL links with the public origin.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): definition of the standard `Forwarded` header.

Property names and defaults can vary across Spring Boot versions. Cross-check the documentation matching the version in your build, then verify the returned URLs through a real proxy before deploying.

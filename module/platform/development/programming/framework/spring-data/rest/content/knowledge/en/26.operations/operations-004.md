# Restricting Trusted Proxies to Prevent Link Generation from Spoofed Hosts

## 1. Problem and Impact on Spring Data REST

A Spring Data REST application typically runs behind a reverse proxy, ingress controller, or load balancer. Clients access the API via a public URL such as:

    https://api.example.com/api/orders

Meanwhile, the proxy may forward the internal request to:

    http://10.20.0.15:8080/api/orders

The application behind the proxy sees the host, port, and scheme of the internal connection. To generate accurate return URLs for the client, the proxy can pass original request information via headers:

- Forwarded: standard header per RFC 7239, which can carry host, proto, and hop information.
- X-Forwarded-Host: the public host called by the client.
- X-Forwarded-Proto: the public scheme, typically https or http.
- X-Forwarded-Port: the public port.
- X-Forwarded-For: the client IP address along the proxy chain.
- X-Forwarded-Prefix: the public path prefix if the proxy rewrites the path.

Spring Framework can use these headers to reconstruct the request from the client's perspective. Host and scheme details can then be used when generating redirects or links in JSON. Spring Data REST returns HAL documents with self and related links; if the request is reconstructed from spoofed headers, returned links can point to a host specified by an attacker.

For example, a client sends:

    X-Forwarded-Host: attacker.example
    X-Forwarded-Proto: http

If the request reaches the application directly or the proxy passes untrusted headers unchanged, a HAL response can contain links bearing the host attacker.example. This can break links followed by clients, produce redirects to the wrong host, or cause a link-consuming system to trust an unintended domain.

Key security principle: **Forwarded and X-Forwarded-* are only trustworthy when written by a proxy inside the trust boundary.** The application cannot tell on its own whether a header was added by a legitimate proxy or sent directly by an external client.

## 2. The Trust Boundary Must Be Established at the Proxy

Configuring Spring to read forwarded headers does not authenticate proxy identity. Therefore, establish a trust boundary before enabling header processing:

1. The proxy at the edge of the system must strip Forwarded and X-Forwarded-* values sent by clients.
2. After stripping, the proxy writes the necessary headers itself from request details verified by the proxy.
3. The backend accepts connections only from allowed proxies or internal networks. Never expose the application port directly to the Internet.
4. If multiple proxy tiers exist, clearly define which hops are trusted, the order of values in header chains, and where headers are overwritten.
5. Validate the Host header and configure virtual hosts at the proxy. Only accept declared public hostnames; never use an arbitrary Host from the request to construct URLs.

Both header families must be handled: standard Forwarded and non-standard X-Forwarded-*. Spring Framework warns that proxies at the trust edge must reset both Forwarded and X-Forwarded-* even when the application only uses one family. This prevents a case where one component reads Forwarded while another reads X-Forwarded-Host.

Simply adding server.forward-headers-strategy to application.yml without configuring the proxy to strip untrusted headers is insufficient. When the backend still accepts direct requests, clients can bypass the proxy and send spoofed headers straight to the application.

## 3. Choosing a Forwarded Header Handling Strategy in Spring Boot

Spring Boot provides the server.forward-headers-strategy property with three options:

| Value | Behavior | When to Use |
|---|---|---|
| NONE | Do not interpret forwarded headers | The application is not behind a trusted proxy or does not need public URL reconstruction. |
| NATIVE | Use embedded web server support | The container properly supports the headers sent by the proxy and container trust settings are restricted. |
| FRAMEWORK | Use Spring Framework handling | Need ForwardedHeaderFilter on the Servlet stack or ForwardedHeaderTransformer on the reactive stack. |

With Spring Data REST running on Spring MVC, FRAMEWORK registers ForwardedHeaderFilter to adjust requests based on Forwarded or X-Forwarded headers. The filter wraps the request so downstream components see the restored host, port, and scheme. The filter also strips forwarded headers from the request after processing so they do not continue affecting lower layers.

If the container properly supports the proxy's header set, NATIVE can be an appropriate choice. Specific support varies by server: Tomcat supports X-Forwarded-*; Jetty and Reactor Netty support X-Forwarded-* and Forwarded according to Spring Boot documentation. If you want handling independent of container native capabilities, consider FRAMEWORK.

Do not rely on platform defaults. Spring Boot may use NATIVE on certain supported cloud platforms and NONE in other cases. Set an explicit value matching your actual topology.

### Configuration When the Application Does Not Need a Proxy

In application.yml or application-dev.yml, if clients connect directly and there is no trusted proxy, set:

~~~yaml
server:
  forward-headers-strategy: none
~~~

Then client-sent request headers such as X-Forwarded-Host will not be used to construct request URLs. This configuration is suitable for local development or test environments that do not simulate a reverse proxy.

### Configuration When Running Behind a Trusted Proxy

If the proxy strips client-sent headers, rewrites standard headers itself, and the backend receives traffic only from the proxy, you can use Spring Framework:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

With this option, Spring MVC uses ForwardedHeaderFilter. Do not register a second ForwardedHeaderFilter if Spring Boot already auto-configures the filter via the property above.

If using Tomcat and TLS terminates at the proxy, you may also need:

~~~yaml
server:
  tomcat:
    redirect-context-root: false
~~~

This property allows X-Forwarded-Proto to be processed before Tomcat performs certain redirects at the context root. Apply this setting only when using Tomcat with a corresponding TLS termination topology.

### Using Tomcat Native Support

If choosing NATIVE, Tomcat has RemoteIpValve to interpret remote IP/protocol headers. You can restrict internal proxies via server.tomcat.remoteip.internal-proxies. This is a regular expression matching proxy IP addresses; replace it with the actual proxy IP range in your infrastructure:

~~~yaml
server:
  forward-headers-strategy: native
  tomcat:
    remoteip:
      internal-proxies: "10\\.20\\.0\\.\\d{1,3}"
~~~

The example above matches only 10.20.0.x addresses. Do not copy this sample range if actual proxies use different addresses. Never set internal-proxies to an empty string in production because that setting can cause every proxy to be treated as trusted. Tomcat's native configuration also has header-specific behavior; check the container documentation if you need X-Forwarded-Host or X-Forwarded-Prefix processing.

## 4. Reverse Proxy Configuration Example

Nginx example for a fixed public hostname. The proxy forwards requests to the Spring Data REST service on an internal network:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location / {
        proxy_pass http://spring-data-rest;

        proxy_set_header Host api.example.com;

        # Remove standard header sent by the client.
        proxy_set_header Forwarded "";

        # Overwrite X-Forwarded-* with values determined by the proxy.
        proxy_set_header X-Forwarded-Host api.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Ssl on;

        # Only set X-Forwarded-Prefix when the proxy actually rewrites the path.
        proxy_set_header X-Forwarded-Prefix "";
    }
}
~~~

This is an example for a single host and a single edge proxy. For multiple hostnames, use validated virtual hosts or an allowlist of hostnames; never forward arbitrary client Host/X-Forwarded-Host values unchanged. Nginx's default server configuration must also reject undeclared hostnames.

In the example, X-Forwarded-For is set to $remote_addr, recording the peer address seen by Nginx. Do not mechanically use $proxy_add_x_forwarded_for if incoming headers can be spoofed by clients. When multiple trusted proxies exist, design the address chain and client IP extraction based on your infrastructure's trusted hop list.

If the proxy exposes the URL /api/orders and the Spring Data REST application also has base path /api, there is no need to add X-Forwarded-Prefix /api again. Only use X-Forwarded-Prefix when the proxy actually rewrites or adds a prefix that differs from the path the backend receives. Configuring the prefix twice can turn HAL links into /api/api/orders.

After configuring headers, restrict networking so the backend receives traffic only from the proxy. This can be done via firewall, security group, Kubernetes NetworkPolicy, or internal platform network rules. Header configuration and network access restriction must go hand in hand.

## 5. Spring Data REST and HAL Links

Spring Data REST uses request information to generate self-referential links in HAL representations. For example, a collection response may contain:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders"
    }
  }
}
~~~

If the proxy terminates HTTPS while the application sees only an internal HTTP connection, links can be generated as http://... when the forwarded scheme is not processed. Similarly, if the host is restored from an untrusted X-Forwarded-Host, the self link can contain a spoofed hostname.

When inspecting responses, observe at least:

- _links.self.href of collection endpoints.
- _links.self.href of an item endpoint.
- Location header when creating a resource and the server returns a new URI.
- Redirect Location if the application or container issues a redirect.
- Scheme, host, port, and prefix across all public URLs.

Do not manually patch individual HAL links in repositories or controllers to mask the issue. Fix how the proxy writes headers and how Spring constructs request URLs so every link is generated consistently.

## 6. Testing in the Application

### Verifying Spring MVC Uses Forwarded Headers

With the Spring Boot Servlet stack and a Spring Data REST repository exported at /api/orders, you can use MockMvc to verify the FRAMEWORK strategy builds links from provided headers:

~~~java
@SpringBootTest(properties = {
    "server.forward-headers-strategy=framework"
})
@AutoConfigureMockMvc
class ForwardedLinkIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void usesForwardedHostAndSchemeForHalLinks() throws Exception {
        mockMvc.perform(get("/api/orders")
                .header("X-Forwarded-Host", "api.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href")
                .value(startsWith("https://api.example.test/api/orders")));
    }
}
~~~

Key imports:

~~~java
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
~~~

The test assumes the application has Spring MVC, Spring Data REST, a repository exported at path orders, and test dependencies for MockMvc. Adjust endpoints and repository configuration to match your actual application.

### Verifying the Direct Application Does Not Trust Client Headers

In a local profile or separate test context with:

~~~yaml
server:
  forward-headers-strategy: none
~~~

Send a request with X-Forwarded-Host: attacker.example and verify the returned links do not contain this hostname. This tests that the direct application does not interpret forwarded headers when no trusted proxy is present.

Do not use MockMvc tests to conclude that the real proxy strips client headers. MockMvc tests behavior inside the application context; it does not run Nginx, an ingress controller, a load balancer, a firewall, or a network policy.

### Testing Through the Real Proxy

In an integration/staging environment, send a request to the public hostname with spoofed headers:

~~~bash
curl -i https://api.example.com/api/orders \
  -H 'Forwarded: host=attacker.example;proto=http' \
  -H 'X-Forwarded-Host: attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Port: 80'
~~~

The proxy must strip or overwrite the client-supplied values. The HAL response must still use the canonical hostname and scheme:

    https://api.example.com/api/orders

Also verify that direct requests to the backend IP/port from unauthorized networks are rejected. If spoofed requests through the proxy still alter links, the proxy is not overwriting headers completely or an intermediate proxy is outside the trust configuration.

## 7. Safe Deployment Procedure

1. Identify which proxy/load balancer actually terminates client connections and which source IP the backend sees.
2. Document the header set supported by the proxy: Forwarded or X-Forwarded-*; determine whether paths are rewritten and whether X-Forwarded-Prefix is needed.
3. Configure the proxy to strip both Forwarded and X-Forwarded-* from external requests, then rewrite canonical values.
4. Choose NONE, NATIVE, or FRAMEWORK in Spring Boot according to the embedded server type and headers to process.
5. If using Tomcat native, configure internal-proxies with a regex matching only valid proxies.
6. Close backend ports from the Internet and allow access only from the proxy.
7. Verify HAL self links, Location, and redirects through the real proxy.
8. Send test spoofed headers through the public endpoint and verify links still use the official host/scheme.
9. Verify direct requests to the backend are blocked.
10. Repeat checks after every change to ingress, load balancer, service mesh, or network topology.

## 8. Troubleshooting

| Symptom | Common Cause | How to Resolve |
|---|---|---|
| HAL self link points to an internal host like 10.x.x.x | Forwarded headers not enabled or proxy not sending public host | Check X-Forwarded-Host/Forwarded host and choose NATIVE or FRAMEWORK appropriately. |
| HAL link contains attacker.example | Proxy forwards client headers unchanged or backend accepts direct requests | Strip and overwrite both Forwarded and X-Forwarded-* at the edge; restrict network access to backend. |
| Link uses http instead of https | Public scheme not sent by proxy or container not processing X-Forwarded-Proto | Set X-Forwarded-Proto=https at the proxy and check strategy. With Tomcat TLS termination, consider redirect-context-root=false. |
| Link contains internal port 8080 | X-Forwarded-Port not sent or ignored | Write the correct public port and verify container/Framework handles that header. |
| Link contains /api/api | Spring Data REST base path and X-Forwarded-Prefix added redundantly | Check the path the proxy sends to the backend; set prefix only when the proxy actually rewrites the path. |
| NATIVE does not handle headers as expected | Embedded server does not support the required header or behavior | Check container documentation; switch to FRAMEWORK if appropriate. |
| Client IP is inaccurate | X-Forwarded-For chain has client-injected values or proxy chain is unmodeled | Overwrite at the edge; configure the trusted hop list and read addresses only from the right proxy. |
| Local runs produce wrong links after enabling FRAMEWORK | Local requests have spoofed forwarded headers or dev profile also trusts headers | Use NONE for direct dev/test; enable forwarded handling only in profiles deployed behind a trusted proxy. |
| Only some requests produce wrong links | Multiple proxies or multiple ingress paths into backend with differing header rules | Audit every ingress/load balancer and unify strip and overwrite rules across all entry paths. |

## 9. Security Checklist

- [ ] Proxy at the trust boundary strips client-sent Forwarded headers.
- [ ] Proxy at the trust boundary strips or overwrites all client-sent X-Forwarded-* headers.
- [ ] Proxy regenerates host, proto, port, and prefix from verified configuration/metadata.
- [ ] Invalid hostnames are rejected at the reverse proxy.
- [ ] Backend accepts traffic only from the proxy or permitted internal networks.
- [ ] server.forward-headers-strategy is explicitly set for each environment.
- [ ] If using Tomcat NATIVE, internal-proxies matches only valid proxies.
- [ ] X-Forwarded-For is not trusted for authorization unless the trusted proxy chain is established.
- [ ] HAL self links and Location use the correct public scheme, host, port, and prefix.
- [ ] Tests sending spoofed headers through the real proxy still receive canonical links.
- [ ] Direct requests to the backend from external networks are blocked.

## 10. Official References

- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/4.2/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server): choosing server.forward-headers-strategy, NATIVE/FRAMEWORK support, and Tomcat proxy configuration. Use the Spring Boot documentation version matching your project when deploying.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): server.forward-headers-strategy property and embedded server settings.
- [Spring Framework — Filters / Forwarded Headers](https://docs.spring.io/spring/reference/web/webmvc/filters.html#filters-forwarded-headers): ForwardedHeaderFilter, supported headers, removeOnly, and security considerations.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): standard Forwarded header format.
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/): repository resources and HAL representations provided by Spring Data REST.
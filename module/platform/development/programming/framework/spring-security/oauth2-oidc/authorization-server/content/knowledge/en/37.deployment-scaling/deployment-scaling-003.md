# Trusting Forwarded Headers from Authorized Proxies

When Spring Authorization Server runs behind a reverse proxy or load balancer, the application often receives internal connections over HTTP even though users connect over HTTPS. The application may also see an internal hostname, port, and path instead of the public address. Proxies use HTTP headers such as Forwarded or X-Forwarded-* to pass along information about the external request.

These headers directly affect how Spring builds URLs, determines whether a request is secure, and generates metadata for OAuth 2.0/OpenID Connect. If the application trusts every value sent to it, a client can spoof the scheme, host, or IP address. The consequences can include broken URLs, an inconsistent issuer, session cookies missing the Secure attribute, inaccurate access logs, or security decisions based on untrusted IPs.

The deployment rule is: **interpret forwarded headers only after a proxy inside the trust boundary has stripped client-supplied values and written verified values**. Spring can read these headers, but the filter itself does not authenticate the proxy sending the request.

## 1. Understanding the trust boundary

A common topology:

~~~text
Browser
    |
    | HTTPS https://auth.example.com
    v
Reverse proxy / Load balancer
    |
    | Internal HTTP, with standardized forwarded headers
    v
Spring Authorization Server
~~~

The proxy may terminate TLS at the network edge and forward requests to the application over HTTP. Therefore, looking only at the internal socket connection, the application might see:

- Scheme as http instead of https.
- Host as the internal service name instead of auth.example.com.
- Port as the internal port instead of public port 443.
- Client IP as the proxy's address instead of the source address observed by the proxy.
- Request URI possibly missing a public prefix if the proxy maps an external path to a different backend context path.

Forwarded headers describe part of the external context. They are data inside an HTTP request, not cryptographic proof that the request passed through a trusted proxy. A client can send headers with the same names itself if the proxy does not remove or overwrite them.

### Common headers

| Header | Common meaning | What to control |
|---|---|---|
| Forwarded | Standard RFC 7239 header; may contain for, by, host, and proto | Proxy must normalize or regenerate the value; watch multi-proxy chains |
| X-Forwarded-For | Client address and/or proxy hops | Do not use directly for authorization decisions without verifying the proxy chain |
| X-Forwarded-Host | Host used by the client externally | Accept only hosts on an allowed domain list |
| X-Forwarded-Proto | External scheme, usually http or https | Must reflect the client's connection to the trusted edge |
| X-Forwarded-Port | Public port | Must be consistent with scheme and host |
| X-Forwarded-Prefix | Public path prefix mapped by the proxy | Set only when corresponding rewriting occurs; avoid prepending the prefix twice |

Do not let clients determine the values above. For example, a request sent directly to the proxy could already carry X-Forwarded-Host: attacker.example and X-Forwarded-Proto: https. If the proxy passes these headers unchanged to the application, the application may treat the request as if it arrived from the attacker's domain.

### Conditions for trusting a proxy

A proxy is only considered trusted when the system controls both the request path and how the proxy creates headers:

1. The backend accepts traffic only from the proxy or identified internal hops. Use a private subnet, firewall, security group, Kubernetes NetworkPolicy, or equivalent mechanism to block direct access.
2. The edge proxy strips client-supplied Forwarded and X-Forwarded-* headers, then regenerates the required values itself.
3. The external host is validated against an allowlist of permitted domains. Never use an arbitrary Host header from the request to construct the issuer or public URLs.
4. If multiple proxies exist, define clearly which proxies may append information and the rules for processing the header chain. Do not rely on the first or last element position without controlling the entire chain.
5. The application enables forwarded-header interpretation only when the network topology guarantees requests arrive from trusted proxies.

If the backend can still be called directly from the Internet or from an uncontrolled network, merely enabling ForwardedHeaderFilter is not enough. That filter does not maintain a list of trusted proxy IPs and does not authenticate the header sender.

## 2. How does Spring handle forwarded headers?

In a Servlet application, Spring Framework provides ForwardedHeaderFilter in the org.springframework.web.filter package. The filter reads Forwarded or X-Forwarded-* and wraps HttpServletRequest so downstream components observe the external information, such as:

- getScheme() returns the public scheme.
- isSecure() reflects external HTTPS.
- getServerName() and getServerPort() reflect the public host and port.
- URI attributes and context path can be adjusted according to the forwarded prefix.

This helps components that construct URLs or redirects from the request build addresses matching the client's perspective. However, the filter cannot tell whether a header was actually produced by a trusted proxy. The trust boundary must be enforced at the proxy and network layers.

### Configuring with Spring Boot

If the application uses Spring Boot and you want Spring Framework to interpret the headers, configure:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Common strategy values:

| Value | Behavior |
|---|---|
| none | Do not enable automatic forwarded-header handling |
| framework | Use Spring Framework's mechanism, typically ForwardedHeaderFilter |
| native | Use the web server or servlet container's built-in support |

Choose one mechanism suited to your runtime. With native, behavior and trusted-proxy configuration depend on the container. For instance, Tomcat has RemoteIpValve and its own configuration properties. Inspect your container's configuration instead of assuming all runtimes handle headers identically.

Do not enable both native handling and register an additional ForwardedHeaderFilter for the same request. Two layers interpreting the same headers can cause scheme, port, or prefix to be modified twice. If Spring Boot already auto-registers the filter under the framework setting, do not register a second filter duplicating the same function.

In a Servlet application not using Spring Boot auto-configuration, you can register ForwardedHeaderFilter manually. The filter must run before any filters or components that need to read scheme, host, port, and context path, including the Spring Security filter chain. Verify the actual filter ordering in the application rather than relying solely on the bean being declared.

### When you only want to strip headers

Some environments prohibit the application from trusting forwarded headers, yet still want them stripped before the request travels deeper into the system. ForwardedHeaderFilter has a remove-only mode that removes supported headers without using them to mutate the request. This is useful when you need to prevent downstream code from accidentally reading raw headers.

Whether using framework, native, or remove-only, the edge proxy still needs to filter and normalize headers. Do not treat application-level configuration as a substitute for ingress controls.

## 3. Normalizing headers at the reverse proxy

The example below illustrates Nginx receiving HTTPS directly from clients and forwarding requests to Spring Authorization Server over an internal network:

~~~nginx
server {
    listen 443 ssl;
    server_name auth.example.com;

    location / {
        proxy_pass http://authorization-server;

        # Public host is already restricted by the server block.
        proxy_set_header Host auth.example.com;

        # Strip client-supplied Forwarded header.
        proxy_set_header Forwarded "";

        # Write proxy-controlled values.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Host auth.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
    }
}
~~~

This example assumes Nginx is the direct termination point for client connections and the server block serves only the listed domain. Setting X-Forwarded-For to $remote_addr records the address observed by Nginx, instead of preserving a client-supplied chain.

If Nginx sits behind a load balancer, $remote_addr may be the load balancer's address. Only configure Nginx's real-IP mechanism after specifying the exact CIDRs of authorized load balancers and the headers they emit. Do not trust X-Forwarded-For from arbitrary sources. Only after verifying the upstream hop can Nginx use the validated client address to build forwarded headers.

When deploying multiple domains, you may need per-virtual-host handling instead of a fixed string. In that case, ingress configuration must reject hosts outside the allowlist and never allow an arbitrary Host header through to the application. Directly reflecting a client-provided Host value into X-Forwarded-Host can open the door to host header poisoning.

You may choose the standard Forwarded header instead of the X-Forwarded-* group. What matters is that the proxy constructs values under a consistent rule and the application interprets that exact rule. Avoid sending both header groups simultaneously with conflicting values.

### When a public prefix is present

Suppose clients access https://auth.example.com/auth/... while the proxy strips the /auth prefix before forwarding requests to the backend. If the application needs to know the public prefix to build URLs, the proxy can pass X-Forwarded-Prefix: /auth.

Set the prefix only when path rewriting actually occurs. If the proxy preserves the prefix and the application also configures the matching context path, adding X-Forwarded-Prefix again can produce URLs like /auth/auth/.... Verify the request URI, context path, and endpoints after deployment.

## 4. Configuring a stable issuer for the Authorization Server

For an Authorization Server, the issuer is a critical identifier in OAuth 2.0 and OpenID Connect. The issuer appears in Authorization Server and OpenID Provider metadata; for JWT tokens, the iss claim must also match the published issuer.

If the issuer is derived from the current request, a spoofed host or scheme can cause the server to advertise an unintended identity. The appropriate approach for an Authorization Server with a fixed domain is to configure the public issuer explicitly:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

This configuration snippet assumes the application has a single fixed public issuer. If the issuer is deployed under a path, such as https://auth.example.com/auth, the issuer value must reflect the exact published identifier and remain consistent with the endpoints used by clients.

When OIDC is enabled, inspect the discovery document at the corresponding endpoint, for example:

~~~text
https://auth.example.com/.well-known/openid-configuration
~~~

Metadata URLs such as issuer, authorization_endpoint, token_endpoint, and jwks_uri must point to reachable public addresses. If the configured issuer includes a path, the discovery endpoint must also follow the well-known URI rules corresponding to that issuer.

Distinguish two responsibilities:

- Forwarded headers describe how the request reached the application through a proxy, helping construct URLs from the external perspective.
- AuthorizationServerSettings defines the issuer published by the Authorization Server.

A fixed issuer keeps server identity independent of the Host or X-Forwarded-Host on individual requests. Forwarded headers still need to be accurate so the application processes requests and URLs properly, but they should not become an arbitrary source that decides the issuer.

In multi-tenant or multi-issuer systems, do not take any arbitrary host from the request and use it as the issuer. Map the proxy-validated host to an issuer on an allowlist. Custom issuer resolution logic must reject unknown hosts and maintain consistency across metadata, tokens, and tenant endpoints.

### Forwarded headers do not replace redirect_uri validation

When the Authorization Server redirects the browser back to the client, redirect_uri must be validated against the registered client configuration. Forwarded headers do not alter redirect_uri matching rules and are not a reason to relax this check.

Never construct the client's redirect_uri from X-Forwarded-Host. The callback address belongs to the client's configuration, whereas the issuer is the Authorization Server's identifier. These two values have different roles and must be managed independently.

### Impact on HTTPS and cookies

When TLS terminates at the proxy, the backend may receive HTTP connections. If the request is not interpreted correctly as HTTPS, code relying on isSecure() may generate HTTP URLs or configure session cookies without the Secure attribute. Browsers may reject cookies or send them inconsistently with the intended policy.

After configuring forwarded headers, inspect actual responses over the public domain, especially:

- Whether URLs in redirects and metadata use HTTPS.
- Whether session cookies carry the Secure attribute when required.
- Whether cookie Domain, Path, and SameSite fit the topology and login flow.
- Whether the proxy preserves required security headers or applies security policies at the edge.

Do not use a passing isSecure() result in a unit test to conclude the entire TLS path is secure. Verify both proxy TLS settings and backend reachability.

## 5. Handling multiple proxies and client addresses

In production environments, requests may traverse a CDN, load balancer, and ingress controller before reaching the application. Each hop may append or alter forwarded headers. The header chain can therefore contain multiple addresses and values.

Define clearly:

- Which hop is the first trusted point receiving traffic from the Internet.
- Which hops are permitted to write or append headers.
- Which header serves as the primary source of truth.
- Which hop the application receives requests from directly, and whether the network blocks other sources.

The edge proxy should strip client-supplied data and generate fresh information. Subsequent hops should only append following a controlled convention. If the system needs the real client IP, configure the trusted proxy chain on the component responsible for resolving that address.

Do not use raw X-Forwarded-For as the basis for authenticating users, granting permissions, bypassing MFA, or allowing access to administrative endpoints. IP addresses can be useful for logging, rate limiting, or network policies, but only after the system has properly identified trusted proxies and how to select the address from the chain. ForwardedHeaderFilter primarily adjusts the request's view; it does not replace a trusted client-IP resolver for security decisions.

## 6. Testing configuration after deployment

Testing must go through the public access path and verify both positive behavior and resistance to spoofing.

### Checking public metadata

Call the discovery endpoint externally:

~~~bash
curl -fsS https://auth.example.com/.well-known/openid-configuration
~~~

If jq is available, filter key fields:

~~~bash
curl -fsS https://auth.example.com/.well-known/openid-configuration \
  | jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri}'
~~~

Confirm that URLs use the public scheme and host, the issuer matches the AuthorizationServerSettings configuration, and the JWKS endpoint is reachable by clients. If OIDC is not enabled, use the metadata endpoint matching your current Authorization Server configuration.

### Testing spoofed headers from the client side

Send spoofed headers to the public domain:

~~~bash
curl -i \
  -H 'X-Forwarded-Host: attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'Forwarded: host=attacker.example;proto=http' \
  https://auth.example.com/.well-known/openid-configuration
~~~

The edge proxy must strip or overwrite these values. Returned metadata must still use the valid configured public issuer and URLs of the Authorization Server. If attacker.example appears in metadata or redirects, recheck header sanitization rules, host allowlists, and forwarded-header processing settings.

### Testing the direct access path

Attempt to access the backend from a network outside authorized proxies. The request must be blocked by the firewall, security group, ingress, or NetworkPolicy. This is a critical check because a request hitting the backend directly can declare its own X-Forwarded-Proto: https and X-Forwarded-Host: auth.example.com.

### Testing requests and responses

In a test environment, verify the application sees scheme https, host auth.example.com, and port 443 when requests go through the proxy. Also inspect redirects, session cookies, context path, and absolute URLs generated by the application.

With multiple proxies, test each valid path and test sending client-crafted X-Forwarded-For or Forwarded chains. Outcomes must adhere to the rules defined at the ingress. Do not conclude that MockMvc tests or mock requests prove the firewall and proxy are working properly; those tests only verify behavior within the application boundary.

## 7. Common deployment mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Enabling ForwardedHeaderFilter while backend remains publicly reachable | Clients can send spoofed headers directly | Restrict ingress so only authorized proxies can call the backend |
| Proxy passes through client-sent X-Forwarded-* unchanged | Host, scheme, or IP can be spoofed | Strip and rewrite headers at the edge proxy |
| Using arbitrary Host to construct the issuer | Metadata or token identity can be wrong | Configure an explicit issuer or map hosts via an allowlist |
| Using raw X-Forwarded-For for authorization | Attackers can spoof IP addresses | Use IPs only after verifying the proxy chain |
| Enabling both native and framework handling | Requests may be interpreted twice | Choose a single processing mechanism |
| Adding X-Forwarded-Prefix inconsistently with topology | URLs may duplicate or lose path segments | Align proxy rewrites, context path, and prefix |
| Trusting X-Forwarded-Proto from any source | HTTP requests may be misclassified as HTTPS | Accept only headers rewritten by trusted proxies |

## 8. Pre-production checklist

- [ ] Backend accepts traffic only from authorized proxies or internal hops.
- [ ] Edge proxy strips client-supplied Forwarded and X-Forwarded-* headers.
- [ ] Proxy regenerates host, proto, port, and client info under controlled configuration.
- [ ] External host is restricted to valid domains.
- [ ] Multi-proxy chains have clear rules and have been tested.
- [ ] Application uses only one forwarded-header processing mechanism.
- [ ] Forwarded-header filter executes before components that read the request URL.
- [ ] AuthorizationServerSettings publishes an accurate and stable issuer.
- [ ] OIDC metadata, endpoints, and the iss claim are consistent with the issuer.
- [ ] redirect_uri is still validated against the registered client.
- [ ] Cookies and redirects have been verified over public HTTPS.
- [ ] Both direct backend access and spoofed headers have been tested.

Trusting forwarded headers is a network boundary decision before it is a Spring configuration decision. When proxies are restricted, headers are normalized, and the issuer is configured consistently, Spring Authorization Server can receive the proper external request context without allowing clients to arbitrarily control the server's identity or public URLs.

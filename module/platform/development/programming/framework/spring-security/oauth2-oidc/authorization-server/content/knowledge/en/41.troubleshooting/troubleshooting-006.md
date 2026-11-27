# Issuer, Forwarded Headers, and Discovery Errors Behind a Reverse Proxy

Spring Authorization Server commonly runs behind a load balancer, ingress controller, or reverse proxy. The application may receive internal requests over HTTP on a different port while users access it over HTTPS on a public hostname. If the Authorization Server misidentifies its external address, it can issue tokens with the wrong `iss`, generate redirects to an internal hostname, publish an unreachable `jwks_uri`, or return inconsistent OIDC metadata across instances.

This group of errors typically surfaces after enabling TLS termination, changing domains, adding a path prefix, switching ingress controllers, or chaining multiple proxies. The effective approach is to establish a single canonical public issuer, define a trust boundary for forwarded headers, and verify metadata and tokens from the external client's perspective.

## 1. Understanding the Issuer and External Address

The issuer is the identifier of the Authorization Server. For example:

```text
https://identity.example.com
```

The issuer appears in OAuth/OIDC metadata and in the `iss` claim of ID tokens or JWT access tokens. Resource Servers and OIDC clients use this value to verify that a token was issued by the expected trusted provider. Issuer matching must be exact; do not normalize trailing `/` characters, swap hostname aliases, or accept a near-matching issuer.

When running behind a proxy, a single request can have two sets of addresses:

| Perspective | Example | Who Sees It? |
|---|---|---|
| External address | `https://identity.example.com` | Browser, OAuth client, OIDC client, and Resource Server |
| Internal address | `http://authorization-server:8080` | Proxy and application inside the deployment network |

The application normally sees only the connection from the proxy: `http` scheme, internal host, and port `8080`. The proxy must pass the original request information via trusted headers such as `Forwarded` or `X-Forwarded-*`. The framework/container uses those headers to reconstruct the scheme, host, port, and prefix used by the external client.

Common headers:

| Header | Information |
|---|---|
| `Forwarded` | Standardized header per RFC 7239; can carry `proto`, `host`, and `for` |
| `X-Forwarded-Proto` | External scheme, usually `https` |
| `X-Forwarded-Host` | Public hostname |
| `X-Forwarded-Port` | Public port, usually `443` |
| `X-Forwarded-Prefix` | Public path prefix if the proxy adds or strips a prefix when forwarding |
| `X-Forwarded-For` | Client IP addresses through the proxy chain; useful for audit/rate limiting, not for determining the issuer |

Do not let `Forwarded` and `X-Forwarded-*` contain conflicting values. Choose one consistent convention across the entire proxy chain and configure Spring to handle that exact convention.

## 2. Common Symptoms and Causes

| Symptom | Most Likely Cause | Where to Check |
|---|---|---|
| `iss` in JWT is `http://authorization-server:8080` | Issuer was derived from internal request or misconfigured | `AuthorizationServerSettings`, forwarded headers, and proxy |
| Discovery returns `issuer` as HTTP while users visit HTTPS | `X-Forwarded-Proto` is missing, overwritten, or ignored | Last proxy before the app and `server.forward-headers-strategy` |
| Metadata advertises internal hostname or port `8080` | Internal host/port leaked into public URL | `Host`, `X-Forwarded-Host`, `X-Forwarded-Port` |
| Login/callback redirect points to wrong domain or scheme | Request wrapper does not reflect original URL or app builds URL manually | Forwarded headers, context path, redirect handler |
| Discovery endpoint returns 404 | Wrong well-known path, issuer has path, OIDC not enabled, or wrong proxy rewrite | `AuthorizationServerSettings`, endpoint configurer, and ingress route |
| OIDC client reports issuer mismatch | Metadata issuer differs from `iss` in ID token or registered issuer | Public metadata, token, and client configuration |
| `jwks_uri` points to internal or unreachable URL | Metadata built from wrong request or proxy does not route JWKS endpoint | Discovery response, JWKS endpoint, and proxy path |
| Some requests succeed, some fail | Proxies/nodes send different headers or stale metadata cache | Every proxy hop, per-replica config, and client cache |

A wrong issuer can break the entire OIDC login even when the login page renders normally. Therefore, do not conclude the system is healthy just because `/login` or `/oauth2/authorize` returns an HTML page.

## 3. Choosing a Stable Public Issuer

In production, declare the public issuer explicitly in `AuthorizationServerSettings`, instead of letting it change dynamically based on the hostname sent by each request:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://identity.example.com")
            .build();
}
```

The value in the example is the environment's canonical issuer. If the system is genuinely published under a path prefix, the issuer must include that exact designed prefix, e.g. `https://example.com/identity`. Do not add a prefix merely because the internal application has a `context-path`; base it on the public URL that OIDC clients and Resource Servers use to identify the issuer.

All instances of the same Authorization Server must use the exact same issuer. Never configure the issuer from pod names, internal hostnames, IP addresses, arbitrary request Host headers, or per-node URLs. If you have staging and production, each environment must have its own issuer, metadata, and keys suited to that environment.

The issuer should be managed as deployment configuration:

```yaml
app:
  security:
    authorization-server:
      issuer: https://identity.example.com
```

Then inject the configuration value into the `AuthorizationServerSettings` bean. Avoid declaring the same issuer in multiple places such as environment variables, code, and ingress annotations without a single source of truth.

Declaring a static issuer keeps metadata and the `iss` claim consistent. It will not fix other endpoint URLs if the proxy path, forwarded host, or endpoint configuration is still wrong. You must still verify the full metadata and redirect flow via the public URL.

## 4. Configuring Forwarded Headers in Spring Boot

Spring Boot has the `server.forward-headers-strategy` property to choose how forwarded headers are processed. Common values:

| Value | How It Works | When to Consider |
|---|---|---|
| `NONE` | Does not process forwarded headers | App is not behind a proxy or proxy does not provide trusted headers |
| `NATIVE` | Uses the web server/container's support | Container has forwarded header handling matching the topology |
| `FRAMEWORK` | Uses Spring Framework's mechanism, typically via `ForwardedHeaderFilter` | Need consistent header handling across Spring Framework |

Example using the framework strategy:

```yaml
server:
  forward-headers-strategy: framework
```

Or if the container is configured to handle the appropriate headers natively:

```yaml
server:
  forward-headers-strategy: native
```

Choose only one strategy matching your deployment. Do not simultaneously enable native container support, register a `ForwardedHeaderFilter` bean manually, and add a custom filter that mutates scheme/host without understanding their execution order. Multiple layers rewriting the request can produce duplicated hosts or prefixes.

For Spring applications not using Boot auto-configuration, you can register the filter explicitly:

```java
@Bean
ForwardedHeaderFilter forwardedHeaderFilter() {
    return new ForwardedHeaderFilter();
}
```

Do this only when the application does not already have an equivalent filter. `ForwardedHeaderFilter` changes how the application sees the request; it does not verify which proxy is trusted. The trust boundary must be enforced at the network and upstream proxy layer.

Property names and container behavior can vary across Spring Boot versions, servlet containers, and deployment environments. Check the documentation for your exact running version, then verify with live requests rather than just reading the YAML config.

## 5. Configuring the Reverse Proxy to Send Accurate Origin Info

The Nginx example below assumes Nginx is the public TLS termination point for hostname `identity.example.com`, then proxies to the internal application over HTTP. Nginx overwrites forwarded headers with values determined at the proxy:

```nginx
server {
    listen 443 ssl;
    server_name identity.example.com;

    location / {
        proxy_pass http://authorization-server:8080;
        proxy_set_header Host identity.example.com;
        proxy_set_header X-Forwarded-Host identity.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Choose X-Forwarded-* as the convention; do not forward a
        # Forwarded header supplied by an external client.
        proxy_set_header Forwarded "";
    }
}
```

If the application is published under the `/identity` prefix and Nginx preserves the prefix when proxying, route configuration and forwarded prefixes must reflect the exact public path. If Nginx strips the prefix before sending internal requests, pass the public prefix in the manner supported by your Spring/container setup, and verify that redirects and metadata include the prefix exactly once. Do not send `X-Forwarded-Prefix` when the external URL has no prefix.

In a topology with a load balancer in front of Nginx, `$scheme` at Nginx may be `http` even though the client connected to the load balancer over HTTPS. In that case, never treat internal `$scheme` as the public scheme. The load balancer must pass verified TLS information to Nginx over a trusted channel; Nginx only uses that information after confirming the request came from the authorized load balancer. Never trust arbitrary forwarded headers from the Internet.

Key rules:

- The first proxy receiving untrusted traffic must strip or overwrite `Forwarded` and all client-supplied `X-Forwarded-*` headers.
- Accept forwarded headers only from proxies inside the trusted network; restrict direct connections to the application so clients cannot bypass the proxy.
- Every proxy hop must follow an explicit convention on keeping, appending, or overwriting headers. Do not let nodes receive different values for the same request.
- Public hosts must be restricted via virtual hosts/allowlists. Never reflect an arbitrary Host header into the issuer or redirect URLs.
- Only forward a prefix if an external route prefix genuinely exists, and verify proxy rewrites are consistent.

## 6. Checking Discovery and Metadata

When OIDC is enabled, clients normally fetch the OpenID Provider Configuration via a well-known URI. OAuth Authorization Server Metadata per RFC 8414 has its own rules for constructing well-known URIs. For an issuer without a path, common URLs are:

```text
Issuer:
https://identity.example.com

OpenID Provider Configuration:
https://identity.example.com/.well-known/openid-configuration

OAuth Authorization Server Metadata:
https://identity.example.com/.well-known/oauth-authorization-server
```

When the issuer includes a path, the well-known URI layout depends on the rules of the respective specification. OIDC Discovery appends `/.well-known/openid-configuration` after the issuer path; RFC 8414 inserts `/.well-known/oauth-authorization-server` between the authority and the issuer path. For example, with issuer `https://example.com/identity`:

```text
OIDC Discovery:
https://example.com/identity/.well-known/openid-configuration

OAuth Authorization Server Metadata:
https://example.com/.well-known/oauth-authorization-server/identity
```

Do not assume a single well-known URL structure for both specifications. Use the issuer configured on the client and the discovery rules of the corresponding protocol/client. Check that ingress routes to the right endpoint after path prefix handling.

Fetch metadata from outside the proxy:

```bash
curl -i https://identity.example.com/.well-known/openid-configuration
```

If the application enables separate OAuth Authorization Server Metadata, check the RFC 8414 URI as well. In the JSON response, verify at least:

| Field | What to Verify |
|---|---|
| `issuer` | Matches the canonical issuer exactly, including scheme, host, port, and path |
| `authorization_endpoint` | Uses HTTPS and the public hostname/path |
| `token_endpoint` | Points to the public token endpoint, not internal service DNS |
| `jwks_uri` | Reachable from clients/resource servers and returns a valid JWK Set |
| `userinfo_endpoint` | Exact public URL if OIDC UserInfo is enabled |
| `end_session_endpoint` | Exact public URL if the provider advertises a logout endpoint |
| `response_types_supported` | Matches the response types the server actually supports |
| `grant_types_supported` | Does not advertise grants the server is not configured to handle |
| `code_challenge_methods_supported` | Includes `S256` if authorization code + PKCE is supported |

Metadata must not contain `http://`, container hostnames, private IP addresses, internal ports, or missing/duplicated paths. URLs must be usable from the external client's network, not only from inside the cluster.

Check JWKS separately:

```bash
curl -i https://identity.example.com/oauth2/jwks
```

The JWKS path may have been customized. Compare `jwks_uri` in metadata with the actual URL and verify the response includes appropriate `keys`, `kid`, `kty`, and `use`/`key_ops`. Never expose private keys in the JWK Set. If metadata is accurate yet clients still cannot verify tokens, check `kid`, signing algorithm, JWKS caching, and key rotation.

## 7. Diagnosing by Error Type

### 7.1. `iss` or Metadata Uses HTTP Instead of HTTPS

**Symptom:** Users visit `https://identity.example.com`, but the ID token has `iss` as `http://identity.example.com` or metadata advertises HTTP.

**Common cause:** TLS terminates at the load balancer, the connection from load balancer to app is HTTP, yet `X-Forwarded-Proto` is not set properly or Spring does not process that header.

**How to check:**

1. Send a request via the public domain and fetch metadata.
2. Check `issuer` in metadata and the `iss` claim in a verified token.
3. Check whether the final proxy before the app sets `X-Forwarded-Proto: https` or `Forwarded: proto=https`.
4. Confirm `server.forward-headers-strategy` uses the right mechanism.
5. Check whether an intermediate proxy overwrites the scheme to `http`.

**How to fix:** Fix the public issuer in `AuthorizationServerSettings` and configure the proxy to send the verified original scheme. After fixing, verify metadata, authorization redirects, and newly issued tokens. Tokens already issued with the wrong issuer remain wrong; you cannot fix the `iss` claim of old tokens by changing metadata.

### 7.2. Metadata or Redirects Contain an Internal Hostname

**Symptom:** Advertised URLs are `http://authorization-server:8080/...`, `http://10.x.x.x/...`, or a Kubernetes service name.

**Common cause:** `Host`/`X-Forwarded-Host` header is not set by the proxy, the request wrapper uses the internal host, or the app builds URLs from internal endpoint config.

**How to fix:** Use the canonical hostname in issuer configuration and configure the proxy to overwrite the public host. Check `authorization_endpoint`, `token_endpoint`, `jwks_uri`, redirect URIs, and links on the login page. Never use an arbitrary client Host header to construct URLs.

### 7.3. Wrong Port or HTTPS Downgraded to HTTP Across a Proxy Chain

**Symptom:** Metadata contains `:8080`, `:80`, or a port mismatching the URL users visit.

**Common cause:** A proxy fails to pass `X-Forwarded-Port`, or an intermediate proxy injects an internal port value. Alternatively, TLS termination occurs at a hop before the proxy writing the headers.

**How to fix:** Map out the full request path and identify which hop knows the public scheme/port. Configure that hop to emit trusted values; subsequent hops only accept them from the authenticated upstream. With a static issuer, ensure endpoint URLs in metadata also use the public authority.

### 7.4. Discovery Returns 404 or Client Cannot Find Well-Known Endpoint

**Possible causes:**

- OIDC is not enabled in `OAuth2AuthorizationServerConfigurer`, so OpenID Provider Configuration is not published.
- Client calls the wrong well-known URI or applies the wrong rule when the issuer contains a path.
- Ingress routes `/oauth2/**` but does not route `/.well-known/**`.
- Proxy strips or prepends a path prefix the wrong number of times.
- Endpoint is blocked by a security matcher or another filter chain.

**How to check:** Call the well-known URL directly for the issuer from the external network. Compare the same request through ingress and directly to the internal service. Inspect status, `Location`, `Host`, actual path, and proxy access logs. If the internal endpoint works while the public URL returns 404, the fault is usually in proxy routing/rewriting. If both return 404, check OIDC/metadata endpoint configuration and library version.

### 7.5. `issuer mismatch` on OIDC Client or Resource Server

**Symptom:** Client rejects the ID token because issuer does not equal the issuer used for discovery; Resource Server rejects JWTs because `iss` does not match configuration.

**How to fix:** Choose one canonical issuer and use it identically across `AuthorizationServerSettings`, OIDC client registration, and Resource Server validators. Do not add exceptions accepting both internal and public hostnames. Because changing the issuer changes provider identity, plan a migration for clients, validators, and still-valid tokens; new metadata does not automatically change the issuer of existing tokens.

### 7.6. Discovery Is Right, Yet Redirect URI or Callback Still Fails

Issuer and endpoint metadata do not override per-client `redirect_uri` validation. The redirect URI must still match the client's registered URI. If the callback is generated with the wrong scheme or prefix, inspect forwarded headers, context path, and the client's redirect URI config. Do not fix it by relaxing redirect URI validation or accepting wildcard domains.

## 8. Inspecting Forwarded Headers Without Leaking Information

In test environments, you can temporarily log request attributes after framework processing:

```java
log.debug("External request view: scheme={}, host={}, port={}, contextPath={}",
        request.getScheme(),
        request.getServerName(),
        request.getServerPort(),
        request.getContextPath());
```

Place this log on a protected internal diagnostic endpoint or in staging. Never create a public endpoint reflecting all request headers. Never log cookies, authorization headers, tokens, session IDs, or secret values. Remove diagnostic logging or lower the log level after verification.

You can inspect response headers with curl:

```bash
curl -sS -D - -o /dev/null https://identity.example.com/.well-known/openid-configuration
```

To distinguish a proxy issue from an application issue, compare three vantage points:

1. Request to the public hostname through the entire proxy chain.
2. Request from the internal network to the service, with Host and forwarded headers crafted like the trusted proxy.
3. Request directly to the application without forwarded headers, strictly in an isolated internal test environment.

If results differ, record the request path and headers forwarded by the proxy at each hop. Never send requests directly from the Internet to the application port to test forwarded headers; doing so can bypass the protective boundary production relies on.

## 9. Security Risks When Trusting Forwarded Headers

Forwarded headers are proxy-supplied data, not self-authenticating proof. If an application accepts direct Internet requests and trusts `X-Forwarded-Host` or `Forwarded`, an attacker can try to alter the issuer, links, redirects, or client IP info by sending forged headers.

Required safeguards:

- Block direct access to the application port from untrusted networks; allow connections only from the proxy/ingress.
- At the edge proxy, strip client-supplied forwarded headers and write values determined by the proxy.
- Never use forwarded host as the issuer without enforcing a host allowlist.
- Limit `server.forward-headers-strategy` to match the real topology; do not enable it merely to make a redirect error disappear.
- With multiple proxies, explicitly define which proxies are trusted and how headers are appended. Do not assume every entry in `X-Forwarded-For` is trustworthy.
- Test forged `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and `X-Forwarded-Prefix` headers from an untrusted client; public output must retain the canonical hostname/scheme.

A forwarded header misconfiguration can become a host-header injection or open redirect vulnerability, not just a URL display bug. Therefore, enabling header processing must always be paired with proxy and network controls.

## 10. Post-Fix Verification Checklist

- [ ] `AuthorizationServerSettings` uses the canonical public issuer identically across all instances.
- [ ] Proxy overwrites client-sent forwarded headers; the application accepts traffic only from trusted proxies.
- [ ] Only one forwarded-header processing strategy is active, matching the container/Boot setup.
- [ ] Processed scheme, host, port, and path prefix match the public URL.
- [ ] OIDC Discovery and OAuth Authorization Server Metadata are fetched via the public domain and return the exact issuer.
- [ ] `authorization_endpoint`, `token_endpoint`, `jwks_uri`, and other OIDC endpoints use public HTTPS URLs.
- [ ] The `iss` claim in newly issued ID tokens/JWTs matches metadata and client/resource server validators exactly.
- [ ] JWKS endpoint is reachable, exposes no private keys, and includes the `kid` matching signed tokens.
- [ ] Redirect URIs are still validated strictly against registered clients.
- [ ] Tests with forged hostname/forwarded headers do not alter the issuer or redirects.
- [ ] Instances and proxies in the same environment return consistent metadata; stale discovery caches are refreshed as planned.

When the public issuer is fixed, proxies send only verified forwarded headers, and discovery is checked from an external client's perspective, OIDC flows keep a stable identity even behind multiple network layers. Treat issuer, forwarded headers, and metadata as one unified deployment configuration rather than three isolated per-endpoint bugs.

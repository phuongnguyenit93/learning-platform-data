# Controlling SSRF from jwks_uri, Metadata, and Client-Supplied URLs

## 1. Objectives and Scope

In the `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER` module, the Authorization Server may need to fetch external resources to retrieve public keys, read metadata, dereference request objects, or process client registration information. When the target URL comes from a client or an untrusted source, that outbound access creates an SSRF attack surface.

**Server-Side Request Forgery (SSRF)** is an attack that tricks a server into sending requests to an address controlled or chosen by the attacker. An attacker can leverage the Authorization Server's network position to probe internal services, access cloud metadata endpoints, call admin APIs, or exfiltrate data from systems unreachable from the Internet.

In OAuth 2.0 and OpenID Connect, notable URLs include `jwks_uri`, `request_uri`, `sector_identifier_uri`, and external OpenID Provider metadata URLs. Not every URL field in client metadata causes the Authorization Server to fetch that URL itself. Risk arises only when a server-side component actually dereferences, fetches, previews, or proxies the URL. Therefore, this lesson starts by pinpointing exactly where the application makes outbound requests.

Objectives after this lesson:

- Identify URL-fetching flows that can create SSRF vulnerabilities.
- Distinguish URLs used for browser navigation from URLs fetched by the server.
- Validate URLs, DNS resolution, IP addresses, redirects, and TLS before connecting.
- Constrain outbound access at both the application and network infrastructure layers.
- Design secure JWKS/metadata fetching in Spring Authorization Server.
- Test DNS rebinding, redirects, IPv4/IPv6 variants, cloud metadata, and URL edge cases.

## 2. SSRF in an Authorization Server

### 2.1. Basic Attack Flow

Suppose a client registers the following metadata:

```json
{
  "client_id": "example-client",
  "jwks_uri": "https://keys.example.net/jwks.json"
}
```

When the Authorization Server needs to verify the signature of a client assertion or client-signed message, the verifier may fetch the JWK Set from `jwks_uri`. If the client is allowed to substitute an arbitrary URL, an attacker could register:

```text
http://169.254.169.254/latest/meta-data/
```

If the server fetches the URL without destination controls, the request can reach the cloud instance metadata service or another internal service. The attacker never needs direct access to the internal network; the Authorization Server itself becomes the proxy.

```mermaid
flowchart TD
    A[Attacker registers client with malicious URL] --> B[Authorization Server stores metadata]
    B --> C[Verification flow triggers JWKS or metadata fetch]
    C --> D[HTTP client sends outbound request]
    D --> E{Is destination controlled?}
    E -- No --> F[Probes internal network or cloud metadata]
    E -- Yes --> G[Accesses only permitted destinations]
```

SSRF can also be blind SSRF: the attacker cannot read the response directly, yet still causes the server to call internal endpoints—mutating state, triggering jobs, or leaking signals via response timing and logs.

### 2.2. Why Does an Authorization Server Have Notable Network Access?

An Authorization Server typically connects to databases, caches, KMS/HSMs, secret managers, service discovery, admin systems, and internal APIs. An SSRF request can inherit this workload's network position and part of its reachability.

Risk increases when:

- The workload can reach cloud instance metadata or the container control plane.
- The HTTP client automatically follows redirects to another host.
- The server accepts URLs via dynamic client registration without policy checks.
- DNS is resolved multiple times, enabling DNS rebinding.
- Requests attach cookies, `Authorization` headers, or ambient credentials.
- Responses are returned to the client or logged without sanitization.
- A fetch endpoint is invoked repeatedly at high frequency, causing DoS or connection exhaustion.

SSRF is not limited to HTTP. URL-handling libraries can support multiple schemes or protocols. For metadata/JWKS fetching, allow only HTTPS and a controlled HTTP client; never pass arbitrary URLs to APIs supporting `file:`, `jar:`, `ftp:`, `gopher:`, or other schemes.

## 3. Identifying URLs That Can Trigger Outbound Requests

### 3.1. `jwks_uri`

`jwks_uri` is the URL published by one party so the peer can retrieve its JSON Web Key Set. In client authentication, the Authorization Server may use this URL to fetch a client's public key when verifying JWT client assertions or client-signed messages, depending on grant, configuration, and library version.

This point requires tight control because:

- The value may be declared in client metadata or dynamic client registration.
- The request may occur during sensitive flows like the token endpoint.
- The URL may be cached, refreshed, or re-fetched when an unseen `kid` appears.
- A modified `jwks_uri` can alter the trusted key source.

Do not confuse a client's `jwks_uri` with the Authorization Server's own JWKS endpoint. The server's JWKS is typically served from the server's `JWKSource`/key management and advertised in metadata; the client's URL is an external public key source the server may need to fetch.

### 3.2. `request_uri`

OAuth 2.0 Request Parameters and OpenID Connect allow request objects to be passed by value or referenced via `request_uri`. If the Authorization Server supports dereferencing request URIs, it downloads content from that URL. When the URL comes from a client or authorization request caller, it is a potential SSRF vector.

A secure policy can require passing Request Objects by value or via Pushed Authorization Requests (PAR), restrict `request_uri` to an allowlist, and verify the client before dereferencing. Never fetch an arbitrary URL merely because it appears in an authorization request.

### 3.3. `sector_identifier_uri`

OpenID Connect uses `sector_identifier_uri` in certain cases to fetch a list of redirect URIs for pairwise subject identifiers. The OpenID Provider may download JSON from this URL to validate associated redirect URIs.

If the Authorization Server performs this fetch, the URL must pass through the exact same secure outbound policy. Cap response size, parse JSON strictly against the expected schema, and validate the URI list. Never let parsers or content handlers trigger secondary unexpected URL fetches.

### 3.4. External OpenID Provider and Identity Provider Metadata

In federation setups or when the Authorization Server acts as a relying party to an upstream OpenID Provider, the application may fetch a discovery document from a configured issuer and then use `jwks_uri`, `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`, or `end_session_endpoint` from that metadata.

Normally, upstream issuers must come from trusted admin configuration or a controlled tenant onboarding process. If tenants or users can enter arbitrary issuer URLs and trigger server-side discovery, both discovery and every endpoint URL returned by metadata become SSRF vectors. Validate the exact issuer and every outbound destination before use.

Do not assume every endpoint in a discovery document is called by the Authorization Server itself. For example, `authorization_endpoint` is usually navigated to by the browser/client; `userinfo_endpoint` may be called by the OIDC client. Only URLs fetched by the server itself are direct outbound sinks, though other URLs still require role-appropriate validation and become risks if proxies, health checks, or preview services exist.

### 3.5. Other URLs in Client Metadata

| Field | Common usage | When is it SSRF? |
|---|---|---|
| `jwks_uri` | Server fetches client public keys | Yes, when the server dereferences the URL |
| `request_uri` | Server fetches Request Object by reference | Yes, when dereferencing is enabled |
| `sector_identifier_uri` | Server fetches redirect URI list for pairwise subjects | Yes, when the server fetches the JSON document |
| `issuer` | Issuer identifier; discovery may be initiated from it | Yes, when the server fetches metadata from this URL |
| `authorization_endpoint` | Client/browser navigates the user | Typically not a server-side fetch in authorization redirects |
| `token_endpoint` | OAuth client sends token requests | Only SSRF if a server-side component of this system calls it |
| `userinfo_endpoint` | OIDC client retrieves user claims | Yes, if this server acts as an RP or proxy calling it |
| `logo_uri`, `client_uri`, `policy_uri`, `tos_uri` | UI display or user links | Yes, if the server generates previews, downloads images, probes URLs, or proxies content |
| `redirect_uris`, `post_logout_redirect_uris` | Browser redirects back to the client | Not SSRF merely because URLs are stored; primary risk is open redirect/redirect URI validation |

This distinction prevents misapplying controls. `redirect_uri` requires exact matching per OAuth/OIDC and client policy; the server should never download it to "check existence." Conversely, `jwks_uri` must be guarded as an outbound request if the server dereferences it.

## 4. SSRF Defense Principles

A solid design uses multiple layers. Never rely on a single simple URL check.

1. **Minimize fetched URLs:** enable dereferencing only where genuinely needed; prefer static config or allowlists.
2. **Validate URLs before use:** check scheme, host, port, userinfo, fragment, syntax, and domain policy.
3. **Validate network addresses:** reject loopback, private, link-local, multicast, reserved, and internal infrastructure ranges.
4. **Protect DNS and connections:** prevent DNS rebinding and ensure the socket connects to the exact validated IP.
5. **Control redirects:** disable automatic redirects or re-validate every hop.
6. **Bound HTTP requests:** enforce timeouts, max response size, content type, concurrency, rate limits, and retry caps.
7. **Send no unexpected credentials:** never forward cookies, bearer tokens, client secrets, or inbound request headers.
8. **Restrict network egress:** block workloads from reaching metadata endpoints and unnecessary internal networks.
9. **Monitor and test:** log safe metadata, alert on blocked destinations, and test URL/DNS variants.

No single check replaces the others. A syntactically valid URL can resolve to an internal IP; a public hostname can redirect to a private IP; DNS that was safe at registration can change before connection time.

## 5. Validating URLs Before Fetching

### 5.1. Standard-Compliant URI Parsing

Never use string checks like `startsWith("https://")` or naive regexes. Parse with a proper URI parser and validate each component:

- Accept only `https` scheme for production metadata/JWKS URLs.
- Host must exist and be canonicalized per hostname/IDN rules.
- Reject userinfo such as `https://user:pass@host/`.
- Reject fragments and URL forms outside the supported profile.
- Accept only default ports or explicitly allowlisted ports.
- Disallow IP literals unless an explicit policy permits a specific destination.
- Bound URL and domain lengths; reject internal hostnames per environment conventions.

Examples of URLs that trick naive string checks:

```text
https://trusted.example@127.0.0.1/admin
https://trusted.example.evil.invalid/jwks
https://trusted.example:443@169.254.169.254/latest/meta-data/
http://127.1/
http://2130706433/
http://[::1]/
```

In the first URL, `trusted.example` is userinfo while the actual host is `127.0.0.1`. Shorthand/integer IPv4 forms and IPv6 literals evade filters searching only for the string `127.0.0.1`. Use well-maintained parsers and address-checking libraries rather than hand-rolled regex IP normalizers.

### 5.2. Hostname and Port Allowlists

When only a known set of clients or issuers exists, an explicit hostname allowlist is best. For example, allow only `keys.partner.example` on port 443 for an approved client.

Allowlists must compare canonicalized hostnames, exact DNS label boundaries, and ports. Never use naive suffix checks such as `host.endsWith("partner.example")`, because `notpartner.example` or `partner.example.attacker.invalid` can slip through if label boundaries are ignored.

With open dynamic registration, static allowlists may be impractical. In that case, enforce egress proxy/firewall policies, block non-public IP ranges, and validate DNS/redirects at connection time. A successful client registration never makes a client's URL trustworthy.

### 5.3. Blocking Non-Public IPs and Sensitive Addresses

After resolving the hostname, inspect every A and AAAA record. Reject non-global unicast addresses per network policy, including at minimum:

| Address group | Examples/ranges typically blocked |
|---|---|
| IPv4 loopback | `127.0.0.0/8` |
| IPv4 private | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` |
| IPv4 link-local | `169.254.0.0/16`, including common cloud metadata |
| IPv4 shared address space | `100.64.0.0/10` |
| IPv4 unspecified/reserved/multicast | `0.0.0.0/8`, `224.0.0.0/4`, `240.0.0.0/4`, and other special ranges |
| IPv6 loopback/unspecified | `::1/128`, `::/128` |
| IPv6 unique local | `fc00::/7` |
| IPv6 link-local/multicast | `fe80::/10`, `ff00::/8` |
| IPv4-mapped IPv6 | IPv4 addresses embedded in IPv6; inspect the inner IPv4 address |

This list shows common ranges to watch, not an exhaustive set. Use libraries or policies grounded in the IANA Special-Purpose Address Registries plus your organization's internal CIDRs. Also account for NAT64, service meshes, Kubernetes service CIDRs, VPNs, and private cloud ranges.

Explicitly block cloud metadata endpoints and link-local ranges at the network layer. Metadata addresses vary across clouds/platforms; never rely on blocking only one IP.

If a hostname returns multiple IPs, never pick one valid address and ignore forbidden ones. The safe policy is rejecting the hostname if *any* resolved record violates policy, or routing exclusively through an egress proxy that enforces policy on the actual connected IP.

## 6. DNS Rebinding and Controlling the Actual Connection

### 6.1. DNS Rebinding

DNS rebinding occurs when a hostname initially resolves to a public IP to pass validation, then resolves to an internal IP on a subsequent lookup. If the application validates DNS and then lets an HTTP client re-resolve independently, the two lookups can yield different results.

Example:

1. At registration, `attacker.example` resolves to a public IP.
2. The URL passes validation.
3. When the Authorization Server fetches it, DNS returns `127.0.0.1` or a metadata IP.
4. The HTTP client connects to the internal target.

Therefore, checking DNS once at registration time is never sufficient.

### 6.2. Pinning Validation to the Connected IP

Strong defenses guarantee that the actual IP used by the socket is the exact IP validated. Approaches include:

- An egress proxy that performs DNS resolution, applies IP policies, and connects to the verified IP.
- An HTTP client with a custom resolver/transport that pins the validated IP to the socket while still verifying the TLS certificate against the original hostname.
- Network policies/firewalls blocking private, loopback, link-local, metadata, and management ranges even if application logic is bypassed.

Never merely call `InetAddress.getAllByName()` to check and then issue requests with a default HTTP client. That leaves a time-of-check/time-of-use (TOCTOU) gap if the HTTP client re-resolves DNS. If you cannot reliably enforce DNS-to-connect pinning in-process, route outbound fetches through a hardened egress proxy.

### 6.3. TLS Hostname Verification

When connecting to a pinned IP, TLS must still verify the certificate against the URL's hostname. Never disable hostname verification, never use a trust-all certificate manager, and never ignore certificate errors to "fix" connectivity issues.

When using a proxy, explicitly define whether TLS terminates at the proxy or the application. Proxies must never weaken destination identity verification or allow arbitrary tunneling into internal networks.

## 7. Redirects, HTTP Headers, and Response Payloads

### 7.1. Redirects

A public URL can return `301`, `302`, `307`, or `308` pointing to `http://127.0.0.1`, a metadata address, or another host. If the HTTP client follows redirects automatically, validating the initial URL does not protect the final request.

For JWKS and metadata, disabling redirects is usually the simplest choice. If protocols or infrastructure require redirects, every `Location` must be parsed and fully re-validated: scheme, host, port, DNS, IP, TLS, and egress policy. Cap hop counts and detect loops. Never forward `Authorization` headers or credentials across redirects to another host.

### 7.2. Never Send Unexpected Credentials

Outbound requests fetching public JWKS/metadata normally need no user cookies, session cookies, inbound bearer tokens, or database credentials. Use a dedicated HTTP client with no shared cookie jar, no inherited headers from the inbound request, and no ambient authentication enabled.

If a protocol requires authenticating to a metadata source, bind those credentials strictly to an admin-trusted host and never forward them on redirects. Avoid reusing an HTTP client configured with internal credentials for client-supplied URLs.

### 7.3. Response Bounds

A malicious endpoint can return huge bodies, deeply nested JSON, excessive JWKs, or stalled streams. Bound all of:

- Connect timeout, response timeout, and total request deadline.
- Maximum bytes read from the response, including streaming handlers.
- Supported `Content-Type` headers and formats.
- JSON nesting depth, element counts, key counts, and field sizes.
- Concurrent connections, retries, and per-client refresh frequency.
- Error rates and cache durations to prevent continuous re-fetching.

For JWKS, accept only valid JWK Set structures with permitted key types and algorithms. Never use `kid`, `jku`, or `x5u` from an untrusted JWT to trigger additional outbound URL fetches without an explicit policy. `kid` selects a key within an already-trusted set—it is not a URL.

## 8. Designing Safe Fetching in Spring

### 8.1. Centralize Outbound Fetching in One Component

Do not let individual providers or controllers instantiate `RestTemplate`, `RestClient`, or `WebClient` and call URLs directly. Create a dedicated service with clear ownership, such as `SafeMetadataFetcher`, so every URL dereference passes through the same policy.

Conceptual contract:

```java
public interface SafeMetadataFetcher {

    byte[] fetchJwks(URI jwksUri, ClientId clientId);

    byte[] fetchSectorIdentifier(URI sectorIdentifierUri, ClientId clientId);

    byte[] fetchRequestObject(URI requestUri, ClientId clientId);
}
```

This is an illustrative API, not a built-in Spring Authorization Server interface. In real implementations, prefer returning already-parsed/validated domain types rather than raw `byte[]`, so callers cannot forget size limits or schema checks.

The service should coordinate:

1. Load persisted metadata for the target client and confirm which fetch capability is allowed.
2. Parse the URI and apply allowlists/policies.
3. Perform resolution/egress validation pinned to the actual connection.
4. Send the request via a dedicated HTTP client with redirects disabled.
5. Enforce timeouts, response size caps, and content-type checks.
6. Parse against the expected schema and validate contents.
7. Cache per client/URL/version with bounded TTL.
8. Fail safely if policy or fetch fails.

### 8.2. Configuring an HTTP Client Without Automatic Redirects

With Java's `HttpClient`, you can disable automatic redirects and configure client/request timeouts. Illustrative example:

```java
HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder(validatedUri)
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/jwk-set+json, application/json")
        .GET()
        .build();
```

This snippet illustrates only timeout and redirect settings. It **does not by itself solve DNS rebinding, IP filtering, body limits, egress firewalls, or schema validation**. Never pass an unvalidated URL into `validatedUri`. Use a transport or proxy that enforces actual destination IP controls; if using `BodyHandlers.ofInputStream()`, enforce a strict byte limit while reading and close the stream properly.

### 8.3. Integrating with Spring Authorization Server

In Spring Authorization Server, `RegisteredClientRepository` persists client metadata. Depending on version and authentication flow, `RegisteredClient.getClientSettings().getJwkSetUrl()` may be used by client assertion verification to fetch remote public keys. Some configurations use `JwtClientAssertionDecoderFactory` to build the client's decoder.

When enabling `private_key_jwt` or features consuming public keys from `jwks_uri`, inspect your exact library version's implementation to verify when JWK Sets are fetched, how they are cached, and how to customize the HTTP transport/resolver. Never assume `RegisteredClientRepository` validates SSRF merely because metadata was saved.

Control points:

- Validate `jwks_uri` at client registration or update time.
- Re-validate at fetch time; metadata may be stale or DNS may have changed.
- Configure JWK resolvers/HTTP transports through a centralized policy.
- Never allow clients to modify `jwks_uri` arbitrarily without verification and auditing.
- Preserve signature, `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, and all other client authentication checks.
- Fail closed on fetch errors: never accept an assertion if the required key cannot be retrieved.

The Authorization Server's `JWKSource` managing the server's own signing keys is a separate concern. Never replace it with a client-supplied URL source, and never let `jku` in an unverified JWT dictate trusted key sources.

### 8.4. Discovery Metadata and Upstream Issuers

If the application supports federating with upstream IdPs, issuer configuration should come from admins or a controlled tenant onboarding workflow. Discovery clients must use the same outbound fetch policy. After fetching metadata, verify `issuer` in the document matches the expected issuer exactly; then validate any endpoint URLs the server itself will call.

Do not automatically trust every URL in metadata merely because JSON was downloaded over HTTPS. HTTPS proves connection to that hostname, not that the hostname is an authorized issuer for the tenant. Validate issuer, tenant binding, signing keys, and endpoint policies.

### 8.5. Never Feed Client URLs into Arbitrary Fetch Sinks

Never pass URLs from registration requests directly into:

- `RestTemplate.getForObject(url, ...)` or `RestClient.get().uri(url)`.
- `WebClient.get().uri(url)` without policy enforcement.
- Shared HTTP clients carrying cookies or `Authorization` headers.
- Image proxies, link previews, favicon fetchers, health checkers, or webhook testers.
- XML/JSON parsers configured to resolve external entities/resources.

Auxiliary components such as admin UIs or preview services must also enforce outbound policies. Never let an admin UI generate previews of `logo_uri` or `client_uri` via unrestricted server-side fetches.

## 9. Caching, Rate Limiting, and Resilience

JWKS and metadata generally do not need re-fetching on every request. Sensible caching shrinks the SSRF surface, reduces partner endpoint load, and mitigates DoS.

- Cache keyed by client/issuer and verified URL; never let one client overwrite another client's cache entry.
- Respect `Cache-Control` within server policy bounds; enforce minimum and maximum TTLs.
- Deduplicate concurrent refreshes for the same client/URL using single-flight or distributed locks.
- Refresh only on TTL expiry, unseen `kid`, or bounded schedules; prevent one token request from triggering floods of fetches.
- Rate-limit by client, tenant, destination host, and source address.
- Use circuit breakers/backoff so failing endpoints do not cause continuous server retries.
- Define controlled stale-key policies; never keep trusting revoked keys indefinitely just because upstream is unreachable.
- When a URL or metadata changes, invalidate stale cache entries via an audited process.

If a fetch fails, never fall back to an arbitrary cached key or skip signature verification to preserve availability. Fallback policies must distinguish transient failures from key rotation and potential compromise.

## 10. Defense at the Network Infrastructure Layer

Application validation can have bugs. Network egress control is an independent and essential layer of defense.

- Allow the Authorization Server to reach only required outbound destinations.
- Block access to loopback, private CIDRs, link-local, metadata IPs, the Kubernetes control plane, database subnets, and management subnets.
- Use an egress proxy to enforce hostnames, DNS resolution, destination IPs, ports, and redirects.
- Isolate Authorization Server workloads from admin workloads and databases via network segmentation.
- Never grant broad cloud IAM privileges to a process that only needs to fetch public JWKS.
- Where supported by the platform, require IMDSv2 or equivalent, restrict hop counts, and block metadata endpoints from workloads that do not need them.
- Check IPv4, IPv6, NAT64, service meshes, and proxy bypasses; never rely solely on one IPv4 firewall rule.

Network policies must be tested from the actual container/pod/process running the Authorization Server. Testing from a developer laptop does not prove production workload egress controls are active.

## 11. Error Handling and Returned Information

Never expose internal details when a URL is rejected or a fetch fails. Admin APIs can return messages such as "Metadata URL does not satisfy access policy" alongside a correlation ID. Never return stack traces, internal IPs, response bodies from probed endpoints, or credentials.

At the token endpoint, if the required JWK to verify a client assertion cannot be retrieved, reject authentication with the appropriate OAuth error. Never treat DNS errors, timeouts, or HTTP 500s from `jwks_uri` as a reason to skip signature verification.

Safe logs should record:

- Verified Client ID or internal reference ID.
- URL category (`JWKS`, `REQUEST_OBJECT`, `SECTOR_IDENTIFIER`, `DISCOVERY`).
- Normalized host or policy code, omitting query strings that could contain secrets.
- Block reason (private IP, scheme, port, redirect, timeout, response size).
- Timestamp, correlation ID, and outcome.

Never log full URLs if query strings might contain tokens or signatures. Never log response bodies, authorization headers, or cookies. Metrics should use low-cardinality labels—never arbitrary URLs as labels.

## 12. Testing SSRF Controls

Run tests in an isolated environment with mock endpoints, never probing production metadata services. Use local test servers to confirm the application rejects requests before reaching targets.

| Scenario | Expected result |
|---|---|
| `jwks_uri` uses HTTPS to allowlisted hostname | Fetch succeeds and valid JWKS parses |
| `jwks_uri` uses `http://` | Rejected by HTTPS policy |
| URL contains userinfo or fragment | Rejected |
| URL points to loopback/private/link-local | Rejected |
| URL points to cloud metadata IP | Blocked by application and network egress |
| Hostname resolves to both public and private IPs | Rejected or blocked by egress proxy |
| DNS flips from public to private after registration | Actual connection is still blocked |
| Public URL redirects to private IP | Redirect disabled or next hop rejected |
| Integer/shorthand IPv4 or IPv6 loopback | Canonicalized and rejected |
| URL uses disallowed port | Rejected |
| Endpoint returns oversized body or hangs | Reading stops at byte cap and timeout |
| Endpoint returns wrong content type or invalid JSON schema | Rejected |
| JWKS has too many keys or unsupported key types | Rejected by parser/policy limits |
| Client sends arbitrary `jku`/`x5u` in JWT | Never triggers outbound fetches outside policy |
| Concurrent token requests need the same JWKS | Cache/single-flight prevents fetch storms |
| Upstream JWKS temporarily fails | Signature check is never skipped; fails per policy |
| Outbound proxy unavailable | Fetch-dependent operations fail closed |
| `redirect_uri` points to internal address | Handled by redirect URI validation; server never fetches it |

Include integration tests covering:

- A mock DNS resolver returning different A/AAAA records over time.
- A mock HTTP server returning redirects to loopback or link-local.
- Oversized response bodies and slow responses.
- Verifying outbound requests carry no `Authorization` or `Cookie` headers from inbound requests.
- Cache isolation between two clients sharing the same `kid` but different JWKS.
- Confirming `jwks_uri` changes require admin authorization, auditing, and old cache invalidation.

Never rely solely on a unit test of `validateUrl` to conclude SSRF is mitigated. Verify actual outbound requests and network egress policies.

## 13. Common Design Pitfalls

| Pitfall | Risk | Fix |
|---|---|---|
| Trusting `jwks_uri` because the client is registered | Registered clients can still be malicious or compromised | Validate URL and egress at fetch time |
| Checking hostname only at registration | DNS can change before connection time | Protect DNS-to-connect and network egress |
| Blocking only `127.0.0.1` via regex | Misses shorthand IPs, IPv6, and other private ranges | Use proper parsers and full IP policies |
| Letting HTTP clients follow redirects automatically | Public URL redirects into internal network | Disable redirects or re-validate every hop |
| Checking `InetAddress` before fetching | HTTP client may re-resolve DNS | Pin resolved IP or route via egress proxy |
| Reusing an HTTP client with internal credentials | SSRF sends credentials to attacker host | Dedicated client with no ambient auth/cookies |
| Leaving responses unbounded | DoS via huge bodies, deep JSON, or slowloris | Enforce timeouts, byte caps, and parser limits |
| Fetching JWKS on every token request | DoS and wider exploitation window | Use caching, single-flight, and rate limits |
| Trusting every URL in discovery metadata | Metadata can point to internal endpoints or wrong issuer | Validate issuer and endpoint policies |
| Fetching `redirect_uri` to validate it | SSRF and broken OAuth redirect model | Validate URIs per OAuth rules; never fetch them |
| Logging full URLs | Leaks query tokens/signatures and internal targets | Log normalized host/policy codes |
| Relying solely on application checks | Code bugs can bypass policy | Add deny-by-default network egress rules |

## 14. Implementation Checklist

- [ ] Inventoried all server-side URL fetch points in the Authorization Server and auxiliary components.
- [ ] Separated browser-navigated URLs from server-dereferenced URLs.
- [ ] Dedicated policies exist for `jwks_uri`, `request_uri`, `sector_identifier_uri`, and issuer discovery.
- [ ] URL dereferencing features are enabled only when explicitly required by business needs.
- [ ] URIs are parsed cleanly; scheme, host, port, userinfo, and fragment are validated.
- [ ] Hostname allowlists exist where feasible; otherwise IP policies and egress proxies are enforced.
- [ ] Loopback, private, link-local, metadata, reserved, and internal CIDRs are blocked for IPv4/IPv6.
- [ ] DNS validation is pinned to the actual connected IP; DNS rebinding is prevented.
- [ ] Redirects are disabled or every hop is fully re-validated.
- [ ] TLS certificate and hostname verification are always enabled.
- [ ] HTTP client forwards no cookies, bearer tokens, or unexpected credentials.
- [ ] Connect/response timeouts, response byte caps, parser limits, and concurrency limits are configured.
- [ ] JWKS/metadata are cached, rate-limited, and refreshed safely.
- [ ] `jku`/`x5u` from unverified JWTs never trigger arbitrary outbound fetches.
- [ ] Network egress blocks metadata endpoints and unnecessary management subnets.
- [ ] Logs/metrics contain no sensitive URL queries, tokens, cookies, or response bodies.
- [ ] Integration tests cover redirects, DNS rebinding, IP variants, IPv6, and oversized payloads.
- [ ] Exact Spring/Spring Security/Spring Authorization Server versions have been audited for fetch/cache behavior.

## 15. Conclusion

SSRF in an Authorization Server typically emerges when the server dereferences URLs supplied by clients or external metadata. `jwks_uri`, `request_uri`, `sector_identifier_uri`, and issuer discovery must each be reviewed according to enabled features. Defenses must combine URI validation, IP filtering, DNS rebinding protection, redirect control, HTTP response bounds, and network egress rules. Within Spring Authorization Server, review how your exact version fetches JWK Sets from `RegisteredClient` and route all outbound fetches through a centralized policy. A successful client registration or metadata download never makes a URL inherently trustworthy; accept data only after verifying its source, connection, and payload.

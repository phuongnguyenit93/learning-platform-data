# Restricting Trusted Proxies and Avoiding Accepting Every Proxy in Spring Security CAS

## 1. Objectives and Scenario

**CAS Proxy Authentication** allows a service that has authenticated a user at CAS to call a downstream service on the user's behalf without passing the user's password. This is useful for portals, gateways, and business applications calling backends, yet it also introduces an additional **authorization boundary**: the backend must decide **which intermediary partners are permitted to act on behalf of the user**, not merely know “CAS authenticated the username.”

Consider the system:

- **Portal**: web application receiving a Service Ticket (ST) from the browser, needing to call a backend on the user's behalf.
- **Gateway**: intermediary service that may further delegate the request to the backend.
- **Reports API**: backend receiving a **Proxy Ticket (PT)** issued by CAS for its own API service.
- **CAS Server**: issues STs, Proxy-Granting Tickets (PGTs), and PTs, and validates tickets against the target service URL.

A dangerous misconfiguration is setting **`acceptAnyProxy=true`** on `Cas20ProxyTicketValidator` or configuring overly broad `allowedProxyChains` on the backend. When that happens, an unfamiliar service in the same CAS federation that holds a PGT can become an accepted delegator at the backend if other conditions allow. CAS ticket validation **does not decide for the backend to trust every proxy**.

After this lesson, you should be able to:

1. Distinguish **ST, PT, PGT, PGTIOU**, and the **CAS proxy chain**.
2. Understand `<cas:proxies>` in `/proxyValidate` responses: **the closest proxy appears first**, with earlier hops following behind.
3. Apply **deny by default**, **exact proxy callback URL allowlists**, **full chain and order matching**, and **target service binding**.
4. Explain why **`acceptAnyProxy=true`** appears only as a functional illustration in some legacy docs and is **unsuitable as a production default**.
5. Configure `Cas20ProxyTicketValidator`/`allowedProxyChains` and distinguish settings across the **Spring Security provider**, **Apereo Java CAS Client filter**, and **CAS Server service registry**.
6. Restrict on the CAS Server **which services may obtain a PGT**, **which HTTPS callbacks are allowed**, and **which target services PTs may be issued for**.
7. Understand **`StatelessTicketCache`** risks, application-layer replay, PGT lifecycles, and secret management.
8. Run standalone Java 17 code illustrating strict chain policies, valid chains, and attack/misconfiguration cases.
9. Apply checklists, test matrices, and ticket-safe diagnostic workflows.

**Guiding principle:** **The CAS Server validates ticket validity and supplies the proxy history; the target service decides whether that history belongs to its trusted list and whether the business action is authorized.** These two checks are **joint requirements**, never substitutes for each other.

## 2. Trust Boundaries in CAS Proxy

### 2.1. Direct ST Flow Without Proxying

~~~text
Browser -> CAS /login?service=https://portal.example.test/login/cas
CAS -> Browser: redirect + ST-...
Browser -> Portal /login/cas?ticket=ST-...
Portal -> CAS /serviceValidate?ticket=ST-...&service=<Portal service>
CAS -> Portal: authenticationSuccess(username)
Portal: create local Authentication if user policy permits
~~~

In this case, no Proxy Ticket is needed. Portal validates the ST with CAS and then uses a local session. If a service has no need to delegate to another backend, **do not enable proxy features solely for CAS login**.

### 2.2. Portal Obtains a PGT to Call a Backend

~~~text
Browser -- ST --> Portal
                   |
                   | /serviceValidate:
                   |   ticket = ST
                   |   service = https://portal.example.test/login/cas
                   |   pgtUrl  = https://portal.example.test/login/cas/proxyreceptor
                   v
                CAS Server
                   |
                   | HTTPS callback to pgtUrl
                   | ?pgtIou=PGTIOU-...&pgtId=PGT-...
                   v
                Portal proxy receptor / PGT storage
                   |
                   | /serviceValidate response contains PGTIOU
                   | Portal matches PGTIOU with received PGT
                   |
                   | /proxy?pgt=PGT-...&
                   |        targetService=https://reports.example.test/api/cas
                   v
                CAS Server
                   |
                   | issues PT strictly for Reports API target service
                   v
Portal --- PT ---> Reports API
                   |
                   | /proxyValidate:
                   |  service=https://reports.example.test/api/cas
                   |  ticket=PT-...
                   v
                CAS Server
                   |
                   | authenticationSuccess
                   | proxies=[https://portal.example.test/.../proxyreceptor]
                   v
                Reports API
                   |
                   | FULL MATCH against trusted proxy list
                   | + identity + authorization policy
                   v
                Business processing
~~~

There are **two distinct permission filters**:

- The CAS Server decides whether Portal may be **issued PGTs/PTs** under the **CAS registered-service proxy policy** and callback validity.
- Reports API decides whether **Portal is a trusted proxy for this API** via a **proxy chain allowlist**.

Passing only one of the two filters is **insufficient**. Never treat “CAS issued a PT” as justification to allow arbitrary proxies at Reports.

### 2.3. Two Hops: Portal → Gateway → Reports

If Portal delegates to Gateway, and Gateway delegates to Reports:

~~~text
User
   |
   v
Portal  (earlier proxy hop)
   |
   v
Gateway (most recent proxy hop)
   |
   v
Reports API (target service)
~~~

In CAS 2.0/3.0, if Portal's proxy callback URL is `P` and Gateway's is `G`, the `/proxyValidate` response at Reports shows:

~~~text
cas:proxies = [G, P]
               ^  ^
         closest  traversed earlier
~~~

**Order is part of the policy.** `[G, P]` is not equivalent to `[P, G]`. Do not invert the order just because business diagrams read left-to-right. The CAS Protocol mandates **the closest proxy first**.

## 3. Distinguishing Ticket Types and Delegation Scopes

| Artifact | Issued To Whom? | Where Is It Used? | Limitations |
| --- | --- | --- | --- |
| **Service Ticket (ST)** | User via CAS for one service | Browser callback and `/serviceValidate` or appropriate validation profile | Bound to **one service**, **single validation attempt**, short TTL |
| **Proxy-Granting Ticket (PGT)** | Service approved by CAS to proxy | `/proxy` to request PTs | Higher-privilege credential; can mint **multiple PTs**; protect as a secret |
| **PGT IOU (PGTIOU)** | Ticket validation response channel | Matches validation response with callback carrying PGT | Correlation handle, **not a PGT** |
| **Proxy Ticket (PT)** | One specific backend target service | Backend sends to CAS `/proxyValidate` | Bound to **one target service**, **single validation attempt**, short TTL |
| **TGT/TGC** | SSO session at CAS/Browser | Used by CAS to maintain SSO login and mint STs | Never treat as PGT or forward to backends |

A PT may carry a `PT-` prefix, yet **never parse prefixes to decide trusted delegation exists**. CAS determines whether the ticket is valid. **Proxy history must come from the assertion built by `TicketValidator` after calling a trusted CAS Server**, never from an HTTP header like `X-Proxy-Chain` sent by the client.

### 3.1. Single-Use Semantics Still Apply to PTs

The CAS Protocol mandates that **STs and PTs are valid for one ticket validation attempt**. Even if validation fails, CAS must invalidate the ticket. Therefore:

- The backend must never resubmit the exact same PT after an `INVALID_TICKET` response expecting CAS to re-authorize it.
- If the service is called twice, the caller normally needs a **fresh PT** from its PGT via an authorized flow.
- **PGT differs from PT**: a PGT can mint multiple PTs, so PGTs require strict storage, TTLs, auditing, and access locks.
- If Spring caches PT results for a **stateless client**, letting the client resend the same string to the app is **Spring-side caching behavior**, not CAS allowing multi-use PTs.

## 4. Where Does the Proxy Chain Live and How Is It Interpreted?

A valid response from `/proxyValidate` may look like:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>employee-42</cas:user>
    <cas:proxies>
      <cas:proxy>https://gateway.example.test/login/cas/proxyreceptor</cas:proxy>
      <cas:proxy>https://portal.example.test/login/cas/proxyreceptor</cas:proxy>
    </cas:proxies>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

This is an **illustrative sample**. An XML response containing `authenticationSuccess` must be confirmed by a **`TicketValidator` calling the right CAS Server over TLS and validating the service ticket**. Never accept such XML from a browser and treat the user as authenticated.

**`cas:proxy` is the proxy callback/`pgtUrl` used by CAS to identify an intermediary service**, not a human name, HTTP forward proxy address, ingress IP, or hostname seen via `X-Forwarded-For`.

### 4.1. CAS Lists Proxies in Reverse Order of the Original Path

Example business flow:

~~~text
Portal -> Gateway -> Reports API
~~~

`<cas:proxy>` ordering:

~~~text
1. https://gateway.example.test/login/cas/proxyreceptor
2. https://portal.example.test/login/cas/proxyreceptor
~~~

If the backend is permitted **only** for direct calls from Portal, the allowlist is `[Portal]`, never implicitly accepting `[Gateway, Portal]`. If the backend permits Gateway forwarding from Portal, declare a **distinct chain** `[Gateway, Portal]`.

### 4.2. Only the Full Chain Should Be Trusted

| CAS-Validated Chain | Reports Policy | Decision |
| --- | --- | --- |
| `[Portal]` | Accept Portal only | PASS |
| `[Gateway, Portal]` | Allow Gateway after Portal | PASS |
| `[Gateway]` | Direct Gateway only allowed | PASS if listed separately |
| `[Unknown]` | Unknown not listed | FAIL |
| `[Portal, Gateway]` | Only `[Gateway, Portal]` allowed | FAIL due to **wrong order** |
| `[Gateway, Portal, Unknown]` | Only two hops allowed | FAIL due to **unknown hop** |
| `[]` | Backend **accepts proxied PTs only** | FAIL |
| `[Portal]` | Backend **accepts two-hop chains only** | FAIL |
| `[Portal]` with wrong service | Valid chain, yet ticket issued for another service | FAIL |

**Never ask merely “does the chain contain Portal?”** `[attacker, Portal]` still “contains Portal” while inserting an unauthorized hop. Likewise, checking only the last or first proxy can miss dangerous intermediaries in between.

## 5. Risks of `acceptAnyProxy=true`

In some Spring Security CAS tutorials, an open configuration snippet illustrating **proxy ticket authentication** shows:

~~~xml
<!-- ILLUSTRATIVE PERMISSIVE CONFIG ONLY - DO NOT USE IN PROD -->
<bean class="org.apereo.cas.client.validation.Cas20ProxyTicketValidator">
  <constructor-arg value="https://sso.example.test/cas"/>
  <property name="acceptAnyProxy" value="true"/>
</bean>
~~~

**This is a production anti-pattern**, not a recommended setup. Apereo Java CAS Client documentation confirms `acceptAnyProxy` defaults to **`false`** and provides `allowedProxyChains` to specify accepted chains.

Why is it dangerous?

1. Another service in the CAS federation might be permitted by CAS to obtain a PGT.
2. That service could request a PT for the backend target service if CAS policy allows.
3. A backend configured with `acceptAnyProxy=true` ignores **delegation through an unfamiliar partner**.
4. The backend may take the verified username and grant business permissions even though **the delegating source is not in the trusted list**.
5. If an intermediary service's PGT leaks, the scope of spoofed delegation can be wider than expected.

**Note that `acceptAnyProxy=true` does not mint valid CAS tickets or bypass TLS/target-service validation by itself.** Its primary damage is removing a **critical control layer at the target service**: verifying proxy identity and history. Other checks may still block some paths, yet the **security posture is substantially weakened**.

### 5.1. Not Only the Boolean Is Dangerous

Other misconfigurations effectively create “accept any” behavior:

- `allowedProxyChains` containing the regex `^https://.*`.
- A regex matching `gateway` anywhere in the URL regardless of host or suffix.
- Checking `chain.contains(trustedProxy)` instead of exact full-chain matching.
- Inspecting only the first hop and ignoring the rest.
- Using `startsWith("https://gateway.example.test")`, letting `gateway.example.test.evil.test` slip through without strict URI parsing.
- Dynamically appending every proxy seen in CAS responses to the allowlist.
- Setting `acceptAnyProxy=false` while another code path instantiates a permissive validator/proxy decider or caches results from an old config.
- The CAS server registry issuing PGTs to every service or every `pgtUrl`, broadening PT issuance sources.

A secure policy must be enforced **on both the backend and the CAS Server**.

## 6. First Pick the Right Mode: Do Not Support Proxying If Unneeded

If an application only authenticates users via browser CAS STs:

~~~text
Browser -> /login/cas?ticket=ST-...
App -> CAS /serviceValidate
App -> SecurityContext/HttpSession
~~~

Prefer:

- Using `Cas20ServiceTicketValidator` or a Service Ticket validator that rejects Proxy Tickets per protocol.
- Processing artifacts only at `CasAuthenticationFilter.filterProcessesUrl`, typically `/login/cas`.
- Keeping `ServiceProperties.authenticateAllArtifacts=false` unless CAS PTs are needed across URLs.
- Omitting `pgtUrl`, proxy receptor, and PGT stores when there is no downstream CAS use case.
- Ensuring the CAS Server **does not issue PGTs** to this service via registered-service proxy policy.
- Never using `/proxyValidate` instead of `/serviceValidate` just because sample docs highlight more features.

Per the CAS Protocol, `/serviceValidate` **must not accept PTs successfully**. Keeping a backend **incapable of accepting PTs** is usually safer and simpler than accepting PTs while “hoping proxies stay valid.”

### 6.1. Which Mode Truly Needs PTs?

A browserless backend that needs to know which intermediary service delegated the user can use PTs:

~~~text
Portal (holds CAS Authentication) -> CAS /proxy -> PT for Reports
Portal -> Reports (PT)
Reports -> CAS /proxyValidate -> assertion + proxy chain
Reports -> validate chain + permissions -> return data
~~~

This is **delegated authentication**; it does not mean Portal automatically gets access to all user data. The backend still must restrict users, business scopes, resource ownership, and allowed operations.

## 7. Deny-by-Default Policy for a PT-Accepting Backend

A clear policy answers **five independent questions**:

1. **Which CAS Server** does the backend trust, and are its URL and TLS certificate/host verified?
2. **Is the target service** the exact service identity the PT was issued for?
3. **Does the proxy chain** match exact URLs, hop count, and order in the allowlist?
4. **Is the user** from the CAS assertion recognized and permitted by the backend?
5. **Is the business operation/context** permitted for that user via that proxy?

### 7.1. Full Allowlist Example

~~~yaml
# Illustrative domain config; not an automatic Spring Boot property.
cas-proxy-policy:
  reports-api:
    cas-server: "https://sso.example.test/cas"
    target-service: "https://reports.example.test/api/cas"
    allow-direct-service-ticket: false
    accept-any-proxy: false
    allowed-chains:
      - - "https://gateway.example.test/login/cas/proxyreceptor"
      - - "https://gateway.example.test/login/cas/proxyreceptor"
        - "https://portal.example.test/login/cas/proxyreceptor"
    require-https-proxy-callback: true
    reject-unlisted-hops: true
    max-proxy-hops: 2
~~~

**This is an application-specific policy DSL to illustrate the concept, not a built-in Spring Security/Apereo schema.** If a project adopts it, write code translating these lines into chain checks and validator settings. Never drop this YAML into `application.yml` expecting the framework to enforce it automatically.

Important attributes:

- `allowed-chains` is a **list of chains**, not a flat list of “every trusted URL.”
- A two-element chain accepts **only** `[Gateway, Portal]`.
- `max-proxy-hops` is an extra depth guard; it **must never** replace the allowlist.
- Never trust `require-https-proxy-callback=true` unless CAS actually verified the callback's HTTPS identity.
- `allow-direct-service-ticket=false` suits backends admitting delegated PTs only; a backend also accepting direct STs needs an explicit policy for empty chains.

### 7.2. Exact URLs vs. Regular Expressions

Apereo CAS Java Client allows specifying `allowedProxyChains` with exact URLs or certain **regular expression** syntaxes depending on client/version. Whenever possible, prefer **exact URLs**.

If regexes are unavoidable during multi-callback migrations, ensure you:

- Anchor with `^` and `$`, pinning exact hostname, path, and port.
- Escape dots in domain names, e.g., `\.` instead of `.`.
- Avoid broad `.*` patterns or optional `https?` schemes when HTTPS is mandatory.
- Bound input length, proxy hop counts, and catastrophic regex backtracking.
- Write negative tests for hostnames like `gateway.example.test.evil.test` and paths like `/proxyreceptor/extra`.
- Verify the exact `ProxyList` parsing syntax of your **deployed Apereo client version**; never guess that Java regex rules behave identically across all binders.

Example pattern inside **your own policy engine**:

~~~regex
^https://gateway\.example\.test/login/cas/proxyreceptor$
~~~

When only one URL is acceptable, **exact string matching is clearer than regex**. Never strip or normalize scheme, host, port, trailing slash, query, or casing ad-hoc; verify every URL variation against how the CAS registry/callback actually identifies services.

## 8. `Cas20ProxyTicketValidator`: Configuring Exact Chains

In Apereo Java CAS Client, `Cas20ProxyTicketValidator` is constructed with the **CAS server URL prefix** and exposes:

~~~java
Cas20ProxyTicketValidator validator =
    new Cas20ProxyTicketValidator("https://sso.example.test/cas");

validator.setAcceptAnyProxy(false);
validator.setAllowEmptyProxyChain(false);
validator.setAllowedProxyChains(approvedProxyList);
~~~

**This is a non-standalone API snippet**:

- `approvedProxyList` is a **`ProxyList` object built from approved chains** via the API/parser of your specific CAS Java Client version—**not a plain `List<String>`**. In `Cas20ProxyTicketValidator` Javadoc, the setter signature is **`setAllowedProxyChains(ProxyList)`**.
- Verify `ProxyList` imports/packages, construction syntax, and regex parsing against your **actual Apereo Java CAS Client version**.
- `setAllowEmptyProxyChain(false)` fits **backends accepting only PTs with valid proxies**. If business also allows direct STs, design a separate empty-chain policy and test explicitly.
- `setAcceptAnyProxy(false)` **does not generate an allowlist on its own**. Supply a real `approvedProxyList` and test unmatched chains.
- `Cas20ProxyTicketValidator` handles **CAS 2.x proxy validation**; CAS 3 attributes may require `Cas30ProxyTicketValidator`. Avoid mixing endpoints and formats.

Even safer is **not instantiating `Cas20ProxyTicketValidator` at all** on services that never receive proxies, as noted in section 6.

### 8.1. Spring Security `CasAuthenticationProvider`

In Spring Security, `CasAuthenticationProvider` takes the `TicketValidator` you configure. Wiring excerpt (other variables supplied by bean configuration):

~~~java
Cas20ProxyTicketValidator validator =
    new Cas20ProxyTicketValidator("https://sso.example.test/cas");
validator.setAcceptAnyProxy(false);
validator.setAllowEmptyProxyChain(false);
validator.setAllowedProxyChains(approvedProxyList);

CasAuthenticationProvider provider = new CasAuthenticationProvider();
provider.setKey("reports-cas-provider-v1");
provider.setServiceProperties(serviceProperties);
provider.setTicketValidator(validator);
provider.setUserDetailsService(userDetailsService);
~~~

**This is a code sketch for a Spring Boot app, not a standalone runnable Java 17 program.** You need Apereo/Spring Security imports plus `serviceProperties`, `userDetailsService`, and `approvedProxyList` beans. `provider.setKey` is an internal provider identifier, **not a CAS cryptographic key**. Final configuration must be verified via integration tests with a CAS Server.

What to avoid:

~~~java
// Do not use in production:
validator.setAcceptAnyProxy(true);
~~~

Some Spring Security documentation uses this value to **demonstrate enabling proxy support**. It is not a recommended trust policy for applications handling real data.

### 8.2. CAS Java Client Servlet Filters vs. Spring Security Are Two Separate Configuration Paths

A service may use **Apereo Java CAS Client filters directly** or **Spring Security's CAS provider/filter**. With pure Java Client filters, `Cas20ProxyReceivingTicketValidationFilter` accepts init parameters:

~~~xml
<!-- web.xml fragment for APEREO CAS CLIENT FILTER; does not automatically
     apply to Spring Security CasAuthenticationProvider. -->
<filter>
  <filter-name>CAS Validation Filter</filter-name>
  <filter-class>
    org.apereo.cas.client.validation.Cas20ProxyReceivingTicketValidationFilter
  </filter-class>
  <init-param>
    <param-name>casServerUrlPrefix</param-name>
    <param-value>https://sso.example.test/cas</param-value>
  </init-param>
  <init-param>
    <param-name>acceptAnyProxy</param-name>
    <param-value>false</param-value>
  </init-param>
  <init-param>
    <param-name>allowedProxyChains</param-name>
    <param-value>https://gateway.example.test/login/cas/proxyreceptor</param-value>
  </init-param>
</filter>
~~~

This is **only an illustrative configuration fragment**, not a complete `web.xml`. You need `filter-mapping`, exact service URL or `serverName`, auth filters, and testing against your actual CAS Client version. Per Apereo Java CAS Client docs, `allowedProxyChains` as an init-param declares **one chain per line, with URLs in each chain separated by whitespace**. Multi-chain configurations must ensure YAML/XML whitespace normalization does not corrupt parser input.

**Never copy an Apereo Filter alongside Spring Security's `CasAuthenticationFilter` on the same URL**: two layers could read/validate the same PT, consuming the **single-use** ticket before the second layer runs. Stick to one integration path with clear ownership.

### 8.3. Multi-Chain Example in an Admin Config File

~~~text
https://gateway.example.test/login/cas/proxyreceptor
https://gateway.example.test/login/cas/proxyreceptor https://portal.example.test/login/cas/proxyreceptor
~~~

**The first line** permits `[Gateway]`. **The second line** permits `[Gateway, Portal]` in the order returned by CAS. Never read those two lines as “any single matching proxy suffices.” Operators must verify the exact `allowedProxyChains` syntax of their Apereo client version and write integration tests loading real config, because XML binders, Servlet init-params, and Java setters **do not take identical types**.

## 9. CAS Server Service Registry: Blocking at the PGT Issuance Source

Checking the chain solely at Reports is insufficient. The CAS Server needs policies defining **who is allowed to act as a proxy**.

Apereo CAS provides **registered service proxy policies**. CAS documentation notes that **services are denied proxying by default**, offering policies like `RefuseRegisteredServiceProxyPolicy` alongside policies permitting callback URLs via restricted patterns.

Policy orientation example:

~~~text
CAS registered service Portal:
  serviceId = https://portal.example.test/login/cas
  proxyPolicy = allow PGT only for
    https://portal.example.test/login/cas/proxyreceptor

CAS registered service Gateway:
  serviceId = https://gateway.example.test/login/cas
  proxyPolicy = allow PGT only for
    https://gateway.example.test/login/cas/proxyreceptor

CAS registered service Unknown:
  proxyPolicy = refuse / no PGT issuance

CAS target Reports:
  targetService = https://reports.example.test/api/cas
  service registry entry approved
  allow PT only from registered actors per applicable policy
~~~

This is a **governance model**, not a complete CAS Server JSON/YAML schema. Every CAS version has its own service registry schema. In real configuration:

1. Verify exact **service IDs** and permitted callback URLs.
2. Enable proxying only for **services with an approved business use case**.
3. Never grant PGT rights if only ST authentication is required.
4. If using callback regexes, tightly restrict scheme, host, path, and escaping.
5. Protect service registry changes with RBAC, code review/audit, and versioning.
6. Never let any service specify an arbitrary internal URL as `pgtUrl` (SSRF risk).
7. Assign an owner and documentation for **each chain permitted by the backend** and its business purpose.

### 9.1. Why Must the Backend Still Validate the Proxy Chain Even When “CAS Issued the PT”?

In CAS proxy, CAS can let a valid service acquire a PGT and mint a PT for a backend. Yet only the backend knows **which intermediary services are authorized to submit that operation**. A CAS federation spanning many apps must never treat every app as **equal in trust and business privilege**.

The **CAS Security Guide** warns that accepting proxy tickets carries the responsibility to validate the proxy chain at the **receiving service**, and configuring `/proxyValidate` without checking chains creates a trust vulnerability. This is a **delegation** concern, not merely token validity.

## 10. PGT Callbacks, TLS, and Proxy Identification

### 10.1. `pgtUrl` Serves as the Proxy's Identity

When Portal wants a PGT, it sends `pgtUrl` during `/serviceValidate` or `/proxyValidate`. The CAS Server opens an HTTPS callback to that URL delivering:

~~~text
pgtIou = PGTIOU-...
pgtId  = PGT-...
~~~

CAS returns `<cas:proxyGrantingTicket>PGTIOU-...</...>` only when the callback mechanism succeeds per protocol/policy. Portal pairs the PGTIOU from the validation response with the PGT received at the callback.

**Failure cases:**

- `pgtUrl` uses HTTP instead of HTTPS.
- Callback certificate is expired or has a hostname mismatch.
- CAS does not trust the callback's CA/certificate chain.
- CAS service registry denies proxy policy.
- Callback endpoint fails to return an accepted status.
- Proxy receptor and validator use **two different PGT stores**, failing IOU correlation.
- Callback hits replica A while validation response is handled on replica B without shared storage.

Never solve these by **disabling TLS peer verification** or enabling `acceptAnyProxy`. These are **PGT issuance/callback** failures, not reasons to lower trust on Reports.

### 10.2. Prevent `pgtUrl` from Becoming SSRF

The CAS Server actively calls `pgtUrl`. Allowing an untrusted service to pass an arbitrary callback URL can enable **server-side request forgery** or force CAS to contact unwanted internal addresses.

Mitigate risk via:

- CAS service registry + proxy policies binding **registered service → specific callback URL**.
- HTTPS only, approved hostnames, and strict certificate/chain/validity verification.
- Restricting redirects and internal/private IP ranges per policy.
- DNS/egress policies and network segmentation.
- Never accepting `pgtUrl` chosen from end-user queries or tenant claims.
- Monitoring callback errors and auditing only necessary metadata.

### 10.3. PGT Is a High-Privilege Secret

A PGT can be used **multiple times to request PTs**, unlike one-time ST/PTs. Therefore:

- Never expose PGTs in URL logs, telemetry, exceptions, CI artifacts, or client-side JavaScript.
- Restrict PGT storage reads strictly to the service identity, with encryption at rest and TTL/cancellation policies.
- Invalidate PGTs per CAS logout policy; if the service caches PGTs separately, ensure cleanup.
- Isolate PGTs by user/session and CAS issuer/service.
- Never share one PGT across multiple tenants unless contracted and isolated.
- Treat suspected PGT compromise as a full credential compromise incident, not merely deleting one used PT.

## 11. Target Service: A Binding Layer Independent of the Chain

CAS issues a PT **for the exact `targetService` specified** at `/proxy`:

~~~text
GET /cas/proxy?pgt=PGT-opaque
    &targetService=https%3A%2F%2Freports.example.test%2Fapi%2Fcas
~~~

When Reports validates:

~~~text
GET /cas/proxyValidate?ticket=PT-opaque
    &service=https%3A%2F%2Freports.example.test%2Fapi%2Fcas
~~~

`targetService` at PT issuance and `service` at validation must match per CAS Protocol/service matching policy. A PT issued for `https://inventory.example.test/api/cas` **never becomes valid for Reports** simply because the user and proxy chain match.

**Note:** a valid proxy chain **does not make a PT valid for every backend**. Operators must separate:

- Trusted CAS Server URL.
- CAS-registered target service ID.
- That backend's proxy chain allowlist.
- Authorization policy for specific resources/actions.
- True service path behind reverse proxies, never letting untrusted `Host` or `X-Forwarded-*` headers dictate service identity.

If a backend validates one shared service URL across many API endpoints, it still must check **per-endpoint/per-resource permissions** post-authentication; a valid PT for the gateway root must never authorize arbitrary admin actions.

## 12. CAS Proxy in Spring Security: Stateless Mode and Caching Risks

Per Spring Security guidance, when a service accepts proxy tickets outside the `filterProcessesUrl` callback, it may need:

- `ServiceProperties.authenticateAllArtifacts=true` if intentionally processing artifacts across multiple URLs.
- `ServiceAuthenticationDetailsSource` to construct the **service URL from the HTTP request** matching the PT target.
- `CasAuthenticationFilter` receiving tickets and creating the right authentication token (modern Spring Security uses `CasServiceTicketAuthenticationToken`).
- `CasAuthenticationProvider` using `Cas20ProxyTicketValidator` (or CAS 3 equivalent) with chain allowlists.
- `StatelessTicketCache` (when adopting this architecture) to retrieve previously validated `Authentication` objects by ticket on repeat calls.

**Never enable `authenticateAllArtifacts` when only browser ST login is required.** Enabling it across an entire filter chain makes every endpoint accept a `ticket` parameter, creating unnecessary attack surface.

### 12.1. Using Caches Requires Explicit Security Semantics

The CAS Protocol states **a PT is for one validation attempt**, yet Spring Security describes `StatelessTicketCache` where an `Authentication` is cached keyed by PT so a remoting client can **resend the same PT** without re-calling CAS. This is an **application-layer trust extension** affecting credential lifetimes.

Required policies:

- Cache only `Authentication` objects that **passed both CAS validation and the proxy-chain allowlist**.
- Enforce a **short TTL, size limit, and eviction**, never longer than security policy permits.
- If allowlists or tenant authorizations change, **invalidate or version the cache** so stale entries cannot bypass new policies.
- If CAS logout or PGT revocation occurs, account for **session invalidation/cached token lifetimes** rather than assuming the cache instantly learns of CAS logout.
- Scope cache keys by CAS server/service/tenant when multiple issuers exist; never collide identical ticket strings across namespaces.
- Prohibit long-lived bearer-style PTs in URLs, logs, or access traces.
- Consider **disabling caching entirely** if protocol or security policy forbids application-layer token reuse.

If the system needs a multi-use API token, evaluate a **dedicated token mechanism** rather than stretching short-lived CAS tickets into long-lived API credentials.

### 12.2. Distinguish Caches from Ticket Registries

- **CAS Server ticket registry** tracks whether ST/PTs are still valid or consumed.
- **Spring `StatelessTicketCache`** caches `Authentication` after initial validation on the PT-receiving service.
- **PGT storage** holds PGTs so a service can mint new PTs.
- **`HttpSession`/`SecurityContextRepository`** holds a browser's local `Authentication`.

These are **four separate types of state**. Never fix `INVALID_TICKET` errors by opening an unbounded cache or treating a PGT like a password.

## 13. Multi-Tenant, Multiple CAS Servers, and Trust Boundaries

A backend may serve partners A and B, each with its own CAS Server or sharing one CAS Server with distinct proxy services.

Recommended model:

~~~text
Partner A:
  CAS issuer/base: https://cas-a.example.test/cas
  backend service: https://api.example.test/a/cas
  chains:
    [https://gateway-a.example.test/cas/pgtCallback]

Partner B:
  CAS issuer/base: https://cas-b.example.test/cas
  backend service: https://api.example.test/b/cas
  chains:
    [https://gateway-b.example.test/cas/pgtCallback]
~~~

**Never validate Partner B's PT with CAS Server A**, never apply A's chain allowlist to B, and never guess the trusted CAS provider from a username or email. Provider selection and service identity must come from governed configuration/routing and be re-verified after validation.

When a backend has one CAS issuer serving multiple tenants:

- Proxy callback URLs may be shared if organizationally approved, yet **tenant context** and **business permissions** must still be checked independently.
- Never derive tenant from a query parameter or an uncontracted CAS attribute.
- Partition caches by service/tenant/policy version when stateful caching is enabled.
- Changes to shared proxies can affect multiple tenants; manage blast radius and rotations carefully.

### 13.1. A Valid Proxy Chain Alone Is Insufficient for Authorization

For instance, Gateway may be allowed to call Reports, yet only as a user belonging to the Reports Reader group. A validated PT with trusted chain `[Gateway, Portal]` must still deny `DELETE /reports/finance` if local authorization forbids it.

Safeguards:

1. Ticket result from a **trusted CAS Server**.
2. Exact target service.
3. Approved full proxy chain.
4. Local principal exists, is enabled, and is scoped to the CAS provider/tenant.
5. User has permissions for the exact resource/action.
6. Where needed, differentiate **delegation levels**: one proxy may only read, another may write.
7. Audit user + proxy chain + action + decision, **without logging raw tickets**.

## 14. Standalone Java 17: Validating the Full Proxy Chain Against an Allowlist

The following program **compiles and runs on JDK 17+ without Spring Security or a CAS Server**. This model allows two chains:

- **`[Gateway]`** — one proxy hop.
- **`[Gateway, Portal]`** — two proxy hops, with Gateway closest per CAS response rules.

The program demonstrates:

- Rejecting **empty chains** on a backend restricted to delegated PTs.
- Rejecting **unknown proxies**, reversed order, and extra hops.
- Rejecting wrong target services, HTTPS downgraded to HTTP, trailing-suffix URLs, or missing usernames.
- Accepting only inputs confirmed by a **real CAS `TicketValidator`**.

**Strict limitations:** `VerifiedCasAssertion` is a **data model simulating trusted output**. The boolean `validatedByTrustedCas` **must never come from JSON, headers, query params, or the client**. In production, only the output of `TicketValidator` after connecting to the CAS Server over **HTTPS with TLS validation**, parsing the CAS protocol, and checking ticket, service, and proxy chain may enter business policy evaluation. This Java code **validates no real tickets, makes no CAS calls, parses no XML, and provides no HTTP security or PGT storage**.

File `CasProxyChainPolicyDemo.java`:

~~~java
import java.util.List;
import java.util.Set;

public class CasProxyChainPolicyDemo {
    static final String TARGET = "https://reports.example.test/api/cas";
    static final String GATEWAY =
        "https://gateway.example.test/login/cas/proxyreceptor";
    static final String PORTAL =
        "https://portal.example.test/login/cas/proxyreceptor";
    static final String ATTACKER =
        "https://evil.example.test/login/cas/proxyreceptor";

    // Represents a result already checked by the real CAS TicketValidator.
    record VerifiedCasAssertion(boolean validatedByTrustedCas,
                                String service, String username,
                                List<String> proxies) {}

    static final class StrictPolicy {
        // CAS lists the most recently traversed proxy first.
        private final Set<List<String>> approvedChains = Set.of(
            List.of(GATEWAY), List.of(GATEWAY, PORTAL));

        boolean accept(VerifiedCasAssertion result) {
            if (result == null || !result.validatedByTrustedCas())
                return false;
            if (!TARGET.equals(result.service()))
                return false;
            if (result.username() == null || result.username().isBlank())
                return false;
            return approvedChains.contains(result.proxies());
        }
    }

    static VerifiedCasAssertion result(boolean verified,
                                       String service, List<String> chain) {
        return new VerifiedCasAssertion(verified, service, "u-42", chain);
    }

    public static void main(String[] args) {
        StrictPolicy p = new StrictPolicy();
        System.out.println("approvedOneHop=" +
            p.accept(result(true, TARGET, List.of(GATEWAY))));
        System.out.println("approvedTwoHops=" +
            p.accept(result(true, TARGET, List.of(GATEWAY, PORTAL))));
        System.out.println("directTicketDenied=" +
            !p.accept(result(true, TARGET, List.of())));
        System.out.println("unknownProxyDenied=" +
            !p.accept(result(true, TARGET, List.of(ATTACKER))));
        System.out.println("reorderedChainDenied=" +
            !p.accept(result(true, TARGET, List.of(PORTAL, GATEWAY))));
        System.out.println("extraHopDenied=" +
            !p.accept(result(true, TARGET,
                List.of(GATEWAY, PORTAL, ATTACKER))));
        System.out.println("untrustedResultDenied=" +
            !p.accept(result(false, TARGET, List.of(GATEWAY))));
        System.out.println("wrongServiceDenied=" +
            !p.accept(result(true, "https://other.example.test/api/cas",
                List.of(GATEWAY))));
        System.out.println("prefixTrickDenied=" +
            !p.accept(result(true, TARGET,
                List.of(GATEWAY + ".evil.example.test"))));
        System.out.println("httpDowngradeDenied=" +
            !p.accept(result(true, TARGET,
                List.of(GATEWAY.replace("https:", "http:")))));
        System.out.println("trailingSlashDenied=" +
            !p.accept(result(true, TARGET, List.of(GATEWAY + "/"))));
        System.out.println("missingUserDenied=" +
            !p.accept(new VerifiedCasAssertion(true, TARGET, "",
                List.of(GATEWAY))));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 CasProxyChainPolicyDemo.java
java CasProxyChainPolicyDemo
~~~

**Exact stdout:**

~~~text
approvedOneHop=true
approvedTwoHops=true
directTicketDenied=true
unknownProxyDenied=true
reorderedChainDenied=true
extraHopDenied=true
untrustedResultDenied=true
wrongServiceDenied=true
prefixTrickDenied=true
httpDowngradeDenied=true
trailingSlashDenied=true
missingUserDenied=true
~~~

In the `...Denied=true` lines, negation confirms **the policy rejected the input as expected**. `approvedOneHop=true` and `approvedTwoHops=true` confirm the two intact approved chains are accepted.

**Intentional lesson limitations:** `Set<List<String>>.contains` performs exact full-chain matching, yet it **does not handle** CAS proxy trust bootstrapping, URI canonicalization, certificate trust, service registries, revocation, or authorization. In production, rely on **CAS Java Client's validated assertion** and the validator's allowlist config; if adding extra business-layer checks, never use them to replace `Cas20ProxyTicketValidator`.

## 15. Attacks and Misconfigurations to Test Proactively

| Scenario | Input or Change | Required Outcome |
| --- | --- | --- |
| Valid single hop | `[Gateway]` with PT for Reports | PASS if identity and authorization pass |
| Valid two hops | `[Gateway, Portal]` | PASS if listed in policy |
| Direct ST to PT-only backend | `cas:proxies=[]` | FAIL unless explicit direct policy exists |
| Unregistered proxy | `[Unknown]` | FAIL |
| Swapped order | `[Portal, Gateway]` | FAIL |
| Extra hop at front | `[Attacker, Gateway, Portal]` | FAIL |
| Extra hop at end | `[Gateway, Portal, Attacker]` | FAIL |
| Chain contains only one allowlisted proxy | `[Gateway, Unknown]` | FAIL |
| Dangerous substring match | Unknown URL containing `gateway.example.test` | FAIL |
| Spoofed hostname prefix | `gateway.example.test.evil.test` | FAIL |
| HTTP downgrade | `http://gateway...` instead of HTTPS | FAIL |
| Trailing slash mismatch | `.../proxyreceptor/` | FAIL per exact policy |
| Lookalike path | `.../proxyreceptor-admin` | FAIL |
| Different port | `https://gateway...:8443/...` | FAIL if unregistered |
| Overly broad regex | `^https://.*` | Config QA FAIL; block from production |
| URL regex missing end anchor | Pattern matches prefix and admits suffixes | FAIL negative tests |
| Spoofed CAS validation endpoint | MITM/DNS/hostname mismatch | FAIL TLS; create no `Authentication` |
| Browser fakes `X-Proxy-Chain` | Header asserting a valid chain | Never treat as CAS assertion |
| Forged CAS response XML | HTTP client sends `cas:proxies` | Never parse as trusted outside `TicketValidator` |
| PT for another service | `targetService=Inventory`, backend=Reports | FAIL at CAS validation |
| Used PT | Same PT submitted twice | CAS rejects unless app caches; verify cache policy |
| Expired PT | Validation after TTL | FAIL |
| Leaked PGT | Actor tries requesting another PT from PGT | Incident response; revoke/protect PGT |
| HTTP PGT callback | `pgtUrl=http://...` | CAS rejects per protocol/policy |
| Expired PGT callback cert | TLS trust fails | No PGT issued |
| PGT callback to unknown internal host | `pgtUrl` targets unapproved IP/host | CAS blocks via policy/SSRF controls |
| PGTIOU mismatch | Callback and validation response do not match | Do not use PGT |
| Cluster loses PGT | Callback hits node A, app node B misses IOU | Fail closed; fix shared storage/affinity |
| Widened CAS service policy | Unknown service granted PGT | Caught by config review/tests |
| `acceptAnyProxy=true` | Enabled on Reports backend | Deployment gate FAIL |
| Unnecessary `authenticateAllArtifacts=true` | PT accepted across every endpoint | Restrict filter processing/URLs |
| Cache keeps auth after policy change | Old valid PT reused from cache | Evict/version cache; never bypass new policy |
| Cross-tenant cache collision | Ticket cache shares namespaces | Separate by issuer/service/tenant |
| Tenant A proxies to B | Valid CAS issuer, yet chain belongs to A | FAIL unless allowlisted by B |
| Locally disabled user | CAS succeeds, app user locked | FAIL authorization |
| Insufficient privileges | Valid proxy chain, user lacks write permission | HTTP 403; grant no access |
| CAS logout | PGT/TGT invalidated while cache remains | Test app cache revocation/TTL |

**You do not need real production tickets to test invalid chains.** Use a dedicated CAS test server/service registry, dummy users, and API-verified integration mocks. For tests involving real ticket codes, log only hashed correlation IDs or redact them.

## 16. Threat Model: What Happens If You Trust Every Proxy?

### 16.1. Unexpected Service Acts as a Proxy

If Reports accepts any proxy, a third internal service that CAS happens to grant a PGT to can request a PT on a user's behalf (within CAS service/target policies). Reports sees a valid CAS ticket and **falsely assumes the delegating source is authorized**.

Possible consequences:
- Bypassing restrictions limiting delegated access exclusively to Portal/Gateway.
- Abusing user permissions on backends outside the reviewed workflow.
- Audits show only the username without clarity on which intermediary was trusted to initiate it.
- Difficulty revoking a single misbehaving proxy after an incident.

### 16.2. Host Spoofing and “Wildcard to Fix Bugs”

If service URLs or callback URLs are derived dynamically from `Host`/`X-Forwarded-Host`, an attacker can forge URLs that misidentify services. Combined with an overly broad allowlist regex, PTs can traverse unapproved paths.

Remediate with **fixed public URLs**, trusted reverse proxies, exact service registrations, and negative tests on host/path/port. Never use `acceptAnyProxy=true` as a “quick fix” for hostname errors.

### 16.3. Forged Proxy Chain via HTTP Headers

An app might receive:

~~~text
X-Proxy-Chain: https://gateway.example.test/login/cas/proxyreceptor
~~~

**Never use that header as a CAS proxy chain.** Use solely `<cas:proxies>` returned by the CAS `TicketValidator` after ticket verification. Infrastructure HTTP proxy headers do not carry CAS delegation semantics.

### 16.4. Abused as a Proxy to Sensitive Backends

Portal may hold a valid PGT yet must never accept an arbitrary `targetService` from a browser-supplied `targetUrl` parameter. Portal must enforce a **backend allowlist**, preventing users from converting a PGT into PTs targeting other sensitive apps.

Controls should span all layers:

- CAS registered proxy policy (who may obtain a PGT).
- Proxy app `targetService` allowlist (which backends may be called).
- Reports backend chain allowlist (which proxies are trusted).
- API authorization (which user may do what).
- Network egress/SSRF protection and secrets management.

## 17. Error-Specific Troubleshooting

| Symptom | Possible Cause | Safe Investigation |
| --- | --- | --- |
| Browser ST login works, yet PGT fails | CAS service `proxyPolicy` denies it | Check service/callback registry; never allow all proxies |
| Missing `pgtIou` | Callback TLS/HTTP status error or CAS denied PGT | Inspect redacted CAS callback logs/truststore |
| PGTIOU present, PGT not found | Mismatched receptor/validator storage, cache TTL, load balancer | Check shared `ProxyGrantingTicketStorage` and correlation |
| PT request returns error | Expired/revoked PGT or disallowed `targetService` | Check CAS `/proxy` response and proxy policy |
| `INVALID_SERVICE` on PT validation | `targetService` differs from backend's `service` URL | Compare exact scheme/host/path/port and proxy config |
| `INVALID_TICKET` | PT expired, consumed, malformed, or wrong CAS server | Request fresh PT; check ticket registry |
| Validation passes yet proxy chain rejected | Hop URL missing from allowlist or wrong order | Inspect validated `cas:proxies` list, redacted |
| Empty chain rejected | Backend PT-only policy disallows direct STs | Check ST vs. PT profile; never open unconditionally |
| Hop order mismatch | Operator wrote `[Portal, Gateway]` while CAS returns `[Gateway, Portal]` | Check protocol; update allowlist via review |
| New intermediary proxy inserted | Service delegation architecture changed | Check onboarding approval; add exact chain |
| Fails only on proxy callback HTTPS | Certificate trust/hostname/CA chain issue | Fix certificate/truststore; never disable TLS |
| Fails only in prod behind ingress | Public URL vs. callback path/host mismatch | Check trusted Forwarded headers and CAS registry |
| CAS 2 validator misses CAS3 attributes | Wrong endpoint/profile used | Choose CAS 3 validator matching version |
| `ClassCastException` / API mismatch | Incompatible Apereo client / Spring Security versions | Check dependency graph and real Javadoc |
| Reloaded allowlist still accepts old chain | Validator/cache not reloaded or stale cached auth | Rolling restart; version/evict cache |
| Stateful ST works, stateless PT fails | `authenticateAllArtifacts`/details source/provider miswired | Check filter chain and service URL |
| PT succeeds yet API returns 403 | Local user locked or insufficient role policy | Check application authorization; never open proxies |
| PT appears in access logs | Logger/proxy logs full query string | Redact `ticket`; run secret exposure response |
| CAS Service gets PGT unintentionally | Overly broad CAS registry regex | Narrow proxy policy; audit all services |
| Fails only on cluster | PGT/PGTIOU/session/cached auth out of sync | Shared storage or partition-aware design |

### 17.1. Safe Logging

~~~text
event=CAS_PROXY_CHAIN_REJECTED
casServer=https://sso.example.test/cas
targetService=https://reports.example.test/api/cas
chain=[gateway,unknown]            # normalized internal labels
reason=UNAPPROVED_PROXY_CHAIN
policyVersion=reports-proxy-v8
requestId=trace-7f4e
~~~

**Never log raw `PT-...`, `PGT-...`, `PGTIOU-...`, full CAS XML, browser cookies, or sensitive user attributes.** CAS proxy callback URLs themselves are not secrets like PGTs, yet should still be logged per policy.

## 18. Step-by-Step Secure Implementation Workflow

1. **Inventory use cases:** which backends truly need PTs? If none, stay ST-only and grant no PGTs.
2. **Inventory CAS services:** what are the service IDs and callback URLs for Portal, Gateway, and Reports?
3. **Design trust chains:** specify **exact proxy hop lists in CAS return order**, tying each chain to an owner and change ticket.
4. **Lock down CAS service registry:** which services get PGTs, which callback URLs are allowed, and which target services are permitted.
5. **Lock down network/TLS:** CAS validation endpoints and PGT callbacks must use HTTPS with verified certificates/hostnames.
6. **Configure backend:** `acceptAnyProxy=false`, explicit `allowedProxyChains`, and `allowEmptyProxyChain=false` if PT-only.
7. **Pick the right validator:** `Cas20ProxyTicketValidator` or CAS 3 equivalent matching server; never use `Cas20ServiceTicketValidator` for PTs or enable a proxy validator on ST-only services.
8. **Configure Spring filter chain:** for stateless PTs, scope endpoints, `ServiceAuthenticationDetailsSource`, and `authenticateAllArtifacts` strictly where needed.
9. **Configure PGT storage:** secure, TTL, cleanup, shared across receptor and validator, working under load balancing.
10. **Enforce local authorization:** user/tenant/role/target operation; a valid chain never grants business permissions automatically.
11. **Test happy paths:** direct ST-only, one hop, approved two hops, exact callbacks and target services.
12. **Test negative matrix:** unknown/reordered/extra/empty chains, service mismatches, PGT callback TLS failures, PGTIOU mismatches, and ticket replays.
13. **Load test and cache policy:** verify TTLs, capacity, revocation, locked users, config reloads, and CAS logout behavior.
14. **Monitor production:** proxy-chain rejections, registry changes, PT/PGT issuance, callback errors, and anomalies.
15. **Rollback:** if a newly approved chain breaks, restore prior config/routing; **never roll back by enabling `acceptAnyProxy`**.

## 19. Code Review and QA Checklist

- [ ] CAS Proxy enabled solely for backends genuinely needing delegation; ST-only services do not use `/proxyValidate`.
- [ ] `Cas20ProxyTicketValidator.setAcceptAnyProxy(false)` set explicitly; no `acceptAnyProxy=true` in any production environment.
- [ ] `allowedProxyChains` lists exact **full chains**, not “contains at least one trusted proxy.”
- [ ] Verifies **most-recent-first ordering**, matching CAS `<cas:proxies>`.
- [ ] Blocks unknown proxies at front, middle, or end; rejects chains exceeding approved hop counts.
- [ ] Exact URL matching for callback URLs; if regexes are used, anchors `^...$` and tests spoofed hosts/paths/ports.
- [ ] If PT-only, empty chains are rejected; if direct STs are also allowed, a separate policy governs them.
- [ ] CAS validation endpoint points to a fixed/trusted server with TLS/hostname verification enabled.
- [ ] CAS response proxy lists originate from a verified **`TicketValidator`**, never headers/queries/client XML.
- [ ] `targetService` at `/proxy` matches `service` at `/proxyValidate` and CAS registered target.
- [ ] CAS registered services grant PGTs only to authorized Portal/Gateway actors; proxy policy defaults to deny.
- [ ] `pgtUrl` is a CAS-permitted HTTPS callback with peer certificate verification.
- [ ] CAS Server prevents SSRF/redirects on `pgtUrl`, never contacting arbitrary user-chosen hosts.
- [ ] PGT, PGTIOU, and PT are never logged; PGT storage enforces least-privilege access and cleanup.
- [ ] CAS 2 vs. CAS 3 validation endpoints/validators are tested against the live server version.
- [ ] Apereo Java CAS Client and Spring Security versions are compatible; `ProxyList` setter behavior is verified.
- [ ] Never register two overlapping CAS filters on the same endpoint to avoid double-consuming ST/PTs.
- [ ] For stateless PTs, `authenticateAllArtifacts` is enabled only alongside proper service URL details.
- [ ] `StatelessTicketCache`, if used, enforces TTL/size/policy invalidation without arbitrarily extending credential lifetimes.
- [ ] Single-use CAS PTs are never treated as infinitely reusable API tokens in Spring.
- [ ] Multi-tenant deployments isolate CAS issuers, services, proxy chains, caches, and user scopes.
- [ ] Valid CAS ticket + valid proxy still passes through local role/resource authorization.
- [ ] Tests cover chain order, unknown hops, extra hops, direct ST, wrong targets, ticket replay, PGT callback TLS, and proxy policies.
- [ ] Onboarding new proxies requires approval and rolled-out/versioned allowlists rather than wildcards.
- [ ] Logs include `policyVersion`, `service`, and `reason` without recording raw tickets.

## 20. Self-Check Questions

**1. Why can a valid CAS Proxy Ticket still be rejected by a backend?**

Because even though CAS confirmed the ticket is valid, the backend must **verify the proxy chain** against its authorized delegators list. A valid ticket **does not prove every proxy is permitted to call the backend**.

**2. What does `acceptAnyProxy=true` change?**

It lets the validator accept broader proxy chains, bypassing allowlist control over delegators. It **does not mint valid CAS tickets or bypass target-service validation**, yet it removes a critical defense layer.

**3. In what order does CAS return the proxy chain?**

**Most recently traversed proxy first.** For Portal → Gateway → Reports, the backend receives **`[Gateway, Portal]`**, not `[Portal, Gateway]`.

**4. Is checking `chain.contains("Portal")` enough?**

No. `[Attacker, Portal]` also contains Portal while including an unauthorized hop. You must validate the **entire chain and its exact order**.

**5. Is `allowedProxyChains` in Apereo Java CAS Client just an arbitrary Java `List<String>`?**

Do not assume so. `Cas20ProxyTicketValidator.setAllowedProxyChains` takes **`ProxyList`** in Javadoc; the filter init-param takes a string formatted with one chain per line. Use the library's exact binder/parser.

**6. If a backend does not need to accept proxy tickets, what is the safest configuration?**

Use **service ticket validation** and disable proxying—do not accept PTs, do not request PGTs, and do not enable `authenticateAllArtifacts` unnecessarily.

**7. What is `pgtUrl` used for and how does it relate to the proxy chain?**

It is the **HTTPS callback CAS uses to verify the identity of a service requesting a PGT**, and that URL identifies the intermediary service inside the proxy chain. It is neither a network header nor an arbitrary user-supplied endpoint.

**8. Is `PGTIOU` a PGT usable for calling `/proxy`?**

No. PGTIOU is used to **correlate the PGT** arriving via callback with the ticket validation response; `/proxy` requires the issued **real PGT**.

**9. Can a Proxy Ticket be used multiple times at CAS?**

No. The CAS Protocol specifies a PT is for a single validation attempt. Spring's `StatelessTicketCache` can reuse an authenticated result inside the app, which is an **application-level caching decision with trade-offs**, not CAS allowing multi-use PTs.

**10. Does `/serviceValidate` accept Proxy Tickets?**

Per the CAS Protocol, **no**. `/proxyValidate` validates both STs and PTs, yet backends using it must **validate the proxy chain**.

**11. Why must arbitrary `pgtUrl` values be blocked on the CAS Server?**

CAS actively makes HTTPS callbacks to `pgtUrl`. Letting services supply arbitrary URLs leads to **SSRF** or delivering PGTs to unauthorized endpoints.

**12. If the proxy chain is valid, does that automatically grant permission to read all reports?**

No. The backend still must verify **subject, tenant, local authorities, and resource permissions**. Delegated authentication never implies business authorization.

**13. When migrating a callback URL from `/pgtCallback` to `/proxyreceptor`, what must change?**

Update the CAS proxy policy/registry, backend allowed proxy chains, TLS/certificate/callback config, integration tests, and roll out with overlap if protocol/policy permits. Never open wildcards to ease migration.

**14. Why not share one CAS issuer and allowlist across all tenants?**

Different tenants may have distinct proxies, callbacks, and business permissions; unscoped shared trust could let tenant A's proxy reach tenant B. Map issuer/service/chain/tenant explicitly.

**15. Is HTTPS on the PGT callback sufficient to trust a proxy?**

No. CAS must verify the peer certificate and registry proxy policy; the backend still must **inspect the CAS-provided chain** to confirm that intermediary is permitted to delegate.

## 21. Official References

- Spring Security, **CAS Authentication** — `Cas20ServiceTicketValidator`, `Cas20ProxyTicketValidator`, proxy ticket authentication, `ServiceAuthenticationDetailsSource`, `StatelessTicketCache`, and permissive config illustrations: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security Javadoc, **CasAuthenticationFilter**, processing service/proxy tickets, `authenticateAllArtifacts`, and stateless tokens: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html
- Spring Security Javadoc, **CasAuthenticationProvider**, ticket validator/service integration: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
- Apereo CAS, **CAS Protocol Specification**, `/serviceValidate`, `/proxyValidate`, `/proxy`, PGT callbacks, `<cas:proxies>`, chain ordering, and single-use tickets: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- Apereo CAS, **CAS Security Guide**, responsibility for validating proxy chains and warning against accepting PTs without chain checks: https://apereo.github.io/cas/development/planning/Security-Guide.html
- Apereo CAS, **Configuring Service Proxy Policy**, deny-by-default proxying and policy-governed callbacks: https://apereo.github.io/cas/8.0.x/services/Configuring-Service-Proxy-Policy.html
- Apereo CAS, **Proxy Authentication**, ST → PGT → PT → backend flow and callback TLS: https://apereo.github.io/cas/7.3.x/authentication/Configuring-Proxy-Authentication.html
- Apereo Java CAS Client, **README**, `acceptAnyProxy=false` default, URL/regex `allowedProxyChains`, and filter init-params: https://github.com/apereo/java-cas-client/blob/master/README.md
- CAS Client Javadoc (Jasig 3.6.4 branch), **Cas20ProxyTicketValidator**, `setAllowedProxyChains(ProxyList)` and `setAllowEmptyProxyChain(boolean)` setters (verify against installed version): https://javadoc.io/static/org.jasig.cas.client/cas-client-core/3.6.4/org/jasig/cas/client/validation/Cas20ProxyTicketValidator.html

**Remember:** **Never enable `acceptAnyProxy=true` just to make proxy login work.** If only browser CAS login is needed, **do not accept Proxy Tickets**. If PTs must be accepted, validate them with a **trusted CAS Server** and **exact `targetService`**, then require the **full proxy chain to match your allowlist in CAS order**; issue PGTs at CAS solely to approved proxy services/callbacks, protect PGTs, and continue enforcing **business authorization**. That is how you restrict trusted proxies without sacrificing the benefits of CAS federation.
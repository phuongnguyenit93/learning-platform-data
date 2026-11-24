# Validating Proxy Tickets and Inspecting the Entire Proxy Chain in CAS

## 1. Why Must You Validate Both the Proxy Ticket and the Proxy Chain?

In **Central Authentication Service (CAS)**, a frontend application (proxy A) may need to call a backend application (service B) **on behalf of the user**. CAS supports this via **Proxy-Granting Tickets (PGT)** and **Proxy Tickets (PT)**.

For backend B, the security question is not merely “was the ticket issued by CAS and is it still valid?”—it is also:

- Was the ticket issued specifically for **service B** or for a different service?
- Did the trusted CAS server **actually validate the ticket via /proxyValidate**?
- Who is the identified user, and do they hold an active application account and permissions?
- Which **proxies, and in what order**, did the ticket traverse?
- Is **every proxy in the entire chain** approved by B for this operation?
- Was an unknown proxy inserted, a hop skipped, the order altered, or an unauthorized service substituted?
- Are the HTTPS channel, single-use ticket semantics, caching, and **PGT** secrets properly protected?

**Core principle:** **CAS protocol validation** and **proxy-chain authorization** are two sequential checks. B must have the **configured trusted CAS server validate the PT** for the exact target service, and then **reject any proxy chain not explicitly permitted by B's approved policy**. Merely seeing a `PT-` prefix, a username, or one valid proxy element is **insufficient**.

This lesson focuses on **CAS native proxy authentication** in the **Spring Security - federation / CAS Proxy** module. It is **distinct** from SAML2 Assertions, OAuth2 delegation, and OIDC ID Tokens. Examples prefer **Java 17**, Spring Boot **3.3.5**, and Spring Security **6.x** when illustrating Spring configuration. The `example.org` domain, tickets, users, and proxies are all mock data.

### Learning Outcomes

1. Distinguish **ST, PGT, PGTIOU, PT** and the roles of **/serviceValidate, /proxy, /proxyValidate**.
2. Explain **HTTPS proxy callbacks (pgtUrl)**, endpoint verification, and correlating PGTIOU with PGT.
3. Understand how **`cas:proxies`** represents proxy history and why **the proxy closest to the backend appears first**.
4. Design **full-chain allowlists** using exact callback URLs in exact order, rejecting unknown proxies.
5. Configure **`Cas20ProxyTicketValidator`** restrictively rather than unconditionally setting **`acceptAnyProxy=true`**.
6. Distinguish **Spring Security CAS stateless ticket caching** from single-use CAS ticket validation at the server.
7. Run a Java 17 example producing exact ALLOW/DENY outcomes for valid chains, reversed order, missing/extra hops, and wrong services.
8. Test real PTs against a CAS sandbox without leaking raw PTs/PGTs into logs.

## 2. Components of CAS Proxying

| Term | Issued / Held By | Purpose | May It Be Exposed to Browser or Logs? |
| --- | --- | --- | --- |
| **TGC/TGT** | CAS server and CAS browser cookie | Maintains the browser's SSO session with CAS. | Never expose TGC/TGT; not a PT. |
| **ST — Service Ticket** | Issued by CAS to app on browser login | Proves one-time login for the issued **service**; typically via callback. | Travels via browser per protocol, yet remains a sensitive credential. |
| **PGT — Proxy-Granting Ticket** | Issued by CAS over back-channel to proxy-enabled app | Lets the app request **multiple PTs** on behalf of an authentication. | **No**; must be protected as a server-side secret. |
| **PGTIOU — Proxy-Granting Ticket IOU** | Included by CAS in ticket validation response | Correlation key to pair with the PGT delivered via callback. | Never treat PGTIOU as a PGT or credential to call `/proxy`. |
| **PT — Proxy Ticket** | Issued by CAS via **/proxy** when app holds a valid PGT | Authorizes calling a specific **targetService**; backend must validate. | Keep out of logs, query tracking, Referrer; short-lived and single-use. |
| **pgtUrl** | HTTPS URL on intermediary app | Called by CAS to verify/identify proxy and deliver PGT. | Public endpoint requiring TLS, trust, and zero PGT leakage. |
| **cas:proxies** | Returned by CAS in proxy validation response | Ordered list of proxy identities, typically **pgtUrl**. | Used for policy checks after CAS validation succeeds. |

**Do not confuse:** **PGTIOU** only identifies which PGT belongs to which ticket validation. **PGT** is the proxy's credential to request PTs. **PT** is neither a PGT nor a CAS TGT/TGC. Never put a PGT in a query string when calling a backend; a PGT is sent solely from the proxy server to **CAS /proxy**.

## 3. Complete Flow: Browser → Proxy A → Proxy B → Backend C

Suppose user **alice** visits portal A, and portal A must go through proxy B to call API C. C trusts only CAS-validated traffic traversing the **exact sequence A → B → C**.

~~~text
Browser alice               CAS server            Proxy A         Proxy B         Backend C
     |                          |                     |               |                |
     |---- GET A/protected -------------------------->|               |                |
     |<--- redirect CAS /login?service=A ------------|               |                |
     |---- CAS login ---------->|                     |               |                |
     |<--- ST-A + browser redirect                    |               |                |
     |---------------------------- ST-A ------------->|               |                |
     |                          |<-- /serviceValidate(ST-A,service=A,pgtUrl=A/pgt)
     |                          |-- HTTPS GET A/pgt?pgtId=PGT-A&pgtIou=IOU-A ------> A
     |                          |------ validated alice + PGTIOU-A -----> A
     |                          |                     |               |                |
     |                          |<-- /proxy?pgt=PGT-A&targetService=B --- A
     |                          |-------- PT-B ------>|               |                |
     |                          |                     |---- PT-B ---->|                |
     |                          |<----- /proxyValidate(PT-B,service=B,pgtUrl=B/pgt) -- B
     |                          |-- HTTPS callback PGT-B/PGTIOU-B ---> B
     |                          |----- alice, proxies=[A], PGTIOU-B --> B
     |                          |                     |               |                |
     |                          |<---- /proxy?pgt=PGT-B&targetService=C ----- B
     |                          |---------------- PT-C --------------------> B
     |                          |                     |               |--- PT-C ------> C
     |                          |<------------------- /proxyValidate(PT-C,service=C) -- C
     |                          |----- alice, proxies=[B,A] --------------> C
     |                          |                     |               |                |
     |                          |                     |               |         C checks [B,A]
     |                          |                     |               |         and alice's rights
~~~

*This diagram illustrates protocol steps only; connection lines are simplified for readability and are not verbatim HTTP traces.*

**C's decision checkpoints:**

1. **PT-C** presented by B was issued by the **trusted CAS server** for **service C**.
2. C calls **/proxyValidate** with exact **ticket=PT-C** and **service=C**.
3. CAS returns validation success, **cas:user=alice**, and **cas:proxies=[B,A]**.
4. C compares the **entire chain [B,A]** against its allowlist: **B must be the proxy closest to C; A must precede B**.
5. C additionally checks whether **alice is authorized for the API/resource/tenant**.
6. On any mismatch, **create no delegated Authentication and perform no sensitive data access**.

### Must A, B, and C Each Be a Spring App?

No. They can be Spring MVC apps, plain Java services, API gateways, or other CAS-capable applications. What CAS cares about are **service identifiers**, **pgtUrl**, and **ticket validation**. Even if A and B coexist inside one logical application, keep roles, proxy permissions, and callback IDs clearly separated.

## 4. Receiving the PGT Properly: /serviceValidate + pgtUrl + PGTIOU

Before proxy A can request a PT, it must obtain a **PGT** through a CAS-accepted mechanism. For example, A validating an ST:

~~~text
GET https://cas.example.org/cas/serviceValidate
    ?service=https%3A%2F%2Fproxy-a.example.org%2Flogin%2Fcas
    &ticket=ST-EXAMPLE
    &pgtUrl=https%3A%2F%2Fproxy-a.example.org%2Fcas%2FpgtCallback
~~~

This URL is line-wrapped **for readability**, not as a valid raw shell command. The parameters **service, ticket, and pgtUrl** are case-sensitive per the CAS protocol.

CAS performs:

1. Checks that the ST is still valid and **service** matches the original value CAS issued the ticket for.
2. Checks that **pgtUrl is HTTPS**, reachable, and satisfies the CAS server's **TLS certificate/endpoint trust** requirements; never trusts an arbitrary caller-supplied host.
3. CAS invokes A's **pgtUrl**, passing query parameters **pgtId=PGT-A** and **pgtIou=PGTIOU-A**.
4. A stores the PGTIOU→PGT pair **server-side**, never passing the PGT to the browser.
5. If both callback and ticket validation succeed, the XML response includes **cas:proxyGrantingTicket** containing **PGTIOU-A**.
6. A matches the response's IOU against the stored pair before using PGT-A.
7. A can then request PT-B from CAS **/proxy** using PGT-A.

**CAS must authenticate pgtUrl**, not merely check that it returns HTTP 200. The CAS protocol spec mandates HTTPS callbacks with at least PKIX/container trust. An impostor callback URL or untrusted TLS endpoint must not receive a PGT. Exact callbacks/registered services and private keys/certificates must be tightly governed.

**Race condition note:** CAS may issue the callback and return the validation response in an order the system must synchronize. The PGTIOU→PGT store must handle correlation, TTLs, duplicate prevention, and delayed callbacks; if an IOU cannot be matched, **never issue a PT from “the latest PGT.”**

### Example Response with PGTIOU

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxyGrantingTicket>PGTIOU-EXAMPLE</cas:proxyGrantingTicket>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**PGTIOU-EXAMPLE is not the PGT.** The real PGT arrives only at the CAS-verified backend callback. This is sample XML and grants no authentication if copied into an app.

### Acquiring Another PGT When B Must Proxy Onward

When B receives PT-B and calls **/proxyValidate** with **pgtUrl=B/pgtCallback**, CAS can issue PGT-B so B can request PT-C. That forms a **CAS proxy chain**. The CAS server/service registry must authorize B to **proxy** to C; never assume every backend is allowed to proxy onward.

## 5. Requesting a PT via /proxy and Validating via /proxyValidate

A or B sends CAS:

~~~text
GET https://cas.example.org/cas/proxy
    ?pgt=PGT-EXAMPLE
    &targetService=https%3A%2F%2Fapi.example.org%2Fcas%2Freceiver
~~~

CAS checks the PGT, proxy authorization, and **targetService**. On success:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:proxySuccess>
    <cas:proxyTicket>PT-EXAMPLE-ONE-TIME</cas:proxyTicket>
  </cas:proxySuccess>
</cas:serviceResponse>
~~~

The proxying app sends the **PT** (never the PGT) to backend C. C validates:

~~~text
GET https://cas.example.org/cas/proxyValidate
    ?ticket=PT-EXAMPLE-ONE-TIME
    &service=https%3A%2F%2Fapi.example.org%2Fcas%2Freceiver
~~~

Here **service** must match the **`targetService`** CAS used when issuing the PT. **Never use an attacker-controlled URL** as `targetService` or validation `service`; if the backend has multiple CAS-protected endpoints, define each service clearly and enforce target/service registration.

| CAS Endpoint | Responsibility | Accepts PT? |
| --- | --- | --- |
| **/login** | Authenticates browser, issues ST. | Not a ticket validator. |
| **/serviceValidate** | Validates **Service Tickets**; may issue PGT if `pgtUrl` is valid. | **Does not** accept PTs successfully per CAS 2.0 protocol. |
| **/proxy** | Uses PGT to request a PT for `targetService`. | Does not validate PTs; not browser login. |
| **/proxyValidate** | Validates **PT or ST** against `service`; can return proxy chain and PGTIOU. | **Yes**. |
| **/p3/proxyValidate** | CAS 3.0 variant, can include attributes. | Depending on CAS server/client configuration. |

**Never call /serviceValidate on an endpoint permitted to receive PTs and ignore errors**, and never enable **acceptAnyProxy** just to let a mismatched-chain PT pass. CAS 2.0 specifies that both PTs and STs are single-use upon server validation. Spring's **StatelessTicketCache** can cache **validation results** in the app, which is a separate session/cache trade-off and does not make CAS server tickets reusable.

### Rejecting Invalid Tickets

CAS returns **authenticationFailure** with codes like **INVALID_TICKET**, **INVALID_SERVICE**, **INVALID_REQUEST**, **INVALID_TICKET_SPEC**, **UNAUTHORIZED_SERVICE_PROXY**, **INVALID_PROXY_CALLBACK**, or internal errors depending on the server. The backend must:

- Never grant access from username/client-supplied claims when validation fails.
- Never retry the exact same PT as if it were still valid: CAS may have already consumed it.
- Never alter `service` to another URL to force the ticket to “match.”
- Never trust an XML response supplied by the caller; responses must come directly from the CAS endpoint over trusted TLS and a proper HTTP client.

## 6. How to Read the `cas:proxies` Chain Correctly

Example CAS success response returned to backend C:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxies>
      <cas:proxy>https://proxy-b.example.org/cas/pgtCallback</cas:proxy>
      <cas:proxy>https://proxy-a.example.org/cas/pgtCallback</cas:proxy>
    </cas:proxies>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Under **CAS Protocol 2.0**, when traversing multiple proxies, **the first `cas:proxy` element is the most recently traversed proxy**. For the path A → B → C, C receives **`[B, A]`**, not `[A, B]`. The list entries normally represent **`pgtUrl` (proxy callback identities)**—**not backend resource URLs**, display names, or service tickets.

| Index | Value | Interpretation |
| --- | --- | --- |
| **[0]** | https://proxy-b.example.org/cas/pgtCallback | Proxy closest **to C**. |
| **[1]** | https://proxy-a.example.org/cas/pgtCallback | Proxy preceding B, closer to the browser/user. |
| **Absent** | No proxy elements | May represent a direct ST or unproxied validation, depending on profile. |

**Never assume an empty proxy list is always an error on every endpoint.** An endpoint accepting **direct STs** may validly see an empty chain. Conversely, an endpoint **exclusively for delegated PTs** must **actively reject an empty chain**. Separate policies by endpoint and use case.

### Why Inspect the Whole Chain Rather Than Only the Last Element?

C might trust B as an API gateway, yet B could accept a request from an unapproved proxy X:

~~~text
Expected: Alice -> A -> B -> C
Observed: Alice -> X -> B -> C

Expected cas:proxies = [B, A]
Observed cas:proxies = [B, X]
~~~

Checking **only “contains B”** would falsely accept it. Checking **the entire `[B,A]` list in order** rejects it even though B itself is valid. Likewise, **`[B,A,X]`** must fail if policy permits only **`[B,A]`**—never ignore extra hops.

### Avoid Loose Prefix/Substring Wildcards

If the allowlist specifies **https://proxy-a.example.org/cas/pgtCallback**, never match strings like:

- https://proxy-a.example.org.evil.test/cas/pgtCallback
- http://proxy-a.example.org/cas/pgtCallback
- https://proxy-a.example.org/cas/pgtCallback-extra
- https://proxy-a.example.org/anotherPath
- https://evil.test/?next=https://proxy-a.example.org/cas/pgtCallback

Use exact IDs standardized under the **CAS contract** and governed configuration; if regexes are necessary in the CAS Java Client, **anchor**, escape, and test lookalike inputs. **Never broadly normalize host/path/query** in ways that erase identity distinctions verified by CAS.

## 7. Designing a Full-Chain Allowlist

A dedicated policy for backend C:

~~~yaml
cas:
  backend-c:
    service: "https://api.example.org/cas/receiver"
    require-delegation: true
    allowed-chains:
      - ["https://proxy-b.example.org/cas/pgtCallback",
         "https://proxy-a.example.org/cas/pgtCallback"]
~~~

This is an **illustrative application policy**, not a built-in Spring Boot auto-configuration property. Deployment must map this policy into **Cas20ProxyTicketValidator** and/or an authorization service matching your client version.

**Matching rules:**

1. Check CAS ticket validation success first; if it fails, **DENY**.
2. Verify the returned/validated service ID matches C's registered service.
3. The CAS-validated chain must have the **exact element count**, exact URL at each position, and exact order.
4. If the endpoint requires proxying, reject empty, null, or incomplete chains.
5. Use a **full-chain allowlist** rather than checking “each hop belongs to a set”: the set `{A,B}` would mistakenly accept both `[A,B]` and `[B,A]`.
6. Never implicitly add gateways/CDNs/ingresses into the chain unless they are published CAS proxy identities.
7. If multiple chains are permitted, enumerate **each valid chain** with business justification; avoid broad regexes that accept arbitrary depths or paths.
8. After the chain passes, **check the user and permissions for the operation/tenant**; a trusted proxy never grants blanket user rights.

### Chain Order in Library Config

The CAS Java Client provides **`allowedProxyChains`**; each entry can be a proxy URL string or regex per the client's documentation syntax. **How the library stores/converts chains and matches them depends on the client version**, so always **test the `[B,A]` case** against a real CAS server; never invert the list intuitively based on “traffic direction” when configuring. In this lesson's policy table, **`[B,A]` is the XML order received by C**.

### One Policy Distinction Beyond the Chain

If backend C only cares to trust **proxy B** regardless of who sits upstream of B, document explicitly that this is a **policy accepting any upstream of B**, distinct from **verifying the full proxy chain**. For sensitive data, prefer a **strict full-chain allowlist** to prevent unexpected delegation paths. If business genuinely allows extensible chains, require a threat model, max hop count, deny/loop lists, identity uniqueness, and auditing—never silently set `acceptAnyProxy=true`.

## 8. Standalone Java 17: Validating the Full Chain in Exact Order

**ProxyChainPolicyDemo.java** runs on **JDK 17** with no Spring or CAS server needed. The **`VerifiedTicket`** input simulates **the result already validated by a CAS TicketValidator over HTTPS**. In production, never construct it directly from HTTP headers, JSON bodies, query params, client-submitted XML, or unvalidated `PT-` strings.

~~~java
import java.util.List;
import java.util.Set;

public class ProxyChainPolicyDemo {
    private static final String TARGET =
            "https://api.example.org/cas/receiver";
    private static final String A =
            "https://proxy-a.example.org/cas/pgtCallback";
    private static final String B =
            "https://proxy-b.example.org/cas/pgtCallback";

    // CAS XML at backend C: closest proxy appears FIRST.
    private static final List<String> EXPECTED = List.of(B, A);
    private static final Set<String> ACTIVE_USERS = Set.of("alice");

    record VerifiedTicket(String user, String service, List<String> proxies) {}

    static String decide(VerifiedTicket ticket) {
        if (ticket == null) {
            return "DENY INVALID_TICKET";
        }
        if (!TARGET.equals(ticket.service())) {
            return "DENY WRONG_SERVICE";
        }
        if (ticket.user() == null || !ACTIVE_USERS.contains(ticket.user())) {
            return "DENY USER_NOT_ALLOWED";
        }
        if (ticket.proxies() == null || ticket.proxies().isEmpty()) {
            return "DENY EMPTY_CHAIN";
        }
        if (!EXPECTED.equals(ticket.proxies())) {
            return "DENY UNAPPROVED_CHAIN";
        }
        return "ALLOW";
    }

    static void check(String label, VerifiedTicket ticket) {
        System.out.println(label + ": " + decide(ticket));
    }

    public static void main(String[] args) {
        check("valid A-B", new VerifiedTicket(
            "alice", TARGET, List.of(B, A)));

        check("reversed B-A", new VerifiedTicket(
            "alice", TARGET, List.of(A, B)));

        check("extra hop", new VerifiedTicket(
            "alice", TARGET, List.of(B, A,
                "https://unknown.example.org/cas/pgtCallback")));

        check("unapproved upstream", new VerifiedTicket(
            "alice", TARGET, List.of(B,
                "https://evil.example.org/cas/pgtCallback")));

        check("direct", new VerifiedTicket(
            "alice", TARGET, List.of()));

        check("wrong service", new VerifiedTicket(
            "alice", "https://other.example.org/cas/receiver",
            List.of(B, A)));

        check("unknown user", new VerifiedTicket(
            "mallory", TARGET, List.of(B, A)));

        check("missing validation", null);
    }
}
~~~

Run:

~~~bash
javac ProxyChainPolicyDemo.java
java ProxyChainPolicyDemo
~~~

**Exact stdout:**

~~~text
valid A-B: ALLOW
reversed B-A: DENY UNAPPROVED_CHAIN
extra hop: DENY UNAPPROVED_CHAIN
unapproved upstream: DENY UNAPPROVED_CHAIN
direct: DENY EMPTY_CHAIN
wrong service: DENY WRONG_SERVICE
unknown user: DENY USER_NOT_ALLOWED
missing validation: DENY INVALID_TICKET
~~~

**Explanation of each case:**

- **valid A-B:** traversal A→B→C produces **`[B,A]`**, matching the exact policy so ALLOW.
- **reversed B-A:** CAS XML `[A,B]` is not `[B,A]`; set-based comparison would fail here.
- **extra hop:** having B, A, plus X does **not** count as valid; fails exact-chain check.
- **unapproved upstream:** B is valid, yet upstream X is unauthorized; fails.
- **direct:** no proxies is invalid on an endpoint accepting **delegated PTs only**.
- **wrong service:** ticket service differs from C's policy; fails even with a valid chain.
- **unknown user:** a valid service and chain never grant access to arbitrary accounts.
- **missing validation:** no result from CAS `TicketValidator`, no access granted.

**Demo boundaries:** `VerifiedTicket` objects are built from static literals in `main`; the program **validates no CAS tickets, HTTPS, XML, PGTs, TTLs, caches, or real CAS identities**. In a real system, run **`decide`** only on outputs confirmed by a trusted CAS server and populated by the library's validator—never from the browser.

## 9. Spring Security CAS: Classes Involved with PTs

In **Spring Security 6.x**, native CAS integration assigns these roles:

| Class | Role |
| --- | --- |
| **CasAuthenticationEntryPoint** | Redirects browsers to CAS `/login` when authentication is needed; does not validate PTs. |
| **CasAuthenticationFilter** | Extracts CAS tickets from HTTP requests; when configured for stateless use, can accept tickets outside `/login/cas`. |
| **ServiceProperties** | Defines the service URL; can enable **authenticateAllArtifacts** to process CAS artifacts across multiple paths. |
| **ServiceAuthenticationDetailsSource** | Builds `ServiceAuthenticationDetails` carrying the request's specific service URL for stateless proxy auth. |
| **CasAuthenticationProvider** | Uses `TicketValidator` to authenticate CAS ST/PTs, loads user details/authorities, returns `CasAuthenticationToken`. |
| **Cas20ServiceTicketValidator** | Calls `/serviceValidate` for STs; unsuitable when PTs must be accepted. |
| **Cas20ProxyTicketValidator** | Calls `/proxyValidate`, validates CAS validation responses and configured **proxy-chain policies**. |
| **StatelessTicketCache** | Optionally caches validation results for remoting/stateless clients; requires strict TTLs and security bindings. |

### 9.1. Switching Validators When the Backend Accepts PTs

In an app that already has CAS login integration, switching from **Cas20ServiceTicketValidator** to **Cas20ProxyTicketValidator** is necessary but insufficient. You must also configure allowed proxy chains, exact service IDs, and ticket cache/endpoint rules.

**Illustrative configuration fragment using Apereo CAS Java Client; does not compile standalone without a project and dependencies:**

~~~java
import org.apereo.cas.client.util.CommonUtils;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;

String casPrefix = "https://cas.example.org/cas";
Cas20ProxyTicketValidator validator =
        new Cas20ProxyTicketValidator(casPrefix);

validator.setAcceptAnyProxy(false);
validator.setAllowEmptyProxyChain(false);
validator.setAllowedProxyChains(CommonUtils.createProxyList(
        "https://proxy-b.example.org/cas/pgtCallback "
      + "https://proxy-a.example.org/cas/pgtCallback"));
~~~

**Meaning:**

- **casPrefix:** approved CAS server base URL; the validator calls **/proxyValidate** over HTTPS.
- **setAcceptAnyProxy(false):** do not bypass proxy chain rules.
- **setAllowEmptyProxyChain(false):** an endpoint strictly for delegated PTs **rejects** direct STs / empty chains.
- **setAllowedProxyChains:** list of permitted chains—here one chain of B and A per policy; **verify exact ordering/matching syntax by testing against your CAS client version**.
- **CommonUtils.createProxyList:** CAS Java Client helper converting a policy string into `ProxyList`; check exact packages/APIs against your dependency.

**If your client version uses a different ProxyList API**, never fall back to **`acceptAnyProxy=true`** to silence compile/config errors. Consult your exact version's Javadoc and implement an equivalent strict allowlist.

### 9.2. Spring Bean Fragment: TicketValidator Inside CasAuthenticationProvider

In a Spring Boot 3.3.5 project with **spring-security-cas**, **CasAuthenticationProvider** receives the `TicketValidator` configured above:

~~~java
// Snippet must live inside a @Configuration class with real beans/imports.
// This is NOT a complete runnable Spring Security application.

@Bean
CasAuthenticationProvider casProvider(
        ServiceProperties serviceProperties,
        UserDetailsService localUsers,
        Cas20ProxyTicketValidator proxyValidator) {

    CasAuthenticationProvider provider = new CasAuthenticationProvider();
    provider.setServiceProperties(serviceProperties);
    provider.setUserDetailsService(localUsers);
    provider.setTicketValidator(proxyValidator);
    provider.setKey("cas-backend-provider");
    return provider;
}
~~~

Corresponding imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;
~~~

**The provider key is an internal identifier**, not a private signing key. **`UserDetailsService`** maps the CAS-verified user to local accounts/authorities; never grant every username `ROLE_ADMIN`.

To participate in **`Spring SecurityFilterChain`**, you also need **CasAuthenticationFilter**, **AuthenticationManager/ProviderManager**, filter ordering, the right `SecurityContextRepository`/session policy, and endpoint matchers. Declaring the provider bean alone **does not enable CAS ticket authentication**. When configuring the CAS filter manually in Spring Security 6.x, ensure **`SecurityContextRepository` persists Authentication for stateful logins** and the right **`SessionAuthenticationStrategy`** (session fixation protection) is wired; otherwise subsequent requests may appear anonymous.

### 9.3. Accepting PTs on URLs Other Than /login/cas

Per Spring Security CAS proxy integration docs, stateless remoting receiving tickets on URLs other than the login callback typically requires:

~~~java
// Illustrative snippet assuming filter and serviceProperties are already created:
serviceProperties.setAuthenticateAllArtifacts(true);
filter.setServiceProperties(serviceProperties);
filter.setAuthenticationDetailsSource(
        new ServiceAuthenticationDetailsSource(serviceProperties));
~~~

**ServiceAuthenticationDetailsSource** lets the validator use the **request's service URL** as the service value in stateless scenarios. However, enabling **`authenticateAllArtifacts=true`** application-wide can cause any URL with a **`ticket`** query param to be intercepted by the CAS filter unless guarded by proper matchers/endpoint policies.

Safeguards:

- Dedicate a **separate filter chain or request matcher** for PT-accepting endpoints.
- Validate CAS tickets for the **exact registered service ID**; avoid building `service` from client-controlled `Host`/`X-Forwarded-*` headers.
- Configure **`acceptAnyProxy=false`** and a full-chain allowlist before exposing the endpoint.
- Decide explicitly **whether direct STs (empty chain) are permitted** or PT-only, and test both.
- Secure authentication success/failure handlers, `SecurityContext`/session behavior, and route authorization.
- Never let a valid PT for one resource grant access across unrelated URLs/tenants just because the backend shares `CasAuthenticationToken`.

**This snippet is not a complete production template.** When assembling the full filter chain, verify Spring Security/CAS client version APIs and run live integration tests; misconfiguration can admit PTs outside the intended scope.

## 10. Ticket Caching: CAS Single-Use vs. Spring Cached Results

Under the CAS protocol, **ST/PTs** are short-lived artifacts **valid once** when calling the CAS server to validate. After `/proxyValidate` succeeds, CAS normally refuses to revalidate **the same PT**.

Spring Security CAS provides **`StatelessTicketCache`** for sessionless remoting architectures to cache **`CasAuthenticationToken` after successful validation**. If a client presents **the same PT string** again to the backend, Spring can retrieve the `Authentication` from cache without calling CAS again.

**This does not make a PT multi-use at CAS.** It creates a **local backend cache decision accepting the bearer ticket again**, introducing risk if the ticket is intercepted.

### Policy Trade-Offs

| Policy | Advantages | Trade-Offs |
| --- | --- | --- |
| **No PT result caching / null cache** | Mirrors one-time CAS validation; replayed PTs fail if revalidated. | Every stateless request needs a **fresh PT** or another session/token mechanism. |
| **StatelessTicketCache with very short TTL and bound scope** | Cuts round trips to CAS; lets clients reuse within the allowed window. | Within the TTL, anyone holding that PT can obtain `Authentication` unless extra binding/authz prevents it; evaluate carefully. |
| **Stateful SP HttpSession** | Browser validates ST/PT once and keeps `SecurityContext`. | Requires cookie/session security, invalidation, and multi-node shared sessions/affinity. |

If caching is enabled, enforce:

1. A short TTL aligned with threat modeling and logout/revocation policies.
2. Never cache negative validations as valid users.
3. Cache keys must never collide across **different CAS servers, services, tenants, or role/proxy policies**.
4. Prevent reusing one PT across endpoints with different services or authorizations.
5. Clear caches when proxies/PGTs are revoked or trust policies change.
6. Bound memory/size, encrypt, and restrict cache access.
7. Test replay with and without caching to make the difference explicit—never promise “single-use” if the backend intentionally caches results.

**Never combine `acceptAnyProxy=true` with multi-hour caching** to avoid invalid ticket errors. That widens both trust and credential lifetimes; if callers need sustained backend calls, design an appropriate delegation/token lifecycle rather than leaning on indefinite ticket caches.

## 11. Protecting Proxy Callbacks, TLS, and PGT Secrets

### `pgtUrl` Is Not an Arbitrary URL

Per the CAS protocol, CAS invokes **`pgtUrl` over HTTPS** and verifies peer trust. Operations must verify:

- Full public URL with **`scheme=https`**.
- CAS server can reach the endpoint with a valid TLS certificate and matching hostname.
- The endpoint belongs to an approved proxy/registered service—never an attacker-supplied callback address.
- Never use a broad **allow-all hostname verifier** or disable TLS cert validation just to “make PGT work.”
- CAS callbacks return proper responses; failed requests must never yield PGTs.
- The callback route **must not require browser authentication or cause CAS login redirect loops**.
- Never log **`pgtId`**, **`pgtIou`**, ST, or PT in reverse proxies, access logs, APM, or browser analytics.

### PGT Storage

- Store PGTs server-side in access-controlled storage with TTL/cleanup; never transmit PGTs to clients/browsers.
- Across multiple instances, the CAS callback can hit node A while the ticket validation response lands on node B; **PGT storage must be shared or deterministically routed**, never matching unknown IOUs to another session's PGT.
- Use **IOU correlation** rather than picking the latest PGT.
- Use a PGT only when bound to the exact authenticated principal/service and policy.
- Never retain compromised/expired PGTs; maintain incident response/rotation and CAS logout lifecycle handling.
- Check callback, TLS, proxy, race, and storage availability errors. Never bypass TLS or issue PTs from a null PGT.

### PT Transport

A PT is a **bearer credential**, requiring HTTPS from proxy→backend; when sent as a query param, scrub URLs in load balancers, logs, tracing, and error reports, and avoid Referrer leakage. The backend validates the PT with a trusted CAS server over HTTPS and avoids storing raw PTs in `SecurityContext`/audit outputs unnecessarily.

### CAS Server-Side Service Registry

The CAS server must restrict:

- Which proxies may receive PGTs / proxy permission.
- Which `targetService`s a proxy may request PTs for.
- Callback `pgtUrl` and TLS policies.
- Which service IDs backends validate with; avoid broad wildcards.
- Whether multi-hop delegation is allowed and under what policy.

Backend C **still checks the full chain** because CAS allowing a proxy does not mean C approved that proxy chain for every feature.

## 12. Cases Where Validation Succeeds Yet Access Must Still Be Denied

Suppose CAS returns user **alice** and the exact chain **`[B,A]`**:

~~~text
cas:authenticationSuccess
  cas:user = alice
  cas:proxies = [B,A]
  validated service = https://api.example.org/cas/receiver
~~~

C may still need to reject unless all hold:

1. **alice** maps to a local account in the right tenant/organization/CAS realm.
2. The account is active, not locked or deprovisioned.
3. Authorities/roles permit the specific **operation**.
4. Resource/owner/tenant matches the requested data—not merely `authenticated()`.
5. Calling app B is permitted proxy scope to service C under policy.
6. The request does not trigger cross-tenant BOLA/IDOR even with a completely valid chain.
7. Rate limits, observability, and audits are active without exposing raw tickets or sensitive proxy identities.

**A CAS username is not a globally unique identity when multiple CAS servers exist.** Identical usernames across two CAS realms can be two different people; namespace by issuer/CAS trust domain and bind accounts explicitly. Even with a single multi-tenant CAS server, verify local tenant membership.

### Per-Endpoint Policies Instead of One Global Policy for Every Backend

Example:

| Backend Endpoint | Allowed Chain | Additional Requirement |
| --- | --- | --- |
| `/api/reports/read` | `[B,A]` | `alice` holds `REPORT_READ` in tenant X. |
| `/api/payroll/export` | `[TrustedPayrollGateway]` | Payroll role; disallow arbitrary delegation from portal A. |
| `/api/self-service` | direct ST or `[A]` per design | User's own records only. |
| `/api/admin` | Public PTs rejected | Dedicated service principal/privileges and audit. |

**A valid ticket identity on one endpoint must never become a global admin identity.** Chain policy, service URL, roles, and resource scope must work together.

## 13. Protecting XML Responses and Parsing Boundaries

CAS `/proxyValidate` returns XML/JSON depending on CAS version/config. **Never hand-parse XML supplied by a browser.** The validator must:

1. Call the trusted CAS endpoint over HTTPS with hostname/certificate validation.
2. Send the exact ticket and **`service`**.
3. Verify **`authenticationSuccess`** rather than `authenticationFailure`.
4. Parse username/attributes and **`cas:proxies`** solely from the **CAS server's response**, never from the client.
5. Defend against XXE, entity expansion, unexpected namespaces/DTDs, oversized payloads, and unsafe XML parser settings; prefer a maintained CAS Java Client.
6. Enforce the full-chain allowlist/empty-chain policy and user/service authorization.
7. Create `Authentication` only when all steps pass.

**Never trust `cas:proxies` copied from user input.** An attacker-crafted XML string can show a neat `[B,A]`, yet only the **CAS validator** knows which PT CAS minted and its genuine proxy history. Plain string matching is not cryptographic or protocol validation.

### Distinguishing CAS XML from SAML Assertions

CAS XML `serviceResponse` is not a **SAMLResponse** carrying a SAML2 XML Signature. Never use **`Saml2WebSsoAuthenticationFilter`** to validate native CAS PTs, and never treat a SAML2 issuer as a CAS proxy callback. If the CAS server also integrates SAML/OIDC, enforce the exact protocol and trust boundaries for each.

## 14. Integration Test Scenarios

Use a **CAS sandbox configured with a service registry, PGT callbacks, and PT issuance**, with at least Proxy A, Proxy B, and Backend C. Observe **`/serviceValidate`, `/proxy`, `/proxyValidate`** while **masking ST/PT/PGT in logs**. Negative tests must separately verify **CAS rejection** and **full-chain policy rejection**.

| # | Scenario | Expected Result |
| --- | --- | --- |
| 1 | A gets valid ST and A's `pgtUrl` over trusted HTTPS | A retrieves PGT after callback + IOU match. |
| 2 | CAS PGT callback targets HTTP URL | **Rejected** by HTTPS requirement. |
| 3 | CAS callback TLS cert/hostname mismatch | No PGT issued; never disable TLS validation. |
| 4 | A's `pgtUrl` unreachable or returns error status | PGT acquisition fails; no PT issued. |
| 5 | Response IOU mismatches PGT callback | **Refuses** to use PGT. |
| 6 | A uses valid PGT to request PT-B for `targetService=B` | CAS issues PT-B if service registry permits. |
| 7 | PGT expired or revoked | CAS rejects `/proxy`; no PT returned. |
| 8 | PT-B validated at B with exact `service` | Succeeds if policy and ticket are valid. |
| 9 | PT-B sent to backend C instead of B | **`INVALID_SERVICE`** due to targetService mismatch. |
| 10 | PT sent to `/serviceValidate` instead of `/proxyValidate` | **Fails** per CAS 2.0. |
| 11 | Same PT resubmitted to CAS a second time | CAS rejects ticket reuse. |
| 12 | CAS `/proxyValidate` returns `authenticationFailure` | Backend creates no `Authentication` or permissions. |
| 13 | Valid PT-C, `cas:proxies=[B,A]` | **ALLOW** if C permits that exact chain and user/action pass. |
| 14 | Reversed `cas:proxies=[A,B]` | **DENY**, even though both A and B are trusted hops. |
| 15 | `cas:proxies=[B,X]` | **DENY**; valid B does not rescue untrusted upstream X. |
| 16 | `cas:proxies=[B,A,X]` | **DENY** due to extra hop outside allowlist. |
| 17 | `cas:proxies=[B]` instead of `[B,A]` | **DENY** if C requires the two-hop chain. |
| 18 | `cas:proxies=[]` on a PT-only endpoint | **DENY EMPTY_CHAIN**. |
| 19 | Chain has `http://proxy-b` instead of `https://proxy-b` | **DENY**; exact callback identity mismatch. |
| 20 | Chain has domain `proxy-b.example.org.evil.test` | **DENY**; never match host substrings. |
| 21 | Chain valid yet user lacks local role/resource ACL | **DENY authorization**. |
| 22 | Chain valid yet CAS ticket `service` is a different endpoint | **DENY WRONG_SERVICE**. |
| 23 | Attacker supplies XML with `<cas:proxies>[B,A]` | Untrusted unless returned by CAS server validation. |
| 24 | `StatelessTicketCache` enabled and old PT reused within TTL | Verify cache behavior; never claim CAS revalidated it. |
| 25 | Cache exceeds TTL or proxy policy changes | Must not retain stale access; require fresh PT/reauth per policy. |
| 26 | CAS server HTTPS certificate expired | Validation errors out; never disable TLS to force acceptance. |
| 27 | App uses multiple CAS servers with same username `alice` | Never auto-merge identities/accounts across CAS realms. |
| 28 | Backend C belongs to another tenant despite valid `[B,A]` | **DENY cross-tenant access**. |
| 29 | B requests PT for unregistered/disallowed service | CAS `/proxy` rejects. |
| 30 | Multi-node app, PGT callback and validator hit two nodes | Proper shared storage/session routing; IOU must match. |

**Tests should report results per layer:**

- **`CAS_VALIDATION=PASS/FAIL`**: CAS server validated the ticket.
- **`PROXY_CHAIN=PASS/FAIL`**: app accepted the **entire** proxy list.
- **`SERVICE_BINDING=PASS/FAIL`**: exact `targetService`.
- **`LOCAL_AUTHZ=PASS/FAIL`**: user, tenant, and resource permissions.

All four layers must pass before executing the operation. A test showing only a **valid ticket** does not prove full-chain policy enforcement.

## 15. Layer-by-Layer Troubleshooting

| Symptom | Common Cause | Investigation Path |
| --- | --- | --- |
| **INVALID_TICKET** | PT expired, already validated once, or nonexistent. | Request a fresh PT; never replay or bypass validator. |
| **INVALID_SERVICE** | CAS `targetService` at PT issuance differs from `service` at validation. | Compare exact scheme/host/path/port, proxy rewriting, and service registry. |
| **UNAUTHORIZED_SERVICE_PROXY** | Service not permitted to obtain PGTs/proxy. | Check CAS registered service policy; never open wildcards. |
| **INVALID_PROXY_CALLBACK** | `pgtUrl` TLS/hostname/endpoint trust failed. | Check HTTPS callback, certificate chain, DNS, and firewall. |
| **Missing PGTIOU** | Callback failed or CAS denied PGT issuance. | Check validation response and proxy receptor; never fall back to a default PGT. |
| **IOU present yet PGT missing** | Storage/race/cluster mapping failure. | Check distributed PGT storage, callbacks, and expiry. |
| **CAS validates PT yet backend returns 403** | Proxy-chain allowlist or local user/tenant role denied. | Separate CAS auth success from application authorization. |
| **Cas20ServiceTicketValidator rejects PT** | Calling `/serviceValidate` instead of `/proxyValidate`. | Switch to `Cas20ProxyTicketValidator` with the right endpoint. |
| **`[B,A]` rejected when expecting A→B** | Confusing traversal direction with XML order. | CAS XML puts **most recent proxy first**; verify rule per client version. |
| **`[B,X]` still accepted** | `acceptAnyProxy=true` or checking only B. | Enforce full-chain policy and test unknown upstreams. |
| **Direct ST accepted on PT-only endpoint** | Empty proxy chain allowed. | Set `setAllowEmptyProxyChain(false)` or equivalent policy. |
| **Same PT works multiple times** | Spring stateless validation-result cache. | Inspect cache TTL, scope, and reuse policy. |
| **HTTP 200 from CAS without auth success** | Body holds `authenticationFailure` or parse error. | Parse via CAS validator rather than checking status code alone. |
| **Tickets leaked in access logs** | Raw query URLs logged verbatim. | Redact `ticket`/`pgtId`/`pgtIou` in proxy/APM/app logs. |
| **Reverse proxy change breaks service** | Host/scheme/path mutated. | Use a fixed public service ID or trusted forwarded headers. |
| **PGT saved on node A, PT request on node B misses** | Multi-node storage out of sync. | Shared PGT store with TTL/ACL; verify IOU correlation. |
| **Valid CAS user accesses another tenant's data** | Local authorization lacks tenant scoping. | Enforce membership, roles, and data-layer tenant predicates. |

**Suggested logging** (not auto-generated by the framework):

~~~text
event=cas_proxy_validation result=success service=backend-c trace=t-102
event=cas_proxy_chain_policy result=deny reason=UNAPPROVED_CHAIN trace=t-102
event=cas_local_authorization result=deny action=payroll-export trace=t-102
~~~

Never log raw **ST, PT, PGT, PGTIOU, TGC**, full proxy callback URLs containing secrets, sensitive usernames, or complete XML validation responses. Audits need only partner IDs, chain policy IDs, reason codes, and governed trace IDs.

## 16. Common Pitfalls

1. **Accepting anything starting with `PT-`**: prefixes are conventions, not proof of validity.
2. **Calling `/serviceValidate` to check a PT**: CAS 2.0 rejects PTs there.
3. **Checking only one trusted proxy**: an untrusted upstream proxy can slip through.
4. **Ignoring `cas:proxies` ordering**: CAS returns most-recent-first.
5. **Comparing as a Set instead of a List**: `[A,B]` and `[B,A]` are different chains.
6. **Using `contains`/`startsWith` for callback URLs**: can match spoofed hosts or paths.
7. **Setting `acceptAnyProxy=true` in production** to silence allowlist errors.
8. **Allowing empty chains on PT-only endpoints**: mistakenly admits direct STs.
9. **Trusting `cas:proxies` sent by an HTTP client** instead of the validated CAS response.
10. **Writing PGT/PGTIOU/PT to logs or browsers**: exposes credentials and correlation handles.
11. **Using PGTIOU as a PGT**: an IOU cannot request PTs.
12. **Accepting arbitrary `pgtUrl`/ticket URLs** without verifying TLS and registry entries.
13. **Retaining PGTs forever without cleanup/rotation** when sessions or proxies are revoked.
14. **Failing to test races between PGT callbacks and validation responses**.
15. **Ignoring service binding**: a PT for B is invalid at C.
16. **Skipping tenant/role checks after proxy chain passes**: valid delegation does not mean business permission.
17. **Assuming Spring's cache means CAS revalidated the PT**: the cache only reuses prior results.
18. **Using Java/Spring client APIs across versions without checking Javadoc**.
19. **Conflating CAS Proxy with OAuth2 delegated tokens or SAML2 Assertions**.
20. **Forgetting reverse proxy/HTTPS public service URLs**, causing puzzling `INVALID_SERVICE` errors.
21. **Checking only HTTP 200 on `/proxyValidate`**: the body may contain `authenticationFailure`.
22. **Applying the CAS filter to every endpoint** without checking `authenticateAllArtifacts` and chain-specific policies.
23. **Granting `ROLE_ADMIN` to every CAS username** without local account management.
24. **Merging usernames across CAS realms** when supporting multiple partners.
25. **Letting ticket caches outlive revocation windows**.
26. **Leaving proxy reception endpoints unprotected against unexpected registration or manipulation**.

## 17. Production Deployment Checklist

**CAS server and protocol**

- [ ] CAS `serverPrefix` and **/serviceValidate, /proxy, /proxyValidate** endpoints match the CAS protocol/version.
- [ ] CAS registered services permit only approved proxies and `targetService`s.
- [ ] `pgtUrl` uses HTTPS/TLS trust; callback is reachable yet never caller-chosen.
- [ ] PGTIOU is matched against the exact server-side PGT with TTL and race protection.
- [ ] ST/PTs are validated by the CAS server with matching service IDs; never trust prefixes or request usernames.
- [ ] PGTs remain strictly server-side; ST/PT/PGT/IOU never leak into logs or browsers outside required protocol flows.

**Proxy chain policy**

- [ ] PT-only vs. direct ST allowance is explicitly decided per backend endpoint.
- [ ] Validates **every hop, exact count, most-recent-first ordering, and exact callback identities**.
- [ ] `acceptAnyProxy=true` is disabled; any mandatory exception has a documented threat model and expiration.
- [ ] `allowedProxyChains` is tested against real CAS responses, including reversed, extra, unknown, and empty chains.
- [ ] CAS HTTPS validation responses are parsed with a hardened client, never client-supplied XML.
- [ ] User account, roles, and tenant/resource ACLs are enforced even when the chain is valid.

**Spring Security and operations**

- [ ] `Cas20ProxyTicketValidator` matches the CAS Java Client version; `setAllowedProxyChains` reflects policy.
- [ ] `CasAuthenticationProvider` is wired into `AuthenticationManager` and the CAS filter covers the exact request scope.
- [ ] If using a custom filter, `SecurityContextRepository` and session fixation protection are configured for stateful flows.
- [ ] If stateless, `ServiceAuthenticationDetailsSource`, `authenticateAllArtifacts`, and caching are tightly controlled.
- [ ] `StatelessTicketCache` TTL and service/tenant scoping are intentional; replay and expiry are tested.
- [ ] Multi-node proxy PGT storage and CAS callbacks have HA, TTLs, and ACLs.
- [ ] TLS, proxies, hostnames, service IDs, and clocks are monitored.
- [ ] Negative tests cover CAS validation, chains, service binding, and local authorization.

## 18. Review Questions

**Q1.** Backend C receives PT-C and the list `[B,A]`. Can it trust the request immediately because both proxies are in its allowlist?  
**Answer:** Not yet. C must call CAS `/proxyValidate` with exact **service C**, verify the **entire chain in exact order** against policy, and then enforce user/resource permissions.

**Q2.** CAS returns `[B,A]`. The user traversed A before B, so did CAS invert the order by mistake?  
**Answer:** No. The CAS Protocol puts the **most recent proxy first**; for A→B→C, C receives `[B,A]`.

**Q3.** Can PGTIOU in `cas:proxyGrantingTicket` be used as the `pgt` parameter for CAS `/proxy`?  
**Answer:** No. PGTIOU is solely a correlation IOU. The **real PGT** arrives via the HTTPS proxy callback and must be looked up by IOU.

**Q4.** Can a PT issued by CAS for Backend B be reused at Backend C if C belongs to the same company?  
**Answer:** No. A PT is bound to **`targetService`**. C must reject with **`INVALID_SERVICE`**, unless CAS mints a fresh ticket specifically for service C.

**Q5.** Why can't `/serviceValidate` replace `/proxyValidate` when handling PTs?  
**Answer:** CAS 2.0 specifies that `/serviceValidate` **does not validate PTs successfully**, whereas `/proxyValidate` supports both ST/PTs and proxy history.

**Q6.** Can `[B,X]` pass because B is a trusted proxy and X did not call C directly?  
**Answer:** No, if policy requires `[B,A]`. The **entire delegation chain** must match.

**Q7.** When can an empty `cas:proxies` list be valid?  
**Answer:** For a direct ST on an endpoint that allows direct logins. A PT-only delegated endpoint must reject empty chains.

**Q8.** Is enabling `acceptAnyProxy=true` safe as long as the CAS ticket is genuine?  
**Answer:** CAS validates that the PT is real, yet the backend still needs a policy on **which proxies may represent users**. `acceptAnyProxy=true` removes chain protection and is unsuitable by default for sensitive systems.

**Q9.** When `StatelessTicketCache` lets the same PT authenticate a second time, is the CAS server revalidating the PT?  
**Answer:** No. Spring's cache reuses the successful result from the first validation; the ticket at CAS remains single-use.

**Q10.** If CAS verified both the PT and the exact full chain, why must the backend still check roles and tenants?  
**Answer:** Tickets and proxy chains are **delegated authentication**, not authorization across every API, organization, or resource.

## 19. Standards and API References

1. [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html), especially **2.5.4 proxy callback**, **2.6 /proxyValidate**, **2.7 /proxy**, **3.3 PGT**, and **3.4 PGTIOU**. Cross-check with your organization's CAS version since development-branch docs can change.
2. [Apereo CAS — CAS 2.0 Protocol in Jasig docs](https://jasigcas.readthedocs.io/en/latest/cas-server-documentation/protocol/CAS-Protocol-V2-Specification.html): service requirements, ST/PT validation, XML `<cas:proxies>`, and proxy ordering rules.
3. [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): proxy grants, `CasAuthenticationFilter`, `CasAuthenticationProvider`, `ServiceAuthenticationDetailsSource`, and `StatelessTicketCache`. Current docs may target Spring Security 7; use 6.x Javadoc for 6.x examples.
4. [Spring Security 6.3 — CasAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): processing ST/PT, proxy receptor, `serviceDetails`, and `authenticateAllArtifacts`.
5. [Spring Security 6.5 — CAS authentication package](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/cas/authentication/package-summary.html): `CasAuthenticationProvider` and `StatelessTicketCache`.
6. [Apereo Java CAS Client](https://github.com/apereo/java-cas-client): `Cas20ProxyTicketValidator`, `Cas20ProxyReceivingTicketValidationFilter`, `acceptAnyProxy`, `allowedProxyChains`, `pgtUrl`, and storage.
7. [CAS Java Client Javadoc (Jasig 3.6.4) — Cas20ProxyTicketValidator](https://javadoc.io/static/org.jasig.cas.client/cas-client-core/3.6.4/org/jasig/cas/client/validation/Cas20ProxyTicketValidator.html): `setAcceptAnyProxy`, `setAllowedProxyChains`, `setAllowEmptyProxyChain`; package names differ from newer Apereo releases—check your project's actual APIs.
8. [Spring Security — ServiceProperties Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/cas/ServiceProperties.html): `authenticateAllArtifacts`, `service`, and `sendRenew`.

**Summary:** A backend receiving a **CAS Proxy Ticket** must **validate the ticket with CAS `/proxyValidate` for the exact service**, then **match the entire `cas:proxies` list in most-recent-first order** against a **full-chain allowlist**, and finally enforce **local user/role/tenant/resource authorization**. **PGTs are delivered separately via HTTPS callback and correlated by PGTIOU**, and **`StatelessTicketCache` does not turn PTs at CAS into reusable tickets**.

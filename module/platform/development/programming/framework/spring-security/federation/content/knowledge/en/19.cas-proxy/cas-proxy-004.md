# Correlating PGT IOU with Proxy Granting Ticket in the Application

## 1. The Problem in CAS Proxy

In **Spring Security - federation**, under the **CAS Proxy** topic, a web application that has logged a user in via Central Authentication Service (CAS) may need to call a downstream API **on behalf of** that user. In that case, the service ticket (ST) used to log into the application cannot be reused to authenticate with the API: an ST is issued for a single exact service and is valid for only one validation attempt. CAS supports a **proxy-granting ticket (PGT)** so the intermediary application can request a fresh **proxy ticket (PT)** specifically for the backend.

Under the standard callback mechanism, the CAS Server **does not return the real PGT directly in the ST validation result**. Instead:

- The CAS Server sends the **real PGT** (`pgtId=PGT-...`) and **PGT IOU** (`pgtIou=PGTIOU-...`) to the application's HTTPS `pgtUrl` endpoint.
- In the response from `/serviceValidate` or `/proxyValidate`, the CAS Server returns only **`<cas:proxyGrantingTicket>PGTIOU-...</cas:proxyGrantingTicket>`**.
- The application reads the **PGT IOU from the verified validation result**, looks up the **matching real PGT** stored by the callback, and binds that PGT to the corresponding CAS Assertion/principal.

**The PGT IOU is a correlation key, not a credential for CAS `/proxy`. The PGT is a sensitive bearer credential that can be used to request multiple PTs within its allowed lifetime.** Never confuse single-use consumption of the IOU mapping with the PGT itself being single-use.

If an application stores only a single `latestPgt` variable or looks up PGTs by username, two concurrent CAS flows can cross-bind the wrong users. If the callback lands on pod A while the validator runs on pod B, a local in-memory store causes the IOU lookup to miss the PGT. If `pgtId` leaks through logs or the browser, anyone holding the credential can request PTs for permitted target services.

**Lesson goal:** understand the two data channels, choose and wire `ProxyGrantingTicketStorage`, verify callback trust boundaries, handle races/TTLs/multi-node setups, and implement secure CAS Proxy integration in Spring Security.

## 2. Distinguishing Tickets and Sessions

| Artifact | Held By | Purpose | Validity and Key Notes |
| --- | --- | --- | --- |
| **TGT** – Ticket Granting Ticket | CAS Server, linked to the CAS SSO cookie | Maintains SSO and serves as the basis for issuing tickets. | Never pass the TGT to a backend service. |
| **ST** – Service Ticket | Delivered by browser to app A; A validates with CAS | Authenticates one login for **service A**. | Service-bound and single validation only. |
| **PGT** – Proxy-Granting Ticket | Proxying app A | Requests one or more **PTs** at CAS `/proxy`. | Higher-privilege secret than a PT; must have lifecycle/revocation. |
| **PGT IOU** | CAS callback and validation response | Pairs the right PGT with the ST/PT validation result. | Does not prove identity on its own; cannot be used to call `/proxy`. |
| **PT** – Proxy Ticket | Sent by A to backend B | Proves a backend B call under CAS Proxy. | Bound to `targetService=B`; single validation. |
| **TGC** | Browser and CAS Server | CAS login session cookie. | Not a PGT or a Spring session. |
| **`HttpSession`** | Java/Spring app and browser | Maintains the web app's `SecurityContext`. | The CAS Server callback does not carry this browser cookie. |

**A single login flow can involve an ST, PGT IOU, PGT, and subsequent PTs, yet none are interchangeable.** Prefixes like `PGT-` and `PGTIOU-` are merely formatting conventions, not cryptographic signatures or proof of trust.

## 3. Two CAS Channels That Must Be Combined

### 3.1. Overall Flow

~~~text
Browser                 Portal A / CAS Client                 CAS Server
   |                             |                                 |
   | GET /login/cas?ticket=ST-1 |                                 |
   |---------------------------->|                                 |
   |                             | HTTPS /serviceValidate           |
   |                             | ticket=ST-1                       |
   |                             | service=https://portal.../login/cas
   |                             | pgtUrl=https://portal.../proxyreceptor
   |                             |-------------------------------->|
   |                             |                                 | validate ST
   |                             |                                 | mint PGT-1 and PGTIOU-1
   |                             |<------ HTTPS GET pgtUrl --------|
   |                             |        pgtId=PGT-1              |
   |                             |        pgtIou=PGTIOU-1           |
   |                             |                                 |
   |                             | storage.save(PGTIOU-1, PGT-1)    |
   |                             |-------- HTTP 200 -------------->|
   |                             |                                 |
   |                             |<----- validation response ------|
   |                             |    cas:user=alice                |
   |                             |    proxyGrantingTicket=PGTIOU-1 |
   |                             |                                 |
   |                             | storage.retrieve(PGTIOU-1)       |
   |                             |   -> PGT-1                       |
   |                             | CAS Assertion alice + PGT-1     |
   |<--- app session ------------|                                 |
   |                             |                                 |
   |   When app needs API B:     |                                 |
   |                             | GET /proxy?pgt=PGT-1             |
   |                             |     &targetService=API-B         |
   |                             |-------------------------------->|
   |                             |<---------- PT-for-B ------------|
   |                             |                                 |
   |                             | --- PT-for-B ---> API B           |
   |                             |          API B validates PT with CAS
~~~

**Ordering matters:** per **CAS Protocol §2.5.4**, the CAS Server calls the callback and waits for HTTP 200 before returning the validation response **containing PGT IOU**. Thus in the standard synchronous flow, the callback does not “arrive after” the validation response by protocol rules. However, in multi-node software, **inconsistent Redis writes, asynchronous handling, timeouts, or retries** can prevent the IOU reader from seeing the PGT just ACKed by the callback. Your design must guarantee read-after-write rather than relying on arbitrary delays.

### 3.2. How Does the CAS Server Receive the PGT Request?

In the validation request, the client sends the exact parameters:

~~~http
GET /cas/serviceValidate?service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas&ticket=ST-1-example&pgtUrl=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas%2Fproxyreceptor HTTP/1.1
Host: sso.example.org
Accept: application/xml
~~~

This is illustrative: the CAS Server validates the one-time ticket, exact `service`, and a server-permitted **HTTPS** `pgtUrl` callback. When running CAS 3.0 with attributes, the endpoint may be `/p3/serviceValidate`. When receiving a PT and validating a proxy chain, use `/proxyValidate` or `/p3/proxyValidate` per your CAS client/server.

`pgtUrl` is a **server-side configured URL**, never an arbitrary browser-supplied value. The CAS Server checks the callback endpoint's certificate (at minimum PKIX/hostname/certificate trust) and reachability before delivering the PGT.

### 3.3. Callback Receives the Real PGT

The CAS Server sends an HTTPS GET to the callback:

~~~http
GET /login/cas/proxyreceptor?pgtId=PGT-1-example&pgtIou=PGTIOU-1-example HTTP/1.1
Host: portal.example.org
~~~

The application receives two distinct parameters:

- **`pgtId`**: the real PGT, a secret credential.
- **`pgtIou`**: an unpredictable correlation handle issued by CAS, from which the PGT cannot be derived.

Only after protecting the caller source per security architecture and **persisting the IOU → PGT pair successfully** does the callback return **HTTP 200**. Never return the PGT value in the response body or redirect it to the browser. If the storage write fails, never ACK 200 first and “write asynchronously later”—CAS would assume the callback succeeded.

**Distinguish both TLS directions:** The CAS Server verifies the callback's HTTPS certificate so it knows it is handing the PGT to the right app, but **the app's server certificate does not authenticate the caller hitting the receptor**. To prevent callback injection, the endpoint needs appropriate inbound trust controls—such as mTLS (where supported) or strict source/gateway controls—plus rate limiting and safe input validation. Never trust a client-set `X-CAS-Server` header.

### 3.4. Validation Response Delivers Only the PGT IOU

CAS may return:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxyGrantingTicket>PGTIOU-1-example</cas:proxyGrantingTicket>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

The application takes the **IOU from the XML response of the trusted CAS Server**, calls `storage.retrieve("PGTIOU-1-example")`, and receives `PGT-1-example`. **Never send PGT IOU to CAS `/proxy` in place of the real PGT.** Never take `cas:user` from the callback, because the callback carries only PGT and IOU.

If CAS does not emit `proxyGrantingTicket`, there is no basis to confirm a PGT for that validation. Possible causes include an unreachable callback, certificate failure, non-200 receptor response, proxy disallowed by server, misconfiguration, or CAS Server running a different profile. **Never fall back to a previous session's PGT.**

## 4. Why Is PGT IOU the Security Linchpin?

Suppose two ST requests are validated nearly simultaneously:

~~~text
Ticket ST-A -> CAS user alice -> CAS generates PGT-A / PGTIOU-A
Ticket ST-B -> CAS user bob   -> CAS generates PGT-B / PGTIOU-B

CAS callbacks:
  (PGTIOU-B, PGT-B) arrives first
  (PGTIOU-A, PGT-A) arrives second

CAS validation responses:
  ST-A -> user alice + PGTIOU-A
  ST-B -> user bob   + PGTIOU-B

Correct outcome:
  Alice gets only PGT-A
  Bob   gets only PGT-B
~~~

A flawed algorithm:

~~~text
latestPgt = PGT-B
login(alice) -> attach latestPgt
~~~

leads to **delegation on behalf of Bob while the app session belongs to Alice**. Even two browser logins sharing the same username do not guarantee interchangeable PGTs, as CAS sessions, entitlements, and service contexts may differ.

**Correlation invariants:**
1. Never correlate by username, email, session ID, or latest timestamp.
2. Accept IOUs only from a **trusted CAS ticket validation response**.
3. Use only the PGT stored by the receptor under that **exact IOU**, within the matching CAS/environment/service namespace.
4. Correlate once and bind to the **exact CAS Assertion**.
5. When the IOU is missing, expired, duplicated/conflicting, or storage is down, **grant no proxy capability**.
6. Never equate “CAS login success” with “PGT acquisition success”; application policy should keep the two outcomes distinct.

## 5. `ProxyGrantingTicketStorage` in Apereo Java CAS Client

In the Java CAS Client, **`org.apereo.cas.client.proxy.ProxyGrantingTicketStorage`** defines the contract for temporarily storing PGTs by IOU. Its methods are:

~~~java
void save(String proxyGrantingTicketIou,
          String proxyGrantingTicket);

String retrieve(String proxyGrantingTicketIou);

void cleanUp();
~~~

These are **illustrative library API signatures**, not a standalone JDK class. When using Spring Security CAS, the callback receiver in `CasAuthenticationFilter` saves the PGT, while `Cas20ProxyTicketValidator` or `Cas30ProxyTicketValidator` retrieves the PGT while reading the CAS validation result.

| API | Purpose | Invariant to Uphold |
| --- | --- | --- |
| `save(iou,pgt)` | Writes the pair when the receptor receives a callback. | One IOU must never be overwritten by a different PGT. |
| `retrieve(iou)` | Fetches the PGT that the CAS Server paired with the response's IOU. | Consumed at most once per storage policy. |
| `cleanUp()` | Purges orphaned or expired entries. | Never let unconsumed PGTs accumulate endlessly in RAM/Redis. |

**The historical `ProxyGrantingTicketStorageImpl` has retrieve-and-remove semantics:** calling `retrieve` **deletes the temporary mapping** upon returning the PGT. This single-use behavior applies to the **IOU lookup**, **not** to the PGT itself. Per the CAS Protocol, one PGT can request multiple PTs until revoked or expired by the CAS Server.

### 5.1. Temporary Storage vs. Session-Bound PGT Storage

At callback time:

~~~text
Temporary:
  PGTIOU-1 -> PGT-1
~~~

After trusted validation:

~~~text
CAS Assertion:
  principal = alice
  verified ST/service = ST-A / Portal
  proxy capability uses PGT-1

Temporary IOU mapping:
  removed
~~~

Once correlated, the PGT must be protected across the lifecycle of the **exact principal/CAS Assertion**. With properly configured Spring/Apereo CAS Client APIs, the principal/assertion provides `getProxyTicketFor(targetService)` to request PTs, rather than the application sending PGTs to the frontend.

Never store PGTs in `localStorage`, include them in browser JSON responses, serialize raw secrets into audit logs, or let every service read a shared PGT Redis store. When persisting PGTs, encrypt at rest and restrict read access.

### 5.2. Callbacks Can Arrive Without Any Local Session

The CAS Server calls the backend receptor without any **browser `JSESSIONID`**. Therefore never write:

~~~text
GET /proxyreceptor?pgtId=PGT-1&pgtIou=PGTIOU-1
  -> request.getSession().getAttribute("currentUser")
  -> save PGT under currentUser
~~~

That fails with a missing or wrong session because there is no browser request context. **IOU exists specifically to join two independent server-side paths.** The receptor only stores the temporary pair; it never creates an `Authentication`, `SecurityContext`, cookie, or user login.

## 6. Spring Security Configuration: Sharing One Store

Components that must be wired together properly:

- `CasAuthenticationEntryPoint`: redirects browsers to CAS login with the service URL.
- `ServiceProperties`: defines the **service callback URL** (typically `https://portal.example.org/login/cas`).
- `CasAuthenticationFilter`: receives STs from the browser and PGT callbacks from the CAS Server at `proxyReceptorUrl`.
- `CasAuthenticationProvider`: validates STs via `TicketValidator` and maps CAS users to local accounts.
- `Cas20ProxyTicketValidator` or `Cas30ProxyTicketValidator`: configures **`proxyCallbackUrl`** and **`proxyGrantingTicketStorage`**.
- `ProxyGrantingTicketStorage`: the **same logical store** for both filter and validator.

### 6.1. Three URLs That Must Never Be Confused

| Name | Illustrative URL | Role |
| --- | --- | --- |
| CAS Server base URL | `https://sso.example.org/cas` | Validator calls `/serviceValidate` or `/proxyValidate`. |
| `ServiceProperties.service` | `https://portal.example.org/login/cas` | Browser callback carrying ST; URL bound by CAS to the ST. |
| `proxyCallbackUrl` | `https://portal.example.org/login/cas/proxyreceptor` | **CAS Server** sends PGT + IOU here over HTTPS. |

**`proxyReceptorUrl`** on the filter is usually an internal path like `/login/cas/proxyreceptor`, whereas **`proxyCallbackUrl`** is the complete HTTPS URL reachable by the CAS Server. When an app uses a context path like `/portal`, the full callback URL must include that context path, while the filter receptor path depends on servlet mapping configuration. Verify ingress/reverse proxy rules and the service registry for your environment.

### 6.2. Illustrative Java Configuration

In a **Spring Boot Servlet project** with version-compatible `spring-security-cas` and `cas-client-core`, the beans centered on PGT storage can be structured as follows:

~~~java
package example.cas;

import org.apereo.cas.client.proxy.ProxyGrantingTicketStorage;
import org.apereo.cas.client.proxy.ProxyGrantingTicketStorageImpl;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;
import org.apereo.cas.client.validation.TicketValidator;
import org.springframework.authentication.AuthenticationManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.cas.web.CasAuthenticationFilter;

@Configuration
public class CasPgtConfiguration {

    @Bean
    ProxyGrantingTicketStorage pgtStorage() {
        return new ProxyGrantingTicketStorageImpl();
    }

    @Bean
    TicketValidator ticketValidator(
            ProxyGrantingTicketStorage pgtStorage) {

        Cas20ProxyTicketValidator validator =
            new Cas20ProxyTicketValidator(
                "https://sso.example.org/cas");
        validator.setProxyCallbackUrl(
            "https://portal.example.org/login/cas/proxyreceptor");
        validator.setProxyGrantingTicketStorage(pgtStorage);
        return validator;
    }

    @Bean
    CasAuthenticationFilter casAuthenticationFilter(
            AuthenticationManager manager,
            ProxyGrantingTicketStorage pgtStorage) {

        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setAuthenticationManager(manager);
        filter.setProxyReceptorUrl("/login/cas/proxyreceptor");
        filter.setProxyGrantingTicketStorage(pgtStorage);
        return filter;
    }
}
~~~

This is a **partial Spring configuration** and **not a complete `javac`-compilable application**. You must add `CasAuthenticationProvider`, `ServiceProperties`, `CasAuthenticationEntryPoint`, `AuthenticationManager`, registering the filter inside the right `SecurityFilterChain`, a local `UserDetailsService`, CAS service registry entries, and TLS. The in-memory storage example suits single-node testing only; multi-node production deployments must supply a shared storage implementation.

**Import note:** In current releases, Spring Security's `AuthenticationManager` resides in **`org.springframework.security.authentication.AuthenticationManager`**, not `org.springframework.authentication`. When adapting this snippet to a project, use the standard imports of your actual dependencies and verify the CAS module setters for your version. Since this is an illustrative configuration fragment, run compilation and integration tests in your real project.

Every callback receiver and ticket validator path must share **the exact same `pgtStorage` bean**. If two beans create two separate instances, `save` and `retrieve` will never meet, even inside a single JVM.

### 6.3. Provider and Service URL Are Still Required

Model:

~~~text
CasAuthenticationProvider:
  ticketValidator -> proxy-aware validator
  serviceProperties.service -> https://portal.example.org/login/cas
  userDetailsService / account mapper -> local user
  key -> stable provider identity

CasAuthenticationFilter:
  browser ST callback -> /login/cas
  CAS PGT receptor -> /login/cas/proxyreceptor
  proxyGrantingTicketStorage -> shared store

CAS TicketValidator:
  CAS base URL -> https://sso.example.org/cas
  proxyCallbackUrl -> HTTPS callback full URL
  proxyGrantingTicketStorage -> same shared store
~~~

`CasAuthenticationProvider#setKey` is not a ticket signing secret. Security still relies on CAS Server ticket validation, TLS, service binding, PGT storage, and local authorization.

### 6.4. Service Validator or Proxy Validator?

If the application only performs **web login** and needs no PGT, `Cas20ServiceTicketValidator` or `Cas30ServiceTicketValidator` is usually sufficient. When CAS must issue a PGT for proxying, Spring Security docs instruct using `Cas20ProxyTicketValidator` with `proxyCallbackUrl` and shared storage; for CAS3 attributes with the proxy protocol, `Cas30ProxyTicketValidator` may be considered where supported.

**Distinguish two roles:** App A **receiving a PGT to call B** versus App B **receiving a proxy ticket and evaluating the proxy chain**. Backend B must use CAS `/proxyValidate`/`/p3/proxyValidate` and **accept only approved proxy chains**, never enabling `acceptAnyProxy=true` just to “make errors go away.”

## 7. From Correlated PGT to Backend B's Proxy Ticket

Once the provider authenticates and attaches the PGT to the CAS Assertion, App A can request a PT for service B. Spring Security documentation illustrates this pattern:

~~~java
// Code fragment inside a handler with an authenticated CAS Authentication.
CasAuthenticationToken authentication =
    (CasAuthenticationToken)
        SecurityContextHolder.getContext().getAuthentication();

String targetService = "https://reports.example.org/api/report";
String pt = authentication.getAssertion()
        .getPrincipal()
        .getProxyTicketFor(targetService);
~~~

This is a **Java snippet inside a Spring project**, not standalone Java SE. A properly proxy-enabled CAS principal/Assertion is required; if the IOU was missing or the PGT is no longer valid, the PT request must never be assumed to succeed by default.

CAS proxy transaction:

~~~http
GET /cas/proxy?pgt=PGT-1-example&targetService=https%3A%2F%2Freports.example.org%2Fapi%2Freport HTTP/1.1
Host: sso.example.org
~~~

CAS returns a PT bound specifically to service B; A sends the PT to B, and B calls CAS proxy validation to verify the PT, service, and proxy chain before allowing API access. **Never pass the PGT directly to API B**, never reuse A's old ST, and never replay an already-validated PT: a PT allows a single validation attempt. Because the CAS protocol may put the PGT in `/proxy` query strings, ticket redaction is mandatory in reverse proxies, server access logs, and APM.

Even when the backend receives a valid PT, it must still verify tenant, resource ownership, action permissions, and account lock status. **Proxy authentication does not replace authorization.**

## 8. Race Conditions and Multi-Node Deployments

### 8.1. Rare Edge Cases That Cause Major Outages

| Scenario | Cause | Remediation |
| --- | --- | --- |
| Receptor Node A returns 200, validator Node B's IOU lookup misses. | No shared store, local HashMap, or replication lag. | Single shared store, read-after-write, ACK only after commit. |
| Two callbacks share an IOU with different PGTs. | Abnormal retry, misconfiguration, or injection. | Reject conflict; never overwrite the mapping. |
| Validation response arrives, then ST validation retries. | ST already consumed; retry violates protocol. | Start a fresh login/validation per policy; never reuse ST. |
| Orphaned PGT callback (never retrieved). | Validation timeout/crash, restart, or dropped response. | TTL and cleanup; monitor/audit orphan counts. |
| Receptor requires a browser session. | CAS backend carries no browser cookies. | Store temporarily by IOU; bind principal after ticket validation. |
| Multiple users share a username across tickets. | Keying PGTs by username. | Correlate strictly by IOU; never use “latest PGT.” |
| Scanner hits callback with forged data. | Endpoint lacks inbound trust protection. | mTLS/gateway policy, anti-injection, rate limits, input validation. |
| Redis/SQL store times out. | Cannot prove IOU matches a PGT. | **Fail closed** on proxy capability; never fall back to an old PGT. |
| Local session locked after PGT issuance. | PGT lifetime outlives local session. | Revocation/status checks and CAS logout integration. |

### 8.2. Why ACK Only After Successful Persistence?

~~~text
CAS Server -> GET receptor on Node A
Node A -> enqueues Redis write and returns 200 immediately
CAS Server -> sends validation XML with PGTIOU to Node B
Node B -> Redis GET PGTIOU -> MISS
~~~

That is “ACK first, durability later.” Never patch it with a fixed `Thread.sleep`. The receptor must return 200 **after** storage satisfies the required durability and consistency guarantees, or return an error otherwise. The CAS Server can refuse PGT issuance if the callback fails; that is far safer than minting an uncorrelatable credential.

### 8.3. Temporary Storage and Bound PGT Storage Have Different Lifecycles

| Store | Key | TTL | Responsibility |
| --- | --- | --- | --- |
| Temporary callback mapping | Namespace + **PGT IOU** | Short, just for the validation transaction | `save`, `retrieve-and-remove`, orphan cleanup. |
| PGT bound to CAS Assertion | Principal/session/account ref with proof | Matches CAS session/PGT lifetime and app policy | Issue PTs only for approved targets; revoke when needed. |
| PT calling Backend B | Target service B | Very short, single validation | Backend validates with CAS and checks proxy chain. |

A PGT can outlive the temporary IOU mapping after a successful `retrieve`, but must never outlive CAS Server/application policy limits. In particular, **CAS logout or TGT destruction typically invalidates associated PGTs** per protocol; applications should also actively revoke or stop using proxy capabilities if the local account is disabled.

## 9. Runnable Java 17: Joining Two Halves by IOU, Conflict Blocking, and TTL

This program compiles standalone on **Java 17** with no Spring or Apereo dependencies. It simulates only the two arrivals **after** callback and CAS validation data have already passed earlier trust layers. The demo **does not verify signatures, tickets, TLS, or caller identity**, does not implement Redis, and must never be used directly as a public controller.

File `PgtIouJoinDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class PgtIouJoinDemo {
    record Callback(String pgt, Instant when) {}
    record Validation(String principal, String service, Instant when) {}
    record Bound(String principal, String service, String pgt) {}

    static final class Store {
        private final Map<String, Callback> callbacks = new HashMap<>();
        private final Map<String, Validation> validations = new HashMap<>();
        private final Set<String> consumed = new HashSet<>();
        private final Set<String> blocked = new HashSet<>();
        private final Duration ttl = Duration.ofSeconds(60);

        // Caller must verify the CAS callback origin before invoking this method.
        synchronized String callback(String iou, String pgt, Instant now) {
            if (iou == null || !iou.startsWith("PGTIOU-")
                    || pgt == null || !pgt.startsWith("PGT-")) {
                return "BAD_CALLBACK";
            }
            if (consumed.contains(iou) || blocked.contains(iou)) {
                return "CLOSED";
            }
            Callback old = callbacks.putIfAbsent(iou, new Callback(pgt, now));
            if (old != null) {
                if (!Objects.equals(old.pgt(), pgt)) {
                    blocked.add(iou);
                    callbacks.remove(iou);
                    validations.remove(iou);
                    return "CALLBACK_CONFLICT";
                }
                return "DUPLICATE_CALLBACK";
            }
            return "CALLBACK_STORED";
        }

        // Caller must verify ticket + CAS validation response first.
        synchronized String validated(String iou, String principal,
                                      String service, Instant now) {
            if (iou == null || !iou.startsWith("PGTIOU-")
                    || principal == null || principal.isBlank()
                    || service == null || service.isBlank()) {
                return "BAD_VALIDATION";
            }
            if (consumed.contains(iou) || blocked.contains(iou)) {
                return "CLOSED";
            }
            Validation old = validations.putIfAbsent(
                    iou, new Validation(principal, service, now));
            if (old != null) {
                if (!old.principal().equals(principal)
                        || !old.service().equals(service)) {
                    blocked.add(iou);
                    callbacks.remove(iou);
                    validations.remove(iou);
                }
                return "DUPLICATE_VALIDATION";
            }
            return "VALIDATION_STORED";
        }

        synchronized Bound take(String iou, Instant now) {
            if (consumed.contains(iou) || blocked.contains(iou)) {
                return null;
            }
            Callback callback = callbacks.get(iou);
            Validation validation = validations.get(iou);
            if (callback == null || validation == null) {
                return null;
            }
            boolean expired = now.isBefore(callback.when())
                    || now.isBefore(validation.when())
                    || now.isAfter(callback.when().plus(ttl))
                    || now.isAfter(validation.when().plus(ttl));
            consumed.add(iou);
            callbacks.remove(iou);
            validations.remove(iou);
            if (expired) {
                return null;
            }
            return new Bound(validation.principal(), validation.service(),
                             callback.pgt());
        }
    }

    static String display(Bound bound) {
        // Never print the PGT to logs/stdout.
        return bound == null ? "NOT_LINKED" : "LINKED:" + bound.principal();
    }

    public static void main(String[] args) {
        Store store = new Store();
        Instant t = Instant.parse("2026-11-07T03:00:00Z");

        // CAS callback arrives before validation response (standard flow).
        System.out.println(store.callback("PGTIOU-A", "PGT-A", t));
        System.out.println(store.validated("PGTIOU-A", "alice",
                "https://portal.example.org/login/cas", t.plusSeconds(1)));
        System.out.println(display(store.take("PGTIOU-A", t.plusSeconds(2))));
        System.out.println(display(store.take("PGTIOU-A", t.plusSeconds(3))));

        // Processing observes validation before callback.
        System.out.println(store.validated("PGTIOU-B", "bob",
                "https://portal.example.org/login/cas", t));
        System.out.println(store.callback(
                "PGTIOU-B", "PGT-B", t.plusSeconds(1)));
        System.out.println(display(store.take("PGTIOU-B", t.plusSeconds(2))));

        // Missing one half or callback expired.
        System.out.println(display(store.take("PGTIOU-UNKNOWN", t)));
        store.callback("PGTIOU-C", "PGT-C", t);
        store.validated("PGTIOU-C", "carol",
                "https://portal.example.org/login/cas", t);
        System.out.println(display(store.take("PGTIOU-C", t.plusSeconds(61))));

        // Two different PGTs for the same IOU: conflict, never overwrite.
        store.callback("PGTIOU-D", "PGT-D1", t);
        System.out.println(store.callback(
                "PGTIOU-D", "PGT-D2", t.plusSeconds(1)));
        System.out.println(store.validated("PGTIOU-D", "dave",
                "https://portal.example.org/login/cas", t.plusSeconds(2)));
        System.out.println(display(store.take("PGTIOU-D", t.plusSeconds(3))));
    }
}
~~~

Compile and run:

~~~bash
javac PgtIouJoinDemo.java
java PgtIouJoinDemo
~~~

**Exact stdout:**

~~~text
CALLBACK_STORED
VALIDATION_STORED
LINKED:alice
NOT_LINKED
VALIDATION_STORED
CALLBACK_STORED
LINKED:bob
NOT_LINKED
NOT_LINKED
CALLBACK_CONFLICT
CLOSED
NOT_LINKED
~~~

Explanation: A correlates with its own PGT and cannot consume the IOU twice; B simulates out-of-order arrivals across handlers; unknown/expired IOUs fail to link; a conflicting callback with a different PGT marks a conflict rather than arbitrarily binding a PGT to Dave.

**Limitations:** `synchronized` is atomic only within a single JVM. Production needs `save-if-absent`, TTLs, and **atomic take** in Redis/SQL or an equivalent adapter, namespaced by CAS Server/environment/service, with PGT encryption at rest, cardinality limits, and source checks on both halves before joining. The demo retains `consumed/blocked` sets without periodic pruning, making it suitable for instruction only. The `PGT-` strings in code are dummy values, not real credentials.

## 10. Designing Secure Shared Storage

Logical diagram:

~~~text
CAS Server
    |
    +-- callback HTTPS --> Ingress --> Node A
    |                                    |
    |                                    v
    |                              PGT shared store
    |                          IOU -> encrypted PGT + TTL
    |                                    ^
    |                                    |
    +-- validation XML --> Node B -------+
                                         |
                                  atomic retrieve
                                         |
                               CAS Assertion exact principal
                                         |
                               request PT for allowed backend
~~~

Requirements:

1. **One logical storage across all pods**: callbacks on A and validators on B still find the right IOU.
2. **ACK 200 only after durable/readable write**: avoid Redis replica lag or fire-and-forget async writes.
3. **Atomic consume**: e.g., a primitive equivalent to Redis `GETDEL` or an SQL transaction; never separate `GET` and `DEL` non-atomically if two consumers can race.
4. **Never overwrite duplicates**: an IOU arriving with a different PGT is a security conflict—audit and refuse.
5. **Short mapping TTL**: unretrieved callbacks must be cleaned up; never leave orphans indefinitely.
6. **Encrypt PGTs**: AES-GCM/KMS or an access-controlled vault; never place raw PGTs in cache keys, logs, or ordinary queues.
7. **Namespacing**: by environment, CAS issuer/server, and service identity; never mix staging/prod or two CAS Servers.
8. **Rate limiting and input validation**: the receptor can face stray requests or DoS; never rely solely on PGT prefixes.
9. **Fail closed** on store timeouts or failure to prove an IOU match.
10. **Lifecycle**: bound PGTs must be revoked/unused when the CAS TGT expires/logs out, the local account is disabled, or the app revokes proxy permissions.
11. **Observability**: metrics for callback latency, missing/orphan/conflict IOU counts, and successful association rates—never log secrets.
12. **Protect backups/snapshots**: ensure Redis dumps or SQL backups cannot leak PGTs.

If callbacks are blocked by Spring authorization or CSRF matchers, configure an exception **strictly for the CAS receptor path** while enforcing inbound trust via gateway/mTLS—never disable CSRF across the entire web application. The callback is a server-to-server request; never route it through a browser-session form login flow.

## 11. Direct/Encrypted PGT Is a Different Mechanism from IOU Callbacks

Some **Apereo CAS Server** configurations support returning the **PGT directly in the validation response** as an attribute encrypted with the service's public key. When that variant is active, there may be **no PGT IOU or `pgtUrl` callback**. That is not “standard CAS callbacks automatically falling back to returning the PGT” when storage breaks.

| Model | Validation Response | Callback Receptor | What Does the Application Need? |
| --- | --- | --- | --- |
| **Standard CAS Proxy callback** | `proxyGrantingTicket=PGTIOU` | GET `pgtId=PGT` + `pgtIou=PGTIOU` | Shared `ProxyGrantingTicketStorage`, lookup by IOU. |
| **CAS extension direct encrypted PGT** | PGT in dedicated profile/attribute, typically encrypted | No IOU callback | Proper public/private key configuration and decryption/validation policy support. |

**Never mix the two profiles.** When PGTIOU is missing, check the server/client mode before assuming an error. Never blindly treat a `proxyGrantingTicket` string as a bearer PGT without verifying which profile is active.

## 12. Common Errors and Diagnostics

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| CAS login succeeds but API proxying fails. | Failed to acquire PGT despite valid ST; or PT/backend authorization denied. | Separate login success from proxy capability success. |
| Validation response lacks PGTIOU. | `pgtUrl` omitted, HTTPS/cert error, proxy disallowed in service registry, callback returned non-200. | Inspect callback outcome and CAS config without exposing tickets. |
| CAS callback 404. | Public `proxyCallbackUrl` mismatches `proxyReceptorUrl`/context path. | Align ingress routing and filter mapping. |
| CAS callback 401/403. | Receptor demands browser login/CSRF, or gateway policy blocks it. | Exact-path exception + inbound trust; never open the whole app. |
| Receptor returns 200 yet validator finds no PGT. | Two storage instances, multi-node local memory, replication lag, TTL. | Shared store and read-after-write; ACK after commit. |
| Duplicate IOU succeeds with a different PGT. | Unsafe overwrite. | Reject conflicts; atomically preserve or invalidate. |
| ST `INVALID_TICKET`. | ST already validated, expired, or wrong CAS Server. | Never retry the same ST indefinitely. |
| ST `INVALID_SERVICE`. | Service URL differs from when CAS minted the ticket; reverse proxy HTTPS mismatch. | Compare `ServiceProperties.service` and CAS registry. |
| Backend PT `INVALID_SERVICE`. | `targetService` at PT request mismatches `service` at backend validation. | Canonicalize service IDs and test end-to-end. |
| Backend rejects PT proxy chain. | Proxied via an unapproved service. | Verify allowlisted proxy chain; never enable acceptAnyProxy indiscriminately. |
| PGT invalid when calling `/proxy`. | CAS TGT/logout, PGT expiration/revocation, or wrong server. | Re-acquire through the proper flow; never substitute another PGT. |
| PGTIOU missing only on one node. | Local registry or shared cache consistency issue. | Multi-node integration test and shared storage. |
| HTTP access logs contain `pgtId` or `pgt`. | Gateway/APM logs raw query strings. | Redact and enforce secret controls. |
| Receptor hit with forged callbacks. | Unprotected caller source, IOU-only checking. | mTLS/gateway controls, audit, rate limiting. |
| Direct encrypted PGT enabled yet IOU lookup always misses. | Different mode active. | Check profile and CAS Client support. |

### 12.1. Safe Auditing and Metrics

Suggested format:

~~~text
event=CAS_PGT_IOU_CORRELATION
timestamp=2026-11-07T03:00:00Z
cas_server_ref=cas-primary
service_ref=portal
iou_ref=HMAC(PGTIOU)
callback_persisted=true
validation_received=true
result=MATCHED
consumed_once=true
proxy_target_ref=reports-api
~~~

This is an illustrative audit schema, not Spring Security's built-in log format. **Never log raw PGTs, IOUs, STs/PTs, browser cookies, full CAS validation responses, or sensitive usernames** into broadly accessible logs. Since CAS passes PGTs in callback/`/proxy` query strings, scrub logs across reverse proxies, WAFs, APM, tracing, and backends.

## 13. Pre-Production Test Suite

| Test | Expected Outcome |
| --- | --- |
| Valid ST + HTTPS callback URL with valid cert. | CAS callback stores IOU→PGT and validation response returns matching IOU. |
| Callback A and validation A share the same IOU. | Retrieves exact PGT-A and binds it to Assertion A. |
| Callback A arrives while response B carries a different IOU. | Never links A to B. |
| Two users log in concurrently with reversed callback order. | Correlated independently by IOU, never by username. |
| Callback hits Node A, validation hits Node B. | Shared store reads the same mapping. |
| Callback ACKs 200 before Redis persistence fails. | Test catches the contract violation; must not report success before persisting. |
| Two callbacks send different PGTs for the same IOU. | Rejects conflict; never overwrites. |
| Identical callback resent. | Idempotency/replay policy prevents double binding. |
| Validator retrieves the same IOU twice. | Only the first retrieval yields the mapping. |
| IOU expired or absent from store. | Grants no PGT; cleans up state. |
| CAS Server cannot reach receptor. | No proxy capability granted; failure handled cleanly. |
| Bad callback certificate or non-HTTPS. | CAS Server refuses to send PGT. |
| Callback sent by browser or attacker. | Neither writes unauthorized PGT nor creates an authenticated session. |
| Already-used ST sent twice. | CAS Server rejects replay. |
| ST issued for service A sent to service B. | Wrong-service validation fails. |
| Revoked PGT. | CAS `/proxy` refuses to issue PT. |
| PT for B presented to service C. | CAS proxy validation rejects target mismatch. |
| PT traverses an unknown proxy chain. | Backend rejects. |
| Local account locked despite valid CAS ticket. | Proxy capability cannot bypass the lock. |
| Storage unavailable. | Fails closed; never falls back to “latest” PGT. |
| Server enables direct PGT extension. | Follows that variant without requiring an IOU callback. |
| Backend B receives valid PT. | Still enforces role, tenant, and resource permissions. |

**Unit tests** in the Java demo check only IOU/TTL/replay mapping; they do not prove HTTPS, the CAS Protocol, CAS Server service registration, callback trust, local account mapping, or proxy authorization. Run integration tests with a test CAS Server (real test ST/PGT/PTs), the Spring app behind a reverse proxy, and at least two nodes if deploying multi-node.

## 14. Conceptual Mistakes to Avoid

1. **PGTIOU is the PGT** — false; the IOU only looks up the PGT.
2. **The callback contains the username** — false; the principal comes from trusted ticket validation.
3. **The validation response contains the real PGT in the standard callback flow** — false; it contains the IOU.
4. **An IOU is fetched once, so the PGT cannot request a second PT** — false; PGTs have a separate lifecycle.
5. **Using `JSESSIONID` to match callbacks** — false; CAS backend calls carry no browser session.
6. **Matching by user/email or latest timestamp** — false; easily cross-wires concurrent transactions.
7. **Callbacks arrive after the validation response per CAS spec** — false for the standard synchronous callback flow; understand that callback 200 precedes the IOU response.
8. **The receptor may return 200 before persisting** — false; creates false positives.
9. **Enabling `acceptAnyProxy=true` fixes storage bugs** — false; weakens proxy trust.
10. **One HashMap per node counts as shared storage** — false; multi-node requires a shared backend.
11. **A PGT can be sent to the frontend for session storage** — false; a PGT is a sensitive bearer credential.
12. **If CAS Server trusts the receptor cert, the receptor automatically trusts callers** — false; inbound caller trust is separate.
13. **Seeing `PGT-` proves a real credential** — false; it must come via a trusted CAS channel.
14. **Holding a PGT authorizes every API** — false; PT target services and backend authorization still apply.
15. **If PGT fails, revalidate the old ST** — false; STs are single-use.
16. **Missing IOU always means callback failure** — not necessarily; the server may use the direct PGT extension.
17. **Local logout guarantees CAS TGT/PGT and API sessions are all destroyed** — false; explicit lifecycle/revocation design is required.

## 15. Implementation Checklist

1. Is there a genuine requirement for Portal to request PTs for a backend, with a defined backend proxy chain policy?
2. Is `ServiceProperties.service` exact and identical to the public HTTPS URL CAS uses to issue STs?
3. Is the CAS Server configured for proxying and trusting the HTTPS `pgtUrl`/certificate/hostname?
4. Do the `proxyReceptorUrl` path and full `proxyCallbackUrl` align across ingress and context paths?
5. Do the validator and filter share the same logical `ProxyGrantingTicketStorage` across all nodes?
6. Does the receptor ACK 200 only after persisting IOU→PGT, with caller source protections?
7. Are IOUs taken strictly from trusted validation results rather than browser queries or usernames?
8. Is PGT lookup by IOU single-use, resistant to duplicate/conflict overwrites, and backed by TTL/cleanup?
9. Does shared storage provide atomic take, read-after-write, and fail-closed error handling?
10. Are real PGTs kept secret, encrypted at rest, and excluded from logs and browser responses?
11. Is the looked-up PGT bound to the exact CAS Assertion/principal and never leaked to another session?
12. Are CAS session/PGT lifetimes and local account revocations properly enforced?
13. Are backend `targetService`, single-use PTs, and proxy chain allowlists strictly enforced?
14. Do integration tests cover callback network/certificates, multi-node, concurrent users, replay, and outages?
15. If CAS uses direct encrypted PGTs, is that profile explicitly selected without mixing with IOU callbacks?

## References

- [Apereo CAS Protocol Specification — §2.5.4 Proxy Callback, §3.3 PGT, §3.4 PGT IOU, and §2.7 Proxy Ticket](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Spring Security — CAS Authentication, Configuring CAS to Obtain Proxy Granting Tickets](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Apereo Java CAS Client — Proxy Receptor and Proxy Granting Ticket Storage](https://github.com/apereo/java-cas-client/blob/master/README.md)
- [Apereo CAS — Proxy Authentication and Direct PGT Variant](https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html)
- [Apereo CAS Protocol Overview](https://apereo.github.io/cas/development/protocol/CAS-Protocol.html)
- [Spring Security API — CasAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html)
- [Spring Security API — CasAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html)

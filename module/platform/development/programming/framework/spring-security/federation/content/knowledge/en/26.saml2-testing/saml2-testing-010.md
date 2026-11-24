# Testing RelayState, Session Loss, and Two Concurrent Login Flows

In a **Spring Security SAML2 Service Provider (SP)**, a validly signed `SAMLResponse` may still have to be rejected if the application **cannot recover the original `AuthnRequest`**, the browser omits the session cookie when the IdP POSTs back to the ACS, `RelayState` is tampered with, or **two tabs concurrently initiate SSO** and overwrite pending request state.

This article guides you through designing and testing three failure groups commonly mistaken for an "unstable IdP":

1. **`RelayState`** tampered, missing, duplicated, confused with `InResponseTo`, or abused as an open redirect.
2. **Session loss** due to `SameSite` cookies, session TTL, logout, session rotation, reverse proxies, or multiple SP nodes.
3. **Two concurrent login flows** in the same session: `AuthnRequest` A/B, out-of-order responses, repository overwrites, race conditions, and replay.

**Security principle:** every response must be verified against the right IdP registration, signature, issuer, audience, recipient, timestamps, subject confirmation, and required correlation. A flow that has lost correlation **must never silently downgrade into an IdP-initiated/unsolicited login**; if the repository cannot prove the flow is valid, **fail closed**.

This article belongs to **Spring Security – federation → SAML2 Testing**. It covers OASIS standard theory, Spring Security versions and repositories, Given–When–Then test design, a pure-JDK Java 17 runnable example, security test matrices, a runbook, and official references.

## 1. SAML SP-Initiated SSO Operates Across Two Halves of a Transaction

~~~text
Browser                          Spring SP                         IdP
  |                                 |                               |
  | GET /saml2/authenticate/corp    |                               |
  |-------------------------------->|                               |
  |                            AuthnRequest ID=REQ-A                |
  |                            RelayState=R-A                       |
  |                            Save pending request                 |
  |<----- Redirect with SAMLRequest + RelayState -------------------|
  |---------------------------------------------------------------->|
  |                                               Authenticate user |
  |<------------------------------- HTML form for ACS POST ---------|
  | POST /login/saml2/sso/corp       |                               |
  | SAMLResponse InResponseTo=REQ-A  |                               |
  | RelayState=R-A                  |                               |
  |-------------------------------->|                               |
  |                              Load pending                       |
  |                              Validate SAML                      |
  |                              One-time consume                   |
  |<------------------------ Local session + redirect -------------|
~~~

In Spring Security, `Saml2WebSsoAuthenticationRequestFilter` generates `AuthnRequest` and saves its state in `Saml2AuthenticationRequestRepository`. When the ACS receives the POST, `Saml2WebSsoAuthenticationFilter` and `Saml2AuthenticationTokenConverter` locate the matching registration/request, and then the OpenSAML provider validates the response.

**What to test:** verifying the SAML signature and recovering the pending login transaction are **two independent guarantees**. Never conclude a signature failed simply because `InResponseTo` lookup failed.

## 2. What Role Does RelayState Play?

**`RelayState`** is a parameter of SAML HTTP bindings, usually holding an **opaque handle** so the SP can link the callback to the original request's state and restore a safe post-login navigation target. The IdP normally echoes back the exact `RelayState` received alongside the `AuthnRequest`.

Illustrative request example:

~~~http
POST /login/saml2/sso/corp HTTP/1.1
Host: portal.example.test
Content-Type: application/x-www-form-urlencoded

SAMLResponse=BASE64_SIGNED_FIXTURE&RelayState=R-A
~~~

In this example, `BASE64_SIGNED_FIXTURE` is only a placeholder, **not a usable assertion**.

**`RelayState` is NOT**:
- A user ID or proof of authentication.
- SAML `Response.InResponseTo`.
- A JWT/OAuth token or session cookie.
- Proof that the IdP signed the form parameter outside the SAML XML.
- Proof that the current browser initiated the flow if looked up solely in a global cache.
- A trusted redirect URL merely because the IdP echoed it back.
- A tenant privilege or local `GrantedAuthority`.

Every use case must independently verify **server-side expected values**, integrity/correlation, and resource authorization.

## 3. OASIS Constraints on RelayState

Per OASIS SAML 2.0 Bindings for HTTP Redirect/POST, `RelayState` **must not exceed 80 bytes**, **should be integrity-protected**, and the responder must echo **the exact value** sent with the request per the applicable binding.

**80 bytes differs from 80 characters**: UTF-8 characters can span multiple bytes. Use short random ASCII/URL-safe tokens instead of stuffing JSON, long URLs, emails, or PII. Include test cases exceeding the byte limit solely due to Unicode.

**Note on signatures:** the XML signature on Response/Assertion **does not automatically protect the `RelayState` form field** outside the XML. HTTP Redirect binding defines a query-parameter signing mechanism covering `RelayState` when binding signatures are used; HTTP POST typically requires separate integrity/correlation controls. Never write tests assuming every `RelayState` is signed by the IdP.

## 4. How RelayState Differs from InResponseTo

| Field | Where it appears | Meaning |
| --- | --- | --- |
| `AuthnRequest.ID` | SP-generated request XML | Issued transaction ID |
| `RelayState` | HTTP query/form binding | State/return-target reference |
| `Response.InResponseTo` | `SAMLResponse` XML | Which `AuthnRequest` the Response answers |
| `SubjectConfirmationData.InResponseTo` | SAML Assertion | Binds bearer subject to the request |
| `Response.ID` / `Assertion.ID` | SAML XML | Replay detection |
| `Destination` | SAML Response | Intended response receiver |
| `Recipient` | `SubjectConfirmationData` | SP's ACS |
| `AudienceRestriction` | Assertion `Conditions` | Permitted SP `entityID` |

**Test invariant:** if `RelayState=R-A` while `InResponseTo=REQ-B`, **reject**, even if both have active pending records. Conversely, `InResponseTo=REQ-A` with `RelayState` swapped to `R-B` must never be paired arbitrarily.

**Never substitute one field for the other** simply because both look like IDs.

## 5. Structure of a Pending Authentication Request

A logical record should retain:

~~~text
PendingSamlLogin:
  opaque_relay_state = R-A
  authn_request_id   = REQ-A
  registration_id    = corp
  expected_idp       = urn:corp:idp
  expected_sp        = urn:portal:sp
  expected_acs       = https://portal.example.test/login/saml2/sso/corp
  created_at         = T0
  expires_at         = T0 + bounded TTL
  browser_binding    = session/binding handle (when supported by design)
  safe_return_path   = /invoices
  consumed           = false
~~~

**Never use raw `RelayState` as a global unique key without a collision/namespace policy**. Choose a random handle with high entropy, enforce TTL and max pending counts, reject duplicates, and isolate registration/browser contexts.

**Never pass a client-supplied return URL directly into the post-login redirect.** If storing a target URL, keep a relative path or allowlisted origin in server-side state, checking path canonicalization, scheme, and domain.

## 6. Request Repositories in Spring Security

Components:

- `Saml2WebSsoAuthenticationRequestFilter`: builds `AuthnRequest`.
- `AbstractSaml2AuthenticationRequest`: generated request/binding data.
- `Saml2AuthenticationRequestRepository`: interface with `saveAuthenticationRequest`, `loadAuthenticationRequest`, and `removeAuthenticationRequest`.
- `HttpSessionSaml2AuthenticationRequestRepository`: default per Spring docs; stores the pending request in `HttpSession`.
- `CacheSaml2AuthenticationRequestRepository`: available since Spring Security **6.5**, enabling cache-based lookup tied to `RelayState` when avoiding session reliance.
- `Saml2WebSsoAuthenticationFilter`: receives `SAMLResponse`.
- `Saml2AuthenticationTokenConverter`: resolves registration and pending request.
- OpenSAML authentication provider: verifies signatures and SAML constraints.

**Do not assume every release shares identical multi-tab behavior or OpenSAML providers.** Spring Security 6.x and 7.x change APIs; verify code against your active Javadoc/BOM.

## 7. Guarantees When Storing Pending Requests in HttpSession

If browser A initiates a request and the pending record sits in A's session, submitting the response from browser B with a different session **normally fails to find the pending record**. This provides a defense layer against **login fixation/login CSRF**.

Conversely, if `RelayState` alone indexes a global cache, the system knows the SP once created that request, yet **does not automatically know whether it originated from the browser currently receiving the response**. Spring Security docs explicitly call out this cache-repository trade-off.

Therefore, testing must distinguish:
- **Correlation:** the response matches an SP-issued request.
- **Browser origin binding:** the response matches the **current browser's flow**.
- **Cryptographic validation:** IdP/Assertion is genuinely verified.
- **Authorization:** user/tenant/resource permissions hold.

These four layers **do not substitute for each other**.

## 8. Session Loss Has More Than One Cause

**Cookie dropped in browser:** the session still exists in the backend, yet the ACS POST lacks `JSESSIONID`. Common causes include `SameSite`, `Domain`, `Path`, `Secure`, or proxy origin mismatches.

**Session invalidated/expired:** MFA at the IdP took too long; session timeout, logout, session invalidation/rotation occurred before callback, or the app restarted.

**Session invisible on another node:** Node A saved the pending record, callback hit Node B; missing Spring Session/shared store, broken sticky routing, or serializer/Redis outage.

**Pending overwritten:** Session is intact, yet saving a newer request B overwrote A's record.

All of these can surface as `InResponseTo mismatch` or the repository returning `null`. **Never "fix" them by dropping `InResponseTo` or defaulting to unsolicited login.**

## 9. SameSite Cookies in SAML POST Binding

IdPs usually deliver the SAML Response via a cross-site **HTML form HTTP POST** to the SP ACS.

- `SameSite=Strict`: browsers withhold cookies on such cross-site navigations.
- `SameSite=Lax`: normally withholds cookies on cross-site POSTs, despite legacy browser-specific quirks for cookies without explicit `SameSite`.
- `SameSite=None; Secure`: generally allows cookies on cross-site HTTPS POSTs where browser policy permits; requires reviewing CSRF protections accordingly.

Illustrative Spring Boot config **that must be reviewed in apps using browser cookies**:

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        same-site: none
~~~

**Do not promise this config solves every browser:** privacy policies, alternate proxy domains, and third-party cookie restrictions still matter. Inspect with real browser DevTools: did the SP send `Set-Cookie`, did the ACS POST send `Cookie`, and was the session recovered?

**Never set `secure: false`, fall back to HTTP, or disable all CSRF controls** just to make login pass.

## 10. Given–When–Then Design for the Baseline Flow

**Given:** browser holds session `S`, registration `Corp`, and pending record `(S, R-A, REQ-A, corp)`.

**When:** IdP `Corp` returns a signed response with `InResponseTo=REQ-A` and echoes `RelayState=R-A` to ACS `Corp`, with the session cookie still sent.

**Then:**
1. Repository locates the exact pending record.
2. Spring selects the right `Corp` `RelyingPartyRegistration`.
3. Signature, issuer, destination, recipient, audience, subject confirmation, and time conditions all pass.
4. Pending record is consumed per policy.
5. `Authentication` holds the exact verified principal and application-mapped tenant/roles.
6. Browser redirects to a safe return path.
7. Re-submitting the same `SAMLResponse` creates no new login.

**Asserting HTTP 302 alone is insufficient** because failure handlers may also redirect. Assert `SecurityContext`/identity/tenant, saved requests, and replay behavior.

## 11. RelayState Tampering: What to Test?

| Scenario | Expected |
| --- | --- |
| Flip one character of `R-A` | Reject |
| Omit `RelayState` | Reject in SP-initiated flows requiring binding |
| Empty `RelayState` replacing stored value | Reject |
| `RelayState` never issued by SP | Reject |
| Reuse already-consumed `RelayState` | Replay reject |
| Use tab B's `RelayState` with Response A | Reject |
| `RelayState` contains external URL | No open redirect |
| `RelayState` contains CRLF/control chars | Reject/sanitize |
| Duplicate `RelayState` form fields with differing values | Reject ambiguous input |
| URL-encoded `RelayState` altering meaning | Never canonicalize into a collision |
| `RelayState` longer than 80 bytes | Reject or controlled failure |
| Unicode `RelayState` >80 bytes yet <80 chars | Byte-aware limit enforced |
| Stale `RelayState` with valid XML signature | Creates no `Authentication` |
| Valid `RelayState` with wrong SAML Issuer | Reject |
| Valid `RelayState` with expired Assertion | Reject |

Most critical guarantee: **malformed input never turns into an authenticated identity or a redirect to an attacker's domain**.

## 12. Two Tabs Initiating SSO in the Same Session

~~~text
Browser session S
  Tab A: AuthnRequest ID=REQ-A, RelayState=R-A
  Tab B: AuthnRequest ID=REQ-B, RelayState=R-B

Timeline:
  A started at t0
  B started at t1
  Response B arrives at t2
  Response A arrives at t3
~~~

**If the repository holds only one pending slot per session**, B overwrites A. Response B can succeed; Response A must fail closed once its matching request is gone. This exact scenario has been reported with `HttpSessionSaml2AuthenticationRequestRepository`; verify the exact behavior of your current version.

**If the repository supports multiple pending records**, A and B can coexist keyed by `RelayState`/request ID and browser binding. Responses arriving in either order resolve accurately, with each pending record consumed once. However, if A/B log in **two different users**, the product needs an explicit `SecurityContext`/session policy so A's roles never attach to B's principal.

**Both tabs do not have to succeed.** The minimum invariant is preserving trust and identity integrity.

## 13. Two Flows Across Different IdPs or Tenants

Test:

~~~text
Tab A:
  registration=corp
  expected IdP=urn:corp:idp
  request=REQ-A
  relay=R-A
  tenant=north

Tab B:
  registration=partner
  expected IdP=urn:partner:idp
  request=REQ-B
  relay=R-B
  tenant=south
~~~

Responses that must be rejected:
- Partner signs an Assertion for a Corp request.
- `R-A` paired with `InResponseTo=REQ-B`.
- Response B hits Corp's ACS and the system "fixes" it by switching to Partner.
- Users sharing an email across two IdPs get auto-linked.
- `ROLE_ADMIN` from tenant South is granted in North.
- Browser holds user A's session, and callback B leaves session with A's principal + B's roles.

**Correlation must encompass registration, IdP `entityID`, audience, subject, and tenant authorization**, never `RelayState` alone.

## 14. Response Arrival Order Must Not Dictate Validity

The IdP might prompt for MFA, making tab A slower than tab B. You cannot guarantee Response A arrives first merely because `AuthnRequest` A started first.

Test both directions:
- A starts first, responses arrive **B→A**.
- A starts first, responses arrive **A→B**.
- B fails login while A succeeds.
- A times out while B remains valid.
- A logs out of the session while B is still at the IdP.
- A and B finish nearly simultaneously.

**There is no "accept whichever response arrives latest" shortcut** when request correlation fails. With a single-slot repository, the older response must fail closed; with multi-slot, each callback consumes its own record with consistent session semantics.

## 15. Race Condition When the Same Response Is POSTed Twice

A replay race can occur across two SP nodes:

~~~text
Node A                       Node B
  load pending R-A -> found    load pending R-A -> found
  validate SAML                validate SAML
  create Authentication        create Authentication
  remove R-A                   remove R-A
~~~

If **load→validate→remove** is not truly one-time under the actual architecture, both nodes can accept it. Enforce **atomic consume or equivalent replay controls**, and track consumed Response/Assertion IDs per policy.

**Careful:** `synchronized` removal inside one JVM does not guarantee atomicity across multiple pods. Redis/DB requires transactional primitives or compare-and-delete, key scoping, and TTL. Never test concurrency using `Thread.sleep` alone; use `CountDownLatch`, `CyclicBarrier`, or synchronized load-test tools.

## 16. CacheSaml2AuthenticationRequestRepository: Benefits and Trade-Offs

Since **Spring Security 6.5**, `CacheSaml2AuthenticationRequestRepository` can replace the session-backed repository to look up `AuthnRequest` via cache/`RelayState`. Docs note its usefulness when `SameSite=Strict` prevents recovering session-bound requests.

Yet the security trade-off is **very real**:
- The SP knows it previously generated that `AuthnRequest`.
- The SP **does not necessarily know the current browser is the one that initiated the request**.

This opens the door to **login fixation** if an attacker initiates a valid flow for their own account and passes the `SAMLResponse`/`RelayState` to a victim's browser.

When using a cache repository:
1. Add or prove browser/transaction binding fitting your threat model.
2. Use opaque keys with high entropy, short TTLs, and atomic one-time consume.
3. Bind the record to the exact registration/IdP/expected ACS.
4. Never treat self-declared `InResponseTo` as proof of the originating browser.
5. Run real cross-browser injection tests.
6. Bound pending counts to prevent DoS.
7. Use distributed storage across multiple nodes; never assume an in-memory cache works across pods.
8. Maintain session/role lifecycles after successful login.
9. Never fall back to unsolicited assertions if the store is unavailable.

**Never switch from session to cache solely to make two tabs pass without reviewing login fixation.**

## 17. Spring Config Snippet for the Cache Repository

The example below is **Spring Security 6.5+ project code**—not runnable on pure JDK and **not a recommendation to enable by default**:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.authentication.AbstractSaml2AuthenticationRequest;
import org.springframework.security.saml2.provider.service.web.CacheSaml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.web.Saml2AuthenticationRequestRepository;

@Configuration
public class SamlRequestRepositoryConfig {

    @Bean
    Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>
            authenticationRequestRepository() {
        // Use only after browser-binding/login-fixation review.
        return new CacheSaml2AuthenticationRequestRepository();
    }
}
~~~

Spring Security can auto-detect repository beans for SAML request/response filters depending on release. **Check your exact BOM and integration tests** to confirm both the request filter and response converter share the **same repository**.

If the only problem is cookie delivery at the ACS, you can keep the default `HttpSessionSaml2AuthenticationRequestRepository` and fix `SameSite`/cookie/proxy settings instead of accepting cache trade-offs.

## 18. Login Fixation When Looking Up Cache Only by RelayState

An essential negative E2E test:

~~~text
Attacker browser:
  Initiates AuthnRequest via SP itself.
  Receives RelayState R-ATTACK.
  Completes IdP login using attacker account.
  Captures signed SAMLResponse for attacker's request.

Victim browser:
  Never started SP login.
  Driven to ACS with response + R-ATTACK.

Expected:
  Must NOT create an authenticated session of attacker for victim,
  if the application requires session-origin binding.
~~~

If the product permits unsolicited SAML by policy, still enforce login-CSRF, response integrity, and replay checks so victims cannot be logged in unwillingly. Never confuse accepting a signed assertion with proving **browser consent/request binding**.

## 19. Session Loss from Logout, Timeout, and Session Rotation

Three easily confused cases:

**Timeout:** the user takes longer at IdP/MFA than the HTTP session TTL. The SP no longer has the pending request. Expected: fail closed, inform the user the login session expired, and allow restarting cleanly without a redirect loop.

**Logout in another tab:** the user clicks logout while another tab is still at the IdP. The stale callback must not silently "resurrect" the pre-logout session and privileges outside policy.

**Session fixation protection/rotation:** Spring may rotate the session ID after successful authentication; this differs from invalidating the session **before** the callback. If a custom filter creates/destroys sessions prematurely, the pending request may be lost.

**Never force `SessionCreationPolicy.STATELESS`** on an SP-initiated SAML flow that relies on pending requests in `HttpSession` without designing an alternative repository/correlation mechanism.

## 20. Spring Session and Multiple Nodes

~~~text
GET /saml2/authenticate/corp -> Node A
  save pending REQ-A in session S

POST /login/saml2/sso/corp -> Node B
  Node B must be able to load session S
  and the exact pending REQ-A
~~~

You can use Spring Session backed by Redis/JDBC or proper LB session affinity with failover tests. However:
- Sticky sessions do not rescue in-flight flows if Node A crashes.
- If the Redis shared session fails/expires, the SP must reject.
- Incompatible serialization versions can drop pending records.
- Distributed cache consumption must be one-time **cluster-wide**.
- Proxies must forward public HTTPS host/scheme properly so ACS/cookies match.
- Apps must never fall back to "skip request correlation" during a session-store outage.

**Test requests on A with callbacks on B, plus concurrent callbacks across A and B.**

## 21. Runnable Java 17: Modeling Single-Slot, Multi-Slot, and Concurrent Consume

This example **performs no SAML signature validation**; it checks **correlation policy only**. An `ACCEPT_CORRELATED` outcome **is not a successful `Authentication`**. Production must still verify SAML issuer, signing credentials, audience, destination, recipient, conditions, `NameID`, and replay caches.

Create **`SamlRelayStateConcurrencyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SamlRelayStateConcurrencyDemo {

    record Pending(String session, String relay, String requestId,
                   String registration, long expiresAt) {}

    static class OneSlotRepository {
        private final Map<String, Pending> store = new HashMap<>();

        synchronized void save(Pending pending) {
            store.put(pending.session(), pending);
        }

        synchronized String consume(String session, String relay,
                                    String inResponseTo, String registration) {
            if (session == null) {
                return "DENY_NO_SESSION";
            }
            Pending p = store.get(session);
            if (p == null) {
                return "DENY_UNKNOWN_OR_REPLAY";
            }
            if (!p.relay().equals(relay)) {
                return "DENY_RELAY";
            }
            if (!p.requestId().equals(inResponseTo)) {
                return "DENY_IN_RESPONSE_TO";
            }
            if (!p.registration().equals(registration)) {
                return "DENY_REGISTRATION";
            }
            store.remove(session);
            return "ACCEPT_CORRELATED";
        }
    }

    static class MultiRequestRepository {
        private final Map<String, Map<String, Pending>> store =
                new HashMap<>();

        synchronized void save(Pending p) {
            Map<String, Pending> requests = store.computeIfAbsent(
                    p.session(), key -> new HashMap<>());
            if (requests.putIfAbsent(p.relay(), p) != null) {
                throw new IllegalArgumentException("Duplicate RelayState");
            }
        }

        synchronized String consume(String session, String relay,
                                    String inResponseTo, String registration,
                                    long now) {
            if (session == null) {
                return "DENY_NO_SESSION";
            }
            Map<String, Pending> requests = store.get(session);
            if (requests == null) {
                return "DENY_UNKNOWN_OR_REPLAY";
            }
            Pending p = requests.get(relay);
            if (p == null) {
                return "DENY_UNKNOWN_OR_REPLAY";
            }
            if (now > p.expiresAt()) {
                remove(session, relay, requests);
                return "DENY_EXPIRED";
            }
            if (!p.requestId().equals(inResponseTo)) {
                return "DENY_IN_RESPONSE_TO";
            }
            if (!p.registration().equals(registration)) {
                return "DENY_REGISTRATION";
            }
            remove(session, relay, requests);
            return "ACCEPT_CORRELATED";
        }

        private void remove(String session, String relay,
                            Map<String, Pending> requests) {
            requests.remove(relay);
            if (requests.isEmpty()) {
                store.remove(session);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Pending a = new Pending("S", "R-A", "REQ-A", "corp", 100);
        Pending b = new Pending("S", "R-B", "REQ-B", "corp", 100);

        OneSlotRepository one = new OneSlotRepository();
        one.save(a);
        one.save(b);
        System.out.println("Single-slot A after B: "
                + one.consume("S", "R-A", "REQ-A", "corp"));
        System.out.println("Single-slot B: "
                + one.consume("S", "R-B", "REQ-B", "corp"));

        MultiRequestRepository multi = new MultiRequestRepository();
        multi.save(a);
        multi.save(b);
        System.out.println("Swap InResponseTo: "
                + multi.consume("S", "R-A", "REQ-B", "corp", 10));
        System.out.println("B before A: "
                + multi.consume("S", "R-B", "REQ-B", "corp", 10));
        System.out.println("A after B: "
                + multi.consume("S", "R-A", "REQ-A", "corp", 10));
        System.out.println("Replay A: "
                + multi.consume("S", "R-A", "REQ-A", "corp", 10));
        System.out.println("Lost session: "
                + multi.consume(null, "R-A", "REQ-A", "corp", 10));

        Pending c = new Pending("S", "R-C", "REQ-C", "partner", 12);
        multi.save(c);
        System.out.println("Wrong registration: "
                + multi.consume("S", "R-C", "REQ-C", "corp", 11));
        System.out.println("Expired: "
                + multi.consume("S", "R-C", "REQ-C", "partner", 13));

        Pending race = new Pending("S", "R-RACE", "REQ-RACE", "corp", 100);
        multi.save(race);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        Callable<String> attempt = () -> {
            start.await();
            return multi.consume("S", "R-RACE",
                    "REQ-RACE", "corp", 20);
        };

        try {
            Future<String> first = pool.submit(attempt);
            Future<String> second = pool.submit(attempt);
            start.countDown();
            String x = first.get();
            String y = second.get();
            int accepted = ("ACCEPT_CORRELATED".equals(x) ? 1 : 0)
                    + ("ACCEPT_CORRELATED".equals(y) ? 1 : 0);
            System.out.println("Concurrent replay: accepted="
                    + accepted + ", rejected=" + (2 - accepted));
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Compile/run:

~~~bash
javac SamlRelayStateConcurrencyDemo.java
java SamlRelayStateConcurrencyDemo
~~~

**Exact stdout:**

~~~text
Single-slot A after B: DENY_RELAY
Single-slot B: ACCEPT_CORRELATED
Swap InResponseTo: DENY_IN_RESPONSE_TO
B before A: ACCEPT_CORRELATED
A after B: ACCEPT_CORRELATED
Replay A: DENY_UNKNOWN_OR_REPLAY
Lost session: DENY_NO_SESSION
Wrong registration: DENY_REGISTRATION
Expired: DENY_EXPIRED
Concurrent replay: accepted=1, rejected=1
~~~

**Explanation:** one-slot shows B overwrites A, yet A is never misaccepted. Multi-slot allows out-of-order responses, rejects swapped `InResponseTo`, blocks replay, and safely handles missing sessions. When two threads race to consume `R-RACE`, `synchronized` ensures **exactly one wins in a single JVM**; the aggregate outcome is scheduler-independent. Multi-node systems require transactional/atomic shared stores and separate replay protection.

**The code contains no SAML verifier**, checks no XML/certificates, creates no Spring `SecurityContext`, and cannot serve as a production `AuthenticationProvider`.

## 22. Distinguishing Unit, Spring Integration, and Browser E2E Tests

| Layer | Can prove | Cannot prove on its own |
| --- | --- | --- |
| Java unit/repository | Exact correlation, TTL, replay, single-slot/multi-slot behavior | Real SAML signatures or browser cookie policy |
| Spring Security MockMvc | Filter wiring, request repository, failure handlers, `Authentication` | Real browser cross-site `SameSite` behavior |
| IdP integration | Signed response, issuer/audience/ACS, `InResponseTo` | Every browser/privacy quirk |
| Browser E2E | Session cookies, cross-site POSTs, two tabs, redirect loops | Cross-pod atomicity if running a single node |
| Multi-node/load | Shared store, duplicate POSTs, failover | Object-level authorization unless explicitly asserted |

**MockMvc tests checking status 302 alone are insufficient**: authentication failures can also redirect to a login page. Assert no authenticated `SecurityContext` in negative cases, and assert exact principal/tenant/roles in positive cases.

## 23. Spring Classes to Cover in Integration Tests

1. `Saml2WebSsoAuthenticationRequestFilter` issues requests with the right registration.
2. `Saml2AuthenticationRequestRepository` genuinely saves/loads/removes.
3. `Saml2WebSsoAuthenticationFilter` handles callbacks matching the ACS matcher.
4. `Saml2AuthenticationTokenConverter` resolves the expected request/registration.
5. OpenSAML provider verifies signatures/issuer/audience/recipient/timestamps.
6. Post-success `SecurityContext`/session does not reuse stale accounts.
7. Authentication failure handler creates no `SecurityContext`.
8. Session fixation strategy does not wipe pending state before callback.
9. Saved request/redirect target is safe.
10. Role mapping and tenant membership apply after authentication.

Test against the **deployed configuration**—do not assume Spring Security 5.x XML matches Spring Security 6.x/7.x Java DSL. OpenSAML 4/5 providers and bean wiring vary by version.

## 24. Fixtures for Two Flows A/B

| Property | Flow A | Flow B |
| --- | --- | --- |
| Browser | Browser-1 | Browser-1 |
| Session ID | S-100 | S-100 |
| Tab | A | B |
| Registration | `corp` | `corp`/`partner` |
| `AuthnRequest` ID | `REQ-A` | `REQ-B` |
| `RelayState` | `R-A` | `R-B` |
| IdP `entityID` | `urn:corp:idp` | `urn:corp:idp` or `urn:partner:idp` |
| SP `entityID` | `urn:portal:sp:corp` | B's SP `entityID` |
| ACS | `/login/saml2/sso/corp` | B's ACS |
| Expiry | `T0 + TTL` | `T1 + TTL` |
| Expected local account | Per verified response A | Per verified response B |
| Tenant | Per server policy A | Per server policy B |

**Fixtures must use distinct request IDs**, random/unique `RelayState`s, dedicated test IdP signing key pairs, and trusted test SP certs. Never log production `NameID`/cookies/assertions.

## 25. E2E Procedures in Given–When–Then

**Standard case:**
- Given a browser session `S` and test IdP `Corp`.
- When initiating login, capturing request/`RelayState`, and IdP signs a matching Response.
- Then the right user is authenticated, pending record is consumed, and replay fails.

**Cookie-loss case:**
- Given `S` holds pending A.
- When the browser POSTs to ACS without the matching cookie.
- Then no authenticated session is created and the failure is categorized.

**Two-tab case:**
- Given A and B created pending records inside the same `S`.
- When response B arrives before A.
- Then only responses with matching pending records succeed per repository behavior, with zero user/tenant mixing.

**Cross-browser case:**
- Given attacker A initiates a request and victim V has never logged in.
- When attacker delivers `RelayState`/Response to V.
- Then login fixation protections prevent victim V from inheriting attacker A's session per security policy.

**Double-POST case:**
- Given the same response is POSTed to two SP nodes concurrently.
- Then at-most-once/replay policy is enforced cluster-wide.

## 26. RelayState and Protocol Correlation Matrix

| # | Scenario | Expected |
| --- | --- | --- |
| 01 | SP sends `R-A`, IdP echoes `R-A`, Response valid | Logs in exact identity |
| 02 | `R-A` altered by one byte | Reject |
| 03 | `RelayState` omitted on callback | Fail closed when SP-initiated requires correlation |
| 04 | Empty `RelayState` | Reject per pending contract |
| 05 | Non-existent `RelayState` | Reject |
| 06 | Already-consumed `RelayState` | Replay reject |
| 07 | `RelayState` contains external URL | No open redirect |
| 08 | `RelayState` exceeds 80 bytes | Reject outside binding limit |
| 09 | Unicode `RelayState` >80 bytes | Byte-aware validation |
| 10 | `RelayState` contains CRLF | Reject/sanitize |
| 11 | Two `RelayState` fields with differing values | Reject ambiguous form |
| 12 | `RelayState` A, `InResponseTo` B | Reject |
| 13 | `RelayState` A, wrong registration | Reject |
| 14 | Valid `RelayState`, wrong IdP issuer | Reject |
| 15 | Valid `RelayState`, invalid SAML signature | Reject |
| 16 | Valid `RelayState`, wrong `AudienceRestriction` | Reject |
| 17 | Valid `RelayState`, wrong `Recipient`/`Destination` | Reject |
| 18 | Valid `RelayState`, expired Response | Reject |
| 19 | Assertion ID replay | Reject |
| 20 | XML Signature Wrapping attempt | Unsigned claims never used |

## 27. Session and Cookie Matrix

| # | Scenario | Expected |
| --- | --- | --- |
| 21 | Valid session cookie on ACS POST | Pending record loaded properly |
| 22 | `SameSite=Strict` cross-site POST | Detects missing session; fails closed |
| 23 | `SameSite=Lax` cross-site POST | Test real browsers; do not rely on quirks |
| 24 | `SameSite=None; Secure` HTTPS | Cookie delivered if policy supports; review CSRF |
| 25 | `Secure` cookie over HTTP ACS | No cookie; fix HTTPS architecture |
| 26 | Cookie `Domain` mismatches ACS | Fail closed |
| 27 | Cookie `Path` excludes ACS | Fail closed |
| 28 | Session TTL expires while user is at IdP | Safe login restart |
| 29 | Logout in another tab before callback | Never resurrect session outside policy |
| 30 | App restart wipes local sessions | Fail closed / shared store |
| 31 | Node A saves, Node B callback without shared session | Reject response |
| 32 | Spring Session shared store working | Loads pending record for session `S` |
| 33 | Session ID rotates before callback | Reject if state lost |
| 34 | Session fixation protection after success | Proper session lifecycle |
| 35 | Redis/DB session store outage | Never skip correlation |
| 36 | Incognito browser receives old callback | Reject if session-bound |
| 37 | Proxy strips `Cookie` header | Fail closed |
| 38 | Callback alters public host/scheme | Check both cookies and SAML `Recipient`/`Destination` |

## 28. Concurrent Flows and Cross-Tenant Matrix

| # | Scenario | Expected |
| --- | --- | --- |
| 39 | A then B in same session, single-slot | A fails if overwritten; B may pass |
| 40 | B then A in same session, single-slot | Never misaccept |
| 41 | Multi-slot callbacks A then B | Accurate correlation per flow |
| 42 | Multi-slot callbacks B then A | Accurate correlation per flow |
| 43 | A's request, callback carries B's `RelayState` | Reject |
| 44 | A's request, callback carries B's `InResponseTo` | Reject |
| 45 | A Corp, B Partner | No cross-IdP confusion |
| 46 | A North tenant, B South tenant | No cross-tenant authorization |
| 47 | A user Alice, B user Bob | Clear session identity-switch policy |
| 48 | Two ACS POSTs of same response in one JVM | At-most-once |
| 49 | Two ACS POSTs of same response across two nodes | Distributed at-most-once |
| 50 | Flow A expires while B stays alive | A fails, B not deleted accidentally |
| 51 | A fails while B pending | Do not unconditionally wipe B |
| 52 | Replay after success | Reject |
| 53 | Attacker response sent to victim browser | Login fixation test |
| 54 | Two tabs + logout/re-authentication | Never resurrect stale session |
| 55 | Signed response for wrong SP `entityID` | Reject despite matching `RelayState` |

**A system PASSES when identity and privileges are accurate**, not merely when multiple callbacks return HTTP 200. Single-slot may intentionally support only one pending request; tests must reflect that policy.

## 29. Testing Concurrency Without Relying on Sleep

**Avoid:**

~~~java
// Anti-pattern: arbitrary timing
Thread.sleep(100);
triggerSecondRequest();
~~~

Use `CountDownLatch` or `CyclicBarrier` like the Java 17 program above, then assert **invariants** instead of assuming which task runs first:
- At most one thread consumes a pending record.
- No record is consumed by the wrong registration.
- Subsequent replays are rejected.
- Processing flow A never deletes flow B.
- Distributed store failures fail closed.
- Authenticated sessions are created only after complete validation.

**Repeat tests multiple times** to expose rare races, combining two-node load tests and network fault injection. Single-JVM unit tests never prove distributed atomicity.

## 30. Diagnosing Failures from Real Symptoms

| Symptom | Likely cause | How to verify |
| --- | --- | --- |
| `InResponseTo` mismatch only with multiple tabs | Pending overwrite | Compare pseudonymized request IDs |
| Callback sees no session | `SameSite`/Domain/Path/TTL | Browser DevTools `Set-Cookie`/`Cookie` |
| One node logs in, another fails | Session store/affinity | Multi-node trace |
| `RelayState` differs at callback | Encoding/IdP/proxy | Compare exact opaque value in tests |
| Infinite 302 loop | Callback failed and restarted flow | Check failure handler/session cookie |
| Bad signature | IdP key/metadata, not `RelayState` | Check trusted cert and SAML validator |
| User A gets B's roles | Session/tenant account-linking race | Audit principal + server memberships |
| Cache repo fixes login yet security test fails | Login fixation trade-off | Cross-browser injection test |
| Replayed response still logs in | Non-atomic consume/replay guard | Concurrent POST test |
| Redirect points to external domain | Trusted raw `RelayState` return URL | Allowlist safe return targets |
| Pending disappears on fast logins | Custom session invalidation/rotation | Trace session lifecycle |
| `SameSite=None` still sends no cookie | TLS/proxy/browser policy | Inspect cookie attributes and origin |

**Never apply quick workarounds** by dropping request correlation, accepting all unsolicited SAML, disabling signatures, or using insecure cookies.

## 31. Controlled Observability and Logging

Instrument these fields under data-minimization rules:

- Shared correlation ID across test SP/IdP and gateway.
- Trusted `registrationId` and IdP `entityID`.
- Hashed/pseudonymized `AuthnRequest.ID`, `InResponseTo`, `RelayState`.
- Repository implementation and pending status: FOUND/MISSING/MISMATCH/EXPIRED.
- Session fingerprint without exposing `JSESSIONID`.
- ACS node/pod, browser version, and cookie policy.
- Request creation time, callback time, remaining TTL.
- Failure category: `COOKIE_MISSING`, `RESPONSE_REPLAY`, `REQUEST_OVERWRITTEN`.
- Local account ID/tenant/action after successful authentication.
- SAML signature/protocol validation outcome without logging raw payloads.

**Absolutely never dump** `SAMLResponse`, raw XML with NameIDs/PII, private keys, session ID cookies, or sensitive `RelayState` into shared logs/APMs/HARs. Test IdPs must use synthetic fixtures and access controls.

Suggested metrics: `saml_relaystate_mismatch_total`, `saml_session_missing_total`, `saml_inresponseto_mismatch_total`, `saml_parallel_login_conflict_total`, `saml_replay_rejected_total`. These are custom recommendations—do not assume every meter exists in Spring out of the box.

## 32. Deployment and Canary Workflow

**Preparation:**
1. Confirm active Spring Boot/Security versions and repository implementation.
2. Verify `RelayState`, `AuthnRequest` ID, expiration, and replay handling.
3. Verify session cookie `SameSite`/`Secure`/`Domain`/`Path` and public HTTPS ACS URL.
4. Define business policy: single vs. multiple concurrent login flows/outstanding requests.
5. Verify load balancer, Spring Session, cache consistency, and node failover.
6. Select test IdP, signing keys/metadata, and synthetic users/tenants.
7. Write signed fixture tests covering Issuer/Audience/Recipient.
8. Enable pseudonymized logging and failure categories.

**Canary:**
1. 1-tab happy path.
2. `RelayState` tampered/unknown/replay/overlong.
3. Missing session after IdP POST.
4. Two same-session tabs with out-of-order responses.
5. Different IdPs/tenants in the same session.
6. Double POST of the same response across two threads/nodes.
7. Cross-browser login fixation.
8. Key rotation/session TTL/ACS proxy path.
9. Verify exact user identity/roles/tenant.
10. Roll out once security owners sign off on test evidence.

**During a production incident:**
1. Capture request correlation, release version, and repository type.
2. Check whether the cookie reached the ACS and whether the session still exists.
3. Check concurrent tabs and pending overwrites.
4. Check exact IdP signing cert, ACS/recipient/audience.
5. Never enable unsolicited fallback to patch session loss.
6. Fix cookie/store/proxy or repository per threat review.
7. Re-run negative tests before rollout.
8. Audit logs for PII, purge sensitive diagnostics, and document root cause.

## 33. Self-Assessment Questions

**1. Does `RelayState` prove the user was authenticated by the IdP?**  
No, it is only binding/correlation state.

**2. Does `RelayState` mean the same thing as `InResponseTo`?**  
No. `InResponseTo` links XML Response/Assertion to `AuthnRequest` ID; `RelayState` references state at the HTTP binding layer.

**3. How does OASIS bound `RelayState`?**  
No more than 80 **bytes** under HTTP Redirect/POST bindings.

**4. Why is a validly signed SAML response rejected when the session is lost?**  
The SP no longer holds the pending request to prove request correlation/browser session.

**5. Why can `SameSite` affect the ACS?**  
Cross-site IdP POSTs may omit the session cookie under `SameSite` `Strict`/`Lax`.

**6. Does a cache repository automatically guarantee browser-origin binding?**  
No. Spring docs warn about the login fixation trade-off.

**7. Must two tabs in the same session both succeed in logging in?**  
No, depending on repository/policy; what is mandatory is zero mixing of requests, identities, or tenants.

**8. If B overwrites A, may `InResponseTo` be dropped so A still logs in?**  
No. A must fail closed once pending A is gone.

**9. What do two threads racing to consume one record require?**  
At-most-once/atomic consume and replay protection.

**10. Is Java `synchronized` enough across multiple pods?**  
No. A distributed atomic mechanism is required.

**11. Should `RelayState` ever be used directly as a redirect URL?**  
No; use a server-stored/allowlisted safe return target.

**12. What should happen if the session expires while the user is doing MFA at the IdP?**  
Report that the login transaction expired and restart cleanly; never accept unsolicited responses instead.

**13. Do MockMvc tests fully validate `SameSite` behavior?**  
No; a real browser executing a cross-site POST is needed.

**14. When two IdPs emit the same NameID/email, should accounts be merged?**  
Never automatically; trusted identity linking is required.

**15. Can a response with a valid `RelayState` but invalid signature pass?**  
No, all protocol validations remain mandatory.

## 34. Production Checklist

- [ ] Pending `AuthnRequest` is saved with ID/`RelayState`/registration and explicit TTL.
- [ ] `RelayState` is opaque, random, `<=80` bytes, with integrity/correlation enforced.
- [ ] Raw `RelayState` is never used as an unvalidated redirect URL or tenant selector.
- [ ] `RelayState` and `InResponseTo` are matched as an exact pair.
- [ ] Every SAML Response/Assertion validates signature, Issuer, Audience, Recipient, Destination, and Conditions.
- [ ] Response/Assertion replay is prevented.
- [ ] Session cookie uses exact `SameSite`/`Secure`/`Domain`/`Path` and HTTPS ACS origin.
- [ ] Missing session/pending request fails closed; unsolicited SAML is never auto-enabled.
- [ ] Version and behavior of `HttpSessionSaml2AuthenticationRequestRepository` are verified.
- [ ] Two same-session tabs A/B and out-of-order responses are tested.
- [ ] Single-slot overwrite or multi-slot behavior is tested per design.
- [ ] If using a cache repository, matching login-fixation/browser-binding defenses exist.
- [ ] Pending consumption and assertion replay guards are atomic for the deployment topology.
- [ ] Spring Session/shared cache state works across multiple nodes.
- [ ] Session timeout/logout/rotation before and after callbacks are tested.
- [ ] IdP registrations/tenants never mix in concurrent flows.
- [ ] Spring `SecurityContext` never retains mismatched user/roles after two callbacks.
- [ ] Cross-browser injection, open redirect, and duplicate `RelayState` fields are tested.
- [ ] E2E signed fixtures, real browser `SameSite` tests, and multi-node load tests run.
- [ ] Negative tests assert no `Authentication` is created.
- [ ] Raw `SAMLResponse`, `RelayState`, `JSESSIONID`, and IdP private keys are never logged.
- [ ] Metrics track mismatches, replay, missing sessions, and parallel conflicts.
- [ ] Incidents are fixed at the right layer without weakening signature/recipient/correlation checks.

## 35. Conclusion

**Testing `RelayState`, session loss, and concurrent SAML logins** tests the system's ability to **bind the exact response to the exact request/browser/registration** and handle replay safely.

Per Spring Security documentation, the default `HttpSessionSaml2AuthenticationRequestRepository` stores pending requests in the HTTP session, offering browser-origin protection that can still break when cross-site POSTs omit cookies or multiple tabs overwrite pending state. `CacheSaml2AuthenticationRequestRepository` (since Spring Security 6.5) is an alternative, yet **does not by itself prove the response belongs to the logging-in browser**. Therefore, adopting a cache or multi-slot design must be paired with threat modeling against login fixation, expiration, atomic consume, and deployment-accurate tests.

**A flow is valid only when:** `RelayState`/request correlation matches, IdP signature/Issuer/Audience/Recipient/Conditions verify, replay guards hold, and local account plus tenant/resource policy permit access. **If a pending request is lost, fail closed rather than "loosening" SAML validation.**

### Official References

- Spring Security — Producing SAML2 AuthnRequests, session/cache request repository: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Saml2AuthenticationRequestRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationRequestRepository.html
- Spring Security — CacheSaml2AuthenticationRequestRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/CacheSaml2AuthenticationRequestRepository.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- OASIS SAML 2.0 Bindings — HTTP Redirect/POST RelayState: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OASIS SAML 2.0 Technical Overview — SP-initiated SSO and RelayState: https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html

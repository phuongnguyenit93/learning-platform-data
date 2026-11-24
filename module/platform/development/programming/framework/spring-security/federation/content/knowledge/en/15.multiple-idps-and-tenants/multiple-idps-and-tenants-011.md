# Correlating Callbacks and Logout Messages to the Exact Initial Registration

> **Module:** Spring Security – Federation · **Parent Topic:** Multiple IdPs and Tenants. This lesson analyzes how a Service Provider (SP) using Spring Security SAML2 **binds a `LogoutResponse`/`LogoutRequest` to the exact `RelyingPartyRegistration`, IdP, tenant, and initiating session**. The focus is avoiding registration mix-ups when an SLO callback hits a shared URL, after the SP's HTTP session has been invalidated, or when multiple tenants share the same IdP issuer.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why `RelyingPartyRegistration` represents **a specific SP–IdP relationship**, whereas `registrationId` is merely Spring's configuration key and not trustworthy proof sent from an IdP.
2. Distinguish an **SP/RP-initiated SLO callback** from an **IdP/AP-initiated `LogoutRequest`**; understand why only RP-initiated SLO has an original SP `LogoutRequest` for `InResponseTo`.
3. Trace the flow of `LogoutRequest ID`, `RelayState`, `Saml2LogoutRequestRepository`, `Issuer`, `Destination`, signatures, and metadata when the callback returns to the SP.
4. Enforce the binding **initial registration → trusted IdP → SP entity ID → tenant → logout attempt**, preventing query/path/body parameters from changing context arbitrarily.
5. Handle two tenants sharing one IdP issuer, two IdPs emitting identical `NameID`/`SessionIndex`, callbacks landing on another node, invalidated sessions, and late responses.
6. Separate **preliminary routing** by endpoint/issuer from **final verification** using the trusted registration, signature, protocol fields, and correlation.
7. Use `saml2Logout`, `Saml2LogoutRequestRepository`, and Spring Security validators **without replacing default security checks with a custom XML parser**.
8. Run a standalone Java 17 example matching callbacks against original attempts with verified stdout, and review a Spring Boot 3.3 / Spring Security 6.3 project with two registrations.
9. Build a multi-IdP/multi-tenant test matrix covering cross-tenant callbacks, request mix-ups, replay, key rollover, shared callback URLs, and AP-initiated SLO.

**Scope:** SAML2 Single Logout (SLO) in a Servlet SP application. This lesson does not replace IdP operations documentation. Check exact Spring APIs for your version; the configuration example below uses **Java 17, Spring Boot 3.3.x, Spring Security 6.3.x** as a baseline.

## 2. Context: One Shared Callback, Multiple Trust Relationships

The Orders Portal system supports:

| Internal `registrationId` | Business Tenant | SP Entity ID | IdP Entity ID |
| --- | --- | --- | --- |
| `partner-a` | `tenant-A` | `https://orders.example/saml2/sp/partner-a` | `https://idp-a.example/saml` |
| `partner-b` | `tenant-B` | `https://orders.example/saml2/sp/partner-b` | `https://idp-b.example/saml` |
| `shared-a` | `tenant-C` | `https://orders.example/saml2/sp/shared-a` | `https://idp-shared.example/saml` |
| `shared-b` | `tenant-D` | `https://orders.example/saml2/sp/shared-b` | `https://idp-shared.example/saml` |

Both `shared-a` and `shared-b` are served by the same IdP system, so their **IdP issuer is identical** while their SP entity IDs and tenants differ.

To receive SLO messages from IdPs, the application may expose one shared callback:

~~~text
https://orders.example/logout/saml2/slo
~~~

**The problem:** if a browser POSTs a `LogoutResponse` carrying `Issuer=https://idp-shared.example/saml` to this callback, does the SP pick `shared-a` or `shared-b`? **Issuer alone is insufficient** because the Issuer is identical. If the app trusts `?registrationId=shared-b` from the browser, an attacker can attempt to shift how the message is interpreted into another tenant.

In **RP-initiated SLO**, the SP **already knows the registration when issuing the `LogoutRequest`** and can store the original request data. The callback must be correlated against that **original issued context**—never re-selecting a tenant freely from strings on the HTTP response.

In **AP-initiated SLO**, there is no original SP `LogoutRequest`. You therefore need an **unambiguous** registration resolution mechanism grounded in endpoint/tenant binding and IdP-signed evidence, then verify the message against the **right** trust config. If one Issuer maps to multiple registrations, require an approved routing discriminator or reject—**never pick the first match arbitrarily**.

## 3. Concepts That Must Be Kept Separate

| Concept | Who Defines It? | Purpose | Must Never Be Used As |
| --- | --- | --- | --- |
| `registrationId` | Spring Security app. | Lookup key for `RelyingPartyRegistrationRepository`. | Proof of IdP/tenant merely because it appears in path/query. |
| SP `entityId` | Published/approved SP–IdP link. | Protocol SP identity; separates two tenants sharing one IdP. | Callback URL (`Destination`) if the two values differ. |
| IdP `entityId` / `Issuer` | Published by IdP, trusted by SP via metadata. | Identifies the signer/sender of `LogoutRequest`/`LogoutResponse`. | Unique tenant key when one IdP serves multiple registrations. |
| SP SLO callback URL | Published by SP in metadata/config. | Destination receiving SLO messages. | Substitute for verifying `InResponseTo`/issuer/signature. |
| `LogoutRequest.ID` | Sender of `LogoutRequest`. | Matches a response to its original request. | Local user ID or tenant ID. |
| `LogoutResponse.InResponseTo` | Sent by IdP in response to RP-initiated SLO. | Must point to the exact original request ID. | Self-asserted value to fabricate a new original request. |
| `RelayState` | State carried across browser per SAML binding. | Helps framework retrieve original request/correlation on callback. | Proof of trust without checking the stored request. |
| `NameID` / `SessionIndex` | Asserted during authentication / issued by IdP per profile. | Selects the session to terminate within the right trust scope. | Global user key across IdPs/tenants. |
| Verification certificate | Trusted registration/metadata. | Verifies the signature of that exact IdP. | Arbitrary cert extracted from browser-delivered `ds:KeyInfo`. |
| Business tenant | SP app after trusted identification. | Scopes sessions, permissions, and resources. | Query parameter chosen by the browser at callback time. |

**Four boundaries:** routing → SAML message verification → identifying affected sessions → local logout/authorization execution. Never skip the last three steps just because the callback URL matched.

## 4. RP-Initiated SLO Flow: Original Binding Must Not Change Mid-Flow

~~~text
Browser              SP Orders / Registration partner-a         IdP A
   |                            |                                 |
   | POST /saml2/logout         |                                 |
   |--------------------------->| Read authenticated principal    |
   |                            | -> partner-a                    |
   |                            | Issue LogoutRequest ID=_reqA    |
   |                            | RelayState=opaqueA              |
   |                            | Save original req + context A   |
   |                            | Invalidate local session per flow|
   |<---- browser to IdP -------|                                 |
   |-------------------------------- LogoutRequest -------------->|
   |                            |                                 | Logout
   |<-------------------------------- LogoutResponse --------------|
   | POST /logout/saml2/slo     |                                 |
   |--------------------------->| Lookup original req opaqueA     |
   |                            | Restore exact registration A    |
   |                            | Verify issuer/key/destination   |
   |                            | Check InResponseTo=_reqA        |
   |                            | Prevent replay/expiry           |
   |<---- valid result ---------|                                 |
~~~

For RP-initiated callbacks, **the principal may already be cleared from `SecurityContext`** because local logout happens before dispatching SLO. You therefore cannot always rely on `SecurityContextHolder.getContext().getAuthentication()` during the response callback to know which registration started the flow. The framework relies on a **saved `LogoutRequest`**, and multi-tenant apps must preserve that mapping in any custom repository/resolver.

### 4.1. SP-Issued `LogoutRequest`

Illustrative outbound XML fragment:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-partner-a-01"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:00Z"
    Destination="https://idp-a.example/slo">
    <saml:Issuer>https://orders.example/saml2/sp/partner-a</saml:Issuer>
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
        pa-4819
    </saml:NameID>
    <samlp:SessionIndex>idp-session-731</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Values are structural examples. In practice, the SP signs the `LogoutRequest` per binding/policy and uses the `NameID` and `SessionIndex` from the original Assertion/Authentication. **Never construct `SessionIndex` from the SP's HTTP session ID.** Unsigned sample XML cannot serve as a real `LogoutRequest`.

The request goes via the browser to **IdP A's SLO endpoint** from trusted metadata; there is no legitimate reason for its callback to be interpreted as registration `partner-b` simply because the browser appended a parameter.

### 4.2. IdP-Returned `LogoutResponse`

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_res-partner-a-01"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:09Z"
    InResponseTo="_req-partner-a-01"
    Destination="https://orders.example/logout/saml2/slo">
    <saml:Issuer>https://idp-a.example/saml</saml:Issuer>
    <samlp:Status>
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>
</samlp:LogoutResponse>
~~~

The callback carries **`Issuer` = IdP A** and **`Destination` = SP callback URL**; there is no standard `tenantId` attribute inside `LogoutResponse` for the SP to trust. Registration resolution relies on the **original `LogoutRequest` + trusted registration configuration**, followed by verifying the response accordingly.

With HTTP-Redirect binding, the signature travels in query parameters per profile rather than as `ds:Signature` inside XML. Validators must handle the exact binding; never assume "the XML has no `ds:Signature`, so it's unsigned," nor treat client-supplied `SigAlg`/`Signature` as trusted without verifying against the right IdP key.

### 4.3. Ordered Verification Steps

1. Locate the original `Saml2LogoutRequest` via the framework-configured repository/state; never fabricate a new one.
2. Read `registrationId` from the original request and fetch `RelyingPartyRegistration` **from the trusted repository**.
3. Verify the original request is within its validity window, unconsumed, and bound to the right tenant/trust context.
4. Verify the `LogoutResponse` signature **using the IdP verification credentials of the original registration**.
5. Verify the response `Issuer` matches the IdP entity ID in that registration.
6. Verify `Destination` matches the published SP SLO endpoint for that registration in the current environment.
7. Verify `InResponseTo` matches the `LogoutRequest.ID` issued by the SP; reconcile `RelayState` through the configured repository mechanism.
8. Inspect `Status` per profile; `Success`, `PartialLogout`, and errors must be interpreted deliberately.
9. Atomically mark the attempt consumed to prevent replay/duplicate processing, then complete auditing and UX.
10. An already-terminated local session **must never be restored** when the callback fails or arrives late.

**Important:** This is the **overall control logic**, not a promise that every default Spring Security callback runs all custom tenant checks and audits out of the box. Keep built-in SAML validation intact; implement and test additional tenant, `config_version`, and correlation checks where your product requires them.

## 5. Why Not Rely Solely on `Issuer` or `registrationId` in the URL?

### 5.1. `Issuer` May Not Uniquely Identify a Tenant

~~~text
tenant-C  -> registration shared-a -> IdP issuer = shared.example/idp
tenant-D  -> registration shared-b -> IdP issuer = shared.example/idp

LogoutResponse.Issuer = shared.example/idp
~~~

The Issuer identifies the **IdP**, yet is **insufficient** to pinpoint which SP entity ID or tenant applies. For RP-initiated callbacks, the original request identifies the exact registration. If the original request is gone or missing, never pick `tenant-C` just because it appears first in a list.

### 5.2. `registrationId` Is a Hint, Not Proof of Trust

URLs such as:

~~~text
/logout/saml2/slo
/logout/saml2/slo/partner-a
/logout/saml2/slo?registrationId=partner-b
~~~

Must be distinguished:

- `/logout/saml2/slo` is the shared callback in Spring Security SLO docs.
- Variants containing `{registrationId}` in the endpoint should be used **only when matching resolvers and metadata are configured and tested**; never assume every variant path works automatically.
- Query parameter `registrationId=partner-b` **is not proof** the response belongs to B. An app may use a route hint to pick a candidate, yet **must** verify signature, IdP issuer, request correlation, and tenant context.
- There is no rule saying "because the path says `partner-a`, trust the response under `partner-a`'s cert without `InResponseTo`."

If the original `LogoutRequest` belonged to `partner-a` yet the callback carries hint `partner-b`, fail closed rather than "switching" the request to B and trying B's key to see if verification passes.

### 5.3. Matching `NameID` and `SessionIndex` Are Not Enough

~~~text
IdP A: NameID=user-42, SessionIndex=session-2
IdP B: NameID=user-42, SessionIndex=session-2
~~~

Identical strings do not mean the same person or the same session. Session identity lives inside **IdP source + registration/tenant + SP scope**. Specifically, never use `SessionIndex` as a globally unique key in a logout table or use it to terminate another tenant's session.

### 5.4. When a Shared IdP Uses the Same Certificate for Two Registrations

Verifying the signature under the shared public key still does not resolve ambiguity: the certificate proves the **IdP source**, not whether the callback targets `shared-a` or `shared-b`. Preserve the **original request, SP entity ID, and tenant binding** in the control plane. Without an original attempt for an RP-initiated flow, never accept a callback merely because it was "signed by the shared IdP."

## 6. AP-Initiated `LogoutRequest`: No Original SP `LogoutRequest`

In **IdP/AP-initiated SLO**, the IdP proactively sends a `LogoutRequest` to the SP:

~~~text
IdP B ---- signed SAMLRequest ----> /logout/saml2/slo
                                   |
                                   +-- Resolve trusted registration candidate
                                   +-- Verify signature with that IdP's keys
                                   +-- Validate Issuer/Destination/conditions
                                   +-- Identify NameID/SessionIndex in scope
                                   +-- Invalidate only matching SP session
                                   +-- Send signed LogoutResponse to IdP B
~~~

Because no prior RP-initiated `LogoutRequest` was issued by the SP, **there is no `InResponseTo` pointing to a prior SP request**. Instead, you must bind **IdP message sender → exact registration → exact target session**.

### 6.1. Fields to Verify on an AP-Initiated Request

| Field / Source | Verification Method | Risk If Skipped |
| --- | --- | --- |
| `SAMLRequest` / binding | Parse per SAML2 binding using safe handlers. | Mishandling non-profile XML. |
| XML / query signature | Verify with trusted keys of the exact IdP registration. | Attacker forges `LogoutRequest` to log users out. |
| `Issuer` | Matches trusted IdP entity ID. | Cross-IdP logout. |
| `Destination` | Targets published/allowed SP SLO endpoint. | Replaying request across SPs/tenants. |
| `NameID` | Match against verified SAML authentication subject within **issuer scope**. | Matching string logs out the wrong user. |
| `SessionIndex` | Matches IdP-issued and SP-stored session, when present per profile/IdP. | Terminates all sessions solely on matching name. |
| Time / ID / replay | Non-empty ID, valid time window where applicable, replay protection. | Stale/replayed request causes unintended logout. |
| Registration / tenant context | Unambiguous, verified against trust config and session mapping. | Terminates sessions in the wrong tenant. |

If a **shared IdP** serves multiple tenants with the same `Issuer` and a shared callback URL, you need **signed tenant-specific routes/configs** or a resolver that safely reconciles session/profile context. If context is insufficient to disambiguate, **reject** the AP-initiated request rather than scanning every session/tenant and logging out all matches.

### 6.2. Tenant-Dedicated Paths Help but Are Not Sufficient

For example, a deployment exposes:

~~~text
https://orders.example/tenant-c/logout/saml2/slo
https://orders.example/tenant-d/logout/saml2/slo
~~~

Dedicated paths can help **route to a candidate**. Still, a client can call any URL; this is safe only when resolvers are configured, metadata/IdP match the exact endpoint, and the message is then verified against IdP/SP entity IDs, `NameID`, and `SessionIndex` for that tenant. Never build a custom MVC controller that reads `SAMLRequest` and deletes sessions using `tenantId` from the path without passing through Spring SAML validators.

### 6.3. RP vs. AP Asymmetry to Remember

| Aspect | RP-Initiated Callback | AP-Initiated Request |
| --- | --- | --- |
| Who sends the initial message? | SP sends `LogoutRequest`. | IdP sends `LogoutRequest`. |
| Original SP request stored? | **Yes**; must be correlated. | **No** for that initiation. |
| `InResponseTo` | Used in `LogoutResponse` to reference SP's request. | Incoming `LogoutRequest` to SP does not carry that meaning. |
| How registration is found | From original request + trusted repository. | Resolver picks candidate via trusted context, then verifies request. |
| Session selection | RP already knows the initiating user/session. | Identifies session to terminate via validated IdP identity + `SessionIndex`/profile. |
| SP response | Receives and processes IdP's `LogoutResponse`. | SP constructs `LogoutResponse` to return to IdP. |

## 7. `RelayState`, `InResponseTo`, and the Request Repository

### 7.1. Distinct Roles

- `LogoutRequest.ID`: ID generated by the SP for RP-initiated SLO.
- `LogoutResponse.InResponseTo`: points to that exact ID.
- `RelayState`: state passed through the browser per binding, commonly used as the lookup/correlation key to the original request.
- `Saml2LogoutRequestRepository`: Spring Security interface storing outbound requests so callbacks can be correlated.
- `RelyingPartyRegistrationRepository`: holds IdP/SP trust/config, **not** every active `LogoutRequest`.

A guessable, tampered, or missing `RelayState` **must never be used to fabricate a new request**. Checking `InResponseTo` and signature must go hand in hand with retrieving the exact stored request.

### 7.2. Why Does Spring Security Store the Request?

Per the Spring Security reference, outbound `LogoutRequest`s are stored to verify `RelayState` and `InResponseTo` on `LogoutResponse`. The docs note the default relies on the **HTTP session**; you can replace `Saml2LogoutRequestRepository` with an appropriate implementation via the DSL.

~~~java
// Configuration fragment inside SecurityFilterChain, NOT a standalone class.
http.saml2Logout(saml -> saml
    .logoutRequest(req -> req
        .logoutRequestRepository(myCustomLogoutRequestRepository)
    )
);
~~~

This snippet only shows the **extension point** when you actually have an implementation; no `myCustomLogoutRequestRepository` bean exists automatically. To build a durable repository, inspect the exact interface for your version and address save/load/remove semantics, serialization, TTL, race conditions, and one-time consumption.

**Warning:** in RP-initiated SLO, the local session is often invalidated before the browser leaves for the IdP. Do not write a listener that wipes request correlation when invalidating the session. If customizing the repository, ensure the framework can still retrieve the request after local cleanup per your actual lifecycle.

### 7.3. Two Nodes and a Load Balancer

~~~text
Browser -> Node 1: LogoutRequest _req1, RelayState rs1
             |
             | persistent/replicated request state
             v
          Shared session/store
             ^
             |
Browser -> Node 2: callback rs1, InResponseTo _req1
~~~

If Node 2 cannot find the original request, never "fall back" to picking a registration solely from IdP Issuer or trying verification keys from all IdPs. That is a **correlation failure**: fail closed and fix session affinity, Spring Session, shared storage, or a custom `Saml2LogoutRequestRepository` with TTL and atomic consumption.

**Important store rules:**

1. Generate unguessable, binding-appropriate request IDs and state, never shared across tenants.
2. Store a record with `registrationId`, tenant/trust scope, `LogoutRequest ID`, `RelayState`, and deadline.
3. On callback, verify every constraint against the original request.
4. Mark consumed / delete the record **atomically** so two nodes cannot both accept it.
5. Enforce a bounded TTL; responses arriving after expiry follow late-response policy rather than extending indefinitely.
6. Avoid storing full raw XML, `NameID`, and PII in the request-store record unless strictly necessary.
7. Even with metadata/registration refresh, define a policy for **the trust config version used when issuing the request** and handle key rollover transparently.

### 7.4. When Registration Config Changed Between Request and Callback

Example:

~~~text
T0: SP sends LogoutRequest for partner-a under IdP key A.
T1: IdP rotates key: trusted metadata adds B.
T2: Browser returns LogoutResponse signed with B to SP.
~~~

You need an explicit rollover/trust policy: signing with B may be accepted if B is in the current trusted set for that exact IdP/registration, yet rotation must never **switch the attempt to registration B / tenant B**. Conversely, if A was compromised and revoked, never restore A just to accept a pending callback.

You can store `config_version`/trust version on the attempt for auditing. Accepting pre-/post-rotation keys must obey security policy rather than hardcoding "all old keys stay OK" or "any request issued under A must be signed with A."

## 8. Verification Flow for an RP-Initiated Callback

### Step 1 — Classify the Message Without Trusting Content Yet

`SAMLResponse` on the logout endpoint can carry a **`LogoutResponse`**, distinct from a `SAMLResponse` sent to the login Assertion Consumer Service. Never use a generic handler that decodes XML and trusts unverified `Issuer`/`NameID` to establish a session.

Use Spring/OpenSAML's safe parsers and binding handlers with payload size limits and XXE/XML Signature Wrapping protections properly configured.

### Step 2 — Restore the Original Attempt

Use the framework-configured `RelayState`/request repository to retrieve the original `LogoutRequest`. If absent: **`REJECT_NO_ORIGINAL`**. For RP-initiated callbacks, never accept an unsolicited response merely because it carries a valid signature.

### Step 3 — Pin the Registration from the Original Attempt

Look up `RelyingPartyRegistrationRepository.findByRegistrationId(original.registrationId)`; confirm the initial mapping matches the right tenant/SP entity ID and has not expired. If the URL carries a route hint differing from the original registration, **`REJECT_CROSS_REGISTRATION`**; never let the browser re-choose.

### Step 4 — Signature and Source

Verify the signature per SAML binding using the verification credentials of the **IdP belonging to the original registration**, and verify `Issuer` and trusted role/metadata. Never accept an arbitrary cert inside `ds:KeyInfo` or "try every certificate until one verifies" to infer a tenant.

### Step 5 — Destination and IDs

Verify `Destination` matches the SP's published public SLO callback URL (scheme/host/path) for that registration. Verify `InResponseTo` matches the exact outbound original request ID, not just a similar string. `RelayState` must match the SP-issued state.

**Never compare `Destination` against SP entity ID:** both may be URLs, yet they carry different meanings. `Destination` is the **endpoint URL**, whereas entity ID is the SP's identifier.

### Step 6 — Validity Window, Status, and Replay

Check `IssueInstant`/timestamps/`NotOnOrAfter` where applicable, internal deadline, and unconsumed request state. Interpret `Status` per profile. If the IdP returns nested `PartialLogout` under `Success`, the UX must still report that some participants did not confirm; if no response returns, never assume global success.

### Step 7 — Atomic Finalization

Consume the original attempt once, write the audit record with registration and tenant, and report the certainty level. **Never recreate a logged-out session** when the callback fails or arrives late.

## 9. Registration Mix-Up Scenarios to Defend Against

| Scenario | Wrong Implementation | Correct Control |
| --- | --- | --- |
| A's callback carries `?registrationId=B`. | Uses B's trust/tenant; may log wrong success. | Compare path hint against original A; reject mismatch. |
| Two tenants share one IdP Issuer. | Picks first tenant matching issuer. | RP callback uses original request; AP request needs unambiguous tenant route/scope. |
| Two IdPs emit the same `NameID` and `SessionIndex`. | Terminates wrong user/tenant's session. | Scope by issuer/registration/SP + validated session info. |
| Guessable or unchecked `RelayState`. | Request mix-up or misbound callback. | Opaque `RelayState`, request lookup, `InResponseTo` check. |
| `LogoutResponse` validly signed by another IdP. | Switches to the IdP whose cert verifies. | Pin cert/trust scope from original registration. |
| `LogoutResponse` has wrong `Destination`. | Accepts response meant for another SP. | Match against public SP callback URL. |
| Response lacks original request. | Accepts unsolicited SLO success. | Reject `no original` for RP-initiated callbacks. |
| Callback lands on node lacking HTTP session. | Resolver picks a random registration. | Properly designed shared correlation store/session; fail closed. |
| IdP sends AP-initiated request to shared callback. | Resolves wrong tenant from Issuer. | Verified resolver via endpoint + session + IdP contract. |
| Registration renames `registrationId` while attempts are pending. | Fails to find request / wrong restoration. | Controlled migration/alias window preserving context until TTL expires. |
| Key rollover occurs while logout is pending. | Uses another tenant's key to "fix" error. | Trust versioning/metadata pinning and rotation testing. |
| Late response arrives after attempt consumed. | Replay alters audit or re-authenticates. | Reject replay/expired; local logout remains intact. |

## 10. Java 17: Modeling Callback Correlation Against Original Request

The following standalone example **does not parse SAML XML and does not verify real cryptographic signatures**. `VerifiedCallback` in the code is strictly **mock data simulating the output of a trusted SAML validator**; the boolean flag in the demo **must never replace real signature checks in production**.

Goal: demonstrate that **even a matching Issuer is insufficient** when two registrations share an IdP; the original request and exact registration/trust scope must match.

### 10.1. File `SloCallbackBindingDemo.java`

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class SloCallbackBindingDemo {

    record Registration(
        String registrationId,
        String tenantId,
        String idpEntityId,
        String spEntityId,
        String sloCallback,
        String verificationKeyId) {
    }

    record Attempt(
        String logoutRequestId,
        String relayState,
        String registrationId,
        String tenantId,
        String spEntityId,
        long expiresAt) {
    }

    // ONLY mock data simulating post-SAML-provider validation.
    record VerifiedCallback(
        String inResponseTo,
        String relayState,
        String issuer,
        String destination,
        String validatedRegistrationId,
        String validatedKeyId,
        boolean signatureTrusted) {
    }

    enum Decision {
        ACCEPTED,
        NO_ORIGINAL_REQUEST,
        UNTRUSTED_SIGNATURE,
        EXPIRED,
        REQUEST_ID_MISMATCH,
        REGISTRATION_MISMATCH,
        TENANT_CONTEXT_MISMATCH,
        ISSUER_MISMATCH,
        DESTINATION_MISMATCH,
        WRONG_KEY_SCOPE,
        REPLAY
    }

    static Decision check(
            VerifiedCallback callback,
            Map<String, Attempt> originalByRelay,
            Map<String, Registration> trustedRegistrations,
            Set<String> alreadyConsumed,
            long now) {

        Attempt original = originalByRelay.get(callback.relayState());
        if (original == null) {
            return Decision.NO_ORIGINAL_REQUEST;
        }

        Registration registration =
            trustedRegistrations.get(original.registrationId());

        if (registration == null || !callback.signatureTrusted()) {
            return Decision.UNTRUSTED_SIGNATURE;
        }

        if (now >= original.expiresAt()) {
            return Decision.EXPIRED;
        }

        if (!original.logoutRequestId().equals(callback.inResponseTo())) {
            return Decision.REQUEST_ID_MISMATCH;
        }

        if (!registration.registrationId().equals(
                callback.validatedRegistrationId())) {
            return Decision.REGISTRATION_MISMATCH;
        }

        if (!registration.tenantId().equals(original.tenantId())
                || !registration.spEntityId().equals(original.spEntityId())) {
            return Decision.TENANT_CONTEXT_MISMATCH;
        }

        if (!registration.idpEntityId().equals(callback.issuer())) {
            return Decision.ISSUER_MISMATCH;
        }

        if (!registration.sloCallback().equals(callback.destination())) {
            return Decision.DESTINATION_MISMATCH;
        }

        if (!registration.verificationKeyId().equals(
                callback.validatedKeyId())) {
            return Decision.WRONG_KEY_SCOPE;
        }

        if (!alreadyConsumed.add(original.logoutRequestId())) {
            return Decision.REPLAY;
        }

        return Decision.ACCEPTED;
    }

    public static void main(String[] args) {
        long now = Instant.parse("2030-05-01T10:00:00Z")
            .getEpochSecond();

        String issuer = "https://idp-shared.example/saml";
        String callbackUrl = "https://orders.example/logout/saml2/slo";

        Registration a = new Registration(
            "shared-a", "tenant-C", issuer,
            "https://orders.example/saml2/sp/shared-a",
            callbackUrl, "shared-idp-key");

        Registration b = new Registration(
            "shared-b", "tenant-D", issuer,
            "https://orders.example/saml2/sp/shared-b",
            callbackUrl, "shared-idp-key");

        Map<String, Registration> trusted = Map.of(
            a.registrationId(), a,
            b.registrationId(), b);

        Attempt reqA = new Attempt(
            "_req-A", "relay-A", "shared-a", "tenant-C",
            a.spEntityId(), now + 60);

        Attempt reqB = new Attempt(
            "_req-B", "relay-B", "shared-b", "tenant-D",
            b.spEntityId(), now + 60);

        Map<String, Attempt> requests = Map.of(
            reqA.relayState(), reqA,
            reqB.relayState(), reqB);

        // Concurrent set in a single JVM; production needs an atomic store
        // shared across multiple nodes.
        Set<String> consumed = ConcurrentHashMap.newKeySet();

        VerifiedCallback goodA = new VerifiedCallback(
            "_req-A", "relay-A", issuer, callbackUrl,
            "shared-a", "shared-idp-key", true);

        VerifiedCallback goodB = new VerifiedCallback(
            "_req-B", "relay-B", issuer, callbackUrl,
            "shared-b", "shared-idp-key", true);

        VerifiedCallback wrongTenant = new VerifiedCallback(
            "_req-A", "relay-A", issuer, callbackUrl,
            "shared-b", "shared-idp-key", true);

        VerifiedCallback wrongRequest = new VerifiedCallback(
            "_req-B", "relay-A", issuer, callbackUrl,
            "shared-a", "shared-idp-key", true);

        VerifiedCallback wrongIssuer = new VerifiedCallback(
            "_req-A", "relay-A", "https://other-idp.example/saml",
            callbackUrl, "shared-a", "shared-idp-key", true);

        VerifiedCallback wrongDestination = new VerifiedCallback(
            "_req-A", "relay-A", issuer,
            "https://other-sp.example/logout/saml2/slo",
            "shared-a", "shared-idp-key", true);

        VerifiedCallback badSignature = new VerifiedCallback(
            "_req-A", "relay-A", issuer, callbackUrl,
            "shared-a", "shared-idp-key", false);

        VerifiedCallback noOriginal = new VerifiedCallback(
            "_req-X", "relay-unknown", issuer, callbackUrl,
            "shared-a", "shared-idp-key", true);

        System.out.println("unknown=" +
            check(noOriginal, requests, trusted, consumed, now));
        System.out.println("crossTenant=" +
            check(wrongTenant, requests, trusted, consumed, now));
        System.out.println("wrongRequest=" +
            check(wrongRequest, requests, trusted, consumed, now));
        System.out.println("wrongIssuer=" +
            check(wrongIssuer, requests, trusted, consumed, now));
        System.out.println("wrongDestination=" +
            check(wrongDestination, requests, trusted, consumed, now));
        System.out.println("badSignature=" +
            check(badSignature, requests, trusted, consumed, now));
        System.out.println("expired=" +
            check(goodB, requests, trusted, consumed, now + 61));
        System.out.println("tenantA=" +
            check(goodA, requests, trusted, consumed, now));
        System.out.println("replay=" +
            check(goodA, requests, trusted, consumed, now));
        System.out.println("tenantB=" +
            check(goodB, requests, trusted, consumed, now));
    }
}
~~~

### 10.2. Compile and Run

With JDK 17+:

~~~bash
javac --release 17 SloCallbackBindingDemo.java
java SloCallbackBindingDemo
~~~

**Exact stdout:**

~~~text
unknown=NO_ORIGINAL_REQUEST
crossTenant=REGISTRATION_MISMATCH
wrongRequest=REQUEST_ID_MISMATCH
wrongIssuer=ISSUER_MISMATCH
wrongDestination=DESTINATION_MISMATCH
badSignature=UNTRUSTED_SIGNATURE
expired=EXPIRED
tenantA=ACCEPTED
replay=REPLAY
tenantB=ACCEPTED
~~~

### 10.3. Lessons from the Code

- Both registrations share `Issuer`, `SLO callback URL`, and verification key, yet differ in SP entity ID and tenant; knowing only the Issuer or cert is **insufficient** to select the tenant.
- `originalByRelay` simulates looking up an SP-created request, not browser-defined data.
- `validatedRegistrationId` and `signatureTrusted` are **simulated**: in production they must come from the SAML provider verifying the signing key against the **original registration**, never from HTTP query/body params.
- `alreadyConsumed.add(...)` prevents replay within one JVM; multiple instances require Redis/SQL transactions or another store offering **atomic consume + TTL**.
- `EXPIRED` uses a 60-second deadline **purely for illustration**, not a default timeout in Spring Security or SAML2.
- `ACCEPTED` only proves the simulated rules passed; **it does not invalidate an HTTP session** or replace SAML cryptographic validation.

**Most important case:** `wrongTenant` has the right IdP issuer and verification key yet the wrong registration—and is still rejected. That is the difference between "knowing who signed" and "knowing which transaction/tenant this message belongs to."

## 11. Spring Boot 3.3 / Spring Security 6.3: Two-Registration SLO Example

The sample below demonstrates **how to configure two independent SP–IdP relationships**, leaving SAML logout callback handling to the framework. It uses only the default SLO filters/validators; adding tenant auditing and a custom request store requires implementing the dedicated extension points in Section 12.

### 11.1. Project Structure

~~~text
multi-tenant-slo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/slo/
    │   ├── MultiTenantSloApplication.java
    │   ├── SecurityConfig.java
    │   └── PageController.java
    └── resources/
        ├── application.yml
        └── templates/
            ├── index.html
            └── signed-out.html
~~~

### 11.2. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'multi-tenant-slo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    maven { url 'https://build.shibboleth.net/maven/releases/' }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

### 11.3. Main Application

`src/main/java/com/example/slo/MultiTenantSloApplication.java`:

~~~java
package com.example.slo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiTenantSloApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiTenantSloApplication.class, args);
    }
}
~~~

### 11.4. `application.yml`

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            entity-id: "https://orders.example/saml2/sp/partner-a"
            assertingparty:
              metadata-uri: ${IDP_A_METADATA_URI}
            signing:
              credentials:
                - private-key-location: "file:${SP_A_SIGNING_KEY}"
                  certificate-location: "file:${SP_A_SIGNING_CERT}"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
              binding: POST

          partner-b:
            entity-id: "https://orders.example/saml2/sp/partner-b"
            assertingparty:
              metadata-uri: ${IDP_B_METADATA_URI}
            signing:
              credentials:
                - private-key-location: "file:${SP_B_SIGNING_KEY}"
                  certificate-location: "file:${SP_B_SIGNING_CERT}"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
              binding: POST
~~~

**Reading the configuration:**

- Both `registrationId`s and SP entity IDs are distinct.
- Each IdP metadata URL is **admin-provided via environment variables**; it must point to real trusted issuers/endpoints/certificates.
- SP signing credentials sign `LogoutRequest`/`LogoutResponse` per contract. Never commit private keys in source control or expose SAML signing keys to browsers.
- Both SP registrations may publish **the same SLO callback URL**. For RP-initiated callbacks, the original request must still determine the registration; never use the shared host/path as a tenant key.
- `singlelogout.url` is the **SP endpoint**, whereas the IdP LogoutService endpoint comes from `SingleLogoutService` in IdP metadata.
- The sample assumes **both IdPs support SLO** with agreed binding and signing. If an IdP does not support SLO, keep that registration local-only; never guess URLs or enable SLO blindly.
- Register the exact public entity ID/ACS/SLO URLs at each IdP. `https://orders.example` only illustrates the integration host; in real runs, replace with an organization-owned deployment domain.
- Behind reverse proxies/load balancers, configure trusted forwarded headers and a canonical HTTPS origin so `{baseUrl}` cannot be computed from an attacker-manipulated `Host` header.

**Multi-tenant with the same IdP:** you can point `IDP_A_METADATA_URI` and `IDP_B_METADATA_URI` to the same source, yet each SP registration must still be identified by the IdP using its exact SP entity ID and callback. If the IdP cannot distinguish two SP registrations per metadata/contract, fix the integration model rather than picking the tenant from a query param.

### 11.5. `SecurityConfig.java`

`src/main/java/com/example/slo/SecurityConfig.java`:

~~~java
package com.example.slo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            )
            .saml2Logout(saml -> saml
                .logoutUrl("/saml2/logout")
            )
            .build();
    }
}
~~~

**Two distinct operations:**

- `POST /logout` = local logout via Spring Security; under this split-endpoint config, it does not emit a `LogoutRequest`.
- `POST /saml2/logout` = user initiates SLO for the **current `Authentication`'s registration**, never selecting an arbitrary IdP from a query param.
- `/logout/saml2/slo` = default callback handling SAML `LogoutRequest`/`LogoutResponse`, owned by Spring filters.
- Never write a competing Spring MVC controller at that callback URL, and never bypass/disable default validators to pick a tenant yourself.
- Never disable CSRF globally; app-side forms require CSRF tokens. SAML callbacks are handled by SLO filters per binding/profile.
- Enabling `saml2Logout` does not create business authorization or tenant isolation: authorization remains the application's responsibility.

**Important note:** this example demonstrates only **standard framework routing/trust setup**. It does not implement a distributed custom `Saml2LogoutRequestRepository` or prove that two registrations sharing an issuer handle every AP-initiated case unambiguously.

### 11.6. `PageController.java`

`src/main/java/com/example/slo/PageController.java`:

~~~java
package com.example.slo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/")
    public String index() {
        return "index";
    }

    @GetMapping("/signed-out")
    public String signedOut() {
        return "signed-out";
    }
}
~~~

### 11.7. `index.html`

`src/main/resources/templates/index.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8"/>
    <title>SAML2 Logout</title>
</head>
<body>
<h1>Logout in a Multi-IdP System</h1>
<p>
    SLO uses the currently logged-in user's registration.
    Never use a browser-supplied tenant parameter
    to switch to another IdP.
</p>

<form th:action="@{/logout}" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}"/>
    <button type="submit">Local Application Logout Only</button>
</form>

<form th:action="@{/saml2/logout}" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}"/>
    <button type="submit">Request SAML Single Logout</button>
</form>
</body>
</html>
~~~

### 11.8. `signed-out.html`

`src/main/resources/templates/signed-out.html`:

~~~html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"/>
    <title>Signed Out</title>
</head>
<body>
<h1>Signed Out of This Application</h1>
<p>
    Your session at this application has ended. Sessions at the IdP
    or other applications may still exist if SLO
    is unsupported or unconfirmed.
</p>
</body>
</html>
~~~

**Note:** this page covers local logout; when SLO runs through the browser, the final landing page may be decided by the IdP. If your system needs to show `Success`/`PartialLogout` status, add state tracking and success/failure handling integrated with the validator for your Spring Security version.

### 11.9. Running and Testing with a Test IdP

With JDK 17 and the appropriate Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

In Windows PowerShell, use `.\gradlew.bat bootRun`.

Provide real IdP metadata and signing key/certificate pairs, and register the exact SP entity ID/ACS/SLO callback at both IdPs. Missing metadata or keys will prevent startup or cause SLO to fail; the code **contains no mock IdP to self-authenticate**.

1. Log in with registration `partner-a` via `/saml2/authenticate/partner-a`; confirm the principal belongs to IdP A.
2. Submit `POST /saml2/logout` with the CSRF token: confirm the browser redirects to IdP A, not B.
3. Have IdP A return a signed `LogoutResponse` with the matching `InResponseTo`; verify validation and outcome.
4. Repeat with `partner-b` and confirm IdP B is used.
5. Use a test IdP sharing the same issuer across two registrations to test ambiguity; if the framework needs an extra resolver, **never** rely on the basic demo alone to assume that case is solved.
6. Test callbacks with a mismatched registration hint or mismatched original request ID; confirm rejection without updating another tenant.
7. Test callbacks landing on another node to verify the session/request repository and correlation.

**Demo limitations:** it does not implement custom audit state or a shared correlation store; cross-node, concurrent-consume, and shared-issuer multi-tenant tests require extra production-grade infrastructure.

## 12. Spring Security Extension Points to Know

### 12.1. Related Classes

| Class / Interface | Role |
| --- | --- |
| `RelyingPartyRegistrationRepository` | Returns trusted metadata/config for a registration ID. |
| `RelyingPartyRegistrationResolver` | Resolves registration from request/context when customization is needed; does not replace SAML verification. |
| `Saml2AuthenticatedPrincipal` | When user is logged in, exposes `getRelyingPartyRegistrationId()`. |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | After local logout, creates and dispatches `LogoutRequest` to the principal's IdP. |
| `Saml2LogoutRequestResolver` | Creates a signed `LogoutRequest` from authentication/registration. |
| `Saml2LogoutRequestRepository` | Saves/loads/removes requests to verify `RelayState`/`InResponseTo`. |
| `Saml2LogoutResponseFilter` | Receives `LogoutResponse` for RP-initiated flows. |
| `Saml2LogoutResponseValidator` | Validates response against registration and original request. |
| `Saml2LogoutRequestFilter` | Receives AP-initiated `LogoutRequest`. |
| `Saml2LogoutRequestValidator` | Validates `LogoutRequest` against matching registration/Authentication. |
| `Saml2LogoutResponseResolver` | Creates `LogoutResponse` for AP-initiated flows. |

OpenSAML 4/5 implementation names and the placement of some extension points vary across releases. Spring Security **6.3.5** docs confirm `Saml2LogoutResponseValidator` checks signature, issuer, destination, status, and correspondence with the original logout request. **Never replace the validator with code that only checks `tenantId`.**

### 12.2. Configuring a Custom Request Repository

Once you have an implementation matching the exact interface/version:

~~~java
// DSL snippet for SecurityFilterChain; requires a real customRepository bean.
http.saml2Logout(saml -> saml
    .logoutRequest(req -> req
        .logoutRequestRepository(customRepository)
    )
);
~~~

Requirements for production use:

- `saveLogoutRequest` persists before the browser leaves the SP.
- `loadLogoutRequest` retrieves the exact request by correlation context, never returning another session's request.
- `removeLogoutRequest`/consume prevents replay/races between two callbacks.
- TTL, key version, and binding to issuer/registration/tenant are explicitly managed.
- Multi-node deployments use a shared store/replication when callbacks are not guaranteed to hit the same node.
- State is not lost simply because the local HTTP session was invalidated.
- Preserves the exact semantics expected by `Saml2LogoutResponseValidator`.

**Never rely solely on a cookie holding a raw `LogoutRequest` or client-assembled JSON as a trusted repository.** Even with a signed token, you still need expiry, replay prevention, and binding to the right user/tenant.

### 12.3. Configuring a Custom Validator

Spring Security allows:

~~~java
// DSL snippet; customValidator must delegate/trust per exact version.
http.saml2Logout(saml -> saml
    .logoutResponse(response -> response
        .logoutResponseValidator(customValidator)
    )
);
~~~

This is **not a standalone class**. Check exact APIs and implementations for your version. A tenant-aware validator should:

1. **Invoke the default delegate** to verify signature, Issuer, Destination, status, and match to the original request.
2. If the delegate returns an error, **preserve the error**—never flip it to success.
3. On a valid result, check the original registration/tenant context, nonce, and issued attempt state.
4. Fail closed whenever multi-tenant ambiguity remains unresolved.
5. Never parse raw HTTP `SAMLResponse` independently and trust an XML element other than the one the framework verified (XML Signature Wrapping risk).

### 12.4. Custom Resolver and IdP Selection

If the app handles IdP-initiated SLO on a shared callback without an active Authentication/session, a custom resolver may be required. Still, **a resolver only picks a candidate registration**—it never lets a request bypass SAML verification.

Never write a resolver like:

~~~java
// BROKEN PATTERN: do not use in multi-tenant systems.
String selected = httpRequest.getParameter("registrationId");
return registrations.findByRegistrationId(selected);
~~~

Without source, signature, and tenant-scope checks, an attacker can pick an arbitrary IdP trust context. A sound design relies on **trusted route contracts, allowlisted issuer/SP context, validated subject/session binding**, and **zero ambiguity**. When an IdP issuer is shared across multiple registrations, disambiguate using profile/metadata-compliant evidence or reject the AP request.

## 13. Correlation and Audit Database: Design Pattern

Example table for multi-node production (PostgreSQL):

~~~sql
CREATE TABLE saml_slo_attempt (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    logout_request_id VARCHAR(255) NOT NULL UNIQUE,
    relay_state_hash VARCHAR(128) NOT NULL UNIQUE,
    registration_id VARCHAR(120) NOT NULL,
    tenant_id VARCHAR(120) NOT NULL,
    idp_entity_id TEXT NOT NULL,
    sp_entity_id TEXT NOT NULL,
    sp_slo_callback TEXT NOT NULL,
    config_version VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    outcome VARCHAR(40) NOT NULL
        CHECK (outcome IN (
            'PENDING', 'ACCEPTED', 'PARTIAL', 'FAILED',
            'EXPIRED', 'INVALID_RESPONSE', 'UNKNOWN'
        ))
);
CREATE INDEX saml_slo_attempt_due
    ON saml_slo_attempt (expires_at)
    WHERE consumed_at IS NULL;
~~~

This is a **conceptual schema**, not a runnable `Saml2LogoutRequestRepository` by itself. The schema uses `relay_state_hash` to avoid storing plaintext state where policy requires, though lookups must stay consistent with token format, hash keys, and rotation. `config_version` supports audits and rollovers; never skip current-trust checks merely because an older version was recorded.

Considerations:

- Request correlation comes from the trusted request generator, never browser-submitted JSON.
- Perform atomic claims inside a transaction—e.g., transition `PENDING → ACCEPTED` only when `consumed_at IS NULL` and before `expires_at`.
- An invalid response must never alter the outcome of another request.
- `tenant_id` in the table comes from the trusted registration/user context, never an arbitrary HTTP header.
- With concurrent callbacks for the same request ID, at most one valid callback may succeed.
- Purge/retain records per retention policy; logs must omit `NameID`, `SessionIndex`, private keys, and raw SAML payloads.

### 13.1. Atomic Consume SQL Example

~~~sql
-- After the SAML validator has verified the response and context:
UPDATE saml_slo_attempt
SET consumed_at = CURRENT_TIMESTAMP,
    outcome = 'ACCEPTED'
WHERE logout_request_id = :request_id
  AND registration_id = :registration_id
  AND tenant_id = :tenant_id
  AND outcome = 'PENDING'
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Require **`affected rows == 1`** before marking an attempt accepted. This is strictly the **atomic state transition**; it does not check signature, `RelayState`, `InResponseTo`, issuer, `Destination`, or `Status`. If the IdP returns `PartialLogout`, record `PARTIAL` rather than `ACCEPTED` per your business model. Never execute this SQL before the SAML message has been verified.

## 14. Key Rollover, Metadata Refresh, and Registration Changes

### 14.1. An IdP Rotates Its Cert While a `LogoutRequest` Is in Flight

At T0 the SP saves the original request for `partner-a`. At T1 the IdP publishes a new signing key and the SP refreshes trusted metadata. At T2 the IdP sends a `LogoutResponse` signed with the new key.

Requirements:

1. Preserve the **original registration binding** until request expiry; never switch to a different registration because of the new key.
2. Evaluate the key against the **trust policy** and accepted metadata of that specific IdP/registration.
3. For a valid A → A+B → B rotation, test acceptance accordingly. If A was compromised, remove A immediately per incident policy.
4. Never restore a revoked key solely because an older request is still pending.
5. Test responses arriving after metadata refresh across different nodes.

### 14.2. Renaming `registrationId` Without Changing SAML Entity IDs

`registrationId` is a config key. Renaming `partner-a` to `supplier-a` while SLO attempts are pending can cause `Saml2LogoutRequestRepository` holding the old ID to fail lookups.

Typical solutions include keeping a controlled compatibility alias/registration for a brief window or draining/closing attempts before renaming, governed by migration policy and auditing. **Never fall back across all registrations to see which one verifies.**

### 14.3. Changing SP Entity ID or IdP Issuer

This is a **trust identity change**, far more serious than renaming `registrationId`. An original request issued for the old SP/IdP is not automatically valid for the new entity ID. Coordinate metadata, certificates, SLO URLs, tenant mappings, and cutover plans; avoid uncontrolled aliases that widen the trust boundary.

## 15. When Callbacks Are Lost or Messages Contain Errors

| Event | Appropriate State | What Must Never Be Done |
| --- | --- | --- |
| Original `LogoutRequest` not found | `NO_ORIGINAL_REQUEST` | Guess registration by issuer and accept response. |
| Original request exceeded TTL | `EXPIRED` / late callback | Accept anyway just to "avoid logout errors." |
| Invalid SAML signature/Issuer | `INVALID_RESPONSE` | Try another IdP's cert arbitrarily. |
| `InResponseTo` mismatch | `REQUEST_ID_MISMATCH` | Match to an attempt by `NameID`/tenant hint. |
| Tampered `RelayState` | `CORRELATION_FAILURE` | Synthesize a new request with the received XML's ID. |
| Tenant context mismatch | `REGISTRATION_MISMATCH` | Log out the wrong tenant or report success for another tenant. |
| IdP reports `PartialLogout` | `PARTIAL_LOGOUT` | Claim all other SPs logged out. |
| Browser never returns | `TIMEOUT_UNKNOWN` | Assert with certainty whether the IdP logged out or not. |
| Duplicate / replayed callback | `REPLAY_REJECTED` | Re-run cleanup or record success a second time. |
| Local session already destroyed | `LOCAL_LOGOUT_DONE` | Restore the session just because the callback failed. |

**Never return raw issuer, `NameID`, `SessionIndex`, stack traces, or verbatim SAML XML to the browser.** Display a simple message to the user: "Your application session has ended; federated sign-out elsewhere could not be confirmed" when no verified response was received.

## 16. Logging, Metrics, and Forensics Without Leaking Identifiers

Suggested structured logs:

~~~text
event=saml_slo_started
registration_id=partner-a
tenant_id=tenant-A
attempt_id=opaque-internal-id
request_id_hash=...
idp_issuer_ref=approved-idp-ref
slo_callback_ref=approved-callback-ref

event=saml_slo_response_checked
attempt_id=opaque-internal-id
correlation=PASS
issuer_and_signature=PASS
destination=PASS
result=PARTIAL
~~~

The `...` indicates deployment-generated operational values; **never log raw payloads**. Keep log fields bounded and never use `NameID`, email, or `SessionIndex` as metric labels.

Suggested metrics (not built into Spring Security):

~~~text
saml_slo_callback_total{registration_id,result}
saml_slo_registration_mismatch_total{registration_id}
saml_slo_no_original_total{registration_id}
saml_slo_replay_total{registration_id}
saml_slo_late_callback_total{registration_id}
saml_slo_request_store_load_failure_total{node}
saml_slo_ap_initiated_total{registration_id,result}
~~~

Use bounded, managed `registration_id`/`node` values; never put callback request IDs or `RelayState` in high-cardinality labels. Alert on spikes in `NO_ORIGINAL_REQUEST`, which often indicate lost HTTP sessions/correlation stores, proxy/cookie/`SameSite` issues, node misconfiguration, TTL expiry, or replay attacks.

## 17. Essential Test Matrix

| ID | Scenario | Expected Outcome |
| --- | --- | --- |
| R01 | SP A issues `LogoutRequest`, IdP A returns `LogoutResponse` with valid Issuer/ID/destination/signature. | Accepted under original registration A. |
| R02 | Callback carries `registrationId=B` while original was A. | Rejects cross-registration; never binds to B. |
| R03 | IdP A and B both emit the same `NameID` value. | Never uses the value as a tenant/trust key. |
| R04 | Two registrations share IdP issuer and shared callback URL. | RP callback resolves via original request, not Issuer alone. |
| R05 | Two registrations share IdP issuer and public verification key. | Still requires original SP scope/tenant binding. |
| R06 | `LogoutResponse` carries `InResponseTo` from another request. | Rejects mismatch. |
| R07 | Valid `RelayState` yet untrusted signature. | Rejects signature. |
| R08 | Valid signature yet wrong Issuer. | Rejects issuer. |
| R09 | Valid signature yet `Destination` targets another SP. | Rejects destination. |
| R10 | Callback has no original request. | Rejects unsolicited RP `LogoutResponse`. |
| R11 | Callback lands on another node with working shared store. | Verifies against the exact original registration. |
| R12 | Callback lands on another node, store lacks request. | Rejects/fails closed; never guesses tenant. |
| R13 | Duplicate/replayed identical `LogoutResponse`. | Consumed once; subsequent attempts rejected. |
| R14 | Callback arrives after TTL. | Expired/late response per policy; never restores session. |
| R15 | Browser never returns from IdP callback. | `TIMEOUT_UNKNOWN`; local logout remains effective. |
| R16 | IdP metadata rotates signing cert A→B while request is pending. | Trusts the right IdP; never picks another registration. |
| R17 | SP `registrationId` renamed between request and callback. | Bounded migration/alias or fails closed. |
| R18 | AP-initiated `LogoutRequest` from IdP A for A's session. | Verifies and logs out only the matching session/tenant. |
| R19 | AP-initiated `LogoutRequest` from IdP A, `NameID` matches user in B. | Never logs out B's session. |
| R20 | AP-initiated with issuer shared across two tenants and no trusted route. | Rejects ambiguity. |
| R21 | AP-initiated request with invalid signature. | Rejects; never terminates sessions arbitrarily. |
| R22 | Replayed AP-initiated request. | Rejects duplicate per profile/policy. |
| R23 | SLO succeeds while local account belongs to another tenant. | Does not alter that tenant's permissions or data. |
| R24 | SP session already invalidated before callback. | Request repo still resolves original; does not rely on current principal. |
| R25 | IdP does not support SLO in metadata. | Local logout only; never fabricates requests. |
| R26 | Response has top-level `Success` + nested `PartialLogout`. | Records partial; never reports full federated success. |
| R27 | Valid `Requester`/`Responder` error. | Records failure per status; local logout stands. |
| R28 | SLO URL behind reverse proxy has wrong scheme/host. | Fix canonical base URL; never disable `Destination` validation. |
| R29 | Multi-node receives two concurrent callbacks for one request. | Atomic consume; no double-finalization. |
| R30 | Callback carries client-supplied XML/HTTP param `tenantId`. | Never used as trust/tenant authority. |

### 17.1. Integration Test Plan

1. Configure two test IdPs with distinct issuers and signing certs.
2. Configure two tenants sharing **the same issuer** with distinct SP entity IDs/registrations; test RP callbacks hitting the shared URL.
3. Run real logins and store the original SLO attempt via the standard repository.
4. Trigger SLO and return a valid `LogoutResponse`; measure correlation/replay handling and UX outcomes.
5. With a configurable test IdP, generate `LogoutResponse`s with wrong `InResponseTo`, wrong `Destination`, wrong signing key, and wrong Issuer.
6. Route a callback to Node 2 when the request started on Node 1; test both healthy shared storage and missing state.
7. Trigger an AP-initiated request from IdP A while a session exists in tenant B with a matching `NameID`.
8. Test metadata refresh/rotation during outstanding SLO requests without relaxing key trust.
9. Test late, partial, and missing responses; verify status reporting is accurate.
10. Keep CSRF enabled for local logout while letting Spring SAML filters handle inbound protocol flows per profile.

**Note:** The Java demo in Section 10 tests only **post-validation simulated rules** without real cryptography. The project in Section 11 uses the Spring SAML2 framework yet **does not automatically cover custom multi-tenant resolvers/request-stores**; tests R02/R04/R05/R11/R20/R29 require matching infrastructure/code and live verification.

## 18. Common Implementation Mistakes

| Broken Approach | Why It Is Wrong | Proper Fix |
| --- | --- | --- |
| "Callback has `Issuer=A`, so `registration=A`." | One Issuer can map to multiple registrations/tenants. | Original request or resolver with trusted disambiguation. |
| "Path `/slo/B` proves tenant B." | Any browser can call that path. | Verify message and reconcile original B/tenant scope. |
| "Just check signature against any cert." | Another IdP or attacker cert can sign fabricated XML. | Verification credentials belonging strictly to the right registration. |
| "Same `NameID`/`SessionIndex` means same user." | IdP/tenant namespaces differ. | Key by issuer/SP scope and session binding. |
| "Original request missing, so reconstruct from `InResponseTo`." | Attacker can forge request/correlation. | Fail closed; investigate repository/session. |
| "Callback lacks `Authentication`, so read tenant from query." | SP normally invalidated the session before the SLO callback. | Request repository retains initial context. |
| "Renamed `registrationId` mid-flight, so try all tenants." | Widens trust boundary. | Controlled cutover/alias with TTL. |
| "Fetch metadata URL from callback HTTP body." | Trust driven by untrusted input. | Use only approved trusted metadata/config. |
| "Use custom XML parser to read status." | Risks XML Signature Wrapping / reading unsigned elements. | Use Spring/OpenSAML validators and extension points. |
| "Skip `InResponseTo` because IdP returned `Success`." | Detaches response from any issued request. | Reject when original/correlation is absent. |
| "Local logout failed, yet report SLO success." | Application session was never cleared. | Verify each logout layer independently. |
| "SLO failed, so restore old local session." | Session already invalidated; unsafe. | Require fresh login when needed. |
| "One request ID can complete multiple times." | Replay/race or corrupted audit. | Atomic consume / idempotency. |
| "Use HTTP `Host` header to build trusted `Destination`." | Host header injection / misconfigured reverse proxy. | Canonical HTTPS base URL from trusted config. |

## 19. Self-Check Questions

**1. Why doesn't `registrationId` necessarily appear in the default SLO callback?**  
Because Spring can derive the registration from the currently logged-in user or the saved original `LogoutRequest` for RP-initiated callbacks. This is safe only if the message is still verified against that exact registration.

**2. The callback has the right IdP Issuer; is that enough to accept it?**  
No. You still need signature, `Destination`, request correlation, tenant context, and profile checks.

**3. When two tenants share an IdP issuer, how do you disambiguate an RP callback?**  
By the **original** `LogoutRequest`/`RelayState`/ID issued by the SP for the known registration—never by Issuer alone.

**4. What is `InResponseTo` for?**  
It references the exact `LogoutRequest` ID issued by the SP, blocking unsolicited and mixed-up responses.

**5. What if an RP-initiated `LogoutResponse` cannot locate an original request?**  
Fail closed. Never "reconstruct" an original request from response content or guess a registration.

**6. Does an AP-initiated `LogoutRequest` have an original SP `LogoutRequest`?**  
No. Resolve the trusted registration and matching user/session via IdP source, signature, `NameID`, and `SessionIndex`.

**7. Can IdP A's `SessionIndex` terminate an IdP B session?**  
No; the string is not unique across the federation.

**8. Why can't a signature from the same IdP distinguish two tenants of that IdP?**  
Because the signing source is identical; tenant/SP entity ID must be established from the original transaction or verified route/session context.

**9. When a callback hits Node 2 while the request started on Node 1, what should happen?**  
Use a multi-node session/request store; if not found, reject rather than guessing.

**10. If a callback URL moves to another host, can you fix it by turning off `Destination` validation?**  
No. Update the public URL, metadata, and reverse proxy while keeping validation enabled.

**11. What if a `LogoutResponse` has a valid signature yet carries another request's `InResponseTo`?**  
Reject the request mismatch; a valid signature never permits transferring results across attempts.

**12. After a callback verifies `Success`, can the user access another tenant's resources?**  
No. Logout never grants permissions; SP authorization must always remain independent.

## 20. Production Checklist

- [ ] Define every `registrationId` and SP–IdP trust relationship in the repository.
- [ ] Maintain clear boundaries for SP entity ID, IdP issuer, tenant, and SLO URLs.
- [ ] Correlate RP callbacks to the original `LogoutRequest` saved before local logout.
- [ ] Verify `RelayState` and `InResponseTo` accurately.
- [ ] Verify signature and Issuer using the certificate of the **exact registration**, never trying all certs to pick a tenant.
- [ ] Match `Destination` against the public callback URL, never confusing it with SP entity ID.
- [ ] Reject unsolicited RP `LogoutResponse`s when no original request exists.
- [ ] AP-initiated requests use an unambiguous resolver; `NameID`/`SessionIndex` are matched within the right IdP/tenant scope.
- [ ] Never select a tenant from path/query/body without verifying source and correlation.
- [ ] Session/`Saml2LogoutRequestRepository` survives local logout and cross-node callbacks as needed.
- [ ] TTL, atomic consumption, and replay protection are tested in multi-node setups.
- [ ] IdP key rotation and metadata refresh never alter the original registration binding.
- [ ] Never restore local `Authentication` when a callback is rejected or arrives late.
- [ ] Define explicit outcomes for `Success`, `Partial`, `Failure`, `Invalid`, and `Timeout Unknown`.
- [ ] Never log raw SAML XML, `NameID`, `SessionIndex`, private keys, or cookies in default logs.
- [ ] Enable SLO only for supported and tested IdPs; local-only logout always remains available.
- [ ] Reverse proxy, base URL, and certs align with IdP metadata.
- [ ] Cover R01–R30 in staging or an equivalent test suite.
- [ ] Never alter default validation layers solely to work around an interoperability error.
- [ ] When upgrading Spring Security/OpenSAML, verify Javadoc APIs and regression tests for that exact version.

## Key Takeaway

> **An RP-initiated SLO `LogoutResponse` must be correlated to the exact `LogoutRequest` issued by the SP—matching ID, `RelayState`, trusted IdP, registration, SP scope, and tenant.** A shared callback URL, a valid signature from an IdP, or a browser-supplied `registrationId` is **insufficient** to select the right tenant. For AP-initiated SLO, there is no original SP `LogoutRequest`; use an unambiguous resolver and verify source/session before clearing local sessions. Whenever evidence is insufficient, **fail closed**—never log out or record success against the wrong tenant.

### Official Documentation

- [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): request/response flows, shared callbacks, `Saml2LogoutRequestRepository`, filters/validators, and customizing SLO endpoints.
- [Spring Security 6.3.5 — `Saml2LogoutResponseValidator` Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/saml2/provider/service/authentication/logout/Saml2LogoutResponseValidator.html): default verification of signature, issuer, destination, status, and correspondence with the original request.
- [Spring Security 6.3.2 — `RelyingPartyRegistration` API](https://docs.spring.io/spring-security/site/docs/6.3.2/api/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html): SP/IdP pair and `registrationId`.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): registration resolution and `RelyingPartyRegistrationRepository` structure.
- [OASIS — SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `LogoutRequest`/`LogoutResponse`, `InResponseTo`, `Issuer`, `Status`, and `SessionIndex`.
- [OASIS — SAML V2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Single Logout Profile, bindings, message handling, and session participants.
- [OASIS — Metadata for SAML V2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `SingleLogoutService`, SP entity ID, and IdP entity ID.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): local logout handlers, session invalidation, and CSRF.

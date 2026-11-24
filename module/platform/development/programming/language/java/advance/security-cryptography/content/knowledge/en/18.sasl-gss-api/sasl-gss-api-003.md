# 18.3. SASL Mechanism Negotiation, Authentication Identity, and Authorization Identity

> Scope: SASL (Simple Authentication and Security Layer) in Java systems, in a GSS-API/Kerberos context; focuses on selecting an authentication mechanism and distinguishing the party that proved its identity from the identity the session is permitted to represent.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain why client and server must agree on a SASL mechanism before exchanging challenge/response messages, and who is responsible for choosing the mechanism.
2. Distinguish **authentication identity** (`authcid` or `authnId`) from **authorization identity** (`authzid`), even when both strings are identical.
3. Describe the default rule when `authzid` is omitted and the conditions for performing proxy/delegated authorization.
4. Recognize the boundary between authenticating via a mechanism (such as `GSSAPI`) and enforcing authorization policies.
5. Properly use the integration points `SaslClient`, `SaslServer`, `CallbackHandler`, and `AuthorizeCallback` in Java; avoid downgrades and `authzid` spoofing.

## 2. Three conceptual layers that are often conflated

**SASL is a framework**, not a standalone cryptographic algorithm. It plugs an authentication mechanism into an application protocol such as IMAP, SMTP, LDAP, or a custom protocol. The application protocol defines how the mechanism list is advertised, how messages are framed, how success/failure is reported, and how the session behaves after authentication.

**A mechanism** is the method by which both sides prove identity and optionally negotiate session protection services, such as `PLAIN`, `SCRAM-SHA-256`, `GSSAPI`, or `EXTERNAL`. Not every mechanism appears in every protocol or every Java provider.

**Identity** comprises two distinct concepts:

| Concept | Question it answers | Origin and usage |
| --- | --- | --- |
| Authentication identity (`authcid` / `authnId`) | **Who proved possession of the credentials?** | The server derives/verifies it from a password, Kerberos ticket, certificate, token, etc. according to the mechanism; never trust an unverified username sent by the client. |
| Requested authorization identity (`authzid`) | **Under which identity does the client want to act?** | The client may propose a different identity; syntax and normalization are defined by the application protocol. |
| Effective authorization identity | **After checking, who is the session actually allowed to represent?** | Decided by the server after authentication and delegation policy checks; used for the session context and subsequent access control. |

Example: service account `svc-report` logs in validly with Kerberos and proposes `authzid=reports-reader`. The server already knows `authcid=svc-report`, but must accept `reports-reader` only if policy grants `svc-report` the right to act for that identity. If user `alice` requests `authzid=admin` without permission, *the entire SASL exchange must be rejected*. Successfully authenticating `alice` does not make an unauthorized role-switch request valid.

**Important:** the SASL step checks permission to **act as an identity**; afterward, the application must still check which resources that identity may read, write, or delete (RBAC/ABAC/ACL). `authzid=admin` does not automatically grant administrative privileges.

## 3. Where does mechanism negotiation happen?

RFC 4422 states that **mechanism negotiation is specific to the application protocol**. Typically the server advertises its enabled mechanisms; the client intersects that set with its own capabilities and picks a mechanism that satisfies security policy and deployment constraints. SASL itself does not define a generic "NEGOTIATE" packet across all applications.

A typical session:

```text
(0) Establish channel, verify server/TLS if required by the protocol.
(1) S -> C: list of mechanisms accepted by server (e.g., GSSAPI, SCRAM-SHA-256, PLAIN)
(2) C: filter against local policy + available providers + credentials.
(3) C -> S: request AUTHENTICATE <selected mechanism> [initial response if applicable]
(4) S: verify that the mechanism is allowed on this connection.
(5) C <-> S: mechanism-specific response/challenge exchange.
(6) S: verify credentials -> determine authcid; determine requested authzid.
(7) S: verify whether authcid is permitted to represent authzid.
(8) S -> C: SUCCESS or FAILURE; only on success is an effective authzid established.
(9) Application uses the effective authzid to authorize each subsequent action.
```

### Policy-driven selection example

Suppose the server advertises `[PLAIN, GSSAPI, SCRAM-SHA-256]`, the client supports `[SCRAM-SHA-256, PLAIN]`, application policy forbids `PLAIN` and prefers `SCRAM-SHA-256`, and a compatible provider is present. The result is `SCRAM-SHA-256`. If the client supports only `PLAIN`, it must report **no acceptable mechanism** rather than silently lowering security requirements.

Do not infer the "strongest mechanism" solely from the server's advertised order: selection also depends on verified TLS, required protection level, credential type, server identity, provider support, downgrade resistance, and organizational policy.

**Downgrade risk:** the initial mechanism list may lie outside authenticated messages, so an on-path attacker could strip strong mechanisms to force the client toward a weak one. For protocols supporting STARTTLS, perform TLS as required, verify the certificate/hostname, and re-query capabilities per the protocol specification; never send passwords or tokens before the channel is adequately protected. Disable out-of-policy fallback. If the protocol allows, re-verify capabilities after an integrity-protected security layer is established to detect tampering.

### Pre-acceptance checks

- **Client side:** mechanism allowlist; local provider can actually instantiate `SaslClient`; appropriate credentials/JAAS setup; TLS and server verification meet requirements; no arbitrary fallback when a strong mechanism fails.
- **Server side:** advertise and accept only configured mechanisms; enforce per-connection conditions (e.g., allow `PLAIN` only over valid TLS); ensure a `SaslServer` provider exists; enforce size, timeout, and attempt limits.
- **Both sides:** agree on the mechanism per protocol rules, process messages in order, and never continue using the session if the exchange fails.

## 4. Authentication identity and authorization identity in real exchanges

### 4.1. Omitting authzid: the server derives it

The client may **omit** the authorization identity, or send an empty string when the mechanism/protocol permits. Under the SASL model, this asks the server to derive the appropriate identity from the authenticated credentials. It is often the same user, though *not necessarily the exact same string*: for example, Kerberos principal `alice@EXAMPLE.COM` might be mapped to application account `alice`.

### 4.2. Supplying authzid: a delegation request, not a command

When sending `authzid=bob`, the client is **proposing** that the server allow its `authcid` to act under the identity `bob`. The server must evaluate proxy/authorization rules rather than blindly setting the session user from the client-supplied field.

| Authenticated credentials | Requested authzid | Example policy | Outcome |
| --- | --- | --- | --- |
| `alice` | omitted | Server maps credentials to `alice` | Session holds `alice` permissions. |
| `alice` | `alice` | Self-authorization allowed | Session holds `alice` permissions. |
| `alice` | `admin` | No delegation permission | Reject the SASL exchange. |
| `svc-report` | `reports-reader` | Explicit authorization rule for this pair | Session holds `reports-reader` permissions. |
| `svc-report` | `root` | No rule | Reject, even though credentials are valid. |

Authorization rules must operate on **trusted canonical identifiers** (realm, tenant, case-sensitivity, principal mapping); normalize consistently on both sides to prevent `Alice`/`alice`, short names vs. full principals, or Unicode ambiguities from causing mistakes. Do not strip realms or tenants out of habit.

### 4.3. At the wire level: the PLAIN mechanism

RFC 4616 defines the UTF-8 payload of `PLAIN` in the format:

```text
[authzid] <NUL> authcid <NUL> password
```

`<NUL>` is the `0x00` byte, not a space or the literal character string "`<NUL>`". When no separate `authzid` is requested, the first field is **empty**. In `PLAIN`, both username and password are placed into the SASL message; the mechanism **provides neither confidentiality nor integrity** for the message, so channel protection such as previously verified TLS is mandatory. Never log or trace payloads, and never Base64-encode data and treat it as secured: Base64 is merely a data representation.

### 4.4. With GSSAPI/Kerberos

In the `GSSAPI` SASL mechanism, GSS-API establishes a security context from Kerberos credentials; this tells the server the authenticated principal. The target's service principal typically has the form `imap/mail.example.com@EXAMPLE.COM` (illustrative; the exact value must match the environment). The application still has to decide how to map that principal to an internal `authcid`, handle empty or requested `authzid`, and reject unauthorized delegation. A valid ticket does **not** mean the client may act as an arbitrary user.

Distinguish clearly:

- `GSS-API` is an API for establishing an abstract security context; Kerberos is a common underlying technology.
- `GSSAPI` is the name of a SASL mechanism that uses GSS-API services; it runs inside the `SaslClient` / `SaslServer` lifecycle.
- `javax.security.sasl.AuthorizeCallback` asks policy whether `authcid` may act as `authzid`. It does not replace Kerberos ticket verification.

## 5. Selected mechanisms to put choices in context

| Mechanism | Data used for authentication | Notes for selection and identity determination |
| --- | --- | --- |
| `GSSAPI` | GSS-API context, typically a Kerberos ticket | Requires realm, principal/service name, ticket/JAAS configuration; supports mutual authentication and optional protection layer negotiation. Mapping and delegation checks remain mandatory. |
| `SCRAM-SHA-256` / `SCRAM-SHA-256-PLUS` | Challenge/response using password and salt, without sending raw password | `-PLUS` adds channel binding; still requires TLS and proper setup. Standard Java providers should not be assumed to support this mechanism out of the box. |
| `PLAIN` | `authcid` + password, optionally with `authzid` | Allow only inside a suitable protected channel; the mechanism itself does not protect the password. |
| `EXTERNAL` | Identity proven at an outer layer (e.g., TLS client certificate) | Server must trust, verify, and map the outer-layer identity; any proposed `authzid` still requires authorization checks. |

Do not include `CRAM-MD5`, `DIGEST-MD5`, or legacy algorithms in new solutions merely because a provider supports them. Mechanism names are registered by specifications, while which mechanisms exist on **the current runtime** depends on providers, versions, and configuration.

## 6. Standalone Java 17+ example: selecting a mechanism and blocking authzid spoofing

The following example has two parts: selecting a mechanism from a policy-approved set and simulating **the authorization check after `authcid` has been authenticated** via `AuthorizeCallback`. It performs no password or Kerberos handshake; never use raw `authn` strings from a real request as a substitute for actual authentication results.

Save the file `SaslIdentityDemo.java`:

```java
import java.io.IOException;
import java.util.List;
import java.util.Set;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.sasl.AuthorizeCallback;

public class SaslIdentityDemo {
    static String choose(List<String> advertised,
                         List<String> preferred,
                         Set<String> allowed) {
        for (String mech : preferred) {
            if (allowed.contains(mech) && advertised.contains(mech)) {
                return mech;
            }
        }
        throw new IllegalStateException("No allowed common SASL mechanism");
    }

    // Example rule: self-representation; svc-report is also allowed to act as reports-reader.
    static boolean mayAssume(String authn, String authz) {
        return authn.equals(authz)
                || (authn.equals("svc-report") && authz.equals("reports-reader"));
    }

    static boolean check(String authn, String authz)
            throws IOException, UnsupportedCallbackException {
        CallbackHandler handler = callbacks -> {
            for (Callback callback : callbacks) {
                if (callback instanceof AuthorizeCallback request) {
                    boolean grant = mayAssume(
                            request.getAuthenticationID(),
                            request.getAuthorizationID());
                    request.setAuthorized(grant);
                    if (grant) {
                        request.setAuthorizedID(request.getAuthorizationID());
                    }
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        AuthorizeCallback request = new AuthorizeCallback(authn, authz);
        handler.handle(new Callback[] {request});
        return request.isAuthorized();
    }

    public static void main(String[] args) throws Exception {
        List<String> advertised = List.of("PLAIN", "GSSAPI", "SCRAM-SHA-256");
        List<String> preferred = List.of("SCRAM-SHA-256", "GSSAPI", "PLAIN");
        Set<String> allowed = Set.of("SCRAM-SHA-256", "GSSAPI");

        System.out.println("mechanism=" + choose(advertised, preferred, allowed));
        System.out.println("alice -> alice: " + check("alice", "alice"));
        System.out.println("alice -> admin: " + check("alice", "admin"));
        System.out.println("svc-report -> reports-reader: "
                + check("svc-report", "reports-reader"));
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 SaslIdentityDemo.java
java SaslIdentityDemo
```

Stdout:

```text
mechanism=SCRAM-SHA-256
alice -> alice: true
alice -> admin: false
svc-report -> reports-reader: true
```

What the example demonstrates:

- The server advertising `PLAIN` does not force the client to use it: policy filters out `PLAIN`.
- An already authenticated `alice` still cannot obtain the `admin` session identity.
- Allowing proxy access must rest on a **specific rule**, here only the pair `svc-report -> reports-reader`; deny by default.
- In a real application, the principal passed into `AuthorizeCallback` must come from a mechanism that verified credentials. Simulation code does not replace authentication or a production authorization system.

## 7. Mapping to the real Java SASL API

Java SE provides the `javax.security.sasl` package and factories built on the Security Provider Framework. After the protocol/client chooses an eligible mechanism, the client creates the implementation:

```java
// Skeleton snippet: mechanism, requestedAuthzid, and clientCallbacks
// come from negotiation, policy, and the application's real credential config.
SaslClient client = Sasl.createSaslClient(
        new String[] {mechanism}, requestedAuthzid,
        "imap", "mail.example.com",
        Map.of(Sasl.QOP, "auth"),
        clientCallbacks);
if (client == null) {
    throw new SaslException("No eligible SASL client provider: " + mechanism);
}
```

The imports needed for this skeleton are `javax.security.sasl.Sasl`, `SaslClient`, `SaslException`, and `java.util.Map`. This is **not a standalone program**: it needs a transport, discovery mechanism, real credentials/JAAS, and a `CallbackHandler`. The `requestedAuthzid` argument can be `null` so the server derives the identity. Across different providers, a given mechanism name may or may not be supported.

On the server, after verifying that the client selected a mechanism enabled for this connection:

```java
// Skeleton snippet; serverCallbacks must handle the mechanism's callbacks
// and enforce AuthorizeCallback policy on a trusted identity.
SaslServer server = Sasl.createSaslServer(
        mechanism, "imap", "mail.example.com", serverProperties,
        serverCallbacks);
if (server == null) {
    throw new SaslException("No eligible SASL server provider: " + mechanism);
}

// For each response received per protocol framing:
// byte[] response = server.evaluateResponse(clientResponseBytes);
// Send next challenge if not complete; treat exceptions as failures.
if (server.isComplete()) {
    String sessionIdentity = server.getAuthorizationID();
    // Only now bind sessionIdentity to the session principal.
}
```

The server skeleton requires importing `javax.security.sasl.Sasl`, `SaslServer`, and `SaslException`. The commented `evaluateResponse(...)` call must actually be invoked for each message according to the protocol; checking `isComplete()` is meaningful only after the exchange loop. The client correspondingly uses `hasInitialResponse()`, `evaluateChallenge(...)`, and `isComplete()`. Always call `dispose()` on client/server when finished to release resources. Never invent challenges, responses, or message framing: the application protocol defines transport, while the mechanism implementation creates and processes tokens.

### Where is AuthorizeCallback used?

When a server mechanism needs to decide whether `authnId` may act as `authzid`, it may invoke `CallbackHandler.handle(...)` with an `AuthorizeCallback`:

1. `getAuthenticationID()`: the authenticated identity, supplied by the mechanism implementation.
2. `getAuthorizationID()`: the identity requested/derived according to the mechanism and protocol.
3. The server applies policy: matching identity, properly permitted delegation/tenant, or rejection.
4. `setAuthorized(true/false)` and, if accepted, `setAuthorizedID(canonicalId)` to return the permitted identity.

Real handlers may also encounter `NameCallback`, `PasswordCallback`, `RealmCallback`, or provider-specific callbacks. Never assume every mechanism uses the same set of callbacks: implement according to the provider and credentials in use. Never grant authorization inside `PasswordCallback` logic based on username; password verification and delegation policy are two separate responsibilities.

### SASL security layer and QOP

The `Sasl.QOP` property can negotiate values (if supported by the mechanism):

| QOP | Meaning | What must the application do? |
| --- | --- | --- |
| `auth` | Authentication only | Use TLS/transport protection per policy; there is no SASL integrity/confidentiality layer. |
| `auth-int` | Authentication + integrity | Use `wrap/unwrap` for data through the SASL layer if that layer was negotiated. |
| `auth-conf` | Authentication + integrity + confidentiality | Use `wrap/unwrap` with protocol framing/buffer sizes; also verify deployment requirements. |

After completion, check `getNegotiatedProperty(Sasl.QOP)` rather than trusting the preference requested when creating the client. Do not call `wrap/unwrap` when no suitable security layer exists, and do not alter the transport protocol by sending protected bytes the peer does not expect. `PLAIN` provides no SASL protection layer; `SCRAM` normally relies on TLS to protect application data.

## 8. Common GSSAPI/Kerberos scenarios

Suppose an LDAP or IMAP server authenticates Kerberos principal `svc-report@EXAMPLE.COM`. The client requests to act as `reports-reader`:

1. The client identifies the exact service name for the server, e.g., `imap/mail.example.com@EXAMPLE.COM`, and uses valid Kerberos credentials (ticket cache, JAAS, or a provider-supported mechanism).
2. SASL `GSSAPI` establishes a security context. The server validates the token, target service, and principal; conditions such as mutual authentication and QOP depend on mechanism and configuration negotiation.
3. The server maps `svc-report@EXAMPLE.COM` to an internal `authcid` per organizational rules. Do not strip realms or tenants by default.
4. The server receives the requested `authzid` `reports-reader`, consults authorization policy, and grants it only when permitted by a rule; otherwise, it fails.
5. After success, `reports-reader`'s resource access rights are still checked by the application on every operation.

Kerberos configuration requires checking DNS/hostname consistency, service principal names, keytabs or tickets, realm trust, clock skew, and credential read permissions. A successful JAAS login or a `Subject` holding a principal does not prove that the SASL server authenticated the right peer or approved a specific `authzid`.

## 9. Failure modes, symptoms, and handling

| Symptom | Common cause | Safe response |
| --- | --- | --- |
| No common mechanism | Server/client/policy/provider sets do not intersect | Report failure; never enable weak mechanisms just to "make it work." |
| Client picks `GSSAPI` but `createSaslClient` returns `null` | Provider or configuration lacks support | Inspect factories/JAAS and deployment config; never assume a mechanism exists. |
| Kerberos token failure | Expired ticket, wrong realm/SPN, hostname mismatch, clock skew | Diagnose configuration/credentials; avoid leaking tickets and secrets in logs. |
| Valid credentials but SASL fails | Requested `authzid` is not authorized | Return an authorization failure; never substitute the requested identity if not granted. |
| Login succeeds but wrong user | Raw `authzid` used or inconsistent principal mapping | Use only the effective authorization ID after server completion; verify canonical mapping. |
| `PLAIN` appears before TLS | Faulty capability advertisement or connection checks | Advertise/accept only when the channel has proper protection; refresh capabilities after TLS per protocol. |
| Confusing QOP with TLS | `auth` mistaken for encrypted data | Check both negotiated QOP and actual TLS state. |

### Implementation checklist

- Define explicitly which mechanisms **are permitted** per environment; never rely on "the first mechanism the server sends."
- Protect discovery/negotiation per protocol; defend against downgrade and authenticate the peer/channel before sending secrets.
- Separate three steps: **verify credential -> map authcid -> authorize requested authzid**. Failure at any step must fail the whole exchange.
- Normalize and map identities with realms/tenants intentionally; never grant proxy rights via arbitrary string matching.
- Trust `getAuthorizationID()` only after `SaslServer.isComplete()`; never take a requested `authzid` from the request as the session principal.
- Resource permissions must still be enforced by application authorization; audit **both `authcid` and effective `authzid`** (never log credentials, secrets, or SASL tokens).
- Test wrong password/ticket, empty `authzid`, different `authzid` with permission, different `authzid` without permission, no common mechanism, TLS/certificate errors, and a client attempting a forbidden mechanism.

## 10. Self-check questions and exercises

1. The server advertises `GSSAPI, PLAIN`, and the client only has `PLAIN`, but the connection has no TLS. What should it choose? **Nothing** if policy requires a protected channel; abort or establish TLS per the protocol first.
2. Alice proves valid credentials and sends `authzid=admin`. Can the server return SASL success and grant `alice`'s role instead? Under the logic here, **no**: an unauthorized identity request must fail the exchange; never silently alter the meaning of the requested identity.
3. Kerberos principal `alice@EXAMPLE.COM` and session identity `alice` differ as strings—does that imply proxy authorization? **Not necessarily**: that may simply be default identity mapping; follow server rules.
4. Modify the demo program to add the rule `svc-report -> audit-reader`, and verify `svc-report -> admin` remains `false`. Try removing `SCRAM-SHA-256` from the allowlist and observe which mechanism is chosen if client/server support `GSSAPI`.
5. Write a test table with (`authcid`, `requested authzid`, authorization result) for two different tenants; prove that an account in tenant A cannot act as an identically named account in tenant B.

## Reference documents

- RFC 4422 — *Simple Authentication and Security Layer (SASL)*: https://www.rfc-editor.org/rfc/rfc4422
- RFC 4616 — *The PLAIN SASL Mechanism*: https://www.rfc-editor.org/rfc/rfc4616
- RFC 5802 — *SCRAM SASL and GSS-API Mechanisms*: https://www.rfc-editor.org/rfc/rfc5802
- RFC 7677 — *SCRAM-SHA-256 and SCRAM-SHA-256-PLUS*: https://www.rfc-editor.org/rfc/rfc7677
- Java SE 17 `javax.security.sasl.Sasl`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.sasl/javax/security/sasl/Sasl.html
- Java SE 17 `javax.security.sasl.AuthorizeCallback`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.sasl/javax/security/sasl/AuthorizeCallback.html
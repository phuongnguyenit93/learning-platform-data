# 18.8. SPNEGO, Credential Delegation, and the Protection Boundaries of Each Mechanism

## Learning Objectives

After this lesson, you will be able to explain how SPNEGO selects an authentication mechanism; distinguish authentication, access authorization, and **credential delegation**; identify the real protection guarantees of Kerberos/GSS-API, SASL GSSAPI, HTTP Negotiate, and TLS; and configure a Java GSS-API flow under the principle of least privilege. The central theme is **the trust boundary of each step**, especially in multi-tier applications (frontend → backend).

> Terminology: `initiator` is the party opening the security context (typically the client), and `acceptor` is the receiving party (typically the service). A `Credential` is the ability to prove identity under a mechanism; it may be a ticket, key, or an object representing them, and is **not synonymous with a password**. `Delegation` allows a service to use delegated credentials to authenticate onward to another service under the user's identity, subject to mechanism and policy.

## 1. Placing SPNEGO at the right layer

| Component | Primary role | What it does not guarantee on its own |
| --- | --- | --- |
| **GSS-API / JGSS** (`org.ietf.jgss`) | Unified API to establish a security context, authenticate peers, and optionally protect messages via MIC/wrap | Does not transport tokens over the network; does not decide business permissions |
| **Kerberos V5 GSS mechanism** | Proves identity via tickets/session keys; can support mutual auth, integrity checks, and per-message encryption | Does not automatically encrypt all HTTP/TCP traffic; does not grant data access rights |
| **SPNEGO** | Pseudo-mechanism enabling two peers to pick a common GSS mechanism | Not an application cryptographic algorithm; does not grant permissions or delegation itself |
| **HTTP Negotiate** | Carries GSS/SPNEGO tokens in HTTP headers across a challenge/response flow | Does not protect HTTP headers/bodies; does not turn on TLS |
| **SASL GSSAPI** | SASL mechanism using Kerberos V5 GSS-API for protocols like LDAP; can negotiate `auth`/`auth-int`/`auth-conf` layers | Not SPNEGO; does not mean all data streams are automatically protected |
| **TLS** | Protects transport connections: encryption, integrity, and endpoint authentication via certificates/config | Does not inherently know the Kerberos user; does not forward user permissions across reverse proxies |
| **Application authorization** | Checks what an authenticated principal may do on which resources | Cannot be replaced by a successful SPNEGO handshake |

**Three distinct questions:** (1) "Who is connecting?" is authentication. (2) "What may they do?" is authorization. (3) "May an intermediary service represent them when connecting elsewhere?" is credential delegation. Answering "SSO succeeded" covers neither (2) nor (3).

### Common OIDs and names

- Kerberos V5 GSS mechanism: `1.2.840.113554.1.2.2`.
- SPNEGO: `1.3.6.1.5.5.2`.
- GSS host-based service name, e.g., `HTTP@api.example.com`; the Kerberos mechanism typically maps this to service principal `HTTP/api.example.com@REALM`. Service name, FQDN, realm, and keytab must match the KDC.
- The SASL name `GSSAPI` per RFC 4752 denotes **Kerberos V5** specifically, even though GSS-API in general supports multiple mechanisms. HTTP `Negotiate` is an HTTP authentication scheme name, not a principal or a cipher.

Never equate a *requested* OID with the mechanism ultimately *established*. When choosing SPNEGO, authentication must run until the context completes; only then inspect the actual mechanism, peer name, and protection flags provided by the implementation.

## 2. How does SPNEGO negotiate a mechanism?

RFC 4178 describes SPNEGO as a protected negotiation layer atop GSS-API:

1. The initiator creates `NegTokenInit` containing its supported mechanisms in preference order; it may attach an **optimistic token** for the preferred mechanism to save round-trips.
2. The acceptor picks a supported mechanism from the list or rejects. Its `NegTokenResp` carries a state such as `accept-incomplete`, `accept-completed`, `reject`, or `request-mic`, along with a token from the selected mechanism if needed.
3. Both peers exchange further tokens for the underlying mechanism (e.g., Kerberos AP-REQ/AP-REP) until the context completes. Never treat an initial token or a single HTTP 401 as proof that authentication is finished.
4. When the chosen mechanism provides integrity, SPNEGO uses `mechListMIC` in cases required by the RFC to protect the mechanism list against tampering/downgrade. The MIC may be optional when the chosen mechanism was already both sides' top preference; if the mechanism lacks integrity, this MIC layer is unavailable.

`mechListMIC` protects **mechanism selection**, not application payloads. If policy mandates Kerberos, reject all other outcomes even if SPNEGO negotiation "succeeded." Never enable silent fallback to weaker mechanisms when Kerberos fails.

### Example HTTP Negotiate flow

```text
Browser/Java client                 HTTP server (acceptor)        KDC
        | GET /private                     |                       |
        |--------------------------------->|                       |
        | 401 WWW-Authenticate: Negotiate  |                       |
        |<---------------------------------|                       |
        | fetch ticket for HTTP/server     |                       |
        |<------------------------------------------------------->|
        | Authorization: Negotiate <base64 GSS token>              |
        |--------------------------------->|                       |
        |<---- 401/200 + WWW-Authenticate: Negotiate <token>? ----|
        | continue initSecContext() until established              |
        |<================================>|                       |
        |     application authorization after authentication       |
```

This is a generalized flow: additional round-trips may occur; the final server token sometimes accompanies a 200 response, and **the client must still process it**. `Authorization: Negotiate` carries a Base64-encoded binary token, **not** an arbitrarily reusable "Bearer token." The server must validate the context, principal, target service, and access policies before returning private data.

Per RFC 4559, HTTP Negotiate handles authentication only; it does not protect HTTP headers or bodies. Production HTTP deployments therefore need **HTTPS/TLS** (and TLS across every sensitive hop), strict scoping of where tokens are sent, no token logging, and policy-driven HTTP response protection.

### Is SPNEGO the same as Kerberos?

No. SPNEGO is a selector; Kerberos may be the selected mechanism. Some SPNEGO/HTTP Negotiate ecosystems can interoperate with NTLM, though the actual mechanism set depends on provider and platform. The JDK's SunJGSS provider primarily implements Kerberos and SPNEGO over Kerberos; **do not assume** Java supports NTLM via JGSS by default. When an application requires Kerberos, configure an allowlist and verify the established mechanism; never treat the string "Negotiate" in a header as proof of the chosen mechanism.

## 3. Credential delegation: what does it allow and forbid?

Consider a three-tier flow:

```text
Alice (initiator)  -- GSS context A -->  Frontend (acceptor)
                                           |
                                           | GSS context B to backend
                                           | using Alice's delegated credential
                                           v
                                        Backend
```

In context A, Alice authenticates to the Frontend. If Alice **explicitly requests it**, the mechanism **supports it**, her credentials are **delegatable**, and policy **permits it**, the frontend can receive a delegated `GSSCredential`. The frontend then establishes context B to the Backend under Alice's identity. The Backend must still authenticate the frontend/delegation and **independently evaluate what Alice is permitted to do**. A frontend holding delegated credentials becomes a high-value target: if compromised, an attacker can abuse user impersonation within the granted lifetime and scope.

Practical prerequisites depend on Kerberos and the environment: `forwardable` tickets, client/KDC/service policies, service delegation attributes, cross-realm trusts, credential caches, and providers. Requesting delegation in the API **does not guarantee** it was granted. Receiving no delegation is a normal outcome and must never be "fixed" by falling back to a superuser service account.

### Distinguishing types of authority

| Concept | Example | Key point to remember |
| --- | --- | --- |
| Authentication | Alice logs into Frontend via Kerberos | Proves identity within context A |
| Authorization | Frontend lets Alice read report #42 | Application rules; Kerberos makes no business decisions |
| SASL authorization identity (`authzid`) | Client asks to act under a specific authorization name | Server must check delegation rules; not GSS credential delegation |
| GSS credential delegation | Frontend uses `getDelegCred()` to call Backend with forwarded credentials | Enables downstream authentication; must constrain lifetime, target, and rights |
| Proxy identity/headers | Gateway sends `X-User` to microservice | Trustworthy only with an explicit trust relationship, auth, and protected gateway → service hop |
| Kerberos constrained delegation | Mechanism such as S4U2proxy restricted to specific target services | Separate configuration/protocol model; not identical to `requestCredDeleg(true)` in JGSS |

Do not confuse delegation with "forwarding the `Authorization: Negotiate` header." A Kerberos token is minted for a specific target/context; forwarding that raw token to a second service does not turn it into a valid credential for that second service. Likewise, SASL `authzid` does not allow a client to seize another user's rights when the server enforces policy properly.

### Rules for safe delegation design

1. By default, **do not request** delegation. Enable it only for business flows with a clear need and user/administrator consent.
2. Restrict target services (SPN/FQDN), accepted principals, permitted actions, and backend permissions. Prefer constrained delegation or narrowly scoped authorization models where supported by the platform.
3. After context A completes, inspect `getCredDelegState()`; the acceptor calls `getDelegCred()` only after establishment. `null` means no credential was delegated.
4. Never log, serialize to JSON, store in a database, or push credentials/tickets onto a message queue. Never pool credentials from multiple users globally. Close contexts and `dispose()` credentials when done.
5. Backend authorization must use the identity authenticated at the Backend, never an unverified username string asserted by the Frontend. Audit by principal, target service, and action without logging tokens or secrets.
6. Plan for when delegation is denied: return a clear business error or use an explicitly designed authorization flow. Never silently "fall back" to elevated privileges.

## 4. Java 17+: setting up an SPNEGO context and verifying conditions

Standard API: module `java.security.jgss`, package `org.ietf.jgss`. `GSSManager` creates `GSSName`, `GSSCredential`, and `GSSContext`. JGSS **does not transmit tokens over the network**; the application or HTTP/SASL library must frame, send, and receive them per protocol.

The example below is a **standalone, compilable/runnable Java 17 program** that verifies the OIDs and provides a client-side context factory. The factory method does not run a handshake; real Kerberos connections require a KDC, principals, credentials, and a token-exchange channel.

```java
// SpnegoContextSetup.java
import org.ietf.jgss.GSSContext;
import org.ietf.jgss.GSSException;
import org.ietf.jgss.GSSManager;
import org.ietf.jgss.GSSName;
import org.ietf.jgss.Oid;

public final class SpnegoContextSetup {
    private static final Oid SPNEGO = oid("1.3.6.1.5.5.2");
    private static final Oid KERBEROS = oid("1.2.840.113554.1.2.2");

    private SpnegoContextSetup() {}

    private static Oid oid(String value) {
        try {
            return new Oid(value);
        } catch (GSSException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    // Call in an environment with appropriate Kerberos credentials available.
    public static GSSContext createClient(String host, boolean allowDelegation)
            throws GSSException {
        GSSManager manager = GSSManager.getInstance();
        GSSName target = manager.createName(
                "HTTP@" + host, GSSName.NT_HOSTBASED_SERVICE);
        GSSContext context = manager.createContext(
                target, SPNEGO, null, GSSContext.DEFAULT_LIFETIME);

        // Effective only when called before the first initSecContext().
        context.requestMutualAuth(true);
        context.requestInteg(true);
        context.requestConf(true);
        context.requestReplayDet(true);
        context.requestSequenceDet(true);
        context.requestCredDeleg(allowDelegation);
        return context;
    }

    // Call only after the token exchange has completed.
    public static void requireClientPolicy(GSSContext context)
            throws GSSException {
        if (!context.isEstablished()) {
            throw new SecurityException("GSS context not established");
        }
        if (!context.getMutualAuthState()) {
            throw new SecurityException("Mutual authentication unavailable");
        }
        // Provider must report Kerberos as the final mechanism; otherwise reject.
        if (!KERBEROS.equals(context.getMech())) {
            throw new SecurityException("Selected GSS mechanism is not Kerberos");
        }
    }

    public static void main(String[] args) {
        System.out.println("SPNEGO: " + SPNEGO);
        System.out.println("Kerberos: " + KERBEROS);
    }
}
```

Compile and run (JDK 17+, no KDC required because `main` only prints OIDs):

```bash
javac SpnegoContextSetup.java
java SpnegoContextSetup
```

Exact stdout:

```text
SPNEGO: 1.3.6.1.5.5.2
Kerberos: 1.2.840.113554.1.2.2
```

In a live Kerberos system, `createClient` runs under an identity/`Subject` holding valid credentials or using a configured provider credential mechanism. Passing `null` for the credential parameter tells the provider to use the appropriate default credential; it does **not** synthesize a new identity. The `HTTP@host` name must point to the server's real SPN, never derived from untrusted input. Keep `requestCredDeleg(false)` unless delegation is specifically required.

### Token exchange: getting the state machine right

**The snippet below is illustrative code inside an I/O handler method you implement yourself**, not a standalone program; `sendToken` and `receiveToken` represent your transport protocol methods.

```java
// Initiator (method body; context has already been created):
byte[] incoming = new byte[0];
while (!context.isEstablished()) {
    byte[] outgoing = context.initSecContext(
            incoming, 0, incoming.length);
    if (outgoing != null) {
        sendToken(outgoing);             // May still need to send the final token.
    }
    if (!context.isEstablished()) {
        incoming = receiveToken();       // Token returned from the real acceptor.
    }
}
requireClientPolicy(context);
// End of session: context.dispose() in finally.
```

On the acceptor, create an `ACCEPT_ONLY` credential matching the principal/keytab (or the provider's default credential), call `manager.createContext(acceptorCredential)`, loop calling `acceptSecContext(incoming, 0, incoming.length)` and returning any output token until `isEstablished()`. Then verify `getSrcName()`, `getMech()`, and application policy. Never mix tokens across requests, connections, users, or contexts.

Note: GSS tokens are **opaque**; never parse ASN.1 or Base64 yourself to infer authentication success or principals. Token transport details (framing, ordering, timeouts, max sizes) are the outer protocol's job. In HTTP Negotiate, the HTTP library usually handles the 401/200 cycle and Base64; over raw sockets, the developer must design safe framing.

### Acceptor reading delegated credentials

**The illustrative fragment below may be called only after `acceptSecContext` finishes successfully**, on the acceptor's context, and after the server verifies this request is permitted to use delegation:

```java
if (!acceptorContext.isEstablished()) {
    throw new SecurityException("Incomplete client authentication");
}
GSSName authenticatedUser = acceptorContext.getSrcName();
if (!isAuthorized(authenticatedUser)) { // Application policy function.
    throw new SecurityException("User is not authorized");
}

if (acceptorContext.getCredDelegState()) {
    GSSCredential delegated = acceptorContext.getDelegCred();
    if (delegated != null) {
        try {
            GSSManager manager = GSSManager.getInstance();
            GSSName backend = manager.createName(
                    "ldap@directory.internal.example",
                    GSSName.NT_HOSTBASED_SERVICE);
            GSSContext downstream = manager.createContext(
                    backend, new Oid("1.2.840.113554.1.2.2"),
                    delegated, GSSContext.DEFAULT_LIFETIME);
            try {
                downstream.requestMutualAuth(true);
                downstream.requestCredDeleg(false); // Do not forward further automatically.
                // Perform token exchange with backend per real protocol.
                // Access backend only after downstream.isEstablished().
            } finally {
                downstream.dispose();
            }
        } finally {
            delegated.dispose();
        }
    }
}
```

`isAuthorized` and the backend token exchange **must be implemented by the application**; they are not in the JDK. `delegated.dispose()` should be called only when the application owns the credential lifecycle and no context still needs it. In production systems, add target-principal verification, delegation policy checks, account mapping, timeouts, and exception handling. Never treat `getCredDelegState()==true` as business authorization.

### Requested flags differ from negotiated flags

| Initiator call, **before** `initSecContext` | Read outcome **after** `isEstablished` |
| --- | --- |
| `requestMutualAuth(true)` | `getMutualAuthState()` |
| `requestCredDeleg(true/false)` | `getCredDelegState()` |
| `requestInteg(true)` | `getIntegState()` |
| `requestConf(true)` | `getConfState()` |
| `requestReplayDet(true)` | `getReplayDetState()` |
| `requestSequenceDet(true)` | `getSequenceDetState()` |

A **requested** flag does not prove the mechanism granted it. If policy requires a property, check the negotiated state and fail closed when missing. `getMech()` can change during negotiation; inspect it after context completion and confirm provider behavior. `getCredDelegState()` is definitive only after establishment; `getDelegCred()` is called on the acceptor and can return `null`.

`requestConf(true)` only requests confidentiality capability for **GSS `wrap()`**; calling that flag **does not encrypt the HTTP body**. If an application uses `wrap(..., new MessageProp(0, true))` to protect custom messages, it must verify the context supports confidentiality, ensure the receiver calls `unwrap()`, and transmit tokens cleanly. `getMIC()/verifyMIC()` provides integrity, not secrecy. Over HTTP, HTTPS/TLS must still be configured properly.

## 5. SASL GSSAPI and SPNEGO: do not conflate them

An application may encounter both APIs:

- **Direct JGSS or HTTP Negotiate:** chooses the SPNEGO OID and exchanges tokens with the peer to establish a `GSSContext`; the actual mechanism can be Kerberos depending on provider/policy.
- **SASL `GSSAPI` (RFC 4752):** a SASL mechanism **fixed to Kerberos V5 GSS-API** that optionally negotiates a post-authentication data protection layer. Protocols like LDAP define challenge/response framing; `SaslClient`/`SaslServer` handle only SASL logic.
- **GS2 family (RFC 5801):** bridges GSS-API to SASL differently from RFC 4752's `GSSAPI`, e.g., `GS2-KRB5` and `GS2-KRB5-PLUS`, where PLUS uses channel binding. Never assume every SASL provider or protocol supports GS2.

In Java (`javax.security.sasl`), `Sasl.QOP` accepts these values:

| QOP | Protection provided by SASL security layer |
| --- | --- |
| `auth` | Authentication; **adds no** SASL data protection layer |
| `auth-int` | Authentication + integrity for messages passed through `wrap()/unwrap()` |
| `auth-conf` | Authentication + integrity + confidentiality for messages passed through `wrap()/unwrap()` |

If `Sasl.QOP` is omitted, the default per Java Javadoc is `auth`. Supplying a preference list does not force the server to pick the strongest value; you must read **`getNegotiatedProperty(Sasl.QOP)` after `isComplete()`** and reject if it falls short of policy. With `auth-int`/`auth-conf`, the application/protocol must pass subsequent data through `SaslClient.wrap()/unwrap()` or `SaslServer.wrap()/unwrap()`; negotiating QOP and then sending plaintext violates the protection boundary.

Illustrative fragment (placed inside a method handling `SaslException` and the protocol's challenge/response loop):

```java
Map<String, String> properties = Map.of(
        Sasl.QOP, "auth-conf,auth-int,auth");

SaslClient client = Sasl.createSaslClient(
        new String[] { "GSSAPI" },
        null,             // authorizationId: do not request impersonating another identity.
        "ldap",           // protocol per SASL profile.
        "directory.example.com",
        properties,
        null);            // CallbackHandler depending on provider configuration.

if (client == null) {
    throw new SaslException("No GSSAPI SASL provider");
}

// Exchange challenge/response until client.isComplete() per the LDAP protocol.
if (!client.isComplete()) {
    throw new SaslException("SASL exchange incomplete");
}
String negotiatedQop = (String) client.getNegotiatedProperty(Sasl.QOP);
if (!"auth-conf".equals(negotiatedQop)) {
    throw new SaslException("Required SASL confidentiality unavailable");
}
// Next: transmit data through client.wrap()/unwrap() per protocol.
// End of session: client.dispose().
```

This fragment requires importing `java.util.Map`, `javax.security.sasl.Sasl`, `SaslClient`, and `SaslException`. In a real flow, you must **execute** the exchange over LDAP or the target protocol before checking `isComplete()`; the snippet does not run authentication by itself.

SASL authorization identity differs from credential delegation: the SASL server itself decides whether the authenticated client may act under the requested `authzid`. Using `Sasl.createSaslClient("GSSAPI")` alone does not automatically create a forwardable `GSSCredential`.

## 6. Protection boundaries that are easy to misunderstand

### 6.1. Peer authentication does not equal full connection encryption

Kerberos GSS authenticates and derives context keys; `wrap`/`getMIC` protect **only messages the application explicitly passes through those APIs**. An HTTP request carrying an SPNEGO token whose body is not passed through `wrap` still requires TLS. TLS protects traffic between **two TLS endpoints**, and does not automatically protect data after proxy decryption or once written to logs/databases.

### 6.2. SPNEGO negotiation protection is not system-wide anti-downgrade

RFC 4178's `mechListMIC` depends on the underlying mechanism having integrity and on the negotiation case. It does not replace a "Kerberos-only" policy, does not protect HTTP schemes advertised elsewhere by the application server, and does not automatically protect HTTP redirects or DNS. When Kerberos is mandatory: accept only the matching real mechanism, never silently retry with NTLM/Basic, and verify the target service principal.

### 6.3. Mutual authentication is not the same as "having TLS"

Kerberos mutual auth (when negotiated) proves the acceptor possesses the credentials needed to complete the Kerberos exchange. TLS server authentication verifies the TLS endpoint's certificate. These two properties apply to **different layers and principals**, which can refer to two distinct entities when a reverse proxy sits in front. To bind application authentication to the TLS channel itself, use channel binding supported and identically configured on both ends; never assume JGSS or an HTTP client handles that automatically.

Java GSS offers `GSSContext.setChannelBinding(ChannelBinding)` before the handshake; binding data must come from the verified channel and match on both sides. For modern SASL standards, RFC 9266 defines `tls-exporter` for TLS 1.3, while RFC 5929 describes earlier binding types. Choose the exact binding type and data per **real protocol and provider**, and never invent certificate strings or mark a session "channel bound" without peer verification.

### 6.4. Endpoint and identity scope

Tickets and service names must match the target service. A user credential for `HTTP/front.example.com` does not mean backend `ldap/directory.example.com` has authenticated the user. When a proxy accepts Negotiate, the backend sees only the hop opened by the proxy; if the backend needs the user's identity, it requires policy-permitted delegation or a separately authenticated and verified identity-propagation protocol. An externally supplied `X-User` header is untrustworthy.

### 6.5. Replay, lifetime, and token handling

Kerberos and GSS contexts offer configurable replay/sequence detection, which does not replace business-level replay protection (such as preventing duplicate money transfers), idempotency keys, per-request authorization, or session lifetimes. Tokens can reveal structure/metadata and must be treated as sensitive data; never log `Authorization: Negotiate`, Kerberos tickets, keytabs, credential dumps, or SASL challenges. Cap token sizes, handshake rounds, timeouts, and concurrent contexts to mitigate DoS.

## 7. Decision matrix by requirement

| Requirement | Required mechanism / setup | Mandatory verification |
| --- | --- | --- |
| User SSO login to internal web app | HTTPS + HTTP Negotiate/SPNEGO allowing Kerberos | Context established, principal, SPN, and authorization |
| Keep HTTP headers/body confidential | TLS across every sensitive endpoint/hop | Certificate, hostname, TLS policy, TLS termination point |
| Protect custom GSS socket messages | `GSSContext.wrap/unwrap` or appropriate MIC | `getIntegState/getConfState`, accurate framing and token checks |
| LDAP using SASL GSSAPI | SASL challenge/response with Kerberos | `isComplete`, `authzid`, negotiated QOP; TLS if needed |
| Backend acting on behalf of user | Credential delegation or controlled delegation solution | Consent/policy, `getCredDelegState`, identity, scope, and audit |
| Mitigate MITM between GSS/SASL and TLS | Channel binding supported by protocol/provider | Both peers bind to the same TLS channel; fail on mismatch |
| Allow Kerberos only, prevent fallback | GSS mechanism allowlist and HTTP auth policy | Final mechanism check; no downgrade to NTLM/Basic |

**Choice example:** A company has a web portal using Negotiate. User Alice views her own data from a database. If the portal reads data using a service account while enforcing **portal-side authorization for Alice**, Kerberos delegation is not strictly necessary. Only if the database mandates per-user Kerberos authentication should target-scoped credential delegation be considered. Both models require authorization policies at the database or portal; delegation widens blast radius if misconfigured.

## 8. Implementation, error handling, and testing

### Java + Kerberos/SPNEGO implementation checklist

1. **Identities:** identify user principals, FQDNs, exact service principals (`HTTP/...`, `ldap/...`), realms, and trust paths. Ensure DNS/canonicalization does not cause clients to request tickets for an unintended host.
2. **Credential store:** set up JAAS/Kerberos logins, ticket caches, keytabs, and OS file permissions for the exact service process. Enable debug only during investigation and scrub logs before sharing.
3. **Negotiate:** define permitted mechanisms. Create contexts with the right OID, setting mutual auth, integrity, and delegation flags before the first `initSecContext`. Never treat a single HTTP 401 as terminal; process every response token.
4. **Post-handshake policy:** verify context establishment, negotiated mechanism, expected acceptor/service, and authenticated user; run independent resource authorization checks.
5. **Data protection:** trace exact TLS hops, GSS/SASL `wrap` usage, channel binding, proxies, and logging. For sensitive data, verify confidentiality at **the layer actually moving the data**.
6. **Delegation:** declare which flows need it, who is eligible, which target services may receive it, and what lifetime applies; test "delegation denied." Never silently retry or escalate privileges when `getDelegCred()` is `null`.
7. **Lifecycle:** tie every context to one session/identity; guard against concurrency/races, enforce timeouts and token caps, and dispose contexts/credentials when finished. Never share a mutable `GSSContext` across independent requests.

### Failure modes and diagnostic guide

| Symptom | Causes to inspect | How to resolve |
| --- | --- | --- |
| `GSSException: No valid credentials` | Not logged into Kerberos, wrong process/`Subject` credential cache, expired ticket | Inspect credential source and principal; never hardcode passwords |
| `KRB_AP_ERR_MODIFIED` / service ticket rejected | SPN targets wrong service, keytab/kvno/key mismatch, duplicate SPN | Reconcile target FQDN, SPN, keytab, and KDC |
| `Clock skew too great` | Clock drift among client/server/KDC | Synchronize clocks per system policy |
| Repeated HTTP 401 Negotiate | Incomplete token exchange, server missing acceptor cred, proxy stripping header, wrong SPN | Trace hops/states safely; never log raw tokens |
| Auth succeeds but backend denies | Delegation absent, backend enforces separate roles, wrong target principal | Check `getCredDelegState`, backend identity/authorization |
| Got `auth` when confidentiality was needed | Negotiated SASL QOP is weaker than required | Fail closed or require an approved TLS channel per policy |
| Channel binding mismatch | Peers bound to different TLS connections, or incompatible binding type | Inspect TLS termination and provider/protocol support |

Operational commands such as `klist`, `kinit`, or `setspn` (depending on OS and environment) help inspect tickets/SPNs; treat their output as security-sensitive data. Never conclude a mechanism, permission, or security guarantee holds merely because a command exited 0.

### Minimum QA test suite

- **Happy path:** Kerberos client/server with valid SPN; context completes; user authorized for the right resource.
- **No common mechanism:** rejected; no fallback to forbidden mechanisms.
- **Wrong SPN/keytab/realm or tampered token:** no access granted; no application session created.
- **Delegation disabled:** acceptor receives no delegated credential; backend follows the non-delegation path.
- **Delegation requested but disallowed by policy/ticket:** no silent privilege escalation or shared superuser service account.
- **Delegation permitted:** only authorized backends called; principal and audit match; credential unusable after session ends.
- **Weak SASL QOP:** an app requiring `auth-conf` must reject `auth`/`auth-int`; verify post-auth data actually traverses the chosen protection.
- **Proxy/TLS:** test TLS termination at gateway, altered channel binding, header stripping at downstream hops, and non-TLS HTTP; confirm policy catches violations and protects the intended scope.
- **Replay/concurrency:** replay business requests and invalid tokens, exceed round/token-size caps; confirm no credential leakage and no cross-session identity mix-up.

## 9. Key takeaways to remember

1. **SPNEGO selects a GSS mechanism**; authentication quality, integrity, confidentiality, and delegation depend on the selected mechanism and enforced policy.
2. **Delegation is not authorization**: a delegated `GSSCredential` lets hop B authenticate to hop C as the user, yet both B and C must still restrict permissions. `requestCredDeleg(true)` is a request, not a grant guarantee.
3. **Each layer protects a distinct scope:** HTTP Negotiate transports tokens; Kerberos authenticates and can protect GSS messages; SASL GSSAPI applies QOP to data passing through its security layer; TLS protects TLS hops; the application decides access rights.
4. **Verify after negotiation and fail closed:** check `isEstablished()`/`isComplete()`, actual mechanism/QOP/flags, principal, TLS/channel binding, and application authorization. Never replace these checks with the assumption "SSO succeeded so it must be safe."

## Standard references for deeper reading

- [RFC 4178 — SPNEGO](https://www.rfc-editor.org/rfc/rfc4178): mechanism lists, tokens, and `mechListMIC`.
- [RFC 4559 — HTTP Negotiate](https://www.rfc-editor.org/rfc/rfc4559): 401/Authorization flow and HTTP protection boundaries.
- [RFC 4121 — Kerberos V5 GSS mechanism](https://www.rfc-editor.org/rfc/rfc4121): MIC, Wrap, and per-message protection.
- [RFC 4752 — SASL GSSAPI (Kerberos V5)](https://www.rfc-editor.org/rfc/rfc4752): SASL GSSAPI and security layers.
- [RFC 5801 — SASL GS2 family](https://www.rfc-editor.org/rfc/rfc5801) and [RFC 9266 — TLS 1.3 channel binding](https://www.rfc-editor.org/rfc/rfc9266): channel binding variants.
- [Java 17 `GSSContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSContext.html), [`GSSManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSManager.html), [`Sasl`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.sasl/javax/security/sasl/Sasl.html): APIs and negotiated states.
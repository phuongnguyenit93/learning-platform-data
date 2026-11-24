# 18.5. GSSManager, GSSName, GSSCredential, and GSSContext

## Objectives and Context

After this lesson, you will be able to explain the roles of the four core objects in Java GSS-API, construct names and security contexts properly on client and server sides, understand the token exchange loop, verify security properties after the handshake, and recognize common Kerberos errors.

**GSS-API (Generic Security Services API)** provides a uniform interface for authentication and message-protection mechanisms, most commonly Kerberos V5. In Java 17+, the standard API lives in package `org.ietf.jgss` within module `java.security.jgss`. Applications can use GSS-API for mutual authentication, integrity verification, and (when supported by the mechanism and context) message confidentiality.

GSS-API **does not open connections or transmit tokens itself**: the program or a protocol such as HTTP or SASL must shuttle tokens between both endpoints. Nor does GSS-API replace business-level authorization once the user's identity is known.

## 1. Map of the four objects

| Component | Primary responsibility | What do you usually do with it? |
| --- | --- | --- |
| `GSSManager` | Factory that knows available GSS mechanisms | `getInstance()`, `getMechs()`, `createName(...)`, `createCredential(...)`, `createContext(...)` |
| `GSSName` | Represents a principal identity under a name type, convertible to a mechanism-specific name | Identify target service `HTTP@api.example.com`; canonicalize with `canonicalize(...)` when needed |
| `GSSCredential` | Handle to existing credentials of a principal for initiating or accepting contexts | Acquire client or service credentials; inspect lifetime, mechanisms, and usage role |
| `GSSContext` | Security session between two peers, initially unestablished | Exchange `initSecContext`/`acceptSecContext`; then verify identities, `wrap`/`unwrap`, `getMIC`/`verifyMIC` |

Typical dependency flow:

```text
             GSSManager
             ├── creates GSSName: peer/service name
             ├── acquires GSSCredential: privileges of the process itself
             └── creates GSSContext (one per connection/authentication session)
                         │
       initiator.initSecContext(...) ↔ acceptor.acceptSecContext(...)
                         │
                 isEstablished() == true
                         │
           getSrcName/getTargName, wrap/unwrap, MIC
```

Keep three questions separate: **who am I** (credential), **who am I talking to** (peer name), and **what protections have the two sides authenticated and agreed upon** (context). `GSSManager` ties them together.

## 2. GSSManager: entry point and mechanism selection

Obtain the default factory via `GSSManager.getInstance()`. The factory can list available mechanisms via `getMechs()`, name types via `getNamesForMech(Oid)`, and mechanisms compatible with a name type via `getMechsForName(Oid)`.

**OID (Object Identifier)** identifies a mechanism numerically rather than by Java class name:

- Kerberos V5 GSS-API: `1.2.840.113554.1.2.2`.
- SPNEGO (GSS negotiation mechanism, if supported by provider): `1.3.6.1.5.5.2`. SPNEGO is not synonymous with pure Kerberos; it can negotiate an underlying mechanism.
- Passing `mech = null` to `createContext` requests the default mechanism; it does **not** mean SPNEGO negotiation is always chosen automatically.

Standalone Java example requiring no KDC, keytab, or ticket because it only inspects mechanism support:

**File `GssCapabilities.java`**

```java
import java.util.Arrays;
import org.ietf.jgss.GSSManager;
import org.ietf.jgss.Oid;

public class GssCapabilities {
    public static void main(String[] args) throws Exception {
        GSSManager manager = GSSManager.getInstance();
        Oid kerberos = new Oid("1.2.840.113554.1.2.2");

        System.out.println("Kerberos OID: " + kerberos);
        System.out.println("Kerberos supported: "
                + Arrays.asList(manager.getMechs()).contains(kerberos));
    }
}
```

Run on Java SE 17+ with a standard GSS-API implementation:

```bash
javac GssCapabilities.java
java GssCapabilities
```

Expected stdout:

```text
Kerberos OID: 1.2.840.113554.1.2.2
Kerberos supported: true
```

Seeing the Kerberos OID in the list does **not** prove the machine has a configured realm, Kerberos tickets, or login accounts. It only confirms that the mechanism is available in the JDK implementation.

## 3. GSSName: logical names, name types, and mechanism names

`GSSName` is not an arbitrary string. When calling `manager.createName(value, nameType)`, the `nameType` parameter specifies how to interpret `value`:

| Name type | Case | Points to remember |
| --- | --- | --- |
| `GSSName.NT_HOSTBASED_SERVICE` | `"HTTP@api.example.com"` | Host-based GSS form is `service@host`, **different** from Kerberos principal notation `HTTP/api.example.com@EXAMPLE.COM` |
| `GSSName.NT_USER_NAME` | Username in a form accepted by the provider | Do not infer realm or permissions from a display string |
| `GSSName.NT_EXPORT_NAME` | Importing a name in binary exported format | Use with the standard export format; never treat bytes as arbitrary UTF-8 |

```java
GSSManager manager = GSSManager.getInstance();
Oid kerberos = new Oid("1.2.840.113554.1.2.2");

// Requires proper Kerberos/realm configuration even when creating a name
// on some JDK providers:
GSSName service = manager.createName(
        "HTTP@api.example.com",
        GSSName.NT_HOSTBASED_SERVICE);

// Convert to a mechanism name (MN) for Kerberos when needed:
GSSName kerberosService = service.canonicalize(kerberos);
```

The snippet above **is an integration illustration**, not a standalone program: some implementations attempt realm resolution during `createName` and throw `GSSException` if Kerberos is unconfigured, even before any token is sent. Never assume name creation always succeeds on an unconfigured host.

`canonicalize(mechOid)` produces a mechanism-specific representation; `isMN()` indicates whether the object is a mechanism name. `GSSName.export()` can export an MN into bytes to be re-imported with `NT_EXPORT_NAME`; never use `getBytes()` on `toString()` as a substitute. When matching security identities, use mechanism-level name comparison rules and explicit authorization policies rather than simply splitting strings around `@`.

**Watch out for service principals:** the client may create host-based name `HTTP@api.example.com`, whereas Kerberos may actually require service principal `HTTP/api.example.com@EXAMPLE.COM` and the matching keytab. Mapping depends on realm, DNS, and provider settings; the wrong name causes authentication to fail even when the client has a ticket.

## 4. GSSCredential: identity and usage rights

`GSSCredential` holds a handle to credentials for a principal already supplied by the environment. `GSSManager.createCredential(...)` is **not a password login operation**: Kerberos tickets or acceptor keys (such as a keytab or a `Subject` containing a `KerberosKey`) must be provided via JAAS or default mechanisms before or during credential acquisition by the provider.

Three usage flags:

- `GSSCredential.INITIATE_ONLY`: used to open contexts with a peer (typically client).
- `GSSCredential.ACCEPT_ONLY`: used to accept contexts from clients (typically service).
- `GSSCredential.INITIATE_AND_ACCEPT`: used for both if supported by the mechanism and actual credentials.

Illustrative example acquiring server-side acceptor credentials once Kerberos and JAAS are prepared:

```java
GSSManager manager = GSSManager.getInstance();
Oid kerberos = new Oid("1.2.840.113554.1.2.2");
GSSName service = manager.createName(
        "HTTP@api.example.com",
        GSSName.NT_HOSTBASED_SERVICE);

GSSCredential acceptorCred = manager.createCredential(
        service,
        GSSCredential.DEFAULT_LIFETIME,
        kerberos,
        GSSCredential.ACCEPT_ONLY);
try {
    // Create context and receive tokens in an authentication session...
    System.out.println(acceptorCred.getRemainingLifetime());
} finally {
    acceptorCred.dispose();
}
```

This is a Java fragment with no `main` method and **cannot run successfully without matching service credentials**. On the client, you may pass credentials acquired with `INITIATE_ONLY` or pass `null` to `GSSManager.createContext(peer, mech, null, lifetime)` so the provider uses the default initiator identity in the current context.

You can inspect `getName()`, `getMechs()`, `getUsage(...)`, and `getRemainingLifetime()`. The requested lifetime is a **request**, not a guarantee; check the actual value. Call `dispose()` when credentials are no longer needed to avoid retaining handles or sensitive material longer than necessary. Never log credentials, keytabs, tickets, or tokens.

## 5. GSSContext: session state and the two sides

`GSSContext` represents a security session with a peer and is **not yet authenticated when constructed**. Distinguish the two creation forms:

- **Initiator/client:** `createContext(GSSName peer, Oid mech, GSSCredential myCred, int lifetime)`. Supply the target peer name and mechanism; `null` for credential means using the client's default identity if available.
- **Acceptor/server:** `createContext(GSSCredential myCred)`. Supply the server's acceptor credential; the context will process tokens sent by the initiator.

Before the first `initSecContext`, the initiator can request:

| Call | Meaning | What to verify after establishment |
| --- | --- | --- |
| `requestMutualAuth(true)` | Client wants server authentication too | `getMutualAuthState()` |
| `requestInteg(true)` | Wants integrity protection | `getIntegState()` |
| `requestConf(true)` | Wants to allow content confidentiality | `getConfState()` |
| `requestReplayDet(true)` | Wants message replay detection | `getReplayDetState()` |
| `requestSequenceDet(true)` | Wants message sequence checking | `getSequenceDetState()` |
| `requestCredDeleg(true)` | Wants to delegate credentials to server | `getCredDelegState()`; enable only when genuinely needed |

`request...` calls are requests, not proof that the feature was enabled. The provider and peer determine final negotiated properties. If the application requires mutual authentication, integrity, or confidentiality, **reject the session** when actual post-establishment properties fail policy. Never request credential delegation by default, as it expands the recipient's privileges.

`setChannelBinding(ChannelBinding)` (when supported by the protocol) is called **before the handshake on both sides** to bind authentication to underlying channel information and reduce cross-channel token relay risks. Both sides must supply compatible binding data; mismatched configuration can break authentication.

Once `isEstablished() == true`, the context exposes `getSrcName()` (initiator), `getTargName()` (acceptor), `getMech()`, and security service states. **Identity authentication does not automatically grant access:** the server must still check the authenticated principal against the appropriate ACL/role/tenant/endpoint rules.

## 6. Illustrating client and server context creation in Java 17+

The file below **compiles cleanly** and demonstrates the four objects. Its methods should be called only in an application with Kerberos configured and a token transport mechanism; it contains no `main` method and does not pretend to succeed without a KDC, ticket, or keytab.

**File `GssSetup.java`**

```java
import org.ietf.jgss.GSSContext;
import org.ietf.jgss.GSSCredential;
import org.ietf.jgss.GSSException;
import org.ietf.jgss.GSSManager;
import org.ietf.jgss.GSSName;
import org.ietf.jgss.Oid;

public final class GssSetup {
    private GssSetup() {}

    private static Oid kerberos() throws GSSException {
        return new Oid("1.2.840.113554.1.2.2");
    }

    public static GSSContext newClientContext(String serviceHost)
            throws GSSException {
        GSSManager manager = GSSManager.getInstance();
        GSSName server = manager.createName(
                "HTTP@" + serviceHost, GSSName.NT_HOSTBASED_SERVICE);

        // null: use the default initiator credential in the current environment.
        GSSContext context = manager.createContext(
                server, kerberos(), null, GSSContext.DEFAULT_LIFETIME);

        context.requestMutualAuth(true);
        context.requestInteg(true);
        context.requestConf(true);
        context.requestReplayDet(true);
        context.requestSequenceDet(true);
        return context;
    }

    public static GSSCredential newServerCredential(String serviceHost)
            throws GSSException {
        GSSManager manager = GSSManager.getInstance();
        GSSName service = manager.createName(
                "HTTP@" + serviceHost, GSSName.NT_HOSTBASED_SERVICE);
        return manager.createCredential(
                service,
                GSSCredential.DEFAULT_LIFETIME,
                kerberos(),
                GSSCredential.ACCEPT_ONLY);
    }

    public static GSSContext newServerContext(GSSCredential credential)
            throws GSSException {
        return GSSManager.getInstance().createContext(credential);
    }
}
```

Syntax check:

```bash
javac GssSetup.java
```

Example resource-ownership flow in a service: prepare `GSSCredential` under a logged-in `Subject`, create a **separate `GSSContext` per session**, use that context for the token exchange and message operations, and call `context.dispose()`. Call `credential.dispose()` only after all sessions using that credential have finished; never dispose a shared credential while still in use. Never share one `GSSContext` across multiple clients or independent processing threads.

## 7. Context establishment is a token-exchange loop, not a single call

Two-party model:

```text
Client / initiator                          Server / acceptor
  initSecContext(initially empty input)
         │ ---- token A ------------------> acceptSecContext(token A)
         │ <--------------- token B ------ (if any)
  initSecContext(token B)
         │ ---- token C (if any) --------> acceptSecContext(token C)
         · · · until both sides complete the context · · ·
```

Implementation rules:

1. The client calls `initSecContext(byte[] inputBuf, int offset, int len)` for the first time, typically with a zero-length input token. If an output token is returned (non-`null`), **send it to the server**, even if the client's `isEstablished()` is already `true`.
2. The server receives one complete token, calls `acceptSecContext(...)`, sends any output token back, and repeats if the context still needs more tokens.
3. The client processes each new token via `initSecContext(...)`; each side checks the state of its **own context**. The number of round-trips depends on the mechanism, mutual-auth options, and environment.
4. The application defines how bytes are carried: e.g., length-prefixed over TCP or a protocol token field. Never convert binary tokens with `new String(token)` and decode via a charset; for text protocols, use standard Base64 encoding.
5. A `null` output means no token needs to be sent on that turn. Never fabricate dummy/empty tokens to replace `null`. Never assume both sides always finish in exactly one round-trip.

Client-side token-handling skeleton. `TokenChannel` is an adapter that **must be implemented by the application** (framing, size limits, full send/receive, and timeout handling), because GSS-API provides no sockets:

```java
import java.io.IOException;
import org.ietf.jgss.GSSContext;
import org.ietf.jgss.GSSException;

public final class GssTokenFlow {
    private GssTokenFlow() {}

    public interface TokenChannel {
        void send(byte[] token) throws IOException;
        byte[] receive() throws IOException;
    }

    public static void initiate(GSSContext context, TokenChannel channel)
            throws GSSException, IOException {
        byte[] incoming = new byte[0];

        while (!context.isEstablished()) {
            byte[] outgoing = context.initSecContext(
                    incoming, 0, incoming.length);

            // One side may already have isEstablished() == true yet still
            // need to send a final token to the peer.
            if (outgoing != null) {
                channel.send(outgoing);
            }
            if (!context.isEstablished()) {
                incoming = channel.receive(); // returns exactly one complete token
                if (incoming == null) {
                    throw new IOException("Peer closed during GSS handshake");
                }
            }
        }
    }

    public static void accept(GSSContext context, TokenChannel channel)
            throws GSSException, IOException {
        while (!context.isEstablished()) {
            byte[] incoming = channel.receive();
            if (incoming == null) {
                throw new IOException("Peer closed during GSS handshake");
            }
            byte[] outgoing = context.acceptSecContext(
                    incoming, 0, incoming.length);
            if (outgoing != null) {
                channel.send(outgoing);
            }
        }
    }
}
```

`GssTokenFlow.java` compiles with `javac GssTokenFlow.java` but **does not run by itself**: it still requires a `TokenChannel` implementation, credentials, handshake completion protocol, and timeout policy. This is a sequential skeleton for a single session; when integrating HTTP Negotiate, SASL, or stateful protocols, follow that protocol's token-control rules. Never assume one side having `isEstablished() == true` guarantees the peer application has already processed the final token.

After completion, you can verify:

```java
if (!context.isEstablished()
        || !context.getMutualAuthState()
        || !context.getIntegState()) {
    throw new SecurityException("GSS context does not meet policy");
}
GSSName authenticatedClient = context.getSrcName(); // on server side
GSSName authenticatedServer = context.getTargName(); // on client side
// Next, check the principal against application authorization policy.
```

The code above is a **post-handshake** fragment; if application policy mandates confidentiality, also verify `getConfState()` and actual per-message privacy status.

## 8. Protecting data after authentication

Once the context is ready (normally after `isEstablished()`; the API also exposes `isProtReady()` for certain mechanisms), the data-protection APIs are:

- `wrap(data, off, len, MessageProp)`: builds a token protecting integrity and optionally encrypting content. `new MessageProp(0, true)` requests default QOP and privacy; after `wrap`, inspect `getPrivacy()` because the actual state may differ from the request.
- `unwrap(token, off, len, MessageProp)`: decrypts/verifies a token produced by the peer's context and returns the data. Read the status fields in `MessageProp` to decide how to handle it.
- `getMIC(data, ..., MessageProp)` produces a message integrity code (**without** encrypting or bundling the plaintext); `verifyMIC(mic, ..., data, ..., MessageProp)` verifies it on the peer.
- `getWrapSizeLimit(...)` estimates the maximum input size that fits within a protocol's wrapped output token limit.

Illustration using two **already-established contexts belonging to the same session**:

```java
import java.nio.charset.StandardCharsets;
import org.ietf.jgss.MessageProp;

// clientContext and serverContext are two ALREADY AUTHENTICATED contexts.
// This is a fragment, not a standalone runnable program.
byte[] data = "Hello GSS".getBytes(StandardCharsets.UTF_8);

MessageProp outbound = new MessageProp(0, true);
byte[] protectedToken = clientContext.wrap(
        data, 0, data.length, outbound);
if (!outbound.getPrivacy()) {
    throw new SecurityException("Confidentiality was required");
}

// Transmit protectedToken intact over TokenChannel/protocol...
MessageProp inbound = new MessageProp(0, false);
byte[] plain = serverContext.unwrap(
        protectedToken, 0, protectedToken.length, inbound);
String received = new String(plain, StandardCharsets.UTF_8);
```

When only a MIC is needed, compute the MIC on one context and verify it against **the exact same data** on the other context:

```java
byte[] mic = clientContext.getMIC(
        data, 0, data.length, new MessageProp(0, false));
serverContext.verifyMIC(
        mic, 0, mic.length,
        data, 0, data.length,
        new MessageProp(0, false));
```

Results are not fixed strings suitable for pasting as expected stdout: tokens and MICs depend on session keys, mechanism, and context state. Modified data or invalid tokens must be treated as verification failures rather than silently continuing.

**GSS protects individual tokens according to context properties**, whereas protecting the whole channel (metadata, framing, timeouts, protocol requirements, non-GSS endpoints) is a separate architectural decision. When combining TLS with GSS, never assume GSS is bound to TLS unless compatible channel binding has been configured.

## 9. Real-world environment requirements and JAAS

To run real Kerberos authentication, the following conditions are typically required:

1. **KDC/realm and host configuration:** `krb5.conf`/`krb5.ini` or corresponding JVM properties, a resolvable realm, and system clocks within Kerberos skew limits.
2. **Target identity:** a service principal matching the host/canonicalization. For example, service `HTTP/api.example.com@EXAMPLE.COM`; DNS, aliases, and principals must match deployment policy.
3. **Client credentials:** a ticket from login/SSO, ticket cache, or a `Subject` populated by JAAS, depending on deployment.
4. **Server credentials:** keys for the target service principal in a keytab or other protected credential store. The server process needs read permission on the credential source, while keytabs must never go into Git or logs.
5. **Exchange protocol:** token transport with framing, size caps, timeouts, error handling, and post-authentication identity checks.

Illustrative **JAAS config example for an administered Kerberos environment**:

**File `jaas.conf` (paths/keytabs/principals are samples only):**

```properties
KrbClient {
    com.sun.security.auth.module.Krb5LoginModule required
    useTicketCache=true
    doNotPrompt=true;
};

KrbService {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/secure/keytabs/http-api.keytab"
    principal="HTTP/api.example.com@EXAMPLE.COM"
    storeKey=true
    doNotPrompt=true
    isInitiator=false;
};
```

The application invokes `LoginContext("KrbClient")` or `LoginContext("KrbService")` and runs GSS operations under the appropriate `Subject` (such as `Subject.doAs(...)` on Java 17) when relying on the JAAS/`Subject` model. `-Djava.security.auth.login.config=/secure/jaas.conf` selects the JAAS configuration; `-Djava.security.krb5.conf=/secure/krb5.conf` selects the Kerberos configuration. Exact options depend on the runtime environment, JDK/provider, and whether a ticket cache or keytab is used.

Note: `javax.security.auth.useSubjectCredsOnly` affects how the Kerberos implementation locates credentials in Java. Never flip it to `false` as a "fix-all workaround"; first identify the valid credential source, active `Subject`, and security policy.

## 10. Common errors and misconceptions

| Symptom | Causes to check | Resolution |
| --- | --- | --- |
| `GSSException: NO_CRED` or "Failed to find any Kerberos tgt" | Missing ticket/keytab, JAAS not logged in, wrong `Subject`, wrong initiator/acceptor usage | Verify actual login and credentials; select the right role |
| "Cannot locate default realm" already at `createName` | Kerberos realm not configured | Check `krb5.conf`/`krb5.ini` and realm mapping |
| `BAD_NAME` or mismatched principal | Wrong name type, service host, or realm | Distinguish `HTTP@host` from `HTTP/host@REALM`; verify the real service principal |
| `BAD_MECH` | OID specified is unsupported by provider | Compare against `manager.getMechs()` and provider configuration |
| `DEFECTIVE_TOKEN` / invalid token | Truncated, altered, charset-corrupted token, or token from another session | Use proper binary framing, Base64 where needed, and never reuse contexts/tokens |
| Server fails to decrypt ticket / Kerberos integrity error | Mismatched keytab, SPN, kvno, encryption type, or realm | Check service identity and keys provisioned by the Kerberos administrator |
| Clock skew / expired ticket errors | Clock drift or expired ticket | Synchronize time and obtain fresh valid tickets |
| `isEstablished()` yet missing required property | `request...` calls do not guarantee all properties were accepted | Inspect `get...State()` and reject sessions failing policy |

Other critical pitfalls:

- **Never compare tokens against fixed strings.** Tokens vary per session, even between the exact same two principals.
- **Never mix contexts:** tokens from session A must never be fed into session B's context; never share a context concurrently across connections.
- **Never ignore protection outcomes:** `wrap` may not grant requested privacy; check `MessageProp.getPrivacy()`, handle `GSSException`, and check `MessageProp` supplementary flags for replay/sequence if used by the application.
- **Never use client-claimed names as authenticated identity:** the server trusts only `getSrcName()` after authentication succeeds and authorization checks pass.
- **Never enable delegation by default:** `requestCredDeleg(true)` carries major security impact; use only with explicit requirements and appropriate permission scoping.
- **Do not use legacy stream APIs just for convenience:** on Java 17, prefer the `byte[]` overloads of `initSecContext`, `acceptSecContext`, `wrap`, and `unwrap`; stream overloads have been deprecated since Java 11.
- **Do not confuse GSS-API with SASL:** SASL defines a mechanism named `GSSAPI` and its own protocol rules; it can use GSS underneath, but a standalone `GSSContext` does not implement full SASL, authorization identities, or security layer negotiation.

## 11. Application scenario and verification workflow

**Scenario:** Java service A needs to call service B using Kerberos.

1. Identify service B using the proper host-based identity, e.g., `HTTP@api.example.com`, and choose the Kerberos GSS mechanism by OID.
2. A holds a valid initiator ticket; B has the matching acceptor keytab/credential. B creates `GSSCredential.ACCEPT_ONLY` and creates one acceptor context per connection.
3. A creates an initiator context with B's `GSSName`, requesting mutual auth and required properties.
4. Both sides exchange binary tokens via the protocol until complete; transmit every generated output token even if local state is already established.
5. A verifies server authentication and required context states; B reads `getSrcName()` and decides which actions the caller is permitted to perform.
6. If application content needs protection, use `wrap/unwrap` or `MIC` as required; check privacy and verification errors. At session end call `dispose()`, and dispose credentials once no consumers remain.

**QA deployment checklist:** correct name type and OID used? credential role accurate? realm, ticket, and keytab configured? tokens transferred intact and bounded? timeouts enforced? actual context states and identities verified? authorization checked? contexts/credentials properly disposed? secret logging and unnecessary delegation avoided?

## 12. Self-check questions

1. Why do creating `GSSManager` and seeing the Kerberos OID not prove Kerberos login succeeded?
2. Which name type does `HTTP@api.example.com` represent? Why does it differ from `HTTP/api.example.com@EXAMPLE.COM`?
3. What is the difference between `GSSCredential.ACCEPT_ONLY` and `INITIATE_ONLY`? Can a server use an initiate-only credential for `acceptSecContext` by default?
4. Why must a final output token still be sent even when `isEstablished()` on the sending side is already `true`?
5. Is `requestConf(true)` enough to prove a message was encrypted? Which two places must be checked?
6. Why is successful authentication via `GSSContext` insufficient to decide whether a user may view a resource?
7. How does `getMIC/verifyMIC` differ from `wrap/unwrap`?
8. When "Cannot locate default realm" occurs right at `GSSName` creation, which configuration should you inspect first?

## Standard references

- [Java SE 17 — `org.ietf.jgss` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/package-summary.html)
- [Java SE 17 — `GSSManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSManager.html), [`GSSName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSName.html), [`GSSCredential`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSCredential.html), [`GSSContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSContext.html).
- [RFC 2743 — Generic Security Service API](https://www.rfc-editor.org/rfc/rfc2743); [RFC 2853 — Java bindings](https://www.rfc-editor.org/rfc/rfc2853); [RFC 4178 — SPNEGO](https://www.rfc-editor.org/rfc/rfc4178).

**Key connection:** `GSSManager` creates the objects; `GSSName` identifies the peer; `GSSCredential` represents the running party's own credentials; `GSSContext` performs authentication and, once established, provides message-protection operations. Security depends on both identity configuration and post-authentication state and policy checks.
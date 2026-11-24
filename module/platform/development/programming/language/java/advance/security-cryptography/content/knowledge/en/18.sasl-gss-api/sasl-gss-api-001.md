# 18.1 How SASL Solves Authentication in Application Protocols

## 1. The Problem SASL Solves

An application protocol such as SMTP, IMAP, LDAP, or XMPP needs to answer the question: **which identity is this connection end proving, by what method, and after successful authentication, under which identity will it be allowed to act?**

If every protocol reinvented password verification, Kerberos tickets, certificates, or tokens, each would have to handle message exchanges, algorithm changes, authentication errors, and security policies on its own. **SASL (Simple Authentication and Security Layer)** solves this reuse problem: the application protocol provides *a slot for authentication*, while a **SASL mechanism** provides the way to prove identity. The authentication mechanism can be swapped without redesigning the entire protocol.

SASL is standardized in **RFC 4422** and applies primarily to connection-oriented protocols. SASL itself is **not** a single encryption method, a user management service, nor does it automatically turn an insecure connection into a secure one. The actual level of protection depends on the mechanism, server configuration, the protocol carrying it, and a security layer such as TLS.

**Lesson objectives:** distinguish an application protocol from a SASL mechanism; describe the negotiation and authentication steps; understand the difference between authentication identity and authorization identity; select an appropriate mechanism and recognize common implementation mistakes in Java.

## 2. Architecture: the protocol "carries" messages, the mechanism "understands" credentials

~~~text
Application and protocol: SMTP / IMAP / LDAP / XMPP / ...
    │ AUTH / bind command, advertise capabilities, report SUCCESS/FAILURE
    ▼
SASL integration layer
    │ Select mechanism, pass byte-level challenge/response messages
    ▼
SASL mechanism (e.g. PLAIN, SCRAM-SHA-256, GSSAPI, EXTERNAL)
    │ Verify password/proof, Kerberos ticket, external identity...
    ▼
Authentication server + identity mapping + authorization policy
    │
    └── If BOTH authentication AND authorization succeed → application session is usable
~~~

A protocol integrating SASL must define **how to advertise or select a mechanism**, **how to start an authentication session**, **how to transmit each challenge/response message**, **how to abort or handle errors**, and **how to report a success/failure outcome**. For example, SMTP uses the `AUTH` command; LDAP uses a SASL bind. Command framing syntax and on-the-wire value encoding belong to each protocol. The SASL mechanism operates on the logical byte messages inside that frame.

A mechanism may take an initial message from the client (*client-first*), wait for a challenge from the server (*server-first*), or exchange multiple rounds. Therefore, there is no "one universal SASL packet" used verbatim across all protocols. **The mechanism name** and its semantics are the reusable part; **the framing, command ordering, and session state** are defined by the application protocol.

The architectural benefit is that when both sides support a new mechanism and policy permits it, an application can upgrade from an older mechanism to a stronger one while keeping its business flow and the protocol's SASL message transport.

## 3. Authentication flow from connection to logged-in session

1. **Establish the channel and authenticate the server.** For mechanisms that send recoverable secrets such as `PLAIN` or a bearer token, TLS protection and proper server identity verification must be in place before sending credentials. If the protocol upgrades via STARTTLS, capability discovery must be re-executed after the upgrade according to the protocol specification, rather than blindly reusing the old list.
2. **The server advertises valid mechanisms.** For example, the server supports `SCRAM-SHA-256` and `PLAIN` over a TLS channel. The advertised list may depend on the channel, configuration, and policy.
3. **The client selects a mechanism supported by both ends that meets security requirements.** Never "just pick whichever the server lists first." If policy requires SCRAM with channel binding and only PLAIN remains, the client must reject or report an error instead of silently downgrading.
4. **Start the SASL exchange.** The client sends the mechanism name along with an initial response if both the mechanism and the protocol allow it. Otherwise, the server may send a challenge first. Subsequent rounds feed the server's challenge into the client-side mechanism to produce a response, and vice versa.
5. **The server verifies the proof and identity.** The mechanism validates the credential/proof; the server determines the *authentication identity* (who actually proved their identity). The server then checks the *authorization identity* (the identity under which the session wants to operate), including cases where the two identities differ.
6. **The server reports the final outcome using a protocol message.** Only when **the server reports success** and all security/authorization conditions are satisfied should the application treat the connection as authenticated. The client processes any final mechanism data if required by the specification; a library object reporting local round completion cannot substitute for a success response from the server.
7. **Begin application operations with the established permissions.** If the mechanism negotiated a *SASL security layer* (not every mechanism has one), both sides install that layer at the exact point specified by the protocol. Otherwise, the connection continues relying on TLS or the external protection layer.

~~~text
Client                     Protocol server             SASL mechanism / verifier
  |--- TLS + capabilities ------->|                                |
  |<-- mechanisms ----------------|                                |
  |--- select mechanism + data -->|------ validate/init --------->|
  |<-- challenge ---------------|<----- challenge ---------------|
  |--- response ---------------->|------ verify response ------->|
  |<-- SUCCESS/FAILURE ----------|<----- outcome -----------------|
  |--- application commands ----->|  (only on SUCCESS)             |
~~~

The number of rounds and message contents vary by mechanism. `challenge`/`response` frames may be Base64-encoded when placed inside a text-based protocol syntax; **Base64 is only a data representation, completely not security encryption**.

## 4. Concrete example: SMTP using SASL PLAIN over TLS

Suppose the client has established a secure TLS connection to the SMTP server and verified the hostname/certificate. The dialogue below is a **simplified illustration**, using a dummy account `alice` and dummy password `secret`:

~~~text
S: 220 mail.example.test ESMTP ready
C: EHLO client.example.test
S: 250-mail.example.test
S: 250-AUTH PLAIN
S: 250 OK
C: AUTH PLAIN AGFsaWNlAHNlY3JldA==
S: 235 2.7.0 Authentication successful
~~~

Per RFC 4616, the logical payload of `PLAIN` has the form:

~~~text
UTF-8(authzid)  0x00  UTF-8(authcid)  0x00  UTF-8(password)
~~~

With an empty `authzid`, `authcid=alice`, and `password=secret`, the byte sequence is `\0alice\0secret`. The string `AGFsaWNlAHNlY3JldA==` is the Base64 encoding of those exact bytes. An eavesdropper can decode Base64 effortlessly; **`PLAIN` does not keep credentials confidential and does not protect integrity on its own**, so it must be placed inside a suitable TLS channel. The example data is for learning only; never use real accounts and never log credentials or responses.

Key takeaway: `EHLO` and `AUTH` belong to **SMTP**, whereas the byte layout `authzid/authcid/password` belongs to **SASL PLAIN**. Another protocol can carry the same mechanism using completely different command syntax. In a STARTTLS session, the initial greeting and TLS negotiation have their own steps; the client must re-discover capabilities after STARTTLS completes.

If the password is wrong, the server returns an error; if the password is right but the client requests to act under an unauthorized identity, the server must still reject it. These two situations are not synonymous.

## 5. Authentication identity differs from authorization identity

- **Authentication identity (authcid):** the identity bound to the authentication proof, such as `alice` proving knowledge of a password or possession of a Kerberos ticket.
- **Authorization identity (authzid):** the identity whose permissions the client proposes to use in the session, such as `billing-agent`. It can be left empty so the server chooses a default identity according to the mechanism and policy.
- **Authorization decision:** the server must verify whether `alice` is permitted to act as `billing-agent`. The client declaring `authzid=billing-agent` **does not grant permissions** to the client.

For example: an integration job authenticates as service account `job-runner` and requests mailbox access with `authzid=alice`. The server needs an explicit delegation policy; if none exists, it fails that request. Even after SASL succeeds, granular access control (which messages can be read, which operations are permitted, which resource limits apply) remains the application's responsibility.

Do not conflate three distinct concepts: **authentication** verifies the proof of identity; **authorization identity mapping** determines which identity the session operates under; **authorization/permission checks** decide whether each individual operation is allowed.

## 6. Common mechanisms and what to consider when choosing

| Mechanism | Proof / primary flow | Security and application notes |
| --- | --- | --- |
| `PLAIN` | Sends `authzid, authcid, password` (as bytes) | Simple, widely compatible; no security layer. Use **only over an appropriate protected channel**, typically TLS with server verification. |
| `SCRAM-SHA-256` | Challenge/response based on nonce, salt, key derivation, and proof; includes server verification | Does not send raw password on the wire; still requires TLS/policy design against MITM and password guessing, plus safe verifier management. RFC 5802/7677. |
| `SCRAM-SHA-256-PLUS` | SCRAM-SHA-256 plus *channel binding* to the outer secure channel | Binds authentication proof to the TLS channel in use to mitigate certain relay/MITM attacks; both sides must support a compatible channel binding type. |
| `GSSAPI` | Exchanges GSS-API tokens, typically backed by Kerberos | Suitable for Kerberos/SSO environments; requires proper principal, service name, and credential configuration; can negotiate a post-authentication protection layer. |
| `EXTERNAL` | Uses an identity already authenticated by an outer layer or context, such as a TLS client certificate | Server must map and verify the trusted outer identity; SASL does not replace certificate verification. |
| `OAUTHBEARER` | Carries an OAuth 2.0 bearer token inside the SASL exchange | Depends on TLS, token lifetime, and proper issuer/audience/expiry/scope checks; a leaked token can be used by another party. RFC 7628. |

Do not choose `CRAM-MD5` or `DIGEST-MD5` for new designs merely because an older JDK or provider supports them; these are historical options, not modern security defaults. A system must rely on **actually supported mechanisms**, client/server capabilities, and security policy, rather than assuming "SASL automatically supports every mechanism."

### How is SCRAM different from sending a password?

In SCRAM, the client and server exchange nonces, a salt, an iteration count, and proofs/signatures according to the standard mechanism. The server verifies proof that the client knows the password without the client **transmitting the raw password** in SCRAM messages; the client also receives data to verify the server. Simplified handshake:

~~~text
C → S: username + client nonce
S → C: combined nonce + salt + iteration count
C → S: client proof (and channel binding data if present)
S → C: server signature or failure notice
~~~

This is a **conceptual diagram**, not a complete byte specification for implementing SCRAM yourself. SCRAM-SHA-256 follows the detailed rules of RFC 5802 and RFC 7677; the `-PLUS` variant requires exact channel binding with the secure session, including compatibility requirements with current TLS versions. Do not roll your own SCRAM algorithm from this summary. SCRAM **does not** provide a security layer to encrypt application data; use TLS or an appropriate protection layer. Salt and key derivation reduce certain risks but do not completely eliminate offline password guessing if stored verifiers leak.

### Where does GSSAPI fit?

`GSSAPI` is **a SASL mechanism**, not another name for SASL. When using GSSAPI, the protocol carries GSS-API authentication tokens; GSS-API and the underlying mechanism (commonly Kerberos) handle session info and proof. SASL standardizes embedding that exchange into an application protocol. Details on tickets, service principals, keytabs, and mutual authentication semantics belong to the dedicated GSS-API/Kerberos topics.

## 7. How do SASL, TLS, and authorization complement each other?

| Layer | Question answered | What it does not handle on its own |
| --- | --- | --- |
| **TLS** | Is data on the connection protected and is the server peer authenticated according to TLS policy? | Does not inherently identify the application user; a TLS client certificate is only one option if configured. |
| **SASL mechanism** | Which identity does the client prove, by what method, and does the mechanism create a security layer? | Does not define business logic, command syntax for all protocols, or per-resource permissions. |
| **Application protocol** | When is SASL invoked, how are challenges/responses transported, and which command reports the outcome? | Should not invent its own authentication algorithms. |
| **Server authorization** | Who is the authenticated identity allowed to act as, and what may it do? | Cannot blindly trust the `authzid` name declared by the client. |

SASL has the concept of an **optional security layer**: depending on the mechanism and negotiation, this layer can protect integrity or both integrity and confidentiality of *post-authentication* messages. For example, the levels `auth`, `auth-int`, and `auth-conf` are often referenced when a mechanism supports QOP. **Not every mechanism has all three levels**: `PLAIN` and `SCRAM-SHA-256` provide no SASL security layer, whereas certain `GSSAPI` configurations can support them. If no such layer is negotiated, the connection can still be protected normally by TLS.

Because TLS and SASL operate at different layers, "logged in with SASL" **does not prove the transport channel is secure**, and "connected over TLS" **does not prove the client has logged into an application account**.

## 8. Java 17+: using the `javax.security.sasl` API

Java provides the interfaces in the `java.security.sasl` module:

- `Sasl.createSaslClient(...)` / `Sasl.createSaslServer(...)` look up a factory by mechanism registered with security providers; they can return `null` if no matching implementation is found.
- `SaslClient` provides `hasInitialResponse()`, `evaluateChallenge(byte[])`, `isComplete()`, `getNegotiatedProperty(...)`, `wrap(...)`, `unwrap(...)`, and `dispose()`.
- `SaslServer` accepts responses via `evaluateResponse(byte[])`, returns challenges to the protocol, and exposes the authorized identity after completion per the API contract.
- `CallbackHandler` supplies the information required by the mechanism, such as `NameCallback` and `PasswordCallback`. Required callbacks vary across mechanisms; not all of them use passwords.

### Standalone example: generating an initial response for PLAIN

This example **does not open a network connection and does not log into a real SMTP server**. It only shows a Java application supplying credential data to a SASL client so the mechanism produces an *initial response*. In production, enable PLAIN **only after the session's TLS is verified**, and never print credentials or payloads to logs. The password here is a dummy string for learning.

~~~java
// File: SaslPlainDemo.java
import java.util.Base64;
import java.util.Map;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.sasl.Sasl;
import javax.security.sasl.SaslClient;

public class SaslPlainDemo {
    public static void main(String[] args) throws Exception {
        CallbackHandler callbacks = requested -> {
            for (Callback callback : requested) {
                if (callback instanceof NameCallback name) {
                    name.setName("alice");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword("secret".toCharArray());
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        SaslClient client = Sasl.createSaslClient(
                new String[] {"PLAIN"},
                null,                     // authzid: no separate identity requested
                "smtp",                   // service/protocol name
                "mail.example.test",      // target service host
                Map.of(),
                callbacks);

        if (client == null) {
            throw new IllegalStateException("No SASL PLAIN client provider available");
        }

        try {
            if (!client.hasInitialResponse()) {
                throw new IllegalStateException("Demo requires an initial response");
            }
            byte[] response = client.evaluateChallenge(new byte[0]);
            System.out.println("mechanism=" + client.getMechanismName());
            System.out.println("payloadBase64=" + Base64.getEncoder().encodeToString(response));
            System.out.println("clientComplete=" + client.isComplete());
        } finally {
            client.dispose();
        }
    }
}
~~~

Run on a JDK that includes a SASL PLAIN client provider (such as the SunSASL implementation in common OpenJDK/JDK distributions):

~~~bash
javac SaslPlainDemo.java
java SaslPlainDemo
~~~

Expected output from an RFC 4616-compliant PLAIN provider:

~~~text
mechanism=PLAIN
payloadBase64=AGFsaWNlAHNlY3JldA==
clientComplete=true
~~~

Meaning of `clientComplete=true`: the SASL client has finished generating data according to **the PLAIN mechanism**; **no server has verified anything** in this demo. A real application must place `response` into the protocol's authentication command, read the server result, and update session state only after a successful reply. The example intentionally prints the payload to observe the byte format; production code must remove this output, obtain credentials from a proper secret store, and manage credential lifecycles carefully. The server-side PLAIN handler must also verify credentials and permissions; calling `SaslClient` alone does not create a complete authentication system.

### When integrating into a real protocol

The application or protocol driver is responsible for:

1. Verifying TLS, receiving the server's mechanism list **on the current connection**, and filtering it according to security policy.
2. Creating `SaslClient` with the chosen mechanism; if `null`, handling the missing provider instead of silently falling back to a weak mechanism.
3. If `hasInitialResponse()` is true, calling `evaluateChallenge(new byte[0])` and packing it into the opening command as specified by the protocol; otherwise, waiting for a server challenge.
4. Looping through challenge/response exchanges until the protocol reports success, failure, or cancellation; each message must be converted/framed per the protocol's rules (such as Base64 if required by the protocol).
5. Checking the final outcome, establishing a logged-in session only when the server confirms and all security layer, identity, and authorization conditions hold; calling `dispose()` on the client when finished.

**Important:** `SaslClient`/`SaslServer` **do not open sockets, perform TLS, or send SMTP/LDAP commands**. Many Java drivers already integrate the protocol layer; when using such a driver, configure strong mechanisms and TLS on the driver rather than writing a new protocol just to invoke SASL.

## 9. Security checklist for a SASL implementation

- **No downgrade.** The client must enforce a policy for minimum acceptable mechanisms; reconcile capabilities at the right moment, prevent pre/post-TLS upgrade tampering, and handle channel binding downgrade attempts.
- **Authenticate the server and channel.** Enable TLS with proper configuration and verify certificates/hostnames; never send `PLAIN` or `OAUTHBEARER` over an unprotected connection. With Kerberos, specify the exact service principal.
- **Separate identity from permissions.** Enforce `authcid → authzid` mapping on the server; successful authentication does not mean every action is permitted.
- **Protect secrets.** Never log passwords, bearer tokens, or sensitive challenges/responses; protect credential/verifier/keytab stores; clear or limit retention of sensitive data whenever feasible.
- **Limit resources and errors.** Prevent brute force with context-aware rate limiting, cap message sizes, round counts, timeouts, and attempt counts; do not leak account-enumeration details in error messages.
- **Validate state.** If an exchange fails, times out, or drops, grant no privileges; verify re-authentication behavior and security layer transitions against the protocol specification.
- **Do not roll your own cryptography.** Use maintained mechanisms, providers, and libraries; verify actual client/server configuration and capabilities. Conduct separate policy reviews against standards, algorithms, and organizational requirements.

## 10. Misconceptions to avoid

**"Using SASL automatically gives you encryption."** False: SASL can perform authentication only. `PLAIN` transmits passwords in recoverable form; `SCRAM-SHA-256` provides no confidentiality for application data.

**"Base64 protects the password."** False: Base64 only changes the representation to fit bytes into a protocol; anyone who receives those bytes can decode them.

**"`client.isComplete()` means login succeeded."** False: that is only the completion state of the SASL client object for the mechanism. Success for the connection as a whole must come from the protocol's server authentication response.

**"Supplying `authzid` grants permission to impersonate another account."** False: `authzid` is a request; the server decides whether to authorize acting under that identity.

**"SASL requires multi-round challenge/response."** False: `PLAIN` can use a single initial response; SCRAM and GSSAPI typically exchange multiple messages.

**"SASL and GSS-API are the same thing."** False: SASL is a framework for embedding authentication into protocols; `GSSAPI` is one mechanism that uses GSS-API services (usually Kerberos).

## 11. Self-check scenarios

1. An SMTP server advertises `PLAIN` and `SCRAM-SHA-256`. The client has not yet verified TLS. Should it send an initial `PLAIN` response right away? **No.** Secure and verify the channel first; pick a mechanism that meets policy. Even though SCRAM does not send raw passwords, TLS and MITM/channel binding still need to be addressed.
2. User `alice` authenticates successfully but requests `authzid=admin` without delegation rights. What should the server do? **Reject that authentication/authorization request**, and never let the session operate as `admin`.
3. Java prints `clientComplete=true`, but the server returns "authentication failed". What is the session state? **Unauthenticated**. Output from `SaslClient` is part of the exchange and cannot override the server's outcome.
4. A protocol switches from `PLAIN` to `GSSAPI`. Must all business commands be rewritten? **No.** The SASL integration layer still transports challenges/responses and receives the outcome, though the mechanism, round count, identity setup, and security policy change.
5. TLS is already enabled; might SASL still be needed? **Possibly yes**, if the application must identify an account or authorization identity. Server-side TLS typically proves the server's identity, not the user account on its own.

## 12. Standard references

- **RFC 4422 — Simple Authentication and Security Layer (SASL):** https://www.rfc-editor.org/rfc/rfc4422
- **RFC 4616 — PLAIN SASL Mechanism:** https://www.rfc-editor.org/rfc/rfc4616
- **RFC 5802 — SCRAM SASL and GSS-API Mechanisms:** https://www.rfc-editor.org/rfc/rfc5802
- **RFC 7677 — SCRAM-SHA-256 and SCRAM-SHA-256-PLUS:** https://www.rfc-editor.org/rfc/rfc7677
- **RFC 7628 — SASL Mechanisms for OAuth:** https://www.rfc-editor.org/rfc/rfc7628
- **Java SE 21 API — `Sasl`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/Sasl.html

**Takeaway:** SASL defines an integration contract between an *application protocol* and a *pluggable authentication mechanism*. Session security comes from mechanism selection, channel verification, credential validation, identity mapping, permission enforcement, and trusting only the server's final outcome.
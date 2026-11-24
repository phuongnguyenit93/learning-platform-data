# 18.2 SaslClient, SaslServer, and the Challenge–Response Exchange

## 1. The Big Picture

**SASL (Simple Authentication and Security Layer)** is an authentication framework for application protocols that describes how to select a *mechanism* and exchange authentication messages. SASL does not define TCP, HTTP, LDAP, or wire packet formats: a protocol using SASL must specify the command that starts authentication, where tokens are carried, continuation/success/failure states, and how connections are closed. RFC 4422 is the foundational specification.

In Java, the `javax.security.sasl` package (module `java.security.sasl`) models the authentication mechanism through two stateful objects:

| Component | Side | Role |
| --- | --- | --- |
| `SaslClient` | Client | Receives challenges from the server, produces responses, and tracks client-side state. |
| `SaslServer` | Server | Receives responses from the client, verifies credentials, optionally produces new challenges, and determines the authorized identity. |
| `Sasl` | Both | Discovers `SaslClientFactory`/`SaslServerFactory` through registered security providers and creates instances matching the mechanism and configuration. |
| `CallbackHandler` | Both | Supplies data requested by the mechanism (username, password, realm, authorization decision, etc.). |

**Distinguish three layers:** (1) the application protocol transports data, (2) SASL orchestrates authentication, and (3) the mechanism executes the specific algorithm. For example, LDAP can carry tokens for the `GSSAPI` mechanism; SMTP can use another SASL mechanism. Mechanism selection must obey security policy and the capabilities of both endpoints.

## 2. The two Java interfaces and their state

### 2.1. `SaslClient`

Create a client with:

```java
SaslClient client = Sasl.createSaslClient(
    new String[] {"GSSAPI"},  // accepted mechanisms, in preference order
    null,                     // desired authorizationId, if supported by mechanism
    "ldap",                   // protocol/service name
    "ldap.example.com",       // target server name
    props,                    // SASL properties
    clientCallbackHandler
);
if (client == null) {
    throw new IllegalStateException("No matching SASL client mechanism available");
}
```

This is an **API illustration snippet** that works only when `props`, `clientCallbackHandler`, providers, and appropriate service/Kerberos setup are prepared; it is not a standalone program. Key methods:

- `getMechanismName()`: returns the mechanism name actually selected. When passing multiple candidates, send **the exact selected name** to the server; never assume a provider supports the first array element.
- `hasInitialResponse()`: indicates whether the mechanism produces data the client sends immediately upon starting. If `true` and the protocol supports an initial response, call `evaluateChallenge(new byte[0])` to obtain the first token.
- `evaluateChallenge(byte[] challenge)`: processes a server token, updates internal state, and returns a response token. The result may be `null` in the special case of final data accompanying a success status, meaning **no response needs to be sent**; `new byte[0]`, by contrast, is **an actual empty response**.
- `isComplete()`: indicates that the client state machine has finished. This **is not sufficient** to treat login as successful: the protocol/server `SUCCESS` status must still be received.
- `getNegotiatedProperty(...)`, `wrap(...)`, `unwrap(...)`: used after completion if the mechanism negotiated properties or a data protection layer.
- `dispose()`: releases state and sensitive data held by the mechanism.

### 2.2. `SaslServer`

Create a server with:

```java
SaslServer server = Sasl.createSaslServer(
    selectedMechanism, "ldap", "ldap.example.com", props, serverCallbackHandler
);
if (server == null) {
    throw new IllegalStateException("No matching SASL server mechanism available");
}
```

This is also an **API illustration snippet**: `selectedMechanism`, `props`, and the handler are supplied by the application. Key methods:

- `evaluateResponse(byte[] response)`: processes a client token and returns the next challenge; some mechanisms require multiple rounds. The return value may be `null` when no further challenge is needed.
- `isComplete()`: the server-side state machine has finished authentication; depending on the mechanism/provider, authentication failures may be signaled by throwing `SaslException`.
- `getAuthorizationID()`: call **only after** `isComplete() == true`; returns the identity the client is permitted to act as (the authorization identity), which does not have to be identical to the authentication username.
- `getNegotiatedProperty(...)`, `wrap(...)`, `unwrap(...)`, and `dispose()` play the corresponding server-side roles.

Both `SaslClient` and `SaslServer` are **stateful and bound to a single exchange session**. Never share an instance across connections, never reuse an instance after `dispose()`, and never assume `evaluateChallenge`/`evaluateResponse` can be called concurrently from multiple threads.

### 2.3. Callbacks and identity

Mechanisms request data through `CallbackHandler.handle(Callback[])`. Common callbacks include:

- `NameCallback`: the authentication name (authentication identity, e.g., `alice`).
- `PasswordCallback`: the secret used to prove identity; its lifecycle must be managed and it must never be logged.
- `RealmCallback`/`RealmChoiceCallback`: realm information, when required by the mechanism.
- `AuthorizeCallback`: used on the server side to decide whether the authenticated identity may **act under the requested authorization ID**.

**Authentication** answers "who is this?"; **authorization** answers "under which identity or permissions is this party allowed to act?". Seeing the same name in both steps in a simple demo does not mean a real application may skip permission checks. Actual callback types depend on the mechanism and provider; handlers must reject unsupported callbacks with `UnsupportedCallbackException`.

## 3. The challenge–response exchange loop

A general exchange proceeds as follows:

```text
Client (SaslClient)                     Server (SaslServer)
       |                                          |
       |-- AUTH <mechanism> [+ initial token] --->|  [application protocol]
       |<--------------- CHALLENGE ---------------|  evaluateResponse(...)
       |-- RESPONSE ----------------------------->|  evaluateChallenge(...)
       |<----------- next CHALLENGE (if any) -----|
       |-- next RESPONSE ------------------------>|
       |<----- SUCCESS / FAILURE [+ final data] --|  [application protocol]
       |                                          |
```

1. **Select and accept a mechanism.** The client selects only from mechanisms advertised by the server and allowed by local policy. The server verifies that the mechanism is permitted and creates `SaslServer`. The mechanism-selection message belongs to the application protocol; `SaslClient` does **not** send it over the network itself.
2. **Initialize in the right direction.** If `client.hasInitialResponse()` is `true`, the client can generate the initial token via `evaluateChallenge(new byte[0])`; if `false`, the client waits for the server's initial challenge. A protocol that forbids initial responses may require sending an initial empty challenge for a client-first mechanism.
3. **Exchange tokens.** The server passes the received response to `server.evaluateResponse(...)`; the client passes the received challenge to `client.evaluateChallenge(...)`. Each call may advance internal state and produce a token for the peer.
4. **Loop as needed.** Do not assume "one challenge, one response" for every mechanism: some involve multiple turns, mutual authentication, or extra negotiation data.
5. **Confirm completion at both levels.** The server must report `SUCCESS`/`FAILURE` via the protocol. The client accepts success only when both the protocol status and `SaslClient` state agree; the server must enforce both authentication and authorization policies. Any final data accompanying a success notice may still need to be processed by the client.
6. **Only after success** should the authorization ID and negotiated properties or protection layer be used to transition to application data traffic.

`null` differs from an empty byte array: `null` typically means "there is no token to send," whereas `byte[0]` is a zero-length token that the protocol may still need to transmit. You must also distinguish `CONTINUE` from `SUCCESS`; seeing an empty array does not prove authentication is complete.

At the transport level, SASL tokens are **arbitrary binary** `byte[]` arrays. If a protocol uses text lines, it may require Base64; if it is binary, it may transmit length-prefixed payloads. Never casually convert tokens via `new String(bytes)` with a default encoding, never inject newlines, and never drop `0x00` bytes.

## 4. Runnable Java 17+ example: a CRAM-MD5 round-trip inside one JVM

This example uses `CRAM-MD5` because the JDK commonly includes providers for both client and server and can simulate a challenge–response round-trip **without requiring Kerberos or a network server**. CRAM-MD5 is a legacy mechanism with security limitations; **use it only to learn the API and state machine, not in new production systems**. For simulation, both sides are invoked directly in the same process; real applications must transport tokens over a well-defined protocol.

Save the file `SaslRoundTripDemo.java`:

```java
import java.io.IOException;
import java.util.Arrays;
import java.util.Map;
import javax.security.auth.callback.*;
import javax.security.sasl.*;

public class SaslRoundTripDemo {
    // Fixed shared secret for simulation only; NEVER do this in production.
    private static final char[] SECRET = "demo-only-secret".toCharArray();

    public static void main(String[] args) throws Exception {
        CallbackHandler clientHandler = callbacks -> {
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    name.setName("alice");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword(SECRET);
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        CallbackHandler serverHandler = callbacks -> {
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    if (!"alice".equals(name.getDefaultName())) {
                        throw new IOException("Unknown user");
                    }
                    name.setName("alice");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword(SECRET);
                } else if (callback instanceof AuthorizeCallback authz) {
                    authz.setAuthorized(
                        authz.getAuthenticationID().equals(authz.getAuthorizationID()));
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        SaslClient client = Sasl.createSaslClient(
            new String[] {"CRAM-MD5"}, null, "demo", "localhost",
            Map.of(), clientHandler);
        SaslServer server = Sasl.createSaslServer(
            "CRAM-MD5", "demo", "localhost", Map.of(), serverHandler);
        if (client == null || server == null) {
            throw new IllegalStateException("Mechanism not available");
        }

        try {
            // CRAM-MD5 is server-first. An empty response simulates the trigger point.
            byte[] challenge = server.evaluateResponse(new byte[0]);
            int rounds = 0;

            while (!server.isComplete()) {
                if (challenge == null || rounds >= 10) {
                    throw new SaslException("Unexpected protocol state");
                }
                byte[] response = client.evaluateChallenge(challenge);
                if (response == null) {
                    throw new SaslException("Missing client response");
                }
                challenge = server.evaluateResponse(response);
                rounds++;
            }

            if (!client.isComplete()) {
                throw new SaslException("Client/server state mismatch");
            }

            System.out.println("Mechanism: " + client.getMechanismName());
            System.out.println("Authenticated: " + server.isComplete());
            System.out.println("Authorized ID: " + server.getAuthorizationID());
            System.out.println("Rounds: " + rounds);
        } finally {
            client.dispose();
            server.dispose();
            Arrays.fill(SECRET, '\0');
        }
    }
}
```

Compile and run (JDK 17 or later with a provider supporting `CRAM-MD5`):

```bash
javac --release 17 SaslRoundTripDemo.java
java SaslRoundTripDemo
```

Verified output when run on a JDK with a `CRAM-MD5` provider:

```text
Mechanism: CRAM-MD5
Authenticated: true
Authorized ID: alice
Rounds: 1
```

**Reading the code in sequence:** the server receives a simulated start signal and generates a challenge → the client processes it with `evaluateChallenge` to create a response → the server validates the response → both report completion → only then does the application call `getAuthorizationID()`. `rounds = 1` applies only to the CRAM-MD5 flow in this example, not as a default round count for SASL. The server-side callback looks up the password for the username supplied by the mechanism; this program uses a single user and fixed secret for clarity, whereas real systems need a protected credential source and independent permission checks.

If the secret on one side is changed, the exchange must fail (`SaslException` or the corresponding authentication error) and must never transition the application into a logged-in state. If the provider is disabled or lacks an implementation, `createSaslClient`/`createSaslServer` can return `null`; this must never be treated as success.

## 5. Distinguishing the state machine from a real network protocol

The Java snippet above invokes two objects directly, so it is **not** a complete LDAP/SMTP server. When integrating into a real protocol, you must build your own orchestration layer:

- Define frames/commands carrying the mechanism name, initial response, challenge, response, `CONTINUE`/`SUCCESS`/`FAILURE` states, and any final data.
- Preserve **every token byte**, message boundaries, and turn ordering. When messages are long or fragmented across frames, reassemble the complete token before passing it to `evaluateChallenge`/`evaluateResponse`.
- Drive the loop by both protocol message status **and** `isComplete()`; enforce caps on round count, token size, and timeouts; abort the session on protocol errors or state mismatches.
- If the client has an initial response, send it where the protocol permits; if server-first, never send a client token before receiving a challenge. If the server returns final data alongside `SUCCESS`, the client handles it per the mechanism/protocol spec without sending an extra response after completion.
- Signal "authenticated" to the application only after the server genuinely confirms success and the client receives the matching result. On failure, close/abort the session and clean up security state.

A simplified state diagram:

```text
NEW
  -> MECHANISM_SELECTED
  -> EXCHANGING (challenge <-> response, repeated 0..n times)
  -> AUTHENTICATED + AUTHORIZED  [server SUCCESS and consistent state]
  -> APPLICATION_TRAFFIC
                  \-> DISPOSED
  -> FAILED / ABORTED -> DISPOSED
```

This is a conceptual model, **not** a built-in enum in the Java SASL API.

## 6. QOP, authorization, and the relationship to GSS-API

SASL can negotiate **quality of protection** via the `Sasl.QOP` property:

| QOP | Meaning |
| --- | --- |
| `auth` | Authentication only; **does not provide** integrity or confidentiality for application data. |
| `auth-int` | Authentication plus message integrity verification. |
| `auth-conf` | Authentication plus message confidentiality (and integrity) protection. |

After both sides complete, the application can inspect `getNegotiatedProperty(Sasl.QOP)`. Call `wrap`/`unwrap` only if the mechanism and QOP actually support a protection layer (`auth-int`/`auth-conf`); these methods are not valid for every mechanism. The application protocol must also frame protected records according to specification.

**GSSAPI** is a SASL mechanism built on GSS-API, usually backed by Kerberos in the JDK. Configuring GSSAPI requires principals/service names, tickets, and a working Kerberos environment; you cannot simply replace `"CRAM-MD5"` with `"GSSAPI"` in the demo and expect it to run out of the box. The mechanism can provide mutual authentication and QOP negotiation, though the outcome depends on the provider, configuration, and application policy.

`AuthorizeCallback` and `getAuthorizationID()` handle **identity authorization**, while permissions to read or modify business resources must still be enforced afterward by the application. A successful SASL session does not mean the user may access every resource.

## 7. Common mistakes and safety notes

| Mistake | Consequence and fix |
| --- | --- |
| Calling `evaluateChallenge` before knowing who sends the first token | Broken handshake order; check `hasInitialResponse()` and the mechanism/protocol specification. |
| Relying solely on `client.isComplete()` or a non-empty response to declare login successful | Can accept mismatched state or protocol failure; require handling `SUCCESS`/`FAILURE` and server verification. |
| Treating `null` and `byte[0]` as identical | Drops or fabricates extra messages; preserve the semantics of empty tokens. |
| Converting SASL tokens to strings using the default charset | Corrupts binary data; use `byte[]` and the protocol-defined encoding. |
| Assuming every JDK/provider ships every mechanism | `Sasl.createSaslClient/Server` may return `null`; check for null and fail closed. |
| Confusing authentication ID with authorization ID | Can grant wrong privileges; enforce `AuthorizeCallback` and application permissions. |
| Calling `wrap`/`unwrap` before completion or with `QOP=auth` | No protection layer exists; verify negotiated QOP first. |
| Logging passwords/tokens or reusing state from another connection | Secret leakage or state corruption; wipe temporary secrets, call `dispose()`, and use one instance per session. |

In production systems:

1. **Allow mechanisms selectively** according to current policy; CRAM-MD5/DIGEST-MD5 are legacy mechanisms, so never copy teaching examples into production config. Mechanisms like SCRAM may require third-party providers; not every JDK supports them by default.
2. **Protect the channel and mechanism list** with verified TLS or an equivalent protection layer when required by the threat model. SASL does not encrypt traffic by itself, and mechanism advertisement/selection can be downgraded if unprotected. Never use `PLAIN` over an unprotected channel.
3. **Never hardcode credentials**, never return error messages that reveal whether a user exists, and never log sensitive tokens. Server handlers must fetch the right user's secret from a protected store and enforce authorization.
4. **Fail closed** on malformed tokens, timeouts, wrong responses, insufficient QOP, unsupported mechanisms, or inconsistent state between peers.
5. **Clean up sessions** with `dispose()`, close/discard failed connections, and enforce payload size, round count, and timeout limits to prevent unbounded resource consumption.

## 8. Self-check questions

- Why is `Sasl.createSaslClient(...)` returning `null` not equivalent to "wrong password"? (Because no implementation was created for the requested mechanism and policy.)
- Why does the CRAM-MD5 demo call `server.evaluateResponse(new byte[0])` first? (A server-first mechanism needs to produce an initial challenge; the program simulates the protocol trigger.)
- Once `client.isComplete() == true`, should privileges be granted immediately? (No; the server must report success, state must be verified consistent, and business permissions must be checked.)
- When the negotiated QOP is `auth`, should you call `wrap` to "encrypt" messages? (No; no message protection layer was negotiated.)
- Is it safe for two threads to share one `SaslClient` across two connections? (No; the object maintains per-session state.)

## 9. References

- [RFC 4422 — Simple Authentication and Security Layer](https://www.rfc-editor.org/rfc/rfc4422)
- [Java SE 21 — `Sasl` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/Sasl.html)
- [Java SE 21 — `SaslClient` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html)
- [Java SE 21 — `SaslServer` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/SaslServer.html)
- [Java SE 21 — Security Developer's Guide](https://docs.oracle.com/en/java/javase/21/security/)
# 15.7. Sessions, Session Resumption, and Connection Lifecycle

**A new HTTPS request does not necessarily create a new TLS connection. Nor does a new TLS connection necessarily perform a full handshake from scratch.** Two performance mechanisms often confused are **connection reuse (reusing an already-open connection)** and **TLS session resumption (resuming a prior security session on a new connection)**. Both can reduce latency, yet they operate at different layers, require different state, and carry different security implications.

In Java, confusion also arises because classes like `SSLContext`, `SSLSession`, `SSLSessionContext`, `SSLSocket`, `SSLEngine`, `HttpClient`, and connection pools each have their own lifecycle. For instance, `SSLSession.isValid() == true` **does not prove the TCP socket is open**; `SSLSession.invalidate()` **does not immediately close all sockets**; and two requests sent over one HTTP/2 connection **are not** two TLS session resumptions.

This lesson explains three lifecycle layers: **transport connection**, **TLS secure connection/handshake/session state**, and **application/HTTP request**. It then contrasts TLS 1.2 session IDs/tickets with TLS 1.3 PSK resumption, how Java exposes session caches, session timeouts, ticket expiration, 0-RTT, replay, and limitations to keep in mind when verifying production.

> **Standards note:** As of October 2026, the current TLS 1.3 specification is **RFC 9846 (published July 2026)**, replacing RFC 8446 with clarifying updates and tightened requirements. Many Java 17 libraries and docs were written against RFC 8446; the session resumption model remains compatible, though new designs should reference RFC 9846 and actual JDK/provider requirements.

## 1. Learning objectives

After studying this lesson, you can:

- Distinguish **TLS connection**, **TLS session/resumption state**, **TCP socket**, **HTTP keep-alive/connection pooling**, and **HTTP/2 multiplexing**.
- Explain why a single `SSLContext` can maintain a session cache across many connections, while an `SSLSocket` represents one specific connection.
- Describe full handshakes and resumed handshakes in TLS 1.2/TLS 1.3, including `NewSessionTicket`, PSK identity, and PSK binder.
- Distinguish **1-RTT PSK resumption** from **0-RTT early data**, knowing why 0-RTT carries replay risk and forward secrecy limitations.
- Correctly read `SSLSession.getProtocol()`, `getCipherSuite()`, `getCreationTime()`, `getLastAccessedTime()`, `getSessionContext()`, `isValid()`, and `invalidate()`.
- Perform basic configuration of `SSLSessionContext.setSessionTimeout()` and `setSessionCacheSize()` in Java 17+, while understanding that doing so **does not force the server to accept resumption**.
- Describe connection teardown, TLS/HTTP closure, idle timeouts, ticket expiration, server restarts/rotation, and load balancing.
- Design test criteria that genuinely verify full vs. resumed handshakes rather than concluding from timing, HTTP status, or session IDs alone.

## 2. Concepts that must be kept separate

| Concept | What exists? | Can it outlive the next request? | What **not** to infer |
| --- | --- | --- | --- |
| TCP connection | Byte stream between client/server over socket (TLS over TCP) | Yes, if still open and app permits reuse | Does not tell whether handshake was resumed |
| TLS connection | Record-layer security state, keys, and sequence numbers for one connection | Yes, within the still-live connection itself | Does not carry traffic keys verbatim onto a new socket |
| TLS handshake | Negotiation of parameters, key agreement, authentication | Usually once initially per connection, with protocol-defined updates | Not "one handshake per HTTP request" |
| TLS session/resumption state | Information allowing continuation of prior authentication/association on a **new connection** | Yes, while cache/ticket/policy remain valid | Not synonymous with a TCP socket |
| TLS session ticket | Carrier/identifier for resumption state or PSK per TLS version | Yes, per lifetime/policy | Not a password and not an application token |
| HTTP request/response | One business operation of the client | Each operation has its own lifecycle | Does not inherently create a new TLS session |
| HTTP persistent connection | Open HTTP/1.1 keep-alive or HTTP/2 connection | Many requests share the same connection | **Not** TLS resumption |
| Connection pool | Manager of multiple connections to an origin/route | Yes, while the pool keeps connections | Does not guarantee the server still accepts TLS tickets |
| Application session cookie/token | User/app login state | Yes, across multiple TLS connections | Not `SSLSession` or a TLS session ticket |

A three-layer diagram:

```text
APPLICATION (HTTPS)
    Request #1  Request #2  Request #3
          \        |        /
           \       |       /
       HTTP/2 streams or HTTP/1.1 keep-alive
                     |
         One open TLS connection
                     |
             One TCP connection
                     |
           Socket closed after idle / EOF
                     |
            Next time opens new socket
                     |
          Full or resumed TLS handshake
                     |
               Request #4
```

**Key takeaway:** if Request #1 and Request #2 go over the **same socket/TLS connection**, you are observing **connection reuse**, not two resumptions. Only when a new socket is opened and its handshake uses prior authentication state (ticket/session) is it **TLS session resumption**.

### 2.1. A TLS session is not an HTTP login session

A user can log in using a cookie or OAuth token over one TLS connection, and then the network connection is replaced. The HTTP login session may continue if the cookie/token remains valid. Conversely, a TLS session can be resumed across TCP connections after the application-level login has expired.

Lifecycles must remain independent:
- **TLS:** provides an encrypted channel and server authentication (plus client auth in mTLS), governed by handshakes and keys.
- **Application authentication:** session cookies, bearer tokens, mTLS principal mapping, or credentials.
- **Authorization:** determines whether a principal may access a resource/action, checked per policy.
- **Business idempotency/replay:** how duplicate transaction requests are handled.

Never equate "TLS session is alive" with "the user is still logged in with the same permissions".

## 3. Full handshake and connection reuse

### 3.1. Full handshake on a new connection

In TLS 1.3, a typical certificate-based full handshake (simplified):

```text
Client                                                Server
  |                                                    |
  | --- ClientHello (+ key_share, versions, suites) --> |
  | <-- ServerHello (+ selected key_share) ------------ |
  | <-- EncryptedExtensions / Certificate ------------ |
  | <-- CertificateVerify / Finished ------------------ |
  | --- Finished -------------------------------------> |
  | <============== Application Data =================> |
  |                                                    |
   TCP/TLS connection continues carrying HTTP requests.
```

In a full handshake, the server normally proves identity via its certificate and proof of private-key possession during the handshake. The TLS 1.3 key schedule derives traffic secrets over the transcript; record-layer keys are connection-scoped and updatable per protocol.

### 3.2. Reusing the connection

After the full handshake, the client sends multiple HTTP requests over the open connection:

```text
TCP connect + TLS full handshake
        |
     HTTP #1 ------- response #1
        |
     HTTP #2 ------- response #2
        |
     HTTP #3 ------- response #3
        |
     Connection idle / closed
```

With HTTP/1.1 keep-alive, requests are handled sequentially on the same connection per client/server behavior; with HTTP/2, multiple streams run concurrently over one connection. In this case no new handshake occurs between Request #1 and Request #2.

**Do not conflate them:** connection reuse normally saves both TCP setup and TLS handshakes. TLS resumption only **shortens the handshake when a new transport connection must be opened**, and does not itself turn a new socket into an old socket.

## 4. TLS 1.2: session IDs and session tickets

Historical TLS 1.2 includes full handshakes and abbreviated handshakes (resumption). Two typical variants:

### 4.1. Session ID + server-side session cache

```text
First time:
    ClientHello --------------> Server
    Full handshake <----------> Certificate/key exchange...
    Server caches session state with session ID
    Client remembers session ID + relevant secrets

Next time (new TCP connection):
    ClientHello(session_id) --> Server
    Server finds acceptable cached state?
       yes -> abbreviated handshake -> new connection keys
       no  -> full handshake (or handshake failure by policy)
```

Benefit: cuts the cost of several full-handshake operations. Drawback: the server must retain and look up matching session state; multi-node load balancers may need sticky routing or shared caches to improve resume rates.

### 4.2. TLS 1.2 session ticket

The ticket mechanism was historically standardized in RFC 5077 (a historical document superseded by RFC 9846). A server encrypts/authenticates session state into an opaque ticket held by the client. On reconnect, the client presents the ticket; a server holding the matching key recovers the state without storing every session in a database.

Keep in mind:
- Tickets do not remove the need to **protect the server-side ticket-encryption key** and manage its rotation lifecycle.
- Key rotation or unshared ticket keys across nodes can cause resumption to fail and fall back to a full handshake.
- Merely "having a ticket" does not force the server to accept it; timeouts, cipher suites, scope, and policy still apply.
- Never build a custom mechanism to store/decrypt tickets at the application layer in place of the TLS provider.

### 4.3. Study TLS 1.2 to understand it, not to design legacy protocols

Modern deployments prefer TLS 1.3 where available; RFC 9846 updated requirements and removed negotiation of TLS 1.0/1.1. When integrating with legacy systems, configure protocol allowlists per policy rather than enabling weak versions just to boost resumption rates.

TLS 1.2 session resumption and TLS 1.3 PSK resumption **do not use the same handshake syntax**, even though Java's `SSLSession` is an abstraction spanning multiple versions.

## 5. TLS 1.3: resumption via PSK and `NewSessionTicket`

Per **RFC 9846**, TLS 1.3 unifies session resumption under a **pre-shared key (PSK)** model. Resumption PSKs are derived from secrets of an earlier session and associated with a **ticket** issued by the server after the handshake.

### 5.1. When is a ticket issued?

```text
Full TLS 1.3 handshake
       |
       v
Server authenticates / Finished
       |
       v
Application connection ready
       |
       +--> Server MAY issue NewSessionTicket
                  |
                  +--> Client stores ticket/associated resumption state
                               |
                               v
                     Later: another TCP connection
                               |
                               v
                        ClientHello offers PSK identity
                               |
                     Server MAY accept or decline
```

The **MAY** clauses are crucial:
- The server **may** issue multiple tickets, one ticket, or none.
- The client **may** choose not to store or offer a ticket.
- The server **may** decline resumption even when the client offers a ticket.
- Because `NewSessionTicket` can arrive **after the main handshake finishes**, a client closing the connection too quickly may miss messages needed for resumption. Depending on framework/provider, reading, caching, and processing post-handshake messages affects outcomes.
- Tickets have lifetimes and policy limits; per RFC 9846, tickets must never be cached indefinitely just because the application stays running.

### 5.2. New handshake with PSK

```text
Client holding ticket/PSK from prior session   Server holding policy/ticket keys
                |                                           |
new TCP connection                             new TCP connection
                |                                           |
ClientHello + PSK identity + binder ---------> |
                |                        Check PSK/ticket age/scope
                |                        and selected handshake mode
                | <---------------- ServerHello + accepts PSK
                |                   (may also use fresh DHE key_share)
                | <---------------- EncryptedExtensions / Finished
Client Finished ------------------------------> |
                |                                           |
          New record-layer traffic keys for this connection
                |                                           |
              Application data over the new TLS connection
```

In TLS 1.3 resumption, the same certificate authentication exchange as a full certificate-based handshake need not repeat; server authentication relies on the PSK linked from the prior connection. **Never interpret this as the client no longer needing hostname checks**: implementations must bind PSK usage to the right identity, SNI, ALPN/application, and security policy.

The **PSK binder** proves the client knows the matching PSK and binds the relevant portion of `ClientHello`. Clients never send plaintext PSKs or hand-roll binders with `HMAC(password)` outside TLS; the TLS implementation handles this.

### 5.3. PSK-only and PSK-DHE do not share identical guarantees

TLS 1.3 defines PSK modes:
- **`psk_ke` (PSK-only):** key establishment relies on the PSK without adding fresh (EC)DHE to that 1-RTT handshake.
- **`psk_dhe_ke` (PSK + ephemeral DHE):** includes fresh ephemeral key agreement, contributing forward secrecy for new traffic per protocol design.

Hence never state "a TLS 1.3 resumed session always uses fresh DHE" or "resumption fully protects traffic if the ticket key/PSK leaks". You must know which mode the server picks, ticket lifetime/rotation, and the threat model.

**Important per RFC 9846:** never reuse `KeyShare` values across connections when implementing the protocol. Use standard TLS libraries; never attempt to cache ephemeral DH private/public keys to "speed up" handshakes.

### 5.4. Tickets are TLS-layer bearer material

A ticket is not necessarily a raw key itself, yet it enables resumption; TLS provider ticket/PSK material can be highly sensitive. Never log raw tickets, PSKs, or session secrets to application logs. Systems must protect server ticket keys and client-side resumption caches while enforcing lifetimes, revocation, and scope.

## 6. What is 0-RTT early data? Why is it unlike normal resumption?

In TLS 1.3, once an eligible PSK exists, the protocol **may** let the client send some application data **right inside the first flight of a new handshake** (0-RTT early data). This is an optional feature, and **does not mean** every TLS 1.3 resumption uses 0-RTT.

```text
1-RTT Resumption:
ClientHello(PSK offer) -------------------------->
                     <---------------- ServerHello/Finished
Client Finished ------------------------------->
Application Data <=============================>

Resumption + 0-RTT (only when explicitly enabled/accepted):
ClientHello(PSK offer) + Early Data ------------>
                     <---------------- ServerHello/Finished
Client Finished ------------------------------->
Normal Application Data <======================>
```

### 6.1. Security differences

RFC 9846 warns that **0-RTT early data** has weaker security properties than 1-RTT data:

1. **No forward secrecy for the 0-RTT data itself**, because it is encrypted under keys derived from the offered PSK before receiving a fresh server key share for the new session.
2. **Cross-connection replay risk**. An attacker can attempt to replay `ClientHello`/early data to the server or cluster within the allowed window.
3. TLS-layer anti-replay mitigations reduce risk but **do not replace business-command controls**. Network conditions, multi-region setups, and retries can still cause duplicate delivery.
4. A server may **reject early data** yet continue the handshake. Applications must know which data was or was not processed and how to retry safely.
5. Support for 0-RTT depends on protocol/application profiles, server policy, tickets, and API/provider capabilities. **Never assume Java 17 `HttpClient` sends 0-RTT automatically just because a cache exists.**

### 6.2. Examples of requests suitable vs. unsuitable for 0-RTT

| Request | Default 0-RTT stance? | Reason |
| --- | --- | --- |
| Read-only `GET`, genuinely side-effect-free and permitted by profile | May be considered | Must tolerate replay and request authentication policy |
| Metadata-only `HEAD` | May be considered | Still check logging/billing/rate-limit effects |
| `POST /transfer-money` | **No** | A replay can trigger duplicate transfers |
| `POST /delete-account` | **No** | Effects are non-idempotent/not replay-safe |
| `POST /issue-token` | **No** if side effects or weak nonce logic exist | Replay can mint multiple credentials |
| `POST /create-order` even with `requestId` | No by default; consider only with a profile and **genuinely safe** idempotency | Idempotency store must be atomic and properly scoped |
| API with login cookie but stateful | No by default | A valid cookie does not make a request replay-safe |

"HTTP GET is usually idempotent" does not automatically clear every GET for 0-RTT: some GET endpoints cause side effects or leak state-dependent data. Applications must verify safety, enforce replay controls, and require an explicit profile.

### 6.3. Idempotency does not eliminate all risk

Even if an endpoint checks `Idempotency-Key`, if the idempotency store lives on only a single node, two early-data requests hitting two nodes can still execute twice. Design for atomicity, principal/tenant namespacing, expiration, business keys, and safe retry handling.

**Lesson:** 0-RTT is an optimization requiring dedicated security design; **1-RTT session resumption** already delivers performance gains without forcing the client to send risky data before handshake completion.

## 7. Lifecycle of a TLS session/ticket

A session is not "valid forever" merely because a handshake once succeeded.

### 7.1. Phases

```text
HANDSHAKE AUTHENTICATED
         |
         v
SESSION / RESUMPTION STATE CREATED
         |
         v
STORED / AVAILABLE
  client cache or ticket
  server cache or ticket keys
         |
         +---------> USED IN NEW HANDSHAKE IF POLICY ACCEPTS
         |                          |
         |                          +--> new connection, new traffic keys
         |                          +--> possibly new tickets
         |
         +---------> EXPIRES / INVALIDATED / EVICTED
         |                 |
         |                 +--> new connection needs full handshake
         |
         +---------> SERVER KEY/CONFIG ROTATION
                           |
                           +--> resumption may be declined
```

Reasons a session does not resume:
- Server did not issue a ticket, client did not receive it yet, or client cache was cleared.
- Ticket/session expired by protocol age, server policy, or provider cache timeout.
- Server restart lost in-memory state or rotated ticket-protection keys.
- Load balancer routed to a node lacking matching resumption state/keys.
- Client used a different `SSLContext` or trust/identity configuration.
- SNI, ALPN, TLS version, cipher-suite hash, or authentication policy changed.
- Server declined resumption because security policy changed, a cert/key was revoked, or a security event occurred.
- Session was evicted from cache due to size limits.
- Resumption was disabled by policy or implementation.

**Not every fallback is a bug.** A full handshake is safe and expected behavior whenever prior state is no longer suitable.

### 7.2. Which timeouts govern what?

| Timeout / lifetime type | What expires? | Effect |
| --- | --- | --- |
| TCP connect timeout | Waiting to establish transport connection | Socket connect fails before any TLS handshake |
| TLS handshake timeout | Waiting for handshake completion | New connection fails to become ready |
| Socket read timeout | Waiting to read bytes on socket | May fail I/O; depending on API, does not necessarily clear session cache |
| HTTP request timeout | A single HTTP call | Request may cancel; not a TLS ticket TTL rule |
| HTTP idle connection timeout | Open yet unused connection | Pool closes socket; next call needs a new connection |
| TLS session cache timeout | How long a cache entry may be reused | Can force a full handshake next time |
| Ticket lifetime | How long a resumption ticket/PSK is offered/accepted | Once expired, cannot resume with that ticket |
| Server ticket-key rotation | Server key decrypting/verifying issued tickets | Older tickets may no longer be accepted |
| App authentication/session expiry | Application user/token/cookie | User must reauthenticate even if the TLS session is valid |

Never configure `SSLSessionContext.setSessionTimeout(600)` and assume "all TCP sockets will close automatically after 600 seconds". That is a **session-cache policy**, not a connection idle timeout.

### 7.3. Both sides may have different limits

The client may still hold a ticket after the server rotated its ticket key; the client may offer the PSK identity and be declined by the server. Conversely, the server may still support resumption after the client evicted the ticket. Success requires **agreement from both sides** during the new handshake.

## 8. Which Java 17+ APIs represent TLS sessions?

### 8.1. `SSLContext`

`SSLContext` holds TLS provider configuration initialized with KeyManagers, TrustManagers, and an appropriate randomness source. One context can create sockets/engines for many TLS connections.

`SSLContext` also exposes:
- `getClientSessionContext()`: context managing client-side sessions per provider capability.
- `getServerSessionContext()`: context managing server-side sessions per provider capability.

Never treat one context as "one single TLS session"; it is the **factory infrastructure creating connections and managing state**.

### 8.2. `SSLSessionContext`

Key APIs:

```java
SSLSessionContext sessions = sslContext.getClientSessionContext();

sessions.setSessionTimeout(600); // timeout in seconds
sessions.setSessionCacheSize(128); // cache entries limit

int seconds = sessions.getSessionTimeout();
int limit = sessions.getSessionCacheSize();
```

Meaning:
- `setSessionTimeout(int seconds)` adjusts the time limit for sessions retained in the provider-managed cache. **`0`** per API means no time limit enforced by this setting; it does not mean resumption is disabled.
- `setSessionCacheSize(int size)` adjusts the limit on cached sessions. **`0`** means no size limit enforced by this setting; it does not mean the cache is empty or disabled.
- Negative values are invalid and normally throw `IllegalArgumentException` per API.
- `getIds()` enumerates cached session IDs as supported by the implementation; `getSession(byte[])` retrieves by ID where available.
- In TLS 1.3, a server may issue multiple tickets and providers track internal state differently; **`getIds()` is not guaranteed to map one-to-one with tickets**, nor does a session ID mean the same thing as in TLS 1.2.
- Cache timeout and size are only **one part of policy**. The server can still decline; ticket lifetimes and TLS implementation rules impose additional bounds.

**Note:** never arbitrarily set cache size/timeout to `0` hoping to "disable" caching; if policy requires disabling resumption, read the provider docs, apply supported configuration, and verify with a wire handshake trace.

### 8.3. `SSLSession`

`SSLSession` represents info about an established TLS session in the JSSE model, providing useful methods:

| API | What can you inspect? | Limitation |
| --- | --- | --- |
| `getProtocol()` | Version such as `TLSv1.3` | Does not tell whether the handshake was full or resumed |
| `getCipherSuite()` | Negotiated suite | Does not mean a ticket was used |
| `getPeerPrincipal()` | Peer principal if authenticated in session | Can throw if peer was unauthenticated; does not replace authorization |
| `getCreationTime()` | Session creation timestamp per model/provider | Not the timestamp of each HTTP request |
| `getLastAccessedTime()` | Last accessed timestamp per model/provider | Not the socket's network idle timer |
| `getId()` | Session ID bytes per JSSE | Not a reliable wire ticket ID to prove resumption |
| `getSessionContext()` | Cache context owning the session, may be null | Does not say whether the connection is still open |
| `isValid()` | Whether the session may still be valid per API | Does not guarantee the socket is open or server will accept the ticket |
| `invalidate()` | Marks the session unusable for future resume/join per API | Does not automatically close established TLS connections |
| `getPeerCertificates()` | Peer certificate chain if present | Does not replace certificate/hostname validation or authorization |

In TLS 1.3, how JSSE providers map sessions onto tickets/IDs and update timestamps can vary. Never build business state on `SSLSession.getId()`, `getCreationTime()`, or an assumption that session object identity proves a resumed handshake.

### 8.4. `SSLSocket`, `SSLEngine`, and HTTP clients

- `SSLSocket`: traditional socket-based TLS with `startHandshake()`, `getSession()`, `close()`. Requires proper trust and endpoint identity config.
- `SSLEngine`: I/O-independent TLS state machine used by NIO/frameworks. The application handles wrap/unwrap, handshake status, close inbound/outbound, and buffers.
- `java.net.http.HttpClient`: manages connections, pooling, HTTP/2, and TLS behind its abstraction. `HttpResponse.sslSession()` can expose session metadata, yet **does not** directly expose full reuse/resumption decisions.
- `HttpsURLConnection`: also exposes TLS info; never assume two responses imply two handshakes.

Never invent a "cache `SSLSocket` forever" scheme to preserve security state. A socket may have closed, lost network, hit idle timeout, failed updated certificate policy, or belong to a different origin.

## 9. Java 17+: offline program to understand the session cache

The example below intentionally **makes no network connections**; it creates a new `SSLContext`, retrieves the client and server session contexts, sets timeout/cache sizes, and reads back the parameters.

This helps separate **configuring session-cache capabilities** from **actually executing TLS handshakes/sessions**. The demo makes no claim that resumption happened without a remote server.

Create **`TlsSessionCacheDemo.java`**:

```java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSessionContext;

public class TlsSessionCacheDemo {
    static SSLContext createContext() throws GeneralSecurityException {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, new SecureRandom());
        return context;
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = createContext();

        SSLSessionContext client = context.getClientSessionContext();
        SSLSessionContext server = context.getServerSessionContext();

        client.setSessionTimeout(600);
        client.setSessionCacheSize(128);
        server.setSessionTimeout(300);
        server.setSessionCacheSize(64);

        System.out.println("Client session timeout (s): "
                + client.getSessionTimeout());
        System.out.println("Client session cache size: "
                + client.getSessionCacheSize());
        System.out.println("Server session timeout (s): "
                + server.getSessionTimeout());
        System.out.println("Server session cache size: "
                + server.getSessionCacheSize());

        boolean badTimeoutRejected = false;
        try {
            client.setSessionTimeout(-1);
        } catch (IllegalArgumentException expected) {
            badTimeoutRejected = true;
        }

        boolean badSizeRejected = false;
        try {
            client.setSessionCacheSize(-1);
        } catch (IllegalArgumentException expected) {
            badSizeRejected = true;
        }

        System.out.println("Negative timeout rejected: " + badTimeoutRejected);
        System.out.println("Negative cache size rejected: " + badSizeRejected);
        System.out.println("Client and server cache objects differ: "
                + (client != server));

        // This program creates no SSLSocket or SSLEngine handshake.
        System.out.println("TLS handshakes performed by demo: 0");
    }
}
```

Compile and run with Java 17+:

```bash
javac TlsSessionCacheDemo.java
java TlsSessionCacheDemo
```

Verified stdout on a Java 17-compatible `SunJSSE` JDK:

```text
Client session timeout (s): 600
Client session cache size: 128
Server session timeout (s): 300
Server session cache size: 64
Negative timeout rejected: true
Negative cache size rejected: true
Client and server cache objects differ: true
TLS handshakes performed by demo: 0
```

### 9.1. Explaining the results

- The setters/getters confirm **the context's cache configuration**, not that any session was created.
- Client and server session caches differ because they represent two independent TLS roles.
- Negative arguments are rejected as invalid cache durations or sizes.
- The final line states the code path explicitly: no socket or engine handshake was opened. **Never write a unit test claiming "session resumption worked" based on this program.**
- Other providers may have distinct session-cache behavior; run tests in the actual target environment for compatibility checks. The program sets no certificate/hostname policy because it connects to no endpoint at all.

### 9.2. Pitfalls when configuring production

Calling `setSessionTimeout(600)` does not:
- Create a TLS session ticket.
- Guarantee the server agrees to resume for ten minutes.
- Configure HTTP keep-alive idle timeouts.
- Close connections after ten minutes.
- Enable 0-RTT.
- Re-validate certificates or app principals every 600 seconds.
- Guarantee server ticket keys stay valid or caches are shared across nodes.

Similarly, `setSessionCacheSize(128)` is an implementation cache limit, not a limit of 128 TCP connections, 128 concurrent users, or 128 HTTP requests.

## 10. Java 17+: observing `SSLSession` in a real HTTPS request

The second example uses `HttpClient` against a real HTTPS address. It opens a network connection and can display the protocol/cipher suite; because results depend on network, server, proxy, provider, and connection pool, **there is no fixed stdout**.

File **`ObserveHttpsSession.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Optional;
import javax.net.ssl.SSLSession;

public class ObserveHttpsSession {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        URI uri = URI.create("https://example.com/");
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        for (int i = 1; i <= 2; i++) {
            HttpResponse<Void> response = client.send(
                    request, HttpResponse.BodyHandlers.discarding()
            );
            Optional<SSLSession> maybeSession = response.sslSession();
            System.out.println("Request: " + i);
            System.out.println("HTTP status: " + response.statusCode());
            System.out.println("TLS protocol: " + maybeSession
                    .map(SSLSession::getProtocol).orElse("not exposed"));
            System.out.println("Cipher suite: " + maybeSession
                    .map(SSLSession::getCipherSuite).orElse("not exposed"));
        }
    }
}
```

Run:

```bash
javac ObserveHttpsSession.java
java ObserveHttpsSession
```

What can be observed:
- Both requests share **one `HttpClient` instance**, increasing the likelihood of connection pooling without guaranteeing both travel on the same socket.
- `response.sslSession()` can display protocol/cipher suite. It **has no standard `"isResumedHandshake"` boolean**.
- If the pool reuses an already-open connection, the second request **performs no new TLS handshake** and produces no resumption event to measure.
- If the server/route/proxy closes the connection between requests, the client opens a new connection; the new handshake **may be full or resumed** depending on conditions.
- A server can respond with HTTP/1.1 or HTTP/2; HTTP version cannot be inferred from the TLS cipher suite alone.
- If the TLS handshake fails or network is unavailable, the example throws an exception instead of printing stdout. Never disable certificate verification to "make it run".

**Never log raw `SSLSession.getId()`, tickets, key material, or HTTP cookies.** When debugging is needed, use security-reviewed logging in a controlled test environment.

### 10.1. How do you prove a handshake genuinely resumed?

A reliable test must:
1. Control both test client and server, with known TLS provider/configuration and peer identity.
2. First perform a **full authenticated handshake**; confirm a session ticket was issued and actually received/stored by the client.
3. Close the **actual transport/TLS connection**, while intentionally keeping the resumption cache/PSK state.
4. Open a **new transport connection** with the same endpoint, policy, and context.
5. Collect evidence from **TLS handshake debug/protocol traces** showing the client offered a PSK and the server selected PSK/resumption (or TLS 1.2 selected session ID/ticket).
6. Retest after cache eviction, ticket expiration, or ticket-key rotation; verify fallback to a full handshake.
7. Verify certificate validation and expected identity remain enforced per protocol/resumption policy.
8. Verify 0-RTT does not occur unless the application intentionally supports it.

**Insufficient evidence:**
- The second handshake was "faster".
- `SSLSession.isValid()` is `true`.
- `getId()` is identical or different.
- HTTP status is `200`.
- The second response used the same `HttpClient`.
- `SSLSession.getCreationTime()` stayed unchanged.
- The TCP connection was reused so no new handshake occurred at all.

When reading TLS 1.3 traces, remember many handshake messages and traffic are encrypted; use appropriate diagnostic/provider tooling and avoid exporting session secrets/keys externally.

## 11. Session cache and connection pool: two distinct stores

### 11.1. What does a connection pool hold?

An HTTP connection pool can hold **already-handshaked sockets**, along with:
- Remote endpoint/origin, proxy route, network interface.
- HTTP/1.1 or HTTP/2 protocol, stream state.
- Live TLS connection.
- Idle timeout, max connections, keep-alive policy.
- Concurrency limits, HTTP/2 `GOAWAY`, connection health.

Main purpose: avoid opening a new socket and running another handshake when a usable live connection exists.

### 11.2. What does a TLS session cache hold?

Depending on protocol/provider, a TLS session cache holds resumption state, PSKs/tickets/session IDs, and metadata sufficient to **shorten the handshake on a new connection**. Never mistake it for a live socket.

### 11.3. Combining both caches

```text
HTTP request arrives
       |
       v
HTTP connection pool contains usable live connection?
       |
   +---+---+
   |       |
  YES      NO
   |       |
reuse      open new TCP connection
existing       |
TLS conn       v
   |       TLS library checks resumption state
   |           |
   |       +---+---+
   |       |       |
   |     ticket   no ticket / rejected
   |     valid       |
   |       |          |
   |     resumed    full handshake
   |     handshake
   |       |          |
   +-------+----------+
           |
           v
       Send HTTP request
```

Therefore, increasing connection-pool reuse can result in **fewer new handshakes**, making the resumption ratio across all requests appear low even while performance is great. Conversely, lowering idle timeouts causes more new sockets and resumption attempts—which is not automatically better for security or performance.

### 11.4. HTTP/2, HTTP/3, and QUIC

- With **HTTPS HTTP/2 over TLS/TCP**, multiple streams share one TLS connection; there is no separate TLS handshake per stream.
- With **HTTP/3**, the transport is QUIC and TLS 1.3 is integrated into QUIC rather than running like ordinary `SSLSocket` TLS-over-TCP. QUIC has connection migration, connection IDs, and resumption/0-RTT mechanics distinct from TCP keep-alive; consult RFC 9000/9001 and the corresponding HTTP/3 stack.
- Never assume a standard Java 17 `java.net.http.HttpClient` supports every HTTP/3/QUIC feature depending on deployment. Never apply TCP socket management assumptions directly to QUIC without verifying the implementation.

## 12. Ending a connection: closing sockets, `close_notify`, and session cache

This area frequently causes lifecycle bugs.

### 12.1. Four distinct actions

| Action | Primary effect | What it does NOT necessarily do |
| --- | --- | --- |
| Close HTTP response body/stream | Frees request resources, lets connection pool reuse or close socket | Does not necessarily clear TLS resumption state |
| Close `SSLSocket` / TLS connection | Stops using the connection and releases related resources | Does not necessarily invalidate cached sessions/tickets |
| `SSLSession.invalidate()` | Marks the session unusable for future resume/join per API | Does not close already-established connections |
| Ticket expired / evicted | Can no longer resume using that ticket | Does not kill live sockets already transmitting data |

Applications should never try to "kill an SSL session" merely by calling `close()` on an HTTP response, or "close a socket" via `SSLSession.invalidate()`.

### 12.2. TLS `close_notify`

TLS defines a `close_notify` alert to signal that a party will send no further data over the TLS channel per protocol semantics. Over TCP, an abrupt EOF or connection reset differs from orderly TLS closure.

Exact behavior regarding half-close, EOF, HTTP framing, and shutdown APIs depends on the protocol and stack. Never build a program reading sensitive data that **treats an unexpected EOF as proof a message is complete** when the protocol lacks proper length/framing/integrity checks.

With standard HTTPS clients, the framework manages TLS connection shutdown and pooling. With `SSLEngine`, the application must properly invoke `closeOutbound()`, wrap closing records, and handle `closeInbound()` per API/provider—never simply call `ByteBuffer.clear()` or ignore handshake status.

### 12.3. Invalidation does not replace key rotation or certificate revocation

If a TLS session is invalidated on the client, a server that issued a ticket may still hold state or the ticket key; enforce policy **on both appropriate sides**. During a private key/certificate or PSK/ticket key incident, systems typically must evaluate resumption scope, rotate server keys, clear caches, revoke credentials, and bound ticket acceptance windows; calling `invalidate()` on a local Java session **is not** global revocation.

For currently open connections, deciding whether to terminate immediately or re-apply policy is a separate security and operational decision.

## 13. Authentication, certificates, and resumption lifecycle

### 13.1. Resumption builds on prior authentication

A normal TLS 1.3 PSK resumption inherits the security binding from an earlier handshake and validly issued ticket/state. It may omit repeating server `Certificate` and `CertificateVerify` on every resumed handshake.

This imposes operational requirements:
- Never extend trust to a revoked certificate or compromised key without explicit policy.
- Bound ticket age, resumption chains, and key lifetimes per security policy.
- Ensure matching SNI, ALPN, protocol, cipher hash, and principal binding.
- If the certificate or mTLS client principal changes, decide whether existing resumption state remains permitted.
- If login/authorization refresh policies exist, enforce them at the application layer; never use resumption to bypass permission checks.

RFC 9846 guides limiting the total time resumption state may persist from an earlier authentication, accounting for certificate lifetime, revocation exposure, and time since the last online authentication.

### 13.2. Hostname verification must never be skipped

When a client opens a new TLS connection to `payments.example.com`, reusing a PSK/ticket from a prior session must stay scoped to the exact identity. Never use a "valid-looking" ticket to connect to an arbitrary server simply because it offers the same cipher suite.

If the application disables hostname verification or uses trust-all, MITM risk remains. TLS resumption **cannot fix** a broken trust manager or missing certificate validation from the initial handshake.

### 13.3. mTLS and client certificate lifecycle

With mTLS, the server may have verified the client certificate in the full handshake. When resuming via a session/ticket tied to client identity, the server must ensure policy still permits access; user/app permissions may have been revoked or tenant assignments changed.

A service must never blindly grant admin rights simply because a resumed connection carries old authentication state:
- Verify identity/principal mapping and policy validity windows.
- Resolve certificate identities and key IDs to tenants/roles from an authoritative source.
- Support revocation/session invalidation matching cluster architecture and token/key lifecycles.
- Avoid embedding long-lived application permissions inside TLS tickets without expiry/version/revalidation policies.

## 14. `KeyUpdate` is not resumption

In TLS 1.3, `KeyUpdate` rotates application traffic keys inside an **existing TLS connection** per protocol. It does not:
- Open a new TCP connection.
- Create a new HTTP request.
- Automatically re-verify certificates.
- Necessarily issue a new session ticket.
- Prove that a resumed handshake happened.

Distinguish clearly:

```text
Same TLS connection:
    handshake -> traffic keys A -> KeyUpdate -> traffic keys B
                                (transport connection remains)

Resumption:
    connection #1 handshake -> ticket/state
              [connection #1 closes]
    connection #2 new handshake using PSK/ticket -> new traffic keys
```

When debugging or designing key rotation, never mistake key-update events for session resumption rates.

## 15. Load balancers and multi-node systems

An API gateway fronting multiple backend nodes may involve:
- TLS termination at the load balancer, with backends receiving internal HTTP/gRPC.
- TLS termination at each application instance.
- A proxy/mesh layer performing mTLS between services.
- Instances holding distinct caches or ticket keys.

When a client connects repeatedly:
- If TLS terminates at the gateway, **session resumption is decided at the gateway**, not by the backend service's `SSLContext`.
- If TLS terminates at individual nodes with local server-side session caches, a new connection landing on another node may do a full handshake for lack of state.
- If server-issued tickets use shared keys, multiple nodes can resume smoothly; **sharing ticket keys expands the blast radius** if one node is compromised and demands secure key distribution/rotation.
- If 0-RTT is enabled across multiple zones, **cross-zone anti-replay coordination** is needed; never treat a single-node local cache as cluster-wide replay protection.
- Restarts or rolling deployments can cause cache misses or rotated ticket keys, increasing full handshakes. That can be completely expected behavior.

Design must balance performance, scalability, and secrecy:
- Share ticket keys/trust material only within policy-approved boundaries.
- Rotate with bounded overlap, capped ticket lifetimes, and auditing.
- Keep caches near the TLS termination tier; keep TLS secrets out of application logs.
- Measure full/resumed handshake ratios **at the actual TLS termination layer**, not at an upstream/downstream service that never sees the handshake.

## 16. Measuring and debugging without leaking TLS secrets

### 16.1. Metrics that are genuinely useful

- Count of **new TCP connections** and **TLS handshakes** over a time window.
- Count of **full handshakes** vs. **resumed handshakes** confirmed by the server/provider.
- Ticket issuance rate, offer/accept/reject rate, expiration, and cache hit/miss/eviction.
- TLS handshake latency broken down by version/cipher/route, without inferring resumption solely from latency.
- HTTP connection pool reuse, idle closures, and HTTP/2 stream concurrency.
- Handshake failures grouped by certificate validation, SNI/ALPN mismatch, expired tickets, key rotation, and network errors.
- 0-RTT offered/accepted/rejected, replay attempts, and business idempotency outcomes if enabled.

**Never lump everything under "TLS sessions" without explicit units.** Sessions differ from connections, handshakes, and requests.

### 16.2. Java TLS debugging

In test environments, JSSE offers SSL/TLS debug options, such as the common flag:

```bash
java -Djavax.net.debug=ssl,handshake,session ObserveHttpsSession
```

This is a diagnostic tool, **not a production default**. Debug logs can expose sensitive metadata like hostnames, certificate subjects, versions, and session IDs/ticket details depending on provider and log level. Never publish unreviewed raw traces; avoid unnecessary key logging or secret extraction.

What to look for in traces/protocols:
- When a new connection opens, are there new `ClientHello`/`ServerHello` messages?
- Is a `pre_shared_key` identity/PSK binder offered in TLS 1.3?
- Did the server select PSK/resumption, or fall back to a certificate-based full handshake?
- Was a `NewSessionTicket` after a full handshake actually received by the client?
- Did the second HTTP request simply reuse the first socket?

**Checking `CipherSuite` or `SSLSession.getId()` alone is insufficient.**

### 16.3. Never log raw tickets, PSKs, or tokens

Sensitive data includes:
- Raw ticket bytes, resumption PSKs, and traffic secrets.
- HTTP-layer credentials, cookies, and tokens.
- Client certificate key material or server ticket-protection keys.
- Debug traces detailed enough to correlate sessions, users, and hosts.
- Application request bodies containing personal data.

Use aggregated metrics and non-sensitive trace IDs. During incidents, apply access control, retention limits, and redaction to diagnostic artifacts just like security data.

## 17. Common mistakes and fixes

| Misconception / mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| "Two consecutive GETs on one `HttpClient` are two session resumptions" | The pool may reuse the same live connection | Separate socket reuse from new handshakes |
| "No need to open a new socket when you have a session ticket" | Tickets shorten the handshake **after** a new connection is opened | A new connection still needs transport and key establishment |
| "`SSLSession.isValid()` means the TCP socket is open" | Session state is distinct from socket state | Track sockets/HTTP pools separately |
| "`SSLSession.invalidate()` closes all TLS connections immediately" | Invalidation blocks future resume/join per API, not connection close | Close sockets/engines per their own lifecycle |
| "`setSessionTimeout(600)` closes idle TCP sockets after 600s" | It is a cache lifetime policy | Configure HTTP/TCP idle timeouts separately |
| "`setSessionCacheSize(0)` disables the cache" | `0` means unlimited cache size per API | Use proper provider policy to disable caching |
| "Resumption always includes 0-RTT" | 0-RTT is a separate, optional feature | 1-RTT PSK resumption can run without early data |
| "0-RTT has TLS so `transfer-money` is safe" | Early data can be replayed; weaker secrecy | Block unsafe ops; enforce anti-replay/idempotency per profile |
| "With PSK resumption, everything has PFS" | PSK-only differs from PSK-DHE; 0-RTT lacks FS | Choose mode/policy explicitly; protect tickets/PSKs |
| "Because the client holds a ticket, the server must resume" | Server can reject due to policy/rotation/expiry | Accept fallback to full handshake |
| "Ticket lifetime = HTTP login lifetime" | Two separate authentication layers | Application AuthN/AuthZ has its own TTL |
| "Server restarts don't affect resumption" | In-memory state or rotated keys may be lost | Design ticket/cache/cluster handling properly |
| "A TLS ticket works for any hostname" | Identity binding, SNI, and security policy apply | Verify expected endpoint; scope tickets |
| "Any 0-RTT GET is safe" | Can have side effects, token state, or risky retries | Allow only when app profile proves replay safety |
| "A full handshake is a bug when caching is enabled" | Cache miss/expiry is normal behavior | Monitor rates and causes; never downgrade |
| "`KeyUpdate` opens a new TLS session" | `KeyUpdate` happens inside the live connection | Distinguish key rotation from resumption |
| "TLS resumption replaces certificate validation" | Trust must rest on full handshake and policy | Keep trust and hostname verification enabled |
| "Resumed mTLS = user still has admin privileges" | App roles and certificates may have been revoked | Revalidate authorization and policy |
| "Comparing session IDs proves resumption" | TLS 1.3 ticket abstractions and pooling complicate IDs | Use proper wire/JSSE handshake evidence |
| "TLS over QUIC also uses `SSLSocket`" | QUIC integrates TLS differently from TCP/TLS | Use HTTP/3 APIs/providers and QUIC standards |

## 18. Practical scenarios

### Scenario A: HTTP/2 loading 40 resources

A client opens one TLS connection to `cdn.example.com` and fetches 40 resources over HTTP/2 streams. An ops team reports 40 TLS resumptions because there were 40 requests.

**Analysis:** Incorrect. Likely only **one TLS handshake** and one connection occurred, carrying 40 HTTP/2 streams. Connection reuse/multiplexing differs from resumption. Measure at the network/TLS layer, not by request count.

### Scenario B: HTTP/1.1 keep-alive expires

Request #1 finishes; the pool closes the socket after an idle timeout. Request #2 opens a new TCP connection, the client still holds a TLS 1.3 ticket, and the server accepts the PSK.

**Analysis:** That is a **new transport connection + resumed TLS handshake**. Request #2 did not reuse the old socket. Even if the ticket were rejected, a full handshake could succeed and serve HTTP normally.

### Scenario C: Server just rotated its certificate

The client holds a resumption ticket from an earlier handshake, yet the server just rotated its certificate or updated trust/policy.

**Analysis:** Never blindly resume all old tickets. Account for ticket lifetime, binding policy, revocation/rotation, and key resumption rules. A fresh full handshake may be required. Never preserve stale security privileges indefinitely for speed.

### Scenario D: Money transfer inside 0-RTT

A client sends `POST /transfer` in early data; an attacker records the early-data flight and replays it against another region.

**Analysis:** 0-RTT carries replay risk even though traffic is encrypted. Never send side-effecting commands like money transfers in early data without a proven anti-replay profile; the default control is disallowing 0-RTT for such operations.

### Scenario E: Client calls `SSLSession.invalidate()` expecting the socket to close

The app invokes `invalidate()` yet observes data continuing to flow over the existing `SSLSocket`.

**Analysis:** No contradiction. Invalidation affects future reuse/resumption state, whereas an established TLS connection maintains its own lifecycle. Close the socket or engine explicitly per API to stop transmission.

### Scenario F: Server restart sharply drops resumption rate

After a deploy, resumed handshakes drop from 80% to 10% and full handshakes rise, while HTTP keeps working.

**Analysis:** Servers may have lost in-memory session state or rotated ticket keys, load balancers shifted routes, or client tickets expired. Do not immediately assume a certificate outage or attack; inspect ticket/PSK acceptance diagnostics and cluster config.

### Scenario G: A Java service behind a reverse proxy

External clients connect over HTTPS to an API gateway; the gateway makes internal HTTP calls to a Java backend. The Java backend checks its `SSLSessionContext` and sees zero client TLS sessions.

**Analysis:** TLS terminated at the gateway, so the backend owns no client TLS sessions. Inspect handshakes at the gateway; propagate identities securely rather than trusting raw client-supplied headers.

### Scenario H: TLS 1.3 resumption without 0-RTT

A client receives a ticket, presents the PSK next time, and the server accepts; application data is sent only after `Finished` in 1-RTT mode.

**Analysis:** This is still **valid session resumption**, just without early data. Distinguish standard resumption optimization from 0-RTT, which requires replay-safe application semantics.

### Scenario I: Application session expired

The TLS connection stays alive and `SSLSession.isValid()` returns `true`, yet the user's access token has expired.

**Analysis:** The server must reject the request or require reauthentication per policy. TLS state never extends bearer tokens or user privileges.

### Scenario J: Java HTTP client opened two parallel connections

Two requests target the same origin, yet the pool opens two sockets due to concurrency or HTTP version behavior. The second handshake may be full even with a ticket in cache.

**Analysis:** Socket count and resumption depend on ticket arrival timing, trust, policy, and provider behavior. Do not infer behavior from the number of `HttpClient` instances; run instrumented tests measuring TLS handshakes and connection reuse.

## 19. Design and operations checklist

### Application client

- [ ] Determine whether you need connection pooling, TLS resumption, or both; collect metrics for each.
- [ ] Use a supported `HttpClient`/HTTP framework with standard trust manager and endpoint identity validation.
- [ ] Never substitute `SSLSession` for an HTTP auth session or user principal.
- [ ] Cap connection counts and idle timeouts per resource, latency, and threat-model limits.
- [ ] If using a custom `SSLContext`, manage client session caches, trust material, and shutdown per policy.
- [ ] Never auto-send 0-RTT for side-effecting operations; check intentional profile/SDK support.
- [ ] Never assume session IDs or cache state prove resumption or peer identity.

### TLS termination server / gateway

- [ ] Select TLS versions, cipher suites, key-exchange modes, and certificate policies aligned with RFC 9846.
- [ ] Manage session/ticket lifetimes, resumption caches, server ticket-key rotation, and secrets securely.
- [ ] Plan for node restarts, load balancing, key sharing, and fallback to full handshakes.
- [ ] Cap ticket lifetimes and resumption chains per policy, accounting for cert/CA/client identity changes.
- [ ] If enabling 0-RTT, enforce cluster-wide anti-replay, accept only replay-safe traffic, and coordinate with the application.
- [ ] Protect logs, traces, metric dimensions, and key material; never write raw PSKs/tickets.
- [ ] Verify the actual scope of session invalidation/revocation; never claim one local Java call clears the whole cluster.

### Connection and resource lifecycle

- [ ] Close `SSLSocket` or `SSLEngine` per contract when finished, handling errors and network EOF cleanly.
- [ ] Read/close HTTP response bodies properly so connection pool resources are released.
- [ ] Never mistake session cache timeout for socket read, HTTP request, or idle timeout.
- [ ] Monitor pool saturation, keep-alive, idle closures, HTTP/2 streams, and remote `GOAWAY` frames.
- [ ] Keep application authorization independent of TLS resumption state.
- [ ] Run load tests, restart tests, ticket-key rotation tests, and browser/mobile/network-change tests.

### Security regression

- [ ] Full handshake to valid certificate and expected hostname succeeds; wrong trust/hostname fails.
- [ ] Resumed handshakes are genuinely verified via provider or wire evidence.
- [ ] Expired ticket/cache or changed trust/policy triggers a full handshake or rejection as expected.
- [ ] Raw tickets/keys never appear in logs or unprotected heap-dump artifacts.
- [ ] PSK-only / PSK-DHE policy is verified, with no ephemeral `KeyShare` reuse.
- [ ] 0-RTT is never automatically enabled on unsafe requests.
- [ ] Multi-instance anti-replay remains consistent if 0-RTT is used.
- [ ] Expired app auth is still rejected even while the TLS session remains valid.

## 20. Self-check questions

**1. Are two HTTP requests over the same TCP/TLS socket session resumption?**  
**No.** That is connection reuse / HTTP pooling. TLS resumption requires a **handshake on a new connection** using prior state.

**2. Does closing a TCP socket erase the TLS session ticket?**  
**Not necessarily.** The TLS provider may retain the session/ticket to resume on a new socket until expiry, eviction, or policy change.

**3. Does `SSLSession.isValid() == true` tell you the `SSLSocket` is open?**  
**No.** That reflects session validity, not transport socket state.

**4. Does `SSLSession.invalidate()` immediately close a running socket?**  
**No.** Invalidation prevents future resumption/joining via the API; an established connection may continue until closed.

**5. What does TLS 1.3 use to resume?**  
A **PSK**, typically tied to a `NewSessionTicket` from an earlier handshake; the client offers PSK identity + binder, and the server accepts or rejects.

**6. Does 1-RTT resumption necessarily use 0-RTT?**  
**No.** 0-RTT is a separate early-data mode that must be explicitly permitted and match the application profile.

**7. Why not send money-transfer commands over 0-RTT by default?**  
Because early data can be replayed across connections; TLS encryption alone does not prevent duplicate execution.

**8. Can you conclude the server accepted a ticket solely from low handshake latency?**  
**No.** You need TLS handshake traces or provider metrics showing PSK/resumption was selected.

**9. Does calling `setSessionTimeout(600)` force sockets to close after ten minutes?**  
**No.** It is a session cache setting, not an HTTP keep-alive or connection idle timeout.

**10. Does calling `setSessionCacheSize(0)` disable the cache?**  
**No.** Per the API contract, `0` means no size limit enforced by this setting; disabling resumption requires different policy/provider configuration.

**11. If a server rotates to a new ticket key and rejects an old ticket, must the client fail to connect?**  
Not necessarily. When policy permits, server and client can safely fall back to a full handshake.

**12. Does TLS resumption automatically renew an application login token?**  
**No.** HTTP cookies, JWTs, OAuth tokens, and application sessions have independent lifecycles.

**13. How do resumption and `KeyUpdate` differ?**  
Resumption performs a **new handshake on a new connection** using prior state; `KeyUpdate` rotates application traffic keys **inside the existing connection**.

**14. Does a Java service behind a TLS-terminating reverse proxy see browsers' TLS sessions?**  
Normally **no**. Those belong to the gateway/proxy; the backend sees only its own hop's connection protocol.

**15. Does TLS 1.3 resumption guarantee forward secrecy in every case?**  
**No**: PSK-only, PSK-DHE, and 0-RTT have different guarantees; consider PSK/ticket compromise and DHE usage.

**16. Which RFC serves as the primary TLS 1.3 standard as of October 2026?**  
**RFC 9846**, published July 2026, replacing RFC 8446 while preserving TLS version 1.3 and core compatibility.

## 21. Lesson summary diagram

```text
                APPLICATION HTTP REQUEST
                         |
               live HTTP connection?
                    /          \
                  YES           NO
                   |             |
               reuse socket    new transport connection
                   |             |
               same TLS        TLS handshake begins
               connection         |
                   |         Resumption PSK/ticket available?
                   |               /         \
                   |              YES         NO
                   |               |           |
                   |          Server accepts? full handshake
                   |            /       \
                   |           YES       NO
                   |            |         |
                   |          resumed   full handshake
                   |            |
                   |      1-RTT normally
                   |      0-RTT only if explicitly enabled/replay-safe
                   |            |
                   +------------+----------+
                                |
                         HTTP application data
                                |
                         Close live connection
                                |
                        Ticket may survive
                                |
                         Later new connection

  Important:
    TLS session != TCP socket
    TLS session != login session
    Connection reuse != TLS resumption
    Resumption != 0-RTT
    Session invalidation != socket.close()
```

**Conclusion:** Keep three lifecycles separate: **application requests**, **live transport/TLS connections**, and **session/resumption state that can span multiple connections**. Connection pooling and HTTP/2 save handshakes by **not reopening connections**; TLS session resumption saves handshakes by **reusing authenticated state on a new connection**. Under RFC 9846, TLS 1.3 uses PSKs/tickets for resumption; 0-RTT is an option carrying replay risk, not the default for resumption. In Java, `SSLSessionContext` configures cache limits without proving resumption occurred, and `SSLSession.invalidate()` does not close sockets. A production system needs clear policies for lifetimes, hostname/authentication, cache/ticket keys, 0-RTT, authorization, logging, and layered connection shutdown.

### References

- RFC 9846 (2026) — *The Transport Layer Security (TLS) Protocol Version 1.3*, replacing RFC 8446: https://www.rfc-editor.org/rfc/rfc9846
- RFC 8446 (2018) — Original TLS 1.3, now replaced by RFC 9846: https://www.rfc-editor.org/rfc/rfc8446
- RFC 9000 — *QUIC: A UDP-Based Multiplexed and Secure Transport*: https://www.rfc-editor.org/rfc/rfc9000
- RFC 9001 — *Using TLS to Secure QUIC*, resumption and early data: https://www.rfc-editor.org/rfc/rfc9001
- Java SE 17, `SSLContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html
- Java SE 17, `SSLSessionContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSessionContext.html
- Java SE 17, `SSLSession`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html
- Java SE 17, `SSLSocket`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html
- Java SE 17, `SSLEngine`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html
- Java SE 17, `HttpClient`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17, `HttpResponse.sslSession()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Oracle JSSE Reference Guide — provider, session caching and diagnostic configuration: https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html
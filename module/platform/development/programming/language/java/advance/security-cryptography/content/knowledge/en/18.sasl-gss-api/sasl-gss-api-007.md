# 18.7 — Establishing a GSS Context, wrap/unwrap, MIC, and Checking Replay or Sequence

## 1. Objectives and Mental Model

After this lesson, you will be able to: (1) distinguish authentication during `GSSContext` establishment from per-message protection afterward; (2) implement the `initSecContext`/`acceptSecContext` flow over a token-framed transport; (3) choose `wrap`/`unwrap` versus `getMIC`/`verifyMIC` based on confidentiality needs; (4) request, verify, and properly handle replay/sequence detection; and (5) avoid treating GSS flags as automatic application policy.

**GSS-API (Generic Security Service API)** is a common interface for security mechanisms such as Kerberos. In Java, the standard API resides in module `java.security.jgss`, package `org.ietf.jgss`. GSS has two sides: the **initiator** (starting side, typically client) and the **acceptor** (accepting side, typically server). Both sides exchange **binary tokens** to establish a security context, then use that context to protect data. GSS **does not itself provide** TCP connections, frame formats, message routing, retries, or business authorization. SASL can use the GSSAPI mechanism, whereas this lesson works directly with Java GSS-API.

Key objects:

| Component | Role |
|---|---|
| `GSSManager` | Factory creating `GSSName`, `GSSCredential`, and `GSSContext`; lists mechanisms. |
| `GSSName` | Identity of the sender, receiver, or targeted service. |
| `GSSCredential` | Handle to provisioned credentials; the API does not log in by itself to create identities. |
| `GSSContext` | Authentication state, keys, and sequence state for **one session**; used to generate/verify tokens. |
| `MessageProp` | Requests QOP/privacy when sending; receives QOP/privacy and replay/order status when receiving. |
| `GSSException` | Token, credential, mechanism policy, timeout/expiry, or MIC verification errors. |

## 2. How is a GSS context established?

```text
Initiator                                          Acceptor
  |  createContext(target, mechanism, credential)    | createContext(acceptorCredential)
  |  requestMutualAuth/Conf/Integ/Replay/Sequence     |
  |                                                  |
  | -- initSecContext(empty) -> token #1 ----------> |
  |                                   acceptSecContext(token #1)
  | <--------- token #2 (if produced) -------------- |
  | initSecContext(token #2)                          |
  | -- token #3 (if produced) ---------------------> |
  |                      ...                         |
  | isEstablished() on both sides                    |
  | check get*State(), peer identity, authorization   |
  | ====== application begins data exchange ======== |
  | -- wrap(plaintext) -> wrapped token ------------> | unwrap(token)
  | -- plaintext + getMIC(plaintext) ---------------> | verifyMIC(token, plaintext)
```

A single call to `initSecContext` or `acceptSecContext` **does not necessarily complete the handshake**. Each call accepts the prior token and may return a new token; the application must transmit **every byte of the token**, even when the token-producing side already reports `isEstablished() == true`. `null` means that call produced no token to send. `isEstablished()` is **local state**: the application's transport protocol must coordinate so both sides are ready before sending business data.

1. Prepare a valid mechanism and credentials. For Kerberos v5, the standard OID is `1.2.840.113554.1.2.2`; the client typically needs a TGT, and the server needs an acceptor credential for the corresponding service principal.
2. The initiator creates a `GSSContext` for the **right service** and configures requests **before the first `initSecContext` call**: `requestMutualAuth(true)`, `requestInteg(true)`, `requestConf(true)`, `requestReplayDet(true)`, `requestSequenceDet(true)`. Do not request credential delegation unless the application genuinely requires it.
3. The acceptor creates a context from a credential with `ACCEPT_ONLY` usage. It does not call the initiator-only `request*` methods; token negotiation determines the final services.
4. Exchange tokens over the transport, looping until both contexts are established. GSS tokens **must never** be converted to strings via a default charset, truncated at byte 0, or confused with UTF-8 text.
5. Once complete, inspect the actual state: `getMech()`, `getSrcName()`, `getTargName()`, `getMutualAuthState()`, `getIntegState()`, `getConfState()`, `getReplayDetState()`, `getSequenceDetState()`, and `getLifetime()`. Calling `request*` **does not guarantee** the mechanism enabled that feature.
6. The server authenticates **and** authorizes `getSrcName()` for the specific resource. The client verifies the target service and authentication properties. If mandatory policy is unmet, tear down the context without proceeding to business messages.

With `GSSName.NT_HOSTBASED_SERVICE`, Java recognizes the `service@hostname` form, such as `HTTP@app.example.com`; the Kerberos library may map it to principal `HTTP/app.example.com@REALM`. Do not confuse the `@` separator in host-based GSS names with `@REALM` in Kerberos principals. DNS, realm, SPN, and credentials must align.

**Call ordering note:** `requestReplayDet`, `requestSequenceDet`, `requestConf`, `requestInteg`, and `requestMutualAuth` may only be requested by the initiator **before** the first `initSecContext` call. `setChannelBinding(...)` (if used) must be configured **on both sides with the same agreed binding data** prior to starting the context. Most applications should permit message operations only after `isEstablished()`; `isProtReady()` exists for mechanisms allowing early protection but demands strict protocol rules.

## 3. Two ways to protect individual messages

| API path | Message on the wire | Primary guarantee |
|---|---|---|
| `wrap(plaintext, ..., new MessageProp(0, true))` → `unwrap(token, ..., prop)` | One **wrapped token** holding data and verification metadata | Integrity; plus confidentiality **if privacy was actually applied**. |
| `wrap(..., new MessageProp(0, false))` → `unwrap(...)` | Wrapped token holding data, without requesting encryption | Integrity; data is not kept confidential. |
| `getMIC(plaintext, ..., prop)` → `verifyMIC(micToken, ..., samePlaintext, ..., prop)` | **Separate plaintext and MIC token** | Verifies integrity/authenticity; **does not encrypt plaintext**. |

`MessageProp(0, true)` means QOP = 0 (default level) and **requesting privacy**, not proof that encryption occurred. After `wrap`, inspect `prop.getPrivacy()`; after `unwrap`, inspect `prop.getPrivacy()` on the received token. If the application requires secrecy and `getConfState()` or `getPrivacy()` is false, reject it. `getIntegState()` must be enabled for both wrap and MIC. A MIC is computed over **the exact byte sequence**: changing encoding, line endings, or a single byte causes `verifyMIC` to fail. Do not use `getMIC` as a general-purpose signature API independent of a GSS context.

`getWrapSizeLimit(qop, confReq, maxTokenSize)` estimates the maximum input bytes that produce a wrapped token within a transport limit. It **does not** replace frame limits, incoming token size validation, or application-level chunking.

## 4. Java 17+ example: creating contexts, exchanging tokens, handling messages

The file below **compiles and runs on JDK 17+**. Its `main` method only executes a replay/order policy test using simulated `MessageProp` instances, so it **requires no KDC**. The methods `newInitiator`, `newAcceptor`, `establish...`, `protect`, `open`, `makeMic`, and `verifyMic` are real integration code for client/server use **once Kerberos credentials and a transport exist**. No real Kerberos tokens are fabricated in the test harness.

```java
// File: GssLesson.java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import org.ietf.jgss.*;

public final class GssLesson {
    private GssLesson() {}

    // Only exchanges GSS tokens; the application layer must manage handshake/data phases.
    public interface TokenPipe {
        void send(byte[] token) throws IOException;
        byte[] receive() throws IOException;
    }

    // Example binary framing: 4-byte int length + token; both sides share the convention.
    public static final class FramedPipe implements TokenPipe {
        private static final int MAX_TOKEN = 1_048_576;
        private final DataInputStream in;
        private final DataOutputStream out;

        public FramedPipe(InputStream input, OutputStream output) {
            in = new DataInputStream(input);
            out = new DataOutputStream(output);
        }

        @Override
        public void send(byte[] token) throws IOException {
            if (token == null || token.length > MAX_TOKEN) {
                throw new IOException("Invalid outgoing token length");
            }
            out.writeInt(token.length);
            out.write(token);
            out.flush();
        }

        @Override
        public byte[] receive() throws IOException {
            int size = in.readInt();
            if (size < 0 || size > MAX_TOKEN) {
                throw new IOException("Invalid incoming token length");
            }
            byte[] token = new byte[size];
            in.readFully(token);
            return token;
        }
    }

    private static Oid kerberosV5() throws GSSException {
        return new Oid("1.2.840.113554.1.2.2");
    }

    // Client: already holds a default initiator credential, e.g., TGT in current Subject.
    public static GSSContext newInitiator(String hostBasedService)
            throws GSSException {
        GSSManager manager = GSSManager.getInstance();
        GSSName server = manager.createName(
                hostBasedService, GSSName.NT_HOSTBASED_SERVICE);
        GSSContext context = manager.createContext(
                server, kerberosV5(), null, GSSContext.DEFAULT_LIFETIME);
        context.requestMutualAuth(true);
        context.requestInteg(true);
        context.requestConf(true);
        context.requestReplayDet(true);
        context.requestSequenceDet(true);
        context.requestCredDeleg(false);
        return context;
    }

    // Server: caller owns acceptorCredential and must dispose it when finished.
    public static GSSContext newAcceptor(GSSCredential acceptorCredential)
            throws GSSException {
        return GSSManager.getInstance().createContext(acceptorCredential);
    }

    public static void establishInitiator(GSSContext context, TokenPipe link)
            throws GSSException, IOException {
        byte[] incoming = new byte[0]; // Empty token only for the initial call.
        while (!context.isEstablished()) {
            byte[] outgoing = context.initSecContext(
                    incoming, 0, incoming.length);
            if (outgoing != null) {
                link.send(outgoing); // Send even if context just became established.
            }
            if (!context.isEstablished()) {
                incoming = link.receive();
                if (incoming == null) throw new EOFException("Missing GSS reply");
            }
        }
    }

    public static void establishAcceptor(GSSContext context, TokenPipe link)
            throws GSSException, IOException {
        while (!context.isEstablished()) {
            byte[] incoming = link.receive();
            if (incoming == null) throw new EOFException("Missing GSS request");
            byte[] outgoing = context.acceptSecContext(
                    incoming, 0, incoming.length);
            if (outgoing != null) {
                link.send(outgoing); // Never drop the final token.
            }
        }
    }

    // Verify mandatory policy rather than trusting client request* calls alone.
    public static void requireServices(GSSContext context,
            boolean requirePrivacy, boolean strictSequence) {
        if (!context.isEstablished()
                || !context.getMutualAuthState()
                || !context.getIntegState()
                || !context.getReplayDetState()
                || (strictSequence && !context.getSequenceDetState())
                || (requirePrivacy && !context.getConfState())) {
            throw new SecurityException("Required GSS service unavailable");
        }
    }

    public static void checkArrival(MessageProp p,
            boolean requirePrivacy, boolean strictSequence) {
        if (p.isDuplicateToken()) {
            throw new SecurityException("Replay: duplicate token");
        }
        if (p.isOldToken()) {
            throw new SecurityException("Replay: old token");
        }
        if (strictSequence && p.isUnseqToken()) {
            throw new SecurityException("Sequence: unsequenced token");
        }
        if (strictSequence && p.isGapToken()) {
            throw new SecurityException("Sequence: gap token");
        }
        if (requirePrivacy && !p.getPrivacy()) {
            throw new SecurityException("Message was not encrypted");
        }
    }

    public static byte[] protect(GSSContext sender, String text,
            boolean requirePrivacy) throws GSSException {
        requireServices(sender, requirePrivacy, false);
        byte[] input = text.getBytes(StandardCharsets.UTF_8);
        MessageProp prop = new MessageProp(0, requirePrivacy);
        byte[] token = sender.wrap(input, 0, input.length, prop);
        if (requirePrivacy && !prop.getPrivacy()) {
            throw new SecurityException("wrap did not apply privacy");
        }
        return token;
    }

    public static String open(GSSContext receiver, byte[] wrappedToken,
            boolean requirePrivacy, boolean strictSequence)
            throws GSSException {
        requireServices(receiver, requirePrivacy, strictSequence);
        MessageProp prop = new MessageProp(0, false);
        byte[] plain = receiver.unwrap(
                wrappedToken, 0, wrappedToken.length, prop);
        checkArrival(prop, requirePrivacy, strictSequence);
        return new String(plain, StandardCharsets.UTF_8);
    }

    public static byte[] makeMic(GSSContext sender, byte[] message)
            throws GSSException {
        requireServices(sender, false, false);
        return sender.getMIC(
                message, 0, message.length, new MessageProp(0, false));
    }

    public static void verifyMic(GSSContext receiver, byte[] micToken,
            byte[] originalMessage, boolean strictSequence)
            throws GSSException {
        requireServices(receiver, false, strictSequence);
        MessageProp prop = new MessageProp(0, false);
        receiver.verifyMIC(
                micToken, 0, micToken.length,
                originalMessage, 0, originalMessage.length, prop);
        checkArrival(prop, false, strictSequence);
    }

    // Tests policy logic only; does NOT generate or verify Kerberos tokens.
    private static String policyResult(MessageProp p, boolean strict) {
        try {
            checkArrival(p, false, strict);
            return "ACCEPT";
        } catch (SecurityException rejected) {
            return "REJECT";
        }
    }

    public static void main(String[] args) {
        MessageProp normal = new MessageProp(0, false);
        MessageProp duplicate = new MessageProp(0, false);
        MessageProp gap = new MessageProp(0, false);
        // Simulate flags the provider populates after unwrap/verifyMIC.
        duplicate.setSupplementaryStates(true, false, false, false, 0, null);
        gap.setSupplementaryStates(false, false, false, true, 0, null);
        System.out.println("normal=" + policyResult(normal, true));
        System.out.println("duplicate=" + policyResult(duplicate, true));
        System.out.println("gap_strict=" + policyResult(gap, true));
        System.out.println("gap_relaxed=" + policyResult(gap, false));
    }
}
```

Run from the directory containing `GssLesson.java`:

```bash
javac -encoding UTF-8 GssLesson.java
java GssLesson
```

Exact output of the **simulated policy test**:

```text
normal=ACCEPT
duplicate=REJECT
gap_strict=REJECT
gap_relaxed=ACCEPT
```

Explanation: `setSupplementaryStates` in `main` is used **only in the test** to fabricate sample flags; in real GSS processing, the provider populates flags during `unwrap`/`verifyMIC`, and the application **never sets flags manually**. `gap_relaxed=ACCEPT` demonstrates that a policy without strict ordering can accept a token arriving before its predecessor, **not** that arbitrary business logic may lose or reorder messages.

### 4.1. Wiring the class into real Kerberos

In an environment with a KDC, `krb5.conf`, principal/keytab, and an appropriate JAAS/`Subject` or login session:

- The client creates `GSSContext client = GssLesson.newInitiator("HTTP@app.example.com")` after obtaining an initiator credential/TGT (e.g., via `kinit` or a Java login flow).
- The server creates `GSSCredential serviceCred = manager.createCredential(serviceName, GSSCredential.DEFAULT_LIFETIME, kerberosOid, GSSCredential.ACCEPT_ONLY)` using a principal with a valid keytab/ticket, then `GSSContext server = GssLesson.newAcceptor(serviceCred)`.
- Each side wraps the connection in a `TokenPipe`. The client calls `establishInitiator(...)`, and the server calls `establishAcceptor(...)`. The server sends any response token to the client **before** the application switches phases. The example framing carries only length + bytes; if a channel carries multiple message kinds, add a frame type/state machine and an explicit handshake completion boundary so the final token is never confused with data.
- Once both sides are ready, each calls `requireServices(...)` and verifies `getSrcName()`/`getTargName()` match expected identities; the server checks authorization before handling requests.
- The sender calls `protect(context, "business command", true)` to build a token and sends it over the pipe; the receiver calls `open(context, token, true, true)` and **executes business side effects only after all checks pass**.
- When only integrity is needed, the sender transmits **two pieces**: the `message` bytes and `makeMic(context, message)`. The receiver calls `verifyMic(context, mic, receivedMessage, true)` before using `receivedMessage`. Message bytes must be preserved 100% intact.

Call `dispose()` on every application-owned context and credential inside `finally` or an equivalent lifecycle mechanism. Never share one `GSSContext` across concurrent threads without synchronization, as context methods are not guaranteed to be thread-safe. Each session/peer gets its own context; expired contexts must be re-established per policy rather than reusing tokens from old contexts.

**Why doesn't the example simulate a successful handshake inside `main`?** Kerberos requires real credentials and a KDC. Printing "authenticated" from fake data creates dangerous misconceptions about security. You can verify compilation and policy logic independently; running a real handshake requires an actual Kerberos environment.

## 5. Replay detection and sequence detection: how do they differ?

Replay is **re-sending** an old token; sequence is **delivery ordering**. A context can detect both via mechanism metadata/sequence numbers, though behavior depends on negotiated features, check window size, and how the application uses a context.

| Flag received after `unwrap`/`verifyMIC` | Practical meaning | Common policy |
|---|---|---|
| `isDuplicateToken()` | Token was already processed within the detection window. | Reject; do not re-execute side effects. |
| `isOldToken()` | Token is too old to verify reliably against replay. | Reject when replay protection is required. |
| `isUnseqToken()` | A token with a **later** sequence number was already processed before this one. | Reject if the protocol requires strict ordering. |
| `isGapToken()` | One or more expected preceding tokens have not been seen yet. | Pause/wait/error per protocol; reject under strict ordering. |

These flags are **supplementary status** on the received token, not a guarantee that "the application is safe." Even when `verifyMIC` does not throw and `unwrap` returns plaintext, you must still inspect the flags before accepting. For corrupted tokens, bad MICs, expired contexts, or invalid credentials, the API may throw `GSSException`; you must fail closed (never decrypt or accept a failed message and continue business execution). Do not assume every `GSSException` means replay; log major codes (`getMajor()`, `getMajorString()`) in a controlled way without logging raw secrets or tokens.

**Sound evaluation order at the receiver:**

1. Confirm the context is established with integrity and replay detection; if strict ordering is required, require `getSequenceDetState() == true`. If encryption is needed, also require confidentiality.
2. Read **one complete token**; enforce frame length limits before allocating memory.
3. Call `unwrap` or `verifyMIC`, catching `GSSException`; never use plaintext when verification fails.
4. Check `duplicate` and `old`; if strict ordering is active, also check `unseq` and `gap`. If privacy is required, check `prop.getPrivacy()`.
5. Only when every check passes should you parse, authorize, and execute business logic; combine with transaction/idempotency keys for side-effecting requests.

Suppose the sender emits tokens in order `T1, T2, T3`:

| Receiver observes | Possible flags | Application implication |
|---|---|---|
| `T1, T2, T3` | No supplementary flags | Delivered in order (when supported by mechanism). |
| `T1, T1` | `duplicate` on the second delivery | Second request must not run again. |
| `T1, T3` | Possible `gap` on `T3` | `T2` has not been processed; decide whether to wait or reject. |
| `T1, T3, T2` | Possible `gap` on `T3`, `unseq` on `T2` | Under strict order, T2 cannot silently apply after T3. |
| Token outside detection window | Possible `old` | Cannot prove freshness; should be rejected. |

"Possible" above is intentional: exact flagging timing, window size, exception behavior, and token handling depend on the mechanism and provider. Real security testing must replay and reorder **actual provider-generated tokens across two live contexts**, not merely mutate `MessageProp` by hand. Furthermore, these flags cover **only one context**; requests replayed across a new session require application-level idempotency and replay policies.

### 5.1. Essential integration test cases

| Test case | Condition | Expected result |
|---|---|---|
| Valid handshake | Matching client/service credentials, mutual auth succeeds | Both established; identities and `get*State()` satisfy policy. |
| Wrong service principal | Client targets wrong service or server lacks matching key | Peer rejected; no data processed. |
| Tampered wrapped token | Flip one byte in the token | `unwrap` fails MIC/token check or rejects; no side effect. |
| MIC against different message | `getMIC` on A, `verifyMIC` on B | Verification error; B is discarded. |
| Secrecy not granted | `getConfState()==false` or token `getPrivacy()==false` | Rejected when policy requires confidentiality. |
| Replaying the same token | `unwrap`/`verifyMIC` called twice on same context | Duplicate/old flag or mechanism error; second call rejected. |
| Out-of-order / gap | Send T2 before T1 on sequence-detecting mechanism | Handled per strict policy; out-of-order token causes no side effect. |
| Expired context | Call per-message API after expiration | Rejected; establish a fresh session per procedure. |
| Abnormally long frame | Length exceeds cap | Rejected before allocating or passing to GSS. |

## 6. Common design mistakes and how to avoid them

**Confusing "requested" with "granted."** `requestReplayDet(true)` only asks for the service. Accepting a message must depend on `getReplayDetState()`, `getSequenceDetState()`, and post-processing token flags.

**Assuming `wrap` always encrypts.** A wrapped token may carry integrity only. To get confidentiality, request it during context setup, pass `MessageProp(0, true)`, and verify `getConfState()` and `getPrivacy()` on both sender and receiver.

**Assuming MIC is encryption or a session-independent signature.** MIC does not hide plaintext; its value is tied to the context and exact message bytes. If a protocol alters JSON formatting, Unicode normalization, or newlines between sender and receiver, MIC verification can fail. Fix a canonical representation or preserve exact bytes.

**Ignoring supplementary flags because `unwrap` returned plaintext.** Plaintext with a valid MIC can still be replayed or out of order. Place flag checks immediately after the GSS call and before parsing or execution.

**Dumping all tokens into one stream without framing or protocol phases.** GSS does not mark TCP stream boundaries or distinguish application frames. Use bounded length prefixes, message type tags, process handshake tokens before data payloads, and avoid deadlocks where both sides wait to read.

**Treating GSS protection as a substitute for authorization and idempotency.** GSS verifies identity per mechanism and protects tokens; the application must still enforce roles/permissions, request IDs, and deduplication for operations like transfers or state writes. A mechanism's replay window does not replace a ledger of processed requests.

**Using the wrong identity or credential.** Host-based `service@host` differs from principal `service/host@REALM`. Default credentials may not exist or may lack `ACCEPT_ONLY` authority. Use keytabs, JAAS, and `Subject` with the proper role, never embed passwords in source code, and never log sensitive tokens.

**Forgetting resource cleanup and error handling.** When a `GSSException` occurs during the handshake, never treat the session as established; close the context and transport. When a request is rejected for replay/ordering, do not blindly retry it just because the transport layer supports retries. A `GSSContext` is not safe for arbitrary concurrent use; synchronize or isolate one context per connection.

## 7. Practical checklist and standard references

Before enabling GSS on a service, verify all items: client/service identities; valid Kerberos credentials; bounded token framing; clear two-way handshake termination; verification of requested vs. negotiated flags; `wrap`/`MIC` matching confidentiality needs; receiver blocking duplicate/old/out-of-order tokens before side effects; separate authorization/idempotency; cleanup and negative tests.

Reference documents:

- Java 17 `GSSContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSContext.html
- Java 17 `GSSManager` and `GSSCredential`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSManager.html and https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSCredential.html
- Java 17 `MessageProp`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/MessageProp.html
- RFC 2743, GSS-API v2: https://www.rfc-editor.org/rfc/rfc2743.html
- RFC 8353, Java bindings update: https://www.rfc-editor.org/rfc/rfc8353.html

Takeaway: **`GSSContext` establishes the session and identities; `wrap/unwrap` protects data (with or without encryption); MIC verifies integrity; replay/order flags give the application the evidence needed to accept or reject messages.**
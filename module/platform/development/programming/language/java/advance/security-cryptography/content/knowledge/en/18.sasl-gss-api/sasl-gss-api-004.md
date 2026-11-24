# 18.4. SASL Quality of Protection: `auth`, `auth-int`, `auth-conf`, and Mechanism Limits

## 1. The Nature of Quality of Protection (QOP)

**SASL (Simple Authentication and Security Layer)** is a framework enabling application protocols such as LDAP, IMAP, or SMTP to integrate pluggable **authentication mechanisms**. Beyond verifying identity, *some* mechanisms also support a **SASL security layer** that protects application data after session authentication succeeds.

**Quality of Protection (QOP)** describes the protection level **actually negotiated for a SASL session**. The three standard levels are:

| QOP | Authentication | Data integrity via SASL layer | Data confidentiality via SASL layer | Meaning |
| --- | --- | --- | --- | --- |
| `auth` | Yes | No | No | Authentication only in SASL; application data is not protected by SASL |
| `auth-int` | Yes | Yes | No | Integrity protection; detects unauthorized modification within the layer's scope |
| `auth-conf` | Yes | Yes | Yes | Integrity and confidentiality protection within the layer's scope |

**Integrity is not encryption.** With `auth-int`, messages can still be read even though modifications will be detected. With `auth-conf`, payloads are protected by the mechanism for both integrity and confidentiality. Replay prevention, message ordering guarantees, specific cryptographic algorithms, and keys belong to the mechanism and security context and cannot be inferred from a QOP string alone without checking the context.

QOP describes the **SASL** layer and does not replace evaluating *overall* connection security. For instance, PLAIN authenticating inside TLS still has SASL QOP `auth` because TLS is what encrypts the transport. Conversely, `auth-conf` protects only the bytes that actually pass through the SASL security layer; it does not hide IP addresses, connection duration, out-of-layer metadata, or exchanges occurring before the layer is activated.

## 2. Negotiating QOP: configuration is a request, not a guarantee

In Java, the constant `Sasl.QOP` is the key `javax.security.sasl.qop`. Its configured value is an **ordered preference list** separated by commas, such as `"auth-conf,auth-int"`. The Java SASL API specifies that if this property is omitted, the default is `auth`.

A QOP level is selected only when **all** of the following hold:

1. The application protocol supports SASL and explicitly defines how the security layer is inserted into the data stream.
2. The selected mechanism **is capable** of providing that level; the SASL framework does not automatically add encryption to every mechanism.
3. Client, server, providers, credentials, and policies all permit the same QOP level.
4. The authentication exchange completes successfully; the application reads the **actual negotiated QOP** and verifies it against required protection before sending business data.

```text
Client: requests auth-conf,auth-int
                 |
                 v
       Select SASL mechanism
                 |
    Challenge / response exchange
                 |
        +--------+--------+
        |                 |
   No common level    Auth succeeds
        |                 |
       Fail         Read chosen QOP
                          |
                   Check policy
                          |
              Accept or reject session
```

If both sides share no compatible QOP, never treat successful authentication alone as satisfying security policy. If the protocol allows `auth-int` to be selected while the application requires confidentiality at the SASL layer, **reject the session before exchanging application data**. Never silently relax policy down to `auth`. If policy permits encrypting via TLS instead of the SASL security layer, verify TLS **separately** (especially server authentication and downgrade prevention).

### Conditions for each level

- **`auth`:** appropriate when another layer already supplies the needed protection or only authentication is required; SASL itself does not protect subsequent message contents.
- **`auth-int`:** appropriate when payload tampering must be prevented within the layer without requiring data secrecy **at that layer itself**. Having `wrap` does not prove payloads are encrypted.
- **`auth-conf`:** used when policy requires both confidentiality and integrity in the SASL layer. You must validate the final QOP, route all covered messages through `wrap/unwrap`, and respect size limits.

## 3. Limits imposed by mechanism, provider, and protocol

**Not every SASL mechanism supports all three levels.** Protocol names like LDAP or SMTP do not determine QOP, because a single protocol can integrate multiple different mechanisms.

| Mechanism / family | Has a SASL security layer? | Practical notes |
| --- | --- | --- |
| **PLAIN** | **No** | RFC 4616 confirms PLAIN has no security layer. Use only with an appropriate protected channel, typically TLS; PLAIN cannot be turned into `auth-conf` via `Sasl.QOP`. |
| **SCRAM** (SCRAM-SHA-256, SCRAM-*-PLUS) | **No** per RFC 5802/7677 | SCRAM performs authentication; `-PLUS` variants support channel binding to an outer channel. Channel binding is not SASL encryption; use TLS/SSH or an equivalent protection layer for payloads. |
| **EXTERNAL** | Does not generate a security layer itself | Takes identity from a pre-authenticated outer channel, such as a TLS client certificate; data protection is handled by the outer channel. |
| **GSSAPI/Kerberos V5** | **Can** offer `auth`, `auth-int`, and `auth-conf` | RFC 4752 describes negotiating security layer support. Integrity/confidentiality may be offered/selected only if the GSS context and both peers actually support it. |
| **DIGEST-MD5** (legacy) | RFC 2831 once described all three levels | **Do not use in new deployments:** RFC 6331 marked the mechanism OBSOLETE and moved RFC 2831 to Historic. |

With **SASL GSSAPI**, deployments typically rely on Kerberos V5: the client needs suitable credentials/tickets; the server needs the proper service principal; service name, hostname, policy, delegation rules, and provider must all align. The JDK includes the `JdkSASL` provider supporting GSSAPI and QOP properties, but that **does not guarantee** the application will end up with `auth-conf`. RFC 4752 forbids advertising a confidentiality security layer when the GSS context lacks the corresponding capability flag. External protocol libraries may also restrict which QOP values they allow.

SASL and **GSS-API** are two conceptual layers: GSS-API provides the security context and data protection operations (GSS-Wrap/GSS-Unwrap); SASL defines how a mechanism integrates those operations into a protocol. Never take an arbitrary GSS-API example and conclude that every SASL mechanism can offer the same properties.

**Capability-check takeaway:** read both the mechanism **and** provider documentation; check policies on both ends; verify QOP after the handshake; test in the real application protocol. Never assume `auth-conf` simply because JDK `javax.security.sasl` is present or the server supports TLS.

## 4. Post-authentication security layer and the meaning of `wrap/unwrap`

RFC 4422 specifies that the SASL security layer is activated **only after** a successful authentication outcome, at the exact point defined by the application protocol. When the protection layer is active, data is processed into protected buffers.

- With **`auth`**, there is no SASL integrity/confidentiality layer processing subsequent payloads.
- With **`auth-int`** or **`auth-conf`**, client and server call `wrap(plain, offset, len)` to produce a protected buffer; the receiver calls `unwrap(protected, offset, len)` to recover the original content or detect verification failure.
- Per RFC 4422, each protected buffer on the wire is framed with a **4-byte length in network byte order (big-endian)** preceding the protected data. Higher-level protocols or libraries may already manage framing: never add it a second time.
- If the layer fails to protect or unwrap a buffer, **close the connection**; never accept unverified payloads or fall back to plaintext transmission.

```text
Business payload
      |
      +-- QOP auth -----------> Sent per protocol, bypassing SASL layer
      |
      +-- QOP auth-int/conf --> wrap(...) --> [4-byte length][protected bytes]
                                                        |
                                                     network
                                                        |
                                         validate frame + unwrap(...)
                                                        |
                                                  Business payload
```

Understand **maximum buffer size** and overhead. `Sasl.MAX_BUFFER` specifies the maximum receive buffer size for the SASL layer; `Sasl.RAW_SEND_SIZE` is the maximum plaintext payload size sendable in one `wrap` call, supplied via negotiation/provider results. Protected output can be larger than input due to MACs, tags, headers, and padding. The `Sasl.STRENGTH` property lets you prefer stronger algorithms on mechanisms that support it, but **cannot create** `auth-conf` if the mechanism has no encryption layer. Never treat `MAX_BUFFER` or `STRENGTH` alone as proof that policy is satisfied.

When combining TLS **and** a SASL layer, the outer TLS layer may protect the transport as well; SASL protects only data actually passed through `wrap`. When protection begins, packing order, accepted byte counts, and state transitions must match the application protocol; if a library already abstracts this, use the library's official API.

## 5. Java 17+: safely validating QOP requirements

### 5.1. Runnable example: policy logic

The first example tests an **ACCEPT/REJECT** decision against a hypothetical negotiated QOP. It **performs no handshake or encryption**; the goal is to test application rules before integrating a real mechanism.

Create the file `SaslQopPolicyDemo.java`:

```java
import java.util.Map;
import javax.security.sasl.Sasl;

public final class SaslQopPolicyDemo {
    private static boolean acceptable(
            String negotiated, boolean needIntegrity, boolean needPrivacy) {
        boolean valid = "auth".equals(negotiated)
                || "auth-int".equals(negotiated)
                || "auth-conf".equals(negotiated);
        if (!valid) {
            return false;
        }

        boolean hasIntegrity = "auth-int".equals(negotiated)
                || "auth-conf".equals(negotiated);
        boolean hasPrivacy = "auth-conf".equals(negotiated);
        return (!needIntegrity || hasIntegrity)
                && (!needPrivacy || hasPrivacy);
    }

    private static void check(
            String negotiated, boolean needIntegrity, boolean needPrivacy) {
        String result = acceptable(negotiated, needIntegrity, needPrivacy)
                ? "ACCEPT" : "REJECT";
        System.out.println(negotiated + " / I=" + needIntegrity
                + " / C=" + needPrivacy + " => " + result);
    }

    public static void main(String[] args) {
        Map<String, Object> props = Map.of(
                Sasl.QOP, "auth-conf,auth-int");
        System.out.println("QOP preferences: " + props.get(Sasl.QOP));
        check("auth-conf", true, true);
        check("auth-int", true, false);
        check("auth-int", true, true);
        check("auth", true, false);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SaslQopPolicyDemo.java
java SaslQopPolicyDemo
```

Exact stdout:

```text
QOP preferences: auth-conf,auth-int
auth-conf / I=true / C=true => ACCEPT
auth-int / I=true / C=false => ACCEPT
auth-int / I=true / C=true => REJECT
auth / I=true / C=false => REJECT
```

In this program, `props` holds **requested preferences**; the `negotiated` parameter is **the input to the verification check**. The `auth-int` case fails a secrecy requirement, and `auth` fails an integrity requirement. Unknown QOP values (including `null`) are also rejected. In a real system, `REJECT` must close the session and never transmit sensitive business data.

### 5.2. Real integration point with `SaslClient`

The Java SASL API lives in the `java.security.sasl` module: `Sasl.createSaslClient` selects the provider/mechanism, `SaslClient.evaluateChallenge` processes server tokens, `SaslClient.isComplete` reflects exchange status, `SaslClient.getNegotiatedProperty` reads negotiated values, and `SaslClient.wrap/unwrap` handles the security layer when present.

The snippet below **only illustrates the integration point** inside an LDAP application that already supplies a callback handler, credentials, and a protocol-managed token exchange loop; it is **not a standalone program**:

```java
Map<String, Object> props = Map.of(
        Sasl.QOP, "auth-conf,auth-int");
SaslClient client = Sasl.createSaslClient(
        new String[] {"GSSAPI"},
        null,
        "ldap",
        "directory.example.org",
        props,
        callbackHandler);
if (client == null) {
    throw new SaslException("No matching SASL mechanism found");
}
```

You need `import java.util.Map;` and `import javax.security.sasl.*;`, while `callbackHandler` and the Kerberos security context must be provided by the real integration environment. If the mechanism is disabled, a provider is missing, or environment settings are invalid, never assume client creation will succeed. Complete the token exchange and confirm a successful outcome per **the application protocol** before querying QOP.

Read QOP and block any session lacking confidentiality at the boundary before application data:

```java
static String requireConfidentialSaslLayer(SaslClient client)
        throws SaslException {
    if (!client.isComplete()) {
        throw new SaslException("SASL handshake not yet complete");
    }
    Object value = client.getNegotiatedProperty(Sasl.QOP);
    String qop = value instanceof String ? (String) value : null;
    if (!"auth-conf".equals(qop)) {
        throw new SaslException("Insufficient QOP: " + qop);
    }
    return qop;
}
```

This is an **integration method** placed inside a class importing `Sasl`, `SaslClient`, and `SaslException`. Per the API contract, calling `getNegotiatedProperty` before `isComplete()==true` may throw `IllegalStateException`; `null` means the property was not negotiated or does not apply. Never compare `props.get(Sasl.QOP)` against policy and conclude the session is safe: that map only holds the initial preference list.

For `auth-int`/`auth-conf` sessions, once QOP is verified, every protected payload must go through `wrap/unwrap`. Java SASL methods allow `wrap/unwrap` **only after** the authentication exchange completes *and* integrity/privacy has been negotiated. Calling them when QOP is `auth` can throw `IllegalStateException`.

### 5.3. Illustrative framing per RFC 4422

The two methods below illustrate **application-managed raw stream** framing: a 4-byte length prefix, receive size cap, and `wrap/unwrap` calls. This snippet compiles as a helper class, but **does not initiate a SASL session** and is suitable only once the peer has authenticated and the protocol requires this framing format.

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import javax.security.sasl.SaslClient;

final class SaslFrameIO {
    static void send(OutputStream socket, SaslClient client, byte[] plain)
            throws IOException {
        byte[] protectedData = client.wrap(plain, 0, plain.length);
        DataOutputStream out = new DataOutputStream(socket);
        out.writeInt(protectedData.length);
        out.write(protectedData);
        out.flush();
    }

    static byte[] receive(InputStream socket, SaslClient client,
                          int maxFrameBytes) throws IOException {
        if (maxFrameBytes <= 0) {
            throw new IllegalArgumentException("maxFrameBytes");
        }
        DataInputStream in = new DataInputStream(socket);
        int size = in.readInt();
        if (size < 0 || size > maxFrameBytes) {
            throw new IOException("Invalid SASL frame size: " + size);
        }
        byte[] protectedData = new byte[size];
        in.readFully(protectedData);
        return client.unwrap(protectedData, 0, protectedData.length);
    }
}
```

`DataOutputStream.writeInt` writes big-endian bytes, matching network byte order. In a real application, you **must also**: check plaintext size against `Sasl.RAW_SEND_SIZE` before `wrap`; derive `maxFrameBytes` from policy, negotiated mechanism properties, or protocol limits rather than guessing; close the connection on error; use `SaslServer.wrap/unwrap` on the server; and **never double-wrap** if an LDAP/IMAP/SMTP library already handles this. `SaslException` extends `IOException`, so `throws IOException` on both signatures fits cleanly.

## 6. Clearly distinguishing SASL QOP from TLS

| Example | Actual SASL QOP | Payload protected by | Conclusion |
| --- | --- | --- | --- |
| **PLAIN + TLS** with server auth | `auth` | TLS | Can properly encrypt the connection, but PLAIN creates no SASL security layer. |
| **SCRAM-SHA-256-PLUS + TLS** | `auth` | TLS, with channel binding in authentication | "PLUS" does not mean `auth-conf`; channel binding ties authentication to the outer channel. |
| **GSSAPI `auth-int`** without TLS | `auth-int` | SASL integrity layer | Protects against tampering within the layer; **provides no confidentiality** for payloads from this layer alone. |
| **GSSAPI `auth-conf`** | `auth-conf` | SASL security layer | Data actually sent through `wrap` receives integrity and confidentiality protection. |
| **GSSAPI `auth` + TLS** | `auth` | TLS | May satisfy *transport encryption* rules; fails a requirement that **SASL QOP must be `auth-conf`**. |

Security rules should be stated precisely: "verified TLS is required," "SASL `auth-conf` is required," or both. Each requirement must be tested independently. Downgrade defenses also depend on mechanism selection, peer identity, and channel protection before/after authentication—checking only the final QOP is not enough.

## 7. Common mistakes, symptoms, and fixes

1. **Treating configuration as proof:** seeing `Sasl.QOP=auth-conf,auth-int` and logging "encrypted". Fix: report protection level only after reading `getNegotiatedProperty(Sasl.QOP)` on successful authentication.
2. **Demanding privacy from a layerless mechanism:** PLAIN or SCRAM will not yield SASL `auth-conf`. Fix: enforce verified TLS or choose an appropriate mechanism/protocol instead of weakening policy.
3. **Equating `auth-int` with encryption:** integrity does not hide content. Fix: state confidentiality requirements explicitly and enforce `auth-conf` if needed at the SASL layer.
4. **Calling `getNegotiatedProperty` before the exchange completes:** the API may throw `IllegalStateException`. Fix: verify `isComplete()` and the protocol's success outcome first.
5. **Calling `wrap/unwrap` with QOP `auth`:** the API permits them only after integrity/privacy is negotiated. Fix: never invoke the security layer when none exists.
6. **Wrong framing or sizes:** missing the 4-byte length, exceeding max frame size, or assuming raw and protected buffers have identical length. Fix: follow the protocol, validate length **before** allocating, and chunk payloads within the raw-send limit.
7. **Continuing after `unwrap` fails:** treating corrupted data as plaintext destroys integrity guarantees. Fix: stop processing and close the connection.
8. **GSSAPI not ready:** invalid principal, Kerberos ticket, service name, hostname, or provider. Fix: diagnose authentication and context setup before inspecting negotiated QOP.
9. **Assuming the SASL layer covers every byte:** handshakes and out-of-scope metadata may remain unprotected by the layer. Fix: evaluate exact message scope and apply TLS where needed.
10. **Using DIGEST-MD5 because it once supported all three levels:** RFC 6331 obsoleted this mechanism. Fix: choose maintained, vetted solutions.

### Integration testing checklist

- Record the actually chosen mechanism, provider/version, requested QOP on both sides, **negotiated QOP**, and TLS status; never log passwords, raw tickets/tokens, or sensitive plaintext.
- Test one compliant session and one downgraded or insufficient-QOP session; the insufficient case **must fail before sending business payloads**.
- For `auth-int`, tamper with a protected frame to verify rejection; never infer confidentiality from a passing integrity test.
- For `auth-conf`, verify data passes through `wrap/unwrap`, test invalid frame lengths and corrupted frames, and verify connection closure handling.
- Test large payloads to verify overhead, `MAX_BUFFER`, `RAW_SEND_SIZE`, chunking, and receive caps.
- Test TLS and server identity verification **separately** when the system relies on transport protection.

## 8. Scenario exercises and answers

**A.** The client requests `auth-conf,auth-int`, and the server only offers `auth-int`; application policy mandates data secrecy in the SASL layer. **Answer:** `auth-int` could be negotiated mechanically, but the application must reject the session because confidentiality is absent.

**B.** PLAIN runs over TLS and Java reports QOP `auth`. Is there a contradiction? **No:** PLAIN only authenticates; TLS protects the transport. The two concepts belong to different layers.

**C.** The session selected `auth-conf`, yet the application writes payloads straight to the socket, bypassing the protocol-mandated security layer. Is the data safe? **No:** QOP does not protect bytes that bypass `wrap`.

**D.** `getNegotiatedProperty(Sasl.QOP)` returns `null` after successful authentication. Can `auth-conf` be assumed? **No:** the property is absent/not applicable; if a SASL security layer is required, reject or investigate the provider.

**E.** `SCRAM-SHA-256-PLUS` contains the word "PLUS". Does it have SASL `auth-conf`? **No:** PLUS refers to channel binding to the outer channel, not a payload-protecting security layer.

## 9. Standards and Java API references

- [RFC 4422 – SASL, §3.7 Security Layers](https://www.rfc-editor.org/rfc/rfc4422.html): when layers are installed, 4-byte framing, error handling, and buffer limits.
- [RFC 4752 – GSSAPI/Kerberos V5 SASL mechanism](https://www.rfc-editor.org/rfc/rfc4752.html): negotiating no layer/integrity/confidentiality and GSS context conditions.
- [RFC 4616 – PLAIN](https://www.rfc-editor.org/rfc/rfc4616.html): PLAIN provides no security layer.
- [RFC 5802 – SCRAM](https://www.rfc-editor.org/rfc/rfc5802.html), [RFC 7677 – SCRAM-SHA-256](https://www.rfc-editor.org/rfc/rfc7677.html): SCRAM negotiates no security layer; channel binding is a distinct feature.
- [RFC 6331 – Moving DIGEST-MD5 to Historic](https://www.rfc-editor.org/rfc/rfc6331.html): deprecation warning for the legacy mechanism.
- [Java SE 21 `Sasl` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/Sasl.html), [`SaslClient` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html), and [Java 17 SASL programming guide](https://docs.oracle.com/en/java/javase/17/security/java-sasl-api-programming-and-deployment-guide1.html): property names, preference lists, negotiated results, `wrap/unwrap`, and the GSSAPI provider.

**Takeaway:** `auth` only authenticates; `auth-int` adds integrity; `auth-conf` adds confidentiality. The **actual** QOP depends on the mechanism, provider, both endpoints, and the protocol. Never substitute requested preferences for verified negotiated outcomes, and never treat TLS security as another SASL QOP.
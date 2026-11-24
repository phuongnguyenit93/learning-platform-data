# 16.3 SSLParameters for protocols, cipher suites, SNI, ALPN, and endpoint identification

A Java client can use `SSLContext` and `SSLEngine` or `SSLSocket` to create a TLS connection. However, `SSLContext.getInstance("TLS")` **does not explain by itself** which TLS versions will be enabled, which *cipher suite* is selected, whether the client sends the server name via SNI, how the application protocol is negotiated via ALPN, and especially whether the client verifies that **the certificate actually belongs to the target hostname**.

In JSSE (*Java Secure Socket Extension*), `javax.net.ssl.SSLParameters` is a configuration object for those handshake terms and related checks. It includes the protocol list, cipher suites, SNI, ALPN, endpoint identification, and several other options. However, you must distinguish **applied configuration** from **negotiated and successfully verified handshake results**: `setProtocols` does not guarantee the peer supports the protocol, `setApplicationProtocols` does not mean HTTP/2 is already in use, `setServerNames` does not replace hostname verification, and `setEndpointIdentificationAlgorithm("HTTPS")` does not create a trusted trust anchor on its own.

This lesson uses **Java 17+** and focuses on five groups:

1. `protocols`: restricting allowed TLS versions.
2. `cipherSuites`: restricting TLS algorithm suites compatible with the version and policy.
3. `serverNames` / **SNI**: announcing the server name so the server selects the appropriate configuration/certificate.
4. `applicationProtocols` / **ALPN**: negotiating the application-layer protocol, such as `h2` or `http/1.1`.
5. `endpointIdentificationAlgorithm`: instructing JSSE to verify the server identity, especially the hostname of an HTTPS connection.

The goal is to know how to **place the right attributes on the right side (client/server), before the handshake**, maintain full TLS verification, recognize the limits of the APIs, and write positive/negative tests. The runnable Java example in section 9 requires no network to avoid depending on public servers and does not pretend that successful configuration equals authenticating a TLS peer.

## 1. Learning objectives

After this lesson, you will be able to:

- Explain the relationship among `SSLContext`, `SSLEngine`, `SSLSocket`, `SSLParameters`, `TrustManager`, and `KeyManager`.
- Retrieve configuration via `getSSLParameters()`, modify the required attributes, and apply them via `setSSLParameters(...)` **before starting the handshake**.
- Distinguish `getSupportedProtocols()` from `getEnabledProtocols()` and avoid enabling legacy TLS versions merely to connect.
- Understand cipher suite naming in TLS 1.2 vs. TLS 1.3, and their relationship to protocol, certificate, signature, and key exchange.
- Use `SNIHostName` and `SSLParameters.setServerNames(...)` on the **client**, knowing server-side `SNIMatcher` does not replace certificate/hostname validation.
- Use `setApplicationProtocols(...)` to offer ALPN and read the **negotiated** protocol after the handshake via `SSLEngine.getApplicationProtocol()` or `SSLSocket.getApplicationProtocol()`.
- Enable `HTTPS` endpoint identification on the appropriate socket/engine, understanding `SNI != hostname verification != trust chain validation`.
- Grasp key differences among `SSLEngine`, `SSLSocket`, `HttpsURLConnection`, and `java.net.http.HttpClient`.
- Test misconfigurations, downgrades, ALPN mismatches, wrong SNI, wrong certificate SAN, untrusted CAs, mTLS, and the impact of TLS connection pooling.

## 2. Where does SSLParameters sit in JSSE?

An overview layer view:

```text
Java application
    |
    +-- java.net.http.HttpClient / HTTPS library
    |       |
    |       +-- JSSE/TLS implementation (depends on library/provider)
    |
    +-- SSLSocket or SSLEngine directly
            |
            +-- SSLContext
            |      +-- KeyManager (local identity, if needed)
            |      +-- TrustManager (peer certificate verification)
            |      +-- SecureRandom / provider
            |
            +-- SSLParameters (handshake / endpoint configuration)
                   +-- protocols
                   +-- cipher suites
                   +-- SNI server names
                   +-- ALPN application protocols
                   +-- endpoint identification algorithm
                   +-- client auth / algorithm constraints / other options
```

`SSLContext` is initialized with key managers/trust managers/provider per policy. An `SSLEngine` or `SSLSocket` is created from the context and carries the configuration used during communication. `SSLParameters` is normally **a mutable configuration object**, not a "security verification result."

Common update pattern:

```java
// Illustrative code inside a method; assume SSLEngine engine is already created.
SSLParameters p = engine.getSSLParameters();
p.setEndpointIdentificationAlgorithm("HTTPS");
engine.setSSLParameters(p); // Apply back to the engine.
```

Do not modify `p` and forget `setSSLParameters(p)`. Having an object `p` with new values does not mean the engine/socket has received the changes.

### Five questions to keep separate

| Question | Related property/API | What does it prove? |
| --- | --- | --- |
| Which TLS versions do I allow? | `setProtocols` | The versions configured as enabled on the endpoint |
| Which TLS algorithms do I allow? | `setCipherSuites` | The suites configured; not yet certain the peer can select one |
| Which target name should the server receive to pick a certificate? | `setServerNames` / SNI | Client sends the name as a TLS extension when the handshake supports it |
| Will client/server speak HTTP/2 or HTTP/1.1? | `setApplicationProtocols` / ALPN | Offered list; actual protocol is known only after negotiation |
| Does the certificate represent the right endpoint? | `setEndpointIdentificationAlgorithm("HTTPS")` | Enables endpoint identity policy for the matching engine/socket; still needs a trusted path and real handshake |

**Not interchangeable:** SNI is information the client sends so the server selects a virtual host; ALPN selects the application protocol; hostname verification validates the server name from the certificate. All three may use the same hostname in an HTTPS application, yet they are **three independent mechanisms**.

## 3. Distinguishing supported, enabled, configured, and negotiated

This is the key to avoiding misreading JSSE output.

- **Supported:** the provider/runtime implements a TLS protocol or cipher suite, exposed via `getSupportedProtocols()` and `getSupportedCipherSuites()`.
- **Enabled:** the set of features currently enabled by default policy and applied configuration for that endpoint, exposed via `getEnabledProtocols()` and `getEnabledCipherSuites()`.
- **Configured/allowed:** the set explicitly set by the application via `SSLParameters`; must be a subset compatible with the provider and policy.
- **Negotiated:** the result the peers actually agree upon after the handshake; inspected via `SSLSession.getProtocol()`, `SSLSession.getCipherSuite()`, and `getApplicationProtocol()`.

```text
Provider SUPPORTED
       |
       v
Runtime security policy + endpoint defaults
       |
       v
ENABLED / app override via SSLParameters
       |
       v
ClientHello + ServerHello + certificate checks + handshake
       |
       v
NEGOTIATED protocol, cipher suite, ALPN, authenticated peer
```

A protocol present in **supported** but absent from **enabled** may be disabled because it is obsolete, dangerous, or non-compliant with policy. **Do not re-enable it simply because it appears in the supported list.** Java 17 typically supports TLS 1.2 and 1.3 on common JSSE providers, though the actual list depends on vendor/build/provider, security properties, `jdk.tls.disabledAlgorithms` settings, and runtime.

### Safe-by-default configuration

In production, start from **governed JSSE defaults** or a reviewed allowlist. If minimum TLS 1.2 is mandatory, take the intersection of allowed versions with **enabled protocols** at the specific runtime. If the intersection is empty, **fail closed** instead of forcing TLS 1.0/1.1 on.

Do not take the array from `getSupportedProtocols()` and feed it directly into `setProtocols(...)`; doing so can enable protocols that JDK defaults intentionally excluded.

## 4. Protocols: TLSv1.2, TLSv1.3, and handshake version

How to set:

```java
// Illustrative code: use only when protocols are verified as enabled and policy-approved.
SSLParameters p = engine.getSSLParameters();
p.setProtocols(new String[] { "TLSv1.3", "TLSv1.2" });
engine.setSSLParameters(p);
```

Conceptually, this is the list of versions **allowed to be attempted during negotiation**. It does not force the server to pick TLS 1.3; the server may support only TLS 1.2, or the intersection of versions may be empty and the handshake fails.

**TLS 1.3** introduces major changes over TLS 1.2 in the handshake flow, defined cipher suites, and ephemeral key mechanics. Do not assume a cipher suite named `TLS_AES_128_GCM_SHA256` works with TLS 1.2 or that a name like `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` is a TLS 1.3 suite.

### Risky settings to watch out for

- Enabling `TLSv1` / `TLSv1.1` / `SSLv3` to "support legacy servers" without policy review.
- Treating `SSLContext.getInstance("TLS")` as fixed to only TLS 1.2/1.3 regardless of provider.
- Reading `setProtocols` as "the handshake already used TLS 1.3."
- Removing TLS 1.2 on a system whose clients/peers do not yet support TLS 1.3 without compatibility testing.
- Letting user requests decide the protocol/cipher list and passing it straight into `SSLParameters`.
- Changing global security properties or providers just to get one legacy connection working, inadvertently affecting the entire JVM.
- Changing the allowlist after `SSLSocket` has already completed the handshake; an established connection does not renegotiate automatically to the new config.

### When should you allow TLSv1.3 only?

When the threat model and all peers support it, **TLS 1.3 only** can be a sound policy. For systems needing compatibility, allowing TLS 1.2 and 1.3 under a strong profile can also be valid. Measure telemetry and establish a deprecation roadmap for older TLS; choosing protocols is a **security/compliance and compatibility decision**, not guesswork based on a single demo.

## 5. Cipher suites: TLS 1.2 differs from TLS 1.3

A **cipher suite** describes the combination of TLS algorithms used during the handshake and record protection. However, the amount of information encoded in the suite name differs by TLS version.

| Version | Example suite name | What to understand |
| --- | --- | --- |
| TLS 1.3 | `TLS_AES_128_GCM_SHA256` | AEAD cipher + hash used in TLS 1.3; key exchange and authentication algorithms are negotiated via other mechanisms |
| TLS 1.3 | `TLS_AES_256_GCM_SHA384` | AES-GCM AEAD and corresponding hash |
| TLS 1.3 | `TLS_CHACHA20_POLY1305_SHA256` | ChaCha20-Poly1305 AEAD if supported by the provider |
| TLS 1.2 | `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | ECDHE key exchange, RSA-based authentication in TLS 1.2 profile, AES-GCM |
| TLS 1.2 | `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256` | ECDHE with ECDSA certificate/authentication in TLS 1.2 profile |
| TLS 1.2 | `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384` | TLS 1.2 profile with ECDHE and AES-GCM |

**Do not interpret TLS 1.3 suite names using TLS 1.2 naming logic.** In TLS 1.3, the cipher suite no longer encodes the RSA/ECDSA certificate algorithm or key exchange as in TLS 1.2.

### Selecting cipher suites properly

- Start from **enabled suites**, not all supported suites.
- Keep only suites in an up-to-date security allowlist that are **compatible with the protocol**.
- Do not force a TLS 1.3 suite when allowing only TLS 1.2; this can cause "no shared cipher"/handshake failure.
- With TLS 1.2, the certificate's key type and server capabilities also matter. An ECDSA suite may not work with a server deploying only an RSA identity, depending on configuration and provider.
- Do not treat `setCipherSuites(...)` as a mechanism for pinning certificates or enforcing peer identity.
- For most standard HTTPS apps, keeping updated JSSE/provider defaults without hard-pinning a single suite helps preserve compatibility. Pin a suite list only when specifically required and tested on both sides.

### Configuring cipher suite order

`SSLParameters.setUseCipherSuitesOrder(true)` means prioritizing the **server's** suite order in applicable cases/protocols/providers. It does not guarantee the server always picks the first suite if incompatible or unsupported. TLS 1.3 and TLS 1.2 have different negotiation rules; always test the actual negotiated cipher.

### Strong warning

Do not use or re-enable cipher suites disabled by JDK policy just because a legacy peer asks for them. Decisions such as dropping static RSA key exchange in TLS 1.2, CBC/3DES/RC4, or weak signature algorithms must follow security policy, not copying an old list from the internet.

## 6. SNI: client announces which server name it wants to connect to

**SNI** (*Server Name Indication*) is a TLS extension allowing a client to send a server name to the endpoint, typically helping a server/CDN/reverse proxy sharing an IP:port select the corresponding certificate and virtual host. One server can serve multiple hostnames on the same IP address.

Example:

```text
Shared IP 203.0.113.10:443
   |
   +-- api.example.test    -> certificate A / virtual host A
   |
   +-- admin.example.test  -> certificate B / virtual host B

Client connects to api.example.test
   ClientHello SNI = api.example.test
   Server chooses certificate A
```

**SNI is not proof of identity.** A client can say it wants server name `api.example.test`, but the TLS client must still verify that the server's certificate matches that name and chains to an allowed trust anchor. If the server returns a certificate for `admin.example.test`, having sent the right SNI **will not** save you from a hostname mismatch error.

### Java client using SNIHostName

```java
// Illustrative code inside a method.
String hostname = "api.example.test";
SSLParameters p = engine.getSSLParameters();
p.setServerNames(List.of(new SNIHostName(hostname)));
engine.setSSLParameters(p);
```

This snippet requires importing `java.util.List` and `javax.net.ssl.SNIHostName`, and assumes `engine` was created for the right peer. `SNIHostName` represents an SNI `host_name`; never pass a full URL `https://api.example.test/path`, port `:443`, wildcard `*.example.test`, IP literal, or invalid string where a DNS name belongs.

**In many modern JSSE HTTPS clients, SNI may be populated automatically from the target hostname.** Manual setting is needed only when you have a specific reason and are sure it does not conflict with the host used by endpoint identification. When connecting to an IP while needing to verify a DNS name, clearly understand the API of the TLS engine/socket, peerHost, SNI, HTTP Host header, and security policy; never tweak a single string to bypass verification.

### SNI on the server

On the server side, `SSLParameters.setSNIMatchers(...)` or TLS stack logic can decide whether to accept/rank names and select a local identity. However:

- `SNIMatcher` does not automatically issue a certificate for a hostname.
- `setServerNames` is how the client supplies a list of names, **not** a configuration declaring "hostnames the server definitely owns."
- The server typically needs `KeyManager`/alias selection/certificate chains matching the SNI.
- If the server requires a specific SNI, missing/wrong SNI may be rejected per policy or fall back to a default virtual host; behavior depends on the server.
- Traditional SNI is not always hidden from network observers; never put tokens, secrets, or sensitive business data inside SNI.
- SNI and HTTP `Host`/`:authority` should be handled consistently, never allowing a spoofed Host header to bypass TLS peer/route authorization.

### SNI vs. hostname verification

| Mechanism | Who initiates? | What does it check? |
| --- | --- | --- |
| SNI | Client sends name during handshake | Helps the server know which virtual host is requested |
| Certificate SAN | CA/issuer embeds identity into certificate | List of DNS/IP names declared by the certificate |
| Endpoint identification | Client verifies certificate against expected peer host | Confirms the certificate is valid for the target hostname/IP |
| HTTP Host / :authority | HTTP client sends origin name | HTTP routing; does not replace TLS authentication |
| App authorization | Application checks caller/tenant/endpoint | Whether the user is permitted to perform the action |

Do not conclude "SNI is right" just because `getServerNames()` returns the name. That only checks local config; a real handshake must occur and the endpoint certificate must still validate successfully.

## 7. ALPN: negotiating HTTP/2, HTTP/1.1, and other protocols

**ALPN** (*Application-Layer Protocol Negotiation*) is a TLS extension allowing client and server to select the application protocol running **over** the TLS connection. For example, an HTTPS client might offer:

```text
Client ALPN offers: ["h2", "http/1.1"]
Server ALPN supports: ["http/1.1"]
Negotiated ALPN: "http/1.1"
```

If both sides support it and policy allows, the result may be `h2`. ALPN **does not implement HTTP/2 on its own**: the application must have HTTP/2 framing, stream management, flow control, and protocol semantics. If a raw Java socket sets ALPN `h2` while the program still writes HTTP/1.1 text, the connection will not operate properly.

### Java setting ALPN offers

```java
SSLParameters p = engine.getSSLParameters();
p.setApplicationProtocols(new String[] { "h2", "http/1.1" });
engine.setSSLParameters(p);
```

Offer order can carry preference semantics depending on the TLS stack/server. `setApplicationProtocols` declares the configured ALPN list, **not yet the negotiation result**. After the handshake completes:

```java
// Illustrative code once the handshake has actually succeeded.
String selectedProtocol = engine.getApplicationProtocol();
```

If the application **requires HTTP/2**, it must verify the result is `"h2"` before sending HTTP/2 frames. If the application allows HTTP/1.1 fallback, it must switch to the corresponding protocol implementation. When the peer does not negotiate ALPN or returns an unacceptable result, fail/fallback behavior must follow the protocol specification rather than assuming `"http/1.1"` for every application.

### ALPN server selection

JSSE provides server-side APIs such as `SSLSocket.setHandshakeApplicationProtocolSelector(...)` or the `SSLEngine` variant in appropriate environments. The server must choose **a protocol offered by the client** and actually implemented by the server, per policy. Do not return arbitrary strings or pick `h2` when the application does not support it.

ALPN also appears in TLS-based gRPC, HTTP/2, and many custom protocols. A gRPC service typically needs to verify `h2`/HTTP/2; do not think setting an ALPN string is enough to instantly turn a service into a gRPC server.

### ALPN does not solve certificate trust

Even if `h2` is selected successfully, the client must still verify the chain, hostname, KU/EKU, protocol security, and application authorization. Never use ALPN output as proof that a peer is a specific service.

## 8. Endpoint identification: binding the certificate to the target hostname

**Endpoint identification** is the step that checks whether the peer's certificate represents the **requested service identity**. In HTTPS, this is usually the URL's DNS hostname or IP literal. It is a separate layer of protection from having the certificate signed by a trusted CA.

Example:

```text
Requested endpoint: https://payments.example.test
Certificate chain: valid to trusted CA
Leaf SAN: DNS:files.example.test

CA path valid?  yes
Name valid?     no
Result:         reject connection
```

Trusting a CA alone is insufficient: a trusted CA can issue certificates for many hostnames. Checking the chain without checking the name lets an attacker with a valid certificate for their own hostname present it on a connection the application thinks belongs to another hostname.

### Java enabling HTTPS endpoint identification

```java
SSLParameters p = engine.getSSLParameters();
p.setEndpointIdentificationAlgorithm("HTTPS");
engine.setSSLParameters(p);
```

The `"HTTPS"` property requests the JSSE-supported HTTPS identity verification algorithm during the handshake. Key conditions:

- The engine/socket must have the **expected peer hostname** created/set properly via the API; an `SSLEngine` unaware of the peer host may lack the context to check names as you expect.
- `SSLContext` must have an appropriate **trust manager** to verify the chain. Enabling hostname checking does not make an untrusted certificate trustworthy.
- The connection must actually perform the handshake and the trust manager/provider must run validation. Seeing `getEndpointIdentificationAlgorithm()` return `"HTTPS"` checks configuration, **not** the certificate.
- With high-level HTTP clients such as `java.net.http.HttpClient`, endpoint verification is usually managed by the library. **Do not disable or accidentally overwrite** those internal settings.
- With raw `SSLSocket`, verify configuration timing, peer host, and TLS context; do not assume all socket factories behave identically.
- For a TLS server verifying an **mTLS client certificate**, identity policy differs from an HTTPS server hostname. Check the chain, `clientAuth` KU/EKU, mapping certificate identity to a principal, and authorization.

### Things you should never do

- `p.setEndpointIdentificationAlgorithm(null)` or `""` to make a mismatched certificate be accepted.
- Install a `HostnameVerifier` that always returns true, or an empty `X509TrustManager.checkServerTrusted`.
- Take an arbitrary user-supplied name and use it as the "expected hostname" to accept an attacker's certificate.
- Compare Subject CN using `contains(...)` or `endsWith(...)` instead of standard SAN/IDN/wildcard rules.
- Treat the SNI hostname as a trusted identity without checking it against the certificate.
- Disable verification when using proxies, service meshes, or private CAs: configure the exact trust anchors, SNI/hostname, and endpoint identity required by the environment.

### SNI, ALPN, and endpoint identification in one flow

```text
Client knows trusted URL/hostname = api.example.test
    |
    v
SSLParameters:
    protocol allowlist
    cipher suite allowlist
    SNI host = api.example.test
    ALPN offers = ["h2", "http/1.1"]
    endpointIdentificationAlgorithm = "HTTPS"
    |
    v
TLS ClientHello / server selection
    |
    v
Server certificate + agreed TLS version/cipher + ALPN
    |
    v
Trust chain validation + hostname SAN + TLS policy
    |
    +--> reject if any mandatory check fails
    |
    v
Authenticated TLS channel
    |
    v
Application speaks negotiated ALPN protocol
    |
    v
Application still checks authorization/tenant/resource
```

## 9. Runnable Java 17+ program requiring no network connection

The following program solely **configures a client `SSLEngine`**, without calling handshake or sending requests to a real hostname. It picks **one enabled protocol** from the `TLSv1.3`/`TLSv1.2` allowlist, picks **one enabled cipher suite compatible with the chosen version**, and sets SNI, ALPN, and `HTTPS` endpoint identification.

Intentionally choosing **one** protocol and **one** suite makes the code and output easy to read. This is **not a recommendation** for production to always pin a single suite; production should generally use a compatible allowlist or governed security defaults to avoid rigid pinning that breaks connectivity. The code fails closed if the runtime has no matching option in the list. The output below proves only that the configuration was applied to the engine.

Save as **`SslParametersDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SNIHostName;

public class SslParametersDemo {
    static String choose(String[] preferred, String[] enabled) {
        List<String> candidates = Arrays.asList(enabled);
        for (String value : preferred) {
            if (candidates.contains(value)) return value;
        }
        throw new IllegalStateException("No approved enabled option");
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null); // Demo: provider default key/trust managers.
        String host = "api.example.test";
        SSLEngine engine = context.createSSLEngine(host, 443);
        engine.setUseClientMode(true);

        String protocol = choose(
                new String[] {"TLSv1.3", "TLSv1.2"},
                engine.getEnabledProtocols());
        String[] preferredSuites = protocol.equals("TLSv1.3")
                ? new String[] {
                    "TLS_AES_128_GCM_SHA256",
                    "TLS_AES_256_GCM_SHA384",
                    "TLS_CHACHA20_POLY1305_SHA256"
                  }
                : new String[] {
                    "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
                    "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
                    "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384"
                  };
        String suite = choose(preferredSuites, engine.getEnabledCipherSuites());

        SSLParameters parameters = engine.getSSLParameters();
        parameters.setProtocols(new String[] {protocol});
        parameters.setCipherSuites(new String[] {suite});
        parameters.setServerNames(List.of(new SNIHostName(host)));
        parameters.setApplicationProtocols(new String[] {"h2", "http/1.1"});
        parameters.setEndpointIdentificationAlgorithm("HTTPS");
        engine.setSSLParameters(parameters);

        SSLParameters applied = engine.getSSLParameters();
        boolean protocolApplied = Arrays.equals(
                new String[] {protocol}, applied.getProtocols());
        boolean suiteApplied = Arrays.equals(
                new String[] {suite}, applied.getCipherSuites());
        boolean sniApplied = Objects.equals(
                List.of(new SNIHostName(host)), applied.getServerNames());
        boolean alpnApplied = Arrays.equals(
                new String[] {"h2", "http/1.1"},
                applied.getApplicationProtocols());

        System.out.println("Client mode: " + engine.getUseClientMode());
        System.out.println("Protocol in enabled allowlist: " +
                Arrays.asList(new String[] {"TLSv1.3", "TLSv1.2"})
                        .contains(protocol));
        System.out.println("Protocol applied: " + protocolApplied);
        System.out.println("Cipher suite applied: " + suiteApplied);
        System.out.println("SNI host applied: " + sniApplied);
        System.out.println("ALPN offers applied: " + alpnApplied);
        System.out.println("Endpoint identification: " +
                applied.getEndpointIdentificationAlgorithm());
        System.out.println("No handshake performed: true");
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac --release 17 SslParametersDemo.java
java SslParametersDemo
```

**Verified stdout after running on a runtime with one of the corresponding protocols/suites enabled:**

```text
Client mode: true
Protocol in enabled allowlist: true
Protocol applied: true
Cipher suite applied: true
SNI host applied: true
ALPN offers applied: true
Endpoint identification: HTTPS
No handshake performed: true
```

If the runtime/provider does not enable TLS 1.2/1.3 or has none of the allowed suites, `choose` intentionally throws `IllegalStateException`; that is **fail closed**, not a reason to enable weak suites. This is conditional output from the tested environment, not a guarantee that every vendor/JDK produces identical results.

### 9.1 Step-by-step analysis

1. `SSLContext.getInstance("TLS")` selects a TLS implementation from the provider. `context.init(null,null,null)` uses the provider's default key/trust configuration for demo purposes; **it does not verify a specific server** and `null` should not be assumed to always point to `cacerts` across all runtimes.
2. `createSSLEngine(host,443)` creates an engine with reference peer host/port, which is crucial for endpoint checks and SNI during a real handshake. It makes **no** network connection.
3. `setUseClientMode(true)` sets the TLS client role. The mode must be set before the handshake and before using client-specific parameters.
4. `getEnabledProtocols()` returns the currently enabled versions. `choose` takes only `TLSv1.3` or `TLSv1.2` from that set, never blindly enabling every supported protocol.
5. The selected cipher list **depends on the protocol**. This is a minimal example to avoid mixing TLSv1.3 with TLSv1.2 suites. A real server has its own certificate/key/signature/ALPN and policy, so the handshake can still fail even when a local suite is enabled.
6. `setProtocols` and `setCipherSuites` apply the checked selections; `setServerNames` sets the SNI hostname, `setApplicationProtocols` offers `h2`/`http/1.1`, and `setEndpointIdentificationAlgorithm("HTTPS")` enables expected identity checking.
7. `engine.setSSLParameters(parameters)` is the **apply** step. Subsequent `getSSLParameters()` checks local values, not server state.
8. The boolean variables confirm the attributes were retained. No line in the output claims "TLS handshake successful" or "server trusted."
9. `No handshake performed: true` is a statement about the program's design, **not a TLS security assertion**. The program never calls `engine.beginHandshake()`, `wrap`, or `unwrap`.

### 9.2 Why didn't the demo include full SSLEngine handshake code?

`SSLEngine` is a nonblocking API meant for programs that manage buffers, I/O, handshake status, and delegated tasks. A real handshake requires a `wrap/unwrap` loop, handling `NEED_TASK`, `NEED_WRAP`, `NEED_UNWRAP`, proper timeout/EOF handling, and an actual peer transport. A short example that just calls `beginHandshake()` and prints "connected" would be **incorrect**.

To keep the focus on `SSLParameters`, the demo only creates/configures the engine and verifies via getters. For real HTTP applications, use a proven HTTP client/JSSE library instead of writing your own handshake state machine.

### 9.3 Do not copy hardcoded suites to production

The example prefers `TLS_AES_128_GCM_SHA256` when using TLS 1.3, or a matching ECDHE-GCM suite when using TLS 1.2. This is a choice for a deterministic demo. Production requires:

- Not defaulting to TLS 1.2 if the organization mandates TLS 1.3.
- Not forcing an RSA/ECDSA TLS 1.2 suite when the server certificate/key does not match.
- Not assuming a suite present in the provider is approved by policy.
- Not letting clients choose security targets regardless of policy.
- Testing against real servers, planning for certificate rotation, and updating JDK/root stores.

## 10. SSLSocket and real handshakes: configuration must take effect before sending

With `SSLSocket`, you can also call `getSSLParameters()`, modify it, and call `setSSLParameters(...)` before `startHandshake()`. Example **illustrated inside a method** (not a standalone program; requires appropriate exception handling/imports and a reliably configured `SSLContext context`):

```java
String host = "api.example.test";
int port = 443;

try (SSLSocket socket = (SSLSocket)
        context.getSocketFactory().createSocket(host, port)) {
    SSLParameters p = socket.getSSLParameters();
    p.setServerNames(List.of(new SNIHostName(host)));
    p.setApplicationProtocols(new String[] {"h2", "http/1.1"});
    p.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(p);

    socket.startHandshake(); // May fail due to CA/SAN/protocol/suite.
    SSLSession session = socket.getSession();
    String negotiatedTls = session.getProtocol();
    String negotiatedCipher = session.getCipherSuite();
    String negotiatedApp = socket.getApplicationProtocol();

    // Select the right implementation for negotiatedApp before exchanging data.
}
```

The snippet above **does not configure an HTTP/2 interface or perform an HTTP request**. It only shows post-handshake information and serves as a reminder that TLS and HTTP are two separate layers. When connecting to a real test server, you need an appropriate truststore/CA, accurate DNS/SNI/hostname, and endpoint identification enabled.

### Why configure before the handshake?

The handshake negotiates protocol, cipher suite, SNI/ALPN, and peer authentication. Modifying `SSLParameters` after the handshake does not automatically force the existing session to restart or re-verify the certificate. In practice, HTTP keep-alive, pooling, and TLS session resumption complicate policy reloading further. When policy changes, create new SSL contexts/clients or manage pools/sessions per your threat model.

### SSLSocket with custom TrustManager

`SSLParameters` controls only part of the checks. Trust anchors come from `SSLContext`/`TrustManagerFactory`/an appropriate `X509ExtendedTrustManager`. If you write a custom `X509TrustManager`, you must fully understand whether JSSE applies endpoint checks with custom managers: never write an empty `checkServerTrusted` assuming `setEndpointIdentificationAlgorithm("HTTPS")` will "make up for" missing chain validation.

Prefer a properly managed provider trust manager and a controlled CA store; avoid bypassing PKIX checks.

## 11. High-level Java HTTP client: avoid breaking library-managed constraints

`java.net.http.HttpClient` already manages many TLS, HTTP/2, and hostname verification details. Unless you have specific requirements, **keep the JDK's secure defaults** and update the runtime/trust policy. Some APIs allow specifying:

```java
// Illustrative code; assume SSLContext context is properly configured.
HttpClient client = HttpClient.newBuilder()
        .sslContext(context)
        .version(HttpClient.Version.HTTP_2)
        .build();
```

The snippet above is not a standalone program; it requires importing `java.net.http.HttpClient` and an initialized context. `version(HTTP_2)` is a high-level HTTP client preference/mode and **does not prove ALPN selected h2 on every connection**. The HTTP client may select/adjust ALPN or fall back depending on protocol/API; verify via actual responses/client traces when needed.

**Do not** stuff everything into an `SSLParameters` and pass it blindly to an HTTP client: some HTTP clients manage their own ALPN/hostname verification and may alter or ignore caller-supplied attributes. Read the documentation for the **exact library and version** deployed, and verify behavior in integration tests.

### Never disable hostname verification via global debug flags

Some people use internal flags or a custom `HostnameVerifier` returning always true to bypass SAN mismatch errors. Doing so can strip HTTPS identity guarantees. When facing TLS issues, fix the CA chain, SAN, URL hostname, SNI, proxy, and truststore—never disable verification.

## 12. Where does server configuration differ from client configuration?

On the server, `SSLParameters` is applied to `SSLServerSocket`, server-side `SSLSocket`, or server-side `SSLEngine` depending on architecture. Attributes may be interpreted differently:

| Attribute | TLS Client | TLS Server |
| --- | --- | --- |
| `setProtocols` | Versions the client is willing to offer | Versions the server is willing to accept |
| `setCipherSuites` | Suites eligible for negotiation | Suites the server can select |
| `setServerNames` | Name the client sends via SNI | **Not** used to declare server-owned hostnames |
| `setSNIMatchers` | Not commonly used | Can check/restrict incoming SNI per policy |
| `setApplicationProtocols` | ALPN list offered by client | ALPN list supported by server |
| `setEndpointIdentificationAlgorithm("HTTPS")` | Used when verifying an HTTPS server | Not a mechanism for the server to advertise its certificate/hostname |
| `setNeedClientAuth(true)` | Not an HTTPS server identity setting | Requires client certificate in mTLS via appropriate API |
| `setWantClientAuth(true)` | Does not replace authorization | Requests client certificate optionally per server policy |
| `setUseCipherSuitesOrder` | Does not force server to follow client order | Can express server preference where supported |

**Need vs. want client auth:** `needClientAuth` typically fails the handshake if no policy-valid client certificate is presented; `wantClientAuth` allows the client to omit a certificate where supported. The two settings interact; do not enable both and guess the override order. When enabling mTLS, the server must have a truststore for client CAs, identity mapping, and authorization—not just `setNeedClientAuth(true)`.

### Server selecting a certificate by SNI

A reverse proxy or Java server with multiple certificate identities can use the SNI hostname and `X509ExtendedKeyManager`/application server selection policy to pick a certificate/alias. That requires pre-configured key material/certificate chains. `SSLParameters.setSNIMatchers` does not create aliases or replace a key manager.

If the server only has a certificate for `api.example.test` while the client sends SNI `admin.example.test`, the server may pick a default certificate or reject. The client must still check SAN/endpoint identity and reject any certificate for a different name.

### Server selecting ALPN

The server must pick a protocol present in the list sent by the client and implemented by the server. If the server picks `h2`, the HTTP stack must genuinely understand HTTP/2; if it picks `http/1.1`, use the HTTP/1.1 parser. If the application uses TLS for another protocol, the ALPN string must match the corresponding standard/registry—do not invent meaningless names.

## 13. Interactions among protocol, cipher suite, certificate, and ALPN

A seemingly valid configuration can fail due to cross-constraints:

```text
Client enabled protocols:      TLSv1.3
Client configured cipher:      TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
Server supports:               TLSv1.3
Result:                        no mutually usable cipher suite for TLSv1.3

Client ALPN offers:            h2
Server ALPN supports:          http/1.1
Result:                        ALPN mismatch / no chosen protocol (policy-dependent)

Client target hostname:        a.example.test
Client SNI:                    b.example.test
Server presents cert:          b.example.test
Result:                        hostname verification must reject a.example.test
```

Each block is an **illustrative scenario**, not output from a standalone Java program. Specific errors may be `SSLHandshakeException` or no-application-protocol/fallback behavior depending on TLS version, provider, and library; do not treat exception text as a fixed contract.

**Key point:** TLS involves multiple linked checks. Do not accept a message like "Cipher suite applied: true" in a demo as proof of a valid handshake.

### Certificate signatures and cipher suites

A TLS 1.2 suite named `ECDHE_RSA` typically requires the matching certificate/authentication type; TLS 1.3 decouples suite selection from the authentication/signature algorithm and key-share negotiation. Consequently, moving from TLS 1.2 to TLS 1.3 can make config checks like "does the suite name contain RSA" stop reflecting the authentication flow. Always consider version, certificate algorithm, signature schemes, and provider policy.

### Session resumption and updated configuration

If an application changes trust roots, hostname policy, enabled versions, or ALPN, **already-established TLS connections and resumed sessions** may not immediately follow the new policy. During urgent changes (such as distrusting a CA), plan to replace clients/contexts, close connection pools, and inspect new handshakes/session caches. Do not merely edit one `SSLParameters` object and declare the whole cluster updated.

## 14. E2E testing: include both positive and negative cases

An integration test suite should distinguish **configuration unit tests** from **TLS handshake tests**:

| Case | Configuration or input | Expected result |
| --- | --- | --- |
| Config protocol | Set TLSv1.3 enabled per allowlist | `getSSLParameters` reflects configuration |
| Config suite | Set compatible and enabled suite | Applied; **does not prove handshake** |
| Real TLS version | Client/server share only TLSv1.2 | Handshake selects TLSv1.2 if policy allows |
| No shared protocol | Client TLSv1.3 only, server TLSv1.2 only | Handshake fails; no fallback outside policy |
| No usable cipher | Shared protocol but disjoint suites | Handshake fails |
| Matching SNI | Two virtual hosts, client sends name A | Server picks certificate/config for A if supported |
| Wrong SNI | Client sends name B while expecting A | Endpoint identity must reject certificate B for hostname A |
| Missing SNI | Server requires SNI to pick vhost | Fails or follows policy; never trusts wrong certificate |
| ALPN h2 | Both support h2 | `getApplicationProtocol()` returns h2 after successful handshake |
| ALPN fallback | Client offers h2/http1, server supports only http1 | Selects http/1.1 if policy/implementation allows |
| ALPN mismatch | No common protocol, app requires h2 | Fails closed or does not proceed into app violating protocol |
| Untrusted CA | Server cert chain does not lead to a trusted CA | Handshake rejects |
| SAN mismatch | Valid chain for a different hostname | HTTPS endpoint identification rejects |
| Expired cert | Server leaf expired | Handshake rejects per policy |
| Invalid KU/EKU | Leaf does not permit serverAuth per policy | TLS server auth rejects |
| Client auth required | mTLS server needs client cert, client has none | Handshake rejects |
| Unknown client certificate | mTLS client has cert from CA outside allowlist | Rejects per server trust policy |
| mTLS authorized? | Valid certificate but principal lacks permission | TLS may pass; application rejects request |
| Downgrade attempt | Peer requests legacy TLS disabled by policy | Rejects; never auto-enables legacy |
| Reused connection | CA policy changes while pool is open | Observe proper refresh/reload per lifecycle |
| Multi-runtime | Different JDK17/JDK versions | Verify actual supported/enabled/ALPN/endpoint behavior |
| Proxy/mesh | Separate TLS termination and SNI routing | Verify endpoints are authenticated at the right trust boundary |

**`SSLParameters` unit tests like section 9 are necessary but insufficient.** To prove connection security, you need a lab server with controlled certificate chains/SANs, a test truststore, and verification of the actual negotiated session.

### Building an isolated lab

You can use `keytool` to create a dedicated CA and leaf for `localhost`/test names; use a loopback port or test container. **Never** import test CAs into a production JDK's `cacerts`, and never use trust-all. Verify the certificate has the proper SAN for the hostname/loopback used, not just `CN`. A JSSE server can use `KeyStore`/`KeyManagerFactory`, while the client uses `TrustManagerFactory` loading the test CA.

To properly test ALPN, the server must have an implementation that selects `h2`/`http/1.1`, and the client must check `getApplicationProtocol()` after the handshake. With a server that speaks only HTTP/1.1, never configure ALPN `h2` and claim TLS success means HTTP/2 works.

## 15. Common mistakes when using SSLParameters

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Enabling everything from `getSupportedProtocols()` | May enable policy-disabled versions | Intersect allowlist with enabled and policy |
| Ignoring TLS version when picking cipher suites | No shared cipher; incompatible configuration | Use suites matching version profile; test handshake |
| Pinning a single suite across all services | Failures when rotating certificates or peer policy | Prefer defaults/curated compatible sets |
| Editing local `SSLParameters` without calling `setSSLParameters` | Engine/socket never receives the change | Re-apply and verify with getters |
| Configuring after the handshake | Session already negotiated earlier | Configure before handshake; refresh connection lifecycle |
| Confusing `setServerNames` with hostname verification | MITM / wrong peer identity | Enable endpoint identification and trust validation |
| Arbitrarily using SNI different from URL hostname | Server returns wrong identity certificate | Bind SNI, peerHost, and endpoint identity per policy |
| Passing a full URL into `SNIHostName` | Invalid SNI name / format error | Pass only an appropriate DNS hostname |
| Assuming ALPN offers = negotiated result | Sending HTTP/2 frames to an HTTP/1.1 peer | Read negotiated ALPN after the handshake |
| Setting ALPN `h2` without an HTTP/2 stack | Application protocol failure | Integrate a library that actually speaks h2 |
| Disabling endpoint identification to fix SAN errors | Accepts wrong-named server | Fix certificate/URL/SNI/trust |
| Installing a trust-all X509TrustManager | Removes CA/path validation | Trusted PKIX trust manager and narrow truststore |
| Mapping any clientAuth cert to admin privileges | mTLS authorization flaw | Validate identity then apply RBAC/ABAC |
| Using one custom truststore for all clients without scoping | Expands or drops public roots | Use per-client SSLContext when needed |
| Swapping truststore files without reloading context/pools | Keeps using old trust anchors | Versioned config, reload, and verify new handshakes |
| Relying on exception text strings | Misdiagnosis across JDKs | Log sanitized reasons and test on target provider |
| Treating `setSSLParameters` success = secure TLS | Ignores actual certificate/cipher/ALPN | Verify via handshake and negotiated session |
| Assuming raw SSLEngine runs I/O automatically | Handshake never completes | Properly implement SSLEngine wrap/unwrap/tasks or use an HTTP client |
| Leaving global debug flags on long-term in production | Huge logs, potential metadata leaks | Enable with controls, disable after diagnosis |
| Skipping negative tests | Fails to prove boundaries | Test wrong CA, wrong SAN, protocol/suite mismatch, ALPN mismatch |

## 16. Production configuration design workflow

An auditable workflow:

1. **Define security policy:** minimum TLS versions, cipher profiles, trust anchors, endpoint names, ALPN protocols, and mTLS requirements; explicitly state client/server scope.
2. **Inspect provider/runtime:** Java version, JSSE provider, `getEnabledProtocols()`, enabled suites, `jdk.tls.disabledAlgorithms`, container image, and root store.
3. **Prefer default HTTPS client:** override only for specific needs after understanding interactions with HTTP/2, hostname verification, and proxy/mesh.
4. **If using raw SSLEngine/SSLSocket:** create context with proper trust/key managers, use real peer host, set client/server mode, and configure `SSLParameters` **before handshake**.
5. **Use accurate SNI names:** never use SNI as authorization; cross-check against certificate SAN/hostname.
6. **Offer ALPN matching the application:** HTTP/2 requires an h2 stack; check negotiated protocol before sending data.
7. **Keep endpoint identification:** for HTTPS use the proper algorithm; do not drop it because of a private CA or proxy.
8. **Test negative paths too:** wrong server hostname, untrusted CA, wrong EKU, weak protocol/suite, and ALPN mismatch must all be handled per policy.
9. **Inspect actual negotiated state:** TLS version/cipher from `SSLSession`, ALPN from post-handshake APIs, peer certificate chain and identity via the TLS stack; never log secrets.
10. **Observe and operate:** TLS handshake failure rates, protocol/cipher distribution, certificate renewal, truststore version, and server-side changes.
11. **Roll out via canary:** across multiple JVMs/providers/regions, rollback-capable without re-enabling banned weak policies.
12. **Perform deliberate rotation/reload:** create new contexts/clients, manage session resumption/connection pooling, and handle CA distrust when required.
13. **Evaluate HTTP interactions:** proxy, redirect, Alt-Svc, SNI/authority routing, and HTTP/2 downgrade per system requirements.
14. **Never confuse TLS authentication with application authorization:** even when TLS succeeds, requests must still be authenticated and authorized at the business layer.

### Example of what to log and what not to log

Log (after privacy review): TLS version, cipher suite, negotiated ALPN, endpoint hostname, trust bundle version, sanitized handshake error category, and request/correlation ID. Never log: private keys, session secrets, raw application credentials, sensitive plaintext, prolonged detailed handshake debug dumps, or full certificate chains containing data unnecessary for monitoring.

## 17. Debugging and identifying handshake failure causes

Common failure groups:

| Symptom | Where to check |
| --- | --- |
| `SSLHandshakeException: no appropriate protocol` | Protocol allowlist, disabled algorithms, client/server versions |
| `no cipher suites in common` / `handshake_failure` | Intersection of suites, TLS version, certificate algorithm, and provider |
| `PKIX path building failed` | Truststore/CA chain, missing intermediate, CA policy, certificate validity |
| `No subject alternative DNS name matching` | SNI/URL host and leaf SAN, endpoint verification |
| ALPN did not select `h2` | Server supported list, client offers, protocol implementations, and negotiation |
| `no_application_protocol` alert | Disjoint ALPN on a peer requiring ALPN and TLS stack raises error |
| TLS succeeds but HTTP/2 fails | ALPN/config lacks an actual HTTP/2 codec, or proxy altered behavior |
| Different behavior after restart | Cached old config in SSLContext/connection pools |
| Missing SNI | Client created socket with IP, omitted host, or proxy/TLS library altered it |
| Valid certificate yet mTLS client rejected | Need/want client auth, client KeyManager, issuer trust, and clientAuth EKU |
| Fails on only one JDK | Differences in provider/version, truststore, disabledAlgorithms, cipher support |

JSSE debugging can be enabled in controlled environments:

```text
-Djavax.net.debug=ssl,handshake,trustmanager
```

This produces large technical logs that may contain hostnames, certificates, and sensitive metadata; collect only when needed and apply log protection policies. **Never** treat every debug line as proof of successful protocol negotiation; verify the actual application and TLS session.

## 18. Practice exercises

### Exercise 1 — Supported vs. enabled

Run `SslParametersDemo` on JDK 17. Print `engine.getSupportedProtocols()` and `engine.getEnabledProtocols()` in an isolated lab and compare them. Are there older protocols that are supported but not enabled? Explain why they must not be re-enabled just to "maximize compatibility."

### Exercise 2 — Separating protocols and cipher suites

Change the allowed TLS versions list to `TLSv1.2` only in the lab, selecting an enabled ECDHE-GCM suite. Configure a TLS 1.3 suite to observe how the configuration cannot be negotiated. Do not use weak suites to force the test to pass.

### Exercise 3 — Two virtual hosts, one IP

Set up two TLS virtual hosts `api.example.test` and `admin.example.test` in the lab. Send the corresponding SNI and observe the certificate. Then request a connection to `api.example.test` while deliberately setting SNI to `admin.example.test`. Prove that endpoint identification still rejects if the certificate does not match the requested hostname.

### Exercise 4 — ALPN and HTTP/2

Use a server supporting both `h2` and `http/1.1`, have the client offer both, and log `getApplicationProtocol()` after the handshake. Switch the server to support only `http/1.1` and test fallback per protocol policy. Why must the application not send HTTP/2 frames before determining the negotiated ALPN?

### Exercise 5 — HTTPS endpoint identity

Create a test CA and certificate with SAN `service.example.test`, and configure a trust manager trusting this CA. Test connections with the matching hostname and another hostname; both may present valid chains, yet only the matching hostname may be accepted. Do not disable hostname checks.

### Exercise 6 — Per-client security policy

A service calls both a public API and a private mTLS endpoint. Design two `SSLContext` instances, appropriate truststores/KeyManagers, and separate `SSLParameters` if needed. Analyze SNI, ALPN, serverAuth/clientAuth, endpoint identity, and authorization for each flow.

### Exercise 7 — Managing a rollout

A system currently allows TLS 1.2 and 1.3 and wants to transition gradually to TLS 1.3 only. Specify the telemetry to collect, client compatibility checks, ALPN/HTTP2, cipher suites, JDK/provider checks, and a rollback plan that **does not violate** security policy.

### Exercise 8 — Handshake state machine

Create a real `SSLEngine` client connecting to a test server over TCP, handling `NEED_WRAP`, `NEED_UNWRAP`, `NEED_TASK`, and `FINISHED` with timeouts. Compare with `SSLSocket` and a high-level HTTP client. If the production goal is standard HTTPS, why prefer a library over writing your own handshake loop?

### Exercise 9 — Comprehensive negative testing

Create a test matrix for: untrusted CA, wrong certificate SAN, EKU `clientAuth` only, no shared TLS version, no shared cipher suite, ALPN `h2` only when server does not support it, wrong SNI, mTLS client without cert, and a connection pool retaining stale policy. Specify which cases fail at TLS and which fail at HTTP or authorization.

**Completion criteria:** you know exactly which values belong in `SSLParameters`, how they are applied to an engine/socket, where the three mechanisms **SNI – ALPN – hostname verification** differ, and why an authenticated TLS channel exists only once a handshake succeeds with full peer verification.

## 19. References

- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setProtocols`, `setCipherSuites`, `setServerNames`, `setApplicationProtocols`, `setEndpointIdentificationAlgorithm`.
- [Java SE 17 — SSLEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html): nonblocking TLS, `getSSLParameters`, `setSSLParameters`, `getApplicationProtocol`.
- [Java SE 17 — SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): TLS socket, `startHandshake`, `getApplicationProtocol`.
- [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): key/trust managers and creating engines/sockets.
- [Java SE 17 — SNIHostName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SNIHostName.html): SNI `host_name` structure.
- [Java SE 17 — SSLSession](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): negotiated TLS version, cipher suite, and peer metadata.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): per-client SSL context, params, and HTTP version.
- [Java 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): configuration/handshake/trust manager/ALPN and endpoint checks.
- [RFC 6066 — TLS Extensions](https://www.rfc-editor.org/rfc/rfc6066): SNI.
- [RFC 7301 — TLS ALPN Extension](https://www.rfc-editor.org/rfc/rfc7301): ALPN negotiation.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake, TLS 1.3 cipher suites, and certificate authentication.
- [RFC 5246 — TLS 1.2](https://www.rfc-editor.org/rfc/rfc5246): TLS 1.2 protocol and cipher suite model.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): matching endpoint identity using certificate identifiers.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS protocol choices, certificates, and operations.
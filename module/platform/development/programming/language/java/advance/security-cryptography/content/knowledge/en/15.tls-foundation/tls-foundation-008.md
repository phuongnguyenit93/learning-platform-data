# 15.8. SNI for Virtual Host Selection and ALPN for Application Protocol Negotiation

**SNI (Server Name Indication)** and **ALPN (Application-Layer Protocol Negotiation)** are two TLS extensions that solve **two independent problems**. SNI tells the server **which hostname the client wants to connect to** right inside the TLS handshake so the server can select the virtual host's configuration and certificate. ALPN lets client and server **negotiate the application protocol** used inside the secure channel, such as HTTP/1.1 or HTTP/2.

Crucially: **SNI does not authenticate client identity or authorize requests**, and **ALPN does not implement HTTP/2 or any application protocol on its own**. They participate in the handshake yet must work alongside certificate selection, hostname/SAN checks, trust-path building, TLS session management, and application protocol handlers. In Java 21, APIs such as `SSLParameters`, `SNIHostName`, `ExtendedSSLSession`, `X509ExtendedKeyManager`, and `SSLSocket` support practicing both mechanisms.

This lesson belongs to **"15. TLS Foundation"** of Java Advanced – Security & Cryptography. The lab uses **TLS 1.3 and Java 21**, building a loopback TLS server with two virtual hosts, selecting certificates via SNI and negotiating ALPN, while explaining why a successful TLS connection does not mean every identity and protocol layer has been handled safely.

## Learning objectives

After completing this lesson, you can:

1. Explain where SNI resides in `ClientHello`, how it helps select a **virtual host/certificate**, and why it is needed before HTTP `Host` or HTTP/2 `:authority`.
2. Explain ALPN: the client **offers a list** of application protocol IDs, and the server **selects one offered and supported value**, or the handshake fails to agree on an eligible protocol.
3. Distinguish **TLS protocol version** (e.g., `TLSv1.3`), **cipher suite**, **SNI server name**, **ALPN application protocol**, and **HTTP `Host`/`:authority`**.
4. Use `SSLParameters.setServerNames`, `SNIHostName`, `ExtendedSSLSession.getRequestedServerNames`, `SSLParameters.setApplicationProtocols`, and `SSLSocket.getApplicationProtocol` in Java 21.
5. Explain `X509ExtendedKeyManager.chooseServerAlias`/`chooseEngineServerAlias` and the conditions required to select the right certificate by hostname, key type, and trust policy.
6. Create/trust certificates for two hosts in a lab, enable HTTPS-style **endpoint identification**, compare SANs, and observe TLS handshake results.
7. Handle missing or unrecognized SNI, wrong certificate hostname, no common ALPN protocol, and handlers lacking support for the chosen value—without insecure fallbacks.
8. Recognize TLS termination issues at reverse proxies, domain privacy, logging, testing, and the difference between **successful negotiation** and **actually sending HTTP**.

## 1. Two extensions solving two different decision layers

Suppose an IP/port `203.0.113.10:443` serves two domains:

- `blue.example.test` — certificate carries a DNS SAN for `blue.example.test`.
- `green.example.test` — certificate carries a DNS SAN for `green.example.test`.

The client connects to the same IP yet expects the **right domain**, and may speak **HTTP/1.1** or **HTTP/2**. Before TLS is established, the server must choose the right certificate; before sending application data, both sides must know which application protocol they speak together.

```text
Client                                            TLS server :443
------                                            ---------------
ClientHello
  supported_versions = TLS 1.3
  server_name (SNI) = blue.example.test  --------> select virtual host blue
  ALPN = [http/1.1, demo/1]                        select certificate blue
  ...                                              select ALPN http/1.1
             <------- ServerHello / TLS handshake / certificate blue
Client checks chain + blue hostname certificate
             <------- handshake completes (TLS authenticated)
getApplicationProtocol() = "http/1.1"
             <------- application records per selected protocol
```

This is a **logical diagram**, not an exact byte-order representation of TLS 1.3. In TLS 1.3, the server's ALPN selection appears inside `EncryptedExtensions`, while the certificate and `Finished` arrive in their respective handshake messages. Never read the diagram as implying ALPN is sent inside TLS 1.3 `ServerHello`.

| Question | **SNI** | **ALPN** |
| --- | --- | --- |
| Goal | *Which server on this IP/port?* | *Which application protocol runs inside this TLS channel?* |
| Who offers? | Client provides a server name, typically a DNS hostname | Client provides a **list** of supported protocol IDs |
| Who decides? | Server/terminator maps hostname → config/certificate/backend | Server picks one application protocol offered by client and supported by server |
| Example | `blue.example.test` | `http/1.1`, `h2` |
| Associated with | Virtual hosts, certificate selection, virtual routing | HTTP/1.1, HTTP/2, application protocols over TLS |
| Not | Hostname verification, client authentication, authorization | TLS version, cipher suite, application execution framework |
| Java API | `SNIHostName`, `setServerNames`, `getRequestedServerNames`, key manager | `setApplicationProtocols`, `getApplicationProtocol`, protocol selector |

**Memory aid:** SNI decides **which host to talk to**; ALPN decides **which application-protocol language to speak**. Both are handshake coordination data and **do not replace certificate checks or channel security**.

## 2. SNI: why does HTTP `Host` arrive too late?

In standard HTTPS, the sequence is:

1. Client opens a TCP connection to an IP and port.
2. TLS handshake starts; the server must **present a certificate** and prove possession of the matching private key.
3. Client checks the certificate chain, hostname, and handshake.
4. Only afterward is the HTTP request sent over TLS.

HTTP/1.1 `Host` and HTTP/2 `:authority` sit in the **HTTP layer**, at step 4. The server cannot wait to receive `Host` inside an HTTP message **before completing TLS** to learn which certificate to present at step 2. That is why SNI is placed inside `ClientHello`.

### 2.1 Virtual hosting: one IP, multiple certificates

```text
                  DNS
                  |
      blue.example.test ---\
                            -> IP:443 -> TLS ingress/virtual hosts
      green.example.test --/                    |
                                         SNI=blue?  -> key+cert blue
                                         SNI=green? -> key+cert green
                                         unknown?   -> reject/default per policy
```

A server can use SNI to:

- Select the **key pair + certificate chain** matching the hostname.
- Select TLS policy (such as certificates/algorithms or mTLS requirements per virtual host).
- Select tenant, listener, virtual server, or forward through a TLS proxy/ingress per design.
- Record hostname-level telemetry (under separate policies for sensitive info).

Having SNI does not mean the server must swap certificates every time. A **SAN certificate** can hold multiple DNS names, or a policy-compliant wildcard can cover multiple names. SNI is strictly a selection hint; **certificate validity is checked separately by the client**.

### 2.2 SNI is a client hint, not an authenticated identity

A client can put any hostname into SNI; a malicious client can send a nonexistent name, another tenant's name, or omit the extension entirely. Therefore:

- **Never** treat "client sent `SNI=admin.example.test`" as proof the client belongs to an admin group.
- **Never** skip application authorization merely because the TLS terminator picked the right virtual host.
- Never grant permissions based on SNI without independent authentication controls.
- If SNI is invalid/unsupported, explicitly design **reject**, default certificate, or default tenant behavior. Never silently route a sensitive tenant to another tenant.
- Cross-check SNI against HTTP `Host`/`:authority` per proxy policy to prevent hostname/tenant confusion, request smuggling, and misrouting.

### 2.3 What happens when a client omits SNI?

Common reasons: client connects directly by IP address, an older client lacks SNI support, or the app omitted `setServerNames`. The server may choose a default certificate, reject, or route differently depending on config; **there is no single universal behavior**.

If the server picks the `blue.example.test` certificate while the client expects `green.example.test`, a client with HTTPS-style hostname verification enabled **must reject** the mismatched certificate, even if the CA chain is valid. That the server "managed to send a certificate" does not mean the client must trust it.

### 2.4 Practical hostname rules

- SNI `host_name` uses a TLS-compatible DNS name, **without `https://` scheme, `:443` port, URL path, or tokens**.
- `SNIHostName` handles DNS names and ASCII/encoding per Java API; applications must enforce hostname conventions, IDN/Punycode, and input normalization.
- An IP address is not a normal DNS hostname for the `host_name` extension; clients connecting by IP should verify an IP SAN per policy rather than inventing a fake DNS SNI.
- Certificate identity verification must inspect **DNS SAN or IP SAN** per application/protocol, not merely check whether Subject CN looks similar.
- Wildcards and internationalized hostnames must follow standard verification rules rather than hand-rolled `String.endsWith` checks standing in for a TLS hostname verifier.

### 2.5 Is SNI "encrypted"?

In standard TLS, the SNI name in `ClientHello` is typically **observable** by on-path network devices; HTTPS encrypting application payloads does not hide the server name by default. **Encrypted ClientHello (ECH)** can protect the real hostname inside `ClientHello` in supporting implementations, though you should never assume every JDK/client/server has deployed ECH or enabled it. Nor is ALPN an anonymity mechanism. Avoid embedding private identifiers in virtual host names or logging SNI uncontrollably.

## 3. ALPN: negotiating which protocol runs inside TLS

**ALPN** per RFC 7301 lets the client advertise identifiers of **application protocols** it supports. The server selects **one** matching identifier; this choice commits both sides to speaking that protocol over the authenticated connection.

Example client offer:

```text
ALPN offered by client = ["demo/1", "http/1.1"]
Server supports        = ["http/1.1", "demo/1"]
Selected               = "http/1.1"
```

In our lab, the server lists `http/1.1` first in preference order, so `http/1.1` is chosen. The value `demo/1` is a protocol ID used solely to **demonstrate negotiation**, **not** a real application standard implemented in the lesson.

Common values:

- `http/1.1`: HTTP/1.1 over TLS.
- `h2`: HTTP/2 over TLS, requiring an endpoint with real HTTP/2 framing, HPACK, multiplexing, and protocol compliance.
- `h3`: HTTP/3 over QUIC (not "HTTP/3 on a TCP `SSLSocket`"); QUIC integrates the TLS handshake differently from the JSSE sockets demonstrated here.
- Other specialized protocol IDs defined by protocols/profiles; never falsely advertise an ID registered for a protocol the server does not actually implement.

**Do not conflate:** `TLSv1.3` is a channel-protection protocol version; `TLS_AES_128_GCM_SHA256` is a TLS 1.3 cipher suite; `http/1.1` is an application protocol via ALPN. Calling `setApplicationProtocols(new String[]{"TLSv1.3"})` will not negotiate the TLS version.

### 3.1 How does the server choose?

- The client advertises protocol IDs **it actually speaks**.
- The server picks only an ID present in the client's list **and** genuinely supported by the server.
- If client and server share no common protocol and ALPN is required to pick one, RFC 7301 requires the server to terminate with a **`no_application_protocol`** alert. Never secretly pick an unadvertised protocol.
- Once chosen, endpoints **must actually use** the negotiated protocol ID; never reply `h2` and then transmit HTTP/1.1.
- If the handshake **negotiated no ALPN**, `getApplicationProtocol()` may be an empty string. Applications need an explicit policy on when legacy fallback is permitted vs. fail-closed.

"If ALPN fails, silently drop to HTTP/1.1" is not always safe. For servers requiring HTTP/2 or a dedicated application protocol, **missing or wrong ALPN must be rejected** per profile.

### 3.2 ALPN does not turn a socket into HTTP/2

`SSLSocket.getApplicationProtocol()` only returns the value negotiated by TLS. Code that sends/receives HTTP/1.1, HTTP/2, or another application protocol must be executed by the framework or application **after** the handshake. Our lab only opens TLS and inspects the ALPN result **without sending any HTTP request**; therefore it must never be called a "real HTTP server".

With Java `HttpClient`, servers like Netty/Jetty, or JSSE-based frameworks, ALPN is normally managed by the integrated HTTP/TLS stack. You do not need to write custom TLS sockets in production just to use ALPN.

## 4. Connecting SNI – certificate – ALPN – HTTP routing

A multi-tenant architecture:

```text
TLS ClientHello
  SNI = blue.example.test
  ALPN offered = [http/1.1, demo/1]
           |
           v
TLS terminator / ingress
  1. Map SNI → vhost blue
  2. Select blue's key + certificate chain
  3. Select ALPN application protocol http/1.1
  4. Complete TLS handshake
           |
           v
Client verifies certificate chain + hostname blue
           |
           v
Application handler for http/1.1 (if implemented)
           |
           v
HTTP Host + route + tenant + authentication/authorization
```

Each step has its own scope:

| Step | Data source | Decision | If verification is skipped |
| --- | --- | --- | --- |
| SNI | `ClientHello` hostname | Selects certificate/vhost | Wrong certificate presented or wrong tenant routed |
| TLS certificate | Certificate presented by server | Which root does client trust, does cert match hostname? | MITM/server impersonation if trust/hostname checks are dropped |
| ALPN | Client app list + server policy | Selects right handler/protocol | HTTP/1.1 vs. HTTP/2 framing mismatch, errors, or protocol confusion |
| HTTP `Host`/`:authority` | HTTP message inside TLS | Routes request to virtual service | Domain fronting, mismatch, or tenant confusion if trusted blindly |
| Authentication | Client credentials, mTLS, session/token | Who is the caller? | SNI does not prove user identity |
| Authorization | Application policy | What may the caller do? | TLS handshake succeeds yet unauthorized actions execute |

### 4.1 Where does TLS terminate?

At a reverse proxy, ingress, or load balancer, models include:

- **Edge TLS termination:** the edge receives SNI, picks the certificate, negotiates ALPN, and decrypts HTTP; the edge-to-backend link is a **separate hop**, needing its own TLS, trust, header, and identity policies.
- **TLS passthrough:** the proxy does not decrypt handshakes/HTTP and may route by SNI observed in `ClientHello` if configured; the backend still presents certificates and performs the TLS handshake.
- **TLS re-encryption:** the edge terminates TLS and opens a new TLS connection to the backend with **new SNI/ALPN** for the backend hop; never assume identical names, certs, or client identities across both hops.

Never treat client-supplied HTTP `X-Forwarded-Host` or `Host` as tenant authentication without a reverse proxy policy stripping/overwriting untrusted headers. HTTPS authentication on the client-edge hop does not automatically provide end-to-end TLS to the backend.

### 4.2 Certificate selection precedes server identity verification

The server reads SNI to pick a certificate. The client **must never** take the name from the server's returned certificate and swap it in as the target name to verify. The target name must come from the URI/target/endpoint the client **intends** to reach; SNI is normally sent using that same name. If the server swaps in a valid certificate for a different domain, hostname verification must fail.

## 5. Java 21 APIs: where do SNI and ALPN live?

| API | Which side? | Role |
| --- | --- | --- |
| `SSLParameters.setServerNames(List<SNIServerName>)` | Client | Sets the SNI extension for the handshake |
| `new SNIHostName("blue.example.test")` | Client | Wraps a DNS hostname as SNI |
| `ExtendedSSLSession.getRequestedServerNames()` | Server | Reads SNI names requested by client from handshake/session |
| `X509ExtendedKeyManager.chooseServerAlias(...)` | Server with `SSLSocket` | Picks alias/cert matching key type, issuers, and SNI |
| `X509ExtendedKeyManager.chooseEngineServerAlias(...)` | Server with `SSLEngine` | Same as above, for NIO/framework engines |
| `SSLParameters.setSNIMatchers(...)` | Server | Can constrain accepted SNI names; does not replace key/cert routing |
| `SSLParameters.setApplicationProtocols(String[])` | Client and server | Sets list of supported ALPN IDs (usually in preference order) |
| `SSLSocket.getApplicationProtocol()` | Both sides, post-handshake | Returns negotiated ID, `""` if ALPN unused, `null` if undetermined |
| `SSLSocket.getHandshakeApplicationProtocol()` | During handshake | Inspects ALPN value currently negotiated if available |
| `SSLSocket.setHandshakeApplicationProtocolSelector(...)` | Server | Callback selecting an ID from the client's offered list |
| Corresponding `SSLEngine` methods | Non-blocking frameworks | Equivalent SNI/ALPN/handshake APIs |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Client | Requests server identity verification via the `HTTPS` endpoint algorithm |
| `TrustManagerFactory` / `KeyManagerFactory` | Client/server | Provides valid trust anchors and private keys/certificate chains |

### 5.1 SNI domain set by the client

Illustrative snippet (**non-standalone**, assuming `SSLSocket socket` is already created):

```java
SSLParameters p = socket.getSSLParameters();
p.setServerNames(List.of(new SNIHostName("blue.example.test")));
p.setApplicationProtocols(new String[] {"http/1.1"});
p.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(p);
socket.startHandshake();
String protocol = socket.getApplicationProtocol();
```

In production, the client must supply a valid truststore/trust manager, use a trusted target hostname, keep endpoint identification enabled, and advertise only ALPN IDs it can actually implement.

### 5.2 Server reading SNI during handshake

Inside `X509ExtendedKeyManager.chooseServerAlias`, you can read `((SSLSocket) socket).getHandshakeSession()` and, if it is an `ExtendedSSLSession`, call `getRequestedServerNames()`. Certificate selection must still satisfy **keyType, issuers, key algorithms, and provider policy**. Never blindly pick an alias solely because the hostname matches while ignoring cryptographic constraints.

With `SSLEngine`, there is no `Socket` for reading SNI; override `chooseEngineServerAlias` and inspect `engine.getHandshakeSession()`. A key manager overriding only `chooseServerAlias` can **fail to work properly** when frameworks use `SSLEngine`.

### 5.3 Explicit ALPN selector

**Illustrative** snippet inside a server loop before `startHandshake()`:

```java
connection.setHandshakeApplicationProtocolSelector((socket, offered) ->
        offered.contains("http/1.1") ? "http/1.1" : null);
```

Here `offered` is the ALPN list advertised by the client; returning `null` signals no ID could be selected. In ALPN, the provider may terminate the connection with a `no_application_protocol` alert. A selector can override static `setApplicationProtocols` lists, so **never** return a value absent from the client's list if you want to avoid handshake failure. In real applications, selector logic must reflect actual capabilities and policy, not "pick a value to look nice in logs".

Our lab uses `setApplicationProtocols` on both sides to illustrate preference order; it does not use a custom callback in the main program.

## 6. Java 21 hands-on: two virtual hosts, two certificates, one TLS listener

We will build a **loopback TLS server** requiring no Internet access, with two certificates signed by the same lab CA:

```text
server.p12:
  lab-ca    : private key + CA certificate          (lab convenience only)
  blue      : private key + leaf SAN blue.example.test + CA chain
  green     : private key + leaf SAN green.example.test + CA chain

trust.p12:
  lab-ca    : TrustedCertificateEntry (public certificate only)
```

In real systems, you must **separate the CA private key** from the application server and protect it with a proper PKI/HSM/offline CA. Keeping the CA key inside `server.p12` is strictly for quickly generating certificates in a temporary directory. Never deploy lab files to production.

The client does not use a trust-all default; instead, `TrustManagerFactory` trusts **only the intentionally imported lab CA**. The client enables `"HTTPS"` endpoint identification and also compares the DNS SAN for readable output. The server wraps `SunX509` in an `X509ExtendedKeyManager` that selects alias **`blue` or `green`** by SNI.

### 6.1 Prepare JDK and lab password

Use JDK 21 or newer supporting `--release 21` and standard SunJSSE/SunJCE providers. Create a dedicated lab directory and open a terminal there.

**PowerShell:**

```powershell
$env:TLS_DEMO_PASS = 'LabOnly-SniAlpn42'
```

**Bash:**

```bash
export TLS_DEMO_PASS='LabOnly-SniAlpn42'
```

This is a **public example password**, not a secret suitable for real environments. `keytool` reads the password via `-storepass:env TLS_DEMO_PASS`, avoiding placing the **literal value** directly on the command line. Environment variables still risk exposure via process environments or logs and do not replace a secret manager.

### 6.2 Create a CA solely to sign the two test certificates

Run on one line:

```text
keytool -genkeypair -alias lab-ca -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Local Lab CA,O=Training,C=VN" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -validity 20 -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS -keypass:env TLS_DEMO_PASS -noprompt
```

The CA has `BasicConstraints CA:TRUE, pathLen:0`, used to sign leaves directly. This is a **self-signed test CA**, untrusted by public systems.

### 6.3 Create two virtual host certificates with separate DNS SANs

```text
keytool -genkeypair -alias blue -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=blue.example.test,O=Training,C=VN" -ext "SAN=dns:blue.example.test" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -signer lab-ca -signerkeypass:env TLS_DEMO_PASS -validity 12 -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS -keypass:env TLS_DEMO_PASS -noprompt
keytool -genkeypair -alias green -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=green.example.test,O=Training,C=VN" -ext "SAN=dns:green.example.test" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -signer lab-ca -signerkeypass:env TLS_DEMO_PASS -validity 12 -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS -keypass:env TLS_DEMO_PASS -noprompt
```

With `-signer lab-ca`, `keytool` generates each leaf signed by the lab CA and stores the chain in the same PKCS12 file. Aliases `blue` and `green` are **internal entry names**, distinct from DNS hostnames. In the example, the key manager maps DNS names to fixed aliases; this mapping is determined by application/tenant configuration.

### 6.4 Export the public CA certificate and create the client truststore

```text
keytool -exportcert -rfc -alias lab-ca -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS -file ca.pem
keytool -importcert -alias lab-ca -file ca.pem -keystore trust.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS -noprompt
```

`trust.p12` holds a `TrustedCertificateEntry` for the lab CA, without the CA private key. Importing it is an **intentional trust decision** strictly for this lab. Never import this CA into the system truststore or JDK `cacerts` used by real applications.

Inspect the structure:

```text
keytool -list -v -alias blue -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS
keytool -list -v -alias green -keystore server.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS
keytool -list -v -alias lab-ca -keystore trust.p12 -storetype PKCS12 -storepass:env TLS_DEMO_PASS
```

Both `blue` and `green` aliases are `PrivateKeyEntry` entries containing their respective leaf and chain; the CA in the truststore is a `trustedCertEntry` (exact label casing depends on JDK). Read metadata only—never export the private key.

## 7. Complete runnable program `SniAlpnDemo.java`

The example uses **TLSv1.3** and `SSLServerSocket` accepting two loopback connections. The client's socket physically connects to loopback, while `createSocket(tcp, name, port, true)` sets the **logical peer hostname** to `blue.example.test` or `green.example.test`. This lets us test hostname verification **without editing DNS or the hosts file** on the machine.

What you will observe:

- SNI `blue.example.test` → `SniKeyManager` selects alias `blue` → blue SAN certificate.
- SNI `green.example.test` → alias `green` → green SAN certificate.
- Client offers `demo/1` before `http/1.1`; server orders `http/1.1` before `demo/1`. The selected value is `http/1.1` on the tested SunJSSE provider.
- Client uses `setEndpointIdentificationAlgorithm("HTTPS")` and the lab CA truststore; if SAN/certificate mismatches, the handshake will not succeed.
- Server reads SNI via `ExtendedSSLSession` **after** the handshake and prints both received names.
- Server sends no HTTP; the ALPN result proves only **protocol-name negotiation**, not an HTTP implementation.

Create **`SniAlpnDemo.java`** (public class name must match filename):

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.Principal;
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import javax.net.ssl.ExtendedSSLSession;
import javax.net.ssl.KeyManager;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SNIHostName;
import javax.net.ssl.SNIServerName;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509ExtendedKeyManager;

public class SniAlpnDemo {
    static final class SniKeyManager extends X509ExtendedKeyManager {
        private final X509ExtendedKeyManager base;
        SniKeyManager(X509ExtendedKeyManager base) { this.base = base; }

        private String aliasFor(List<SNIServerName> requested) {
            for (SNIServerName name : requested) {
                if (name instanceof SNIHostName host) {
                    if ("blue.example.test".equalsIgnoreCase(host.getAsciiName())) return "blue";
                    if ("green.example.test".equalsIgnoreCase(host.getAsciiName())) return "green";
                }
            }
            return null;
        }
        private String selected(String keyType, Principal[] issuers,
                                List<SNIServerName> requested) {
            String required = aliasFor(requested);
            if (required == null) return null; // Do not silently use another cert.
            String[] compatible = base.getServerAliases(keyType, issuers);
            if (compatible == null) return null;
            for (String candidate : compatible) {
                if (candidate.equalsIgnoreCase(required)) return candidate;
            }
            return null;
        }
        @Override public String chooseServerAlias(String type,
                        Principal[] issuers, Socket socket) {
            if (!(socket instanceof SSLSocket ssl)) return null;
            if (!(ssl.getHandshakeSession() instanceof ExtendedSSLSession session))
                return null;
            return selected(type, issuers, session.getRequestedServerNames());
        }
        @Override public String chooseEngineServerAlias(String type,
                        Principal[] issuers, SSLEngine engine) {
            if (!(engine.getHandshakeSession() instanceof ExtendedSSLSession session))
                return null;
            return selected(type, issuers, session.getRequestedServerNames());
        }
        @Override public String[] getClientAliases(String type, Principal[] issuers) {
            return base.getClientAliases(type, issuers);
        }
        @Override public String chooseClientAlias(String[] types,
                        Principal[] issuers, Socket socket) {
            return base.chooseClientAlias(types, issuers, socket);
        }
        @Override public String chooseEngineClientAlias(String[] types,
                        Principal[] issuers, SSLEngine engine) {
            return base.chooseEngineClientAlias(types, issuers, engine);
        }
        @Override public String[] getServerAliases(String type, Principal[] issuers) {
            return base.getServerAliases(type, issuers);
        }
        @Override public X509Certificate[] getCertificateChain(String alias) {
            return base.getCertificateChain(alias);
        }
        @Override public PrivateKey getPrivateKey(String alias) {
            return base.getPrivateKey(alias);
        }
    }

    static KeyStore load(Path path, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream stream = Files.newInputStream(path)) {
            store.load(stream, password);
        }
        return store;
    }

    static SSLContext serverContext(KeyStore identity, char[] password)
            throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance("SunX509");
        kmf.init(identity, password);
        X509ExtendedKeyManager delegate = null;
        for (KeyManager manager : kmf.getKeyManagers()) {
            if (manager instanceof X509ExtendedKeyManager extended) {
                delegate = extended;
                break;
            }
        }
        if (delegate == null) throw new IllegalStateException("No X509 key manager");
        SSLContext context = SSLContext.getInstance("TLSv1.3");
        context.init(new KeyManager[]{new SniKeyManager(delegate)},
                     null, new SecureRandom());
        return context;
    }

    static SSLContext clientContext(KeyStore anchors) throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(anchors);
        SSLContext context = SSLContext.getInstance("TLSv1.3");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    static String requestedHost(SSLSocket socket) {
        if (socket.getSession() instanceof ExtendedSSLSession session) {
            for (SNIServerName n : session.getRequestedServerNames()) {
                if (n instanceof SNIHostName host) return host.getAsciiName();
            }
        }
        return "(missing)";
    }

    static boolean sanMatches(X509Certificate leaf, String name)
            throws Exception {
        Collection<List<?>> sans = leaf.getSubjectAlternativeNames();
        if (sans == null) return false;
        for (List<?> san : sans) {
            if (Integer.valueOf(2).equals(san.get(0))
                    && name.equalsIgnoreCase((String) san.get(1))) return true;
        }
        return false;
    }

    static void connect(SSLContext context, int port, String name)
            throws Exception {
        try (Socket tcp = new Socket(InetAddress.getLoopbackAddress(), port);
             SSLSocket tls = (SSLSocket) context.getSocketFactory()
                     .createSocket(tcp, name, port, true)) {
            SSLParameters parameters = tls.getSSLParameters();
            parameters.setProtocols(new String[]{"TLSv1.3"});
            parameters.setServerNames(List.of(new SNIHostName(name)));
            parameters.setApplicationProtocols(
                    new String[]{"demo/1", "http/1.1"});
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            tls.setSSLParameters(parameters);
            tls.startHandshake();
            X509Certificate cert =
                    (X509Certificate) tls.getSession().getPeerCertificates()[0];
            System.out.println(name + ": ALPN=" + tls.getApplicationProtocol()
                    + ", certificate SAN matches=" + sanMatches(cert, name));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException(
                "Usage: java SniAlpnDemo server.p12 trust.p12");
        String env = System.getenv("TLS_DEMO_PASS");
        if (env == null) throw new IllegalStateException("Missing TLS_DEMO_PASS");
        char[] password = env.toCharArray();
        try {
            SSLContext serverCtx = serverContext(load(Path.of(args[0]), password),
                                                 password);
            SSLContext clientCtx = clientContext(load(Path.of(args[1]), password));
            String[] seen = new String[2];
            AtomicReference<Throwable> failure = new AtomicReference<>();
            try (SSLServerSocket listener = (SSLServerSocket)
                    serverCtx.getServerSocketFactory().createServerSocket(
                            0, 2, InetAddress.getLoopbackAddress())) {
                Thread server = new Thread(() -> {
                    try {
                        for (int i = 0; i < 2; i++) {
                            try (SSLSocket connection = (SSLSocket) listener.accept()) {
                                SSLParameters p = connection.getSSLParameters();
                                p.setProtocols(new String[]{"TLSv1.3"});
                                p.setApplicationProtocols(
                                        new String[]{"http/1.1", "demo/1"});
                                connection.setSSLParameters(p);
                                connection.startHandshake();
                                seen[i] = requestedHost(connection);
                            }
                        }
                    } catch (Throwable t) {
                        failure.set(t);
                    }
                });
                server.start();
                connect(clientCtx, listener.getLocalPort(), "blue.example.test");
                connect(clientCtx, listener.getLocalPort(), "green.example.test");
                server.join();
                if (failure.get() != null) throw new Exception(failure.get());
                System.out.println("server SNI: " + String.join(", ", seen));
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

### 7.1 Compile and run

Once `server.p12`, `trust.p12`, and `SniAlpnDemo.java` are in the current directory:

```text
javac --release 21 -encoding UTF-8 SniAlpnDemo.java
java SniAlpnDemo server.p12 trust.p12
```

**Verified stdout:**

```text
blue.example.test: ALPN=http/1.1, certificate SAN matches=true
green.example.test: ALPN=http/1.1, certificate SAN matches=true
server SNI: blue.example.test, green.example.test
```

The fixtures were created, compiled with `javac --release 21`, and executed successfully with the bundled JDK JSSE. Certificates, serial numbers, private keys, TLS sessions, and session secrets change across runs, while the expected boolean/ALPN lines remain as shown under the same configuration. If an environment uses a provider other than `SunX509` or lacks algorithm support, the API may throw an error; see troubleshooting.

### 7.2 Why use `createSocket(tcp, name, port, true)`?

The physical TCP connection goes to `InetAddress.getLoopbackAddress()` on an ephemeral server port. The logical peer name `blue.example.test` serves as the **target hostname for TLS endpoint identification**. Adding `new SNIHostName(name)` makes the SNI hostname explicit even while connecting to loopback. This avoids configuring fake DNS/hosts entries, yet **must not** be taken as advice to skip DNS and invent hostnames in production: target names must come from trusted configuration.

### 7.3 Why must `SniKeyManager` also check `keyType`?

In JSSE, server certificate selection is constrained by scheme/key type, provider, issuer constraints, and signatures supported by both sides. Picking an alias matching the hostname whose key algorithm is **incompatible** can still fail the TLS handshake or violate policy. The wrapper calls `base.getServerAliases(keyType, issuers)` and returns the alias only if it appears in the compatible list.

This wrapper is **for the lab**, not a complete production certificate selector: it lacks hot reload, wildcard matching, IDN rules, fallback policies, tenant permissions, chain expiration/rotation, logging/monitoring, caching, or cross-provider testing. In production, prefer maintained TLS server/framework capabilities, properly configured key managers, and thorough testing.

### 7.4 Why can the server still read SNI after the TLS handshake?

`ExtendedSSLSession.getRequestedServerNames()` exposes the received SNI names. Inside `chooseServerAlias`/`chooseEngineServerAlias`, the code reads from the **handshake session** because certificate selection must happen *before* the handshake finishes. After the handshake, the demo's `requestedHost` helper reads the established session merely for logging.

If SNI is absent or unmapped, the wrapper returns `null` rather than picking another tenant's certificate. The provider may try other key types; if no compatible alias exists, the handshake is rejected. A deployment with an explicit default-certificate policy may behave differently, yet must preserve hostname verification and tenant isolation.

### 7.5 Why does `getApplicationProtocol()` return `http/1.1`?

The client set ALPN list `["demo/1","http/1.1"]`; the server set `["http/1.1","demo/1"]`. With SunJSSE in the lab, the server picks `http/1.1` per server preference. **ALPN does not inspect SNI to decide HTTP routing**; it is protocol-ID negotiation independent of virtual host selection.

The value `"http/1.1"` **does not mean the program served HTTP/1.1**. The lab has no HTTP parser or response; both sockets simply complete the TLS handshake and close. A real application must dispatch to the corresponding **protocol handler**. For HTTP/2, the handler must implement framing/multiplexing and profile-specific HTTP/2 TLS constraints.

### 7.6 Why is hostname verification still needed when trusting the lab CA?

`TrustManagerFactory` with `trust.p12` tells the client **which CA is trusted**. From there, JSSE can verify the chain presented by the server. However, that CA can sign certificates for both `blue` and `green`, so **hostname verification** must still confirm the certificate belongs to the **exact DNS name the client expects**.

`setEndpointIdentificationAlgorithm("HTTPS")` enforces appropriate identity checking against the peer hostname. Our `sanMatches` helper that manually checks DNS SANs to print a boolean is purely for learner visibility and **does not replace** standard hostname verification (wildcards, IDN, IPs, and other rules belong to standard TLS clients).

## 8. What happens when SNI or ALPN is misconfigured?

| Scenario | Typical consequence | Proper handling |
| --- | --- | --- |
| Client omits SNI | Server picks default or rejects per policy; may pick cert mismatched to target name | Design explicit default/fail-closed behavior; enable client hostname verification |
| SNI is `red.example.test`, server has only blue/green | No matching alias/cert in demo; handshake can fail | Never silently route to another tenant; fail handshake cleanly |
| SNI sends `blue`, client intends `green` | `blue` certificate mismatches peer hostname `green` | Verify hostname from target, not from presented certificate |
| Chain hits right root, SAN mismatches | PKIX trust passes yet endpoint auth fails | Enable `HTTPS` endpoint identification |
| Client offers only `h2`, server supports only `http/1.1` | No shared ALPN protocol, typically fatal `no_application_protocol` | Select only shared IDs; reject when profile requires it |
| ALPN ID is `h2`, server has only an HTTP/1.1 handler | Breaks application framing and rules | Advertise only implemented and tested protocols |
| ALPN not negotiated, `getApplicationProtocol()==""` | No protocol ID selected via ALPN | Allow fallback **only if** profile permits; otherwise reject |
| Spoofed HTTP `Host` differs from SNI | Risk of cross-tenant/misdirected requests under blind routing | Bind SNI, endpoint, HTTP authority, and tenant policy |
| Java provider lacks ALPN/SNI APIs or behaves differently | `UnsupportedOperationException`, handshake error, or different choice | Verify runtime/provider and supported capabilities |
| Worked initially, cert reload/key rotation out of sync | New connections get stale/wrong chain or broken SNI mapping | Atomic update process, test per hostname, support rollback |
| Proxy terminates TLS, backend expects same SNI | Backend sees a new TLS connection with different peer host/suite | Define trust and routing per TLS hop |
| SSL server failed to load right private key/cert alias | Cannot pick compatible certificate | Check `KeyStore` alias/type, key password, chain, and key manager |
| Using IP address when client expects a domain | Cannot rely on default DNS SNI; IP SAN certs follow different rules | Use trusted target hostname or design explicit IP identity |

### 8.1 Principle of no insecure fallback

In a multi-tenant system, if `SNI=tenant-b` cannot find a `tenant-b` certificate, **never pick** `tenant-a` and skip certificate name checks. If ALPN demands `h2` while the server only implements HTTP/1.1, **never reply `h2`** and send HTTP/1.1 bytes. If hostname verification fails, **never install a trust-all manager** to test and leave it in production.

Security mechanisms must **fail closed** per policy. Exceptions are acceptable only under an explicit design, such as an approved default certificate for a permitted legacy domain, with clear scope and testing.

## 9. Distinguishing SNI/ALPN from other TLS functions

### 9.1 SNI is not a certificate, and a certificate is not SNI

SNI is merely **the name the client asks for**. A certificate attests a **public key bound to DNS names / IP SANs and signed by a CA**. The client must verify the path to a trust anchor and verify the name matches the target.

Clients can change SNI arbitrarily; never substitute SNI for client certificates or JWTs/sessions. Conversely, one certificate can serve multiple SNI values (multi-domain SAN or wildcard), so it does not require a one-to-one alias/host mapping.

### 9.2 ALPN is not TLS cipher negotiation

TLS cipher suites define record-protection encryption/authentication algorithms; ALPN selects the **application** running inside those records. TLS 1.3 and HTTP/2 live at different layers. A server can support TLS 1.3 yet speak only HTTP/1.1, or negotiate HTTP/2 over TLS 1.3 when it has the right handler and profile.

### 9.3 ALPN is not HTTP URL routing

`ALPN=http/1.1` indicates the post-handshake byte stream follows HTTP/1.1; selecting a specific service (`/api/v1`) still depends on HTTP routing and authorization. `SNI=blue.example.test` may select a virtual host, yet does not replace parsing HTTP `Host`/`:authority` and enforcing application permissions.

### 9.4 ECH, session resumption, and HTTP/2 connection reuse

When assessing real systems:

- **ECH** can conceal the real SNI hostname; check deployment and client/server support rather than relying on cleartext SNI for identity/policy decisions in every environment.
- **TLS session resumption/PSK** has constraints around virtual hosts and application protocols; never assume every resumed connection repeats a full certificate exchange.
- **HTTP/2** multiplexes multiple requests/streams and has coalescing/origin rules; servers must validate authority and certificates properly rather than relying solely on the first handshake's SNI.
- With multi-tenant reverse proxies, test consistency across original target, SNI, certificate, ALPN, `Host`/`:authority`, and upstream destination across reuse and reconnects.

These are **protocol and deployment design** concerns; they cannot be deduced from a single `SSLSession.getProtocol()` value or an SNI log line alone.

## 10. Debugging and observing in Java environments

When `curl` succeeds yet Java throws `SSLHandshakeException`, categorize systematically:

1. **DNS/peer host:** is the client connecting to the right target? Did layered sockets pass the right peer hostname for endpoint identification?
2. **SNI:** did the client send a valid `SNIHostName`? Did the server receive it and select the right key alias/cert?
3. **Certificates:** is the root/intermediate chain complete, does the truststore contain the valid trust anchor, does the leaf SAN match hostname, and are validity/algorithms/key usage compliant?
4. **ALPN:** which IDs did the client offer? Which did the server support/pick? Does the app handler implement the chosen protocol?
5. **TLS policy:** is there a common TLS version/cipher suite? Does mTLS require a client certificate?
6. **Proxy:** does TLS terminate at the edge or backend? Are there two separate TLS hops?
7. **Runtime:** do the Java version, provider, and key manager support SNI/ALPN as expected?

For lab debugging, JSSE provides `javax.net.debug` flags; enable them only **in isolated test environments**, e.g.:

```text
java -Djavax.net.debug=ssl,handshake -cp . SniAlpnDemo server.p12 trust.p12
```

Handshake logs can be very verbose and contain sensitive metadata (hostnames, certificate chains, configuration details), so **never enable broadly in production** and never copy logs containing secrets to public places. Debugging is only to identify handshake extensions/branches, never to weaken trust policy.

When external tools are needed in an environment you are **authorized to test**, `openssl s_client` with `-servername` and `-alpn` can inspect SNI/ALPN against a live server. In our lab, the listener binds an ephemeral loopback port and exits after two connections, so it is not a persistent server for manual external probing afterward.

## 11. Systematic testing

| Test case | Expected outcome |
| --- | --- |
| SNI `blue` with `blue` certificate | Handshake succeeds; SAN and `blue` hostname valid |
| SNI `green` with `green` certificate | Handshake succeeds; SAN and `green` hostname valid |
| Nonexistent SNI, no default policy | Does not pick wrong cert/vhost; handshake rejected |
| `blue` certificate served for `green` target | Hostname verification rejects |
| Certificate signed by CA absent from truststore | PKIX/trust manager rejects |
| Client ALPN `demo/1,http/1.1`; server prefers `http/1.1` | Selects `http/1.1` and runs HTTP/1.1 handler only if one exists |
| Client has only `h2`, server has only `http/1.1` | Rejected per ALPN policy; no unexpected protocol picked |
| One side omits ALPN | Unnegotiated per API; handled per profile without guessing |
| HTTP `Host` changed to another tenant | Routing/authorization does not grant cross-tenant access |
| Proxy terminates + re-encrypts | Separate proper cert/trust/SNI/ALPN per hop |
| Alias reloads new certificate | Picks right chain, hostname, and key type after rotation |
| App advertises ALPN `h2` without implementing HTTP/2 | Caught by tests; blocked from production |
| Client uses IP SAN instead of DNS SAN | Verifies IP identity policy and missing-DNS-SNI case |
| KeyManager handles only `SSLSocket`, app uses `SSLEngine` | Must implement `chooseEngineServerAlias` or use proper framework config |

### 11.1 Exercises

1. **Trace the path:** an HTTPS client connects to `blue.example.test` on an IP shared with `green`. When is SNI sent, which certificate must be chosen, and why can't HTTP `Host` be used to pick the certificate at the start of the handshake?
2. **Identify APIs:** in `SniAlpnDemo`, pinpoint the method configuring client SNI, the method reading server SNI during key selection, the method setting ALPN choices, and the method retrieving the final ALPN value.
3. **Flip ALPN order:** reverse the server list from `["http/1.1","demo/1"]` to `["demo/1","http/1.1"]` and observe what the provider picks. Explain why changing a label alone does not mean the application supports a new protocol.
4. **Unrecognized SNI:** consider how to modify `aliasFor` to handle unconfigured hostnames. Why can picking a default alias by similar name break tenant isolation?
5. **Endpoint identity:** remove `setEndpointIdentificationAlgorithm("HTTPS")` and explain the security risk (never recommended in production code). Distinguish a trusted CA chain from matching the intended server name.
6. **One certificate, multiple SANs:** suppose `blue` and `green` share one certificate carrying both SANs; what value does SNI still retain for routing and policy?
7. **HTTP/2:** if the client sends `ALPN=h2`, what additional application components must the server have? If the server has only an HTTP/1.1 handler, what is the safe outcome?
8. **Two TLS hops:** the edge picks a cert from external SNI and then opens a backend TLS connection; determine backend SNI/ALPN, how the backend is authenticated, and the role of HTTP `Host`/`:authority`.
9. **Observation:** in a test environment, enable JSSE handshake debugging and locate `ClientHello` SNI, the ALPN list, and the chosen certificate; avoid sharing sensitive data in logs.
10. **Privacy:** why does TLS 1.3 encrypting application data not necessarily hide the SNI name? What does ECH change?
11. **Authorization:** a request to `admin.example.test` uses a valid certificate and HTTP/2. Why does the user still need authentication and authorization?
12. **Provider portability:** explain why `KeyManagerFactory.getInstance("SunX509")` and the example's alias mapping must be verified when switching to another provider or HSM.

**Completion criteria:** you can answer three questions for any multi-domain HTTPS connection: **(1) Which SNI was sent and which certificate/vhost was chosen? (2) Did the client verify both the trust anchor and the certificate's hostname? (3) Which application protocol did ALPN select, and do server and client actually implement handlers for it?** Missing any layer can allow TLS to partially succeed while routing or application security remains broken.

## 12. Official references

- [Java SE 21 – `SSLParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setServerNames`, `setApplicationProtocols`, `setSNIMatchers`, and `setEndpointIdentificationAlgorithm`.
- [Java SE 21 – `SNIHostName`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SNIHostName.html) and [`SNIServerName`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SNIServerName.html): server name structures in TLS.
- [Java SE 21 – `ExtendedSSLSession`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/ExtendedSSLSession.html): `getRequestedServerNames` and handshake/session metadata.
- [Java SE 21 – `X509ExtendedKeyManager`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/X509ExtendedKeyManager.html): `chooseServerAlias`, `chooseEngineServerAlias`, certificate chain/private key.
- [Java SE 21 – `SSLSocket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLSocket.html): `getApplicationProtocol`, `getHandshakeApplicationProtocol`, protocol selector, `getHandshakeSession`, and handshake behavior.
- [Java SE 21 – `SSLServerSocket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLServerSocket.html) and [`SSLEngine`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html): TLS server listener and non-blocking engine.
- [Java SE 21 – JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS configuration, ALPN, SNI, key/trust managers, and debugging.
- [RFC 6066](https://www.rfc-editor.org/rfc/rfc6066): TLS Extension Definitions, `server_name` (SNI).
- [RFC 7301](https://www.rfc-editor.org/rfc/rfc7301): ALPN extension, protocol selection, and `no_application_protocol` alert.
- [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446): TLS 1.3 `ClientHello`, `EncryptedExtensions`, certificate, and session semantics.
- [RFC 9113](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 and HTTP/2 over TLS, ALPN `h2`.
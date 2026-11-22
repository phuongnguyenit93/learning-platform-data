# Client Address in Java Web Application Logging

## 1. What is a client address?

In web application logging, **client address** typically refers to the network address of the request sender, primarily the **IP address** and sometimes the **source port**. This information is useful for investigating connection issues, aggregating errors by source, tracing requests, or identifying anomalous behavior.

Example of a structured access event log:

~~~text
event=http_request_finished method=GET route=/orders/{id}
status=200 durationMs=18 requestId=req-001
peerIp=10.0.0.10 clientIp=203.0.113.9 clientIpSource=TRUSTED_EDGE
~~~

The addresses in the example belong to documentation and internal network IP ranges. The `peerIp` and `clientIp` fields **do not necessarily have the same value** when a reverse proxy is present. `requestId` is used to correlate logs belonging to the same request; do not use access tokens or cookies instead of a request ID.

Three concepts to distinguish:

- **Socket peer / remote peer:** The IP of the other end of the TCP connection as seen by the Java server. If the connection goes through a proxy, this is usually the **proxy's** IP.
- **Logical/original client IP:** The IP of the party that initiated the request before any proxies, provided there is a trusted forwarding chain and a valid source-resolution policy.
- **User identity:** The authenticated user, account, or service. **You cannot infer identity or access permissions from an IP address alone**: multiple users can share a NAT/VPN/proxy, IPs can change, and proxy data can be spoofed.

**Client address is not the address that the HTTP `Host` or `:authority` header requests to access.** `Host` describes the HTTP target, not proof of the connection's origin. Nor should reading an address from a header be called "getting the real IP" without explicitly stating the trust model.

## 2. Why can the client address change across layers?

A web architecture might look like this:

~~~text
Browser (203.0.113.9)
      |
      v
CDN / Edge proxy
      |
      v
Load balancer (10.0.0.5)
      |
      v
Reverse proxy (10.0.0.10)
      |
      v
Java application
~~~

The Java application typically sees only the **peer of the direct connection**: for example, `10.0.0.10`. Original client address information can be forwarded by proxies via HTTP metadata or a transport-layer mechanism, if the infrastructure is configured to support it.

Common reasons why the client address differs from the peer address:

1. **Reverse proxy/load balancer:** TLS may be terminated at ingress, and the proxy then opens a new connection to Java.
2. **CDN/WAF:** Many incoming requests pass through a pool of provider addresses.
3. **Service mesh/gateway:** Requests pass through a sidecar or internal proxy.
4. **NAT/CGNAT:** Multiple devices share a single public IP address; the server does not know a device's private IP without additional trusted information.
5. **VPN/corporate proxy:** The public IP is the egress point of an intermediary network.
6. **IPv4 and IPv6:** A single user may traverse multiple protocols/addresses over time.

Therefore, logging should distinguish between the **directly observed address** and the **proxy-inferred address**, and explicitly record the **resolution source** if policy permits storing these fields.

## 3. Getting the remote peer in Java

### 3.1. JDK HttpServer

With the JDK's built-in simple HTTP server:

~~~java
import com.sun.net.httpserver.HttpExchange;
import java.net.InetSocketAddress;

// Integration snippet inside HttpHandler.handle(HttpExchange exchange).
InetSocketAddress peer = exchange.getRemoteAddress();
String peerIp = peer.getAddress().getHostAddress();
int peerPort = peer.getPort();
~~~

`exchange.getRemoteAddress()` returns the remote address of the **connection accepted by HttpServer**. In a proxied deployment, this value is typically the address of the proxy closest to Java. `getAddress()` returns an `InetAddress` when the socket address is resolved; the snippet above assumes that state during an actual JDK HttpServer request. `getHostAddress()` retrieves the textual IP representation, not a user identity.

The port from `getPort()` is the **remote source port of the TCP connection**, which is typically ephemeral and changes when a new connection is established. Do not confuse it with the server's HTTP port or with a persistent user identifier.

### 3.2. Servlet/Jakarta Servlet and Spring

In the Servlet API, the application can typically read:

~~~java
// Integration snippet; requires Servlet/Jakarta Servlet API and an active request.
String remoteAddr = request.getRemoteAddr();
int remotePort = request.getRemotePort();
~~~

The meaning of `getRemoteAddr()` depends on the connection path and **container/filter/valve configuration**. In some deployments, a configured container or forwarded-header handler can alter the address returned by the high-level API. Do not assume every Servlet application sees the original IP or sees the proxy IP; verify the exact runtime configuration.

In Spring MVC, `HttpServletRequest` remains a commonly used source. However, if the system trusts forwarded headers via the container/framework, the trust policy must be configured at the appropriate layer; **do not manually read unvalidated headers in a controller and call them the client IP**.

**Do not use reverse DNS** (`getHostName()`) solely for logging source addresses: DNS lookups add latency, results can change, and a domain name is not proof of identity. For IP logging purposes, `getHostAddress()` is typically preferred.

## 4. X-Forwarded-For, Forwarded, and X-Real-IP

Some infrastructures pass information via HTTP headers:

| Header | Common format | Things to watch out for |
| --- | --- | --- |
| `X-Forwarded-For` | `203.0.113.9, 10.0.0.5` | De-facto header, usually a list of IPs across proxies; not a guarantee of origin |
| `Forwarded` | `for=203.0.113.9;proto=https` | Standardized header per RFC 7239; has more complex syntax |
| `X-Real-IP` | `203.0.113.9` | Convention of some proxies; not guaranteed to be present |
| CDN-specific header | Provider-dependent | Only trust when requests pass through that exact infrastructure and it strips/overwrites forged data |

`X-Forwarded-For` (XFF) can be appended to by each proxy:

~~~text
X-Forwarded-For: 203.0.113.9, 10.0.0.5
~~~

The rule "take the **first IP** on the left" is **unsafe if the value can be arbitrarily supplied by the client**. An attacker can send:

~~~text
X-Forwarded-For: 1.2.3.4
~~~

If the server receives this request directly and trusts the header, the log may falsely record `clientIp=1.2.3.4` even though the actual peer is different. HTTP headers are **sender-controlled data**, unless a trusted proxy chain sits in front of the application and sets/normalizes the header according to policy.

**`Forwarded` syntax is even more complex than XFF:** it has `for`, `by`, `host`, and `proto` parameters, quoted values, bracketed IPv6 addresses, ports, `unknown` values, or obfuscated identifiers. Do not parse this header by simply splitting on commas, colons, or taking the first substring.

For IPv6, `2001:db8::1` contains multiple `:` characters; calling `split(":")` to extract an IP from a value like `[2001:db8::1]:12345` is very error-prone. If full `Forwarded` parsing is needed, prefer a tested web server/framework processor or a library that properly supports the grammar.

## 5. Trust model: the most important step

To extract a logical client address from proxy metadata, you must first answer the question: **did this request actually come from a proxy that the system trusts?**

A secure design typically includes these layers:

1. **Restrict ingress to Java:** The backend does not allow external Internet clients to connect directly, unless intentional. Use appropriate network configuration, firewalls, service mesh, mTLS, or source restrictions.
2. **Configure a trusted proxy list:** IPs/CIDRs or identities based on managed infrastructure; do not trust every private address or every `X-Forwarded-For`.
3. **Normalize at the edge:** The first proxy allowed to receive public traffic should **strip/overwrite** untrusted forwarded headers, or properly apply concatenation algorithms and trusted-hop policies.
4. **Verify the immediate peer:** The application only interprets forwarded metadata when the connection genuinely comes from a trusted proxy.
5. **Select the address according to the trusted chain:** In multi-hop setups, traverse hops per infrastructure rules (typically from right to left to find the first untrusted hop), rather than unconditionally "taking the leftmost".
6. **Handle missing/malformed headers:** Have a fallback policy or mark as `unknown`; do not silently assign a bogus value and use it for security decisions.

**Example:**

~~~text
Immediate peer before Java: 10.0.0.10 (managed proxy)
XFF: 203.0.113.9, 10.0.0.5
Trusted chain: 10.0.0.10 and 10.0.0.5
=> Nearest untrusted client hop: 203.0.113.9
~~~

If only `10.0.0.10` is trusted and `10.0.0.5` is not, you cannot infer `203.0.113.9` as a verified source; `10.0.0.5` must be treated as the untrusted boundary under the defined policy. Systems with one or multiple proxies need a model tailored to the actual network topology—**do not hard-code a single algorithm for all deployments**.

In many applications, the best approach is to **let the ingress/container handle forwarded headers properly**, and then expose a consistent `clientAddress` API along with source metadata, rather than having each controller parse XFF itself.

## 6. Standalone Java 17 example: ignoring forged headers and trusting only an edge with an explicit contract

This program simulates two types of requests: direct access and requests arriving from an internally managed edge proxy. To avoid teaching arbitrary header trust, the demo uses **very narrow infrastructure assumptions**:

- The immediate peer `10.0.0.10` is an established edge proxy, and **network policy prevents external clients from reaching Java as this peer**.
- The edge proxy **overwrites** `X-Forwarded-For` with a **single IPv4 address** that it has determined; it does not preserve untrusted values from the client.
- If the peer is anything other than `10.0.0.10`, ignore XFF completely.
- If the header is missing, multi-hop, or malformed, the demo does not guess the client IP: it logs the peer address with source `PROXY_FALLBACK`.
- This is an example to illustrate trust boundaries, **not a production XFF/Forwarded parser**, and it does not handle IPv6 or CIDR.

Create `ClientAddressDemo.java`:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ClientAddressDemo {

    record Address(String ip, String source) {}

    private static boolean singleIpv4(String value) {
        if (value == null || !value.matches("[0-9.]{7,15}")) {
            return false;
        }
        String[] parts = value.split("[.]", -1);
        if (parts.length != 4) {
            return false;
        }
        for (String part : parts) {
            if (part.isEmpty() || part.length() > 3
                    || (part.length() > 1 && part.startsWith("0"))) {
                return false;
            }
            if (Integer.parseInt(part) > 255) {
                return false;
            }
        }
        return true;
    }

    private static Address resolve(
            InetSocketAddress peer, String xForwardedFor) {
        String peerIp = peer.getAddress().getHostAddress();

        // Demo policy: only edge 10.0.0.10 is allowed to
        // overwrite XFF to a single IPv4.
        if (!"10.0.0.10".equals(peerIp)) {
            return new Address(peerIp, "SOCKET_PEER");
        }
        if (!singleIpv4(xForwardedFor)) {
            return new Address(peerIp, "PROXY_FALLBACK");
        }
        return new Address(xForwardedFor, "TRUSTED_EDGE_HEADER");
    }

    private static InetSocketAddress socket(byte[] ip) throws Exception {
        return new InetSocketAddress(InetAddress.getByAddress(ip), 52000);
    }

    private static void logCase(
            Logger logger, String name, Address address) {
        logger.info("case=" + name
                + " client=" + address.ip()
                + " source=" + address.source());
    }

    public static void main(String[] args) throws Exception {
        Logger logger = Logger.getLogger("demo.client.address");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(handler);

        try {
            InetSocketAddress direct = socket(
                    new byte[] {(byte) 198, 51, 100, 23});
            InetSocketAddress edge = socket(
                    new byte[] {10, 0, 0, 10});

            logCase(logger, "direct", resolve(direct, null));

            // Client sets a forged XFF, but the peer is untrusted.
            logCase(logger, "spoof-at-direct",
                    resolve(direct, "1.2.3.4"));

            // Managed edge overwrote the header according to policy.
            logCase(logger, "trusted-edge",
                    resolve(edge, "203.0.113.9"));

            // Demo only supports a single-IPv4 header, no chain parsing.
            logCase(logger, "multi-hop",
                    resolve(edge, "203.0.113.9, 10.0.0.5"));
        } finally {
            logger.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac ClientAddressDemo.java
java ClientAddressDemo
~~~

**Stdout:** no output.

**Exact stderr** from a successful run:

~~~text
INFO: case=direct client=198.51.100.23 source=SOCKET_PEER
INFO: case=spoof-at-direct client=198.51.100.23 source=SOCKET_PEER
INFO: case=trusted-edge client=203.0.113.9 source=TRUSTED_EDGE_HEADER
INFO: case=multi-hop client=10.0.0.10 source=PROXY_FALLBACK
~~~

JUL's `ConsoleHandler` writes to **stderr**. The custom `Formatter` ensures a short, stable format without adding random timestamps. Addresses and ports are constructed in code so the run does not depend on a live network or DNS.

### Case-by-case analysis

| Case | Immediate peer | XFF value | Conclusion |
| --- | --- | --- | --- |
| Direct access | `198.51.100.23` | None | Log the directly observed peer |
| Forged header from client | `198.51.100.23` | `1.2.3.4` | **Ignore XFF**, do not accept the forged address |
| Trusted edge, 1 IPv4 | `10.0.0.10` | `203.0.113.9` | Accept only per the **described infrastructure contract** |
| Multi-hop header | `10.0.0.10` | `203.0.113.9, 10.0.0.5` | Do not self-parse; fall back to peer with source label |

**Crucial limitation:** the example trusts `X-Forwarded-For` solely because the peer matches `10.0.0.10` **and** the deployment is assumed to protect the backend while the edge overwrites the header. This Java code **cannot prove on its own** that the proxy actually did so. If the edge merely appends to an attacker-supplied header, or if the backend has a direct access path bypassing the edge, the design must be fixed at the **network and proxy configuration** level first. Do not copy this `resolve` function verbatim into a multi-hop/IPv6 production system.

## 7. Request logging: which fields should be recorded?

A common request log schema:

~~~text
timestamp=...
requestId=...
method=GET
route=/orders/{id}
status=200
durationMs=18
peerIp=10.0.0.10
clientIp=203.0.113.9
clientIpSource=TRUSTED_EDGE
proxyPolicy=edge-v1
~~~

Explanation:

- `route` is the **route template** when supported by the framework, such as `/orders/{id}`, rather than defaulting to the full URL with query parameters containing user data.
- `clientIpSource` helps investigators know whether the IP came from a direct connection or was inferred via proxy policy.
- `peerIp` can help spot ingress/proxy issues or misrouted requests.
- `requestId` is usually more important than IP addresses for correlating processing steps across multiple services.
- `durationMs`, status, and error category should be separate fields; there is no need to dump the HTTP body.

**Do not log the raw `X-Forwarded-For` header string from untrusted requests** just for debugging: it can be very long, contain control characters, forged strings, or multiple personal addresses. If you need to investigate parser/proxy issues, log a status such as `FORWARDED_MISSING`, `FORWARDED_INVALID`, `UNTRUSTED_PEER`, or a count of inspected hops instead of printing the entire raw string.

### IP is technical metadata, yet can still be personal data

In many contexts, an IP address can be linked to a device or user when combined with timestamps, account logs, and ISP data. Therefore:

- Only collect IPs if there is a **clear, legitimate purpose**.
- Define retention periods, access permissions, and who is authorized to look them up.
- Consider **masking/truncating or aggregating** if statistical needs do not require full IPs.
- Do not put IPs or user agents into high-cardinality metric labels.
- Do not assume hashed IPs are anonymous: IPv4 addresses can be guessed and matched, and a static hash allows activity correlation.
- Do not automatically forward IPs to third-party systems without a security/privacy review.

Some purposes, such as security incident response, require full IPs for an appropriate window; others only need network/address prefixes or aggregated rates. Separate log types and policies instead of "keeping everything forever."

## 8. Practical issues: IPv4, IPv6, NAT, ports, and malformed addresses

**IPv4 and IPv6:** Many applications must support both. For example, `192.0.2.10` is IPv4 and `2001:db8::1` is IPv6. Do not force IPv6 into a 4-octet format, and do not rely on a fixed length like "IPs are always at most 15 characters." When storing or comparing addresses, prefer IP structures validated by an appropriate library rather than arbitrary string splitting.

**NAT/CGNAT/VPN:** A public IP does not equal a single user. Thousands of legitimate requests from different accounts can share the same IP. Do not use IP as the sole key for identity, audit actors, or authorization decisions.

**Source port:** Ports can help distinguish connections in some network logs, but they vary by connection, NAT, and time; they are not stable user information. If logging `IP:port`, use an unambiguous representation for IPv6 (e.g., IPv6 needs square brackets when combined with a port).

**IPv4-mapped IPv6 and normalization:** Two IP strings can represent the same destination under different conventions. When comparing an IP against a set of IPs/CIDRs, use appropriate networking algorithms and libraries rather than comparing raw strings and assuming equivalence.

**Missing/unparseable addresses:** Do not fill in a dummy IP like `0.0.0.0` to fabricate a known source address. Log a status like `unknown` or `invalid-forwarded-header` alongside `peerIp` if policy permits, so readers can distinguish missing data from real addresses.

**Control characters and log injection:** An attacker-controlled header can contain newlines, delimiters, or strings designed to mislead log parsers. Only log parsed and validated fields; if raw logging is strictly required for controlled investigation, apply proper encoding/escaping and enforce size/retention limits.

## 9. Frameworks, reverse proxies, and infrastructure configuration

When deploying with Spring Boot, Tomcat, Jetty, Netty, nginx, Apache HTTP Server, Envoy, a CDN, or a load balancer, you must determine **which component is responsible for validating trusted proxies**. Containers and frameworks may provide forwarded-header normalization, but behavior depends on version, configuration, and ingress path.

A safe configuration workflow:

1. Diagram the actual hops sitting in front of the JVM in production.
2. Identify the IPs/CIDRs or identities of trusted hops; avoid configuring "trust all proxies."
3. At the edge proxy, strip client-supplied headers if policy requires it and regenerate standard headers.
4. Ensure the Java backend has no unintended connection paths bypassing the proxy.
5. Use container/framework configuration to process forwarded metadata **once**, avoiding duplicate custom parsers across filters/controllers.
6. Test direct access, single-proxy, multi-proxy, and forged-header scenarios.
7. Log source/policy/version and observe how logs change when ingress changes.
8. Ensure consistent behavior across dev, staging, production, and inside containers.

**Specifically:** headers used to determine client IP for logging should not be trusted on their own and used for **security policies** such as access allowlists or rate limiting before verifying the trust chain. An IP address is only an auxiliary signal; authentication and authorization requirements should rely on proper identities and mechanisms.

If the application uses containers or a service mesh, ingress logs may already record the source IP per network policy. In that case, the Java backend may only need to log `requestId`/trace ID and correlate with edge access logs, rather than duplicating IPs across every service. This is a decision about purpose, data, and access control.

## 10. Testing with targeted cases

| Test case | Expected behavior |
| --- | --- |
| Direct request, no forwarded header | Use socket peer |
| Direct request with forged XFF | Still use socket peer; do not trust header |
| Request through trusted edge that overwrote header | Select address confirmed by edge policy |
| Edge missing header | Log missing/fallback status; do not assume original IP |
| Multi-hop header | Run actual proxy-chain policy; do not blindly take leftmost |
| IPv6 or RFC `Forwarded` header | Parser/framework supports proper grammar or rejects cleanly |
| Oversized header / contains newlines | Enforce size limit; do not log raw data unchecked |
| Backend has path bypassing proxy | Do not trust header merely because it exists |
| Proxy IP/CIDR changes | Update trust policy; alert on mismatch |
| XFF contains mixed private/public IPs | Select by *trusted hop*, not a "first public IP" heuristic |
| Switch from IPv4 to IPv6 | No dropped logs or broken schema due to length limits |
| Client behind NAT/VPN | Do not treat IP as a unique user identity |

In an integration test, log **peer IP**, **resolved client IP**, and **source/policy** in a controlled test infrastructure. Verify the response status, request ID, and where the logs are written. Do not rely on logs after passing through a collector as the sole proof that the original header was parsed correctly, because the collector itself might alter or normalize fields.

## 11. Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using `getRemoteAddr()` and claiming it is always the browser IP | It may just be a reverse proxy | Distinguish peer and logical client |
| Trusting `X-Forwarded-For` on every request | Clients can send the header to spoof IPs | Trust the immediate peer and proxy path |
| Taking the leftmost IP in any XFF | The chain may start with an attacker-supplied value | Select using a trusted-hop policy |
| Using `Host` as the client address | `Host` is the HTTP target | Read socket peer and trusted proxy metadata |
| Parsing `Forwarded` with `split(":")` | IPv6, quotes, ports, and multiple elements break it | Use a grammar-aware parser |
| Treating IP as a user ID | NAT, VPN, and multiple users share IPs | Use correlation IDs and separate auth identity |
| Logging raw XFF without limits | Risks spoofing, injection, PII, and bloat | Validate, normalize, and limit size |
| Rewriting remote address in both container and app | Can re-process headers incorrectly | Designate a single responsible layer |
| Keeping IPs forever | Increases privacy risk and storage cost | Set retention by purpose and access rights |
| Hashing IPs and treating them as anonymous | Can still be correlated or guessed | Assess re-identification risk |

## 12. Adoption checklist

- [ ] Clearly distinguish `peerIp`, `clientIp`, `clientIpSource`, and request ID.
- [ ] Identify whether the app runs directly or behind a CDN/load balancer/reverse proxy/mesh.
- [ ] Establish, test, and document the trusted proxies list.
- [ ] Edge controls incoming `X-Forwarded-For`/`Forwarded` per policy.
- [ ] Do not trust headers when the immediate peer is outside the trust boundary.
- [ ] Properly support IPv4/IPv6 or cleanly reject unsupported formats.
- [ ] Do not use raw XFF as identity or security rules.
- [ ] Use a log schema with explicit data source and trust level.
- [ ] Limit PII/IP logging by purpose; set appropriate retention, access control, and masking.
- [ ] Test spoofed headers, multi-hop, NAT/VPN, newlines, and infrastructure changes.
- [ ] Correlate service logs via request ID/trace ID rather than relying solely on IP.

### Self-check

**Q1.** A Java server accepts a connection from proxy `10.0.0.10`. Which IP does `getRemoteAddress()` typically see?  
**A:** The immediate peer address `10.0.0.10`, not the browser IP by default.

**Q2.** A direct request contains `X-Forwarded-For: 1.2.3.4`. Can the client IP be trusted as `1.2.3.4`?  
**A:** No. The header could have been set by the client itself; a trusted proxy chain is required.

**Q3.** Is it safe to use the leftmost public IP in every XFF chain?  
**A:** No. You must determine trusted hops and the infrastructure's header policy.

**Q4.** Is it right to use IP to identify a logged-in user?  
**A:** No. IPs can be shared via NAT/VPN and do not substitute for authentication credentials.

**Q5.** Are IP addresses in logs always harmless data?  
**A:** No. They can be linked to individuals or devices; appropriate collection limits, access controls, and retention are required.

**Key takeaway:** Client address in web logging provides information about the **network origin of a request**, yet peer address, proxy-forwarded client IP, and user identity are three distinct concepts. Do not trust forwarded headers without a trusted proxy policy and proper infrastructure protection. Log the address resolution source, test spoofing/IPv6/multi-hop scenarios, and manage IPs as potentially sensitive data.
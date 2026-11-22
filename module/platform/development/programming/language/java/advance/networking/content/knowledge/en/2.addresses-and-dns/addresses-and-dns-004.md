# Creating Addresses from Bytes or IP Literals Without Confusing Them with Name Resolution

## 1. Identifying the Three Input Types Correctly

In Java networking, `java.net.InetAddress` represents an **IP address** (IPv4: 32-bit; IPv6: 128-bit), which may be accompanied by host name information. Three forms of data often appear side by side but behave differently:

- **Address bytes**: four IPv4 bytes or sixteen IPv6 bytes taken from a packet, protocol, or binary configuration. The bytes are already the address; there is no need to query DNS to find the IP.
- **IP literal**: a string that directly writes out the address, for example `192.0.2.42` or `2001:db8::1`. It requires *address parsing*, not name resolution, if the string is actually a valid literal.
- **Hostname**: a string such as `api.example.com`. The program must use the operating system/JVM name resolution service to find the IP; the source can be the hosts file, a cache, or DNS, so you cannot assume every call triggers a DNS query.

Distinguish between the two operations: **literal parsing** converts the representation of an already-known IP into an object; **name resolution** looks up the IP corresponding to a name. Successfully creating an `InetAddress` does not mean the target host exists, has network connectivity, or that the address has been verified.

```text
byte[4]/byte[16] -- getByAddress(...) --> InetAddress
IP literal       -- getByName(literal) --> InetAddress (syntax parsing)
hostname         -- getByName(hostname) --> name service/cache --> InetAddress
```

The ranges `192.0.2.0/24`, `203.0.113.0/24`, and `2001:db8::/32` are reserved for documentation/examples; do not treat them as reachable hosts.

## 2. Choosing an API by Purpose

| Java 17+ API | Input and behavior at call time | May perform name resolution? |
| --- | --- | --- |
| `InetAddress.getByAddress(byte[])` | Converts 4/16 bytes in network byte order into an IP address | **No**; no reverse lookup |
| `InetAddress.getByAddress(String host, byte[])` | Uses the bytes as the IP and **attaches the provided hostname label** without verifying the label | **No** at creation time |
| `InetAddress.getByName("192.0.2.42")` | Parses a valid IPv4 literal | **No** name service needed |
| `InetAddress.getByName("2001:db8::1")` | Parses a valid IPv6 literal | **No** name service needed |
| `InetAddress.getByName("api.example.com")` | Looks up the IP for a hostname | **Yes**, via resolver/cache |
| `InetAddress.getAllByName(hostname)` | Looks up the addresses returned for a name | **Yes**, via resolver/cache |
| `address.getAddress()` / `address.getHostAddress()` | Gets the IP bytes / IP string of an existing object | **No** |
| `address.getHostName()` / `getCanonicalHostName()` | Gets the hostname; may need a reverse lookup if no name is cached/stored | **Yes** |

**Common pitfall:** `getByName` does not mean "always call DNS". It accepts **both literals and hostnames**. Conversely, `getByAddress(String host, byte[] ip)` does not resolve `host` and does not verify whether that name points to `ip`.

## 3. Creating IPv4/IPv6 from Bytes

`InetAddress.getByAddress(raw)` requires:

1. `raw.length == 4` for IPv4 or `raw.length == 16` for IPv6. Any other length leads to `UnknownHostException`, which here is an **address data error**, not evidence of a failed DNS query.
2. Bytes are arranged in **network byte order**: the most significant byte comes first. For `192.0.2.42`, the order is `192, 0, 2, 42`.
3. Java's `byte` is signed in the range -128 to 127. Network octets have values 0–255; therefore, write `(byte) 192` and read them back with `b & 0xFF`.

The following example runs standalone on Java 17 or later, **without needing network/DNS**, because it only uses bytes and valid literals.

**`AddressCreationDemo.java`**

```java
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;

public class AddressCreationDemo {
    public static void main(String[] args) throws UnknownHostException {
        // IPv4: 192.0.2.42. Cast because 192 exceeds the signed byte range.
        byte[] v4Raw = {(byte) 192, 0, 2, 42};
        InetAddress fromBytesV4 = InetAddress.getByAddress(v4Raw);
        InetAddress fromLiteralV4 = InetAddress.getByName("192.0.2.42");

        // IPv6: 2001:db8::1, all 16 bytes in network byte order.
        byte[] v6Raw = {
                0x20, 0x01, 0x0d, (byte) 0xb8,
                0, 0, 0, 0,
                0, 0, 0, 0,
                0, 0, 0, 1
        };
        InetAddress fromBytesV6 = InetAddress.getByAddress(v6Raw);
        InetAddress fromLiteralV6 = InetAddress.getByName("2001:db8::1");

        System.out.println("IPv4: " + fromBytesV4.getHostAddress());
        System.out.println("IPv4 family: "
                + (fromBytesV4 instanceof Inet4Address));
        System.out.println("IPv4 same: " + fromBytesV4.equals(fromLiteralV4));
        System.out.println("First octet: "
                + (fromBytesV4.getAddress()[0] & 0xFF));

        System.out.println("IPv6 family: "
                + (fromBytesV6 instanceof Inet6Address));
        System.out.println("IPv6 size: " + fromBytesV6.getAddress().length);
        System.out.println("IPv6 same: " + fromBytesV6.equals(fromLiteralV6));

        // The host label is not resolved or validated at creation time.
        InetAddress tagged =
                InetAddress.getByAddress("example.invalid", v4Raw);
        System.out.println("Tagged IP: " + tagged.getHostAddress());
        System.out.println("Tagged equal: " + tagged.equals(fromBytesV4));

        try {
            InetAddress.getByAddress(new byte[] {1, 2, 3});
        } catch (UnknownHostException e) {
            System.out.println("Invalid length: rejected");
        }
    }
}
```

Run:

```bash
javac --release 17 AddressCreationDemo.java
java AddressCreationDemo
```

Output:

```text
IPv4: 192.0.2.42
IPv4 family: true
IPv4 same: true
First octet: 192
IPv6 family: true
IPv6 size: 16
IPv6 same: true
Tagged IP: 192.0.2.42
Tagged equal: true
Invalid length: rejected
```

Explanation:

- Both ways of creating IPv4 return objects with the same **IP value**. `equals` compares the address content and does not use the host label as the identity of the IP.
- Both ways of creating IPv6 also hold the same 16 bytes. Avoid comparing IPv6 strings as the sole criterion, because literals can use compressed notation (`::`), while `getHostAddress()` may return a different representation.
- `getByAddress("example.invalid", v4Raw)` still creates `192.0.2.42`; the attached name is unverified metadata.
- `UnknownHostException` in the three-byte case merely reflects an invalid length.

## 4. Creating from an IP Literal Without Accidentally Going Through Hostname Resolution

For a value **known with certainty to be a valid literal**, you can use:

```java
InetAddress ipv4 = InetAddress.getByName("198.51.100.10");
InetAddress ipv6 = InetAddress.getByName("2001:db8::a");
```

These two calls parse the address syntax without needing a hostname lookup. However, **do not use `getByName(untrustedInput)` as an "IP-only" validator**:

- If the input is a name (or is treated as a name), the API may invoke the name service.
- Java 17 also accepts certain **shorthand IPv4 forms** (not necessarily strictly four `d.d.d.d` octets); an address accepted by the API does not mean it satisfies your application's input format policy.
- `getByName(null)` and `getByName("")` return the loopback address; do not let missing data pass through the API and be mistaken for a valid supplied address.
- `"192.0.2.42:443"` is not an IP literal; the port belongs to `InetSocketAddress`. Square brackets around IPv6 in a URI (`[2001:db8::1]`) are a URI/endpoint rule; you must separate the host and port before applying validation policies.

If you require **standard dotted-quad IPv4, with zero lookups even on invalid input**, validate the four octets yourself and then call `getByAddress`. The example below intentionally rejects octets with leading zeros (except `"0"` itself).

**`StrictIpv4Parser.java`**

```java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.List;

public final class StrictIpv4Parser {
    public static Inet4Address parse(String text)
            throws UnknownHostException {
        if (text == null) {
            throw new IllegalArgumentException("IPv4 is required");
        }

        String[] octets = text.split("\\.", -1);
        if (octets.length != 4) {
            throw new IllegalArgumentException("Expected four octets");
        }

        byte[] raw = new byte[4];
        for (int i = 0; i < octets.length; i++) {
            String part = octets[i];
            if (part.isEmpty() || part.length() > 3
                    || (part.length() > 1 && part.charAt(0) == '0')) {
                throw new IllegalArgumentException("Invalid octet: " + part);
            }

            // Accept only ASCII '0'..'9', no implicit trimming.
            for (int j = 0; j < part.length(); j++) {
                char ch = part.charAt(j);
                if (ch < '0' || ch > '9') {
                    throw new IllegalArgumentException("Non-decimal octet");
                }
            }

            int value = Integer.parseInt(part);
            if (value > 255) {
                throw new IllegalArgumentException("Octet exceeds 255");
            }
            raw[i] = (byte) value;
        }

        // Validated exactly 4 bytes: no reason to invoke the resolver.
        return (Inet4Address) InetAddress.getByAddress(raw);
    }

    public static void main(String[] args) throws UnknownHostException {
        System.out.println(parse("203.0.113.7").getHostAddress());

        for (String value : List.of(
                "203.0.113.999",
                "203.0.113",
                "203.0.113.007",
                "example.com")) {
            try {
                parse(value);
                System.out.println(value + " => accepted");
            } catch (IllegalArgumentException e) {
                System.out.println(value + " => rejected");
            }
        }
    }
}
```

```bash
javac --release 17 StrictIpv4Parser.java
java StrictIpv4Parser
```

```text
203.0.113.7
203.0.113.999 => rejected
203.0.113 => rejected
203.0.113.007 => rejected
example.com => rejected
```

This validator is **intentionally scoped to dotted-quad IPv4**; it is not a hostname or IPv6 parser. IPv6 has a rich grammar (`::` compression, IPv4-embedded addresses, zone IDs); you should not validate IPv6 with a simplified homebrew regex. If the system needs to guarantee "literal-only" for **both IPv4 and IPv6** on Java 17, use a tested dedicated IP parser or construct `InetAddress` from 4/16 validated bytes. The `InetAddress.ofLiteral(String)` API was added in **Java 22** and is not available when compiling for Java 17.

## 5. Forward and Reverse Name Resolution Are Two Separate Concerns

- **Forward resolution**: `getByName("server.example.com")` or `getAllByName(...)` needs to find an IP from a hostname. Results may come from a cache, hosts file, or DNS, depending on the system and timing; `getAllByName` may return multiple IPs.
- **Reverse resolution**: `address.getHostName()` may look up the hostname from the address if the object does not already store a name; `getCanonicalHostName()` may perform a lookup to find the canonical name (best effort). Neither call is suitable for code paths that require IP-only operations without triggering lookups.
- **Display IP only**: use `getHostAddress()`; if you need to compare values, use `equals` or `getAddress()`, not the hostname.
- **Labeling ≠ verification**: `getByAddress("trusted.example", raw)` records the string `trusted.example` without verifying forward or reverse DNS. Do not use that label as proof of address ownership, access rights, or security identity.
- **`toString()` is not a canonical formatting encoder**: it may include a hostname part and a `/` character; avoid parsing `InetAddress.toString()` to extract an IP or hostname.

Behavior comparison example (illustrative snippet; you do **not** need a real hostname to understand it):

```java
InetAddress raw = InetAddress.getByAddress(
        new byte[] {(byte) 192, 0, 2, 42});  // No DNS

String ipText = raw.getHostAddress();       // "192.0.2.42", no DNS
String possiblyName = raw.getHostName();   // May perform reverse lookup

InetAddress labeled = InetAddress.getByAddress(
        "app.example.invalid", raw.getAddress()); // Does not verify hostname

// The call below may use the resolver; do not put it on an offline path.
// InetAddress named = InetAddress.getByName("api.example.com");
```

In systems requiring determinism, avoid placing reverse name lookup calls on hot logging paths, packet processing, IP comparisons, or access-control logic. Name resolution can be slow, fail, or return different results depending on the environment.

## 6. IP Address, Hostname, and Connection Port

`InetAddress` does not contain a port. `InetSocketAddress` pairs an address/name with a port, but **the chosen constructor affects lookup behavior**:

| How the endpoint is created | Consequence |
| --- | --- |
| `new InetSocketAddress(existingInetAddress, 443)` | IP address is already known; no hostname resolution needed when creating the endpoint |
| `new InetSocketAddress("api.example.com", 443)` | Attempts to resolve the hostname immediately upon creation; may return an object with `isUnresolved() == true` if resolution fails |
| `InetSocketAddress.createUnresolved("api.example.com", 443)` | Intentionally keeps the hostname unresolved; no lookup at creation time; useful when another layer (such as a proxy) will handle the name |
| `socketAddress.getHostString()` | Gets the host/IP as a string without triggering a reverse lookup |
| `socketAddress.getHostName()` | May perform a reverse lookup if the endpoint was created from an IP literal |

Illustrative snippet placed **inside a method that declares `throws UnknownHostException`** (not a standalone program):

```java
InetAddress fixedIp = InetAddress.getByAddress(
        new byte[] {(byte) 192, 0, 2, 42});

InetSocketAddress direct = new InetSocketAddress(fixedIp, 443);
InetSocketAddress deferred =
        InetSocketAddress.createUnresolved("api.example.invalid", 443);

System.out.println(direct.isUnresolved());        // false
System.out.println(deferred.isUnresolved());      // true
System.out.println(deferred.getHostString());     // api.example.invalid
```

This is only **creating the endpoint object**; calling `Socket.connect(...)` or sending data afterward is still a real network operation. An `unresolved` endpoint is not guaranteed to connect directly; whatever consumes it must know how to handle the hostname.

## 7. Advanced Edge Cases to Watch Out For

**IPv6 scope/zone:** Link-local addresses such as `fe80::1%3` need to specify the appropriate network interface. Sixteen raw IP bytes alone do not fully describe the zone. When you need to preserve the scope, use `Inet6Address.getByAddress(host, raw, scopeId)` or the overload taking `NetworkInterface`, verifying that the scope is meaningful on the running machine. Do not hardcode interface indices across machines. The `2001:db8::1` examples above are unscoped IPv6 addresses.

**IPv4/IPv6 and the environment:** Successful parsing does not guarantee that the actual network stack supports connecting via the corresponding IP version. Do not use an `instanceof` check to infer that the target host is reachable. Also do not assume a hostname has only one IP or that the order of resolved addresses is always fixed.

**Untrusted input:** Clearly separate "IP literal only" and "hostname allowed" policies. With hostnames, resolution results can change; if used to enforce network security rules, you must check **the actual IP used to connect**, not just the initial name string. If you only want to read a user-supplied IP without allowing implicit DNS queries, parse the literal first in a way that cannot fall back to the resolver.

**Error handling:** `UnknownHostException` can indicate invalid IP byte length in `getByAddress` or a name-not-found failure in `getByName(hostname)`. It is the same exception type, but **the causes and handling differ**: a byte-length error must fix the input, whereas a resolver error requires its own timeout/retry/reporting policy.

## 8. Self-Check Exercises

1. Given `byte[] {(byte) 203, 0, 113, 9}`, create an `InetAddress` without any lookup, print the exact IP string, and print the first octet as 0–255.
2. Does `InetAddress.getByAddress("my-service.internal", bytes)` assert that `my-service.internal` actually points to the IP in `bytes`? Why or why not?
3. An API accepts **dotted-quad IPv4 only**, but calls `InetAddress.getByName(userInput)` directly. What are the two main risks?
4. When you want to display the IP without performing a reverse name lookup, should you choose `getHostAddress()` or `getHostName()`? When creating an `InetSocketAddress` from a hostname string while deferring the lookup, which API should you choose?

**Answers:** (1) use `getByAddress`, `getHostAddress()`, and `address.getAddress()[0] & 0xFF`, yielding `203.0.113.9` and `203`; (2) no, the hostname is only an unverified label; (3) the string may be treated as a hostname and invoke the resolver, and certain shorthand IPv4 forms are accepted outside the four-octet policy; (4) `getHostAddress()` and `InetSocketAddress.createUnresolved(host, port)`.

## References

- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): `getByAddress`, `getByName`, `getHostName`, `getHostAddress`.
- [Java SE 17 — Inet4Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet4Address.html): accepted IPv4 representations.
- [Java SE 17 — Inet6Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet6Address.html): IPv6 literals and scopes.
- [Java SE 17 — InetSocketAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): resolved/unresolved endpoints and `getHostString()`.

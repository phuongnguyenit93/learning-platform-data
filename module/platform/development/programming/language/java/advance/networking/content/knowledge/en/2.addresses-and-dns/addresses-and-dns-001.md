# IPv4, IPv6, and Address Representation with InetAddress

When programming networking in Java, you need to distinguish between an **IP address** (a network-layer identifier), a **hostname** (a name that needs to be resolved), and a **port** (which identifies a service on a machine). This lesson focuses on how to read, represent, and classify IPv4/IPv6 addresses and work with `java.net.InetAddress`, `Inet4Address`, and `Inet6Address` on Java 17+.

After this lesson, you will be able to: recognize IPv4/IPv6 addresses and their usage scopes; explain why they are 4/16 bytes long; create an `InetAddress` from a literal, a hostname, or bytes; identify the difference between DNS resolution and address conversion; and handle link-local, CIDR, and socket endpoint cases.

## 1. IP Addresses and Hostnames Are Two Different Concepts

- An **IP address** is a binary value used by the Internet Protocol to route packets. IPv4 is 32 bits; IPv6 is 128 bits.
- An **IP literal** is how humans write an IP address as a string, such as `192.0.2.10` or `2001:db8::1`.
- A **hostname** is a name like `example.com`. A name may be resolved to zero, one, or more IPv4/IPv6 addresses. Resolution does not necessarily always query remote DNS: the operating system, hosts file, cache, and preconfigured resolvers may also participate.
- A **port** is a number from 0–65535 used in a TCP/UDP endpoint, for example host `192.0.2.10` at port `443`. `InetAddress` only carries IP address information (and may attach hostname information); to combine an address with a port, use `InetSocketAddress`.

Conceptual flow:

~~~text
"example.com" (hostname)
        |
        v
name resolver / DNS / hosts / cache
        |
        +----> IPv4 address (A) ----> Inet4Address
        |
        +----> IPv6 address (AAAA) --> Inet6Address
                                      |
                                      v
                             IP + port => endpoint
~~~

Do not treat an IP as the immutable identity of a website: a single hostname can return multiple IPs, an IP can change over time, and a single IP can serve multiple hostnames.

## 2. IPv4: 32 Bits, Four Octets

IPv4 is commonly written in **dotted decimal** notation consisting of four decimal numbers from 0–255, separated by dots:

~~~text
192.0.2.10
192 | 0 | 2 | 10
 8    8   8   8 bits = 32 bits = 4 bytes
~~~

Each octet is an unsigned byte at the protocol level. In Java, `byte` is signed (−128 to 127), so the octet `192` must be placed in a byte using `(byte) 192` and read back using `Byte.toUnsignedInt(value)` or `value & 0xff`.

**Addresses and network prefixes:** `192.0.2.10/24` has a 24-bit network prefix, equivalent to the subnet mask `255.255.255.0`. The `/24` part is CIDR notation used when referring to a network/subnet; it is **not** part of an IP literal that `InetAddress.getByName(...)` understands on its own. You must store and parse the prefix separately if you are building a subnet management tool.

Common groups:

| IPv4 range/example | Meaning to remember |
| --- | --- |
| `127.0.0.0/8`, commonly `127.0.0.1` | Loopback, communication right on the same machine |
| `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | Private addresses, not directly routed on the public Internet |
| `169.254.0.0/16` | IPv4 link-local, typically auto-configured by the machine on the local link |
| `0.0.0.0` | Unspecified address; when binding a server, usually represents all suitable IPv4 interfaces |
| `224.0.0.0/4` | IPv4 multicast |
| `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` | Ranges reserved for documentation/examples; do not use as real server targets |

Do not equate `0.0.0.0` with an address a server can connect to, and do not assume every non-public address is loopback. IPv4 broadcast also depends on the subnet; for example, the traditional broadcast of `192.0.2.0/24` is `192.0.2.255`, and there is no rule that “every address ending in .255 is a broadcast”.

## 3. IPv6: 128 Bits, Eight Hextets

IPv6 consists of eight 16-bit groups represented in hexadecimal, separated by colons. Each group has one to four hex digits:

~~~text
2001:0db8:0000:0000:0000:0000:0000:0001
   = 2001:db8:0:0:0:0:0:1
   = 2001:db8::1
~~~

Compression rules:

1. Leading `0`s in each group can be omitted (`0db8` becomes `db8`; an all-zero group becomes `0`).
2. A consecutive sequence of all-zero groups can be replaced with `::`, **at most once per address** so that all eight groups can still be unambiguously inferred.
3. The RFC 5952 presentation standard prefers the shortest form, lowercase hex letters, and consistent rules when choosing which zero sequence to compress; Java may return a different presentation string that still represents the same binary address.

For example, `::1` is IPv6 loopback, and `::` is IPv6 unspecified. `2001:db8::/32` is reserved for documentation; for example, `2001:db8:abcd::/48` represents a 48-bit prefix. Just like IPv4, a `/48` or `/64` prefix is **not** part of the contents of an `InetAddress` object.

Essential IPv6 scopes:

| IPv6 range/example | Role |
| --- | --- |
| `::1/128` | Loopback |
| `::/128` | Unspecified |
| `fe80::/10` | Link-local, for traffic within the local link |
| `fc00::/7` | Unique Local Address (ULA), commonly used internally |
| `ff00::/8` | Multicast |
| `2001:db8::/32` | Example/documentation range |

IPv6 **does not use broadcast** like IPv4; many corresponding functions use multicast (such as Neighbor Discovery). Never assume IPv6 always has Internet connectivity: reachability depends on configuration, routing, firewalls, and the network in use.

### Scope/zone ID on IPv6 link-local

Two different network interfaces can both see an address like `fe80::1`. When you need to select the right link interface, the string representation can include a **zone identifier**, such as `fe80::1%eth0` or `fe80::1%3`. Interface names and scope IDs vary across machines/OSes; code that hard-codes `eth0` is not portable.

`Inet6Address` provides `getScopeId()`, `getScopedInterface()`, and methods for creating scoped addresses. Do not confuse the `%` zone delimiter with part of the 128-bit address. For URIs containing an IPv6 literal, square brackets are required, and be careful to percent-encode the `%` character when a zone ID is present.

## 4. How Does Java Store IP Addresses?

Practical class diagram:

~~~text
java.net.InetAddress
    +-- java.net.Inet4Address  (4 bytes / IPv4)
    +-- java.net.Inet6Address  (16 bytes / IPv6)
~~~

`InetAddress` is the common type used when you do not yet know whether a hostname will return IPv4 or IPv6. You can identify the family via `instanceof Inet4Address` or `instanceof Inet6Address`; `getAddress()` returns a byte array in **network byte order** (the first byte is the most significant part); `getHostAddress()` returns the IP literal as a string.

| API | Function | Points to note |
| --- | --- | --- |
| `InetAddress.getByName(host)` | Returns one address for a hostname or IP literal | A hostname may require a resolver; the chosen address is not fixed |
| `InetAddress.getAllByName(host)` | Returns the addresses provided by the resolver | Order, count, and family depend on DNS/configuration/cache |
| `InetAddress.getByAddress(bytes)` | Creates an IP from 4 or 16 bytes | Does not query DNS to validate the address; a wrong-length byte array throws `UnknownHostException` |
| `getAddress()` | Gets the raw 4/16 bytes | Java's `byte` is signed; convert to unsigned when printing octets |
| `getHostAddress()` | Gets the numeric IP string | Do not rely on IPv6 shorthand formatting to compare addresses |
| `getHostName()` | Gets the associated hostname or looks up the name | May involve a reverse lookup; do not call on latency-sensitive threads without consideration |
| `getCanonicalHostName()` | Gets the canonical name via the resolution mechanism | May block/be slow, depends on the resolver |
| `isLoopbackAddress()`, `isAnyLocalAddress()`, `isLinkLocalAddress()`, `isMulticastAddress()` | Checks address properties | Classifies the address; does not verify that a server is running |
| `InetAddress.getLoopbackAddress()` | Gets the machine's loopback address | May return IPv4 or IPv6 depending on the environment |
| `InetAddress.getLocalHost()` | Resolves the local machine's name | Not guaranteed to be a public IP, an IP visible to external Internet clients, or all IPs of the machine |

`UnknownHostException` occurs when a name cannot be resolved or the address input is invalid for the corresponding API. A valid IP literal does not need DNS to convert to bytes; a hostname may require a network query. Do not use `getByName` as a pure IP syntax validator for untrusted input, because a non-literal string can trigger name resolution.

## 5. Java 17+ Example: Parsing, Family, and Unsigned Bytes

Create the file `AddressBasics.java`:

~~~java
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;

public class AddressBasics {
    public static void main(String[] args) throws UnknownHostException {
        InetAddress ipv4 = InetAddress.getByName("192.0.2.10");
        InetAddress ipv6 = InetAddress.getByName("2001:db8::1");
        InetAddress expanded =
                InetAddress.getByName("2001:0db8:0:0:0:0:0:1");

        System.out.println("IPv4 literal: " + ipv4.getHostAddress());
        System.out.println("IPv4 type: " + (ipv4 instanceof Inet4Address));
        System.out.println("IPv4 bytes: " + ipv4.getAddress().length);
        System.out.println("IPv4 first octet: "
                + Byte.toUnsignedInt(ipv4.getAddress()[0]));
        System.out.println("IPv6 type: " + (ipv6 instanceof Inet6Address));
        System.out.println("IPv6 bytes: " + ipv6.getAddress().length);
        System.out.println("IPv6 same address: " + ipv6.equals(expanded));
        System.out.println("IPv6 loopback: " + ipv6.isLoopbackAddress());
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac AddressBasics.java
java AddressBasics
~~~

Deterministic output of the program:

~~~text
IPv4 literal: 192.0.2.10
IPv4 type: true
IPv4 bytes: 4
IPv4 first octet: 192
IPv6 type: true
IPv6 bytes: 16
IPv6 same address: true
IPv6 loopback: false
~~~

Explanation:

- `getByName("192.0.2.10")` and `getByName("2001:db8::1")` accept **literals**, without needing a hostname lookup. These are documentation ranges used to illustrate parsing.
- `getAddress().length` demonstrates the difference between 4 bytes and 16 bytes.
- `Byte.toUnsignedInt` converts a signed Java `byte` into an octet value from 0–255.
- Both the compressed and full IPv6 forms represent the same 128 bits, so `equals` returns `true`. Compare objects/bytes rather than comparing literal strings.

## 6. Creating an InetAddress Directly from Bytes Without Name Resolution

Create the file `RawAddress.java`:

~~~java
import java.net.InetAddress;
import java.net.UnknownHostException;

public class RawAddress {
    public static void main(String[] args) throws UnknownHostException {
        byte[] raw4 = {(byte) 192, 0, 2, 10};
        InetAddress ipv4 = InetAddress.getByAddress(raw4);

        byte[] raw6 = new byte[16];
        raw6[0] = 0x20;
        raw6[1] = 0x01;
        raw6[2] = 0x0d;
        raw6[3] = (byte) 0xb8;
        raw6[15] = 1; // 2001:db8::1
        InetAddress ipv6 = InetAddress.getByAddress(raw6);

        System.out.println("IPv4: " + ipv4.getHostAddress());
        System.out.println("First octet: "
                + Byte.toUnsignedInt(ipv4.getAddress()[0]));
        System.out.println("IPv6 class: "
                + ipv6.getClass().getSimpleName());
        System.out.println("IPv6 byte count: "
                + ipv6.getAddress().length);
        System.out.println("Same IPv6: "
                + ipv6.equals(InetAddress.getByName("2001:db8::1")));
    }
}
~~~

~~~bash
javac RawAddress.java
java RawAddress
~~~

Output:

~~~text
IPv4: 192.0.2.10
First octet: 192
IPv6 class: Inet6Address
IPv6 byte count: 16
Same IPv6: true
~~~

`getByAddress(byte[])` only accepts arrays of exactly **4 or 16 bytes**. Byte order is big-endian/network order; do not reverse bytes based on CPU endianness. Given a 5-byte array, the API throws `UnknownHostException`. The `getByAddress(String host, byte[] addr)` overload lets you attach a hostname label, but it **does not verify** that the hostname actually points to that IP; do not treat this label as DNS proof.

**IPv4-mapped IPv6:** The form `::ffff:192.0.2.10` represents an IPv4 address within the 128-bit syntax space. Java's `InetAddress`/`Inet6Address` APIs may accept this form as input but convert it into an IPv4 object, so you should not infer the address family merely from whether the input string contains a `:`. When needed, check the actual object using `instanceof` and `getAddress().length`.

## 7. Resolving a Hostname: Both A and AAAA May Exist

For a real hostname, use `getAllByName` if you want to observe the addresses provided by the resolver. Create `ResolveHost.java`:

~~~java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.UnknownHostException;

public class ResolveHost {
    public static void main(String[] args) {
        String host = args.length > 0 ? args[0] : "example.com";
        try {
            InetAddress[] addresses = InetAddress.getAllByName(host);
            for (InetAddress address : addresses) {
                String family =
                        address instanceof Inet4Address ? "IPv4" : "IPv6";
                System.out.printf("%s: %s%n",
                        family, address.getHostAddress());
            }
        } catch (UnknownHostException e) {
            System.err.println("Could not resolve " + host
                    + ": " + e.getMessage());
        }
    }
}
~~~

~~~bash
javac ResolveHost.java
java ResolveHost example.com
~~~

**Non-deterministic output:** The result may be one or more IPv4/IPv6 lines; the IPs, their order, and even whether resolution succeeds all depend on DNS/resolver, cache, address selection policy, and network connectivity. Do not hard-code a current IP of `example.com` as the expected output. In real systems, DNS may return multiple addresses for load balancing or failover; a connecting application must handle the case where one target is unavailable.

Paths to distinguish:

1. Parse an IP literal: `"192.0.2.10"` → address bytes, no name query needed.
2. Forward resolution: `"example.com"` → set of addresses from the resolver (typically via DNS A/AAAA and system configuration).
3. Reverse resolution: IP → hostname via reverse lookup (typically using DNS PTR); results are not guaranteed to exist or reflect the original name. `getHostName()`/`getCanonicalHostName()` may incur latency.
4. TCP/UDP connection: choose an address + port, then use the appropriate socket/client. `InetAddress` by itself does not open a connection.

Java and the resolver may cache lookup results. Do not assume that changing a DNS record will affect running connections or that every `getByName` call will immediately return the new IP.

## 8. IP Addresses in URLs and Endpoints

An IP address **does not contain a port**. Java represents a socket endpoint via `InetSocketAddress`:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;

InetAddress loopback = InetAddress.getLoopbackAddress();
InetSocketAddress endpoint = new InetSocketAddress(loopback, 8080);
// endpoint.getAddress(): IP address
// endpoint.getPort(): 8080
~~~

The code above is a **snippet**, not a standalone program; place it inside a method with appropriate exception handling when modifying it to use a hostname. `InetSocketAddress` only constructs endpoint information; it does not guarantee that a machine/service is listening.

In a URI/URL, an IPv6 literal must be enclosed in square brackets to distinguish the `:` characters of the address from the `:` before the port:

~~~text
http://192.0.2.10:8080/path
http://[2001:db8::1]:8080/path
~~~

For example, `http://2001:db8::1:8080/path` is not a valid representation of an HTTP authority containing an IPv6 address and port. The documentation addresses in the examples are only for syntax illustration; they are not reachable servers. When using IPv6 link-local with a zone ID in a URI, there are also specific percent-encoding rules; do not construct URIs by arbitrary string concatenation.

## 9. Choosing the Right Address and Recognizing Common Mistakes

- **Confusing IPv4 with IPv6 by punctuation:** `InetAddress` is the common type, and IPv4-mapped addresses can be converted by Java to `Inet4Address`. Check the family using the actual class or byte length.
- **Comparing IPv6 strings:** `2001:db8::1` and `2001:0db8:0:0:0:0:0:1` are the same address. `getHostAddress()` does not necessarily preserve the input formatting. Use `equals` for addresses, while also considering the IPv6 scope when an address requires an interface.
- **Treating Java `byte` as an unsigned octet:** printing `(byte) 192` directly can produce `-64`; use `Byte.toUnsignedInt`.
- **Passing `/24` or `/64` inside a literal:** CIDR is an address **with a prefix**, whereas `InetAddress` only holds an address. Network/subnet parsing is a separate responsibility.
- **Forgetting link-local scope:** `fe80::...` may require a specific zone/interface for routing and cannot be treated as an ordinary global destination.
- **Assuming `getLocalHost()` returns a public IP:** a machine can have multiple NICs, loopbacks, NAT, and containers; the method's value depends on the local system.
- **Assuming `getByName` is just a format check:** a hostname can trigger DNS or the resolver and fail or be slow; validate untrusted input, set timeouts on network threads, and avoid arbitrary synchronous lookups in latency-sensitive tasks.
- **Trusting `isReachable(timeout)` as a service test:** the result depends on ICMP, permissions, firewalls, and the network environment; `true` does not mean an application port is working, and `false` does not conclusively prove the host is completely down.
- **Assuming a hostname has only one address:** `getByName` selects one of the results; dual-stack applications should consider IPv4/IPv6 selection policies, failure handling, and the connection library's fallback mechanism.
- **Hard-coding the IP of a DNS-backed service:** IPs can change. When an application needs continuity, use the hostname with an appropriate resolution/connection policy.

## 10. Self-Check

1. How many bytes does `192.0.2.10` require? What about `2001:db8::1`? **Answer:** 4 and 16 bytes, respectively; the same `getAddress()` method returns the corresponding length.
2. Are the two strings `2001:db8::1` and `2001:0db8:0:0:0:0:0:1` two different addresses? **No.** They represent the same 128 bits, which can be verified with `InetAddress.equals`.
3. Why can `InetAddress.getByName("example.com")` be slow while `getByAddress(new byte[]{127,0,0,1})` does not need DNS? **Because** the first call resolves a hostname using the resolver; the second call already receives the binary address.
4. To connect to IPv6 `2001:db8::1` on port `443`, is a single `InetAddress` enough information? **No.** You need both the address **and the port** (for example via `InetSocketAddress`) before creating a connection. This is a documentation address, not a real server.
5. Why does accessing `fe80::1` sometimes require `%interface`? **Because** IPv6 link-local is only meaningful within a single link and a machine may have multiple interfaces; the zone specifies the scope for sending packets.

## Technical References

- [Java SE 21: InetAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html) — parsing methods, resolver, bytes, and address attributes.
- [Java SE 21: Inet4Address](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Inet4Address.html) and [Inet6Address](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Inet6Address.html) — formatting, IPv4-mapped, and scoped IPv6.
- [RFC 4291](https://www.rfc-editor.org/rfc/rfc4291) (IPv6 Addressing Architecture), [RFC 5952](https://www.rfc-editor.org/rfc/rfc5952) (IPv6 representation), and [RFC 4007](https://www.rfc-editor.org/rfc/rfc4007) (IPv6 Scoped Address Architecture).

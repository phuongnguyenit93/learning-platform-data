# IDN and Converting Internationalized Domain Names to ASCII Representation in Java

A URL like `https://bücher.example/sách` has a **hostname containing a Unicode character** (`ü`) and a Vietnamese path. Humans want to read domain names naturally, but many DNS interfaces, URIs, and networking libraries require hostnames in ASCII form. **IDN (Internationalized Domain Name)** addresses this need through **ASCII-Compatible Encoding (ACE)**. Java provides the `java.net.IDN` class to convert domain names between Unicode and ACE.

This lesson is part of the **URI and URL** topic, focusing on how to convert **only the hostname part** to ASCII, distinguish it from URI percent-encoding, and understand the API's limitations when validating or securing domain names. The examples use the `.example` domain reserved for documentation; no network or DNS is needed to run them.

After this lesson, you will be able to:
- Explain IDN, **U-label, A-label, ACE, Punycode**, and why DNS requires an ASCII representation.
- Use `IDN.toASCII()`, `IDN.toUnicode()`, and flags on Java 17+.
- Combine IDN with `java.net.URI` while preserving the correct scheme, port, path, query, and fragment.
- Recognize the differences between Java's IDNA2003 and IDNA2008/UTS #46, as well as homograph risks.

## 1. From Unicode Hostname to A-label

A domain name consists of multiple **labels** separated by dots. For example, `shop.bücher.example` consists of the labels `shop`, `bücher`, and `example`. Instead of forcing users to type domain names in ASCII, IDNA defines a compatible representation for internationalized labels.

| Term | Meaning | Example |
| --- | --- | --- |
| IDN | Internationalized domain name with one or more internationalized labels | `bücher.example` |
| U-label | Valid Unicode label according to IDNA2008 terminology | `bücher` |
| A-label | Valid ASCII representation of a U-label, starting with `xn--` | `xn--bcher-kva` |
| ACE | Method for representing internationalized labels using ASCII characters | `xn--bcher-kva` |
| Punycode | Encoding algorithm used to generate the part after the ACE prefix | `bcher-kva` |
| LDH label | ASCII hostname label using letters, digits, and hyphens | `shop`, `example` |

Process:

~~~text
Unicode hostname:     bücher.example
                        |
                        | IDN.toASCII(...)
                        v
ASCII hostname:       xn--bcher-kva.example
                        |
                        | IDN.toUnicode(...)
                        v
Unicode for display:  bücher.example
~~~

Important distinctions:

1. **Punycode encodes each label individually**, not the entire URL; the pure ASCII part `example` is kept as is.
2. Not every string starting with `xn--` is a valid A-label: it must also be decodable, correspond to a valid U-label under the chosen standard, and comply with label rules.
3. `IDN.toASCII` only performs **in-place string conversion**. It does not query DNS, nor does it prove that the name exists, has A/AAAA records, or that a server has an open port.
4. `IDN` handles domain names; it does not know about `https://`, `:443`, or the `/books` path.

For example, `bücher` converts to `xn--bcher-kva`. You should not strip the accent from `ü` or manually replace it with `u`, because the resulting domain name may be **different** from the one the user intended to visit.

## 2. How Does IDN Differ from Percent-Encoding and URL-Encoding?

There are three different groups of operations that all deal with non-ASCII characters but serve different purposes:

| What needs handling | Mechanism | Example |
| --- | --- | --- |
| Unicode in **hostname** for DNS/URI authority | IDNA/ACE via `IDN.toASCII` | `bücher.example` → `xn--bcher-kva.example` |
| Unicode/spaces in **URI path or query** | Percent-encoding (usually with UTF-8) | `/cẩm nang` → `/c%E1%BA%A9m%20nang` |
| Form values in `application/x-www-form-urlencoded` format | `URLEncoder` | Spaces in form data can become `+` |

Do not do this:

~~~java
// WRONG purpose: URLEncoder does not produce an A-label for a DNS hostname.
String host = java.net.URLEncoder.encode(
        "bücher.example", java.nio.charset.StandardCharsets.UTF_8);
~~~

This snippet illustrates an incorrect usage, not a solution. `URLEncoder` uses form encoding rules, whereas `IDN.toASCII` uses IDNA/Punycode. Likewise, **do not** call `IDN.toASCII` on `/cẩm nang` or a query string.

Visualizing the full address:

~~~text
https://bücher.example:8443/cẩm nang?lang=vi#intro
|---|   |------------|     |-------| |-----| |---|
scheme       host      port    path      query fragment

             Part needing IDN.toASCII
             |------------|
https://xn--bcher-kva.example:8443/c%E1%BA%A9m%20nang?lang=vi#intro
~~~

The host is a separate component; the port is a number, and the path/query have their own quoting rules. Mixing everything into a single conversion breaks the URI structure.

## 3. The `java.net.IDN` Class and Processing Flags

`java.net.IDN` is a utility class with static methods; the API has been available since Java 6 and works on Java 17+.

| API | Purpose | Notable behavior |
| --- | --- | --- |
| `IDN.toASCII(String)` | Unicode or already-ASCII hostname → ACE | Equivalent to `toASCII(input, 0)` |
| `IDN.toASCII(String, int flags)` | Conversion with options | Throws `IllegalArgumentException` if rules are violated |
| `IDN.toUnicode(String)` | ACE → Unicode for display | Leaves corresponding data unchanged if it cannot convert |
| `IDN.toUnicode(String, int flags)` | Decoding with flags | Not a tool for certifying a valid domain |
| `IDN.USE_STD3_ASCII_RULES` | Stricter checking of ASCII hostname rules | For example, `bad_name.example` is rejected |
| `IDN.ALLOW_UNASSIGNED` | Allows Unicode code points unassigned under Unicode 3.2 of this mechanism | Not enabled by default for untrusted user input |

Usage snippet inside a method (requires `import java.net.IDN;`):

~~~java
String asciiHost = IDN.toASCII(
        unicodeHost, IDN.USE_STD3_ASCII_RULES);
String displayHost = IDN.toUnicode(asciiHost);
~~~

**Errors and validation:** `toASCII` can throw `IllegalArgumentException` if a label is invalid according to RFC 3490 and the active flags. Catch the exception to report an error to the user; do not catch it and silently fall back to the unconverted string. According to the Java API, `toUnicode` does not fail by throwing a conversion error: when it cannot convert, the content may be returned unchanged, so a successful call cannot be treated as proof of a valid domain name.

**Dots and labels:** Java recognizes `.` (U+002E), `。` (U+3002), `．` (U+FF0E), and `｡` (U+FF61) as label separators; `toASCII` output uses the standard ASCII dot. `example.com.` has a trailing root dot and can be preserved as such; do not strip it automatically if the application needs to preserve absolute name semantics. Empty labels in the middle, such as `a..example`, are not valid normal hostnames.

**STD-3:** With `USE_STD3_ASCII_RULES`, Java applies stricter ASCII hostname rules, such as rejecting underscores `_` or leading/trailing hyphens in a label. This is a very useful flag, but it **does not replace** domain validation according to product policy, registry rules, or anti-spoofing checks.

## 4. Complete Program: `toASCII` and `toUnicode`

Create the file **`IdnBasics.java`**, encoded in UTF-8:

~~~java
import java.net.IDN;

public class IdnBasics {
    public static void main(String[] args) {
        String unicodeHost = "bücher.example";
        String asciiHost =
                IDN.toASCII(unicodeHost, IDN.USE_STD3_ASCII_RULES);

        System.out.println("Unicode: " + unicodeHost);
        System.out.println("ASCII: " + asciiHost);
        System.out.println("Display: " + IDN.toUnicode(asciiHost));
        System.out.println("Mapped: " + IDN.toASCII("faß.example"));

        try {
            IDN.toASCII("bad_name.example", IDN.USE_STD3_ASCII_RULES);
            System.out.println("Accepted bad_name");
        } catch (IllegalArgumentException e) {
            System.out.println("Rejected bad_name");
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 IdnBasics.java
java IdnBasics
~~~

Output on a Unicode-capable terminal:

~~~text
Unicode: bücher.example
ASCII: xn--bcher-kva.example
Display: bücher.example
Mapped: fass.example
Rejected bad_name
~~~

Explanation:

- The string `bücher.example` is converted to `xn--bcher-kva.example` label by label, without accessing DNS.
- `toUnicode` decodes the A-label into a human-readable string, used for the user interface when appropriate under the display policy.
- Java maps `faß` to `fass` due to **IDNA2003 mapping**. Therefore, you cannot assume `toUnicode(toASCII(s)).equals(s)` for all Unicode inputs.
- `bad_name.example` violates ASCII hostname rules when STD-3 is enabled; the program catches the error and prints a deterministic message that does not depend on the JDK's error message text.

`.example` is a name reserved for documentation and does not require a real website to exist. The program above is a pure Java parsing example with deterministic stdout.

## 5. Combining IDN with `java.net.URI` and `java.net.URL`

For URLs with internationalized hostnames, handle them along proper component boundaries:

1. Receive/inspect the **hostname** separately, e.g. `bücher.example`. When starting from a full URL, you need a parser compliant with URI/IRI syntax to extract components without confusing `userinfo@`, IPv6 literals, ports, or delimiters.
2. Convert the hostname using `IDN.toASCII(host, IDN.USE_STD3_ASCII_RULES)`.
3. Apply validation and policy to the resulting host; keep the scheme, port, path, query, and fragment intact.
4. Construct a `URI` using a component constructor such as `new URI(scheme, userInfo, host, port, path, query, fragment)`. This constructor quotes characters as needed in the path/query.
5. When an ASCII representation is needed, use `uri.toASCIIString()`; an HTTP client can accept the constructed URI and perform DNS/TLS according to its configuration.

**Important pitfall:** `URI.toASCIIString()` **does not convert a Unicode hostname to Punycode**. It percent-encodes non-ASCII characters in the URI representation. In Java, `URI.create("https://bücher.example/").getHost()` can return `null` because the parser does not recognize that Unicode authority as a valid server-host; `getRawAuthority()` may still hold the raw authority. Therefore, do not pass a Unicode authority to `URI.create` and assume Java has normalized it for DNS IDN.

Do not call:

~~~java
// WRONG: passing the entire URI to an API that only accepts a hostname.
String wrong = java.net.IDN.toASCII(
        "https://bücher.example:8443/cẩm nang");
~~~

And do not extract the hostname using `split(":")` or manual string replacement. This is especially error-prone with IPv6 literals `[2001:db8::1]`, userinfo containing `@`, ports, queries, and fragments. `IDN` handles **domain names**, not IPv4/IPv6 literals.

The `URL` class also has `getHost()`, but the fact that a URL string can be parsed should not be taken as proof that the hostname has been converted, resolved, or certified safe. In new code, it is generally better to build a `URI` from valid components and pass it to the HTTP client.

## 6. Complete Program: IDN Hostname and Unicode Path in a URI

Create the file **`IdnUriDemo.java`** in UTF-8:

~~~java
import java.net.IDN;
import java.net.URI;
import java.net.URISyntaxException;

public class IdnUriDemo {
    public static void main(String[] args) throws URISyntaxException {
        String unicodeHost = "bücher.example";
        String asciiHost =
                IDN.toASCII(unicodeHost, IDN.USE_STD3_ASCII_RULES);

        URI uri = new URI(
                "https",        // scheme
                null,           // userInfo
                asciiHost,      // host: converted to ACE
                8443,           // port
                "/cẩm nang",    // Unicode path
                "lang=vi",      // query
                null            // fragment
        );

        System.out.println("Host: " + uri.getHost());
        System.out.println("Port: " + uri.getPort());
        System.out.println("Path: " + uri.getPath());
        System.out.println("ASCII URI: " + uri.toASCIIString());

        URI raw = URI.create("https://" + unicodeHost + "/");
        System.out.println("Raw host recognized: " + (raw.getHost() != null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 IdnUriDemo.java
java IdnUriDemo
~~~

Output:

~~~text
Host: xn--bcher-kva.example
Port: 8443
Path: /cẩm nang
ASCII URI: https://xn--bcher-kva.example:8443/c%E1%BA%A9m%20nang?lang=vi
Raw host recognized: false
~~~

The two types of conversion are clearly shown:
- `getHost()` has the A-label value `xn--bcher-kva.example` and `getPort()` is `8443`.
- `getPath()` returns the Unicode path. In `toASCIIString()`, the character `ẩ` and the space in the path are percent-encoded using UTF-8; the hostname remains the A-label.
- The last line illustrates that `URI` parses the Unicode authority but does not recognize it as a server-host. You must convert the host separately before constructing the `URI`.
- `throws URISyntaxException` only keeps the example short. Production code should catch/transform errors into clear validation results; also remember that creating a `URI` **does not open a network connection**.

When passing this URI to an HTTP client, the domain name used for routing still has to go through DNS; successfully creating the object does not guarantee that DNS, TLS, or HTTP will succeed.

## 7. Validate and Canonicalize at the Right Layer

`IDN.toASCII` is a conversion step with some syntax checks; it **does not** check the full web address policy.

### Checking DNS Structure After Converting to ACE

- A DNS label is at most **63 octets**; a DNS name on the wire is at most **255 octets** including the length octets of the labels and the root. For a text-form name without a trailing root dot, the commonly applied limit is **253 ASCII characters**.
- **Check length after `toASCII`**. A short-looking Unicode string can expand into a longer A-label.
- For standard hostnames, ASCII labels follow the LDH (letter, digit, hyphen) rule and must not have hyphens at either end. `USE_STD3_ASCII_RULES` helps enforce many of these constraints.
- DNS in general allows name types other than HTTP hostnames. For example, service labels in specialized records may contain `_`; do not accidentally apply a web hostname validator to every kind of DNS name.
- Distinguish domains with a trailing dot like `example.com.` from `example.com` according to your specific policy; do not strip the root dot automatically.

### Canonicalization for Comparison and Storage

ASCII hosts in DNS are compared **case-insensitively**. For a consistent application policy, you can store the A-label in lowercase using `Locale.ROOT` (and standardize the root-dot rule). Example snippet:

~~~java
import java.net.IDN;
import java.util.Locale;

String canonicalHost = IDN.toASCII(
        "BÜCHER.example", IDN.USE_STD3_ASCII_RULES
).toLowerCase(Locale.ROOT);
~~~

This snippet is **not standalone**; place it inside a class/method when using it. `Locale.ROOT` is for canonical case conversion independent of the device locale. Do not manually "strip accents" or use `String.toLowerCase()` as a substitute for the IDNA algorithm.

If you need to display the exact name the user entered, store the original value separately; **do not assume** `IDN.toUnicode(IDN.toASCII(input))` restores the original. The A-label is suitable as a canonical key under the chosen policy, while the original Unicode string may be needed for UX, auditing, or troubleshooting.

### A Successfully Converted Hostname Is Still Not Trusted

- `toASCII` does not prove that the TLD allows label registration, that the domain exists, or that DNS returns valid records.
- It does not prove that the TLS certificate is trustworthy, that the site belongs to the expected brand, or that the connection will succeed.
- If the server itself opens user-supplied URLs, you must check the scheme/port, redirects, DNS resolution, and target IP according to an SSRF protection policy. IDN canonicalization **does not** replace those validation layers.

## 8. Java's IDNA2003 vs. IDNA2008 and UTS #46

This is a technical point that easily causes bugs when two libraries or browsers produce different results.

**Java SE 17/21's `java.net.IDN` is documented according to RFC 3490 (IDNA2003)**, with Nameprep/Punycode and rules tied to Unicode 3.2. The web ecosystem also uses **IDNA2008** (RFC 5890–5895) and **UTS #46** to handle mapping/compatibility under different policies and Unicode versions.

Example with `ß`:

~~~text
Unicode input:  faß.example

Java IDN / IDNA2003:
    IDN.toASCII(...)   -> fass.example
    IDN.toUnicode(...) -> fass.example

A compliant IDNA2008 flow can preserve the character ß,
and encode the label "faß" into its own A-label instead of "fass".
~~~

Because mapping occurs in the initial step, round-tripping does not preserve all original characters:

~~~text
"faß.example" --> toASCII --> "fass.example"
                                 |
                                 v
                               toUnicode
                                 |
                                 v
                            "fass.example"
~~~

You should not conclude that one of two libraries is "wrong" when their results differ without first identifying the **IDNA standard, Unicode version, and mapping mode** of each side. If strict compatibility with browsers/registries using IDNA2008 or UTS #46 is required, choose an appropriate library and workflow, and test specific Unicode cases. `USE_STD3_ASCII_RULES` does not turn IDNA2003 into IDNA2008; `ALLOW_UNASSIGNED` only changes how unassigned code points are handled under Java's mechanism, not a switch for "latest Unicode".

### U-label/A-label and Version Terminology

In RFC 5890, an **A-label** must be a **valid** ACE label, not just any string with the `xn--` prefix; a **U-label** must be valid under the relevant IDNA2008 rules (including normalization/Unicode). Java `IDN` uses terminology and algorithms from RFC 3490; when explaining or designing APIs, explicitly state which standard is being used.

## 9. Security: Homographs, Confusables, Spoofing

Internationalized domain names can contain characters that **look alike but have different code points**. For example, the Latin character `a` (U+0061) and the Cyrillic character `а` (U+0430) are two different characters even though they may look nearly identical in some fonts. Attackers can exploit this visual similarity to create hostnames that deceive users.

What `IDN.toASCII` and `IDN.toUnicode` **do not do**:

- Do not detect all confusable characters, mixed scripts, or similarity to an organization's name.
- Do not prove that the hostname belongs to a brand or has a valid HTTPS certificate.
- Do not verify that an A-label/Unicode string is safe to display in all browsers/UIs.
- Do not prevent the host from resolving to a private/loopback IP when the URL is accessed by a server.
- Do not prevent DNS rebinding or dangerous redirects.

Depending on the product, you can apply an allowed character/script policy, check for confusables per Unicode UTS #39, display the A-label in suspicious cases, log both the canonical A-label and the original name, and let the TLS/HTTP stack perform hostname and certificate verification. For inputs used to fetch URLs server-side, control DNS/IP/redirects independently of IDN. When logging or comparing hostnames, do not compare only the displayed Unicode strings because different characters can look visually identical.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| `IDN.toASCII("https://bücher.example/a")` | Passing the entire URI to an API meant for hostnames | Extract the hostname and convert it separately |
| `URLEncoder.encode(host, UTF_8)` | That is form encoding, not an A-label | Use `IDN.toASCII` |
| `URI.toASCIIString()` to do Punycode | Only percent-encodes Unicode in the URI, does not normalize IDNA host | Convert the host before building the `URI` |
| Stripping accents or transliterating domains to Latin with custom code | May turn it into a different domain name | Use standard-compliant IDNA mapping |
| Treating every `xn--...` label as valid | There are "fake A-labels" and other IDNA conditions | Use standard-compliant validation and policy |
| Assuming `toUnicode(toASCII(s))` must return `s` | Mapping can replace `ß` with `ss` | Store the original input if reproduction is needed |
| Treating a successful `toASCII` as a trusted host | Does not check DNS, HTTPS, spoofing, or policy | Validate at the network/security layer |
| Extracting host with `split(":")` | Confuses IPv6, port, and userinfo | Use a syntax-aware component parser |
| Comparing raw Unicode hostnames case-sensitively | Ignores ACE/canonicalization and IDNA rules | Under the same IDNA policy, compare on the A-label |
| Not checking length after encoding | An A-label can be longer than the visible Unicode | Check DNS limits after conversion |

## 11. Exercises and Answers

**1.** What ASCII hostname should `bücher.example` be converted to? Should `https://` and `/path` also be converted?

**Answer:** `xn--bcher-kva.example`. Only the hostname is converted via IDNA; the scheme and path follow their own rules.

**2.** Why does `toUnicode(toASCII("faß.example"))` in Java no longer contain `ß`?

**Answer:** IDNA2003 mapping converts `ß` to `ss`, producing `fass.example`; the reverse conversion does not know that the user originally typed `ß`.

**3.** What can `URI.create("https://bücher.example/").getHost()` return, and what should you do?

**Answer:** It can return `null` because the Unicode authority is not recognized by the parser as a server-host. Convert the domain name to an A-label and then construct the URI from its components.

**4.** Does `IDN.toASCII(host, IDN.USE_STD3_ASCII_RULES)` running successfully prove the domain is safe?

**Answer:** No. The API validates/converts the string; it does not verify DNS, IP, TLS, spoofing, or registration policy.

**5.** Should Punycode be applied to the path `/cẩm nang` or the label `bücher`?

**Answer:** To the domain label `bücher`. For an ASCII URI, the path is appropriately percent-encoded (UTF-8), not Punycode-encoded.

**6.** What is the maximum length of a DNS label in octets, and when is it measured?

**Answer:** 63 octets; measured **after** converting to ACE, when the actual ASCII label length used by DNS is known.

**7.** Is calling `toUnicode` alone enough to display any Unicode label safely?

**Answer:** No; IDNs carry homograph/confusable risks, requiring a display policy and context-appropriate checks.

## References

- [Java SE 21: java.net.IDN](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/IDN.html) — API, flags, ToASCII/ToUnicode, RFC 3490 compliance, and conversion limitations.
- [Java SE 21: java.net.URI](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html) — constructors, host parsing, and percent-encoding.
- [RFC 3490](https://www.rfc-editor.org/rfc/rfc3490), [RFC 3492](https://www.rfc-editor.org/rfc/rfc3492) — IDNA2003 and the Punycode algorithm.
- [RFC 5890](https://www.rfc-editor.org/rfc/rfc5890), [RFC 5891](https://www.rfc-editor.org/rfc/rfc5891) — U-label/A-label terminology and IDNA2008.
- [Unicode UTS #46](https://www.unicode.org/reports/tr46/) and [UTS #39](https://www.unicode.org/reports/tr39/) — compatible IDNA mapping and confusable character detection.

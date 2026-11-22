# Cookie Domain, Path, Secure, and Lifetime

## 1. Why understand cookie attributes in Java networking?

**HTTP is inherently stateless between requests.** A server can assign a session identifier via a **Set-Cookie** response; subsequent client requests will include **Cookie** if the cookie is still valid and matches the sending conditions. This allows the server to look up a logged-in session, shopping cart, or user preferences.

However, a cookie **is not sent to every URL**. When deciding whether to send it, the user agent (browser or HTTP client with a cookie store) evaluates **host/Domain**, **Path**, **Secure**, **lifetime**, and other policies such as **SameSite** or cookie partitioning.

This lesson focuses on the four factors stated in the title:

- **Domain:** does the cookie belong strictly to the host that created it, or can it be sent to subdomains?
- **Path:** which request paths match to send the cookie?
- **Secure:** is the cookie sent only over a secure HTTPS channel?
- **Lifetime:** is the cookie a session cookie or a persistent cookie; how do **Max-Age** and **Expires** interact?

It also explains how to use **java.net.CookieManager, HttpCookie, CookieStore, CookiePolicy** in **Java 17+**, where Java differs from modern browsers, and the impact of **proxies** on HTTP sessions.

**Security principle:** a cookie containing a session ID is a **bearer credential**. Anyone possessing a valid session value may be treated by the server as the owner of that session. Do not store passwords or raw sensitive data in cookies; use a sufficiently strong random session ID, TLS, cookie attributes, authorization checks, and server-side session lifecycle management.

## 2. Distinguishing Set-Cookie and Cookie

The server issues or updates a cookie using the **Set-Cookie response header**:

~~~http
HTTP/1.1 200 OK
Set-Cookie: session=abc123; Path=/account; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
Set-Cookie: theme=dark; Path=/; Secure; Max-Age=2592000
Content-Type: text/plain

Welcome
~~~

In the next request, if matching, the client sends only the **name=value** pairs in the **Cookie request header**:

~~~http
GET /account/profile HTTP/1.1
Host: shop.example.test
Cookie: session=abc123; theme=dark
~~~

Notes:

1. **Domain, Path, Secure, Max-Age, Expires, HttpOnly, SameSite** are **attributes in Set-Cookie** to instruct the user agent on storing/sending cookies; they are **not sent back as attributes in the standard Cookie header**.
2. Each cookie is issued via a **separate Set-Cookie field**. Do not fold multiple Set-Cookie fields into a single comma-separated field; in particular, Expires contains a comma from the HTTP-date format.
3. If the request does not match or the cookie has expired, the client does not include that cookie in the Cookie header.
4. The server must independently verify that the session value exists, is still valid, and is authorized to perform the requested action. **The fact that the client sends a Cookie does not mean the session is guaranteed to be valid.**
5. Cookies are HTTP-layer metadata. **TCP connection, TLS session, HTTP/2 stream, proxy connection**, and application login session are different concepts; reusing a connection does not alter cookie lifetime.

## 3. Domain: host-only and domain cookies

### 3.1. Without Domain: host-only cookie

Suppose an HTTPS response from **shop.example.test** contains:

~~~http
Set-Cookie: cart=A1; Path=/; Secure; HttpOnly; Max-Age=900
~~~

Omitting Domain means the cookie is **host-only**, bound to the issuing **shop.example.test**. A browser following RFC 6265 sends it to **shop.example.test** (if other conditions are met), but **not** to:

- **api.example.test**: a subdomain sharing the same parent but a different host.
- **a.shop.example.test**: a subdomain beneath the original host, not matching the exact host.
- **other.test**: a completely different host.

This is the safe default to use when other hosts do not need to share the cookie. Also keep in mind that cookies are generally **not isolated by port** under the browser model: different ports on the same host do not automatically create a strong cookie boundary; Path and Scheme must also be considered.

### 3.2. With Domain: allowing the same domain and subdomains

Response from **shop.example.test**:

~~~http
Set-Cookie: sharedSession=B2; Domain=example.test; Path=/; Secure; HttpOnly; Max-Age=900
~~~

Under modern browser cookie mechanics, Domain=example.test scopes the cookie to **example.test** and subdomains such as **shop.example.test** and **api.example.test**. Domain must have a valid relationship with the issuing host; a server at shop.example.test **cannot validly request Domain=other.test**.

The legacy form **Domain=.example.test** with a leading dot is handled by modern browsers similarly to Domain=example.test; the leading dot **no longer expands the scope further** under RFC 6265. However, Java's **java.net.CookieManager** is based on older RFC 2965 semantics and may handle leading dots differently; see the Java-specific section below.

**Pitfall:** Domain=example.test does not allow the cookie to be sent to **notexample.test** or **example.test.attacker.invalid**. Those are not valid domains/subdomains merely because they contain the substring example.test.

### 3.3. Do not allow clients to set cookies on a public suffix

Browsers typically use the **Public Suffix List** to prevent a site from issuing a cookie for a suffix shared by many independent entities, such as **Domain=com** or a public suffix like **co.uk**. A single tenant should not be allowed to set cookies for an entire shared suffix.

With multi-tenant services, wildcard DNS does not mean every tenant is entitled to share sessions. An overly broad cookie Domain can lead to **cookie tossing, session fixation, or name collisions** across subdomains.

**Recommended practice:** if cross-subdomain sharing is not needed, omit Domain altogether. If sharing among subdomains managed by the organization is truly required, set the narrowest possible Domain and design against session fixation.

### 3.4. Domain is not an authentication mechanism

A request carrying a Cookie that matches Domain only proves the client **sent a value**. It does not prove which user the cookie content belongs to or that the user has been granted authorization.

The server must still look up the session, check expiry/revocation, verify access rights, and defend against CSRF according to the threat model. For services sharing multiple subdomains, be cautious when a less-trusted subdomain could intentionally set a cookie with a broader Domain.

## 4. Path: which paths match and why it is not a security boundary

### 4.1. Cookies with a specific Path

Suppose:

~~~http
Set-Cookie: accountSession=X1; Path=/account; Secure; HttpOnly; Max-Age=900
~~~

According to browser **RFC 6265 path-match**, this cookie matches:

| Request URL path | Send cookie with Path=/account? | Explanation |
| --- | --- | --- |
| **/account** | Yes | Exact match |
| **/account/** | Yes | Path is a prefix and the next character is / |
| **/account/orders** | Yes | Subpath of /account |
| **/accounting** | **No** | After /account is the character i, not / |
| **/accounts** | **No** | Different path segment |
| **/** | No | Not under the /account branch |
| **/help** | No | Not under the /account branch |

The RFC 6265 algorithm is not just a **startsWith("/account")** check: the request path must equal the cookie path, or if the cookie path ends with / then the prefix matches, or the next character after the prefix must be **/**. The **/accounting** case is a very useful test to detect overly broad path-match implementations.

### 4.2. What is the default when Path is omitted?

If a response comes from the URL:

~~~text
https://shop.example.test/docs/guide/page.html
~~~

and Set-Cookie **omits Path**, a browser following RFC 6265 typically selects the directory containing the resource, i.e. **/docs/guide/**, as the default-path. Do not always assume the default cookie Path=/.

Examples:

| Issuing URL | Default Path under RFC 6265 |
| --- | --- |
| **https://x.example.test/** | / |
| **https://x.example.test/login** | / |
| **https://x.example.test/docs/page.html** | /docs/ |
| **https://x.example.test/docs/guide/page.html** | /docs/guide/ |

If the application needs the cookie across all paths on the host, **set Path=/** explicitly. If it is only needed under /account, set Path=/account to limit the cookie from being attached to unrelated endpoints.

### 4.3. Path is not a security boundary

**Path is only a cookie-sending selection mechanism**, not a security isolation mechanism like a process/container/origin. Pages on the same host with different paths can interact in ways that prevent Path from protecting secrets like an authentication mechanism.

For example, JavaScript code running on one path can send requests to another path on the same origin; cookies belonging to the target path can be attached by the browser when the request is valid. Therefore, **Path=/admin does not replace admin authorization checks on the server**.

Cookies with the same name but different Paths can coexist. When both match a request, the Cookie header may carry multiple pairs with the same name; **do not design authentication logic that relies on the ordering of the Cookie header string**. Avoid name collisions and use clear scoping rules.

### 4.4. Important differences with java.net.CookieManager

Java 17 documentation states that **CookieManager/HttpCookie** is tied to **RFC 2965** and historical rules, **not a complete RFC 6265 browser**. Therefore, Domain/path match details may differ from browsers; for example, some Java implementations use a broader path prefix and do not accurately reproduce the RFC 6265 **/accounting** case.

**Do not use a Java CookieManager result to assert that browsers will send the exact same cookie.** To test browser behavior, use a browser test aligned with modern policies and test path segment and domain/public suffix cases.

## 5. Secure: send cookies only over authenticated HTTPS

### 5.1. Exact meaning

~~~http
Set-Cookie: session=RANDOM_ID; Path=/; Secure; HttpOnly; Max-Age=900
~~~

**Secure** requires the client to send the cookie only over a secure channel per user agent policy, typically **HTTPS**. For the same host/path:

| Request | Is a Secure cookie sent? |
| --- | --- |
| **https://shop.example.test/account** | Yes, if Domain/Path/TTL and other conditions match |
| **http://shop.example.test/account** | No |
| **https://api.example.test/account** | Only if Domain allows api.example.test |
| **https://shop.example.test/other** | Only if Path matches |

Browsers have a **special exception for localhost** in some contexts; do not design production security around this exception. Secure does not mean **the cookie is encrypted while stored on the client disk**, nor does it automatically keep the cookie content secret from JavaScript.

### 5.2. How Secure differs from HttpOnly and SameSite

| Attribute | Primary protection | What it cannot protect against alone |
| --- | --- | --- |
| **Secure** | Restricts sending cookies over plaintext HTTP | Does not prevent JavaScript from reading the cookie without HttpOnly |
| **HttpOnly** | Prevents normal JavaScript access via document.cookie | Does not prevent valid HTTP requests from automatically sending the cookie; does not block all XSS consequences |
| **SameSite=Lax/Strict** | Reduces certain cases of cookies being automatically sent in cross-site requests | Does not replace full CSRF defenses and authorization |
| **Domain/Path** | Limits where the cookie is sent | Does not replace an independent security boundary |
| **Max-Age/Expires** | Limits how long the cookie persists on the client | Does not automatically invalidate a compromised server session |

With **SameSite=None**, modern browsers require **Secure**. For web app session cookies, the common policy is **Secure; HttpOnly; SameSite=Lax or Strict** depending on the business flow, plus a short lifetime and server-side CSRF checks when needed.

**HttpOnly is not a flag for the response body:** it is a Set-Cookie attribute. When JavaScript sends a fetch to a matching endpoint and the credential policy permits, the browser can still attach the HttpOnly cookie in the HTTP request even though the script cannot read its value via document.cookie.

### 5.3. Prefixes add stronger constraints in supporting browsers

Cookie names with prefixes provide additional enforcement:

~~~http
Set-Cookie: __Secure-session=A1; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: __Host-session=B2; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **__Secure-**: must be set from a secure origin and include Secure.
- **__Host-**: requires a secure origin, **Secure**, **Path=/**, and **no Domain**. Suitable when the cookie is meant strictly for the exact host and you do not want other subdomains setting a cookie with the same scope.
- Prefix rules are enforced by **user agents that support prefixes**; **do not assume legacy Java HttpCookie/CookieManager automatically enforces all prefixes, SameSite, and cookie partitioning** like modern browsers.

Prefixes are an additional defense layer. The backend must still verify the session ID and protect against session fixation.

## 6. Lifetime: session, Max-Age, Expires, and deleting cookies

### 6.1. Session cookie: without Max-Age/Expires

~~~http
Set-Cookie: session=abc; Path=/; Secure; HttpOnly
~~~

Under the browser cookie model, this is a **session cookie**, typically discarded when the browser session ends. However, many browsers have **session restore**, which can restore session cookies after reopening. **Do not assume closing a tab/browser is a secure logout operation**; the server needs separate session expiration and revocation.

In Java HttpCookie, **getMaxAge() defaults to -1** to represent a session-style cookie. CookieManager's default in-memory CookieStore **does not persist across JVM termination**, though this differs from browser session-restore mechanisms.

### 6.2. Max-Age is a relative duration in seconds

~~~http
Set-Cookie: cart=abc; Path=/; Max-Age=1800; Secure
~~~

**Max-Age=1800** means the cookie has a maximum lifetime of 1,800 seconds (30 minutes) from the time it is received/processed by the user agent per policy. Do not mistake this for milliseconds or a Unix timestamp.

**Max-Age=0** or a negative number per RFC/browsers is equivalent to immediate expiration, commonly used to delete a cookie:

~~~http
Set-Cookie: cart=; Path=/; Max-Age=0; Secure
~~~

In Java HttpCookie, **setMaxAge(0)** and **hasExpired()** express the same removal semantics; the negative value -1 represents a session cookie when constructing the object. Do not assume a negative Max-Age in header syntax behaves identically across all browsers; check the specific user agent.

### 6.3. Expires is an absolute timestamp

~~~http
Set-Cookie: cart=abc; Path=/; Expires=Wed, 21 Oct 2037 07:28:00 GMT; Secure
~~~

**Expires** is a UTC/GMT HTTP-date. The cookie expires after that timestamp according to the client's clock/policy. If the server and client clocks diverge, interpreting the expiration date can be unpredictable; modern browsers may adjust for clock skew based on the Date response header.

**Max-Age is usually easier to manage** when expressing "live for at most N seconds", though the backend must also maintain a corresponding session TTL. Do not rely solely on cookie expiration to invalidate a stolen token.

### 6.4. What if both Max-Age and Expires are present?

~~~http
Set-Cookie: cart=abc; Path=/; Max-Age=3600; Expires=Wed, 21 Oct 2037 07:28:00 GMT; Secure
~~~

According to RFC 6265, **Max-Age takes precedence** over Expires if both are valid. In the example, learners should calculate the lifetime as **3,600 seconds** rather than the year 2037 date.

This also explains why TLS certificate expiry, HTTP cache freshness, cookie Max-Age, and session database TTL are **four distinct time limits** and should not be lumped together as a single generic "session timeout".

### 6.5. Deleting the right cookie must match its identity

If a cookie was stored with **name=session**, **Domain=example.test**, and **Path=/account**, a deletion response should reuse the **exact name, Domain, and Path** of that cookie:

~~~http
Set-Cookie: session=; Domain=example.test; Path=/account; Max-Age=0; Secure; HttpOnly
~~~

If **Domain was omitted** when created (host-only), Domain should also be omitted when deleting and sent from the exact same host. If another cookie has the same name but a different Path, deleting Path=/ will not necessarily delete the Path=/account cookie. Partitioned cookies may also require considering the partition key; test with the actual user agent.

**Secure logout has two parts:** (1) mark the server-side session/token as expired or revoked, (2) send Set-Cookie to clear the client-side value. Clearing only the client cookie is insufficient if a copied token remains valid on the server.

### 6.6. Absolute TTL and idle timeout

For example, a security policy requires a session to expire after 30 minutes of **inactivity**, and no more than 8 hours since login. Cookie Max-Age=1800 can help represent the idle period if the server actively refreshes the cookie, but the backend must still track:

- **Created-at** / login timestamp.
- **Last activity** / most recent valid interaction.
- **Absolute expiration** / maximum age.
- **Revoked** / logout, password change, security event.

Do not extend a session indefinitely simply by repeatedly sending a new Set-Cookie Max-Age if the policy enforces an absolute expiration.

## 7. Matrix of Domain × Path × Secure × lifetime

Suppose an HTTPS response from **shop.example.test** issues the following cookies:

~~~http
Set-Cookie: hostLogin=H; Path=/account; Secure; HttpOnly; Max-Age=900
Set-Cookie: shared=S; Domain=example.test; Path=/; Secure; Max-Age=3600
Set-Cookie: theme=dark; Path=/; Secure; Max-Age=86400
Set-Cookie: obsolete=; Path=/account; Max-Age=0
~~~

**The results below follow RFC 6265 browser cookie rules**, assuming all cookies are unexpired except obsolete, same-site/security policies do not block further, and the issuing domain is valid:

| Request URL | Matching cookies | Why |
| --- | --- | --- |
| **https://shop.example.test/account/profile** | hostLogin, shared, theme | Matches host, path /account, HTTPS, unexpired |
| **https://shop.example.test/** | shared, theme | hostLogin only has Path=/account |
| **https://shop.example.test/accounting** | shared, theme | /accounting does **not** path-match /account under RFC 6265 |
| **https://api.example.test/account/profile** | shared | shared has Domain=example.test; the other two are host-only |
| **http://shop.example.test/account/profile** | None | All three live cookies are Secure, not sent over HTTP |
| **https://unrelated.test/account/profile** | None | Different domain |
| **https://shop.example.test/account/profile** after all three TTLs expire | None | Expired |
| **https://shop.example.test/account/profile** immediately after response | No obsolete | Max-Age=0 deletes immediately |

Common point of confusion: internally in Java CookieManager, **Path** may be handled per RFC 2965 and **Domain** per historical logic, so do not treat this browser table as hard expected output for Java CookieManager. The demo section below tests cases supported by the actual Java runtime and states the conditions clearly.

### How to read a request line properly

To decide whether to send a cookie, the client checks sequentially:

1. **Has the cookie expired or been deleted?** If so, skip.
2. **Does the host match host-only/Domain?** If not, skip.
3. **Does the request path path-match Path?** If not, skip.
4. **Does Secure require HTTPS?** If required and the request is insecure, skip.
5. **Do SameSite/partitioning/browser policies** allow the current request to carry the cookie? If not, skip.
6. If still eligible, place **name=value** into the Cookie request header; **do not** repeat the Set-Cookie attributes in that header.

This is a mental model; the exact internal check order may vary by user agent, and not all implementations guarantee the same policy.

## 8. Java 17: HttpCookie, CookieManager, CookieStore, and CookiePolicy

### 8.1. Components and responsibilities

| API | Role |
| --- | --- |
| **java.net.HttpCookie** | Object storing name/value, Domain, Path, Secure, HttpOnly, Max-Age; parses Set-Cookie in formats supported by Java |
| **java.net.CookieManager** | Implements CookieHandler.get/put, selects cookies to send and accepts cookies issued by servers |
| **java.net.CookieStore** | Storage for accepted cookies; CookieManager's default implementation is in-memory |
| **java.net.CookiePolicy** | Rules deciding which cookies are accepted, e.g., ACCEPT_ORIGINAL_SERVER, ACCEPT_NONE, ACCEPT_ALL |
| **java.net.CookieHandler** | Cookie management abstraction, usable as a JVM-wide default handler or configured per client |
| **java.net.http.HttpClient.Builder.cookieHandler(...)** | Attaches a CookieHandler to HttpClient for automatic HTTP cookie management |

**CookieManager is not a modern web browser engine.** The Java 17 API originates from Netscape/RFC 2109/RFC 2965 and does not promise to reproduce all modern browser RFC 6265 policies, SameSite, Partitioned, cookie prefixes, or the Public Suffix List. This is especially important when using a Java HTTP client to test web systems.

### 8.2. Creating a scoped CookieManager

~~~java
// Java 17 snippet: manager lives alongside an HttpClient.
CookieManager cookieManager =
        new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookieManager)
        .build();
~~~

Here **null CookieStore** instructs Java to use the default in-memory store; the ACCEPT_ORIGINAL_SERVER policy only accepts cookies matching the origin per the implementation's rules. This is a good approach for isolated clients, avoiding unintentional sharing of JVM-wide cookie state across tasks.

**Do not use ACCEPT_ALL for untrusted data just to make cookies "work".** ACCEPT_ALL relaxes the cookie acceptance policy. If stricter accuracy is needed, write a custom CookiePolicy/CookieStore and test against the threat model.

### 8.3. Avoid configuring a JVM-wide CookieHandler unnecessarily

**CookieHandler.setDefault(manager)** sets a shared default handler across the JVM. It can affect other code, creating risks of mixing sessions between components or parallel tests. When using **java.net.http.HttpClient**, configure **cookieHandler(manager)** on each client/appropriate lifetime object instead of setting it globally unless the architecture requires it.

### 8.4. A notable difference regarding Domain in Java

In RFC 6265 browsers, **Domain=example.test** and **Domain=.example.test** have the same scope. However, **HttpCookie.domainMatches(...)** and **CookieManager** in Java have legacy RFC 2965 logic; some implementations may not accept **Domain=example.test** the way browsers do for the source host **shop.example.test**. In the **tested Java example**, **Domain=.example.test** is used to demonstrate cookie sharing across subdomains under that implementation.

That is a **convention of the Java example**, not a recommendation for web servers to always prepend a dot to Domain. When building a backend serving browsers, issue Domain per browser standards and test on real browsers; when building a Java client, verify the CookieManager behavior of the JDK in use.

### 8.5. Do not use CookieStore.getCookies to assert actual headers

**CookieStore.getCookies()** returns the set of cookies in the store, which **does not mean** all of them will be sent to a specific request. To see the expected Cookie headers for a URI in Java, use **CookieManager.get(requestURI, requestHeaders)**. The manager performs additional filtering by host/path/secure.

Conversely, **CookieManager.put(responseURI, responseHeaders)** simulates/receives Set-Cookie responses and updates the store according to policy. These two methods can be used for offline testing without sending real requests.

## 9. Runnable Java 17 example: testing host, subdomain, path, Secure, and cookie age

The **CookieScopeAudit.java** example uses no network and requires no real server. It creates a **CookieManager + CookiePolicy.ACCEPT_ORIGINAL_SERVER**, simulates receiving four Set-Cookie headers from **https://shop.example.test/account/login**, and then queries CookieManager for which cookies are selected for different URIs.

The four cookies:

- **hostOnly=H; Path=/account; HttpOnly; Max-Age=120**: has no Domain, so it is scoped to the issuing host in the Java example; intentionally **omits Secure** so the difference when switching to HTTP can be observed.
- **shared=W; Domain=.example.test; Path=/; Max-Age=120**: uses a leading dot for Java CookieManager in this test; modern browsers do not require that dot.
- **secureOnly=S; Path=/account; Secure; HttpOnly; Max-Age=120**: same path, but only selected by the Java manager for HTTPS.
- **obsolete=x; Path=/account; Max-Age=0**: expires immediately and does not remain in the final cookie store.

**Security:** having a non-Secure hostOnly cookie is a **test configuration for demonstration**, not a production session cookie pattern. For real sessions/tokens, use **Secure, HttpOnly, appropriate SameSite, HTTPS**, and policy-driven TTLs. The .test URIs illustrate logic only, with **no network requests**.

### File CookieScopeAudit.java

~~~java
import java.io.IOException;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpCookie;
import java.net.URI;
import java.net.http.HttpClient;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class CookieScopeAudit {
    static void assertNames(
            CookieManager manager, String label,
            String url, String... expectedNames) throws IOException {
        Set<String> actual = new TreeSet<>();
        List<String> headers = manager.get(
                URI.create(url), Map.of())
                .getOrDefault("Cookie", List.of());

        for (String header : headers) {
            int equals = header.indexOf('=');
            if (equals > 0 && !header.startsWith("$")) {
                actual.add(header.substring(0, equals));
            }
        }

        Set<String> expected = new TreeSet<>(
                Arrays.asList(expectedNames));
        if (!actual.equals(expected)) {
            throw new AssertionError(
                    label + " expected=" + expected +
                    " actual=" + actual);
        }
        System.out.println(label + ": " +
                (actual.isEmpty() ? "(none)" :
                        String.join(",", actual)));
    }

    public static void main(String[] args) throws Exception {
        CookieManager manager = new CookieManager(
                null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
        URI origin = URI.create(
                "https://shop.example.test/account/login");

        manager.put(origin, Map.of("Set-Cookie", List.of(
                "hostOnly=H; Path=/account; HttpOnly; Max-Age=120",
                "shared=W; Domain=.example.test; Path=/; Max-Age=120",
                "secureOnly=S; Path=/account; Secure; HttpOnly; Max-Age=120",
                "obsolete=x; Path=/account; Max-Age=0"
        )));

        assertNames(manager, "HTTPS /account",
                "https://shop.example.test/account/orders",
                "hostOnly", "secureOnly", "shared");
        assertNames(manager, "HTTP /account",
                "http://shop.example.test/account/orders",
                "hostOnly", "shared");
        assertNames(manager, "HTTPS /public",
                "https://shop.example.test/public",
                "shared");
        assertNames(manager, "HTTPS sibling",
                "https://api.example.test/",
                "shared");
        assertNames(manager, "HTTPS unrelated",
                "https://unrelated.test/", new String[0]);

        boolean obsoleteInStore = manager.getCookieStore().getCookies()
                .stream().anyMatch(c -> "obsolete".equals(c.getName()));
        if (obsoleteInStore) {
            throw new AssertionError("Max-Age=0 cookie persisted");
        }
        System.out.println(
                "Max-Age=0 stored: " + obsoleteInStore);

        HttpCookie session = HttpCookie.parse(
                "session=transient; Path=/").get(0);
        HttpCookie deleted = HttpCookie.parse(
                "deleted=x; Max-Age=0").get(0);
        System.out.println("Session Max-Age: " +
                session.getMaxAge());
        System.out.println("Max-Age=0 expired: " +
                deleted.hasExpired());

        HttpClient client = HttpClient.newBuilder()
                .cookieHandler(manager)
                .build();
        System.out.println(
                "HttpClient CookieHandler configured: " +
                client.cookieHandler().isPresent());
        System.out.println("No network request performed");
    }
}
~~~

### Compile and run

Create the file with the exact name **CookieScopeAudit.java**, using **JDK 17 or newer**:

~~~bash
javac --release 17 -encoding UTF-8 CookieScopeAudit.java
java CookieScopeAudit
~~~

**Exact stdout from compiling with --release 17 and running successfully on OpenJDK 24.0.2:**

~~~text
HTTPS /account: hostOnly,secureOnly,shared
HTTP /account: hostOnly,shared
HTTPS /public: shared
HTTPS sibling: shared
HTTPS unrelated: (none)
Max-Age=0 stored: false
Session Max-Age: -1
Max-Age=0 expired: true
HttpClient CookieHandler configured: true
No network request performed
~~~

**Line-by-line explanation:**

1. **HTTPS /account:** path matches, Secure permits HTTPS, domain is valid, so hostOnly, secureOnly, and shared are all selected.
2. **HTTP /account:** secureOnly disappears because Secure cookies are not sent over HTTP; hostOnly and shared still appear **only because the example intentionally omitted Secure on them**.
3. **HTTPS /public:** hostOnly and secureOnly have Path=/account so they are not sent; shared has Path=/ and a matching domain.
4. **HTTPS sibling:** only the cookie with Domain=.example.test is selected for **api.example.test**; the others are host-only to shop.example.test.
5. **HTTPS unrelated:** no cookie matches the unrelated.test domain.
6. **Max-Age=0 stored: false:** the obsolete cookie is not in the final CookieStore; simulates immediate expiration/deletion.
7. **Session Max-Age: -1:** a new HttpCookie object without Max-Age is session-style per the Java API.
8. **Max-Age=0 expired: true:** HttpCookie treats a lifetime of 0 as expired.
9. **HttpClient CookieHandler configured: true:** the client has the manager attached, but **sends no real request**.
10. **No network request performed:** all URIs above are used solely to verify selection logic.

**Why doesn't assertNames compare the raw Cookie header?** Java CookieManager may include RFC 2965-style components such as **$Version, $Path, $Domain** and cookie ordering may not be fixed. The helper extracts cookie names from the header values list, sorts them with TreeSet, and compares against the expected name set; **do not turn a single implementation's ordering/format into a wrong learning criterion**.

**Do not replace the .test URLs with a real website and run this test with real credentials.** The program needs no Internet, exchanges no tokens, and only demonstrates Java CookieManager semantics in a test environment. It does not verify browser SameSite, prefix, partitioning, or public-suffix policies.

## 10. Proxies, redirects, and HTTP sessions: where cookies easily go wrong

### 10.1. Choosing a proxy does not mean cookies belong to the proxy

Suppose the application sends **https://shop.example.test/account** through an HTTP forward proxy. The cookie scope must still bind to the **origin of the request** made by the client, **not to the proxy's hostname**.

~~~text
Java HttpClient
  |
  | Request URI = https://shop.example.test/account
  | Cookie selection: shop.example.test + /account + HTTPS + TTL
  v
HTTP proxy or tunnel
  |
  v
Origin shop.example.test
~~~

CookieManager is given the corresponding **request URI/response URI** to evaluate cookies per policy. Do not create a Domain=proxy.corp.test cookie just because the TCP socket connects to that proxy.

### 10.2. TLS termination and Secure

A reverse proxy/ingress may accept **HTTPS** from the browser and forward the internal request to the backend over **HTTP**. If the backend infers incorrectly from the internal connection and issues a session cookie **without Secure**, the cookie could be sent over HTTP in other requests.

**Fix:** configure the application/server to issue security cookies based on the **external HTTPS origin** and trust the proper proxy. Forwarded headers such as **Forwarded** or **X-Forwarded-Proto** should only be accepted from **trusted proxies**, never trusting arbitrary values sent by Internet clients.

Do not omit Secure simply because the backend receives HTTP requests after TLS termination; session security is evaluated from the user agent's perspective.

### 10.3. Proxies may modify Set-Cookie or change host/path

A gateway may rewrite **Domain**, **Path**, or **Location** when routing multiple backends. If the proxy rewrites the public URL from **/app/** to backend **/**, a cookie with **Path=/** or **Path=/app** may result in different cookie-sending behavior than intended.

When encountering "login succeeds but the next request loses the session", record:

- The public URL before/after redirect.
- The actual Set-Cookie response received by the client (with tokens redacted).
- The cookie's Domain/Path/Secure/Max-Age/Expires.
- The host and scheme of the next request.
- Whether the Cookie request header was sent (with tokens redacted).
- Browser SameSite/third-party cookie policies or Java CookieManager behavior.

**Avoid logging raw session IDs.** Cookies are bearer credentials; logging them in full can create a session-leakage point.

### 10.4. Redirects and hostname changes

A login flow may transition from **login.example.test** to **shop.example.test**:

- A **host-only** cookie from login.example.test will **not** automatically carry over to shop.example.test.
- A cookie with Domain=example.test can be used on both hosts if valid, but increases sharing scope and session fixation risk.
- A **Secure** cookie requires a secure channel; redirecting to HTTP can prevent the cookie from being sent.
- If a redirect changes the path outside the configured Path, the cookie will not follow.
- **Max-Age** is still counted from when the cookie was set, not automatically reset after an HTTP redirect.

A sound solution may be an authentication flow that exchanges tokens/sessions server-side or via secure redirects, **not always broadening Domain to all subdomains**.

## 11. Common mistakes and fixes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| **Omitting Domain and assuming the cookie goes to all subdomains** | Sibling services do not receive the session | Design intentionally for host-only or shared Domain |
| **Setting Domain too broadly** | Increases cookie tossing/session fixation risk | Omit Domain when possible, use the narrowest scope |
| **Confusing Domain with a full URL containing port/path** | Cookie rejected or wrong scope | Domain is only a DNS domain, without scheme/port/path |
| **Treating Path=/account as matching /accounting** | Sends cookies more broadly than browser RFC permits | Test properly against RFC 6265 path segments |
| **Omitting Path while assuming it defaults to /** | Cookie does not go to URLs in other directories | Understand default-path or set Path explicitly |
| **Trusting Path as an authorization boundary** | Data exposure because the server skips permission checks | Always enforce authorization on the backend |
| **Missing Secure on session cookies** | Cookie can traverse plaintext HTTP | Issue Secure over HTTPS, configure TLS termination properly |
| **Confusing Secure with HttpOnly** | JS can still read non-HttpOnly cookies | Use both Secure and HttpOnly where appropriate |
| **Mistaking Max-Age for milliseconds** | Cookie lifetime off by 1,000x | Max-Age is in seconds |
| **Having both Max-Age and Expires and picking Expires** | Lifetime differs from expectations | RFC 6265 prioritizes Max-Age |
| **Deleting with the wrong Domain/Path** | Old cookie continues to be sent | Delete with the exact original name and scope |
| **Logout only clears the client cookie** | Copied tokens remain valid | Revoke/expire the session on the server |
| **Using CookieManager but forgetting to attach it to HttpClient** | HTTP client does not automatically store/send cookies | Builder.cookieHandler(manager) |
| **Using CookieStore.getCookies to conclude a cookie is sent** | Does not evaluate the specific request path | Use CookieManager.get(requestURI, headers) |
| **Using Java CookieManager as an oracle for browser SameSite** | Tests yield false conclusions about browsers | Test browsers separately with RFC6265/SameSite policies |
| **Enabling CookieHandler.setDefault for unisolated tests** | Mixes sessions across different clients | Separate manager per HttpClient/test scope |
| **Connecting via a proxy and setting Domain to the proxy name** | Wrong session scope | Always base on the origin URI |
| **HTTPS reverse proxy but backend forgets Secure** | Security cookies issued without Secure | Bind cookie policy to trusted external scheme |
| **Logging raw Cookie headers** | Leaks bearer session IDs | Redact, log only names/scope and investigation IDs |
| **Not setting server-side session TTL** | Cookie expires but leaked token remains usable | Enforce idle/absolute TTL and revocation on the server |

## 12. Recommended test suite for real systems

### Host scope tests

1. Issue a cookie without Domain from **shop.example.test**.
2. Requests to **shop.example.test** can receive the cookie.
3. Requests to **api.example.test** do not receive the host-only cookie.
4. If Domain=example.test is set, verify root and allowed subdomains; requests to independent hosts do **not** receive it.
5. Verify the user agent rejects unauthorized Domains and public suffixes.

### Path scope tests

1. Path=/account must match **/account**.
2. Must match **/account/orders**.
3. Must **not** match **/accounting** per RFC6265 browsers.
4. Omitting Path from URL **/docs/page.html** must yield default-path **/docs/**.
5. Test same-named cookies with different Paths, without relying on wire ordering.

### Secure and other flag tests

1. A Secure cookie from HTTPS must be sent to valid HTTPS URIs.
2. The same host/path URI over plaintext HTTP must not receive the Secure cookie.
3. An HttpOnly session cookie is unreadable via browser document.cookie, but is sent by the browser in matching HTTP requests.
4. SameSite/CSRF tests include cross-site request cases and OAuth/redirect flows if used by the app.
5. If using the __Host- prefix, verify the cookie always has Secure, Path=/, and no Domain.
6. Reverse proxy/TLS termination must not strip the Secure flag.

### Lifetime tests

1. Max-Age=2 expires after a few seconds in a controlled test environment; avoid overly short sleeps that cause flakiness.
2. Max-Age=0 deletes immediately.
3. Both a distant Expires and a near Max-Age: browsers prioritize Max-Age.
4. Deleting a cookie with the wrong Path does not delete the one with the right Path.
5. Logout must revoke the backend session.
6. Closing/reopening a browser may trigger session restore; do not treat closing the browser as a reliable revocation mechanism.

### Java-specific tests

1. Use **CookieManager.get(uri, headers)** to verify selection instead of only inspecting getCookieStore().getCookies().
2. Test **Domain=.example.test** on the running JDK implementation and compare differences with browser Domain=example.test.
3. Test **Path=/account** versus **/accounting** separately in Java and browsers; do not assume identical results.
4. Test **CookiePolicy.ACCEPT_ORIGINAL_SERVER** versus a custom policy if needed.
5. Test **HttpClient** with its attached cookieHandler, ensuring cookie managers are not mixed across tenants/users.
6. Test expiration/replacement across multiple Set-Cookie responses and redirect behavior across different hosts.

## 13. Self-check questions

**Question 1.** Does a cookie without Domain issued from shop.example.test go to api.example.test?  
**Answer:** No in RFC 6265 browsers: it is a host-only cookie, requiring an exact host match.

**Question 2.** Do Domain=example.test and Domain=.example.test differ in modern browsers?  
**Answer:** Not in scope: the leading dot is ignored under RFC 6265. However, Java CookieManager may handle it differently due to its RFC 2965 foundation.

**Question 3.** Does Domain=example.test allow the cookie to be sent to fakeexample.test?  
**Answer:** No. A valid domain-match is required, not merely containing the substring.

**Question 4.** Is Path=/account sent to /accounting in browsers under RFC6265?  
**Answer:** No, because the path segment does not match; after /account is not a / character.

**Question 5.** Does a cookie without Path from /docs/page.html default to Path=/?  
**Answer:** No. The default-path is typically /docs/.

**Question 6.** Can a Secure cookie be sent over plaintext HTTP to the right host/path?  
**Answer:** Not under normal conditions; Secure restricts sending over insecure channels. Browsers have a localhost exception for testing.

**Question 7.** Does Secure prevent JavaScript from reading the cookie?  
**Answer:** No. HttpOnly is what blocks normal document.cookie access, and it does not replace other XSS defenses.

**Question 8.** What kind of cookie is one without Max-Age and Expires?  
**Answer:** A session cookie under the browser model; however, session restore may keep it longer than expected, so a server-side TTL is needed.

**Question 9.** What unit is Max-Age=1800 measured in?  
**Answer:** 1,800 seconds = 30 minutes, not milliseconds.

**Question 10.** When both Max-Age and Expires are present, which one do browsers prioritize?  
**Answer:** Max-Age.

**Question 11.** Is setting Max-Age=0 on the client at logout enough to invalidate a compromised token?  
**Answer:** No. The server must revoke/expire the corresponding session/token.

**Question 12.** Does Java's default CookieManager persist cookies across JVM restarts?  
**Answer:** No. The default store is in-memory; if persistence is needed, select/implement an appropriate CookieStore.

**Question 13.** Does CookieStore.getCookies() tell you which cookies will accompany a specific URL?  
**Answer:** Not completely. Use CookieManager.get(requestURI, headers) to apply the selection policy for that URI.

**Question 14.** Why must a request through a proxy still use the origin's Domain rather than the proxy's?  
**Answer:** Cookies belong to the HTTP origin being accessed, not the host providing proxy transport.

**Question 15.** Does issuing a cookie with Path=/admin replace authorization checks for /admin?  
**Answer:** No. Path is not a security barrier; the backend must verify the session and permissions on every request.

## Conclusion

The four attributes **Domain, Path, Secure, Max-Age/Expires** determine **whether a cookie is stored and sent on an HTTP request**. Domain controls host/subdomain, Path controls URL path, Secure restricts the transport channel, and Max-Age/Expires defines client-side lifetime. They do not replace **authentication/authorization, CSRF protection, and server-side session revocation**.

In Java 17, **CookieManager, CookieStore, HttpCookie, and HttpClient.cookieHandler(...)** help manage cookies in HTTP clients. However, Java CookieManager is rooted in RFC 2965 and **is not a complete reference for modern RFC 6265/SameSite browsers**. When debugging, know whether you are testing a **Java user agent** or a **web browser**, and inspect the expected Cookie header for the **exact origin URI**, even when routing through a proxy or reverse proxy.

### References

- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): Domain, Path, host-only, Secure, Expires, and Max-Age.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): syntax, Domain/Path/Secure, HttpOnly, SameSite, and cookie prefixes.
- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies): cookie lifecycle, security, browser policy.
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies): security defaults for session cookies.
- [Java SE 17 — CookieManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html): cookie handling, policies, and RFC 2965.
- [Java SE 17 — HttpCookie](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpCookie.html): Domain, Path, Secure, HttpOnly, and Max-Age API.
- [Java SE 17 — CookiePolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookiePolicy.html): ACCEPT_ORIGINAL_SERVER, ACCEPT_ALL, ACCEPT_NONE.
- [Java SE 17 — CookieStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieStore.html): storing and retrieving cookies.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): cookieHandler(CookieHandler).
- [Oracle Java Tutorials — Default CookieManager](https://docs.oracle.com/javase/tutorial/networking/cookies/cookiemanager.html): in-memory store and policy scope.

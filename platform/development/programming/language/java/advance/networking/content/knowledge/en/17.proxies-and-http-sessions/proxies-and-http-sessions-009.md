# Intentionally Maintaining Session State Between HTTP Requests and Isolating Users

At the protocol level, HTTP **does not require each request to carry the application state of the previous request**. However, real-world products often need to maintain a **session** so the server knows that consecutive operations belong to the same logged-in user, the same shopping cart, or the same transaction. In Java, `HttpClient` can send multiple `HttpRequest`s over reused connections; if configured with a `CookieManager`, the client can also store cookies from responses and send back valid cookies on subsequent requests.

The key point is to **maintain state only intentionally and isolate it by identity/tenant**. Two users A and B may call the same API hostname, but **they must never accidentally share session cookies, bearer tokens, proxy credentials, or each other's authentication information**. Separating `HttpClient` instances while still sharing the same `CookieManager` also **does not isolate sessions**.

This Knowledge article belongs to **Java Advance - networking → Proxies and HTTP Sessions**. It focuses on Java 17+, explaining HTTP session/cookie boundaries, state and connection caching, several per-user management approaches, the risks of sharing configuration across proxies/redirects/authenticators, the login–logout lifecycle, isolation tests, and two standalone Java programs running on localhost.

**After this lesson, you will be able to:**
- Distinguish between server-side state and client-side state.
- Know when to use a **separate cookie store per session/user** and when to use **a shared stateless HttpClient with tokens placed separately on each HttpRequest**.
- Understand why `CookieManager` partitions by **URI/domain/path**, not by user ID.
- Avoid mixing authentication/sessions of multiple tenants when handling concurrent requests.
- Design logout, token rotation, session expiry, redirect/proxy isolation, and cleanup.
- Run two Java 17+ examples to observe **proper isolation** and **cookie leakage caused by a shared store**.

## 1. HTTP Is Stateless, Yet Applications Can Maintain Sessions

Consider three consecutive requests:

~~~http
GET /cart HTTP/1.1
Host: shop.example

GET /cart HTTP/1.1
Host: shop.example

POST /checkout HTTP/1.1
Host: shop.example
Content-Type: application/json

{"confirm":true}
~~~

Looking at these HTTP messages, **nothing automatically indicates that they belong to the same user**. If the server wants to store a shopping cart per user, it needs to recognize the identity/session on each request: a session cookie, a bearer token, or another authentication mechanism.

A typical cookie-backed session flow looks like this:

~~~text
                    LOGIN
Client A                         Server
  | POST /login (credentials)      |
  |------------------------------->|
  |                     validate credentials
  |                     create random session ID
  |                     store session ID -> user A
  |<-------------------------------|
  | 200 OK                         |
  | Set-Cookie: sid=...; Path=/; HttpOnly; Secure; SameSite=Lax
  |                                |
                    NEXT REQUEST
  | GET /me                        |
  | Cookie: sid=...                |
  |------------------------------->|
  |                     lookup sid -> user A
  |<-------------------------------|
  | 200 OK, user=A                 |
  |                                |
                     LOGOUT
  | POST /logout                   |
  | Cookie: sid=...                |
  |------------------------------->|
  |                      invalidate server session
  |<-------------------------------|
  | Set-Cookie: sid=; Max-Age=0; ... 
~~~

In the diagram, the cookie ID is only a **pointer** used to look up the session. All security decisions must still be checked **on the server side**; a cookie sent by the client does not by itself prove the user is authorized to access a resource.

**Important:** HTTP statelessness is **different** from TCP connection statelessness. Java's `HttpClient` can keep TCP connections, TLS sessions, or HTTP/2 streams open to optimize performance. That is **not** evidence that two HTTP requests share the same user identity. Conversely, two requests sent over two different connections **can still** belong to the same session when they carry the appropriate cookie/token.

## 2. Three Layers of State That Are Easily Confused

| Layer | Examples | Who manages it? | Is it a user identity boundary? |
| --- | --- | --- | --- |
| **Application session** | Server map `sessionId → userId`, permissions, expiry | Server / session store | Yes, provided authentication and authorization are done properly |
| **Client credential state** | Cookie store, access token, Authenticator, proxy credentials | Java application / HttpClient | Can carry identity; must be intentionally isolated |
| **Network connection state** | Keep-alive TCP, TLS session, HTTP/2 streams, connection pool | HttpClient / provider / OS | **No**, by itself it does not distinguish users |

Do not write logic like “this request reuses the old connection, so it must still be Alice.” Authentication belongs to request credentials and verified sessions, **not reused sockets**. Over HTTP/2, multiple logical streams can share a single connection; sharing a connection even less implies sharing permissions.

Similarly, “a built Java HTTP client is immutable” only means that **the client object's configuration cannot be changed via the builder after building**. It does not mean referenced components such as `CookieManager` or a custom `Authenticator` are immutable, or that they cannot store new state during subsequent HTTP exchanges.

## 3. What Is a Cookie and How Are Session Cookies Sent Back?

A server may send the header:

~~~http
HTTP/1.1 200 OK
Set-Cookie: sid=SESSION_TOKEN; Path=/; HttpOnly; Secure; SameSite=Lax
Cache-Control: no-store
~~~

Here, `sid` is an **example cookie name**, not a JDK standard name. Servlet frameworks often use `JSESSIONID`; other frameworks use their own names. The actual value must be sufficiently random, unpredictable, time-bounded, and bound by the server to a session/auth policy.

Common attributes:

| Attribute | Purpose | Notes |
| --- | --- | --- |
| `Path=/` | Restricts the path to which the cookie is sent | Path does not replace authorization; multiple apps sharing a host/path can collide on scope |
| `Domain=...` | Allows the cookie within a valid domain scope | A broad domain can unintentionally share cookies across subdomains |
| `Secure` | Sends the cookie only over a secure channel per client policy | Required for session cookies over HTTPS; localhost HTTP demos omit Secure |
| `HttpOnly` | Instructs browsers not to expose the cookie to page-side JavaScript | Does not make the cookie secret from the Java application itself that owns the CookieStore |
| `SameSite=Lax/Strict/None` | Hints at binding cookies to cross-site browser contexts | **Do not assume** Java CookieManager enforces full browser SameSite policies |
| `Max-Age` or `Expires` | Cookie lifetime | Does not replace server-side idle/absolute session expiration |
| `sid=; Max-Age=0` | Instructs the user agent to delete the corresponding cookie | Must match scope/path/domain and **still must** invalidate the session on the server |

**Cookie scope is not user scope.** Standard cookie policies care about scheme, domain/host, path, Secure, and expiry; **they do not automatically bind cookies to Alice or Bob**. Cookies with the same name/domain/path are normally updated/replaced, even if the application thinks two HTTP sessions belong to two different Java objects. HTTP cookies also do not provide an identity-isolation mechanism by TCP port as a security boundary.

In the Java JDK, `CookieManager` and `CookieStore` are where client-side cookie policy is stored and applied; a server-side session store is something completely different. You should not store user-specific permissions solely in a client-modifiable cookie; if claims must be stored on the client (for example, a signed token), the server must verify the signature, expiry, audience, scope, and revocation policy.

## 4. java.net.CookieManager, CookieStore, and HttpClient.cookieHandler

Java 17 provides `java.net.CookieManager` to connect a cookie acceptance policy with a `CookieStore`. A separate manager per session:

~~~java
CookieManager cookies = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookies)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
~~~

This is a **snippet** requiring imports `java.net.CookieManager`, `java.net.CookiePolicy`, and `java.net.http.HttpClient`. When the constructor receives `null` for the store, it uses the default in-memory store; the `ACCEPT_ORIGINAL_SERVER` policy only accepts cookies according to the origin rules supported by the JDK. That policy **does not** distinguish two users on the same hostname.

Expected behavior:

~~~text
Server response: Set-Cookie: sid=token-A; Path=/
       |
       v
CookieManager.put(responseUri, headers)
       |
       v
CookieStore holds cookie matching URI/scope
       |
     Next request to matching URI
       |
       v
CookieManager.get(requestUri, headers)
       |
       v
Header Cookie: sid=token-A
~~~

The application **does not** have to call `put/get` manually for normal HTTP client flows if a manager has been attached via `HttpClient.Builder.cookieHandler(...)`. The CookieHandler is used by the client during send/receive.

### Does HttpClient Retain Cookies by Default?

According to Java 17's `HttpClient.cookieHandler()`, if the builder does **not** set `cookieHandler(...)`, the method returns `Optional.empty()`. Do not assume a new client will store every `Set-Cookie` like a browser. If you want to maintain a session via cookies intentionally, **explicitly configure a manager**; if you want stateless behavior, **do not attach a stateful cookie handler**.

The JDK also has `CookieHandler.setDefault(...)`, which is a **process-wide** configuration API for consumers using the default handler. Do not use a global manager as a “shared session” in a multi-user backend. With `HttpClient`, configuring `cookieHandler(...)` on the builder provides a clearer boundary.

### How Can a CookieStore Be Implicitly Shared?

~~~java
CookieManager sharedCookies = new CookieManager();

HttpClient userA = HttpClient.newBuilder()
        .cookieHandler(sharedCookies).build();

HttpClient userB = HttpClient.newBuilder()
        .cookieHandler(sharedCookies).build();
~~~

**This is a counterexample when two clients represent two different users.** Even though `userA != userB`, both use **the same CookieManager and CookieStore objects**. If they call the same hostname, cookies with the same name/path can overwrite each other's state. Two client instances **do not** automatically separate cookie state when passed the same store.

**Safer invariant:** For cookie-backed identity, one logical session/tenant isolation boundary must own a **dedicated CookieManager/CookieStore**, and must not leak its reference to another user's session.

## 5. Two Primary Models: Cookie-Backed Sessions vs. Stateless Per-Request Credentials

| Design Question | Cookie-backed user session | Stateless/per-request token |
| --- | --- | --- |
| How is identity carried? | `Cookie: sid=...` sent by CookieManager | `Authorization: Bearer ...` or per-request auth header |
| Client state to maintain | Dedicated CookieStore per session | Token supplied from request context / credential provider |
| Should one HttpClient be used for all users? | **No** if sharing cookie/auth state; typically create a separate client+manager per user | **Possible**, if the client has no per-user cookie/auth/proxy state and headers are isolated per request |
| Logout mechanism | Invalidate server session and expire cookie | Revoke/expire token per policy; stop using token on client |
| Cross-user risk | Sharing CookieManager/Authenticator or cookie scope | Using mutable global `currentToken` or attaching previous user's header to next request |
| Security requirements | HTTPS, cookie flags, CSRF policy, session rotation | HTTPS, token validation/expiry/rotation, no secret logging |
| Suitable use cases | Web-like sessions, APIs requiring cookies, legacy apps | Backend fan-out, service-to-service APIs, each call carries explicit credentials |

**There is no single rule saying “create a new HttpClient on every request.”** The goal is to **isolate identity-bearing state**, not necessarily to separate physical TCP connections for every request. Creating too many clients can waste resources and reduce connection reuse; sharing a client improperly leaks sessions. Choose the model based on whether the client holds personal state.

## 6. Designing Per-User Cookie Sessions

An easily auditable pattern:

~~~text
User A session context:
  CookieManager A -> CookieStore A
  HttpClient A    -> cookieHandler(A)
  A auth/session lifecycle
  A request/response metadata

User B session context:
  CookieManager B -> CookieStore B
  HttpClient B    -> cookieHandler(B)
  B auth/session lifecycle
  B request/response metadata

A and B can call the same https://api.example.com/
but cookies are not in the same store.
~~~

Factory example (syntactically standalone snippet, without `main`):

~~~java
static HttpClient newSessionClient() {
    CookieManager cookies = new CookieManager(
            null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
    return HttpClient.newBuilder()
            .cookieHandler(cookies)
            .followRedirects(HttpClient.Redirect.NEVER)
            .connectTimeout(Duration.ofSeconds(3))
            .build();
}
~~~

Each factory call creates a **new manager** and a **new client**. Advantage: eliminates accidental CookieStore sharing. However, server-side authorization is still required; a separate client will not save you if a developer accidentally copies Alice's `Authorization` header onto Bob's request.

**Specifically for multi-tenant backends:**
- Obtain the Tenant ID from the authenticated request context; **do not** blindly trust a caller-supplied `tenantId` parameter.
- Explicitly map `tenant/user session key → session context`; do not use a single static variable holding the most recently logged-in client.
- Prevent one user from looking up/accessing another user's session context (application-level authorization).
- If caching contexts, use expiry, cap the total number of sessions/clients, and clean up references/credentials upon expiration.
- Never store plain-text tokens or cookies in logs, metrics labels, or exception messages.
- Partition application result caches containing personal data by user/tenant; separating cookies alone is not enough.

## 7. Complete Java 17+ Example: Two Users, Two CookieManagers, Login and Logout

The program **`SessionIsolationDemo.java`** consists of a test HTTP server running on `127.0.0.1`, an OS-chosen port, and three separate `HttpClient`s. The server:
- Accepts `POST /login` with body `"alice"` or `"bob"`.
- Generates a random 256-bit session token using `SecureRandom` and `Base64 URL-safe`; stores `sessionToken → username` in a `ConcurrentHashMap`.
- Sends `Set-Cookie: sid=...; Path=/; HttpOnly; SameSite=Lax` to the client. Because the demo uses **HTTP localhost**, it intentionally **omits** `Secure`; production session cookies over HTTPS **must** use `Secure` appropriately.
- `GET /whoami` reads the cookie and looks up the server-side map to identify the user.
- `POST /logout` removes the session from the map and sends a cookie with `Max-Age=0`.

This is a **session management simulation**, not a real login system: the server only accepts a username in the body to easily demonstrate state, **with no password/OAuth verification and no CSRF middleware**. In production, never allow anyone to claim “alice” and create an Alice session like this fixture.

After running the **safe** flow, the program intentionally creates **two different HttpClients attached to a shared CookieManager** to observe the bug: the second user logs in as Bob and the `sid` cookie in the shared store replaces Alice's cookie; a subsequent call from `unsafeOne` sees Bob's identity.

Create the file **`SessionIsolationDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class SessionIsolationDemo {
    static final Map<String, String> sessions =
            new ConcurrentHashMap<>();
    static final SecureRandom random = new SecureRandom();

    static String randomToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding().encodeToString(bytes);
    }

    static String sessionCookie(HttpExchange ex) {
        String header = ex.getRequestHeaders().getFirst("Cookie");
        if (header == null) return null;

        for (String entry : header.split(";")) {
            String part = entry.trim();
            if (part.startsWith("sid=")) {
                return part.substring(4);
            }
        }
        return null;
    }

    static void reply(
            HttpExchange ex, int status, String body, String cookie)
            throws IOException {

        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        ex.getResponseHeaders().set("Cache-Control", "no-store");

        if (cookie != null) {
            ex.getResponseHeaders().set("Set-Cookie", cookie);
        }

        ex.sendResponseHeaders(status, data.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(data);
        }
    }

    static void handle(HttpExchange ex) throws IOException {
        String path = ex.getRequestURI().getPath();
        String method = ex.getRequestMethod();

        if (path.equals("/login") && method.equals("POST")) {
            String name = new String(
                    ex.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8);

            if (!name.equals("alice") && !name.equals("bob")) {
                reply(ex, 400, "unknown-user", null);
                return;
            }

            String sid = randomToken();
            sessions.put(sid, name);
            reply(ex, 200, "logged-in",
                    "sid=" + sid + "; Path=/; HttpOnly; SameSite=Lax");

        } else if (path.equals("/whoami") && method.equals("GET")) {
            String sid = sessionCookie(ex);
            String name = sid == null ? null : sessions.get(sid);
            reply(ex, 200, name == null ? "anonymous" : name, null);

        } else if (path.equals("/logout") && method.equals("POST")) {
            String sid = sessionCookie(ex);
            if (sid != null) sessions.remove(sid);

            reply(ex, 200, "logged-out",
                    "sid=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax");

        } else {
            reply(ex, 404, "not-found", null);
        }
    }

    static HttpClient isolatedClient() {
        CookieManager cookies = new CookieManager(
                null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

        return HttpClient.newBuilder()
                .cookieHandler(cookies)
                .followRedirects(HttpClient.Redirect.NEVER)
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    static String get(HttpClient client, URI root, String path)
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                        root.resolve(path))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        if (response.statusCode() != 200) {
            throw new IOException("GET status: " + response.statusCode());
        }
        return response.body();
    }

    static void post(
            HttpClient client, URI root, String path, String body)
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                        root.resolve(path))
                .timeout(Duration.ofSeconds(3))
                .POST(HttpRequest.BodyPublishers.ofString(
                        body, StandardCharsets.UTF_8))
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        if (response.statusCode() != 200) {
            throw new IOException("POST status: "
                    + response.statusCode());
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/", ex -> {
            try {
                handle(ex);
            } catch (IOException error) {
                ex.close();
            }
        });
        server.start();

        try {
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());

            HttpClient alice = isolatedClient();
            HttpClient bob = isolatedClient();
            HttpClient fresh = isolatedClient();

            System.out.println("Alice before login: "
                    + get(alice, root, "/whoami"));

            post(alice, root, "/login", "alice");
            System.out.println("Alice after login: "
                    + get(alice, root, "/whoami"));

            System.out.println("Bob before login: "
                    + get(bob, root, "/whoami"));

            post(bob, root, "/login", "bob");
            System.out.println("Bob after login: "
                    + get(bob, root, "/whoami"));

            System.out.println("Alice after Bob login: "
                    + get(alice, root, "/whoami"));

            System.out.println("Fresh client: "
                    + get(fresh, root, "/whoami"));

            post(alice, root, "/logout", "");
            System.out.println("Alice after logout: "
                    + get(alice, root, "/whoami"));

            System.out.println("Bob after Alice logout: "
                    + get(bob, root, "/whoami"));

            // COUNTEREXAMPLE: Two different clients sharing the SAME CookieManager.
            CookieManager sharedCookies = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

            HttpClient unsafeOne = HttpClient.newBuilder()
                    .cookieHandler(sharedCookies).build();
            HttpClient unsafeTwo = HttpClient.newBuilder()
                    .cookieHandler(sharedCookies).build();

            post(unsafeOne, root, "/login", "alice");
            post(unsafeTwo, root, "/login", "bob");

            System.out.println("Shared CookieManager leak: "
                    + get(unsafeOne, root, "/whoami"));
        } finally {
            server.stop(0);
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SessionIsolationDemo.java
java SessionIsolationDemo
~~~

**Execution output verified with Java 17-compatible APIs on loopback:**

~~~text
Alice before login: anonymous
Alice after login: alice
Bob before login: anonymous
Bob after login: bob
Alice after Bob login: alice
Fresh client: anonymous
Alice after logout: anonymous
Bob after Alice logout: bob
Shared CookieManager leak: bob
~~~

### Analysis: Why Is Alice Unaffected in the Correct Flow?

- `alice = isolatedClient()` creates `CookieManager A`, `bob = isolatedClient()` creates `CookieManager B`, and `fresh` creates an empty store C.
- When Alice logs in, the cookie with `sid=tokenAlice` goes only into **store A**; Bob logging in gets `tokenBob` only into **store B**.
- The subsequent `get(alice, "/whoami")` request sends `tokenAlice`, while `bob` sends `tokenBob`. Same server, URI, and path, but different user identities.
- The fresh client has no cookies and the server returns `anonymous`. That proves **no implicit session is inherited just because of the same JVM or host**.
- Alice's logout invalidates the session token on the server and sends an expired cookie; Alice's client returns to anonymous, while Bob remains logged in.
- In the **incorrect part**, `unsafeOne` and `unsafeTwo` both hold `sharedCookies`. After Bob logs in, the cookie in the shared store for the same hostname/path belongs to Bob; therefore `unsafeOne` observes Bob. This is a cross-user state leakage bug, **not** a TLS or HTTP connection pool bug.

This code **does not print session tokens to stdout**: it only prints the identity returned by the server. In real production systems, also avoid logging raw cookies, Authorization headers, session IDs, and sensitive information.

### What the Fixture Simplified

- Login here only reads the username, **without verifying passwords/accounts**. Production must verify real credentials.
- The server stores the session map in RAM, **without expiration, replication, idle timeout, session rotation after privilege changes**, replay protection, or CSRF middleware; production must add these.
- The server parses `Cookie` by splitting on `;` only because the fixture uses a simple cookie name, not a full standard cookie parser.
- The cookie lacks `Secure` because requests are over `http://127.0.0.1`; do not do that for session cookies over the Internet.
- The demo only has two names `alice/bob` and no real user data.
- Java 17 has no `HttpClient.close()` API; the example stops the server with `server.stop(0)`. For long-running applications, manage client/session context lifecycles according to your runtime/framework.

## 8. Session Lifecycle: Login, Refresh, Logout, and Expiration

Keeping a session does not mean keeping a cookie token forever. The design should describe the **lifecycle**:

~~~text
[anonymous]
     |
     | successful authentication
     v
[active session] -- reissue/rotate --> [active new session]
     |                                    |
     | logout / revocation / expiry       | timeout
     v                                    v
[revoked / expired]                 [expired]
     |
     +--> request with old token = unauthorized
~~~

**On login:**
- Server verifies valid credentials.
- Generate a random session ID with sufficient entropy; never trust a caller-chosen session ID.
- **Rotate** the session token when transitioning from anonymous → authenticated to reduce session fixation risk.
- Set server-side idle timeout and absolute timeout.
- Store only minimal information; the session store should manage TTL, auditing, and revocation.

**While the session is active:**
- Each request is re-identified by the server using the cookie/token.
- Only allow resources according to the **authenticated principal** and verified permissions/tenant.
- If permissions/account status change, update/revoke the session per policy; do not merely change display text on the client.
- If a CSRF threat model applies, protect state-changing operations with CSRF tokens, Origin checks, and/or an appropriate SameSite policy; do not rely on a single attribute.

**On logout:**
- Server invalidates the session token **even if the browser/Java client still holds the old cookie**.
- Send `Set-Cookie` with `Max-Age=0` and matching scope/domain/path to request cookie deletion.
- Remove the token from the user credential store, clear the session, and disable further session activity where possible.
- If the app supports multiple sessions across multiple devices, distinguish between “logout current session” and “logout all sessions.”

**Do not use `CookieStore.removeAll()` as a substitute for server-side revocation.** Deleting cookies on the client only stops that client from sending the token itself; someone else who copied the token can still use it if the server has not expired/revoked it.

## 9. When Should You Separate One HttpClient per Session?

**Separating HttpClient + CookieManager** is usually appropriate when:
- The application acts on behalf of a single user throughout a session.
- A legacy server uses session cookies automatically, and multiple requests must continuously send the right cookie.
- Users/tenants have distinct `Authenticator` configurations, proxy credentials, or client TLS identities.
- You want a simple, easily testable implementation boundary with low chance of accidentally sharing state.

Conceptual pattern:

~~~text
Map<AuthenticatedSessionKey, SessionClientContext>

SessionClientContext {
    HttpClient client;
    CookieManager cookieManager;
    auth/proxy configuration;
    session expiry + lifecycle policy;
}
~~~

This is a **structural diagram**, not a complete Java class. In production, ensure the context map has bounded capacity, TTL/eviction, and that session keys do not contain raw bearer tokens. Context data must never be returned directly to another tenant.

However, creating a separate client **for every incoming HTTP request** is an unnecessary extreme that can hurt connection reuse. One context per user-session can serve **many requests** while the session remains valid.

**Separating the CookieManager matters more than the client's name.** Using two different clients with the same `CookieStore` is a bug; using one client that holds no user state and explicitly adding per-request tokens is sometimes safer and more economical.

## 10. Stateless Model: One Shared HttpClient, Authorization on Each Request

For APIs authenticated via bearer tokens or another authentication mechanism attached **per request**, you can create one `HttpClient` without configuring a cookie handler or user-specific authenticator:

~~~java
HttpClient shared = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest aliceRequest = HttpRequest.newBuilder(uri)
        .header("Authorization", "Bearer " + aliceToken)
        .GET()
        .build();

HttpRequest bobRequest = HttpRequest.newBuilder(uri)
        .header("Authorization", "Bearer " + bobToken)
        .GET()
        .build();
~~~

This is a **snippet** with hypothetical tokens retrieved from a secure credential provider, not hard-coded into source. Built `HttpRequest`s are immutable, so when sent concurrently, authentication credentials reside on **their respective requests**, not in a continuously mutated `currentToken` variable.

**Common anti-pattern:**

~~~java
// COUNTEREXAMPLE: Do not use a mutable global variable for identity.
static String currentToken;

// Thread A sets Alice's token; thread B changes it to Bob's token;
// thread A building a request afterward may accidentally pick up Bob's token.
~~~

**Do not rely solely on `ThreadLocal`** to carry identity across `CompletableFuture` callbacks or executors: completion callbacks may run on a different thread than the one that received the request. Pass the authenticated principal/credential reference explicitly in an immutable per-request context and avoid capturing references to mutable global state.

**Do not share an `Authenticator` that stores dynamic user/password state** across tenants on the same client. If HTTP authentication challenges or proxy authentication use per-user credentials, design an audited tenant-aware implementation or use separate clients/contexts.

## 11. Complete Java 17+ Example: Same HttpClient, Separate Token per HttpRequest

The example **`RequestIdentityIsolationDemo.java`** uses a mock HTTP server:
- The header `Authorization: Bearer demo-key-a` is mapped by the fixture to `alice`.
- The header `Authorization: Bearer demo-key-b` is mapped by the fixture to `bob`.
- Missing or invalid header → `anonymous`.
- Alice, Bob, and the anonymous request are sent **nearly concurrently** using a single shared `HttpClient.sendAsync`.
- Each call creates a new `HttpRequest`; **there is no CookieManager** or mutable current user token.
- Output is printed in the order `Future.get` is called, **not** proving response completion order.

**The strings demo-key-a/demo-key-b are dummy keys for testing routing**, not secure access tokens. Production servers must verify signatures/expiry/audience or introspect real tokens and run only over HTTPS.

Create the file **`RequestIdentityIsolationDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class RequestIdentityIsolationDemo {
    static void handle(HttpExchange ex) throws IOException {
        String auth = ex.getRequestHeaders().getFirst("Authorization");

        String body =
                "Bearer demo-key-a".equals(auth) ? "alice" :
                "Bearer demo-key-b".equals(auth) ? "bob" : "anonymous";

        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Cache-Control", "no-store");
        ex.sendResponseHeaders(200, data.length);

        try (OutputStream out = ex.getResponseBody()) {
            out.write(data);
        }
    }

    static HttpRequest request(URI uri, String demoToken) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .GET();

        if (demoToken != null) {
            builder.header("Authorization", "Bearer " + demoToken);
        }
        return builder.build();
    }

    static String body(
            CompletableFuture<HttpResponse<String>> future)
            throws Exception {

        HttpResponse<String> response =
                future.get(3, TimeUnit.SECONDS);

        if (response.statusCode() != 200) {
            throw new IOException("HTTP " + response.statusCode());
        }
        return response.body();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/me", ex -> {
            try {
                handle(ex);
            } catch (IOException error) {
                ex.close();
            }
        });
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/me");

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            var handler = HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8);

            CompletableFuture<HttpResponse<String>> a =
                    client.sendAsync(request(uri, "demo-key-a"), handler);
            CompletableFuture<HttpResponse<String>> b =
                    client.sendAsync(request(uri, "demo-key-b"), handler);
            CompletableFuture<HttpResponse<String>> none =
                    client.sendAsync(request(uri, null), handler);

            System.out.println("Alice: " + body(a));
            System.out.println("Bob: " + body(b));
            System.out.println("Anonymous: " + body(none));

            System.out.println("Alice again: " + body(
                    client.sendAsync(
                            request(uri, "demo-key-a"), handler)));

            System.out.println("Client cookie handler absent: "
                    + client.cookieHandler().isEmpty());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 RequestIdentityIsolationDemo.java
java RequestIdentityIsolationDemo
~~~

**Output observed on loopback:**

~~~text
Alice: alice
Bob: bob
Anonymous: anonymous
Alice again: alice
Client cookie handler absent: true
~~~

### Why Can One HttpClient Be Safe Here?

- `HttpClient` has no cookie handler, so it does not retain Alice's or Bob's session cookies.
- Each `HttpRequest` carries its **own mock token**, and built request objects are immutable.
- The sender does not use a mutable global credential that changes between concurrent calls.
- The server fixture determines identity **from each request's header**, not from an old socket.
- The second call for A is still Alice because the new request also carries only Alice's token, without inheriting Bob's token.
- `client.cookieHandler().isEmpty() == true` confirms no CookieHandler is configured on the client.

This does **not** mean sharing a client is safe regardless of configuration: if you add a shared cookie handler, user-dependent authenticator, proxy credentials, or incorrect header injection, the boundary changes. The decision must be based on **the state actually attached to the client** and the downstream authentication contract.

## 12. Authorization, Cookie, and Authenticator Are Not the Same

Identity-carrying mechanisms:

| Mechanism | Typical Level | Sharing Risk |
| --- | --- | --- |
| `Cookie` header containing session ID | Per HTTP request, attached automatically by client cookie manager | Shared CookieStore causes later user to overwrite previous session |
| `Authorization: Bearer ...` header | Per HTTP request | Global mutable token / request-builder reuse or retrying to wrong URL |
| `HttpClient.Builder.authenticator(...)` | HttpClient configuration for HTTP auth challenges | Authenticator may hold credentials/cache; must not share user context arbitrarily |
| Proxy credentials (e.g., 407 challenge) | Proxy / network access layer | Single proxy account or credential cache mixed across tenants |
| mTLS client certificate/private key | TLS connection / client SSLContext | Client certificate represents a different identity; must separate TLS security contexts when needed |
| Server session cache / app result cache | Server / business layer | Key missing tenant/user ID leads to data leakage even if cookies are properly separated |

**Cookie** and **Authorization** can both be present on the same request. When both carry different identities, the server must define a clear policy (reject/mismatch) rather than arbitrarily picking one. A new `Authorization` header on a request does not automatically remove a session cookie that CookieManager will attach.

**Authenticator** in Java is a mechanism for responding to authentication challenges (typically HTTP Basic/Digest or proxy), not where you automatically attach an OAuth bearer token to every request. For OAuth2 access tokens, applications typically supply the header per request or use interceptors/middleware with audited context isolation.

**Do not treat IP / proxy IP as a user identifier:** Many users may go through one NAT/proxy; one user may change IPs between requests. You need an authenticated identity and an appropriate session/token.

## 13. Proxies and Sessions: Changing Network Must Not Change Identity

In the topic **Proxies and HTTP Sessions**, you often see configuration like:

~~~java
HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.example", 8080)))
        .build();
~~~

This is a snippet with an illustrative hostname/port, not a real proxy. `ProxySelector` chooses the network route; **it does not partition sessions/cookies per user**. Cookies are still selected based on URI and cookie policy; the same proxy can serve multiple users, but credentials must not be mixed.

Principles:
1. **Proxy for outbound routing** and **user session for HTTP authentication** are two separate concerns.
2. If a proxy requires per-tenant account/password credentials, attach a separate authenticator or client context per tenant; do not mutate a shared global default password authenticator across threads.
3. With HTTP CONNECT for HTTPS, the app must still verify the hostname/certificate at the TLS endpoint. Using a proxy does not automatically create a trust boundary for credentials.
4. Do not send a website's `Authorization` to a proxy as if it were `Proxy-Authorization`, and do not send proxy credentials to inappropriate upstream APIs.
5. If the system enforces an outbound proxy and an allowlist, do not let untrusted URLs/redirects send requests to hosts/private addresses violating policy.
6. The proxy/connection pool may keep connection-layer state per provider, but **never rely on connection reuse to decide the user principal**.

**Redirects are especially dangerous:** If an API returns `3xx Location` pointing to another host, the client may follow it according to the `HttpClient.Redirect` policy. Policies should forbid or re-validate redirects across trust boundaries, especially when cookies, bearer tokens, or credentials could be sent/copied unintentionally. In both demos, `Redirect.NEVER` is set or redirects are unused to keep the examples clear.

## 14. Cookie Domain/Path and Misunderstood Boundaries

Suppose three applications share the same hostname:

~~~text
https://app.example.com/admin
https://app.example.com/shop
https://app.example.com/api
~~~

If each application uses `sid` with `Path=/`, there is a risk of overlapping cookie names/scopes or the server using the wrong session token, depending on how `Set-Cookie` and the client jar behave.

Key points to remember:
- `Domain` and `Path` assist **cookie routing**, not authorization/tenant isolation.
- There is no `userId` field inside cookie scope for JDK CookieManager to automatically distinguish Alice/Bob.
- Cookies with the same name on the same host/path can **replace** each other, as the first program demonstrated.
- Cookies from a subdomain or broad domain can affect applications in the same scope; control where cookies are allowed to be issued.
- Do not assume HTTP cookies partition independently by port or by HttpClient object if they **share the same CookieManager**.
- Prefer narrow domain/path scopes as needed; avoid setting a broad `Domain` unnecessarily.
- When strong isolation is needed between untrusted applications, use distinct hostnames/security origins and server-side authorization; do not rely solely on cookie `Path`.

**Security tip for browser cookies:** The `__Host-` prefix (requiring `Secure`, `Path=/`, and no `Domain`) can tighten host-bound semantics on supporting user agents. However, JDK CookieManager should not be assumed to act as a browser enforcing all modern prefix/SameSite mechanisms. Always check the client's contract and enforce server logic.

## 15. Logout, Clearing Cookies, and Cleaning Up When a Session Ends

For sessions you own, **true logout** requires combining server-side and client-side actions:

~~~text
Application signals logout
        |
        v
Server invalidates / revokes session ID
        |
        v
Server returns expired Set-Cookie for matching scope
        |
        v
Client's CookieManager updates its store
        |
        v
App evicts user session context and other sensitive caches
        |
        v
Further requests must not use old user identity
~~~

You can clear the entire cookie store of **one** logical session when you no longer want to reuse it:

~~~java
CookieManager manager = /* SEPARATE manager for this session */;
manager.getCookieStore().removeAll();
~~~

This is a snippet: in practice, obtain `manager` from an audited context, not by traversing a global shared cookie store. **Never call `removeAll()` on a shared manager** in a multi-user system because it will break everyone's sessions.

Other items to clear besides cookies:
- OAuth access/refresh tokens and credential handles.
- Session-scoped authorization contexts, response caches, temporary files/downloads.
- Queued HTTP jobs still carrying old tokens.
- HTTP headers/client contexts holding private data via references.
- Observability tags containing sensitive user data.
- Session-associated resources when a tenant is deleted/revoked.

**Deleting local cookies does not replace session invalidation.** If the server has not revoked it, a stolen old token remains valid until expiry. Server-side logout must be authoritative, while also invalidating/rotating refresh tokens as needed.

## 16. Session Fixation, Hijacking, CSRF, and Access Control

Threats related to maintaining sessions:

**Session fixation:** Before login, the client has an attacker-controlled cookie; if the server continues using that ID after authentication, the attacker may know the elevated session ID. **Rotate the session ID upon login or privilege changes**; never elevate a client-proposed session ID.

**Session hijacking:** An attacker obtains a bearer cookie/token. Protect with HTTPS, `Secure`/`HttpOnly` for browser cookies, no secret logging, expiration, short-lived tokens, and revocation. `HttpOnly` does not protect cookies from backend Java code reading the CookieStore; it is a restriction on JavaScript in browsers.

**CSRF:** Browsers may automatically attach cookies to requests in certain contexts; protect state-changing operations with CSRF tokens, SameSite cookie policies, and/or appropriate Origin/Referer checks. **Do not assume Java HttpClient fully supports browser SameSite behavior** or modern cookie partitioning mechanisms.

**Horizontal privilege escalation / IDOR:** Even with Alice's valid session, the `GET /users/bob/orders` endpoint must still check whether Alice is allowed to view Bob's data. Cookie isolation **does not replace** resource-level authorization.

**SSRF:** In backends that proxy requests from user input, do not let callers choose arbitrary URIs and accidentally send cookies/tokens to internal services or hosts outside the trust boundary. Allowlist hosts/services, validate redirect targets, DNS/IP ranges, and outbound network rules.

**Multi-tenant caches:** Using a cache key of only `GET /profile` can cause Alice's data to be returned to Bob. Cache keys must include the authenticated tenant/user scope, or private data must not be cached if isolation cannot be guaranteed.

## 17. Concurrency: Request Context, Callbacks, and Race Conditions

When multiple requests run simultaneously, including with `CompletableFuture`:

~~~text
Thread A (Alice's request) ---> Alice's token
Thread B (Bob's request)   ---> Bob's token
                   |
                   v
           shared HTTP client
                   |
           sendAsync(reqA, ...)
           sendAsync(reqB, ...)
                   |
            callbacks may run
              on a different thread
~~~

**Never use a mutable static `currentUser` or `currentToken` variable** updated by both threads. If A sets the token, B sets the token, and A builds `HttpRequest` afterward, A's request may carry B's token.

Safe approach:
- Obtain the authenticated principal/tenant ID from the request entrypoint.
- Create a dedicated **immutable request context** (`requestId`, `tenantId`, credential reference).
- Build a separate `HttpRequest`, setting the `Authorization` header to the right credential; do not reuse an `HttpRequest.Builder` being modified by other threads.
- If using cookie-backed sessions, retrieve the exact `SessionClientContext` mapped to that principal, and prevent other tenants from referencing that context.
- Pass the correlation context into callbacks explicitly; **do not assume ThreadLocal propagates automatically across executors**.
- Verify the same userID/tenantID when responses update caches, DBs, or data sinks; do not rely solely on completion order.

`HttpClient` itself supports sending requests from multiple threads. That **does not make a mutable CookieStore, custom Authenticator, application cache, or user session map automatically thread-safe for authorization**.

## 18. Should Sessions Be Stored on the Server or Inside Tokens?

The two models have trade-offs:

| Model | Server-side state needed? | Advantages | What must be managed |
| --- | --- | --- | --- |
| Random opaque session ID + server session store | Yes: ID → user, TTL, permissions | Easy centralized revocation/session rotation; client only holds opaque ID | Store availability, replication, expiry, fixation protection |
| Signed self-contained access token | May not need state per access token | Easy distributed verification and sending in Authorization | Signature, audience, scopes, expiry, key rotation, and revocation strategy |
| Cookie containing signed token | Not necessarily a separate map | Browser-friendly token transport mechanism | Cookie/CSRF issues and token verification on every request |

**Do not equate “stateless server JWT” with “stateless client.”** The client still needs somewhere to obtain tokens per request, handle refresh/expiry, and avoid mixing identities. Conversely, using a server-side session store does not mean sockets or CookieManager must hold a global Java object.

A **cookie** is a way to transport credentials over HTTP; a **session** is a business/authentication concept. You can put a token in a cookie, or put a token in an `Authorization` header. Security depends on verification and state boundaries, not merely the location of the token.

## 19. Avoiding Memory/Resource Leaks When Creating Per-User Clients

An architectural issue: if a backend creates a new `HttpClient` and `CookieManager` for every user but **never cleans them up**, the number of clients and session stores can grow unboundedly.

A session-context cache design should include:
- Maximum context count limits and admission control.
- TTL/idle timeout aligned with the server session.
- Logout/revocation clearing caches and cookies.
- Context lookup permissions checked against the authenticated principal.
- Separate memory/connection/downstream quotas when there are many tenants.
- Not retaining credentials longer than necessary.
- Not passing session context references through threads/queues without lifecycle control.
- Recording metrics safely by group/tenant, never using session tokens as labels.

**JDK version nuance:** Java 17's `HttpClient` does not yet have the `AutoCloseable/close()` lifecycle introduced in newer JDKs. Do not write `try (HttpClient client = ...)` expecting it to compile on Java 17. On modern JDKs, check the exact lifecycle API for your version, while clearing application-level session contexts/cookies/credentials remains a separate responsibility.

With the **per-request Authorization** model and a shared stateless client, you can reduce the number of `HttpClient` instances, though you still need to manage token caches per user/tenant and clear/revoke them upon login/logout.

## 20. Multi-User System Design Checklist

| Check Question | Goal |
| --- | --- |
| Who owns the cookie jar? | Per-session manager; no shared CookieManager between users |
| Is a default/global CookieHandler used? | Do not accidentally create a global shared session |
| Does HttpClient have an Authenticator? | If so, credentials belong to the right user/tenant |
| Whom do proxy credentials belong to? | Do not mix proxy user with HTTP app principal |
| Does the client auto-follow redirects? | Do not send credentials across unauthorized trust boundaries |
| How are Cookie Domain/Path/Secure/HttpOnly/SameSite set? | Minimal scope, HTTPS, appropriate server policy |
| Does login rotate the session ID? | Prevent session fixation |
| Does logout invalidate the server session? | Block replay of old tokens |
| Does every endpoint check authorization? | Prevent IDOR / cross-tenant access |
| Are caches keyed by tenant/user? | Prevent data leakage from cached responses |
| Do concurrent HTTP calls have immutable per-request identity? | No global `currentToken` race |
| Do callbacks preserve the right request context? | Do not rely on implicit ThreadLocal propagation |
| Are session contexts capped with TTL? | Do not retain unbounded clients/cookies/credentials |
| Do logs record cookies/tokens/Authorization? | Do not expose secrets |
| Do tests include concurrent A/B and logout isolation? | Catch both state leaks and improper session cleanup |

## 21. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming HTTP keep-alive means the same session | Wrong identity tied to connection | Use verified cookie/token on each request |
| Creating two HttpClients but passing the same CookieManager | User B overwrites A's cookie | Dedicated CookieManager/CookieStore per session |
| Using global `CookieHandler.setDefault` for multiple tenants | Cross-user state leak in code using default | Explicit and scoped cookie handler configuration |
| Trusting `CookiePolicy.ACCEPT_ORIGINAL_SERVER` to separate users | Still leaks cookies on same hostname/path | Application-level tenant isolation, per-user jar |
| Using global `currentToken` in concurrent requests | Request A carries B's token | Immutable request context + per-request header |
| Reusing `HttpRequest.Builder` from multiple threads | Races / misplaced headers | Create a separate builder/request per call |
| Assuming ThreadLocal automatically crosses CompletableFuture callbacks | Wrong user context in callbacks | Explicitly capture/pass context |
| Only deleting local cookies on logout | Old token still usable elsewhere | Server-side session revocation |
| Not rotating session ID on login | Session fixation | Regenerate session ID after authentication |
| Thinking `HttpOnly` prevents Java backend from reading cookie | Misunderstood threat model | `HttpOnly` is for browser JavaScript access |
| Thinking `SameSite` is auto-enforced by all Java HTTP clients | Missing CSRF protection | Analyze threat model and implement server checks |
| Unnecessarily broad Cookie Path/Domain | Session collisions across apps | Minimal scope; separate hostnames when needed |
| Shared proxy Authenticator holding previous user's password | Mixed credentials | Tenant-specific auth/proxy configuration |
| Auto-following redirects to arbitrary hosts | Credential leak / SSRF risk | `Redirect.NEVER` or validate each destination |
| Caching responses by URL only | Returns A's data to B | Key cache with tenant/principal or do not cache |
| Creating an HttpClient per request | Wastes resources, hurts reuse | Reuse per session if using cookies, or shared stateless client |
| Creating HttpClient per user without expiring | Memory/resource leak | TTL/eviction/bounded context count |
| Reading session IDs from logs while debugging | Exposes bearer secret | Hash/redact/correlate via non-sensitive request ID |
| Treating a username-only login fixture as real authentication | Any user can claim any account | Validate credentials and authorization server-side |

## 22. Self-Check Exercises

**1.** Why can the same `HttpClient` send multiple HTTP requests without all of them belonging to the same user?  
**Answer:** The client can reuse connections/transport, whereas user identity must be passed/verified via separate cookies/tokens/authentication on each request.

**2.** Do two different HttpClients with the same `CookieManager` isolate sessions?  
**Answer:** **No.** The same CookieStore stores/sends cookies for the same URI scope; one user can overwrite another user's session.

**3.** Does a server-set `sid` cookie prove the user is allowed to read Bob's resource?  
**Answer:** No. The server must still identify the principal and check authorization against the resource.

**4.** When should you create one CookieManager per user/session?  
**Answer:** When each user/session needs to retain cookies automatically across the same or multiple HTTP endpoints; cookie state must not be shared across users.

**5.** Can a single shared `HttpClient` be used for Alice/Bob?  
**Answer:** Yes, if the client holds no user-specific cookie/auth/proxy state and each HttpRequest carries its own clearly bounded credential, as in Example 2.

**6.** Does `CookiePolicy.ACCEPT_ORIGINAL_SERVER` understand application tenant IDs?  
**Answer:** No. It is an origin-based cookie acceptance policy, not a user identity policy.

**7.** Does `HttpOnly` prevent Java CookieManager from reading a cookie?  
**Answer:** No. This attribute restricts browser-side JavaScript, not the Java application itself managing the cookies.

**8.** Is clearing the local CookieStore enough for a secure logout?  
**Answer:** No. You must invalidate/revoke the session on the server because a copied token could still be used.

**9.** Why must the session ID be rotated on login?  
**Answer:** To avoid continuing to use a session ID known/set by an attacker before transitioning to an authenticated state (session fixation).

**10.** Why should a shared proxy not be treated as a user-differentiation mechanism?  
**Answer:** A proxy IP/network route does not carry an authenticated principal; multiple users share the same proxy, so auth/sessions must still be separated.

**11.** Does a `CompletableFuture` callback automatically see the `ThreadLocal` principal from the request-sending thread?  
**Answer:** Do not assume so; callbacks may run on a different thread, so context must be explicitly captured/passed.

**12.** Does a `SameSite=Lax` cookie mean Java HttpClient definitely behaves like Chrome?  
**Answer:** No. SameSite is a user-agent/browser-context protection mechanism; JDK CookieManager should not be treated as a browser policy engine.

**13.** In Example 1, why does Alice still see `alice` after Bob logs in?  
**Answer:** Because A and B's cookie managers and stores are independent; only in the shared-CookieManager counterexample is Bob mistakenly observed.

**14.** In Example 2, why does calling `request(uri, "demo-key-a")` again still return `alice`?  
**Answer:** The token is attached to the new HttpRequest itself, without global state being overwritten by Bob's request.

**15.** What should be tested to ensure cross-user isolation?  
**Answer:** Two users calling the same endpoint concurrently; user B logging in does not affect A; A logging out does not affect B; a fresh client is anonymous; redirects/proxies/authenticators and caches do not leak credentials/data across user boundaries.

## Official References

- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client-level configuration, cookieHandler, authenticator, proxy, redirects, transport reuse, and sendAsync.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `cookieHandler(...)`, `proxy(...)`, `authenticator(...)`, and `followRedirects(...)`.
- [Java SE 17 — CookieManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html): policy, cookie store, default `ACCEPT_ORIGINAL_SERVER`.
- [Java SE 17 — CookieStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieStore.html): storing, looking up, and removing cookies.
- [Java SE 17 — HttpCookie](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpCookie.html): cookie properties such as Secure/HttpOnly/Path/Domain.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): immutable requests, request-specific headers, and timeout.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): callbacks, execution context, and completion.
- [Java SE 17 — HttpServer (jdk.httpserver)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HTTP server fixture in both examples.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): cookies, Domain/Path, Set-Cookie/Cookie, and scope.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session ID, rotation, expiration, logout/revocation, cookie security, and threat model.

# Authenticator and PasswordAuthentication for Server or Proxy in Java 17

In the **Proxies and HTTP Sessions** section of Java Advanced Networking, an HTTP client may be required by an **origin server** or an **intermediary proxy** to authenticate before returning data. Java provides the **java.net.Authenticator** and **java.net.PasswordAuthentication** API pair so that an application can return a username/password when the networking layer encounters a matching authentication request. With **java.net.http.HttpClient** in Java 11 and later, you attach an Authenticator to **HttpClient.Builder.authenticator(...)**, after which HttpClient can ask for credentials when handling an HTTP challenge that it supports.

**Most important distinction:** The Authenticator in this lesson is a **client-side object that supplies credentials to a server or proxy**, **not** an authenticator for users logging **into your own HTTP server**. If you are building a Java HTTP server that receives requests, checking Authorization from clients is the responsibility of the server framework/gateway or a server-side security filter. These two directions are not interchangeable.

This lesson will explain:

- When an origin server uses **401 Unauthorized** with **WWW-Authenticate**, and when a proxy uses **407 Proxy Authentication Required** with **Proxy-Authenticate**.
- Why **Authorization** and **Proxy-Authorization** must be sent to the right recipient; why proxy credentials cannot be forwarded to the origin.
- How to override **Authenticator.getPasswordAuthentication()**, using **getRequestorType()**, **getRequestingHost()**, **getRequestingPort()**, **getRequestingScheme()**, and context fields to **issue credentials only where permitted**.
- How to use **PasswordAuthentication(String, char[])**, understand the char[] lifecycle, and protect secrets.
- How to configure **HttpClient.Builder.authenticator** and **ProxySelector** properly for Java 17, including HTTP Basic limitations, HTTPS, proxy CONNECT, authentication caching, and retries.
- Two complete Java 17 programs running on loopback: one with both an **origin 401** and a **mock HTTP proxy 407**, and the other testing the credential allowlist without making network requests.
- Security pitfalls, common errors, negative testing, exercises, and review questions.

The practice environment simulates **HTTP Basic authentication on 127.0.0.1** using fixed credentials **student/lab-only**. This is **only dummy lab data**; never use HTTP Basic over an external network without appropriate protection mechanisms.

## 1. Distinguishing an origin server from an HTTP proxy

Suppose a Java application sends a GET request to a web API:

~~~text
Java HttpClient
      |
      | HTTP request
      v
Origin server: api.example.org
~~~

If the origin requires HTTP authentication, it may return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
~~~

The client can ask the Authenticator for the appropriate username/password and then send another request with the header:

~~~http
Authorization: Basic <credentials-encoded>
~~~

**Basic** encodes the `username:password` string with Base64 for transmission in a header; **Base64 is not secure encryption**. When using a real network, there must be a trusted TLS channel and proper server certificate/hostname verification. Do not log the Authorization header and do not put real passwords in code.

If the application must go through a **forward proxy**:

~~~text
Java HttpClient
      |
      | (1) send request to proxy
      v
Corporate proxy: proxy.internal:8080
      |
      | (2) proxy forwards to origin if permitted
      v
Origin server: api.example.org
~~~

The proxy itself may require the caller to authenticate:

~~~http
HTTP/1.1 407 Proxy Authentication Required
Proxy-Authenticate: Basic realm="company-proxy"
~~~

When responding to a proxy challenge, the credentials are intended for the **proxy** and go in:

~~~http
Proxy-Authorization: Basic <proxy-credentials-encoded>
~~~

**Do not convert 401 to 407 or vice versa.** These two codes belong to **two different authenticating entities**, and the application may need two sets of credentials with separate trust scopes.

| Property | Origin server authentication | Proxy authentication |
|---|---|---|
| Requesting party | Final resource server | Forward proxy |
| Challenge HTTP status | **401** | **407** |
| Response challenge header | **WWW-Authenticate** | **Proxy-Authenticate** |
| Credential header in request | **Authorization** | **Proxy-Authorization** |
| Authenticator.RequestorType | **SERVER** | **PROXY** |
| Host/port used to decide whether to issue password | Approved origin host/port | Approved proxy host/port |
| Proves permission to access business data? | Not automatically; server still checks authorization | No; only authenticates with the proxy |
| Can they occur together? | Yes | Yes; use separate credentials |

**A single request can encounter both challenges:** the proxy asks for credentials first before forwarding, and then the origin server asks for different credentials. Do not use a single shared user/password pair for both just because both invoke **Authenticator**.

## 2. What does Authenticator actually do?

**java.net.Authenticator** is a class that allows networking code to ask the application for **PasswordAuthentication** in the current authentication context. The common approach is to subclass it and override:

~~~java
Authenticator auth = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        // Inspect the context requesting authentication.
        // If outside the allowed scope: return null.
        // If valid: return new PasswordAuthentication(user, passChars);
        return null;
    }
};
~~~

This is only a **structural pattern**, not a runnable program. A default Authenticator does not provide login credentials; **getPasswordAuthentication() returns null by default**.

HttpClient uses this callback when an HTTP response requires authentication with a scheme supported by the JDK/provider. **Do not assume the callback is invoked exactly once per HttpRequest**: authentication can be affected by challenges, caching, connection reuse, HTTP version, redirects, proxies, and implementation details. Nor should Authenticator be treated as a hook called before **every** request.

### Protected methods that provide context

| Method | Value/meaning |
|---|---|
| **getRequestorType()** | **Authenticator.RequestorType.SERVER** or **PROXY** |
| **getRequestingHost()** | Hostname of the requesting party; may be null |
| **getRequestingPort()** | Port of the connection requesting authentication |
| **getRequestingSite()** | InetAddress if known; may be null |
| **getRequestingProtocol()** | Protocol, for example **http** or **https** |
| **getRequestingScheme()** | HTTP authentication scheme such as **Basic**, depending on challenge/provider |
| **getRequestingPrompt()** | Prompt/realm from the authentication request (if any) |
| **getRequestingURL()** | URL associated with the request, may be null depending on source |
| **getPasswordAuthentication()** | Returns credentials or **null** to decline |

**getRequestingScheme() is not synonymous with URI scheme.** For example, "Basic" is an **HTTP authentication scheme**, whereas "https" is a **protocol/URI scheme**. Confusing these two concepts can cause you to issue credentials in the wrong case.

### RequestorType is a security boundary

A shared Authenticator can receive requests from many places. If you write:

~~~java
@Override
protected PasswordAuthentication getPasswordAuthentication() {
    return new PasswordAuthentication("admin", secret);
}
~~~

then the application risks **issuing the same credentials to every place the Authenticator is asked**, including a proxy or another host, if there is no verification policy. This is an **anti-pattern**. In production, you must verify at least **RequestorType + host + port + auth scheme + business trust policy/realm** before returning secrets.

**Do not rely on an arbitrary Host header** to decide whether to send a password. The host/port used in the Authenticator context is populated by the networking stack, but host identity must still be checked against the application's endpoint/proxy policy; if users are allowed to supply URLs or a ProxySelector, you must guard against SSRF/redirects and control endpoints.

### Accept or decline

- When the policy **matches** and the secret is valid, return **PasswordAuthentication**.
- When type/host/port/scheme/realm/URL is outside the approved scope, **return null**, and do not issue a password.
- When the secrets manager fails or the secret is expired, report an application error; do not fall back to broader credentials.
- Do not repeatedly return an invalid user/password that triggers multiple challenge/retry rounds. Set deadlines, attempt limits, and observe errors according to policy.

## 3. What does PasswordAuthentication store and what does it not store?

**java.net.PasswordAuthentication** is a simple **data holder**:

~~~java
PasswordAuthentication credentials =
        new PasswordAuthentication("service-user", passwordChars);

String username = credentials.getUserName();
char[] password = credentials.getPassword();
~~~

This is an illustrative snippet, with **passwordChars** already loaded from a secure source. It does **not** perform login itself, send HTTP requests, store cookies, select proxies, perform TLS encryption, or check permissions on the server.

The constructor accepts **String userName** and **char[] password**. According to the Javadoc, **the constructor copies the input password array** before storing it. **getPassword() returns a reference to the password array held by the object**, so the caller is responsible for handling it safely and clearing the array contents when no longer needed. Do not assume the password will immediately disappear from memory as soon as the object is no longer referenced.

### Why use char[] instead of String?

**String is immutable**; the application cannot clear individual characters of a sensitive String once it is created. With **char[]**, when you actually own the array, you can use **Arrays.fill(secret, '\0')** in a finally block after finishing with it. However:

- The array may have been copied into PasswordAuthentication or another library; clearing **one array** does not guarantee all copies are erased.
- The test code in this lesson hardcodes "lab-only" and creates a temporary array purely for ease of learning; this is **not suitable for production**.
- Do not call **new String(secretChars)** for convenient logging/debugging, because doing so creates an immutable copy.
- Do not keep char[] in static fields indefinitely; you need a reload/rotation policy, time-to-live, and restricted permissions.
- Avoid putting username/password in **URI userinfo** or query strings, because URLs can be recorded by logs, caches, metrics, or history.
- Do not return PasswordAuthentication to a new host just because it also returns `WWW-Authenticate: Basic`.

**PasswordAuthentication is not an Authorization header.** The HTTP client/provider uses the object and the challenge to establish a supported authentication mechanism; application code should not manually Base64-encode credentials and assemble Authorization when it has chosen to use Authenticator, unless it genuinely controls the full policy and header APIs of the version in use.

## 4. Attaching a custom Authenticator to Java 17 HttpClient

Java 17 provides **java.net.http.HttpClient.Builder.authenticator(Authenticator)**:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .authenticator(myAuthenticator)
        .build();
~~~

This is an illustrative snippet; **myAuthenticator** must be an Authenticator configured with a policy/credential provider. Once built, **HttpClient** is an immutable object capable of sending multiple requests; **the builder is not thread-safe**. Do not unconditionally create a new HttpClient for every request if you want to take advantage of connection management.

For a proxy:

~~~java
HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.example.internal", 8080)))
        .authenticator(myAuthenticator)
        .build();
~~~

Still a snippet, **proxy.example.internal** is only an illustrative name; do not send requests to it in the demo. **ProxySelector** chooses the path of the network request, while **Authenticator** decides credentials when challenged. **Configuring a proxy does not mean you have authenticated with the proxy**; the proxy may be open or require different credentials.

### Authenticator at HttpClient scope or JVM scope?

| API | Scope/behavior |
|---|---|
| **HttpClient.Builder.authenticator(auth)** | Sets the Authenticator **for a specific HttpClient** |
| **HttpClient.authenticator()** | Returns **Optional<Authenticator>** configured on the client |
| **Authenticator.setDefault(auth)** | Sets the **JVM-wide default authenticator** for networking APIs using the default |
| **ProxySelector.of(address)** | Selects an HTTP proxy for applicable requests |
| **HttpClient.Builder.NO_PROXY** | Selects **direct connection**, bypassing proxies |
| **HttpURLConnection** | Legacy API with default authenticator policy and its own specifics |
| **java.net.http.HttpClient** | Modern client; when specific auth is needed, attach the authenticator directly in the builder |

**Design recommendation:** when building a multi-tenant or multi-endpoint service, **avoid Authenticator.setDefault(...)** if possible. It is a process-wide setting; other libraries can also query the default authenticator and inadvertently receive credentials not meant for them. One **HttpClient per security boundary** with a scoped Authenticator is usually clearer. Do not infer that all libraries honor setDefault in the same way; read the specific API documentation.

### Authenticator is not the only option for every auth type

- HTTP **Basic** challenges can use PasswordAuthentication when supported by the provider.
- **Digest/NTLM/Kerberos/Negotiate** depend on the library/provider/JDK and security policy; do not assume every scheme present in a header is supported by Java 17 HttpClient.
- **Bearer tokens (OAuth 2.0/JWT)** typically use **Authorization: Bearer ...** with their own lifecycle/refresh; **PasswordAuthentication** does not automatically turn a username/password into a bearer token.
- **mTLS** uses SSLContext/certificates, not PasswordAuthentication for HTTP Basic.
- **Cookie/session auth** requires CookieHandler/CookieManager or a client library, and cannot be accomplished solely with getPasswordAuthentication.

## 5. The 401 flow: server requests Basic credentials

~~~text
Java HttpClient                                 Origin server
      |                                              |
      | -------- GET /private ---------------------> |
      |                                              |
      | <--- 401 + WWW-Authenticate: Basic --------- |
      |                                              |
HttpClient asks Authenticator:
    RequestorType = SERVER
    host/port/scheme/realm...
      |
Authenticator checks allowlist and returns
PasswordAuthentication(username, char[])
      |
      | -------- GET /private ---------------------> |
      |           Authorization: Basic ...          |
      |                                              |
      | <---------------- 200 OK ------------------- |
      |                                              |
~~~

The diagram is intentionally simplified. The provider may cache state/challenges, limit retry attempts, and reprocess requests depending on implementation. Do not assume there are always **exact two HTTP requests on the wire** under all conditions, even though that is the typical case for an initial Basic challenge.

**HTTP 401 can be a valid result when no credentials are present**, and does not necessarily become an IOException. When using HttpClient, the application must check **HttpResponse.statusCode()** and handle 401/403 according to policy. If credentials are supplied but still invalid, the server may continue returning 401; the client may stop retrying after a limit or report an error depending on the implementation.

### Basic authentication does not encrypt passwords

~~~text
Authorization: Basic base64(username + ":" + password)
~~~

Base64 is only **reversible encoding**, not encryption/hashing. Use **HTTPS** with proper certificate verification when sending credentials to an origin outside a trusted network. Do not allow proxy TLS interception or logging to leak credentials. Do not write Authorization to logs/traces, and restrict where credentials can be sent.

## 6. The 407 flow: proxy requests credentials

~~~text
Java HttpClient                 Forward proxy                Origin
      |                              |                       |
      | ----- GET absolute-URI ----> |                       |
      | <---- 407 Proxy-Authenticate |                       |
      |                              |                       |
HttpClient asks Authenticator:
    RequestorType = PROXY
    host/port of PROXY
      |
Policy verifies proxy is allowed and returns
PasswordAuthentication(proxyUser, proxyPassword)
      |
      | ----- Proxy-Authorization -->|                       |
      |                              | -- forward if valid ->|
      |                              | <------- response ----|
      | <--------- response -------- |                       |
~~~

**407 is a proxy challenge**, whereas 401 is an origin challenge. RequestorType is an essential input when choosing credentials; **host/port in the callback for PROXY refers to the proxy, not the final website hostname**. If you use the same Authenticator for both sides, the branching condition on type must be explicit.

An HTTP proxy may receive requests in **absolute-form** (e.g., `GET http://service.invalid/resource HTTP/1.1`) or require **CONNECT** to create a tunnel for HTTPS. These two modes have different authentication policies in the Java JDK; this will be analyzed separately in the HTTPS proxy section.

## 7. Complete Java 17 program: 401 origin and 407 proxy on loopback

The demo starts **two local HTTP servers**, one acting as **origin** and one acting as a **mock HTTP forward proxy**. The mock proxy **only authenticates and returns a dummy body**, and **does not forward to the Internet**; as a result, all output is deterministic and no external hostname needs to resolve.

- Origin on 127.0.0.1/ephemeral port: first request missing Authorization returns **401 + WWW-Authenticate: Basic**; request with a valid header returns **ORIGIN_OK**.
- Mock proxy on 127.0.0.1/ephemeral port: request missing Proxy-Authorization returns **407 + Proxy-Authenticate: Basic**; request with a valid header returns **PROXY_OK**.
- The HTTP client for the origin is configured with **NO_PROXY** and an Authenticator that returns credentials only if **RequestorType.SERVER** and the host/port/scheme match the allowlist.
- The HTTP client for the proxy is configured with **ProxySelector.of(...)** and a separate Authenticator only for **RequestorType.PROXY** and the exact proxy host/port/scheme.
- The lab credentials are `student/lab-only`, **not for use on a real network**. HTTP is unencrypted on loopback; this code is only to observe the challenge flow, not a pattern for transmitting passwords over the Internet.
- The application **does not print passwords, Base64 auth headers, or dynamic ports** so that stdout remains stable.

Create the file **AuthenticatorServerProxyDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.Authenticator;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

public class AuthenticatorServerProxyDemo {
    private static String basic(String name, String password) {
        String userPass = name + ":" + password;
        return "Basic " + Base64.getEncoder().encodeToString(
                userPass.getBytes(StandardCharsets.ISO_8859_1));
    }

    private static void reply(HttpExchange exchange, int status,
                              String headerName, String body)
            throws IOException {
        if (headerName != null) {
            exchange.getResponseHeaders().set(headerName,
                    "Basic realm=\"java17-lab\"");
        }
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, data.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(data);
        } finally {
            exchange.close();
        }
    }

    private static Authenticator credentials(
            Authenticator.RequestorType allowedType,
            int allowedPort,
            AtomicReference<Authenticator.RequestorType> observed) {
        return new Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                Authenticator.RequestorType type = getRequestorType();
                if (type != allowedType
                        || getRequestingPort() != allowedPort
                        || !"127.0.0.1".equals(getRequestingHost())
                        || !"basic".equalsIgnoreCase(getRequestingScheme())) {
                    return null;
                }
                observed.set(type);
                return new PasswordAuthentication(
                        "student", "lab-only".toCharArray());
            }
        };
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer origin = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        HttpServer proxy = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(4);
        origin.setExecutor(workers);
        proxy.setExecutor(workers);
        String expected = basic("student", "lab-only");

        origin.createContext("/protected", exchange -> {
            String auth = exchange.getRequestHeaders().getFirst("Authorization");
            if (!expected.equals(auth)) {
                reply(exchange, 401, "WWW-Authenticate", "AUTH_REQUIRED");
            } else {
                reply(exchange, 200, null, "ORIGIN_OK");
            }
        });

        proxy.createContext("/", exchange -> {
            String auth = exchange.getRequestHeaders().getFirst("Proxy-Authorization");
            if (!expected.equals(auth)) {
                reply(exchange, 407, "Proxy-Authenticate", "PROXY_AUTH_REQUIRED");
            } else {
                reply(exchange, 200, null, "PROXY_OK");
            }
        });

        origin.start();
        proxy.start();
        try {
            AtomicReference<Authenticator.RequestorType> serverType =
                    new AtomicReference<>();
            AtomicReference<Authenticator.RequestorType> proxyType =
                    new AtomicReference<>();
            int originPort = origin.getAddress().getPort();
            int proxyPort = proxy.getAddress().getPort();

            HttpClient serverClient = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .authenticator(credentials(
                            Authenticator.RequestorType.SERVER,
                            originPort, serverType))
                    .connectTimeout(Duration.ofSeconds(2))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            HttpRequest serverRequest = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:" + originPort + "/protected"))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();
            HttpResponse<String> fromOrigin = serverClient.send(
                    serverRequest, HttpResponse.BodyHandlers.ofString());

            HttpClient proxyClient = HttpClient.newBuilder()
                    .proxy(ProxySelector.of(new InetSocketAddress(
                            loopback, proxyPort)))
                    .authenticator(credentials(
                            Authenticator.RequestorType.PROXY,
                            proxyPort, proxyType))
                    .connectTimeout(Duration.ofSeconds(2))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            HttpRequest proxyRequest = HttpRequest.newBuilder(
                    URI.create("http://service.invalid/resource"))
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<String> fromProxy = proxyClient.send(
                    proxyRequest, HttpResponse.BodyHandlers.ofString());

            System.out.println("Server status: " + fromOrigin.statusCode());
            System.out.println("Server body: " + fromOrigin.body());
            System.out.println("Authenticator type (server): " + serverType.get());
            System.out.println("Proxy status: " + fromProxy.statusCode());
            System.out.println("Proxy body: " + fromProxy.body());
            System.out.println("Authenticator type (proxy): " + proxyType.get());
        } finally {
            origin.stop(0);
            proxy.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac --release 17 --add-modules jdk.httpserver AuthenticatorServerProxyDemo.java
java --add-modules jdk.httpserver AuthenticatorServerProxyDemo
~~~

Stdout on a successful run:

~~~text
Server status: 200
Server body: ORIGIN_OK
Authenticator type (server): SERVER
Proxy status: 200
Proxy body: PROXY_OK
Authenticator type (proxy): PROXY
~~~

**Compiled with `javac --release 17` and ran successfully** on a JDK with the `jdk.httpserver` module, matching all six output lines. The result relies on local loopback and JDK HttpClient supporting Basic authentication over HTTP in the lab environment. Do not infer from this that HTTPS proxy tunneling has the same policy as HTTP proxying.

### Step-by-step explanation of the demo

1. **HttpServer.create(...,0)** asks the OS to assign an unused port; the two servers do not depend on fixed ports. **HttpClient.Builder.NO_PROXY** ensures the first request goes directly to the origin instead of being routed through a system default proxy.
2. **origin.createContext("/protected",...)** checks **Authorization** from the HTTP request. If missing/wrong, it returns 401 and **WWW-Authenticate**; if valid, it returns 200/ORIGIN_OK. This is the mock server demonstrating the challenge, **not java.net.Authenticator running on the server side**.
3. **proxy.createContext("/",...)** checks **Proxy-Authorization**. In the demo, the proxy is built with HttpServer but does not relay bytes; it only confirms whether the client automatically handles 407 and selects RequestorType.PROXY.
4. **getRequestorType()** is checked in the Authenticator, along with **getRequestingHost**, **getRequestingPort**, and **getRequestingScheme**. A request from an out-of-scope host/port/type receives **null**, with no password.
5. **AtomicReference** only stores the SERVER/PROXY request type to print the result; it does not store passwords. In a real system, Authenticator may be invoked on different threads concurrently; shared state must be thread-safe.
6. **HttpClient.Builder.authenticator** separates policies for origin and proxy. **ProxySelector.of** is used only on proxyClient, while serverClient selects NO_PROXY.
7. The URI **http://service.invalid/resource** is a **reserved dummy destination name for documentation**; the local mock proxy returns the response itself without connecting to that domain. If the mock proxy were replaced with a real proxy, the proxy would have to forward and perform DNS/network calls to the origin according to policy.
8. **HTTP 200 is not sufficient proof that a remote service is authorized**; it only confirms the mock in the lab received the expected Basic header. A production system must verify TLS, proxy/origin identity, and authorization.
9. **Credentials are hardcoded in the lab** and the server checks the Base64 expected header to test the flow. Do not copy this logic into a production server: store password hashes securely, use a tested auth framework, TLS, and proper log/secret handling.
10. **The server and proxy are stopped** in finally; the executor calls shutdownNow. If loopback is blocked or another JDK/provider handles proxy auth differently than assumed, the demo may throw IOException/timeout instead of printing six lines.

## 8. Second Java 17 program: testing credential issuance scope without a network

To separate the **Authenticator policy** from network timing and HTTP challenges, Java provides **Authenticator.requestPasswordAuthentication(Authenticator, host, addr, port, protocol, prompt, scheme, url, RequestorType)**. You can use it to **test an Authenticator instance directly** without actually sending an HTTP request.

The following program allows returning credentials only when:

- RequestorType is exactly **PROXY**.
- Host is exactly **127.0.0.1**.
- Port is exactly **8888**.
- Authentication scheme is **Basic** (case-insensitive comparison).

Any SERVER request or wrong proxy host/port **returns null**. The lab password is not printed.

Create the file **AuthenticatorPolicyDemo.java**:

~~~java
import java.net.Authenticator;
import java.net.InetAddress;
import java.net.PasswordAuthentication;
import java.util.Arrays;

public class AuthenticatorPolicyDemo {
    private static final class ScopedAuthenticator extends Authenticator {
        @Override
        protected PasswordAuthentication getPasswordAuthentication() {
            if (getRequestorType() != RequestorType.PROXY
                    || !"127.0.0.1".equals(getRequestingHost())
                    || getRequestingPort() != 8888
                    || !"basic".equalsIgnoreCase(getRequestingScheme())) {
                return null;
            }
            return new PasswordAuthentication(
                    "proxy-user", "lab-only".toCharArray());
        }
    }

    private static PasswordAuthentication ask(
            Authenticator auth, String host, int port,
            Authenticator.RequestorType type) throws Exception {
        return Authenticator.requestPasswordAuthentication(
                auth, host, InetAddress.getByName("127.0.0.1"),
                port, "http", "lab", "Basic", null, type);
    }

    public static void main(String[] args) throws Exception {
        Authenticator auth = new ScopedAuthenticator();
        PasswordAuthentication allowed = ask(
                auth, "127.0.0.1", 8888, Authenticator.RequestorType.PROXY);
        System.out.println("Expected proxy: " + (allowed != null));
        System.out.println("Proxy username: " + allowed.getUserName());

        System.out.println("Server request denied: " + (ask(
                auth, "127.0.0.1", 8888,
                Authenticator.RequestorType.SERVER) == null));
        System.out.println("Wrong proxy port denied: " + (ask(
                auth, "127.0.0.1", 9999,
                Authenticator.RequestorType.PROXY) == null));
        System.out.println("Wrong proxy host denied: " + (ask(
                auth, "other.invalid", 8888,
                Authenticator.RequestorType.PROXY) == null));
        char[] retrieved = allowed.getPassword();
        System.out.println("Password provided: " + (retrieved.length > 0));
        Arrays.fill(retrieved, '\0');
    }
}
~~~

~~~bash
javac --release 17 AuthenticatorPolicyDemo.java
java AuthenticatorPolicyDemo
~~~

Stdout:

~~~text
Expected proxy: true
Proxy username: proxy-user
Server request denied: true
Wrong proxy port denied: true
Wrong proxy host denied: true
Password provided: true
~~~

**Compiled with `javac --release 17` and ran successfully.** The program **does not connect to `other.invalid`**: that is simply a host string passed into the callback to test the policy. Calling `getPassword()` and **Arrays.fill** illustrates the responsibility to clear the array retrieved from PasswordAuthentication; it does not prove that all copies or secrets stored outside the array can be erased. Do not print or store real passwords.

### Important note on requestPasswordAuthentication

A test program calling **Authenticator.requestPasswordAuthentication(...)** invokes the policy directly, but does **not** prove that an HTTP client/provider supports all schemes or will trigger the callback in every scenario. You need both **policy unit tests** and **real integration tests with HTTP challenges**. The first program addresses the lab integration test; the second tests the policy independently.

## 9. Designing a secure Authenticator in real production systems

When deploying an application that calls multiple origin APIs and a corporate proxy, an Authenticator should restrict credentials by identity and appropriate route:

~~~text
Authentication challenge
        |
        v
getRequestorType() == SERVER or PROXY?
        |
        +-- SERVER:
        |     allowlisted origin + port + scheme + realm?
        |        |
        |        +-- no --> null
        |        +-- yes -> secret provider for that origin
        |
        +-- PROXY:
              allowlisted proxy + port + scheme + realm?
                 |
                 +-- no --> null
                 +-- yes -> secret provider for that proxy
~~~

Context fields such as host/port/scheme can be null/non-fixed depending on the request and provider. A good policy must **fail closed** when a matching endpoint cannot be proven. Do not use overly broad conditions like `host.endsWith("example.com")` if it would accept **evil-example.com**; compare normalized hosts or exact subdomain boundaries, and be careful with IDN/punycode, IPv4/IPv6, and port changes.

### Rules for separating secrets

- **Origin credentials:** scoped to a specific origin API and normally used only over HTTPS to an approved host.
- **Proxy credentials:** used only for a specifically identified proxy, never used to construct an Authorization header sent to an origin.
- **Realm:** can be used as part of a lookup key, but **the realm is supplied by the requesting party** and is not an independent cryptographic identity.
- **Auth scheme:** do not automatically fall back to Basic when a server changes policy or an unfamiliar scheme appears; enforce an approved scheme allowlist.
- **Tenant/service identity:** if two tenants share an HttpClient/proxy but have different secrets, design separate Authenticators/clients per security boundary to prevent privilege mixing.
- **Secret source:** secrets manager, injected credentials, key rotation, or a controlled provider; do not commit passwords to Git or container images.

**Do not automatically supply PasswordAuthentication for arbitrary user-supplied URLs.** If a URL can be controlled externally, an attacker can stand up a server returning 401 to trick the Authenticator into leaking credentials. Require allowlists, proxy rules, redirect restrictions, TLS verification, and isolated security contexts.

### Thread safety and avoiding blocking callbacks

An HttpClient can send multiple requests concurrently; the Authenticator may be called on different threads. Therefore:

- Policy data should be **immutable** or thread-safe.
- Do not store a global variable like **currentHost/currentPassword** and assume each request completes sequentially.
- Scoped secret caching may be used, but **TTL, rotation, and revocation** must be explicit.
- If the password provider contacts a slow secrets management system, the callback can become a bottleneck; preload secrets securely or use a non-blocking mechanism suited to your architecture, and do not prompt for passwords with a UI dialog on a headless server.
- Do not log request context along with credentials or sensitive challenge headers; log only SERVER/PROXY type, masked host/port, error reason, and correlation id.

## 10. HTTPS through a proxy, CONNECT, and Basic policy

**HTTP proxying** and **HTTPS tunneling** are not the same.

### HTTP origin through a forward proxy

For an **http://...** URL, the client typically sends an HTTP request to the proxy with an absolute URI (per HTTP/1.1 proxy semantics). The proxy may return 407/Proxy-Authenticate and the client replies with Proxy-Authorization. If the **proxy transport is plaintext HTTP**, Basic credentials sent to the proxy can be observed on the wire: **do not use them over an untrusted network**. The lab uses loopback to avoid sending credentials over a real network.

### HTTPS origin through an HTTP proxy

For an **https://...** URL, a typical flow is:

~~~text
Client --- CONNECT origin:443 ---> HTTP proxy
        <--- 407 Proxy-Authenticate? ---
        --- Proxy-Authorization? ---->
        <--- 200 Connection Established ---
                  |
                  +--- TLS handshake to origin through tunnel
                  |
                  +--- TLS-encrypted HTTPS request/response
~~~

**HTTPS to the origin does not automatically encrypt authentication messages sent to the proxy before the tunnel is established.** If Basic credentials are sent to a proxy without protected transport, they can be exposed even though traffic inside the tunnel later uses TLS. Use an organization-approved proxy architecture and authentication method (which may include VPN/mTLS/secure proxy). Do not treat an HTTPS indicator at the destination as proof that every hop is confidential.

### JDK limitations regarding Basic with CONNECT

The **Java 17 Networking System Properties** documentation states:

- **jdk.http.auth.tunneling.disabledSchemes** lists **Basic** by default. A listed scheme may **not be used when tunneling HTTPS via HTTP CONNECT**.
- **jdk.http.auth.proxying.disabledSchemes** applies to regular HTTP proxying; by default no disabled schemes are declared in the documentation.
- These are **JDK-level system/security properties** and behavior may vary by provider/JDK configuration.

Therefore, **the HTTP proxy returning 407 in the earlier demo does not prove Basic works with HTTPS CONNECT** in every JDK. If a corporate proxy requires Basic over CONNECT and the client fails to authenticate, inspect the logs, proxy tunnel type, and JVM policy; do not immediately conclude the Authenticator code is wrong.

**Do not automatically remove Basic from the disabled schemes list in production just to fix a handshake.** That can be a security policy downgrade. Evaluate the transport to the proxy, the auth method, and compliance requirements. If the organization approves a configuration change, verify it in a controlled environment and document the risk.

## 11. Authenticator and HTTP headers: do not mix the two mechanisms

When using Authenticator for HTTP challenges, the networking implementation may manage generating **Authorization** or **Proxy-Authorization** according to the scheme. If the application also sets these headers manually, the following can happen:

- The manually set header takes precedence, skipping the Authenticator for that request.
- The header is rejected, or behavior depends on the JDK/provider.
- The request carries credentials to the wrong origin after a redirect.
- Risk of credential caching/leakage when requests are repeated.

Oracle's Java Networking documentation warns that **Authorization** has special restrictions when HttpClient has an Authenticator. **Do not rely on a mechanism that overrides restricted headers in production**. Choose one clear authentication strategy: **challenge-response via Authenticator** for supported schemes, or **explicit auth headers** with a clear scope if the protocol requires it (e.g., bearer tokens), checking the exact API/JDK behavior.

### A challenge is not a login session

**PasswordAuthentication** does not automatically create a login session (cookie/session). If the origin server returns **Set-Cookie** after Basic auth, cookie management belongs to the HTTP client CookieHandler/application and server. A separate token/session lifecycle may be needed; **do not assume all subsequent requests require no authentication** just because a previous request returned 200.

**401** does not necessarily mean "your username/password is definitely wrong"; it can also be caused by missing credentials, an unsupported realm/scheme, a different policy, an expired token, or a server config bug. **403 Forbidden** usually indicates the server denies authorization even though identity is known, though you should still read the API contract to classify it accurately.

## 12. Common errors and how to diagnose them

| Symptom | Causes to check | Appropriate action |
|---|---|---|
| HttpResponse.statusCode() == **401** | Origin requires authentication / credentials rejected | Check WWW-Authenticate, Authenticator.SERVER, exact host/port/realm, scheme |
| HttpResponse.statusCode() == **407** | Proxy requires authentication | Check Proxy-Authenticate, ProxySelector, Authenticator.PROXY, proxy host/port |
| Authenticator callback does not run | No challenge received, authenticator not set, scheme disabled/unsupported, manual header or cache | Check config and controlled traffic; do not guess |
| Callback runs but returns null | Allowlist policy mismatch or secret provider declined | Check RequestorType, host/port/scheme/realm in masked logs |
| Callback returns credentials but still 401/407 | Wrong user/password, realm, scheme, provider, or server/proxy policy | Stop blind retries, verify account/trust, rate limit |
| HTTP 403 | Application/proxy layer denied permission | Do not send additional passwords to unknown hosts |
| IOException/ConnectException | Network/proxy route/port error, not necessarily a credential error | Check DNS, proxy address, firewall, timeout |
| SSLHandshakeException | Invalid TLS certificate/trust/hostname/cipher | Fix trust/PKI; do not enable trust-all |
| CONNECT through proxy returns 407 with Basic | Basic tunneling may be disabled by JVM policy | Check `jdk.http.auth.tunneling.disabledSchemes` and proxy design |
| Authenticator leaks secrets in logs | Logging password, Authorization header, URI userinfo, exception payload | Mask/remove logs, rotate secrets, and audit |
| Multiple authentication retries | Wrong credentials or server rejects challenge flow | Limit retries, check server logs, prevent brute-force |
| No proxy used despite OS configuration | Java proxy properties/default selector differ from expectation | Set ProxySelector explicitly if needed; check Java 17 config |

### Debugging checklist for 401/407

1. Is the request going to the **right origin or right proxy**? Is there a redirect or proxy auto-config?
2. Is the status actually 401 or 407? Which **WWW-Authenticate** or **Proxy-Authenticate** header appears?
3. Was **authenticator(...)** set on the exact HttpClient sending the request?
4. Is **getRequestorType()** in the callback SERVER or PROXY?
5. Do the callback's host and port match the target per policy, rather than the initial host before a redirect?
6. Is the scheme supported/accepted? Is **getRequestingScheme()** Basic or another scheme?
7. Are credentials being blocked by the allowlist/realm (returning null)?
8. Is the username/password from the secret provider expired, out of scope, or currently rotating?
9. Is the application manually setting Authorization/Proxy-Authorization, causing HttpClient not to use the expected flow?
10. If HTTPS through a proxy, is CONNECT blocking the Basic scheme per JDK config?
11. Does the connection to origin/proxy have proper TLS, valid certificate/hostname verification, and protected transport to the proxy?
12. Do client/server logs contain secrets or expose passwords in URLs? If so, treat it as a leak incident.

### Do not equate HTTP status with a Java exception

**401/407 are typically normal HTTP responses under the HTTP protocol**, and do not automatically turn into a dedicated exception class in `java.net.http`. The Authenticator layer may attempt to handle the challenge; if unsuccessful, the client may return a 401/407 response status or report an error depending on the implementation. Business code must always **check statusCode** and **handle IOException/InterruptedException**. Do not write code assuming "if `send` did not throw an exception, login succeeded."

## 13. Security: Basic, HTTPS, proxy credentials, and secret lifecycle

### Do not use Basic over an unprotected network

Basic can be Base64-decoded back into username/password. For origins, use **HTTPS**, certificate chain, and hostname verification; do not disable TLS checks to bypass errors. For proxies, **control the path to the proxy** and support secure authentication per corporate policy. An HTTPS tunnel to the origin does not automatically protect Basic credentials sent to the proxy before CONNECT.

### Restricting credential scope

- Separate usernames/passwords for proxy and origin.
- Scope by host/port and auth method; reject test/staging environments if production secrets are not allowed there.
- Do not issue credentials to another host after a redirect just because it shares the same top-level domain.
- If users supply arbitrary URLs, protect against SSRF, DNS rebinding, and internal private endpoints outside the allowlist.
- Do not create a global Authenticator that returns a default admin password to any caller.

### Rotation and invalidation

Authenticator typically reads secrets from memory/provider. If a password rotates, you may need to refresh the secret provider/cache, rebuild the HttpClient/config according to policy, or close connections with stale auth context. **Do not assume Java HttpClient immediately forgets all cached authentication state when a secret file changes on disk**. Do not hardcode or reuse passwords in production, and do not expose credentials via telemetry.

### Limiting logging

Log **RequestorType, endpoint alias, challenge scheme, status, latency, attempt count**, correlation ID, and filtered error reason; do not log **PasswordAuthentication.getPassword()**, HTTP Authorization/Proxy-Authorization, cookies, or tokens. If enabling Java HTTP debug logs, check redaction policies and storage access first.

### Practical use of char[]

Create `char[]` from the secret provider when needed, limit its lifetime, and clear **the arrays you own** after the API finishes using them. However, PasswordAuthentication **copies the input** and `getPassword()` returns a **reference** to the internal array; do not clear that array before the HTTP client finishes using it or keep the object with an unclear lifetime. Do not treat `char[]` as sufficient against memory dumps; secret isolation, process privileges, and TLS remain essential.

## 14. When should PasswordAuthentication not be used?

There are cases where a different mechanism is needed:

| Case | Usually better approach |
|---|---|
| API using OAuth2 access token/JWT | Token provider + Authorization: Bearer, refresh lifecycle |
| Service-to-service using mTLS | SSLContext/client certificates, identity/authorization checks |
| Web login with cookies and CSRF | CookieManager/client/session framework and CSRF policy |
| HTTP server validating incoming requests | Server-side auth filter, BasicAuthenticator/Servlet Security/Spring Security |
| Proxy connection requiring SSO/Kerberos | Appropriate library/provider or enterprise proxy stack; verify JDK support |
| Role-based authorization needed | Application/policy engine authorization, not just Basic credentials |
| Proxy with multiple custom schemes/methods | Organization-approved proxy configuration SDK, not manually faked headers |

**com.sun.net.httpserver.BasicAuthenticator** (in the `jdk.httpserver` module) is a **server-side authenticator**, distinct from **java.net.Authenticator**. Their names are similar, but their roles differ: one validates incoming credentials, while the other supplies credentials for a client to answer challenges.

If a program needs to send **Bearer** to an origin and **Basic** to a proxy, manage the two mechanisms separately. Do not use a single PasswordAuthentication to store both a token and a password and expect HttpClient to understand the format.

## 15. Performance, retries, and concurrency

### Authentication adds a round-trip

In a challenge-response flow, the initial request may receive 401/407 and another request is then sent with credentials. This adds a network round-trip and can affect latency. Proxy chaining, TLS handshakes, server processing, and authentication caching make actual timings vary. **Do not treat "already logged in earlier" as a guarantee that subsequent requests will never be challenged again**.

### Limiting retries

If credentials are wrong, continuous automatic retries can lock accounts, trigger rate limits, or flood the network. Design **bounded attempts**, auth failure metrics, backoff/lockout policies, and distinguish transient network errors from unrecoverable 401/407 errors. An invalid credential should not be retried indefinitely across many parallel requests.

### Do not automatically replay POST requests with side effects

An authentication challenge may require resending the request; for POST/PUT requests with one-shot bodies and side effects, you must understand BodyPublisher replayability, how many bytes the server already read/processed, and the idempotency policy. **Do not assume every HTTP request can be safely replayed after encountering 401/407**. For payment/order creation workflows, use idempotency keys and reconciliation to avoid duplicate actions.

### Thread safety

An HttpClient can serve multiple requests; the Authenticator callback can run concurrently. When using credential caches or metrics inside the callback, avoid unsynchronized mutable global variables; for example, the lab uses **AtomicReference** to observe request types. In production, you may need an immutable credential map and a thread-safe per-endpoint secret provider.

### Separate timeouts

**HttpClient.Builder.connectTimeout(Duration)** limits establishing a new connection; **HttpRequest.Builder.timeout(Duration)** limits waiting for each request's response. They do not automatically replace an **authentication challenge timeout**, **proxy CONNECT policy**, **overall business deadline**, or **secret provider latency**. Add an overall deadline across multiple retries and network hops; monitor connection/authentication timings.

## 16. Test matrix: must include negative paths

| Test | Input/scenario | What to verify |
|---|---|---|
| Origin challenge | 401 + WWW-Authenticate: Basic | SERVER Authenticator provides valid credentials, receives 200 |
| Proxy challenge | 407 + Proxy-Authenticate: Basic | PROXY Authenticator provides valid proxy credentials, receives 200 |
| No Authenticator | Call origin `/protected` | May receive 401; does not send credentials implicitly |
| Wrong password | Return incorrect PasswordAuthentication | Cannot automatically become an authenticated response |
| Wrong origin host | Policy does not allowlist it | **return null**, does not leak secret |
| Wrong proxy port | Proxy host matches but port is wrong | **return null** |
| Wrong RequestorType | SERVER credentials asked for PROXY | **return null** |
| Unsupported auth scheme | Unapproved scheme | Does not automatically issue credentials |
| Cross-origin redirect | URL redirects from host A to host B | Does not send A's secret to B |
| Multiple proxies | ProxySelector picks a different proxy | Selects exact credentials for that proxy |
| HTTPS CONNECT proxy | Proxy requires Basic over tunnel | Check `disabledSchemes`, do not downgrade security |
| No listener | Wrong proxy/origin address | Classify as ConnectException/IOException rather than auth failure |
| Proxy returns 403 | Denied by policy | Does not retry endlessly with other credentials |
| Password rotation | Old secret expires | Can reload per policy, does not keep stale cached state |
| Concurrent requests | N simultaneous callbacks | No mixing of host, port, user, tenant, or secret |

**Test code matters more than looking at a standalone 200 status.** A proxy returning 200 in a mock does not prove the proxy forwarded bytes to the origin, because the demo's mock intentionally does not forward. When running real integration tests, verify the **right hop**, the right endpoint, and that policies were enforced.

### Testing logging

Trigger a failed auth and verify logs contain only status/type/scheme/endpoint alias. They must not contain Basic base64, passwords, URI userinfo, or tokens/cookies. In security testing, run secret scanners and masking tests on logs/traces.

## 17. Practice exercises

### Exercise A — Observe a real 401

Run **AuthenticatorServerProxyDemo.java**. Temporarily remove **authenticator(...)** from `serverClient`, keeping `NO_PROXY`. Predict what status the `/protected` request will return, and why no `PasswordAuthentication` is created for the origin. Then restore it and verify status 200.

### Exercise B — Observe a real 407

Remove the Authenticator from `proxyClient` while keeping **ProxySelector.of(...)**. Verify that the mock proxy returns 407. Analyze why the API cannot "borrow" `originClient`'s credentials when unconfigured; re-attach the PROXY policy to get 200.

### Exercise C — Check type/port

Run **AuthenticatorPolicyDemo.java**, try changing port 8888 to 9999 or switching `RequestorType.PROXY` to `SERVER`. Write assertions instead of just printing output, ensuring every type/port outside the allowlist returns null.

### Exercise D — Add a realm policy

In the Authenticator, additionally check **getRequestingPrompt()** against the realm configured in the lab. Intentionally change the realm on the server and demonstrate that the policy rejects the credentials. Note that realm has no security guarantee of its own; it only helps namespace credentials.

### Exercise E — Separate secrets on both sides

Replace `student/lab-only` with two pairs: **lab-origin/lab-origin-only** and **lab-proxy/lab-proxy-only**. Update the two mock HTTP servers to validate their respective pairs. If the two pairs are swapped, both origin and proxy must reject them.

### Exercise F — Concurrent requests

Use **sendAsync** for multiple requests to `/protected` through the same HttpClient with a scoped Authenticator, printing results after **CompletableFuture.allOf**. Ensure no global mutable `currentHost/currentPassword` variables are used; try measuring the callback count without assuming callback count equals request count.

### Exercise G — HTTPS and Basic

In a separate TLS lab, create an HTTPS server with a trusted cert/hostname and a Basic challenge, with the client using an appropriate SSLContext. Confirm that username/password appear only inside TLS application data, not exposed in plaintext HTTP; do not disable certificate verification.

### Exercise H — Proxy CONNECT policy

With a test HTTP proxy under your control, compare regular HTTP proxying and CONNECT HTTPS tunneling, checking **jdk.http.auth.tunneling.disabledSchemes** in JDK 17. Explain why Basic for an HTTP proxy can work while Basic for CONNECT is disabled by default. Do not disable security policies on a real network to complete the test.

### Exercise I — Token vs PasswordAuthentication

An API uses a **Bearer token** while the proxy requires **Basic**. Design how to configure the token provider for the origin and a separate PROXY-scoped Authenticator; do not mix `Proxy-Authorization` with `Authorization` and do not log any secrets.

### Exercise J — Redirect and SSRF

Have server A redirect to server B in the lab network. Verify that the Authenticator allowlist refuses to supply A's origin credentials to B, regardless of whether B also sends `WWW-Authenticate`. Discuss DNS rebinding, IP/private network egress policies, and redirect allowlists.

## 18. Self-check questions

**1. In this lesson, is java.net.Authenticator on the server or client?** On the **client** side; it supplies credentials when an external party requests authentication. It does not replace server-side verification.

**2. What does PasswordAuthentication contain?** A username `String` and a password `char[]`; it does not send HTTP requests or verify accounts itself.

**3. What status does an origin return to request HTTP authentication?** **401 Unauthorized**, usually accompanied by **WWW-Authenticate**.

**4. What status does a proxy return to request authentication?** **407 Proxy Authentication Required**, accompanied by **Proxy-Authenticate**.

**5. In which header does the client send origin credentials?** **Authorization**.

**6. In which header does the client send proxy credentials?** **Proxy-Authorization**.

**7. What values does getRequestorType() have?** **SERVER** and **PROXY**.

**8. Does getRequestingScheme() == "Basic" mean the URI is using HTTP?** No. "Basic" is an HTTP authentication scheme, distinct from the URI protocol "http"/"https".

**9. If host/type does not match the allowlist, what should Authenticator return?** **null**, meaning no credentials are issued.

**10. Can a single Authenticator return an admin password for every challenge?** No; that risks leaking the password to untrusted hosts/proxies.

**11. Is Basic secure solely because of Base64?** No. Base64 is reversible encoding; appropriate TLS transport and security policies are required.

**12. Do 401/407 automatically cause an IOException in every Java HttpClient?** No. They may simply be an `HttpResponse` with the corresponding status; you must check `statusCode`.

**13. What does HttpClient.Builder.NO_PROXY do?** Selects a direct connection, bypassing the default proxy.

**14. Does ProxySelector.of(...) automatically log into the proxy?** No. It only selects the proxy; Authenticator/credentials handle authentication.

**15. Why must PasswordAuthentication.getPassword() be handled carefully?** It returns a reference to the password array; do not expose, store/log, or clear it before the client has used it.

**16. Can a single HttpClient need two types of credentials?** Yes, if it encounters both origin 401 and proxy 407. They must be separated by `RequestorType` and endpoint.

**17. Does HTTPS to the origin automatically encrypt Basic credentials sent to the proxy before CONNECT?** No. Transport and security boundaries to the proxy must be evaluated separately.

**18. Why might Basic over CONNECT not work even though HTTP proxy Basic works?** Java 17 JDK has the **jdk.http.auth.tunneling.disabledSchemes** property that disables Basic for CONNECT tunneling by default.

**19. Should Authenticator.setDefault be used unconditionally in a multi-tenant server?** No. JVM-wide configuration can issue credentials out of scope; prefer a per-HttpClient scoped authenticator.

**20. Can PasswordAuthentication be used instead of an OAuth Bearer token?** Not automatically. Bearer tokens are a different auth mechanism requiring their own provider/header/lifecycle.

## Official Java 17 and HTTP references

- **Java SE 17 — java.net.Authenticator:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Authenticator.html
- **Java SE 17 — java.net.PasswordAuthentication:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/PasswordAuthentication.html
- **Java SE 17 — HttpClient.Builder (authenticator and proxy):** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- **Java SE 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java SE 17 — ProxySelector:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html
- **Java SE 17 — Networking System Properties:** https://docs.oracle.com/en/java/javase/17/core/java-networking.html
- **Java SE 17 — HttpResponse:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- **RFC 9110 — HTTP Semantics (401, 407 and authentication):** https://www.rfc-editor.org/rfc/rfc9110
- **RFC 7617 — The 'Basic' HTTP Authentication Scheme:** https://www.rfc-editor.org/rfc/rfc7617

**Key takeaway:** **Authenticator** is a callback that helps a Java HTTP client supply credentials when an **origin server (SERVER/401)** or **proxy (PROXY/407)** requests authentication; **PasswordAuthentication** holds the username/char[] password for the client to use in a supported scheme. **Authorization** is for the origin, and **Proxy-Authorization** is for the proxy. Do not return passwords for every challenge: **verify RequestorType, host, port, scheme, realm, and trust policy**, keep secrets out of source code, protect transport with appropriate TLS, handle timeouts/retries, and check `statusCode`. Configuring **HttpClient.Builder.authenticator(...)** per security boundary is generally safer than a JVM-wide Authenticator, and **Basic authentication over proxy CONNECT has its own policy** that must be verified on Java 17.
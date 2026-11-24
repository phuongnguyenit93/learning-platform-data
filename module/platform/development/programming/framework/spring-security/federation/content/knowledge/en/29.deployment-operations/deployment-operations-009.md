# Timeouts and Connection Limits When Calling Metadata, CAS, or Directory Services

## 1. Why Is This an Operational Requirement for Federation Systems?

In **Spring Security - federation**, many authentication steps access external resources: fetching SAML2 IdP metadata, downloading OIDC discovery/JWKS, making back-channel CAS calls to validate service tickets, binding/searching LDAP/Active Directory, or querying group memberships. When an endpoint hangs and the client lacks configured timeouts, a single login request can tie up threads, sockets, connection pools, and sessions far too long. Under concurrent logins, slowness from one IdP or directory can cascade into web-server congestion, thread-pool exhaustion, file-descriptor depletion, and service outage.

**The goal of this article** is placing bounds **on each stage**, enforcing an **end-to-end login deadline**, governing connections/pools, distinguishing network errors from bad accounts, and ensuring **fail-closed behavior**: a timeout never equals successful authentication.

This article belongs to **Deployment and Operations**. Illustrative environment: **Java 17+, Spring Boot 3.3.5, Spring Security 6.x**, SAML2 Service Provider, OAuth2/OIDC, CAS ticket validation, and LDAP/Active Directory via Spring LDAP/JNDI. All `example.org` addresses are examples, not live endpoints.

### After This Lesson You Must Be Able To

1. Distinguish connect timeout, response/read timeout, request timeout, pool acquisition timeout, LDAP search time limit, and **end-to-end login deadline**.
2. Assign separate time budgets to **metadata**, **CAS**, and **LDAP** rather than using one value for everything.
3. Configure HTTP clients with bounded waits, TLS trust, redirect/response-size policies, and endpoint allowlists.
4. Feed fetched/trust-verified SAML metadata into `RelyingPartyRegistrations.fromMetadata(InputStream)` without confusing downloading bytes with verifying metadata trust.
5. Bound back-channel CAS network time; explain why you must never blindly retry the same **single-use service ticket**.
6. Configure `com.sun.jndi.ldap.connect.timeout` and `com.sun.jndi.ldap.read.timeout` for LDAP bind/search; bound pools, search result sizes, and referrals.
7. Implement bounded retries, bounded caches, circuit breakers, metrics/alerts, and negative tests while preserving security.
8. Run a Java 17 demo on loopback to observe fast responses and timeouts safely.

## 2. Login Flows and Outbound Network Calls

~~~text
Browser  --->  Spring Security app  -------------------->  External systems
                   |
                   +-- SAML2 registration bootstrap/refresh
                   |      -> HTTPS GET IdP metadata
                   |      -> parse XML, verify metadata trust
                   |      -> trusted IdP signing certificates
                   |
                   +-- OIDC login / resource server
                   |      -> HTTPS GET discovery/JWKS
                   |      -> verify token signature and issuer/claims
                   |      -> optional OIDC token/userinfo endpoint
                   |
                   +-- CAS
                   |      -> HTTPS /serviceValidate or /proxyValidate
                   |      -> validate one-time ticket + service URL
                   |
                   +-- LDAP / Active Directory
                          -> TCP + TLS (LDAPS or StartTLS)
                          -> bind and search user/groups
                          -> local authorization
~~~

These calls do not necessarily happen in the same request: SAML metadata may load at startup or refresh periodically; JWKS is usually cached; CAS ticket validation happens on callback; LDAP bind and group lookup may run per login or per session setup. **Set timeouts based on where the call sits in the flow** rather than assuming every call sits directly on the user's critical path.

### Timeouts at Which Layer?

| Limit type | Meaning | If you configure only this type |
| --- | --- | --- |
| **DNS/resolver delay** | Time to resolve hostname to IP. | Not every Java client/OS guarantees DNS is bounded by connect timeout. |
| **Connect timeout** | Waiting to open the TCP connection and implementation connect steps. | Does not bound waiting for the response after connecting; does not apply when reusing a connection. |
| **TLS handshake timeout** | Waiting for TLS handshake and CA/hostname validation. | Does not bound body reads or LDAP searches. Some clients fold it into connect; check implementation. |
| **Read/socket timeout** | Wait between reads or receiving a response after connecting. | Usually a **per-read inactivity timeout**, not a total wall-clock limit for the whole request. |
| **HTTP request/response timeout** | Request-layer limit per HTTP client. | Exact semantics vary by JDK/library, version, and headers vs body stage. |
| **Pool acquire timeout** | Waiting for a connection from a busy pool. | Does not bound connect/read once a connection is leased. |
| **LDAP search time limit** | Server/operation time limit for search results. | Does not replace connect/read timeouts or entry count limits. |
| **Login deadline** | Total budget for an authentication request spanning multiple stages. | Must combine with per-transport timeouts, cancellation, and resource cleanup. |
| **Session/token TTL** | Lifetime of sessions/tickets/assertions, not a network wait. | Does not cure hung LDAP/CAS connections. |

**Important for Java 17:** `HttpClient.Builder.connectTimeout(Duration)` applies only when opening a **new connection**, having no effect on reused connections. `HttpRequest.Builder.timeout(Duration)` in JDK 17 bounds waiting for the **response**; do not assume it acts as a hard deadline across a slowly streaming body. Newer JDKs changed timeout enforcement scope, so verify against your exact runtime. When a whole-payload budget is required, enforce maximum body size, lifecycle/cancellation, and a client designed for whole-response deadlines.

### Why Never Set Timeout to 0?

In APIs such as `HttpURLConnection.setConnectTimeout(0)` and `setReadTimeout(0)`, 0 usually means **unlimited** for that timeout; JNDI `com.sun.jndi.ldap.read.timeout` when unset or non-positive can wait indefinitely. Read the exact client documentation. Never copy `timeout=0` thinking it means "do not wait."

## 3. Time Budgeting and Connection Limits

Suppose a user-facing goal is **login under 6 seconds** per an organization-chosen threshold (illustrative only, not a universal standard). A flow might allocate:

~~~text
Illustrative total budget: 6 000 ms

Application routing, session, crypto, redirects: 1 000 ms
CAS validation HTTPS:                   up to 2 000 ms
LDAP bind + search + group lookup:      up to 2 000 ms
Buffer/cleanup:                         1 000 ms

Each call still requires:
  DNS / connect / TLS
  wait-to-acquire connection
  response/read
  parse and authorization
~~~

If CAS already took 2 seconds, LDAP must not silently extend login by another 5 seconds. Compute an overall deadline using a **monotonic clock** (`System.nanoTime()` for elapsed time), passing remaining budget into outbound calls/cancellation. The numbers above are illustrative; measure real latencies across environments, regions, network hops, and IdP contracts.

**Configure timeouts by layer—never add them blindly:**

- Background HTTP metadata refresh: e.g., 2s connect, 3s read, 1 MiB max body, and 1 jittered retry if policy permits—plus an overall refresh deadline.
- CAS ticket callbacks: normally need fast responses; e.g., 1s connect, 2s read, 3s deadline, **never auto-retrying single-use tickets**.
- LDAP user bind and group search: e.g., 1.5s connect, 2.5s read per operation, search result time/size caps, and total login budget across chained operations.
- Pool acquisition: e.g., 200–500 ms max wait so hundreds of concurrent logins do not pile up waiting on the pool forever.
- Metadata/JWKS should not be fetched over the network on **every HTTP request** when a trusted cache and proactive refresh work.

These numbers are **not Spring Boot defaults**. They must be wired into the actual HTTP client, library, or JNDI configuration in use. A property like `app.timeout` is just an inert custom property until code binds it to the client.

### Pool Capacity Guidance

Size max connections by concurrency, not user headcount alone. For instance, 100 requests/sec where each outbound call averages 150 ms yields roughly **15** concurrent connections (100 × 0.15). A pool of 30 may be an initial test baseline, **not automatically right** under tail latency or slow CAS/LDAP. Raising pool limits indefinitely without bounding upstream capacity simply shifts congestion onto KDC/LDAP/CAS. Measure per-route active/idle/pending counts, per-server limits, TCP file descriptors, and retry fan-out.

## 4. HTTP Metadata: Timeouts Cannot Replace Trust

### 4.1. When Is SAML Metadata Loaded?

`RelyingPartyRegistrations.fromMetadataLocation("https://...")` can fetch IdP metadata over HTTP while building registrations. If startup relies on this endpoint, IdP timeouts can stall or fail application startup. On **Spring Security 6.x**, you can fetch metadata through an application-managed mechanism and call:

~~~java
RelyingPartyRegistrations.fromMetadata(inputStream)
~~~

The `InputStream` overload works well for metadata stored in a database, snapshot file, or fetched by a separate HTTP client. **The caller is responsible for closing the `InputStream`.** This pattern separates network fetch/bounded waits from parsing/registration without automatically turning an HTTP endpoint into a trust anchor.

### 4.2. Java 17: Fetching Metadata with HTTP Connect/Read Timeouts

**BoundedMetadataFetch.java** — standalone Java 17 class that runs when pointed at an approved HTTPS metadata URI. The code handles **fetch transport only**; it **does not verify XML signatures, IdP EntityID, or certificate trust**.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.HttpURLConnection;
import javax.net.ssl.HttpsURLConnection;

public final class BoundedMetadataFetch {
    private static final URI APPROVED = URI.create(
        "https://idp.example.org/saml/metadata");
    private static final int MAX_BYTES = 1_048_576; // 1 MiB

    private BoundedMetadataFetch() {}

    public static byte[] load(URI requested) throws IOException {
        // URI configured from trusted deployment, never from browser.
        if (!APPROVED.equals(requested)
                || !"https".equalsIgnoreCase(requested.getScheme())) {
            throw new IOException("Metadata endpoint not allowlisted");
        }

        HttpsURLConnection connection =
            (HttpsURLConnection) requested.toURL().openConnection();
        connection.setConnectTimeout(2_000);
        connection.setReadTimeout(3_000);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty(
            "Accept", "application/samlmetadata+xml, application/xml");

        try {
            int status = connection.getResponseCode();
            if (status != HttpURLConnection.HTTP_OK) {
                throw new IOException(
                    "Metadata HTTP status: " + status);
            }
            try (InputStream stream = connection.getInputStream()) {
                byte[] bytes = stream.readNBytes(MAX_BYTES + 1);
                if (bytes.length > MAX_BYTES) {
                    throw new IOException("Metadata exceeds 1 MiB");
                }
                if (bytes.length == 0) {
                    throw new IOException("Empty metadata");
                }
                return bytes;
            }
        } finally {
            connection.disconnect();
        }
    }

    public static void main(String[] args) throws IOException {
        // Run against an actual approved HTTPS endpoint, NOT example.org.
        byte[] bytes = load(APPROVED);
        System.out.println("Downloaded bytes: " + bytes.length);
    }
}
~~~

Compile:

~~~bash
javac BoundedMetadataFetch.java
java BoundedMetadataFetch
~~~

There is **no fixed stdout** because a real metadata server must exist and returns varying payloads; `example.org` is illustrative. When the endpoint does not exist, the program must error out rather than printing success. `setConnectTimeout` bounds connecting; `setReadTimeout` bounds the **wait between reads**, not a hard deadline if a peer trickles bytes continuously. To bound the entire refresh, enforce orchestration deadlines/cancellation, body caps, caching, and connection quotas. On cross-origin HTTP redirects, the sample **refuses to follow**; if an IdP requires redirects, enforce allowlists and TLS trust per hop per policy.

Default Java TLS trust and hostname verification must remain enabled. Never install a trust-all `HostnameVerifier` or custom `SSLContext` accepting every certificate to bypass environment errors.

### 4.3. Feeding Fetched Bytes into Spring SAML Registration

This is a **Spring Boot app fragment**, not runnable standalone without dependencies:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.net.URI;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.*;

@Configuration
public class SamlRegistrationConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties()
            throws Exception {
        URI uri = URI.create(
            "https://idp.example.org/saml/metadata");
        byte[] trustedTransportBytes =
            BoundedMetadataFetch.load(uri);

        // Must verify source/metadata signature and IdP EntityID
        // per policy BEFORE treating signing keys as trusted.
        try (InputStream input =
                new ByteArrayInputStream(trustedTransportBytes)) {
            RelyingPartyRegistration corp =
                RelyingPartyRegistrations
                    .fromMetadata(input)
                    .registrationId("corp")
                    .entityId(
                        "https://sp.example.org/saml2/service-provider-metadata/corp")
                    .assertionConsumerServiceLocation(
                        "https://sp.example.org/login/saml2/sso/corp")
                    .build();
            return new InMemoryRelyingPartyRegistrationRepository(
                corp);
        }
    }
}
~~~

Trust boundary warning: `BoundedMetadataFetch` **only** provides timeouts, HTTPS, allowlisting, and a body cap. It **does not verify XML metadata signatures or pin IdP signing credentials per policy**. In production, add dedicated trust validation: metadata signed by an out-of-band provisioned key, approved IdP EntityID and endpoints, verification certificate inventory, TTL/`validUntil`, and atomic promotion. **Never assume calling `fromMetadata` proves the publisher is trustworthy.**

When metadata refresh fails:
- Never load a partial XML body to update public verification keys.
- Never fall back to arbitrarily trusted metadata from another URL.
- You may retain a verified **last-known-good snapshot** while it remains **unexpired and permitted by security policy**, with snapshot-age alerts.
- Once the snapshot's trust validity expires or no trusted key exists, **fail closed** on unverifiable logins rather than bypassing signatures.
- Refresh off the request path, record versions/fingerprints, promote atomically after parsing/trust checks pass, and prevent nodes from diverging on keys.

**OIDC discovery/JWKS** also uses outbound HTTPS with connect/request timeouts, caching, and bounded refresh. Never use a JWKS URI asserted by a JWT header `jku`/`x5u`; JWKS must come from trusted issuer configuration/discovery, never accepting arbitrary keys on unknown `kid`.

## 5. Java 17 HttpClient: `connectTimeout` Is Not a Body Deadline

JDK 17 provides `java.net.http.HttpClient`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HttpClientExample {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://idp.example.org/metadata"))
            .timeout(Duration.ofSeconds(4))
            .GET()
            .build();

        HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());
        System.out.println(response.statusCode());
    }
}
~~~

This is an illustrative transport snippet; the example URL may fail with no guaranteed stdout. Never use `BodyHandlers.ofString()` to read unbounded metadata in production; enforce **bounded body handling** per library and validate metadata after download.

**Java 17 note:** per the docs, `HttpRequest` timeout covers receiving the response; for a slowly streaming body it does not automatically guarantee all reads finish by that deadline. JDK 26 expanded timeout semantics to include the response body—do not project JDK 26 behavior onto JDK 17. Connection reuse also means `connectTimeout` does not apply on every request. Always test exact timeout behavior on your active JDK, container, and HTTP client.

## 6. CAS: Back-Channel Ticket Validation Must Have Network Bounds

### 6.1. Where Does CAS Service Ticket Validation Sit in the Flow?

~~~text
User presents CAS ticket to Spring CAS Service:
  Browser -> /login/cas?ticket=ST-... (one-time)

Spring CAS authentication:
  CasAuthenticationProvider -> TicketValidator
  -> HTTPS GET https://cas.example.org/cas/serviceValidate
     ?service=<exact-service-url>&ticket=<single-use-ticket>
  -> CAS response success/failure
  -> verified principal + local authorities
~~~

Spring Security CAS integrates with CAS Java Client `Cas20ServiceTicketValidator` or the corresponding proxy validator. **CAS ticket validation is an HTTP back-channel call**; if the endpoint hangs, login callbacks tie up servlet threads. Setting a browser login redirect timeout **does not set any timeout on the Java ticket validator**.

Timeouts must attach to the **HTTP connection factory / HTTP transport actually used by your CAS Java Client version**. Some CAS Java Client versions offer `AbstractUrlBasedTicketValidator#setURLConnectionFactory(...)` to plug in an `HttpURLConnectionFactory`; check your exact version's API rather than assuming identical bean properties.

### 6.2. Timeout Contract for the CAS Validator

~~~text
Trusted CAS base URL: https://cas.example.org/cas
Validation endpoint: /serviceValidate or /proxyValidate per profile
Connect timeout: 1 000 ms (example)
Read timeout:    2 000 ms (example)
Total callback deadline: 3 000 ms (example, including pool wait/parse)
Redirect policy: never auto-follow to unfamiliar origins
TLS: validate hostname/CA, no trust-all
Retry: never auto-retry validation with the same one-time ticket
Result timeout: AUTHENTICATION NOT ESTABLISHED
~~~

The above is a **security/transport contract**, not built-in Spring Security CAS properties. Check your exact `org.apereo.cas.client` or legacy CAS client version, then configure its `URLConnectionFactory`/HTTP client with `setConnectTimeout` and `setReadTimeout`, or equivalent pool/request timeouts. **Do not simply add `spring.cas.timeout` to YAML and assume the CAS client reads it.**

On `HttpURLConnection`, an **illustrative helper to wire into the CAS library's URLConnection factory** (not a standalone ticket validator):

~~~java
import java.net.HttpURLConnection;

// connection supplied by the trusted CAS library/factory.
static HttpURLConnection configureCasConnection(
        HttpURLConnection connection) {
    connection.setConnectTimeout(1_000);
    connection.setReadTimeout(2_000);
    connection.setInstanceFollowRedirects(false);
    return connection;
}
~~~

When replacing a built-in factory, never drop **custom TLS trust/hostname verification** used by your organization's CAS client. Preserve the approved HTTPS socket factory/truststore and add timeouts on top. Ensure `service` URL is canonically set to the public HTTPS domain; a CAS service ticket is valid only for the **exact service** it was issued to, never an arbitrary callback URL.

### 6.3. Should CAS Timeouts Be Retried?

**Never automatically retry the same service ticket** as if it were an ordinary metadata GET. CAS service tickets are typically **one-time use**; a timeout can happen **after CAS already processed/consumed the ticket yet before the client received the response**. Retrying the same ticket causes invalid-ticket rejections, retry storms, or confusing login states.

Safe behavior:
- Classify `CAS_VALIDATION_TIMEOUT` separately from `INVALID_SERVICE_TICKET` and `BAD_CREDENTIALS`.
- Never establish `Authentication` from an unvalidated ticket.
- Return a temporary login error page or ask the user to **restart the CAS authentication flow for a fresh ticket**.
- Never log raw `ticket=ST-...` in reverse-proxy logs, URLs, traces, or metrics.
- Limit retries to **health checks / idempotent metadata fetches**, never validation of single-use credentials.
- For proxy tickets (`/proxyValidate`), continue enforcing proxy-chain and trust policies; never disable proxy checks because a backend is slow.

## 7. LDAP/AD: TCP Connect, Bind, Search, and Pool Are Distinct Limits

### 7.1. When Do Bind and Search Happen?

~~~text
Spring login / authorization
  -> acquire LDAP connection (possibly from pool)
  -> DNS + TCP + TLS (LDAPS:636 or StartTLS on 389)
  -> bind (service account or user bind)
  -> search user DN
  -> query group membership / roles
  -> close / return connection
  -> local SecurityContext/authorization
~~~

A slow LDAP directory can cause **multiple operations per login**. If bind takes 2s, user search takes 2s, group search takes 2s, and an LDAP referral to another server takes 2s, total time exceeds budget even though every call had a 2s read timeout. Account for operation counts and parallelism.

**Separate authentication from authorization:** if LDAP bind succeeds yet group lookup times out, never assign `ROLE_ADMIN` or return "authorized" from unread data. You may use a verified, unexpired group cache if policy permits; when authorization data is missing, deny or return temporarily unavailable by design.

### 7.2. Exact JNDI LDAP Timeouts

Two environment properties of the Oracle/OpenJDK LDAP provider:

~~~text
com.sun.jndi.ldap.connect.timeout = "1500"
com.sun.jndi.ldap.read.timeout    = "2500"
~~~

Units are **milliseconds as positive strings**. `connect.timeout` bounds TCP connect; when native LDAP pooling is enabled, it can also bound **waiting for a pooled connection** when exhausted per provider behavior. `read.timeout` bounds waiting for an LDAP response; if unset, the provider default can block indefinitely. Never pass `0` assuming immediate timeout.

**Do not confuse** `com.sun.jndi.ldap.connect.pool.timeout`: that is **how long an idle connection stays in the native JNDI pool before eviction**, not the LDAP operation read timeout. Native pool system properties (`maxsize`, `prefsize`, `timeout`) are JVM-wide and can cause unintended side effects across multiple context sources.

### 7.3. Java 17: JNDI Bind/Search with Timeouts

**LdapDirectoryProbe.java** runs end-to-end only against a **test LDAPS server with an authorized bind user**. There is no fixed stdout because directories and data vary. Never replace LDAPS with plaintext LDAP to "fix" CA errors; import the test CA into the right truststore instead.

~~~java
import java.util.Hashtable;
import java.util.Objects;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

public class LdapDirectoryProbe {
    public static void main(String[] args)
            throws NamingException {
        String dn = Objects.requireNonNull(
            System.getenv("LDAP_BIND_DN"),
            "LDAP_BIND_DN is required");
        String password = Objects.requireNonNull(
            System.getenv("LDAP_BIND_PASSWORD"),
            "LDAP_BIND_PASSWORD is required");

        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL,
            "ldaps://directory.lab.example.org:636");
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL, dn);
        env.put(Context.SECURITY_CREDENTIALS, password);
        env.put(Context.REFERRAL, "throw");
        env.put("com.sun.jndi.ldap.connect.timeout", "1500");
        env.put("com.sun.jndi.ldap.read.timeout", "2500");

        DirContext ctx = new InitialDirContext(env);
        try {
            SearchControls limits = new SearchControls();
            limits.setSearchScope(SearchControls.SUBTREE_SCOPE);
            limits.setTimeLimit(1500);  // search time limit ms
            limits.setCountLimit(20);   // maximum results
            limits.setReturningAttributes(
                new String[] {"uid", "cn"});

            NamingEnumeration<SearchResult> results =
                ctx.search(
                    "ou=people,dc=lab,dc=example,dc=org",
                    "(uid=alice)", limits);
            try {
                int count = 0;
                while (results.hasMore()) {
                    results.next();
                    count++;
                }
                System.out.println("entries: " + count);
            } finally {
                results.close();
            }
        } finally {
            ctx.close();
        }
    }
}
~~~

Compile:

~~~bash
javac LdapDirectoryProbe.java
java LdapDirectoryProbe
~~~

Because URL and bind credentials are lab-specific, the program will **fail** without a live server, trust, and bind credentials; do not assume the API is wrong. The search filter `(uid=alice)` is a **fixed literal**; when incorporating user input, escape LDAP filters properly or use parameterized APIs—never concatenate raw strings and invite LDAP injection.

`SearchControls.setTimeLimit` and `setCountLimit` bound the search itself, yet **do not replace** JNDI connect/read timeouts or gateway deadlines. Search time-limit behavior can vary by server/provider; with paging or referrals, the budget must cover follow-up calls.

### 7.4. Spring LDAP `LdapContextSource`

A Spring Boot app using `spring-boot-starter-data-ldap` (or matching Spring LDAP core) can configure the bean directly:

~~~java
package com.example.directory;

import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfig {
    @Bean
    LdapContextSource directorySource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String dn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(dn);
        source.setPassword(password);
        source.setReferral("throw");
        source.setPooled(false);
        source.setBaseEnvironmentProperties(Map.of(
            "com.sun.jndi.ldap.connect.timeout", "1500",
            "com.sun.jndi.ldap.read.timeout", "2500"));
        return source;
    }
}
~~~

The `application.yml` config uses **application-defined** keys rather than automatically becoming Spring Security LDAP auto-configuration properties:

~~~yaml
app:
  ldap:
    url: "ldaps://directory.lab.example.org:636"
    base: "dc=lab,dc=example,dc=org"
    bind-dn: "${LDAP_BIND_DN}"
    bind-password: "${LDAP_BIND_PASSWORD}"
~~~

Store passwords in a governed secret manager/env; restrict exposure via process environments, logs, and diagnostic endpoints. LDAPS certificates require a trusted CA and hostname validation. Timeout settings on `LdapContextSource` affect only consumers **actually using that bean**. If your organization uses `ActiveDirectoryLdapAuthenticationProvider` (which constructs its own context), `spring.ldap.*`, or another LDAP SDK, inspect that specific connection factory/provider—never assume this bean governs the entire JVM.

**Referrals:** `setReferral("throw")` surfaces referrals so the app handles them per policy; never blindly `follow` across untrusted domains/servers. Referral following opens external connections and consumes extra budget; require egress allowlists, domain trust policies, and per-hop timeouts.

### 7.5. Native LDAP Pooling vs Spring LDAP Pool

Per current documentation, Spring LDAP disables JNDI native pooling by default on `AbstractContextSource`. **Disabling native pooling** in the example avoids caching user-authenticated connections with the wrong lifecycle, especially across user binds and password rotations. For high throughput, consider **Spring LDAP pooling** with:
- `maxTotal`, `maxIdle`/`minIdle`, and per-directory server caps;
- bounded pool acquire wait, idle eviction timeouts, and borrow/idle validation;
- separate pools for service-account searches vs user-bind flows;
- clear semantics for account/password changes and secret rotation;
- active/idle/pending/rejection metrics;
- proper closing/returning of `DirContext`/`NamingEnumeration`.

Do not mistake `com.sun.jndi.ldap.connect.pool.timeout` for a pool wait timeout; Oracle documents it as **idle pooled connection eviction**, distinct from `connect.timeout`. Native JNDI pools rely on JVM-wide System properties scoped by auth principal/credentials; operations must guard against leaks, cross-account reuse, and password changes. Spring LDAP recommends its own pooling implementation for complex pooling rather than toggling native flags carelessly.

## 8. Retries, Circuit Breakers, Bulkheads, and Caching

### 8.1. Retry Only the Right Request Types

| Call | Retryable? | Conditions |
| --- | --- | --- |
| **GET SAML metadata** | Yes, off the login critical path. | Idempotent, 1 jittered retry, trusted origin, bounded deadline, never load partial bodies. |
| **GET OIDC discovery/JWKS** | Yes, per cache/SDK policy. | Never dynamically trust keys from token headers; avoid stampedes on new `kid`. |
| **CAS service ticket validation** | **Never auto-retry the same ticket**. | CAS tickets are usually one-time; timeout may happen after server consumption. |
| **Read-only LDAP search** | Yes in some cases, within budget. | Cap attempts, idempotent, scoped referrals, release connections. |
| **LDAP user bind** | Cautiously, never unbounded. | Can trigger auth failures/lockouts; distinguish transport timeout from wrong password. |
| **LDAP write/provisioning** | Never auto-retry without an idempotency contract. | Outcome after timeout may be ambiguous. |

**Never share one retry policy across all outbound federation calls.** If 5 requests each retry 3 times, upstream load spikes sharply; keep retries finite with jittered exponential backoff only while enough deadline remains. For single-use authentication tickets, prompt a **fresh login** after a CAS back-channel timeout rather than retrying the ticket.

### 8.2. Circuit Breakers Must Never Substitute for Authentication

An open circuit breaker during LDAP/CAS downtime fails fast to protect web threads. Yet it **must never return a verified principal or admin roles** when validation did not run. Distinguish:
- **Authentication unavailable**: render UI/HTTP error with safe retry guidance.
- **Invalid credentials**: only when IdP/CAS/LDAP explicitly confirmed invalid credentials.
- **Authenticated yet unauthorized**: deny/403 per local policy.
- **Metadata refresh unavailable**: may keep using a policy-valid trusted snapshot; if trust expires or a signing key is unknown, fail closed.

### 8.3. Safe Caching

- SAML IdP metadata: cache **trusted/verified snapshots** only, with version, `validUntil`, maximum age, and atomic promotion. Never use stale signatures indefinitely.
- OIDC/JWKS: cache public keys from the trusted issuer with TTL and refresh rate limits; unknown `kid` is a reason code to monitor.
- CAS service tickets: **never cache unvalidated tickets as valid users**, and never make them multi-use. Some Spring CAS flows cache verified assertions separately—keep that distinct from raw ticket replay.
- LDAP group membership: cache identity/permissions with short TTLs and approved revocation semantics; when unable to verify a new user or sensitive role, fail closed. Never rely indefinitely on stale admin groups.
- HTTP connections: pooled sockets may be reused, yet cap max idle/age/connection TTL to avoid stale TLS sessions and pool exhaustion; HTTPS hostname verification remains mandatory.

## 9. Common Failures: Diagnosing by Signals

| Symptom | Primary suspect | Check and fix |
| --- | --- | --- |
| Spring startup hangs when IdP is slow | Unbounded remote metadata fetch. | Fetch proactively with timeouts, trusted snapshot, app bootstrap policy. |
| SAML logins alternate pass/fail | Metadata cache/node parity or IdP response signatures. | Separate transport vs signature; verify keyset refresh without disabling signatures. |
| JWKS unknown `kid` right after rotation | Stale keyset, slow issuer/JWKS endpoint. | Trusted cache refresh, key overlap, rate limiting. |
| CAS 401/redirect loop | Slow `/serviceValidate` or service URL mismatch. | Sanitized CAS ticket validation logs, connect/read timeouts, canonical public service URL. |
| CAS timeout then retry of same ST yields invalid | One-time ticket already consumed by CAS. | Prompt login flow for a new ticket; never retry loop. |
| LDAP bind hangs for minutes | Missing `connect.timeout`, blocked port/DNS, TLS handshake. | Explicit JNDI connect/read, network/firewall/LDAPS trust. |
| LDAP search hangs while bind is fast | Read timeout, unindexed slow group query, referrals. | Bounded read/search limits, query optimization, referral policy. |
| Pool mostly idle yet app stalls | Pool max/pending caps, connection leaks, bind blocking. | Active/idle/pending metrics, return contexts, thread dumps. |
| Directory down yet user gets admin role | Fail-open fallback or stale-privileged cache. | Block authorization; open security incident review. |
| Invalid HTTPS CA | TLS trust/hostname issue, not bad credentials. | Fix certificate chain/truststore; never trust-all. |
| Timeouts jump after proxy deploy | New DNS/egress, TLS or host routing, connection reuse. | Measure per-hop latency and connect/TLS/read errors. |
| Only one pod times out on LDAP | Node DNS/network/proxy config or pool state differs. | Compare versions/regions, connections, ACLs. |

**Diagnose by root cause:** `SocketTimeoutException`, `HttpTimeoutException`, JNDI `CommunicationException`, or `ServiceUnavailableException` must not be mapped blindly into `BadCredentialsException` when the cause is purely network-level. Never leak account details or secrets in user-facing responses.

## 10. Standalone Java 17: Simulating HTTP Response Timeout on Loopback

To observe real timeout behavior **without calling any IdP/CAS/LDAP**, this program spins up an HTTP server strictly on loopback. `/fast` replies immediately; `/slow` waits 1.5 seconds **before sending response headers**. The client configures a 500 ms connect timeout and a **100 ms request timeout** for `/slow`. This demonstrates **timeout before response headers arrive**, not a bound on slow body streaming.

**HttpTimeoutLab.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HttpTimeoutLab {
    private static void reply(HttpExchange exchange, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(2);
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(workers);

        server.createContext("/fast", exchange ->
            reply(exchange, "OK"));

        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(1_500);
                reply(exchange, "LATE");
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                exchange.close();
            } catch (IOException connectionClosed) {
                exchange.close();
            }
        });
        server.start();

        try {
            String base = "http://127.0.0.1:"
                + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(500))
                .followRedirects(HttpClient.Redirect.NEVER)
                .proxy(HttpClient.Builder.NO_PROXY)
                .build();

            HttpRequest fast = HttpRequest.newBuilder()
                .uri(URI.create(base + "/fast"))
                .timeout(Duration.ofSeconds(3))
                .GET().build();
            HttpResponse<String> ok = client.send(
                fast, HttpResponse.BodyHandlers.ofString());
            System.out.println("fast: " + ok.statusCode()
                + " " + ok.body());

            HttpRequest slow = HttpRequest.newBuilder()
                .uri(URI.create(base + "/slow"))
                .timeout(Duration.ofMillis(100))
                .GET().build();

            try {
                client.send(slow, HttpResponse.BodyHandlers.ofString());
                System.out.println("slow: UNEXPECTED_SUCCESS");
            } catch (HttpTimeoutException timeout) {
                System.out.println("slow: TIMEOUT");
            }
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

Compile and run with Java 17 (`jdk.httpserver` module):

~~~bash
javac --add-modules jdk.httpserver HttpTimeoutLab.java
java --add-modules jdk.httpserver HttpTimeoutLab
~~~

**Expected stdout in a healthy loopback environment**:

~~~text
fast: 200 OK
slow: TIMEOUT
~~~

The `/slow` outcome is intentionally produced by the server delaying response headers beyond the request timeout, independent of Internet or KDC connectivity. Results may vary under extreme scheduler/CPU contention; if loopback binding or the executor fails, report that as a lab runtime error. Never use plain loopback HTTP code like this to fetch production metadata; production must use a trusted HTTPS origin as shown in section 4.

**Takeaways from the demo:**
- The 500 ms `connectTimeout` applies when establishing TCP connections, not as a 500 ms total cap on `/slow`.
- `/slow` fails because the response headers did not arrive within 100 ms—a **request-level timeout**.
- If body bytes trickle slowly after response headers, Java 17 request timeouts behave differently; add bounded body caps and deadlines.
- `HttpServer` here authenticates no users and has nothing to do with CAS/LDAP; it strictly demonstrates network wait behavior.

## 11. Observability, Metrics, Logs, and Alerts

### 11.1. Structured Logging Without Leaking Credentials

~~~text
event=federation.outbound_request_failed
trace_id=trace-demo-4b12
protocol=CAS
dependency_alias=cas-prod
phase=READ
reason=TIMEOUT
timeout_budget_ms=2000
elapsed_ms=2010
retry_attempt=0
result=AUTH_NOT_ESTABLISHED
~~~

Values are illustrative, **not emitted automatically by the framework**. Never log:
- Raw CAS `ticket` query params or CAS responses carrying principals/attributes.
- `SAMLResponse`/XML Assertions, OIDC ID Tokens, JWT access tokens, or `Authorization` headers.
- LDAP bind passwords, DNs containing PII, filters containing sensitive user input, or directory-returned attributes.
- Private keys, cookies, client certificates, or authentication secrets.

**Log** server-defined dependency aliases, protocol, phase (`DNS`/`CONNECT`/`TLS`/`POOL_WAIT`/`READ`/`PARSE`), sanitized reason codes, request trace IDs, elapsed ms, configured budget, node/deployment, and result. Never use user IDs, tokens, or full endpoint URLs as high-cardinality metric labels.

### 11.2. Metrics to Observe

| Illustrative metric | Meaning |
| --- | --- |
| `federation_outbound_latency_seconds` | Histogram of outbound call durations per dependency and operation. |
| `federation_outbound_timeouts_total` | Errors by dependency alias/phase; avoid user/token labels. |
| `federation_pool_active_connections` | Currently leased connections. |
| `federation_pool_pending_acquires` | Requests waiting on the pool; signals exhaustion or leaks. |
| `federation_pool_acquire_time_seconds` | Time spent waiting to lease a connection. |
| `federation_metadata_age_seconds` | Age of the last-known-good metadata snapshot. |
| `federation_metadata_refresh_failures_total` | Refresh failures even while logins still use cached keys. |
| `ldap_search_duration_seconds` | Search latency, slow queries, and referral loops. |
| `cas_ticket_validation_failures_total` | Distinguishes `INVALID_TICKET` from `NETWORK_TIMEOUT`. |
| `federation_login_outcome_total` | `SUCCESS`, `BAD_CREDENTIALS`, `DEPENDENCY_UNAVAILABLE`, `POLICY_DENIED`. |

### 11.3. Essential Alerts

- Rapid rise in CAS/LDAP timeout ratios; login p95/p99 breaching SLO.
- Pool pending > 0 sustained while active hits `maxTotal`.
- Login failure rate concentrated on one node/region, indicating DNS/network/pool drift.
- Repeated metadata/JWKS refresh failures or snapshot age exceeding thresholds.
- Spike in TLS/LDAPS handshake errors right after certificate rotation.
- Multi-hop LDAP referrals or group searches driving up timeouts.
- Unexpected retry amplification or open circuit breakers.
- Any security fallback granting `Authentication` during upstream timeouts is a critical security incident.

## 12. Test Matrix: Positive, Fault, and High-Load Cases

| # | Test | Expectation |
| --- | --- | --- |
| 1 | Fast HTTPS 200 metadata from trusted IdP | Downloads, parses, trust-checks, loads registration. |
| 2 | Metadata TCP connect stalls | Bounded by connect timeout; never hangs forever. |
| 3 | Metadata server accepts connection then delays response | Bounded by appropriate read/request timeout. |
| 4 | Oversized metadata body | Rejected by `MAX_BYTES`; no OOM. |
| 5 | Metadata HTTP redirects to untrusted host | Not followed automatically; rejected. |
| 6 | Untrusted metadata TLS certificate | TLS fails; no trust-all. |
| 7 | Malformed metadata XML | Rejected; no signing keys imported. |
| 8 | Invalid metadata signature/trust | Rejected even though HTTPS fetch succeeded. |
| 9 | Stale IdP metadata with policy-valid trusted snapshot | Keeps snapshot within limits and alerts. |
| 10 | Trusted snapshot past `validUntil`/policy age | Stops trusting keys indefinitely. |
| 11 | JWKS fetch times out while valid cached key exists | Uses cached key per policy; alerts refresh failure. |
| 12 | Unknown JWT `kid` before JWKS refreshes | Fails closed; never trusts arbitrary token headers. |
| 13 | Successful CAS validation with valid ticket/service URL | Verified authentication. |
| 14 | CAS HTTPS connect timeout | `DEPENDENCY_UNAVAILABLE`; creates no `Authentication`. |
| 15 | CAS consumes ticket then response times out | Never retries ticket; requires fresh login. |
| 16 | CAS HTTP 5xx | Treated neither as bad credentials nor valid ticket; fails closed. |
| 17 | CAS service URL mismatch | Ticket validation fails; never drop URL binding. |
| 18 | CAS proxy ticket lacking trusted proxy chain | Rejected; never accept-any-proxy. |
| 19 | Invalid CAS TLS certificate | HTTPS rejected; never disable hostname verification. |
| 20 | Fast LDAP LDAPS bind with valid account | Bind passes and user search proceeds. |
| 21 | Slow LDAP connect | JNDI `connect.timeout` triggers. |
| 22 | Slow LDAP bind response | JNDI `read.timeout` triggers. |
| 23 | Unindexed slow LDAP search filter | Search/read timeout fires; fix query/index. |
| 24 | LDAP group lookup spanning multiple searches | Total login deadline cannot stretch indefinitely. |
| 25 | LDAP referral pointing outside allowlist | Blocked/thrown per policy. |
| 26 | LDAP returns excessive entries | Count limit / pagination cap enforces bound. |
| 27 | LDAP simple bind over plaintext URL | Security QA fails; require TLS/StartTLS. |
| 28 | Genuinely wrong LDAP credentials | Bad credentials per provider, not mislabeled as network timeout. |
| 29 | LDAP unavailable yet app assigns `ROLE_USER`/`ADMIN` | Security QA fails; remove fail-open fallback. |
| 30 | Directory role lookup times out | Grants no special groups/privileges. |
| 31 | Native pool full, infinite connection wait | Test fails; bound pool wait and `maxTotal`. |
| 32 | Connections unclosed after error | Leak detector/metrics catch it; fix lifecycle. |
| 33 | SSL handshake hangs/fails | Bounded/clean TLS failure; never disable cert trust. |
| 34 | Extremely slow DNS resolver | Accounted outside connect timeout with budget/supervisor. |
| 35 | Every login request fetches fresh metadata | Throughput test fails; cache and refresh off path. |
| 36 | 100 concurrent logins with slow LDAP | Bulkhead/pool limits keep web server responsive. |
| 37 | Metadata retry storm while IdP is down | Rate-limit/jitter/circuit breaker prevents amplification. |
| 38 | Retrying same CAS ST on timeout | Test fails; never retry single-use credentials. |
| 39 | Metadata refresh passes on node A, fails on node B | Detected by keyset parity / refresh observability. |
| 40 | Read timeout set to 0 in Java/JNDI | Security/config QA fails on indefinite wait. |
| 41 | HTTP client timeout covers headers only while body streams slowly | Body cap + deadline test, not JDK 17 request timeout alone. |
| 42 | Expired login session/ticket | Never raise token TTL to mask LDAP/network timeouts. |
| 43 | LDAP cached admin roles past TTL while LDAP is down | Stop granting admin privileges from stale cache. |
| 44 | Previously authenticated API request while directory fails | Apply clear session/authz policy; grant no new privileges. |
| 45 | Logs contain CAS ticket / LDAP password / JWT | Security QA fails; redact and treat as incident. |
| 46 | Graceful shutdown while outbound requests are pending | Clean cancellation/resource cleanup; no leaked connections. |
| 47 | Pool wait `0ms` misconfigured as unlimited | Verify exact library semantics and test saturation. |
| 48 | IdP metadata ETag/304 on refresh | Retains already-verified snapshot per cache policy; never parses empty body. |

## 13. Anti-Patterns to Avoid

**Setting only `server.servlet.session.timeout`:** that bounds HTTP sessions, not outgoing CAS/LDAP connections.

**Setting only `HttpClient.connectTimeout`:** already-open connections can be reused; response reads can still hang.

**Using `readTimeout=0` to "wait until the IdP responds":** can block forever, causing pool exhaustion.

**Letting CAS/LDAP timeouts fall back to anonymous login:** turns an outage into an authentication bypass. Always fail closed.

**Immediately retrying a CAS service ticket 3 times:** the server may have consumed the ticket on the first attempt, making retries futile and overloading the server.

**Fetching fresh IdP metadata/JWKS on every login:** increases latency, adds critical-path network dependencies, and risks keyset inconsistencies.

**Trusting HTTP 200 metadata:** receiving bytes does not prove XML metadata or signing keys are trustworthy.

**Following redirects to arbitrary URLs from metadata/tenants/users:** invites SSRF and trust confusion. Enforce server-side allowlists, egress policies, and hop limits.

**Enabling native LDAP pooling without measuring waits or leaks:** pools can amplify slowdowns and obscure credential lifecycles; enforce caps, validation, and metrics.

**Reusing another user's pooled LDAP connection:** risks identity confusion, especially after password changes; enforce proper authentication strategies.

**Increasing pool sizes/timeouts indefinitely during incidents:** merely pushes congestion onto CAS/LDAP without fixing upstream latency.

**Concatenating user input into LDAP search filters:** enables LDAP injection; use escaping or parameterized queries.

**Enabling trust-all SSL for CAS/LDAPS:** turns a timeout or CA issue into a MITM vulnerability.

**Keeping privileged group caches forever when the directory is down:** delays revocation and risks privilege escalation.

## 14. Implementation and Operations Checklist

### Choosing Timeouts

- [ ] End-to-end login deadline exists, budgeted across upstreams and operations.
- [ ] HTTP connect/read/request timeouts are all positive with semantics verified on the real JDK/library.
- [ ] Pool acquire wait, `maxTotal`, and idle timeouts match expected throughput.
- [ ] DNS, TLS, redirects, and body sizes are explicitly bounded.
- [ ] Deadlines/cancellation and resource cleanup trigger when users disconnect or upstreams fail.

### SAML / OIDC Metadata

- [ ] Metadata/JWKS come strictly from trusted issuers / allowlisted endpoints.
- [ ] HTTPS CA and hostname validation remain enabled.
- [ ] Metadata fetches are bounded with explicit body caps and redirect policies.
- [ ] Metadata XML signatures/trust, IdP EntityID, and `validUntil` are verified per policy.
- [ ] Verified snapshots are cached with background refresh and atomic rollout.
- [ ] Unknown verification keys fail closed—never accept arbitrary `KeyInfo`/JWK URLs.

### CAS

- [ ] Trusted CAS server URL and canonical public service URL are exact.
- [ ] CAS ticket validator HTTP transport sets connect/read/pool timeouts.
- [ ] Single-use STs are never retried after timeout; prompt a fresh login flow.
- [ ] CAS TLS trust and proxy trust policies remain intact.
- [ ] Never log ticket query parameters or grant `Authentication` on timeout.

### LDAP

- [ ] JNDI `com.sun.jndi.ldap.connect.timeout` and `read.timeout` are positive.
- [ ] LDAPS/StartTLS certificate trust and hostname validation are verified.
- [ ] Bind/search and group lookups fit inside the login budget.
- [ ] Search result count/time limits, escaped filters, and referral policies are enforced.
- [ ] Pooled connections have explicit max/wait/lifecycle rules; contexts/results are closed.
- [ ] No new roles are granted while the directory is unavailable.

### Observability and QA

- [ ] Metrics track p95/p99 latency, timeout phases, and pool active/idle/pending counts.
- [ ] Alerts cover metadata refresh age, CAS validation outages, and LDAP read spikes.
- [ ] Tests cover connect stalls, header stalls, streaming bodies, pool saturation, TLS failures, referral loops, and retries.
- [ ] Never log raw assertions, tickets, passwords, or secrets.
- [ ] Negative tests confirm network timeouts **never create `Authentication`**.

## 15. Review Questions

**1. Why are both connect and read timeouts needed?**  
Because a TCP connection can succeed quickly while the server never sends a response, and vice versa. Connect timeout does not bound subsequent reads.

**2. Does JDK 17's request timeout reliably bound a full streaming HTTP body?**  
No. Check exact implementation/version, add body caps, and enforce an overall deadline/cancellation for the operation.

**3. Should IdP metadata be fetched over the network on every login?**  
No. Use verified cached metadata and controlled refresh to remove upstream availability from the request path.

**4. Does Spring `RelyingPartyRegistrations` accept an `InputStream`?**  
Yes, from trusted metadata bytes fetched by another client; the caller must close the stream. It does not automatically perform every source trust check on those bytes.

**5. Should a timed-out CAS service ticket validation retry with the same ticket?**  
Not automatically. CAS service tickets are typically one-time and may already be consumed. Require a fresh authentication flow when status is unknown.

**6. What happens if JNDI LDAP `read.timeout` is left unset?**  
Oracle/OpenJDK providers can wait indefinitely for responses by default, hanging threads when the directory slows down.

**7. Is `com.sun.jndi.ldap.connect.pool.timeout` a pool acquire wait timeout?**  
No. It governs idle pooled connection eviction; `connect.timeout` behaves differently, including pool wait in certain native pooling modes.

**8. If LDAP bind succeeds yet group lookup times out, should `ROLE_ADMIN` be granted by default?**  
No. Missing authorization evidence must fail closed or adhere to an approved cache TTL/revocation policy.

**9. Why not raise pool `maxTotal` indefinitely when the directory is congested?**  
It piles even more connections and load onto the upstream and exhausts application resources.

**10. Does HTTP 200 on metadata prove the IdP signing certificate is trustworthy?**  
No. A trust anchor/metadata signature or channel/source integrity policy plus issuer/key checks are required.

**11. When a pool is full, what should a login request do?**  
Wait up to a bounded acquire timeout and return a temporary error—never block indefinitely or bypass authentication.

**12. Are CAS `ticket invalid` and CAS `network timeout` identical?**  
No. One is a failed ticket verification and the other is an unknown result; neither grants `Authentication`, though UX and incident handling differ.

**13. How can LDAP referrals impact the time budget?**  
Referrals can spawn extra connections/searches to other hosts; enforce allowlists, trusted domains, per-hop timeouts, and a total deadline.

**14. Should a circuit breaker fall back to an authenticated user when CAS/LDAP is down?**  
No. Circuit breakers fail fast or consult policy-approved trusted caches—they must never turn upstream errors into authentication bypasses.

## 16. Official References

1. [Java 17 HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `connectTimeout`, connection reuse, and TLS configuration.
2. [Java 17 HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout semantics.
3. [Java HTTP Client timeout change in JDK 26](https://inside.java/2026/03/04/jdk-26-http-client/): differences covering response bodies compared to earlier JDKs.
4. [Java URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): connect/read timeouts.
5. [Spring Security RelyingPartyRegistrations API](https://docs.spring.io/spring-security/site/docs/6.0.x/api/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrations.html): `fromMetadata(InputStream)` / `fromMetadataLocation`.
6. [Spring Security SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): registration, asserting-party metadata, and refresh patterns.
7. [Spring Security CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `CasAuthenticationProvider` and back-channel CAS ticket validators.
8. [Apereo Java CAS Client](https://github.com/apereo/java-cas-client): ticket validation library and HTTP connection implementations; verify version.
9. [Jasig CAS Client AbstractUrlBasedTicketValidator API](https://javadoc.io/static/org.jasig.cas.client/cas-client-core/3.6.4/org/jasig/cas/client/validation/AbstractUrlBasedTicketValidator.html): example version exposing `setURLConnectionFactory`; packages vary across CAS client releases.
10. [Oracle JNDI LDAP connect timeout](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/create.html): connect timeout.
11. [Oracle JNDI LDAP read timeout](https://docs.oracle.com/javase/tutorial/jndi/newstuff/readtimeout.html): read timeout.
12. [Oracle JNDI LDAP Service Provider](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap.html): pooling, timeouts, and system/env property semantics.
13. [Spring LDAP Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource`, pooling, and custom environment properties.
14. [Spring LDAP AbstractContextSource API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html): `setBaseEnvironmentProperties` / `setPooled`.
15. [Spring Security LDAP](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): bind/search and authorization.
16. [Apereo CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): service tickets, service URLs, and validation semantics.
17. [Spring Security Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session timeouts vs network timeouts.
18. [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): fail-safe authentication and operations.

**Conclusion:** When deploying federation, bound **every HTTP/LDAP transport timeout, pool wait, body/search limit, and total deadline** so IdP/CAS/directory latency never stalls the system. For metadata, cache only **trusted/verified snapshots**; for CAS, never replay single-use tickets; for LDAP, bound bind/search and handle group lookups safely. **A timeout is never a reason to skip verifying signatures, tickets, or access permissions.**
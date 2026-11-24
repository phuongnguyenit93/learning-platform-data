# Distributed Session Stores, Load Balancing, and Keeping Sessions on One Node

## 1. The SAML2 Problem When Running Across Multiple Nodes

A **Spring Security Servlet SAML2** application acting as a **Service Provider (SP/Relying Party)** typically runs behind a **load balancer (LB)**, ingress, or reverse proxy. When deploying two or more instances, storing session state in each instance's memory can cause SAML logins to fail randomly or force users to log in again.

Example of an application with two nodes **sp-a** and **sp-b**:

~~~text
                            HTTPS
Browser  ------------------------------------------> Load Balancer
                                                       |
                                       +---------------+---------------+
                                       |                               |
                                   Spring SP A                     Spring SP B
                                   HttpSession A                  HttpSession B
                                       |                               |
                                       +------- IdP (external) --------+
~~~

User accesses the application:

1. The LB sends GET **/saml2/authenticate/corp** to node **A**.
2. Spring Security on A creates an **AuthnRequest** and stores the pending request info in **HttpSession**.
3. The browser is redirected to the IdP, logs in or completes MFA.
4. The IdP instructs the browser to POST **SAMLResponse** to **/login/saml2/sso/corp** on the SP.
5. The LB may route the POST callback to **B** instead of A.
6. If A and B keep **separate HttpSessions**, B cannot read the saved AuthnRequest and cannot restore the login context.

The result is **InResponseTo finding no matching request**, login failures, repeated redirects to the IdP, or logging in on A only for the next request hitting B to treat the user as unauthenticated.

There are two main architectural choices:

- **Keeping sessions on one node (sticky session/session affinity)**: the LB tries to route requests belonging to a browser/session to **the same node**; HttpSession state can remain in local memory.
- **Distributed session store**: nodes share **the same session store**, such as **Spring Session + Redis** or **Spring Session JDBC**; callbacks arriving at any node can read session data as long as cookies, session IDs, serialization, and the backend are healthy.

A third model is a **single node**: simple and suitable for learning or small services, but offers no application-level HA.

**Goal:** understand where SAML data lives; when sticky sessions suffice and when Spring Session is needed; how to align cookies, load balancing, keys/certificates, login sessions, and failover testing without weakening SAML checks.

## 2. Distinguishing Five Types of State Often Loosely Called "Sessions"

| Concept | Who manages it? | What is it used for? | Automatically shared across SP nodes? |
| --- | --- | --- | --- |
| **IdP SSO session** | Identity Provider | Maintains the user's logged-in state at the IdP; may enable SSO to other SPs. | **No**, independent of SP HttpSession; managed by IdP infrastructure. |
| **SP HttpSession** | Servlet container or Spring Session | Stores SecurityContext and servlet state for the SP application. | If local: **no**. If Spring Session shared store: **yes**, per configuration. |
| **Pending AuthnRequest** | Saml2AuthenticationRequestRepository | Links SAMLResponse to the SP-sent request, registrationId, and request ID. | By default in **HttpSession**; sharing depends on the session store. |
| **Browser session cookie** | Browser, issued by SP | Holds the **session ID**, helping the SP locate the right HttpSession. | Cookie travels with the browser; nodes recognize it only when store/routing align. |
| **LB affinity mapping/cookie** | Load balancer | Remembers whether the browser should go to node A or B. | Affects **routing** only; **does not** turn local HttpSession A into HttpSession B. |

**RelayState**, **AuthnRequest.ID**, and **InResponseTo** are not the **browser's session ID**. If using **CacheSaml2AuthenticationRequestRepository** to look up by RelayState or InResponseTo, you must design browser/session binding and login CSRF defenses; never treat a cache key alone as proof the request belongs to the current browser.

### HttpSessionSaml2AuthenticationRequestRepository

For the common SP-initiated flow, **Spring Security** defaults to **HttpSessionSaml2AuthenticationRequestRepository** to store **AbstractSaml2AuthenticationRequest** in HttpSession. Spring Session replaces the storage backend behind HttpSession, so you can use Redis/JDBC while preserving the request's binding to the browser session.

Diagram:

~~~text
GET /saml2/authenticate/corp
      |
      v
Saml2WebSsoAuthenticationRequestFilter
      |
      +-- creates AuthnRequest ID=_r123, registrationId=corp
      +-- HttpSessionSaml2AuthenticationRequestRepository.save(...)
      |         |
      |         +-- Local HttpSession A  OR  Spring Session Redis
      v
Browser -> IdP -> POST SAMLResponse, InResponseTo=_r123
      |
      v
Saml2WebSsoAuthenticationFilter / token converter
      |
      +-- Load/remove AuthnRequest from the same browser session
      +-- Verify signature, issuer, audience, time,
          destination, recipient, InResponseTo, and anti-replay policy
      v
Authenticated SecurityContext in SP session
~~~

**A distributed session store does not fix every SAML error by itself.** If the browser omits the cookie, the Response has the wrong issuer, the AuthnRequest expired, IDs mismatch, the IdP certificate is wrong, or SP entityID/ACS differs between two nodes, Redis will not make the Response valid.

## 3. Sticky Sessions: Keeping the Browser on One Node

**Sticky session/session affinity** is a load balancer policy that tries to send a related sequence of requests to the same backend.

Several mechanisms:

| Mechanism | How it works | Limitations |
| --- | --- | --- |
| **LB cookie-based affinity** | LB sets its own cookie/route token, routing subsequent requests by that cookie. | Cookie may be withheld on SAML cross-site POST due to SameSite/Secure; if a node dies, local sessions are lost. |
| **Client IP hash** | LB routes the same IP to the same node. | NAT, mobile networks, IPv6 prefixes, proxies, or IP changes cause low stability and skewed load distribution. |
| **App/session ID affinity** | LB reads the session cookie and maps to the right node. | Must not confuse cookies; **session ID can change after login** due to session fixation protection. |
| **Time-bounded route cookie** | Route token sticks to a backend while healthy and within expiry. | Cookie expiry, cross-site requests, or node failure can switch nodes. |

In practice, a sticky solution must apply consistently to **both the login initiation endpoint and the ACS callback**:

~~~text
Browser -> LB -> A : GET /saml2/authenticate/corp
Browser -> IdP     : authenticate
Browser -> LB -> A : POST /login/saml2/sso/corp
Browser -> LB -> A : GET /me
~~~

If the callback is sent to B while AuthnRequest is stored only on A, SAML can fail. If the user logs in successfully on A yet a later request hits B, B lacks SecurityContext in its local session and forces re-login.

### Sticky Is Not High Availability for Session State

- **Node A crashes or is redeployed**: local HttpSession A is lost; the LB sends the browser to B, which cannot read A's state.
- **Rolling update deployments**: connection draining does not automatically migrate sessions; old sessions can break when the node shuts down.
- **Scaling down**: removing a backend holding local sessions forces users on that backend to log in again.
- **Session timeout**: affinity remains intact yet the server session expired, so the browser still must log in again.
- **Session ID rotation after authentication**: if the LB keys off the session cookie rather than a dedicated affinity cookie, the mapping can shift.

Thus, **sticky sessions solve routing continuity while nodes stay alive**, not session replication, backup, or failover.

### When Is Sticky Still a Reasonable Choice?

- One or a few instances, where forcing users to log in again if a node dies is acceptable.
- SLAs do not require preserving sessions across rollouts/failovers.
- Infrastructure lacks Redis/JDBC and you want to avoid a shared session store dependency.
- LB cookie-based affinity is configured and thoroughly tested for **SAML cross-site POST** and all SP endpoints.
- Rollout draining processes exist to minimize disruption when shutting down a node.
- Not spanning multiple geographic regions or switching nodes frequently.

**Do not** choose sticky merely because "a few test runs logged in fine". You must test slow MFA, cross-node callbacks, node failures, idle timeouts, cookie rotation, and restarts.

## 4. Distributed Session Store: Spring Session Replacing Local HttpSession

**Spring Session** lets servlet applications keep using the **HttpSession** API while actually persisting data in an external **SessionRepository**, such as Redis or a relational database.

Redis model:

~~~text
                    HTTPS
Browser --------------------------------> Load Balancer
                                            |
                                 +----------+----------+
                                 |                     |
                               SP-A                  SP-B
                                 |                     |
                                 +------ Redis --------+
                                       shared sessions
                                       - AuthnRequest pending
                                       - SecurityContext
                                       - session attributes
                                       - idle expiration / TTL
~~~

With the same session cookie, **A and B access the exact same stored session record**. A callback reaching B after AuthnRequest was saved on A can succeed **provided the session key matches, data saves/loads cleanly, the cookie is sent, and all SAML checks pass**.

### Benefits and Costs

| Property | Redis/JDBC shared session | Sticky + local HttpSession |
| --- | --- | --- |
| Callback routed by LB to another node | Can read the same pending AuthnRequest. | Can lose the request due to separate local sessions. |
| Subsequent request switches nodes | Can read the shared SecurityContext. | May be treated as unauthenticated. |
| Node A dies | Session can continue on B if shared store is healthy and session valid. | Local session A does not transfer to B. |
| New node joins | No need to import local sessions if sharing the repo. | Sticky users stay mostly pinned to old nodes. |
| Throughput and latency | Adds store latency/traffic; requires capacity planning. | Avoids shared-store round-trips for most session reads/writes. |
| Central point of failure | Redis/JDBC becomes a critical dependency; needs proper HA and backups. | Independent of a shared store; each node holds its own state. |
| Rolling deploy | Can switch nodes, **if session serialization/schema is compatible**. | Usually hard to preserve sessions when removing nodes. |
| Security | Requires TLS, ACLs, network isolation, TTLs, and store access controls. | Requires memory/node protection; loses local sessions on restart. |

**Distributed sessions do not mean stateless distribution.** The application remains **stateful**: HttpSession lives outside the instance. Spring Session does not turn SAML SSO into stateless JWTs or eliminate cookies.

### Redis or JDBC?

- **Redis**: fast reads/writes, convenient TTLs, well suited for expiring sessions; tradeoffs include availability dependency, memory budget, Redis topology, and serialization policy.
- **JDBC**: can leverage existing DB/transactions/HA and eases data inspection/auditing; tradeoffs include added DB session traffic, schema migrations, and cleanup jobs.
- **Local memory + sticky**: minimal infrastructure dependencies, yet loses sessions on failover.

Decide based on load, SLA, operations, cost, compliance requirements, and session characteristics—not a slogan that "Redis is always better than a DB".

## 5. The SAML Cross-Site POST Trap: SameSite Cookies

A common SAML Web Browser SSO flow uses:

~~~text
GET SP /saml2/authenticate/corp   -> redirect IdP
POST IdP -> SP /login/saml2/sso/corp
~~~

On the POST from the **IdP** page back to the **SP**, the browser may treat this as a **cross-site navigation with POST**. If the SP's session cookie has **SameSite=Lax** or **Strict**, the browser may **omit the SP cookie** on that callback. When that happens:

- Spring SP may create a **new session** and fail to find the AuthnRequest saved in the old session.
- Some LB affinity cookies are also omitted, routing the callback to a **different node**.
- Even with shared Redis, the SP **cannot find the right session** without the right cookie/ID.
- Debugging can misdiagnose a cookie issue as a Redis error or an IdP certificate error.

**SameSite=None; Secure** is a common choice when the session cookie truly must be sent on cross-site POSTs. However, cookie policy must be evaluated across the **entire CSRF/XSS model, browsers, domains, and security requirements**; never disable CSRF app-wide just to "fix login".

In **Spring Boot 3.3**, the properties:

~~~yaml
server:
  servlet:
    session:
      cookie:
        same-site: none
        secure: true
        http-only: true
~~~

can configure SameSite for the servlet session cookie, including Boot-auto-configured Spring Session servlet SessionRepository. **Secure** requires external browser flows to run over **HTTPS**; local HTTP examples do not represent production behavior.

### Both Session Cookie and LB Affinity Cookie Must Be Tested

A system may carry:

~~~text
SESSION=<session-id>              (Spring Session)
LB_AFFINITY=<routing-token>      (Load Balancer)
~~~

Exact names depend on your configuration; they are not the same cookie. If the session cookie uses SameSite=None while the affinity cookie uses Lax, the SAML POST callback may **carry enough cookie to find the Redis session**, yet the LB still switches nodes. With a Redis shared store, that usually causes no session harm; with local HttpSession, it is a critical failure.

**Never widen cookie domains arbitrarily**, never disable HttpOnly so JavaScript can read the session ID, and never put session IDs or affinity tokens in URLs. If a proxy terminates TLS, align **forwarded proto/host** so Spring generates the right baseUrl, ACS, and cookie policies.

### Checklist When Cookies Are Not Sent

1. Browser DevTools → Network on the **POST ACS**; inspect the **request Cookie header** and browser blocking reasons.
2. Check **SameSite**, **Secure**, **Domain**, **Path**, **Expires/Max-Age**, and browser third-party/cross-site policies.
3. Verify the exact public SP host before and after redirects; avoid mixing `http://internal` and `https://app.example.com`.
4. Test real browsers, especially mobile, popups, cross-domain flows, and redirects from external IdPs.
5. Check both the **Spring SESSION/JSESSIONID cookie** and the **LB affinity cookie** if using sticky sessions.
6. Check session expiration and the SAML AuthnRequest repository rather than concluding "request missing" means Redis is empty.

Some browsers have differing exceptions/restrictions around SameSite; **never rely on short-lived exceptions** or random results from a single browser as a production guarantee.

## 6. Do Not Lose Login CSRF Protection When Switching Request Stores

Keeping **AuthnRequest in HttpSession** gives a vital security benefit: the pending request is bound to the **browser/session that initiated SSO**. A Response prepared by an attacker for the attacker's own session will not match a pending request in the victim's session.

Switching to a global cache and looking up requests solely by **RelayState or InResponseTo** can introduce a **login CSRF/login fixation** vulnerability:

~~~text
Attacker initiates SAML login in attacker's browser
  -> gets AuthnRequest ID=_attacker
  -> shared cache stores request by ID or RelayState

Attacker forces victim's browser to POST a valid Response
  -> SP queries cache by ID/RelayState carried in request
  -> without binding to victim's browser session, risks accepting it mistakenly
~~~

**Distinguish two models that "both use Redis":**

- **Spring Session Redis replacing the HttpSession backend**: the browser's HttpSession cookie still binds the pending AuthnRequest to the exact session; this is the simplest way for multiple nodes to share SAML sessions.
- **Custom Saml2AuthenticationRequestRepository querying Redis by RelayState independent of the browser**: lacks built-in browser binding; requires adding correlation, TTL, one-time consumption, and anti-replay/login CSRF defenses.

Do not swap out the request repository merely to "avoid depending on sessions" without analyzing equivalent security controls. Spring Security offers custom/cache request repositories, yet using them safely demands understanding the security tradeoffs.

## 7. Configuring Spring Boot 3.3.5 + Spring Session Redis + SAML SP

The example is a **Spring Security Servlet SAML2 Service Provider**, running **two instances** sharing Redis. A real deployment requires **real trusted IdP metadata** and the IdP having the **SP entityID/ACS** properly registered.

### 7.1. Maven Dependencies Aligned with Boot 3.3

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>saml-shared-session-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
        </repository>
    </repositories>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-saml2-service-provider</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-redis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.session</groupId>
            <artifactId>spring-session-data-redis</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Compatibility note:** For **Boot 3.3**, use **spring-session-data-redis** and **spring-boot-starter-data-redis** as above. A starter named **spring-boot-starter-session-data-redis** appears in newer Spring Boot documentation; do not copy that dependency into a Boot 3.3 project without checking the BOM/version.

**There is no need to add @EnableRedisHttpSession** when Spring Boot already auto-configures an appropriate Spring Session store. Adding the annotation manually can stop certain auto-config settings from applying as expected; use it only when you genuinely need explicit control over the repository/TTL.

### 7.2. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  data:
    redis:
      host: "${REDIS_HOST:127.0.0.1}"
      port: ${REDIS_PORT:6379}
  session:
    store-type: redis
    timeout: 30m
    redis:
      namespace: "samlsp:session"
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "${SAML_IDP_METADATA_URI}"

server:
  port: ${APP_PORT:8080}
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        same-site: none
        secure: true
        http-only: true

app:
  node-id: "${INSTANCE_ID:node-local}"
~~~

Explanation:

- **spring.data.redis.host/port:** Redis connection; local demo uses 127.0.0.1:6379. Production needs a Redis endpoint with TLS, network isolation, ACLs/auth, and dedicated HA.
- **spring.session.store-type=redis:** selects the Redis session store; when only one Spring Session module is on the classpath, Boot 3.3 can also pick it automatically, yet the property makes intent explicit.
- **spring.session.timeout=30m:** example session idle timeout, not the SAML Assertion lifetime or IdP SSO session timeout.
- **spring.session.redis.namespace:** isolates session keys by application/environment. **Nodes of the same SP cluster must share the same namespace** to share sessions; other applications should use distinct namespaces.
- **SAML_IDP_METADATA_URI:** trusted IdP metadata URL. Without a valid IdP, the demo cannot complete real SSO.
- **APP_PORT/INSTANCE_ID:** allows running two processes on different ports with distinct node labels during testing.
- **server.forward-headers-strategy=framework:** helps reconstruct the right external scheme/host behind a proxy. Only accept forwarded headers written by a trusted LB/proxy and **never let the Internet directly control `X-Forwarded-*` headers**.
- **same-site:none + secure:true:** supports SAML cross-site POST callbacks when cookie policies permit. The browser must connect via a public HTTPS endpoint; do not expect local HTTP to demonstrate production cookie behavior.

**Security tradeoff:** with Redis shared sessions, any node can read a session given the same cookie and store. That is the goal of the architecture, yet Redis must be **secured as an authentication data store**, not an open-network Redis cache.

### 7.3. Main class

**src/main/java/com/example/samlsession/SamlSessionApplication.java**

~~~java
package com.example.samlsession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSessionApplication.class, args);
    }
}
~~~

### 7.4. SecurityFilterChain

**src/main/java/com/example/samlsession/SecurityConfig.java**

~~~java
package com.example.samlsession;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/node", "/error",
                    "/saml2/metadata", "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

SAML AuthnRequest and SAMLResponse are handled through Spring Security filters. **Do not create a manual controller to receive SAMLResponse**. Post-login SecurityContext uses **HttpSession backed by Redis via Spring Session**.

### 7.5. Controller for Two-Node Testing

**src/main/java/com/example/samlsession/NodeController.java**

~~~java
package com.example.samlsession;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class NodeController {

    private final String nodeId;

    public NodeController(@Value("${app.node-id:node-local}") String nodeId) {
        this.nodeId = nodeId;
    }

    @GetMapping("/")
    public String home() {
        return "SAML shared-session SP";
    }

    @GetMapping("/node")
    public String node() {
        return "Serving from " + nodeId;
    }

    @GetMapping("/me")
    public String me() {
        return "Authenticated on " + nodeId;
    }
}
~~~

**GET /node** shows which node is currently serving the request without **exposing session IDs, cookies, NameIDs, or user data**. **GET /me** requires Authentication and demonstrates whether the browser maintains its logged-in session when the LB switches nodes.

### 7.6. Startup

Two environment prerequisites exist:

1. Redis is running, allowing both instances to connect to the same database/namespace per config and policy.
2. A real IdP sandbox has registered the SP metadata/ACS using the **LB's public HTTPS address**, the SP trusts the IdP verification cert, and the SSO flow can run.

Run the project with:

~~~bash
mvn spring-boot:run
~~~

To test two independent processes, use **two terminals** with preconfigured environments:

~~~text
Process A:
  APP_PORT = 8081
  INSTANCE_ID = sp-a
  REDIS_HOST = shared Redis address
  SAML_IDP_METADATA_URI = approved IdP metadata URL

Process B:
  APP_PORT = 8082
  INSTANCE_ID = sp-b
  REDIS_HOST = same Redis as A
  SAML_IDP_METADATA_URI = same matching IdP configuration
~~~

In each terminal run **mvn spring-boot:run**. The LB's HTTPS front door points to A:8081 and B:8082. Both processes must share **the same code/build, Redis namespace, SP entityID/ACS, and trust configuration**. With separate host/container deployments, configure real hosts/ports and TLS at the proxy.

**Do not** register **localhost:8081** as A's ACS and **localhost:8082** as B's ACS within the same multi-node application. The IdP needs **one stable external SP entityID/ACS** that browsers reach through the LB, such as **https://sp.example.org/login/saml2/sso/corp**.

### 7.7. Observed Results

- **GET /node** returns **Serving from sp-a** or **Serving from sp-b** depending on which node the LB picks. Locally with a single process, it returns that nodeId.
- **GET /saml2/authenticate/corp** initiates an AuthnRequest to the IdP for registration `corp`.
- **POST /login/saml2/sso/corp** must be handled by the framework; when the browser carries back a valid session cookie, another node can retrieve the pending request from Redis for correlation.
- **GET /me** after valid SAML login returns **Authenticated on sp-a** or **Authenticated on sp-b**. Staying authenticated across node switches shows the session store/cookies and SecurityContext continue working, though **only integration tests with real signed SAML prove full SSO correctness**.
- **GET /me** before login triggers SAML login instead of returning a fake principal.

Without real IdP metadata and a healthy Redis instance, the application may fail to start or fail to complete login; that is an expected constraint of an example with external dependencies.

## 8. Spring Session Redis: What to Check Beyond a Few YAML Lines

### 8.1. Both Nodes Must Share Session Data Versions

Session attributes may include:

- **SPRING_SECURITY_CONTEXT**, Spring Security's principal and Authentication;
- Pending AbstractSaml2AuthenticationRequest, depending on request repository/version;
- Other application session attributes.

Spring Session Redis typically uses **Java serialization** by default for session attributes depending on configuration/version. When node A writes an object and node B reads it, both sides must deserialize the same type/class/`serialVersionUID`/schema. During rolling deploys, objects/classes from the old version may be incompatible with the new version.

**Do not assume having Redis up means you are done.** Integration-test:

1. A creates AuthnRequest and writes the session to Redis.
2. B reads that exact session after the callback.
3. B reads the SecurityContext that A saved after login.
4. Deploy A on the old version and B on the new version during overlap; verify sessions still read/write cleanly.
5. Expire old sessions via TTL and plan serializer changes carefully.
6. Test session fixation protection rotating the session ID and cookie after login.

Do not blindly enable a JSON serializer for production sessions assuming it always supports every Spring Security/SAML object. **Serialization must undergo security review**, configure type whitelists/modules properly, and pass upgrade tests. Native Java deserialization carries risks if Redis is accessed without authorization; isolate Redis and restrict arbitrary writes.

### 8.2. Flush, Save Mode, and Consistency

Spring Session exposes settings such as **spring.session.redis.flush-mode** and **save-mode**; they govern when sessions write to Redis and how attribute mutations are tracked.

- **on-save** typically defers writing until session commit/save at the end of the request; verify AuthnRequest state is actually persisted **before redirecting the browser to the IdP**.
- **immediate** can write earlier at the cost of extra I/O, depending on repository/version.
- If the application mutates an object inside the session without calling `setAttribute` in a way the framework tracks, `save-mode` can affect consistency.

**Never change flush/save modes by guesswork.** Test with the real request/filter chain and observe session persistence under the exact configuration. Across multiple nodes, watch for **race conditions** when concurrent requests for the same session mutate state; merge/locking strategies are not guaranteed automatically on every backend.

### 8.3. TTL, Timeout, Eviction, and Logout

- **spring.session.timeout=30m** in the example is the **SP session inactivity timeout**; it is not the IdP SSO timeout.
- **Pending AuthnRequests** should have a short lifetime, one-time correlation, and policy-bound expiration; custom repositories need appropriate dedicated TTLs.
- Redis memory eviction can purge sessions before TTL under improper configuration/memory pressure.
- Once a session is invalidated, neither A nor B may continue accepting the old cookie after state is deleted from the shared store.
- **Local logout** removes the SP session and does not automatically log out the IdP or other SPs; **SAML Single Logout (SLO)** requires separate configuration.
- If Redis is unreadable/unwritable, enforce **fail-closed behavior** or a security-reviewed degraded flow; never silently forge an authenticated session from unverifiable data.

### 8.4. Redis Availability and Data Protection

Production needs plans for:

- Redis **TLS** and passwords/ACLs/identities where supported; network policies permitting access only from SP nodes.
- Redis HA (replicas/sentinel/cluster/managed service), handling failovers and potential loss of recent writes per persistence/replication policy.
- Backups/restores if business requires them; for session data, fast recovery often outweighs restoring stale sessions.
- Maxmemory/eviction limits, metrics for session counts, failed logins, latency, connection pools, and timeouts.
- Separate keyspace namespaces per app/environment to prevent accidental cross-app key deletion across Redis.
- Never log raw sessions, SAMLResponse, SecurityContext, cookies, or Redis credentials.
- Test real Redis restarts and leader failovers, not merely `/node` health checks.

Redis can become a **single point of failure** without HA. Choosing distributed sessions does not inherently yield higher availability than local sessions if the shared store is an unredundant single server.

## 9. Load Balancers, HTTPS, and Forwarded Headers

Even with Redis, both nodes must see **the same external SP address**:

~~~text
External:
  https://sp.example.org/saml2/authenticate/corp
  https://sp.example.org/login/saml2/sso/corp
  https://sp.example.org/saml2/metadata/corp

Internal:
  http://sp-a:8080
  http://sp-b:8080
~~~

If Spring generates metadata or AuthnRequests with **http://sp-a:8080/login/saml2/sso/corp**, the IdP may reject them because ACS/Recipient/Destination mismatch the allowlisted public URL. Verify:

1. **SP entityID** is uniform per registration.
2. **ACS URL** is identical on A/B and matches the HTTPS URL registered at the IdP.
3. **IdP SSO URL, issuer, and signing/verification credentials** are loaded identically.
4. LB forwarded proto/host/port are accurate, **written/overwritten by the trusted proxy**, never trusting raw headers from Internet clients.
5. Callback POSTs are routed by the LB to any healthy node without accidentally blocking **/login/saml2/sso/** or stripping form fields.
6. LB response header/cookie rewriting does not break **Secure, SameSite, Path, or Domain**.
7. Health checks and readiness distinguish **live process** from **ready Redis/metadata dependencies**.

**Never use a node's IP address** as the SP entityID in scaled/failover environments. Every node of a logical SP must appear as the same application to the IdP, unless intentionally designing multiple registrations/tenants.

### Can Sticky Sessions Still Be Used Alongside Redis?

Yes. The LB can continue using affinity to optimize cache locality/connections, yet with **Redis shared sessions**, **login correctness must not depend on the callback always hitting one node**. This reduces disruption when a node fails. Ensure Redis and cookies still work when affinity breaks.

## 10. Choosing an Architecture Based on Requirements

| Context | Recommendation and Tradeoffs |
| --- | --- |
| **Learning, single-instance development** | **Local HttpSession** suffices; minimal moving parts. Do not treat it as HA. |
| **Two nodes, downtime may force users to re-login** | **Sticky + local sessions** can work, but verify cross-site POST cookies and plan node draining. |
| **Multiple nodes, rolling deploys, preserve logins when a node fails** | **Spring Session Redis/JDBC** is worth considering; correctness no longer relies on affinity if backend is stable. |
| **HA RDBMS already available, Redis not allowed** | Consider **Spring Session JDBC**, reviewing schema/transactions/cleanup and DB load. |
| **Multiple geographic regions, high network latency** | Analyze latency, consistency, cookie domains, failover, region-local data, idempotency, and routing policy; single-region Redis can bottleneck. |
| **Strict security, anti-login-CSRF** | Keep pending AuthnRequest bound to browser/session; avoid global lookup caches keyed only by RelayState. |
| **High session volume, high SLA** | Provision redundant shared stores, monitor metrics, test failovers, and size serialization/Redis IO costs. |

**Architecture takeaway:** if you need **true failover while keeping sessions alive**, sticky alone is insufficient. If SLAs allow re-login after node failure, sticky can reduce operational overhead. If active cross-node switching is needed, sharing HttpSession via **Spring Session** addresses the core bottleneck.

## 11. Pure Java 17: Simulating Sticky and Shared Sessions

The following program **runs standalone on JDK 17** without Spring, Redis, or an IdP. It models session ID **demo-s1** created on A. Keeping the session ID only in **A's local set** makes B unaware of it; a **shared set** models a common store visible to both nodes.

**SessionRoutingDemo.java**

~~~java
import java.util.HashSet;
import java.util.Set;

public class SessionRoutingDemo {
    public static void main(String[] args) {
        String sessionId = "demo-s1";

        Set<String> localA = new HashSet<>();
        Set<String> localB = new HashSet<>();
        Set<String> shared = new HashSet<>();

        localA.add(sessionId);
        shared.add(sessionId);

        System.out.println("local A before redirect: "
                + localA.contains(sessionId));
        System.out.println("local B on SAML callback: "
                + localB.contains(sessionId));
        System.out.println("shared store on B: "
                + shared.contains(sessionId));

        localA.clear(); // simulate A dying and losing local sessions

        System.out.println("sticky fallback to local B: "
                + localB.contains(sessionId));
        System.out.println("shared store after A failure: "
                + shared.contains(sessionId));

        shared.remove(sessionId); // simulate logout/invalidation

        System.out.println("shared store after logout: "
                + shared.contains(sessionId));
    }
}
~~~

Run:

~~~bash
javac SessionRoutingDemo.java
java SessionRoutingDemo
~~~

**Exact stdout:**

~~~text
local A before redirect: true
local B on SAML callback: false
shared store on B: true
sticky fallback to local B: false
shared store after A failure: true
shared store after logout: false
~~~

Interpretation:

- **local A before redirect=true**: requests on A see the created session.
- **local B on SAML callback=false**: B is unaware of A's local session.
- **shared store on B=true**: with a shared session backend, B resolves the same ID.
- **sticky fallback to local B=false**: when A is lost, sticky routing cannot restore local state.
- **shared store after A failure=true**: shared state does not depend on A's memory in the simulation.
- **shared store after logout=false**: invalidation in the shared backend removes the session ID from all nodes' view.

**Limitations:** a HashSet simulation lacks TLS, cookies, Redis, serialization, AuthnRequests, and SAML signatures. It **does not prove a real SAMLResponse is valid**. Production deployments must validate browser cookies, registrationId, IdP trust, and SAML conditions.

## 12. End-to-End Test Matrix

Use an **IdP sandbox** with trusted metadata/certs and an HTTPS front door. Never use unsigned fake SAMLResponses to draw conclusions about session health.

| # | Scenario | Expectation / What to Verify |
| --- | --- | --- |
| 1 | Normal login, GET and ACS POST hit same node A | SSO succeeds if SAML and cookies are valid. |
| 2 | AuthnRequest created on A, ACS callback hits B, local-only HttpSession | Request/correlation is lost and login fails. |
| 3 | AuthnRequest created on A, ACS hits B, Redis shared session | Succeeds when session cookie matches and serialization is healthy. |
| 4 | Redis shared session, log in on A, next `/me` request hits B | B sees the authenticated SecurityContext. |
| 5 | Sticky local-only, log in on A then A dies | B lacks A's session; user must re-login. |
| 6 | Redis shared session, log in on A then A dies | B continues seamlessly if Redis/keys/cookies/versions remain valid. |
| 7 | SameSite=Lax, cross-site POST omits session cookie | Pending AuthnRequest is lost regardless of local or Redis; fix cookie policy. |
| 8 | SP session cookie None/Secure is right, LB affinity cookie blocked | Sticky fails to stick; Redis shared store can still succeed. |
| 9 | SESSION cookie expires during long IdP MFA | Session/request missing; never disable InResponseTo just to force login through. |
| 10 | Redis connection drops while saving AuthnRequest | Do not proceed as if saved; fail closed cleanly. |
| 11 | Redis unreachable when reading callback | Do not construct an authenticated session from missing state; fail safely. |
| 12 | Redis evicts session before timeout | State lost; fix capacity/eviction policy. |
| 13 | A/B run different SecurityContext serialization versions | B fails to read session; test rolling upgrades and serializers. |
| 14 | A/B use different Redis namespaces | Sessions are not shared; same Redis host alone is not enough. |
| 15 | A/B emit different public SP entityID/ACS due to bad forwarded headers | IdP or SP rejects destination/recipient/audience mismatch. |
| 16 | LB forwards wrong Content-Type/form fields on ACS POST | Spring fails to parse a valid SAMLResponse. |
| 17 | Logout at A after logging in at B with Redis shared session | SP session invalidated for all nodes; do not assume IdP logout. |
| 18 | Browser replays SAMLResponse after request was consumed | Must not create a new session; enforce anti-replay/correlation. |
| 19 | Two tabs log in simultaneously, repository holds only one pending request | One callback may fail; test multi-tab/concurrent requests. |
| 20 | Sticky affinity expires between IdP redirect and callback | Fails if local-only; shared stores should not depend on affinity. |
| 21 | Rolling update A old / B new with shared Redis | Verify session serialization compatibility before rollout. |
| 22 | Redis Sentinel/Cluster failover while users are logged in | Check session loss/latency/reconnection per HA policy. |
| 23 | Node B fails health check while browser POSTs callback | LB picks a healthy backend; session continuity depends on store. |
| 24 | Browser switches networks/IPs between SP GET and ACS POST | IP-hash affinity breaks; shared session works regardless of IP if cookie is valid. |

Tests must **observe which node handles each request** (nodeId/trace ID), whether the session cookie is sent, whether Redis holds the record, whether SAML request correlation matches, and whether the Identity Provider signs/responds properly. Seeing a single login screen succeed once is insufficient.

### Quick Browser Verification Steps

1. Before login, hit **GET /node** several times to confirm LB distribution, or inspect LB request logs by trace ID.
2. Visit **/saml2/authenticate/corp**, recording which node issued AuthnRequest via redacted logs and timestamp.
3. After IdP MFA, check **POST /login/saml2/sso/corp** for which cookies are sent and which node handles it.
4. After login, call **/me** repeatedly under varying LB conditions.
5. Remove the serving node from the pool and call `/me` again; session must remain valid with a shared store, or require re-login per policy under local sticky.
6. Log out/invalidate the SP session and verify every node rejects the old session.
7. Repeat under timeouts, Redis restarts, and rolling deploys; document outcomes and acceptable downtime.

## 13. Quick Troubleshooting Table

| Symptom | Possible Cause | Inspection & Fix |
| --- | --- | --- |
| Intermittent login failures across 2 instances | AuthnRequest lives only on node A, callback hits B | Check LB routing for init/ACS; configure sticky or Spring Session shared store. |
| Callback loses InResponseTo despite Redis holding data | Browser omitted SESSION cookie or wrong session ID | Check SameSite/Secure/Domain/Path, redirect hostname, and cookie rotation. |
| Login succeeds yet next request prompts again | Other node cannot see SecurityContext or serialization failed | Check Spring Session filter/repository, Redis keyspace, and versions. |
| Sticky sessions lose logins during deploys | Sticky node was killed; local sessions were not migrated | Use a shared store or accept re-login/draining. |
| Redis present yet B cannot read A's session | Different namespace, DB, credentials, serializer, or TTL | Compare exact Redis/namespace/serializer configs on both nodes. |
| Redis error disrupts all SP authentication | Shared store is a single point of failure | Enable HA, monitoring, readiness checks, and fail-closed policy. |
| Callback returns to the right node yet loses request | HttpSession expired or cookie was blocked | Check cookies and TTLs instead of immediately blaming the LB. |
| SAMLResponse signature invalid | IdP verification certificate/metadata mismatch | Fix trust/rotation; never disable signature validation. |
| ACS shows `http://internal:8080` | Wrong proxy scheme/host headers | Configure external baseUrl/forwarded headers from trusted proxies. |
| `/node` succeeds while `/me` fails | Node process is healthy yet Redis/SAML dependencies are broken | Implement deeper readiness checks and layered logging. |
| Session exists in Redis yet user is logged out | Authentication/serializer/expiry/rotation/security policy mismatch | Inspect SecurityContext state and session policies. |
| IdP auto-logs back in after local logout | IdP SSO session remains alive | Implement SAML Single Logout if needed; distinguish session scopes. |
| Same account gets multiple sessions across tabs | Request repository/parallel login or business logic | Check correlation and session semantics; never disable CSRF. |

**Safe logging suggestion:**

~~~text
event=saml_request_saved node=sp-a registration=corp trace=t-001
event=saml_response_received node=sp-b registration=corp trace=t-001
event=session_store_read node=sp-b result=found
event=saml_authentication_result result=success
~~~

This is an **example log structure** (fictional trace), not automatic Spring output. Avoid logging **full session IDs, cookies, SAMLResponse, Assertions, NameIDs, private signing keys, or Redis passwords**. Trace IDs must not let anyone guess or read sessions.

## 14. Common Mistakes

1. **"Sticky sessions are distributed sessions."** No; sticky routing only picks a node and does not share HttpSession.
2. **"With Redis, cookies aren't needed."** False; the browser still must send the session identifier so nodes locate the right session.
3. **"Session cookie None is enough for sticky."** Not necessarily; the LB may use its own affinity cookie blocked by SameSite.
4. **"If AuthnRequest is lost, skip InResponseTo."** Dangerous; weakens login CSRF and replay defenses.
5. **"Use RelayState as the session ID."** False; RelayState is not inherently a trusted browser-bound identifier.
6. **"Redis makes the app stateless."** False; it only moves state outside the SP process.
7. **"Node failover with sticky keeps sessions alive."** Not when local sessions are unreplicated.
8. **"Spring Boot 3.3 uses the exact same Spring Session starter as Boot 4."** Not necessarily; use dependencies matching your BOM/version.
9. **"Different SP entityID/ACS on A and B won't hurt."** False; the IdP and SAML validators can reject them.
10. **"Redis TTL = Assertion lifetime = IdP SSO timeout."** False; they are independent clocks and lifecycles.
11. **"Shared Redis guarantees every session object is readable across any versions."** False; serialization schemas must stay compatible.
12. **"Logging out of the SP always logs out the IdP too."** False; local logout and SAML Single Logout are distinct.
13. **"If the node is healthy, Redis is healthy."** False; monitor store readiness separately.
14. **"Can disable Secure cookies so HTTP tests pass."** Never extrapolate that to production; test with a real HTTPS sandbox.
15. **"Any open Redis cache can store SecurityContext."** Dangerous; session stores require access controls and network isolation.
16. **"Sticky cookies or session IDs aren't secrets."** False; session identifiers and affinity tokens must be protected from leaks and fixation.
17. **"Adding `@EnableRedisHttpSession` alongside Boot auto-config has no side effects."** It can alter auto-config behavior and requires testing.
18. **"If node B can read SAMLResponse, skip signature/audience checks."** False; shared sessions only restore state and do not replace protocol validation.

## 15. Production Checklist

**Architecture and operations**

- [ ] Distinguished local/sticky/shared sessions according to SLA and failure budgets.
- [ ] If multi-node session failover is required, deployed a real shared store with an HA backend.
- [ ] Nodes run compatible app versions/serializers, with uniform registration/trust/namespaces.
- [ ] All nodes serve the **same SP public entityID and HTTPS ACS** per IdP agreement.
- [ ] Redis/JDBC has network policies, TLS/auth, TTLs, capacity planning, and backups/recovery as needed.
- [ ] Observability covers the request store, session reads/writes, backend availability, and SAML errors.
- [ ] Tested rolling deploys, scale-downs, node kills, and Redis failovers.

**Cookies, browsers, and SAML**

- [ ] Tested POST ACS from the IdP in real browsers; session cookies are sent and valid.
- [ ] If using sticky sessions, verified the affinity cookie separately during cross-site POSTs.
- [ ] Cookies have proper Secure/HttpOnly/Domain/Path/SameSite attributes; real HTTPS at the edge.
- [ ] Forwarded headers come solely from trusted proxies; Spring never emits internal ACS URLs.
- [ ] Pending AuthnRequests remain bound to browser/session; avoid global lookups keyed solely by RelayState.
- [ ] Preserved InResponseTo, issuer, signature, audience, destination, recipient, time, and replay checks.
- [ ] Local logout/invalidation takes effect across all SP nodes; SLO is designed separately if required.
- [ ] Raw sessions/cookies/Assertions are never logged; monitoring uses anonymized traces.

## 16. Review Questions

**Q1.** The LB always sends the browser to A, yet A crashes. With sticky + local HttpSession, does B continue the session seamlessly?  
**Answer:** **No**, unless separate session replication/migration exists. Sticky preserves routing only, not session data transfer.

**Q2.** Using Spring Session Redis, AuthnRequest is created on A and SAMLResponse POSTs to B. Can login complete?  
**Answer:** **Yes, it can**, provided the same session cookie/Redis record is used, the request was saved and readable, the session has not expired, serialized state is compatible, and SAMLResponse passes all security checks.

**Q3.** Redis holds the right session yet the SAML POST callback omits the SP cookie. Should you fix Redis or the cookie?  
**Answer:** First inspect **SameSite/Secure/Domain/Path** and the external HTTPS URL. Without the right session ID, B cannot look up the Redis record.

**Q4.** Does `SameSite=None` on the SESSION cookie guarantee a sticky LB always routes back to A?  
**Answer:** **No**. The LB may use its own affinity cookie or IP hashing; inspect each mechanism individually.

**Q5.** Can you drop `HttpSessionSaml2AuthenticationRequestRepository` and look up AuthnRequest by RelayState in Redis?  
**Answer:** A custom repository can be designed, yet it is **not secure by default**; you must enforce browser/session binding, one-time use, TTL, anti-login-CSRF, and anti-replay.

**Q6.** Does Spring Session Redis require `@EnableRedisHttpSession` when Spring Boot 3.3 auto-configures the right dependencies?  
**Answer:** **Not required**; Boot provides auto-configuration. Add the annotation manually only when explicit control is needed and its effects are understood.

**Q7.** Both A and B share Redis, yet after logging in on A, `/me` on B fails to deserialize SecurityContext. Why?  
**Answer:** Object/class/serializer/schema versions may be incompatible, dependencies missing, or session attributes non-serializable; inspect, align, and test rolling upgrades.

**Q8.** A user logs out of the SP via node A, while the IdP keeps its SSO session. Does that prove Redis is broken?  
**Answer:** **No**. SP local logout and the IdP SSO session are separate scopes; SAML SLO must be implemented separately for cross-app logout.

## 17. References

1. [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) — default HttpSessionSaml2AuthenticationRequestRepository, custom repositories, storing requests in sessions, and login fixation risks when looking up cache solely by RelayState.
2. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — AuthnRequest/Response filter chain, RelyingPartyRegistration, ACS, SAML sessions, and verification.
3. [Spring Boot 3.3 — Spring Session](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html) — Redis/JDBC auto-configuration, session timeouts, and HttpSession replacement.
4. [Spring Boot 3.3 — SameSite Cookies](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html#web.servlet.embedded-container.customizing.samesite) — `server.servlet.session.cookie.same-site` property and interaction with Spring Session.
5. [Spring Boot 3.3 — Redis](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html#data.nosql.redis) — `spring-boot-starter-data-redis`, connection configuration, and `RedisConnectionFactory`.
6. [Spring Session — Spring Boot with Redis](https://docs.spring.io/spring-session/reference/3.1/guides/boot-redis.html) — using Spring Session Redis with Boot 3.x generation.
7. [Spring Session — Configuring Redis](https://docs.spring.io/spring-session/reference/3.3/configuration/redis.html) — namespaces, flush/save modes, session serialization, and indexing/expiry.
8. [OASIS — SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf) — Web Browser SSO, AuthnRequest/Response correlation, and browser binding.

**Conclusion:** **Sticky sessions keep requests on the same node but do not survive node failures**. **Spring Session Redis/JDBC truly shares HttpSession**, letting nodes serve the same browser session and pending SAML AuthnRequests when **cookies, serialization, SAML trust, public ACS, and repositories** all align. Choose based on SLA and operations; whichever approach you take, never sacrifice **InResponseTo, signatures, issuer, audience, or anti-login-CSRF** to work around routing bugs.

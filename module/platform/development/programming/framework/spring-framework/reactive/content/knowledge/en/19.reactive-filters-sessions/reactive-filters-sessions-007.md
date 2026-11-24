# WebSession, WebSessionManager, and When Sessions Are Saved in Spring WebFlux

## 1. What Problem Does WebSession Solve?

In Spring WebFlux, `WebSession` is the abstraction of a **server-side working session**, allowing a user's attributes to be kept across multiple HTTP requests. Examples: temporary shopping cart state, the current step of a multi-screen workflow, UI choices, or a short-term reference code.

Unlike a cookie that holds all data itself, a session usually works on this model:

- The server stores session data in a storage backend.
- The client holds a **session ID** so the server can find the session again on the next request.
- The server uses the session ID to retrieve the `WebSession`, read/write attributes, and update session state.

The default cookie of `CookieWebSessionIdResolver` is named `SESSION`; the cookie contains the session identifier, not the entire attributes map. Session data remains in the server-side store.

In WebFlux, the session API is designed to be reactive. `ServerWebExchange.getSession()` returns `Mono<WebSession>`, so a controller or filter can combine reading/writing the session with other publishers without calling `block()`.

**The most important point of this lesson:** getting a `WebSession` object **does not mean the session has been created and its ID sent to the client**. A session is marked started only when `start()` is called or when an attribute is added. Saving the session is usually performed automatically by the framework right before the response is committed.

## 2. WebSession, WebSessionManager, WebSessionIdResolver, and WebSessionStore

The four components have different responsibilities:

| Component | Responsibility |
| --- | --- |
| `WebSession` | API to operate on the ID, attributes, access times, idle timeout, start, save, invalidate, and ID change |
| `WebSessionManager` | Gets the session matching the current HTTP request; finds the session by client-sent ID or creates a new instance |
| `WebSessionIdResolver` | Reads the session ID from the request and sends/expires the ID in the response, usually via cookie or header |
| `WebSessionStore` | Strategy to create, retrieve, update last-access time, and remove sessions in storage |

General flow:

~~~text
HTTP request
   |
   | Cookie SESSION=<opaque-id> or session ID header
   v
WebSessionIdResolver
   | resolveSessionIds(exchange)
   v
WebSessionManager
   | getSession(exchange)
   v
WebSessionStore
   | retrieveSession(id) or createWebSession()
   v
WebSession
   | getAttribute / getAttributes / put / invalidate
   v
WebFlux runs handler and creates response
   |
   | right before response commit
   v
WebSession.save()
   | persist or remove according to state
   v
WebSessionIdResolver updates/expires session ID in response
~~~

In WebFlux infrastructure, the bean named `webSessionManager` is what provides the session for `ServerWebExchange`. Under the default configuration, that is `DefaultWebSessionManager`. This manager combines a resolver to handle session IDs and a store to manage session data.

## 3. Getting a Session Does Not Automatically Start the Session

The usual approach in a controller or WebFilter is:

~~~java
Mono<WebSession> session = exchange.getSession();
~~~

`ServerWebExchange.getSession()` always returns a `WebSession` corresponding to the session ID the client sent, or a new instance if the client sent no ID or the old session has expired. However, calling `getSession()` **does not automatically start the session**.

When a new instance is not yet started:

- `session.isStarted()` returns `false`.
- There is no need to send a session ID to the client yet.
- `save()` will not create a new session if `start()` has not been called or no attribute has been added.

There are two ways to actively start it:

### Approach 1: Add a Session Attribute

~~~java
return exchange.getSession().map(session -> {
    session.getAttributes().put("theme", "dark");
    return "Session attribute added";
});
~~~

Adding an attribute **implicitly starts** the session. This is the most common approach because the application only creates a session when there is actually data to store.

### Approach 2: Call start() Explicitly

~~~java
return exchange.getSession().map(session -> {
    session.start();
    return "Session explicitly started";
});
~~~

Use this when a session is needed even without attributes yet. For example, a flow needs to issue a session ID before the user goes through subsequent steps.

You should not call `start()` on every request if the endpoint does not actually need a session. Unnecessary session creation increases the number of server-side sessions and issues cookies to clients even when there is no state to keep.

## 4. Main Operations on WebSession

`WebSession` provides commonly used APIs:

| API | Meaning |
| --- | --- |
| `getId()` | Get the current session ID |
| `getAttributes()` | Get the readable/writable attributes map |
| `getAttribute(name)` | Get an attribute; returns null if absent |
| `getAttributeOrDefault(name, defaultValue)` | Get an attribute or a default value |
| `getRequiredAttribute(name)` | Get a required attribute; throws an error if missing |
| `start()` | Mark the session as started |
| `isStarted()` | Check whether the session has started |
| `save()` | Save via WebSessionStore; the framework calls this automatically before response commit |
| `invalidate()` | Invalidate the current session and remove the session from storage |
| `changeSessionId()` | Generate a new ID and update storage |
| `getCreationTime()` | The time the session was created |
| `getLastAccessTime()` | The most recent access time |
| `getMaxIdleTime()` | The maximum idle duration |
| `setMaxIdleTime(duration)` | Set the maximum idle duration |
| `isExpired()` | Check whether the session has expired |

Example of reading and updating an attribute:

~~~java
return exchange.getSession().map(session -> {
    String theme = session.getAttributeOrDefault("theme", "light");
    session.getAttributes().put("theme", "dark");
    return theme;
});
~~~

`getAttributes()` returns the session's map. Modifying the map marks the session as started when adding a new attribute. If only reading the session or only getting the ID, a new session is not necessarily created.

Do not store large data, files, streams, complex entity graphs, or objects that cannot be serialized/restored reliably in the session. Only keep small state needed to identify and continue the flow.

## 5. When the Session Is Saved: Before the Response Commits

This is the most easily misunderstood part.

`WebSession.save()` returns `Mono<Void>`, but the Spring API explicitly states this method **is not meant for applications to call directly**. The framework automatically calls save **right before the response is committed**.

Flow:

1. The handler gets the `WebSession`.
2. The handler reads or modifies attributes.
3. The handler returns the response `Mono`/`Flux`.
4. As the response prepares to commit, WebFlux saves the session if needed.
5. The resolver sends the session ID or handles expiring the ID in the response.

Therefore, the following is sufficient:

~~~java
@GetMapping("/theme")
public Mono<String> changeTheme(ServerWebExchange exchange) {
    return exchange.getSession().map(session -> {
        session.getAttributes().put("theme", "dark");
        return "Theme saved";
    });
}
~~~

There is no need for:

~~~java
// Do not call save() directly in the controller.
return exchange.getSession()
    .flatMap(session -> {
        session.getAttributes().put("theme", "dark");
        return session.save().thenReturn("saved");
    });
~~~

Calling `save()` yourself can tangle the lifecycle and is unnecessary in a normal WebFlux flow. Let the framework manage persisting and sending the session ID.

**Update the session before the response commits.** With streaming responses, the response may commit as soon as body writing begins; do not rely on modifying the session after the stream has started to update the cookie or session state for the current response.

If the session is not started yet, `save()` has no effect of creating a new session. If the session was retrieved from the store but later invalidated, the save operation may report an error according to the implementation's contract.

## 6. How Does WebSessionManager.getSession() Work?

`WebSessionManager` is the low-level abstraction for retrieving a session for a `ServerWebExchange`:

~~~java
Mono<WebSession> getSession(ServerWebExchange exchange);
~~~

The contract guarantees returning one of two cases:

- The session corresponding to the ID the client sent in the request, if the session is still valid.
- A new session instance if the client did not send an ID or the old session has expired.

A typical application should use:

~~~java
exchange.getSession()
~~~

This is the convenient API already provided by `ServerWebExchange`. Only interact directly with `WebSessionManager` when writing custom infrastructure, integrating another session manager, or building low-level components.

Example of using the manager directly in an infrastructure component:

~~~java
// Illustrative code; manager is injected from ApplicationContext.
Mono<WebSession> current =
    webSessionManager.getSession(exchange);
~~~

There is no need to inject the manager into every controller just to read an attribute. Using `exchange.getSession()` keeps the code aligned with standard WebFlux APIs.

## 7. WebSessionIdResolver: Cookie or Header?

`WebSessionIdResolver` determines how the client sends the session ID and how the server returns the ID to the client. Two common implementations:

| Resolver | How the ID is carried | Use case |
| --- | --- | --- |
| `CookieWebSessionIdResolver` | Cookie in request/response | Browsers and web applications |
| `HeaderWebSessionIdResolver` | HTTP header | API clients intentionally managing the session ID via headers |

`DefaultWebSessionManager` uses `CookieWebSessionIdResolver` by default. The default cookie name is `SESSION`.

### CookieWebSessionIdResolver

Cookies are convenient for browsers because the browser automatically sends the matching cookie by domain/path. You can change the cookie name and configure cookie attributes with the resolver.

Example of customizing the cookie name and some attributes:

~~~java
@Bean
WebSessionManager webSessionManager() {
    DefaultWebSessionManager manager = new DefaultWebSessionManager();

    CookieWebSessionIdResolver resolver =
        new CookieWebSessionIdResolver();

    resolver.setCookieName("APPSESSION");
    resolver.addCookieInitializer(cookie -> cookie
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax"));

    manager.setSessionIdResolver(resolver);
    return manager;
}
~~~

This is optional infrastructure configuration; it does not need to be added to the default demo. When using `secure(true)`, the client only sends the cookie over HTTPS; production environments need HTTPS configured properly.

### HeaderWebSessionIdResolver

A header-based resolver can suit API clients that do not rely on browser cookies:

~~~java
HeaderWebSessionIdResolver resolver =
    new HeaderWebSessionIdResolver();

resolver.setHeaderName("X-SESSION-ID");
~~~

The client must send this header back in subsequent requests. A session ID header is still a sensitive credential; do not log its value, do not put it in URLs, and protect it with TLS.

Whether using a cookie or a header, the resolver only transports the ID. Identity authentication and permission checks still belong to Spring Security or the application's authorization layer.

## 8. WebSessionStore and Default Storage

`WebSessionStore` defines the session persistence strategy:

| Method | Responsibility |
| --- | --- |
| `createWebSession()` | Create a new WebSession instance |
| `retrieveSession(id)` | Find a session by ID; check expiry and update last access time |
| `updateLastAccessTime(session)` | Update the most recent access timestamp |
| `removeSession(id)` | Remove the session from storage |

`DefaultWebSessionManager` uses `InMemoryWebSessionStore` by default. This store is a map-based implementation that stores sessions in the process's memory.

Advantages of the in-memory store:

- Does not require a database or Redis to run a demo.
- Simple for single-instance applications and development environments.
- Easy to test the session lifecycle.

Limitations:

- Sessions reside in the memory of a single application instance.
- Process restarts can lose all sessions.
- Multiple nodes do not automatically share the same session store.
- If a load balancer routes a request to another node, that node may not find the session.

Therefore, applications running multiple instances or needing sessions to survive restarts should use a shared store such as Spring Session with Redis, instead of relying on an in-memory map.

## 9. Integrating Spring Session with Redis

Spring Session can replace the underlying `WebSession` implementation without forcing controllers to change how they call `exchange.getSession()`. The WebFlux integration uses a `WebSessionManager` backed by `ReactiveSessionRepository`.

Conceptual configuration example:

~~~java
@Configuration
@EnableRedisWebSession
public class SessionConfiguration {
}
~~~

You need to add the Spring Session Data Redis dependency compatible with the project's Spring Boot/Spring Framework and configure a reactive Redis connection factory. In Spring Boot, you can configure the Redis host, port, and credentials through application properties.

`@EnableRedisWebSession` registers a `webSessionManager` bean using a Redis-backed implementation. From the controller's perspective, usage stays the same:

~~~java
return exchange.getSession()
    .map(session -> {
        session.getAttributes().put("cartCount", 3);
        return "updated";
    });
~~~

The difference lies in where the session is persisted. Spring Session handles the integration with `ReactiveSessionRepository`; the application does not need to write its own Redis `WebSessionStore` if it uses the provided support module.

In a cluster, you need to configure Redis availability, timeouts, serialization, expiry, network security, and monitor session-saving errors. A centralized session store lets multiple nodes share sessions, but also becomes an important dependency of the request.

## 10. Idle Timeout and Expiration

`WebSession` has time-related properties:

- `getCreationTime()`: when the session was created.
- `getLastAccessTime()`: the most recent access time.
- `getMaxIdleTime()`: the maximum allowed inactive duration.
- `setMaxIdleTime(Duration)`: change the idle timeout.
- `isExpired()`: check the expiration state.

Example of setting a 20-minute idle timeout:

~~~java
return exchange.getSession().map(session -> {
    session.setMaxIdleTime(Duration.ofMinutes(20));
    session.getAttributes().put("userPreference", "compact");
    return "updated";
});
~~~

A session can expire when the time since last access exceeds max idle time. The store needs to check expiration on retrieval; an expired session is discarded and the next request receives a new session.

A negative `Duration` value indicates the session does not expire by idle timeout. You should not use non-expiring sessions without a clear cleanup and security policy.

**Cookie Max-Age and session maxIdleTime are two different concepts:**

- Cookie Max-Age controls how long the browser keeps the session ID cookie.
- `WebSession.maxIdleTime` controls how long the server allows the session to be inactive.

A browser can still send an old cookie after the server-side session has expired; the server will not restore old data just because the cookie still exists.

## 11. Deleting Sessions, Logout, and Changing Session IDs

### invalidate()

`invalidate()` cancels the current session and deletes session storage:

~~~java
@PostMapping("/logout")
public Mono<ResponseEntity<Void>> logout(ServerWebExchange exchange) {
    return exchange.getSession()
        .flatMap(WebSession::invalidate)
        .thenReturn(ResponseEntity.<Void>noContent().build());
}
~~~

This is an example inside a controller. Because `invalidate()` returns `Mono<Void>`, you must compose the publisher so the response is only created after the invalidation operation completes. Do not call `subscribe()` inside the controller.

After logout, the old session is no longer used. The session ID cookie is handled by the resolver/framework according to the invalidation lifecycle; the client should not keep using the old ID.

### changeSessionId()

`changeSessionId()` generates a new ID and updates storage:

~~~java
return exchange.getSession()
    .flatMap(WebSession::changeSessionId);
~~~

This is a reactive operation returning `Mono<Void>`. Use it when you need to change the session ID while keeping the session state, such as after a change in trust level or access rights.

An important case is **session fixation**: after a user logs in or privileges change, you must ensure the session ID does not remain an ID an attacker might have known beforehand. Spring Security provides session fixation protection; you should use the framework's security configuration instead of implementing the entire flow yourself.

### Removing One Attribute

If you only need to remove part of the state:

~~~java
return exchange.getSession().map(session -> {
    session.getAttributes().remove("temporaryCheckout");
    return "temporary data removed";
});
~~~

There is no need to invalidate the entire session if you only want to remove one temporary attribute.

## 12. Distinguishing WebSession from @SessionAttribute and @SessionAttributes

Spring WebFlux provides additional annotations supporting controllers:

| Mechanism | Purpose |
| --- | --- |
| `WebSession` | Direct API to read, write, invalidate, or change the session ID |
| `@SessionAttribute` | Read an existing attribute managed outside the controller |
| `@SessionAttributes` | Store a controller's model attributes in WebSession across multiple requests |
| `SessionStatus.setComplete()` | Mark a workflow complete and clear model attributes managed by `@SessionAttributes` |

Example of reading an existing attribute:

~~~java
@GetMapping("/profile")
public Mono<String> profile(
        @SessionAttribute(name = "displayName", required = false)
        String displayName) {
    return Mono.just(
        displayName == null ? "Guest" : displayName
    );
}
~~~

`@SessionAttribute` is suitable when the attribute has already been created by a filter, security, or another component. If the controller needs to add/remove attributes itself, use `WebSession` directly.

`@SessionAttributes` is suitable for controller workflows, such as keeping a multi-step form. This is a controller-scoped model attribute mechanism, different from directly accessing the entire session map.

## 13. Complete Java 17+ Example with Spring Boot WebFlux

The example builds a simple session counter:

- `GET /api/session`: reads the session, increments the visit count, and returns JSON.
- `POST /api/session/logout`: invalidates the session and returns 204.
- Uses cURL's cookie jar to send back the session ID across multiple requests.

Structure:

~~~text
websession-demo/
├── pom.xml
└── src/main/java/com/example/websession/
    ├── WebSessionApplication.java
    └── SessionController.java
~~~

File `pom.xml` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>websession-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

File `src/main/java/com/example/websession/WebSessionApplication.java`:

~~~java
package com.example.websession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSessionApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/websession/SessionController.java`:

~~~java
package com.example.websession;

import java.time.Duration;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;
import org.springframework.web.server.WebSession;

@RestController
@RequestMapping("/api/session")
public class SessionController {

    public record SessionView(
        int visits,
        boolean started,
        long maxIdleSeconds
    ) {}

    @GetMapping
    public Mono<SessionView> visit(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            Integer previous = session.getAttribute("visits");
            int visits = previous == null ? 1 : previous + 1;

            session.getAttributes().put("visits", visits);
            session.setMaxIdleTime(Duration.ofMinutes(20));

            return new SessionView(
                visits,
                session.isStarted(),
                session.getMaxIdleTime().toSeconds()
            );
        });
    }

    @PostMapping("/logout")
    public Mono<ResponseEntity<Void>> logout(
            ServerWebExchange exchange) {
        return exchange.getSession()
            .flatMap(WebSession::invalidate)
            .thenReturn(ResponseEntity.<Void>noContent().build());
    }
}
~~~

Run from the `websession-demo` directory with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

### First Request

~~~bash
curl -i -c session.cookies -b session.cookies http://localhost:8080/api/session
~~~

Expected JSON body:

~~~json
{"visits":1,"started":true,"maxIdleSeconds":1200}
~~~

The first response will include the session ID cookie if the session was started and saved successfully. With the default resolver, the cookie name is `SESSION`; the ID value is opaque and changes per run.

### Next Request with the Same Cookie

~~~bash
curl -i -c session.cookies -b session.cookies http://localhost:8080/api/session
~~~

Expected JSON body:

~~~json
{"visits":2,"started":true,"maxIdleSeconds":1200}
~~~

The client sends back the cookie, the server finds the old session, and increments the counter from 1 to 2. Without a cookie jar, each request can receive a new session and the counter starts over.

### Logout

~~~bash
curl -i -X POST -b session.cookies -c session.cookies http://localhost:8080/api/session/logout
~~~

Main result:

~~~http
HTTP/1.1 204 No Content
~~~

After logout, the next GET request will use a new session and the counter starts over from 1.

The demo uses the default in-memory store, so it is suitable for learning and running locally. It does not provide session persistence across restarts or sharing across multiple nodes.

## 14. Race Condition When Multiple Requests Share One Session

One session can be used by multiple concurrent requests, for example a browser opening multiple tabs or a client sending parallel requests with the same cookie.

The read-modify-write snippet:

~~~java
Integer old = session.getAttribute("visits");
int next = old == null ? 1 : old + 1;
session.getAttributes().put("visits", next);
~~~

is not an atomic increment across multiple requests. Two requests can both read the value 5, both calculate 6, and both write 6; one increment is lost.

You should not assume the entire `WebSession` or objects inside attributes are thread-safe. For data needing consistency:

- Use atomic operations at Redis/database or a store that supports controlled updates.
- Design operations to be idempotent if the client can retry.
- Avoid keeping large mutable objects modified concurrently by multiple requests.
- Do not treat the session as a place to store business data needing strong transactions.

A session suits short-term state serving the request experience; it does not replace a database as the primary data source.

## 15. Session Security and Operations

The session ID is a bearer credential: anyone holding a valid ID can be recognized as the session owner according to application policy. Both the ID and the session data need protection.

### Cookie and Transport

- Use HTTPS in production.
- Enable `Secure` so browsers send the cookie only over HTTPS.
- Enable `HttpOnly` so browser-side JavaScript cannot read the cookie.
- Choose `SameSite` suitable for navigation flows and cross-site integrations.
- Configure Domain/Path as narrowly as possible.
- Do not put the session ID in URLs or query strings.

`SameSite` does not completely replace CSRF protection. With cookies sent automatically by the browser, you need to enable appropriate CSRF protection for state-changing requests.

### Session Fixation and Logout

- Use Spring Security session fixation protection during authentication.
- Change the session ID after privileges/authentication state change per policy.
- Invalidate the session on logout or when the session needs to end.
- Do not log session IDs, cookie values, or sensitive attributes.
- Do not trust session data as proof of authorization if it was not established from a trusted source.

### Data Stored in the Session

- Store only small and necessary data.
- Avoid storing passwords, long-lived access tokens, payment card info, or unnecessary secrets.
- Define serialization if using an out-of-process store.
- Design versioning for session data if multiple application versions read/write concurrently.
- Have an expiry and cleanup policy to prevent sessions from living longer than needed.

### Operations

Monitor active session count, session expiration rate, store read/write errors, latency when fetching sessions, and payload size. If Redis/store fails, requests must handle the error per policy; do not silently turn every persistence error into a new session if that can lose state or bypass security requirements.

## 16. Common Mistakes

1. **Calling `exchange.getSession()` and thinking the cookie was already sent:** wrong. Simply getting the instance does not start the session; `start()` or adding an attribute is needed.
2. **Calling `session.save()` manually in a controller:** unnecessary in a normal flow; the framework saves automatically before response commit.
3. **Modifying the session after the response has committed:** it may be too late to persist changes or update the cookie for the current response.
4. **Calling `block()` on `Mono<WebSession>`:** blocks the event loop. Compose with `map`/`flatMap` and return the publisher.
5. **Calling `subscribe()` manually to save the session:** creates a subscription detached from the HTTP lifecycle. Return the publisher to WebFlux.
6. **Creating a session on every request even with no state:** increases session count and issues unnecessary cookies.
7. **Confusing cookie Max-Age with server idle timeout:** one is the browser keeping the cookie, the other is the server expiring the session.
8. **Using the in-memory store for a cluster without a sharing strategy:** other nodes do not see sessions created in this process.
9. **Storing large or non-serializable objects:** increases memory, latency, or causes errors when using a distributed store.
10. **Treating session attributes as thread-safe:** parallel requests can overwrite data; read-modify-write is not automatically atomic.
11. **Not invalidating on logout:** the old session can continue to be used if the ID is still valid.
12. **Not changing the session ID after authentication:** can create session fixation risk; use Spring Security protection.
13. **Logging the session ID:** turns logs into a store of credentials that can be reused.
14. **Using cookie sessions while ignoring CSRF:** browsers automatically send cookies, so state-changing requests need protection.
15. **Putting the session ID in the URL:** the ID can leak via browser history, referrer, analytics, and access logs.
16. **Using the session as the source of business data:** sessions are short-lived and can expire or be lost when stores change; important data needs a database.
17. **Assuming WebSessionManager is where all attributes live:** the manager coordinates obtaining the session; the store is the persistence strategy.
18. **Implementing a custom resolver/store while skipping expiry checks:** expired sessions may be reused or last access time not updated properly.

## 17. Session Design Checklist

Before using sessions, determine:

- Is it truly necessary to keep state across multiple HTTP requests?
- What data is stored? Is it sensitive or too large?
- When does the session start: adding an attribute or calling `start()`?
- Do session modifications occur before the response commits?
- Are idle timeout and cookie lifetime appropriate?
- Is the store in-memory, Redis, or another persistence backend?
- Does the application run on a single node or multiple nodes?
- Does the cookie have appropriate Secure, HttpOnly, SameSite, and HTTPS settings?
- How is CSRF handled if the browser sends cookies automatically?
- How are login/logout and session fixation protected?
- Can parallel requests update the same attribute?
- Have expiry, invalidation, session ID rotation, and store failure been tested?

## 18. Self-Check Questions

**1.** What is `WebSession`? A server-side API for keeping session attributes across multiple HTTP requests.

**2.** What type does `ServerWebExchange.getSession()` return? `Mono<WebSession>`.

**3.** Does calling `getSession()` automatically start the session? No. It returns the matching session or a new instance; `start()` or adding an attribute is needed to start it.

**4.** What is the responsibility of `WebSessionManager`? To find the session by the client-sent ID or provide a new session for the exchange.

**5.** What does `WebSessionIdResolver` do? Reads the session ID from the request and sends/expires the ID in the response.

**6.** What does `WebSessionStore` do? Creates, retrieves, updates last access time, and removes sessions.

**7.** Which resolver/store does `DefaultWebSessionManager` use by default? `CookieWebSessionIdResolver` and `InMemoryWebSessionStore`.

**8.** What is the default cookie name of `CookieWebSessionIdResolver`? `SESSION`.

**9.** When does WebFlux automatically call `WebSession.save()`? Right before the response is committed.

**10.** Should you call `save()` manually in a controller? Not in a normal flow; the framework manages it automatically.

**11.** How should `Mono<Void>` from `invalidate()` and `changeSessionId()` be handled? Compose with `flatMap`/`then`, do not ignore the publisher and do not subscribe manually.

**12.** How do you set the idle timeout? Call `session.setMaxIdleTime(Duration)`.

**13.** Is the in-memory store suitable for a multi-node cluster? Not without a shared session store; each process keeps its own map.

**14.** What is used to share WebSession across multiple nodes? Spring Session with `ReactiveSessionRepository`, for example Redis.

**15.** Why shouldn't you update a counter with read-modify-write in a session under parallel requests? Because the operation is not atomic; updates can be lost.

**16.** Why do you need to change the session ID after login? To reduce session fixation risk; Spring Security provides corresponding protection.

**Remember:** `WebSession` holds attributes server-side; `WebSessionManager` gets the session for a request; `WebSessionIdResolver` transports the ID; `WebSessionStore` manages persistence. Getting a session does not automatically start it. Adding an attribute or calling `start()` starts it; WebFlux automatically calls `save()` right before response commit. Use `exchange.getSession()` and compose reactively, choose a store suitable for your deployment, manage idle timeout, invalidate/logout, and protect the session ID like a credential.

**Official documentation:**
- [Spring Framework 6.2 — WebSession Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework 6.2 — WebSessionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/session/WebSessionManager.html)
- [Spring Framework 6.2 — DefaultWebSessionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/session/DefaultWebSessionManager.html)
- [Spring Framework 6.2 — Reactive Core and WebSession infrastructure](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — @SessionAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/sessionattribute.html)
- [Spring Framework 6.2 — @SessionAttributes](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/sessionattributes.html)
- [Spring Session — WebSession Integration and Redis](https://docs.spring.io/spring-session/reference/web-session.html).
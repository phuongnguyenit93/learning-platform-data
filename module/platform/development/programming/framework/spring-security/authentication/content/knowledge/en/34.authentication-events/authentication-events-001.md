# AuthenticationEventPublisher and DefaultAuthenticationEventPublisher in Spring Security

## 1. What problem does this lesson solve?

When a Spring Security system authenticates a user successfully or unsuccessfully, development teams often want to **record audit logs, collect metrics, detect anomalous logins, or trigger a security workflow**. If all of that logic is placed inside HTTP filters, controllers, or `AuthenticationProvider`, the code becomes tightly coupled to the login mechanism and hard to reuse across form login, HTTP Basic, LDAP, JWT, or custom providers.

Spring Security provides the **authentication events** mechanism:

- `AuthenticationEventPublisher` is the **event publishing interface** for authentication results.
- `DefaultAuthenticationEventPublisher` is the **default implementation**: it publishes `AuthenticationSuccessEvent` when authentication succeeds, and maps common `AuthenticationException` types to specific `AbstractAuthenticationFailureEvent` classes.
- Spring Framework's `@EventListener` or `ApplicationListener` **receives events** to record, aggregate statistics, or perform side-effect tasks.

This lesson explains the mechanism, event emission points, exception mapping, bean registration, differences between events and authentication handlers, a runnable Spring Boot Java 17+ example, testing, and security/operational considerations.

**Version:** the main content uses **Spring Boot 3.5.x / Spring Security 6.5.x / Servlet**. Both APIs were introduced in Spring Security 3.0 and remain present in Spring Security 7.x, though the Java examples below follow Spring Boot 3.5 dependencies. Reactive/WebFlux flows require checking their own event publishing behavior, as they do not use the same `ProviderManager` by default.

## 2. Diagram: at which layer do events appear?

~~~text
Client
  |
  | Authorization: Basic ... / POST /login / other providers
  v
Spring Security authentication filter
  |
  | create Authentication request (usually unauthenticated)
  v
AuthenticationManager
  |
  v
ProviderManager  ----> AuthenticationProvider(s)
  |                           |
  |             check credentials / account state
  |                           |
  +<--------------------------+
  |
  +-- SUCCESS --> AuthenticationEventPublisher
  |                       |
  |                       +--> AuthenticationSuccessEvent
  |
  +-- FAILURE ----> AuthenticationEventPublisher
                          |
                          +--> AuthenticationFailureBadCredentialsEvent
                          +--> AuthenticationFailureLockedEvent
                          +--> ... other failure events
                                    |
                                    v
                          ApplicationEventPublisher
                                    |
                                    v
                    @EventListener / ApplicationListener
                    audit · monitoring · alerts · metrics
~~~

This diagram illustrates the **common flow when `AuthenticationManager` uses a `ProviderManager` configured with a publisher**. Not every authentication mechanism, custom manager, or request automatically publishes events in the same way.

Meanwhile, the filter handles the **HTTP flow** (returning 401, redirecting, creating a session, or handling callbacks). Events serve to **observe authentication results**, not to decide the HTTP response or replace credential verification.

### 2.1. One authentication is different from one HTTP request

- With **HTTP Basic**, each request carrying credentials can be re-authenticated, so a single client can produce multiple success events.
- With **form login + session**, after successful authentication, subsequent requests using the session that stores `SecurityContext` usually **do not** re-run password verification, so there is no new success event per page view.
- With **Bearer/JWT**, event generation depends on the authentication path and the specific manager/filter; do not automatically treat event counts as unique users.
- If a public endpoint is accessed without going through an authentication manager, it does not necessarily publish `AuthenticationSuccessEvent`.
- If a filter or custom endpoint sets `SecurityContext` directly without going through the publisher, you might not see any events.

**Event emission milestone:** this model focuses on authentication results at the `AuthenticationManager` layer. It is not proof that the browser received the cookie, that the user viewed the target page, or that every post-login business step succeeded.

## 3. AuthenticationEventPublisher: an interface with two methods

Package:

~~~java
org.springframework.security.authentication.AuthenticationEventPublisher
~~~

Two core methods:

~~~java
void publishAuthenticationSuccess(Authentication authentication);

void publishAuthenticationFailure(
        AuthenticationException exception,
        Authentication authentication);
~~~

| Parameter | Role | Key point to understand |
| --- | --- | --- |
| `authentication` on success | Authenticated `Authentication` object, containing principal and authorities | Do not log the entire object indiscriminately; it may contain sensitive details |
| `exception` on failure | `AuthenticationException` reason from the provider/manager | Selects the failure event type; should not send detailed messages to the client |
| `authentication` on failure | Original or in-progress authentication request | May contain **raw credentials**; do not log the raw object |

The publisher has no method to "verify passwords" or "log users in." It **does not** place authorities into `SecurityContext` itself; that is the responsibility of the authentication flow and providers.

### 3.1. Why separate the interface from the implementation?

A custom `AuthenticationEventPublisher` can forward results to Spring Application Events, a metrics collector, or an audit pipeline. However, it must preserve semantics, avoid swallowing important security errors, avoid reusing credentials, and never emit fake success events when authentication has not succeeded.

The default implementation suits most applications because it provides standard error mapping and uses Spring Framework's familiar event mechanism.

## 4. How does DefaultAuthenticationEventPublisher work?

Class:

~~~java
org.springframework.security.authentication.DefaultAuthenticationEventPublisher
~~~

This class implements `AuthenticationEventPublisher` and `ApplicationEventPublisherAware`. When passed an `ApplicationEventPublisher` or properly injected by Spring, it can publish events through the application context.

Bean example according to Spring Security:

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new DefaultAuthenticationEventPublisher(applicationEvents);
}
~~~

This is a **configuration snippet** to place inside a `@Configuration`/`@SpringBootApplication` class with the appropriate imports. The lab in section 7 provides a complete runnable program.

**Distinguishing the two publishers:**

- `AuthenticationEventPublisher`: **Spring Security** interface that receives authentication success/failure results.
- `ApplicationEventPublisher`: **Spring Framework** interface that publishes events to the general listener system.

`DefaultAuthenticationEventPublisher` is the class that **bridges the two worlds**: turning authentication results into Spring events for listeners to consume.

### 4.1. Authentication success

After `ProviderManager.authenticate(...)` returns a successful result, it invokes the publisher with the `Authentication` object, which by default publishes:

~~~text
AuthenticationSuccessEvent
~~~

A listener can access it as follows:

~~~java
@EventListener
void onSuccess(AuthenticationSuccessEvent event) {
    Authentication authentication = event.getAuthentication();
    // Authenticated; extract minimal metadata for auditing.
}
~~~

Do not use this event in place of authorization decisions. Access permissions are still checked during the authorization phase; a successful authentication does not mean every endpoint is `permitAll`.

### 4.2. Authentication failure

For failures, the publisher inspects the **exact class** of the `AuthenticationException` and chooses the event type based on the mapping.

Default table in Spring Security 6.5 documentation:

| Exception thrown | Default event |
| --- | --- |
| `BadCredentialsException` | `AuthenticationFailureBadCredentialsEvent` |
| `UsernameNotFoundException` | `AuthenticationFailureBadCredentialsEvent` |
| `AccountExpiredException` | `AuthenticationFailureExpiredEvent` |
| `ProviderNotFoundException` | `AuthenticationFailureProviderNotFoundEvent` |
| `DisabledException` | `AuthenticationFailureDisabledEvent` |
| `LockedException` | `AuthenticationFailureLockedEvent` |
| `AuthenticationServiceException` | `AuthenticationFailureServiceExceptionEvent` |
| `CredentialsExpiredException` | `AuthenticationFailureCredentialsExpiredEvent` |
| `InvalidBearerTokenException` | `AuthenticationFailureBadCredentialsEvent` |

Not every `AuthenticationException` is mapped. If an exception is not in the map and no fallback is configured, **no failure event may be published**, even though authentication still fails and the request is rejected.

**Note:** `UsernameNotFoundException` and `BadCredentialsException` both map to the bad credentials event. Standard `DaoAuthenticationProvider` can also hide non-existent user errors behind a bad credentials error to avoid distinguishing "user does not exist" from "wrong password" in external responses.

## 5. Important pitfall: exception mapping uses EXACT CLASS

`DefaultAuthenticationEventPublisher` matches the **actual runtime class** of the exception and does not automatically use "is-a" matching across the entire class hierarchy.

Example:

~~~java
class CustomBadCredentialsException
        extends BadCredentialsException {
    CustomBadCredentialsException(String message) {
        super(message);
    }
}
~~~

If the publisher only has the default mapping for `BadCredentialsException.class`:

~~~text
new BadCredentialsException(...)        → mapped
new CustomBadCredentialsException(...)  → NOT automatically mapped
~~~

A subclass with a similar name or extending an already mapped class **does not automatically produce an event**. This is a common reason listeners do not receive failure events from custom providers.

### 5.1. Adding exception mappings

Supported API:

~~~java
setAdditionalExceptionMappings(
    Map<Class<? extends AuthenticationException>,
        Class<? extends AbstractAuthenticationFailureEvent>>
)
~~~

**Illustrative** bean example (requires the custom class above and Spring Security imports):

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    var publisher =
        new DefaultAuthenticationEventPublisher(applicationEvents);

    publisher.setAdditionalExceptionMappings(Map.of(
        CustomBadCredentialsException.class,
        AuthenticationFailureBadCredentialsEvent.class
    ));

    return publisher;
}
~~~

The new map **merges** with the default mappings without requiring you to rewrite the entire list. Spring Security 6.5 supports the overload taking `Map<Class, Class>`. The older overload taking `Properties` is **deprecated**; do not use it in new code.

The event class must be a concrete subclass of `AbstractAuthenticationFailureEvent` and have a matching constructor:

~~~java
MyFailureEvent(Authentication authentication,
               AuthenticationException exception)
~~~

If you create a custom event type, listeners can filter by that class. For custom business errors, consider which exceptions genuinely represent authentication failures rather than authorization errors or system errors outside authentication.

### 5.2. Fallback for unmapped exceptions

The publisher also provides:

~~~java
setDefaultAuthenticationFailureEvent(
    Class<? extends AbstractAuthenticationFailureEvent> eventClass)
~~~

Depending on your code/version and contract, you can configure a fallback when an exception has no mapping. To have an explicit event type, you can define a concrete subclass:

~~~java
// Illustrative class snippet; place in a Java file with the appropriate package/imports.
public class UnmappedAuthenticationFailureEvent
        extends AbstractAuthenticationFailureEvent {

    public UnmappedAuthenticationFailureEvent(
            Authentication authentication,
            AuthenticationException exception) {
        super(authentication, exception);
    }
}
~~~

And configure it:

~~~java
publisher.setDefaultAuthenticationFailureEvent(
    UnmappedAuthenticationFailureEvent.class);
~~~

This is useful when you need to ensure **no failure audit is missed**. Do not map every unknown exception to `AuthenticationFailureBadCredentialsEvent` if it might represent a system outage, a locked account, or a situation requiring different operational handling.

**Distinction:** the absence of an event does not prove authentication succeeded. It could be due to a missing publisher, an unmapped custom exception, a flow bypassing the manager wired with the publisher, or an inactive subscriber.

## 6. Does Spring Boot register the publisher automatically?

In **Spring Boot 3.5**, Security Auto-Configuration typically provides a `DefaultAuthenticationEventPublisher` bean on the condition that **no other `AuthenticationEventPublisher` bean exists**. Therefore, in a standard Boot project, you **may not need** to declare a publisher bean to receive events.

However, note the distinctions:

| Case | What to watch out for |
| --- | --- |
| Boot + Spring Security with standard auto-configuration | Boot can create `DefaultAuthenticationEventPublisher` and register it with the framework-configured authentication manager |
| Declaring a custom `AuthenticationEventPublisher` bean | Your bean replaces Boot's default conditional bean; it must have the proper mappings/behavior |
| Manually calling `new ProviderManager(provider)` | **Does not automatically publish events by default**; you must call `setAuthenticationEventPublisher(...)` |
| Using a parent `AuthenticationManager` | Avoid configuring both parent and child to publish the same result into **duplicate events** |
| Custom filter not calling AuthenticationManager | The publisher may never be invoked |
| Catching AuthenticationException and swallowing the error before the manager | You may not get the expected event |
| Without Spring Boot | Per Spring Security documentation, explicitly register a publisher bean and wire it to the appropriate manager |

In Spring Security, `ProviderManager` defaults to a no-op publisher if you **construct the manager manually**. Declaring a publisher bean **does not automatically wire** it into every `ProviderManager` instantiated with `new` elsewhere.

Explicit wiring form:

~~~java
DaoAuthenticationProvider provider =
    new DaoAuthenticationProvider(userDetailsService);
provider.setPasswordEncoder(passwordEncoder);

ProviderManager manager = new ProviderManager(provider);
manager.setAuthenticationEventPublisher(authenticationEventPublisher);
~~~

This is a configuration snippet inside a bean/method using already-injected variables. Wire **only one** appropriate publisher to the manager by design; do not both manually call `publishAuthenticationSuccess(...)` inside the provider and let `ProviderManager` publish the same event again.

## 7. Runnable Spring Boot 3.5 / Java 17+ example

The following example intentionally configures the **publisher and ProviderManager explicitly** so the boundaries are clear. The access interface uses HTTP Basic for easy testing with `curl`; in production, use HTTPS. This is a Servlet demo program with no OAuth/LDAP dependencies.

Goals:

- Demo user `observer` / password `lab-password` hashed with BCrypt.
- Requests to `/me` authenticate through `DaoAuthenticationProvider`.
- `ProviderManager` publishes success or failure events via the attached publisher.
- Spring `@EventListener` logs the **event class name**, without logging the username, password, Basic header, or token.
- Do not log the full `Authentication` object or exception message.

### 7.1. Maven project

Structure:

~~~text
authentication-events-demo/
├── pom.xml
└── src/main/
    └── java/
        └── demo/
            └── events/
                └── AuthenticationEventsDemoApplication.java
~~~

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>authentication-events-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

Using the Spring Boot parent BOM pulls in the matching Spring Security 6.5 version. The example does not need a third "event starter"; Spring Framework Application Events are already included in the Boot/Security ecosystem.

### 7.2. Complete Java code

File `src/main/java/demo/events/AuthenticationEventsDemoApplication.java`:

~~~java
package demo.events;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthenticationEventsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthenticationEventsDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("observer")
                .password(encoder.encode("lab-password"))
                .roles("USER")
                .build());
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher events) {
        return new DefaultAuthenticationEventPublisher(events);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder,
            AuthenticationEventPublisher publisher) {
        var dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);

        var manager = new ProviderManager(dao);
        manager.setAuthenticationEventPublisher(publisher);
        return manager;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager)
            throws Exception {

        http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @RestController
    static class Api {

        @GetMapping("/health")
        String health() {
            return "Authentication events demo ready";
        }

        @GetMapping("/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("user", authentication.getName());
        }
    }

    @Component
    static class SecurityEventListener {
        private static final Logger log =
            LoggerFactory.getLogger(SecurityEventListener.class);

        @EventListener
        void onSuccess(AuthenticationSuccessEvent event) {
            // Do not log credentials, the full Authentication object,
            // or sensitive identifying information.
            log.info("AUTH_SUCCESS eventType={}",
                event.getClass().getSimpleName());
        }

        @EventListener
        void onFailure(AbstractAuthenticationFailureEvent event) {
            log.warn("AUTH_FAILURE eventType={} exceptionType={}",
                event.getClass().getSimpleName(),
                event.getException().getClass().getSimpleName());
        }
    }
}
~~~

### 7.3. Bean explanations

1. `PasswordEncoder` is BCrypt; the demo user is encoded at application startup rather than using `{noop}` in the store.
2. `DaoAuthenticationProvider` verifies the password from `UserDetailsService` and produces an authenticated token.
3. The manually created `ProviderManager` is **attached to exactly one** `AuthenticationEventPublisher` via `setAuthenticationEventPublisher(...)`.
4. The `DefaultAuthenticationEventPublisher` bean receives Spring Framework's `ApplicationEventPublisher` through its constructor.
5. `HttpSecurity.authenticationManager(manager)` ensures the HTTP Basic flow uses the newly configured manager rather than guessing which manager auto-configuration would wire.
6. `@EventListener` is a subscriber; it does not participate in password verification and does not return 401/200 to the client.
7. `/health` is public to check startup; `/me` requires authentication. `anyRequest().denyAll()` prevents unexpected routes.
8. Static nested `@Component` classes are discovered by Spring Boot's component scan when placed inside the application package.

**Caution with systems that already have other managers/filters:** do not copy this manager bean verbatim into an application with multiple authentication providers/SSO/JWT without checking the configuration. This isolated lab uses only the Dao provider.

### 7.4. Running

With Java 17+ and Maven installed, run from the project directory:

~~~bash
mvn spring-boot:run
~~~

Or if the project has the Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

On Windows you can use `mvnw.cmd spring-boot:run`.

Verify the application:

~~~bash
curl -i http://127.0.0.1:8080/health
~~~

Expected response has HTTP 200 and body:

~~~text
Authentication events demo ready
~~~

Log in with valid credentials to the protected endpoint:

~~~bash
curl -i --user observer:lab-password http://127.0.0.1:8080/me
~~~

Example response body:

~~~json
{"user":"observer"}
~~~

In the server log you will typically see:

~~~text
AUTH_SUCCESS eventType=AuthenticationSuccessEvent
~~~

Try a wrong password:

~~~bash
curl -i --user observer:wrong-password http://127.0.0.1:8080/me
~~~

Expected HTTP 401; the listener logs a failure event of type:

~~~text
AUTH_FAILURE eventType=AuthenticationFailureBadCredentialsEvent exceptionType=BadCredentialsException
~~~

**The log lines above are the identifying message content**, excluding the timestamp/logger/thread prefix that Spring Boot adds. The number of events depends on actual invocation count and the filter chain. If you copy passwords into the terminal, treat them strictly as **lab credentials** and never use them with real accounts; shell history and process lists can expose credentials. Run production over HTTPS with secure secrets.

### 7.5. Why aren't events emitted on every request?

With Basic, requests carrying a valid header are typically verified each time, though this can be affected by session/security-context caching or additional configured filters. With form login, subsequent requests on the session normally do not re-authenticate. **Counting events is neither counting requests nor counting online logged-in users.**

## 8. Standalone Java 17 example: why are subclasses not mapped?

To understand the exact mapping rule without running Spring Boot, the following program simulates **exact class lookup** using Java's `Map.get(exception.getClass())`.

**This is only a Java Collection demo** — it is not an implementation of `DefaultAuthenticationEventPublisher` and does not publish Spring Application Events.

Create `ExactExceptionMappingDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ExactExceptionMappingDemo {

    static class BadCredentials extends RuntimeException {}
    static class CustomBadCredentials extends BadCredentials {}

    public static void main(String[] args) {
        Map<Class<?>, String> mapping = new HashMap<>();
        mapping.put(BadCredentials.class,
                "AuthenticationFailureBadCredentialsEvent");

        System.out.println("base=" +
            mapping.get(new BadCredentials().getClass()));
        System.out.println("subclass=" +
            mapping.get(new CustomBadCredentials().getClass()));

        mapping.put(CustomBadCredentials.class,
                "AuthenticationFailureBadCredentialsEvent");

        System.out.println("afterMapping=" +
            mapping.get(new CustomBadCredentials().getClass()));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 ExactExceptionMappingDemo.java
java ExactExceptionMappingDemo
~~~

**Exact stdout:**

~~~text
base=AuthenticationFailureBadCredentialsEvent
subclass=null
afterMapping=AuthenticationFailureBadCredentialsEvent
~~~

The second line shows that the subclass is not mapped solely through inheritance. The third line illustrates the benefit of `setAdditionalExceptionMappings(...)` in the real publisher.

## 9. Events differ from SuccessHandler / FailureHandler / AccessDeniedHandler

These extension points handle **different concerns**:

| Component | Context in which it is invoked | Appropriate responsibility |
| --- | --- | --- |
| `AuthenticationEventPublisher` | Handling authentication result (usually via manager) | Publishing success/failure events |
| `@EventListener(AuthenticationSuccessEvent)` | Spring Application Event has been published | Auditing, metrics, anomaly detection |
| `AuthenticationSuccessHandler` | Interactive login filter succeeded | HTTP redirect, response, saved request |
| `AuthenticationFailureHandler` | Interactive login filter failed | Redirect `?error`, HTTP error response |
| `AuthenticationEntryPoint` | Request requires authentication but lacks it | 401 challenge or redirect to login |
| `AccessDeniedHandler` | Request is authenticated but lacks permissions | 403 response / denial handling rules |
| `AuthorizationDeniedEvent` / method authorization events | Authorization decision when enabled | Analyzing permission violations, not password errors |
| `InteractiveAuthenticationSuccessEvent` | Certain interactive authentication flows | Tracking completion of interactive login |

**Two success events are not the same:** `InteractiveAuthenticationSuccessEvent` does not extend `AuthenticationSuccessEvent`, so listeners for one do not receive duplicates as if they were the same event class. Do not add both counts together and assume they represent two separate user logins.

An HTTP 403 due to missing `ROLE_ADMIN` normally **does not** mean `BadCredentialsException` or `AuthenticationFailureBadCredentialsEvent`, because the user may have authenticated validly yet lack authorization.

### 9.1. AuthenticationFailureEvent and AuthenticationException

The failure classes listed in section 4 are subtypes of `AbstractAuthenticationFailureEvent`. Each failure event retains the original exception via `getException()`. In a listener:

~~~java
@EventListener
void onFailure(AbstractAuthenticationFailureEvent event) {
    String reasonType =
        event.getException().getClass().getSimpleName();
    // Record a standardized category/metric; do not log stack traces
    // or usernames/raw credentials arbitrarily.
}
~~~

There is no need (and you should not) return raw `event.getException().getMessage()` to the client; the message may describe internals or contain data that should not be disclosed.

## 10. Security: events can contain sensitive data

An `Authentication` object may contain:

- Username/principal and authorities.
- `credentials` such as the raw password in the authentication request **before erasure**.
- `details` such as IP address or session ID.
- A Bearer token or information placed into details by a provider/filter.
- Exceptions containing messages and causes with environmental data.

Therefore:

1. **Do not log `Authentication.toString()`, `getCredentials()`, full exceptions, or raw event objects** without a vetted masking strategy.
2. Prefer minimal metadata: event type, auth method, error category, server timestamp, correlation ID, and a protected internal user ID when available.
3. The username in a failure event can be arbitrary client input; do not use it as a sole key for locking accounts without rate-limiting by IP/device/user and protection against enumeration/DoS.
4. If capturing IP addresses, extract them via a trusted reverse-proxy chain; do not trust `X-Forwarded-For` headers directly from the Internet.
5. Logs/metrics need retention policies, access controls, PII minimization, and log injection protection.
6. Never put passwords, OTPs, Authorization headers, cookies, or private keys into tracing/exporters.
7. Bound cardinality: metrics should not carry username or token labels because doing so both leaks data and overloads the monitoring system.

### 10.1. Synchronous or asynchronous event listeners?

By default, Spring Application Events are processed **synchronously** unless an appropriate executor is configured. Consequently, a slow listener can increase login latency, and an unhandled exception thrown by a listener can affect the authentication flow or HTTP response depending on where the event was published.

For critical auditing:

- Collect **sanitized** and minimal payloads.
- Use a queue/outbox when slow processing is needed; bound capacity and implement retry/backpressure/idempotency.
- Never send raw `Authentication`/passwords to a message broker.
- Define **fail closed/fail open** behavior appropriate to the criticality of the audit, but do not let an auxiliary listener accidentally break all logins because a metrics service is slow.
- Never emit fake success events to "fix" missing events in logs.

Spring events do not automatically provide durable audit history across process restarts. If security investigations are required, you need a log/metric/audit store with appropriate retention policies and access controls.

## 11. Monitoring and attack detection

Appropriate observation categories:

| Metric/event | Purpose | Caveat |
| --- | --- | --- |
| Success count by auth method and service | Assess authentication traffic | Do not use as unique user count |
| Failure bad credentials | Detect password spraying/brute-force | Avoid raw username labels |
| Failure locked/disabled/expired | Track account states and support operations | Distinguish from bad password |
| Failure service exception | DB/LDAP/IdP or provider outage | Avoid misinterpreting as a credential attack |
| Provider not found | Miswired/misconfigured authentication manager | Requires checking manager/providers |
| Success after multiple failures | Anomaly signal per risk policy | Do not automatically conclude account takeover |
| Sudden drop of events to zero | Broken instrumentation or changed manager | Cross-check against request/authentication telemetry |

Example detection strategy:

~~~text
If the same source has multiple failures in a short window:
  -> increase risk score, apply rate-limit, captcha, or step-up per policy.

If there are multiple failures followed by a success:
  -> audit further; do not automatically alert "attack succeeded"
     before correlating identity, session, IP, and device.

If AuthenticationFailureServiceExceptionEvent appears:
  -> check provider/LDAP/DB health before locking users.
~~~

That is **business pseudocode**, not behavior built into Spring events. `DefaultAuthenticationEventPublisher` **does not** automatically lock accounts, rate-limit, grant permissions, or send emails; it publishes events for consumers.

## 12. Avoiding duplicate events with multiple AuthenticationManagers

An application may have:

~~~text
Child ProviderManager
    |
    +-- Provider A
    +-- Provider B
    |
    +--> Parent AuthenticationManager
~~~

According to Javadoc, `ProviderManager` can publish events even when the result/exception comes from its **parent**. If the parent is also configured to publish the same event, subscribers may receive **two events for a single authentication attempt**.

Therefore:

- Define where **event publishing ownership** lives in the manager hierarchy.
- Avoid attaching publishers to both parent and child for the same outcome unless duplication is intended.
- Do not manually invoke the publisher inside a custom provider while letting the manager publish again.
- When using multiple security filter chains, test each chain and the manager it uses.
- With queues/auditing, use correlation/deduplication if the infrastructure can redeliver.

Because `ProviderManager` defaults to a no-op publisher when constructed with `new`, there are two extremes: **no events** or **duplicate events**. Both should be verified with integration tests rather than guessed from bean counts.

## 13. Testing at the right level

### 13.1. Unit testing the publisher

You can instantiate the publisher with a fake `ApplicationEventPublisher` and invoke:

~~~java
var publisher = new DefaultAuthenticationEventPublisher(events);
publisher.publishAuthenticationSuccess(verifiedAuthentication);
publisher.publishAuthenticationFailure(
    new BadCredentialsException("bad credentials"),
    authenticationRequest);
~~~

This is an **illustrative test snippet** requiring `events`, `verifiedAuthentication`, and `authenticationRequest` variables provided by the test. When capturing events, assert that:

- Success creates `AuthenticationSuccessEvent`.
- Failure with `BadCredentialsException` creates `AuthenticationFailureBadCredentialsEvent`.
- An unmapped exception subclass emits no event when no fallback is configured.
- After adding a subclass mapping, the publisher emits the expected event class.
- The fallback for unmapped exceptions only fires after being configured.

Do not use mock `Authentication` objects containing real passwords when test assertions or logs might print that data.

### 13.2. Spring Boot integration tests

A test suite should verify both manager wiring and subscribers:

1. GET `/health` without credentials returns 200.
2. GET `/me` without credentials is rejected (typically 401).
3. GET `/me` with valid user/password returns 200 and the listener records success.
4. GET `/me` with a wrong password returns 401 and the listener records `AuthenticationFailureBadCredentialsEvent`.
5. If a custom provider throws `CustomBadCredentialsException`, adding the mapping produces the expected event.
6. If a `ProviderManager` is created manually without setting a publisher, tests should detect that no events are emitted.
7. If a parent manager is used, verify success/failure events are not duplicated.
8. Do not confuse a 403 missing-role denial with a password failure.
9. Ensure no passwords, Bearer tokens, or raw exception messages appear in logs or metrics.
10. A failing listener must not cause authentication to behave against security policy; manage failure handling explicitly.

**Note:** when testing with `MockMvc` and `spring-security-test` helpers like `with(user(...))`, some helpers only **pre-populate Authentication in the SecurityContext** instead of executing through `AuthenticationManager`. Such tests do not prove the publisher works. Integration tests need to pass through the real endpoint/manager.

### 13.3. When test events do not reach the listener

Check in order:

1. Is there a `DefaultAuthenticationEventPublisher` bean or proper publisher in the application context?
2. Which `ProviderManager` is actually handling that request?
3. Was `setAuthenticationEventPublisher(...)` called on the manager (if constructed manually)?
4. Is the request freshly authenticating or reusing a cached session/authentication?
5. Is the failure exception the exact mapped class?
6. Does the listener have `@Component`/`@EventListener` and get picked up by component scan?
7. Is there a parent/child manager causing duplicate events or publishing only on another manager?
8. Is another filter, bypass, or custom login endpoint creating a session without going through the manager?
9. Is a proxy or another OAuth2 login layer authenticating elsewhere and only forwarding the principal?
10. Is the listener throwing an exception or is a queue/monitor dropping data?

## 14. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "Having `@EventListener` guarantees events will arrive" | A publisher must emit the event and the manager/filter must route through it |
| "Spring Security always emits events for every request" | Events tie to authentication attempts, not every GET |
| "The default publisher handles all subclasses of BadCredentials" | **Exact exception class matching**; subclasses need explicit mapping or fallback |
| "A failure event means the user is not in the database" | Failure can be caused by wrong password, locked, disabled, provider unavailable, or invalid token |
| "A success event means the request is authorized" | Authorization can still return 403 |
| "AccessDeniedHandler publishes AuthenticationFailureEvent" | 403 authorization failure is distinct from authentication failure |
| "A custom ProviderManager will use the event publisher bean automatically" | Manual wiring is required when constructing the manager with `new` |
| "Every caught exception is an AuthenticationFailure" | Business errors do not belong to the authentication stage |
| "Enabling async @EventListener makes auditing durable" | In-memory queues can still lose data; persistence and durability require dedicated storage |
| "Logging the entire Authentication object is most convenient" | Very likely to leak credentials/details/tokens |
| "A success event means session logout succeeded" | Logout is a separate lifecycle requiring appropriate events/handlers |
| "HTTP Basic success on every request means the user logged in repeatedly" | Basic usually verifies credentials per request; it does not imply interactive logins |
| "Declaring a bean while the parent manager also publishes is harmless" | It can produce duplicate events |
| "Emit AuthenticationSuccessEvent for every HTTP 200" | HTTP 200 does not guarantee authentication just occurred |

## 15. Production deployment checklist

**Configuration and contract**

- [ ] Identify the exact AuthenticationManager and AuthenticationProvider handling every login path.
- [ ] Configure the proper publisher and wire it to manually constructed managers.
- [ ] Verify default mappings; map custom exceptions by **exact class**.
- [ ] Separate authn events from authz denied events and HTTP handlers.
- [ ] Prevent duplicate events across parent/child managers or custom providers.
- [ ] Have real success/failure tests for each major authentication type.

**Security and privacy**

- [ ] Never log passwords, session cookies, Bearer tokens, raw Authentication objects, or arbitrary exception messages.
- [ ] Use sanitized data in audit records with PII retention and access control.
- [ ] Implement rate limiting and account protection via dedicated security policy, not solely through events.
- [ ] Never trigger cross-account lockouts based solely on attacker-supplied usernames.
- [ ] Validate automated event-driven actions against risk policy to prevent spam/DoS.
- [ ] Ensure listeners do not leak user data via telemetry labels.

**Operations**

- [ ] Check whether synchronous listeners affect login latency.
- [ ] For critical audits, use appropriate queues/outboxes/retries/backpressure/deduplication.
- [ ] Monitor and alert when event volume drops to zero or spikes abnormally.
- [ ] Distinguish authentication errors from provider/service outages.
- [ ] Include trace/correlation IDs across instances and authentication flows.
- [ ] Understand the limitation: Spring Application Events are not a durable audit store on their own.

## 16. Self-check questions

1. How do `AuthenticationEventPublisher` and `ApplicationEventPublisher` differ?
2. What does `DefaultAuthenticationEventPublisher` do when `ProviderManager` returns a successful authentication?
3. Which event does a `BadCredentialsException` map to?
4. Why might a custom exception extending `BadCredentialsException` fail to publish an event?
5. Which API is used to add custom exception mappings, and why should you use the Map overload?
6. Why might a custom `new ProviderManager(...)` fail to publish events even when a publisher bean exists in the context?
7. What is the difference between `AuthenticationSuccessEvent` and `InteractiveAuthenticationSuccessEvent`?
8. Does an HTTP 403 due to a missing role mean `AuthenticationFailureBadCredentialsEvent` was published?
9. Why should you avoid logging the entire `event.getAuthentication()` in a failure listener?
10. Why can heavy synchronous listeners slow down logins?
11. How many success events should one form login with a session and multiple subsequent GET requests produce?
12. What problem arises when both parent and child managers publish events?
13. Why do tests using `with(user(...))` not necessarily test the publisher?
14. Events aid auditing, but are they automatically persisted durably across application restarts?

**Conclusion:** `AuthenticationEventPublisher` is the contract for publishing authentication outcomes, and `DefaultAuthenticationEventPublisher` bridges `ProviderManager` to **Spring Application Events** using standard **exact-class** error mapping. Reliable observability requires **proper manager wiring, appropriate listeners, no duplicates, no credential logging, and testing every authentication flow**.

## 17. Official references

- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — AuthenticationEventPublisher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationEventPublisher.html)
- [Spring Security 6.5 — DefaultAuthenticationEventPublisher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DefaultAuthenticationEventPublisher.html)
- [Spring Security 6.5 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — AuthenticationFailureBadCredentialsEvent](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/event/AuthenticationFailureBadCredentialsEvent.html)
- [Spring Boot 3.5 — Spring Security Auto-Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Framework — Annotation-driven event listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-annotation)

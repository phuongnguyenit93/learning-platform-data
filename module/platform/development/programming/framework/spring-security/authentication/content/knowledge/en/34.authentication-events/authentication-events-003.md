# Mapping Custom Exceptions to Appropriate Authentication Events in Spring Security

**Authentication events** allow an application to record successful/failed logins, generate metrics, trigger alerts, or write audit logs without mixing all observability logic into Servlet filters or login pages. In Spring Security, **`DefaultAuthenticationEventPublisher`** translates certain `AuthenticationException` types into events such as `AuthenticationFailureBadCredentialsEvent`, `AuthenticationFailureLockedEvent`, or `AuthenticationFailureServiceExceptionEvent`.

A problem arises when a project defines **custom exceptions**. For example, `DirectoryTemporarilyUnavailableException` extends `AuthenticationServiceException`, yet by default it does not necessarily emit the same event as its parent class. The critical reason: the default publisher **maps by exact exception class**, rather than walking up the inheritance hierarchy. To emit semantically accurate events, you need to register explicit mappings, choose the right event type, and test both event emission and information security.

This lesson explains the exception -> event path, default mappings, how to create custom exceptions/custom events, configuring `AuthenticationEventPublisher` and `@EventListener`, distinguishing events from `AuthenticationFailureHandler`, testing, and operational considerations. Code examples use **Java 17+ / Spring Security Servlet**; parts requiring a Spring context are explicitly noted rather than equated with standalone Java programs runnable via `javac`.

## 1. How do AuthenticationException and Authentication Events differ?

An `AuthenticationException` represents an **unsuccessful authentication attempt**; it is thrown while verifying credentials, account status, providers, or identity sources. An **authentication event** is a notification published to the Spring ApplicationContext so listeners can react to that outcome.

| Component | Role | Example |
| --- | --- | --- |
| `Authentication` | Authentication request or post-authentication result | `UsernamePasswordAuthenticationToken` |
| `AuthenticationManager` / `ProviderManager` | Coordinates `AuthenticationProvider` instances | Selects provider, handles result |
| `AuthenticationException` | Reason authentication failed | `BadCredentialsException`, custom exception |
| `AuthenticationEventPublisher` | Event publishing interface | `publishAuthenticationFailure(...)` |
| `DefaultAuthenticationEventPublisher` | Publisher mapping exceptions -> default events | `LockedException` -> locked event |
| `AbstractAuthenticationFailureEvent` | Base class for failure events | Holds `getAuthentication()` / `getException()` |
| `AuthenticationSuccessEvent` | Authentication success event | Counts successful authentications |
| `@EventListener` | Handles events in the Spring context | Auditing, telemetry, alerts |

Key point: **an exception is the failure decision on the authentication path; an event is the notification to observe that failure**. Configuring an event does not automatically change the HTTP status, turn `Authentication` into a success, or unlock an account.

Common flow diagram:

~~~text
HTTP Login / API authentication
          |
          v
Authentication filter / caller
          |
          v
AuthenticationManager (usually ProviderManager)
          |
          v
AuthenticationProvider checks credentials + policy
          |
          +-- success -> returns authenticated Authentication
          |                 |
          |                 v
          |       AuthenticationEventPublisher
          |                 |
          |                 +--> AuthenticationSuccessEvent
          |
          +-- failure -> throws AuthenticationException
                            |
                            v
                  AuthenticationEventPublisher
                            |
                            v
                  Exception type -> Event mapping
                            |
                            +--> AbstractAuthenticationFailureEvent
                            |
                            v
                    @EventListener / metrics / audit
          |
          v
HTTP authentication success/failure handler decides response
~~~

This is a conceptual model; exact ordering depends on filters/providers and configuration. If an exception is caught and swallowed before reaching `AuthenticationManager`, or if you construct a `ProviderManager` without setting an event publisher, **there is no guarantee an event will be published**.

## 2. Default mappings worth knowing

Spring Security 7.x Authentication Events documentation lists the key mappings:

| Exact AuthenticationException | Failure event |
| --- | --- |
| `BadCredentialsException` | `AuthenticationFailureBadCredentialsEvent` |
| `UsernameNotFoundException` | `AuthenticationFailureBadCredentialsEvent` |
| `AccountExpiredException` | `AuthenticationFailureExpiredEvent` |
| `CredentialsExpiredException` | `AuthenticationFailureCredentialsExpiredEvent` |
| `DisabledException` | `AuthenticationFailureDisabledEvent` |
| `LockedException` | `AuthenticationFailureLockedEvent` |
| `ProviderNotFoundException` | `AuthenticationFailureProviderNotFoundEvent` |
| `AuthenticationServiceException` | `AuthenticationFailureServiceExceptionEvent` |
| `InvalidBearerTokenException` | `AuthenticationFailureBadCredentialsEvent` |

This is an **event mapping**, not an HTTP status table. For example, `LockedException` can lead to `AuthenticationFailureLockedEvent` internally, yet the public login UI should still return a **generic message** to prevent account enumeration.

Other exceptions or custom subclasses **do not have default mappings**. Depending on fallback configuration, they may produce no failure event. When framework documentation changes across versions, verify Javadoc and the mapping list against your running dependency.

### Do not use "special" events just to drive UI messages

For instance, a disabled account might be recorded internally with `AuthenticationFailureDisabledEvent`. That does **not** mean returning "This account exists but is disabled" to the browser. Events are for the backend; client error messaging must follow the application's security requirements.

Similarly, an OAuth bearer token system may emit a bad-credentials event for an invalid token, so you must not infer from the event class alone that the request's credential type was always a password.

## 3. Biggest pitfall: exact exception class, no mapping inheritance

Suppose you create:

~~~java
public final class DirectoryTemporarilyUnavailableException
        extends AuthenticationServiceException {

    public DirectoryTemporarilyUnavailableException(String message) {
        super(message);
    }
}
~~~

The publisher has the default mapping:

~~~text
AuthenticationServiceException.class
    -> AuthenticationFailureServiceExceptionEvent.class
~~~

**Do not infer:**

~~~text
DirectoryTemporarilyUnavailableException.class
    -> AuthenticationFailureServiceExceptionEvent.class
~~~

By default, the publisher looks up by **exact exception class** (conceptually `exception.getClass()`), rather than searching superclass mappings. Therefore, a subclass does not necessarily emit the event the author expects, even though `instanceof AuthenticationServiceException` returns true.

Illustrative table:

| Exception actually thrown | Explicit mapping? | Expected event |
| --- | --- | --- |
| `AuthenticationServiceException` | Default | Service exception event |
| `DirectoryTemporarilyUnavailableException` | No | No event or fallback depending on configuration |
| `DirectoryTemporarilyUnavailableException` | Mapped to service event | Service exception event |
| `InvalidOtpException extends BadCredentialsException` | No | Does not automatically inherit bad credentials event |
| `InvalidOtpException` | Mapped to bad credentials event | Bad credentials event |
| `UnknownCustomAuthenticationException` | No, fallback configured | Catch-all event |

**Technical takeaway:** changing an exception's class hierarchy can drop or alter event telemetry if the team does not review the mapping list. Every operationally meaningful custom `AuthenticationException` must be listed and tested explicitly.

## 4. Choose events by failure nature, not just exception name

First, determine which failure category the error truly belongs to:

| Scenario | Suggested event type | Notes |
| --- | --- | --- |
| Wrong password/OTP/token | Bad credentials event | Never reveal which users exist |
| Account locked | Locked event | Status must be determined by a trusted identity source |
| Account disabled | Disabled event | Do not use events to auto-unlock |
| Expired credentials | Credentials expired event | Distinct from account expiration |
| Expired account | Expired event | Based on lifecycle policy |
| Identity source unavailable | Service exception event | Do not blame infrastructure outages on user bad passwords |
| No provider supports token type | Provider not found event | Check ProviderManager configuration |
| Custom authentication rule rejected | Custom failure event | Use clear naming/semantics without exposing sensitive reasons |

For example: `DirectoryTemporarilyUnavailableException` means the IdP/LDAP is unresponsive. If mapped to `AuthenticationFailureBadCredentialsEvent`, dashboards will falsely report wrong passwords; the system might trigger false credential-stuffing alerts or wrongly increment lockout counters. Map it to **service failure event** instead.

Conversely, `OtpCodeMismatchException` is a credential verification failure, so a bad credentials event may fit — unless the application needs a dedicated custom event to distinguish *authentication factor types* under internal policy.

**Authorization warning:** when an already authenticated user accesses a resource without permission, that is normally an **authorization failure** (e.g., `AccessDeniedException`/HTTP 403), **not an authentication exception**. Never force every 403 error into `AuthenticationFailureBadCredentialsEvent`; doing so pollutes event semantics and skews failed-login counts.

**Pending MFA/step-up:** requiring a user to complete an additional step is not necessarily a final authentication failure. If the flow is multi-stage, do not throw a failure exception just to trigger a metric every time an OTP is needed; model challenge/flow state properly.

## 5. Key APIs of DefaultAuthenticationEventPublisher

The publisher supports these APIs:

~~~java
DefaultAuthenticationEventPublisher publisher =
        new DefaultAuthenticationEventPublisher(applicationEventPublisher);

publisher.setAdditionalExceptionMappings(mappings);

publisher.setDefaultAuthenticationFailureEvent(
        UnmappedAuthenticationFailureEvent.class);
~~~

Here `applicationEventPublisher` is Spring's `ApplicationEventPublisher`, and `mappings` is:

~~~java
Map<Class<? extends AuthenticationException>,
    Class<? extends AbstractAuthenticationFailureEvent>>
~~~

Characteristics:

- `setAdditionalExceptionMappings(Map)` **adds or overrides** mappings alongside the defaults; keys are exception classes, values are event classes.
- The specified event must be a concrete subclass of `AbstractAuthenticationFailureEvent` with a matching `(Authentication, AuthenticationException)` constructor.
- `setDefaultAuthenticationFailureEvent(...)` configures a fallback event for any **unmapped** exception. Do not use the fallback to mask missing mappings for critical business/operational errors.
- The overload taking `Properties` is marked deprecated in modern Spring Security versions; prefer the typed `Map` to avoid String class names and runtime configuration errors.
- Passing `ApplicationEventPublisher` to the constructor publishes events to that context; when declared as a Spring bean, the framework can also inject it via `ApplicationEventPublisherAware`.

Do not create a separate `AuthenticationEventPublisher` bean per exception. A single publisher with an explicit map keeps the entire event-publishing policy manageable and prevents competing publishers.

## 6. Complete configuration example for custom exceptions and events

Scenario: the system authenticates against an external directory. When the directory is unavailable, the provider throws `DirectoryTemporarilyUnavailableException`; the team wants a service-failure event. When an internal authentication condition is rejected, the provider throws `CredentialPolicyRejectedException`; the team wants a **custom event** for separate analysis. These exceptions must be thrown inside the **authentication flow**, not from an arbitrary controller.

File **AuthenticationEventConfig.java** — code inside a Spring Boot Servlet application using Spring Security 6.x/7.x:

~~~java
package demo.auth.events;

import java.util.Map;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationFailureServiceExceptionEvent;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

@Configuration(proxyBeanMethods = false)
public class AuthenticationEventConfig {

    public static final class DirectoryTemporarilyUnavailableException
            extends AuthenticationServiceException {
        public DirectoryTemporarilyUnavailableException(String message) {
            super(message);
        }
    }

    public static final class CredentialPolicyRejectedException
            extends AuthenticationException {
        public CredentialPolicyRejectedException(String message) {
            super(message);
        }
    }

    public static final class AuthenticationFailurePolicyRejectedEvent
            extends AbstractAuthenticationFailureEvent {
        public AuthenticationFailurePolicyRejectedEvent(
                Authentication authentication,
                AuthenticationException exception) {
            super(authentication, exception);
        }
    }

    public static final class AuthenticationFailureUnmappedEvent
            extends AbstractAuthenticationFailureEvent {
        public AuthenticationFailureUnmappedEvent(
                Authentication authentication,
                AuthenticationException exception) {
            super(authentication, exception);
        }
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationEvents) {

        Map<Class<? extends AuthenticationException>,
            Class<? extends AbstractAuthenticationFailureEvent>> mappings =
                Map.of(
                    DirectoryTemporarilyUnavailableException.class,
                    AuthenticationFailureServiceExceptionEvent.class,
                    CredentialPolicyRejectedException.class,
                    AuthenticationFailurePolicyRejectedEvent.class);

        DefaultAuthenticationEventPublisher publisher =
                new DefaultAuthenticationEventPublisher(applicationEvents);

        publisher.setAdditionalExceptionMappings(mappings);
        publisher.setDefaultAuthenticationFailureEvent(
                AuthenticationFailureUnmappedEvent.class);
        return publisher;
    }
}
~~~

### Code explanation

- Both exceptions are `AuthenticationException` or subclasses; they can be thrown by an `AuthenticationProvider` when authentication fails.
- The first mapping preserves the **directory/service outage** meaning rather than reporting a user bad password.
- The second mapping emits a dedicated event because the error carries specific business monitoring semantics.
- The custom event extends `AbstractAuthenticationFailureEvent` and exposes the exact two-argument constructor required by the publisher.
- The fallback event `AuthenticationFailureUnmappedEvent` captures other unmapped custom failures.
- `@Bean` returns the `AuthenticationEventPublisher` interface so Spring Security-configured authentication managers can consume it.

**Execution scope:** This is a configuration class inside a Spring Boot application with Spring Security; it **does not set up an AuthenticationManager or provider on its own** and cannot run standalone with `javac`. You need a Spring Boot main class, compatible dependencies, an authentication flow actually wired to this publisher, and a user/provider throwing the sample exceptions.

**Why use a concrete fallback event?** `AbstractAuthenticationFailureEvent` is abstract. Even though some documentation versions show the abstract class name to illustrate a catch-all, application code should pick a **concrete event class with a valid constructor** like `AuthenticationFailureUnmappedEvent` to avoid runtime instantiation errors.

If the organization does not need policy-specific classification, replacing the second mapping with an appropriate **built-in event** is also fine. However, do not choose a "BadCredentials" event just because it is common; telemetry must reflect the server-determined authentication cause.

## 7. AuthenticationProvider must throw the right exception

An application authentication provider can throw custom exceptions at the appropriate moments:

~~~java
// Snippet inside AuthenticationProvider.authenticate(...):
try {
    directoryClient.verifyCredential(username, password);
} catch (DirectoryTimeoutException ex) {
    throw new AuthenticationEventConfig
            .DirectoryTemporarilyUnavailableException(
                    "Authentication directory temporarily unavailable");
}

if (!policy.allowsAuthentication(username, loginContext)) {
    throw new AuthenticationEventConfig
            .CredentialPolicyRejectedException(
                    "Authentication policy rejected");
}

// Only when all steps pass should an authenticated Authentication be returned.
~~~

This is **Java pseudocode dependent on application interfaces**; `directoryClient`, `policy`, `DirectoryTimeoutException`, and `loginContext` must be defined by the project. It is not a standalone compilable class.

Principles:

1. Only throw custom exceptions representing **authentication failures**; do not misuse them for post-login authorization errors.
2. Preserve semantics when translating exceptions from LDAP/IdP/KMS into Spring `AuthenticationException`.
3. Never place raw passwords/tokens in exception messages or cause chains exposed to public logs.
4. Avoid catching `AuthenticationException`, logging it, and returning a fake success token. The manager must see the failure to publish the event and let the filter handle the outcome.
5. Never manually construct `new AuthenticationSuccessEvent(...)` when authentication has not actually succeeded.

**Note:** genuine service errors must be tracked separately so on-call engineers can distinguish them from wrong passwords. Never turn an outage into a mass lockout wave by misclassifying the failure type.

## 8. Receiving events with @EventListener

Spring Framework supports `@EventListener`. Example file **AuthenticationAuditListener.java**:

~~~java
package demo.auth.events;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;

@Component
public class AuthenticationAuditListener {

    private static final Logger log =
            LoggerFactory.getLogger(AuthenticationAuditListener.class);

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        // Only log event/exception types; do not print credentials or messages.
        log.info("auth_failure event={} exception={}",
                event.getClass().getSimpleName(),
                event.getException().getClass().getSimpleName());
    }

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        log.info("auth_success");
    }
}
~~~

This file runs **inside a Spring context**, not standalone. It handles every subtype of `AbstractAuthenticationFailureEvent`, including custom and fallback events. You can declare dedicated listeners for `AuthenticationFailurePolicyRejectedEvent` or `AuthenticationFailureServiceExceptionEvent` if separate metrics are needed.

Do not log:

~~~java
// Do not do:
log.info("credential={}", event.getAuthentication().getCredentials());
log.info("exceptionMessage={}", event.getException().getMessage());
~~~

The request authentication object may contain passwords/tokens/certificates or sensitive data; the exception message may contain usernames, tenants, internal endpoints, or provider details. Audits should use **allowlisted event categories**, correlation IDs, environment, and properly PII-handled identifiers instead of dumping the full `Authentication`.

**Never make a listener write 401/403 to HttpServletResponse.** Event listeners may run outside a Servlet request context. HTTP responses belong to `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, or the corresponding web filter.

## 9. Distinguishing AuthenticationFailureHandler from Authentication Events

These two concepts are easily confused because both mention "failure":

| Mechanism | Where it is used | Primary responsibility |
| --- | --- | --- |
| `AuthenticationFailureHandler` | Servlet filters, e.g., form login | Selects redirect, status, and message after failure |
| `AuthenticationEventPublisher` | AuthenticationManager or integrated flow | Publishes events for system observability |
| `@EventListener` | Spring ApplicationContext | Records audits/metrics/alerts or secondary logic |
| `AuthenticationEntryPoint` | When a request needs authentication | Starts login flow or returns 401 |
| `AccessDeniedHandler` | When a user lacks permissions | Handles authorization denial, typically 403 |

For instance, a `CredentialPolicyRejectedException` can lead to **an internal custom failure event**, while HTTP login still returns "Invalid username or password" or a generic policy message. They do not conflict.

**Do not use event mapping to mask a response leak:** even if mapped to a bad-credentials event, if the failure handler returns "User is disabled" for `DisabledException`, the browser still sees sensitive details. Public messaging must be protected separately.

## 10. ProviderManager must actually use the configured publisher

When the application uses an authentication manager built by Spring Security/Boot, the `AuthenticationEventPublisher` bean is typically integrated via security configuration. However, if you instantiate `ProviderManager` manually, do not assume it automatically finds and attaches a publisher from the ApplicationContext.

Illustrative snippet:

~~~java
AuthenticationProvider provider = ...; // genuinely configured provider

ProviderManager manager = new ProviderManager(provider);
manager.setAuthenticationEventPublisher(authenticationEventPublisher);
~~~

This is a **Java snippet depending on a real provider and publisher**. You must import `org.springframework.security.authentication.ProviderManager` and `org.springframework.security.authentication.AuthenticationProvider`; the concrete class/method must reside in application configuration.

Per Javadoc, `ProviderManager` can default to a no-op publisher when constructed manually, so having a listener bean does not guarantee you will receive events from this manager.

### Parent AuthenticationManager can cause duplicate events

A `ProviderManager` can have a **parent AuthenticationManager**. Javadoc warns: the child manager may publish an event for a result/error returned by the parent; if the parent also has its own publisher, **the same attempt can emit multiple events**.

Mitigations:

- Review parent/child manager architecture when using multiple filter chains.
- Configure publishing responsibility in only one place to avoid double-counting metrics/lockouts.
- Test that one attempt produces the exact expected event count.
- Make listeners idempotent if events feed downstream audits/metrics.

Do not equate event counts with absolute HTTP request counts if the authentication manager is invoked multiple times per request or the system has multi-step authentication.

## 11. Do you need a fallback event for every exception?

`setDefaultAuthenticationFailureEvent(...)` is helpful to avoid missing unmapped exceptions. However, **a fallback is not a substitute for proper classification**.

Example:

~~~text
CustomUnknownException
    |
    v
No exact mapping found
    |
    v
AuthenticationFailureUnmappedEvent
    |
    v
Metric: auth_failure_unmapped
~~~

A system should:

- Use the fallback to spot new exceptions needing review.
- Set up dashboards/alerts when unmapped fallback events spike.
- Never use "bad credentials" as a fallback for all errors; outages would then be counted as credential attacks.
- Maintain an inventory of custom exceptions and their business owners.
- Add mappings/documentation/tests whenever a new exception is introduced.
- Never rethrow a fallback exception after a listener processes the event, creating loops or breaking the login flow.

If a new subtype of `AuthenticationException` appears after a dependency upgrade, the fallback helps surface the change; you must still verify the publisher is attached to the right manager and the listener is registered.

## 12. Mapping and public error responses must stay decoupled

A realistic scenario:

~~~text
username does not exist -> UsernameNotFoundException
wrong password          -> BadCredentialsException
account is locked       -> LockedException
directory unreachable   -> DirectoryTemporarilyUnavailableException
~~~

On the backend, these can be classified into distinct events for investigation. However, responses sent to the Internet must not arbitrarily expose differences that reveal user existence.

Example policy:

| Case | Internal event | Suggested public response |
| --- | --- | --- |
| Wrong password | BadCredentials event | Generic authentication failure |
| Unknown user | BadCredentials event (if provider throws the right type) | Same generic failure |
| Locked account | Locked event | Anti-enumeration designed message |
| Disabled account | Disabled event | Do not confirm account state to anonymous callers |
| Directory outage | Service failure event | Generic authentication error, operational support per policy |
| OTP mismatch | Custom or BadCredentials event | Do not reveal OTP value or correctness details |
| Missing permission post-login | Separate authorization event/handler | 403/redirect per policy |

**Never use metrics or event subtypes to alter response timing in an exploitable way.** If a listener performs synchronous RPC/SMTP calls only when an account exists, it can create a timing side-channel even when the login failure handler returns the exact same body.

For sensitive events, keep processing lightweight, limit logging/PII, and offload slow work to a protected queue when needed.

## 13. Understanding synchronous, asynchronous, and reliable event listeners

Spring `ApplicationEvent` instances are typically handled **synchronously** with the default multicaster. This has consequences:

- A slow listener lengthens authentication latency.
- A listener throwing an unchecked exception can affect the caller and make failure flows unpredictable.
- Audit/notification side effects may run before the HTTP response finishes.
- In-memory application events must not be relied upon as a **durable queue** with guaranteed at-least-once/once-only delivery.

When sending security notifications, SIEM logs, or compliance audits:

1. Keep the listener lightweight or persist an event record via an appropriate durable mechanism.
2. Offload slow side effects to a worker/queue with retries and idempotency.
3. Explicitly define which events must be recorded before permitting login (business/compliance requirement).
4. Avoid circular dependencies: a listener calling back into `AuthenticationManager` or throwing hard-to-handle exceptions.
5. Measure drop/failure rates of the event pipeline; do not rely solely on having `@EventListener` code present.
6. In a multi-instance cluster, events inside one JVM do not automatically broadcast to other nodes.

**Important:** a published authentication event does not necessarily carry full HTTP request context. If IP/user-agent/session correlation is needed, obtain it from an authorized component in the same security flow or a trusted correlation context, rather than assuming `AbstractAuthenticationFailureEvent` contains those fields.

## 14. Testing exact-class logic with plain Java 17

Before testing with the Spring runtime, you can use a mini Java 17 lab illustrating **exact-class mapping lookup**. This program does not use Spring Security and does not publish real ApplicationEvents; it demonstrates the principle described in the publisher documentation.

Create **ExactExceptionEventMappingDemo.java**:

~~~java
import java.util.Map;

public class ExactExceptionEventMappingDemo {

    static class CredentialFailure extends RuntimeException {}
    static class CustomCredentialFailure extends CredentialFailure {}
    static class DirectoryFailure extends RuntimeException {}
    static class UnknownFailure extends RuntimeException {}

    private static final Map<Class<? extends RuntimeException>, String>
            EVENTS = Map.of(
                    CredentialFailure.class, "BAD_CREDENTIALS",
                    DirectoryFailure.class, "SERVICE_FAILURE");

    static String eventFor(RuntimeException exception) {
        return EVENTS.getOrDefault(exception.getClass(), "UNMAPPED");
    }

    public static void main(String[] args) {
        System.out.println("Base = "
                + eventFor(new CredentialFailure()));
        System.out.println("Subclass = "
                + eventFor(new CustomCredentialFailure()));
        System.out.println("Service = "
                + eventFor(new DirectoryFailure()));
        System.out.println("Unknown = "
                + eventFor(new UnknownFailure()));
    }
}
~~~

Compile/run:

~~~bash
javac ExactExceptionEventMappingDemo.java
java ExactExceptionEventMappingDemo
~~~

Exact stdout:

~~~text
Base = BAD_CREDENTIALS
Subclass = UNMAPPED
Service = SERVICE_FAILURE
Unknown = UNMAPPED
~~~

Explanation:

- `CredentialFailure.class` has a mapping, so it yields BAD_CREDENTIALS.
- `CustomCredentialFailure` is a subclass, yet **does not automatically inherit the superclass mapping**, so it yields UNMAPPED.
- The directory error is explicitly mapped to SERVICE_FAILURE.
- Unmapped errors fall back to UNMAPPED.
- Adding `CustomCredentialFailure.class` to the map changes the output to reflect the new mapping.

From there, apply this to Spring Security with `Class<? extends AuthenticationException>` -> `Class<? extends AbstractAuthenticationFailureEvent>`. **Never substitute the mini lab code for a real Spring Security AuthenticationEventPublisher**; it only helps learners grasp exact matching and the risk of missing event observations.

## 15. Testing the Spring publisher without HTTP

You should have a small test invoking the publisher directly to verify mappings work. One Spring Framework testing approach uses an ApplicationContext/listener collecting a list of events.

JUnit 5/Spring test pseudocode (requires a real project and imports):

~~~java
// Build a context containing the @Bean AuthenticationEventPublisher from section 6.
// Register a listener collecting events in the test environment.
Authentication attempted =
        new UsernamePasswordAuthenticationToken("user", "test-secret");

// Invoke directly to verify mapping without asserting full login failure flow.
publisher.publishAuthenticationFailure(
        new AuthenticationEventConfig
                .DirectoryTemporarilyUnavailableException("directory down"),
        attempted);

// Assertion: exactly 1 AuthenticationFailureServiceExceptionEvent received.
// Must not expect AuthenticationFailureBadCredentialsEvent.
~~~

This is a **directional test snippet**, not a complete JUnit class or standalone runnable command. Real tests should use `ApplicationEvents` in Spring Boot Test or a Spring `ApplicationContext` with a test listener, verifying event counts and types.

What to test separately:

- Direct call to `publishAuthenticationFailure` to verify **publisher mapping**.
- Calling `AuthenticationManager.authenticate(...)` to verify **integration publisher wiring**.
- Real requests through the filter chain to verify responses/failure handlers/CSRF/sessions.
- When multiple AuthenticationManagers or security chains exist, verify there are no duplicate events.

Do not take publisher unit test results as proof that every route emits events.

## 16. Complete testing matrix

| Scenario | Expected event / behavior |
| --- | --- |
| Exact `BadCredentialsException` | `AuthenticationFailureBadCredentialsEvent` |
| `LockedException` | `AuthenticationFailureLockedEvent` |
| `DisabledException` | `AuthenticationFailureDisabledEvent` |
| `CredentialsExpiredException` | `AuthenticationFailureCredentialsExpiredEvent` |
| `DirectoryTemporarilyUnavailableException` with mapping | `AuthenticationFailureServiceExceptionEvent` |
| `CredentialPolicyRejectedException` with mapping | `AuthenticationFailurePolicyRejectedEvent` |
| Unmapped exception with fallback | `AuthenticationFailureUnmappedEvent` |
| New unmapped custom subclass | Fallback, not auto-mapped via superclass |
| Custom mapping added for new subclass | Expected configured event type |
| Successful authentication | `AuthenticationSuccessEvent` if publisher is invoked |
| Auth provider fails without throwing `AuthenticationException` properly | Investigate because no event may be published |
| Manual `ProviderManager` constructed without publisher | Listener sees no events; do not conclude login had no errors |
| Both parent and child managers publish | Risk of double events; requires design/testing |
| No listener | Publisher still publishes, but no audit handler acts on it |
| Listener throws RuntimeException | May impact the flow; requires operational handling |
| Listener logs credentials | Must be blocked by tests/security review |
| Login handler returns different messages per error | Test anti-enumeration independently of event mapping |
| HTTP 403 authorization error post-login | Not an authentication failure event by default |
| Directory outage | Not counted as password brute force |
| Multi-node deployment | Nodes must aggregate telemetry/audits properly |

### Regression tests on version upgrades

Keep a test suite covering the exception classes the team relies on. After upgrading Spring Security:

1. Verify default mappings and API compatibility.
2. Check for new `AuthenticationException` types or hierarchy changes.
3. Ensure `@Bean AuthenticationEventPublisher` is injected into the right manager.
4. Verify listeners receive events when providers throw real exceptions.
5. Verify no account states or credentials leak via HTTP/logs.
6. Check event counts and latency under realistic load.

## 17. Troubleshooting: why is a custom exception missing an event?

| Symptom | Question to check | Resolution |
| --- | --- | --- |
| No event seen for custom exception | Is there an exact mapping for the runtime class? | Add a Map entry |
| Subclass of BadCredentialsException has no event | Publisher uses exact matching, not inheritance | Map the subclass explicitly |
| `@Bean` configured yet still no events | Which AuthenticationManager is actually running? | Attach publisher to the right manager |
| Events appear in tests but not in API | Does the filter/provider go through the manager or catch exceptions itself? | Inspect the call chain |
| Bad-credentials event emitted during IdP outage | Was the wrong exception thrown or mapped? | Remap to service failure |
| Listener called twice | Parent/child managers or multiple listeners? | Check double publishing and bean registration |
| Logins slow down after adding listener | Is the listener sending synchronous HTTP/SMTP? | Switch to fast processing/queue |
| Event logging leaks passwords | Logging entire Authentication/Exception? | Redact and allowlist fields |
| No event on HTTP 403 | That is authorization, not authentication | Handle AccessDenied separately |
| Adding Properties mapping triggers deprecation warning | Using legacy API? | Use `Map<Class,Class>` |
| Fallback not published | Unconfigured or invalid event constructor? | Use a valid concrete failure event |
| Single attempt yields multiple events | Multiple providers/managers or duplicate publication? | Test manager wiring directly |

## 18. Checklist for safe mapping design

1. Does the custom exception genuinely represent an **authentication failure**, or is it an authorization/business error?
2. Have the semantics been identified: bad credentials, locked, disabled, expired, service issue, or custom policy?
3. Which class is **actually thrown**? Are there new subclasses? Is there an exact mapping for it?
4. Is `DefaultAuthenticationEventPublisher` declared as a bean or attached to the right manager?
5. Does the concrete event class extend `AbstractAuthenticationFailureEvent` with a valid constructor?
6. Is typed `Map` used instead of deprecated `Properties`?
7. Does the fallback event catch omissions without mixing incompatible semantics?
8. Does the listener limit output and avoid logging credentials/tokens/PII or sensitive exception messages?
9. Could a slow/failing listener hurt authentication latency or propagate incidents?
10. Are HTTP failure handlers decoupled from event listeners with anti-enumeration protections?
11. Are real provider/manager integrations, parent/child duplication, and multi-node deployments tested?
12. Are mappings, event counts, HTTP statuses, and authorization tested separately?

**Conclusion:** When Spring Security publishes authentication events, **the exact exception class determines the failure event** via the mapping table. Because the default publisher **does not infer mappings from superclasses**, custom exceptions must be registered via `setAdditionalExceptionMappings(Map)` or handled by an explicitly designed fallback event. Pick events matching the failure's true nature, wire the publisher to the right `AuthenticationManager`, handle auditing safely, and test both mappings and live authentication paths to avoid missing events, skewed metrics, and sensitive data leaks.

### Official references

- Spring Security — Authentication Events (Servlet, 7.0): https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/events.html
- Spring Security — DefaultAuthenticationEventPublisher API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/DefaultAuthenticationEventPublisher.html
- Spring Security — AuthenticationEventPublisher API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationEventPublisher.html
- Spring Security — AbstractAuthenticationFailureEvent API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/event/AbstractAuthenticationFailureEvent.html
- Spring Security — AuthenticationFailureBadCredentialsEvent API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/event/AuthenticationFailureBadCredentialsEvent.html
- Spring Security — ProviderManager API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Framework — EventListener API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html

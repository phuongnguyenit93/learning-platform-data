# JAAS and Integrating Subject with the Spring Security Model

> **Scope:** JAAS (Java Authentication and Authorization Service) provides `LoginContext`, `LoginModule`, `Subject`, and `Principal` instances. Spring Security uses `AuthenticationManager`, `AuthenticationProvider`, `Authentication`, `SecurityContext`, and `GrantedAuthority`. This lesson explains the boundary between the two models, how to authenticate via JAAS and map permissions into Spring, when legacy code must execute under a JAAS Subject, and lifecycle/execution-context limitations. Java examples target JDK 17+; the Spring sections illustrate Spring Security 6.x on the Servlet stack.

## 1. What Do You Need to Understand?

After this lesson, you will be able to:

1. Describe the roles of `Configuration`, `LoginContext`, `LoginModule`, `CallbackHandler`, `Subject`, and `Principal`.
2. Distinguish **JAAS Subject** from **Spring Security Authentication**, and understand why the two objects are not directly interchangeable.
3. Choose `DefaultJaasAuthenticationProvider` or `JaasAuthenticationProvider` to bring an existing LoginModule into Spring Security's authentication chain.
4. Map JAAS group principals into `GrantedAuthority` via `AuthorityGranter` under an explicit policy.
5. Identify when `JaasApiIntegrationFilter` or `Subject.doAs` is required for libraries expecting a current Subject.
6. Control errors, credentials, login/logout, sessions, cross-thread context leaks, and WebFlux limitations.

JAAS is useful when an organization already has **Kerberos login modules, enterprise libraries, or legacy integration layers** relying on the JAAS mechanism. JAAS is not mandatory for every Spring application and does not by itself provide OAuth2/OIDC login, LDAP group mapping, or application authorization policies.

## 2. The Nature of JAAS: Subject and Multiple Principals

| Component | Purpose | Notes |
| --- | --- | --- |
| `LoginContext` | Looks up configuration name, runs `LoginModule`, invokes `login()`/`logout()`, and returns `Subject` | Not Spring's `SecurityContext` |
| `LoginModule` | Plugin executing concrete authentication, e.g., Kerberos or an enterprise backend | Not synonymous with Spring `AuthenticationProvider` |
| `CallbackHandler` | Supplies username/password/OTP or other data to LoginModule via callbacks | Should not re-prompt for passwords already collected by Spring |
| `Configuration` | Module list and flags `REQUIRED`, `REQUISITE`, `SUFFICIENT`, `OPTIONAL` | Flags govern how multiple modules combine |
| `Subject` | Collection of identities and credentials for an entity | Holds multiple `Principal` objects, not just a single username |
| `Principal` | An identifier: user, group, service principal, or Kerberos identity | A principal does not automatically become a Spring role |
| `Subject.getPrivateCredentials()` | Sensitive credentials | Never log, serialize, or push arbitrarily into sessions |

A `Subject` can hold `UserPrincipal("mai")`, `GroupPrincipal("report-readers")`, and a Kerberos principal simultaneously. Each principal represents one facet of identity. **Never take an arbitrary `principal.getName()` string and treat it as administrative permission.** You must know the exact principal class, which LoginModule produced it, and which authorization policy the organization approved.

### Two-Phase Login/Commit in JAAS

~~~text
Application calls LoginContext.login()
         |
         v
Configuration looks up LoginModule by context name
         |
         v
LoginModule.initialize(subject, callbackHandler, sharedState, options)
         |
         +-- login()  : verify credentials, record temporary state
         |
         +-- commit() : when overall auth succeeds, attach Principal
         |
         +-- abort()  : on failure, discard temporary state
         |
         v
LoginContext.getSubject() after successful login
         |
         +-- logout() : invoke cleanup for each LoginModule
~~~

`LoginContext` coordinates modules according to control flags. A module can return `false` (ignored), return `true` (succeeded), or throw `LoginException`. When overall login succeeds, successful modules execute `commit()` and add valid principals/credentials to the Subject. On failure, `abort()` must clean up state; an unauthenticated Subject must never carry roles as if logged in.

## 3. Comparing JAAS with Spring Security

| JAAS | Spring Security | How to Interpret |
| --- | --- | --- |
| `Subject` holding multiple `Principal` objects and credentials | `Authentication` carrying principal, credentials, authorities, authenticated flag | No direct type cast exists |
| `LoginContext.login()` | `AuthenticationManager.authenticate(...)` | One is the JAAS authentication API; the other is Spring's provider orchestration API |
| `LoginModule` | `AuthenticationProvider` | Spring provides a bridge provider to invoke LoginModules |
| `Subject.getPrincipals()` | `Authentication.getPrincipal()` | Spring has a primary principal; JAAS can carry multiple principal types |
| JAAS group principal | `GrantedAuthority` such as `ROLE_REPORT_READER` | Requires mapping via an explicit policy |
| `Subject.doAs` / current Subject | `SecurityContextHolder` or `ReactiveSecurityContextHolder` | Two independent context mechanisms |
| `LoginContext.logout()` | Session invalidation, logout handler, context clearing | Requires lifecycle coordination |

After Spring authentication succeeds, `SecurityContextHolder.getContext().getAuthentication()` holds the Spring `Authentication` for the current Servlet request. With a JAAS provider, the resulting token is typically `JaasAuthenticationToken` holding the `LoginContext`; if you need the Subject, obtain it via `token.getLoginContext().getSubject()`. **`Authentication.getPrincipal()` does not return `Subject` by default.**

There are two separate steps: **authentication** proves who the user is; **authorization** decides what the user may do. Having a group principal on a Subject does not mean every group is automatically granted as a Spring authority.

## 4. Data Flow When Spring Authenticates via JAAS

~~~text
Browser / API
    |
    v
Spring Security authentication filter
    |
    v
UsernamePasswordAuthenticationToken(username, password)
    |
    v
AuthenticationManager / ProviderManager
    |
    v
DefaultJaasAuthenticationProvider or JaasAuthenticationProvider
    |
    +-- JaasNameCallbackHandler / JaasPasswordCallbackHandler
    |                          |
    |                     LoginContext.login()
    |                          |
    |                     LoginModule(s)
    |                          |
    |                     Subject.getPrincipals()
    |                          |
    +------------------> AuthorityGranter(s)
                               |
                               v
                     JaasGrantedAuthority
                               |
                               v
                     JaasAuthenticationToken
                               |
                               v
                    Spring SecurityContext
                               |
                               v
                     hasRole / hasAuthority
~~~

Key classes:

- `AbstractJaasAuthenticationProvider` is the base for Spring's JAAS providers, supporting username/password token authentication and `LoginContext` interaction.
- `DefaultJaasAuthenticationProvider` accepts `javax.security.auth.login.Configuration` directly, fitting Spring-managed configuration and isolated tests.
- `JaasAuthenticationProvider` relies on file-based/Java-provider JAAS configuration; suited for applications already using `login.conf` and matching operations.
- `JaasNameCallbackHandler` and `JaasPasswordCallbackHandler` translate username/password fields from the Spring token into JAAS callbacks. OTP, smartcards, certificates, or other mechanisms may require custom handlers.
- `AuthorityGranter.grant(Principal)` evaluates each principal of the Subject after successful login and returns a set of authority strings; Spring creates corresponding `JaasGrantedAuthority` instances.

Spring remains responsible for `SecurityFilterChain`, CSRF, sessions, endpoint authorization, error responses, and logging. The provider is solely an **authentication bridge**, not a replacement for the entire security architecture.

## 5. Standalone Java 17 Example: LoginModule Creating a Subject

This example intentionally uses a fake username/password in a **learning environment**, without connecting to a real identity system or production password policy. It directly illustrates the two `login/commit` phases, reading principals, and logging out.

Create `JaasSubjectDemo.java`:

~~~java
import java.io.IOException;
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import javax.security.auth.Subject;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.FailedLoginException;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public final class JaasSubjectDemo {

    public record UserPrincipal(String name) implements Principal {
        @Override
        public String getName() {
            return name;
        }
    }

    public record GroupPrincipal(String name) implements Principal {
        @Override
        public String getName() {
            return name;
        }
    }

    public static final class DemoLoginModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private UserPrincipal user;
        private GroupPrincipal group;
        private boolean authenticated;

        public DemoLoginModule() {
        }

        @Override
        public void initialize(Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
        }

        @Override
        public boolean login() throws LoginException {
            if (handler == null) {
                throw new LoginException("CallbackHandler required");
            }
            NameCallback name = new NameCallback("User: ");
            PasswordCallback password = new PasswordCallback("Password: ", false);
            char[] received = null;
            try {
                handler.handle(new Callback[] {name, password});
                received = password.getPassword();
                boolean valid = "mai".equals(name.getName())
                        && Arrays.equals(received,
                                new char[] {'d', 'e', 'm', 'o'});
                if (!valid) {
                    throw new FailedLoginException("Invalid credentials");
                }
                user = new UserPrincipal("mai");
                group = new GroupPrincipal("report-readers");
                authenticated = true;
                return true;
            } catch (IOException | UnsupportedCallbackException ex) {
                throw new LoginException("Cannot process callbacks");
            } finally {
                if (received != null) {
                    Arrays.fill(received, '\0');
                }
                password.clearPassword();
            }
        }

        @Override
        public boolean commit() {
            if (!authenticated) {
                return false;
            }
            subject.getPrincipals().add(user);
            subject.getPrincipals().add(group);
            return true;
        }

        @Override
        public boolean abort() {
            return logout();
        }

        @Override
        public boolean logout() {
            if (user != null) {
                subject.getPrincipals().remove(user);
            }
            if (group != null) {
                subject.getPrincipals().remove(group);
            }
            user = null;
            group = null;
            authenticated = false;
            return true;
        }
    }

    public static void main(String[] args) throws LoginException {
        Configuration configuration = new Configuration() {
            @Override
            public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
                if (!"Demo".equals(name)) {
                    return null;
                }
                return new AppConfigurationEntry[] {
                    new AppConfigurationEntry(
                            DemoLoginModule.class.getName(),
                            AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                            Map.of())
                };
            }
        };

        CallbackHandler callbacks = values -> {
            for (Callback callback : values) {
                if (callback instanceof NameCallback name) {
                    name.setName("mai");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword(new char[] {'d', 'e', 'm', 'o'});
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        LoginContext context = new LoginContext("Demo", null,
                callbacks, configuration);
        context.login();

        Subject subject = context.getSubject();
        System.out.println("Login: OK");
        System.out.println("Principals: " + subject.getPrincipals().size());
        System.out.println("User: " + subject.getPrincipals(UserPrincipal.class)
                .iterator().next().getName());
        System.out.println("Group: " + subject.getPrincipals(GroupPrincipal.class)
                .iterator().next().getName());

        context.logout();
        System.out.println("After logout: " + subject.getPrincipals().size());
    }
}
~~~

Compile/run with JDK 17 or newer:

~~~bash
javac JaasSubjectDemo.java
java JaasSubjectDemo
~~~

Exact stdout matching the example:

~~~text
Login: OK
Principals: 2
User: mai
Group: report-readers
After logout: 0
~~~

Explanation: `LoginContext` selects `DemoLoginModule` by configuration name. `login()` reads callbacks and checks fake data; `commit()` adds the two principals to the Subject only when authentication succeeds. `logout()` removes the exact principals created by the module, leaving 0 principals on the example Subject. In a multi-module setup, never blindly remove principals managed by other modules.

**Limitation:** this is a pure-JDK JAAS example. It does **not** yet create a Spring `Authentication` or Spring authorities, performs no Kerberos/LDAP verification, and has no secure password storage. Never deploy `DemoLoginModule` in a real product.

## 6. AuthorityGranter: Converting Group Principals to Spring Authorities

Once `LoginContext.login()` succeeds, the Spring JAAS provider iterates `LoginContext.getSubject().getPrincipals()` and queries `AuthorityGranter` instances. Only accepted roles are converted into `JaasGrantedAuthority`.

Example where an application permits only two verified groups:

~~~java
import java.security.Principal;
import java.util.Set;
import org.springframework.security.authentication.jaas.AuthorityGranter;

public final class TrustedGroupAuthorityGranter implements AuthorityGranter {

    @Override
    public Set<String> grant(Principal principal) {
        if (!(principal instanceof JaasSubjectDemo.GroupPrincipal group)) {
            return Set.of();
        }
        return switch (group.getName()) {
            case "report-readers" -> Set.of("ROLE_REPORT_READER");
            case "report-writers" -> Set.of("ROLE_REPORT_WRITER");
            default -> Set.of();
        };
    }
}
~~~

This Spring Security class snippet **shares the same source/package as `JaasSubjectDemo` from the previous example**, or must import the corresponding principal type. For a production LoginModule, replace `JaasSubjectDemo.GroupPrincipal` with the **real group principal class emitted by the trusted module**. Never map permissions solely by `principal.getName()`, because a user principal could share the same name as a group.

| Principal | Mapping Result | Spring Expression |
| --- | --- | --- |
| Group principal `report-readers` | `ROLE_REPORT_READER` | `hasRole("REPORT_READER")` |
| Group principal `report-writers` | `ROLE_REPORT_WRITER` | `hasAuthority("ROLE_REPORT_WRITER")` |
| User principal named `report-readers` | Empty set | Does not automatically become a group role |
| Group outside allowlist | Empty set | Granted no permissions |
| Service principal / Kerberos principal | Depends on specific policy; unmapped by default | Must verify type and origin |

In default Spring configuration, `hasRole("REPORT_READER")` checks for authority `ROLE_REPORT_READER`. `AuthorityGranter` is not a way to invent new identities; it only maps **permissions** from existing JAAS principals after authentication.

**Keep least privilege intact:** unverified groups must not arbitrarily receive `ROLE_USER`. A user may authenticate successfully yet lack the required role; Spring returns an authorization denial rather than altering the login outcome.

## 7. Integrating an Existing LoginModule with DefaultJaasAuthenticationProvider

When the enterprise already has an approved `LoginModule` on the classpath, `DefaultJaasAuthenticationProvider` lets you avoid rewriting authentication.

Gradle Groovy dependencies in a Spring Boot Servlet application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

JAAS belongs to the JDK, and the Spring JAAS adapter belongs to Spring Security. If the LoginModule resides in an internal library, add that library's dependency and configure callbacks/options per its contract.

File `JaasBridgeConfiguration.java` (configuration snippet in a Spring project):

~~~java
package example.security;

import java.util.Map;
import javax.security.auth.login.AppConfigurationEntry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.authentication.jaas.AuthorityGranter;
import org.springframework.security.authentication.jaas.DefaultJaasAuthenticationProvider;
import org.springframework.security.authentication.jaas.memory.InMemoryConfiguration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JaasBridgeConfiguration {

    @Bean
    DefaultJaasAuthenticationProvider jaasProvider(
            Environment properties, AuthorityGranter trustedGroupGranter) {
        String loginModuleClass =
                properties.getRequiredProperty("app.jaas.login-module-class");

        AppConfigurationEntry entry = new AppConfigurationEntry(
                loginModuleClass,
                AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                Map.of());

        DefaultJaasAuthenticationProvider provider =
                new DefaultJaasAuthenticationProvider();
        provider.setLoginContextName("LegacyBridge");
        provider.setConfiguration(new InMemoryConfiguration(
                Map.of("LegacyBridge", new AppConfigurationEntry[] {entry})));
        provider.setAuthorityGranters(
                new AuthorityGranter[] {trustedGroupGranter});
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            DefaultJaasAuthenticationProvider jaasProvider) throws Exception {
        return http
                .authenticationProvider(jaasProvider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**", "/login", "/error")
                        .permitAll()
                        .requestMatchers("/reports/**")
                        .hasRole("REPORT_READER")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

How it works:

- `app.jaas.login-module-class` is a deployment setting holding the **fully qualified class name of a real LoginModule**, supplied strictly by administrators; never read it from requests or queries. The module must have a no-arg constructor and implement `javax.security.auth.spi.LoginModule`.
- The `AuthorityGranter` bean is registered separately by the application (e.g., annotating the mapper class from section 6 with `@Component` after adjusting its package). The real module must emit the exact group principal class checked by the granter.
- `InMemoryConfiguration` defines context name `LegacyBridge`, which must match `provider.setLoginContextName("LegacyBridge")`. This lets you inject an isolated JAAS configuration rather than relying on global JVM settings.
- Spring's `formLogin` submits a `UsernamePasswordAuthenticationToken` to the provider chain. The JAAS provider uses name/password callbacks to invoke `LoginContext.login()` and translates principals/authorities into a Spring authentication token.
- `requestMatchers("/reports/**").hasRole("REPORT_READER")` grants access only when `ROLE_REPORT_READER` is actually present. Successful authentication without the role is still denied.

This bean snippet is not yet a standalone runnable program: it **requires a production LoginModule, matching callbacks, a credential source, an authority policy, and a Spring Boot application**. Never wire a demo module with hardcoded passwords into production just to test the flow.

### JaasAuthenticationProvider with a JAAS Config File

A traditional `login.conf` file may look like:

~~~text
LegacyBridge {
    company.security.EnterpriseLoginModule required;
};
~~~

`company.security.EnterpriseLoginModule` in the sample is an **organization-provided class name**, not a built-in JDK class. `JaasAuthenticationProvider` offers `setLoginConfig(Resource)` and `setLoginContextName(...)` for file-based integration. In multi-application deployments, JVM-wide JAAS configuration can be hard to isolate; verify where the config comes from, file edit permissions, and impact on other modules.

## 8. JAAS LoginException Does Not Automatically Become BadCredentialsException

JAAS typically reports authentication or infrastructure errors via `javax.security.auth.login.LoginException`, including the `FailedLoginException` subclass. Spring expects an `AuthenticationException` to handle failures. In Spring Security JAAS, `DefaultLoginExceptionResolver` **wraps JAAS errors into `AuthenticationServiceException` by default**, so never assume a wrong password automatically turns into `BadCredentialsException`.

You can supply a `LoginExceptionResolver` when a module has an explicit error contract:

~~~java
import javax.security.auth.login.FailedLoginException;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.jaas.LoginExceptionResolver;

LoginExceptionResolver resolver = exception -> {
    if (exception instanceof FailedLoginException) {
        return new BadCredentialsException("Invalid credentials");
    }
    return new AuthenticationServiceException("JAAS login service failed",
            exception);
};
~~~

Attach the resolver to the provider bean via `provider.setLoginExceptionResolver(resolver)`. This snippet is valid only if the **specific LoginModule consistently uses `FailedLoginException` for invalid credentials**. A module that throws that subclass for KDC/network loss needs its classification fixed in the module. Never inspect `exception.getMessage()` substrings to make authorization decisions.

Semantic mapping table:

| Actual Outcome | Desired Spring Handling |
| --- | --- |
| Wrong username/password per backend | `BadCredentialsException` if confirmed by the module contract |
| Locked/expired account | Appropriate status exception if the module distinguishes it |
| Kerberos KDC failure, directory unavailable, timeout | `AuthenticationServiceException` or infrastructure error type |
| Missing module, wrong login context name, unsupported callback | Configuration/system error; never issue an authenticated token |
| Login succeeds, yet group is not permitted | Authentication succeeds; authorization blocks missing permission |
| Any exception during authentication | **Fail closed**: never implicitly grant principals/roles |

Actual HTTP 401/403/5xx responses depend on login failure handlers, entry points, and API rules. Never expose raw exception messages, passwords, Kerberos tickets, Subjects, stack traces, or private credentials to users.

## 9. Subject.doAs and JaasApiIntegrationFilter

Some legacy libraries do not take a user parameter directly, instead reading the **current JAAS Subject** while processing data. In such cases, Spring `Authentication` handles framework-level authentication/authorization, while legacy code may still need the `Subject`.

JDK 17 example inside a **method that already has `subject` and `legacyService` variables**:

~~~java
import java.security.PrivilegedAction;
import javax.security.auth.Subject;

String output = Subject.doAs(subject,
        (PrivilegedAction<String>) () -> legacyService.readData());
~~~

`Subject.doAs` creates a synchronous execution scope under the given Subject. It does **not** turn Spring's `SecurityContext` into a Subject, nor does it automatically grant Spring roles. In Java 17 this API still works; starting in JDK 18 it is marked deprecated-for-removal. `Subject.getSubject(AccessController.getContext())` has been deprecated-for-removal since JDK 17. JDK 18+ adds `Subject.current()` and `Subject.callAs(...)`; when upgrading JDKs, verify how legacy libraries access the Subject and check compatibility rather than relying on the Java Security Manager as an always-available security feature.

### Filter Integrating Subject with Servlet

Spring Security provides `org.springframework.security.web.jaasapi.JaasApiIntegrationFilter`. The filter locates the `Subject` of the current `JaasAuthenticationToken` and runs the downstream `FilterChain` under that Subject, enabling both:

~~~text
Spring SecurityContext: Authentication + GrantedAuthority
JAAS current Subject:  UserPrincipal + GroupPrincipal (+ credentials)
~~~

This filter is **optional**; only include it when downstream code genuinely requires a current Subject. Place it in `SecurityFilterChain` after Spring has authenticated the request before legacy code reads the Subject, and test with real requests. If a request has no JAAS token, the filter cannot fabricate an authenticated Subject.

For WebFlux, `JaasApiIntegrationFilter` is a Servlet `Filter`, not a `WebFilter`. Do not place it in a reactive stack expecting Reactor to preserve Subject across scheduler switches.

## 10. Context Propagation Limits Across Threads, Reactive, and Jobs

Subject scope inside `doAs` is tied to Java execution context; Spring's `SecurityContextHolder` on Servlet is typically thread-bound, whereas `ReactiveSecurityContextHolder` uses Reactor Context. These mechanisms are **different**.

~~~text
Authenticated HTTP thread
    |
    +-- Subject.doAs(subject, synchronous code)
    |       -> legacy API can read current Subject
    |
    +-- CompletableFuture / ExecutorService
    |       -> different thread; neither Subject nor SecurityContext is guaranteed
    |
    +-- WebFlux / Reactor publishOn
            -> different thread; Reactor Context is not automatically a JAAS Subject
~~~

Wrappers like `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` can propagate **Spring SecurityContext** in certain Servlet async flows, yet they do not automatically carry the JAAS Subject too. To propagate a Subject across async tasks, explicitly define controlled propagation, lifecycle, and cleanup; avoid copying private credentials into thread pools or message queues.

An older `LoginModule` may be synchronous and wait on network I/O (KDC, LDAP, HTTP). In WebFlux, placing blocking login directly on the event loop stalls requests; integration requires isolating blocking calls onto a dedicated scheduler with timeouts and concurrency bounds. `Mono.just(loginContext.login())` does not make a blocking call non-blocking. Usually, only use the JAAS bridge when a specific legacy need exists; new reactive applications should consider reactor-compatible authentication managers and drivers.

## 11. Logout Lifecycle and Resource Cleanup

A `LoginContext` normally serves **a single login**. `LoginModule` implementations may create principals, sessions, or tickets; `LoginContext.logout()` triggers cleanup. Logging out of Spring and logging out of JAAS are two related contracts that must be verified separately.

Spring's JAAS provider listens for `SessionDestroyedEvent`: when a destroyed session holds a context with `JaasAuthenticationToken`, the provider can invoke `LoginContext.logout()`. However, never assume that closing a browser tab, deleting a cookie, or stateless/JWT setups trigger identical cleanup. Test actual logout, session expiration, session registries, event publishers, and LoginModule behavior.

Risks to control:

- A Subject or LoginContext shared between two users inside a thread pool.
- Credentials/tickets lingering in memory long after a session ends.
- Logging out one session breaking another session because a module manages process-wide resources.
- A LoginModule adding principals when `login()` fails or `abort()` failing to clean up.
- Spring's session being cleared while a legacy library still holds a reference to a privileged Subject.
- Directory group changes not affecting existing sessions because authorities are cached for the session lifetime.

## 12. When to Use JAAS vs. Another Integration?

| Scenario | Appropriate Choice |
| --- | --- |
| Existing JAAS-standard LoginModule that must be reused | `DefaultJaasAuthenticationProvider` / `JaasAuthenticationProvider` |
| Kerberos/legacy library requiring a current Subject | JAAS bridge + tightly scoped Subject execution |
| New application signing in via OIDC | `oauth2Login` / OIDC, do not route through JAAS by default |
| REST API protected by access tokens | Spring OAuth2 Resource Server validating tokens |
| Standard username/password authentication via JDBC or LDAP | Dedicated `AuthenticationProvider` when appropriate |
| End-to-end non-blocking WebFlux | Reactive `AuthenticationManager` and matching drivers; weigh blocking JAAS overhead |
| Simply assigning roles to users | Use `GrantedAuthority` and Spring policies; never fabricate a Subject for this |

JAAS primarily solves integrating an **existing login/caller-identity mechanism**, while Spring Security remains the coordinator for HTTP request security, method security, and authorization rules.

## 13. Testing the Right Boundaries and Avoiding Accidental Privilege Grants

**Testing JAAS (independent of Spring):**

- `LoginContext.login()` succeeds with valid test credentials; Subject contains the expected principals.
- Invalid credentials throw an error, leaving no valid principals or credentials after `abort()`.
- Each user gets an independent Subject/LoginContext when running concurrently.
- `logout()` removes only principals created by that module, leaving state from other modules untouched.
- Misconfigured context/module/class names fail with configuration errors instead of allowing login.

**Testing the Spring JAAS bridge:**

- `AuthenticationManager.authenticate(...)` returns the right token; `JaasAuthenticationToken` holds a LoginContext with a valid Subject.
- `AuthorityGranter` grants roles only for the right principal class **and** allowlisted group, never granting roles from a username matching a group name.
- Same user: can log in successfully yet receives 403 when lacking `ROLE_REPORT_READER`.
- Wrong passwords and KDC/backend errors are classified accurately per module contract rather than lumped together.
- Verify login failure handlers, session fixation protection, logout, expiration, concurrent sessions, auditing, and zero credential leaks.
- If `JaasApiIntegrationFilter` is enabled, downstream legacy APIs receive the right user's Subject, and anonymous requests never receive a privileged Subject.
- If executors or WebFlux are used, test context propagation and confirm identities never bleed across requests.

JUnit 5 unit test example for the granter from section 6, placed in the matching package/test source:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TrustedGroupAuthorityGranterTest {
    private final TrustedGroupAuthorityGranter granter =
            new TrustedGroupAuthorityGranter();

    @Test
    void onlyTrustedGroupGetsRole() {
        assertEquals(java.util.Set.of("ROLE_REPORT_READER"),
                granter.grant(new JaasSubjectDemo.GroupPrincipal("report-readers")));
        assertTrue(granter.grant(
                new JaasSubjectDemo.UserPrincipal("report-readers")).isEmpty());
        assertTrue(granter.grant(
                new JaasSubjectDemo.GroupPrincipal("unknown")).isEmpty());
    }
}
~~~

In a project with JUnit 5 and the Gradle wrapper:

~~~bash
./gradlew test --tests TrustedGroupAuthorityGranterTest
~~~

If the classes reside in package `example.security`, declare the corresponding package/imports and pass the fully qualified test name. Expected result: JUnit passes with no required stdout. This unit test only proves allowlist mapping; you still need integration tests with a real LoginModule, JAAS provider, HTTP filters, and backend.

## 14. Production Checklist

- [ ] Genuine need for JAAS confirmed; exact LoginModule, callbacks, package/class, and Subject creation verified.
- [ ] LoginModule uses a trusted identity source; no hardcoded passwords or demo modules for real users.
- [ ] Context name and `Configuration` fixed in trusted deployment configuration; never accept LoginModule names from requests.
- [ ] Never grant roles from `Principal.getName()` without checking principal class and group allowlist.
- [ ] `AuthorityGranter`, `hasRole`/`hasAuthority`, login failure handling, and session policy tested together.
- [ ] `LoginExceptionResolver` accurately distinguishes bad credentials, account status, and backend/config errors; all errors fail closed.
- [ ] Current JAAS Subject provided only when genuinely required, with filter/`doAs` strictly scoped.
- [ ] For async/WebFlux, never assume Subject or Spring SecurityContext propagates automatically across threads.
- [ ] Logout/session destruction/timeout and LoginModule cleanup tested for both success and failure paths.
- [ ] Private credentials, password callbacks, Kerberos tickets, or full Subjects are never logged, serialized, or returned.
- [ ] Deprecated JAAS APIs reviewed across JDK upgrades and blocking LoginModule performance measured.

**Key takeaway:** JAAS **authenticates through a LoginModule and constructs a Subject holding multiple Principals**; Spring Security **protects requests with `Authentication` and `GrantedAuthority`**. `DefaultJaasAuthenticationProvider`/`JaasAuthenticationProvider` together with `AuthorityGranter` bridge the two models. `JaasApiIntegrationFilter` is needed only for legacy code that genuinely consumes the current JAAS Subject. Security relies on trusted principal sources, bounded mapping, lifecycle cleanup, and execution-context hygiene.

## Reference Documentation

- [Spring Security 6.5 — JAAS Authentication Provider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/jaas.html)
- [Spring Security 6.5 — AbstractJaasAuthenticationProvider API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/jaas/AbstractJaasAuthenticationProvider.html)
- [Spring Security 6.5 — DefaultJaasAuthenticationProvider API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/jaas/DefaultJaasAuthenticationProvider.html)
- [Spring Security 6.5 — AuthorityGranter API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/jaas/AuthorityGranter.html)
- [Spring Security 6.5 — DefaultLoginExceptionResolver API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/jaas/DefaultLoginExceptionResolver.html)
- [Java 17 — LoginContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html)
- [Java 17 — LoginModule API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html)
- [Java 21 — Subject API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/Subject.html)

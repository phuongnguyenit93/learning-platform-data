# No AuthenticationProvider Found for the Input Token Type

## 1. Exact Meaning of the Error

In Spring Security, `AuthenticationManager` is the entry point that receives authentication requests. The commonly used implementation is `ProviderManager`: it inspects the configured `AuthenticationProvider` instances in order. A provider should only examine the types of `Authentication` objects it understands. If no provider can handle the request token, the application may throw:

~~~text
org.springframework.security.authentication.ProviderNotFoundException:
No AuthenticationProvider found for
demo.security.DeviceOtpAuthenticationToken
~~~

The class name above is an example. The actual message usually specifies the **fully qualified Java class** of the input token. This is **different** from a wrong password, wrong OTP, expired JWT access token, or locked account: first and foremost, this indicates **the request type is incompatible with the set of providers in the manager being called**.

Example:

~~~text
POST /mfa/verify
      |
      v
DeviceOtpFilter
  -> new DeviceOtpAuthenticationToken(challengeId, code)
      |
      v
AuthenticationManager.authenticate(request)
      |
      v
ProviderManager [
    DaoAuthenticationProvider,
    RememberMeAuthenticationProvider
]
      |
      +-- Dao supports OTP request? false
      +-- RememberMe supports OTP request? false
      +-- Parent manager? None / cannot handle
      |
      v
ProviderNotFoundException
~~~

Even if the Spring context has `UserDetailsService`, `PasswordEncoder`, and other security beans, those components **do not automatically create a provider capable of verifying a custom OTP token**. Do not "fix" the error by skipping authentication or marking the token `authenticated=true` from client data.

An important note: `ProviderNotFoundException` does not appear only when every `supports(...)` returns false. A provider can return `null` after evaluating a request, and if no other provider/parent produces a result, the manager still cannot authenticate the request. Therefore, you must check both **capability** and **the result of `authenticate`**.

## 2. Distinguishing Authentication, Provider, and Manager

| Component | Responsibility | What to Check |
|---|---|---|
| `Authentication` | Java object representing a request or result: principal, credentials, authorities, authenticated state. | `authentication.getClass().getName()`, `isAuthenticated()`. |
| `AuthenticationProvider` | Knows how to verify one or a few Authentication types. | `supports(Class<?>)` and `authenticate(Authentication)`. |
| `AuthenticationManager` | API that performs authentication. | The manager instance called by the filter/controller. |
| `ProviderManager` | Tries providers in order; can consult a parent manager. | `getProviders()`, provider order, parent wiring. |
| `SecurityFilterChain` | Selects which filters run on a Servlet request. | `securityMatcher`, `@Order`, filter mechanism/manager. |
| `AuthenticationManagerResolver` | Selects a manager per request/tenant/issuer when the app uses dynamic routing. | Resolver rules, actual manager selected. |
| `SecurityContext` | Holds the authenticated result for the request/session. | Must not create authorities from input not yet verified by a provider. |

**A Java Authentication token is different from an OAuth2 access token.** `UsernamePasswordAuthenticationToken` is a class carrying username/password. `BearerTokenAuthenticationToken` is a class carrying a bearer credential for a provider to verify. `JwtAuthenticationToken` is typically **the result after a JWT has been decoded and verified**; do not put a client-created object named `JwtAuthenticationToken` into `SecurityContext` and treat it as having a verified signature.

A successful login requires all layers to coordinate:

~~~text
HTTP form/header/body
      |
      v
Servlet security filter / authentication converter
      |
      v
Authentication request object
      |
      v
Manager picks an AuthenticationProvider
      |
      v
Verify credentials/token/challenge
      |
      v
Authenticated Authentication result
      |
      v
SecurityContext and authorization checks
~~~

If the filter constructs the wrong class, the manager may skip all providers even when the credential is valid in business terms.

## 3. The `AuthenticationProvider.supports` Contract

The core Java interface looks like this:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

According to the Spring Security Javadoc, `supports` returns true when the provider **can evaluate the request token type further**; returning true **does not guarantee** authentication will succeed.

Inside `authenticate(...)`, a provider has three options:

1. Return a non-null, verified `Authentication` result.
2. Return `null` if the provider cannot decide on this instance and wants to defer to another provider.
3. Throw an appropriate `AuthenticationException` when the credential is invalid, the account is locked, the backend fails, or other policies apply.

For a custom token:

~~~java
@Override
public boolean supports(Class<?> authentication) {
    return DeviceOtpAuthenticationToken.class
            .isAssignableFrom(authentication);
}
~~~

This is the **correct `isAssignableFrom` direction** if you want to support this class and its subclasses. For a system that only supports one exact concrete class, you can choose:

~~~java
@Override
public boolean supports(Class<?> authentication) {
    return DeviceOtpAuthenticationToken.class.equals(authentication);
}
~~~

Do not use:

~~~java
// Bad design if the provider only understands OTP:
@Override
public boolean supports(Class<?> authentication) {
    return true;
}
~~~

An overly broad predicate can cause the provider to receive JWT, form password, or remember-me tokens it does not understand; easily causing `ClassCastException`, mishandling credentials, or granting unintended authorities. Do not call `setAuthenticated(true)` in a constructor receiving HTTP requests just to bypass provider selection.

## 4. How Does `ProviderManager` Decide the Result?

Conceptual flow:

~~~text
Authentication request -> ProviderManager
  For each provider in configured order:
     if provider.supports(request.getClass()):
        result = provider.authenticate(request)
        if result is non-null -> success, stop
        if result is null     -> try another
        if AuthenticationException -> handle under manager rules
  If no successful provider:
     optionally consult parent AuthenticationManager
  If still no result:
     propagate relevant failure exception
     or throw ProviderNotFoundException
~~~

This is **pseudocode**, not an exact copy of a specific version's source. The `ProviderManager` Javadoc notes the following cases:

- An earlier provider may throw an error and a later provider may authenticate successfully; the later provider's success result can win.
- If no provider succeeds, the last relevant exception may be used.
- `AccountStatusException` subclasses such as `LockedException`/`DisabledException` are handled specially; you should not try fallbacks to bypass account-status policy.
- A parent manager can be consulted when local providers do not resolve the request under the contract.

Therefore, four kinds of problems must be distinguished:

| Error | Symptom | Root-Cause Direction |
|---|---|---|
| `ProviderNotFoundException` | No provider produced a suitable handling result for the token. | Token Java type, provider list, manager/chain, supports/return null. |
| `BadCredentialsException` | A provider accepted the request, but credentials are invalid. | Verifier/password/OTP/bearer value; do not add arbitrary providers. |
| `DisabledException`, `LockedException` | Account status forbids authentication. | Account lifecycle/recovery; do not bypass. |
| `AuthenticationServiceException` | Backend/provider could not process due to a service error. | DB/LDAP/IdP/network; fail closed. |

An HTTP `401` can originate from any of these branches or because the request sent no credentials; do not infer from the status code and ignore the exception class.

## 5. Common Token/Provider Pairs

| Request Authentication Type | Typical Supporting Provider/Mechanism | Notes |
|---|---|---|
| `UsernamePasswordAuthenticationToken` | `DaoAuthenticationProvider`, `LdapAuthenticationProvider`, and matching password providers. | Form login/HTTP Basic typically use this type. |
| `BearerTokenAuthenticationToken` | `JwtAuthenticationProvider` or `OpaqueTokenAuthenticationProvider`. | Usually created by `BearerTokenAuthenticationFilter`. |
| `PreAuthenticatedAuthenticationToken` | `PreAuthenticatedAuthenticationProvider`. | Requires an upstream trust boundary; do not trust user headers self-declared from the Internet. |
| `RememberMeAuthenticationToken` | `RememberMeAuthenticationProvider`. | Relies on remember-me trust/key policy, not a fresh password. |
| `AnonymousAuthenticationToken` | `AnonymousAuthenticationProvider` in paths that have a corresponding manager. | Anonymous is not an authenticated human login. |
| `OAuth2LoginAuthenticationToken` | `OAuth2LoginAuthenticationProvider` for the client login flow. | Does not automatically provide resource-server JWT support. |
| `Saml2AuthenticationToken` | SAML provider depending on the Spring Security SAML module/config. | Must verify response, issuer, signature, and audience. |
| Custom `DeviceOtpAuthenticationToken` | Custom `DeviceOtpAuthenticationProvider`. | Needs challenge/session/purpose binding and replay protection. |

**Do not conflate input and output.** A Bearer JWT request can be processed into a `JwtAuthenticationToken` after `JwtDecoder`, while a custom provider may return a result class different from the request class. A common mistake is manually constructing a result token from user input and putting it into `SecurityContext`, thinking that having "Jwt" or "Authenticated" in the name means Spring will trust it.

If the exception says no provider was found for `UsernamePasswordAuthenticationToken` even though you sent an `Authorization: Bearer` header, it is very likely that **a filter/custom converter created the wrong token type** or the request hit the wrong chain.

## 6. Step-by-Step Diagnostics: Token, Manager, Provider, Chain

Follow these steps in order without relaxing access controls mid-way:

1. Record the **exception class and token class** in `No AuthenticationProvider found for ...`; do not log credentials.
2. Identify the endpoint/method, the credential type the user is sending, and where the request arrives after ingress/proxy.
3. Identify the filter or controller that **creates the `Authentication` object**.
4. Print the **request class** right before `AuthenticationManager.authenticate(...)`; do not use `toString()`.
5. Identify the **manager instance** that code calls; do not just look for a bean named `authenticationManager`.
6. If it is a `ProviderManager`, inspect its `getProviders()` list, order, and parent manager created by config.
7. For each provider, evaluate `supports(request.getClass())` **without calling `authenticate` to probe**.
8. When `supports` is true, check whether the provider returns non-null, returns `null`, or throws an exception.
9. Check which Servlet `SecurityFilterChain` matches the request, `@Order` values, and which filters are added.
10. Fix the token/provider type properly and add tests for success, wrong credentials, disabled status, and the missing-provider path.

Safe logging snippet:

~~~java
// Integration snippet: variables auth, manager, log must already be available.
log.debug("authenticationRequestType={}",
        auth.getClass().getName());
log.debug("authenticationManagerType={}",
        manager.getClass().getName());
~~~

If you have an actual `ProviderManager`:

~~~java
if (manager instanceof ProviderManager pm) {
    for (AuthenticationProvider p : pm.getProviders()) {
        log.debug("providerClass={} supportsRequest={}",
                p.getClass().getName(),
                p.supports(auth.getClass()));
    }
}
~~~

These snippets are **integration code** and require real imports/objects. **Do not log** `auth.getCredentials()`, password/OTP, raw JWT, token headers, session cookies, the full `Authentication`, or exception messages containing secrets. Do not call `p.authenticate(auth)` just to "try" each provider; that could consume an OTP, lock an account, or call an IdP.

## 7. Cause A: Filter Creates the Wrong Token Class

A filter receives an OTP:

~~~json
{
  "challengeId": "ch-204",
  "code": "123456"
}
~~~

but the code creates:

~~~java
Authentication request = new UsernamePasswordAuthenticationToken(
        challengeId, code);
~~~

When `DaoAuthenticationProvider` is present, it may treat the request as **username/password** and return `BadCredentialsException`. That is not a no-provider error, yet it is still a design flaw: `challengeId` is not a username and `code` is not a password.

If you change the filter to create `DeviceOtpAuthenticationToken` without a provider for that class, the manager can throw `ProviderNotFoundException`. The right direction is to create a request class with clear semantics **and** add a provider that verifies the challenge against an unexpired account/session/purpose, attempt limits, replay protection, and a transaction.

**Do not:** use `UsernamePasswordAuthenticationToken` for OTP just to fit `DaoAuthenticationProvider`; or construct an already-authenticated `JwtAuthenticationToken` from client-supplied claims and place it into `SecurityContext`.

## 8. Cause B: Provider Bean Exists, but Manager Does Not Know About It

For example, the project declares:

~~~java
@Bean
AuthenticationProvider deviceOtpProvider(
        ChallengeVerifier verifier) {
    return new DeviceOtpAuthenticationProvider(verifier);
}
~~~

but the custom filter uses a manually constructed manager:

~~~java
AuthenticationManager local = new ProviderManager(
        List.of(daoAuthenticationProvider));
~~~

The `local` manager only sees the DAO provider. The mere existence of a `deviceOtpProvider` bean does not mean it is automatically added to every `ProviderManager` the application instantiates manually.

Questions to ask:

- Are there multiple `AuthenticationManager` beans/instances?
- Are you using the global manager from `AuthenticationConfiguration.getAuthenticationManager()` while the provider was registered on a different chain-local `HttpSecurity`?
- Did you call `HttpSecurity.authenticationProvider(...)` on the chain serving the right endpoint?
- Is the `@Configuration` defining the provider properly component-scanned/imported, or excluded by a profile?
- Does a test mock bean disable `supports` or replace the provider unintentionally?
- Is there a parent manager, and does it have the required provider?

**You must inspect the manager actually called by the filter**, not infer from dependencies in `pom.xml` or bean names. A wrong fix is registering a provider that supports too many token types into the global manager without scoping control, causing APIs to accidentally accept disallowed login mechanisms.

## 9. Cause C: Endpoint Falls Into the Wrong SecurityFilterChain

An application may have multiple Servlet chains:

~~~java
// Spring Security 6 snippet, requires corresponding imports and JwtDecoder:
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
        .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain website(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

This is **code illustrating two beans in one configuration**, not a complete app. `FilterChainProxy` selects a chain by `securityMatcher`/order; `/api/mfa/verify` might enter the API chain that only has a JWT provider. If a custom OTP filter on the API chain calls this manager, it may not support the OTP request class.

Distinguish among:

- **Chain ordering:** `@Order(1)`/`@Order(2)` and matchers.
- **Filter ordering:** custom filter placement before/after `BearerTokenAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`.
- **Manager wiring:** which manager the custom filter uses after the chain is built.
- **Actual request path:** does a proxy rewrite `/auth` or `/api`?
- **Public endpoints:** do challenge-issue/verify endpoints require anonymous access, a partial session, or already-authenticated state? Do not attach `.anyRequest().authenticated()` and end up blocking the login flow itself.

Do not fix by using `anyRequest().permitAll()` or disabling Spring Security. That removes enforcement instead of fixing the mismatch.

## 10. Cause D: `supports` Has Reversed Direction or Returns True Too Broadly

This is a correct example:

~~~java
@Override
public boolean supports(Class<?> type) {
    return DeviceOtpAuthenticationToken.class.isAssignableFrom(type);
}
~~~

Reversing the direction can produce false positives:

~~~java
// Wrong if it needs to match DeviceOtpToken and subclasses:
return type.isAssignableFrom(DeviceOtpAuthenticationToken.class);
~~~

When a parent class like `AbstractAuthenticationToken` is passed, the reversed check can return true while the provider does not actually support every subclass token. Use `equals` when only an exact class is supported.

Another case: the provider returns `true`, but `authenticate` casts the token and throws `ClassCastException`. That is a **code/provider contract bug**, not `BadCredentialsException`; the manager may not handle it as a controlled authentication failure.

Do not fix by doing:

~~~java
// Never skip credential verification just to make tests pass:
if (!supports(request.getClass())) {
    return UsernamePasswordAuthenticationToken.authenticated(
            "admin", null, adminAuthorities);
}
~~~

An authentication result **must only be created after a trusted verifier actually confirms it**. Even in an internal app, a "self-authenticated" fallback is a severe bypass.

## 11. Cause E: `supports=true` but `authenticate` Returns Null

Example of a multi-tenant provider:

~~~java
@Override
public Authentication authenticate(Authentication authentication) {
    DeviceOtpAuthenticationToken request =
            (DeviceOtpAuthenticationToken) authentication;

    if (!belongsToThisTenant(request)) {
        return null;
    }
    // Verify credential and return trusted result...
}
~~~

This is an intentional pattern when **other providers also understand the request class**. If every provider returns null, the manager has no result. If a provider already checked the OTP and it was wrong, it should throw `BadCredentialsException` rather than returning null so a less strict provider could try next.

Rules to lock down:

- `null` = the provider cannot take responsibility for **this** request.
- `BadCredentialsException` = the verifier determined the credential is invalid.
- `DisabledException`/`LockedException` = account state prevents authentication.
- `AuthenticationServiceException` = the backend cannot process the request.
- Non-null authenticated result = verified successfully with proper scope.

If multiple providers support the same type, their order and fallback must be threat-modeled so a user from tenant A cannot be authenticated by tenant B's provider or a lower-assurance provider.

## 12. Integration Demo: Custom OTP Request Token

In Spring Security 6, a custom request token can extend `AbstractAuthenticationToken`:

~~~java
package demo.security;

import org.springframework.security.authentication.AbstractAuthenticationToken;

public final class DeviceOtpAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String challengeId;
    private String code;

    public DeviceOtpAuthenticationToken(
            String challengeId, String code) {
        super(null);
        this.challengeId = challengeId;
        this.code = code;
        super.setAuthenticated(false);
    }

    @Override
    public Object getPrincipal() {
        // challengeId is not yet an authenticated identity.
        return challengeId;
    }

    @Override
    public Object getCredentials() {
        return code;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        code = null;
    }
}
~~~

This is a request class for **framework integration**, not a complete OTP server implementation. The initial state **must be unauthenticated**. Storing OTP as a `String` still has limitations because `String` is immutable; in production, minimize its lifetime, avoid logging, limit credentials in memory, and use erasable structures where appropriate.

When the OTP verification flow is a **step-up step** on an already logged-in session, the request token must bind the challenge to the user/session/purpose via a server-side store. Never take a subject self-declared in client JSON and treat it as an authenticated user.

## 13. Integration Demo: Matching Provider and Verifier Contract

~~~java
package demo.security;

import java.util.Collection;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;

public final class DeviceOtpAuthenticationProvider
        implements AuthenticationProvider {

    private final ChallengeVerifier verifier;

    public DeviceOtpAuthenticationProvider(ChallengeVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public boolean supports(Class<?> type) {
        return DeviceOtpAuthenticationToken.class
                .isAssignableFrom(type);
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {
        DeviceOtpAuthenticationToken request =
                (DeviceOtpAuthenticationToken) authentication;

        VerifiedIdentity verified = verifier.verifyAndConsume(
                (String) request.getPrincipal(),
                (String) request.getCredentials());

        if (verified == null) {
            throw new BadCredentialsException(
                    "Invalid authentication challenge");
        }

        Collection<? extends GrantedAuthority> authorities =
                verified.authoritiesFromTrustedRepository();

        return UsernamePasswordAuthenticationToken.authenticated(
                verified.internalPrincipal(), null, authorities);
    }
}
~~~

`ChallengeVerifier` and `VerifiedIdentity` are **domain contracts the application must implement**, not Spring APIs. A real verifier must check OTP/signature, challenge expiry, subject/session/purpose, attempts, replay, atomic consumption, and account status; the illustrative implementation **is not sufficient on its own for production**.

Having the provider return an authenticated result of type `UsernamePasswordAuthenticationToken` is valid under the interface, though an MFA system may prefer returning a dedicated token carrying verified assurance/purpose to avoid conflating OTP success with password success. Authorities must come from a trusted repository, **not** from the client or an arbitrary `challengeId`.

## 14. Registering the Provider in the Right Manager or Chain

Spring Boot 3 / Spring Security 6 example:

~~~java
@Bean
DeviceOtpAuthenticationProvider deviceOtpProvider(
        ChallengeVerifier verifier) {
    return new DeviceOtpAuthenticationProvider(verifier);
}

@Bean
SecurityFilterChain otpChain(HttpSecurity http,
        DeviceOtpAuthenticationProvider otpProvider) throws Exception {
    http.securityMatcher("/mfa/**")
        .authenticationProvider(otpProvider)
        .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

    return http.build();
}
~~~

This is **not yet a complete application**: you need a custom filter creating `DeviceOtpAuthenticationToken` and **a manager that has this provider**, CSRF, error handling, and a cookie/session or stateless contract. For enrollment/verify endpoints, you may need to allow **partial authentication** to avoid blocking the MFA step itself; do not copy the matcher or role rule above without analyzing the flow architecture.

A custom filter must not accidentally call a global manager that lacks the chain-local provider. You can use a manager or resolver created/wired for that flow, or a custom `ProviderManager` with the OTP provider and an appropriate parent. The goal is that **the exact token class created by the filter has a trusted provider in the manager the filter actually calls**.

When adding a provider to `HttpSecurity`, check bean lifecycle and filter constructor dependencies for your Spring Security version; do not assume from `http.authenticationProvider(...)` that every filter outside the chain will automatically see the provider.

## 15. Runnable Java 17 Maven Project to Reproduce the Real Error

This section uses **Spring Security Core 6.5.11** directly, without Spring Boot or a web server. The example intentionally creates one manager missing the OTP provider, then creates a second manager with the required provider. The credentials `demo-pass` and `123456` are only fixtures in the program, **not a production security algorithm**.

Directory tree:

~~~text
provider-not-found-demo/
  pom.xml
  src/main/java/demo/ProviderNotFoundDemo.java
~~~

### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>provider-not-found-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
            <version>6.5.11</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The specific version pins the demo and does not imply it is the latest release. Spring Boot projects have their own dependency management, so avoid mixing arbitrary Spring Security versions.

### `src/main/java/demo/ProviderNotFoundDemo.java`

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class ProviderNotFoundDemo {

    static final class OtpRequest extends AbstractAuthenticationToken {
        private final String user;
        private String code;

        OtpRequest(String user, String code) {
            super(null);
            this.user = user;
            this.code = code;
            super.setAuthenticated(false);
        }

        @Override
        public Object getPrincipal() {
            return user;
        }

        @Override
        public Object getCredentials() {
            return code;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            code = null;
        }
    }

    static final class PasswordProvider implements AuthenticationProvider {
        @Override
        public boolean supports(Class<?> type) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            boolean valid = Objects.equals("alice", request.getName())
                    && Objects.equals("demo-pass", request.getCredentials());

            if (!valid) {
                throw new BadCredentialsException("Bad demo password");
            }

            return UsernamePasswordAuthenticationToken.authenticated(
                    "alice", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
        }
    }

    static final class OtpProvider implements AuthenticationProvider {
        @Override
        public boolean supports(Class<?> type) {
            return OtpRequest.class.isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            boolean valid = Objects.equals("alice", request.getName())
                    && Objects.equals("123456", request.getCredentials());

            if (!valid) {
                throw new BadCredentialsException("Bad demo OTP");
            }

            return UsernamePasswordAuthenticationToken.authenticated(
                    "alice", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
        }
    }

    static void check(
            String label, AuthenticationManager manager,
            Authentication request) {
        try {
            Authentication result = manager.authenticate(request);
            System.out.println(label + ": "
                    + (result.isAuthenticated() ? "authenticated" : "not authenticated"));
        } catch (AuthenticationException ex) {
            System.out.println(label + ": "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        AuthenticationManager passwordOnly =
                new ProviderManager(List.of(new PasswordProvider()));

        AuthenticationManager withOtp =
                new ProviderManager(List.of(
                        new PasswordProvider(), new OtpProvider()));

        check("password valid", passwordOnly,
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "demo-pass"));

        check("otp no provider", passwordOnly,
                new OtpRequest("alice", "123456"));

        check("password incorrect", passwordOnly,
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "wrong"));

        check("otp with provider", withOtp,
                new OtpRequest("alice", "123456"));

        check("otp incorrect", withOtp,
                new OtpRequest("alice", "wrong"));
    }
}
~~~

Run in the project directory with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ProviderNotFoundDemo
~~~

**Expected stdout of the program** (excluding extra Maven/plugin output if the environment prints any):

~~~text
password valid: authenticated
otp no provider: ProviderNotFoundException
password incorrect: BadCredentialsException
otp with provider: authenticated
otp incorrect: BadCredentialsException
~~~

Interpretation:

- Password request has a supporting provider and valid fixture value → authenticated.
- OTP request goes into the manager that only has the password provider → `ProviderNotFoundException`.
- Password request has a supporting provider, but wrong credential → `BadCredentialsException`.
- Adding the OTP provider to the second manager → OTP request succeeds.
- OTP provider is selected, but the OTP fixture is wrong → `BadCredentialsException`, not missing provider.

Because the program uses real Spring APIs, the JARs must be on the classpath; Maven is the proper way to run it, and you cannot just run plain `javac ProviderNotFoundDemo.java` without downloading dependencies.

**Limitations:** this code checks constant strings and has no password hashing, TOTP algorithm, challenge expiry, atomic replay prevention, or session/tenant binding. In production, use `PasswordEncoder`, method-appropriate verifiers, rate limits, and trusted state. This is a dispatch/exception demo, not a real OTP implementation template.

## 16. Testing Direct Manager and `supports` Predicate

Important tests:

| Case | Expectation |
|---|---|
| Password provider supports `UsernamePasswordAuthenticationToken`. | `supports(...) == true`. |
| Password provider does not support `DeviceOtpAuthenticationToken`. | `supports(...) == false`. |
| OTP provider supports the right custom type. | `supports(...) == true`. |
| Manager lacks the OTP provider. | `ProviderNotFoundException`. |
| Provider is present, but password/OTP is wrong. | `BadCredentialsException`. |
| Provider returns `null` for an instance that does not belong to it. | Manager tries another provider per contract. |
| Account disabled/locked. | Does not fall back to a less secure provider. |
| Manager has a different parent. | Parent behavior obeys policy; does not bypass the chain. |
| Result has proper principal/authorities. | Only after verification; roles come from a trusted source. |
| Auth request class inherits from custom type. | `isAssignableFrom`/`equals` behaves as expected. |
| Trace logging enabled. | No raw credentials/JWT/OTP appear in logs. |

Conceptual JUnit test:

~~~java
@Test
void noProviderForCustomOtpRequest() {
    AuthenticationManager manager =
            new ProviderManager(List.of(new PasswordProvider()));

    assertThrows(ProviderNotFoundException.class,
            () -> manager.authenticate(
                    new OtpRequest("alice", "123456")));
}
~~~

This test snippet assumes the demo classes and JUnit 5 `assertThrows` are imported; it requires the `junit-jupiter` test dependency. For Spring Boot apps, use `spring-boot-starter-test`. Add a similar test for `BadCredentialsException` to prove both situations are properly distinguished.

**Do not only unit-test `supports`.** An app can have a perfect provider while filter/manager wiring is broken; you need integration tests covering the real endpoint and chain.

## 17. MockMvc Testing to Detect Wrong Chains

In a Spring MVC application:

- Use `@SpringBootTest` + `@AutoConfigureMockMvc` with filters enabled.
- With `MockMvcBuilders.webAppContextSetup(...)`, integrate `springSecurity()`.
- Send OTP/JWT requests through the **real filter/converter path** under test.
- Do not use `@WithMockUser` or `SecurityMockMvcRequestPostProcessors.jwt()` and then claim the **real provider was called**: both helpers construct/set mock authentication to test authorization.
- Test both the right path and paths that match into a different chain.
- Include a valid CSRF token if POST uses cookie sessions; a `403` from CSRF does not prove a provider mismatch.

Example test matrix:

~~~text
POST /mfa/verify   valid challenge   -> provider called, success policy
POST /mfa/verify   invalid code      -> bad credentials / generic response
POST /mfa/verify   expired challenge -> reject, no authenticated result
POST /mfa/verify   missing provider  -> controlled auth failure, audit
POST /mfa/verify   another tenant    -> reject, no cross-tenant fallback
GET  /api/orders   valid JWT         -> correct resource-server provider
GET  /api/orders   invalid JWT       -> decoder rejects, no bypass
POST /login        valid password    -> Dao/LDAP provider handles request
~~~

The HTTP status depends on the entry point and failure handler (web login may redirect; REST API returns 401). Assert the exception type in manager-level tests, while HTTP integration tests should assert **safe client-visible behavior, no side effects, and that the right filter/manager was invoked**.

## 18. Authentication Events and Logging

`DefaultAuthenticationEventPublisher` maps `ProviderNotFoundException` to `AuthenticationFailureProviderNotFoundEvent` in Spring Security. However, the event is only published if that `AuthenticationManager` path has an event publisher configured; it is not automatically guaranteed for every custom filter.

Internal audit taxonomy you can use:

~~~json
{
  "outcome": "FAILURE",
  "category": "PROVIDER_CONFIGURATION",
  "requestTokenClass": "demo.security.DeviceOtpAuthenticationToken",
  "managerId": "otp-manager",
  "route": "/mfa/verify",
  "requestId": "req-a3b",
  "occurredAt": "2026-11-06T08:00:00Z"
}
~~~

This is a **suggested schema**, not a built-in event payload. Never log `Authentication.getCredentials()`, bearer strings, passwords, OTPs, secrets, sensitive token claims, or full request bodies. In public responses, do not list class/provider names; avoid letting attackers read your auth architecture.

`ProviderNotFoundException` is usually a **configuration/integration defect**. Do not count it as a failed password guess and trigger mass account lockouts. If a new deployment causes a provider-not-found spike, inspect the change set, security chain order, bean wiring, and canary environment.

## 19. OAuth2 Resource Server: How Is the JWT Provider Created?

With Spring Security Servlet and an OAuth2 JWT resource server:

~~~java
http.authorizeHttpRequests(a -> a.anyRequest().authenticated())
    .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));
~~~

To work, the project needs resource-server/JOSE dependencies and a `JwtDecoder` (for example, configuring an issuer URI). Typical flow:

~~~text
Authorization: Bearer eyJ...
        |
        v
BearerTokenAuthenticationFilter
        |
        v
BearerTokenAuthenticationToken
        |
        v
JwtAuthenticationProvider + JwtDecoder
        |
        v
JwtAuthenticationToken (authenticated result)
        |
        v
SecurityContext -> authorization
~~~

If the application only enables `oauth2Login()` as an OIDC browser client, it **does not automatically get** a bearer resource-server chain for APIs. Conversely, enabling resource-server JWT does not automatically create form-login/LDAP/OTP providers.

More important than provider errors: real JWTs must verify **signature, issuer, audience, expiry, token purpose, and scope**. Do not create a `JwtAuthenticationToken` from client claims and insert it into `SecurityContext` to avoid the exception; that skips cryptographic verification.

## 20. Reactivity, Multi-Tenant, and Manager Resolvers

In **Spring WebFlux**, `ReactiveAuthenticationManager`/`SecurityWebFilterChain` have reactive APIs and semantics, not the same Servlet `ProviderManager`. A reactive manager may return `Mono.empty()` to defer processing per contract; you must debug the actual implementation rather than applying the Servlet exception model verbatim.

In multi-tenant/issuer apps, `AuthenticationManagerResolver<HttpServletRequest>` chooses a manager per request. One tenant may have `JwtAuthenticationProvider` while another selects a manager with only DAO; the same token class can trigger provider-not-found **for only one tenant**.

You must inspect resolver mapping based on trusted signals; an `iss` read from an unverified JWT should only be a **hint to select the verifier**, and the verifier must still re-verify signature/issuer/audience before accepting the token. Do not let an unknown tenant fall back to a shared manager that accepts weaker credentials.

If a custom filter directly uses the global manager while the chain-local manager holds the required provider, the error appears only on some requests. Log manager ID/class/correlation, never bearer tokens.

## 21. Anti-Patterns to Avoid

**Anti-pattern 1: fixing the error with `permitAll()`.** Removing authentication requirements does not fix the provider; it opens the endpoint to unauthenticated requests.

**Anti-pattern 2: `supports()` always returns true.** The provider receives token types that have no matching verifier.

**Anti-pattern 3: calling `setAuthenticated(true)` on a token from JSON.** That bypasses the verifier, not a fix.

**Anti-pattern 4: using `UsernamePasswordAuthenticationToken` for every credential type.** Token classes should reflect semantics; a password provider is not an OTP/JWT provider.

**Anti-pattern 5: creating `new ProviderManager(...)` in every controller.** This can drop beans/configuration, event publishers, and parent/chain semantics, making consistency hard to guarantee.

**Anti-pattern 6: returning null on wrong password so another provider can try.** That can open a fallback bypass.

**Anti-pattern 7: catching `ProviderNotFoundException` and returning login success.** A severe fail-open bug.

**Anti-pattern 8: switching to `DaoAuthenticationProvider` because a `UserDetailsService` exists.** DAO only fits username/password mechanisms; it does not verify bearer JWTs, SAML, or WebAuthn challenges.

**Anti-pattern 9: trusting the `jwt()` test helper to verify JWT signatures.** The helper mocks authentication and does not run the decoder.

**Anti-pattern 10: checking only bean names and ignoring the chain/manager instance.** The provider exists in the context, but not in the manager the request actually calls.

**Anti-pattern 11: registering providers on all chains to be "safe".** Increases attack surface: stateless endpoints might accept form/password authentication the architecture never intended.

**Anti-pattern 12: using unverified username/tenant from the request to pick a cross-tenant provider.** Requires a tested trust boundary and provider mapping.

## 22. Operational Checklist Before Closing an Investigation

- [ ] The actual exception class is `ProviderNotFoundException`, not `BadCredentialsException`.
- [ ] The request token Java class has been safely recorded.
- [ ] The filter/converter creates the right class with proper credential semantics.
- [ ] The manager instance used by the filter/controller has been verified.
- [ ] The provider list and `supports` checks are accurate on that exact manager.
- [ ] Returning `null`/non-null/exceptions is clearly distinguished and tested.
- [ ] Account status errors cannot be bypassed via fallback.
- [ ] `SecurityFilterChain` matchers and `@Order` are tested for real endpoints.
- [ ] Custom provider is registered in the right chain/manager, not just present as a bean.
- [ ] OTP verifier enforces expiry, replay protection, attempts, and user/session binding.
- [ ] JWT decoder verifies signature/issuer/audience/expiry; no fake authenticated results.
- [ ] Parent manager and dynamic resolver do not grant access beyond policy.
- [ ] Negative tests cover: wrong password, wrong OTP, disabled user, missing provider, cross-tenant.
- [ ] Authentication failure events classify configuration defects and are monitored.
- [ ] No raw credentials, OTPs, session cookies, or JWTs appear in logs.
- [ ] Only minimal fixes are made, and tests verify behavior through the real filter chain/request after deployment.

## 23. Conclusion

The message **"No AuthenticationProvider found for the input token type"** signals that **an Authentication request object was sent to a manager that has no provider capable of handling that type**. Trace in order: **HTTP request → filter/converter → request token Java class → specific AuthenticationManager → providers and supports → authenticate result/exception → SecurityContext**.

The sustainable fix is creating the right request type, registering a provider with a real verifier into **the right manager/chain**, implementing `supports` and `authenticate` per contract, and preserving MFA, JWT, session, and tenant boundaries. Never turn off security or issue an authenticated result from unverified input.

By reproducing `ProviderNotFoundException` with a real `ProviderManager` and testing wrong-password/wrong-OTP cases as well, you distinguish **provider configuration errors** from **credential verification failures**, avoiding bad fixes that introduce login vulnerabilities.

## References

- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, providers.
- [Spring Security 6.5 – AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html): `supports`, `authenticate`, and null results.
- [Spring Security 6.5 – ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): provider order, parent manager, exception semantics.
- [Spring Security 6.5 – ProviderNotFoundException Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderNotFoundException.html): no-provider exception.
- [Spring Security – Servlet SecurityFilterChain Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain selection and order.
- [Spring Security – JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): bearer authentication, `JwtDecoder`, and claim validation.
- [Spring Security – Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): failure event mapping.
- [Spring Security – MockMvc Test Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): running real security filters in tests.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login failure, account enumeration, and error handling.

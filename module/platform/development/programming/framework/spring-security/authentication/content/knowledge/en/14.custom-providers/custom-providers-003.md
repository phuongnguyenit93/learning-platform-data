# Implementing \`supports\` and Accurately Checking Credential Types in a Custom AuthenticationProvider

## 1. Lesson Objectives

When a Spring Security application has multiple authentication mechanisms — for example username/password, API key, OTP, certificate, or an internal token type — each `AuthenticationProvider` should only handle the exact request type it understands. The `supports(Class<?> authentication)` method is the first “provider selection gate”; accurately checking the object inside `authenticate(Authentication)` is the next line of defense.

After this lesson, you will be able to:

- Understand that `AuthenticationProvider.supports` receives a **token class** (a `Class<?>` object), not a login method string or password value.
- Write `supports` to return `true` **only** for the token class the provider can actually handle; distinguish exact type comparison (`==` or `equals`) from accepting subclasses (`isAssignableFrom`).
- Know how `ProviderManager` uses `supports` to pick a provider, as well as the cases of returning `null`, throwing `AuthenticationException`, or finding no provider.
- Protect `authenticate` against invalid casts, tokens improperly marked as authenticated, and malformed credentials; return a verified `Authentication` only after actually checking the credentials.
- Test both **supported** and **unsupported** token types rather than testing only a single successful login case.

The scope is **Spring Security Servlet/Core, Java 17+, custom AuthenticationProvider**. The example runs directly with `spring-security-core`, without setting up a web server. Wiring into an HTTP filter is shown to clarify responsibilities between layers.

## 2. Understanding the True Role of \`supports\`

The contract of `AuthenticationProvider` in Spring Security 6.x:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

Conceptually, the flow is:

~~~text
Client sends credentials
        |
        v
Filter / Controller creates an UNAUTHENTICATED Authentication
        |
        v
AuthenticationManager (typically ProviderManager)
        |
        +--> provider A.supports(request.getClass()) == false -> skip A
        |
        +--> provider B.supports(request.getClass()) == true
                        |
                        v
                  B.authenticate(request)
                        |
            +-----------+-----------+
            |           |           |
      Authentication   null     AuthenticationException
       succeeded        |            |
            |      try next     record error;
            |      provider     may try another provider
            v
     Return result to caller
~~~

Key points to grasp:

1. `supports(Class<?>)` says **“I am capable of considering this token type”**; it does not say “the password is right”, “the user is valid”, or “the request is authenticated”.
2. `ProviderManager` typically takes `authentication.getClass()` and queries each provider in its list in turn. A provider returning `false` will not have `authenticate` called for that request.
3. `supports` returning `true` **does not guarantee** the provider will accept every object of that type. It can still return `null` if it cannot decide and wants the next matching provider to evaluate it.
4. If a provider verifies successfully and returns a **non-null** `Authentication`, `ProviderManager` stops and uses that result. If a provider throws `AuthenticationException`, the manager may continue trying other matching providers depending on the exception type; do not treat every exception as an absolute stop. `AccountStatusException` is an example handled by stopping immediately.
5. When no provider supports/completes authentication and no parent manager resolves it, `ProviderManager` throws `ProviderNotFoundException`. This is a provider registration or token type issue, not synonymous with a wrong password.
6. `supports` is not authorization. An authenticated result still has to pass through `SecurityContext`, endpoint rules, or method security.

Do not write `supports` based on username/password, user roles, or JSON contents: the parameter here is a **Java class**, not an instance holding credentials.

## 3. Type Checking: \`equals\`, \`==\`, or \`isAssignableFrom\`?

Suppose we have a custom `ApiKeyAuthenticationToken` class for API keys. There are three common ways to write it:

~~~java
// A. Exact ApiKeyAuthenticationToken class only
@Override
public boolean supports(Class<?> authentication) {
    return ApiKeyAuthenticationToken.class.equals(authentication);
}
~~~

~~~java
// B. Equivalent to A for exact Class comparison
@Override
public boolean supports(Class<?> authentication) {
    return authentication == ApiKeyAuthenticationToken.class;
}
~~~

~~~java
// C. Also supports subclasses of ApiKeyAuthenticationToken
@Override
public boolean supports(Class<?> authentication) {
    return ApiKeyAuthenticationToken.class.isAssignableFrom(authentication);
}
~~~

Comparison:

| Approach | `ApiKeyAuthenticationToken.class` | Subclass `SpecialApiKeyAuthenticationToken.class` (if inheritance is allowed) | `UsernamePasswordAuthenticationToken.class` |
| --- | --- | --- | --- |
| `ApiKeyAuthenticationToken.class.equals(authentication)` | `true` | `false` | `false` |
| `authentication == ApiKeyAuthenticationToken.class` | `true` | `false` | `false` |
| `ApiKeyAuthenticationToken.class.isAssignableFrom(authentication)` | `true` | `true` | `false` |

Choose based on your provider's contract:

- **Choose exact checking** when the provider only understands one specific token type and has no intention of supporting subclasses or protocol extensions. This is the choice in the example.
- **Choose `isAssignableFrom`** when supporting subtypes is **intentional**, and the logic inside `authenticate` safely handles any accepted subtype. This is also the pattern used by some built-in Spring Security providers for their token families.
- In either approach, avoid reversing the direction: `authentication.isAssignableFrom(ApiKeyAuthenticationToken.class)` can return `true` for overly broad classes like `Authentication.class` or `Object.class`, causing the provider to claim support for unintended types.
- Avoid `return true;` for all classes, and do not write `Authentication.class.isAssignableFrom(authentication)` if the provider only truly understands one concrete token. Nearly every token implements `Authentication`; that expression would be far too broad.

**Note:** `Class<?>` does not tell you the data type inside `getCredentials()`. Even when the token has the right class, you must still verify inside `authenticate` that the instance is unauthenticated, credentials have the right type, and the value is valid.

## 4. Complete Java 17+ Example: A Provider Accepting Only an API Key Token

To see `supports` clearly without clutter from controllers, form login, or HTTP configuration, this example uses **Spring Security Core 6.5.x** and `ProviderManager`. A dedicated custom token is created for the API key; `UsernamePasswordAuthenticationToken` is intentionally **not** supported by the provider.

> This is an example for learning the routing mechanism. The hardcoded API key in code is only for running the demo and **must not be used in production**. Real systems must store secrets securely, support key revocation/rotation, access limits, auditing, HTTPS, and proper authentication policies.

### 4.1. Create the Maven Project

Directory layout:

~~~text
provider-supports-demo/
├── pom.xml
└── src/
    ├── main/java/demo/security/ProviderSupportsDemo.java
    └── test/java/demo/security/ProviderSupportsDemoTest.java
~~~

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.security</groupId>
    <artifactId>provider-supports-demo</artifactId>
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
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

When using real Spring Boot, let the Boot BOM manage compatible versions of Spring Security and JUnit; do not mechanically copy and override these versions into an existing project.

### 4.2. Runnable Java File

File `src/main/java/demo/security/ProviderSupportsDemo.java`:

~~~java
package demo.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class ProviderSupportsDemo {

    /**
     * Authentication request type ONLY for API keys.
     * "final" prevents subclasses from silently extending the token protocol.
     */
    static final class ApiKeyAuthenticationToken
            extends AbstractAuthenticationToken {

        private final Object principal;
        private final String apiKey;

        private ApiKeyAuthenticationToken(
                Object principal,
                String apiKey,
                Collection<? extends GrantedAuthority> authorities,
                boolean authenticated) {

            super(authorities);
            this.principal = Objects.requireNonNull(principal);
            this.apiKey = apiKey;
            // Only the private constructor may set the trusted state.
            super.setAuthenticated(authenticated);
        }

        static ApiKeyAuthenticationToken unauthenticated(String rawApiKey) {
            return new ApiKeyAuthenticationToken(
                "unverified-client", rawApiKey, List.of(), false);
        }

        private static ApiKeyAuthenticationToken verified(String clientName) {
            return new ApiKeyAuthenticationToken(
                clientName,
                null, // Do not carry the secret into the authenticated token.
                List.of(new SimpleGrantedAuthority("ROLE_SERVICE")),
                true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return apiKey;
        }

        @Override
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                    "Cannot mark an unverified token as authenticated");
            }
            super.setAuthenticated(false);
        }
    }

    static final class ApiKeyAuthenticationProvider
            implements AuthenticationProvider {

        // DO NOT hardcode secrets in a real program.
        private static final String LEARNING_ONLY_KEY = "demo-api-key";

        @Override
        public boolean supports(Class<?> authenticationType) {
            // Accept only this exact concrete class.
            return ApiKeyAuthenticationToken.class.equals(authenticationType);
        }

        @Override
        public Authentication authenticate(Authentication authentication) {
            // Second line of defense: do not cast when encountering a foreign token.
            if (authentication == null
                    || authentication.getClass()
                       != ApiKeyAuthenticationToken.class) {
                return null;
            }

            ApiKeyAuthenticationToken request =
                (ApiKeyAuthenticationToken) authentication;

            if (request.isAuthenticated()
                    || !(request.getCredentials() instanceof String rawKey)
                    || rawKey.isBlank()) {
                throw new BadCredentialsException("Invalid API key");
            }

            byte[] supplied = rawKey.getBytes(StandardCharsets.UTF_8);
            byte[] expected =
                LEARNING_ONLY_KEY.getBytes(StandardCharsets.UTF_8);

            if (!MessageDigest.isEqual(expected, supplied)) {
                throw new BadCredentialsException("Invalid API key");
            }

            // Only the provider after successful verification creates a trusted token.
            return ApiKeyAuthenticationToken.verified("service-client");
        }
    }

    public static void main(String[] args) {
        AuthenticationProvider provider = new ApiKeyAuthenticationProvider();
        AuthenticationManager manager = new ProviderManager(provider);

        System.out.println("supports(api-key)=" +
            provider.supports(ApiKeyAuthenticationToken.class));
        System.out.println("supports(username-password)=" +
            provider.supports(UsernamePasswordAuthenticationToken.class));

        Authentication trusted = manager.authenticate(
            ApiKeyAuthenticationToken.unauthenticated("demo-api-key"));

        System.out.println("principal=" + trusted.getName());
        System.out.println("authenticated=" + trusted.isAuthenticated());

        try {
            manager.authenticate(
                ApiKeyAuthenticationToken.unauthenticated("wrong-key"));
        } catch (BadCredentialsException ex) {
            System.out.println("wrong-key=" +
                ex.getClass().getSimpleName());
        }

        try {
            manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "password"));
        } catch (ProviderNotFoundException ex) {
            System.out.println("other-token=" +
                ex.getClass().getSimpleName());
        }
    }
}
~~~

Run in the directory containing `pom.xml` (Maven and JDK 17+ installed):

~~~bash
mvn -q -DskipTests compile
mvn -q -Dexec.mainClass=demo.security.ProviderSupportsDemo exec:java
~~~

Lines **explicitly printed by the program**:

~~~text
supports(api-key)=true
supports(username-password)=false
principal=service-client
authenticated=true
wrong-key=BadCredentialsException
other-token=ProviderNotFoundException
~~~

Maven or the logging system may emit extra logs/warnings depending on the environment. The code content and file/class names match package `demo.security`. Since the class depends on Spring Security, it will not run with plain `javac` unless dependencies are declared on the classpath; Maven above resolves those dependencies.

### 4.3. Why Is This Design Right?

**Distinct and explicit token type.** `ApiKeyAuthenticationToken` is a separate `Authentication`, avoiding misusing `UsernamePasswordAuthenticationToken` to hold an API key. `final` prevents the supported type set from changing through unintended inheritance.

**Factory for the unauthenticated state.** Any client input is only turned into `ApiKeyAuthenticationToken.unauthenticated(...)`. The `authenticated=false` flag means the token is awaiting verification by `AuthenticationManager`.

**Exact `supports` rule.** `ApiKeyAuthenticationProvider.supports(...)` returns `true` solely for `ApiKeyAuthenticationToken.class`. Username/password tokens go to another provider (if registered), instead of causing a cast error inside the API key provider.

**Type guard inside `authenticate`.** Even though `ProviderManager` normally calls `supports` first, never assume every caller follows that order: tests or other code may call `provider.authenticate(foreignToken)` directly. The code returns `null` for tokens outside its contract; it does not throw `ClassCastException`.

**Credential validation at authentication time.** Having the right class is not enough: the API key could be blank, wrong, or the token could have an invalid state flag. The provider throws `BadCredentialsException` for invalid data that it actually accepted responsibility for verifying. It returns a `verified` token only after confirming the demo key.

**The result object does not retain the key.** The trusted token contains a server-determined principal and authorities; `getCredentials()` is `null`. `ProviderManager` also has a policy to erase credentials on the result if the token implements `CredentialsContainer`; do not rely solely on that mechanism to handle secrets on input requests.

**Restricting creation of trusted tokens.** `setAuthenticated(true)` is blocked for normal callers; the provider creates results through a controlled private factory. This avoids privilege escalation via calling a setter; Java class-level visibility does not replace input control and provider registration checks.

## 5. Testing Valid, Invalid, and Wrong Token Types

A provider is only considered correct when it both authenticates its own token and **does not compete to handle** another provider's token. Test at three levels:

1. `supports` returns the right boolean for `Class<?>`.
2. `authenticate` returns a trusted token when credentials are valid, returns `null` when called directly with a foreign type, and throws a credential error when the type matches but the secret is wrong.
3. `ProviderManager` actually skips the provider when the token is unsupported, thereby raising `ProviderNotFoundException` if this manager has no other provider and no parent manager.

File `src/test/java/demo/security/ProviderSupportsDemoTest.java`:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

import static org.junit.jupiter.api.Assertions.*;

class ProviderSupportsDemoTest {

    private final ProviderSupportsDemo.ApiKeyAuthenticationProvider provider =
        new ProviderSupportsDemo.ApiKeyAuthenticationProvider();

    @Test
    void supportsOnlyExactApiKeyTokenClass() {
        assertTrue(provider.supports(
            ProviderSupportsDemo.ApiKeyAuthenticationToken.class));
        assertFalse(provider.supports(
            UsernamePasswordAuthenticationToken.class));
        assertFalse(provider.supports(Authentication.class));
        assertFalse(provider.supports(Object.class));
        assertFalse(provider.supports(null));
    }

    @Test
    void validKeyProducesAuthenticatedResultWithoutCredentials() {
        Authentication result = new ProviderManager(provider).authenticate(
            ProviderSupportsDemo.ApiKeyAuthenticationToken
                .unauthenticated("demo-api-key"));

        assertTrue(result.isAuthenticated());
        assertEquals("service-client", result.getName());
        assertNull(result.getCredentials());
        assertTrue(result.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_SERVICE")));
    }

    @Test
    void invalidKeyIsAuthenticationFailure() {
        assertThrows(BadCredentialsException.class,
            () -> new ProviderManager(provider).authenticate(
                ProviderSupportsDemo.ApiKeyAuthenticationToken
                    .unauthenticated("wrong-key")));
    }

    @Test
    void nullOrBlankKeyIsRejected() {
        assertThrows(BadCredentialsException.class,
            () -> new ProviderManager(provider).authenticate(
                ProviderSupportsDemo.ApiKeyAuthenticationToken
                    .unauthenticated(null)));
        assertThrows(BadCredentialsException.class,
            () -> new ProviderManager(provider).authenticate(
                ProviderSupportsDemo.ApiKeyAuthenticationToken
                    .unauthenticated("")));
    }

    @Test
    void directCallWithForeignTokenReturnsNullWithoutCasting() {
        Authentication other =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "password");

        assertNull(provider.authenticate(other));
    }

    @Test
    void managerCannotAuthenticateUnregisteredTokenType() {
        assertThrows(ProviderNotFoundException.class,
            () -> new ProviderManager(provider).authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "password")));
    }

    @Test
    void clientCannotMarkUnverifiedTokenAsTrusted() {
        var request = ProviderSupportsDemo.ApiKeyAuthenticationToken
            .unauthenticated("invalid-key");

        assertThrows(IllegalArgumentException.class,
            () -> request.setAuthenticated(true));
        assertFalse(request.isAuthenticated());
    }
}
~~~

Run:

~~~bash
mvn -q test
~~~

If dependencies download and the code compiles under the stated versions, **7 tests are expected to pass**, with no errors or failures. Run it in an actual project to confirm; this is example code for learners, not test results executed in a production environment.

The tests protect important invariants:

| Test | Invariant |
| --- | --- |
| `supportsOnlyExactApiKeyTokenClass` | Provider accepts only exact `ApiKeyAuthenticationToken` |
| `validKeyProducesAuthenticatedResultWithoutCredentials` | Only a valid key yields a trusted principal without leaking the secret in the result |
| `invalidKeyIsAuthenticationFailure` | Matching class with wrong key must be rejected |
| `nullOrBlankKeyIsRejected` | Missing/empty values are never treated as valid |
| `directCallWithForeignTokenReturnsNullWithoutCasting` | Direct call with a foreign token does not cause `ClassCastException` |
| `managerCannotAuthenticateUnregisteredTokenType` | `ProviderManager` does not “turn” a foreign token into an API key token |
| `clientCannotMarkUnverifiedTokenAsTrusted` | Trusted state cannot be enabled via setter alone |

## 6. Easy-to-Misunderstand Situations with Multiple Providers

### 6.1. `supports` Returns `true` but `authenticate` Returns `null`

This is a meaningful outcome: the provider **knows the token type**, but cannot complete authentication for the specific case; the manager can try the next provider whose `supports` matches. For instance, multiple authentication providers understand the same token, but each is responsible for a different tenant. To say “not my tenant”, it can return `null`.

However, when a provider has taken responsibility for verifying credentials and knows the credentials are **wrong**, it should usually throw `BadCredentialsException` rather than returning `null` just to avoid errors. Allowing another provider to continue after a failure must be intentionally designed: `ProviderManager` may continue to another supporting provider and a later successful authentication can override an earlier error. If policy requires an invalid credential to block outright, you must design provider ordering/routing and special exceptions with the right semantics, without assuming `BadCredentialsException` always stops all fallback.

### 6.2. Multiple Providers Supporting the Same Token Type

~~~java
AuthenticationManager manager = new ProviderManager(
    firstProvider,
    secondProvider
);
~~~

If both return `supports(TokenType.class) == true`, the manager typically tries them in order. The first provider to succeed decides the result; a provider returning `null` yields to the next provider. If both verify the same type but with different rules, carefully inspect fallback behavior to prevent “a later provider accepting what an earlier provider rejected”. Never configure a provider too broadly for every token just to “catch all requests”.

### 6.3. No Provider Supports the Token

With the demo manager containing only the API key provider, sending `UsernamePasswordAuthenticationToken` produces `ProviderNotFoundException`. In a real application, confirm that:

- The Filter/AuthenticationConverter created the **exact expected token class**.
- The provider was registered into the exact `AuthenticationManager` that the filter calls.
- If there are multiple `SecurityFilterChain` beans, the request hits the right chain and manager.
- `supports` uses the right `isAssignableFrom` direction or exact class comparison.
- Servlet `AuthenticationProvider` is not confused with WebFlux `ReactiveAuthenticationManager`/`AuthenticationWebFilter`.

**Do not fix this by writing `supports(...) { return true; }`.** That only hides misconfiguration and can cause cast errors, misrouting, or unintended auth flows.

### 6.4. Exact Class or Also Subclasses?

If the token is declared `final` as in the demo, `equals` and `isAssignableFrom` cover the exact same set of valid concrete classes. But with a **non-final** token that allows subclasses, `isAssignableFrom` is broader. Explicitly decide whether subclasses should receive the same authentication rights instead of picking the broader option by default.

When allowing subclasses, `authenticate` should check `instanceof` and rely on the verified contract of the parent class; if the logic is only safe for the root class, you still need to check `getClass() == ConcreteToken.class` and reject subtypes. When supporting only the exact type, a runtime check like the demo's keeps the declaration and implementation strictly consistent.

## 7. Wiring the Provider into the Servlet Flow: Right Place and Right Responsibility

An `AuthenticationProvider` does not read HTTP itself. A filter or controller creates an unauthenticated `Authentication`, then calls `AuthenticationManager`. Conceptual filter snippet:

~~~java
// Illustrative snippet inside an authentication converter/filter,
// not a complete servlet filter:
String rawKey = request.getHeader("X-API-Key");
if (rawKey == null || rawKey.isBlank()) {
    throw new BadCredentialsException("Missing credentials");
}
Authentication candidate =
    ApiKeyAuthenticationToken.unauthenticated(rawKey);
Authentication result = authenticationManager.authenticate(candidate);
~~~

`authenticationManager` at this point must have `ApiKeyAuthenticationProvider` registered. The code above only illustrates how to construct and dispatch the token; the demo's token class is nested/package-private, so when splitting across packages it should be made a separate class with a properly scoped factory API. **Do not** place API keys in URLs or query strings; use headers or a clearly designed authentication channel. Production should prefer Spring Security's built-in standard mechanisms if they meet requirements.

If the application also uses standard username/password, keep the username/password provider separate. Responsibility diagram:

~~~text
POST /api/login + username/password
    -> UsernamePasswordAuthenticationToken
    -> DaoAuthenticationProvider

GET /api/data + API key
    -> ApiKeyAuthenticationToken
    -> ApiKeyAuthenticationProvider
~~~

`supports` selects a provider **by token class**, not by HTTP method, endpoint, header, or role. Request/method routing happens in `RequestMatcher` and the converter/filter (or controller) **before** the token enters the manager. Never let a provider read the request from `RequestContextHolder` to decide `supports`.

For real web login, the filter needs to handle `AuthenticationException` per design, place the authenticated result into `SecurityContextHolder`, and decide whether to save the context to the session or use stateless tokens. Those steps are **outside the direct responsibility of `supports`**.

## 8. Common Implementation Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `supports(Class<?> c) { return true; }` | Provider competes to handle tokens outside its protocol | Compare the exact token class |
| `return Authentication.class.isAssignableFrom(c);` | Matches nearly every Spring Security token | Use the concrete token class |
| `return c.isAssignableFrom(MyToken.class);` | Reversed comparison: overly broad parent classes claim support | `MyToken.class.isAssignableFrom(c)` or exact `equals` |
| Checking only `instanceof` and trusting credentials | Right class can still carry blank/invalid data | Validate structure, state, and actual credentials |
| Casting right at the start of `authenticate` | Direct calls with other tokens cause `ClassCastException` | Check type before casting |
| Returning `null` when key is wrong | May forward error to another provider unexpectedly | Throw `BadCredentialsException` when owning verification and finding it invalid |
| Creating a trusted token before verification | Allows privilege escalation before calling the provider | Request tokens must be unauthenticated |
| Reusing username/password token for API keys out of convenience | Other providers may accept and misinterpret credentials | Create a dedicated token for the dedicated protocol |
| Treating `supports` as route authorization | Token type does not grant endpoint access | Apply authorization on endpoints and methods |
| Forgetting to register provider in the filter's manager | `ProviderNotFoundException` even though provider exists in code | Check the actual `SecurityFilterChain` and `AuthenticationManager` used |
| Copying client-sent roles into the authenticated token | Clients can grant themselves roles | Build authorities from verified server data |
| Logging API keys or keeping secrets in result tokens | Increases credential exposure risk | Redact logs, limit lifetime, and store secrets safely |

## 9. Code Review Checklist for a Custom AuthenticationProvider

- [ ] The input token has a concrete class accurately representing the authentication mechanism (API key, OTP, username/password, etc.).
- [ ] `supports` uses the exact signature `boolean supports(Class<?> authentication)` and declares the **exact set of supported classes**.
- [ ] Exact class (`equals`/`==`) vs. all subtypes (`isAssignableFrom`) has been explicitly evaluated.
- [ ] `authenticate` performs safe type checking before casting, including when invoked directly.
- [ ] `authenticate` verifies the unauthenticated state and required credential data.
- [ ] The provider never sets trusted=true before verifying the key/password/OTP.
- [ ] Principal/authorities in the result are derived from a verified identity, never from client-supplied roles.
- [ ] Invalid credential failures and cases the provider cannot handle are properly distinguished (exception vs. `null`).
- [ ] Tests cover both positive and negative `supports`, wrong credentials, wrong token classes, and the `ProviderManager` flow.
- [ ] Provider is registered in the right manager/chain; behavior with multiple providers and parent managers is verified.
- [ ] Secrets never appear in logs, URLs, authenticated tokens, or HTTP output; production includes secret management and rotation.
- [ ] On success, SecurityContext/session/stateless rules and authorization are configured separately in the filter/application.

## 10. Self-Check Questions

1. Why does `supports(UsernamePasswordAuthenticationToken.class) == false` not mean “the user's password is wrong”?
2. What is the difference between `MyToken.class.equals(authentication)` and `MyToken.class.isAssignableFrom(authentication)`?
3. If `supports` returns `true`, is Spring Security guaranteed to authenticate successfully?
4. When should `authenticate` return `null`? When should it throw `BadCredentialsException`?
5. Why should a provider that already has a correct `supports` still check the token class inside `authenticate`?
6. What happens if a manager only registers an API key provider while a filter sends `UsernamePasswordAuthenticationToken`?
7. If two providers both support the same token, what must be tested to prevent fallback from accidentally accepting invalid credentials?
8. Why must the provider's return value contain authorities from the server rather than roles sent by the client?

## 11. Official Documentation

- Spring Security 6.5 API — `AuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- Spring Security 6.5 API — `ProviderManager` (provider ordering, exceptions, erasure): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security 6.5 — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 API — `AbstractAuthenticationToken` (trusted state, credentials): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html
- Spring Security 6.5 API — `ProviderNotFoundException`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderNotFoundException.html
- Java SE — `Class.isAssignableFrom`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isAssignableFrom(java.lang.Class)

**Key takeaway:** `supports` only registers the **exact type of Authentication a provider can consider**; `authenticate` is what verifies credentials and issues a trusted authenticated object. Checking the **exact token class** in both places lets multiple authentication mechanisms coexist without misrouting.
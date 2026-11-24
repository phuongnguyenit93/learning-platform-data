# ProviderManager Selecting the Matching AuthenticationProvider in Spring Security

When a request sends username/password, HTTP Basic, JWT, or a custom credential type, Spring Security needs to know **which component can verify that credential**. A common implementation of AuthenticationManager is **ProviderManager**: it iterates through the list of registered AuthenticationProvider instances, asks each provider whether it supports the incoming Authentication type, and delegates authentication to matching providers in order.

An easy misconception is that **ProviderManager does not always pick a single provider and stop immediately**. A provider might not support the token type, might support it yet return null to yield to another provider, might return a successfully authenticated Authentication, or might throw an AuthenticationException. Ordering and exception types affect what happens next.

This lesson belongs to the **Authentication Flow** section of Spring Security fundamentals. The goal is to understand the exact path from an authentication filter to AuthenticationManager, how ProviderManager collaborates with providers, and how to diagnose errors such as BadCredentialsException, ProviderNotFoundException, or 401. The practical section uses **Java 17+, Spring Boot 3.3.6, and Spring Security 6.x**, including a Maven project and MockMvc/JUnit tests for two different provider types: **DaoAuthenticationProvider** and a **custom AuthenticationProvider for API keys**. The API key is a local experimental model, not a complete production API key issuance system.

## 1. Role of ProviderManager in a Request

Overview diagram:

~~~mermaid
flowchart TD
    R["HTTP request"] --> F["Matching authentication filter"]
    F --> T["Authentication request token: unauthenticated"]
    T --> M["AuthenticationManager.authenticate(request)"]
    M --> PM["ProviderManager"]
    PM --> P1{"Provider #1 supports(token class)?"}
    P1 -- "No" --> P2{"Provider #2 supports(token class)?"}
    P1 -- "Yes" --> A1["Provider #1 authenticate(token)"]
    A1 --> S{"Result"}
    S -- "Authentication succeeds" --> OK["Return authenticated Authentication"]
    S -- "null or retryable error" --> P2
    P2 -- "Yes" --> A2["Provider #2 authenticate(token)"]
    P2 -- "No" --> FALL["Next provider / parent if configured"]
    A2 --> FINAL["Authentication or AuthenticationException"]
    OK --> CTX["Filter uses result and handles SecurityContext"]
    FINAL --> CTX
~~~

Simplified diagram: certain exceptions **stop immediately** and do not try the next provider; parent policies, events, and credentials erasure also affect the actual flow. Those branches are analyzed below.

Separate two responsibilities:

- **Authentication filter** reads the request, extracts credentials, constructs an Authentication request (typically with isAuthenticated=false), calls AuthenticationManager, and then handles SecurityContext/responses per the mechanism.
- **ProviderManager** receives Authentication from the filter, decides which AuthenticationProviders to try, and receives the result or exception. It **does not read arbitrary HTTP headers itself**, does not automatically turn an arbitrary X-API-Key into a token, and does not write SecurityContext merely because authenticate() was called.

An HTTP Basic filter typically puts username/password into **UsernamePasswordAuthenticationToken**; DaoAuthenticationProvider can usually handle that type. A JWT authentication filter may produce **BearerTokenAuthenticationToken** or a type appropriate for the Bearer mechanism; JwtAuthenticationProvider belongs to an appropriate Resource Server configuration. With a custom API key type, you need **the token, provider, filter/converter, and chain configuration** if you want to invoke it over HTTP.

## 2. Four Interfaces/Types to Distinguish

| Component | Primary contract | Responsibility |
| --- | --- | --- |
| **Authentication** | getPrincipal(), getCredentials(), getAuthorities(), isAuthenticated() | Carries an authentication request or an authentication result. |
| **AuthenticationManager** | authenticate(Authentication) | High-level interface performing authentication. |
| **ProviderManager** | authenticate(...) with a list of providers | Implementation of AuthenticationManager, delegating sequentially to suitable providers. |
| **AuthenticationProvider** | supports(Class<?>), authenticate(Authentication) | Can authenticate one or more specific Authentication types. |

Some familiar types:

| Type | Typical role |
| --- | --- |
| **UsernamePasswordAuthenticationToken** | Username/password in HTTP Basic, form login, or certain custom flows. |
| **DaoAuthenticationProvider** | Verifies username/password through UserDetailsService and PasswordEncoder. |
| **JwtAuthenticationProvider** | Verifies JWT via the configured JwtDecoder in a Resource Server. |
| **BearerTokenAuthenticationToken** | Authentication request representing a Bearer token before verification. |
| **AbstractAuthenticationToken** | Useful base class when creating a token for a custom authentication mechanism. |
| **SecurityContext** | Holds the Authentication attached to the active security context. |

**An AuthenticationProvider name is not a user role.** A provider decides **whether credentials are valid and what Authentication to create**, whereas rules like hasRole, hasAuthority, authenticated, or object-permission policies execute at the corresponding authorization step.

### 2.1. Authentication request differs from Authentication result

Before authentication, a token may contain:

~~~text
UsernamePasswordAuthenticationToken
  principal   = "alice"
  credentials = "(password from request)"
  authenticated = false
  authorities = []
~~~

After DaoAuthenticationProvider verifies successfully, the returned object may contain:

~~~text
UsernamePasswordAuthenticationToken
  principal   = UserDetails(alice)
  credentials = "(will be erased if erase credentials mechanism applies)"
  authenticated = true
  authorities = [ROLE_USER]
~~~

A post-authentication token is **not necessarily the same object** as the input token, even though it may be the same class. Never use an isAuthenticated=true flag sent by the client or manually set on an untrusted token as a substitute for verifying a password, signature, or API key.

## 3. The supports(Class<?>) Contract: Filtering by Type

The AuthenticationProvider interface has the method:

~~~java
boolean supports(Class<?> authentication);
~~~

ProviderManager calls supports() to learn whether the provider can inspect **the class of the Authentication request**. In a custom provider, a common expression is:

~~~java
@Override
public boolean supports(Class<?> authenticationType) {
    return DemoApiKeyAuthenticationToken.class
        .isAssignableFrom(authenticationType);
}
~~~

Meaning:

- If the request is DemoApiKeyAuthenticationToken or a subclass of it, the provider can handle it.
- If the request is UsernamePasswordAuthenticationToken, the API-key provider above typically returns false.
- If supports() returns false, ProviderManager **skips calling authenticate() on this provider** and considers other providers.
- If supports() returns true, that only means **it is worth trying authentication**, not proof that credentials are valid. authenticate() can still return null or throw AuthenticationException.

Do not write supports() based on header names, URL paths, or granted roles; the interface only receives **Class<?>**, not HttpServletRequest. Distinguishing requests by path/HTTP header to construct the right Authentication type is the responsibility of the authentication filter/converter or SecurityFilterChain organization.

**Wrong example:**

~~~java
@Override
public boolean supports(Class<?> authenticationType) {
    return true;
}
~~~

A provider claiming to support every token type will be called even for tokens it does not understand. If the implementation then casts UsernamePasswordAuthenticationToken to a custom token, ClassCastException or inconsistent handling can occur. Only return true for types the provider actually knows how to evaluate.

## 4. authenticate(Authentication): Three Basic Outcomes

Primary signature:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

An AuthenticationProvider has three meaningful outcomes:

| Outcome from provider | Meaning | What ProviderManager typically does next |
| --- | --- | --- |
| **Returns non-null Authentication** | Provider authenticated successfully and produced a result. | **Stops** trying remaining providers; returns result after final post-processing. |
| **Returns null** | Provider cannot conclude / cannot handle this instance. | Tries the next provider whose supports() matches; may consult parent. |
| **Throws AuthenticationException** | Authentication failed or related condition occurred. | Depends on exception type: may remember it and try next provider; some types stop immediately. |

Note two points:

1. **null differs from a wrong password**. A provider returning null is saying "I cannot decide", not "I confirmed the credential is wrong".
2. **supports=true does not mean authenticate must succeed**. Two providers can share the UsernamePasswordAuthenticationToken type while serving different identity sources or realms.

This contract lets ProviderManager support multiple mechanisms or identity sources under one AuthenticationManager. However, that flexibility makes it necessary to clearly design **ordering, provider conditions, error classification, and fail-closed policies**.

### 4.1. Why not return null when credentials are definitely wrong?

Suppose an API-key provider supports DemoApiKeyAuthenticationToken and has verified that the submitted key is invalid. If it returns null, another provider supporting the same token type could try and accept the key under a different unintended policy.

In the basic example, throw **BadCredentialsException** when the key is wrong. When multiple providers share supports for one token, relying on BadCredentialsException alone to guarantee no other provider runs is still insufficient: ProviderManager can proceed to the next provider and accept if the next provider succeeds. To isolate identity domains completely, use **separate Authentication types, separate managers/chains, or unambiguous identity source selection**.

### 4.2. What is ProviderNotFoundException?

When no provider handles the token type and no parent yields a result, ProviderManager may throw:

~~~text
ProviderNotFoundException: No AuthenticationProvider found for ...
~~~

This is a **configuration/token-type error**, not proof that the user typed a wrong password. For example, you create CustomOtpAuthenticationToken while only registering DaoAuthenticationProvider, leaving no provider matching the OTP token.

Distinguish:

- **BadCredentialsException**: a matching provider tried and the credentials were invalid.
- **ProviderNotFoundException**: no provider can handle the Authentication request type under the current configuration.
- **AccessDeniedException**: usually an authorization issue after or outside authentication, not synonymous with ProviderManager failing to find a provider.

## 5. Ordered Selection Algorithm

Suppose ProviderManager has:

~~~text
ProviderManager
  providers[0] = DemoApiKeyAuthenticationProvider
  providers[1] = DaoAuthenticationProvider
  parent       = null
~~~

Request A is UsernamePasswordAuthenticationToken:

1. API-key provider.supports(UsernamePasswordAuthenticationToken.class) returns false -> skipped.
2. DAO provider.supports(...) returns true -> tries user/password.
3. If valid, DAO returns an authenticated Authentication -> ProviderManager stops.
4. If invalid, DAO throws BadCredentialsException -> no more matching providers remain -> request fails.

Request B is DemoApiKeyAuthenticationToken:

1. API-key provider.supports(DemoApiKeyAuthenticationToken.class) returns true.
2. API-key provider checks the key. Key valid -> returns authenticated Authentication -> stops.
3. DAO provider **is not called**, even though it remains in the list.
4. Key invalid -> BadCredentialsException; DAO does not support the custom token so there is no fallback success.

Decision table:

| Input token | API-key provider | DAO provider | Expected outcome |
| --- | --- | --- | --- |
| Alice's UsernamePasswordAuthenticationToken, valid password | supports=false | supports=true, succeeds | Principal alice, ROLE_USER. |
| Alice's UsernamePasswordAuthenticationToken, wrong password | supports=false | supports=true, fails | BadCredentialsException. |
| DemoApiKeyAuthenticationToken with valid demo key | supports=true, succeeds | Not tried | Principal batch-service, ROLE_SERVICE. |
| DemoApiKeyAuthenticationToken with invalid key | supports=true, fails | supports=false | BadCredentialsException. |
| Authentication type supported by nobody | supports=false | supports=false | ProviderNotFoundException. |

**Ordering truly matters** when **multiple providers support the same token type**. With two providers for distinct types as shown above, ordering does not affect normal outcomes, though writing it explicitly still aids readability and testing.

### 5.1. Annotated pseudocode

~~~java
// Pseudocode to understand ProviderManager, not Spring Security source code.
Authentication authenticate(Authentication request) {
    AuthenticationException lastFailure = null;

    for (AuthenticationProvider provider : providers) {
        if (!provider.supports(request.getClass())) {
            continue;
        }

        try {
            Authentication result = provider.authenticate(request);

            if (result != null) {
                return postProcessSuccessfulAuthentication(result);
            }
        } catch (AccountStatusException critical) {
            throw critical; // Stop immediately.
        } catch (InternalAuthenticationServiceException critical) {
            throw critical; // Stop immediately per ProviderManager mechanism.
        } catch (AuthenticationException failure) {
            lastFailure = failure;
            // Can evaluate the next provider.
        }
    }

    // If no result yet, can ask parent AuthenticationManager.
    // Then decide to throw failure or ProviderNotFoundException.
    throw selectFinalFailure(lastFailure);
}
~~~

The pseudocode intentionally omits several Spring Security details such as message sources, event publishing, exception parent, and eraseCredentials. Do not copy it into a project and treat it as Spring Security's implementation.

### 5.2. What if the first provider throws BadCredentialsException?

An easy detail to miss: when the first provider **throws BadCredentialsException**, ProviderManager **can still try subsequent providers**. If a subsequent provider succeeds, that successful result is used and the earlier error can be discarded. If no provider succeeds, the appropriate last exception is usually thrown.

Therefore, you cannot say "the first provider with supports=true has the final word". Supports only filters which providers are eligible to try; **execution results** decide.

### 5.3. Exceptions that stop the search

In Spring Security 6.x ProviderManager, **AccountStatusException** (e.g., locked/disabled account under the corresponding check mechanism) and **InternalAuthenticationServiceException** are early-stop cases that do not continue trying other providers as a bypass. This prevents accidentally consulting another source to bypass account status blocks or internal service failures.

Do not write a custom provider that catches every AuthenticationException and returns null, as that can turn a meaningful failure into a fallback branch. When a failure is an intentional rejection, use the appropriate exception and test that no other provider lets the request slip past the policy.

## 6. ProviderManager with a Parent AuthenticationManager

ProviderManager can have an optional **parent AuthenticationManager**. When the local provider list does not yield a result, the parent may be consulted per Spring Security's supported behavior. This is useful in systems with multiple SecurityFilterChain beans sharing an authentication source while each chain has its own local provider.

~~~text
ProviderManager for /admin/**
  local providers:
    AdminCertificateAuthenticationProvider
  parent:
    SharedProviderManager
      providers:
        DaoAuthenticationProvider
~~~

The model above only explains **manager hierarchy**; a real application must explicitly choose which endpoints allow falling back to username/password and which endpoints require a certificate. If admin policy **mandates a client certificate**, attaching a DAO parent to the admin chain could accidentally allow password login instead of a certificate.

Principles:

- Parent is an **AuthenticationManager**, not necessarily another ProviderManager.
- Not every request reaches the parent: a local provider may succeed first.
- Parent does not mean unconditional fallback after every AuthenticationException; some exceptions stop early.
- When configuring parent/child chains, test the exact **token types**, order, and invalid/locked credential cases.
- Do not create parent cycles between managers.

**Having multiple SecurityFilterChain beans does not by itself prove they share the same ProviderManager.** Each chain can configure its own AuthenticationManager; to know what actually runs, inspect bean wiring and securityMatcher.

## 7. DaoAuthenticationProvider as the Standard Example

**DaoAuthenticationProvider** is the commonly used provider for username/password. It is typically configured with:

- **UserDetailsService**: looks up the account by username, returning UserDetails or signaling not found.
- **PasswordEncoder**: verifies the request's password against the stored password hash.
- **UserDetails**: contains username, hash, account flags (enabled/locked/expired...), and authorities.
- Associated policy/cache/checkers according to configuration.

Model:

~~~text
UsernamePasswordAuthenticationToken
    principal = username
    credentials = raw password from request
            |
            v
DaoAuthenticationProvider
    -> UserDetailsService.loadUserByUsername(username)
    -> Check account status
    -> PasswordEncoder.matches(rawPassword, encodedPassword)
    -> Create authenticated Authentication and authorities
            |
            v
ProviderManager
    -> Return successful Authentication or AuthenticationException
~~~

**DaoAuthenticationProvider does not inspect HTTP bodies or headers itself**. HttpBasic, formLogin, or a custom filter translates HTTP credentials into UsernamePasswordAuthenticationToken. With HTTP Basic, BasicAuthenticationFilter is a key component in the preceding layer.

**Never store plaintext passwords** in real UserDetails. A PasswordEncoder suitable for long-term password storage uses hashing with appropriate work factors, such as BCrypt or an organization-approved encoder. Choice of algorithm/cost should follow the system's security and performance policy.

### 7.1. Must HTTP Basic and form login be two different providers?

**No.** Two different authentication filters can both create UsernamePasswordAuthenticationToken and share a single DaoAuthenticationProvider. Whether the filter reads credentials from a Basic header or an HTML form does not change how passwords are verified.

This separates the **credential transport mechanism** (Basic, form) from the **identity verification provider** (DAO, LDAP, external service). Do not create a new AuthenticationProvider just because you want to change the login page or JSON response.

## 8. Complete Project: ProviderManager with Two Different Provider Types

The following project has:

- A **DaoAuthenticationProvider** verifying HTTP Basic user/password.
- A custom **DemoApiKeyAuthenticationProvider** accepting its own token type.
- A **ProviderManager** containing both providers in a clear order.
- A **SecurityFilterChain** using that exact declared AuthenticationManager.
- Public GET, authenticated GET, and ADMIN-only GET endpoints.
- A test suite calling ProviderManager directly with both token types, alongside testing HTTP Basic with MockMvc.

**Important pedagogical point:** the API-key provider is registered to demonstrate **selection by token type**. This project **does not yet include an HTTP filter converting X-API-Key into DemoApiKeyAuthenticationToken**, so sending an X-API-Key header directly to /api/me **does not automatically create a login**. This behavior is intentionally tested; section 12 explains how to wire the provider into an HTTP authentication flow if needed.

Requires **JDK 17+, Maven 3.9+**, and an available port 8080. Uses fake demo accounts/keys, run only on localhost; real deployments must replace credential issuance and management appropriately.

### 8.1. Directory structure

~~~text
provider-manager-demo/
  pom.xml
  src/main/java/com/example/providers/
    ProviderRoutingApplication.java
    ApiController.java
    DemoApiKeyAuthenticationToken.java
    DemoApiKeyAuthenticationProvider.java
    SecurityConfig.java
  src/test/java/com/example/providers/
    ProviderRoutingTests.java
~~~

All classes share package **com.example.providers** so Spring Boot discovers the beans.

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>provider-manager-demo</artifactId>
    <version>1.0.0</version>

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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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

Spring Boot 3.3.6 manages compatible Spring Security 6.x versions via dependency management; the example does not individually override spring-security-core versions to avoid mismatched library versions.

**Note:** xsd/maven in the schemaLocation line helps tooling understand POM structure. When creating a new Maven project, you can use the official schemaLocation format:

~~~xml
xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd"
~~~

The line above is an attribute fragment of the root element, not a standalone XML tag. In real projects, use one valid and consistent schemaLocation form.

### 8.3. ProviderRoutingApplication.java

~~~java
package com.example.providers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProviderRoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProviderRoutingApplication.class, args);
    }
}
~~~

This class boots Spring Boot and scans Controllers/Configurations in the same package. Do not put code in main to authenticate users manually when receiving HTTP requests.

### 8.4. ApiController.java

~~~java
package com.example.providers;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("name", authentication.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin");
    }
}
~~~

The Controller does not check username/password, API key, or roles from raw headers. Authorization requirements live in SecurityFilterChain; specifically GET /api/admin requires ROLE_ADMIN.

### 8.5. DemoApiKeyAuthenticationToken.java

This is a **new Authentication request type**, distinct from UsernamePasswordAuthenticationToken. It extends AbstractAuthenticationToken and separates the unauthenticated token constructor from the factory that produces an authenticated result:

~~~java
package com.example.providers;

import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class DemoApiKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final Object principal;
    private final String apiKey;

    // Untrusted input: only used after filter/logic receives key.
    public DemoApiKeyAuthenticationToken(String apiKey) {
        super(List.of());
        this.principal = "unverified-api-key";
        this.apiKey = apiKey;
        super.setAuthenticated(false);
    }

    // Result created only after a trusted provider has verified the key.
    private DemoApiKeyAuthenticationToken(
            String principal,
            Collection<? extends GrantedAuthority> authorities) {
        super(authorities);
        this.principal = principal;
        this.apiKey = null;
        super.setAuthenticated(true);
    }

    static DemoApiKeyAuthenticationToken authenticated(
            String principal,
            Collection<? extends GrantedAuthority> authorities) {
        return new DemoApiKeyAuthenticationToken(
            principal, authorities
        );
    }

    @Override
    public Object getCredentials() {
        return apiKey;
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                "Only a verified provider may create an authenticated token"
            );
        }
        super.setAuthenticated(false);
    }
}
~~~

Security decisions:

- The public constructor creates a token with **authenticated=false**. Even if the caller knows the key or not, a new token must not consider itself authenticated.
- The authenticated(...) factory is package-private, used by DemoApiKeyAuthenticationProvider after the key is verified. It does not read client data directly to create authorities.
- Overriding setAuthenticated(true) prevents ordinary code from flipping an unverified token to authenticated via setter.
- The authenticated result **does not keep apiKey in credentials**. This is a better choice than retaining the raw key in SecurityContext.
- However, a package-scoped factory **is not a security boundary against malicious code in the same process**; Java classpath integrity and Spring bean configuration must still be controlled.
- In production, never use a hardcoded static API key; use a secret store, key lifecycle, rotation, revocation, hashing, auditing, and rate limiting.

### 8.6. DemoApiKeyAuthenticationProvider.java

This provider accepts only DemoApiKeyAuthenticationToken, compares the demo key, and creates a service principal with ROLE_SERVICE.

~~~java
package com.example.providers;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class DemoApiKeyAuthenticationProvider
        implements AuthenticationProvider {

    private static final byte[] EXPECTED_KEY =
        "local-demo-key".getBytes(StandardCharsets.UTF_8);

    @Override
    public Authentication authenticate(Authentication input) {
        String presented = (String) input.getCredentials();

        if (presented == null ||
            !MessageDigest.isEqual(
                EXPECTED_KEY,
                presented.getBytes(StandardCharsets.UTF_8))) {
            throw new BadCredentialsException("Invalid API key");
        }

        return DemoApiKeyAuthenticationToken.authenticated(
            "batch-service",
            List.of(new SimpleGrantedAuthority("ROLE_SERVICE"))
        );
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return DemoApiKeyAuthenticationToken.class
            .isAssignableFrom(authenticationType);
    }
}
~~~

**Exact explanation:**

1. ProviderManager calls supports() first. If input is UsernamePasswordAuthenticationToken, it **does not call** the API-key provider's authenticate().
2. With DemoApiKeyAuthenticationToken, the provider reads credentials passed inside the token.
3. Invalid key -> **BadCredentialsException**, without pretending to return a successful Authentication or using null to hide a credential error.
4. Valid demo key -> returns a new token marked authenticated with ROLE_SERVICE.
5. MessageDigest.isEqual helps reduce timing differences compared to standard string equality; **it does not turn a short key in source code into a secure API key management model**.
6. Never log the key value or Authentication#getCredentials().

Because this provider **was already selected by ProviderManager via supports()**, casting or reading credentials for DemoApiKeyAuthenticationToken is valid in the configured flow. If you invoke provider.authenticate() directly with a different token type, you break the standard contract and may encounter errors. A production implementation can add explicit defensive type checking.

### 8.7. SecurityConfig.java

This creates a **concrete ProviderManager** and configures HttpSecurity to use that exact manager.

~~~java
package com.example.providers;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {

        DaoAuthenticationProvider dao =
            new DaoAuthenticationProvider();
        dao.setUserDetailsService(users);
        dao.setPasswordEncoder(encoder);

        DemoApiKeyAuthenticationProvider apiKey =
            new DemoApiKeyAuthenticationProvider();

        return new ProviderManager(List.of(apiKey, dao));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager manager) throws Exception {

        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

**Reading layer by layer:**

- UserDetailsService holds two test accounts in memory: alice/demo-alice and admin/demo-admin. BCryptPasswordEncoder hashes passwords before placing them in UserDetails.
- DaoAuthenticationProvider is configured to authenticate UsernamePasswordAuthenticationToken using UserDetailsService + PasswordEncoder.
- DemoApiKeyAuthenticationProvider handles DemoApiKeyAuthenticationToken; it **does not** check alice's password.
- new ProviderManager(List.of(apiKey, dao)) creates the manager with a concrete order. It can authenticate both Authentication request types per the tests.
- http.authenticationManager(manager) **attaches that exact manager to HttpSecurity**, avoiding assuming the filter uses it automatically just because a bean exists in the context.
- httpBasic(...) sets up the HTTP Basic flow for clients. It sends username/password to AuthenticationManager; **it does not read X-API-Key itself**.
- /api/public is intentionally public; /api/me requires authenticated(); /api/admin requires ROLE_ADMIN; anyRequest().denyAll() restricts unmapped routes.
- SecurityFilterChain **does not transform roles itself**: the ROLE_ADMIN authority is granted by the authenticated UserDetails. The demo API key only has ROLE_SERVICE and therefore is not automatically allowed into /api/admin.

**Version note:** the example uses DaoAuthenticationProvider's no-arg constructor and setters suitable for Spring Security 6.3.x. On newer Spring Security lines, initialization APIs may differ; check the Javadoc for the exact version selected by dependency management.

**Important:** this configuration does not enable formLogin and does not design session/browser login. In real applications, explicitly choose the appropriate mechanism, session policy, HTTPS, secret handling, and CSRF. This lesson uses only GET requests so it does not disable default CSRF.

## 9. Verifying HTTP Basic with curl

Start in the project directory:

~~~bash
mvn spring-boot:run
~~~

If port 8080 is free and the app starts properly, test on localhost. On Windows PowerShell use curl.exe; on Linux/macOS use curl.

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u alice:demo-alice http://localhost:8080/api/me
curl.exe -i -u alice:wrong http://localhost:8080/api/me
curl.exe -i -u alice:demo-alice http://localhost:8080/api/admin
curl.exe -i -u admin:demo-admin http://localhost:8080/api/admin
~~~

**Expected** results:

| HTTP request | Status | Reason |
| --- | --- | --- |
| GET /api/public, no credential | 200 | permitAll(), JSON response message=public. |
| GET /api/me, no credential | 401 | Unauthenticated; HTTP Basic challenge. |
| GET /api/me with alice/demo-alice | 200 | DaoAuthenticationProvider verifies valid password. |
| GET /api/me with alice/wrong | 401 | DaoAuthenticationProvider rejects credential. |
| GET /api/admin with alice/demo-alice | 403 | Alice only has ROLE_USER, lacks ROLE_ADMIN. |
| GET /api/admin with admin/demo-admin | 200 | Principal admin has ROLE_ADMIN. |

HTTP Basic 401 status usually includes **WWW-Authenticate**. Realm name, error body, and extra headers can vary across configurations; you do not need to memorize auxiliary headers byte-for-byte.

If you send:

~~~powershell
curl.exe -i -H "X-API-Key: local-demo-key" http://localhost:8080/api/me
~~~

the result is still **401** in the current project. This is **by design**: the API-key provider is registered in ProviderManager, yet **there is no HTTP authentication filter creating DemoApiKeyAuthenticationToken from X-API-Key**. This demonstrates that adding a provider **does not automatically open a new HTTP login method**.

Similarly, Authorization: Basic ... is how the HTTP Basic filter reads username/password; adding a header like X-Username or X-Role does not make the DAO provider pick them up automatically.

**Lab warning:** fake credentials are for localhost only. HTTP Basic uses Base64 and provides no confidentiality over plain HTTP; real systems must use HTTPS. Never store or share real passwords/tokens in screenshots, logs, or shared command histories.

## 10. Testing ProviderManager and Selection Order with JUnit

Create **src/test/java/com/example/providers/ProviderRoutingTests.java**:

~~~java
package com.example.providers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProviderRoutingTests {

    @Autowired
    AuthenticationManager manager;

    @Autowired
    MockMvc mvc;

    @Test
    void daoProviderAuthenticatesUsernamePasswordToken() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-alice");

        Authentication result = manager.authenticate(request);

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("alice");
        assertThat(result.getCredentials()).isNull();
        assertThat(result.getAuthorities())
            .extracting(a -> a.getAuthority())
            .contains("ROLE_USER");
    }

    @Test
    void daoProviderRejectsWrongPassword() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "wrong");

        assertThatThrownBy(() -> manager.authenticate(request))
            .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void apiKeyProviderAuthenticatesItsOwnTokenType() {
        Authentication request =
            new DemoApiKeyAuthenticationToken("local-demo-key");

        Authentication result = manager.authenticate(request);

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("batch-service");
        assertThat(result.getCredentials()).isNull();
        assertThat(result.getAuthorities())
            .extracting(a -> a.getAuthority())
            .contains("ROLE_SERVICE");
    }

    @Test
    void apiKeyProviderRejectsBadKey() {
        Authentication request =
            new DemoApiKeyAuthenticationToken("bad-key");

        assertThatThrownBy(() -> manager.authenticate(request))
            .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void unknownTokenHasNoSupportingProvider() {
        Authentication request =
            new TestingAuthenticationToken("nobody", "irrelevant");

        assertThatThrownBy(() -> manager.authenticate(request))
            .isInstanceOf(ProviderNotFoundException.class);
    }

    @Test
    void publicEndpointIsAvailableWithoutCredential()
            throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void privateEndpointNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void basicAuthUsesDaoProvider() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void badBasicCredentialIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiKeyHeaderAloneDoesNotCreateAuthentication()
            throws Exception {
        mvc.perform(get("/api/me")
                .header("X-API-Key", "local-demo-key"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin"));
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

**Twelve tests** prove two layers of conditions:

1. **Direct authentication with AuthenticationManager:** username/password uses DAO; custom key uses the custom provider; wrong password/key is rejected; an unsupported token reports ProviderNotFoundException.
2. **Actual HTTP flow at the MockMvc layer:** Basic succeeds and fails as expected; ADMIN role is a separate authorization requirement; X-API-Key is not accepted merely because a provider exists.

The test suite uses Spring Boot test and Spring Security test as declared in pom.xml. If a real project has a different AuthenticationManager or multiple SecurityFilterChain beans, verify the exact manager used by each filter, not just an autowired bean by name.

**Explaining the getCredentials()==null test:** ProviderManager by default attempts to erase sensitive credentials from the resulting Authentication via the CredentialsContainer/eraseCredentials mechanism. When DAO returns UsernamePasswordAuthenticationToken, credentials are normally erased per that token class's behavior. The sample API-key token is designed not to retain the key in the authenticated result from the start.

### 10.1. Why these tests do not cover every production case

- In-memory accounts do not test LDAP, database, IdP backends, or real account lock states.
- MockMvc does not open TLS connections or verify ingress/gateway or trusted proxy headers.
- The demo API key lacks rotation, revocation, expiration, limits/quotas, and real key issuance policies.
- It does not test multiple providers supporting the same token and exception ordering; to use that in production, add tests matching each source's policy.
- Passing status tests do not prove state-changing APIs lack unauthorized side effects; verify DB, messages, and audit logs for write operations.

## 11. Extended Scenario: Two Providers Supporting the Same Token Type

Suppose there are two username/password sources:

~~~text
ProviderManager
  [0] StaffAuthenticationProvider
  [1] CustomerAuthenticationProvider
~~~

Both may return true for supports(UsernamePasswordAuthenticationToken.class). Consider the behaviors:

| First provider | Second provider | Possible conclusion |
| --- | --- | --- |
| Returns null because request is not staff | Checks customer, succeeds | Login succeeds via customer source. |
| Succeeds | Not tried | Staff result is used. |
| Throws BadCredentialsException | Customer may still be tried; if it succeeds, later result wins | Can log in from customer source. |
| Throws BadCredentialsException | Customer also fails | Throws appropriate AuthenticationException; does not become success. |
| Throws AccountStatusException | Not tried further | Stops immediately per ProviderManager policy. |
| Throws InternalAuthenticationServiceException | Not tried further | Avoids treating a system error as another acceptance branch. |

**Risk:** If the same username exists in both staff and customer with two different policies, trying the second source after the first reports a wrong password can create unintended behavior. The fix depends on architecture: separate identity domains clearly, use distinct token types, use a trusted authenticationManagerResolver, or separate chains/filters by protocol. Never rely on provider order to resolve an undefined identity conflict.

A custom provider should implement **supports** for the right token type, return null only when it cannot decide on the request, and throw the appropriate exception when rejecting credentials. If policy requires stopping immediately because an account is locked, do not convert an AccountStatusException into BadCredentialsException hoping the manager will still stop.

### 11.1. Quick ordering exercise

Given the list:

~~~text
[ProviderA, ProviderB, ProviderC]
~~~

And a request with class UsernamePasswordAuthenticationToken:

- A.supports=false.
- B.supports=true, B.authenticate returns null.
- C.supports=true, C.authenticate succeeds.

**Outcome:** A is skipped; B is tried without concluding; C succeeds; the manager returns C's Authentication.

If B returns a successful Authentication, C is not tried. If B throws BadCredentialsException yet C succeeds, C's success can supersede B's error. If B throws an AccountStatusException, the manager stops and C is not tried per ProviderManager's rules.

## 12. What Else Is Needed to Bring a Custom Provider to HTTP?

Registering a new AuthenticationProvider is **not enough** for an X-API-Key header to become an HTTP login mechanism. A complete integration flow is needed:

~~~text
HTTP GET /api/me
X-API-Key: ...
       |
       v
Filter/converter reads header per clear rules
       |
       v
DemoApiKeyAuthenticationToken(isAuthenticated=false)
       |
       v
AuthenticationManager.authenticate(token)
       |
       v
ProviderManager selects DemoApiKeyAuthenticationProvider
       |
       v
Authenticated Authentication
       |
       v
Filter populates SecurityContext / handles success
       |
       v
Authorization checks authenticated()/authority
       |
       v
Controller
~~~

Important implementation factors:

1. **Filter/converter** applies only to designed endpoints and reads headers accurately; validate token size/format and avoid logging keys.
2. **AuthenticationManager** must be the manager containing the right provider. Creating a separate manager inside the filter while another chain uses a different manager easily causes confusing behavior.
3. **Authentication request** must be the type the provider supports. Do not take an apiKey string and put it into UsernamePasswordAuthenticationToken just to reuse DAO.
4. **Success:** the filter needs to attach Authentication to SecurityContext properly and ensure the right context lifecycle. With sessions, check SecurityContextRepository and session persistence; if stateless, avoid retaining Authentication across requests.
5. **Failure:** return 401/challenge per API contract, clearing context if needed; distinguish missing credentials from submitted-but-invalid credentials.
6. **Credential conflict:** if a client sends both Authorization: Basic and X-API-Key, define precedence policy or reject ambiguous requests; do not silently pick whichever happens to work.
7. **Authorization policy:** a service principal with ROLE_SERVICE does not automatically get access to /api/admin. Scopes/permissions/object ownership must still be checked independently.
8. **Filter order** relative to BasicAuthenticationFilter, SecurityContextHolderFilter, CsrfFilter, and AuthorizationFilter affects outcomes; write integration tests covering both success and error paths.
9. **Production key protection:** sufficient key entropy, store keys hashed or via proper secret management, rotation/revocation, TTL if applicable, rate limiting, auditing, and HTTPS.
10. **Object-level permissions:** if an API key represents a service, do not assume it can read every user's data. Design service identities and tenant boundaries clearly.

A custom API-key filter is **not required to prove ProviderManager selection** in this lesson; the project in sections 8–10 directly tested that the right token type routes to the right provider. When adding a filter, write real HTTP tests rather than relying only on supports().

## 13. Successful Authentication Does Not Mean the Request Is Permitted

A request can go through:

~~~text
DaoAuthenticationProvider:
  alice + valid password
  -> Authentication(principal=alice, ROLE_USER)
           |
           v
Authorization for /api/admin:
  requires ROLE_ADMIN
  -> AccessDenied
           |
           v
HTTP 403 (typical)
~~~

ProviderManager **finished its authentication job** when it returned a valid Authentication. Getting 403 on GET /api/admin **is not proof that ProviderManager picked the wrong provider**: the identity is right, but permissions are missing.

Distinguish:

| Error/success | Layer involved | What to inspect |
| --- | --- | --- |
| 200 with valid Basic on /api/me | Both authentication and authorization pass | Principal, authorities, body match the right user. |
| 401 from wrong Basic password | Authentication filter/DAO/entry point | Credentials, UserDetailsService, PasswordEncoder. |
| 401 from missing credentials | Authentication entry point when auth required | Did the request actually send Authorization? |
| 403 from missing ROLE_ADMIN | Authorization | hasRole, ROLE_ADMIN authority, rule order. |
| 403 from POST missing CSRF token | CsrfFilter | Do not immediately blame the password provider. |
| ProviderNotFoundException | AuthenticationManager/provider wiring | Token class and supports(), manager used by filter. |
| InternalAuthenticationServiceException | Authentication backend/provider | DB/LDAP/IdP failure? Do not fall back to a weak source. |
| 404 when fetching an object | Routing/domain or hiding policy | Path, object ownership, policy, and body. |

URL-based authorization alone is also insufficient for IDOR/BOLA: a valid user may only read orders belonging to them. Service/domain code must check owner/tenant/relationship before returning data or causing side effects.

## 14. Credentials Erasure and Impact on Caching

ProviderManager by default attempts to **erase sensitive credential data** from the returned Authentication after successful authentication, if the object supports CredentialsContainer. The goal is to avoid passwords/keys lingering in SecurityContext, sessions, or places holding Authentication.

This **does not mean all sensitive data ever processed has vanished from memory**. An input String can remain until GC, and copies in logs/requests can exist outside Authentication. Therefore minimize secret lifetime, never log raw credentials, and design storage carefully.

### 14.1. Cached UserDetails case

If the successful Authentication holds a direct reference to a UserDetails **sitting in a cache** and eraseCredentials mutates the shared object, the cached UserDetails may lose the password hash needed for the next authentication.

Correct ways to handle this:

- Return/copy a **separate UserDetails** for Authentication instead of sharing a mutable object with the cache.
- Design the cache to hold values that cannot be erased via a reference from the authentication result.
- Check the cache/provider implementation and test multiple consecutive logins.
- Only consider changing eraseCredentialsAfterAuthentication with a clear reason and risk assessment; **disabling credential erasure increases how long sensitive data is retained**.

The demo uses in-memory UserDetails and DaoAuthenticationProvider in a basic configuration. When introducing caching and multiple providers in production, re-test outcomes and credential state.

## 15. Relationship to AuthenticationEntryPoint, FailureHandler, and SecurityContext

ProviderManager is not an HTTP response renderer. It returns an Authentication or throws an AuthenticationException. Its caller is responsible for what follows:

- **BasicAuthenticationFilter** reads HTTP Basic credentials, calls the manager, and handles invalid credentials/entry point appropriately.
- **UsernamePasswordAuthenticationFilter** is used for form login, calling the manager; success or failure can go through AuthenticationSuccessHandler/AuthenticationFailureHandler.
- **Bearer token authentication filter** uses the corresponding Resource Server/JWT/opaque token mechanism.
- **SecurityContextHolder/SecurityContextRepository** handles attaching/saving/restoring the context across sessions and filters.
- **ExceptionTranslationFilter** translates certain downstream AuthenticationException/AccessDeniedException instances into HTTP behavior. Not every error from every authentication filter passes through that filter.
- **AuthenticationEntryPoint** initiates/challenges authentication when needed, such as Basic 401 or redirecting to login depending on the stack.

A successful form login flow usually needs to update SecurityContext and may write a session; that is **not something ProviderManager does itself**. A manager called directly in a unit test only returns a result; it does not create a logged-in HTTP session.

### 15.1. 401, 403, and login redirect

- **401:** usually missing or invalid credentials for challenge-based APIs.
- **403:** principal authenticated successfully but lacks permission, or another mechanism such as CSRF rejected it.
- **302 to /login:** commonly occurs when a web app uses formLogin and an anonymous user needs authentication.
- **ProviderNotFoundException:** error at the manager/provider layer; the HTTP response depends on the configured handler/filter. Do not assume it always maps to one fixed status code.

When debugging, identify **the first component that rejected the request** and log carefully. Looking only at 401 or 403 does not tell you which provider ran.

## 16. Common ProviderManager Configuration Mistakes

### 16.1. Registering a provider, yet the filter does not use that manager

An application may declare an AuthenticationManager bean while a SecurityFilterChain uses its own separate manager. When debugging, inspect http.authenticationManager(...) or the manager the actual authentication mechanism uses; do not look only at the bean list in ApplicationContext.

### 16.2. Wrong class in supports()

A custom provider writes supports only for String.class or Jwt.class while the filter creates a different Authentication subtype -> ProviderManager skips the provider. Inspect **request.getClass()** and the token type created by the filter, rather than guessing from header names.

### 16.3. Too broad supports()

If a custom provider supports all Authentication types, it may receive tokens it does not understand and throw inappropriate errors. Prefer restricting to explicit token classes, and test that requests for other providers remain unaffected.

### 16.4. Returning null when a password/key is wrong

Returning null means yielding to another provider. If credentials have been determined invalid, throw an appropriate AuthenticationException. With multiple providers for the same token type, establish clear identity source boundaries and test provider ordering.

### 16.5. Not distinguishing locked accounts from wrong credentials

When an account is disabled/locked, authentication must preserve account status semantics. Never turn an AccountStatusException into null to let another source "retry".

### 16.6. Trusting a provider merely because the token type matches

Two username/password sources can both support UsernamePasswordAuthenticationToken while relying on different realms. Without safe routing by identity domain, username collisions, wrong role grants, or authenticating against an unintended source can occur.

### 16.7. Not erasing credentials after authentication

Returning an Authentication containing a raw password or API key in principal/credentials/details can leak secrets during serialization, logging, or session storage. Use safe implementations and verify erasure behavior.

### 16.8. Setting ROLE_ADMIN directly from client data

AuthenticationProvider must verify the authority source. An X-Role: ADMIN header or an unverified JWT payload must never become ROLE_ADMIN. Providers should derive authorities from trusted sources and apply least privilege.

### 16.9. Skipping authorization in later steps

A valid Authentication does not grant access to every resource. Enforce roles/permissions/scopes/object policies at URL and service/domain layers as appropriate.

### 16.10. Wrong PasswordEncoder or password hash

PasswordEncoder.matches(rawPassword, storedHash) requires a hash matching the configured algorithm. If code stores raw passwords in UserDetails while the encoder expects a BCrypt hash, login fails. Never "fix" this with NoOpPasswordEncoder in production.

### 16.11. Mixing HTTP Basic and API key without handling credential conflicts

If an HTTP filter accepts both Authorization and X-API-Key, specify precedence rules and what happens when both appear. Avoid having an invalid credential silently "rescued" by another credential when policy requires a single identity.

### 16.12. Opening endpoints by default when no provider is found

If the manager cannot authenticate, requests to protected endpoints must not run business logic. Never catch ProviderNotFoundException and permitAll or attach an anonymous principal with privileged roles.

## 17. Debugging in the Right Order

If a request gets 401 and you suspect ProviderManager picked the wrong provider, check in order:

1. **Identify SecurityFilterChain:** which URL/method matches? Are there multiple chains or a dedicated API chain?
2. **Identify the authentication filter:** HTTP Basic, form login, Bearer/JWT, or custom key? Which filter is actually triggered by the request?
3. **Identify the Authentication request class:** UsernamePasswordAuthenticationToken, BearerTokenAuthenticationToken, or a custom class?
4. **Inspect the provider list in the actual manager:** which providers are in the manager used by the filter, and in what order?
5. **Check supports():** which providers return true for request.getClass()? Which providers are guaranteed to be skipped?
6. **Check authenticate():** did it return null, succeed, or throw an exception? Could a later provider override an error?
7. **Check parent AuthenticationManager:** is there a parent? Why is fallback needed, and does it fit the threat model?
8. **Check credentials:** wrong password, password hash/encoder, disabled/locked account, expired API key, or unavailable IdP?
9. **Check post-success Authentication:** principal, authenticated, authorities, credentials erasure; do not log secrets.
10. **Check authorization:** 401 or 403? If 403, ProviderManager may have succeeded and the issue lies in permissions.
11. **Check context/session:** did the filter persist SecurityContext properly when needed? Does the next request carry valid credentials/session?
12. **Write negative tests:** wrong token type, wrong password, missing role, missing provider, fake key, another user's resource.

**Logging tip:** you can raise Spring Security logging locally to observe filter and authentication decisions, while masking Authorization, Cookie, raw credentials, API keys, and tokens. Do not enable verbose security logging in production just to find a bug quickly.

## 18. Self-Check Questions

1. Is ProviderManager an AuthenticationProvider? **Suggested answer:** No; it implements AuthenticationManager and coordinates AuthenticationProviders.
2. What parameter does supports() accept? **Answer:** Class<?> of the Authentication request, not an HTTP header/path.
3. Does supports() returning true guarantee authenticate() succeeds? **Answer:** No; it may return null or throw AuthenticationException.
4. Provider A returns null, Provider B succeeds: what does the manager do? **Answer:** Uses B's result and stops.
5. Provider A throws BadCredentialsException, Provider B also supports and succeeds: what can happen? **Answer:** B's success can be used; check ordering and policy.
6. First provider throws AccountStatusException: are later providers tried? **Answer:** No under Spring Security 6.x ProviderManager behavior.
7. When does ProviderNotFoundException occur? **Answer:** No matching provider/parent can handle the token.
8. Why doesn't BasicAuthenticationFilter with DaoAuthenticationProvider automatically support X-API-Key? **Answer:** A filter must actively create the right custom Authentication request.
9. A DAO provider authenticates alice successfully, yet /api/admin returns 403. Is ProviderManager broken? **Answer:** No; alice lacks ROLE_ADMIN.
10. Why use a separate token type for API keys? **Answer:** Keeps supports() accurate and separates credentials from username/password.
11. Why is calling setAuthenticated(true) on a client-supplied token dangerous? **Answer:** It bypasses credential verification.
12. Why should a custom provider not return the raw API key in the authenticated Authentication? **Answer:** Risk of exposure via context/session/logs; erase or avoid storing secrets.
13. With multiple SecurityFilterChain beans, can there be multiple ProviderManagers? **Answer:** Yes; chains can configure separate managers or share a parent.
14. A system has JWT and Basic sharing a backend UserDetailsService. Must you use two DaoAuthenticationProviders? **Answer:** No; JWT has its own provider/decoder, Basic uses DAO; identity mapping depends on design.
15. Distinguish BadCredentialsException, ProviderNotFoundException, and AccessDeniedException in one sentence each.

### Memory Checklist

- **AuthenticationManager** is an interface; **ProviderManager** is an implementation using a list of providers.
- **AuthenticationProvider** defines supports(Class<?>) and authenticate(Authentication).
- **supports=false** -> skip provider; **supports=true** -> eligible to try, not guaranteed to succeed.
- **authenticate() returns non-null Authentication** -> success, stop; **null** -> yield; **AuthenticationException** -> handle by type and next provider.
- **ProviderNotFoundException** usually indicates no provider can handle the token request.
- **AccountStatusException/InternalAuthenticationServiceException** can stop the flow immediately to protect policy.
- **Provider order** matters when more than one provider supports the same Authentication type.
- **Parent AuthenticationManager** is an optional fallback that must be designed not to open unintended authentication paths.
- **Credential erasure** limits how long secrets remain inside a successful Authentication.
- **ProviderManager does not set SecurityContext itself, does not emit HTTP 401 itself, and does not grant permissions itself**.
- **Custom headers require a filter/converter creating the right Authentication request type**.
- **Test both authentication and authorization**, both valid and invalid cases, not just HTTP 200.

## References

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): AuthenticationManager, ProviderManager, AuthenticationProvider, and filter overview.
- [ProviderManager JavaDoc — Spring Security 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/authentication/ProviderManager.html): provider ordering, parent, exceptions, and credentials erasure.
- [AuthenticationProvider JavaDoc — Spring Security 6.3](https://docs.spring.io/spring-security/site/docs/6.3.9/api/org/springframework/security/authentication/AuthenticationProvider.html): supports/authenticate contract and null case.
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html): username/password authentication mechanism.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): authorities and authorization decisions after Authentication exists.

**Version:** The project uses Spring Boot 3.3.6 (Spring Security 6.3.x) to illustrate ProviderManager behavior. For projects on newer Spring Security versions, verify the API docs for that exact version, apply patches, and re-verify the project with an actual build/test run.

## Conclusion

ProviderManager is the coordinator of AuthenticationProvider instances for **a specific Authentication request**. It checks supports() by token type, tries registered providers in order, accepts a successful Authentication result, handles null/exceptions, and can consult a parent as configured. **Selecting a provider is only part of the authentication flow**: filters are responsible for putting credentials into the right token and handling SecurityContext/HTTP responses, while authorization decides permission to use endpoints and data after identity has been verified. Understanding these responsibilities clearly helps read logs accurately, configure multiple authentication mechanisms safely, and avoid confusing 401, ProviderNotFoundException, or 403 as bugs in the same component.

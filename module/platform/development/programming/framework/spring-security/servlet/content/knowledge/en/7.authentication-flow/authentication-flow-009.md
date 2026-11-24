# Credential Erasure After Authentication and Impact on User Caches

## 1. The Practical Problem

In a **Spring Security application on the Servlet stack**, a login request typically carries sensitive data such as a password. After authentication succeeds, the application needs to keep the user's **identity** and **authorities** to process requests, yet usually **does not need to retain the raw password** inside the `Authentication` object. Spring Security includes a mechanism that actively erases credentials from the authentication result to shorten the lifetime of sensitive data in memory.

An easily overlooked pitfall: **the principal/`UserDetails` object may be shared with a user cache**. If credential erasure mutates the very object stored in the cache, the cached entry can lose the password hash needed for the next authentication attempt. When that happens, the first request may log in normally, while subsequent requests fail, trigger extra lookups against the data store, or behave inconsistently depending on how the cache is wired.

This lesson helps you:

1. Identify what **`ProviderManager`**, **`Authentication`**, **`CredentialsContainer`**, and **`eraseCredentialsAfterAuthentication`** do.
2. Distinguish **client-submitted password**, **password hash in `UserDetails`**, **authenticated `Authentication`**, and **`UserCache`/`UserDetailsService` cache**.
3. Understand why credential erasure is useful, yet **is not a guarantee that every copy of a secret is wiped from RAM**.
4. Recognize the case where the **same `UserDetails` object** is returned from a cache and then has its password erased.
5. Choose the preferred solution: **keep default erasure enabled, avoid returning the same mutable instance from cache, and pass an independent copy into the authentication flow**.
6. Build a Spring Boot Java 17+ example with HTTP Basic, BCrypt, a simulated user cache, and tests verifying two consecutive authentications.
7. Diagnose the "first login works, second login fails" symptom, especially when caching is enabled in multi-request environments.

**Scope:** Spring Security **Servlet** with username/password authentication via `AuthenticationManager`/`DaoAuthenticationProvider`. Other authentication mechanisms such as bearer JWT, OAuth2/OIDC, or opaque tokens have their own credential/principal models; do not assume every `Authentication` type stores and erases passwords in the same way.

## 2. From Username/Password to Authenticated Authentication

Conceptual flow for form login or HTTP Basic:

~~~text
HTTP request containing username + password
       |
       v
Appropriate authentication filter
       |
       +--> create UNAUTHENTICATED Authentication
       |      principal = username
       |      credentials = client-submitted password
       |
       v
AuthenticationManager (typically ProviderManager)
       |
       +--> Suitable AuthenticationProvider
       |       |
       |       +--> UserDetailsService.loadUserByUsername(username)
       |       |        |
       |       |        +--> load user from DB or cache (with password hash)
       |       |
       |       +--> PasswordEncoder.matches(rawPassword, encodedPassword)
       |       +--> check account status, authorities
       |
       +--> produce AUTHENTICATED Authentication result
       |
       +--> erase credentials from result, when default config applies
       |
       v
SecurityContextHolder -> authenticated Authentication
       |
       v
AuthorizationFilter -> Controller / Service
~~~

**Authentication** describes the current authentication outcome. An `Authentication` may have a **`UserDetails`** principal, **`String` password** or other credentials object, and a collection of **`GrantedAuthority`**. The authenticated result still needs the principal and authorities; normally it does not need the raw password to enforce authorization.

**UserDetailsService** is solely responsible for **looking up user info** by username. It does not authenticate HTTP requests itself, does not decide URL policies, and is not where post-authentication credential erasure is decided. **DaoAuthenticationProvider** uses `UserDetailsService` and `PasswordEncoder` to verify passwords in standard username/password flows.

**PasswordEncoder** may need the password hash in `UserDetails` to call `matches(raw, encoded)`. Therefore default credential erasure happens **after authentication succeeds**, rather than wiping the password hash before verification.

## 3. How Does `ProviderManager.eraseCredentialsAfterAuthentication` Work?

In Spring Security's architecture, **ProviderManager** coordinates matching `AuthenticationProvider`s. After receiving a successful authentication result, `ProviderManager` has a mechanism to erase credentials from the result if enabled.

Notable behavior:

- **eraseCredentialsAfterAuthentication**: normally **true by default** in `ProviderManager`.
- When a successful result exists and implements **CredentialsContainer**, `ProviderManager` calls **eraseCredentials()** on the result.
- Disabling this property stops `ProviderManager` from performing that automatic erasure; turning it off generally keeps sensitive data around longer and is **not the preferred fix** for cache bugs.

Conceptual code, **not verbatim framework source**:

~~~java
Authentication result = provider.authenticate(requestAuthentication);

if (result != null && eraseCredentialsAfterAuthentication
        && result instanceof CredentialsContainer container) {
    container.eraseCredentials();
}

return result;
~~~

Actual behavior also handles provider selection, exceptions, events, parent `AuthenticationManager`s, and other branches. The fragment above highlights only the **post-authentication timing** and the call to **CredentialsContainer**.

### What Is CredentialsContainer?

**org.springframework.security.core.CredentialsContainer** represents an object supporting credential erasure. Its key method is:

~~~java
void eraseCredentials();
~~~

**UsernamePasswordAuthenticationToken** supports credential erasure. In typical implementations, erasure not only nulls out the token's credentials field, it can also **call `eraseCredentials` on related objects if they implement `CredentialsContainer`**.

Notable examples:

- A resulting `UsernamePasswordAuthenticationToken` holding **credentials as the raw password**: after erasure, credentials normally become **`null`**.
- If the **principal is Spring Security's `org.springframework.security.core.userdetails.User`**, that class also implements `CredentialsContainer`: calling erase can set the **password inside the `User` principal** to **`null`**.
- If the principal is a custom `UserDetails` class that does **not** implement `CredentialsContainer`, automatic erasure might **not clear that class's own password fields**. Do not assume every nested object is always cleared.
- If a `UserDetails` object is referenced by multiple components simultaneously, mutating the password on that object becomes visible to the other components.

This does not mean values in the user database are modified. It is a mutation on an **object in JVM memory**, which can affect a cache if the cache holds the exact same object.

### Erasure Does Not Mean Zeroing Every Byte

In Java, **`String` is immutable**. Setting `credentials = null` or clearing a reference field does not guarantee the byte array that once held the password is securely overwritten immediately. Other objects, heap dumps, logs, traces, or copies may already have captured the data earlier.

Therefore combine defenses:
- Never log passwords, `Authorization` headers, or bearer tokens.
- Use HTTPS and protect requests.
- Never store raw passwords in sessions or caches.
- Minimize the lifetime and scope of secrets in memory.
- Protect heap dumps, crash dumps, and production observability tools under security policy.

Spring Security's erasure mechanism **reduces credential retention**, rather than guaranteeing complete wiping of secrets from the entire process.

## 4. Distinguishing Four Places Login Data Can Live

| Storage Location | Typical Contents | Should It Keep Raw Password? | Notes |
| --- | --- | --- | --- |
| Request `Authentication` before verification | Username + raw password from client | Only during necessary processing | Used by filter/provider |
| `UserDetails` from `UserDetailsService` | Username, **password hash**, flags, authorities | **No** | Hash is needed for `PasswordEncoder.matches` |
| Successful `Authentication` in `SecurityContext` | Principal + authorities, authenticated state | Normally **not needed** | `ProviderManager` may erase credentials |
| User cache / `UserDetails` cache | Loaded `UserDetails` to reduce lookups | **No**; may need hash for next authentication | Must avoid sharing an instance that gets erased |

**A password hash is not a raw password**, yet it is still sensitive data. Hashes require proper password-hashing algorithms like BCrypt/Argon2 with appropriate parameters, not a raw fast hash used directly. If a cache stores hashes, it still needs TTL controls, access scoping, password-change handling, and account revocation.

**An authenticated `Authentication` need not always preserve `UserDetails`:** depending on the provider, the principal may be a `String`, `UserDetails`, or an OAuth2/OIDC mechanism object. Exact erasure behavior depends on the object types and `CredentialsContainer` implementations. Never build security logic assuming every principal has `getPassword()`.

## 5. Conflict Point: Cache Holds the Same Object as Principal

Consider a custom `UserDetailsService` written like this:

~~~java
// Illustrates an object-sharing bug; do not put this pattern into production.
public final class SharedInstanceUserDetailsService implements UserDetailsService {

    private final UserDetails cachedUser;

    public SharedInstanceUserDetailsService(PasswordEncoder encoder) {
        cachedUser = User.withUsername("learner")
            .password(encoder.encode("learner-pass"))
            .roles("USER")
            .build();
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        if (!cachedUser.getUsername().equals(username)) {
            throw new UsernameNotFoundException(username);
        }
        return cachedUser; // Returns the EXACT object stored in the cache.
    }
}
~~~

This snippet compiles once Spring Security imports are added in an app with a configured `PasswordEncoder`; its purpose is to show **a flawed implementation**, not an example recommended outside controlled study.

Flow:

~~~text
Attempt 1:
cache.originalUser.password = "$2a$...hash..."
       |
loadUserByUsername -> returns cachedUser itself
       |
DaoAuthenticationProvider creates Authentication(principal = cachedUser)
       |
ProviderManager erases credentials after authentication
       |
UsernamePasswordAuthenticationToken.eraseCredentials()
       |
principal implements CredentialsContainer -> principal.eraseCredentials()
       |
cache.originalUser.password = null  (due to shared reference)

Attempt 2:
loadUserByUsername -> returns the same old cachedUser object
       |
PasswordEncoder.matches(rawPassword, cachedUser.getPassword())
       |
hash is now null -> password check cannot succeed normally
~~~

For a `UserDetailsService` cache that directly returns the same mutable instance, subsequent attempts typically fail authentication or error on a missing password hash, depending on how the provider/encoder handles null. With other caches, the system might fall back to the underlying store, rendering the cache ineffective even though requests still succeed. The key point is not guessing a single 401 code, but recognizing that **the cache was unintentionally mutated** by the security mechanism.

### What Gets Erased?

If the exact same `UserDetails` object resides in:

1. The cache, holding one reference.
2. The `Authentication` principal, holding another reference to the **same instance**.
3. `ProviderManager` calls `eraseCredentials` on the `Authentication`.
4. `Authentication` recursively asks its principal to erase credentials.

Then **the password on the shared instance** is erased. This is **aliasing / reference sharing** in Java. Neither did `PasswordEncoder` overwrite the hash in the database, nor did the framework hunt down and wipe all cache entries.

### Is `UserCache` Enabled by Default?

**Do not assume every app with a `UserDetailsService` has a user cache enabled.** In `DaoAuthenticationProvider`/`AbstractUserDetailsAuthenticationProvider`, `UserCache` is a separate interface whose typical default is **`NullUserCache`** (does not retain user data across lookups). Caching is usually enabled explicitly or added at the `UserDetailsService` layer via a cache such as `ConcurrentHashMap`, Caffeine, Redis, `@Cacheable`, or another proxy.

When using **`InMemoryUserDetailsManager`**, it is an in-memory user store. When writing tests or working with `UserDetails` objects directly, still check whether returned objects share references with the store. Do not infer from the name "in-memory" that every configuration has identical caching or erasure behavior.

If you explicitly configure **`UserCache`** on a provider, watch out for the cache returning the same `UserDetails` instance that subsequently gets erased. In some paths, the provider may fall back to reloading from `UserDetailsService` when cached data fails verification; this can mask the bug while causing redundant queries and making the cache ineffective.

## 6. Preferred Design: Keep Default Erasure and Return an Independent Copy

The stable model is:

- **The cache holds the source record** with username, password hash, account status, and authorities in a protected store.
- **Each authentication attempt receives its own copy** of `UserDetails` rather than the exact instance stored in the cache.
- `ProviderManager` can **erase credentials on the copied principal** without wiping the source record's password hash.
- The next request gets a fresh copy from the intact cached source.
- Password, role, or account-status changes must have an appropriate **cache invalidation/refresh** strategy.

Diagram:

~~~text
Cache (source UserDetails: passwordHash intact)
   |
   +-- create defensive copy #1
   |       |
   |       +--> DaoAuthenticationProvider authenticates successfully
   |       +--> ProviderManager.eraseCredentials()
   |       +--> copy #1.password = null
   |
   +-- create defensive copy #2
           |
           +--> second authentication still has valid password hash
           +--> copy #2 is erased independently
~~~

**Avoid merely copying the reference.** Assigning a new variable like **`UserDetails other = cached;`** still points to the same object. To protect the source, create a new object that shares no mutable fields subject to erasure.

For **`org.springframework.security.core.userdetails.User`**, Spring Security offers **`User.withUserDetails(existing).build()`** to construct a new `UserDetails` from an existing one's values. This suits simple cases where inner components are not accidentally shared mutably.

If a custom principal contains tokens, byte arrays, credential maps, or deeply nested mutable objects, verify a **sufficiently deep defensive copy** matching that structure, avoiding shallow copies that still share sensitive fields.

## 7. Complete Spring Boot Example: Erase Credentials While Keeping the Cache Safe

### 7.1. Versions and Target Outcomes

The example uses **Java 17+**, **Spring Boot 3.3.13**, Spring Security 6, and Maven. The app enables **HTTP Basic** to easily test multiple authentications with curl, uses **`BCryptPasswordEncoder`**, and includes a simulated user cache. `UserDetailsService` itself returns a **fresh copy** on every lookup.

For requests with valid credentials, the `/me` API returns **true** flags confirming credentials on the `Authentication` were erased. After two independent requests, the source cache still retains its password hash—which is what this lesson demonstrates.

Files:

~~~text
credentials-erasure-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/erasure/
    │   ├── ErasureDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── CopyingUserDetailsService.java
    │   └── AccountController.java
    └── test/java/com/example/erasure/
        └── CredentialsErasureTest.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>credentials-erasure-demo</artifactId>
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

Starter dependency versions are managed by the Spring Boot parent; avoid mixing incompatible Spring Framework/Security versions manually. No database is added here: the cache is simply a `ConcurrentHashMap` in a single JVM.

### 7.3. ErasureDemoApplication.java

~~~java
package com.example.erasure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErasureDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErasureDemoApplication.class, args);
    }
}
~~~

All four source classes live in package `com.example.erasure` so Spring Boot discovers `SecurityConfig` and `AccountController`.

### 7.4. CopyingUserDetailsService.java

~~~java
package com.example.erasure;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class CopyingUserDetailsService implements UserDetailsService {

    // Source record stays in cache. Never return this instance directly to the provider.
    private final Map<String, UserDetails> cache = new ConcurrentHashMap<>();

    public CopyingUserDetailsService(PasswordEncoder passwordEncoder) {
        UserDetails learner = User.withUsername("learner")
            .password(passwordEncoder.encode("learner-pass"))
            .roles("USER")
            .build();

        cache.put(learner.getUsername(), learner);
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        UserDetails source = cache.get(username);

        if (source == null) {
            throw new UsernameNotFoundException("Unknown user");
        }

        // Core point: return a new User object, do not share the source instance.
        return User.withUserDetails(source).build();
    }

    // For tests only: reports whether the source cache retains its hash without exposing it.
    public boolean cacheRetainsPasswordHash(String username) {
        UserDetails source = cache.get(username);
        return source != null
            && source.getPassword() != null
            && !source.getPassword().isBlank();
    }
}
~~~

**Key points about this class:**

1. **`cache`** holds a source `UserDetails` with a BCrypt hash.
2. **`loadUserByUsername`** looks up the source yet **returns a new `User` object** via `User.withUserDetails(...).build()`.
3. **`DaoAuthenticationProvider`** can use the password hash on the copy to check the password.
4. **`ProviderManager`** after authentication can erase the password on the copied principal; the source in `ConcurrentHashMap` remains untouched.
5. `cacheRetainsPasswordHash` returns only a boolean for testing. It never returns the password hash and is not a production endpoint.
6. `ConcurrentHashMap` supports concurrent access, yet **does not solve TTL, invalidation, password changes, account lockout, or distributed caching**. Those must be designed separately for real systems.

This is a learning cache. Real systems may store `UserDetails` in Caffeine/Redis or another data store; the principle of not sharing the erased object applies to every implementation with a mutable principal.

### 7.5. SecurityConfig.java

~~~java
package com.example.erasure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    CopyingUserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new CopyingUserDetailsService(encoder);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
~~~

**Design choices explained:**

- The **`CopyingUserDetailsService`** bean implements `UserDetailsService`, used by Spring Security as the user store for username/password authentication. When Spring Security creates the standard provider, the `PasswordEncoder` bean enables BCrypt hash verification.
- **`httpBasic`** accepts credentials on every request. The username/password pair in a Basic header is only Base64-encoded, not secure encryption; HTTPS is mandatory in production.
- **`SessionCreationPolicy.STATELESS`** prevents Spring Security from relying on `HttpSession` to remember `Authentication` across requests; thus subsequent calls with credentials are re-verified independently, clearly revealing cache behavior.
- **`formLogin(disable)`** avoids redirecting to a login page and ensures credential-less requests to `/me` receive 401 from the Basic mechanism.
- **Do not configure `ProviderManager.setEraseCredentialsAfterAuthentication(false)`.** The example intentionally keeps default credential erasure so you can observe both the erased principal and the intact cached source.
- The example uses GET only. If extending to POST/PUT/DELETE, do not automatically disable CSRF just because HTTP Basic/`STATELESS` is used: browsers can automatically attach cached Basic credentials, so you must still evaluate the threat model and CSRF defenses.

**Note:** `SessionCreationPolicy.STATELESS` is not a credential-erasure feature. It governs saving/loading `SecurityContext` across requests. The two policies address separate responsibilities.

### 7.6. AccountController.java

~~~java
package com.example.erasure;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        Object principal = authentication.getPrincipal();

        boolean principalPasswordErased =
            principal instanceof UserDetails details
                && details.getPassword() == null;

        return Map.of(
            "username", authentication.getName(),
            "credentialsErased", authentication.getCredentials() == null,
            "principalPasswordErased", principalPasswordErased
        );
    }
}
~~~

`/me` returns only **boolean flags** to demonstrate the erasure mechanism. Never return raw passwords, password hashes, `Authorization` headers, or full `Authentication` objects. In this `UserDetails` flow, the principal is `org.springframework.security.core.userdetails.User`, so `principalPasswordErased` is expected to be true after `ProviderManager` processes the result.

Do not reuse this `principalPasswordErased` check as an authorization condition. For JWTs or custom principals, a password is not necessarily a meaningful property. **Erasing credentials** and **authorizing access** are two distinct responsibilities.

## 8. Running the Application and Observing Two Authentications

Inside `credentials-erasure-demo` where `pom.xml` resides:

~~~bash
mvn spring-boot:run
~~~

Open another terminal. On older PowerShell, use **`curl.exe`** instead of the `curl` alias if needed.

### 8.1. Unauthenticated Request

~~~bash
curl -i http://localhost:8080/me
~~~

Key output:

~~~http
HTTP/1.1 401
WWW-Authenticate: Basic realm="Realm"
~~~

Exact headers may vary by configuration or container, yet the response carries no `/me` payload because the caller is unauthenticated.

### 8.2. First Valid Request

~~~bash
curl -i -u learner:learner-pass http://localhost:8080/me
~~~

Expected key output is **HTTP 200**, with JSON values:

~~~json
{
  "username": "learner",
  "credentialsErased": true,
  "principalPasswordErased": true
}
~~~

JSON key ordering is not guaranteed. **`credentialsErased = true`** means the resulting `Authentication` no longer holds credentials in that field. **`principalPasswordErased = true`** means the `User` principal in this flow had its password erased. Do not conclude that every copy of the password in the JVM was zeroed out.

### 8.3. Second Valid Request

Run the same command again:

~~~bash
curl -i -u learner:learner-pass http://localhost:8080/me
~~~

The result must still be **HTTP 200** with the same flags. Because `UserDetailsService` returns a **fresh copy** for each authentication, the original password hash in the cache is not lost after the first request.

### 8.4. Request with Wrong Password

~~~bash
curl -i -u learner:wrong-pass http://localhost:8080/me
~~~

Key output is **401 Unauthorized**. Having the valid hash intact in the cache **does not** allow a wrong password to pass.

### 8.5. Public GET Request

~~~bash
curl -i http://localhost:8080/public
~~~

Key output is **200 OK** with JSON `message = "public"`. This endpoint requires no credentials.

| Request | Expected Status | What Is Verified |
| --- | --- | --- |
| GET `/me` without Basic header | 401 | Unauthenticated, unauthorized |
| GET `/me` valid Basic, 1st time | 200 | Password verified, credentials on successful `Authentication` erased |
| GET `/me` valid Basic, 2nd time | 200 | Source cache retains hash thanks to defensive copy |
| GET `/me` Basic wrong password | 401 | Cache does not bypass credential verification |
| GET `/public` without Basic header | 200 | Public access allowed |

The HTTP calls above show only request outcomes. Automated tests in the next section directly verify that the **source cache still retains its password hash** after both requests, avoiding inferences from status 200 alone.

## 9. Automated Testing with MockMvc: Proving the Cache Is Not Erased

Create **src/test/java/com/example/erasure/CredentialsErasureTest.java**:

~~~java
package com.example.erasure;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CredentialsErasureTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    CopyingUserDetailsService users;

    @Test
    void credentialsAreErasedButCacheCanAuthenticateAgain() throws Exception {
        assertTrue(users.cacheRetainsPasswordHash("learner"));

        mvc.perform(get("/me").with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.credentialsErased").value(true))
            .andExpect(jsonPath("$.principalPasswordErased").value(true));

        // This checks the original object in cache, not the copied principal.
        assertTrue(users.cacheRetainsPasswordHash("learner"));

        mvc.perform(get("/me").with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.credentialsErased").value(true))
            .andExpect(jsonPath("$.principalPasswordErased").value(true));

        assertTrue(users.cacheRetainsPasswordHash("learner"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/me").with(httpBasic("learner", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCredentialsAreRejected() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

This test verifies **two simultaneous states**:

1. The principal in the `Authentication` result had its credentials erased, reducing secret retention.
2. The source record in the cache still retains its password hash to authenticate the next independent request.

If you temporarily replace **`return User.withUserDetails(source).build();`** with **`return source;`** in `CopyingUserDetailsService`, the test can detect that the cache lost its hash after the first authentication. Only run that experiment locally in a draft and then restore the defensive copy. Exact HTTP behavior can depend on provider and version, while **`assertTrue(cacheRetainsPasswordHash(...))`** directly tests object-sharing corruption.

### Distinguishing Mockito Tests from Integration Tests

Heavy mocking of `PasswordEncoder` or `DaoAuthenticationProvider` can bypass the real `eraseCredentials` call altogether. The `MockMvc` tests above execute through the Spring Security filter chain and HTTP Basic flow with the application's actual provider, making them far better suited to observe multi-component interactions.

If the application uses a custom `AuthenticationManager` instead of Spring's auto-configured setup, tests must ensure that manager is actually used. Never claim "erasure works" simply by calling `eraseCredentials` manually in a unit test without verifying requests traverse `ProviderManager`.

## 10. At Which Layer Should You Fix the Cache Bug?

Not every application uses the same caching architecture, so identify which object is being shared.

### Case A: `UserDetailsService` Has Its Own Cache

For example, `UserDetailsService` uses a `Map` or `@Cacheable` to return `UserDetails`.

**Risk:** the returned object is the exact object stored in the cache. If the principal holds the same instance and implements `CredentialsContainer`, the cache loses its hash.

**Solution:** the repository/cache keeps the source object; at the `loadUserByUsername` boundary, return an **independent copy**. For custom `UserDetails`, ensure the copy is truly independent for any fields that can be mutated or erased.

### Case B: Configuring `UserCache` on `DaoAuthenticationProvider`

Some applications explicitly enable `UserCache` on the provider to avoid calling `UserDetailsService` on every authentication.

**Risk:** the provider may store the exact `UserDetails` instance that the `Authentication` principal references and which gets erased post-authentication. On the next read, the cached entry lacks a hash, forcing the provider to reload or fail depending on the path. A reload fallback might make the system "still log in", yet defeats caching efficiency.

**Solution:** inspect the paths for **putting into cache**, **reading from cache**, **placing principal on `Authentication`**, and **calling erase**. Evaluate copy-on-write/copy-on-read or another cache design so mutable erased instances are never shared. Verify with a test running two real authentications.

### Case C: Custom `UserDetails` Implementing `CredentialsContainer`

A custom object might implement:

~~~java
@Override
public void eraseCredentials() {
    this.passwordHash = null;
}
~~~

This is a **fragment of a custom class**, not a standalone program. If the same object is cached, the same side effect occurs. Trying to work around it by making `eraseCredentials` a no-op can keep credentials on the principal longer than intended.

**Solution:** clearly separate which object serves as the **cached identity record** and which serves as the **authenticated principal**, letting erasure mutate only instances meant to be cleared. Never use a single mutable JPA entity as both the cache entry and the per-request principal.

### Case D: Custom `AuthenticationProvider`

A custom `AuthenticationProvider` might return an `Authentication` where:

- `credentials` holds the raw password;
- `principal` is an entity carrying the password hash;
- `details` contains sensitive data;
- objects fail to implement `CredentialsContainer` properly.

**Risk:** even with `ProviderManager`'s default erasure enabled, it only clears supported objects; sensitive fields outside the contract remain.

**Solution:** design successful `Authentication` results with minimal data, preferring a principal without passwords or properly implementing `CredentialsContainer`. For custom providers, verify the result after erasure and confirm neither cache nor data stores are corrupted.

### Case E: Principal Already Stored in `HttpSession`

After form login, `SecurityContext` can be persisted via `HttpSession`. If `Authentication` was erased before saving, the principal may retain username and authorities without the password. **This is normally desirable**, since subsequent session requests do not need the hash to re-verify the password.

Never write business logic that relies on **`authentication.getCredentials()`** or **`((UserDetails) principal).getPassword()`** after login. Those values may already be erased and are not an API for reading logged-in passwords.

## 11. Should You Disable `eraseCredentialsAfterAuthentication`?

`ProviderManager` has a setter:

~~~java
providerManager.setEraseCredentialsAfterAuthentication(false);
~~~

This is an **illustrative single line on an existing `ProviderManager`**, not a complete Spring Boot configuration to paste. It prevents `ProviderManager` from calling erase on successful results, so it is occasionally mentioned as a workaround for caches with shared objects.

However, **do not treat it as the default solution**:

- Raw passwords or other credentials can linger longer inside `Authentication`.
- `Authentication` can be placed in `SecurityContext` and stored in `HttpSession`, caches, or observability tools.
- The underlying design bug of sharing a mutable object between cache and principal remains unfixed.
- When the app changes authentication mechanisms, the consequences of retaining credentials can be hard to spot.
- Future readers may assume credentials are erased by standard defaults when you actually disabled it.

**Preferred approach:** keep default erasure enabled and **separate cached source records from principal objects**. Only consider disabling it after evaluating special requirements, threat model, `Authentication` storage, and testing secret retention.

### Never Null Out the Password Hash in the Database

Calling `eraseCredentials` on a successful `UserDetails` object does **not** mean updating the password hash in the database to null. The password hash is needed for the next username/password login. Only remove or change database hashes for explicit workflows such as password resets/changes, policy-driven account lockouts, or proper account deletion.

## 12. Boundaries with SecurityContextRepository, Sessions, and Statelessness

Three concepts often appear together yet do different jobs:

| Concept | Question It Answers | Primary Effect |
| --- | --- | --- |
| **`ProviderManager` / `eraseCredentialsAfterAuthentication`** | Does the authentication result still retain credentials? | Mutates sensitive fields on successful `Authentication` |
| **`SecurityContextHolder` / `SecurityContextRepository`** | Where is the authentication context used and saved/loaded? | Maintains `Authentication` within or across requests |
| **`SessionCreationPolicy`** | How does Spring Security create/use `HttpSession`? | Determines stateful vs stateless strategy at the chain level |

Examples:

- With **form login + session**, login runs once, the erased `Authentication` can be saved in the session, and subsequent requests reload the identity. No password hash on the principal is needed for every page view.
- With **stateless HTTP Basic**, each request carries Basic credentials and may run authentication anew; `UserDetailsService` can be invoked repeatedly. Thus a `UserDetails` cache losing its password hash quickly surfaces failures on the very next request.
- With **OAuth2 Resource Server + bearer token**, per-request token validation can produce a different `Authentication` type; erasure behavior and principal shape depend on the token/provider. Do not project the password-hash `UserDetails` model onto every resource server.

**Important:** Erasing credentials does not mean logging out and does not revoke permissions in `SecurityContext`. As long as `Authentication` retains valid principal/authorities, the current request can still be authorized. Conversely, choosing `STATELESS` does not automatically disable credential erasure.

## 13. Handling Password Changes, Role Changes, and Account Disabling with a Cache

Protecting objects from erasure is a **necessary condition**, not the entire secure cache design.

### Password Changes

If the database updates a password hash while the cache holds the old hash, users may keep authenticating with the old password until the cache refreshes or evicts, depending on architecture. Implement invalidation on password change and test when changes take effect.

### Role Changes or Account Locking

If authorities or account flags stay cached too long, users whose roles were revoked or accounts were locked may still be accepted using stale cache entries. Set suitable TTLs and eviction; high-sensitivity systems may need authoritative status checks at critical operations.

### Multi-Node Synchronization

A `ConcurrentHashMap` cache lives only inside a single JVM. Different nodes may hold different versions of `UserDetails`. Share invalidation signals or adopt a distributed caching strategy when running multiple production instances.

### Never Cache Raw Passwords

User caches should generally store only the **password hash**, account status, and required authorities. Never store raw passwords, session cookies, or `Authorization` headers as cache keys or values.

### Avoid Information-Leaking Keys and Logs

Use stable keys for user records; avoid putting passwords or tokens in cache keys. Use redacted logs, cache access controls, and managed telemetry so sensitive data never leaks.

### Consider Cache Misses, Concurrency, and Thundering Herd

When a user entry is evicted, concurrent requests may hit the database simultaneously. Use synchronized/throttled cache loaders under heavy load, and ensure each `Authentication` receives consistent data after password or role changes. Avoid holding global locks across network calls without clear design.

## 14. Diagnosing "First Login Works, Second Login Fails"

Follow this sequence instead of immediately disabling erasure:

1. **Confirm the flow type:** stateful form login with session, or stateless HTTP Basic/JWT? Do subsequent requests actually re-authenticate?
2. **Confirm the right chain:** which `SecurityFilterChain` handles that path? Are there multiple chains with different `SessionCreationPolicy` settings?
3. **Confirm the `AuthenticationManager`:** is it a standard `ProviderManager` with default `eraseCredentialsAfterAuthentication` enabled?
4. **Check the principal type:** does `UsernamePasswordAuthenticationToken` hold a `UserDetails` implementing `CredentialsContainer`? Does a custom provider return another principal type?
5. **Check the `UserDetails` source:** does `UserDetailsService` use `@Cacheable`, a `Map`, `UserCache`, or another caching library?
6. **Check reference sharing:** does the cache return the exact instance or a fresh copy? Are nested mutable credentials shared?
7. **Inspect after a successful request:** is the password hash **on the source cached `UserDetails`** intact or null? Check safely in tests without printing hash values.
8. **Observe the next request:** is there a cache hit, a fallback reload from `UserDetailsService`, an authentication failure, or a retry?
9. **Check real user updates:** are passwords, roles, account locks, TTLs, and invalidation leaving the cache stale?
10. **Try an independent copy:** keep default erasure enabled, add defensive copying, rerun two requests, and assert the cache hash stays intact.

**Never log raw credentials**, encoded passwords, `Authorization` headers, or full principals to "prove" the bug. Tests need only boolean/identity assertions and source-load counters if desired.

### Common Symptoms

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| First request 200, second request 401 | `UserDetails` cache shares the same object and gets its password erased | Return a defensive copy; keep cache source independent |
| Requests still 200 yet DB queries spike after first call | Provider falls back to reloading `UserDetails` because cached object was wiped | Check `UserCache` object identity, copying, or cache strategy |
| `Authentication` principal password is null | Erasure is working | Usually **expected**, not a bug unless business logic wrongly depends on password |
| Cache source password is null | Cache was unintentionally mutated | Separate source instance from principal |
| Old password still works after password change | Stale cache, missing invalidation | Evict/reload at the right point; test revocation |
| Revoked role still takes effect | Stale cached authorities or old session | Design session/authority refresh and cache eviction policies |
| Disabling erasure makes login work again | Likely masking a reference-sharing bug | Re-enable erasure and fix how the cache returns `UserDetails` |
| Fails only under concurrent requests | Shared mutable `UserDetails` or unsafe cache updates | Review concurrency, snapshotting/copying, and atomic updates |

## 15. Misconceptions to Avoid

**Misconception 1: Credential erasure also deletes the password hash from the database.**  
False. `ProviderManager`/`Authentication` operate on JVM objects; updating the database requires an explicit persistence operation.

**Misconception 2: The `Authentication` principal always holds the raw password.**  
False. The principal can be `UserDetails`, a `String`, or another object; raw passwords normally live on the input credentials and may be erased from the result.

**Misconception 3: A user cache is always active whenever `UserDetailsService` exists.**  
False. `DaoAuthenticationProvider` does not cache users by default. Caching layers are explicitly added by the application.

**Misconception 4: Turning off erasure is the standard fix for cache issues.**  
Not recommended. Fix the shared object instead and keep secret-retention minimization enabled wherever possible.

**Misconception 5: Copying means assigning to a new variable.**  
False. Assigning the same reference does not separate instances; perform a real clone/copy and inspect nested mutable fields.

**Misconception 6: Once erased, every password byte is guaranteed gone from RAM.**  
False. Java `String` is immutable, and copies, logs, or dumps may still exist; erasure reduces retention duration, not a magic zeroization guarantee.

**Misconception 7: Erasing credentials logs the user out.**  
False. The `Authentication` result still retains its principal and authorities, preserving valid authorization.

**Misconception 8: If HTTP Basic sends the password every time, the cache needs no hash.**  
False. The server still needs the stored hash (or authoritative verifier) to check the incoming request's credentials.

## 16. Self-Check Exercises

### Exercise A — Distinguishing Two `UserDetails` Copies

A cache holds a `UserDetails` object named `cachedUser`. `UserDetailsService` returns `cachedUser` directly, and `DaoAuthenticationProvider` sets it as the principal. `ProviderManager` succeeds and erases credentials. Afterward, `cachedUser.getPassword()` becomes `null`. Why?

**Answer:** `principal` and `cachedUser` point to the same instance, and the principal implements `CredentialsContainer`. Erasure mutates the shared object, so the cache sees a null password.

### Exercise B — Fixing the Cache

Fix the return statement in `UserDetailsService` to avoid corrupting `cachedUser`.

~~~java
return User.withUserDetails(cachedUser).build();
~~~

**Explanation:** constructs a new `UserDetails` as the principal; the cached source is untouched when the new instance is erased. For custom user types, copy all relevant fields and share no mutable credentials.

### Exercise C — Misguided Configuration

A teammate suggests changing `SessionCreationPolicy` from `STATELESS` to `IF_REQUIRED` to "prevent losing the hash on the cache". Does this solve the root cause?

**Answer:** No. Session policy governs session usage, not the erasure of a shared `UserDetails` instance. Fix the copying/cache boundary.

### Exercise D — Checking After Erasure

In a username/password flow, `Authentication.getCredentials()` returns `null` after successful authentication, yet the principal still has username and authorities. Is this a bug?

**Answer:** Normally expected. Once authenticated, the raw password is not needed for authorization; `Authentication` retains identity and authorities.

### Exercise E — Why HTTP 200 Alone Is Not Enough

A user cache loses its password hash after the first request, yet subsequent requests still return 200 because the provider reloads from the DB. Can you conclude the cache is healthy?

**Answer:** No. Inspect the source object in cache, cache hit/miss counts, user-load frequency, and erasure effects; provider fallback can mask the issue.

### Exercise F — Choosing a Security Strategy

There are two options: (1) disable `eraseCredentialsAfterAuthentication`; (2) keep default erasure and return a defensive copy from cache. For typical applications, which should you choose?

**Answer:** Prefer (2) to keep the cached source password hash intact while minimizing retention of raw credentials post-authentication. Option (1) requires thorough security review for a specific exception.

### Exercise G — Stale Cache

A user changes their password in the DB while the cache retains the old hash, and `UserDetailsService` returns copies of the stale cache entry. Does defensive copying prevent login with the old password?

**Answer:** No. Defensive copying solves aliasing/erasure; stale caches require TTL, eviction, or authoritative data refresh mechanisms.

## 17. Pre-Production Checklist

- [ ] Understood that **`ProviderManager.eraseCredentialsAfterAuthentication`** is normally enabled by default.
- [ ] Distinguished **raw password**, **password hash**, **principal**, **`Authentication`**, and **cached `UserDetails`**.
- [ ] If using a `UserCache`/`UserDetailsService` cache, checked for aliasing with the principal.
- [ ] Implemented **defensive copying** or proper data boundaries before mutable cached instances are exposed to erasure.
- [ ] Tested **at least two consecutive successful authentications** and verified the source cache is not unintentionally modified.
- [ ] Tested wrong passwords, nonexistent users, locked/expired accounts, and invalidation after password changes.
- [ ] Defined TTL/eviction policies for password hashes, roles, and account states.
- [ ] Never disabled erasure merely to hide a cache bug; if an exception forces disabling it, completed security review and credential-retention tests.
- [ ] Never logged raw passwords, password hashes, cookies, `Authorization` headers, or full `Authentication` objects.
- [ ] Never used `Authentication.getCredentials()` or `principal.getPassword()` as business data after login.
- [ ] For multi-node or async setups, evaluated cache consistency, propagation, and object sharing.
- [ ] Understood that erasure does not wipe secrets from all RAM copies and does not replace encryption or access controls.
- [ ] Verified behavior against the application's actual `AuthenticationProvider` and `Authentication` implementations, especially with OAuth2/JWT or custom providers.

**Remember:** After username/password authentication, **`ProviderManager`** normally erases credentials from `Authentication` to reduce retention of sensitive data. If the principal is the exact **`UserDetails` object** held in a cache, erasure can wipe the cache's password hash. The preferred fix is to **keep default erasure enabled, separate cached source instances from authentication instances, test consecutive requests**, and manage cache invalidation on password, role, or account-state changes.

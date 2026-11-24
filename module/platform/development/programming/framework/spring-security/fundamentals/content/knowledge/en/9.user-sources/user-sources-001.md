# UserDetailsService Loads User Data and Does Not Verify Passwords Itself

In Spring Security, `UserDetailsService`, `DaoAuthenticationProvider`, and `PasswordEncoder` are often used together for username/password login. They collaborate, yet **they do not perform the same job**:

- **`UserDetailsService`**: receives a **username**, looks up and loads account data, and returns a `UserDetails` containing the username, password hash, authorities, and account status.
- **`DaoAuthenticationProvider`**: receives an untrusted authentication request, uses `UserDetailsService` to retrieve the user, verifies the password via `PasswordEncoder` along with status conditions, and then returns a verified `Authentication` or throws an exception.
- **`PasswordEncoder`**: provides `encode` to generate a hash when setting/changing a password and `matches(rawPassword, storedHash)` to match during authentication.

**Finding a user does not mean login succeeded.** Someone may know the username `alice` and cause the application to find Alice's account, yet that alone grants no right to access Alice's data. Only the provider that verifies credentials and account conditions may establish a trusted authentication.

This lesson uses **Spring Boot 3, Spring Security 6.5, Java 17+, and Spring MVC/Servlet** as examples. A standalone Java 17 program at the end helps you directly observe the difference between lookup and password check. The Spring Boot snippets require an appropriate Gradle/Maven setup; they cannot be compiled separately with `javac` if libraries are missing. For Spring Security 7 or WebFlux, refer to the reference/Javadoc corresponding to the version and stack you are using.

## 1. Responsibility Boundary Table

| Component | What does it receive? | What does it do? | What does it return? | What does it not do itself? |
| --- | --- | --- | --- | --- |
| `UserDetailsService` | `String username` | Queries the user source by name | `UserDetails` or `UsernameNotFoundException` | Does not verify raw password, does not create login session |
| `UserDetails` | Loaded from user source | Carries hash, authorities, flags, and username | Data via getters | Does not itself decide whether password is correct |
| `PasswordEncoder` | Raw password, encoded password | Hashes and matches | Hash `String` or `boolean` from `matches` | Does not look up users or decide URL permissions |
| `DaoAuthenticationProvider` | Username/password `Authentication` | Lookup + account checks + password matches | Trusted `Authentication` or exception | Does not itself authorize per owner/tenant |
| `AuthenticationManager` / `ProviderManager` | Unauthenticated `Authentication` | Delegates to the appropriate provider | Resulting `Authentication` or exception | Does not itself emit HTTP response |
| `SecurityFilterChain` | HTTP request | Integrates filters, authentication, authorization, exploit protection | Allows continuation or blocks request | Does not automatically know all business policies |

Let us separate two propositions:

1. "Found Alice's account and retrieved the stored hash" → **data reading** succeeded.
2. "The password provided by the client matches the hash, the account is valid, and the provider accepts" → **authentication** succeeded.

`UserDetailsService` is responsible for the first proposition. `DaoAuthenticationProvider` and the authentication components are responsible for the second proposition.

## 2. Exact Contract of UserDetailsService

The interface belongs to package `org.springframework.security.core.userdetails` and has exactly one core method:

```java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
```

This is a simplified form from the API for learning purposes.

You can immediately see:

- The parameter is only **username**. There is no `password`, `HttpServletRequest`, `Jwt`, or client-claimed role list.
- The result is a `UserDetails` populated with the data needed by the provider; there is no "password valid/invalid" boolean in the result.
- If the user is not found, the contract uses `UsernameNotFoundException`. You should not return `null` to indicate that the user does not exist.
- The interface itself only **reads** users. To create/update/delete users, you may need `UserDetailsManager` or another business service; changing passwords/hashes has its own mechanism.

This snippet is a lookup, not a login:

```java
UserDetails user =
    userDetailsService.loadUserByUsername("alice");

String username = user.getUsername();
String storedHash = user.getPassword();
var authorities = user.getAuthorities();
```

This is a fragment requiring Spring Security imports and a `userDetailsService` bean. `storedHash` is the password encoded when creating/changing the password, **not the raw password the client just entered**. Do not print password hashes in logs or return them via API.

### 2.1. Why is there no password parameter?

`DaoAuthenticationProvider` has access to the raw credentials from the `UsernamePasswordAuthenticationToken` created by the authentication filter. It only needs the service to find the account record, while password matching is the responsibility of the provider/`PasswordEncoder`. Thanks to this boundary:

- A user source can be fetched from memory, JDBC, or a custom repository;
- Password hashing/migration rules are managed in a dedicated place;
- Lookup can be unit tested without simulating HTTP login;
- Changing the data source does not require rewriting all password authentication;
- The provider can also check account status, credentials expiry, and other constraints.

If the system uses OTP, certificates, LDAP bind, or mechanisms not based on standard password hashes, you may need a specialized `AuthenticationProvider`/flow. Do not invent a `loadUserByUsername(username, password)` method and assume the default provider will call it.

### 2.2. Usernames may differ in case

The `UserDetailsService` Javadoc allows implementations to look up usernames case-sensitively or case-insensitively. For example, looking up `ALICE` may return a `UserDetails` with the normalized username `alice` if the data source is designed that way. Choose consistent normalization/unique index conventions across registration, login, and email changes.

If a username is only unique **within a tenant**, you must design how to identify the tenant within an appropriate trust boundary. Do not blindly treat a client-sent `X-Tenant-Id` or form field as proof of permission to access that tenant.

## 3. What data does UserDetails contain?

`UserDetails` typically has the following APIs:

| Method | Data | Who uses it? |
| --- | --- | --- |
| `getUsername()` | Loaded username | Provider and identity code |
| `getPassword()` | Encoded password / hash | Provider + PasswordEncoder |
| `getAuthorities()` | Roles and permissions | Resulting Authentication, authorization |
| `isEnabled()` | Is it allowed to operate? | Provider |
| `isAccountNonLocked()` | Is the account not locked? | Provider |
| `isAccountNonExpired()` | Is the account still valid? | Provider |
| `isCredentialsNonExpired()` | Are credentials still valid? | Provider |

Reading `UserDetails` does not mean putting all of this data into a JSON response; password hashes, account flags, and internal permissions may be sensitive information.

### 3.1. Authorities do not come from the request body

With username/password, roles/permissions should come from a user store or trusted server-controlled source:

```text
Account Alice:
    username = alice
    passwordHash = BCrypt(...)
    authorities = [ROLE_USER, report:read]
    enabled = true
```

Only after valid authentication do the authorities become meaningful as input for rules like `hasRole("ADMIN")` or `hasAuthority("report:read")`. Never trust a client-sent `roles: ["ROLE_ADMIN"]` array and create an `Authentication` marked as authenticated.

### 3.2. UserDetails does not have to be a JPA entity

A JPA entity may contain lazy relationships, business data, sensitive fields, and mutability. It is usually better to map `Account`/`Role` → `UserDetails` or a dedicated principal DTO, rather than returning the entity directly:

- Avoids `LazyInitializationException` when the provider reads permissions after the transaction;
- Avoids pulling in unnecessary relationship lists;
- Avoids accidentally serializing password/hash/address or personal data;
- Avoids sharing a reference that could have credentials erased;
- Keeps a boundary between the identity used for login and the domain object used for business logic.

## 4. Authentication flow from filter to controller

```text
Client: username + raw password
             |
             v
SecurityFilterChain
   |
   +-- BasicAuthenticationFilter / form login filter
   |       |
   |       +-- UsernamePasswordAuthenticationToken
   |             principal = claimed username
   |             credentials = raw password
   |             authenticated = false
   |
   v
AuthenticationManager / ProviderManager
   |
   v
DaoAuthenticationProvider
   |
   +-- UserDetailsService.loadUserByUsername(username)
   |       +-- Look up user from DB / memory
   |       +-- Return UserDetails with storedHash, authorities, flags
   |
   +-- Check account flags
   |
   +-- PasswordEncoder.matches(rawPassword, storedHash)
   |       +-- false -> AuthenticationException
   |       +-- true  -> continue
   |
   +-- Authenticated Authentication
                |
                v
         SecurityContext
                |
                v
    authorizeHttpRequests / AuthorizationManager
                |
                v
        Controller / Service
```

This is a **logical model**. The order of status checks, credentials, filters, and caching may differ depending on configuration; a valid session may be restored without performing a new username/password login on every request.

### 4.1. The provider is where passwords are checked

The provider can perform the equivalent of:

```java
UserDetails user = service.loadUserByUsername(username);

boolean valid =
    passwordEncoder.matches(rawPassword, user.getPassword());
```

This is an **illustrative** fragment and does not reflect all account state checks, exceptions, timing, or caching in the real provider. `loadUserByUsername` only supplies the user/hash; the provider evaluates the evidence. Do not write:

```java
// Wrong when password hashing uses a salt:
passwordEncoder.encode(rawPassword).equals(user.getPassword());
```

With BCrypt, calling `encode` twice on the same raw password usually uses different salts and returns different hashes. You must use `matches`.

### 4.2. A correct password still does not guarantee login

A `UserDetails` with `enabled=false` or `accountNonLocked=false` can still be loaded successfully by the service, yet the provider must reject login based on account status. Authentication may also depend on other measures such as MFA or risk assessment, depending on the flow.

### 4.3. Resulting Authentication can differ from input

`UsernamePasswordAuthenticationToken.unauthenticated("alice",raw)` is untrusted, even though `getName()` already returns `alice`. After authentication, the provider may return a new `Authentication` with `UserDetails` as the principal and trusted authorities. The filter uses the result to populate `SecurityContext`.

`UserDetailsService` does not itself create a session cookie, does not itself save `SecurityContext`, and does not itself issue a JWT. A direct call to `loadUserByUsername` in a service **does not log a user in**.

### 4.4. 401 differs from 403

- Missing or wrong HTTP Basic credentials → usually **401 Unauthorized**, possibly accompanied by `WWW-Authenticate`.
- Logged in correctly but missing `ROLE_ADMIN` → usually **403 Forbidden** due to authorization.
- A POST missing a CSRF token can return **403** even if the user is logged in and has permission; it does not mean a wrong password.
- Form login may redirect to `/login` or `/login?error` depending on configuration, rather than necessarily returning 401 JSON.

Do not infer that a 403 error means `UserDetailsService` failed to find the user. Identify which filter, provider, and authorization rule the request passed through.

## 5. Common user data sources

| Option | Source | When to use? |
| --- | --- | --- |
| `InMemoryUserDetailsManager` | In-memory data | Demos, tests, apps with fixed users |
| `JdbcUserDetailsManager` | Database via JDBC schema/query | JDBC user store and user management tasks |
| `JdbcDaoImpl` | Reads users/authorities via JDBC | A JDBC-based UserDetailsService implementation |
| `CachingUserDetailsService` | Wraps user source with cache | Reduces DB lookups, requires TTL/invalidation |
| Custom `UserDetailsService` | JPA repository, DB, directory, or custom adapter | Domain-specific account/role data |
| LDAP integration | LDAP directory | May use a separate provider/LDAP strategy, not defaulting to DAO password-hash flow |

`UserDetailsManager` extends `UserDetailsService` with user management functions. The `UserDetailsService` interface only has the lookup operation; it **does not define** registration, password change, role revocation, or user locking.

### 5.1. Simple in-memory

```java
UserDetails alice = User.withUsername("alice")
    .password(encoder.encode("demo-alice-pass"))
    .authorities("ROLE_USER", "report:read")
    .build();

UserDetailsService source =
    new InMemoryUserDetailsManager(alice);
```

Here `encoder` must be appropriately created/injected. `source.loadUserByUsername("alice")` reads the object containing the hash; whether the password is right or wrong remains the provider's job to check when an authentication request arrives.

### 5.2. When to implement your own?

When users, hashes, roles, permissions, or status live in a custom application schema; when you need to map accounts to `UserDetails`; or when there is a tenant/username mapping policy that needs control. Do not implement your own just to rename a class if an existing implementation already fits.

## 6. Complete Spring Boot 3 example: UserDetailsService performs only lookup

This example set uses **Spring MVC, HTTP Basic, BCrypt, and three demo users**. We write a custom service using a `Map` as the data source so everything can run locally. The service stores the **hash** in a separate record and **creates a new UserDetails on each lookup** so it does not share an erasable object with the original record.

Files:

```text
src/main/java/example/userlookup/
  UserLookupApplication.java
  DemoUserDetailsService.java
  SecurityConfig.java
  DemoController.java

src/test/java/example/userlookup/
  UserLookupSecurityTest.java
```

### 6.1. Dependencies

In `build.gradle` Groovy DSL of a Spring Boot 3 project with plugins/repositories already configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is only the `dependencies` block, not a complete Gradle build file. With Maven, use the equivalent starters and `spring-security-test` in `test` scope. Let the Boot BOM choose compatible Spring Security versions; do not add standalone versions for individual modules without checking the dependency graph.

### 6.2. File UserLookupApplication.java

```java
package example.userlookup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UserLookupApplication {
    public static void main(String[] args) {
        SpringApplication.run(UserLookupApplication.class, args);
    }
}
```

### 6.3. File DemoUserDetailsService.java

```java
package example.userlookup;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class DemoUserDetailsService implements UserDetailsService {

    private record AccountRow(
        String passwordHash,
        List<String> authorities,
        boolean enabled
    ) {}

    private final Map<String, AccountRow> accounts;

    public DemoUserDetailsService(PasswordEncoder encoder) {
        this.accounts = Map.of(
            "alice",
            new AccountRow(
                encoder.encode("demo-alice-pass"),
                List.of("ROLE_USER", "report:read"),
                true
            ),
            "admin",
            new AccountRow(
                encoder.encode("demo-admin-pass"),
                List.of("ROLE_USER", "ROLE_ADMIN"),
                true
            ),
            "disabled",
            new AccountRow(
                encoder.encode("demo-disabled-pass"),
                List.of("ROLE_USER"),
                false
            )
        );
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AccountRow row = accounts.get(username);

        if (row == null) {
            throw new UsernameNotFoundException("User not found");
        }

        return User.withUsername(username)
            .password(row.passwordHash())
            .authorities(row.authorities().toArray(String[]::new))
            .disabled(!row.enabled())
            .build();
    }
}
```

Let us examine each responsibility:

1. The class `implements UserDetailsService` and only overrides `loadUserByUsername(String)`.
2. `AccountRow.passwordHash` holds the password hash, not the plaintext password.
3. The constructor calls `encoder.encode(...)` **only to create demo user data at application startup**. Production databases typically store hashes already generated during registration/password change.
4. `accounts.get(username)` is a repository-like lookup; there is no raw password.
5. Account not found → throws `UsernameNotFoundException`, rather than returning null or creating a fake user.
6. Account found → creates a new `UserDetails` with the hash, authorities, and disabled status.
7. There is no `PasswordEncoder.matches` call in this method: password verification remains in the provider.
8. Authorities are not taken from client-claimed headers/JSON.
9. The service does not itself modify `SecurityContext` or issue login cookies.

### 6.4. File SecurityConfig.java

```java
package example.userlookup;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
    DemoUserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new DemoUserDetailsService(encoder);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("report:read")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Here:

- `DemoUserDetailsService` is a **Spring bean** whose type implements `UserDetailsService`.
- In an appropriate default username/password configuration, when there is no overriding custom AuthenticationManager/AuthenticationProvider, Spring Security can build `DaoAuthenticationProvider` based on the `UserDetailsService` and `PasswordEncoder` beans.
- `.httpBasic(...)` enables the filter to extract Basic credentials from HTTP requests and send them to the authentication flow.
- `.authorizeHttpRequests(...)` is **authorization**, not password checking.
- `hasRole("ADMIN")` by default requires `ROLE_ADMIN`; `hasAuthority("report:read")` matches the string `report:read`.
- `anyRequest().denyAll()` denies URLs/methods without explicit rules, preventing accidentally exposed endpoints.
- Spring Security Servlet CSRF is not disabled by this configuration; the example uses GET to observe the authentication flow independently.

Having a single UserDetailsService bean is convenient for the demo. If the application already has multiple providers/managers or multiple chains, you must check which instance the filter uses. Do not assume that merely creating a class named `UserDetailsService` will make the framework pick it up automatically if you forget to register the bean or have overriding custom configuration.

### 6.5. File DemoController.java

```java
package example.userlookup;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    Map<String, String> publicPage() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .filter(Objects::nonNull)
            .sorted()
            .toList();

        return Map.of(
            "username", authentication.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/api/reports")
    Map<String, String> reports() {
        return Map.of("message", "report available");
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin only");
    }
}
```

The controller receives the `Authentication` already present in the security context. It does not itself call `loadUserByUsername` or `PasswordEncoder.matches`. The API returns a DTO containing selected fields; it does not return the raw `Authentication` or the password hash.

### 6.6. Running the application

In a project with the Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

With the default configuration, the server listens at `http://localhost:8080`. Three demo accounts:

| Username | Password for localhost | Authorities | Status |
| --- | --- | --- | --- |
| `alice` | `demo-alice-pass` | `ROLE_USER`, `report:read` | enabled |
| `admin` | `demo-admin-pass` | `ROLE_USER`, `ROLE_ADMIN` | enabled |
| `disabled` | `demo-disabled-pass` | `ROLE_USER` | disabled |

The passwords above are local demo data; never hardcode production credentials. HTTP Basic uses Base64 to **encode**, providing no cryptographic confidentiality; production requires HTTPS and proper secret management.

### 6.7. Observing with curl

```bash
# Public: 200 even without logging in
curl -i http://localhost:8080/public

# Private: 401 due to missing credentials
curl -i http://localhost:8080/api/me

# Alice + right password: 200
curl -i -u alice:demo-alice-pass http://localhost:8080/api/me

# Still finds Alice, but wrong password: 401
curl -i -u alice:wrong-pass http://localhost:8080/api/me

# Non-existent user: 401
curl -i -u nobody:anything http://localhost:8080/api/me

# Right password, but disabled account: 401
curl -i -u disabled:demo-disabled-pass http://localhost:8080/api/me

# Alice has report:read: 200
curl -i -u alice:demo-alice-pass http://localhost:8080/api/reports

# Alice lacks ROLE_ADMIN: 403
curl -i -u alice:demo-alice-pass http://localhost:8080/api/admin

# Admin has ROLE_ADMIN: 200
curl -i -u admin:demo-admin-pass http://localhost:8080/api/admin
```

Illustrative JSON output when Alice logs in correctly:

```json
{
  "username": "alice",
  "authorities": ["ROLE_USER", "report:read"]
}
```

`authorities` is sorted so the array order is deterministic; the order of **JSON fields** is not required to be fixed. There is no raw password/hash in the response.

Conclusions from the requests:

| Case | Alice lookup | Password / status | Sample HTTP result |
| --- | --- | --- | --- |
| Username Alice + right password | Succeeded | `matches` true, enabled | 200 |
| Username Alice + wrong password | **Still succeeded** | `matches` false | 401 |
| Non-existent username | Throws UsernameNotFoundException | Not authenticated | 401 |
| Disabled account + right password | Succeeded | Disabled → rejected | 401 |
| Alice accessing admin | Succeeded and password right | Missing role at authorization | 403 |
| Admin accessing admin | Succeeded and password right | Has role | 200 |

Do not infer from a single HTTP status without checking filters/handlers. For example, a POST missing CSRF can return 403 before the controller runs, even if the user has the right password.

## 7. Testing the boundary with JUnit and MockMvc

To confirm that `UserDetailsService` only performs lookup, we test the **service layer**, **PasswordEncoder**, and **HTTP filter/provider** separately. The test suite below uses the exact files declared above.

Create `src/test/java/example/userlookup/UserLookupSecurityTest.java`:

```java
package example.userlookup;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UserLookupSecurityTest {

    @Autowired
    DemoUserDetailsService source;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    MockMvc mvc;

    @Test
    void lookupReturnsDataWithoutPasswordArgument() {
        UserDetails alice = source.loadUserByUsername("alice");

        assertThat(alice.getUsername()).isEqualTo("alice");
        assertThat(alice.getPassword()).isNotEqualTo("demo-alice-pass");
        assertThat(alice.getAuthorities())
            .extracting(a -> a.getAuthority())
            .contains("ROLE_USER", "report:read");
        assertThat(alice.isEnabled()).isTrue();
    }

    @Test
    void missingUsernameThrowsException() {
        assertThatThrownBy(() -> source.loadUserByUsername("nobody"))
            .isInstanceOf(UsernameNotFoundException.class);
    }

    @Test
    void encoderChecksPasswordSeparately() {
        UserDetails alice = source.loadUserByUsername("alice");

        assertThat(encoder.matches(
            "demo-alice-pass", alice.getPassword())).isTrue();
        assertThat(encoder.matches(
            "wrong-pass", alice.getPassword())).isFalse();
    }

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointRequiresLogin() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctBasicPasswordAuthenticatesAlice() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"))
            .andExpect(jsonPath("$.authorities[1]").value("report:read"));
    }

    @Test
    void wrongBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void disabledAccountIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("disabled", "demo-disabled-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void reportPermissionIsCheckedAfterLogin() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/reports")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleIsCheckedAfterLogin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isOk());
    }
}
```

Run:

```bash
./gradlew test --tests example.userlookup.UserLookupSecurityTest
```

In Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.userlookup.UserLookupSecurityTest
```

**Expected:** all **10 test methods** pass when using a compatible Boot 3 / Security 6.5 project and the exact files above. This is an **expected outcome from the code**, not a log confirming Gradle was executed in this lesson.

| Test group | What is verified |
| --- | --- |
| Direct lookup | UserDetailsService takes only username; returns hash, authorities, and account flags |
| Missing username | Throws UsernameNotFoundException |
| Separate PasswordEncoder | Right/wrong raw password gives two different outcomes despite identical lookup |
| Right HTTP Basic | Filter/provider verifies credentials, returns identity |
| Wrong HTTP Basic | Does not log in even though user exists |
| Disabled account | Provider rejects even though hash may match |
| Report/admin | Valid authentication still requires the right authority at authorization |

`@WithMockUser` or `with(user("alice"))` creates a **mock** identity to test authorization, **without checking passwords** in `DaoAuthenticationProvider`. When you want to test real username/password login, `httpBasic(...)` or a form-login integration test is the appropriate choice.

If you later add POST requests in an app with CSRF enabled, use `with(csrf())` in tests that need to pass the CSRF layer to test downstream authorization. Do not disable CSRF just to turn a 403 into a 200.

## 8. Integrating with JPA/Database

In a real application, the service typically uses a repository to fetch records from the DB. What must stay the same: **query by username**, read the stored hash and permissions, then return `UserDetails`. Do not embed the client's raw password in the query or try to implement login by comparing plaintext passwords in SQL.

An architectural fragment example:

```java
@Service
public class DatabaseUserDetailsService
        implements UserDetailsService {

    private final AccountRepository accounts;

    public DatabaseUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) {
        Account account = accounts.findByLogin(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("User not found"));

        String[] authorities = account.getPermissions()
            .stream()
            .map(Permission::getCode)
            .distinct()
            .toArray(String[]::new);

        return User.withUsername(account.getLogin())
            .password(account.getPasswordHash())
            .authorities(authorities)
            .disabled(!account.isEnabled())
            .accountLocked(account.isLocked())
            .build();
    }
}
```

**This is a fragment**, not a standalone Java file: it requires `Account` and `Permission` entities, `AccountRepository`, JPA dependencies, a datasource, and imports. Do not copy it verbatim into the in-memory demo and expect `javac` to compile it without Spring/JPA dependencies.

### 8.1. What must the repository guarantee?

- Have a unique index for username/email scoped by tenant and normalization convention.
- Fetch the stored hash, **do not store raw passwords**.
- Load needed permissions and flags within the transaction scope; avoid lazy-loading errors or unnecessary N+1 queries.
- Use parameterized queries to avoid SQL injection.
- Permissions must come from a trusted source, not user-editable fields.
- When an account is locked/disabled or permissions are revoked, have a cache invalidation strategy.
- Do not return the full entity via a controller or log password hashes.

An illustrative schema:

```text
accounts(id, normalized_username, password_hash, enabled, locked, tenant_id)
roles(id, role_code)
account_roles(account_id, role_id)
permissions(id, permission_code)
role_permissions(role_id, permission_id)
```

### 8.2. When is the password encoded?

The password is encoded when the user registers or changes their password, using `PasswordEncoder.encode(rawPassword)`. `loadUserByUsername` later **reads this hash**. Inside the provider, matching is done via `PasswordEncoder.matches(raw, hash)`.

Anti-pattern:

```java
// Wrong purpose: do not re-hash the client password inside lookup.
String newHash = encoder.encode(passwordFromRequest);
return User.withUsername(username)
    .password(newHash)
    .authorities("ROLE_USER")
    .build();
```

Besides the contract not having `passwordFromRequest`, this snippet breaks the architecture and fails easily with salted hashing. If the system's credential is not a username/password hash (e.g., LDAP bind), choose an appropriate provider.

### 8.3. Avoiding loss of tenant and object-level access control

`getAuthorities()` may allow a user to enter the `order:read` feature, yet it does not itself prove the user owns order ID 123. The domain service must check principal ID, tenant, owner, and order state based on server data. Never use a feature-level authority as a substitute for per-record permissions.

## 9. Caching, credential erasure, and password changes

A `CachingUserDetailsService` or provider cache can reduce database lookups. When caching, consider TTL and invalidation when password hashes, roles, account status, or tenants change. Never assume "loaded once = permissions always valid".

`ProviderManager` can erase credentials on the resulting Authentication via `CredentialsContainer.eraseCredentials()`. If the resulting principal/`UserDetails` **shares the same mutable object** with the cache, credential erasure can cause the cache to lose the hash. In the demo, `AccountRow` keeps the hash separately and the service creates a new `UserDetails` for each lookup, reducing the risk of this object sharing.

Do not disable credential erasure just to keep the password hash in cache without assessing the risk of retaining sensitive data in memory. Depending on the case, return copies, cache immutable records, or refresh objects appropriately.

### 9.1. UserDetailsPasswordService vs. UserDetailsService

| Interface | Responsibility |
| --- | --- |
| `UserDetailsService` | Loads user by username |
| `UserDetailsPasswordService` | Updates the encoded password if a flow/provider is configured to upgrade hashes |
| `UserDetailsManager` | Manages users via the operations available in the interface |
| `PasswordEncoder` | `encode`, `matches`, and optionally `upgradeEncoding` |

Merely implementing `UserDetailsService` does not mean the provider will automatically update password hashes in the database when the algorithm changes. To upgrade hashes, you must design a `UserDetailsPasswordService` or corresponding migration flow, ensuring safe DB writes.

### 9.2. BCrypt vs. DelegatingPasswordEncoder

`BCryptPasswordEncoder` handles BCrypt hashes in `$2a$...` format. `DelegatingPasswordEncoder` expects an ID prefix such as `{bcrypt}$2a$...` to select the right algorithm. If you switch encoders while stored hashes lack the required prefix, you may encounter the error `There is no PasswordEncoder mapped for the id "null"`.

Do not "quick-fix" with `NoOpPasswordEncoder` for production. Check the hash format and encoder migration plan.

## 10. Do JWT/OIDC flows always call UserDetailsService?

**No.** `UserDetailsService` belongs to the typical username/password flow. With a JWT resource server, `JwtDecoder` and a converter can verify the token and build the principal and authorities without calling `loadUserByUsername` on every request.

| Mechanism | Is UserDetailsService required? |
| --- | --- |
| HTTP Basic + DaoAuthenticationProvider | Usually yes |
| Username/password form login | Usually yes |
| JWT Resource Server | Not required |
| OAuth2/OIDC login | Not required |
| LDAP bind | May use an LDAP provider instead of DAO hash flow |
| Custom API key/mTLS | Uses an appropriate flow/provider |

If the system needs to load extra profile data after the JWT has been verified, that is custom application logic; do not turn lookup into a step that "re-verifies raw passwords" or trusts client-supplied roles.

When MFA is present, `loadUserByUsername` also does not handle OTP/challenges itself: a dedicated authentication flow and proper step-by-step authentication state are needed.

## 11. Standalone Java 17: lookup and password check are two separate jobs

The following program **does not use Spring Security**. It only simulates the architecture separating the source from the checker so it compiles with plain JDK 17. For simplicity, the program uses **demo plaintext and `String.equals`**, which is completely unsafe for real applications. In production, use dedicated password hashing/encoders like the Spring Boot setup above.

Create file `UserLookupVsPasswordCheck.java`:

```java
import java.util.List;
import java.util.Map;

public class UserLookupVsPasswordCheck {

    record Account(
        String username,
        String demoSecret,
        List<String> authorities,
        boolean enabled
    ) {}

    static final class UserDirectory {
        private final Map<String, Account> rows = Map.of(
            "alice",
            new Account(
                "alice",
                "demo-pass",
                List.of("ROLE_USER", "report:read"),
                true
            )
        );

        Account loadByUsername(String username) {
            Account account = rows.get(username);
            if (account == null) {
                throw new IllegalArgumentException("unknown-user");
            }
            return account;
        }
    }

    static final class DemoPasswordChecker {
        boolean matches(String submitted, String stored) {
            // This is only a simulation, NOT password hashing.
            return submitted.equals(stored);
        }
    }

    public static void main(String[] args) {
        UserDirectory source = new UserDirectory();
        DemoPasswordChecker checker = new DemoPasswordChecker();

        Account alice = source.loadByUsername("alice");

        System.out.println("lookup.username=" + alice.username());
        System.out.println(
            "lookup.authorities="
                + String.join(",", alice.authorities())
        );
        System.out.println("lookup.verifiedPassword=false");
        System.out.println(
            "password.correct="
                + checker.matches("demo-pass", alice.demoSecret())
        );
        System.out.println(
            "password.wrong="
                + checker.matches("wrong", alice.demoSecret())
        );
        System.out.println("account.enabled=" + alice.enabled());

        try {
            source.loadByUsername("nobody");
        } catch (IllegalArgumentException ignored) {
            System.out.println("lookup.unknown=rejected");
        }
    }
}
```

Run:

```bash
javac UserLookupVsPasswordCheck.java
java UserLookupVsPasswordCheck
```

**Exact stdout according to the code:**

```text
lookup.username=alice
lookup.authorities=ROLE_USER,report:read
lookup.verifiedPassword=false
password.correct=true
password.wrong=false
account.enabled=true
lookup.unknown=rejected
```

Here `UserDirectory.loadByUsername` only retrieves the record. It does not accept a request password and makes no conclusion that the password is correct. `DemoPasswordChecker` checks the string after lookup. In real Spring Security, `UserDetailsService` supplies `UserDetails`, while the provider uses `PasswordEncoder` to match password/hash; the provider also checks the account flags.

This Java program **does not authenticate securely**, does not create Authentication/SecurityContext, and does not protect the web; it only serves to illustrate the responsibility boundary.

## 12. Common errors and how to debug

| Symptom | Possible reason | How to check |
| --- | --- | --- |
| `UsernameNotFoundException` | Username missing in lookup source | Repository/query, normalization, tenant boundary |
| API returns 401 even though lookup finds user | Wrong password or account disabled/locked | Encoder matches, account flags, and provider |
| BCrypt hash exists but reports encoder id null | DelegatingPasswordEncoder expects `{id}` | Hash version/format and encoder |
| Login succeeds, admin returns 403 | Missing `ROLE_ADMIN` / other policy | Authorities, `hasRole`, object policy |
| `@WithMockUser` test passes but Basic login fails | Mock bypassed the password provider | Integration test with `httpBasic(...)` |
| Multiple users share the same username | Wrong unique constraint/tenant namespace | Choose an immutable identifier and unique scope |
| `getPassword()` on cached user disappears | Credential erasure on shared object | Copy UserDetails, cache design, invalidation |
| Old login retains permissions after DB revocation | Session/token/cache authorities not refreshed | Revoke/TTL and runtime checks |
| JWT API does not call service | This may be the default token flow | Read JwtDecoder/converter and chain |
| `Cannot resolve UserDetailsService` | Missing dependency, import, or module | Starter, `org.springframework.security.core.userdetails` |
| Form login redirects while curl sees 401 | Different client/entry point | SecurityFilterChain, HTTP Basic vs. form login |
| POST returns 403 | CSRF or authorization | Check token and rules before changing anything |

### 12.1. Why can a missing-username error become BadCredentialsException?

In many DAO authentication configurations, the provider tries to avoid disclosing whether a user exists. `UsernameNotFoundException` from the service can be **hidden behind a generic credentials error**. This reduces user enumeration risk. Do not publicly return "username exists, wrong password" when the threat model forbids it.

### 12.2. Do not use the source to authenticate login

Anti-pattern:

```java
// Do not use a successful load as proof of login.
UserDetails user = source.loadUserByUsername(request.username());
if (user != null) {
    // Do not grant permissions or mark authenticated here.
}
```

Only when a trusted `AuthenticationProvider`/manager successfully verifies credentials and account flags is there a resulting Authentication usable for access policy.

### 12.3. When the data source fails

A database error, query timeout, or unreachable user directory is not a wrong password. The system must classify errors and **never create an authenticated Authentication** from unverified data. Depending on the API, it may need to return an infrastructure error per policy; never let the user proceed because lookup hit an exception.

### 12.4. Why must passwords not be put into SQL?

Queries like `WHERE username=? AND password=?` easily conflate raw passwords with stored hashes and are incompatible with salted password hashing. Query the user by username, load the hash, and let the provider use `matches`. Input data must be bound via parameters or proper ORM mapping to prevent SQL injection.

### 12.5. User's roles changed but the session still holds old roles

Authorities in `Authentication` may reflect the moment login occurred or when the token/session was created. If a role is revoked or a user is disabled, the session/token/cache does not necessarily update immediately. You need TTL, invalidation, revocation policies, or runtime checks for sensitive actions.

## 13. Checklist when building a real UserDetailsService

- `loadUserByUsername` takes only username and returns `UserDetails` or throws `UsernameNotFoundException`.
- Clearly define case sensitivity, normalization, and uniqueness of username/email per tenant.
- Return the stored password hash, never a raw password.
- Do not call `PasswordEncoder.matches` inside standard lookup.
- Do not re-encode a request's raw password during load.
- Return accurate authorities/flags from a trusted source.
- Avoid using JPA entities with unloaded lazy relations or serializing secrets.
- Use an appropriate `PasswordEncoder` and have a hash migration strategy.
- Ensure the provider actually uses the source; verify when multiple providers/managers exist.
- Do not set `authenticated=true` from a found user or client-claimed roles.
- Control caching and credential erasure so stale permissions/hashes are not used.
- Test user present/missing, right/wrong password, disabled/locked, authority present/missing.
- Add owner/tenant/resource authorization tests at the service or repository layer.
- For POSTs using cookies/sessions, verify CSRF appropriately.
- Do not log Authorization headers, raw passwords, password hashes, tokens, or session IDs.
- When identity/permissions cannot be verified due to infrastructure failure, do not automatically grant access.

## 14. Self-check questions

**1.** Why can `UserDetailsService.loadUserByUsername` not check the raw password itself under the standard contract?

**2.** What data should `UserDetails.getPassword()` return?

**3.** If the source finds Alice but the caller enters the wrong password, does authentication succeed?

**4.** Which component usually calls `PasswordEncoder.matches` during username/password authentication?

**5.** Can an account with a matching hash but `isEnabled() == false` be authenticated?

**6.** Why should you not return null when a username does not exist?

**7.** What is the difference between `UserDetailsService` and `UserDetailsManager`?

**8.** When is `UserDetailsPasswordService` used?

**9.** Which authority does `hasRole("ADMIN")` look for under the default prefix?

**10.** Why is `@WithMockUser` insufficient to prove Alice's password is checked by the provider?

**11.** Why does a JWT Resource Server API not necessarily call `loadUserByUsername` on every request?

**12.** Why can caching `UserDetails` cause issues when `ProviderManager` erases credentials?

**13.** If a username is only unique within a tenant, what else must be checked?

**14.** After logging in properly, can a user automatically view everyone else's reports?

**15.** What issue can a BCrypt hash stored in the DB without the `{bcrypt}` prefix encounter when using `DelegatingPasswordEncoder`?

**Suggested answers:**

1. The method only receives username; there is no raw password from the request.
2. Encoded password/hash from a trusted user source.
3. No; the provider uses `PasswordEncoder` to check and rejects the wrong password.
4. `DaoAuthenticationProvider` working together with `PasswordEncoder`.
5. No. Account status is one of the authentication conditions.
6. The contract requires returning `UserDetails` or throwing `UsernameNotFoundException`.
7. `UserDetailsManager` adds user management operations; the base service only loads users.
8. Updating the encoded password when a hash upgrade/password change flow is properly designed.
9. `ROLE_ADMIN`.
10. Mock user fakes an `Authentication` without calling the real provider/encoder.
11. JWTs are verified by a decoder/converter under the resource server mechanism.
12. If the cache and principal share a mutable object, erasure can wipe the hash in the cache.
13. The tenant must come from a trust boundary, and queries/unique indexes must be scoped to the right tenant.
14. No; owner, tenant, and object-level policies still need to be checked.
15. The delegating encoder may fail to find an id mapping; you need to check and migrate the hash format properly.

## 15. Official documentation

- [Spring Security 6.5 – UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 – Username/Password Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/index.html)
- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 – Servlet Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 – MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/)
- [UserDetailsService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html)

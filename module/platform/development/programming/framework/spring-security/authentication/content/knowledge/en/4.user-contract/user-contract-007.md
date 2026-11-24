# UsernameNotFoundException and Handling Non-Existent Accounts

In Spring Security, `UsernameNotFoundException` is the exception representing that **no user matching the username could be found** when the authentication data-loading layer executes the `UserDetailsService.loadUserByUsername(...)` contract. However, **an exception occurring in the data-loading layer does not mean the error is exposed to the person logging in**. With `DaoAuthenticationProvider`, the default behavior is **to hide the user-not-found error as a `BadCredentialsException`**, just like entering a wrong password. This reduces the risk of attackers probing whether an account exists.

This lesson belongs to the **User Contract** group of Spring Security Authentication. You will understand when to throw `UsernameNotFoundException`, how providers handle the exception, how to distinguish missing data from system outages, account enumeration vulnerabilities, and how to write practical Java 17 code/tests.

## 1. Where UsernameNotFoundException Sits in the Authentication Flow

A username/password login request passes through layers similar to:

~~~text
Client: username + password
        |
        v
Filter creates unauthenticated Authentication
        |
        v
AuthenticationManager / ProviderManager
        |
        v
DaoAuthenticationProvider
        |
        +--> UserDetailsService.loadUserByUsername(username)
        |       |
        |       +--> User exists: return complete UserDetails
        |       |
        |       '--> User missing:
        |                throw UsernameNotFoundException
        |
        +--> Default hideUserNotFoundExceptions = true
        |       |
        |       '--> Convert not-found error -> BadCredentialsException
        |
        +--> If user exists: check status and password hash
        |       |
        |       +--> Wrong password -> BadCredentialsException
        |       '--> Valid -> authenticated Authentication
        |
        v
Filter / AuthenticationEntryPoint / failure handler
        |
        v
HTTP response or redirect per configuration
~~~

The diagram above illustrates the **conceptual** flow. An application may have multiple `AuthenticationProvider` instances or other authentication mechanisms; exact errors and HTTP translation depend on the actual provider/filter used.

### 1.1. Which Package Does the Exception Live In?

~~~java
import org.springframework.security.core.userdetails.UsernameNotFoundException;
~~~

`UsernameNotFoundException` is a subclass of `AuthenticationException`, so the framework can handle it as an authentication failure. Yet what is exposed to the API does not necessarily preserve that exception name.

| Layer | When Username Does Not Exist | Meaning |
|---|---|---|
| `AccountRepository` | E.g., returns `Optional.empty()` | Data lookup result, not yet a security error |
| `UserDetailsService` | Throws `UsernameNotFoundException` | Adheres to Spring Security's user-loading contract |
| Default `DaoAuthenticationProvider` | Typically converts to `BadCredentialsException` | Does not publicly distinguish "no user" from "wrong password" |
| `AuthenticationManager` | Throws the final authentication error if no provider succeeds | Authentication contract; not an HTTP status code yet |
| Login filter/failure handler | E.g., returns 401 or redirects with generic message | Error presentation depends on web mechanism |

**Do not infer from HTTP 401 that the username definitely does not exist.** The exact same response can come from a missing account, wrong password, invalid token, or another authentication policy.

## 2. The UserDetailsService.loadUserByUsername Contract

Spring Security interface:

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
~~~

This is a **simplified signature of the framework interface**, not a class to define yourself when using Spring Security. Basic contract:

1. **Input** `username` is the value the authentication mechanism uses to look up the user; it does not have to be an email, UUID, or a table's `name` column.
2. **User found**: return a **non-`null`** `UserDetails` containing the info the framework needs for authentication: username, password hash (if password-based), authorities, and status flags.
3. **Not found**: throw `UsernameNotFoundException`. Do not return `null`, as `null` violates the contract and may be treated by the provider as an internal service error.
4. **Lookup fails due to a system outage**: do not pretend "the user does not exist". For instance, a database timeout/connection failure should follow the infrastructure error path so operations can detect it and login fails closed.
5. **Do not authenticate passwords here** when using standard `DaoAuthenticationProvider`: normally `UserDetailsService` loads data while the provider/`PasswordEncoder` checks the password. Custom provider architectures may differ.

The JavaDoc of `UserDetailsService` also mentions the case where a user has no `GrantedAuthority` as a possible cause of `UsernameNotFoundException`. However, do not arbitrarily equate **"user exists but has not been granted a role yet"** with **"account does not exist"** in the business model. Define a clear policy: whether they may authenticate and then be denied resource access, or must be rejected right in the authentication flow.

### 2.1. Username Does Not Have to Match the Primary Key

For example, a database has:

~~~text
accounts
  id:           4c...UUID
  email:        linh@example.com
  login_name:   linh
  password_hash: $2a$... (illustrative value)
  status:       ACTIVE
~~~

`loadUserByUsername("linh")` can query by `login_name`. If email is used as the login credential, the service can canonicalize the email before querying according to defined rules. Yet the account's durable internal ID can still be a UUID. **The login name for looking up data** and **the business identifier for linking orders/tenants/audits** serve two distinct purposes.

In multi-tenant applications, the same username may appear across multiple organizations. In that case, lookups must use the real composite key such as `(tenantId, username)` if policy allows; taking `tenantId` from the client does not make it trustworthy. Ensure server-side verification of tenant context and membership.

### 2.2. Should You Normalize Usernames Yourself?

Design consistently across registration, DB storage, search, and login. For example, lowercasing emails may fit a product policy, yet not all identifiers share the same case-sensitivity rules. Avoid indiscriminately calling `toLowerCase()` on every username and avoid `trim()`/Unicode normalization without agreeing on a data contract.

There should be a unique constraint matching the lookup rule. If a query returns multiple accounts for an identifier meant to be unique, that is a data integrity bug—**never** randomly pick one record to authenticate.

## 3. Why Does DaoAuthenticationProvider Hide Not-Found Errors?

`DaoAuthenticationProvider` extends `AbstractUserDetailsAuthenticationProvider`. Important configuration:

~~~java
provider.setHideUserNotFoundExceptions(true);
~~~

This is an **illustrative snippet in provider configuration**, and does not compile standalone; `provider` must be a suitable instance. The default value is `true`, so normally there is no need to call the setter.

Per the `AbstractUserDetailsAuthenticationProvider` contract:

- If the username does not exist, the provider reports **`BadCredentialsException`** by default.
- If the username exists but the password is wrong, the provider also reports **`BadCredentialsException`**.
- Setting `setHideUserNotFoundExceptions(false)` can allow `UsernameNotFoundException` to be thrown outward when an account does not exist; Spring Security documentation **considers that less secure**.
- Account status exceptions like `DisabledException` or `LockedException` are a separate matter: they are not automatically turned into a missing-username error. The web layer should still limit info exposed in public responses.

### 3.1. Two Important Different Messages

**Internal message:** "No user found for this username."  
**Public message:** "Invalid login credentials."

The authentication data layer needs to know there is no record to stop lookup cleanly, yet the client does not need to know whether an account exists. Even when using a generic message, differing **HTTP status, redirect URL, response body shape, headers, and latency** can still leak data. Thus, mitigating account enumeration is the job of the entire endpoint chain, not just one setter.

### 3.2. Why Was the Default Chosen?

If a public endpoint returns:

~~~text
Login "linh@example.com"    -> Wrong password
Login "missing@example.com" -> Account does not exist
~~~

an attacker can test a list of emails to harvest registered addresses, then focus password spraying, phishing, or social engineering. Returning the same error for both cases reduces what they can learn from login failures.

**That does not mean every failure must succeed or return HTTP 200.** Failed logins are still failures; HTTP 401 or a redirect may be appropriate. The security requirement is **creating no observable difference that reveals whether a username exists**, except in workflows that have verified the requester and genuinely need that information.

## 4. Distinguishing Missing Accounts from Neighboring Cases

| Scenario | Detection Source | Common Handling |
|---|---|---|
| Username not found | `UserDetailsService`/repository | Throw `UsernameNotFoundException`, let provider hide as `BadCredentialsException` by default |
| Right username, wrong password | `DaoAuthenticationProvider` + encoder | `BadCredentialsException` |
| Account disabled | Account status check | `DisabledException` in the appropriate authentication flow |
| Account locked | Account status check | `LockedException` in the appropriate authentication flow |
| Password expired | Credential policy | Corresponding exception/status, do not fabricate missing username |
| Account email unverified | Business rules | May use ineligible-for-login state; design clear verification flow |
| Database timeout or lost connection | Repository/DB client | Internal service error, never arbitrarily turn into "user does not exist" |
| Insufficient permission for a resource | Authorization | Not `UsernameNotFoundException`; AuthN and AuthZ are distinct |
| External IdP has valid subject without local link | Identity mapping/provisioning | Dedicated linking or rejection policy; do not auto-merge by email |
| Username exists in another tenant | Tenant-scoped lookup | Do not leak another tenant's account; apply proper lookup policy |

### 4.1. Do Not Turn Outages into UsernameNotFoundException

An anti-pattern:

~~~java
try {
    return repository.findByLoginName(username)
            .orElseThrow(...);
} catch (Exception e) {
    throw new UsernameNotFoundException("Not found");
}
~~~

This is **counter-example code**; `repository` and `...` are schematic only, not meant to compile. Catching every exception into one lumps DB downtime, SQL errors, network drops, and missing records together; this can skew metrics, retries, and alerts. Distinguish `Optional.empty()` from repository exceptions; let infrastructure service errors take a separate path and never issue an authenticated token.

### 4.2. When Multiple AuthenticationProviders Exist

`ProviderManager` may try multiple providers. A `BadCredentialsException` from the first provider **does not always** terminate the entire chain if a later provider can handle and succeed. If the application supports multiple realms, clearly define routing and guard against fallbacks that weaken credential checks.

If one provider authenticates accounts in domain A and another accepts the same username with weaker policy, differing error translation must never open a bypass path. Account enumeration protection does not replace provider ordering policy.

## 5. Implementing UserDetailsService with a Repository

An implementation can follow the structure:

~~~text
Authentication request
     -> DaoAuthenticationProvider
         -> AccountUserDetailsService
             -> AccountRepository.findByLoginName(...)
                 -> Optional<AccountEntity>
         -> PasswordEncoder.matches(...)
     -> Authentication success / exception
~~~

**Spring Boot integration snippet**, assuming the project defines `AccountRepository`, `AccountEntity`, columns, and status mappings:

~~~java
@Service
public class AccountUserDetailsService implements UserDetailsService {

    private final AccountRepository repository;

    public AccountUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AccountEntity account = repository.findByLoginName(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Invalid credentials"));

        return User.withUsername(account.getLoginName())
                .password(account.getPasswordHash())
                .authorities("profile:read")
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .build();
    }
}
~~~

**This is not a standalone Java file:** it needs proper Spring imports, existing `AccountRepository`/`AccountEntity`, and a real permission-granting policy. The `"profile:read"` authority string is merely an example; **never grant fixed permissions to every account** in a real app. `locked/disabled` status must map from the domain per authentication rules.

The right flow here is:

1. The repository finds the record by canonicalized identifier and policy-enforced uniqueness.
2. If `Optional.empty()`, throw `UsernameNotFoundException`; never return `null` or a fake entity.
3. If found, construct `UserDetails`; avoid returning a raw JPA entity holding passwords, lazy relationships, and private data unnecessarily.
4. The provider checks the hash with a trusted `PasswordEncoder` (e.g., BCrypt/Argon2 per config) and account status.
5. The provider/filter manages results, context, errors, and public responses. `UserDetailsService` must not send emails or write HTTP responses itself while loading users.

**Important:** `UsernameNotFoundException` may carry a developer-supplied message to aid diagnostics, yet never pass that message raw into public responses or logs containing sensitive data. You can log an event code, provider, correlation ID, or redacted content per observability policy.

## 6. Runnable Java 17 Example: Directly Seeing the Difference Between Service and Login

We build a **console** application using Spring Security Core/Crypto to observe actual exceptions without depending on HTTP responses. The demo deliberately builds a new `UserDetails` on every load to avoid holding a mutable principal with a password hash inside a shared cache.

Scenarios include:

- Calling `loadUserByUsername("ghost")` directly: receives `UsernameNotFoundException`.
- Calling `AuthenticationManager.authenticate(...)` with username `ghost`: receives **`BadCredentialsException`** because the provider hides not-found names by default.
- Logging in as `linh` with a wrong password: also receives `BadCredentialsException`.
- Logging in as `khoa` (disabled account): receives `DisabledException`.
- Logging in as `linh` with the right password: authenticates and returns the matching principal.

### 6.1. Creating the Project

~~~text
missing-user-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/MissingUserDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'missing-user-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.8'
    implementation 'org.springframework.security:spring-security-crypto:6.3.8'
}

application {
    mainClass = 'example.MissingUserDemo'
}
~~~

Spring Security version 6.3.8 is pinned for the console lesson; in real Spring Boot projects, prefer the dependency management/BOM of your Boot version. Running requires JDK 17+, compatible Gradle, and access to Maven Central on first dependency download.

### 6.2. Complete Java Code

Create `src/main/java/example/MissingUserDemo.java`:

~~~java
package example;

import java.util.List;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class MissingUserDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        String hash = encoder.encode("demo-pass");

        UserDetailsService users = username -> {
            if ("linh".equals(username)) {
                // Create a new instance on every load; do not share a
                // UserDetails object holding a hash with the Authentication result.
                return User.withUsername("linh")
                        .password(hash)
                        .authorities("profile:read")
                        .build();
            }
            if ("khoa".equals(username)) {
                return User.withUsername("khoa")
                        .password(hash)
                        .authorities("profile:read")
                        .disabled(true)
                        .build();
            }
            throw new UsernameNotFoundException("Account not found");
        };

        try {
            users.loadUserByUsername("ghost");
        } catch (UsernameNotFoundException ex) {
            System.out.println("DIRECT ghost -> "
                    + ex.getClass().getSimpleName());
        }

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        // Default: hideUserNotFoundExceptions == true.

        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        login(manager, "ghost", "demo-pass", "ghost");
        login(manager, "linh", "wrong-pass", "linh/wrong");
        login(manager, "khoa", "demo-pass", "khoa/disabled");
        login(manager, "linh", "demo-pass", "linh/correct");
    }

    private static void login(AuthenticationManager manager,
                              String username, String password,
                              String label) {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);
        try {
            Authentication result = manager.authenticate(request);
            System.out.println("LOGIN " + label
                    + " -> OK, name=" + result.getName()
                    + ", authenticated=" + result.isAuthenticated()
                    + ", credentialsNull="
                    + (result.getCredentials() == null));
        } catch (AuthenticationException ex) {
            System.out.println("LOGIN " + label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

All classes and imports for the console program are declared in the same file as `public final class MissingUserDemo`. If running with a different Gradle plugin and version, cross-check that version's JavaDoc; the demo does not start a web server, set HTTP sessions, or issue JWTs.

### 6.3. Running and Reading Results

From the project directory with a compatible Gradle Wrapper:

~~~bash
./gradlew run
~~~

If there is no wrapper, you can use `gradle run` with installed Gradle. On PowerShell, the wrapper normally runs with `.\gradlew.bat run`.

Output from the `System.out.println` statements in the program (excluding Gradle logs):

~~~text
DIRECT ghost -> UsernameNotFoundException
LOGIN ghost -> BadCredentialsException
LOGIN linh/wrong -> BadCredentialsException
LOGIN khoa/disabled -> DisabledException
LOGIN linh/correct -> OK, name=linh, authenticated=true, credentialsNull=true
~~~

**Why do the lines differ?**

1. `users.loadUserByUsername("ghost")` is a **direct** call to the contract. The service itself throws `UsernameNotFoundException` without passing through a provider to change the error type.
2. `manager.authenticate(...)` runs through `DaoAuthenticationProvider` and its default hiding setting; the ghost username comes back as bad credentials.
3. With `linh` and wrong password, the account is found, yet `PasswordEncoder.matches(...)` fails: the same `BadCredentialsException`.
4. With `khoa`, the account exists yet is disabled. The provider checks status and throws `DisabledException`.
5. With `linh` and right password, the manager returns an authenticated authentication. `ProviderManager` attempts to erase credentials from the result by default, so `result.getCredentials() == null`.

BCrypt hashes generate random salts so internal hash strings may differ across runs, yet **the stdout above does not depend on the specific hash value**. The demo uses sample password `demo-pass` strictly in a learning environment; never use that password for real accounts.

### 6.4. What If You Disable hideUserNotFoundExceptions?

To inspect the difference *strictly inside an internal test*, add:

~~~java
provider.setHideUserNotFoundExceptions(false);
~~~

right before creating the manager in the demo program. Then `LOGIN ghost` may throw `UsernameNotFoundException` instead of `BadCredentialsException`; `linh`'s wrong-password line remains `BadCredentialsException`.

**Never apply this setting to public logins.** That configuration exposes differing error types, easily leaking through unisolated exception handlers, status codes, response bodies, or metrics. If you need server-side failure breakdown, use controlled internal logging/monitoring rather than altering the public contract.

## 7. Preventing Account Enumeration

### 7.1. Login Response

For wrong username/password, a JSON API can return a generic message:

~~~json
{
  "error": "invalid_credentials",
  "message": "Invalid login credentials"
}
~~~

This JSON example is an **API schema illustration**, not Spring Security's default response. In HTTP Basic, the client may get status 401 and header `WWW-Authenticate`; form login normally redirects to a failure page. Choose the right protocol while avoiding differences based on "whether the account exists".

Check that the public response is identical between a non-existent username and a wrong password: HTTP status code, body structure, error keys, redirect URL, headers, cookies, response size, and displayed text. Never put exception classes, SQL errors, or username lookup outcomes in responses.

### 7.2. Response Timing Can Also Leak Data

If real accounts run BCrypt while non-existent accounts return immediately, measuring many requests can reveal which users exist via average latency. `DaoAuthenticationProvider` includes logic to narrow that gap by running the password encoder against a dummy hash when a user is not found on the username/password path.

However, **this is not an absolute constant-time guarantee**: caches, databases, networks, MFA, lockouts, application handlers, and other queries can still create side channels. Never build a solution with a naive fixed `Thread.sleep(...)`: it does not eliminate all differences and can help attackers overload the server.

Practical mitigations include multi-signal rate limiting, monitoring, anti-brute-force/password-spraying policies, spam protection, tuning BCrypt cost, and testing latency in production-like environments without logging real passwords.

### 7.3. Endpoints Other Than Login

Even when login hides errors, the following endpoints can still disclose accounts:

| Endpoint/Flow | Risky Response | Safer Approach |
|---|---|---|
| Forgot password | "This email is not registered" | "If the address is valid and has an account, we will send instructions" |
| Resend verification email | "Account not found" | Generic message, rate-limit sending |
| Sign up | "Email is already in use" | Build proper policy and curb bulk probing; avoid disclosing extra info |
| Invite member | "User X already exists in the system" | Restrict by inviter permissions and tenant scope |
| Check username availability API | Probing names from a list | Rate-limit/gate access and reconsider public need |
| OAuth account linking | Merging by unverified email | Verify source/subject and use controlled linking workflow |

For forgot-password flows, **a generic message is not enough** if emails are only sent for existing accounts and cost/timing/cookies differ noticeably; test the entire flow. Reset tokens must expire, be single-use or replay-protected, and be stored/verified securely.

### 7.4. Server-Side Logging/Auditing

Never print raw passwords, bearer tokens, password hashes, or full `Authentication` objects to logs. For non-existent users, log an event with correlation ID, flow type, generic error code, provider name, and data-policy-permitted context; consider hashing/de-identifying usernames if analyzing attacks on usernames. **Internal logs also need access controls, retention policies, and PII protection.**

## 8. Mapping to HTTP and Handling Exceptions

`UsernameNotFoundException` **does not mean automatically returning HTTP 404**. It is an error in the user-lookup contract during authentication, not "REST resource not found". Returning 404 for a missing username yet 401 for a wrong password typically creates account enumeration.

Depending on configuration:

- **HTTP Basic**: the authentication entry point may return 401 with `WWW-Authenticate`.
- **Form login**: the failure handler typically redirects to the login page with a generic failure parameter/message.
- **Custom JSON login**: may handle `AuthenticationException` in the appropriate controller/filter and map to a unified public error.
- **Session/JWT**: issue sessions/tokens only after authentication completes; never issue tokens to rejected users.

Illustrative snippet *inside a custom endpoint*:

~~~java
try {
    Authentication verified = authenticationManager.authenticate(request);
    // Continue success flow: set context/session or issue token
} catch (AuthenticationException ex) {
    // Return only a generic public message, never ex.getMessage().
    // Actual response writing depends on filter/controller.
}
~~~

This is **flow-sketch code**, not a complete Java controller; variables `authenticationManager` and `request` must be declared in the application. Never catch every exception into "wrong password": infrastructure outages must be observed, alerted, and handled fail-closed, while clients never receive stack traces or sensitive details.

### 8.1. Special Case: Calling the Service from the Business Layer

`UserDetailsService` is a contract for **username/password authentication**. Do not call `loadUserByUsername` from an endpoint like `GET /users/{username}` and automatically turn `UsernameNotFoundException` into a business 404/200. Business endpoints need a domain service and their own authorization/data-hiding rules.

For example, a logged-in user is not allowed to view someone else's profile. That is an **authorization** issue, not username lookup during login. Separating those layers avoids data leaks and wrong responses.

## 9. Common Mistakes

**Mistake 1 — Returning `null` when a user is not found.**  
Violates the `UserDetailsService` contract; can lead to internal errors instead of the failed-credentials branch. **Fix:** explicitly throw `UsernameNotFoundException`.

**Mistake 2 — Returning the raw exception to the client.**  
`UsernameNotFoundException: user X does not exist` easily leaks account lists. **Fix:** keep the provider's default hiding and standardize public responses.

**Mistake 3 — Leaving `setHideUserNotFoundExceptions(false)` on long-term for debugging.**  
Can cause login endpoints to distinguish missing users from wrong passwords. **Fix:** debug via safe tests/logs without changing public policy.

**Mistake 4 — Catching all repository errors and throwing UsernameNotFoundException.**  
Masks outages and makes operational failures hard to spot. **Fix:** only throw when lookup succeeds with no record; handle infrastructure errors separately.

**Mistake 5 — Creating a fake user with a default password to "avoid errors".**  
If the dummy account is misconfigured, it could accidentally log in or trigger unwanted authorization. **Fix:** use the proper exception contract; timing defenses belong to provider/security design.

**Mistake 6 — Using HTTP 404 for missing usernames in login.**  
Exposes account enumeration. **Fix:** map errors identically to wrong passwords per login protocol.

**Mistake 7 — Assuming identical BadCredentialsException means full enumeration protection.**  
Latency, password reset, sign-up, MFA, and account lockout can still leak data. **Fix:** test and harden every related endpoint.

**Mistake 8 — Throwing `UsernameNotFoundException` for missing permissions.**  
Missing roles/ownership is authz; having a user without permission does not mean the user is absent. **Fix:** separate authentication from resource authorization.

**Mistake 9 — Email login with inconsistent uniqueness/case rules.**  
One username might point to multiple records or fail to find a valid user. **Fix:** design consistent identifier normalization and unique constraints.

**Mistake 10 — Logging raw usernames/password hashes for investigation.**  
Creates sensitive-data risk in logs/CI. **Fix:** use correlation IDs and minimal, access-controlled telemetry.

## 10. Tests You Should Have

| Scenario | Expected Check |
|---|---|
| Direct `loadUserByUsername` call with existing user | Returns non-null `UserDetails`, right username, policy-matching hash/flags/authorities |
| Direct call with absent user | Throws `UsernameNotFoundException` |
| Through default `DaoAuthenticationProvider` with absent user | `BadCredentialsException` |
| Through provider with existing user but wrong password | Same public/external error type as absent user |
| Setting hide=false in unit test | Difference understood and kept out of public login |
| Disabled/locked account | Grants no successful authentication; controlled public response |
| Repository times out/loses connection | Does not become missing account, grants no token, triggers server alert |
| Lookup with varying letter casing | Follows normalization and uniqueness policy |
| Multi-tenant duplicate usernames | Never finds/leaks accounts outside permitted tenant |
| Sign-up/forgot password | Does not easily disclose account existence via body/headers/latency |
| Multiple failed logins | Rate limiting, brute-force monitoring, no secret leaks |
| Multiple providers supporting same token type | No check bypass via weak fallback |
| Authenticated but lacking permissions | Authorization denies independently of user lookup |
| Caching and account status changes | Stale data not used to permit policy-violating logins |

### 10.1. Self-Review Questions

**1. What does `UserDetailsService.loadUserByUsername` return if the username is not found?**  
Throw `UsernameNotFoundException`; never return `null`.

**2. Why does login with a non-existent username normally report `BadCredentialsException`?**  
Because `AbstractUserDetailsAuthenticationProvider` hides `UsernameNotFoundException` by default to reduce account enumeration.

**3. If `hideUserNotFoundExceptions=false` is set, what changes?**  
The provider can emit `UsernameNotFoundException` directly. Using this for public logins can leak information; never flip it casually.

**4. Should a database connection error throw `UsernameNotFoundException`?**  
No. An account lookup failing due to an outage differs from a valid lookup returning empty.

**5. Right username, but no permission to access a resource—should it be treated as user not found?**  
No. Handle it as authorization rather than misusing username lookup.

**6. Is returning the same JSON on all login failures enough to prevent account enumeration?**  
Not enough: timing, headers, redirects, reset/registration endpoints, and lockout policies also matter.

**7. Why not return HTTP 404 for a non-existent username at login?**  
Because it creates a response distinguishable from a wrong password and reveals which users are registered.

**8. With OIDC/JWT, do you always use UserDetailsService and UsernameNotFoundException?**  
No. That is the typical username/password contract through DaoAuthenticationProvider. Bearer JWT/OIDC has its own provider/identity-mapping chain; do not force every mechanism into the same exception.

## 11. Implementation Checklist

- [ ] `loadUserByUsername` returns a complete `UserDetails` or throws `UsernameNotFoundException`, never `null`.
- [ ] Treat only `Optional.empty()` as not-found; handle outages and data integrity errors in separate branches.
- [ ] Keep `hideUserNotFoundExceptions=true` for public username/password logins unless there is a vetted security reason.
- [ ] Use identical public errors for absent usernames and wrong passwords; do not leak exception messages.
- [ ] Unify normalization, uniqueness, tenant scope, and identity modeling.
- [ ] Use a strong password encoder and rate-limiting policies; test timing, logs, and auxiliary endpoints.
- [ ] Keep raw passwords/hashes/tokens and private info out of logs, error bodies, and URLs.
- [ ] Test unknown users, wrong passwords, disabled/locked accounts, storage outages, and multi-provider setups.
- [ ] Separate authentication lookups from business user lookups and authorization.
- [ ] When using sessions/JWTs, issue session credentials only after authentication succeeds and account policies are satisfied.

**Key takeaway:** `UsernameNotFoundException` is **a valid internal signal of the user-loading contract**. Yet public login must **not let attackers easily tell "account does not exist" apart from "wrong password"**. Follow the contract in `UserDetailsService`, keep default error hiding in `DaoAuthenticationProvider`, and harden the entire login/recovery/registration flow rather than changing just one message string.

### Official Documentation

- [Spring Security — UserDetailsService JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html): `loadUserByUsername` contract, non-null return, and `UsernameNotFoundException`.
- [Spring Security — AbstractUserDetailsAuthenticationProvider JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): `setHideUserNotFoundExceptions` and default choice.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): loading users and verifying passwords.
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/): authentication chain and configuration with `AuthenticationManager`.
- [Spring Security — UsernameNotFoundException JavaDoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/userdetails/UsernameNotFoundException.html): exception meaning and `AuthenticationException` hierarchy.

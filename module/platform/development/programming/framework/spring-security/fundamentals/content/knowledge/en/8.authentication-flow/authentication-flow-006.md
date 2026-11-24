# AuthenticationException and Distinguishing Invalid Credentials from System Errors

Mai types the wrong password, and the application replies that login failed. Ten minutes later, Mai enters the right password, yet the account data store has lost its connection. This time as well, the application cannot complete login. **Both requests failed to produce a trusted authentication result, yet their causes are completely different.**

If a developer catches every exception and returns "wrong password", users will keep retrying while the database is broken; a failed-password counter might even lock the account by mistake. Conversely, if the application returns a raw database connection error to the browser, it leaks internal details. Spring Security provides the `AuthenticationException` hierarchy to distinguish these kinds of failures.

This lesson explains **what `AuthenticationException` is, where it is created and handled in the Spring Security flow, how to tell invalid credentials apart from system failures, how to translate them into safe messages/HTTP responses, and how to log and test them**. The example uses Java 17+ and Spring Security to observe differences at the exception level before integrating into Servlet.

## 1. A Failed Login Has at Least Three Causes

Consider three scenarios:

| Scenario | Underlying reality | Sound system handling |
| --- | --- | --- |
| User provides a password that does not match the stored hash | Invalid login credentials | Reject authentication, create no session; increment/enforce anti-guessing policy if appropriate |
| Right user, but account is locked or disabled | Identity may exist, yet status policy forbids authentication | Reject login; per policy, direct to a safe verification or recovery channel |
| Unable to read account due to DB/identity provider outage | Not enough trustworthy data to decide right or wrong | **Fail closed**: grant no Authentication; record the infrastructure outage and return a service-temporarily-unavailable notice |

There are many other situations: no matching `AuthenticationProvider`, invalid JWT, identity service timeout, hash configuration error, MFA requirement policy, or expired credentials.

The starting point is **never conflate "authentication did not succeed" with "user typed the wrong password"**. Both end without a successful login, yet operations, monitoring, and external responses must differ.

### Three-layer view

~~~text
LAYER 1: EVIDENCE VERIFICATION
  Is the password/token valid?
  -> invalid -> reject due to credentials

LAYER 2: STATUS / IDENTITY POLICY CHECK
  Account enabled, non-locked, non-expired?
  -> no -> reject per policy

LAYER 3: SYSTEM ABILITY TO PROCESS
  Can the repository/identity service return trustworthy data?
  -> no -> service error; DO NOT pretend the password was checked and wrong
~~~

This is a mental model, not a fixed check order for every provider. In Spring Security, a provider may perform status checks before comparing passwords, and security patches may also perform extra checks to reduce response-timing leaks.

## 2. Which Layer Does AuthenticationException Belong To?

In Spring Security, the root type is:

~~~java
org.springframework.security.core.AuthenticationException
~~~

It is an **abstract class extending `RuntimeException`**, used to represent failures preventing an `Authentication` request from being validly authenticated. Key characteristics:

- `AuthenticationManager.authenticate(Authentication)` can return an authenticated `Authentication` **or throw an `AuthenticationException`**.
- Different `AuthenticationProvider` implementations can throw subtypes indicating the reason: wrong password, forbidden user state, missing provider, unable to reach service...
- `AuthenticationException` has `getMessage()` and possibly `getCause()`, yet **its message/cause must never be assumed safe to return to the client**.
- It belongs to **login/authentication**, unlike `AccessDeniedException`, which usually relates to **authorization** decisions after or during access control.

Common call model:

~~~text
HTTP request containing authentication credentials
             |
             v
Authentication filter / login controller
             |
             v
AuthenticationManager
    (usually ProviderManager)
             |
             v
Matching AuthenticationProvider
             |
             +--> valid outcome -> Authenticated Authentication
             |
             +--> invalid evidence -> BadCredentialsException
             |
             +--> disallowed status -> AccountStatusException subtype
             |
             +--> processing outage -> AuthenticationServiceException subtype
             |
             +--> no provider -> ProviderNotFoundException (in manager)
             |
             v
Failure handler matching the login mechanism
             |
             v
HTTP response / redirect / audit / metric
~~~

**Not every error inside authentication code automatically becomes an `AuthenticationException`.** A `NullPointerException`, coding bug, serialization error, or misconfiguration may remain another `RuntimeException` and be handled by the system error layer. Some providers translate repository exceptions into `AuthenticationServiceException` or `InternalAuthenticationServiceException`; that behavior depends on the implementation.

## 3. Important Subtypes to Remember

| Exception type | When it may occur | How to understand it |
| --- | --- | --- |
| `BadCredentialsException` | Invalid password or credentials; often also used for non-existent usernames | Request failed to prove identity; do not disclose externally whether the account exists |
| `UsernameNotFoundException` | `UserDetailsService` cannot find the user | In `DaoAuthenticationProvider`, by default usually masked as `BadCredentialsException` |
| `LockedException` | Account is locked | Subtype of `AccountStatusException`; not necessarily a wrong password |
| `DisabledException` | Account is disabled | Subtype of `AccountStatusException`; may need an activation/recovery flow |
| `AccountExpiredException` | Account validity period has expired | Distinct from an expired token or separate subscription |
| `CredentialsExpiredException` | Login evidence, usually the password, has expired per policy | Distinct from "password mismatch"; needs an appropriate change/reset flow |
| `AuthenticationServiceException` | Unable to process authentication request due to a system failure | E.g., user store/identity service unavailable; report infrastructure condition |
| `InternalAuthenticationServiceException` | Processing failure arising **inside the internal system**; subtype of `AuthenticationServiceException` | Can be distinguished from external provider errors; never turn into "wrong password" |
| `ProviderNotFoundException` | No provider/manager handles the requested `Authentication` type | Usually points to authentication wiring/configuration, not user typo |
| `InsufficientAuthenticationException` | Subject's authentication level is not trustworthy enough for a request | May require step-up authentication, not implicitly a wrong password |
| `AuthenticationCredentialsNotFoundException` | Required `Authentication` not found in security context | Usually occurs when policy requires authentication yet context lacks suitable identity |

With JWT, OAuth2/OIDC, SAML2, or MFA mechanisms, you will encounter mechanism-specific subtypes/error flows; you must still treat **invalid evidence**, **insufficient authentication level**, and **verification service outage** as distinct cases.

### Condensed class hierarchy

~~~text
RuntimeException
    |
    +-- AuthenticationException                 (abstract)
           |
           +-- BadCredentialsException
           +-- UsernameNotFoundException
           +-- AccountStatusException           (abstract)
           |      +-- LockedException
           |      +-- DisabledException
           |      +-- AccountExpiredException
           |      +-- CredentialsExpiredException
           |
           +-- AuthenticationServiceException
           |      +-- InternalAuthenticationServiceException
           |
           +-- ProviderNotFoundException
           +-- InsufficientAuthenticationException
           +-- AuthenticationCredentialsNotFoundException
           +-- ... other types ...
~~~

This diagram focuses only on types relevant to this lesson and does not list the entire Spring Security class hierarchy.

## 4. BadCredentialsException Does Not Necessarily Mean "Username Definitely Exists"

In an application using `DaoAuthenticationProvider` and `UserDetailsService`, two requests might be:

~~~text
username = "mai"          password = "wrong"
username = "nonexistent"  password = "any"
~~~

In the standard configuration, the provider has `hideUserNotFoundExceptions` defaulting to **true**. Accordingly:

- Existing username with mismatched password -> `BadCredentialsException`.
- Non-existent username where `UserDetailsService` throws `UsernameNotFoundException` -> provider normally **translates** it to `BadCredentialsException`.

The goal is to prevent login error messages from becoming an **account enumeration tool for discovering valid usernames/emails**.

Avoid changing this configuration like below without an evaluated security justification:

~~~java
// NOT RECOMMENDED FOR PUBLIC LOGIN:
provider.setHideUserNotFoundExceptions(false);
~~~

Doing so lets callers distinguish `UsernameNotFoundException` from a wrong password; if response mapping also differs, attackers can easily guess which accounts exist.

An application may still need to let legitimate users know their account is locked or password expired to assist them. Do this **after proper identity verification**, through a controlled channel or a safe recovery flow. Never expose raw internal status to anyone who merely submits a username.

**Important:** differences in HTTP status codes, redirect URLs, response times, HTML, body sizes, and rate limiting can also leak information. Merely making the string message generic is not enough.

## 5. AuthenticationServiceException: System Cannot Decide Right/Wrong

Suppose:

- The user store in the database is temporarily unreachable.
- The remote identity service times out.
- Required verification material cannot be read because a dependent service went down.
- The repository layer reports an error preventing consistent authentication data retrieval.

These are cases **lacking conditions to trust any authentication outcome**, distinct from `PasswordEncoder.matches(raw, hash)` having run and returned `false`.

Spring Security defines `AuthenticationServiceException` for failures to process an authentication request due to system issues. `InternalAuthenticationServiceException` specializes the case of **an error arising inside the internal system**; this classification helps with logs, metrics, and separating external provider failures.

Example when writing a custom `UserDetailsService`:

~~~java
// Fragment: accountRepository is a component the application must provide.
@Override
public UserDetails loadUserByUsername(String username) {
    try {
        return accountRepository.findForAuthentication(username)
            .map(accountMapper::toUserDetails)
            .orElseThrow(() -> new UsernameNotFoundException("Not found"));
    } catch (UsernameNotFoundException exception) {
        throw exception;
    } catch (DataAccessException exception) {
        throw new InternalAuthenticationServiceException(
            "Cannot read authentication repository", exception);
    }
}
~~~

This is an **illustrative fragment inside a service with Spring Data**, not standalone runnable code: it requires imports, repository, mapper, and proper transactions. The code intentionally:

1. Preserves `UsernameNotFoundException` when **the query succeeded yet no account was found**.
2. Translates infrastructure `DataAccessException` into `InternalAuthenticationServiceException` with its cause for internal diagnostics.
3. **Does not** catch all `Exception`s and throw `UsernameNotFoundException` or `BadCredentialsException`.
4. **Does not** return an empty list/dummy user while the DB is broken just to "keep login running".

In practice, `DaoAuthenticationProvider` may already translate repository errors other than `UsernameNotFoundException` into an appropriate service exception subtype. Add a custom mapping layer only when it adds value and does not obscure the root cause.

### Distinguishing "broken service" from "data not found"

~~~text
Database query succeeds, result = empty
  -> identity not found
  -> UsernameNotFoundException (provider may mask as BadCredentials)

Database query throws connection/timeout error
  -> CANNOT know if account exists or password matches
  -> AuthenticationServiceException subtype / system failure

Query succeeds, user/hash present, PasswordEncoder.matches = false
  -> credentials mismatch
  -> BadCredentialsException
~~~

Never turn an "unknown" state into "wrong" just because neither grants access.

## 6. Check Order in DaoAuthenticationProvider and ProviderManager

A typical username/password flow:

~~~text
POST /login
    |
    v
UsernamePasswordAuthenticationFilter
    |
    v
AuthenticationManager (ProviderManager)
    |
    v
DaoAuthenticationProvider
    |
    +-- UserDetailsService.loadUserByUsername(...)
    |        |
    |        +-- not found -> UsernameNotFoundException
    |        +-- datastore fails -> AuthenticationServiceException subclass
    |        +-- returns UserDetails + password hash
    |
    +-- checks account status (enabled/locked/expired)
    +-- PasswordEncoder checks raw password against hash
    +-- checks credentials status
    |
    +-- success -> Authentication
    +-- failure -> AuthenticationException
    |
    v
Filter handles success/failure per configuration
~~~

`AuthenticationManager` itself does not emit HTTP statuses. It processes an `Authentication` and returns an authenticated `Authentication` or throws an exception. **HTTP responses belong to the web/filter/controller layer.**

`ProviderManager` can try multiple `AuthenticationProvider` instances in order, depending on token types and results. A `BadCredentialsException` from the first provider is not always the final result if a later provider can authenticate successfully. However, cases like `AccountStatusException` or `InternalAuthenticationServiceException` usually make `ProviderManager` **stop immediately**, without trying another provider. Read the actual configuration before assuming the final exception.

`ProviderNotFoundException` reports that no provider handles that `Authentication` type; it usually indicates wiring or authentication strategy issues. Do not tell the user "wrong password" and close the incident.

### Do not use the exception class like a second password

Some applications intentionally replace exceptions with `BadCredentialsException` to "hide" everything. Hiding details from external users is reasonable, yet **the internal failure category must still be preserved in logs/metrics**. You can return a generic login-failed message while accurately recording that the system just hit an infrastructure outage.

Misclassification leads to wrong operational decisions: locking accounts by mistake, incrementing `failedPasswordAttempts`, misjudging brute-force rates, missing a DB outage, or retrying a wrong-password failure forever.

## 7. Standalone Java 17+ Example: Correct Password, Wrong Password, Non-Existent User, and Repository Error

This example invokes Spring Security's **real `AuthenticationManager`/`DaoAuthenticationProvider`**. It has no Servlet/HTTP, creates no session, stores no JWT, and manages no database; its sole purpose is to observe **the exception type after an authentication attempt**.

We use an in-memory `UserDetailsService` with three fixed behaviors:

- `mai`: found, valid password is `correct-password`.
- Any username other than `mai`, except `repository-offline`: user not found.
- `repository-offline`: simulates an infrastructure failure with `InternalAuthenticationServiceException`.

### 7.1. Create Gradle structure

~~~text
authentication-error-demo/
  build.gradle
  src/main/java/AuthenticationErrorDemo.java
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:7.1.2'
}

application {
    mainClass = 'AuthenticationErrorDemo'
}
~~~

Because this is a standalone program, Spring Security 7.1.2 is pinned so learners have a deterministic code base. **In real Spring Boot**, use `spring-boot-starter-security` and let Boot's BOM manage module versions. The code runs on Java 17+, requiring a compatible Gradle installation and initial library download access.

### 7.2. Complete Java file

Create `src/main/java/AuthenticationErrorDemo.java`:

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
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

public class AuthenticationErrorDemo {

    private static AuthenticationManager createManager() {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        String hash = encoder.encode("correct-password");

        UserDetailsService users = username -> {
            if ("repository-offline".equals(username)) {
                throw new InternalAuthenticationServiceException(
                        "Simulated authentication repository outage",
                        new IllegalStateException("Simulated connection failure"));
            }

            if (!"mai".equals(username)) {
                throw new UsernameNotFoundException("User not found");
            }

            return User.withUsername("mai")
                    .password(hash)
                    .roles("USER")
                    .build();
        };

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        // hideUserNotFoundExceptions defaults to true.
        return new ProviderManager(provider);
    }

    private static void attempt(
            AuthenticationManager manager,
            String label,
            String username,
            String password) {

        try {
            Authentication input =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password);

            Authentication result = manager.authenticate(input);
            System.out.println(label + " -> SUCCESS:" + result.getName());

        } catch (BadCredentialsException exception) {
            System.out.println(label + " -> INVALID_CREDENTIALS");

        } catch (AuthenticationServiceException exception) {
            System.out.println(label + " -> SERVICE_UNAVAILABLE");

        } catch (AuthenticationException exception) {
            System.out.println(label + " -> OTHER_AUTHENTICATION_FAILURE");
        }
    }

    public static void main(String[] args) {
        AuthenticationManager manager = createManager();

        attempt(manager, "correct", "mai", "correct-password");
        attempt(manager, "wrong-password", "mai", "wrong");
        attempt(manager, "unknown-user", "does-not-exist", "any");
        attempt(manager, "repository-down", "repository-offline", "any");
    }
}
~~~

All user data, passwords, and DB errors are fake. This code does not log real passwords and needs no connection to a database or external service once dependencies are downloaded.

Run with Java 17+ and Gradle:

~~~bash
gradle run --quiet
~~~

Lines printed by the program itself in order:

~~~text
correct -> SUCCESS:mai
wrong-password -> INVALID_CREDENTIALS
unknown-user -> INVALID_CREDENTIALS
repository-down -> SERVICE_UNAVAILABLE
~~~

Case-by-case breakdown:

1. **`correct`:** `UserDetailsService` finds Mai and `PasswordEncoder.matches` matches the hash, so the manager returns an authenticated `Authentication`.
2. **`wrong-password`:** user exists yet password does not match; provider throws `BadCredentialsException`.
3. **`unknown-user`:** `UserDetailsService` throws `UsernameNotFoundException`; `DaoAuthenticationProvider` by default hides the distinction with `BadCredentialsException`.
4. **`repository-down`:** service throws `InternalAuthenticationServiceException`, which is an `AuthenticationServiceException`, and the dedicated service-error catch handles it.
5. The final `catch (AuthenticationException)` handles authentication failure types **not yet specifically categorized**. It does not mean bad credentials.

**Why does catch order matter?** `BadCredentialsException` and `AuthenticationServiceException` both extend `AuthenticationException`. If `catch (AuthenticationException)` is placed first, the specific catch blocks below it can never receive their exceptions and the Java compiler reports an unreachable catch error.

**Why use bcrypt instead of `{noop}`?** `BCryptPasswordEncoder` creates a password hash. Even in an exception demo, we want to demonstrate real verification flow rather than plaintext comparison in production. The hash generated on each run has a random salt, so we do not print/compare exact hash contents; the logical output remains deterministic.

### 7.3. Why should failed logins not all be "retried the same way"?

With `BadCredentialsException`, immediately retrying **the exact same username/password** usually solves nothing. You can guide users to double-check their input or use a safe recovery flow. Systems also need rate limiting.

With `AuthenticationServiceException`, a **controlled retry** after the service recovers can succeed with those same credentials. However, strictly avoid unbounded retry loops that flood an impaired database/identity provider. Timeouts, retry budgets, and circuit breakers are needed per system design.

The standalone example does not retry itself. It only proves **the cause category** must be preserved.

## 8. Translating AuthenticationException into an HTTP Response

`AuthenticationException` is a Java exception. It **does not carry HTTP 401, 403, 500, or 503 itself**. The HTTP code and body are decided by the filter, `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, controller, or error handler actually processing the request.

An API policy might be:

| Scenario | Suggested status | Public body | Reason |
| --- | --- | --- | --- |
| Invalid credentials | `401 Unauthorized` | `{"error":"LOGIN_FAILED"}` | Unable to authenticate |
| User not found | `401 Unauthorized` same as invalid credentials | Same `LOGIN_FAILED` | Reduce username enumeration |
| Account locked/disabled before login | May use `401` with generic body; another flow after verification | Do not expose account status to strangers | Reduce account enumeration |
| User store/IdP unavailable | `503 Service Unavailable` if app configures service-error classification | `{"error":"AUTHENTICATION_UNAVAILABLE"}` | User cannot fix by changing password |
| Provider misconfigured | `500` or `503` depending on cause and policy | `{"error":"INTERNAL_ERROR"}` | Needs internal configuration investigation |
| Authenticated yet lacking permission for resource | Usually `403 Forbidden` | `{"error":"FORBIDDEN"}` | This is an authorization issue, not failed login |
| Unauthenticated when accessing protected endpoint | Usually `401` or redirect to login per client type | Corresponding message/redirect | This is an auth challenge, not necessarily a failed login attempt |

**The table above describes an intentional design, not a claim that Spring Security automatically returns 503 for every `AuthenticationServiceException`.** By default, form login may redirect to `/login?error`, HTTP Basic may send a 401 challenge, or handle differently depending on the exception's path. To differentiate responses, configure **the exact mechanism handling login** and test behavior end-to-end.

### 401, 403, and 503 differ in meaning

- **401:** the request needs valid authentication evidence. In HTTP Basic, the response usually includes `WWW-Authenticate` so the client knows how to authenticate.
- **403:** the server refuses the action per policy even though the request may already be authenticated; a request missing a CSRF token can also be rejected with 403 unrelated to passwords.
- **503:** the service is temporarily unable to handle the request. A server unable to read the user store **cannot conclude the password is wrong**, yet must not grant access either.
- **500:** a server error not handled as an expected business/authentication case, such as a coding bug or misconfiguration.

HTTP status codes should match protocol and client contracts. Using different codes can help clients, yet can also create **side channels for probing account status** if differences depend on whether an account exists or is locked. Always evaluate both public responses and support needs.

## 9. FailureHandler, AuthenticationEntryPoint, and ExceptionTranslationFilter Differ

This is a very common place to catch exceptions in the wrong spot.

### 9.1. Form login: AuthenticationFailureHandler

When form login is handled via `UsernamePasswordAuthenticationFilter`/`AbstractAuthenticationProcessingFilter`, an authentication failure goes to `AuthenticationFailureHandler`. `SimpleUrlAuthenticationFailureHandler` can redirect back to the login page with an error parameter.

If you want an API receiving login POSTs through the **form login mechanism** and returning JSON that distinguishes service errors, you can configure a custom handler. This is a **fragment inside a Servlet SecurityFilterChain configuration**, not a standalone class:

~~~java
http.formLogin(form -> form
    .failureHandler((request, response, exception) -> {
        response.setHeader("Cache-Control", "no-store");
        response.setContentType("application/json;charset=UTF-8");

        if (exception instanceof AuthenticationServiceException) {
            response.setStatus(503);
            response.getWriter().write(
                "{\"error\":\"AUTHENTICATION_UNAVAILABLE\"}");
        } else {
            response.setStatus(401);
            response.getWriter().write(
                "{\"error\":\"LOGIN_FAILED\"}");
        }
    })
);
~~~

This configuration assumes a login request is processed by the form-login filter and the frontend expects JSON. It **does not set up CSRF tokens, providers, login pages, or post-login account state handling itself**. Traditional HTML forms may be better served by a fixed redirect to a safe error page; design for the actual client type.

Note that `AuthenticationServiceException` requires importing from `org.springframework.security.authentication`. Never push `exception.getMessage()` or a stack trace straight into the response. Never let responses include sensitive request data.

### 9.2. Accessing a login-required endpoint: AuthenticationEntryPoint

A `GET /private` request without credentials can be routed by `ExceptionTranslationFilter` to `AuthenticationEntryPoint` to begin an authentication flow. For instance, form login may redirect to `/login`; HTTP Basic may return 401 with a challenge.

This **does not necessarily mean the user entered a wrong password**. `AuthenticationEntryPoint` is invoked when authentication is required per the configured flow; never assume every anonymous request to `/private` was a failed password attempt.

### 9.3. HTTP Basic handles errors in a different filter

`BasicAuthenticationFilter` reads credentials in the `Authorization` header, calls the authentication manager, and handles failure via the corresponding Basic/entry point mechanism. Configuring only `formLogin().failureHandler(...)` **does not ensure** errors from HTTP Basic pass through the form login handler.

If an application has multiple chains (`/api/**` and web), check **which chain and filter actually handle the request** before configuring error mapping.

### 9.4. @ControllerAdvice does not catch every Spring Security error

A `@RestControllerAdvice` can handle exceptions thrown by controllers/services in Spring MVC. However, many authentication exceptions occur **inside the security filter chain, before the request ever reaches a controller**. Thus a single `@ExceptionHandler(AuthenticationException.class)` in MVC cannot be relied on to intercept all login failures.

If you call `AuthenticationManager.authenticate(...)` yourself in a controller, you decide how to catch exceptions there. If using built-in form login or Basic filter, prefer that mechanism's extension points.

## 10. Designing Error Responses: Safe for Users and Useful for Operators

A sound system maintains **two separate views**:

~~~text
                 AuthenticationException
                          |
                Internal classification
                  /               \
                 /                 \
        VALIDATION/POLICY         SERVICE FAILURE
                |                      |
                v                      v
     Generic response for         Temporarily unavailable
     unverified users             response (hide backend)
                |                      |
                +----------+-----------+
                           |
                           v
              Audit + metrics + correlation ID
              matching exact root cause
~~~

**External interface:** clear enough for users to know what to do next, without disclosing whether a username exists, whether an account is under investigation, or what database backend is used. Sensitive statuses can be communicated via verified email or an authenticated support session.

**Internal observability:** classify and track counts for `INVALID_CREDENTIALS`, `ACCOUNT_STATUS`, `AUTH_SERVICE_UNAVAILABLE`, `NO_PROVIDER`, latency, and success rates. Operations teams need to know whether a service outage is occurring.

### What should never be logged

- Raw passwords, OTPs, recovery codes, `Authorization` headers, JWTs/access tokens/refresh tokens.
- Session IDs/cookies, full `Authentication` objects, or request objects containing credentials.
- The raw `exception.getAuthenticationRequest()` value if the API version exposes it: that object may reference a request holding sensitive data.
- Connection strings containing database passwords, identity provider secrets, or full stack traces into public responses.

You may record **exception class**, category, trace/correlation ID, normalized endpoint, timestamp, service, and sanitized account info per data protection policy. Detailed stack traces belong in restricted-access operational channels with appropriate secret scrubbing.

**Do not attach personal identifiers as high-cardinality metric labels**: avoid using username/email as Prometheus labels. Dedicated audits may use hashed or safely stored account IDs with matching retention and access controls.

### Counting wrong passwords and locking accounts

Anti-brute-force policies can increment counters on `BadCredentialsException`. However, account for non-existent usernames, multiple providers, caches, and concurrency. **Never increment the "wrong password" counter on `AuthenticationServiceException`** because the system never verified whether the password was right or wrong.

An example observability-layer policy:

| Internal category | Increment failed-password counter? | Alert operations? |
| --- | --- | --- |
| Verified invalid credentials | Per policy/rate limit | Above threshold, assess brute force |
| Username does not exist | Do not tie to a fake account; can still rate-limit request source | Above enumeration threshold |
| Account locked/disabled/expired | Do not treat as wrong password by default | Per status audit policy |
| Authentication service down | **No** | **Yes**, service outage |
| ProviderNotFound/misconfiguration | No | Yes, needs config investigation |

If an application writes a custom `UserDetailsService`, never write `catch (Exception e) { throw new BadCredentialsException("Bad login"); }` because it completely erases the boundary above.

## 11. Common Mistakes When Handling AuthenticationException

1. **"Every `AuthenticationException` means wrong password."** No: there are system, status, configuration, and authentication-level errors too.
2. **"A database timeout means the user does not exist."** No: the data source has not returned a trustworthy answer.
3. **"`UsernameNotFoundException` is always shown to the client."** No: `DaoAuthenticationProvider` usually masks it as `BadCredentialsException`.
4. **"Setting `hideUserNotFoundExceptions=false` improves security."** It can expose user enumeration.
5. **"Returning `exception.getMessage()` is helpful to users."** Internal messages can contain infrastructure details or sensitive states.
6. **"Authentication errors should always return 403."** 401/403 carry different semantics; CSRF/authorization can also produce 403.
7. **"`AuthenticationServiceException` automatically returns 503."** No: HTTP status is decided by filters/handlers/controllers.
8. **"Adding a form-login failure handler handles HTTP Basic/JWT too."** No: those mechanisms have their own error handling hooks.
9. **"Adding `@ControllerAdvice` catches all security errors."** Filter chains can raise exceptions before MVC.
10. **"On DB errors, keep retrying login continuously."** Adds extra load while the system is impaired.
11. **"On DB errors, increment the failed-password counter."** Wrong: the password could not be checked.
12. **"`BadCredentialsException` means the account definitely exists."** No; providers can use the same exception for non-existent usernames.
13. **"Every locked account must be announced publicly."** Differentiated status messages can enable account enumeration.
14. **"Turning all errors into 401 removes the need for metrics."** You lose the ability to tell an outage from brute force; observability is still required.
15. **"Just catch `RuntimeException` and return 401 to be safe."** Can hide serious bugs and mislead clients.
16. **"ProviderNotFoundException means wrong password."** It can mean no provider handles the token; check wiring/configuration.
17. **"Failed login always means resetting the password."** Wrong for service outages or insufficient authentication levels.
18. **"JWT login throws all the same exceptions as DaoAuthenticationProvider."** No; JWT/resource servers have their own filters/providers/exceptions.
19. **"No SecurityContext in the controller means a password was tried and failed."** An authentication attempt may never have been made.
20. **"Logging the full authentication request helps debugging."** Risks leaking credentials/tokens; sanitize and isolate sensitive data.

## 12. Minimum Test Matrix

To prove the system distinguishes failures properly, test at **two layers**:

- **Unit/integration at AuthenticationManager/Provider:** verify exact internal exception types.
- **End-to-end HTTP through filters/chains:** verify exact status/body/redirect, no information leaks, and no session created on failure.

| Test scenario | At AuthenticationManager | Expected response/policy |
| --- | --- | --- |
| Valid username, valid password | Successful `Authentication` | Per flow, session/token or appropriate response |
| Valid username, wrong password | `BadCredentialsException` | Generic login failure message; usually 401 for APIs |
| Non-existent username | Usually masked as `BadCredentialsException` | No distinguishable difference from wrong password |
| Locked account | `LockedException` per provider mechanism | Do not expose sensitive status prior to verification |
| Disabled account | `DisabledException` | Safe response policy, separate activation flow if any |
| Expired password | `CredentialsExpiredException` | Valid change/reset workflow, no full access granted |
| DB/repository timeout | `AuthenticationServiceException` subtype or mapped system error | Issue no Authentication; alert operations; possibly 503 |
| No provider supports token | `ProviderNotFoundException` | Do not turn into wrong password; inspect wiring |
| User has Authentication yet lacks role | Usually **not** a new login exception | Authorization denies, usually 403 |
| POST rejected by CSRF | May **never call AuthenticationManager** | CSRF handled by filter; usually 403 |
| Failed form login | Right chain's failure handler called | Redirect/message per UI policy |
| Failed Basic auth | Basic filter/entry point handles | Basic response per client, not relying on form handler |
| Invalid OAuth2/JWT signature | Corresponding token/validation error | Deny access, avoid leaking token configuration |
| DB down during peak traffic | Service error category spikes | Alert, retry budget/circuit breaker, no mistaken user lockouts |

With Spring Boot and MockMvc, `@WithMockUser` **does not** prove passwords were checked by a provider: the annotation sets up a pre-built `Authentication` to test authorization. To verify `BadCredentialsException` or `AuthenticationServiceException`, send real login requests through the matching filter or invoke the real manager in integration tests.

### Keeping errors safely hidden yet still observable

When users with and without accounts both enter bad credentials, public responses should show no exploitable differences in message, status, URL, or timing. Internally in metrics, however, the application can still distinguish **system errors** from **credential errors** without revealing that to callers.

During a real outage, it is critical never to emit a successful `Authentication` via a "let-through" fallback, stale cache, or unmanaged emergency account. **Fail closed** means granting no access without trustworthy evidence; it does not mean hiding all failure telemetry from operators.

## 13. Scenarios to Think Through Further

### Scenario A — Repository throws a connection error

The app catches `DataAccessException` and throws `BadCredentialsException` with message `Invalid username or password`. What goes wrong?

**Answer:** the system loses visibility into the service outage, clients get uselessly told to fix their passwords, failed-password counters may increment wrongly, and operators struggle to detect the outage. Preserve the internal service-error type, fail closed, and pick a safe public response without leaking details.

### Scenario B — One provider receives two usernames

One username exists with a wrong password; the other username does not exist. Both throw `BadCredentialsException`. Is that wrong?

**Answer:** no; this is the recommended behavior to reduce account information leakage. You should still check for differences in processing time, HTTP status, and public body.

### Scenario C — Admin locks an account right as a user logs in

`DaoAuthenticationProvider` throws `LockedException` even though the user's password was right. Should it count as a wrong password attempt?

**Answer:** not by default. This is an account-status rejection and should be audited separately and handled under unlock policies. Watch for race conditions if account state changes mid-login.

### Scenario D — Guest visits a login-required URL without sending username/password

The system invokes `AuthenticationEntryPoint` sending them to the login page. Does that mean `BadCredentialsException` occurred?

**Answer:** not necessarily. The request currently has no valid Authentication; it may not have attempted password authentication at all.

### Scenario E — External Auth0/Keycloak/IdP

If a remote IdP returns an HTTP 500 error, should it be treated as the user's wrong password?

**Answer:** no. Distinguish trusted IdP protocol responses, network failures, configuration errors, and invalid evidence. Never expose raw IdP messages to clients or allow untrusted callers to trigger unbounded log storms. Exception types depend on the integration, not necessarily `DaoAuthenticationProvider`.

### Scenario F — HTTP API returns 401 when the DB is down

Can that happen? Is Spring Security broken?

**Answer:** yes, it can happen depending on exception handling and configuration. Returning 503 for infrastructure outages is an explicit design choice when proactively mapped; Spring Security does not guarantee that default across every filter/login mechanism.

## 14. Pre-Production Deployment Checklist

- [ ] Distinguish **invalid credentials**, **account status**, and **authentication service failure** in your internal error model.
- [ ] Never catch all exceptions from the user store and convert them to `BadCredentialsException`.
- [ ] `UserDetailsService` throws `UsernameNotFoundException` only when *genuinely not found*, keeping DB/IdP failures as system errors.
- [ ] `DaoAuthenticationProvider` uses an appropriate `PasswordEncoder` and hides missing users per security requirements.
- [ ] Form login, Basic, JWT, OAuth2, or custom controllers each have **error handling in the right flow**.
- [ ] External responses never leak account status, stack traces, hostnames, SQL, or system info.
- [ ] Status codes 401, 403, 500, 503 follow the client contract rather than indiscriminate catch-all blocks.
- [ ] Never create sessions/tokens without sufficient authentication evidence.
- [ ] Never increment failed-password counters when a service error prevented checking the password.
- [ ] Never retry infinitely when the user store/IdP loses connectivity.
- [ ] Audits/metrics separate system failures from credential failures, with correlation IDs for investigation.
- [ ] Never log passwords/OTPs/tokens, session IDs, or full Authentication requests.
- [ ] Test account enumeration across messages, statuses, response timing, and reset flows.
- [ ] Run real HTTP tests through filters, because `@WithMockUser` does not test login.
- [ ] Keep Spring Security and auth libraries patched, checking related timing or account-disclosure advisories.

## 15. Self-Check Questions

**Question 1.** Why is `AuthenticationException` not a synonym for `BadCredentialsException`?

*Answer:* `AuthenticationException` is the base class for many authentication failure categories, including invalid credentials, account status, service errors, missing providers, or insufficient authentication level. `BadCredentialsException` is just one subtype.

**Question 2.** `UserDetailsService` throws `UsernameNotFoundException`, so why is `BadCredentialsException` still often seen externally?

*Answer:* `DaoAuthenticationProvider` by default masks missing-user errors with generic `BadCredentialsException` to prevent username enumeration.

**Question 3.** The password is correct, yet the database cannot be queried. Can you conclude the user entered invalid login details?

*Answer:* No. The system has not verified the evidence; fail closed, handle the service failure, and do not pollute wrong-password counters.

**Question 4.** Which branch does `InternalAuthenticationServiceException` belong to?

*Answer:* It extends `AuthenticationServiceException`, used for internal system errors preventing authentication processing.

**Question 5.** Why must `catch (AuthenticationException)` be placed after specific catch blocks?

*Answer:* Because Java matches catch clauses in order; catching the parent class first makes subsequent child catch clauses unreachable.

**Question 6.** Does `AuthenticationManager.authenticate` returning a successful `Authentication` mean the user can view someone else's profile?

*Answer:* No. Authorization decides permissions per action/resource after authentication; it may still deny with 403.

**Question 7.** Form login has a failure handler returning 503 on service errors. Why isn't that enough for HTTP Basic to return 503?

*Answer:* Basic uses its own filter and entry point handling; form login's failure handler is not invoked automatically for Basic.

**Question 8.** A DB error is converted to `BadCredentialsException` and the UI returns a generic 401. Is the system still "safe" because it hid the DB error?

*Answer:* Not enough. Denying access is necessary, yet misclassification corrupts metrics, lockout policies, and recovery. Generic public responses and accurate internal classification can coexist.

**Question 9.** Does `AuthenticationServiceException` decide HTTP status codes itself?

*Answer:* No. It is a Java exception; filters/handlers/entry points/controllers translate it into HTTP behavior.

**Question 10.** Why should you never print the raw `AuthenticationException.getAuthenticationRequest()` into logs?

*Answer:* The authentication request object may hold or reference sensitive credentials. Log only sanitized minimal data and operational error info.

The key takeaway when reading any login flow is: **"Evidence proved invalid" is different from "the system could not check the evidence."** Spring Security provides `AuthenticationException` subtypes to express that distinction. Preserving accurate internal error types while returning safe public messages prevents both security flaws and operational mistakes.

### References

- [Spring Security — AuthenticationException API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/AuthenticationException.html)
- [Spring Security — AuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [Spring Security — BadCredentialsException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/BadCredentialsException.html)
- [Spring Security — AuthenticationServiceException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationServiceException.html)
- [Spring Security — InternalAuthenticationServiceException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/InternalAuthenticationServiceException.html)
- [Spring Security — AbstractUserDetailsAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — AuthenticationFailureHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html)

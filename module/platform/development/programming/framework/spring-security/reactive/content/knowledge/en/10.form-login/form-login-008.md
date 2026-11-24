# Saving Context After Login and Rotating Session IDs to Mitigate Session Fixation in Spring Security Reactive

## 1. The Problem to Solve

Form login in Spring WebFlux does not end with verifying the username/password. After successful authentication, a stateful web app typically needs to **write `SecurityContext` into `WebSession`** so subsequent requests recover the logged-in identity. At the same time, the server must **rotate the session identifier (session ID)** at the privilege-escalation boundary from anonymous to authenticated to mitigate **session fixation**.

Imagine a user:

1. Opens `/login` and receives a session cookie when the server needs to store data such as a CSRF token.
2. Enters username and password; the browser submits `POST /login` with the existing cookie.
3. The server checks credentials and creates a trusted `Authentication`.
4. The server **saves `SecurityContext`** into the session and **rotates the session ID**.
5. The browser uses the new session cookie for `GET /api/me`; the server loads `SecurityContext` back and recognizes the exact user.

If step 4 is skipped or misimplemented, two separate issues can occur: **login is not persisted across requests**, or **a session ID already known to an attacker remains usable after the victim logs in**.

Lesson objectives:

- Understand `SecurityContext`, `Authentication`, `WebSession`, session cookies, and `Reactor Context`.
- Use **`WebSessionServerSecurityContextRepository`** to save/load `SecurityContext` across requests.
- Understand **`WebSession.changeSessionId()`** and why the default form-login repository rotates the ID on save.
- Configure **`ServerHttpSecurity`** so form login's **save** path and `ReactorContextWebFilter`'s **load** path use the exact same repository.
- Practice Java 17+ with a patched Spring version, default form login, CSRF, cookie jars, and testing with `StepVerifier`.
- Distinguish session fixation from session hijacking, CSRF, and XSS; understand the limits of ID rotation.

**Focus:** rotating the ID when needed is not enough by itself; you must ensure **the authentication result is stored in the right place, the cookie is sent back properly, and the old ID can no longer be used** under your active session mechanism.

## 2. Objects in the Session Lifecycle

| Object | Responsibility | Do Not Misunderstand |
| --- | --- | --- |
| `Authentication` | Result of verifying the user and authorities | Does not persist across all requests on its own |
| `SecurityContext` | Wraps `Authentication` | Not the session ID |
| `ReactiveSecurityContextHolder` | Reads `SecurityContext` from Reactor Context in the current subscription | Not a long-term session store |
| `ServerSecurityContextRepository` | Contract `load(exchange)` and `save(exchange, context)` | Not a Servlet `SecurityContextRepository` |
| `WebSessionServerSecurityContextRepository` | Stores `SecurityContext` in `WebSession`; rotates session ID on save | Does not create credentials or check passwords itself |
| `WebSession` | Holds session attributes and ID on the server | Different from `jakarta.servlet.http.HttpSession` |
| Session cookie | Helps the browser send the ID to the server on subsequent requests | Must not be treated like a loggable/public password |
| `ReactorContextWebFilter` | Loads `SecurityContext` from the repository into Reactor Context | Needs a repository compatible with where it was saved |
| Form login `AuthenticationWebFilter` | Authenticates username/password and saves context via configured repo | Does not automatically carry context across requests if using a NoOp repository |

A diagram:

~~~text
                           FIRST LOGIN
GET /login  ----------------> WebSession (not logged in)
     |                                  |
     +<------ CSRF token + cookie ID S0-+
     |
POST /login, cookie S0, username/password, _csrf
     |
     v
AuthenticationWebFilter -> ReactiveAuthenticationManager
     |
     +-- invalid ------> login?error, do not save authenticated context
     |
     +-- valid --------> Authentication(alice)
                              |
                              v
                      SecurityContext(alice)
                              |
                              v
                  WebSessionServerSecurityContextRepository.save()
                              |
                              +--> Write context to WebSession
                              +--> Rotate ID S0 -> S1
                              |
                              v
                     Redirect + Set-Cookie(S1)
                              |
                       SUBSEQUENT REQUEST
GET /api/me, cookie S1
     |
     v
ReactorContextWebFilter -> repository.load()
     |
     v
Reactor Context -> Authentication(alice) -> Authorization -> Controller
~~~

The diagram illustrates the concept under session-based form login. Whether a session exists prior to login depends on the request and components storing CSRF/request cache; if **S0 never existed**, the system can still create a new session when needed. It is not a prerequisite for login to succeed.

## 3. Understanding Session Fixation from Its Root Cause

**Session fixation** is an attack where an attacker gets a victim to use a **session ID that the attacker already knows or can control**, then waits for the victim to log in. If the server keeps that same ID after login and allows it to access the elevated session, the attacker can try using the same ID to impersonate the victim.

Illustrative example:

~~~text
BEFORE LOGIN
Attacker knows ID = S0
Victim also uses ID = S0

VICTIM LOGS IN
Server stores Authentication(alice)

FLAWED DESIGN
After login ID is still = S0
Attacker tries S0 -> risks accessing Alice's session

DESIGN WITH FIXATION PROTECTION
After login ID rotates to S1
ID S0 is no longer a valid credential for Alice's session
Victim holds S1, while attacker only knows S0
~~~

Rotating the session ID does not protect against all attacks. It **does not automatically defend** if `S1` is stolen after login via malware, XSS, weak cookie settings, proxy logs, URL leaks, or non-TLS HTTP channels. Those risks are **session hijacking** or other session-takeover techniques. Session fixation focuses on **a session ID that may already have been known prior to authentication**.

Conditions for meaningful protection:

1. Rotate to a random, unpredictable ID via a trusted WebSession/Session Store mechanism.
2. The old ID no longer maps to the logged-in session.
3. The browser is updated with the new cookie/session identifier.
4. All instances in a shared session system recognize the ID rotation.
5. Cookies have proper protective attributes, and the app uses HTTPS and defends against CSRF/XSS.
6. On logout/expiration, the session or `SecurityContext` is properly cleared.

Never generate IDs from usernames, timestamps, or `Random`; never send session IDs in query parameters to "make debugging easier".

## 4. Default Mechanism of Spring Security WebFlux Form Login

In **Spring Security Reactive**, `ServerHttpSecurity.FormLoginSpec.securityContextRepository(...)` chooses the repository that **saves `Authentication` after form login succeeds**. Per Spring Security 6.5 Javadoc, `FormLoginSpec`'s default is **`WebSessionServerSecurityContextRepository`**.

This class carries an important API contract: **when `SecurityContext` is saved, the session ID is changed to prevent session fixation**. It implements `ServerSecurityContextRepository`, with methods:

~~~java
Mono<SecurityContext> load(ServerWebExchange exchange);
Mono<Void> save(ServerWebExchange exchange, SecurityContext context);
~~~

In Spring Framework, the corresponding `WebSession`-level API is:

~~~java
Mono<Void> changeSessionId();
~~~

This is a **reactive** API, not Servlet's `HttpServletRequest.changeSessionId()`. The fact that `save()` returns `Mono<Void>` means the operation must be properly **subscribed/composed**; never create the publisher and discard it.

**Crucial note:** the default of a **directly instantiated `AuthenticationWebFilter`** is **`NoOpServerSecurityContextRepository`**. When using `http.formLogin(...)`, `FormLoginSpec` configures the repository on the form login filter. If you construct an `AuthenticationWebFilter` manually and only call `setAuthenticationSuccessHandler()`, do not assume it will persist identity across subsequent requests. Configure the repository explicitly.

### 4.1. Do Not Confuse Where Context Is Saved vs. Loaded

The Javadoc of `ServerHttpSecurity.securityContextRepository(repository)` notes it is the strategy used with **`ReactorContextWebFilter`**; meanwhile `FormLoginSpec.securityContextRepository(...)` governs how the **form login filter saves context after authentication**. They have distinct responsibilities and **are not always wired together automatically** when customizing manually.

Consistent design:

~~~java
ServerSecurityContextRepository repository =
        new WebSessionServerSecurityContextRepository();

return http
        .securityContextRepository(repository) // LOAD on subsequent requests
        .formLogin(form -> form
                .securityContextRepository(repository)) // SAVE on login
        .build();
~~~

The snippet above illustrates only the `SecurityWebFilterChain` portion, not a separately compilable Java class. Sharing the same repository prevents the "login succeeds yet next request is anonymous" bug caused by save and load pointing to two different stores.

### 4.2. Reactor Signal Flow

~~~text
POST /login
  -> authenticationManager.authenticate(...)
  -> Mono<Authentication> succeeds
  -> SecurityContextImpl(authentication)
  -> repository.save(exchange, context)
  -> WebSession rotates ID on save
  -> handler redirects/continues
  -> browser receives new session cookie

GET /api/me
  -> repository.load(exchange)
  -> Mono<SecurityContext>
  -> ReactorContextWebFilter puts into Reactor Context
  -> ReactiveSecurityContextHolder.getContext()
  -> Authorization and controller
~~~

If `repository.save` fails because the session store or backend is unavailable, the application **must not treat login as durably saved** and falsely report success. In a reactive flow, handle errors rather than calling `subscribe()` manually and ignoring the outcome.

## 5. Why Observe Both Cookies and SecurityContext?

Three distinct states can exist:

| State | What Is True? | Consequence |
| --- | --- | --- |
| Authentication succeeds only during login request | Manager verified the password | Does not yet prove the next request will have identity |
| `SecurityContext` is saved into `WebSession` | Session store has the authentication record | Next request can reload it if browser sends the right ID |
| Session ID rotated and new cookie is used | Pre-login ID is no longer the logged-in session's ID | Reduces session fixation risk |

How to prove end-to-end:

1. Before login, hold an unauthenticated session/cookie (if created).
2. Log in successfully with a valid CSRF token and password.
3. Verify the **post-login ID differs from the pre-login ID** if a prior ID existed.
4. Use the new cookie to call a protected endpoint → right user.
5. Reuse the pre-login cookie → **must not** read protected data.
6. Log out via a valid flow → the old cookie of the logged-out session no longer grants access.

Do not inspect only the status of `POST /login`: a 302 redirect can happen even if the client dropped the cookie or the app is using a NoOp context repo.

### 5.1. Form Login Differs from HTTP Basic and Bearer Tokens

Form login primarily serves browsers with login state persisted via a session cookie. HTTP Basic or bearer JWTs typically carry credentials on each request and **do not necessarily** need a server-side session. If choosing stateless, design specifically for it rather than trying to "rotate session IDs" for a session the system does not use.

`WebSessionServerSecurityContextRepository` fits session-based web apps. **`NoOpServerSecurityContextRepository`** fits cases where you intentionally do not save `SecurityContext` across requests; it does not rotate IDs on save because it does not save.

### 5.2. CSRF During Login

Spring Security WebFlux **protects `POST /login` with CSRF** by default. For the demo to work:

- GET `/login` first to obtain the page with the CSRF token.
- Send the cookie alongside the corresponding `_csrf` when POSTing the form.
- Do not disable CSRF just to shorten a curl POST command.

A missing CSRF token can return **403 before checking the password**, misleading learners into thinking the user/password was wrong. CSRF tokens protect cookie-based actions against forged cross-site requests; session ID rotation solves a different problem. With custom login forms, you must embed the token properly in the form.

## 6. Example Misconfiguration and How to Fix It

**Wrong: using NoOp repository in session-based form login**

~~~java
// Illustrates misconfiguration if login persistence across requests is required.
return http
        .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
        .formLogin(form -> form
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance()))
        .build();
~~~

A single request may authenticate successfully, yet `SecurityContext` is not persisted across session cookies with this repo. Nor does it rotate the ID via `WebSessionServerSecurityContextRepository.save()`.

**Right: using WebSession repository in both places**

~~~java
ServerSecurityContextRepository repo =
        new WebSessionServerSecurityContextRepository();

return http
        .securityContextRepository(repo)
        .formLogin(form -> form
                .securityContextRepository(repo))
        .build();
~~~

If using a custom `AuthenticationWebFilter`, call `setSecurityContextRepository(repo)` on that filter and also configure the load path from the same store. Do not write a custom filter just to rotate IDs when the standard repository already does it. If you design a custom replacement repository, you are **personally responsible** for save timing, ID rotation, invalidating old IDs, error handling, expiration, and multi-instance consistency; never assume every repository is safe by default.

## 7. Runnable Java 17+ Demo

Use **Spring Boot 3.5.16** (Java 17+, Gradle 8.4+ or compatible; Gradle 8.14+ recommended) so the example does not depend on older Spring Framework versions with disclosed WebFlux session fixation vulnerabilities. With Spring Boot 3.5.16, Spring Framework requires at least the 6.2.19 line, which contains the patch for the issue noted in section 12. When bringing a demo into a real system, always verify resolved dependency versions via a dependency report and apply the latest patches.

The application includes:

- GET `/public/ping`: public.
- GET `/login`: login page generated by Spring Security.
- POST `/login`: form login with username/password and CSRF.
- GET `/api/me`: accepted only when `SecurityContext` is restored via session.
- GET `/api/admin`: only for `ROLE_ADMIN`.
- POST `/logout`: default logout requiring appropriate CSRF.

Directory structure:

~~~text
webflux-form-session/
├── settings.gradle
├── build.gradle
├── src/main/java/example/session/SessionApplication.java
├── src/main/java/example/session/SecurityConfig.java
├── src/main/java/example/session/ApiController.java
└── src/test/java/example/session/SessionRepositoryTest.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-form-session'
~~~

### 7.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

To ensure consistent Gradle versions in team workflows, you can generate a **Gradle Wrapper** in the project using a valid Gradle installation; the demo does not depend on a pre-bundled wrapper.

### 7.3. SessionApplication.java

~~~java
package example.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionApplication.class, args);
    }
}
~~~

### 7.4. SecurityConfig.java — Unifying LOAD and SAVE Repositories

~~~java
package example.session;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    ServerSecurityContextRepository securityContextRepository() {
        return new WebSessionServerSecurityContextRepository();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerSecurityContextRepository repository) {

        return http
                // LOAD path on requests carrying a session cookie.
                .securityContextRepository(repository)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping", "/login", "/logout")
                            .permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                // SAVE path after successful POST /login.
                .formLogin(form -> form
                        .securityContextRepository(repository)
                        .authenticationSuccessHandler(
                                new RedirectServerAuthenticationSuccessHandler(
                                        "/api/me")))
                // Demo uses form login only, not Basic in parallel.
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .build();
    }
}
~~~

**Part by part:**

1. **Repository bean** is a shared `WebSessionServerSecurityContextRepository` instance; load/save responsibilities are explicit.
2. **`http.securityContextRepository(repository)`** configures the path restoring `SecurityContext` for `ReactorContextWebFilter` on subsequent requests.
3. **`form.securityContextRepository(repository)`** configures the path saving successful `Authentication` from form login. This repository performs session ID rotation on save.
4. **Success handler** redirects to `/api/me`; this demonstrates success for learners and does not itself create a session or assign `Authentication`.
5. **`httpBasic.disable()`** prevents confusion between per-request Basic credentials and cookie-based form login.
6. **`authorizeExchange`** requires login for `/api/**` and `ROLE_ADMIN` for the admin route. Logging in does not automatically grant access to every resource.
7. **Do not disable CSRF**: form `POST /login` and `POST /logout` must stay protected.
8. Do not change default logout; when customizing logout, synchronize clearing `SecurityContext`, session, and cookies.

Password values are **static examples for local dev only**. In production, use an identity store, secret rotation, and proper login policies.

### 7.5. ApiController.java

~~~java
package example.session;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(p ->
                Map.of("username", p.getName()));
    }

    @GetMapping("/api/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("report", "ok"));
    }
}
~~~

The controller neither reads nor outputs the session ID. It only inspects the request's `Principal` restored/verified by Spring Security. Never create an endpoint returning `WebSession.getId()` to clients just for debugging: a session identifier is a sensitive credential.

### 7.6. Running the Application

Requires JDK 17+, compatible Gradle, and access to Maven Central to download dependencies:

~~~bash
gradle bootRun
~~~

Upon successful startup, the demo listens on `http://localhost:8080` unless another port is configured. This is a local environment only; production must use HTTPS.

### 7.7. Browser Flow

1. Open `http://localhost:8080/login`. Spring Security generates the login page with username, password, and a hidden CSRF field.
2. Log in with `alice` / `alice-pass`.
3. On success, the browser redirects to `/api/me` and receives `{"username":"alice"}`.
4. Reload `/api/me`: still receives `alice` because the session cookie was sent back and the repository loaded `SecurityContext`.
5. Open `/api/admin` while logged in as `alice`: rejected with 403; logging in as `admin` / `admin-pass` satisfies `ROLE_ADMIN`.
6. Log out via a valid POST flow with CSRF; afterwards requests to `/api/me` must redirect to login or be denied.

Inspect the DevTools **Network** tab: the successful login request will yield a new cookie/session, though **never copy session IDs into logs/chats/tickets**. Headers/cookies may depend on reverse proxies, SameSite/Secure settings, and the session resolver.

## 8. Testing with curl Preserving Cookies and CSRF

A command like `curl -d 'username=alice&password=alice-pass' /login` is insufficient when CSRF is enabled by default. You need a **cookie jar** and to extract the token from the login page.

### 8.1. Step 1: GET Login Page

~~~bash
curl -sS -c before-login.cookies \
  http://localhost:8080/login \
  -o login.html
~~~

`before-login.cookies` stores cookies issued by the server before login (if a session was created). `login.html` holds the form generated by Spring Security. The CSRF token may be BREACH-masked, so you must submit **the exact value rendered in the form**.

To inspect the token manually, look for the input with `name="_csrf"` in `login.html`. Never take a token from another request or make up a random value.

### 8.2. Step 2: Send POST Login with the Token

In an environment with Python 3, you can extract the token using a short `HTMLParser` script:

~~~python
from html.parser import HTMLParser

class CsrfParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        if tag != "input":
            return
        values = dict(attrs)
        if values.get("name") == "_csrf":
            self.token = values.get("value")

parser = CsrfParser()
with open("login.html", encoding="utf-8") as file:
    parser.feed(file.read())

if not parser.token:
    raise SystemExit("No _csrf input found")
print(parser.token)
~~~

Save the code above as `extract_csrf.py` and run:

~~~bash
CSRF_TOKEN="$(python3 extract_csrf.py)"

curl -i -sS \
  -b before-login.cookies \
  -c after-login.cookies \
  --data-urlencode "username=alice" \
  --data-urlencode "password=alice-pass" \
  --data-urlencode "_csrf=$CSRF_TOKEN" \
  http://localhost:8080/login
~~~

Expect **`POST /login` to return a 302 or 303 redirect depending on the handler**, with `Location` pointing to `/api/me` per configuration. Cookie jar **`after-login.cookies`** will hold the updated session cookie issued when the server saved `SecurityContext`.

**Do not use `curl -L` in the initial step** if you want to clearly see the redirect response, `Set-Cookie`, and POST outcome. Afterwards you can use `-L` to follow redirects if preserving the cookie jar properly.

### 8.3. Step 3: Use the Post-Login Cookie

~~~bash
curl -i -sS -b after-login.cookies \
  http://localhost:8080/api/me
~~~

Expected response body:

~~~json
{"username":"alice"}
~~~

If using the **pre-login** cookie to call a protected endpoint:

~~~bash
curl -i -sS -b before-login.cookies \
  http://localhost:8080/api/me
~~~

This action **must not** return logged-in user data. With default form login, the unauthenticated request usually redirects to `/login`. If there was no pre-login cookie because no session had been created yet, that is still normal; verifying ID rotation requires a test with a real pre-login session `S0` (section 9).

**Distinguishing cookie files:** `curl` with `-c` writes only cookies known at the time of that execution. To compare accurately, save **`before-login.cookies`** separately and use **`after-login.cookies`** for follow-up requests. Never commit cookie files to version control or share them publicly; they can grant access to dev sessions.

### 8.4. Explaining Session IDs Before and After

In Spring WebFlux, the session cookie name is typically `SESSION` unless the cookie resolver is customized. Name, path, attributes, and Secure/SameSite state can differ in real applications. Compare **identifier values** before and after login when both appear.

| Milestone | ID | State |
| --- | --- | --- |
| Before login | S0 | Anonymous, may contain CSRF token |
| After successful login | S1, distinct from S0 | Holds Alice's `SecurityContext` |
| Subsequent request with S1 | S1 | Loads `SecurityContext` successfully |
| Request with S0 | S0 | Must not receive Alice's permissions |
| Successful logout | Session ended/context cleared per config | Old cookie no longer grants protected access |

Do not include real `S0`/`S1` values in demo screenshots or reports. You may log a **boolean `"rotated=true"`** for verification without logging raw session IDs.

## 9. Testing save/load/changeSessionId Functionality Directly

Testing the `WebSessionServerSecurityContextRepository` API in isolation makes ID rotation easy to observe without depending on login HTML or curl syntax.

File **`src/test/java/example/session/SessionRepositoryTest.java`**:

~~~java
package example.session;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.web.server.MockWebSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

import reactor.test.StepVerifier;

class SessionRepositoryTest {

    @Test
    void saveRotatesSessionIdAndLoadRestoresAuthentication() {
        WebSessionServerSecurityContextRepository repository =
                new WebSessionServerSecurityContextRepository();

        MockWebSession session = new MockWebSession();
        String originalSessionId = session.getId();

        MockServerWebExchange exchange = MockServerWebExchange
                .builder(MockServerHttpRequest.get("/api/me"))
                .session(session)
                .build();

        Authentication verified =
                UsernamePasswordAuthenticationToken.authenticated(
                        "alice",
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER")));

        SecurityContext context = new SecurityContextImpl(verified);

        StepVerifier.create(repository.save(exchange, context))
                .verifyComplete();

        assertNotEquals(originalSessionId, session.getId());

        StepVerifier.create(repository.load(exchange))
                .assertNext(restored -> {
                    assertEquals(
                            "alice",
                            restored.getAuthentication().getName());
                    assertEquals(
                            "ROLE_USER",
                            restored.getAuthentication()
                                    .getAuthorities()
                                    .iterator()
                                    .next()
                                    .getAuthority());
                })
                .verifyComplete();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected result:** the test PASSes and Gradle reports `BUILD SUCCESSFUL` in an environment with valid JDK/Gradle/dependencies. No fixed session ID string is assumed here: the IDs must differ, while the new ID value is random or managed by the Session Store.

This test proves **standalone repository behavior**: save has the side effect of rotating the ID, and load returns the right `Authentication`. It is **not sufficient to prove that a browser receives `Set-Cookie` or that the pre-login ID is invalidated across all replicas**; to guarantee end-to-end behavior, add real HTTP tests via WebTestClient/browser/curl, a real session store, and reverse proxies if used.

### 9.1. What Should Be Tested Over HTTP?

1. Unauthenticated `GET /api/me` → redirects to `/login`, cannot read username.
2. `GET /login` → form has CSRF token; cookie jar retained if a session exists.
3. `POST /login` with valid CSRF and right password → redirects and sets a valid session cookie.
4. `GET /api/me` with post-login cookie → right username.
5. `POST /login` with wrong password → no authenticated context saved, typically redirects to `/login?error`.
6. Send POST login without CSRF → rejected per CSRF rules, typically 403.
7. If pre-login ID `S0` existed, post-login `S1` must differ, and `S0` must not access `S1`'s session.
8. Valid logout → new request with the old cookie cannot read protected data.
9. Log in as `alice` and `admin` in two separate cookie jars → no `Authentication` cross-contamination.
10. Test behavior on session expiration, when the session backend is unavailable, and across restarts.

Do not test the repository only with `MockWebSession` and conclude real browsers are immune to session fixation. Session cookies, stores, proxies, and framework versions can all introduce differences.

## 10. Common Configuration Mistakes

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Configuring only `formLogin.securityContextRepository` while the load path uses another repo | POST login succeeds, subsequent GET is anonymous | Specify a consistent repository in both `formLogin` and `ServerHttpSecurity` |
| Using `NoOpServerSecurityContextRepository` despite wanting session login | Does not persist `SecurityContext` across requests | Use `WebSessionServerSecurityContextRepository` |
| Creating `AuthenticationWebFilter` manually and forgetting `setSecurityContextRepository` | Default filter does not save context | Configure repo on both the filter and load path |
| Manually calling `subscribe()` to save `SecurityContext` | Save errors detached from login lifecycle; no guarantee redirect waits for save | Compose `repository.save`'s `Mono<Void>` |
| Adding `Authentication` only to Reactor Context | Works for current subscription, does not persist across requests | Save via `ServerSecurityContextRepository` |
| Changing cookie only in JS without rotating ID in session store | Old ID may still remain valid | Use official `WebSession.changeSessionId`/session store mechanism |
| Calling `session.changeSessionId()` redundantly in multiple places | Causes hard-to-trace multiple ID rotations | Let `WebSessionServerSecurityContextRepository.save` do its job |
| Using Servlet `HttpSession`/`SessionFixationProtectionStrategy` in WebFlux | Wrong stack | Use `WebSession` and reactive APIs |
| Trying `POST /login` without sending CSRF | Receives 403 before password check | GET form, keep cookie, and send `_csrf` |
| Disabling CSRF just to make curl commands shorter | Exposes login CSRF/cross-site writes | Keep CSRF; support tokens in forms and tests |
| Sending session cookies over non-TLS HTTP | Bystanders can capture the new ID and hijack the session | HTTPS, `Secure`/`HttpOnly`/`SameSite`, and proxy config |
| Assuming rotation also prevents session hijacking | New ID can still be stolen after login | Combine XSS defense, TLS, and cookie protection |
| Setting Cookie Domain too broadly across untrusted subdomains | Risks cookie injection/session abuse | Restrict Domain/Path; prefer host-only cookies |
| Using a Spring Framework version with known CVEs | Still vulnerable even when config looks right | Upgrade to an officially patched release |
| Returning the session ID from an API for testing | Exposes session credentials | Use internal tests; never expose IDs publicly |
| Forgetting logout / timeout handling | Users may retain access longer than intended | Invalidate sessions and test expiration |

## 11. Storing Sessions in Multi-Instance Systems

**In-RAM user maps** and **in-RAM sessions** are two separate issues. In the demo, `UserDetails` in a Map is only for learning; WebFlux's default session store is typically in-memory for a single-process app and does not guarantee two instances see the same login state.

When running multiple replicas behind a load balancer:

- Use a **shared session store** supporting reactive I/O, such as configuring Spring Session with an appropriate Redis setup.
- Ensure **`changeSessionId`** updates the mapping in the store with proper semantics so the old ID is no longer accessible.
- Ensure every replica shares identical cookie configuration (name, Domain, Path, SameSite, Secure) and session attribute serialization.
- Bound TTL, max idle time, key rotation, recovery, and revocation policies.
- When using session clustering, test login/redirect/subsequent requests across **two different instances** rather than only one.
- Do not rely solely on sticky sessions to mask broken ID rotation or store inconsistencies.

Spring Session provides **`ReactiveRedisSessionRepository`** / **`@EnableRedisWebSession`** for WebFlux, though connecting Redis, secrets, TLS, serializers, and TTL configuration is a separate deployment concern. Do not add a Redis dependency to a demo without a running Redis server and real configuration.

When logging out or changing a password, business requirements may call for invalidating multiple sessions. Rotation at login does not replace logout-all-devices policies, concurrent session limits, or auditing.

## 12. Security Advisory Update: CVE-2026-41839

On **June 8, 2026**, Spring disclosed **CVE-2026-41839 – Spring Framework Escalation via Session Fixation in WebFlux**, involving scenarios with a compromised subdomain and transferring a known session ID to an authenticated user. This is a practical reason never to look only at code calling `changeSessionId` and assume the system is guaranteed safe.

Per Spring's advisory, affected Framework lines include:

- **7.0.0–7.0.7**.
- **6.2.0–6.2.18**.
- **6.1.0–6.1.27**.
- Branches **5.3.48 and earlier**.

Publicly announced patches in the advisory include **Spring Framework 7.0.8** and **6.2.19**; older lines have different support terms. Applications must run a vendor-patched version, even when already using `WebSessionServerSecurityContextRepository`.

**That is why the demo selects Spring Boot 3.5.16**, avoiding an older example like Spring Boot 3.3.5 based on a Spring Framework branch prior to this vulnerability disclosure. When migrating an existing project, verify the actual resolved version via:

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

Then locate the versions of `org.springframework:spring-webflux`, `spring-web`, and `spring-session` (if present), and compare against the official advisory. Never assume changing the Spring Boot plugin version alone removes prior BOM overrides or pinned dependencies.

Source: https://spring.io/security/cve-2026-41839/

## 13. Pre-Production Checklist

**Securing the login flow:**

1. Use HTTPS everywhere; trust `X-Forwarded-*` only from controlled reverse proxies.
2. Every form login POST must include a valid CSRF token; protect other state-changing operations.
3. Verify passwords with an appropriate `PasswordEncoder`; rate-limit and monitor failed logins.
4. Never build `Authentication` from client-asserted usernames/roles.
5. Write `SecurityContext` via the chosen `ServerSecurityContextRepository`, failing closed if saving fails.
6. Ensure `WebSessionServerSecurityContextRepository` rotates the ID on save; never disable this mechanism to "keep cookies stable".
7. Verify the old ID no longer grants the newly logged-in user's permissions.
8. Ensure session cookies are configured with `Secure` under HTTPS, `HttpOnly`, appropriate `SameSite`, restricted Domain/Path, and never logged.
9. Test logout/expiration/password change/permission revocation per policy.
10. Upgrade Spring Framework/Security/Session to supported patched releases.
11. For multi-instance deployments, test real session rotation on the shared store.
12. Never output session IDs in URLs, JSON, traces, error responses, or screenshots.

**Do not confuse mechanisms:**

| Mechanism | What It Protects Against | Example |
| --- | --- | --- |
| Session ID rotation | Mitigates pre/post-login session fixation | S0 → S1 |
| CSRF token | Mitigates forged cross-site requests abusing auto-sent cookies/credentials | `_csrf` in `POST /login` |
| TLS + Secure cookie | Mitigates eavesdropping IDs in transit | HTTPS |
| HttpOnly cookie | Restricts JavaScript from reading cookies directly | `Set-Cookie HttpOnly` |
| SameSite | Mitigates certain cross-site cookie-sending scenarios | Lax/Strict per domain rules |
| XSS defense | Reduces ability for malicious scripts to hijack sessions and actions | Escaping, CSP, no unsafe inline |
| Authorization | Decides user permissions on URLs/resources | `hasRole`, owner/tenant check |
| Session invalidation | Terminates session on logout/timeout | `WebSession.invalidate()` / logout handler |

## 14. Self-Check Questions

1. Why does successful `Authentication` in `POST /login` not yet prove a subsequent `GET /api/me` will still see the user?
2. What roles do `http.securityContextRepository(repo)` and `form.securityContextRepository(repo)` play?
3. Why does `WebSessionServerSecurityContextRepository` rotate the ID when saving `SecurityContext`?
4. How does session fixation differ from post-login session hijacking?
5. If there is no `S0` cookie before login, is an `S0` ID required for login to succeed?
6. Why should `NoOpServerSecurityContextRepository` not be used for websites using session-persisted form login?
7. Why is a single curl POST with username/password usually insufficient when default CSRF is enabled?
8. How must requests with cookies `S0` and `S1` differ in permissions after login?
9. Why does a `MockWebSession` test not replace integration tests across real cookies and session stores?
10. Should you manually call `changeSessionId()` an extra time right after the standard repo already saved?
11. When using a Redis session store across multiple nodes, what must be tested regarding the old ID?
12. What does CVE-2026-41839 show about why library versions still matter even when session ID rotation is enabled?

**Suggested answers:** (1) context still needs to be saved/loaded and the client must send the cookie; (2) loading on subsequent requests and saving on login; (3) severs ties with a pre-auth ID that might already be known; (4) fixation targets an ID known before login, whereas hijacking can occur if the new ID leaks afterwards; (5) no, the server can create a session when needed; (6) NoOp does not persist context across requests; (7) `POST /login` is CSRF-protected; (8) `S1` works, while `S0` must not inherit permissions; (9) unit tests do not exercise cookies/proxies/multi-node behavior; (10) unnecessary if the repo already rotates the ID; (11) old ID is invalid, new ID loads cleanly on every node; (12) protection also depends on Spring Framework/Session Store patches.

## 15. Reference Documentation

- Spring Security Javadoc — `WebSessionServerSecurityContextRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
- Spring Security Javadoc — `ServerHttpSecurity.FormLoginSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security Javadoc — `ServerHttpSecurity.securityContextRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Framework — `WebSession.changeSessionId()`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Session — WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Security Advisory CVE-2026-41839: https://spring.io/security/cve-2026-41839/
- Spring Boot 3.5 System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html

**Conclusion:** In Spring Security Reactive, secure form login requires **successful authentication → saving `SecurityContext` into `WebSession` → rotating the session ID → client using the new cookie → subsequent requests reloading the context**. Use `WebSessionServerSecurityContextRepository` and configure it consistently on both `FormLoginSpec` and `ServerHttpSecurity` to avoid save/load mismatches. Keep CSRF enabled, protect cookies, verify the old ID is unusable, and always apply Spring Framework patches, especially in light of disclosed session fixation vulnerabilities.
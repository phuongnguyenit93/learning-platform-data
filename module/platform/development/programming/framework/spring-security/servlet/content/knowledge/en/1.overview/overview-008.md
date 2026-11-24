# Foundations, Reading Roadmap, and Observing a Protected Request in Spring Security Servlet

Spring Security in a Servlet application protects HTTP requests **before they enter a controller**. When learning a Spring MVC project, the first thing to do is identify the request path, where identity is authenticated, and where access decisions are made. This lesson builds the mental model, outlines the order for reading configuration, and demonstrates how to observe a public request, a login-required request, and an access-denied request.

After this lesson, you will be able to:
- Distinguish **authentication** (verifying identity) from **authorization** (checking permissions).
- Explain the roles of Servlet Filters, `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`, and `SecurityContext`.
- Read a URL protection configuration from `requestMatchers` to `anyRequest`, and connect it to the corresponding controller.
- Send HTTP requests with and without credentials, compare 200, 401, and 403 outcomes, and trace logs to find the root cause.

## 1. HTTP and Servlet Foundations to Know First

An HTTP request consists of a **method** (GET, POST...), **path**, **headers**, and sometimes a **body**. The server returns a **status**, headers, and body. Identity information can travel via the `Authorization` header, a login session cookie, or another mechanism. Path and method are two independent dimensions: GET and POST on the same URL do not necessarily share the same policy.

In the Servlet stack, the container (for example, Tomcat) receives the request, passes it through the Servlet Filter chain, and only then reaches Spring MVC's `DispatcherServlet` and controllers. Spring Security hooks into the **filter chain**: thus a request can receive 401 or 403 **before the controller method runs**. HTTP-layer protection can coexist with method-level permission checks; this lesson focuses on the HTTP path.

Distinguishing key concepts:

| Concept | Question to Answer | Example |
| --- | --- | --- |
| Authentication | Who is the caller? Is the proof of identity valid? | Verifying username/password with HTTP Basic. |
| Authorization | Does the current identity have permission for this action? | Only users with `ROLE_ADMIN` may access `/api/admin`. |
| Principal | Identity representation of the caller after authentication | Username `reader`. |
| Authority/Role | Permission attached to the identity | `ROLE_READER`, `ROLE_ADMIN`. |
| SecurityContext | Holds the `Authentication` object for current security processing | Controller can read the principal if the request is authenticated. |
| Session/Cookie | Mechanism for keeping state across requests when configured | Browser resends a session cookie; the cookie itself is not a permission. |
| CSRF | Risk of a browser being tricked into sending requests on behalf of a logged-in user | For state-changing methods, CSRF protection can reject requests missing a token. |

**HTTP does not automatically remember users across requests.** If the application uses sessions, cookies help the server identify the session; if using Basic, the client normally resends the `Authorization` header on each request. Do not infer an application is completely stateless merely because it uses Basic: session state also depends on `SessionCreationPolicy` configuration and related components.

Status codes to interpret in context:

- **200 OK**: the request reached the handler and succeeded; this is not proof that the endpoint has no protection.
- **401 Unauthorized**: required login credentials are missing or failed authentication. With HTTP Basic, a `WWW-Authenticate` header usually prompts the client for credentials.
- **403 Forbidden**: the request was denied access. Commonly because the user is authenticated but lacks permission; it can also be caused by CSRF, so read logs and configuration before concluding.
- **302 Found**: a redirect-based login mechanism may send the user to a login page, depending on configuration; do not assume every unauthenticated request returns 401.
- **404/405**: after passing the filters, the URL or method matched no handler. Distinguish this from security errors.

## 2. Component Map of a Protected Request

When integrating Spring Security into a Servlet application, the container calls `DelegatingFilterProxy`, which forwards to a Spring bean named `springSecurityFilterChain` (typically `FilterChainProxy`). `FilterChainProxy` selects the **first SecurityFilterChain whose matcher matches** the request. That chain consists of security filters matching the configuration; do not assume every project has the exact same filter count or fixed order.

~~~text
HTTP client
   |
   v
Servlet container (Tomcat...)
   |
   v
DelegatingFilterProxy -> FilterChainProxy
   |
   v
Select SecurityFilterChain matching request
   |
   +--> Create/load SecurityContext per configuration
   +--> Read credentials and authenticate if a matching filter exists
   +--> Determine caller (authenticated or anonymous)
   +--> Check authorization policy
                |
                +--> Allowed -> DispatcherServlet -> controller -> response
                |
                +--> Blocked -> entry point/denied handler -> 401/403/... 
~~~

Links in the chain to recognize when reading logs or source code:

1. **`SecurityFilterChain`** is the set of filters applied to a group of requests; an application can declare multiple chains, with matcher order deciding which chain is selected.
2. **`SecurityContextHolderFilter`** helps bring `SecurityContext` into the request processing scope; how the context is saved/persisted depends on the repository and configuration.
3. **Authentication filter** depends on the mechanism: HTTP Basic typically has `BasicAuthenticationFilter`; form login or bearer tokens use other components. Filters do not automatically understand every credential type.
4. **`AuthenticationManager` and `AuthenticationProvider`** coordinate/verify credentials. `UserDetailsService` is commonly used to load user data during username/password authentication; it is not the URL permission-granting layer.
5. **`AnonymousAuthenticationFilter`** can place an anonymous authentication representation into the context; that does not turn an unauthenticated guest into an authenticated user.
6. **`AuthorizationFilter`** enforces policies declared via `authorizeHttpRequests`. `ExceptionTranslationFilter` can translate authentication/access errors into responses via an entry point or access-denied handler. Specifically, an authentication filter like `BasicAuthenticationFilter` can also directly trigger the entry point on invalid credentials.

**Separate three questions when observing:** which chain was selected? Who is the current `Authentication`? Which authorization rule allowed or denied the request? Answering all three explains the status code.

## 3. Roadmap for Reading a Servlet Security Project

Read from the **HTTP boundary inward**, rather than starting by randomly opening a user or role class.

| Order | Where to Read | What to Extract |
| --- | --- | --- |
| 1 | Dependencies and app configuration | Is Spring Web/Spring Security Servlet present? Is it using Basic, form login, session, JWT resource server, or a combination? |
| 2 | `SecurityFilterChain` beans, `@Order`, `securityMatcher` | How many chains exist? Which chain does a specific request match? |
| 3 | `authorizeHttpRequests`, `requestMatchers`, `anyRequest` | Is this method/path public, login-required, or does it need a specific authority? |
| 4 | Authentication filters, `AuthenticationProvider`, `UserDetailsService`, password encoder | Where do credentials come from and how are they verified? |
| 5 | Session, `SecurityContextRepository`, CSRF, exception handling | In what scope does identity persist? Why is a request blocked or redirected? |
| 6 | `@RequestMapping`/`@GetMapping`, method security if any, logs, and tests | Which handler does a valid request enter, and are there additional permission checks? |

How to read a specific rule: find the **exact matcher**, check **rule order**, identify the **chain containing the rule**, and only then open the controller. `permitAll()` means the URL policy permits access, **not that the entire filter chain is bypassed**. `authenticated()` requires an authenticated identity; `hasRole("ADMIN")` requires the `ROLE_ADMIN` authority (Spring Security adds the `ROLE_` prefix by default convention), whereas `hasAuthority("REPORT_READ")` checks that exact authority string.

Study deeply in order: HTTP/Servlet Filter → chain selection → authentication & SecurityContext → authorization → 401/403/entry point → session/CSRF → method security and testing. JWT/OAuth2 can be studied after mastering this flow: they change how credentials are authenticated, yet you still must explain which chain is selected and which permissions are checked.

## 4. Runnable Example: Three Endpoints, One User

Create a **Java 17+**, **Spring Boot 3.x** application with **Spring Web** and **Spring Security** dependencies (Gradle or Maven both work). Inside the source root, place the exact file `src/main/java/example/security/SecurityLessonApplication.java` with the following content. The additional classes are package-private, residing in the same Java file so the example is self-contained at the source level.

~~~java
package example.security;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityLessonApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("demo-pass"))
                .roles("READER")
                .build();
        return new InMemoryUserDetailsManager(reader);
    }
}

@RestController
class ExampleController {
    @GetMapping("/health")
    String health() {
        return "OK";
    }

    @GetMapping("/api/notes")
    String notes(Principal principal) {
        return "Private notes for " + principal.getName();
    }

    @GetMapping("/api/admin")
    String admin() {
        return "Admin only";
    }
}
~~~

**Reading the configuration before running:**

- `/health` is allowed even without credentials; requests still pass through the security chain.
- `/api/admin` requires role ADMIN, i.e., authority `ROLE_ADMIN`. The sample user only has `ROLE_READER`, so logging in with valid credentials still lacks sufficient permission.
- Other URLs, including `/api/notes`, require an authenticated user.
- `httpBasic(...)` enables HTTP Basic; no form login is configured, so unauthenticated requests in the example will use a Basic challenge rather than a login page.
- `InMemoryUserDetailsManager` provides the sample user; `BCryptPasswordEncoder` hashes the password stored in memory. The `reader/demo-pass` credentials are only for local experimentation.
- The example does not explicitly disable CSRF. Because only GET is used, no CSRF token is needed; when expanding to POST/PUT/DELETE, examine CSRF policy separately.

Start using the project's wrapper (in the directory containing `build.gradle` or `build.gradle.kts`):

~~~bash
./gradlew bootRun
~~~

On Windows you can run `gradlew.bat bootRun`. If using Maven, run with the wrapper `./mvnw spring-boot:run` (Windows: `mvnw.cmd spring-boot:run`). Standalone `javac` is insufficient because the example needs Spring libraries and a classpath from the build tool.

In another terminal, send the following requests. `curl -i` displays both status and response headers; `-u` builds the HTTP Basic header:

~~~bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/notes
curl -i -u reader:wrong http://localhost:8080/api/notes
curl -i -u reader:demo-pass http://localhost:8080/api/notes
curl -i -u reader:demo-pass http://localhost:8080/api/admin
~~~

Results to compare (headers depend on version and environment, so only core status/body are asserted):

| Request | Expected Result | Explanation |
| --- | --- | --- |
| GET `/health`, no credentials | **200**, body `OK` | `permitAll()` permits access. |
| GET `/api/notes`, no credentials | **401**, typically with `WWW-Authenticate: Basic ...` | No valid identity to satisfy `authenticated()`. |
| GET `/api/notes`, wrong password | **401** | HTTP Basic receives credentials but authentication fails. |
| GET `/api/notes`, `reader/demo-pass` | **200**, body `Private notes for reader` | Authentication succeeds and controller reads `Principal`. |
| GET `/api/admin`, `reader/demo-pass` | **403** | Authenticated, but missing `ROLE_ADMIN`. |

The two 401 cases can reach the entry point via different branches (no credentials vs. invalid Basic credentials). Therefore, identical status codes **do not mean** the exact same path was taken through every filter.

## 5. Observing a Request from Logs to Controller

### Step 1: Enable Bounded Security Logging in a Learning Environment

Add to `src/main/resources/application.properties`:

~~~properties
logging.level.org.springframework.security=TRACE
~~~

Restart the application and send each `curl` command individually. Depending on the version, logs can reveal the request being secured, chains/filters being invoked, authentication or authorization outcomes, and the exception handling branch. **Do not rely on fixed log strings**: message names and filter lists vary by version/configuration. Only enable TRACE for experimentation, as logs are verbose and may contain sensitive request details.

### Step 2: Trace Along Three Axes

For each request, record:

1. **Incoming request:** method, path, presence or absence of an `Authorization` header or relevant cookie.
2. **Security chain & identity:** which chain the request matched; which filter processed credentials; before/after authentication, what `Authentication` and authorities are.
3. **Authorization & response:** which rule was applied; whether the request reached the controller or stopped at a filter; what produced the status/redirect/challenge.

For example, with `GET /api/notes` and valid credentials: the container invokes the security chain → the Basic filter verifies the password via the provider/user store → context contains identity `reader` and `ROLE_READER` → rule `authenticated()` succeeds → controller receives `Principal` and returns `Private notes for reader`. With the same credentials but `GET /api/admin`, authentication still succeeds; the divergence occurs at the `hasRole("ADMIN")` rule. This is the core difference between **being logged in** and **being allowed to act**.

For a request without credentials, anonymous authentication may appear in the context. **Anonymous authentication is not synonymous with a logged-in user.** With wrong credentials, the authentication filter may trigger the HTTP Basic entry point immediately; do not assume a wrong-password request ran all the way to the controller.

### Step 3: Use Breakpoints When Logs Are Not Enough

When debugging a real Servlet project, you can set breakpoints at locations matching your configuration:

- `FilterChainProxy`: check which chain matches method/path.
- The active authentication filter, e.g., `BasicAuthenticationFilter`: verify how credentials are read and the success/failure branch.
- `AuthorizationFilter` or the configured authorization manager: find the rule and authorities leading to the decision.
- Controller: verify whether the request actually reached the handler; inspect `Principal` or `SecurityContextHolder.getContext().getAuthentication()` if you need to observe identity.

Do not expect breakpoints in **unconfigured filters** (such as the Bearer filter in a Basic example) to hit. With asynchronous processing or separate threads, `SecurityContext` is not automatically propagated to every thread; inspect the application's actual propagation mechanism.

### Step 4: Analyze the Response Before Changing Configuration

A quick diagnostic workflow:

| Symptom | Check First |
| --- | --- |
| 401 when calling a login-required endpoint | Were credentials sent? Did the authentication filter run? Did the provider accept them? Is `WWW-Authenticate` present? |
| 403 with valid credentials | What authorities does `Authentication` hold? Does `hasRole` expect the `ROLE_` prefix? Is it a CSRF denial? |
| 302 to login page | Is there a `formLogin`/redirecting entry point? Did the client send a session cookie? |
| 404/405 | After clearing security, do controller mappings match path and method? |
| Public endpoint still blocked | Does the request match the right chain/`permitAll` rule? Is there a higher-priority matcher ahead of it or CSRF? |

**Do not fix issues by broadly adding `permitAll` just to make 401/403 disappear.** First determine whether the cause is authentication, authorization, CSRF, or route mismatch; then fix the responsible layer.

## 6. Common Confusions to Avoid

1. **Confusing 401 with 403.** 401 leans toward missing/invalid authentication; 403 leans toward permission denial or another defense mechanism such as CSRF. In form-login apps, an unauthenticated request may even be redirected with 302.
2. **Confusing rules with chains.** `securityMatcher` decides which chain applies, whereas `requestMatchers` in `authorizeHttpRequests` decides access permissions **within the selected chain**. When multiple chains exist, inspect priority order before reading rules.
3. **Placing broad matchers before specific matchers.** Read rules in order: a catch-all rule can prevent subsequent rules from being evaluated. The `anyRequest()` rule normally goes last.
4. **Misusing roles/authorities.** `roles("READER")` creates `ROLE_READER`; `hasRole("READER")` checks that authority, whereas `hasAuthority("READER")` checks the distinct string `READER`.
5. **Assuming `permitAll` bypasses Spring Security.** Public endpoints can still run through security filters. `web.ignoring` is a different matter and should not be used casually.
6. **Assuming Basic always implies stateless.** The `Authorization` header is sent on each request, but session/SecurityContext creation and storage policy is a separate configuration; observe `Set-Cookie` and session rules before concluding.
7. **Disabling CSRF to resolve 403 without investigating.** For browsers using cookies/sessions, CSRF means something different than for clients sending standalone tokens. GET alone is not a sufficient test for POST/PUT/DELETE.
8. **Assuming all errors come from controllers.** Security filters can return status codes before MVC; conversely, a request can pass security and then hit 404/405 inside MVC.
9. **Treating logs as absolute truth.** TRACE aids path tracing, but final conclusions require cross-checking configuration, identity, and actual HTTP responses.

## 7. Observation Exercise and Self-Check Criteria

Perform this short exercise in order to ensure you understand the request flow rather than merely memorizing commands:

1. Call `/api/notes` while unauthenticated; explain why the controller does not return `Private notes ...`.
2. Call again with `reader/demo-pass`; explain why the same URL switches from 401 to 200, and where the controller obtains the username.
3. Call `/api/admin` as that user; explain why **successful authentication** still returns 403. Identify the held authority and the required authority.
4. Temporarily change the `/health` rule from `permitAll()` to `authenticated()` in a test environment, restart, and predict the status before/after adding credentials. Note the change occurred in **authorization**, without mistaking it for a controller change.
5. Enable TRACE and fill out the three-axis table *chain → authentication → authorization → response* for each request. Record only what is actually observed; if logs do not show enough, verify further with breakpoints or tests.

Being able to answer these questions independently builds a solid foundation for the next lesson:

- Which requests get routed to which `SecurityFilterChain`, and how can you tell?
- In which filter are credentials read? Which component verifies them? What does `Authentication` hold afterward?
- At which step do `authenticated()`, `hasRole()`, and `permitAll()` differ?
- Why can 401, 403, 302, and 404 appear in different scenarios?
- If switching from Basic to form login or bearer tokens, which part of the flow changes and which parts must still be checked?

**Mental thread to keep:** identify the **request** → select the **filter chain** → establish **identity** → evaluate **access permissions** → observe **HTTP response/controller**. When these five steps are clear, deeper topics like sessions, CSRF, method security, or OAuth2 fit naturally into the same model rather than becoming disconnected configurations.

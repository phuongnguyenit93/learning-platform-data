# permitAll vs Bypassing the Filter Chain with ignoring

In Spring Security for Servlet applications, two configuration snippets that look like they both "allow loading public content" have very different security meanings:

- **`requestMatchers(...).permitAll()`**: the request **still passes through the Spring Security filter chain**, while the *HTTP authorization* step permits access without requiring the caller to have a role, authority, or login.
- **`web.ignoring().requestMatchers(...)`**: requests matching the matcher **bypass the security filters managed by Spring Security** in `FilterChainProxy`. This is not an ALLOW decision from `AuthorizationFilter`, but rather **not passing through that security mechanism at all**.

For most public pages and static resources such as CSS, JavaScript, images, and favicons, the **recommended default choice is `permitAll`**. Spring Security 6.x documentation recommends this because public resources still benefit from HTTP security headers and other protective filters; in Spring Security 6, `permitAll` also avoids fetching `Authentication` from the session to make the grant decision.

This article explains accurately how requests are processed, which capabilities remain or are lost, how to configure Spring Boot 3 / Spring Security 6, edge cases to consider, how to test, and mistakes that easily cause vulnerabilities.

## 1. Context: which layers does a request pass through?

A Spring MVC/Servlet application typically has these layers:

~~~text
Client
  |
  v
Servlet container filters (may be registered by multiple libraries or the application)
  |
  v
DelegatingFilterProxy
  |
  v
Spring Security's FilterChainProxy
  |
  +-- Request matches a SecurityFilterChain:
  |      SecurityContext / authentication filters / CSRF /
  |      exception handling / security headers / AuthorizationFilter ...
  |         |
  |         +-- requestMatchers(...).permitAll() -> ALLOW at authorization step
  |         |   (remaining Spring Security filters can still run)
  |         v
  |      Controller / static resource handler
  |
  +-- Request belongs to web.ignoring():
         does not execute Spring Security's security filters for that request
         |
         v
         Controller / static resource handler
~~~

`FilterChainProxy` is where multiple `SecurityFilterChain`s are coordinated. Which filters are actually present depends on the application configuration: form login, HTTP Basic, JWT resource server, or custom filters produce different pipelines. `permitAll` **does not guarantee every filter is present**, yet it **does not actively remove the entire chain**.

`ignoring` also **does not mean** the request bypasses all middleware in the system: Servlet filters outside Spring Security, the container, gateways, reverse proxies, the web application, and the browser itself can still process or reject it. The accurate conclusion is that **Spring Security does not execute its filter chain on ignored URLs**.

Neither operation **creates a URL or file**. If `/assets/app.css` does not exist, whether `permitAll` or `ignoring` is used, the application's static resource layer can still return **404**.

## 2. Comparing every attribute, not just "can it be accessed?"

| Criterion | `permitAll` in `authorizeHttpRequests` | `web.ignoring()` |
| --- | --- | --- |
| Does the request pass through `FilterChainProxy`? | Yes; selects the matching chain and runs the chain's security filters. | Ignored URLs are not processed by the security filter chain. |
| Is `AuthorizationFilter` applied? | Yes in chains using `authorizeHttpRequests`; the public rule returns ALLOW. | Spring Security's `AuthorizationFilter` does not run for that URL. |
| Is login required at **this HTTP rule**? | No. | There is no Spring Security HTTP rule to evaluate. |
| Spring Security response headers? | Applied if the chain configures the corresponding header writer. | Spring Security **does not add** headers through the bypassed chain. |
| CSRF filter? | Can still apply to state-changing requests when CSRF is enabled. | Not applied by Spring Security to the ignored URL. |
| Authentication filters? | Still part of the pipeline; may process supplied credentials. | Not processed by Spring Security on this URL. |
| Spring Security-integrated CORS? | Can apply if `http.cors(...)` is configured. | Spring Security's CORS filter in the chain does not run. |
| Custom logging/audit/exception-handling filters in security chain? | Can run depending on position and configuration. | Do not run if they only exist inside the Spring Security chain. |
| `SecurityContext` provided by Spring Security? | Can be populated per pipeline. | Do not rely on Spring Security populating it for this request. |
| Scope of impact | Authorization rule inside the **selected chain**. | Bypasses Spring Security across the **ignored URL region**, not just one rule. |
| Intended use | Public endpoints, login pages, static assets, intentionally public health endpoints. | Specially evaluated technical exceptions, not the normal way to open public endpoints. |

Note on the security headers column: **there is no guarantee every header is always present**. For example, Spring Security provides common headers by default such as `X-Content-Type-Options: nosniff`, `X-Frame-Options`, cache-control, and HSTS **over HTTPS** (subject to conditions/config). The `Content-Security-Policy` (**CSP**) header is **not added by default** and must be configured if the application needs it. Headers can also be set or overridden by another server/gateway. Saying "`ignoring` loses security headers" here means **losing Spring Security's header-writing mechanism**, not guaranteeing the network response has zero headers.

## 3. Recommended configuration example: permitting static resources with permitAll

Suppose an e-commerce application has:

- `/assets/**` and `/favicon.ico` files loaded without login.
- `GET /public/**` as public content; `POST /public/contact` for visitors to submit a form.
- `/api/admin/**` requiring `ROLE_ADMIN`.
- All remaining endpoints requiring login.

In Spring Boot 3.x / Spring Security 6.x, you can create the following configuration class. File **`WebSecurityConfig.java`**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/assets/**", "/favicon.ico")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/public/**")
                .permitAll()
            .requestMatchers(HttpMethod.POST, "/public/contact")
                .permitAll()
            .requestMatchers("/api/admin/**")
                .hasRole("ADMIN")
            .anyRequest()
                .authenticated()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is **configuration code requiring Spring Boot/Spring Security libraries and a valid account mechanism**, not a standalone Java program runnable with plain JDK. Examples use Spring Security 6 configuration; exact APIs must match the version the application actually runs.

In this example:

1. `GET /assets/site.css` matches the first rule and **passes the authorization step**, while still entering the security chain where enabled header writers and other filters reside.
2. `GET /api/admin/users` matches the admin rule: `hasRole("ADMIN")` requires `ROLE_ADMIN` by default. Placing admin routes **after** asset rules is not dangerous as long as the asset matcher truly matches only assets.
3. `POST /public/contact` requires no login at the HTTP authorization step. **However, default CSRF remains enabled**; a browser POST request using cookies/sessions must usually send a valid CSRF token. If missing, the result can be **403** despite `permitAll`.
4. `GET /api/orders/42` requires login, yet does not check ownership of Order 42. That is a resource-level policy that must be enforced in the service/repository layer.
5. `anyRequest().authenticated()` applies to remaining requests in the chain. For stricter **deny by default**, use `anyRequest().denyAll()` and declare each permitted endpoint explicitly.

Using `permitAll` **does not turn** those URLs into "unsecured." It merely states that **no HTTP-layer authorization condition is required for the matching URL**. If the application has `@PreAuthorize`, business policies, gateway rate limiting, validation, or other checks, those conditions do not vanish automatically.

### Using Spring Boot's PathRequest when appropriate

Spring Boot offers a helper for static resource paths at default locations. If the application uses Boot's standard static structure, you can use it inside `authorizeHttpRequests`:

~~~java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;

// Place inside authorizeHttpRequests(auth -> auth ...):
.requestMatchers(PathRequest.toStaticResources().atCommonLocations())
    .permitAll()
~~~

This is a **DSL snippet**, not a standalone file. `PathRequest` belongs to **Spring Boot**, not Spring Security core APIs. Custom paths like `/assets/**` may **not belong** to those common locations; if the application uses custom assets, dedicated matchers are needed. Always verify the actual URLs served by MVC and permit only resources intended to be public.

## 4. Configuring ignoring: what does it actually do?

Bypassing the security filter chain is typically configured with `WebSecurityCustomizer`. This representation is shown to **recognize and evaluate legacy configurations or technical exceptions**, **not as a default recommended pattern** for static resources.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;

@Configuration
public class IgnoredPathsConfig {

    @Bean
    WebSecurityCustomizer webSecurityCustomizer() {
        return web -> web.ignoring().requestMatchers("/assets/**");
    }
}
~~~

When a request matches `/assets/**`, `FilterChainProxy` **does not run Spring security filters** for that request. It does not skip only `AuthorizationFilter`; components such as the security header writer, authentication filters, CSRF filter, security context handling, and custom filters inside the chain are also not executed via the normal Spring Security flow.

**Hidden risk:** `app.css` can load successfully under both configurations, so tests checking only status 200 fail to notice that public resources lost security headers or security/telemetry filters. Worse, later on the development team might accidentally put a business API under `/assets/**` and silently bypass all of Spring Security.

If an organization is forced to use `ignoring` due to measured architectural/performance requirements, the ignored region must be **narrow, static, contain no personal data, perform no state-changing actions, and never become an arbitrary API area**. You must also clearly identify which other layer supplies the necessary headers and safeguards. Never use `ignoring("/**")`, `ignoring("/api/**")`, or ignore an entire region just to quickly work around a 401/403 error.

A better alternative when you only want to skip **one specific mechanism** is configuring **that mechanism itself**, such as adjusting the CSRF matcher or authentication mechanism for the exact endpoint, instead of removing the entire security chain.

## 5. Most important point: permitAll does not turn off other filters

Try three requests:

~~~text
GET /assets/site.css       (anonymous)
POST /public/contact       (anonymous, missing CSRF token)
GET /public/info           (carrying an invalid Bearer token)
~~~

With an active `SecurityFilterChain`, `permitAll` only answers the question "**Does `AuthorizationFilter` require an identity/permission?**":

- **Public GET asset:** usually allowed to proceed, and the response gets processed by configured security header writers. Nonexistent assets can still return 404.
- **Public POST missing CSRF:** can be rejected by `CsrfFilter` with 403 if the request falls under CSRF scope and lacks a valid token. Permitting authorization does not disable CSRF protection.
- **Public GET with invalid Bearer token:** if a resource server authentication filter is enabled and processes `Authorization: Bearer ...`, the request may be rejected **before** `permitAll` gets a chance to allow it. "Public" means credentials are not required, **not that bad credentials are always ignored**.

The fix for that situation is not mechanically switching to `ignoring`, because that loses other protections. Inspect the actual filter chain and design authentication handling for public URLs when needed.

### CSRF: selective disabling is completely different from ignoring

Suppose a webhook uses an independent digital signature, does not use browser cookies, and needs no CSRF token. You can **skip only CSRF for that endpoint** while keeping all other security filters. **Illustrative** configuration example:

~~~java
http
    .csrf(csrf -> csrf
        .ignoringRequestMatchers("/webhooks/partner/**"))
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/webhooks/partner/**")
            .permitAll()
        .anyRequest().authenticated()
    );
~~~

`csrf.ignoringRequestMatchers(...)` is **not** `web.ignoring()`: it only adjusts the scope of **CSRF protection**, while the request is still processed by the Spring Security filter chain. The webhook must still verify signatures, timestamps, nonces/replay protection, key sources, and quotas in business logic; **`permitAll` is not webhook security**. Never apply CSRF-skipping examples to endpoints using cookies/Basic auth in browsers without risk analysis.

### CORS differs from authorization

CORS is a browser rule applied to cross-origin requests. If the app configures `http.cors(...)`, the CORS filter is integrated into the Spring Security chain. With `ignoring`, the CORS integration inside Spring Security is also skipped; MVC or gateway CORS might still exist, yet that is a separate mechanism. Do not use `ignoring` to solve 401/403 on OPTIONS preflights; configure CORS and matchers properly for the actual path.

## 6. Security headers: the main reason Spring Security recommends permitAll

Spring Security supports writing headers such as:

| Header or policy | Practical significance | Notes |
| --- | --- | --- |
| `X-Content-Type-Options: nosniff` | Reduces risk of browsers MIME-sniffing improperly. | Included in Spring Security Servlet's default headers. |
| `X-Frame-Options` | Controls ability to embed pages in frames. | Defaults to `DENY` in many standard configs. |
| `Strict-Transport-Security` | Instructs browsers to use HTTPS in the future. | Only added under appropriate HTTPS/configuration conditions. |
| `Cache-Control` / `Pragma` / `Expires` | By default prevents accidental caching of sensitive content. | Can be adjusted for static assets needing long caching. |
| `Content-Security-Policy` | Restricts script/style sources and browser behaviors. | **Not enabled by default**; application must configure it. |
| Custom headers | Internal policies applied across responses. | Present only if configured by the app/gateway. |

With `permitAll`, the security header writer in the chain can still attach configured headers to public responses. With `ignoring`, Spring Security does not run that header writer. Even a public JavaScript or HTML file can benefit from `nosniff`, configured CSP, or other protective headers.

**Performance and caching:** fingerprinted static assets like `app.8fa12.js` should generally be cached. Spring Security's default `Cache-Control: no-store` may be unsuitable; the solution is **configuring cache headers specifically for static resources** via Spring MVC/response or an appropriate CDN mechanism, not automatically bypassing the security filter chain. Spring Security can respect cache headers already set by the application; test actual headers rather than assuming.

On platforms with a reverse proxy/CDN adding security headers externally, those headers may still exist even if the app ignores the request. Nonetheless, the decision to bypass the security filter chain must be weighed against **CSRF, Authentication, SecurityContext, CORS, and custom filters**, not headers alone.

## 7. Performance: does permitAll force session access?

**No, not in Spring Security 6.x.** With the modern `authorizeHttpRequests` mechanism, `permitAll` (and `denyAll`) can decide **without retrieving `Authentication` from the session** at the request authorization step. That is one reason Spring Security documentation recommends `permitAll` instead of ignoring static assets.

However, saying "`permitAll` does not read Authentication for authorization" **does not mean** the entire security chain never reads the session or does any work: an authentication filter, security context repository, custom filter, or another mechanism may still process the request depending on configuration.

When optimizing static resources:

1. Start with `permitAll`, narrow URL/method rules, and measure latency/CPU/cacheability.
2. Check whether high cost actually comes from a custom authentication filter querying the database on every request.
3. If the issue lies in a custom filter, adjust **that filter's** matcher/logic or use an appropriate separate chain structure instead of dropping all of Spring Security.
4. If assets are served by a CDN outside the application, consider routing separation at infrastructure level; analyze header and access responsibilities at the CDN.
5. Only consider `ignoring` when backed by strong performance evidence, full awareness of all lost protections, periodic tests, and formal risk acceptance.

Not every static-looking request is small or non-sensitive. Uploaded files, invoice documents, private avatars, CSV exports, and object storage proxies can look like "files" while containing data needing permissions; **never ignore just because a URL has a file extension**.

## 8. Distinguishing ignoring, permitAll, securityMatcher, and no matching chain

These four concepts are often lumped together:

| Case | Impact | What to understand |
| --- | --- | --- |
| `authorizeHttpRequests(...permitAll())` | Permits at **one HTTP authorization rule**. | The chain's filters can still run. |
| `web.ignoring().requestMatchers(...)` | Request bypasses the **Spring Security filter chain**. | Not merely "no login needed." |
| `http.securityMatcher("/api/**")` | Limits which requests **one `SecurityFilterChain`** protects. | Requests outside `/api/**` may belong to another chain. |
| No `SecurityFilterChain` matches | Request sits **outside Spring Security protection**. | Usually a vulnerability when a fallback chain is missing. |

Decision diagram:

~~~text
FilterChainProxy
  |
  +-- URL belongs to global ignoring?
  |       YES -> skips Spring Security filters
  |
  +-- select first SecurityFilterChain matching request
          |
          +-- if no chain -> not protected by Spring Security
          |
          +-- if chain exists -> run chain's filters
                              |
                              +-- AuthorizationFilter reads rules
                                    |
                                    +-- permitAll -> passes authorization
                                    +-- authenticated/hasRole/... -> check condition
                                    +-- denyAll -> blocks authorization
~~~

When multiple chains exist, `@Order` decides chain evaluation order; the first chain matching the request wins. Inside that chain, `authorizeHttpRequests` uses the first matching `requestMatchers` rule. **Putting `anyRequest().permitAll()` at the start or `web.ignoring("/**")` can widen public exposure unintentionally.**

### Multi-chain configuration case

Example separating API and website:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/assets/**", "/login").permitAll()
        .anyRequest().authenticated());
    return http.build();
}
~~~

This is a **configuration fragment placed in a `@Configuration` class**, needing imports for `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, and an appropriate login mechanism. It cannot run standalone with JDK. The website chain has no `securityMatcher` so it acts as the fallback; `/assets/**` is permitted in the web chain and **still passes through the web chain's security filters**. If `/assets/**` were put in `web.ignoring`, neither Spring Security chain would handle that area anymore.

**A dangerous bug** is configuring an API chain matching only `/api/**` with no fallback for `/admin/**`; `/admin/users` requests can then fall outside Spring Security. That is a **missing-chain** vulnerability, not `permitAll`, though the "unprotected by security filters" consequence is essentially the same.

## 9. What should be used for common URL groups?

| URL group | Recommendation | Why |
| --- | --- | --- |
| Public `/css/**`, `/js/**`, `/images/**`, `/favicon.ico` | **`permitAll`** | Public while retaining security headers/filter chain. |
| `/`, about pages, public docs | **`permitAll`** | May contain HTML/scripts where security headers are especially valuable. |
| Public `GET /products/**` | **`permitAll`** | Authorization requires no login, while services still control public data and other filters still run. |
| Form login GET/POST | Allow access per `formLogin` configuration and matching URLs | Login still needs authentication and CSRF filters. |
| `POST /public/contact` | **`permitAll` + CSRF/rate limit/validation** per model | Not needing login does not mean dropping all protections. |
| `POST /webhooks/partner` | Authorization can be `permitAll`; design dedicated signature auth | Skip CSRF conditionally only if appropriate; **do not ignore the whole chain**. |
| Controlled public `GET /actuator/health` | `permitAll` on the **exact endpoint** if approved | Never expose all of `/actuator/**` by default, especially env, heapdump, config. |
| Private downloads, invoices, reports | **Require authorization + resource checks** | Static-looking paths do not mean public. |
| JavaScript/HTML served by external CDN | Policy at CDN/gateway | Not an in-app `WebSecurityCustomizer` case if requests never hit the app. |

Never use extension matchers like `/**/*.pdf` to permit by default: a PDF may be a private contract; a CSV may contain customer data. Design from **data classification and actions**, not from URL suffixes.

## 10. A standalone Java 17+ program to observe both mechanisms

The following program is an **intentional simulation**, not Spring Security code. It illustrates three main ideas: `permitAll` lets the request pass at the **authorization step** while filters still run; `ignoring` sends the request straight to the application **without security filters**; and public POST requests can be blocked by CSRF when protection remains enabled.

The model sets `securityHeaders=true` for requests traversing the chain to represent a Spring Security configuration **with header writers enabled**. In a real app, whether headers appear depends on configuration, HTTPS, MVC, gateway, and specific header writers. `forwarded=true` here simply means "passed to handler," **not a promise of HTTP 200**.

Save the program with the exact name **`PermitAllVsIgnoringDemo.java`**:

~~~java
public class PermitAllVsIgnoringDemo {
    record Request(String method, String path,
                   boolean authenticated, boolean csrfValid) {}

    record Outcome(boolean filtersRan, boolean forwarded,
                   boolean securityHeaders, String result) {}

    static Outcome handle(Request request, boolean ignoreAssets) {
        boolean asset = request.path().startsWith("/assets/");
        if (ignoreAssets && asset) {
            return new Outcome(false, true, false, "BYPASS");
        }

        boolean stateChanging = !request.method().equals("GET")
                && !request.method().equals("HEAD")
                && !request.method().equals("OPTIONS")
                && !request.method().equals("TRACE");

        if (stateChanging && !request.csrfValid()) {
            return new Outcome(true, false, true, "CSRF_DENIED");
        }

        boolean publicPath = asset || request.path().startsWith("/public/");
        if (publicPath || request.authenticated()) {
            return new Outcome(true, true, true, "ALLOW");
        }
        return new Outcome(true, false, true, "AUTH_REQUIRED");
    }

    static String describe(Outcome outcome) {
        return "filters=" + outcome.filtersRan()
                + ", forwarded=" + outcome.forwarded()
                + ", headers=" + outcome.securityHeaders()
                + ", result=" + outcome.result();
    }

    public static void main(String[] args) {
        Request staticGet = new Request("GET", "/assets/app.css", false, false);
        Request privateGet = new Request("GET", "/api/profile", false, false);
        Request publicPost = new Request("POST", "/public/contact", false, false);
        Request postWithCsrf = new Request("POST", "/public/contact", false, true);

        System.out.println("Asset permitAll: "
                + describe(handle(staticGet, false)));
        System.out.println("Asset ignoring: "
                + describe(handle(staticGet, true)));
        System.out.println("Private anonymous: "
                + describe(handle(privateGet, false)));
        System.out.println("Public POST without CSRF: "
                + describe(handle(publicPost, false)));
        System.out.println("Public POST with CSRF: "
                + describe(handle(postWithCsrf, false)));
    }
}
~~~

Compile/run with JDK 17 or higher:

~~~bash
javac --release 17 PermitAllVsIgnoringDemo.java
java PermitAllVsIgnoringDemo
~~~

Exact output:

~~~text
Asset permitAll: filters=true, forwarded=true, headers=true, result=ALLOW
Asset ignoring: filters=false, forwarded=true, headers=false, result=BYPASS
Private anonymous: filters=true, forwarded=false, headers=true, result=AUTH_REQUIRED
Public POST without CSRF: filters=true, forwarded=false, headers=true, result=CSRF_DENIED
Public POST with CSRF: filters=true, forwarded=true, headers=true, result=ALLOW
~~~

**Reading the output:** both asset scenarios reach the handler, yet the mechanisms differ completely. With `permitAll`, the request traverses the chain and can receive headers; with `ignoring`, the request bypasses the chain. Anonymous private requests are blocked; `POST /public/contact` missing CSRF is denied **before** the public authorization check completes. This is a model for learning logic, not a substitute for integration tests with Spring MVC and real filter configs.

## 11. Real-world testing: do not inspect only status code 200

To distinguish the two configurations, test **the entire pipeline** rather than only whether an endpoint opens. With Spring Boot and `spring-security-test`, `MockMvc` can run through the Spring Security filter chain when tests are configured properly.

For `permitAll`, verify at minimum:

- Anonymous requests to public assets **do not require login** at `AuthorizationFilter`, and the default headers you enabled are actually present.
- Private endpoints remain denied to anonymous callers (401 with HTTP Basic, or redirect per mechanism), avoiding overly broad `permitAll` rules.
- Public POSTs with CSRF enabled do not succeed automatically when missing a CSRF token.
- Requests carrying invalid credentials are handled by authentication filters as configured, rather than assuming "public" skips all authentication.
- When renaming or changing resource paths, matchers stay accurate so new assets are not accidentally blocked and private resources are not exposed.

Illustrative assertions **in a Spring Boot integration test** (requires `MockMvc`, static imports, and real endpoints/resources):

~~~java
// Default security headers configuration is enabled:
mvc.perform(get("/assets/app.css"))
    .andExpect(header().string("X-Content-Type-Options", "nosniff"));

// POST has permitAll, yet CSRF protection still applies:
mvc.perform(post("/public/contact"))
    .andExpect(status().isForbidden());

// With a CSRF token, the request can reach the controller:
mvc.perform(post("/public/contact").with(csrf()));
// After this step, outcome depends on controller and validation.
~~~

If the asset does not exist, `get("/assets/app.css")` may return 404, yet the header assertion remains useful to observe that the request passed through the header writer. To avoid confusion, in real tests create an actual asset file and assert body/content type as well, not headers alone.

When testing `ignoring`, **do not automatically assert "zero security headers exist"**; a reverse proxy or another Servlet filter might attach headers. Verify that **the Spring Security filter chain was not invoked** using appropriate integration tests/observations, and check which headers are actually guaranteed by the application/gateway.

### Recommended test matrix

| Scenario | `permitAll` with valid default chain | `ignoring` |
| --- | --- | --- |
| Public GET asset | Passes authorization and still runs security filters | Skips security filters |
| GET asset with bad credentials | May be rejected by authentication filter | Spring Security's authentication filter does not run |
| Anonymous private GET | Blocked by login-required rule | Outside ignored scope if narrowly configured |
| Public POST, missing CSRF | Can return 403 due to `CsrfFilter` | If URL is ignored, not checked by Spring CSRF |
| HTTP response headers | Security header writer can add configured headers | Spring Security's header writer does not run |
| Public URL later made private | Update `permitAll` rule accordingly | If still ignored, Spring Security remains bypassed |
| Nonexistent endpoint | May return 404 after passing security | Can also return 404 at handler |

All expectations for specific 401/403/redirect/headers must rest on actual configuration, not merely on the names `permitAll` or `ignoring`.

## 12. Common mistakes and right fixes

1. **"CSS is public so ignore it for speed."** → Try `requestMatchers("/css/**").permitAll()` first; use a profiler to prove an exception is needed, as Spring Security 6 does not fetch Authentication for `permitAll` at the authorization step.
2. **"PermitAll stops Spring Security from running."** → False: it only relaxes the authorization rule. Security headers, CSRF, authentication, and other filters can still run.
3. **"Public POST returned 403, so switch to ignoring."** → Check whether CSRF requires a token; adjust CSRF rules per authentication model if suitable, never bypass the whole chain.
4. **"Use ignoring on /api/** to fix CORS errors."** → This is a severe vulnerability. Configure CORS and preflight narrowly while still checking permissions on real requests.
5. **"Static resources do not need security headers."** → Even public HTML/JS/CSS benefit from `nosniff` and configured headers. Do not drop header writers without a replacement.
6. **"A CDN already sends headers so ignore everything."** → A CDN does not replace application authentication/CSRF/security context/custom filters; audit all responsibilities.
7. **"`securityMatcher` and ignoring are the same."** → `securityMatcher` selects a chain; ignoring excludes requests from security filters. Matching zero chains must also be recognized as a vulnerability.
8. **"`permitAll` means no business data safety needed."** → Public endpoints still need validation, rate limiting, abuse protection, and must never leak private data via IDs.
9. **"Testing 200 OK alone is enough."** → Test headers, CSRF, authentication, private routes, match boundaries, and filters that must run.
10. **"Fix role/permission issues by skipping the chain."** → If 403 occurs due to wrong authority mapping, fix authentication/authorization at the source; do not use ignoring as a shortcut.
11. **"CSP is enabled by default."** → Spring Security does not add CSP automatically; declare an appropriate policy and verify responses if CSP is desired.
12. **"If no chain matches, denyAll surely applies."** → False. `anyRequest().denyAll()` is effective only within a selected chain. If no chain matches, Spring Security does not protect that request.

## 13. Checklist before making a path public

Before exposing `/assets/**`, `/public/**`, or `/health` without login, answer:

1. **Is it genuinely public?** Is all content in that URL area—including new files and other HTTP methods—intended for anonymous users?
2. **Does the path match accurately?** Check MVC mappings, URL prefixes, `securityMatcher`, `requestMatchers`, and rule ordering.
3. **Which protections are still needed?** Security headers, CSRF, CORS, authentication when tokens are present, rate limiting, request validation, auditing, and domain policies.
4. **Can it be exposed with `permitAll`?** In most cases **yes**; prefer this over bypassing security filters.
5. **If there is an ignoring exception, why?** There must be a clear, verifiable reason, minimal scope, compensating controls, and tests preventing unintended expansion.
6. **When permissions change, who tests it?** A public endpoint that later becomes private must be removed from `permitAll` or ignored regions and covered by anonymous tests.
7. **What headers are in the response?** Verify on both HTTP and HTTPS matching the environment; do not assume CSP, cache-control, or HSTS always have the same values.
8. **What about paths matching no chain?** Define a tested fallback chain or coverage policy to avoid areas unprotected by Spring Security.

**Conclusion:** `permitAll` and `ignoring` are **not equivalent**. `permitAll` permits access at the **authorization step of a still-active chain**. `ignoring` makes requests **bypass Spring Security's security filters**. For static resources and public endpoints, **`permitAll` is the choice recommended by Spring Security 6.x**; use ignoring only as an exception whose full impact on headers, authentication, CSRF, and other safeguards has been evaluated.

### References

- [Spring Security 6.5 – Authorize HttpServletRequests: Favor permitAll over ignoring](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 – Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 – Java Configuration, RequestMatcher and filter chains](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 – CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)

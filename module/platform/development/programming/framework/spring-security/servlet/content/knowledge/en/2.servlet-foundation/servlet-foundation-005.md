# Context Path, Servlet Path, and Paths Used When Matching Requests

In a **Spring Security application running on Servlet**, a URL can contain several path segments. Confusing the browser-facing path, the path inside the application, the servlet-mapped path, and the pattern used by Spring Security can cause authorization rules not to match as expected. The goal of this lesson is to read those components accurately and choose the right `RequestMatcher`.

## 1. Breaking Down an HTTP Request

Consider an application deployed under context path `/app`, with `DispatcherServlet` mapped to prefix `/mvc/*`. The browser sends:

~~~http
GET /app/mvc/admin/reports?page=2 HTTP/1.1
Host: example.test
~~~

Assuming the servlet container uses the prefix mapping above, `HttpServletRequest` provides:

| Component | Value | Meaning |
| --- | --- | --- |
| `getContextPath()` | `/app` | Root path of the web application in the servlet container. |
| `getServletPath()` | `/mvc` | Path portion matching the servlet mapping `/mvc/*`. |
| `getPathInfo()` | `/admin/reports` | Remainder after the servlet path for prefix mappings. |
| `getRequestURI()` | `/app/mvc/admin/reports` | Request URI, including context path and path segments, without the query string. |
| `getQueryString()` | `page=2` | Data after `?`, not a path component matched by common path matchers. |

A helpful visualization for the **prefix-mapping case** is:

~~~text
URL:           https://example.test/app/mvc/admin/reports?page=2
                              └─┬┘└┬┘└──────┬─────┘
                         context  servlet   pathInfo
                         /app     /mvc      /admin/reports

requestURI                = /app/mvc/admin/reports
servletPath + pathInfo    = /mvc/admin/reports
path inside servlet       = /admin/reports
queryString               = page=2
~~~

This illustrates **one type of servlet mapping**, not unconditional string concatenation valid for every request. The Servlet specification allows exact mapping, prefix mapping, extension mapping, and the default servlet; how the container returns `servletPath` and `pathInfo` depends on the actual mapping. `getPathInfo()` is typically `null` for the default mapping `/` or an exact mapping. Never write security code assuming `pathInfo` is always non-`null`.

**Context path is not the same as servlet path.** `server.servlet.context-path=/app` (in Spring Boot) sets a prefix for the entire web application. `spring.mvc.servlet.path=/mvc` is a separate mapping option for Spring MVC's `DispatcherServlet`. They address two different layers; you must also check servlet mapping compatibility and path matching strategy in your running Spring Boot/Spring MVC version.

Common configuration example:

~~~properties
server.servlet.context-path=/app
spring.mvc.servlet.path=/mvc
~~~

With the default `DispatcherServlet` mapped to `/` instead of `/mvc/*`, the same application endpoint `/admin/reports` under context `/app` has URL `/app/admin/reports`. This common case typically returns `servletPath=/admin/reports` and `pathInfo=null`. Therefore, looking only at the URL or controller name is not enough to infer every `HttpServletRequest` property.

## 2. What Does Java See and Why Not Slice URLs Manually?

The standalone Java 17 illustration below concatenates **hypothetical values** from the prefix-mapping example; it is no substitute for reading the actual `HttpServletRequest`:

~~~java
public class PathPartsDemo {
    public static void main(String[] args) {
        String contextPath = "/app";
        String servletPath = "/mvc";
        String pathInfo = "/admin/reports";

        String requestUri = contextPath + servletPath + pathInfo;

        System.out.println("requestURI = " + requestUri);
        System.out.println("appPath = " + servletPath + pathInfo);
        System.out.println("pathInfo = " + pathInfo);
    }
}
~~~

Save the file as `PathPartsDemo.java`, then run:

~~~bash
javac PathPartsDemo.java
java PathPartsDemo
~~~

Exact stdout:

~~~text
requestURI = /app/mvc/admin/reports
appPath = /mvc/admin/reports
pathInfo = /admin/reports
~~~

In a real application, read the components from the request to see how the servlet container interpreted them. Do not use `substring` or `startsWith` on raw URIs to build access checks: there are also URL encoding, path normalization, `;` parameters, multiple servlet mappings, and proxy configurations.

Example diagnostic filter (a snippet belonging to a **Spring Boot/Spring MVC application with Jakarta Servlet dependencies**, not a standalone Java program):

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class PathDiagnosticsFilter extends OncePerRequestFilter {
    private static final Logger log =
            LoggerFactory.getLogger(PathDiagnosticsFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        log.debug("contextPath={}, servletPath={}, pathInfo={}, requestURI={}",
                request.getContextPath(),
                request.getServletPath(),
                request.getPathInfo(),
                request.getRequestURI());

        chain.doFilter(request, response);
    }
}
~~~

Enable diagnostic logs only in appropriate environments, and never log tokens, cookies, or sensitive information. For proxied requests, compare application logs with the actual path forwarded by the proxy.

## 3. Where Does Spring Security Match Paths?

There are three distinct decisions in the processing flow:

1. The **Servlet container** receives the request and decides which application/servlet handles it; context path and servlet mapping participate here.
2. **Spring Security's `FilterChainProxy`** iterates through the list of `SecurityFilterChain`s in order and selects the **first chain** whose `RequestMatcher` matches. Inside `HttpSecurity` configuration, `securityMatcher(...)` scopes a single chain.
3. **Authorization rules within the selected chain** evaluate `requestMatchers(...)` in declaration order and apply the first matching rule, such as `permitAll()`, `hasRole("ADMIN")`, or `authenticated()`.

Two APIs have similar names but operate at **different decision levels**:

| API | Question answered | Consequence when not matched |
| --- | --- | --- |
| `http.securityMatcher(...)` | Does the request enter **this SecurityFilterChain**? | Tries the next chain; if no chain matches, the request is not protected by the filters of those chains. |
| `authorizeHttpRequests(...requestMatchers(...))` | Inside the selected chain, **which authorization rule** applies? | Evaluates the next rule, typically down to `anyRequest()`. |

Example with the default `DispatcherServlet` mapped to `/` and an application deployed at `/app`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

The snippet above is configuration for a Spring Security project; it requires a Spring Boot application and the corresponding dependencies. Path-wise, a request to `/app/api/admin/users` is under context `/app`, yet the configured matchers still use `/api/**` and `/api/admin/**` in this case. **Do not manually prepend `/app` to patterns just because the public URL has that context path.** For Spring Security's standard path matchers, the context path is normally excluded from matching scope; specifics depend on the `RequestMatcher` type.

**Point to watch:** The configuration above only defines a chain for `/api/**`. If the project also needs to protect `/login`, `/actuator`, or other endpoints, there must be an appropriate chain/strategy for them. A single chain with `securityMatcher("/api/**")` does not automatically protect URLs outside `/api/**`. And `permitAll()` still sends the request through the chain's filters; it differs from bypassing Spring Security filters completely.

## 4. Why Does Servlet Path Make Matchers Easy to Misunderstand?

Suppose the application maps `DispatcherServlet` to `/mvc/*`, while a controller has `@GetMapping("/admin/reports")`. A user visits `/app/mvc/admin/reports`. There are at least three valid strings with different meanings:

- Full URI in the servlet request: `/app/mvc/admin/reports`.
- Path inside the application excluding context path: `/mvc/admin/reports`.
- Relative path inside the prefix-mapped servlet: `/admin/reports`.

**Different `RequestMatcher`s do not necessarily interpret pattern strings the same way.** There is no universal rule that every `requestMatchers("/admin/**")` call compares against a single string manually sliced by the application.

In many **Spring Security 6.x + Spring MVC** setups, `MvcRequestMatcher` uses `HandlerMappingIntrospector` to follow Spring MVC matching semantics. When `DispatcherServlet` has its own servlet path, set the servlet path explicitly on the MVC matcher:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class MvcSecurityConfig {
    @Bean
    SecurityFilterChain mvcChain(
            HttpSecurity http,
            HandlerMappingIntrospector introspector) throws Exception {

        MvcRequestMatcher.Builder mvc =
                new MvcRequestMatcher.Builder(introspector)
                        .servletPath("/mvc");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(mvc.pattern("/public/**")).permitAll()
                .requestMatchers(mvc.pattern("/admin/**")).hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

In this example, `/mvc` identifies the servlet path, while `/admin/**` is the MVC path pattern inside that servlet. That is an explicit way to avoid confusing `/mvc/admin/**` with `/admin/**`. `MvcRequestMatcher` is an API from the Spring Security 6.x generation; if using a newer Spring Security version, check which matchers are supported and used by default in that version.

For configurations using `PathPatternRequestMatcher` (introduced in newer Spring Security versions), the corresponding mindset is specifying the servlet's base path and matching the remainder, for example via `PathPatternRequestMatcher.withDefaults().basePath("/mvc")`, provided the path matching strategy is compatible. Conversely, `AntPathRequestMatcher` in older setups matches against `servletPath + pathInfo` (ignoring the query string), so the corresponding pattern might need `/mvc/admin/**`. Never copy patterns verbatim from one matcher type to another without testing.

The table below summarizes **hypothetical examples** when the context path is `/app` and the servlet prefix is `/mvc/*`:

| Incoming URL | `servletPath` | `pathInfo` | MVC Matcher with `servletPath("/mvc")` + `pattern("/admin/**")` |
| --- | --- | --- | --- |
| `/app/mvc/admin/reports` | `/mvc` | `/admin/reports` | Matches. |
| `/app/mvc/public/help` | `/mvc` | `/public/help` | Does not match the admin rule. |
| `/app/mvc/administrator` | `/mvc` | `/administrator` | Does not match the `/admin/**` segment. |
| `/app/mvc/admin/reports?page=2` | `/mvc` | `/admin/reports` | Still matches: the query does not alter the path. |

Values in the table are derived from that specific prefix mapping and pattern; when using the default servlet, another controller servlet, or a different `RequestMatcher`, verify the actual request fields.

## 5. Rule Order, HTTP Methods, and Multiple Filter Chains

Within a single chain, place specific rules before broad rules. Example:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll());
~~~

This snippet requires `import org.springframework.http.HttpMethod;` and lives inside the application's `HttpSecurity` configuration. It illustrates that `GET /api/public/news` can be permitted, whereas `POST /api/public/news` does not match the GET rule and falls through to the authentication requirement of `/api/**`. An overly broad `anyRequest().permitAll()` or an `/api/**` rule placed ahead of `/api/admin/**` can prevent specific rules from ever being evaluated.

When there are multiple `SecurityFilterChain` beans, chain order determines the first matching chain. Design example: an `@Order(1)` chain applies only to `/api/**`; an `@Order(2)` chain acts as a fallback for everything else. Inspect both the chain-selection matcher and the authorization matchers inside the chain. If you set `securityMatcher("/api/**")` and then declare `requestMatchers("/admin/**")`, the `/admin/**` rule cannot protect an endpoint located completely outside that chain's scope.

Distinguish three easily confused cases: **no security chain selected**, **chain selected but specific rule not matched**, and **rule matched but denied due to unauthenticated/unauthorized status**. These cases lead to different fixes.

## 6. Verifying Matchers with Real Requests, Logs, and Tests

When an endpoint meant to be "public" returns `401/403`, or an endpoint expected to require authorization lets requests through, a useful diagnostic procedure is:

1. Record the **method**, the URL/path sent by the client, the path actually forwarded by any reverse proxy, the servlet mapping, and the values of `getContextPath()`, `getServletPath()`, `getPathInfo()`, and `getRequestURI()`.
2. Identify whether you are using `MvcRequestMatcher`, `PathPatternRequestMatcher`, Ant-style matchers, or custom matchers; do not look solely at pattern strings.
3. Check the order of `SecurityFilterChain`s, especially `securityMatcher` scope; only then inspect the order of `requestMatchers` inside `authorizeHttpRequests`.
4. Check HTTP method, query string, URL encoding, and trailing slashes. Rules can differ by version and matching strategy.
5. Create test requests for at least one path that **must match**, one path that **must not match**, and one path with a **similar name but different segment** such as `/admin/reports` vs `/administrator`. Test with an unauthenticated user as well as users with and without the role.

Logs can be enabled in a test environment:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access.intercept=TRACE
~~~

Logs reveal which filter chain was selected and many access decisions, but they do not replace test assertions; log messages vary by version. Turn off or lower the log level once the issue is found.

Example `MockMvc` test in a project with Spring Security filters integrated. When simulating a context path and servlet prefix, configure the request consistently with the real mapping:

~~~java
mockMvc.perform(get("/app/mvc/admin/reports")
        .contextPath("/app")
        .servletPath("/mvc")
        .pathInfo("/admin/reports"))
    .andExpect(status().isUnauthorized());
~~~

This is a **snippet inside a Spring Boot test class** (requiring `MockMvc`, static imports of `get`/`status`, an existing endpoint, and HTTP Basic or an entry point returning `401`). The `401` result holds only under those preconditions for an unauthenticated request; an app using form login may redirect with `302`. Test further with a principal having role `ADMIN` and another role to verify the rule rather than inferring security from a single status code. If multiple servlets/filter chains exist, verify that the simulated request maps the same way as a real container request.

### When running behind a reverse proxy

Suppose a client calls `https://host.example/gateway/app/mvc/admin/reports`, but the proxy strips `/gateway` before forwarding to the application. The application may then receive only `/app/mvc/admin/reports`. Security patterns must be designed for the request information the application actually sees, not blindly for the external URL. Handling `Forwarded`, `X-Forwarded-*`, or `ForwardedHeaderFilter` can also affect path properties; check the actual configuration before adjusting matchers.

Similarly, never use `startsWith("/admin")` in place of a normalized matcher: that check can falsely accept `/administrator`, and manual handling of `%2F` decoding or `;` parameters can introduce discrepancies between the security layer and MVC routing. Use the same path-matching strategy as the framework, configure anomalous URL handling consistently, and test edge cases.

## 7. Self-Check Exercises

**Scenario A.** A web application has context `/portal` and servlet mapping `/ui/*`. A request `GET /portal/ui/admin/dashboard?tab=stats` enters this servlet. Identify the path parts.

**Answer:** `contextPath=/portal`; `servletPath=/ui`; `pathInfo=/admin/dashboard`; `requestURI=/portal/ui/admin/dashboard`; `queryString=tab=stats`. If using an MVC matcher with `servletPath("/ui")` and `pattern("/admin/**")`, this URL matches the admin rule.

**Scenario B.** A chain has `securityMatcher("/api/**")`, inside which `requestMatchers("/admin/**").hasRole("ADMIN")` is declared. Endpoint `/admin/metrics` lies outside `/api/**`. Does this admin rule protect the endpoint?

**Answer:** No. That chain is not selected for that endpoint. Design the chain scope or fallback chain properly instead of just adding an authorization rule inside an inapplicable chain.

**Scenario C.** On the default servlet `/`, an application has context `/shop`. The public URL is `/shop/api/orders/7`, yet the Security rule uses `/shop/api/**`. Why might the rule fail to match?

**Answer:** Because the context path `/shop` is normally excluded from the path matched by standard matchers. The candidate pattern for the in-app path is `/api/**`. Verify the matcher type and servlet mapping before changing configuration.

## 8. Checklist When Building Path Rules

- Verify the **context path**, **servlet mapping**, **actual `servletPath`/`pathInfo`**, and post-proxy URL.
- Verify the **`RequestMatcher` type**, Spring Security version, and how the engine handles servlet prefixes.
- Distinguish **chain selection** via `securityMatcher` from **authorization** via `requestMatchers`.
- Place specific rules before broad rules, provide an explicit fallback, and test endpoints outside the chain's scope.
- Never prepend the context path mechanically to patterns; never slice raw URL strings to make access decisions.
- Write tests for HTTP methods, prefixes, look-alike routes, unauthenticated users, users lacking roles, and proxy setups if present.

**Key takeaway:** The path seen by the client, the paths parsed by the servlet container, and the path evaluated by each `RequestMatcher` are related but not identical concepts. Knowing which layer matches what helps you write accurate, verifiable Spring Security rules.
# Showing or Hiding UI Features Does Not Replace Server Authorization

> **Scope:** Spring Security on the Servlet stack (Spring MVC, Spring Boot 3.x, Spring Security 6.x, and Java 17+). This lesson explains the relationship between **showing/hiding UI elements** and **enforcing mandatory access control on the server**. Examples use Thymeleaf, Servlet `SecurityFilterChain`, method security, per-resource permission checks, and MockMvc. Readers must clearly distinguish **UX (user interface)** from the **security boundary**.

## 1. The Most Important Rule

**Hiding a button, menu, link, or HTML element does not make the server-side endpoint secure.** The UI can improve user experience by showing only actions a user is expected to perform, but real authorization must be **verified on the backend for every request that reads or mutates data**.

Suppose an application has an admin report export feature:

- Regular accounts do not see the **Export all reports** button.
- A user can type the URL manually, edit HTML/CSS in Developer Tools, send an HTTP request using a script, curl, or Postman, or call the API directly.
- If the backend does not enforce authorization on `POST /admin/export`, the request can still succeed even though the button was never rendered.

The difference lies in where enforcement happens:

| Action | Purpose | Counts as a Security Control? |
| --- | --- | --- |
| Hiding with CSS `display: none` or `hidden` attribute | Keep an element out of visual sight. | **No**. Both DOM and API remain accessible. |
| Disabling a button with `disabled` | Prevent clicks in normal UI usage. | **No**. Other HTTP clients ignore button state. |
| Omitting an element via `th:if` or `sec:authorize` | Improve UX by avoiding irrelevant options. | **Insufficient**. Only controls the current HTML response. |
| Conditionally rendering React/Vue UI via `role` or `canExport` | UX, keeping UI consistent with server. | **No**. Client state can be tampered with. |
| `authorizeHttpRequests(...)` in Spring Security | Protects requests by URL/method and authorities. | **Yes**, at the HTTP entry point; matchers must be designed properly. |
| `@PreAuthorize` on a service | Protects business operations before method execution. | **Yes**, when method security is enabled and calls go through a Spring proxy/interceptor. |
| Ownership/tenant checks on data | Verifies the user has rights to the exact record/resource. | **Yes**, if enforced on the server across all code paths. |

**Practical rule:** the UI may ask "should this button appear?", but the server **must independently answer** "is this request allowed to execute?" based on the request's actual identity, authorities, and target resource.

## 2. Why Hiding UI Does Not Stop Attacks

### 2.1 The Client Is an Untrusted Environment

The browser is under the user's control. Any condition evaluated only on the client can be bypassed or modified:

~~~javascript
// For user experience only, NOT access control.
const canExport = currentUser.roles.includes("ADMIN");

if (canExport) {
  document.querySelector("#export-button").hidden = false;
}
~~~

An unauthorized user can bypass JavaScript and send requests straight to the API. Browser extensions, automated scripts, or other devices may not even use this UI. Thus, `canExport` in JavaScript is only a **display hint**, not a privilege the server may trust.

An illustrative direct HTTP request:

~~~http
POST /admin/export HTTP/1.1
Host: app.example.org
Cookie: JSESSIONID=example-session-cookie
Content-Type: application/x-www-form-urlencoded

format=csv
~~~

The endpoint must check **authentication** (who is calling), **authorization** (whether exporting is allowed), business rules, and CSRF (when ambient credentials like cookies are used). Never rely on whether the caller could see a button.

### 2.2 Hiding Is Different from Not Sending Data

There are two very different behaviors:

1. The server **still sends sensitive data** in HTML/JSON and hides it via CSS: the data has already reached the client and can be read in page source, DOM, or Network tools. That is a **data leak**, not merely bad UX.
2. The server checks permissions before querying or returning data and renders only permitted content: this is proper access control.

Never place passwords, tokens, other users' data, internal pricing, or admin reports into HTML/JSON for an unauthorized user hoping `display:none` will protect it. Permissions must be enforced **before returning sensitive content**.

### 2.3 It Is Not Just About "Admin" Buttons

Even ordinary resource-viewing features require **per-object** authorization. For example:

~~~text
GET /reports/11  -> alice's report
GET /reports/12  -> bob's report
~~~

Both `alice` and `bob` hold the `USER` role; therefore, `hasRole("USER")` is **not enough** to decide whether `alice` may read report 12. If the server only authenticates and lets users freely swap IDs in the URL, the application suffers from **Broken Object Level Authorization (BOLA/IDOR)**.

The right rule is: the user must hold the appropriate role/capability **and** be permitted to view that specific record (by owner, tenant, ACL, or policy). Never trust a client-supplied `ownerId`.

## 3. Three Layers of Responsibility in a Spring MVC Application

A clean design separates these layers:

~~~text
                         User experience
[Thymeleaf / JSP / SPA]
  - sec:authorize, th:if, canExport...
  - show/hide menus, status messages
                    |
                    v HTTP request
                         Server boundary
[Spring Security Servlet Filter Chain]
  - authentication: who is calling?
  - authorizeHttpRequests: which URL/method is allowed?
  - CSRF protection (when applicable)
                    |
                    v Controller
[Service / Method Security]
  - @PreAuthorize: which business operation is allowed?
  - policy by role, owner, tenant, state
                    |
                    v
[Repository / Data Access]
  - scope queries by account/tenant
  - prevent reading/modifying out-of-scope data
~~~

The UI layer **replaces none** of the server layers. In systems with multiple entry points (REST, MVC, jobs, message consumers), checks at the **service/business layer** are especially valuable because they do not depend on a single URL or controller. Still, URL authorization remains a valuable defense-in-depth layer; do not leave all endpoints open hoping every controller remembers to check.

## 4. Conditional Rendering with Thymeleaf and Spring Security

Thymeleaf offers the `thymeleaf-extras-springsecurity6` dialect, providing the `sec:authorize` attribute to conditionally render HTML based on Spring Security's `Authentication`.

### 4.1 Required Dependencies

In a Spring Boot 3.x Maven project using Spring MVC, add these dependencies under `<dependencies>` in `pom.xml`. This is a **configuration snippet**, not a complete POM:

~~~xml
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
        <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
    <dependency>
        <groupId>org.thymeleaf.extras</groupId>
        <artifactId>thymeleaf-extras-springsecurity6</artifactId>
    </dependency>
</dependencies>
~~~

When using Spring Boot dependency management/BOM, compatible versions are managed centrally. Do not manually pull Spring Security 5 artifacts into Boot 3/Security 6. Ensure the application produces a valid `Authentication` in the Spring Security context.

### 4.2 Thymeleaf Template

File `src/main/resources/templates/dashboard.html`:

~~~html
<!DOCTYPE html>
<html lang="en"
      xmlns:th="http://www.thymeleaf.org"
      xmlns:sec="http://www.thymeleaf.org/extras/spring-security">
<head>
    <meta charset="UTF-8">
    <title>Dashboard</title>
</head>
<body>
    <h1>Dashboard</h1>

    <p sec:authorize="isAnonymous()">
        Please sign in to view your reports.
    </p>

    <div sec:authorize="isAuthenticated()">
        <p>Signed in as:
            <strong sec:authentication="name">User</strong>
        </p>
        <a th:href="@{/reports/11}">Example: view report #11</a>
    </div>

    <section sec:authorize="hasRole('ADMIN')">
        <h2>Admin functions</h2>
        <form th:action="@{/admin/export}" method="post">
            <button type="submit">Export all reports</button>
        </form>
    </section>

    <p sec:authorize="!hasRole('ADMIN')">
        Admin report export is not available for this account.
    </p>
</body>
</html>
~~~

Explanation:

- `sec:authorize="hasRole('ADMIN')"` only renders the form when the current Spring Authentication holds authority `ROLE_ADMIN` under default conventions. **It does not protect `/admin/export` on its own**.
- `sec:authorize="isAuthenticated()"` displays the section for logged-in users. This **does not guarantee the user owns report 11**; the demo link above still requires a server-side ownership policy.
- `sec:authentication="name"` reads the name from Spring Security's Authentication rather than an arbitrary client value.
- With POST forms and `th:action`, Spring MVC/Thymeleaf integration with Spring Security's `RequestDataValueProcessor` typically injects a hidden CSRF input. **Inspect the rendered HTML** and ensure the CSRF token is submitted when CSRF is enabled; never disable CSRF globally because of a 403 error.
- Display expressions do not re-evaluate once HTML reaches the browser; permission changes mid-session require refreshing/reloading the UI or updating state. Even with stale UI, the server must enforce current permissions.
- This code illustrates display logic only. Which URLs exist and who may access them must be configured on the server.

**Do not confuse `sec:authorize` with `@PreAuthorize`**: the former decides whether to **render HTML**; the latter decides whether **a method invocation runs or is denied** when method security is active.

### 4.3 JSP and SPA Frontends

In legacy JSP projects, Spring Security taglibs similarly provide `<sec:authorize access="hasRole('ADMIN')">` (requiring the appropriate dependency/taglib). Example **JSP fragment**:

~~~jsp
<%@ taglib prefix="sec" uri="http://www.springframework.org/security/tags" %>

<sec:authorize access="hasRole('ADMIN')">
    <a href="/admin">Admin</a>
</sec:authorize>
~~~

Omitting the link **does not** protect `GET /admin`. Similarly, a React/Vue/Angular app may call a server-computed `GET /api/me/capabilities` endpoint to know which actions to display. JSON like `{"canExport":false}` is a **UX hint**; the export API must still enforce authorization using the principal/authorities/policy when the POST arrives.

## 5. Real Authorization with SecurityFilterChain

Below is a **Java 17+ configuration class running in a Spring Boot project** with the starters shown earlier. It demonstrates URL authentication/authorization with Spring Security 6 Servlet.

File `src/main/java/com/example/ui/SecurityConfig.java`:

~~~java
package com.example.ui;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error", "/css/**")
                    .permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Key takeaways:**

1. `authorizeHttpRequests` runs **on the server** via the Servlet Security Filter Chain, independent of whether a button was rendered.
2. `requestMatchers("/admin/**").hasRole("ADMIN")` requires `ROLE_ADMIN` for every HTTP request matching `/admin/**`. An unauthorized user sending a manual POST is still blocked.
3. `requestMatchers("/reports/**").authenticated()` only enforces login. It does **not** yet restrict users to their own reports; the ownership example in the next section solves that.
4. **Matcher order matters.** Narrower/stricter rules must appear before broader rules that could match the same URL.
5. `anyRequest().denyAll()` establishes a fail-closed default for undeclared endpoints; this is an intentional security choice. When adding new valid endpoints, add explicit matchers. Never use `anyRequest().permitAll()` just to make the UI "run easily".
6. `formLogin(...)` in the example uses Spring Security's default login page. In real apps, substitute your actual authentication mechanism (OIDC, SAML2, sessions, etc.) while **keeping server-side authorization intact**.
7. `@EnableMethodSecurity` activates processing for annotations like `@PreAuthorize`. You cannot simply annotate a method and assume it works without enabling method security.
8. Spring Security's default CSRF protection remains enabled. Cookie-backed POST requests require a CSRF token where applicable; **a 403 can come from a missing token or missing permission**, and you must distinguish them.

### Do hasRole and hasAuthority Differ?

In the default configuration, `hasRole("ADMIN")` checks for granted authority `ROLE_ADMIN`, whereas `hasAuthority("EXPORT_REPORTS")` checks for an authority named **literally** `EXPORT_REPORTS`. They are not interchangeable arbitrary strings. Choose a clear convention consistent with your user directory, IdP, and authority mapper.

For instance, a system might use a coarse role `ROLE_ADMIN` alongside a narrower permission `EXPORT_REPORTS`. Both the UI and server can query matching expressions for consistent UX, but **only the server** decides execution. Never treat all logged-in users as automatically allowed to export.

## 6. Minimal End-to-End Spring Boot Example

The snippets below form an illustrative structure for a Spring Boot 3.x application. It uses **in-memory demo accounts** and should not be deployed as-is to production. Place all classes in package `com.example.ui` so Spring Boot scans the beans.

### 6.1 Application Entry Point

File `src/main/java/com/example/ui/UiAuthorizationDemoApplication.java`:

~~~java
package com.example.ui;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UiAuthorizationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(UiAuthorizationDemoApplication.class, args);
    }
}
~~~

### 6.2 Demo Accounts for Testing Permissions

File `src/main/java/com/example/ui/DemoUsersConfig.java`:

~~~java
package com.example.ui;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUsersConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-user-password"))
                .roles("USER")
                .build(),
            User.withUsername("manager")
                .password(encoder.encode("demo-admin-password"))
                .roles("USER", "ADMIN")
                .build()
        );
    }
}
~~~

Account `alice` only has `ROLE_USER`; `manager` also has `ROLE_ADMIN`. Passwords in source code are strictly for **local testing** and are hashed when constructing users; never hardcode production passwords in source. Real applications integrate a user store/SSO and proper credential management.

### 6.3 Controller Rendering the Home Page

File `src/main/java/com/example/ui/DashboardController.java`:

~~~java
package com.example.ui;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class DashboardController {

    @GetMapping("/")
    public String dashboard() {
        return "dashboard";
    }
}
~~~

Spring MVC renders `templates/dashboard.html` from section 4 when the Thymeleaf starter is properly configured.

### 6.4 Admin Endpoint: Always Verify on the Server

File `src/main/java/com/example/ui/AdminController.java`:

~~~java
package com.example.ui;

import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AdminController {

    @PostMapping(value = "/admin/export",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    @PreAuthorize("hasRole('ADMIN')")
    public String export() {
        return "Export accepted";
    }
}
~~~

Here there are **two layers of defense** for the demo:

- `SecurityFilterChain` requires `ROLE_ADMIN` for every `/admin/**` request, including direct calls bypassing the UI.
- `@PreAuthorize("hasRole('ADMIN')")` protects the method invocation when Spring Method Security is enabled, reducing risk if future code paths call this method. For complex business logic, method security is usually placed on the service layer rather than only on the controller.
- The demo returns a short string instead of actually exporting data. When writing a real export, enforce the scope of data an admin may export, record proper audit logs, and avoid returning overly broad sensitive data.

**POST routes still need a CSRF token when using forms/sessions.** A user with `ROLE_ADMIN` can receive HTTP 403 if a POST lacks a CSRF token. That is a separate protection layer, not a wrong role.

## 7. Per-Resource Authorization: ROLE_USER Is Not Enough

### 7.1 Example of an IDOR/BOLA Vulnerability

An API is insecure if it only does this:

~~~java
@GetMapping("/reports/{id}")
public Report get(@PathVariable Long id) {
    return reportRepository.findById(id).orElseThrow();
}
~~~

The snippet above **illustrates an anti-pattern only** and will not compile standalone since `Report` and `reportRepository` are project components. If the `/reports/**` matcher only requires `authenticated`, `alice` can try `bob`'s ID. Having the UI display only `alice`'s reports **does not stop** a direct HTTP GET to `bob`'s ID.

You must enforce server-side **owner, tenant, ACL, or business policy** checks on the requested ID—for instance, placing the check in service/method security so it does not depend solely on the controller.

### 7.2 Illustrative Fail-Closed Ownership Policy

File `src/main/java/com/example/ui/ReportAccess.java`:

~~~java
package com.example.ui;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportAccess")
public class ReportAccess {

    // Local illustrative data; real apps use DB/ACL/tenant.
    private final Map<Long, String> owners =
            Map.of(11L, "alice", 12L, "bob");

    public boolean canRead(Authentication authentication, long reportId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        String owner = owners.get(reportId);
        if (owner == null) {
            return false;
        }

        boolean isAdmin = authentication.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

        return isAdmin || owner.equals(authentication.getName());
    }
}
~~~

Demo rules: report 11 belongs to `alice`, report 12 belongs to `bob`; admins can read either if the record exists. A nonexistent ID returns `false`, failing closed rather than granting access by default. Real systems must decide between returning 403 or 404 per policy and query a controlled repository; never use a mock `Map` in production.

**Important:** admin privilege is determined from `Authentication.getAuthorities()` established by Spring Security, **never** from a query parameter or request body field `isAdmin=true`. In multi-tenant systems, check both the user's tenant and the report's tenant; having the "same role" across two tenants does not grant cross-tenant access.

### 7.3 Service Applying @PreAuthorize

File `src/main/java/com/example/ui/ReportService.java`:

~~~java
package com.example.ui;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("@reportAccess.canRead(authentication, #p0)")
    public String readReport(long reportId) {
        return "Report " + reportId;
    }
}
~~~

`#p0` refers to the first method parameter in method-security SpEL, keeping the example independent of whether the compiler retains parameter names. `authentication` is the current Spring Authentication. When method security is active, Spring invokes the `reportAccess` bean to decide whether the user can view the report. The bean name is specified via `@Component("reportAccess")`.

This logic is **minimal to illustrate authorization**: in real applications, the service should load the resource from the data store, apply tenant/owner filters in the query, and avoid TOCTOU races if permissions or data can change between check and use. Repository queries constrained by `ownerId`/`tenantId` are preferable to fetching all records and filtering in the UI.

### 7.4 Controller Calling the Protected Service

File `src/main/java/com/example/ui/ReportController.java`:

~~~java
package com.example.ui;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping(value = "/reports/{id}",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String read(@PathVariable long id) {
        return reportService.readReport(id);
    }
}
~~~

Because `ReportController` calls a **Spring-managed service bean** wrapped by the method-security proxy/interceptor, `@PreAuthorize` on the service can deny the call before `readReport` executes.

**Self-invocation warning:** if a method inside the same service calls a `@PreAuthorize`-annotated method directly via `this.`, the call may bypass the proxy depending on the AOP mode. Never rely on annotations at unintercepted call sites; design clean service boundaries and test actual call paths. Never turn permission checks into a client-reported "already authorized" flag.

## 8. Testing Server-Side Authorization with MockMvc

Proper tests **send requests directly**, without depending on whether a button appears in a template. Spring Security Test lets you simulate principals, CSRF, and assert HTTP statuses.

Add test dependencies under `<dependencies>` in `pom.xml` in a project using Boot dependency management:

~~~xml
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
~~~

File `src/test/java/com/example/ui/AuthorizationIntegrationTest.java`:

~~~java
package com.example.ui;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void normalUserCannotCallHiddenAdminEndpoint() throws Exception {
        mvc.perform(post("/admin/export").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "manager", roles = {"USER", "ADMIN"})
    void adminCanExportWithCsrf() throws Exception {
        mvc.perform(post("/admin/export").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("Export accepted"));
    }

    @Test
    @WithMockUser(username = "manager", roles = {"USER", "ADMIN"})
    void missingCsrfBlocksEvenAdmin() throws Exception {
        mvc.perform(post("/admin/export"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCanReadOwnReport() throws Exception {
        mvc.perform(get("/reports/11"))
                .andExpect(status().isOk())
                .andExpect(content().string("Report 11"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void cannotReadAnotherUsersReport() throws Exception {
        mvc.perform(get("/reports/12"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "manager", roles = {"USER", "ADMIN"})
    void adminCanReadExistingReport() throws Exception {
        mvc.perform(get("/reports/12"))
                .andExpect(status().isOk())
                .andExpect(content().string("Report 12"));
    }
}
~~~

**Test explanation:**

- The USER POST test includes `csrf()` to eliminate a missing token as a factor, ensuring the 403 genuinely tests **admin authorization** rather than passing accidentally due to CSRF.
- The valid admin test sends a token so it reaches the controller and receives `Export accepted`.
- The admin-without-CSRF test demonstrates that CSRF and authorization are **two independent checks**.
- The test where `alice` cannot read `reports/12` proves the backend enforces ownership even when a user types the URL directly.
- `@WithMockUser` creates a simulated Spring Security Authentication for testing; it **does not verify** production IdP/SSO integration or policies backed by a real database. When using a production user store/tenant model, add integration tests against real mappings and data.

In a properly configured Maven project, run:

~~~bash
mvn test
~~~

These tests must be run in a project containing all classes and dependencies from the example. No fixed Maven stdout is provided because test counts, plugin versions, and modules vary. Expect all six tests to pass in a compatible sample setup; if unexpected 401/302/403 responses appear, inspect the security chain, CSRF, method security, and test principal.

## 9. HTTP Statuses: 401, 403, and Redirects Are Not the Same

When checking URLs server-side, distinguish:

- **Unauthenticated:** a request may receive **401 Unauthorized**, or a **302 redirect** to a login page if using form login. Depending on `AuthenticationEntryPoint`, never assume every endpoint returns 401.
- **Authenticated but insufficient permissions:** typically receives **403 Forbidden** from `AccessDeniedHandler`.
- **Missing or invalid CSRF token:** a cookie-backed POST/PUT/PATCH/DELETE request can receive **403** even when the user holds the right role.
- **Nonexistent resource or existence hidden:** the app may choose 404 by policy. Never let status codes or error messages reveal data the caller should not know.

If the frontend sees 403, **do not "fix" it by showing a button or disabling CSRF**. Inspect who the principal is, their actual authorities, which matcher/method was invoked, whether the CSRF token is valid, and what the per-resource permission policy returned.

## 10. Checks Required Beyond Hiding Menus

### 10.1 Distinguish Authentication, Authorization, and CSRF

A request can pass authentication yet fail authorization. A fully authorized request can still be blocked by CSRF; that is the right behavior when a browser attaches a session cookie automatically without proof of valid intent for a state-changing request.

Never make an app "work" by:
- Calling `http.csrf(csrf -> csrf.disable())` just to stop form POSTs from returning 403.
- Using `anyRequest().permitAll()` just so JavaScript stops getting blocked.
- Checking `role` only in React/Thymeleaf while omitting `authorizeHttpRequests` or business policies.
- Using GET for state-changing actions like delete/export with side effects to evade form CSRF.

CSRF protection does not replace authorization; authorization does not replace CSRF. Neither CORS nor `SameSite` cookies check a user's permission on a specific report.

### 10.2 Separate Menu Permissions from Data Permissions

A user may have permission to see the "Reports" menu while only being allowed to view reports in their own department or tenant. Data access may also depend on:

- User and report `tenantId`.
- Owner, team, organization, or project membership.
- Resource state (draft, locked, published).
- Granular permissions (VIEW_REPORT, EDIT_REPORT, EXPORT_REPORT).
- Sensitivity levels or separation-of-duties rules.

When computing "should the edit button appear?", the server can expose a boolean evaluated by **the same domain policy** that enforces the real action. Never let the client send `canEdit=true` back and trust it: the update request must re-evaluate the policy against the current principal and resource.

### 10.3 Entry Points Other Than MVC Controllers

A business operation may be invoked from a REST controller, GraphQL resolver, message consumer, scheduled job, or internal service. If permissions are checked only in an MVC controller, other paths can bypass them. Build an explicit **authorization service/policy** and enforce controls at the business boundary in addition to URL checks.

For background jobs lacking a user HTTP session, define a dedicated **service identity** and authorization mechanism; never spoof `ROLE_ADMIN` or share a single "super user" account across all tasks. Audit logs must record the real principal/service, action, and affected resource.

### 10.4 Avoid Leaking Data in Templates

Never render admin content and hide it only with CSS. Never send the entire reports JSON and filter it in JavaScript. Apply filtering and authorization before fetching and returning data. On pages with sensitive sections, build view models containing only permitted fields rather than exposing full domain entities to the view.

### 10.5 Do Not Tie Authorization to a UI Framework

Thymeleaf `sec:authorize`, JSP `sec:authorize`, and React conditional rendering are three different UX presentation mechanisms. None of them replaces server-side rules. If you migrate your UI from Thymeleaf to an SPA, **backend security policies must keep working** without duplicating permissions in JavaScript.

## 11. Pre-Deployment Security Checklist

1. **Every sensitive endpoint** has an explicit server-side rule (URL authorization and/or service authorization), including GET endpoints reading sensitive data.
2. **Object-level permissions** are enforced by owner/tenant/ACL, not just broad roles.
3. **Method security** is genuinely enabled and invoked through a proxy/interceptor; both HTTP entry points and service calls are tested.
4. **The UI** uses capability info strictly for UX, never hiding secrets inside DOM/JSON.
5. **Data** is queried and returned only when allowed by policy, with protections against enumeration/IDOR.
6. **POST/PUT/PATCH/DELETE** endpoints are properly protected against CSRF when using cookies/sessions; do not blindly mistake CSRF 403 for a role error.
7. **Least privilege:** never grant `ROLE_ADMIN` or `permitAll` just to make a screen function.
8. **Authentication from IdP/DB** maps to trusted authorities; never take unverified roles from client headers/query/body.
9. **Negative tests:** regular users posting directly to admin endpoints, tampering with URL IDs, cross-tenant access, direct API calls bypassing the UI, missing CSRF tokens, and logged-out users or revoked roles.
10. **Auditing and errors:** the server logs denied actions safely without leaking secrets in responses.
11. **Defense in depth:** URL/method layers + domain policies + data-access filters applied consistently.

## 12. Common Misconceptions and Fixes

| Misconception | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| "Without an admin button, users can't call the feature." | HTTP endpoints exist independently of rendered HTML. | Protect `/admin/**` and services on the server. |
| "A disabled button prevents data changes." | Clients can send POST requests directly. | Always enforce server-side authorization and validation. |
| "Having `sec:authorize` is enough." | The dialect only controls template output. | Use `authorizeHttpRequests`, `@PreAuthorize`, and resource policies. |
| "Anyone with ROLE_USER can view any report." | A role does not prove ownership or tenant membership. | Enforce object-level authorization. |
| "If the frontend sends `isAdmin=true`, the server obeys." | Client-controlled data cannot be trusted. | Derive permissions from trusted Authentication/permission stores. |
| "The API returns 403; just disable CSRF to fix it." | 403 may legitimately stem from a missing token or missing permission. | Diagnose CSRF and authorization separately. |
| "Protecting the controller is enough." | Methods may be invoked via other paths. | Enforce security at the business boundary with proper method security. |
| "Data hidden with CSS is not leaked." | The data is already in the DOM and network payload. | Never send unauthorized data. |
| "An admin in tenant A has rights in tenant B." | Roles do not automatically imply tenant scope. | Bind user, resource, and tenant in policy checks. |
| "Testing that HTML hides the button proves the backend is safe." | UI tests skip direct HTTP access. | Test endpoint statuses/responses across roles and resource IDs. |

## 13. Summary

**UI visibility is a UX decision**, while **authorization is a server-side security decision**. Spring MVC/Thymeleaf can use `sec:authorize` to show the right menus; Spring Security Servlet uses `SecurityFilterChain` to guard URLs/methods; `@PreAuthorize` and business policies validate permissions on operations and resources; and the data-access layer scopes what can be read or modified. All of these must still hold even when a user **never opens the UI**, calls APIs directly, or tampers with requests.

**Rule to remember:** *Do not protect a feature by hiding the button; protect the action that the button triggers.*

## References

- Spring Security Reference — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security Reference — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security Reference — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Thymeleaf Extras Spring Security: https://github.com/thymeleaf/thymeleaf-extras-springsecurity

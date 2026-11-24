# Integrating Forms, Thymeleaf, or JSP with Identity and CSRF Tokens

**Module:** Spring Security – Servlet  
**Parent Topic:** MVC Integration

## 1. Objectives and Problem Statement

An HTML-rendering Spring MVC page typically needs three things at once:

1. **Identify the current user** from Spring Security's `Authentication`, rather than trusting a username or role submitted by a form.
2. **Protect state-changing actions** such as POST record creation, POST updates, or POST logout against **Cross-Site Request Forgery (CSRF)** when browsers automatically attach session cookies.
3. **Bind and validate forms**, displaying errors and content using HTML escaping; never mistake a CSRF token for input validation or XSS protection.

This lesson focuses on **Spring Security Servlet + Spring MVC + server-rendered Thymeleaf or JSP**. We will build an example featuring form login, displaying the username, creating user-scoped private notes, and logging out via POST with a CSRF token. Then we compare JSP syntax and test with MockMvc.

**Principle:** Authentication answers "who"; Authorization answers "what is allowed"; CSRF tokens reduce the risk of a browser being tricked into sending unintended actions; validation and escaping keep data safe and valid. None of these layers replaces another.

## 2. Request Flow and Where Identity/CSRF Participate

~~~text
Browser                     Spring Security Servlet       Spring MVC
   | GET /notes                       |                        |
   |--------------------------------->|                        |
   |      session cookie is read      |                        |
   |                Authentication -> | ----> Controller GET   |
   |                                  |       Model + View      |
   |         HTML: username, notes, form, _csrf.token          |
   |<---------------------------------------------------------|
   | POST /notes + cookie + CSRF field                         |
   |---------------------------------------------------------> |
   |                CsrfFilter verifies token                 |
   |                Authorization checks permission           |
   |                                  | ----> @Valid form      |
   |                                  |       writes right owner
   |               302 /notes         |                        |
   |<---------------------------------------------------------|
   | GET /notes (Post/Redirect/Get)                             |
   |---------------------------------------------------------->|
~~~

If a POST lacks a valid token, **`CsrfFilter` typically returns HTTP 403** and the controller never runs the action. If unauthenticated, a GET request to a protected page is typically redirected to the login page. Do not assume every 403 is a CSRF error: missing permissions can also return 403; inspect logs and flow safely.

### Authentication and Principal

Spring Security stores `Authentication` in `SecurityContext`. With standard form login, the principal may be `UserDetails`; with OAuth2/OIDC login, it may be `OAuth2User` or `OidcUser`.

In an MVC controller:

~~~java
@GetMapping("/profile")
String profile(Authentication authentication, Model model) {
    model.addAttribute("username", authentication.getName());
    return "profile";
}
~~~

This is an **illustrative method snippet inside a protected controller**, not a standalone Java class. `Authentication#getName()` returns the identity from Spring Security, not a field freely editable by the user in the browser.

Alternatives:

- `@AuthenticationPrincipal UserDetails user` when the app guarantees the principal is `UserDetails`.
- `@AuthenticationPrincipal` with the appropriate OAuth2/OIDC principal if using that login type.
- In Thymeleaf with extras: `sec:authentication="name"`.
- In JSP: Servlet `request.userPrincipal` or the corresponding Spring Security taglib.

Never cast to a form-login principal when the application actually uses OAuth2. On `permitAll()` endpoints and unauthenticated requests, check for `null`/anonymous before use.

### Authority Is Not Just Hiding Buttons

`hasRole("USER")` typically checks for authority `ROLE_USER`. Having Thymeleaf/JSP hide buttons based on role only helps the UI; clients can still send HTTP requests directly. The server must protect the endpoint and then enforce permissions **on the specific resource and tenant** when needed.

## 3. Spring Security Servlet's CSRF Mechanism

### 3.1. Why Do Session Cookies Create CSRF Risk?

Browsers automatically send authentication cookies when issuing requests to the matching cookie scope. Another website can try to trigger an action on the real application inside the victim's browser context. If the server checks only the session cookie, the forged request may look valid.

Spring Security's CSRF protection typically requires a token for **POST, PUT, PATCH, DELETE** and treats **GET, HEAD, OPTIONS, TRACE** as safe under the default matcher. Therefore, **never perform state-changing operations via GET** to avoid CSRF.

A server-rendered form may carry a hidden field:

~~~html
<form method="post" action="/notes">
    <input name="text" value="Hello">
    <input name="_csrf" type="hidden" value="server-issued-token">
    <button type="submit">Save</button>
</form>
~~~

The string `server-issued-token` is an explanatory example only; **never hardcode tokens**. The actual value and field name must come from the request's `CsrfToken`.

### 3.2. Key Components

| Component | Role |
| --- | --- |
| `CsrfFilter` | Decides which methods require a token and validates the token in the request. |
| `CsrfTokenRepository` | Generates and stores the expected token; a common MVC session setup uses `HttpSessionCsrfTokenRepository`. |
| `CsrfTokenRequestHandler` | Makes the token available on the request and resolves submitted values; Spring Security 6 supports deferred tokens and XOR masking to mitigate BREACH. |
| Request attribute `_csrf` | Allows templates to read `_csrf.parameterName`, `_csrf.token`, and `_csrf.headerName`. |
| Session cookie | Maintains the login session; cannot substitute for a CSRF token value. |

In standard HTTP configurations, Spring Security **enables CSRF by default**. Never call `csrf.disable()` just to bypass a 403 error caused by a missing form field.

### 3.3. How Does a Form Token Reach the Filter?

~~~text
GET /notes
  -> filter exposes _csrf
  -> template renders hidden field named _csrf.parameterName
     and value _csrf.token
  -> browser holds session cookie

POST /notes
  -> browser sends cookie + hidden field
  -> CsrfFilter validates token against repository/handler
  -> if valid: proceed to authorization and controller
  -> if invalid/missing: typically 403
~~~

Another POST form like `/logout` also requires a token when CSRF is enabled. Tokens may be cleared and rotated upon login/logout, so an HTML form left open from an old session may receive 403. The right remedy is to **reload the page/form** to obtain the active token, not to disable CSRF.

### 3.4. Cases Not to Misunderstand

- A CSRF token **does not** stop malicious JavaScript already running in the application's origin from abusing the user's privileges; prevent XSS with proper escaping and CSP.
- A CSRF token **does not** make fields like `ownerId`, `role`, or `price` trustworthy. Clients can modify hidden inputs.
- **SameSite cookies** mitigate risk in certain scenarios, but are not a default reason to drop CSRF tokens.
- Stateless APIs authenticating **strictly via bearer tokens in the Authorization header** have a different threat model. Do not copy that API config onto a session-cookie MVC form app.
- If an app configures multiple `SecurityFilterChain`s, ensure form paths traverse a chain with proper CSRF and authorization.

## 4. Thymeleaf: Identity, Form Binding, and CSRF Tokens

Thymeleaf receives the `Model` from the controller, binds field values, and escapes output automatically when using the right processors.

### 4.1. Displaying Identity with Thymeleaf Extras

With the `thymeleaf-extras-springsecurity6` dependency compatible with Spring Security 6, you can write:

~~~html
<html xmlns:th="http://www.thymeleaf.org"
      xmlns:sec="https://www.thymeleaf.org/extras/spring-security">
<body>
    <p sec:authorize="isAuthenticated()">
        Hello, <strong sec:authentication="name">Name</strong>
    </p>
</body>
</html>
~~~

`sec:authentication="name"` reads server-managed authentication info. `sec:authorize` only alters the **view**; it must never be used as the sole permission check.

### 4.2. Explicit Token in a Form

~~~html
<form method="post" action="/notes" th:object="${noteForm}">
    <label for="text">Note</label>
    <input id="text" th:field="*{text}" type="text"
           maxlength="200" required>

    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">

    <p th:if="${#fields.hasErrors('text')}"
       th:errors="*{text}">Invalid data</p>

    <button type="submit">Save</button>
</form>
~~~

- `th:object` selects the DTO; `th:field` binds the input to property `text`.
- `_csrf.parameterName` and `_csrf.token` come from the Spring Security request.
- `th:errors` displays errors from `BindingResult`; the server must use `@Valid`.
- HTML `required` and `maxlength` only assist UX and are easily bypassed by crafted requests.

**Caution with automatic CSRF:** with `th:action`, Spring-integrated Thymeleaf can automatically inject a hidden CSRF field via `RequestDataValueProcessor`. When using the automatic approach, do not add a second explicit hidden field. The example above uses the **explicit** approach with a static `action`. If the app runs under a context path other than `/`, use the URL expression `@{/notes}` and inspect the rendered HTML to avoid path or duplicate-token bugs.

### 4.3. Escaping Data on Output

~~~html
<!-- Safe: Thymeleaf escapes content in HTML text context. -->
<li th:each="note : ${notes}"
    th:text="${note}">Note content</li>

<!-- Unsafe for unsanitized data. -->
<li th:utext="${note}">Note content</li>
~~~

If a user saves `<img src=x onerror=alert(1)>`, `th:text` renders it as **plain text**, not an executable HTML tag. A CSRF token does not replace output escaping, and length validation alone does not stop XSS.

## 5. Complete Spring Boot 3.3.5 / Java 17 Project

This project uses Spring MVC Servlet, Security form login, Thymeleaf, Bean Validation, and MockMvc. The Boot version is pinned for syntax reproducibility; production must use a supported release with current security patches.

Features:

- `GET /notes`: viewable only by users with `ROLE_USER`.
- `POST /notes`: writable only by users with `ROLE_USER`, a valid CSRF token, and valid input.
- `POST /logout`: logs out through Spring Security with a CSRF token.
- Notes are partitioned by the **server-authenticated** username; no `ownerId` is accepted from the form.
- Data is stored temporarily in memory, not a production repository.

### 5.1. Directory Structure

~~~text
mvc-form-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/MvcFormApplication.java
    │   └── resources/templates/notes.html
    └── test/java/demo/MvcFormApplicationTests.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>mvc-form-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.thymeleaf.extras</groupId>
            <artifactId>thymeleaf-extras-springsecurity6</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

### 5.3. src/main/java/demo/MvcFormApplication.java

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@SpringBootApplication
public class MvcFormApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcFormApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // For learning only: never hardcode passwords in production.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("learning-only"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("learning-only"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/notes")
                    .hasRole("USER")
                .requestMatchers(HttpMethod.POST, "/notes")
                    .hasRole("USER")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        // Do not disable CSRF: POST requests remain protected by default.
        return http.build();
    }

    public static class NoteForm {
        @NotBlank
        @Size(max = 200)
        private String text;

        public String getText() {
            return text;
        }

        public void setText(String text) {
            this.text = text;
        }
    }

    @Controller
    public static class NoteController {
        private final Map<String, CopyOnWriteArrayList<String>> notes =
            new ConcurrentHashMap<>();

        @GetMapping("/notes")
        public String page(Authentication authentication, Model model) {
            model.addAttribute("noteForm", new NoteForm());
            model.addAttribute(
                "notes",
                notes.getOrDefault(
                    authentication.getName(), new CopyOnWriteArrayList<>()
                )
            );
            return "notes";
        }

        @PostMapping("/notes")
        public String save(
                @Valid @ModelAttribute("noteForm") NoteForm form,
                BindingResult errors,
                Authentication authentication,
                Model model) {
            if (errors.hasErrors()) {
                model.addAttribute(
                    "notes",
                    notes.getOrDefault(
                        authentication.getName(), new CopyOnWriteArrayList<>()
                    )
                );
                return "notes";
            }

            // User identity comes from Authentication, NOT from a hidden field.
            notes.computeIfAbsent(
                authentication.getName(),
                key -> new CopyOnWriteArrayList<>()
            ).add(form.getText());

            return "redirect:/notes";
        }
    }
}
~~~

**Explanation:**

- `formLogin(Customizer.withDefaults())` provides the default login form at `/login`. No separate login controller is needed for the demo.
- In-memory users `alice`/`bob` have demo password `learning-only`. Passwords are encoded using Spring's `PasswordEncoder`. **Never deploy this setup to production**.
- `hasRole("USER")` checks authority `ROLE_USER` using the default prefix.
- `@Valid` + `BindingResult` (placed immediately after the bound object) rejects blank or overly long input. Only the DTO containing `text` is bound—never an entity with `ownerId` or `role`.
- `Authentication#getName()` determines the owner. User Alice cannot alter the owner by adding extra form parameters.
- Data is held in `ConcurrentHashMap` and `CopyOnWriteArrayList` only for a light-write demo; there is no persistence, transaction management, or production data authorization.
- `redirect:/notes` implements **Post/Redirect/Get**, preventing duplicate POST submissions on browser refresh.
- Logout is handled by Spring Security by default; with CSRF enabled, `POST /logout` with a token is standard.

### 5.4. src/main/resources/templates/notes.html

~~~html
<!DOCTYPE html>
<html lang="en"
      xmlns:th="http://www.thymeleaf.org"
      xmlns:sec="https://www.thymeleaf.org/extras/spring-security">
<head>
    <meta charset="UTF-8">
    <title>Private Notes</title>
</head>
<body>
    <h1>My Notes</h1>
    <p sec:authorize="isAuthenticated()">
        Signed in:
        <strong sec:authentication="name">Username</strong>
    </p>

    <form method="post" action="/notes" th:object="${noteForm}">
        <label for="text">Content</label>
        <input id="text" type="text" th:field="*{text}"
               maxlength="200" required>
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">
        <p th:if="${#fields.hasErrors('text')}"
           th:errors="*{text}">Invalid value</p>
        <button type="submit">Save</button>
    </form>

    <ul>
        <li th:each="note : ${notes}"
            th:text="${note}">Escaped note</li>
    </ul>

    <form method="post" action="/logout">
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">
        <button type="submit">Sign out</button>
    </form>
</body>
</html>
~~~

Here the form uses a static `action` together with an explicit hidden token. Both **POST create note** and **POST logout** include the token. With `th:action` and Spring integration, the framework can add the hidden token automatically; do not mix both approaches on the same form without inspecting the final HTML.

`th:text` escapes content during rendering. For example, entering `<img src=x onerror=alert(1)>` makes the browser display the literal text without running any event handler. Never replace `th:text` with `th:utext` unless the data has been sanitized under an explicit policy.

### 5.5. Running the Demo

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Open:

~~~text
http://localhost:8080/notes
~~~

Expect the browser to redirect to `/login`. Sign in with `alice` / `learning-only`. When the form POST includes a valid token, the page redirects back to `/notes`, and the text appears in Alice's list. Sign out and sign in as Bob: Bob's list is independent of Alice's in demo memory.

Try submitting the form without a CSRF token (e.g., via an HTTP test carrying the session cookie): Spring Security typically returns 403. Open DevTools Network to inspect request fields and the session cookie, but **never copy real tokens or cookies into logs or tickets**.

The steps here describe **expected behavior** when running the code, not captured execution logs from this environment.

## 6. MockMvc: Testing Identity, CSRF, Validation, and Escaping

File **src/test/java/demo/MvcFormApplicationTests.java**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcFormApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadNotes() throws Exception {
        mvc.perform(get("/notes"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/notes").param("text", "Hello"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void validPostEscapesStoredNote() throws Exception {
        String payload = "<img src=x onerror=alert(1)>";

        mvc.perform(post("/notes").with(csrf()).param("text", payload))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/notes"));

        mvc.perform(get("/notes"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("&lt;img")))
            .andExpect(content().string(not(containsString(payload))));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void invalidFormIsRejectedByServer() throws Exception {
        mvc.perform(post("/notes").with(csrf()).param("text", "   "))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasFieldErrors("noteForm", "text"));

        mvc.perform(post("/notes").with(csrf())
                .param("text", "a".repeat(201)))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasFieldErrors("noteForm", "text"));
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void otherUserSeesOwnPage() throws Exception {
        mvc.perform(get("/notes"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("bob")));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void logoutWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/logout"))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Expected:** all tests pass; this is not a verified execution output from this environment.

`@WithMockUser` creates a simulated `SecurityContext` for testing filters and controllers; it **does not test real password login**. `csrf()` is a test helper generating a valid token, not how a production client obtains tokens. For form-login integration tests, use `formLogin()` in Spring Security Test or browser integration as needed.

In real products, expand tests for: users lacking the required role, valid logout, session fixation, protected routes, resource ownership, stale tokens after session changes, binding errors, and safe logging of 403 responses.

## 7. JSP: Same Security Principles, Different Rendering from Thymeleaf

JSP is rendered by Spring MVC inside the Servlet container. With Spring Security, the server still supplies `Authentication`, the CSRF request attribute, and authorization filters. JSP is not a CSRF-protection filter.

**Illustrative JSP fragment**, placed at `/WEB-INF/jsp/notes.jsp` in a JSP project configured with Jakarta JSTL:

~~~jsp
<%@ page contentType="text/html;charset=UTF-8" %>
<%@ taglib prefix="c" uri="jakarta.tags.core" %>

<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>JSP Notes</title></head>
<body>
    <p>
        Signed in:
        <c:out value="${pageContext.request.userPrincipal.name}"/>
    </p>

    <form method="post"
          action="${pageContext.request.contextPath}/notes">
        <input name="text" maxlength="200" required>
        <input type="hidden"
               name="${_csrf.parameterName}"
               value="${_csrf.token}">
        <button type="submit">Save</button>
    </form>

    <ul>
        <c:forEach var="note" items="${notes}">
            <li><c:out value="${note}"/></li>
        </c:forEach>
    </ul>

    <form method="post"
          action="${pageContext.request.contextPath}/logout">
        <input type="hidden"
               name="${_csrf.parameterName}"
               value="${_csrf.token}">
        <button type="submit">Sign out</button>
    </form>
</body>
</html>
~~~

**Key distinctions:**

- Raw JSP expression language `${note}` output directly into HTML **does not guarantee escaping** like `th:text`. Use `<c:out>` for HTML text or an encoder appropriate to the output context.
- `request.userPrincipal` reflects the current user when Spring Security/Servlet request wrapping is properly configured. The page must require authentication or handle a missing principal.
- `_csrf.parameterName` and `_csrf.token` come from request attributes; JSP does not invent tokens itself.
- `${pageContext.request.contextPath}` builds the right URL when the app is not deployed at root context path `/`.
- If the app uses the Spring MVC form tag library, it has its own field-binding and error-display mechanisms; Spring Security still handles CSRF in the filter layer.

JSP on Spring Boot 3 / Jakarta Servlet requires a compatible JSP engine, container, and Jakarta JSTL (such as Jasper on Tomcat), a view resolver, and appropriate packaging; typically a WAR or JSP-capable container setup is used rather than assuming an executable JAR always runs JSP. Dependency versions must match the Boot/Jakarta JSP versions in use.

**In a JSP project only**, for example:

~~~properties
spring.mvc.view.prefix=/WEB-INF/jsp/
spring.mvc.view.suffix=.jsp
~~~

Do not apply this resolver configuration directly to the Thymeleaf example in section 5 unless intentionally configuring multiple resolvers. The JSP snippets are **view illustrations**, not a standalone runnable project without a JSP runtime.

### 7.1. Thymeleaf vs. JSP Comparison Table

| Task | Thymeleaf | JSP |
| --- | --- | --- |
| Display username | `sec:authentication="name"` or Model | `request.userPrincipal` / Spring Security JSP taglibs |
| Add CSRF to form | `th:name="${_csrf.parameterName}"`, `th:value="${_csrf.token}"` | `name="${_csrf.parameterName}"`, `value="${_csrf.token}"` |
| Escape HTML text | `th:text` | `<c:out>` |
| Form binding | `th:object`, `th:field`, `th:errors` | Spring form taglib or HTML form + model errors |
| Role-based UI | `sec:authorize` | Spring Security JSP taglib or Model |
| Server authorization | `SecurityFilterChain` / method security | `SecurityFilterChain` / method security |
| Runtime | Template engine | JSP compiler, JSTL, container, view resolver |

**Conclusion:** the rendering engines differ, but **the CSRF filter and server-side permission enforcement** are the exact same Spring Security responsibilities.

## 8. Login, Logout, and Advanced Scenarios

### 8.1. Custom Login Page

Instead of the default login page, you can build a custom Thymeleaf form:

~~~html
<form method="post" action="/login">
    <input name="username" autocomplete="username">
    <input name="password" type="password"
           autocomplete="current-password">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Sign in</button>
</form>
~~~

This is a **fragment**, not a complete app. To use a custom page, declare `loginPage` and create a GET controller returning the view:

~~~java
// Snippet inside HttpSecurity configuration:
.formLogin(form -> form.loginPage("/login").permitAll())
~~~

**Login POST also needs a CSRF token** when CSRF is enabled, helping mitigate login CSRF. Never write custom password-comparison code in a controller when Spring Security already provides authentication filters and providers.

### 8.2. Logout via POST

With CSRF enabled, `POST /logout` is the standard approach. `GET /logout` in some setups only shows a confirmation page; never rely on a GET link to change state. When session/logout state changes, old tokens can become invalid.

### 8.3. AJAX Sending JSON from an MVC Page

If part of a view issues fetch/AJAX calls, you can expose the token and header name as meta tags:

~~~html
<meta name="_csrf" th:content="${_csrf.token}">
<meta name="_csrf_header" th:content="${_csrf.headerName}">
~~~

Then send the header on POST:

~~~javascript
const token = document.querySelector('meta[name="_csrf"]').content;
const header = document.querySelector('meta[name="_csrf_header"]').content;

const headers = { "Content-Type": "application/json" };
headers[header] = token;

const response = await fetch("/api/action", {
    method: "POST",
    credentials: "same-origin",
    headers,
    body: JSON.stringify({ action: "save" })
});

if (!response.ok) throw new Error("Request failed");
~~~

This is an **illustrative browser JavaScript snippet**, assuming `/api/action` is implemented and properly protected; it is not an existing component of the project in section 5. For cross-origin SPAs or cookie-based CSRF repositories, design CORS, SameSite, token lifecycle, and request handlers accordingly; never arbitrarily use a raw cookie token if the configuration uses XOR/BREACH protection.

### 8.4. Hidden Fields Cannot Self-Authenticate Data

A valid CSRF token **does not** make `ownerId`, `role`, `price`, `approved`, or `isAdmin` in a hidden field trustworthy. Clients can edit any request input. The server must obtain the true owner from authentication or database resource ownership, enforce business rules, and use parameterized queries.

If a user is not allowed to write to project ID 999, checking `hasRole("USER")` alone is insufficient; the service must verify permissions against that specific project.

## 9. Common Errors

| Symptom | Cause and Resolution |
| --- | --- |
| Form POST returns **403** after login | Check CSRF field, session cookie, stale token, or missing permissions; 403 does not automatically mean wrong password. |
| Form has two `_csrf` fields | `th:action`/RequestDataValueProcessor may auto-insert one alongside a manual hidden field; pick one method. |
| `_csrf` request attribute is missing | Request bypassed the chain, CSRF is disabled, or handler/view mismatch; check configuration. |
| GET page renders, but POST returns 404 | Wrong context path in action or wrong controller mapping; build URLs with context path. |
| `sec:authentication` renders nothing | Check extras dependency, XML namespace, and security context. |
| Button hidden by `sec:authorize`, yet URL still works | Missing server authorization; UI does not replace filter/method security. |
| JSP renders raw HTML from note | Used raw JSP EL instead of escaping; use `<c:out>`. |
| Spring Boot 3 JSP fails to render | Missing Jasper/Jakarta JSTL/view resolver, WAR/JAR mismatch, or legacy `javax.servlet` namespace. |
| `@Valid` does not reject input | Missing validation starter/constraints or `BindingResult` in wrong parameter position. |
| POST after logout returns 403 | Session/token changed; reload the form/token rather than disabling CSRF. |
| Valid token submitted, yet another user's data is modified | Per-resource authorization bug; determine owner and enforce permissions on the server. |
| Using GET for updates because "POST hits CSRF" | Violates HTTP semantics and introduces vulnerabilities; fix the form token and keep state-changing methods. |
| Curl POST with cookie still gets 403 | Curl does not automatically extract the CSRF field from the GET form; reuse the same session and valid token in tests. |

## 10. Acceptance Checklist

1. Anonymous GET to protected page → redirects to login or responds appropriately without leaking data.
2. GET after login → displays correct user name, never read from a browser-submitted field.
3. Form POST with server-rendered token → succeeds when permissions and input are valid.
4. Form POST **missing/invalid token** → does not mutate data.
5. Unauthorized user or accessing another user's resource → server rejects even with a valid token.
6. Empty/oversized input → server validation reports errors and does not save.
7. Content with HTML/scripts → escaped in Thymeleaf/JSP and never executes.
8. Logout POST with token → terminates session; old tokens cannot be reused outside policy.
9. Static assets, login page, error page → matched by the proper chain without accidentally dropping security headers.
10. HTTPS, Secure/HttpOnly/SameSite session cookies, timeouts, and session-fixation protection → suitable for production.
11. If multiple chains exist (MVC forms and bearer APIs) → configure CSRF per threat model rather than disabling globally.
12. For JSP → confirm taglib, view resolver, and compatible container/Jakarta runtime.

## 11. Self-Check

**Q1:** Once a user is logged in, why does a form still need a CSRF token?  
**Answer:** Browsers can attach session cookies automatically. The token adds proof that a state-changing request came from the application's intended flow, not merely a cookie.

**Q2:** Does `sec:authorize` protect `POST /notes`?  
**Answer:** No. It only controls what HTML is rendered. Authorization must live in Spring Security filters, method security, or services.

**Q3:** Why should JSP use `<c:out>` to render notes?  
**Answer:** Raw JSP EL does not automatically HTML-escape safely like `th:text`. Untrusted data must be encoded for its output context.

**Q4:** Does a valid CSRF token make a hidden `ownerId` field trustworthy?  
**Answer:** No. Hidden fields remain client-controlled; the server must verify identity and per-resource ownership.

**Q5:** What should you do if a form from an old session returns 403 on POST after login/logout?  
**Answer:** Fetch a fresh token via GET/view or an appropriate refresh flow, and check session/handler alignment; do not remove CSRF.

**Q6:** If an API is completely stateless and accepts only bearer tokens in headers, does it necessarily use CSRF like a form app?  
**Answer:** The threat model differs; evaluate whether browsers attach credentials automatically. Never use that API pattern as an excuse to disable CSRF for form/session apps.

---

**Key takeaway:** Form integration with Spring Security Servlet must combine **Authentication**, **Authorization**, **CSRF tokens**, **server-side validation**, and **output encoding**. Thymeleaf and JSP are two view-rendering engines, not two different CSRF protections. Spring Security validates requests and permissions; MVC processes data; templates render verified identity, tokens, and escaped content.
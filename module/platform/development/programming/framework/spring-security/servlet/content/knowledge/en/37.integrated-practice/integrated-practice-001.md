# MVC Application with Form Login, Role-Based Access, and Admin Page — Spring Security Servlet

## 1. What Does This Practice Build?

A **Spring MVC + Thymeleaf** web application with a public home page, login page, personal account page, and admin page. Unauthenticated users are redirected to the form login when opening a private area. Users with the **USER** role can view the account page. Only users with the **ADMIN** role can access **/admin**; regular users who manually type this URL are still denied by Spring Security.

Technologies: **Java 17**, **Spring Boot 3.4.5**, **Spring Security 6**, Maven, Spring MVC Servlet, Thymeleaf, JUnit 5, and Spring Security Test. The configuration includes **BCryptPasswordEncoder**, **InMemoryUserDetailsManager** for demo purposes, form authentication, **SecurityFilterChain**, session, and **CSRF protection**. It includes source files, run steps, and MockMvc tests.

**Expected outcome:** not only can users log in, but it also proves the system rejects **anonymous** requests, **wrong passwords**, **missing CSRF tokens**, and **ROLE_USER calling the admin page**.

### Features and Access Matrix

| URL | Unauthenticated | USER | ADMIN |
| --- | --- | --- | --- |
| GET / | 200 | 200 | 200 |
| GET /login | 200 | Access allowed | Access allowed |
| POST /login | Processes username/password + CSRF | Same processing | Same processing |
| GET /account | 302 -> /login | 200 | 200 |
| GET /admin | 302 -> /login | **403** | **200** |
| POST /logout | Requires CSRF per security chain | Logout + redirect | Logout + redirect |

In the example:
- User **reader** has **ROLE_USER**.
- User **admin** has both **ROLE_USER** and **ROLE_ADMIN**.
- Demo passwords are **reader-pass** and **admin-pass** respectively, for localhost use only.

**Authentication** verifies identity; **authorization** determines permissions. Receiving 200 from a public route does not prove the caller is logged in. An authenticated user lacking ROLE_ADMIN still cannot access /admin.

## 2. How Does Spring Security Form Login Process a Request?

~~~text
Unauthenticated Browser
    |
    +-- GET /account
           |
           v
       Spring Security FilterChainProxy
           |
       AuthorizationFilter requires authenticated
           |
       AuthenticationEntryPoint
           |
       302 Location: /login
           |
    +-- GET /login
           |
       MVC controller -> Thymeleaf login.html
           |
       Form contains username/password and CSRF token
           |
    +-- POST /login
           |
       CsrfFilter validates CSRF
           |
       UsernamePasswordAuthenticationFilter
           |
       AuthenticationManager / DaoAuthenticationProvider
           |
       UserDetailsService + PasswordEncoder.matches(...)
           |
       +---------+-----------+
       |                     |
    Failure               Success
       |                     |
    302 /login?error     Verified Authentication
                             |
                         SecurityContext
                             |
                         HttpSession
                             |
                         302 /account
                             |
    +-- GET /account with session cookie
           |
       SecurityContext is restored
           |
       AuthorizationFilter allows
           |
       PageController -> Thymeleaf account.html
~~~

**GET /login** is handled by the controller returning an HTML page. **POST /login** is handled by **UsernamePasswordAuthenticationFilter** via **loginProcessingUrl("/login")**; you do not need and should not write a controller to compare passwords manually for that route.

After login, Spring Security stores Authentication in SecurityContext, and in the typical form-session mechanism, the context is bound to the session so subsequent requests using the session cookie are recognized. The framework provides protections for session fixation and session logout; do not manually hold SecurityContext in a singleton/static field.

**The /admin case:** AuthorizationFilter compares GrantedAuthority against the **hasRole("ADMIN")** rule. User reader is logged in but only has ROLE_USER, so they receive 403; hiding the link in HTML is not a security barrier.

## 3. Project Setup and Dependencies

File structure:

~~~text
mvc-role-portal/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/portal/
    │   │   ├── MvcRolePortalApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PortalController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/
    │           ├── home.html
    │           ├── login.html
    │           ├── account.html
    │           └── admin.html
    └── test/java/demo/portal/
        └── PortalSecurityTests.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-role-portal</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

**starter-web** provides Servlet MVC; **starter-thymeleaf** renders HTML; **starter-security** provides filters/providers/security context; **spring-security-test** enables using **user()**, **csrf()**, and testing authentication/authorization in MockMvc. The parent manages dependency versions.

## 4. Java Application and Security Configuration

### 4.1. MvcRolePortalApplication.java

**src/main/java/demo/portal/MvcRolePortalApplication.java**:

~~~java
package demo.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcRolePortalApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcRolePortalApplication.class, args);
    }
}
~~~

### 4.2. SecurityConfiguration.java

**src/main/java/demo/portal/SecurityConfiguration.java**:

~~~java
package demo.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                    .password(encoder.encode("reader-pass"))
                    .roles("USER")
                    .build(),
                User.withUsername("admin")
                    .password(encoder.encode("admin-pass"))
                    .roles("USER", "ADMIN")
                    .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(
                        "/", "/login", "/error", "/css/**")
                        .permitAll()
                    .requestMatchers("/admin", "/admin/**")
                        .hasRole("ADMIN")
                    .anyRequest().authenticated()
                )
                .formLogin(form -> form
                    .loginPage("/login")
                    .loginProcessingUrl("/login")
                    .defaultSuccessUrl("/account", false)
                    .permitAll()
                )
                .logout(logout -> logout
                    .logoutUrl("/logout")
                    .logoutSuccessUrl("/login?logout")
                    .invalidateHttpSession(true)
                    .clearAuthentication(true)
                    .permitAll()
                )
                // Keep default CSRF protection for web forms.
                .build();
    }
}
~~~

**Component breakdown:**

1. **BCryptPasswordEncoder** performs salted password hashing. Unlike plaintext storage, the encoder is used in UserDetailsService and the appropriate AuthenticationProvider. For practice, the two passwords still appear in source, so **do not deploy this demo as-is to production**. Production needs hashed passwords in a database/IdP, secret management, password policies, and rate limiting.
2. **InMemoryUserDetailsManager** creates sample users. **.roles("USER")** generates the **ROLE_USER** authority; **.roles("USER", "ADMIN")** generates **ROLE_USER** and **ROLE_ADMIN**.
3. **requestMatchers(...).permitAll()** opens only public URLs. **/admin** and all **/admin/** subpaths are protected with hasRole before the fallback rule.
4. **hasRole("ADMIN")** requires **ROLE_ADMIN** by default. Do not pass a prefixed string into **.roles("ROLE_ADMIN")**; the roles method adds the prefix automatically.
5. **anyRequest().authenticated()** requires login for all remaining URLs, including **/account**.
6. **loginPage("/login")** specifies where to display the form; **loginProcessingUrl("/login")** sets the endpoint handling the form POST.
7. **defaultSuccessUrl("/account", false)** uses /account when there is no saved request. When the user requested a protected page before logging in, SavedRequestAwareAuthenticationSuccessHandler can prioritize the saved request; see section 10.
8. **logoutUrl("/logout")** uses POST when CSRF is enabled; **invalidateHttpSession(true)** and **clearAuthentication(true)** terminate the local session.
9. **Do not use csrf.disable()** in a session-cookie-based web app just to test forms. Use a valid token in HTML and MockMvc.
10. If adding a Bearer/Resource Server API, you may need a **separate SecurityFilterChain with appropriate securityMatcher and entry point**; do not default to returning a 302 HTML login redirect for a JSON API.

### 4.3. PortalController.java

**src/main/java/demo/portal/PortalController.java**:

~~~java
package demo.portal;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PortalController {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/account")
    public String account(Model model,
                          Authentication authentication) {
        model.addAttribute("displayName", authentication.getName());

        boolean isAdmin = authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch("ROLE_ADMIN"::equals);
        model.addAttribute("showAdminLink", isAdmin);

        return "account";
    }

    @GetMapping("/admin")
    public String admin(Model model,
                        Authentication authentication) {
        model.addAttribute("displayName", authentication.getName());
        return "admin";
    }
}
~~~

**@Controller** returns view names **home/login/account/admin**, rather than returning template names as JSON. Spring MVC resolves HTML files in resources/templates.

The controller receives an **Authentication** already verified by the security infrastructure. **authentication.getName()** is used here for display in the demo; it is not proof of permission on all resources. When an application holds multi-tenant data, the service layer must also check owner/ACL.

The **showAdminLink** variable only controls the UI. Reader can still type /admin manually; the server must still return **403** from the hasRole rule. Do not implement security solely by hiding menus.

**GET /login** is rendered by the controller. **POST /login** is handled by UsernamePasswordAuthenticationFilter; **no @PostMapping("/login") is needed** to manually verify passwords.

## 5. Thymeleaf HTML Views

Create four files in **src/main/resources/templates/** using Thymeleaf **th:** syntax. The expressions inside curly braces below are evaluated on the server when the template renders.

### 5.1. home.html

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>MVC Portal Home</title>
</head>
<body>
    <h1>Welcome to MVC Portal</h1>
    <p>Spring Security form login and role-based access practice.</p>
    <nav>
        <a th:href="@{/login}">Sign in</a>
        <a th:href="@{/account}">Account page</a>
    </nav>
</body>
</html>
~~~

The home page has **permitAll()**, so no Authentication is required. The /account link can be displayed publicly; if unauthenticated, the security chain redirects the visitor to /login.

### 5.2. login.html

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign in</title>
</head>
<body>
    <main>
        <h1>Sign in</h1>

        <p th:if="${param.error}">
            Invalid username or password.
        </p>
        <p th:if="${param.logout}">
            You have been signed out.
        </p>

        <form th:action="@{/login}" method="post">
            <label for="username">Username</label>
            <input id="username" name="username"
                   type="text" autocomplete="username" required>

            <label for="password">Password</label>
            <input id="password" name="password"
                   type="password" autocomplete="current-password" required>

            <input type="hidden"
                   th:name="${_csrf.parameterName}"
                   th:value="${_csrf.token}">
            <button type="submit">Sign in</button>
        </form>
        <a th:href="@{/}">Back to home</a>
    </main>
</body>
</html>
~~~

**name="username"** and **name="password"** match UsernamePasswordAuthenticationFilter defaults. Changing the input names without configuring **usernameParameter/passwordParameter** will cause login to fail even when the user enters valid credentials.

**_csrf** is exposed by Spring Security; the hidden field submits the token checked by the server on POST. With Thymeleaf Spring MVC, **th:action** can automatically inject the CSRF hidden field via RequestDataValueProcessor; the example explicitly shows the hidden field to illustrate the mechanism. When inspecting actual HTML, if a token is already injected automatically by the engine, avoid rendering an unnecessary duplicate _csrf field; one valid token is sufficient.

**Error messages:** when the password is wrong, the form failure handler redirects to **/login?error**. On successful logout, it redirects to **/login?logout**. The template uses **param.error/param.logout** to display status without returning detailed errors that reveal which accounts exist.

### 5.3. account.html

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Account page</title>
</head>
<body>
    <main>
        <h1>Account</h1>
        <p>Hello, <strong th:text="${displayName}">
            User
        </strong></p>

        <a th:if="${showAdminLink}"
           th:href="@{/admin}">
            Admin page
        </a>

        <form th:action="@{/logout}" method="post">
            <input type="hidden"
                   th:name="${_csrf.parameterName}"
                   th:value="${_csrf.token}">
            <button type="submit">Sign out</button>
        </form>
    </main>
</body>
</html>
~~~

**th:text** escapes HTML in the username; never replace it with **th:utext** for untrusted data. **th:if** only hides the admin link when the user lacks ROLE_ADMIN; server-side **hasRole** is still required and still tested independently.

### 5.4. admin.html

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Admin page</title>
</head>
<body>
    <main>
        <h1>Admin Control Panel</h1>
        <p>Administrator:
            <strong th:text="${displayName}">admin</strong>
        </p>
        <p>This page requires ROLE_ADMIN.</p>
        <a th:href="@{/account}">Back to account</a>

        <form th:action="@{/logout}" method="post">
            <input type="hidden"
                   th:name="${_csrf.parameterName}"
                   th:value="${_csrf.token}">
            <button type="submit">Sign out</button>
        </form>
    </main>
</body>
</html>
~~~

The admin page does not perform sensitive mutations itself so the exercise stays focused on web authorization. If you add POST handlers to create users, delete accounts, or change roles, you must enforce authorization/validation/CSRF/audit in both the controller and service layers, not merely show buttons in HTML.

### 5.5. application.properties

**src/main/resources/application.properties**:

~~~properties
spring.application.name=mvc-role-portal
server.port=8080
spring.thymeleaf.cache=false
~~~

**spring.thymeleaf.cache=false** is only to make template edits easier while learning. Production should configure caching alongside appropriate security headers/session timeout/TLS.

## 6. Startup and Manual Testing

Requires JDK 17+ and Maven. From the directory containing pom.xml:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Open **http://localhost:8080/**. Perform:

1. While unauthenticated, click **Account page**; the browser is redirected to /login.
2. Sign in with **reader / reader-pass**. The /account page displays reader and does not display the admin link.
3. Manually type **http://localhost:8080/admin**. Spring Security returns **403** without rendering admin.html.
4. Click **Sign out** via the POST form, returning to /login?logout.
5. Sign in with **admin / admin-pass**, open /admin from /account; the admin page displays the name admin.
6. Enter a wrong password at login to see /login?error.
7. In tests, try POST login/logout without CSRF to confirm 403.

This is a **local training application** with demo credentials; do not deploy it directly to the Internet.

### 6.1. HTTP Expectations

| Request | HTTP status | Meaning |
| --- | --- | --- |
| Anonymous GET / | 200 | Public page |
| Anonymous GET /login | 200 | HTML login form |
| Anonymous GET /account | 302 | Location to /login |
| Anonymous GET /admin | 302 | Location to /login |
| Reader GET /account | 200 | Account page |
| Reader GET /admin | 403 | Authenticated, missing authorization |
| Admin GET /admin | 200 | Has ROLE_ADMIN |
| POST /login missing CSRF | 403 | Rejected by CsrfFilter |
| POST /login wrong password, valid CSRF | 302 | Location /login?error |
| POST /login valid, no saved request | 302 | Location /account |
| POST /logout, valid CSRF | 302 | Location /login?logout |

In a browser, redirects are followed automatically; the final URL may be /login returning 200. To inspect the **initial response**, use MockMvc or curl without follow-redirect mode. Status 302 does not equate to a successful login; it can also be a redirect to the login page because the caller is unauthenticated.

## 7. MockMvc Test Suite

Create **src/test/java/demo/portal/PortalSecurityTests.java**.

~~~java
package demo.portal;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class PortalSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void homeIsPublic() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(view().name("home"))
                .andExpect(content().string(
                        containsString("MVC Portal")));
    }

    @Test
    void loginPageIsPublic() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(view().name("login"))
                .andExpect(content().string(
                        containsString("Sign in")));
    }

    @Test
    void anonymousAccountRedirectsToLogin() throws Exception {
        mvc.perform(get("/account"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void anonymousAdminRedirectsToLogin() throws Exception {
        mvc.perform(get("/admin"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void readerSeesAccountButNotAdminLink() throws Exception {
        mvc.perform(get("/account")
                        .with(user("reader").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(view().name("account"))
                .andExpect(model().attribute(
                        "displayName", "reader"))
                .andExpect(model().attribute(
                        "showAdminLink", false));
    }

    @Test
    void readerCannotOpenAdminPage() throws Exception {
        mvc.perform(get("/admin")
                        .with(user("reader").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenAdminPage() throws Exception {
        mvc.perform(get("/admin")
                        .with(user("admin").roles("USER", "ADMIN")))
                .andExpect(status().isOk())
                .andExpect(view().name("admin"))
                .andExpect(model().attribute(
                        "displayName", "admin"));
    }

    @Test
    void formLoginWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "reader")
                        .param("password", "reader-pass"))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordRedirectsToLoginError() throws Exception {
        mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "reader")
                        .param("password", "wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void successfulLoginCreatesSessionAndAllowsAccount()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "reader")
                        .param("password", "reader-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/account"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/account").session(session))
                .andExpect(status().isOk())
                .andExpect(view().name("account"))
                .andExpect(model().attribute(
                        "displayName", "reader"));
    }

    @Test
    void logoutWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/logout"))
                .andExpect(status().isForbidden());
    }

    @Test
    void successfulLogoutRedirectsToConfirmation()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "admin")
                        .param("password", "admin-pass"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"));
    }
}
~~~

**There are 12 @Test methods.** This test suite covers public routes, anonymous redirects, USER/ADMIN roles, CSRF, login failure/success, and logout. **mvn test** is expected to pass on JDK/Maven with compatible dependencies, though it should be run for real to confirm; the code here has only been statically checked.

### 7.1. Why Do We Need Both Mock Users and Real Form Login?

**.with(user("admin").roles("ADMIN"))** supplies an Authentication for the MockMvc request. It is useful when you only want to test **hasRole** and controller rendering, but **it does not check passwords or BCrypt**.

**POST /login** with **.with(csrf())** and **.param("username", ...).param("password", ...)** goes through the test app's authentication filter/provider, verifying the UserDetailsService/PasswordEncoder configuration and the login flow. Testing a second request with the same MockHttpSession proves the session works across multiple requests.

**Do not confuse MockMvc with a real embedded HTTP server:** TLS, Secure/HttpOnly/SameSite cookies over the network, proxy headers, and external IdPs require separate integration/E2E tests.

### 7.2. Testing View Name vs. Testing Rendered HTML

**view().name("admin")** confirms the handler selected the right template. **content().string(...)** verifies the rendered HTML contains the expected text. If you need to test role-based menus, you can assert that reader's HTML does not contain the /admin link while admin's HTML does. Still, **the most important check remains that a reader request to /admin returns 403**.

### 7.3. Testing Saved Request and Roles After Login

For example: an anonymous user attempts GET /admin, Spring Security returns 302 to /login and saves the target URL in the session via RequestCache. If reader then logs in, the success handler may redirect back to the saved /admin; the next request **must still receive 403** because reader lacks ROLE_ADMIN.

This is the difference between **defaultSuccessUrl("/account", false)** (can restore a saved request) and **true** (always uses the default target). The sample tests the successful login case *without a saved request*, so asserting /account is valid.

If you add a saved-request test, reuse the same MockHttpSession between the redirected GET and the POST login, check Location per contract, and then GET /admin with that session to confirm 403. Do not assume a saved request grants extra permissions.

## 8. CSRF and Sessions in Browser Applications

### 8.1. Why Not Disable CSRF?

Browsers send session cookies according to cookie rules, and an external site can attempt to make the browser issue a POST. A CSRF token helps the server verify that a state-changing request was generated in a valid context. Login CSRF can also have subtle impacts when an attacker tries to force a browser to log into an account they control.

The GET requests in this practice do not require a token because they only read data, whereas **POST /login** and **POST /logout** require a token. For HTML forms, a hidden field uses the token issued by Spring Security:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
~~~

In MockMvc, use **.with(csrf())**; to test an invalid token, use **.with(csrf().useInvalidToken())**. Do not write **csrf.disable()** or change POST login to GET just to avoid 403.

### 8.2. Form Login and Session Lifecycle

Spring Security protects against **session fixation**; when a user authenticates, the session ID can be rotated or the session migrated depending on the Servlet container and configuration. **JSESSIONID** is a session identifier, not a token to write into business logs.

In production:
- Enforce HTTPS, and configure **Secure**, **HttpOnly**, and **SameSite** cookies for the environment.
- Configure session timeout and invalidation mechanisms on logout/password reset/offboarding.
- With multiple instances, consider Spring Session or a distributed session repository.
- Never log raw passwords, Authorization headers, cookies, or SecurityContext.
- Ensure authorities in the session do not remain stale after sensitive permission changes.
- Distinguish local logout from IdP logout if OIDC is added later.

### 8.3. POST Logout and Cookie Security

A **GET /logout** link does not replace a POST form when CSRF is enabled. Use POST with a valid CSRF token. **logoutSuccessUrl("/login?logout")** only confirms the browser is redirected to the confirmation page; to prove the session was invalidated, check a subsequent request with the old cookie or check session state in an integration test.

In MockMvc, MockHttpSession simulates a session but cannot fully replace real Set-Cookie/Cookie behavior over HTTP/TLS, so cookie flags should be tested using an embedded server test.

## 9. UI Permissions vs. Real Server-Side Permissions

**Hiding the admin link** with showAdminLink is purely UI design; it does not secure the endpoint. The server must keep **hasRole("ADMIN")** for /admin and its sub-routes.

For a real admin page, you should also protect the **service layer**. Example snippet (not standalone):

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void disableAccount(long accountId) {
    service.disableAccount(accountId);
}
~~~

You must enable **@EnableMethodSecurity** when using method authorization. For concrete operations, you also need tenant checks, ownership checks, separation of duties, auditing, and validation. Never trust roles declared in a JSON body or hidden form field.

Spring Security **hasRole("ADMIN")** normally expects the **ROLE_ADMIN** GrantedAuthority. If you use **.authorities("ADMIN")** while requiring hasRole("ADMIN"), requests may get 403. Check the exact authority string rather than removing authorization to fix it.

## 10. Common Errors and How to Fix Them

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| GET /account -> 302 | Not logged in / no session | Follow /login redirect, verify cookie |
| reader GET /admin -> 403 | Correct policy | Do not open permitAll to "fix" it |
| admin GET /admin -> 403 | Wrong username, roles, authority prefix | Check ROLE_ADMIN and authenticated user |
| POST /login -> 403 | Missing/invalid CSRF | Check _csrf, session, CsrfFilter |
| POST /login -> /login?error | Password/user mismatch | Check input name, encoder, UserDetailsService |
| Controller POST /login not called | Filter already handles the route | No POST login controller needed |
| Login page 404 | Missing controller or login.html template | Check @GetMapping("/login") and resources/templates |
| Template render exception | Wrong Model attribute/Thymeleaf expression | Check th:text and controller |
| Login succeeds but redirects elsewhere than /account | Saved request took precedence | Check defaultSuccessUrl(false), RequestCache |
| Logout button gets 403 | Missing CSRF | POST form containing CSRF token |
| Admin link hidden but URL still accessible | UI-only hiding, missing server rule | Add hasRole in SecurityFilterChain |
| MockMvc with(user()) passes, real login fails | Mock user skips password check | Test POST /login with valid/wrong credentials |
| Session still active after SSO logout | Local app logout only | Design separate IdP session/logout |
| Admin enters page but views wrong tenant | Role only, missing object ACL | Resource-level authorization in service |
| Username rendered as unwanted HTML/script | Used th:utext or unsafe rendering | Use th:text and output escaping |

**Debugging pipeline:** URL/method → SecurityFilterChain match → CsrfFilter → UsernamePasswordAuthenticationFilter → AuthenticationManager/UserDetailsService/PasswordEncoder → Authentication authorities → AuthorizationFilter → MVC controller → Thymeleaf → session/Location. A 403 error can come from **CSRF** or **missing authorization**; do not jump to conclusions before checking which layer rejected the request.

## 11. Hardening Before Production

- Replace InMemoryUserDetailsManager with an appropriate persistent UserDetailsService managing password hashes and permissions via IAM/IdP.
- Never store production usernames/passwords in source code, Git, build artifacts, or logs.
- Implement password policies, lockout/rate-limiting, credential-stuffing monitoring, and MFA/step-up for admin accounts.
- Use HTTPS with Secure/HttpOnly/SameSite cookies and session expiration policies.
- Use CSRF for browser mutations; do not rely solely on SameSite.
- Add service-layer authorization by tenant/ACL/object, not just URL roles.
- Audit login success/failure, logout, and admin operations without logging credentials.
- Handle disabled/deleted users and invalidate active sessions per revocation policy.
- Provide an appropriate 403 error page without leaking configuration or sensitive data.
- For SPAs/APIs, design separate Bearer/JWT/Resource Server handling and 401/403 JSON responses per contract; do not force APIs through HTML form login.
- Validate redirect targets, open redirects, and saved requests; do not let clients freely choose URLs outside an allowlist.
- Never serialize raw Authentication or SecurityContext to HTML/JSON.
- Run unit/integration tests against realistic environments and test across multiple browsers/nodes when using distributed sessions.

## 12. Extension Exercises

**Exercise A:** Add **GET /reports** for any logged-in user. Test anonymous 302, reader 200, and admin 200.

**Exercise B:** Add POST **/admin/users/disable**. Require Role ADMIN, CSRF, validation, service-layer authorization, and auditing. Test reader 403, admin missing CSRF 403, and valid admin request processed.

**Exercise C:** Enable **@EnableMethodSecurity** and use **@PreAuthorize** on the admin service. Verify that service-layer security still blocks unauthorized calls even if the controller is refactored.

**Exercise D:** Build a SavedRequest test: anonymous requests /admin, browser logs in as reader, redirects back to /admin and receives 403. Repeat with admin to confirm /admin succeeds. Distinguish target URL from authorization.

**Exercise E:** Replace in-memory user storage with a database, using BCrypt, account enabled/locked flags, role removal, and revocation of old HttpSessions. Analyze why updating the user store does not automatically update every Authentication already cached in a session.

## 13. Acceptance Checklist

- [ ] Java 17 and Maven work; file/package paths match the code.
- [ ] GET / and GET /login return public HTML pages.
- [ ] Anonymous GET /account, /admin redirect to /login.
- [ ] POST /login goes through UsernamePasswordAuthenticationFilter.
- [ ] Wrong password redirects to /login?error without granting access.
- [ ] Valid login creates a session, and subsequent GET /account displays the right user.
- [ ] reader only has ROLE_USER; GET /admin returns 403.
- [ ] admin has ROLE_ADMIN; GET /admin succeeds.
- [ ] UI only shows the admin link to admin, while the server still blocks direct URL access.
- [ ] BCrypt PasswordEncoder and UserDetailsService are configured properly.
- [ ] CSRF protects POST /login and POST /logout; csrf.disable() is not called.
- [ ] Logout uses POST/CSRF, invalidates the session, and redirects to /login?logout.
- [ ] MockMvc has complete positive and negative tests, including session continuity.
- [ ] Passwords, raw Authentication, or session cookies are not exposed in views/logs.
- [ ] Production plan covers TLS, session management, account revocation, auditing, and service authorization.

## 14. Self-Check Questions

1. **How does GET /login differ from POST /login?** GET is rendered by MVC; POST is handled by the authentication filter.
2. **Can ROLE_USER access /admin?** No, because the hasRole ADMIN rule blocks it.
3. **Is hiding the admin link in HTML enough?** No; the server must enforce permissions on the URL.
4. **What does anonymous access to /account receive?** Per the form-login contract, typically 302 to /login.
5. **What does a logged-in user without permission receive on /admin?** Typically 403.
6. **What authority does .roles("ADMIN") create?** ROLE_ADMIN.
7. **Why does POST /login require CSRF?** To prevent unintended state-changing requests when browsers use cookies/sessions.
8. **Does .with(user("reader")) check the password with BCrypt?** No; it builds a mock user for authorization testing.
9. **Which test verifies the demo's real credentials?** POST /login with CSRF and username/password, followed by verifying the session.
10. **Does defaultSuccessUrl("/account", false) always return /account?** No, a saved request can take precedence.
11. **Does local form-login logout end an external OIDC session?** Not applicable; OIDC is a different flow and requires separate logout handling.
12. **Can an admin view every record of every tenant?** Not by default; permissions must be checked at the resource/service level.
13. **Why not disable CSRF when tests get 403?** Because you should fix the form/token or identify the root cause instead of removing the protection layer.
14. **Is a project using InMemoryUserDetailsManager production-ready?** No, it only serves to demonstrate form login and role-based access.

**Conclusion:** A secure MVC application requires more than a login screen. It must have **Spring Security authentication, a SecurityFilterChain protecting USER/ADMIN, proper session/CSRF handling, an MVC controller and escaped templates**, along with tests proving both **allowed** and **denied** paths. Only when anonymous access, wrong passwords, missing CSRF, and missing ROLE_ADMIN all fail to bypass policy is the role-based practice complete.

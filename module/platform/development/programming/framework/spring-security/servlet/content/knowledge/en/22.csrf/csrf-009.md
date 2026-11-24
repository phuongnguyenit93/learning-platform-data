# CSRF with Multipart, File Uploads, and MultipartFilter Processing Order (Spring Security Servlet)

## 1. Problem and Outcome to Understand

In a Spring MVC application using sessions/cookies, a file upload request is typically a **POST multipart/form-data**. The browser sends both file data and form fields in multiple parts separated by a boundary. Because POST can mutate server state, Spring Security requires a valid CSRF token by default.

The challenge lies in **when the parts are read**. The security filter checks CSRF *before* the request reaches DispatcherServlet, whereas Spring MVC usually parses multipart during MVC processing. If the token resides only inside a hidden field in the multipart body, CsrfFilter may not be able to obtain the token yet when it needs to verify it.

After this lesson, you should be able to distinguish:

- **CSRF token** is used to prove a state-changing request came from a legitimate UI tied to the user's session; it does not replace authentication, authorization, or file inspection.
- **MultipartResolver** parses the multipart body and provides MultipartFile and form parameters.
- **MultipartFilter** can be placed *before the entire Spring Security filter chain* to parse multipart before CsrfFilter reads the token field.
- Sending the token via an **HTTP header** is another option for fetch/AJAX: CsrfFilter checks the header without needing to parse the body first.
- Filter ordering determines **resource risk**: parsing multipart before security can create temporary files even for unauthenticated or CSRF-blocked requests.

Scope: **Spring Security on the Servlet stack (Spring MVC, Spring Boot 3.x, Spring Security 6.x, Java 17+)**. WebFlux has a different pipeline and multipart mechanism; do not apply Servlet MultipartFilter registration from this lesson directly to WebFlux.

## 2. Why Can Multipart Lead to a 403 CSRF Error?

With standard forms using application/x-www-form-urlencoded, the container can typically provide parameters via HttpServletRequest.getParameter(). With multipart/form-data, fields and files reside inside a multipart-structured body; reading them depends on multipart parsing.

A typical Servlet flow:

~~~text
Browser
  |
  v
Servlet filter chain
  |
  +--> DelegatingFilterProxy("springSecurityFilterChain")
  |       |
  |       +--> FilterChainProxy
  |               |
  |               +--> SecurityContext, authentication, ...
  |               +--> CsrfFilter   <--- token needed here
  |
  v
DispatcherServlet
  |
  +--> MultipartResolver / HandlerMapping / Controller
  |
  v
@RequestParam("file") MultipartFile
~~~

Internal Spring Security filters run **inside** the servlet filter named springSecurityFilterChain. In the default CSRF configuration, CsrfFilter protects unsafe methods (e.g., POST, PUT, PATCH, DELETE; GET, HEAD, TRACE, and OPTIONS are normally not CSRF-checked). It obtains the expected token via CsrfTokenRepository, then extracts the client-sent token via CsrfTokenRequestHandler, typically from a header or request parameter.

If the request has not yet been multipart-parsed, the hidden field named _csrf in the body may not appear as a request parameter at the time CsrfFilter reads it. The result is usually **403 Forbidden**, even though the form sent the hidden field. Do not assume every servlet container automatically parses multipart at that point: behavior depends on multipart registration, the resolver, and how the application is initialized.

Note: Spring Security 6 has a deferred CSRF token mechanism and by default protects tokens output into HTML against BREACH using a masked token value. The UI should use the _csrf value provided by the framework to the view; do not mix masked tokens with raw cookie tokens or decode tokens manually.

## 3. Two Proper Arrangements and Trade-offs

| Approach | Where is the token sent? | When is multipart parsed? | Key trade-off |
| --- | --- | --- | --- |
| **A. MultipartFilter before Spring Security** | Hidden field in multipart body | Before CsrfFilter and typically before authentication | Supports plain HTML forms; unapproved requests can create temporary files |
| **B. Keep multipart handling after security** | Header X-CSRF-TOKEN (or name from CsrfToken.headerName) | After CsrfFilter has checked the header, typically at MVC | Reduces need to parse before CSRF check; requires JavaScript/HTTP client able to set headers |
| **Token in URL** | Query parameter on POST URL | No need to parse body to find token | Risks leaking token in logs, history, observability tools, links; should be avoided |

Neither option makes authentication, authorization, size limits, virus scanning, or rate limiting unnecessary.

## 4. Approach A: Forms with Token in Multipart Body

### 4.1. Placing MultipartFilter Before springSecurityFilterChain

Desired order:

~~~text
Client -> MultipartFilter -> springSecurityFilterChain
                              -> CsrfFilter
       -> DispatcherServlet -> Controller
~~~

MultipartFilter wraps the request in a MultipartHttpServletRequest via MultipartResolver. Hence CsrfFilter can see the _csrf parameter in the multipart body before deciding whether to let the request proceed. In Spring Boot applications, register ordering at the **Servlet filter level** using FilterRegistrationBean.

Example SecurityConfig.java, in a project with spring-boot-starter-web and spring-boot-starter-security:

~~~java
package demo.upload;

import org.springframework.boot.autoconfigure.security.SecurityProperties;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.multipart.support.MultipartFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .formLogin(login -> login.permitAll())
            // Keep default CSRF enabled.
            .build();
    }

    @Bean
    FilterRegistrationBean<MultipartFilter> multipartFilterBeforeSecurity() {
        var registration =
            new FilterRegistrationBean<>(new MultipartFilter());
        registration.setName("multipartFilterBeforeSecurity");
        registration.setOrder(SecurityProperties.DEFAULT_FILTER_ORDER - 1);
        return registration;
    }
}
~~~

In the example, MultipartFilter's registration order is lower (runs earlier) than the Spring Security filter registration order that Spring Boot uses by default. **Always check the actual order** if the project changed security filter registration order, uses multiple SecurityFilterChain beans, configures a custom servlet initializer, or adds other filters. The @Order annotation on SecurityFilterChain only selects ordering *inside* FilterChainProxy; it does not replace servlet filter registration order.

MultipartFilter looks up an appropriate multipart resolver in the root context and falls back to StandardServletMultipartResolver in supported Servlet environments. For the example to run, the application must have Spring MVC/Servlet multipart support configured; Spring Boot MVC usually auto-configures this support via spring.servlet.multipart.*. If the project uses a custom resolver, verify which resolver MultipartFilter actually uses, rather than implicitly assuming DispatcherServlet and the filter share the same resolver.

**Do not** treat http.addFilterBefore(..., CsrfFilter.class) as equivalent to registering the servlet MultipartFilter before springSecurityFilterChain. addFilterBefore only orders filters *inside* the Spring Security chain and does not express the same processing boundary.

### 4.2. Upload Endpoint Example

A complete controller at an illustrative level:

~~~java
package demo.upload;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
public class UploadController {

    @GetMapping("/upload")
    public String form() {
        return "upload";
    }

    @PostMapping("/upload")
    public String receive(@RequestParam("file") MultipartFile file,
                          RedirectAttributes flash) {
        if (file.isEmpty()) {
            flash.addFlashAttribute("message", "You have not selected a file.");
        } else {
            flash.addFlashAttribute(
                "message", "Received " + file.getSize() + " bytes.");
        }
        return "redirect:/upload";
    }
}
~~~

The controller only reads the size to illustrate the authentication/CSRF flow and **does not persist files long-term**. When implementing real storage, verify content type, size limits, generate safe storage names, isolate directories, enforce permissions, and scan contents per system requirements; never trust the client-supplied filename or Content-Type.

File src/main/resources/templates/upload.html if the project includes spring-boot-starter-thymeleaf:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Upload File</title>
</head>
<body>
  <h1>Upload File</h1>
  <form action="/upload" method="post" enctype="multipart/form-data">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <input type="file" name="file" required>
    <button type="submit">Submit</button>
  </form>
  <p th:if="${message}" th:text="${message}"></p>
</body>
</html>
~~~

The _csrf value is supplied to the request by Spring Security when the view accesses the CSRF token; Thymeleaf renders the actual field name and value matching the request handler. The example uses action="/upload" with the root context path. If using Thymeleaf's th:action, Spring MVC can auto-insert the CSRF field via RequestDataValueProcessor; inspect the rendered HTML and **do not manually insert a duplicate _csrf field**. For applications deployed under a different context path, the action URL must be built with the right context path.

Example limit configuration, file application.properties:

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
~~~

In a Boot 3.x project, use Java 17+ and the Web, Security, and Thymeleaf starters; the @SpringBootApplication class resides in package demo.upload or a parent package so SecurityConfig and UploadController are scanned. When running the application, log in via the configured form login and visit GET /upload. The returned page must include a hidden input named _csrf (or the parameterName provided by the framework), after which a valid multipart POST will be processed by the controller.

### 4.3. What Actually Happens on POST

1. Browser sends the session cookie, the "file" multipart part, and the hidden _csrf field.
2. MultipartFilter reads/parses the body, creating a request wrapper with the parts and parameters.
3. CsrfFilter checks the submitted token value against the token bound to the session/request according to the repository and request handler.
4. If the token is wrong or missing, returns 403; controller does not run. If valid, the request proceeds through authentication/authorization and MVC.
5. The controller is only allowed to process the file after passing the above checks.

**Very important trade-off:** step 2 happens before Spring Security blocks an invalid request. Depending on the implementation/resolver and memory threshold, parsing may create temporary files on disk before CSRF/authentication completes. An unauthenticated caller can still send a body to consume bandwidth, RAM, CPU, or temporary disk space, even though they cannot make the controller save the file successfully. You must enforce request size limits at the reverse proxy/container, quotas and rate limits, temporary directory management, and resource monitoring. Application-level multipart limits are only one layer of defense.

## 5. Approach B: Sending the CSRF Token via Header, Keeping Multipart After Security

If the UI uses fetch/AJAX, the client can send the token via a header instead of relying on CsrfFilter reading a parameter inside the multipart body. In that case, **there is no need to add MultipartFilter before Spring Security just to read the CSRF token**. Let Spring MVC/DispatcherServlet handle multipart after security checks as in standard configurations.

Flow:

~~~text
Client (multipart body + X-CSRF-TOKEN header)
  -> springSecurityFilterChain
       -> CsrfFilter reads header, verifies token
  -> DispatcherServlet / MultipartResolver
  -> Controller receives MultipartFile
~~~

Example Thymeleaf view placing the token in meta tags and sending FormData from JavaScript:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="_csrf" th:content="${_csrf.token}">
  <meta name="_csrf_header" th:content="${_csrf.headerName}">
</head>
<body>
  <form id="uploadForm" action="/upload"
        method="post" enctype="multipart/form-data">
    <input type="file" name="file" required>
    <button type="submit">Upload</button>
  </form>
  <p id="result"></p>
  <script>
    const form = document.getElementById("uploadForm");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const token = document.querySelector('meta[name="_csrf"]').content;
      const header = document.querySelector('meta[name="_csrf_header"]').content;

      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: { [header]: token },
        body: new FormData(form)
      });

      document.getElementById("result").textContent =
        response.ok ? "Request was accepted." :
                      "Request failed: HTTP " + response.status;
    });
  </script>
</body>
</html>
~~~

Keep the SecurityFilterChain and controller configuration similar to above, but **remove the bean registering MultipartFilter before Security** if choosing Approach B. You can use the headerName provided by CsrfToken rather than hardcoding X-CSRF-TOKEN. Do not manually set Content-Type: multipart/form-data when using FormData; the browser must append the exact boundary itself. This header must generally be sent alongside the session cookie for same-origin requests.

Note for SPAs or cookie-stored token mechanisms: Spring Security 6 distinguishes between tokens masked for HTML rendering and tokens read directly from cookies. Do not blindly read a cookie value and apply the default handler as if all token formats were identical; configure CsrfTokenRepository and CsrfTokenRequestHandler per the exact version's guidance, especially when using CookieCsrfTokenRepository.

For **direct plain HTML form submissions** (without JavaScript setting headers), Approach B does not work because HTML forms cannot create custom headers themselves; choose Approach A or redesign the request flow. Passing _csrf in the POST URL query string is a technical workaround that can be parsed early, yet should generally be avoided because URLs easily appear in logs and monitoring systems.

## 6. Distinguishing Layers of Responsibility

| Component | Role | What not to infer |
| --- | --- | --- |
| Servlet MultipartConfig / container | Enables the Servlet to process request parts | Does not decide whether the CSRF token is valid |
| MultipartResolver | Turns a multipart request into parts/MultipartFile | Does not replace authentication or authorization |
| MultipartFilter | Triggers multipart parsing early at the Servlet filter level | Does not mean the body is protected prior to parsing |
| DelegatingFilterProxy / FilterChainProxy | Bridge to the Spring Security chain | Servlet filter order differs from internal security filter order |
| CsrfFilter | Verifies tokens for protected requests | Does not scan for viruses or validate file contents |
| AuthorizationFilter | Checks endpoint access permissions | Does not replace CSRF for cookie-based authentication |
| DispatcherServlet / Controller | Maps multipart and runs upload logic | Should not process files if the request was rejected by an earlier layer |

An upload POST can return **401/redirect to login** if unauthenticated, **403** if CSRF is wrong or missing, **403** due to authorization, **413**/multipart error when exceeding size limits, or **400** for a missing "file" part. Statuses depend on configuration and filter ordering; observing 403 alone is insufficient to conclude the cause.

## 7. Testing CSRF and Filter Ordering

Example testing endpoint protection logic with MockMvc using spring-security-test and spring-boot-starter-test:

~~~java
package demo.upload;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UploadCsrfTest {

    @Autowired
    MockMvc mvc;

    private MockMultipartFile sampleFile() {
        return new MockMultipartFile(
            "file", "demo.txt", "text/plain",
            "hello".getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void missingCsrfIsRejected() throws Exception {
        mvc.perform(multipart("/upload")
                .file(sampleFile())
                .with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfCanReachController() throws Exception {
        mvc.perform(multipart("/upload")
                .file(sampleFile())
                .with(user("alice"))
                .with(csrf()))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

The first test confirms an authenticated request missing a token is blocked. The second test confirms a valid token reaches the controller and receives a redirect response. **MockMvc limitation:** MockMvc constructs a simulated multipart request and populates part data directly into the test request; it **does not prove the actual servlet container filter ordering**. Additional verification is needed by running the application on embedded Tomcat/Jetty, inspecting filter registration order, and testing uploads over real HTTP.

Integration environment testing checklist:

1. GET /upload after login returns a page with a valid token; inspect the rendered HTML for the _csrf field or CSRF meta tags, not just the template source.
2. Multipart POST in the same session with the right token reaches the controller and produces the expected outcome.
3. Multipart POST in the same session with token omitted/altered is rejected; the controller is not executed.
4. For Approach A, verify MultipartFilter stands **before** springSecurityFilterChain in servlet filter registrations; observe that body parsing happens before security.
5. For Approach B, verify the CSRF header is present before the request reaches the controller; no unnecessary early MultipartFilter registration exists.
6. Test files exceeding max-file-size and max-request-size; record the actual error type without conflating it into CSRF diagnosis.
7. Observe temp storage/bandwidth when sending unauthenticated or invalid-token requests; ensure resource limits operate properly.

During diagnosis, you can enable DEBUG logging for org.springframework.security in development to see where a request is blocked, but **never log or share raw session cookie and CSRF token values** in logs or screenshots.

## 8. Common Errors and How to Fix Them

**Error 1: Hidden _csrf exists in HTML yet POST always returns 403.** Verify the field actually appears in the outgoing request, the token belongs to the right session, the request carries the matching cookie, and it was already parsed/read by the time CsrfFilter runs. If the token is in the multipart body, check filter order; if in a header, verify the exact header name and rendered token value.

**Error 2: Registering MultipartFilter after Spring Security.** When CsrfFilter checks, the multipart wrapper does not exist yet. Set the order in servlet registration before springSecurityFilterChain; do not confuse SecurityFilterChain ordering or an HttpSecurity.addFilterBefore call with servlet filter ordering.

**Error 3: Adding MultipartFilter before security to fix 403 while ignoring temp-file risk.** Rejected requests can still be parsed and consume resources. Enforce size limits at the proxy/container, quotas, temp directory controls, rate limits, and concurrency limits; consider switching to header tokens when the client has JavaScript.

**Error 4: Disabling CSRF for /upload so the request goes through.** csrf.disable() or csrf.ignoringRequestMatchers("/upload") can expose session-cookie-authenticated endpoints to CSRF. Never use this merely to mask a parse-ordering bug. Only adjust CSRF policy after properly evaluating the authentication model and request risk.

**Error 5: Sending FormData while manually setting Content-Type.** If JavaScript assigns multipart/form-data without the matching boundary, the server may fail to parse the parts. Let fetch set Content-Type automatically when the body is FormData.

**Error 6: Mismatched field names or size configuration.** name="file" in the form must match @RequestParam("file"); missing-part or size-exceeded errors are not proof that CsrfFilter is broken. Tokens and file parts are also separate data.

**Error 7: Trusting file.getOriginalFilename().** This value is client-controlled. Do not use it as a storage path, do not infer file safety from extension/MIME type, and do not allow path traversal; inspect actual content and use server-generated names.

**Error 8: Mixing up CSRF with CORS or checking Origin alone.** CORS controls reading/sending certain browser requests across origins; it does not automatically replace CSRF mechanisms for cookie-authenticated sensitive actions. SameSite, Origin/Referer validation, and CSRF tokens can complement one another.

## 9. Selection Rules and Takeaways

- For **direct multipart HTML form POSTs** with the token in the body: ensure the token parameter is available before CsrfFilter, typically by registering MultipartFilter before Spring Security; strictly evaluate pre-authentication parse/temp-upload risks.
- For **fetch or clients able to set headers**: prefer sending the token via a header, so CSRF is verified before Spring MVC needs to parse multipart; avoid an early multipart filter solely to read the token.
- For real uploads: after passing CSRF and authentication/authorization, the controller must still limit and validate contents, store files safely, clean up resources, and monitor abuse.
- A **403** request must be traced end to end: CSRF token, session, multipart parsing location, authentication, and authorization. Fix only the layer causing the issue.

Core point: **placing MultipartFilter before springSecurityFilterChain makes tokens in the multipart body available early, yet also allows the body to be parsed prior to security checks**. Sending the token via header avoids that dependency when clients can set headers; every design must include appropriate upload and resource controls.

# Protecting File Download Paths, Static Resources, and Forwarded Views in Spring Security Servlet + Spring MVC

## 1. Objectives and Practical Scenario

A Spring MVC application typically has three kinds of paths:

- `/assets/app.css`, `/assets/logo.svg`: **public** static resources required for the login page and UI to function.
- `/api/files/{id}/download`: documents belonging to **a specific user or organization**, downloadable only when authenticated **and** owning or authorized to read the document.
- `/reports/summary` returning `forward:/internal/report-view`: an internal navigation URL dispatching to another handler/view that may still handle sensitive data.

A common mistake is allowing all `GET` requests, all `/static/**`, or all `DispatcherType.FORWARD` dispatches and assuming the MVC controller alone is safe enough. In reality, multiple independent layers must be controlled: **Spring Security URL authorization**, **MVC handler/resource mapping**, **object-level authorization**, **Servlet dispatcher types**, **filesystem/storage boundaries**, and **HTTP response headers/caching**.

One guiding principle throughout this lesson:

> **Whether a path is reachable from a browser does not determine whether the data is public. Only resources explicitly classified as public should receive `permitAll()`; private documents must enforce permissions at both the URL and object levels, and forwarded views must never create a bypass around authorization.**

This lesson targets **Spring Security 6, Spring Boot 3.3.5, Java 17, and the Servlet stack**. All code blocks are marked as complete files or illustrative snippets; the demo uses HTTP Basic and in-memory data for easy observation, not a production document storage system.

## 2. Which Components Does a Request Traverse?

In a Servlet application, a request passes through the **filter chain** before Spring MVC selects a controller or static resource handler:

~~~text
Browser
  |
  | GET /api/files/alice-budget/download
  v
Servlet container
  |
  v
DelegatingFilterProxy
  |
  v
Spring Security FilterChainProxy / SecurityFilterChain
  |-- SecurityContext
  |-- Authentication (if needed)
  |-- AuthorizationFilter (path rules)
  |
  v
DispatcherServlet (Spring MVC)
  |
  +-- RequestMappingHandlerMapping -> @Controller/@RestController
  |                                    -> check document ownership
  |                                    -> return ResponseEntity<Resource>
  |
  +-- ResourceHandlerMapping -> ResourceHttpRequestHandler
  |                            -> public images, CSS, JavaScript
  |
  +-- ViewResolver -> JSP/Thymeleaf/InternalResourceView
                               -> may trigger FORWARD
~~~

Do not assume `ResourceHttpRequestHandler` only serves safe resources; **it serves whatever you place inside mapped directories or locations**. If private documents live inside a public static path, an unauthorized user can download them without ever hitting an ownership-checking controller.

`authorizeHttpRequests` can permit or deny URLs before MVC. However, it is only the first layer: two documents under `/api/files/**` do not automatically share the same owner. Therefore, `hasRole("FILE_READER")` alone is insufficient to protect `/api/files/bob-budget/download` from Alice if Alice also holds `FILE_READER`.

## 3. Classify URLs Before Writing Request Matchers

Start with an **explicit classification table**, not `permitAll("/**")` followed by patching exceptions as bugs appear.

| Path | Category | Sound Security Decision |
| --- | --- | --- |
| `/assets/**` | Inventoried CSS/JS/images, genuinely public | `permitAll()` while still routing requests through the Spring Security filter chain |
| `/api/files/{id}/download` | Private application-managed files | Authentication + minimum role + **object-level ownership/ACL** |
| `/reports/**` | Sensitive reporting endpoints | Role/business authorization, not merely `authenticated` |
| `/internal/report-view` | Target handler/view of `forward:` | Protect the target path as well and/or add method-level checks |
| `/error` | Non-secret error page/response | May permit to avoid nested errors, but never disclose data |
| `/login` | Application login page | Allow access before login; preserve CSRF on submit |
| `/admin/**`, `/private/**` | Sensitive endpoints/resources | Specific role or `denyAll()` if no valid route exists |
| Undeclared URLs | No public requirement | Default `denyAll()` |

**`permitAll()` does not mean "skip Spring Security filters".** With `permitAll()`, the request still passes through the filter chain per the active configuration, giving security headers and other filters a chance to run. Conversely, `web.ignoring()` or excluding the filter chain bypasses those controls, which is usually **unnecessary** just to speed up static resources.

Never assume a file placed in a directory named `private` is automatically access-controlled. Rules must rest on the **actual locations served by Spring MVC, the web server, and CDNs**, plus any alternate paths or aliases.

## 4. Static Resources in Spring Boot: What Is Public?

Spring Boot MVC normally searches for static resources in default classpath locations such as `/static`, `/public`, `/resources`, and `/META-INF/resources`; depending on configuration, public URLs may be mapped under `/**`. For example, placing `salary.csv` inside `src/main/resources/static` makes it **unsafe for secret files**, even if you expect a controller to check permissions at `/api/files/**`: the file may still be served directly under another URL.

Separate locations clearly:

~~~text
src/main/resources/
  public-assets/
    app.css                 <- exposed via /assets/**
  templates/
    login.html              <- server-rendered template, not static public
  private-documents/
    internal-note.txt       <- not statically mapped, classification example only

/srv/application/private-files/
  ...                       <- stored outside web root; accessed only via controller
~~~

The demo application **disables Spring Boot's default static mappings** and declares a narrow `/assets/**` mapping. That makes public assets explicit; not every project is required to do this if default configurations and location contents are strictly controlled.

~~~properties
# application.properties
spring.web.resources.add-mappings=false
spring.security.filter.dispatcher-types=request,async,error,forward
server.error.include-message=never
~~~

Here `spring.web.resources.add-mappings=false` disables Boot's auto-registered static mappings, while mappings registered explicitly via `WebMvcConfigurer` remain active. The `spring.security.filter.dispatcher-types` property declares which Servlet dispatcher types the **Spring Security filter** handles in this example, including `FORWARD`. Forwarding behavior also depends on the container, filter registration, and deployment setup; verify it with container integration tests if your application relies on securing secondary dispatches.

A `WebMvcConfigurer` can declare the allowed directory to serve:

~~~java
@Bean
WebMvcConfigurer publicResources() {
    return new WebMvcConfigurer() {
        @Override
        public void addResourceHandlers(
                ResourceHandlerRegistry registry) {
            registry.addResourceHandler("/assets/**")
                    .addResourceLocations("classpath:/public-assets/");
        }
    };
}
~~~

This is a **Java snippet inside a Spring Configuration class**, not a standalone program. `ResourceHttpRequestHandler` serves resources from that location. **Never** add `file:/srv/application/private-files/` to a `permitAll()` mapping: doing so turns private files into public static resources.

Public assets still require source governance: never mix user uploads into the same directory, configure proper content types and security headers, and manage versioning/caching on release. An untrusted SVG/HTML/JavaScript file can create XSS risk if served from the application's own origin; do not judge risk merely by calling it "a static file".

## 5. Private File Downloads: Authentication, Authorization, and IDOR

A `GET /api/files/{id}/download` URL typically needs three layers of verification:

1. **Identity:** Is the caller authenticated? For example, HTTP Basic or session confirms Alice.
2. **Coarse authorization:** Is the caller allowed to use the download feature? For example, `ROLE_FILE_READER`.
3. **Object-level authorization:** Does the document with `id` belong to Alice or to a tenant/group Alice is authorized to access?

Without step 3, guessing an ID or swapping `id` in the URL yields an **Insecure Direct Object Reference (IDOR)** / Broken Object Level Authorization (BOLA) vulnerability.

Example:

~~~http
GET /api/files/alice-budget/download HTTP/1.1
Authorization: Basic <credential-example>
~~~

Alice holds `FILE_READER`, and `alice-budget` belongs to Alice: returning 200 is valid. Yet with the exact same credentials:

~~~http
GET /api/files/bob-budget/download HTTP/1.1
Authorization: Basic <credential-example>
~~~

The server must deny the request. In our example, it returns **404 Not Found** for both nonexistent files and existing files not owned by the caller; real apps may choose 403 per policy, while avoiding error messages that help enumerate other users' IDs or filenames.

**Never use a client-supplied file path as authorization.** Dangerous example:

~~~java
// UNSAFE: client-controlled input can contain ../
Path requested = Path.of("/srv/private").resolve(filenameFromUrl);
return new FileSystemResource(requested);
~~~

A request such as `/download?name=../../secrets/config.yml`, URL-encoded traversal, or symlinks can trick the backend into reading outside the intended directory. A safer approach:

- Requests send only an **opaque document ID** (typically a UUID, containing no path).
- The server looks up metadata for that ID from the database; metadata holds owner/tenant, visibility, status, and storage key.
- Enforce ACL/ownership from that verified metadata against the current user.
- Fetch bytes from storage using a **server-managed storage key**, never converting client filenames/URLs directly into a `Path`.
- If filesystem storage is unavoidable, verify real paths and root containment (including symlinks), mitigate TOCTOU races, and restrict OS permissions. Use dedicated object storage with application-managed keys where appropriate.

UUIDs do not replace authorization. Hard-to-guess IDs reduce enumeration risk, but offer no protection if a URL leaks via logs, emails, or browser history.

## 6. File Download Responses Are Also a Security Surface

After passing authorization, the response itself must be controlled:

~~~http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="alice-budget.txt"
Cache-Control: no-store
X-Content-Type-Options: nosniff

Private data...
~~~

`Content-Disposition: attachment` instructs browsers to **download** rather than render inline; `filename` must be built with an HTTP library's escaping/encoding API, never concatenated from untrusted input. `application/octet-stream` suits generic downloads; if safe inline PDF/image previews are needed, design separate routes and headers.

`Cache-Control: no-store` limits sensitive caching in browsers and proxies; with CDNs, add explicit configuration so private resources are never cached by mistake. `X-Content-Type-Options: nosniff` reduces certain content-type sniffing risks. Never rely on headers alone when handling untrusted HTML/SVG content: consider a **separate origin for user-generated content**, malware scanning, content-type restrictions, non-executable storage, and never serving uploads from the public web root.

**Never return `ResponseEntity<Resource>` without checking ownership**, and never redirect to a long-lived public storage URL. With object storage, a **presigned URL** acts as a bearer credential: anyone holding the URL while it remains valid can download the content, so verify permissions before issuing it, set an appropriately short TTL, restrict allowed operations, and remember that a time-limited URL is **not automatically single-use**.

Note that `HEAD`, `Range`, cache revalidation, and preview endpoints can also be used to access content. Where supported, enforce the exact same authentication/ownership rules; never protect `GET` in one handler while leaving another static mapping serving the same file.

## 7. View Forwarding Differs from Redirect: Protect the Target Too

In Spring MVC, a controller can return:

~~~java
return "forward:/internal/report-view";
~~~

This is a **server-side forward** via Servlet `RequestDispatcher`, not the browser requesting a new URL. It creates an internal dispatch to the target path inside the server. Conversely:

~~~java
return "redirect:/reports/home";
~~~

`redirect:` returns an HTTP 3xx status so the browser issues a **new request** to the target URL; security filters for the new request execute normally. Meanwhile, rendering a template directly (like `return "dashboard"` with Thymeleaf) does not necessarily trigger a new Servlet request. Identify which mechanism your application uses.

### 7.1. Why Can FORWARD Create a Vulnerability?

Suppose `/reports/summary` requires `ROLE_ANALYST` and then forwards to `/internal/report-view`. If only the source path is protected, a direct request to `/internal/report-view` may bypass access control if the target URL is broadly permitted.

In Servlets, `DispatcherType` typically includes `REQUEST`, `FORWARD`, `INCLUDE`, `ERROR`, and `ASYNC`. Spring Security's `AuthorizationFilter` evaluates dispatcher types routed into the Security chain by filter registration; if a dispatcher type is not registered for Spring Security's filter, **do not assume the filter will re-run** on that dispatch.

Defense-in-depth approach:

- Protect the **source URL** (`/reports/**`) so only authorized users can initiate the report.
- Protect the **target URL** (`/internal/**`) in case it can be requested directly.
- On target handlers processing sensitive data, add **method-level authorization** or service-level ACLs instead of relying solely on filters re-running during FORWARD.
- If the target path should only be reached via forward, check **`DispatcherType.FORWARD`** in the target handler to block direct requests. This is an extra guard, **not a replacement for role checks**.
- Verify behavior with real container tests configured with the corresponding dispatcher types.

### 7.2. Do Not Unconditionally `permitAll(FORWARD)` When Sensitive Data Is Involved

You may see configurations like:

~~~java
// Snippet may suit certain applications;
// DO NOT use by default with sensitive forwards.
auth.dispatcherTypeMatchers(DispatcherType.FORWARD).permitAll();
~~~

This may be needed in systems whose view/error forwards already completed full authorization on the initial request. However, if a sensitive handler is invoked via forward from elsewhere, **skipping authorization for every FORWARD** drops a protective layer. Evaluate each path, isolate internal endpoints, and/or enforce method security on target handlers.

`DispatcherType.ERROR` is sometimes permitted to render error pages without triggering security loops, yet **error pages must never display private data**. For forward and error dispatches, never apply overly broad rules just to make a test "stop returning 403" before finding the root cause.

JSP's `/WEB-INF` directory is normally blocked from direct static access by the container, but **that is not a per-user/per-tenant authorization system**. A controller passing sensitive data to a JSP must still verify permissions before rendering. `forward:`, `include`, view resolvers, and templating engines do not automatically keep data confidential.

## 8. Runnable Example: Spring Boot 3.3.5, Java 17

Demo goals:

1. Only `/assets/**` contains public resources; Boot's default static mappings are disabled.
2. `/api/files/**` requires `ROLE_FILE_READER`; documents must also belong to the caller.
3. `/reports/**` and `/internal/**` require `ROLE_ANALYST`.
4. `forward:/internal/report-view` is a server-side dispatch; the target handler enforces **`@PreAuthorize`** and checks the dispatcher type.
5. All other paths hit `denyAll()`. HTTP Basic is used for demo convenience; `{noop}` passwords are a learning fixture only, never for production.
6. Demo files are small server-owned `byte[]` payloads rather than real uploads or external storage. This keeps the example filesystem-independent and is not a pattern for serving large files.

### 8.1. Structure

~~~text
protected-mvc-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/resources/public-assets/app.css
  src/main/java/example/protectedmvc/ProtectedMvcApplication.java
  src/test/java/example/protectedmvc/ProtectedMvcTests.java
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
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>protected-mvc-demo</artifactId>
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

**src/main/resources/application.properties**:

~~~properties
spring.web.resources.add-mappings=false
spring.security.filter.dispatcher-types=request,async,error,forward
server.error.include-message=never
~~~

**src/main/resources/public-assets/app.css**:

~~~css
body {
    font-family: sans-serif;
    margin: 2rem;
}
~~~

### 8.2. Security Configuration, Download Controller, and Forward

**src/main/java/example/protectedmvc/ProtectedMvcApplication.java**:

~~~java
package example.protectedmvc;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Optional;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.stereotype.Controller;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
@EnableMethodSecurity
public class ProtectedMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProtectedMvcApplication.class, args);
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-password")
                        .roles("FILE_READER").build(),
                User.withUsername("bob")
                        .password("{noop}demo-password")
                        .roles("FILE_READER").build(),
                User.withUsername("analyst")
                        .password("{noop}demo-password")
                        .roles("ANALYST").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**", "/error").permitAll()
                        .requestMatchers("/api/files/**")
                            .hasRole("FILE_READER")
                        .requestMatchers("/reports/**", "/internal/**")
                            .hasRole("ANALYST")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    WebMvcConfigurer publicResources() {
        return new WebMvcConfigurer() {
            @Override
            public void addResourceHandlers(
                    ResourceHandlerRegistry registry) {
                registry.addResourceHandler("/assets/**")
                        .addResourceLocations(
                                "classpath:/public-assets/");
            }
        };
    }

    @Bean
    FileCatalog fileCatalog() {
        return new FileCatalog();
    }

    record StoredFile(
            String owner, String downloadName, byte[] bytes) {}

    static final class FileCatalog {
        private final Map<String, StoredFile> files = Map.of(
                "alice-budget", new StoredFile(
                        "alice",
                        "alice-budget.txt",
                        "Budget for Alice\n".getBytes(
                                StandardCharsets.UTF_8)),
                "bob-budget", new StoredFile(
                        "bob",
                        "bob-budget.txt",
                        "Budget for Bob\n".getBytes(
                                StandardCharsets.UTF_8)));

        Optional<StoredFile> find(String id) {
            return Optional.ofNullable(files.get(id));
        }
    }

    @RestController
    static class FileController {
        private final FileCatalog catalog;

        FileController(FileCatalog catalog) {
            this.catalog = catalog;
        }

        @GetMapping("/api/files/{id}/download")
        ResponseEntity<ByteArrayResource> download(
                @PathVariable String id, Authentication auth) {
            StoredFile file = catalog.find(id).orElseThrow(() ->
                    new ResponseStatusException(HttpStatus.NOT_FOUND));

            // BOLA/IDOR: valid role must still match the owner.
            if (!file.owner().equals(auth.getName())) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }

            String disposition = ContentDisposition.attachment()
                    .filename(file.downloadName(), StandardCharsets.UTF_8)
                    .build().toString();

            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .contentType(MediaType.APPLICATION_OCTET_STREAM)
                    .contentLength(file.bytes().length)
                    .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                    .body(new ByteArrayResource(file.bytes()));
        }
    }

    @Controller
    static class ForwardController {

        @GetMapping("/reports/summary")
        String summary() {
            // Uses RequestDispatcher FORWARD, not a 302 redirect.
            return "forward:/internal/report-view";
        }
    }

    @RestController
    static class InternalReportController {

        @PreAuthorize("hasRole('ANALYST')")
        @GetMapping("/internal/report-view")
        ResponseEntity<String> render(HttpServletRequest request) {
            // Role check independent of whether the filter re-runs on FORWARD.
            if (request.getDispatcherType() != DispatcherType.FORWARD) {
                // Even when an analyst is logged in, disallow direct calls to the target view.
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }
            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body("Internal report for analysts");
        }
    }
}
~~~

**Each important protective layer:**

- `requestMatchers("/assets/**").permitAll()`: permits only inventoried public CSS/images/JS, never `/**`.
- `requestMatchers("/api/files/**").hasRole("FILE_READER")`: blocks callers without the file-download capability before MVC.
- `FileController`: looks up a server-known ID and checks `file.owner().equals(auth.getName())`; Alice cannot read Bob's file even though both hold `ROLE_FILE_READER`.
- `ResponseEntity<ByteArrayResource>`: sets `Content-Disposition: attachment`, `Content-Type: application/octet-stream`, and `Cache-Control: no-store`. For large files, switch to streaming and a secure storage layer.
- `requestMatchers("/reports/**", "/internal/**").hasRole("ANALYST")`: protects both source and target URLs at the HTTP layer. When a `FORWARD` dispatcher enters the Security chain, it is checked too.
- `@EnableMethodSecurity` and `@PreAuthorize("hasRole('ANALYST')")`: the target handler enforces authorization **independently** of whether the filter runs a second time on forward.
- Checking `DispatcherType.FORWARD` blocks direct calls to `/internal/report-view` even for authorized callers. This check **cannot** stand alone instead of `@PreAuthorize`: an attacker might abuse other forward routes if application code has a bug.
- `anyRequest().denyAll()`: undeclared paths are denied, preventing unintended static resource exposure via auto-mapping.
- `{noop}` and `InMemoryUserDetailsManager` are demo fixtures only; production requires properly hashed credentials, account status checks, and role management from DB/IdP.

`httpBasic` is chosen only for easy `curl` testing; session-based form login still requires appropriate CSRF, session, cookie, logout, and authentication policies. `GET` must never cause business state mutations; the example has no POST/DELETE endpoints, so CSRF in the download flow is not demonstrated here.

### 8.3. Testing with curl

From `protected-mvc-demo`, requiring JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
# Public CSS; no credentials required.
curl -i http://localhost:8080/assets/app.css

# Unauthenticated private file: 401 via HTTP Basic.
curl -i http://localhost:8080/api/files/alice-budget/download

# Correct file owner: 200 and download headers.
curl -i -u alice:demo-password \
  http://localhost:8080/api/files/alice-budget/download

# Logged in, same role, but not owner: 404.
curl -i -u bob:demo-password \
  http://localhost:8080/api/files/alice-budget/download

# Missing ROLE_ANALYST: 403.
curl -i -u alice:demo-password \
  http://localhost:8080/reports/summary

# Valid ROLE_ANALYST: 200 with content from forwarded handler.
curl -i -u analyst:demo-password \
  http://localhost:8080/reports/summary

# Direct call to FORWARD target: 404 per handler.
curl -i -u analyst:demo-password \
  http://localhost:8080/internal/report-view
~~~

A successful file response has body `Budget for Alice` and typically includes `Content-Disposition: attachment` and `Cache-Control: no-store`. The report response has body `Internal report for analysts`. With HTTP Basic, authentication failures typically return 401 while authenticated callers lacking a role return 403. In deployments with `/error` or proxies involved, error bodies and headers may differ, yet the **access decision** must remain intact.

### 8.4. Why Not Use `file:/srv/private/` in ResourceHandler?

You could write:

~~~java
// Do not do this for private documents just because /api/files/** also exists.
registry.addResourceHandler("/downloads/**")
        .addResourceLocations("file:/srv/private/");
~~~

When Spring MVC handles `/downloads/**`, it does not automatically call `FileController` to verify per-file ownership. If Security has `permitAll("/downloads/**")` or another proxy exposes that location, object-level protection is completely bypassed. For confidential files, routes must enforce **identity + ACL + controlled streaming** or issue presigned URLs after authorization, never relying on a static resource handler.

## 9. MockMvc Tests: Separating Public Assets, File Ownership, and Forwarding

Add **src/test/java/example/protectedmvc/ProtectedMvcTests.java**:

~~~java
package example.protectedmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProtectedMvcTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicAssetIsAvailableWithoutLogin() throws Exception {
        mvc.perform(get("/assets/app.css"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("font-family")));
    }

    @Test
    void privateFileRequiresLogin() throws Exception {
        mvc.perform(get("/api/files/alice-budget/download"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanDownloadPrivateFile() throws Exception {
        mvc.perform(get("/api/files/alice-budget/download")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("Budget for Alice\n"))
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(header().exists(
                        HttpHeaders.CONTENT_DISPOSITION));
    }

    @Test
    void sameRoleCannotDownloadAnotherPersonsFile()
            throws Exception {
        mvc.perform(get("/api/files/alice-budget/download")
                        .with(httpBasic("bob", "demo-password")))
                .andExpect(status().isNotFound());
    }

    @Test
    void nonAnalystCannotEnterReport() throws Exception {
        mvc.perform(get("/reports/summary")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void analystCanInitiateProtectedForward() throws Exception {
        mvc.perform(get("/reports/summary")
                        .with(httpBasic("analyst", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(forwardedUrl("/internal/report-view"));
    }

    @Test
    void analystCannotCallInternalTargetDirectly()
            throws Exception {
        mvc.perform(get("/internal/report-view")
                        .with(httpBasic("analyst", "demo-password")))
                .andExpect(status().isNotFound());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

These tests verify that **public CSS requires no login**, private files require login, the **owner** can download while another user with the same role cannot, the analyst role permits initiating the forward, and the internal target URL rejects direct requests.

**Important limitation:** asserting `forwardedUrl(...)` in MockMvc here confirms MVC returned a forward instruction, **not that a real Servlet container executed an actual FORWARD dispatch with full filter registration**. Add tests against a real embedded server (e.g., `@SpringBootTest(webEnvironment=RANDOM_PORT)` + an HTTP client) to prove the forwarded handler's body is only returned to analysts and to exercise auth checks on forwarded requests. Testing `/internal/report-view` directly verifies direct-access blocking, not full container forward behavior.

### 9.1. Additional Tests Needed for Real File Applications

- Users with the same role but different tenants/owners, nonexistent files, malformed IDs, and revoked or unshared documents.
- `../`, encoded slashes, double encoding, unusual URL paths, Unicode filenames, and special characters.
- `HEAD`, `Range`, cache-revalidation requests, and preview routes if supported.
- Symlinks, path escaping, file renames between check and open, and data outside the storage root.
- `GET`/`HEAD` on static assets, ensuring no private folders exist under `classpath:/public-assets/`.
- Direct `REQUEST` to internal URLs, real `FORWARD`, and `ERROR` dispatches when target routes throw errors.
- Multiple `SecurityFilterChain`s, multiple servlet paths, or reverse proxy rewrites; request matchers must match the final effective URL.
- Cache/CDN isolation ensuring User A's documents are never served to User B, even after logout or account switching.

## 10. If Files Live on Disk: Check Root, Symlinks, and OS Permissions

In the demo, files are stored as `byte[]`. For real files, obtain only **storage-relative paths from a database after verifying permissions**. Never use paths from request input. An **illustrative** boundary-check helper:

~~~java
// Java snippet inside storage service, not a standalone class.
static Path resolveApprovedFile(
        Path configuredRoot, String storedRelativePath)
        throws IOException {

    Path realRoot = configuredRoot.toRealPath();
    Path realFile = realRoot.resolve(storedRelativePath).toRealPath();

    if (!realFile.startsWith(realRoot)
            || !Files.isRegularFile(realFile)) {
        throw new FileNotFoundException("Not found");
    }

    return realFile;
}
~~~

Requires importing `java.nio.file.Path`, `java.nio.file.Files`, `java.io.IOException`, and `java.io.FileNotFoundException`. `toRealPath()` resolves symbolic links and canonicalizes paths; comparing with `Path.startsWith(Path)` (by path segment) differs from `String.startsWith`, avoiding mistaking `/srv/private2` as sitting under `/srv/private`. If a file is symlinked outside the root, its real path escapes the root and is rejected.

However, **this alone does not completely eliminate TOCTOU** if another actor can alter symlinks/paths between the check and opening the file. Production storage should restrict OS write permissions, avoid untrusted shared directories, use file descriptors/secure directory operations where needed, or adopt well-designed storage key / object APIs. The core rule remains **lookup ID -> ACL -> resolve internal storage key -> open/stream**, never `Path.of(userInput)`.

Never serve large files by loading them completely into RAM like the demo's `ByteArrayResource`; use streaming/`Resource`, quotas, and concurrency limits. For uploads and previews, also enforce MIME restrictions, size/count limits, malware scanning, safe naming, and isolation of user-controlled content.

## 11. MvcRequestMatcher, Paths, and Multiple Servlets

In Spring Security 6 Servlet with Spring MVC present, `authorizeHttpRequests().requestMatchers("/...")` normally uses MVC-compatible matching when `HandlerMappingIntrospector` is available. What matters is **the actual path observed by Security**, not just the string shown in the browser:

- Is `server.servlet.context-path` or a custom servlet path configured? Matchers may require corresponding setup; never arbitrarily prepend the context path to matcher patterns.
- Are there multiple `DispatcherServlet`s or other servlets in the same app? Use MVC matchers only within the appropriate MVC scope; you may need to specify the servlet path/builder explicitly.
- Does a proxy rewrite URLs or add `X-Forwarded-*` prefixes? Configure proxy handling and trusted headers properly, never treating client-supplied paths or hosts as authorization proof.
- Are there multiple `SecurityFilterChain`s with different `securityMatcher`s? `FORWARD`, `ERROR`, static, or download requests can fall into a different chain—or no chain—if scopes are misconfigured.
- How are paths decoded/normalized at the container and MVC layers? Encoded slashes, semicolons/matrix variables, and trailing slashes must be tested on the real container rather than relying on hand-written regexes.

For multiple servlet paths, you can use `MvcRequestMatcher.Builder` with `HandlerMappingIntrospector` to specify the servlet path explicitly. This is a **suggested snippet to adapt to your app**, not a drop-in replacement for section 8's complete config:

~~~java
MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(introspector)
                .servletPath("/mvc");

http.authorizeHttpRequests(auth -> auth
        .requestMatchers(mvc.pattern("/api/files/**"))
            .hasRole("FILE_READER")
        .anyRequest().denyAll());
~~~

Your app must import `org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher` and inject `HandlerMappingIntrospector`. **Do not copy `/mvc` literally** if your application does not use that servlet path.

Avoid overly broad or overly narrow security matchers. File download paths might exist across `/download/**`, `/api/files/**`, `/static/uploads/**`, or CDNs; **inventory every access path to the same resource** before declaring protection complete.

## 12. Special Risks of Forward, Include, and Error Views

### 12.1. Forward

`forward:/...` runs server-side and can change the path seen by filters and handlers. Even if the source controller performs some checks, the target must still be protected if it can be called directly or reached via another forward path. For specific documents or tenants, a coarse role is insufficient: the handler or service must enforce permissions based on the data being rendered.

### 12.2. Include

A JSP or controller can **include** content from another component inside the same response. Depending on dispatcher registration, security filters may not run like a fresh `REQUEST` on `DispatcherType.INCLUDE`. Never put sensitive data into a fragment that any handler can include without service/view-model authorization checks. Guard by business data, not solely by JSP filename.

### 12.3. Error

An exception can trigger an `ERROR` dispatch to `/error`. If the error view accidentally prints stack traces, request attributes, session details, or data from a private route, `permitAll("/error")` stops being harmless. Use minimal error pages, omit secrets/PII from messages, and configure safe error rendering.

### 12.4. Redirect

`redirect:` returns 302/303/307... telling the browser to request another URL. The new request must be authorized by the target route; never assume that because a user could call the redirecting route they are authorized for the target. Prevent **open redirects** by redirecting only to application-allowlisted paths or hosts.

### 12.5. View Templates and Data

With Thymeleaf, FreeMarker, Mustache, or JSP, placing a template in a non-directly-accessible folder does not secure the data placed in its model. Check **ownership/tenant/role before populating the model**, not only after rendering or by hiding buttons/links in the frontend. Frontend menu hiding is not a security control.

## 13. Common Mistakes and Fixes

| Mistake | Why Is It Dangerous? | Fix |
| --- | --- | --- |
| `permitAll("/**")` hoping controllers block requests | Overly permissive; new routes slip through | Narrow public allowlist, `anyRequest().denyAll()` |
| `web.ignoring("/static/**")` for all resources | Skips the Security filter chain and may drop security headers | Prefer `permitAll()` for public assets |
| Putting private files in `resources/static` | Downloadable via other public URLs, bypassing controllers | Move out of static root; expose only via ACL controller |
| Relying solely on `hasRole("FILE_READER")` | Same-role users can download others' files | Enforce ownership/tenant/ACL per document ID |
| Concatenating client `filename` into `Path` | Path traversal and symlink escape | Opaque ID -> server-side key, realpath/OS storage safety |
| Trusting UUIDs as sufficient security | IDs can leak; unguessable is not authorization | Enforce auth + ACL on every request |
| `forward:` to a `permitAll` URL with sensitive data | Bypasses target authorization via alternate route | Protect source, target, and method/service |
| Unconditional `dispatcherTypeMatchers(FORWARD).permitAll()` | Loses control layer on forwarded endpoints | Evaluate each path; add method security on sensitive targets |
| Testing `forwardedUrl` and claiming the filter re-ran | MockMvc does not prove real container forward dispatch | Embedded servlet integration tests |
| Sharing CDN/cache for private files | Can leak data across users or tenants | `Cache-Control` private/`no-store`, partition keys, signed URL policy |
| String-concatenating filename in `Content-Disposition` | Header injection and broken filename encoding | Use builder API, encoding/escaping, and filename allowlists |
| Mapping `file:/private` in `ResourceHttpRequestHandler` | Static handlers know nothing about ownership | Use an ACL-enforcing controller or auth-gated signed URLs |
| Public error view containing data | Leaks stack traces/models/PII via error dispatch | Minimal error responses; never log tokens |
| Treating forward and redirect as identical | Confuses internal dispatchers with browser request boundaries | Test servlet dispatch vs. browser 3xx separately |
| Ignoring `HEAD`, `Range`, or preview routes | Leaves alternate file-read paths unprotected | Apply the same ACL across all read paths |
| Security matcher missing the real servlet path | Requests can fall into the wrong chain | Verify `HandlerMappingIntrospector`, servlet path, and proxy |

**When debugging 401/403/404**, determine whether the error comes from a Spring Security filter, MVC handler, ownership check, or storage. In our demo, another user's file intentionally returns 404; this does not mean the document does not exist. Conversely, a static 404 may mean the resource handler lacks a mapping or file, not an authentication issue.

## 14. Production Verification Workflow

1. **Map paths and storage.** Document all GET/HEAD/Range URLs, controllers, static handlers, view resolvers, proxy/CDN routes, and actual data locations.
2. **Classify data.** Separate public CSS/JS/images from private uploads, exports, invoices, reports, temporary files, and ticket attachments.
3. **Create a public allowlist.** Grant `permitAll` only to `/assets/**` or trusted locations; require roles and deny-by-default everywhere else.
4. **Enforce per-object permissions.** For each file ID, look up owner, tenant, visibility, and ACL on the backend. Verify disabled/revoked accounts.
5. **Check storage boundaries.** Keep private files outside the web root; use server-managed paths, prevent traversal/symlinks, and restrict OS permissions.
6. **Verify response headers and caching.** Check `Content-Disposition`, `Content-Type`, `nosniff`, `no-store`, referrer/URL leakage, and CDN policies.
7. **Audit forward/include/error flows.** For each internal route, verify source/target URLs, dispatcher registration, method security, and views that never leak model data.
8. **Write role- and owner-based tests.** Test anonymous callers, wrong roles, rightful owners, same-role non-owners, missing documents, special paths, and direct vs. indirect forwards.
9. **Test with a real container and proxy.** MockMvc is helpful, but does not replace verifying real `FORWARD`/`ERROR` dispatches, headers/caching, and URL rewrites in production-like setups.
10. **Track changes.** Whenever adding a static location, controller, servlet mapping, or CDN rule, update your threat model and authorization tests.

Never log passwords, bearer tokens, session cookies, presigned URLs, or full sensitive paths in error reports. For auditing, log identity, internal document ID, action type, and access outcome (per security policy), avoiding file contents.

## 15. Self-Check Exercises

**Q1.** Alice has `ROLE_FILE_READER`; should she be able to call `/api/files/bob-budget/download`?  
**No.** Per-file ACL/ownership is required; the role is only an initial check.

**Q2.** If a confidential file lives in `src/main/resources/static`, is protecting `/api/files/**` enough?  
**No.** A public static handler URL may still serve it. Move the file out of public locations and audit every access path.

**Q3.** Why is `permitAll("/assets/**")` usually better than `web.ignoring("/assets/**")`?  
**Because** static requests still pass through the Security filter chain, preserving security headers and related policies without requiring login.

**Q4.** When `/reports/summary` forwards to `/internal/report-view`, which path needs protection?  
**Both source and target**, especially if the target can be accessed directly. Method/service-level authorization protects data right at the handler.

**Q5.** Does `MockMvc.andExpect(forwardedUrl(...))` prove a real Servlet `FORWARD` dispatch was re-checked by Security filters?  
**No.** Real container integration tests with matching dispatcher registration are needed.

**Q6.** Why is `DispatcherType.FORWARD` not an authorization condition?  
**Because** it only describes how the request was dispatched, not whether the user holds the role or permission for the data.

**Q7.** A client sends `?path=../../etc/passwd`; should you do `Path.of(root).resolve(path)` and return the file?  
**No.** Use opaque IDs, server-side metadata + ACLs, traversal/symlink guards, and keep private storage outside the web root.

**Q8.** Does `Content-Disposition: attachment` replace authorization?  
**No.** It only hints to the browser how to handle a response after the server has already decided to return the content.

**Q9.** Is a presigned URL with a 10-minute TTL single-use by default?  
**No.** Anyone holding the URL can reuse it within the TTL per storage rules; enforce permissions before issuing it and understand bearer semantics.

**Q10.** Files can be read via `GET`, `HEAD`, and `Range`; is testing `GET` 200/403 enough?  
**No.** Test every method, route, and read mechanism the application supports.

## 16. Takeaways

- **Public assets**: store in inventoried locations, permit a narrow `/assets/**` pattern, and keep the Spring Security filter chain and response headers active.
- **Private downloads**: **authentication + role + object-level ownership/ACL**. Never let private files leak through static resource handlers or public CDNs; never turn client input into filesystem paths.
- **Forwarded views**: understand how `FORWARD` differs from `redirect` and template rendering. Protect source and target URLs, verify dispatcher registration, add method/service security for sensitive content, and avoid blanket `permitAll(FORWARD)`.
- **File responses**: download headers, caching, content sniffing, and storage access are part of security, not just `requestMatchers`.
- **Testing**: use unit/MockMvc tests for roles, ownership, and static mappings, plus container integration tests for real `FORWARD` dispatches and proxy/storage behavior across all download paths.

**Conclusion:** In Spring Security Servlet integrated with MVC, static paths, file downloads, and forwarded views are all access surfaces requiring **explicit, verifiable authorization decisions**. URL-level rules block from the outside; controller/service ACLs protect individual objects; and storage and dispatch configurations must never open a bypass around either.

# Distinguishing Normalization, Validation, Escaping, and Authorization in Spring Framework

## 1. Objective: Four Defense Layers Answering Four Different Questions

When Spring MVC receives data from a browser, JSON API, webhook, or another application, the same string can pass through several stages. Four terms frequently conflated are **normalization**, **validation**, **escaping/encoding (context-aware output encoding)**, and **authorization**. They cannot replace one another.

For example, suppose a user submits a display name containing:

```text
  <img src=x onerror=alert(1)>  
```

When storing or rendering it, the application must answer several independent questions:

- Does the data have leading/trailing whitespace, Unicode variations, or formatting that must be **consistently normalized**?
- Are the length, type, characters, or business rules **acceptable**?
- When rendering the name into HTML, could the browser interpret it as HTML/JavaScript code rather than plain text? That is the responsibility of **escaping/encoding at the output sink**.
- Is the sender genuinely **authorized to edit the profile with this ID**? That is the responsibility of authentication/authorization.

**A syntactically valid string can still cause XSS when placed into unescaped HTML; an escaped string can still belong to another user's account; an authenticated user still may not modify arbitrary resources.**

This lesson uses Java 17+, Spring Boot 3.5.x, Spring MVC, Jakarta Bean Validation, Spring Security, and Thymeleaf to clarify ordering, scope, checkpoints, and common security traps. This is not a guide for deploying a full production system; the illustrative example uses in-memory users and binds only to loopback.

## 2. Quick Comparison Table

| Layer | Question | Example | Primary timing | Cannot replace |
| --- | --- | --- | --- | --- |
| **Normalization** | "Is the same value represented consistently?" | `strip()` whitespace, Unicode NFC, identifier canonicalization | Before comparisons/validation requiring a uniform representation | Does not block XSS, SQL injection, or unauthorized access |
| **Validation** | "Does the value conform to the contract and business rules?" | `@NotBlank`, `@Size`, `@Email`, range checks | After parsing/binding and after designed normalization | Does not verify ownership; does not encode output |
| **Escaping/encoding** | "Is the data represented safely for **this output context**?" | Thymeleaf `th:text` for HTML text; JSON serializer for JSON | Right before inserting data into HTML/JS/URL/CSS/SQL sinks via the right API | Does not make input valid or authorize operations |
| **Authorization** | "Does the current principal have permission for this action on this resource/field?" | Ownership/tenant check, `@PreAuthorize`, policy service | Before reading sensitive info or mutating state | Does not validate format and does not prevent XSS |
| **Authentication** (paired with authorization) | "Who is the caller?" | Session login, OIDC, access token | Before authorization | Being logged in does not grant every permission |

For SQL, the primary defense is not HTML escaping but **parameterized queries/prepared statements**. For rich HTML that users are permitted to author, a separate layer is **HTML sanitization** using a dedicated library; it likewise does not replace authorization.

## 3. Practical Processing Chain in Spring MVC

For a form bound with `@ModelAttribute`, a clear design is:

```text
HTTP request
   |
   +-- Security filter chain: authentication, coarse access checks, CSRF
   |
   v
DispatcherServlet -> HandlerMapping -> @ModelAttribute
   |
   +-- WebDataBinder: type conversion / @InitBinder / per-field normalization
   |      (bind only permitted properties)
   |
   +-- Jakarta Bean Validation / Spring Validator
   |      @NotBlank, @Size, custom constraints
   |
   v
Controller / service
   |
   +-- Authorization by owner/tenant/role/action
   |      (check specific resource, never rely on hidden fields)
   |
   +-- Execute business logic / persist accepted data
   |
   v
View template / JSON serializer / other sinks
   |
   +-- Context-appropriate encoding/escaping on output
   v
HTTP response
```

This is a **responsibility model**, not a promise that every endpoint executes in that exact sequential order. Spring Security can reject a request before MVC runs; `@PreAuthorize` checks before the service method body runs; validation can execute via `@Valid`/`@Validated` or method validation. With `@RequestBody` JSON, Jackson decodes the body via `HttpMessageConverter`, bypassing the `@ModelAttribute` property-binding pipeline.

**The ordering "normalization before validation" is a choice that must be implemented deliberately.** If you normalize inside the service **after** `@Valid` has already run in the controller, constraints evaluated the raw data rather than the normalized data. The complete runnable example places normalization directly in field binding so Bean Validation inspects the consistent value.

## 4. Normalization: Making Representations Consistent, Not "Sanitizing Every Risk"

### 4.1. Unicode NFC example

An accented character can have multiple Unicode representations. For instance, `é` can be a single precomposed code point, or `e` + combining acute accent.

```java
import java.text.Normalizer;

String composed = "Café";
String decomposed = "Cafe\u0301";

System.out.println(composed.equals(decomposed)); // false

String normalized = Normalizer.normalize(
    decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
```

This is an illustrative Java snippet. `java.text.Normalizer.Form.NFC` performs **canonical composition**. It lets equivalent representations be compared, validated, indexed, or cached consistently when that aligns with domain policy.

**NFC is not an XSS filter.** The string `<script>` still contains HTML-significant characters after normalization.

### 4.2. Trim/strip and semantic boundaries

`String#strip()` removes leading and trailing Unicode whitespace as defined by `Character.isWhitespace`. It does not strip all invisible characters, cannot replace a control-character policy, and does not resolve Unicode confusables on its own.

Example:

```java
public static String normalizeDisplayName(String raw) {
    if (raw == null) {
        return null;
    }
    return Normalizer.normalize(
        raw.strip(), Normalizer.Form.NFC);
}
```

This is a fragment requiring `import java.text.Normalizer`. For a "display name" domain, trimming edges and applying NFC can be sensible rules. For passwords, digital signatures, API tokens, payment codes, serialized payloads, or whitespace-significant text, **never automatically normalize or strip** unless the protocol specifies it.

### 4.3. NFKC, case folding, URL decoding, and canonicalization

- **NFC/NFD** is Unicode canonical normalization; **NFKC/NFKD** is compatibility normalization, which can erase meaningful character distinctions. Never apply NFKC blindly to every input.
- **Case folding** or `toLowerCase(Locale.ROOT)` is useful for certain case-insensitive identifiers. It is not an accurate algorithm for all languages and should not be applied indiscriminately to human names.
- **URL percent-decoding** should occur only at the appropriate protocol layer and a known number of times. Double-decoding can unexpectedly transform paths or bypass checks.
- **Path canonicalization** must verify the resolved real path lies within the permitted root directory; simply replacing `../` with an empty string is unsafe, especially with symlinks and alternate encodings.
- **File names, emails, domain names, and internationalized identifiers** each have specific standards and rules; no single magic `normalize(String)` fits all of them.

**Principle:** Pick the canonical form for each field, validate against that canonical form, and persist/compare consistently; avoid ad-hoc re-normalization across multiple layers with conflicting rules.

### 4.4. Normalization can alter validation outcomes

If a user submits:

```text
"  Alice  "
```

and the form requires a name of 1–80 characters, you must define whether leading/trailing spaces count. If policy strips whitespace, the validator should inspect `"Alice"`.

Conversely, validating the raw value before stripping can cause discrepancies in length, uniqueness, and persisted data. This rule is especially important with Unicode normalization, because UTF-16 code unit count or code point count can change.

Note that `@Size(max=80)` on `String` counts Java `CharSequence` length (typically UTF-16 code units), **not user-perceived grapheme clusters**. If business rules require bounding "visible characters," implement dedicated counting logic.

## 5. Validation: Checking the Contract, Not Authorizing Automatically

### 5.1. Bean Validation on input DTOs

```java
public class ProfileForm {

    @NotBlank
    @Size(max = 80)
    private String displayName;

    // Getters, setters, constructor...
}
```

When a form uses `@Valid @ModelAttribute("form") ProfileForm form`, Spring MVC invokes the registered validator (typically `LocalValidatorFactoryBean` when a Jakarta provider is present) to populate `FieldError`s in `BindingResult`.

- `@NotBlank` verifies the string contains at least one non-whitespace character per the constraint contract.
- `@Size(max=80)` checks maximum length.
- Custom validators can enforce reserved names, code formats, cross-field rules, or appropriate business invariants.

**Validation may legitimately accept HTML-significant characters.** A display name containing `<` and `>` does not cause XSS by itself if rendered safely; do not apply a denylist forbidding every angle bracket or accented character just to "stop XSS."

### 5.2. Syntactic, structural, semantic, business, and authorization checks

| Check type | Example | Purpose |
| --- | --- | --- |
| Syntactic | Email looks like a valid address, code matches regex | Accept meaningful formatting |
| Structural | Element counts, nested DTOs, string length, enum values | Reject malformed structures |
| Semantic | Start date is not after end date | Enforce relationships between values |
| Business | Order cannot transition out of cancelled state | Enforce domain invariants and workflows |
| Authorization | May User A edit User B's order? | **Access control—a separate layer** |

A request can pass all four initial categories and still require rejection because the sender lacks permission.

### 5.3. @Valid is not magic

- Does not tell you whether the caller owns the entity.
- Does not stop mass assignment if you bind requests straight onto a broad entity.
- Does not encode output or configure CSP.
- Does not stop SQL injection if raw strings are later concatenated into SQL.
- Does not prevent race conditions where business rules need transactions.
- Does not replace JWT/session authentication or CSRF protection.

At the web boundary, validation failures are handled via `BindingResult` or corresponding exceptions. When `BindingResult` sits immediately after the form object, the controller must check `errors.hasErrors()` before saving data; declaring `@Valid` and proceeding to save anyway is a severe bug.

### 5.4. Fail-safe validation and over-posting

An input DTO should contain only properties allowed to be updated. With property binding, `WebDataBinder#setAllowedFields(...)` adds a field-allowlist barrier; `BindingResult#getSuppressedFields()` reports suppressed fields.

When a request sends `role=ADMIN` on a form permitting only `displayName`, reject or intentionally ignore it—**never update `role` merely because the client sent it**. Use dedicated DTOs and explicit service mapping for permitted changes.

## 6. Escaping/Encoding: Protecting the Right Sink as Close to Output as Possible

### 6.1. Concept

**Output encoding** transforms data into a representation that the target context's interpreter will not treat as executable syntax. Inside an HTML text node, `<` must be encoded when needed so it displays as a literal character rather than starting a tag.

Example user value:

```text
<img src=x onerror=alert(1)>
```

When rendered safely as HTML text, the resulting HTML source looks like:

```html
&lt;img src=x onerror=alert(1)&gt;
```

The browser displays the characters `<img ...>` as text and creates no `img` element to run an event handler.

**Do not pre-store HTML-escaped strings in the database as if they were "permanently sanitized."** If you later render that value into JSON, a URL, or email, HTML text encoding is wrong for that context; even in HTML it can become double-escaped.

### 6.2. Thymeleaf th:text and th:utext

With Spring MVC server-rendered templates:

```html
<p th:text="${profile.displayName}">Example</p>
```

`th:text` outputs data with HTML escaping. Conversely:

```html
<!-- Caution: th:utext outputs unescaped HTML. -->
<p th:utext="${profile.displayName}">Example</p>
```

`th:utext` is strictly for **HTML already trusted or sanitized under an explicit policy**—never feed raw user input into it. Thymeleaf 3.1 restricts expression evaluation in dangerous contexts, yet that cannot substitute for output encoding.

In frontend JavaScript:

- Use `textContent` when inserting data into text nodes.
- Avoid `innerHTML` with untrusted strings.
- If rich HTML display is truly required, sanitize against an allowlist of tags/attributes/URLs using a vetted library (such as OWASP Java HTML Sanitizer), backed by malformed-markup tests.
- Avoid inline event-handler attributes and building scripts from data strings.

### 6.3. Specific contexts dictate specific encodings

| Sink/context | Primary handling | Why plain HTML escaping is insufficient |
| --- | --- | --- |
| HTML text node | HTML text encoding, template `th:text` | Prevents turning into tags |
| HTML attribute value | Quoted attribute + attribute encoding, template framework | Prevents breaking out of quotes / injecting attributes |
| URL path/query | Per-component URL encoding + scheme/origin validation | HTML escaping does not encode URL components |
| JavaScript literal | Safe JSON serialization for JS context or separating data from code | HTML escaping is not JS string escaping |
| CSS | CSS-safe encoding / avoid putting raw input into styles | CSS has its own parser and sinks |
| JSON HTTP response | JSON serializer, proper content type | Never concatenate JSON strings manually |
| SQL parameter | Prepared statement / parameter binding | **SQL injection is not solved by HTML escaping** |
| Shell command | Avoid shell; use fixed-arg `ProcessBuilder` if needed | HTML escaping means nothing to a shell |
| Rich HTML text | Dedicated sanitization then proper rendering | Escaping everything strips formatting; sanitizer must block injection |
| Logs | Structured logging + CR/LF/PII controls per sink | Never dump secrets or rejected values arbitrarily |

**There is no single universal `escape(String)` for all outputs.** Use the library/framework API matched to each sink; OWASP emphasizes that output encoding must be context-sensitive.

### 6.4. Additional XSS protections

Content Security Policy (CSP), Trusted Types (where supported), template auto-escaping, avoiding inline scripts, and security headers provide defense-in-depth. CSP does not excuse server code using `th:utext` to inject untrusted HTML. Moreover, XSS is not just `<script>`: event handlers, URL schemes, DOM sinks, and parser contexts all matter.

### 6.5. SQL injection is a different problem

Dangerous example:

```java
String sql = "SELECT * FROM profiles WHERE username = '" + username + "'";
```

Even if `username` passed `@Size`, the string can still alter SQL syntax when concatenated like this. Use parameter binding:

```java
PreparedStatement statement =
    connection.prepareStatement(
        "SELECT * FROM profiles WHERE username = ?");
statement.setString(1, username);
```

These two fragments reference undefined `username`/`connection` variables for comparison. Prepared statements separate query syntax from data values. **Never** HTML-encode or manually escape quotes to prevent SQL injection.

## 7. Authorization: Who May Do What on Which Resource?

### 7.1. Authentication differs from authorization

- **Authentication** verifies identity—for example, user `alice` is logged in.
- **Authorization** decides whether `alice` is permitted to **read/edit profile ID 1**, **change roles**, **access another tenant**, or **export sensitive data**.

A user with role `USER` is not automatically allowed to edit every profile. Checking "is logged in" does not replace ownership/tenant verification; failing to check creates **IDOR/BOLA** vulnerabilities.

Example:

```text
GET /profiles/1   -> Alice (owner) can view
GET /profiles/2   -> Alice cannot view if profile 2 belongs to Bob
POST /profiles/2  -> Alice cannot update even with valid data
```

### 7.2. Defense in depth

Spring Security provides:

- **Request-level rules** via `SecurityFilterChain` and `authorizeHttpRequests`: blocks anonymous access to private endpoints.
- **Method-level rules** via `@EnableMethodSecurity` + `@PreAuthorize`: guards service methods by permissions and resource ID.
- Policies at service/domain/data-access layers: avoids trusting `owner` from HTTP forms and prevents bypass if a service is called from another controller.
- CSRF protection for browsers sending session/cookie credentials automatically; this is **a separate layer from authorization**.

Spring Security Starter does not enable `@PreAuthorize` on methods automatically without `@EnableMethodSecurity`. Methods without authorization annotations still need policies enforced in the proper layer.

### 7.3. Check before side effects

Do not update the database first and rely on `@PostAuthorize` to catch unauthorized callers afterward. Once a transaction has mutated state, post-checking can be too late or tricky to guarantee rollback in every scenario. For write operations, prefer `@PreAuthorize`/policy checks **before** modifying objects, followed by transactions and domain invariants.

### 7.4. Deny by default and least privilege

Keep **deny by default**: requests without explicit policies should be denied rather than accidentally public. Permissions should be scoped tightly to the task. Enforce checks on **every request** and every code path capable of side effects, not only the UI "Save" button.

Never treat `ownerId` in a form as proof. The server itself must derive ownership from authenticated identity, policies, and stored records. Never equate "authentication succeeded" with "authorized to modify this entity."

## 8. Complete Sample Program: Spring MVC + Security + Thymeleaf

This program demonstrates all four layers on a display-name edit screen. Data storage is an in-memory map to focus on the flow without database setup; real requests still traverse Spring MVC and Spring Security.

**Design:**

- `GET /profiles/{id}`: only the authenticated owner can view.
- `POST /profiles/{id}`: accepts a **DTO containing only `displayName`**, normalizes via `@InitBinder` before `@Valid`, checks `@NotBlank`/`@Size`, then updates through a `@PreAuthorize`-protected service.
- Thymeleaf `th:text` renders stored data as **HTML-escaped text** without creating tags.
- The binder allowlists `displayName`; a client-sent `role=ADMIN` is suppressed and the request is rejected.
- Spring Security's default CSRF protection remains enabled; form POSTs must supply a valid token.
- Fixed accounts: profile 1 belongs to `alice`, profile 2 belongs to `bob`.

**Explicit limitation:** the example uses `{noop}` passwords and in-memory identities strictly for local learning. Do not deploy it in publicly reachable environments; production requires an identity provider, password encoder, auditing, database, rate limiting, and full security policies.

### 8.1. Project structure

```text
profile-security-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/profile/
    │   │   ├── ProfileDemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── Profile.java
    │   │   ├── ProfileStore.java
    │   │   ├── ProfilePermission.java
    │   │   ├── ProfileService.java
    │   │   ├── ProfileForm.java
    │   │   ├── SafeText.java
    │   │   └── ProfileController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/profile.html
    └── test/
        └── java/demo/profile/ProfileSecurityTest.java
```

### 8.2. pom.xml — Java 17 and Spring Boot 3.5.6

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>profile-security-demo</artifactId>
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
      <artifactId>spring-boot-starter-validation</artifactId>
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
```

### 8.3. application.properties

```properties
# Lab only: do not expose to the network.
server.address=127.0.0.1
server.port=8080

# In the lab, renders template updates immediately; helpful for learning.
spring.thymeleaf.cache=false
```

Never rely on demo credentials or this configuration as production protection. Loopback binding limits network exposure; proper security testing remains a separate requirement.

### 8.4. ProfileDemoApplication.java

```java
package demo.profile;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProfileDemoApplication.class, args);
    }
}
```

`@EnableMethodSecurity` enables `@PreAuthorize` enforcement on Spring-managed services. Never use `@Validated` as a replacement: validation and authorization are separate systems.

### 8.5. SecurityConfig.java

```java
package demo.profile;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        // CSRF is enabled by default; intentionally left on.
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}demo-alice")
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password("{noop}demo-bob")
                .roles("USER")
                .build());
    }
}
```

Here:

- All endpoints other than login/error require authentication.
- The login form is provided by Spring Security; session/cookies are managed by the security framework.
- Permission to edit **a specific profile** is enforced at service method security rather than in request path rules.
- `{noop}` is an unhashed password encoder, **strictly for loopback demos**; production uses a proper password encoder and managed identity system.
- CSRF is not disabled. A session-backed POST must carry a valid token even when the user is logged in.

### 8.6. Profile.java

```java
package demo.profile;

public record Profile(
        long id,
        String owner,
        String displayName) {
}
```

The record is an immutable value object and does not let clients bind/edit a `role` property. In a real project this could be a JPA entity, while HTTP input should still use a dedicated DTO.

### 8.7. ProfileStore.java

```java
package demo.profile;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class ProfileStore {

    private final ConcurrentMap<Long, Profile> data =
        new ConcurrentHashMap<>(Map.of(
            1L, new Profile(1L, "alice", "Alice"),
            2L, new Profile(2L, "bob", "Bob")
        ));

    public Optional<Profile> find(long id) {
        return Optional.ofNullable(data.get(id));
    }

    public Profile require(long id) {
        return find(id).orElseThrow(
            () -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Profile not found"));
    }

    public Profile rename(long id, String displayName) {
        Profile updated = data.computeIfPresent(
            id,
            (key, old) -> new Profile(
                old.id(), old.owner(), displayName));

        if (updated == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Profile not found");
        }
        return updated;
    }
}
```

`ConcurrentHashMap#computeIfPresent` replaces the value for a key atomically on the map. This demo lacks persistence/tenant DB; production requires a transactional store and proper handling of race conditions, ownership, and locking.

### 8.8. ProfilePermission.java — policy based on true owner

```java
package demo.profile;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("profilePermission")
public class ProfilePermission {

    private final ProfileStore store;

    public ProfilePermission(ProfileStore store) {
        this.store = store;
    }

    public boolean owns(long id, Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()) {
            return false;
        }

        return store.find(id)
            .map(profile ->
                profile.owner().equals(authentication.getName()))
            .orElse(false);
    }
}
```

The policy reads `owner` from **server-side** data rather than an `owner` field in the request. For nonexistent resources or those not owned by the caller, the expression returns `false`. Thus the app can deny access without leaking which resources exist; exact 403/404 statuses follow API policy.

### 8.9. ProfileService.java — authorization before reading or modifying

```java
package demo.profile;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {

    private final ProfileStore store;

    public ProfileService(ProfileStore store) {
        this.store = store;
    }

    @PreAuthorize("@profilePermission.owns(#id, authentication)")
    public Profile read(@P("id") long id) {
        return store.require(id);
    }

    @PreAuthorize("@profilePermission.owns(#id, authentication)")
    public Profile changeName(
            @P("id") long id,
            String displayName) {
        return store.rename(id, displayName);
    }
}
```

`@P("id")` exposes the parameter name explicitly to the method-security expression `#id`. This is `org.springframework.security.core.parameters.P`, **not a JDBC query parameter annotation**.

Thanks to `@PreAuthorize`, calls from the controller through the Spring-managed service proxy are checked **before the method body executes**. `@EnableMethodSecurity` enables this behavior.

**AOP note:** Calling `this.changeName(...)` from another method in the same class can bypass proxy-based method security. Place policies at a boundary reliably invoked through a Spring bean proxy, add domain-level checks, and never treat annotations as infallible across self-invocation.

### 8.10. ProfileForm.java — DTO and Jakarta Validation

```java
package demo.profile;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class ProfileForm {

    @NotBlank
    @Size(max = 80)
    private String displayName;

    public ProfileForm() {
    }

    public ProfileForm(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

There is no `role`, `owner`, or `verified` on the DTO. Sending any of those attributes from the client grants no ability to alter the profile.

### 8.11. SafeText.java — normalization before validation

```java
package demo.profile;

import java.text.Normalizer;

public final class SafeText {

    private SafeText() {
    }

    public static String normalizeDisplayName(String raw) {
        if (raw == null) {
            return null;
        }
        return Normalizer.normalize(
            raw.strip(), Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        String composed = "Café";
        String decomposed = "Cafe\u0301";

        System.out.println(
            "same-before=" + composed.equals(decomposed));

        System.out.println(
            "same-after=" + composed.equals(
                normalizeDisplayName("  " + decomposed + "  ")));
    }
}
```

You can run this class standalone after compiling to observe Unicode NFC:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java \
  -Dexec.mainClass=demo.profile.SafeText
```

Exact output from the two `System.out.println` calls (excluding Maven logs):

```text
same-before=false
same-after=true
```

This is strictly normalization—not validation, sanitization, or escaping.

### 8.12. ProfileController.java — placing all four layers in the right places

```java
package demo.profile;

import java.beans.PropertyEditorSupport;

import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/profiles")
public class ProfileController {

    private final ProfileService service;

    public ProfileController(ProfileService service) {
        this.service = service;
    }

    @InitBinder("form")
    void initFormBinder(WebDataBinder binder) {
        // Accept only this single property from the request.
        binder.setAllowedFields("displayName");

        // PropertyEditor belongs to the request's binder; no shared
        // mutable state across requests.
        binder.registerCustomEditor(
            String.class,
            "displayName",
            new PropertyEditorSupport() {
                @Override
                public void setAsText(String text) {
                    setValue(SafeText.normalizeDisplayName(text));
                }
            });
    }

    @GetMapping("/{id}")
    public String show(
            @PathVariable("id") long id,
            Model model) {

        Profile profile = service.read(id); // @PreAuthorize
        model.addAttribute("profile", profile);
        model.addAttribute(
            "form", new ProfileForm(profile.displayName()));

        return "profile";
    }

    @PostMapping("/{id}")
    public String update(
            @PathVariable("id") long id,
            @Valid @ModelAttribute("form") ProfileForm form,
            BindingResult errors,
            Model model,
            HttpServletResponse response,
            RedirectAttributes redirect) {

        // Do not expose profile data unless the caller is authorized.
        Profile profile = service.read(id); // @PreAuthorize

        if (errors.getSuppressedFields().length > 0) {
            errors.reject(
                "extraFields", "Form contains disallowed fields");
            response.setStatus(
                HttpServletResponse.SC_BAD_REQUEST);
        }

        if (errors.hasErrors()) {
            model.addAttribute("profile", profile);
            return "profile";
        }

        // @PreAuthorize again on the write method.
        service.changeName(id, form.getDisplayName());
        redirect.addFlashAttribute("saved", true);
        return "redirect:/profiles/" + id;
    }
}
```

Clear separation of responsibilities:

1. `@InitBinder("form")` configures **normalization and allowlist** for that form; the Java property editor runs before form validation.
2. `@Valid` verifies the normalized name is non-blank and at most 80 characters.
3. `BindingResult errors` sits **immediately after** `ProfileForm form`; the controller does not save when errors exist.
4. Both `service.read(id)` and `service.changeName(id,...)` enforce **authorization against the real resource ID**. Never trust a form-submitted ID as ownership proof.
5. If a request adds `role=ADMIN`, the binder suppresses the field; the controller explicitly sets status 400. Normal validation does not automatically return 400 when an adjacent `BindingResult` is present, so the code selects the appropriate response.
6. **Escaping is not in the controller and does not happen on save.** It happens when Thymeleaf renders the template output.

A request with `displayName="   "` normalizes to an empty string before `@NotBlank`. Sending a field outside the allowlist returns 400 with no side effects. In this example, regular validation failures re-render the same view (typically HTTP 200 for server-rendered forms); if an API contract requires 422/400 for validation, update the HTTP contract deliberately.

### 8.13. templates/profile.html — escaping at the output sink

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Profile</title>
</head>
<body>
    <h1>Edit Profile</h1>

    <p>Owner:
        <span th:text="${profile.owner}">owner</span>
    </p>

    <p>Current name:
        <span id="currentName"
              th:text="${profile.displayName}">name</span>
    </p>

    <p th:if="${saved}">Saved.</p>

    <form method="post"
          th:action="@{/profiles/{id}(id=${profile.id})}"
          th:object="${form}">

        <label for="displayName">Display name</label>
        <input id="displayName" type="text"
               th:field="*{displayName}" maxlength="80"/>

        <p th:if="${#fields.hasErrors('displayName')}"
           th:errors="*{displayName}">Invalid name</p>

        <p th:if="${#fields.hasGlobalErrors()}">
            Form contains disallowed properties.
        </p>

        <button type="submit">Save</button>
    </form>
</body>
</html>
```

When `profile.displayName` holds an HTML-like string, `th:text` emits it as **HTML-escaped text**. It creates no `img` tag and fires no `onerror` handler. This is where output encoding belongs.

`th:field` renders the input value safely for attribute context. `th:action` uses a Thymeleaf URL expression; with Spring Security CSRF enabled, Spring/Thymeleaf integration via `RequestDataValueProcessor` injects the hidden CSRF token into the HTML POST form. Verify that the token actually appears in rendered HTML and is submitted back.

**Never replace `th:text` with `th:utext` for user data.** Do not assemble an HTML string in the controller and pass it to the view as "sanitized" unless an explicit rich-HTML sanitization contract exists.

## 9. Running the Project and Observing Results

In the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

Open a browser on the **same machine**:

```text
http://127.0.0.1:8080/profiles/1
```

The app redirects to the login form if unauthenticated. Use the demo user:

```text
username: alice
password: demo-alice
```

After logging in, Alice's profile page appears. Try:

1. Enter `"  Café  "` (or a decomposed `é`) and click Save. The normalizer strips outer whitespace and applies NFC; the result displays consistently.
2. Enter a string of only spaces. `@NotBlank` catches the error after normalization; nothing is saved.
3. Enter a string longer than 80 UTF-16 code units after normalization. `@Size(max=80)` catches the error. Browsers may constrain input via `maxlength=80`, yet the backend must still validate tampered requests.
4. Enter `<img src=x onerror=alert(1)>`. Within the length limit, the app may store those HTML-significant characters as **plain text data**, while `th:text` renders them inertly as text without creating an `img` element.
5. Log out, log in as `bob / demo-bob`, and open `/profiles/1`. Method security denies access because Bob does not own profile 1. Bob may view/edit only `/profiles/2`.

Never test HTML injection outside a controlled lab environment; here the sole purpose is verifying template output encoding.

### 9.1. CSRF tokens and curl

With form login, sessions, and CSRF enabled, a direct `curl -X POST` **without a valid CSRF token** typically receives HTTP 403 before reaching the controller. That is expected behavior, not a bug in Bean Validation or ownership checks.

For automated HTTP testing, use `MockMvc` with `with(csrf())` from Spring Security Test, or drive an authenticated browser submitting the form with its hidden token. **Never disable CSRF just to make curl examples easier** when authentication relies on sessions/cookies.

### 9.2. Distinguishing each failure over HTTP

| Test case | Deciding layer | Expected outcome |
| --- | --- | --- |
| Anonymous opens `/profiles/1` | Authentication/request security | Redirects to login page |
| Bob opens Alice's profile | Service authorization | 403 or matching concealment policy |
| Alice POSTs without CSRF | CSRF filter | 403 |
| Alice submits `displayName="   "` | Normalization + validation | Form view shows error, no update |
| Alice submits extra `role=ADMIN` | Binder allowlist + suppressed fields check | 400, no update |
| Alice submits valid HTML-like text | Validation + output escaping | Stored as text per contract, rendered inert |
| Alice sends script to unescaped JS sink | Context-specific output handling (if sink is broken) | XSS risk; no such sink exists in the sample |
| Alice changes URL ID to 2 | Owner authorization | Cannot edit Bob |
| Code concatenates input into SQL | Query building | Needs prepared statements, not HTML escaping |

## 10. Automated Testing with MockMvc and Spring Security Test

The `src/test/java/demo/profile/ProfileSecurityTest.java` example below tests all four layers using real requests through Spring MVC and Security filters.

```java
package demo.profile;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode =
    DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ProfileSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice")
    void normalizationAndEscaping() throws Exception {
        mvc.perform(post("/profiles/1")
                .with(csrf())
                .param("displayName",
                    "  <img src=x onerror=alert(1)>  "))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/profiles/1"));

        mvc.perform(get("/profiles/1"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("&lt;img")))
            .andExpect(content().string(not(
                containsString("<img src=x onerror=alert(1)>"))));
    }

    @Test
    @WithMockUser(username = "alice")
    void disallowedFieldsRejected() throws Exception {
        mvc.perform(post("/profiles/1")
                .with(csrf())
                .param("displayName", "New name")
                .param("role", "ADMIN"))
            .andExpect(status().isBadRequest());

        // Request rejected: name remains Alice.
        mvc.perform(get("/profiles/1"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("Alice")));
    }

    @Test
    @WithMockUser(username = "bob")
    void cannotEditOtherUsersProfile() throws Exception {
        mvc.perform(post("/profiles/1")
                .with(csrf())
                .param("displayName", "Stolen"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void missingCsrfIsForbidden() throws Exception {
        mvc.perform(post("/profiles/1")
                .param("displayName", "New name"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void blankAfterNormalizationDoesNotUpdate() throws Exception {
        mvc.perform(post("/profiles/1")
                .with(csrf())
                .param("displayName", "   "))
            .andExpect(status().isOk());

        mvc.perform(get("/profiles/1"))
            .andExpect(content().string(containsString("Alice")));
    }
}
```

**Note when copying imports:** Java does not allow arbitrary line breaks inside an `import static` at awkward positions; the `import static org.springframework...` lines above are wrapped at whitespace after package names for formatting. While Java permits whitespace/newlines between tokens, the cleanest IDE practice is **one import per line**. To avoid paste-formatting issues, you can replace the static imports with standard single-line imports using the class names listed below:

```java
// List for IDE auto-import, not a standalone Java file:
// org.hamcrest.Matchers.containsString
// org.hamcrest.Matchers.not
// SecurityMockMvcRequestPostProcessors.csrf
// MockMvcRequestBuilders.get
// MockMvcRequestBuilders.post
// MockMvcResultMatchers.content
// MockMvcResultMatchers.redirectedUrl
// MockMvcResultMatchers.status
```

Run:

```bash
mvn -q test
```

When tests pass, Maven typically prints no application stdout because assertions do not call `System.out.println`. Do not treat a phrase like "5 tests PASS" as literal fixed Maven stdout; check exit code 0 and the test report to confirm.

**Scope of proof:**

- The normalization + XSS test proves only that data is HTML-escaped when rendered; do not treat it as proof for JavaScript/CSS/URL sinks.
- The rejected-fields test proves the binder allowlist runs and skips saving the profile.
- The Bob test proves owner authorization in the service.
- The CSRF test proves the filter protects form POSTs.
- The blank test proves normalization happens before validation.
- `@DirtiesContext` gives each test fresh in-memory data, avoiding test-order coupling.

Real projects should add tests for context-specific DOM sinks, concurrency, IDOR/BOLA, and every other service/async update path.

## 11. Common Mistakes When Combining Layers

### 11.1. "It's validated, so escaping isn't needed"

False. A valid value can contain `<`, `"`, or `'`. Validation enforces the business contract; output encoders address HTML/JS/URL parser syntax. Even data read from the database must be treated as untrusted before display because it might have been stored via another endpoint (stored XSS).

### 11.2. "It's escaped, so validation isn't needed"

False. An HTML-escaped email can still be an invalid email; an escaped negative quantity still violates business invariants. Never substitute encoding for range checks, enum allowlists, payload size caps, or cross-field constraints.

### 11.3. "Just normalize and strip the word script"

False. XSS spans far more contexts and payloads than `<script>`. A regex denylist stripping "script" fails against event handlers, URL schemes, SVG, CSS, and DOM sinks. Normalization can also produce new equivalent strings; apply validation and output encoding at the proper layers.

### 11.4. "The user is logged in, so they can edit the resource"

False. Authentication establishes identity, while authorization checks **ownership/tenant/action**. Changing `/profiles/1` to `/profiles/2` in the URL must never grant permission to update someone else's profile.

### 11.5. "Hiding the role field in the form is safe"

False. Clients can append `role=ADMIN` themselves. Use DTOs/allowlists/explicit mapping and authorization rather than binding entities with sensitive properties directly from requests. Be careful with `@RequestBody` JSON: Jackson deserialization works differently from `@ModelAttribute`, so form-binder `setAllowedFields` does not guard JSON properties.

### 11.6. "Sanitize HTML once and use it everywhere"

False. If rich HTML is permitted, a sanitizer must enforce a sound HTML policy and output sinks must still be handled safely. An HTML snippet can still be unsafe inside an attribute, inline JS, or URL. There is no universal "safe string."

### 11.7. "@PreAuthorize is enough even for internal calls in the same class"

False under standard proxy-based method security: self-invocation can bypass the proxy. Enforce policies at a service boundary genuinely called through a Spring bean proxy, add domain/data-access authorization, or use a mechanism suited to your architecture.

### 11.8. "Use th:utext to support accented names"

False. Vietnamese Unicode displays normally through `th:text` when character encoding is set properly. `th:utext` enables unescaped HTML, not Unicode support.

### 11.9. "Disabling CSRF is a performance optimization"

Not by default. With browsers and session cookies, CSRF protects against forged cross-site requests independently of validation and authorization. Only change CSRF strategy when your authentication and threat models justify it; never disable it just to make POST tests easier.

### 11.10. "HTML escaping works for SQL"

False. SQL has its own parser and escaping rules; use parameter binding/prepared statements. Likewise, URL path traversal requires path/URI checks, command injection requires avoiding shells, and JSON requires a proper serializer.

## 12. Code Review Checklist and Exercises

When reviewing a Spring MVC data-receiving endpoint:

1. Clearly identify all **untrusted data sources**: body, query, path, headers, database, message queues, third-party APIs.
2. Does the data require **normalization**? Would that rule alter the meaning of passwords, tokens, or identifiers?
3. Does normalization occur **before validation and comparison** on the exact request path?
4. Is there a dedicated DTO exposing **only necessary fields**?
5. Is `@Valid`/`@Validated` or explicit validation applied, and is `BindingResult` checked on error?
6. Which principal saves/updates the value? Where is **owner/tenant/action authorization** checked?
7. For writes, are policies checked before side effects? Can any service call bypass the proxy?
8. Are request-level rules **deny-by-default**?
9. Do browser forms/cookies have CSRF protection, and how is the token included in POSTs?
10. Through which sinks does data exit to HTML, attributes, JS, CSS, URLs, JSON, SQL, or logs?
11. Is output encoding/serialization **context-appropriate**? Does `th:utext` or `innerHTML` receive raw text?
12. If rich HTML is permitted, does the sanitizer use an allowlist with malformed-HTML tests?
13. When building SQL, are prepared statements used instead of string concatenation?
14. Are there regression tests for decomposed Unicode, blank strings, oversized strings, HTML-like text, extra `role` fields, and other users' resource IDs?
15. Do logs and error responses avoid leaking tokens, passwords, rejected values, and stack traces?

### Exercise A — classify the defense layer

Given these scenarios:

| Requirement | Primary layer |
| --- | --- |
| Strip leading/trailing whitespace from display name per policy | Normalization |
| Reject an empty name after trimming | Validation |
| Reject unknown role outside enum/domain contract | Validation |
| Prevent regular users from changing role even though `ADMIN` is valid | Authorization + DTO/allowlist |
| Render a string containing `<img>` as plain text in HTML | Output encoding |
| Block Bob from updating Alice's profile ID | Authorization |
| Return JSON containing double quotes in a name | JSON serialization |
| Execute a SELECT by username | SQL parameter binding |
| Form POST missing a valid CSRF token | CSRF protection |
| Preserve valid rich HTML while stripping event handlers | Dedicated HTML sanitization |

### Exercise B — spot the bugs in code

The snippet below is intentionally unsafe:

```java
@PostMapping("/accounts/{id}")
public String update(@PathVariable long id,
                     @Valid @ModelAttribute Account entity,
                     Model model) {

    repository.save(entity);
    model.addAttribute("html",
        "<div>" + entity.getDisplayName() + "</div>");
    return "account";
}
```

Issues:

- Using the entity as the input object opens mass assignment.
- Never verifies whether the user has permission to update that account ID.
- `@Valid` does not block updating sensitive roles if constraints allow them.
- Concatenating raw `displayName` into HTML causes XSS if the view renders it unescaped.
- Fails to reconcile the URL ID source with the bound data object (they may mismatch).
- Lacks explicit handling for validation/binding and authorization failures.

How to fix: dedicated DTO, normalization before validation per policy, service-layer owner/tenant checks mapping only allowed fields, standardized error responses, rendering fields as escaped text, and tests sending extra sensitive attributes.

## 13. Summary

**Normalization** ensures input has a consistent domain representation. **Validation** verifies data conforms to structure and rules. **Escaping/output encoding** keeps data as data in a **specific output context** rather than becoming HTML/JavaScript/SQL syntax (SQL requires parameterization). **Authorization** checks whether the caller has permission for the actual **action and resource**; it builds on authentication without being identical to it.

In Spring MVC, you can use `WebDataBinder`/converters to normalize fields before `@Valid`; input DTOs and `BindingResult` to handle validation; Thymeleaf `th:text` or context-appropriate serializers on output; and Spring Security's `SecurityFilterChain`, `@PreAuthorize`, and domain policies to protect resources. **Only when these layers work together in their proper places** can an application resist malformed data, injection, and unauthorized access while preserving legitimate inputs such as accented Unicode names.

## References

- OWASP — Input Validation Cheat Sheet (normalization/canonicalization, schema validation): https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
- OWASP — Cross Site Scripting Prevention Cheat Sheet (context-sensitive output encoding): https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- OWASP — Authorization Cheat Sheet (deny-by-default, least privilege, every request): https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — Mass Assignment Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
- OWASP — SQL Injection Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- Spring Framework 6.2 — `@InitBinder` and data binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — `@ModelAttribute` arguments and security: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — Bean Validation integration: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Security — Method Security and `@PreAuthorize`: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Spring MVC integration and defense-in-depth: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html
- Spring Security — CSRF protection for forms: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Thymeleaf 3.1 — `th:text` escaping vs `th:utext`: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html
- Unicode Standard Annex #15 — Unicode normalization forms: https://www.unicode.org/reports/tr15/
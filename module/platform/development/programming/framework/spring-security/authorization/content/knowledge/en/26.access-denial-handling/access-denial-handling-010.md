# Fallback Values, Field Masking, and Safe Boundaries When Access Is Denied

A system using **Spring Security Authorization** does not only need to know when to return `403 Forbidden`. When a caller has permission to view **part** of the data but is not allowed to see sensitive fields, the system must also decide whether to **omit fields**, **partially mask** them, or return a **safe fallback value**. All of these choices must be enforced by server-side permission policies; a `"***"` string in the UI does not create security on its own.

This lesson belongs to the **Access Denial Handling** topic in the **Spring Security - authorization** module. The focus is on decisions after authorization checks, limiting returned data, and avoiding leaks while trying to create a user-friendly experience.

## 1. Distinguishing Full Resource Denial from Per-Field Restrictions

Before thinking about masking or fallbacks, answer two independent questions:

1. **Is the caller permitted to read this object?** For example, Alice may read Alice's profile; Bob may not read Alice's private profile.
2. **If permitted to read the object, which attributes may the caller read?** For example, support staff can see the name and last four digits of the phone number, but may not read the raw email or admin notes.

If question (1) is denied, do not return HTTP 200 with fake data as if the caller had been granted access. Apply the denial policy, usually `403`, or `404` when the product intentionally hides the object's existence. If question (1) is allowed but a field is restricted, return an **authorized projection**: include only permitted attributes and masked/fallback values compliant with the API contract.

~~~text
Request -> Authenticate identity -> Check resource permissions
                                |
                        +-------+--------+
                        |                |
                      DENY             ALLOW
                        |                |
                   403 or 404     Check per-field permissions
                                         |
                                 DTO containing only safe data
                                         |
                              Serialize JSON -> HTTP 200
~~~

Spring Security manages authentication and request/method authorization rules. How each attribute is masked is a **business policy decision** that the application must enforce at the service/DTO/serialization boundary. Configuring `authorizeHttpRequests` only protects calling the endpoint; it **does not automatically guarantee** every attribute in an entity is allowed to appear in JSON.

These are two distinct layers of control, corresponding to **Broken Object Level Authorization** and **Broken Object Property Level Authorization** risks (OWASP API1/API3).

## 2. Meaning of Fallback Values, Field Masking, and Field Omission

| Handling Approach | Common Representation | When to Use | Risks to Control |
| --- | --- | --- | --- |
| **Full denial** | HTTP `403` or `404` | Access to the object/action is not permitted | Never include real data in body, headers, or error messages |
| **Omit field** | Missing `internalNote` key | Caller has no permission to know about this field | Ensure nested objects, exports, and other endpoints do not leak it either |
| **Fallback due to missing data** | `"Not provided"` | Field is permitted to view, but source is genuinely empty | Do not use this fallback to conceal a permission denial |
| **Fallback due to permission limit** | `"Hidden"` | Allowed to view object, not allowed to view field value | Fallback string must be server-generated and contain no original data |
| **Partial mask** | `"***4567"` | Policy **explicitly allows** viewing the last four digits | Trailing digits, format, length, and email domain are still disclosed data |
| **No permission to read secrets** | Do not return field/token | Passwords, refresh tokens, API secrets, private keys | Never use "mask a few characters" as a security promise |

In particular, `null`, `""`, `"N/A"`, and *absent property* carry different meanings for clients. Document them clearly in the API contract. For example, `email: null` could be interpreted as no email on file, when in fact an email exists but the caller is not permitted to know. If the response must not even disclose the **existence** of the email, a fixed placeholder or a schema without the email field is more appropriate.

**Do not fabricate misleading default data.** Using `0` as an account balance when the user cannot view balances can misrepresent financial status; using `false` when not allowed to know moderation status can lead to wrong conclusions. If permission is denied for an action, return the denial status per contract—never return `success: true` with fake data.

### Principles for Partial Masking

A mask is safe only when the parts **retained have been approved for disclosure**. Examples like keeping the last four digits of a phone number, part of an email, or part of an identifier are not inherently safe for every organization.

- Validate input format before applying a mask; data that is too short or invalid should use a fixed placeholder to avoid exposing the raw text.
- Never store masked output and treat it as a form of encryption. Masking reduces displayed information; it is not encryption, hashing, or tokenization.
- Do not match the number of asterisks to the real string length if policy forbids inferring length.
- Never use masking to turn passwords, access tokens, refresh tokens, secret keys, or recovery codes into "safe" values for re-issuance.
- Never place original data in hidden HTML attributes, state hydration, debug JSON, logs, tooltips, URLs, or HTTP headers and hide it only with CSS.

## 3. Choose the HTTP Status Code Before Choosing the Representation

| Scenario | Typical Response | Interpretation |
| --- | --- | --- |
| Unauthenticated, calling a login-required resource | `401 Unauthorized` with scheme-appropriate challenge | Valid credentials must be provided |
| Authenticated, not allowed to read the resource | `403 Forbidden` | Server denies the resource/action |
| Object missing, or policy intentionally hides object existence | `404 Not Found` | Client must not learn that an accessible resource exists |
| Allowed to read resource, but only some fields | `200 OK` with field-restricted DTO | Returned data must obey **per-field** permissions |
| Allowed to read field, but actual value is absent | `200 OK` with defined placeholder | This is a data fallback, not a security exception |

`ExceptionTranslationFilter` along with `AuthenticationEntryPoint`/`AccessDeniedHandler` handles security exceptions according to the servlet filter chain configuration. It does not automatically mask emails or convert entities into DTOs. If a service/controller throws `AccessDeniedException` and the exception propagates out through the security filter chain, Spring Security can translate it into a denial response. An authentication filter can also handle its own authentication failure before the exception reaches `ExceptionTranslationFilter`.

Choosing `404` to hide an object's existence works only if **the policy is applied consistently**. Different responses between real IDs and non-existent IDs can still create a resource-enumeration vulnerability via status codes, messages, body sizes, or processing time. Do not use `404` as a way to skip permission checks.

## 4. Designing Policies Based on Identity and Data

Suppose an API returns user profiles. The actors:

- **Owner**: views their own profile, including email and phone.
- **SUPPORT**: views profiles to provide support, but email is replaced with `"Hidden"`, and phone shows only the last four digits.
- **ADMIN**: views both contact details and internal notes.
- **Another USER**: not allowed to view the owner's profile.

Permission matrix for any given profile:

| Field | Owner | SUPPORT | ADMIN | Other USER |
| --- | --- | --- | --- | --- |
| `id`, `displayName` | Real value / default value if missing | Same | Same | Do not return profile |
| `email` | Real email or `"Not provided"` | `"Hidden"` | Real email or `"Not provided"` | Do not return profile |
| `phone` | Real number or `"Not provided"` | `"***4567"` if last four digits allowed, otherwise `"Hidden"` | Real number or `"Not provided"` | Do not return profile |
| `internalNote` | Omit field | Omit field | Real note | Do not return profile |

This permission matrix is **only an example policy**. Specifically, whether SUPPORT can view all profiles or the last four phone digits, or whether ADMIN can view notes, must be approved by the business in a real product. Never assume `SUPPORT` or `ADMIN` roles grant every permission based solely on role names.

Safe processing workflow:

1. Obtain principal/authorities from `Authentication` verified by Spring Security; never trust `role`, `ownerId`, or `isAdmin` sent by the client.
2. Retrieve the target record and check permissions on **the specific record**. Requiring `authenticated()` on the endpoint is not enough to allow reading arbitrary IDs.
3. If viewing the record is denied, stop processing and return 403/404 per policy; never use masking to turn unauthorized access into valid access.
4. If viewing is allowed, determine permissions for **each attribute**. Construct a response DTO from the list of permitted fields, substituting or omitting fields per contract.
5. Only then serialize and send over the network. Re-check error paths, caching, logging, and all related endpoints.

## 5. Spring Boot Servlet 3.x + Spring Security 6.x + Java 17+ Example

In a Spring Boot project with plugins already configured, use two starters:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Save the complete program at `src/main/java/com/example/safeview/SafeViewApplication.java`. Goal: distinguish **blocking resource access** from **granting profile view in a field-masked form**.

~~~java
package com.example.safeview;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;

@SpringBootApplication
@RestController
public class SafeViewApplication {

    private static final Map<String, Profile> PROFILES = Map.of(
            "p1", new Profile(
                    "p1", "alice", "An", "an@example.test",
                    "0901234567", "Admin-only note"),
            "p2", new Profile(
                    "p2", "bob", "", null,
                    null, "Internal control info")
    );

    public static void main(String[] args) {
        SpringApplication.run(SafeViewApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/profiles/*")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .exceptionHandling(ex -> ex.accessDeniedHandler(
                        (request, response, error) ->
                                response.setStatus(
                                        HttpServletResponse.SC_FORBIDDEN)))
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice").password("{noop}pw")
                        .roles("USER").build(),
                User.withUsername("bob").password("{noop}pw")
                        .roles("USER").build(),
                User.withUsername("support").password("{noop}pw")
                        .roles("SUPPORT").build(),
                User.withUsername("admin").password("{noop}pw")
                        .roles("ADMIN").build()
        );
    }

    @GetMapping("/api/profiles/{id}")
    public ProfileView readProfile(@PathVariable String id,
                                   Authentication authentication,
                                   HttpServletResponse response) {
        Profile profile = PROFILES.get(id);
        if (profile == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        boolean owner = authentication.getName().equals(profile.owner());
        boolean support = hasAuthority(authentication, "ROLE_SUPPORT");
        boolean admin = hasAuthority(authentication, "ROLE_ADMIN");

        if (!owner && !support && !admin) {
            throw new AccessDeniedException("Profile access denied");
        }

        boolean fullContact = owner || admin;
        String safeName = fallback(profile.displayName(), "Not updated");
        String safeEmail = fullContact
                ? fallback(profile.email(), "Not provided")
                : "Hidden";
        String safePhone = fullContact
                ? fallback(profile.phone(), "Not provided")
                : maskLastFour(profile.phone());
        String safeInternalNote = admin ? profile.internalNote() : null;

        response.setHeader(HttpHeaders.CACHE_CONTROL, "private, no-store");
        return new ProfileView(
                profile.id(), safeName, safeEmail,
                safePhone, safeInternalNote);
    }

    private static boolean hasAuthority(
            Authentication authentication, String authority) {
        return authentication.getAuthorities().stream()
                .anyMatch(granted -> authority.equals(granted.getAuthority()));
    }

    private static String fallback(String raw, String substitute) {
        return raw == null || raw.isBlank() ? substitute : raw;
    }

    private static String maskLastFour(String raw) {
        if (raw == null) {
            return "Hidden";
        }
        String digits = raw.replaceAll("[^0-9]", "");
        if (digits.length() < 4) {
            return "Hidden";
        }
        return "***" + digits.substring(digits.length() - 4);
    }

    private record Profile(
            String id,
            String owner,
            String displayName,
            String email,
            String phone,
            String internalNote) {
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record ProfileView(
            String id,
            String displayName,
            String email,
            String phone,
            String internalNote) {
    }
}
~~~

### Why Is This Example Safe Within Its Illustrative Scope?

- `authorizeHttpRequests` requires login before entering the API. For unpermitted routes, `denyAll()` is a safe default. `DispatcherType.ERROR` is permitted so Servlet HTTP error dispatches are not masked by a second denial.
- **Owner/support/admin checks are performed on records p1/p2**, not just on the path. A logged-in USER does not automatically get permission to view someone else's profile.
- In the denied branch, the method throws `AccessDeniedException` before creating a DTO; the configured `AccessDeniedHandler` returns `403`. In a real system, resource policies can live in the service/repository or method authorization so every call path obeys them.
- `Profile` is internal data and is **never returned directly** from the controller. `ProfileView` is an intentional DTO; for owner/support, `internalNote` is `null` and `@JsonInclude(NON_NULL)` omits the key from JSON.
- `maskLastFour` intentionally exposes only the last four digits to SUPPORT; if data is short/missing, it returns a fixed placeholder. Do not reuse this helper for data where the last four digits are also forbidden to expose.
- Restricted fields are processed **before** Jackson serializes. Changing text on the frontend after receiving raw data fails the protection goal.
- The response sets `Cache-Control: private, no-store` to limit caching of sensitive responses. Actual cache/CDN configurations must still be verified.
- `{noop}pw` passwords and in-memory data are for local testing only. In production, use proper password hashing, HTTPS, identities from a real authentication system, and separately managed authorization policies.

**Note on 404:** the example returns `404` for a non-existent ID but `403` when Bob knows a real ID without permission. That is a policy that **may disclose the existence** of the profile. If the product must not disclose existence, design and test a policy returning `404` consistently for both cases while reducing other inference channels. The example keeps `403` to clearly illustrate the access-denied branch.

### Running and Observing Results

In the project directory containing the Gradle wrapper and Spring Boot plugin:

~~~bash
./gradlew bootRun
# On Windows: gradlew.bat bootRun
~~~

Call in sequence:

~~~bash
curl -i http://localhost:8080/api/profiles/p1
curl -i -u alice:pw http://localhost:8080/api/profiles/p1
curl -i -u support:pw http://localhost:8080/api/profiles/p1
curl -i -u admin:pw http://localhost:8080/api/profiles/p1
curl -i -u bob:pw http://localhost:8080/api/profiles/p1
curl -i -u bob:pw http://localhost:8080/api/profiles/p2
curl -i -u admin:pw http://localhost:8080/api/profiles/not-found
curl -i -u alice:wrong http://localhost:8080/api/profiles/p1
~~~

| Request | Expected HTTP | Key Decision |
| --- | --- | --- |
| Anonymous -> `p1` | 401 | Authentication required; HTTP Basic has challenge |
| Alice -> `p1` | 200 | Owner: real email/phone, no `internalNote` |
| SUPPORT -> `p1` | 200 | Email placeholder, phone has only last four digits |
| ADMIN -> `p1` | 200 | Has email, phone, and `internalNote` |
| Bob -> `p1` | 403 | Not allowed to view resource at all; never return 200 with mask |
| Bob -> `p2` | 200 | Owner: empty fields replaced with valid defaults |
| ADMIN -> missing ID | 404 | Resource not found |
| Alice with wrong password -> `p1` | 401 | HTTP Basic authentication failed |

Illustrative response for SUPPORT reading `p1`:

~~~json
{
  "id": "p1",
  "displayName": "An",
  "email": "Hidden",
  "phone": "***4567"
}
~~~

Illustrative response for Bob reading his own profile `p2`:

~~~json
{
  "id": "p2",
  "displayName": "Not updated",
  "email": "Not provided",
  "phone": "Not provided"
}
~~~

Illustrative response for ADMIN reading `p1`:

~~~json
{
  "id": "p1",
  "displayName": "An",
  "email": "an@example.test",
  "phone": "0901234567",
  "internalNote": "Admin-only note"
}
~~~

JSON key ordering and additional HTTP headers may vary depending on framework/version. The status codes and field values in the table are what must be verified. Specifically, no response for SUPPORT or owner **may contain** the internal string `"Admin-only note"`, even in error bodies or metadata.

## 6. When to Use Spring Security Method Authorization?

`@EnableMethodSecurity` allows `@PreAuthorize` and `@PostAuthorize` to control calls to Spring-managed methods. It is useful when the same service is called from multiple controllers, background tasks, or other adapters. A **brief illustrative example, not a standalone program**:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public ProfileAudit readAuditForAdmin(String profileId) {
    return repository.readAudit(profileId);
}
~~~

Without enabling `@EnableMethodSecurity`, the annotation above is not automatically enforced merely by having `spring-boot-starter-security`. `@PreAuthorize` itself also does not automatically produce field-level masked data. For mixed public/private data, you still need object-level permission checks and per-field DTO construction.

Prefer **checking permissions before performing side effects**. `@PostAuthorize` can fit certain read operations, but do not rely on a check after the method has written data to guard a dangerous action. For large lists, filter permissions directly in the query/repository so counts, ordering, and pagination reflect the records permitted to be viewed.

When using multiple `SecurityFilterChain` beans, verify which chain a request actually matches: entry points, denied handlers, and endpoint rules may differ. Controllers are not the sole protection boundary if objects/services are also exposed via GraphQL, WebSocket, message consumers, or other jobs.

## 7. Safety Boundaries to Protect Beyond the JSON Body

**A. Do not leak raw data through other paths.** A field masked in the detail endpoint can still leak via: lists, search results, CSV/Excel exports, API v2, GraphQL selections, attachments, event payloads, email notifications, autocomplete, nested objects, debug endpoints, or automatic entity serialization. Every output path must apply the appropriate policy and projection.

**B. Do not leak sensitive structure.** Values like `hasPrivateNote: true`, data length, element counts, the distinction between `null` and an omitted key, `ETag` content, validation errors, response timing, or sort order can disclose existence/attributes even without returning the direct value. Acceptable risk depends on the threat model and policy.

**C. Do not leak via logs and tracing.** A 403 error message may log a request ID/correlation ID, but must not copy raw emails, tokens, full profiles, or stack traces to the client. Configure body logging, APM, reverse proxies, and audit logs with the same protection level. Limit sensitive content in entity `toString()` methods.

**D. Do not leak via caches.** Identity-dependent responses must not enter shared CDN caches if the cache key does not fully distinguish permissions. Use `Cache-Control: private, no-store` for sensitive content; check browsers, proxies, CDNs, and mobile apps alike. An ETag or cache key tied to raw data can also unintentionally leak info.

**E. Do not leak via pagination and statistics.** For `GET /profiles?owner=...`, do not fetch the entire list and mask fields on denied rows or return the total count before permission filtering. Perform row-level filtering in the query before `COUNT`, `OFFSET/LIMIT`, and aggregations, per business requirements.

**F. Do not turn client input into policy.** Never let clients choose `fields=internalNote`, `includePrivate=true`, `role=ADMIN`, or supply `ownerId` to fetch sensitive data. If an API supports field selection, **intersect** the requested field set with the server-permitted field set before querying/serializing. Also guard against mass assignment on writes: input DTOs must only permit editing attributes the principal has permission to modify.

**G. Do not let system errors open permissions.** Policy service timeouts, missing authorities, or configuration read failures must follow appropriate fail-closed behavior; never return the full entity to "preserve user experience". Distinguish real infrastructure errors (`5xx`) from policy denials (`403`/`404`), avoiding using 403 to mask all server errors.

## 8. Testing Against a Permission and Field Matrix

Tests should verify **the absence of forbidden data**, not just whether the response has status 200/403:

| Case | What Must Be Asserted |
| --- | --- |
| Not logged in | 401/appropriate challenge, no PII |
| USER matching owner | Permitted full contact info, `internalNote` omitted |
| USER other owner | 403/404 per policy, no DTO/PII |
| SUPPORT | Email is placeholder, phone only last-4, `internalNote` absent |
| ADMIN | Exact permitted fields, no out-of-contract attributes |
| Source field null/empty | Right placeholder for authorized actor, no misleading `null` |
| Phone under four digits | Does not return raw phone due to masking bug |
| Non-existent ID | 404 per policy, no ID-enumeration signals |
| Missing or invalid roles/claims | Does not grant ADMIN/SUPPORT-level access |
| List/export/search endpoints | Apply the same object and field policies |
| Cache across two principals | ADMIN's full response is not served to SUPPORT |
| Error/logging paths | Contain no real data, stack traces, or secrets |

An example Spring MVC test snippet (illustrative only, not standalone) can assert values and **absence** simultaneously:

~~~java
mockMvc.perform(get("/api/profiles/p1")
        .with(httpBasic("support", "pw")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.email").value("Hidden"))
    .andExpect(jsonPath("$.phone").value("***4567"))
    .andExpect(jsonPath("$.internalNote").doesNotExist());
~~~

This snippet assumes the test already has `MockMvc` and static imports from `MockMvcRequestBuilders`, `SecurityMockMvcRequestPostProcessors`, and `MockMvcResultMatchers`; `spring-security-test` and `spring-boot-starter-test` must be added when building a real test suite. For sensitive information, you can combine assertions confirming the secret string does not appear anywhere in the full response.

## 9. Common Mistakes

1. **Masking data in React/HTML after the API returned real values.** Anyone opening the Network tab still sees the data. Move masking logic to the server and return a safe DTO.
2. **Returning `200` with the string `"No permission"` for forbidden resources.** Clients and caches may treat it as successful access. Maintain a clear boundary between full denial and authorized field-restricted representation.
3. **Returning JPA entities or domain objects directly.** Jackson may serialize newly added properties or nested relationships. Use response DTOs with explicitly selected fields; do not rely on implicit blacklists.
4. **Treating `@JsonIgnore` or `@JsonView` as a complete authorization decision.** They control static serialization or selected views, but the application must still authenticate the caller and enforce resource/field policies.
5. **Using different placeholders for missing data vs. forbidden view, accidentally leaking existence.** Decide clearly whether field existence may be known, then unify the representation.
6. **Masking phone numbers via substring without checking length.** Can throw exceptions or expose short numbers verbatim. Handle missing/invalid data with safe outputs.
7. **Checking only roles, ignoring object ownership.** Users should typically only see their own IDs even though both have `ROLE_USER`.
8. **Checking only GET endpoints, ignoring PATCH/PUT/POST.** Fields forbidden to read often need dedicated edit policies too; prevent mass assignment and over-privileged writes.
9. **Enabling public caching on principal-dependent responses.** Wrong caching can serve ADMIN's full response to less-privileged users.
10. **Writing verbose logs, exception messages, or debug responses containing the entire entity.** Masking JSON on the success path is insufficient if the error path still leaks data.

## 10. Pre-Release Decision Checklist

- [ ] Defined **object-level** and **per-attribute** permissions for real actors.
- [ ] Denied operations return 401/403/404 under a consistent policy; never silently fake a 200.
- [ ] Placeholders accurately convey meaning: missing data, restricted permission, or intentionally unknown data.
- [ ] Only approved parts are masked; passwords/tokens/secrets are never issued in masked form.
- [ ] Response DTOs act as an allowlist; raw domain entities, nested objects, and new fields do not leak out automatically.
- [ ] The same permissions apply across detail/list/search/export/error paths; counts and pagination do not bypass permissions.
- [ ] Tested at least owner, outsider, support, admin, anonymous, missing fields, and malformed fields.
- [ ] Checked logs, caches, tracing, API versions, and 403/404 differences that could leak info.
- [ ] When policy is indeterminate or fails, the system never defaults to relaxing permissions.

### References

- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Servlet Architecture / ExceptionTranslationFilter: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- OWASP API Security Top 10 2023 — API1/API3: https://api-security.owasp.org/editions/2023/en/0x11-t10/
- OWASP API3:2023 — Broken Object Property Level Authorization: https://github.com/OWASP/API-Security/blob/master/editions/2023/en/0xa3-broken-object-property-level-authorization.md

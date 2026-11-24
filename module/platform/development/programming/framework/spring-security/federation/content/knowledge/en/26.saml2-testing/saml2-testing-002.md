# saml2Login() in Testing and Customizing Principal, Attributes, and Authorities

## 1. Problem and Objectives

A Spring Boot application using **SAML 2.0 federation** lets users log in through an Identity Provider (IdP), receives an identity in `Saml2Authentication`, reads SAML attributes such as email/department, and then authorizes document reads or administrative actions. When writing tests, development teams typically want to verify:

- User Alice logs in via SAML and has the expected email/department.
- Alice has the employee role, and does not automatically receive the admin role.
- Ops users receive permissions granted through **application policy** rather than just because the IdP sent an `"admin"` string.
- Controllers receive a genuine `Saml2AuthenticatedPrincipal`, not merely a fake username via `@WithMockUser`.
- A user belonging to IdP/tenant A cannot by default view tenant B's data.
- Configuring `saml2Login()` does not bypass signature, issuer, audience, `InResponseTo`, or expiration checks during real integration tests.

**Key distinction from the very start:** `HttpSecurity.saml2Login(...)` is the **DSL for configuring the real SAML login flow** for the application. In `spring-security-test` version **6.5.x**, the `SecurityMockMvcRequestPostProcessors` API **does not have a `saml2Login()` factory** analogous to `oidcLogin()` or `oauth2Login()`. To run MockMvc tests at the controller/authorization layer with a **mocked** SAML principal, build `DefaultSaml2AuthenticatedPrincipal` + `Saml2Authentication` and use `.with(authentication(samlAuthentication))`. Projects or external libraries may define their own helper named `saml2Login()`; in that case, verify where the helper is imported from and whether it performs any cryptographic validation.

This lesson belongs to the **SAML2 Testing** group of the Spring Security – federation module. Its goal is to test **principals, attributes, and authorities** with Java 17+/Spring Boot 3.x/Spring Security 6.5, and then connect with integration tests that verify genuinely signed `SAMLResponse` payloads. SAML credentials, `example.test` URLs, and user data in this article are illustrative examples only.

## 2. Two Types of Testing and What They Can Prove

| Layer | Input request | Runs real OpenSAML/IdP protocol? | What is verified |
| --- | --- | --- | --- |
| **Service unit test** | `Saml2AuthenticatedPrincipal`/`Authentication` fixture | No | Claim mapping, authorization policy, tenant/ACL |
| **MockMvc controller/authorization slice** | `.with(authentication(samlAuth))` | **No** | URL rules, `@AuthenticationPrincipal`, JSON, HTTP 200/401/403, CSRF |
| **MockMvc running full application context** | May still use `authentication(...)` fixture | No if injecting a fixture | Wires MVC/security filter chain but **skips SAML XML verification** |
| **ACS integration with signed SAMLResponse** | POST `SAMLResponse` to `/login/saml2/sso/{registrationId}` | **Yes**, when using the real provider/validator | IdP key, signature, issuer, audience, timing, subject confirmation, `InResponseTo` |
| **End-to-end with test IdP** | Browser redirect/AuthnRequest/callback/Session | Yes | Federation flow and real proxy/cookie configuration |
| **Security negative tests** | Signed/tampered/expired/cross-audience messages | Yes at the integration layer | Fail closed when SAML validation fails |

**Never claim that a `.with(authentication(...))` test proves the XML signature is valid.** It pre-builds a Spring Security `Authentication`, which is exactly what mocking is for. The SAML provider never receives a `SAMLResponse` to re-verify.

Conversely, there is no need to spin up an IdP and X.509 keys for every controller test just to prove "an employee cannot call the admin API." Choosing the right test layer keeps the suite fast without conflating unit tests with SSO integration.

## 3. Distinguishing the Two Commonly Confused Uses of saml2Login()

### 3.1. Production DSL: `HttpSecurity.saml2Login`

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
}
```

This snippet configures Spring Security as a **SAML 2.0 Relying Party/Service Provider**. It requires a defined or auto-configured `RelyingPartyRegistrationRepository`, IdP metadata/verification certificates, entity IDs, and an ACS endpoint; when a browser logs in, redirect/AuthnRequest/Response/Assertion exchanges occur.

### 3.2. MockMvc: No Built-in saml2Login Post-Processor in 6.5

In Spring Security Test 6.5, the familiar factories include:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.*;

user("alice");                 // UsernamePasswordAuthenticationToken
oauth2Login();                 // OAuth2AuthenticationToken / OAuth2User
oidcLogin();                   // OIDC principal
jwt();                         // JwtAuthenticationToken
authentication(myAuthentication); // Custom Authentication
securityContext(myContext);       // Custom SecurityContext
```

This is an **API illustration snippet**, not a complete Java file. There is no standard factory allowing you to write:

```java
// WRONG if you only have spring-security-test 6.5:
mvc.perform(get("/api/me").with(saml2Login()));
```

The right approach without relying on external helper libraries:

```java
Saml2Authentication saml = createSamlFixture(...);

mvc.perform(get("/api/me")
        .with(authentication(saml)));
```

If your project defines a custom helper named `saml2Login()`, it should **return a `RequestPostProcessor` using `authentication(...)`**, and the helper's name and scope must be clearly documented. Do not mistakenly import `oidcLogin()` to simulate a SAML user.

## 4. Key Spring Security Classes to Know

| Class/interface | Abbreviated package | Responsibility |
| --- | --- | --- |
| `Saml2Authentication` | `...saml2.provider.service.authentication` | Authenticated SAML token, principal, response XML, authorities |
| `Saml2AuthenticationToken` | Same package | Input token holding an **unverified** `SAMLResponse`, used in the authentication pipeline |
| `Saml2AuthenticatedPrincipal` | Same package | SAML principal: `getName()`, `getAttributes()`, `getAttribute()`, `getFirstAttribute()`, registration |
| `DefaultSaml2AuthenticatedPrincipal` | Same package | Convenient implementation for **fixtures/tests** and Spring Security 6.x |
| `SimpleGrantedAuthority` | `org.springframework.security.core.authority` | A single authority such as `ROLE_EMPLOYEE` |
| `SecurityMockMvcRequestPostProcessors.authentication` | `org.springframework.security.test.web.servlet.request` | Attaches an arbitrary `Authentication` to a MockMvc request |
| `@AuthenticationPrincipal` | `org.springframework.security.core.annotation` | Injects the current request's principal into a controller |
| `@WithMockUser` | `spring-security-test` | Simulates a standard user, **does not automatically provide SAML attributes** |
| `RelyingPartyRegistration` | `...saml2.provider.service.registration` | Contract between SP and IdP: issuer/keys/ACS/entity IDs |
| `OpenSaml4AuthenticationProvider` or `OpenSaml5AuthenticationProvider` | Version-dependent | Processes/validates SAML XML in the real flow |

In **Spring Security 6.5**, `DefaultSaml2AuthenticatedPrincipal` has constructor `(String name, Map<String,List<Object>> attributes)` and method `setRelyingPartyRegistrationId(String)`. When constructing `Saml2Authentication`, the third argument is a **Collection of GrantedAuthority**, not a `roles` Map.

Upgrade note: the **Spring Security 7.1.x** branch marks `Saml2AuthenticatedPrincipal` and `DefaultSaml2AuthenticatedPrincipal` as deprecated and points toward `Saml2ResponseAssertionAccessor`/`Saml2AssertionAuthentication` for some use cases. **Do not mechanically copy 6.5 code to 7.1**; pin versions and review the migration guide.

## 5. SAML Data Structure Inside the Principal

After a SAML Response is verified, a SAML principal may contain:

```text
name / NameID      = idp-user-1001
registrationId     = corp
attributes:
  email            = [alice@example.test]
  department       = [engineering]
  groups           = [reports, employees]
  employeeNumber   = [E-1001]
authorities:
  ROLE_EMPLOYEE
  REPORT_READ
```

Three **distinct** concepts:

- `principal.getName()`: usually derived from the **SAML NameID** or customized per provider/policy. Not necessarily an email or internal username.
- `principal.getAttributes()`: `Map<String,List<Object>>` from the SAML `AttributeStatement`; an attribute can be **multi-valued**.
- `authentication.getAuthorities()`: **Spring Security `GrantedAuthority`** instances used to evaluate `hasRole`/`hasAuthority`; do not blindly equate every IdP group value with app roles.

For example, `groups=[admins]` in a SAML attribute **does not automatically grant `ROLE_ADMIN`**. Mapping groups → authorities must live in a server-side converter/policy that has verified the issuer/registration/tenant and local entitlements.

### Identity of NameID

A NameID can be a transient/persistent ID, email format, or another format agreed upon with the IdP. Do not force `getName()` to be an email if the system uses an opaque persistent NameID. If the app needs a local user, establish a reliable mapping:

```text
verified IdP issuer + registration + SAML NameID
           |
           v
local identity link / provisioning
           |
           v
local userId + active status + tenant memberships
           |
           v
business roles/permissions/ACL
```

## 6. Dependencies for the Example

For a **Spring Boot 3.x, Java 17+, Spring Security 6.5.x** project with the corresponding Gradle plugin/BOM:

```groovy
repositories {
    mavenCentral()
    // Depending on OpenSAML dependencies, the Shibboleth repository may be needed.
    maven { url "https://build.shibboleth.net/maven/releases/" }
}

dependencies {
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.boot:spring-boot-starter-security"
    implementation "org.springframework.security:spring-security-saml2-service-provider"

    testImplementation "org.springframework.boot:spring-boot-starter-test"
    testImplementation "org.springframework.security:spring-security-test"
}
```

This is a **`build.gradle` snippet**, omitting plugins/BOM/Java toolchain, so it is not a standalone build file. Spring Boot dependency management must select a compatible version set; avoid forcing `spring-security-test` version 7 if the runtime is Spring Security 6.5.

If using Maven, add the equivalent artifacts and let the BOM manage versions. Do not place IdP private keys or production SAMLResponses into the test repository.

Check dependency versions:

```bash
./gradlew dependencyInsight \
  --dependency spring-security-test \
  --configuration testRuntimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-saml2-service-provider \
  --configuration testRuntimeClasspath
```

## 7. Building SAML Fixtures Manually for MockMvc

This is a **complete Java snippet for a helper class** used in `src/test/java/demo/saml/SamlFixtures.java`. All attributes are declared as `Map<String,List<Object>>`; authorities are Spring Security `GrantedAuthority` instances:

```java
package demo.saml;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication
        .DefaultSaml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2Authentication;

public final class SamlFixtures {

    private SamlFixtures() {
    }

    public static Saml2Authentication authenticated(
            String name,
            String registrationId,
            Map<String, List<Object>> attributes,
            String... authorityNames) {

        Map<String, List<Object>> copied = new LinkedHashMap<>();
        attributes.forEach((key, values) ->
                copied.put(key, List.copyOf(values)));

        DefaultSaml2AuthenticatedPrincipal principal =
                new DefaultSaml2AuthenticatedPrincipal(name, copied);
        principal.setRelyingPartyRegistrationId(registrationId);

        Collection<GrantedAuthority> authorities = new ArrayList<>();
        for (String roleOrPermission : authorityNames) {
            authorities.add(new SimpleGrantedAuthority(roleOrPermission));
        }

        // XML data is just a dummy string: .with(authentication(...))
        // Does NOT parse it, does NOT run OpenSAML or verify signatures.
        String unverifiedTestXml = "<test-only-not-saml-response/>";
        return new Saml2Authentication(
                principal, unverifiedTestXml, authorities);
    }

    public static Map<String, List<Object>> aliceAttributes() {
        return Map.of(
                "email", List.of((Object) "alice@example.test"),
                "department", List.of((Object) "engineering"),
                "groups", List.of((Object) "reports", "employees"));
    }
}
```

Note: Java imports cannot split **a qualified class name** across two lines cleanly in all editors without care. When copying into an IDE, the two imports `org.springframework.security.saml2.provider.service.authentication.DefaultSaml2AuthenticatedPrincipal` and `...Saml2Authentication` above should each sit on a single line. Written cleanly:

```java
import org.springframework.security.saml2.provider.service.authentication.DefaultSaml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
```

**Fixture rules:**

1. Build the principal with the **NameID**, attributes, and `registrationId` appropriate for the use case.
2. Supply authorities explicitly; do not derive them from attributes when writing mock controller tests.
3. Use dummy XML only because the test does not invoke the SAML provider; never send that payload to an ACS endpoint.
4. Never copy production SAMLResponses/NameIDs/sessions into fixtures.
5. If the app changes principal types when upgrading to Security 7.1, update fixtures to match the type the real app uses.

### An Alice Fixture

```java
Saml2Authentication alice = SamlFixtures.authenticated(
        "idp-user-1001",
        "corp",
        SamlFixtures.aliceAttributes(),
        "ROLE_EMPLOYEE",
        "REPORT_READ");
```

`alice.getName()` returns `idp-user-1001`. `getPrincipal()` is the SAML principal; `getAuthorities()` contains `ROLE_EMPLOYEE` and `REPORT_READ`, **and does not contain `ROLE_ADMIN`**.

## 8. Spring Boot Controller Reading Principal and Attributes

Example API/controller in `src/main/java/demo/saml/ProfileController.java`:

```java
package demo.saml;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProfileController {

    @GetMapping("/api/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        String email = principal.getFirstAttribute("email");
        List<Object> groups = principal.getAttribute("groups");
        String registrationId = principal.getRelyingPartyRegistrationId();

        return Map.of(
                "name", principal.getName(),
                "email", email == null ? "" : email,
                "registrationId", registrationId == null ? "" : registrationId,
                "groupCount", groups == null ? 0 : groups.size());
    }

    @GetMapping("/api/admin")
    public String admin(Authentication authentication) {
        return "admin=" + authentication.getName();
    }

    @GetMapping("/api/reports/{tenant}")
    public Map<String, String> reports(
            @PathVariable String tenant,
            Authentication authentication) {

        // DEMO: do not trust tenant from request or SAML claims
        // before mapping to local user/tenant membership.
        String localTenant = switch (authentication.getName()) {
            case "idp-user-1001" -> "north";
            case "idp-ops-1002" -> "north";
            default -> "none";
        };

        if (!tenant.equals(localTenant)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        return Map.of("tenant", tenant, "status", "visible");
    }
}
```

As in section 7, the wrapped import in this block should be written as **a single Java line**:

```java
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
```

When reading attributes:

- `getFirstAttribute("email")` may return `null` if the attribute is absent.
- `getAttribute("groups")` returns a list of values, **not a single `String`**.
- `getName()` is not necessarily equal to the email.
- `getRelyingPartyRegistrationId()` identifies the source registration in version 6.5.
- `Authentication.getAuthorities()` is used for authorization; do not map roles from raw untrusted strings inside a controller.

If an endpoint allows authenticated principals that are not SAML (e.g., OIDC login), `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` may be `null`. Separate routes/filter chains or handle multiple authentication types explicitly instead of risking a `NullPointerException`.

## 9. Production saml2Login() Configuration and HTTP Authorization

A Java 17+ `SecurityFilterChain`, running in a Spring Boot Servlet project:

```java
package demo.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain samlWeb(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .requestMatchers(HttpMethod.GET, "/api/reports/**")
                            .hasAuthority("REPORT_READ")
                        .requestMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .anyRequest().denyAll())
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
```

**This configuration requires a real `RelyingPartyRegistrationRepository`** in order to log in. The slice test example below **does not wire up the SAML Login filter**, because it only tests authorization for already-authenticated requests; testing the production config/ACS belongs in a separate integration layer.

`hasRole("ADMIN")` checks `ROLE_ADMIN`. `hasAuthority("REPORT_READ")` checks the exact string `REPORT_READ`, **without prepending `ROLE_`**. Therefore, a test fixture using `ROLE_EMPLOYEE` is denied access to `/api/admin`, whereas a fixture with `REPORT_READ` passes the URL guard on `/api/reports/**` and is then subject to local tenant checks.

### Illustrative IdP/RP Configuration

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "https://sp.example.test/saml2/metadata/corp"
            acs:
              location: "https://sp.example.test/login/saml2/sso/corp"
            assertingparty:
              metadata-uri: "https://idp.example.test/metadata"
```

The metadata URL on `example.test` is a non-existent placeholder; to run it, use a real test IdP/metadata and verify trust anchors/certificates, issuer/audience, ACS, and cookies/SAML request repository. Never replace the metadata URI with an arbitrary user-supplied URL.

## 10. MockMvc: Configuring a Slice Test Without Depending on an IdP

To test `ProfileController` and URL permissions without calling an IdP, use `@WebMvcTest` with a **test-only `SecurityFilterChain`**. It protects routes like production, **but does not configure `saml2Login`/IdP** inside the test slice; the SAML principal is supplied via `spring-security-test`. Clearly distinguish this as an **authorization test**, not a test of production SAML login wiring.

Save `src/test/java/demo/saml/ProfileControllerTest.java`:

```java
package demo.saml;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ProfileController.class)
@Import(ProfileControllerTest.TestAuthorizationSecurity.class)
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class TestAuthorizationSecurity {
        @Bean
        SecurityFilterChain testsOnly(HttpSecurity http) throws Exception {
            return http
                    .authorizeHttpRequests(auth -> auth
                            .requestMatchers(HttpMethod.GET, "/api/admin")
                                .hasRole("ADMIN")
                            .requestMatchers(HttpMethod.GET, "/api/reports/**")
                                .hasAuthority("REPORT_READ")
                            .requestMatchers(HttpMethod.GET, "/api/me")
                                .authenticated()
                            .anyRequest().denyAll())
                    .exceptionHandling(ex -> ex
                            .authenticationEntryPoint(
                                new HttpStatusEntryPoint(
                                    HttpStatus.UNAUTHORIZED)))
                    .build();
        }
    }

    @Test
    void aliceHasSamlNameIdAndMultivaluedAttributes() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ");

        mvc.perform(get("/api/me").with(authentication(alice)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("idp-user-1001"))
                .andExpect(jsonPath("$.email").value("alice@example.test"))
                .andExpect(jsonPath("$.registrationId").value("corp"))
                .andExpect(jsonPath("$.groupCount").value(2));
    }

    @Test
    void employeeCannotCallAdmin() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ");

        mvc.perform(get("/api/admin").with(authentication(alice)))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleIsExplicit() throws Exception {
        var ops = SamlFixtures.authenticated(
                "idp-ops-1002", "corp",
                Map.of("email", List.of((Object) "ops@example.test")),
                "ROLE_EMPLOYEE", "ROLE_ADMIN", "REPORT_READ");

        mvc.perform(get("/api/admin").with(authentication(ops)))
                .andExpect(status().isOk())
                .andExpect(content().string("admin=idp-ops-1002"));
    }

    @Test
    void aliceCannotReadSouthTenant() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ");

        mvc.perform(get("/api/reports/south")
                .with(authentication(alice)))
                .andExpect(status().isForbidden());
    }

    @Test
    void aliceCanReadNorthTenant() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ");

        mvc.perform(get("/api/reports/north")
                .with(authentication(alice)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenant").value("north"));
    }

    @Test
    void noSamlAuthenticationIsUnauthorized() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void missingReportAuthorityIsForbidden() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE");

        mvc.perform(get("/api/reports/north")
                .with(authentication(alice)))
                .andExpect(status().isForbidden());
    }

    @Test
    void forgedHeaderDoesNotGrantAdminRole() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ");

        mvc.perform(get("/api/admin")
                .header("X-Role", "ROLE_ADMIN")
                .with(authentication(alice)))
                .andExpect(status().isForbidden());
    }
}
```

**Static imports wrapped across lines for readability should be flattened onto single lines when creating real source files.** The five lines properly written:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
```

The test suite uses `spring-security-test` with `@WebMvcTest` auto-configured `MockMvc` and the filter chain. If building `MockMvcBuilders.standaloneSetup` separately, you must call `.apply(springSecurity())` or integrate the Spring Security `FilterChainProxy` properly.

### Prerequisites to Run

- Classes `SamlFixtures` and `ProfileController` must have the packages and paths shown above.
- Test dependencies must include JUnit Jupiter, Spring Boot Test, Spring Security Test, and Spring SAML service provider.
- The slice test must use the test `SecurityFilterChain` above, **not** scan a production chain that requires live IdP metadata.
- If the app brings in extra filters/beans via global imports, isolate the test context properly so tests do not attempt to fetch an external IdP.
- The test here **does not parse dummy XML**, which is expected since it tests controller/authorization logic.

Run command in a configured Gradle project:

```bash
./gradlew test --tests "demo.saml.ProfileControllerTest"
```

When dependencies and slice wiring are correct, the eight tests above verify 200/401/403 and principal/attributes/roles/tenant. Fixed test-runner stdout is not printed here because it varies with Gradle/JUnit version and build output.

## 11. Explaining getFirstAttribute and getAttribute

A SAML `AttributeStatement` can contain:

```xml
<saml:Attribute
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Name="groups">
  <saml:AttributeValue>reports</saml:AttributeValue>
  <saml:AttributeValue>employees</saml:AttributeValue>
</saml:Attribute>
```

After the IdP signature and SAML response are verified, `DefaultSaml2AuthenticatedPrincipal` in Spring 6.5 exposes:

```java
List<Object> groups = principal.getAttribute("groups");
Object first = principal.getFirstAttribute("groups");
Map<String, List<Object>> all = principal.getAttributes();
```

With the fixture above:

```text
groups=[reports, employees]
first=reports
```

**Do not force every attribute into a single String**. For a missing attribute, `getFirstAttribute` may return `null`; a multi-valued attribute needs either handling all values or an explicit first-value selection policy. If an attribute holds a custom XML/SAML value rather than a String, parse/convert per contract instead of blindly casting to String.

### Key/Namespace Collisions

SAML attributes have a `Name` and optionally a `NameFormat`/`FriendlyName`. Spring mapping may use `Attribute.Name` as the map key; another IdP might emit a URI/URN instead of short names like `email` or `groups`. For example:

```text
http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress
urn:oid:0.9.2342.19200300.100.1.3
email
mail
```

Only normalize attribute names **agreed upon in the profile of that specific IdP/registration**. Never use a fallback like "if any attribute contains the word admin, grant `ROLE_ADMIN`."

## 12. Customizing Principal Name: NameID, email, employeeId

`DefaultSaml2AuthenticatedPrincipal` in tests takes `name` directly. You can simulate:

```java
var principalByNameId = new DefaultSaml2AuthenticatedPrincipal(
        "opaque-nameid-981",
        Map.of("email", List.of((Object) "alice@example.test")));

var principalByLocalId = new DefaultSaml2AuthenticatedPrincipal(
        "local-user-42",
        Map.of("email", List.of((Object) "alice@example.test")));
```

Both fixtures have the same email yet **different `principal.getName()` values**. Tests should mirror the runtime converter. If production keeps the NameID, do not write unit tests pretending `getName()==email` just for convenience: such tests mask mapping bugs.

### Runtime Customization

In Spring Security 6.5/7.x, to customize the principal name after SAML validation, use an **authentication converter/delegating provider** appropriate for the release while preserving default signature/issuer/audience/recipient/time checks. Conceptually:

```text
Verified SAML assertion
  -> verified issuer + stable NameID
  -> local identity linking service
  -> local userId (allowed as principal name if policy permits)
  -> normalized attributes and authorities
  -> Saml2Authentication / application-specific Authentication
```

Never write a converter that inspects **unverified XML** or sets the principal from `request.getParameter("email")`. To map the principal name in Spring Security 7.1, inspect `ResponseAuthenticationConverter` and `Saml2ResponseAssertionAccessor`; the newer APIs supersede some older 6.x patterns.

## 13. RelyingPartyRegistrationId in Fixtures

With multiple IdPs or multiple tenants, `registrationId` distinguishes configurations:

```java
DefaultSaml2AuthenticatedPrincipal principal =
        new DefaultSaml2AuthenticatedPrincipal(
                "nameid-abc",
                Map.of("email", List.of((Object) "alice@example.test")));

principal.setRelyingPartyRegistrationId("partner-a");
```

Test another principal with `partner-b`: even with the same NameID/email, **it does not default to the same local account/roles**. Robust mapping typically relies on **verified IdP Entity ID/issuer + NameID + registration context**, not email alone.

In a test fixture, `setRelyingPartyRegistrationId("partner-a")` only sets a **string**; it does not prove a real registration exists or that an assertion was signed by the right IdP. Assertion verification and registration lookup must be verified in integration tests.

## 14. Custom Authorities Do Not Automatically Equal SAML Attributes

In Spring Security:

```text
hasRole("ADMIN")     -> requires authority ROLE_ADMIN
hasAuthority("ADMIN") -> requires authority ADMIN
hasAuthority("REPORT_READ") -> requires exact REPORT_READ
```

In a test:

```java
new Saml2Authentication(
    principal,
    "<dummy/>",
    List.of(new SimpleGrantedAuthority("ROLE_EMPLOYEE"),
            new SimpleGrantedAuthority("REPORT_READ")));
```

Do not write:

```java
// WRONG: Attribute map is not GrantedAuthorities.
Map.of("groups", List.of((Object) "admins"));
// then assume the request receives ROLE_ADMIN
```

Provider defaults may grant a baseline role such as `ROLE_USER` or a factor-indicating authority depending on the release; business permissions **should not rely on guessing defaults**. When testing business authorization, supply the exact set of authorities that the **production mapper** is designed to grant.

### Authority Granularity

Coarse roles: `ROLE_ADMIN`, `ROLE_EMPLOYEE`. Fine-grained permissions: `REPORT_READ`, `REPORT_APPROVE`, `DOCUMENT_EXPORT`. If the product uses the `SCOPE_` prefix for OAuth Bearer tokens, do not automatically map a SAML `scope` attribute into `SCOPE_ADMIN` without equivalent AS/local policy.

## 15. Testing Role Mapping from IdP Groups: Don't Mock the Very Logic Under Test

A common mistake:

```java
// Production mapper: groups -> authorities.
// Yet the test injects both groups AND pre-mapped authority.
.with(authentication(samlWithGroupAndAuthority("admins", "ROLE_ADMIN")));
```

Such a test **never runs the mapper**, so it will not catch a bug where the production mapper grants `ADMIN` too broadly.

The right way is to separate two layers:

1. **Unit test the group-to-authority converter:** pass **verified** identity/attributes, registration/issuer, and local policy, then assert roles. For example, group `employee` at partner A gets `ROLE_EMPLOYEE`, while `admin` from an unauthorized partner **does not** receive admin.
2. **MockMvc authorization test:** pass `Saml2Authentication` with **already-mapped** authorities, then assert whether the controller/endpoint allows or denies.
3. **ACS integration test:** run a signed `SAMLResponse` from a sandbox IdP through the real converter and assert the resulting authorities.

If you only have MockMvc fixtures, both (1) and (3) remain untested.

### Safe Mapping Policy

```text
allow ADMIN =
   sourceIssuerApprovedForAdminGroup
   AND registrationMappedToCorrectTenant
   AND stableSubjectLinkedToActiveLocalUser
   AND localEntitlementGrantsAdmin
   AND optional assurance/freshness requirements met
```

This is **pseudocode**, not runnable SpEL or Spring config. A SAML attribute containing the string `admin` **does not grant permissions on its own**.

## 16. Customizing Principals in Tests with a Clearly Named Helper

If a team wants syntax similar to `.with(saml2Login())`, they can write a **helper** returning a `RequestPostProcessor`. To avoid confusion with `HttpSecurity.saml2Login`, name it `withSamlAuthentication`:

```java
package demo.saml;

import java.util.List;
import java.util.Map;

import org.springframework.test.web.servlet.request.RequestPostProcessor;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.authentication;

public final class CustomSamlMockMvc {

    private CustomSamlMockMvc() {
    }

    public static RequestPostProcessor withSamlAuthentication(
            String name,
            String registrationId,
            Map<String, List<Object>> attributes,
            String... authorities) {
        return authentication(SamlFixtures.authenticated(
                name, registrationId, attributes, authorities));
    }
}
```

**Static import must be on a single complete Java line when copying:**

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
```

Usage:

```java
mvc.perform(get("/api/me")
        .with(CustomSamlMockMvc.withSamlAuthentication(
                "idp-user-1001",
                "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ")))
        .andExpect(status().isOk());
```

This is a **custom helper**, not a built-in Spring Security Test API. It only attaches a SAML-shaped authenticated principal to `SecurityContext`—it **does not generate an AuthnRequest and does not verify a SAMLResponse**. Avoid naming custom helpers as if they were official APIs that new team members might misunderstand.

## 17. With @WithMockUser: Why Is the Principal Type Different?

`@WithMockUser(username="alice", roles="USER")` creates a `UsernamePasswordAuthenticationToken` with `UserDetails`. Meanwhile, a SAML controller may expect:

```java
@GetMapping("/api/me")
public Map<String, Object> me(
        @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal)
```

If tested with `@WithMockUser`, the principal is not a `Saml2AuthenticatedPrincipal`; Spring may inject `null` or throw a type-specific error depending on configuration. Therefore, tests involving SAML attributes **should not treat `@WithMockUser` as a full substitute**.

For endpoints that **only check `hasRole`** and do not depend on principal type, `@WithMockUser(roles="EMPLOYEE")` remains useful as a generic test. However, whenever business code calls `getFirstAttribute("email")`, `getRelyingPartyRegistrationId()`, `getSessionIndexes()`, or distinguishes IdPs, you need a properly typed SAML fixture.

## 18. Creating a @WithMockSamlPrincipal Annotation for Large Test Suites

Beyond request-scoped `.with(authentication(...))`, Spring Security Test supports `@WithSecurityContext` and `WithSecurityContextFactory` to create reusable fixtures for tests at the method/service layers.

Annotation snippet:

```java
package demo.saml;

import java.lang.annotation.Retention;
import java.lang.annotation.Target;
import static java.lang.annotation.ElementType.METHOD;
import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RUNTIME)
@Target({ METHOD, TYPE })
@WithSecurityContext(factory = MockSamlSecurityContextFactory.class)
public @interface WithMockSamlPrincipal {
    String name() default "idp-user-1001";
    String registrationId() default "corp";
    String[] authorities() default { "ROLE_EMPLOYEE" };
}
```

Factory snippet:

```java
package demo.saml;

import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support
        .WithSecurityContextFactory;

public final class MockSamlSecurityContextFactory
        implements WithSecurityContextFactory<WithMockSamlPrincipal> {

    @Override
    public SecurityContext createSecurityContext(
            WithMockSamlPrincipal annotation) {

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(SamlFixtures.authenticated(
                annotation.name(),
                annotation.registrationId(),
                SamlFixtures.aliceAttributes(),
                annotation.authorities()));
        return context;
    }
}
```

Note the full import on **a single line**:

```java
import org.springframework.security.test.context.support.WithSecurityContextFactory;
```

Test:

```java
@Test
@WithMockSamlPrincipal(
        name = "idp-user-1001",
        registrationId = "corp",
        authorities = { "ROLE_EMPLOYEE", "REPORT_READ" })
void myServiceSeesSamlPrincipal() {
    // Service-under-test uses SecurityContextHolder
    // with mocked SAML principal/authorities.
}
```

**Limitation of this helper annotation:** it uses fixed `aliceAttributes()` for every subject. In a real project, allow configuring email/groups/tenant or provide multiple fixture builders; never use Alice's email on Bob's principal and conclude account linking works. `WithSecurityContextFactory` populates a test context—it **does not validate XML or an IdP**.

## 19. When to Use authentication(...) vs. securityContext(...)

Two approaches:

```java
mvc.perform(get("/api/me")
        .with(authentication(mySamlAuthentication)));
```

and:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(mySamlAuthentication);

mvc.perform(get("/api/me")
        .with(securityContext(context)));
```

`authentication(...)` is concise when you only need to attach a principal/authorities to one request. `securityContext(...)` is more flexible when testing custom details, custom `Authentication` implementations, or specialized contexts.

**MockMvc must be configured with Spring Security integration**. With `@WebMvcTest` + `@AutoConfigureMockMvc`/Spring Boot auto-configuration, the filter chain is usually wired automatically. When building MockMvc manually with `MockMvcBuilders`, official documentation specifies:

```java
mvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .build();
```

If this integration is omitted, `authentication(...)` may not be propagated into `SecurityContextHolder` as controllers/services expect. Never call `SecurityContextHolder.setContext(...)` inside a test method and forget to clear it afterward; that easily leaks users across tests. Use request post-processors or `@WithSecurityContext`.

## 20. @AuthenticationPrincipal vs. Authentication.getPrincipal()

In a controller:

```java
@GetMapping("/api/whoami")
public String whoami(
        Authentication authentication,
        @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
    return authentication.getName() + "|" + principal.getName();
}
```

`Authentication` exposes name, authorities, details, and token type. `@AuthenticationPrincipal` extracts the **principal object**. With `Saml2Authentication` in Spring Security 6.5, the principal is typically `Saml2AuthenticatedPrincipal`; its name may match `Saml2Authentication.getName()`.

However, not every authentication provider keeps the same principal type after custom conversion; some systems wrap the principal into a local `UserDetails` or domain-specific object. Therefore, decide the contract before writing controllers:

- SAML-specific controller: accepts `Saml2AuthenticatedPrincipal`, invoked only on SAML-protected routes.
- Multi-protocol controller: accepts `Authentication` or a normalized local domain principal.
- Business services: should take **local user ID + permissions**, avoiding direct coupling to XML/IdP NameIDs.

### Common Null and Generic Type Pitfalls

```java
String email = principal.getFirstAttribute("email");
List<Object> groups = principal.getAttribute("groups");
```

`getFirstAttribute` can return `null`; if a group attribute holds a non-String value, do not cast `(String) groups.get(0)` without type checking. When debugging, log **attribute names**, never dump raw assertions or PII.

## 21. Testing Multiple Attributes and Multi-Valued Groups

Do not test only a single value. An IdP may return:

```text
groups = [engineering, reports, beta-testers]
department = [platform]
email = [alice@example.test]
employeeId = []
```

Test cases should cover:

1. Single-valued attribute.
2. Multi-valued attribute preserving order/format if required by business contract.
3. Completely missing attribute → graceful null/empty handling.
4. Attribute present as an empty list.
5. Non-String attribute value → parser/mapper does not throw `ClassCastException`.
6. Two attribute keys sharing a `FriendlyName` but differing in `Name` → only accept the attribute name allowed by contract.
7. IdP A using URI attribute names while IdP B uses `email` → avoid cross-mapping mistakes.
8. Business group-to-authority mapper does not over-grant privileges when `"admins"` comes from an unapproved issuer.

**Accurate fixture data** does not make those groups trustworthy. Only once SAML integration has verified the IdP signature/issuer may the runtime mapper act on claims per policy.

## 22. Method Security and @PreAuthorize

In a production application:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

Service:

```java
@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_APPROVE')")
    public void approve(String reportId) {
        // Business validation, tenant/ownership, and transaction handling must be added.
    }
}
```

To genuinely test `@PreAuthorize`, the service must be a **Spring-managed proxy** and `@EnableMethodSecurity` must be active in the test context. Calling `new ReportService().approve(...)` skips the method authorization aspect **completely**.

A unit/slice test with `@WithMockSamlPrincipal`/`@WithSecurityContext` can supply the needed authorities, provided the test boots enough context to invoke the real proxied bean. Alternatively, use `MockMvc` to call a controller backed by the secured service method. Do not equate a route-level `hasAuthority` check with a business-object ACL: defending against BOLA/IDOR requires checking permissions against the specific `reportId`/tenant.

### Testing Denials

- Employee with only `REPORT_READ` calls `approve` → `AccessDeniedException`/403 depending on test layer.
- Approver with `REPORT_APPROVE` targeting a report in another tenant → still denied by local tenant/resource checks.
- IdP group `approvers` while local account is disabled → fail-closed.
- Machine token/Bearer API is not automatically treated as a SAML user.

## 23. MockMvc Testing HTTP 401, 403, and Redirects

With the **test-only chain** in section 10, `HttpStatusEntryPoint(UNAUTHORIZED)` returns HTTP 401 for anonymous tests; authenticated users missing an authority receive 403.

In a **production SAML chain**, an anonymous request to a protected URL typically:

1. Redirects to an IdP selection/login page.
2. Continues redirecting to `/saml2/authenticate/{registrationId}` and the IdP.
3. Establishes an application session after successful SSO.

Therefore, **do not claim every anonymous request in production must return 401**. The HTTP status depends on the entry point/configuration; the controller authorization slice uses a 401 entry point solely for deterministic assertions.

### Contract Verification by Layer

| Scenario | Authorization slice | Real SAML login |
| --- | --- | --- |
| No `Authentication` | 401 per test entry point | Redirect to login/IdP per config |
| Authenticated without role | 403 | 403 if SAML valid but role missing |
| Mock SAML principal with role | 200 | Not equivalent to signed `SAMLResponse` |
| Signed Response wrong audience | Not tested | Provider must reject |
| Signed Response wrong issuer/key | Not tested | Provider must reject |
| Missing CSRF on business POST | If CSRF enabled, 403 | Web CSRF policy must remain active |

## 24. CSRF in SAML2 Testing and Business POSTs

The SAML ACS is typically `POST /login/saml2/sso/{registrationId}` carrying `SAMLResponse` from the browser/IdP. Spring Security's SAML login DSL handles the callback **without requiring an application form CSRF token** at the protocol endpoint, while signature/issuer/recipient/`InResponseTo`/`OneTimeUse` serve as its dedicated protections.

**Do not disable CSRF across the entire application** just to let the SAML POST work. Business endpoints relying on session cookies remain vulnerable to CSRF.

Example testing a business POST:

```java
mvc.perform(post("/api/reports/approve")
        .with(authentication(approver))
        .with(csrf()))
    .andExpect(status().isOk());
```

This snippet assumes a controller/URL rule exists for the route and `post`/`csrf` are imported; it **does not initiate SAML login**. Calling the same POST without `csrf()` when default CSRF protection is enabled should be rejected (typically 403) before authorization/business logic runs.

`with(csrf())` only creates a test CSRF token; it **does not sign a SAML Response** and has no relationship to `SAMLRequest`/`RelayState`.

## 25. Integration Layer: POSTing a Signed SAMLResponse Through the ACS

To prove end-to-end SAML federation, you must use a **real SAML response payload signed by the test IdP key** alongside a `RelyingPartyRegistration` trusting the test certificate. Steps:

1. Configure a dedicated test IdP and RP metadata/IdP signing certificate in the application test profile.
2. Start an SP-initiated flow so `Saml2AuthenticationRequestRepository` stores the pending `AuthnRequest`.
3. The sandbox IdP generates a Response with valid `Response.ID`, `Assertion.ID`, `Issuer`, `Destination`, `AudienceRestriction`, `SubjectConfirmationData.InResponseTo`, and timestamps.
4. Sign the Response/Assertion per the trust contract and Base64-encode for HTTP-POST binding.
5. Submit the POST to the ACS within the **matching browser/session** along with `RelayState` if present.
6. Verify the HTTP login outcome, `SecurityContext`, principal name, attributes, authorities, and session cookie.
7. Send responses with bad signatures, expired timestamps, replays, or wrong audiences and confirm fail-closed behavior.

This MockMvc request snippet **only illustrates** how a real response is submitted, without generating signatures itself:

```java
mvc.perform(post("/login/saml2/sso/corp")
        .param("SAMLResponse", signedFixtureBase64)
        .param("RelayState", pendingRelayState)
        .session(initiatingBrowserSession))
    .andExpect(status().is3xxRedirection());
```

`signedFixtureBase64`, `pendingRelayState`, and `initiatingBrowserSession` must come from a properly configured **test harness**, not random strings. Never construct unsigned XML, Base64-encode it, and expect Spring Security to accept it. In integration tests, even a 302 status could be a redirect to an error page; always assert the **actual authentication success handler/state**, not merely 3xx.

### Critical Negative Fixtures

- Response missing a signature required by policy.
- Signature created with a key not in trusted IdP certs.
- Signed XML tampered with after signing.
- Issuer mismatching the registration.
- Audience mismatching the SP Entity ID.
- Recipient/Destination differing from the ACS.
- Expired Assertion or future `NotBefore`.
- Wrong `InResponseTo` or already-consumed `AuthnRequest`.
- Replayed `Response.ID`/`Assertion.ID`.
- XML Signature Wrapping or duplicate XML IDs.
- Multi-tenant/IdP registration mismatch.
- Disabled local account despite a valid SAML assertion.

MockMvc `authentication(...)` **cannot detect** any of these failures because it bypasses the SAML provider. Dedicated signed integration tests are mandatory.

## 26. Do Not Substitute Saml2AuthenticationToken for a Saml2Authentication Fixture

The two classes are not equivalent:

```java
Saml2AuthenticationToken tokenBeforeValidation = ...; // unverified
Saml2Authentication afterValidation = ...;             // authenticated
```

`Saml2AuthenticationToken` represents an inbound unverified `SAMLResponse`, where `isAuthenticated()` is `false`. `Saml2Authentication` represents the verified outcome in production, whereas in tests it may **be created as a fixture**.

Do not pass `Saml2AuthenticationToken` into MockMvc `.with(authentication(...))` expecting `authenticated()`/`hasRole` to behave like an authenticated SAML principal; and definitely never call `setAuthenticated(true)` on an unverified token just to "make tests pass."

In a real application, only the OpenSAML provider/`AuthenticationManager`—after verifying signature, conditions, audience, issuer, and subject confirmation—should issue an authenticated token. Test fixtures are an exception **confined strictly to test scope**.

## 27. @WithSecurityContextFactory and SecurityContext Lifecycle

A custom test annotation can populate `SecurityContext` at the start of a test method:

```text
@BeforeTestExecution:
  TestSecurityContextHolder holds Saml2Authentication fixture

Test:
  Controller/Service sees fixture when Spring Security Test is properly integrated

After test:
  SecurityContext is cleaned up by test infrastructure
```

Calling `SecurityContextHolder.setAuthentication(...)` manually without Spring Security Test risks leaking `ThreadLocal` state to subsequent tests, especially when the test runner reuses threads.

**Best practice** for per-request MockMvc is `.with(authentication(saml))`. For method-security tests with multiple invocations per test, `@WithMockSamlPrincipal`/a custom factory is more convenient. When upgrading to Security 7.1, principal interfaces have deprecations, so keep fixture builders isolated in one file for centralized updates.

## 28. Separating SAML Registrations and Multi-Tenant Tests

Suppose the system has:

```text
registrationId=corp, issuer=https://idp.corp.example.test
registrationId=partner, issuer=https://idp.partner.example.test
```

Principals sharing an email across two IdPs do not automatically represent the same local user:

```text
(corp,   NameID=A123, email=alice@example.test)
(partner,NameID=B777, email=alice@example.test)
```

Test cases:

1. Assert the exact `registrationId` on the principal after SAML login.
2. Assert local user mapping keys off issuer + stable NameID, not email alone.
3. Assert partner group `admin` does not grant `ROLE_ADMIN` in tenant `corp`.
4. Assert `/api/reports/north` denies a user belonging only to South.
5. Assert a disabled local account fails closed even if the IdP issues a fresh signed assertion.
6. Assert a `SAMLResponse` from Issuer B sent to the `corp` ACS is rejected in integration tests.
7. Assert the request repository/`RelayState` cannot cross-wire browsers or tenants.

A mock fixture can set any `registrationId`, so **never use a MockMvc auth fixture to claim issuer-to-registration signature validation is tested**.

## 29. Production Authority Mapping from Verified SAML Assertions

In Spring Security 6.x, depending on release/provider, extension points exist to customize the **response authentication converter**, or wrap/delegate the provider's post-validation result:

```text
OpenSAML validates Response/Assertion:
  signature + trusted issuer + destination/recipient
  + audience + subject confirmation + time + InResponseTo

Default response authentication conversion:
  verified NameID + SAML Attributes + base authorities

Application enrichment:
  verify local account link and tenant membership
  map approved attributes/groups to local permissions
  preserve trusted principal and avoid privilege escalation

Result:
  Saml2Authentication (or approved custom Authentication)
```

**Never disable default validation to add claims or authorities.** If creating a new `Saml2Authentication` after conversion in Security 6.x, still build from the validated principal/response and local policy. Avoid retaining raw `SAMLResponse` payloads in logs while debugging converters.

Exact APIs differ among `OpenSaml4AuthenticationProvider` in some 6.x releases, `OpenSaml5AuthenticationProvider` in 6.5/7.x, and `ResponseAuthenticationConverter` in the 7.1 branch. Consult the Javadoc of the active BOM instead of mixing lambda parameter types like `ResponseToken`/`AssertionToken`/`Saml2ResponseAssertionAccessor`.

### Guarding Multi-Valued Group Mapping

Mapping IdP groups to roles must never rely on substring matching:

```text
groups contains "admin" -> ROLE_ADMIN  // dangerous
```

Instead, use exact matching against an allowlisted issuer + group identifier:

```text
if verifiedIssuer == approvedCorpIdp
   AND groups contains exact configured group identifier
   AND localUser.active == true
   AND localUser.hasEntitlement("admin"):
       grant ROLE_ADMIN
```

This is pseudocode, not runnable SpEL. Role mapper tests should include `groups=["administered-project"]` and verify it **does not** grant admin via substring matching.

## 30. Standalone Java 17: Principal, Attributes, and Authorities Policy

For a **runnable example without Spring or an IdP**, the following program models a verified principal and enforces policy across email, registration, roles, and tenant. It **does not verify SAML XML** and does not replace Spring Security code; it only demonstrates how identity and permissions operate differently.

Save `SamlPrincipalPolicyDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class SamlPrincipalPolicyDemo {

    record Principal(
            String nameId,
            String registrationId,
            Map<String, List<String>> attributes,
            Set<String> authorities,
            String localTenant) {
    }

    static String firstAttribute(Principal principal, String key) {
        List<String> values = principal.attributes().get(key);
        return (values == null || values.isEmpty()) ? "" : values.get(0);
    }

    static boolean canRead(Principal principal, String tenant) {
        return principal != null
                && "corp".equals(principal.registrationId())
                && principal.authorities().contains("REPORT_READ")
                && principal.localTenant().equals(tenant);
    }

    static boolean canAdmin(Principal principal) {
        return principal != null
                && "corp".equals(principal.registrationId())
                && principal.authorities().contains("ROLE_ADMIN");
    }

    public static void main(String[] args) {
        Principal alice = new Principal(
                "idp-user-1001", "corp",
                Map.of(
                        "email", List.of("alice@example.test"),
                        "groups", List.of("reports", "employees")),
                Set.of("ROLE_EMPLOYEE", "REPORT_READ"),
                "north");

        Principal partner = new Principal(
                "partner-999", "partner",
                Map.of(
                        "email", List.of("alice@example.test"),
                        "groups", List.of("admins")),
                Set.of("ROLE_EMPLOYEE"), "south");

        System.out.println("nameId=" + alice.nameId());
        System.out.println("email=" + firstAttribute(alice, "email"));
        System.out.println("groupCount="
                + alice.attributes().get("groups").size());
        System.out.println("missingAttribute="
                + firstAttribute(alice, "employeeNumber").isEmpty());
        System.out.println("aliceCanReadNorth=" + canRead(alice, "north"));
        System.out.println("aliceCanReadSouth=" + canRead(alice, "south"));
        System.out.println("aliceIsAdmin=" + canAdmin(alice));
        System.out.println("partnerIsAdmin=" + canAdmin(partner));
        System.out.println("sameEmailDifferentIdentity="
                + !alice.nameId().equals(partner.nameId()));
    }
}
```

Run on Java 17+:

```bash
javac SamlPrincipalPolicyDemo.java
java SamlPrincipalPolicyDemo
```

**Exact** stdout:

```text
nameId=idp-user-1001
email=alice@example.test
groupCount=2
missingAttribute=true
aliceCanReadNorth=true
aliceCanReadSouth=false
aliceIsAdmin=false
partnerIsAdmin=false
sameEmailDifferentIdentity=true
```

This is a Java SE demo with deterministic output, completely decoupled from the SAML provider. `SamlFixtures` in section 7 is the Spring-specific fixture with similar semantics, though testing it through MockMvc requires Spring Boot/Security dependencies.

## 31. Testing Account Linking, Roles, and Tenants Across Attributes

A useful set of test cases:

| Case | NameID | Registration | Attributes | GrantedAuthority | Expected |
| --- | --- | --- | --- | --- | --- |
| Alice employee | A123 | corp | email, groups reports | ROLE_EMPLOYEE/REPORT_READ | Me=200, reports north=200, admin=403 |
| Alice missing email | A123 | corp | groups reports | ROLE_EMPLOYEE | Me handles empty/missing email, no NPE |
| Alice with 3 groups | A123 | corp | groups with 3 values | REPORT_READ | groupCount=3 |
| Ops admin | OPS7 | corp | verified ops identity | ROLE_ADMIN | admin=200 if granted by local policy |
| Partner with Alice's email | B999 | partner | same email as Alice | ROLE_EMPLOYEE | Does not auto-link to corp Alice |
| `"admins"` attribute but no local admin | C555 | partner | groups=[admins] | ROLE_EMPLOYEE | admin=403 |
| Disabled user | DIS9 | corp | valid signed attributes | No Authentication granted after local policy | Deny |
| Tenant South requests north | S001 | corp | tenant south | REPORT_READ | 403 local ACL |
| Anonymous | — | — | — | — | 401/redirect per entry point |
| UsernamePassword fixture | alice | — | No SAML attrs | ROLE_USER | Cannot test SAML attributes contract |

Methodology note: the 401/403 test cases in MockMvc only verify URL/controller policy. Tests for "signed SAML but disabled account" must exercise the converter/user directory at the appropriate layer; pre-authenticated fixtures bypass disabled-account validation.

## 32. Common Errors When Using saml2Login() in Tests

| Error | Cause | How to fix |
| --- | --- | --- |
| `Cannot resolve method saml2Login()` in `SecurityMockMvcRequestPostProcessors` | 6.5 API does not have this test post-processor | Construct `Saml2Authentication` and use `authentication(...)` |
| Importing `oidcLogin()` to fake SAML | Principal type becomes OIDC, not SAML | Use a proper SAML fixture |
| `@WithMockUser` causes `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` to be null | Principal type mismatch | `authentication(new Saml2Authentication(...))` |
| Testing group attribute as a `String` | SAML attribute is multi-valued | `Map<String,List<Object>>` and `getAttribute()` |
| Expecting name to equal email when fixture NameID is opaque | Wrong principal-name contract | Test proper NameID/local ID mapping |
| Missing `ROLE_` prefix with `hasRole` | `hasRole("ADMIN")` checks `ROLE_ADMIN` | Create the exact expected authority |
| Setting `groups=[admins]` and expecting admin | Attributes are distinct from authorities | Test mapper/local policy separately |
| Creating dummy XML fixture and POSTing to ACS | Provider rejects because unsigned/invalid | Use a signed IdP fixture |
| Assuming `authentication(...)` tests verify signatures | It pre-populates SecurityContext | Run integration tests through the SAML provider |
| Testing 3xx at ACS and calling it success | Could be redirecting to login error | Assert authenticated SecurityContext/handler outcome |
| Using unverified `Saml2AuthenticationToken` as authenticated token | Token `isAuthenticated=false` | Use a `Saml2Authentication` fixture |
| Test skips Spring Security filter chain | SecurityContext not injected properly | `@WebMvcTest` security config or `springSecurity()` |
| Slice test fetches IdP metadata from the Internet | Production config accidentally imported | Isolate test config/fixtures |
| Not testing missing attributes | NPE/cast failures | Test missing and multi-valued cases |
| Not testing cross-tenant access | BOLA/IDOR | Add local ACL/tenant tests |
| Test uses live production `SAMLResponse` | Credential/PII exposure and replay risk | Use sandbox IdP/dedicated signed fixtures |
| Spring 7.1 deprecation warnings | Principal/accessor APIs change across releases | Follow migration docs, isolate fixture builders |

## 33. Complete Layered Testing Matrix

### Unit and MockMvc Authorization

| Test | Input fields | Expected |
| --- | --- | --- |
| U1 | Fixed NameID | `Authentication.getName()` matches |
| U2 | Single-valued email attribute | `getFirstAttribute("email")` returns email |
| U3 | Multi-valued groups | `getAttribute("groups")` preserves list |
| U4 | Missing email | No NPE or privilege escalation |
| U5 | registrationId=corp | Response returns exact registration |
| U6 | Same email registrationId=partner | Does not auto-link corp user |
| U7 | Employee missing `ROLE_ADMIN` | 403 admin |
| U8 | Valid `ROLE_ADMIN` | 200 admin |
| U9 | `REPORT_READ` | 200 report for matching tenant |
| U10 | Missing `REPORT_READ` | 403 report |
| U11 | `REPORT_READ` but wrong tenant | 403 local ACL |
| U12 | Anonymous | 401 per test entry point |
| U13 | Browser spoofs `X-Role=ADMIN` | Does not alter `GrantedAuthority` |
| U14 | `@WithMockUser` instead of SAML fixture | Detects principal type mismatch |
| U15 | Role mapper group from another issuer | Does not grant admin |
| U16 | Disabled local account | Denied at user-linking/mapper layer |

### Integration and Federation

| Test | SAML input | Expected |
| --- | --- | --- |
| I1 | Valid signed Response from test IdP | Login succeeds |
| I2 | Unsigned Response | Rejected per profile |
| I3 | Tampered signature | Rejected |
| I4 | Unknown IdP signing certificate | Rejected |
| I5 | Wrong Issuer | Rejected |
| I6 | Wrong Audience | Rejected |
| I7 | Wrong Recipient/Destination | Rejected |
| I8 | Expired Assertion | Rejected |
| I9 | Future `NotBefore` | Rejected |
| I10 | `InResponseTo` mismatching AuthnRequest | Rejected |
| I11 | Session/`RelayState` not belonging to browser | Rejected |
| I12 | Replayed Response/Assertion | Rejected per anti-replay policy |
| I13 | XML Signature Wrapping | Does not accept unsigned/attacker-controlled node |
| I14 | IdP returns two values for groups | Attributes mapped per contract |
| I15 | IdP sends privilege-like group from unknown issuer | Does not over-grant local roles |
| I16 | Browser callback with SameSite/cookie policy | AuthnRequest correlation remains valid |
| I17 | Two IdP registrations with same email | No cross-tenant account linking |
| I18 | Approved key rotation | Properly accepts new trusted key |
| I19 | Revoked/unknown key | Rejected |
| I20 | SP session logout and re-login | No stale `SecurityContext` reuse |

**Fixture injection via `authentication(...)` belongs strictly in the Unit/MockMvc column**. All integration tests must use SAML XML validly signed or intentionally corrupted with test keys.

## 34. Writing Deterministic, Order-Independent Tests

Key principles:

- Create a fresh `Saml2Authentication` per test request; never share a mutable principal with `setRelyingPartyRegistrationId` across threads.
- Never store `SecurityContextHolder` statically/globally across tests; let the framework clean up.
- With `@WebMvcTest`, import the right test security config; if multiple `SecurityFilterChain` beans exist, verify matcher order.
- With `@SpringBootTest`, configure stable test RP/IdP metadata and avoid hitting uncontrolled external URLs at startup.
- Do not assert specific `JSESSIONID` values or treat XML signature bytes as invariant across runs.
- Do not assert only a 302 status code while ignoring the redirect target and `SecurityContext`.
- Do not use `MockMvcRequestBuilders.post` with unsigned XML and call it a "successful SAML login."
- If changing an attribute converter or role mapper, write converter unit tests **before** MockMvc fixtures.
- Use the Java 17 toolchain and BOM to align Spring Security Test with runtime versions.
- Browser/proxy HTTPS behavior may differ from MockMvc `http://localhost`; verify `{baseUrl}`, forwarded headers, and ACS URLs in integration tests.

## 35. Self-Check Questions

**1. Does `HttpSecurity.saml2Login()` create a mock user for MockMvc?**  
No. It configures the real Service Provider login flow.

**2. Does `spring-security-test` 6.5 include a standard `.with(saml2Login())` like `oidcLogin()`?**  
No, not in the inspected official `SecurityMockMvcRequestPostProcessors` API. Use `authentication(Saml2Authentication)` or a custom helper.

**3. Why is `@WithMockUser` insufficient?**  
It creates a UsernamePassword principal and does not contain SAML attributes/`registrationId` in a `Saml2AuthenticatedPrincipal`.

**4. Is the principal name always an email?**  
No. It may be an opaque NameID or a local ID produced by a converter, depending on contract.

**5. Why are attributes typed as `Map<String,List<Object>>`?**  
A SAML `Attribute` can have multiple `AttributeValue` elements; the provider retains a list.

**6. Does a SAML attribute `groups=[admins]` automatically become `ROLE_ADMIN`?**  
No. Authorities are assigned by a mapper/local IAM based on issuer, registration, and policy.

**7. What authority does `hasRole("ADMIN")` require?**  
Typically `ROLE_ADMIN`. `hasAuthority("ADMIN")` requires the exact string `ADMIN`.

**8. Does `authentication(new Saml2Authentication(...))` verify the IdP signature?**  
No; it is a mock authenticated token for authorization/controller tests.

**9. What must be done to test signature/audience/`InResponseTo`?**  
Submit a signed `SAMLResponse` through the ACS with a test IdP/keys, a pending AuthnRequest, and the real validator.

**10. Why are tenant authorization tests still needed after SAML login?**  
SAML authenticates identity; it does not prove a user may view reports/resources of another tenant.

**11. Must `springSecurity()` be called when building MockMvc manually?**  
Yes, when using `MockMvcBuilders` per documentation, so `SecurityContext` and the filter chain operate properly.

**12. What should be reviewed for Spring Security 7.1?**  
Deprecations of `Saml2AuthenticatedPrincipal`/`DefaultSaml2AuthenticatedPrincipal`, assertion/accessor APIs, and the migration guide.

## 36. Project Adoption Checklist

- [ ] Clearly distinguish `HttpSecurity.saml2Login` from MockMvc `authentication(...)`.
- [ ] Verify `spring-security-test` version matches runtime Security/BOM.
- [ ] Test principal type is SAML; do not use `@WithMockUser` to fake SAML attributes.
- [ ] Fixtures contain contract-compliant NameID, `Map<String,List<Object>>` attributes, `registrationId`, and `GrantedAuthorities`.
- [ ] Tests cover missing, single-valued, and multi-valued attributes as well as custom NameIDs.
- [ ] Roles are granted explicitly by policy, not inferred from arbitrary groups.
- [ ] `hasRole`/`hasAuthority` are tested with exact prefixes and permission names.
- [ ] Controller `@AuthenticationPrincipal` accepts the right type or handles multiple protocols.
- [ ] MockMvc runs inside a deny-by-default test `SecurityFilterChain`.
- [ ] Anonymous requests are tested for 401/redirect per each layer's actual entry point.
- [ ] Tests verify employee gets 403 on admin routes and approver gets 200 per permissions.
- [ ] Tests enforce local tenant/ACL checks even when the user is authenticated.
- [ ] Auth group/role mappers have dedicated unit tests instead of pre-populated fixture permissions.
- [ ] `@PreAuthorize` tests invoke Spring-managed proxied services, not `new`.
- [ ] CSRF on business POSTs is not disabled because of the SAML ACS.
- [ ] Integration tests exist with signed `SAMLResponse`/IdP sandbox plus negative signature/issuer/audience/time/`InResponseTo`/replay cases.
- [ ] Production `SAMLResponse` payloads and private signing keys are never used as test fixtures.
- [ ] Multi-IdP/tenant mapping preserves issuer/registration/NameID scoping.
- [ ] Unverified `Saml2AuthenticationToken` is never confused with post-validation `Saml2Authentication`.
- [ ] When upgrading to Spring Security 7.1, update fixture principal types per the migration guide.

## 37. References

- [Spring Security 6.5 — SecurityMockMvcRequestPostProcessors API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html): list of builders `user`, `oauth2Login`, `oidcLogin`, `jwt`, `authentication` (**no `saml2Login`**).
- [Spring Security — Running a Test as a User in Spring MVC Test](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `authentication(authentication)` and `securityContext(context)`.
- [Spring Security 6.5 — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): `springSecurity()` and `FilterChainProxy` integration.
- [Spring Security — MockMvc Request Post-processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html): standard test request processors.
- [Spring Security 6.5 — Saml2Authentication API](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2Authentication.html): principal/XML/authorities constructor.
- [Spring Security 6.5 — DefaultSaml2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/site/docs/6.5.6-SNAPSHOT/api/org/springframework/security/saml2/provider/service/authentication/DefaultSaml2AuthenticatedPrincipal.html): name, attributes, `registrationId` setter.
- [Spring Security 6.5 — Saml2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): `getAttribute`, `getFirstAttribute`, `registrationId`.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): provider, SAML authentication pipeline, and URL patterns.
- [Spring Security — SAML Authentication Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): customizing principal, attributes, granted authorities, and OpenSAML provider.
- [Spring Security 6.5 — SAML 2.0 Migrations to 7.0](https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html): response authentication converter migration.
- [Spring Security 7.1 — DefaultSaml2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/DefaultSaml2AuthenticatedPrincipal.html): deprecation and `Saml2ResponseAssertionAccessor`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`/`@WithSecurityContext`/factory.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF for business POSTs and web sessions.
- [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signatures, validation, replay, XML Signature Wrapping, trust boundaries.

# Setting Up MockMvc with Spring Security for a Service Provider Application

> **Module:** Spring Security – federation · **Parent topic:** SAML2 Testing. This Knowledge article guides you through setting up and using **MockMvc with Spring Security** to test a Java Servlet application acting as a **SAML 2.0 Service Provider (SP) / Relying Party (RP)**. The article clearly distinguishes two very different tasks: **simulating an authenticated principal** to test controllers, filter chains, and authorization; and **genuinely verifying a SAML Response** from the Identity Provider (IdP) at the Assertion Consumer Service (ACS). Never conclude from a `MockMvc.with(authentication(...))` test that SAML signatures, audience, recipient, expiration, or replay protection are secure.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain SP/RP, IdP/Asserting Party, `RelyingPartyRegistration`, `RelyingPartyRegistrationRepository`, AuthnRequest, SAMLResponse, and ACS.
2. Identify the default endpoints `/saml2/authenticate/{registrationId}` and `/login/saml2/sso/{registrationId}` in Spring Security 6.x; understand that custom configurations can change these paths.
3. Set up `spring-boot-starter-test`, `spring-security-test`, `spring-security-saml2-service-provider`, and `MockMvc` on Spring Boot 3.3.x with Java 17.
4. Use `@WebMvcTest` or `@SpringBootTest @AutoConfigureMockMvc` appropriately, preserving the Spring `FilterChainProxy` when testing authorization.
5. Use `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity())` when creating MockMvc manually; do not confuse it with `standaloneSetup` which lacks Spring Security.
6. Create a mock `Saml2Authentication` in tests via `DefaultSaml2AuthenticatedPrincipal` and `SecurityMockMvcRequestPostProcessors.authentication(...)`; distinguish this from the `user()` processor and `@WithMockUser`.
7. Write tests for anonymous redirect, principal, RP registration ID, role/authority, 403, CSRF, sensitive action POSTs, and preventing tenant data leakage.
8. Know how to verify the source IdP and RP registration in application logic, while not treating fields in a mock principal as verified signatures.
9. Use test slices with `@MockBean RelyingPartyRegistrationRepository` when testing only controllers/security without calling a real IdP; understand the limitations of a mocked repository.
10. Separate unit/slice tests, MockMvc filter-chain tests, ACS validation tests with a SAMLResponse **validly signed with a test key**, and end-to-end tests with a real IdP.
11. Recognize common pitfalls: `FilterChainProxy` not attached, `@WithMockUser` differing from a SAML principal, 302 instead of 401, 403 due to CSRF, wrong ACS route, expired test certificates, key rotation, invalid signatures, wrong audience/destination, and Response replay.
12. Design appropriate SAML fixtures, run tests with Gradle, build a test matrix, and define QA gates before promoting an SP to production.

**Example platform:** Java 17, Spring Boot 3.3.x, Spring Security 6.3.x/6.x, JUnit Jupiter, Mockito, and Spring MVC Test. API names may change in Spring Security 7.x; when upgrading versions, re-check the Javadoc and regression suite. The `.example`/`.test` URLs in this article are illustrative addresses, not live IdPs.

## 2. Problem: The SP App Logs In via SAML2—How to Test Without Starting an IdP?

An Orders Portal application has:
- `GET /health` public, used for health checks.
- `GET /api/me` restricted to users authenticated via SAML2 from IdP `corp`.
- `GET /api/admin/report` restricted to SAML principals of RP `corp` with local authority `APP_ADMIN`.
- `POST /api/admin/approve` as a sensitive action, requiring same-origin CSRF protection and authority `APP_ADMIN`.
- In production, the project receives a SAML Response from the IdP, links the identity to a local user, and verifies tenant/permissions.

In MVC tests, we do not want every JUnit run to require opening a browser, connecting to an IdP, issuing a ticket, and clicking login. We can **construct a `Saml2Authentication` directly in test code only** to invoke the controller under the same Spring Security filter chain.

However, such a test only proves what happens **after authentication has already succeeded**:

~~~text
MockMvc request
    |
    +-- with(authentication(fixtureSaml2Auth))
    |          |
    |          +-- SecurityContext for test request
    |
    +-- Spring Security FilterChainProxy
    |          |
    |          +-- CSRF / authorization / exception translation
    |
    +-- MVC controller
               |
               +-- response/status/body
~~~

It does **not** create a digitally signed `SAMLResponse` or invoke `OpenSaml4AuthenticationProvider` / parsers/validators at the ACS. Therefore, **additional testing layers** in sections 12–14 are required.

## 3. SAML2 Components You Should See in Tests

| Component | Real role | Which MockMvc test? |
| --- | --- | --- |
| `RelyingPartyRegistration` | Describes SP entity ID, ACS location, IdP entity ID, SSO URL, certificate, signing/decryption policies. | Test configuration/metadata/request generation with a real registration. |
| `RelyingPartyRegistrationRepository` | Stores multiple registrations, looked up by `registrationId`. | Can be mocked in controller tests; other tests must use a real registration. |
| `Saml2WebSsoAuthenticationRequestFilter` | Creates AuthnRequest from endpoint `/saml2/authenticate/{registrationId}`. | Verify redirect/Form POST and request params when using a real RP fixture. |
| `Saml2WebSsoAuthenticationFilter` | Receives `SAMLResponse` at ACS `/login/saml2/sso/{registrationId}`. | Test signed Response fixtures via `post(...)`, **do not bypass** the filter. |
| `Saml2AuthenticationToken` | Wraps Response content and registration before verification. | Only used in ACS integration tests with the real provider. |
| OpenSAML authentication provider | Verifies signatures, issuer, audience, timing, subject confirmation, decrypts when needed. | Must use a trusted test key, signed assertions/responses, and negative fixtures. |
| `Saml2Authentication` | Spring Security `Authentication` **after** SAML2 authentication has succeeded. | Can be constructed directly for controller/authorization tests. |
| `Saml2AuthenticatedPrincipal` | Principal containing NameID, attributes, and `relyingPartyRegistrationId`. | Test principal mapping and permissions; do not treat attributes as trusted when self-constructed. |
| `SecurityFilterChain`/`FilterChainProxy` | CSRF, authorization, sessions, exception handling. | Must be attached to MockMvc to verify HTTP path security. |

**Version note:** Spring Security 6.3 uses OpenSAML 4 in many default configurations; documentation for newer versions may describe OpenSAML 5. Exact provider class names should be checked against the dependency tree rather than hard-coding one version across all releases.

### 3.1. A Complete SAML Flow

~~~text
Browser -> SP /api/me (no session yet)
   SP -> /saml2/authenticate/corp
   SP -> IdP SSO endpoint (SAMLRequest/AuthnRequest)
   IdP authenticates user and signs SAML assertion/response
   Browser POST SAMLResponse -> SP /login/saml2/sso/corp
   SP/Spring validate:
     issuer, signature, trust key, InResponseTo, Destination,
     Recipient, Audience, Conditions, SubjectConfirmation, expiry
   SP creates Saml2Authentication, local identity/role mapping
   Browser has local session -> /api/me
~~~

Only the part **after the SP creates `Saml2Authentication`** is simulated by the `authentication(...)` processor. To test earlier steps, real SAML data must be sent and processed by the filter/provider.

## 4. Choosing the Right Test Scope

| Layer | Tools | Evidence gained | Not achieved |
| --- | --- | --- | --- |
| Java unit | JUnit, pure Java, Mockito. | Role/tenant mapping and pure policies. | No Servlet filters, HTTP, SAML validation. |
| MVC slice | `@WebMvcTest` + `@Import(SecurityConfig)` + MockMvc. | Controller JSON/status, CSRF and imported security filter chain, principal injection. | Does not by itself prove a signed SAML Response is valid. |
| Full app MockMvc | `@SpringBootTest @AutoConfigureMockMvc`. | ApplicationContext, controllers, filters, persistence test wiring per configuration. | No real IdP/browser/HTTPS by itself. |
| ACS protocol integration | MockMvc with RP registration + signed SAML fixtures. | Parser, signatures, issuer, audience, recipient, status/failure handler, session creation. | Does not test real external KDC/IdP/browser/proxy outside the app. |
| Federated end-to-end | Test IdP, browser, SP, TLS, proxy, session store. | Login/logout/metadata/clock/cert rotation across the system. | Slow, environment-dependent, does not replace negative unit tests. |

**Rule:** MockMvc is Spring MVC's HTTP testing interface. It does not automatically guarantee that a test passed through the right SAML filter; the way the request and SecurityContext are constructed determines the validation path.

## 5. Minimal Dependencies for Spring Boot + Spring Security Tests

### 5.1. Tutorial Project Structure

~~~text
saml-sp-mockmvc/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/spmock/
    │   ├── SpApplication.java
    │   ├── SpSecurityConfig.java
    │   └── SpController.java
    └── test/java/com/example/spmock/
        └── SpMockMvcTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-sp-mockmvc'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    // Some OpenSAML/Shibboleth artifacts require this repository
    // per the Spring Security guide on SAML2 dependencies.
    maven { url 'https://build.shibboleth.net/maven/releases/' }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

In `implementation`, **`spring-security-saml2-service-provider`** provides the `Saml2Authentication` API and SAML filters, while `spring-security-test` provides `SecurityMockMvcRequestPostProcessors.authentication(...)` and `SecurityMockMvcConfigurers.springSecurity()`.

Do not omit `spring-security-saml2-service-provider` from a test module that lacks the exact dependency and try to manually create classes with the same name. Do not use `javax.servlet` packages when running Spring Boot 3 / Jakarta Servlet.

**Project limitation:** `@WebMvcTest` below mocks `RelyingPartyRegistrationRepository` to focus on post-authentication HTTP routes. That is not a configuration for running the SP against a real IdP. If you want to run `bootRun`, add a real registration and certificate/metadata as in section 11.

## 6. Configuring the SP SecurityFilterChain

`src/main/java/com/example/spmock/SpApplication.java`:

~~~java
package com.example.spmock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpApplication {
    public static void main(String[] args) {
        SpringApplication.run(SpApplication.class, args);
    }
}
~~~

`src/main/java/com/example/spmock/SpSecurityConfig.java`:

~~~java
package com.example.spmock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication
        .LoginUrlAuthenticationEntryPoint;

@Configuration(proxyBeanMethods = false)
public class SpSecurityConfig {

    private static boolean approvedSaml(Authentication a) {
        if (!(a instanceof Saml2Authentication saml)
                || !saml.isAuthenticated()) {
            return false;
        }
        if (!(saml.getPrincipal()
                instanceof Saml2AuthenticatedPrincipal principal)) {
            return false;
        }
        return "corp".equals(
            principal.getRelyingPartyRegistrationId()
        );
    }

    private static boolean hasAuthority(
            Authentication a, String permission) {
        return a != null && a.getAuthorities().stream()
            .anyMatch(g -> permission.equals(g.getAuthority()));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/error").permitAll()
                .requestMatchers("/saml2/**", "/login/**").permitAll()
                .requestMatchers("/api/admin/**").access(
                    (authSupplier, context) -> {
                        Authentication user = authSupplier.get();
                        return new AuthorizationDecision(
                            approvedSaml(user)
                                && hasAuthority(user, "APP_ADMIN")
                        );
                    }
                )
                .requestMatchers("/api/**").access(
                    (authSupplier, context) ->
                        new AuthorizationDecision(
                            approvedSaml(authSupplier.get())
                        )
                )
                .anyRequest().denyAll()
            )
            .saml2Login(Customizer.withDefaults())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new LoginUrlAuthenticationEntryPoint(
                        "/saml2/authenticate/corp"
                    )
                )
            )
            .build();
    }
}
~~~

**Why check `Saml2Authentication` and `registrationId`?**

- `hasAuthority("APP_ADMIN")` alone proves a permission on any `Authentication`; sometimes an app needs to bind access to an approved RP/IdP.
- `approvedSaml` checks that authentication is marked authenticated, the SAML principal type, and registration ID `corp`.
- This is an **authorization-layer guard**, not a replacement for `Saml2WebSsoAuthenticationFilter` verifying SAML signatures before creating a real `Saml2Authentication`.
- In **tests**, we intentionally construct fixtures with registration ID `corp`; that is mock data. In **production**, you must keep SAML protocol validation, trust config, account linking, and a local authority mapper.
- Controllers must not grant admin permissions based solely on NameID/email. `APP_ADMIN` is a **sample local authority** that should be granted from a managed authorization store after identifying the right local user.
- `/saml2/**` and `/login/**` are routes of the SAML security flow; calling `permitAll` at the URL layer does **not** bypass validation in the SAML filters. Never create your own controller to accept `SAMLResponse` and return 200.
- `LoginUrlAuthenticationEntryPoint` enables exact testing of redirecting an anonymous user to the AuthnRequest initiation path. A multi-IdP SP usually needs a discovery/selection page or custom entry point.
- `@Configuration` imported via a test slice makes the real `SecurityFilterChain` take effect. Never disable security filters in `@AutoConfigureMockMvc` just because a test is hard to run.

### 6.1. Adjusting Java Imports for Easy Copying

Java allows line breaks at many points between tokens; however, to avoid confusion and make copying easier, these three `import` statements should be written on single lines in source files:

~~~java
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
~~~

If you use the exact source structure from section 6, replace the wrapped `import` statements with the three lines above. Formatting does not change the API.

## 7. Controller Using the SAML Principal and Local Permissions

`src/main/java/com/example/spmock/SpController.java`:

~~~java
package com.example.spmock;

import java.util.Map;
import org.springframework.security.core.annotation
    .AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication
    .Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SpController {

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(
            @AuthenticationPrincipal
            Saml2AuthenticatedPrincipal principal) {
        return Map.of(
            "subject", principal.getName(),
            "registrationId",
            principal.getRelyingPartyRegistrationId()
        );
    }

    @GetMapping("/api/admin/report")
    public String report() {
        return "report";
    }

    @PostMapping("/api/admin/approve")
    public String approve() {
        return "approved";
    }
}
~~~

In real source files, use single-line imports:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
~~~

**Note:** The `/api/me` controller assumes `SecurityConfig` only allows approved SAML principals through. If the application supports multiple authentication mechanisms, principal types must be handled intentionally instead of blindly casting. `principal.getName()` may be a NameID; in a real product, map it to a trusted local ID and do not default to using NameID/email as an authorization ID.

## 8. Slice Test: @WebMvcTest + MockMvc + Spring Security

`src/test/java/com/example/spmock/SpMockMvcTests.java`:

~~~java
package com.example.spmock;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet
    .WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority
    .SimpleGrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication
    .DefaultSaml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication
    .Saml2Authentication;
import org.springframework.security.saml2.provider.service.registration
    .RelyingPartyRegistrationRepository;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;

@WebMvcTest(controllers = SpController.class)
@Import(SpSecurityConfig.class)
@AutoConfigureMockMvc(addFilters = true)
class SpMockMvcTests {

    @Autowired
    MockMvc mvc;

    // Only mock metadata repository in the controller test layer.
    // Does not call a real IdP, does not verify a real SAMLResponse.
    @MockBean
    RelyingPartyRegistrationRepository registrations;

    static Saml2Authentication saml(
            String registrationId,
            String subject,
            String... permissions) {

        Map<String, List<Object>> attributes =
            Map.of("department", List.of((Object) "orders"));

        DefaultSaml2AuthenticatedPrincipal principal =
            new DefaultSaml2AuthenticatedPrincipal(
                subject, attributes
            );
        principal.setRelyingPartyRegistrationId(registrationId);

        List<GrantedAuthority> authorities = new ArrayList<>();
        for (String permission : permissions) {
            authorities.add(
                new SimpleGrantedAuthority(permission)
            );
        }

        // This string is ONLY stored in the mock Authentication.
        // Not sent via ACS and not signed SAML XML.
        return new Saml2Authentication(
            principal,
            "<test-only-not-a-real-saml-response/>",
            authorities
        );
    }

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void anonymousIsRedirectedToSamlInitiation() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(
                redirectedUrl("/saml2/authenticate/corp")
            );
    }

    @Test
    void approvedSamlPrincipalCanViewProfile() throws Exception {
        mvc.perform(get("/api/me").with(
                authentication(saml(
                    "corp", "subject-17", "APP_ORDER_READ"
                ))
            ))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("subject-17"))
            .andExpect(jsonPath("$.registrationId").value("corp"));
    }

    @Test
    void samlUserWithoutAdminPermissionGets403() throws Exception {
        mvc.perform(get("/api/admin/report").with(
                authentication(saml(
                    "corp", "subject-17", "APP_ORDER_READ"
                ))
            ))
            .andExpect(status().isForbidden());
    }

    @Test
    void samlAdminFromApprovedRpCanViewReport() throws Exception {
        mvc.perform(get("/api/admin/report").with(
                authentication(saml(
                    "corp", "subject-18", "APP_ADMIN"
                ))
            ))
            .andExpect(status().isOk())
            .andExpect(content().string("report"));
    }

    @Test
    void adminPermissionFromWrongRpGets403() throws Exception {
        mvc.perform(get("/api/admin/report").with(
                authentication(saml(
                    "unapproved", "subject-19", "APP_ADMIN"
                ))
            ))
            .andExpect(status().isForbidden());
    }

    @Test
    void ordinaryMockUserIsNotSamlPrincipal() throws Exception {
        mvc.perform(get("/api/admin/report").with(
                user("fake").roles("ADMIN")
            ))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminPostWithoutCsrfGets403() throws Exception {
        mvc.perform(post("/api/admin/approve").with(
                authentication(saml(
                    "corp", "subject-18", "APP_ADMIN"
                ))
            ))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminPostWithCsrfCanProceed() throws Exception {
        mvc.perform(post("/api/admin/approve")
                .with(csrf())
                .with(authentication(saml(
                    "corp", "subject-18", "APP_ADMIN"
                )))
            )
            .andExpect(status().isOk())
            .andExpect(content().string("approved"));
    }

    @Test
    void csrfDoesNotGrantPermission() throws Exception {
        mvc.perform(post("/api/admin/approve")
                .with(csrf())
                .with(authentication(saml(
                    "corp", "subject-17", "APP_ORDER_READ"
                )))
            )
            .andExpect(status().isForbidden());
    }
}
~~~

In a real Java file, `import` lines wrapped for display can be **rewritten on single lines**, for example:

~~~java
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication.DefaultSaml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
~~~

**Important regarding syntax:** Java allows whitespace between identifiers and dots in certain places, but **not** an arbitrary dot inserted inside a package/class name. To be safe, use the standard single-line import list above when copying. The test body uses Java 17, JUnit 5, and the Spring Security 6.x MockMvc API.

### 8.1. Meaning of Each Test Case

| Test | What it asserts | What it does NOT assert |
| --- | --- | --- |
| `healthIsPublic` | Public matcher and controller work. | Not yet SAML-related. |
| `anonymousIsRedirectedToSamlInitiation` | Unauthenticated request is directed to the SAML login-initiation route. | Does not prove AuthnRequest is signed or accepted by the IdP. |
| `approvedSamlPrincipalCanViewProfile` | Mock Saml2Authentication is attached to the request; controller sees subject/RP. | Does not validate XML/signatures. |
| `samlUserWithoutAdminPermissionGets403` | Local authorization blocks a principal lacking permission. | Does not prove permissions from the IdP were mapped correctly. |
| `samlAdminFromApprovedRpCanViewReport` | Policy allows a test principal with RP+permission. | Does not prove an attacker cannot forge an assertion. |
| `adminPermissionFromWrongRpGets403` | RP registration ID guard blocks a test principal from another source. | Registration ID is a test fixture; provider trust must be tested separately. |
| `ordinaryMockUserIsNotSamlPrincipal` | `UsernamePasswordAuthenticationToken` does not substitute for `Saml2Authentication`. | Proves nothing about production LDAP/password auth. |
| `adminPostWithoutCsrfGets403` | CSRF filter runs on the business POST endpoint. | Does not verify ACS CSRF exception or SAML assertion. |
| `adminPostWithCsrfCanProceed` | CSRF + valid authentication and authority allow POST. | Does not prove the transaction service implementation. |
| `csrfDoesNotGrantPermission` | Having a CSRF token does not grant `APP_ADMIN`. | Does not replace object-level permissions. |

### 8.2. Run Commands

If a Gradle wrapper is present:

~~~bash
./gradlew test --tests com.example.spmock.SpMockMvcTests
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.spmock.SpMockMvcTests
~~~

**Expectation:** JUnit runs 10 test methods, normally all green if dependencies, slice configuration, and versions are right. This is an expectation from the sample code, **not a claim that tests were executed against a real repository or IdP**. If compilation fails after changing versions, check imports/classes in `spring-security-saml2-service-provider`, `spring-security-test`, and Boot/BOM compatibility.

## 9. MockMvc Setup Patterns: Do Not Let the Filter Chain Disappear

### 9.1. `@WebMvcTest` and `@AutoConfigureMockMvc`

In the slice test in section 8:

~~~java
@WebMvcTest(controllers = SpController.class)
@Import(SpSecurityConfig.class)
@AutoConfigureMockMvc(addFilters = true)
class SpMockMvcTests {
    @Autowired MockMvc mvc;
}
~~~

- `@WebMvcTest` initializes the MVC slice rather than all repositories/services.
- `@Import(SpSecurityConfig.class)` brings the SP's rules and `SecurityFilterChain` into the slice.
- `@AutoConfigureMockMvc(addFilters = true)` explicitly specifies that test requests must pass through Servlet filters.
- `@MockBean RelyingPartyRegistrationRepository` supplies the collaborator needed to build SAML login filters **without real IdP metadata** in controller tests. It holds no real registration data and cannot be used to test `/saml2/authenticate/corp`.
- When service/domain logic is needed, use `@MockBean` appropriately and assert interactions/side effects; do not mock every authorization service if the test intends to check real authorization.

**Version note:** Spring Boot 3.3 has `@MockBean`; newer Boot releases introduce replacement mock bean mechanisms and deprecations. When upgrading dependencies, apply the equivalent mechanism for that version.

### 9.2. `@SpringBootTest @AutoConfigureMockMvc`

When testing full-application wiring:

~~~java
@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class FullSpMockMvcIntegrationTests {
    @Autowired MockMvc mvc;
}
~~~

There is no need to create a separate `MockMvcBuilders.standaloneSetup(...)`; the auto-configured MockMvc already integrates the application context's filters. This fits testing repositories, tenant mapping, real session policy, or transaction services.

However, the **full context may require IdP metadata/certificates**. Use trusted test-profile RP registrations/fixtures, not a live production IdP, just to boot JUnit. If `@SpringBootTest` attempts to fetch metadata from a public URL, separate test configuration from the production registration.

### 9.3. Creating MockMvc Manually the Right Way

When building manually from `WebApplicationContext`:

~~~java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;

// In @BeforeEach, after @Autowired WebApplicationContext context:
this.mvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Use a single-line static import in a real Java file:

~~~java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
~~~

`springSecurity()` integrates the `springSecurityFilterChain` bean and Spring Security's `TestSecurityContext` holder into MockMvc. When tests use `authentication(...)`/`user(...)`, the SecurityContext is propagated into the filter chain properly only when this configuration or equivalent integration is active.

**Do not add `springSecurity()` twice** if Boot has already auto-registered filters; avoid duplicate filtering and hard-to-diagnose CSRF test issues.

### 9.4. Mistake: Using `standaloneSetup(controller)` and Thinking Security Is Tested

~~~java
// WRONG if the goal is to test the real SecurityFilterChain:
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new SpController())
    .build();
~~~

Without `FilterChainProxy`, requests can reach the controller directly, bypassing CSRF/authorization; a `200 OK` test while unauthenticated creates **false confidence**.

`standaloneSetup` can be useful for pure MVC unit tests, **but its scope must be stated clearly** and never used as authorization evidence. If filters are needed, prefer `webAppContextSetup(...).apply(springSecurity())` or Boot's auto-configured MockMvc.

## 10. Creating the Right Kind of Saml2Authentication Fixture

### 10.1. Why Not Just Use `@WithMockUser`?

`@WithMockUser` creates a Spring Security `Authentication` for a mock username/roles (typically user/password style). It does not carry:
- `Saml2AuthenticatedPrincipal` with SAML attributes;
- `getRelyingPartyRegistrationId()`;
- NameID, SessionIndex in principal data;
- the SP's `Saml2Authentication` type.

It may suffice for a protocol-independent controller using only `@PreAuthorize("hasRole(...)")`, **but it is insufficient** if code actually reads SAML attributes or must ensure authentication came from an approved RP.

### 10.2. Using `authentication(...)`

~~~java
DefaultSaml2AuthenticatedPrincipal p =
    new DefaultSaml2AuthenticatedPrincipal(
        "subject-17",
        Map.of("department", List.of((Object) "orders"))
    );
p.setRelyingPartyRegistrationId("corp");

Saml2Authentication a = new Saml2Authentication(
    p,
    "<test-only-not-a-real-saml-response/>",
    List.of(new SimpleGrantedAuthority("APP_ORDER_READ"))
);

mvc.perform(get("/api/me").with(authentication(a)))
    .andExpect(status().isOk());
~~~

The `saml2Response` string in `Saml2Authentication` is just a data field inside the fixture; **the constructor does not parse/verify XML**. Using a string that is clearly not real SAML XML further reminds learners that this is a **test authentication fixture**, not an ACS authentication success.

### 10.3. Using Factories to Avoid Duplication and Reduce False Positives

You can place helpers in `src/test/java/.../SamlFixtures.java`:

~~~java
// SNIPPET factory used in test source:
static Saml2Authentication samlReader(
        String relyingParty, String immutableSubject) {
    DefaultSaml2AuthenticatedPrincipal principal =
        new DefaultSaml2AuthenticatedPrincipal(
            immutableSubject,
            Map.of("department", List.of((Object) "orders"))
        );
    principal.setRelyingPartyRegistrationId(relyingParty);
    return new Saml2Authentication(
        principal, "<test-only/>",
        List.of(new SimpleGrantedAuthority("APP_ORDER_READ"))
    );
}
~~~

- Use synthetic subjects/NameIDs that are deterministic per test.
- `APP_*` permissions in fixtures must be **local authorities** per app policy; do not blindly copy arbitrary group strings as trusted.
- Test multiple RPs/tenants to catch negative cases.
- Do not use an overly powerful fixture (admin by default) for every test because it masks authorization bugs.
- Do not store raw SAML Assertions, private keys, or session tokens in test logs outside isolated environments.

## 11. AuthnRequest Endpoint and RelyingPartyRegistration: Test Separately

### 11.1. AuthnRequest Initiation Endpoint

The default path is usually:

~~~text
GET /saml2/authenticate/corp
     |
     v
Saml2WebSsoAuthenticationRequestFilter
     |
     v
RelyingPartyRegistrationRepository.findByRegistrationId("corp")
     |
     v
Generate SAML2 AuthnRequest
     |
     v
HTTP Redirect to IdP SSO URL
with SAMLRequest + optional RelayState + optional Signature
~~~

For a registration with HTTP-POST request binding, the server may return an auto-submitting HTML form instead of a Redirect. Do not write a test that **always** expects 302 if the project chooses POST binding.

### 11.2. Testing a Real Registration Instead of an Empty Mockito Repository

To test AuthnRequest generation, a test registration needs at least:
- `registrationId=corp`;
- SP `entityId` and ACS URL;
- IdP `entityId` / `SingleSignOnServiceLocation`;
- required binding;
- AuthnRequest signing if required by the IdP, using a **test signing credential**;
- IdP verification certificate if the same registration is used in ACS tests.

Example Spring Security Boot configuration:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              entity-id: "https://idp.example.test/entity"
              singlesignon:
                url: "https://idp.example.test/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "classpath:test-idp.crt"
~~~

**`test-idp.crt` must be an actual certificate fixture** and the corresponding signer key must belong to the **test IdP**. This configuration is incomplete if the file has not been created; never copy an untrusted certificate or disable signature checks. In production, obtain official certificates/metadata and trust anchors from the approved IdP and manage rotation.

### 11.3. Redirect Binding Test Snippet

Once a real registration is supplied, you can test along these lines:

~~~java
// SNIPPET integration test; do not run with an empty @MockBean repo.
mvc.perform(get("/saml2/authenticate/corp"))
    .andExpect(status().is3xxRedirection())
    .andExpect(header().string(
        "Location",
        org.hamcrest.Matchers.startsWith(
            "https://idp.example.test/sso?"
        )
    ));
~~~

Safely decode `SAMLRequest` (URL-decode, Base64, DEFLATE for HTTP-Redirect binding) to confirm:
- `Issuer` is the SP's entity ID per the registration;
- `Destination` is the approved IdP SSO endpoint;
- ACS URL, binding, and request ID have appropriate format/randomness;
- If signed requests are required: verify the signature per the binding profile;
- `RelayState` does not lead to open redirect or session mix-up;
- If multiple RPs exist: each request uses the right issuer/ACS/trust bundle.

**Do not just assert a 302 response and conclude that the AuthnRequest is signed and correct.**

## 12. ACS Tests: A Base64 Mock SAMLResponse Is Not Authentication Success

### 12.1. Endpoint Receiving SAMLResponse

Typically the SP receives:

~~~http
POST /login/saml2/sso/corp HTTP/1.1
Content-Type: application/x-www-form-urlencoded

SAMLResponse=<Base64-encoded-SAML-Response>
~~~

`Saml2WebSsoAuthenticationFilter` reads the parameter, resolves `RelyingPartyRegistration`, creates a token, and passes it to the provider for verification. Version details/ordering may vary, but security verification conditions must not be skipped:
- trusted issuer/entity ID and verifying certificate;
- XML signature on Response/Assertion per profile;
- audience restriction matching SP entity ID;
- Destination/Recipient matching ACS URL;
- InResponseTo/AuthnRequest binding per IdP-initiated/SP-initiated policy;
- Conditions: NotBefore/NotOnOrAfter, SubjectConfirmationData;
- replay/reuse of Assertion ID/Response ID per policy and cache;
- subject mapping, tenant isolation, local account status, authority mapping;
- parser hardened against XXE/oversized XML and approved clock skew limits.

### 12.2. What Not to Do in Tests

~~~java
// WRONG: send Base64 from hand-crafted XML then mock AuthenticationManager
// returning an admin principal and concluding "signature verified".
mvc.perform(post("/login/saml2/sso/corp")
    .param("SAMLResponse", base64OfUnsignedXml));
~~~

Such a test can be useful for exercising failure paths, **but it does not prove a valid assertion**. If you replace `AuthenticationManager` with a Mockito stub that always returns success, you are bypassing the provider—just like `with(authentication(...))`.

### 12.3. Building Proper Signed Fixtures

A real SAML validation suite should have:
1. A key pair and certificate **for test use only**, not production private keys.
2. An RP registration pointing to the test IdP's public cert.
3. A generator/OpenSAML test utility producing Assertions with a unique ID, Issuer, Subject, SubjectConfirmation, AudienceRestriction, timestamps, and signature per binding/profile.
4. A valid fixture **signed by the test private key** matching the exact issuer/ACS.
5. Negative cases created by modifying **one property after signing** or re-signing with an untrusted key, ensuring every defect is genuinely caught by the provider.
6. Avoid reusing the same Response ID across tests where a replay cache holds state, except for intentional replay tests.
7. Use a test-only clock/cert lifecycle to avoid fixtures expiring and causing flaky tests.
8. Assertions confirming **no authenticated session/security context** exists when validation fails, rather than only checking a default 302/400/401.

### 12.4. Request Test Pattern with a Pre-Generated Valid Fixture

~~~java
// SNIPPET, requires fixture signedSamlResponseBase64()
// real one from a test IdP/OpenSAML generator.
MvcResult result = mvc.perform(
    post("/login/saml2/sso/corp")
        .param("SAMLResponse", signedSamlResponseBase64())
).andReturn();

// Verify authentication success handler/session semantics
// according to the project's actual config.
// Do not hard-code status 200/302 when success handler is customized.
~~~

For SP-initiated SSO, before the POST there must be an AuthnRequest and matching **session state/request repository** for `InResponseTo` to be valid. If a test simply POSTs an IdP-generated assertion without a prior request, the outcome depends on whether the deployment supports unsolicited/IdP-initiated SSO. Never "fix" a test by indiscriminately disabling `InResponseTo` validation.

### 12.5. Distinguishing CSRF at the ACS vs. Business APIs

Browser SAML POSTs redirected from the IdP normally **do not carry the application's CSRF token**. Spring SAML2 login configuration sets up ACS handling appropriate to the protocol; it relies on SAML Response/relay state verification rather than a typical form CSRF token.

Conversely, `POST /api/admin/approve` is a business action using a local session cookie and **must** retain CSRF protection. Testing `.with(csrf())` on a business POST does not prove the ACS has a CSRF token, and exempting the SAML endpoint correctly from CSRF does not justify disabling CSRF app-wide.

## 13. Principal Attributes, Permissions, and Tenants in Tests

### 13.1. SAML Attributes Can Be Multi-Valued

`Saml2AuthenticatedPrincipal#getAttributes()` returns a map of attribute → list of values. For example, an IdP might issue:

~~~text
NameID: opaque-subject-17
registrationId: corp
attributes:
  department: ["orders"]
  groups: ["employee", "approver"]
  tenant: ["company-A"]
~~~

Do not blindly cast every attribute to a single String. `getFirstAttribute(...)` is convenient when the profile guarantees a single value, whereas group membership can be multi-valued.

### 13.2. Authentication ≠ Authorization

A mock principal with `groups=["admin"]` set by a test does **not** prove the real IdP is authorized to grant `APP_ADMIN`. Production should:
1. Verify the issuer/SAML Assertion.
2. Map the stable external ID to a local user via an approved key, not just email.
3. Check local account enabled status, tenant membership, and lifecycle.
4. Load local permissions/roles from the authorization store.
5. Apply resource-specific `AuthorizationManager` and method security.
6. Enforce object-level tenant ownership (e.g., an order must belong to the user's tenant).

In a slice test, `APP_ADMIN` is a local fixture simulating the mapper's output. Test the mapper separately with Mockito/database/fixtures rather than trusting `Saml2Authentication` from an untrusted source.

### 13.3. Cross-Tenant Negative Tests

If there are two registrations `corp-A` and `corp-B`, ensure:
- callbacks from IdP A cannot read B's local users just because NameID/email happens to match;
- a test principal with RP B cannot access RP A endpoints;
- an authority in one tenant does not grant permissions in another tenant;
- `registrationId` is only an internal lookup ID, not cryptographic proof if constructed from an unverified HTTP query.

### 13.4. Attaching Sessions When Testing Multiple Requests

`authentication(...)` normally injects `Authentication` into **a single test request**. It does not automatically simulate an end-to-end session from the SAML ACS. To test real session persistence:
- use full MockMvc + an authenticated ACS flow and retain the `MockHttpSession` from the response;
- run subsequent requests with `.session(session)`;
- verify logout invalidates the session/CSRF and session fixation rotation works;
- do not create a fresh session per request and claim session persistence passed.

Sharing a `SecurityContext` inside the test JVM does not prove session cookies across browsers or reverse proxies will be properly protected; integration/e2e tests are required.

## 14. Testing Status Codes, Redirects, Security Matchers, and Success Handlers

### 14.1. Test 302 as Expected—Do Not Treat "302 = Error"

An unauthenticated request to a SAML2-protected resource normally receives a redirect to `/saml2/authenticate/{registrationId}` or an IdP picker page; a test expecting `401` out of habit from Basic/Bearer APIs may be wrong.

- HTML browser: 302/303 leading to login may be correct.
- Machine API: should usually return 401/403 JSON or a Bearer challenge if specified by contract, not redirect clients to an IdP HTML flow.
- After successful login: a custom success handler, saved request, or landing page determines `Location`.
- After failed login: a failure handler may redirect to `/login?error`; a 302 status does not prove validation succeeded.

### 14.2. Filter Ordering with Multiple Chains

With `@Order` and `securityMatcher`, the **first matching chain** decides which filters run. A SAML ACS callback might accidentally fall into a stateless API chain, receive 401/403, or miss the SAML2 filter.

Test that:
- `GET /api/me` matches the browser SP chain;
- `POST /login/saml2/sso/corp` is handled by the SAML filter;
- `GET /saml2/authenticate/corp` is handled by the AuthnRequest filter;
- `POST /api/admin/approve` still enforces CSRF and authorization;
- `GET /actuator/health` is not redirected to SAML when health policy is public.

### 14.3. SecurityContext and Tests Prone to False Passes

A test that sets a JVM-wide static `SecurityContext` and forgets to clear it can cause later requests to inherit Authentication from an earlier test. Use `spring-security-test` processors/`@WithMockUser` with default teardown, and avoid global `SecurityContextHolder.setContext` without cleanup.

Never use `MockMvcResultMatchers.status().isOk()` as the sole assertion on a sensitive endpoint: assert principal, tenant, local permission, and that the response contains no data belonging to someone else.

## 15. Standalone Java 17: Illustrating the Post-SAML-Validation Decision Matrix

The example below runs on **standalone JDK 17**, showing how SP policy operates after the IdP has verified the principal. It does not simulate MockMvc or verify XML; real MockMvc code is in section 8. Use it to teach that RP, authority, and tenant must all be checked together.

### 15.1. `SamlSpAuthorizationDemo.java`

~~~java
public final class SamlSpAuthorizationDemo {

    record SamlEvidence(
        boolean samlValidated,
        String relyingPartyRegistrationId,
        String userTenant,
        boolean localAccountActive,
        boolean hasAdminPermission) {
    }

    enum Decision {
        ALLOW, DENY_UNVERIFIED, DENY_WRONG_RP,
        DENY_DISABLED, DENY_TENANT, DENY_PERMISSION
    }

    static Decision decide(
            SamlEvidence e, String requiredTenant) {
        if (!e.samlValidated()) {
            return Decision.DENY_UNVERIFIED;
        }
        if (!"corp".equals(e.relyingPartyRegistrationId())) {
            return Decision.DENY_WRONG_RP;
        }
        if (!e.localAccountActive()) {
            return Decision.DENY_DISABLED;
        }
        if (!requiredTenant.equals(e.userTenant())) {
            return Decision.DENY_TENANT;
        }
        if (!e.hasAdminPermission()) {
            return Decision.DENY_PERMISSION;
        }
        return Decision.ALLOW;
    }

    static void show(String scenario, SamlEvidence e) {
        System.out.println(scenario + "=" +
            decide(e, "tenant-A"));
    }

    public static void main(String[] args) {
        show("happyPath", new SamlEvidence(
            true, "corp", "tenant-A", true, true));
        show("invalidResponse", new SamlEvidence(
            false, "corp", "tenant-A", true, true));
        show("wrongRp", new SamlEvidence(
            true, "external", "tenant-A", true, true));
        show("disabledAccount", new SamlEvidence(
            true, "corp", "tenant-A", false, true));
        show("crossTenant", new SamlEvidence(
            true, "corp", "tenant-B", true, true));
        show("missingRole", new SamlEvidence(
            true, "corp", "tenant-A", true, false));
    }
}
~~~

### 15.2. Compile, Run, Stdout

~~~bash
javac --release 17 SamlSpAuthorizationDemo.java
java SamlSpAuthorizationDemo
~~~

**Deterministic stdout:**

~~~text
happyPath=ALLOW
invalidResponse=DENY_UNVERIFIED
wrongRp=DENY_WRONG_RP
disabledAccount=DENY_DISABLED
crossTenant=DENY_TENANT
missingRole=DENY_PERMISSION
~~~

Limitation: `samlValidated` is a test fixture for this Java exercise, not a user-supplied request parameter; RP, tenant, and permissions must all come from trusted server-side validation and repositories. This code **does not prove SAML signatures are secure**; it only demonstrates the intended order of authorization decisions.

## 16. Standard and Safe Test Fixtures

### 16.1. Which Fixtures Are Needed?

| Fixture | Used in test | Pitfalls avoided |
| --- | --- | --- |
| Mock authenticated SAML principal | Controller/authorization MockMvc slice. | Do not assume it passed signature validation. |
| RelyingPartyRegistration `corp` | AuthnRequest/ACS tests. | Endpoints, Issuer/ACS trust, and certs must match. |
| Test IdP RSA/EC key + X.509 cert | Sign Response/Assertion fixtures. | Never use production keys/private metadata. |
| Valid SP-initiated Response | ACS happy path with AuthnRequest correlation. | `InResponseTo` and session state must be valid. |
| Unsigned Response/Assertion | Negative signature test. | Must be rejected; do not mock validator to always succeed. |
| Wrong Audience | AudienceRestriction test. | Change only the intended value in the fixture. |
| Wrong Recipient/Destination | ACS routing validation. | Do not "fix" by disabling destination checks. |
| Expired/NotYetValid | Time validation. | Use a controlled clock or time-bound fixtures. |
| Unknown issuer/untrusted signer | Trust boundary. | Never trust a cert embedded arbitrarily in the Response. |
| Replay Response/Assertion | Replay protection. | Cache state must persist between the two submissions. |
| Cross-RP/tenant subject | Identity mapping/authorization. | Do not merge NameIDs/emails across IdPs. |

### 16.2. Do Not Commit Real SAMLResponses to Source

SAML Assertions can contain NameID, email, groups, session details, and sensitive attributes. Avoid storing full production SAMLResponses in test resources or Git. Generate fixtures using synthetic test subjects and test certificates. Do not log full XML, decrypted assertions, or raw `SessionIndex` in public CI artifacts.

### 16.3. Cert Rollover

If the IdP rotates its signing certificate, tests are needed for:
- old cert / trust overlap during the transition period;
- new cert validly configured;
- untrusted cert rejected;
- expired certificate or mismatched trust agreement;
- AuthnRequest signing credential distinct from Response verification credential;
- encrypted assertions decryptable only with the matching SP private key, not with the IdP's signing cert.

A MockMvc slice with `authentication(...)` will **not** detect rollover failures. That is why a dedicated ACS signed-fixture layer is required.

## 17. QA Testing Matrix for the SP

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| M01 | `@WebMvcTest` imports SecurityConfig with `addFilters=true`. | Real filter chain runs in the MVC slice. |
| M02 | MockMvc built manually without `springSecurity()`. | Test must catch missing filters/false pass; never use as security proof. |
| M03 | `GET /health` anonymous. | 200 per public policy. |
| M04 | `GET /api/me` anonymous. | Redirect/challenge per entry point; never returns 200. |
| M05 | Valid `Saml2Authentication` fixture RP=corp. | Principal injection reflects correct NameID/RP. |
| M06 | `@WithMockUser` used instead of SAML principal. | Test must demonstrate type mismatch; does not bypass SAML-only guard. |
| M07 | `Saml2Authentication` with RP other than corp. | 403 on RP-restricted route. |
| M08 | SAML principal corp missing `APP_ADMIN`. | 403 on admin route. |
| M09 | SAML principal corp with local `APP_ADMIN`. | 200 on admin route if other policies pass. |
| M10 | `POST /api/admin/approve` without CSRF. | 403. |
| M11 | POST with `with(csrf())` but lacking permission. | 403. |
| M12 | POST with CSRF + valid permission. | 200 / action authorized in fixture. |
| M13 | SAML principal with same NameID but different tenant. | Cross-tenant denied per domain policy. |
| M14 | RP registration repository lacks `corp` for AuthnRequest. | Initiation fails; do not fake a 302 success. |
| M15 | GET SAML auth initiation with real RP, Redirect binding. | IdP URL + SAMLRequest match config. |
| M16 | SAML AuthnRequest has wrong Issuer/ACS. | QA fails when decoding request. |
| M17 | Invalid/unknown `registrationId`. | Does not select an arbitrary IdP/registration. |
| M18 | ACS receives valid signed Response from test IdP. | Authenticates and creates session per success handler. |
| M19 | ACS receives unsigned Response/Assertion. | Rejected; no authenticated session created. |
| M20 | ACS signed with untrusted key. | Rejected. |
| M21 | ACS has wrong issuer. | Rejected. |
| M22 | ACS wrong Destination/Recipient. | Rejected. |
| M23 | ACS wrong AudienceRestriction. | Rejected. |
| M24 | ACS expired NotOnOrAfter. | Rejected. |
| M25 | ACS NotBefore in the future beyond clock skew. | Rejected. |
| M26 | ACS InResponseTo does not match outstanding request. | Rejected per SP-initiated policy. |
| M27 | ACS unsolicited IdP-initiated when disallowed by policy. | Rejected. |
| M28 | ACS replays previous Response/Assertion ID. | Replay blocked per anti-replay policy. |
| M29 | ACS with XML Entity / oversized payload. | Parser rejects; does not crash the service. |
| M30 | Signed response contains multi-valued attributes. | Mapper parses per profile without granting wrong roles. |
| M31 | IdP group "admin" but local account lacks admin. | Does not automatically grant `APP_ADMIN`. |
| M32 | Local account disabled after SAML login. | Reauthorization/session revocation per policy. |
| M33 | Same NameID from two IdPs. | Does not auto-link to the same local user. |
| M34 | Response has email matching a local account but different stable ID. | Does not auto-link. |
| M35 | Multi-chain: ACS callback captured by API chain. | Test detects 401/403 and fixes matcher. |
| M36 | Multi-chain: business POST accidentally CSRF-exempt. | QA fails. |
| M37 | SAML login success handler redirects to arbitrary external URL. | No open redirect; allowlist/saved request enforced. |
| M38 | Local session after ACS reused on another request. | Session persistence works without hitting IdP again while session valid. |
| M39 | Local logout invalidates session; old request loses access. | Denied/redirected per policy. |
| M40 | Session ID rotation after SAML login. | Session fixation protection active per configuration. |
| M41 | Certificate rollover with new trusted signer. | New signed fixture passes; old/untrusted behaves per overlap policy. |
| M42 | Invalid/failed assertion decryption. | Rejected; no Authentication granted. |
| M43 | Valid Response but invalid local account/tenant. | IdP authentication does not override local authorization. |
| M44 | MockMvc test uses `authentication(...)` then marks signature QA pass. | **Test-scope QA FAIL**; signed fixtures are required. |
| M45 | SP metadata emits wrong ACS/public host behind proxy. | Detect metadata mismatch/trust configuration. |
| M46 | Missing `spring-security-test` dependency. | Compiler lacks `authentication(...)`/`csrf()` processors. |
| M47 | Spring Security version changes OpenSAML provider API. | Build/test/upgrade review; do not remove validator. |
| M48 | CI runs tests requiring a live production IdP online. | QA fails on independence; use test IdP/fixtures. |

### 17.1. Mandatory Checks Before Merging a PR

1. **Controller slice:** tests M01–M13, asserting body/status/authorities.
2. **AuthnRequest integration:** endpoint, destination, issuer, ACS, binding, `RelayState`, signature if required.
3. **ACS provider integration:** valid signed fixture, signature fail, trust, audience, destination, time, replay, subject confirmation.
4. **Identity mapping:** issuer/SP-scoped stable ID → local user ID; no email auto-linking; local enabled + role + tenant.
5. **Sessions:** CSRF on business APIs, fixation, saved request, logout, persistence.
6. **Infrastructure:** reverse proxy `Host`/`X-Forwarded` trust, public metadata, TLS certificates, cert rotation.
7. **CI artifacts:** no raw `SAMLResponse`/tokens/private keys logged; test fixtures use synthetic data and need no production IdP.

## 18. Troubleshooting MockMvc and SAML2

### 18.1. Anonymous Test Returns 200 Instead of Redirect

**Common causes:** using `MockMvcBuilders.standaloneSetup(controller)` so `SecurityFilterChain` does not run; or `@AutoConfigureMockMvc(addFilters=false)`; or the route is `permitAll` due to a misconfigured matcher.

**Fix:** use `@WebMvcTest + @Import(SecurityConfig)`, `@AutoConfigureMockMvc(addFilters=true)`, or `webAppContextSetup(...).apply(springSecurity())`. Verify the endpoint matches the right matcher and no authentication leaked from another test.

### 18.2. `@WithMockUser` Causes ClassCastException / Null Principal

**Cause:** Controller expects `Saml2AuthenticatedPrincipal`, but `@WithMockUser` supplies a different principal type.

**Fix:** use `authentication(new Saml2Authentication(...))` for SAML-specific tests. If the controller supports multiple login types, write a common mapper keyed by trusted local user ID and test each path explicitly.

### 18.3. Business API POST Always Returns 403 Even With APP_ADMIN

**Cause:** The CSRF filter is blocking it; 403 can happen **before** business authorization.

**Fix:** add `.with(csrf())` for allowed business requests, and also test the missing-permission case. **Never** disable CSRF app-wide just to make tests pass.

### 18.4. ACS POST Returns 403 Without CSRF

**Cause:** The SAML2 filter is not configured or does not match the path, or SAML config CSRF exemption was overridden, causing the callback to land in the wrong chain.

**Fix:** check that the ACS URL matches `loginProcessingUrl`, `Saml2WebSsoAuthenticationFilter` is in the chain, Spring `saml2Login` is configured, and the SAML POST profile performs protocol validation. Never permit arbitrary unvalidated POSTs just to silence 403.

### 18.5. Mock Principal Test Returns 200, But Real IdP Login Fails

**Cause:** Mocks bypass signatures/timestamps/issuer/audience, whereas the production SAML provider rejects bad certificates, ACS URLs, clock skew, `InResponseTo`, or key rotation.

**Fix:** add signed-fixture ACS tests, metadata agreement checks, and e2e tests with a test IdP. Never swap the verification certificate for an attacker's cert or disable signature validation.

### 18.6. `No qualifying bean of type RelyingPartyRegistrationRepository`

**Cause:** The Spring Context has `saml2Login()` without registration config/bean, or the slice test imported security config without supplying the collaborator.

**Fix:** slice tests use `@MockBean RelyingPartyRegistrationRepository` when testing only controllers; ACS/AuthnRequest tests use real registrations and test certificates. Do not use an empty Mockito repo for tests that generate AuthnRequests.

### 18.7. 302 With Unexpected Location

**Cause:** multiple IdPs configured, redirecting to a login picker, custom entry point, saved request, or different forwarded base URL.

**Fix:** check the actual entry point; assert only the URL guaranteed by the app's contract. `Location` after SAML2 initiation may contain `SAMLRequest`/`RelayState`/Signature; avoid comparing the entire URL string containing random IDs/timestamps.

### 18.8. Flaky Tests (Sometimes Pass, Sometimes Fail)

**Cause:** stale `SecurityContext`/session, time-sensitive SAML fixtures, shared replay cache, random request IDs, expired cert, global test state, or parallel runs sharing a principal ID.

**Fix:** give each test fresh fixtures/nonces/clocks, isolated session/replay stores, proper context teardown, and zero reliance on production IdPs or environment data.

## 19. Self-Check Questions

**1. Does `MockMvc.with(authentication(saml2Auth))` verify XML signatures?**  
No. It attaches a test-constructed `Authentication` to `SecurityContext` and bypasses SAML ACS validation.

**2. Why is `spring-security-test` needed?**  
To use MockMvc Spring Security configurers and request processors such as `authentication()`, `user()`, and `csrf()`.

**3. When should `springSecurity()` be used?**  
When manually building MockMvc from `WebApplicationContext`; it attaches the Spring Security filter chain and test holder. Do not attach it again if Boot already auto-configured MockMvc with filters.

**4. Why is `@WithMockUser` insufficient for a controller that reads SAML attributes?**  
Its principal and `Authentication` type are normally not `Saml2AuthenticatedPrincipal`/`Saml2Authentication`.

**5. Does receiving 302 on a protected page mean SAML2 login succeeded?**  
No. It may just be the SSO initiation redirect or a redirect caused by a login failure.

**6. Does testing `with(csrf())` validate a SAML Response?**  
No. CSRF protects browser app actions; a SAML Response requires signature/recipient/audience/subject confirmation validation.

**7. Does `@WebMvcTest` test the entire IdP flow?**  
No. It is an MVC slice; ACS signed fixtures and e2e tests belong in separate layers.

**8. Should the app accept an unsigned Base64 SAMLResponse containing a NameID?**  
It must be rejected by real validation; never mock the provider to always succeed in security tests.

**9. Does a test principal with `registrationId=corp` prove the issuer is trusted?**  
No. That is just a field set by the test. The provider must verify the actual issuer and trust anchor.

**10. Can `standaloneSetup` be used to test pure controller logic?**  
Yes, but do not treat it as testing Spring Security authorization/filters unless `FilterChainProxy` is properly attached.

**11. When the IdP certificate changes, which test catches errors?**  
ACS integration tests with signed fixtures/credential rotation; direct `Saml2Authentication` fixture tests will not detect it.

**12. Does a valid SAML response automatically grant `APP_ADMIN`?**  
No. Local account linking and policy-governed application permissions are required.

## 20. Completion Checklist

- [ ] Project uses JDK 17+, compatible Spring Boot/Spring Security versions, and test dependencies aligned with the BOM.
- [ ] `spring-boot-starter-test` and `spring-security-test` are present for JUnit/MockMvc.
- [ ] SAML SP support uses `spring-security-saml2-service-provider`, with OpenSAML/Shibboleth artifact repository configured if needed by dependencies.
- [ ] Slice tests have `@Import(SecurityConfig)` and `@AutoConfigureMockMvc(addFilters=true)` or equivalent configuration.
- [ ] Manual MockMvc uses `webAppContextSetup(context).apply(springSecurity())`; `FilterChainProxy` is not omitted.
- [ ] Security tests do not rely on filterless `standaloneSetup` as proof of safety.
- [ ] `authentication(Saml2Authentication)` is used when SAML-specific principal/registration ID/attributes are needed.
- [ ] Mock authenticated fixtures are clearly distinguished from real signed SAMLResponses.
- [ ] `@WithMockUser` is used only when the authentication type is not under test.
- [ ] Tests cover anonymous, SAML principal, wrong RP, missing permission, admin permission, CSRF POST, and 403.
- [ ] Controller tests do not need a real IdP; `@MockBean` RP repository is used only at the appropriate layer.
- [ ] AuthnRequest tests use a real registration and check issuer/ACS/destination/signature per binding.
- [ ] ACS tests use signed fixtures with a test trust cert and do not mock the provider to always succeed.
- [ ] Negative ACS tests cover unsigned, wrong issuer/audience/destination, expiry, `InResponseTo`, replay, and untrusted cert.
- [ ] An RP registration is never selected from untrusted browser input; tenant isolation is tested.
- [ ] Stable external IDs map to local accounts; email/NameID never automatically grants admin roles.
- [ ] Business POSTs enforce CSRF; SAML ACS is processed per protocol on the proper filter chain path.
- [ ] Tests do not depend on production IdPs, private keys, or SAMLResponses containing PII.
- [ ] Session fixation, logout, session persistence, and account revocation have dedicated integration tests.
- [ ] CI covers M01–M48 or equivalent test coverage and reports test scope accurately.
- [ ] When upgrading Spring Boot/Security/OpenSAML, imports and APIs are reviewed and the SAML regression suite is re-run.
- [ ] Never claim "SAML signature QA PASS" solely because a MockMvc request was given a `Saml2Authentication`.

## Takeaways

> **MockMvc + Spring Security** is a powerful tool for testing **controllers, `SecurityFilterChain`, authorization, CSRF, and HTTP responses of a SAML2 Service Provider application**. Use `@WebMvcTest`/`@SpringBootTest` with the real filter chain and `authentication(new Saml2Authentication(...))` for already-authenticated tests. However, **mock principals do not verify SAML Responses**: signatures, issuer, audience, recipient, expiry, `InResponseTo`, and replay must be tested separately with **ACS protocol tests using signed fixtures** and a real test IdP where appropriate.

### Official References

- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): integrating `MockMvcBuilders.webAppContextSetup(...).apply(springSecurity())`.
- [Spring Security — Running as a User in MockMvc Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `authentication(...)`, `user(...)`, `@WithMockUser`, and SecurityContext.
- [Spring Security — CSRF MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `with(csrf())`.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP/RP, registration, AuthnRequest, ACS, and SAML authentication.
- [Spring Security — SAML2 AuthnRequest](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): request generation and destination/binding.
- [Spring Security — SAML2 Response Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): default ACS, signature/condition checks, principal/authorities.
- [Spring Security 6.3 — Saml2Authentication Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/saml2/provider/service/authentication/Saml2Authentication.html): constructor `(principal, response, authorities)`.
- [Spring Security 6.x — DefaultSaml2AuthenticatedPrincipal Javadoc](https://docs.spring.io/spring-security/site/docs/6.4.10/api/org/springframework/security/saml2/provider/service/authentication/DefaultSaml2AuthenticatedPrincipal.html): NameID, attributes, and registrationId.
- [Spring Security — Servlet Architecture / Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter ordering, `SecurityFilterChain` matching.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@WebMvcTest`/`@SpringBootTest`/`@AutoConfigureMockMvc`.
- [OASIS SAML V2.0 Core Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): assertions, audience, issuer, conditions, and subject confirmation.
- [OASIS SAML V2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO, `InResponseTo`, bindings, and SP/IdP flow.

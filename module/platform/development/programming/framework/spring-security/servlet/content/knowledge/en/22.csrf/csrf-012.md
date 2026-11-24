# Limiting CSRF Exceptions with ignoringRequestMatchers and Evaluating Before Disabling

## 1. Problem to Solve

In Spring Security on a **Servlet** foundation (Spring MVC, Spring Boot 3.x, and Spring Security 6.x), CSRF (Cross-Site Request Forgery) is the risk when a browser automatically sends credentials such as session cookies on a request initiated by another page. For example, a user remains logged into a banking application; a malicious page makes their browser send a money-transfer POST. The server may receive a valid session cookie even though the user never intended to transfer funds.

By default, Spring Security protects state-changing methods (such as POST, PUT, PATCH, DELETE) with a CSRF token; methods considered safe (GET, HEAD, TRACE, OPTIONS) normally do not require a token. If a request requiring protection lacks a valid token, **CsrfFilter returns HTTP 403** before business processing. Key principle: GET must not perform state changes.

Certain endpoints, typically webhooks from external systems, do not use browser/session cookies and therefore have no CSRF token to send. When there is a clear reason, **skip CSRF verification only for the exact necessary requests** using **csrf.ignoringRequestMatchers(...)**, while keeping defense active for other requests. Never disable CSRF across the entire filter chain merely to fix a 403 error on one endpoint.

Goals after this lesson:
- Distinguish an endpoint that genuinely needs no CSRF from one simply missing how to send the token.
- Write narrow exceptions scoped by **path and HTTP method**.
- Understand that exempting CSRF verification does not mean dropping authentication, authorization, or webhook signature verification.
- Verify both the exception and the remaining protection with HTTP tests.

## 2. Mechanism and Protection Boundaries

With a Servlet SecurityFilterChain, Spring Security determines which requests require CSRF verification. When using **ignoringRequestMatchers**, requests matching the matcher are excluded from the set requiring token verification; remaining requests still follow the CSRF policy. A matcher is a request-selection condition, not an access-permission list.

Distinguish three commonly confused configurations:

| Configuration | Purpose | Outcome |
| --- | --- | --- |
| **csrf.ignoringRequestMatchers(matcher)** | Exempt requests matching the matcher from CSRF | CSRF remains enabled for all other requests |
| **authorizeHttpRequests(...requestMatchers(...).permitAll())** | Allow accessing an endpoint without logging in | Does **not** auto-exempt CSRF: POST can still receive 403 |
| **csrf.disable()** | Disable CSRF for the entire corresponding SecurityFilterChain | Every request in that chain loses the CSRF check layer |

Thus, adding only **permitAll()** does not fix a POST missing a token. Conversely, adding only **ignoringRequestMatchers** does not grant access to an endpoint if authentication/authorization rules still deny it.

### Is CSRF Still Needed for REST APIs?

The "REST" label does not determine risk; **how the client authenticates** is what matters:

| Usage flow | CSRF assessment |
| --- | --- |
| Web MVC with login/session cookies | Keep CSRF; forms/JavaScript must send tokens |
| SPA calling APIs with login cookies | Usually still needs CSRF, even when responses are JSON |
| API using bearer tokens actively attached by client only in the Authorization header, not accepting cookies as credentials | May not need CSRF for that flow after verifying the full authentication mechanism |
| JWT stored in a cookie and auto-sent by the browser | **Still at CSRF risk**; using JWT does not solve the issue by itself |
| Server-to-server webhook using HMAC signatures, not relying on browser sessions/cookies | Can exempt CSRF for that specific endpoint, while strictly verifying signatures/requests per partner protocol |

CORS is not a substitute for CSRF: blocking the browser from reading cross-origin responses does not guarantee the server did not receive the data-modifying request. SameSite cookies, Origin/Referer checks, and Content-Type restrictions are useful supplementary defense layers, yet must not be used as an excuse to arbitrarily disable CSRF. HTTP Basic must also be evaluated because browsers can auto-send remembered credentials.

## 3. Configuring a Scoped Exception

Suppose the application has:
- **POST /account/notification**: action by a session-authenticated user; must require a CSRF token.
- **POST /webhooks/provider**: callback from a partner, authenticated via HMAC over the raw body; has no CSRF token.

The example below works in a Spring Boot 3.x / Spring Security 6.x application with Java 17+. Use a **RequestMatcher** checking both method and exact path to avoid accidentally exempting other POSTs or other methods on the same URL. In an application with DispatcherServlet at the default mapping, **getServletPath()** is the request path excluding the context path.

Add the following dependencies to the **dependencies** block of an already configured Gradle Spring Boot project:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
implementation 'org.springframework.boot:spring-boot-starter-security'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
~~~

File **src/main/java/com/example/csrf/CsrfExampleApplication.java**:

~~~java
package com.example.csrf;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CsrfExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfExampleApplication.class, args);
    }
}

@Configuration
class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        RequestMatcher providerWebhookPost = request ->
                "POST".equals(request.getMethod())
                && "/webhooks/provider".equals(request.getServletPath())
                && request.getPathInfo() == null;

        return http
                .csrf(csrf -> csrf.ignoringRequestMatchers(providerWebhookPost))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.POST, "/webhooks/provider").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}

@RestController
class DemoController {
    private final byte[] webhookSecret;

    DemoController(@Value("${example.webhook-secret}") String secret) {
        this.webhookSecret = secret.getBytes(StandardCharsets.UTF_8);
    }

    @PostMapping("/account/notification")
    String updateNotification() {
        return "updated";
    }

    @PostMapping("/webhooks/provider")
    ResponseEntity<String> providerWebhook(
            @RequestBody byte[] rawBody,
            @RequestHeader(value = "X-Signature", required = false) String signature) {
        if (!validHmac(rawBody, signature)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("bad signature");
        }
        return ResponseEntity.ok("accepted");
    }

    private boolean validHmac(byte[] rawBody, String signature) {
        if (signature == null || !signature.matches("[0-9a-fA-F]{64}")) {
            return false;
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(webhookSecret, "HmacSHA256"));
            byte[] expected = mac.doFinal(rawBody);
            byte[] provided = HexFormat.of().parseHex(signature);
            return MessageDigest.isEqual(expected, provided);
        } catch (GeneralSecurityException ex) {
            return false;
        }
    }
}
~~~

In this configuration:
1. **providerWebhookPost** matches only a POST request with exact servlet path **/webhooks/provider**. A POST to **/webhooks/provider/extra**, or a PUT to **/webhooks/provider**, remains subject to CSRF.
2. **ignoringRequestMatchers(providerWebhookPost)** exempts CSRF verification specifically for that callback. It does not disable the entire CsrfFilter.
3. **permitAll()** allows an unauthenticated partner without a login session to reach the controller, yet the controller itself requires and verifies an HMAC signature. The signature is computed over the **raw bytes** of the request body and compared with **MessageDigest.isEqual**.
4. **/account/notification** requires logging in via form login and must send a CSRF token on POST.

**Safety limits of the demo:** The **X-Signature** header with HMAC-SHA256 is an illustrative protocol, not a universal standard for every provider. In real systems, adhere to the partner's exact signature/timestamp format, source secrets from a secret store or environment variables, enforce timestamp windows, replay protection, idempotency, and other verification rules. Never use test secret values in production. If the app has a context path, custom servlet mapping, or multiple SecurityFilterChain beans, re-test the matcher and chain order under the real configuration.

## 4. Testing the Policy: Only One Endpoint Is Exempt

File **src/test/java/com/example/csrf/CsrfPolicyTest.java**:

~~~java
package com.example.csrf;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = "example.webhook-secret=test-secret")
@AutoConfigureMockMvc
class CsrfPolicyTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser
    void accountPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/account/notification"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void accountPostWithCsrfSucceeds() throws Exception {
        mvc.perform(post("/account/notification").with(csrf()))
                .andExpect(status().isOk());
    }

    @Test
    void webhookWithoutValidSignatureIsUnauthorized() throws Exception {
        mvc.perform(post("/webhooks/provider")
                        .content("payload")
                        .header("X-Signature", "invalid"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void webhookWithValidSignatureDoesNotNeedCsrf() throws Exception {
        byte[] body = "payload".getBytes(StandardCharsets.UTF_8);
        mvc.perform(post("/webhooks/provider")
                        .content(body)
                        .header("X-Signature", signatureFor(body)))
                .andExpect(status().isOk());
    }

    @Test
    void differentPathIsStillProtected() throws Exception {
        mvc.perform(post("/webhooks/provider/extra"))
                .andExpect(status().isForbidden());
    }

    @Test
    void differentUnsafeMethodIsStillProtected() throws Exception {
        mvc.perform(put("/webhooks/provider"))
                .andExpect(status().isForbidden());
    }

    private static String signatureFor(byte[] body) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
                "test-secret".getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return HexFormat.of().formatHex(mac.doFinal(body));
    }
}
~~~

Run in the project directory with Gradle wrapper:

~~~bash
./gradlew test --tests com.example.csrf.CsrfPolicyTest
~~~

On Windows you can use **gradlew.bat** instead of **./gradlew**. The six cases expect HTTP results **403, 200, 401, 200, 403, 403** respectively. The final two tests confirm the exception scope does not spill over to similar URLs or other methods; they are still rejected by CsrfFilter before controller lookup. The test uses **@WithMockUser** only to simulate an authenticated user, not to replace a CSRF token; **with(csrf())** generates a valid token for MockMvc.

To observe real requests via curl or Postman, configure **example.webhook-secret** from the environment (e.g., **EXAMPLE_WEBHOOK_SECRET**) and compute a valid signature over the body bytes. Note that curl/Postman do not themselves create a CSRF threat: tests verify server-side policy, whereas actual risk originates from browsers auto-sending credentials.

## 5. Evaluating Before Considering Disabling

Never immediately change to **csrf.disable()** just because a POST returns 403. Follow this sequence:

1. **Identify the request and actual result.** Record method, path, selected filter chain, credential type, status, logs, and check whether the request lacked/had an invalid CSRF token. 403 can also come from authorization rules; do not assume every 403 is CSRF.
2. **Classify the client.** Can the request originate from a browser carrying session/cookies or auto-sent HTTP Basic? If so, prefer keeping CSRF and sending the token properly. HTML forms need a hidden token input; for JavaScript SPAs, set up token issuance/reading/sending compatible with Spring Security 6 and the app's cookie policy.
3. **Establish a technical reason to exempt.** Does the endpoint genuinely accept only server-to-server connections, not rely on browser auto-sent credentials, and already enforce independent authentication (signature/mTLS/equivalent standard)? If not, do not create an exception merely because a partner or frontend currently omits the token.
4. **Narrow the matcher.** Choose the specific path, method, servlet mapping, and chain; avoid broad patterns like **/api/** or **/** when only one callback needs exemption. If using multiple SecurityFilterChain beans, check **securityMatcher** and **@Order** precedence because CSRF configuration affects only the matched chain.
5. **Define independent access control.** Authentication and authorization still apply; webhooks that are public from a session perspective must verify message authenticity. Add rate limits, auditing, anti-replay, and idempotency as risk dictates, never treating CSRF exemption as sender verification.
6. **Write negative and positive tests.** CSRF-exempt requests reach business verification without a token; similar requests on different paths/methods remain blocked; browser operations still get 403 without a token and succeed with one. Re-test whenever adding new routes or modifying chains.
7. **Only consider chain-level disable after proving the entire chain needs no CSRF.** For example, a truly stateless API chain accepting only bearer tokens in the Authorization header, with no cookie/session/automatic Basic auth from browsers, and verified by tests. If the same chain also hosts form login, logout, admin pages, or cookie-based APIs, disabling globally removes their protection.

### Common Mistakes

- **"The API returns JSON so no CSRF needed."** False when browsers authenticate via cookies.
- **"Added permitAll so POST will not ask for a token."** False because authorization and CSRF are separate decisions.
- **"Webhooks have no token, so disable everything."** Broadens the exemption unnecessarily to login, account settings, and other POSTs.
- **"Already using JWT so CSRF is exempt."** Incorrect if the JWT resides in an auto-sent cookie.
- **"ignoringRequestMatchers protects the webhook."** False: it only skips one check; signature verification and access control must still be implemented.
- **"Using /** is convenient for all callbacks."** An overly broad matcher can disable CSRF for routes added in the future.
- **"GET can modify data because GET requires no token."** Broken HTTP design; state-changing operations must move to appropriate methods.

## 6. Completion Criteria

A sound CSRF exception can be stated in one sentence: **which request is exempted, why it needs no CSRF token, which mechanism authenticates it, and which requests remain protected**. In the example above, only **POST /webhooks/provider** is exempted from CSRF and the HMAC signature remains a business requirement; **POST /account/notification** continues to require login and a CSRF token. When that boundary cannot be proven, keeping CSRF and fixing how clients obtain/send tokens is the safer choice.

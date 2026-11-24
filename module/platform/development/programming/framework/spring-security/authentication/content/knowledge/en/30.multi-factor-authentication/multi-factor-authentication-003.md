# FactorGrantedAuthority and @EnableMultiFactorAuthentication in Supported Spring Security Versions

## 1. Objectives and Important Version Notes

**Multi-Factor Authentication (MFA)** requires users to prove their identity with multiple authentication factors. In **Spring Security 7.0 and later (Servlet)**, the framework introduces two particularly useful APIs:

- `FactorGrantedAuthority`: a type of `GrantedAuthority` representing the **method/factor used for authentication**, along with the timestamp when that factor was recorded.
- `@EnableMultiFactorAuthentication`: an annotation supporting **adding authentication factor requirements to authorization rules** instead of repeating check expressions across every endpoint.

**Mandatory version boundaries to remember:**

| Version Line | Can You Use This Article's Two APIs Directly? | What Should You Do? |
| --- | --- | --- |
| Spring Security 6.4/6.5 (Spring Boot 3.x) | **No**: these two APIs were introduced in Spring Security **7.0** | Do not copy 7.x imports/annotations; use a 6.x-compatible MFA solution or upgrade per the migration guide |
| Spring Security 7.0 (typically used with Spring Boot 4.0) | **Yes**: `FactorGrantedAuthority` and `@EnableMultiFactorAuthentication` | Configure factor policies and the corresponding login mechanisms |
| Spring Security 7.1+ | **Yes**, and adds conditional mechanisms such as `MultiFactorCondition.WEBAUTHN_REGISTERED` in current documentation | Check the Javadoc for your specific version before using additional APIs |
| Spring WebFlux/reactive | Do not assume identical support to Servlet | Check the WebFlux docs for your exact version; the 7.0 MFA annotation is documented as not applying to reactive |

Both `FactorGrantedAuthority` and `@EnableMultiFactorAuthentication` carry **Since: 7.0** in their Javadoc. In this article, the primary configuration examples use **Spring Boot 4.0.x / Spring Security 7.0.x / Java 17+ / Servlet**. Parts marked **7.1+** apply only when your project has upgraded to a supporting branch.

After studying, you should be able to distinguish: **a proven factor**, **the authority representing the factor**, **the rule requiring the factor**, and **the mechanism that actually gathers authentication evidence**. An annotation does not by itself turn a password-only application into MFA.

## 2. What Is a Factor? Why Is a Single Login Not Enough?

Common categories of user evidence:

| Category | Examples | What to Evaluate |
| --- | --- | --- |
| Something you know | Password, secret PIN known only to the user | Phishing resistance, password guessing, reuse |
| Something you have | Security key, passkey-holding device, OTT receiving channel | Is the device or channel genuinely independent from the password? |
| Something you are | Fingerprint/face verified locally on the authenticator | Does the RP receive appropriate user verification evidence? |

Entering **the same password** twice does not create two independent factors. Two codes sent to the same mailbox do not automatically guarantee strong MFA. An email magic link can serve as an additional factor if the organization accepts the email channel's assurance level, but it is typically **not as phishing-resistant** as properly designed and verified WebAuthn/passkeys.

Spring Security separates **authentication mechanisms** (how users prove identity) from **authorization policy** (which factors must be proven to perform an action).

Business examples:

- Reading ordinary articles: requires an authenticated account.
- Viewing personal information: requires password and one-time token (OTT) evidence.
- Transferring funds or changing recovery methods: additionally requires a “recent factor” condition, business permissions, and step-up authentication.
- System administration: requires `ROLE_ADMIN` **and** policy-mandated factors; a role does not replace a factor.

## 3. What Is FactorGrantedAuthority?

In Spring Security 7, the class:

~~~java
org.springframework.security.core.authority.FactorGrantedAuthority
~~~

implements `GrantedAuthority`. Unlike `SimpleGrantedAuthority("ROLE_ADMIN")` which is a business permission, `FactorGrantedAuthority` represents an **authentication method recorded by the framework**.

Constants worth remembering:

| Constant | Authority Value | Corresponding Evidence |
| --- | --- | --- |
| `FactorGrantedAuthority.PASSWORD_AUTHORITY` | `FACTOR_PASSWORD` | Password login |
| `FactorGrantedAuthority.OTT_AUTHORITY` | `FACTOR_OTT` | One-Time Token login |
| `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` | `FACTOR_WEBAUTHN` | WebAuthn/passkey login |
| `FactorGrantedAuthority.X509_AUTHORITY` | `FACTOR_X509` | X.509 client-certificate authentication |
| `FactorGrantedAuthority.BEARER_AUTHORITY` | `FACTOR_BEARER` | Bearer-token authentication |
| `FactorGrantedAuthority.AUTHORIZATION_CODE_AUTHORITY` | `FACTOR_AUTHORIZATION_CODE` | OAuth2 Authorization Code login |
| `FactorGrantedAuthority.SAML_RESPONSE_AUTHORITY` | `FACTOR_SAML_RESPONSE` | SAML authentication |
| `FactorGrantedAuthority.CAS_AUTHORITY` | `FACTOR_CAS` | CAS authentication |

**Note:** `FACTOR_*` names denote the **mechanism** that was used; they do not mean any two arbitrary mechanisms qualify as two independent factors under a given MFA policy. For instance, `FACTOR_BEARER` only indicates bearer authentication was used—it does not prove the token bearer holds a separate factor.

### 3.1. issuedAt: When Was the Factor Authenticated?

`FactorGrantedAuthority` also provides:

~~~java
Instant issuedAt = factorGrantedAuthority.getIssuedAt();
String authority = factorGrantedAuthority.getAuthority();
~~~

Meaning:

- `getAuthority()` returns the factor name, e.g., `FACTOR_PASSWORD`.
- `getIssuedAt()` returns the timestamp when that factor's authority was recorded.
- A factor authority itself **does not set a global TTL**. The same authentication may satisfy a “within 60 minutes” rule while no longer satisfying a “within 5 minutes” rule.

For example: a password entered at 09:00 may by 09:45 no longer satisfy “password within 30 minutes” for changing a phone number, even though the session remains logged in. In that case, the application must ask the user to re-prove the factor via a secure step-up flow.

### 3.2. Do Not Forge Fake Factors

In Spring Security 7, the framework adds factor authorities when the corresponding authentication mechanism succeeds. **Do not** do this to “enable MFA”:

~~~java
// WRONG: self-issuing authorities without ever verifying password/OTT.
var authorities = java.util.List.of(
    new org.springframework.security.core.authority.SimpleGrantedAuthority(
        FactorGrantedAuthority.PASSWORD_AUTHORITY),
    new org.springframework.security.core.authority.SimpleGrantedAuthority(
        FactorGrantedAuthority.OTT_AUTHORITY)
);
~~~

This is a **counter-example snippet**, not a standalone program. The strings `FACTOR_PASSWORD`/`FACTOR_OTT` must never be taken from client-sent headers, unverified JWT claims, or self-declared form flags. Assurance lies in the actual **authentication mechanisms** and `SecurityContext` management, not in inserting strings into a list.

When implementing a custom authentication provider, read the API/contract of your Spring Security version before issuing a `FactorGrantedAuthority`, ensuring it is issued only after properly verifying the factor and handling time/session validity.

## 4. What Does @EnableMultiFactorAuthentication Do?

Full annotation name:

~~~java
org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication
~~~

Syntax:

~~~java
@Configuration
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
class SecurityConfiguration {
    // Place SecurityFilterChain and authentication mechanism beans here.
}
~~~

This is a **configuration snippet**, not a complete Java file: you must import `@Configuration`, `@EnableMultiFactorAuthentication`, and `FactorGrantedAuthority` from the right Spring Security 7 packages.

Meaning of the annotation:

1. Enables MFA support at the authorization layer.
2. When `authorities` are specified, creates an `AuthorizationManagerFactory` combining regular rules with **required factors**.
3. Authorization rules such as `authenticated()` or `hasRole("ADMIN")` created via the factory can additionally require both `FACTOR_PASSWORD` and `FACTOR_OTT`.
4. Spring Security coordinates entry points/flows to direct the user to the authentication step for the **missing factor** when the corresponding mechanisms are configured.

**The annotation does not create passwords or an OTT delivery service.** The application must also configure:

~~~java
http
    .formLogin(Customizer.withDefaults())
    .oneTimeTokenLogin(Customizer.withDefaults());
~~~

In Servlet 7.0 integration, form login supplies the password factor, and One-Time Token Login (OTT) supplies the OTT factor when properly completed. Never use two `formLogin()` calls as two factors.

### 4.1. Role, Scope, and Factor Are Different Dimensions

Suppose an account has:

~~~text
ROLE_ADMIN
FACTOR_PASSWORD
FACTOR_OTT
~~~

When global MFA is configured to require PASSWORD + OTT:

| Rule | Effective Requirement |
| --- | --- |
| `anyRequest().authenticated()` | The user is authenticated and has both PASSWORD and OTT per policy |
| `hasRole("ADMIN")` | Has `ROLE_ADMIN` **and** both factors |
| `hasAuthority("SCOPE_reports.write")` | Has the specific scope **and** sufficient factors when applied globally by the factory |
| `hasRole("USER")` | Has role USER **and** sufficient factors |

Do not turn `ROLE_ADMIN` into a factor; do not turn `FACTOR_OTT` into permission to edit another tenant's data. Resource/object-level permissions still require separate checks.

### 4.2. The Factory Behind the Annotation

Conceptually, the annotation with two authorities is equivalent to providing a factory like:

~~~java
@Bean
AuthorizationManagerFactory<Object> authorizationManagerFactory() {
    return AuthorizationManagerFactories.multiFactor()
        .requireFactors(
            FactorGrantedAuthority.PASSWORD_AUTHORITY,
            FactorGrantedAuthority.OTT_AUTHORITY
        )
        .build();
}
~~~

This is an **illustrative bean snippet**, using Spring Security 7 classes in the appropriate packages. In an application, you normally choose **one** of the two approaches: annotation-generated factory or manually configured factory. Avoid declaring duplicate factory beans and assuming both combine automatically.

## 5. Spring Security 7 Password + OTT MFA Flow

A common Servlet web flow:

~~~text
Unauthenticated browser
         |
         | GET /private
         v
Authorization requires FACTOR_PASSWORD + FACTOR_OTT
         |
         | redirect to password login
         v
POST /login (valid username/password)
         |
         | Authentication has FACTOR_PASSWORD
         | but not yet FACTOR_OTT
         v
Redirect to One-Time Token Login
         |
         | POST /ott/generate requests token for account
         | Spring creates short-lived one-time token
         | success handler delivers token via external channel (email...)
         v
User receives token, submits to /login/ott
         |
         | verify unused token, right account, unexpired
         v
Authentication has both PASSWORD + OTT
         |
         | Authorization rule succeeds
         v
GET /private -> 200
~~~

In a real system, Spring Security manages transitioning/retaining factor evidence across the session according to the framework mechanism. Never arbitrarily merge two `Authentication` instances by taking the union of their authorities without following the contract; on principal changes, expiration, logout, or session fixation, ensure the previous user's factors cannot be reused for a new user.

**One-Time Token (OTT) differs from OTP/TOTP/HOTP.** Spring Security's `oneTimeTokenLogin()` (available since 6.4) provides a **single-use** token generated by the server and delivered via a handler/external channel such as email/magic link. This is not by default a 6-digit rolling TOTP code computed locally by an authenticator app.

Strong MFA requires checking **factor independence**: if both the password and email are stolen from the same device/session, risk remains. In particular, a magic link in the same browser can leak via URLs/logs; critical systems should consider WebAuthn/phishing-resistant MFA.

## 6. Spring Boot 4.0 / Spring Security 7.0 Example (Java 17+)

The complete example here builds a Servlet application using:

- Spring Boot **4.0.x** (e.g., `4.0.9`) and Spring Security **7.0.x** via the BOM.
- Form login with an in-memory lab user.
- One-Time Token Login; `OneTimeTokenGenerationSuccessHandler` sends the token via SMTP **to a pre-registered mailbox**.
- `@EnableMultiFactorAuthentication` requiring PASSWORD + OTT for authorization rules.
- Route `/me` to observe the result after authentication; `/admin/info` additionally requires role ADMIN.

**End-to-end execution requirements:** you need an SMTP/mail capture server (such as Mailpit in a lab environment) and a browser preserving session cookies. The Java/Maven code compiles and starts with the right dependencies; receiving the OTP/OTT requires a real mail environment. The `example.test` domain is test data only, not a public operational email.

### 6.1. Directory Structure

~~~text
mfa-demo/
├── pom.xml
└── src/main/
    ├── java/demo/mfa/MfaDemoApplication.java
    └── resources/application.properties
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>mfa-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-mail</artifactId>
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

Spring Boot 4 introduces the new starter `spring-boot-starter-webmvc` (replacing the older web starter name). The parent BOM manages compatible Spring Security 7 versions; do not override down to `spring-security-core:6.x` because the MFA classes will not exist.

### 6.3. application.properties

File `src/main/resources/application.properties`:

~~~properties
server.port=8080

# SMTP dev-only: locally running Mailpit/mail capture tool.
spring.mail.host=127.0.0.1
spring.mail.port=1025

# Do not put real SMTP credentials into Git.
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=5000
spring.mail.properties[mail.smtp.writetimeout]=5000
~~~

The test SMTP mail capture server does not send emails to the Internet; learners read messages in a dedicated mail capture UI (for example, Mailpit typically opens at `http://localhost:8025` if configured that way). Never deploy an unauthenticated public mail sink in production.

### 6.4. MfaDemoApplication.java

~~~java
package demo.mfa;

import java.util.Map;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
public class MfaDemoApplication {

    private static final String DEMO_USER = "learner@example.test";

    public static void main(String[] args) {
        SpringApplication.run(MfaDemoApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername(DEMO_USER)
                .password("{noop}lab-password")
                .roles("USER")
                .build()
        );
    }

    @Bean
    OneTimeTokenGenerationSuccessHandler sendOttViaMail(
            JavaMailSender mailSender) {
        return (request, response, token) -> {
            // Demo only accepts the mailbox belonging to the provisioned account.
            // Production must look up a server-verified email.
            if (DEMO_USER.equals(token.getUsername())) {
                SimpleMailMessage message = new SimpleMailMessage();
                message.setFrom("no-reply@example.test");
                message.setTo(DEMO_USER);
                message.setSubject("Your one-time login token");
                message.setText(
                    "One-time token (use it on the /login/ott form):\n"
                    + token.getTokenValue()
                );
                mailSender.send(message);
            }
            // Do not expose the token in HTTP responses or server logs.
            response.sendRedirect(request.getContextPath() + "/login/ott");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OneTimeTokenGenerationSuccessHandler ottHandler)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(ott -> ott
                .tokenGenerationSuccessHandler(ottHandler));

        return http.build();
    }

    @RestController
    static class DemoApi {

        @GetMapping("/me")
        Map<String, Object> currentUser(Authentication auth) {
            List<String> authorities = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();

            return Map.of(
                "username", auth.getName(),
                "authorities", authorities
            );
        }

        @GetMapping("/admin/info")
        String adminInfo() {
            return "admin protected";
        }
    }
}
~~~

**Configuration explanation:**

1. `@EnableMultiFactorAuthentication` on the application class requires both `FACTOR_PASSWORD` and `FACTOR_OTT` via the authorization factory.
2. `UserDetailsService` contains only `learner@example.test` with `ROLE_USER`; `{noop}` is for lab execution only—**never use plaintext passwords in production**.
3. `formLogin` enables password authentication; `oneTimeTokenLogin` enables the OTT generation/consumption flow.
4. `OneTimeTokenGenerationSuccessHandler` is the part you **must customize** to deliver tokens to users. The framework cannot infer email/SMS delivery on its own. The bean in the example only sends to the provisioned mailbox, never arbitrarily using an attacker-supplied address.
5. `mailSender.send` calls the configured internal SMTP server. Never use a handler that prints the token to access logs, response URLs, or query parameters without a threat model.
6. `/me` returns learning data and is accessible only when MFA is satisfied. Endpoint `/admin/info` also requires `ROLE_ADMIN`; the demo user has role USER and is still denied even after completing both factors.
7. Default form-login and OTT submit pages are provided by the framework. Spring protects state-changing HTTP POSTs with CSRF by default; browsers must submit proper forms/tokens—never disable CSRF just to make the demo work.

**This is lab code**, not a complete production MFA design: you need a persistent user store/OTT service, verified out-of-band token delivery, a real mail provider, rate limiting, auditing, account status checks, recovery, and session/HA policies.

### 6.5. Running the Lab and Expected Results

Requires JDK 17+, Maven, and a dev SMTP server. For example, if you have Docker installed, you can run a mail capture server:

~~~bash
docker run --rm -p 1025:1025 -p 8025:8025 axllent/mailpit:latest
~~~

The command uses a third-party mail capture tool image for lab machines only; the Docker environment must have network access to pull the image if not already cached. Another SMTP capture tool can be used. For production, configure a real SMTP server, TLS/authentication, and secrets from a vault.

In the `mfa-demo` directory:

~~~bash
mvn spring-boot:run
~~~

Once the app starts:

1. Open `http://localhost:8080/me` in an unauthenticated browser.
2. Spring's login page prompts for password: username `learner@example.test`, password `lab-password`.
3. Password is valid, but without OTT the MFA rule is not yet satisfied; Spring Security routes the user to the supplementary step.
4. From the OTT UI, request token generation for the account. Default token generation accepts the username and the handler sends to the SMTP capture server.
5. Open the dev mailbox UI (e.g., `http://localhost:8025`), read the OTT code, and submit it at `/login/ott`.
6. If the token is valid, unexpired, unused, and bound to the right account, returning to `/me` yields 200. JSON in Spring Security 7 typically includes at least these authorities:

~~~json
{
  "username": "learner@example.test",
  "authorities": ["FACTOR_OTT", "FACTOR_PASSWORD", "ROLE_USER"]
}
~~~

Additional authorities may be present depending on version and policy; when writing integration tests, verify **that the two required factors are present** rather than hardcoding the entire list.

With account `learner@example.test`, accessing `/admin/info` is still denied due to missing `ROLE_ADMIN`, even though MFA is complete.

**Do not use `curl -u` to conclude that MFA works.** This is a browser flow with sessions, forms, CSRF, and redirects to the missing factor; HTTP Basic or Bearer tokens do not exercise the same factor-accumulation flow.

### 6.6. Why Are Negative Tests Necessary?

| Scenario | Expected Outcome |
| --- | --- |
| Neither password nor OTT entered | Cannot view `/me`; routed to corresponding login |
| Valid password only, no OTT | Cannot access resources requiring both factors |
| Valid OTT but missing password factor | Cannot access resources requiring both factors |
| Valid password + OTT, same account/session, unexpired | Allowed to access `/me` |
| Expired token | Cannot grant the OTT factor |
| Reusing an already-consumed OTT | Cannot be reused as valid evidence |
| User A's OTT submitted in User B's flow | Does not grant factor to User B |
| Both factors present but missing ADMIN role | Cannot access `/admin/info` |
| Log out then reuse old session | Cannot continue using previously authenticated factors |
| SMTP unresponsive | Must not silently treat OTT as verified; fail closed |

For Servlet applications with form-based authentication, missing factors can produce an **HTTP 302 redirect to the login/step-up page**, not necessarily 401/403 directly. Check **no authorization granted**, redirects, and session state rather than hardcoding every case to 403.

## 7. Selective MFA Configuration: Only Sensitive Endpoints

Not every system needs global MFA. For example:

- `/dashboard/**`: requires only authenticated.
- `/user/settings/**`: requires PASSWORD + OTT.
- `/admin/**`: requires PASSWORD + OTT + ROLE_ADMIN.

If you use the annotation with global `authorities = { PASSWORD, OTT }`, it is no longer a “settings/admin only” policy. Spring Security 7 supports selective design by enabling annotation support **without publishing a global mandatory factory**:

~~~java
@EnableMultiFactorAuthentication(authorities = {})
~~~

Then create a factory **locally inside the SecurityFilterChain configuration**:

~~~java
// Illustrative @Bean method snippet for Spring Security 7.0+.
@Bean
SecurityFilterChain selectiveSecurityFilterChain(HttpSecurity http)
        throws Exception {
    var mfa = AuthorizationManagerFactories.multiFactor()
        .requireFactors(
            FactorGrantedAuthority.PASSWORD_AUTHORITY,
            FactorGrantedAuthority.OTT_AUTHORITY
        )
        .build();

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin/**").access(mfa.hasRole("ADMIN"))
            .requestMatchers("/user/settings/**")
                .access(mfa.authenticated())
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .oneTimeTokenLogin(Customizer.withDefaults());

    return http.build();
}
~~~

This is an **illustrative configuration method**; it requires Spring Security 7 imports and integrating the OTT delivery handler as in section 6. When using this method, replace the example's global `securityFilterChain`—**do not** simultaneously define two chains with overlapping matchers for the same URLs without proper design.

**Meaning:** only `/admin/**` and `/user/settings/**` use the `mfa` factory and therefore require two factors. `anyRequest().authenticated()` uses the normal authentication rule. Do not expose `mfa` as a `@Bean` in this case unless you want the rule applied globally.

### 7.1. Using hasAllAuthorities When Policy Is Simple

Spring Security 7 can express the requirement directly:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasAllAuthorities(
        "ROLE_ADMIN",
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY
    )
    .anyRequest().authenticated()
)
~~~

This is only a **DSL snippet**; it must be placed inside `HttpSecurity` with login mechanisms configured. With many routes and complex policies, repeating factor lists becomes hard to maintain; `AuthorizationManagerFactory` helps reuse policies. Having only `hasAuthority("FACTOR_OTT")` does not enforce two-factor MFA.

### 7.2. Using the Annotation with Method Security

In Spring Security 7 Servlet, `@EnableMultiFactorAuthentication`'s Javadoc states that the requirements can be used alongside `@EnableWebSecurity` and `@EnableMethodSecurity`. For example, `@PreAuthorize("hasRole('ADMIN')")` can participate in the appropriately configured policy. However, enabling MFA on the filter chain does not mean every method/dispatcher path automatically receives the same assurance if method security is disabled or multiple security chains exist. Design policies consistently and write tests for both HTTP requests and service methods.

## 8. Factors Must Stay “Fresh”: validDuration and Step-Up

An application might want:

- Dashboard page: any authentication, timestamp irrelevant beyond session policy.
- Changing phone number: password verified within **30 minutes**.
- Transferring funds: password within **30 minutes** and OTT within **5 minutes**.

Using `FactorGrantedAuthority.getIssuedAt()`, Spring Security 7 supports configuring expiration in **authorization rules**, for example:

~~~java
// Spring Security 7.0+ config snippet, not a standalone class.
var passwordFresh30m = AuthorizationManagerFactories.multiFactor()
    .requireFactor(factor -> factor
        .passwordAuthority()
        .validDuration(java.time.Duration.ofMinutes(30)))
    .build();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/account/change-phone/**")
        .access(passwordFresh30m.authenticated())
    .anyRequest().authenticated());
~~~

Once 45 minutes have elapsed since entering the password, the “30 minutes” rule is no longer satisfied. The same authority in the session can still satisfy a “within 1 hour” rule if that policy allows it.

**The `issuedAt` timestamp is not session expiration.** Requiring reauthentication for sensitive factors must be evaluated under its own policy, and upon completion the new factor timestamp must be recorded properly. In multi-instance environments, ensure clock synchronization, session persistence, and step-up policies.

You can configure multiple factors with different `validDuration` values via repeated `requireFactor(...)` calls as supported by the factory API. When **multiple** factors are needed, never check only the age of one factor and forget the second.

## 9. When Does a Single Strong Method Replace “Password + OTT”?

A passkey/WebAuthn can provide proof of private key possession bound to the RP ID and, when UV is required, verify the user on the authenticator. Depending on organizational policy, a phishing-resistant method like a passkey may achieve the desired assurance level without needing password and email OTT.

Never assume:

~~~text
FACTOR_WEBAUTHN = FACTOR_PASSWORD + FACTOR_OTT
~~~

That is **not an identity in Spring Security**. If a policy wants to allow:

- **WebAuthn**, or
- **password AND OTT**,

you must express an **OR rule between two combinations** using an authorization manager. Spring Security 7 provides `AllRequiredFactorsAuthorizationManager.anyOf(...)` to express this policy when using the appropriate version API.

Illustrative example:

~~~java
// Spring Security 7.x config snippet; chain and WebAuthn
// registration/repository must be configured separately.
AllRequiredFactorsAuthorizationManager<Object> passkey =
    AllRequiredFactorsAuthorizationManager.<Object>builder()
        .requireFactor(factor -> factor.webauthnAuthority())
        .build();

AllRequiredFactorsAuthorizationManager<Object> passwordAndOtt =
    AllRequiredFactorsAuthorizationManager.<Object>builder()
        .requireFactor(factor -> factor.passwordAuthority())
        .requireFactor(factor -> factor.ottAuthority())
        .build();

var alternatives = AllRequiredFactorsAuthorizationManager.anyOf(
    passkey, passwordAndOtt);
~~~

This snippet **does not run standalone** and does not provide WebAuthn enrollment, RP ID/origin, or OTT delivery; those components must be implemented and tested in their own modules. When combined with `AuthorizationManagerFactory`, access is granted only if one valid combination passes per policy.

### 9.1. WebAuthn Registered Condition in Spring Security 7.1+

Spring Security 7.1 documentation introduces a conditional example:

~~~java
// Use only when the actual version supports MultiFactorCondition.
@EnableMultiFactorAuthentication(
    authorities = {
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.WEBAUTHN_AUTHORITY
    },
    when = MultiFactorCondition.WEBAUTHN_REGISTERED
)
~~~

This configuration illustrates requiring password + WebAuthn **for users who have registered a passkey**, requiring WebAuthn repository beans (`PublicKeyCredentialUserEntityRepository` and `UserCredentialRepository`) to determine registration status. **Do not copy the `when` attribute into Spring Security 7.0** if that version's annotation/Javadoc does not have it. If security requires MFA for all users, never use an “only when registered” condition and leave unregistered users unprotected; there must be an enrollment policy and proper fail-closed behavior.

## 10. Standalone Java 17: Demonstrating Authorities, Factors, and Freshness

The small lab below uses no Spring libraries and **performs no authentication**. It helps clarify three separate concepts: business permissions, recorded factors, and factor freshness.

Create the file `FactorPolicyDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;

public class FactorPolicyDemo {

    record VerifiedFactor(String authority, Instant issuedAt) {}

    static boolean hasFactor(
            List<VerifiedFactor> factors, String expected) {
        return factors.stream()
                .anyMatch(f -> f.authority().equals(expected));
    }

    static boolean factorIsFresh(
            List<VerifiedFactor> factors,
            String expected,
            Instant now,
            Duration maximumAge) {
        return factors.stream().anyMatch(f ->
            f.authority().equals(expected)
            && !f.issuedAt().isAfter(now)
            && !f.issuedAt().plus(maximumAge).isBefore(now));
    }

    static boolean mayAdmin(
            Set<String> roles, List<VerifiedFactor> factors) {
        return roles.contains("ROLE_ADMIN")
                && hasFactor(factors, "FACTOR_PASSWORD")
                && hasFactor(factors, "FACTOR_OTT");
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T09:00:00Z");

        var factors = List.of(
            new VerifiedFactor("FACTOR_PASSWORD",
                now.minus(Duration.ofMinutes(45))),
            new VerifiedFactor("FACTOR_OTT",
                now.minus(Duration.ofMinutes(2)))
        );

        System.out.println("bothFactors=" +
            (hasFactor(factors, "FACTOR_PASSWORD")
                && hasFactor(factors, "FACTOR_OTT")));
        System.out.println("password30m=" +
            factorIsFresh(factors, "FACTOR_PASSWORD",
                now, Duration.ofMinutes(30)));
        System.out.println("ott5m=" +
            factorIsFresh(factors, "FACTOR_OTT",
                now, Duration.ofMinutes(5)));
        System.out.println("adminAsUser=" +
            mayAdmin(Set.of("ROLE_USER"), factors));
        System.out.println("adminWithRole=" +
            mayAdmin(Set.of("ROLE_ADMIN"), factors));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac --release 17 FactorPolicyDemo.java
java FactorPolicyDemo
~~~

**Exact** stdout:

~~~text
bothFactors=true
password30m=false
ott5m=true
adminAsUser=false
adminWithRole=true
~~~

Explanation:

- **Both** factors are present, but password is 45 minutes old and no longer meets the 30-minute rule.
- OTT was verified 2 minutes ago and meets the 5-minute rule.
- A user with both factors but only `ROLE_USER` cannot access a route requiring `ROLE_ADMIN`.
- With `ROLE_ADMIN` and sufficient factors, the simple `mayAdmin` rule allows access. If the route requires fresh factors, `factorIsFresh` must be combined into the policy.

**Do not use this program to perform real MFA.** It intentionally accepts a list named `VerifiedFactor` without proving that password/OTT were actually verified. In a real system, only the framework/trusted authentication providers after successful verification may grant factor authorities.

## 11. Common Mistakes and Fixes

| Symptom / Mistake | Cause | Fix |
| --- | --- | --- |
| `FactorGrantedAuthority` import not found | Using Spring Security 6.x | Move to 7.0+ with Boot 4 or use a 6.x-compatible MFA design |
| `@EnableMultiFactorAuthentication` fails to compile | Wrong version or wrong package | Use `org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication` on 7.0+ |
| Annotation present but app still asks only for password | OTT/WebAuthn mechanism not enabled or handler/token delivery not configured | Configure factor providers and verify step-up flow |
| One-time token not delivered to user | Missing `OneTimeTokenGenerationSuccessHandler` or SMTP failure | Implement delivery channel, timeouts, and log protection |
| Token arrives in same browser making MFA weak | Email/device channel not independent | Assess threat model; consider passkey/hardware key |
| Login succeeds but enters redirect loop | Session/context not saved, missing factor unreachable, wrong endpoint matcher | Check login entry points, session cookie, filter chain, and token delivery |
| Incorrect authorization when using only `hasRole("ADMIN")` while wanting MFA | Not using a factor-aware factory or missing factor rules | Use global annotation or proper selective factory |
| Misusing `permitAll` or allowlist | Sensitive endpoint skips check due to matcher/order | Audit every `SecurityFilterChain` and route |
| User has sufficient factors but gets 403 on admin | Missing `ROLE_ADMIN` or object-level policy | Check distinct authorities between roles and factors |
| Factor persists in session too long | Missing `validDuration`/reauth requirement for sensitive actions | Enforce factor-age policies and session timeouts |
| Same OTT can be reused | Token service/consumption does not guarantee one-time use | Persistent token store, atomic consume, TTL, and replay tests |
| Account A's OTT completes flow for Account B | Incorrect username/session binding | Bind token to exact principal; prevent session mix-up |
| New login flow retains old factors of another user | Session fixation/concurrency bug | Test account switching, session invalidation, and `SecurityContext` lifecycle |
| Custom JWT sets `FACTOR_OTT` string from client input | Factor spoofed via untrusted claims | Trust only verified issuers/mechanisms; design strict claim contracts |
| `MultiFactorCondition.WEBAUTHN_REGISTERED` unsupported | On 7.0 branch or missing repositories | Verify version 7.1+, register WebAuthn repositories and enrollment |
| Using Servlet annotations in WebFlux | Different stack/security DSL | Read version-specific reactive docs; do not assume identical support |

## 12. Preserving Security Meaning in Real Development

### 12.1. OTT Must Be Short-Lived and Single-Use

A one-time token is a sensitive credential. Production requires:

- Unpredictable token values generated with a CSPRNG.
- Short TTL, single-use only, with atomic consumption to prevent races.
- Binding the token to the exact user and login ceremony/request as designed.
- Delivery via a verified mailbox or channel, never an address specified arbitrarily by the client.
- Rate limiting on token generation and validation to prevent email spam and account enumeration.
- Never logging raw tokens, or leaking them in analytics/referrers or support screenshots.
- Telemetry and alerting for anomalous behavior.

Spring Security One-Time Token Login provides a default in-memory service for demos; production typically needs a persistent service such as JDBC and an appropriate HA policy. When delivering tokens via email, an email inbox can be compromised, so it does not by default achieve FIDO2 hardware assurance.

### 12.2. Sessions and Factor State

MFA spans **multiple HTTP steps**. Protect:

- Cookies with appropriate `Secure`, `HttpOnly`, and `SameSite` flags.
- HTTPS everywhere, HSTS in production.
- Session fixation protection after authentication and step-up.
- CSRF protection on form/OTT endpoints.
- Session timeout/invalidation on logout, account switch, and credential reset.
- Shared session store when load-balancing across multiple instances, or a topology ensuring accurate state persistence.
- Reauthentication rules for highly sensitive actions.
- Recording factor timestamps and re-checking them whenever policy requires.

A **stateless** JWT Resource Server does not accumulate password + OTT over a Servlet session; if the system uses OAuth/OIDC, design MFA evidence with the IdP/AS using claims like `amr`/`acr` where appropriate, while verifying issuer, audience, freshness, and exact claim semantics. Never replace full MFA with a client-sent `amr=["pwd","otp"]`.

### 12.3. Authorization Is Still Needed After MFA

MFA confirms the quality of login evidence; it does not replace checking:

- `ROLE_ADMIN` for administrative features.
- Tenant/organization authorization.
- Object-level permissions (records, accounts, reports).
- Risk/step-up conditions based on amount, IP, and device posture when policy requires.
- Credential management permissions (adding/removing passkeys, changing email/phone, recovery codes).

Adding more factors does not fix IDOR/BOLA bugs or overly permissive policies.

## 13. Recommended Testing Matrix

### Functional

- [ ] Valid password alone cannot pass a route requiring both factors.
- [ ] Valid OTT alone cannot pass a route requiring both factors.
- [ ] Valid password + OTT for the same principal/session passes the MFA rule.
- [ ] ADMIN role and both factors are all required for `/admin/**`; missing any of the three is denied.
- [ ] Expired, reused, or tampered OTT cannot grant `FACTOR_OTT`.
- [ ] OTP/TOTP is not confused with Spring OTT without a dedicated provider.
- [ ] Logout, session expiration, and account switching clear the corresponding factors.
- [ ] A 45-minute-old password factor fails a route requiring a 30-minute `validDuration`.
- [ ] A 2-minute-old OTT still satisfies a 5-minute `validDuration`.
- [ ] With MFA scoped only to settings/admin, the dashboard remains accessible with normal authentication.

### Security and Resilience

- [ ] Cannot self-submit `FACTOR_PASSWORD`/`FACTOR_OTT` in forms/headers to bypass checks.
- [ ] OTT is delivered to the provisioned mailbox; bulk generation requests are rate-limited.
- [ ] OTT codes never appear in access logs, exception logs, redirect query strings, or analytics.
- [ ] SMTP errors/timeouts never cause the framework to treat the factor as succeeded.
- [ ] Replay/race conditions are blocked when two requests attempt to consume an OTT concurrently.
- [ ] Multiple `SecurityFilterChain`s do not accidentally bypass the factory/MFA.
- [ ] Clustered/shared session and OTT stores maintain accurate state across replicas.
- [ ] Session cookies and CSRF are not disabled to work around demo issues.
- [ ] If OAuth/OIDC/WebAuthn is present, separately test trust boundaries, issuance, and RP/issuer validation.

### Version Checks

- [ ] Use `mvn dependency:tree` or your build tool to confirm **Spring Security 7.x** is on the classpath.
- [ ] Do not import `FactorGrantedAuthority` in a project running only Security 6.x.
- [ ] Do not use 7.1+ annotation attributes or builders on 7.0 if absent from Javadoc.
- [ ] Check Servlet/Reactive documentation separately instead of assuming parity.
- [ ] Include integration tests covering redirects, OTT delivery mechanism, and multi-factor enforcement.

## 14. Self-Check Questions

1. Why is `ROLE_ADMIN` not considered an authentication factor?
2. What authority value does `FactorGrantedAuthority.PASSWORD_AUTHORITY` have? What about `OTT_AUTHORITY`?
3. How does `getIssuedAt()` differ from session expiration?
4. Does `@EnableMultiFactorAuthentication` generate OTT codes or send emails automatically?
5. Why does an application need both `formLogin()` and `oneTimeTokenLogin()` when policy requires password + OTT?
6. Why are two OTPs received in the same mailbox not automatically two independent factors?
7. Why must you never manually add `SimpleGrantedAuthority("FACTOR_OTT")` to get past a rejected request?
8. Why can't you copy code using `@EnableMultiFactorAuthentication` from Spring Security 7 into Spring Security 6.5?
9. If you want MFA only on `/admin/**` and `/user/settings/**`, should you configure a global factory or a local factory?
10. Why might a password used 45 minutes ago fail a route requiring a password within 30 minutes?
11. What is the threat-model difference between password + OTT and WebAuthn login with UV?
12. When an API uses stateless JWTs, does adding the Servlet annotation cause the IdP to issue tokens containing MFA evidence?

**Conclusion:** `FactorGrantedAuthority` describes a **proven factor** and when it was proven; `@EnableMultiFactorAuthentication` (**Spring Security 7.0+**) adds **mandatory factor policies** to authorization. For MFA to truly exist, the application still needs **trusted authentication mechanisms**, evidence delivery/collection channels, session/token lifecycles, and corresponding business authorization checks.

## 15. Official Documentation and References

- [Spring Security 7.0 — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html)
- [Spring Security 7.1 — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/7.1/servlet/authentication/mfa.html)
- [Spring Security 7.0 — FactorGrantedAuthority API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html)
- [Spring Security 7.0 — @EnableMultiFactorAuthentication API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html)
- [Spring Security 7.0 — One-Time Token Login](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/onetimetoken.html)
- [Spring Boot 4.0 — Getting Started and Maven Starters](https://docs.spring.io/spring-boot/4.0/tutorial/first-application/index.html)
- [Spring Boot 4.0 — Sending Email](https://docs.spring.io/spring-boot/4.0/reference/io/email.html)
- [OWASP — Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)

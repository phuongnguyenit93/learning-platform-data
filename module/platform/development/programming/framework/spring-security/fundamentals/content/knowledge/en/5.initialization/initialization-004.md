# Default Account, Auto-Generated Password, and Development Usage Limits

## 1. Why Does the API Already Require Login Right After Installing Spring Security?

A Spring Boot application with a `GET /hello` controller can normally be called immediately before security is added. When you add **spring-boot-starter-security**, the same request may receive **401 Unauthorized** in curl or be redirected to a login page when accessed in a browser. The startup log prints **Using generated security password: ...**.

This is Spring Boot's **auto-configuration** behavior: the web application gets default HTTP protection and usually a test account so developers can observe the login flow. This is useful during initialization, yet it is **neither a user management system nor a production configuration**.

This lesson explains how that account is created, where the password appears, when the password changes, how to use it while learning, how to customize it via properties, when auto-configuration backs off, and the limits of using the test account.

**Scope:** Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Spring MVC/Servlet. Other Boot/Security versions may change configuration and logging details; read the documentation for your actual version. WebFlux has its own reactive configuration mechanism.

### Learning Outcomes

After this lesson, you will be able to:

1. Identify the source of the username/password and storage state of the default account.
2. Find the generated password from the log of the currently running startup.
3. Explain why a browser may display a login page while curl receives HTTP 401.
4. Distinguish replacing **SecurityFilterChain** from replacing **UserDetailsService**.
5. Use **spring.security.user.name/password/roles** within their proper scope.
6. Analyze cases where Boot stops creating the default user due to custom beans or new dependencies.
7. Test `/public`, `/private`, and `/admin` policies and explain 200, 401, 403, and 404.
8. Know the changes required before deploying to real users.

## 2. Two Default Mechanisms to Distinguish

Many people assume there is only a single "default security configuration." In Spring Boot 3.3 Servlet apps, distinguish:

| Group | Related Auto-Configuration | Responsibility |
| --- | --- | --- |
| **HTTP protection** | SecurityAutoConfiguration and SpringBootWebSecurityConfiguration | Creates the default web protection policy when no custom SecurityFilterChain exists |
| **Test user source** | UserDetailsServiceAutoConfiguration | Creates a UserDetailsService/in-memory user if no replacement authentication source exists |
| **Authentication events** | DefaultAuthenticationEventPublisher | Publishes authentication events per default integration |

The first group decides **which endpoints require login**, while the second group supplies **an account to verify credentials against**. They are auto-configured under different conditions.

Therefore:

- Declaring a custom **SecurityFilterChain** bean makes Boot's **default web security** configuration back off, yet **does not automatically remove the default user**.
- Declaring a custom **UserDetailsService** bean stops Boot from creating the default UserDetailsService, yet **does not automatically make endpoints public**.
- A custom AuthenticationProvider or AuthenticationManager bean can also cause UserDetailsService auto-configuration to back off.
- Certain OAuth2/SAML2 modules on the classpath also affect whether Boot creates the default user.

This is the most important relationship in this lesson: **HTTP policy** and **authentication source** are two independent components, even though they collaborate on a request.

## 3. Spring Boot 3.3's Default Account

When Spring Security is on the classpath, the web app has not replaced the relevant beans, and other conditions hold, Boot may create a single account:

| Attribute | Default Value or Mechanism |
| --- | --- |
| Username | **user** |
| Password | **Random string generated at application startup** |
| Store | **InMemoryUserDetailsManager** in process memory |
| Default role | **USER**, corresponding to the typical authority ROLE_USER |
| Login | Form login or HTTP Basic depending on request/configuration |
| Stored in database? | **No**; this is not a record in a business users table |

This account does not come with email, phone number, MFA, password reset, multi-user management, or business admin privileges. The default role is typically USER, **not ADMIN**. Do not infer that a URL named `/admin` is protected by ADMIN merely from its path name.

### 3.1. How Is the Password Printed?

In Spring Boot 3.3, when the password is auto-generated, the startup log may contain a **WARN**-level message:

~~~text
Using generated security password: 78fa095d-3f4c-48b1-ad50-e24c31d5cf35

This generated password is for development use only. Your security configuration must be updated before running your application in production.
~~~

This is an **example log format**, not a shared password across applications. The real password must be taken from **the exact startup of that exact instance**.

If the log does not show it, do not jump to the conclusion that security is disabled. The password may have been configured in properties, the default UserDetailsService may have backed off, or logging may suppress warnings from **org.springframework.boot.autoconfigure.security**. In Spring Boot 3.3, if you adjust logging, WARN messages in that logger must remain enabled to see the generated password.

### 3.2. Does the Password Change After Restart?

When Boot generates it, creating a new ApplicationContext **normally generates a different password**. Thus yesterday's password is not a stable credential for today's session. The account lives in each process's memory; multiple replicas can have different auto-generated passwords.

This random password is:

- Not a database root/admin password.
- Not a JWT signing key.
- Not an API key issued to application clients.
- Not a real customer's password.
- Not a secret distributed consistently across servers.

### 3.3. Why Is Printing the Password in Logs a Risk?

The password in the log is a **real credential of the running application**, even though it was randomly generated. Logs can be collected by terminals, CI tools, Docker/container runtimes, observability agents, or centralized logging systems. Anyone who can read the relevant logs and reach the application can attempt to use that password.

Never share screenshots publicly containing the generated password; never paste it into issues/tickets or operational docs. The "for development use only" warning emphasizes that this mechanism is designed for **local testing**, not real internet-facing accounts.

## 4. How Does Default HTTP Protection Behave?

For a Servlet web app with Spring Security and no replacement SecurityFilterChain, Spring Boot typically requires authentication for application endpoints, including **/error**. It offers **HTTP Basic** or **form login** based on content negotiation.

Some common outcomes:

- **curl** sending an unauthenticated request asking for JSON usually gets **HTTP 401**.
- A **Browser** sending an HTML-preferring Accept header may be redirected **302** to the login page.
- Valid login to a URL with no Controller may return **404**.
- If a role policy exists, an authenticated user lacking privileges may get **403**.
- A state-changing request lacking a valid CSRF token may receive **403**, even with valid username/password.

**Authentication** determines whether the requester has valid credentials. **Authorization** decides what that identity is allowed to do. Boot's defaults are a starting point for web protection; they do not automatically know who owns individual records.

### 4.1. Actuator Is Not an Exception You Can Ignore

If using Spring Boot Actuator, **exposing an endpoint** and **protecting an endpoint** are two separate concerns. Health endpoints often have their own access policy, while sensitive management endpoints need proper protection.

When declaring your own SecurityFilterChain, you become responsible for both application HTTP policies and related Actuator endpoints. Do not rely on Boot having protected management endpoints previously and assume a new chain will automatically preserve all old rules.

## 5. Practice A: An Application with Only Default Security Configuration

### 5.1. Create the Project

Use Spring Initializr to generate a Java 17+ project with Spring Boot 3.3.x, Gradle Groovy DSL, and Spring Web/Spring Security. If you already have a Boot project with Gradle Wrapper, you only need these two dependencies in build.gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

This is the dependencies block of a Boot project that already configures plugins and build tooling, not a complete standalone build.gradle.

### 5.2. Complete Java File

Create **src/main/java/com/example/defaultsecurity/DefaultSecurityApplication.java**:

~~~java
package com.example.defaultsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DefaultSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(DefaultSecurityApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    String privateEndpoint() {
        return "private OK";
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

The public class matching the filename holds the Spring Boot entry point. The controller is a package-private class in the same package, so Spring Boot component scanning discovers it. **In Step A, do not create custom SecurityFilterChain or UserDetailsService beans yet.**

### 5.3. Run the Project and Find the Password

In the directory containing Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On PowerShell use **.\gradlew.bat bootRun**. Find the `Using generated security password` line in the startup console and use the password from **the current run**. HTTP Basic sends credentials as Base64, not secure encryption; the example uses localhost for learning, whereas real systems must use HTTPS.

Test with curl:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/public
curl -i -u user http://localhost:8080/public
curl -i -u user http://localhost:8080/private
curl -i -u user http://localhost:8080/admin
~~~

Passing **-u user** makes curl prompt for the password in the terminal when not supplied inline. Enter the generated value from the log. On Windows PowerShell, use **curl.exe** if `curl` is an alias.

**Expected result table for Step A:**

| Request | HTTP status | Meaning |
| --- | --- | --- |
| /public, no credentials, Accept: application/json | **401** | By default Boot still protects an endpoint named public |
| /public, valid credentials | **200**, public OK | Authentication succeeded |
| /private, valid credentials | **200**, private OK | Authentication succeeded |
| /admin, valid credentials | **200**, admin OK | No rule yet requires role ADMIN for URL /admin |
| Unmapped URL, valid credentials | Possibly **404** | Authentication succeeded but no Controller exists |

The path name **/admin** does not automatically create a **hasRole("ADMIN")** rule. Thus 200 in Step A does not prove the default user account is a business admin.

The results above are **inferred from the demo configuration**, not live run output captured in this document. If your environment has proxies, extra configuration, or other dependencies, verify directly against your running app.

### 5.4. Why Can a Browser Show a Login Form?

Spring Security chooses the authentication entry point based on the request and content negotiation. Browsers sending an HTML-preferring Accept header are normally redirected to form login; clients requesting JSON usually receive an HTTP Basic challenge. Both responses can be valid for the same protected endpoint.

## 6. Customizing the User via Properties

Spring Boot provides three commonly used properties:

| Property | Effect |
| --- | --- |
| **spring.security.user.name** | Username of the default user |
| **spring.security.user.password** | Fixed password, replacing Boot's auto-generated password |
| **spring.security.user.roles** | Roles assigned to the default user |

Example in **src/main/resources/application-local.properties**:

~~~properties
spring.security.user.name=devuser
spring.security.user.roles=USER
~~~

This example does not write a password into the file. When running the `local` profile, you can supply the password via the **SPRING_SECURITY_USER_PASSWORD** environment variable, which Spring Boot maps to `spring.security.user.password`.

On Windows PowerShell:

~~~powershell
$env:SPRING_SECURITY_USER_PASSWORD = 'local-demo-pass-123'
.\gradlew.bat bootRun --args='--spring.profiles.active=local'
~~~

On Linux/macOS with bash:

~~~bash
SPRING_SECURITY_USER_PASSWORD='local-demo-pass-123' \
./gradlew bootRun --args='--spring.profiles.active=local'
~~~

The password in the command is only for local learning; never reuse it in real systems. Shell history and process environments can record values, so production requires proper secret management and secure deployment pipelines.

After configuring:

1. The username created by Boot is **devuser**, not the original `user`.
2. The password comes from the environment variable, so an auto-generated random password is no longer needed for this account.
3. Role USER corresponds to ROLE_USER in typical configuration.
4. It remains **a single simple in-memory account**, not a database user or SSO.

Try logging in with **curl -i -u devuser http://localhost:8080/private** and entering the local password when prompted.

### 6.1. Can You Put the Password Directly in application.properties?

Technically you can set `spring.security.user.password` in the file. However, real passwords stored in source code, container images, or shared configs are easily leaked. For local study, a non-sensitive demo password can be used to see the mechanism, yet before production you must switch to a managed credential source or identity provider.

### 6.2. Can You Add Multiple Users with spring.security.user.*?

These properties are meant for the **single default user**, not managing a multi-user account list. To support multiple users, design a custom `UserDetailsService`, user store, or identity system integration. Do not try to scale by scattering hardcoded passwords and treating that as user administration.

## 7. When Does Account Auto-Configuration Back Off?

Boot 3.3 evaluates the condition for creating the **default UserDetailsService** independently from the condition for creating the **default SecurityFilterChain**.

| Application Change | Boot Default Web Security | Default User |
| --- | --- | --- |
| Only starter-security added | Created when conditions match | Typically created in memory |
| Custom **SecurityFilterChain** bean | **Backs off**, uses app-declared chain | **May still exist** |
| Custom **UserDetailsService** bean | May still exist if no custom chain | **No longer created** |
| Custom **AuthenticationProvider** bean | May still exist if no custom chain | **No longer created** |
| Custom **AuthenticationManager** bean | May still exist if no custom chain | **No longer created** |
| Both custom chain and user source | Controlled by application | Controlled by application |
| OAuth2 Client/Resource Server/SAML2 module on classpath | Depends on actual chain setup | UserDetailsService auto-configuration may back off |

Modules in the last row include **spring-security-oauth2-client**, **spring-security-oauth2-resource-server**, and **spring-security-saml2-service-provider**. Boot 3.3 has separate classpath conditions for this group; if you still need an in-memory username/password alongside OAuth2, you must provide your own `UserDetailsService`.

**Mechanism takeaway:** declaring a SecurityFilterChain does not mean the generated password is gone. Conversely, declaring a UserDetailsService does not mean URL protection was removed. Always verify both explicitly.

## 8. Practice B: Change URL Policy While Keeping Boot's Account

Keep `DefaultSecurityApplication.java` from Step A unchanged. Create a second file **src/main/java/com/example/defaultsecurity/SecurityRules.java**:

~~~java
package com.example.defaultsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityRules {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/private").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

This is a **second Java file in the same project and package**, not a standalone snippet to run by itself. With `@Configuration` and `@Bean`, Spring Boot picks up the application-defined `SecurityFilterChain`. Then:

- `/public` is accessible without logging in.
- `/private` only requires authentication.
- `/admin` requires role ADMIN.
- Every other URL hits `denyAll` in this example.
- HTTP Basic is enabled; form login is disabled so 401 is easy to observe in tests.

**Replacing only the chain does not remove the default UserDetailsService** unless another condition causes it to back off. Without a fixed configured password, the app may still generate a startup password for `user`.

### 8.1. Results in Step B

Restart and read the password for this run if using the generated password. Test:

~~~bash
curl -i http://localhost:8080/public
curl -i -H "Accept: application/json" http://localhost:8080/private
curl -i -u user http://localhost:8080/private
curl -i -u user http://localhost:8080/admin
~~~

| Request | Expected HTTP status | Explanation |
| --- | --- | --- |
| /public, anonymous | **200**, public OK | permitAll |
| /private, anonymous | **401** | HTTP Basic requires authentication |
| /private, valid user/password | **200**, private OK | `authenticated()` is satisfied |
| /admin, valid user/password | **403** | Default user lacks `ROLE_ADMIN` |

In Step A, the default user could reach `/admin` because the policy only required authentication. In Step B, that user gets 403 because we added an explicit authorization rule. **What changed was the policy**, not the password.

### 8.2. Do Not Confuse 404 with 401/403

A request to a URL with no Controller can return 404 after passing security filters. Yet with **anyRequest().denyAll()**, unlisted URLs can be rejected immediately by policy before DispatcherServlet looks up a handler. Read authentication state, rules, and mappings together rather than guessing from a single status code.

## 9. Practice C: Replace the User Source with a Custom UserDetailsService

To observe the auto-generated account disappear once you supply a custom user source, create a third file **src/main/java/com/example/defaultsecurity/LocalUsers.java** in the same package:

~~~java
package com.example.defaultsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration(proxyBeanMethods = false)
public class LocalUsers {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-local-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-local-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

This snippet contains two hardcoded test accounts **intended solely for an isolated learning environment**. Never store real credentials in source code, never reuse these passwords in production, and never deploy `InMemoryUserDetailsManager` as an enterprise user system.

Once this `UserDetailsService` bean is present:

1. Boot no longer creates the default `UserDetailsService` with username `user`.
2. The auto-generated account and password are no longer an authentication source in the application.
3. Alice has `ROLE_USER`; admin has `ROLE_ADMIN`.
4. `SecurityRules` remains in place, so URL policies do not change.

Test:

~~~bash
curl -i -u alice http://localhost:8080/private
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
~~~

Enter the corresponding password when prompted. Expected outcomes are **200**, **403**, and **200** respectively. This clarifies: replacing `UserDetailsService` changes the **authentication source**, whereas `SecurityFilterChain` decides **authorization**.

## 10. Limits of the Default Account in Development and Production

### 10.1. One Test Account Is Not User Management

The in-memory default user lacks multi-account creation/deletion, identity verification, password reset, account disabling, MFA, complex permissions, and administrative auditing. It does not serve real customer login needs.

### 10.2. Random Passwords in Logs Are Still Secrets

Even though random, the password is a real credential. Centralized logs, CI pipelines, or anyone with log access could use it accidentally or intentionally. Never leave the generated password as a production access mechanism.

### 10.3. Unstable Lifecycle

Passwords can change across restarts. Multiple instances generate different values. Process memory does not replace a database or identity provider; it offers no synchronized management or credential revocation across machines.

### 10.4. Default Security Does Not Understand Business Permissions

Boot does not automatically know that USER A can only read A's orders, or that staff can only approve invoices within a spending limit. In real deployments, authorization must rely on roles/permissions and ownership data, not just `authenticated()`.

### 10.5. HTTP Protection Involves More Responsibilities

You must choose HTTPS/TLS, cookie and session policies, CSRF aligned with client types, CORS configuration, secret management, rate limiting, brute-force defenses, log hygiene, dependency updates, backup/restore procedures, and monitoring. `starter-security` supports many layers, yet **does not complete every operational control automatically**.

**Note:** HTTP Basic sends passwords in a Base64-encoded header; HTTPS is mandatory over any network. In browsers, state-changing requests may require a CSRF token because Spring Security enables CSRF protection by default in Servlet apps. Never disable CSRF just to make a POST return 200 without analyzing your credential model.

### 10.6. A Custom Chain Can Affect Actuator

Once your application declares a `SecurityFilterChain`, do not assume Boot protects Actuator for you the same way as before. Check both **endpoint exposure** and **access rules**, including operational endpoints.

## 11. Common Beginner Mistakes

| Symptom | Common Cause | Check / Resolution |
| --- | --- | --- |
| No generated password visible | Password pre-configured, user auto-config backed off, WARN logging hidden | Check beans, classpath, config, and startup log of the right instance |
| Added SecurityFilterChain but still see password | Replaced web policy only, not default UserDetailsService | Remember the two auto-configuration groups are independent |
| Added UserDetailsService but URLs still require login | User source changed, web policy still protects endpoints | Inspect the active SecurityFilterChain |
| curl gets 401, browser shows login page | HTTP Basic vs form login via content negotiation | Check Accept, entry points, and custom handlers |
| Logged in fine yet `/admin` returns 403 | Missing `ROLE_ADMIN`, or another policy denied access | Check roles/authorities and request matchers |
| GET with valid credentials returns 404 | No matching Controller/mapping | Check path, HTTP method, context path |
| POST with valid credentials returns 403 | Possibly missing CSRF token or missing privilege | Check CSRF and authorization; do not disable blindly |
| Old password stops working after restart | Generated password was regenerated | Read the new log or configure an explicit user source |
| `spring.security.user.password` has no effect | Default user source was replaced by another bean | Check UserDetailsService, Provider, and Manager beans |
| Docker replicas use different passwords | Each instance runs its own user/password generation lifecycle | Use an identity provider or shared identity store |
| Default user accesses `/admin` in Step A | URL name does not enforce ADMIN role automatically | Add a `hasRole` rule matching real requirements |
| Setting `permitAll` on every endpoint to stop errors | Bypassing protection instead of fixing the root cause | Determine whether the issue is authentication or authorization |

### 11.1. Distinguishing Four Response Codes

- **200**: Request authenticated/authorized as needed, and Controller succeeded.
- **401**: Under HTTP Basic, typically missing or invalid credentials when the resource requires authentication.
- **403**: Typically authenticated yet lacking permission, or rejected by a mechanism like CSRF.
- **404**: No matching resource/handler after passing earlier processing steps.

Browsers may return **302** to the login page instead of 401 due to entry point selection. Never rely on a single status code to conclude how auto-configuration works.

## 12. From Learning Setup to a Real Application

Before exposing an application to real users:

1. **Choose a real identity source:** managed database users, LDAP, OIDC/identity provider, or an organization-approved mechanism.
2. **Protect credentials:** hash passwords with a suitable PasswordEncoder, protect secrets and tokens, support password rotation/revocation and MFA when needed.
3. **Design explicit HTTP policies:** public/private/admin, method-specific matchers, deny by default, and appropriate chains.
4. **Enforce data-level permissions:** USER A cannot read or edit USER B's records even though both are logged in.
5. **Configure web protections:** HTTPS, session/cookies, CSRF, CORS, proxy headers, and security headers matching your topology.
6. **Review Actuator:** exposure and access control for operational endpoints.
7. **Monitor and audit:** log relevant events without logging raw passwords, alert on abuse, apply rate limiting, and run security tests.
8. **Pre-deployment checks:** no stray test users/generated passwords, no secrets in logs or source, profiles matched to environment.
9. **Test failure paths:** anonymous, wrong password, locked user, missing role, cross-tenant/cross-owner access, expired token.
10. **Long-term operations:** dependency updates, backups, recovery, rotation, and incident response documentation.

This path moves from a simple learning setup to a system with concrete policies; not every feature appears automatically just from adding `starter-security`.

## 13. Self-Check Questions

**Question 1:** Does creating only a `SecurityFilterChain` remove Boot's default account automatically?  
**Answer:** No. `UserDetailsService` auto-configuration is separate; the default user may still be created.

**Question 2:** Why does Spring Boot print a generated password at startup?  
**Answer:** So developers have a test account to try logging in when starting out; it is not a production credential.

**Question 3:** Is the randomly generated password a JWT secret or database password?  
**Answer:** No. It is the password for the default in-memory user.

**Question 4:** Does the default user automatically have `ROLE_ADMIN` because a URL is named `/admin`?  
**Answer:** No. Without a role policy, the URL may only require authentication; an authorization rule is needed.

**Question 5:** Why might requests still return 401 after a custom `UserDetailsService` is added?  
**Answer:** Web policy can still require login; credentials must match the new user store and filter chain.

**Question 6:** A POST with valid Basic credentials returns 403—should you immediately disable CSRF?  
**Answer:** No. Check the CSRF token, session/cookie behavior, and authorization policy; disabling CSRF is not a general fix.

**Question 7:** An app has three replicas starting independently; should automation use the generated password?  
**Answer:** No. Passwords can differ per replica, there is no centralized user store, and it is unsuitable for operations.

**Question 8:** How do you verify no unintended test user remains before going to production?  
**Answer:** Check dependencies, `UserDetailsService`/`Provider`/`Manager` beans, config profiles, security chains, and startup logs in the actual deployment.

## 14. Official Documentation

- Spring Boot 3.3 — Spring Security, default account, generated password, and back-off rules: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Boot 3.3 — Security how-to: https://docs.spring.io/spring-boot/3.3/how-to/security.html
- Spring Security — Getting Started (Servlet): https://docs.spring.io/spring-security/reference/servlet/getting-started.html
- Spring Security — Servlet Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/index.html
- Spring Security — HTTP Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Boot 3.3 — Externalized configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html

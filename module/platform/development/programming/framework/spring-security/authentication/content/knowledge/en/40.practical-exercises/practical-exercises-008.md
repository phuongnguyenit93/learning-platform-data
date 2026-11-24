# Integrating LDAP or an OIDC Provider in a Lab Environment

> **Module:** Spring Security – authentication. **Group:** Capstone Practical Exercises. This lab presents **two independent options**: A – account authentication via LDAP bind with embedded UnboundID, and B – OpenID Connect (OIDC) login with local Keycloak. You can complete **either one** to achieve the objectives, or complete both to compare them. The stack uses Java 17+, Spring Boot 3.x / Spring Security 6.5 on Servlet MVC. Configuration code must be placed inside a Boot project with a valid Gradle wrapper/parent; the standalone Java 17 program at the end is marked explicitly. Never use the test passwords, users, tokens, or IdP from this guide in production.

## 1. Objectives to Achieve

After completing this practice, you will be able to:

1. Distinguish **LDAP bind** (the app receives username/password and the LDAP server verifies them) from **OIDC login** (the user signs in at the IdP, while the client app handles Authorization Code exchange and ID Token verification).
2. Spin up an in-memory LDAP server with UnboundID and LDIF fixtures, or start a local Keycloak OIDC provider in a container without relying on real corporate accounts.
3. Create a Spring Boot project whose `SecurityFilterChain` activates only under the `ldap-lab` or `oidc-lab` profile.
4. Understand `LdapBindAuthenticationManagerFactory`, `EmbeddedLdapServerContextSourceFactoryBean`, DN, search base, and group/authority mapping.
5. Understand `ClientRegistration`, `issuer-uri`, the `/login/oauth2/code/{registrationId}` callback, `state`, `nonce`, code exchange, ID Token claims, and user sessions.
6. Test both positive and negative flows: wrong password, nonexistent user, LDAP bind error; OIDC redirect mismatch, issuer/client-secret mismatch, claims, and scopes/roles.
7. Distinguish `@WithMockUser` or `oidcLogin()` tests that **pre-populate a principal** from tests that actually exercise the real verifier.
8. Manage TLS, secrets, cookies, CSRF, local-account identity mapping, account disablement/revocation, and authorization correctness.
9. Record verifiable results using `curl -i`, Browser DevTools with redacted tokens, sanitized logs, and test cases.
10. Clean up the environment afterward so no dev IdP, directory fixtures, or credentials remain exposed on the network.

## 2. Two Mechanisms – Never Equate Them

| Criterion | LDAP Bind | OIDC Authorization Code |
|---|---|---|
| Identity verification system | LDAP directory, e.g., OpenLDAP/AD/UnboundID | OIDC Provider / Identity Provider (IdP), e.g., Keycloak |
| Initial credentials | Username and password sent to the app | Browser redirects to IdP where user enters credentials |
| Verification step | Directory checks password via bind | IdP verifies credentials/MFA; client verifies tokens/protocol |
| What app receives post-login | LDAP Authentication/attributes/groups | Verified OIDC principal/ID Token, `(issuer, subject)` |
| Proof of login | Bind success | Code exchange, ID Token signature, `iss`/`aud`/expiry/`nonce` |
| Redirects to external system? | Not required | Yes, per Authorization Code flow |
| App session cookie | Optional after form login | Typically issued after OIDC browser login |
| Source of privileges | LDAP groups / application policy | IdP claims or local authorization policy |
| Common misconfigurations | Wrong DN, LDAP injection, plaintext LDAP, over-privileged service bind | Overbroad redirects, wrong issuer, token confusion, missing state/nonce |
| Real test layer | Real bind/password through LDAP provider | Browser/HTTP redirect to test IdP, code, ID Token verification |

**Hybrid scenario:** many organizations federate Keycloak to LDAP/AD. In that setup, **the Spring app integrates only OIDC**, while Keycloak speaks LDAP behind the scenes. Never describe an OIDC-enabled app as "performing direct LDAP bind" when it uses no LDAP provider at all.

### 2.1. LDAP Bind Does Not Fetch Passwords from LDAP to Compare Locally

With bind authentication, Spring Security creates an LDAP authentication request, resolves the DN, and asks the LDAP server to verify username/password. Never extract a user's `userPassword` into the app to compare manually. Spring Security LDAP provides `LdapAuthenticator`, supporting bind and password comparison as two distinct strategies; this lab uses **bind**, not `UserDetailsService`/`PasswordEncoder.matches` on directory passwords.

### 2.2. ID Tokens Differ from Access Tokens

OIDC layers identity authentication on top of OAuth2. An **ID Token** carries `iss`/`sub`/`aud`/`exp` and login claims; an **Access Token** targets resource APIs with audience/scopes. Even though both may look like JWTs, **never** accept an arbitrary Access Token as proof of user login, and never treat an ID Token as a general API access token.

## 3. Lab Architecture

### 3.1. LDAP

```text
Browser or curl -u user:password
          |
          v
Spring Security FilterChain
          |
  BasicAuthenticationFilter or
  UsernamePasswordAuthenticationFilter
          |
          v
AuthenticationManager from
LdapBindAuthenticationManagerFactory
          |
          | LDAP bind using resolved DN
          v
UnboundID embedded LDAP (JVM)
          |
     success / failed credentials
          |
          v
SecurityContext / Authentication
          |
  Authenticated with permission? -> /whoami
```

### 3.2. OIDC

```text
Browser               Spring Boot client                  Keycloak IdP
   | GET /whoami              |                                  |
   |------------------------->|                                  |
   | 302 login / start OIDC   |                                  |
   |<-------------------------|                                  |
   | GET /oauth2/authorization/keycloak                          |
   |------------------------->|                                  |
   |           state, nonce, redirect_uri, client_id             |
   |<-------------------------|                                  |
   |----------------------------------------------------------->|
   |           User enters credentials on IdP page               |
   |<--------------------------------- 302 callback code+state   |
   | GET /login/oauth2/code/keycloak?code=...&state=...          |
   |------------------------->|                                  |
   |                          | POST /token + client auth       |
   |                          |--------------------------------->|
   |                          |<---------------------------------|
   |                          | ID Token & verify               |
   |  Session cookie, redirect|                                  |
   |<-------------------------|                                  |
   | GET /whoami with cookie  |                                  |
   |------------------------->|                                  |
   |                    200 principal name                       |
```

**Never** expose `client_secret` to the browser; confidential-client token exchanges execute from the backend. Callback `code` and `state` values are sensitive; never paste URLs containing codes into public reports.

## 4. Prerequisites and Safety Boundaries

You need JDK 17+, a Gradle/Maven Spring Boot project, an IDE, terminal/`curl`, a browser, and Docker/Podman if choosing OIDC. Two local ports are used: `8080` for the application and `8180` for Keycloak. Embedded LDAP requires **no Docker**.

- Use only test users, passwords, and realms; never connect to production AD/domains or IdPs.
- Bind the Keycloak container to `127.0.0.1`; never publish it to the Internet.
- HTTP on localhost is a **lab-only** exception; real apps must use HTTPS and LDAP over LDAPS/StartTLS.
- Pin dependencies/versions to a **compatible BOM** rather than forcing Spring Security 7 into Boot 3 just to copy samples.
- You may run one branch at a time; both configs use `@Profile` so neither boots both flows nor fights over `SecurityFilterChain`.
- Never disable CSRF, issuer validation, or TLS certificate validation just to "make the demo work".
- Use private browser sessions for repeated tests so old login sessions do not mask authentication failures.
- Never log `Authorization` headers, Basic passwords, LDAP manager passwords, OAuth codes, ID/access tokens, or cookies.

## 5. Sample Project Structure

```text
security-integration-lab/
├── build.gradle
├── settings.gradle
├── gradlew / gradlew.bat
└── src/
    ├── main/
    │   ├── java/lab/security/
    │   │   ├── SecurityLabApplication.java
    │   │   ├── WhoAmIController.java
    │   │   ├── LdapLabSecurity.java
    │   │   └── OidcLabSecurity.java
    │   └── resources/
    │       ├── application.yml
    │       ├── application-oidc-lab.yml
    │       └── users.ldif
    └── test/java/lab/security/
        └── LdapAuthenticationTests.java
```

Initialize the project with the Spring Boot plugin/repositories/Gradle Wrapper and JDK 17. If using Spring Initializr, stay on the same Spring Boot 3.x line; [Spring Security LDAP 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html) is the basis for the LDAP classes below.

### 5.1. Dependencies

Excerpt of `dependencies` in Gradle Groovy DSL – **not a complete `build.gradle`**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    // LDAP lab
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    implementation 'org.springframework.security:spring-security-ldap'
    runtimeOnly 'com.unboundid:unboundid-ldapsdk:6.0.11'

    // OIDC lab
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Tests
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

UnboundID `6.0.11` is the version illustrated in the Spring Security 6.5 Reference; always verify version compatibility and security advisories for real usage. You do not need `spring-boot-starter-oauth2-resource-server` for **OIDC browser login**; add it only if the app also validates Bearer Access Tokens on REST APIs.

### 5.2. Shared application.yml

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

logging:
  level:
    root: INFO
```

Do not enable full HTTP request/response debug logging automatically because OIDC callback `code` values, session cookies, and credentials can leak into logs.

### 5.3. Main Class

`src/main/java/lab/security/SecurityLabApplication.java`:

```java
package lab.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityLabApplication.class, args);
    }
}
```

### 5.4. Shared Controller for Both Profiles

`src/main/java/lab/security/WhoAmIController.java`:

```java
package lab.security;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/")
    public String home() {
        return "Security lab: open /whoami after logging in";
    }

    @GetMapping("/whoami")
    public Map<String, String> whoAmI(Authentication auth) {
        return Map.of("name", auth.getName());
    }
}
```

The controller **does not verify** identity; it simply consumes `Authentication` from Spring Security. Under LDAP, the name may be `student`; under OIDC, `name` is often a `sub`/principal claim per mapping, not guaranteed to equal `preferred_username` or email.

## 6. Option A – Embedded LDAP with UnboundID

### 6.1. Directory Concepts

- **Distinguished Name (DN):** full entry path, e.g., `uid=student,ou=people,dc=springframework,dc=org`.
- **Base DN:** search root `dc=springframework,dc=org`.
- **Organizational Unit (OU):** tree container; `ou=people` holds the demo users.
- **uid:** login attribute in the lab; Microsoft AD also uses `sAMAccountName` and `userPrincipalName`, which are not automatically identical.
- **Bind:** the LDAP server verifies credentials.
- **Search filter:** locates a user DN across multiple OUs; requires proper escaping and search permissions.
- **Groups/roles:** LDAP membership **does not automatically become `ROLE_ADMIN`**; the app must map authorities per policy.

### 6.2. Creating users.ldif Data

File `src/main/resources/users.ldif`:

```ldif
dn: ou=people,dc=springframework,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=student,ou=people,dc=springframework,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Lab Student
sn: Student
uid: student
userPassword: lab-password-123

dn: uid=reader,ou=people,dc=springframework,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Lab Reader
sn: Reader
uid: reader
userPassword: reader-password-123
```

These are plaintext password fixtures **strictly for booting a local in-memory server**. Never put these credentials into a shared directory or production. In the lab, the embedded server manages the default root entry; do not duplicate the root entry if the implementation already creates it.

### 6.3. Configuring LDAP and Form/Basic Login

File `src/main/java/lab/security/LdapLabSecurity.java`:

```java
package lab.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.ldap.EmbeddedLdapServerContextSourceFactoryBean;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@Profile("ldap-lab")
public class LdapLabSecurity {

    @Bean
    EmbeddedLdapServerContextSourceFactoryBean embeddedLdap() {
        EmbeddedLdapServerContextSourceFactoryBean factory =
            EmbeddedLdapServerContextSourceFactoryBean
                .fromEmbeddedLdapServer();
        factory.setPort(0);
        factory.setRoot("dc=springframework,dc=org");
        factory.setLdif("classpath:users.ldif");
        return factory;
    }

    @Bean
    AuthenticationManager ldapManager(
            DefaultSpringSecurityContextSource source) {
        LdapBindAuthenticationManagerFactory factory =
            new LdapBindAuthenticationManagerFactory(source);
        factory.setUserDnPatterns("uid={0},ou=people");
        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain ldapChain(
            HttpSecurity http,
            AuthenticationManager ldapManager) throws Exception {
        http
            .authenticationManager(ldapManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

**Explanation:**

1. `@Profile("ldap-lab")` activates these beans only when this branch is selected.
2. `EmbeddedLdapServerContextSourceFactoryBean` boots an LDAP server from LDIF; `setPort(0)` picks a dynamic port to avoid test collisions.
3. `setRoot`/`setLdif` are verified methods in the Spring Security 6.5 Javadoc.
4. `LdapBindAuthenticationManagerFactory` creates an `AuthenticationManager` verifying username/password via **LDAP bind**, not local password hashes.
5. `userDnPatterns("uid={0},ou=people")` appends to the `ContextSource` root to form the expected DN.
6. `http.authenticationManager(ldapManager)` ensures HTTP authentication filters in this chain use the LDAP manager rather than an unrelated provider.
7. `/` is public; `/whoami` requires authentication. `formLogin` serves browsers, and `httpBasic` serves `curl`/tests.
8. **Never** disable CSRF on form login or mark `/admin` as `permitAll`.

This code **integrates into a Spring Boot project** and will not compile standalone with `javac`. Depending on the Spring Security patch version and bean wiring, you may use the `BaseLdapPathContextSource` interface instead of `DefaultSpringSecurityContextSource` in constructor/bean injection. Check your exact dependency version's Javadoc if the IDE flags a type/method mismatch.

### 6.4. Running the LDAP Lab

With the Gradle Wrapper:

```bash
./gradlew bootRun --args='--spring.profiles.active=ldap-lab'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=ldap-lab"
```

Do not enable `oidc-lab` in the same process. If LDAP startup fails to load LDIF, verify `src/main/resources/users.ldif` on the classpath, DN/root/blank-line formatting, and the `unboundid-ldapsdk` dependency.

### 6.5. Testing with curl

```bash
# Public
curl -i http://localhost:8080/

# Valid LDAP bind; local lab only
curl -i -H 'Accept: application/json' \
  -u student:lab-password-123 http://localhost:8080/whoami

# Wrong password
curl -i -H 'Accept: application/json' \
  -u student:wrong http://localhost:8080/whoami

# Nonexistent user
curl -i -H 'Accept: application/json' \
  -u ghost:whatever http://localhost:8080/whoami
```

Expected: public 200; valid credentials 200 with JSON principal; wrong password and unknown username are not authenticated, typically HTTP 401 + Basic challenge. Because both form and Basic are enabled, **browser 302 redirect vs. Basic 401 challenge depends on request negotiation**; test Basic with `Accept: application/json` as above.

Never pass real passwords on the command line: many OSes record shell history or expose command arguments in process lists. Run these commands strictly with synthetic accounts in an isolated test environment.

### 6.6. LDAP User Search Instead of DN Patterns

When users span multiple OUs, use user search:

```java
factory.setUserSearchBase("ou=people");
factory.setUserSearchFilter("(uid={0})");
```

In real LDAP, verify search permissions, schema, and input escaping. **Never** build raw filters like `"(uid=" + userInput + ")"`, which invite LDAP injection. When directories involve AD/LDAP referrals, nested groups, or account restrictions, test against real directory behavior and policies.

### 6.7. Group/Role Mapping

A successful bind **does not** mean the user holds `ROLE_ADMIN`. LDAP group memberships may live in `member`, `uniqueMember`, `memberOf`, or nested group queries. Authority mapping must be explicit:

```text
LDAP group: cn=readers,ou=groups,dc=example,dc=org
        |
        | trusted mapper (group lookup / cache policy)
        v
GrantedAuthority("ROLE_READER")
        |
        v
AuthorizationManager.hasRole("READER")
```

Before adding mapping, `/whoami` only checks `authenticated()`. If you add `hasRole("ADMIN")` without mapping authorities, HTTP 403 means **authenticated yet unauthorized**, not a failed bind. Never "fix" it by assigning `ROLE_ADMIN` to every principal.

### 6.8. LDAP over TLS in Production

For external LDAP/AD, app→directory connections must use LDAPS/StartTLS with CA/hostname verification and timeouts. If a manager DN is needed to search users, grant that account read-only least privilege and store its secret in a vault. Browser→Spring must also use HTTPS; backend LDAPS offers little password protection if frontend forms travel over public HTTP.

## 7. Automated LDAP Tests Through Real Filters

File `src/test/java/lab/security/LdapAuthenticationTests.java`:

```java
package lab.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@ActiveProfiles("ldap-lab")
@AutoConfigureMockMvc(addFilters = true)
class LdapAuthenticationTests {

    @Autowired MockMvc mvc;

    @Test
    void correctPasswordUsesRealBind() throws Exception {
        mvc.perform(get("/whoami")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("student", "lab-password-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("student"));
    }

    @Test
    void wrongPasswordFailsBind() throws Exception {
        mvc.perform(get("/whoami")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("student", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUserFailsBind() throws Exception {
        mvc.perform(get("/whoami")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("ghost", "whatever")))
            .andExpect(status().isUnauthorized());
    }
}
```

Run:

```bash
./gradlew test --tests lab.security.LdapAuthenticationTests
```

**What passing tests prove:** the HTTP Basic filter parses credentials, `AuthenticationManager` delegates to LDAP bind, and the embedded server accepts/rejects per fixture. **What they do not prove:** LDAPS certificates, AD lockout/expired accounts, network failover, corporate group mapping, or production identity proofing.

### 7.1. Mock Principals Are Not Equivalent to Bind

```java
// Snippet in a MockMvc test with static import user().
mvc.perform(get("/whoami")
        .with(user("ghost").roles("USER")))
    .andExpect(status().isOk());
```

This passes with principal `ghost` even though the directory **contains no user `ghost`**. `user()` is a `RequestPostProcessor` injecting a mock `Authentication` for authorization testing. Never use it to claim "LDAP password login works". Test real credentials with `httpBasic` or `formLogin` and never mock the verifier to always succeed.

### 7.2. Negative LDAP Cases to Expand

| Input / Event | Expected Result |
|---|---|
| Wrong / empty password | Not authenticated |
| Nonexistent user | Not authenticated, neutral response |
| Valid password yet user disabled per AD policy | Login rejected (requires directory test simulating real flags) |
| User in regular group hitting admin route | 403 per role mapping |
| Directory unreachable | Fails closed, grants no new session |
| DN pattern mismatch | Fails bind or search properly |
| Username with LDAP metacharacters | Escaped/validated, no filter injection |
| Wrong / over-privileged manager DN | Never silently falls back to admin |
| Plaintext LDAP connection on real network | Blocked by policy, secrets never sent |
| LDAP search returns multiple users | Never arbitrarily picks the first identity |
| Password rotated in directory | Old credential cannot log in; old session follows policy |
| Successful auth then logout | Session invalidated per application policy |
| Two requests in separate sessions | Never reuses `Authentication` from earlier test |
| Directory timeout | Redacted operational error log, never disguised as "wrong password" |

## 8. Option B – Keycloak as a Local OpenID Provider

### 8.1. Where Does Keycloak Sit in the Architecture?

Keycloak is the IdP / Authorization Server. The Spring Boot app is an OAuth2 Client using `oauth2Login()` and browser redirects. In OIDC, **the user enters their password at Keycloak**, never sending Keycloak credentials to a Spring controller. Spring validates the token response/trusted metadata and creates an `OidcUser` and session.

You can use any compliant OpenID Provider, though Keycloak offers a convenient Docker image and Admin Console for the lab. Use a dedicated realm, dedicated client, and dedicated users—never reuse corporate credentials.

### 8.2. Running Keycloak with Docker

Example from Keycloak Docker Getting Started: image `quay.io/keycloak/keycloak:26.8.1` was published in docs at the time of writing. To avoid colliding with the Spring app's port `8080`, map Keycloak onto `localhost:8180`:

```bash
docker run --rm --name keycloak-lab \
  -p 127.0.0.1:8180:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=lab-admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=lab-admin-only \
  quay.io/keycloak/keycloak:26.8.1 \
  start-dev --hostname=http://localhost:8180
```

**Details:** `start-dev` allows HTTP and uses dev-only security defaults; bind strictly to loopback and never deploy to production. `--hostname` sets the public URL so `issuer` and endpoints advertised by Keycloak match browser/backend URLs. If your Docker/Podman setup or Keycloak version handles hostnames differently, consult that version's docs and verify live discovery. Avoid `:latest` when reproducibility matters.

Open `http://localhost:8180` and choose Admin Console; log in as `lab-admin` with the test password. The container runs in the foreground: stop with Ctrl+C or `docker stop keycloak-lab`; `--rm` removes the container on exit, so test realms do not persist unless you configure volumes/exports.

### 8.3. Creating the Realm and User

In the Admin Console:

1. Create a realm named `spring-lab`; never use the `master` realm for applications.
2. Under Users, create `student-oidc` with test email `student@lab.example`.
3. Set a password under Credentials; toggle **Temporary OFF** for single-step login in the lab.
4. Ensure the user is **Enabled** with no pending required actions (unless testing that scenario).
5. Never use the Keycloak admin account as a Spring app user.
6. Document test user config in local notes without secrets.

Issuer:

```text
http://localhost:8180/realms/spring-lab
```

Metadata:

```bash
curl -i http://localhost:8180/realms/spring-lab/.well-known/openid-configuration
```

Verify that `issuer` in the JSON matches the URL above **verbatim**; inspect `authorization_endpoint`, `token_endpoint`, and `jwks_uri` from discovery. A 404 means the realm wasn't created, hostname/port is wrong, or Keycloak isn't ready yet.

### 8.4. Registering the OIDC Client

In realm `spring-lab` → Clients → Create client, configure:

| Property | Lab Value | Purpose |
|---|---|---|
| Client type | OpenID Connect | Enables OIDC ID Token |
| Client ID | `spring-lab-client` | Matches Spring registration |
| Client authentication | **ON** | Confidential web client with secret |
| Standard flow | **ON** | Authorization Code |
| Direct access grants | **OFF** unless needed | Disables password grant |
| Valid redirect URIs | `http://localhost:8080/login/oauth2/code/keycloak` | Matches Spring callback |
| Web origins | `http://localhost:8080` if needed | Avoid wildcards |
| Client secret | Copy from Credentials | Store via environment/secret store |

**Important:** redirect URI must be the exact callback—never use a wildcard like `http://localhost:8080/*` just to bypass errors. When Client authentication is ON, confidential clients authenticate at the token endpoint with the secret; Spring's auth method must match Keycloak's client policy.

### 8.5. Keeping the Secret Out of Source Code

Set the `OIDC_CLIENT_SECRET` environment variable from your local secret manager or IDE config. Bash lab example:

```bash
export OIDC_CLIENT_SECRET='YOUR_LOCAL_TEST_CLIENT_SECRET'
```

PowerShell:

```powershell
$env:OIDC_CLIENT_SECRET = "YOUR_LOCAL_TEST_CLIENT_SECRET"
```

This is strictly a placeholder for the **test secret** issued by Keycloak. Never commit real values, screenshot client credentials, or print tokens/secrets into CI logs. Rotate immediately if exposed.

### 8.6. Spring Boot OIDC Client Properties

File `src/main/resources/application-oidc-lab.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          keycloak:
            provider: keycloak
            client-id: spring-lab-client
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          keycloak:
            issuer-uri: http://localhost:8180/realms/spring-lab
```

**Explanation:**

- `registration.keycloak` is the registration ID, so the default login-initiation URL is `/oauth2/authorization/keycloak`.
- `client-id` matches the client registered in Keycloak.
- `client-secret` comes from the environment, never hardcoded in YAML.
- `openid` requests OpenID Connect; `profile,email` are optional scopes.
- `redirect-uri` uses placeholders supported by Spring OAuth2 Client; when Spring runs on `localhost:8080`, the callback becomes `http://localhost:8080/login/oauth2/code/keycloak`.
- `issuer-uri` enables discovery and anchors issuer, endpoint, and JWK verification; **never** mix `http://127.0.0.1:8180` and `http://localhost:8180` if advertised metadata differs.
- This configuration is for a **server-side confidential web client**, not a public SPA client.

### 8.7. SecurityFilterChain for the OIDC Profile

File `src/main/java/lab/security/OidcLabSecurity.java`:

```java
package lab.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@Profile("oidc-lab")
public class OidcLabSecurity {

    @Bean
    SecurityFilterChain oidcChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

`oauth2Login` enables the client filters and protocol flow. Callback requests are handled automatically by Spring Security's filter; **never write `@GetMapping("/login/oauth2/code/keycloak")` yourself**. The config preserves CSRF for browser sessions. Spring Boot auto-configures `ClientRegistrationRepository` from properties when the OAuth2 Client starter is present.

### 8.8. Running and Verifying in the Browser

Once Keycloak is running and the realm/client/secret are ready:

```bash
./gradlew bootRun --args='--spring.profiles.active=oidc-lab'
```

Steps:

1. Open `http://localhost:8080/` in the browser and see the public response.
2. Open `http://localhost:8080/whoami` while unauthenticated.
3. Spring redirects to the login page or directly to OAuth2 authorization; click "Keycloak" (or visit `http://localhost:8080/oauth2/authorization/keycloak` directly).
4. The browser redirects to Keycloak's `spring-lab` realm; sign in as `student-oidc` at the IdP.
5. Keycloak returns the authorization `code` and `state` to the app's callback.
6. Spring verifies `state`, exchanges `code` at the token endpoint using client auth, and validates the ID Token.
7. Spring stores the authenticated principal in the session; revisiting `/whoami` returns 200 with the OIDC principal's `name`.

**Do not assume `getName()` equals `student-oidc`.** Many OIDC setups use the stable `sub` claim as the principal name. What matters is verifying the user by `(iss, sub)` and mapping privileges from trusted sources—not comparing display names.

### 8.9. Host/Container Networking Issues

`localhost` inside a Docker container **points only to that container**. If the Spring app also runs inside another container, `localhost:8180` cannot reach Keycloak, while the browser still needs to reach the endpoints Keycloak advertises. Solve this with a **canonical hostname/issuer** resolvable by both browsers and the app JVM, paired with proper networking/DNS/ingress and TLS—never disable issuer verification to work around DNS/hostname mismatches.

## 9. OIDC Protocol: Checks You Must Never Skip

### 9.1. Authorization Code and Client Authentication

The Authorization Code arrives via redirect to the exact `redirect_uri`. Confidential clients send the code to the token endpoint over the **back-channel** and authenticate using their secret or configured method. Codes must be short-lived, single-use, and bound to client + redirect/PKCE per policy.

**Never** grab the code from the callback and send it to an IdP chosen by the browser, and never ship client secrets to frontend JavaScript.

### 9.2. state and nonce

- `state` is used by the OAuth2 client to bind the authorization request to the callback, mitigating login CSRF and code injection.
- `nonce` binds the ID Token to the OIDC flow and must be verified per protocol/implementation.
- Test that two browser sessions A/B cannot swap `state`/`code` to log into each other's session.
- Test that a consumed authorization code cannot be replayed to obtain a new session.
- Never hardcode a static `state=123` in production or disable state checking to make tests pass.

### 9.3. ID Token Validation

A trusted ID Token must be processed/verified for:

| Field / Condition | Purpose | Negative Test |
|---|---|---|
| Signature + JWK/JWKS | Matches trusted issuer keys and algorithm | Swap signature/key from another realm |
| `iss` | Configured IdP issuer | Token from another realm |
| `aud` | Matching Client ID | Token issued to a different client |
| `azp` when applicable | Authorized party per OIDC rules | Multiple audiences with wrong `azp` |
| `exp`/`iat` | Expiration and time validity | Expired token / far-future `iat` |
| `nonce` | Binds to browser flow | Wrong or replayed nonce |
| `sub` | Stable principal ID within issuer | Missing or invalid |
| Token type/use | Never accept an Access Token as an ID Token | Swap token types |
| `email_verified` | Did the IdP verify the email? | Never link local accounts by unverified email |

Spring Security and its OIDC client library handle core protocol checks, yet **tests must use proper client config and issuers**. A unit test constructing a mock `OidcUser` proves nothing about ID Token verification.

### 9.4. PKCE, Confidential Clients, and Redirects

PKCE protects Authorization Codes against interception. For public clients, PKCE is essential for secure OAuth; for confidential server-side clients, whether PKCE is enabled depends on `ClientRegistration`/framework/IdP policy—**do not claim it is "always enabled" without checking**.

Redirect URIs must be **exact**, never broad wildcards. Apps must never reflect `next=https://evil.example` blindly after login. Behind reverse proxies, base URLs and forwarded headers must be trusted to avoid redirecting to foreign hosts or dropping session cookies.

## 10. Source of Truth for Identity and Authorities

### 10.1. LDAP Identity

Directory namespace + stable entry ID/DN (and managed identity attributes) identify accounts. In AD, `objectGUID` is often safer than `displayName` or a mutable `sAMAccountName`. When linking LDAP users to domain accounts, account for renames, OU moves, and account reuse—never rely solely on display names.

### 10.2. OIDC Identity

OIDC identifies users by the **`(iss, sub)` pair**. `email` and `preferred_username` can change, collide, or be unverified. Simulated ID Token claims:

```json
{
  "iss": "http://localhost:8180/realms/spring-lab",
  "sub": "subject-123",
  "aud": "spring-lab-client",
  "preferred_username": "student-oidc",
  "email": "student@lab.example",
  "email_verified": false
}
```

This is **illustrative JSON**, not a real Keycloak token or verified signature. Apps must never auto-link an existing local account solely by `email` when `email_verified=false`. Beyond verified email, some systems also require **local account** reauthentication before linking an IdP for the first time.

### 10.3. Independent Authorization

A user who passes LDAP bind or OIDC login **may still lack permission** to view `/admin` or another tenant's data. Both branches need trusted authority mapping:

- LDAP: group search/membership, nested groups, allowlisted policies, `ROLE_` prefix.
- OIDC: verified token claims/realm roles/client roles, or a local role repository.
- Domain: object ownership, tenant boundaries, disabled accounts, permission freshness, and revocation.
- Tests: low role → 403; sufficient role yet wrong owner → 403/404 per policy.

**Never assume every Keycloak realm role appears automatically as `ROLE_ADMIN` in Spring Security.** Build and test your own mapper. Likewise, never grant `ROLE_ADMIN` to all LDAP users simply because they belong to some group.

## 11. Testing: Mock Fixtures vs. Real Verifiers

| Test | What It Verifies | What Remains Unproven |
|---|---|---|
| `@WithMockUser(username="student")` | Authorization/controller with mock `Authentication` | That LDAP user exists or password works |
| `user("ghost")` in MockMvc | Endpoint behavior for a given principal | That LDAP bind happened |
| `@WithUserDetails` | `UserDetailsService` lookup and bean mapping | That `PasswordEncoder`/LDAP bind ran |
| `oidcLogin()` in MockMvc | Controller handling of pre-built `OidcUser`/claims | Keycloak redirect, code, signature, issuer, nonce |
| `httpBasic("student","password")` + real LDAP manager | HTTP filter → real lab LDAP bind | Production AD/TLS/failover |
| Browser OIDC login with test Keycloak | Redirect, client auth, code exchange, ID Token check, session | All multi-node/production IdP failure modes |
| Unit test custom mapper | Role/tenant policy on mock claims/LDAP attrs | That claims/tokens came from a trusted source |
| E2E + negative crypto tests | Stronger protocol/verification evidence | Threat modeling and operational monitoring |

**Rule of thumb:** if a test still passes with both LDAP and Keycloak turned off and no fake server running, it is likely testing a mock principal only. That is fine for authorization tests, **never** call it a real login test.

### 11.1. Proper Role of MockMvc oidcLogin()

Spring Security Test snippet:

```java
mvc.perform(get("/whoami").with(oidcLogin()))
    .andExpect(status().isOk());
```

This does not call Keycloak's authorization endpoint or ID Token verifier. Mock claims can be supplied:

```java
mvc.perform(get("/whoami")
        .with(oidcLogin().idToken(token ->
            token.claim("sub", "student-test-subject"))))
    .andExpect(status().isOk());
```

Requires static imports `oidcLogin`, `get`, `status`, and a Spring MVC test context. Never use that snippet to claim your app validates JWT signatures or `state`.

### 11.2. LDAP MockMvc Tests vs. Browser OIDC E2E

In the LDAP branch, `httpBasic` travels through the filter and executes bind inside the same JVM. In the OIDC branch, a real callback requires a browser + IdP + client secret + token endpoint + JWKs. You can use browser automation/Testcontainers/WireMock with test issuer/JWKS/signing keys, yet a mocked `oidcLogin()` **never replaces** E2E.

When using a fake OIDC provider, prove the server issues **checked codes**, real signed tokens, and Spring's decoder actually verifies them—never mock `OidcIdTokenDecoderFactory` to succeed for any string and call it a crypto test.

## 12. Integration Test Matrix

### 12.1. LDAP

| Test | Setup | Expected |
|---|---|---|
| Valid bind | User `student`, right password | 200 `/whoami`, matching name |
| Wrong password | Same user, wrong password | 401 / form failure branch |
| Nonexistent user | Ghost DN | 401, no `Authentication` created |
| Missing credentials | New client/browser | 302 login or Basic 401 per `Accept` |
| Different search base | User in another OU | Fails bind if pattern/search is wrong |
| LDAP filter injection | Username with wildcards/metacharacters | Escaped or rejected per policy |
| LDAP server down | Service unreachable | No new session granted |
| Read-only manager DN | Search-before-bind | Does not read beyond necessary scope |
| Missing LDAP group | Valid bind yet lacks group | 403 on protected role |
| Disabled account | Test directory supports flag | Blocked when policy requires |
| Rotated password | Old password | Cannot open new login |
| Session logout | Logged-in browser | Old session loses resource access |
| Invalid TLS CA | External LDAPS test | Connection rejected; never trust-all |
| Multi-node directory | Replica failover | Never fails open |

### 12.2. OIDC

| Test | Setup | Expected |
|---|---|---|
| Valid login | Matching Keycloak realm/client/user | App session and principal created |
| Wrong redirect | Keycloak Valid redirect URI differs from app | IdP rejects |
| Wrong client secret | Env secret mismatches Keycloak | Token exchange fails |
| Wrong issuer | `127.0.0.1` vs. `localhost` or other realm | Rejects token/metadata |
| Wrong `state` | Callback alters `state` | No session created |
| Code replay | Reuse code | Rejected |
| `nonce` mismatch | ID Token `nonce` mismatches flow | Rejected |
| Bad ID Token signature | Signed fixture with wrong key | Rejected |
| Wrong `aud` in ID Token | Token issued for another client | Rejected |
| Expired ID Token | Past `exp` | Rejected |
| User disabled at IdP | Keycloak user disabled | No new login |
| Unverified email | `email_verified=false` | Never auto-links local account |
| Unmapped realm role | Regular user logs in | 403 on admin route |
| Session logout | App logout | Local session invalidated |
| Separate IdP logout | IdP SSO remains active | Never assume local logout = IdP logout |
| JWKS rotation | IdP rotates signing key | Client trusts new JWK per policy |
| IdP outage | No discovery/token response | Fails closed |
| Wrong proxy hostname | Redirect base URL mismatch | Fix canonical origin, never disable checks |

## 13. Standalone Java 17: Evidence Trust Boundaries

This program **runs on JDK 17+ with zero libraries**, modeling two **post-verifier outcomes**. It DOES NOT execute LDAP binds, sign/verify JWTs, or call an IdP. Flags `bindVerified`, `signatureVerified`, and `nonceVerified` are **test-supplied mock data**—never accept them from client JSON or headers in real apps.

Save `IdentityTrustBoundaryDemo.java`:

```java
import java.time.Instant;

public class IdentityTrustBoundaryDemo {

    record LdapEvidence(
        String directory, String dn,
        boolean bindVerified) {}

    record OidcEvidence(
        String issuer, String subject, String audience,
        boolean signatureVerified, boolean nonceVerified,
        Instant expiresAt) {}

    static boolean acceptLdap(LdapEvidence proof) {
        return proof.bindVerified()
            && proof.directory().equals("lab-directory")
            && proof.dn().equals(
                "uid=student,ou=people,dc=springframework,dc=org");
    }

    static boolean acceptOidc(OidcEvidence proof, Instant now) {
        return proof.signatureVerified()
            && proof.nonceVerified()
            && proof.issuer().equals(
                "http://localhost:8180/realms/spring-lab")
            && proof.audience().equals("spring-lab-client")
            && !proof.subject().isBlank()
            && now.isBefore(proof.expiresAt());
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T09:00:00Z");

        LdapEvidence verifiedBind = new LdapEvidence(
            "lab-directory",
            "uid=student,ou=people,dc=springframework,dc=org", true);
        LdapEvidence falseBind = new LdapEvidence(
            "lab-directory",
            "uid=student,ou=people,dc=springframework,dc=org", false);

        OidcEvidence good = new OidcEvidence(
            "http://localhost:8180/realms/spring-lab",
            "subject-123", "spring-lab-client", true, true,
            now.plusSeconds(120));
        OidcEvidence wrongIssuer = new OidcEvidence(
            "http://localhost:8180/realms/other",
            "subject-123", "spring-lab-client", true, true,
            now.plusSeconds(120));
        OidcEvidence wrongSignature = new OidcEvidence(
            "http://localhost:8180/realms/spring-lab",
            "subject-123", "spring-lab-client", false, true,
            now.plusSeconds(120));
        OidcEvidence expired = new OidcEvidence(
            "http://localhost:8180/realms/spring-lab",
            "subject-123", "spring-lab-client", true, true, now);

        System.out.println("LDAP verified bind: " +
            acceptLdap(verifiedBind));
        System.out.println("LDAP invalid bind: " +
            acceptLdap(falseBind));
        System.out.println("OIDC valid proof: " +
            acceptOidc(good, now));
        System.out.println("OIDC wrong issuer: " +
            acceptOidc(wrongIssuer, now));
        System.out.println("OIDC bad signature: " +
            acceptOidc(wrongSignature, now));
        System.out.println("OIDC expired: " +
            acceptOidc(expired, now));
        System.out.println("Different namespaces: " +
            !verifiedBind.dn().equals(good.subject()));
    }
}
```

Compile and run:

```bash
javac IdentityTrustBoundaryDemo.java
java IdentityTrustBoundaryDemo
```

**Exact** stdout:

```text
LDAP verified bind: true
LDAP invalid bind: false
OIDC valid proof: true
OIDC wrong issuer: false
OIDC bad signature: false
OIDC expired: false
Different namespaces: true
```

**Takeaway:** having the same display username `student` is no proof of login if LDAP bind failed; OIDC requires issuer, audience, signature, nonce, and expiry. Missing any single condition must reject. The demo also highlights that an LDAP DN belongs to a directory namespace and an OIDC subject belongs to an issuer namespace—never merge accounts based on a username string.

**Limitations:** this model checks booleans from an assumed trusted verifier; it omits `state`, JWT JWK algorithms, `azp`, token endpoint/client authentication, clock-skew policy, issuer discovery, signature verification, and browser sessions. Never copy `acceptOidc` into production to replace Spring Security's OIDC verifier. Real tests must run through the LDAP/OIDC integrations above.

## 14. Symptom-Based Debugging

### 14.1. LDAP Bind Fails Even Though Password Looks Right

1. Verify `ldap-lab` is active; did `LdapLabSecurity` load?
2. Is the LDIF actually on the classpath and initialized cleanly? Any init errors in logs?
3. Does the user's DN match `uid=student,ou=people,dc=springframework,dc=org`?
4. Does the user-DN pattern append cleanly to the root without duplicating suffixes?
5. Was another `AuthenticationManager` or test mock provider registered accidentally?
6. Is the browser caching stale Basic credentials from an earlier session? Use a fresh `curl` or private browser.
7. For external LDAP, check DNS/LDAPS certs/connect/read timeouts before blaming the password.
8. Never add `permitAll("/whoami")` to hide an authentication error.

### 14.2. Valid LDAP User Yet Missing Permissions

Once mapping is added, inspect `DefaultLdapAuthoritiesPopulator`/group search config, actual `member`/`memberOf` schema, nested groups, `ROLE_` prefix, service bind permissions, and caches. Never assume `ROLE_ADMIN` exists just because the directory has a differently named "admin" group.

### 14.3. OIDC "invalid_redirect_uri"

Spring callback:

```text
http://localhost:8080/login/oauth2/code/keycloak
```

The Keycloak client must register the exact URI, including scheme, host, port, and path. `localhost` differs from `127.0.0.1` in exact URI matching. Never use wildcards to paper over misconfigurations.

### 14.4. OIDC "invalid issuer"

Inspect discovery metadata's `issuer`; compare verbatim with `provider.keycloak.issuer-uri`. Behind reverse proxies/port mappings, configure the canonical public hostname properly. Never drop issuer checks in favor of "signature-only JWT checks", or tokens from other realms may be trusted mistakenly.

### 14.5. OIDC "invalid_client"

Check the registration/client ID in the right realm, Client authentication ON, secret copied from the right client, `client_secret_basic`, token endpoint metadata, and secret rotation. Never put secrets into frontends or logs.

### 14.6. OIDC Browser Login Finishes Yet User Remains Anonymous

Inspect callback `state`, cookie domain/path/`SameSite`/`Secure`, HTTP vs. HTTPS, session persistence/repository, reverse proxy forwarding, and session fixation strategy. When Spring and the IdP share a host on different ports, cookie domain/path and `SameSite` interact depending on context; never disable protections.

### 14.7. API Returns 403 After Login

Successful authentication does not grant business authorities. Inspect method security, roles/scopes/tenant/ownership rules; never disable JWT/ID Token signature validation to "fix 403". If the app also exposes a Bearer resource server, isolate the API filter chain from browser OAuth2 login.

## 15. Moving from Lab to Production

**LDAP:** enforce end-to-end LDAPS/StartTLS, trusted CAs, read-only service binds, DN/filter escaping, rate limiting, account lockouts, directory replicas/referrals, group mapping, auditing, and proper account disablement. Use an external LDAP server and appropriate session/cache configs rather than embedded in-memory servers.

**OIDC:** use a managed production IdP, HTTPS, exact redirect URIs, trusted issuer/JWKS, vaulted/rotated client secrets, `state`/`nonce`, single-use authorization codes/PKCE policy, session fixation/CSRF, app logout vs. IdP logout, signed claims, account linking via `iss+sub`, role mapping, and assurance/MFA requirements. Never trust unverified emails or browser-supplied roles.

**Both:** authentication and authorization are separate layers. Never treat 200 from a public endpoint as successful login; never use `@WithMockUser`/`oidcLogin()` as proof of real password/cryptographic verification. Test negative cases, keep redacted reports, collect observability metrics, protect secrets, and track CVEs across Boot/Security/IdP/LDAP dependencies.

## 16. Pre-Submission Checklist

### 16.1. LDAP Branch

- [ ] Project runs `ldap-lab` without activating the OIDC branch.
- [ ] LDIF users `student`/`reader` load into the UnboundID server.
- [ ] `student` with right password binds via HTTP Basic/form.
- [ ] Wrong passwords and ghost users create no `Authentication`.
- [ ] Tests cover 401/302 and 403 with role rules when groups are added.
- [ ] MockMvc `user()` is not confused with real LDAP bind.
- [ ] DN, search/filters, and roles are clearly distinguished.
- [ ] No real passwords sent and no plaintext directories used outside the lab.
- [ ] Session cleanup/logout and log redaction are verified.

### 16.2. OIDC Branch

- [ ] Keycloak binds only to localhost with a dedicated `spring-lab` realm.
- [ ] Test user and confidential client `spring-lab-client` exist.
- [ ] Issuer metadata returns exact `http://localhost:8180/realms/spring-lab`.
- [ ] Keycloak redirect URI is exact `http://localhost:8080/login/oauth2/code/keycloak`.
- [ ] Client secret is supplied via env, never committed.
- [ ] Real browser flow traverses Spring → Keycloak → Spring callback.
- [ ] Spring creates a session after code exchange and ID Token verification.
- [ ] `/whoami` returns the OIDC principal without treating email as account ID.
- [ ] Tests cover `state`/`nonce`, wrong issuer, wrong secret, and missing roles.
- [ ] Verified that IdP login and local session logout have separate lifecycles.
- [ ] Container, browser sessions, and secrets cleaned up afterward.

## 17. Self-Assessment Questions

**1. Where does LDAP bind verify the password?**  
On the directory server. The Spring app uses the LDAP provider to submit credentials and receive the bind outcome, rather than reading password hashes from the directory by default.

**2. Why shouldn't every LDAP user be treated as an admin?**  
Bind only proves identity. Groups/roles/ownership require separate mapping and authorization.

**3. Does OIDC require the Spring app to know the user's Keycloak password?**  
No. The user enters their password at the IdP; the client app receives a code/ID Token through the protected flow.

**4. What is the default OIDC callback for registration ID `keycloak`?**  
`/login/oauth2/code/keycloak`. Keycloak must register the exact full URL including host/port.

**5. How do ID Tokens differ from Access Tokens?**  
ID Tokens prove login to the OIDC client, whereas Access Tokens target resource APIs by audience/scope.

**6. Why might `getName()` after OIDC not equal the username?**  
It may be the `sub` claim. Stable mapping uses `(iss, sub)`; emails/usernames are mutable attributes.

**7. Does `oidcLogin()` in MockMvc prove real token signatures?**  
No, it supplies a mock principal/claims. Browser/IdP integration with real signed tokens and verifiers is required.

**8. Why does embedded LDAP success not prove production LDAPS safety?**  
Local in-memory LDAP tests neither CAs, network attackers, AD restrictions, failover, nor multi-node behavior.

**9. If a token has the wrong issuer, should issuer validation be disabled?**  
No. Fix the canonical hostname, realm, and discovery metadata properly.

**10. What if login succeeds yet the admin route returns 403?**  
That usually indicates missing authorization privileges or a role mapper issue, not a failed password/IdP login.

**11. Does changing a role in Keycloak immediately update all Spring sessions?**  
Not guaranteed. Design session lifetimes/revocation and permission freshness explicitly.

**12. What proves real integration in this lab?**  
Requests traversing real LDAP bind or OIDC redirect/code exchange/ID Token verification, plus negative tests with bad credentials/protocol inputs—not mock authenticated principals alone.

## References

- [Spring Security 6.5 – LDAP Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html): bind, UnboundID/LDIF, managers, and directory config.
- [Spring Security 6.5 – Embedded LDAP Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/ldap/EmbeddedLdapServerContextSourceFactoryBean.html): `setPort`, `setLdif`, `setRoot`.
- [Spring Security 6.5 – OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): OAuth2 Client, Authorization Code, and login flow.
- [Spring Security – OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): request/redirect endpoints and customization.
- [Spring Boot 3.5 – OAuth2 Client Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): registration/client secret/provider issuer.
- [Spring Security – Testing OAuth2/OIDC](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oidcLogin()` fixture and limitations.
- [Keycloak – Docker Getting Started](https://www.keycloak.org/getting-started/getting-started-docker): local IdP container, realms, users, and clients.
- [Keycloak – Running in a Container](https://www.keycloak.org/server/containers): `start-dev`, bootstrap admin, hostname, and ports.
- [Keycloak – Realm import/export](https://www.keycloak.org/server/importExport): reproducible test fixtures.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `iss`/`sub`/`aud`/`nonce` and ID Token verification.
- [RFC 6749 – OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749.html): Authorization Code and redirect/client authentication.
- [RFC 7636 – PKCE](https://www.rfc-editor.org/rfc/rfc7636.html): code verifier/challenge.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): controls and error handling.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): redirects, state/PKCE, token types, and security.

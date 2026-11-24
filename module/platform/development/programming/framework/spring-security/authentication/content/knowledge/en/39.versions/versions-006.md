# Checking Dependencies, Persistence, and Versions Before Enabling OTT or WebAuthn

## 1. Goal: Do Not Just Enable the DSL and Call It Done

Spring Security offers two modern login mechanisms:

- **One-Time Token Login (OTT):** the server issues a single-use token, usually sent via email/SMS as a magic link. The recipient submits the token back to authenticate.
- **WebAuthn / Passkeys:** the browser uses the Web Authentication API and an authenticator to register a credential and then signs authentication assertions with a private key; the server stores and verifies the public-key credential.

Both have very short-looking configuration:

```java
http.oneTimeTokenLogin(Customizer.withDefaults());
http.webAuthn(Customizer.withDefaults());
```

However, **compiling configuration does not mean the system is production-ready**. OTT needs secure token delivery and a single-use token store suitable across multiple nodes. WebAuthn needs the version-matched library, a credential store that survives restarts, challenge handling across requests, proper RP ID/origin/HTTPS configuration, and compatible session serialization. Security patches also depend on the specific Spring Security version.

This lesson belongs to the **Versions** group and focuses on the pre-enablement verification workflow, avoiding two common mistakes:

1. Copying a Spring Security 7.x snippet into a 6.5 project and wondering why dependencies/APIs vanish.
2. Enabling a login UI that works on localhost yet loses tokens/credentials on restart, fails behind a load balancer, or permits a login path weaker than your security policy.

### Expected Outcomes

After this lesson, you should be able to answer:
- Which **Spring Boot, Spring Security, Spring Framework, and Java** versions are running? Is there one or multiple Security versions on the runtime classpath?
- From which version are OTT and WebAuthn supported, and which dependencies match **your version branch**?
- Which stores hold **OTT**, **WebAuthn registered credentials**, **WebAuthn user entities**, **registration/authentication options and challenges**, and **`SecurityContext`/sessions**?
- On restart or node switch, what must persist and what must expire?
- Are HTTPS, RP ID, origins, session/CSRF, and MFA policies properly aligned?
- Can you run tests for **one-time use, expiry, credential persistence, multi-node, session round-trip, and negative security cases** before opening to users?

Primary scope: Java 17+, Spring Security Servlet / Spring MVC, especially Spring Security 6.5 and 7.x. WebFlux has separate APIs distinguished later. Java examples explicitly indicate which ones are standalone and which are configurations to wire into an application.

## 2. Version Matrix: The First Thing to Establish

| Item | Spring Security 6.3 and Earlier | 6.4 | 6.5 | 7.x |
| --- | --- | --- | --- | --- |
| Built-in `oneTimeTokenLogin` | Not available as standard 6.4+ DSL | **Yes** | Yes, expanded configuration | Yes; check API/Javadoc of running branch |
| Built-in `webAuthn`/Passkeys | Not available as standard 6.4+ DSL | **Yes** | Yes | Yes |
| WebAuthn dependency per guide | Not applicable | Version-matched WebAuthn4J | **`spring-security-web` + `webauthn4j-core`** | **`spring-security-webauthn`** |
| WebAuthn credential repositories | Self-built or third-party library | Map/in-memory; check exact version | **JDBC repositories added** | JDBC/custom continues to be supported |
| OTT default token store | Not applicable | In-memory | In-memory | In-memory unless otherwise specified |
| OTT JDBC store | Not applicable | `JdbcOneTimeTokenService` | Yes | Yes |
| MFA integration via factor authorities | Not the model covered here | No | No 7.x `FactorGrantedAuthority` | **Yes**, new MFA mechanism |
| Typical Spring Boot | Older lines | Compatible Boot 3.x | Compatible Boot 3.x | Compatible Boot 4.x |

**This is a capability matrix, not an official compatibility table for every patch.** Choose a Boot BOM/security BOM and cross-check the specific Spring Boot compatibility matrix. Never mix Spring Boot 3 with a few Spring Security 7 modules and expect it to work.

One particularly important change: in the **Spring Security 6.5 guide**, WebAuthn requires `webauthn4j-core` alongside `spring-security-web`; in the **Spring Security 7.0+ guide**, a **dedicated module** `spring-security-webauthn` is used. Therefore, dependency setup **cannot be copied back and forth between the two branches**.

Beyond features, you must also check **security patches**. For example, advisory **CVE-2026-47841 (August 20, 2026)** affects WebAuthn with `userVerification=REQUIRED` and distributed HTTP session serialization in published affected versions. Detailed checklist in section 18.

## 3. Decision Order Before Touching `SecurityFilterChain`

Apply the following sequence to a real application:

```text
1. Record Boot / Security / Framework / Java versions
              |
              v
2. Clean dependency tree, matching BOM and WebAuthn module
              |
              v
3. Check security advisories + select patched release
              |
              v
4. Decide Servlet vs. WebFlux / which SecurityFilterChain handles routes
              |
              v
5. Choose persistence for OTT + WebAuthn + challenge + session
              |
              v
6. Prepare database schema, secrets, TLS, origins, RP ID
              |
              v
7. Build OTT delivery handler and WebAuthn credential enrollment
              |
              v
8. Test functionality, security, restart, multi-node, rollback
              |
              v
9. Roll out behind feature flag to small cohort, monitor, expand gradually
```

If any **dependency/persistence/patch/security** step fails, do not expose the feature simply because a localhost demo works. This sequence diagnoses root causes instead of randomly tweaking `@Bean` definitions and URLs.

## 4. Inspecting Actual Dependencies with Gradle

In a project with the Gradle wrapper (normal project inspection commands):

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency webauthn4j-core --configuration runtimeClasspath
```

If using Spring Security 7.x, also check:

```bash
./gradlew dependencyInsight --dependency spring-security-webauthn --configuration runtimeClasspath
```

**Verify:**
- Do `spring-security-config`, `spring-security-core`, `spring-security-web`, `spring-security-crypto`, and `spring-security-oauth2-*` resolve consistently?
- Is `spring-security-webauthn` present on the 7.x branch?
- Does 6.5 include `webauthn4j-core` at the version recommended by the guide/compatible BOM?
- Does any dependency transitively pull a different `webauthn4j` version onto the classpath?
- Are there manual build overrides via `resolutionStrategy.force`, Gradle constraints, `ext['spring-security.version']`, or direct pins overriding the BOM?
- Does the artifact running in containers match CI’s classpath? A clean `compileClasspath` with a mismatched `runtimeClasspath` still breaks at runtime.

`dependencyInsight` only displays dependencies **present in the project graph**; if it reports “no dependencies matching”, the feature dependency may not be declared yet. Never resolve that by adding random JARs one by one until the IDE stops complaining.

### Gradle Configuration for the 6.5 Branch

**Snippet** for `build.gradle` in a Spring Boot 3.x project that already has compatible plugins and BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    // Per Spring Security 6.5 guide: select compatible version.
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

**Do not** put 7.x’s `spring-security-webauthn` into this dependency block. `spring-security-*` artifacts are managed by the Boot BOM; the WebAuthn4J version in this snippet is the version illustrated in the **6.5 guide**, **not a guarantee that it is always the newest or safest**. Check compatibility and CVEs against your target deployment patch.

If you are only trying **OTT** on the 6.5 branch, WebAuthn4J is unnecessary. Conversely, WebAuthn alone does not require SMTP unless OTT is used, though a proper recovery/enrollment mechanism is still needed.

### Gradle Configuration for the 7.x Branch

**Separate snippet** for a compatible Spring Boot 4.x and Spring Security 7.x project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-webauthn'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Let the BOM resolve the `spring-security-webauthn` version within the same Spring Security family. Do not add a `webauthn4j-core` version from the 6.5 guide just because you see WebAuthn in the name: dependencies and libraries follow the supported 7.x module/version unless the matching documentation specifies otherwise.

**The Gradle snippets above are dependency lists**, not complete build files: you still need compatible Spring Boot plugins/versions, repositories, and the project’s Java toolchain config.

## 5. If Using Maven: Verify `dependencyManagement`

With the Maven wrapper:

```bash
./mvnw --version
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=com.webauthn4j
./mvnw help:effective-pom
```

On PowerShell, you can use `.\mvnw.cmd` instead of `./mvnw` when the project includes the Windows Maven Wrapper.

Cross-check `spring-boot-starter-parent` or the `spring-boot-dependencies` BOM. If you see `spring-security-web:6.5.x` next to `spring-security-config:7.x`, stop. Java APIs might still appear on the compile classpath while runtime throws `NoSuchMethodError`, `NoClassDefFoundError`, or filter-chain initialization failures.

**Never** rely on a single version line in the IDE. You must know how dependencies resolve after all parents, BOMs, transitive constraints, profiles, and actual image packaging.

## 6. What Else Does Enabling OTT Require Besides Dependencies?

Functionally, Spring Security’s `oneTimeTokenLogin()` involves two transactions:

```text
User submits identifier at /ott/generate
                  |
                  v
GenerateOneTimeTokenFilter
                  |
                  v
OneTimeTokenService.generate(request)
                  |
                  v
Token has username, random value, expiration
                  |
                  v
OneTimeTokenGenerationSuccessHandler
                  |
                  v
Send magic link/email/SMS to verified channel
                  |
                  v
User submits token at /login/ott
                  |
                  v
OneTimeTokenService.consume(...)
                  |
                  v
OneTimeTokenAuthenticationProvider
                  |
                  v
Authentication succeeds if policy permits
```

**Required checklist:**
- Appropriate `UserDetailsService`/account source.
- A **trusted** token delivery channel and a real `OneTimeTokenGenerationSuccessHandler`.
- A `OneTimeTokenService` store with TTL, single-use enforcement, and expired-record cleanup.
- Rate limiting, auditing, and protection against account enumeration.
- Proper HTTPS/link generation and reverse-proxy URL config (never use an arbitrary host header to craft phishing links).
- CSRF/session policies; recovery/login must not bypass locked/disabled accounts or required MFA per policy.
- In a cluster, tokens generated on node A must be consumable on node B.
- Fallbacks when email/SMS channels are unavailable; never log or return raw tokens in HTTP responses.

**OTT is not TOTP/HOTP.** The server issues a single-use token and sends it to a selected channel. TOTP/HOTP relies on an enrolled shared secret and a time/counter step. Enabling `oneTimeTokenLogin()` does not integrate an Authenticator app to verify TOTP codes.

## 7. OTT Persistence: When Is the In-Memory Default Appropriate?

If no custom `OneTimeTokenService` is provided, Spring Security uses `InMemoryOneTimeTokenService`. This implementation is useful for testing the feature:

- Simple, requires no DB tables.
- Suitable for local demos, standalone tests, and short-lived single-instance environments.
- Tokens disappear on process restart and are not shared across JVMs.
- Insufficient for multi-replica deployments behind a load balancer.
- Does not solve email delivery or monitoring.

Real-world failure scenario:

```text
POST /ott/generate  -> node A -> in-memory Map on A
Email contains token x
POST /login/ott     -> node B -> Map on B does not have x
                       -> authentication failed
```

**Typical production solution:** `JdbcOneTimeTokenService` or a custom `OneTimeTokenService` backed by a centralized store with reliable atomic single-use consumption. Never substitute session stickiness for durable token persistence when failover/restart resilience is required.

## 8. OTT Persistence via JDBC: Dependencies and Schema

Spring Security provides `org.springframework.security.authentication.ott.JdbcOneTimeTokenService`, initialized with `JdbcOperations`:

```java
@Bean
OneTimeTokenService oneTimeTokenService(JdbcOperations jdbc) {
    return new JdbcOneTimeTokenService(jdbc);
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.authentication.ott.JdbcOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeTokenService;
```

This is a **snippet for a `@Configuration` class**. It requires `spring-boot-starter-jdbc`, a properly configured `DataSource`, a database driver, migration scripts, and appropriate DB privileges. The bean can be picked up automatically by the `oneTimeTokenLogin` DSL; if you have **multiple `SecurityFilterChain` beans** or multiple token services, verify which chain uses which bean.

**Official schema resource** specified by the 6.5 `JdbcOneTimeTokenService` Javadoc:

```text
classpath:org/springframework/security/core/ott/jdbc/one-time-tokens-schema.sql
```

It **must be created in the database before using the service**. Do not assume adding the JDBC dependency makes Spring Boot auto-deploy the schema in production.

### Test Schema Differs from Production Schema

For example, in a **test profile using embedded H2** you can load the official resource:

```java
DataSource dataSource = new EmbeddedDatabaseBuilder()
    .setType(EmbeddedDatabaseType.H2)
    .addScript(
        "classpath:org/springframework/security/core/ott/jdbc/"
        + "one-time-tokens-schema.sql"
    )
    .build();
```

Required imports:

```java
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
```

This is a **snippet for unit/integration tests**; never copy `EmbeddedDatabaseBuilder` configuration straight into production.

For PostgreSQL/MySQL/Oracle:
1. Read the **DDL resource from the exact JAR/version**.
2. Adapt SQL syntax to your dialect if needed.
3. Create versioned migrations with Flyway/Liquibase.
4. Add appropriate indexes, constraints, and DB permissions.
5. Run migrations before deploying the application.
6. Test single-use consumption, expiration, and cleanup.
7. Monitor table/token volume and DB health.

Never write SQL guessing column names and run it on production. The resource inside the JAR is the authoritative source because schemas can evolve across versions.

## 9. OTT: Difference Between Generating, Storing, and Delivering Tokens

These responsibilities are distinct:

| Step | What Does the Framework Do? | What Must You Do? |
| --- | --- | --- |
| Generate | `OneTimeTokenService.generate(...)` creates token | Choose TTL/policy and a reliable store |
| Persist | In-memory or JDBC/custom store | Prepare schema, cleanup, clustering, concurrency |
| Deliver | `OneTimeTokenGenerationSuccessHandler` hook | Deliver to **verified** email/SMS, handle retries and anti-abuse |
| Consume | `OneTimeTokenService.consume(...)` looks up and consumes token | Test single-use, expiry, transactions/atomicity under load |
| Authenticate | Provider creates Authentication per config | Check account status, roles, MFA, session/cookie policies |

If during development you **print the token to stdout** and paste it manually, that is a testing convenience and **not** a secure delivery handler. Tokens can leak via log shipping, tracing, screenshots, or shell history.

When using magic links, configure the server-side base URL from trusted settings instead of building it from `Host`/`Forwarded` headers not validated by a proxy. A URL that works on `localhost:8080` can turn into `http://internal-service:8080` behind a reverse proxy if forwarded headers and public hostnames are misconfigured.

### Minimal 6.5 OTT Configuration Snippet

Example file `src/main/java/example/auth/OttSecurityConfig.java` in a Spring Boot 3.x Servlet project:

```java
package example.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.authentication.ott.JdbcOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeTokenService;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class OttSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .oneTimeTokenLogin(withDefaults());

        return http.build();
    }

    @Bean
    OneTimeTokenService oneTimeTokenService(JdbcOperations jdbc) {
        return new JdbcOneTimeTokenService(jdbc);
    }
}
```

**Explicit limitations:** this file can **compile** with matching 6.5 dependencies and JDBC, yet **is not a self-contained production OTT application**. You must still configure `UserDetailsService`, database/schema, a secure `OneTimeTokenGenerationSuccessHandler`, real email/SMS delivery, and security controls. Default filter settings generate login UI/submit pages; if the app has custom login pages, verify the differences.

If you already have an existing `SecurityFilterChain`, **merge** this snippet into the right chain rather than creating a second chain with a matching `anyRequest()` that accidentally shadows the existing chain’s routes.

## 10. OTT Token TTL and Single-Use Guarantees

`GenerateOneTimeTokenRequest` has a constructor accepting a username and `Duration`, for example:

```java
GenerateOneTimeTokenRequest request =
    new GenerateOneTimeTokenRequest(
        "alice",
        java.time.Duration.ofMinutes(5)
    );

OneTimeToken token = service.generate(request);
```

Imports:

```java
import org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest;
import org.springframework.security.authentication.ott.OneTimeToken;
```

This is a **snippet inside test/service code** with an existing `OneTimeTokenService service`; it is not a public request controller.

Behaviors to test:

1. A valid token can be consumed **once**.
2. A second call with the same token must fail.
3. A token past `expiresAt` must be rejected.
4. Two **concurrent** requests consuming the same token may succeed at most once, even across two nodes/DB connections.
5. A token generated on A can be consumed on B when sharing a store.
6. Tokens cannot be used for a different account/transaction if policy binds them.
7. Tokens never appear in logs, metric tags, or external analytics/referrer URLs.
8. Expired-row deletion and cleanup retries never delete valid tokens.
9. Token data does not linger indefinitely after logout/disable/password reset if policy requires revocation.

**Note:** testing two sequential calls alone does not prove atomicity under concurrent requests. Custom JDBC implementations need strong transaction/delete/update conditions; even with built-in JDBC, run integration tests against the real database/dialect.

`JdbcOneTimeTokenService` provides `setCleanupCron(...)`, `cleanupExpiredTokens()`, and a test clock; default cleanup runs roughly **hourly** per the 6.5 Javadoc. Purging expired records is separate from **rejecting expired tokens on consumption**.

## 11. OTT Does Not Automatically Handle Account State and MFA

Several rules must be tested independently:

- Are locked, disabled, or expired accounts allowed to log in with OTT?
- Do password-only or magic-link-only routes still enter areas requiring MFA?
- When resetting email or recovering an account, are outstanding tokens revoked?
- If an email account is compromised, can an attacker use magic links to gain admin-equivalent privileges?
- Is OTT treated as an independent factor alongside another factor under your policy?

Never assume `OneTimeTokenAuthenticationProvider` performs **all** the same account status checks as `DaoAuthenticationProvider`. Check the Javadoc and provider configuration **for your exact version**; 7.x provides a `UserDetailsChecker` option, while 6.x behavior must be verified before relying on it. Testing a disabled account across every login path matters more than guessing from class names.

Spring Security 7.x introduces an MFA model via `FactorGrantedAuthority` and authorization managers, yet **enabling both OTT and WebAuthn does not automatically force accounts to use both**. Define policies per resource: password + OTT, user-verifying WebAuthn, or other approved combinations.

## 12. WebAuthn: Needs Two Phases, Not Just a “Sign In with Passkey” Button

WebAuthn has two major ceremonies:

```text
ENROLL / REGISTRATION
User is already identified
   |
   v
Server creates PublicKeyCredentialCreationOptions + challenge
   |
   v
Browser navigator.credentials.create(...)
   |
   v
Authenticator creates credential key pair
   |
   v
Browser sends attestation/credential response
   |
   v
Server verifies challenge, origin, RP ID, policy
   |
   v
STORE user entity + public key credential linked to account

AUTHENTICATION
Browser requests challenge from server
   |
   v
navigator.credentials.get(...)
   |
   v
Authenticator signs assertion with private key
   |
   v
Server verifies challenge, signature, origin, RP ID,
UP/UV, credential record, status, and replay
   |
   v
Authentication succeeds if policy permits
```

**Private keys never enter the server database.** The database stores the public key, credential identifier, and metadata sufficient to verify assertions; the exact schema depends on the repositories/version.

**Credential registration and assertion authentication are two separate endpoints/flows**. Having `navigator` return a credential is not enough; the server must verify the ceremony. Without a previously registered credential, passkey login has nothing to verify unless a separate federated/registration mechanism is designed.

## 13. WebAuthn Persistence Involves at Least Two Repository Types

In Spring Security 6.5, the documentation describes:

| Repository | Data Managed | Built-in Implementation |
| --- | --- | --- |
| `PublicKeyCredentialUserEntityRepository` | WebAuthn user entity/handle linked to identity | Map/in-memory or **`JdbcPublicKeyCredentialUserEntityRepository`** |
| `UserCredentialRepository` | Credential records: ID, public key, user link, metadata | Map/in-memory or **`JdbcUserCredentialRepository`** |
| `PublicKeyCredentialCreationOptionsRepository` | Registration options/challenge across requests | Default via **`HttpSession`**; customizable |
| Authentication request/challenge state | Options used to verify assertions and matching session/correlation | Check implementation/version and session configuration |
| `SecurityContextRepository` | Post-login Authentication | Per chosen session/security context model |

**Do not conflate “credential persistence” with “challenge persistence”.** Registered credentials must persist long-term for future user logins. Challenges/options are **short-lived**, bound to a single ceremony, and often stored in the session. Even with durable credential storage, if the challenge is lost across nodes, registration or authentication still fails.

Default in-memory repositories are fine for demos; **restarting the JVM wipes passkey registrations**. Before production rollout, adopt JDBC/custom shared repositories and plan backups, schema migrations, ownership checks, and auditing.

### JDBC Repository Beans for WebAuthn 6.5

Example file `src/main/java/example/auth/WebAuthnRepositoryConfig.java`:

```java
package example.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.web.webauthn.management
    .JdbcPublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management
    .JdbcUserCredentialRepository;

@Configuration
public class WebAuthnRepositoryConfig {

    @Bean
    JdbcPublicKeyCredentialUserEntityRepository userEntityRepository(
            JdbcOperations jdbc) {
        return new JdbcPublicKeyCredentialUserEntityRepository(jdbc);
    }

    @Bean
    JdbcUserCredentialRepository userCredentialRepository(
            JdbcOperations jdbc) {
        return new JdbcUserCredentialRepository(jdbc);
    }
}
```

**Note when copying to an IDE:** Java `import` statements **must sit on a single line**, for example:

```java
import org.springframework.security.web.webauthn.management.JdbcPublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management.JdbcUserCredentialRepository;
```

In a real runnable file, use the **two full single-line imports below** instead of the wrapped imports shown for formatting. Requires Spring Security 6.5 with JDBC WebAuthn support, `JdbcOperations`, migrated tables, and the matching WebAuthn4J dependency.

If using custom storage (MongoDB/non-standard SQL), implement both interfaces completely and check concurrency/ownership/uniqueness/replay rather than overriding a single `save` method.

## 14. WebAuthn JDBC Schema via Official Resources

The Spring Security 6.5 Javadoc for the two JDBC repositories specifies two resources:

```text
classpath:org/springframework/security/user-entities-schema.sql
classpath:org/springframework/security/user-credentials-schema.sql
```

**These are WebAuthn schemas**, distinct from:

```text
classpath:org/springframework/security/core/ott/jdbc/one-time-tokens-schema.sql
```

used by OTT.

Do not run `users.ddl` meant for JDBC `UserDetailsManager` and assume it creates WebAuthn credential tables. **Both contain the word “user”, yet they are completely different tables/objects**.

Recommended migration sequence:
1. Confirm the Spring Security patch version in the production artifact.
2. Open the **DDL resources inside the exact version’s JAR** to check table/column/index/FK names.
3. Convert the DDL into Flyway/Liquibase migrations for the target RDBMS.
4. Enforce uniqueness constraints on credential IDs and user handles per the repository model.
5. Check the relationship between WebAuthn user entities and the account database: renaming a username must not break credential mappings; user handles should remain stable.
6. Review `signCount`, transports, discoverability/backup metadata, labels, and columns updated during authentication.
7. Grant `SELECT/INSERT/UPDATE/DELETE` privileges only to the appropriate service role.
8. Test backup/restore; verify previously registered credentials work after restart/restore.
9. Attempt concurrent registration of the same credential to verify uniqueness.
10. Verify no user can manage/delete another account’s credentials.

**Never** store raw user private keys in the server database. Avoid logging full public-key credential responses if they contain unnecessary identifiers or sensitive metadata.

## 15. Two Branch-Accurate Examples Enabling WebAuthn

### 15.1. Spring Security 6.5 (Spring Boot 3.x)

**Snippet** attached to an existing `SecurityFilterChain`:

```java
http
    .formLogin(withDefaults())
    .webAuthn(webAuthn -> webAuthn
        .rpId("login.example.com")
        .allowedOrigins("https://login.example.com")
    );
```

Imports:

```java
import static org.springframework.security.config.Customizer.withDefaults;
```

If deployed at `https://login.example.com`, the RP ID can be `login.example.com` per valid domain rules, and `allowedOrigins` must contain the **real origin** (scheme + host + non-default port). These values are **domain placeholders**, not generic settings to copy verbatim.

A 6.5 project requires `webauthn4j-core`, JDBC repositories for persistence, HTTPS, and Web Authentication browser support. When using the default registration page, protect credential add/delete actions by policy; never let a weak remember-me session enroll a passkey and take over an account.

### 15.2. Spring Security 7.x (Spring Boot 4.x)

The DSL looks similar:

```java
http
    .formLogin(withDefaults())
    .webAuthn(webAuthn -> webAuthn
        .rpId("login.example.com")
        .allowedOrigins("https://login.example.com")
    );
```

**Yet the dependency differs:** module `org.springframework.security:spring-security-webauthn`. In particular, after a major upgrade you must check imports, repository APIs, serialization, nullability/Jackson, and patch advisories rather than treating “the DSL looks alike” as proof of binary compatibility.

**Do not** drop 7.x’s `@EnableMultiFactorAuthentication` into a 6.5 branch. When enforcing MFA policies, inspect how the system stores factor authorities and which factors are required on protected routes. Enabling WebAuthn does not automatically convert every route in the system to user-verifying WebAuthn.

## 16. RP ID, Origins, TLS, Browsers, and Reverse Proxies

Before enabling WebAuthn, verify:

- **Secure context:** browsers generally allow the Web Authentication API only over HTTPS (localhost has development exceptions).
- **RP ID:** relying-party domain ID to which the authenticator binds credentials; it must be valid for the current origin under WebAuthn rules.
- **Allowed origins:** exact set of valid origins matching protocol, hostname, and port. `https://example.com` differs from `https://login.example.com`, and differs from `http://login.example.com`.
- **Public hostname behind a proxy:** when TLS terminates at a load balancer, the backend Spring app may see an internal HTTP host if forwarded headers are misconfigured.
- **Never take RP ID/origin from arbitrary client input.** `Host`/`X-Forwarded-*` headers must pass through a trusted proxy and an allowlist.
- **Credential portability:** changing the hostname or RP ID after users enroll can render old credentials unusable on the new domain. Plan a migration/transition strategy.
- **Browsers and authenticators:** test platform passkeys, roaming security keys, desktop/mobile, and real supported browsers.
- **User verification policy:** `preferred`, `required`, and `discouraged` differ; if the server truly requires UV, enforce it during verification, not just in UI hints.
- **Authenticator device loss:** before rollout, review at least one recovery mechanism that does not downgrade factor assurance via a weaker link.
- **Username-less login:** user handles and credential mappings must be stable/unique; never infer a user from an email field before the assertion is verified.

Testing a passkey created in Chrome/Windows on localhost **does not** prove production reverse proxies and hostnames are configured properly.

## 17. Challenges, Options, and Sessions: Long-Lived or Short-Lived?

WebAuthn requires unpredictable, server-verified challenges bound to a ceremony. In Spring Security 6.5, `PublicKeyCredentialCreationOptionsRepository` defaults to persisting creation options via **`HttpSession`**; thus registration can depend on the session across:

```text
POST /webauthn/register/options    -> issue challenge, save options
navigator.credentials.create(...)   -> browser + authenticator
POST /webauthn/register             -> read options/challenge, verify
```

Similarly for authentication:

```text
POST /webauthn/authenticate/options
navigator.credentials.get(...)
POST /login/webauthn
```

Here:
- **Credential records** must endure for months/years over the account lifecycle.
- **Challenges/options** only need to survive long enough to finish the ceremony, then must be invalidated against replay.
- **Session/`SecurityContext`** has its own login lifecycle.

If options sit in node A’s local session, a request completing the ceremony on node B loses that data. Plan **Spring Session Redis/JDBC**, equivalent shared sessions, or an appropriate options repository; load-balancer stickiness can serve as a limited stopgap, yet does not guarantee failover.

### When Using Redis/JDBC Sessions

Verify:
1. Do objects in `SecurityContext` and options serialize/deserialize cleanly under the actual serializer?
2. Does the browser send the session cookie across every step (`SameSite`, `Secure`, `Domain`, `Path`)?
3. Are CSRF tokens generated and sent properly when POSTing options/register?
4. Does the session remain valid long enough for the ceremony without staying overly permissive?
5. When a user logs in or enrolls a passkey, are session rotation/CSRF/state handled properly?
6. Do all application nodes run matching Spring Security JARs, serializers, secrets, and RP policies?
7. After a restart or node switch, are options/challenges restored properly?
8. Once consumed, can a similar ceremony reuse the challenge if policy forbids it?
9. Are raw challenges and sensitive assertions kept out of logs and public caches?

**Crucial point:** credential record persistence and challenge/options persistence are **two separate problems**. A JDBC user credential repository will not fix broken session serialization.

## 18. WebAuthn Security Patches and 2026 Versions to Check

According to the official **Spring Security CVE-2026-47841** advisory published on **August 20, 2026**: when WebAuthn is configured with `userVerification=REQUIRED` alongside a distributed HTTP session store (Redis/JDBC/Hazelcast), deserializing a `UserVerificationRequirement` can cause flawed identity checking and bypass the UV requirement in affected versions.

Published scope:

| Branch | Affected Versions | Patched Version / Channel per Advisory |
| --- | --- | --- |
| Spring Security 7.1 | 7.1.0 | **7.1.1** (OSS) |
| Spring Security 7.0 | 7.0.0–7.0.6 | **7.0.7** (OSS) |
| Spring Security 6.5 | 6.5.0–6.5.11 | **6.5.12** (Enterprise Support) |
| Spring Security 6.4 | 6.4.0–6.4.18 | **6.4.19** (Enterprise Support) |

**Accurate interpretation:** this advisory applies under specific conditions; it does not claim every WebAuthn app using sessions is bypassed. However, if your application falls within those conditions, **do not roll out** an affected version. Select a supported/patched version, review the advisory, and test real session serialization and UV enforcement.

Reference: https://spring.io/security/cve-2026-47841/

Beyond this advisory, check **newer security advisories** at actual release time for Spring Security, Spring Framework, WebAuthn4J, Spring Session, Jackson, JDBC drivers, and Boot. A static checklist cannot replace SCA/CVE scanning in CI.

### Other Serialization Errors That Also Require Testing

When storing WebAuthn Authentication/options in Spring Session JDBC/Redis, older versions can hit serialization incompatibilities. A Broadcom support article describes serializability improvements in the 7.1 line. That is a **different operational failure mode** from the UV bypass vulnerability. Tests must distinguish:
- `NotSerializableException` or deserialization failure → broken login flow.
- Session round-trip succeeds yet UV policy is bypassed → severe **security vulnerability**.
- Credential not found in repository → persistence/mapping error.
- `Origin`/`RP ID` mismatch → WebAuthn configuration error.

Never “fix” errors by lowering `userVerification` from `required` to `preferred`. Pick the proper patch and policy.

## 19. Protecting the Registration/Enrollment Flow

Once a user has logged in with a single factor, should `POST /webauthn/register` be allowed to add a new passkey? This is a critical security decision.

A new passkey can become a **long-lived login method**. Therefore you need:
- Verification of the current user’s identity from a **server-verified** `SecurityContext`.
- Fresh reauthentication/step-up to add/remove factors based on risk level.
- CSRF protection on registration/options POSTs over cookie sessions.
- Prevention of user A registering a credential onto user B’s account via body/path parameters.
- Unique credential IDs and stable user handles.
- Never elevating privileges based on user-entered metadata labels.
- Reasonable limits on credentials/devices per account, handling races when two tabs enroll concurrently.
- Auditing/notifications when passkeys are added/removed or recovery emails change.
- Timely procedures for lost authenticators and credential revocation.
- `disabled` or `locked` accounts must not bypass controls via passkeys or OTT unless policy explicitly allows it.

WebAuthn provides strong cryptography yet **does not automatically protect all account-management endpoints**.

## 20. `SecurityContext` Persistence Differs from Token/Credential Persistence

An app may store OTT via JDBC and WebAuthn credentials via JDBC, yet after authentication **fail to save the session properly** or lose it on node switch. Spring Security 6.x uses `SecurityContextRepository` to save/restore Authentication across Servlet requests; custom logins must save context explicitly.

Picture three stores:

```text
OTT token DB
    -> Exists only until consumed/expired.

WebAuthn Credential DB
    -> Persists long-term across many logins.

Spring SecurityContext / HTTP session
    -> Holds browser Authentication across requests.
```

They may share the same PostgreSQL instance, yet have **different tables and lifecycles**. `JdbcOneTimeTokenService` does not replace `HttpSessionSecurityContextRepository`, and `JdbcUserCredentialRepository` does not imply shared Spring Session is configured.

In a **stateless JWT** app, post-login outcomes may be exchanged for an access token; that is a different persistence model. Cookie-based login generally needs a session or an appropriate authentication repository.

### Custom Login Warning

If you write a custom controller after authentication:

```java
SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(
    context, request, response
);
```

**This is a snippet**, valid only once `authentication` has been verified by `AuthenticationManager`/providers, with matching `SecurityContextRepository`, Servlet request/response, and session strategy. Never fabricate an authenticated `Authentication` from an arbitrary username just to “make login work”.

## 21. Standalone Java 17: Demonstrating a Readiness Gate

This program is a **JDK learning model**; it does not call Spring Security and cannot replace dependency trees, CVE scans, browsers, or integration tests. It helps formalize **explicit deployment criteria** instead of vaguely saying “just turn it on”.

Create `AuthFeatureReadinessDemo.java`:

```java
public class AuthFeatureReadinessDemo {

    record Environment(
        boolean versionsAligned,
        boolean patchApproved,
        boolean httpsAndOriginCorrect,
        boolean ottSharedStore,
        boolean ottDeliveryReady,
        boolean webAuthnCredentialStore,
        boolean webAuthnChallengeRoundTrip,
        boolean recoveryReady) {}

    static String ott(Environment env) {
        boolean ready =
            env.versionsAligned()
            && env.patchApproved()
            && env.ottSharedStore()
            && env.ottDeliveryReady()
            && env.recoveryReady();
        return ready ? "READY" : "BLOCK";
    }

    static String webAuthn(Environment env) {
        boolean ready =
            env.versionsAligned()
            && env.patchApproved()
            && env.httpsAndOriginCorrect()
            && env.webAuthnCredentialStore()
            && env.webAuthnChallengeRoundTrip()
            && env.recoveryReady();
        return ready ? "READY" : "BLOCK";
    }

    static void show(String name, Environment env) {
        System.out.println(
            name + ": OTT=" + ott(env)
                + ", WebAuthn=" + webAuthn(env)
        );
    }

    public static void main(String[] args) {
        Environment localDemo = new Environment(
            true, true, false, false, false, false, false, false
        );

        Environment production = new Environment(
            true, true, true, true, true, true, true, true
        );

        Environment missingChallengeState = new Environment(
            true, true, true, true, true, true, false, true
        );

        show("local", localDemo);
        show("production", production);
        show("no-session-roundtrip", missingChallengeState);
    }
}
```

Run:

```bash
javac AuthFeatureReadinessDemo.java
java AuthFeatureReadinessDemo
```

**Expected exact stdout:**

```text
local: OTT=BLOCK, WebAuthn=BLOCK
production: OTT=READY, WebAuthn=READY
no-session-roundtrip: OTT=READY, WebAuthn=BLOCK
```

`production=READY` only means **the assumed booleans were marked true by the reviewer**, not a security certification. In a real application, each boolean requires concrete evidence: Gradle dependency report, patch report, deployment config, DB migration test, SMTP integration test, WebAuthn browser ceremony, and multi-node/serialization tests.

### Why Is `recoveryReady` in the Gate?

If a user loses a device or mailbox access, the product needs an approved account-recovery path. **Failing to design recovery upfront** often leads to help-desk flows that disable MFA or enroll new passkeys using weak email/password checks, creating a bypass around the primary authentication method.

## 22. JUnit 5: Testing Real `JdbcOneTimeTokenService` with H2

This example is valuable for verifying **the right JDBC schema and single-use consumption**. It sends no emails and runs no HTTP server. Its scope is a component test, not a full OTT login verification.

Requires Spring Security 6.5 dependencies, `spring-jdbc`, H2, and JUnit 5 from the test starter. Create `src/test/java/example/auth/JdbcOttStoreTest.java`:

```java
package example.auth;

import java.time.Duration;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest;
import org.springframework.security.authentication.ott.JdbcOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.authentication.ott.OneTimeTokenAuthenticationToken;

import static org.junit.jupiter.api.Assertions.*;

class JdbcOttStoreTest {

    private EmbeddedDatabase database;
    private JdbcOneTimeTokenService service;

    @BeforeEach
    void setUp() {
        database = new EmbeddedDatabaseBuilder()
            .setType(EmbeddedDatabaseType.H2)
            .addScript(
                "classpath:org/springframework/security/core/ott/jdbc/"
                    + "one-time-tokens-schema.sql"
            )
            .build();

        service = new JdbcOneTimeTokenService(
            new JdbcTemplate(database)
        );
    }

    @AfterEach
    void tearDown() throws Exception {
        if (service != null) {
            service.destroy();
        }
        if (database != null) {
            database.shutdown();
        }
    }

    @Test
    void tokenCanBeConsumedOnlyOnce() {
        OneTimeToken token = service.generate(
            new GenerateOneTimeTokenRequest(
                "alice", Duration.ofMinutes(5)
            )
        );

        OneTimeToken first = service.consume(
            new OneTimeTokenAuthenticationToken(
                token.getTokenValue()
            )
        );

        OneTimeToken second = service.consume(
            new OneTimeTokenAuthenticationToken(
                token.getTokenValue()
            )
        );

        assertNotNull(first);
        assertEquals("alice", first.getUsername());
        assertNull(second);
    }
}
```

Run:

```bash
./gradlew test --tests example.auth.JdbcOttStoreTest
```

**Expected** per the `OneTimeTokenService` contract: the first consumption returns the valid token, and the second returns `null`. If the DDL resource/dialect disagrees with the project’s H2 version, check the exact SQL script and dependency tree; do not “fix” it by skipping the table or using in-memory storage and claiming JDBC was tested.

For production-grade confidence, repeat the test with **Testcontainers running real PostgreSQL/MySQL**, run real schema migrations, and test generating a token on repository instance A, consuming it on B, and two concurrent consumers racing on the same token. This test **does not** verify SMTP, CSRF, account status, or session login.

## 23. WebAuthn Integration Tests Must Include a Browser/Authenticator

Unit tests mocking `Authentication` or `UserCredentialRepository` can be useful, yet do not prove passkeys can really log in. At minimum, staging should:

1. Run HTTPS on **the production-like hostname/RP ID** or an approved staging origin.
2. Sign in with an approved enrollment authentication method.
3. Fetch registration options with valid challenge, CSRF, and session.
4. Execute `navigator.credentials.create(...)` with a controlled test browser/authenticator.
5. Submit the result to `POST /webauthn/register`.
6. Read back the credential record from JDBC and the matching user entity.
7. Restart the app and confirm the record survives.
8. From another node, fetch authentication options and run `navigator.credentials.get(...)`.
9. Submit `POST /login/webauthn`, asserting principal/authorities match the user and expected flags.
10. Test invalid origin/RP ID/challenge/signature, insufficient user verification, and revoked credentials; all must be rejected.
11. Test two users, multiple browser sessions, user handles, and backup/synced passkeys.
12. Test distributed session serialization/deserialization when `userVerification=REQUIRED` on a patch proven to fix the advisory.

**Never fake a WebAuthn signature by setting `authenticated=true` in a test fixture and calling it an integration test.** Authentication outcomes must come from a real verifier validating a properly issued and bound challenge.

### Post-Restore Data Verification

Each registered credential maintains a stable link to its account. After backup restore or migration:
- User handles and credential IDs must remain intact.
- Public keys and required metadata must remain intact.
- Alice and Bob’s accounts must never get swapped.
- `signCount` and backup-state attributes must obey the library’s WebAuthn rules.
- Credentials revoked before the backup must not “resurrect” contrary to policy after restore.
- Only the account owner may delete/rename their own credentials.

## 24. Pre-Release QA Matrix

| Check Item | OTT | WebAuthn |
| --- | --- | --- |
| Version/BOM-aligned dependencies | Security 6.4+ core/web | 6.5 WebAuthn4J or 7.x dedicated module |
| Application startup | `oneTimeTokenLogin()` receives right service | `webAuthn()` receives right verifier/deps |
| Production persistence | JDBC/custom shared token store | JDBC/custom **user + credential repositories** |
| Data schema migration | OTT schema | User entity + user credential schemas |
| Node restart | Unexpired valid tokens remain consumable | Enrolled credentials remain intact |
| Cross-node traffic | Generate on A, consume on B | Options/challenge on A, ceremony on B |
| Session/challenge | Session/CSRF per login policy | Registration/auth options round-trip and CSRF |
| Network | Trusted public URL for email/SMS/magic link | TLS, RP ID, allowed origins accurate |
| Security events | Generate/consume/fail/rate limit | Register/assert/delete/fail/recovery |
| Replay | Token cannot be consumed twice | Challenge/signature/counter enforced by verifier |
| Account status | Disabled/locked cannot bypass | Disabled/locked cannot bypass |
| Authorization | OTT alone is not treated as MFA | WebAuthn alone does not satisfy every policy |
| Recovery | Safe process on lost mailbox/SMS | Safe process on lost authenticator |
| Patches | Scan Security/OTT advisories | **CVE-2026-47841** and active advisories |
| Rollback | Handling of unexpired issued tokens | Whether existing credentials continue working |
| Audit | Never log raw tokens | Never log private keys/sensitive assertions |

**Practical Definition of Done:** staging tests must have **recorded pass/fail results** tied to the exact target version and deployment topology. Tests on H2 and localhost cannot substitute for real RDBMS, reverse proxy, or shared session store verification.

## 25. Risks When Multiple `SecurityFilterChain` Beans Exist

Spring Security Servlet may have:
- API chain `/api/**` using Bearer tokens.
- Browser chain `/**` using form, OTT, and WebAuthn.
- Admin chain `/admin/**` with a dedicated MFA policy.

If OTT/WebAuthn is configured on a chain that **does not match the login routes**, the feature can stop working. Worse, a weaker chain could admit users to resources that require an additional factor.

Checklist:
1. Check `@Order` and `securityMatcher(...)` on all chains.
2. Do `POST /ott/generate`, `POST /login/ott`, and WebAuthn options/register/login endpoints traverse the intended chain?
3. Is CSRF properly enforced on POSTs? Never blanket `.csrf().disable()` just to make a demo run easily.
4. For browser logins, does a `STATELESS` `SessionCreationPolicy` prevent challenge/`SecurityContext` restoration?
5. Are roles/permissions mapped accurately after OTT/WebAuthn authentication?
6. Do protected routes requiring MFA enforce the policy across **all** paths: form, bearer, remember-me, recovery, and legacy login APIs?
7. Do CORS/proxy settings allow browsers to send cookies, CSRF tokens, and related headers properly?
8. Does any new login endpoint return `200` without actually saving Authentication/session?
9. Test both GET/POST methods and reverse-proxy prefixes/context paths.
10. Never define two `SecurityFilterChain` beans with overlapping matchers without understanding priority order.

**In WebFlux**, configuration types are `ServerHttpSecurity` and `SecurityWebFilterChain`; never use `HttpSecurity`/Servlet filters assuming they are equivalent. WebFlux OTT uses token-delivery handlers prefixed with `Server...`; read the reactive reference for your version. For WebAuthn, confirm the feature actually exists in your running **reactive branch** before adding Servlet dependencies.

## 26. Symptoms and Diagnostics

| Symptom | First Suspect | How to Check |
| --- | --- | --- |
| IDE cannot find `webAuthn()` | Older Spring Security or wrong import | `dependencyInsight`, correct Servlet `HttpSecurity` |
| Runtime `NoClassDefFoundError` WebAuthn4J | Missing/conflicting WebAuthn dependency | Runtime graph, BOM, artifact image |
| Spring 7 missing WebAuthn module | Missing `spring-security-webauthn` | Add the 7.x module |
| 6.5 missing JDBC WebAuthn repositories | Older patch or wrong package | Cross-check 6.5 Javadoc, dependencies |
| `BadSqlGrammarException` on OTT generate | OTT schema not applied or dialect mismatch | Migrations and classpath SQL resource |
| Passkey registration works yet vanishes on restart | Map/in-memory credential repository | JDBC/custom persistent repositories |
| Token emailed yet rejected on another node | In-memory token store on node A | Shared JDBC/custom store, test A→B |
| `POST /webauthn/register` reports missing challenge | Lost session/options or cookie issue | Session repo, sticky/shared, CSRF, challenge |
| Authenticator reports RP/origin mismatch | Wrong proxy/TLS/domain config | Browser origin vs. server `rpId`/`allowedOrigins` |
| `NotSerializableException` behind load balancer | Session store serializer incompatible with WebAuthn objects | Patched release, Spring Session round-trip test |
| UV configured REQUIRED yet not enforced | Possible 2026 advisory with session serialization | Check CVE-2026-47841 + patch and test |
| `/ott/generate` returns raw token in response | Demo/debug handler pushed to production | Use secure delivery handler, never log tokens |
| Expired tokens remain in DB | Cleanup job not running or unconfigured | `cleanupExpiredTokens`, cron, clock/expiry test |
| Disabled account logs in via OTT | Custom provider/status policy skipped check | Test each provider and `UserDetailsChecker` |
| `403` after passkey login despite valid credential | Auth succeeded yet role/factor policy unmet | Safely log class/authorities, policy, session |
| Passkey added in browser A missing in B | Local cache/repo or session mismatch | JDBC, user handle, multi-node check |
| “MFA enabled” yet Basic/legacy still enters admin | Policy only in UI / another chain | Test every authentication path |
| SQL migration succeeds yet user entities duplicate | Missing uniqueness/tenant mapping | Schema constraints, concurrent registration test |
| Login page breaks after Spring Security update | DSL endpoint/deprecation changes | Read version-matched migration guide/Javadoc |
| Admin UI shows “has passkey” yet login fails | Stale metadata cache, different credential repo | Compare real credential IDs/user entity |

**Categorize failures before fixing:** build-time API, runtime dependencies, persistence schema, challenge/session, origin/HTTPS, verification/authorization, security patch. Never try disabling CSRF, downgrading UV policy, or disabling session serialization as an unreviewed “fix”.

## 27. Safe Rollout and Rollback

### Before Rollout

- Lock a single **BOM version and patch** across the entire cluster.
- Scan CVEs, verify affected conditions, and confirm approved/available patches.
- Run **backward-compatible** DB migrations before deploying binaries.
- If the WebAuthn credential schema differs from older versions, prepare data/backups.
- Enable the feature via an internal feature flag first, then a pilot cohort.
- Test email delivery/SMTP, public URLs, TTLs, and load balancing.
- Test authenticator enrollment, browser support, session persistence, and challenges.
- Prepare dashboards: generate success, delivery errors, consume success/replay, register/assert success/fail, DB errors, node switches.
- Prepare runbooks for lost devices/mailboxes supporting account recovery without weakening assurance.

### Rolling Out Across Multiple Nodes

- **Never mix incompatible patches** across nodes sharing token/credential schemas or serialized sessions.
- Version skew can cause one node to write objects another node cannot deserialize.
- Rolling deployments must verify two-version read/write compatibility per the migration guide.
- Keep client/browser flows working when the load balancer routes two steps to two different nodes.
- Never log raw tokens/signatures to “debug easily”.
- When testing failover, capture correlation IDs, node/version, and DB/session states **without secrets**.

### If Rollback Is Required

1. Disable **new enrollments** via feature flag before changing schemas/versions.
2. Never delete already-registered WebAuthn credentials just because the new app failed.
3. Check whether the older binary can still read new DB records/serialized sessions.
4. For OTT, decide how already-sent unconsumed tokens will be handled.
5. Keep recovery paths working so users are not locked out.
6. Force re-login/clear sessions per policy if formats changed, while communicating and controlling impact.
7. If rollback restores a version **with a known CVE**, do not treat it as safe for keeping public WebAuthn active.
8. After an incident, add a regression test for the exact failure case that broke rollout.

## 28. Pre-Release Approval Checklist Before Flipping the Feature Flag

### Dependencies and Versions

- [ ] Saved outputs of `java -version`, `./gradlew dependencies`, and `dependencyInsight` for Spring Security modules.
- [ ] Spring Boot/Security/Framework/Java are compatible; no mixed major versions.
- [ ] Spring Security version supports OTT/WebAuthn (`6.4+` in Servlet).
- [ ] WebAuthn dependency matches branch: 6.5 WebAuthn4J; 7.x `spring-security-webauthn` module.
- [ ] Build/runtime classpath contains no conflicting versions/libraries.
- [ ] SBOM/security advisory review completed, especially CVE-2026-47841 if running WebAuthn distributed sessions.
- [ ] Multi-node deployed versions do not break serialization/schema compatibility.

### OTT

- [ ] `OneTimeTokenGenerationSuccessHandler` delivers tokens securely to verified channels.
- [ ] Using JDBC/custom shared `OneTimeTokenService` for multi-node/restart production.
- [ ] OTT DDL resource converted to migrations and applied to the right database.
- [ ] Tokens tested for entropy, TTL, single-use, and concurrent replay resistance.
- [ ] Links use trusted HTTPS hostnames; tokens never leak in logs, analytics, or external redirects.
- [ ] Rate limiting, anti-account-enumeration, auditing, and delivery-failure handling in place.
- [ ] Account state and MFA/authorization policies enforced on OTT logins.
- [ ] Tested generate A → consume B, expiry, retries, and cleanup.

### WebAuthn

- [ ] Durable user entity and credential repositories in place; no in-memory maps in production.
- [ ] Both WebAuthn DDL resources migrated for the target SQL dialect.
- [ ] Stable user handles/credential IDs bound accurately to accounts; revocation and backup/restore verified.
- [ ] RP ID and allowed origins match real domains; HTTPS and reverse-proxy config verified.
- [ ] Registration/authentication options/challenges persist and bind properly to the session/ceremony.
- [ ] When using distributed sessions, integration tests cover serialization/UV on a patched version.
- [ ] CSRF, account ownership, and role/MFA policies protect passkey enrollment/deletion.
- [ ] Tested with real authenticators/browsers plus negative signature/origin/challenge/UV cases.
- [ ] Recovery and authenticator-replacement workflows reviewed.
- [ ] Restarts, multi-node routing, and rollbacks do not lose credentials.

### Operations

- [ ] Quantitative readiness criteria, owners, and staging test results documented.
- [ ] Monitoring tracks error rates, latency, token volume, registration/auth success, and node identifiers.
- [ ] Never log passwords, magic tokens, private keys, or raw cookies/sessions/JWTs.
- [ ] Canary rollout, feature flags, and rollback paths tested.
- [ ] Security review covers API/legacy/remember-me/SSO paths, not just the login page.
- [ ] Alerts configured when DB/cache/sessions become unavailable or credential replay/abuse is detected.
- [ ] Every version change passes the regression suite before production.

## 29. Self-Check Questions

**Q1.** A Spring Boot 3/Security 6.5 project adds `spring-security-webauthn` from 7.x docs and hits dependency errors. What should be done?

**Answer:** Identify the exact dependency branch. The 6.5 guide uses `spring-security-web` + compatible `webauthn4j-core`; 7.x uses the `spring-security-webauthn` module. Never mix Security major modules.

**Q2.** OTT works on a single local node, yet when scaled to 2 replicas many users get “invalid token”. Why?

**Answer:** `InMemoryOneTimeTokenService` keeps separate per-JVM token maps. Switch to a shared JDBC/custom store and test generate A → consume B, while also checking sessions/URLs/TTLs.

**Q3.** WebAuthn credentials are stored in JDBC, yet `POST /webauthn/register` loses the challenge when routed to node B. Is persistence complete?

**Answer:** No. The JDBC credential repository persists long-lived records; challenges/options depend on a separate session/repository. Check session cookies, shared sessions/serializers, CSRF, and ceremony lifecycle.

**Q4.** Can you copy `JdbcUserDetailsManager`’s `users.ddl` to create all OTT and WebAuthn tables?

**Answer:** No. OTT and WebAuthn have dedicated DDL resources listed in this lesson. Migrate each repository’s exact schema for your dialect.

**Q5.** Does enabling `oneTimeTokenLogin()` and `webAuthn()` automatically create a “password + second factor” policy?

**Answer:** No. Those are authentication mechanisms. MFA enforcement requires factor/assurance policies on resources, particularly in Spring Security 7.x.

**Q6.** Should you set `userVerification=preferred` to “work around” the distributed-session UV bug in 6.5.11?

**Answer:** No. If policy requires `REQUIRED`, lowering to `preferred` weakens security. Check advisory CVE-2026-47841 and upgrade to a patched/supported version.

**Q7.** Why do passkeys fail to log in after changing the product domain?

**Answer:** WebAuthn credentials are bound to RP ID/origin rules. Changing the hostname or RP ID can invalidate existing credentials. Plan a domain migration strategy and re-enrollment.

**Q8.** A JDBC token test consuming sequentially twice succeeds then fails as expected. Does that prove strict single-use on a cluster?

**Answer:** No. You must test two **concurrent** consumers against a real DB and multiple nodes, verifying transaction/atomicity.

**Q9.** Why can an instance still throw `NotSerializableException` even though credential records are stored in PostgreSQL?

**Answer:** Credential record persistence and session/challenge serialization are two separate layers. Check Spring Session/Jackson serializers, `SecurityContext`/Auth objects, and version compatibility.

**Q10.** Does successful passkey registration mean modifying MFA factors requires no step-up?

**Answer:** No. Enrollment creates a new long-lived login method; enforce account ownership, CSRF, fresh reauthentication, and notifications.

## 30. Summary

Safely enabling OTT or WebAuthn requires **checking versions + dependencies + persistence + security policies + operational integration**, not just calling a DSL method.

- **Version:** 6.4 introduced Servlet OTT/WebAuthn; 6.5 added JDBC persistence for WebAuthn; 7.x provides `spring-security-webauthn` and expanded MFA mechanisms. Select patches addressing relevant advisories.
- **Dependencies:** use a consistent BOM; the 6.5 guide requires WebAuthn4J while the 7.x guide uses the dedicated WebAuthn module.
- **OTT store:** avoid in-memory in clusters; deploy `JdbcOneTimeTokenService`, prepare its schema, add a secure delivery handler, and enforce TTL and single-use.
- **WebAuthn store:** configure durable user-entity and credential repositories alongside proper challenge/options/session persistence.
- **Browser security:** HTTPS, RP ID, origins, CSRF, and UV policies must align.
- **Assurance:** enabling one login mechanism does not automatically enforce MFA on other APIs or login paths.
- **QA:** test restarts, multi-node routing, session serialization, disabled accounts, credential revocation, and token replay.
- **Release:** never ship with mismatched dependencies, missing migrations, missing recovery, or a version affected by an advisory relevant to your threat model.

A practical definition of “ready” requires real test evidence on the **exact binary and deployment topology** you plan to run. The Java 17 and JUnit JDBC examples show how to turn assumptions into tests, yet never replace verification with real browsers/authenticators and production-like environments.

## 31. Official References

- Spring Security 6.5 — One-Time Token Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html
- Spring Security 6.5 — Passkeys / WebAuthn dependencies and JDBC repositories: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html
- Spring Security 6.5 — What's New (JDBC persistence WebAuthn): https://docs.spring.io/spring-security/reference/6.5/whats-new.html
- Spring Security 7.0 — Passkeys (dedicated `spring-security-webauthn`): https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passkeys.html
- Spring Security 7.x — One-Time Token Login and MFA: https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html
- Spring Security 7.x — Multi-Factor Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html
- Javadoc Spring Security 6.5 — `JdbcOneTimeTokenService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/JdbcOneTimeTokenService.html
- Javadoc Spring Security 6.5 — `JdbcUserCredentialRepository`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/webauthn/management/JdbcUserCredentialRepository.html
- Javadoc Spring Security 6.5 — `JdbcPublicKeyCredentialUserEntityRepository`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/webauthn/management/JdbcPublicKeyCredentialUserEntityRepository.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security security advisory **CVE-2026-47841** (August 20, 2026): https://spring.io/security/cve-2026-47841/
- Broadcom knowledge article — Passkeys and Spring Session serialization: https://knowledge.broadcom.com/external/article/432996/using-passkey-with-spring-security-autho.html
- W3C Web Authentication specification: https://www.w3.org/TR/webauthn-3/
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Multifactor Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html

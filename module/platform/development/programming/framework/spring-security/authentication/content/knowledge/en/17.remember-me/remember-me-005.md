# Cookie lifetime, signing keys, and protecting server-side token data (Remember-me)

> **Goal:** Within Spring Security's **Remember Me** module, understand remember-me cookie lifetime, the role of the **key** in remember-me verification, and protections for **persistent tokens** stored in the database. Design so that token leaks, password changes, account revocation, application restarts, or multi-server deployments behave in controlled, tested ways.

## 1. What problem does Remember-me solve?

**Remember-me** allows a browser to re-identify a user after a normal session ends without prompting for a password on every return visit. It is a **long-lived login credential**, not merely setting a `Max-Age` on **JSESSIONID**.

Typical Servlet application flow:

~~~text
User submits POST /login (username/password + CSRF)
    |
    +-- Valid password verified
    |
    +-- If "Remember me" is checked:
    |       - issue a time-bounded remember-me cookie
    |       - for persistent-token: store series/token in server-side store
    |
    +-- Create current session (JSESSIONID)
    |
    v
Browser uses application with session

Later, old session expires / browser restarts:
    |
    | Remember-me cookie is still valid
    v
RememberMeAuthenticationFilter
    |
    +-- Extract remember-me cookie
    +-- RememberMeServices verifies token / calls UserDetailsService
    +-- ProviderManager validates RememberMeAuthenticationToken
    +-- Place RememberMeAuthenticationToken in SecurityContext
    |
    v
User is identified via remember-me, not a just-entered password
~~~

When the session already has a valid **Authentication**, remember-me normally does not run again. If Authentication is absent and a remember-me cookie is present, **RememberMeAuthenticationFilter** can attempt auto-login. Authentication succeeds only when the cookie is valid and the account remains eligible under policy.

**Key differences:**

| Mechanism | Client holds | Server holds | Lifetime / revocation |
| --- | --- | --- | --- |
| **Session** | JSESSIONID cookie (session ID) | Session and SecurityContext | Idle timeout; invalidate session |
| **Hash-based remember-me** | Cookie with username, expiration, and algorithm signature | UserDetails + encoded password info and key | Until expiration; changing password hash/key can invalidate token |
| **Persistent-token remember-me** | Cookie with opaque **series** and **token** | `persistent_logins` record with username, series, token, and last_used | Server-checked validity; records can be deleted/revoked and tokens rotated |
| **Remember-me disabled by default** | No remember-me cookie | No remember-me token | User must log in again when session ends |

**Remember-me cookies must not be used as an indefinite password replacement.** Anyone holding a valid cookie can impersonate the user while the cookie remains usable. In particular, applications handling payments, password changes, MFA toggles, or security settings should consider **requiring fresh full authentication** rather than trusting remember-me for sensitive actions.

## 2. Two built-in strategies in Spring Security

Spring Security Servlet provides two main remember-me strategies:

### 2.1. TokenBasedRememberMeServices — signature derived from user, expiry, and key

Per Spring Security documentation, cookie data conceptually consists of:

~~~text
Base64(
  username + ":" +
  expirationTime + ":" +
  algorithmName + ":" +
  algorithmHex(
    username + ":" + expirationTime + ":" +
    storedPassword + ":" + key
  )
)
~~~

Here **storedPassword** is the password value returned by **UserDetailsService**, typically a PasswordEncoder-encoded hash, **not** the plaintext password entered by the client. The snippet describes Spring Security's logical structure; it is not a JWT format and **Base64 is not secret encryption**.

Verification process:

1. Read the cookie and split username, expiration timestamp, algorithm, and signature.
2. Validate format, expiration timestamp, and accepted algorithm.
3. Load **UserDetails** by username from a trusted server source.
4. Recompute the signature using the stored password and the right **key**.
5. Compare results; accept only when information matches and account state is valid.

In Spring Security 6.5, this approach uses **SHA-256 by default** for new token signatures; Spring supports configuring a separate matching algorithm to transition legacy tokens. Never roll a custom signature by concatenating Base64 or choose MD5 just because old internet examples use it.

**Pros:** no separate token table required. **Cons:** stolen cookies can be replayed until expiration or until related inputs change; it is not easy to revoke **a single specific device**. Changing the password hash or key can invalidate many cookies at once. If password hashes are re-hashed on every run even without password changes, hash-based remember-me may also break after restarts.

### 2.2. PersistentTokenBasedRememberMeServices — series + token and database

The persistent-token strategy stores **one record** server-side per series. The cookie does not need to carry the username; the server looks up the username via the series.

~~~text
Browser cookie (Base64 of series:token)
   |
   +--> series: login series identifier
   +--> token: random value proving possession
                    |
                    v
           PersistentTokenRepository
              persistent_logins
              username
              series (PRIMARY KEY)
              token
              last_used
                    |
          series and token match?
               /            \
         Yes / valid       Mismatch
             |                 |
      generate new token   reject, handle
      update DB            suspected token reuse
      issue new cookie
~~~

Upon successful auto-login, the default implementation **rotates the token value**, updates token/last_used in the repository, and issues a new cookie. This limits how long an old token remains usable after replacement. Records can be deleted on logout or revoked by user depending on the flow.

**Pros:** the server holds data to revoke and manage tokens; it can detect reuse of rotated tokens while the series remains stored. **Cons:** requires an available database, strict access controls, secure backups, cleanup, concurrent-request handling, and multi-instance operations.

**Do not confuse “persistent token” with “signed JWT”**: the default persistent cookie is not a JWT and is not automatically encrypted with the key. It is a **bearer credential**: anyone possessing the right series and token can replay it. Thus the database storing the token column is also sensitive data.

### 2.3. Comparing choices

| Criterion | Hash-based token | Persistent token |
| --- | --- | --- |
| Needs separate storage table? | No | Yes |
| Key directly affects cookie signature? | **Yes** | Cookie does not use the hash-based formula; key mainly serves internal trust of remember-me Authentication in Spring Security |
| Password hash change invalidates old tokens? | **Yes**, because signature depends on stored password | **Not guaranteed**: persistent tokens must be actively revoked on password change |
| Can revoke one series/device? | Not easily with default architecture | Can design single-series deletion; default repository API focuses on per-user deletion |
| Can detect reused tokens? | No table-backed token rotation | Checks mismatch/rotation; must account for race conditions |
| If DB leaks | May expose user data, though no token table exists | Series/token values in the table must be treated as replayable secrets |
| Suitability | Low risk with understood revocation limits | Apps needing stronger management/revocation of remembered sessions |

**Practical recommendation:** choose **persistent-token** when you genuinely need remember-me and want revocation control; for highly sensitive apps, consider disallowing remember-me or limiting it to initial identification followed by full login.

## 3. Cookie lifetime: three different clocks

To design remember-me accurately, separate **cookie lifetime**, **remember-me server-side validity**, and **session idle timeout**.

| Clock | Controlled where | Example | What happens on expiration? |
| --- | --- | --- | --- |
| **Cookie Max-Age/Expires** | Set-Cookie header / browser | Max-Age=1209600 (14 days) | Browser stops sending that cookie |
| **Remember-me token validity** | RememberMeServices.tokenValiditySeconds | 1,209,600 seconds | Server rejects expired remember-me token even if browser retains it |
| **HTTP session timeout** | Servlet container / Spring Session | 15 minutes idle | JSESSIONID session becomes unusable; remember-me may run if cookie is still valid |

The example setting **tokenValiditySeconds(14 * 24 * 60 * 60)** is **14 days**. Default cookies are usually issued with a matching **Max-Age**. Still, never equate these clocks: browsers can clear cookies early, users can log out, or servers can revoke tokens or expire repositories before Max-Age finishes.

### 3.1. Timeline example

~~~text
Day 1, 08:00:
  Login succeeds, remember-me checked.
  JSESSIONID: 15-minute idle session (example).
  remember-me: cookie lives up to ~14 days, token stored in DB.

Day 1, 08:20:
  Session has idled out; browser still sends remember-me cookie.
  RememberMeAuthenticationFilter verifies token, restores identity.
  With persistent-token: generates new token, updates DB, issues new cookie.

Day 5:
  User changes password and policy revokes all remember-me tokens.
  DB deletes user's tokens; remaining browser cookie is no longer valid.

Day 16:
  Without renewal/re-login, remember-me has expired.
  Browser or server rejects it; fresh interactive credentials required.
~~~

In **PersistentTokenBasedRememberMeServices**, each successful auto-login can **refresh the token and cookie**, updating **last_used** in the DB. Effective lifetime can therefore act as **sliding validity** upon use rather than always a fixed deadline from initial issuance.

If policy mandates an **absolute lifetime** (e.g., every device must re-enter a password at least once every 30 days), store and check an extra **issued_at / original_authenticated_at** timestamp in a custom design. The default table's **last_used** alone does not prove hard absolute expiry is enforced.

### 3.2. Configuring lifetime in the right place

Spring Security DSL snippet for remember-me:

~~~java
.rememberMe(remember -> remember
    .tokenValiditySeconds(14 * 24 * 60 * 60)
    .rememberMeParameter("remember-me")
    .rememberMeCookieName("remember-me")
    .useSecureCookie(true))
~~~

This snippet is **only part of SecurityFilterChain**, not a standalone compilable Java class. For persistent tokens, add **tokenRepository(...)**, **UserDetailsService**, and key as shown in the full configuration later.

Do not use:

~~~properties
server.servlet.session.timeout=14d
~~~

to substitute for remember-me lifetime. That property controls the **HTTP session**, not the remember-me cookie lifetime. Also do not merely set **server.servlet.session.cookie.max-age=14d** hoping to remember logins: once the server session expires, an old JSESSIONID cookie cannot restore a valid Authentication by itself.

### 3.3. Default values and negative values

In standard remember-me implementations, the default lifetime is typically **14 days**, yet always **set it explicitly** to match your policy and version. The **TokenBasedRememberMeServices** API also documents **negative tokenValiditySeconds** values to create a non-persistent browser cookie while still applying a separate internal expiration; do not use negative numbers as a production trick without reading the exact Javadoc/version behavior. The example uses positive numbers for clear behavior.

**Max-Age=0** instructs the browser to delete the cookie; it is not how you configure a “session cookie”. When revoking, handle server-side token state as well rather than only sending Max-Age=0.

## 4. Signing key / key: role, lifecycle, and rotation

### 4.1. Remember-me key is neither a session ID nor a password

Spring Security provides **rememberMe().key(...)** or the **RememberMeServices(key, ...)** constructor. The key is a server secret that must be protected and kept consistent with the matching **RememberMeAuthenticationProvider** configuration.

With **hash-based remember-me**, the key is an input to the signature formula. If an attacker learns the key alongside related data, signature security degrades severely. Never set keys like **"myKey"**, **"springRocks"**, app names, dates, or a fixed literal in source code.

With **persistent-token remember-me**, the default cookie holds random series/token values matched against the database; the key **does not automatically encrypt or sign token columns in the DB**. It still participates internally when Spring Security issues/verifies `RememberMeAuthenticationToken` during authentication. **Changing the key does not fully revoke persistent-token cookies residing in the database**: to revoke, delete the corresponding rows.

### 4.2. Generating and keeping keys on the server

Example generating a strong random secret for dev environments or secret provisioning:

~~~bash
openssl rand -hex 32
~~~

This command creates **32 random bytes** represented as **64 hex characters**; output differs on every run. Never paste a hard-coded example directly as a real secret. Use a Secret Manager, properly protected Kubernetes Secrets, KMS, or your organization's secrets service. Grant read access only to services that need it, and never put keys in logs, exceptions, metrics, URLs, or repositories.

Set an environment variable, for instance:

~~~bash
export REMEMBER_ME_KEY="<secret-provisioned-from-Secret-Manager>"
~~~

On PowerShell:

~~~powershell
$env:REMEMBER_ME_KEY = "<secret-provisioned-from-Secret-Manager>"
~~~

Values in angle brackets are **placeholders**, not real keys. In deployment, supply a real secret provisioned securely.

**Multiple instances:** instances of the same application behind a load balancer must share compatible trust configuration. With hash-based strategy, differing keys between nodes can cause a cookie issued by node A to be rejected by node B. With persistent strategy, instances must access **the same persistent token store** and follow synchronization policies; the remember-me authentication key should be configured consistently to avoid operational surprises.

### 4.3. Key rotation must be planned

| Action | Hash-based remember-me | Persistent-token remember-me |
| --- | --- | --- |
| Rotate signature key | Usually invalidates older cookies | Insufficient to revoke tokens still in the DB |
| Change password hash | Cookies signed with old password hash may fail | Must actively delete user persistent tokens to log out devices |
| Delete token row from DB | Not applicable (no token table) | Corresponding cookie becomes invalid |
| Rotate DB encryption key (if any) | Not directly relevant | May require re-encrypting data or managing key versions |
| Key compromise incident | Rotate key, assess risk, and invalidate per model | Also assess persistent token data; revoke DB tokens as needed |

With hash-based remember-me, systems rotating keys by version usually need either a short-lived multi-key verification window or **forcing all users to log in again** if security takes precedence. Do not keep a leaked key in a “grace period” for long. Default Spring Security remember-me does not provide a full multi-key rotation store; supporting multiple keys requires designing and testing a custom implementation.

With persistent tokens, the key must be protected, yet **compromise revocation** primarily acts on the **token store**. Rotating the key alone does not render a valid series/token cookie useless.

## 5. Protecting persistent tokens stored server-side

### 5.1. Default schema and meaning of each field

Spring Security provides **JdbcTokenRepositoryImpl** for persistent remember-me. Typical schema:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

| Column | Function | Sensitivity |
| --- | --- | --- |
| username | Links record to user for lookup and revocation | Identifying data |
| series | Unique token series ID; looks up record | Sensitive alongside token; do not treat as an arbitrary public ID |
| token | Current random proof matched against the cookie | **Long-lived credential**: must be treated as a secret |
| last_used | Validity checkpoint updated on token rotation | Login behavior metadata; restrict access |

**Easy-to-miss detail:** the standard JDBC implementation stores tokens in a format that **PersistentTokenBasedRememberMeServices** compares directly with cookie values; it **does not cryptographically hash the token column the way BCrypt hashes passwords**. Consequently, a leaked backup or database dump containing series and token can be replayed for impersonation.

**Do not simply replace the token column with a BCrypt hash in JdbcTokenRepositoryImpl** and expect things to keep working. The default service expects to compare the repository-returned token with the cookie token; changing storage representation without adapting the service breaks all auto-logins. Storing one-way hashed tokens requires a **custom token protocol/service** implementing hash/verify/rotation properly, or a rigorously tested compatible design. Another option is **storage-layer encryption** of the token column with decryption inside a trusted adapter using a key outside the DB, which requires threat modeling, key rotation, and decryption error handling.

### 5.2. Minimum defense layers for the token store

1. **Least-privilege DB permissions:** the app account should access only required tables and operations; do not let arbitrary services or operators SELECT tokens freely.
2. **TLS on DB connections** across networks needing protection; verify DB endpoints and certificates.
3. **Encryption at rest and for backups** per policy. Full-disk/DB encryption mitigates lost disks/backups, though it does not stop a compromised DB account from reading plaintext values via SELECT.
4. **Never log tokens** as cookies, SQL bind parameters, APM spans, HTTP headers, ORM debug output, or crash dumps. Redact **Cookie** and **Set-Cookie**.
5. **Prevent SQL injection:** use parameterized SQL/JDBC repositories; never concatenate username/series from requests into SQL strings.
6. **Protect DB dumps and staging copies:** use synthetic/sanitized data; never copy production persistent login tokens to test environments.
7. **Controlled backup/restore:** restoring an old backup can resurrect revoked tokens if restored past a revocation point; define post-restore policies, potentially forcing re-login.
8. **Limit series/device counts** and watch for anomalies; the default table enforces no per-user maximum.
9. **TTL cleanup** and documented retention: expired rows must be purged periodically rather than retained forever.
10. **Minimal auditing:** record creation/revocation/rotation/alert events and correlation IDs per policy, never raw credentials.

### 5.3. Token rotation, reuse detection, and race conditions

In the standard persistent-token strategy:

- **Valid interactive login with remember-me checked** → create random **series** and **token**; INSERT into DB; issue cookie.
- **Valid auto-login** → look up series, compare token, generate new random token; UPDATE token and last_used; issue new cookie.
- **Series found but token mismatch** → may indicate an old token was reused or stolen; Spring can detect this, delete the user's tokens, and reject.
- **Expired** → reject authentication even if the DB row has not yet been purged.
- **Logout or revocation** → delete token records per policy and send an expired Set-Cookie to clear the browser cookie.

**Concurrent request scenario:** two tabs/callers both send the old cookie before the browser receives the new cookie. One request rotates the token; the second sees a mismatch and may be treated as potential theft. This is a race condition to test, especially with SPAs firing parallel API calls. Do not disable token mismatch checks just to “stop login errors”; design request flows, revocation policies, and coordination properly, or reconsider remember-me architecture if concurrency collisions happen frequently.

If store replication lags, a check on another node may read a stale token or miss the record. Persistent tokens require aligned **transaction isolation, consistency, series uniqueness, atomic updates, and primary/replica DB routing** on the authentication path. Never rely on stale caches to “accept” a token mismatch.

### 5.4. Expired token cleanup does not happen automatically

The Javadoc of **PersistentTokenBasedRememberMeServices** notes that it checks token age for validity, **but does not automatically delete all expired records** from the data store. You need a scheduled cleanup job aligned with the configured TTL.

Conceptual SQL example (**will not run verbatim if the DB does not support named parameters**):

~~~sql
DELETE FROM persistent_logins
WHERE last_used < :cutoff_time;
~~~

Here **cutoff_time** is computed by the application as current time **minus tokenValiditySeconds**. Syntax and schedulers vary across PostgreSQL, MySQL, and H2; standardize on UTC/timezones, clean up only under approved policy rules, monitor deleted row counts, and avoid long table locks.

If a **separate absolute lifetime** or stricter policy applies, the default schema's `last_used` column cannot enforce all rules accurately; extend the repository data/design.

## 6. Spring Boot 3.x and Spring Security 6.x sample using JDBC persistent remember-me

The example below is a **runnable Maven Java 17+ project** using Spring Boot 3.x, Spring Security 6.x, and Spring MVC/Servlet. It intentionally uses a **file-backed H2 database for local demo only** so persistent tokens survive a restart. In production, replace it with PostgreSQL/MySQL or an appropriate DB, controlled migrations, TLS, least-privilege DB roles, a secret manager, and HTTPS.

### 6.1. Dependencies

Generate the app from **Spring Initializr** with: **Spring Web**, **Spring Security**, **JDBC API**, **H2 Database**, and **Spring Boot Starter Test**. In Maven, typical dependencies are:

~~~xml
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
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
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
~~~

This is the **dependencies section** inside a `pom.xml` that already has the Spring Boot parent, version, and plugins from Initializr; it is not a standalone `pom.xml`. Do not pin a Spring Security version manually out of sync with the Spring Boot BOM without good reason.

### 6.2. Configuring datasource, remember-me key, and HTTPS

File **src/main/resources/application.properties**:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:./local-demo.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=local-demo

# File-backed H2 for study only: DB persists across restarts.
spring.datasource.url=jdbc:h2:file:./rememberme-demo;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

# Short-lived session cookie, independent of remember-me cookie
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=15m

# Secret from environment/secret manager, never commit
app.remember-me.key=${REMEMBER_ME_KEY}
demo.user.password=${DEMO_USER_PASSWORD}
~~~

The H2 file **rememberme-demo.mv.db** is created in the working directory; add it to **.gitignore** and never share it in a repo. It holds sensitive persistent tokens. If restart persistence is unnecessary, tests use **in-memory H2** and note the difference.

In production, enforce end-to-end HTTPS per your deployment topology and configure valid cookies at the public edge. **SameSite** on JSESSIONID in the properties above **does not guarantee SameSite on the remember-me cookie**, since that cookie is issued by Spring Security; in the Java code below we configure it directly via the cookie customizer and must verify the actual Set-Cookie header.

### 6.3. The persistent_logins table

File **src/main/resources/schema.sql**:

~~~sql
CREATE TABLE IF NOT EXISTS persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

This file runs at startup because **spring.sql.init.mode=always**. In production, do not let runtime SQL init manage schemas automatically; use **Flyway/Liquibase** or a controlled migration pipeline. The `series` primary key prevents duplicate series, though a unique constraint alone does not replace secure random token generation.

### 6.4. Entry point

File **src/main/java/com/example/remember/RememberApplication.java**:

~~~java
package com.example.remember;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberApplication.class, args);
    }
}
~~~

### 6.5. Security and persistent remember-me configuration

File **src/main/java/com/example/remember/SecurityConfig.java**:

~~~java
package com.example.remember;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.RememberMeServices;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String password) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(password))
                        .roles("USER")
                        .build());
    }

    @Bean
    PersistentTokenRepository persistentTokenRepository(
            DataSource dataSource) {
        JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
        repository.setDataSource(dataSource);
        // schema.sql already creates the table; do not enable setCreateTableOnStartup.
        return repository;
    }

    @Bean
    RememberMeServices rememberMeServices(
            UserDetailsService users,
            PersistentTokenRepository tokens,
            @Value("${app.remember-me.key}") String key) {

        var service = new PersistentTokenBasedRememberMeServices(
                key, users, tokens);

        service.setTokenValiditySeconds(14 * 24 * 60 * 60);
        service.setParameter("remember-me");
        service.setCookieName("remember-me");
        service.setUseSecureCookie(true);
        service.setCookieCustomizer(cookie -> {
            cookie.setAttribute("SameSite", "Lax");
            cookie.setHttpOnly(true);
            cookie.setSecure(true);
            cookie.setPath("/");
        });
        return service;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RememberMeServices rememberServices,
            @Value("${app.remember-me.key}") String key)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/error").permitAll()
                        .requestMatchers("/api/sensitive").fullyAuthenticated()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .rememberMe(remember -> remember
                        .key(key)
                        .rememberMeServices(rememberServices))
                .logout(logout -> logout
                        .logoutSuccessUrl("/public?logout"))
                .build();
    }
}
~~~

**Component breakdown:**

- **JdbcTokenRepositoryImpl** uses the DataSource to create/update/fetch/delete remember-me tokens. It serves as a shared repository across instances using the same DB.
- **PersistentTokenBasedRememberMeServices** generates and verifies tokens by series and rotates tokens after auto-login. It depends on **UserDetailsService** to load the user and authorities; a custom authentication provider not using UserDetailsService must still supply one for standard remember-me integration.
- **setTokenValiditySeconds(...)** governs remember-me lifetime; distinct from **server.servlet.session.timeout**.
- **setUseSecureCookie(true)** forces the remember-me cookie to carry `Secure` even when the backend sits behind a TLS-terminating proxy.
- **setCookieCustomizer(...)** sets `SameSite=Lax`, `HttpOnly`, `Secure`, `Path=/` on the remember-me cookie. These cookie attributes cannot be inferred solely from JSESSIONID settings.
- **rememberMeServices(...)** wires the exact service into Spring Security; **key(...)** keeps the remember-me authentication provider key aligned with the service.
- **formLogin(...)** supports the **remember-me** checkbox/form parameter. It does not issue cookies automatically for users who did not opt in unless policy sets `alwaysRemember`.
- **fullyAuthenticated()** on sensitive endpoints requires full authentication, rejecting `RememberMeAuthenticationToken` alone. Remembered users may have to re-enter credentials to access this path.

**Sample implementation limits:** users live in `InMemoryUserDetailsManager`, token DB is local H2, and password change, device management, scheduled token cleanup, and custom re-authentication UX are omitted. This demonstrates standard API integration, not a complete production setup. User memory is recreated on restart with consistent username/password and roles; persistent remember-me relies on the repository, so it is not inherently invalidated by BCrypt rehashing the way the hash-based scheme is.

### 6.6. Controller to observe remember-me and fully authenticated

File **src/main/java/com/example/remember/ProfileController.java**:

~~~java
package com.example.remember;

import java.util.Map;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "remembered",
                authentication instanceof RememberMeAuthenticationToken);
    }

    @GetMapping("/api/sensitive")
    public Map<String, Object> sensitive() {
        return Map.of("allowed", true);
    }
}
~~~

After password login, **remembered=false**. Once the session disappears while a valid remember-me cookie triggers auto-login, **remembered=true**. Endpoint **/api/sensitive** demands **fullyAuthenticated**, so remember-me alone is insufficient; depending on the entry point, the browser may be redirected to the login page to fully authenticate. This highlights an essential practical point: **remember-me verifies identity at a different assurance level than a recent interactive login**.

### 6.7. Localhost HTTPS and safe secrets

Use the JDK **keytool** to generate a self-signed certificate for localhost only:

~~~bash
keytool -genkeypair -alias local-demo -keyalg RSA -keysize 2048 -validity 7 -storetype PKCS12 -keystore local-demo.p12 -storepass local-test-only -keypass local-test-only -dname "CN=localhost" -ext "SAN=dns:localhost"
keytool -exportcert -rfc -alias local-demo -keystore local-demo.p12 -storepass local-test-only -file local-demo.crt
~~~

Run these in the project directory. Never commit **local-demo.p12** or TLS passwords. Self-signed certificates are never for production.

Linux/macOS:

~~~bash
export TLS_KEYSTORE_PASSWORD=local-test-only
export DEMO_USER_PASSWORD=demo-pass
export REMEMBER_ME_KEY="$(openssl rand -hex 32)"
./mvnw spring-boot:run
~~~

**Note:** the command above creates a new remember-me key on every shell invocation. If you want to verify that cookies stay valid **across restarts**, supply **a stable key** from a secret manager or protected local dev secret file rather than regenerating on every startup.

Windows PowerShell example:

~~~powershell
$env:TLS_KEYSTORE_PASSWORD = "local-test-only"
$env:DEMO_USER_PASSWORD = "demo-pass"
$env:REMEMBER_ME_KEY = "<stable-secret-from-secret-manager>"
.\mvnw.cmd spring-boot:run
~~~

Protect cookies with real HTTPS. For instance, open **https://localhost:8443/login** in a browser and select **Remember me**. Browsers will require trusting the local certificate per your dev workflow; never pass flags that bypass TLS verification in production paths.

### 6.8. Inspecting Set-Cookie with browser and curl

After logging in with remember-me selected, **Network → Response Headers** will contain a cookie like:

~~~http
Set-Cookie: remember-me=<opaque-cookie>; Path=/; Max-Age=1209600; Secure; HttpOnly; SameSite=Lax
~~~

**This is a shape illustration only**; token values and attribute order vary by container/version, and `Expires` may appear. To verify accurately, inspect your app's actual headers and **Application/Storage → Cookies** in the browser. The JSESSIONID cookie has its own structure and lifetime.

Using curl to inspect the API and HTTP status:

~~~bash
curl --cacert local-demo.crt -i -c cookies.txt https://localhost:8443/public
curl --cacert local-demo.crt -i -b cookies.txt https://localhost:8443/api/me
~~~

The second request while unauthenticated typically returns **302** to `/login`. To test login via curl, extract the CSRF token from **GET /login**, keep the session cookie, and POST username/password/_csrf/remember-me; a browser or MockMvc is more convenient and less error-prone. Never pass real passwords in commands that might be saved in shell history.

After login, try deleting only the **JSESSIONID session cookie** in DevTools while keeping the remember-me cookie. Requesting **/api/me** triggers auto-login if the token is still valid, returning **remembered=true** for the new request. When the remember-me cookie rotates, the browser must store the new cookie from `Set-Cookie`.

Never copy raw remember-me cookie values into logs, public DevTools screenshots, or ticketing systems: it is a replayable credential.

## 7. Automated testing of critical boundaries

**MockMvc** is well suited for testing form login and the remember-me filter flow. Still, it is not a browser and does not guarantee every Set-Cookie attribute is enforced identically by browsers in production; add an actual HTTPS E2E test.

### 7.1. Testing form login, auto-login, and sensitive access

File **src/test/java/com/example/remember/RememberMeFlowTest.java**:

~~~java
package com.example.remember;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "server.ssl.enabled=false",
        "demo.user.password=demo-pass",
        "app.remember-me.key=local-test-key-for-unit-tests",
        "spring.datasource.url=jdbc:h2:mem:remember-tests;DB_CLOSE_DELAY=-1"
})
@AutoConfigureMockMvc
class RememberMeFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rememberMeCookieRestoresUserAfterSessionIsGone()
            throws Exception {

        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "alice")
                        .param("password", "demo-pass")
                        .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        Cookie remembered =
                login.getResponse().getCookie("remember-me");

        assertNotNull(remembered);
        assertTrue(remembered.getSecure());
        assertTrue(remembered.isHttpOnly());
        assertEquals("/", remembered.getPath());
        assertEquals(14 * 24 * 60 * 60, remembered.getMaxAge());

        // Do not forward the JSESSIONID session from the login request.
        // Send only the remember-me cookie on the new request.
        MvcResult autoLogin = mvc.perform(get("/api/me")
                        .cookie(remembered))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.remembered").value(true))
                .andReturn();

        // With persistent remember-me, auto-login rotates the cookie.
        Cookie rotated =
                autoLogin.getResponse().getCookie("remember-me");
        assertNotNull(rotated);
        assertNotEquals(remembered.getValue(), rotated.getValue());

        // Remember-me is not yet full authentication.
        mvc.perform(get("/api/sensitive").cookie(rotated))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void withoutRememberMeParameterNoPersistentCookie()
            throws Exception {

        MockHttpServletResponse response =
                mvc.perform(post("/login")
                            .with(csrf())
                            .param("username", "alice")
                            .param("password", "demo-pass"))
                        .andExpect(status().is3xxRedirection())
                        .andReturn()
                        .getResponse();

        assertNull(response.getCookie("remember-me"));
    }

    @Test
    void incorrectPasswordDoesNotIssueRememberMeCookie()
            throws Exception {

        MockHttpServletResponse response =
                mvc.perform(post("/login")
                            .with(csrf())
                            .param("username", "alice")
                            .param("password", "wrong")
                            .param("remember-me", "on"))
                        .andExpect(status().is3xxRedirection())
                        .andReturn()
                        .getResponse();

        assertNull(response.getCookie("remember-me"));
    }
}
~~~

**Significance:** the first test runs from real credentials through the login filter, obtains the remember-me cookie, drops the session, and uses the cookie on a new request. It also verifies that the token rotates and that the sensitive endpoint demands full authentication. **@WithMockUser** cannot substitute for this test because it skips credential verification and cookie issuance.

In this test no real HTTP server runs and **server.ssl.enabled=false** merely simplifies MockMvc startup; we still assert the remember-me cookie has **Secure=true** per service config. That does not prove a browser will accept/send the cookie over plain HTTP. To test real **SameSite=Lax** headers from the container, run an HTTP-level test reading **Set-Cookie** over an embedded HTTPS server or verify in a browser.

### 7.2. Testing expiration and revocation

Additional cases to cover in real systems:

| Scenario | Expectation |
| --- | --- |
| Cookie and token still valid | Auto-login succeeds; persistent token rotates |
| Cookie past Max-Age (browser) | Browser does not send it; user must log in again |
| Token past server-side validity | Server rejects even if raw cookie is sent by a manual client |
| DB row deleted | Old cookie fails to authenticate |
| User disabled/locked | Auto-login rejected per user details checker and policy |
| Password changed | With persistent tokens: invoke revocation; old cookie must not re-authenticate |
| Token mismatch after rotation | Rejected; suspected replay/theft handled per implementation |
| Two concurrent auto-login requests | Detect race/false theft and design sensible rules |
| DB unavailable/timeout | **Fail closed**; do not issue Authentication from unverified tokens |
| App restarts with unchanged key, DB intact | Token still works if conditions are met |
| App restarts yet DB wiped | Remember-me cannot recover; re-login required |
| Hash-based signing key changed | Old hash-based cookies rejected |
| Only persistent service key changed, DB tokens intact | Do not treat key change as absolute revocation; test and delete tokens per policy |
| User logs out | Cookie cleared and server-side persistent tokens revoked per behavior/design |
| Sensitive endpoint authorization | RememberMeAuthenticationToken must not substitute for full authentication |

**Do not use Thread.sleep(14 days)** to test expiration. Instead use controllable time (a custom implementation's Clock, fixture rows with an old `last_used`, a test-only very short TTL, or database test fixtures) and verify right at the boundary. With default code, test fixture construction must match your schema/version.

### 7.3. Testing durable storage does not automatically mean secure

A test proving “login survives restart” only proves the DB stores tokens; it does not prove the DB is secure. Add tests and configuration checks for: table SELECT privileges, backup encryption, redaction, token reuse, lockout/rate limiting, input validation, rotation atomicity, auditing, and revocation policies.

Also never print real tokens to stdout to “prove token rotation”. You can compare two strings **with assertions** without logging their values.

## 8. Logout, password changes, and logging out all devices

### 8.1. Logout is more than clearing a cookie

With persistent remember-me, a sound logout process should:

1. Verify the logout request belongs to the active user/session; for browser session cookies, verify CSRF.
2. Clear SecurityContext and invalidate the HTTP session.
3. Invoke RememberMeServices' logout mechanism to clear the remember-me cookie.
4. Revoke matching persistent tokens per your implementation's policy (default behavior revokes via repository in certain flows — **verify actual behavior with your version**).
5. Ensure valid token records cannot accidentally re-authenticate the user right after logout.

**Do not assume client-side cookie deletion is enough.** If an attacker already copied a token, the copy remains valid as long as the DB record exists. Server-side revocation is the decisive control for persistent tokens.

### 8.2. Password changes and account locks

When a user successfully changes their password, the system should define clear policies:

- **Revoke all remembered devices**: delete the username's persistent tokens immediately when updating the password.
- **Revoke current device only**: requires identifying the current series and building per-series repository/endpoint management; the default **removeUserTokens(username)** API deletes by user and does not provide complete device-management UIs out of the box.
- **Disable/lock account**: ensure UserDetailsChecker or user lookup blocks remember-me login even if tokens remain in the DB; you may also delete tokens immediately to reduce leftover state.
- **MFA re-enrollment / credential resets**: should generally invalidate remembered devices per security policy rather than waiting out the TTL.

In a password-change service sharing a transaction on the same datasource, revocation can invoke:

~~~java
// Integration snippet, NOT a standalone class.
// userPasswordService is the application component updating the BCrypt hash.
@Transactional
public void changePassword(String username, String newPassword) {
    userPasswordService.updatePasswordHash(username, newPassword);
    persistentTokenRepository.removeUserTokens(username);
}
~~~

You must import Spring's **@Transactional** and declare dependencies like **userPasswordService** and **persistentTokenRepository** in the real service. When users reside in a separate service/DB, you need consistency/event coordination and error handling rather than assuming a JDBC transaction spans a remote system.

Note: with **hash-based remember-me**, changing the password hash is one way tokens become invalid; with **persistent-token**, **that is not automatic**. Include this distinction in both tests and operational runbooks.

### 8.3. Suspected theft or DB breach

- If **one user's cookie leaks**, revoke their persistent tokens, invalidate sessions as needed, and investigate anomalous events.
- If the **`persistent_logins` table leaks**, assume series/token pairs may have been read. Revoke all affected tokens and require re-login per incident policy; do not merely change the remember-me key.
- If a **hash-based signing key leaks**, rotate the key and scope impact; also assess whether password hashes were exposed.
- If a **DB encryption key leaks**, plan key rotation, inspect backup exposure, and investigate whether ciphertext/tokens were exfiltrated.
- Notify the security team and execute incident response per procedure; never paste credentials into tickets.

## 9. Common implementation mistakes

**Mistake 1 — Stretching JSESSIONID to 30 days and calling it remember-me.** Long-lived cookies do not restore evicted sessions. **Right way:** use RememberMeServices or a clear token-refresh design, managing server lifetimes and cookies separately.

**Mistake 2 — Putting the remember-me key in Git or source code.** Exposed secrets are hard to rotate and impossible to un-read. **Right way:** secret manager, least privilege, planned key rotation, log redaction.

**Mistake 3 — Generating a fresh random key whenever each node boots.** With hash-based remember-me, cookies issued by node A can fail on node B. **Right way:** configure a stable, compatible key across the cluster.

**Mistake 4 — Thinking rotating the key deletes all persistent tokens.** Persistent cookies rely on series/tokens and the DB; the key does not automatically encrypt token columns. **Right way:** actively revoke records, especially during incidents.

**Mistake 5 — Storing persistent tokens in a DB while treating them as non-sensitive.** SQL dumps or backups can be replayed. **Right way:** DB ACLs, encryption/backup protection, redaction, rotation, key custody, and operator controls.

**Mistake 6 — Replacing DB tokens with BCrypt hashes directly inside JdbcTokenRepositoryImpl.** The default service matches the cookie token against the repository value; altering the format breaks auto-login. **Right way:** build a custom hash-verifying service or compatible encryption adapter, testing both rotation and revocation.

**Mistake 7 — Failing to purge expired rows.** Stale tokens enlarge sensitive data stores and complicate operations. **Right way:** TTL-based cleanup jobs, monitoring, and retention policies.

**Mistake 8 — Not revoking tokens on password change or account lock.** Persistent tokens may keep authenticating if the user source permits it or policy lacks revocation. **Right way:** hook revocation into the account lifecycle.

**Mistake 9 — Testing only with @WithMockUser.** Authorization tests can pass even if no remember-me cookie is ever issued or verified. **Right way:** test real form login, cookies, auto-login, DB storage, and failure cases.

**Mistake 10 — Enabling Secure for JSESSIONID while forgetting the remember-me cookie.** Two cookies may be emitted by two different components. **Right way:** call **setUseSecureCookie(true)** and inspect Set-Cookie headers for every cookie at public ingress.

**Mistake 11 — Treating remember-me as fully authenticated.** A days-old remember-me credential is inappropriate for every sensitive action. **Right way:** enforce **fullyAuthenticated()**, re-authentication, and step-up MFA as needed.

**Mistake 12 — Solving two-tab mismatches by removing all reuse detection.** That weakens replay detection. **Right way:** investigate race conditions, cookie issuance/receipt flow, and concurrency controls, then design a tested policy.

## 10. Production and acceptance testing checklist

- [ ] Choice between hash-based and persistent-token is grounded in a threat model; if high-risk, consider disabling remember-me.
- [ ] Remember-me is issued only when the user opts in, unless product policy specifies another clear mechanism.
- [ ] Remember-me cookie has **Secure**, **HttpOnly**, SameSite, and appropriate Path; verified in a real HTTPS browser.
- [ ] **tokenValiditySeconds** is configured explicitly; distinct from JSESSIONID timeout and absolute session lifetime.
- [ ] Key is sufficiently random, managed as a secret, consistent across deployments, and has a rotation plan.
- [ ] Team understands hash-based key rotation vs. persistent-token server-side revocation.
- [ ] Persistent store has schema/unique series, transactions, consistency, and least-privilege DB roles.
- [ ] Token columns and DB backups are treated as sensitive credentials; never log raw tokens, Cookie, or Set-Cookie.
- [ ] Encryption-at-rest or a tested custom hash-at-rest design is evaluated; never alter token column formats ad hoc.
- [ ] **Revoke on password change**, disable/lock, logout, security incidents, and MFA resets are implemented.
- [ ] Expired-row cleanup, clear TTLs, and sliding vs. absolute expiry evaluation are in place.
- [ ] Tests cover remember-me after session expiry, token rotation, tampering/reuse, DB outages, concurrent requests, and clusters.
- [ ] Sensitive endpoints require `fullyAuthenticated`/step-up rather than treating remembered users as fresh logins.
- [ ] TLS, CORS/CSRF, and regular session cookies remain controlled independently of remember-me.
- [ ] CI includes real tests running through filters and token repositories, not mocked security contexts alone.

## 11. Self-check questions

**1. If JSESSIONID expires after 15 minutes while the remember-me cookie lasts 14 days, can auto-login work?** Yes, provided the remember-me token is still valid, the repository/user store is available, and policy allows it. This is a new remember-me authentication, not the old session coming back to life.

**2. Does rotating the key delete all persistent tokens?** Not guaranteed. Persistent tokens are verified against server-side records; you must delete/revoke tokens in the repository to invalidate them.

**3. Why must tokens in the DB table be treated as secrets?** Because cookies carry series/token as a bearer credential. Anyone possessing that data can attempt replay to impersonate the user.

**4. Does PersistentTokenBasedRememberMeServices automatically delete expired rows?** Per Javadoc, it rejects expired tokens without automatically purging all expired rows; run a cleanup job.

**5. Why shouldn't remember-me unlock sensitive password-change endpoints?** Remember-me credentials are long-lived and may have been copied; requiring full authentication/step-up reduces risk.

**6. Why can the same persistent cookie fail when two tabs send concurrent requests?** Auto-login rotates tokens; the second tab can present the old token after the first tab rotated it, causing a token mismatch. Test and handle concurrency properly.

## 12. References

- [Spring Security 6.5 — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html): two strategies, hash-based signatures, persistent tokens, UserDetailsService, schema.
- [Spring Security 6.5 — RememberMeConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/RememberMeConfigurer.html): key, tokenRepository, tokenValiditySeconds, rememberMeParameter, useSecureCookie.
- [Spring Security 6.5 — AbstractRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/AbstractRememberMeServices.html): cookie customizer, validity, Secure, account checker.
- [Spring Security 6.5 — PersistentTokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html): token rotation, validity checks, expired row cleanup.
- [Spring Security 6.5 — Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html): persistent_logins table.
- [Spring Security 6.5 — Authorization](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): fullyAuthenticated() and access rules.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Secure, HttpOnly, SameSite, Path, Max-Age.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): protecting session tokens, cookies, and revocation.

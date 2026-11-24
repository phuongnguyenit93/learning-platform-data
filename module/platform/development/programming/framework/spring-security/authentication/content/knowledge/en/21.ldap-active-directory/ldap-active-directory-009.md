# LDAPS, connection secrets, timeouts, and distinguishing account errors from infrastructure errors

> **Scope:** Authenticating users via LDAP or Active Directory (AD) in a Spring Security application. The focus is on protecting the connection channel to the directory, keeping secrets safe, setting effective timeouts, and distinguishing **invalid credentials/account status** from **LDAP/AD, network, TLS, or configuration incidents**. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, and the JDK's JNDI LDAP provider; when using other versions, re-check the corresponding APIs and configuration.

## 1. Learning outcomes and authentication flow

After this lesson, you should be able to:

1. Explain the difference between **LDAPS** (LDAP over TLS immediately upon connection) and **StartTLS** (upgrading an LDAP connection to TLS before sending secrets); verify certificate chains, hostnames, and truststores.
2. Distinguish user passwords from credentials of the **service/bind account** used for lookups; design storage, least privilege, rotation, and log controls for each type.
3. Configure JNDI **connect timeout**, **read timeout**, and overall request time budgets; identify places where unbounded waits can still occur.
4. Recognize LDAP result codes, AD subcodes, Spring Security exceptions, and infrastructure causes without returning sensitive details to the user logging in.
5. Practice verifying success, wrong password, locked account, unavailable LDAP, invalid certificate, slow connections, and service outages with a **fail closed** mindset.

A common bind authentication flow:

~~~text
Client --HTTPS--> Spring Security application
                      |
                      v
             AuthenticationManager
                      |
           [look up user DN] ----(optionally using service account)---> LDAP/AD
                      |
           [bind with user's username + password] -------------------> LDAP/AD
                      |
           [read groups/permissions if needed] ----------------------> LDAP/AD
                      |
           result -> Authentication succeeds | rejected | service error
                      |
          Create session/token only when authentication conditions are met
~~~

**Two non-identical types of secrets:** The user password is sent per authentication attempt to perform a bind; the service account password is only used for operations the service account is permitted to perform (such as searching for users and groups). With a fixed DN pattern strategy, a service account might not be needed to look up the DN. AD can use a UPN (`user@domain`) for direct bind. Never store user passwords in the application's database or logs after authentication.

## 2. What do LDAPS and StartTLS protect?

| Approach | Channel establishment | Common port | Security conditions |
| --- | --- | --- | --- |
| LDAPS | TLS handshake first, then LDAP exchange over the TLS channel | TCP 636 (or system-configured port) | Valid server certificate, matching trust chain and hostname, modern TLS configuration |
| LDAP + StartTLS | Initial LDAP connection, then StartTLS **before** sensitive SIMPLE bind/search | TCP 389 | Upgrade must succeed, no fallback to cleartext, full certificate verification |
| Unencrypted LDAP | LDAP exchange over a channel without TLS | TCP 389 | **Never use for password-based SIMPLE bind** on trusted or untrusted networks |

LDAPS is the practical choice when the system supports a dedicated TLS port. StartTLS can also meet security requirements if configured properly and configured to **reject the connection outright if the TLS upgrade fails**. Changing `ldap://` to `ldaps://` is only the first step and is insufficient if the application skips certificate verification.

TLS protection provides confidentiality and integrity for data in transit on the network, while authenticating the server's identity via the trust chain and hostname. TLS **does not** encrypt secrets stored in configuration, does not prevent the application from logging passwords itself, and does not replace limiting service account permissions.

### Why is hostname verification needed?

Suppose the configuration is:

~~~text
ldaps://dc01.corp.example.test:636
~~~

The DC's certificate must contain a DNS identifier matching `dc01.corp.example.test` (typically in Subject Alternative Name), and the issuing or intermediate CA must be trusted by the JVM truststore. Using an IP address when the certificate was issued only for a DNS name can cause hostname verification failures.

On modern JDKs, LDAPS endpoint identification is enabled by default. **Do not "fix" errors by disabling endpoint identification**, installing a TrustManager that trusts all certificates, downgrading to `ldap://`, or allowing fallback to plain LDAP. The right fix is issuing/selecting the proper certificate, hostname, CA chain, and truststore.

Some AD environments also use the Global Catalog TLS port (typically 3269) for cross-domain searches. Choose the endpoint according to your organization's AD design; do not replace port 636 with 3269 based on port numbers alone.

## 3. Truststores, certificates, and connection checks

**Layered verification:**

1. **DNS and network:** the application resolves the right FQDN, opens a TCP connection to the approved endpoint/port; firewalls and Network Policies allow traffic.
2. **TLS:** the server presents a complete, unexpired certificate chain, supported algorithms/protocols, and matching hostname; the JVM trusts the right CA.
3. **LDAP bind:** the service account or user can bind under the chosen mechanism; search/attribute-read permissions are sufficient.
4. **Application:** user search filter, base DN, and group mapping are accurate; Spring Security receives the expected principal/authorities.

You can run the following command from a **machine or container with network routing equivalent to the application environment** to inspect the handshake and certificate chain:

~~~bash
openssl s_client -connect dc01.corp.example.test:636 -servername dc01.corp.example.test -showcerts
~~~

This command is useful for observing the certificate chain and TLS from the host running the command; it **does not prove** the Java truststore trusts the CA, does not perform an LDAP bind, and does not replace testing endpoint identification inside the application. If using a dedicated truststore, configure the truststore path/type and password through the runtime's secret mechanism, and verify intermediate CAs and certificate rotation plans. Prefer managing trust via approved CAs rather than ad-hoc importing a leaf certificate without a renewal process.

**Warning when using failover:** Every DC in the endpoint list must have a valid certificate matching its own hostname. The first DC having valid TLS does not guarantee the backup DC does as well. When traffic goes through a load balancer or TLS proxy, determine which party terminates TLS and whether TLS is maintained to the backend.

## 4. Managing connection secrets

In LDAP/AD, maintain separate secret inventories for two groups:

| Group | Who uses it | Minimum policy |
| --- | --- | --- |
| **Service/bind account** | Application to search DNs, read groups/permissions per policy | Read-only permissions on strictly required OUs/attributes; never use a Domain Admin account; store secrets in a secret manager, Vault, or secure provisioning mechanism; have a rotation plan |
| **User password** | Verified by LDAP/AD during each login | Received only over HTTPS; used to bind over a verified TLS channel; never cache indiscriminately, never write to logs/metrics/exceptions, never put in URLs |
| **Truststore/key material** | JVM/LDAP client or client certificate if mutual TLS is used | Files and passwords granted least-privilege read access; manage CAs, expiry, and rotation; distinguish truststore (trusting the server) from keystore (holding private keys) |

Common mistakes:

- Committing secrets to `application.yml`, `application.properties`, test files, READMEs, Dockerfiles, Git history, or screenshots.
- Passing passwords in command-line arguments (`-D...password=...`) and logging the full command line; many environments allow viewing process arguments.
- Using a high-privilege account "to connect easily," skipping rotation requirements, or reusing one password between staging and production.
- Putting `Authentication`, LDAP `DirContext`, or exceptions containing credentials into structured logs; leaving unrestricted JNDI/LDAP tracing enabled in production.
- Confusing an **expired/locked service account** error with "wrong user password," triggering false alerts and wrongly locking user accounts.

Configuration can be supplied via a secret management system and Spring Boot's externalized configuration mechanism. For example, define logical properties `app.ldap.url`, `app.ldap.base`, `app.ldap.bind-dn`, and `app.ldap.bind-password`. With environment variables, Spring Boot supports `APP_LDAP_URL`, `APP_LDAP_BASE`, `APP_LDAP_BIND_DN`, and `APP_LDAP_BIND_PASSWORD` via configuration binding; inject secrets only at runtime. **Never copy secret values into examples or shared shell environment variables.**

When rotating the service account password, check whether the application or connection pool is holding onto old credentials. You may need to reload beans/connections or perform a proper rolling restart; test binding with the new credentials, monitor error rates after rotation, and then revoke the old credential. Never record the old value in a ticket for debugging.

## 5. Timeouts: connect, read, and total request are three separate layers

The JDK's JNDI LDAP provider has two critical environment properties:

| JNDI property | Meaning | Illustrative example |
| --- | --- | --- |
| `com.sun.jndi.ldap.connect.timeout` | Time limit to establish an LDAP connection (and potentially wait to acquire a pooled connection) | `"2000"` = 2,000 ms |
| `com.sun.jndi.ldap.read.timeout` | Time limit waiting for a response to an LDAP operation after connecting | `"3000"` = 3,000 ms |

Values are **strings representing an integer number of milliseconds**, not a `Duration`. On the default JNDI provider, missing or non-positive (`<= 0`) values may fall back to TCP timeouts or wait indefinitely for reads. Set positive values and verify with real packet-loss/network-drop tests.

For example, a single authentication call performs DNS/TCP/TLS, service bind, DN search, user bind, group lookup, and then returns a response. Setting `connect=2s` and `read=3s` **does not guarantee** total login time stays under 5 seconds:

- A single login involves **multiple LDAP operations**; wait times across operations can accumulate.
- Multiple fallback LDAP URLs, referrals, or retries can repeat connection attempts.
- Queue/thread pool waits, DNS, TLS handshakes, or a slow backend can exceed the HTTP-level budget.
- A client calling other internal services before/after LDAP also needs its own budget.

Start from the **overall request deadline** (e.g., 5 seconds per an illustrative SLA), allocate time across actual measured steps, and set client/driver timeouts so no single operation can consume the entire budget. On timeout, **never return a successful Authentication** and never turn a `CommunicationException` into `BadCredentialsException` just to keep returning HTTP 401.

**Using reactive Java:** If a synchronous LDAP/JNDI client sits inside WebFlux, wrapping it in `Mono` only changes the API type. The I/O remains blocking; isolate it off the event loop with an appropriate scheduler/pool and still set connect/read timeouts directly on JNDI. Cancellation signals or `Mono.timeout` do not guarantee interrupting every legacy blocking I/O call. In Servlet applications, request threads can also remain blocked until timeout.

## 6. Configuring Spring Security LDAP with LDAPS and timeouts

The example below assumes an LDAP-style directory with users under `ou=people` and login attribute `uid`. The configuration uses a **read-only service account** to search and then **binds as the user's identity** to verify the password.

Appropriate dependencies for a Spring Boot Servlet project using Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-ldap'
}
~~~

The Spring Boot BOM manages compatible dependency versions. If the application already has a web stack, do not add a second stack just for this example.

~~~java
package demo.ldap;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;

@Configuration
public class LdapAuthenticationConfig {

    @Bean
    BaseLdapPathContextSource ldapContextSource(Environment properties) {
        String url = properties.getRequiredProperty("app.ldap.url");

        if (!url.startsWith("ldaps://")) {
            throw new IllegalArgumentException("LDAPS endpoint is required");
        }

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(properties.getRequiredProperty("app.ldap.base"));
        source.setUserDn(properties.getRequiredProperty("app.ldap.bind-dn"));
        source.setPassword(properties.getRequiredProperty("app.ldap.bind-password"));
        source.setPooled(false);
        source.setBaseEnvironmentProperties(Map.<String, Object>of(
                "com.sun.jndi.ldap.connect.timeout", "2000",
                "com.sun.jndi.ldap.read.timeout", "3000"
        ));
        return source;
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource ldapContextSource) {
        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(ldapContextSource);
        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter("(uid={0})");
        return factory.createAuthenticationManager();
    }
}
~~~

Example configuration, adjusted with addresses and DNs matching your directory:

~~~text
app.ldap.url              = ldaps://ldap01.corp.example.test:636
app.ldap.base             = dc=corp,dc=example,dc=test
app.ldap.bind-dn          = uid=svc-search,ou=service,dc=corp,dc=example,dc=test
app.ldap.bind-password    = [provided by secret manager at runtime]
~~~

The `[provided by secret manager at runtime]` part is an **annotation** distinguishing the data type, not a literal configuration value to put in an actual file. Supply it via environment/secret mounting and ensure the runtime reads the right property. The illustrative timeout numbers must be tuned to your network, SLA, operation count, and load tests.

Explanation:

- `LdapContextSource` is the factory for creating LDAP contexts; JNDI properties are applied when establishing connections.
- `setUserDn`/`setPassword` configure the service bind for user lookup; user authentication passes the login username/password to `AuthenticationManager` when performing the user bind. Restrict the service account's ACLs.
- `factory.setUserSearchFilter("(uid={0})")` locates users with a parameter handled by Spring in the filter template. Never concatenate unescaped usernames directly into LDAP filters. For AD, the filter, base DN, and login format usually differ.
- `setPooled(false)` in the example avoids relying on native JNDI pooling for sensitive contexts; in high-load applications, design pooling deliberately with monitoring and verify how credentials/contexts are handled.
- These beans are **not a standalone application with a `main` method**; they require a Spring Boot project with dependencies, real properties, valid CA trust, a properly configured `SecurityFilterChain`/login route, and a reachable directory.

**Note on StartTLS:** The configuration above uses `ldaps://` and does **not** implement StartTLS. If StartTLS is required, use Spring LDAP's appropriate `DirContextAuthenticationStrategy` to ensure TLS is upgraded and verified **before SIMPLE bind**. Never swap `ldaps://` for `ldap://` and assume the same security level. In particular, never enable native JNDI pooling for contexts that mutate TLS state or bind principals.

## 7. Active Directory case: subcodes aid investigation, not public messages

AD commonly authenticates using `user@domain` and has `ActiveDirectoryLdapAuthenticationProvider`. When configuring the provider, still enforce a trusted LDAPS URL and JNDI timeouts.

~~~java
package demo.ldap;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider;

@Configuration
public class AdAuthenticationConfig {

    @Bean
    ActiveDirectoryLdapAuthenticationProvider adProvider() {
        ActiveDirectoryLdapAuthenticationProvider provider =
                new ActiveDirectoryLdapAuthenticationProvider(
                        "corp.example.test",
                        "ldaps://dc01.corp.example.test:636/");

        provider.setContextEnvironmentProperties(Map.<String, Object>of(
                "com.sun.jndi.ldap.connect.timeout", "2000",
                "com.sun.jndi.ldap.read.timeout", "3000"
        ));

        // Enable only if the application has a safe detailed error-handling policy.
        provider.setConvertSubErrorCodesToExceptions(true);
        return provider;
    }
}
~~~

The snippet above only declares the provider; wiring the provider into `AuthenticationManager` and `SecurityFilterChain` must fit the specific application. Do not combine both the illustrative LDAP and AD configurations simultaneously unless intentionally creating multiple authentication providers. For production, verify API versions, AD policies, actual domain/URL, and error-response rules.

When AD returns LDAP result code `49`, the diagnostic message sometimes contains a subcode:

| Common AD subcode | Diagnostic meaning |
| --- | --- |
| `525` | User not found |
| `52e` | Invalid credentials |
| `530` | Not permitted to log on at this time |
| `532` | Password expired |
| `533` | Account disabled |
| `701` | Account expired |
| `773` | User must reset password |
| `775` | Account locked out |

These are **AD-specific subcodes**, not standard LDAP error codes uniform across all directories. Per Spring Security's API, bind error `49` becomes `BadCredentialsException` by default. When `setConvertSubErrorCodesToExceptions(true)` is enabled, certain subcodes are mapped to `CredentialsExpiredException`, `DisabledException`, `AccountExpiredException`, or `LockedException`; other codes may still map to `BadCredentialsException`. Do not assume every subcode has its own exception or that any arbitrary LDAP server returns those subcodes.

Subcodes should be used for **controlled internal audits/investigations**, never returned verbatim in API responses, HTML, cookies, redirect query strings, or metric labels carrying account identifiers. Public messages like "this account exists but is locked" enable user enumeration; if an account recovery flow is needed, protect that flow with separate verification mechanisms.

## 8. Distinguishing account errors from infrastructure errors

Error classification must consider **the stage at which the failure occurred** and the **exception/cause chain**. For example, a service account bind failing because a secret was rotated is a service configuration incident to the person logging in, not their wrong password.

| Signal | Category to investigate | Appropriate behavior |
| --- | --- | --- |
| LDAP `49` on **user** bind / `BadCredentialsException` | Invalid credentials or invalid account state per directory data | Do not issue session; generic login message, bounded audit log |
| `LockedException`, `DisabledException`, `CredentialsExpiredException` from AD (when subcode conversion is enabled) | Account policy/status | Do not issue session; handle support/recovery per policy; avoid public detail leakage |
| LDAP `49` on **service account** bind | Wrong, expired, or locked service secret/account, or changed bind permissions | **Configuration/infrastructure error**; alert operations, do not blame user |
| `javax.naming.CommunicationException`, socket timeout, DNS failure, LDAP server unreachable | Cannot connect / no response | **Infrastructure**; do not create session; raise health alert and investigate |
| `SSLHandshakeException`, CA/hostname/certificate error | TLS trust or certificate configuration | **Infrastructure/security**; do not downgrade; fix certificate/truststore |
| LDAP `51 busy` / `52 unavailable` (if returned by directory) | Backend busy or unavailable | **Infrastructure**; control retry/backoff and load |
| LDAP `32 noSuchObject`, `50 insufficientAccessRights` | Wrong DN/search base or missing permissions; occasionally data-related | Verify stage and policy; never assume wrong password |
| Java error / group-mapping or user-DN parsing bug | Application configuration or bug | Never grant default permissions; alert and add regression tests |

**Two errors very easily confused:**

- **Bad credentials:** the LDAP server was reached successfully, TLS was valid, and the user bind was rejected due to credentials/status. Return a single generic message to avoid account disclosure.
- **Directory unavailable:** the system could not verify the user due to network/TLS/timeout/backend failure. There is no evidence of a wrong password. Return a temporary error or service-support notice with a correlation ID for operations lookup.

### Illustrative HTTP/API decision table

| Conclusion after safe classification | Suggested outcome | Notes |
| --- | --- | --- |
| Wrong username/password or account state disallowing login | `401 Unauthorized` and generic message | Do not distinguish non-existent user / locked / wrong password on public interfaces |
| Authenticated successfully but lacking resource permissions | `403 Forbidden` | This is an **authorization** error, not an LDAP bind failure |
| LDAP/AD temporarily unavailable, timeout, connection error | `503 Service Unavailable` when outage is identifiable | Requires a dedicated API handler; default Spring Security does not necessarily pick 503 |
| Misconfigured truststore, service bind, or unrecoverable bug | `500` or `503` per operational policy | Never leak exception internals, cert DNs, or secrets to clients |

**Security invariant:** If the directory cannot verify identity, never issue a JWT, never create a security session, never fall back to a default principal, and never "temporarily allow" logins to preserve uptime. That is the **fail closed** principle. The system must separate user-facing messages from operations-accessible logs.

## 9. Exception classification pattern at the Spring Security boundary

This is a helper for a specific LDAP authentication flow. It classifies common Spring Security exceptions; it is **not** an adapter catching every JNDI error across all configurations, so you must still verify `cause` and bind stages in integration tests.

~~~java
package demo.ldap;

import org.springframework.security.authentication.AccountStatusException;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

public final class LdapFailurePolicy {

    public enum Category {
        CREDENTIAL_REJECTED,
        ACCOUNT_RESTRICTED,
        DIRECTORY_SERVICE_ERROR,
        UNKNOWN
    }

    private LdapFailurePolicy() {
    }

    public static Category classify(AuthenticationException error) {
        if (error instanceof AccountStatusException) {
            return Category.ACCOUNT_RESTRICTED;
        }
        if (error instanceof BadCredentialsException
                || error instanceof UsernameNotFoundException) {
            return Category.CREDENTIAL_REJECTED;
        }
        if (error instanceof AuthenticationServiceException) {
            return Category.DIRECTORY_SERVICE_ERROR;
        }
        return Category.UNKNOWN;
    }
}
~~~

Boundary notes:

- `InternalAuthenticationServiceException` falls under `AuthenticationServiceException`; however, higher-level exception types also depend on the active authentication provider. Before sending an HTTP response, callers must examine the **failure context and actual cause**.
- When a custom provider wraps network errors improperly in `BadCredentialsException`, classification becomes inaccurate. Fix it at the provider/adapter where the processing stage is still known, rather than patching by string-matching error messages.
- Never use `exception.getMessage()` or LDAP diagnostic text as a user-facing message; it may contain DNs, server names, or AD subcodes. Keep a stable internal error code and correlation ID with controlled log access.
- Never catch every `RuntimeException` and convert it into `BadCredentialsException`. Doing so masks production incidents and makes outages hard for monitoring to detect.
- The helper is a **code snippet inside a Spring Security project**, not runnable standalone with `javac` without the corresponding dependencies. Real code paths still need an authentication failure handler/entry point for Servlet or WebFlux to return HTTP statuses per policy.

## 10. Standalone Java 17 example: testing LDAPS bind with timeouts

When you need to isolate TLS, network path, and credentials from Spring configuration, you can run a small JDK program. **Its sole purpose is controlled bind probing**, not a login API and not testing multiple usernames/passwords.

File `LdapsProbe.java`:

~~~java
import java.net.URI;
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;

public final class LdapsProbe {

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment variable: " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        String url = required("LDAP_URL");
        if (!"ldaps".equalsIgnoreCase(URI.create(url).getScheme())) {
            throw new IllegalArgumentException("LDAP_URL must use ldaps://");
        }

        Hashtable<String, String> environment = new Hashtable<>();
        environment.put(Context.INITIAL_CONTEXT_FACTORY,
                "com.sun.jndi.ldap.LdapCtxFactory");
        environment.put(Context.PROVIDER_URL, url);
        environment.put(Context.SECURITY_AUTHENTICATION, "simple");
        environment.put(Context.SECURITY_PRINCIPAL, required("LDAP_BIND_DN"));
        environment.put(Context.SECURITY_CREDENTIALS, required("LDAP_BIND_PASSWORD"));
        environment.put("com.sun.jndi.ldap.connect.timeout", "2000");
        environment.put("com.sun.jndi.ldap.read.timeout", "3000");

        DirContext context = null;
        try {
            context = new InitialDirContext(environment);
            System.out.println("LDAPS bind: OK");
        } catch (NamingException ex) {
            System.err.println("LDAPS bind: FAILED ("
                    + ex.getClass().getSimpleName() + ")");
            System.exit(2);
        } finally {
            if (context != null) {
                try {
                    context.close();
                } catch (NamingException ignored) {
                    // Ignore context close error in this simple check utility.
                }
            }
        }
    }
}
~~~

Compile/run (JDK 17+, no Spring dependencies needed):

~~~bash
javac LdapsProbe.java
java LdapsProbe
~~~

Before running, **supply the three environment variables `LDAP_URL`, `LDAP_BIND_DN`, and `LDAP_BIND_PASSWORD` from a secure secret store**, targeting an authorized test endpoint with a CA trusted by the JVM. Valid URL example: `ldaps://dc01.corp.example.test:636`. On a successful bind, exact stdout is:

~~~text
LDAPS bind: OK
~~~

If the bind fails, stderr has the form `LDAPS bind: FAILED (<ExceptionName>)`, such as `CommunicationException` or `AuthenticationException`; the exception name depends on the actual root cause, so no fixed failure stdout is promised. Omitting the message/cause is intentional to avoid writing DNs and sensitive data to operator logs. If environment variables are missing, the program terminates with a configuration error before opening a connection.

This program only proves TLS connectivity and **binding a specific account**; it does not test search filters, user bind, group authorization, retries, SLAs, or `SecurityFilterChain`. Never test batches of passwords or real accounts outside authorized operational scenarios.

## 11. Observability, alerting, and incident handling strategies

Track metrics with bounded-cardinality labels:

- `ldap_auth_success_total`, `ldap_auth_reject_total`, `ldap_infra_error_total`; keep *account rejected* separate from *service unavailable*.
- Bind/search/group-lookup latency, p50/p95/p99; timeout rate; thread/connection pool saturation; TLS handshake failure count.
- Internally identified directory endpoint, deployment environment, step type (`service_bind`/`user_bind`/`search`), and correlation ID.
- Rate-limit hits and lockouts (under internal policy); never attach raw passwords, tokens, or usernames as metric labels.

When diagnostic logs are needed, log the classified error category and request ID at info level; deeper TLS/LDAP details (DNs, DCs, detailed error codes) belong only in access-controlled operational channels with data masking. Never leave protocol tracing or JNDI BER tracing enabled long-term in production.

**Retries:** Consider bounded retries with backoff + jitter for certain transient connection errors if request time budget remains and it will not trigger a load storm. Never automatically retry when LDAP returns bad password or account locked; repeating failed binds can lock out accounts. With a multi-DC load balancer, avoid failing over to another DC without verifying its corresponding certificate/trust. Investigate whether retrying a bind operation affects AD's account lockout policy.

**Failover:** Having multiple LDAP URLs or multiple DCs provides resilience when one node drops, but does not solve domain-wide DNS failures, wrong CA/truststore, expired service passwords, or simultaneous overload across all nodes. With multiple endpoints, wait times can accumulate; verify actual paths and timeouts before claiming SLA compliance.

## 12. Symptom-based incident response workflow

| Symptom | Priority checks | Remediation direction |
| --- | --- | --- |
| Worked previously; after certificate rotation all requests fail | Java truststore, CA chain, SAN/FQDN, certificate validity window | Update truststore/certificate and roll out cleanly; **never disable hostname check** |
| Only one DC fails while others are fine | That DC's certificate and DNS, network path, TLS port | Drain the failing node per runbook, fix the DC, and verify failover |
| All users fail to log in simultaneously with `CommunicationException` | DNS/firewall/routing, TLS, LDAP server state, connect/read timeouts | Declare outage, do not blame accounts; do not issue tokens |
| Only service DN search fails after credential rotation | New bind DN/secret, service account status/ACLs, restart/reload | Fix config and permissions; ensure secrets are not leaked |
| One user has wrong password while others succeed | User bind error `49`, internal AD subcode, lockout policy | Return generic message, audit appropriately, and follow separate recovery flow |
| Connects successfully yet search finds no user | Base DN, OU, filter, read permissions, account type, referrals | Fix search policy; never treat `noSuchObject` as a wrong password |
| Traffic spike drives login p99 sharply higher | Connection counts, threads, LDAP backend, retry storms, timeouts | Shed/limit load, optimize lookups/appropriate caching, tune pools after benchmarking |

During a real incident, identify **which layer failed**: handshake/TCP → service bind → user search → user bind → groups/authorities → session/token. Never jump straight to "user entered wrong password" just because the overall login endpoint returned an error.

## 13. Mandatory testing before production

Integration tests can be structured using a test directory or AD staging environment with test accounts and intentionally created scenarios:

| Test | Expected result |
| --- | --- |
| Valid CA/hostname + valid credentials | Authentication succeeds with right principal/authorities |
| Wrong user password | No token/session issued; generic response; classified as credential rejection |
| Non-existent user | Login denied; public message does not enable clear user enumeration |
| Locked/disabled/password-expired user on AD | No session issued; internally classified per actual provider/subcode |
| Wrong, locked, or ACL-missing service account password | Classified as service/config error, not attributed as wrong password for all users |
| Expired certificate, untrusted CA, or SAN mismatch | TLS handshake fails; **no downgrade and no bind attempt** |
| LDAP port blocked or server unresponsive | Bounded connect/read timeout, controlled infrastructure error response |
| One of multiple DCs fails | Routes per policy, verifies TLS on backup DC and overall deadline |
| Directory returns `busy`/`unavailable` | Login disallowed; bounded retry/backoff, operational alert |
| 100+ concurrent logins in authorized load test | No unexpected thread/connection exhaustion; p95/p99 and rejections measured |
| Login cancelled, browser closes connection | No session/token created when outcome not accepted; resources released per library capabilities |
| Post-test log/trace/metric scan | Zero user passwords, service secrets, access tokens, or sensitive LDAP diagnostics exposed |

With Spring Security Servlet, run `MockMvc`/HTTP integration tests to verify authentication entry points, success/failure handlers, and response semantics. With WebFlux, use `WebTestClient` and verify blocking LDAP client offloading on the scheduler. Unit tests on an error-classification helper cannot replace real TLS connection and LDAP provider tests.

## 14. Operational configuration checklist

- [ ] Connect only to approved LDAP/AD FQDNs/ports; LDAPS or StartTLS is **verified** before transmitting passwords.
- [ ] Valid truststore, complete CA chain, SAN matching hostname; no trust-all, disabled endpoint identification, or fallback to cleartext.
- [ ] Service account has least privilege, secrets injected at runtime, with rotation/expiry monitoring; user passwords never stored/logged.
- [ ] Positive connect/read timeouts properly configured in JNDI; HTTP deadline, multiple operations, referrals, and failover measured.
- [ ] All TLS, timeout, network, provider, and service-bind failures **fail closed** and return no session/token.
- [ ] Distinguish `BadCredentialsException`/account status from `AuthenticationServiceException`; never rely solely on exception messages.
- [ ] Frontend/API never leaks account enumeration or AD subcodes; logs/metrics have access control and data masking.
- [ ] Tested wrong passwords, locked accounts, invalid certs, expiry, DC loss, delays, secret rotation, ACL errors, and concurrent load.
- [ ] Incident response assigns owners for directory, secrets, TLS, and application; audit records are sufficient for incident investigation.

**Main takeaway:** LDAPS/StartTLS secures the channel when **verifying the right endpoint**; secret management and timeouts are independent mandatory controls. Account errors are authentication rejections by the directory; infrastructure errors mean **identity could not be verified yet**. Both cases must deny access, yet must be classified, recorded, and responded to differently to remain both secure and operable.

## Official documentation and cross-references

- [Spring Security 6.5 — LDAP Authentication](https://www.springframework.org/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html)
- [Spring Security — ActiveDirectoryLdapAuthenticationProvider API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html)
- [Spring LDAP — Configuration, ContextSource, TLS](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Java SE 21 — java.naming module and JNDI LDAP timeouts](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/module-summary.html)
- [OWASP — Authentication Cheat Sheet: Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [Oracle Java 8u181 release notes — LDAPS endpoint identification](https://www.java.com/en/download/help/release_changes.html)

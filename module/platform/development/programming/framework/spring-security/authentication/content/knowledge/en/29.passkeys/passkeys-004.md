# Relying Party ID, allowed origins, and HTTPS requirements in Passkey/WebAuthn

## 1. Problem: why can a passkey work on one domain yet fail on another?

A Spring Security application supports **passkeys** so users can sign in with WebAuthn/FIDO2. During registration, the authenticator generates a key pair; the server stores the public key and credential metadata. During authentication, the authenticator signs challenge data and the server verifies the signature. No shared password is sent over the network as in traditional login.

Suppose the website is served at `https://login.example.com`, while the backend runs behind a reverse proxy at `http://passkey-service:8080`. A secure passkey configuration must answer three questions:

1. **What is the Relying Party ID (RP ID)?** For instance, `example.com` or `login.example.com`. The RP ID defines the credential's domain scope.
2. **What are the allowed origins?** For instance, only `https://login.example.com`; these are the specific origins permitted by the server to execute WebAuthn ceremonies.
3. **Does the page have a secure context?** In production, the page must be served over HTTPS with a valid certificate; HTTP `localhost` has an exception for local development.

If the RP ID is invalid, the browser may reject immediately with `SecurityError`. If the browser allows creating an assertion but the `origin` is not trusted by the server, the backend must reject it. If TLS/forwarded host is misconfigured, registration and authentication can fail even when the Java signature-verification code is right.

**Learning objectives:** distinguish RP ID, origin, and URL; design for multiple subdomains/ports; configure Spring Security 6.5's `HttpSecurity.webAuthn()`; understand `rpIdHash` and `clientDataJSON.origin`; test localhost/HTTPS; resolve host mismatches caused by reverse proxies and domain migrations without disabling security checks.

## 2. Four actors in WebAuthn

| Actor | Role | Related information |
| --- | --- | --- |
| **End user** | Requests registration/login; interacts via biometric/PIN when the authenticator needs it | The user never needs to know the private key |
| **Browser/WebAuthn client** | Executes `navigator.credentials.create/get`, enforces origin and RP ID limits | Active page origin, challenge, requested RP ID |
| **Authenticator/passkey provider** | Generates/stores/uses credentials and signs data | Private key, `authenticatorData`, `rpIdHash`, UP/UV flags |
| **Relying Party server** | Issues challenges, stores public keys, verifies responses, issues session upon valid auth | Configured RP ID and allowed origins, public key, credential ID/account binding |

A WebAuthn server may run across multiple instances or behind a proxy; **the RP ID is not the JVM/container's hostname**. The browser sees the public address; that is what determines the origin calling the API.

Diagram:

~~~text
User / Browser at https://login.example.com
    |
    | GET/POST WebAuthn options and response over HTTPS
    v
Reverse proxy / TLS termination
    |
    | Internal HTTP only when the trust boundary permits
    v
Spring Security WebAuthn RP
    |
    +-- RP ID: example.com
    +-- allowed origins: https://login.example.com
    +-- credential public keys, challenge/session, user mapping
~~~

## 3. RP ID is a domain string, not a full URL

The **RP ID** is the domain to which a credential is bound under WebAuthn rules. It **does not contain** an `https://` scheme, port, path, query, fragment, or wildcard.

~~~text
Valid:   example.com
Valid:   login.example.com
Lab:     localhost

Invalid: https://example.com
Invalid: login.example.com:443
Invalid: https://login.example.com/login
Invalid: *.example.com
Invalid: com
Invalid: co.uk
~~~

Under standard WebAuthn rules, the RP ID must **equal the calling origin's effective domain**, or be a valid **registrable domain suffix** of that effective domain. You cannot pick a public suffix like `com` or `co.uk`. Distinguishing public suffixes from registrable domains in practice requires proper public suffix data/policy—never guess by counting dots.

### 3.1. Concrete examples with subdomains

Suppose the browser is at `https://login.example.com:8443`:

| RP ID | Valid under standard rules? | Reason |
| --- | --- | --- |
| `login.example.com` | Yes | Equals the origin's host |
| `example.com` | Yes | Registrable domain suffix |
| `m.login.example.com` | No | It is a **deeper subdomain**, not a suffix |
| `app.example.com` | No | Sibling hostname, not a suffix of `login.example.com` |
| `evil-example.com` | No | Merely looks similar as a string; not the same domain |
| `com` | No | Public suffix |
| `https://example.com` | No | Invalid RP ID format |

If you pick `rpId=example.com`, both `login.example.com` and `app.example.com` could request credentials for that RP ID, but this **does not automatically** mean the server should trust both origins. The server-side origin allowlist is an independent check.

**Do not arbitrarily match domains with `host.endsWith("example.com")`**: `evil-example.com` could match a naive suffix check in buggy handlers. RP ID enforcement must rely on standard WebAuthn/browser libraries and approved domain policies.

### 3.2. Do not accidentally open scope to tenant/preview hosts

If your organization owns `example.com` while subdomains like `preview.example.com`, `customer-123.example.com`, or `blog.example.com` are operated by different teams/customers, choosing the parent RP ID has security implications. Malicious script on an untrusted subdomain could attempt to initiate a WebAuthn ceremony for the parent RP ID if browser eligibility allows it. **The server must block origins outside the allowlist**, and you must also manage XSS/supply-chain security on allowed origins.

If only one hostname uses passkeys, a narrow RP ID like `login.example.com` is easier to govern. If you need to share credentials across multiple subdomains, choose `example.com` intentionally and restrict the allowlist.

## 4. Origin is the scheme + host + port triple

An **Origin** identifies the source of the page calling WebAuthn. The following origins are distinct:

~~~text
https://login.example.com
https://login.example.com:8443
https://app.example.com
http://login.example.com
~~~

There is no `/login` or `/settings/security` path in an origin. When using default ports, browsers typically normalize `https://login.example.com:443` to `https://login.example.com`. Allowed origins configuration should use canonical origin form, not string-concatenated URL paths.

For example, suppose the server wants to allow only:

~~~text
RP ID: example.com
Allowed origins:
  https://login.example.com
  https://app.example.com
~~~

The server must reject:

~~~text
https://evil.example.com
https://preview.example.com
http://login.example.com
https://login.example.com:8443    # unless port 8443 is explicitly approved
~~~

Port is a critical detail: **RP ID has no port, whereas origin does**. If you change the frontend port from 443 to 8443, you may need to update allowed origins even though the RP ID stays unchanged.

### 4.1. Allowed origins ≠ CORS ≠ cookie domain

- **WebAuthn allowed origins:** the server only accepts `origin` in WebAuthn client data for approved sites.
- **CORS:** browser rules allowing JavaScript on origin A to read/send certain HTTP requests to B; does not verify WebAuthn assertions.
- **Cookie Domain/SameSite:** cookie distribution and CSRF risk-reduction mechanisms; does not define RP ID or prove signatures.
- **HTTP Origin header:** useful for certain request protections, but does not replace verifying `clientDataJSON.origin` in WebAuthn.

Do not fix origin mismatches with `Access-Control-Allow-Origin: *` or wildcard allowed origins. Never allow the client to pass an arbitrary origin and have the server dynamically add it to the allowlist.

## 5. Cryptographic mechanism binding credentials to RP ID and origin

Inside `authenticatorData`, the **32-byte** `rpIdHash` field is computed as:

~~~text
rpIdHash = SHA-256(UTF-8(RP ID))
~~~

With RP ID `example.com`, the server expects the hash of the exact string `example.com`; not the hash of `https://example.com` or `https://login.example.com` unless the chosen RP ID is `login.example.com`.

For authentication, the authenticator signs data involving `authenticatorData` and the hash of `clientDataJSON`. `clientDataJSON` contains fields such as `type`, `challenge`, `origin`, and potentially cross-origin info. The server must verify all of the following together:

1. **Type:** `webauthn.get` for login; `webauthn.create` for registration.
2. **Challenge:** matches the random challenge issued by the server for that exact transaction and is single-use.
3. **Origin:** strictly belongs to the RP's allowed origins set.
4. **RP ID hash:** `rpIdHash` matches the server's configured RP ID.
5. **Signature:** valid under the registered credential's public key; not a client-asserted value.
6. **Flags:** UP (user presence) and UV (user verification) per required policy.
7. **Credential/user mapping:** credential ID and user handle map to the right account, never crossing over to someone else.
8. **Lifecycle/replay:** challenge expiration, state, sign counter (when meaningful), and other spec constraints.

**Two separate checks:** RP ID defines **credential scope**, while origin identifies **the website invoking the ceremony**. An assertion with a valid RP ID hash whose origin came from a preview host not on the allowlist **must be rejected**.

Never Base64URL-decode `clientDataJSON` yourself, see a matching `origin` field, and conclude login is valid. You must use a maintained server WebAuthn library because of signatures, parsers, bindings, and anti-spoofing countermeasures.

## 6. HTTPS and secure context

WebAuthn is a **secure context** API. In standard web deployments:

| Browser address | Assessment |
| --- | --- |
| `https://login.example.com`, valid certificate | Suitable for production |
| `http://login.example.com` | Unsuitable: lacks secure context |
| `http://localhost:8080` | Common exception for local WebAuthn development |
| `https://localhost:8443` | Secure context if TLS/cert is trusted by the browser |
| `http://192.168.1.20:8080` | Not treated as equivalent to `localhost` by default |
| `http://app.internal` | Do not use for real browser WebAuthn deployments |

Some browsers treat loopback addresses, `.localhost`, or authenticated schemes as *potentially trustworthy*. However, a **general secure context** is not synonymous with a **valid WebAuthn RP ID in every browser**. For reproducible learning, use `http://localhost:<port>` and RP ID `localhost`. Production must have HTTPS and a controlled domain.

### 6.1. Checking from DevTools

Open the exact page calling passkeys and run:

~~~javascript
console.log(window.location.origin);
console.log(window.isSecureContext);
console.log(typeof PublicKeyCredential !== "undefined");
~~~

Example in a supported browser at `http://localhost:8080`:

~~~text
http://localhost:8080
true
true
~~~

This is the expected output for a supported browser, not guaranteed across all devices/managed policies. `isSecureContext=true` alone does not prove that RP ID/allowed origins/signatures are all correct.

**HTTPS in production:** expose endpoints over TLS, use certificates matching the hostname, block HTTP downgrades, consider HSTS, protect cookies/sessions with `Secure`/`HttpOnly`/`SameSite`, and defend against XSS. Passkeys help prevent phishing via origin/RP constraints, but do not replace these layers.

## 7. RP ID and allowed origin matrix

| Page calling WebAuthn | RP ID | Allowed origin | Outcome |
| --- | --- | --- | --- |
| `https://login.example.com` | `login.example.com` | `https://login.example.com` | Valid |
| `https://login.example.com` | `example.com` | `https://login.example.com` | Valid |
| `https://app.example.com` | `example.com` | `https://app.example.com` | Valid if approved by server |
| `https://login.example.com:8443` | `example.com` | `https://login.example.com:8443` | Valid if this port is approved |
| `https://login.example.com:8443` | `example.com` | Only `https://login.example.com` | Server rejects |
| `http://login.example.com` | `example.com` | `http://login.example.com` | Fails HTTPS requirement |
| `http://localhost:8080` | `localhost` | `http://localhost:8080` | Valid for local lab |
| `http://localhost:8081` | `localhost` | Only `http://localhost:8080` | Different origin; server rejects |
| `https://login.other.net` | `example.com` | `https://login.other.net` | Browser normally rejects under suffix rule |
| `https://login.example.com` | `com` | `https://login.example.com` | Invalid RP ID due to public suffix |

When an allowed origin is HTTPS on the default port, do not arbitrarily append `:443` if the browser reports a normalized portless origin. When moving from local HTTP to HTTPS staging, update allowed origins to the exact scheme/hostname.

## 8. Spring Security 6.5 and Spring Boot 3.5.x example

Spring Security 6.5.x provides the Servlet DSL `HttpSecurity.webAuthn(...)` with `rpId(...)` and `allowedOrigins(...)`. To keep code consistent, the example uses **Spring Boot 3.5.7** (Java 17+, Spring Security 6.5 line). Do not take a Spring Boot 3.3.x/Spring Security 6.3.x project and expect `webAuthn()` to exist automatically.

### 8.1. Project file structure

~~~text
passkey-local-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/passkey/
    │   ├── PasskeyApplication.java
    │   └── SecurityConfig.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'passkey-local-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Security 6.5 documentation requires `webauthn4j-core`; Spring Security 7 has a different dependency model (such as the `spring-security-webauthn` artifact)—verify the exact version before using it.

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
~~~

`src/main/java/demo/passkey/PasskeyApplication.java`:

~~~java
package demo.passkey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasskeyApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasskeyApplication.class, args);
    }
}
~~~

`src/main/java/demo/passkey/SecurityConfig.java`:

~~~java
package demo.passkey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .webAuthn(webAuthn -> webAuthn
                        .rpName("Local Passkey Lab")
                        .rpId("localhost")
                        .allowedOrigins("http://localhost:8080"))
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("demo")
                        .password(encoder.encode("demo-only-password"))
                        .roles("USER")
                        .build());
    }
}
~~~

This is a configuration for a **local lab**:
- `rpId("localhost")` is a domain string without a port.
- `allowedOrigins("http://localhost:8080")` includes the exact scheme and port.
- `formLogin()` provides a way to establish a session with a test password before registering a passkey.
- WebAuthn registration/login is provided by Spring Security; assertion verification must be performed by the library, not a hand-rolled controller.
- Default user/credential repositories may be **in-memory**, unsuitable for storing passkeys in production.

Run in the project directory with Gradle or its wrapper:

~~~bash
gradle bootRun
# If the project has a wrapper: ./gradlew bootRun
~~~

Open exactly `http://localhost:8080`, log in with `demo` / `demo-only-password`, then open the registration page at `/webauthn/register` in a WebAuthn-capable browser. Do not switch to `http://127.0.0.1:8080` as the hostname/origin will differ. In-memory data is not preserved after restart.

Per Spring Security docs, core endpoints include `POST /webauthn/register/options`, `POST /webauthn/register`, `POST /webauthn/authenticate/options`, and `POST /login/webauthn`. These POSTs carry state/challenges and must enforce CSRF by design—never disable CSRF recklessly.

### 8.2. Production: one RP ID and two trusted origins

This is a configuration snippet **illustrated inside a Spring Security 6.5 `SecurityFilterChain`**, not a standalone Java program:

~~~java
http.webAuthn(webAuthn -> webAuthn
        .rpName("Example Identity")
        .rpId("example.com")
        .allowedOrigins(
                "https://login.example.com",
                "https://app.example.com"));
~~~

Only add origins you genuinely own, control, and authorize to run ceremonies. If the website only logs in at `login.example.com`, allow **only** `https://login.example.com`. Never add `https://preview.example.com`, `http://login.example.com`, or `https://*.example.com`.

If the browser is on `https://app.example.com` while the RP ID is configured as `login.example.com`, server-side allowed origins **cannot** force the browser to permit an RP ID that violates the suffix rule.

### 8.3. Persistence and session management

Per Spring Security 6.5, WebAuthn persistence uses `PublicKeyCredentialUserEntityRepository` and `UserCredentialRepository`. The demo defaults to in-memory; production requires a persistent credential store (such as the JDBC repositories supported by Spring Security) plus backup/revocation policies. When deploying across multiple nodes, ensure challenges, sessions, CSRF, caches, and user mappings behave consistently.

A passkey is linked to an account by credential ID/public key/user handle. Never auto-create a new internal account just because the browser returns a username matching an email; dedicated account-linking and authorization rules are required.

## 9. What do registration and authentication check?

### 9.1. Registration (credential creation)

The server builds `PublicKeyCredentialCreationOptions` including `rp.id`, user handle, challenge, algorithms, and policy:

~~~json
{
  "rp": { "name": "Example Identity", "id": "example.com" },
  "user": {
    "id": "BASE64URL_USER_HANDLE",
    "name": "demo@example.com",
    "displayName": "Demo User"
  },
  "challenge": "BASE64URL_FRESH_CHALLENGE",
  "pubKeyCredParams": [{ "type": "public-key", "alg": -7 }],
  "attestation": "none"
}
~~~

The `BASE64URL_*` strings here are **illustrative placeholders**, not valid WebAuthn values to submit. Spring Security generates the challenge, selects algorithms, and retains appropriate state. The browser converts binary fields to `ArrayBuffer` and calls `navigator.credentials.create({ publicKey: ... })`.

The browser checks RP ID. The authenticator creates a credential scoped to the RP ID. The server verifies the registration response/challenge/origin/`rpIdHash` and other policies **before** saving the public key.

### 9.2. Authentication (using a credential)

The server sends `PublicKeyCredentialRequestOptions` with `rpId` and challenge:

~~~json
{
  "challenge": "BASE64URL_FRESH_CHALLENGE",
  "rpId": "example.com",
  "timeout": 120000,
  "userVerification": "preferred",
  "allowCredentials": []
}
~~~

The browser calls `navigator.credentials.get({ publicKey: ... })`. If the device holds a credential for the right RP ID and the user consents, the server receives an assertion. Inside the decoded `clientDataJSON` you may see:

~~~json
{
  "type": "webauthn.get",
  "challenge": "BASE64URL_FRESH_CHALLENGE",
  "origin": "https://login.example.com",
  "crossOrigin": false
}
~~~

These fields **do not self-authenticate** when you merely parse JSON. The server must still verify the cryptographic signature, challenge, `rpIdHash`, flags, `userHandle`, and matching key. If embedded/cross-origin contexts are needed, evaluate `crossOrigin`/`topOrigin` and permissions policy per the spec.

### 9.3. Confusion between browser checks and server checks

For example, `https://preview.example.com` with RP ID `example.com`: the browser may accept the suffix rule. However, when the server only allows `https://login.example.com`, **assertions from preview must be rejected**.

Conversely, `https://login.other.net` cannot use RP ID `example.com` by default simply by adding the origin to the server allowlist. That requires a domain architecture solution or client-supported Related Origin Requests—there is no backend-only shortcut.

## 10. Standalone Java 17: distinguishing RP ID and origin allowlist

The sample below checks an **allowlist policy against simulated data**. It is **not** a WebAuthn verifier; it does not check the Public Suffix List, signatures/challenges, or data provenance. The goal is to show that sharing an RP ID does not automatically allow every subdomain.

Create `PasskeyOriginPolicyDemo.java`:

~~~java
import java.util.List;
import java.util.Set;

public final class PasskeyOriginPolicyDemo {
    private static final String RP_ID = "example.com";
    private static final Set<String> ALLOWED_ORIGINS = Set.of(
            "https://login.example.com",
            "https://app.example.com");

    record Scenario(String name, String origin, String rpId) {}

    static boolean accepts(Scenario scenario) {
        return RP_ID.equals(scenario.rpId())
                && ALLOWED_ORIGINS.contains(scenario.origin());
    }

    public static void main(String[] args) {
        List<Scenario> cases = List.of(
                new Scenario("Login", "https://login.example.com",
                        "example.com"),
                new Scenario("App", "https://app.example.com",
                        "example.com"),
                new Scenario("Preview", "https://preview.example.com",
                        "example.com"),
                new Scenario("HTTP", "http://login.example.com",
                        "example.com"),
                new Scenario("Other port", "https://login.example.com:8443",
                        "example.com"),
                new Scenario("Different RP", "https://login.example.com",
                        "login.example.com"));

        for (Scenario scenario : cases) {
            System.out.println(scenario.name() + ": "
                    + (accepts(scenario) ? "ALLOW" : "DENY"));
        }
    }
}
~~~

Compile and run:

~~~bash
javac PasskeyOriginPolicyDemo.java
java PasskeyOriginPolicyDemo
~~~

**Exact** stdout:

~~~text
Login: ALLOW
App: ALLOW
Preview: DENY
HTTP: DENY
Other port: DENY
Different RP: DENY
~~~

**Important:** this program only simulates **known** strings. Never run `accepts(Scenario)` on self-reported network strings to grant login sessions; a production server must use a WebAuthn library, verified `clientDataJSON`, and a fixed server-configured RP ID. Validating origin does not replace signature verification.

## 11. Reverse proxy and public address

Topology:

~~~text
Browser: https://login.example.com
    |
    | HTTPS
    v
Gateway/TLS terminator
    |
    | http://passkey-app:8080 (internal upstream)
    v
Spring Security
~~~

WebAuthn configuration must reflect the **public browser context**:

~~~text
rpId = example.com
allowedOrigins = [https://login.example.com]
~~~

Never set `rpId=passkey-app` or `allowedOrigins=http://passkey-app:8080` when users do not access the page at that hostname.

If the backend generates redirects with the wrong scheme/host (for instance, redirecting to `http://...`):
- Review TLS termination and Spring Boot forwarded-header handling.
- Only trust `Forwarded`/`X-Forwarded-*` from authenticated/controlled gateways, never from user-supplied requests.
- Configure the public base URL and allowlist from deployment config, rather than inferring from untrusted request headers.
- Verify HTTPS from client to edge and protection on the edge→service hop.

A host poisoning attack can alter `Host` or `X-Forwarded-Host` if the proxy does not sanitize them. Never resolve that error by adding the received host to WebAuthn allowed origins.

## 12. Multiple origins on the same domain vs. different domains

### 12.1. Same registrable domain

`https://login.example.com` and `https://app.example.com` can share RP ID `example.com`, yet they are two different origins. If both need to run ceremonies, you must approve and govern the security posture of each site. CSP, XSS protection, third-party scripts, sessions, and account recovery all affect security.

If a credential was created under `rpId=login.example.com`, do not assume `app.example.com` can use it automatically. To support both subdomains, a shared RP ID must be chosen upfront or a centralized login design should be used.

### 12.2. Related Origin Requests (ROR) for different domains

WebAuthn Level 3 (2026 W3C Recommendation) supports **Related Origin Requests** on WebAuthn clients that implement the feature. An RP can list related origins in JSON served **over HTTPS** at:

~~~text
https://example.com/.well-known/webauthn
~~~

Example:

~~~json
{
  "origins": [
    "https://example.co.uk",
    "https://example.net"
  ]
}
~~~

Key points to remember:
1. The file must reside on the **RP ID's** domain and be controlled by the RP; use `Content-Type: application/json`.
2. Supporting browsers can consult this file when an origin fails the default suffix rule; unsupported browsers may still reject with `SecurityError`.
3. The server must still validate `clientDataJSON.origin` against its own policy using the expected RP ID—never trust arbitrary Internet domains.
4. This is not CORS, not a wildcard, and does not prove domain ownership merely by listing a name in JSON.
5. You must consider brand-confusion/phishing risks, domain lifecycle, and browser/OS compatibility.

If your architecture spans multiple domains without needing browsers on every domain to call WebAuthn directly, a **centralized login origin** paired with appropriate sessions/SSO is often simpler.

## 13. Changing the RP ID after issuance

Passkeys are created within the scope of the chosen RP ID. Changing `rpId("login.example.com")` to `rpId("example.com")` or vice versa is **not just editing a URL config**; the authenticator/server must operate under the RP ID to which the credential is bound. Users may need to re-register their passkeys.

Migration process:
1. Inventory current RP IDs, credential counts, active login origins, and domains under your control.
2. Choose a long-term RP ID with clear tenant/subdomain policies.
3. Prepare a flow to register new passkeys within an authenticated session or a protected account recovery method.
4. If parallel operation is needed, isolate RP deployments and explicitly govern credential stores/issuers/domains—**never disable `rpIdHash`/origin verification**.
5. Plan user communications, revocation of old credentials, metadata backups, and incident handling.
6. Test in staging with test credentials before rollout.

Changing **allowed origins** under the same RP ID may not require re-registering credentials, provided the browser permits the domain and the backend allows that origin. Changing the **RP ID** alters the cryptographic scope.

## 14. Browser and Spring Security test matrix

| Scenario | Expected outcome |
| --- | --- |
| Local `http://localhost:8080`, RP ID `localhost`, origin allowed | Ceremony can run in supported browsers |
| Production `https://login.example.com`, RP ID `example.com` | Valid if server allows origin and response is cryptographically valid |
| RP ID written as `https://example.com` | Browser/server rejects due to invalid format |
| RP ID is `com` | Rejected because it is a public suffix |
| `http://login.example.com` on the Internet | Not a WebAuthn secure context |
| `https://preview.example.com` uses RP ID `example.com` without origin allowed | **Server rejects** |
| `https://login.example.com:8443` not explicitly allowed | **Server rejects** due to different port |
| Challenge altered/expired/reused | Rejected |
| `rpIdHash` differs from configured RP ID | Rejected |
| Signature mismatches public key | Rejected |
| User handle/credential not bound to account | Never auto-logs in to another account |
| `crossOrigin=true` from unapproved iframe | Rejected per policy |
| HTTP `localhost` switched to `127.0.0.1` | Do not assume both origins/RP IDs are equivalent |
| Proxy produces `http://internal-service` address | Fix trusted forwarding/base URL, never loosen allowed origins |
| Changing production origin to another domain | Design ROR/central login origin or migration, never bypass |

**Testing levels:**
- **Unit:** policy/origin allowlist and configuration.
- **Integration:** WebAuthn handlers/repositories/challenges/sessions and valid/invalid signed test responses.
- **Browser E2E:** real registration/authentication with virtual authenticators or test devices over HTTPS/localhost across supported browsers and OSes.

`MockMvc` returning `200` on an endpoint does not prove passkey verification works unless the test produces a validly signed WebAuthn assertion. Tests must include negative cases and verify the exact principal.

### Troubleshooting

| Error/symptom | What to check |
| --- | --- |
| Browser throws `SecurityError` before calling server | Domain suffix, RP ID syntax, HTTPS/secure context, browser support |
| `window.isSecureContext=false` | Scheme/host/TLS |
| Server reports origin mismatch | `clientDataJSON.origin` vs. allowlist scheme/host/port |
| `rpIdHash` mismatch | RP ID differs between registration/authentication or migration |
| Passkeys lost after demo restart | In-memory credential repository |
| Registration returns 403 | Session/CSRF/endpoint authorization |
| One subdomain cannot log in | RP ID scope and allowlist, not default CORS |
| Only seeing internal HTTP backend URL | Check public origin through the proxy |
| Cross-domain ROR fails to run | Browser support, `/.well-known/webauthn`, RP ID/allowed origin |

Do not log raw assertions, key material, or sensitive challenges for debugging. Use request/correlation IDs, error types, and redacted configuration.

## 15. Mistakes to avoid

1. "RP ID is a URL." **False:** it is only a domain, with no scheme/port/path.
2. "Setting RP ID to the parent domain means every subdomain is trusted by the server." **False:** the server needs an explicit origin allowlist.
3. "Ports don't matter." **False:** origins include ports even though RP IDs do not.
4. "With HTTPS, origin checks aren't needed." **False:** HTTPS secures the transport channel, not policy.
5. "CORS allowlist is the same as WebAuthn allowed origins." **False:** the two controls serve different purposes.
6. "The browser checked RP ID, so the backend can skip `rpIdHash`." **False:** the backend must verify it.
7. "Parsing JSON and seeing the right `origin` means login is valid." **False:** challenge/signature/flags are still required.
8. "`http://staging.internal` works like `http://localhost`." **False:** no such broad WebAuthn exception exists.
9. "Adding any domain to `allowedOrigins` lets browsers share credentials there." **False:** browsers enforce suffix rules or ROR mechanisms.
10. "You can change RP ID freely without affecting passkeys." **False:** credential scope changes.
11. "`login.example.com` and `app.example.com` are the same origin." **False:** different hostnames.
12. "Visiting `127.0.0.1` is identical to `localhost`." **False:** different hostname/origin; browser policies must be verified.
13. "With passkeys, you can remove CSRF/XSS controls." **False:** registration, sessions, and account recovery still require protection.
14. "Trust `X-Forwarded-Host` from any request to fix errors." **False:** risks host poisoning.
15. "Default in-memory credentials suffice for production." **False:** persistence and clear lifecycle management are required.

## 16. Practice questions

**Question 1.** Can `https://login.example.com` use RP ID `example.com`?  
**Yes**, under suffix rules when the domain is valid; the server must still explicitly allow the origin.

**Question 2.** Is RP ID `example.com:443` valid?  
**No**, ports belong to origins, not RP IDs.

**Question 3.** With the same RP ID `example.com`, if origin `https://preview.example.com` is unapproved, should assertions be accepted?  
**No**, the server rejects it even if the browser allows the RP ID.

**Question 4.** Can passkeys be enabled on `http://login.example.com` because it's an internal network?  
**No**, a secure context with HTTPS must be deployed; only `localhost` and specific special cases have appropriate exceptions.

**Question 5.** If the backend runs at `http://app:8080` while users visit `https://login.example.com`, what should the allowed origin be?  
**`https://login.example.com`**, not the internal hostname.

**Question 6.** How does changing an allowed origin differ from changing an RP ID?  
Allowed origin adjusts **where the server trusts ceremonies**; RP ID is the **cryptographic credential scope**, which may require migration/re-registration.

**Question 7.** Is adding `https://example.net` to allowed origins enough for browsers there to use RP ID `example.com`?  
**No**. You need a different architecture or Related Origin Requests with browser support and server validation.

### Pre-go-live checklist

- [ ] RP ID is a valid, stable domain with no scheme/port/path and is not a public suffix.
- [ ] Allowed origins specify exact scheme/host/port, with no wildcards.
- [ ] Production web app runs over HTTPS with a valid certificate; HTTP localhost is lab-only.
- [ ] Proxy trusts proper forwarded headers, never using untrusted `Host` headers to generate allowlists.
- [ ] WebAuthn library verifies challenge, origin, `rpIdHash`, signature, flags, and user mapping.
- [ ] Sessions/CSRF/account recovery and persistence are tested.
- [ ] Do not relax production allowlists for preview or low-trust subdomains.
- [ ] Have a plan for multi-origin, ROR compatibility, and RP ID migration.
- [ ] Browser E2E tests and negative error cases, not just config unit tests.
- [ ] Never treat unverified `clientData` fields as proof of login.

## 17. References

- [W3C — Web Authentication Level 3 Recommendation, 2026-08-25](https://www.w3.org/TR/2026/REC-webauthn-3-20260825/): RP ID/domain suffix, secure context, `rpIdHash`, origin verification, and Related Origin Requests.
- [Spring Security 6.5 — Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html): `webAuthn(...)`, dependencies, registration/authentication endpoints, and credential persistence.
- [Spring Security 6.5 — WebAuthnConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/WebAuthnConfigurer.html): configuring `rpId`, `allowedOrigins`.
- [MDN — Secure contexts](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts): local trustworthy origins and `isSecureContext`.
- [web.dev — Related Origin Requests](https://web.dev/articles/webauthn-related-origin-requests): `/.well-known/webauthn` file and browser compatibility.
- [Spring Boot 3.5 Gradle plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/): Java/Gradle project for the example.

**Conclusion:** **RP ID** governs which domain a credential belongs to, **allowed origins** govern which websites the server permits to perform WebAuthn, and **HTTPS** provides the secure context for production browsers. All three must be right; none of them permits skipping cryptographic assertion verification.
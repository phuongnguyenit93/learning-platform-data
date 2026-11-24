# Preparing a Sample Application, Test IdP, HTTPS, and Time Synchronization

> **Topic:** Spring Security – federation. **Foundation:** Spring Boot/Spring Security, OpenID Connect (OIDC), test IdP, TLS, and system time. This lab builds a Java 17+ web app authenticating via Keycloak, running HTTPS on localhost, then verifies baseline prerequisites before moving on to SAML, CAS, or Resource Servers.

## 1. Lab Objectives and Scope

After this lab, you will be able to:

1. Create a minimal Spring Boot application with a `SecurityFilterChain` and an endpoint requiring login.
2. Start a standalone test IdP and create a realm, OIDC client, and test user.
3. Connect the application to the OIDC issuer via discovery; distinguish issuer address, authorization endpoint, redirect URI, and client credentials.
4. Enable HTTPS for the application with a development certificate; understand the difference between **transport encryption** and **certificate trust**.
5. Inspect clocks on the application host, IdP host, and container/VM environments; understand the impact on JWT, SAML, CAS, and TLS certificates.
6. Run a positive/negative test suite: successful login, wrong redirect URI, untrusted certificate, wrong issuer, and clock drift.
7. Know which settings are **lab-only** and what additional prerequisites apply before staging/production deployment.

This lab implements one **OIDC Authorization Code** path for concrete test results. The principles of HTTPS, issuer identity, time synchronization, and certificate management continue to apply when replacing OIDC with **SAML 2.0**, **CAS**, or adding an **OAuth2 Resource Server**.

**Convention:** Names such as `lab`, `spring-lab`, and `keycloak` are example environment identifiers. Passwords and client secrets must be created by the learner and kept outside source code. `localhost` addresses only work when the browser, Spring Boot, and Keycloak reach ports on **the same development machine**.

## 2. Lab Diagram and Network Boundaries

```text
Browser on development machine
       | 1. HTTPS https://localhost:8443/me
       v
[Spring Boot app]  (OIDC Relying Party / OAuth2 Client)
       | 2. Redirect browser to IdP
       v
[Keycloak IdP/OP]  http://localhost:8081  (loopback lab only)
       | 3. User logs in; OP redirects to HTTPS callback
       v
https://localhost:8443/login/oauth2/code/keycloak
       | 4. Spring backend exchanges authorization code for tokens
       v
[Keycloak token endpoint]
       | 5. Spring validates ID Token and creates web session
       v
https://localhost:8443/me  -> test identity details
```

**Roles:**

| Component | Responsibility | Must Stay Consistent |
| --- | --- | --- |
| **Spring Boot web** | RP/client: creates authorization request, receives code, validates OIDC result, establishes session | `client-id`, secret, `redirect_uri`, and issuer |
| **Keycloak** | OP/IdP: authenticates users, issues codes and tokens | Realm, discovery endpoints, keys, user/client, time |
| **Browser** | Follows redirects, holds RP session cookies | Trusts app HTTPS cert and exact hostname |
| **OS/VM/Docker** | Provides clock, DNS, and networking | True time, display timezone, port mapping |
| **TLS certificate / CA** | Authenticates endpoint and encrypts connection | SAN, validity window, CA chain, private key |

**Distinguish two security levels:** The example uses **HTTPS for the app**, while **Keycloak `start-dev` over HTTP is bound solely to `127.0.0.1`** for fast loopback learning. This **is not a full HTTPS architecture**. When deploying to staging, shared-network CI, or production, **both** the IdP and the app must use HTTPS with trusted DNS names/certificates; never expose HTTP/`start-dev` IdP configs on real networks.

## 3. Preparing Tools and Selecting Versions

### 3.1. Required Tools

- **JDK 17 or newer**, compatible with the chosen Spring Boot version. Verify via `java -version` and `javac -version`.
- **Docker Engine/Docker Desktop** to run Keycloak; verify `docker version`. Start the engine and allocate sufficient CPU/RAM for the IdP.
- **Browser** and `curl` CLI; on Windows PowerShell you can call `curl.exe` to avoid legacy environment `curl` aliases.
- **Maven Wrapper** included with projects generated from Spring Initializr; global Maven installation is not mandatory.
- `keytool` bundled with the JDK to generate development certificates, or a lab-dedicated trusted local CA such as `mkcert`.
- Permissions to inspect time synchronization service status on the host/VM.

Generate the project from [Spring Initializr](https://start.spring.io/) with illustrative settings:

| Property | Value Used in Lesson |
| --- | --- |
| Project | Maven |
| Language | Java |
| Spring Boot | A supported stable release matching the installed JDK |
| Group | `com.example` |
| Artifact | `federation-lab` |
| Package | `com.example.federationlab` |
| Dependencies | **Spring Web**, **Spring Security**, **OAuth2 Client** |

Exact starter names can vary across Spring Boot generations; use Initializr's dependency catalog for your **exact version**. This is a **Servlet web** application, not WebFlux. OAuth2 Resource Server is not needed yet for testing OIDC login; when building an API accepting Bearer Access Tokens, add its dependency and dedicated config separately.

Run checks from the project directory:

```bash
java -version
javac -version
./mvnw -version
docker version
```

On Windows use `.\mvnw.cmd -version`. If `java` and `javac` report different major versions, fix `JAVA_HOME`/`PATH` before starting; never treat an unready Java environment as a federation runtime bug.

### 3.2. Keeping the Environment Reproducible

Record Java, Spring Boot, Spring Security, Keycloak image versions, port settings, realm/client config, and certificate steps in your lab's internal README. Pin a fixed Keycloak image, such as `26.8.1` as shown in Keycloak's Docker guide, so behavior does not shift unexpectedly across runs; when updating the image, re-verify admin UI and OIDC flows.

**Do not store in Git:** private keys, `*.p12` files containing private keys, keystore passwords, client secrets, refresh tokens, session cookies, or raw token dumps. Use environment variables or a secret manager; if using a `certs/` directory in the project, add it to your `.gitignore`.

## 4. Starting the Test Keycloak IdP

### 4.1. Running the Container Bound Only to Loopback

The command below uses a shell with Docker; it binds only host `127.0.0.1:8081` to container port `8080`:

```bash
docker run -d --name keycloak-federation-lab \
  -p 127.0.0.1:8081:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=labadmin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=lab-admin-only-local \
  quay.io/keycloak/keycloak:26.8.1 \
  start-dev
```

**This admin password is a one-time example for a loopback-restricted lab; never reuse it or move it to shared servers.** In real operations, use strong passwords from a secret vault and Keycloak production mode. Windows PowerShell users can put the command on **one line** (removing Bash line-continuation `\`).

Check container and logs when needed:

```bash
docker ps --filter name=keycloak-federation-lab
docker logs keycloak-federation-lab
```

Once the server finishes starting, visit `http://localhost:8081/admin/` and log in with the lab admin account. If port 8081 is occupied, pick another host port **and update all issuer URLs in this lesson**; avoid changing just one place.

### 4.2. Creating the Realm and OIDC Client

In the Keycloak Admin Console:

1. Create a **realm** named `lab`. This isolates lab users/settings from the master admin realm.
2. Go to **Clients → Create client**, choose **Client type = OpenID Connect**, **Client ID = spring-lab**.
3. Set **Client authentication = On** to use a **confidential client** on the backend. Enable **Standard flow** (Authorization Code); Direct Access Grants/password grant need not be enabled for this lab.
4. Set **Valid redirect URIs** to the exact value: `https://localhost:8443/login/oauth2/code/keycloak`. If Root URL/Home URL fields exist, you may use `https://localhost:8443`. Never use wildcard `*` just to silence callback errors.
5. Save the client and copy the **Client secret** from the Credentials tab. Supply the secret via an environment variable at runtime; never paste it into source files or logs.
6. Create user `learner` under **Users**, set a password under **Credentials**, and turn off **Temporary** if you want to log in directly without a forced password change during the lab. Use test data only, never real identities.
7. Confirm the client has the `openid` scope; you can also include `profile`. `openid` marks this as an OIDC request rather than plain OAuth2 authorization.

Menu labels may shift slightly across Keycloak versions; `Client authentication`, `Standard flow`, `Valid redirect URIs`, and `Credentials` remain the essential checkpoints.

### 4.3. Checking OIDC Discovery Before Writing Spring Config

Open the URL:

```text
http://localhost:8081/realms/lab/.well-known/openid-configuration
```

Or run:

```bash
curl -f http://localhost:8081/realms/lab/.well-known/openid-configuration
```

The response is the OP's JSON metadata; inspect fields such as `issuer`, `authorization_endpoint`, `token_endpoint`, and `jwks_uri`. The `issuer` value **must match** `http://localhost:8081/realms/lab` configured in Spring: exact scheme, host, port, and realm. Never swap `localhost` for `127.0.0.1` in only some URLs and expect issuer/audience checks to stay consistent.

**Docker trap:** If later the Spring app also runs inside a container, `localhost` inside the Spring container refers to **the Spring container itself**, not the host or the Keycloak container. In that case you must design DNS/networking so **browser, app, and issuer metadata** share consistent endpoints; do not arbitrarily change issuer URI to a Docker service name if Keycloak emits a different `issuer` value. For this lab, run **Spring on the host** and Keycloak in Docker so URLs remain uniform.

## 5. Enabling HTTPS for the Spring Boot Application

### 5.1. Why Use HTTPS Starting in the Lab?

In OIDC, the browser carries the authorization code back to the redirect URI and stores the RP's session cookie; TLS protects this traffic in transit and authenticates the receiving server. In SAML, the browser submits SAMLResponse to the ACS; in CAS, the browser carries the service ticket to the app URL. In production, login/callback endpoints require HTTPS with valid certificates; HTTP localhost exceptions in development rules **are not permission to run HTTP on real networks**.

HTTPS has two components:

- **Encryption and integrity:** TLS prevents third parties in transit from reading/tampering with traffic assuming keys/sessions are uncompromised.
- **Endpoint authentication:** the browser/client verifies the server certificate, hostname/SAN, CA chain, and validity dates. A self-signed certificate encrypts traffic yet **is not trusted by browsers automatically**; users should never form a habit of clicking past certificate warnings.

### 5.2. Creating a Development Keystore for `localhost`

Create a `certs` directory in the project and generate a private key and self-signed certificate:

```bash
mkdir -p certs

keytool -genkeypair \
  -alias localhost \
  -keyalg RSA \
  -keysize 3072 \
  -storetype PKCS12 \
  -keystore certs/lab-https.p12 \
  -validity 30 \
  -dname "CN=localhost, OU=LocalLab, O=Training, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

On Windows PowerShell create the folder with `New-Item -ItemType Directory -Path certs` if absent, then run `keytool` with all arguments on one line. When `keytool` prompts, set a **dedicated keystore password** and store it safely. `-ext SAN` ensures the certificate declares `localhost` and the loopback IP; `CN` alone is insufficient for modern hostname verification.

Export the **public certificate** to test with `curl` without disabling TLS verification:

```bash
keytool -exportcert -rfc \
  -alias localhost \
  -keystore certs/lab-https.p12 \
  -file certs/lab-https.pem
```

`lab-https.pem` contains only the public certificate; `lab-https.p12` contains the private key and must never be committed. In browsers, self-signed certificates normally trigger untrusted warnings; you can substitute a certificate from a **locally trusted dev CA** (like mkcert) or import the lab CA per internal procedure. Avoid clicking "bypass warning" as a routine workflow. In staging/production, use certificates issued by an appropriate CA for the **real FQDN** with automated renewal.

### 5.3. Configuring `application.yml`

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:./certs/lab-https.p12
    key-store-type: PKCS12
    key-store-password: ${LAB_TLS_KEYSTORE_PASSWORD}
    key-alias: localhost

spring:
  security:
    oauth2:
      client:
        provider:
          keycloak:
            issuer-uri: http://localhost:8081/realms/lab
        registration:
          keycloak:
            provider: keycloak
            client-id: spring-lab
            client-secret: ${LAB_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
```

**Explanation of each piece:**

- `server.port: 8443` and `server.ssl.*` configure the embedded server to serve HTTPS using the private key from PKCS#12; `file:./certs/...` is relative to the working directory.
- `provider.keycloak.issuer-uri` enables OIDC discovery; must match the exact `issuer` Keycloak publishes.
- `registration.keycloak` sets **registrationId = keycloak**; thus the default callback becomes `/login/oauth2/code/keycloak`, matching what was registered in Keycloak.
- `scope: [openid, profile]` enables the OIDC layer; the app receives an ID Token after completing the code flow.
- Two environment variables keep secrets out of source code. Never write real client secrets in `application.yml`, Git, screenshots, or submitted assignments.
- The app runs HTTPS while the **lab HTTP issuer is loopback-only**; upgrade the IdP to HTTPS on any network beyond a personal machine.

Spring Boot can configure TLS via `server.ssl` or **SSL bundles** (`spring.ssl.bundle`), depending on your goal. Here we use the keystore directly so beginners clearly see the certificate, port, and password; do not configure both mechanisms simultaneously. With the settings above, Spring Boot by default **does not open an extra HTTP connector** on 8080.

## 6. Writing the Sample OIDC Application with Spring Security

### 6.1. Startup Class

File `src/main/java/com/example/federationlab/FederationLabApplication.java`:

```java
package com.example.federationlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationLabApplication.class, args);
    }
}
```

Spring Initializr normally generates an equivalent application class; keep **one** entrypoint matching the package without creating duplicate classes. This is a Java program using Spring Boot/Maven dependencies, **not runnable standalone via plain `javac`**.

### 6.2. Login Configuration

File `src/main/java/com/example/federationlab/SecurityConfig.java`:

```java
package com.example.federationlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

`oauth2Login` redirects unauthenticated users into the OIDC/OAuth2 flow, verifies callbacks, and establishes web session authentication. Public `/` lets you test HTTPS independently of the IdP; `/me` and remaining URLs require login. **Do not disable CSRF for browser sessions**: Spring Security protects CSRF by default where needed. Never accept `X-User`, query-string `email`, or unverified tokens as login proof.

### 6.3. Identity Verification Endpoint

File `src/main/java/com/example/federationlab/LabController.java`:

```java
package com.example.federationlab;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabController {

    @GetMapping("/")
    public String home() {
        return "Federation lab is running over HTTPS";
    }

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject()
        );
    }
}
```

**Why return only `issuer` and `subject`?** The `iss` + `sub` pair is the proper OIDC identifier showing the IdP–RP link; no need to expose raw ID Tokens, access tokens, real emails, cookies, or secrets on the page. Never use `sub` alone as a global user ID across multiple issuers. In real applications, session details and permissions must follow dedicated data and authorization policies.

Endpoint `/me` in this lesson is protected by a session after OAuth2 login; returning JSON **does not mean** this is an OAuth2 Resource Server accepting Bearer Access Tokens. To demonstrate a Resource Server, build a separate API with `oauth2ResourceServer`, audiences/scopes, and JWT validation.

### 6.4. Run Commands and Environment Variables

In Bash (Linux/macOS if using Bash), prompt for both secrets to avoid recording raw secrets in shell history:

```bash
read -rsp "Keystore password: " LAB_TLS_KEYSTORE_PASSWORD
echo
export LAB_TLS_KEYSTORE_PASSWORD

read -rsp "OIDC client secret: " LAB_OIDC_CLIENT_SECRET
echo
export LAB_OIDC_CLIENT_SECRET

./mvnw spring-boot:run
```

On Windows PowerShell, equivalent example:

```powershell
$env:LAB_TLS_KEYSTORE_PASSWORD = Read-Host "Keystore password"
$env:LAB_OIDC_CLIENT_SECRET = Read-Host "OIDC client secret"
.\mvnw.cmd spring-boot:run
```

The entered values are your **created keystore password** and the **client secret** from Keycloak. The PowerShell prompt above is only for a private lab machine; to mask typed input, use `-AsSecureString` or your environment's managed secret store. After testing, clear both variables from the shell session and stop the container.

When the app starts, check logs confirming the embedded server is listening on port **8443**. Log phrasing varies by version; do not depend on exact text. If `ClientRegistration` fails to initialize, verify the IdP is running, discovery URI, and issuer before editing Java code.

## 7. End-to-End HTTPS and Login Testing

### 7.1. Testing TLS Without Skipping Certificate Checks

On the development machine:

```bash
curl --cacert certs/lab-https.pem \
  -i https://localhost:8443/
```

For `/`, expected response has HTTP `200` and body:

```text
Federation lab is running over HTTPS
```

`--cacert` specifies the matching public certificate; because this lab's cert is self-signed for localhost, `curl` verifies the trust chain **without `-k`/`--insecure`**. On Windows use `curl.exe` if needed. `curl` does not check browser trust stores the same way browsers do; browser tests must still ensure the certificate is trusted.

Test the authenticated endpoint:

```bash
curl --cacert certs/lab-https.pem \
  -I https://localhost:8443/me
```

Without a login cookie, the response is typically a **302 redirect** to Spring Security's login flow; it is not yet the `/me` response. Never put raw access tokens or session cookies into shared `curl` commands to "bypass" login.

### 7.2. Browser Testing

1. Ensure the browser trusts the localhost certificate from the lab CA; verify the address bar shows `https://localhost:8443`.
2. Open `https://localhost:8443/`; observe the test string. This verifies Spring/HTTPS **independently** of the IdP.
3. Open `https://localhost:8443/me`; Spring Security routes to the login page offering **Keycloak**.
4. Choose Keycloak login; confirm the browser redirects to realm `lab` on `http://localhost:8081`. Enter test user `learner`.
5. After completing the code flow, the browser returns to HTTPS callback `/login/oauth2/code/keycloak` and continues to `/me`.
6. The JSON response shows `issuer` pointing to realm `lab` and `subject` as the stable ID assigned by Keycloak to the test account. `subject` is unique per user and **not predictable or hardcoded**.
7. Open an incognito window and visit `/me`: a new login must be required since no RP session exists; this helps distinguish local browser sessions from an active IdP SSO session.
8. Log out of the application and test again. **Local logout** does not mean the entire **OP SSO session** ended; federated logout requires separate protocol configuration.

Result diagram:

```text
GET /                       -> 200 when TLS works
GET /me (no session)        -> redirect to login
Select "Keycloak"           -> OP authorization endpoint
Log in test user            -> authorization code to HTTPS callback
Spring exchanges + verifies -> RP session created
GET /me (with session)      -> 200, JSON {issuer, subject}
```

In the browser check, `subject` may change if you delete and recreate the user or realm. The displayed value is test data; never assume two recreated users named `learner` get the same `sub`.

### 7.3. "Fail-Safe" Negative Testing

| Test | Expected Outcome and Meaning |
| --- | --- |
| Change redirect URI in Keycloak to exclude the real callback | Keycloak rejects/cannot complete auth code flow; **never** add wildcards to work around errors |
| Change `issuer-uri` to a wrong realm/host/port | Discovery or issuer validation fails; tokens from other OPs are rejected |
| Access app via a hostname absent from SAN | TLS hostname verification fails; never disable hostname verification |
| Omit `LAB_TLS_KEYSTORE_PASSWORD` | App fails to load private key/keystore or bind HTTPS properly; must not silently fall back to HTTP |
| Omit `LAB_OIDC_CLIENT_SECRET` or use wrong secret | Token exchange fails; never log the secret value |
| Stop Keycloak while keeping the HTTPS app running | `/` still works; new logins or token exchanges fail; separates IdP errors from app TLS errors |
| Send an ID Token in Bearer header to another endpoint | Must not grant API access by default; `/me` uses **sessions**, not Resource Server ID-Token validation |

Only run destructive config tests on the test realm/app, then **restore** approved settings. For self-signed certificates, browser `NET::ERR_CERT_AUTHORITY_INVALID` is expected when the CA is untrusted; the fix is proper trust setup, not writing code to skip TLS validation.

## 8. Time Synchronization: A Foundational Prerequisite of Federation

### 8.1. "Timezone" vs "Clock Skew"

**UTC** is the baseline for comparing timestamps; timezones like Asia/Ho_Chi_Minh only affect how local time is **displayed**. Two machines with different display timezones yet synchronized to UTC still validate tokens normally. Conversely, two machines in the same timezone with **drifted real clocks** can fail authentication.

Values to distinguish:

- `iat`: time the token was issued, sometimes used in policy checks.
- `nbf`: token is **not valid before** this timestamp.
- `exp`: token **expires** at this timestamp.
- `auth_time` in OIDC: when the OP authenticated the user, relevant for `max_age`/reauthentication checks.
- `NotBefore` and `NotOnOrAfter` in SAML: assertion/conditions validity window.
- TTL/expiration of **authorization codes**, **CAS Service Tickets**, session cookies, request correlations, and nonce/replay stores.
- `Not Before`/`Not After` of **TLS certificates**: wrong clocks can make valid certificates appear not-yet-valid or expired.

**Timezone-independent (UTC) time calculation example:**

```text
Issuer creates token:
  nbf = 2026-11-07T03:00:00Z
  exp = 2026-11-07T03:05:00Z

Real time at request: 2026-11-07T03:01:00Z
Spring Boot clock runs +6 minutes fast:
  Spring sees 2026-11-07T03:07:00Z
=> Spring may reject token as past exp,
   even though it was issued only ~1 minute ago in real time.

Spring Boot clock runs -3 minutes slow:
  Spring sees 2026-11-07T02:58:00Z
=> Spring may reject token as before nbf.
```

The example illustrates the principle; actual decisions also depend on `clock skew`/leeway applied by the validator. **Never change timezones or remove `exp` checks** to compensate for a drifted clock.

### 8.2. Checking NTP/NTS and Clock Status

On Linux with systemd, check:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
timedatectl status
timedatectl show -p NTPSynchronized
```

If using chrony, check offset and sources with:

```bash
chronyc tracking
chronyc sources -v
```

On Windows (PowerShell or Command Prompt):

```powershell
Get-Date -Format o
w32tm /query /status
w32tm /query /source
```

On macOS, view UTC with `date -u` and check "Set time and date automatically" plus the OS sync source. Commands may require appropriate privileges; if an environment does not use `systemd` or `chrony`, inspect whichever time service actually runs on that host.

**Which machines must be checked?** The host running Spring Boot, the host/container/VM running the IdP, any gateway/proxy inspecting tokens, API Resource Server hosts, and certificate issuers/stores. In Docker, Linux containers typically share the host/VM kernel clock; Docker Desktop also has a VM layer. When drift occurs, inspect **host and VM clocks** rather than trying to adjust time inside an unprivileged container as a long-term fix.

### 8.3. Controlled Clock Skew Configuration

When validating JWTs, Spring Security Resource Server uses `JwtTimestampValidator` to check `nbf` and `exp`; Spring Security documentation describes a default clock skew of roughly **60 seconds** for Resource Server and allows tuning when needed. This is a **small tolerance**, not an excuse to skip NTP synchronization. ID Token/OIDC validators, SAML assertion validators, and CAS tickets have their own mechanisms/limits; **do not assume the same 60-second default across every protocol**.

If tuning is needed on Resource Server:

1. Measure actual clock drift first, confirm NTP is truly running, and fix the infrastructure root cause.
2. Pick the smallest leeway matching measured drift and security policy instead of widening it by minutes to hide errors.
3. Never remove `exp`/`nbf`, signature, issuer, or audience checks; all validators must still work together.
4. Alert when offset exceeds an agreed operational threshold; periodically test tokens near expiration.

**Distinguish failures:** `invalid_grant` at the token endpoint can come from reused codes, expired codes, PKCE/redirect URI mismatches, or other server conditions; **never conclude every `invalid_grant` is clock drift**. If a freshly issued token immediately reads "expired" or a SAML assertion reads "not yet valid", checking UTC across hosts becomes the top diagnostic step.

## 9. Extending the Lab to SAML, CAS, and OAuth Resource Server

Once basic OIDC works, **keep the HTTPS + time-sync infrastructure** and add each protocol in a dedicated configuration.

| To Test | Spring App Role | What to Prepare on IdP or Central Server | Special Time / Identifier Fields |
| --- | --- | --- | --- |
| **SAML 2.0 Web SSO** | SAML Service Provider/Relying Party | SAML metadata, `entityID`, assertion signing cert, SSO endpoint, ACS URL | `NotBefore`/`NotOnOrAfter`, `Destination`, `AudienceRestriction`, `InResponseTo` where applicable |
| **OIDC login** | OIDC RP | OIDC discovery, issuer, client, redirect URI, secret/PKCE, JWK Set | `iss`, `aud`, `exp`, `nonce`, `auth_time` per flow |
| **CAS login** | CAS service | CAS login and `/serviceValidate`, registered service URL, TLS channel | Short-lived/single-use Service Ticket, CAS session, exact `service` |
| **OAuth2 API** | Resource Server | Authorization Server issuing Access Tokens with API audience/scopes; JWKS or introspection | `iss`, `aud`, `exp`/`nbf`, scopes/roles, and business permissions |

**Never mix proofs:** SAML Assertions, OIDC ID Tokens, CAS Service Tickets, and OAuth Access Tokens **are not directly interchangeable**. One Keycloak realm may support both OIDC and SAML, yet Spring Security config must pick `oauth2Login` or `saml2Login` accordingly; CAS requires its own ticket validation flow. Resource Server verifies Access Tokens for APIs, while the `/me` lab currently uses a web session after OIDC login.

An extension exercise can deploy a second API application with `spring-boot-starter-oauth2-resource-server` configured with `issuer-uri`/`audiences`, then test bearer tokens with valid/invalid issuers, audiences, and scopes. Sharing an IdP **does not turn an RP's ID Token into an API Access Token**.

## 10. Promoting Properly from Lab to Staging/Production

**Operational goal:** Both browser → RP and RP → OP, plus calls to token/JWKS/metadata endpoints must use verified TLS connections; hostnames, issuers, and redirect URIs must match real infrastructure.

1. **Production IdP:** Use a real domain like `login.company.example`; configure Keycloak production mode, proper database, HA/backup, TLS, and host/proxy per deployment docs. Never keep `start-dev`, default admin accounts, public HTTP, or test users in real environments.
2. **Application and callbacks:** Set `https://app.company.example/login/oauth2/code/keycloak` as the exact redirect URI; update `issuer-uri` to the HTTPS-published issuer. `http://` vs `https://`, and `localhost` vs FQDN, are distinct origins/issuers.
3. **Certificates and trust:** Issue certs from a trusted CA; automate renewal and private key management; configure Java truststores when using an internal CA. Never disable TLS verification in Java clients.
4. **Reverse proxy:** If TLS terminates at ingress/proxy, the backend may run on a private network yet must be protected per topology; configure forwarded headers **trusted only from known proxies**, ensuring Spring builds `{baseUrl}` and `redirect_uri` with the right HTTPS scheme and public host. Never blindly trust `X-Forwarded-Proto`/`Host` from arbitrary clients.
5. **Secrets:** Move client secrets, keystore passwords, and signing keys to a secret manager; enforce permissions and planned rotation. Isolate `dev/staging/prod` with distinct clients/realms/issuers/keys where appropriate.
6. **Clocks:** Every host, node, VM, and proxy uses a reliable time-sync source with offset metrics and drift alerts. Assess NTP/NTS accuracy per system policy.
7. **Sessions/cookies:** Enable `Secure` and `HttpOnly` on session cookies, set SameSite appropriately for required redirects/cross-site requests, enforce CSRF/session fixation protections; use tight cookie domains and timeouts.
8. **Least privilege:** Register exact redirect URIs, minimal scopes, proper client authentication/PKCE, approved role mapping, plus logout and revocation where supported.
9. **Pre-launch verification:** Discovery, HTTPS chain, callbacks, token validation, user mapping, locked users, clock skew, expired certs, key rotation, IdP downtime, and fail-closed behavior.
10. **Monitoring:** Keep correlated logs, categorized auth errors, cert validity, drift, and IdP health, while never logging raw ID Tokens, Access Tokens, SAML Assertions, CAS tickets, client secrets, or session cookies.

**Certificate note:** When IdP HTTPS uses a private CA, the Java client must trust that CA; a browser trusting a cert does not mean the JVM trusts it. `PKIX path building failed` is typically a trust-chain/hostname issue, never solved by changing `client-id` or turning off SSL verification.

## 11. Troubleshooting by Symptom

| Symptom | Common Cause | How to Check / Fix |
| --- | --- | --- |
| `Connection refused` on port 8081 | Docker not running, container not ready, wrong port binding | `docker ps`/`docker logs`, check `http://localhost:8081/admin/` |
| Spring fails startup missing issuer metadata | Keycloak/realm not ready, wrong issuer-uri, JVM network cannot reach OP | Curl `/.well-known/openid-configuration` directly; compare issuer, DNS, and port |
| `invalid_redirect_uri` or rejected callback | Scheme, host, port, or path differs from client config | Compare exact actual redirect URI vs Valid redirect URIs; no wildcards |
| OAuth2 login returns `invalid_client` | Wrong client secret, client auth mode, client ID, or registration | Check client authentication and secret in Keycloak; regenerate secret if needed |
| Browser warns `ERR_CERT_AUTHORITY_INVALID` | Self-signed app cert or lab CA not yet trusted | Use a trusted dev CA, check SAN/chain; avoid bypassing |
| `SSLHandshakeException`, `PKIX path building failed` from JVM | JVM does not trust IdP cert or HTTPS endpoint | Check CA/truststore, cert DNS match, complete chain |
| `Issuer mismatch` | OP's `iss` differs from configured issuer | Compare exact `issuer` string in discovery vs config; avoid arbitrary localhost/127.0.0.1 swaps |
| `Token expired` or `not yet valid` right after login | Clock drift, expired token, or mismatched lifetime config | Compare UTC/NTP across hosts; check `exp`, `nbf`, valid skew |
| OAuth code rejected or `invalid_grant` | Expired/reused code, wrong redirect URI/PKCE, time drift, or IdP policy | Start fresh request, check exact timeline and correlation; never replay code |
| Repeated 302 or app reverts to HTTP | Proxy forwarded headers, `{baseUrl}`, Secure cookie, non-standard reverse-proxy scheme | Check public HTTPS URL, trusted proxies, cookies, redirect URI |
| `/me` page has no `OidcUser` | Client not using OIDC, missing `openid` scope, or not logged in | Check registration scope, OIDC response, `oauth2Login`, and session |
| Sudden failures after cert/key rotation | Stale browser/JVM truststore/JWKS cache or un-updated metadata | Check trust chain and rollover procedure; never disable validation |

**Quick triage workflow:**

```text
Java/Docker error?           -> fix runtime environment
TLS GET "/" fails?           -> fix cert/port/keystore
GET "/" works, IdP down?     -> fix container/realm/network
Discovery mismatch?          -> fix issuer/host/port
IdP rejects authorize?       -> check client, redirect URI, user
Callback/token exchange err? -> check secret, code, issuer, clock
Logged in yet /me 401?       -> check session and filter chain
Bad exp/nbf?                 -> measure clock offset before tuning leeway
```

## 12. Acceptance Checklist for a Foundational Federation Environment

- [ ] `java -version`/`./mvnw -version`/Docker work; Spring Boot project includes Web + Security + OAuth2 Client.
- [ ] Keycloak binds loopback-only in the lab; realm `lab` and OIDC client `spring-lab` are operational.
- [ ] Discovery endpoint returns the exact issuer declared in the application's `issuer-uri`.
- [ ] Registered redirect URI matches `https://localhost:8443/login/oauth2/code/keycloak` verbatim.
- [ ] App serves HTTPS on 8443; cert includes SAN `localhost`, is unexpired, and passes client verification; `curl --cacert` succeeds.
- [ ] Private keys, keystore passwords, and client secrets are neither committed nor logged.
- [ ] `/` returns public 200; unauthenticated `/me` redirects to login; Keycloak login succeeds and returns test user's ID.
- [ ] Wrong redirect, wrong issuer, and untrusted TLS cases are **rejected** by the proper mechanisms.
- [ ] UTC clocks and time-sync services on host/VM/IdP are verified; oversized clock skew is not used to mask NTP failures.
- [ ] Clear understanding of when lab HTTP IdP must be replaced by an **HTTPS IdP** and real infrastructure config.
- [ ] Procedures exist for secret rotation, cert/key rotation, clean teardown, and safe log inspection for subsequent federation labs.

**Expected outcome:** A reproducible learning environment where you can access the app over HTTPS, log in via a test IdP with OIDC, observe issuer/subject, and verify accurate clocks. With these foundations stable, subsequent SAML/CAS/OAuth2 labs can focus on **protocols and trust boundaries** rather than port, certificate, or clock noise.

## 13. Reference Documentation

- [Spring Initializr](https://start.spring.io/) — generate sample applications matching supported Spring Boot versions.
- [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html) — `ClientRegistration`, OIDC discovery, redirect URIs, and filters.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/) — flows and differences between OAuth2 client and Resource Server.
- [Spring Boot — Embedded Web Server SSL](https://docs.spring.io/spring-boot/how-to/webserver.html) — `server.ssl`, keystores, HTTPS connectors.
- [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html) — reusable key/trust material configuration.
- [Keycloak — Getting Started on Docker](https://www.keycloak.org/getting-started/getting-started-docker) — running dev Keycloak, creating realms and OIDC clients.
- [Keycloak — Running in a Container](https://www.keycloak.org/server/containers) — container options, startup modes, and production notes.
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — `exp`/`nbf`, issuer, JWT validator clock skew.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — issuer, ID Token, and validation.
- [SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — SP/IdP flows, ACS, and assertion conditions.

# SPNEGO, HTTP Negotiate, and the Role of the Browser

> **Module:** Spring Security – federation. **Group:** Kerberos and SPNEGO. This lesson explains how the browser participates in **Integrated Windows Authentication/Single Sign-On** via HTTP `Negotiate`; clearly distinguishes **Kerberos**, **GSS-API/SSPI**, **SPNEGO**, **SPN**, **keytab**, **ticket cache**, browser allowlists, HTTP 401, and Spring Security authentication mechanics. Examples use Java 17, Spring Boot 3.5.x, Spring Security 6.5.x, and Spring Security Kerberos 2.2.0. All hostnames/realms in this lesson are **examples**, not real services.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish Kerberos v5, GSS-API, Windows SSPI, SPNEGO, and the HTTP `Negotiate` authentication scheme; do not refer to all five as a single protocol.
2. Describe how a browser receives `401 WWW-Authenticate: Negotiate`, asks the OS to build a GSS context token, sends `Authorization: Negotiate <base64-token>`, handles continuation rounds, and receives the outcome.
3. Explain how a user achieves SSO without re-entering a password thanks to **TGT and service ticket**; the browser never sends a TGT or keytab to the web server.
4. Identify the Service Principal Name `HTTP/intranet.example.org@EXAMPLE.ORG`, the role of the KDC/Active Directory, DNS/FQDN, server keytab, and Java GSS acceptor.
5. Configure trusted sites in Microsoft Edge/Chrome/Firefox and distinguish **permitting SSO authentication** from **Kerberos credential delegation**.
6. Recognize that `Negotiate` can select NTLM in certain environments, so you must verify the **negotiated mechanism** if a Kerberos-only policy is required.
7. Integrate `SpnegoEntryPoint`, `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator`, and `UserDetailsService` into Spring Security.
8. Understand the differences among **HTTP Negotiate authentication**, **HTTP session cookie**, **application authorization**, **CSRF protection**, **mutual authentication**, and **TLS**.
9. Run a pure-JDK Java 17 program that classifies HTTP headers, verify stdout, and know why Base64 decoding is not Kerberos validation.
10. Build a positive/negative test matrix and runbook for KDC/SPN/keytab/KVNO, browser allowlists, reverse proxies, NTLM fallback, channel binding, and double-hop.

**Recommended prerequisites:** HTTP status/headers, browser DevTools, TLS and reverse proxies, Java 17, Spring Security `SecurityFilterChain`, and basic Kerberos concepts (KDC, principal, keytab). Exercises use a separate AD/KDC sandbox environment; that environment is not needed to run the pure Java portion.

## 2. Overview: Four Layers and Responsibilities

| Layer | Standard / Mechanism | Role |
| --- | --- | --- |
| **Kerberos v5** | RFC 4120/4121 | KDC issues TGT and **service ticket** for a service principal; the service verifies the token using its secret key |
| **GSS-API / SSPI** | Java/Unix GSS-API, Windows SSPI | APIs for clients to produce and servers to accept **security context tokens** |
| **SPNEGO** | RFC 4178 | Negotiates which GSS-API authentication mechanism to use, such as Kerberos or NTLM depending on the environment |
| **HTTP Negotiate** | RFC 4559 | Carries GSS/SPNEGO tokens in HTTP `WWW-Authenticate` and `Authorization` |
| **Spring Security** | Servlet authentication architecture | Uses filters/providers to verify tokens, create `Authentication`, store `SecurityContext`, and enforce authorization |

**Do not conflate the layers:**

- `Authorization: Negotiate ...` is an **HTTP header**, not automatic proof that the selected mechanism is Kerberos.
- SPNEGO **is not a new version of Kerberos**; it is mechanism negotiation. In some Windows environments, NTLM may be chosen.
- A Kerberos service ticket **is not a JWT, SAML Assertion, OAuth Access Token, or `JSESSIONID` cookie**.
- SPNEGO is an **authentication** mechanism; it does not decide whether a user may read a report, edit an order, or access another tenant.
- The browser does not hold the **server keytab** and is not the KDC. The browser exchanges GSS tokens with the server while the OS/security library handles credentials and tickets.

### 2.1. The Big Picture

~~~text
                         Kerberos Realm EXAMPLE.ORG
                +-------------------------------------+
                | KDC / Active Directory Controller   |
                | - Authentication Service (AS)       |
                | - Ticket Granting Service (TGS)     |
                +-------------------------------------+
                       ^                       |
                       | request ticket        | service ticket
                       | for HTTP/host         v
User -> Desktop login -> OS Ticket Cache <-> Browser/GSS/SSPI
        TGT typically present     |                |
                                 +-- SPNEGO token--+
                                              |
                                              | HTTPS
                                              | WWW-Authenticate: Negotiate
                                              | Authorization: Negotiate ...
                                              v
                               intranet.example.org (Web SP)
                                      |
                           GSS accept with SPN/keytab
                                      |
                           Spring Security Authentication
                                      |
                           UserDetails + tenant/role policy
                                      |
                           Business resource / HTTP 200
~~~

**The value of SSO:** A user already authenticated with the domain/KDC can open an intranet website without typing their password again. This happens only when **browser trusted-site policy, ticket cache, SPN, KDC, server keytab, and app config** all align.

## 3. Kerberos Before HTTP

1. The user logs into a Windows domain or obtains credentials in a supported Kerberos realm. With MIT Kerberos, `kinit lan@EXAMPLE.ORG` can be used in a test environment.
2. The KDC issues a **Ticket-Granting Ticket (TGT)** and the user keeps it in the **OS ticket cache**, never sending the TGT to the web server.
3. The browser needs to access `https://intranet.example.org/private`. The OS/GSS determines the typical service principal `HTTP/intranet.example.org@EXAMPLE.ORG`.
4. If the client does not yet hold a service ticket for this SPN, it uses the TGT to ask the KDC TGS for a **service ticket specifically for HTTP/intranet.example.org**.
5. The client builds a Kerberos authenticator/AP-REQ via GSS-API and wraps it in a SPNEGO token.
6. The browser carries those bytes inside `Authorization: Negotiate <base64-token>`.
7. The server uses its service principal/keytab to accept the GSS context, verify the user, and reject unsuitable tickets/tokens.
8. Spring Security takes the verified user principal, looks up user status/roles/tenant, and enforces data permissions.

### 3.1. Important Artifacts

| Artifact | Who Holds It | What It Is Used For |
| --- | --- | --- |
| **TGT** | User client/KDC | Requesting other service tickets; never sent to Portal |
| **Service ticket** | Client obtained from KDC | Authenticating to a specific SPN, such as HTTP/intranet.example.org |
| **AP-REQ** | Built by client from service ticket and authenticator | Proving identity to the service acceptor |
| **AP-REP** | Returned by service when mutual authentication is needed | Client verifies the service in the Kerberos security context |
| **SPNEGO GSS token** | Exchanged between client/server | Token containing/negotiating the mechanism, carried via HTTP Negotiate |
| **Server keytab** | Service process or trusted gateway | Contains long-term secret keys to accept Kerberos service tickets |
| **JSESSIONID** | Browser + Spring web app | Local HTTP session after authentication; not a Kerberos ticket |

**Practical rule to remember:** When a user logs back in immediately after "Logout Portal", it is often because the browser still holds a TGT/service ticket in the OS cache. Deleting the local `JSESSIONID` **does not delete the TGT**, and the server cannot erase the OS user's Kerberos credentials via a Set-Cookie response.

### 3.2. FQDN and SPN

~~~text
Browser public URL:
    https://intranet.example.org/private

Kerberos HTTP service principal:
    HTTP/intranet.example.org@EXAMPLE.ORG

Server acceptor:
    service-principal = HTTP/intranet.example.org@EXAMPLE.ORG
    keytab = /run/secrets/http-intranet.keytab
~~~

`HTTP/` is the **Kerberos service class**, even when the transport uses HTTPS; the hostname must match the identifier chosen by the client's GSS stack, usually the public FQDN. The realm is a Kerberos identity and cannot always be inferred from the HTTP host if the organization uses cross-realm trusts. DNS aliases/CNAMEs, load balancers, IP access, and proxies can cause the client to request a service ticket for a name **different** from the server's keytab.

When the same service runs across multiple nodes, service account/keytab distribution must follow an approved security policy. Do not share a single keytab broadly across unrelated apps just to avoid SPN errors.

## 4. HTTP Negotiate: The 401 Challenge-Response Cycle

Per RFC 4559, an initial unauthenticated request:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
Accept: text/html
~~~

The web server returns a challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

The browser sees the scheme, evaluates trusted-site policy, and calls the OS security library. If permitted and valid Kerberos credentials exist, the browser sends:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
Authorization: Negotiate <base64-of-gss-spnego-token>
~~~

**The bracketed text is a format placeholder only**, not a sendable token; never copy it as a credential.

The server Base64-decodes the bytes and passes them to the **GSS acceptor**/Kerberos provider. Upon completion, the server may return:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8

Hello authenticated user
~~~

### 4.1. Not Always Just Two Round Trips

GSS-API `initSecContext`/`acceptSecContext` can require additional round trips. If the context is not yet established, the server returns another 401 **with a continuation token**:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate <base64-response-token>
~~~

The client processes the token and sends the next `Authorization: Negotiate ...`. If mutual authentication requires a final token, RFC 4559 allows the server to send the final token **inside the 200 response**:

~~~http
HTTP/1.1 200 OK
WWW-Authenticate: Negotiate <base64-final-token>
Content-Type: text/plain; charset=UTF-8

Authenticated
~~~

**The first 401 is not a final failure**. Distinguish a "normal challenge" from "GSS/credentials rejected", and distinguish a 401 continuation from a 401 loop caused by a wrong SPN/keytab. Proxies must not strip required headers on 401 or 200 responses.

### 4.2. You Might Not See the Initial 401

A browser that already knows the server supports Negotiate may send a token proactively or reuse an authentication/session context; browsers vary in caches and policies. If Spring already stores `SecurityContext` in the HTTP session, subsequent requests may carry only the `JSESSIONID` cookie. Therefore, "not seeing 401" or "not seeing Authorization on every request" **is not enough** to conclude SPNEGO never ran.

### 4.3. 401 vs. 407

- **401 + WWW-Authenticate: Negotiate**: origin server requires authentication.
- **407 + Proxy-Authenticate: Negotiate**: **forward HTTP proxy** requires authentication before forwarding the request.
- `Authorization` differs from `Proxy-Authorization`. The tokens target different SPNs; never forward a proxy token to the origin server or vice versa.
- If DevTools shows 407, inspect proxy/PAC/client policies, not just Spring Security config on the target app.

### 4.4. Why Base64 Does Not Protect HTTP

Base64 encodes **byte representation into text** for headers; it neither encrypts data nor protects content. HTTP Negotiate is an authentication scheme and does not protect the full HTTP request body/headers by itself. **HTTPS/TLS remains required** to prevent eavesdropping, tampering, credential leakage via intermediaries, and to protect session cookies. Use HSTS, secure cookies, and TLS policies appropriate to your environment.

## 5. What Does the Browser Actually Do?

The browser is both an HTTP client and a **policy enforcement point**: it sends Integrated Authentication automatically only when the host and environment satisfy policy.

| Step | Browser / OS | Server |
| --- | --- | --- |
| User opens intranet URL | Browser sends GET over HTTPS | Spring/nginx/gateway checks if request has authentication |
| Server requires auth | Browser receives 401 Negotiate | EntryPoint issues challenge |
| Policy check | Browser checks trusted-site/enterprise policy; OS checks ticket cache | Server does not yet know identity from 401 alone |
| Token generation | SSPI (Windows) or GSS libraries build token, requesting service ticket from KDC if needed | Server does not acquire the ticket on the browser's behalf |
| New request sent | Browser sends `Authorization: Negotiate ...` | Filter passes bytes to Kerberos/GSS acceptor |
| Negotiation continues | Browser processes token from 401/200 | Server calls `acceptSecContext` and may emit response token |
| Login completes | Browser receives content and possibly a session cookie | Spring Authentication and app authorization |
| User refreshes or logs out locally | Browser may reuse tickets still in OS cache | Spring may re-challenge with Negotiate or use session |

**Browsers do not send plaintext domain passwords in normal Kerberos.** They also **do not send the TGT** to the web server just for SSO; they present a credential scoped to the **HTTP service principal**. However, SPNEGO on Windows can fall back to NTLM, so you cannot assume every Negotiate token is completely free of sensitive credential material. Browser trust policy and mechanism restrictions remain essential.

### 5.1. The Browser Does Not Decide Whether the User Is Admin

After Kerberos validation, the server may know a principal such as `lan@EXAMPLE.ORG`. However, **the application** must verify enabled status, tenant, roles, and resource permissions. A valid ticket proves only authentication within the realm/trust policy, not permission to view another user's data or every internal API.

### 5.2. The Browser May Show a Prompt or Fallback Form

If the OS lacks a TGT, the host is not allowlisted, or the mechanism is unsupported, the client may omit the Negotiate token; depending on browser/app config, the user sees a credential prompt, HTTP 401, or an app-provided form/OIDC/SAML fallback. Do not assume a single universal behavior across all browsers/OSes.

### 5.3. Silent SSO Is Different from Credential Delegation

**Integrated Authentication** proves the user to the web server. **Kerberos delegation** allows the web server to use delegated credentials to call **another service** on the user's behalf, requiring dedicated KDC/AD, service account, browser policy, and permissions. Allowing the browser to send Negotiate to Portal **does not mean** Portal has permission to call a database/API as the user.

## 6. Configuring Edge, Chrome, and Firefox

If any arbitrary website could return 401 Negotiate and make browsers automatically send credentials, users could be lured to untrusted hosts. For this reason, browsers maintain trusted-site lists.

### 6.1. Microsoft Edge / Chromium: AuthServerAllowlist

The Microsoft Edge enterprise policy `AuthServerAllowlist` defines servers permitted to use Integrated Authentication when challenged. When unconfigured, Edge may rely on whether the site is classified as intranet under platform policy; explicit configuration avoids surprises.

Example approved host list:

~~~text
AuthServerAllowlist = intranet.example.org,reports.example.org
~~~

Verify effective policy at `edge://policy`. In enterprises, deploy via appropriate GPO/MDM/ADMX; never ask users to add a `*` wildcard or third-party-owned hosts. Broad wildcards covering all subdomains may include untrusted sites and expose credentials.

`AuthNegotiateDelegateAllowlist` is a **different policy** allowing **credential delegation** to designated servers. If an app only needs user SSO login to an intranet page, **do not enable delegation by default**.

~~~text
AuthServerAllowlist
    -> browser is permitted Integrated Authentication with host

AuthNegotiateDelegateAllowlist
    -> browser is permitted to delegate Kerberos credentials to host
       (only when KDC/server-side policy also allows)
~~~

### 6.2. Chrome / Chromium

Chrome Enterprise provides HTTP authentication policies such as `AuthServerAllowlist` and `AuthNegotiateDelegateAllowlist`, though deployment/OS integration varies by platform and version. Inspect `chrome://policy` on an actual device. Older documentation uses legacy `AuthServerWhitelist`/command-line flags; **do not copy-paste those settings onto current versions without checking docs**.

### 6.3. Firefox: Authentication.SPNEGO

Firefox Enterprise provides the `Authentication` policy with `SPNEGO` for allowed sites and `Delegated` as a separate list for delegation. Example sandbox policy:

~~~json
{
  "policies": {
    "Authentication": {
      "SPNEGO": [
        "https://intranet.example.org",
        "https://reports.example.org"
      ],
      "Delegated": []
    }
  }
}
~~~

Preferences to know:
- `network.negotiate-auth.trusted-uris`: sites permitted to use SPNEGO.
- `network.negotiate-auth.delegation-uris`: sites permitted Kerberos delegation.
- `network.automatic-ntlm-auth.trusted-uris`: separate configuration for NTLM.
- `about:config` can be inspected in a sandbox; production uses enterprise policies to stop users from opening arbitrary hosts.

Per Mozilla policy docs, Firefox matching may accept a domain and its subdomains (dot-boundary). If you allow `https://example.org`, do not assume only the apex host receives credentials; verify subdomain scope and choose narrow, clearly owned domains.

### 6.4. Browsers Without a Ticket or Unmanaged Devices

Firefox/Chrome/Edge on Linux/macOS also depend on GSS libraries/credential caches, not just a JSON policy. Safari and mobile browsers vary by OS and managed-device configuration. For automated REST clients, `curl --negotiate`, Java HTTP client/GSS, or an appropriate agent handles it; not every HTTP client acquires Kerberos tickets automatically like a desktop browser.

**Invariant:** Browser policy only decides whether the client may **initiate/continue Negotiate**. It does not fix an SPN, create a server keytab, or replace authorization.

## 7. SPN, DNS, Realm, and Keytab on the Server

In the example environment:

~~~text
Public URL  = https://intranet.example.org/private
SPN         = HTTP/intranet.example.org@EXAMPLE.ORG
Service key = /run/secrets/http-intranet.keytab
KDC/realm   = EXAMPLE.ORG
~~~

**Breakdown:**
- `HTTP/` is the Kerberos service class (still `HTTP/` when the site uses HTTPS).
- `intranet.example.org` is the FQDN the browser/GSS selects as the Kerberos service target.
- `EXAMPLE.ORG` is the realm; it may differ from the hostname domain in cross-realm setups.
- `keytab` on the web service holds secret keys for the service principal. Only the public website owner/service account should have access.
- **KVNO** is the key version number; a stale keytab after password rotation may fail to decrypt new tickets.
- Enctype (AES types), clock skew, key rotation, and duplicate SPNs also affect GSS validation.

### 7.1. Common Failures with Aliases and Load Balancers

The browser visits `https://intranet.example.org` while the app runs behind an LB at `app01.internal.example.org`. The client usually requests a ticket for `HTTP/intranet.example.org`, **not** automatically for the internal node `app01`. Thus you must decide:

**Model A – app is the acceptor:** The LB forwards `Authorization: Negotiate ...` to the app, and the app holds a keytab matching the public SPN to verify the GSS token. TLS/mTLS between LB→app, source network policy, and forwarded headers must be protected.

**Model B – gateway is the acceptor:** The gateway receives/verifies SPNEGO using the keytab and sends the **verified identity** to the app over a secure channel (mTLS/signed identity assertion/headers stripped and overwritten by the gateway). The app never trusts an `X-User` header sent directly by a browser.

If the LB consumes Authorization itself while the app still demands Negotiate, a 401 loop results. If the app uses a keytab only for an internal SPN, GSS rejects. The fix is **aligning the public SPN and termination point**, not disabling validation.

### 7.2. Environment Inspection Commands

**Windows domain workstation / admin:**

~~~powershell
klist
setspn -Q HTTP/intranet.example.org
~~~

`klist` inspects user TGT/service tickets; `setspn -Q` queries registered SPNs in AD (with proper privileges/environment). Do not make AD changes with `setspn -S` in production without approval.

**Linux/macOS with Kerberos tools:**

~~~bash
klist
kvno HTTP/intranet.example.org
~~~

`kvno` normally needs a TGT and network KDC and may request a fresh ticket for the service principal. On a server with read access to the keytab:

~~~bash
klist -k /run/secrets/http-intranet.keytab
~~~

These are **environment-dependent diagnostic commands**; they have no fixed stdout. Never paste ticket caches, keytabs, or `Authorization` tokens into bug reports.

### 7.3. TLS, Channel Binding, and Proxies

SPNEGO HTTP authentication **does not automatically encrypt request bodies/headers**; use public HTTPS, HSTS, and Secure/HttpOnly session cookies. If the environment enforces **Extended Protection for Authentication / channel binding**, certain TLS termination topologies trigger `GSSException: Channel binding mismatch`. Investigate certificates, TLS endpoints, binding policies, reverse proxies, and GSS implementation—**never** fix it by blindly disabling EPA/TLS verification.

## 8. How Does Spring Security Kerberos Work?

Spring Security Kerberos is a separate extension. Documentation for version **2.2.0** states it is built/tested with **JDK 17, Spring Security 6.5.1, and Spring Framework 6.2.8**, making it well suited for learning on Spring Boot 3.5.x. When deploying, verify effective dependency versions and the container runtime before go-live.

| Component | Responsibility |
| --- | --- |
| `SpnegoEntryPoint` | Returns HTTP 401 + `WWW-Authenticate: Negotiate` so the browser begins SSO |
| `SpnegoAuthenticationProcessingFilter` | Extracts token from `Authorization`, creates `KerberosServiceRequestToken`, and calls AuthenticationManager |
| `KerberosServiceAuthenticationProvider` | Validates the token using the ticket validator; integrates `UserDetailsService` |
| `SunJaasKerberosTicketValidator` | Uses Java/JGSS and servicePrincipal/keytab to accept Kerberos service tokens |
| `UserDetailsService` | Loads user details, enabled state, and GrantedAuthorities; does NOT perform Kerberos verification |
| `SecurityFilterChain` | Registers entry point/filter and guards unauthorized resources |
| `SecurityContext`/Session | Holds the app's resulting authentication; does not store the Kerberos TGT |
| `AuthorizationManager`/Business service | Checks roles, tenant, resource ownership, and method permissions |

### 8.1. Filter Flow

~~~text
GET /whoami without Spring Security authentication
        |
        v
Authorization filter requires authenticated()
        |
        v
ExceptionTranslationFilter -> SpnegoEntryPoint
        |
        | 401 WWW-Authenticate: Negotiate
        v
Browser + OS/GSS + KDC
        |
        | Authorization: Negotiate <base64 token>
        v
SpnegoAuthenticationProcessingFilter
        |
        v
KerberosServiceRequestToken -> AuthenticationManager
        |
        v
KerberosServiceAuthenticationProvider
        |
        +--> SunJaasKerberosTicketValidator
        |       verify GSS token with SPN/keytab
        |
        +--> UserDetailsService
                active user + application authorities
        |
        v
Spring Security authenticated principal
        |
        v
Application authorization -> 200 or 403
~~~

**Never write a controller that Base64-decodes the header and extracts a username via regex**. Any decodable bytes can be forged. Only a GSS acceptor using a trusted service key and mechanism policy can authenticate.

## 9. Spring Boot 3.5 / Java 17 Project Integrating SPNEGO

The project below demonstrates **browser→server authentication only**, without backend delegation or an embedded KDC. The Maven/JDK17 build works once dependencies are available; **end-to-end Kerberos login runs only once real AD/KDC, SPN, keytab, browser trusted-site policy, and HTTPS ingress are in place**.

### 9.1. Structure

~~~text
negotiate-web/
  pom.xml
  src/main/
    java/demo/NegotiateApplication.java
    resources/application.yml
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.1</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>negotiate-web</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
      <groupId>org.springframework.security.kerberos</groupId>
      <artifactId>spring-security-kerberos-core</artifactId>
      <version>2.2.0</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.security.kerberos</groupId>
      <artifactId>spring-security-kerberos-web</artifactId>
      <version>2.2.0</version>
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

The Spring Boot BOM manages Spring Security; extension 2.2.0 is tested with Spring Security 6.5.1. Check `mvn dependency:tree` and dependency alignment for your actual patch versions. Do not use Spring Security Kerberos 1.x tutorials relying on `javax.servlet` with Boot 3.x Jakarta Servlet without verifying compatibility.

### 9.3. application.yml

~~~yaml
server:
  port: 8080

kerberos:
  service-principal: HTTP/intranet.example.org@EXAMPLE.ORG
  keytab-path: /run/secrets/http-intranet.keytab
~~~

The keytab contains a secret key and must be mounted read-only from a secret manager/volume with minimal permissions. Never commit it to Git, container images, the classpath, or store it in source. Never expose production keytabs in user downloads or logs.

### 9.4. NegotiateApplication.java

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class NegotiateApplication {

    public static void main(String[] args) {
        SpringApplication.run(NegotiateApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        // DEMO: every verified Kerberos user receives ROLE_USER.
        // Production: query directory/DB, enabled status, tenant, roles.
        return name -> new User(
                name, "{noop}unused",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            Environment env,
            UserDetailsService users) throws Exception {

        String principal =
                env.getRequiredProperty("kerberos.service-principal");
        String path =
                env.getRequiredProperty("kerberos.keytab-path");

        var validator = new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(new FileSystemResource(path));
        validator.setDebug(false);

        var provider = new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);

        var authManager = new ProviderManager(provider);
        var spnegoFilter = new SpnegoAuthenticationProcessingFilter();
        spnegoFilter.setAuthenticationManager(authManager);

        // Create the filter internally for SecurityFilterChain; do not register
        // another servlet Filter @Bean to avoid double execution.
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(new SpnegoEntryPoint()))
                .addFilterBefore(
                        spnegoFilter, BasicAuthenticationFilter.class)
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String home() {
            return "Open /whoami for HTTP Negotiate";
        }

        @GetMapping("/whoami")
        Map<String, Object> whoami(Authentication auth) {
            return Map.of(
                    "authenticated", auth.isAuthenticated(),
                    "principal", auth.getName());
        }
    }
}
~~~

**How the code works:**
- `SpnegoEntryPoint` challenges the browser with Negotiate if `/whoami` is unauthenticated.
- `SpnegoAuthenticationProcessingFilter` reads Authorization Negotiate and invokes `ProviderManager`.
- `KerberosServiceAuthenticationProvider` uses the Kerberos/JGSS validator and `UserDetailsService` to produce the authenticated principal.
- `SunJaasKerberosTicketValidator` receives the service principal/keytab from protected configuration.
- `users()` is **demo-only**: it grants ROLE_USER to every verified Kerberos principal; production must check directory/user enabled state, tenant, account status, and per-resource policies.
- The filter is instantiated inside the chain method, **not exposed as a @Bean for the Servlet container to register separately** (avoiding duplicate execution outside the security chain).
- This is not a Kerberos delegation demo; there are no backend API calls on the user's behalf.

**Important limitation:** This code sample is a reference configuration for extension 2.2.0; under different framework/BOM patches or in production setups with multiple chains, authentication failures, fallbacks, and session strategies require dedicated integration tests. Never conclude from `SpnegoEntryPoint` alone that the keytab is valid.

### 9.5. Running the Project

After registering `HTTP/intranet.example.org@EXAMPLE.ORG` and mounting a valid keytab, run with JDK 17:

~~~bash
mvn spring-boot:run
~~~

For the browser to perform Kerberos SSO, open the configured HTTPS public hostname through ingress, e.g. `https://intranet.example.org/whoami`. Public `GET /` returns:

~~~text
Open /whoami for HTTP Negotiate
~~~

An unauthenticated request to `/whoami` may receive:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

After browser/GSS completion and Spring Security acceptance, the response **looks like**:

~~~json
{
  "authenticated": true,
  "principal": "lan@EXAMPLE.ORG"
}
~~~

This JSON is a **sample**; the actual principal depends on the realm/user. Without a KDC, keytab, SPN, public TLS host, and browser trusted-site policy, you cannot conclude SSO works from the Maven command alone. You normally cannot use `http://localhost:8080` to test a public SPN; the browser may not request the right ticket.

## 10. Standalone Java 17 Example: HTTP Gate Before GSS

This sample does not require a Kerberos realm. It illustrates only **Host allowlist + HTTP Authorization Negotiate syntax + Base64 decode + length guard** prior to handing bytes to a GSS validator. The `PASS_TO_GSS` state **does not mean authentication succeeded**. The length limit of 64 in the demo is purely for easy testing and is much smaller than production GSS tokens.

**File `NegotiateHeaderDemo.java`:**

~~~java
import java.util.Base64;
import java.util.Set;

public class NegotiateHeaderDemo {

    enum Decision {
        CHALLENGE, DENY_HOST, DENY_SCHEME,
        DENY_FORMAT, DENY_SIZE, PASS_TO_GSS
    }

    private static final Set<String> APPROVED = Set.of(
            "intranet.example.org", "reports.example.org");

    static Decision decide(String host, String authorization) {
        if (!APPROVED.contains(host)) {
            return Decision.DENY_HOST;
        }
        if (authorization == null || authorization.isBlank()) {
            return Decision.CHALLENGE;
        }

        int space = authorization.indexOf(' ');
        if (space < 0 ||
            !authorization.substring(0, space)
                    .equalsIgnoreCase("Negotiate")) {
            return Decision.DENY_SCHEME;
        }

        String encoded = authorization.substring(space + 1).trim();
        if (encoded.isEmpty()) {
            return Decision.DENY_FORMAT;
        }
        if (encoded.length() > 64) {
            return Decision.DENY_SIZE;
        }
        try {
            byte[] bytes = Base64.getDecoder().decode(encoded);
            return bytes.length == 0
                    ? Decision.DENY_FORMAT
                    : Decision.PASS_TO_GSS;
        } catch (IllegalArgumentException ex) {
            return Decision.DENY_FORMAT;
        }
    }

    static void show(String label, String host, String auth) {
        System.out.println(label + "=" + decide(host, auth));
    }

    public static void main(String[] args) {
        show("missing", "intranet.example.org", null);
        show("evilHost", "evil.example.org", null);
        show("basic", "intranet.example.org", "Basic dXNlcjpwYXNz");
        show("bareNegotiate", "intranet.example.org", "Negotiate");
        show("emptyNegotiate", "intranet.example.org", "Negotiate ");
        show("invalidBase64", "intranet.example.org", "Negotiate !!!");
        show("fakeShape", "intranet.example.org", "Negotiate dG9rZW4=");
        show("tooLong", "intranet.example.org",
                "Negotiate " + "A".repeat(65));
        show("reports", "reports.example.org", "Negotiate dG9rZW4=");
    }
}
~~~

Run with JDK 17:

~~~bash
javac NegotiateHeaderDemo.java
java NegotiateHeaderDemo
~~~

**Exact stdout:**

~~~text
missing=CHALLENGE
evilHost=DENY_HOST
basic=DENY_SCHEME
bareNegotiate=DENY_SCHEME
emptyNegotiate=DENY_FORMAT
invalidBase64=DENY_FORMAT
fakeShape=PASS_TO_GSS
tooLong=DENY_SIZE
reports=PASS_TO_GSS
~~~

**Explanation:**

- `missing`: if the endpoint is protected, the server should return a 401 challenge.
- `evilHost`: a host outside the internal allowlist is rejected. In a real app, the host must be the canonical host from a trusted ingress; raw `Host`/`X-Forwarded-Host` can be spoofed.
- `basic` is not the authentication scheme selected by the application.
- `bareNegotiate` lacks a token and separator, so this classifier returns `DENY_SCHEME`. `emptyNegotiate` has a separator with an empty token, yielding `DENY_FORMAT`.
- `invalidBase64` fails syntax; `fakeShape` decodes to the bytes of the word "token", **not a Kerberos token**.
- `tooLong` exceeds the illustrative 64-character limit; production GSS tokens can be several KB long, so choose limits per framework/container/threat model rather than this threshold.
- `reports` is another allowlisted host, yet does not prove Reports' SPN/keytab is valid.

**Do not deploy this program as a Kerberos authentication provider.** In production, Spring Security Kerberos/GSS must cryptographically verify the token, negotiated mechanism, and service principal before granting access. A decodable token could be fake, NTLM, or a tampered Kerberos service ticket.

## 11. SPNEGO vs. Session, Logout, and CSRF

### 11.1. An HTTP Session Is Not a Domain Session

After a successful SPNEGO exchange, Spring Security can hold `Authentication` in `SecurityContext` and the HTTP session. The browser sends the session cookie on subsequent requests without necessarily repeating the Kerberos handshake each time.

- **Local app logout** can invalidate Portal's session/cookie.
- **TGT/service tickets in the OS cache** may still exist: the browser can silently re-SSO immediately upon seeing 401 Negotiate.
- **Locking/logging out the OS domain user** has a separate lifecycle. The website server cannot arbitrarily wipe client-side TGTs remotely.
- If the session expires or the account is disabled, the application must check authorization/status properly rather than trusting a cache forever.
- If the application uses stateless per-request auth, monitor overhead, replay/connection context, and gateway behavior rather than applying stateful-session assumptions.

### 11.2. Kerberos Does Not Automatically Prevent Business-Form CSRF

The browser can automatically attach credentials (Negotiate or cookies) when navigated to a trusted host. Thus a state-changing POST can still suffer from **Cross-Site Request Forgery** without controls. For Servlet apps with browser forms/APIs, preserve CSRF protection, cookie policies, and per-action authorization. Never disable CSRF just because "the user already has Kerberos SSO".

### 11.3. CORS Is Not an Authorization Mechanism

A cross-origin SPA needs proper CORS/credentials handling, yet CORS does not replace SPNEGO/GSS checks or grant server-side permissions. Never combine `Access-Control-Allow-Origin: *` with credentials or set wildcards to bypass Integrated Auth browser restrictions. Prefer same-origin or a BFF/gateway with clear trust boundaries for browser apps.

### 11.4. Session Fixation and Cookies

After authentication, Spring Security must apply a session fixation strategy and cookie settings (`Secure`, `HttpOnly`, `SameSite`, idle/absolute timeouts) per policy. Kerberos authenticates the user; it does not validate the contents of an attacker-planted cookie. Do not share session cookies across unrelated subdomains/tenants.

## 12. TLS, Mutual Authentication, Channel Binding

### 12.1. TLS Is a Separate Requirement

Per RFC 4559, HTTP Negotiate is an authentication mechanism and **does not automatically protect the full HTTP body/headers**. Use HTTPS, certificate validation, HSTS, and secure cookies. A SPNEGO GSS token is Base64-carried in a header, not encryption for HTTP messages.

### 12.2. Mutual Authentication / AP-REP

Kerberos can perform mutual authentication: the service sends a GSS output token and the browser processes it to verify the server. In HTTP Negotiate, a final token can appear in `WWW-Authenticate` **even on a 200 response**, so not every `WWW-Authenticate` indicates an error.

Reverse proxies/LBs must pass continuation/final tokens per GSS/context lifecycle; never strip the header to "avoid leaking info" while the protocol still needs it.

### 12.3. Extended Protection and Channel Binding

Windows Extended Protection for Authentication can require TLS channel binding to mitigate certain relay attacks. When TLS terminates at a gateway while Kerberos is accepted at the backend, client/proxy/backend configurations can disagree and trigger `GSSException: Channel binding mismatch`. Never fix this by unconditionally disabling EPA; reconcile TLS termination architecture, SPN, certificates, browser/server policies, and Java GSS implementation.

## 13. NTLM Fallback: Negotiate Does Not Guarantee Kerberos

RFC 4559 notes that Negotiate on Windows can operate with SPNEGO wrapping **either Kerberos or NTLM**. A site seeing `Authorization: Negotiate ...` cannot claim "Kerberos verified" from the scheme name alone.

**When does NTLM fallback happen?** It can occur when the client fails to obtain a Kerberos service ticket: unregistered/duplicate SPN, wrong IP/alias, DNS/KDC failure, clock skew, missing trust, or browser/OS policy picking another mechanism. Do not guess the cause; inspect the actual negotiated mechanism.

**Security consequences:**
- NTLM has different trust, mutual authentication, and delegation semantics from Kerberos and carries relay risks in unfavorable configs.
- Any application requiring **Kerberos-only** must ensure **server/OS/GSS mechanism selection and domain/browser policy** actively reject NTLM rather than merely checking the `Authorization` prefix.
- Never enable wildcard trusted hosts or delegation to "fix" NTLM/401 errors.
- Inspect AD/KDC and the accepted mechanism rather than merely checking that `klist` shows a TGT.

### 13.1. Double-Hop and Delegation Differ from Single-Hop SSO

Browser Lan can Kerberos-SSO to Portal A; however, A calling Reports B as Lan is a **delegation** problem that does not happen automatically:

~~~text
Browser Lan -- Kerberos HTTP/portal --> Portal A
                                        |
                                        +-- no delegation:
                                        |     A cannot use user ticket
                                        |     for HTTP/reports
                                        |
                                        +-- constrained delegation:
                                        |     AD/KDC lets A act for user to
                                        |     approved SPN list
                                        |
                                        +-- OAuth2 Token Exchange/OBO:
                                              uses API delegation per
                                              separate audience/scopes
~~~

Prefer **constrained delegation** for Kerberos backends rather than enabling broad unconstrained delegation across services. Edge has `AuthNegotiateDelegateAllowlist` and Firefox has `Authentication.Delegated`; neither replaces KDC/server-side delegation policy. If user impersonation is not required, use a service identity with explicit machine permissions or appropriate OIDC/OAuth2 flows.

## 14. Step-by-Step Debugging: From Browser to KDC and App

~~~text
A. Protected request without auth:
   Does server return 401 + WWW-Authenticate: Negotiate?
   |
   +-- No: entry point, filter chain, gateway/route
   |
   +-- Yes: Does browser automatically send Authorization?
             |
             +-- No: Edge/Chrome/Firefox trusted host policy,
             |          OS GSS support, TGT, user profile
             |
             +-- Yes: Did KDC issue HTTP/fqdn service ticket?
                       |
                       +-- No: SPN, DNS, realm trust,
                       |          time skew, KDC connectivity
                       |
                       +-- Yes: Does header reach acceptor?
                                  |
                                  +-- No: proxy stripped Authorization,
                                  |          407 vs 401, routing
                                  |
                                  +-- Yes: Does GSS accept context pass?
                                             |
                                             +-- No: service keytab, KVNO,
                                             |          enctype, SPN/EPA
                                             |
                                             +-- Yes: UserDetails/authorization?
                                                        |
                                                        +-- No: user disabled,
                                                        |          tenant/roles
                                                        |
                                                        +-- Yes: 200 resource
~~~

### 14.1. Client / Host Inspection Commands

~~~bash
# Requires Kerberos credentials, GSS-enabled curl, and a real HTTPS server:
curl --negotiate -u : -v https://intranet.example.org/whoami
~~~

`curl --negotiate -u :` works only when the curl build supports GSS/SPNEGO and has an appropriate OS cache. `-v` can print Authorization tokens: **use only in a sandbox and redact before sharing logs**. Never use `-k` to disable TLS validation just to make tests pass.

`klist` inspects the ticket cache; `kvno HTTP/intranet.example.org` can request a service ticket in a Kerberos environment; `setspn -Q HTTP/intranet.example.org` queries AD SPNs (with admin permissions). Output depends on the environment and has no fixed stdout.

### 14.2. Symptoms and Meanings

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Initial 401 then 200 | Normal challenge-response | Verify browser request carries Negotiate token |
| 401 loop, no Authorization | Browser does not send credentials | Edge/Firefox policy, OS TGT, hostname |
| 401 loop, Authorization sent | GSS rejection or continuation token stripped | SPN/keytab, KDC, gateway, mechanism |
| 407 from proxy | Forward proxy authentication | Proxy/PAC and Proxy-Authenticate |
| `KRB5KDC_ERR_S_PRINCIPAL_UNKNOWN` | SPN missing in KDC | `HTTP/fqdn` registration |
| `KRB_AP_ERR_MODIFIED` | Wrong keytab/service account, duplicate SPN | KVNO, key rotation, duplicate SPNs |
| `KRB_AP_ERR_SKEW` | Clock mismatch | NTP on client/KDC/server |
| `GSSException: Defective token` | Corrupted/wrong GSS token | Proxy header truncation, mechanism |
| `GSSException: Channel binding mismatch` | Mismatched EPA/TLS binding | TLS offload/cert/context |
| Login passes, yet 403 | Authorization denial or CSRF | Role, account, tenant, CSRF on POST |
| Fails only in Firefox | Firefox SPNEGO allowlist/policy | `Authentication.SPNEGO` |
| Fails only in Edge | Edge AuthServerAllowlist/intranet detection | `edge://policy` |
| IP vs. FQDN difference | SPN target mismatch | DNS/FQDN, aliases |
| Fails through proxy | Header, SPN, or gateway termination | Authorization passthrough mode |
| Auto-SSOs again after app logout | OS TGT/ticket cache remains | Expected lifecycle; clarify UX |
| Backend "on behalf of" fails | Delegation not configured | Constrained delegation/OBO |

### 14.3. Safe Logging

Log a sanitized correlation ID, canonical host/SPN/realm, auth scheme type, accepted mechanism if safely exposed by the API, success/error category, internal user/tenant, and latency. **Never log** raw SPNEGO tokens, HTTP Authorization headers, TGTs, service tickets, keytabs, session cookies, passwords, overly verbose GSS traces, or private user attributes. Use GSS debug logs only in a sandbox.

## 15. Technical and Security Test Matrix

| Test Case | Setup | Expected Outcome |
| --- | --- | --- |
| Happy path Windows domain | Valid TGT, SPN/keytab, and browser allowlist | 401→Negotiate→200 |
| Happy path Firefox | Valid SPNEGO policy, OS credential cache | Token sent and verified |
| No Authorization | Protected GET, no session | 401 `WWW-Authenticate: Negotiate` |
| Browser untrusted host | Host not on allowlist | Does not silently send credentials |
| No TGT | Browser has no credentials | 401/fallback per policy; no fake user |
| Wrong SPN | Browser requests ticket for wrong alias | GSS/KDC fails |
| Wrong keytab/KVNO | Server uses stale secret | GSS rejects |
| Duplicate SPN | AD has principal conflict | Fails or policy ambiguity; investigate AD |
| NTLM fallback | Kerberos KDC/SPN fails; NTLM client permits | For Kerberos-only: reject |
| Wrong realm | Untrusted user/realm | Reject per policy |
| Initial 401 stripped | Gateway removes WWW-Authenticate | Browser never starts SSO |
| Authorization stripped | Gateway strips token | 401 loop; fix reverse proxy |
| 401 continuation stripped | Proxy strips GSS output token | Negotiation never completes |
| 200 final token stripped | Proxy strips final Negotiate token | Mutual context may fail |
| 407 from forward proxy | Separate proxy requires auth | Handle Proxy-Authenticate; do not confuse with app |
| Oversized header | Group-heavy SPNEGO token | Reasonable size policy without truncation |
| TLS downgrade | HTTP fails to protect token | Deny/redirect per HTTPS/HSTS policy |
| Channel binding mismatch | Differing TLS termination/EPA policy | Fail; investigate rather than disabling protection |
| Authenticated but disabled user | GSS passes, directory disables user | Spring/app denies |
| Cross-tenant resource | Valid principal accesses another tenant | 403 |
| POST without CSRF | Browser is Kerberos-authenticated | CSRF filter denies per policy |
| Local logout | Spring session invalidated, OS TGT remains | May re-SSO; do not claim domain logout |
| Multi-node | LB callbacks/keys properly designed | Consistent acceptance |
| Unauthorized double-hop | A tries to impersonate user to B | Reject without delegation rights |
| Delegation wildcard | Browser/domain policy overly broad | Security review fails |
| Host header spoofing | Client sends forged forwarded host | Trusted ingress does not turn it into identity |

### How to Prove Kerberos Rather Than Just Negotiate

Inspect the server-side **accepted GSS mechanism**, appropriate audit/logs, and confirm the client ticket cache holds an `HTTP/fqdn` service ticket. Even if `klist` on the client shows a TGT, `Authorization: Negotiate` alone does not prove Kerberos was used. For Kerberos-only tests, intentionally trigger NTLM fallback conditions and confirm the server rejects it if policy requires.

### Testing Spring Security Separately

Use unit/integration tests to verify filters/entry point, `UserDetailsService`, account status, and `SecurityContext`. Mocks can verify 401/authorization wiring, yet **do not prove cryptographic GSS ticket validation**. Real validation testing requires a KDC/AD sandbox and test keytab. Never use domain admin keytabs or live user credentials in CI.

## 16. Operations and Hardening

**Service account/keytab:** enforce least privilege, read-only secret mounts, coordinated rotation with KVNO/enctype/certificates/trust, and never store in Git/images. Across multiple nodes, distribute secrets only to workloads sharing the approved SPN; never copy them to every container.

**Browser policy:** manage server-name allowlists and delegation lists separately; inspect `edge://policy`, `chrome://policy`, and Firefox enterprise configurations; disable broad wildcards/unknown domains. Enforce canonical HTTPS origins and valid TLS certs.

**Network:** verify KDC/AD routing, DNS, client/server NTP, firewalls, reverse proxy authentication termination, trusted forwarded headers, and Authorization passthrough. Never raise header-size limits endlessly without considering DoS; Kerberos tokens can grow due to PAC/groups, so choose realistic bounds.

**Mechanism policy:** if the product requires Kerberos-only, enforce it at OS/GSS/domain/server layers and run negative NTLM tests. Never assume `Negotiate=Kerberos`.

**App authorization:** internally enforce user enabled state, realm trust, tenant membership, roles, resource ownership, and CSRF. A principal from a trusted domain can still be unauthorized to use an application.

**UX/fallback:** if off-domain devices lack tickets, provide an approved form/OIDC fallback rather than silently lowering security. A page explaining "SSO is unavailable on this device" is far better than a 401 loop.

### Runbook if a Keytab Is Exposed

1. Contain the affected service/credential, block its scope of use, and prevent further access.
2. Identify every node, secret store, backup, and log that touched the keytab.
3. Coordinate AD/KDC rotation of the service account key and update keytab/KVNO across all service acceptors.
4. Assess still-valid tickets/sessions and revocation options in the actual Kerberos environment.
5. Audit accepted mechanisms, browser allowlists, and app authorization events.
6. Never attach keytabs/raw tokens to support tickets; use redacted logs and correlation IDs.
7. Run regression tests for wrong keytab/duplicate SPN/NTLM fallback and confirm the service works with the new key.

## 17. Practice Exercises

**Exercise 1 – Layering.** Diagram Kerberos/KDC, GSS-API/SSPI, SPNEGO, and HTTP Negotiate. Place TGT, TGS-REQ, service ticket, AP-REQ, WWW-Authenticate, and Authorization at their exact stages.

**Exercise 2 – Trace reading.** Explain the sequence `GET /private → 401 Negotiate → GET Authorization Negotiate → 200`. State when 401 continuation/200 final tokens occur and why proxies must not strip them.

**Exercise 3 – Browser role.** A browser is domain-logged-in and the user opens the intranet. Does it send a password, a TGT, or a service ticket? How does the KDC help? Who verifies the token?

**Exercise 4 – Edge policy.** Write a narrow `AuthServerAllowlist` for intranet hosts without enabling `AuthNegotiateDelegateAllowlist`. Explain the difference between authentication and delegation.

**Exercise 5 – Firefox.** Write an `Authentication.SPNEGO` policy for one HTTPS host with an empty `Delegated` list. Check subdomain matching behavior in Mozilla docs; why is an overly broad domain dangerous?

**Exercise 6 – SPN.** The browser requests ticket `HTTP/intranet.example.org`, yet the keytab only holds `HTTP/app01.internal.example.org`. Identify the failure and how to fix SPN/DNS/proxy/keytab properly without bypassing GSS validation.

**Exercise 7 – Java 17.** Run `NegotiateHeaderDemo.java` and verify all 9 stdout lines. Explain why `fakeShape=PASS_TO_GSS` does not mean "logged in".

**Exercise 8 – Spring Boot.** In a KDC sandbox, run the project from section 9 with a test SPN/keytab. Observe 401/Authorization/200, then test a disabled user and insufficient roles.

**Exercise 9 – NTLM.** Given `Authorization: Negotiate`, describe how to verify the actual mechanism and why checking only the prefix does not prove Kerberos-only.

**Exercise 10 – Channel binding.** If changing a TLS proxy causes a GSS channel-binding mismatch, which layers must you inspect before changing policy?

**Exercise 11 – CSRF/logout.** Why can a user silently re-SSO without a password after logging out locally? Why does a state-changing POST still need CSRF protection?

**Exercise 12 – Double-hop.** Portal A completed Kerberos login and needs to call API B on the user's behalf. State the requirements for constrained delegation or OAuth2 OBO; explain why a service ticket for A cannot simply be forwarded to B.

**Completion criteria:** The learner accurately presents the chain **OS/KDC ticket cache → browser SSPI/GSS token → SPNEGO/HTTP 401/Authorization → SPN/keytab GSS accept → Spring Authentication → application authorization** and completely distinguishes **Negotiate vs. Kerberos, SSO vs. delegation, and authentication vs. authorization**.

## 18. Official Sources

- RFC 4559 – HTTP Negotiate/SPNEGO, 401 challenge, Authorization, multi-step/final response: https://www.rfc-editor.org/rfc/rfc4559
- RFC 4178 – The Simple and Protected GSS-API Negotiation Mechanism: https://www.rfc-editor.org/rfc/rfc4178
- RFC 4120 – Kerberos Network Authentication Service v5: https://www.rfc-editor.org/rfc/rfc4120
- RFC 4121 – Kerberos GSS-API mechanism: https://www.rfc-editor.org/rfc/rfc4121
- Spring Security Kerberos 2.2.0 – Introduction and tested versions: https://docs.spring.io/spring-security-kerberos/reference/introduction.html
- Spring Security Kerberos – Spring and Spring Security Kerberos: https://docs.spring.io/spring-security-kerberos/reference/ssk.html
- Spring Security Kerberos – SpnegoEntryPoint: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html
- Spring Security Kerberos – SpnegoAuthenticationProcessingFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
- Microsoft Edge AuthServerAllowlist: https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/authserverallowlist
- Microsoft Edge AuthNegotiateDelegateAllowlist: https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/authnegotiatedelegateallowlist
- Firefox Enterprise Authentication/SPNEGO policy: https://firefox-admin-docs.mozilla.org/reference/policies/authentication/
- Oracle Java – JAAS/Kerberos JGSS: https://docs.oracle.com/en/java/javase/26/security/part-i--secure-authentication-using-java-authentication-authorization-service-jaas.html
- Microsoft Learn – Kerberos double-hop with Microsoft Edge: https://learn.microsoft.com/en-us/troubleshoot/developer/webapps/iis/www-authentication-authorization/kerberos-double-hop-authentication-edge-chromium

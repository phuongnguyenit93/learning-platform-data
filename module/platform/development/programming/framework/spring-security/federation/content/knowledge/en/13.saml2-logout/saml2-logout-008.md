# Separating Local Logout and Federated Logout Endpoints in SAML 2.0

> **Module:** Spring Security – federation. **Group:** SAML2 Logout. This lesson guides building two independent actions: **Local Logout** terminating only the session at the Service Provider (SP), and **SAML Single Logout (SLO)** sending a request to the Identity Provider (IdP) to coordinate federated logout. Examples use Java 17, Spring Boot 3.5.x, and Spring Security 6.5.x on the Servlet stack.

## 1. Objectives and Prerequisites

After this lesson, you should be able to:

1. Distinguish the SP's HTTP/SecurityContext session from the SSO session at the IdP and sessions at other SPs.
2. Identify accurately **`POST /logout`** (local-only), **`POST /saml2/logout`** (SP/RP-initiated SLO), and **`POST /logout/saml2/slo`** (receiving SAML LogoutRequest/LogoutResponse from the IdP).
3. Explain the direction of `LogoutRequest`, `LogoutResponse`, `SAMLRequest`, `SAMLResponse`, `InResponseTo`, `NameID`, and `SessionIndex`.
4. Separate the two endpoints in the Spring Security DSL without writing a custom session-deleting controller and assuming you logged out per framework standards.
5. Understand SLO prerequisites: IdP `SingleLogoutService`, SP signing key, public certificates, metadata, transaction correlation, and session repository.
6. Protect user actions with POST/CSRF; verify signatures and issuers of inbound SLO messages with standard validators.
7. Test both independent behaviors, handling IdP-initiated SLO, timeouts, partial logout, and multi-device limits.
8. Design UX messaging that never claims "logged out everywhere" without evidence.

**Prerequisites:** SAML2 login, IdP/SP metadata, `RelyingPartyRegistration`, Spring Security `SecurityFilterChain`, `LogoutFilter`, HTTP POST/redirect, session cookies, and CSRF.

## 2. How Do Local Logout and Federated Logout Differ?

Suppose Portal and Payroll share one IdP for SSO:

~~~text
          IdP: browser SSO session
             /               \
            v                 v
   Portal SP session     Payroll SP session

Local logout at Portal:
   Portal session -> destroyed
   IdP session    -> may remain alive
   Payroll        -> may remain logged in

Federated logout from Portal:
   Portal -> LogoutRequest -> IdP
   IdP may end the IdP session
   and ask SLO-participating SPs to end their sessions.
   Outcome depends on IdP, other SPs, binding, and network.
~~~

| Aspect | Local Logout | SAML Single Logout |
| --- | --- | --- |
| Who initiates | User at SP | User at SP (RP-initiated) or IdP (AP-initiated) |
| Minimum scope | Session at current SP | SP session and a protocol exchange with IdP |
| Emits `LogoutRequest` | No | Yes, from SP or IdP depending on direction |
| Requires IdP SLO endpoint | No | Yes for metadata-integrated flows |
| Requires SP signing credential | Not specifically for local logout | Usually required to sign SLO requests/responses per policy |
| Is IdP cookie deleted? | No | Possibly, per IdP outcome/policy |
| Are other SPs logged out? | Not implicitly | Only when SPs participate in SLO and flow succeeds |
| What user sees | Local-signed-out page | May redirect browser to IdP and back to SP |
| UX risk | User can immediately log in again via IdP session | Partial/timed-out SLO cannot promise every app/device is out |

**Common misconception:** Local logout succeeds, yet the user clicks `/private` and gets SAML-logged in immediately without a password prompt. The cause is usually that **the SSO session at the IdP remains alive**; this does not mean Spring Security failed to destroy the local session.

**Point to make explicit:** SAML SLO is not a mechanism to revoke all API tokens, refresh tokens, sessions on all devices, or applications not participating in the federation. Organization-wide logout requires additional IdP policies, device/session management, or dedicated token revocation.

## 3. Three Types of Endpoints and Messages

In Spring Security 6.5, `saml2Logout` can use `POST /logout` as the SLO starting point if not separated. To give users two choices, configure **two distinct triggers** and **one inbound protocol endpoint**.

| Endpoint | Sender | Request Type | Function |
| --- | --- | --- | --- |
| **`POST /logout`** | Browser/user, valid CSRF | Form POST, no SAML protocol message | Clears SP session; emits no LogoutRequest |
| **`POST /saml2/logout`** | Browser/user, valid CSRF | Form POST | Starts RP-initiated SLO; creates/signs LogoutRequest |
| **`POST /logout/saml2/slo`**, parameter `SAMLRequest` | IdP via browser | SAML LogoutRequest | AP-initiated SLO; SP verifies before deleting local session |
| **`POST /logout/saml2/slo`**, parameter `SAMLResponse` | IdP via browser | SAML LogoutResponse | Replies to the SP's prior SLO request |
| **`GET /logout`** | Browser | Confirmation page request | Usually shows only a confirmation page when CSRF is enabled; does not log out |

**Crucial distinction:** `/saml2/logout` is **not** the callback for the IdP to POST SAMLRequest to the SP. The default SLO callback is `/logout/saml2/slo`. Never combine both "user button" and "IdP listener" into one controller inspecting form parameters manually.

~~~text
Browser:
  POST /logout + CSRF
       -> LogoutFilter -> local cleanup -> local success page
       -> NO SAMLRequest

Browser:
  POST /saml2/logout + CSRF
       -> local cleanup + SAML LogoutRequest
       -> IdP SingleLogoutService
       -> IdP SAMLResponse returns to /logout/saml2/slo

IdP:
  SAMLRequest -> POST /logout/saml2/slo
       -> Saml2LogoutRequestFilter
       -> validate -> local cleanup -> SAML LogoutResponse to IdP
~~~

Many IdPs can support HTTP-Redirect binding for SLO (GET with signature query parameters), though the examples and Spring Security 6.5 defaults in this lesson use HTTP-POST. When changing bindings, follow IdP capabilities and library version; **never** treat every GET carrying `SAMLRequest` as a trusted request.

## 4. Local Logout: Mechanism for Clearing the Local Session

In Spring Security Servlet, `LogoutFilter` processes the logout action through `LogoutHandler` instances. Default behavior typically includes invalidating the HTTP session, clearing `SecurityContextHolder`/`SecurityContextRepository`, cleaning CSRF tokens, remember-me state if used, and publishing logout events; afterward `LogoutSuccessHandler` decides the redirect.

### Steps

1. User is logged in to Portal and has session cookie `JSESSIONID`.
2. Form submits `POST /logout` with CSRF token.
3. Spring Security runs local logout handlers and invalidates the session.
4. SP can redirect to `/local-signed-out` to explain scope.
5. **No SAML LogoutRequest is sent** to the IdP.
6. When the user accesses an authenticated resource again, SP can start a new SAML login; if the IdP cookie is still valid, the IdP can return a new assertion immediately.

**Do not replace with a naive controller:**

~~~java
// Example NOT recommended as the complete Spring Security logout mechanism:
@PostMapping("/logout")
String wrong(HttpSession session) {
    session.invalidate();
    return "redirect:/";
}
~~~

The snippet above illustrates a design flaw, not code to put into an application. It can miss cleanup for `SecurityContextRepository`, remember-me, CSRF, and custom `LogoutHandler` instances. Use `http.logout(...)`.

### Why Is Local Logout Useful?

- The user only wants to close Portal while continuing work in Payroll/email where they are logged in.
- The IdP does not support SLO or federation logout is not configured yet.
- The application wants to avoid disrupting other SPs, or has clear UX requirements on scope.
- Closing the local session is a necessary step before leaving a shared device, **though if the goal is IdP logout, SLO must be chosen**.

**Do not display:** "Logged out of all systems successfully" after local logout. The message should be "You have logged out of this application; your login session at the identity provider may still exist."

## 5. RP-Initiated SLO: SP Proactively Asks the IdP to Log Out

RP = Relying Party, corresponding to SP. When a user holds a `Saml2AuthenticatedPrincipal` and calls the trigger `POST /saml2/logout`:

1. Spring Security executes local logout/cleanup per mechanism.
2. `Saml2RelyingPartyInitiatedLogoutSuccessHandler` uses `Saml2LogoutRequestResolver` to build a SAML `LogoutRequest`.
3. The request carries `ID`, `Issuer` (SP entity ID), `Destination` (IdP SingleLogoutService), `NameID`, and `SessionIndex` matching the SAML session.
4. SP uses its signing credential to sign the message per binding and IdP policy.
5. Browser forwards `SAMLRequest` to the IdP.
6. IdP verifies the SP signer, decides whether to log out the IdP session, and may coordinate with other SPs.
7. IdP may return a `LogoutResponse` to `/logout/saml2/slo`.
8. `Saml2LogoutResponseFilter` verifies the response, especially signer/issuer, destination/status, and `InResponseTo` against the stored request.

~~~text
Portal:
  POST /saml2/logout
     -> SP LogoutHandler
     -> Saml2LogoutRequestResolver
     -> signed LogoutRequest ID="_lo123"
     -> Browser -> IdP /slo

IdP:
  verify SP signature + session
  close / coordinate sessions
  -> signed LogoutResponse InResponseTo="_lo123"

Portal:
  POST /logout/saml2/slo (SAMLResponse)
  -> Saml2LogoutResponseFilter
  -> validate / correlate / finish flow
~~~

### Sample LogoutRequest

~~~xml
<samlp:LogoutRequest
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_lo123"
  Version="2.0"
  IssueInstant="2030-01-01T10:00:00Z"
  Destination="https://idp.example.org/slo">
  <saml:Issuer>urn:portal:sp</saml:Issuer>
  <saml:NameID
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    opaque-user-identifier
  </saml:NameID>
  <samlp:SessionIndex>_idp-session-1</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

This is **illustrative XML**, unsigned and not ready to send. `Issuer` in the SP→IdP direction is the **SP entity ID**, not the IdP. `SessionIndex` comes from the SAML session's `AuthnStatement`, not `JSESSIONID` or an internal user ID. Values must be supplied by the framework and trusted registration.

### Sample LogoutResponse

~~~xml
<samlp:LogoutResponse
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_lores456"
  InResponseTo="_lo123"
  Version="2.0"
  IssueInstant="2030-01-01T10:00:30Z"
  Destination="https://portal.example.org/logout/saml2/slo">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

This is also only an unsigned excerpt. The SP must verify signature, issuer, destination, correlation, and status before trusting the outcome. An unverified `Status=Success` from the browser does not prove the IdP finished logging out.

**Never promise global logout:** if another SP fails to respond, the IdP may report `PartialLogout` or complete within a limited scope. Even when the IdP confirms, non-SLO sessions, other devices, or API tokens may persist.

## 6. AP/IdP-Initiated SLO: Listener Receiving Requests from the IdP

In the reverse direction, the IdP emits a `LogoutRequest` to the SP SLO endpoint. With Spring Security 6.5, `Saml2LogoutRequestFilter` handles the protocol; it is not the user form's `LogoutFilter`.

~~~text
IdP
   -> SAMLRequest: signed LogoutRequest
   -> Browser POST /logout/saml2/slo
   -> Saml2LogoutRequestFilter
       * Resolve approved registration
       * Verify IdP signing key
       * Validate Issuer, Destination, subject/NameID,
         SessionIndex, timestamps, and applicable policy
       * Log out matching local session if request is valid
       * Create/sign LogoutResponse back to IdP
~~~

**Security boundary:** do not call `session.invalidate()` merely because a `SAMLRequest` parameter is present. Parameter names can be sent by an attacker. Process only after the SAML protocol validator verifies issuer/signature, message destination, and session context. If the signature is invalid, the request comes from an untrusted IdP, or the session does not match, reject rather than logging out the wrong user.

### Why Is a Separate Inbound Endpoint Necessary?

- **User trigger** `/saml2/logout` needs a logged-in principal to determine the IdP/SP registration and SAML session.
- **Protocol listener** `/logout/saml2/slo` must accept both AP-initiated `LogoutRequest` and `LogoutResponse` replying to a prior request, possibly after the local session was already destroyed.
- **Local trigger** `/logout` performs cleanup without sending protocol messages.

Merging all three into one MVC endpoint invites CSRF mismatches, filter order collisions, skipped SAML signature validation, lost correlation, or logout loops.

## 7. Separated Configuration in Spring Security

The core point, directly documented in Spring Security 6.5:

~~~java
http
    .logout(logout -> logout.logoutUrl("/logout"))
    .saml2Logout(saml -> saml.logoutUrl("/saml2/logout"));
~~~

When this configuration is active:

- `POST /logout`: local session cleanup only.
- `POST /saml2/logout`: RP-initiated SLO (if principal and registration support it).
- `POST /logout/saml2/slo` with protocol message: handled by SAML SLO filters per metadata/registration.

**Default if not separated:** when `saml2Logout` is enabled, `POST /logout` can trigger SLO for SAML principals. If the UI needs two genuinely distinct options, **you cannot just change button labels**; you must set different URIs in the DSL.

### 7.1. How Necessary Are Signing Keys and Metadata?

For SLO to actually run:

1. IdP metadata publishes `SingleLogoutService` with supported binding/Location.
2. SP has a PKCS#8 signing private key and matching X.509 public certificate to sign SLO messages.
3. IdP has registered the SP signing certificate and SP SLO callback.
4. SP trusts the IdP's public verification cert from trusted metadata.
5. SP entity ID / IdP entity ID pair, NameID/SessionIndex, and binding align.
6. Browser/request repository can retain LogoutRequest/LogoutResponse correlation when needed.

**Successful SAML login does not imply SLO is supported.** If `SingleLogoutService` is missing or keys/metadata mismatch, the federated logout button must not be advertised as a working feature. Local logout should still be maintained as a separate action.

## 8. Spring Boot 3.5.x: Java 17 Project with Two Logout Buttons

The demo project uses Spring MVC + Thymeleaf to render **two POST forms**. Spring Security handles logout in filters, needing no custom `@PostMapping`. Real SSO/SLO can only be tested once you have a sandbox IdP supporting Single Logout and SP credentials.

Structure:

~~~text
saml-logout-demo/
  pom.xml
  src/main/java/demo/SamlLogoutApplication.java
  src/main/resources/application.yml
  src/main/resources/templates/index.html
  src/main/resources/templates/local-signed-out.html
~~~

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>saml-logout-demo</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots><enabled>false</enabled></snapshots>
    </repository>
  </repositories>
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
      <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-saml2-service-provider</artifactId>
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

### 8.2. application.yml

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/sp-signing.key
                  certificate-location: file:/run/secrets/sp-signing.crt
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
~~~

Explanation:

- `metadata-uri` points to **approved IdP metadata**, which must publish `SingleLogoutService` and the public verification certificate.
- `signing.credentials` is the **SP private signing key + SP public certificate**; not the IdP's private key. Provide the private key via a secret manager or read-only mount with restricted permissions; never commit to Git.
- `singlelogout.url` specifies the **SP callback** receiving protocol messages `/logout/saml2/slo`. It is **not** the user button to start SLO.
- `{baseUrl}` must resolve to the exact public scheme/host/path behind any proxy; inspect metadata published by the SP at the production address.
- The IdP must know the SP entity ID, ACS, SLO endpoint, and SP signing cert with compatible binding. Login cannot work with unbacked illustrative URLs.

Spring Boot can read PEM credentials in compatible formats; private keys normally need to be PKCS#8. If a file is PKCS#1/encrypted PEM or a passphrase-protected keystore, configure the corresponding loader/provider rather than copying plaintext into `application.yml`.

### 8.3. SamlLogoutApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@SpringBootApplication
public class SamlLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlLogoutApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/local-signed-out", "/error")
                            .permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutSuccessUrl("/local-signed-out")
                        .permitAll())
                .saml2Logout(saml -> saml
                        .logoutUrl("/saml2/logout"))
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @Controller
    static class Pages {
        @GetMapping("/")
        String index() {
            return "index";
        }

        @GetMapping("/local-signed-out")
        String localSignedOut() {
            return "local-signed-out";
        }
    }
}
~~~

`SecurityFilterChain` uses **two logout configurers** with distinct URIs. `.logout(...)` handles local cleanup; `.saml2Logout(...)` enables RP SLO for SAML principals; the inbound endpoint is handled by SAML filters. The controller only renders two public pages and **executes no logout logic**.

### 8.4. templates/index.html

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>SAML Logout</title>
</head>
<body>
  <h1>Choose logout scope</h1>

  <form th:action="@{/logout}" method="post">
    <button type="submit">Log out of this application</button>
  </form>
  <p>Your IdP login session and other applications may still remain active.</p>

  <form th:action="@{/saml2/logout}" method="post">
    <button type="submit">Request federated logout</button>
  </form>
  <p>The result at other applications depends on Single Logout support.</p>
</body>
</html>
~~~

With Thymeleaf/Spring Security integration, POST forms with `th:action` receive a CSRF token automatically via framework mechanics. **Inspect the rendered HTML** to confirm the hidden `_csrf` field; if using SPA/fetch, retrieve and send the token properly. Never hardcode CSRF tokens in HTML, and never disable CSRF to fix form errors.

### 8.5. templates/local-signed-out.html

~~~html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Locally signed out</title>
</head>
<body>
  <h1>Logged out of this application</h1>
  <p>
    Your session at the identity provider may still be active.
    If you revisit this application, you may be signed in automatically via SSO
    without re-entering your password.
  </p>
  <a href="/">Return to home</a>
</body>
</html>
~~~

Do not automatically redirect from this page to a protected resource, or users will immediately SSO back in and think local logout failed. Nor does the page promise "logged out everywhere".

### 8.6. Running and Testing

After supplying real metadata/credentials for a sandbox IdP:

~~~bash
mvn spring-boot:run
~~~

Open `http://localhost:8080/` to see both buttons. With a test IdP that has registered the app, log in and inspect network traffic:

- **Local:** `POST /logout` → local success page; no SAML LogoutRequest emitted.
- **Federated:** `POST /saml2/logout` → Spring creates `SAMLRequest` and directs the browser to the IdP SingleLogoutService, potentially receiving a callback at `/logout/saml2/slo`.
- **IdP-initiated:** IdP sends signed LogoutRequest to the SP inbound endpoint; Spring verifies, cleans the matching session, and returns LogoutResponse.

There is no fixed stdout/login response for SLO because HTTP redirects, bindings, and IdP policies vary. Never claim the demo has verified SLO integration without testing against a real IdP.

## 9. CSRF, SameSite Cookies, and Session Lifecycle

**User forms:** both local and RP-initiated triggers should be POSTs with CSRF tokens. `GET /logout` with CSRF enabled typically shows a confirmation page rather than logging out directly; this is a security feature, not a routing bug. An attacker must not be able to log users out via an embedded image or GET link.

**SAML inbound:** the IdP does not hold the SP form's CSRF token. Spring SAML logout filters must process the binding and validate signed SAML messages. Never call `csrf.disable()` for the whole application or overly broadly on `/logout/**`; add only a narrow exception if your version's config requires it alongside SAML verification.

**Cookies:** SP `JSESSIONID` and IdP SSO cookies belong to different domains. The SP cannot directly delete an IdP cookie with a `Set-Cookie` for the SP domain. You need the SLO protocol or an IdP logout flow. `SameSite`, `Secure`, browser privacy restrictions, and cross-site POST can affect callbacks; test with real browsers over a public HTTPS hostname.

**Session cleanup:** Spring `LogoutFilter` + handlers invalidate the session and clear SecurityContext. If the app stores extra user state (caches, WebSockets, shopping carts, remember-me), decide separate cleanup explicitly. Never wipe the repository holding `LogoutRequest` needed for `InResponseTo` before the callback arrives; let the framework manage lifecycle or use a cluster-compatible repository.

**Cluster:** SP emits the request on node A, and the IdP response lands on node B. A shared session/request repository or sticky routing is needed; never fix errors by dropping `LogoutResponse` validation. When using Spring Session, verify how SLO requests are stored and retrieved in your actual version.

## 10. InResponseTo, NameID, SessionIndex, and Differences from Login

| SAML Field | Where It Appears | Meaning |
| --- | --- | --- |
| `LogoutRequest/ID` | Logout request | Unique message ID to correlate response |
| `LogoutResponse/InResponseTo` | Logout response | Points to original LogoutRequest ID |
| `LogoutRequest/Issuer` | Message issued by initiator | SP entity ID when RP-initiated; IdP entity ID when AP-initiated |
| `LogoutRequest/Destination` | Logout message | Recipient's SLO endpoint URI |
| `LogoutRequest/NameID` | Logout message | Subject in SAML namespace, not app user ID |
| `LogoutRequest/SessionIndex` | Logout request | IdP session index from AuthnStatement when present |
| `LogoutResponse/Status` | Logout response | Success, PartialLogout, or error per SAML |
| `RelayState` | HTTP binding | Supports state/correlation; not standalone authentication proof |

**SLO `SAMLResponse` differs from login `SAMLResponse`:** both may share the HTTP form parameter name `SAMLResponse`, yet SLO XML is `samlp:LogoutResponse` whereas login XML is `samlp:Response` containing an Assertion. The SLO endpoint differs from login ACS. Never feed `LogoutResponse` through `Saml2WebSsoAuthenticationFilter`.

**Validation:** for `LogoutResponse`, signature/issuer/destination/status together with `InResponseTo` must be valid; `Status=Success` alone is insufficient. For inbound `LogoutRequest`, the IdP signature and matching principal/session are critical prerequisites before local logout.

## 11. Standalone Java 17: Identifying Endpoint Types

This program only simulates **route classification**; it does not process real SAML and **does not authenticate a LogoutRequest**. It illustrates that the three endpoints have distinct responsibilities.

**LogoutRouteDemo.java:**

~~~java
public class LogoutRouteDemo {
    enum Action {
        LOCAL_ONLY,
        RP_SLO,
        INBOUND_REQUEST,
        INBOUND_RESPONSE,
        NO_MATCH
    }

    static Action classify(String method, String path, String formKey) {
        if (!"POST".equals(method)) {
            return Action.NO_MATCH;
        }
        return switch (path) {
            case "/logout" -> Action.LOCAL_ONLY;
            case "/saml2/logout" -> Action.RP_SLO;
            case "/logout/saml2/slo" -> switch (formKey) {
                case "SAMLRequest" -> Action.INBOUND_REQUEST;
                case "SAMLResponse" -> Action.INBOUND_RESPONSE;
                default -> Action.NO_MATCH;
            };
            default -> Action.NO_MATCH;
        };
    }

    static void show(String label, Action action) {
        System.out.println(label + " -> " + action);
    }

    public static void main(String[] args) {
        show("POST /logout", classify("POST", "/logout", ""));
        show("POST /saml2/logout",
                classify("POST", "/saml2/logout", ""));
        show("POST /logout/saml2/slo [SAMLRequest]",
                classify("POST", "/logout/saml2/slo", "SAMLRequest"));
        show("POST /logout/saml2/slo [SAMLResponse]",
                classify("POST", "/logout/saml2/slo", "SAMLResponse"));
        show("GET /logout", classify("GET", "/logout", ""));
        show("POST /logout/saml2/slo [none]",
                classify("POST", "/logout/saml2/slo", ""));
    }
}
~~~

Compile/run with Java 17+:

~~~bash
javac LogoutRouteDemo.java
java LogoutRouteDemo
~~~

**Exact stdout:**

~~~text
POST /logout -> LOCAL_ONLY
POST /saml2/logout -> RP_SLO
POST /logout/saml2/slo [SAMLRequest] -> INBOUND_REQUEST
POST /logout/saml2/slo [SAMLResponse] -> INBOUND_RESPONSE
GET /logout -> NO_MATCH
POST /logout/saml2/slo [none] -> NO_MATCH
~~~

In real Spring Security, `GET /logout` may render a confirmation page; `NO_MATCH` in the demo means **not a POST logout action**. And a forged inbound `SAMLRequest` will also be classified by this program as `INBOUND_REQUEST`, yet must be rejected by Spring Security due to invalid signature/issuer. This is merely route classification, not a production implementation.

## 12. Edge Cases and Proper Handling

### 12.1. User Completes Local Logout First, Then Clicks Federated Logout

After local logout, the SP has already lost the SAML principal/session that the SLO request resolver may need to determine the IdP, NameID, and SessionIndex. Never assume `/saml2/logout` can be called afterward to recover the old context. If users want federated SLO, they should **click the federated button while the session is still authenticated**. Once the session is gone, they may need to use a dedicated IdP logout flow or appropriate policy.

### 12.2. Multi-IdP and Multi-Tenant

Portal has IdPs A and B. When user A initiates SLO, the SP must rely on `Saml2AuthenticatedPrincipal` and the **trusted `RelyingPartyRegistration`** to pick IdP A's SLO service. Never trust a user-supplied `?idp=https://...` query parameter to send logout messages; that can become an open redirect, SSRF, or IdP mix-up. Each partner needs its own signing/verification keys and metadata.

### 12.3. IdP Lacks SLO Support

If metadata lacks `SingleLogoutService` or the partner does not support signing/binding, keep Local Logout working and **hide/disable the federated button** if it cannot execute. Where needed, direct users to log out at an approved IdP portal; that is not the same SLO guarantee.

### 12.4. IdP Returns PartialLogout or Does Not Respond

The SP may already have cleared the local session before the IdP finishes. Never claim "logged out everywhere" merely because of a redirect to the IdP or because the local cookie is gone. UX should explain "this application session has ended; not all SSO sessions are confirmed closed". Log errors/statuses minimally and provide guidance for shared devices.

### 12.5. Invalid IdP-Initiated LogoutRequest

Never delete a user's session merely because a `SAMLRequest` parameter arrived. Let `Saml2LogoutRequestFilter` verify signature, issuer, destination, NameID/SessionIndex, and applicable policy before invoking LogoutHandlers. Avoid writing a custom `@PostMapping("/logout/saml2/slo")` controller that parses XML with DOM/XPath and invalidates sessions.

### 12.6. API Tokens Outlive SLO

SAML SLO coordinates browser SSO sessions; REST API Bearer tokens, refresh tokens, service-to-service credentials, or mobile sessions are separate state types. If they must be revoked upon user logout or offboarding, design token revocation/introspection, session registries, or policies at your API gateway/authorization server separately.

## 13. Pre-Go-Live Testing Matrix

| Test Case | Expected Outcome |
| --- | --- |
| POST `/logout` with valid CSRF | Clears local session; emits no SAMLRequest |
| POST `/saml2/logout` with valid CSRF + SAML principal | Builds/signs LogoutRequest to IdP SLO endpoint |
| GET `/logout` with CSRF enabled | Does not directly execute logout |
| POST local without CSRF | Request rejected; no arbitrary logout |
| POST federated without CSRF | Does not initiate SLO |
| Local logout then immediate re-login via IdP cookie | Automatic SSO may happen; not a local logout bug |
| Validly signed SLO LogoutResponse with matching InResponseTo | SP verifies and completes flow |
| SLO LogoutResponse with wrong issuer or InResponseTo | Rejected / not reported complete |
| Validly signed IdP-initiated LogoutRequest | SP logs out matching session and sends LogoutResponse |
| Unsigned/bad-signature IdP-initiated LogoutRequest | Rejected; does not delete another user's session |
| IdP lacks `SingleLogoutService` | Local still works; SLO not advertised as passing |
| IdP does not yet trust new SP signing cert | IdP rejects RP-initiated request; check certificate rotation |
| IdP returns `PartialLogout` | Do not claim all applications logged out |
| IdP times out or user closes tab mid-SLO | Local/session state and UX show unconfirmed outcome |
| SAMLRequest sent to `/logout` | Not processed as protocol SLO |
| SLO SAMLResponse sent to login ACS | Not processed as authentication assertion |
| SP cluster node B receives callback after node A emitted request | Repository/correlation works or fails safely |
| One browser executes SLO | Do not assume all devices logged out |
| Non-SAML principal calls `/saml2/logout` | Cannot arbitrarily pick an IdP to emit LogoutRequest |
| `local-signed-out` page accidentally protected | Fix permitAll to prevent auto-SSO loop on render |
| Role/user status changes after logout | Authorization always enforces app policy; logout ≠ role revocation |

**Multi-layer verification:** UI/route tests check both POST actions; Spring MVC/MockMvc tests check CSRF and session cleanup; IdP sandbox integration tests check **signed SAML LogoutRequest/LogoutResponse**, issuer/destination/InResponseTo, and NameID/SessionIndex; browser E2E tests check cookies/SameSite/proxy/callbacks; multi-node tests check repositories.

To properly test SLO signature/issuer validators, have the test IdP emit **validly signed messages with other conditions invalid**. If you tamper with XML after signing, the first failure is the signature; that test does not prove correlation/destination validation works.

### Logging Principles

Log event type (`LOCAL`, `RP_SLO`, `AP_SLO`, `SLO_RESPONSE`), `registrationId`, controlled correlation ID, timestamp, and status/error code. Avoid logging raw XML, `SAMLRequest`/`SAMLResponse`, NameID, session cookies, signing private keys, or personal data. Capture SAML traces only in tests, and mask/purge data per retention policy.

## 14. Common Mistakes

| Symptom | Cause | Remediation |
| --- | --- | --- |
| Clicking local redirects to IdP | `saml2Logout` still uses default `POST /logout` | Separate `.logout(...)` and `.saml2Logout(...logoutUrl(...))` |
| Local logout then login without password | IdP session still alive | Clarify UX; use SLO/re-auth when needed |
| Clicking federated emits no SAMLRequest | Wrong form action, non-SAML principal, missing SLO capability | Check URI/registration/IdP metadata |
| CSRF 403 | Form does not send token | Use Thymeleaf `th:action`/framework token handling |
| IdP rejects LogoutRequest | Wrong signing key/cert, unsupported binding, issuer/NameID/SessionIndex skew | Cross-check SP metadata, IdP logs, key rotation |
| SP receives SLO but returns 400 | Invalid LogoutRequest signature/issuer/destination/session | Investigate validator; never drop checks |
| LogoutResponse callback fails to match | Lost `InResponseTo`, RelayState, or request repository | Check session cookies, cluster store, and IdP response |
| SLO callback hits wrong URL | Wrong `singlelogout.url`/proxy/metadata | Configure exact public HTTPS SLO endpoint |
| Login loop on `local-signed-out` | Logout success page protected | Permit public access to the success page |
| IdP SLO succeeds yet Payroll stays logged in | Payroll lacks SLO participation or separate session exists | Check SLO capabilities; never promise universal logout |
| HTTP response succeeds yet SLO failed | 302 is only a browser hop | Inspect verified LogoutResponse and status |
| User logs out via SAML yet API token still works | Tokens have an independent lifecycle | Dedicated token revocation/session management |
| Fails on one node only | Out-of-sync session repository or keys | Shared sessions, deployment config, signing certs |

**Never fix issues by** disabling CSRF app-wide, enabling GET logout, skipping signature verification, trusting arbitrary public keys from SAML messages, or accepting uncorrelated LogoutResponses.

## 15. UX and Operational Decisions

**Choose Local Logout** when users only want to finish work in one application, partners do not support SLO, or the system wants to avoid unintentionally closing other SPs. Label the button "Log out of this application".

**Offer Federated SLO** when SLO is supported by IdP/SP and users need to request closing federated SSO sessions, especially on shared devices, with plans for PartialLogout and IdP timeouts. Label the button "Request federated logout", never "Guaranteed logout everywhere".

After **local success**, display: "Session in this application has ended; sessions at your identity provider and other applications may still remain active."

When **federated response cannot be verified**, do not show a global success banner. State that the app ended the local session without confirming full federation logout, and provide guidance to visit the official IdP logout portal.

After **AP-initiated SLO**, the browser usually returns to the IdP per LogoutResponse, so rendering an SP success page is not guaranteed. Design UX not to depend on a local HTML callback in this branch.

**Operational checklist:**

- [ ] IdP metadata includes `SingleLogoutService`; SP signing certificate is trusted by the IdP.
- [ ] Public SP SLO endpoint `/logout/saml2/slo` has accurate binding, scheme, host, and path.
- [ ] Two user triggers are **`POST /logout`** and **`POST /saml2/logout`**, with non-overlapping URIs.
- [ ] Form POST carries a CSRF token; inbound SAML messages are validated by protocol validators.
- [ ] LogoutRequest/Response are signed/verified per policy.
- [ ] LogoutResponse has `InResponseTo` correlated with the sent request.
- [ ] Cluster/session repository preserves state across nodes.
- [ ] Local logout emits no `LogoutRequest`; federated logout emits one when prerequisites are met.
- [ ] Negative tests exist for signature/issuer/destination/status and unauthorized requests.
- [ ] Success page distinguishes "local" from federation status.
- [ ] Never promise revoking all devices, application sessions, or API tokens via SAML SLO alone.
- [ ] Monitoring, IdP timeout/PartialLogout runbooks, and certificate rotation procedures exist.

## 16. Exercises and Mastery Criteria

**Exercise A – Diagram the three paths:** Draw separately local `POST /logout`, RP-initiated `POST /saml2/logout`, and AP-initiated `POST /logout/saml2/slo`. Label the Spring Security component handling each branch.

**Exercise B – Configuration:** Build the project in section 8 with a sandbox SAML IdP supporting `SingleLogoutService`. Ensure both forms render CSRF properly. Prove clicking local sends no `SAMLRequest` and clicking federated sends a signed `LogoutRequest`.

**Exercise C – Java:** Run `LogoutRouteDemo.java`, verify the 6 lines of stdout, and explain why a route matcher alone is insufficient to authenticate an inbound `SAMLRequest`.

**Exercise D – IdP-initiated:** From the test IdP, send a validly signed `LogoutRequest`, observe the SP clean up the session and send `LogoutResponse`. Send a forged request and verify the SP rejects it.

**Exercise E – Correlation:** Alter `InResponseTo` in a test `LogoutResponse` to another ID re-signed by the test IdP; the SP must reject it. Inspect where `LogoutRequest` is stored when the session is invalidated.

**Exercise F – UX:** Write two distinct messages for local success and federated `PartialLogout`, avoiding promises that all apps are logged out.

**Exercise G – Multi-IdP:** If an application has IdPs A and B, explain why the SP must select the IdP from the authenticated principal/registration rather than an arbitrary query parameter.

**Mastery achieved** when you understand exact logout scopes, separate the two triggers and protocol listener with the Spring DSL, protect POST/CSRF, integrate signed SAML SLO via metadata/certificates, and test local, RP-initiated, AP-initiated, and failure cases.

## 17. Official References

- Spring Security **6.5** – Performing Single Logout, especially "Separating Local Logout from SAML 2.0 Logout": https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security 6.5 – Handling Logouts: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security – SAML 2.0 Logout reference (verify against your version): https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.5 – SAML Relying Party: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS SAML 2.0 Core – Single Logout Protocol: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles – Single Logout: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML 2.0 Metadata – SingleLogoutService: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf

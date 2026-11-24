# Testing RP-Initiated SLO, IdP-Initiated SLO, and Local Logout

> **Module:** Spring Security – federation. **Group:** SAML2 Testing. This lesson builds test suites for three logout behaviors: **Local Logout**, **RP-initiated SAML Single Logout**, and **IdP/AP-initiated SAML Single Logout**, plus the **`LogoutResponse`** callback. Examples use Java 17, Spring Boot 3.5.x, and Spring Security 6.5.x on the Servlet stack. All Entity IDs, URLs, and certificates in the examples are sandbox fixtures; never use production accounts or signing keys.

## 1. Objectives

After this lesson, you will be able to:

1. Distinguish the Service Provider (SP) HTTP session/`SecurityContext`, the Identity Provider (IdP) SSO session, and a second SP's session.
2. Identify the exact endpoints for local logout, RP-initiated user trigger, IdP-initiated `LogoutRequest`, and IdP `LogoutResponse` callback.
3. Verify that local logout clears the session without emitting a SAML `LogoutRequest`; the RP flow emits a signed `LogoutRequest` to the IdP; and the IdP flow validates the inbound request before clearing the session.
4. Design negative tests for signature, `Issuer`, `Destination`, `NameID`/Format, `SessionIndex`, `InResponseTo`, `RelayState`, `Status`, replay, and CSRF.
5. Distinguish HTTP transport success, SAML protocol result, and whether user/IdP/other-SP sessions were actually terminated.
6. Configure Spring Security SAML2 with two separate logout buttons; know the roles of `LogoutFilter`, `Saml2LogoutRequestFilter`, `Saml2LogoutResponseFilter`, and `LogoutRequestRepository`.
7. Run a standalone Java 17 test oracle with deterministic stdout, while understanding cryptographic testing requires a sandbox IdP with signed fixtures.
8. Test browser `SameSite` cookies, reverse proxies/HTTPS, IdP timeouts, `PartialLogout`, multi-node callbacks, and multi-session scenarios.
9. Collect QA evidence safely without retaining private keys, raw SAML XML, `NameID`s, or bearer cookies.

**Prerequisites:** SAML 2.0 Web Browser SSO, `RelyingPartyRegistration`, SAML Assertion, `NameID`/`SessionIndex`, logout messages, XML Signature, HTTP-POST/Redirect bindings, Java Servlet sessions, CSRF, and Spring `SecurityFilterChain`.

## 2. Logout Architecture and Scope

~~~text
                  IdP SSO session
                    /        \
                   v          v
             Portal SP     Reports SP
             JSESSIONID    separate session

Local:
 Browser --POST /logout + CSRF--> Portal
 Portal clears its own session
 IdP and Reports are not automatically logged out

RP-initiated:
 Browser --POST /saml2/logout + CSRF--> Portal
 Portal clears local, sends signed LogoutRequest to IdP
 IdP processes SSO/SLO, may coordinate Reports
 IdP may return signed LogoutResponse to Portal

IdP-initiated:
 IdP --signed LogoutRequest--> Portal SLO listener
 Portal verifies, clears matching session, sends LogoutResponse to IdP
~~~

| Flow | Initiator | SAML traffic | Minimum pass criteria | Do not infer |
| --- | --- | --- | --- | --- |
| Local | User at Portal | **No** `LogoutRequest` to IdP | Portal session/`SecurityContext` invalidated | IdP/Reports logged out |
| RP SLO | User at Portal | Portal sends `LogoutRequest`, may receive `LogoutResponse` | Outbound request signed/right IdP; local cleanup; inbound response verified if present | Every device/API token revoked |
| IdP SLO | IdP | IdP sends `LogoutRequest`, Portal sends `LogoutResponse` | Inbound verified before clearing the right session | Every user sharing `NameID` logged out everywhere |
| RP callback | IdP replies to SP request | IdP sends `LogoutResponse` | Verify signer/issuer/destination/status/`InResponseTo` | Response with HTTP 200 alone means success |

**Common source of confusion:** Local logout succeeds, yet the user revisits Portal and immediately SSOs back in because **the IdP session is still alive**. That creates a **new Portal session**, not the old session surviving. Tests must compare session fingerprints and confirm a fresh Assertion was issued rather than merely checking whether the user had to re-enter a password.

## 3. Endpoint Contract in Spring Security 6.5

If you configure only default SAML logout, `POST /logout` for a SAML principal may trigger RP SLO. To keep local and federated logout independent, configure **two distinct user-trigger endpoints**:

~~~java
http
    .logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/local-signed-out"))
    .saml2Logout(saml -> saml
        .logoutUrl("/saml2/logout"));
~~~

| Endpoint | Sender | Input | Spring component | Assertion |
| --- | --- | --- | --- | --- |
| `POST /logout` | Browser/user | Form POST + CSRF | `LogoutFilter`, `LogoutHandler`s | Local cleanup only, no `SAMLRequest` |
| `POST /saml2/logout` | SAML browser/user | Form POST + CSRF | `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Emits `LogoutRequest` to IdP |
| `POST /logout/saml2/slo` | IdP | Form field `SAMLRequest` | `Saml2LogoutRequestFilter` | Validates signed `LogoutRequest` then clears local session |
| `POST /logout/saml2/slo` | IdP | Form field `SAMLResponse` | `Saml2LogoutResponseFilter` | Validates signed `LogoutResponse` + correlation |
| `GET /logout` | Browser | GET | Logout confirmation (when CSRF enabled) | Performs no direct logout |
| `GET /saml2/logout` | Browser | GET | Not a POST RP trigger | Emits no `LogoutRequest` |

**Binding note:** With HTTP-POST, `SAMLRequest`/`SAMLResponse` are form parameters, **not** query parameters. With HTTP-Redirect, the signature sits in query fields `SigAlg`/`Signature`, requiring binding-specific signature verification rather than only looking for XML `<ds:Signature>`. This lesson uses HTTP-POST fixtures; only open GET SLO if IdP and SP agree on Redirect binding and its matching validator.

**Separate callback from trigger button:** `/saml2/logout` is for the user to trigger RP SLO; `/logout/saml2/slo` is the protocol listener. Never build a controller that clears sessions whenever it sees a `SAMLRequest` parameter while skipping SAML validators.

## 4. Test Fixtures and Preconditions

Sandbox model:

~~~text
Browser QA -> Portal Spring Security 6.5
  https://portal.test.example.org
  SP Entity ID: urn:portal:test:sp
  registrationId: corporate
  ACS: /login/saml2/sso/corporate
  SLO callback: /logout/saml2/slo

Test IdP
  https://idp.test.example.org
  IdP Entity ID: https://idp.test.example.org/saml
  SingleLogoutService: https://idp.test.example.org/slo
  Lab-only signing private key
  Public verification certificate published in trusted metadata

Reports SP (optional)
  https://reports.test.example.org
  Has separate session and joins SLO if IdP supports it

QA user: opaque-user-17
NameIDFormat: persistent
SessionIndex: _idp-session-17
Binding: HTTP-POST
~~~

| Preparation | Why it is required |
| --- | --- |
| IdP metadata includes `SingleLogoutService`/binding/location | SAML login working does not guarantee the IdP supports SLO |
| SP PKCS#8 signing private key + X.509 certificate | IdP needs to verify signed `LogoutRequest`/`LogoutResponse` |
| SP trusts IdP signer public cert via approved metadata | SP verifies inbound SAML messages |
| Public HTTPS SP entity ID, ACS, and SLO callback | `Destination`/`Recipient`/service URLs must match |
| Real principal from SAML login | RP resolver needs right registration/`NameID`/session |
| `NameIDFormat`, `SessionIndex` from Assertion/IdP | Verify logging out the exact user/SSO session per profile |
| `Saml2LogoutRequestRepository` and browser session | Holds request ID/`RelayState` for `InResponseTo` |
| Synchronized clocks, test user, and dedicated signing cert | Avoid false negative clocks; isolate secrets |
| Browser HTTPS, `SameSite`/`Secure`, reverse proxy | Callbacks can drop cookies/state |
| IdP capable of deliberately signing invalid-case fixtures | Isolate validators instead of breaking signatures post-signing |

**Never log raw `SAMLRequest`/`SAMLResponse`, cookies, or real people's `NameID`s.** Use synthetic test identities, certificate aliases, and ID fingerprints when investigating.

## 5. Local Logout: Happy Path and Negative Cases

### 5.1. Arrange → Act → Assert

**Arrange:** QA user logs into Portal via SAML, `GET /private` returns 200; record fingerprints of the local session, IdP session, and Reports session. Enable the test IdP event recorder to count SAML `LogoutRequest`s.

**Act:** Browser sends `POST /logout` with a valid CSRF token.

**Assert:**
1. Spring executes `LogoutHandler`s, invalidates the HTTP session, and clears `SecurityContext` and CSRF/remember-me state if configured.
2. Response goes to `/local-signed-out` per policy; the success page is public and causes no login loop.
3. Old cookie/session can no longer call `GET /private` with the old authentication.
4. **No** `SAMLRequest`/`LogoutRequest` is sent to the IdP; IdP and Reports sessions **do not automatically change**.
5. When the user revisits a protected URL, immediate SSO may happen; verify the new Portal session differs from the prior one.
6. The application does not display "logged out of all applications" after a local action.

### 5.2. Negative Cases

| Case | Expected |
| --- | --- |
| `POST /logout` missing CSRF | Rejected, typically 403; no forced logout |
| POST with another browser's CSRF token | Rejected |
| `GET /logout` | Confirmation / no logout |
| `GET /saml2/logout` | Emits no federated `LogoutRequest` |
| Attach fake `SAMLRequest` to `POST /logout` | Still the local route; does not obey IdP command |
| User double-clicks local logout | Does not emit duplicate SLO messages or strange sessions |
| Old `JSESSIONID` reused | Old authentication is gone |
| Browser holds IdP cookie and immediately re-SSOs | Not proof that local logout failed |
| `/local-signed-out` page is protected | Detects loop/redirect to IdP; fix `permitAll` |
| Custom app caches not cleared | Test business state; add managed `LogoutHandler` |

Do not assert HTTP 302 alone. A controller doing `return "redirect:..."` without clearing the session still returns 302. Tests must verify **the old session actually loses access** and the outbound SAML event count is 0.

## 6. RP-Initiated SLO: Testing the Flow from SP to IdP

### 6.1. Positive Flow

1. User is SAML-authenticated at Portal with trusted registration `corporate`. To test propagation, also open Reports and log in via the same IdP in the same sandbox.
2. Browser sends `POST /saml2/logout` with valid CSRF.
3. Portal performs local cleanup; `Saml2RelyingPartyInitiatedLogoutSuccessHandler` uses `Saml2LogoutRequestResolver` to generate a request with a unique `ID`.
4. Inspect outbound `LogoutRequest`: `Issuer=urn:portal:test:sp`, `Destination=https://idp.test.example.org/slo`, reasonable `IssueInstant`, exact `NameID`/Format, and `SessionIndex` per profile.
5. Sandbox IdP verifies the signature with the registered SP public cert; browser delivers the message via HTTP-POST binding.
6. IdP terminates/coordinates sessions per policy and may issue a signed `LogoutResponse` with `InResponseTo` matching the request ID.
7. Portal `Saml2LogoutResponseFilter` verifies the signed response, issuer, destination, status, and pending request correlation.
8. Verify old Portal session is invalidated, IdP SSO outcome, and Reports outcome **individually**—never infer from HTTP redirects.
9. If Reports does not support SLO or rejects the request, record `PartialLogout`/unconfirmed rather than global success.

**Illustrative `LogoutRequest` XML, UNSIGNED:**

~~~xml
<samlp:LogoutRequest
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_sp-logout-17" Version="2.0"
  IssueInstant="2030-01-01T10:00:00Z"
  Destination="https://idp.test.example.org/slo">
  <saml:Issuer>urn:portal:test:sp</saml:Issuer>
  <saml:NameID Format=
      "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    opaque-user-17
  </saml:NameID>
  <samlp:SessionIndex>_idp-session-17</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

This is a syntax sample; never use it as a real signed fixture. Per SAML Profiles, the session participant must include `SessionIndex` when initiating Single Logout for the corresponding session. Inspect the actual `SAMLMessage` generated by Spring's resolver and IdP agreement; **never** substitute `JSESSIONID` for `SessionIndex`.

**Sample `LogoutResponse` XML, also UNSIGNED:**

~~~xml
<samlp:LogoutResponse
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_idp-res-17"
  InResponseTo="_sp-logout-17"
  Version="2.0"
  IssueInstant="2030-01-01T10:00:10Z"
  Destination="https://portal.test.example.org/logout/saml2/slo">
  <saml:Issuer>https://idp.test.example.org/saml</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
       Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

**Never accept** `Status=Success` from browser-submitted XML without verifying signer/issuer/destination and `InResponseTo`. A response from IdP B outside Portal A's registration must be rejected.

### 6.2. Negative Cases for the RP Flow

| Case | Expected |
| --- | --- |
| `POST /saml2/logout` missing CSRF | Emits no `LogoutRequest` |
| Anonymous user or non-SAML principal | Never picks an arbitrary IdP to send a request |
| IdP metadata lacks `SingleLogoutService` | SLO unsupported; local logout still works |
| Missing/mismatched SP signing key/cert | IdP rejects or config failure |
| Wrong outbound `Destination` | IdP rejects |
| Wrong outbound `Issuer`/SP entity ID | IdP rejects |
| Wrong `NameID`/Format | IdP does not log out the wrong session |
| Wrong/missing `SessionIndex` when profile requires | IdP rejects or does not confirm that session |
| IdP unreachable/timeout | Portal local session may be cleared; federation unconfirmed |
| Browser closes tab before callback | No verified full SLO completion |
| User clicks RP logout a second time post-cleanup | Does not mint a request from a stale principal |
| IdP returns signed `LogoutResponse` with error status | Do not mark global success |
| IdP returns `PartialLogout` | Do not claim all SPs logged out |

**Do not require rolling back local logout when the IdP is unreachable**: Spring may invalidate the Portal session before redirecting the browser to the IdP. UX should state "application session ended; federated logout outcome unconfirmed."

## 7. IdP-Initiated SLO: Testing Verification Before Clearing Sessions

### 7.1. Positive Scenario

**Arrange:** QA user has an authenticated SAML session at Portal. Test IdP holds a private signing key trusted by Portal via metadata.

**Act:** IdP proactively issues a signed `LogoutRequest` using HTTP-POST binding, placing the Base64-encoded payload in form field `SAMLRequest`, and the browser POSTs to `/logout/saml2/slo`.

**Assert:**
1. `Saml2LogoutRequestFilter` receives the message and selects the right registration/IdP trust.
2. Validators verify signature, issuer, destination, subject/`NameID`/Format, session context, timing, and replay per framework/policy.
3. **Only when the request is valid** are local `LogoutHandler`s invoked to clear the right user session.
4. `Saml2LogoutResponseResolver` issues a signed `LogoutResponse` with `InResponseTo` equal to the `LogoutRequest` ID, `Issuer` set to SP entity ID, and `Destination` set to the IdP SLO response URL.
5. Browser returns the response to the IdP. **Do not assert** that the app renders a local success page; the IdP retains browser control.
6. Sessions of unrelated users/tenants/devices are not cleared merely due to a matching email or `NameID`.

**Sample incoming `LogoutRequest` XML, UNSIGNED:**

~~~xml
<samlp:LogoutRequest
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_idp-logout-17" Version="2.0"
  IssueInstant="2030-01-01T10:30:00Z"
  Destination="https://portal.test.example.org/logout/saml2/slo">
  <saml:Issuer>https://idp.test.example.org/saml</saml:Issuer>
  <saml:NameID Format=
    "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    opaque-user-17
  </saml:NameID>
  <samlp:SessionIndex>_idp-session-17</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Use this XML purely as a **structural illustration**. Positive tests must let the sandbox IdP generate/sign valid messages. SAML Profiles allow session authorities/IdPs specific rules on including or omitting `SessionIndex` depending on logout scope; test against your actual profile and policy rather than assuming a request without `SessionIndex` is forged solely for lacking that field.

### 7.2. Negative Scenarios

| Input | Expected |
| --- | --- |
| Missing `SAMLRequest` or malformed Base64/XML | Rejected; no forced logout |
| Unsigned request when policy requires signed | Rejected |
| Signed by untrusted IdP | Rejected |
| `Issuer` differs from trusted registration | Rejected |
| `Destination` targets another SP | Rejected |
| `NameID`/Format does not match user session | Does not log out wrong user |
| `SessionIndex` mismatches when matching is required | Does not log out unrelated session |
| Expired/invalid `IssueInstant` per policy | Rejected |
| Replay of same request ID | Rejected or causes no repeated side effects per replay policy |
| Malicious XML Signature Wrapping | Validator ignores unsigned elements |
| User has no active SP session | Creates no new session and clears no other user |
| Tenant B IdP sends request for tenant A | No cross-tenant logout |

**Validation order is critical:** If an invalid `SAMLRequest` still invalidates the user's session before signature/subject validation runs, that is a forced-logout vulnerability. Tests must assert both rejection and that **the valid existing session remains untouched** when rejecting the request.

## 8. LogoutResponse Callback: Checking InResponseTo and RelayState

The RP flow is not finished merely because Portal sent a `LogoutRequest`. When the IdP posts `SAMLResponse` to `/logout/saml2/slo`:

~~~text
Portal generated LogoutRequest:
  ID = _sp-logout-17
  Issuer = urn:portal:test:sp
  Store request + RelayState (if used) in repository

IdP returns LogoutResponse:
  InResponseTo = _sp-logout-17
  Issuer = https://idp.test.example.org/saml
  Destination = https://portal.test.example.org/logout/saml2/slo
  signed by trusted IdP private key

Portal:
  lookup pending request
  verify signature/issuer/destination/status/ID
  consume state / finish or report failure
~~~

### Callback Cases to Execute

1. Positive signed `LogoutResponse` with `InResponseTo` matching the pending request; app handles per `Status`.
2. Signed `LogoutResponse` with wrong `InResponseTo` yet same IdP signer and valid `Destination` → reject.
3. Signed `LogoutResponse` with right ID yet wrong `Issuer` → reject.
4. Signed `LogoutResponse` with right ID yet wrong `Destination` → reject.
5. Replayed `LogoutResponse` after flow completion → reject / no duplicate completion.
6. Modified `RelayState` or belonging to another browser → never picks wrong IdP/tenant and never bypasses request correlation.
7. IdP returns `Status=Responder`/error → never report global success.
8. Callback hits node B after node A created the request without a shared repository → fail safely rather than dropping `InResponseTo`.
9. Cross-site browser POST drops cookie due to `SameSite` → detect state loss and fix browser/session/repository config rather than making validators "always pass."
10. Callback arrives after user opened a new login session → never apply stale response to the new session.

**Proper signature testing:** If you edit `InResponseTo` in XML after the IdP signed it, the signature breaks and the validator rejects at the crypto layer, **failing to prove** correlation checking. Have the sandbox IdP **re-sign** a `LogoutResponse` with wrong `InResponseTo` to isolate the validation layer.

### SAML Status PartialLogout

~~~xml
<samlp:Status xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
  <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success">
    <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:PartialLogout"/>
  </samlp:StatusCode>
</samlp:Status>
~~~

This illustrates the second-level status, not a signed `LogoutResponse`. Per SAML Profiles, `PartialLogout` indicates the session authority could not confirm logout across all session participants. Testers must distinguish:
- Portal's local session cleanup;
- IdP reporting `Success`, `PartialLogout`, or error;
- Whether Reports SP actually logged out the right user;
- Other devices, tokens, and applications that may remain active outside SLO scope.

## 9. CSRF: User Forms vs. Signed SAML Protocol Callbacks

**User-triggered:** `POST /logout` and `POST /saml2/logout` mutate the browser session and must require CSRF tokens. `GET /logout` when CSRF is enabled typically renders a confirmation page; never log out on a bare GET from an external page.

**Protocol inbound:** The IdP **does not possess** Portal's form CSRF token; `POST /logout/saml2/slo` must pass through the signed SAML validator. An **exact** CSRF exemption for the inbound route may be needed depending on Spring config/version, yet **never** disable CSRF app-wide or open an uncontrolled `/logout/**` wildcard.

**Negative test:** Attacker POSTs a fake `SAMLRequest` to the listener without a CSRF token. The request must still be rejected by the SAML validator due to invalid signature/issuer/session—never logging out users solely because a parameter was present.

**Do not confuse 403 and 400:** User forms missing CSRF usually return 403; invalid SAML messages may return 400 from Spring's SAML filter. Assert exact behavior for your pinned version and **side effects** rather than hard-coding a single status when configs vary.

## 10. Spring Boot 3.5.x Sandbox App: Two Independent Buttons

The sample below requires a test IdP with real SLO metadata, SP private signing key/cert, and public HTTPS deployment. SLO cannot be completed with non-live illustrative URLs.

### Structure

~~~text
saml-slo-sandbox/
  pom.xml
  src/main/java/demo/SloSandboxApplication.java
  src/main/resources/application.yml
  src/main/resources/templates/home.html
  src/main/resources/templates/local-signed-out.html
~~~

### pom.xml

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
  <artifactId>saml-slo-sandbox</artifactId>
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

### application.yml

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.test.example.org/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/saml/sp-signing.key
                  certificate-location: file:/run/secrets/saml/sp-signing.crt
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
~~~

`singlelogout.url` is the **SP protocol callback**, not the user trigger. IdP metadata must contain `SingleLogoutService`; the SP **PKCS#8** private key and X.509 public certificate sit outside source code in a secret store/mount. The IdP must be configured with the SP EntityID, ACS/SLO URLs, and signing public cert. If IdP metadata cannot be fetched, Spring may fail at startup.

### SloSandboxApplication.java

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
public class SloSandboxApplication {

    public static void main(String[] args) {
        SpringApplication.run(SloSandboxApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
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
        String home() {
            return "home";
        }

        @GetMapping("/local-signed-out")
        String signedOut() {
            return "local-signed-out";
        }
    }
}
~~~

The controller only renders pages; logout is handled by Spring filters/handlers. Do not add `@PostMapping` handlers implementing logout manually.

### templates/home.html

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>SAML SLO</title></head>
<body>
  <h1>Choose logout scope</h1>
  <form th:action="@{/logout}" method="post">
    <button type="submit">Log out of this application</button>
  </form>
  <p>IdP and other applications may still retain sessions.</p>
  <form th:action="@{/saml2/logout}" method="post">
    <button type="submit">Request federated logout</button>
  </form>
  <p>Federated outcome depends on the IdP and participating SPs.</p>
</body>
</html>
~~~

Verify rendered HTML includes the `_csrf` field injected by template integration. For SPAs/`fetch`, send the CSRF token per repository/header policy; **never** disable CSRF to pass tests.

### templates/local-signed-out.html

~~~html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Local logout</title></head>
<body>
  <h1>Logged out of this application</h1>
  <p>Your SSO session at the IdP may still be active.</p>
  <a href="/">Home</a>
</body>
</html>
~~~

**Run** once keys, test IdP, and DNS/TLS are provisioned:

~~~bash
mvn spring-boot:run
~~~

Observe directly without mocking:
- Local POST → local success page, **no** SAML `LogoutRequest`.
- RP POST → SP emits signed `LogoutRequest` to IdP; IdP may return `LogoutResponse`.
- IdP POST `SAMLRequest` → SP verifies then emits signed `LogoutResponse`.
- IdP POST `SAMLResponse` → SP verifies response correlated to the RP transaction.

## 11. MockMvc: Testing the Servlet Layer Without Mistaking It for SAML Pass

MockMvc helps test routing, CSRF, and local `LogoutHandler`s/redirects. When a Spring Boot app defines `metadata-uri`, test bootstrap may need a sandbox IdP or registration bean fixture to avoid network startup dependencies.

**Example test fragment** (requires section 10 project and test IdP fixture; does not prove signed SAML):

~~~java
package demo;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class LocalLogoutSmokeTest {
    @Autowired MockMvc mvc;

    @Test
    void localLogoutPostWithCsrfCanProceed() throws Exception {
        mvc.perform(post("/logout")
                .with(user("qa-user"))
                .with(csrf()))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void localLogoutWithoutCsrfMustBeRejected() throws Exception {
        mvc.perform(post("/logout")
                .with(user("qa-user")))
            .andExpect(status().isForbidden());
    }
}
~~~

`user("qa-user")` creates a **non-SAML mock principal**: this test only checks CSRF/local filter wiring, **not RP-initiated SLO**. Add tests that verify session/`SecurityContext` post-logout and an IdP message recorder to prove no SAML was emitted. To test SLO, use a SAML principal fixture + signed OpenSAML messages from a test IdP; never mock a validator to `always true` and claim cryptography was tested.

## 12. Standalone Java 17: Test Oracle for Four Events

This program uses pure JDK 17 with **no** Maven/IdP and parses no SAML; it models state decisions from booleans *assumed already verified by the framework*. This is a **unit-level oracle**, not a replacement for signature/protocol integration tests.

**File `SloTestOracle.java`:**

~~~java
public class SloTestOracle {

    enum Event {
        LOCAL, RP_START, IDP_REQUEST, IDP_RESPONSE
    }

    record TestCase(Event event, boolean csrf, boolean samlPrincipal,
                    boolean trustedSignature, boolean sameSubject,
                    boolean correlated, boolean idpAvailable) {}

    static String outcome(TestCase c) {
        return switch (c.event()) {
            case LOCAL -> c.csrf()
                    ? "LOCAL_CLEARED_NO_SAML"
                    : "REJECT_CSRF";
            case RP_START -> {
                if (!c.csrf()) yield "REJECT_CSRF";
                if (!c.samlPrincipal()) yield "REJECT_NO_SAML";
                yield c.idpAvailable()
                    ? "LOCAL_CLEARED_SEND_REQUEST"
                    : "LOCAL_CLEARED_FEDERATION_UNCONFIRMED";
            }
            case IDP_REQUEST -> {
                if (!c.trustedSignature()) yield "REJECT_BAD_REQUEST";
                if (!c.sameSubject()) yield "REJECT_WRONG_SUBJECT";
                yield "LOCAL_CLEARED_SEND_RESPONSE";
            }
            case IDP_RESPONSE -> {
                if (!c.trustedSignature()) yield "REJECT_BAD_RESPONSE";
                yield c.correlated()
                    ? "RESPONSE_CORRELATED"
                    : "REJECT_IN_RESPONSE_TO";
            }
        };
    }

    static void show(String label, TestCase c) {
        System.out.println(label + "=" + outcome(c));
    }

    public static void main(String[] args) {
        show("localOK", new TestCase(
            Event.LOCAL, true, true, false, false, false, false));
        show("localNoCsrf", new TestCase(
            Event.LOCAL, false, true, false, false, false, false));
        show("rpOK", new TestCase(
            Event.RP_START, true, true, false, false, false, true));
        show("rpNoSaml", new TestCase(
            Event.RP_START, true, false, false, false, false, true));
        show("rpOffline", new TestCase(
            Event.RP_START, true, true, false, false, false, false));
        show("idpRequestOK", new TestCase(
            Event.IDP_REQUEST, false, true, true, true, false, true));
        show("idpUnsigned", new TestCase(
            Event.IDP_REQUEST, false, true, false, true, false, true));
        show("idpWrongSubject", new TestCase(
            Event.IDP_REQUEST, false, true, true, false, false, true));
        show("responseOK", new TestCase(
            Event.IDP_RESPONSE, false, false, true, false, true, true));
        show("responseWrongId", new TestCase(
            Event.IDP_RESPONSE, false, false, true, false, false, true));
        show("responseBadSignature", new TestCase(
            Event.IDP_RESPONSE, false, false, false, false, true, true));
    }
}
~~~

Run:

~~~bash
javac SloTestOracle.java
java SloTestOracle
~~~

**Exact stdout:**

~~~text
localOK=LOCAL_CLEARED_NO_SAML
localNoCsrf=REJECT_CSRF
rpOK=LOCAL_CLEARED_SEND_REQUEST
rpNoSaml=REJECT_NO_SAML
rpOffline=LOCAL_CLEARED_FEDERATION_UNCONFIRMED
idpRequestOK=LOCAL_CLEARED_SEND_RESPONSE
idpUnsigned=REJECT_BAD_REQUEST
idpWrongSubject=REJECT_WRONG_SUBJECT
responseOK=RESPONSE_CORRELATED
responseWrongId=REJECT_IN_RESPONSE_TO
responseBadSignature=REJECT_BAD_RESPONSE
~~~

`csrf=false` on `IDP_REQUEST`/`RESPONSE` does not let arbitrary requests bypass security: those are **protocol callbacks** requiring signed SAML validation, not user forms. `trustedSignature` in the demo is an assumed boolean; **never accept a boolean from an HTTP client**. `idpAvailable=false` illustrates local state cleared while federation remains unconfirmed; real timing depends on when network failure occurs. Never use this program as a production logout handler.

## 13. Protocol-Level and System-Level Negative Test Matrix

| ID | Request/state | Expected |
| --- | --- | --- |
| L01 | Local valid POST+CSRF | Local logout, no `LogoutRequest` |
| L02 | Local POST missing CSRF | Rejected, no forced logout |
| L03 | `GET /logout` | No direct logout |
| L04 | Public local success page | No redirect loop |
| L05 | Old `JSESSIONID` after local logout | No authenticated access |
| L06 | Local logout then immediate re-SSO | New Portal session; do not confuse with failure |
| R01 | RP POST valid SAML user+CSRF | Signed `LogoutRequest` to right IdP |
| R02 | RP missing CSRF | No outbound request |
| R03 | RP non-SAML principal | Never sends arbitrary request |
| R04 | IdP has no `SingleLogoutService` | Capability missing; local still usable |
| R05 | Wrong SP signing key/certificate | IdP rejects |
| R06 | Wrong outbound `Issuer` | IdP rejects |
| R07 | Wrong outbound `Destination` | IdP rejects |
| R08 | Wrong `NameID`/Format | Does not log out wrong user |
| R09 | Wrong `SessionIndex` | Does not log out wrong session |
| R10 | Valid `LogoutResponse` matching request | Correlated success/status handled |
| R11 | Unsigned/bad-signature `LogoutResponse` | Rejected |
| R12 | Signed `LogoutResponse` from other IdP | Rejected |
| R13 | Signed `LogoutResponse` with wrong `InResponseTo` | Rejected |
| R14 | Signed `LogoutResponse` with wrong `Destination` | Rejected |
| R15 | Replayed `LogoutResponse` | Rejected / no duplicate completion |
| R16 | Modified `RelayState` | No open redirect / tenant switch |
| R17 | `PartialLogout` | Do not report global success |
| R18 | IdP timeout / browser tab closed | Federation unconfirmed |
| R19 | Callback hits node B missing request | Fail closed; do not drop validation |
| A01 | IdP signed `LogoutRequest` matching subject | Verify, local logout, signed `LogoutResponse` |
| A02 | Unsigned IdP request | Rejected / no session invalidation |
| A03 | IdP wrong signer/`Issuer` | Rejected |
| A04 | IdP wrong `Destination` | Rejected |
| A05 | IdP wrong `NameID` | Does not clear another session |
| A06 | IdP wrong `SessionIndex` | Does not log out wrong session |
| A07 | Malformed Base64/XML | Rejected |
| A08 | Replayed `LogoutRequest` | Rejected / no repeated side effects |
| A09 | IdP request with no active SP session | Creates no new authentication or clears other users |
| A10 | AP flow expecting local success page | Not required: browser belongs to IdP |
| A11 | IdP request from wrong tenant | No cross-tenant logout |
| E01 | Cross-site POST cookie blocked | Detects session/correlation issue |
| E02 | Signing cert rotation | Only approved trusted certs accepted |
| E03 | Reports SP SLO fails | Partial/unconfirmed; local remains right |
| E04 | Session user A vs. B sharing `NameID` | No cross-user/tenant logout |
| E05 | API refresh token still active | SLO does not revoke tokens automatically |
| E06 | User logged in on second device | Do not promise every device logged out |
| E07 | Debug log records raw SAML | QA fails; redact/incident process |
| E08 | LB reverse proxy wrong scheme/host | Fix metadata/public URL; do not disable `Destination` |

### 13.1. Testing Each Validator Independently

If you edit `Destination` inside signed XML, the signature breaks; the test fails on signature **before** the destination rule is measured. To test destination or correlation, the test IdP must issue a **validly signed fixture with only that target field wrong**. Similarly:
- Wrong signer: sign with a key outside trusted IdP metadata.
- Wrong issuer: re-sign with an approved signer yet set an issuer mismatching registration.
- Wrong `InResponseTo`: re-sign with an ID absent from the repository.
- Wrong `SessionIndex`: re-sign a `LogoutRequest` for another subject/session.
- Wrong status: sign a real error/`PartialLogout` `LogoutResponse`.
- Replay: re-submit the **exact** already-processed message and verify replay/side effects.

Never mock `Saml2LogoutRequestValidator` to always pass and claim signature/issuer tests passed.

## 14. Testing Browsers, Clusters, and Hard Cases

**Local browser scenario:**
1. Log into Portal and Reports via the same IdP.
2. Record session fingerprints.
3. Click Local Logout; verify no `SAMLRequest` in the IdP event recorder.
4. Reports may still retain its session; Portal's old session is invalidated.
5. Revisit Portal and distinguish the fresh SSO session from the IdP.

**RP browser scenario:**
1. Log into both SPs; click SAML SLO.
2. Capture the signed `LogoutRequest` SP→IdP, its ID, and signature validation outcome.
3. Track IdP propagation to Reports (if supported) and the callback.
4. Verify `LogoutResponse` signature/`InResponseTo`/status.
5. Inspect each session; expect `PartialLogout` when one SP fails to respond.

**IdP browser scenario:**
1. User logs into Portal.
2. Sandbox IdP initiates SLO for the user's session.
3. Portal receives signed `LogoutRequest`, verifies it, then clears the session.
4. Portal signs `LogoutResponse` back to IdP; do not assert a Portal local success page.
5. Test unsigned/wrong-subject/replay and confirm no forced logout.

**Cluster scenario:** Node A sends `LogoutRequest`, node B receives `LogoutResponse`; repository/session must support correlation or fail safely. Never "fix" by dropping `InResponseTo`. If `SameSite`/HTTPS/proxy drops cookies on cross-site POSTs, test with a real browser. Configure `SameSite=None; Secure` only when contract and threat model require, without weakening CSRF.

**Multi-IdP:** Portal has IdPs A/B; requests must go to the IdP matching the authenticated principal/registration, never selecting an IdP URL from user query parameters. Issuer/signing key of IdP B must never be accepted to log out user A, even with identical `NameID`/email.

**Multi-device:** Browser/session-based SAML SLO does not automatically revoke HTTP sessions on other devices, access/refresh tokens, WebSockets, or non-SAML apps. Offboarding/global logout requires a dedicated session registry and token revocation design.

## 15. Layered Troubleshooting

| Symptom | Possible error source | Remediation |
| --- | --- | --- |
| Clicking local sends `SAMLRequest` | Local/RP URLs not separated | Configure both logout URLs |
| Immediately logged back in after local | IdP SSO cookie still present | Compare old/new sessions, clarify UX |
| Local POST returns 403 | Missing/wrong CSRF token | Supply form token; never disable app-wide |
| RP emits no request | Non-SAML principal or missing SLO config | Check registration/IdP metadata/SP key |
| IdP rejects request | Wrong SP signer/issuer/`NameID`/`SessionIndex` | Check IdP verifier logs + metadata |
| AP request returns 400 | Invalid SAML signature/issuer/destination | Use signed IdP test fixtures |
| AP request returns 403 | CSRF matcher blocks protocol endpoint | Exact exemption + signed SAML validator |
| Callback reports `InResponseTo` mismatch | Lost request state/cookie/cluster | Request repository + `SameSite`/shared store |
| Callback hits wrong host/path | Wrong proxy/public SLO URL | Fix metadata, canonical HTTPS, no bypass |
| `PartialLogout` | One participant failed to respond | Report partial; test Reports separately |
| Login loop on local success | Success page lacks `permitAll` | Permit public access to success page |
| Wrong-correlation tests always fail signature | XML edited post-signing | Re-sign invalid-field fixture |
| IdP timeout | Network/browser incomplete | Local done / federation unconfirmed |
| Logout leaves device B active | No cross-device revocation | Session registry/token policy |
| Key rotation | SP/IdP signers out of sync | Public cert rollover/rotation tests |

**Diagnostic order:** Route+CSRF → local `LogoutHandler`s → outbound resolver & SP signer → IdP SLO service → inbound IdP signer/issuer/destination → request repository/`InResponseTo` → SAML Status → actual SP/IdP/Reports sessions. Never fix a later layer by disabling an earlier validator.

## 16. Recording QA Results and Protecting Data

A useful test report includes:

~~~text
Case ID: R13
Flow: RP-initiated / LogoutResponse callback
SP registration: corporate
Expected: Signed LogoutResponse with unknown InResponseTo rejected
Actual: callback rejected, old session state checked
Signature verified: YES (sandbox IdP test signer)
Correlation verified: NO
Pending request ID: fingerprint only
SAML response Status: not treated as success
Other SP sessions: not asserted
Evidence: redacted test-IdP event ID and SP log correlation ID
Result: PASS
~~~

Reports must never contain: raw `SAMLRequest`/`SAMLResponse`, real `NameID`s, `JSESSIONID`, CSRF tokens, private signing keys, SAML assertions, API tokens, or unnecessary emails/attributes.

**CI:**
- Unit/MockMvc tests run in a dedicated profile with metadata fixtures solely from approved test keys.
- IdP integration can use a test IdP acting as trusted signer to produce **re-signed** negative messages.
- Run browser E2E against a public HTTPS host and real cookie `SameSite` behavior, not MockMvc alone.
- Use isolated test users/sessions per test and clean up IdP/Portal/Reports after the suite.
- Never run malformed SAML tests against a production IdP or real users.
- Monitor signature validation failures, correlation failures, SLO timeouts, and partial statuses.
- A report lacking signing/correlation evidence must never be marked PASS solely on HTTP 302/200.

## 17. Exercises and Mastery Criteria

**Exercise A:** Diagram the four endpoints/actions. Distinguish user form CSRF tokens from signed SAML protocol callbacks.

**Exercise B:** Run `SloTestOracle.java` and match all 11 lines of stdout. Explain why `csrf=false` in the IdP flow does not mean "skipping security."

**Exercise C:** In the Spring Boot sandbox, POST local logout with and without CSRF; assert the old session is invalidated in the valid case, rejected in the invalid case, and zero outbound `SAMLRequest`s are sent.

**Exercise D:** RP SLO against the sandbox IdP: verify outbound signed `LogoutRequest`, exact `Issuer`/`Destination`/`NameID`/`SessionIndex`; IdP returns a signed `LogoutResponse` with matching `InResponseTo`.

**Exercise E:** Have the test IdP re-sign a `LogoutResponse` with wrong `InResponseTo` yet valid signature; prove the SP rejects due to correlation rather than signature.

**Exercise F:** IdP-initiated signed `LogoutRequest` for the right subject → SP performs local logout and returns a signed `LogoutResponse`. Signed request with wrong `NameID` → clears nobody else's session.

**Exercise G:** IdP returns `PartialLogout` because Reports did not respond; design UX stating "Application session ended; federated logout incomplete" instead of "Logged out everywhere."

**Exercise H:** Node A sends `LogoutRequest`, node B receives the callback while `SameSite` blocks the session cookie. Diagnose the request repository and propose a secure configuration.

**Exercise I:** A user has two browsers. IdP-initiated SLO arrives for one session; distinguish current scope from the need for a dedicated global session revocation mechanism.

**Exercise J:** Build a 10-case negative matrix covering signature, issuer, destination, status, session, replay, and CSRF; specify how to create signed invalid-field fixtures to test the exact validator.

**Mastery:** Able to explain and verify **local cleanup with zero SAML**, **transaction-accurate RP `LogoutRequest`/IdP `LogoutResponse`**, **IdP signed `LogoutRequest`/exact principal**, and **failure/partial/multi-node cases** without claiming global logout beyond what evidence proves.

## 18. Official Documentation

- Spring Security 6.5 – Performing Single Logout, APIs, endpoints, handlers, and separating local: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security 6.5 – Handling Logouts and CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security 6.5 – MockMvc setup: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Spring Security 6.5 – SAML2 login/registration: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security – SAML2 metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- OASIS SAML 2.0 Core – Single Logout Protocol: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles – Single Logout Profile, `SessionIndex`, and `PartialLogout`: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML 2.0 Bindings – HTTP-POST/Redirect and signature handling: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OASIS SAML 2.0 Metadata – `SingleLogoutService`: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf

# SubjectConfirmation, Recipient, and InResponseTo in SAML 2.0

## 1. Purpose and Context

When a **Service Provider (SP)** receives a **SAMLResponse** through a browser, a valid digital signature is not enough to conclude that **this Assertion is permitted for the current login session at the current endpoint**. The SP must also verify the subject's confirmation constraints (*subject confirmation*) and its relationship to the issued login request.

The three core concepts are:

1. **SubjectConfirmation**: how the SP confirms that the party presenting the Assertion is permitted to present it to establish the identity named in **Subject**. In **SAML 2.0 Web Browser SSO**, the usual method is **bearer**.
2. **Recipient**: an attribute on **SubjectConfirmationData** explicitly naming the **Assertion Consumer Service (ACS)** to which the Assertion may be delivered.
3. **InResponseTo**: an ID linking a response/confirmation back to a prior **AuthnRequest**, helping the SP verify whether the response belongs to a login transaction the SP itself initiated.

**Learning context:** SAML 2.0 Web Browser SSO Profile, a **Spring Security Servlet** application acting as the SP, and an enterprise IdP acting as the Assertion issuer. Distinguish **OASIS protocol** rules from **Spring Security's specific configuration, request storage, and runtime behavior**.

After this lesson, you should be able to explain *why* these fields exist, *what values they must be compared against*, *when to reject login*, and *how to diagnose issues in real deployments*. Never build a login mechanism by manually parsing Base64/XML and comparing a few strings.

## 2. How Do Subject, SubjectConfirmation, and Bearer Differ?

Inside an Assertion, **Subject** refers to the **user/entity** authenticated by the IdP, usually carrying a **NameID**. Yet merely mentioning a username in an XML document does not prove the document is permitted to log into the SP.

**SubjectConfirmation** sits inside **Subject** and describes the conditions under which a relying party may **confirm the subject**. Each element has a **Method**; the typical value in Web Browser SSO is:

~~~text
urn:oasis:names:tc:SAML:2.0:cm:bearer
~~~

**Bearer** means the party carrying the Assertion (in this flow, the browser forwarding `SAMLResponse`) can present it to confirm the subject **provided all security constraints are satisfied**. The browser does not need to prove possession of a private key. Therefore, a **bearer Assertion must be strictly protected against wrong-target delivery, expiration, and replay**.

Example element carrying the three key fields, solely for explaining structure:

~~~xml
<saml:Subject xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:NameID>employee-123</saml:NameID>
  <saml:SubjectConfirmation
      Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData
        Recipient="https://app.example.com/login/saml2/sso/corp"
        InResponseTo="_req_A01"
        NotOnOrAfter="2026-11-07T09:05:00Z"/>
  </saml:SubjectConfirmation>
</saml:Subject>
~~~

This is an **illustrative XML snippet**, not a complete/signed Response; it **cannot be used to log in**. In the example, the SP needs to know the expected ACS URL, the ID of the issued `AuthnRequest`, and the current time to check the constraints.

### SubjectConfirmationData: Where Conditions Live

**SubjectConfirmationData** supplies the details helping the SP decide whether a specific `SubjectConfirmation` is valid.

| Attribute | Role for bearer Web Browser SSO | Example/note |
| --- | --- | --- |
| **Recipient** | Required: binds the Assertion to the receiving SP's ACS URL. | https://app.example.com/login/saml2/sso/corp |
| **NotOnOrAfter** | Required: latest timestamp at which the subject can be confirmed. | 2026-11-07T09:05:00Z |
| **InResponseTo** | Required to match **AuthnRequest.ID** when the Response answers an AuthnRequest; must not appear in unsolicited responses per the Web Browser SSO Profile. | _req_A01 |
| **Address** | Optional: restricts the user agent's network address; checked per policy/profile. | May be unreliable behind proxies, NAT, or mobile networks. |
| **NotBefore** | Allowed by the general SAML data type, **but the Web Browser SSO bearer profile specifies it must not be included in bearer SubjectConfirmationData**. | Do not confuse with **Conditions.NotBefore**. |

Common pitfall: **SubjectConfirmationData.NotOnOrAfter is not the lifetime of the application web session**; it only states that the Assertion may be presented to confirm the subject before this timestamp. The application session created after login has its own lifecycle.

An Assertion may contain **multiple `SubjectConfirmation` elements**. Per Web Browser SSO rules and OASIS errata, **a single bearer `SubjectConfirmation` satisfying all conditions may suffice to confirm that Assertion's subject**; if a Response contains multiple Assertions that are used, **each Assertion must still be evaluated independently**. Do not write logic that arbitrarily “takes the first element and ignores all others.”

## 3. Recipient: Binding to the Exact Consumption Endpoint

**Recipient** is located at:

~~~text
Assertion
└── Subject
    └── SubjectConfirmation (Method=bearer)
        └── SubjectConfirmationData Recipient="..."
~~~

It must designate the **actual SP ACS address** to which the Response is delivered, for example:

~~~text
https://app.example.com/login/saml2/sso/corp
~~~

With Spring Security Servlet, the default URL handling `SAMLResponse` usually looks like **/login/saml2/sso/{registrationId}**. If `registrationId` is **corp**, the ACS in the example must be **registered accurately at the IdP** and **Spring Security** must observe the exact same public URL.

### What Does Recipient Protect Against?

Suppose the same IdP trusts two SPs:

- **SP A:** https://app-a.example.com/login/saml2/sso/corp
- **SP B:** https://app-b.example.com/login/saml2/sso/corp

An Assertion issued by the IdP with **A's Recipient** must not be usable to log into **B**, even if both A and B trust signatures from the **same IdP**. This check prevents an Assertion from being redirected to the **right kind of system, wrong application**.

Similarly, two ACS endpoints on the same host can be two distinct targets:

- https://app.example.com/login/saml2/sso/corp
- https://app.example.com/login/saml2/sso/partner

If a token was issued for **corp**, it must not be accepted at the **partner** endpoint merely because the hostname matches.

### Recipient Differs from Response.Destination and Audience

| Field | Where is it? | Compared against what? | Purpose |
| --- | --- | --- | --- |
| **Recipient** | **SubjectConfirmationData** inside Assertion | ACS URL where the bearer Assertion is delivered. | Confirms the **permitted receiving target for the Assertion**. |
| **Destination** | **Response** attribute (protocol message) | Receiving target for the Response per binding, usually also the ACS URL. | Confirms the **protocol message was sent to the right endpoint**. |
| **Audience** | **Conditions → AudienceRestriction → Audience** inside Assertion | **SP's entityId**. | Confirms **which RP is permitted to consume the Assertion**. |
| **Issuer** | Response/Assertion Issuer | Trusted IdP/partner identifier in registration. | Confirms the **issuing party**. |

All three fields—**Recipient**, **Destination**, and **Audience**—matter, yet they **cannot substitute for one another**. For example, the SP's `entityId` may be **https://app.example.com/saml/metadata**, while the ACS is **https://app.example.com/login/saml2/sso/corp**. Audience must match `entityId`, and Recipient must match ACS.

Do not use a generic “same hostname” check for both Recipient and Audience. Nor should you normalize differing URLs by arbitrarily stripping schemes, ports, or paths. Match the public URLs in SP metadata, IdP registration, and actual XML values according to protocol and library rules.

### Typical Failure Behind a Reverse Proxy

The SP runs internally at **http://spring-internal:8080**, while browsers access **https://app.example.com**. If the IdP sends:

~~~xml
<saml:SubjectConfirmationData
    Recipient="https://app.example.com/login/saml2/sso/corp"
    NotOnOrAfter="2026-11-07T09:05:00Z"/>
~~~

while the application resolves its default ACS as **http://spring-internal:8080/login/saml2/sso/corp**, matching can fail. The fix is to **align the public URL**: trusted proxy headers, proper base URL/`entityId`/ACS configuration, and matching IdP metadata and SP metadata. **Never** fix it by disabling Recipient checks.

If error logs alternate between **http** and **https**, or change hosts across load balancers, inspect the deployment topology first before altering validation.

## 4. InResponseTo: Binding the Response to the Login Request

In **SP-initiated SSO**, the application creates an **AuthnRequest** itself. The `AuthnRequest` carries a **unique, unpredictable ID** for the transaction, such as:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_req_A01"
    Version="2.0"
    IssueInstant="2026-11-07T09:00:00Z"
    Destination="https://idp.example.org/sso"
    AssertionConsumerServiceURL="https://app.example.com/login/saml2/sso/corp"/>
~~~

This example omits elements of a real `AuthnRequest` to highlight **ID**; it is not a complete message to send to an IdP. The SP stores **the pending request context** in the appropriate state store, then the browser redirects to the IdP.

After authentication, the IdP sends **Response.InResponseTo** and **SubjectConfirmationData.InResponseTo** pointing to **the same original ID**. Upon receiving the callback, the SP must verify:

1. Was a **corresponding AuthnRequest** actually **created and stored by the SP** for this flow/browser session?
2. Does **Response.InResponseTo** match the stored **AuthnRequest.ID**?
3. Does **SubjectConfirmationData.InResponseTo** on the chosen bearer confirmation match the **AuthnRequest.ID**?
4. Does the pending request match the **IdP, registration, endpoint, RelayState, browser session, and one-time/expiry policies**?
5. Are the Response and Assertion still valid across independent checks such as signature, issuer, audience, timestamps, and recipient?

**Do not treat InResponseTo as sole proof that the response belongs to the right browser session.** An attacker may know or supply the same ID string; the SP needs saved request state **bound to the right login context** plus the remaining protocol constraints.

### Three Easily Confused IDs

| Field | Example | Created by | Used for |
| --- | --- | --- | --- |
| **AuthnRequest.ID** | _req_A01 | SP | Identifies the issued **login request**. |
| **Response.ID** | _res_B52 | IdP | Identifies the **Response** itself returned by the IdP; usable for logging/audit/anti-replay. |
| **Assertion.ID** | _assert_C77 | IdP | Identifies the **Assertion**; useful when enforcing one-time/anti-replay policies. |

Therefore, **InResponseTo must match _req_A01**, **not _res_B52 or _assert_C77**. Nor is it `SessionIndex`, `NameID`, `JSESSIONID`, a cookie, `RelayState`, or a user ID.

### InResponseTo at Two Layers

**InResponseTo** can appear on:

- **Response.InResponseTo**: attribute on the **SAML protocol Response**, indicating which request the Response answers.
- **SubjectConfirmationData.InResponseTo**: condition on **bearer subject confirmation**, binding the Assertion to the same initial request.

Understand these as **two distinct XML locations**. For an SP-initiated flow, one location being right **creates no exception** if the other location is wrong. A profile-compliant validator must not check only the Response attribute and skip the one inside bearer `SubjectConfirmationData`.

## 5. XML Example Showing All Three Rules

Assume:

- IdP entityId: **https://idp.example.org/metadata**
- SP entityId: **https://app.example.com/saml2/service-provider-metadata/corp**
- SP ACS: **https://app.example.com/login/saml2/sso/corp**
- SP just sent an `AuthnRequest` with ID **_req_A01**
- IdP issues the Assertion at **09:00:25 UTC**, and bearer confirmation expires at **09:05:00 UTC**.

This is a **simplified XML diagram** for learning structure. It **lacks an XML Signature** and detailed profile verification fields, so it is **not a valid SAMLResponse for login**. In a real system, the IdP signs the Response or Assertion per trust requirements and Spring Security/OpenSAML verifies the signature.

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_res_B52"
    Version="2.0"
    IssueInstant="2026-11-07T09:00:25Z"
    Destination="https://app.example.com/login/saml2/sso/corp"
    InResponseTo="_req_A01">

  <saml:Issuer>https://idp.example.org/metadata</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>

  <saml:Assertion
      ID="_assert_C77"
      Version="2.0"
      IssueInstant="2026-11-07T09:00:25Z">
    <saml:Issuer>https://idp.example.org/metadata</saml:Issuer>

    <saml:Subject>
      <saml:NameID>employee-123</saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://app.example.com/login/saml2/sso/corp"
            InResponseTo="_req_A01"
            NotOnOrAfter="2026-11-07T09:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2026-11-07T08:59:30Z"
        NotOnOrAfter="2026-11-07T09:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://app.example.com/saml2/service-provider-metadata/corp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>

    <saml:AuthnStatement
        AuthnInstant="2026-11-07T09:00:10Z">
      <saml:AuthnContext>
        <saml:AuthnContextClassRef>
          urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
      </saml:AuthnContext>
    </saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

Reading from the outside in:

1. **Response.InResponseTo=_req_A01**: the protocol response targets the SP's `AuthnRequest`.
2. **Response.Destination=ACS**: the Response message is delivered to the valid ACS endpoint.
3. **Assertion.Subject.NameID=employee-123**: subject described by the IdP, **not self-sufficient proof**.
4. **SubjectConfirmation.Method=bearer**: permits confirming the subject via the bearer profile.
5. **SubjectConfirmationData.Recipient=ACS**: only this endpoint may confirm the subject.
6. **SubjectConfirmationData.InResponseTo=_req_A01**: subject confirmation binds to the exact original request.
7. **SubjectConfirmationData.NotOnOrAfter=09:05 UTC**: bearer confirmation must not be accepted after this time, allowing minor clock skew per policy.
8. **Conditions.Audience**: the Assertion is intended only for the SP with that specific `entityId`.
9. **Signature, issuer, status, timing, correlation, and anti-replay** still must be checked independently before creating an `Authentication`.

### What Happens If Only Recipient Changes?

Keep every other field intact, but change:

~~~xml
<saml:SubjectConfirmationData
    Recipient="https://other-app.example.com/login/saml2/sso/corp"
    InResponseTo="_req_A01"
    NotOnOrAfter="2026-11-07T09:05:00Z"/>
~~~

The SP at **app.example.com** must reject this confirmation because **Recipient** does not match the **ACS receiving the Response**. If someone altered the XML after the IdP signed it, the signature would also break; yet **never skip Recipient verification merely because the signature was originally valid**. The two defenses solve different problems.

### What If Only InResponseTo Changes?

~~~xml
<saml:SubjectConfirmationData
    Recipient="https://app.example.com/login/saml2/sso/corp"
    InResponseTo="_req_KHAC"
    NotOnOrAfter="2026-11-07T09:05:00Z"/>
~~~

The SP's pending request is **_req_A01**, so this confirmation does not match that login transaction. It must be rejected in an SP-initiated context, even though **Recipient** matches.

## 6. NotOnOrAfter: A Time Boundary That Must Not Be Skipped

The Web Browser SSO bearer profile requires **SubjectConfirmationData.NotOnOrAfter**. Once the current time reaches or exceeds this boundary, confirmation is **no longer valid** (aside from minor, properly configured clock skew).

Example without clock skew:

| SP check time (UTC) | NotOnOrAfter | Bearer confirmation still valid? |
| --- | --- | --- |
| 09:04:59Z | 09:05:00Z | Yes |
| 09:05:00Z | 09:05:00Z | **No** – **exclusive** of the exact end timestamp |
| 09:05:01Z | 09:05:00Z | No |
| 09:00:00Z | 09:05:00Z | Yes on **timing**, yet all other checks still apply |

Do not confuse:

- **Conditions.NotBefore / Conditions.NotOnOrAfter:** general time conditions for accepting the Assertion.
- **SubjectConfirmationData.NotOnOrAfter:** deadline for confirming the subject as bearer.
- **AuthnStatement.AuthnInstant:** timestamp when the IdP authenticated the user.
- **AuthnStatement.SessionNotOnOrAfter:** session limit associated with `AuthnStatement` if present, handled per profile/policy; does not replace `SCD.NotOnOrAfter`.
- **HttpSession timeout / JSESSIONID:** lifetime of the Spring application session; not how long an Assertion can be reused.

In particular, **NotBefore may appear in Conditions**, yet per **Web Browser SSO bearer confirmation** rules, **do not put NotBefore on bearer SubjectConfirmationData**. If an IdP emits non-compliant data, fix the IdP's configuration/issuance rather than removing time checks.

**Clock skew** is meant only to tolerate minor infrastructure clock drift, not as a trick to extend Assertions for hours. Sync NTP on SP and IdP; when tuning skew, evaluate its impact on all time checks and replay windows.

## 7. SP-Initiated vs. IdP-Initiated: How Does InResponseTo Differ?

### 7.1. SP-Initiated Login

The Spring application starts with:

~~~text
GET /saml2/authenticate/corp
    -> Spring creates AuthnRequest ID=_req_A01
    -> saves pending request in repository/session
    -> browser is redirected to IdP
    -> IdP sends Response InResponseTo=_req_A01
    -> bearer SubjectConfirmationData InResponseTo=_req_A01
    -> SP verifies and creates Authentication if all conditions pass
~~~

The link must be a **real SP-issued AuthnRequest** and **real saved request context**, not merely two strings on two XML tags happening to match.

### 7.2. IdP-Initiated / Unsolicited Response

Some IdPs offer a portal where users click an application tile so the IdP sends a Response **even though the SP never issued an AuthnRequest**. This is an **unsolicited Response**.

According to the Web Browser SSO Profile, **an unsolicited Response must not contain `Response.InResponseTo`**, and bearer `SubjectConfirmationData` must also **not use `InResponseTo` to fake a nonexistent request**. The SP must have a dedicated **unsolicited acceptance policy**: allowed partners, ACS, recipient, audience, timing, signature, replay, `RelayState` handling, login CSRF, and safe redirect destinations.

**Do not mechanically apply a rule that “InResponseTo is always mandatory in every SAMLResponse.”** The right rule is:

| Flow type | Does SP have a pending AuthnRequest? | Response.InResponseTo / SubjectConfirmationData.InResponseTo |
| --- | --- | --- |
| **SP-initiated** | Yes | **Must match** the original `AuthnRequest` ID per profile. |
| **IdP-initiated (unsolicited)** | No | Per profile, **must be absent**; the SP must decide whether to support/allow this flow. |

**Minimize attack surface:** if the application does not need IdP-initiated login, **reject unsolicited Responses** as supported by your provider's config/design and test this behavior. Never disable SP-initiated `InResponseTo` checks just to make an IdP portal tile work.

### 7.3. RelayState Is Not InResponseTo

**RelayState** is a SAML binding parameter used to preserve navigation/context or assist transaction lookup, depending on implementation. **AuthnRequest.ID/InResponseTo** is a SAML constraint inside the message itself.

- **RelayState** can be forwarded by the browser or affected by different state-storage designs; use it only as **one component of a protected context-storage mechanism**.
- **InResponseTo** must correlate with the exact initial `AuthnRequest` ID.
- Do not treat `RelayState` “looking like a secret token” as sufficient to authenticate a SAML Response.
- If `RelayState` is used to choose a return URL, restrict allowed URLs to prevent **open redirects**.

Storing requests in a **browser-bound session** usually helps mitigate login CSRF. If using a distributed store looked up via `RelayState` or `InResponseTo`, explicitly design **browser/session binding, TTL, randomness, one-time consumption, and anti-replay**.

## 8. Proper Verification Flow in Conceptual Order

The exact technical ordering lives inside the provider, depending on whether Response or Assertion is signed and on decryption steps. **Do not hand-write a validator** from the list below; use a vetted SAML library/framework. This list clarifies the groups of checks the SP must ensure **before creating an `Authentication`**.

1. **Receive on right endpoint and binding:** the ACS is processing `SAMLResponse` for the expected registration/IdP; payload size, XML parser, and transport are controlled.
2. **Establish trusted origin:** rely on administered `RelyingPartyRegistration` and metadata/certificates, never on an unverified issuer field sent by the browser.
3. **Verify signatures** per SP policy and Response/Assertion signing model; handle encrypted Assertions when configured and enforce matching signature conditions.
4. **Response-level validation:** issuer, success status, `Destination`, message timestamps/attributes, and **Response.InResponseTo** for SP-initiated flows.
5. **Assertion-level validation:** issuer, signature or policy-accepted protection coverage, **Conditions**, **AudienceRestriction**, time limits, and `AuthnStatement`.
6. **SubjectConfirmation:** check **bearer** method, **Recipient**, **NotOnOrAfter**, **InResponseTo**, optional `Address`, and other constraints if required by profile.
7. **Correlation + replay:** bind to the stored request in the right context, consume request/response/assertion one-time per policy; reject repeated or cross-session responses.
8. **Create Authentication:** only upon valid results, grant local `SecurityContext`/session and map application authorities. Resource-level authorization checks inside the app are still required.

**All security checks must pass together per profile.** A valid signature **does not bypass Recipient**, a right Recipient **does not bypass InResponseTo**, and a right `InResponseTo` **does not bypass signature/audience/expiry**.

### Two Attack Scenarios to Picture

**Response replayed to another application.** The IdP signs an Assertion for A; an attacker tries submitting it to B's ACS. If B verifies only the IdP signature without checking **Recipient/Audience**, it could log the user into the wrong application. That is why both the Assertion destination and the SP entity ID permitted to consume it must be checked.

**Login CSRF / cross-session response.** An attacker initiates login in their own browser, captures a valid Response for themselves, and tries forcing that Response into the victim's browser. If the SP trusts only the signature and `NameID` without tying **InResponseTo to a request initiated by the victim's session**, the victim risks being logged into the attacker's account. Thus request correlation and session binding carry independent security value.

## 9. Where Does Spring Security Servlet Perform These Checks?

For a SAML2 Service Provider, Spring Security provides **`saml2Login()`**; primary processing components include:

- **Saml2WebSsoAuthenticationRequestFilter**: creates `AuthnRequest` and sends it to the IdP.
- **Saml2AuthenticationRequestRepository**: stores `AuthnRequest` context for retrieval when the IdP returns a Response. The common default uses **HttpSessionSaml2AuthenticationRequestRepository**.
- **Saml2WebSsoAuthenticationFilter**: receives POST `SAMLResponse` at the ACS; delegates to `AuthenticationConverter`/`AuthenticationManager`.
- **Saml2AuthenticationTokenConverter**: resolves `RelyingPartyRegistration` and the SAML Response context; lookup may use the saved request, URL `registrationId`, and issuer per configured strategy.
- **OpenSAML authentication provider**: decrypts/verifies Response and Assertion per registration/trust/validation policy, then creates `Authentication`.

**Version note:** Spring Security **6.x** has APIs/providers based on **OpenSAML 4** (and certain 6.x versions support OpenSAML 5); **Spring Security 7.x** documentation presents **OpenSaml5AuthenticationProvider**. When customizing validators, **consult the exact Spring Security/OpenSAML version of your project**, rather than copying imports or constructors from another version's docs. Most applications only need proper IdP configuration and letting default validations run; avoid replacing the entire `AuthenticationManager` unnecessarily.

### Why Is the AuthnRequest Repository So Important?

Suppose a request has ID **_req_A01**. Spring must be able to look up the **original AuthnRequest** after the browser visits the IdP and returns to the ACS. Storing requests in **HttpSession** helps bind the request to the corresponding browser session, mitigating login fixation/CSRF.

Common failures that lose the original request:

- Browser session lost due to `SameSite`, `Secure` cookies, reverse proxy, or inconsistent hostnames.
- Session timeout while the user completes login/MFA at the IdP.
- Multi-instance Spring cluster without shared/properly routed sessions.
- User opens multiple tabs, launching parallel `AuthnRequest`s while a custom request store keeps only one transaction.
- Callback lands on a different registration or ACS after IdP/proxy configuration changes.

**Right fix:** fix session management, request repository, cookie policy, reverse proxy, and IdP registration; never remove `InResponseTo` validation to mask lost state.

### Successful Authentication Does Not Mean Reusing SAMLResponse

`SAMLResponse` is used to **establish a session** at callback time. Afterward, the application normally maintains its own local Spring Security session. Do not store a `SAMLResponse` as a “login cookie” replayed on every HTTP request, and do not rely on the mere presence of an ID token/OAuth token or `NameID` to skip SAML checks.

## 10. Minimal Spring Security Configuration Example

Practical example for **Spring Boot 3.3.5, Java 17**, using a **real SAML IdP**. Its purpose is to let Spring Security **verify SAML conditions itself**; there is no custom code “bypassing” `Recipient`, `InResponseTo`, or signatures.

### 10.1. Maven Dependencies

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>saml-confirmation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
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

### 10.2. Registering the IdP Partner

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: ${SAML_IDP_METADATA_URI}
server:
  port: 8080
~~~

Set the **SAML_IDP_METADATA_URI** environment variable to the XML metadata of a real, trusted IdP. Register the SP at the IdP with public **SP entityId/ACS** matching the application's metadata. Use HTTPS URLs in real deployments. If the IdP requires a **signed AuthnRequest** or encrypted Assertions, configure SP signing/decryption credentials per Spring configuration; this minimal example omits private keys.

**registrationId = corp** identifies the RP partner in Spring, **not** a subject/user ID.

### 10.3. Spring Boot Application

**src/main/java/com/example/samlconfirmation/SamlConfirmationApplication.java**

~~~java
package com.example.samlconfirmation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlConfirmationApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlConfirmationApplication.class, args);
    }
}
~~~

**src/main/java/com/example/samlconfirmation/SecurityConfig.java**

~~~java
package com.example.samlconfirmation;

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
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**src/main/java/com/example/samlconfirmation/DemoController.java**

~~~java
package com.example.samlconfirmation;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "SP ready";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return "NameID=" + principal.getName();
    }
}
~~~

Set the environment variable, verify IdP metadata, and run from the directory containing **pom.xml**:

~~~bash
mvn spring-boot:run
~~~

**Valid verification outcomes:**

- **GET http://localhost:8080/** returns exact **SP ready**, without SAML login.
- **GET http://localhost:8080/saml2/metadata/corp** exports **SP metadata XML** when registration is configured successfully and the endpoint is allowed, helping verify SP `entityId` and ACS; it is not IdP metadata.
- **GET http://localhost:8080/saml2/authenticate/corp** creates an `AuthnRequest` to start SAML login.
- **GET http://localhost:8080/me** without a session starts the login flow; if the IdP issues a valid Response/Assertion, the body has the form **NameID=<value issued by the IdP>**. The subject value is not fixed.

The application completes SSO only with a **real IdP, valid trust certificate, matching registered ACS/entityId**, and an IdP-issued Assertion with valid **Recipient, InResponseTo, expiry**, and other checks. This example is based on Spring Security 6.x; if deploying another version, preserve protocol rules and check configuration/APIs against that version's docs.

**Do not add a controller handling POST ACS to invoke an XML parser yourself**. Spring Security/OpenSAML handles SAML verification; application code receives `Authentication` **after** validation succeeds.

## 11. Java 17: Simulating Three Comparisons as a Mnemonic

This **pure Java** example can be compiled/run standalone and illustrates only the basic **Recipient**, **InResponseTo**, and **NotOnOrAfter** checks in an SP-initiated flow. **Do not use this snippet for real SAML authentication:** it does **not** decode SAML, verify signatures, issuer, audience, response-level `InResponseTo`, XML schema, session binding, anti-replay, or the full profile.

**ConfirmationRulesDemo.java**

~~~java
import java.time.Instant;

public class ConfirmationRulesDemo {
    private record Confirmation(
            String recipient,
            String inResponseTo,
            Instant notOnOrAfter) {}

    private static boolean matchesThreeFields(
            Confirmation data,
            String expectedAcs,
            String savedRequestId,
            Instant now) {

        return expectedAcs.equals(data.recipient())
                && savedRequestId.equals(data.inResponseTo())
                && now.isBefore(data.notOnOrAfter());
    }

    public static void main(String[] args) {
        String acs = "https://app.example.com/login/saml2/sso/corp";
        String requestId = "_req_A01";
        Instant now = Instant.parse("2026-11-07T09:00:00Z");
        Instant expiry = Instant.parse("2026-11-07T09:05:00Z");

        Confirmation valid = new Confirmation(acs, requestId, expiry);
        Confirmation wrongRecipient = new Confirmation(
                "https://other.example.com/login/saml2/sso/corp",
                requestId, expiry);
        Confirmation wrongRequest = new Confirmation(
                acs, "_req_OTHER", expiry);
        Confirmation expired = new Confirmation(acs, requestId, now);

        System.out.println("valid: "
                + matchesThreeFields(valid, acs, requestId, now));
        System.out.println("wrong recipient: "
                + matchesThreeFields(wrongRecipient, acs, requestId, now));
        System.out.println("wrong InResponseTo: "
                + matchesThreeFields(wrongRequest, acs, requestId, now));
        System.out.println("expired: "
                + matchesThreeFields(expired, acs, requestId, now));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac ConfirmationRulesDemo.java
java ConfirmationRulesDemo
~~~

**Exact stdout:**

~~~text
valid: true
wrong recipient: false
wrong InResponseTo: false
expired: false
~~~

Explanation:

- **valid: true** means **only that the three simulated comparisons passed**. It does **not** mean a real `SAMLResponse` is safe for login.
- **wrong recipient** fails because the Assertion was sent to a different ACS.
- **wrong InResponseTo** fails because the ID does not match the saved request ID.
- **expired** fails because the current instant **equals** `NotOnOrAfter`, whereas the required condition is strictly **before** that timestamp.

In a real application, never use the boolean output above to grant a `SecurityContext`; let Spring Security/OpenSAML execute full validation.

## 12. Security Test Matrix and Expected Results

Run tests **in a sandbox with a controllable IdP/SP**, generating **validly signed SAMLResponses with test keys** when isolating a single condition. If you hand-edit signed XML, the broken signature causes the test to prove only that **signature validation** works, without exercising the Recipient/`InResponseTo` validator. Never put test private keys into production systems.

| # | Scenario | Expected outcome at SP |
| --- | --- | --- |
| 1 | Signature/issuer/audience valid; Recipient = ACS; InResponseTo in both Response and SCD = pending request; valid timing | **Accept**, provided all remaining validations also pass. |
| 2 | Recipient is another **SP's ACS** | **Reject** subject confirmation. |
| 3 | Recipient has the right hostname but wrong ACS path | **Reject**. |
| 4 | Recipient uses **http** instead of SP's public **https** | **Reject** if it does not match the valid ACS. |
| 5 | Response.InResponseTo does not match AuthnRequest.ID | **Reject** SP-initiated response. |
| 6 | Response.InResponseTo matches, but SCD.InResponseTo is wrong | **Reject** bearer confirmation not matching request. |
| 7 | SCD.InResponseTo matches, but Response.InResponseTo is wrong | **Reject** response not matching request. |
| 8 | InResponseTo points to an **expired/already consumed** request | **Reject** per correlation/anti-replay policy. |
| 9 | NotOnOrAfter **has passed** or time equals exact deadline, without skew | **Reject** confirmation. |
| 10 | SCD lacks Recipient or NotOnOrAfter required for bearer Web Browser SSO | **Reject** due to missing profile requirements. |
| 11 | NotBefore is present in bearer SCD | **Non-compliant with Web Browser SSO bearer profile**; IdP must fix message. |
| 12 | Destination is wrong while Recipient is right | **Reject** Response due to invalid Destination. |
| 13 | Audience lacks SP entityId while Recipient is right | **Reject** Assertion because it was not issued for this SP. |
| 14 | IdP-initiated unsolicited Response **without InResponseTo** | Consider only if RP **explicitly permits unsolicited** and all other checks pass; if policy forbids it, **reject**. |
| 15 | IdP-initiated unsolicited Response injects a fake InResponseTo | **Reject** per profile/policy; do not invent a request that never existed. |
| 16 | Two bearer confirmations: one valid, one invalid | Per profile/errata, **one valid confirmation may suffice for that Assertion**; still check other rules and each Assertion separately. |
| 17 | Replayed Response/Assertion after already creating a session | **Reject replay** per implemented correlation/one-time/anti-replay mechanism. |
| 18 | Multi-instance Spring SP, callback cannot find AuthnRequest because sessions are not shared | **Do not accept response**; fix session/repository. |
| 19 | IdP issues a valid-looking Response whose signature fails SP trust verification | **Reject**, even if Recipient/InResponseTo/expiry are all valid. |

**Do not aim to “fix things so every case logs in.”** Negative testing succeeds when the SP **correctly rejects** invalid cases.

### Testing Across Multiple Tabs and Multiple IdPs

Logging in simultaneously in two tabs can generate two `AuthnRequest`s, **_req_A01** and **_req_A02**. Each Response must bind only to its corresponding request; if the framework/repository limits concurrent requests, know and test the actual behavior, never allowing callback A02 to match request A01.

If the application supports multiple IdPs, the request ID must be verified alongside the **right registration/IdP and ACS**. Never receive a Response claiming issuer IdP X while trusting IdP Y's certificate, or look up registration details from a URL value arbitrarily chosen by an attacker.

## 13. Troubleshooting Errors in Spring Security

| Symptom | Possible cause | Safe diagnostic direction |
| --- | --- | --- |
| “Invalid Recipient” or SubjectConfirmation validation failure | Assertion ACS does not match SP URL/registration; wrong host/port/path | Compare **Recipient**, ACS in SP metadata, IdP app config, and proxy public URL. |
| “InResponseTo mismatch”, “No matching AuthnRequest” | Saved request lost, wrong ID, missing session/cookie, or unsolicited response | Check request repository, browser session, TTL, and callback order; never disable correlation. |
| Login fails after lengthy MFA | Pending request session or NotOnOrAfter expired | Compare UTC timestamps, timeouts, and IdP policy; sync NTP. |
| Fails only behind HTTPS reverse proxy | Spring constructs internal HTTP/hostname/port ACS | Fix forwarded headers, public base URL, SP metadata, and IdP config. |
| Fails in second tab | Two parallel requests overwrite/collide on ID in custom storage | Check how the repository manages concurrent requests and session binding. |
| Assertion validly signed yet SP still rejects | Recipient, audience, issuer, InResponseTo, Conditions, or SCD expiration mismatch | Check **each validation group**; never assume a good signature guarantees login. |
| Only IdP portal launch fails | Unsolicited not supported or RelayState/ACS misconfigured | Decide IdP-initiated requirement, evaluate login CSRF/replay, configure explicitly. |
| Resubmitted SAMLResponse rejected on second attempt | Request already consumed or response detected as replay | This is usually the **intended security behavior**. |
| SecurityContext has principal, yet user lacks business permissions | SAML authentication finished, role/authority mapping missing | Handle **authorization** separately; never tweak SubjectConfirmation to grant roles. |

### How to Log Without Leaking Data?

In development environments, log **sanitized** details such as: `registrationId`, internal correlation ID, validation error category, error code, and expected/actual ACS hostname when appropriate. You may log **transaction IDs** per security policy, but avoid logging full raw `SAMLResponse`, sensitive `NameID`s, personal Attributes, session cookies, private keys, signatures, or authentication credentials. Never paste Base64 Assertions into public chats/tickets.

When debugging failures, **never** edit a production XML file and “skip the signature to see if it works.” Test in a separate environment with a test IdP capable of issuing properly signed responses for each negative case.

## 14. Common Mistakes to Avoid

1. **“NameID is right so login works.”** Wrong: `NameID` only identifies the Subject; `SubjectConfirmation`, signature, audience, recipient, correlation, and timestamps must all be valid.
2. **“Recipient is the IdP URL.”** Wrong: in bearer Web Browser SSO, Recipient points to the **SP's ACS**. The IdP SSO URL is the target of `AuthnRequest`, not where the Assertion is returned.
3. **“Audience and Recipient are the same.”** Wrong: Audience is usually the **SP entityId**, while Recipient is the **ACS URL**.
4. **“If Response.InResponseTo matches, SCD.InResponseTo isn't needed.”** Wrong: these are two distinct binding layers; the SP-initiated profile requires exact correlation matching.
5. **“InResponseTo must be present even for IdP-initiated login.”** Wrong: unsolicited Responses have no original `AuthnRequest`, so they need a dedicated policy instead of inventing a dummy ID.
6. **“RelayState can replace InResponseTo.”** Wrong: `RelayState` assists forwarding context but is not a substitute for request correlation and signature/trust proof.
7. **“Checking the signature alone is enough.”** Wrong: an Assertion with a valid signature sent to the wrong SP, expired, or belonging to another transaction still must be rejected.
8. **“NotOnOrAfter is the JSESSIONID timeout.”** Wrong: this boundary limits presenting bearer confirmation, not the local web session lifetime.
9. **“Having NotBefore in every SCD is safer.”** Wrong: the Web Browser SSO bearer profile **forbids NotBefore in bearer SubjectConfirmationData**, even though `Conditions.NotBefore` remains valid in the protocol.
10. **“If sessions drop, just disable InResponseTo checks.”** Wrong: doing so removes login CSRF/correlation protection; fix request storage and cookies/clustering instead.
11. **“If a SAMLResponse has multiple confirmations, accept the first one.”** Wrong: evaluate confirmations by method and conditions; per errata, one valid bearer confirmation may suffice for that Assertion, without arbitrarily skipping other Assertions.
12. **“Comparing Recipient with string equals means SAML is integrated.”** Wrong: comparing three fields is only a tiny slice. Use a maintained, profile-compliant SAML library/validator.

## 15. Practice Questions

**Question 1.** SP A has ACS **https://a.example.com/login/saml2/sso/corp**, while the IdP sends an Assertion with Recipient **https://b.example.com/login/saml2/sso/corp**. The IdP signature is valid. Should A log the user in?  
**Answer:** **No**. Recipient binds the Assertion to ACS B, not A. A valid signature does not change the intended recipient.

**Question 2.** The SP sent `AuthnRequest.ID` **_req_123**, `Response.InResponseTo` is **_req_123**, and `SubjectConfirmationData.InResponseTo` is **_req_999**. Can `Response.InResponseTo` be treated as overriding?  
**Answer:** **No**. In SP-initiated Web Browser SSO, bearer confirmation must correlate to the exact saved request. A confirmation with the wrong `InResponseTo` fails subject confirmation.

**Question 3.** A user clicks an app icon in the IdP portal; the SP never sent an `AuthnRequest`. Should the SP invent a fake ID to satisfy `InResponseTo`?  
**Answer:** **No**. That is an unsolicited/IdP-initiated flow requiring a dedicated support policy. Without a business need and security review, reject it.

**Question 4.** Recipient matches ACS, `InResponseTo` matches `AuthnRequest`, yet `NotOnOrAfter` passed 10 minutes ago. Accept it?  
**Answer:** **No**. `SubjectConfirmationData` has expired. Inspect clocks, profile, and re-issuing the Response rather than arbitrarily widening skew.

**Question 5.** A reverse proxy runs the SP over internal HTTP while the public URL is HTTPS. The IdP sends an HTTPS Recipient, and Spring resolves an HTTP ACS. What do you fix first?  
**Answer:** Fix **forwarded headers/base URL/metadata/IdP registration** so SP and IdP agree on the same public ACS. Never remove Recipient validation.

**Question 6.** Can you write a Java method comparing three strings and place the user directly into `SecurityContext`?  
**Answer:** **No**. That approach lacks signature/trust, issuer, audience, `Conditions`, response validation, anti-replay, safe XML parsing, and session binding. Use properly configured Spring Security SAML2 SP/OpenSAML.

## 16. Key Takeaways and Primary Sources

- **SubjectConfirmation** answers: “Under what conditions may the subject be confirmed when this Assertion is presented?”
- **Recipient** answers: “Which **SP's ACS** is this bearer Assertion permitted to reach?”
- **InResponseTo** answers: “Which **SP-issued AuthnRequest** does this Response/confirmation belong to?”
- In **SP-initiated Web Browser SSO**, `Response.InResponseTo` and bearer `SubjectConfirmationData.InResponseTo` must bind to the exact saved **AuthnRequest.ID**; in **unsolicited** flows, no original request exists and a dedicated policy is required.
- **NotOnOrAfter** limits bearer confirmation lifetime; signature, issuer, `Destination`, `AudienceRestriction`, `Conditions`, anti-replay, and session integrity still must be checked.
- In Spring Security, keep **Saml2AuthenticationRequestRepository**/session/cookies consistent, configure **RelyingPartyRegistration**/public ACS accurately, and let the **OpenSAML provider** perform validation. Never troubleshoot by disabling security checks.

**References:**

1. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf), section **4.1 Web Browser SSO Profile**, especially **4.1.4.3 Response Processing Rules** and **4.1.5 Unsolicited Responses**.
2. [OASIS SAML 2.0 Approved Errata](https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0.html): clarifies evaluating multiple bearer `SubjectConfirmation` elements and multiple Assertions.
3. [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP/RP, filters, and verification pipeline.
4. [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): `Saml2AuthenticationRequestRepository`, session, and correlation protection.
5. [Spring Security – Authenticating Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): response/assertion validators, correlation, and error handling. Check **documentation matching your dependency version** before customizing APIs.

**Final principle:** an IdP authenticating a person does not mean **every SAML Assertion** mentioning that person should be accepted. An SP permits login only when the Assertion was issued **for the right SP, to the right ACS, in the right transaction, at the right time, and under the right trust relationship**.

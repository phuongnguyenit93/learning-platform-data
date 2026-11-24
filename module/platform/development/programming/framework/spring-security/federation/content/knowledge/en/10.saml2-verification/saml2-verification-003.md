# Distinguishing Response Signature Verification from Verifying the Assertion Used in SAML 2.0

> **Topic:** Spring Security – federation · **Track:** SAML2 Verification. This lesson focuses on an easily misunderstood question: **if the SP has verified the signature on `samlp:Response`, does that guarantee the `saml:Assertion` the application uses to log the user in is also protected?** The answer depends on **which exact node the signature covers**, **which Assertion is actually selected for principal/attributes**, **key trust**, and **the remaining SAML checks**.

## 1. Objectives and Key Conclusions

After this lesson, you will be able to:

1. Pinpoint the placement and protection scope of an XML signature on **Response** versus on **Assertion**.
2. Distinguish **successful signature verification** from **verifying the exact Assertion used to issue a session and permissions**.
3. Understand the two valid models in Web Browser SSO HTTP-POST: **signed Response** or **every used Assertion signed** per profile/policy.
4. Identify **XML Signature Wrapping**, duplicate IDs, wrong element selection, and mistakenly trusting data outside the signed region.
5. Understand the Spring Security SAML2/OpenSAML pipeline and points of caution when customizing converters/validators.
6. Design test cases for Response-only signature, Assertion-only signature, both-signed, multi-assertion, encrypted assertion, and malicious messages.
7. Avoid confusing signature/metadata/issuer checks with separate validations like Audience, Recipient, Destination, Expiry, InResponseTo, and Replay.

**Brief distinction:**

- **Response signature**: protects the **signed Response XML** and inner content that the signature reference actually covers, including an Assertion nested inside the signed Response.
- **Assertion signature**: protects **one specific Assertion XML** that the signature reference points to; does not automatically sign the outer Response.
- **Used Assertion validation**: the application may only use principal/attributes from an **Assertion that has been authenticated, lies within a trusted signed scope, and passes all mandatory SAML conditions**.
- **Signature validation ≠ SAML validation ≠ authorization**. A valid signature does not turn an Assertion with the wrong audience, expiration, or wrong request into valid login proof.

## 2. Components Present in SAML Web Browser SSO

A `SAMLResponse` message from the Identity Provider (IdP) is typically sent by the browser via HTTP POST to the Service Provider's (SP) Assertion Consumer Service (ACS). Note the XML namespace prefixes: `samlp` belongs to SAML protocol; `saml` belongs to SAML assertion; `ds` belongs to XML Digital Signature (XMLDSig).

| Component | Role | Verification question |
|---|---|---|
| `samlp:Response` | Protocol envelope, ID, Issuer, Destination, InResponseTo, Status, Assertions | Is the Response from the right IdP, ACS, pending request, and profile? |
| `saml:Assertion` | Subject, NameID, authentication statement, Conditions, attributes | Which Assertion is actually used? Is it valid and protected? |
| `ds:Signature` under Response | XML signature for Response scope | Does Reference point to the right Response and cover the used content? |
| `ds:Signature` under Assertion | XML signature for one Assertion | Does Reference point to that exact Assertion? |
| `ds:SignedInfo/Reference` | Binds hash/digest to the signed object | Are URI, transforms, canonicalization, and digest valid? |
| `RelyingPartyRegistration` | SP ↔ IdP trust and endpoint config in Spring Security | Does the verification certificate belong to the right IdP? |
| `Saml2AuthenticatedPrincipal` | Principal created after authentication | From which Assertion and after which checks were NameID/attributes taken? |

Do not treat `<ds:Signature>` as merely a tag somewhere in the XML. XMLDSig must verify **the exact referenced element** along with transforms, digest, SignatureValue, and key/trust. Furthermore, the actual user is determined from the Assertion used by the converter, **not an arbitrary `NameID` string anywhere in the XML**.

### Basic Flow Example

~~~text
User + Browser
      |
      | POST SAMLResponse (base64 XML)
      v
Spring Security /login/saml2/sso/{registrationId}
      |
      | 1. Safely decode and parse XML
      | 2. Resolve the right RelyingPartyRegistration / IdP
      | 3. Verify Response signature if present
      | 4. Decrypt EncryptedAssertion if present
      | 5. Verify Assertion signatures, trust, policy
      | 6. Check Issuer, Destination, Audience,
      |    SubjectConfirmation, validity period, request state
      | 7. Select/convert verified Assertion into
      |    principal + attributes + authorities
      v
Authentication / SecurityContext / Session
~~~

The diagram depicts **logical requirements**. The concrete execution order may change between Spring Security 6 and 7, particularly response validation order relative to assertion validation. What is mandatory is **never creating a session or granting permissions from unverified data**.

## 3. What Does a Signature on Response Protect?

### 3.1. Response-Signed, Assertion-Unsigned Model

XML example **abbreviated for structural reading**, omitting several required elements, real signature, and digest values, **not a runnable SAMLResponse**:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="_response_01"
    Destination="https://sp.example.org/login/saml2/sso/corporate">
  <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
  <ds:Signature>
    <ds:SignedInfo>
      <ds:Reference URI="#_response_01">
        <!-- Transforms, DigestMethod, DigestValue... -->
      </ds:Reference>
    </ds:SignedInfo>
    <!-- SignatureValue and key info per profile -->
  </ds:Signature>
  <samlp:Status>...</samlp:Status>
  <saml:Assertion ID="_assertion_01">
    <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
    <saml:Subject>
      <saml:NameID>alice</saml:NameID>
    </saml:Subject>
    <saml:Conditions>...</saml:Conditions>
    <saml:AuthnStatement>...</saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

In the example, `ds:Signature` is a child of Response and `ds:Reference URI="#_response_01"` points to Response. When the signature validator:

- Resolves the ID accurately and verifies the digest of the **exact Response element** after transforms.
- Verifies `SignatureValue` with the public verification key belonging to the **IdP trusted by the SP**.
- Confirms the Response used by business logic **is the exact Response that was signed**.
- Ensures the used Assertion **resides inside the signed Response scope**, not a node injected, swapped, or mistakenly picked from elsewhere.

...then a valid Response signature **can** protect an assertion nested inside it, even if that assertion does not contain its own `ds:Signature`. For Web Browser SSO HTTP-POST, this is a form of protection compliant with the standard and with Spring Security defaults when all other conditions are valid.

**Point to state accurately:** A Response signature **does not merely sign a list of Response attributes**. It can protect the entire child XML structure via canonicalization/digest. Yet you must verify the actual **Reference and transforms**; seeing a signature placed in Response is not enough to guarantee every node processed by the application is protected.

### 3.2. What a Response Signature Does Not Do by Itself

- **Does not encrypt the Assertion:** the browser can read NameID and Attributes if the Assertion is plaintext.
- **Does not guarantee the right SP:** you must still check `AudienceRestriction` and recipient.
- **Does not guarantee freshness:** you must still check `NotBefore/NotOnOrAfter`, replay, and subject confirmation expiration.
- **Does not guarantee the right session:** in SP-initiated SSO you must check `InResponseTo` and matching pending AuthnRequest; IdP-initiated has its own policy.
- **Does not guarantee the user has privileges:** `role=admin` is only an attribute/claim that must be mapped per policy.
- **Does not replace IdP trust:** a response signed with the private key of a party not in the trust registration must not be accepted.
- **Does not allow using an Assertion outside the signed subtree:** this is the core flaw leading to XML Signature Wrapping.

**Example:** An IdP signs a Response containing an assertion for `alice` with Audience `https://another-sp.example.org`. The signature is still cryptographically valid, yet the current SP must **reject** it because the Audience is not intended for it.

## 4. What Does a Signature on Assertion Protect?

### 4.1. Assertion-Signed, Response-Unsigned Model

Abbreviated XML example:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="_response_02"
    Destination="https://sp.example.org/login/saml2/sso/corporate">
  <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
  <samlp:Status>...</samlp:Status>
  <saml:Assertion ID="_assertion_02">
    <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
    <ds:Signature>
      <ds:SignedInfo>
        <ds:Reference URI="#_assertion_02">
          <!-- Transforms and digest... -->
        </ds:Reference>
      </ds:SignedInfo>
      <!-- SignatureValue... -->
    </ds:Signature>
    <saml:Subject>
      <saml:NameID>alice</saml:NameID>
    </saml:Subject>
    <saml:Conditions>...</saml:Conditions>
    <saml:AuthnStatement>...</saml:AuthnStatement>
    <saml:AttributeStatement>...</saml:AttributeStatement>
  </saml:Assertion>
</samlp:Response>
~~~

The Assertion signature is attached to `_assertion_02`, protecting only **that Assertion per XMLDSig transforms**. It **does not automatically sign** fields outside the Assertion on the Response, such as `Response.Destination` or `Response.InResponseTo`. This is why the SP remains responsible for validating the Response profile, ACS, and request context, even when the Assertion signature is valid.

Must verify:

1. Reference `URI="#_assertion_02"` resolves to **the exact Assertion the SP will use**.
2. Signature/digest are valid and signed with the key of a **trusted configured IdP**.
3. The Assertion actually belongs to the Response received at a valid ACS; no other unsigned Assertion was selected by the parser/converter.
4. `Issuer, Subject, SubjectConfirmationData, AudienceRestriction, Conditions, AuthnStatement` are valid.
5. When multiple Assertions exist, **never use Assertion A's signature to trust Assertion B**.

### 4.2. Why Doesn't an Assertion Signature Cover the Response?

Suppose a response has:

~~~text
Response (unsigned)
  ├── Destination / InResponseTo / Status
  └── Assertion ID=A1 (signed)
       ├── Subject NameID=alice
       ├── Conditions Audience=sp-1
       └── Attribute groups=report-readers
~~~

The signature on Assertion guarantees Assertion A1's contents cannot be altered without failing verification, yet it **does not directly protect** the outer Response fields. The SP must use the **protocol validator** to determine whether the Response was sent to the right ACS, correlates to the right request and issuer, and has an appropriate status. Do not skip Response validation just because ID/Subject/Attributes have their own signature.

In systems using multiple Assertions, every Assertion actually used for authentication or attribute extraction must be **protected under a trusted policy**. It is insufficient for one Assertion to be validly signed if the converter pulls roles from another unprotected Assertion.

## 5. Four Mandatory Questions About a Signature

A complete signature validation step must answer **four questions**:

1. **Who signed?** The signature must be checked with the verification credential of an **IdP permitted by the SP**, obtained from trusted metadata/trust configuration. Do not pull an arbitrary key from `ds:KeyInfo` in the payload and treat it as trusted.
2. **What was signed?** `ds:Reference URI`, transforms, canonicalization, and digest determine **the exact XML node/scope actually signed**. Reference must not point to a different Assertion than the one used.
3. **Is it intact?** Are the digest and `SignatureValue` valid under an accepted algorithm? Any modification inside the signed scope must cause verification to fail.
4. **Which data is used?** After verification, do the parser and business converter use **the exact node protected by the signature**? If a new node or one outside the signed content is picked, the signature guarantee becomes meaningless.

Outcome distinction table:

| Finding | Assessment | Correct action |
|---|---|---|
| `ds:Signature` present but verification fails | Untrusted | Reject |
| Verification succeeds using self-declared cert from payload untrusted by SP | Missing trust | Reject |
| Verification succeeds but Reference points to a **different** Response | Does not protect the node needed | Reject |
| Verification succeeds on Assertion A, but converter reads NameID from unprotected Assertion B | Used Assertion is untrusted | Reject |
| Verification succeeds on used Response, Assertion is a child inside signed subtree | Provides integrity protection for that Assertion | Continue checking SAML conditions |
| Verification succeeds on used Assertion, Response unsigned | Assertion is protected | Continue checking Response conditions and correlation |
| Signature valid, but Assertion expired or wrong Audience | Fails SAML policy | Reject |
| Signature valid, conditions valid, but user lacks permission | Authentication may be valid; authorization fails | Return 403/deny restricted resource |

**Summary:** A valid signature is a necessary condition for the signature-protected XML portion, yet **insufficient** to create Authentication for a user.

## 6. SAML XML Signature Wrapping: Valid Signature, Wrong Assertion Used

### 6.1. Idea Behind the Attack Class

**XML Signature Wrapping (XSW)** occurs when a validly signed XML portion still exists, yet an attacker rearranges/injects elements so that:

- The XML signature library checks **one signed Response/Assertion**.
- Application logic reads **a different Response/Assertion** (unsigned or outside signed content).
- The application unwittingly trusts NameID/roles from a node not protected by the signature.

This is a **mismatch binding the verification result to the consumed data**. There is no need to break the signature algorithm or know the IdP's private key.

A conceptual example:

~~~text
Untrusted XML envelope
  ├── Original Assertion ID=A1, valid signature for A1
  │    NameID=alice
  └── Injected Assertion ID=A2, unsigned or misplaced
       NameID=admin

Signature library:  "Assertion A1 signature is valid"
Business converter: "Read NameID from Assertion A2"
Wrong outcome:      "Log in as admin"
~~~

This is a **threat illustration**, not a specific valid SAML document. Schema validation, signature reference enforcement, and proper node selection logic must ensure such forged structures **are rejected**.

### 6.2. Why Is Selecting via `getElementsByTagName` Dangerous?

DOM snippet illustrating an **anti-pattern**; strictly never use as a SAML validator:

~~~java
// WRONG: arbitrarily picking an element by name without ensuring it is signed.
var assertions = document.getElementsByTagName("saml:Assertion");
var selected = assertions.item(assertions.getLength() - 1);
// Must not take NameID or roles from selected to create Authentication.
~~~

The mistakes here include:

- Matching elements by literal prefix, whereas in XML prefixes can change while the namespace stays identical.
- With multiple Assertions in unusual positions or duplicate IDs, the signature library and application may pick different ones.
- Picking an element by position instead of **schema + signature coverage + profile**.
- Failing to prove the selected node belongs to a valid signed Response or is the exact signed Assertion itself.

**Countermeasures:**

1. Use a **vetted SAML parser/schema and OpenSAML validator** instead of cobbling together XPath/regex to decide identity.
2. Configure the XML parser safely: disallow arbitrary DTDs/external entities, enforce size/resource limits and schema structure.
3. Reject **duplicate XML IDs**, anomalous References, multiple roots/out-of-schema Assertions, and disallowed transforms/algorithms.
4. Check the exact **resolved signed element** by node identity/valid ID, not merely comparing text or display names.
5. Extract principal and attributes **from the exact Assertion that passed signature/trust/conditions**.
6. Do not replace default validations with a converter searching for `NameID`/`Attribute` tags across the entire document DOM.

OWASP specifically highlights Signature Wrapping and requires verifying that the **exact Assertion used for authentication** is covered by a verified signature.

## 7. Multiple Assertions in a Single Response

A `samlp:Response` can contain multiple assertions per compliant profiles/specs, or `EncryptedAssertion` elements that must be decrypted first. With Spring Security SAML2, **never infer that having any one signed Assertion is enough**.

### 7.1. Default Policy Described by Spring Security

Spring Security SAML 2.0 Login Overview documentation describes these conditions:

- If the Response has a signature that is **invalid**, authentication fails.
- If an Assertion has a signature that is **invalid**, authentication fails.
- If **neither the Response nor the Assertions have a signature**, authentication fails.
- Under the documented default policy, **either the Response must have a valid signature or all Assertions must have valid signatures**.
- The provider checks each Assertion before authenticating; principal/attributes are by default created from the **first Assertion** after processing.

Thus there are three distinct layers:

| Layer | Indicator | Control |
|---|---|---|
| Cryptographic | Signed Response / Signed Assertions | Which nodes were signed, and is the signing key trusted |
| SAML semantic | Issuer, Destination, Audience, Conditions, SubjectConfirmation | Are the Assertion and Response permitted for use |
| Principal conversion | First Assertion / custom converter | Which data is used to construct NameID, Attributes, and GrantedAuthority |

If you customize the converter to pick the second Assertion or merge attributes from multiple Assertions, you must **retain and apply full validation to all used Assertions**. Never alter the pipeline so that only Assertion A is validated while an unprotected Assertion B is used.

### 7.2. Multi-Assertion Matrix

Suppose Response contains A1 and A2:

| Response | A1 | A2 | Outcome under the documented default policy |
|---|---|---|---|
| Validly signed | Unsigned | Unsigned | Can pass signature requirement if both A1 and A2 lie inside the signed Response, then check all SAML conditions |
| Unsigned | Validly signed | Validly signed | Can pass signature requirement, then check all SAML conditions |
| Unsigned | Validly signed | Unsigned | **Reject**: not all Assertions are signed |
| Validly signed | Validly signed | Unsigned | Can pass signature requirement; every signature present must be valid and every Assertion must pass validation |
| Validly signed | Signed **invalid** | Unsigned | **Reject**: cannot ignore A1's broken signature |
| Unsigned | Unsigned | Validly signed | **Reject**: one signed Assertion does not protect A1 |
| Validly signed | Unsigned, wrong Audience | Unsigned | **Reject** due to semantic validation, even though signed Response protects integrity |
| Validly signed | Valid | Valid | Can succeed; default converter uses principal/attributes from **A1** |

"**Can**" means **considering signature requirements only**; it still must pass full issuer, audience, recipient, timing, subject, replay, request correlation, and IdP configuration checks. If a profile/partner requires an **individual Assertion signature**, a signed Response may not satisfy that contract.

### 7.3. Which Assertion Is "Used" and Role-Mapping Risks?

In Spring Security's documented defaults, after validating assertions the provider takes **`NameID` and `AttributeStatement` from the first assertion** to build `Saml2AuthenticatedPrincipal`. This is an implementation/version detail, **not a universal rule that every SAML SP picks the first assertion**.

When adding a custom `ResponseAuthenticationConverter` or merging group claims yourself, explicitly define:

- Which Assertion supplies the **principal ID**?
- Which Assertion supplies the **attributes**?
- If merging multiple assertions, do all share the same issuer/subject/tenant and undergo the same validation policy?
- Is there abnormal behavior when assertions are missing or reordered?
- Does any assertion with a bad signature, expiration, or wrong audience fail the entire authentication?
- Is mapping `role=ADMIN` based on claims belonging to a signed Assertion within an accepted trust realm?

**Critical mistake:** validating only `Response.getAssertions().get(0)` while the mapper uses `get(1)` for roles, or running XPath across the whole XML after the validator checked another node's signature.

## 8. Two Scenarios Involving Signatures and Encrypted Assertions

### 8.1. Signed Response Covering EncryptedAssertion

~~~text
Signed(Response ID=R1)
  └── EncryptedAssertion [ciphertext sent to SP]
         └── (after decryption) Assertion without its own signature
~~~

When an XML Signature properly protects a **Response containing ciphertext**, the SP can verify the outer signature first, then decrypt using its private decryption key. The Response signature protection remains meaningful for the encrypted assertion it covers. You must still validate issuer/audience/subject/conditions of the plaintext.

**Content confidentiality:** encryption prevents the browser from reading NameID/attributes, yet **does not prove IdP issuance on its own**. If the Response is unsigned and the inner Assertion is also unsigned, succeeding at decryption alone is insufficient to authenticate.

### 8.2. Assertion Signed Then Encrypted

~~~text
Response (unsigned or signed depending on config)
  └── EncryptedAssertion
        └── Decrypt...
               └── Signed(Assertion ID=A1)
                      ├── NameID
                      ├── Conditions
                      └── Attributes
~~~

The SP cannot verify the signature of an encrypted Assertion until after **decryption**. After decrypting, it must verify the signature on the exact Assertion being used and then check SAML semantics. If the outer Response is signed, verify the Response signature per its structure/coverage before processing.

Spring Security/OpenSAML separates the decrypters:

- **Response elements decrypter:** decrypts `EncryptedAssertion` at the Response level.
- **Assertion elements decrypter:** decrypts `EncryptedID`/`EncryptedAttribute` inside an Assertion.

The reason is that **decrypting content inside a signed Assertion before verifying the Assertion signature** can alter the signed XML, causing signature verification failure. Follow the provider's pipeline; do not manually reorder decryption/signature validation.

### 8.3. Comparison Table of the Three Goals

| Procedure | Question answered | What it cannot replace |
|---|---|---|
| Verify Response XMLDSig | Is the signed Response from the right source, intact, and covering the right node? | Assertion condition checks and authorization |
| Verify Assertion XMLDSig | Is the specific Assertion signed by the IdP intact? | Outer Response/request validation |
| Decrypt EncryptedAssertion | Does the SP possess the private key to read the content? | Signature trust/issuer/audience, anti-replay |
| Validate Assertion | Are Subject, Audience, Recipient, time, and conditions valid? | Signature/crypto integrity guarantees |
| Convert to Authentication | Select NameID, Attributes, and authorities | Prior validations |
| Application authorization | What is the principal permitted to do? | Identity authentication at the IdP |

## 9. Spring Security SAML2: Practical Processing

### 9.1. Key Components to Know

A Servlet Spring Security application acting as a SAML Service Provider typically has:

- `HttpSecurity.saml2Login()`: enables the SAML2 login flow.
- `Saml2WebSsoAuthenticationFilter`: receives `SAMLResponse` at the ACS.
- `Saml2AuthenticationTokenConverter`: converts the HTTP request into `Saml2AuthenticationToken` and resolves the registration.
- `RelyingPartyRegistrationRepository`: registers SP, IdP, issuer, ACS, verification credentials, and decryption credentials.
- `OpenSaml5AuthenticationProvider` in the documentation branch using OpenSAML 5: verifies signatures, decrypts, validates Response/Assertions, and builds Authentication.
- `Saml2AuthenticatedPrincipal` / `Saml2Authentication`: principal and authorities placed into SecurityContext upon success.

Spring Security documentation describes the pipeline (abbreviated):

1. Parse Response from the HTTP binding.
2. If a Response signature is present, **verify the signature**; fail if invalid.
3. Decrypt `EncryptedAssertion`; fail on error.
4. Validate Response conditions, such as issuer/destination and request correlation per validator.
5. Verify **each Assertion's** signature; if present and invalid, fail. If there is no Response signature and not all Assertions are signed, fail.
6. Decrypt elements inside Assertions where applicable.
7. Validate assertion expiration, subject, audience, confirmations, and conditions.
8. Select/convert principal and attributes from accepted assertions, then create Authentication.

**Version note:** Spring Security 6.x and 7.x may differ in the **order** of response validation and assertion validation; Spring Security 7 migration docs note moving response validation after assertion validation. The invariant rule is that **the signature and semantics of the exact data used to build the principal must be verified before login**. Check the exact docs of your running version when extending the provider.

### 9.2. Where Does the IdP Verification Certificate Come From?

The SP must hold the IdP's trusted verification certificate in `RelyingPartyRegistration`, which can be loaded from trusted IdP metadata:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: "https://idp.example.org/metadata"
~~~

This is a **configuration example**; the URL must point to real IdP metadata with a verified source; the IdP must also register the SP entityID/ACS. If configured manually, valid entityID, SSO URL/binding, and `verification.credentials` are required. **Do not** treat a cert embedded in a browser-submitted SAML Response as trusted simply because the XML contains `KeyInfo`.

Regarding signing/encryption:

- **IdP signing private key** is held by the IdP; the SP holds the **IdP verification public cert** to verify Response/Assertion.
- **SP decryption private key** is held by the SP; the IdP holds the **SP encryption public cert** to encrypt Assertions for the SP.
- **SP signing private key** (when signing AuthnRequest/LogoutRequest) is held by the SP; the IdP holds the corresponding public cert to verify requests.

These key pairs can differ. Do not automatically reuse an encryption public cert as verification trust, or accept a different IdP solely because it shares an email domain.

### 9.3. Minimal Java 17+ Spring Boot Servlet Application

This is a **complete application-level Spring Boot class**, for use when the project already has matching versions of Spring MVC, Spring Security, and the SAML2 SP dependency. It cannot run with plain `javac` because it requires the Spring classpath and a real IdP.

File `src/main/java/com/example/sso/SamlVerificationApplication.java`:

~~~java
package com.example.sso;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SamlVerificationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlVerificationApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SAML verification demo";
    }

    @GetMapping("/private")
    String privateResource() {
        return "Authenticated";
    }
}
~~~

To run a Maven project with wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Once Spring Boot starts and valid IdP metadata/registration is configured, `GET /` returns HTTP body `SAML verification demo`. `GET /private` requires login; it only returns `Authenticated` after the SAML Response and assertions are verified. Exact stdout and real redirect URLs cannot be fixed without a real IdP.

**Required dependencies:** `spring-boot-starter-web`, `spring-boot-starter-security`, and `spring-security-saml2-service-provider`; versions come from the appropriate Boot BOM/branch. For OpenSAML/Maven repositories, follow the corresponding Spring Security dependency guide. This SAML2 login flow is for **Servlet**, not WebFlux `ServerHttpSecurity`.

### 9.4. What to Do When Customizing Converter/Validator?

Spring Security allows customizing the provider, response validator, assertion validator, and response authentication converter. **Never replace them with a superficial validator that checks a signature in just one place**.

When customizing:

- Prefer **extending the default validator** to add rules, avoiding full replacement that drops issuer/destination/audience/subject confirmation.
- Preserve signature validation along with IdP trust and signed-node coverage of the consumed data.
- If a custom converter picks a different Assertion or merges attributes, test multi-assertion/unsigned assertion cases and authorization mapping.
- If a custom decrypter handles EncryptedAssertion, still verify the signature and plaintext conditions in the proper order; never treat decryption as authentication.
- With multiple IdP registrations, never pick an arbitrary trusted cert that matches a signature while skipping issuer/entityID/ACS.
- If adjusting allowed clock skew, keep the window tight with a proper replay policy; do not keep widening it just to avoid errors.
- Never use `Response.getAssertions().stream().findFirst()` as security evidence **before** verification.
- Never disable `SignatureValidator` or drop `AudienceRestriction` so that a sample IdP response "logs in".

**Potential design bug:** Spring Security includes validators for required profile fields by default, yet a poorly written **custom provider/converter** can break the signature → Assertion → Authentication link. Always test with multi-Assertion Responses and invalid signature cases.

## 10. Matrix of Signature Verification and Actually Used Data

This table is for reasoning **in an SP using Web Browser SSO HTTP-POST**. "Passing signature" does not mean login succeeded.

| Case | Response signature | Used Assertion signature | Conclusion |
|---|---|---|---|
| A | Valid, covers used Assertion | Absent | **Can pass signature requirement**; proceed to validate Assertion conditions |
| B | Absent | Valid on the exact used Assertion | **Can pass signature requirement** if all Assertions must have valid signatures |
| C | Valid, covers used Assertion | Valid | Can pass signature requirement; verify both present signatures |
| D | Absent | Absent | **Reject**: no signature protection |
| E | Present but **invalid** | Valid | **Reject**: do not ignore broken Response signature |
| F | Valid | Present but **invalid** | **Reject** per documented Spring Security pipeline |
| G | Valid for another Response / wrong Reference | Absent | **Reject**: signature does not protect used Response/Assertion |
| H | Absent | Valid for Assertion A, but converter uses unsigned Assertion B | **Reject**: used Assertion is unprotected |
| I | Valid for Response covering A1+A2 | Both A1 and A2 unsigned | Can pass signature requirement, but both need semantic validation |
| J | Absent | A1 signed, A2 unsigned | **Reject** per documented default policy |
| K | Valid for Response | Used Assertion expired/wrong Audience | **Reject**: semantic failure |
| L | Valid for Response containing ciphertext | Decrypted Assertion, unsigned | Can pass signature requirement if signed ciphertext matches and policy allows |
| M | Absent | Assertion signed **inside ciphertext** | Can pass signature requirement after decryption and verify, still must check all conditions |
| N | Absent | Assertion decryptable but unsigned | **Reject**: encryption is not authentication |
| O | Valid with cert of **untrusted** IdP | Absent | **Reject**: missing trust |
| P | Valid and right node | Valid, but role not mapped | Authentication may succeed, but **grant no permissions** outside policy |

Any federation setup may require stricter guarantees than the default policy, such as **mandating an Assertion signature** even when the Response is signed. In that case, Response-only signed must be rejected **per partner contract**, not adjusted arbitrarily.

## 11. Checking Conditions, Subject, and Request After Signature

Once you know which data is signature-protected and that the signer is trusted, the SP must also check:

| Check | Source | Example failure to reject |
|---|---|---|
| **Issuer** | Response/Assertion | Assertion from an IdP outside the registered tenant |
| **AudienceRestriction** | `saml:Conditions` | Assertion issued for SP B used to log into SP A |
| **Destination** | Response | Target URL does not match registration ACS |
| **Recipient** | `SubjectConfirmationData` | Bearer assertion sent to a different ACS |
| **InResponseTo** | Response + bearer subject confirmation, pending AuthnRequest | Response belongs to a different request/session |
| **NotBefore** | Conditions | Assertion is not yet valid |
| **NotOnOrAfter** | Conditions + SubjectConfirmationData | Assertion has expired |
| **AuthnStatement** | Assertion | Lacks authentication method/context matching policy |
| **Status** | Response | IdP returned an error yet app still creates a session |
| **Replay** | Assertion/Response IDs, policy | A consumed bearer assertion is re-submitted |
| **Principal mapping** | Subject/NameID | ID from another issuer mistakenly linked to an account |
| **Authorization** | Role/group mapping and business rules | Authenticated user is not allowed to modify data |

**Explanation:** When a Response is signed, an assertion inside the signed subtree has integrity protection. That **does not mean** `AudienceRestriction` or validity times are automatically right. They can be data signed by a **real IdP** yet meant for another SP, expired, or mismatched to the request; the SP must reject it.

### Distinguishing Signing and Encryption

- **Response/Assertion signature**: integrity and authenticated origin for the signed XML.
- **EncryptedAssertion**: confidentiality for the assertion, usually encrypted by the IdP using the SP's public encryption cert.
- **TLS/HTTPS**: protects transport between browser–SP/IdP; the browser remains a payload carrier, not a trusted issuer.

An `EncryptedAssertion` that is unsigned and not inside a signed Response **cannot** become a trusted assertion merely because the SP can decrypt it. Conversely, a signed Response with a plaintext Assertion can be read; a signature **does not hide** NameID/email/groups.

## 12. Standalone Java 17 Exercise: Confirming Protected Scope

This exercise expresses **business policy after receiving signature verification results from a dedicated security library**. It **does not perform XML Signature verification, does not parse SAML, and does not replace OpenSAML**. The goal is to practice thinking: "the signature is valid, but is the Assertion actually used within the trusted scope?".

File `SignedAssertionPolicyDemo.java`:

~~~java
public class SignedAssertionPolicyDemo {

    static String decide(
            boolean responseSignaturePresent,
            boolean responseSignatureValid,
            boolean responseCoversUsedAssertion,
            boolean assertionSignaturePresent,
            boolean assertionSignatureValid,
            boolean sameAssertionNode,
            boolean assertionConditionsValid) {

        if (responseSignaturePresent && !responseSignatureValid) {
            return "REJECT: bad response signature";
        }
        if (assertionSignaturePresent && !assertionSignatureValid) {
            return "REJECT: bad assertion signature";
        }

        boolean protectedByResponse =
                responseSignaturePresent
                && responseSignatureValid
                && responseCoversUsedAssertion;

        boolean protectedByAssertion =
                assertionSignaturePresent
                && assertionSignatureValid
                && sameAssertionNode;

        if (!protectedByResponse && !protectedByAssertion) {
            return "REJECT: used assertion unsigned";
        }
        if (!assertionConditionsValid) {
            return "REJECT: assertion conditions";
        }
        return "ACCEPT: protected and valid";
    }

    public static void main(String[] args) {
        System.out.println(decide(
                true, true, true, false, false, false, true));
        System.out.println(decide(
                false, false, false, true, true, true, true));
        System.out.println(decide(
                true, true, false, false, false, false, true));
        System.out.println(decide(
                false, false, false, true, true, false, true));
        System.out.println(decide(
                true, true, true, false, false, false, false));
        System.out.println(decide(
                true, false, true, true, true, true, true));
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac SignedAssertionPolicyDemo.java
java SignedAssertionPolicyDemo
~~~

**Exact stdout:**

~~~text
ACCEPT: protected and valid
ACCEPT: protected and valid
REJECT: used assertion unsigned
REJECT: used assertion unsigned
REJECT: assertion conditions
REJECT: bad response signature
~~~

Explanation:

1. Valid Response signature covering the used Assertion; Assertion has no separate signature → signature condition passes.
2. Response unsigned, Assertion validly signed and is the exact node used → signature condition passes.
3. Valid Response signature yet **does not cover** the used Assertion → rejected.
4. Valid Assertion signature yet belongs to **another node** → used Assertion remains unprotected.
5. Valid signature/coverage yet invalid conditions → rejected.
6. Response signature present yet invalid → rejected even though Assertion signature is present and valid.

**Exercise limitation:** `decide` assumes booleans from a validator **that already checked cryptography + trust**; it does not check multi-assertion, duplicate IDs, XML schema, issuer, response destination, request correlation, replay, or permission groups. A production SP must use OpenSAML/Spring Security for those checks rather than turning a boolean sample into SAML XML middleware.

## 13. Testing SAML with Real Signatures and Malicious Responses

### 13.1. Positive Tests

1. **Response-only signed:** valid Response signature covering an unsigned Assertion; SP accepts per policy once conditions pass.
2. **Assertion-only signed:** Response unsigned, used Assertion validly signed; SP accepts when all required assertions are signed and conditions pass.
3. **Both-signed:** both Response and Assertion have valid signatures; SP processes normally.
4. **Multi-assertion, Response-signed:** signed Response covers A1/A2; provider checks conditions on each Assertion and converter picks the principal per policy.
5. **Multi-assertion, Assertion-signed:** all Assertions have valid signatures and valid conditions.
6. **Encrypted Assertion in signed Response:** provider verifies the signature covering ciphertext, decrypts, and checks conditions.
7. **Signed Assertion then encrypted:** decrypt to obtain Assertion, verify that exact Assertion's signature.
8. **Key rotation:** IdP signs with new cert already in SP's trusted credentials; certs outside allowlist are not accepted.

### 13.2. Negative Tests

| Test case | Expected result |
|---|---|
| Alter one character of NameID/role in signed Response | Signature/digest verification fails |
| Alter one character inside signed Assertion | Signature verification fails |
| Signature on Response with wrong Reference ID or outside used node | Reject |
| XML with duplicate ID, wrapped structure, or Assertion outside signed subtree | Reject |
| Valid signature for A1 yet app tries to take unsigned A2 NameID | Reject |
| Response unsigned, A1 validly signed, A2 unsigned | Reject per default policy |
| Response signature invalid while Assertion signature valid | Reject broken signature |
| Response signature valid while Assertion signature invalid | Reject broken signature |
| Response/Assertion unsigned, only EncryptedAssertion present | Do not accept merely because decryption succeeds |
| XML Signature using cert from KeyInfo not registered in trust | Reject |
| Valid signature yet Audience differs from SP entityID | Reject |
| Valid signature yet Recipient/Destination differs from ACS | Reject |
| Valid signature yet InResponseTo does not match pending request | Reject |
| Valid signature yet expired/invalid NotBefore | Reject |
| Valid signature yet replaying a previously used assertion ID | Reject |
| Valid signature, user lacks business role | Deny access to restricted resources |
| Custom converter selects an unverified Assertion | Test fails and converter/pipeline must be fixed |

### 13.3. How to Build Safe and Meaningful Tests

Use a test IdP, OpenSAML fixtures, or a SAML test harness that issues **Responses signed with test keys**; do not assume editing XML leaves a signature valid. For negative tests of a **business converter picking the wrong node**, you need a fixture with a **valid signature for one node** and untrusted data in another node; the validator must reject due to schema/coverage, not accidentally because it "cannot parse".

When testing multi-assertion, also check:
- Which Assertion the authentication principal NameID is actually read from.
- Whether group/role attributes are accidentally merged from another Assertion.
- Whether all assertions undergo proper signature/trust/conditions verification.
- Whether even a single invalid signature triggers failure as required by policy.
- Whether Spring Security 6.x and 7.x behave differently with custom converters/validators.

Do not log full real `SAMLResponse`, raw assertions containing PII, private keys, cookies, or session tokens to public systems. Log sanitized events and appropriate fingerprints/correlation IDs.

## 14. Common Incidents and Troubleshooting

| Symptom | Possible cause | How to check |
|---|---|---|
| `Signature validation failed` | Wrong IdP cert, key rollover, XML mutation, invalid digest/signer | Compare IdP metadata, verification credentials, ID/Reference, signature algorithm |
| Response signature present yet SP reports missing Assertion protection | Response did not sign right node/Reference, custom converter uses Assertion outside signed subtree, or partner requires Assertion signature | Verify signed node and actual used Assertion, IdP contract |
| Assertion signature valid yet login rejected | Wrong Response fields, wrong request correlation/recipient/audience/expiry | Separate signature test from semantic validation |
| XML has two Assertions, one signed, one not | Default policy requires Response signed or all Assertions signed | Check both response signature and every assertion |
| Login produces unexpected user | Converter picked wrong Assertion/NameID, email-based account linking | Trace exact validated assertion the principal came from |
| Unexpected role privilege escalation | Attribute from unverified Assertion or mapper merged wrong source | Check claims mapping, issuer, tenant, converter |
| Signature Wrapping or duplicate ID | XML parser + signature verifier pick different node than business code | Reject duplicate ID/invalid schema; use hardened OpenSAML |
| EncryptedAssertion decrypts yet signature fails | SP decryption key differs from verification trust; wrong signing cert | Verify key roles, trust chain, and decryption order |
| Signed Response valid, Assertion expired | Valid signature yet invalid semantic conditions | Check `NotOnOrAfter`, NTP, SubjectConfirmation |
| SSO through proxy fails Destination | Public host/scheme differs from internal ACS | Fix trusted forwarded headers, entityID/ACS |
| Different app versions behave differently | Different Spring Security 6/7 or custom provider/validator | Compare locked dependencies, migration docs, integration tests |

**Diagnostic flow:** verify right issuer/registration → verify Response signature/trust/Reference → decrypt if present → verify each Assertion signature and exact node → verify SAML conditions → principal conversion → authorization. Do not remove signature validation or Audience checks to patch config errors.

## 15. Security Review Checklist for a PR / SAML Integration

- [ ] `RelyingPartyRegistration` points to the right trusted IdP metadata/issuer/cert.
- [ ] User/roles are not read via arbitrary regex/XML DOM from an unvalidated `SAMLResponse`.
- [ ] **Response signature verified if present** and matches the exact Response used.
- [ ] **Assertion signature verified if present** and matches the exact Assertion used.
- [ ] If Response is unsigned, **all required Assertions** have trusted signatures; do not accept another unsigned Assertion.
- [ ] Reject any present yet invalid signature, even if another layer's signature is valid.
- [ ] Signed node/Reference/ID must be exact; reject duplicate IDs/signature wrapping.
- [ ] XML parser is hardened, schema is valid, and signing/hash algorithms are on the allowlist.
- [ ] For EncryptedAssertion, proper decryption credentials exist and signature/conditions checks continue.
- [ ] Response issuer/destination/status and Assertion audience/subject/time/confirmation are validated.
- [ ] Request correlation with `InResponseTo` is enforced for SP-initiated; explicit policy exists for unsolicited IdP-initiated.
- [ ] Replay protection matches profile/deployment.
- [ ] Principal/attributes come only from the **validated used Assertion**; do not merge unverified roles.
- [ ] Test multi-assertion, Response-only signed, Assertion-only signed, both, wrong-key, wrong-Reference, and signature-wrapping.
- [ ] Test low-privilege user, unauthorized user, different tenant, and expired Assertion.
- [ ] Do not disable default validators when customizing converter/decrypter; check actual Spring Security version.

## 16. Self-Check Questions

1. **Response is validly signed, inner Assertion is unsigned; can the SP accept it?** Potentially yes, if the Response signature **covers the exact used Assertion**, the IdP cert is trusted, policy/profile permits, and all SAML conditions are valid.
2. **Assertion is validly signed, outer Response is unsigned; can Destination/InResponseTo be skipped?** No. Response/request context must be validated per profile, even though Assertion protects its own inner fields.
3. **Response has validly signed A1 and unsigned A2, Response is unsigned; is using A1 enough?** Under the documented default Spring Security pipeline, **no**: either the Response must be signed or **all Assertions** must be signed.
4. **Does one valid signature protect every Assertion in the document?** No. You must verify Reference, transforms, signed subtree, and used node.
5. **What is Signature wrapping?** Verifying the signature of node A while the application uses node B outside the signed scope.
6. **Why can a valid signature still be rejected?** Audience, issuer, recipient, destination, time, request state, replay, or authorization policy may be invalid.
7. **Does encrypting an Assertion replace signing?** No; decryption provides confidentiality, and issuer/signature/conditions still must be verified.
8. **By default, from which Assertion does Spring Security build the principal?** The overview documentation of the described pipeline reads NameID/AttributeStatement from the **first Assertion after validation**. Custom converters or other versions must be verified separately.
9. **Should `getElementsByTagName("Assertion")` be used to extract the principal?** No. Logic must bind to the exact validated and signed node through a vetted SAML library.
10. **When the IdP changes its signing cert and the SP does not trust the new cert yet, what should be done?** Update verification credentials/metadata trust and roll out in a controlled manner; do not disable signature validation.

## 17. Official References

- Spring Security – SAML 2.0 Login Overview (pipeline, Response-or-all-Assertions signature policy, principal conversion): https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML2 Responses (provider, validator, decrypter, converters): https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – SAML2 Migration to 7 (response validation order): https://docs.spring.io/spring-security/reference/migration-7/saml2.html
- OWASP SAML Security Cheat Sheet (signature wrapping, exact signed assertion, XML validation): https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet
- OASIS SAML 2.0 Core (Assertions, Protocols, Signatures): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles (Web Browser SSO, signature requirements): https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML 2.0 Approved Errata (signature coverage/Response signature conditions): https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0.html

**Key takeaway:** A valid signature on the Response can protect a nested Assertion; a signature on an Assertion protects only that Assertion itself. **The data determining NameID/attributes/roles must come from an Assertion actually covered by a trusted signature**, and must then pass full **SAML conditions** and **application authorization**. Never take "signature valid" as standalone proof that every element in the XML is trustworthy.

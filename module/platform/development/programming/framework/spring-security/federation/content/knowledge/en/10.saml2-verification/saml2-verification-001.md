# Transport Message Decoding and XML Parsing with a Dedicated Library in SAML2

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **transport-layer decoding** (URL encoding, Base64, and DEFLATE), **XML parsing** (parse/unmarshal), **cryptographic decryption** (`EncryptedAssertion`), and **signature verification**; understand what each operation protects.
2. Accurately describe how `SAMLRequest`/`SAMLResponse` travel over **HTTP-Redirect Binding** and **HTTP-POST Binding**, with the proper decoding order for each type.
3. Use **Spring Security SAML2 + OpenSAML** to receive, unmarshal, and verify responses instead of manually reading `NameID` with regex/DOM and creating a session.
4. Understand the roles of `Saml2WebSsoAuthenticationFilter`, `Saml2AuthenticationTokenConverter`, `RelyingPartyRegistration`, the OpenSAML provider, and `Saml2Authentication`.
5. Practice Java 17+ with Base64 POST and raw DEFLATE Redirect to see how encoding works, without mistaking transport demos for an authentication system.
6. Apply parser hardening against **XXE**, resource limits against XML bombs/zip bombs, **XML Signature Wrapping** defenses, issuer/audience/destination/conditions verification, and sensitive data protection.

## 1. Nature of SAML2 Message Processing

**SAML 2.0** uses XML to represent protocol messages such as `AuthnRequest`, `Response`, and assertions about a user. A **Binding** describes how those messages travel over the wire (for example, HTTP Redirect or HTTP POST). A message being "successfully transported" only means the receiver has bytes to process; it does **not** prove the user has authenticated.

In the Web Browser SSO model:

- **Service Provider (SP) / Relying Party (RP):** the Spring Boot application that receives the SAMLResponse at the Assertion Consumer Service (ACS), verifies it, and creates a session if eligible.
- **Identity Provider (IdP) / Asserting Party (AP):** authenticates the user, issues the Response/Assertion, signs it with the IdP's private signing key, and may encrypt the assertion for the SP.
- **Browser:** follows redirects or submits an HTML form. The browser is an **untrusted transport channel**, not where identity is verified.
- **OpenSAML:** the library that parses/represents/verifies SAML objects. Spring Security builds a safe integration layer around those capabilities.
- **RelyingPartyRegistration:** the IdP/SP identities, certificates, and endpoints with trust established before receiving a response.

### 1.1. Separating Steps to Avoid Creating Vulnerabilities

| Step | Operation | Output | What is **not** yet guaranteed |
| --- | --- | --- | --- |
| HTTP transport | Servlet reads form/query parameter | `SAMLResponse` or `SAMLRequest` string | Not sure input is valid |
| Transport decode | URL decode / Base64 / Inflate per binding | XML bytes | Does not verify signature/issuer |
| XML parsing | Hardened parser reads namespaces and elements | XML structure | Does not know whether the IdP is trusted |
| SAML unmarshalling | OpenSAML converts XML into `Response`, `Assertion`, `Issuer`... | Domain objects | Protocol conditions not yet evaluated |
| Cryptographic processing | Signatures, trusted cert, decrypting encrypted elements when needed | Verifiable data | Insufficient if audience/recipient/expiry is wrong |
| SAML validation | Issuer, destination, audience, timestamp, `InResponseTo`, subject confirmation... | Assertion valid for SP and transaction | Does not automatically grant all business permissions |
| Spring authentication | Creates principal/authorities/`SecurityContext` | Application login session | Per-resource authorization remains separate |

**Three distinctions to remember:**

- **Base64 ≠ encryption:** anyone with the Base64 string can recover the bytes.
- **Successful XML parse ≠ verify SAML:** a message can be valid XML yet self-signed, expired, or intended for another application.
- **Successful decryption ≠ signature verified:** encryption protects content confidentiality; signatures and SAML conditions verify the trustworthiness of the result.

## 2. Overview of the SP-Initiated SAML2 Flow

```mermaid
sequenceDiagram
    actor User as User
    participant Browser as Browser
    participant SP as Spring Security SP
    participant IdP as IdP
    User->>Browser: Open /reports
    Browser->>SP: GET /reports (anonymous)
    SP-->>Browser: Redirect to AuthnRequest
    Browser->>SP: GET /saml2/authenticate/company
    SP->>SP: Generate AuthnRequest, ID, and RelayState
    SP-->>Browser: Redirect encoded SAMLRequest to IdP
    Browser->>IdP: GET /sso?SAMLRequest=...
    IdP->>IdP: Decode/parse AuthnRequest; verify signature if required
    IdP->>User: Login or use SSO session
    User->>IdP: Authenticate
    IdP->>IdP: Create and sign SAMLResponse/Assertion
    IdP-->>Browser: Base64 SAMLResponse form
    Browser->>SP: POST /login/saml2/sso/company
    SP->>SP: Decode, OpenSAML parse/unmarshal
    SP->>SP: Verify/decrypt/validate issuer, audience, state, time
    alt Valid
        SP->>SP: Create Saml2Authentication and session
        SP-->>Browser: Redirect to /reports
    else Invalid
        SP-->>Browser: Authentication failure
    end
```

The common flow uses **Redirect for AuthnRequest** and **POST for SAMLResponse**. The two bindings are not always fixed that way; check the metadata and agreements of the IdP/SP. Every response coming through the browser is external input to the SP.

## 3. Comparing HTTP-POST, HTTP-Redirect, and Artifact

| Binding | How the message is carried | Data recovery steps | Common usage |
| --- | --- | --- | --- |
| **HTTP-POST** | HTML form with `SAMLResponse` or `SAMLRequest` containing Base64-encoded XML | HTTP form decode → Base64 decode → XML parse | Response from IdP to SP's ACS |
| **HTTP-Redirect** | URL query with `SAMLRequest`/`SAMLResponse` as raw DEFLATE → Base64 → URL-encode | URL decode → Base64 decode → raw DEFLATE inflate → XML parse | AuthnRequest from SP to IdP |
| **HTTP-Artifact** | Browser only carries an artifact/reference; message is retrieved via an agreed back-channel | Artifact resolution protocol and trust verification | Some deployments needing a small front-channel |
| **SOAP/back-channel** | Server-to-server SOAP XML | SOAP/SAML protocol processing | Artifact resolution or secondary flows |

Do not apply one generic "decode SAML" snippet to every binding. If an HTTP-POST message is Base64 XML and you run `Inflater` on it, the result is usually a compressed data error. If an HTTP-Redirect raw DEFLATE payload is only Base64-decoded and treated as XML, the parser will see compressed bytes that are not XML.

### 3.1. Signatures Differ Across the Two Bindings

- With **POST binding**, the signature is usually an **XML Signature** inside `Response`/`Assertion`, verified according to XML Signature and trust policy.
- With **Redirect binding**, the signature may be in the query parameters `SigAlg`/`Signature`; the signature is computed over the exact string of **URL-encoded** query parameters in the binding's required order. Therefore, the decompressed XML **may not contain** `<ds:Signature>` even when the Redirect request is signed.
- Do not URL-decode, arbitrarily reorder query parameters, and then verify the signature, because that can alter the signed bytes.
- Never trust a certificate embedded in the message without matching it against the vetted trust configuration.

**Transport encoding does not create security.** It is the signature/trust and SAML conditions that allow the SP to accept an identity.

## 4. HTTP-POST Binding: From Form Field to XML

Example HTML form sent by the IdP:

```html
<!-- Abbreviated data; not a SAMLResponse capable of logging in -->
<form method="post" action="https://portal.example.org/login/saml2/sso/company">
  <input type="hidden" name="SAMLResponse" value="BASE64_ENCODED_XML" />
  <input type="hidden" name="RelayState" value="OPAQUE_STATE" />
  <button type="submit">Continue</button>
</form>
```

When the browser submits:

```http
POST /login/saml2/sso/company HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=BASE64_ENCODED_XML&RelayState=OPAQUE_STATE
```

Reading sequence:

1. The Servlet container parses the HTTP body according to its content type and provides the `SAMLResponse` parameter; do not form-urlencoded-decode twice.
2. The Base64 decoder recovers the XML bytes. **POST binding normally does not need DEFLATE.**
3. A securely configured XML parser reads the document and namespaces; the OpenSAML unmarshaller builds `Response` and related SAML types.
4. The provider verifies the signature against the IdP verification certificate, decrypts `EncryptedAssertion` if present, and validates issuer, destination, audience, time conditions, and request correlation.
5. Only when all required checks succeed is `Saml2Authentication` created.

### 4.1. Caution with `+` Signs and URL Encoding

The Base64 alphabet contains `+`, `/`, and padding character `=`. In `application/x-www-form-urlencoded`, `+` can be treated as a space if form encoding is mishandled. You should not:

- Manually read the raw POST body and call `replace("+", " ")`.
- Call `URLDecoder.decode` a second time on a parameter value already form-decoded by the container.
- Log the Base64 message to copy into a tool and assume the bytes were not altered.
- Try to get "clean" Base64 by stripping all unexpected characters and still proceed with authentication.

Use the tested binding handling from Spring Security/OpenSAML. If transport errors occur, inspect the raw HTTP capture **in a controlled environment with sensitive data masked**.

### 4.2. Having XML Does Not Mean Having a Trusted User

After Base64 decoding you may see `<samlp:Response>` and `<saml:Assertion>`, or you may see `<saml:EncryptedAssertion>`. An XML parser seeing an **EncryptedAssertion node** does not mean it can read the `NameID` inside. You need the matching SP private decryption key, where the IdP encrypted using the SP public encryption certificate.

XML with a valid signature but a wrong `AudienceRestriction` must also be rejected. XML with `NameID=admin` can easily be crafted by an untrusted party. Never use a parser to grant authorization.

## 5. HTTP-Redirect Binding: URL Decode, Base64, Raw DEFLATE

Here is an example when the SP sends an `AuthnRequest` to the IdP via HTTP Redirect:

```http
HTTP/1.1 302 Found
Location: https://idp.example.org/sso?SAMLRequest=ENCODED&RelayState=OPAQUE
```

Outbound order:

```text
AuthnRequest XML
    -> UTF-8 bytes
    -> raw DEFLATE compress
    -> Base64 encode
    -> URL encode
    -> Query parameter SAMLRequest
```

Inbound order:

```text
SAMLRequest query (URL decode exactly once)
    -> Base64 decode
    -> raw DEFLATE inflate
    -> XML bytes
    -> XML parser + SAML unmarshaller
    -> Binding signature + protocol validation by role
```

**Raw DEFLATE** differs from GZIP and the zlib wrapper. In Java, when testing raw DEFLATE use `Inflater(true)`. Production code must prefer the library's HTTP-Redirect decoder because beyond decompression it handles `SigAlg`/`Signature`, raw query encoding, and resource limits.

### 5.1. Defending Against "Compression Bombs"

A tiny compressed input can expand into huge XML. You must check:

- Received URL/query length; Base64 string length and compressed bytes.
- **Output size after inflation**, not just compressed bytes.
- Timeouts/CPU and limits on the servlet container/decoder/parser.
- Stream termination and whether compressed data is valid; do not accept unchecked data.
- XML depth, node/attribute counts, and entity expansion.

Do not "inflate everything first and then check `String.length`" if memory exhaustion can occur before the check.

### 5.2. Signature Path of Redirect Binding

When `SigAlg` and `Signature` are present, the signature protects the message according to the SAML HTTP-Redirect binding. An implementation that arbitrarily URL-decodes, reorders parameters, and re-encodes with a different charset before signing/verifying can fail even if the XML is still readable.

Therefore: **for real authentication, always delegate both decoding and binding signature handling to OpenSAML and Spring Security according to role**, rather than just running `Base64.getDecoder()` + `Inflater` and assuming the signature is valid.

## 6. Runnable Java 17 Example: POST Base64 and Safe XML Parser for Demo

Purpose: clearly show that "being able to read XML" **does not equal** "valid login". This snippet uses JDK 17, an in-memory sample XML, Base64 decode, and a JAXP parser configured against XXE. It **has no XML Signature validation, decryption, SAML profile checks, or trust configuration** and **must never be used as an ACS/login handler**.

**File `PostTransportDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public final class PostTransportDemo {
    private static final int MAX_XML_BYTES = 16 * 1024;

    public static void main(String[] args) throws Exception {
        String xml = """
                <samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                                ID="_demo" Version="2.0"/>
                """;
        String formParameter = Base64.getEncoder()
                .encodeToString(xml.getBytes(StandardCharsets.UTF_8));
        byte[] bytes = Base64.getDecoder().decode(formParameter);

        if (bytes.length > MAX_XML_BYTES) {
            throw new IllegalArgumentException("XML too large");
        }

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        Document document = factory.newDocumentBuilder()
                .parse(new ByteArrayInputStream(bytes));
        System.out.println("Root local name: "
                + document.getDocumentElement().getLocalName());
        System.out.println("Trusted authentication: false");
    }
}
```

Commands:

```bash
javac PostTransportDemo.java
java PostTransportDemo
```

Exact stdout:

```text
Root local name: Response
Trusted authentication: false
```

**Explanation:**

- `Base64` and `DocumentBuilderFactory` belong to the standard JDK, needing no Spring/OpenSAML for the transport exercise.
- `newDefaultInstance()` selects the JDK parser supported in Java 17; `namespaceAware` distinguishes local names/namespaces.
- `disallow-doctype-decl` rejects DTDs; `FEATURE_SECURE_PROCESSING` and external-access restrictions mitigate XXE/resource attacks. If an essential security setting is unsupported, the code **throws an error** rather than silently continuing.
- `MAX_XML_BYTES` is a **lab threshold** to prevent large inputs; production systems must limit request size and parser resources **before** allocation/decoding.
- `Response` is only the local name. The parser has not verified the SAML namespace, nor checked the signature or whether the token is meant for the right SP.
- **Do not change `Trusted authentication: false` to true** based on the parser output. Authentication must go through a SAML library with full validation.

### 6.1. Why Can't DOM/JAXP Replace OpenSAML?

A general XML parser only understands document structure. SAML requires XML Signature validation over the **exact signed node**, canonicalization, X.509 trust, issuer, audience, recipient, `InResponseTo`, bearer subject conditions, and timestamps. DOM/XML syntax does not know those rules on its own.

An incorrect approach:

```java
// Anti-pattern; DO NOT use for SAML verification.
String xmlText = new String(
        java.util.Base64.getDecoder().decode(samlResponseParam),
        java.nio.charset.StandardCharsets.UTF_8);
if (xmlText.contains("admin")) {
    // Must NOT manually create Authentication/ROLE_ADMIN.
}
```

An attacker can inject the string "admin" into XML at will; there may be a different namespace prefix, a fake node, or an unsigned assertion. **Only trust a principal after complete SAML validation.**

## 7. Runnable Java 17 Example: Raw DEFLATE Round-Trip for Redirect

The following snippet compresses a sample XML with **raw DEFLATE**, Base64-encodes it, and reverses the process to demonstrate. It does not compute `SigAlg`/`Signature`, nor does it create a compliant AuthnRequest to send to an IdP; it only observes encoding in a lab.

**File `RedirectTransportDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.Inflater;
import java.util.zip.InflaterInputStream;

public final class RedirectTransportDemo {
    private static final int MAX_INFLATED_BYTES = 16 * 1024;

    public static void main(String[] args) throws Exception {
        String xml = "<samlp:AuthnRequest "
                + "xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\" "
                + "ID=\"_demo\" Version=\"2.0\"/>";

        byte[] compressed;
        try (ByteArrayOutputStream sink = new ByteArrayOutputStream()) {
            Deflater deflater =
                    new Deflater(Deflater.DEFAULT_COMPRESSION, true);
            try (DeflaterOutputStream out =
                    new DeflaterOutputStream(sink, deflater)) {
                out.write(xml.getBytes(StandardCharsets.UTF_8));
            } finally {
                deflater.end();
            }
            compressed = sink.toByteArray();
        }

        String base64 = Base64.getEncoder().encodeToString(compressed);
        byte[] restored;
        Inflater inflater = new Inflater(true);
        try (InflaterInputStream input = new InflaterInputStream(
                new ByteArrayInputStream(
                        Base64.getDecoder().decode(base64)), inflater);
             ByteArrayOutputStream sink = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[1024];
            int n;
            while ((n = input.read(buffer)) != -1) {
                if (sink.size() + n > MAX_INFLATED_BYTES) {
                    throw new IllegalArgumentException("Inflated XML too large");
                }
                sink.write(buffer, 0, n);
            }
            restored = sink.toByteArray();
        } finally {
            inflater.end();
        }

        String result = new String(restored, StandardCharsets.UTF_8);
        System.out.println("Round trip matches: " + xml.equals(result));
        System.out.println("Trusted authentication: false");
    }
}
```

Commands:

```bash
javac RedirectTransportDemo.java
java RedirectTransportDemo
```

Exact stdout:

```text
Round trip matches: true
Trusted authentication: false
```

In real HTTP Redirect there is also **URL-encoding into the query string**: on receipt, the container/binding processor must URL-decode exactly once before Base64. This demo intentionally omits the HTTP URL step because the input is created in memory. Do not use the demo to verify Redirect signatures; that is the job of a dedicated binding handler.

### 7.1. Why Shouldn't You Use the Demo Snippet in Production?

- Does not parse `RelayState`, `SigAlg`, and `Signature`.
- Does not verify signed bytes according to the HTTP-Redirect binding.
- Has no knowledge of SP/IdP entity IDs, destination, service registration, or the SAML message schema.
- Has no XML parser/SAML unmarshaller and SAML signature/conditions validator.
- Only enforces size limits **after** some memory allocations; production needs HTTP/URL/Base64 size limits at an earlier layer.
- Must not accept arbitrary URLs/metadata/issuers from browser input.

**Use the JDK demo to learn; use OpenSAML/Spring Security to authenticate.**

## 8. OpenSAML Reads XML into the SAML Object Model

OpenSAML handles many domain types:

| XML / concept | Type/meaning in SAML |
| --- | --- |
| `<samlp:Response>` | Protocol response envelope, status, issuer, destination, ID, InResponseTo |
| `<saml:Assertion>` | Assertion payload about a subject, authentication/attributes/conditions |
| `<saml:Issuer>` | Issuing party of request/response/assertion |
| `<saml:Subject>` and `<saml:NameID>` | Subject identifier, not necessarily an email |
| `<saml:Conditions>` | Validity window and usage restrictions |
| `<saml:AudienceRestriction>` | Which SP is permitted to accept the assertion |
| `<saml:SubjectConfirmation>` | Subject confirmation/recipient/InResponseTo conditions |
| `<saml:AuthnStatement>` | Authentication timestamp/method per profile |
| `<saml:AttributeStatement>` | Claims/attributes issued by the IdP |
| `<saml:EncryptedAssertion>` | Encrypted assertion requiring the SP's private key |
| `<ds:Signature>` | XML Signature requiring verification with trust material for the right issuer |

The **Unmarshaller** converts XML DOM elements into SAML `XMLObject` instances with proper structure/namespaces. The **Validator** and provider determine whether these objects can be trusted. Never use `Unmarshaller` alone to log a user in: a structurally complete SAML object does not guarantee a trusted signature.

### 8.1. Why Is Parsing with Regex/String Search Dangerous?

XML allows changing namespace prefixes; `<saml:NameID>` and `<x:NameID>` can share the same namespace. Conversely, two identical prefixes with different namespaces can represent different data. In addition, there are:

- Namespace spoofing and duplicate-named nodes.
- Undecrypted `EncryptedAssertion`.
- XML Signature Wrapping, duplicate IDs, or a signature protecting **node A** while the code reads the user from **node B**.
- XML entities/DTDs leading to XXE, SSRF, or resource exhaustion.
- Responses with multiple assertions, with the signature on Response or on each Assertion depending on the profile.
- Messages with wrong audience, expiration, destination, or request correlation.

Reading `NameID` text is only reading a **claim**; before trusting it, you must ensure the claim belongs to a **protected and valid SAML object**.

### 8.2. XML Signature Wrapping (XSW)

A signature can use an ID reference to an assertion. An attacker can insert another assertion outside the signed portion; a custom parser/validator might verify a signed node yet extract the identity from an unsigned node. Countermeasures:

1. Use a maintained SAML library that handles ID uniqueness and signature references.
2. Verify the exact **signed**/protected node; do not select an assertion by arbitrary DOM position.
3. The verification certificate must come from **vetted IdP metadata/registration**, rather than trusting any `KeyInfo` inside the message.
4. Configure an appropriate signed-response/signed-assertion policy; do not skip XML Signature verification just because "it decoded".
5. Keep Spring Security/OpenSAML updated and test negative cases when the IdP changes profiles.

### 8.3. XML External Entity (XXE)

XML is untrusted input. A misconfigured parser can read internal files or make network requests via external entities. Defensive layers:

- Disallow `DOCTYPE`/DTD when not needed.
- Disable external general/parameter entities, external DTD loading, and XInclude.
- Restrict external schema/stylesheet resource access.
- Use `FEATURE_SECURE_PROCESSING` and corresponding parser resource limits.
- **Fail closed** if the parser does not support a required security flag; do not fall back to an unvetted default parser.
- Do not add an unhardened "XML pretty-print debug parser" alongside OpenSAML.

Do not fix XXE by using regex to strip `<!DOCTYPE>` strings, because parsers handle many constructs/encodings and attackers can bypass regex filters.

## 9. Spring Security: Components in Inbound SAMLResponse Processing

In a Servlet application using `spring-security-saml2-service-provider`, the common flow is:

```text
Browser POST /login/saml2/sso/company
  -> Saml2WebSsoAuthenticationFilter
  -> Saml2AuthenticationTokenConverter
       + HttpServletRequest
       + RelyingPartyRegistration(company)
       -> Saml2AuthenticationToken
  -> AuthenticationManager
  -> OpenSAML authentication provider
       -> Deserialize/unmarshal Response
       -> Verify signatures with trusted IdP certificate
       -> Decrypt encrypted elements using SP private key
       -> Validate issuer, destination, audience, conditions, state
       -> Create Saml2AuthenticatedPrincipal/authorities
  -> Saml2Authentication
  -> SecurityContext and app session (if accepted)
```

`Saml2AuthenticationTokenConverter` extracts the response from the request and attaches the right registration so the provider knows **whom to trust, which entity ID to receive for, and which key to decrypt with**. It must not be where business code concludes login succeeded merely because the parameter exists.

**Version note:** Spring Security 6.x has OpenSAML provider implementations with version-specific names (for example `OpenSaml4AuthenticationProvider` or `OpenSaml5AuthenticationProvider` depending on dependency/version); current Spring Security documentation describes `OpenSaml5AuthenticationProvider`. When configuring extensions, look up the API for the **exact version your project uses**, rather than copying a class from another release. The general semantics of decode/unmarshal/verify/decrypt/validate remain the same.

### 9.1. Importance of `RelyingPartyRegistration`

Each RP registration provides:

- `registrationId` – local configuration identifier (for example `company`).
- SP `entityId`, ACS URL – the assertion must be issued for this SP and endpoint.
- IdP `entityId/issuer`, SSO URL/metadata – the trusted SAML source.
- **IdP verification certificates** – public signing certs used to verify the response/assertion.
- **SP decryption credentials** – SP private key when the IdP issues an EncryptedAssertion.
- **SP signing credentials** – SP private key if AuthnRequest must be signed.

Choosing the wrong registration in a multi-IdP system easily leads to issuer/certificate mismatches. Do not "try every cert of every IdP until one passes" if doing so breaks tenant/trust boundaries.

### 9.2. Order of Cryptographic Validation

A properly configured SAML provider must verify the Response Signature (if present), decrypt EncryptedAssertion when needed, check Response Issuer/Destination, verify Assertion signatures, process encrypted elements, and validate conditions such as AudienceRestriction, bearer SubjectConfirmation, and validity timestamps. The detailed order of steps can vary by version and where signatures/encryption appear.

**Do not manually reorder** "decrypt all XML, modify DOM, then recompute signatures" because XML canonicalization and signature references can change. If a response only signs the outer Response versus an assertion having its own signature, the timing of decrypting encrypted elements also matters.

### 9.3. When Is `Saml2Authentication` Created?

Only after the SAML provider concludes the response is valid does Spring Security place the principal/authorities into `Authentication` and store it in `SecurityContext`/session in the standard web login manner. `NameID` is commonly the source for `Authentication#getName()`; some systems map a different principal per policy.

**Access control** still belongs to the application: logging in from an IdP does not automatically grant `ROLE_ADMIN`. If a user is authenticated but lacks permission on a resource, the application can return 403 unrelated to XML transport.

## 10. Spring Boot 3 / Spring Security 6 Example: Do Not Write a Custom ACS Parser

The Java 17+ example below configures a **Spring Boot Servlet project**. It requires a real IdP, valid metadata/entity IDs/ACS, and a valid trusted X.509 cert. It cannot be compiled with standalone `javac` because of Spring dependencies; `example.org` domains are for illustration only.

### 10.1. Gradle Dependencies

`build.gradle` already applies the Spring Boot plugin and dependency management; the required dependencies section is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Use the Spring Security/OpenSAML versions supported by your project's BOM/repositories. Do not manually pull in an incompatible OpenSAML version just because an old article uses a different class.

### 10.2. Manual Registration Configuration with YAML

File `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          company:
            entity-id: "https://portal.example.org/saml2/service-provider-metadata/company"
            acs:
              location: "https://portal.example.org/login/saml2/sso/company"
            assertingparty:
              entity-id: "https://idp.example.org/saml"
              verification:
                credentials:
                  - certificate-location: "classpath:idp-signing.crt"
              singlesignon:
                url: "https://idp.example.org/sso"
                sign-request: false
```

Explanation:

- `company` is the local registration name, used in `/saml2/authenticate/company` and ACS `/login/saml2/sso/company`.
- `entity-id` at the registration level is the SP entity ID; the IdP must register it and only issue assertions for that exact audience.
- `acs.location` must match the external HTTPS URL that the browser can POST to and the IdP recognizes. A reverse proxy must not synthesize the wrong host/scheme.
- `assertingparty.entity-id` is the trusted IdP issuer; distinct from the SP entity ID.
- `verification.credentials` is the **IdP's public signing certificate from a verified source**; do not take it from a self-declared response.
- `sign-request: false` is only valid if the IdP permits unsigned requests. If signed AuthnRequests are required, you must add the SP signing private key/cert and set `true`.
- If receiving `EncryptedAssertion`, you must add the SP's `decryption.credentials` so OpenSAML can decrypt during authentication.

**The YAML cannot fully run without a real `idp-signing.crt`** and proper IdP registration. This is a code/config example, not a deployed SSO product.

### 10.3. Java 17+ SecurityFilterChain

File `src/main/java/com/example/saml/SamlSecurityConfiguration.java`:

```java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated()
                )
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
```

With `saml2Login()`, Spring Security already provides filters for outbound `AuthnRequest` and inbound SAMLResponse at the ACS. **There is no need to write your own HTTP controller that accepts POST, Base64-decodes, parses XML, and manually issues a session.**

Anti-pattern:

```java
// Do not use this approach to authenticate SAML2.
@PostMapping("/login/saml2/sso/company")
void accept(String samlResponse) {
    // Base64 decode -> extract NameID -> manually mark authenticated: WRONG.
}
```

When you need to **customize** how responses are validated/received, use the extension points of `Saml2LoginConfigurer`/the provider in use; keep default signature, issuer, audience, recipient, time, and request correlation checks intact. Do not create an authentication "shortcut" outside Spring Security.

### 10.4. Startup Class and Controller

File `src/main/java/com/example/saml/SamlDemoApplication.java`:

```java
package com.example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlDemoApplication.class, args);
    }
}
```

File `src/main/java/com/example/saml/ReportController.java`:

```java
package com.example.saml;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    @GetMapping("/")
    String home() {
        return "Public";
    }

    @GetMapping("/reports")
    String reports(Authentication authentication) {
        return "Authenticated as " + authentication.getName();
    }
}
```

If a real IdP sends a valid assertion with NameID `employee-42` and the application accepts it, the HTTP response of `GET /reports` can be:

```text
Authenticated as employee-42
```

This is a **conditional** result based on the actual NameID, not `javac` stdout. Learners must configure the IdP/ACS/cert properly and complete the browser SSO flow to observe this result.

## 11. Signature Verification and Encryption Cannot Be Skipped

### 11.1. Signature Trust

The IdP signs the Response/Assertion with the **IdP's private signing key**. The SP uses the **trusted IdP public signing certificate** in the registration to verify it. If the Response contains a `<KeyInfo>` or an attached certificate, that certificate **does not automatically become a trusted key**. An attacker can self-sign a response with their own key and attach the corresponding cert.

A valid signature against a cert is **not enough** if issuer, audience, recipient, time conditions, or request correlation are wrong.

### 11.2. XML Signature Wrapping

SAML XML can contain multiple elements; an XML Signature may protect one assertion by ID. If an application picks another `NameID` outside the verified node, an attacker can exploit **XML Signature Wrapping**. Therefore, use the exact data verified by the provider instead of parsing the whole document yourself and looking up nodes by position.

### 11.3. Decryption Credentials

The IdP can use the SP's public encryption certificate to encrypt `EncryptedAssertion`. The SP decrypts it using the **SP's private decryption key** in `RelyingPartyRegistration`. This is a real cryptographic operation, **not Base64 decoding**.

If the IdP changes the SP encryption certificate during rotation, the SP may need to keep both old/new private keys during the overlap period per library and policy. Do not remove signature verification just to "get decryption working".

### 11.4. Signatures and XML Encoding

XML Signature is sensitive to canonicalization/Reference URI/ID mapping. Do not pretty-print/re-serialize/modify a signed element and expect the signature to remain valid. The binding handler and provider operate on the standard structure/evidence; debugging should only inspect sanitized data.

## 12. SAML Checks Required After Parsing

| Condition | Purpose |
| --- | --- |
| **Issuer** | Response/Assertion comes from a registered IdP |
| **Destination/Recipient** | Browser POSTed to the agreed ACS, and assertion is intended for a valid endpoint |
| **AudienceRestriction** | Assertion is intended for the right SP entity ID, not another SP |
| **InResponseTo** | In SP-initiated flows, the response correlates to the SP's AuthnRequest; prevents mix-up/login CSRF |
| **NotBefore / NotOnOrAfter** | Not-yet-valid or expired assertions must be rejected |
| **SubjectConfirmation** | Verify bearer confirmation/recipient/time/request ID conditions |
| **Signature placement** | The trusted object must actually be protected by a valid signature |
| **Replay/state** | Do not accept replay of a response/assertion outside policy |
| **SAML status** | If the IdP reports authentication failure, do not create a successful session |
| **Principal mapping** | Map the authenticated subject/attributes to an internal account and tenant permissions |

If any step fails, **do not grant authentication**. Never "shorten validation" to make a demo run when URLs or certificates are wrong.

## 13. Security Risks Specific to XML and Transport

1. **XXE/SSRF:** an unlocked DTD/external entity parser can access internal resources; apply security parser settings and fail closed.
2. **XML bomb:** entity expansion, node depth, and DOM allocations can exhaust memory; set HTTP/input/parser limits.
3. **DEFLATE bomb:** a small Redirect payload inflates into huge XML; limit output before accumulating too much data.
4. **XML Signature Wrapping:** verify the exact signed node, without confusing a valid assertion with a forged one.
5. **Forged certificates:** do not use `KeyInfo` from XML to expand the list of trusted IdPs.
6. **Replay:** check request ID/state/time and profile; a used SAMLResponse is not a "forever login ticket".
7. **IdP mix-up:** with multiple registrations, issuer/certificate/ACS must belong to the chosen IdP/tenant.
8. **URL/form double-decoding:** do not decode `+`/`%xx` an extra time and then parse mutated data.
9. **Data leakage in logs:** XML assertions can contain emails, NameIDs, groups, identifiers, and signatures; do not log raw payloads/URL queries.
10. **Cross-site POST cookies:** Browser POST to ACS from the IdP domain may drop session cookies due to `SameSite`; check cookies/HTTPS and request correlation instead of dropping `InResponseTo`.
11. **Reverse proxy:** altered hostname/scheme can cause `Destination`/`Recipient` mismatches even when transport decoding succeeds.
12. **Do not auto-grant privileges:** permission checks are still needed after authentication; do not grant `ROLE_ADMIN` from arbitrary SAML attributes.

## 14. Layer-by-Layer Testing and Troubleshooting

| Symptom | Common error layer | How to check |
| --- | --- | --- |
| `Illegal base64 character` | POST/form encoding or transport | Ensure form value is not double-URL-decoded; inspect `+`/`/`/`=` characters |
| `DataFormatException` | Redirect DEFLATE | Verify raw DEFLATE is used; do not pass GZIP/zlib or POST XML into Inflate |
| `Content is not allowed in prolog` | XML parse | Usually improperly decoded, bytes are not XML, or wrong charset/parameter |
| XML root is not `samlp:Response` | Unmarshal/type | Wrong SAMLRequest/endpoint used, different namespace, or forged payload |
| `DOCTYPE is disallowed` | Parser hardening | Parser rejects DTD per policy; do not allow it just to bypass the error |
| OOM / high CPU | Inflate, XML parse | Set size limits, depth/entity limits, timeouts, and resource budgets |
| `InvalidSignature` | Cryptographic validation | Check trusted IdP signing cert, metadata, and key rollover |
| Missing `NameID` | Unmarshal/decryption | Assertion may be encrypted; check decryption credentials |
| `DecryptionException` | EncryptedAssertion | SP private key mismatches cert used by IdP, or incompatible algorithm/rotation |
| `Issuer mismatch` | SAML trust | Wrong registration/IdP, or response from an unknown issuer |
| `Audience/Recipient mismatch` | SAML conditions | Wrong SP entity ID/ACS, or proxy changed public URL |
| `InResponseTo mismatch` | Session/request state | Cookie SameSite, session repo, LB, or wrong transaction |
| SAML succeeds but returns 403 | Authorization | Principal lacks role/permission; not a Base64/parser error |
| Redirect loop after ACS | Session persistence | Check SecurityContext, session cookie/domain/proxy/filter chains |

### 14.1. Sensible Debugging Workflow

1. Check HTTP method, endpoint, content type, and whether the `SAMLResponse`/`SAMLRequest` field matches the binding.
2. Check transport decoding (Base64/Inflate) for the right binding type rather than applying one routine to all.
3. Verify the XML parser sees the expected root QName/namespace via controlled tooling; do not log raw SAML in production.
4. Check registration, issuer, IdP cert, SP decryption key, and metadata.
5. Check signature, audience, destination, conditions, request correlation, and clock.
6. Check session/cookies and authorization **only after authentication succeeds**.

Do not disable the signature validator or `InResponseTo` as a temporary workaround. If the library reports a security error, find the root cause in trust, binding, and policy.

## 15. Hands-On Testing

**Transport-only tests:**

- Valid POST Base64 → matches sample XML bytes.
- Corrupted/oversized POST Base64 → fails before parsing.
- Redirect raw DEFLATE → accurately recovers fixture bytes.
- GZIP bytes passed into raw Inflater → rejected; do not guess formats.
- XML with DOCTYPE/external entity → hardened parser rejects.
- XML with wrong namespace/fake root → unmarshaller does not treat it as a valid SAML Response.
- Small compressed data inflating past limit → rejected.

**Security validation tests:**

- Response from IdP with trusted signature/certificate + valid conditions → authentication can succeed.
- Self-signed XML Response → must be rejected even if decode/parse is flawless.
- Response with valid signature but audience/recipient for another SP → rejected.
- Expired or replayed Response → rejected.
- Fake/unsigned assertion alongside a signed assertion → do not read user from the fake node.
- EncryptedAssertion without the matching SP private key → fails decryption, no session created.
- Logged in but missing role → 403 authorization.

Spring Boot build commands (in a project with Gradle Wrapper):

```bash
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-saml2-service-provider
./gradlew compileJava
./gradlew test
```

On Windows you can use `.\gradlew.bat`. These commands only check the configured code/build/tests; end-to-end login still requires a real IdP and browser. The two standalone Java 17 examples in sections 6–7 have their own `javac`/`java` commands and deterministic stdout.

## 16. Self-Check Questions

**1. Why does successful Base64 decoding not prove the user has logged in?**

Base64 only changes the byte representation; the XML could come from an attacker or be intended for another SP. You must verify the signature/trust and SAML conditions before creating Authentication.

**2. How do HTTP-POST and HTTP-Redirect differ in decoding?**

POST usually carries Base64 XML in a form field. Redirect usually uses a URL-encoded, Base64-encoded, raw-DEFLATE-compressed query parameter, so the receiver must URL-decode, Base64-decode, and then inflate before parsing.

**3. Why might a Redirect AuthnRequest signature not have `<ds:Signature>` inside the XML?**

Because the binding can directly sign the URL-encoded query parameters `SAMLRequest`, `RelayState`, and `SigAlg`, carrying the signature in the `Signature` parameter.

**4. Why shouldn't you run `contains("admin")` on XML after decoding?**

A substring does not prove identity, nor does it check signatures, namespaces, the signed node, audience, or expiration. It can lead to authentication bypass and XML Signature Wrapping.

**5. How is OpenSAML's role different from JAXP DOM?**

JAXP understands XML; OpenSAML understands SAML structure/object types and, together with Spring Security, performs signature/decryption/validation per profile. A DOM parse does not establish trust.

**6. Can `EncryptedAssertion` be read with a Base64 decoder?**

No. Base64 can recover the XML carrying EncryptedAssertion, but the encrypted content requires the SP private decryption key and matching algorithm, followed by SAML verification.

**7. Is `Saml2AuthenticationTokenConverter` the component that decides the user is logged in?**

No. The converter builds a request token from the HTTP response and registration. The provider with OpenSAML verifies it before producing a valid `Saml2Authentication`.

**8. Why shouldn't you trust a certificate from `KeyInfo` inside an unverified SAMLResponse?**

An attacker can generate a key, sign a forged response, and embed their own public cert. The SP must use the IdP certificate registered/verified through a trusted channel.

**9. What should happen if the signature is valid but `AudienceRestriction` is another SP?**

Reject. A signature does not make an assertion valid for all applications; it must match the SP entity ID and ACS/recipient per profile.

**10. Can `PostTransportDemo`/`RedirectTransportDemo` be used for production SSO?**

No. They only demonstrate encoding/decoding and safe parsing at a lab level. They lack signature/trust/issuer/audience/time/replay/authorization validation.

## Takeaways

**SAML2 has multiple processing layers that cannot be skipped:**

**HTTP binding → transport decoding → hardened XML parser → OpenSAML unmarshal → trusted signature verification and decryption if needed → SAML conditions validation → Spring Security Authentication → application authorization.**

- **POST:** form-urlencoded + Base64 of XML; normally no Inflate.
- **Redirect:** URL-encoding + Base64 + raw DEFLATE; signature may be in the query binding, not inside the XML.
- **XML parse ≠ authentication:** only accept a principal from an assertion with a valid source, right signed target, right SP, valid time window, and request correlation.
- **Use Spring Security/OpenSAML** instead of writing custom ACS parsers/regex.
- **Enforce resource limits and lock down the XML parser**, mask sensitive data in logs, and always fail closed if a security step does not pass.

### References

- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [OASIS – SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html)
- [OWASP – XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html)

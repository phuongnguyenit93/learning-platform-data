# Structure of Response, Assertion, and Subject in SAML2

> **Module:** Spring Security – federation · **Parent topic:** SAML2 Model. This lesson explains how to read the three core XML layers of SAML 2.0 Web Browser SSO, how they link together, and how a Service Provider (SP) verifies them before accepting a login.

## Learning Objectives

After this lesson, you can:

1. Distinguish **`<samlp:Response>`**, **`<saml:Assertion>`**, and **`<saml:Subject>`** by their responsibilities, positions, and the data they carry.
2. Read the `ID`, `Version`, `IssueInstant`, `Destination`, `InResponseTo`, `Issuer`, and `Status` attributes/elements; cross-check them against the login request and SP configuration.
3. Understand the meaning of `NameID`, `SubjectConfirmation`, `SubjectConfirmationData`, `Conditions`, `AudienceRestriction`, `AuthnStatement`, and `AttributeStatement`.
4. Trace a structurally complete XML example, identifying **who issued it**, **who the subject is**, **which SP it was issued for**, **which request it responds to**, and **until what time it remains acceptable**.
5. Explain why **Base64 decoding or reading XML does not prove authenticity**, and state the checks an SP must perform before creating a session.
6. Recognize how Spring Security SAML2 turns a verified response into `Saml2Authentication` and `Saml2AuthenticatedPrincipal`.

## 1. The Big Picture: Three Layers, Three Responsibilities

In SAML 2.0 Web Browser SSO, the **Identity Provider (IdP)**, also called the *Asserting Party*, authenticates the user; the **Service Provider (SP)**, also called the *Relying Party*, receives and verifies the SAML message to decide whether to create an application session.

Look at the following conceptual structure:

~~~text
HTTP POST to the Assertion Consumer Service (ACS)
└── form field SAMLResponse = Base64(XML)
    └── <samlp:Response>              (protocol-layer message envelope)
        ├── <saml:Issuer>             (response issuer)
        ├── <ds:Signature>?           (if signed at the Response layer)
        ├── <samlp:Status>            (request processing result)
        └── <saml:Assertion>          (a SAML assertion)
            ├── <saml:Issuer>         (assertion issuer)
            ├── <ds:Signature>?       (if signed at the Assertion layer)
            ├── <saml:Subject>        (subject of the assertion)
            │   ├── <saml:NameID>     (subject identifier)
            │   └── <saml:SubjectConfirmation>
            │       └── <saml:SubjectConfirmationData>
            ├── <saml:Conditions>     (conditions under which use is permitted)
            │   └── <saml:AudienceRestriction>
            ├── <saml:AuthnStatement> (authentication event/context)
            └── <saml:AttributeStatement> (user attributes)
~~~

The `?` mark on Signature means **the signature location depends on the profile and configuration**, not that every unsigned response is accepted. In a typical Web SSO setup, the SP must require **valid signature proof according to the profile/trust policy**: signing the Response and/or signing the Assertions according to the appropriate rules. An illustrative XML document without a real signature is **not sufficient** to log in.

A mnemonic:

| Component | Answers the question | Should not be used to conclude |
| --- | --- | --- |
| **Response** | “What message did the IdP return to the SP, for which request, and with what processing result?” | Not enough to conclude a user is logged in before verifying the assertion. |
| **Assertion** | “What facts does the IdP assert about a subject, within what scope and validity window?” | Does not prove every claim is an application permission. |
| **Subject** | “Who is the assertion about, and what conditions must the presenter meet to be accepted?” | Not a password; `NameID` does not by itself prove access rights. |

**Distinguishing protocol from transport:** the `SAMLResponse` string in an HTTP form is a **binding parameter** name, usually containing Base64-encoded XML. It is distinct from the `<samlp:Response>` XML element. Base64 is a data representation encoding, **not security encryption and not a signature**.

## 2. Namespaces and Element Names

SAML2 separates **protocol** from **assertion** using two XML namespaces:

| Common prefix | Namespace URI | Examples |
| --- | --- | --- |
| `samlp` | `urn:oasis:names:tc:SAML:2.0:protocol` | `Response`, `Status`, `AuthnRequest` |
| `saml` | `urn:oasis:names:tc:SAML:2.0:assertion` | `Assertion`, `Subject`, `NameID`, `Conditions` |
| `ds` | `http://www.w3.org/2000/09/xmldsig#` | `Signature` and XML Digital Signature structures |

**Prefixes can change:** `<p:Response xmlns:p="urn:oasis:names:tc:SAML:2.0:protocol">` and `<samlp:Response ...>` refer to the exact same element by XML namespace. Parsers must rely on **namespace URI + local name**, not on the prefix string in the XML. SAML Core specifies element names and ordering; not just any XML element named “Assertion” is valid.

## 3. Outermost Layer: `<samlp:Response>`

Response is the protocol message returned by the IdP to the SP. Typical structure:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp-4ac"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:00Z"
    Destination="https://sp.example.org/login/saml2/sso/partner"
    InResponseTo="_req-48f">
    <saml:Issuer>https://idp.partner.example.org/saml</saml:Issuer>
    <!-- If signing Response, ds:Signature goes here in valid XML order -->
    <samlp:Status>
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>
    <!-- Assertion or EncryptedAssertion follows Status -->
</samlp:Response>
~~~

This is an **illustrative structural snippet**, not a signed Response or one usable for login.

### 3.1. Meaning of Each Field

| Field | Meaning | What the SP must verify |
| --- | --- | --- |
| `ID` | Unique identifier of the **Response** (per SAML ID rules). | Identify the response and prevent duplicates/replay when appropriate; distinct from Assertion and AuthnRequest IDs. |
| `Version="2.0"` | SAML protocol version. | Must match the SAML 2.0 processor. |
| `IssueInstant` | Time the IdP issued the **Response**. | Check time/clock-skew policy; do not confuse with when the user authenticated. |
| `Destination` | Intended address **receiving the Response message**. | Usually must match the SP's expected ACS address exactly per binding/configuration. |
| `InResponseTo` | ID of the **AuthnRequest** that this Response answers. | In SP-initiated SSO, must correspond to an SP-issued request that is still valid. |
| `<saml:Issuer>` | Issuer of the Response (usually the IdP's entity ID). | Must match the configured IdP/registration; do not trust an issuer chosen arbitrarily by the request. |
| `<samlp:Status>` | Processing result of the SAML request. | Requires an appropriate status, typically `Success`, before accepting the authentication result. |
| `<saml:Assertion>` | One or more assertions containing statements. | Must verify integrity, conditions, and subject on the assertion actually used. |
| `<saml:EncryptedAssertion>` | Assertion in encrypted form (if used). | Decrypt with the SP's key and continue checking signatures/conditions in proper order. |

The Response `ID` is **different** from `InResponseTo`: for example, `_resp-4ac` is the new message ID, while `_req-48f` points to the previous request ID. Do not validate by comparing these two IDs to each other.

### 3.2. `Status`: Protocol Result, Not Access Permission

~~~xml
<samlp:Status
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Responder">
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:AuthnFailed"/>
    </samlp:StatusCode>
    <samlp:StatusMessage>Authentication failed</samlp:StatusMessage>
</samlp:Status>
~~~

A Response can carry errors such as `Responder`, `AuthnFailed`, `Requester`, or other SAML statuses. An error response may **have no successful authentication assertion**. `StatusMessage` is an optional description and must be treated as external data when displayed or logged; detailed IdP errors should not leak sensitive information.

`Success` only means the protocol request was processed successfully; **it does not replace verifying the signature, subject, Conditions, or application permissions**.

## 4. Assertion Layer: `<saml:Assertion>`

An Assertion is a package of statements from an issuer about a subject. For Web Browser SSO, an authentication assertion typically contains:

~~~text
Assertion
├── ID, Version, IssueInstant
├── Issuer
├── Signature (if assertion is signed)
├── Subject
├── Conditions
├── AuthnStatement
│   ├── AuthnInstant
│   ├── SessionIndex (optional)
│   └── AuthnContext
└── AttributeStatement (if present)
    └── Attribute / AttributeValue
~~~

### 4.1. Three Common Statement Types

- **`AuthnStatement`**: The IdP asserts that **the user authenticated**, with `AuthnInstant`, `AuthnContext`, and possibly `SessionIndex` or `SessionNotOnOrAfter`. This is the core of the SSO story.
- **`AttributeStatement`**: The IdP asserts **attributes** of the subject (email, department code, groups…). Each `Attribute` can have **multiple `AttributeValue` elements**; do not assume a single value is unique/singular.
- **`AuthzDecisionStatement`**: SAML Core models authorization decision statements, but they should not be implicitly treated as the authorization policy for every application. The application must clearly define the authority source and trust contract if used.

In Spring Security's SAML2 Login flow, the application typically relies on the verified assertion to build a principal, then performs **separate authorization** at the application layer. An attribute `department=finance` or `group=admin` does not automatically become an `APP_PAYMENT_APPROVE` permission.

### 4.2. `Issuer` in Response and Assertion

A message can have `Issuer` at **two layers**: the Response issuer and each Assertion's issuer. In a typical Web SSO configuration, both must align with the trust relationships with the IdP. You must not check only the outer issuer and blindly trust any inner assertion.

The same applies to digital signatures: a **Response signature** protects one XML scope; an **Assertion signature** protects another scope. You must know exactly which element is signed and which element the program consumes, to guard against XML Signature Wrapping variants.

### 4.3. `Conditions` Is Not `SubjectConfirmationData`

~~~xml
<saml:Conditions
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    NotBefore="2030-05-01T09:59:00Z"
    NotOnOrAfter="2030-05-01T10:05:00Z">
    <saml:AudienceRestriction>
        <saml:Audience>
            https://sp.example.org/saml2/service-provider-metadata/partner
        </saml:Audience>
    </saml:AudienceRestriction>
</saml:Conditions>
~~~

- `NotBefore`: the assertion **must not be used before this time**, subject to the clock-skew tolerance policy.
- `NotOnOrAfter`: at or after this instant, the assertion **is no longer valid for acceptance**; do not interpret this boundary as “still valid during the exact expiration second.”
- `AudienceRestriction`: specifies **entities permitted to consume the assertion**; typically the **SP entity ID**, not necessarily equal to the ACS address.
- Other conditions such as `OneTimeUse` or `ProxyRestriction` may be present. Enforcement support depends on the library/profile/policy; if a condition is not safely handled, do not silently ignore it.
- You must check **both Conditions and SubjectConfirmationData** when applicable; passing one **does not** compensate for failing the other.

## 5. Subject Layer: `<saml:Subject>`

`Subject` resides **inside an Assertion** and describes who is the subject of the statements. It usually has two important parts:

~~~xml
<saml:Subject
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
        partner-user-073
    </saml:NameID>
    <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            InResponseTo="_req-48f"
            NotOnOrAfter="2030-05-01T10:05:00Z"
            Recipient="https://sp.example.org/login/saml2/sso/partner"/>
    </saml:SubjectConfirmation>
</saml:Subject>
~~~

### 5.1. `NameID`: How the Asserted Person Is Identified

`NameID` has text content and may carry `Format`, `NameQualifier`, `SPNameQualifier`, and `SPProvidedID` depending on the setup. Some common formats:

| NameID Format | Meaning | Proper interpretation |
| --- | --- | --- |
| `unspecified` | IdP and SP use a custom convention. | Must read the IdP–SP contract to know what this string represents. |
| `emailAddress` | Email address formatted identifier. | Emails can change or be recycled; avoid linking accounts solely by email. |
| `persistent` | IdP-issued identifier that is durable within the federation context. | Suitable for account linking if IdP policy confirms stability and scope. |
| `transient` | Temporary identifier, not a long-term key. | Do not use to link a user across logins unless the IdP guarantees stability. |

**NameID is not by default a username/email/local user ID.** With multiple IdPs, the same `NameID` string can refer to different people; account linking should be keyed by **issuer/entity ID + NameID and format/qualifier context** per contract, optionally adding tenant/registration. An empty/unexpected `NameID` or wrong format must be handled by policy rather than guessed.

`NameID` can also be encrypted as `EncryptedID`. In that case the SP must decrypt it with the appropriate key **while preserving signature/format constraints**, and must not treat decrypted plaintext as trusted evidence without verifying the entire assertion.

### 5.2. `SubjectConfirmation`: Proving the Assertion Is Presented Properly

`SubjectConfirmation` specifies the **subject confirmation method**. In SAML2 Web Browser SSO, the method is usually:

~~~text
urn:oasis:names:tc:SAML:2.0:cm:bearer
~~~

**Bearer** here does not mean “anyone holding the XML is allowed to use it anywhere.” The SP must verify that the assertion is valid, was issued for this SP, is still within its validity window, is presented by the party submitting the response via a compliant binding, and is not replayed.

`SubjectConfirmationData` typically contains:

- **`Recipient`**: where the assertion may be presented for acceptance, usually the SP's **ACS endpoint**.
- **`InResponseTo`**: links to the `AuthnRequest` created by the SP, especially in SP-initiated SSO.
- **`NotOnOrAfter`**: acceptance deadline for **subject confirmation**, usually short; distinct from the IdP session's `SessionNotOnOrAfter`.
- **`NotBefore` or `Address`** if present per method/profile: understand the corresponding rules; do not assume every system sends these fields.

An Assertion may contain multiple `SubjectConfirmation` elements. The verifier must process according to the profile and ensure an **appropriate confirmation method/branch** is actually valid; it must not arbitrarily read the first element and conclude success.

### 5.3. Four Easily Confused Values

| Attribute/element | Binding target | Value in example |
| --- | --- | --- |
| `Response.Destination` | **ACS URL receiving the Response** | `https://sp.example.org/login/saml2/sso/partner` |
| `SubjectConfirmationData.Recipient` | **URL where the bearer assertion is presented** | `https://sp.example.org/login/saml2/sso/partner` |
| `Conditions.AudienceRestriction.Audience` | **SP entity ID**, identifying the entity permitted to use the assertion | `https://sp.example.org/saml2/service-provider-metadata/partner` |
| `InResponseTo` (Response/SubjectConfirmationData) | **ID of the AuthnRequest being answered** | `_req-48f` |

Depending on configuration, **Destination and Recipient often match the ACS**, while **Audience is the entity ID**, usually a different URL. Do not use the IdP's URL for Audience. `InResponseTo` is an **ID**, not a URL.

## 6. Complete XML Example to Trace

Assume the SP has:

- **SP entity ID**: `https://sp.example.org/saml2/service-provider-metadata/partner`.
- **ACS**: `https://sp.example.org/login/saml2/sso/partner`.
- **IdP entity ID**: `https://idp.partner.example.org/saml`.
- **AuthnRequest ID** just sent: `_req-48f`.
- **User**: `partner-user-073`.

This example **intentionally omits a digital signature**, and the dates and IDs are solely for studying structure. **Even though the XML is well-formed, a secure SP must reject using this illustration for authentication**; a valid real-world SAML Response requires a configured IdP and signatures/bindings/conditions satisfying the profile.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp-4ac"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:00Z"
    Destination="https://sp.example.org/login/saml2/sso/partner"
    InResponseTo="_req-48f">

    <saml:Issuer>https://idp.partner.example.org/saml</saml:Issuer>

    <!-- Illustration: omitting actual ds:Signature. DO NOT USE to log in. -->

    <samlp:Status>
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>

    <saml:Assertion
        ID="_assert-9d1"
        Version="2.0"
        IssueInstant="2030-05-01T10:00:00Z">

        <saml:Issuer>https://idp.partner.example.org/saml</saml:Issuer>

        <!-- If Assertion is signed, ds:Signature sits in the schema-valid position. -->

        <saml:Subject>
            <saml:NameID
                Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
                partner-user-073
            </saml:NameID>
            <saml:SubjectConfirmation
                Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
                <saml:SubjectConfirmationData
                    InResponseTo="_req-48f"
                    Recipient="https://sp.example.org/login/saml2/sso/partner"
                    NotOnOrAfter="2030-05-01T10:05:00Z"/>
            </saml:SubjectConfirmation>
        </saml:Subject>

        <saml:Conditions
            NotBefore="2030-05-01T09:59:00Z"
            NotOnOrAfter="2030-05-01T10:05:00Z">
            <saml:AudienceRestriction>
                <saml:Audience>https://sp.example.org/saml2/service-provider-metadata/partner</saml:Audience>
            </saml:AudienceRestriction>
        </saml:Conditions>

        <saml:AuthnStatement
            AuthnInstant="2030-05-01T09:58:30Z"
            SessionIndex="_idp-session-28"
            SessionNotOnOrAfter="2030-05-01T18:00:00Z">
            <saml:AuthnContext>
                <saml:AuthnContextClassRef>
                    urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
                </saml:AuthnContextClassRef>
            </saml:AuthnContext>
        </saml:AuthnStatement>

        <saml:AttributeStatement>
            <saml:Attribute Name="department">
                <saml:AttributeValue>engineering</saml:AttributeValue>
            </saml:Attribute>
            <saml:Attribute Name="groups">
                <saml:AttributeValue>partner-readers</saml:AttributeValue>
                <saml:AttributeValue>partner-auditors</saml:AttributeValue>
            </saml:Attribute>
        </saml:AttributeStatement>
    </saml:Assertion>
</samlp:Response>
~~~

### 6.1. Reading the Example Through a Series of Questions

**(a) Who issued it?** Both illustrative `Issuer` elements have the same entity ID `https://idp.partner.example.org/saml`. The SP still must match against a trusted IdP and **verify the signature**; looking at the text string is not enough.

**(b) Which request does the message belong to?** `Response.InResponseTo` and `SubjectConfirmationData.InResponseTo` are both `_req-48f`. The SP must still hold matching AuthnRequest state; a syntactically valid ID without a corresponding request is grounds for rejection in an SP-initiated flow.

**(c) Where is it returned?** `Response.Destination` and `Recipient` point to the SP's ACS. If the response is POSTed to a different ACS or has a URL contradicting configuration, that indicates a destination binding failure.

**(d) Which SP is it for?** `Audience` is the SP entity ID. This check prevents using an assertion issued for application X to log into application Y.

**(e) Who is the subject?** `NameID=partner-user-073` with format `persistent`. This is the identifier asserted by the IdP, not automatically a local username or permission. The SP needs to link it to a local account using an appropriate key and workflow.

**(f) Until when is it valid?** Both `Conditions.NotOnOrAfter` and `SubjectConfirmationData.NotOnOrAfter` are `10:05:00Z` in the example; both must pass separate checks. `SessionNotOnOrAfter=18:00:00Z` is the reported IdP session context deadline, **not an extension of assertion acceptance validity**.

**(g) When did authentication happen?** `AuthnInstant=09:58:30Z` can precede `IssueInstant=10:00:00Z`: the IdP authenticated the user earlier and later issued the assertion (possibly based on an SSO session). The two timestamps have different meanings.

**(h) Which attributes are declared?** `groups` has **two values**. Do not treat `partner-readers` as an internal permission without a trusted mapping. An SP may allow login yet deny calling business APIs when permissions are lacking.

## 7. Message Lifecycle: From AuthnRequest to SP Session

~~~text
User                SP (Spring Security)              IdP
    |                        |                          |
    |-- GET /private ------->|                          |
    |<-- redirect AuthnRequest -------------------------|
    |----------------- send AuthnRequest -------------->|
    |                        |            check session/login
    |<------------- page/HTML POST with SAMLResponse ---|
    |-- POST SAMLResponse -->| ACS                      |
    |                        |-- parse + verify sig     |
    |                        |-- validate Status/Issuer |
    |                        |-- validate assertion     |
    |                        |-- validate Subject       |
    |                        |-- map principal/roles    |
    |<--- SP session cookie -|                          |
    |-- GET /private ------->| authorize at SP          |
~~~

In **SP-initiated SSO**, the SP creates the `AuthnRequest` and records its ID/registration to correlate the response. In **IdP-initiated/unsolicited SSO**, there may be no corresponding `AuthnRequest`; supporting or rejecting this mode is a policy/profile choice of the SP and library. Do not relax SP-initiated `InResponseTo` checks just to “fix” integration errors.

### SAML Binding: HTTP Layer, Not XML Layer

- **HTTP-Redirect Binding** is commonly used to carry `AuthnRequest` from SP to IdP via URL; request representation/signing mechanisms follow specific rules.
- **HTTP-POST Binding** is commonly used to return `Response` from IdP to ACS using a form with a `SAMLResponse` field containing **Base64-encoded XML**.
- **`RelayState`** is state data passed across the binding, **not** an `Assertion` element and not proof of identity. It must be bound to the appropriate request, avoiding turning `RelayState` into an arbitrary redirect URL.
- After a successful POST, **the SP creates its own session**; the XML assertion and the SP session cookie are not the same thing.

A Base64-encoded message **does not hide its contents**, especially if form values are logged. Do not log raw SAMLResponse, assertions, or sensitive NameIDs in production logs; use HTTPS and appropriate data retention policies.

## 8. Easily Misunderstood Timestamps and IDs

| Value | Where it originates | What it is used for |
| --- | --- | --- |
| `AuthnRequest.ID` | SP when requesting login | Request-response correlation key. |
| `Response.ID` | IdP when issuing response | Identifies the returned message, used for replay/correlation control. |
| `Assertion.ID` | IdP when issuing assertion | Identifies the assertion; audit/anti-replay per profile. |
| `Response.InResponseTo` | IdP copied from request | Indicates which SP request the response answers. |
| `SubjectConfirmationData.InResponseTo` | IdP inside bearer assertion | Ties permission to present the assertion to a specific SP request. |
| `Response.IssueInstant` | IdP when issuing response | Time the response was created. |
| `Assertion.IssueInstant` | IdP when issuing assertion | Time the assertion was created (may differ from response). |
| `AuthnStatement.AuthnInstant` | IdP recorded when user authenticated | May be older than IssueInstant due to SSO session reuse. |
| `Conditions.NotOnOrAfter` | IdP for assertion | Assertion validity deadline per Conditions. |
| `SubjectConfirmationData.NotOnOrAfter` | IdP for bearer confirmation | Deadline to present the assertion per confirmation method. |
| `AuthnStatement.SessionNotOnOrAfter` | IdP if sent | Time limit of the reported authentication session; not a TTL for every application. |
| `AuthnStatement.SessionIndex` | IdP if sent | IdP session identifier/handle, useful in some SAML Single Logout flows. |

The first three IDs **do not need to be equal**; each has a distinct role. `InResponseTo` usually points to **AuthnRequest.ID**, not to Response.ID or Assertion.ID. In multi-IdP/tenant environments, you must preserve the **AuthnRequest ↔ registration/IdP ↔ ACS** mapping to prevent responses from being submitted into another context.

If an SP accepts an Assertion whose `NotOnOrAfter` has passed merely because `SessionNotOnOrAfter` is still far in the future, the SP has **read the wrong time object**. An assertion valid at login time does not automatically mean every application session must be capped at the exact same timestamp; a separate session policy is needed.

## 9. Security Checks When the SP Receives `Response`

**Do not hand-roll a SAML verifier by manually parsing XML and comparing a few strings.** The SP needs a vetted SAML2 library, accurate metadata/trust keys, and matching policies. Exact sequencing may vary across library versions, but security requires ensuring all of the following conditions:

1. **Select the right registration:** Identify the trusted RP–IdP pair; IdP issuer, binding, ACS, entity ID, and credentials must match configuration.
2. **Parse XML safely:** Defend against XXE/entity expansion, enforce size and depth limits; avoid processing payloads with duplicate/parser-confusing elements.
3. **Verify signatures on the right target:** Verify XML Digital Signature with a certificate/key trusted via metadata/configuration, check signed ID references; prevent **XML Signature Wrapping**, where the program reads an Assertion other than the signed Assertion.
4. **Handle encryption safely:** If `EncryptedAssertion`/`EncryptedID`/`EncryptedAttribute` appears, decrypt using a valid SP key while preserving verification requirements.
5. **Check the Response layer:** Appropriate `Status`; issuer, `Destination`, `InResponseTo`, version, time, and binding per profile/registration.
6. **Check the Assertion layer:** issuer, signature and signed scope, `Conditions`, `AudienceRestriction`, other required conditions, and Assertion count/placement per policy.
7. **Check the Subject layer:** `NameID` matching format/agreement, appropriate `bearer` method, `SubjectConfirmationData.Recipient` matching ACS, `InResponseTo` matching the request, validity window active.
8. **Prevent replay:** An accepted assertion/response should not be reusable to mint unlimited sessions; maintain an ID/nonce/request-state cache when required by profile and aligned with lifetime.
9. **Only upon successful verification:** Create `Authentication`/principal, link the local account, and enforce authorization in the application. An IdP claim `group=admin` does not inherently mean `ROLE_ADMIN` in the SP.
10. **Do not weaken policy on errors:** Clock skew, stale metadata, wrong ACS, or an IdP not signing properly must be fixed by adjusting configuration/syncing per profile, **never by disabling signature/audience/recipient checks**.

### 9.1. Distinguishing Digital Signing from Encryption

| Feature | What does it solve? | What does it not solve? |
| --- | --- | --- |
| XML Digital Signature (`ds:Signature`) | Verifies signer origin and integrity of the **signed XML element** via a trusted key. | Does not keep data confidential; does not by itself prove targets outside the valid signed scope. |
| XML Encryption (`EncryptedAssertion`/`EncryptedID`) | Keeps content confidential from parties without the decryption key. | Does not by itself prove issuer identity and assertion integrity per profile. |
| HTTPS | Protects the transport channel between browser and endpoint. | Does not replace SAML signatures in a model where responses transit via the browser. |
| Base64 in HTTP-POST | Encodes XML into a string suitable for form submission. | Not security encryption, not origin authentication, not replay protection. |

A response may have a **Signature on the Response**, a **Signature on each Assertion**, both, or a combination with encryption. Do not impose a “must sign both” rule on every IdP if the profile/metadata allows one specific option; however, always ensure that **every assertion used for authentication is protected by a valid signature** per policy. Under Spring Security's validation model, lacking both a Response signature and Assertion signatures is unacceptable.

### 9.2. Multiple Assertions and XML Signature Wrapping

A SAML Response can contain multiple Assertions; the elements that are signed and the elements the application **reads** must be the exact same verified content. If a system merely looks up `//Assertion[1]/Subject/NameID` with custom XPath, an attacker could inject an unprotected assertion into that slot while the signature still matches another assertion. This is the **XML Signature Wrapping** risk pattern.

The defense is to use a dedicated SAML verifier adhering to ID uniqueness rules, signature references, and assertion selection policies; do not build a second parser to extract claims after the library has validated a different object.

## 10. How Spring Security SAML2 Processes a Response

With Spring Security Servlet/SAML2 Login, the application acts as the **SP/Relying Party**. Typical components:

| Spring Security component | Role |
| --- | --- |
| `RelyingPartyRegistration` | Configures the SP–IdP relationship: entity IDs, ACS, metadata, credentials, and bindings. |
| `Saml2WebSsoAuthenticationRequestFilter` | Creates/sends `AuthnRequest` to the IdP when initiating login. |
| `Saml2WebSsoAuthenticationFilter` | Receives `SAMLResponse` via ACS and delegates to the authentication provider. |
| `Saml2AuthenticationToken` | Authentication input containing the SAML response and associated registration. |
| OpenSAML authentication provider | Parses, verifies signatures, decrypts, and validates SAML conditions according to version/configuration. |
| `Saml2AuthenticatedPrincipal` | Principal received by the application after authentication, containing name/attributes and registration info. |
| `Saml2Authentication` | Authentication result placed into the security context; authorization is enforced afterward. |

Exact names/versions of the OpenSAML provider vary by Spring Security release; applications usually configure via `saml2Login` rather than instantiating providers directly. The sample below targets **Java 17 and Spring Boot 3.3.x / Spring Security 6.x**.

### 10.1. Minimal SP Application Example

Project structure:

~~~text
saml-structure-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/samlstructure/
    │   ├── SamlStructureApplication.java
    │   ├── SecurityConfig.java
    │   └── PrincipalController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-structure-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    // OpenSAML artifacts are published by the Shibboleth ecosystem.
    maven {
        url 'https://build.shibboleth.net/maven/releases/'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Use a Spring Boot/Gradle version suitable for your environment; the Shibboleth repository is used per Spring Security's dependency guide. There is no need to parse XML manually with `DocumentBuilder` to perform login.

`src/main/java/com/example/samlstructure/SamlStructureApplication.java`:

~~~java
package com.example.samlstructure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlStructureApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlStructureApplication.class, args);
    }
}
~~~

`src/main/java/com/example/samlstructure/SecurityConfig.java`:

~~~java
package com.example.samlstructure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

`saml2Login` enables SAML2 login handling; `saml2Metadata` supports exporting SP metadata for partner configuration. The `authenticated()` rule only requires login; real business endpoints must enforce permissions/tenant checks in services. Keep CSRF protection and default filters intact; do not disable all verification just to make a test IdP login succeed.

`src/main/java/com/example/samlstructure/PrincipalController.java`:

~~~java
package com.example.samlstructure;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrincipalController {

    @GetMapping("/")
    public String home() {
        return "Visit /me to start SAML 2.0 login";
    }

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("nameId", principal.getName());
        result.put("registrationId",
            principal.getRelyingPartyRegistrationId());
        result.put("department", principal.getFirstAttribute("department"));
        result.put("sessionIndexes", principal.getSessionIndexes());
        return result;
    }
}
~~~

After the authentication processor succeeds, `principal.getName()` typically reflects the **NameID** of the assertion selected by Spring Security; `getFirstAttribute("department")` retrieves the first value of the Attribute in the example. `getSessionIndexes()` may be empty depending on the assertion/IdP. **Do not treat `nameId` or `department` as administrative privileges**. The output printed in the demo is for learning only; restrict or remove debug endpoints in production deployments.

### 10.2. Configuring IdP Metadata

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner:
            assertingparty:
              metadata-uri: ${SAML_IDP_METADATA_URI}
~~~

`SAML_IDP_METADATA_URI` is the **real** metadata URL of the partner IdP that the SP has decided to trust. Metadata usually describes the entity ID, endpoints, certificates, and bindings; the SP must be registered at the IdP with the right entity ID, ACS URL, signing requirements, and policies. URLs in the educational XML section (such as `sp.example.org`) do not represent an immediately log-in-ready IdP.

Common endpoints in the default configuration:

~~~text
Initiate SP-initiated SSO:  GET /saml2/authenticate/partner
ACS receives SAMLResponse:  POST /login/saml2/sso/partner
Export SP metadata:         GET /saml2/metadata/partner
~~~

In real deployments, reverse proxy settings, `{baseUrl}`, HTTPS, and certificates/metadata must match the SP's public URL. The demo application itself **does not create an IdP** and does not issue SAML signatures on its own.

### 10.3. Running the Demo and Understanding the Output

If the machine already has a suitable Gradle installation or the project has a valid Gradle Wrapper:

~~~bash
gradle bootRun
~~~

With a real IdP configured and working network/metadata environment:

1. Open `http://localhost:8080/` and receive the public instruction string.
2. Open `http://localhost:8080/me` while unauthenticated; Spring Security initiates SAML2 login with the registered IdP.
3. The IdP authenticates the user and sends a SAMLResponse via HTTP-POST to the ACS. Spring Security/OpenSAML verifies the response and assertion.
4. After valid authentication, `/me` displays JSON containing `nameId`, `registrationId`, `department`, and `sessionIndexes`. These values **depend on the IdP**; there is no fixed JSON output.
5. If metadata/certificate/ACS are not configured properly, the application may fail to start or login will fail. Errors cannot be fixed by copying the unsigned XML in section 6 into a POST.

**Only inspect structure with the XML in section 6** visually or with a local XML viewer. **Do not** POST the unsigned example as a “valid” SAMLResponse and do not claim it has been authenticated.

### 10.4. Boundary Between Validation and Authorization in Spring

Spring Security turns a SAML Response into a principal **after** the verification steps finish. Yet the IdP asserting `NameID=partner-user-073` only answers who the IdP authenticated; the SP decides:

- Which local account this person links to and which partner/tenant they belong to?
- Whether the local account is active or blocked?
- Whether this person has `APP_ORDER_READ` or other permissions?
- Whether the request targets a resource belonging to an allowed partner?

A secure design can use a link key **(IdP entity ID, NameID + format/qualifiers per contract)** to look up the account. Do not assign `ROLE_ADMIN` just because an Attribute named `groups` contains the word `admin`. Authorization should live in a separate layer tested independently of SAML parsing.

## 11. Common Mistakes When Reading Response, Assertion, and Subject

| Misunderstanding/implementation bug | Why it is wrong | How to fix |
| --- | --- | --- |
| “`SAMLResponse` is encrypted XML so it can be trusted.” | Base64 only transforms string representation. | Decode via a SAML library and verify signatures/conditions. |
| Checking only `Status=Success` and allowing login. | Status is only the protocol processing state. | Verify Assertion, Subject, conditions, and signature. |
| Comparing `Response.ID` with `InResponseTo`. | The two IDs have different roles. | `InResponseTo` must be matched against `AuthnRequest.ID`. |
| Treating `Destination`, `Recipient`, and `Audience` as the same URL. | The first two are usually the ACS; Audience is the SP entity ID. | Bind each value against its own configuration source. |
| Using `AuthnInstant` to infer Assertion expiration. | Authentication time is not bearer assertion expiration. | Check `Conditions` and `SubjectConfirmationData`. |
| Treating `SessionNotOnOrAfter` as the assertion expiry. | That is IdP session information. | Separate session lifetime from assertion acceptance window. |
| Accepting `NameID=email` as an immutable local user key. | Emails change/recycle; identifiers depend on format and IdP. | Design identity linking around issuer/nameID/qualifier. |
| Manually XPath-querying the “first Assertion” before signature verification. | May consume an assertion other than the signed one. | Use OpenSAML/Spring Security to prevent signature wrapping. |
| Trusting a certificate merely because it sits in `ds:KeyInfo`. | A sender can embed its own key. | Anchor trust in configured trusted metadata/certificates. |
| Allowing unlimited replay within a 5-minute window. | Time validity does not enforce one-time use. | Request correlation and ID/replay caching per profile/policy. |
| Ignoring multiple `AttributeValue` entries of an attribute. | SAML allows multi-valued attributes. | Use lists and appropriate mapping rules. |
| Treating an external group directly as a local permission. | The IdP is authoritative on identity/claims per contract, not automatically on business permissions. | Apply least-privilege mapping and ownership/tenant checks. |
| Disabling issuer/recipient checks when reverse proxy is misconfigured. | Masks a config bug into a wrong-target auth risk. | Fix base URL, ACS, metadata, and forwarded headers. |
| Ignoring `EncryptedAssertion` because plain XML cannot be read. | Assertions can be encrypted and need the SP's decryption key. | Configure decryption credentials and use a standard SAML provider. |

## 12. Practice Exercises: Analyzing and Cross-Checking a Response

Use the illustrative XML in section 6. No real IdP is needed for **structural reading** questions; to test Spring Security accepting a login, you need a real signed payload and a properly configured integration environment.

### Exercise A — Read the Relationships

1. Identify the **two issuers** and where they appear.
2. Identify the **Response ID**, **Assertion ID**, and **answered AuthnRequest ID**.
3. Point out the three values **Destination**, **Recipient**, and **Audience**, and explain why Audience differs from the ACS URL.
4. Identify **NameID**, **NameID Format**, **bearer confirmation method**, and the bearer validity deadline.
5. Find **AuthnInstant**, **IssueInstant**, and **SessionNotOnOrAfter**; explain why they cannot substitute for one another.
6. Name the **two values** of the `groups` Attribute and state why they are not automatically SP permissions.

### Exercise B — Single-Field Modification Scenarios

| Variation from a validly signed Response | What must happen at the SP |
| --- | --- |
| `Recipient` points to another ACS. | Reject because bearer confirmation is not for the current ACS. |
| `Audience` is the entity ID of another SP. | Reject the assertion because it is not intended for this SP. |
| `InResponseTo` points to a non-existent request ID in an SP-initiated flow. | Reject due to correlation failure. |
| `Conditions.NotOnOrAfter` has passed. | Reject the expired assertion. |
| `NameID` changes after the response was signed. | Signature/protected scope is no longer valid; reject. |
| `Status` reports `AuthnFailed`. | Do not create a logged-in session. |
| An already accepted response is submitted again. | Blocked by replay/request-state policy; do not create sessions arbitrarily. |
| `groups=admin` is present, but the local user lacks permission. | Authentication may succeed, but admin endpoints must return 403. |

### Exercise C — Short Self-Check Answers

**Question 1.** “If an Assertion has valid `Conditions`, can a login succeed when `SubjectConfirmationData.NotOnOrAfter` has expired?”  
**Answer:** No. Applicable checks must **simultaneously** pass; `Conditions` validity does not extend bearer confirmation.

**Question 2.** “Can a signature be verified using any key embedded directly inside the XML?”  
**Answer:** No. The signing key must chain to a **trust anchor/IdP metadata** configured by the SP; partner-sent XML does not self-declare who is trusted.

**Question 3.** “Is a `<saml:Subject>` name sufficient to prove that person may access the admin page?”  
**Answer:** No. Subject is an identifier in the assertion; local permissions are decided by the SP after account linking and policy checks.

**Question 4.** “Why can `AuthnInstant` be earlier than `Response.IssueInstant`?”  
**Answer:** The IdP may have authenticated the user earlier and reused an SSO session to issue a new Response.

**Question 5.** “Why must `Assertion.ID`, `Response.ID`, and `AuthnRequest.ID` be distinguished?”  
**Answer:** The three IDs identify **three different objects**. `InResponseTo` is the reply relationship referencing the **request ID**, whereas assertion/response IDs serve separate identification and control purposes.

## 13. Key Takeaways and Checklist Before Accepting SAML2 Login

- **Response** is the protocol envelope: issuer, destination, request correlation, status.
- **Assertion** carries the IdP's statements: subject, conditions, authentication event, and attributes.
- **Subject** identifies the asserted person: NameID and presentation method/conditions.
- **Recipient/Destination are the ACS target**, while **Audience is the SP entity ID**; `InResponseTo` points to AuthnRequest.
- **Conditions**, **SubjectConfirmationData**, and **AuthnStatement** describe different kinds of timestamps.
- **XML signature + trusted key + profile conditions + anti-replay** are mandatory security gates before creating a principal.
- **Spring Security/OpenSAML** performs protocol verification; the **application** handles local account linking and business authorization.
- Unsigned illustrative XML is **for study only**: it cannot prove a real login was authenticated.

### References

- [OASIS — Assertions and Protocols for SAML V2.0 (SAML Core)](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) — structure of Response, Assertion, Subject, Conditions, statements.
- [OASIS — Profiles for SAML V2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf) — Web Browser SSO rules, bearer subject confirmation, bindings/correlation.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — filters and RP components.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) — verifying response/assertion and principal.
- [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — SP/IdP metadata configuration.

# Separating entityId, ACS, Keys, and Attribute Policies per Partner in Spring Security SAML 2.0

## 1. Objectives and Real-World Scenario

A Spring Boot application may serve **multiple enterprises, tenants, or partners** while letting each partner's users log in through their own **Identity Provider (IdP)**. In SAML 2.0, the application acts as the **Service Provider (SP / Relying Party)**; the IdP acts as the **Asserting Party**. For example:

- Partner **Alpha** uses `https://alpha-idp.example.test/issuer` and requires its own SP Entity ID, ACS, Alpha signing certificate, and attributes `employeeId`, `groups`.
- Partner **Beta** uses `https://beta-idp.example.test/issuer` and requires a different SP Entity ID/ACS, separate SP keys, and attributes `uid`, `entitlements`.
- Both are served by **the same Java codebase, same application database, and same web UI**.

The problem goes beyond "adding two SSO routes." If the system mixes up **issuer, audience, ACS, certificate, signing/decryption key, or attribute-mapping rules** between partners, Beta users could be recognized as Alpha users, one IdP's certificate could be used to trust another IdP's response, or a self-asserted group could turn into admin privileges in another tenant.

This lesson belongs to **Multiple IdPs and Tenants** and focuses on these objectives:

1. Understand **`RelyingPartyRegistration` as an SP–IdP relationship**, typically bound to a dedicated `registrationId`.
2. Separate **SP `entityId`**, **ACS (Assertion Consumer Service)**, SP keys, and IdP verification keys **per partner**; know what *may* be intentionally shared.
3. Select a registration when generating AuthnRequests and receiving SAML Responses **without treating URLs, `RelayState`, or an unverified Issuer as proof of trust**.
4. Validate the response with the right IdP certificate, verify Audience/Recipient/Destination/`InResponseTo`, and only then apply **NameID, attribute, group, role, and tenant** policies.
5. Design identity linking, JIT provisioning, key rotation, and multi-tenant authorization without introducing cross-tenant flaws.
6. Test **cross-partner confusion** scenarios and diagnose misconfigured ACS/certificate/attribute policies.

**Principle:** for every response, one **trusted registration must be selected accurately**. The system must never treat "IdP A signed validly" as a reason to accept a response meant for SP B, nor use unvalidated user attributes to select a trust configuration.

## 2. Four Layers to Separate per Partner

A clear conceptual model:

~~~text
                 Java / Spring Security App
                             |
                RelyingPartyRegistrationRepository
                             |
                 +-----------+------------+
                 |                        |
       registrationId="alpha"    registrationId="beta"
                 |                        |
        SP Entity ID Alpha        SP Entity ID Beta
        ACS Alpha                 ACS Beta
        SP signing key Alpha      SP signing key Beta
        SP decryption key Alpha   SP decryption key Beta
        IdP issuer Alpha          IdP issuer Beta
        IdP verification Alpha    IdP verification Beta
        Attribute policy Alpha    Attribute policy Beta
        Tenant = A                Tenant = B
                 |                        |
            IdP Alpha                 IdP Beta
                 |                        |
                 +---------> local user / permissions
                               scoped by tenant
~~~

In Spring Security, **one `RelyingPartyRegistration` describes a relying party and asserting party pair**. `registrationId` is the internal identifier distinguishing configurations. Spring Security documentation supports multi-tenancy by registering multiple `RelyingPartyRegistration` instances in a `RelyingPartyRegistrationRepository`.

**Important:** each IdP is not strictly forced to use a **different SP Entity ID, ACS, or private key** in every design. Spring Security documents scenarios where multiple registrations **share an entityId, ACS, or credential**. However, **when the goal is per-partner isolation**, choose a policy that clearly separates components carrying risk or independent lifecycles. Whenever sharing a component, document **why sharing is permitted and how control boundaries remain intact**.

### 2.1. Policy Matrix

| Component | Alpha | Beta | Mandatory Constraint |
| --- | --- | --- | --- |
| `registrationId` | `alpha` | `beta` | **Unique** in the repository |
| Internal tenant | `tenant-a` | `tenant-b` | Never take tenant directly from unverified claims |
| SP `entityId` | `urn:portal:sp:alpha` | `urn:portal:sp:beta` | Must match Audience/SP registered at the IdP |
| ACS URL | `https://portal.example.test/login/saml2/sso/alpha` | `https://portal.example.test/login/saml2/sso/beta` | Matches filter, Recipient/Destination, and IdP config |
| IdP `entityId` | `https://alpha-idp.example.test/issuer` | `https://beta-idp.example.test/issuer` | Issuer and trust policy must match |
| SP signing key | `alpha-sp-sign` | `beta-sp-sign` | SP private keys must not be mixed or exposed to IdPs |
| SP decryption key | `alpha-sp-decrypt` | `beta-sp-decrypt` | Decrypt only using the registration's authorized key ring |
| IdP verification cert | `alpha-idp-signing` | `beta-idp-signing` | Trust only the issued/registered public cert of that IdP |
| Stable subject attr | `employeeId` | `uid` | Verified under the right policy |
| Group attr | `groups` | `entitlements` | Never turn raw group values directly into authorities |
| Role mapping | `engineers -> ROLE_ALPHA_EDITOR` | `partner-viewer -> ROLE_BETA_READER` | Per-partner allowlist, tenant business permissions |

This is an **illustrative architectural example**, not a mandatory SAML standard. Replace `example.test` URIs/URNs and key aliases with values **agreed upon** in your real system.

## 3. `registrationId`, SP `entityId`, and IdP `entityId` Are Three Different Concepts

### 3.1. `registrationId` Is a Local Key

Spring Security uses `registrationId` to look up a `RelyingPartyRegistration`. For instance, `alpha` typically appears in:

~~~text
/saml2/authenticate/alpha
/login/saml2/sso/alpha
/saml2/metadata/alpha
~~~

`alpha` is only an **application-chosen name**. Do not assume this name is itself a tenant ID, IdP Entity ID, or SAML issuer. It merely points to an admin-managed configuration carrying a **trusted tenant mapping**.

### 3.2. SP `entityId` Is the Recipient Identifier

In an AuthnRequest, `<saml:Issuer>` typically carries the **SP `entityId`**. In an Assertion from the IdP, `AudienceRestriction/Audience` must match the SP for which the assertion was issued.

Example:

~~~text
Alpha SP Entity ID = urn:portal:sp:alpha
Beta SP Entity ID  = urn:portal:sp:beta
~~~

An assertion with `Audience=urn:portal:sp:alpha` **must not** be carried over to registration Beta merely because a user ID or email matches. Audience is one of the defenses answering "whom was this assertion issued for?"

### 3.3. IdP `entityId` Is the Issuer Identifier

~~~text
Alpha IdP Entity ID = https://alpha-idp.example.test/issuer
Beta IdP Entity ID  = https://beta-idp.example.test/issuer
~~~

The IdP `entityId` normally appears in `<saml:Issuer>` of the Response/Assertion. **Do not use email domains or ACS URLs to guess a trusted IdP.** The Issuer must match the registration and **the signature must be valid under that exact IdP's certificate**. Unverified XML Issuer text may serve only as a lookup hint, never to expand the list of permitted certificates.

### 3.4. One Entity May Have Multiple Tenants

Some partners use **one IdP Entity ID for multiple tenants** or sub-applications within the same organization. In that case, inspecting the issuer alone is **insufficient** to distinguish tenants. You need SP-initiated request state, protected routes/context, or an explicitly designed registration resolver. If the registration cannot be disambiguated unambiguously, **reject** rather than picking the first tenant.

## 4. ACS: Separate URLs or Shared?

The **Assertion Consumer Service (ACS)** is the SP-side endpoint that receives the **SAML Response** after the IdP authenticates the user. It differs from the **IdP's SingleSignOnService**, where the SP sends AuthnRequests.

In Spring Security Servlet, the standard processing path is:

~~~text
POST /login/saml2/sso/{registrationId}
~~~

When separated per partner:

~~~text
POST /login/saml2/sso/alpha
POST /login/saml2/sso/beta
~~~

Benefits:

- Easy to tell which callback is expected to serve which registration.
- Easy to publish separate SP metadata per partner.
- Reduces the chance of misconfiguring the ACS in the IdP portal.
- Enables observing errors, latency, and volume per registration.
- Compatible with Spring Security's path-based and request-state registration selection.

**However, a path containing `alpha` is not proof of valid SAML.** An attacker can still POST an arbitrary `SAMLResponse` to `/alpha`. Spring Security must verify signature, issuer, audience, destination, recipient, timestamps, correlation, and other conditions **before creating an `Authentication`**.

### 4.1. When Using a Shared ACS

A shared ACS can also be valid:

~~~text
POST /login/saml2/sso
~~~

In that case you need a reliable way to choose the right `RelyingPartyRegistration`, such as **saved AuthnRequest and `InResponseTo`**, or a custom converter/resolver with explicit rules. Spring Security docs note that when receiving a SAML Response, the converter can resolve the registration from the associated AuthnRequest, from `registrationId` in the URL, or from `Response/Issuer` when prior context is absent.

**Trust-bootstrap warning:** if selection depends on Issuer before signature verification, treat Issuer solely as **a candidate lookup value**. You must then verify the signature with **the candidate's IdP verification credential** and re-check every field—never trust Issuer alone.

With **multiple tenants sharing one IdP issuer**, relying on issuer alone is ambiguous; you need a stronger correlation source. If the SAML Response is **IdP-initiated/unsolicited**, `InResponseTo` is typically absent; establish an **explicit allow/deny policy** and a safe resolution mechanism.

### 4.2. Custom `loginProcessingUrl` Must Match Published ACS

Spring Security provides the DSL:

~~~java
http.saml2Login(saml2 -> saml2
    .loginProcessingUrl("/saml/acs/{registrationId}"));
~~~

This is a **configuration snippet**, not a standalone Java file. If you change the filter processing path, update **`assertionConsumerServiceLocation`** and SP metadata to match; never change only one side.

If the app publishes:

~~~text
https://portal.example.test/saml/acs/alpha
~~~

yet the IdP sends to:

~~~text
https://portal.example.test/login/saml2/sso/alpha
~~~

errors can appear as HTTP 404, the filter not matching, or `Destination/Recipient` mismatch. Fix the **URL contract between SP and IdP**; never disable Destination checks.

### 4.3. Reverse Proxies and Host-Based Tenants

When running behind a proxy, Spring Security can derive `{baseUrl}` from the request. If the proxy passes an internal host or misconfigured `http` scheme, metadata/ACS will be wrong.

Trust only **forwarded headers from a controlled reverse proxy**; never let client-supplied HTTP `Host` or `X-Forwarded-Host` arbitrarily alter ACS/Entity IDs. Preferably use fixed public URLs or an approved trusted base-URL mechanism, and verify the live metadata after deployment.

## 5. One Registration per Partner in Spring Security

A `RelyingPartyRegistration` contains two groups of settings:

~~~text
RelyingPartyRegistration("alpha")
   Relying Party (SP):
       entityId
       assertionConsumerServiceLocation
       signingX509Credentials
       decryptionX509Credentials

   Asserting Party (IdP):
       entityId
       singleSignOnServiceLocation + binding
       verificationX509Credentials
       wantAuthnRequestsSigned
       metadata / encryption preferences
~~~

`InMemoryRelyingPartyRegistrationRepository` can hold multiple registrations. Larger projects may use a repository backed by a database, cache, or managed metadata provider. Crucially, **looking up by `registrationId` must return the exact SP–IdP pair's configuration**, never merging all IdP certificates into an unscoped "global verification list."

### 5.1. Spring Boot YAML Sample for Two Partners

Example for Spring Boot 3.x/Spring Security SAML2 Servlet, with private keys mounted securely from the filesystem. This is **illustrative integration config**; SSO cannot run without real certificates, metadata, and IdPs.

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          alpha:
            entity-id: "urn:portal:sp:alpha"
            acs:
              location: "https://portal.example.test/login/saml2/sso/alpha"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/alpha-sign.pem"
                  certificate-location: "file:/etc/saml/alpha-sign.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/alpha-dec.pem"
                  certificate-location: "file:/etc/saml/alpha-dec.crt"
            assertingparty:
              metadata-uri: "file:/etc/saml/idp-alpha.xml"

          beta:
            entity-id: "urn:portal:sp:beta"
            acs:
              location: "https://portal.example.test/login/saml2/sso/beta"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/beta-sign.pem"
                  certificate-location: "file:/etc/saml/beta-sign.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/beta-dec.pem"
                  certificate-location: "file:/etc/saml/beta-dec.crt"
            assertingparty:
              metadata-uri: "file:/etc/saml/idp-beta.xml"
~~~

**Layer-by-layer explanation:**

1. `registration.alpha` and `registration.beta` establish two distinct SP–IdP relationships.
2. The SP's `entity-id` is the Audience the SP expects per the partner's setup, not the IdP Entity ID.
3. `acs.location` is the SP callback for **SAML Responses**; distinct from the IdP SSO URL inside metadata.
4. **`signing.credentials`** is the **SP's** private key + X.509 certificate pair used to sign AuthnRequests or other SAML messages when required.
5. **`decryption.credentials`** is the **SP's** private key + certificate pair used to decrypt `EncryptedAssertion`s encrypted by the IdP with the SP's public cert.
6. `assertingparty.metadata-uri` points to that specific partner's **IdP** metadata, containing IdP issuer, SSO endpoints, and verification keys; even local file sources still require **trust/onboarding and refresh workflows**.
7. `alpha-sign.pem`/`beta-sign.pem` in the example **are not pre-existing keys**; private keys must be provisioned in a secret manager/secure volume per entity/tenant.
8. `file:` paths must exist **inside the JVM/container**. Never bake production private keys into the classpath/JAR/image.

**Version check:** Spring Boot/Spring Security may rename APIs/properties across branches. Verify `spring.security.saml2.relyingparty.registration.<id>.entity-id`, `acs.location`, `signing.credentials`, `decryption.credentials`, and `assertingparty.metadata-uri` against the configuration metadata of your **running version**.

### 5.2. Manually Separating IdP Verification Certificates

Some partners do not provide a convenient metadata URL. In that case, a registration can declare IdP attributes directly:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          alpha:
            entity-id: "urn:portal:sp:alpha"
            acs:
              location: "https://portal.example.test/login/saml2/sso/alpha"
            assertingparty:
              entity-id: "https://alpha-idp.example.test/issuer"
              singlesignon:
                url: "https://alpha-idp.example.test/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml/idp-alpha-sign.crt"
~~~

This declares the **IdP-side trust source**, not the SP signing credential. If the IdP actually requires signed AuthnRequests, update `sign-request` and provide a valid **SP signing key** rather than blindly copying `false`.

If IdP A and IdP B use different issuers, never copy `idp-alpha-sign.crt` over to Beta just to "make login stop failing." **Certificate verification must stay scoped to the issuer and partner.**

## 6. Java Configuration with `RelyingPartyRegistrationRepository`

For advanced requirements, registrations can be constructed in Java. The example below is **a snippet for inside a Spring Boot configuration class**; `alphaSigningCredential`, `alphaDecryptionCredential`, `betaSigningCredential`, and `betaDecryptionCredential` are already provisioned as `Saml2X509Credential` instances with the right purpose and keys:

~~~java
RelyingPartyRegistration alpha =
    RelyingPartyRegistrations
        .fromMetadataLocation("file:/etc/saml/idp-alpha.xml")
        .registrationId("alpha")
        .entityId("urn:portal:sp:alpha")
        .assertionConsumerServiceLocation(
            "https://portal.example.test/login/saml2/sso/alpha")
        .signingX509Credentials(c -> c.add(alphaSigningCredential))
        .decryptionX509Credentials(c -> c.add(alphaDecryptionCredential))
        .build();

RelyingPartyRegistration beta =
    RelyingPartyRegistrations
        .fromMetadataLocation("file:/etc/saml/idp-beta.xml")
        .registrationId("beta")
        .entityId("urn:portal:sp:beta")
        .assertionConsumerServiceLocation(
            "https://portal.example.test/login/saml2/sso/beta")
        .signingX509Credentials(c -> c.add(betaSigningCredential))
        .decryptionX509Credentials(c -> c.add(betaDecryptionCredential))
        .build();

RelyingPartyRegistrationRepository registrations =
    new InMemoryRelyingPartyRegistrationRepository(alpha, beta);
~~~

**This is a snippet, not a standalone `javac` program.** It needs imports, Spring Security dependencies, credential variables, a repository bean, and a real `SecurityFilterChain`. `fromMetadataLocation` loads metadata yet **does not automatically verify metadata signatures against an independent trust anchor**. If policy requires signed metadata, use a compatible metadata repository/trust engine with pre-provisioned metadata signer keys.

A simple SAML `SecurityFilterChain`:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .saml2Metadata(Customizer.withDefaults());
    return http.build();
}
~~~

This second snippet **belongs in a Spring configuration class** with proper imports and beans; it will not load two IdPs without a repository bean. Spring Boot normally wires the repository bean into the filter chain automatically. When customizing multiple repositories or filter chains, verify **the filter actually uses the right repository** instead of relying on bean names alone.

### 6.1. SP Metadata per Registration

With `saml2Metadata()` in Spring Security, endpoints such as these are available:

~~~text
/saml2/metadata/alpha
/saml2/metadata/beta
/saml2/service-provider-metadata/alpha
/saml2/service-provider-metadata/beta
~~~

Alpha should see **Alpha's SP `entityId`, ACS, and public certificates**, while Beta sees Beta's config. This is onboarding data for the IdP, never secret private keys.

Inspect the actual exported metadata:

- `EntityDescriptor/@entityID` matches the agreed SP Entity ID.
- `AssertionConsumerService/@Location` matches the public HTTPS callback.
- `KeyDescriptor use="signing"` or `use="encryption"` matches the intended purpose and issued certificate.
- Algorithms and bindings are compatible with the IdP.
- Never publish `localhost` URLs, internal IPs, wrong hosts, or another tenant's certificate.

Metadata containing multiple `EntityDescriptor` elements or an aggregated endpoint can also be valid, provided **each partner's onboarding clearly identifies which entity/certificate belongs to them**.

## 7. Selecting Registration When Issuing AuthnRequest

An application-initiated login can proceed as follows:

~~~text
GET /saml2/authenticate/alpha
      |
      v
RelyingPartyRegistrationRepository.findByRegistrationId("alpha")
      |
      +-> SP issuer = urn:portal:sp:alpha
      +-> Destination = SSO URL in IdP Alpha metadata
      +-> ACS = https://portal.example.test/login/saml2/sso/alpha
      +-> Signing key = alpha-sign
      +-> Request ID + RelayState stored per flow
      |
      v
Browser -> IdP Alpha -> SAML Response -> ACS Alpha
~~~

This is **SP-initiated login**, retaining request state to match `InResponseTo` when the IdP responds. For Beta, the corresponding route uses registration `beta` and must never reuse Alpha's request state.

**Never pick a tenant from an unverified email domain** and treat that as trust. Email/tenant hints on a login page can help display options, but the final request must bind to an **allowlisted registration** with state that cannot be swapped across flows by the browser.

### 7.1. IdP-Initiated / Unsolicited Login

An IdP may send a SAML Response to the ACS **without an SP-issued AuthnRequest**. Depending on policy, the SP may accept or reject unsolicited logins.

In multi-tenancy:

- If the ACS includes `registrationId`, that is only a **candidate lookup**.
- If the ACS is shared and two registrations share an issuer, there may be **insufficient information** to choose a tenant safely.
- Define an explicit policy for unsolicited responses: which IdPs are allowed, which ACS, which audience, which recipient, and whether channel binding/hints are required.
- **Never pick a tenant from NameID/email/group** inside an unverified assertion.
- If it cannot be resolved deterministically, **fail closed** and require SP-initiated login.

SP-initiated SSO is usually easier to correlate safely when a product has multiple tenants sharing an issuer. This is not a blanket ban on IdP-initiated SSO; it is a security design decision that must be made deliberately.

## 8. Selecting Registration When Receiving a SAML Response

Spring Security uses `Saml2WebSsoAuthenticationFilter`, `Saml2AuthenticationTokenConverter`, and `OpenSaml5AuthenticationProvider` for the core SAML login pipeline. Spring Security documentation describes resolving `RelyingPartyRegistration` from the associated AuthnRequest, `registrationId` in the URL, or the Issuer in the Response under specific circumstances.

Conceptual verification flow (not a replacement for the framework):

~~~text
1. Browser POSTs SAMLResponse to ACS
2. Locate candidate registration
   - state of issued AuthnRequest, or
   - URL registrationId, or
   - issuer lookup constrained as a policy hint
3. Load IdP verification credentials for the candidate
4. Verify Response/Assertion signature and issuer
5. Verify Audience matches the registration's SP entityId
6. Verify Destination/Recipient matches the permitted ACS
7. Verify InResponseTo and request/session correlation if flow requires
8. Verify timestamps, NotBefore/NotOnOrAfter, Conditions, SubjectConfirmation
9. Enforce replay protection, XML structure checks, and EncryptedAssertion decryption if any
10. Only after PASS: extract verified principal/attributes
11. Apply registration's tenant + subject policy + role mapping
12. Resolve local user/permissions and build Authentication with scoped authorities
~~~

**Never use an unverified `SAMLResponse/Issuer` as the final authority.** The Issuer may appear in an unsigned XML section or be forged by an attacker. Using it to pick a **candidate** is valid only if solely that candidate's certificate is then used and every related claim is verified.

### 8.1. Cross-Partner Confusion

An especially dangerous failure mode:

~~~text
POST /login/saml2/sso/beta
Response.Issuer = https://alpha-idp.example.test/issuer
Response.Audience = urn:portal:sp:alpha
Response.Signature = valid by Alpha IdP key
~~~

**Correct outcome:** **Beta must not authenticate this user.** Alpha's Response may be valid for Alpha, yet it is not meant for Beta. Pooling all IdP verification certificates and asking "does any key verify?" destroys partner isolation.

Even when Alpha and Beta intentionally share an SP entityId/ACS, there must still be **explicit trust mapping/issuer scope and tenant selection** to prevent out-of-context token reuse.

## 9. SP Keys and IdP Certificates Must Have Explicit Purpose and Scope

Inside a registration, the credentials are:

| Credential | Where Is the Private Key? | Purpose | Scoping Rule |
| --- | --- | --- | --- |
| **SP signing** | SP | Sign AuthnRequests/SLO messages | Only keys approved for that registration |
| **SP decryption** | SP | Decrypt `EncryptedAssertion`/`EncryptedID` sent to SP | Only registered key ring; overlap during rotation as needed |
| **IdP verification** | IdP; SP holds public cert only | SP verifies Response/Assertion signatures | Only the IdP certificate trusted for that registration |
| **Metadata signer verification** | IdP/federation operator | SP verifies metadata signature (if policy requires) | Independent trust anchor prior to importing metadata |

**Never give an SP private key to an IdP.** The IdP receives the SP's public certificate to verify AuthnRequests or encrypt assertions. The SP keeps private keys in a secret store/HSM under least privilege.

### 9.1. Why Key Separation Helps

- If Alpha is compromised, risk does not automatically spread to Beta's keys.
- Rotating Alpha's signing certificate does not force Beta to update.
- If Beta uses encrypted assertions and Alpha does not, you can provision a decryption key solely for Beta.
- Monitoring and incident response can isolate events per partner.
- Different issuer/certificate pinning policies can apply per IdP.

**Key sharing can be a valid design** when a single logical SP intentionally uses the same `entityId`/certificate with multiple IdPs. Still, document who shares access to the private key, how one partner's config change can impact others, and the shared rotation process.

### 9.2. Per-Partner Key Rotation

SP **signing key**:
1. Generate a new keypair/cert for Alpha.
2. Deliver the **new public signing cert** to IdP Alpha through a trusted channel.
3. IdP Alpha starts trusting the new cert; only then does SP Alpha switch to signing with the new private key.
4. Test signed AuthnRequests, then retire the old key on schedule.

SP **decryption key**:
1. SP Alpha provisions the **new private key first**.
2. IdP Alpha switches to encrypting with the **new public encryption certificate**.
3. SP keeps both old and new keys active during an approved overlap window.
4. Once no ciphertexts using the old cert remain, retire the old key.

IdP **verification cert**:
1. Alpha announces signer rollover via metadata/trusted workflow.
2. SP Alpha updates **Alpha's verification certificate**.
3. Test during the overlap window and remove the old certificate after cutover.
4. Never carry Alpha's cert into Beta's trust policy.

Metadata trust has its own lifecycle; a `metadata-uri` pointing to a file/URL only says **where to fetch**, not who legitimately signed the metadata. If policy requires signed metadata, verify it with an **independently provisioned metadata signer trust anchor**. Spring Security documentation on metadata signature validation requires configuring the corresponding `verificationCredentials`.

## 10. Per-Partner Attribute Policies: No Single Global Schema

SAML Attributes vary across IdPs:

- `employeeId` / `uid` / `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier`;
- `email` / `mail` / `EmailAddress`;
- `groups` / `memberOf` / `entitlements`;
- `department`, `costCenter`, `tenant`, `role`.

One partner may emit groups as human-readable names, while another emits GUIDs. A SAML Attribute can also contain **multiple values**, so `getFirstAttribute` is safe only when the schema **guarantees exactly one value**.

### 10.1. Designing `AttributePolicy`

Bind a dedicated policy to each registration:

~~~yaml
saml-attribute-policies:
  alpha:
    subject:
      attribute: employeeId
      required: true
      exactly-one: true
    display-name:
      attribute: displayName
      required: false
    groups:
      attribute: groups
      mappings:
        engineers: ROLE_ALPHA_EDITOR
        auditors: ROLE_ALPHA_AUDITOR
    jit-provisioning: false

  beta:
    subject:
      attribute: uid
      required: true
      exactly-one: true
    display-name:
      attribute: fullName
      required: false
    groups:
      attribute: entitlements
      mappings:
        partner-viewer: ROLE_BETA_READER
    jit-provisioning: false
~~~

**This is a custom domain configuration schema designed for this lesson, not built-in Spring Boot/Spring Security properties.** To apply it, you must write and test a component that reads the policy from config/database. Do not paste it into `application.yml` and expect Spring Security to parse it or assign roles automatically.

**Policy selection rule:** select by `registrationId` **after the SAML Response is verified and bound to that registration**—never pick a policy from an IdP-supplied `tenant` attribute.

### 10.2. Stable Subjects and Scoped Identities

Emails can change or be reassigned, so **never use email by default to auto-link a user across IdPs/tenants**. Use:

- Persistent NameID if the IdP contract guarantees stability and NameID Format/NameQualifier/SPNameQualifier are handled properly.
- A verified non-reusable subject ID committed by the IdP, such as `employeeId`, `uid`, or an immutable directory object ID.
- An internal key scoped by tenant/registration/IdP issuer/subject or an explicit foreign-key identity record.

Example local identifiers:

~~~text
(tenant-a, alpha, https://alpha-idp.example.test/issuer, employeeId=u-100)
(tenant-b, beta,  https://beta-idp.example.test/issuer,  uid=u-100)
~~~

Both records share the **same string `u-100`** yet are not the same local identity by default. Only **verified and approved account linking** may attach them to the same user account if the product allows it.

### 10.3. Enforcing Type and Cardinality Checks

For any subject attribute used as an identity key:

- If **missing**, reject JIT login/linking or route to an approved exception workflow; never fall back to `email` automatically.
- If **multi-valued** when policy requires a single value, reject to avoid order-dependent "first value" ambiguity.
- If empty, oversized, or malformed, reject; verify encoding/normalization rules per contract.
- Never turn numeric `123` and string `"123"` into inconsistent identities; define schema and serialization explicitly.
- Never truncate, lowercase, or trim an immutable subject identifier unless the IdP contract guarantees that normalization.
- If the IdP changes schema or NameID Format, perform a controlled mapping migration.

## 11. Mapping Groups to Authorities: Per-Tenant Allowlists

A classic mistake:

~~~java
// UNSAFE:
String claimedGroup = principal.getFirstAttribute("group");
authority = new SimpleGrantedAuthority("ROLE_" + claimedGroup);
~~~

If an IdP or group admin can create a value `ADMIN`, the app may inadvertently grant `ROLE_ADMIN` system-wide. With multiple partners, Beta's `admin` group is **not** Alpha's admin permission.

**Conceptually sound approach:** an **application/tenant-owner-approved map** translating verified attribute values into bounded authorities:

~~~text
Alpha:
  "engineers" -> ROLE_ALPHA_EDITOR
  "auditors"  -> ROLE_ALPHA_AUDITOR

Beta:
  "partner-viewer" -> ROLE_BETA_READER
  "partner-billing" -> ROLE_BETA_BILLING
~~~

Never convert unknown groups into authorities. Leave roles empty, require local database roles, or deny per policy. You must check **permissions on every resource** using tenant membership and local authorization—not merely because a user holds `ROLE_USER` from a valid SAML login.

### 11.1. How Spring Security Handles Attributes Post-Verification

After `OpenSaml5AuthenticationProvider` verifies the Response and Assertion, Spring Security builds a `Saml2Authentication` holding a `Saml2AuthenticatedPrincipal`. You can read:

~~~java
Saml2AuthenticatedPrincipal principal =
    (Saml2AuthenticatedPrincipal) authentication.getPrincipal();

String registrationId =
    principal.getRelyingPartyRegistrationId();

Object employeeId = principal.getFirstAttribute("employeeId");
List<Object> groups = principal.getAttribute("groups");
~~~

This snippet is **used after authentication succeeds**, requiring Spring Security imports and casting/validation per policy. The exact element types returned by `getAttribute` depend on the data and API; do not assume `List<String>` in every case.

Spring Security exposes `OpenSaml5AuthenticationProvider#setResponseAuthenticationConverter` to customize how an Assertion becomes an `Authentication`. Documentation also covers `ResponseAuthenticationConverter` for extracting NameID/attributes. **Never skip default validation steps** to read raw XML earlier; attribute mapping and authority enrichment must run **only after** issuer, signature, audience, timestamps, and `SubjectConfirmation` succeed.

### 11.2. Domain-Level Mapping After Authentication

An application service can accept **normalized input from Spring Security's `Authentication`**, then:

1. Read the `registrationId` bound to the principal by the framework.
2. From trusted config, map registration → `tenantId` / attribute policy.
3. Extract the required subject attribute and enforce exact cardinality.
4. Look up the external identity link scoped by tenant + provider + subject.
5. Map groups through the policy's allowlist.
6. Fetch local entitlements from the database/authorization service and compute effective authorities.
7. Set tenant context based on **verified local entities**, never trusting unverified tenant headers, query params, or unmanaged claims.
8. Issue the session with least privilege; never auto-grant tenant membership merely because SAML login succeeded.

**Specifically:** if an IdP is permitted to supply business entitlements, the contract must specify exact **attribute names, values, issuer authority, update timing, and revocation**. If the IdP only proves identity, business permissions must reside completely in the application.

## 12. Recommended Data Model for Multiple Partners

Abbreviated PostgreSQL example:

~~~sql
CREATE TABLE saml_partner (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    registration_id TEXT NOT NULL UNIQUE,
    sp_entity_id TEXT NOT NULL,
    acs_url TEXT NOT NULL,
    idp_entity_id TEXT NOT NULL,
    idp_metadata_source TEXT NOT NULL,
    sp_signing_key_ref TEXT,
    sp_decryption_key_ref TEXT,
    idp_verification_trust_ref TEXT NOT NULL,
    attribute_policy_ref TEXT NOT NULL,
    config_version BIGINT NOT NULL DEFAULT 1,
    enabled BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE external_saml_identity (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    partner_id BIGINT NOT NULL REFERENCES saml_partner(id),
    subject_namespace TEXT NOT NULL,
    subject_value TEXT NOT NULL,
    local_user_id UUID NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, partner_id,
            subject_namespace, subject_value)
);
~~~

This is a **learning model**, not a complete multi-tenant production schema. `subject_namespace` can represent the agreed NameID Format/qualifier or attribute type; issuer mapping relies on trusted rows in `saml_partner`. Never create a global `UNIQUE(subject_value)` across the whole system, as it would collide `u-100` across two partners.

### 12.1. Why Store Key Refs Instead of PEM?

`sp_signing_key_ref` and `sp_decryption_key_ref` should reference a secret manager/keystore alias or a controlled registry rather than storing **plaintext private keys** in the tenant config table. When loading a registration:

- Only services authorized for that registration may resolve the key reference.
- Never take `keyRef` from a browser-supplied `SAMLResponse`, `RelayState`, or Attribute.
- Maintain explicit versioning/rotation and audit changes to key references.
- IdP verification trust must bind to the exact partner and verified metadata source.

Remember that while an **IdP's public certificate** is not a private key, its source is **integrity-sensitive trust configuration**: an attacker who swaps the cert can trick the SP into trusting a rogue IdP.

### 12.2. Tenant-Aware Database Access

Application-layer checks are insufficient if database queries lack tenant filtering. After authentication, every query for local users, groups, and resources must include the **verified** tenant context. Consider:

- Tenant-scoped unique constraints for external identities.
- Foreign keys protecting tenant/user relationships in true multi-tenant apps.
- Row-level security (RLS) or tenant-scoped repository predicates.
- Preventing users from switching `tenantId` via an HTTP header to read another tenant's data.
- Auditing account linking, JIT provisioning, deprovisioning, and cross-tenant role changes.

SAML solves **sign-in**, not business data authorization policy.

## 13. Standalone Java 17: Proving Isolation Between Two Partners

This example **runs on JDK 17+** with no Spring Security or live IdP. It models:

- Each partner with its own `registrationId`, tenant, SP `entityId`, ACS, IdP issuer, key aliases, and **attribute policy**.
- A `VerifiedAssertion` record mocking the **validated output of a SAML library**, not unverified XML.
- Identical subject `u-100` from Alpha and Beta yielding **two distinct scoped local identity keys**.
- Group `ROLE_SUPER_ADMIN` sent by Alpha without a policy mapping **receiving zero authority**.
- Wrong issuer, audience, recipient/ACS, missing subject, swapped partner schema, or unverified assertions all failing closed.

**Important warning:** the boolean `verifiedBySamlLibrary` is strictly a **trust simulation in unit tests**; in real integrations, never read such a boolean from HTTP requests, JSON, headers, or SAML Attributes. Spring Security/OpenSAML must run **cryptographic and protocol validation first**. Nor does this program **sign/decrypt SAML XML, manage private keys, or expose HTTP endpoints**.

File `PartnerIsolationDemo.java`:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

public class PartnerIsolationDemo {
    record Partner(String registrationId, String tenantId,
                   String spEntityId, String acs,
                   String idpEntityId, String subjectAttribute,
                   String groupsAttribute,
                   Map<String, String> groupToRole,
                   String signingKeyAlias, String decryptionKeyAlias,
                   String idpCertificateFingerprint) {}

    // This is a MOCK of an output from a trusted SAML verifier, not raw XML.
    record VerifiedAssertion(String registrationId, String issuer,
                             String audience, String recipient,
                             boolean verifiedBySamlLibrary,
                             Map<String, List<String>> attributes) {}

    record LocalIdentity(String key, String tenantId, Set<String> roles) {}

    static Optional<LocalIdentity> resolve(
            Map<String, Partner> registrations, VerifiedAssertion assertion) {
        // In production registration resolution + every SAML validation
        // MUST be done by Spring Security/OpenSAML.
        if (!assertion.verifiedBySamlLibrary()) return Optional.empty();
        Partner partner = registrations.get(assertion.registrationId());
        if (partner == null
                || !partner.idpEntityId().equals(assertion.issuer())
                || !partner.spEntityId().equals(assertion.audience())
                || !partner.acs().equals(assertion.recipient())) {
            return Optional.empty();
        }
        List<String> subjects = assertion.attributes()
            .getOrDefault(partner.subjectAttribute(), List.of());
        if (subjects.size() != 1 || subjects.get(0).isBlank()) {
            return Optional.empty();
        }
        String stableId = subjects.get(0);
        Set<String> roles = new LinkedHashSet<>();
        for (String group : assertion.attributes().getOrDefault(
                partner.groupsAttribute(), List.of())) {
            String mapped = partner.groupToRole().get(group);
            if (mapped != null) roles.add(mapped);
        }
        String key = partner.tenantId() + "|" + partner.registrationId()
            + "|" + stableId;
        return Optional.of(new LocalIdentity(
            key, partner.tenantId(), Set.copyOf(roles)));
    }

    public static void main(String[] args) {
        Partner alpha = new Partner(
            "alpha", "tenant-a", "urn:portal:sp:alpha",
            "https://portal.example.test/login/saml2/sso/alpha",
            "https://alpha-idp.example.test/issuer",
            "employeeId", "groups",
            Map.of("engineers", "ROLE_ALPHA_EDITOR"),
            "alpha-sp-sign", "alpha-sp-decrypt", "cert-alpha");
        Partner beta = new Partner(
            "beta", "tenant-b", "urn:portal:sp:beta",
            "https://portal.example.test/login/saml2/sso/beta",
            "https://beta-idp.example.test/issuer",
            "uid", "entitlements",
            Map.of("partner-viewer", "ROLE_BETA_READER"),
            "beta-sp-sign", "beta-sp-decrypt", "cert-beta");
        Map<String, Partner> registrations =
            Map.of("alpha", alpha, "beta", beta);

        VerifiedAssertion a = new VerifiedAssertion(
            "alpha", alpha.idpEntityId(), alpha.spEntityId(), alpha.acs(),
            true, Map.of(
                "employeeId", List.of("u-100"),
                "groups", List.of("engineers", "ROLE_SUPER_ADMIN")));
        VerifiedAssertion b = new VerifiedAssertion(
            "beta", beta.idpEntityId(), beta.spEntityId(), beta.acs(),
            true, Map.of(
                "uid", List.of("u-100"),
                "entitlements", List.of("partner-viewer")));

        Optional<LocalIdentity> aId = resolve(registrations, a);
        Optional<LocalIdentity> bId = resolve(registrations, b);
        System.out.println("alphaAccepted=" + aId.isPresent());
        System.out.println("betaAccepted=" + bId.isPresent());
        System.out.println("sameSubjectSeparated=" +
            (aId.isPresent() && bId.isPresent()
                && !aId.get().key().equals(bId.get().key())));
        System.out.println("unmappedRoleRejected=" +
            (aId.isPresent()
                && !aId.get().roles().contains("ROLE_SUPER_ADMIN")));
        System.out.println("wrongIssuer=" + resolve(registrations,
            new VerifiedAssertion("alpha", beta.idpEntityId(),
                alpha.spEntityId(), alpha.acs(), true, a.attributes()))
            .isPresent());
        System.out.println("wrongAudience=" + resolve(registrations,
            new VerifiedAssertion("alpha", alpha.idpEntityId(),
                beta.spEntityId(), alpha.acs(), true, a.attributes()))
            .isPresent());
        System.out.println("wrongAcs=" + resolve(registrations,
            new VerifiedAssertion("alpha", alpha.idpEntityId(),
                alpha.spEntityId(), beta.acs(), true, a.attributes()))
            .isPresent());
        System.out.println("missingSubject=" + resolve(registrations,
            new VerifiedAssertion("alpha", alpha.idpEntityId(),
                alpha.spEntityId(), alpha.acs(), true,
                Map.of("groups", List.of("engineers")))).isPresent());
        System.out.println("wrongAttributePolicy=" + resolve(registrations,
            new VerifiedAssertion("beta", beta.idpEntityId(),
                beta.spEntityId(), beta.acs(), true, a.attributes()))
            .isPresent());
        System.out.println("unverifiedResponse=" + resolve(registrations,
            new VerifiedAssertion("alpha", alpha.idpEntityId(),
                alpha.spEntityId(), alpha.acs(), false, a.attributes()))
            .isPresent());
    }
}
~~~

Compile/run with JDK 17:

~~~bash
javac --release 17 PartnerIsolationDemo.java
java PartnerIsolationDemo
~~~

**Exact stdout:**

~~~text
alphaAccepted=true
betaAccepted=true
sameSubjectSeparated=true
unmappedRoleRejected=true
wrongIssuer=false
wrongAudience=false
wrongAcs=false
missingSubject=false
wrongAttributePolicy=false
unverifiedResponse=false
~~~

Reading the results:

- **alphaAccepted/betaAccepted=true:** both partner policies accept their respective valid subjects.
- **sameSubjectSeparated=true:** identical `u-100` across two tenants/registrations are not merged.
- **unmappedRoleRejected=true:** an admin-looking group value without a mapping creates no authority.
- **wrongIssuer/wrongAudience/wrongAcs=false:** an assertion fragment from another partner cannot be misdirected across issuers or endpoints.
- **missingSubject=false:** when policy requires a subject, missing subject is rejected.
- **wrongAttributePolicy=false:** Alpha's attributes do not satisfy Beta's schema, even though both emit user `u-100`.
- **unverifiedResponse=false:** an assertion not yet verified by the SAML verifier cannot produce a business identity.

**In production**, issuer/audience/recipient checks are handled upstream by **Spring Security/OpenSAML**. The `resolve` method here illustrates only the post-validation application-layer guard, not a replacement for validators or an API for accepting browser SAML Responses directly.

## 14. End-to-End Flow: From Tenant Selection to Local User

A clean architecture organizes the pipeline into these steps:

~~~text
HTTP request from user
   |
   v
Tenant selection (domain/path/login picker)
   |
   v
Select allowlisted registrationId
   |
   v
Spring Security creates AuthnRequest + stores correlation
   |
   v
Matching IdP authenticates and returns SAMLResponse
   |
   v
Saml2AuthenticationTokenConverter resolves registration
   |
   v
OpenSaml5AuthenticationProvider verifies
   - right IdP signing cert
   - issuer, audience, destination/recipient
   - InResponseTo, timestamps, subject, signature
   - decrypts with matching SP decryption credentials if needed
   |
   v
Saml2Authentication / Saml2AuthenticatedPrincipal
   |
   v
PartnerAttributePolicyService(registrationId)
   - extracts stable subject
   - verifies cardinality/format
   - maps groups through allowlist
   |
   v
LocalIdentityService
   - tenant + partner-scoped external identity
   - account linking / JIT policy
   - local roles + resource permissions
   |
   v
Session/Authentication context carries verified tenant
   |
   v
Business API enforces tenant ownership and roles
~~~

**Trust boundary transition:** before the SAML validator, URL/`RelayState`/SAML XML are untrusted inputs. After the validator, verified claims inside the right registration can drive mapping, while **business permissions** still depend on local policy.

### 14.1. Separating Technical Federation from Business Tenancy

The SAML module should focus on:

- `RelyingPartyRegistration`, metadata, keys, endpoints.
- AuthnRequest/Response, XMLDSig, XML Encryption.
- Issuer/audience/recipient/session correlation and producing the authenticated principal.

The business tenant/identity module handles:

- Which tenant each registration maps to.
- Which subject attribute identifies users.
- Whether JIT provisioning is permitted.
- How external identities link to local users.
- Role/group mapping, deprovisioning, and authorization.
- Per-tenant data access contracts.

Separating these two layers avoids "I saw group `ADMIN` in SAML so I granted `ADMIN` immediately." An authenticated SAML login **does not equal administrative access across every tenant**.

## 15. Designing Tenant Selection with Shared Domains or Paths

If a portal exposes URLs like:

~~~text
https://portal.example.test/alpha/login
https://portal.example.test/beta/login
~~~

or subdomains:

~~~text
https://alpha.portal.example.test/login
https://beta.portal.example.test/login
~~~

the app can use admin-managed domains/paths to **propose** a registration. However:

- `Host`/forwarded headers may be trusted only from a controlled reverse proxy.
- The registration must be **an allowlisted value**, never dynamically constructed from an arbitrary path like `new RelyingPartyRegistration(userInput)`.
- Tenant selection must bind to auth request state/cookies; callbacks must not switch tenants simply by changing the URL.
- Replaying a Response signed for Alpha against Beta's endpoint must fail issuer/audience/recipient/flow checks.
- If a user holds access in multiple tenants, post-login tenant switching must rely on **verified local membership** and switch-tenant policy—never from arbitrary groups or query strings.

**Never rely solely on a `Referer` or arbitrary header** to determine the tenant when receiving a SAML Response from an IdP.

## 16. Multiple IdPs with the Same Display Name or Shared Metadata

Consider these cases:

1. **Two distinct IdPs sharing the label** `Corporate SSO`.
2. **One IdP serving multiple tenants** with a shared issuer.
3. **A federation aggregator** publishing multiple `IDPSSODescriptor` entries in one metadata feed.
4. **An IdP changing its `entityId`** during a regional migration.
5. **One partner operating multiple IdPs** by geography or authentication method.

Never solve these using display names:

- `registrationId` must be unique and stable for configuration management.
- `IdP entityId` and verification keys must bind to the exact entity source.
- Every onboarding has an owner, environment, metadata source/trust, and configuration version.
- If aggregate metadata contains multiple IdPs, select only **permitted entities** inside the verified aggregate.
- When one IdP truly serves multiple tenants under the same issuer, design **dedicated SP `entityId`/ACS or request correlation** where feasible, or a trusted tenant-selection mechanism.
- Display names are purely for UI; never use them as identity or trust keys.

## 17. Account Linking, JIT Provisioning, and Identity Lifecycle

### 17.1. Do Not Auto-Link Accounts by Email

Example:

~~~text
Alpha emits email=person@example.test, employeeId=a-123
Beta  emits email=person@example.test, uid=b-989
~~~

Two IdPs emitting the same email **do not prove it is the same external identity**, nor that the person is authorized for both tenants. Emails can be reassigned, reused, or changed.

When account linking is required:

1. User/administrator completes an approved linking flow.
2. Authenticate both identity sources or verify acceptable proof of ownership.
3. Record issuer/provider/subject scope, timestamp, and owner.
4. Support review/unlinking and auditing.
5. Never reassign a record from tenant A to tenant B solely because emails match.

### 17.2. JIT Provisioning Must Be Constrained

If policy permits automatic user creation after SAML login, verify:

- Is JIT permitted for that registration/IdP?
- Is the subject guaranteed stable with no existing conflict?
- Is the local tenant active and allowed to accept new users?
- What minimal default state and permissions does the newly created user receive?
- Are groups mapped via the tenant's allowlist, with no dynamic `ADMIN`?
- Deprovisioning: what happens when the IdP account is disabled, the user leaves a group, or the local account is locked?

**JIT must not automatically grant access to all tenant resources.** By default, create only the identity/profile and require separate business authorization unless a specific provisioning contract dictates otherwise.

### 17.3. Attribute Schema Changes

When IdP Alpha migrates from `employeeId` to `objectGUID`, do not swap the key mapping directly and let existing users be duplicated. Perform a migration:

1. IdP confirms stability and uniqueness of the new attribute.
2. Build a documented old → new mapping backed by evidence.
3. Test on sample accounts and resolve collisions.
4. Version `attribute_policy_ref` and the cutover date.
5. Prepare rollback and auditing.

## 18. Per-Partner Security Testing

| Test Case | Input | Expected Outcome |
| --- | --- | --- |
| Standard Alpha login | Alpha issuer/cert, Alpha Audience, Alpha ACS | PASS if all validation and local policy succeed |
| Standard Beta login | Beta issuer/cert, Beta Audience, Beta ACS | PASS per Beta policy |
| Alpha Response sent to Beta ACS | Beta URL, Alpha Response Issuer/Audience | FAIL |
| Beta Response signed with Alpha key | Signature not in Beta IdP trust | FAIL |
| Alpha IdP self-publishes new key in Response | `KeyInfo` contains unknown certificate | Not auto-trusted |
| Wrong Audience | Validly signed Response for another SP | FAIL |
| Wrong Recipient | `SubjectConfirmationData` Recipient != ACS | FAIL |
| Wrong Destination | Response targets URL outside policy | FAIL |
| Wrong `InResponseTo` | Response does not match pending AuthnRequest | FAIL in SP-initiated flow |
| Response replay | Reused Assertion/Response | FAIL |
| Clock skew/expiry | `NotBefore`/`NotOnOrAfter` outside policy | FAIL |
| Alpha-key `EncryptedAssertion` sent to Beta | No matching Beta private decryption key | FAIL |
| Multi-IdP same issuer | Issuer alone cannot pick tenant | FAIL without additional correlation |
| Missing subject | Alpha `employeeId` absent | FAIL per required policy |
| Multi-valued subject | Alpha carries two `employeeId` values | FAIL when policy is `exactly-one` |
| Swapped attribute schema | Beta receives Alpha attributes | Does not map Beta identity |
| Same ID across tenants | Both have subject = `u-100` | Two distinct scoped identities |
| Same email across IdPs | Matching email, different subjects | No auto-link |
| Arbitrary admin group | Alpha receives `ROLE_SUPER_ADMIN` in groups | No authority granted unless allowlisted |
| Beta group claims Alpha role | `entitlements=engineers` | Alpha mapping not applied |
| Tampered tenant header | Alpha-authenticated user sends `X-Tenant: beta` | Does not switch tenant without local membership |
| Spoofed proxy host | Attacker injects forwarded host | Never alters ACS/`entityId` from untrusted host |
| Unverified IdP metadata | Metadata signer untrusted | Does not update IdP trust per policy |
| Alpha cert rotation | Alpha holds old/new certs during overlap | Alpha passes; Beta unaffected |
| Revoked cert | Old Alpha cert removed from trust | Rejects assertion signed with old key |
| Deactivated tenant | Registration disabled | Neither initiates nor accepts login |
| JIT disabled | Valid SAML user has no local link | Does not auto-create privileged user |
| Multi-tab SP-initiated | Distinct AuthnRequest A/B states | Callback binds to right flow |
| Unsolicited login disabled | Response lacks `InResponseTo` | FAIL |
| Aggregate metadata | Only entities inside trusted signed scope | Accepts approved entities only |
| Logging | Assertion carries email/groups | Never writes full SAML XML/PII to production logs |

**Name tests by registration and attack vector**, not just "login fails." In integration tests, verify both IdP metadata/certificates and local side effects: no wrong-tenant session, no unauthorized user link, and no database privilege grant.

## 19. Troubleshooting by Failure Layer

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Alpha login goes to Beta IdP | Wrong `registrationId`/router/default picker | Inspect `/saml2/authenticate/{id}`, repository, and tenant selector |
| Beta ACS receives Alpha Response | Wrong ACS registered in IdP portal | Compare SP metadata and IdP configuration |
| `Invalid issuer` | Wrong partner IdP config used | Compare IdP `entityId` in registration |
| `Invalid audience` | SP Entity ID differs from contract | Compare Audience and SP `EntityDescriptor` |
| `Invalid destination` | Wrong proxy/ACS scheme/host/path | Check public URL and trusted forwarded headers |
| Signature invalid | Stale IdP cert or wrong partner | Compare fingerprint/trust per registration |
| `EncryptedAssertion` decrypt fail | Wrong SP key ring or IdP encrypted with wrong cert | Check SP decryption cert and private key |
| `InResponseTo` mismatch | Request state/cookie/cluster mismatch | Check AuthnRequest repository, session, and binding |
| Login succeeds yet user not found | Subject policy targets missing attribute | Verify IdP schema and required attributes |
| Alpha user appears in Beta | Identity key used unscoped email/subject | Fix external identity schema and linking |
| Beta receives `ROLE_ALPHA_ADMIN` | Group mapping applied globally | Separate per-registration policy and role allowlists |
| JIT creates duplicate users | IdP sends transient NameID/attribute | Check persistent identity contract and migration |
| Fails only in production | Host/proxy/cert/Entity ID differs from UAT | Compare live metadata/runtime config per environment |
| Callback cannot map registration | Shared ACS, overlapping issuer/missing state | Design trusted resolver/correlation |
| New metadata breaks all IdPs | Shared unscoped trust bundle/key | Partition trust, versioning, and rollback per partner |
| Errors right after rotation | IdP hasn't imported cert or JVM cached old key | Check cutover/reload and overlap |
| SAML succeeds yet API returns 403 | Business authorization lacks tenant membership | Check local roles/resource permissions; never loosen SAML validation |

### 19.1. Minimal, Investigative-Ready Logging

Log per security policy:

~~~text
timestamp
registrationId
tenantId (from trusted config)
spEntityId
idpEntityId (post-validation)
public certificate fingerprint
signature/issuer/audience/recipient validation result
attribute policy version
local identity lookup result
correlation ID, error category
~~~

**Never write private keys, full XML assertions, sensitive NameID/attributes, Base64 `SAMLResponse`s, or session cookies** to production logs. A certificate fingerprint is helpful public data, yet logs alone must never become the sole trust authority.

## 20. Design and Operations Checklist

- [ ] Inventory all partners, IdP `entityId`, tenant, `registrationId`, SP `entityId`, and ACS.
- [ ] Each `registrationId` is unique and has an owner and config version.
- [ ] Explicitly decide **which `entityId`/ACS/private keys are separate and which are intentionally shared**; never share implicitly.
- [ ] IdP verification keys are scoped per registration, never pooled into an unscoped global trust list.
- [ ] SP signing/decryption private keys are managed separately per partner when policy requires.
- [ ] Verify Alpha/Beta SP metadata publishes the exact Entity ID, ACS, and public certificates.
- [ ] Default ACS, custom `loginProcessingUrl`, reverse proxy, and IdP callback URLs align.
- [ ] Registration resolver safely handles SP-initiated flows, `InResponseTo`, IdP-initiated policy, and shared-issuer ambiguity.
- [ ] Response Issuer is only a pre-validation candidate hint; the trusted IdP certificate is enforced properly.
- [ ] Audience, Recipient, Destination, timestamps, `SubjectConfirmation`, and replay checks are never skipped.
- [ ] `EncryptedAssertion` is decrypted only with the matching registration's SP decryption credentials.
- [ ] IdP metadata sources manage trust, expiry, rotation, and signer verification when required by policy.
- [ ] Attribute policies attach to `registrationId`, never chosen from unverified tenant/email claims.
- [ ] Subject is a stable identifier scoped by tenant/provider; email never auto-links identities.
- [ ] Required attributes enforce type, cardinality, normalization, and explicit fallback rules.
- [ ] Group/role mappings come strictly from per-partner allowlists; no dynamic `ROLE_` + raw group.
- [ ] Business APIs verify tenant membership/local authorization independently of SAML success.
- [ ] JIT provisioning, account linking, deprovisioning, and schema migrations have auditing and approval.
- [ ] Cert/key rotation has purpose-built overlap and per-partner plans.
- [ ] Test cross-partner confusion, same subject/email, wrong ACS/key, missing attrs, unsolicited responses, and multi-node sessions.
- [ ] Monitor per registration and secret key version without logging sensitive data.

## 21. Self-Check Questions

**1. Must every IdP have its own SP Entity ID?**

Not strictly required by Spring Security/SAML: multiple registrations can intentionally share an `entityId`, ACS, or credentials. However, when isolating trust/tenants, dedicated values reduce mix-ups and allow independent key rotation. Any sharing requires explicit policy and correlation.

**2. Is `registrationId = alpha` the SAML Issuer?**

No. `registrationId` is a local Spring Security key; SP and IdP `entityId`s are the logical identifiers exchanged in SAML and metadata.

**3. Is an ACS URL containing `beta` enough to prove the Response came from Beta?**

No. A browser can POST arbitrary data to any path. You must verify Beta IdP's signature, issuer, audience, recipient/destination, correlation, and conditions.

**4. If an Alpha Response has a valid signature, can it log into Beta?**

No. The signature is valid only for Alpha IdP; the response must also match the SP `entityId`, ACS, and trust policy of the requested registration/tenant. Never use a global "any key passes" rule.

**5. When one IdP issuer serves multiple tenants, is Issuer alone enough to identify the tenant?**

No. You need SP-initiated request state or a trusted routing/correlation mechanism. If still ambiguous, reject.

**6. Should SAML groups be mapped to `ROLE_` + `groupName`?**

No. Map only verified groups/entitlements through a **per-partner allowlist**; never let Beta's `ADMIN` value grant ADMIN privileges in Alpha.

**7. If Alpha and Beta users both have subject `u-100`, are they the same account?**

Not by default. Identities must be scoped by tenant, registration, issuer, and stable subject. To link them, use a verified linking flow.

**8. Why shouldn't email be the sole account-linking key?**

Email can change or be reused and may collide across different IdPs. It proves neither the same identity source nor tenant access rights.

**9. If Alpha's SP signing private key rotates, must Beta's change too?**

No if the two registrations use separate keys. If keys are intentionally shared, rotation affects both and must be coordinated with every involved IdP.

**10. Where do you read attributes in Spring Security?**

After successful SAML authentication, via `Saml2Authentication` / `Saml2AuthenticatedPrincipal` or a supported response authentication converter. Never use unverified raw XML for identity/role mapping.

**11. Why must a custom ACS align with SP metadata and the filter URL?**

The IdP posts Responses to the registered ACS, while the Spring filter listens on the configured path. Any mismatch causes 404s or Destination/Recipient validation failures.

**12. Does JIT provisioning with a verified new subject automatically grant tenant permissions?**

No. It must follow onboarding policy, membership, allowlisted roles, and local authorization. A valid SAML identity is not business permission.

## 22. Technical References

- Spring Security, **SAML 2.0 Login Overview**, `RelyingPartyRegistration`, multiple asserting parties, URI patterns, duplicated relying party configurations, and default ACS: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **Authenticating SAML Responses**, registration lookup, `Saml2AuthenticationTokenConverter`, `OpenSaml5AuthenticationProvider`, response authentication converter, attributes/authorities: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Producing AuthnRequests**, routing/signing AuthnRequests per `RelyingPartyRegistration`: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security, **SAML 2.0 Metadata**, per-registration SP metadata and verifying signed IdP metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security Javadoc, **RelyingPartyRegistration**, SP/IdP pair and `registrationId`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html
- Spring Security, **Saml2AuthenticatedPrincipal**, attribute access and registration association: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- OASIS, **SAML 2.0 Core**, Issuer, AudienceRestriction, SubjectConfirmationData/Recipient, and NameID: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS, **SAML 2.0 Metadata**, `EntityDescriptor`, `AssertionConsumerService`, `KeyDescriptor`, and `IDPSSODescriptor`: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS, **SAML 2.0 Profiles**, Web Browser SSO and unsolicited Responses: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OWASP, **SAML Security Cheat Sheet**, preventing XML Signature Wrapping, signature/trust, and recipient validation: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Takeaway:** an application with multiple IdPs/tenants should treat **each `RelyingPartyRegistration` as a trust boundary**. `registrationId` selects the configuration pair; **SP `entityId` and ACS identify the recipient**; **IdP issuer and verification certificate identify the sender**; **SP signing/decryption credentials serve that specific connection**; **attribute policy defines how verified claims become scoped local identities and permissions**. Every account/tenant decision must happen **after SAML validation** and enforce **independent cross-tenant authorization**.
# Persistent vs. Transient Identifiers and Their Impact on Account Linking

> **Module:** Spring Security – federation · **Parent topic:** Identity and authorities. This lesson analyzes SAML 2.0 `NameID` in **persistent** and **transient** formats, why identifier choice directly affects user recognition across SSO logins, and how to build safe **account linking** in a Service Provider (SP).

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **successful authentication at an Identity Provider (IdP)**, **the identifier asserted by the IdP**, **the link to a local account**, and **access permissions decided by the application**.
2. Explain the SAML 2.0 semantics of `persistent NameID` and `transient NameID`: stability, IdP–SP scope, privacy, and lifecycle.
3. Compare related formats `emailAddress` and `unspecified` without equating "looks stable" with "guaranteed durable".
4. Build a scoped external linking key that avoids mismatches when two IdPs issue the same NameID string, a user changes email, or the SP changes its registration ID.
5. Design workflows for **unlinked accounts**, **first-time approval**, **NameID changes**, **permission revocation**, and **IdP migrations**.
6. Enforce permissions on the **right resource and tenant**, preventing a valid identifier from automatically turning into administrative privilege.
7. Run a **Java 17 example with no external dependencies** proving that persistent IDs can map stably, transient IDs must not be durably mapped, and scope/permissions prevent cross-tenant access.
8. Understand the role of `Saml2AuthenticatedPrincipal` in Spring Security 6.x and the limitations of `getName()` when inspecting NameID Format/qualifiers.

## 2. Place four concepts properly before designing

Suppose a partner IdP authenticates employee An and sends a valid SAML Assertion to the Orders Portal. There are four distinct questions:

| Question | Primarily responsible party | Commonly used data/conditions |
| --- | --- | --- |
| **Who authenticated the user?** | The IdP and the SAML verification layer at the SP. | IdP `Issuer`, signature, response/assertion, binding, validity window, audience, recipient, `InResponseTo`. |
| **Which ID does the IdP use to represent the subject?** | IdP issues `Subject/NameID`; SP reads the proper format and scope. | `NameID.Value`, `Format`, `NameQualifier`, `SPNameQualifier`. |
| **Which local account is that external identity bound to?** | SP application and link governance workflow. | Approved `external_identity → local_user_id` record; active/revoked state. |
| **What may the local user do with this resource?** | Authorization layer of the SP application. | Local permissions, tenant, resource ownership, account state, and per-request policy. |

**Valid SAML authentication does not mean an account link exists**, and **a valid account link does not mean all permissions are granted**.

For example, the IdP authenticates an employee of Partner A, yet the internal account has not been granted permission to view orders. The application can direct the user to a "pending approval" screen while denying the orders API. A partner does not gain privileges merely by asserting membership in a group named `admin`.

## 3. Where does SAML2 NameID live?

In Web Browser SSO, the SP typically sends an `AuthnRequest` and the IdP returns a `Response` containing an `Assertion`. The user identifier usually resides at:

~~~text
<samlp:Response>                SAML protocol
  <saml:Assertion>              IdP assertion
    <saml:Issuer>...</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format="...">VALUE</saml:NameID>
      <saml:SubjectConfirmation>...</saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions>...</saml:Conditions>
    <saml:AuthnStatement>...</saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

`NameID` is a **subject identifier with semantics asserted by the IdP**. It is **not by itself an email, local user ID, password, session cookie, or application role**. The same display string can refer to different people if the issuer/namespace differs.

Examples of two NameIDs:

~~~xml
<!-- Persistent: simulates a subject reusable across sessions per contract -->
<saml:NameID
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
    NameQualifier="https://idp.partner-a.example/saml"
    SPNameQualifier="https://orders.example/saml2/sp/partner-a">
    p-7b91e
</saml:NameID>
~~~

~~~xml
<!-- Transient: simulates a temporary subject for a single SSO login -->
<saml:NameID
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:transient">
    tmp-6e41
</saml:NameID>
~~~

These are **illustrative XML fragments without signatures**; never use them alone as proof of login. Only read NameID from an **Assertion actually verified by the SAML provider**, after protocol and trust checks pass.

### 3.1. Components of the identity key

- **Issuer / IdP entity ID:** who asserts the identifier? IdP A can issue the same value as IdP B.
- **NameID.Format:** meaning of the value; identical strings under `persistent` and `transient` are not equivalent.
- **NameID.Value:** identifying data within the defined scope; for persistent/transient, treat it as an opaque string rather than decoding subjective meaning.
- **NameQualifier:** namespace of the party creating/naming the identifier if present; typically related to the IdP.
- **SPNameQualifier:** which SP or SP affiliation the identifier may be scoped to.
- **SP entity ID / registration context:** the trust pair the assertion targets. Spring's registration ID is useful for selecting configuration, but **should not be the sole durable key component**, as the app may rename a registration while keeping the same SP entity ID.
- **Tenant:** business scope approved at the SP; never accept it blindly from a user-supplied query parameter.

When qualifiers are absent, there must be an **explicit normalization rule in the contract**. Never arbitrarily treat an absent qualifier as equivalent to some value if that could conflate two identities.

## 4. Persistent NameID: durable, but not a global ID

Standard URI:

~~~text
urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
~~~

In SAML2, the persistent format uses an identifier that is **durable and typically pseudonymous** within a federation relationship, allowing an SP to recognize the same principal across SSO logins **as long as the link is maintained**. This identifier is usually generated for a **specific IdP–SP pair or SP affiliation**, not meant to be shared across all websites by default.

### 4.1. Why durability helps account linking

A Partner A employee has local account `user_104`, permission `ORDER_READ`, and order history in the Orders Portal. The IdP issues persistent NameID `p-7b91e` on the first SSO login; the SP stores an approved link:

~~~text
(issuer=A, sp=Orders, format=persistent, nameId=p-7b91e)
    → local_user_id=user_104
~~~

On subsequent logins, if the IdP continues issuing the same identifier per contract, the SP can locate `user_104` without relying on email, full name, or IdP groups. When the user changes email or name, the identity link **does not necessarily change**.

### 4.2. Persistent can be pairwise

~~~text
Same user in IdP A:
  SP Orders  → persistent value "p-orders-7b91e"
  SP Payroll → persistent value "p-pay-0fa22"

A user in IdP B:
  SP Orders  → persistent value "p-orders-7b91e"
~~~

Even for the same person at IdP A, two SPs can receive **two different pseudonyms**; and even with the same string across IdP A and IdP B, they can be **two different people**. This design limits unintended data correlation across services.

**Persistent does not mean "an absolutely permanent ID".** When an IdP deletes a link, splits a tenant, changes SP entity ID, migrates IdPs, or changes identity policy, the value can change or expire. Therefore, you need an evidence-backed change process rather than a code assumption that the value never changes.

### 4.3. Do not turn a persistent pseudonym into common PII

An opaque identifier is generally better than email/username when the goal is strictly a linking key, because it reduces real-world identity exposure. However, a durable pseudonym can still track users within an SP, so:

- Do not write raw NameIDs to public logs, URL queries, uncontrolled telemetry, or external support tools.
- Do not send a persistent identifier scoped to SP A over to SP B without a linking/affiliation agreement.
- Restrict access to the `external_identity` table and audit all link changes.
- Avoid stuffing email, employee number, or personal details directly into `persistent` format if the agreement expects an opaque pseudonymous value.

## 5. Transient NameID: temporary identifier, not for long-term account keys

Standard URI:

~~~text
urn:oasis:names:tc:SAML:2.0:nameid-format:transient
~~~

SAML 2.0 describes a transient identifier as an **opaque, temporary** value; it is designed for cases where no long-term identity link needs to be established between IdP and SP. Across sessions/SSO logins, the same person can receive different values. Never build a durable `external_identity` solely on a transient value.

~~~text
Day 1: IdP A authenticates An → transient NameID = T-6e41
Day 2: IdP A authenticates An → transient NameID = T-942c

T-6e41 != T-942c
Insufficient evidence for the SP to infer this is the same local user.
~~~

**Do not equate transient NameID with the SP's session ID**: the IdP issues a temporary identifier for the SSO event; after authentication, the SP creates its own session cookie with its own timeout and logout rules. A transient identifier is not a bearer token permitted for arbitrary API calls.

### 5.1. When transient is appropriate

- The application only needs to know the session was authenticated by a trusted IdP, without preserving personal identity across logins.
- Resources use **contractual group/attribute policies** and current context, requiring no persistent local user or personal profile (tenant and permission limits still apply).
- The service only needs short-lived sessions; avoid storing the temporary identifier as a user primary key in the database.
- A privacy-focused model where the SP should not correlate the same person's activity across multiple SSO logins.

Transient **does not automatically guarantee full anonymity**: `AttributeStatement` may still include email/employee ID; IP addresses, SP cookies, or telemetry may also allow identification. Privacy is a property of **overall data and operations**, not just the NameID URI.

### 5.2. When transient is inappropriate

- A portal with orders, transaction history, approval limits, and per-employee accountability audits.
- Business workflows needing to remember users across days or identify a user when revoking an account.
- Requiring linkage to an existing local account holding permissions or in-progress work.
- Granting `APP_ADMIN`, `APP_APPROVE_PAYMENT`, or sensitive permissions based on local account history.

If an IdP only issues transient IDs yet the application requires durable local accounts, there are two governed paths:

1. Negotiate a **persistent NameID** or another identifier proven stable and unique within scope.
2. Use a **stable Attribute guaranteed and verified by the IdP** along with issuer/namespace for account linking; do not arbitrarily pick email just because it is present, and never tie permissions to a transient NameID.

There is no safe third option such as "matching by closest display name".

## 6. Persistent, transient, emailAddress, and unspecified: accurate comparison

| Format | URI | Promise you can rely on | Risk if used as account key |
| --- | --- | --- | --- |
| **persistent** | `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` | Durable identifier within the defined scope. | Forgetting issuer/SP scope, failing to handle migration/termination. |
| **transient** | `urn:oasis:names:tc:SAML:2.0:nameid-format:transient` | Opaque, temporary, for short-lived context. | Creating a new user on every SSO or mis-matching users by guesswork. |
| **emailAddress** | `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress` | Email format; **not** promised by this spec to be an immutable ID. | Email changes/reuse causing account mis-linking. |
| **unspecified** | `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified` | Semantics defined outside the URI. | Assuming the value is a durable object ID when it is actually a reusable username. |

Note that `emailAddress` and `unspecified` use the **SAML:1.1** namespace even in SAML2; do not alter them to `SAML:2.0`.

### 6.1. Is a verified email enough?

No, at least **not enough to automatically link an account with sensitive permissions**. The address `alex@partner.example` can change or be reassigned to another employee. If the SP uses email as a key, a new person receiving the recycled email can be mapped into the previous person's local account.

An email asserted by the IdP in a signed Assertion proves **the IdP made that assertion**; it does not turn email into an immutable identifier and does not let the SP skip link-approval workflows.

### 6.2. Unspecified can be stable, but requires a contract

One partner using `unspecified` with value `object-8f42` might be issuing an immutable directory object ID. Another partner using `unspecified` might send a reusable username. An SP cannot tell them apart just by reading `Format`; it must know the value's **source, lifecycle, and uniqueness scope**, backed by tests and documentation.

### 6.3. Comparing with OIDC `sub`, without equating them

OIDC typically uses the `(iss, sub)` pair to identify a subject; an IdP may issue a **pairwise subject** per client/sector. This is a similar model regarding **scope**, but not the same field, and `SAML NameID` cannot simply be renamed `OIDC sub` without defining protocol and policy. When a system supports both SAML and OIDC, do not merge accounts across protocols merely on matching identifier strings.

## 7. Step-by-step secure account linking flow

### 7.1. Architecture

~~~text
Browser → Trusted IdP → Signed SAML Response
                          |
                          v
                 SP verify protocol
         signature, issuer, audience, ACS,
        InResponseTo, expiry, subject, replay
                          |
                          v
               Read verified identity
            format + value + qualifiers
                          |
             Contractually durable ID?
               /                   \
             Yes                    No
              |                       |
   Lookup external identity      Do not auto-link
              |                  on transient
        Link exists?                  |
          /    \                  Guest/PENDING/
        Yes     No               reject per policy
        |         |
  Check ACTIVE  Provisioning/
  tenant        approval
        |         |
        v         v
    Valid local account?
              |
              v
    Load local permissions + tenant
              |
              v
    Authorization by action/resource
~~~

The **verify SAML** step must occur before any decision to trust an identifier. Do not Base64-decode `SAMLResponse` yourself in a Controller and run a separate XPath query; you risk consuming a different element than the one verified by the signature (**XML Signature Wrapping**).

### 7.2. Recommended link statuses

| Status | Meaning | Typically permitted access |
| --- | --- | --- |
| `UNLINKED` | Valid subject, but no external identity record exists yet. | No business permissions; may view onboarding/guidance screen. |
| `PENDING` | Link or provisioning requested, not yet approved. | Very narrow onboarding steps only. |
| `ACTIVE` | External identity bound to a local user per approved policy. | Permissions determined by local account/tenant and resource policy. |
| `SUSPENDED` | Temporarily paused due to risk, employee leave, or missing data. | Deny business actions. |
| `REVOKED` | Link no longer trusted or terminated. | Do not reuse link; require new approval to establish another link. |

**Note:** "Authenticated by IdP" is an authentication event, not the `ACTIVE` status of a local account. A user disabled in the SP may still have an active IdP account and receive valid assertions.

### 7.3. First login / Just-in-Time provisioning

When encountering an unseen subject:

1. Verify valid Issuer/Signature/Audience/Recipient/Conditions/SubjectConfirmation/Correlation.
2. Classify the identifier: contract-compliant persistent, or transient/email/unspecified requiring separate policy?
3. Look up an external key **in the right namespace**, never searching arbitrarily by email.
4. If no link exists, create a `PENDING` request or reject. If the system supports automatic local account creation, default permissions must be minimal, with a proven tenant.
5. If a user asks to **link to an existing local account**, require proof of control over both the local account and the external identity, applying MFA/approval as needed; never "claim an account" solely by matching email.
6. Write the link inside a transaction with a unique constraint to prevent races between concurrent callbacks.
7. Grant permissions **at the SP** from a governed administrative source; never turn an external group `admin` directly into `ROLE_ADMIN`.
8. Write controlled audit logs: who approved, when, which issuer/SP scope, and why.

### 7.4. Account linking is not account creation

- **Linking:** mapping an IdP-asserted external identity to an **existing local account**.
- **Provisioning:** creating a new local account per policy, possibly synced from SCIM/IdP directory or JIT.
- **Authentication:** verifying a subject at login time.
- **Authorization:** allowing or denying an action on a resource.

A persistent identifier makes linking more stable, but **does not automatically create a local account** or grant permissions. A transient identifier can still be used to log into **a session without long-term user binding**, if SP policy permits.

## 8. Linking key: what scope prevents ambiguity?

### 8.1. Logical key

A typical design in SAML2:

~~~text
ExternalIdentityKey =
    (idp_entity_id,
     stable_sp_scope,
     name_id_format,
     name_qualifier,
     sp_name_qualifier,
     name_id_value)
~~~

In some deployments, certain qualifiers may not be sent by the IdP. In that case, the contract must define how **absence** is represented and accepted, rather than stripping all scope down to just `name_id_value`.

- `idp_entity_id` comes from trust configuration and the verified issuer.
- `stable_sp_scope` is typically the **SP entity ID**, rather than just a Spring registration ID that can be renamed.
- `name_id_format` uses the exact URI, not arbitrary abbreviations.
- `name_qualifier` / `sp_name_qualifier` preserve namespace boundaries when present.
- `name_id_value` is an opaque string; do not arbitrarily lowercase, trim, or speculatively decode it.

**Do not use `registrationId` alone to prove identity:** it is an internal config key for an RP–IdP pair. If `partner-a` is renamed to `supplier-a` while keeping the same issuer/SP entity ID/subject, it may still be the same external identity. Conversely, reusing the same registration ID for a different IdP must be treated as a **trust relationship change**, never auto-merging users.

### 8.2. Recommended data model

~~~sql
-- PostgreSQL architectural example. Not an executable migration in the Java demo.
CREATE TABLE local_user (
    id             BIGINT PRIMARY KEY,
    tenant_id      VARCHAR(100) NOT NULL,
    status         VARCHAR(20) NOT NULL
                   CHECK (status IN ('ACTIVE','SUSPENDED','DISABLED'))
);

CREATE TABLE external_identity (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_user_id     BIGINT REFERENCES local_user(id),
    idp_entity_id     TEXT NOT NULL,
    sp_scope          TEXT NOT NULL,
    name_id_format    TEXT NOT NULL,
    name_qualifier    TEXT NOT NULL DEFAULT '',
    sp_name_qualifier TEXT NOT NULL DEFAULT '',
    name_id_value     TEXT NOT NULL,
    status            VARCHAR(20) NOT NULL
                      CHECK (status IN ('PENDING','ACTIVE','SUSPENDED','REVOKED')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (idp_entity_id, sp_scope, name_id_format,
            name_qualifier, sp_name_qualifier, name_id_value)
);

CREATE TABLE local_permission (
    local_user_id BIGINT NOT NULL REFERENCES local_user(id),
    permission    VARCHAR(100) NOT NULL,
    PRIMARY KEY (local_user_id, permission)
);
~~~

In this example schema, empty string `''` represents a qualifier **that was not provided**. Use this convention only if contract/data analysis proves it cannot collide with a real value. In production, consider `local_user_id IS NOT NULL` constraints when `status=ACTIVE`, foreign keys, indexes, link states, audit tables, encryption/tokenization, and data deletion workflows. **Not all databases treat `NULL` in unique constraints the same way**; key representation must be designed deliberately.

### 8.3. Fields that must never be used to automatically grant permissions

- `email` or `emailAddress` without a lifecycle contract;
- display name, full name, avatar;
- `groups=["admin"]` at the IdP with external group semantics;
- transient NameIDs and session identifiers;
- `tenantId` or `partnerId` sent by the client in query/body;
- an unverified claim or an XML element outside the validated signature scope.

## 9. Change scenarios and how to handle links

### 9.1. User changes email

**Right:** if persistent ID/issuer/SP scope are unchanged, preserve the local link and update email strictly as a profile attribute per policy.  
**Wrong:** creating a new local user because email changed, or granting permissions from an old user by comparing display names.

### 9.2. IdP switches from persistent to transient

This is an **identity contract change**, not a harmless text change. The SP cannot maintain long-term mappings using transient values alone. Pause automatic linking, find a stable alternative identifier, test with the partner, and execute an approved migration. Never "upgrade" transient to "persistent" by altering the Format label at the SP.

### 9.3. IdP changes persistent NameID during a migration

This can happen when migrating tenants, directories, entity IDs, SP affiliations, or pairwise policies. Do not link the new NameID to the old local account merely because emails match. Safe workflow:

1. Freeze a snapshot of old mappings and identify the old and new IdPs.
2. Receive an old→new mapping from a trusted administrative channel with source proof.
3. Verify 1–1 correspondence, no cross-person duplicates, no cross-tenant mixing.
4. Require approval and proof-of-control for sensitive accounts.
5. Execute transactionally with audit logs and rollback support; never "temporarily stitch" two admin accounts without controls.
6. Test active sessions, deprovisioning, permission revocation, cutoff dates, and absent-user handling.
7. After migration, remove dangerous fallbacks by email/username or old NameID per policy.

### 9.4. Two IdPs both issue `p-7b91e`

~~~text
(IdP A, SP Orders, persistent, p-7b91e) → local_user_A
(IdP B, SP Orders, persistent, p-7b91e) → local_user_B
~~~

These are **two distinct external identities**. Even with the same email, do not auto-merge local accounts without proof of control over both identities and approval.

### 9.5. Changing Spring `registrationId`

If only the configuration key name changes while IdP entity ID, SP entity ID, NameID, and qualifiers remain unchanged, the identity link does not need to change. Using registration ID as the sole key risks creating thousands of "new users" after a config rename. Therefore, store **stable trust identifiers** in the identity link table, keeping registration ID as supplementary metadata.

### 9.6. User leaves the company or is locked out

The IdP may disable the account while an SP session still exists. Combine sync provisioning/deprovisioning, local user state, session invalidation, and permission checks at sensitive operations. **The persistent NameID still being the same string** does not prove the local user is still permitted access.

## 10. How does identity affect authorization?

A decision formula for an order-reading API:

~~~text
ALLOW_READ_ORDER(subject, order) =
    validated_saml_assertion(subject)
    AND trusted_issuer_and_scope(subject)
    AND linked_local_account(subject).status == ACTIVE
    AND linked_local_account.permissions CONTAINS "APP_ORDER_READ"
    AND linked_local_account.tenant_id == order.owner_tenant_id
    AND any_business_specific_checks_pass
~~~

An external identity may map stably to `user_104`, yet `user_104` is still **not allowed** to read Partner B's orders. Enforce this in the backend/service/repository, not merely by hiding UI buttons.

| Identity and link | Local permission | Resource | Result |
| --- | --- | --- | --- |
| Valid persistent, linked to active user A | `APP_ORDER_READ` | Order belonging to A | **ALLOW** |
| Valid persistent, linked to active user A | `APP_ORDER_READ` | Order belonging to B | **DENY** |
| Valid persistent, linked to active user A | Lacks `APP_ORDER_READ` | Order belonging to A | **DENY** |
| Valid persistent, linked to disabled user | Any | Any | **DENY** |
| Valid persistent, but unlinked | Claim `groups=admin` at IdP | Any | **DENY** |
| Valid transient SSO, no durable link | No local permission | Any protected order | **DENY** |
| Invalid issuer/signature/audience | Any | Any | **REJECT AUTHENTICATION** |

In Servlet web apps, "unauthenticated" typically causes filters to redirect to login; "authenticated but lacking permission" typically yields **403 Forbidden**. Exact HTTP behavior depends on entry points/API setup. Never use a 403 from local permissions as an excuse to skip SAML verification.

### 10.1. Transient can still serve a service that needs no local user

For example, a public-docs portal that only allows authenticated partners to view content without storing individual profiles. After validating SAML, the SP can establish a **short session** with narrowly scoped permissions defined for a partner/group, without writing the transient NameID into a local account table.

If the business requires per-person audit trails or ownership-based permissions, transient is **insufficient**, and an approved stable identifier is required. Avoid conflating an "authenticated anonymous guest" with a privileged local user.

## 11. Standalone Java 17 example: checking link and permission scope

To make the consequences concrete, the following example simulates **post-SAML verification**: `ExternalKey` data is assumed to have come from an Assertion already checked by a trusted SAML validator. The program **does not** parse XML, verify signatures, or stand up an IdP. It solely demonstrates **local account linking policy and authorization**.

### 11.1. Single file `IdentityLinkDemo.java`

~~~java
import java.util.Map;
import java.util.Set;

public class IdentityLinkDemo {

    static final String PERSISTENT =
        "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent";
    static final String TRANSIENT =
        "urn:oasis:names:tc:SAML:2.0:nameid-format:transient";
    static final String EMAIL =
        "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress";

    static final String IDP_A = "https://idp-a.example/saml";
    static final String IDP_B = "https://idp-b.example/saml";
    static final String SP = "https://orders.example/saml2/sp";

    // This is the key AFTER the SAML provider has verified source and scope.
    // Empty qualifier is only a simulated convention in this example.
    record ExternalKey(
        String issuer,
        String spScope,
        String format,
        String value,
        String nameQualifier,
        String spNameQualifier) {
    }

    record LocalUser(
        String id,
        String tenantId,
        boolean active,
        Set<String> permissions) {
    }

    static ExternalKey identity(
            String issuer, String format, String value) {
        return new ExternalKey(
            issuer, SP, format, value, issuer, SP);
    }

    static boolean canReadOrder(
            ExternalKey identity,
            String orderTenant,
            Map<ExternalKey, LocalUser> approvedLinks) {

        // Trust/scope check: do not trust arbitrary issuers or SPs.
        if (!Set.of(IDP_A, IDP_B).contains(identity.issuer())) {
            return false;
        }
        if (!SP.equals(identity.spScope())) {
            return false;
        }

        // Demo policy allows durable links only with persistent format.
        if (!PERSISTENT.equals(identity.format())) {
            return false;
        }

        LocalUser account = approvedLinks.get(identity);

        // Unlinked identity, disabled user, or wrong permission => deny.
        return account != null
            && account.active()
            && account.permissions().contains("APP_ORDER_READ")
            && account.tenantId().equals(orderTenant);
    }

    public static void main(String[] args) {
        ExternalKey a = identity(IDP_A, PERSISTENT, "p-7b91e");
        ExternalKey b = identity(IDP_B, PERSISTENT, "p-7b91e");
        ExternalKey disabled =
            identity(IDP_A, PERSISTENT, "p-disabled");

        Map<ExternalKey, LocalUser> links = Map.of(
            a, new LocalUser(
                "u-A", "tenant-A", true, Set.of("APP_ORDER_READ")),
            b, new LocalUser(
                "u-B", "tenant-B", true, Set.of("APP_ORDER_READ")),
            disabled, new LocalUser(
                "u-C", "tenant-A", false, Set.of("APP_ORDER_READ"))
        );

        // Both issuers use the same value, yet the keys remain distinct.
        System.out.println("A / own tenant: " +
            canReadOrder(a, "tenant-A", links));
        System.out.println("A / other tenant: " +
            canReadOrder(a, "tenant-B", links));
        System.out.println("B / own tenant: " +
            canReadOrder(b, "tenant-B", links));
        System.out.println("B / A tenant: " +
            canReadOrder(b, "tenant-A", links));

        ExternalKey transientId =
            identity(IDP_A, TRANSIENT, "temporary-001");
        System.out.println("transient / A: " +
            canReadOrder(transientId, "tenant-A", links));

        ExternalKey emailId =
            identity(IDP_A, EMAIL, "an@partner-a.example");
        System.out.println("email / A: " +
            canReadOrder(emailId, "tenant-A", links));

        System.out.println("disabled / A: " +
            canReadOrder(disabled, "tenant-A", links));

        // An identical persistent external key is seen again.
        ExternalKey aAgain = identity(IDP_A, PERSISTENT, "p-7b91e");
        System.out.println("A repeat SSO: " +
            canReadOrder(aAgain, "tenant-A", links));
    }
}
~~~

### 11.2. Compile and run

No Spring, Gradle, or external libraries needed. Use JDK 17 or higher:

~~~bash
javac --release 17 IdentityLinkDemo.java
java IdentityLinkDemo
~~~

**Exact expected stdout:**

~~~text
A / own tenant: true
A / other tenant: false
B / own tenant: true
B / A tenant: false
transient / A: false
email / A: false
disabled / A: false
A repeat SSO: true
~~~

Line-by-line explanation:

1. A has an active persistent link `u-A`, read permission, and matching tenant A → true.
2. A has permission, but the resource belongs to B → false.
3. B has the **same NameID value** as A, but a different issuer; B is linked separately to `u-B`, matching tenant B → true.
4. B cannot read tenant A's resource → false.
5. Transient NameID has no durable link and is excluded from long-term linking by demo policy → false.
6. EmailAddress is not an approved format for durable links in the demo → false, even though the email may look valid.
7. Local user is disabled → false.
8. Repeating the same persistent key resolves the same `u-A` → true.

**Intentional limitations:** this is an in-memory **post-SAML-verification** model with a **hardcoded** issuer allowlist and approved link map. It is not a production SP and has no database, transactions, certificates, sessions/cookies, parsers, SAML signatures, or user provisioning. Never construct `ExternalKey` from unverified HTTP data and expect `canReadOrder` to substitute for SAML verification.

### 11.3. Additions needed for production

- Turn the map into an `external_identity` table with transactions, unique composite key, auditing, and approval workflows.
- Source the trust list from configured `RelyingPartyRegistrationRepository`, not arbitrary URL literals.
- Inspect format and qualifiers in the **verified Assertion**; `getName()` alone cannot reveal the format.
- Store accounts and permissions in the database; enforce per-resource/request permissions with revocation and cache invalidation.
- When the SAML principal or local account lacks info, return **UNLINKED/PENDING/DENIED** rather than guessing from email.
- Use optimistic locking/unique constraints to prevent concurrent callbacks from creating competing links.
- Consider keyed hashing/encryption for identity indexes if leakage risk reduction is required, preserving lookup and rotation; never log raw persistent IDs.

## 12. Applying this in Spring Security SAML2 Login

### 12.1. Spring Security's boundary

A Spring Boot Servlet SP typically looks like:

~~~text
IdP metadata ──> RelyingPartyRegistration
                     |
HTTP SAMLResponse --> SAML processing filter/provider
                     |
              Validation succeeded
                     |
              Saml2Authentication
                     |
              Saml2AuthenticatedPrincipal
                     |
           Local identity linking service
                     |
            User status + local roles
                     |
           Service/resource authorization
~~~

`spring-security-saml2-service-provider` handles SAML login, while the business application designs external identity linking. In Spring Security 6.x branches, `Saml2AuthenticatedPrincipal` supports `getName()` and `getRelyingPartyRegistrationId()`, along with IdP-issued Attributes.

**Important:** `principal.getName()` is usually the NameID value, **not the full NameID XML**; from this string alone you cannot be certain of Format/NameQualifier/SPNameQualifier. `getRelyingPartyRegistrationId()` only identifies the internal registration, not replacing issuer/SP scope checks. If you need to distinguish persistent from transient, extract the details from the **provider-verified Assertion** via the extension point/response converter matching your Spring Security and OpenSAML versions.

### 12.2. Minimal SP configuration to illustrate the authentication layer

Example for **Spring Boot 3.3.x / Spring Security 6.x**, with real IdP metadata. `application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_METADATA_URI}
~~~

`SecurityConfig.java`, placed inside a Spring Boot Servlet app with the Spring Security SAML2 dependency:

~~~java
package com.example.federated;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
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

This snippet only enables **SAML authentication** and checks "is authenticated"; it **does not yet** restrict sensitive APIs by local permission. To avoid misunderstanding, production requires adding service-level authorization such as `@PreAuthorize`/business policies, and linking external identities to local accounts **before granting permissions**.

A `Controller` to observe two basic properties after authentication:

~~~java
package com.example.federated;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {
    @GetMapping("/")
    public String home() {
        return "Visit /me for SAML sign-in";
    }

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return Map.of(
            "nameIdValue", principal.getName(),
            "registrationId", principal.getRelyingPartyRegistrationId()
        );
    }
}
~~~

This sample Controller **does not** return Format or qualifiers. Do not use it as proof that NameID is persistent. In production, also remove or restrict this debug endpoint because identifiers are sensitive.

To enforce persistent/transient policies post-authentication, you need an extension point operating on the validated assertion (or a trusted identity adapter with a matching contract) to construct an `ExternalKey` as in Section 11. **Do not re-parse raw SAMLResponse alongside Spring Security**; you risk reading a different XML element than the one whose signature was verified.

### 12.3. If using Spring Security 7.x

APIs around SAML authentication/principal change across releases, especially with OpenSAML 5 and new assertion representations. **Consult the Javadoc/migration guide for your exact runtime version** before copying 6.x code. The principle stays the same: SAML validation first, external identity link second, local authorization last.

### 12.4. NameIDPolicy is a request, not a guarantee

An SP can request persistent format in `AuthnRequest`:

~~~xml
<samlp:NameIDPolicy
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"/>
~~~

The IdP may not support it, or may follow a different selection policy. Before mapping a durable link, check the **actual received NameID Format** and test at least two logins for the same subject. Sending a request with the persistent URI **does not** automatically make a transient subject stable.

## 13. Mandatory testing before granting real permissions

### 13.1. Test matrix

| Test | Scenario | Expected outcome |
| --- | --- | --- |
| I01 | Persistent NameID stays identical across two SSO sessions for the same user, right issuer/SP scope. | Same external link resolves to the same local user. |
| I02 | Transient NameID changes between two SSO logins. | No durable link created from the transient value. |
| I03 | Two IdPs emit the same persistent value. | Two distinct external identities; no local account mix-up. |
| I04 | Same IdP, but two SPs receive different pairwise persistent values. | Do not guess they are the same user or merge across SPs. |
| I05 | User changes email, persistent ID unchanged. | Still finds the right local user; updates email as profile info. |
| I06 | Old email is reassigned to someone else. | Cannot take over the local account via email matching. |
| I07 | IdP returns `Format=unspecified` without contractual stability proof. | Do not auto-create privileged durable links. |
| I08 | Persistent ID changes during IdP migration. | Handled via proven, approved old→new workflow. |
| I09 | Valid SAML user with no external link yet. | UNLINKED/PENDING; denied access to business APIs. |
| I10 | Linked user whose local account is disabled. | Permission denied, even though IdP authenticates. |
| I11 | User A has `APP_ORDER_READ`, order belongs to B. | DENY due to tenant/ownership. |
| I12 | IdP claim says `groups=admin`, but no local permission exists. | DENY admin functionality. |
| I13 | Two callbacks concurrently create a link for the same external identity. | Only one link committed or controlled conflict reported. |
| I14 | Assertion has bad signature, issuer, audience, recipient, or is expired. | REJECT before account linking. |
| I15 | SP renames Spring registration ID while keeping issuer/SP entity ID. | Does not break links because stable scope is stored. |
| I16 | External link is REVOKED or local permission revoked during an active session. | Policy/session invalidation blocks sensitive actions promptly. |
| I17 | IdP only sends transient IDs, yet SP needs long-term per-person audit. | Request another stable subject / negotiate with IdP, do not fabricate mappings. |
| I18 | NameID carries qualifiers outside the approved scope. | Do not auto-equate identities; handle per contract. |

### 13.2. Practical testing approach

1. Set up a **test IdP** with the SP's exact entity ID and ACS registered, plus a trusted signing certificate.
2. Create two distinct IdP users and two SP tenants; test multiple logins for each person.
3. For IdPs supporting persistent, verify NameID value/Format/qualifiers in test; change email and confirm the link still resolves properly.
4. For transient, perform multiple SSO logins and verify the SP never stores the temporary value as a long-term `local_user_id`.
5. Send two IdPs/registrations with the same NameID string to test composite-key scoping.
6. Test unlinked users, disabled users, revoked links, missing permissions, and cross-tenant orders.
7. Test the migration workflow with one approved old→new mapping and one ambiguous mapping; the ambiguous one must fail closed.
8. Verify logs contain no private keys, raw XML, SAMLResponse, or raw persistent NameIDs outside policy.
9. Use appropriate tools to inspect **real provider-verified Assertions**; never upload real user responses to untrusted debugging websites.

**Completion criteria:** learners can explain why the same person can receive different transient values, why two people from two IdPs can have the same persistent value, and why a valid persistent link still does not permit reading another tenant's resources.

## 14. Common mistakes and fixes

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| "NameID has `Format=persistent`, so use the value alone as a global primary key." | Not globally unique across IdPs/SPs. | Use a composite key with issuer/SP scope/qualifiers. |
| "Transient is just shorter persistent, so store it permanently anyway." | Temporary semantics, not guaranteed repeatable. | Use ephemeral sessions or another stable identifier. |
| Matching local users by IdP email. | Emails can change or be reused. | Approved link by contractually guaranteed identifier. |
| Trusting IdP `groups=admin` as `ROLE_ADMIN`. | IdP group namespaces do not default to SP business privileges. | Local least-privilege mapping. |
| Treating valid SAML authentication as permission to view all resources. | Authentication ≠ authorization. | Check local account, tenant, and resource ownership. |
| Stripping email/lowercasing all NameIDs before comparing. | Opaque identifiers can be case-, character-, and namespace-sensitive. | Preserve values, normalize only per contract. |
| When NameID changes, auto-linking by display name. | Easy account takeover or mis-granted permissions. | Sourced, approved, audited old→new migration. |
| Omitting issuer because registration ID suffices. | Registration ID can be renamed/reused and does not prove source trust. | Store stable issuer/SP entity IDs. |
| Checking only `principal.getName()` to guess Format. | The name string lacks XML NameID metadata. | Read the verified Assertion via version-specific APIs. |
| Decoding raw XML with XPath and using values as authorities. | May read elements unprotected by the signature. | Use standard SAML libraries and safe conversion/validation. |
| Auto-granting permissions to new subjects just because IdP login succeeded. | Any partner employee could gain business privileges. | UNLINKED/PENDING, approval, and privilege-granting policy. |
| Keeping local users active after the partner disables them. | SP sessions or permission caches may linger. | Sync revocation, session invalidation, re-check when needed. |
| Allowing the client to choose `partnerId`/issuer for permission lookups. | User can tamper with parameters to cross tenants. | Derive tenant and issuer from the trusted identity link. |
| Logging raw NameIDs system-wide. | Persistent pseudonyms enable user tracking. | Protect identity data, minimize logs, and limit retention. |

## 15. Pre-production design checklist

- [ ] Confirmed the actual NameID Format URI (`persistent`, `transient`, or another format).
- [ ] For persistent, IdP commits to uniqueness/stability **scoped by issuer and SP**, with deprovisioning/migration workflows.
- [ ] For transient, the application never stores the value as a durable user key.
- [ ] External identity key stores exact issuer, SP scope, format, qualifiers, and value; never email/NameID alone.
- [ ] Unique constraint, transactions, race-condition handling, and auditing exist for account linking.
- [ ] New local accounts do not receive sensitive permissions by default.
- [ ] Tenant and permission sources are governed by the SP or trust contract; never taken directly from query strings.
- [ ] Response/Assertion signature, issuer, audience, recipient, InResponseTo, expiry, and replay are verified before linking.
- [ ] Never parse raw responses outside the provider to obtain a different NameID than what was verified.
- [ ] UNLINKED/PENDING/ACTIVE/SUSPENDED/REVOKED states and an approval workflow exist.
- [ ] A workflow exists for issuer/SP entity ID/NameID changes so privileged accounts are never silently created or merged.
- [ ] When an account or permission is revoked, active sessions also obey revocation policy.
- [ ] Resource-level authorization enforces tenant and ownership on the backend.
- [ ] Tests cover I01–I18 or equivalent, including multiple IdPs and email changes.
- [ ] Logging, telemetry, and NameID storage comply with privacy/security policies.
- [ ] Spring Security/OpenSAML APIs match the runtime version when implementing real converters/validators.

## Key takeaway

> **Persistent NameID** lets an SP link a subject over time **within the agreed IdP–SP scope**; **transient NameID** suits sessions needing no durable recognition and **must not be treated as a long-term account key**. In every case, **verified identity → approved local link → local permission → resource authorization** are four separate steps.

### Official documentation

- [OASIS — SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf), section `Name Identifier Formats` (persistent and transient).
- [OASIS — SAML V2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html), sections **4.4.2**, **5.4.2–5.4.5** on Federation, persistent/transient pseudonyms, and termination.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html), conversion/validation, principals, and the role of local authorization.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html), registrations, IdP metadata, filters, and ACS.
- [Spring Security 6.5 — Saml2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html), attributes and registration ID.
- [Microsoft Entra ID — Customize SAML token claims](https://learn.microsoft.com/entra/identity-platform/saml-claims-customization), examples of IdP NameID Format choices and implementation specifics.

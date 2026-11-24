# NameID, SessionIndex, and Identifying Sessions to Terminate in SAML 2.0 Single Logout

In **SAML 2.0 Single Logout (SLO)**, a `LogoutRequest` does not merely mean "the user wants to leave". The recipient needs to know **which exact subject**, **which federated login session**, and **which corresponding application sessions** must be terminated. The two core pieces of data for scoping are **`NameID`** (the principal identifier within the federation relationship) and **`SessionIndex`** (the session identifier attached by the Identity Provider/Session Authority in `AuthnStatement`).

A mistake can cause security consequences in either direction: deleting only **one** browser session when the logout request covers multiple sessions, or deleting **all** sessions with the same email even though the LogoutRequest only requested ending one specific session. This lesson explains the SAML rules, how to store information at login time, session matching mechanisms in multi-node systems, and how to apply them in **Spring Security Servlet**.

**Takeaway up front:** never use `NameID`, `SessionIndex`, email, or the `JSESSIONID` cookie alone to decide session destruction. You must rely on **verified issuer/IdP + registration/SP + NameID and scope attributes + SessionIndex list (if present) + SLO policy**, and only then determine which local sessions to revoke.

## 1. Distinguishing Identity and Session Objects

| Element | Where Does It Appear? | Meaning | Not Equivalent To |
| --- | --- | --- | --- |
| **`NameID`** | SAML assertion `Subject`; `LogoutRequest` (or `BaseID`/`EncryptedID`). | Principal identifier understood by the IdP and SP within federation scope. | Email, local account ID, Servlet session ID. |
| **`NameID@Format`** | Identifier attribute. | How the identifier is interpreted: `persistent`, `transient`, `emailAddress`, `unspecified`... | A guarantee that the value never changes. |
| **`NameQualifier`, `SPNameQualifier`** | Optional attributes of `NameID`. | Identity provider and SP scope within which a NameID is interpreted. | Decorative parameters that can be arbitrarily ignored. |
| **`AuthnStatement@SessionIndex`** | Assertion issued by the IdP at login. | Federated authentication session index managed by the session authority; used in SLO. | `Assertion@ID`, `Response@ID`, `AuthnRequest@ID`, or `JSESSIONID`. |
| **`LogoutRequest/SessionIndex`** | One or more `<samlp:SessionIndex>` elements in the logout message. | Specifies which federated sessions to terminate when the profile requires/accepts the index. | Account name or logout transaction ID. |
| **`LogoutRequest@ID`** | Attribute on the LogoutRequest itself. | Logout transaction identifier for correlation/replay; `LogoutResponse@InResponseTo` points here. | SessionIndex of the login session. |
| **SP's `HttpSession`** | Servlet application server/Spring Session. | HTTP session between one browser and the SP. | SSO session at the IdP. |
| **Session cookie at the IdP** | Browser and IdP. | SSO session managed by the IdP. | Cookies or session IDs owned by the SP. |

**Example:** two browsers belonging to the same user may have two different `JSESSIONID` values yet the same `SessionIndex` assigned by the IdP on two entries to the same SSO session, depending on the IdP model. Conversely, the same person may re-authenticate into two IdP sessions and receive two different SessionIndexes. Therefore, one `SessionIndex` can map to **multiple** local HTTP sessions at the same SP, while one `NameID` can relate to multiple SessionIndexes.

A LogoutRequest must be interpreted according to **federated session relationships**, not merely a single HTTP callback request.

## 2. SLO Data Originates at SAML Login Time

The SP can only terminate the right sessions if, upon receiving `SAMLResponse`, it retained the information needed for SLO.

### 2.1. `AuthnStatement@SessionIndex` Is Emitted in the Assertion

Simplified example showing only the identity and session structure (signatures, conditions, and other required fields are omitted, so **this is not a valid assertion for real login**):

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion-42" Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z">
  <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
  <saml:Subject>
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
        NameQualifier="urn:example:idp:corporate"
        SPNameQualifier="urn:example:sp:portal">principal-83917</saml:NameID>
  </saml:Subject>
  <saml:AuthnStatement
      AuthnInstant="2026-11-07T02:58:00Z"
      SessionIndex="idp-session-7e3"
      SessionNotOnOrAfter="2026-11-07T11:00:00Z">
    <saml:AuthnContext>
      <saml:AuthnContextClassRef>
        urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
      </saml:AuthnContextClassRef>
    </saml:AuthnContext>
  </saml:AuthnStatement>
</saml:Assertion>
~~~

Distinguishing the markers:

- `Assertion@ID="_assertion-42"`: ID of the assertion, used for assertion replay protection, **not** SessionIndex.
- `AuthnStatement@SessionIndex="idp-session-7e3"`: the session index used when identifying the SLO session.
- `SessionNotOnOrAfter`: declared lifetime limit of the authentication session, **not** a session ID, nor a forced deadline for the SP to delete every local cookie.
- `Subject/NameID`: principal within the IdP/SP relationship; both format and meaningful qualifiers must be stored.

SAML Core makes `SessionIndex` on `AuthnStatement` optional in the general schema. However, per the **Web Browser SSO Profile amended in OASIS Errata 05**, if the IdP supports Single Logout, the relevant `AuthnStatement` must carry `SessionIndex` so the SP can request logout of the right session. **Never assume every assertion on the Internet contains SessionIndex**; verify actual capabilities/profiles and what the IdP emits.

### 2.2. What Must the SP Store After Successful Authentication?

A federated session record may take this form:

~~~text
SamlSessionContext
  registrationId      = corporate
  trustedIdpEntityId  = urn:example:idp:corporate
  spEntityId          = urn:example:sp:portal
  nameId.value        = principal-83917
  nameId.format       = urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
  nameId.nameQualifier   = urn:example:idp:corporate
  nameId.spNameQualifier = urn:example:sp:portal
  samlSessionIndex    = idp-session-7e3
  localAccountId      = user-42
  httpSessionId       = sp-session-A
  authenticatedAt     = 2026-11-07T03:00:00Z
  sessionActive       = true
~~~

This information must come from a **validator-verified SAML assertion**, never by reading raw XML before signature verification or taking values from HTTP queries/RelayState. When SessionIndex is absent, record `missing` explicitly along with the corresponding handling policy; **never fabricate a random SessionIndex** and send it to the IdP as if the IdP had issued it.

To support users with multiple browsers or multiple Spring Boot pods, store records in a shared session registry indexed by:

- **Local HTTP session ID** to revoke a single specific session precisely.
- **(registration, trusted issuer, canonical NameID, SessionIndex)** to find all local sessions tied to one SAML session.
- **(registration, trusted issuer, canonical NameID)** to find principal-related sessions upon receiving a valid LogoutRequest **without SessionIndex from a session authority**, within permitted scope.
- **Local account ID** to revoke all sessions due to account lockout policies (which is a different business operation from SAML SLO).

The table should enforce namespacing by environment/tenant and prevent `NameID` collisions between two IdPs. Sensitive identity data must be access-protected, share consistent TTL/cleanup with sessions, and be purged upon session destruction. Store session indexes verbatim for exact matching rather than lowercasing/uppercasing or trimming unless allowed by the protocol.

## 3. How Does a LogoutRequest Carry NameID and SessionIndex?

Per **SAML Core §3.7.1**, `LogoutRequest` requires **one of** `BaseID`, `NameID`, or `EncryptedID` to identify the principal; `SessionIndex` may appear **0 or more times** at the schema level.

Example **SP-initiated LogoutRequest** targeting one IdP session:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-request-901"
    Version="2.0"
    IssueInstant="2026-11-07T03:30:00Z"
    NotOnOrAfter="2026-11-07T03:35:00Z"
    Destination="https://idp.example.org/saml/slo">
  <saml:Issuer>urn:example:sp:portal</saml:Issuer>
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      NameQualifier="urn:example:idp:corporate"
      SPNameQualifier="urn:example:sp:portal">principal-83917</saml:NameID>
  <samlp:SessionIndex>idp-session-7e3</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Example **IdP-initiated LogoutRequest** for the same principal requesting multiple sessions:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-request-902"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z"
    Destination="https://sp.example.org/logout/saml2/slo">
  <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      NameQualifier="urn:example:idp:corporate"
      SPNameQualifier="urn:example:sp:portal">principal-83917</saml:NameID>
  <samlp:SessionIndex>idp-session-7e3</samlp:SessionIndex>
  <samlp:SessionIndex>idp-session-9f2</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

This XML explains field layout, **without signatures/binding protection**, so it cannot be used as a real LogoutRequest in production. Real messages must also be protected according to the binding and trust relationship.

**Order of significance:**
1. `Issuer`: the party **issuing the logout request**; verify it is a registered partner/role.
2. `NameID` (with format/qualifiers): identifies the **exact principal** within federation scope.
3. Each `SessionIndex`: selects a SAML session belonging to that principal. Multiple indexes mean requesting multiple sessions, not a malformed request.
4. `LogoutRequest@ID`, `IssueInstant`, `NotOnOrAfter`, `Destination`, and signature: protect/bound the **logout transaction**, not HTTP session identifiers.

### 3.1. Important Rule from OASIS Errata 05 (E38)

You must distinguish a **Session Participant** (usually the SP) from a **Session Authority** (usually the IdP):

| LogoutRequest Sender | SessionIndex Rule in SAML SLO Profile |
| --- | --- |
| **SP / session participant** | **MUST include at least one `SessionIndex`** when requesting logout of a federated session. |
| **IdP / session authority** or validly delegated party | **MAY omit SessionIndex** to signify terminating **all applicable sessions of the principal**. |
| Any party sending one/many SessionIndexes | Process only **sessions matching those indexes**, within issuer, principal, registration, and policy scope. |

A common pitfall is that **the element schema allows 0 SessionIndexes**, whereas **the profile imposes stricter rules on an SP acting as session participant**. If the SP lacks SessionIndex, do not arbitrarily treat that as a "log out everywhere" command. Record the missing data, inspect SLO capabilities/stored sessions, and either build a compliant LogoutRequest or perform **local logout** only with honest status/guidance.

Conversely, a **verified IdP acting as session authority** may send a LogoutRequest without SessionIndex; per the profile, that requests terminating **all sessions related to the principal within the request's trust scope**, not all sessions of every account on the SP or across the organization.

### 3.2. NameID Is Not Just a Plain Text String

`NameID` can carry `Format`, `NameQualifier`, `SPNameQualifier`, and `SPProvidedID`. These values carry identity/scoping semantics. For example:

~~~text
Value           = principal-83917
Format          = ...:nameid-format:persistent
NameQualifier   = urn:example:idp:corporate
SPNameQualifier = urn:example:sp:portal
~~~

Do not compare `NameID.value` solely against a local account email: another IdP could use the same string, or the same IdP could issue different identifiers per SP/tenant. Conversely, if NameID is **transient**, it changes between logins; falling back to email to "fix" non-matches can log out the wrong person.

You need **canonical identity matching per IdP/SP contract**: compare format and qualifiers using mutually agreed rules, namespaced by issuer/registration, and bind NameID to the local session at SAML login time. Never downgrade matching strictness when a NameID is unrecognized.

For `EncryptedID`, decrypt using the appropriate private key **after checking policy and signature/source**, then compare against the stored session identity. Never log plaintext NameID, assertion XML, or sensitive user information.

## 4. Decision Table: Which Exact Sessions Must Be Terminated?

Suppose the SP currently holds five local sessions:

| Local HttpSession | Registration / IdP | Verified NameID | SAML SessionIndex |
| --- | --- | --- | --- |
| `browser-A` | `corporate` / IdP-X | `principal-83917` | `idx-01` |
| `browser-B` | `corporate` / IdP-X | `principal-83917` | `idx-02` |
| `browser-C` | `corporate` / IdP-X | `principal-other` | `idx-01` |
| `browser-D` | `partner` / IdP-Y | `principal-83917` | `idx-01` |
| `browser-E` | `corporate` / IdP-X | `principal-83917` | `idx-01` |

`browser-A` and `browser-E` may be two separate HTTP sessions participating in **the same SAML session `idx-01`**.

| **Verified** LogoutRequest | Local Sessions to Target | Explanation |
| --- | --- | --- |
| IdP-X, matching NameID, `SessionIndex=idx-01`. | **A, E** | Same registration/issuer, NameID, and SessionIndex. |
| IdP-X, matching NameID, `SessionIndex=idx-02`. | **B** | Must not delete A/E because they belong to a different SAML session. |
| IdP-X, matching NameID, indexes `idx-01`, `idx-02`. | **A, B, E** | Union of matching sessions; do not delete C/D. |
| IdP-X is a **trusted session authority**, same NameID, **no SessionIndex**. | **A, B, E** | Ends all principal sessions within the right registration/issuer. |
| A session participant sends a request **without SessionIndex**. | **Reject treating as all-sessions command** | Does not comply with SLO profile for session participants. |
| IdP-X, different NameID, `idx-01`. | **C** if matching that NameID | Matching index must never cause deleting another person's session. |
| IdP-Y, `principal-83917`, `idx-01`. | **D** | Same NameID/index text but different registration/issuer. |
| IdP-X, matching NameID, `idx-unknown`. | **No matching session** | Never fall back to "log out all". |

**Never:** use a bare `SessionIndex` to run `DELETE FROM sessions WHERE session_index = ?` if the table holds multiple IdPs/SPs; use username/email to delete all sessions when the request carries a specific index; or blindly interpret "no SessionIndex" as "all sessions" regardless of sender.

### 4.1. Multiple SessionIndexes in the Same Request

`LogoutRequest` allows multiple `<SessionIndex>` elements. The scope-correct algorithm is:

~~~text
if issuer + registration + NameID not verified:
    REJECT

if SessionIndex list is non-empty:
    targets = all local sessions with same scoped identity
              AND sessionIndex in list
else if requester is trusted Session Authority
        AND policy allows all applicable sessions:
    targets = all local sessions of scoped identity
else:
    REJECT or handle per protocol error policy

revoke targets via multi-node-capable session store
audit outcome, send LogoutResponse with appropriate status
~~~

An empty `targets` set **does not mean** all sessions should be destroyed: sessions may have expired, already been revoked, NameID may have changed, or the request may be wrong. Verify the transaction and return status/log per policy without automatically broadening scope.

### 4.2. SessionIndex Does Not Necessarily Correspond to One HttpSession

One IdP session can be linked to multiple tabs/browsers/service nodes; a user may have multiple SP sessions sharing the same or different SAML indexes depending on logins. The storage model needs to be **one-to-many**, not enforcing `UNIQUE(saml_session_index)` on the HTTP session table. If the SP only keeps one `SessionIndex → JSESSIONID` mapping, it may destroy one session and leave others created from the same SAML session alive.

Conversely, **`SessionIndex` is not globally meaningful**: it must be paired with issuer/NameID/registration to prevent collisions.

## 5. RP-Initiated Logout: When the SP Proactively Requests the IdP to End the Session

The **Relying Party (RP)** is the SP/application serving the user. When the user clicks Logout, determine whether the goal is **local logout** or **federated SLO**:

~~~text
User -- POST /logout --> SP
      |
      +--> Local logout:
      |      destroy application HTTP session
      |      no request to IdP / no confirmation of other SPs logging out
      |
      +--> RP-initiated SLO:
             retrieve SAML identity context of current session
             destroy local session per policy
             build LogoutRequest with matching NameID + SessionIndex
             sign/protect message per binding
             send to IdP SingleLogoutService
             await LogoutResponse and verify
             complete flow / report outcome
~~~

### 5.1. Retrieving the Exact NameID and SessionIndex from Original Login

RP-initiated SLO needs to know which `RelyingPartyRegistration` the `Saml2AuthenticatedPrincipal` belongs to, plus the NameID and format/qualifiers used by the IdP at login. If the application maps `Authentication#getName()` to `localUserId` or email, do not assume that string is the `NameID` the IdP will accept for logout. Likewise, **do not generate a new SessionIndex at logout time**; it must correlate with the original `AuthnStatement@SessionIndex`.

Per the Spring Security reference, the default resolver builds LogoutRequest using **Issuer** from SP entityID, **NameID** from `Authentication#getName()`, a transaction ID, and Destination from IdP metadata. That default behavior **should not be misread as automatically supplying every `NameID` qualifier or `SessionIndex` required by every IdP**. For IdPs requiring SessionIndex, inspect the real SAML XML and customize the resolver per your running version's API.

### 5.2. What If SessionIndex Could Not Be Stored?

- When SAML login succeeded without `SessionIndex`, the SP **should not emit an index-less LogoutRequest and describe it as profile-compliant per-session SLO**.
- You may perform **local logout** immediately, explaining that the IdP SSO session may remain and the user could be logged back in automatically.
- If the IdP does not support SLO, perform local logout only; do not call guessed endpoints from the UI.
- When global logout is mandatory under enterprise policy, coordinate with the IdP via a separately governed API/administrative flow; **do not assume** an index-less SLO request from the SP means global logout.
- Add storage of `SessionIndex` from SAML authentication for future logins; never "fix" it by substituting `JSESSIONID`.

### 5.3. Ending Local Session Before or After LogoutResponse?

Spring Security documentation describes **RP-initiated** logout as executing local logout/invalidating the session and then sending `LogoutRequest` to the IdP. If the IdP fails to respond or returns an error, the SP session may already have been deleted. Clearly explain to users: **exiting the current application** does not mean every other SP/IdP session has logged out.

Because `LogoutResponse` may return after the local HttpSession has been invalidated, the framework needs a mechanism to store `Saml2LogoutRequest`/RelayState and `InResponseTo` for correlation; never delete all state yourself before receiving the reply and then skip verification.

## 6. IdP-Initiated Logout: The SP Receives LogoutRequest

When the IdP/session authority initiates logout, it sends a `LogoutRequest` to the **SP's SLO endpoint**. Spring Security uses `Saml2LogoutRequestFilter` along with validators/resolvers to process it.

~~~text
IdP -- signed LogoutRequest --> SP /logout/saml2/slo
                                  |
                                  v
                           Select trusted registration
                                  |
                         Verify issuer + signature
                         destination + time + replay
                         NameID + SessionIndexes
                                  |
                                  v
                     Find sessions in shared registry
                                  |
                         +--------+----------+
                         |                   |
                       match              no match
                         |                   |
                  revoke exact          decide status
                  target sessions       per policy
                         |                   |
                         +--------+----------+
                                  |
                         signed LogoutResponse
                                  |
                           send back to IdP SLO
~~~

### 6.1. Do Not Infer All Sessions from a Single Browser Callback

**An SLO callback arrives only with the current browser**; it might not carry cookies for all sessions needing revocation. If the IdP asks to terminate `idx-01`, multiple HttpSessions across different browsers/tabs/nodes may share that SAML context. Calling only `request.getSession().invalidate()` allows the SP to destroy **only the session attached to the current request** (if any), potentially missing other sessions.

In Spring Security, `saml2Logout` provides the protocol support and filters for SLO. **Do not assume by default** that `.saml2Logout(withDefaults())` revokes all HTTP sessions across every browser and every pod by NameID/SessionIndex. To meet system-wide requirements, design a **shared session registry + revocation service** and integrate it at the right hook with validators/logout handlers.

For SLO calls to the SP, some cross-site browser POSTs may lack cookies due to `SameSite`, or the callback may have no active application HTTP session at all. Therefore you cannot rely solely on the current HttpSession to identify the principal; use the verified request and a trusted registry, while **never allowing unverified logout requests to revoke another user's sessions**.

### 6.2. Selecting Target Sessions With/Without an Index

1. **Verify source:** registered IdP issuer, signature and binding, Destination matching SLO URL, expiration/IssueInstant, request ID replay protection, and registration trust.
2. **Verify principal:** exact NameID by format/qualifier/issuer/SP scope. For `EncryptedID`, decrypt validly before matching.
3. **If SessionIndex is present:** select all local sessions having the exact tuple `(registration, issuer, scopedNameID, sessionIndex)`; there may be multiple HTTP sessions.
4. **If SessionIndex is absent:** treat as "all principal-related sessions" only when the requester **is verified as a session authority** and SLO policy permits it.
5. **Execute revocation:** invalidate the selected local sessions via the shared registry/store and write an audit entry; never delete sessions of another IdP/tenant/subject.
6. **Return response:** build a `LogoutResponse` to the IdP SLO endpoint, with `InResponseTo` matching the request ID and a status reflecting reality; handle partial failures.

**Never match on NameID once and log out any user sharing that name or email.** Never treat an unknown/unmatched SessionIndex as license to ignore scope boundaries.

## 7. LogoutResponse, Correlation, and Partial Logout Status

Sample SAML response (simplified for explanation, unsigned):

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-response-902"
    InResponseTo="_logout-request-901"
    Version="2.0"
    IssueInstant="2026-11-07T03:30:10Z"
    Destination="https://sp.example.org/logout/saml2/slo">
  <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

**`InResponseTo` points to the LogoutRequest ID, not SessionIndex.** The SP needs to know which request it sent, to which IdP, over which binding and endpoint; then verify response, signature, and status. Spring Security's `Saml2LogoutRequestRepository` supports storing the request to compare `RelayState` and `InResponseTo`.

**`PartialLogout`** may occur, or part of the application fleet may fail to terminate sessions. Never report "all sessions deleted" if the shared registry failed, another node did not revoke sessions, or the IdP never received a reply. On failure, prioritize **no longer accepting local sessions already known to need revocation**, return an accurate error/status, and apply retry/audit per operational runbooks.

**Completing SLO does not mean all tokens/API keys are revoked.** The SP may use stateless JWTs or long-lived refresh tokens; terminating access requires checking token revocation, TTL, session versioning, or account security state accordingly.

## 8. Multi-Node Deployment: A Session Registry Is the Foundation

Suppose a Spring Boot application runs behind a load balancer with nodes A/B/C:

~~~text
                  IdP
                   |
             LogoutRequest
                   |
             Load Balancer
                   |
        +----------+----------+
        |                     |
      Node A                Node B
        |                     |
        +----------+----------+
                   |
       SHARED SESSION CONTEXT / INDEX
       key=(registration, issuer, NameID, SessionIndex)
           |             |
           v             v
     browser-A        browser-E
     HTTP session      HTTP session
           |             |
           +------ atomic revoke --------+
                                         |
                              HTTP sessions invalidated
                              or marked revoked in shared store
~~~

Logical schema may include:

~~~text
saml_session_binding
  registration_id
  idp_issuer
  sp_entity_id
  name_id_value_or_protected_key
  name_id_format
  name_qualifier
  sp_name_qualifier
  sp_provided_id
  saml_session_index
  http_session_id
  local_account_id
  created_at
  expires_at
  revoked_at
  UNIQUE(http_session_id, registration_id)

INDEX(registration_id, idp_issuer, scoped_name_id, saml_session_index)
INDEX(registration_id, idp_issuer, scoped_name_id)
~~~

This schema is illustrative, not a SQL migration. `scoped_name_id` can be an internal normalized/HMAC key to reduce data exposure in indexes; design format/qualifier normalization and key rotation carefully. Never store plaintext sensitive NameIDs in metrics or URLs.

### 8.1. Preventing Races Between Logout and New Logins

A real-world hazard:

~~~text
T0: IdP initiates logout of session idx-01.
T1: Node A reads registry, finds HTTP sessions A/E.
T2: Node B just created HTTP session F from an old SAML callback.
T3: Node A invalidates A/E, yet F remains active.
~~~

To avoid missing sessions, maintain a **revocation marker** or shared SAML session state:

- Mark the tuple `(registration, issuer, scopedNameID, SessionIndex)` as `REVOKED` or `LOGOUT_IN_PROGRESS` **before or atomically with** selecting local sessions.
- Any new login/session attempting to use the same revoked SAML session must be rejected per policy until there is proof of a new valid IdP session; **do not clear** the marker via an old callback.
- Find and revoke all matching local sessions in the shared registry, including sessions created right around logout time.
- Use transactions/CAS or appropriate atomic/consistent primitives; avoid gaps between SQL/Redis/revocation stores that leave invalid access active.
- If unsure whether every node has completed revocation, do not report full SLO success. Write audit logs and reconcile using an idempotent retry policy.

**Do not treat a bare `DEL sessionId` command as "distributed logout completed".** You must know which SAML context that session ID belonged to, where else tokens were issued, and whether in-flight requests hold an authentication snapshot.

### 8.2. Redis/SQL or Spring Session?

| Solution | What It Can Do | What It Does Not Solve Automatically |
| --- | --- | --- |
| **Spring Session** with Redis/JDBC | Stores shared HTTP sessions and supports invalidating sessions by ID/configured lookup. | Does not auto-discover SAML NameID/SessionIndex unless mapping is stored. |
| **Spring Security SessionRegistry** | Manages/looks up sessions by principal in applicable setups. | May lack IdP+NameID+SessionIndex scoping, or fail to share across nodes if in-memory. |
| **SAML session link table** in DB | Queries by namespace/NameID/SessionIndex, auditing, and revocation. | Requires transactions and synchronization with the HTTP session store. |
| **Redis index/sets** | Fast lookup of multiple local session IDs, TTL, revocation markers. | Requires atomic updates, cleanup, and clear eviction/failover policies. |
| **Only `HttpServletRequest.getSession().invalidate()`** | Destroys the local session attached to the current request. | Does not revoke sessions on other browsers or across multiple SessionIndexes for one NameID. |

In production, verify which `FindByIndexNameSessionRepository`/session indexing actually exists in your Spring Session version, permissions across nodes, and disabled-session policies. Never grant blanket admin lookup over all sessions sharing an email just to make queries easier.

### 8.3. What If the Registry Is Unavailable?

Suppose the IdP asks to destroy `idx-01` while the shared session store times out: **do not swallow the error and return "Success – all done"**. Prioritize fail-safe access control (recording revocation in durable storage or blocking acceptance of the related session), return an error/partial status per the SLO contract, and alert operations. If only local logout could run, clearly state the unconfirmed scope.

## 9. Spring Security SAML 2.0 Logout: Components to Know

Spring Security Servlet provides **RP-initiated** and **AP-/IdP-initiated** SAML SLO capabilities when the IdP supports them and the registration is enabled.

| Component | Role |
| --- | --- |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | When SP initiates logout, builds/sends LogoutRequest to the IdP via the configured resolver. |
| `Saml2LogoutRequestResolver` (e.g., `OpenSaml5LogoutRequestResolver`) | Creates, signs, and serializes LogoutRequest, including NameID/SessionIndex values required by IdP/profile. |
| `Saml2LogoutRequestFilter` | Handles LogoutRequests sent by the IdP to the SP. |
| `Saml2LogoutRequestValidator` | Validates requests; extensible to enforce NameID/SessionIndex matching and policy. |
| `Saml2LogoutResponseResolver` | Generates validly signed LogoutResponses back to the partner. |
| `Saml2LogoutResponseFilter` | Receives/validates LogoutResponses for the SP-initiated flow. |
| `Saml2LogoutRequestRepository` | Stores outstanding LogoutRequests to verify correlated responses via RelayState/InResponseTo. |
| `RelyingPartyRegistration` | Configures IdP/entityIDs/metadata, SLO endpoints, signing/verification credentials, and bindings. |

### 9.1. Minimal Configuration (Spring Boot Servlet)

Example `application.yml` using hypothetical **IdP metadata**, with the SP holding a private key/certificate to sign LogoutRequests/LogoutResponses:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
            signing:
              credentials:
                - private-key-location: classpath:credentials/sp-signing.key
                  certificate-location: classpath:credentials/sp-signing.crt
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
~~~

The `credentials/...` paths are illustrative: real systems must supply keys in the proper format (e.g., PKCS#8) and protect the private key. IdP metadata must publish an appropriate `SingleLogoutService`; the SP must have its SLO URL registered at the IdP with proper HTTPS/certificate/issuer configuration.

File `src/main/java/example/federation/SamlLogoutSecurityConfig.java`:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlLogoutSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is **configuration code within a Spring Boot project** and **cannot compile standalone with JDK alone**; it requires `spring-security-saml2-service-provider`, IdP metadata, and a valid registration. **Important:** enabling `saml2Logout` with a signing key **only activates protocol capability**; it does not prove `SessionIndex` was saved at login or that all HTTP sessions in scope are revoked. Verify with integration tests and customize resolvers/validators/session registry where needed.

Common paths:
- **`POST /logout`**: triggers SP logout; when SLO is configured and the principal qualifies, can emit a LogoutRequest to the IdP.
- **`/logout/saml2/slo`**: SP receives SLO `SAMLRequest` or `SAMLResponse` over the configured binding; typically POST.
- **`/login/saml2/sso/{registrationId}`**: ACS receiving login SAMLResponse; **not** an SLO endpoint.

Routes/bindings can be customized; keep runtime, IdP/SP metadata, and `RelyingPartyRegistration` synchronized. Never disable CSRF app-wide to support SLO; leave only the framework-protected SAML callback open while continuing to verify signatures/sources.

### 9.2. Customizing NameID and SessionIndex in LogoutRequest

Current Spring Security documentation describes `OpenSaml5LogoutRequestResolver` having **`setParametersConsumer`** to populate/modify fields in LogoutRequest before signing/serialization. If your app uses `OpenSaml4LogoutRequestResolver` or a different Spring Security release, APIs and types may differ; adhere to your exact version.

Customization flow **at the architectural level**:

~~~text
On SP logout:
  auth = current authenticated Saml2 principal
  reg  = trusted RelyingPartyRegistration attached to auth
  ctx  = server-side SamlSessionContext for this SP HTTP session

  verify ctx.registration and ctx.nameId against auth/reg
  require ctx.samlSessionIndex for per-session SP-initiated SLO

  buildLogoutRequestWithSpringResolver(reg)
  set NameID:
    value, Format, NameQualifier, SPNameQualifier, SPProvidedID
    from the verified original login context
  add samlp:SessionIndex using ctx.samlSessionIndex
  sign/serialize using framework with SP signing credentials
  send via registered IdP SingleLogoutService binding/location
~~~

This is **pseudocode**, not ready-to-copy class/method names. Never concatenate XML strings manually or sign with a certificate taken from the request. **Never replace NameID with an email or local account ID merely because `Authentication#getName()` holds that value.** Start from the properly formatted NameID stored at SAML login and inspect the generated XML after the Spring resolver runs.

When multiple `AuthnStatement`/SessionIndex entries appear in the same assertion, define a strategy per the IdP's profile and store **all relevant indexes** rather than picking one arbitrarily. When sending SLO from the SP for a session, the SessionIndex list must accurately represent the session(s) the SP intends to terminate.

### 9.3. Extending IdP-Initiated LogoutRequest Handling

When customizing matching/revocation, you should:

1. **Delegate to the default `Saml2LogoutRequestValidator`** of your version to verify signature, issuer, destination, and principal within supported scope.
2. Add checks for NameID qualifiers, session authority, and SessionIndex list; reject when proper identification fails.
3. Map into the shared session registry using the exact key/namespace.
4. Perform revocation **after the request is verified and before issuing a successful LogoutResponse**.
5. Support controlled retry/idempotency handling and LogoutRequest@ID replay protection.
6. If complete revocation fails, determine the response status and report operational alerts honestly.

**Implementation note:** `Saml2LogoutRequestValidator` only validates the message; finding/destroying *multiple* HttpSessions requires a dedicated **session-revocation service**. Never turn the validator into an untransactional DB write or silently act before the signature is valid. Similarly, never assume the default filter knows all user sessions across other pods.

## 10. Java 17: Simulating Exact Selection of Sessions to Terminate

The following program **runs standalone with Java 17**. It demonstrates the algorithm for **selecting local sessions** by trusted registration, issuer, NameID, and SessionIndex. The code **does not validate XML/signatures, does not access Redis/SQL, and does not actually invalidate HttpSessions**. The `verified`/authority role arguments must come from a `LogoutRequest` already verified by the Spring/OpenSAML validator; never call this function with unverified HTTP request data.

File `SamlLogoutSessionSelectionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class SamlLogoutSessionSelectionDemo {
    record NameId(String value, String format,
                  String nameQualifier, String spNameQualifier) {}

    record LocalSession(String httpSessionId, String registration,
                        String trustedIdpIssuer, NameId nameId,
                        String samlSessionIndex) {}

    record Selection(boolean allowed, List<String> httpSessionIds) {}

    static Selection selectTargets(
            List<LocalSession> sessions,
            String registration,
            String verifiedIssuer,
            NameId verifiedNameId,
            List<String> requestedSessionIndexes,
            boolean trustedSessionAuthority) {

        // Session participant missing index: do not turn into all-sessions.
        if (requestedSessionIndexes.isEmpty() &&
                !trustedSessionAuthority) {
            return new Selection(false, List.of());
        }

        List<String> targets = new ArrayList<>();
        for (LocalSession session : sessions) {
            if (!session.registration().equals(registration)
                    || !session.trustedIdpIssuer().equals(verifiedIssuer)
                    || !Objects.equals(session.nameId(), verifiedNameId)) {
                continue;
            }

            boolean match = requestedSessionIndexes.isEmpty()
                    || requestedSessionIndexes.contains(
                        session.samlSessionIndex());

            if (match) {
                targets.add(session.httpSessionId());
            }
        }

        targets.sort(Comparator.naturalOrder());
        return new Selection(true, List.copyOf(targets));
    }

    public static void main(String[] args) {
        NameId alice = new NameId("principal-83917",
                "persistent", "idp-X", "sp-portal");
        NameId bob = new NameId("principal-other",
                "persistent", "idp-X", "sp-portal");

        List<LocalSession> sessions = List.of(
            new LocalSession("browser-A", "corporate",
                    "idp-X", alice, "idx-01"),
            new LocalSession("browser-B", "corporate",
                    "idp-X", alice, "idx-02"),
            new LocalSession("browser-C", "corporate",
                    "idp-X", bob, "idx-01"),
            new LocalSession("browser-D", "partner",
                    "idp-Y", alice, "idx-01"),
            new LocalSession("browser-E", "corporate",
                    "idp-X", alice, "idx-01")
        );

        System.out.println(selectTargets(sessions,
                "corporate", "idp-X", alice,
                List.of("idx-01"), false).httpSessionIds());

        System.out.println(selectTargets(sessions,
                "corporate", "idp-X", alice,
                List.of("idx-01", "idx-02"), false).httpSessionIds());

        System.out.println(selectTargets(sessions,
                "corporate", "idp-X", alice,
                List.of(), true).httpSessionIds());

        System.out.println(selectTargets(sessions,
                "corporate", "idp-X", alice,
                List.of(), false).allowed());

        System.out.println(selectTargets(sessions,
                "corporate", "idp-X", alice,
                List.of("idx-unknown"), false)
                .httpSessionIds().isEmpty());
    }
}
~~~

Compile and run:

~~~bash
javac SamlLogoutSessionSelectionDemo.java
java SamlLogoutSessionSelectionDemo
~~~

**Deterministic output:**

~~~text
[browser-A, browser-E]
[browser-A, browser-B, browser-E]
[browser-A, browser-B, browser-E]
false
true
~~~

Explanation:

1. A request with `idx-01` selects only **A and E** even though session **C** also has `idx-01`, because C belongs to a different NameID; D belongs to a different IdP/registration.
2. A list of two indexes `idx-01`, `idx-02` selects **A, B, E**.
3. When a **verified trusted session authority** omits SessionIndex, it selects **all local sessions belonging to that principal in scope**, excluding C/D.
4. A session participant omitting an index receives `allowed=false` rather than switching to full logout.
5. An unknown index yields an empty list with no fallback to all sessions.

**Important limitation:** the demo uses a four-field `NameId` to illustrate scope; real NameIDs may also carry `SPProvidedID` and qualifier rules per IdP contract. It does not verify issuer or authority, does not handle encrypted NameID, multi-node/races, timestamps, logout request replay, and does not perform invalidation. Production requires trust evaluation first, a shared session registry, and appropriate atomic revocation.

## 11. Security and Accuracy Testing

| Scenario | Expected Outcome |
| --- | --- |
| Valid `LogoutRequest` with matching issuer, NameID, `idx-01`. | Revoke only local sessions in the same scope with `idx-01`. |
| Two HTTP sessions share the same NameID and `idx-01`. | Revoke **both** if belonging to the same requested federated/SAML session. |
| Same `idx-01` but different NameID. | **Do not** delete the other user's session. |
| Same NameID string and index but different issuer/registration. | **Do not** delete another IdP/tenant's session. |
| `NameID@Format` or qualifier mismatch. | Do not fall back to email/bare-string comparison; verify per contract. |
| Request has two SessionIndexes. | Revoke the union of sessions matching both indexes; select no other indexes. |
| Valid IdP session authority sends request without index. | Revoke all principal-related sessions within exact scope per policy. |
| SP participant sends request without index. | Reject/non-compliant; do not process as all-sessions. |
| Request has index not found. | Do not broaden scope; handle no-match/status per policy. |
| `EncryptedID` fails decryption. | Do not delete sessions; handle verification error. |
| Bad signature, unknown issuer, or wrong Destination. | **Do not** perform invalidation. |
| Replayed or expired LogoutRequest. | Reject or handle idempotently per policy; prevent wrongful actions. |
| LogoutResponse with non-matching `InResponseTo`. | Do not treat as logout confirmation for the current request. |
| IdP does not respond after RP-initiated SLO. | Do not claim all apps logged out; local SP may be logged out. |
| Browser IdP-initiated callback lacks SP cookie. | Rely on verified LogoutRequest and registry, not solely on current HttpSession. |
| One session destroyed while another node creates a session from old callback. | Revocation marker protects; no new session survives for the ended session. |
| Session store/registry partially fails. | Do not report full Success; fail-safe and audit. |
| SLO revokes local HTTP sessions while API JWT stays alive. | Revocation/token policy must prevent continued use beyond SLA. |
| LogoutResponse contains `PartialLogout`. | Reflect partial success; do not mask errors or infer completion everywhere. |
| User holds admin and regular accounts at same IdP with different session indexes. | Do not delete the wrong session; organization-wide revocation is a separate operation. |

### 11.1. Observability Data and Incident Investigation

Audit logs should stay minimal:

~~~text
event=SAML_SLO_REQUEST_VERIFIED
time_utc=2026-11-07T03:30:00Z
registration=corporate
verified_issuer=urn:example:idp:corporate
nameid_scope_hash=sha256:ab12...
requested_session_indexes_count=2
selected_local_sessions=3
revoked_local_sessions=3
outcome=SUCCESS
correlation_id=slo-req-901
~~~

The data above is a design example, **not default Spring Security metrics**. Never log raw personal NameIDs, sensitive SessionIndexes, raw `SAMLRequest`/`SAMLResponse`, cookies, signing keys, or user info in public audit logs. Log counts of selected/revoked sessions, registry errors, correlation, and partial status to cross-check with the IdP.

## 12. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Using bare `NameID`/email as global logout key. | Deletes wrong user's or wrong IdP/tenant's sessions. | Scope by registration, trusted issuer, and full NameID. |
| Using `SessionIndex` alone as key. | Collisions across issuers, users, SPs. | Combine identity scope with SessionIndex. |
| Using `JSESSIONID` as `SessionIndex`. | IdP fails to recognize session due to wrong identifier space. | Store original SessionIndex from AuthnStatement. |
| Using `AuthnRequest@ID` or `Assertion@ID` as SLO index. | Mismatch between transaction ID and session ID. | Extract `AuthnStatement@SessionIndex`. |
| Always logging out all sessions when SessionIndex is absent. | A session participant's non-compliant request triggers overly broad logout. | Distinguish session authority vs. participant properly. |
| Assuming one SessionIndex equals one HttpSession. | Leaves other browsers sharing the same federated session logged in. | One-to-many registry revoking all targets in scope. |
| Calling only `request.getSession().invalidate()` on IdP-initiated SLO. | Misses sessions on other browsers or callbacks missing cookies. | Shared session registry and revocation. |
| Enabling `saml2Logout` and assuming cluster-wide SLO is done. | Lacks NameID/SessionIndex mapping or cross-node invalidation. | Integrate session index/revocation service and test end-to-end. |
| Taking NameID from `Authentication#getName()` without checking IdP. | May send local user ID/email instead of SAML session NameID. | Preserve original NameID with Format/qualifiers. |
| Skipping LogoutRequest signature/trust checks. | Attacker can forge SLO to log out other users. | Default validator + policy; reject before side effects. |
| Skipping `LogoutResponse@InResponseTo` checks. | Forged/late responses treated as confirming current transaction. | Store original request and correlate once. |
| Reporting Success on store timeout. | IdP thinks all sessions ended while SP session remains alive. | Fail-safe, PartialLogout/error, retry, and audit. |
| Only deleting cookies when user logs out. | JWT/refresh tokens and other-browser sessions stay alive. | Scoped session/token revocation. |
| Putting raw NameID/SessionIndex and SAML XML in URLs/logs. | Data/PII leak and replay risks during uncontrolled debugging. | Protect session registry and mask/hash logs. |

## 13. Production Deployment Checklist

1. Does the IdP's SAML metadata include `SingleLogoutService` with the right binding/location and valid verification certificate?
2. Does the SP have signing credentials, a working SLO callback, and consistent SP metadata?
3. At login, does the application store **trusted issuer/registration + full NameID semantics + SessionIndex from AuthnStatement**?
4. For RP-initiated SLO, does the LogoutRequest carry the exact NameID and at least one SessionIndex per profile?
5. For IdP-initiated SLO without SessionIndex, does policy verify session authority and revoke only **applicable sessions** within proper scope?
6. When an index is present, does the algorithm select **all local sessions matching the tuple** without deleting sessions for the same username having a different index?
7. Are one-to-many `SessionIndex → HttpSession`, multiple browsers, and multiple nodes handled?
8. Are signature/issuer/destination/IssueInstant/expiry/replay of LogoutRequest verified **before revocation**?
9. Are `LogoutResponse@InResponseTo`, RelayState, status, and trust correlated before announcing SLO success?
10. Does the shared session registry support atomic revocation, concurrency, failover, cleanup, and auditing?
11. When the registry fails or logout is partial, does the application fail safely and report status honestly?
12. Is there a JWT/refresh token revocation policy if stateless APIs are used?
13. Are there tests for sessions sharing NameID with different issuer/index, two browsers sharing an index, and callbacks missing cookies?
14. Is PII controlled across registries, logs, and dashboards?

## 14. Self-Check Knowledge Questions

1. **What question does `NameID` answer?** — Who the principal is under the IdP/SP relationship and format/qualifier scope.
2. **Where does `SessionIndex` come from?** — From `AuthnStatement@SessionIndex` of the IdP-issued SAML assertion verified at login.
3. **Is `LogoutRequest@ID` a SessionIndex?** — No; it is the logout transaction ID referenced by `LogoutResponse@InResponseTo`.
4. **Is an SP sending a LogoutRequest without SessionIndex compliant with the SLO profile?** — Per OASIS Errata 05 E38, a session participant **must include at least one** SessionIndex.
5. **Why might an IdP omit SessionIndex?** — When acting as a valid session authority, to signify logging out **all applicable sessions of the principal** within scope and policy.
6. **Do two local sessions sharing the same SAML index have the same `JSESSIONID`?** — Not necessarily; they can be two different HTTP sessions.
7. **Can email matching alone decide who gets logged out?** — No; issuer, registration, and scoped NameID are required.
8. **If an IdP SLO callback lacks an SP cookie, can a registry be used?** — Yes, once the request is verified and the registry holds trusted mappings; never trust unverified data.
9. **When encountering an unknown index, should we fall back to logging out all sessions?** — No.
10. **Once the SP session is deleted, are all API JWTs/tokens revoked?** — No; a separate token revocation mechanism is needed.
11. **Does enabling Spring Security `saml2Logout` mean all browser sessions are automatically handled?** — Do not assume so; test and implement proper session indexing.
12. **Does not receiving a LogoutResponse mean local logout failed?** — Not necessarily; the local session may already be destroyed, only federation-wide SLO remains unconfirmed.

## References

- [OASIS SAML 2.0 Core — LogoutRequest, NameID, and SessionIndex (§3.7.1)](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML 2.0 Profiles — Single Logout (§4.4), Web Browser SSO (§4.1)](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
- [OASIS SAML 2.0 Errata 05 — E38: SessionIndex in LogoutRequest and Session Authority](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html)
- [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html)
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security API — Saml2LogoutRequestResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestResolver.html)
- [Spring Security API — SAML logout package and request/response filters](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/package-summary.html)
- [Spring Session — Redis-backed HttpSession](https://docs.spring.io/spring-session/reference/guides/boot-redis.html)

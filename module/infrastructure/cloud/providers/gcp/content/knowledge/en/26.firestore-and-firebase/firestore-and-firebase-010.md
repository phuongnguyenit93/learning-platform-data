# Firebase Authentication and Identity Platform

> **Chapter:** Firestore and Firebase  
> **Lesson:** Firebase Authentication and Identity Platform  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from projects, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases, while learning how to choose services, protect resources, automate releases, and monitor reliability and cost. For Java applications with web/mobile frontends, **end-user authentication** is a separate layer from the **backend's service account identity**.

**Firebase Authentication** lets applications sign in users with email/password, Google and supported providers, phone numbers, or custom authentication; Firebase client SDKs manage sign-in sessions and supply **Firebase ID tokens**. **Identity Platform** is Google Cloud's Customer Identity and Access Management (CIAM) platform and serves as the backend for **Firebase Authentication with Identity Platform** once upgraded. Beyond basic sign-in methods, Identity Platform adds **SAML, OIDC, multi-factor authentication (MFA), multi-tenancy, blocking functions, and enterprise options**.

Most important rule: **successful authentication does not mean permission to read or modify any data**. Java APIs must verify tokens and enforce business authorization; Firebase clients accessing Firestore must satisfy **Security Rules**; Java server SDKs accessing Firestore use **Google Cloud IAM** and are not restricted by Security Rules. Examples in this lesson use only test projects and test users. Never enable providers, alter IAM, send SMS, or create real users outside an approved sandbox.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **Firebase Authentication**, **Firebase Authentication with Identity Platform**, **Identity Platform**, **Google Cloud IAM**, and **Firebase App Check**.
2. Explain sign-in → **ID token / refresh token** → verification in the Java backend → **domain authorization**.
3. Choose among email/password, social/OAuth, phone, anonymous, custom tokens, OIDC, or SAML based on requirements.
4. Use the **Firebase Web SDK** to sign in and send an **ID token over HTTPS** to a Java API.
5. Initialize the **Firebase Admin Java SDK via ADC** and safely run `verifyIdToken`/revocation checks.
6. Distinguish **custom tokens** from **Firebase ID tokens**, session cookies, custom claims, and Google Cloud IAM permissions.
7. Design Firestore Security Rules around `request.auth.uid` while understanding server SDK limits.
8. Identify needs for **MFA, multi-tenancy, and blocking functions** before upgrading to Identity Platform.
9. Troubleshoot 401/403 errors, project/tenant mismatches, stale tokens, quotas, and MAU/SMS billing.
10. Plan deployment, testing, and permission revocation using a Java Orders API example.

## 2. Authentication Architecture for Java + Firebase Apps

~~~mermaid
sequenceDiagram
    participant U as User
    participant Web as Firebase Web/Mobile SDK
    participant Auth as Firebase Auth / Identity Platform
    participant Java as Cloud Run Java Orders API
    participant DB as Firestore
    U->>Web: Enter sign-in credentials
    Web->>Auth: Authenticate with provider
    Auth-->>Web: Firebase ID token + refresh token
    Web->>Java: HTTPS Authorization: Bearer ID_TOKEN
    Java->>Java: Verify signature, project, expiry, optional revocation
    Java->>Java: Check uid, tenant, role, and order ownership
    Java->>DB: Server SDK via runtime service account + IAM
    DB-->>Java: Data permitted by IAM
    Java-->>Web: JSON / 401 / 403
~~~

### 2.1. Four identities never to confuse

| Component | Identity | Verification mechanism |
|---|---|---|
| **End user** | Firebase `uid` in ID token | Firebase Authentication / Identity Platform |
| **Mobile/web client** | Firebase app configuration and App Check token if enabled | Firebase App Check verifies app/device; **never replaces user auth** |
| **Java Cloud Run service** | Runtime **service account** | Google Cloud IAM when calling Firestore, Pub/Sub, Cloud SQL, etc. |
| **Developer/CI deployer** | Human/CI principal | IAM deployment, service account impersonation, and audit |

**A Firebase `uid` is not a service account email.** A user signing in with Google does not automatically receive `roles/datastore.user` or `roles/run.invoker` in the project. Conversely, a Java runtime SA having Firestore IAM access **does not prove an HTTP caller is allowed to view another tenant's orders**.

### 2.2. Two paths to Firestore

~~~mermaid
flowchart LR
    User["Mobile/Web client"] --> Auth["Firebase Authentication"]
    Auth --> Rules["Firestore Security Rules"]
    Rules --> Firestore["Firestore Native database"]
    API["Java backend"] --> Verify["Verify Firebase ID token<br/>+ business authorization"]
    Verify --> IAM["Runtime SA + Google IAM"]
    IAM --> Firestore
~~~

- **Firebase Client SDK**: Security Rules evaluate `request.auth`, document conditions, and incoming/existing data to decide access.
- **Firebase Admin SDK / Google Cloud server SDK**: privileged via **IAM**; **bypasses Security Rules**. Caller authentication and authorization live in the Java API.
- **Datastore-mode or MongoDB-compatible access**: does not apply Firebase Rules like the Native client SDK; evaluate security per that API/mode.

Never set Rules to `allow read, write: if false` and conclude the Java server cannot read data; nor should you grant IAM to Cloud Run expecting mobile phones to query Firestore with server permissions.

## 3. Choose Firebase Authentication or Identity Platform?

| Criterion | Basic Firebase Authentication | Firebase Authentication with Identity Platform / Identity Platform |
|---|---|---|
| Email/password, social, phone, anonymous, custom auth | Yes | Yes |
| Firebase Client SDK, Admin SDK | Yes | Yes; preserves compatibility with existing Firebase apps |
| SAML / generic OpenID Connect | Not in the basic feature set | Yes |
| MFA (SMS, TOTP where supported) | No equivalent advanced capability | Yes |
| **Multi-tenant** identity isolation inside one project | No | Yes |
| **Blocking functions** before user creation/sign-in | No | Yes |
| Identity-Aware Proxy integration | Not in the basic tier | Available in Identity Platform |
| Enterprise SLA / BAA coverage | Not under the basic tier | Available under applicable service terms/agreements |
| Pricing | Per Firebase plan and provider/quotas | Typically by **Monthly Active Users**; SMS/MFA billed separately |
| Best fit | Small/medium consumer apps without advanced federation | B2B, multi-tenant SaaS, enterprise SSO, strict security compliance |

This is a **directional** comparison and does not guarantee every MFA provider, region, compliance/SLA, or pricing tier is enabled automatically. Enabling **Firebase Authentication with Identity Platform** generally lets apps **keep using existing SDKs without migrating users**, though **billing/quotas change**—review pricing and limits before upgrading. Adding SAML/OIDC, MFA, or tenant-aware flows **still requires new configuration and code**.

### 3.1. Three typical scenarios

1. **Consumer order-tracking mobile app** with Google/email login, one user pool, and no enterprise SSO: start with basic Firebase Authentication.
2. **B2B partner application** requiring SAML with external identity providers: consider Identity Platform for enterprise federation.
3. **Multi-tenant Java SaaS** where each organization wants separate user pools, providers, and policies: evaluate Identity Platform multi-tenancy.

Do not upgrade merely because you want a Java API on Cloud Run: basic Firebase Authentication **already lets** the Java Admin SDK verify Firebase ID tokens.

## 4. Sign-In Methods and Selection Criteria

| Provider | When to use | Security/operational notes |
|---|---|---|
| **Email/password** | Product manages accounts directly | Email verification, password reset, credential-stuffing defense |
| **Email link / passwordless** | Want to reduce password friction | Authorized domains, anti-phishing, and email deliverability |
| **Google/Apple/Facebook/GitHub...** | Social login | OAuth consent, redirect URIs, account linking |
| **Phone/SMS** | Phone-centric flows or verification steps | SMS charges, quotas, SIM-swap risk, abuse prevention |
| **Anonymous** | Guest trials before account creation | Account linking, cleanup, never trust anonymous as verified identity for transactions |
| **Custom auth** | Existing identity system integrated with Firebase | Only trusted backends sign custom tokens; client exchanges for an ID token |
| **SAML 2.0** | Enterprise SSO with org IdPs | Metadata, certificates, assertion audience, clock skew |
| **Generic OIDC** | Enterprise SSO/third-party OIDC IdPs | Issuer, client ID, redirects, scopes, JWKS, account linking |

**Phone/SMS should not be the sole identity proof for high-value accounts**: phone numbers can be reassigned or SIM-swapped. **Email/password** requires email enumeration protection, strong password policies, and appropriate rate limiting. For social/OIDC/SAML, design **account linking** so signing in with two providers does not accidentally create two separate business profiles.

### 4.1. When do you use custom authentication?

A Java backend with its own existing login system can mint a **Firebase custom token**:

~~~text
Java backend verifies business credentials
  → Firebase Admin SDK createCustomToken(uid)
  → Client signInWithCustomToken(customToken)
  → Firebase Auth returns Firebase ID token + refresh token
  → Client uses ID token to access Firebase / Java API
~~~

**A custom token is not a Firebase ID token.** Never pass a raw custom token into `FirebaseAuth.verifyIdToken()` to authorize API calls; the client must exchange it through Firebase Authentication first. Signing custom tokens with the Admin SDK may require IAM **`signBlob`/token signing** permission on the service identity in Google Cloud; **never** download a static service account JSON key just for this feature.

## 5. ID Tokens, Refresh Tokens, and Session Cookies

| Token type | Issued / used by | Lifetime & notes |
|---|---|---|
| **Firebase ID token** | Returned by Firebase Authentication after sign-in | JWT typically valid for ~**1 hour**, used by Security Rules or verified by Java APIs |
| **Refresh token** | Managed by Client SDK for long-lived sessions | Fetches new ID tokens; invalidated on account disable/delete/major change or admin revoke |
| **Custom token** | Minted by backend Admin SDK for client sign-in | Only to **exchange** for a Firebase session, never used as an API bearer token |
| **Firebase session cookie** | Created by Admin SDK from an ID token for web server sessions | Configurable ~**5 minutes to 2 weeks**, `HttpOnly`/`Secure`, CSRF protection |
| **Cloud Run service caller OIDC token** | Google Cloud IAM/service-to-service | Invokes private Cloud Run services; **different** from a Firebase ID token |

### 5.1. What `verifyIdToken` validates on a Firebase ID token

The Firebase Admin SDK checks signature, expiration, issuer/audience bound to your **Firebase project**, and SDK token structure. Java should always call `FirebaseAuth.verifyIdToken(idToken)` rather than Base64-decoding the JWT manually.

When revocation/disabled-account checks are needed, call `verifyIdToken(idToken, true)`; this makes an extra network call to Firebase Auth, adding latency and operational cost. Do not enable or omit it arbitrarily—align it with your risk profile and resilience targets.

For high-privilege requests, also inspect **`auth_time`** to require recent authentication in addition to expiry/revocation checks.

### 5.2. Session cookies for server-rendered web apps

If a Java server uses session cookies:

1. Client signs in via Firebase SDK and posts the ID token to `/sessionLogin` over HTTPS.
2. Server **verifies the ID token**, validates a **CSRF token**, and calls Admin SDK to mint the session cookie.
3. Set the cookie with `HttpOnly`, `Secure`, and appropriate `SameSite`, scoping path/domain and TTL.
4. Each server request runs `verifySessionCookie`, optionally checking revocation.
5. Logout clears the cookie/session and considers `revokeRefreshTokens(uid)` when broad revocation is needed.

**A Firebase session cookie cannot replace an ID token for direct Firestore/Firebase client SDK calls.** It is meant for server-side session management, where the server enforces authorization itself.

## 6. Lab A — Web SDK Signing In and Calling a Java API

**Prerequisites:** sandbox Firebase project, registered Web app, **Email/Password** provider enabled, and authorized domains configured; never use production emails or passwords in the lab. An HTTPS Java API `https://JAVA_API_HOST` is running under an authorized access setup.

### 6.1. Enable the provider in the console

In Firebase Console → **Authentication → Sign-in method**, enable **Email/Password** for the lab project. Copy the exact **project ID, auth domain, and Web app API key** from Firebase project settings.

**A Firebase Web SDK API key is not a service account password**; it identifies the Firebase project/app for certain Firebase APIs. Although it is not a secret protecting data, apply **API key restrictions** where possible, anti-abuse controls, and Security Rules, and never confuse the key with user permissions.

### 6.2. Modular JavaScript Web SDK

Illustrative sample for a web app with the `firebase` package installed, signing in with email/password:

~~~javascript
import { initializeApp } from "firebase/app";
import {
  getAuth, signInWithEmailAndPassword,
  signOut
} from "firebase/auth";

const app = initializeApp({
  apiKey: "FIREBASE_WEB_API_KEY",
  authDomain: "PROJECT_ID.firebaseapp.com",
  projectId: "PROJECT_ID",
  appId: "FIREBASE_APP_ID"
});

const auth = getAuth(app);

export async function signInAndCallApi(email, password) {
  const userCredential =
    await signInWithEmailAndPassword(auth, email, password);

  // Never log tokens or place tokens in URLs/query strings.
  const idToken = await userCredential.user.getIdToken();

  const response = await fetch("https://JAVA_API_HOST/api/me", {
    method: "GET",
    headers: { Authorization: "Bearer " + idToken }
  });

  if (!response.ok) {
    throw new Error("API request failed: " + response.status);
  }

  return await response.json();
}

export async function logout() {
  await signOut(auth);
}
~~~

**Key points to understand:**

- The Client SDK manages the refresh token and supplies fresh ID tokens automatically; avoid storing raw tokens manually in `localStorage` without good reason.
- `userCredential.user.uid` is fine for UI rendering, but the server must **never trust a UID from a JSON body or self-asserted header**. Java must derive identity from the **verified Firebase ID token**.
- Require HTTPS and configure CORS if frontend/backend have different origins; **CORS is not authorization**.
- If the Cloud Run API enforces IAM requiring a **Google Cloud Invoker token**, a Firebase ID token is **not** a Cloud Run IAM token. Pick a clean trust boundary: authenticate Firebase tokens inside Java ingress (behind appropriate gateway/WAF controls), or use an API gateway—never leave data access unguarded in Java.

### 6.3. When NOT to use email/password directly

If an enterprise requires Microsoft Entra ID/SAML SSO or custom OIDC, use **Identity Platform provider federation** instead of asking employees to create another Firebase password. This requires configuring issuer, certificates, redirects, and account linking—you cannot just swap a provider name in the Web SDK and skip setup.

## 7. Lab B — Java Cloud Run Verifying a Firebase ID Token

**Architecture:** Java Spring Boot (JDK 17+) receives `Authorization: Bearer FIREBASE_ID_TOKEN`; the Firebase Admin SDK verifies the token, then the application checks user/role before accessing Firestore or Cloud SQL.

### 7.1. Maven dependency for the Admin SDK

In a Spring Boot Maven project already including `spring-boot-starter-web`, add:

~~~xml
<dependency>
  <groupId>com.google.firebase</groupId>
  <artifactId>firebase-admin</artifactId>
  <version>9.12.0</version>
</dependency>
~~~

`9.12.0` is an Admin Java SDK release from **11/11/2026** (used as a pinned version example). Always inspect release notes, Java/Spring compatibility, and security advisories before upgrading. Never put JSON keys into `pom.xml` or source code.

### 7.2. Initializing the Firebase Admin SDK with ADC

Create `FirebaseAdminConfig.java` (in a package scanned by Spring Boot):

~~~java
package com.example.orders;

import com.google.auth.oauth2.GoogleCredentials;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.auth.FirebaseAuth;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FirebaseAdminConfig {
    @Bean
    public FirebaseApp firebaseApp() throws Exception {
        String projectId = System.getenv("FIREBASE_PROJECT_ID");
        if (projectId == null || projectId.isBlank()) {
            throw new IllegalStateException("FIREBASE_PROJECT_ID is required");
        }
        FirebaseOptions options = FirebaseOptions.builder()
            .setCredentials(GoogleCredentials.getApplicationDefault())
            .setProjectId(projectId)
            .build();
        return FirebaseApp.initializeApp(options);
    }

    @Bean
    public FirebaseAuth firebaseAuth(FirebaseApp app) {
        return FirebaseAuth.getInstance(app);
    }
}
~~~

On Cloud Run/GKE/Compute Engine, use the **runtime service account** and ADC, granting least-privilege IAM for the exact Admin SDK operations needed. For example, a service that only **verifies JWTs locally** should not hold project-wide Identity Platform Admin. User lookups, revoking refresh tokens, setting claims, or minting custom tokens require specific permissions. **Never** grant `roles/owner` or `roles/identitytoolkit.admin` to every API service by default.

**Local testing nuance:** end-user credentials from `gcloud auth application-default login` may **not be accepted by the Firebase Authentication Admin SDK for certain auth operations**. Local testing requires an appropriate project ID and OAuth client/ADC setup per docs; better yet, use the **Firebase Authentication Emulator Suite** or a test environment with workload identity. Avoid downloading long-lived JSON keys just for demos.

### 7.3. REST controller verifying the user token

Create `MeController.java` in the same package; the Java backend returns `401` for missing/invalid tokens and `403` when business authorization denies access:

~~~java
package com.example.orders;

import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseAuthException;
import com.google.firebase.auth.FirebaseToken;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {
    private final FirebaseAuth firebaseAuth;

    public MeController(FirebaseAuth firebaseAuth) {
        this.firebaseAuth = firebaseAuth;
    }

    @GetMapping("/api/me")
    public ResponseEntity<?> me(
        @RequestHeader(value = "Authorization", required = false)
        String authorization
    ) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "missing_bearer_token"));
        }

        String idToken = authorization.substring("Bearer ".length()).trim();
        if (idToken.isEmpty()) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_token"));
        }

        try {
            // true: checks whether the token is revoked/disabled, adding a network request.
            FirebaseToken verified =
                firebaseAuth.verifyIdToken(idToken, true);

            String uid = verified.getUid();
            // This endpoint returns only the UID; business routes
            // must check order/tenant permissions before querying the DB.
            return ResponseEntity.ok(Map.of("uid", uid));
        } catch (FirebaseAuthException e) {
            // Do not expose the ID token or sensitive error details in the response.
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_or_revoked_token"));
        }
    }
}
~~~

**Illustration boundary:** This is a complete controller + config bean for an **existing Spring Boot Web project with an entrypoint**, not a standalone single-file app. `/api/me` only proves user identity. For `GET /api/orders/{id}`, verify `ownerUid`/`tenantId` in the business layer and return **403** if the caller is authenticated but unauthorized. For multiple API routes, use a **Spring Security filter** to enforce authentication uniformly instead of duplicating logic across controllers.

### 7.4. When should you check revocation?

| Context | Recommendation |
|---|---|
| Simple profile view, high traffic | Consider `verifyIdToken(token)` paired with token TTL/authorization policies, balancing latency |
| Billing access, sensitive data, admin actions | `verifyIdToken(token, true)` when early revocation enforcement is required |
| Admin role recently downgraded | Remember **older ID tokens hold older claims**; use refresh/authoritative permission checks or revoke sessions |
| Locked account or suspected token theft | Revoke refresh tokens, check revoked/disabled, and investigate sessions |

**Checking the JWT signature alone cannot tell whether the refresh token was revoked.** Firebase ID tokens normally stay valid until expiration, so define clear requirements for **how quickly permission revocations must take effect**.

## 8. Security Rules + Java Authorization

### 8.1. Firestore Rules for user-owned documents

Sample client-side rules in Firestore Native:

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read: if request.auth != null
                  && request.auth.uid == userId;
      allow write: if false;
    }

    match /orders/{orderId} {
      allow read: if request.auth != null
                  && resource.data.ownerUid == request.auth.uid;
      allow write: if false;
    }
  }
}
~~~

This lets mobile/web Firebase SDKs read the authenticated user's profile and orders, while writes happen through the **Java backend** via IAM. A query asking for **all** orders hoping Rules will filter out other users' orders **will be rejected**: **Security Rules are not filters**. Client queries must constrain `ownerUid == request.auth.uid` with a matching index.

### 8.2. Java server "bypassing Rules" does not mean bypassing security

Java server Admin/Firestore SDKs **bypass Rules** because they use Google IAM. The server must:

1. Authenticate the HTTP caller via Firebase ID token.
2. Extract `uid` and, if present, `tenantId` from the **verified token**.
3. Look up the order and match `ownerUid`/`tenantId` against business permissions.
4. Reject unauthorized callers with `403`—never check only "is the client logged in."
5. Execute queries/transactions strictly scoped to authorized data.
6. Emit audit logs free of raw tokens, PII, or database secrets.

Never trust client-supplied `request.queryParams.uid` or `X-Tenant-Id` as a principal. If a URL includes a tenant parameter, verify it against the **token's tenant** and backend membership/entitlements.

### 8.3. How do Identity Platform and App Check complement each other?

**Firebase App Check** uses app/device attestation to reduce spoofed requests from unauthorized apps. App Check **does not authenticate users**, and Authentication **does not prove a request came from a genuine app build**. For custom Java backends, **send and verify the App Check token separately** if enabled—never accept an arbitrary custom header as proof of App Check.

## 9. Custom Claims and Role Management in Identity

Custom claims embed **compact roles** like `admin`, `support`, or shared permissions into the Firebase ID token.

~~~java
import com.google.firebase.auth.FirebaseAuth;
import java.util.Map;

// Run ONLY in an authorized admin environment.
String uid = "TEST_UID";
FirebaseAuth.getInstance().setCustomUserClaims(
    uid, Map.of("support", true));
~~~

Firebase custom claims:

- Only **trusted server/Admin SDK** code may set claims; never accept client-sent `isAdmin` flags.
- Claims payload is capped around **1,000 bytes**; never store profiles, lists of thousands of tenants, or PII.
- New claims appear when the **ID token refreshes** or the user signs in again; they do not retroactively update already-issued tokens.
- `setCustomUserClaims` **replaces the existing claims map**, so merge from an authoritative source when managing multiple claims to avoid wiping out other claims.
- **Custom token claims** can interact with post-sign-in tokens per documented precedence rules; never use custom tokens to let users pick their own roles.

### 9.1. Combining claims and policy checks in Java

~~~java
FirebaseToken token = firebaseAuth.verifyIdToken(idToken, true);
boolean support = Boolean.TRUE.equals(token.getClaims().get("support"));
if (!support) {
    // Return HTTP 403; never trust unverified claims.
}
~~~

**Claims inside a token are not a database role engine.** Having `support=true` does not grant Google Cloud IAM `roles/datastore.user`. For rapidly changing or per-order permissions, querying your application's **authorization datastore** remains essential.

### 9.2. Admin User Management API

The Firebase Admin SDK can create/update/disable/delete users and revoke refresh tokens:

~~~java
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.UserRecord;

// Execute ONLY inside an authorized admin tool/workflow.
UserRecord user = FirebaseAuth.getInstance().getUser("TEST_UID");
FirebaseAuth.getInstance().updateUser(
    new UserRecord.UpdateRequest(user.getUid()).setDisabled(true));
FirebaseAuth.getInstance().revokeRefreshTokens(user.getUid());
~~~

**Never execute this directly against a real production UID** without an approved change plan. Disabling/revoking **does not immediately invalidate cached ID tokens unless the backend checks revocation/disabled status**. Offboarding must also cover active sessions, custom claims, linked providers, personal data, and retention/compliance.

## 10. Identity Platform: Multi-Tenancy for SaaS and B2B

### 10.1. What is a tenant?

In Identity Platform, a **tenant** is an isolated user pool and identity configuration (providers, user accounts, policies) within the same Google Cloud/Firebase project. Tenants have distinct IDs; the same email can exist across multiple tenants as **separate identity accounts**.

~~~mermaid
flowchart LR
    WebA["Customer A portal"] --> A["Identity tenant A<br/>OIDC IdP A"]
    WebB["Customer B portal"] --> B["Identity tenant B<br/>SAML IdP B"]
    A --> API["Java multi-tenant API"]
    B --> API
    API --> Guard["Verify tenant-aware token<br/>+ tenant authorization"]
    Guard --> Data["Tenant-partitioned orders"]
~~~

**Tenant identity does not automatically isolate Firestore, Cloud SQL, or Storage data.** When sharing a backend or database, Java must verify `tenantId` on the token, cross-check business membership, and scope every query by tenant. For stricter isolation, consider separate projects, databases, or services.

### 10.2. Client selects the tenant before sign-in

With a configured Firebase Web SDK:

~~~javascript
import { getAuth, signInWithEmailAndPassword } from "firebase/auth";

const auth = getAuth();
auth.tenantId = "TENANT_A_ID";

const credential = await signInWithEmailAndPassword(
  auth, "user@tenant-a.example", "TEST_PASSWORD");
const idToken = await credential.user.getIdToken();
~~~

`tenantId` is not persisted across full page reloads automatically; re-determine and set the tenant before auth operations after reload. **Never trust a tenant ID derived solely from a subdomain or URL** if users could spoof it; the server must check the tenant inside the ID token.

### 10.3. Java using `TenantAwareFirebaseAuth`

~~~java
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseToken;
import com.google.firebase.auth.TenantAwareFirebaseAuth;

String tokenFromClient = "VERIFIED_TRANSPORT_ONLY";
String expectedTenant = "TENANT_A_ID";

TenantAwareFirebaseAuth tenantAuth =
    FirebaseAuth.getInstance()
        .getTenantManager()
        .getAuthForTenant(expectedTenant);

FirebaseToken verified = tenantAuth.verifyIdToken(tokenFromClient, true);
// Tenant other than expectedTenant -> verification fails.
String uid = verified.getUid();
String tenantId = verified.getTenantId();
~~~

**If Java serves multiple tenants and does not know which tenant beforehand**, verify the token at the project level first to extract the tenant ID, **then** use the matching tenant-aware auth client to check revocation status. **Never call project-level `verifyIdToken(token, true)` on a tenant user and assume the user was deleted**, because project-level revocation checks look in the root user pool and can throw `user-not-found` for tenant users. Whitelist valid tenants and enforce the tenant → resource mapping.

## 11. SAML, OIDC, MFA, and Blocking Functions

### 11.1. Enterprise federation (SAML/OIDC)

Identity Platform supports configuring SAML/OIDC IdPs within supported capabilities:

| Area | What to verify |
|---|---|
| OIDC | Issuer URL, client ID/secret, redirect URI, signing keys, scopes, email claims |
| SAML | Entity ID, SSO URL, X.509 signing certificate, NameID mapping, assertion times |
| Account linking | Never merge two users across UIDs/emails without verifying ownership |
| Tenant-specific IdP | Configure providers on the specific tenant rather than project-wide |
| JIT provisioning | User lifecycle, group/role mapping, deletion/offboarding |
| Security | PKCE/state/nonce per SDK/provider flow and prevent open redirects |

**Do not hand-roll SAML signature validation inside a Java API** when Identity Platform handles federation. Java should consume the verified Firebase ID token and enforce business authorization.

### 11.2. MFA: SMS or TOTP

Identity Platform supports **multi-factor authentication** via SMS or TOTP in supported configurations.

- **TOTP** uses authenticator apps; avoids SMS costs, though it requires enrollment, recovery, and secret protection workflows.
- **SMS MFA** carries messaging charges, quotas, SIM-swap risks, and regional support constraints.
- MFA has prerequisites on the **first sign-in provider and email verification**; sources like **anonymous, phone, and custom-token sign-in** cannot serve as a first factor per TOTP guidance.
- Enforce MFA for sensitive accounts, admins, or high-risk actions; design recovery without weakening security.

**MFA does not authorize individual orders** and does not replace Security Rules.

### 11.3. Blocking functions: intercepting user creation and sign-in

`beforeUserCreated` and `beforeUserSignedIn` let you validate email domains, enforce risk policies, or enrich claims **before Firebase Auth issues an ID token**. Key operational traits:

- Blocking functions have a **short deadline (7 seconds per current docs)**; errors or timeouts can block all sign-ups or sign-ins.
- User creation can invoke both create and sign-in hooks.
- **Anonymous and custom auth** do not trigger blocking functions per current rules.
- Deleting a function **without unregistering the trigger** can lock users out of signing in.
- In multi-tenancy, a function may span multiple tenants; verify scoping, feature flags, and circuit-breaker/fallback policies.

**Never put multi-second workflows or flaky external API calls inside a blocking function.** It sits directly on every user's login critical path and needs its own SLO, monitoring, and rollback plan.

## 12. Account, Token, and HTTP Flow Security

### 12.1. Essential controls

1. Enforce **HTTPS** on every endpoint receiving ID tokens; never place tokens in URLs/query strings, logs, or analytics.
2. Choose platform-appropriate session storage; web apps should avoid handling refresh tokens manually.
3. Enable email verification, password policies, anti-abuse/rate limiting, and anomalous sign-in alerts.
4. Handle account linking carefully; never merge accounts based on unverified emails.
5. Sensitive APIs require **recent authentication**, revocation checks, and per-resource authorization.
6. For session cookies, set `Secure`, `HttpOnly`, `SameSite`, CSRF tokens, and bounded lifetimes.
7. **App Check** attests app/device integrity as a supporting layer—it never replaces Firebase Authentication.
8. Restrict backend/admin IAM: `roles/identitytoolkit.admin` and `roles/identityplatform.admin` belong only to required administrative roles.
9. Isolate **test/staging/prod projects**, token audiences/projects, and provider credential rotation procedures.
10. Define data retention, export/deletion workflows, and legal compliance for user records.

### 12.2. Firebase Auth ID token vs Google Cloud Run IAM token

| Purpose | Correct token |
|---|---|
| Web user calling a Java API doing Firebase auth | **Firebase ID token** |
| Cloud Scheduler calling a private IAM-protected Cloud Run service | **Google-signed OIDC ID token** for a service account with `roles/run.invoker` |
| Java server calling Google Cloud APIs | **ADC/OAuth access token** of the runtime service account |
| Mobile client accessing Firestore Native | Firebase Auth session/Rules, plus App Check if enabled |
| Java server accessing Firestore Native | Runtime SA's Google IAM, **not a Firebase UID token** |

**A valid Firebase ID token does not satisfy Cloud Run Invoker IAM.** If Cloud Run enforces IAM at ingress, use an appropriate frontend/gateway pattern—or configure the endpoint to accept HTTP requests and have **Java verify the Firebase token itself**, paired with Cloud Armor, rate limiting, and security controls. Never equate `--allow-unauthenticated` with "public data"; application authorization must still be enforced in code.

## 13. Lab C — Testing and Governance Workflows

### 13.1. End-to-end Firebase client + Java tests

Prepare an isolated **Firebase Auth test project** and **Java API sandbox**. Test cases should cover:

| Case | Expected |
|---|---|
| Valid sign-in calling `/api/me` with a valid ID token | HTTP 200 returning verified UID |
| Missing `Authorization` header | HTTP 401 |
| Token modified by one byte | HTTP 401 |
| Token from a **different Firebase project** | HTTP 401 |
| Stale/expired token | HTTP 401 |
| Disabled/revoked user calling an API with `checkRevoked` | HTTP 401 |
| User A's token reading user B's order | HTTP 403 |
| Firebase mobile querying docs outside Rules scope | `PERMISSION_DENIED` |
| Java runtime SA missing Firestore IAM permission | Server Cloud client API `PERMISSION_DENIED` |
| Multi-tenant token A calling tenant B API | HTTP 401 or 403 per authn/authz policy |

For unit/integration tests, the **Firebase Authentication Emulator Suite** can mint test users/tokens locally via an isolated emulator endpoint. **Emulator-issued tokens lack production signatures**, so never point a production Admin SDK at an emulator or trust unsigned emulator tokens in production.

### 13.2. Safely inspecting configurations

- Firebase Console → Authentication → Providers / Users / Settings: inspect enabled providers and authorized domains.
- Google Cloud Console → Identity Platform → Providers / Tenants: inspect federation, tenant policies, and upgrade state if applicable.
- Cloud IAM: verify the **principal running Java** and its assigned roles without exposing private credentials.
- Firebase/Identity Platform Logs: track sign-in activity and provider errors; distinguish **Cloud Audit Logs** (admin changes) from **Activity logging** (user sign-ins).

**Identity Platform Activity logging is off by default per documentation**; enable it intentionally when security and privacy policies allow, noting log storage costs and avoiding unnecessary sensitive data capture.

### 13.3. Rehearsing permission changes

To revoke the `support` role:

1. Update permissions in the **authoritative data source**; update user custom claims via the Admin SDK.
2. If immediate effect is needed, revoke refresh tokens and require client reauthentication.
3. Ensure the Java API runs revocation checks and/or queries persistent authorization state on sensitive routes.
4. Test old sessions, new sessions, other devices, cookies, and tenant-specific users.
5. Capture log evidence proving the user can no longer read privileged data.

Never test by granting admin permissions to a client and deleting users in a live project.

## 14. Cost, Quotas, SLA, and Operations

### 14.1. Billing by provider type and usage

Identity Platform generally bills by **MAU (Monthly Active Users)**:

| Category | Billing mechanism to verify |
|---|---|
| Email/social/anonymous/custom | Billed per MAU, with a **50,000 MAU no-cost tier** on eligible plans |
| **SAML / generic OIDC** | Separate pricing tier with a smaller no-cost allowance (e.g., **50 MAU**) |
| SMS phone sign-in / SMS MFA | **Billed per message**, varying by destination region and limits |
| Firebase Auth with Identity Platform without a billing instrument | Subject to **daily active user** caps |
| Blocking functions/Cloud Run/Cloud Functions | Compute/network/logging costs in addition to MAU |
| Cloud Logging/Monitoring and App Check | Service and attestation-provider quotas/charges |

**Never estimate cost from total stored accounts.** A user who never signs in during a month may not count toward MAU; **monthly active** differs from **registered users**. For phone auth, SMS fees and fraud mitigation can outweigh MAU pricing. Pricing and thresholds can change—check current pricing pages and Billing Reports at deployment time.

Per Firebase Authentication with Identity Platform docs, a **Spark plan without a billing instrument** has caps of **3,000 tier-1 DAU and 2 tier-2 DAU** (distinct from Blaze's MAU allowances). Never assume **50,000 MAU** lets every Spark project handle 50,000 daily sign-ins unrestricted.

### 14.2. Quotas and scaling safely

- Rate limits on **sign-ups, token exchanges, account lookups, password reset emails, and SMS sends** can apply per project/IP/provider.
- Email/SMS OTP flows are prime abuse targets; enable supported App Check/reCAPTCHA and abuse controls.
- Multi-tenancy and enterprise federation add external IdP dependencies and SSO latency.
- Blocking functions sit on the login critical path; monitor failure rates and p95/p99 latency.
- Checking revocation on every request increases calls to the Auth backend; weigh caching, TTL, and risk tolerance.
- True SLOs must measure **successful sign-in + usable API + authorized resource access**, not provider auth alone.

## 15. Troubleshooting: Separating Identity Errors from Data Errors

| Symptom | Likely cause | Diagnostics |
|---|---|---|
| Web sign-in `auth/invalid-credential` | Wrong credentials/provider or invalid account | Provider enablement, test user, client error code |
| `auth/unauthorized-domain` | Web domain not allowlisted | Firebase Auth authorized domains |
| Google/OIDC redirect fails | Mismatched URI, issuer, OAuth consent, state/nonce | Provider configuration and callback logs |
| Firebase ID token sent to Java returns 401 | Missing Bearer prefix, expired token, wrong signature/project | Backend `verifyIdToken`, project ID |
| Token valid yet Java returns 403 | Wrong tenant/role or order `ownerUid` | Domain authorization, claims, and data |
| Cloud Run ingress returns 401/403 **before Java runs** | Missing IAM Invoker or Firebase token mistaken for Cloud Run IAM token | Cloud Run ingress policy and request logs |
| Java Admin SDK lacks permission | Runtime SA IAM insufficient for user management | Required IAM role/permissions for the operation |
| Newly revoked token still accepted | Revocation not checked or token not yet expired | `verifyIdToken(token, true)` and session policy |
| New custom claim missing | ID token not refreshed or claims overwritten | Force refresh/new sign-in, Admin `getUser` |
| Multi-tenant user gets `user-not-found` | Project-level revocation check instead of tenant-level | `TenantAwareFirebaseAuth` |
| Firebase Rules deny multi-order query | Rules are not filters; query lacks `ownerUid` | Query constraints and Rules tests |
| Java Firestore server reads despite deny Rules | Admin/server SDK bypasses Rules | Cloud IAM/runtime SA and app authorization |
| MFA TOTP enrollment fails | Ineligible first-factor/provider or unverified email | Identity Platform MFA settings |
| Blocking function blocks all logins | Function timeout/error or deleted without unregistering | Auth trigger config, function logs/rollbacks |
| SMS bill spikes | OTP fraud/retries, phone sign-in surge | Identity Platform usage, rate limits, Billing |
| Local Java Admin SDK ADC errors | User OAuth ADC rejected or wrong project | SDK setup and Emulator configuration |

### 15.1. Six-step runbook

1. **Who is calling?** Web/mobile user, Java runtime SA, or CI deployer?
2. **Where did it fail?** Provider sign-in, Firebase ID token, Cloud Run ingress, Java authorization, Firestore Rules, or IAM?
3. **Which project/tenant?** Compare project ID, issuer/audience, tenant ID, and client SDK config.
4. **Which token?** Firebase ID token, custom token, Google OIDC IAM token, or App Check token.
5. **Which permission?** User claims/tenant/order ownership, Rules, or runtime SA IAM.
6. **Controlled fix:** test in sandbox, inspect logs/metrics, and run negative tests before production.

Never fix a 403 with `allow read, write: if true`, disabling Java authorization, granting Owner, or printing raw tokens to logs.

## 16. Case Study — RetailOne Java Orders API and B2B Partners

**Context:** RetailOne runs a mobile order-tracking app and a **Java Orders API** on Cloud Run with orders in Firestore Native. Initially it used only Google/email sign-in; later, two enterprise partners required SAML and isolated user pools.

### 16.1. Phased design

| Phase | Solution |
|---|---|
| **A. Mobile consumer** | Basic Firebase Authentication, Firebase SDK, Rules `ownerUid == auth.uid` |
| **B. Java Orders API** | Firebase Admin Java verifies ID tokens, domain authorization, runtime SA + Firestore IAM |
| **C. Enterprise SSO** | Upgrade to Firebase Auth with Identity Platform, configure SAML/OIDC providers |
| **D. B2B multi-tenant** | Identity Platform tenants, tenant-aware token verification, dataset separation policy |
| **E. Higher assurance** | MFA, revocation handling, blocking functions with SLOs, and App Check |

### 16.2. Why is separating identity important?

~~~mermaid
flowchart LR
    A["Mobile user A"] --> Auth["Firebase Auth"]
    B["Partner B employee"] --> Tenant["Identity Platform tenant B"]
    Auth --> Java["Cloud Run Java Orders API"]
    Tenant --> Java
    Java --> Guard["Verify token + tenant + owner + role"]
    Guard --> IAM["Runtime service account + Firestore IAM"]
    IAM --> Docs["Firestore orders"]
~~~

An engineer might accidentally write `GET /api/orders/{id}` checking only "is the token valid." If partner B guesses an `orderId` from tenant A, the backend—having IAM read access across the collection—could leak cross-tenant data.

**Proper fix:** after verification, Java extracts `tenantId`/`uid` from the token, reads order metadata, validates `ownerUid` and `tenantId` against policy, and only then returns a response. **Never rely solely on email/domain claims as proof of tenant**, as email/IdP mappings can change.

### 16.3. Rollout and rollback plan

1. Inventory providers, MAU counts, SLAs, session lifecycles, Rules, and IAM.
2. Estimate MAU/SAML/SMS/Cloud Functions costs before upgrading Identity Platform.
3. Create and test SAML tenants in staging; test login failures, redirects, and MFA.
4. Test the Java backend with tenant A/B tokens, cross-project tokens, and expired tokens.
5. Run the Security Rules emulator to prove user A cannot read order B.
6. Roll out via feature flags to a pilot group; monitor sign-in error rates, 401/403s, and SLOs.
7. Maintain playbooks to disable tenant providers/claims and clear sessions on incidents; do not assume a product-level upgrade can be rolled back with one button.
8. Periodically audit costs, IAM roles, and sign-in UX.

## 17. Exercises and Self-Assessment

### Exercise 1 — Identifying identity systems

A user signs in to Firebase with Google, and then Java on Cloud Run reads Firestore via a service account.

**Question:** What identities are the Firebase `uid`, Cloud Run runtime SA, and deployer IAM principal? Who decides whether the user may view an order?

**Hint:** Backend domain authorization checks owner/tenant; a Firebase UID is not a GCP IAM service account.

### Exercise 2 — Firebase Auth vs Identity Platform

A mobile app has 2,000 users using only email/Google sign-in. Another B2B product needs SAML with separate IdPs per company.

**Question:** Which solution fits each product and why? What changes in billing upon upgrading?

### Exercise 3 — Firebase ID token vs custom token

A Java backend calls `createCustomToken(uid)` and the client sends that token directly to `/api/orders`. Java calls `verifyIdToken` and gets an error.

**Question:** Which step is missing?

**Hint:** The client must call `signInWithCustomToken` to exchange it for a **Firebase ID token**.

### Exercise 4 — Firebase Auth vs Cloud Run Invoker

The Web SDK sends a Firebase ID token, yet Cloud Run returns 403 before Java code executes.

**Question:** Why is a valid Firebase token insufficient? How should ingress be designed?

### Exercise 5 — Security Rules do not stop Java

Firestore Rules deny everything, yet the Java Admin SDK on Cloud Run can still read `orders`.

**Question:** Where is the misconception? How should runtime SA IAM and Java business authorization be controlled?

### Exercise 6 — Revoking the support role

A user's `support` custom claim is removed, yet an existing session continues accessing the endpoint for a while.

**Question:** Which refresh, revocation, and persistent permission mechanisms enforce the change on time?

### Exercise 7 — Multi-tenant user pools

Tenants A and B both contain `user@example.com`. Java receives a tenant A token for a request to `/tenant/B/orders`.

**Question:** Where must the tenant ID be checked besides email? Why can a project-level revocation check fail?

### Exercise 8 — Blocking function failure

Identity Platform uses `beforeUserSignedIn` to call an external risk API that times out after 9 seconds.

**Question:** How does this affect sign-ins? How do you design reliability and rollback?

**Hint:** Blocking paths have roughly a 7-second deadline; use short timeouts/circuit-breakers and avoid heavy dependencies.

### Exercise 9 — MFA and App Check

One team suggests enabling only App Check to protect admin accounts, or only SMS MFA to block spoofed apps.

**Question:** Why do these two tools serve different goals? Outline a combined design.

### Exercise 10 — Cost and quotas

Identity Platform has 70,000 email/social MAU, 400 SAML/OIDC MAU, 20,000 SMS per month, and heavy blocking function invocations.

**Question:** Which SKUs/quotas must be broken out in estimates? Does the 50,000 MAU free tier cover all methods combined?

### Exercise 11 — End-to-end security drill

Draft a test checklist for RetailOne covering user A, user B, partner tenant, wrong-project ID token, revoked token, stale custom claim, Firestore Rules, server IAM, and API error codes. State the expected log evidence **without exposing tokens or PII**.

## 18. Production Checklist

- [ ] Distinguished basic Firebase Authentication from required Identity Platform features.
- [ ] Enabled only needed providers; verified OAuth/SAML redirects and authorized domains.
- [ ] Email/password configured with verification, anti-abuse, password resets, and safe account linking.
- [ ] ID tokens sent over HTTPS via `Authorization: Bearer ...` and **verified with the Admin SDK**.
- [ ] Java code never trusts UID/tenant/role from unverified request fields.
- [ ] Understood custom token exchange, and how ID tokens differ from refresh tokens and Cloud Run IAM tokens.
- [ ] Defined token expiry/revocation and recent sign-in policies for sensitive actions.
- [ ] Custom claims kept small, set via trusted admin workflows, without PII/profiles.
- [ ] Mobile/web Firestore Security Rules tested; recognized Rules **are not filters**.
- [ ] Java server Firestore SDK uses IAM with domain-level authorization and least-privilege runtime SA.
- [ ] Cloud Run ingress designed explicitly for Firebase clients or service-to-service IAM.
- [ ] MFA/TOTP/SMS tested for provider eligibility, recovery, and billing/quotas.
- [ ] Multi-tenant tokens verified with the right tenant-aware client where needed; data isolated by policy.
- [ ] Blocking functions have timeouts, monitoring, fallback/rollback, and no slow external dependencies.
- [ ] App Check deployed as a **supporting layer**, never replacing user authentication.
- [ ] Session cookies use Secure/HttpOnly/SameSite/CSRF protections if used.
- [ ] Auth Admin SDK uses ADC/service identity; no committed service account JSON keys.
- [ ] Identity Platform admin IAM roles restricted to necessary operators and audited.
- [ ] Tested 401/403/revoked/expired/cross-project/cross-tenant and abuse scenarios.
- [ ] Activity logging/Audit Logs, quotas, MAU/SMS, and alerts configured per privacy policy.
- [ ] Estimated costs across tier-1/tier-2 providers, SMS, blocking function compute, and logs.
- [ ] Defined sign-in SLOs and recovery runbooks for provider/SAML/IdP or blocking function failures.

## 19. Official Firebase and Google Cloud Documentation

Verify APIs, IAM permissions, pricing/quotas, provider eligibility, and regional requirements at deployment time:

- [Firebase Authentication — Overview](https://firebase.google.com/docs/auth)
- [Identity Platform — Product comparison](https://docs.cloud.google.com/identity-platform/docs/product-comparison)
- [Identity Platform — Getting started](https://docs.cloud.google.com/identity-platform/docs/quickstart)
- [Firebase — Password authentication for web](https://firebase.google.com/docs/auth/web/password-auth)
- [Firebase — Admin SDK setup](https://firebase.google.com/docs/admin/setup)
- [Firebase — Verify ID tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [Firebase — Manage user sessions and revocation](https://firebase.google.com/docs/auth/admin/manage-sessions)
- [Firebase — Manage session cookies](https://firebase.google.com/docs/auth/admin/manage-cookies)
- [Firebase — Create custom tokens](https://firebase.google.com/docs/auth/admin/create-custom-tokens)
- [Firebase — Custom claims and Rules](https://firebase.google.com/docs/auth/admin/custom-claims)
- [Firebase — Admin user management](https://firebase.google.com/docs/auth/admin/manage-users)
- [Identity Platform — Multi-tenancy and tenant-aware Admin SDK](https://docs.cloud.google.com/identity-platform/docs/multi-tenancy-managing-tenants)
- [Firebase — Add TOTP MFA](https://firebase.google.com/docs/auth/web/totp-mfa)
- [Firebase — Blocking functions](https://firebase.google.com/docs/auth/extend-with-blocking-functions)
- [Firebase — Firestore Security Rules conditions](https://firebase.google.com/docs/firestore/security/rules-conditions)
- [Firebase — App Check](https://firebase.google.com/docs/app-check)
- [Identity Platform — Activity logging](https://docs.cloud.google.com/identity-platform/docs/activity-logging)
- [Identity Toolkit IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/identitytoolkit)
- [Firebase Authentication usage limits](https://firebase.google.com/docs/auth/limits)
- [Identity Platform pricing](https://cloud.google.com/identity-platform/pricing)
- [Firebase Admin Java release notes](https://firebase.google.com/support/release-notes/admin/java)

**Key takeaway:** Firebase Authentication authenticates **end users**, Identity Platform extends it into **CIAM for enterprise/SSO/multi-tenancy**, and **Google Cloud IAM** authenticates **backend service accounts**. For a Java Orders API, the right flow is **client sign-in → Firebase ID token → Admin SDK verify → check tenant/owner/role → access data via runtime IAM**. Keep **Security Rules, App Check, custom claims, session/revocation, and Cloud Run Invoker** distinct, test negative cases, and evaluate MAU/SMS costs alongside sign-in SLOs before going to production.

# Distinguishing Cognito User Pool and Identity Pool

An e-commerce application may need to let customers **sign up and sign in with email, Google, or an enterprise account**, then call an API to view orders. Another photo application wants signed-in users to **download photos directly from Amazon S3** without routing all traffic through an intermediary server. Both can use **Amazon Cognito**, but not the same component.

**Amazon Cognito User Pool** focuses on **user sign-up, authentication, login profile management, and issuing OIDC/OAuth 2.0 tokens**. **Amazon Cognito Identity Pool** focuses on **federating an identity from a trusted provider with an IAM role to issue temporary AWS credentials**. The two services can **operate independently** or **be combined**; not every application that uses a User Pool needs an Identity Pool.

This lesson belongs to the **Application Identity with Cognito** chapter of the **CLOUD_PROVIDERS_AWS** module. Its content connects application identity design with Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless. Learners will build skills in service selection, API and data protection, monitoring, recovery, and cost control.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the roles of **User Pool**, **Identity Pool**, **App Client**, **Identity Provider (IdP)**, **JWT**, and **IAM role**.
2. Distinguish **authentication**, **application authorization**, and **AWS IAM authorization**.
3. Choose **User Pool only**, **Identity Pool only**, or **both** based on business requirements.
4. Understand the three User Pool token types: **ID token, access token, refresh token**; know which token is used at the API and which token is passed to the Identity Pool.
5. Describe the flow **User Pool ID token → Identity Pool GetId/GetCredentialsForIdentity → STS credentials → AWS API**.
6. Read an IAM role trust policy with **aud/amr** conditions, and design authenticated/guest roles with least privilege.
7. Apply **Authorization Code + PKCE**, JWT verification, MFA, and token/secret protection principles.
8. Diagnose common issues across Cognito, API Gateway, IAM, and S3; estimate costs and build a production checklist.

## 2. Five Concepts to Separate from the Start

| Concept | Which question does it answer? | Example |
|---|---|---|
| **Authentication** | Who is this user, and have they proven their identity? | Signing in with password, passkey, MFA, or an external IdP |
| **Application authorization** | What business actions is the user allowed to perform? | Only the order owner can view their order; administrators can manage products |
| **AWS IAM authorization** | Which AWS APIs can the principal call, and on which resources? | Allowing s3:GetObject on the user's prefix |
| **User Pool** | What manages sign-in accounts, login sessions, and tokens? | User Pool issues access/ID/refresh tokens |
| **Identity Pool** | From an existing identity, which temporary AWS permissions does the app receive? | Identity Pool issues credentials via an IAM role |

**Successful sign-in does not mean permission to read all data.** A valid access token only proves the token issuance conditions and the permissions at the claims/scopes level that you designed. The backend still needs to check permissions for **each order, tenant, file, and operation**.

**An Identity Pool is also not a place to store passwords instead of a User Pool.** It can trust a User Pool or supported IdPs, then connect that identity to IAM permissions. The shared "Cognito" name often causes these two responsibilities to be conflated, leading to security flaws.

## 3. Comparison Table: User Pool vs. Identity Pool

| Criterion | Cognito **User Pool** | Cognito **Identity Pool** |
|---|---|---|
| Primary purpose | **Sign-up, sign-in, IdP federation, token issuance** | **Identity federation and obtaining temporary AWS credentials** |
| Managed objects | User directory, profile attributes, groups, app clients | Federated identity IDs, identity providers, authenticated/guest roles, role mappings |
| Authentication data | Password/challenge, IdP federation, MFA/passkey depending on features | Uses sign-in proof from an IdP; can support **unauthenticated** guests |
| Typical output | **ID JWT, access JWT, refresh token** | **AWS temporary credentials** and **IdentityId** |
| Standards/targets | OAuth 2.0, OpenID Connect, sign-in, and API authorization | IAM role, STS web identity, signing AWS SigV4 requests |
| API Gateway integration | JWT/User Pool authorizer validates tokens | IAM authorization via credentials if the API is configured with AWS_IAM |
| Direct use with S3/DynamoDB | User Pool tokens **are not themselves** AWS access keys | Can call AWS SDK with least-privilege credentials |
| Guest/unauthenticated | Not the goal of a signed-in User Pool session | Optional **unauthenticated identities** when explicitly enabled |
| Must use together? | No | No; can also use external IdPs without a User Pool |
| Recognizable identifiers | User Pool ID in format **region_...**, app client ID | Identity Pool ID in format **region:UUID** |
| Access control | OAuth scopes, JWT claims/groups, and API-level checks | IAM policies, trust policies, role mappings/ABAC |

**Remember in one sentence:** User Pool tells you **who signed in and which token proves it**; Identity Pool tells you **which AWS credentials with which IAM permissions the application receives**. Do not use them interchangeably.

### 3.1. Quick Selection Examples

- An ordering website with its own Java/Lambda API: **User Pool** may be sufficient; the API verifies the access token and per-order permissions.
- A mobile app downloading personal assets directly from S3: can use **User Pool + Identity Pool**, with a role allowing only the right prefix.
- An app that only uses **Google/OIDC** as its IdP and needs AWS credentials for the client: can use **Identity Pool** federating directly with the IdP **without a User Pool** if requirements are met.
- Public content placed behind CloudFront: neither is needed by default; consider public CDN or signed URLs/cookies according to the access model.
- Backend Lambda calling DynamoDB with service permissions: typically uses the **Lambda execution role**, **not** an Identity Pool to grant permissions to the backend.

## 4. User Pool: User Directory and Token Issuer

### 4.1. Components in a User Pool

A **User Pool** stores or federates user profiles and authentication configurations. Common components:

| Component | Role |
|---|---|
| **User directory** | User attributes such as username, email, phone, and verification status |
| **App Client** | Application integrating with the User Pool, OAuth grant types, redirect URIs, scopes, token lifetimes |
| **Managed login / Hosted UI** | Sign-in UI managed by Cognito according to configuration |
| **Domain** | Endpoints for OAuth/OIDC authorize/token/logout and related links |
| **Identity provider federation** | Configured Google, Apple, SAML/OIDC IdPs |
| **MFA and account recovery** | Additional steps to protect accounts and handle recovery |
| **Groups and custom attributes** | Group/attribute metadata supporting access rules |
| **Lambda triggers** | Customize certain sign-up/sign-in/token steps via supported triggers |

A User Pool can store directly registered users or federate identities from another IdP; during federation, Cognito can map the IdP's claims into the User Pool's own profile and tokens. The application sees the **User Pool issuer** instead of handling every login mechanism itself.

### 4.2. Public App Client vs. Confidential App Client

- **Public client**: an application running in a browser/mobile app that cannot securely keep a secret. **Do not embed a client secret** in a JavaScript bundle or mobile app.
- **Confidential client**: a backend/server-side app capable of protecting a client secret architecturally. It can use OAuth grant types that require client authentication.

For SPAs/mobile apps, best practice is **OAuth 2.0 Authorization Code Flow + PKCE (S256)**, validating **state** and **nonce** where appropriate, exact redirect URIs, and HTTPS. PKCE prevents another party from exchanging a stolen authorization code for tokens; it **does not replace** token verification and backend authorization.

### 4.3. User Pool Sign-In Sequence Diagram

~~~mermaid
sequenceDiagram
    participant U as User
    participant APP as Web / Mobile App
    participant UP as Cognito User Pool
    participant API as API Gateway / Backend
    U->>APP: Open sign-in screen
    APP->>UP: /oauth2/authorize + PKCE + state
    UP->>U: Authenticate, MFA / IdP if configured
    UP-->>APP: Authorization code via callback
    APP->>UP: /oauth2/token + code_verifier
    UP-->>APP: ID token, access token, refresh token
    APP->>API: Authorization: Bearer ACCESS_TOKEN
    API->>API: Verify signature, issuer, client, exp, scopes
    API-->>APP: Authorized business response
~~~

This example **does not need an Identity Pool**. API Gateway can validate the JWT before forwarding the request to the backend, but the backend must still enforce **object-level authorization**, such as verifying the order belongs to the right user/tenant.

## 5. The Three User Pool Tokens: Do Not Misuse Them

| Token | Format | Intended Purpose | Common Misconceptions |
|---|---|---|---|
| **ID token** | Signed JWT | Identity information for the app; **sign-in proof when linking User Pool with Identity Pool** | Not an AWS AccessKeyId; does not automatically substitute for an API access token |
| **Access token** | Signed JWT | Calling APIs and allowed actions per OAuth scopes/claims; certain Cognito self-service APIs | Not IAM session credentials |
| **Refresh token** | Opaque token | Requesting new ID/access tokens per expiration and refresh policy | Not a JWT to send to APIs or pass to an Identity Pool |

### 5.1. What Does an ID Token Contain?

Example of shortened claims structure, **not a real token**:

~~~json
{
  "iss": "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE",
  "sub": "11111111-2222-3333-4444-555555555555",
  "aud": "APP_CLIENT_ID",
  "token_use": "id",
  "email_verified": true,
  "exp": 1900000000
}
~~~

The **sub** value here is the **User Pool user subject**. It is not identical to the **IdentityId** of an Identity Pool. If the app needs to associate both IDs, maintain a secure mapping and avoid treating an email address as an immutable key.

### 5.2. What Does an Access Token Contain?

Example of shortened claims:

~~~json
{
  "iss": "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE",
  "sub": "11111111-2222-3333-4444-555555555555",
  "client_id": "APP_CLIENT_ID",
  "token_use": "access",
  "scope": "openid orders/read",
  "exp": 1900000000
}
~~~

APIs use the **access token** for OAuth scopes, such as **orders/read**, when a resource server and scopes are appropriately configured. In many User Pool flows, **aud** is in the ID token while the access token typically contains **client_id**; an access token bound to a resource server may have its own aud. Check according to token type and actual configuration—do not write a single parser assuming both token types always share identical claims.

### 5.3. How to Verify a JWT Securely

When the backend verifies JWTs itself:

1. Read the token over **HTTPS** and enforce a reasonable size limit; **do not trust claims before verification**.
2. Verify the **RS256 signature** using public keys from the exact User Pool's **JWKS endpoint**, matching **kid** and handling key rotation.
3. Verify **iss** matches the expected User Pool; check **exp**, **token_use**, and relevant timestamps.
4. Verify **aud** of the ID token or **client_id/audience** of the access token per your security contract.
5. For APIs, verify **scope**, group/role, and **resource-level permissions** for the request.
6. Maintain an expiration/revocation policy; offline JWT verification may still consider signature and exp valid even if the token was revoked before expiration.

The JWKS URL typically has the form:

~~~text
https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE/.well-known/jwks.json
~~~

**Merely Base64-decoding a JWT to inspect its payload is not token verification.** Never make authorization decisions based on an unverified JWT. An API Gateway HTTP API JWT authorizer can verify JWTs at the gateway layer on behalf of the app; for routes requiring permissions, configure **authorization scopes** to avoid accidentally accepting an ID token when the route must require an access token.

### 5.4. Token Refresh and Storage

ID/access tokens typically have short lifetimes; refresh tokens live longer depending on app client configuration and may use rotation. For browsers, consider a **backend-for-frontend (BFF)** with **HttpOnly/Secure/SameSite** cookies or an appropriate token storage strategy that mitigates XSS. For native mobile, use the OS secure storage. Never store refresh tokens or client secrets in logs, URLs, analytics, or source code.

**An access token is not used to obtain AWS STS credentials directly** in the standard flow integrating Cognito User Pool with Identity Pool. For Identity Pool, the proof from **User Pool is the ID token**, per AWS documentation.

## 6. Identity Pool: Federated Identities and Temporary AWS Credentials

**Cognito Identity Pool** is also known as **federated identities**. The service allows an application to use authentication proof from a supported IdP to receive an **IdentityId** and **temporary AWS credentials**. The Identity Pool selects a role based on configuration to restrict permissions against S3, DynamoDB, API Gateway with IAM authorization, or other AWS services.

### 6.1. IdPs That Identity Pool Can Trust

Identity Pool can integrate with:

- **Cognito User Pool** and the ID token issued after sign-in.
- Compatible **OIDC identity providers**.
- **SAML 2.0 identity providers** and corresponding assertions.
- Certain **social identity providers** according to supported token types.
- **Developer authenticated identities** where a trusted backend is responsible for proving identity.
- **Unauthenticated (guest) identities** if enabled, requiring no prior sign-in.

**It is not mandatory to create a User Pool if Identity Pool already accepts a supported IdP directly** and the application does not need User Pool account/flow management. Conversely, if you only need JWTs for a backend-controlled API, do not create an Identity Pool simply because the app uses Cognito.

### 6.2. Enhanced Authentication Flow

The commonly recommended flow is **enhanced/simplified**:

1. The application obtains authentication proof from an IdP, such as a **User Pool ID token**.
2. The application calls **GetId** with the Identity Pool ID and **Logins** map.
3. The Identity Pool returns the corresponding **IdentityId**.
4. The application calls **GetCredentialsForIdentity** with the IdentityId and authentication proof.
5. The Identity Pool selects an IAM role per role mappings and coordinates with AWS STS to return **temporary credentials**.
6. The AWS SDK uses **AccessKeyId + SecretAccessKey + SessionToken** to sign requests to S3, DynamoDB, or authorized services.

~~~mermaid
sequenceDiagram
    participant APP as Mobile / Browser
    participant UP as User Pool
    participant IP as Identity Pool
    participant STS as AWS STS
    participant S3 as Amazon S3
    APP->>UP: Login / OAuth code + PKCE
    UP-->>APP: ID token + access/refresh token
    APP->>IP: GetId + Logins[USER_POOL_PROVIDER] = ID token
    IP-->>APP: IdentityId
    APP->>IP: GetCredentialsForIdentity + ID token
    IP->>STS: Select IAM role / web identity
    STS-->>IP: Temporary AWS credentials
    IP-->>APP: AccessKeyId + SecretAccessKey + SessionToken + Expiration
    APP->>S3: SigV4 request with temporary credentials
    S3-->>APP: Object when both IAM and resource policies allow
~~~

Applications should use the appropriate **AWS SDK or AWS Amplify credentials provider** rather than manually storing and signing credentials. The SDK can manage obtaining and refreshing temporary credentials according to the configured mechanism. **Do not** copy temporary credentials into localStorage, logs, or hard-code them; even with an expiration, they hold real AWS permissions while valid.

### 6.3. Correct Logins Map Format for User Pool

When integrating User Pool with Identity Pool, the **provider name/key** in the Logins map has the form:

~~~text
cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE
~~~

Unlike the JWT issuer above, this key **does not have the https:// prefix**. Conceptual payload example for GetId:

~~~json
{
  "IdentityPoolId": "ap-southeast-1:11111111-2222-3333-4444-555555555555",
  "Logins": {
    "cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE": "ID_TOKEN_FROM_USER_POOL"
  }
}
~~~

**ID_TOKEN_FROM_USER_POOL** is a placeholder, not a usable token. The Identity Pool must have the **exact User Pool and App Client ID** registered in its identity providers configuration. Passing an access token instead of an ID token in Logins for User Pool, using the wrong Region, wrong provider key, or wrong app client will result in authentication errors.

### 6.4. IdentityId Is Not User Pool sub

| Identifier | Scope | Example |
|---|---|---|
| **User Pool sub** | User within a User Pool | UUID like 11111111-... |
| **User Pool ID** | User directory/auth issuer | ap-southeast-1_EXAMPLE |
| **App Client ID** | OAuth/OIDC application | APP_CLIENT_ID |
| **Identity Pool ID** | Configured Identity Pool | ap-southeast-1:11111111-... |
| **IdentityId** | Federated identity returned by Identity Pool | ap-southeast-1:aaaaaaaa-... |
| **IAM role ARN** | Set of AWS permissions assignable to an identity | arn:aws:iam::111122223333:role/app-user-role |

**Do not take User Pool sub and substitute it directly for IdentityId**. They belong to two different identifier systems; when applying IAM policy variables for Identity Pool, the identity value is the Identity Pool identity ID, not the User Pool subject.

## 7. IAM Role, Role Mapping, and Guest Access in Identity Pool

Identity Pool does not grant all AWS permissions by itself. It associates an identity with an **IAM role** and corresponding policies; effective permissions are further constrained by resource policies, KMS policies, permission boundaries, SCPs, and other active controls.

### 7.1. Authenticated Role and Unauthenticated Role

| Role | Who can receive it? | Principle |
|---|---|---|
| **Authenticated role** | Identities authenticated via a provider accepted by the Identity Pool | Grant only the minimum AWS actions required by the business |
| **Unauthenticated (guest) role** | Users who have not signed in, **if guest access is enabled** | Grant only permissions the organization is willing to expose publicly to anyone |
| **Role by claims/rules/groups** | Identities with attributes matching role mapping | Test each selected role, handle missing claims and multiple roles |

**Enabling guest access means unauthenticated users can still obtain temporary AWS credentials with the guest role's permissions.** Do not treat the Identity Pool ID as a password or secret; anyone who knows the public configuration and can reach the service can attempt to use granted guest permissions. Disable guest access if the app does not need it, or allow reading only minimal resources.

### 7.2. IAM Trust Policy Must Bind to the Exact Identity Pool

A role trust policy defines **who can assume the role**, distinct from the permissions policy defining **which AWS APIs the role can call**. With the enhanced flow, Identity Pool uses STS associated with **AssumeRoleWithWebIdentity**. The role must trust the principal **cognito-identity.amazonaws.com** and constrain **aud = exact Identity Pool ID**; it should also include the condition **amr = authenticated** or **unauthenticated** depending on the role.

Example trust policy for an **authenticated role** (IDs are for illustration only):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOnlyAuthenticatedIdentitiesFromThisPool",
      "Effect": "Allow",
      "Principal": {
        "Federated": "cognito-identity.amazonaws.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "cognito-identity.amazonaws.com:aud": "ap-southeast-1:11111111-2222-3333-4444-555555555555"
        },
        "ForAnyValue:StringLike": {
          "cognito-identity.amazonaws.com:amr": "authenticated"
        }
      }
    }
  ]
}
~~~

**aud in this trust policy is the Identity Pool ID**, not the App Client ID or the **aud** of a User Pool ID token. **amr** describes the authentication state and sign-in source in the identity-pool token; for a guest role, the condition must match **unauthenticated**.

Do not allow a trust policy to accept **any identity pool**, or omit the aud condition and rely on role naming for security. In the **enhanced flow**, roles are chosen per Identity Pool configuration and must satisfy the service's account/role conditions. The **basic/classic flow** interacts with STS differently, so do not mechanically apply the same role selection assumptions; prefer the enhanced flow unless there is a specific requirement.

### 7.3. Per-IdentityId S3 Permission Policy

Example: each signed-in user may only read objects in the prefix corresponding to their own identity:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadObjectsInOwnIdentityPrefix",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::example-private-users/files/${cognito-identity.amazonaws.com:sub}/*"
      ]
    }
  ]
}
~~~

**IDENTITY_SUB_VAR** in the path above is substituted by the Identity Pool IAM policy variable. IAM automatically populates the identity ID from the assumed role session; this **is not** a string the browser is allowed to arbitrarily send to broaden access. Plan how object keys are created/moved according to actual prefixes and check permissions, bucket policies, S3 Block Public Access, KMS, and Object Ownership.

For example, granting only **s3:GetObject** should not implicitly include **s3:ListBucket** or **s3:PutObject**. If the app must upload, build a separate prefix policy, validate object size and media type, perform malware scanning, and configure CORS and appropriate S3 conditions. Users must not be granted bucket administration permissions or access to other users' data.

**Technical note:** the policy variable **cognito-identity.amazonaws.com:sub** is the **Identity Pool identity ID**, not the **sub** inside the User Pool JWT. If the backend organizes directories by User Pool sub, maintain a mapping or design permissions appropriately rather than directly concatenating or equating the two IDs.

### 7.4. Role Mapping from User Pool Claims

Identity Pool can apply a **default authenticated role**, **rules based on claims**, or **token-based role mapping**. When combined with User Pool groups, tokens can carry claims such as **cognito:groups**, **cognito:roles**, and **cognito:preferred_role** per configuration; Identity Pool can use these to select a role.

For example, the **premium** group has permission to view a different set of assets than the **standard** group. Placing a user into a User Pool group **does not automatically grant IAM permissions**: you need the corresponding role, trust policy, permission policy, and role mapping. When a token matches multiple roles or no rule matches, the **AmbiguousRoleResolution** setting determines whether to fall back to the default role or deny; test this to avoid overly broad fallbacks.

**Do not use Cognito groups as a substitute for all business authorization checks.** For example, **premium** only indicates a customer tier, not that the person owns a specific invoice.

## 8. Three Architectural Patterns to Distinguish

### 8.1. User Pool Only: Application Protects Its Own API

~~~mermaid
flowchart LR
    U["Web / Mobile user"] --> UP["Cognito User Pool<br/>Sign-in + tokens"]
    UP -->|"Access JWT"| APP["Client application"]
    APP -->|"Bearer access JWT"| API["API Gateway JWT authorizer<br/>or backend verify"]
    API --> L["Lambda / ECS / EC2"]
    L -->|"Execution / task role"| DB["DynamoDB / RDS / S3"]
~~~

Suitable when the client only needs to call **the application's API**. The backend retains its own AWS access permissions; users do not hold AWS access keys. The API verifies the token and enforces **business authorization**, such as fetching orders by **tenantId + ownerId**.

**You do not need an Identity Pool** just for API Gateway to verify a User Pool access JWT.

### 8.2. Identity Pool Only: External IdP or Guest Access

~~~mermaid
flowchart LR
    CLIENT["Mobile / Web client"] --> IDP["External OIDC / SAML / Social IdP<br/>or guest identity"]
    IDP --> CLIENT
    CLIENT -->|"Provider proof or guest"| IP["Cognito Identity Pool"]
    IP -->|"Temporary AWS credentials"| CLIENT
    CLIENT -->|"Signed AWS requests"| AWS["S3 / DynamoDB / AWS_IAM API"]
~~~

Suitable when the app already has an IdP and only needs **temporary AWS credentials** via IAM, or wants to serve assets to guests with truly minimal permissions. In this design, **Identity Pool does not provide a sign-in UI** for the IdP and does not replace a user password management system.

### 8.3. Combining Both: User Pool for Sign-In, Identity Pool for IAM

~~~mermaid
flowchart TB
    CLIENT["Mobile / SPA"] --> LOGIN["User Pool + app client<br/>Managed login / OAuth PKCE"]
    LOGIN --> TOKENS["ID token + access token"]
    TOKENS -->|"Access token"| API["API Gateway / App API"]
    TOKENS -->|"ID token"| IP["Cognito Identity Pool"]
    IP --> ROLE["IAM role + STS credentials"]
    ROLE -->|"SigV4"| S3["S3 private objects<br/>Scoped identity prefix"]
    API --> DB["Backend + database"]
~~~

Suitable when the same client both calls **application APIs using an access token** and directly accesses **a subset of AWS resources via identity-scoped credentials**. Both credential types coexist but serve distinct purposes.

### 8.4. Quick Decision Table

| Primary Requirement | User Pool | Identity Pool | Why? |
|---|---|---|---|
| Sign-in and protecting a custom REST API | **Yes** | Not required | Access token/JWT authorizer is sufficient for many APIs |
| Google/SAML sign-in through a unified issuer and user profile | **Yes** | Not required | User Pool federates the IdP and issues tokens |
| Browser receiving IAM permissions to read S3 objects per user | Usually has IdP | **Yes** | Requires temporary AWS credentials and a least-privilege role |
| AWS SDK client calling DynamoDB directly via IAM | Not required | **Yes** | Identity Pool federates the IdP to temporary credentials |
| Serving only public images from S3 via CloudFront | Not required | Not required | Public/cached data does not necessarily require sign-in |
| Backend Lambda calling S3/DynamoDB | Not required | Not required | Use the Lambda execution role for the backend |
| Guest reading a controlled set of assets via IAM | Not required | Optional | Guest role grants only permissions safe for any visitor |

## 9. API Access and AWS Resource Access Are Two Authorization Models

### 9.1. API Gateway + User Pool Access Token

A **GET /orders/{id}** route may require an access JWT with the **orders/read** scope. The JWT authorizer validates the issuer/audience and signature; the route scope indicates the request holds the declared API-level permission. The backend then checks the data:

| Step | Check | Who performs it? |
|---|---|---|
| 1 | Signature, issuer, expiry, audience/client, and appropriate token type | API Gateway authorizer or backend |
| 2 | Scope **orders/read** for the route | JWT authorizer/backend |
| 3 | Order belongs to the user/tenant in the token and the user is allowed to view it | Backend/authorization service |
| 4 | Query database and return allowed fields | Backend |

**A valid JWT does not allow viewing someone else's order.** If the backend only verifies the signature and then uses **orderId** from the URL, a user can exploit **broken object-level authorization (BOLA/IDOR)**. Identity Pool does not fix that business logic vulnerability either.

### 9.2. API Gateway AWS_IAM + Identity Pool Credentials

An API can be configured with **AWS_IAM**. In that case, the client uses **temporary credentials** from Identity Pool and the AWS SDK signs requests with **Signature Version 4 (SigV4)**, instead of just sending a **Bearer access JWT**. The IAM policy must grant **execute-api:Invoke** for the specific API/stage/method/resource, and any resource policy/authorizer must also allow it.

Choose a consistent authorization model per route. A route configured for AWS_IAM will not automatically accept a Bearer JWT as a signed IAM request; conversely, a JWT authorizer does not automatically derive a customer's IAM role from an access token.

### 9.3. Direct S3 Access: Convenient but Comes with Responsibilities

When clients call S3 directly with Identity Pool credentials:

- IAM policy, bucket policy, KMS, and CORS must all be configured properly.
- The browser/app must not receive permissions broader than a specific prefix or object.
- Direct API access can reduce proxy traffic but requires **client-side upload validation**, size/type limits, malware scanning, and metadata controls.
- For many **one-off upload/download** cases, having the backend issue a **presigned S3 URL** through an authenticated API can be simpler than issuing AWS credentials to each client. Presigned URLs must have appropriate TTLs, scopes, and revocation/control processes.

**Identity Pool is not mandatory for every S3 upload.** Compare direct credential flows with presigned URLs based on security posture, operation frequency, volume, offline needs, and user experience.

## 10. Step-by-Step Design Process for User Pool and Identity Pool

### Step 1 — Identify Users, IdPs, and Application Types

Who are the users: shoppers, employees, partners, or machine-to-machine? Is the application a web SPA, mobile app, or confidential backend client? Do you need new user registration, MFA, password reset, social sign-in, enterprise SAML/OIDC, and attribute management?

**Output:** decide whether a **User Pool** is needed along with appropriate OAuth grant types and authentication methods. Avoid using a User Pool as an issuer of IAM access keys.

### Step 2 — Classify How Resources Are Accessed

List each request path:

- **Client → Application API**: typically uses a **User Pool access token**.
- **Client → S3/DynamoDB/AWS_IAM API directly**: consider **Identity Pool** or presigned URLs.
- **Backend → AWS services**: use an **IAM execution/task/instance role**; do not borrow user credentials unless there is an explicit architectural requirement.

**Output:** a matrix of **principal × operation × resource × authorization method**, rather than deciding based solely on service names mentioned in an architecture diagram.

### Step 3 — Configure User Pool First If Sign-In Is Needed

Create the User Pool in the chosen Region, configure an app client compatible with public/confidential apps, domain/managed login, redirect/logout URIs, sign-in methods, MFA, attributes, scopes, and token durations. For SPAs/native apps, use **Authorization Code + PKCE**; do not embed a client secret.

If using an external IdP, configure the provider, claim mapping, and test missing-email or changed-email cases. Create groups or custom scopes when justified by business logic; do not treat them as data ownership checks in place of the backend.

### Step 4 — Integrate the API and Verify Tokens

Configure an API Gateway JWT/User Pool authorizer or backend verifier. Test signature/JWKS rotation, issuer, token type, client/audience, expiry, and scopes. Test **two different users** against the same resource path to prove neither can read the other's data.

### Step 5 — Create an Identity Pool Only If Clients Need AWS Credentials

Link the User Pool/App Client or external IdP. Define the authenticated role, **guest role only when genuinely needed**, role mapping, IAM trust/permission policies, bucket policies, and KMS. Verify the Logins map, IdentityId, and SDK credentials provider. Never test with AdministratorAccess.

### Step 6 — Test Failure Modes, Lifecycle, and Observability

Test expired/revoked tokens, wrong JWT issuer, missing scopes, denied guest role, IAM AccessDenied, another user's S3 prefix, CORS, refresh tokens, key rotation, IdP outages, and the rollout timing of new role policies. Log minimal traceable data without exposing tokens or credentials.

## 11. AWS CLI: Inventorying Both Pools Without Creating Resources

These commands only **read configuration** and require an AWS identity with appropriate permissions. The Region **ap-southeast-1**, User Pool ID, App Client ID, and Identity Pool ID below are placeholders. **Do not** call sign-in APIs with real accounts, print tokens, or issue credentials in inventory examples.

### 11.1. Inspecting User Pools and Sign-In Configuration

~~~bash
# List existing User Pools in the selected Region.
aws cognito-idp list-user-pools \
  --region ap-southeast-1 \
  --max-results 20 \
  --query 'UserPools[].{Id:Id,Name:Name,LastModified:LastModifiedDate}' \
  --output table

# Inspect a specific User Pool.
aws cognito-idp describe-user-pool \
  --region ap-southeast-1 \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --query 'UserPool.{Id:Id,Name:Name,Domain:Domain,MfaConfiguration:MfaConfiguration,Policies:Policies}' \
  --output json

# List App Clients in the User Pool.
aws cognito-idp list-user-pool-clients \
  --region ap-southeast-1 \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --max-results 20 \
  --output table

# Inspect an App Client to review OAuth flows/callbacks.
aws cognito-idp describe-user-pool-client \
  --region ap-southeast-1 \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --client-id APP_CLIENT_ID \
  --query 'UserPoolClient.{ClientId:ClientId,Name:ClientName,CallbackURLs:CallbackURLs,LogoutURLs:LogoutURLs,AllowedOAuthFlows:AllowedOAuthFlows,AllowedOAuthScopes:AllowedOAuthScopes}' \
  --output json
~~~

**Security note:** the full **DescribeUserPoolClient** response may contain the secret field of a confidential app client. That is why the example selects only non-sensitive fields; do not paste full outputs into public issues/tickets/chats. When checking whether an app client has a secret, report only the boolean/assessment from an authorized environment—never copy the secret value.

### 11.2. Inspecting Identity Pools, Providers, and IAM Roles

~~~bash
# List Identity Pools.
aws cognito-identity list-identity-pools \
  --region ap-southeast-1 \
  --max-results 20 \
  --query 'IdentityPools[].{Id:IdentityPoolId,Name:IdentityPoolName}' \
  --output table

# Inspect providers and guest access settings.
aws cognito-identity describe-identity-pool \
  --region ap-southeast-1 \
  --identity-pool-id ap-southeast-1:11111111-2222-3333-4444-555555555555 \
  --query '{Id:IdentityPoolId,Name:IdentityPoolName,Guest:AllowUnauthenticatedIdentities,UserPoolProviders:CognitoIdentityProviders,OpenIdProviders:OpenIdConnectProviderARNs}' \
  --output json

# Read IAM role ARNs and role mappings.
aws cognito-identity get-identity-pool-roles \
  --region ap-southeast-1 \
  --identity-pool-id ap-southeast-1:11111111-2222-3333-4444-555555555555 \
  --output json
~~~

These commands reveal which Identity Pools allow guest access, which User Pools/App Clients are linked, and which roles are selected. **GetIdentityPoolRoles** only shows role assignments/mappings; to evaluate actual effective permissions, inspect **IAM trust policies, identity-based permissions, resource policies, and permission boundaries/SCPs** using an appropriate audit process.

**Note the AWS CLI service names:**

- **cognito-idp**: operates on **User Pools and app clients**.
- **cognito-identity**: operates on **Identity Pools and federated identities**.

This is a quick way to distinguish them when reading CloudTrail logs, IaC, or SDK errors. The **cognito-idp** APIs do not issue temporary IAM credentials to end users.

## 12. Security Model: The Most Critical Risks

### 12.1. Threat Model Across Three Assets

| Asset | Risk | Key Controls |
|---|---|---|
| **User session / JWT** | Token leakage, replay, expired token, token type confusion | HTTPS, PKCE, CSRF state, secure storage, signature/issuer/scope/exp checks |
| **Identity Pool credentials** | Guest or client receives overly broad role, stolen credentials | Trust aud/amr, least-privilege IAM, TTL, identity-scoped policies, audit |
| **Business data** | Valid user reads another user's objects/orders | Backend object-level authorization, S3 prefix/resource policies, tenant isolation |

For SPAs/mobile apps, there is no way to keep a static client secret reliably safe from extraction. **Public client + PKCE** is the more suitable pattern. If the app uses a server-side session/BFF, verify **HttpOnly/Secure/SameSite** cookies, CSRF protections, and refresh token protection on the backend.

### 12.2. Token Type Confusion Risk

A backend that accepts a **Bearer ID token** on a route meant for an **access token** can bypass scope policies. Verify **token_use = access** and the corresponding claims, or use an authorizer configured with route scopes. **Never** check only that a signature is valid and let every request through.

Similarly, the **Identity Pool ID token flow** must use the exact **User Pool ID token**—do not swap in an access token just because both are JWTs.

### 12.3. Overly Broad IAM Role Trust Risk

An IAM role trusting **cognito-identity.amazonaws.com** without binding to the exact **Identity Pool aud** can open a path to assume the role out of scope. Authenticated roles must restrict **amr = authenticated**; guest roles need explicit conditions and very narrow permissions. Never assume that naming a role **AppAuthenticatedRole** tells AWS it is only for signed-in users.

### 12.4. Cross-Tenant Authorization

In multi-tenant SaaS, **User Pool groups/Identity Pool roles** can assist with tiering, but are insufficient if all tenants share a single IAM role or API endpoint. The backend must verify **tenantId** and ownership from a trusted source. For direct S3 access, use verified policy variables/ABAC or bucket/prefix isolation—never trust a client-supplied tenantId claim as authorization.

### 12.5. MFA, Account Management, and Fraud

User Pool can enforce MFA, password policies, account recovery, passkeys, or advanced threat protection depending on tier and supported features. Enable protections aligned with application risk, separating admin accounts from regular users. **Identity Pool does not replace MFA or sign-in policies**; it only accepts proof from configured identity providers.

**Workforce identities differ from application customers:** when the requirement is employees accessing AWS accounts, AWS IAM Identity Center may be a better fit. Do not treat Cognito User Pool as a default replacement for every internal enterprise identity system.

## 13. Common Errors and How to Diagnose Them

| Symptom | Likely Cause | Diagnostic Checks |
|---|---|---|
| User Pool sign-in fails | Unverified user, incomplete MFA challenge, wrong password/flow | User status, app client auth flows, challenge response |
| OAuth returns **invalid_client** | Wrong client ID/secret, confidential client auth error | Public/confidential client type, token endpoint config |
| OAuth returns **invalid_grant** | Expired or reused authorization code, invalid redirect or PKCE | Callback, single-use code exchange, code_verifier |
| OAuth returns **invalid_scope** | Scope not enabled on app client or invalid request | Resource server and AllowedOAuthScopes |
| API Gateway returns **401** | Missing/invalid JWT, wrong signature/iss/aud/exp | Issuer, JWKS kid, token type, app client |
| API Gateway returns **403** | Route scope/authorization mismatch or backend denial | OAuth scope, IAM/API policy, object-level permission |
| Token decodes successfully but API still rejects it | Decoding is not verifying, wrong issuer/token_use | Verify JWT and claims per API contract |
| Identity Pool reports **Token is not from a supported provider** | Wrong Logins key, unregistered User Pool/App Client, wrong token sent | Provider name, region, exact ID token, client mapping |
| **InvalidIdentityPoolConfigurationException** | Unassigned IAM role or incorrect role trust aud/amr | Identity Pool roles, IAM trust principal/conditions |
| **Unauthenticated access is not supported** | Guest access disabled but app calls Identity Pool without Logins | Enable controlled guest access or require sign-in |
| STS **AccessDenied** on assume role | Role trust disallows identity pool/auth state, boundary/policy blocks | aud, amr, role, account, SCP, and error context |
| S3 returns **AccessDenied** after obtaining credentials | IAM role lacks s3 actions, wrong prefix, bucket/KMS policy denies | IdentityId, role, object ARN, bucket policy, KMS, Block Public Access |
| Browser hits **CORS** when calling S3 | CORS rule disallows origin/method/header; IAM may not be the cause | Browser network tab, S3 CORS config, IAM separately |
| User Pool sign-in succeeds but AWS SDK reports missing credentials | Identity Pool/credentials provider unconfigured, refresh failing | SDK auth + credentials config, Identity Pool ID, Logins |
| Admin group user does not receive corresponding role | Role mapping, token claim, ambiguous resolution, or trust error | ID token claims, PreferredRole, mappings |
| Switching account/IdP changes IdentityId | Identity mapping and linking not working as expected | IdP subject, GetId response, backend mapping |
| User signs out yet old token still verifies offline | JWT signature/exp remain valid after revocation | Token lifetime, revocation strategy, backend session policy |

### 13.1. Layered Diagnostic Workflow

~~~mermaid
flowchart TD
    A["User cannot access resource"] --> B{"Where does the error occur?"}
    B -->|"Login / OAuth"| UP["User Pool: app client,<br/>MFA, PKCE, redirect, IdP"]
    B -->|"API 401 / 403"| API["JWT issuer/audience/exp/scope<br/>and backend object authorization"]
    B -->|"GetId / credentials"| IP["Identity Pool providers, Logins,<br/>roles, trust aud/amr"]
    B -->|"AWS API AccessDenied"| IAM["IdentityId + IAM permission<br/>resource policy + KMS"]
    UP --> END["Fix at the right layer, retest with<br/>two users/tenants, record evidence"]
    API --> END
    IP --> END
    IAM --> END
~~~

**Do not widen a role to AdministratorAccess just to debug an S3 403 error.** First determine whether the request uses a JWT, temporary AWS credentials, or a backend session; find the policy actually blocking it; then grant only the minimum required permissions.

### 13.2. Distinguishing 401, 403, and CORS

- **401 Unauthorized** typically indicates missing or unacceptable authentication proof at the API.
- **403 Forbidden** typically means the request was received/authenticated, but lacks permission, or was denied by WAF/resource policy/authorizer.
- **CORS error** is a browser mechanism blocking access to cross-origin responses; it is not enough to conclude IAM or User Pool is misconfigured.

Inspect the **HTTP status**, response body, CloudTrail/CloudWatch logs, request origin, OPTIONS preflight, and effective permissions. A browser may display a CORS error while the backend service actually returned an auth error; inspect the network trace to tell them apart.

## 14. Operations, Monitoring, and Resilience

### 14.1. Observing Critical Layers

| Layer | What to monitor? | Suggested sources |
|---|---|---|
| **User Pool sign-in** | Authentication failures, MFA challenges, account lockout, token requests | Cognito/CloudWatch metrics, IdP logs per configuration |
| **API authorization** | 401/403, JWT verifier failures, invalid scopes | API Gateway access logs, Lambda/Java application logs |
| **Identity Pool federation** | GetId/GetCredentials failures, guest usage, failed role mappings | CloudTrail/AWS service metrics and appropriate app telemetry |
| **STS/IAM** | AccessDenied, assume role failures, policy changes | CloudTrail, IAM Access Analyzer, and IAM audits |
| **S3/DynamoDB** | 403s, access patterns, data transfer, wrong prefixes | Service logs/metrics, CloudTrail data events when enabled |
| **External identity providers** | IdP outages, certificate/metadata rotation, response latency | IdP health and application auth traces |

**CloudTrail does not automatically record every UI user sign-in as a complete application access log.** Identify precisely what telemetry each layer emits; the application must log appropriate business events itself without leaking tokens, passwords, secrets, or excessive PII into logs.

### 14.2. Why You Must Plan for Sign-In Outages

Do not assume a Cognito User Pool has automatic failover to another User Pool in a different Region. User Pools and Identity Pools have **Region-specific IDs**, and the JWT **issuer** is tied to the User Pool. If your system requires **cross-Region DR**, you need a dedicated plan for accounts, identity federation, app clients, domains/callbacks, profile data, passwords/recovery, secrets, DNS, and the backend.

**You cannot simply swing DNS to another User Pool and expect old JWTs to have a trusted issuer/audience.** You need a migration/federation plan, token validation updates, and user experience planning during failover.

### 14.3. Token Expiry, Revocation, and IdP Outages

When an access token expires, the app can refresh it if a valid refresh token remains. When a user is disabled or a token is revoked, design API rejection handling proportional to data sensitivity. Offline JWT verification will not automatically detect immediate revocations. During external IdP outages, new sign-ins may fail even while some existing sessions/tokens remain valid; any fallback options must comply with security policy and may require re-authentication after recovery.

## 15. Cost and Product Selection

Under the current AWS pricing model, **Cognito User Pools** offer tiers such as **Lite, Essentials, and Plus**, with charges potentially based on **monthly active users (MAU)**, federation type, and features. **Machine-to-machine token requests** or advanced capabilities may carry separate pricing models. Always check current pricing per Region/tier rather than assuming a fixed unit price for all User Pools.

**Identity Pools** currently do not charge separately for **authenticating users and generating unique identifiers** per the AWS pricing page. This **does not mean an app using Identity Pool is free**: S3/DynamoDB requests, data transfer, API Gateway, WAF, CloudWatch, SMS/email MFA, Lambda triggers, and related services still incur their standard charges.

| Line Item | What to Include in Estimates |
|---|---|
| **User Pool tier** | MAU, direct/social/SAML/OIDC sign-in types, Lite/Essentials/Plus tier |
| **OAuth/M2M** | Special token requests or machine-to-machine flows where applicable |
| **MFA/notifications** | SMS, email, delivery services, and fraud prevention |
| **Lambda triggers** | Invocations/duration for custom authentication and pre-token generation |
| **Identity Pool + AWS resources** | IAM credentials are scoped, but invoked AWS APIs still incur costs |
| **Observability** | CloudWatch logs/metrics, CloudTrail data events, WAF, tracing |
| **DR and operations** | Multi-Region if needed, account migration, auth incidents, support |

**Do not create an Identity Pool thinking it reduces auth costs.** It solves **AWS credential federation**, without changing the core cost structure of User Pool sign-in management. If the goal is uploading/reading a few objects, compare Identity Pool direct credentials against backend-issued **presigned URLs** before deciding.

## 16. Case Studies

### Scenario A — Ordering Website with a REST API

A Java Spring Boot application runs behind API Gateway with an RDS database. Customers sign in with email/MFA and then need to view their orders. The frontend does not call S3 or DynamoDB directly.

**Question:** choose User Pool, Identity Pool, or both?

**Hint:** **User Pool** is usually sufficient for sign-in and issuing access JWTs. API Gateway/backend validates the token, scope, and tenant/owner; Spring Boot accesses RDS using protected backend credentials. An Identity Pool is unnecessary just to validate JWTs.

### Scenario B — Photo App Downloading Personal Files from S3

A mobile app uses User Pool sign-in and wants to read/write per-user photos directly using the AWS SDK.

**Question:** what value does Identity Pool provide, and how must permissions be constrained?

**Hint:** pass the User Pool **ID token** to the Identity Pool to receive an **IdentityId** and temporary credentials for an authenticated IAM role. The S3 policy must allow only the prefix matching the **Identity Pool identity ID**, alongside bucket/KMS policies; also enforce upload limits, object validation, and SDK credential refresh.

### Scenario C — App with Google-Only Sign-In

A team already has Google/OIDC sign-in and does not need a User Pool to manage user profiles, but needs temporary AWS credentials to download controlled files.

**Question:** is it mandatory to create a User Pool?

**Hint:** no. You can link the Identity Pool directly to the supported IdP and define IAM roles. However, if you want a unified OIDC issuer, attribute mapping, account management, or Cognito-managed flows, a User Pool is a separate option to consider.

### Scenario D — Guest Credentials Abused

An Identity Pool enables **AllowUnauthenticatedIdentities** to read a public image, yet the guest IAM role grants **s3:* on the entire bucket**.

**Question:** why is this high risk?

**Hint:** any unauthenticated visitor can obtain temporary credentials with the guest role's permissions. Disable guest access if unneeded; otherwise grant only **s3:GetObject** on the exact asset, or consider public CloudFront as an alternative. Verify role trust aud/amr and monitor traffic.

### Scenario E — Valid JWT Rejected by the API

A client sends an ID token instead of an access token when calling **GET /orders/123**, while the API Gateway route requires the **orders/read** scope.

**Question:** why doesn't a valid JWT signature mean the API must accept it?

**Hint:** the ID token describes identity, whereas the access token carries OAuth scopes. Check **token_use**, route scopes, issuer/client/audience, and send the proper access token; the backend must still confirm order 123 belongs to the caller.

### Scenario F — Identity Pool Returns InvalidIdentityPoolConfigurationException

Sign-in succeeds, the app receives a User Pool ID token, and GetId returns an IdentityId, yet **GetCredentialsForIdentity** fails to issue credentials.

**Question:** what should you check?

**Hint:** Identity Pool authenticated role assignment, role mapping, role trust principal **cognito-identity.amazonaws.com**, **aud** condition matching the Identity Pool ID and **amr=authenticated**, account/role status, and IAM restrictions. Never attach AdministratorAccess to mask a trust error.

### Scenario G — Engineer Mixes Up the Two Pools' sub Values

The backend creates objects under **User Pool sub**, while the authenticated role's IAM policy restricts prefixes by **cognito-identity.amazonaws.com:sub**. Users receive AccessDenied.

**Question:** should you fix the path structure or the permissions?

**Hint:** the two **sub/IdentityId** values are not the same. Decide on the system's canonical identifier key, maintain a trusted mapping, and align the object prefix/policy accordingly. Never allow clients to arbitrarily choose another prefix to bypass permissions.

## 17. Production Deployment Checklist

- [ ] Clearly documented requirements for **authentication**, **API authorization**, and **AWS IAM authorization**.
- [ ] Created a **User Pool** only when sign-in/user directory/OIDC issuer capabilities are needed; created an **Identity Pool** only when clients need temporary AWS credentials.
- [ ] Recognized User Pool, App Client, Identity Pool, and IdentityId as four distinct identifiers.
- [ ] Public apps use Authorization Code + **PKCE**, **state**, and exact redirect URIs; no embedded client secret.
- [ ] Enabled MFA/account recovery and risk-appropriate sign-in protection policies.
- [ ] API verifies signature, **iss**, **exp**, **token_use**, client/audience, and **scope**.
- [ ] Backend enforces permissions down to **each object/order/tenant**, not just groups and valid JWTs.
- [ ] When linking User Pool to Identity Pool, uses the **ID token** with the exact Logins provider key and App Client.
- [ ] IAM role trust enforces **aud = Identity Pool ID**, appropriate **amr**, and exact principal and account.
- [ ] Authenticated/guest IAM policies follow **least privilege**; guest access disabled if unnecessary.
- [ ] Temporary AWS credentials are managed/refreshed by the SDK; never logged or stored like long-term keys.
- [ ] For direct S3 access, verified IdentityId prefixes, bucket policies, KMS, CORS, and upload security.
- [ ] Designed token storage, expiration, refresh/revocation, and JWKS rotation.
- [ ] Configured alerts for auth errors, API 401/403s, STS/IAM AccessDenied, and auditing for role/policy changes.
- [ ] Tested two distinct users/tenants, guest access, expired tokens, wrong issuers, missing scopes, and misconfigured role mappings.
- [ ] Accounted for IdP/Region outages, DR, profile migration, and token issuers during recovery.
- [ ] Estimated costs for User Pool tier/MAU, SMS, triggers, CloudWatch, API Gateway/S3, and related services.

## 18. Key Takeaways

**Cognito User Pool** solves **user sign-up, sign-in, identity provider federation, and issuing ID/access/refresh tokens**. A web/mobile app calling its own API with an **access token** typically **does not need an Identity Pool**. **Cognito Identity Pool** solves **exchanging an authenticated or guest identity for IAM roles and temporary AWS credentials**, enabling clients to use the AWS SDK to access resources under restricted permissions.

When combining both, the standard flow is **User Pool sign-in → ID token passed to Identity Pool → GetId + GetCredentialsForIdentity → IAM role/STS temporary credentials → signed AWS request**. Never confuse User Pool **sub** with Identity Pool **IdentityId**, never confuse an **access JWT** with an **AWS AccessKeyId**, and never let a valid JWT become an excuse to skip order/file/tenant-level authorization.

### Official AWS Documentation References

- [What is Amazon Cognito?](https://docs.aws.amazon.com/cognito/latest/developerguide/what-is-amazon-cognito.html) — comparison table of User Pools and Identity Pools.
- [Authenticating users with Amazon Cognito user pools](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools.html) — account management, IdP federation, sign-in.
- [Understanding user pool JSON web tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-with-identity-providers.html) — ID/access/refresh tokens.
- [Verifying JSON web tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html) — signature, issuer, scopes, and JWKS.
- [Using PKCE in authorization code grants](https://docs.aws.amazon.com/cognito/latest/developerguide/using-pkce-in-authorization-code.html) — protecting OAuth public clients.
- [Application-specific settings with app clients](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-client-apps.html) — public/confidential app clients.
- [Amazon Cognito identity pools](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-identity.html) — identity federation and AWS credentials.
- [Identity pools authentication flow](https://docs.aws.amazon.com/cognito/latest/developerguide/authentication-flow.html) — GetId, GetCredentialsForIdentity, enhanced/basic.
- [Access AWS resources with an identity pool after sign-in](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-integrating-user-pools-with-identity-pools.html) — integrating both Pools.
- [IAM roles for identity pools](https://docs.aws.amazon.com/cognito/latest/developerguide/iam-roles.html) — aud/amr trust conditions, IAM policy variables.
- [Role-based access control in identity pools](https://docs.aws.amazon.com/cognito/latest/developerguide/role-based-access-control.html) — claim-based role mapping.
- [Identity pool security best practices](https://docs.aws.amazon.com/cognito/latest/developerguide/identity-pools-security-best-practices.html) — least privilege and guest access.
- [Troubleshooting Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/troubleshooting.html) — token, IAM role, and IdP errors.
- [Amazon Cognito pricing](https://aws.amazon.com/cognito/pricing/) and [AWS Pricing Calculator](https://calculator.aws/) — current pricing by tier and related services.


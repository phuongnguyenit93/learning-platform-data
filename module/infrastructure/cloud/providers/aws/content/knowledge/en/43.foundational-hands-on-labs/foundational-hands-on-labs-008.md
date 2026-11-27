# Securing an Application API with Cognito and JWT Validation

An API cannot simply rely on a client sending a string that looks like a valid JWT. The backend must verify that the token was issued by the right identity provider, is not expired, was issued for the right application, and holds permissions for the invoked action. If you only verify the signature without checking scopes, a valid token granted only read access to user profiles could be misused to call an order management API.

In this hands-on lab, you build a user authentication flow with an Amazon Cognito User Pool, grant API permissions via OAuth 2.0 custom scopes, and protect endpoints using an Amazon API Gateway HTTP API JWT Authorizer. An AWS Lambda function acts as the backend to display the claims verified by API Gateway. The sign-in flow uses Authorization Code Grant with PKCE, suitable for public clients running in browsers or mobile apps.

This lesson belongs to the CLOUD_PROVIDERS_AWS module. You will practice creating a user pool, app client, resource server, managed login domain, JWT authorizer, and route scopes; then test requests with no token, invalid tokens, an ID token, an access token missing scopes, and an access token carrying the right scope.

## 1. Expected Outcomes

After this lab, you will be able to:

- Distinguish authentication, authorization, Cognito User Pools, and Identity Pools.
- Create a User Pool, public app client, and managed login domain.
- Define a resource server along with custom scopes.
- Use Authorization Code Grant with PKCE to obtain ID, access, and refresh tokens.
- Configure an API Gateway HTTP API JWT Authorizer with issuer and audience.
- Attach authorization scopes to individual routes.
- Verify the API rejects requests lacking tokens or sufficient permissions.
- Read verified claims inside a Lambda integration.
- Understand limitations of JWT revocation when API Gateway validates tokens offline.

## 2. Lab Architecture

~~~mermaid
flowchart LR
    U[Browser / local PKCE client] -->|1. Authorization Code + PKCE| C[Cognito Managed Login]
    C -->|2. ID / Access / Refresh tokens| U
    U -->|3. Bearer access token| A[API Gateway HTTP API]
    A -->|4. JWT validation + scope check| J[JWT Authorizer]
    J -->|5. Verified claims| L[Lambda integration]
    L -->|6. JSON response| U
    C --- P[User Pool / App Client / Resource Server]
    J --- K[Issuer JWKS public keys]
~~~

Role of each component:

| Component | Role |
|---|---|
| Cognito User Pool | Manages users, sign-in, identity verification, and JWT issuance |
| App client | Represents an application; configures OAuth flows, callback URLs, and scopes |
| Resource server | Defines custom scopes protecting the API |
| Managed login domain | Hosts the sign-in page and OAuth endpoints |
| PKCE client | Generates code verifier/challenge, receives authorization code, and exchanges it for tokens |
| API Gateway HTTP API | Receives requests and invokes the JWT Authorizer |
| JWT Authorizer | Validates signature, issuer, audience/client ID, expiration, and scopes |
| Lambda | Executes business logic after the request is accepted by the authorizer |

This lab uses an HTTP API JWT Authorizer. API Gateway REST API also supports Cognito User Pool Authorizers, but configuration and token selection differ; do not apply HTTP API steps verbatim to REST APIs.

## 3. Distinguishing Authentication and Authorization

Authentication answers "who is the user?". Cognito User Pool verifies login credentials or an identity provider and issues tokens.

Authorization answers "what is the user allowed to do?". API Gateway checks the token and scopes before forwarding requests to the backend.

Example:

- The user signs in successfully: authentication is complete.
- The user has scope `orders/read`: allowed to call `GET /orders`.
- The user lacks scope `orders/write`: not allowed to call `POST /orders`.

Signing in successfully does not mean a user is authorized to call every API.

## 4. How User Pools and Identity Pools Differ

| Service | Purpose | Typical Output |
|---|---|---|
| Cognito User Pool | User directory and authentication; supports OAuth/OIDC and federation | ID token, access token, refresh token |
| Cognito Identity Pool | Exchanges identities for temporary AWS credentials | AWS credentials via STS to access AWS services |

This lab uses a User Pool because the API needs to verify identity and permissions via JWTs. An Identity Pool is unnecessary when Lambda/the backend is the only component accessing AWS resources on the user's behalf.

## 5. ID Token, Access Token, and Refresh Token

Cognito issues three main token types:

| Token | Purpose | Data / Capabilities |
|---|---|---|
| ID token | Proves the user signed in and provides identity claims | `sub`, `email`, and readable profile claims |
| Access token | Proves authorization to access resources/APIs | `scope`, `client_id`, `token_use=access`, and related claims |
| Refresh token | Obtains new access and ID tokens when current ones expire | Never sent to API resource servers |

For APIs, use the access token. The ID token is meant for clients to know the user's identity; never use an ID token instead of an access token when a route requires authorization scopes.

API Gateway JWT Authorizer does not automatically infer whether a token is an access token or an ID token purely from its JWT format. AWS recommends configuring authorization scopes on routes to require tokens to carry the scope expected by the API. This is why the lab creates custom scopes and attaches them to routes.

## 6. Prerequisites and Resources

You need:

- An AWS account with permissions to create a Cognito User Pool, API Gateway HTTP API, Lambda, and IAM role.
- AWS CLI v2 if you want to run optional verification commands.
- Node.js 18 or later to run the local PKCE callback script.
- PowerShell 5.1 or later, or a shell able to send HTTP form requests.
- A browser to sign in through Cognito Managed Login.

Select a single Region for the User Pool, API Gateway, and Lambda, such as `ap-southeast-1`. Note the selected Region because the Region in the issuer URL must match the User Pool's Region.

Use test accounts and synthetic data. Never put production passwords, client secrets, authorization codes, access tokens, or refresh tokens in source control, tickets, or public logs.

## 7. Creating the Cognito User Pool

1. Open the Amazon Cognito console.
2. Select User Pools and create a new user pool.
3. Choose sign-in options with email or username/email per lab needs.
4. Enable email verification if using email as the sign-in identifier.
5. Choose an appropriate password policy configuration.
6. Create the User Pool and record the User Pool ID.

The User Pool ID has the format:

~~~text
ap-southeast-1_AbCdEf123
~~~

Do not use the User Pool ID as the app client ID. These are two distinct identifiers used in different places for issuer and audience.

## 8. Creating a Resource Server and Custom Scopes

A resource server represents the API that access tokens protect. Inside the User Pool:

1. Open Domain or Resource servers in the User Pool configuration.
2. Choose Create resource server.
3. Set display name: `Orders API`.
4. Set identifier: `https://api.example.com`
5. Create custom scope `orders.read` with description "Read orders list".
6. Create custom scope `orders.write` with description "Create or update orders".

The full scopes look like:

~~~text
https://api.example.com/orders.read
https://api.example.com/orders.write
~~~

Amazon Cognito joins the resource server identifier and scope name with a slash. The identifier can be a short name or URL; using a URL makes it clear which API the scope belongs to, though it makes tokens slightly longer.

Scopes are permissions requested by applications and enforced by APIs. Name scopes by action or resource, avoiding generic names like `admin` when an API can split read and write permissions.

## 9. Creating a Public App Client for the Web App

Create a dedicated app client for the test application:

1. Open App clients in the User Pool.
2. Create an app client of type Single-page application or public client.
3. Do not generate a client secret because browser/mobile apps have no trustworthy place to keep a static secret.
4. Enable OAuth 2.0 authorization code grant.
5. Do not enable implicit grant for this lab.
6. Add callback URL: `http://localhost:3000/callback`
7. Add sign-out URL: `http://localhost:3000/`
8. Select identity provider Cognito User Pool.
9. Allow OIDC scopes `openid`, `email`, and `profile`.
10. Allow custom scopes `https://api.example.com/orders.read` and `https://api.example.com/orders.write`.
11. Save the configuration and record the App client ID.

Cognito allows HTTP callback URLs only with `localhost` for testing purposes. In production deployments, use HTTPS and exact registered callback URLs.

The App client ID is a long alphanumeric string. This is the value used as the JWT authorizer audience in this lab.

## 10. Configuring the Managed Login Domain

The OAuth authorization code flow requires a User Pool domain.

1. Open Domain in the User Pool.
2. Choose a Cognito domain or custom domain per requirements.
3. For the lab, choose Cognito domain and enter a prefix unique within the Region.
4. Choose the Managed login configuration.
5. Save the domain.

The domain has the form:

~~~text
https://<domain-prefix>.auth.<region>.amazoncognito.com
~~~

For example, with domain-prefix `lab-orders-abc123` and Region `ap-southeast-1`:

~~~text
https://lab-orders-abc123.auth.ap-southeast-1.amazoncognito.com
~~~

Record the domain prefix/host. OAuth endpoints used in this lab:

~~~text
/oauth2/authorize
/oauth2/token
/oauth2/revoke
~~~

## 11. Creating a Test User

You can create a user via the Cognito console or allow self sign-up on Managed Login.

For manual creation:

1. Open Users in the User Pool.
2. Choose Create user.
3. Enter a dedicated lab email address.
4. Verify the email per configuration.
5. Set a test password or complete the temporary password change step.
6. Verify the user is in a sign-in-ready state.

If the User Pool requires email verification, complete verification before running the authorization flow. Never use someone else's real email address.

## 12. Creating the Lambda Backend

In the Lambda console:

1. Create a function named `orders-api-lab`.
2. Choose runtime Python 3.12 or a Python runtime supported in your Region.
3. Create an execution role with `AWSLambdaBasicExecutionRole` to write CloudWatch Logs.
4. Paste the following handler into `index.py` or the handler file expected by the runtime.
5. Deploy the function.

~~~python
import json


def handler(event, context):
    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {})
    jwt = authorizer.get("jwt", {})
    claims = jwt.get("claims", {})
    scopes = jwt.get("scopes", [])

    body = {
        "message": "Request accepted by Cognito JWT Authorizer",
        "method": request_context.get("http", {}).get("method"),
        "path": event.get("rawPath"),
        "subject": claims.get("sub"),
        "username": claims.get("username"),
        "token_use": claims.get("token_use"),
        "scopes": scopes
    }

    return {
        "statusCode": 200,
        "headers": {
            "content-type": "application/json",
            "cache-control": "no-store"
        },
        "body": json.dumps(body)
    }
~~~

The handler returns select claims purely for learning purposes. Never return access tokens, refresh tokens, full sensitive claims, or internal user details in production responses.

API Gateway passes verified JWT claims to Lambda at:

~~~text
event.requestContext.authorizer.jwt.claims
~~~

The scopes list can be read from:

~~~text
event.requestContext.authorizer.jwt.scopes
~~~

Lambda does not need to parse or verify token signatures itself in this lab because API Gateway performs that validation before invoking the integration.

## 13. Creating the API Gateway HTTP API

1. Open the API Gateway console.
2. Choose Create API.
3. Choose HTTP API.
4. Create a Lambda integration pointing to `orders-api-lab`.
   - If the console asks for Payload format version, choose `2.0` because the handler reads `requestContext.http.method`, `rawPath`, and `requestContext.authorizer.jwt`.
5. Name the API, for example `orders-http-api`.
6. Create route `GET /orders`.
7. Attach the Lambda integration to the route.
8. Create a stage, for example `$default`, and enable auto-deploy.
9. Record the Invoke URL.

The Invoke URL typically looks like:

~~~text
https://<api-id>.execute-api.<region>.amazonaws.com
~~~

Complete route:

~~~text
GET https://<api-id>.execute-api.<region>.amazonaws.com/orders
~~~

If using a custom domain or named stage, use the corresponding Invoke URL. HTTP APIs with the `$default` stage generally do not require a stage segment in the URL.

## 14. Creating a JWT Authorizer for HTTP API

In API Gateway:

1. Open the newly created API.
2. Select Authorization.
3. Choose Manage authorizers and then Create.
4. Select Authorizer type `JWT`.
5. Name it `CognitoUserPoolJwt`.
6. Identity source: `$request.header.Authorization`.
7. Issuer URL:

~~~text
https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
~~~

8. Audience: the App client ID of the public app client.
9. Create the authorizer.

The issuer must match the `iss` claim in the JWT exactly. For example:

~~~text
https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_AbCdEf123
~~~

The audience in this lab is the App client ID. For standard Cognito access tokens, the `client_id` claim is checked when the token lacks `aud`. API Gateway checks `aud` if present; only when `aud` is absent does it check `client_id`. If you enable resource binding causing access tokens to include `aud`, configure the audience to match the corresponding resource URI.

## 15. Attaching the Authorizer and Scope to the Route

1. Open Routes.
2. Select `GET /orders`.
3. Select Authorization type `JWT`.
4. Select authorizer `CognitoUserPoolJwt`.
5. Add authorization scope:

~~~text
https://api.example.com/orders.read
~~~

6. Save changes and deploy if auto-deploy is disabled on the stage.

If you later create `POST /orders`, attach scope:

~~~text
https://api.example.com/orders.write
~~~

When a route has authorization scopes, API Gateway requires the token to contain at least one scope in the route's list. If a route requires multiple permissions simultaneously using AND logic, do not simply list multiple scopes assuming API Gateway enforces all of them; perform additional checks in the backend or design an appropriate policy.

## 16. Creating the PKCE Verifier and Local Callback Server

To obtain custom scopes, use Cognito's OAuth authorization endpoint. Do not use `InitiateAuth` for this step: `InitiateAuth`/`AdminInitiateAuth` only issue the `aws.cognito.signin.user.admin` scope, not custom resource-server scopes.

Create `pkce-login.mjs` on your development machine:

~~~javascript
import { createServer } from "node:http";
import { randomBytes, createHash } from "node:crypto";

const domain = process.env.COGNITO_DOMAIN;
const clientId = process.env.COGNITO_CLIENT_ID;
const redirectUri = "http://localhost:3000/callback";
const defaultScopes =
  "openid email profile https://api.example.com/orders.read";
const scopes = process.env.OAUTH_SCOPES || defaultScopes;

if (!domain || !clientId) {
  throw new Error("Set COGNITO_DOMAIN and COGNITO_CLIENT_ID first.");
}

const base64url = (value) => value.toString("base64url");
const verifier = base64url(randomBytes(32));
const challenge = base64url(
  createHash("sha256").update(verifier).digest()
);
const state = base64url(randomBytes(24));

const params = new URLSearchParams({
  response_type: "code",
  client_id: clientId,
  redirect_uri: redirectUri,
  scope: scopes,
  code_challenge: challenge,
  code_challenge_method: "S256",
  state
});

const authorizeUrl =
  "https://" + domain + "/oauth2/authorize?" + params.toString();

const server = createServer((request, response) => {
  const callbackUrl = new URL(request.url, redirectUri);

  if (callbackUrl.pathname !== "/callback") {
    response.writeHead(404);
    response.end("Not found");
    return;
  }

  const returnedState = callbackUrl.searchParams.get("state");
  const code = callbackUrl.searchParams.get("code");
  const oauthError = callbackUrl.searchParams.get("error");

  if (returnedState !== state) {
    response.writeHead(400);
    response.end("State mismatch. Reject this response.");
    server.close();
    return;
  }

  if (oauthError || !code) {
    response.writeHead(400);
    response.end("Authorization failed: " + (oauthError || "missing code"));
    console.error("OAuth error:", oauthError);
    server.close();
    return;
  }

  response.writeHead(200, { "content-type": "text/plain; charset=utf-8" });
  response.end("Sign-in completed. Return to the terminal.");

  console.log("AUTH_CODE=" + code);
  console.log("CODE_VERIFIER=" + verifier);
  console.log("STATE_VALID=true");
  server.close();
});

server.listen(3000, () => {
  console.log("Open this URL in your browser:\n");
  console.log(authorizeUrl);
  console.log("\nWaiting for Cognito callback on localhost:3000...");
});
~~~

The script generates a random code verifier, computes its SHA-256 code challenge, creates an anti-CSRF state value, and listens for the callback on the localhost loopback. The code verifier is used only when exchanging the authorization code.

## 17. Running PKCE Login

Open PowerShell in the directory containing `pkce-login.mjs` and set environment variables:

~~~powershell
$env:COGNITO_DOMAIN = "<domain-prefix>.auth.<region>.amazoncognito.com"
$env:COGNITO_CLIENT_ID = "<app-client-id>"
$env:OAUTH_SCOPES = "openid email profile https://api.example.com/orders.read"
node .\pkce-login.mjs
~~~

The script prints the authorization URL. Open the URL in a browser, sign in with the test user, and consent if prompted by Managed Login. After sign-in, Cognito redirects to `localhost:3000/callback`. The terminal prints `AUTH_CODE` and `CODE_VERIFIER`.

Do not share the authorization code or verifier. The authorization code is single-use, and the verifier must be kept secret until the token exchange completes.

## 18. Exchanging the Authorization Code for Tokens

In the same PowerShell session, enter the code and verifier you received:

~~~powershell
$authorizationCode = Read-Host "Paste AUTH_CODE"
$codeVerifier = Read-Host "Paste CODE_VERIFIER"
$redirectUri = "http://localhost:3000/callback"
$tokenEndpoint = "https://$env:COGNITO_DOMAIN/oauth2/token"

$tokenRequest = @{
  Method = "Post"
  Uri = $tokenEndpoint
  ContentType = "application/x-www-form-urlencoded"
  Body = @{
    grant_type = "authorization_code"
    client_id = $env:COGNITO_CLIENT_ID
    code = $authorizationCode
    redirect_uri = $redirectUri
    code_verifier = $codeVerifier
  }
}

$tokenResponse = Invoke-RestMethod @tokenRequest

if (-not $tokenResponse.access_token) {
  throw "Cognito did not return an access token."
}

Write-Host "Access token received. Expires in $($tokenResponse.expires_in) seconds."
Write-Host "Token type: $($tokenResponse.token_type)"
~~~

`redirect_uri` in the token request must match `redirect_uri` in the authorization request verbatim. Cognito issues tokens only when `code_verifier` hashes to the original `code_challenge`. Public app clients do not send a client secret.

The token response typically includes `access_token`, `id_token`, `refresh_token`, `expires_in`, and `token_type`. Keep tokens in variables or appropriate secure storage; do not print tokens to terminal history or shared logs.

## 19. Calling the API with the Access Token

Set the API URL based on the Invoke URL and configured route:

~~~powershell
$apiUrl = "https://<api-id>.execute-api.<region>.amazonaws.com/orders"
$apiRequest = @{
  Method = "Get"
  Uri = $apiUrl
  Headers = @{
    Authorization = "Bearer $($tokenResponse.access_token)"
  }
}
$apiResponse = Invoke-RestMethod @apiRequest
$apiResponse | ConvertTo-Json -Depth 5
~~~

A successful response looks like:

~~~json
{
  "message": "Request accepted by Cognito JWT Authorizer",
  "method": "GET",
  "path": "/orders",
  "subject": "a1b2c3d4-example",
  "username": "lab-user",
  "token_use": "access",
  "scopes": [
    "openid",
    "email",
    "profile",
    "https://api.example.com/orders.read"
  ]
}
~~~

`subject`, `username`, and `scopes` values will vary based on the actual user and token. API Gateway validated the token before Lambda was invoked.

## 20. Testing a Request Without a Token

Send a request without an `Authorization` header:

~~~powershell
try {
  Invoke-WebRequest -Method Get -Uri $apiUrl
} catch {
  Write-Host "HTTP status:" $_.Exception.Response.StatusCode.value__
}
~~~

Expected result is `401 Unauthorized` because the JWT Authorizer received no valid token.

## 21. Testing an Access Token Missing the Required Scope

Rerun `pkce-login.mjs` requesting only OIDC scopes:

~~~powershell
$env:OAUTH_SCOPES = "openid email profile"
node .\pkce-login.mjs
~~~

Sign in and exchange the authorization code for tokens as before. The new access token lacks the custom scope `orders.read`. Call `GET /orders` with this access token.

Expected result is `403 Forbidden` or the corresponding authorization error because the token has a valid signature/issuer but lacks the scope required by the route.

This test demonstrates that authentication and authorization are two independent steps.

## 22. Testing an ID Token

Try calling the API with the ID token instead of the access token:

~~~powershell
$idTokenRequest = @{
  Method = "Get"
  Uri = $apiUrl
  Headers = @{
    Authorization = "Bearer $($tokenResponse.id_token)"
  }
}
Invoke-WebRequest @idTokenRequest
~~~

The route requires custom scope `orders.read`. The ID token does not carry that custom API scope, so the request must be rejected during scope authorization. This is why authorization scopes should be attached to routes.

If a route configures no authorization scopes, the JWT Authorizer may accept another valid JWT with matching issuer/audience, including an ID token if claims match. Never omit scope requirements on API routes merely because the JWT signature is valid.

## 23. Testing Wrong Issuer, Audience, or Expired Tokens

Try the following scenarios in the lab environment:

- Send a token from a different User Pool.
- Use a token from a different app client.
- Modify a single character in the token to invalidate the signature.
- Use an expired token.
- Use a token without the custom scope.

Results:

| Scenario | Expected Result |
|---|---|
| No token | 401 |
| Invalid signature | 401 |
| Wrong issuer | 401 |
| Wrong audience/client ID | 401 |
| Expired token | 401 |
| Valid token missing scope | 403 |
| Valid token with right scope | 2xx from integration |

Specific HTTP status codes may include different response bodies depending on API Gateway and route configuration. Inspect the `WWW-Authenticate` header and CloudWatch logs when troubleshooting.

## 24. How API Gateway Validates a JWT

The HTTP API JWT Authorizer performs these main steps:

1. Reads the token from the identity source, which in this lab is the `Authorization` header.
2. Decodes the JWT to inspect header and claims.
3. Finds the public key matching `kid` in the issuer's JWKS.
4. Verifies the algorithm and signature.
5. Verifies `iss` matches the configured issuer.
6. Verifies `aud` or `client_id` matches the audience.
7. Verifies `exp`, `nbf`, and `iat`.
8. If the route requires scopes, verifies the token contains at least one required scope.
9. Only upon passing all checks forwards claims to the integration.

For Cognito User Pools, the issuer typically looks like:

~~~text
https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
~~~

The JWKS endpoint is published via the OpenID Connect discovery document. API Gateway fetches public keys to verify tokens; the application does not need to download private keys or sign tokens itself.

## 25. Inspecting JWT Claims Safely

A JWT has three parts separated by dots:

~~~text
header.payload.signature
~~~

The header typically contains `alg` and `kid`. The payload holds claims such as `iss`, `sub`, `exp`, `iat`, `token_use`, `client_id`, and `scope`. The signature proves the token was signed by the corresponding private key.

Decoding the payload only lets you read its contents; it does not verify the signature. Never trust claims simply because decoding succeeded. Only the API Gateway Authorizer or a JWT library that checks signature, issuer, audience, and expiration provides verified claims.

Never paste production tokens into public JWT debugging websites. A bearer token can allow others to make requests on a user's behalf until it expires or is blocked by a system checking revocation state.

## 26. Configuring Multiple Routes by Permission

As the API grows, split routes by action:

| Route | Scope | Meaning |
|---|---|---|
| `GET /orders` | `https://api.example.com/orders.read` | View orders |
| `GET /orders/{id}` | `https://api.example.com/orders.read` | View details |
| `POST /orders` | `https://api.example.com/orders.write` | Create order |
| `PATCH /orders/{id}` | `https://api.example.com/orders.write` | Update order |

Each route can share the same JWT Authorizer while specifying distinct authorization scopes. An access token carrying both read and write scopes can invoke both route groups; a read-only token cannot call write routes.

Never use scopes as a substitute for resource-level authorization. For example, a user holding `orders.read` should still only see orders belonging to their tenant; the Lambda/service layer must still check `tenantId` or ownership against verified identity data.

## 27. Protecting Lambda and the Backend

The JWT Authorizer blocks invalid requests before Lambda runs, yet the backend still must:

- Enforce tenant, ownership, and business rules.
- Never trust client-sent headers to identify users if those headers are not generated/controlled by the gateway.
- Read identity claims strictly from `requestContext.authorizer.jwt`.
- Use a least-privilege IAM execution role for Lambda.
- Restrict Lambda invoke permissions to the exact API Gateway source ARN.
- Never return stack traces, secrets, or internal exception messages to clients.
- Log correlation/request IDs for investigation.
- Protect databases with appropriate IAM, secret rotation, and network isolation.

If the backend can be invoked directly outside API Gateway, add protection controls on that invocation path too. Do not assume every request reaching Lambda passed through the JWT Authorizer.

## 28. Token Expiration, Refresh, and Revocation

Access tokens have shorter lifetimes than refresh tokens. When an access token expires, the application can use the refresh token to obtain new tokens per the app client configuration.

Key points:

- Set access token lifetime based on risk posture and application UX.
- Store refresh tokens in secure storage; never put them in URLs or logs.
- Enable token revocation on the app client; newer app clients enable it by default.
- Use `RevokeToken`, the revoke endpoint, `GlobalSignOut`, or `AdminUserGlobalSignOut` as needed.
- Clear tokens from client storage on logout.

Important limitation: JWTs are self-contained. A token revoked in Cognito can still pass an offline validator that only checks signature and expiration. The API Gateway JWT Authorizer verifies JWTs using issuer keys and claims; it does not query Cognito to check revocation status on every request. Therefore, revocation may not immediately block an unexpired access token at API Gateway.

If near-instant revocation is required, consider short access token lifetimes, a backend-checked denylist/session state, or a custom authorizer that checks session status. Weigh the trade-offs in latency, cost, and complexity.

## 29. CORS for Browser-Based Applications

This lab calls the API from PowerShell, so CORS is not needed. When a JavaScript frontend runs from a different origin, configure CORS on the HTTP API:

- Allowed origins: only the actual frontend domains.
- Allowed methods: `GET`/`POST`/`PATCH` per routes.
- Allowed headers: `Authorization` and `Content-Type`.
- Expose headers if the frontend needs to read response headers.

Do not use wildcard origins for applications handling credentials or sensitive data without clear justification. CORS is not an authentication/authorization mechanism; it is solely a browser policy controlling whether JavaScript can read cross-origin responses.

## 30. Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `redirect_mismatch` | Callback URL mismatches app client configuration | Compare `redirect_uri` character by character in authorize and token requests |
| `invalid_grant` | Authorization code expired/already used or wrong PKCE verifier | Start a fresh flow and exchange the code once with the right verifier |
| `invalid_client` | Wrong client ID or app client requires a secret | Use a public client without a secret for the PKCE browser flow |
| `unauthorized_client` | Authorization code grant not enabled | Enable authorization code grant in the app client |
| `401 Unauthorized` | Invalid issuer, audience, signature, or expiration | Decode claims to inspect, then verify issuer/audience and JWKS |
| `403 Forbidden` | Valid token but missing custom scope | Request the right scope in the authorize URL and enable it on the app client |
| Token lacks custom scope | Scope not enabled on app client or `InitiateAuth` was used | Enable the custom scope and use the OAuth authorization endpoint |
| Lambda not invoked | JWT Authorizer rejected request or route lacks integration | Check authorizer, route, and execution logs |
| Lambda returns `500` | Handler bug or Lambda execution role lacks permissions | Inspect CloudWatch Logs and function configuration |
| API returns `502` | API Gateway cannot invoke Lambda or invalid response format | Check Lambda permissions, integration, and payload format |
| Domain unreachable | Domain provisioning incomplete or wrong hostname | Check domain status and Region |
| State mismatch | Callback does not match the newly initiated login flow | Reject response and restart the PKCE flow |

When the API returns `401`, inspect the `WWW-Authenticate` header to see whether the token missed audience, had the wrong issuer, or was invalid. Never paste raw access tokens into tickets for debugging.

## 31. Verifying Lab Results

- [ ] User Pool created with a recorded User Pool ID.
- [ ] Resource server has custom scopes `orders.read` and `orders.write`.
- [ ] Public app client has no client secret.
- [ ] Authorization code grant and PKCE are configured.
- [ ] Localhost callback URL is registered accurately.
- [ ] Managed login domain is operational.
- [ ] Test user signed in successfully.
- [ ] Lambda backend returns verified claims.
- [ ] HTTP API JWT Authorizer has the exact issuer and audience.
- [ ] `GET /orders` requires `orders.read`.
- [ ] Request without a token returns 401.
- [ ] Token missing the required scope is rejected.
- [ ] Access token with the right scope calls the API successfully.
- [ ] ID token cannot be used in place of an access token for scoped routes.
- [ ] No tokens or secrets appear in logs or source control.

## 32. Resource Cleanup

After finishing:

1. Delete the API Gateway HTTP API.
2. Delete the Lambda function `orders-api-lab`.
3. Delete the User Pool domain if no longer reused.
4. Delete the test User Pool and app client.
5. Delete the IAM role created exclusively for the lab Lambda if no other functions use it.
6. Check CloudWatch log groups and delete lab logs if retention is unnecessary.

Never delete User Pools, IAM roles, or APIs used by other applications. Verify resource names and owners before deleting.

## 33. Extending Beyond the Lab

Once the basic flow works, you can extend it:

- Add `POST /orders` protected by `orders.write`.
- Add group/tenant claims and enforce resource-level authorization.
- Connect external identity providers such as Google or enterprise OIDC.
- Use a custom domain and HTTPS callback for the frontend.
- Adopt AWS Verified Permissions when complex policy-based authorization is needed.
- Use a Lambda authorizer when custom claim validation or session state checks are needed.
- Add CloudWatch alarms, access logs, and tracing.
- Add rate limiting, WAF, and abuse protection for public APIs.

## 34. Key Takeaways

Cognito User Pools authenticate users and issue ID/access/refresh tokens. Resource servers define custom scopes inside access tokens. Public app clients should use Authorization Code Grant with PKCE and never keep a client secret in browser/mobile apps.

API Gateway HTTP API JWT Authorizers check signature, issuer, audience/client ID, expiration, and scopes before invoking the backend. Attaching authorization scopes to routes distinguishes tokens authorized for API access from JWTs that merely prove a user signed in. Lambda continues enforcing ownership, tenant isolation, and business rules.

JWT revocation does not guarantee every offline API validator learns immediately that a token was revoked. Choose access token lifetimes and session validation mechanisms aligned with security requirements. Always keep tokens out of logs, URLs, and source control.

## References

- [Using PKCE in Authorization Code Grants - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/using-pkce-in-authorization-code.html)
- [Application-specific Settings with App Clients - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-client-apps.html)
- [Scopes, M2M, and Resource Servers - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html)
- [OAuth 2.0 Grants - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/federation-endpoints-oauth-grants.html)
- [Understanding User Pool JSON Web Tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html)
- [Verifying JSON Web Tokens - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html)
- [Control Access to HTTP APIs with JWT Authorizers - API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)
- [Troubleshoot HTTP API JWT Authorizers](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-troubleshooting-jwt.html)
- [Create an HTTP API - API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api.html)
- [Create Lambda Proxy Integrations for HTTP APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html)
- [Ending User Sessions with Token Revocation - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html)
- [Control Access to REST APIs with Cognito User Pools](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-integrate-with-cognito.html)

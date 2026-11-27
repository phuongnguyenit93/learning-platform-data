# invalid_scope, unauthorized_client, and unsupported_grant_type

The three errors `invalid_scope`, `unauthorized_client`, and `unsupported_grant_type` commonly appear when a client sends an authorization request or token request that does not conform to the registered policy on Spring Authorization Server. They may all return HTTP 400, yet they point to three distinct issues: the requested permissions are invalid, the client is not allowed to use that grant type, or the server does not support the grant type sent to the token endpoint.

This lesson belongs to the `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER` module, focusing on designing and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Authorization Server. Diagnosis requires looking at the endpoint, request type, `RegisteredClient`, scopes, grant types, and authorization/consent state. You should not fix the error by broadening the client's permissions before identifying which condition is being violated.

## 1. Distinguishing the Three Errors Under the OAuth2 Contract

| Error code | Meaning | First Diagnostic Question |
|---|---|---|
| `invalid_scope` | The requested scope is invalid, unsupported, or exceeds what the client is permitted to request | Is this scope registered and permitted in the current request/grant? |
| `unauthorized_client` | The client has been identified, but is not permitted to use the requested grant type or response type | Is this grant type in the client's `authorizationGrantTypes` list? |
| `unsupported_grant_type` | The token endpoint does not support the submitted `grant_type` value | Did the request send the right standard grant type and has the server registered a provider for that grant? |

These three errors differ from other common errors:

- `invalid_client`: client authentication failed, for example wrong client secret, wrong authentication method, or unrecognized client.
- `invalid_grant`: the grant credential is invalid, for example an expired/already-used authorization code, mismatched redirect URI, or invalid refresh token.
- `invalid_request`: missing required parameter, duplicate parameter, or malformed request.
- `access_denied`: the user or authorization policy denied access.

At the token endpoint, the three errors in this lesson are typically returned as an OAuth2 error response with HTTP 400. `invalid_client` has its own status code rules depending on the client authentication method; therefore, do not diagnose solely from the status code. Read the `error` field in the response body.

## 2. Identifying Which Endpoint Produced the Error

Spring Authorization Server typically has two endpoints to distinguish:

| Endpoint | Flow-Determining Parameters | Role |
|---|---|---|
| `/oauth2/authorize` | `response_type`, `client_id`, `scope`, `redirect_uri` | Starts the authorization flow, validates the request, and may require login/consent |
| `/oauth2/token` | `grant_type`, `client_id`, `scope`, grant credential | Exchanges an authorization code, refreshes a token, or issues a token under a registered grant |

`response_type=code` is a parameter of the authorization endpoint. `grant_type=authorization_code` is a parameter of the token endpoint when exchanging a code. Sending `response_type` to the token endpoint or sending `grant_type` instead of `response_type` at the authorization endpoint does not form a valid request.

Before investigating configuration, record at minimum:

1. The receiving endpoint and HTTP method.
2. The actual `grant_type` or `response_type` value after form decoding.
3. The client ID masked or replaced by a safe identifier in logs.
4. The requested scopes and scopes registered for the client.
5. The error code, sanitized error description, and correlation ID.

Do not log client secrets, authorization codes, access tokens, refresh tokens, PKCE verifiers, or the full Authorization header. Those values are unnecessary for diagnosing these three errors.

## 3. Diagnosing `invalid_scope`

`invalid_scope` means the set of scopes in the request is not accepted by the authorization server's policy. Scopes are case-sensitive strings; having a scope in the client registration does not mean every grant or every user is automatically granted that scope.

### 3.1. Checking Registered Scopes for the Client

Spring Authorization Server stores allowed scopes in `RegisteredClient`. Example of a service client registered with two scopes:

```java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.client.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient ordersClient = RegisteredClient.withId("orders-client-row")
        .clientId("orders-service")
        .clientSecret(passwordEncoder.encode("test-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .scope("orders.write")
        .build();
```

With this registration, `orders.read` and `orders.write` are the two scopes the client can request subject to the grant and additional policies. If the client sends `orders.admin`, the authorization server can return `invalid_scope` because that scope is not registered or not allowed.

Read the actual registration from the exact repository the application uses:

```java
import java.util.Set;

RegisteredClient client = registeredClientRepository.findByClientId("orders-service");

if (client == null) {
    throw new IllegalStateException("Client registration was not found");
}

Set<String> registeredScopes = client.getScopes();
```

If registrations are stored via JDBC, inspect the data through `JdbcRegisteredClientRepository` or an authorized database administration tool. Do not inspect only config files or seed data: the registration may have been updated in the database while a cache or another node still uses an older copy.

### 3.2. Checking How the Scope Parameter Is Passed

OAuth2 passes scopes as a space-delimited list of scope tokens. For example:

```text
scope=orders.read%20orders.write
```

Do not pass a comma-separated list (`orders.read,orders.write`) unless the application has a custom protocol convention. When sending `application/x-www-form-urlencoded`, spaces must be properly encoded. Scope names must also match the registered values exactly; `Orders.Read` differs from `orders.read`.

Example client credentials request:

```bash
curl --user orders-service:test-secret \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=orders.read" \
  https://auth.example.com/oauth2/token
```

Try changing the scope to `orders.admin` to confirm the negative test returns `invalid_scope`. In real environments, use a securely managed test secret; do not place production secrets directly in shell history or documentation.

### 3.3. Distinguishing Client Scopes from User Consent

In the Authorization Code flow, a client may request registered scopes, yet the user must still consent if policy requires it. Consent answers which permissions the user has approved; `RegisteredClient.getScopes()` answers which permissions the client is permitted to request. These two conditions are distinct.

If a scope is not in the registration, adding the scope to existing consent will not make the request valid. If the scope is registered but consent is not yet recorded, the server may redirect the user to the consent page or deny the request according to application policy. Determine whether the request failed at registration validation or at the consent step.

Check consent for the exact client-and-principal pair. Consent from user A cannot be used to infer that user B has approved the same permissions. When tests share a database, clean up prior consents to avoid order-dependent test results.

### 3.4. Checking Scopes Against Grant and Application Policy

A scope may be registered for a client yet still restricted by grant type, tenant, resource, user, or custom policy. For instance, a service client may only receive `orders.read` via client credentials, while `orders.write` requires a user-involved flow with consent. In that case, do not broaden the global scope list just to make a service request succeed.

If the application uses an `OAuth2TokenCustomizer`, custom authorization consent, or custom provider, check whether that logic filters scopes or alters claims after the grant is validated. Scopes in the access token and authorities mapped by the resource server must also be checked separately.

A successful token endpoint request followed by `403 Forbidden` when calling an API is usually a resource server authorization issue, not a token endpoint `invalid_scope`. Check whether the token contains the expected scope/authority and whether the resource server maps them into `SCOPE_...` or custom authorities properly.

## 4. Diagnosing `unauthorized_client`

`unauthorized_client` usually indicates that the client was identified, but is not allowed to use the requested grant type or response type. Check `RegisteredClient`'s `authorizationGrantTypes` before inspecting token providers or credentials.

### 4.1. Unregistered Grant Type

Example of a client permitted to use only client credentials:

```java
RegisteredClient serviceClient = RegisteredClient.withId("service-client-row")
        .clientId("billing-service")
        .clientSecret(passwordEncoder.encode("test-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("billing.read")
        .build();
```

This client is not permitted to perform an Authorization Code grant or Refresh Token grant merely because the token endpoint supports those grants. If it sends `grant_type=authorization_code` or `grant_type=refresh_token`, the server can return `unauthorized_client` when the grant is recognized but not registered for that client.

If business requirements need Authorization Code and Refresh Token, the registration must declare both:

```java
RegisteredClient webClient = RegisteredClient.withId("web-client-row")
        .clientId("web-portal")
        .clientSecret(passwordEncoder.encode("test-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://portal.example.com/login/oauth2/code/portal")
        .scope("openid")
        .scope("profile")
        .build();
```

Public clients using PKCE typically register `ClientAuthenticationMethod.NONE` and have no client secret. Confidential clients must use a client authentication method matching the registration. Do not change the authentication method to fix a grant type error; client authentication failures are usually reported as `invalid_client`.

### 4.2. Checking the Authorization Request and Response Type

At `/oauth2/authorize`, `response_type=code` requires the Authorization Code flow. If the client is not configured to use authorization code, the server can return `unauthorized_client` or a context-appropriate protocol error.

Check:

- Does the client ID point to the right `RegisteredClient`?
- Does the registration include `AuthorizationGrantType.AUTHORIZATION_CODE`?
- Does the redirect URI match a registered URI exactly?
- Do client settings require PKCE or consent, and does the request satisfy them?
- Does the application customize the authorization endpoint/provider in a way that alters the decision?

Do not confuse `response_type=code` with `grant_type=authorization_code`. An authorization request begins with response type; grant type only appears when the client exchanges the code at the token endpoint.

### 4.3. Checking the Refresh Token Grant

A client using Authorization Code can be configured to receive refresh tokens. If the application wants the client to use refresh tokens, register `AuthorizationGrantType.REFRESH_TOKEN` and check refresh token issuance policies, such as the `offline_access` scope in OIDC when required by the application, consent, and `TokenSettings`.

If the client receives an access token but no refresh token, first determine whether the server has a policy to issue refresh tokens for that client/flow. Do not send `grant_type=refresh_token` under the assumption that every authorization code flow automatically issues a refresh token.

## 5. Diagnosing `unsupported_grant_type`

`unsupported_grant_type` indicates that the token endpoint does not support the submitted `grant_type` value. This error typically occurs before the server evaluates whether the client is allowed to use that grant.

### 5.1. Checking the Grant Type Name and Endpoint

Common standard values:

| Grant | `grant_type` Value |
|---|---|
| Authorization Code | `authorization_code` |
| Client Credentials | `client_credentials` |
| Refresh Token | `refresh_token` |
| Device Authorization Grant | `urn:ietf:params:oauth:grant-type:device_code` |
| Token Exchange | `urn:ietf:params:oauth:grant-type:token-exchange` |

Extension grants use URI identifiers per their respective specifications. Do not shorten them to `device_code` or `token_exchange` if the protocol requires the full URI.

Verify that the request sends the `grant_type` form parameter at `/oauth2/token`, not a misplaced query parameter or a JSON body unsupported by the endpoint. Confirm the exact token endpoint URL from discovery metadata instead of guessing the URL from habit.

### 5.2. Distinguishing an Unsupported Grant from an Unauthorized Grant

| Scenario | Usually Expected Error |
|---|---|
| `grant_type` is misspelled or the server has no converter/provider for it | `unsupported_grant_type` |
| Server supports `client_credentials`, but the current client does not have this grant registered | `unauthorized_client` |
| Client is allowed to use the grant, but grant credentials are missing/wrong | Usually `invalid_request` or `invalid_grant`, depending on parameter and grant type |
| Client authentication fails | `invalid_client` |

For example: if the server already has client credentials configured while the client only registered authorization code, add the grant type to the registration when business requirements allow. If the server has not implemented a custom grant, adding the grant to `RegisteredClient` alone is not enough; the token endpoint still needs a component to convert the request and a provider to handle the grant.

### 5.3. Checking a Custom Grant

Spring Authorization Server supports extending the token endpoint with an appropriate `AuthenticationConverter` and `AuthenticationProvider`. A custom grant requires:

1. Defining the grant type with a stable URI identifier.
2. Registering that grant type for each `RegisteredClient` permitted to use it.
3. Providing a converter to translate the HTTP request into the grant's `Authentication` object.
4. Providing a provider to authenticate the client, check permissions, validate grant data, and issue tokens.
5. Registering the converter/provider on the token endpoint of the right `SecurityFilterChain`.
6. Testing a valid grant, an unauthorized client, invalid grant data, and an unsupported grant type.

When adding a custom grant, verify that the converter recognizes the exact `grant_type` and that the provider is added to the token endpoint's provider list. Only adding `.authorizationGrantType(customGrantType)` to `RegisteredClient` without a converter/provider typically results in `unsupported_grant_type`.

Configuration DSL APIs and constructor signatures can vary across Spring Authorization Server versions. Follow the documentation for your installed dependency version when registering `accessTokenRequestConverter` and `authenticationProvider`; avoid copying examples from another version without checking.

## 6. Step-by-Step Investigation Workflow

Follow this order to separate protocol errors from registration errors:

1. **Identify the endpoint.** `/oauth2/authorize` or `/oauth2/token`? Check the method and content type.
2. **Read the error body.** Capture `error` and correlation ID; do not infer solely from the HTTP status.
3. **Authenticate the client.** Check client ID, authentication method, and credentials. If you get `invalid_client`, resolve this step first.
4. **Check the grant.** Read `RegisteredClient.getAuthorizationGrantTypes()` and compare with the `response_type`/`grant_type` being used.
5. **Check the scopes.** Compare requested scopes with `RegisteredClient.getScopes()` and custom policy/consent.
6. **Check the provider.** For standard grants, confirm the token endpoint supports it; for custom grants, confirm the converter and provider are registered.
7. **Check storage/cache.** Compare registrations across instances and check whether caches hold stale data.
8. **Re-run a minimal test.** Change only one condition at a time and verify the error code transitions as expected.

An example of a safe diagnostic log:

```text
event=oauth2_token_error
request_id=8f1c...
client_id=orders-service
grant_type=client_credentials
requested_scopes=[orders.read, orders.admin]
registered_grants=[client_credentials]
registered_scopes=[orders.read, orders.write]
oauth_error=invalid_scope
```

This is an illustrative log with credentials and tokens stripped. Do not log the entire form body or authentication headers.

## 7. Testing Errors with MockMvc

Token endpoint tests should run with a real `RegisteredClientRepository`, `OAuth2AuthorizationService`, security filter chain, and providers. You can use MockMvc to assert the returned error code.

Example of client credentials requesting an unregistered scope:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(post("/oauth2/token")
        .with(httpBasic("orders-service", "test-secret"))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "client_credentials")
        .param("scope", "orders.admin"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.error").value("invalid_scope"));
```

To test `unauthorized_client`, use a client that authenticates successfully but has not registered the submitted grant:

```java
mockMvc.perform(post("/oauth2/token")
        .with(httpBasic("billing-service", "test-secret"))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "refresh_token")
        .param("refresh_token", "test-refresh-token"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.error").value("unauthorized_client"));
```

This test requires the `billing-service` client to be registered and only allow `client_credentials`. Do not let client authentication fail, because then the test will only receive `invalid_client`.

To test `unsupported_grant_type`, send a grant type that the server does not support and has no corresponding converter/provider for:

```java
mockMvc.perform(post("/oauth2/token")
        .with(httpBasic("orders-service", "test-secret"))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "urn:example:params:oauth:grant-type:unknown"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.error").value("unsupported_grant_type"));
```

Every negative test should have a corresponding positive test: valid scopes are granted, the client uses a registered grant successfully, and supported standard/custom grants can complete. This proves the test fails for the exact condition being targeted.

## 8. Error Matrix and Remediation

| Symptom | Common Cause | Remediation |
|---|---|---|
| `invalid_scope` with client credentials | Scope is not in `RegisteredClient.getScopes()` | Register the scope if permitted or fix the request to a valid scope |
| `invalid_scope` even though scope is in seed file | Database or cache still holds an older registration | Read the actual registration from the repository and check every instance |
| `invalid_scope` in authorization request | Misspelled scope, unsupported scope, or exceeds policy | Check scope list, consent, and user/tenant policy |
| Token issued, but API returns 403 | Resource server lacks matching authority or scope was downscoped | Check the `scope` claim and authority mapping on the resource server |
| `unauthorized_client` when using authorization code | Client did not register `authorization_code` or response type is not allowed | Check grant types and client settings |
| `unauthorized_client` when refreshing | Client did not register `refresh_token` or refresh policy disallows it | Check registration, token issuance, and refresh policy |
| `unsupported_grant_type` with standard grant | Wrong `grant_type` value, wrong endpoint, or server config does not support it | Verify protocol value and discovery metadata |
| `unsupported_grant_type` with custom grant | Missing converter/provider or provider not registered on token endpoint | Check extension wiring and `SecurityFilterChain` |
| Error occurs on only one node | Inconsistent `RegisteredClient` config or cache across nodes | Synchronize config, cache invalidation, and shared repository |
| Cannot distinguish errors due to status 400 | Only checking HTTP status without reading OAuth2 error body | Assert `$.error` and record correlation ID |

## 9. Pre-Release Checklist

- [ ] Client ID and client authentication method are verified independently.
- [ ] `RegisteredClient.authorizationGrantTypes` contains only the grants the client actually needs.
- [ ] `RegisteredClient.scopes` accurately reflects the permissions the client is allowed to request.
- [ ] Scope requests use space delimiters, exact casing, and proper form encoding.
- [ ] User consent and policy are checked separately from scope registration.
- [ ] Authorization Code flow uses `response_type=code`; token exchange uses `grant_type=authorization_code`.
- [ ] Refresh tokens are only used when permitted by the client and issuance policy.
- [ ] Standard grant types are sent with exact protocol values at the token endpoint.
- [ ] Custom grants have matching converter, provider, and registration.
- [ ] Registrations and caches are consistent across instances.
- [ ] Tests verify both negative errors and corresponding positive flows.
- [ ] Logs include correlation ID and error code without secrets, codes, or tokens.

When invalid scopes, unauthorized client grants, and unsupported server grants are properly distinguished, remediation becomes clear: fix the scope or policy, adjust the specific client's registration, or fully implement the grant provider. Keeping these three conditions separate ensures the Authorization Server only issues permissions that the client is truly authorized to use.

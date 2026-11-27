# Testing Device Authorization and polling states

The Device Authorization Grant solves the scenario of a device that has Internet connectivity but lacks a suitable browser or is hard to type on, such as a smart TV, game console, streaming device, printer, or CLI on a remote server. The device initiates an authorization request and displays a short code along with a verification address. The user opens a browser on a phone or another computer, logs in, enters the code, and approves access. The original device keeps polling the token endpoint periodically until the user completes, denies, or the session expires.

This flow is defined in RFC 8628 as an OAuth 2.0 extension grant. Spring Authorization Server ships built-in support for the Device Authorization endpoint, Device Verification endpoint, and `device_code` handling at the Token endpoint. What needs thorough testing is the lifecycle of the two codes, the browser verification UI, client polling behavior, and how the system responds accurately to each state.

This lab focuses on the following objectives:

- Distinguishing `device_code` and `user_code`, and understanding the role of each endpoint.
- Registering a client permitted to use the Device Authorization Grant in Spring Authorization Server.
- Implementing the user verification and consent page.
- Writing a polling client that honors `interval`, `authorization_pending`, `slow_down`, `access_denied`, and `expired_token`.
- Testing valid, error, expiration, polling-too-fast, and replay states.
- Protecting `user_code` against brute force, `device_code` against leakage, and users against remote phishing.

## 1. Understanding the Device Authorization flow

The Device Authorization Grant separates the device initiating the request from the device the user uses to authenticate. The first device does not need to receive a browser callback. It only needs an outbound connection to the Authorization Server to request codes and poll the Token endpoint.

For example, a user opens an app on a TV and selects "Sign in". The TV calls the Device Authorization endpoint, receives codes, and displays the verification address and `user_code`. The user opens a phone, visits that address, signs into their account, and confirms the TV is showing the matching code. After the user approves, the TV receives an access token on its next poll.

~~~text
TV / CLI / input-constrained device
       |
       | 1. POST device_authorization
       v
Spring Authorization Server
       |
       | 2. device_code + user_code
       |    verification_uri + expires_in + interval
       v
Device displays code and instructions
       |
       |                         Phone / browser
       |                                  |
       |                                  | 3. Open verification_uri
       |                                  v
       |                         User logs in
       |                                  |
       |                                  | 4. Enter user_code
       |                                  v
       |                         Display client and scopes
       |                                  |
       |                                  | 5. Approve / Deny
       |                                  v
       |                         Authorization Server
       |
       | 6. Poll token endpoint with device_code
       |    authorization_pending / slow_down
       |    (or access_denied / expired_token)
       |
       | 7. User approves
       v
Token endpoint returns access token
~~~

The device does not redirect the user back to a `redirect_uri` like the Authorization Code Flow. Nor does it receive an authorization code to exchange on its own. The Device Authorization endpoint returns two codes with different purposes:

| Value | Where used | Who uses it | How to protect |
|---|---|---|---|
| device_code | Token endpoint | Device waiting for authorization | Secret, high entropy, never displayed to the user, never logged |
| user_code | Verification page | User entering it on a secondary browser | Short, easy-to-enter code that still has entropy, attempt limits, and expiration |
| verification_uri | Device screen and browser | User | Short, stable HTTPS URL belonging to the right Authorization Server |
| verification_uri_complete | QR/NFC or deep link | Secondary browser | May include user_code; still requires user confirmation of the right device |
| expires_in | Device and server | Both client and server | Defines the lifetime of the device authorization session |
| interval | Client polling | Device | Minimum wait interval between poll attempts |

Do not confuse `device_code` with `user_code`. `device_code` is the verification credential the device sends back at the Token endpoint and is not meant for the user. `user_code` is the easy-to-type code linking the pending session with the verification action in the browser.

## 2. Endpoints and request/response formats

According to the Spring Authorization Server 1.5.8 documentation, the default endpoints include:

| Endpoint | Default | Role |
|---|---|---|
| Device Authorization | /oauth2/device_authorization | Client requests device_code and user_code |
| Device Verification | /oauth2/device_verification | Receives user_code from browser and handles verification |
| Token | /oauth2/token | Client polls with device_code to obtain tokens |

The Device Authorization request uses HTTP POST with URL-encoded form data. A public client sends `client_id`. A confidential client must authenticate using its registered method, just like other OAuth requests.

~~~http
POST /oauth2/device_authorization HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

client_id=tv-device-client&scope=media.read%20profile
~~~

If the client is confidential and registered with `client_secret_basic`, the request must include the corresponding Authorization header. Do not ship a client secret inside firmware on a public device or an app from which users could extract it. RFC 8628 treats such devices as public clients unless trustworthy additional protections exist.

A successful response looks like:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "device_code": "DEVICE_CODE_HIGH_ENTROPY",
  "user_code": "WDJB-MJHT",
  "verification_uri": "https://auth.example.test/activate",
  "verification_uri_complete": "https://auth.example.test/activate?user_code=WDJB-MJHT",
  "expires_in": 600,
  "interval": 5
}
~~~

The required fields are `device_code`, `user_code`, `verification_uri`, and `expires_in`. `verification_uri_complete` and `interval` are optional. If the response omits `interval`, the client must default to 5 seconds. The server should return uncacheable responses; these codes can be used to complete an authorization session.

The client should display:

- The full, readable `verification_uri`.
- The `user_code` formatted with spacing or hyphens so the user can enter it accurately.
- Remaining time before the code expires.
- Instructions to open a browser on another device and approve permissions.
- Pending, success, denied, or expired status.

Do not display `device_code`. Do not automatically initiate a Device Authorization request on app startup or when a previous session expires. Only start when the user actively chooses to sign in or link the device, to avoid creating unnecessary sessions and polling load.

### Token request

After displaying instructions, the device sends a Token request using the grant type registered in RFC 8628:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:device_code&
device_code=DEVICE_CODE_HIGH_ENTROPY&
client_id=tv-device-client
~~~

For a confidential client, authenticate the client according to its registered method. `client_id` is required when the client does not authenticate with client credentials. `device_code` must be the value received from the Device Authorization response and must belong to the same client sending the request.

Once the user has approved, the Token endpoint returns a standard OAuth 2.0 token response, which may include `access_token`, `token_type`, `expires_in`, `scope`, and `refresh_token` if permitted by client/policy. Do not assume every Device Authorization client receives a refresh token. Check `RegisteredClient` and `TokenSettings`.

## 3. Device authorization lifecycle and states

A device authorization session can be modeled with the following states:

~~~text
                  Device Authorization request
                              |
                              v
                           PENDING
                         /    |     \
                        /     |      \
                       v      v       v
                  APPROVED  DENIED  EXPIRED
                     |
                     | Valid Token endpoint poll
                     v
                   ISSUED
                     |
                     v
                 CONSUMED
~~~

Meaning of each state:

| State | Condition | Token endpoint behavior | Verification page behavior |
|---|---|---|---|
| PENDING | Codes created, user has not finished | authorization_pending | Allows login, entering code, and viewing request |
| APPROVED | User authenticated and approved | Next valid poll can receive token | Shows completion and instructs returning to device |
| DENIED | User denied | access_denied | Shows denied status |
| EXPIRED | device_code/user_code expired | expired_token | Rejects expired code, prompts to start a new session |
| ISSUED/CONSUMED | Token issued and code already used | Does not re-issue token from same device_code | Disallows re-confirming or reusing the session |

This is a domain model for design and testing. Actual internal state may be represented via token metadata, authorization attributes, and token status inside `OAuth2Authorization`. Do not assume internal enum names match the table labels verbatim.

A session must be associated with the requesting client, scopes, creation time, expiration, `user_code`, `device_code`, and consent state. When the user approves, the authorization must bind to the exact original client and scopes. Never allow a user entering one code to accidentally approve permissions for a different session.

## 4. Understanding polling intervals and returned states

Polling is the most distinctive aspect of the Device Authorization Grant. The device sends repeated token requests because there is no direct callback channel from the secondary browser. The client must throttle its rate based on `interval` and error codes.

RFC 8628-specific errors:

| Error | Meaning | What the client must do |
|---|---|---|
| authorization_pending | User has not completed verification/consent | Continue polling after at least interval |
| slow_down | Client polling too fast or server requests throttling | Increase interval by 5 seconds and keep the new interval for subsequent polls |
| access_denied | User denied | Stop polling, report denial |
| expired_token | device_code expired and session ended | Stop polling; start a new session only when the user explicitly requests it |
| invalid_client / invalid_grant / other errors | Invalid client or grant request | Stop polling and handle the error by type |

### Timing rules

1. The client must wait at least `interval` seconds before each poll. If the response omits `interval`, use 5 seconds.
2. When receiving `authorization_pending`, continue polling using the current interval.
3. When receiving `slow_down`, increase the wait interval by 5 seconds for the next poll and all remaining polls in that session.
4. When a request hits a connection timeout, the client must reduce its polling frequency before retrying. Exponential backoff, such as doubling the wait after each timeout, is recommended by the RFC.
5. For any error other than `authorization_pending` and `slow_down`, stop polling and display an appropriate outcome.
6. Do not send multiple parallel polls for the same `device_code`. Keep only one polling loop per session.
7. Do not continue polling past `expires_in` or after receiving a terminal state.

For example: the server returns `interval = 5`. The client waits at least 5 seconds before the first poll. If the server returns `authorization_pending`, the client waits at least another 5 seconds. If the server returns `slow_down`, the client increases the interval to 10 seconds and uses 10 seconds for subsequent attempts. If a request times out, the client may further increase the wait via exponential backoff; it must never drop below the current interval.

### Client-side state machine

~~~text
Receive device authorization response
             |
             v
Compute deadline from expires_in
             |
             v
Wait interval (or 5 seconds)
             |
             v
POST token endpoint
             |
       +-----+-------------------------+
       |                               |
       v                               v
  HTTP 200 token                    OAuth error
       |                               |
       v                    +----------+-----------+
  Session complete          |          |           |
                            v          v           v
                  authorization_pending slow_down  Terminal error
                            |          |           |
                            v          v           v
                     Wait interval  interval + 5s  Stop polling
                            |          |
                            +-----+----+
                                  |
                                  v
                            Continue polling if
                            not yet expired
~~~

The client should use a monotonic clock to track the deadline, preventing system clock changes from extending the session. Once the response provides `expires_in`, store the deadline locally. If the device sleeps or loses network connectivity for an extended period, check the deadline before polling again.

## 5. Designing the browser verification page

The user visits `verification_uri` over TLS, logs into the Authorization Server, enters `user_code`, and reviews the pending request. The Authorization Server must clearly inform the user which application or device they are authorizing and which scopes will be granted.

A UI flow should cover:

1. GET `verification_uri` page displays a form to enter `user_code`.
2. The user enters the code on the second device.
3. The server normalizes the code format and looks up the pending session.
4. If not logged in, redirects to the login page and returns to the verification step.
5. Displays the client/application name, scopes, and trustworthy device info if available.
6. Prompts the user to explicitly approve or deny.
7. Upon completion, instructs the user to return to the original device.
8. The Token endpoint reflects the decision on the next poll.

Abbreviated HTML form example:

~~~html
<form method="post" action="/oauth2/device_verification">
    <label for="user_code">Code displayed on the device</label>
    <input id="user_code"
           name="user_code"
           autocomplete="one-time-code"
           required>
    <button type="submit">Continue</button>
</form>
~~~

This example only illustrates the field and endpoint. The real page must integrate a CSRF token per Spring Security configuration, validation, user-friendly error messages, accessibility, and session policy. Do not disable CSRF application-wide just to make the form work.

In Spring Authorization Server, the `deviceVerificationEndpoint` filter handles `user_code` submission. `verificationUri` in the Device Authorization response is the address the user visits; the GET page can be provided by the application. These two URIs can differ:

- `/activate`: GET page where the user enters the code.
- `/oauth2/device_verification`: endpoint receiving the `user_code` POST and routing through Spring Authorization Server's authentication providers.

When using `verification_uri_complete`, the server may prefill `user_code` into the form. However, never auto-approve. Display the code in the browser and ask the user to compare it against the code shown on the device to mitigate remote phishing.

### Information to display before approval

The user should see enough information to spot unusual requests:

- Registered application/client name.
- Device type or device description if that data comes from a trusted source.
- Requested permissions/scopes in plain, understandable language.
- Request timestamp and remaining expiration time.
- Confirmation code to compare with the device.
- Two clear actions: approve or deny.

Do not treat a self-declared device name from the client as proof of identity. If you need to display a device label, manage it via provisioning or a trusted registry. The Device Authorization Grant carries remote phishing risk: an attacker can initiate a flow on their own device and trick a victim into entering the code on the real page. Clearly state which device the user is authorizing and encourage them to confirm that the device is right in front of them.

## 6. Configuring Device Authorization in Spring Authorization Server

Spring Authorization Server 1.5.8 includes built-in filters and providers for the Device Authorization endpoint, Device Verification endpoint, and Device Code grant at the Token endpoint. The default Authorization Server configuration includes these endpoints; the Token endpoint includes the converter/provider for `device_code`. The API examples below follow the 1.5.8 documentation; verify against the pinned dependency version in your project before applying, as APIs can change across branches.

### Endpoint configuration

Endpoint paths can be declared explicitly in `AuthorizationServerSettings`:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.test")
            .deviceAuthorizationEndpoint("/oauth2/device_authorization")
            .deviceVerificationEndpoint("/oauth2/device_verification")
            .tokenEndpoint("/oauth2/token")
            .build();
}
~~~

The Authorization Server configuration can customize the verification URI and consent page:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                    authorizationServer
                            .deviceAuthorizationEndpoint(device ->
                                    device.verificationUri("/activate"))
                            .deviceVerificationEndpoint(device ->
                                    device.consentPage("/oauth2/device-consent")));

    return http.build();
}
~~~

Here `/activate` is the URI returned to the user. The application must provide the corresponding GET page. POST `user_code` is handled at the `deviceVerificationEndpoint` configured in `AuthorizationServerSettings`. If you change paths, synchronize the form action and security filter chain.

This configures only the device endpoints, not the entire login setup. The application still needs filter chains for form login, the `/activate` page, the consent UI, error pages, and static resources. Protect admin and health endpoints separately. Keep CSRF enabled for state-changing web operations per policy.

### Client registration

Device clients usually cannot keep a client secret confidential because users can access the firmware or binary. In that case, register a public client with `ClientAuthenticationMethod.NONE`. If the client can genuinely protect credentials in a secure environment, a confidential client with an appropriate authentication method can be used.

~~~java
AuthorizationGrantType DEVICE_CODE_GRANT =
        new AuthorizationGrantType(
                "urn:ietf:params:oauth:grant-type:device_code");

RegisteredClient tvClient = RegisteredClient.withId(
                UUID.randomUUID().toString())
        .clientId("tv-device-client")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(DEVICE_CODE_GRANT)
        .scope("media.read")
        .scope("profile")
        .clientSettings(ClientSettings.builder()
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .deviceCodeTimeToLive(Duration.ofMinutes(10))
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .build())
        .build();
~~~

The example above illustrates a public device client. In production, store `RegisteredClient` in a durable repository such as JDBC. The client ID must be stable and provisioned through a management process; do not generate a new random client ID every time the application starts. Do not add `authorization_code` or `refresh_token` grants if the device does not need them.

`deviceCodeTimeToLive` sets the device code lifetime. This lifetime must be long enough for a user to grab their phone, open a browser, log in, and confirm, yet not so long that it increases phishing or session-hijacking risk. Apply the same expiration policy to the `user_code` and `device_code` experience, and test both sides.

### Repository and persistence

Device authorization state must persist across requests and across instances in multi-node deployments. Use an `OAuth2AuthorizationService` suited to the architecture, typically `JdbcOAuth2AuthorizationService` when using JDBC. Do not store pending device flows in memory if the client may poll a different node or the application runs multiple instances.

Verify that persistence can look up authorizations by both `device_code` and `user_code` using your SAS version's mechanism. Do not build a separate second code store without transactional synchronization with `OAuth2AuthorizationService`; if `user_code` and `device_code` state drift apart, the verification page could approve a session that the token endpoint never sees.

## 7. Implementing client polling

The client needs a single polling loop per device authorization session. The pseudocode below expresses the processing rules; HTTP calls, JSON parsing, cancellation, and clock handling should be implemented using libraries appropriate for the target device.

~~~text
response = requestDeviceAuthorization()
interval = response.interval if present else 5 seconds
deadline = monotonicNow + response.expires_in
timeoutBackoff = interval

while monotonicNow < deadline:
    wait(interval)

    if monotonicNow >= deadline:
        stop with expired state

    result = requestToken(device_code)

    if result is success:
        store token securely
        stop with authorized state

    if result.error == authorization_pending:
        interval = max(interval, response.interval or 5 seconds)
        continue

    if result.error == slow_down:
        interval = interval + 5 seconds
        timeoutBackoff = interval
        continue

    if result is connection timeout:
        timeoutBackoff = max(interval, timeoutBackoff * 2)
        interval = timeoutBackoff
        continue

    stop polling and display terminal error
~~~

Implementation rules to preserve:

- Wait `interval` before the first poll; do not poll immediately after the Device Authorization response.
- `authorization_pending` is not a terminal error; it is the normal waiting state.
- `slow_down` adds 5 seconds to the wait interval and never decreases within the same session.
- Timeouts must make the client reduce polling frequency before retrying.
- `access_denied`, `expired_token`, and other errors are terminal; exit the loop.
- Do not automatically start a new session after `expired_token`. Display instructions and wait for the user to explicitly restart.
- Do not let two threads or two processes poll the same `device_code` concurrently.
- Cancel polling when the user cancels login or closes the app.
- Never write `device_code` to logs, analytics, crash reports, or telemetry.

If the client can receive a notification through another channel, such as push or a dedicated connection, it may wait for the notification before polling. However, that is an optimization outside RFC 8628's baseline polling flow; it must still check status at the Token endpoint before using any token.

## 8. Testing the Device Authorization endpoint

Use MockMvc with a real Spring ApplicationContext to test the endpoint and Security filter chain. The client fixture must have the Device Code grant and appropriate authentication method.

Example test for the Device Authorization endpoint response:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class DeviceAuthorizationEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsDeviceAuthorizationForRegisteredPublicClient()
            throws Exception {

        mockMvc.perform(post("/oauth2/device_authorization")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("client_id", "tv-device-client")
                        .param("scope", "media.read profile"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.device_code").isNotEmpty())
                .andExpect(jsonPath("$.user_code").isNotEmpty())
                .andExpect(jsonPath("$.verification_uri")
                        .value("https://auth.example.test/activate"))
                .andExpect(jsonPath("$.expires_in").isNumber());
    }
}
~~~

The example assumes the `tv-device-client` fixture is provisioned and `verificationUri` is configured. `interval` is optional per the RFC; if the response omits this field, the test client must default to 5 seconds. Response tests should also verify `Cache-Control: no-store` and the absence of unnecessary secret data.

Negative cases to test:

- Nonexistent `client_id`.
- Client not registered with the Device Code grant.
- Scope not granted to the client.
- Confidential client missing or sending wrong credentials.
- Request sending duplicate parameters.
- Request with malformed scopes.
- Device authorization endpoint is not accessible over unencrypted HTTP in production environments.

## 9. Testing polling and token endpoint states

Do not test only a single successful poll. Test every state branch and client reaction after each response.

| Scenario | Setup | Expected result |
|---|---|---|
| Pending | Create device session, user_code not yet entered | Token endpoint returns authorization_pending |
| Approved | User authenticates, approves the right session | Next poll returns token |
| Denied | User chooses deny | Next poll returns access_denied |
| Expired | Wait or advance clock past deviceCodeTimeToLive | Token endpoint returns expired_token |
| Wrong device_code | Use nonexistent code | Request rejected, no token issued |
| Wrong client | Use device_code with another client | Request rejected |
| Reuse | Poll device_code again after token was issued | No second token issued |
| Poll too fast | Send requests faster than interval | Server protects capacity; if slow_down returned, client adds exactly 5 seconds to interval |
| Network timeout | Simulate timeout on client | Client performs exponential backoff and does not flood |
| Scope | Request scope outside policy | No permissions granted beyond client/consent |

Example testing the pending state at the Token endpoint:

~~~java
@Test
void tokenEndpointReportsAuthorizationPending() throws Exception {
    mockMvc.perform(post("/oauth2/token")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type",
                            "urn:ietf:params:oauth:grant-type:device_code")
                    .param("client_id", "tv-device-client")
                    .param("device_code", "DEVICE_CODE_FOR_PENDING_FIXTURE"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error")
                    .value("authorization_pending"));
}
~~~

The test fixture must create an authorization in the pending state in `OAuth2AuthorizationService`. Do not hardcode a `device_code` assumed to be valid in a standalone test. Create a session via the Device Authorization endpoint and use the real value from the response, or use a controlled persistence fixture.

### Testing slow_down and interval

RFC 8628 requires the client to increase `interval` by 5 seconds upon receiving `slow_down`. Write dedicated tests for the polling client to verify:

1. Initial `interval` is read from the response, or defaults to 5 seconds.
2. `authorization_pending` does not decrease `interval`.
3. `slow_down` increases `interval` by exactly 5 seconds.
4. Subsequent polls continue using the increased `interval`.
5. Timeouts trigger exponential backoff.
6. No new request is issued before the allowed time.

Do not use long `Thread.sleep` calls in unit tests. Inject a `Clock`, `Scheduler`, or a `WaitStrategy` abstraction to control time and verify the polling schedule. On the server side, verify the behavior of your pinned Spring Authorization Server version. Do not assume that having a Device Code provider in the framework means every rate-limit/`slow_down` policy is already configured for your system.

## 10. Testing the verification page and consent

The verification page is part of the security flow. Test both browser behavior and OAuth state.

Required cases:

- Unauthenticated user is redirected to login and returns to the right verification session.
- Valid `user_code` locates the right device authorization session.
- Nonexistent `user_code` is rejected with a message that does not leak excessive details.
- Expired `user_code` is rejected immediately on the verification page.
- Already-used `user_code` or terminal session cannot be approved again.
- Repeated wrong `user_code` submissions are rate-limited.
- User approval saves consent and binds it to the right client/scopes.
- User denial causes the Token endpoint to return `access_denied`.
- CSRF token is validated on form POST.
- `verification_uri_complete` only prefills the code; the user still sees the code and confirms the right device.
- The user can cancel or go back without generating a token.

One item requiring an explicit regression test is `user_code` expiration at the Device Verification endpoint. There has been an issue report in Spring Authorization Server where the verification page accepted an expired `user_code`, and only the Token endpoint poll later returned `expired_token`. Test your active version's behavior and ensure expired codes are rejected as soon as the user submits them on the verification page. Do not rely solely on the Token endpoint eventually rejecting the token.

## 11. Protecting user_code and device_code

`user_code` is usually short so users can type it on a phone. That makes its entropy lower than `device_code`. Attempt limits and lifetimes must be constrained.

Measures for `user_code`:

- Generate using a cryptographic random source, never an incrementing sequence or timestamp.
- Pick an easy-to-type character set, avoiding ambiguous characters such as O/0 and I/1.
- Normalize letter case and hyphens before comparison.
- Rate-limit by IP, client, session, and account signals; avoid locking out a user account just because one source IP is brute-forcing.
- Use a short, practical lifetime, and do not reuse codes within a window that could cause session confusion.
- Use error messages that do not reveal which codes exist or which user owns a code.
- Audit failure counts by correlation ID without logging the raw code.

Measures for `device_code`:

- Use high entropy since the user never types this code.
- Never display or log `device_code`.
- Accept it only from the exact client that initiated the session.
- Limit its lifetime and allow exchanging it only once.
- Never let `device_code` appear in browser URLs, analytics, referrers, or crash dumps.
- Purge/mask sensitive token metadata per retention policy after the session ends.

### Preventing remote phishing

An attacker can initiate a device flow on their own device, then persuade a victim to enter the `user_code` on the real Authorization Server page. Therefore:

- The verification page must state clearly that the user is authorizing a device.
- Display the client/app name and requested scopes.
- Encourage the user to check the device showing the matching `user_code`.
- When using QR or `verification_uri_complete`, still display the code and require confirmation.
- Never approve merely because the user is logged in or opened the link.
- Never treat client-self-reported info as the sole proof of device type.
- Keep `user_code` lifetime long enough to complete the flow yet short enough to limit the value of a stolen code.

The `verification_uri_complete` page may contain `user_code` in the query string. Restrict third-party scripts, set an appropriate `Referrer-Policy`, avoid writing query strings to access logs, and use `Cache-Control: no-store` for pages carrying session data.

## 12. Metadata and client compatibility

RFC 8628 extends OAuth Authorization Server Metadata with:

- `device_authorization_endpoint`: URL of the Device Authorization endpoint.
- `grant_types_supported`: must include `urn:ietf:params:oauth:grant-type:device_code` when supported by the server.

Verify the metadata that clients will use to discover endpoints. With Spring Authorization Server, confirm the Authorization Server Metadata endpoint and that published values match `AuthorizationServerSettings`. If the system also enables OIDC Discovery, distinguish OAuth metadata from Provider Configuration metadata and verify the exact document clients are expected to consume.

Do not hardcode endpoints across multiple clients when metadata can be used. If endpoint paths change, clients must rediscover or have their configuration updated accordingly. Test after changing the issuer, domain, reverse proxy, or context path to ensure `verification_uri` is a public HTTPS URL reachable from a secondary device.

## 13. Diagnosing common issues

| Symptom | Possible cause | What to check |
|---|---|---|
| Device Authorization returns invalid_client | Client does not exist or wrong authentication method | Check RegisteredClient and client authentication |
| unsupported_grant_type | Client not registered for Device Code grant or wrong URN in request | Compare grant type and form request |
| TV continuously polls authorization_pending | User has not entered code, logged in, or approved | Check user_code session and consent state |
| TV receives access_denied | User denied or consent policy denied | Show denial message, stop polling |
| TV receives expired_token | Device code expired | Stop polling, wait for user to explicitly restart |
| Activate page reports invalid code | Wrong, expired, already-used user_code, or normalization mismatch | Check format, TTL, and lookup |
| Verification page succeeds but token stays pending | Consent not saved or authorization state not updated | Check OAuth2AuthorizationService and consent service |
| Expired user_code still accepted on verification page | Verification provider in active version does not check expiry | Add regression test and validation in verification step |
| slow_down appears repeatedly | Client does not increase interval or multiple poll loops run concurrently | Check scheduler, state, and interval |
| Token endpoint overloaded | Client polls too fast or auto-starts flows in bulk | Check interval, rate limits, and ensure flows start only on user action |
| One node approves while another stays pending | Non-shared persistence or inconsistent cache | Check JDBC store, transactions, and cache invalidation |
| QR opens page but does not complete | Incorrect prefill link or user has not confirmed | Check verification_uri_complete and form workflow |

### Triage procedure

1. Identify the client ID, session creation timestamp, and correlation ID.
2. Verify Device Authorization endpoint responses have scrubbed sensitive codes.
3. Verify `user_code` exists, is unexpired, and is not yet terminal.
4. Confirm the user logged in and consented to the right client/scopes.
5. Inspect authorization state in persistence.
6. Check polling interval and timestamps without relying on logs containing raw `device_code`.
7. Check whether the node handling verification and the node handling tokens share the same persistence.
8. Re-run a smoke test with a fresh client fixture.
9. Document the root cause and add a regression test before closing the incident.

Do not perform bulk resets of authorization state to fix polling issues. Doing so can wipe out legitimate pending sessions. Before deleting or revoking data, identify the exact affected client and session.

## 14. Lab completion checklist

- [ ] The Device Authorization endpoint is enabled and its public URL is accurate.
- [ ] The Device Verification endpoint handles `user_code` per your SAS version.
- [ ] The Token endpoint accepts the `device_code` `grant_type` properly.
- [ ] The client is registered with the Device Code grant and proper authentication method.
- [ ] Public device clients contain no extractable hardcoded secret.
- [ ] Responses include `device_code`, `user_code`, `verification_uri`, `expires_in`, and `interval` when configured.
- [ ] The client waits `interval` before the first poll; defaults to 5 seconds when `interval` is absent.
- [ ] `authorization_pending` continues polling at the current interval.
- [ ] `slow_down` increases the interval by 5 seconds for subsequent attempts.
- [ ] Timeouts trigger exponential backoff.
- [ ] `access_denied` and `expired_token` stop polling.
- [ ] No parallel polls or automatic polling after expiration occur.
- [ ] The verification page requires login, code entry, client/scope review, and approve/deny.
- [ ] `verification_uri_complete` does not auto-approve and includes a code confirmation step.
- [ ] Expired `user_code` values are rejected immediately at the verification step.
- [ ] `user_code` is rate-limited and `device_code` has high entropy.
- [ ] `device_code` is never displayed, logged, or leaked via URL/referrer.
- [ ] Metadata publishes `device_authorization_endpoint` and the matching grant type.
- [ ] Multi-instance tests verify shared state.
- [ ] Audit events record outcomes without containing `device_code`, `user_code`, or tokens.

The Device Authorization Grant is only secure when the device, secondary browser, and Authorization Server coordinate properly. The client must honor the polling interval and stop on terminal states; the verification page must require the user to identify the right device and grant consent; and the server must protect `user_code` from brute force, `device_code` from leakage, and state from reuse. By testing pending, approved, denied, expired, and `slow_down` states alike, the system can serve input-constrained devices while preserving clear authorization boundaries.

## References

- RFC 8628 — OAuth 2.0 Device Authorization Grant: https://datatracker.ietf.org/doc/html/rfc8628
- Spring Authorization Server 1.5.8 — Protocol Endpoints: https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html
- Spring Authorization Server 1.5.8 — Configuration Model: https://docs.spring.io/spring-authorization-server/reference/configuration-model.html
- Spring Authorization Server 1.5.8 — AuthorizationServerSettings API: https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.html
- Spring Authorization Server 1.5.8 — TokenSettings API: https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html
- Spring Authorization Server issue #1977 — User Code expiration report: https://github.com/spring-projects/spring-authorization-server/issues/1977

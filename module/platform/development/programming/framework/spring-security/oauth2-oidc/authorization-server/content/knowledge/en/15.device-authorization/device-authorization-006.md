# Polling the Token Endpoint with device_code

## 1. Purpose and Use Case

**OAuth 2.0 Device Authorization Grant** (RFC 8628) solves the problem of devices with limited input capabilities or no suitable browser: TVs, game consoles, presentation hardware, media players, or CLI applications. The device displays instructions; the user uses **another device with a browser** to sign in and approve permissions. Meanwhile, the app on the initial device calls the **Token Endpoint repeatedly at a specified interval** to check whether the user has finished. This repeated checking is called **polling**.

With **Spring Security** and **Spring Authorization Server** running in **Spring Boot**, most device code validation logic lives in the Authorization Server's filters and providers. However, **the polling loop, wait schedule, protocol error handling, and UI state protection** are the responsibility of the **OAuth client on the device**. Correct server configuration is not enough if the client sends hundreds of requests per second or ignores <code>slow_down</code> errors.

Running example throughout:

- Authorization Server: <code>https://auth.example.com</code>.
- OAuth public client on the TV: <code>living-room-tv</code>.
- Requested scope: <code>media.read</code>.
- Device Authorization Endpoint: <code>POST /oauth2/device_authorization</code>.
- Device Verification Endpoint: <code>/oauth2/device_verification</code> (opened by the user in a phone browser).
- Token Endpoint: <code>POST /oauth2/token</code> (polled actively by the TV).

After this lesson, you will be able to:

1. Distinguish **<code>device_code</code>**, **<code>user_code</code>**, <code>verification_uri</code>, and <code>verification_uri_complete</code>.
2. Construct a valid Token Request with the <code>urn:ietf:params:oauth:grant-type:device_code</code> grant.
3. Build a polling loop that honors <code>interval</code>, <code>expires_in</code>, and backoff requirements on errors.
4. Handle <code>authorization_pending</code>, <code>slow_down</code>, <code>access_denied</code>, <code>expired_token</code>, and other OAuth errors properly.
5. Understand how Spring Authorization Server links a device code to the client, authorization, user authentication, and consent.
6. Write a Java polling client and design polling schedule tests without waiting in real wall-clock time.
7. Deploy safely in multi-instance environments, network dropouts, user cancellations, and resource-constrained devices.

**Version scope:** Server configuration Java snippets use the <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code> and <code>HttpSecurity.with(...)</code> style familiar from Spring Authorization Server 1.x. In Spring Security releases with integrated Authorization Server support, APIs/packages may differ; verify against your running version. Client examples use <code>RestClient</code> (Spring Framework 6.1+) and Java 17+. Code illustrates architecture, not a full production project source tree.

## 2. How Does Device Authorization Differ from Authorization Code?

In Authorization Code Flow, **the browser used for authorization typically runs alongside the OAuth client**, with a redirect URI and an authorization code exchange. Device Authorization Flow splits into two actors:

1. **The OAuth client device**: displays instructions and calls the token endpoint itself.
2. **The user's browser**: opens the verification URL, enters the code, and logs in/consents.

The device does not continually scrape an HTML page, never collects a password on the TV, and never receives login credentials from the phone. It simply sends <code>device_code</code> to the Token Endpoint until the server signals success or a reason to stop.

~~~mermaid
sequenceDiagram
    autonumber
    participant D as TV / Public OAuth Client
    participant AS as Authorization Server
    participant B as Phone Browser
    D->>AS: POST /oauth2/device_authorization (client_id, scope)
    AS-->>D: device_code, user_code, verification_uri, expires_in, interval
    D-->>D: Display URL and user_code to user
    D->>AS: POST /oauth2/token (device_code grant)
    AS-->>D: authorization_pending
    B->>AS: Open verification_uri and enter user_code
    AS-->>B: Login + consent per policy
    B->>AS: Approve permissions for device
    D->>AS: Poll after valid wait interval
    AS-->>D: access_token, token_type, expires_in, scope if applicable
    D-->>D: Store access token securely and call APIs
~~~

This is the **success** diagram. If the user denies, the device receives <code>access_denied</code>; if the user does not finish in time, the device gets <code>expired_token</code> or detects expiration locally. The server not yet having a final answer is a **normal** state, represented by <code>authorization_pending</code>.

### 2.1. Three Endpoints That Cannot Be Swapped

| Endpoint | Who sends the request? | Responsibility |
| --- | --- | --- |
| <code>/oauth2/device_authorization</code> | Device, once to initialize a session | Issues <code>device_code</code>, <code>user_code</code>, verification URL, TTL, and polling interval. |
| <code>/oauth2/device_verification</code> | User via browser on another device | Logs in, verifies <code>user_code</code>, checks client name, and captures consent decision. |
| <code>/oauth2/token</code> | Device, repeatedly by interval | Validates <code>device_code</code> and authorization state to return pending/slow_down errors or an access token. |

In Spring Authorization Server, these paths are **common defaults**; they can be changed via <code>AuthorizationServerSettings</code>. The OAuth client should use configured endpoint info or trusted discovery metadata rather than assembling URLs from the issuer blindly.

## 3. Initializing a Session to Obtain <code>device_code</code>

### 3.1. Device Authorization Request

For a registered public client with ID <code>living-room-tv</code>:

~~~http
POST /oauth2/device_authorization HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

client_id=living-room-tv&scope=media.read
~~~

This shows the request structure, not a command you can run against a non-existent server. Use **HTTPS** and URL encoding for the form body. A confidential client requiring client authentication must apply its registered method; devices incapable of protecting a client secret should usually be registered as **public clients** instead of hardcoding a secret into firmware to pretend security.

### 3.2. Device Authorization Response

Illustrative RFC 8628 response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "device_code": "secret-device-code-value",
  "user_code": "JXHP-4QMN",
  "verification_uri": "https://auth.example.com/oauth2/device_verification",
  "verification_uri_complete": "https://auth.example.com/oauth2/device_verification?user_code=JXHP-4QMN",
  "expires_in": 600,
  "interval": 5
}
~~~

The values are illustrative only and not live credentials. Key meanings:

| Field | Per RFC 8628 | What must the user/device do? |
| --- | --- | --- |
| <code>device_code</code> | **Required**, unpredictable string | Device keeps it secret and uses it in token polling; **never display to the user**. |
| <code>user_code</code> | **Required**, easy-to-type code | Displayed for the user to enter in the browser. |
| <code>verification_uri</code> | **Required** | Displays the HTTPS address the user must open on a phone or computer. |
| <code>verification_uri_complete</code> | **Optional** | Can be used for QR/deep links to reduce typing; still requires phishing defenses and confirmation. |
| <code>expires_in</code> | **Required**, in seconds | Lifetime of the device code **and user code**; client must stop when elapsed. |
| <code>interval</code> | **Optional**, in seconds | Minimum wait between token requests; **defaults to 5 seconds if omitted**. |

Never confuse <code>expires_in</code> in this response with <code>expires_in</code> of the access token issued after approval: they describe **two different credentials**.

### 3.3. <code>user_code</code> Differs from <code>device_code</code>

<code>user_code</code> is designed for humans to read and type, so it is typically shorter and requires rate limiting on the verification UI to prevent brute force. <code>device_code</code> is designed as an unpredictable secret value, **only** included in token polling requests.

**Wrong:** Sending <code>user_code=JXHP-4QMN</code> to <code>/oauth2/token</code> instead of <code>device_code</code>.

**Right:** The user enters <code>user_code</code> on the phone; the TV keeps <code>device_code</code> and sends that value periodically to the Token Endpoint.

## 4. Polling the Token Endpoint with the <code>device_code</code> Grant

Per RFC 8628 §3.4, after displaying instructions, the client sends a token request with these parameters:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&
device_code=secret-device-code-value&
client_id=living-room-tv
~~~

Line breaks in the body are for readability; real requests must be properly URL-encoded as a single form body. The decoded <code>grant_type</code> value is:

~~~text
urn:ietf:params:oauth:grant-type:device_code
~~~

| Parameter | Rule |
| --- | --- |
| <code>grant_type</code> | **Required** and must be the exact URN above. Do not use a shortened string like <code>device_code</code>. |
| <code>device_code</code> | **Required**, taken from the Device Authorization Response; never the user code. |
| <code>client_id</code> | **Required if the client does not authenticate with client credentials**. Public clients normally must send this field. |
| Client authentication | **Required if the client has issued credentials or another auth requirement**; use the registered method, such as HTTP Basic, private_key_jwt, or mTLS as appropriate. |

The RFC does not ask clients to resend <code>scope</code> during token polling: scopes are already bound to the earlier device authorization request and the user's decision. Never inject new scopes during polling to escalate privileges.

**A poll is not a new authorization grant.** Each request simply checks the status of the **same device code** within the same session; it does not regenerate codes while pending, change client IDs, or transfer tokens from one device to another client.

## 5. Polling State Machine

### 5.1. Flow on the OAuth Client Side

~~~mermaid
flowchart TD
    A["Receive device_code + expires_in + interval"] --> B["Display verification URI and user_code"]
    B --> C{"User cancelled or TTL elapsed?"}
    C -- Yes --> X["Stop polling, clear device_code from memory"]
    C -- No --> D["POST /oauth2/token with device_code"]
    D --> E{"Token response"}
    E -- "200 + access_token" --> S["Success, store token securely, stop"]
    E -- "authorization_pending" --> W["Wait at least current interval"]
    E -- "slow_down" --> I["Increase interval by 5 seconds"]
    I --> W
    E -- "access_denied" --> N["Stop: user denied"]
    E -- "expired_token" --> X
    E -- "Other OAuth error" --> F["Stop and handle error safely"]
    E -- "Connection timeout" --> T["Reduce frequency, e.g. exponential backoff"]
    T --> W
    W --> C
~~~

Device verification and state updates live on the Authorization Server; the client does not need to know internal tables or filters. A client state machine might define:

| Client state | Interpretation | Transition |
| --- | --- | --- |
| <code>WAITING_FOR_USER</code> | Just displayed user code; no decision yet. | Poll at the wait interval. |
| <code>POLLING</code> | Sending the scheduled token request. | Read response. |
| <code>BACKING_OFF</code> | Received <code>slow_down</code> or connection timeout. | Increase wait time, then poll again. |
| <code>AUTHORIZED</code> | Received valid access token per response contract. | Stop polling; use token for the right Resource Server. |
| <code>DENIED</code> | User denied. | Stop; do not retry with the same device code. |
| <code>EXPIRED</code> | Device code has expired. | Stop; may start a new flow **after user interaction**. |
| <code>CANCELLED</code> | User cancelled on TV/CLI or app closed. | Cancel schedule and clear state; never auto-issue tokens. |
| <code>FAILED</code> | Other client/grant/protocol error. | Stop and report error safely. |

### 5.2. Outcomes on the Authorization Server Side

Upon receiving a polling request, the server must verify the right client, that the device code belongs to a valid authorization, that the code is neither expired nor already redeemed, and the End-User's decision. In summary:

~~~text
Device code missing / wrong client / invalid
  -> reject request

Device code valid but End-User has not approved yet
  -> authorization_pending

Client polling too fast and server requests throttling
  -> slow_down (if policy is implemented)

End-User denied
  -> access_denied

Device code expired
  -> expired_token

End-User approved + valid client/token request
  -> issue access token and mark device code non-reusable
~~~

These branches represent protocol logic; exact errors for missing tokens, invalid clients, or already-consumed tokens may vary by version/provider. Clients should not rely on a single HTTP status code to distinguish branches, but rather parse the OAuth **JSON <code>error</code>**.

## 6. Four Specific Error Codes the Poller Must Understand

### 6.1. <code>authorization_pending</code>

If the user has not completed login/consent yet, the token endpoint returns:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"authorization_pending"}
~~~

This is an **expected state** of the Device Flow, not an application error that warrants raising an alarm on every occurrence. The client keeps the session and **waits at least the current interval before the next poll**. Do not generate another device code, change scopes, or show "Login failed" to the user just because it is pending.

### 6.2. <code>slow_down</code>

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"slow_down"}
~~~

RFC 8628 mandates that the poller must **increase the interval by 5 seconds** upon receiving this error, applying to **the next poll and all subsequent polls**. For instance, if the previous interval was 5 seconds, one <code>slow_down</code> makes it 10 seconds; another <code>slow_down</code> makes it 15 seconds.

Never wait an extra 5 seconds once and then drop back to the old interval. Never treat HTTP 400 itself as a trigger to retry immediately; doing so violates the protocol and increases server load and rate-limit risk.

### 6.3. <code>access_denied</code>

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"access_denied"}
~~~

The End-User denied or authorization was refused. The client **stops polling immediately**, clears the device code, and displays an appropriate message. Never automatically fire a new device authorization request to "work around" a denial; retrying requires explicit user action.

### 6.4. <code>expired_token</code>

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"expired_token"}
~~~

<code>device_code</code> expired, and the device authorization session has ended. The client **stops polling** and discards the held device code. To continue, it may initiate a new flow, ideally waiting for user interaction to avoid unnecessary polling.

### 6.5. All Other OAuth Errors

Errors like <code>invalid_client</code>, <code>invalid_request</code>, <code>unauthorized_client</code>, <code>unsupported_grant_type</code>, or invalid token errors do not permit endless polling. RFC 8628 requires: for **any error code other than** <code>authorization_pending</code> and <code>slow_down</code>, the client **must stop polling** and handle the failure appropriately.

If the server returns <code>429 Too Many Requests</code>, a proxy error, HTML, or malformed JSON, that is not an invitation to retry immediately. Follow trusted operational retry guidance if available; without a clear retry contract, stop safely rather than equating it with <code>authorization_pending</code>.

## 7. Calculating <code>interval</code>, <code>expires_in</code>, and the Polling Schedule

### 7.1. Minimum Wait Interval

Example initial response:

~~~json
{
  "device_code": "secret-device-code-value",
  "user_code": "JXHP-4QMN",
  "verification_uri": "https://auth.example.com/oauth2/device_verification",
  "expires_in": 600,
  "interval": 5
}
~~~

The client may send the first poll after displaying instructions; **between consecutive polling requests**, it must guarantee the minimum wait interval. An easy-to-control strategy is **waiting a full interval after the previous response finishes** before sending the next request; this can be slightly slower, yet never accidentally exceeds the allowed cadence.

If the server **omits <code>interval</code>**, use **5 seconds**, never defaulting to 0 or 1 second. If the server returns an invalid value, treat it as a protocol error or use a safe fallback no faster than the rule to avoid tight overload loops.

### 7.2. Example Timeline

~~~text
T = 0s   Device Authorization Response: expires_in=600, interval=5
T = 0s   Poll #1 -> authorization_pending
T = 5s   Poll #2 -> authorization_pending
T = 10s  Poll #3 -> slow_down
                    new interval = 5 + 5 = 10 seconds
T = 20s  Poll #4 -> authorization_pending
T = 30s  Poll #5 -> 200 OK + access_token
          STOP POLLING
~~~

Timestamps are illustrative and ignore network latency. What matters is not hitting exact whole seconds, but **never polling earlier than the minimum wait** and stopping immediately on terminal state.

### 7.3. Connection Timeouts: Slow Down, Never Retry Immediately

When the client **cannot connect or hits a connection timeout**, RFC 8628 requires the client to **reduce polling frequency before retrying**. The recommended method is **exponential backoff**. For example:

~~~text
current interval is 5 seconds
Connection timeout #1 -> wait at least 10 seconds
Connection timeout #2 -> wait at least 20 seconds
Connection timeout #3 -> wait at least 40 seconds
~~~

This is an example backoff policy, not a mandate for those exact numbers. If a later request returns <code>slow_down</code>, still add 5 seconds to the active interval. If the deadline arrives before the next poll time, **stop** instead of sending a late request.

Do not treat every <code>ResourceAccessException</code> in Java as a retryable network error: TLS certificate verification failures, permanently misconfigured DNS, or untrusted endpoints may require **stopping and failing** rather than retrying hundreds of times.

### 7.4. Deadline and Clocks

<code>expires_in</code> is counted in seconds from when the Authorization Server issued the response. On the client, use a **monotonic clock** such as <code>System.nanoTime()</code> to track remaining time; never rely solely on <code>LocalDateTime.now()</code> because the system wall clock can be altered.

Never save a 600-second TTL, restart the app later, and assume 600 seconds remain. To support resuming, persist an accurate deadline with trustworthy metadata, account for offline elapsed time, and treat the server as the final authority. For simple TV/CLI apps, discarding old sessions on restart is usually safer and easier to reason about.

## 8. Java Code: A Poller Using <code>RestClient</code>

### 8.1. Data Model

The client app receives the device authorization initialization response and stores it in per-session memory:

~~~java
// Runs inside the OAuth CLIENT on TV/CLI, NOT an AS filter.
record DeviceSession(
    String clientId,
    String deviceCode,
    long expiresInSeconds,
    Long intervalSeconds
) {}

record TokenHttpResponse(int httpStatus, JsonNode body) {}
~~~

Fields like <code>user_code</code> and <code>verification_uri</code> serve the display UI; the poller **does not need to send user code** to the token endpoint. If the app is a confidential client, add client authentication per registration; the snippet below is a **public client** sending <code>client_id</code>.

### 8.2. Sending One Polling Request and Reading Error Responses

~~~java
final class DeviceTokenHttpClient {
    private final RestClient restClient;
    private final ObjectMapper mapper;

    DeviceTokenHttpClient(RestClient restClient, ObjectMapper mapper) {
        this.restClient = restClient;
        this.mapper = mapper;
    }

    TokenHttpResponse pollOnce(DeviceSession session) {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type", AuthorizationGrantType.DEVICE_CODE.getValue());
        form.add("device_code", session.deviceCode());
        form.add("client_id", session.clientId());

        return restClient.post()
            .uri("https://auth.example.com/oauth2/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(form)
            .exchange((request, response) -> {
                JsonNode body = mapper.readTree(response.getBody());
                return new TokenHttpResponse(
                    response.getStatusCode().value(), body);
            });
    }
}
~~~

Choose <code>exchange(...)</code> instead of simple <code>retrieve().body(...)</code> because the token endpoint returns **HTTP 400 containing JSON <code>error</code>, which is completely valid under Device Flow**. You must read the response body when the server returns <code>authorization_pending</code> or <code>slow_down</code>.

Imports are omitted. This example targets Spring Framework 6.1+; in Spring Boot, inject a <code>RestClient</code> built from <code>RestClient.Builder</code> with TLS, connection timeout, read timeout, and a reliable HTTP client configured. Never log response JSON containing an access token or raw device code. The URI is hardcoded for illustration; when the AS customizes its token endpoint, load the official configured URL.

### 8.3. Response Handling Loop

The snippet below intentionally uses a **blocking API in a background worker**, suited for a CLI or dedicated desktop task. **Never call it directly on a Spring MVC HTTP request thread or a WebFlux event loop**; in reactive apps, use an appropriate scheduler/Reactor operator.

~~~java
final class DeviceCodePoller {
    private final DeviceTokenHttpClient tokenClient;

    DeviceCodePoller(DeviceTokenHttpClient tokenClient) {
        this.tokenClient = tokenClient;
    }

    // Returns JSON token response. Never log/serialize raw tokens carelessly.
    JsonNode awaitToken(DeviceSession session) throws InterruptedException {
        if (session.expiresInSeconds() <= 0) {
            throw new IllegalArgumentException("Invalid device code TTL");
        }

        long ttlNanos = TimeUnit.SECONDS.toNanos(
            session.expiresInSeconds());
        long startedAt = System.nanoTime();
        long intervalSeconds = session.intervalSeconds() == null
            ? 5L : Math.max(1L, session.intervalSeconds());
        boolean first = true;

        while (!Thread.currentThread().isInterrupted()) {
            long remainingNanos = ttlNanos
                - (System.nanoTime() - startedAt);
            if (remainingNanos <= 0) {
                throw new IllegalStateException("device_code expired");
            }

            // First poll may be sent right after displaying instructions.
            // Subsequent polls must wait at least the current interval.
            if (!first) {
                long waitNanos = TimeUnit.SECONDS.toNanos(intervalSeconds);
                if (waitNanos >= remainingNanos) {
                    throw new IllegalStateException("device_code expired");
                }
                TimeUnit.NANOSECONDS.sleep(waitNanos);
            }
            first = false;

            if (System.nanoTime() - startedAt >= ttlNanos) {
                throw new IllegalStateException("device_code expired");
            }

            TokenHttpResponse result;
            try {
                result = tokenClient.pollOnce(session);
            } catch (ResourceAccessException networkError) {
                if (!causedByTimeout(networkError)) {
                    throw networkError; // Do not retry all network/TLS errors.
                }
                // Double backoff, guarded against overflow.
                intervalSeconds = intervalSeconds > Long.MAX_VALUE / 2
                    ? Long.MAX_VALUE : intervalSeconds * 2;
                continue;
            }

            JsonNode body = result.body();
            if (body == null || !body.isObject()) {
                throw new IllegalStateException("Invalid token response");
            }

            if (result.httpStatus() >= 200
                    && result.httpStatus() < 300) {
                if (!body.hasNonNull("access_token")) {
                    throw new IllegalStateException("Missing access_token");
                }
                return body;  // Succeeded: stop polling immediately.
            }

            String error = body.path("error").asText("");
            switch (error) {
                case "authorization_pending" -> {
                    // Keep interval unchanged, poll again after wait.
                }
                case "slow_down" -> {
                    // RFC 8628: +5 seconds for subsequent requests.
                    intervalSeconds = intervalSeconds > Long.MAX_VALUE - 5
                        ? Long.MAX_VALUE : intervalSeconds + 5;
                }
                case "access_denied" ->
                    throw new IllegalStateException("User denied request");
                case "expired_token" ->
                    throw new IllegalStateException("device_code expired");
                default ->
                    throw new IllegalStateException(
                        "Device token request failed: " + error);
            }
        }
        throw new InterruptedException("Polling cancelled");
    }

    private boolean causedByTimeout(Throwable error) {
        for (Throwable cause = error;
                cause != null; cause = cause.getCause()) {
            if (cause instanceof SocketTimeoutException
                    || cause instanceof HttpTimeoutException) {
                return true;
            }
        }
        return false;
    }
}
~~~

**Code scope:**

- <code>RestClient</code>, <code>ObjectMapper</code>, <code>JsonNode</code>, <code>LinkedMultiValueMap</code>, and <code>AuthorizationGrantType.DEVICE_CODE</code> are library components; include version-appropriate imports and dependencies. <code>HttpTimeoutException</code> comes from <code>java.net.http</code>.
- Caller layers must still configure HTTP timeouts, cancellation, endpoint discovery, appropriate client authentication, <code>token_type</code>/<code>expires_in</code> checks, secure token storage, and application error handling.
- The poller can wait for a long time; run it on a single worker/background task per device session. If the user cancels, call <code>Future.cancel(true)</code> or equivalent cancellation and ensure in-flight HTTP calls are also aborted/timed out.
- Even when the client respects its deadline, **the Authorization Server decides whether the code has truly expired**. Successful responses must be validated per the token endpoint contract; never trust forged payloads from an unverified issuer URL or invalid TLS.
- Never attach an automatic HTTP client retry interceptor to retry 400 responses: it can break the poller's calculated interval.

For apps managing multiple concurrent device sessions, keep session state isolated per session rather than sharing global <code>deviceCode</code> or <code>intervalSeconds</code> variables. Never run multiple pollers for the **same device code**.

## 9. Configuring Spring Authorization Server to Support Device Grant

### 9.1. Registering the Client and Device Code TTL

Example public client for a TV:

~~~java
RegisteredClient tvClient = RegisteredClient.withId("tv-record-001")
    .clientId("living-room-tv")
    .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
    .authorizationGrantType(AuthorizationGrantType.DEVICE_CODE)
    .scope("media.read")
    .clientSettings(ClientSettings.builder()
        .requireAuthorizationConsent(true)
        .build())
    .tokenSettings(TokenSettings.builder()
        .deviceCodeTimeToLive(Duration.ofMinutes(10))
        .accessTokenTimeToLive(Duration.ofMinutes(15))
        .build())
    .build();
~~~

<code>ClientAuthenticationMethod.NONE</code> describes a public client with no secret for authentication. <code>AuthorizationGrantType.DEVICE_CODE</code> registers the grant using the RFC 8628 URN. <code>deviceCodeTimeToLive</code> sets the server-issued TTL; **it is distinct from the access token TTL**. Lifetimes are illustrative and must balance code-entry UX, polling load, attack exposure, and real policy.

If a client can safely store its own secret and is registered as a confidential client, configure token endpoint authentication per its allowed method. Never hardcode the same client secret into thousands of TVs and pretend it is a per-device secret.

**Do not confuse** <code>RegisteredClient.getId()</code> (internal ID) with <code>clientId</code> (ID sent in forms). The server must bind each device authorization to the right registered client; since a public client ID can be publicly known, the **device_code**, authorization state, and server-side checks must provide proper entropy and protection.

### 9.2. SecurityFilterChain and Endpoints

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .deviceAuthorizationEndpoint(Customizer.withDefaults())
            .deviceVerificationEndpoint(Customizer.withDefaults()))
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .exceptionHandling(exceptions -> exceptions
            .defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

    return http.build();
}
~~~

This is an **AS configuration skeleton**. The app still needs beans like <code>RegisteredClientRepository</code>, <code>OAuth2AuthorizationService</code>, <code>AuthorizationServerSettings</code>, user authentication, token generator, JWK/decoder if using JWT/OIDC, and a Web/form-login chain for user device verification.

In Spring Authorization Server:

- <code>OAuth2DeviceAuthorizationEndpointFilter</code> processes device/user code creation requests.
- <code>OAuth2DeviceVerificationEndpointFilter</code> handles user code entry and consent.
- <code>OAuth2TokenEndpointFilter</code> accepts token polling requests; behind it, converters/providers handle the device code grant, such as <code>OAuth2DeviceCodeAuthenticationConverter</code> and <code>OAuth2DeviceCodeAuthenticationProvider</code> in supported versions.
- <code>OAuth2AuthorizationService</code> persists/retrieves state for device authorizations, tokens, and flow decisions.

Never build a custom <code>/oauth2/token</code> controller just for polling when using Spring Authorization Server. Bypassing the framework's filters/providers can skip checks for client binding, code TTL, consent state, and token issuance.

### 9.3. Endpoint Settings and Issuer

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .deviceAuthorizationEndpoint("/oauth2/device_authorization")
        .deviceVerificationEndpoint("/oauth2/device_verification")
        .tokenEndpoint("/oauth2/token")
        .build();
}
~~~

The example uses standard paths for illustration. When changing endpoints, update clients, reverse proxies, metadata, and tests together; **never derive the token endpoint via string concatenation**. The issuer must be a stable public URL trusted by Resource Servers and clients. Behind a reverse proxy, handle forwarded headers only from trusted sources.

### 9.4. Storage in Multi-Instance Environments

An in-memory authorization service works for learning and testing, but with two nodes—one creating a device code and another receiving polls—state cannot stay consistent if each node holds a private store.

For production systems, use <code>JdbcOAuth2AuthorizationService</code> or a suitable durable backend, version-matched schema/migrations, indexes for token lookups, TTL cleanup, transactions, and atomic controls for transitioning from pending to approved/issued. Successful token issuance must prevent **two concurrent poll requests from using the same device code to obtain two tokens against policy**.

## 10. Why Is Polling at the Right Interval Both a Security and Operational Requirement?

### 10.1. Client Polling Too Fast

With 10,000 TVs, if each polls 20 times/second, the token endpoint could receive 200,000 requests/second just for waiting on user approval. When each TV waits 5 seconds, steady-state average load drops to roughly 2,000 requests/second. This is an illustrative load calculation; real traffic depends on active pending devices, session durations, and synchronization bursts.

The server must enforce appropriate rate limits and return <code>slow_down</code> when necessary. Clients must obey that signal and never hide polling cadence behind framework HTTP retry interceptors.

### 10.2. Anti-Abuse Controls

The Authorization Server should guard against:

| Risk | Mitigation |
| --- | --- |
| Guessing <code>user_code</code> | Adequate code entropy, short lifetime, attempt caps, anti-enumeration, and rate limits. |
| Guessing <code>device_code</code> | Unpredictable device code, secure storage, no logging, request limits by client/network/risk. |
| Excessive polling | Track/monitor poll cadence if needed, return <code>slow_down</code>, rate-limit, and enforce backend policies. |
| Using another client's code | Verify device code belongs to the exact client/authorization that created it. |
| Reusing consumed codes | Single successful transition; reject reuse/races per policy. |
| Redirecting users to spoofed pages | Show exact HTTPS verification URI and app name; never build QR/links from untrusted data. |
| Tricking victims into authorizing attacker's device | Verification browser displays client name, device/session if available, scopes, and explicit confirmation. |

In particular, **remote phishing** is a core Device Flow risk: an attacker can start a flow on their own device and trick another user into entering the matching user code. Simply having the user enter a code on the real website does not prove they intend to authorize **the right device**. Verification/consent UIs should let users verify the linked client/device and warn them if they did not initiate the action.

### 10.3. Never Substitute UI State for Security Checks

A TV displaying "Connected" **does not prove** a token is valid for every API. The client must receive a valid token response, check token type, scope, and lifetime, and then the Resource Server verifies the access token, issuer, audience, expiration, and resource-level permissions.

Conversely, a phone UI saying "Success" does not push an access token through the browser to the TV; the subsequent token poll is what lets the TV learn that authorization was approved.

## 11. Cancellation, Expiration, Flaky Networks, and Resuming

### 11.1. User Cancels on TV Before a Decision

When the user presses "Cancel" or closes the screen:

1. Stop the polling scheduler/task and abort any in-flight HTTP request if possible.
2. Clear <code>device_code</code> from session memory and clear the user code from the screen.
3. Do not automatically start a new flow unless requested by the user.
4. If the system offers a trusted server-side cancellation mechanism, call it per policy; **RFC 8628 defines no mandatory device code cancellation endpoint**.

Stopping on the client **does not guarantee** the pending server record disappears immediately; it will expire by TTL or be cleaned up by a separate cancellation workflow.

### 11.2. User Denies on the Phone

The token endpoint conveys the denial via <code>access_denied</code> per protocol when the client polls. The client stops and shows a clear message. Never quietly keep polling or automatically reopen consent with a fresh device code.

### 11.3. Device Loses Network Connectivity

On connection timeouts, increase the interval and retry **within the TTL window**, updating the UI to "Waiting for connection" if appropriate. If offline past expiration, stop. Never add extra time to <code>expires_in</code> on timeouts as if the code were extended.

If a token was issued successfully but connectivity dropped before the client read the response, the server may have already marked the device code as consumed. The client must handle uncertain outcomes: a subsequent poll **after backoff** may fail because the code was used; never assume the prior request did not issue a token. For flows needing idempotency, rely on server semantics and capabilities rather than "disabling consumed checks."

### 11.4. State Across Restarts and Clocks

To resume across restarts, design encrypted storage for the device code, a reliable deadline, client ID, endpoint, and polling cadence state, minimizing risk of logs/backups leaking bearer credentials. For simple devices, **cancelling the old session and restarting** is usually safer and easier to control.

## 12. Testing Polling and the Token Endpoint

### 12.1. Testing the State Machine Without Real-Time Waiting

To test polling schedules accurately without calling <code>Thread.sleep(5000)</code> in unit tests, separate three components:

1. <code>TokenTransport</code>: sends requests and returns fake HTTP/JSON responses in tests.
2. <code>Clock/Scheduler</code>: monotonic or virtual-time clock that tests can advance deterministically.
3. <code>DeviceCodePoller</code>: state machine handling responses and deciding when to poll next.

The sample code in section 8 illustrates a blocking algorithm; when integrating into a larger library or test suite, refactor to inject a scheduler/clock. Sample test cases:

~~~text
Given interval=5, expires_in=600
Responses:
  #1 authorization_pending
  #2 authorization_pending
  #3 slow_down
  #4 authorization_pending
  #5 success
Assert:
  Poll times >= [0, 5, 10, 20, 30] seconds from start
  Token received successfully exactly once; no requests after success
~~~

Do not assert exact equality on <code>[0,5,10,20,30]</code> if simulated processing/network delay exists; assert **never faster than the minimum interval**. If mocked responses add processing time, actual timestamps may be slightly later.

### 12.2. Required Protocol Test Matrix

| Scenario | Expected response or behavior |
| --- | --- |
| No End-User decision yet | <code>authorization_pending</code>; client waits interval then polls again. |
| No <code>interval</code> in initial response | Client defaults to **5 seconds**. |
| Response has <code>interval=8</code> | Client waits at least **8 seconds** between polls. |
| One <code>slow_down</code> after interval 8 | Interval becomes **13 seconds** for all subsequent polls. |
| Two consecutive <code>slow_down</code> responses | Interval increases by **10 seconds** total over the initial value. |
| Connection timeout | Reduces frequency, e.g. exponential backoff; never retries immediately. |
| User approves | Token endpoint returns token successfully; client stops polling. |
| User denies | <code>access_denied</code>; stops completely for that code. |
| <code>device_code</code> expired on server | <code>expired_token</code>; stops and allows a new flow on user request. |
| Local deadline expires before next poll | Does not send an expired request. |
| Using <code>user_code</code> at token endpoint | Rejected; no token issued. |
| Wrong <code>grant_type</code> | Not accepted as a valid device grant. |
| Public client missing <code>client_id</code> | Rejected per RFC 8628 rules. |
| Code issued to Client A polled by Client B | Rejected; no token issued to Client B. |
| Confidential client with wrong credentials | Rejected; does not trust client ID in body alone. |
| Previously succeeded code re-submitted | Does not re-issue tokens against policy; ensures one-time use. |
| Two concurrent polls for the same code | Must not produce two unauthorized successful issuances. |
| Scope altered in polling request | Must not expand requested/consented permissions. |
| AS returns 400 with <code>invalid_client</code> | Stops; does not retry forever. |
| Server returns HTML/invalid JSON | Stops safely or applies connection error policy; never treats as pending. |
| Cancelled on device | Polling task cancelled; stops sending requests. |
| User session on verification page expires | User must re-authenticate per server; device still honors TTL/interval. |

### 12.3. Spring Authorization Server Integration Tests

With <code>MockMvc</code> or a real HTTP client, verify across three stages:

1. **Create session:** Register a test client with <code>AuthorizationGrantType.DEVICE_CODE</code>, send <code>POST /oauth2/device_authorization</code>, extract <code>device_code</code>, <code>user_code</code>, <code>expires_in</code>, and <code>interval</code>.
2. **Pending:** Send <code>POST /oauth2/token</code> with the grant URN, device code, and client ID. Assert the pending error response and that state in <code>OAuth2AuthorizationService</code> is not yet authorized.
3. **User approves:** Complete login/verification/consent through the real UI chain or controlled integration fixture, then poll after the interval; verify the issued access token, scope limits, and that the consumed code cannot be reused.

Example assertion while still pending (assuming the test already obtained a valid <code>deviceCode</code>):

~~~java
mockMvc.perform(post("/oauth2/token")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type",
            AuthorizationGrantType.DEVICE_CODE.getValue())
        .param("device_code", deviceCode)
        .param("client_id", "living-room-tv"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.error")
        .value("authorization_pending"));
~~~

This is a **sample test snippet**, valid only if the public client, filter chain, and registered client are properly configured; obtain the code from a real device authorization request inside the test. If your framework version adds specific validations, adjust the fixture accordingly—never weaken security just to make tests pass.

### 12.4. Load Testing and Multi-Node Resilience

A system serving thousands of TVs must test:

- Many clients starting sessions concurrently: server handles rate, logs no credentials, bounds resource usage.
- A device code created on node A polled on node B: uses a shared authorization store.
- Pending → approved transition and polling happening simultaneously: token issued exactly once.
- Server emitting <code>slow_down</code>: client reduces frequency; no retry interceptor breaks the limit.
- Brute-forced codes or multiple IPs polling one code: throttled and alerted without leaking user decisions.
- Rolling deploys/restarts: pending sessions survive via durable storage if designed for it, or session loss behavior is documented.

## 13. Common Implementation Pitfalls

### Pitfall 1: Polling Every 100 ms for a "Real-Time Feel"

RFC 8628 requires honoring <code>interval</code>; a TV polling aggressively generates unnecessary load and triggers rate limiting. The UI can display local animations/spinners without increasing HTTP request frequency.

### Pitfall 2: Waiting 5 Extra Seconds Only Once After <code>slow_down</code>

If the initial interval is 5 and the server returns <code>slow_down</code>, the next poll must wait **10 seconds**, and stay at least 10 seconds for all subsequent polls; another slow_down raises it to 15 seconds. Never revert to 5 on <code>authorization_pending</code>.

### Pitfall 3: Confusing <code>user_code</code> with <code>device_code</code>

<code>user_code</code> is for the user to enter in the browser; <code>device_code</code> is for the client to present at the token endpoint. Passing user code during token polling is invalid and increases risk if secret codes start leaking into logs.

### Pitfall 4: Treating Every HTTP 400 as "Still Waiting"

In Device Flow, HTTP 400 can mean <code>authorization_pending</code>, <code>slow_down</code>, <code>access_denied</code>, <code>expired_token</code>, or a fatal client error. Parse the JSON <code>error</code> and branch accurately; only the first two permit continuing to poll.

### Pitfall 5: Automatically Retrying the Same Device Code After Expiration

Once TTL elapses or <code>expired_token</code> arrives, stop. If the user wants to try again, **initiate a fresh Device Authorization Request** for a new pair of codes; never reuse expired codes.

### Pitfall 6: Failing to Limit Concurrent Requests

Two background workers sharing one device code can poll simultaneously, doubling load and racing right as the server issues a token. Enforce one poller per session and atomic completion state; the backend must block code reuse.

### Pitfall 7: Treating <code>ClientAuthenticationMethod.NONE</code> as "No Validation Needed"

A public client holds no secret, yet still requires a registered <code>client_id</code>, valid device code, client–authorization binding, End-User state, valid scopes, and policy checks. Never hand one client's device code or access token to another client merely because both are public.

### Pitfall 8: Using <code>verification_uri_complete</code> for Everything

<code>verification_uri_complete</code> helps build QR/deep links; it is **not** the URL to submit device codes to the token endpoint or a shortcut that completes authorization on the TV. When showing QR codes, guard against remote phishing, check hostnames, and protect users from uninitiated pairing requests.

### Pitfall 9: Ignoring Lifetimes and State Across Multiple Server Nodes

If a device code is created on node A and node B cannot find it due to isolated in-memory stores, polling keeps failing. Use a shared store and proper transactions for production, or explicitly scope single-node demos as non-HA.

## 14. Production Checklist

| Area | Check |
| --- | --- |
| Protocol compliance | Grant URN, form parameters, right endpoints, and HTTPS. |
| Polling interval | Default 5 seconds if omitted, never poll too fast, honor <code>slow_down</code>. |
| Deadline | Use TTL from <code>expires_in</code> with a monotonic clock; never poll past expiration. |
| Error handling | Retry on pending/slow_down; stop on denied/expired/other errors. |
| Network resilience | Exponential backoff on timeouts; handle TLS errors safely. |
| Client registration | Permitted for device grant, accurate client ID/authentication method/scopes. |
| Credential security | Device code and tokens never exposed in URLs, logs, analytics, crash reports, or unprotected backups. |
| Server storage | Device authorization, user verification, consent, and token state consistent across nodes. |
| One-time issuance | Guard against races and device code reuse once successfully redeemed. |
| Abuse protection | Rate limiting on verification, device code endpoint, and token polling. |
| UX | Clear URL/code display, waiting indicator, cancel button, expiration guidance, and phishing warnings. |
| Audit/monitoring | Track pending/denied/expired rates, slow_down counts, latency, active sessions, and anomalous rates. |
| Testing | Virtual-time state tests, HTTP integration tests, multi-node, concurrency, cancellation, and timeouts. |

## 15. Practice Exercises

You are building a smart TV app for an internal library reading service. The TV has <code>client_id=library-tv</code>; users grant <code>books.read</code> via phone. The Authorization Server runs three Spring Boot instances behind a load balancer, and the Device Authorization Response returns <code>expires_in=420</code>, <code>interval=7</code>.

1. Write the HTTP request to create a device code, distinguishing data shown to the user from data kept secret.
2. Write the token polling request with the exact grant URN, <code>device_code</code>, and <code>client_id</code>. Explain why the TV does not send <code>user_code</code> to the token endpoint.
3. Sketch the polling schedule if the first three responses are <code>authorization_pending</code>, <code>slow_down</code>, and <code>authorization_pending</code>. State the new interval for subsequent polls.
4. Given <code>interval=7</code> when a request hits a connection timeout, propose an exponential backoff schedule and when to stop as remaining TTL nears zero.
5. Design a state machine with pending, slow down, authorized, denied, expired, cancelled, and failed states. Disallow retries after <code>access_denied</code>.
6. Write a <code>RegisteredClient</code> for the public TV with <code>AuthorizationGrantType.DEVICE_CODE</code> and <code>TokenSettings.deviceCodeTimeToLive(...)</code>; identify the AS chain configuration.
7. Explain what the backend must store so node A can create codes, node B can receive polls, and node C can handle user verification.
8. Design an integration test for two concurrent poll requests immediately after user approval, verifying no duplicate token issuance violates policy.
9. Propose how to protect users when an attacker sends them a URL and user code belonging to the attacker's device.
10. Write a virtual-time test verifying the client never polls faster than interval, adds 5 seconds per slow_down, and stops immediately upon receiving a token.

**Expected outcome:** A sound design must prove that **the device code is a session-bound credential**, **polling complies with RFC 8628**, **no token exists before End-User approval**, and **token polling stops immediately after success, denial, or expiration**.

## 16. References

- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): full protocol, especially §3.2 (response), §3.4 (token request), §3.5 (polling and errors), §5 (security).
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, client authentication, and responses/errors.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): advertising device authorization endpoint and grant types via metadata.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): token management and securing OAuth 2.0 flows.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Device Authorization/Verification Endpoints, Token Endpoint, and filters/configurers.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): Java DSL, endpoint settings, and issuer.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, <code>OAuth2Authorization</code>, and authorization storage.
- [Spring Authorization Server — TokenSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): <code>deviceCodeTimeToLive</code> and token lifetime settings.
- [Spring Security — Authorization Server (newer version)](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/): Authorization Server integration guide in newer Spring Security releases.

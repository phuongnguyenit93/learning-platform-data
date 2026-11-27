# Testing the filter chain, endpoint matcher, and issuer configuration

Spring Authorization Server often runs alongside an application's business endpoints within a Spring Security filter chain. OAuth 2.0/OIDC endpoints such as authorization, token, JWK Set, introspection, and userinfo have their own security requirements. If a request enters the wrong filter chain, the endpoint may be blocked by form login, skip client authentication rules, or receive inappropriate session and CSRF settings. If the issuer is misconfigured, discovery metadata and tokens may advertise a different address than the one clients are actually using.

Functional testing must prove three things: requests to Authorization Server endpoints are routed to the right SecurityFilterChain; application requests continue to use the default chain; and the issuer appears consistently in metadata and tokens. Test through MockMvc with the real filter chains loaded in the application context, rather than testing individual configuration beans in isolation.

## 1. Distinguishing between a SecurityFilterChain matcher and an authorization matcher

Spring Security has two distinct layers of decision-making:

- securityMatcher selects which SecurityFilterChain will handle an HTTP request. FilterChainProxy iterates through the chains in order and uses the first chain whose matcher returns true.
- requestMatchers inside authorizeHttpRequests decide whether a request is permitted or requires authentication once it has entered a chain.

These two types of matchers are not interchangeable. Writing requestMatchers("/oauth2/**").authenticated() in the default chain does not create a separate chain for the Authorization Server. Conversely, securityMatcher("/oauth2/**") only selects the chain; it does not replace the authorization rules inside that chain.

For the Authorization Server, obtain the matcher from OAuth2AuthorizationServerConfigurer.getEndpointsMatcher(). This matcher stays tied to the set of endpoints managed by the configurer, even when some endpoints are customized. Avoid manually listing a few paths like /oauth2/authorize and /oauth2/token, as that can miss JWK Set, introspection, revocation, device authorization, or OIDC endpoints.

## 2. Configuring two filter chains

The following example uses the modern configuration API of Spring Security 6 and the Spring Authorization Server version with OAuth2AuthorizationServerConfigurer.authorizationServer(). The higher-order chain handles protocol endpoints; the second chain handles the rest of the application.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults())
        )
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
        )
        .exceptionHandling(exceptions ->
                exceptions.defaultAuthenticationEntryPointFor(
                        new LoginUrlAuthenticationEntryPoint("/login"),
                        new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
                )
        );

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public-probe", "/assets/**").permitAll()
                .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

The second chain declares no securityMatcher, so it acts as the fallback chain for remaining requests. Order is part of the security behavior: if the fallback chain comes first and its matcher catches every request, the Authorization Server chain will never be invoked. When using an older version of Spring Authorization Server, the way the configurer is instantiated or applied may differ; keep the principle of using the endpoint matcher from the configurer and verify the API against your actual dependency version.

In the example, OIDC is enabled to provide discovery and userinfo. If the application does not support OpenID Connect, omit the oidc configuration and omit OIDC-only tests. OAuth 2.0 endpoints must still be tested according to the actual configuration.

## 3. Configuring a static issuer

The issuer is the URL identifier of the Authorization Server. Clients use the issuer to validate metadata, verify tokens, and identify the issuing server. In production environments, it is usually best to configure a stable public issuer rather than letting the value change based on the incoming request's Host header:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://identity.example.com")
            .build();
}
~~~

The issuer value must match the issuer that clients are configured to trust exactly, including scheme, hostname, port if any, and path. Avoid inconsistently adding or omitting a trailing slash. Endpoint URLs in metadata are typically constructed from the issuer and the server's endpoint settings.

If deployed behind a reverse proxy or ingress, the application might receive internal requests over HTTP while clients connect over HTTPS. When the issuer is not statically configured, the server may derive the address from the current request; in that case, Forwarded or X-Forwarded-* headers affect the scheme and host seen by the application. Only process these headers from trusted proxies. Do not allow arbitrary Internet clients to send forwarded headers to dictate the issuer.

## 4. Preparing the integration test

Use an application context that contains the exact two SecurityFilterChains, AuthorizationServerSettings, RegisteredClientRepository, OAuth2AuthorizationService, and JWKSource as the integrated application. The following test examples use Spring Boot with MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationServerSecurityIntegrationTests {

    private static final String ISSUER =
            "https://identity.example.com";

    @Autowired
    MockMvc mockMvc;

    @Autowired
    FilterChainProxy springSecurityFilterChain;

    @Autowired
    JwtDecoder jwtDecoder;

    // Tests in the following sections belong in this class.
}
~~~

If using @WebMvcTest, you must explicitly import both chains and the Authorization Server's dependent beans. A test slice that loads only the application chain or only the Authorization Server chain can produce false positives because it does not test chain selection ordering in the full context.

For the JWK Set endpoint, a JWKSource bean containing the corresponding public key is required. For OIDC discovery, enable OIDC in the configurer. Create clients, users, and consents via dedicated fixtures so tests do not depend on leftover data from previous runs.

## 5. Verifying matchers and chain ordering

You can test the matchers directly as an additional diagnostic check. The example below assumes the test context has the Authorization Server chain first and the application chain second:

~~~java
@Test
void authorizationServerMatcherSelectsProtocolEndpointsOnly() {
    List<SecurityFilterChain> chains =
            springSecurityFilterChain.getFilterChains();

    MockHttpServletRequest authorizeRequest =
            new MockHttpServletRequest("GET", "/oauth2/authorize");
    MockHttpServletRequest tokenRequest =
            new MockHttpServletRequest("POST", "/oauth2/token");
    MockHttpServletRequest applicationRequest =
            new MockHttpServletRequest("GET", "/public-probe");

    assertThat(chains.get(0).matches(authorizeRequest)).isTrue();
    assertThat(chains.get(0).matches(tokenRequest)).isTrue();
    assertThat(chains.get(0).matches(applicationRequest)).isFalse();
}
~~~

This test checks the first chain's matcher. It does not replace HTTP testing because FilterChainProxy also depends on the actual order and behavior of filters. If the application has additional chains for actuator, static resources, or separate APIs, update the test to match the expected order of all chains in the test context.

## 6. Proving application requests enter the fallback chain

The /public-probe path in the configuration example is configured with permitAll by the application chain. Create a test-only probe endpoint or use an existing public endpoint:

~~~java
@Test
void applicationRouteUsesApplicationSecurityRules() throws Exception {
    mockMvc.perform(get("/public-probe"))
            .andExpect(status().isOk());
}
~~~

If this request is mistakenly captured by the Authorization Server chain, the first chain's authenticated rule may redirect it to login or return an authentication error. Testing a public application endpoint therefore helps detect if the first chain accidentally uses an overly broad matcher such as anyRequest or /**.

You should also add a protected business endpoint to confirm that the application chain still requires authentication. One passing public endpoint does not prove every rule in the second chain is correct; it only confirms one representative case.

## 7. Verifying the behavior of Authorization Server endpoints

The following HTTP tests prove that protocol endpoints are served by the Authorization Server configuration. Default paths can be changed via AuthorizationServerSettings, so use the application's actual paths if endpoints have been customized.

**JWK Set endpoint:** When JWKSource is configured, the public endpoint must return JSON containing the list of public keys:

~~~java
@Test
void jwkSetEndpointIsReachableWithoutLogin() throws Exception {
    mockMvc.perform(get("/oauth2/jwks"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.keys").isArray());
}
~~~

The public JWK Set should contain only public keys. Do not let private key members such as d, p, q, dp, dq, qi, or oth appear in the response. You can add assertions checking that each JWK does not contain these private members.

**Authorization endpoint:** For an unauthenticated HTML request, the Authorization Server chain can redirect the user to the login page via the AuthenticationEntryPoint:

~~~java
@Test
void authorizationEndpointRequiresUserAuthentication() throws Exception {
    mockMvc.perform(get("/oauth2/authorize")
                    .accept(MediaType.TEXT_HTML)
                    .param("response_type", "code")
                    .param("client_id", "browser-client")
                    .param("redirect_uri", "https://client.example/callback")
                    .param("scope", "openid profile")
                    .param("state", "state-test"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                    HttpHeaders.LOCATION, containsString("/login")));
}
~~~

This test focuses on the case of a browser request without a user session. A request missing client_id or redirect_uri may be rejected during protocol validation before reaching the login step; therefore, use a valid client and redirect URI when testing the AuthenticationEntryPoint.

**Token endpoint:** The token endpoint must perform client authentication according to the registered method. A negative test can send invalid client credentials and verify that the server returns the OAuth error invalid_client and no token:

~~~java
@Test
void tokenEndpointRejectsInvalidClientCredentials() throws Exception {
    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("browser-client", "wrong-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "client_credentials")
                    .param("scope", "api.read"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_client"))
            .andExpect(jsonPath("$.access_token").doesNotExist());
}
~~~

Register the client fixture with the client_credentials grant type and the corresponding client authentication method so the request reaches the credential check step. If using a different authentication method, replace the HTTP Basic helper accordingly. Do not use a request with the wrong grant type to conclude that client authentication is working.

## 8. Checking OIDC discovery and issuer

When OIDC is enabled, the discovery endpoint publishes the issuer and the endpoints clients need to call. Verify the issuer and key endpoint URLs in the same response:

~~~java
@Test
void oidcDiscoveryPublishesConfiguredIssuerAndEndpoints() throws Exception {
    mockMvc.perform(get("/.well-known/openid-configuration"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.issuer").value(ISSUER))
            .andExpect(jsonPath("$.authorization_endpoint")
                    .value(ISSUER + "/oauth2/authorize"))
            .andExpect(jsonPath("$.token_endpoint")
                    .value(ISSUER + "/oauth2/token"))
            .andExpect(jsonPath("$.jwks_uri")
                    .value(ISSUER + "/oauth2/jwks"));
}
~~~

If endpoints are customized, update the expected URLs according to AuthorizationServerSettings. If the application does not enable OIDC, you can check OAuth 2.0 Authorization Server Metadata at the well-known endpoint provided by your version and configuration; do not expect OIDC discovery to work when OIDC is not enabled.

The issuer in metadata must match the issuer used when issuing tokens. For an ID token obtained after an authorization code flow with the openid scope, decode it using a JwtDecoder configured with the corresponding JWKSource and verify the iss claim:

~~~java
Jwt idToken = jwtDecoder.decode(idTokenValue);
assertThat(idToken.getClaimAsString("iss")).isEqualTo(ISSUER);
~~~

This example assumes the test has completed an authorization code flow with the openid scope and obtained a valid ID token. When testing JWT access tokens, also verify the iss claim according to the token format the application issues. For opaque access tokens, JWT claims cannot be read directly; verify the issuer through metadata and introspection according to the application's contract.

## 9. Checking the issuer with Host and forwarded headers

A static issuer must remain unchanged when requests arrive with a different Host header. This test detects configurations that accidentally derive the issuer from the host supplied by the request:

~~~java
@Test
void configuredIssuerDoesNotFollowArbitraryHostHeader() throws Exception {
    mockMvc.perform(get("/.well-known/openid-configuration")
                    .header(HttpHeaders.HOST, "untrusted.example"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.issuer").value(ISSUER));
}
~~~

If the system relies on forwarded headers to construct public URLs, create dedicated tests for trusted proxies checking scheme, host, port, and context path. Also verify that direct requests from untrusted sources cannot spoof the issuer using Forwarded or X-Forwarded-Host. Do not assume a forwarded header is always ignored or always trusted; behavior depends on proxy configuration and the application's ForwardedHeaderFilter.

## 10. Functional test matrix

| Scenario | Request/observation point | Expected result |
|---|---|---|
| Authorization endpoint | GET /oauth2/authorize with valid request, unauthenticated | Redirects to login per HTML entry point configuration |
| Token endpoint | POST /oauth2/token with wrong client secret | invalid_client, no access token |
| JWK Set | GET /oauth2/jwks | 200 JSON, public keys only |
| OIDC discovery | GET /.well-known/openid-configuration | Metadata has accurate issuer and endpoint URLs |
| Public application route | GET /public-probe | Handled by application chain's permitAll |
| Protected application route | GET protected business endpoint | Requires authentication |
| Issuer with unknown Host | Discovery request with untrusted Host | Issuer retains statically configured value |
| OIDC token | Decode issued ID token | iss claim matches published issuer |

## 11. Common configuration mistakes

**Authorization Server chain is not ordered first:** FilterChainProxy selects the first fallback chain whose matcher matches. When an application chain catching all requests comes first, OAuth endpoints may be redirected to login or subjected to rules not meant for the protocol.

**Writing an overly narrow custom matcher:** A matcher containing only authorize and token can miss JWK Set, metadata, introspection, revocation, or OIDC. Obtain the matcher from the configurer so the endpoint list stays synchronized with configuration.

**Confusing matchers with authorization rules:** securityMatcher selects the chain; authorizeHttpRequests defines permissions within that chain. Both layers must be tested.

**Unstable issuer behind a proxy:** If the application derives the issuer from the request without properly handling forwarded headers, metadata may advertise http or an internal hostname. If it trusts forwarded headers from any source, clients can corrupt the advertised address. Configure a static issuer or restrict forwarded headers to trusted proxies.

**Checking only metadata:** Valid discovery does not guarantee that issued tokens have the right issuer. Also verify the iss claim of the ID token or JWT access token when the test flow produces the corresponding token.

**Test slice missing filter chains:** A test that imports only one SecurityFilterChain cannot catch ordering errors between the Authorization Server chain and the application chain. Use an integrated application context or import all chains in the test.

## 12. Pre-release checklist

- [ ] The Authorization Server uses securityMatcher obtained from OAuth2AuthorizationServerConfigurer.getEndpointsMatcher().
- [ ] The Authorization Server chain is ordered before the catch-all application chain.
- [ ] The application chain continues handling business routes and static resources according to its own policy.
- [ ] Tests prove the authorize, token, and JWK Set endpoints go through the expected configuration.
- [ ] JWK Set exposes only public keys.
- [ ] OIDC discovery works when OIDC is enabled and publishes the exact issuer.
- [ ] The issuer in the ID token or JWT access token matches the issuer in metadata.
- [ ] Host and forwarded headers cannot alter the public issuer.
- [ ] Tests use an application context containing the full set of filter chains matching the deployment environment.

When these tests run in CI, changes to endpoints, filter chain ordering, proxies, or the issuer are caught before they disrupt clients' OAuth 2.0/OIDC flows.

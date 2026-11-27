# Integrating a Spring OAuth2 Client via Issuer Discovery

## 1. Context and Objectives

In the **Application Integration** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson guides you through connecting a Spring Boot application to an OpenID Provider/Authorization Server using Spring Security OAuth2 Client via **issuer discovery**.

This module teaches how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application. When another application consumes the Authorization Server, the development team should not have to manually assemble the authorization, token, JWKS, and UserInfo URLs for every environment. Issuer discovery allows the client to fetch metadata from a trusted issuer identifier and then initialize a consistent provider configuration.

For example, an enterprise has an Authorization Server at issuer https://login.example.com and a Portal application using Spring Boot. The Portal needs to sign users in with OpenID Connect, then call the Orders API using an Access Token. Instead of hard-coding authorization-uri, token-uri, jwk-set-uri, and user-info-uri, the Portal declares issuer-uri. Spring Security queries Provider Configuration or Authorization Server Metadata, retrieves the endpoints and key location from the metadata, and creates a ClientRegistration.

After this lesson, you will be able to:

1. Distinguish between issuer identifier, provider metadata, and client registration.
2. Configure issuer-uri in Spring Boot.
3. Understand the discovery process of ClientRegistrations.fromIssuerLocation.
4. Sign in using Authorization Code Flow and PKCE.
5. Handle callbacks, sessions, ID Tokens, and UserInfo.
6. Use OAuth2AuthorizedClientManager and WebClient to call APIs with an Access Token.
7. Perform logout at the application and initiate RP-Initiated Logout when supported by the OP.
8. Test discovery, login, token relay, and issuer/redirect/JWKS errors.

## 2. Components in the Integration Model

| Component | Responsibility |
| --- | --- |
| OpenID Provider / Authorization Server | Authenticates the End User, issues ID Tokens and Access Tokens, publishes metadata |
| Issuer Identifier | Unique identifier of the OpenID Provider/Authorization Server |
| Provider Metadata | Publishes authorization endpoint, token endpoint, JWKS URI, UserInfo, and capabilities |
| ClientRegistration | Configuration of a client registered with a provider |
| ClientRegistrationRepository | Stores and looks up ClientRegistration by registration ID |
| OAuth2LoginAuthenticationFilter | Handles the Authorization Code callback for browser login |
| OAuth2AuthorizedClientRepository | Stores authorized clients bound to the principal/session in a Servlet application |
| OAuth2AuthorizedClientService | Stores authorized clients at the service level, suitable for use cases requiring persistence |
| OAuth2AuthorizedClientManager | Coordinates authorization, refresh, and token issuance for outbound calls |
| WebClient OAuth2 filter | Attaches the appropriate Access Token to requests calling a protected API |

### 2.1. Issuer vs. Registration ID

The issuer is the identity of the Authorization Server, for example https://login.example.com/tenant-a. The registration ID is an internal name chosen by the Spring application, for example corporate. One application can have multiple registration IDs pointing to multiple issuers or multiple client registrations of the same provider. The registration ID appears in login URLs such as /oauth2/authorization/corporate; it is not the issuer, client ID, or tenant ID.

### 2.2. Issuer vs. client_id

The issuer identifies the Authorization Server. client_id identifies the Portal within the Authorization Server's system. One issuer can register hundreds of clients; a Spring application can also declare multiple registrations pointing to different issuers.

## 3. How Does Issuer Discovery Work?

OpenID Connect Discovery publishes the Provider Configuration at a well-known endpoint. For a root issuer https://login.example.com, the endpoint is typically:

~~~text
https://login.example.com/.well-known/openid-configuration
~~~

For an issuer with a path https://login.example.com/tenant-a, the OIDC Provider Configuration is typically located at:

~~~text
https://login.example.com/tenant-a/.well-known/openid-configuration
~~~

The response is JSON metadata, for example:

~~~json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "token_endpoint": "https://login.example.com/oauth2/token",
  "jwks_uri": "https://login.example.com/oauth2/jwks",
  "userinfo_endpoint": "https://login.example.com/userinfo",
  "end_session_endpoint": "https://login.example.com/connect/logout",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

This is an abbreviated example. Actual metadata may include many other fields, and values depend on provider configuration.

### 3.1. Metadata Needed by the Client

- authorization_endpoint: where the browser is redirected for the user to authenticate and grant consent.
- token_endpoint: where the client exchanges the authorization code for tokens or refreshes a token.
- jwks_uri: where public keys are fetched to verify ID Token signatures.
- userinfo_endpoint: where additional claims about the End User are retrieved if the flow requires them.
- issuer: the issuer value must match the configured issuer and the iss claim in the ID Token.
- end_session_endpoint: where the RP initiates logout if the provider publishes and supports RP-Initiated Logout.

Metadata can also publish capabilities such as grant types, response types, signing algorithms, scopes, authentication methods, and PKCE support.

### 3.2. Discovery Does Not Automatically Register a Client

Discovery only helps the application learn provider endpoints and capabilities. It does not create a client_id, issue a client_secret, register a redirect URI, or automatically grant permissions to the Portal.

The client must still be pre-registered at the Authorization Server. The client ID, secret, or public-client configuration is provided through a separate onboarding process.

## 4. ClientRegistrations.fromIssuerLocation

Spring Security provides ClientRegistrations.fromIssuerLocation(issuer) to create a ClientRegistration.Builder from the issuer's metadata.

For an issuer with a host and path, this API sequentially tries the following discovery endpoints and uses the first successful response:

1. host/.well-known/openid-configuration/path per the compatibility notes of RFC 8414.
2. issuer/.well-known/openid-configuration per OpenID Connect Discovery.
3. host/.well-known/oauth-authorization-server/path per OAuth 2.0 Authorization Server Metadata.

If an endpoint returns HTTP 200, the metadata response is used to initialize the builder. Error responses other than 200 or 4xx may cause the process to stop according to the API rules; therefore, configure the discovery endpoint accurately and inspect logs when initialization fails.

### 4.1. Querying Only OIDC Discovery

If you want to use only the OpenID Provider Configuration endpoint, you can use:

~~~java
ClientRegistration registration =
        ClientRegistrations.fromOidcIssuerLocation(
                "https://login.example.com")
            .registrationId("portal")
            .clientId("portal-client")
            .clientSecret(clientSecret)
            .build();
~~~

fromIssuerLocation is more flexible when the provider supports OAuth Authorization Server Metadata; fromOidcIssuerLocation focuses strictly on OIDC discovery.

### 4.2. Issuer in Metadata Must Be Exact

The client must verify that the issuer field in the metadata matches the configured issuer exactly. Do not replace the issuer with another hostname, drop the path, or normalize it arbitrarily. When verifying the ID Token, the iss claim must also match the corresponding issuer.

Do not take an issuer URI from a query parameter or arbitrary user input and call discovery on it. If multiple providers are allowed to be configured, use an administratively managed list of trusted issuers to prevent SSRF and connecting to untrusted servers.

## 5. Configuring Spring Boot with issuer-uri

This is the most common configuration approach when the application uses Spring Boot auto-configuration.

### 5.1. Dependencies

For a Servlet MVC application:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

If the application uses Spring MVC and WebClient, add spring-boot-starter-webflux to use the WebClient API; there is no need to convert the entire MVC application to WebFlux.

### 5.2. application.yml

Portal application example:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: company-idp
            client-id: ${PORTAL_OIDC_CLIENT_ID}
            client-secret: ${PORTAL_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: Company Login
        provider:
          company-idp:
            issuer-uri: https://login.example.com
~~~

The variables PORTAL_OIDC_CLIENT_ID and PORTAL_OIDC_CLIENT_SECRET are loaded from the environment/secret manager. Do not commit real secrets to Git or shared configuration files.

### 5.3. Meaning of the Properties

| Property | Meaning |
| --- | --- |
| registration.portal | Registration ID chosen by the Portal |
| provider: company-idp | Links the registration to the provider configured below |
| client-id | Client ID issued by the Authorization Server |
| client-secret | Secret of the confidential client |
| client-authentication-method | How the client authenticates at the Token Endpoint |
| authorization-grant-type | Grant flow used by the client |
| redirect-uri | Callback handled by Spring Security |
| scope | Permissions requested by the client |
| issuer-uri | Issuer used for provider discovery |

### 5.4. Do Not Confuse Registration ID with Provider ID

portal is the registration ID; company-idp is the provider ID. Multiple registrations can reference the same provider while using different client IDs, secrets, redirect URIs, or scopes.

## 6. Configuring Public Clients and PKCE

An SPA or native app cannot reliably keep a client secret. When the application is a public client, configure the authentication method as none:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          desktop:
            provider: company-idp
            client-id: desktop-public-client
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company-idp:
            issuer-uri: https://login.example.com
~~~

A public client has no secret to prove its identity at the Token Endpoint. The Authorization Code Flow requires PKCE to bind the authorization code to the client instance that initiated the request.

Spring Security automatically adds PKCE when a client registration satisfies both conditions: no client-secret is configured (or the secret is empty) and client-authentication-method is none. In addition, PKCE can be required via ClientRegistration.clientSettings.requireProofKey=true for the Authorization Code Flow. If you need to customize how the Authorization Request is built, you can customize OAuth2AuthorizationRequestResolver. On the Authorization Server side, PKCE must be required for public clients and code_verifier must be verified when exchanging the code.

Do not place a dummy secret into an SPA/native app in an attempt to turn it into a confidential client. The secret can be extracted from the package, binary, browser storage, or the user's device.

## 7. Configuring OAuth2 Login

Once a ClientRegistrationRepository is available, enable OAuth2 Login in the SecurityFilterChain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class PortalSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Spring Boot automatically configures ClientRegistrationRepository from the spring.security.oauth2.client.registration.* and provider.* properties. If you need to configure the repository in Java, you can manually create ClientRegistration instances using ClientRegistrations.fromIssuerLocation.

### 7.1. Login Initiation URL

For registration ID portal, Spring Security provides the default URL:

~~~text
/oauth2/authorization/portal
~~~

When a user opens this URL:

1. Spring Security looks up the ClientRegistration with registration ID portal.
2. Creates an Authorization Request with the client ID, redirect URI, scope, state, and nonce when using OIDC.
3. Redirects the browser to the authorization endpoint obtained from discovery.

Do not redirect users directly to the token endpoint. The Token Endpoint is not a browser login endpoint.

### 7.2. Callback URL

By default, Spring Security handles callbacks matching the pattern:

~~~text
/login/oauth2/code/*
~~~

With redirect URI {baseUrl}/login/oauth2/code/{registrationId} and registration ID portal, the actual callback looks like:

~~~text
https://portal.example.com/login/oauth2/code/portal
~~~

This URI must be registered exactly at the Authorization Server. If you change the callback path, you must configure both redirect-uri and the corresponding OAuth2LoginAuthenticationFilter/redirection endpoint.

### 7.3. State and Nonce

- state binds the authorization response to the request initiated by the Portal, helping protect against CSRF/login response injection.
- nonce in OIDC binds the ID Token to the authentication request, helping detect replayed ID Tokens within the flow.

Do not disable state or nonce validation to work around callback errors. Check sessions/cookies, proxies, callback URLs, and whether the application runs on multiple nodes without shared sessions.

## 8. Authorization Code Flow via Discovery

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Browser / End User
    participant APP as Spring Boot Portal
    participant OP as OpenID Provider
    participant API as Orders API
    APP->>OP: Discovery from issuer-uri
    OP-->>APP: Provider metadata + jwks_uri
    U->>APP: GET /oauth2/authorization/portal
    APP-->>U: Redirect to authorization_endpoint
    U->>OP: Authorization Request (code, state, nonce, PKCE)
    OP->>U: Authentication + Consent
    U-->>OP: User authenticates and consents
    OP-->>U: Redirect callback?code=...&state=...
    U->>APP: GET /login/oauth2/code/portal
    APP->>OP: POST token_endpoint (code + verifier)
    OP-->>APP: ID Token + Access Token
    APP->>APP: Verify ID Token and create Authentication
    APP-->>U: Portal login session
    APP->>API: Request with Bearer Access Token
    API-->>APP: Protected resource
~~~

### 8.1. Exchanging the Authorization Code

Spring Security performs the token request on the backend. The client must:

- Send the exact authorization code.
- Use the redirect URI associated with the authorization request.
- Authenticate at the Token Endpoint using the registered authentication method.
- Send code_verifier if the request used PKCE.

The Authorization Server validates the code, redirect URI, client authentication, and PKCE before issuing tokens.

### 8.2. Verifying the ID Token

With OIDC Login, Spring Security uses provider metadata/JWKS to verify the ID Token, including key checks:

- Valid signature according to trusted algorithms/keys.
- iss matches the configured issuer.
- aud contains the Portal's client ID.
- exp and related timestamps are still valid.
- nonce matches the request value if one was sent.

Do not merely decode the JWT and trust its claims. Decoding the payload does not verify the signature, issuer, or audience.

### 8.3. ID Token vs. Access Token

| Token | Used For | Not Used For |
| --- | --- | --- |
| ID Token | Confirming authentication and subject for the OIDC Client | Calling the Orders API |
| Access Token | Accessing a resource server according to scope/audience | Serving as proof of login in place of an ID Token |
| Refresh Token | Requesting a new Access Token when issued and still valid | Sending to UserInfo or business APIs |

The Portal should not send an ID Token to an API just because it is a JWT. The API must receive an Access Token with the appropriate audience/resource.

## 9. Retrieving User Information via OIDC UserInfo

When the scope includes openid, Spring Security handles OIDC Login. If the provider publishes userinfo_endpoint, OidcUserService can call this endpoint with the Access Token to retrieve additional claims.

Controller example:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/me")
    Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("issuer", user.getIssuer().toString());
        result.put("subject", user.getSubject());
        result.put("name", user.getFullName());
        result.put("email", user.getEmail());
        result.put("emailVerified", user.getEmailVerified());
        return result;
    }
}
~~~

### 9.1. Subject Is the Stable Identifier Key

Use the (iss, sub) pair to identify a user in the integrated system. Do not use email as the unique key because emails can change, collide, or be reassigned to someone else.

If the provider uses pairwise subject identifiers, the same person may receive different sub values across two clients. The Portal must store mappings according to the designed issuer/client context and must not infer that two subjects are the same person merely because their emails match.

### 9.2. Scopes and Claims

| Scope | Typical Claims |
| --- | --- |
| openid | sub and OIDC authentication context |
| profile | name, given_name, family_name, preferred_username, picture, locale |
| email | email, email_verified |
| address | address |
| phone | phone_number, phone_number_verified |

The client only receives claims granted according to scope, consent, and provider policy. Do not assume adding a scope to the Portal configuration will automatically cause the provider to return sensitive data.

### 9.3. UserInfo sub Must Match ID Token sub

According to OIDC Core, sub in the UserInfo Response must match sub in the ID Token exactly. If they differ, the client must not use the UserInfo Response. Do not link accounts by email or username to ignore this mismatch.

## 10. Storing and Using OAuth2AuthorizedClient

OAuth2AuthorizedClient links:

- ClientRegistration.
- Principal name.
- Access Token.
- Refresh Token if present.

In a Servlet application, OAuth2AuthorizedClientRepository typically stores authorized clients bound to the principal/session. OAuth2AuthorizedClientService provides service-level persistence and is suitable when the application needs to manage authorized clients independently of a specific request.

Do not manually store raw Access Tokens in session attributes, cookies, localStorage, or logs. Use Spring Security's abstractions so token lifecycle, refresh, and authorization are managed consistently.

### 10.1. Calling APIs with WebClient

Example configuring OAuth2AuthorizedClientManager and WebClient:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class OAuth2ClientHttpConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .build();

        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean
    WebClient oauth2WebClient(OAuth2AuthorizedClientManager authorizedClientManager) {
        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
                new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                        authorizedClientManager);

        return WebClient.builder()
                .apply(oauth2.oauth2Configuration())
                .build();
    }
}
~~~

The example above is for a Servlet application with a request/session context. If running background tasks or services without an HttpServletRequest, use AuthorizedClientServiceOAuth2AuthorizedClientManager with OAuth2AuthorizedClientService instead of a request-bound manager.

Note on Resource Server errors: when constructing ServletOAuth2AuthorizedClientExchangeFilterFunction using the constructor that takes OAuth2AuthorizedClientManager as in the example above, the filter does not automatically configure a failure handler to remove the authorized client when the Resource Server returns 401/403. Configure an appropriate OAuth2AuthorizationFailureHandler if you want to remove rejected authorized clients. Another option is to use the constructor taking ClientRegistrationRepository and OAuth2AuthorizedClientRepository; that constructor automatically configures RemoveAuthorizedClientOAuth2AuthorizationFailureHandler. This mechanism handles tokens rejected by the Resource Server; it is distinct from the manager removing the authorized client when a refresh token returns invalid_grant.

### 10.2. Calling the Orders API with the User's Authorized Client

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

class OrdersClient {

    private final OAuth2AuthorizedClientManager authorizedClientManager;
    private final WebClient webClient;

    OrdersClient(
            OAuth2AuthorizedClientManager authorizedClientManager,
            WebClient oauth2WebClient) {
        this.authorizedClientManager = authorizedClientManager;
        this.webClient = oauth2WebClient;
    }

    String getOrders(String principalName) {
        OAuth2AuthorizeRequest authorizeRequest =
                OAuth2AuthorizeRequest.withClientRegistrationId("portal")
                        .principal(principalName)
                        .build();

        OAuth2AuthorizedClient client =
                authorizedClientManager.authorize(authorizeRequest);
        if (client == null) {
            throw new IllegalStateException("Unable to authorize Orders API call");
        }

        return webClient.get()
                .uri("https://api.example.com/orders")
                .attributes(
                        ServletOAuth2AuthorizedClientExchangeFilterFunction
                                .oauth2AuthorizedClient(client))
                .retrieve()
                .bodyToMono(String.class)
                .block();
    }
}
~~~

This is a synchronous example for illustration; in an end-to-end reactive application, do not use block(). On a Servlet request thread, ensure principalName belongs to the currently authenticated user and the authorized client belongs to the right registration.

### 10.3. Client Credentials for Service-to-Service

For a machine-to-machine client, use a separate registration with the client_credentials grant, confidential client authentication, and appropriate API scopes. Do not reuse the user's OIDC Login registration as a service account if policies differ.

Example acquiring a token with the manager:

~~~java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest.withClientRegistrationId("orders-service")
                .principal("orders-integration")
                .build();

OAuth2AuthorizedClient authorizedClient =
        authorizedClientManager.authorize(request);
~~~

The orders-service registration must declare authorization-grant-type: client_credentials and a client authentication method supported by the Authorization Server. The principal name here is a local identifier for the authorized client service flow; it is not an End User.

## 11. Manual Configuration Without Boot Properties

You can create registrations in Java if the application loads configurations from a tenant catalog or needs control over initialization:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration(proxyBeanMethods = false)
class ClientRegistrationConfiguration {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            OidcClientProperties properties) {

        ClientRegistration registration =
                ClientRegistrations.fromIssuerLocation(properties.issuerUri())
                        .registrationId("portal")
                        .clientId(properties.clientId())
                        .clientSecret(properties.clientSecret())
                        .clientAuthenticationMethod(
                                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                        .authorizationGrantType(
                                AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                        .scope("openid", "profile", "email")
                        .clientName("Company Login")
                        .build();

        return new InMemoryClientRegistrationRepository(registration);
    }
}
~~~

OidcClientProperties is a configuration class defined by the application itself, not a built-in Spring class. You can use @ConfigurationProperties to bind the issuer URI, client ID, and secret from externalized configuration.

InMemoryClientRegistrationRepository is suitable when registrations are loaded at startup and do not change at runtime. If the application needs dynamic registration management or multiple tenants, use an appropriate repository/registry and control the issuer source.

## 12. Multiple Issuers and Multi-Tenant Clients

A Spring application can declare multiple providers:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          tenant-a:
            provider: tenant-a-provider
            client-id: ${TENANT_A_CLIENT_ID}
            client-secret: ${TENANT_A_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile
          tenant-b:
            provider: tenant-b-provider
            client-id: ${TENANT_B_CLIENT_ID}
            client-secret: ${TENANT_B_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile
        provider:
          tenant-a-provider:
            issuer-uri: https://login.example.com/tenant-a
          tenant-b-provider:
            issuer-uri: https://login.example.com/tenant-b
~~~

Issuers must be administratively managed values. Do not build registrations by taking a tenant from the URL and concatenating it into an arbitrary issuer. If supporting dynamic tenants, use a tenant catalog/allowlist, verify domains and issuers, limit the number of registrations, cache discovery in a controlled manner, and provide a revocation mechanism.

### 12.1. Do Not Mix Authorized Clients Across Tenants

An Access Token issued by Tenant A must not be sent to Tenant B's API if audience/resource policies prohibit it. Cache keys and authorized client associations must include the registration/issuer context.

If the same principal name exists in two tenants, do not use the principal name as a unique key for application data. Use an identifier namespaced by issuer, typically (iss, sub).

## 13. Discovery and Operations When the Authorization Server Is Behind a Reverse Proxy

The published issuer and endpoints must be public URLs reachable by browsers and clients. For example, the application runs internally at http://authorization-server:9000, while the public URL is https://login.example.com.

Provider metadata must publish:

~~~json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "token_endpoint": "https://login.example.com/oauth2/token",
  "jwks_uri": "https://login.example.com/oauth2/jwks"
}
~~~

If metadata contains internal URLs or an issuer differing from the public host, the OAuth2 Client may redirect to an unreachable endpoint or reject the ID Token due to an iss mismatch.

### 13.1. Configuring the Issuer on the Authorization Server Side

Explicit configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://login.example.com")
            .build();
}
~~~

When deploying multiple issuers on the same host, issuer resolution must be consistent with multi-issuer configuration and request routing. Do not hardcode a fixed issuer if the deployment requires the issuer to vary per request.

### 13.2. Enabling OIDC Provider Configuration

Spring Authorization Server must enable OIDC to publish OpenID Provider Configuration, UserInfo, and Logout endpoints. Example with SecurityFilterChain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(Customizer.withDefaults())
        );

    return http.build();
}
~~~

This covers configuration for the protocol endpoints; a complete application also requires RegisteredClientRepository, OAuth2AuthorizationService, JWKSource, a user authentication chain, and corresponding policies. The OIDC Client Registration Endpoint remains disabled by default; there is no need to enable that endpoint solely for Spring OAuth2 Client to use issuer discovery.

### 13.3. Forwarded Headers

If a reverse proxy terminates TLS, the Authorization Server needs to know the public scheme/host/port/prefix when generating metadata and redirect URIs. Configure forwarded headers on the proxy and Spring Boot according to your topology, for example server.forward-headers-strategy=framework when appropriate.

Only trust forwarded headers from trusted proxies that overwrite client-supplied values. If the application directly trusts X-Forwarded-Host from the Internet, an attacker can spoof the issuer or URLs in the metadata.

### 13.4. Checking Metadata from the Client's Perspective

- issuer matches the issuer configured on the OAuth2 Client exactly.
- Authorization, token, and JWKS endpoints are reachable from the client's network.
- Endpoints use HTTPS in production.
- No internal hostnames or missing path prefixes appear.
- TLS certificates are valid and DNS points to the right environment.

## 14. Logout from Spring OAuth2 Client

Spring Security's default local logout clears the session at the Portal. It does not automatically terminate the SSO session at the OpenID Provider. If the OP publishes end_session_endpoint, the Portal can use OidcClientInitiatedLogoutSuccessHandler to initiate RP-Initiated Logout:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration(proxyBeanMethods = false)
class OidcLogoutConfiguration {

    @Bean
    LogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {

        OidcClientInitiatedLogoutSuccessHandler handler =
                new OidcClientInitiatedLogoutSuccessHandler(registrations);
        handler.setPostLogoutRedirectUri("{baseUrl}");
        return handler;
    }
}
~~~

Inject the handler into SecurityFilterChain:

~~~java
@Bean
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http,
        LogoutSuccessHandler oidcLogoutSuccessHandler) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .logout(logout ->
            logout.logoutSuccessHandler(oidcLogoutSuccessHandler)
        );

    return http.build();
}
~~~

The OP must publish the endpoint, accept the ID Token hint, and have the corresponding post-logout redirect URI registered. The redirect URI must be validated according to the OP's configuration. If the OP does not support RP-Initiated Logout, the handler cannot automatically perform global logout.

Logging out of a session does not automatically revoke all issued Access Tokens. If business requirements call for token revocation, implement token revocation or a separate policy.

## 15. Securing Integrated Applications

### 15.1. Protecting the Client Secret

- Load secrets from a secret manager or environment injection.
- Do not commit secrets to Git.
- Do not log Authorization headers, codes, or tokens.
- Rotate secrets according to policy.
- Choose private_key_jwt or mTLS if security requirements and infrastructure support them.

### 15.2. Redirect URI

The Redirect URI must be registered as an exact match at the Authorization Server. Use HTTPS in production; do not use wildcard domains/paths. When an application has multiple environments, register separate callbacks for dev/staging/production and avoid unnecessary credential sharing.

### 15.3. Session and CSRF

Browser-based OAuth2 Login typically relies on a session to store the authorization request and SecurityContext. Keep CSRF protection enabled for browser applications. Do not disable CSRF globally just to make a callback endpoint work; the OAuth2 callback has its own state verification mechanism.

### 15.4. Token Storage and Token Relay

- Do not store Access Tokens in browser localStorage unless supported by an appropriate threat model.
- Do not pass ID Tokens to a Resource Server instead of Access Tokens.
- Do not send Access Tokens to arbitrary user-supplied hosts.
- Only relay tokens to resource servers configured as trusted.
- Validate audience, scope, and resource before calling an API.
- Use TLS between the client and the Resource Server.

### 15.5. Discovery Endpoint as a Trusted Input

Issuer discovery causes the application to make outbound HTTP requests to metadata/JWKS URIs. Only use trusted issuers to avoid SSRF and DNS rebinding. Restrict egress network access, timeouts, response sizes, and redirects according to your threat model.

Do not allow users to submit arbitrary issuer URLs that the application then calls. For tenant onboarding, only resolve issuers that have been verified by an administrator.

### 15.6. Clock Skew and Time

ID Tokens and JWTs depend on exp, iat, nbf, and nonce/time windows. Synchronize clocks across the Authorization Server, client, and Resource Server using NTP. Configure only a reasonable clock skew; do not extend token lifetimes to mask clock errors.

## 16. Integration Testing

### 16.1. Testing Discovery

Use WireMock/MockWebServer or a test provider to return metadata. Verify:

1. The client queries the correct discovery URL for the issuer.
2. The metadata contains a valid issuer, authorization endpoint, token endpoint, and JWKS URI.
3. Issuer response mismatches are detected.
4. Metadata missing required endpoints causes registration initialization to fail.
5. TLS/network timeouts are handled and logged with sufficient detail without leaking secrets.

### 16.2. Testing OAuth2 Login with MockMvc

Spring Security Test provides oidcLogin() to simulate a user logged in via OIDC:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@SpringBootTest
@AutoConfigureMockMvc
class OidcLoginIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedOidcUserCanReadProfile() throws Exception {
        mvc.perform(get("/api/me").with(oidcLogin()
                        .idToken(token -> token
                                .claim("iss", "https://login.example.com")
                                .subject("user-123")
                                .claim("name", "Nguyen An")
                                .claim("email", "an@example.com"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject").value("user-123"))
                .andExpect(jsonPath("$.email").value("an@example.com"));
    }
}
~~~

oidcLogin() creates a test Authentication for controller/security authorization. It does not test discovery, code exchange, ID Token signatures, or the token endpoint; those parts require integration tests with a real provider or a mock test server.

### 16.3. Testing the Authorization Code Flow End-to-End

An end-to-end test should:

1. Start the Portal and test OP.
2. Verify discovery completes.
3. Initiate /oauth2/authorization/portal.
4. Follow the redirect to the authorization endpoint.
5. Authenticate the user and grant consent at the test OP.
6. Redirect back to the callback with code and state.
7. Confirm the Portal exchanges the code for tokens.
8. Verify the ID Token and create a session.
9. Call /api/me and protected APIs.
10. Verify refresh token, logout, and session cleanup according to policy.

### 16.4. Test Matrix

| # | Scenario | Expected Result |
| --- | --- | --- |
| 1 | Valid issuer-uri, discovery returns 200 | ClientRegistration is initialized |
| 2 | Metadata issuer differs from configured issuer | Registration/token validation fails |
| 3 | Discovery URL is unreachable | Clear initialization/connection error |
| 4 | Metadata is missing token_endpoint | Client fails to initialize a valid registration |
| 5 | JWKS URI is unreachable | ID Token validation fails |
| 6 | Incorrect client_id | Authorization/token request is rejected |
| 7 | Incorrect client_secret | Token request is rejected |
| 8 | Unregistered redirect URI | Authorization request is rejected |
| 9 | Callback state mismatch | Login response is rejected |
| 10 | ID Token issuer mismatch | Authentication fails |
| 11 | ID Token audience mismatch | Authentication fails |
| 12 | Expired ID Token | Authentication fails |
| 13 | Nonce mismatch | Authentication fails |
| 14 | UserInfo sub differs from ID Token sub | UserInfo response is not used |
| 15 | Access Token lacks required API scope | Resource Server returns authorization error |
| 16 | Calling Orders API with ID Token | Resource Server rejects the request |
| 17 | Access Token expired with valid Refresh Token | AuthorizedClientManager refreshes according to policy |
| 18 | Refresh Token is revoked | Refresh fails; re-authentication required |
| 19 | Calling API with wrong client registration | Token with wrong audience/resource is not sent |
| 20 | Tenant A token used in Tenant B | Rejected per issuer/audience policy |
| 21 | Local logout | Portal session is cleared |
| 22 | OP has end_session_endpoint | Handler initiates RP-Initiated Logout |
| 23 | OP does not publish logout endpoint | Global logout is not assumed |
| 24 | Reverse proxy drops forwarded scheme | Discovery/redirect URL is wrong and caught by test |
| 25 | User enters arbitrary issuer URI | Blocked by issuer allowlist |

## 17. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Application startup fails when using issuer-uri | Discovery endpoint unreachable or invalid metadata | Check issuer, DNS, TLS, metadata, and outbound network |
| /oauth2/authorization/portal returns 404 | Wrong registration ID or OAuth2 Login not enabled | Check registration ID and SecurityFilterChain |
| Authorization Server returns invalid_redirect_uri | Callback not registered or not an exact match | Align redirect-uri between Portal and RegisteredClient |
| Callback reports state mismatch | Session/cookie not preserved or wrong proxy/callback domain | Check cookies, session affinity, and forwarded headers |
| invalid_client at token endpoint | Client ID/secret/authentication method mismatch | Check RegisteredClient and client configuration |
| invalid_grant when exchanging code | Code expired, already used, or redirect/PKCE mismatch | Check code lifecycle and PKCE verifier |
| ID Token signature invalid | Wrong JWKS URI/key rotation/algorithm | Check metadata, key set, and signing algorithm |
| issuer mismatch | Public issuer and issuer in metadata/token differ | Configure AuthorizationServerSettings and proxy |
| UserInfo 401 | Access Token missing/invalid or revoked | Check token, scope, and endpoint policy |
| UserInfo returns fewer claims | Scope/consent/provider mapper not permitted | Check authorized scopes and claims release |
| WebClient does not attach token | AuthorizedClientManager/repository not configured or wrong registration ID | Check manager, authorized client, and filter |
| API returns 401 despite successful login | Access Token has wrong audience/resource | Issue token for the right API and check resource server |
| Refresh does not work | Provider does not issue refresh tokens or client lacks scope/offline policy | Check grants, consent, and refresh token policy |
| Logout only exits Portal | OIDC logout handler not configured or OP not supported | Check end_session_endpoint and post-logout URI |
| Metadata returns internal hostname | Forwarded headers or issuer misconfigured | Fix proxy trust and public issuer |

## 18. Operations and Observability

Monitor the following metrics:

- Discovery success/failure and latency.
- Login success/failure by registration ID.
- Authorization callback errors: state, code exchange, redirect.
- Token endpoint latency and error codes.
- ID Token/JWKS validation failures.
- UserInfo latency and errors.
- Authorized client refresh success/failure.
- Protected API 401/403 responses.
- Logout success and session cleanup.

Logs should record correlation ID, registration ID, issuer, endpoint, error code, and processing duration. Do not log authorization codes, raw state unless necessary, ID Tokens, Access Tokens, Refresh Tokens, client secrets, or session cookies.

### 18.1. Key Rotation

The Authorization Server may rotate signing keys and publish multiple public keys in JWKS during the transition period. The OAuth2 Client must use the discovered JWKS URI and handle kid appropriately. Do not pin a static public key if the architecture requires automatic rotation.

### 18.2. Metadata Caching

Discovery and JWKS are fetched over the network. Put an appropriate cache/refresh policy in place to avoid calling metadata too frequently while still updating keys during rotation. Do not cache metadata indefinitely or reuse one metadata response for another issuer.

## 19. Production Deployment Checklist

1. **Issuer:** configure canonical, HTTPS issuer consistent with metadata/ID Token.
2. **Discovery:** use trusted issuer URIs; verify metadata issuer and endpoints.
3. **Registration:** client is registered, redirect URI is an exact match.
4. **Credentials:** secrets are retrieved from a secret manager; public clients have no dummy secrets.
5. **Grant:** use Authorization Code Flow; PKCE for public clients and per policy for confidential clients.
6. **Scopes:** request only necessary scopes; consent is handled at the OP.
7. **Callback:** state, nonce, session, and redirect URI are validated.
8. **Tokens:** distinguish ID Token, Access Token, and Refresh Token.
9. **UserInfo:** use Access Token, check sub consistency and claims policy.
10. **API calls:** use OAuth2AuthorizedClientManager; do not manually assemble Bearer headers from arbitrary tokens.
11. **Audience:** Access Tokens are issued for the correct resource server.
12. **Logout:** local logout and RP-Initiated Logout are clearly separated.
13. **Proxy:** forwarded headers are trusted only from authenticated proxies.
14. **Multi-tenant:** issuer allowlist, registration isolation, and per-issuer cache keys.
15. **Observability:** do not log credentials/tokens; monitor discovery/login/token errors.
16. **Resilience:** runbooks exist for timeouts, DNS, TLS, JWKS rotation, and provider outages.
17. **Testing:** end-to-end tests cover login, tokens, API calls, refresh, and logout.

## 20. Exercises and Self-Assessment Questions

**Exercise A — Configure issuer discovery.** Create a Spring Boot Portal using the Authorization Server's issuer-uri. Declare an appropriate registration ID, client ID, redirect URI, and scopes.

**Exercise B — Discovery paths.** For issuer https://login.example.com/tenant-a, list the discovery endpoints that ClientRegistrations.fromIssuerLocation may try and explain how it differs from fromOidcIssuerLocation.

**Exercise C — Authorization Code Flow.** Diagram the flow from /oauth2/authorization/portal to the callback, code exchange, ID Token validation, and session creation.

**Exercise D — Token usage.** Explain why the Portal uses an Access Token to call the Orders API and does not send the ID Token instead.

**Exercise E — UserInfo.** Write a controller that receives an OidcUser, returning (iss, sub) and several profile claims. Add handling for when the UserInfo sub mismatches.

**Exercise F — WebClient.** Configure OAuth2AuthorizedClientManager supporting authorization_code, refresh_token, and client_credentials; write a service that calls an API.

**Exercise G — Multi-tenant.** The Portal supports two issuers. Design an issuer allowlist, two registrations, and a way to prevent Tenant A's authorized client from being used for Tenant B.

**Exercise H — Reverse proxy.** The Authorization Server runs internal HTTP but public HTTPS. Analyze the impact of forwarded headers on the issuer, metadata, and callback URLs.

**Review questions:**

1. How does an Issuer Identifier differ from a client ID and a registration ID?
2. What endpoints does provider metadata publish?
3. Does discovery automatically register a client?
4. Under which Spring Boot property branch is issuer-uri declared?
5. How does fromIssuerLocation differ from fromOidcIssuerLocation?
6. Why must the metadata issuer match the configured issuer?
7. What is the role of /oauth2/authorization/{registrationId}?
8. What is Spring Security's default callback?
9. Which parts of the flow do state and nonce protect?
10. How do an ID Token and an Access Token differ?
11. When does OidcUserService call UserInfo?
12. Why use (iss, sub) instead of email as an identifier?
13. What operations does OAuth2AuthorizedClientManager manage?
14. When should you use DefaultOAuth2AuthorizedClientManager vs. AuthorizedClientServiceOAuth2AuthorizedClientManager?
15. Why does local logout not equate to OP logout or token revocation?
16. How do you prevent SSRF through issuer discovery?

## 21. References

- [Spring Boot — OAuth2 Client](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [Spring Security — OAuth2 Client Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — OAuth2 Client Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security — ClientRegistrations API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/registration/ClientRegistrations.html)
- [Spring Security — OIDC Client-Initiated Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)

**Takeaway:** Spring OAuth2 Client can initialize a ClientRegistration from a trusted issuer using issuer-uri. Discovery supplies endpoints and key metadata; it does not replace client registration. OAuth2 Login uses the Authorization Code Flow, handles state/nonce, and verifies the ID Token. When calling APIs, use an Access Token managed through OAuth2AuthorizedClientManager; never use an ID Token in place of an Access Token. Local logout, OP logout, and token revocation are separate actions. With multi-tenancy, manage issuers via an allowlist and keep registrations, tokens, caches, and identities within the proper tenant boundary.

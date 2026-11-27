# Customizing Metadata Converters, Providers, and Registration Policies

OpenID Connect Dynamic Client Registration (DCR) allows a Relying Party (RP) to send its own metadata to an OpenID Provider (OP) to obtain a `client_id` and the details needed for subsequent interactions. Instead of manually entering client configurations for every deployment, organizations can automate onboarding, manage redirect URIs, token endpoint authentication methods, scopes, and platform-specific metadata.

In Spring Authorization Server, DCR is implemented via the **OpenID Connect Client Registration Endpoint**. This endpoint is disabled by default. When enabled, `OidcClientRegistrationEndpointConfigurer` lets you customize request converters, authentication providers, response handlers, and error handlers. The default providers themselves have dedicated converters to map `OidcClientRegistration` to `RegisteredClient` and back.

**Customizing metadata converters, providers, and registration policies** means designing all three parts consistently: the data clients send in, how the Authorization Server persists that data into a registration, and how the server returns the exact same metadata in responses/Client Read. At the same time, the server must verify registration permissions, constrain accepted metadata, and protect endpoints from unauthorized clients.

This lesson belongs to the **Dynamic Client Registration** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, focusing on designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.

After this lesson, you will be able to:

- Explain the OIDC Dynamic Client Registration and Client Read flows.
- Enable `clientRegistrationEndpoint` using `OidcClientRegistrationEndpointConfigurer`.
- Distinguish HTTP request converters from provider-level metadata converters.
- Customize `OidcClientRegistrationAuthenticationProvider` and `OidcClientConfigurationAuthenticationProvider`.
- Map extended metadata into `ClientSettings` and return it via Client Registration/Client Read.
- Preserve default validation for redirect URIs, post-logout redirect URIs, and `jwks_uri`.
- Build allowlists for scopes, grant types, and token endpoint authentication methods.
- Distinguish Initial Access Tokens from Registration Access Tokens.
- Design protected registration policies, quotas, auditing, secret handling, and client lifecycles.
- Test registration, read-back, metadata round-trips, and rejection scenarios.

## 1. What Problem Does Dynamic Client Registration Solve?

An Authorization Server typically needs to store information for each OAuth/OIDC client:

- `client_id` and optionally `client_secret`;
- redirect URIs and post-logout redirect URIs;
- grant types and response types;
- token endpoint authentication method;
- scopes the client is permitted to request;
- JWK Set URL or ID Token signing algorithms;
- display name, logo, contact info, and other metadata.

If every client is created manually, onboarding many tenants, deployment environments, or SaaS applications can be slow and error-prone. DCR allows clients/developers to send metadata to the Registration Endpoint so the OP can evaluate it and create a registration.

General flow:

~~~mermaid
sequenceDiagram
    autonumber
    participant D as Client Developer / Registrar
    participant AS as Authorization Server
    participant DB as RegisteredClientRepository
    participant C as OIDC Client

    D->>AS: Request Initial Access Token
    AS-->>D: Initial Access Token (client.create)
    D->>AS: POST Client Registration + Bearer token
    AS->>AS: Authenticate registrar and validate metadata
    AS->>AS: OidcClientRegistration -> RegisteredClient
    AS->>DB: Save RegisteredClient
    AS-->>D: client_id, credentials, metadata, registration_access_token, registration_client_uri
    C->>AS: GET registration_client_uri + Registration Access Token
    AS->>DB: Find registration and verify read permission
    AS-->>C: Client Registration metadata
~~~

DCR can be deployed using either an open registration model or a protected registration model. In enterprise environments, protected registration is usually more appropriate: only registrars/developers issued an Initial Access Token have permission to create clients. DCR does not mean every Internet user is allowed to create new clients.

### 1.1. DCR Is Not Client Authentication

Three distinct activities:

| Activity | Purpose | Related Credential/Permission |
| --- | --- | --- |
| Dynamic Client Registration | Creates a new registration for a client. | Initial Access Token with `client.create` permission in Spring Authorization Server configuration. |
| Client Read / Client Configuration | Reads metadata of an existing registration. | Registration Access Token bound to the client and `client.read` permission. |
| OAuth Client Authentication | Authenticates the client when calling Token/Introspection/Revocation Endpoints. | `client_secret_basic`, `private_key_jwt`, mTLS, or registered method. |

A new client receiving a `client_id` via DCR does not mean it is already authenticated on token requests. The client's authentication method and grant types must still be configured, stored, and enforced per policy.

## 2. Client Registration Endpoint and Client Read Endpoint

OIDC Dynamic Client Registration 1.0 defines two key operations:

- **Client Registration Request:** client sends an HTTP POST with metadata to register.
- **Client Read Request:** client sends an HTTP GET to the Client Configuration Endpoint to read registered metadata.

In Spring Authorization Server 1.5.8, `OidcClientRegistrationEndpointFilter` handles both Client Registration requests and Client Read requests. By default, the filter uses two providers:

| Provider | Role |
| --- | --- |
| `OidcClientRegistrationAuthenticationProvider` | Handles creating registrations, converting metadata into `RegisteredClient`, saving the client, and building the response. |
| `OidcClientConfigurationAuthenticationProvider` | Handles Client Read, looking up the existing registration and converting it into an `OidcClientRegistration` response. |

The default Client Registration Endpoint is `/connect/register`; it can be changed via `AuthorizationServerSettings.oidcClientRegistrationEndpoint(...)`.

**Do not confuse Client Read with full Dynamic Client Management.** The DCR/Client Configuration specifications include broader registration management operations, whereas the Spring Authorization Server 1.5.8 endpoint described here handles registration and reading details. Do not assume PUT/PATCH/DELETE or full RFC 7592 lifecycle operations are automatically enabled just because the registration endpoint works.

## 3. Enabling the Client Registration Endpoint in Spring Authorization Server

OIDC endpoints are activated via `oidc(...)`. The Client Registration Endpoint must be enabled explicitly using `clientRegistrationEndpoint(...)`.

Example for Spring Authorization Server 1.5.x:

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
            authorizationServer
                .oidc(oidc ->
                    oidc.clientRegistrationEndpoint(Customizer.withDefaults())
                )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        );

    return http.build();
}
~~~

This covers enabling the endpoint. A real application also needs `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, `AuthorizationServerSettings`, JWK source, and corresponding filter chains.

### 3.1. JwtDecoder Is a Required Dependency

Spring Authorization Server uses OAuth2 Resource Server support to verify Bearer access tokens at the Client Registration/Client Read Endpoint. Under the current configuration, a `JwtDecoder` bean is required:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Related imports:

~~~java
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import com.nimbusds.jose.jwk.source.JWKSource;
~~~

If the endpoint returns 401 even though converters/providers are configured properly, check the Bearer token, `JwtDecoder`, issuer/signature validation, and the active filter chain.

### 3.2. Configuring the Endpoint Path

You can override the default path:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://login.example.com")
        .oidcClientRegistrationEndpoint("/connect/v1/register")
        .build();
}
~~~

Discovery metadata must publish the accurate `registration_endpoint`. Clients should use the OP-published URL or a trusted configured URL; never assemble host/path from untrusted data.

## 4. Extension Points of OidcClientRegistrationEndpointConfigurer

`OidcClientRegistrationEndpointConfigurer` configures `OidcClientRegistrationEndpointFilter` and exposes extension points:

~~~mermaid
flowchart LR
    HTTP["HTTP POST / GET"] --> CONV["Request Converter"]
    CONV --> AUTH["OidcClientRegistrationAuthenticationToken"]
    AUTH --> PROVIDERS["AuthenticationManager"]
    PROVIDERS --> REG["Registration Provider"]
    PROVIDERS --> READ["Configuration Provider"]
    REG --> SAVE["RegisteredClientRepository"]
    SAVE --> RESPONSE["Client Registration Response"]
    READ --> RESPONSE
    RESPONSE --> SUCCESS["Client Registration Response Handler"]
    PROVIDERS -->|OAuth error| ERROR["Error Response Handler"]
~~~

| API | Role | When to Customize |
| --- | --- | --- |
| `clientRegistrationRequestConverter(...)` | Adds an `AuthenticationConverter` to turn an HTTP request into an `OidcClientRegistrationAuthenticationToken`. | When needing a special request format or adding controlled context. |
| `clientRegistrationRequestConverters(...)` | Accesses the list of default and added converters. | When adjusting ordering or replacing a specific converter. |
| `authenticationProvider(...)` | Adds a provider to handle authentication requests. | When having a dedicated provider for a registration type. |
| `authenticationProviders(...)` | Accesses the default provider list to configure/add/remove providers. | When attaching validators or metadata converters to default providers. |
| `clientRegistrationResponseHandler(...)` | Handles successful responses for Registration or Client Read. | When needing custom response handling/auditing. |
| `errorResponseHandler(...)` | Handles OAuth error responses. | When needing policy-specific telemetry or error formatting. |

By default, the filter uses:

- `OidcClientRegistrationAuthenticationConverter`;
- `OidcClientRegistrationAuthenticationProvider`;
- `OidcClientConfigurationAuthenticationProvider`;
- an internal success handler returning `OidcClientRegistration`;
- an internal failure handler returning `OAuth2Error`.

**You do not need to write a new request converter just to persist extra metadata.** If JSON is already parsed into `OidcClientRegistration` with extended claims, you can keep the default request converter and customize the provider-level metadata converters. This is simpler and has less risk of breaking protocol parsing.

## 5. Distinguishing Converter Layers

There are several converters in DCR; they operate at different data boundaries.

| Converter | Conversion Direction | Where Used |
| --- | --- | --- |
| `OidcClientRegistrationAuthenticationConverter` | `HttpServletRequest` → `OidcClientRegistrationAuthenticationToken` | Endpoint filter, pre-processing. |
| `OidcClientRegistrationHttpMessageConverter` | JSON/map ↔ `OidcClientRegistration` | HTTP message serialization/deserialization. |
| `OidcClientRegistrationRegisteredClientConverter` | `OidcClientRegistration` → `RegisteredClient` | Registration provider, building client to save. |
| `RegisteredClientOidcClientRegistrationConverter` | `RegisteredClient` → `OidcClientRegistration` | Registration response and Client Read response. |

You can visualize this with a diagram:

~~~mermaid
flowchart TD
    JSON["JSON metadata from client"] --> HTTP["HTTP Message Converter"]
    HTTP --> OIDC["OidcClientRegistration"]
    OIDC --> REGCONV["OidcClientRegistrationRegisteredClientConverter"]
    REGCONV --> RC["RegisteredClient"]
    RC --> REPO["RegisteredClientRepository"]
    REPO --> BACK["RegisteredClientOidcClientRegistrationConverter"]
    BACK --> RESPONSE["OidcClientRegistration response"]
    RESPONSE --> JSONOUT["JSON returned to client"]
~~~

The two provider-level converters are the ones typically extended when storing custom metadata:

- `setRegisteredClientConverter(...)` takes an `OidcClientRegistration` → `RegisteredClient` converter.
- `setClientRegistrationConverter(...)` takes a `RegisteredClient` → `OidcClientRegistration` converter.

If custom metadata is only parsed but not stored, it is lost after registration finishes. If metadata is stored but the response converter does not read it back, it disappears from responses and Client Read. Both directions must perform a proper **round-trip**.

## 6. Persisting Custom Metadata in RegisteredClient

`RegisteredClient` has standard properties such as `clientId`, `clientSecret`, redirect URIs, grant types, scopes, and client authentication methods. Some OIDC metadata such as `logo_uri` or `contacts` have no dedicated corresponding properties on `RegisteredClient`.

An appropriate approach is storing extended metadata in `ClientSettings` using custom setting keys. In this lesson's example, `logo_uri` and `contacts` are client metadata defined by OIDC DCR; they are handled as custom settings with respect to the `RegisteredClient` model because that model lacks dedicated properties for them. Organization-specific fields such as `tenant_code` must be verified or assigned by the server, never trusted as self-declared claims.

Illustrative keys:
- `logo_uri`: client logo URL;
- `contacts`: operational contact list;
- `tenant_code`: internal tenant code issued or verified by the server;
- `registration_source`: onboarding source determined by the server.

Do not store arbitrary sensitive values in publicly exposed metadata. Keep only necessary fields and decide explicitly which fields are returned to clients.

### 6.1. Metadata Converter from OidcClientRegistration to RegisteredClient

The inbound converter should delegate to the standard converter first, then add allowlisted settings:

~~~java
public final class CustomRegisteredClientConverter
        implements Converter<OidcClientRegistration, RegisteredClient> {

    private static final Set<String> CUSTOM_METADATA =
        Set.of("logo_uri", "contacts");

    private final OidcClientRegistrationRegisteredClientConverter delegate =
        new OidcClientRegistrationRegisteredClientConverter();

    @Override
    public RegisteredClient convert(OidcClientRegistration registration) {
        RegisteredClient registeredClient = this.delegate.convert(registration);

        ClientSettings.Builder settings = ClientSettings.withSettings(
            registeredClient.getClientSettings().getSettings()
        );

        registration.getClaims().forEach((name, value) -> {
            if (CUSTOM_METADATA.contains(name) && value != null) {
                settings.setting(name, value);
            }
        });

        return RegisteredClient.from(registeredClient)
            .clientSettings(settings.build())
            .build();
    }
}
~~~

The snippet above illustrates the storage mechanism. Before invoking the converter, a validator must verify the types and contents of `logo_uri` and `contacts`; never trust a value merely because it is in JSON metadata. If `contacts` must be a list of strings, reject objects or other types rather than performing unchecked casts.

### 6.2. Metadata Converter from RegisteredClient to OidcClientRegistration

The outbound converter starts from the standard response and then appends stored metadata:

~~~java
public final class CustomClientRegistrationConverter
        implements Converter<RegisteredClient, OidcClientRegistration> {

    private static final Set<String> CUSTOM_METADATA =
        Set.of("logo_uri", "contacts");

    private final RegisteredClientOidcClientRegistrationConverter delegate =
        new RegisteredClientOidcClientRegistrationConverter();

    @Override
    public OidcClientRegistration convert(RegisteredClient registeredClient) {
        OidcClientRegistration base = this.delegate.convert(registeredClient);
        Map<String, Object> claims = new HashMap<>(base.getClaims());

        ClientSettings settings = registeredClient.getClientSettings();
        for (String name : CUSTOM_METADATA) {
            Object value = settings.getSetting(name);
            if (value != null) {
                claims.put(name, value);
            }
        }

        return OidcClientRegistration.withClaims(claims).build();
    }
}
~~~

This converter is used for both post-registration responses and Client Read. Use `new HashMap<>(base.getClaims())` to retain standard metadata produced by the default converter; never build a new map containing only custom fields, as that would drop `client_id`, `redirect_uris`, `grant_types`, and other fields.

### 6.3. Registering Both Converters on the Providers

Configure `OidcClientRegistrationAuthenticationProvider` and `OidcClientConfigurationAuthenticationProvider`:

~~~java
public final class CustomClientMetadataConfig {

    public static Consumer<List<AuthenticationProvider>>
            configureCustomClientMetadataConverters() {

        Converter<OidcClientRegistration, RegisteredClient> toRegisteredClient =
            new CustomRegisteredClientConverter();

        Converter<RegisteredClient, OidcClientRegistration> toClientRegistration =
            new CustomClientRegistrationConverter();

        return providers -> providers.forEach(provider -> {
            if (provider instanceof OidcClientRegistrationAuthenticationProvider registrationProvider) {
                registrationProvider.setRegisteredClientConverter(toRegisteredClient);
                registrationProvider.setClientRegistrationConverter(toClientRegistration);
            }

            if (provider instanceof OidcClientConfigurationAuthenticationProvider configurationProvider) {
                configurationProvider.setClientRegistrationConverter(toClientRegistration);
            }
        });
    }
}
~~~

The providers have distinct responsibilities:

- Registration provider uses the inbound converter to create `RegisteredClient`.
- Registration provider uses the outbound converter to build the response after POST.
- Configuration provider uses the outbound converter to return the response for Client Read.

If you configure the converter only on the Registration provider, the client may receive metadata immediately after POST yet fail to see it when calling GET registration later.

## 7. Configuring the Endpoint with Metadata Converters

You can wire the provider customizer into `authenticationProviders(...)`:

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
            authorizationServer.oidc(oidc ->
                oidc.clientRegistrationEndpoint(endpoint ->
                    endpoint.authenticationProviders(
                        CustomClientMetadataConfig
                            .configureCustomClientMetadataConverters()
                    )
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        );

    return http.build();
}
~~~

This example focuses on attaching metadata converters. Add the organization's validator policies to the same consumer or compose consumers in an explicit order. Never create a second Authorization Server filter chain with the same matcher just to install a converter.

## 8. Customizing AuthenticationProvider and Validation Policy

`OidcClientRegistrationAuthenticationProvider` can be customized via:

- `setRegisteredClientConverter(...)`;
- `setClientRegistrationConverter(...)`;
- `setAuthenticationValidator(...)`;
- `setPasswordEncoder(...)`.

`OidcClientConfigurationAuthenticationProvider` exposes `setClientRegistrationConverter(...)` to customize data returned on Client Read.

Validators receive `OidcClientRegistrationAuthenticationContext` and must throw `OAuth2AuthenticationException` when request metadata is invalid.

### 8.1. Default Validators in Spring Authorization Server 1.5.8

`OidcClientRegistrationAuthenticationValidator` checks the following fields:

| Validator | Meaning |
| --- | --- |
| `DEFAULT_REDIRECT_URI_VALIDATOR` | Rejects redirect URIs with fragments, missing schemes, or unsafe schemes such as `javascript:`, `data:`, and `vbscript:`. |
| `DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR` | Applies similar rules to post-logout redirect URIs. |
| `DEFAULT_JWK_SET_URI_VALIDATOR` | Requires `jwks_uri` to use HTTPS. |
| `DEFAULT_SCOPE_VALIDATOR` | Rejects requests with non-empty scope values under default policy. |

The `SIMPLE_*_VALIDATOR` constants exist for legacy behavior compatibility:

- `SIMPLE_REDIRECT_URI_VALIDATOR` checks primarily for fragments.
- `SIMPLE_POST_LOGOUT_REDIRECT_URI_VALIDATOR` is similarly permissive.
- `SIMPLE_JWK_SET_URI_VALIDATOR` performs no HTTPS validation.
- `SIMPLE_SCOPE_VALIDATOR` accepts any scope.

`SIMPLE_*` validators can allow dangerous metadata such as unsafe redirect URIs, `jwks_uri` pointing to internal endpoints, or arbitrary scopes. Use them only when there is a specific compatibility requirement, a risk assessment, and explicit compensating controls.

### 8.2. Why Not Use SIMPLE_SCOPE_VALIDATOR Mechanically?

In Spring Authorization Server 1.5.8, `DEFAULT_SCOPE_VALIDATOR` rejects non-empty scopes. If your deployment wants clients to register scopes, replace the scope validation piece with your own policy. Example allowing a bounded set of scopes:

~~~java
private static final Set<String> ALLOWED_SCOPES =
    Set.of("openid", "profile", "email", "orders.read");

private static Consumer<OidcClientRegistrationAuthenticationContext>
        allowedScopeValidator() {

    return context -> {
        OidcClientRegistration registration =
            context.getAuthentication().getClientRegistration();

        List<String> requestedScopes = registration.getScopes();
        if (requestedScopes == null || requestedScopes.isEmpty()) {
            return;
        }

        if (!ALLOWED_SCOPES.containsAll(requestedScopes)) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error(
                    "invalid_client_metadata",
                    "The registration request contains an unsupported scope",
                    null
                )
            );
        }
    };
}
~~~

This example permits scopes in an allowlist. In multi-tenant systems, the allowlist can be computed per registrar, software statement, or tenant policy; avoid a single global list if different registrar groups have different permissions.

### 8.3. Combining Default URI Validators with a Scope Allowlist

When calling `setAuthenticationValidator(...)`, the new validator replaces the existing one. Therefore, compose the safe validators you need to retain:

~~~java
private static Consumer<List<AuthenticationProvider>>
        configureRegistrationValidators() {

    Consumer<OidcClientRegistrationAuthenticationContext> validator =
        OidcClientRegistrationAuthenticationValidator.DEFAULT_REDIRECT_URI_VALIDATOR
            .andThen(
                OidcClientRegistrationAuthenticationValidator
                    .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR
            )
            .andThen(
                OidcClientRegistrationAuthenticationValidator
                    .DEFAULT_JWK_SET_URI_VALIDATOR
            )
            .andThen(allowedScopeValidator())
            .andThen(clientCapabilityValidator())
            .andThen(customMetadataValidator());

    return providers -> providers.forEach(provider -> {
        if (provider instanceof OidcClientRegistrationAuthenticationProvider registrationProvider) {
            registrationProvider.setAuthenticationValidator(validator);
        }
    });
}
~~~

Here `DEFAULT_SCOPE_VALIDATOR` is omitted because that validator rejects every non-empty scope. Scopes are validated by the dedicated allowlist. The strict URI validators are preserved.

The two configurations can be composed:

~~~java
.authenticationProviders(
    configureRegistrationValidators()
        .andThen(
            CustomClientMetadataConfig
                .configureCustomClientMetadataConverters()
        )
)
~~~

Ensure each provider is configured once per concern and avoid having a later customizer overwrite a validator set earlier.

## 9. Policies for Grant Types, Response Types, and Authentication Methods

Scopes are not the only metadata requiring control. Clients can send `grant_types`, `response_types`, and `token_endpoint_auth_method`; these values directly govern how the client is allowed to operate.

Example policy:

| Metadata | Illustrative Policy |
| --- | --- |
| `grant_types` | Allow only `authorization_code`, `refresh_token`, and `client_credentials` according to client type. |
| `response_types` | For web OIDC clients, allow only `code`. |
| `token_endpoint_auth_method` | Allow `client_secret_basic`, `private_key_jwt`, or `none` depending on client type. |
| `redirect_uris` | Per-client exact allowlist; HTTPS for web clients, loopback exceptions per native-app policy. |
| `post_logout_redirect_uris` | Dedicated exact allowlist; never automatically reuse redirect URIs. |
| `jwks_uri` | HTTPS and controlled host/network policy. |
| `scope` | Allowlist per tenant, product, or registrar. |

An additional validator can read metadata via `context.getAuthentication().getClientRegistration()` and verify grants/auth methods before the provider saves the client:

~~~java
private static final Set<String> ALLOWED_GRANTS =
    Set.of("authorization_code", "refresh_token");

private static final Set<String> ALLOWED_AUTH_METHODS =
    Set.of("client_secret_basic", "private_key_jwt", "none");

private static Consumer<OidcClientRegistrationAuthenticationContext>
        clientCapabilityValidator() {

    return context -> {
        OidcClientRegistration registration =
            context.getAuthentication().getClientRegistration();

        List<String> grantTypes = registration.getGrantTypes();
        if (grantTypes != null && !ALLOWED_GRANTS.containsAll(grantTypes)) {
            throw invalidClientMetadata("Unsupported grant_types");
        }

        String authenticationMethod =
            registration.getTokenEndpointAuthenticationMethod();

        if (authenticationMethod != null
                && !ALLOWED_AUTH_METHODS.contains(authenticationMethod)) {
            throw invalidClientMetadata(
                "Unsupported token_endpoint_auth_method"
            );
        }
    };
}

private static OAuth2AuthenticationException invalidClientMetadata(
        String description) {

    return new OAuth2AuthenticationException(
        new OAuth2Error("invalid_client_metadata", description, null)
    );
}
~~~

This is an illustrative policy. In production, allowlists must depend on the registrar/client class. For example, `none` is only for public clients; `client_secret_basic` and `private_key_jwt` are for confidential clients per the corresponding credential issuance workflow. Never let clients self-declare `token_endpoint_auth_method=none` to bypass authentication if the organization only accepts confidential clients.

### 9.1. Enforcing PKCE for Public Clients

For public clients, require PKCE for the Authorization Code flow. When converting metadata to `RegisteredClient`, enforce policy via `ClientSettings.requireProofKey(true)` for clients classified as public. Do not rely solely on unverified `token_endpoint_auth_method` metadata; combine application type/registrar policy and validation.

If public clients are not allowed to use `client_credentials`, reject that grant in the registration validator. Dropping a grant from the response metadata while still persisting it in `RegisteredClient` creates an inconsistent configuration.

## 10. Building Validators for Custom Metadata

Custom metadata is also untrusted input. Examples with `logo_uri` and `contacts`:

| Field | Recommended Validation |
| --- | --- |
| `logo_uri` | Must be an HTTPS URL, host/domain restricted per policy, length-bounded, and free of dangerous schemes. |
| `contacts` | Must be a list of strings, bounded in count and length, with email/URI formats normalized as required by the app. |
| `tenant_code` | Never accept privileged tenants self-declared by the client; derive from registrar identity or verify tenant membership. |
| `software_id` | Accept only values in the organization's trusted software catalog. |

Example custom metadata validation:

~~~java
private static Consumer<OidcClientRegistrationAuthenticationContext>
        customMetadataValidator() {

    return context -> {
        OidcClientRegistration registration =
            context.getAuthentication().getClientRegistration();

        String logoUri = registration.getClaimAsString("logo_uri");
        if (logoUri != null) {
            URI uri;
            try {
                uri = URI.create(logoUri);
            }
            catch (IllegalArgumentException ex) {
                throw invalidClientMetadata("Invalid logo_uri");
            }

            if (!"https".equalsIgnoreCase(uri.getScheme())
                    || uri.getHost() == null
                    || uri.getUserInfo() != null) {
                throw invalidClientMetadata("Unsafe logo_uri");
            }
        }

        Object contacts = registration.getClaims().get("contacts");
        if (contacts != null) {
            if (!(contacts instanceof List<?> values)
                    || values.size() > 10
                    || values.stream().anyMatch(value ->
                        !(value instanceof String text)
                            || text.isBlank()
                            || text.length() > 254)) {
                throw invalidClientMetadata("Invalid contacts");
            }
        }
    };
}
~~~

This example checks only basic structure. If the server or admin console fetches logos from the URL, add SSRF defenses: block private/loopback/link-local IPs, control DNS rebinding and redirects, and restrict egress, timeouts, and download size. A safer approach is displaying logos only from allowlisted hosts or proxying through a controlled media service.

## 11. Registering the Registrar Client

In Spring Authorization Server, a pre-registered client acts as the registrar calling the Client Registration Endpoint.

The registrar needs:

- `client_credentials` grant to obtain access tokens.
- `client.create` scope to create registrations.
- `client.read` scope if it needs to read back registrations.

Example:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder) {
    RegisteredClient registrar = RegisteredClient
        .withId("registrar-internal-id")
        .clientId("client-registrar")
        .clientSecret(passwordEncoder.encode("replace-with-secret"))
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();

    return new InMemoryRegisteredClientRepository(registrar);
}
~~~

The example uses an in-memory repository for clarity. Production should use a persistent `RegisteredClientRepository` and proper secret management; never hardcode secrets in source or public configuration.

### 11.1. Obtaining an Initial Access Token

Registration requests require an Initial Access Token with the exact `client.create` scope per Spring Authorization Server configuration. The token must not contain other scopes.

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <BASE64_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
~~~

The request above fetches an access token from the registrar client. In Spring Authorization Server 1.5.8, the Initial Access Token used for registration is a one-time token: after registration succeeds, this token is invalidated. Do not reuse that token for multiple clients.

### 11.2. Initial Access Token vs. Registration Access Token

| Token | Issued To | Used To | Scope |
| --- | --- | --- | --- |
| Initial Access Token | Approved registrar/developer. | Call the Registration Endpoint to create a new client. | Can be scoped to `client.create`; in the SAS guide the token has only this scope and is single-use. |
| Registration Access Token | Newly registered client. | Call the Client Configuration Endpoint to read metadata of that exact registration. | Bound to one specific client; not a token for creating other clients. |

Do not return the Registration Access Token to end users or log it in application logs. It is a bearer credential for reading registration details and must be protected like a secret.

## 12. Sending a Client Registration Request

Example POST request:

~~~http
POST /connect/register HTTP/1.1
Host: login.example.com
Authorization: Bearer <INITIAL_ACCESS_TOKEN>
Content-Type: application/json
Accept: application/json

{
  "client_name": "orders-portal",
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "redirect_uris": [
    "https://orders.example.com/login/oauth2/code/portal"
  ],
  "post_logout_redirect_uris": [
    "https://orders.example.com/signed-out"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile email orders.read",
  "logo_uri": "https://orders.example.com/assets/logo.png",
  "contacts": [
    "platform@example.com"
  ]
}
~~~

A successful response may contain:

- `client_id`;
- `client_secret` if the client uses a method needing a secret;
- OP-accepted metadata;
- `registration_access_token`;
- `registration_client_uri`.

The OP may reject, substitute, or supplement certain metadata per specification and policy. Clients must use the values returned by the server rather than assuming all requested values were kept intact.

### 12.1. Client Read

The client uses `registration_client_uri` and the Registration Access Token to read the registration:

~~~http
GET <REGISTRATION_CLIENT_URI_FROM_RESPONSE> HTTP/1.1
Authorization: Bearer <REGISTRATION_ACCESS_TOKEN>
Accept: application/json
~~~

In Spring Authorization Server, Client Read requires an access token with the `client.read` scope. The client must use the exact `registration_client_uri` returned by the server; never build the URL from client ID or hostname.

The Client Read response should retain both standard metadata and persisted custom metadata. Do not return `registration_access_token` as a routine read field unless required by protocol/implementation.

## 13. Customizing Password Encoder and Client Secrets

`OidcClientRegistrationAuthenticationProvider` supports `setPasswordEncoder(...)` to encode client secrets generated during registration. If not explicitly configured, the provider uses `PasswordEncoderFactories.createDelegatingPasswordEncoder()`.

Example wiring an encoder:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
~~~

If a custom provider or custom registration workflow generates client secrets itself, encode them before saving and return the plaintext secret only once per the response contract. Never store plaintext secrets in `ClientSettings`, custom metadata, audit logs, or Client Read responses.

For public clients using `token_endpoint_auth_method=none`, never issue a client secret as if it were a confidential client. For `private_key_jwt`, store the JWK Set URL or required key reference per policy; never accept a client's private key as public metadata.

## 14. Security Policies for Dynamic Client Registration

DCR can create clients capable of requesting tokens for the organization's APIs. Therefore, registration policies must constrain who can register and what clients are allowed to do.

### 14.1. Prefer Protected Registration

In protected registration:

- Initial Access Tokens are issued only to approved registrars/developers.
- Tokens have short TTLs and minimal `client.create` scope.
- Tokens should be single-use when the registration model permits.
- Registrars have quotas per tenant/team.
- Every registration creation emits an audit event and request origin.

Open registration may be needed in certain public ecosystems, yet requires rate limits, abuse detection, quotas, reviews, and client revocation policies. Never enable the endpoint just because it exists in the OIDC specification.

### 14.2. Redirect URI

Redirect URIs are a critical security boundary. You should:

- Reject URIs missing schemes, URIs with fragments, and dangerous schemes.
- Enforce HTTPS for web clients.
- Allow loopback HTTP only for native apps per explicit policy.
- Use exact redirect URI matching when handling authorization requests.
- Disallow wildcards or prefix matching.
- Verify host/domain ownership if required by the registration model.

The default validator in SAS 1.5.8 checks basic safety conditions. It does not replace domain ownership verification or exact-match validation at the Authorization Endpoint.

### 14.3. JWK Set URI and SSRF

The default validator requires `jwks_uri` to use HTTPS. This alone is insufficient for all deployments: an HTTPS URL can still point to internal addresses or metadata services on private networks.

If the server fetches JWK Sets from client-provided URLs, you need:

- Domain allowlists or trusted domains per registrar.
- Blocking loopback, private, link-local, and special-purpose IPs.
- DNS resolution checks and DNS rebinding protections.
- Limits on redirects, timeouts, response size, and refresh frequency.
- Blocking URLs pointing to cloud metadata services or internal control planes.

### 14.4. Grant Types and Scopes

Never let clients self-grant permissions. `scope` in registration metadata describes what the client wishes to use; the OP must restrict it per registrar, tenant, product, and API policy.

Similarly, `grant_types` should not be accepted unconditionally. For example, public clients may be restricted to Authorization Code + PKCE; never grant `client_credentials` to an SPA.

### 14.5. Logos and Display Information

Metadata fields `client_name`, `logo_uri`, `policy_uri`, and `contacts` may appear on consent pages or admin UIs. A malicious client could impersonate a brand, use misleading logos, or supply URLs serving dangerous content.

You should:

- Label untrusted clients clearly.
- Cross-check logo hosts against redirect domains or verified domains.
- Never render client-supplied HTML.
- Escape text and enforce CSP.
- Never automatically fetch logos from arbitrary URLs on the server.
- Review sensitive metadata before displaying it to End-Users.

### 14.6. Quotas, Duplicates, and Lifecycle

Set limits on registrations per registrar/tenant, creation rate, redirect URI count, scope count, and metadata size. Have processes to:

- detect duplicate registrations;
- revoke abusive clients;
- rotate secrets;
- update metadata through supported administrative flows;
- purge expired registrations per policy;
- retain audits and approval sources.

Never use `client_name` as a unique key. Use server-generated client IDs and stable internal IDs.

## 15. Common Pitfalls When Customizing Providers/Converters

### 15.1. Custom Metadata Appears in POST Response but Disappears on GET

The registration provider was configured with inbound/outbound converters, but `OidcClientConfigurationAuthenticationProvider` was not configured with the outbound converter. Share the same `CustomClientRegistrationConverter` across both providers.

### 15.2. Custom Metadata Is Lost After Saving

The inbound converter did not copy claims into `ClientSettings`, or the persistence layer failed to serialize custom settings. Inspect `RegisteredClient` immediately after conversion and read it back from the repository after saving.

### 15.3. Response Metadata Loses Standard Fields

The custom converter built `OidcClientRegistration` from an empty map instead of copying `base.getClaims()`. Delegate to the default converter, copy standard claims, and then add custom keys.

### 15.4. Registration Scopes Are Always Rejected

SAS 1.5.8's `DEFAULT_SCOPE_VALIDATOR` rejects non-empty scopes. If you want to accept scopes, replace that portion with a custom allowlist. Do not jump straight to `SIMPLE_SCOPE_VALIDATOR` without controls.

### 15.5. Redirect URI or jwks_uri Is Rejected

Check scheme, fragment, HTTPS, and domain policy. Never disable strict validators just to make an invalid registration request succeed.

### 15.6. Client Registration Returns 401

Check the Initial Access Token, signature/issuer/audience, TTL, and Bearer header. The token must carry `client.create` per endpoint requirements.

### 15.7. Client Read Returns 401/403

Check the Registration Access Token, `registration_client_uri`, and `client.read` scope. Do not use the Initial Access Token to read the registration after it has been consumed.

### 15.8. Client Read Returns 404 Due to Manually Constructed URL

Use the exact `registration_client_uri` from the response. Do not manually append `/connect/register/{client_id}` when the server already supplied a full URL.

### 15.9. Client Secret Appears in Logs or Plaintext Database

Check `PasswordEncoder`, custom metadata converters, audit serialization, and response logging. Secrets should appear only in the registration response per protocol; never log them or store them in plaintext.

### 15.10. Endpoint Returns 404

Check whether `oidc.clientRegistrationEndpoint(...)` is enabled, whether `AuthorizationServerSettings.oidcClientRegistrationEndpoint(...)` matches the route, whether requests hit the Authorization Server filter chain, and whether proxies route the endpoint.

## 16. Test Matrix

| Scenario | Expected Result |
| --- | --- |
| Registration endpoint disabled | Endpoint is not served as a DCR endpoint. |
| Endpoint enabled and POST sent with valid Initial Access Token | Creates `RegisteredClient` and returns registration response. |
| No access token sent in protected registration | Rejected. |
| Token missing `client.create` | Rejected. |
| Token has extra scopes beyond `client.create` in single-scope flow | Rejected. |
| Reusing an Initial Access Token after successful registration | Rejected because token was invalidated. |
| GET Client Read with valid Registration Access Token and `client.read` | Returns registration metadata. |
| GET with wrong token or insufficient permission | Returns appropriate authentication/authorization error. |
| Redirect URI with fragment or dangerous scheme | Rejected by validator. |
| Invalid post-logout redirect URI | Rejected by validator. |
| `jwks_uri` using HTTP | Rejected by default validator. |
| Scope outside allowlist | Rejected by custom scope validator. |
| Grant type disallowed by policy | Registration rejected. |
| Authentication method disallowed by policy | Registration rejected. |
| `logo_uri` metadata with bad scheme | Rejected by custom metadata validator. |
| `contacts` is an object instead of a list of strings | Rejected by custom metadata validator. |
| Valid custom metadata | Persisted inside `ClientSettings`. |
| Client Registration response | Contains standard metadata and allowed custom metadata. |
| Client Read after persistence | Returns exact saved custom metadata. |
| JDBC repository restart followed by Client Read | Custom metadata remains intact after restart. |
| Custom converter preserves standard claims | `client_id`, grants, redirect URIs, and scopes remain intact. |
| Public client requesting a client secret | Behavior restricted per client policy. |
| Registrar exceeds quota | Rejected and audited. |
| Two concurrent registrations with identical client metadata | Server generates unique client IDs without overwriting the other registration. |
| Client attempts to submit another tenant's `tenant_code` | Validator/registrar policy rejects or overrides with trusted tenant identity. |
| Registration response logging | Never logs client secret or Registration Access Token. |

### 16.1. Integration Test for Metadata Round-Trip

The test should prove data flows through every layer:

1. Send a registration POST containing `logo_uri` and `contacts`.
2. Confirm the POST response contains both fields.
3. Read `registration_client_uri` and `registration_access_token`.
4. Call GET Client Read with that token.
5. Confirm the GET response contains the same custom metadata.
6. Read `RegisteredClient` from the repository and confirm `ClientSettings` holds the custom settings.
7. Restart the application or use a persistent test repository to verify data survives.

Do not test converters in isolation alone. Integration tests must traverse the HTTP message converter, authentication converter, provider, repository, and response handler.

### 16.2. Testing Validators

Write dedicated tests for:

- redirect URI missing a scheme;
- redirect URI with a fragment;
- `javascript:` or `data:` schemes;
- invalid post-logout redirect URI;
- non-HTTPS `jwks_uri`;
- scope outside allowlist;
- grant type outside allowlist;
- unsupported auth method;
- custom metadata with wrong type.

Check both the OAuth error code and that **no new client was persisted** after a failed request.

## 17. Operations and Observability

Monitor the following events:

| Metric/Event | Purpose |
| --- | --- |
| Registration success/failure | Track client creation rates and metadata errors. |
| Registrar client ID | Identify the source of registrations. |
| Registration quota usage | Detect abnormal client creation. |
| Validation error by field | Spot redirect/JWKS/scope policy mismatches. |
| Client Read success/failure | Detect token or permission issues. |
| Custom metadata persistence failure | Detect converter/JDBC serialization errors. |
| Client secret issuance | Track secret issuance counts without logging secret values. |
| Initial Access Token consumption | Detect token replay or abuse. |

Never log Initial Access Tokens, Registration Access Tokens, client secrets, or full registration requests/responses. If correlation is needed, use request ID, registrar client ID, and internal registration ID; never put bearer credentials into metric labels.

In multi-instance environments, all nodes must share a persistent `RegisteredClientRepository` and use identical converter/validator configurations. If node A saves custom settings while node B runs a different converter, Client Read may return incomplete metadata or inconsistent responses.

## 18. Deployment Checklist

- [ ] OIDC Client Registration Endpoint enabled only when there is a business need.
- [ ] Endpoint uses HTTPS and is published via accurate `registration_endpoint`.
- [ ] `JwtDecoder` bean is present to verify Bearer tokens.
- [ ] Registration endpoint is protected by an Initial Access Token or a risk-assessed open registration policy.
- [ ] Registrar has minimal `client.create` scope.
- [ ] Client Read uses only a Registration Access Token with `client.read` scope.
- [ ] Initial Access Token has the exact flow-required scope and is consumed per policy.
- [ ] Initial Access Token is kept distinct from Registration Access Token.
- [ ] Default request converter/provider preserved unless protocol parsing changes are required.
- [ ] Inbound custom converter delegates to standard converter and saves allowlisted custom keys in `ClientSettings`.
- [ ] Outbound custom converter retains standard claims and adds extended metadata.
- [ ] Both `OidcClientRegistrationAuthenticationProvider` and `OidcClientConfigurationAuthenticationProvider` use the appropriate outbound converter.
- [ ] Validators retain `DEFAULT_REDIRECT_URI_VALIDATOR`, `DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR`, and `DEFAULT_JWK_SET_URI_VALIDATOR`.
- [ ] Scopes are validated via an explicit allowlist; never accept arbitrary scopes.
- [ ] `SIMPLE_*_VALIDATOR` is not used without compatibility and risk evaluation.
- [ ] Grant types, response types, and token endpoint auth methods are restricted by client type.
- [ ] PKCE is enforced for public clients per policy.
- [ ] `logo_uri`, `jwks_uri`, and custom URLs have SSRF/phishing defenses.
- [ ] Client secrets are encoded and never logged in plaintext.
- [ ] Registration responses and Client Read do not leak internal data.
- [ ] Quotas, rate limits, auditing, lifecycle management, and client revocation procedures are in place.
- [ ] Integration tests prove custom metadata round-trips through the repository.
- [ ] Negative tests confirm failed requests do not create registrations.
- [ ] Production instances share the repository and identical validator/converter configurations.

**Key takeaway:** `OidcClientRegistrationAuthenticationProvider` converts incoming metadata into `RegisteredClient` and builds the response; `OidcClientConfigurationAuthenticationProvider` returns metadata on Client Read. Custom metadata must be mapped in both directions and stored in a durable location such as `ClientSettings`. Keep strict URI validators, enforce allowlists for scopes/grants/auth methods, and protect the Registration Endpoint with least-privilege Initial Access Tokens.

## 19. References

- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): Client Registration Request/Response, Initial Access Token, Registration Access Token, and Client Configuration Endpoint.
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): registration metadata, software statements, and protected/open registration.
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592.html): post-creation registration management; distinguish from specific endpoints supported by Spring Authorization Server.
- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): enabling the endpoint, custom metadata converters, registrars, and initial access tokens.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcClientRegistrationEndpointConfigurer`, filters, and default providers.
- [OidcClientRegistrationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationProvider.html): validators, password encoders, and metadata converters.
- [OidcClientConfigurationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientConfigurationAuthenticationProvider.html): Client Read provider and response converter.
- [OidcClientRegistrationAuthenticationValidator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationValidator.html): strict/default and simple validators.
- [OidcClientRegistration API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcClientRegistration.html): Client Registration metadata claims.
- [RegisteredClient API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClient.html): client registration model in Spring Authorization Server.
- [ClientSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.html): custom settings and client security settings.

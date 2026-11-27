# Adding JDBC, Custom Login, and Consent Page

In this lab, you migrate Spring Authorization Server's client and authorization data from in-memory to JDBC, authenticate users against accounts stored in a database, and replace the default login and consent pages with Thymeleaf views. Once complete, the client can initiate the authorization code flow, the user logs in, reviews the requested scopes, approves permissions, and returns to the callback to exchange the authorization code for a token.

The pieces connect across three types of data (plus user accounts):

| Data | Storage Component | Role |
|---|---|---|
| Client registration | JdbcRegisteredClientRepository | Client ID, encoded secret, grant types, redirect URIs, scopes, and client settings |
| Authorization and token state | JdbcOAuth2AuthorizationService | Authorization codes, access tokens, refresh tokens, ID tokens, and their states |
| Consent | JdbcOAuth2AuthorizationConsentService | Permissions approved by the user for each client |
| User accounts | JdbcUserDetailsManager | Username, encoded password, account status, and authorities |

Spring Authorization Server provides JDBC implementations for the first three OAuth data types. Spring Security provides JdbcUserDetailsManager for user accounts. Flyway manages schemas via migrations so the database structure can be deployed repeatably across environments.

## 1. Preparing the Project and Database

The example uses Spring Boot 3, Spring Security 6, a Spring Authorization Server version compatible with the Spring Security version in use, Java 17 or higher, PostgreSQL, and Thymeleaf. Do not mix incompatible Spring Security or Spring Authorization Server versions. Check the release notes and dependency management of the chosen version before starting.

Key dependencies in Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.security:spring-security-oauth2-authorization-server'
    implementation 'org.flywaydb:flyway-core'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The Spring Authorization Server dependency requires a version compatible with Spring Boot's Spring Security version. If the project BOM does not manage this artifact, declare its version in a Gradle version catalog or dependency constraint; do not pick a version independent of Spring Security. If the Flyway version in use splits database support into separate modules, add the corresponding PostgreSQL module according to that Flyway version's documentation.

Start PostgreSQL locally using Docker:

~~~yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: authserver
      POSTGRES_USER: authserver
      POSTGRES_PASSWORD: local-dev-password
    ports:
      - "5432:5432"
    volumes:
      - authserver-data:/var/lib/postgresql/data

volumes:
  authserver-data:
~~~

Save this content as docker-compose.yml in the lab project and run:

~~~bash
docker compose up -d
~~~

Configure the application in application.yml:

~~~yaml
server:
  port: 9000

spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/authserver
    username: authserver
    password: local-dev-password
    driver-class-name: org.postgresql.Driver
  flyway:
    enabled: true
    locations: classpath:db/migration
  thymeleaf:
    cache: false
~~~

The credentials in the example are for a local database only. In shared environments, retrieve the URL and credentials from a secret manager or environment variables, restrict database user privileges, and enable TLS for database connections.

## 2. Creating the Schema with Flyway

Create the src/main/resources/db/migration directory. The first migration creates the users and authorities tables used by JdbcUserDetailsManager by default:

~~~sql
-- V1__user_tables.sql
CREATE TABLE users (
    username VARCHAR(100) PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(100) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_authorities_users
        FOREIGN KEY (username) REFERENCES users(username)
);

CREATE UNIQUE INDEX ix_auth_username
    ON authorities (username, authority);
~~~

The next migration needs to create the three Spring Authorization Server tables:

- oauth2_registered_client
- oauth2_authorization
- oauth2_authorization_consent

Do not manually create these three tables using a stripped-down schema. Take the exact schema scripts bundled with the Spring Authorization Server version you are using, and put their contents into the Flyway migration:

~~~text
org/springframework/security/oauth2/server/authorization/client/oauth2-registered-client-schema.sql
org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql
org/springframework/security/oauth2/server/authorization/consent/oauth2-authorization-consent-schema.sql
~~~

Place the corresponding statements into V2__authorization_server_tables.sql. The original scripts may need data type adjustments for PostgreSQL or another database vendor, especially for columns storing large payloads and serialized attributes. Keep table names, column names, and lengths compatible with the JDBC implementation. Do not copy schemas from a library version different from the dependency being run.

After the application starts, Flyway must record V1 and V2 in flyway_schema_history. If a migration fails, fix the migration in the dedicated lab database and re-run following Flyway's process; do not delete or edit migration history in shared environments to hide errors.

## 3. Wiring the JDBC Services

Spring Boot auto-configures DataSource and JdbcTemplate from application.yml. Declare the JDBC repository and services:

~~~java
@Configuration
public class AuthorizationPersistenceConfiguration {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            JdbcTemplate jdbcTemplate) {
        return new JdbcRegisteredClientRepository(jdbcTemplate);
    }

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository registeredClientRepository) {
        return new JdbcOAuth2AuthorizationService(
                jdbcTemplate, registeredClientRepository);
    }

    @Bean
    OAuth2AuthorizationConsentService authorizationConsentService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository registeredClientRepository) {
        return new JdbcOAuth2AuthorizationConsentService(
                jdbcTemplate, registeredClientRepository);
    }
}
~~~

These three beans each have a distinct responsibility. RegisteredClientRepository reads and writes client configurations. OAuth2AuthorizationService stores authorization and token state. OAuth2AuthorizationConsentService stores permissions approved by users. If you only switch client registration to JDBC while still using an in-memory authorization service, codes or tokens may vanish when the application restarts.

Do not auto-create schemas on every production run. Flyway is responsible for schema changes; the JDBC services only read and write data according to the schema matching the library version.

## 4. Configuring the Password Encoder and JDBC User Accounts

Create a shared PasswordEncoder for login passwords and client secrets. DelegatingPasswordEncoder stores the algorithm prefix inside the encoded string, helping the server identify the encoder during verification:

~~~java
@Configuration
public class IdentityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    JdbcUserDetailsManager userDetailsService(DataSource dataSource) {
        return new JdbcUserDetailsManager(dataSource);
    }
}
~~~

JdbcUserDetailsManager uses the users and authorities tables created in migration V1 by default. If your organization's schema uses different names or structures, you must configure the corresponding queries using the JdbcUserDetailsManager API and re-test loading users and authorities.

Create an idempotent demo account to run the lab:

~~~java
@Bean
ApplicationRunner seedDemoUser(
        JdbcUserDetailsManager users,
        PasswordEncoder passwordEncoder) {

    return args -> {
        if (!users.userExists("alice")) {
            users.createUser(User.withUsername("alice")
                    .password(passwordEncoder.encode("local-only-password"))
                    .roles("USER")
                    .build());
        }
    };
}
~~~

The demo account is for the local database only. Do not keep hardcoded passwords in source code or create default high-privilege accounts when deploying to production. In a real application, accounts should be provisioned through an administrative workflow or an appropriate identity provider.

## 5. Storing RegisteredClient in JDBC

Create a client for the authorization code flow. The client requires PKCE and consent so the lab can verify both steps:

~~~java
@Bean
ApplicationRunner seedRegisteredClient(
        RegisteredClientRepository clients,
        PasswordEncoder passwordEncoder) {

    return args -> {
        if (clients.findByClientId("portal-client") == null) {
            RegisteredClient client = RegisteredClient
                    .withId(UUID.randomUUID().toString())
                    .clientId("portal-client")
                    .clientName("Portal Lab")
                    .clientSecret(passwordEncoder.encode("local-only-secret"))
                    .clientAuthenticationMethod(
                            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                    .authorizationGrantType(
                            AuthorizationGrantType.AUTHORIZATION_CODE)
                    .authorizationGrantType(
                            AuthorizationGrantType.REFRESH_TOKEN)
                    .redirectUri("http://localhost:9000/callback")
                    .scope(OidcScopes.OPENID)
                    .scope(OidcScopes.PROFILE)
                    .scope("orders.read")
                    .clientSettings(ClientSettings.builder()
                            .requireProofKey(true)
                            .requireAuthorizationConsent(true)
                            .build())
                    .build();

            clients.save(client);
        }
    };
}
~~~

Client ID is the protocol identifier that the client sends in requests. The id passed to withId is the internal key of the RegisteredClient record; these two values are not interchangeable. The client secret must be encoded with a PasswordEncoder compatible with the client authentication provider. Do not store raw secrets in the client_secret column.

Client secret authentication has its own PasswordEncoder in ClientSecretAuthenticationProvider. With the default configuration, use a compatible DelegatingPasswordEncoder; if the application customizes the provider, configure the same PasswordEncoder bean so stored values and received values are compared using the same algorithm.

If the application runs multiple instances, the seed runner must be safe under concurrent execution. For production environments, manage client registrations via data migrations or a controlled administrative process; avoid having every instance create new clients with random UUIDs on startup.

## 6. Configuring the Authorization Server and Application Filter Chains

The Authorization Server needs one chain for protocol endpoints and a fallback chain for the login page, consent page, and application routes. Obtain the endpoint matcher from the configurer so no endpoints are missed when OIDC is enabled:

~~~java
@Configuration
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(
                    authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                    authorizationServer
                        .oidc(Customizer.withDefaults())
                        .authorizationEndpoint(endpoint ->
                                endpoint.consentPage("/oauth2/consent"))
            )
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions ->
                    exceptions.defaultAuthenticationEntryPointFor(
                            new LoginUrlAuthenticationEntryPoint("/login"),
                            new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
                    ));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                            "/login", "/error", "/css/**").permitAll()
                    .anyRequest().authenticated()
            )
            .formLogin(form -> form
                    .loginPage("/login")
                    .loginProcessingUrl("/login")
                    .failureUrl("/login?error")
                    .permitAll()
            );

        return http.build();
    }
}
~~~

The Authorization Server chain comes before the application chain. Because the application chain does not declare a securityMatcher, it handles all remaining requests, including /login, /oauth2/consent, and /callback. The GET consent page requires an authenticated user. The login form is processed in the application chain with CSRF protection. The consent form POST goes back to the /oauth2/authorize protocol endpoint and is handled by the Authorization Server configurer; keep the CSRF policy for this endpoint as configured by your version, and do not disable CSRF application-wide. The template includes the CSRF token for compatibility with test configurations that enable the CSRF filter for that route.

The example uses the modern Spring Authorization Server configurer API. If your project uses an older version, the way the configurer is initialized may differ; keep the two core principles: obtain the matcher from the configurer and order the Authorization Server chain before the fallback chain.

## 7. Configuring the Issuer and Signing Key for the Lab Environment

Set the public issuer that clients will trust:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("http://localhost:9000")
            .build();
}
~~~

The Authorization Server needs a JWKSource to sign tokens. For a local lab, you can generate an in-memory RSA key:

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() throws Exception {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    KeyPair pair = generator.generateKeyPair();

    RSAKey rsaKey = new RSAKey.Builder(
            (RSAPublicKey) pair.getPublic())
            .privateKey((RSAPrivateKey) pair.getPrivate())
            .keyID(UUID.randomUUID().toString())
            .build();

    JWKSet jwkSet = new JWKSet(rsaKey);
    return (selector, context) -> selector.select(jwkSet);
}

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

In-memory generated keys change after every restart. This is only a simple way to run the lab; previously issued tokens may no longer verify after the application restarts. Production must use persistent keys managed via a keystore, KMS, or HSM, with rotation and backup plans. Do not store private keys in the authorization database or in logs.

## 8. Creating a Custom Login Page with Thymeleaf

Spring Security still handles the login POST at /login. The controller only serves the GET page:

~~~java
@Controller
public class LoginPageController {

    @GetMapping("/login")
    public String login(
            @RequestParam(name = "error", required = false) String error,
            Model model) {
        model.addAttribute("loginFailed", error != null);
        return "login";
    }
}
~~~

Create src/main/resources/templates/login.html:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign In</title>
</head>
<body>
<main>
    <h1>Sign In to Portal Lab</h1>
    <p th:if="${loginFailed}" role="alert">
        Invalid username or password.
    </p>

    <form th:action="@{/login}" method="post">
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">

        <label for="username">Username</label>
        <input id="username" name="username"
               type="text" autocomplete="username" required>

        <label for="password">Password</label>
        <input id="password" name="password"
               type="password" autocomplete="current-password" required>

        <button type="submit">Sign In</button>
    </form>
</main>
</body>
</html>
~~~

The username and password field names must match the default form login processing or be reconfigured in formLogin. The CSRF token is injected into the form using the request attribute provided by Spring Security. The error message does not reveal whether the username exists. Do not handle passwords directly in the controller; let AuthenticationManager and DaoAuthenticationProvider verify them via UserDetailsService and PasswordEncoder.

## 9. Creating the Consent Controller

When a client requests scopes not yet approved by the user, the Authorization Server redirects the browser to /oauth2/consent with client_id, state, and the requested scopes. The controller looks up the client and saved consent to display the application name and current permission state:

~~~java
@Controller
public class ConsentPageController {

    private final RegisteredClientRepository clients;
    private final OAuth2AuthorizationConsentService consents;

    public ConsentPageController(
            RegisteredClientRepository clients,
            OAuth2AuthorizationConsentService consents) {
        this.clients = clients;
        this.consents = consents;
    }

    @GetMapping("/oauth2/consent")
    public String consent(
            @RequestParam("client_id") String clientId,
            @RequestParam("state") String state,
            @RequestParam(name = "scope", required = false)
                    List<String> requestedScopes,
            Principal principal,
            Model model) {

        RegisteredClient client = clients.findByClientId(clientId);
        if (client == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        Set<String> approvedScopes = new HashSet<>();
        OAuth2AuthorizationConsent existing = consents.findById(
                client.getId(), principal.getName());

        if (existing != null) {
            existing.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .filter(authority -> authority.startsWith("SCOPE_"))
                    .map(authority -> authority.substring("SCOPE_".length()))
                    .forEach(approvedScopes::add);
        }

        model.addAttribute("clientId", clientId);
        model.addAttribute("clientName", client.getClientName());
        model.addAttribute("state", state);
        model.addAttribute("requestedScopes",
                requestedScopes == null ? List.of() : requestedScopes);
        model.addAttribute("approvedScopes", approvedScopes);

        return "consent";
    }
}
~~~

Consent is looked up by the internal registered client ID and the authenticated username. The Principal must come from the login session's SecurityContext; never accept a username from a query parameter or hidden field. The controller only displays consent; recording the user's choice is handled by the Authorization Server when the form POSTs back to the authorization endpoint.

## 10. Creating the Custom Consent Page

Create src/main/resources/templates/consent.html:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Approve Access Permissions</title>
</head>
<body>
<main>
    <h1>Approve Access Permissions</h1>
    <p>
        The application
        <strong th:text="${clientName}">Portal Lab</strong>
        is requesting the following permissions:
    </p>

    <form th:action="@{/oauth2/authorize}" method="post">
        <input type="hidden" name="client_id" th:value="${clientId}">
        <input type="hidden" name="state" th:value="${state}">
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">

        <fieldset>
            <legend>Requested Permissions</legend>
            <label th:each="scope : ${requestedScopes}">
                <input type="checkbox" name="scope"
                       th:value="${scope}" checked>
                <span th:text="${scope}">profile</span>
                <small th:if="${approvedScopes.contains(scope)}">
                    Previously approved
                </small>
            </label>
        </fieldset>

        <button type="submit"
                name="user_oauth_approval" value="true">
            Approve
        </button>
        <button type="submit"
                name="user_oauth_approval" value="false">
            Deny
        </button>
    </form>
</main>
</body>
</html>
~~~

The checkboxes submit the scopes the user actually selects. The Approve button submits user_oauth_approval=true; the Deny button submits false. The Authorization Server handles the POST at /oauth2/authorize, validates the client and state against the original request, and updates the consent service. Do not create a separate POST controller to save consent manually unless there is a requirement to extend the protocol; doing so easily bypasses state validation, client validation, and the framework's authorization workflow.

In a production UI, clearly explain the meaning of each scope rather than displaying only cryptic technical names. Sensitive scopes should describe the data or actions the application will be permitted to access. Do not auto-approve all scopes without giving the user a choice.

## 11. Adding a Lab Callback to Observe the Authorization Code

To complete the flow within the same application, create a lab-only callback. This route is protected by the application chain's login session:

~~~java
@Controller
public class LabCallbackController {

    @GetMapping("/callback")
    public String callback(
            @RequestParam("code") String code,
            @RequestParam("state") String state,
            Model model) {
        model.addAttribute("code", code);
        model.addAttribute("state", state);
        return "callback";
    }
}
~~~

The callback.html template can display the code and state so learners can copy them to the token exchange step:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Authorization callback</title>
</head>
<body>
<h1>Authorization Successful</h1>
<p>Code: <code th:text="${code}"></code></p>
<p>State: <code th:text="${state}"></code></p>
</body>
</html>
~~~

This is an observational callback for the lab, not how a real application handles authorization codes. A production client must verify state, process the callback securely, and exchange the code in the backend or in a public client following the appropriate security model. Do not write codes into application logs or analytics.

## 12. Testing the Authorization Code Flow with PKCE

Start the database, run Flyway, and start the application. Verify the following preconditions before opening the browser:

- The database has the users, authorities, and three OAuth tables.
- The alice account is created with an encoded password.
- portal-client is stored in oauth2_registered_client.
- The JWK Set endpoint returns a public key.
- The issuer is http://localhost:9000.

Use the RFC 7636 test vector to run the lab reproducibly:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge_method:
S256

code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Open the following authorization request in the browser:

~~~text
http://localhost:9000/oauth2/authorize?response_type=code&client_id=portal-client&redirect_uri=http%3A%2F%2Flocalhost%3A9000%2Fcallback&scope=openid%20profile%20orders.read&state=lab-state-001&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256
~~~

The browser is redirected to the login page. Log in with username alice and password local-only-password. After logging in, the server resumes the authorization request and redirects to the consent page. Select the scopes to grant and click Approve. The server redirects to /callback with the authorization code and state. Confirm that the returned state equals lab-state-001.

Exchange the code for a token using curl:

~~~bash
curl --user portal-client:local-only-secret \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "code=PASTE_AUTHORIZATION_CODE_HERE" \
  --data-urlencode "redirect_uri=http://localhost:9000/callback" \
  --data-urlencode "code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk" \
  http://localhost:9000/oauth2/token
~~~

On Windows PowerShell, invoke curl.exe to avoid PowerShell 5.1's curl alias:

~~~powershell
curl.exe --user "portal-client:local-only-secret" --header "Content-Type: application/x-www-form-urlencoded" --data-urlencode "grant_type=authorization_code" --data-urlencode "code=PASTE_AUTHORIZATION_CODE_HERE" --data-urlencode "redirect_uri=http://localhost:9000/callback" --data-urlencode "code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk" http://localhost:9000/oauth2/token
~~~

A successful response contains access_token and, with the openid scope, an ID token. Depending on token configuration, the response may also include refresh_token. Do not paste token responses into tickets, logs, or shared screenshots.

## 13. Verifying JDBC Data

Check the client registration:

~~~sql
SELECT client_id,
       client_authentication_methods,
       authorization_grant_types,
       redirect_uris,
       scopes
FROM oauth2_registered_client
WHERE client_id = 'portal-client';
~~~

Check the consent saved for alice:

~~~sql
SELECT principal_name, authorities
FROM oauth2_authorization_consent
WHERE registered_client_id = (
    SELECT id
    FROM oauth2_registered_client
    WHERE client_id = 'portal-client'
)
AND principal_name = 'alice';
~~~

Check authorization metadata without reading columns containing token values:

~~~sql
SELECT principal_name,
       authorization_grant_type,
       authorized_scopes,
       authorization_code_issued_at,
       authorization_code_expires_at
FROM oauth2_authorization
WHERE principal_name = 'alice'
  AND authorization_code_issued_at IS NOT NULL
ORDER BY authorization_code_issued_at DESC;
~~~

The OAuth2Authorization schema has columns storing authorization codes, access tokens, refresh tokens, and ID tokens. Do not SELECT or export *_value columns in operational reports. When verifying persistence, metadata such as principal, grant type, scopes, and issued/expiration timestamps is sufficient.

Restart the application and verify that portal-client and the saved consent remain in the database. If using the lab's in-memory JWKSource, tokens issued before the restart may no longer verify because the signing key changed; that does not mean JDBC authorization or consent data was lost.

## 14. Additional Verification Tests

After the happy path succeeds, run the following scenarios:

| Scenario | Action | Expected Observation |
|---|---|---|
| Wrong password | Log in as alice with an incorrect password | Login page shows a generic error without revealing account existence |
| Deny consent | Click Deny | No authorization code is issued; client receives an authorization error |
| Saved consent | Resend authorization request with the same client and approved scopes | Server may skip the consent page for already approved scopes |
| New scope | Add an unapproved scope to the request | Consent page asks the user to review and approve the new permission |
| Wrong PKCE verifier | Exchange code with a different verifier | Token endpoint returns invalid_grant |
| Replay code | Resend an already exchanged authorization code | Token endpoint rejects the subsequent exchange |
| Server restart | Restart the application | Client and consent still exist in JDBC |
| Unauthenticated user | Open authorization request in a new session | Server redirects to the custom login page |

To re-run consent from scratch in the lab database, use a new test user or delete the consent for the specific client and user via a controlled administrative operation. Do not truncate the entire authorization or consent table in shared environments.

## 15. Common Errors and Troubleshooting

**Tables not found at startup:** Confirm Flyway ran migrations and the schema matches the Spring Authorization Server version. Check which database/schema the datasource points to. Do not fix this by enabling arbitrary table creation at runtime.

**Client secret authentication fails:** Check client_id, the CLIENT_SECRET_BASIC method, encoder prefix, and the encoded secret in RegisteredClient. Ensure the client does not send the secret in both the header and the body simultaneously.

**User login fails:** Check the users and authorities tables, PasswordEncoder, the enabled column, and JdbcUserDetailsManager queries. Do not store raw passwords.

**Consent page is not invoked:** Check that the client has requireAuthorizationConsent(true), the configurer sets consentPage("/oauth2/consent"), and the request reaches the Authorization Server chain. If consent is already saved for the scopes, the server may not ask the user to approve again.

**Consent POST returns 403:** Check the CSRF token in the form, the session cookie, and the chain handling POST /oauth2/authorize. Do not disable CSRF application-wide. Confirm the POST endpoint is handled by the Authorization Server configurer.

**Consent is not saved:** Check that the OAuth2AuthorizationConsentService bean is JdbcOAuth2AuthorizationConsentService and the oauth2_authorization_consent table has been migrated. Check that the principal in the login session matches the user who granted consent.

**Authorization code cannot be exchanged:** Check client authentication, exact redirect_uri match, that the code has not expired or been used, and that code_verifier matches the challenge. Do not reuse a code from a previous run.

## 16. Lab Completion

- [ ] PostgreSQL is running and Flyway applies the user schema and three OAuth tables.
- [ ] RegisteredClientRepository uses JdbcRegisteredClientRepository.
- [ ] OAuth2AuthorizationService uses JdbcOAuth2AuthorizationService.
- [ ] OAuth2AuthorizationConsentService uses JdbcOAuth2AuthorizationConsentService.
- [ ] UserDetailsService uses JdbcUserDetailsManager with encoded passwords.
- [ ] Users log in via the custom Thymeleaf login page.
- [ ] The client requires consent and displays the custom consent page.
- [ ] Users can approve or deny scopes.
- [ ] Authorization code flow with PKCE exchanges the code for tokens.
- [ ] Client registration and consent persist across application restarts.

In production, replace temporary signing keys with persistent keys, manage secrets outside source code, enable HTTPS, configure secure session cookies, restrict database access, and set up backups and migration monitoring. This lab completes JDBC persistence, custom login, and the consent page; key management policies and infrastructure hardening must be implemented according to the target environment.

# Connecting UserDetailsService, AuthenticationProvider, and the Account Store

> **Chapter:** User Authentication  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Module Goal:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Example Scope:** Servlet stack of Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.x. When using Spring Security 7.x/Boot 4.x, verify the APIs and starters for your exact version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the responsibilities of `UserDetailsService`, `AuthenticationProvider`, `AuthenticationManager`, `PasswordEncoder`, and the account data store.
2. Explain how Spring Security verifies username/password credentials and persists the **Resource Owner**'s login state before the Authorization Server continues the OAuth 2.0/OIDC flow.
3. Connect a custom account table using Spring Data JPA, convert domain data into `UserDetails`, and configure `DaoAuthenticationProvider` properly.
4. Know when to choose `JdbcUserDetailsManager`, a custom `UserDetailsService`, or another `AuthenticationProvider`.
5. Design passwords, account lock states, authorities, sessions, and safe error messages.
6. Test account loading, password verification, login request processing, and the impact on `/oauth2/authorize`.

This lesson focuses on **end-user authentication at the Authorization Server**. OAuth2 Client registration, client secret validation, authorization code issuance, and token minting are separate parts of the protocol; do not confuse them with looking up user records in a database.

## 2. Why Does an Authorization Server Need an Account Store?

An Authorization Server might receive a request like:

~~~http
GET /oauth2/authorize?response_type=code&client_id=booking-web&scope=openid%20booking.read&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&state=example-state&code_challenge=example-challenge&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
Accept: text/html
~~~

The request above only illustrates the request shape; `state` and `code_challenge` must be validly and securely generated in a real application. If the Resource Owner is not signed in yet, the AS typically redirects the browser to the login page. When the user submits a username/password, the system must answer these questions:

- In which data source is the username looked up?
- Does the submitted password match the **stored hash**?
- Is the account disabled, locked, or expired?
- Which authorities/roles does the account hold?
- Once authentication succeeds, how will Spring Security record the principal and maintain the browser session?

This is where `UserDetailsService`, `DaoAuthenticationProvider`, `PasswordEncoder`, and the account repository work together.

### 2.1. Roles in the Authentication Chain

| Component | Responsibility | Should Not Be Assigned |
| --- | --- | --- |
| **Account Store** | Stores usernames, password hashes, status flags, authorities, and related data | Issuing OAuth2 access tokens directly |
| **`UserDetailsService`** | Looks up an account by username and returns `UserDetails` | Comparing raw passwords with hashes itself or issuing OAuth2 tokens |
| **`PasswordEncoder`** | One-way hashes new passwords and verifies submitted passwords | Managing sessions or OAuth2 scopes |
| **`AuthenticationProvider`** | Verifies a specific `Authentication` type; here, username/password | Managing all OAuth2 client registrations |
| **`AuthenticationManager`** | Dispatches to providers capable of handling an authentication request | Having to be rewritten from scratch for every application |
| **`SecurityContext`** | Holds the authenticated `Authentication` for the request | Acting as a store for OAuth2 authorization codes/tokens |
| **`RegisteredClientRepository`** | Stores OAuth2 Client configuration, grants, redirect URIs, scopes, client authentication | Looking up login users by username |
| **`OAuth2AuthorizationService`** | Stores OAuth2 grant and token state | Replacing `UserDetailsService` |

Specifically, "client authentication" in OAuth 2.0 refers to the **application** calling the token endpoint; "user authentication" in this lesson refers to the **user** logging in. Both can appear in the same Spring Security system, yet they do not share the same principal, credentials, or providers.

## 3. Username/Password Flow from Form Login to Database

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User (Resource Owner)
    participant B as Browser
    participant F as UsernamePasswordAuthenticationFilter
    participant M as AuthenticationManager
    participant P as DaoAuthenticationProvider
    participant D as UserDetailsService
    participant DB as Account Repository / Database
    participant E as PasswordEncoder
    participant S as SecurityContext / Session

    U->>B: Enter username and password
    B->>F: POST /login + CSRF token
    F->>M: Unauthenticated UsernamePasswordAuthenticationToken
    M->>P: authenticate(...)
    P->>D: loadUserByUsername(username)
    D->>DB: Find account, authorities, and status
    DB-->>D: Account + password hash + authorities
    D-->>P: UserDetails
    P->>P: Check enabled / locked / expiry
    P->>E: matches(rawPassword, passwordHash)
    E-->>P: true or false
    alt Valid
        P-->>M: Authenticated Authentication
        M-->>F: Authentication
        F->>S: Save SecurityContext per login mechanism
        F-->>B: Redirect onward to saved request
    else Invalid
        P-->>F: AuthenticationException
        F-->>B: Redirect to login failure page
    end
~~~

The diagram illustrates the typical logic of `DaoAuthenticationProvider` and does not assert the exact order of every check or internal method name across all versions. Spring Security may run account status checks before or after credential matching and includes mechanisms to hide whether an account exists.

### 3.1. Distinguishing the Two Forms of `UsernamePasswordAuthenticationToken`

Before authentication:

~~~java
Authentication request = UsernamePasswordAuthenticationToken
    .unauthenticated("lan", "submitted-password");
~~~

This is only an **authentication request**, not valid proof yet. The filter passes it to `AuthenticationManager` to find a supporting provider. `DaoAuthenticationProvider` loads `UserDetails` and calls `PasswordEncoder.matches(...)`.

Upon success, the provider creates an authenticated `Authentication` carrying the principal and authorities; the result is placed in the `SecurityContext`. Sensitive credential details are typically erased after authentication according to framework configuration.

**Never manually call** `UsernamePasswordAuthenticationToken.authenticated(...)` from a controller simply because an account was found. Doing so can bypass password verification, account status checks, and provider policies.

### 3.2. ProviderManager Decides Which Provider Handles It

`AuthenticationManager` is an interface contract. `ProviderManager` is a common implementation that iterates over configured `AuthenticationProvider` instances and picks one that supports the corresponding `Authentication` type via `supports(...)`.

For example:

- `DaoAuthenticationProvider` handles username/password requests.
- An LDAP provider or custom provider can verify a different type of credential.
- OAuth2 Client providers at Spring Authorization Server's token endpoint handle **client authentication**, not the Resource Owner's login password.
- An application may have multiple providers, but you must control their order and the request types each handles.

## 4. Choosing the Right Account Store

| Account Store | When It Fits | Key Considerations |
| --- | --- | --- |
| `InMemoryUserDetailsManager` | Demos, tests, or quick spikes | Not suitable as a long-term production user store |
| `JdbcUserDetailsManager` | Simple systems using the default schema or customizable SQL | Requires matching `users`/`authorities` tables or configured SQL queries |
| Custom `UserDetailsService` + Spring Data JPA | Custom account table with domain status and roles | Entity mapping, transactions, unique username, migrations, account locking |
| Custom `UserDetailsService` + JDBC/MyBatis | Full SQL control or no JPA | Must query safely and map rows to `UserDetails` yourself |
| LDAP/Active Directory | Accounts and authentication centrally managed by an organization | Can use an LDAP provider directly; `DaoAuthenticationProvider` with a DB password hash is not always appropriate |
| Login via External IdP (OIDC/SAML) | Delegates user authentication to an identity provider | Requires configuring federation such as `oauth2Login()` or an equivalent solution; no internal username/password needed if unnecessary |

This lesson walks through the **Spring Data JPA** approach because it clearly illustrates the boundary between business data sources and Spring Security. An alternative JDBC example is provided in section 9.

## 5. Designing Account Data Before Writing Code

A reference schema with two tables:

~~~sql
-- PostgreSQL: schema illustration for user authentication.
CREATE TABLE auth_account (
    id UUID PRIMARY KEY,
    username VARCHAR(160) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    locked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE auth_account_authority (
    account_id UUID NOT NULL REFERENCES auth_account(id),
    authority VARCHAR(100) NOT NULL,
    PRIMARY KEY (account_id, authority)
);
~~~

In real deployments, add fields and tables to support policies such as auditing, password changes, multi-factor credentials, login history, account lockout events, tenants, or deleted accounts. Everything does not have to live in a single table.

### 5.1. Identifier Keys and Username Normalization

- `id`: a stable technical identifier that does not change when the user changes their username/email.
- `username`: the login lookup key; requires a consistent normalization policy during both creation and login.
- `password_hash`: holds only the hash produced by a supported algorithm; never store raw passwords.
- `enabled`: whether the account is allowed to sign in.
- `locked`: whether the account is locked by administrative policy or incident response.
- `authority`: high-level account permissions, such as `ROLE_USER` or `ROLE_SUPPORT`.

You may use email as the username, but you must explicitly decide case sensitivity, normalization rules, collation, uniqueness, and email ownership verification. Avoid casually calling `toLowerCase()` on every identifier field without a clear policy.

### 5.2. Authorities and Business Permissions Are Different

`ROLE_USER` indicates a standard user role; `ROLE_SUPPORT` might represent support staff. Do not infer from that role alone that the user can view every order or booking. The Resource Server must still check **object-level permissions**, access token scopes, tenants, and business policies.

Adding `ROLE_ADMIN` to a logged-in user **does not automatically** grant the `booking.read` scope to every OAuth2 Client. Client scopes and user authorities are managed in different places; the AS can combine them according to policy when issuing tokens.

## 6. Connecting the Account Store with Spring Data JPA

This section presents **code snippets from a single example**, intended for a Spring Boot project that already includes Web, Security, Data JPA, a database driver, and a migration tool. Common imports are shown per snippet; your IDE can supply imports from `jakarta.persistence.*`, `org.springframework.data.*`, and `org.springframework.security.*`.

### 6.1. Mapping the `AuthAccount` Entity

~~~java
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "auth_account")
public class AuthAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, unique = true, length = 160)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;

    @Column(nullable = false)
    private boolean enabled = true;

    @Column(nullable = false)
    private boolean locked = false;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "auth_account_authority",
        joinColumns = @JoinColumn(name = "account_id"))
    @Column(name = "authority", nullable = false, length = 100)
    private Set<String> authorities = new HashSet<>();

    protected AuthAccount() {
        // JPA
    }

    public UUID getId() { return id; }
    public String getUsername() { return username; }
    public String getPasswordHash() { return passwordHash; }
    public boolean isEnabled() { return enabled; }
    public boolean isLocked() { return locked; }
    public Set<String> getAuthorities() { return authorities; }
}
~~~

Setters and factories for account creation are omitted. When building a user registration service, deliberately design account creation rather than exposing arbitrary setters that let any API mutate password hashes or roles.

### 6.2. A Repository That Reads Only Authentication Data

~~~java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AuthAccountRepository
        extends JpaRepository<AuthAccount, UUID> {

    @EntityGraph(attributePaths = "authorities")
    Optional<AuthAccount> findByUsername(String username);
}
~~~

`@EntityGraph` here instructs JPA to load authorities together with the account, avoiding lazy-loading failures outside the transaction. For complex systems, you may opt for a dedicated projection or optimized query; the key is to map `UserDetails` completely within transaction boundaries without unintended extra queries for secrets.

At the database layer, enforce a unique constraint on username. If allowing case-insensitive lookups, do not merely write `findByUsernameIgnoreCase`: enforce the **exact same uniqueness rule** on insert so two accounts cannot share the same name from a user's perspective.

### 6.3. Writing a `UserDetailsService` That Maps DB Data to Spring Security

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final AuthAccountRepository accounts;

    public DatabaseUserDetailsService(AuthAccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AuthAccount account = accounts.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Account not found"));

        return User.withUsername(account.getUsername())
            .password(account.getPasswordHash())
            .disabled(!account.isEnabled())
            .accountLocked(account.isLocked())
            .authorities(account.getAuthorities().toArray(String[]::new))
            .build();
    }
}
~~~

Key points to understand:

1. `loadUserByUsername` looks up **one** account; it does not accept a raw password parameter.
2. `getPasswordHash()` returns the **hashed** password so the provider can verify it with `PasswordEncoder`.
3. `.disabled(!enabled)` and `.accountLocked(locked)` carry account state into `UserDetails`.
4. `.authorities(...)` uses the stored strings as-is. If the DB stores `ROLE_USER`, it keeps `ROLE_USER`; by contrast, `roles("USER")` automatically prepends `ROLE_`. Avoid mixing both styles unintentionally.
5. `@Transactional(readOnly = true)` manages the JPA query within a read-only transaction.
6. Never pass this detailed exception message straight to the UI, as doing so can reveal whether an account exists.

If your account store tracks account or password expiration, extend a custom `UserDetails` or map the corresponding flags in the builder. For tenant/organization-scoped permissions, explicitly model where the tenant is selected and verified rather than stuffing permissions from every tenant into one shared principal.

### 6.4. Choosing a `PasswordEncoder`

Spring Security provides `DelegatingPasswordEncoder` to store an algorithm identifier inside the hash, such as `{bcrypt}...`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
~~~

Example hashing when registering or changing a password:

~~~java
String passwordHash = passwordEncoder.encode(rawPasswordFromUser);

// During login, DaoAuthenticationProvider automatically calls
// passwordEncoder.matches(submittedPassword, passwordHash).
~~~

**Never compare hashes using `equals` or re-encode the raw password and compare the two strings**: salted hashing algorithms produce different outputs across calls. Always use `matches(raw, encoded)`.

With `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, newly created hashes carry an identifying prefix such as `{bcrypt}`. If legacy data stores raw BCrypt strings `$2a$...` without a prefix, design a controlled **migration/compatibility policy**. Never enable a fallback accepting plaintext or use `NoOpPasswordEncoder` in production.

BCrypt/Argon2 cost factors must be chosen based on server capacity and security targets. Arbitrarily cranking up the cost can overload the server under heavy login traffic; include rate limiting, timeouts, and capacity testing. Never log raw passwords, hashes, or per-attempt match results in application logs.

### 6.5. Wiring `DaoAuthenticationProvider`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class UserAuthenticationConfig {

    @Bean
    AuthenticationProvider userAuthenticationProvider(
            UserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);

        provider.setPasswordEncoder(passwordEncoder);
        return provider;
    }
}
~~~

`DaoAuthenticationProvider` loads the user via `UserDetailsService`, verifies user status flags, and uses `PasswordEncoder` to verify credentials. This provider supports username/password authentication requests. Across Spring Security 6.x releases, there are different constructor overloads or configuration styles; the example above uses the constructor taking `UserDetailsService`. When upgrading Spring Security major versions, verify the constructors/DSL rather than copying verbatim.

**Key takeaway:** merely registering a `PasswordEncoder` or `UserDetailsService` bean does not mean you have verified the full login flow. Ensure the login filter chain uses the provider and form login is configured in the right place.

## 7. Connecting the Provider to the Login Filter Chain

An AS running Spring Authorization Server typically separates the **filter chain for OAuth2/OIDC endpoints** from the **web filter chain for user login**.

### 7.1. Chain Selection Diagram

~~~mermaid
flowchart TD
    A["HTTP request arrives at Spring Boot AS"]
    B{"Matches Authorization Server<br/>OAuth2/OIDC endpoint?"}
    C["AS SecurityFilterChain<br/>@Order(1)"]
    D["Application/Login SecurityFilterChain<br/>@Order(2)"]
    E{"Is user logged in?"}
    L["Redirect to /login<br/>if interactive request"]
    T["OAuth2 handlers process<br/>grant/client/token"]
    F["UsernamePasswordAuthenticationFilter"]
    P["DaoAuthenticationProvider"]
    DB[("Account Store")]
    S["SecurityContext + session"]

    A --> B
    B -->|"Yes"| C
    B -->|"No"| D
    C --> E
    E -->|"No, authorizing"| L
    E -->|"Yes / other endpoint"| T
    L --> D
    D -->|"POST /login"| F
    F --> P
    P --> DB
    P --> S
    S --> T
~~~

`GET /login` is a new browser request and is normally handled by the application/login chain. The token endpoint has its own **OAuth2 Client** authentication mechanism; `DaoAuthenticationProvider` is not used to verify `client_secret` at the token endpoint.

### 7.2. Two-Chain Configuration Example

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration
public class SecurityChains {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .exceptionHandling(exceptions ->
                exceptions.defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain loginSecurity(
            HttpSecurity http,
            AuthenticationProvider userAuthenticationProvider)
            throws Exception {

        http
            .authenticationProvider(userAuthenticationProvider)
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Requirements for the code above to run inside a complete Authorization Server:

- The project has the appropriate Spring Authorization Server, Spring Web/Security dependencies, and build configuration.
- The AS has `RegisteredClientRepository`, `OAuth2AuthorizationService`, keys/JWK, issuer settings, and other beans required by enabled endpoints.
- If `oidc(...)` is enabled, OIDC-supporting components such as `JwtDecoder` must be present as required by your version.
- User login has valid `UserDetailsService`, `AuthenticationProvider`, and `PasswordEncoder` beans; if multiple providers are configured, avoid bean ambiguity during injection.
- `GET /login` and `POST /login` are handled via form login. `formLogin(Customizer.withDefaults())` supplies a default login page suitable for learning environments.
- If you also expose separate REST APIs, design a chain with appropriate Bearer token support instead of letting APIs return an HTML login page.

**Never place a general `@Order(1)` `anyRequest()` chain ahead of the AS matcher**: it can swallow all OAuth2/OIDC endpoints. Chain ordering and `securityMatcher` behavior must be tested.

### 7.3. After Login, What Happens to the OAuth2 Authorization Request?

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Resource Owner
    participant B as Browser
    participant AS as Authorization Server
    participant LOGIN as Form Login / Provider
    participant DB as Account Store
    participant C as OAuth2 Client

    C-->>B: Redirect /oauth2/authorize
    B->>AS: Request authorize while unauthenticated
    AS-->>B: Redirect /login
    U->>B: Enter username/password
    B->>LOGIN: POST /login (valid CSRF token)
    LOGIN->>DB: UserDetailsService looks up user
    DB-->>LOGIN: Hash + account flags + authorities
    LOGIN->>LOGIN: PasswordEncoder.matches + account checks
    LOGIN-->>B: Authenticated session + redirect saved request
    B->>AS: Resume /oauth2/authorize with session
    AS->>AS: Validate client, scopes, consent
    AS-->>B: Redirect callback with authorization code
    B->>C: Client receives authorization code
    C->>AS: POST /oauth2/token + client auth + code/verifier
    AS-->>C: Access token / ID token if valid
~~~

`SavedRequest` and the request cache help the browser return to the authorization request after login; session and cookie policies must be configured accordingly. Resource Owner credentials are used at the authorization endpoint and **are never forwarded directly to the Client**.

## 8. Properly Persisting SecurityContext and the Login Session

### 8.1. Distinguishing Per-Request Authentication from Grant State

- `SecurityContextHolder.getContext().getAuthentication()` during login/authorization requests holds the Resource Owner's principal.
- `HttpSession` or an appropriate `SecurityContextRepository` lets the signed-in user continue the flow across redirects.
- `OAuth2AuthorizationService` stores authorization code/token state so the Client can exchange the code in a subsequent request.
- The token endpoint uses OAuth2 client authentication. Do not rely on the `ThreadLocal` from a finished login request.

If you write a custom authentication filter or controller (instead of built-in form login), under Spring Security 6's explicit-save behavior you must persist the `SecurityContext` via `SecurityContextRepository.saveContext(...)` to maintain the login across subsequent requests. Calling `SecurityContextHolder.setContext(...)` alone does not automatically save it to the session.

### 8.2. CSRF and Cookies

Form login relies on sessions/cookies and therefore requires CSRF handling. With `MockMvc` or custom HTML forms, submit the CSRF token according to Spring Security's configured mechanism. Never disable CSRF globally just to make `POST /login` work.

In production, enforce HTTPS, `Secure` and `HttpOnly` cookies, verify `SameSite` policies for cross-site redirects, preserve session fixation protection, bound session lifetimes, and configure trusted load balancer/reverse proxy headers. With multiple AS instances, session and authorization/consent storage require shared/distributed backing unless sticky sessions are used.

## 9. Alternative: JdbcUserDetailsManager

If the account store is simple and matches Spring Security's schema, there is no need to write custom JPA entities. `JdbcUserDetailsManager` implements both `UserDetailsService` and configurable user-management operations.

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.JdbcUserDetailsManager;

@Bean
UserDetailsService jdbcUserDetailsService(DataSource dataSource) {
    return new JdbcUserDetailsManager(dataSource);
}
~~~

With default usage, create the `users` and `authorities` tables matching Spring Security's schema, or customize the SQL queries via `JdbcDaoImpl`/`JdbcUserDetailsManager` APIs when using an existing schema.

Minimal example illustrating a schema compatible with the default queries (verify DDL against your database dialect and Spring version):

~~~sql
CREATE TABLE users (
    username VARCHAR(50) NOT NULL PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(50) NOT NULL,
    CONSTRAINT fk_authorities_users
        FOREIGN KEY (username) REFERENCES users(username)
);

CREATE UNIQUE INDEX ix_auth_username
    ON authorities(username, authority);
~~~

Do not declare **both** the `DatabaseUserDetailsService` bean from the JPA example and the `jdbcUserDetailsService` bean here unless you intentionally configure qualifiers or provider selection. If both exist, plain `UserDetailsService` injection will be ambiguous or the system may query the wrong account store.

### 9.1. When Your Company Schema Differs from the Default

You have two options:

1. Use `JdbcUserDetailsManager` and customize its SQL queries to read your account/authority tables.
2. Write a custom `UserDetailsService` using Spring Data JPA/JDBC to map domain statuses and authorities.

Do not force another system's database into the `users`/`authorities` schema just to fit a tutorial example if there are existing domain, transaction, or migration constraints.

## 10. Authenticating Users Outside the Internal Database

### 10.1. LDAP or Active Directory

For LDAP, Spring Security supports direct LDAP authentication mechanisms such as bind authentication. Passwords can be verified directly by the directory server; **`DaoAuthenticationProvider` with a local password hash may not be the right path**.

You still need to address authority/group mapping, account status, directory timeouts/HA, application authorization, and how the user principal is persisted after authentication.

### 10.2. Signing In via Another OpenID Connect Provider

Your Authorization Server can let users sign in through an external IdP using `oauth2Login()`, and then use the resulting authentication as the Resource Owner session to authorize OAuth2 Clients of the **internal AS**.

In this flow:

- The internal AS acts as an **OIDC Client/Relying Party** when talking to the external IdP.
- Simultaneously, the internal AS still acts as an **Authorization Server/OpenID Provider** to its own Clients.
- The principal from `oauth2Login()` is typically an `OidcUser`, not a `UserDetails` loaded by `DaoAuthenticationProvider`.
- You must design a mapping from the external IdP's `issuer + sub` to an internal account and user permissions; never treat email as an immutable identifier.

Do not use the Resource Owner Password Credentials grant to bypass login configuration in modern systems. Authorization Code + PKCE or appropriate federation flows are preferred.

## 11. Account States and Safe Handling

`UserDetails` exposes these flags:

| Property | Meaning | In the Example |
| --- | --- | --- |
| `isEnabled()` | Whether the account is permitted to authenticate | Mapped from `enabled` |
| `isAccountNonLocked()` | Whether the account is not locked | Inverted from `locked` |
| `isAccountNonExpired()` | Whether the account has not expired | `User` builder keeps default if unset |
| `isCredentialsNonExpired()` | Whether credentials have not expired | `User` builder keeps default if unset |
| `getAuthorities()` | High-level authorities at user load time | From `auth_account_authority` |

Spring Security may raise exceptions such as `BadCredentialsException`, `DisabledException`, `LockedException`, `AccountExpiredException`, or `CredentialsExpiredException` during authentication. **You should not necessarily display the exact reason** on a public login page, as doing so can help attackers infer whether an account exists or is locked.

### 11.1. Account Lockout Does Not Happen Automatically Just Because a `locked` Flag Exists

Mapping `locked` only lets the provider reject users **already marked as locked**. It does not count failed login attempts or decide when to lock an account.

A complete policy might include:

- Rate limiting by IP, account, and risk signals; prevent attackers from locking out large numbers of users via forged requests.
- Recording failures and security events in a secure store with cleanup and retention policies.
- Temporary lockouts or step-up challenges based on risk scores, paired with a valid unlock workflow.
- MFA support for sensitive accounts or high-assurance operations.
- Limiting enumeration across responses, latency, and error message content.
- Session and token revocation or account status checks when a user is locked after already signing in.

**Locking a user in the database does not necessarily terminate active sessions or already-issued JWTs.** If immediate lockout is required, design corresponding session invalidation and token verification policies at the AS/RS.

### 11.2. UserDetails Caching and Mid-Session Permission Changes

Some deployments/providers cache `UserDetails` to reduce database load. If the cache retains `enabled`, `locked`, or `authorities` for too long, subsequent logins can observe stale state. Define TTL and invalidation rules for password changes, account lockouts, or permission updates.

Existing sessions may also hold an `Authentication` containing authorities captured at login time. Changing a role in the DB **does not automatically** update live sessions; choose an authority evaluation or session invalidation strategy matching your system's requirements.

## 12. Account Creation and Password Change Flows

Never accept a pre-hashed password from the client and trust it as authoritative. Accounts must be created and passwords updated inside a service enforcing proper authorization and validation.

~~~mermaid
flowchart TD
    A["Account creation or password change request"]
    B["Verify permissions, identity, and input data"]
    C["Normalize username per policy"]
    D["Evaluate password policy + rate limit"]
    E["PasswordEncoder.encode(rawPassword)"]
    F["Persist password hash in DB within transaction"]
    G["Audit event; consider revoking sessions/tokens"]
    H["Never return raw password/hash in API/logs"]

    A --> B --> C --> D --> E --> F --> G --> H
~~~

Example hashing method in an application service:

~~~java
public String hashNewPassword(
        String rawPassword,
        PasswordEncoder passwordEncoder) {

    // Password policy, caller authorization, auditing, and
    // rate limiting must be handled in the business service.
    return passwordEncoder.encode(rawPassword);
}
~~~

This snippet only illustrates calling `encode()`, **not a complete password-change endpoint**. A production system must verify the caller's permission to change the password, verify current credentials or an appropriate strong-authentication step, execute transactionally, and consider revoking sessions/tokens.

## 13. Testing Each Integration Layer

### 13.1. Unit Testing `UserDetailsService`

With a mocked repository, verify:

| Input | Expectation |
| --- | --- |
| Existing username, account enabled, unlocked | Returns expected `UserDetails`, hash, and authorities |
| Non-existent username | Throws `UsernameNotFoundException` |
| Disabled account | Returns `UserDetails.isEnabled() == false` |
| Locked account | Returns `isAccountNonLocked() == false` |
| DB returns multiple authorities | Preserves all and does not misapply `ROLE_` prefixes |
| Permissions change while cache is active | Cache/invalidation obeys policy |
| Different username casing | Behavior matches uniqueness/normalization rules |

A `UserDetailsService` test does not need to invoke a password encoder because the service only maps account data.

### 13.2. Testing `DaoAuthenticationProvider`

Use a fixture account with a hash generated by the same `PasswordEncoder` configured on the provider:

~~~java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String storedHash = encoder.encode("strong-password-for-test");

// In tests, UserDetailsService returns UserDetails
// with password = storedHash and account enabled.

Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "lan", "strong-password-for-test");

Authentication result = provider.authenticate(request);

assertThat(result.isAuthenticated()).isTrue();
assertThat(result.getName()).isEqualTo("lan");
~~~

This is the **core snippet of a unit test**, assuming `provider` has been constructed and the `UserDetailsService` fixture returns user `lan` with the corresponding hash. Never seed a test account with a hardcoded password in production environments.

Additional cases to cover: wrong password, missing user, disabled account, locked account, unsupported hash format, and DB outage. Assert exceptions/responses per contract without leaking sensitive data into HTML or logs.

### 13.3. MockMvc Tests for Form Login

With `spring-security-test`, an invalid login example:

~~~java
@Test
void invalidPasswordDoesNotAuthenticate() throws Exception {
    mockMvc.perform(post("/login")
            .param("username", "lan")
            .param("password", "wrong-password")
            .with(csrf()))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/login?error"));
}
~~~

Valid login test:

~~~java
@Test
void validPasswordAuthenticatesUser() throws Exception {
    mockMvc.perform(post("/login")
            .param("username", "lan")
            .param("password", "correct-test-password")
            .with(csrf()))
        .andExpect(status().is3xxRedirection())
        .andExpect(authenticated().withUsername("lan"));
}
~~~

Prerequisites: the fixture stores user `lan` with the hash of `correct-test-password`, the provider actually uses the application's repository and encoder, default form login is active, `MockMvc` is wired with Spring Security, and static imports for `csrf()`/`authenticated()` are present.

Tests using `@WithMockUser` are convenient for **authorization rules**, but they bypass the real `UserDetailsService` and `PasswordEncoder`. Therefore, do not treat `@WithMockUser` tests as proof that password authentication is wired properly.

### 13.4. Integration Testing with the Authorization Server

After testing login on its own, exercise the full Authorization Code + PKCE flow:

1. A valid client sends the browser to `/oauth2/authorize` while the Resource Owner is unauthenticated.
2. The AS redirects to `/login`; the form contains a valid CSRF token.
3. The user submits valid credentials; the provider loads the real account and verifies the password hash.
4. The browser holds a valid session and returns to the original authorization request.
5. The AS validates client/redirect URI/scopes/consent and issues an authorization code per policy.
6. The client backend exchanges the code with `code_verifier` and the registered client authentication method.
7. The AS issues tokens; the Resource Server accepts only valid access tokens and enforces business permissions.

Negative test cases to include: disabled/locked user, missing user, wrong password, missing CSRF, session cookie lost across redirects, wrong client redirect URI, and invalid PKCE verifier. Avoid cramming all tests into one oversized MockMvc method; split account-store tests, login/session tests, and end-to-end protocol tests.

## 14. Common Configuration Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Login throws `BadCredentialsException` even with right password | Hash lacks `{bcrypt}` with delegating encoder, wrong test fixture, different encoder used when hashing | Verify `PasswordEncoder`, stored hash format, and migration policy |
| `No AuthenticationProvider found` for username/password | Provider not registered on the right chain/manager | Inspect `AuthenticationProvider` bean, `supports()`, and filter chain |
| `NoUniqueBeanDefinitionException` for `UserDetailsService` | Multiple user service / JDBC / in-memory beans exist | Choose the intended provider/qualifier and remove test/demo configs |
| User exists but throws `LazyInitializationException` | Authorities accessed outside transaction | Fetch authorities inside transaction using `@EntityGraph` or suitable query |
| GET login enters redirect loop | `/login` requires authentication or chain matcher is wrong | Permit access to login page; check `@Order`/`securityMatcher` |
| POST login returns 403 | Missing/invalid CSRF, wrong session cookie or chain | Fix CSRF token/form/session; never disable CSRF globally |
| Login succeeds but `/oauth2/authorize` remains anonymous | Context not persisted/restored, bad cookie, or stateless chain | Check `SecurityContextRepository`, session config, and proxy settings |
| User is locked yet old sessions still work | DB lock does not revoke active sessions/issued tokens | Enforce session invalidation, revocation, or status checks per policy |
| Client Credentials fails at token endpoint due to user service | Confused client authentication with user login | Check `RegisteredClientRepository`, client secret, and token endpoint providers |
| Slow login, DB overloaded | N+1 query on authorities, excessive hash cost, missing rate limit | Optimize query, benchmark encoder cost, and add rate limiting |
| User logs in with wrong authorities | Misused `roles()`/`authorities()` or leaked roles across tenants | Define prefix convention and tenant context clearly |
| User not found due to casing | Inconsistent normalization and unique constraint | Unify username normalization policy across creation and lookup |

### 14.1. How to Read Logs When Authentication Fails

Trace in sequence:

1. Did the request enter the right `SecurityFilterChain`? Did `UsernamePasswordAuthenticationFilter` process `POST /login`?
2. Did `AuthenticationManager` select a provider supporting the request?
3. Did `UserDetailsService` find the right account? Any DB error/timeout or authorities lazy-loading issue?
4. Are `enabled`/`locked` flags valid on the account?
5. Does the hash algorithm prefix/format match `PasswordEncoder`?
6. Were the session and `SecurityContext` persisted properly after success?
7. Did the OAuth2 request resume and validate client/grant/consent properly?

**Never log** `password`, `password_hash`, client secrets, access tokens, authorization codes, or the entire `Authentication` object. Logs may include a request ID, provider type, success/failure outcome, generic error code, masked account ID, and processing duration per privacy policy.

## 15. Account Security and Operations

A production system requires controls beyond simply "checking the right password":

- **Passwords:** modern salted hashes, length/complexity or breached-password checks as required, and secure change/reset workflows.
- **Login attack defenses:** rate limiting, monitoring, brute-force/credential-stuffing mitigation, and anomaly alerting.
- **MFA/step-up:** consider for sensitive actions; do not assume default `DaoAuthenticationProvider` provides MFA.
- **User lifecycle:** disabled/locked/expired states, permission change events, and policies for existing sessions/tokens.
- **Authorization:** separate user authorities from OAuth2 scopes/client permissions and object-level authorization in the Resource Server.
- **Database infrastructure:** secrets from a secret manager, TLS/connection policies, backups, migrations, HA, and least-privilege SQL grants.
- **Sensitive data:** never expose password hashes in API JSON responses, never emit them in logs/traces, and never store raw passwords.
- **Auditing:** record login successes/failures, lock/unlock actions, password resets, and credential compromises with necessary context and retention policies.
- **Scale:** load-test account lookup latency, hash cost, timeouts, connection pools, and directory/DB outage scenarios.
- **Environment parity:** development/test/staging/production use compatible password/hashing configs and controlled migrations; never seed default admin accounts with public passwords.

### 15.1. Implementation Checklist

- [ ] Choose a specific user store: JPA, JDBC, LDAP, or external IdP.
- [ ] Username has a unique constraint and explicit normalization policy.
- [ ] Passwords stored as hashes compatible with `PasswordEncoder`, never plaintext.
- [ ] `UserDetailsService` returns accurate principal, password hash, flags, and authorities.
- [ ] `DaoAuthenticationProvider` properly registered on the login chain when using username/password.
- [ ] Authorization Server endpoint chain and application/form-login chain have proper matchers and ordering.
- [ ] `GET /login` is public when needed, and `POST /login` has CSRF protection.
- [ ] Sessions and `SecurityContextRepository` work across redirects.
- [ ] Client authentication / token endpoint are independent of user login and tested.
- [ ] Rate limiting, auditing, lockout/disabled policies, and account recovery workflows are in place.
- [ ] Tests cover wrong password, disabled, locked, lazy authorities, DB outage, login/session, and Authorization Code + PKCE.
- [ ] No password hashes, raw passwords, cookies, codes, or tokens leaked in logs or APIs.

## 16. Self-Check Questions

**Question 1.** Why doesn't `UserDetailsService` have a `checkPassword(String, String)` method?

**Answer:** Its contract is strictly to **load a user** by username. `DaoAuthenticationProvider` combines that data with `PasswordEncoder` to match credentials and make the authentication decision.

**Question 2.** Can `RegisteredClientRepository` replace `UserDetailsService`?

**Answer:** No. `RegisteredClientRepository` manages OAuth2 Client applications, grants, secrets, and redirect URIs. `UserDetailsService` manages loading user accounts for login.

**Question 3.** Why can storing raw BCrypt hashes without `{bcrypt}` fail when using `DelegatingPasswordEncoder`?

**Answer:** The delegating encoder relies on the prefix to select the verification algorithm. Legacy hashes require a controlled migration/fallback policy.

**Question 4.** If a user has `locked = true`, do I need custom code to compare the raw password and reject them?

**Answer:** If `UserDetailsService` properly maps `isAccountNonLocked = false` and `DaoAuthenticationProvider` is used, the provider enforces the status check automatically. Auto-locking after repeated failed logins remains an additional policy to implement.

**Question 5.** Why is `@WithMockUser` insufficient to prove database user/password wiring works?

**Answer:** It injects a pre-built `Authentication` for tests, bypassing `UserDetailsService → DaoAuthenticationProvider → PasswordEncoder`. You must test the real provider, repository, and form login.

**Question 6.** If an API is called via Client Credentials, can the token endpoint look up a login user with `UserDetailsService`?

**Answer:** No. Client Credentials authenticates a **client**, typically with no interactive Resource Owner. The AS verifies the client via `RegisteredClientRepository` and processes the grant with the appropriate providers.

**Question 7.** After a user logs in properly at the AS, can the API skip checking scopes and data-level permissions?

**Answer:** No. User login is authentication. The Resource Server must still validate the access token, issuer, audience, scopes, and business permissions on data.

## 17. Summary and References

The standard integration pipeline is **Account Store → `UserDetailsService` → `DaoAuthenticationProvider` + `PasswordEncoder` → `AuthenticationManager` → `SecurityContext`**. This pipeline serves **Resource Owner login** inside the Authorization Server. Once the user is signed in, the AS proceeds with OAuth2 authorization, consent, authorization codes, and tokens per policy; `OAuth2Authorization` and `RegisteredClient` records maintain their own lifecycles.

Official documentation to verify APIs against your exact deployment version:

- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — JDBC Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/jdbc.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)

This lesson presents sample code blocks for design and hands-on practice. For production deployment, assemble them into a project with proper dependencies, migrations, client registrations, OIDC keys/issuer, session handling, account lifecycle management, and testing.

# What Is Identity Federation and What Problem Does It Solve?

**Identity federation** is a model in which an application or service trusts the authentication result issued by an **Identity Provider (IdP)**, instead of verifying the user's password, passkey, or authentication factors itself. The IdP and the application have a pre-established trust relationship; the sign-in result is transferred via a standard federation protocol, and the application validates it and creates its own session.

**Key point:** The user proves their identity to the IdP; the application receives and verifies the authentication evidence to know *who is signing in*, and then **decides for itself what that person is allowed to do**. Federation enables multiple systems to share a single source of identity without sharing passwords across systems.

## 1. Why Is Identity Federation Needed?

Suppose an enterprise uses three independent applications: an HR portal, a customer support system, and a project management application. If each application stores its own accounts and passwords, the same employee must maintain multiple login identities. When the enterprise collaborates with external partners, provisioning additional accounts in every application becomes even more complex.

An isolated login model typically causes the following problems:

1. **Identity fragmentation:** the same person is represented by different accounts, passwords, attributes, and recovery processes; it is easy to make mistakes when correlating users across systems.
2. **High administrative overhead:** creating, locking, and revoking access must be coordinated across many applications; accounts are easily missed when an employee leaves or a partner contract ends.
3. **Inconsistent authentication policies:** one application enforces MFA while another still uses weak passwords; each development team must operate its own sign-in flow and security controls.
4. **Fragmented experience:** users must sign in repeatedly and remember multiple credentials, increasing login support requests.
5. **Difficult cross-organization collaboration:** an application in enterprise A can hardly trust an account authenticated by enterprise B without a standard federation mechanism.

Federation addresses the core of these issues by **separating the role of authenticating identity from the role of providing business functionality**. The application focuses on business logic and authorization; the IdP focuses on accounts, authentication flows, and the identity information to be shared.

## 2. Components and Trust Relationships

| Component | Role | Example |
| --- | --- | --- |
| **User / Subject** | The person who needs to access a service and proves their identity | Employee, customer, partner |
| **Identity Provider (IdP)** | Authenticates users and issues information or evidence about the authentication event | Enterprise identity system |
| **Relying Party (RP) / Service Provider (SP)** | The application that relies on evidence from the IdP, validates it, and serves the user | HR portal, Spring Boot application |
| **Assertion / Identity token** | A verifiable message about the user and authentication context | SAML assertion or OIDC ID token |
| **Trust configuration** | Configuration specifying which IdPs are trusted, keys/certificates for verification, valid recipients, and endpoints | Issuer, client registration, metadata, signing certificate |

In OpenID Connect (OIDC), the application is typically called a **Relying Party**; in SAML 2.0, it is typically called a **Service Provider**. In both, the application **must not trust a claim merely because it looks like a token or came from a browser**: it must verify the evidence according to the protocol and trust configuration.

Trust relationships can cross organizational boundaries: enterprise A accepts authentication results from partner B's IdP. An RP can also trust multiple IdPs, provided there are clear rules to identify and map each person accurately.

## 3. How Does a Federated Sign-In Flow Work?

For example, a user wants to access a Spring Boot application that uses an enterprise IdP:

~~~text
User ──(1) accesses──> Application / RP
                              |
                              | (2) requests federated login
                              v
                       Configured IdP
                              |
                       (3) authenticates user
                       (password/MFA/passkey...)
                              |
                              v
                      Protocol response
                              |
                              v
Application / RP <──(4) receives and validates evidence
       |
       +──(5) identifies account, checks permissions
       |
       +──(6) creates application session and returns content
~~~

1. **Start at the RP:** the user accesses a resource that requires sign-in. The RP knows the allowed IdP and the application's registration parameters.
2. **Redirect to the IdP:** the RP initiates the federation flow. The browser may be redirected to the IdP; the request includes data used to correlate the exact sign-in attempt and application.
3. **IdP authenticates:** the IdP checks authentication factors according to its policy. If the user already has a valid session at the IdP, this step may not require re-entering a password.
4. **Exchange the result:** with the **OIDC Authorization Code Flow**, the browser returns to the RP with an authorization code; the RP exchanges the code via a server-to-server connection to the IdP to obtain tokens, including the **ID token**. With **SAML 2.0 Web Browser SSO**, the RP receives and processes a **SAML response/assertion** according to the configured binding. The two protocols have different exchange formats.
5. **RP validates:** checks the signature, issuer, recipient (audience/recipient), time validity, correlation with the initial request, and anti-forgery/anti-replay conditions for the respective protocol. The RP identifies the user from the verified identifier, then applies internal account and authorization rules.
6. **RP creates a session:** after successful sign-in, the RP manages the application's own session or security context. The session at the IdP and the session at the RP are two separate objects.

**Common pitfall:** The IdP authenticates the user, but the application does not simply "accept any token and let them in". Without proper validation and identity mapping, federation is not secure.

## 4. What Specific Problems Does Identity Federation Solve?

| Problem | How Federation Helps | Boundary to Understand |
| --- | --- | --- |
| Each application has its own accounts/passwords | The application trusts authentication results from one or more configured IdPs | The application may still need internal user profiles |
| Users must sign in repeatedly | Can create a **Single Sign-On (SSO)** experience via an existing session at the IdP | Federation does not automatically guarantee SSO if IdP policy requires re-authentication |
| Inconsistent sign-in policies | Centralizes MFA, authentication policies, and recovery flows at the IdP | The RP must choose an appropriate IdP and may need to check the authentication assurance level |
| Partners need to use enterprise applications | Establishes trust with the partner's IdP instead of issuing separate passwords to everyone | Contracts, trust scope, and application permissions still need to be managed |
| Integrating users from multiple systems | Standardizes how required identifiers and attributes are received | Does not automatically synchronize profiles, groups, or account lifecycles |
| Each dev team writes its own login flow | Can use standard libraries/protocols with standardized verification mechanisms | Issuer, keys, redirects, sessions, and authorization must still be configured correctly |

**Before and after example:**

- *Before:* An employee signs in to three applications using three accounts. When the employee leaves, operations must disable each account individually, which is easy to miss.
- *After:* All three applications rely on the enterprise IdP. Disabling sign-in at the IdP prevents new federated logins according to IdP policy; the applications still need mechanisms to manage **already-issued sessions**, internal permissions, and appropriate revocation/provisioning workflows.

Federation reduces authentication duplication. It **does not mean that every session and every access right vanishes instantaneously** when an account is locked.

## 5. Distinguishing Related Concepts

### Federation vs. Single Sign-On (SSO)

- **Federation** is the mechanism and trust relationship allowing one system to accept authentication evidence from another identity system.
- **SSO** is the experience of signing in once and accessing multiple applications without re-authenticating at each application, when sessions and policies permit.

Federation is often used to implement SSO across multiple applications or organizations. However, SSO can also exist within a single administrative domain, and a federated flow can still require MFA or re-authentication.

### Authentication vs. Authorization

- **Authentication:** who is the user, and is their login evidence valid?
- **Authorization:** which resources is the user allowed to read, modify, approve, or administer?

For example, the IdP proves the user has a valid identifier. The Spring Boot application must still determine whether that user has permission to approve orders or only view them. Claims or groups from the IdP **do not automatically become elevated privileges in the application**; they must be mapped and controlled according to policy.

### Federation vs. OAuth 2.0, OpenID Connect, and SAML 2.0

| Concept | Core Purpose | Relation to Federation |
| --- | --- | --- |
| **OAuth 2.0** | Authorizes a client to access resources/APIs within granted scopes | OAuth 2.0 itself is not a user identity verification protocol |
| **OpenID Connect (OIDC)** | Authentication layer built on OAuth 2.0, with **ID tokens** and user identification rules | Commonly used for federation and web/mobile application login |
| **SAML 2.0** | Exchanges assertions about authentication/attributes, typically using XML and digital signatures | Common in enterprise SSO and federation |
| **Identity federation** | Trust model for identity across parties | Can be implemented with OIDC, SAML, or another suitable mechanism |

OIDC's **ID token** is designed for the RP to verify the authentication result. The **access token** primarily serves to access authorized resources; it must not be arbitrarily used as an ID token. Some providers support "social login" via OAuth 2.0 combined with fetching user info, but that does not turn every access token into standard OIDC login evidence.

## 6. Three Real-World Scenarios

**Scenario A – Internal SSO:** A company has an HR portal, a Jira-like tracker, and a reporting portal, all trusting the company's IdP. Employees are required to complete MFA at the IdP, then enter applications according to their respective sessions and policies. Each application still has different roles.

**Scenario B – B2B Partners:** A company provides a transaction portal for partners. Instead of holding passwords of partner employees, the portal allows sign-in through a partner's IdP that has an established trust agreement. The application checks the issuer and recipient conditions, maps the user to the right partner organization, and applies permissions for that organization.

**Scenario C – Multiple IdPs:** A product supports employees signing in with an enterprise IdP and customers signing in with a customer IdP. Two people having the same display email are not necessarily the same identity. Linked accounts must be based on a durable IdP-scoped identifier (such as the **issuer + subject** pair in OIDC) and a verified linking process.

These scenarios show that federation's value lies in **delegating authentication responsibility across clear trust boundaries**; business data and authorization decisions remain on the application side.

## 7. How Identity Federation Relates to Spring Security

In a Java/Spring Boot application, Spring Security provides components for the application to act as the recipient of authentication results:

- **OIDC/OAuth2 Login:** Spring Security's **oauth2Login** feature enables a servlet application to sign in via an OIDC provider or an OAuth 2.0 provider with a supported login flow. With OIDC, the application is typically the **Relying Party** and configures **ClientRegistration**, issuer, client credentials, and redirect URI.
- **SAML 2.0 Login:** the **saml2Login** feature allows a servlet application to act as a **Service Provider/Relying Party**, relying on assertions from a SAML IdP/Asserting Party, with registration, metadata, and signature verification configuration.
- **OAuth2 Resource Server:** used when an API validates an **access token** from an authorization server to protect resources. This is the API token-receiving role, **distinct** from the browser-based user login flow of **oauth2Login**.
- **Authorization in the application:** Spring Security can rely on the principal/authorities after sign-in to protect URLs and methods. Mapping claims/groups to authorities should be designed according to actual business permissions.

Minimal example of *configuring URL protection and enabling OIDC login* in a **Spring Boot servlet** application with Spring Security and the **spring-boot-starter-oauth2-client** dependency:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is **a configuration class inside a Spring Boot project**, not a standalone Java program run with **javac/java**, and it has no fixed stdout. For sign-in to work, the project also needs at least one valid OIDC client registration with an IdP (issuer, client ID, secret when required, matching callback/redirect registration). Secrets must be managed securely rather than embedded in source code. When a user visits a protected URL, Spring Security initiates the login flow and handles the callback according to the configuration.

**Why does this example demonstrate federation?** The class does not implement a function to check user passwords. Authentication is delegated to the IdP; Spring Security handles the protocol and creates the security context for the application. Application access permissions are still configured separately through authorization rules.

## 8. Trust Conditions and Security Boundaries

Federation centralizes authentication but also creates dependencies on the IdP and trust configuration. A proper design must pay attention to:

1. **Genuine evidence verification:** accept only permitted issuers, verify signatures with trusted keys/certificates, validate recipients, and check time validity. For OIDC, pay attention to **state**, **nonce** (when applicable), PKCE, and the code flow; for SAML, check conditions such as **Destination**, **Recipient**, **InResponseTo**, and replay protection for the corresponding profile/binding. Do not write custom logic that bypasses library checks.
2. **Channel and callback configuration protection:** use HTTPS, register exact redirect URIs, protect sessions/cookies, and do not expose tokens or client secrets in logs.
3. **Durable identifiers:** prefer the **issuer + subject** pair or federated identifier per policy; do not automatically merge accounts merely because email addresses match or may change. Avoid accepting tokens from tenants/issuers outside the trusted list.
4. **Least-privilege authorization:** a user signing in successfully does not equate to becoming an administrator. Roles and groups from the IdP are meaningful only when verified and intentionally mapped in the application.
5. **Lifecycle management:** account provisioning/deprovisioning, attribute updates, session revocation, single-application logout, and Single Logout are separate concerns. Federation does not automatically solve all of them.
6. **Trust dependencies and limits:** an IdP outage can block new sign-ins; a compromised IdP can affect multiple RPs. Reliability, signing-key management/rotation, and incident response plans must be evaluated.
7. **Privacy:** request and store only the identity attributes needed for business purposes; define data-sharing responsibilities across organizations.

**Common mistakes:** treating "signed in via IdP" as "having all permissions"; confusing access tokens with ID tokens; trusting email as a unique identifier key; accepting an incorrect issuer; skipping audience/signature checks; assuming that locking an account at the IdP always terminates all open sessions at RPs immediately.

## 9. How to Check Your Understanding

- **Question 1:** Application A accepts a valid ID token from IdP B. Who verified the user's password or passkey? **IdP B**; A verifies the evidence and decides whether to issue a session.
- **Question 2:** Does signing in successfully to application A with a shared IdP automatically grant admin rights in application A? **No**; A must check its own authorization rules.
- **Question 3:** Does sharing an IdP guarantee that when an account is locked, every session across applications disappears immediately? **No**; proper session management and revocation mechanisms are required.
- **Question 4:** Is an OAuth 2.0 access token by default standard OIDC authentication evidence? **No**; OIDC defines the ID token and separate verification steps.

## 10. Key Takeaways and Further Reading

Identity federation answers the question: **"How can an application trust an identity authenticated by another party, under a verifiable protocol and trust relationship?"** It reduces fragmented accounts and login flows, supporting SSO and cross-organization collaboration, but it does not replace authorization, account lifecycle management, or application session security.

Official reference documentation:

- NIST SP 800-63C-4 – Federation and Assertions: https://pages.nist.gov/800-63-4/sp800-63c.html
- Spring Security – OAuth2 Login (servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security – SAML 2.0 Login (servlet): https://docs.spring.io/spring-security/reference/servlet/saml2/login/index.html

# X509AuthenticationFilter and x509 Configuration

## 1. Objectives and Scope

In Spring Security applications running on **Servlet/Spring MVC**, `X509AuthenticationFilter` identifies a user or device from a **client X.509 certificate already verified by the TLS layer**. This is a *pre-authentication* model: certificate verification and proof of private key possession occur at the TLS connector or a trusted proxy; Spring Security receives the identity afterward, maps it to an application user, and decides access permissions.

After this lesson, you will be able to:

- Distinguish a **server** certificate from a **client** certificate and understand mTLS.
- Explain the roles of `X509AuthenticationFilter`, `X509PrincipalExtractor`, `PreAuthenticatedAuthenticationToken`, `PreAuthenticatedAuthenticationProvider`, `UserDetailsService`, and `SecurityContext`.
- Use `HttpSecurity.x509(...)` to create the filter automatically and configure mTLS in **Spring Boot 3.x**.
- Extract the username from Subject DN/CN, choose a custom extractor when identity resides in SAN, and assign authorities from trusted data.
- Use `MockMvc` and `curl` to test two independent layers: mapping in Spring Security and the handshake at the TLS server.
- Identify important configuration changes when migrating from Spring Security 5.x to 6.x/7.x and security pitfalls with reverse proxies.

**Primary scope:** Spring Security 6.x, Spring Boot 3.x, Java 17+, Servlet applications with embedded Tomcat. Separate notes are included for 5.x and 7.x. WebFlux has a different reactive X.509 API; do not use Servlet's `X509AuthenticationFilter` directly as a filter in `SecurityWebFilterChain`.

## 2. X.509 Certificates, One-Way TLS, and mTLS

An X.509 certificate is CA-signed data binding a public key to an identity and attributes such as Subject, Subject Alternative Name (SAN), issuer, validity period, Key Usage, and Extended Key Usage. The party holding the corresponding private key can prove key possession during the TLS protocol.

- **One-way TLS:** the client verifies the server certificate. Standard HTTPS uses this mechanism; users can still log in via password/token.
- **mTLS (mutual TLS):** the server also requests and verifies the client's certificate. The client certificate must satisfy the trust policy, be within validity, and match the intended usage.
- **Spring Security X.509 authentication:** after the TLS layer accepts the client certificate, Spring Security extracts the identity and looks up user details and permissions in the application.

```text
Client with client.crt + client.key
           |
           | (1) TLS handshake, verifies server certificate
           | (2) Server requests client certificate, checks chain/CA/key usage
           v
Embedded Tomcat / trusted TLS terminator
           |
           | (3) Provides verified certificate chain to servlet request
           v
Spring Security FilterChainProxy
           |
           v
X509AuthenticationFilter
           |
           | (4) X509PrincipalExtractor -> application username
           v
PreAuthenticatedAuthenticationToken
           |
           v
PreAuthenticatedAuthenticationProvider
           |
           | (5) UserDetailsService / AuthenticationUserDetailsService
           |     -> account allowed? enabled? authorities?
           v
Authenticated Authentication -> SecurityContext
           |
           v
AuthorizationFilter -> endpoint/controller
```

**Trust boundary:** `X509AuthenticationFilter` **does not replace** server-side verification of certificate signatures, CAs, validity period, hostname, revocation, or the TLS handshake. Simply extracting `CN` from a text string does not prove a client is trustworthy. The TLS server must enforce certificate policy before requests reach the application.

## 3. Role and Mechanism of X509AuthenticationFilter

`org.springframework.security.web.authentication.preauth.x509.X509AuthenticationFilter` extends `AbstractPreAuthenticatedProcessingFilter`. It reads the client certificate from the Servlet request provided by the container (typically under the `jakarta.servlet.request.X509Certificate` attribute on modern Servlet/Jakarta), then uses `X509PrincipalExtractor` to obtain the principal.

Typical flow:

1. The Servlet container has completed TLS certificate verification.
2. `X509AuthenticationFilter` looks for the certificate chain in the request. If present, the filter retrieves the needed information to build an authentication request.
3. `X509PrincipalExtractor` extracts the username from the leaf certificate. Under standard configuration, this value is taken from the **Common Name (CN)** of the Subject DN.
4. `AuthenticationManager` uses `PreAuthenticatedAuthenticationProvider` to load `UserDetails`/authorities corresponding to the username.
5. On success, `Authentication` is placed in `SecurityContext` for downstream processing; the endpoint is still subject to authorization checks.
6. If the certificate is missing, no principal can be extracted, or the user does not exist/is not allowed, no valid X.509 login result is produced. The returned status depends on the TLS connector, entry point, and other authentication mechanisms.

Component responsibilities:

| Component | Responsibility | Not Responsible For |
| --- | --- | --- |
| TLS connector (Tomcat/Jetty/proxy) | Requesting and verifying the client certificate | Business permissions such as `ROLE_DEVICE` |
| `X509AuthenticationFilter` | Reading the certificate passed on the request, invoking pre-authentication | Building trust chains / checking OCSP for TLS |
| `X509PrincipalExtractor` | Selecting which application identifier to extract from the certificate | Proving that the user has admin rights |
| `PreAuthenticatedAuthenticationProvider` | Processing the pre-authentication token and loading user data | Re-verifying a user password |
| `UserDetailsService` | Looking up user, account status, and authorities | Checking whether the client holds the private key |
| `SecurityFilterChain` | Wiring filters, entry points, and policies | Enabling mTLS on the HTTPS port if server is unconfigured |

In Spring Security 6, `http.x509(...)` automatically installs `X509AuthenticationFilter` and its associated provider. **Normally, do not instantiate the filter manually and call `addFilterBefore`**: it is easy to register duplicate filters or place them in the wrong order. Only replace the filter via `x509AuthenticationFilter(...)` when you have a specific reason and understand the custom filter's manager/extractor configuration.

## 4. Preparing Spring Boot 3.x + Spring Security 6.x

Suppose the system needs to authenticate a client certificate with the following Subject DN:

```text
CN=client-alice,OU=Machines,O=Example
```

The directory/application account for `client-alice` is granted `ROLE_DEVICE`. The server certificate is for `localhost`, and the client certificate is signed by a trusted CA. Demo goal:

```text
GET https://localhost:8443/whoami
  + client certificate accepted
  + CN=client-alice
  + user exists and has ROLE_DEVICE
=> 200 OK, body: client-alice
```

The values above are examples. **You cannot make a real connection** without the corresponding server keystore, truststore, and client certificate/key.

### 4.1. Dependencies

In `build.gradle` of a Spring Boot 3.x application configured with the Spring Boot plugin and Java 17+, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-security-web` and `spring-security-config` are included in the security starter; you do not need LDAP, OAuth2, or WebFlux just to run `X509AuthenticationFilter`. Keep versions aligned via Spring Boot dependency management/BOM; do not mix different Spring Security major versions.

### 4.2. Configuring HTTPS and Requiring Client Certificates

`src/main/resources/application.yml`:

```yaml
server:
  port: 8443
  ssl:
    enabled: true

    # Server identity: server's private key and HTTPS certificate.
    key-store: ${SERVER_KEYSTORE_PATH}
    key-store-password: ${SERVER_KEYSTORE_PASSWORD}
    key-store-type: PKCS12

    # Client trust: CAs allowed to issue client certificates.
    trust-store: ${CLIENT_TRUSTSTORE_PATH}
    trust-store-password: ${CLIENT_TRUSTSTORE_PASSWORD}
    trust-store-type: PKCS12

    # need = without a valid client certificate, the TLS handshake fails.
    client-auth: need
```

Illustrative environment values:

```text
SERVER_KEYSTORE_PATH=file:/secure/server.p12
SERVER_KEYSTORE_PASSWORD=<secret-from-secret-manager>
CLIENT_TRUSTSTORE_PATH=file:/secure/client-truststore.p12
CLIENT_TRUSTSTORE_PASSWORD=<secret-from-secret-manager>
```

Do not store private keys, passwords, or production truststores in Git. The server keystore holds the private key and certificate chain used for HTTPS. The client truststore holds the trust anchors/CAs accepted by the server for clients. These two stores have distinct responsibilities; do not put the server certificate in the truststore and assume it allows all clients.

- `client-auth: need`: TLS requires a client certificate. Requests missing a certificate are typically blocked **before** Spring Security can return HTTP.
- `client-auth: want`: the server asks, but may allow clients without a certificate to complete the handshake; afterward only endpoints/mechanisms permitting anonymous or another authentication method will work. For endpoints using only X.509 and `.authenticated()`, a client without a cert is still denied.
- `client-auth: none`: the server does not request a certificate; configuring `.x509(...)` alone will not make browsers/clients send certificates automatically.

For client certificates: verify trusted CAs, Extended Key Usage `clientAuth`, Key Usage, validity period, revocation status (if enforced by infrastructure), and identity acceptance policies. For server certificates: SAN must include the hostname the client connects to, such as `DNS:localhost` for local demos.

**Note:** `server.ssl.*` applies to TLS endpoints managed by Spring Boot; if TLS terminates at a reverse proxy/load balancer, you must configure client cert requirements/verification at the proxy and have a secure mechanism to pass the verified identity (see Section 10).

### 4.3. Configuring Spring Security x509 (Servlet Application)

File `src/main/java/example/x509/X509SecurityConfig.java`:

```java
package example.x509;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class X509SecurityConfig {

    @Bean
    UserDetailsService certificateUsers() {
        UserDetails alice = User.withUsername("client-alice")
            // Required field of UserDetails only; X.509 does not use this password.
            // Do not enable HTTP Basic/form login for this demo.
            .password("{noop}!x509-only-not-a-login-password!")
            .authorities("ROLE_DEVICE")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService certificateUsers) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/whoami").hasAuthority("ROLE_DEVICE")
                .anyRequest().denyAll()
            )
            .x509(x509 -> x509.userDetailsService(certificateUsers));

        return http.build();
    }
}
```

Here:

- `.x509(...)` registers the X.509 filter in the chain; `userDetailsService(certificateUsers)` uses the defined service to look up the principal extracted from the certificate.
- The demo `UserDetailsService` contains only **one** user. Knowing `CN=client-alice` does not cause Spring Security to automatically create accounts for other valid certificates.
- `.hasAuthority("ROLE_DEVICE")` requires that exact authority. A user with a trusted certificate who has not been granted the right authority is still denied access.
- The password field in `UserDetails` does not participate in X.509 pre-authentication. Do not use such strings as real passwords; if adding Basic/form login, design proper password storage/encoders and never leave placeholder values as an active login path.
- `anyRequest().denyAll()` is a demo scoping policy, not a mandatory X.509 setting.

`src/main/java/example/x509/WhoAmIController.java`:

```java
package example.x509;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/whoami")
    public String whoAmI(Principal principal) {
        return principal.getName();
    }
}
```

`src/main/java/example/x509/X509DemoApplication.java`:

```java
package example.x509;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class X509DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(X509DemoApplication.class, args);
    }
}
```

These are standalone Java files matching the exact paths/packages; when placed in a Spring Boot application with appropriate TLS assets and dependencies, they create an X.509 authentication flow. No certificate fixtures are embedded in the code: to test live, you must supply an issued certificate chain and private key.

Run using the project's Gradle wrapper:

```bash
./gradlew bootRun
```

In Windows PowerShell, use `.\gradlew.bat bootRun` when the project includes the Gradle wrapper.

### 4.4. Sending a Request with a Client Certificate

Assuming you have `client-alice.crt`, `client-alice.key`, and a CA file for the client to verify the server, try:

```bash
curl --verbose \
  --cacert server-ca.crt \
  --cert client-alice.crt \
  --key client-alice.key \
  https://localhost:8443/whoami
```

When the hostname, server CA, client certificate, private key, and user/authority mapping are all valid, the expected body is:

```text
client-alice
```

This is the **expected HTTP response body**, not a fixed stdout from the Java app when PKI test assets are absent. In production, avoid passing private keys or passwords on the command line, in shell history, images, or CI logs. Do not use `curl -k`/`--insecure` to skip server verification when testing a secure deployment.

## 5. Extracting the Principal from a Certificate: CN, DN, and SAN

Every client certificate has a Subject DN, which may include `CN`, `OU`, `O`, `C`; modern certificates also have SANs such as `rfc822Name` (email), `dNSName`, and `uniformResourceIdentifier`. Applications must choose a stable identifier according to PKI policy rather than assuming every certificate has a unique CN.

A common X.509 configuration uses a username from CN:

```text
Subject DN = CN=client-alice, OU=Machines, O=Example
Username   = client-alice
```

`X509Configurer` offers two customization methods:

- `subjectPrincipalRegex(String)` sets a regular expression directly, used in many Spring Security 5.x/6.x examples, but **deprecated in the 7.x API**.
- `x509PrincipalExtractor(X509PrincipalExtractor)` accepts a custom extractor, better suited when you want control over identity extraction or need strong compatibility with 7.x.

Example using `SubjectDnX509PrincipalExtractor` in **Spring Security 6.x**, updating the `securityFilterChain` bean accordingly:

```java
import org.springframework.security.web.authentication.preauth.x509
    .SubjectDnX509PrincipalExtractor;

// Written inside the SecurityFilterChain method, before the http.x509(...) call:
SubjectDnX509PrincipalExtractor extractor =
    new SubjectDnX509PrincipalExtractor();

extractor.setSubjectDnRegex("CN=(.*?)(?:,|$)");

http.x509(x509 -> x509
    .x509PrincipalExtractor(extractor)
    .userDetailsService(certificateUsers)
);
```

**Java import note:** in a real Java file, `import` **must be on a single line**; the correct import syntax is:

```java
import org.springframework.security.web.authentication.preauth.x509.SubjectDnX509PrincipalExtractor;
```

The snippet above illustrates configuration lines **added inside the `SecurityFilterChain` method**, not a standalone program. The expression `(.*?)` captures the CN value; `(?:,|$)` serves as the pattern delimiter in standard DNs. The extractor class requires a regex with **one capturing group** to determine the username.

You can test the regex logic with pure JDK Java 17. File `SubjectRegexDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SubjectRegexDemo {
    public static void main(String[] args) {
        String subject = "CN=client-alice,OU=Machines,O=Example";
        Pattern pattern = Pattern.compile(
            "CN=(.*?)(?:,|$)",
            Pattern.CASE_INSENSITIVE
        );
        Matcher matcher = pattern.matcher(subject);
        System.out.println(matcher.find() ? matcher.group(1) : "NO_CN");
    }
}
```

Run command:

```bash
javac SubjectRegexDemo.java
java SubjectRegexDemo
```

**Exact stdout:**

```text
client-alice
```

This is only a **string extraction** demo. It does not read a private key, verify a certificate signature, or create a trusted `Authentication`.

### When Should You Not Rely on CN?

- Multiple users share a CN; the CA does not guarantee uniqueness; employee name changes alter the CN.
- Subjects contain commas/escaped characters and complex RDN ordering; hand-written regexes on DN strings are error-prone.
- Identity policy determines accounts via SAN URI/email, issuer serial number, or a custom normalized identifier.
- You need to enforce issuer/key usage/certificate generation or map groups from the certificate-issuing system.

In such cases, create an `X509PrincipalExtractor` matching your organization's identity model and pass it via `.x509PrincipalExtractor(...)`. SAN data can be read via `X509Certificate.getSubjectAlternativeNames()`; the API returns a collection of entries with type and value, requiring handling for missing SANs and `CertificateParsingException`. Never parse signatures/issuers yourself using unverified string parsing. Even a trusted certificate **must still be mapped** to an account permitted to use the application.

## 6. Mapping Application Users and Authorities

X.509 pre-authentication has two distinct steps:

1. **Identity:** the extractor returns `client-alice` from the certificate.
2. **Application account:** `UserDetailsService` confirms `client-alice` is a valid account, providing enabled/locked/expired flags and authorities.

The factory/configurer normally creates a `PreAuthenticatedAuthenticationProvider`. The provider uses `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>`; `.userDetailsService(...)` is a shortcut that wraps a `UserDetailsService` by username.

If you need additional data from the token, you can use `authenticationUserDetailsService(...)` (snippet inside a `SecurityFilterChain` bean):

```java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.AuthenticationUserDetailsService;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;

// Example mapping function in an environment with a real account list:
AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken> mapping =
    token -> {
        String name = token.getName();
        if (!"client-alice".equals(name)) {
            throw new UsernameNotFoundException("Client identity not registered");
        }
        return User.withUsername(name)
            .password("{noop}!not-used-by-x509!")
            .authorities("ROLE_DEVICE")
            .build();
    };

http.x509(x509 -> x509.authenticationUserDetailsService(mapping));
```

This is an **illustrative snippet inside a method that has `http`**; a real file must place `import`s at the top of the file and ensure `.x509(...)` is not registered twice. In a production application, replace the single-username check with a server-managed account/allowlist lookup and policy. **Never** derive `ROLE_ADMIN` directly from a CN or grant permissions to any CA-signed certificate without an explicit authorization policy.

Failure states must be kept separate:

| Scenario | Typical Handling |
| --- | --- |
| Certificate fails TLS verification | TLS connector rejects before the servlet |
| TLS accepts, but no principal can be extracted | X.509 authentication cannot succeed |
| Principal extracted, but no account exists | `UserDetailsService`/provider rejects |
| Valid user, but lacks `ROLE_DEVICE` | Authorization denies, typically HTTP 403 |
| User has role, but account is disabled | Account status check causes authentication failure |
| Valid user with required role | Allowed into endpoint if other security conditions pass |

Therefore, **“TLS handshake OK” does not mean “HTTP 200”**.

## 7. Why Should You Not Instantiate X509AuthenticationFilter Manually?

The standard approach:

```java
http.x509(x509 -> x509.userDetailsService(certificateUsers));
```

orders the filter into `SecurityFilterChain` and builds the related pre-authentication components. If you manually write:

```java
X509AuthenticationFilter filter = new X509AuthenticationFilter();
```

you only have a filter object that may lack the right `AuthenticationManager`, principal extractor, failure behavior, and filter ordering. In particular, if you register a `@Bean Filter` and also call `addFilter...` in Spring Security, the embedded Servlet container and `FilterChainProxy` can invoke it twice under certain configurations.

Only customize the filter when faced with requirements difficult to solve via `x509PrincipalExtractor(...)`, `authenticationUserDetailsService(...)`, or `authenticationDetailsSource(...)`. `X509Configurer.x509AuthenticationFilter(...)` lets you replace the entire filter, but you must verify lifecycle and subclass pre-authentication properties. Never modify `SecurityContextHolder` directly to fake a login in place of the pipeline.

`AbstractPreAuthenticatedProcessingFilter` includes settings such as checking for principal changes and whether to continue the chain on authentication failure; changing them must be designed alongside session management and remaining authentication methods. With multiple `SecurityFilterChain` beans, matchers/order determine which chain handles a request; `.x509(...)` on chain A does not guarantee chain B processes X.509.

## 8. Spring Security Versions: 5.x → 6.x → 7.x

| Topic | Security 5.x | Security 6.x | Security 7.x |
| --- | --- | --- | --- |
| Servlet namespace | `javax.servlet.*` | `jakarta.servlet.*` | `jakarta.servlet.*` |
| Java baseline | Depends on 5.x version used | Java 17+ | Per the 7.x line baseline and migration guide |
| Legacy adapter configuration | `WebSecurityConfigurerAdapter` existed in older releases, deprecated in 5.7 | Adapter removed | Use `SecurityFilterChain` beans |
| HTTP Security X.509 | `.x509()`/configurer previously used | Prefer `.x509(Customizer.withDefaults())` or `.x509(x -> ...)` | Prefer lambda/Customizer DSL |
| Username customization | `subjectPrincipalRegex(...)`, extractor | `subjectPrincipalRegex(...)`, or `x509PrincipalExtractor(...)` | `subjectPrincipalRegex(...)` is marked deprecated in current Javadoc; prefer `x509PrincipalExtractor(...)` |
| Where client certificate is verified | TLS/container/proxy | TLS/container/proxy | TLS/container/proxy |

**Maintainable 6.x/7.x pattern:**

```java
http
    .x509(x509 -> x509.userDetailsService(certificateUsers))
    .authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
```

To use default configuration when a suitable `UserDetailsService` exists:

```java
import static org.springframework.security.config.Customizer.withDefaults;

// Inside the HttpSecurity configuration method:
http.x509(withDefaults());
```

Note that some older X.509 guides only show the XML namespace (`<x509/>`) and `WebSecurityConfigurerAdapter`: they describe a different API version and are not recommended for Boot 3.x.

**Minor/major version details to check:** multi-factor authentication mechanisms, authority markers for authentication methods (e.g., `FACTOR_X509` in Spring Security 7.x documentation), and custom principal APIs. Do not rely on a new 7.x marker as a default assumption across 6.x applications. Check runtime versions via the dependency tree; upgrade Spring Security/Boot together and re-run mTLS tests.

## 9. Two-Layer Testing: MockMvc and Real TLS

### 9.1. Testing Mapping/Filter with MockMvc

Add the `spring-security-test` dependency. Create a test certificate with CN=`client-alice` at `src/test/resources/certs/client-alice.crt` (PEM/DER accepted by test tools), then write `src/test/java/example/x509/X509SecurityTest.java`:

```java
package example.x509;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.x509;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class X509SecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void recognizedCertificateGetsMappedToApplicationUser() throws Exception {
        mvc.perform(get("/whoami")
                .with(x509("classpath:certs/client-alice.crt")))
            .andExpect(status().isOk())
            .andExpect(content().string("client-alice"));
    }

    @Test
    void requestWithoutCertificateCannotAccessProtectedEndpoint()
            throws Exception {
        mvc.perform(get("/whoami"))
            .andExpect(status().isForbidden());
    }
}
```

For real Java compilation, the first `import static` must be written **on a single line**:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.x509;
```

`MockMvc` simulates a Servlet request that already carries a certificate chain; it is useful for testing the extractor, user lookup, authorities, and `hasAuthority` rules. **`MockMvc` does not perform a TLS handshake**, does not prove the server enabled `client-auth: need` or has the right CA, and does not check truststores/CRLs. If testing X.509 with certificate fixtures without SSL assets configured for Boot, you still need valid SSL properties in the test context or a test profile disabling SSL since MockMvc does not open a socket.

Note that the status in the missing-cert test (`403`) is the result of the demo configuration's X.509 policy and entry point **once a request has reached Spring Security**; when running real TLS with `client-auth: need`, a request without a client cert normally never reaches the HTTP layer.

### 9.2. Testing mTLS Over a Real HTTPS Port

With the server running and valid certificate files:

```bash
# Success: cert/key/CA are trusted and principal is mapped.
curl -i --cacert server-ca.crt \
  --cert client-alice.crt --key client-alice.key \
  https://localhost:8443/whoami

# No client certificate: TLS handshake usually fails when client-auth=need.
curl -v --cacert server-ca.crt https://localhost:8443/whoami
```

Test additional cases:
- Client certificate signed by a CA not accepted by the truststore.
- Expired, not-yet-valid, wrong EKU `clientAuth`, or revoked certificate (depending on policy).
- Mismatched cert/key pair.
- Valid cert whose CN has no user in `UserDetailsService`.
- Valid cert where the user exists but lacks `ROLE_DEVICE`.
- Wrong server CA or server hostname mismatching SAN when client verifies HTTPS.
- Multi-chain, certificate chain missing an intermediate, or proxy not forwarding attributes securely.

The important result is not just the HTTP status: **explicitly record whether the failure occurred at TLS handshake, authentication mapping, or authorization**. Avoid printing private keys, credentials, entire certificate chains, or sensitive data into logs.

## 10. Reverse Proxies and TLS Termination: Security Boundaries

In deployments behind ingress/nginx/load balancers:

```text
Client --mTLS--> Trusted TLS Terminator --(protected internal channel)--> Spring Boot
```

If a proxy terminates TLS, the app may **not** receive `jakarta.servlet.request.X509Certificate` as it does when Tomcat handles TLS directly. The system needs a controlled mechanism to pass the verified identity, such as a container/server integration with certificate information forwarded by the proxy over a trusted channel. Never assume `.x509(...)` automatically reads proxy-added headers.

**Never trust client-supplied headers**, such as `X-SSL-Client-Cert` or `X-Forwarded-Client-Cert`, because a client can spoof them if the proxy fails to strip incoming headers. If the architecture accepts identity from a proxy, it must simultaneously guarantee:
1. The network path to the application permits only the trusted proxy (firewall/service mesh/ACL), with no bypass paths.
2. The proxy genuinely verifies certificates, CA/CRL policies as needed, and **strips** identity headers received from outside.
3. The certificate value or identity is conveyed via verified middleware/protocols; the application knows the trusted source with certainty, rather than just parsing a header string.
4. Rotation/revocation policies, auditing, and tests for client header spoofing are in place.

The relationship: **trusted mTLS at the edge** can authenticate a client; **authorization in Spring Security** still must check the account, permissions, status, and request context.

## 11. Common Errors and Troubleshooting

| Symptom | Common Cause | Check |
| --- | --- | --- |
| `.x509(...)` is configured, yet requests without a client certificate still establish HTTPS | `server.ssl.client-auth` not enabled or TLS terminates at proxy | Inspect Tomcat/ingress config; use `curl -v` to check TLS |
| `curl` reports SSL handshake failure, bad certificate | Wrong client CA truststore, cert/key mismatch, expired cert, or wrong EKU | Check chain, issuer, SAN/EKU, key, client trust anchor |
| Valid certificate exists, but no principal in app | Container did not forward attribute, extractor cannot read CN/SAN | Check Servlet API attribute from trusted TLS connector, check extractor |
| Principal is correct, but login fails | User missing or user status disabled/locked | `UserDetailsService`, account mapping, security logs |
| Login succeeds, but HTTP 403 | Missing `ROLE_DEVICE` or denied by another authorization rule | Check `Authentication.getAuthorities()` and endpoint matchers |
| Config copied from Spring Security 5.x fails to compile on 6.x | `WebSecurityConfigurerAdapter`, `javax.servlet.*` still in code | Use `@Bean SecurityFilterChain`, `jakarta.servlet.*` |
| `subjectPrincipalRegex` method shows deprecation warning | Security 7.x recommends a dedicated extractor | Use `x509PrincipalExtractor(...)` with a clear strategy |
| Spring Boot fails to start HTTPS | Wrong keystore/truststore path, password, type, or alias | Check resource URL/permissions/store type; do not print secrets |
| Cert works directly against Tomcat, fails through proxy | TLS termination and lost chain/request attribute | Check trusted proxy integration and network bypass |
| MockMvc tests pass, but real connection fails | Unit tests only simulate request certificates, not TLS | Run real HTTPS/mTLS integration tests |
| Any cert from internal CA gets into the app | Overly broad user/role mapping or missing allowlist | Check identity uniqueness, account policy, and role groups |
| Tests pass, but renewed certs fail to access | CN/SAN/issuer changed, mapping hardcoded to subject | Design stable identifiers, manage rotation/revocation |

In configurations with only X.509 pre-authentication, `Http403ForbiddenEntryPoint` is typically configured when no other authentication entry point exists. If the app also enables form login, Basic, or multiple chains, the status/redirect on authentication failure may differ; do not claim every case returns 401 or 403.

## 12. Decisions Required in Production

1. **Where is mTLS verified?** Directly at Tomcat or at the load balancer? Who is responsible for trust anchors, revocation, and identity forwarding?
2. **Which identifier is unique?** CN is not always unique. SAN URI/email, issuer+serial, or a PKI-managed ID may fit better under organizational rules.
3. **Who does the identity map to?** Device, service, or human user? Service accounts and human accounts have different lifecycles/privileges.
4. **Where do permissions come from?** Verified database/allowlist/identity provider; do not grant roles automatically from CN/OU.
5. **What happens when certificates are revoked/rotated?** Define CA trust, CRL/OCSP, cert lifetimes, account and session invalidation, and certificate replacement rollouts.
6. **Is another login method needed?** If `client-auth=need` applies across the entire port, users without a client cert cannot reach a login form. Combining mechanisms requires proper TLS connector/host/path and policy design.
7. **What is the right level of observability?** Log handshake and authentication results in enough detail to investigate, while avoiding exposing private keys, unnecessary identifiers, and personal data from certificates.

When both layers are properly configured, mTLS verifies that **the client holds a certificate satisfying the trust policy**; `X509AuthenticationFilter` brings the certificate's identity into Spring Security's authentication mechanism; `UserDetailsService` and authorization rules decide **what that user is allowed to do**.

## 13. Official Documentation

- Spring Security 6.5, X.509 Authentication (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/x509.html
- Spring Security 7.0, X.509 Authentication: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/x509.html
- `X509Configurer` API (7.x): https://docs.spring.io/spring-security/site/docs/7.0.x/api/org/springframework/security/config/annotation/web/configurers/X509Configurer.html
- `AbstractPreAuthenticatedProcessingFilter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
- Spring Boot, SSL: https://docs.spring.io/spring-boot/reference/features/ssl.html
- Spring Boot, Application SSL Properties: https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Security Test, MockMvc Request Post Processors: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html

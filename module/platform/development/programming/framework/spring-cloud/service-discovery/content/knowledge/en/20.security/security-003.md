# Securing Eureka with Spring Security and HTTP Basic

Eureka Server stores the list of service instances and exposes HTTP APIs for clients to register, send heartbeats, update status, and query the registry. If these endpoints are open to every connection, an unauthorized system or user can read internal topology, register rogue instances, alter status, or tamper with the registry.

Spring Security can protect Eureka Server using HTTP Basic. Eureka Client automatically sends Basic Auth credentials when the server URL contains a username and password. The implementation must properly handle three parts: request authentication, CSRF handling for Eureka registration APIs, and transport encryption with HTTPS.

## 1. Eureka Protection Model

A Eureka deployment has two primary roles:

- **Eureka Server:** receives registrations, heartbeats, and status updates, and returns instance lists.
- **Eureka Client:** calls server APIs to register instances and fetch the registry.

When Spring Security is enabled on Eureka Server, requests must be authenticated before accessing the dashboard or API. With HTTP Basic, the client sends an Authorization header containing a Base64-encoded username/password pair. The server validates credentials through a UserDetailsService or AuthenticationProvider.

Registration flow:

    Eureka Client
         |
         | HTTPS + Authorization: Basic ...
         v
    Spring Security Filter Chain
         |
         | authenticate + authorize
         v
    Eureka REST API (/eureka/**)
         |
         v
    Eureka Registry

HTTP Basic only authenticates identity. It does not encrypt network traffic on its own, does not replace TLS, does not provide granular per-service authorization, and does not protect every internal channel of a Eureka cluster.

## 2. Adding Dependencies to Eureka Server

The server application needs the Eureka Server starter and the Spring Security starter.

**Maven**

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>

**Gradle**

    dependencies {
        implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-server'
        implementation 'org.springframework.boot:spring-boot-starter-security'
    }

Use a Spring Cloud BOM compatible with your Spring Boot version to manage versions. Do not pick standalone Eureka Server or Spring Security versions manually if the project already manages them via dependency management.

The Eureka Server application can start as follows:

    @SpringBootApplication
    @EnableEurekaServer
    public class EurekaServerApplication {

        public static void main(String[] args) {
            SpringApplication.run(EurekaServerApplication.class, args);
        }
    }

Simply adding Spring Security to the classpath makes Spring Boot automatically protect the web application with default settings. However, you should declare an explicit SecurityFilterChain to control which endpoints are accessible and how Eureka CSRF is handled.

## 3. Configuring SecurityFilterChain for Eureka

Eureka Client calls REST APIs under /eureka/** using HTTP methods such as POST, PUT, and DELETE. Spring Security enables CSRF protection for state-changing methods. Standard Eureka clients do not obtain or send CSRF tokens, so keeping the default setting can cause registration and heartbeat requests to be rejected with HTTP 403.

Spring Cloud Netflix recommends ignoring CSRF checks specifically for /eureka/** while still requiring authentication. Do not disable CSRF for the entire application just to make Eureka Client work.

Example using Spring Security 6 or later:

    import org.springframework.context.annotation.Bean;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.security.config.Customizer;
    import org.springframework.security.config.annotation.web.builders.HttpSecurity;
    import org.springframework.security.config.http.SessionCreationPolicy;
    import org.springframework.security.web.SecurityFilterChain;

    @Configuration
    public class EurekaSecurityConfiguration {

        @Bean
        SecurityFilterChain eurekaSecurityFilterChain(HttpSecurity http)
                throws Exception {

            http
                .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                        "/actuator/health",
                        "/actuator/health/**"
                    ).permitAll()
                    .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
                )
                .csrf(csrf -> csrf
                    .ignoringRequestMatchers("/eureka/**")
                );

            return http.build();
        }
    }

Explanation:

- /actuator/health and health groups are permitted if the platform needs to check server health without sending credentials. If public health access is not needed, require authentication for these endpoints as well.
- anyRequest().authenticated() requires login for the dashboard, API, and remaining endpoints.
- httpBasic(...) enables HTTP Basic authentication.
- STATELESS avoids relying on HTTP sessions for machine-to-machine authentication flows.
- ignoringRequestMatchers("/eureka/**") disables CSRF only for the Eureka API. Requests still must pass authentication and authorization.

If the application changes the context path or Eureka API prefix, the CSRF matcher must match the actual path. Do not broaden the matcher to /** when it is only needed for Eureka Client registration.

## 4. Configuring an Account for Test Environments

For a small Eureka Server, Spring Boot allows configuring an in-memory user via properties:

    spring:
      security:
        user:
          name: ${EUREKA_USERNAME}
          password: ${EUREKA_PASSWORD}
          roles:
            - EUREKA_CLIENT

In this example, username and password are read from environment variables instead of being hardcoded into the repository. The SecurityFilterChain in the previous section only requires authenticated; if you want to check roles, you can change the rules to:

    .requestMatchers("/eureka/**").hasRole("EUREKA_CLIENT")
    .anyRequest().authenticated()

When using hasRole("EUREKA_CLIENT"), the user must have the ROLE_EUREKA_CLIENT authority. Spring Boot's roles: EUREKA_CLIENT property automatically prepends the ROLE_ prefix.

Configuring a single user is a convenient starting point for demos or small environments. By default, Spring Boot creates an in-memory user and generates a random password when no credentials are configured; that password is only for development and is printed in startup logs. Never use this random password as a production identity management mechanism.

## 5. Authorization for Multiple Clients and Operators

When there are many services, sharing a single account across all clients makes revocation and traceability harder. You can issue separate users for each service or service group through UserDetailsService, LDAP, a database, or an internal identity system.

An illustrative example with two in-memory users:

    @Bean
    UserDetailsService eurekaUsers(PasswordEncoder encoder) {
        UserDetails inventoryClient = User.withUsername("inventory-client")
                .password(encoder.encode(
                        System.getenv("INVENTORY_EUREKA_PASSWORD")
                ))
                .roles("EUREKA_CLIENT")
                .build();

        UserDetails operator = User.withUsername("eureka-operator")
                .password(encoder.encode(
                        System.getenv("EUREKA_OPERATOR_PASSWORD")
                ))
                .roles("EUREKA_CLIENT", "EUREKA_OPERATOR")
                .build();

        return new InMemoryUserDetailsManager(
                inventoryClient,
                operator
        );
    }

Declare PasswordEncoder:

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

Include the corresponding imports:

    import org.springframework.security.core.userdetails.UserDetails;
    import org.springframework.security.core.userdetails.UserDetailsService;
    import org.springframework.security.core.userdetails.User;
    import org.springframework.security.provisioning.InMemoryUserDetailsManager;
    import org.springframework.security.crypto.password.PasswordEncoder;
    import org.springframework.security.crypto.factory.PasswordEncoderFactories;

This example illustrates distinguishing identities. InMemoryUserDetailsManager stores users in process memory and is suitable for demos or small environments; when the server restarts, the user list is recreated from configuration. Production should use a managed identity store, store hashed passwords using PasswordEncoder, and have processes for issuing, revoking, and rotating credentials.

If you need to restrict the dashboard to operators while allowing clients to call only the API, separate rules by path and role. Verify which static resources and endpoints the Eureka UI needs before applying stricter rules.

Example rule separating the API and dashboard using the two roles above:

    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/actuator/health", "/actuator/health/**").permitAll()
        .requestMatchers("/eureka/**").hasRole("EUREKA_CLIENT")
        .anyRequest().hasRole("EUREKA_OPERATOR")
    )

In this configuration, inventory-client can only call the Eureka API; eureka-operator has both EUREKA_CLIENT and EUREKA_OPERATOR, so it can use both the API and the dashboard. When declaring a custom UserDetailsService, Spring Boot no longer uses the default user from spring.security.user.* as an identity source; users must be created in UserDetailsService or the integrated authentication store.

## 6. Configuring Eureka Client to Send HTTP Basic

Spring Cloud Netflix automatically adds HTTP Basic authentication to Eureka Client if the URL in eureka.client.serviceUrl.defaultZone contains credentials in user-info format.

Example:

    eureka:
      client:
        serviceUrl:
          defaultZone: https://${EUREKA_USERNAME}:${EUREKA_PASSWORD}@eureka.internal:8761/eureka/

The client will send Basic Auth credentials when calling Eureka Server. There is no need to write a custom filter or interceptor for this simple HTTP Basic case.

defaultZone must retain the capital Z because serviceUrl is a Map and its Map keys are case-sensitive. The form default-zone is not the standard Eureka fallback key.

When the password contains special characters in the URL, percent-encode the user-info portion according to URI rules. Characters such as @, :, /, ?, or # can cause the URL to be parsed incorrectly if left unencoded. Do not encode the entire URL; encode only the username/password according to URI component rules.

Do not place credentials directly inside committed application.yml files. Use a secret manager, Kubernetes Secret, Docker secret, or platform-managed environment variables. Restrict read access to environment variables and never log URLs containing user-info.

## 7. Complete Eureka Server and Client Configuration

Example standalone Eureka Server configuration:

    server:
      port: 8761

    spring:
      application:
        name: eureka-server
      security:
        user:
          name: ${EUREKA_USERNAME}
          password: ${EUREKA_PASSWORD}
          roles:
            - EUREKA_CLIENT

    eureka:
      client:
        register-with-eureka: false
        fetch-registry: false

Combine this configuration with @EnableEurekaServer and the SecurityFilterChain from the previous section. register-with-eureka: false and fetch-registry: false are common settings for a standalone server; for a peer-aware cluster, client-side settings and peer URLs must be configured separately.

Example configuration for a service client:

    spring:
      application:
        name: inventory-service

    eureka:
      client:
        register-with-eureka: true
        fetch-registry: true
        serviceUrl:
          defaultZone: https://${EUREKA_USERNAME}:${EUREKA_PASSWORD}@eureka.internal:8761/eureka/

On startup, inventory-service uses the credentials to register and fetch the registry. If the credentials are wrong, the server returns HTTP 401 and the client cannot complete registration or fetch operations.

## 8. HTTP Basic Must Be Paired with HTTPS

HTTP Basic sends the username/password pair in the Authorization header encoded in Base64. Base64 is only a representation encoding, not security encryption. Anyone able to eavesdrop on unencrypted traffic can recover the credentials.

Therefore, never use HTTP Basic over plain HTTP on an untrusted network. Enable HTTPS on Eureka Server or terminate TLS at a trusted reverse proxy/gateway, while also protecting the internal path from the proxy to the server.

Example using a PKCS12 keystore with Spring Boot:

    server:
      port: 8761
      ssl:
        key-store: file:/etc/eureka/tls/eureka-server.p12
        key-store-type: PKCS12
        key-store-password: ${EUREKA_KEYSTORE_PASSWORD}
        key-alias: eureka-server

Clients must trust the server's certificate. If the certificate is issued by an internal CA, configure the appropriate trust store for the JVM or Eureka Client. Never disable certificate validation as a quick fix for TLS errors.

If Eureka Server requires a client certificate, that is mutual TLS. Spring Cloud Netflix provides eureka.client.tls.* properties to configure the key store and trust store on the client. mTLS adds authentication at the TLS layer; it differs from HTTP Basic and can be used alongside Basic Auth.

## 9. Protecting the Dashboard and Actuator

Eureka Server serves both the dashboard and the HTTP API under /eureka/*. When using anyRequest().authenticated(), the dashboard also requires Basic Auth.

Actuator is a separate administrative surface. Expose only the endpoints that are genuinely needed:

    management:
      endpoints:
        web:
          exposure:
            include: health,info
      endpoint:
        health:
          show-details: never

If the health endpoint is permitted without authentication in SecurityFilterChain, keep health details non-sensitive. Do not expose env, configprops, beans, mappings, or broad admin endpoints to public networks just for convenience.

Dashboard and registry endpoints can reveal service names, hostnames, IPs, ports, zones, and internal metadata. Treat registry data as sensitive operational information and restrict access accordingly.

## 10. Testing Authentication with curl

You can verify that the server requires credentials by calling the registry API without login details:

    curl -i https://eureka.internal:8761/eureka/apps

If the server is properly protected, a request without credentials typically receives HTTP 401 Unauthorized and a WWW-Authenticate: Basic header.

Call again with credentials:

    curl -i \
      --user "$EUREKA_USERNAME:$EUREKA_PASSWORD" \
      -H "Accept: application/json" \
      https://eureka.internal:8761/eureka/apps

If the credentials are valid and the endpoint is working, the server returns HTTP 200 along with the registry contents. An empty registry can still return 200; this does not mean instances are already registered.

Test an incorrect password:

    curl -i \
      --user "$EUREKA_USERNAME:wrong-password" \
      -H "Accept: application/json" \
      https://eureka.internal:8761/eureka/apps

The expected result is 401. Never put real passwords into command history or shared documentation. In automated testing environments, pull credentials from the pipeline's secret store and avoid printing variables to logs.

## 11. Verifying Client Registration and Heartbeats

After confirming the server accepts Basic Auth, start a Eureka Client with the URL containing credentials.

Verify:

1. Client logs show the instance registered successfully.
2. Eureka Dashboard displays the correct application name and instance ID.
3. The client continues sending heartbeats without receiving 401 or 403.
4. Another consumer can fetch the registry using valid credentials.
5. Requests without credentials are rejected.
6. Requests to the health endpoint are handled according to the configured rule.

Do not verify only via a browser dashboard. A browser may retain session credentials, while a client service may still be using different credentials or a misconfigured URL.

## 12. Limitations of HTTP Basic in Eureka

HTTP Basic is a simple way to do machine-to-machine authentication, but it has several limitations:

- Credentials are often embedded in the Eureka Client URL; configuration and logs must be protected.
- Standard defaultZone configuration is generally convenient only for a single shared credential set.
- Eureka has a limitation with multiple server URLs using different Basic Auth credentials: per-server credentials in the list are not supported, and only the first credentials found are used.
- Basic Auth does not provide distinct per-instance identities if all clients share one user.
- Basic Auth does not encrypt traffic on its own; HTTPS remains mandatory on untrusted networks.
- Basic Auth does not replace role-based authorization or network policies.

If more sophisticated authentication is required, Spring Cloud Netflix allows creating DiscoveryClientOptionalArgs and adding a ClientFilter to customize client-to-server requests. Evaluate an authentication mechanism suited to your infrastructure instead of manually extending it when HTTP Basic already meets requirements.

## 13. Special Considerations When Running a Eureka Cluster

Protecting client requests with Spring Security does not mean all requests between Eureka Server peers are also protected by the same filter chain.

Spring Cloud Netflix notes that replication requests between Eureka Servers, such as /eureka/peerreplication/..., are internal requests and do not pass through standard Spring Security filters. Therefore, the SecurityFilterChain configuration above does not automatically protect peer replication.

When deploying multiple Eureka Servers:

- Restrict peer communication to internal networks.
- Use firewalls or security groups that permit only legitimate peers.
- Consider TLS/mTLS for communication between peers.
- If authentication headers must be added to replication, configure ReplicationClientAdditionalFilters per Spring Cloud Netflix guidance.
- Test client registration and peer replication as two separate flows.
- Do not assume Basic Auth in the client URL automatically protects peer replication.

If a peer cannot replicate, servers may end up with inconsistent registry states. Monitor peer replication and verify network configuration, TLS, and custom filters separately.

## 14. Troubleshooting Common Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Client receives 401 | Wrong or missing username/password | Check the server secret and the client's defaultZone URL |
| Client receives 403 on registration | CSRF still blocks POST/PUT or user lacks permissions | Check the /eureka/** matcher and authorization rules |
| Dashboard repeatedly prompts for login | Wrong credentials, nonexistent user, or proxy strips Authorization header | Call the API directly with curl and check the proxy |
| GET registry succeeds but registration fails | CSRF matcher not applied to the API path or method blocked | Inspect POST/PUT requests and security logs |
| Client does not send Basic Auth | URL lacks valid user-info or service URL config is wrong | Check defaultZone, placeholders, and client logs |
| Password with @ or : breaks URL | User-info not percent-encoded | Encode username/password individually |
| TLS handshake fails | Client does not trust certificate or hostname mismatch | Check trust store, CA, and SAN |
| A peer does not receive replication | Peer replication bypasses standard Spring Security filters | Check network, TLS, and ReplicationClientAdditionalFilters |
| Actuator health returns 401 | Security rule does not permit health endpoint or matcher mismatch | Check actual endpoint path and policy |
| Credentials appear in logs | URL containing user-info was logged | Mask URLs, disable sensitive logging, and rotate exposed secrets |

When diagnosing, distinguish between:

- 401 Unauthorized: credentials could not be authenticated.
- 403 Forbidden: authenticated but lacking permissions, or request rejected by CSRF.
- 404 Not Found: wrong context path or Eureka URL.
- SSLHandshakeException: TLS/certificate error, not a Basic Auth error.

Do not disable CSRF application-wide to fix a Eureka 403 error. Verify that the request falls under /eureka/** and that the matcher is applied properly.

## 15. Credential Management and Secure Operations

Principles to apply:

- Create separate credentials for each Eureka Client or client group when independent revocation is required.
- Use a secret manager or platform secrets to supply username/password.
- Never commit credentials, bake them into image layers, or print them in logs.
- Rotate passwords via a controlled process; update clients and servers to avoid registration disruption.
- Use an appropriate password encoder when managing UserDetailsService yourself.
- Restrict registry read and dashboard permissions by role.
- Protect Actuator, reverse proxies, and internal transport channels.
- Monitor authentication failure counts, request sources, and anomalous registration changes.
- Use HTTPS and verify certificates on both client and server.
- When running Eureka peers, protect peer replication separately from the client authentication flow.

Basic Auth fits simple setups or controlled internal networks. If requirements call for per-workload identities, short-lived tokens, granular authorization, or per-service auditing, evaluate stronger authentication mechanisms instead of a single long-lived shared password.

## 16. Step-by-Step Implementation Procedure

You can implement in the following order for easier testing:

1. Add the Eureka Server starter and Spring Security starter.
2. Create the Eureka Server using @EnableEurekaServer.
3. Configure HTTPS and certificates before transmitting credentials.
4. Declare users or UserDetailsService.
5. Create a SecurityFilterChain requiring authentication for the dashboard and API.
6. Ignore CSRF specifically for /eureka/** while keeping other CSRF rules.
7. Expose minimal health endpoints and secure remaining Actuator endpoints.
8. Use curl to confirm no credentials returns 401 and valid credentials return 200.
9. Configure Eureka Client defaultZone with credentials from secrets.
10. Start the client and verify registration, heartbeats, and registry fetching.
11. If running a cluster, test peer replication and protect peer communication separately.
12. Verify logs, auditing, and credential rotation procedures before going to production.

Execute each step in a test environment first. When changing passwords, you can roll out in phases: add the new credential on the server, update clients, verify clients work, and then revoke the old credential if the user store supports two credentials concurrently.

## 17. Conclusion

Spring Security protects Eureka Server by requiring authentication for the dashboard and HTTP APIs. HTTP Basic can be enabled via SecurityFilterChain; CSRF must be ignored specifically for /eureka/** because Eureka Client does not send CSRF tokens when registering and updating instances. On the client side, Spring Cloud Netflix automatically sends Basic credentials when the eureka.client.serviceUrl.defaultZone URL includes a username and password.

This configuration is only complete when paired with HTTPS, secret management, authorization, and real-world functional verification. In a Eureka cluster, peer replication is a separate flow that bypasses standard Spring Security filters and must be protected additionally. Verify API authentication, client registration, heartbeats, the dashboard, and peer replication before broad deployment.

## References

- [Spring Cloud Netflix — Securing the Eureka Server](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Authenticating with the Eureka Server](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Boot — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Boot — Configure SSL for Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617.html)

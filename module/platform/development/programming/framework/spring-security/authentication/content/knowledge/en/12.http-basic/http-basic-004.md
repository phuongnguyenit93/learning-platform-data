# Base64 Is Not Encryption and the Requirement for HTTPS in HTTP Basic

> **Key point:** HTTP Basic sends the username and password pair encoded in Base64. Base64 is only a data representation format, not a way to hide secrets. When using HTTP Basic, every request containing credentials must be transmitted over HTTPS with a properly verified certificate.

## 1. What Does HTTP Basic Actually Send?

According to RFC 7617, the client constructs the string **username:password**, converts that string into bytes using an agreed-upon character encoding, and encodes it in Base64. The Base64 part is placed in the **Authorization** header after the **Basic** prefix.

Example with the illustrative account **alice** and dummy password **demo-pass**:

~~~http
GET /hello HTTP/1.1
Host: api.example.com
Authorization: Basic YWxpY2U6ZGVtby1wYXNz
~~~

The string **YWxpY2U6ZGVtby1wYXNz** can be decoded back instantly into **alice:demo-pass**. Seeing unreadable-looking characters does not mean they are secured. Passwords in examples are for learning only; never use real passwords in documentation or illustrative commands.

The HTTP Basic flow typically proceeds as follows:

1. The client requests a resource requiring authentication without providing credentials.
2. The server returns **401 Unauthorized**, typically with a **WWW-Authenticate** challenge announcing the Basic scheme and realm.
3. The client resends the request with **Authorization: Basic ...**. Some clients may proactively send this header on the very first request.
4. Spring Security uses **BasicAuthenticationFilter** to read the credentials, create a **UsernamePasswordAuthenticationToken**, and pass it to **AuthenticationManager** for verification.
5. With the right password and sufficient permissions, the request is processed; invalid credentials typically result in **401**. If authenticated but lacking permissions, the server usually returns **403 Forbidden**.

Example challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo"
~~~

Do not treat the challenge as a prerequisite for sending the password: a client configured for preemptive Basic can include the **Authorization** header on the first request. Therefore, even a single HTTP hit followed by a redirect to HTTPS can leak the password.

## 2. How Does Encoding Differ from Encryption and Hashing?

| Mechanism | Purpose | Reversible? | Role in this lesson |
| --- | --- | --- | --- |
| **Base64 encoding** | Represent bytes using characters suitable for text protocols | Yes, no key required | Packages the username/password pair for HTTP Basic |
| **Encryption** | Protect confidentiality using an algorithm and a key | Yes, with the right key | TLS encrypts data in transit over HTTPS |
| **Password hashing** | Store and verify passwords without saving plaintext passwords | No direct decryption; verified by comparison | BCrypt/Argon2 used when storing passwords server-side |

Merely switching Base64 to hex, URL encoding, or another string transformation still provides no security. **Base64 is not cryptographic encryption, uses no key, and provides no confidentiality.** Changing the representation algorithm does not solve network eavesdropping.

### Runnable Experiment with Java 17+

Save the following code into **BasicBase64Demo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicBase64Demo {
    public static void main(String[] args) {
        String credentials = "alice:demo-pass";

        String token = Base64.getEncoder().encodeToString(
                credentials.getBytes(StandardCharsets.UTF_8));

        String restored = new String(
                Base64.getDecoder().decode(token),
                StandardCharsets.UTF_8);

        System.out.println("Token: " + token);
        System.out.println("Decoded: " + restored);
    }
}
~~~

Compile and run:

~~~bash
javac BasicBase64Demo.java
java BasicBase64Demo
~~~

Exact output:

~~~text
Token: YWxpY2U6ZGVtby1wYXNz
Decoded: alice:demo-pass
~~~

No password or decryption key is needed to recover the credential pair. The Java snippet uses UTF-8 for a consistent experiment; in real HTTP Basic, pay attention to charset rules and client/server compatibility under RFC 7617 when using non-ASCII characters.

## 3. Why Must HTTPS/TLS Be Used?

If a Basic header is sent over **HTTP**, anyone able to read traffic in transit can capture the header, Base64-decode it, and obtain the password. They can then reuse that password to impersonate the user. HTTP also does not protect integrity on its own, so an intermediary can tamper with request/response contents.

**HTTPS** establishes a TLS connection before sending HTTP messages. With a server certificate verified for the correct domain name and trust chain, TLS provides:

- **Confidentiality in transit:** the Authorization header, path, and HTTP payload travel inside the encrypted portion of the TLS connection.
- **Integrity protection:** detects unauthorized modification of data in transit.
- **TLS endpoint authentication:** gives the client evidence that it is connecting to the server issued the certificate, mitigating man-in-the-middle spoofing attacks.

Comparison examples:

| Scenario | Consequence |
| --- | --- |
| HTTP + Basic | The Base64 header can be read and reversed into a password if traffic is eavesdropped. **Unsafe.** |
| HTTPS + Basic, valid certificate | Passive observers on the wire cannot directly read HTTP headers. **This is the minimum requirement when using Basic.** |
| HTTPS, but the app/proxy logs Authorization | Anyone reading logs still obtains credentials. TLS does not protect data after decryption at the TLS termination point. |
| HTTPS to reverse proxy, but proxy → backend uses HTTP | Data on the backend hop can be exposed if the intermediate network is untrusted; protect internal hops according to the threat model. |
| HTTP returns 301/302 redirect to HTTPS | The first HTTP request may already carry credentials. Redirects **cannot undo** sending secrets before TLS is established. |

Three things to distinguish:

1. **HTTPS protects data in transit**, which does not mean passwords stored in the database are safe: the server still needs an appropriate password hashing function.
2. **Wherever HTTPS terminates, data is decrypted there**: web servers, load balancers, or reverse proxies can see headers; you must control logs, access rights, and hops after TLS termination.
3. **HTTPS does not replace authentication policy**: HTTP Basic still reuses the same credentials per request; you need strong passwords, access controls, rate limiting, and credential revocation/rotation mechanisms.

### Redirects and HSTS Assist, but Do Not Replace HTTPS

You can configure Spring Security to redirect HTTP requests to HTTPS and send the **Strict-Transport-Security** header on HTTPS responses so browsers prefer HTTPS on future visits. However, a browser only learns HSTS after receiving the policy over a trusted HTTPS connection (aside from preloading). For API clients, configure HTTPS URLs from the start, never send credentials to HTTP URLs, and never ignore certificate errors.

A strict deployment exposes only HTTPS endpoints for APIs using Basic; if an HTTP port is needed solely for redirection, ensure clients never send credentials on that port.

## 4. Applying It in Spring Security (Servlet)

This example targets a **Servlet/MVC** Spring Boot application, Java 17+, with **Spring Web** and **Spring Security** dependencies. Below are complete classes to place in the **com.example.demo** package of a Spring Boot project created with Spring Initializr; the Spring Boot bootstrap is provided by the project. The example works with modern Spring Security 6.5+/7.x configuration APIs.

### 4.1. Enable HTTP Basic and Require HTTPS

Create **src/main/java/com/example/demo/SecurityConfig.java**:

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .redirectToHttps(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String rawPassword) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(rawPassword))
                        .roles("READER")
                        .build());
    }
}
~~~

Explanation:

- **httpBasic(...)** adds Basic header processing to the filter chain. When providing a custom SecurityFilterChain, enable HTTP Basic explicitly.
- **authorizeHttpRequests(...)** requires an authenticated user for all endpoints.
- **redirectToHttps(...)** helps redirect HTTP requests to HTTPS **if** the server/proxy receives HTTP requests. It does not generate certificates and does not open a TLS port on its own: TLS must be configured on the server or reverse proxy.
- **BCryptPasswordEncoder** hashes passwords stored on the server. It does not change the fact that Basic transmits passwords in headers, so HTTPS is still required.
- The demo password is read from an environment variable rather than hardcoded in source code. The example uses an in-memory user to focus on Basic; real applications use an appropriate user store.

Create **src/main/java/com/example/demo/HelloController.java**:

~~~java
package com.example.demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello(Authentication authentication) {
        return "Xin chao, " + authentication.getName() + "!";
    }
}
~~~

### 4.2. Configuring HTTPS for Spring Boot

In **src/main/resources/application.properties**:

~~~properties
server.port=8443
server.ssl.key-store=file:./local-demo.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=local-demo
demo.user.password=${DEMO_USER_PASSWORD}
~~~

For the localhost exercise, generate a PKCS#12 keystore and export a locally trusted certificate using the JDK **keytool**. Run these commands from the project root directory:

~~~bash
keytool -genkeypair -alias local-demo -keyalg RSA -keysize 2048 -validity 7 -storetype PKCS12 -keystore local-demo.p12 -storepass local-only-demo -dname "CN=localhost" -ext SAN=dns:localhost
keytool -exportcert -rfc -alias local-demo -keystore local-demo.p12 -storepass local-only-demo -file local-demo.crt
~~~

POSIX environment example (Linux/macOS):

~~~bash
export TLS_KEYSTORE_PASSWORD=local-only-demo
export DEMO_USER_PASSWORD=demo-pass
./mvnw spring-boot:run
~~~

In PowerShell on Windows, set the two variables with **$env:TLS_KEYSTORE_PASSWORD = "local-only-demo"** and **$env:DEMO_USER_PASSWORD = "demo-pass"**, then run the Maven wrapper **mvnw.cmd spring-boot:run** in the project directory.

**Use the self-signed certificate and passwords above only for localhost.** Never commit PKCS#12 files containing private keys, passwords, or test-issued certificates to a repository. In production, use valid certificates, centralized secret management, and configure TLS at the web server or ingress.

With the Spring Boot HTTPS configuration above, the application listens on port **8443** with TLS and by default no longer has an HTTP connector on **8080**. Therefore, not being able to reach the HTTP port is normal; you do not need to open an extra HTTP port just to observe a redirect.

### 4.3. Testing with curl

After the application starts, run in the directory containing **local-demo.crt**:

~~~bash
curl --cacert local-demo.crt -i https://localhost:8443/hello
curl --cacert local-demo.crt -i -u alice:demo-pass https://localhost:8443/hello
curl --cacert local-demo.crt -i -u alice:sai https://localhost:8443/hello
~~~

Expected results in order:

1. **401 Unauthorized**: no credentials sent.
2. **200 OK**, body **Xin chao, alice!**: valid credentials.
3. **401 Unauthorized**: incorrect password.

The **--cacert** option tells curl to verify the self-signed certificate using the exported certificate for localhost; do not use **-k/--insecure** to bypass TLS verification. The **-u alice:demo-pass** flag is only for dummy credentials in a lab: on real machines, command lines and shell history can expose passwords; use secure secret input methods suited to your environment.

## 5. Secure Deployment Checklist

- **Force clients to use https:// URLs from the first request.** Reject API client configurations pointing to http://; do not treat Base64 or redirects as security controls.
- **Verify TLS certificates.** Validate hostnames, trust chains, and certificate validity; never disable verification just to make the app "work".
- **Configure HTTPS on the right hops.** If TLS terminates at a load balancer or API gateway, evaluate and protect the connection to the backend. Only trust **Forwarded/X-Forwarded-Proto** headers set by trusted proxies; prevent external clients from spoofing these headers.
- **Do not log secrets.** Mask or strip Authorization, cookies, and passwords from access logs, tracing, error messages, and debugging screenshots. Never put credentials in URLs.
- **Store passwords properly.** Use a strong PasswordEncoder (such as BCrypt), password policies, retry rate limits, and account lock/revocation or credential rotation as appropriate.
- **Keep other protection layers.** HTTPS does not replace authorization, CSRF protection where required by the application, access monitoring, or browser security. Never disable CSRF just to make an HTTP Basic example work.
- **Assess Basic's suitability.** For simple internal APIs or machine-to-machine clients with managed secrets, Basic over HTTPS may be acceptable by design. When user login, MFA, session-based permissions, or short-lived tokens are needed, consider modern alternatives; any bearer token still requires TLS.

## 6. Quick Questions to Build Accurate Understanding

**Q: The Basic header looks like a secret string; why isn't it safe enough?** Because anyone with the Base64 token can decode it back into username:password. No key is needed.

**Q: Passwords are already BCrypt-hashed in the database; can HTTP be used?** No. BCrypt protects records stored on the server; HTTP Basic still places the client-known password in a header over the wire. The two layers address different risks.

**Q: Is redirecting HTTP to HTTPS enough?** Not guaranteed. If a client sends Authorization on the initial HTTP request, the credentials are already exposed before the redirect response arrives. Clients must start with HTTPS.

**Q: Does HTTPS protect you if a reverse proxy decrypts the request and writes all headers to logs?** No. TLS only protects traffic between TLS termination endpoints; logs must still be controlled and scrubbed of secrets.

**Q: With HTTPS, does Basic become completely secure authentication?** No. TLS reduces eavesdropping and tampering in transit, but passwords can still be compromised via breached endpoints, phishing, logs, or compromised clients.

## 7. References

- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): definition of Base64 tokens, credentials, and security considerations.
- [Spring Security — Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html): BasicAuthenticationFilter flow and SecurityFilterChain.
- [Spring Security — HTTP/HTTPS Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/http.html): HTTPS redirects, HSTS, and proxy configuration.
- [Spring Boot — Embedded Web Servers / SSL](https://docs.spring.io/spring-boot/how-to/webserver.html): server.ssl configuration and the difference between HTTP and HTTPS connectors.

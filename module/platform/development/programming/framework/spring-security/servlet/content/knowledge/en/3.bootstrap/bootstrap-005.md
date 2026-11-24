# Creating Your First SecurityFilterChain and UserDetailsService Beans

## Goal

In a Spring Boot application running on the **Servlet stack** (typically using Spring MVC), the first two beans to master when configuring Spring Security yourself are **SecurityFilterChain** and **UserDetailsService**.

After this lesson, you will be able to:

1. Create a SecurityFilterChain bean to specify which HTTP requests are publicly accessible, which require login, and which are reserved for administrators.
2. Create a UserDetailsService bean providing test users in memory, paired with a PasswordEncoder to verify passwords.
3. Run a complete Spring Boot example and verify **200 OK**, **401 Unauthorized**, and **403 Forbidden** responses yourself.
4. Explain the path of an HTTP Basic request: SecurityFilterChain → identity authentication → authorization check → controller.
5. Recognize the limitations of a starter configuration before deploying to production.

This lesson focuses on **building the first two beans and verifying their behavior**. More complex login systems such as database user stores, OAuth2/OIDC, JWT, multiple security chains, method-level security, and data-level authorization will require additional configuration and dedicated knowledge.

## 1. Why Are Two Different Beans Needed?

Each bean answers a different question:

| Bean | Responsibility | Example |
| --- | --- | --- |
| **SecurityFilterChain** | Configures the security filters and policies applied to HTTP requests | GET /public is public; GET /profile requires login; GET /admin requires role ADMIN |
| **UserDetailsService** | Looks up and returns user details by username for the authentication mechanism to use | Look up username student, return the hashed password and ROLE_USER |

Imagine a building:

- **SecurityFilterChain** is like the door access system: deciding which doors are open to the public, which require presenting a badge, and which require admin privileges.
- **UserDetailsService** is like the employee directory: looking up an identity profile from a username. By itself, it **does not decide** which doors that person may enter.
- **PasswordEncoder** verifies passwords in a securely stored format; the authentication mechanism uses it alongside UserDetailsService data.
- **AuthenticationManager/AuthenticationProvider** coordinates the components to authenticate credentials. Do not think of UserDetailsService as comparing passwords or granting HTTP access on its own.

**Key takeaway:** SecurityFilterChain holds the rules protecting requests; UserDetailsService supplies user data for the authentication system. Both must be configured properly to observe login and authorization.

## 2. Prerequisites and Project Structure

This example uses:

- JDK **17 or newer** (also compatible with JDK 21).
- Spring Boot **3.3.13**, on the branch using Spring Security **6**.
- Maven, Spring MVC/Servlet application.
- Two primary dependencies: **spring-boot-starter-web** and **spring-boot-starter-security**.
- Users stored **in memory** to keep the focus on the first two beans.

Directory tree:

~~~text
security-first-beans/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── securitydemo/
                        ├── SecurityDemoApplication.java
                        ├── SecurityConfig.java
                        └── DemoController.java
~~~

Place the three Java classes in the same package com.example.securitydemo so @SpringBootApplication discovers @Configuration and @RestController via component scanning.

### pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>security-first-beans</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

You do not need to declare Spring Security's version directly: the Spring Boot parent manages compatible dependency versions. Avoid mixing Spring Framework and Spring Security versions arbitrarily.

### SecurityDemoApplication.java

~~~java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
~~~

This class is the entry point. When run, Spring creates the ApplicationContext, discovers the @Bean methods in SecurityConfig, and registers the corresponding beans.

## 3. Creating Your First SecurityFilterChain Bean

Create the file **src/main/java/com/example/securitydemo/SecurityConfig.java** with the following content:

~~~java
package com.example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder passwordEncoder) {
        UserDetails student = User.withUsername("student")
            .password(passwordEncoder.encode("student123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(passwordEncoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(student, admin);
    }
}
~~~

**This is a runnable configuration for a learning environment.** The accounts and passwords written directly in source are for simulation only; never put these sample passwords into a real system.

### Explaining Each Part of SecurityFilterChain

**1. @Configuration and @Bean**

@Configuration marks a class containing bean definitions. The @Bean method returns SecurityFilterChain; Spring manages the result as a bean in the ApplicationContext. The method name can vary; the SecurityFilterChain **bean type** is what matters.

**2. HttpSecurity Provided by Spring**

The HttpSecurity parameter is a builder for declaring security configuration for a filter chain. The statement **return http.build()** constructs the actual SecurityFilterChain from that configuration. If you omit @Bean or forget to call build(), Spring will not register your chain as intended.

**3. authorizeHttpRequests Decides Permissions for URLs**

- **requestMatchers(HttpMethod.GET, "/public").permitAll():** only GET /public is allowed through the request authorization layer without logging in.
- **requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN"):** GET /admin requires the ROLE_ADMIN authority.
- **anyRequest().authenticated():** all remaining requests must be authenticated; this is the final catch-all rule so new endpoints are not accidentally left open.

Rules are evaluated in declaration order. Place specific conditions before broad ones. For example, if you write anyRequest().authenticated() before the /admin rule, the later rule will never get a chance to decide permissions as intended.

**4. HTTP Basic for a Simple Example**

**httpBasic(Customizer.withDefaults())** enables HTTP Basic; curl can send username/password in the Authorization header. HTTP Basic only encodes the username/password pair in Base64, **it does not encrypt secrets**. Always use HTTPS in real deployments. The local http://localhost:8080 example is strictly for learning.

**5. Disabling Form Login to Keep Lesson Behavior Clear**

**formLogin(AbstractHttpConfigurer::disable)** only disables form login in this chain; it **does not disable authentication** and does not disable HTTP Basic. As a result, requests lacking credentials to protected endpoints receive an HTTP Basic challenge instead of being redirected to an HTML login page.

**6. What This Configuration Does Not Do**

This configuration does not yet enable method-level authorization, does not support database users, does not build JSON/JWT login, and does not define resource-ownership policies. It still includes Spring Security's default protections, including CSRF protection for applicable requests; enabling HTTP Basic does not mean CSRF is automatically disabled.

### Why Create a Custom SecurityFilterChain?

When you add spring-boot-starter-security without declaring your own chain, Spring Boot provides a default web security configuration. Once you register your own **SecurityFilterChain bean**, Boot's default security chain backs off so you can define your HTTP policy yourself. Spring Security remains the provider that builds and executes the underlying filters.

There is no need to extend WebSecurityConfigurerAdapter: that approach was removed in Spring Security 6. For modern configuration, use a SecurityFilterChain bean with the lambda DSL.

## 4. Creating Your First UserDetailsService and PasswordEncoder

Both beans are already in SecurityConfig, but it is important to understand why.

### What Does UserDetailsService Do?

The UserDetailsService interface has one central method:

~~~java
UserDetails loadUserByUsername(String username)
    throws UsernameNotFoundException;
~~~

An implementation takes a username, looks up user details, and returns a **UserDetails** containing username, password hash, authorities, and account status flags. The example uses the built-in **InMemoryUserDetailsManager**; you do not need to write a custom class implementing UserDetailsService.

When an HTTP Basic request arrives:

1. The filter extracts the username and password from the Authorization header.
2. The configured authentication mechanism invokes AuthenticationManager/AuthenticationProvider.
3. For username/password authentication via UserDetailsService, the provider fetches UserDetails by username.
4. PasswordEncoder compares the submitted password against the stored password hash.
5. On success, Authentication carries the identity and authorities for rules in SecurityFilterChain to check.

UserDetailsService **does not** read HTTP requests itself, **does not** decide which URLs are accessible, and **does not** return HTTP 200/401/403 directly.

### Why Add PasswordEncoder?

Passwords in UserDetails must be stored in a format that the authentication mechanism can verify securely. In the example:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}
~~~

BCryptPasswordEncoder uses a password hashing algorithm suitable for the example. Inside userDetailsService, **passwordEncoder.encode("student123")** produces the hash string for the sample password. On login, Spring Security verifies by matching the submitted password against the hash, never by comparing plaintext against a hash with equals.

BCrypt usually produces a different hash value for the same password due to salting; this is normal behavior. Because InMemoryUserDetailsManager is created at application startup, sample users are reset on restart.

**Do not use {noop} or store plaintext in production.** In real applications, passwords are registered and stored as hashes when accounts are created; when reading from a database, UserDetailsService must return the stored hash faithfully.

### Roles and GrantedAuthority

~~~java
User.withUsername("admin")
    .password(passwordEncoder.encode("admin123"))
    .roles("ADMIN")
    .build();
~~~

Under default configuration, **roles("ADMIN")** creates the **ROLE_ADMIN** authority. Thus **hasRole("ADMIN")** corresponds to the ROLE_ADMIN authority. If you use **hasAuthority("ADMIN")**, Spring Security looks for the exact authority named ADMIN without automatically adding ROLE_; the two are not arbitrarily interchangeable.

In the example, student has ROLE_USER and admin has ROLE_ADMIN. Admin does not get ROLE_USER by default; grant all required authorities when designing real roles.

### Difference Between Beans and User Objects

There is **one** UserDetailsService bean here, yet it manages **two** UserDetails objects. The number of users is not the number of beans. Spring does not create a separate UserDetailsService bean per user.

Defining a custom UserDetailsService also causes Spring Boot's default in-memory user with an auto-generated password to back off. So when running the example, use student/student123 or admin/admin123 directly instead of looking for a random password in the logs.

## 5. Creating a Controller to Test

Create the file **src/main/java/com/example/securitydemo/DemoController.java**:

~~~java
package com.example.securitydemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "Hello, everyone!";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "Hello, " + authentication.getName() + "!";
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "Admin dashboard";
    }
}
~~~

In /profile, the Authentication parameter supplied by Spring Security/Spring MVC represents the authenticated identity. When sending student's credentials, **authentication.getName()** returns **student**. Using this parameter does not mean the controller authenticates passwords itself; the request already passed through the filter chain before the controller was invoked.

Three GET endpoints are sufficient for verification:

- /public: viewable by anyone.
- /profile: viewable by any validly logged-in user.
- /admin: viewable only by someone with ROLE_ADMIN.

## 6. Running the Application and Testing Each Scenario

In the **security-first-beans/** directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Wait for the application to start successfully on port 8080. The commands below use curl syntax; in Windows PowerShell use **curl.exe** to avoid the legacy PowerShell alias. You can replace curl with curl.exe without changing the arguments.

### Testing a Public Request

~~~bash
curl -i http://localhost:8080/public
~~~

Expected key result:

~~~http
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8

Hello, everyone!
~~~

Other headers may appear from default security headers or the web server. The goal is to verify status 200 and body **Hello, everyone!**.

### Testing a Protected Request Without Logging In

~~~bash
curl -i http://localhost:8080/profile
~~~

Expected key result:

~~~http
HTTP/1.1 401
WWW-Authenticate: Basic realm="Realm"
~~~

The WWW-Authenticate details may vary depending on configuration; status **401** is what to observe. Because the request lacks valid credentials, it is not allowed into /profile.

### Logging In as student

~~~bash
curl -i -u student:student123 http://localhost:8080/profile
~~~

Expected key result:

~~~http
HTTP/1.1 200

Hello, student!
~~~

The **-u student:student123** flag makes curl create a Basic Authorization header; the endpoint reads the authenticated Authentication's name.

### Student Attempting to Access /admin

~~~bash
curl -i -u student:student123 http://localhost:8080/admin
~~~

Expected key result:

~~~http
HTTP/1.1 403
~~~

The user student is authenticated, yet lacks ROLE_ADMIN, and is therefore denied by the authorization rule.

### Admin Accessing /admin

~~~bash
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

Expected key result:

~~~http
HTTP/1.1 200

Admin dashboard
~~~

### Testing a Wrong Password

~~~bash
curl -i -u student:wrong-password http://localhost:8080/profile
~~~

The expected key result is **401**, because the credentials are invalid. A valid username with a wrong password does not produce an authenticated user.

| Request | Credentials | Key result | Reason |
| --- | --- | --- | --- |
| GET /public | None | 200 + Hello, everyone! | permitAll |
| GET /profile | None | 401 | Authentication required |
| GET /profile | student/student123 | 200 + Hello, student! | Authentication succeeded |
| GET /admin | student/student123 | 403 | Missing ROLE_ADMIN |
| GET /admin | admin/admin123 | 200 + Admin dashboard | Has ROLE_ADMIN |
| GET /profile | student/wrong-password | 401 | Wrong password |

**401 and 403 are different:** 401 generally indicates valid credentials are required; 403 generally indicates the request lacks authorization or was rejected by another protection mechanism. Do not assume every 403 is caused by a wrong role, because for instance CSRF can also return 403.

## 7. Tracing a Request from Start to Finish

Consider the command:

~~~bash
curl -i -u student:student123 http://localhost:8080/profile
~~~

Conceptual processing flow:

~~~text
Client
  |
  | GET /profile
  | Authorization: Basic ...
  v
Servlet container
  |
  v
DelegatingFilterProxy -> springSecurityFilterChain
  |
  v
FilterChainProxy -> configured SecurityFilterChain
  |
  +-- HTTP Basic filter reads credentials
  |       |
  |       +-- Provider authenticates username/password
  |               |
  |               +-- UserDetailsService.loadUserByUsername("student")
  |               +-- PasswordEncoder matches password against hash
  |               +-- Authentication(student, ROLE_USER)
  |
  +-- Authorization checks /profile -> authenticated()
  |
  v
DemoController.profile(authentication)
  |
  v
HTTP 200, body: Hello, student!
~~~

The diagram focuses on the two beans in this lesson; it is **not** a complete list or strict ordering of all filters. Spring Security also includes filters/components for security context, exception handling, CSRF, headers, and others depending on configuration.

For student's GET /admin, authentication succeeds yet the **hasRole("ADMIN")** rule denies access. Controller.adminEndpoint() never runs. For a wrong password, authentication fails before the controller ever runs.

## 8. Important Points When Modifying Configuration Yourself

### URL Matching Scope and Rule Order

The rule:

~~~java
.requestMatchers(HttpMethod.GET, "/public").permitAll()
~~~

only matches **GET** /public; it does not mean POST /public is public. Both path and HTTP method can affect authorization decisions. When adding APIs, specify method, path, and required authorities explicitly.

Within one SecurityFilterChain, specific rules go before **anyRequest()**. In applications with multiple SecurityFilterChain beans, you also need to understand securityMatcher and chain ordering; this lesson creates only one chain to avoid initial complexity.

### Authentication Does Not Equal Resource Authorization

The clause **anyRequest().authenticated()** only checks that the user is authenticated. It does not check whether the user owns a specific document, invoice, or tenant record. If you add an endpoint like GET /orders/{id}, the service layer must verify ownership or record-level access rights to prevent cross-resource access vulnerabilities.

### Do Not Accidentally Disable CSRF While Learning Basic Configuration

The example never calls csrf().disable(). Spring Security enables CSRF protection by default for state-changing HTTP methods. If you add a POST/PUT/DELETE endpoint and call it with curl without sending a CSRF token, you may receive **403** even with a valid username/password.

Analyze how clients send credentials before deciding to change CSRF settings: browser apps using cookie sessions usually need CSRF protection; APIs strictly using bearer tokens sent explicitly via an Authorization header may have a different setup. Never disable CSRF just to “make the 403 error go away.”

### Why Not Use formLogin Alongside HTTP Basic in This Example?

The two mechanisms serve different interaction models. HTTP Basic is convenient for curl; formLogin is suited to form-based login flows and typically pairs with sessions. This lesson intentionally uses only Basic to keep SecurityFilterChain and UserDetailsService clear. When enabling formLogin, design the login page/form, session handling, redirects, and CSRF accordingly.

### Which Beans Are Created at Startup vs. What Happens Per Request?

- **The SecurityFilterChain bean** is created by Spring when building the ApplicationContext; this filter chain handles matching requests.
- **The InMemoryUserDetailsManager bean** is created at startup, holding the sample UserDetails.
- **The BCryptPasswordEncoder bean** is used to hash sample passwords when creating users and to verify passwords during authentication.
- Each HTTP Basic request passes through the security mechanism and is authenticated according to how that mechanism manages requests and context; the controller only handles permitted requests.

Do not describe @Bean methods as if Spring re-invokes the bean factory method for every request: by default, these beans are singletons.

## 9. Common Errors and Diagnosis

| Symptom | Common cause | What to check |
| --- | --- | --- |
| Every endpoint returns 401 | Missing permitAll for the right path/method; SecurityConfig was not picked up | Check package scanning, @Configuration, @Bean, and requestMatchers |
| Student can log in, but /admin returns 403 | **Intended behavior by design**: student has ROLE_USER | Use admin or change rules/roles when requirements clearly call for it |
| Correct username and password, yet still 401 | PasswordEncoder does not match hash; UserDetailsService returns wrong user; wrong credentials sent | Check the UserDetailsService bean, hash, and username; do not log plaintext passwords |
| GET returns 200, but POST returns 403 | Likely missing CSRF token on a state-changing method | Check CSRF policy and client type; do not disable globally by reflex |
| Startup fails due to multiple similar beans | Multiple user store/password encoder beans or ambiguous wiring | Check bean types and qualifiers/primary if multiple implementations are genuinely needed |
| Bean is not created | SecurityConfig is outside package scan or missing @Configuration/@Bean | Place under @SpringBootApplication base package or configure explicit scanning |
| hasRole("ADMIN") does not match authority | User data contains an authority string other than ROLE_ADMIN | Distinguish roles("ADMIN"), hasRole("ADMIN"), and hasAuthority(...) |
| New endpoint accidentally allows access | Rule is too broad, permitAll placed improperly, or fallback missing | Use narrower matchers, check rule ordering, and ensure a clear final catch-all rule |

When diagnosing, you can temporarily enable Spring Security logging at DEBUG level in development to see which filter chain and rule matched a request. Never print passwords, Authorization headers, or secret tokens. Avoid resolving 401/403 errors by deleting your security configuration.

## 10. Hands-On Exercises

### Exercise A — Endpoint Requiring Login

Add a GET /private controller returning the string “Private area”. Keep **anyRequest().authenticated()** as in the example. Predict and test the result before and after sending student's credentials. Explain why you do not need to declare a separate rule for /private.

**Suggested answer:** GET /private is not covered by the /public or /admin rules, so it matches anyRequest().authenticated(). Without credentials → 401; valid student → 200 if the controller exists.

### Exercise B — Adding the REVIEWER Role

Add user reviewer/reviewer123 with roles("REVIEWER") in InMemoryUserDetailsManager and a GET /review endpoint reserved for role REVIEWER. Add the requestMatchers GET /review rule **before** anyRequest().authenticated().

**Suggested answer:** hasRole("REVIEWER") checks for ROLE_REVIEWER. Reviewer can access /review; student/admin can only access it if explicitly granted ROLE_REVIEWER, not merely because they are logged in.

### Exercise C — Observing 401 and 403

Test /admin sequentially with no credentials, with student, and with admin. Record the HTTP status and identify whether the request was rejected at authentication or authorization.

**Answer:** Missing credentials → typically 401 with Basic; valid student → 403 due to missing role; valid admin → 200.

### Exercise D — Adding a State-Changing API

If you add POST /profile requiring login, predict the result of a POST using HTTP Basic without a CSRF token, then investigate how to configure and test CSRF protection appropriately for a real client. Do not disable CSRF globally just to get status 200.

**Goal:** distinguish user authentication, endpoint authorization, and anti-forgery protection; understand why 403 can originate from a mechanism other than roles.

## 11. Checklist Before Expanding the Project

1. SecurityConfig is scanned by Spring and produces the expected **SecurityFilterChain bean**.
2. Public rules are declared specifically; login/role rules are explicit; a fallback rule covers remaining requests.
3. UserDetailsService returns username, password hash, and authorities as intended.
4. PasswordEncoder is configured compatibly with how passwords are stored.
5. Real tests cover at least 200/401/403 and verify bodies/side effects.
6. HTTP Basic is used only over HTTPS in real environments.
7. No hardcoded accounts/passwords or in-memory user stores are used as a production mechanism.
8. When adding a database, JWT, OAuth2, method security, or object-level authorization, define responsibility boundaries for each component and add tests.
9. When adding state-changing methods, verify CSRF, input validation, object-level authorization, and safe logging.

## 12. Self-Check Knowledge Questions

**Q:** Does SecurityFilterChain store the user list?  
**A:** No. It describes the filter chain and security policy for requests; the user store is the responsibility of UserDetailsService or the corresponding authentication component.

**Q:** Does UserDetailsService decide that /admin requires ROLE_ADMIN?  
**A:** No. URL rules live in SecurityFilterChain; UserDetailsService only supplies user information, including authorities.

**Q:** Why is PasswordEncoder needed when using InMemoryUserDetailsManager?  
**A:** Because password authentication must compare against the hash stored in UserDetails. In-memory does not mean storing plaintext.

**Q:** When student accesses /admin, does a 403 error mean the password was wrong?  
**A:** No. With the right password, student authenticated successfully but lacks ROLE_ADMIN. A wrong password typically leads to 401.

**Q:** Is an application completely secure with just these two beans?  
**A:** Not yet. This is an initial foundation; production still requires a durable user store, credential management, HTTPS, input/resource validation, client-appropriate CSRF, security headers, and proper testing.

**Takeaway:** Start with a SecurityFilterChain describing *which requests are allowed*, a UserDetailsService supplying *who the user is and what authorities they hold*, and a PasswordEncoder to *verify passwords safely*. Verify both beans with real HTTP requests before adding more complex mechanisms.

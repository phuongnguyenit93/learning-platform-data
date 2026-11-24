# javax.servlet and jakarta.servlet During Platform Upgrades

## 1. Problem and Objective

When upgrading an application from **Spring Boot 2.x / Spring Framework 5.x / Spring Security 5.x** to **Spring Boot 3.x / Spring Framework 6.x / Spring Security 6.x**, HTTP Servlet handling code typically must migrate from **javax.servlet** to **jakarta.servlet**.

~~~java
// Before upgrade (Java EE / Spring Boot 2.x):
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

// After upgrade (Jakarta EE / Spring Boot 3.x):
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
~~~

This is **not just renaming imports**. The JVM treats **javax.servlet.Filter** and **jakarta.servlet.Filter** as two independent types. A class compiled against the old interface is not automatically compatible with the new interface. If the project or a dependency still relies on the old Servlet API, you may encounter:

- Compile errors such as **package javax.servlet does not exist**, **method does not override or implement a method from a supertype**, or missing ServletException.
- Runtime errors such as **NoClassDefFoundError: javax/servlet/Filter**, **ClassNotFoundException**, **LinkageError**, **ClassCastException**, or **NoSuchMethodError** due to binary mismatch.
- Custom **Filter/Servlet/Listener** not being registered, invoked at the wrong stage, or missing Authentication on the request.
- A WAR running on an older Tomcat failing to start on a newer container, or vice versa.
- HTTP test **401/403/302** responses changing after upgrade due to **Spring Security 6 configuration** rather than directly from javax/jakarta.

This lesson helps you understand the nature of the namespace migration, choose the right Servlet container and dependencies, migrate custom Security filters, write a buildable and testable Java 17 example, diagnose errors, and preserve security controls during the upgrade.

**Scope:** Spring Security **Servlet stack**, not WebFlux. Examples use **Java 17+, Spring Boot 3.x, Spring Security 6.x**. Exact versions in a real project must be mutually compatible.

## 2. Why do javax.servlet and jakarta.servlet both exist?

### 2.1. From Java EE to Jakarta EE

Earlier enterprise Java specifications used the **javax.servlet** namespace. After the Java EE ecosystem transitioned to Jakarta EE, many enterprise APIs moved their packages to **jakarta.***. The Servlet API is one of the components that must be converted when using Spring Framework 6.

| Illustrative stack | Servlet API/namespace | Typical container |
| --- | --- | --- |
| Spring Boot 2.x, Framework 5.x, Security 5.x | **javax.servlet**, Servlet 4.0 | **Tomcat 9** |
| Jakarta EE 9, Servlet 5.0 | **jakarta.servlet** | **Tomcat 10.0** |
| Spring Boot 3.x, Framework 6.x, Security 6.x | **jakarta.servlet**, Servlet 6.0 | **Tomcat 10.1** |

This table shows **common platform combinations**, not a claim that every Java application uses a single specific container. Spring Boot 3 requires **Java 17+** and a matching Jakarta platform; migrating source code to Jakarta while keeping a Java 11 runtime or an external Tomcat 9 does not produce a compatible system.

### 2.2. Two Java types that are not interchangeable

~~~text
javax.servlet.Filter         != jakarta.servlet.Filter
javax.servlet.Servlet        != jakarta.servlet.Servlet
javax.servlet.FilterChain    != jakarta.servlet.FilterChain
javax.servlet.ServletRequest != jakarta.servlet.ServletRequest

LegacyFilter implements javax.servlet.Filter
→ NOT an implementation of jakarta.servlet.Filter
~~~

The package name is part of the **binary class name** stored in bytecode. A third-party JAR that still references **javax/servlet/Filter** remains tied to the old API even after your main project changes every import to jakarta.servlet.

Therefore, **every library running inside the same web application classloader** must be upgraded to a Jakarta-compatible version—especially libraries creating Filters, ServletContextListeners, servlet initializers, JSP/JSTL, SSO adapters, and test support.

### 2.3. Do not blindly replace every javax.* package

| Previous type | What to do during migration |
| --- | --- |
| javax.servlet.Filter | **jakarta.servlet.Filter** |
| javax.servlet.FilterChain | **jakarta.servlet.FilterChain** |
| javax.servlet.ServletException | **jakarta.servlet.ServletException** |
| javax.servlet.http.HttpServletRequest / Response | **jakarta.servlet.http.HttpServletRequest / Response** |
| javax.servlet.annotation.WebFilter | **jakarta.servlet.annotation.WebFilter** |
| javax.servlet.jsp.* | **jakarta.servlet.jsp.*** if the project uses JSP |
| javax.validation.Valid | **jakarta.validation.Valid** |
| javax.persistence.Entity | **jakarta.persistence.Entity** |
| javax.annotation.PostConstruct | **jakarta.annotation.PostConstruct** when using Jakarta annotations |
| javax.ws.rs.* | Matching Jakarta REST API if the project uses JAX-RS |
| javax.net.ssl.* | **Keep unchanged**, Java SE TLS |
| javax.crypto.* | **Keep unchanged**, Java SE cryptography |
| javax.sql.* | **Keep unchanged**, Java SE SQL |
| javax.xml.parsers.* | **Keep unchanged**, Java SE XML |

Do not run a global find-and-replace for **javax. → jakarta.**. Several Java SE APIs still start with `javax` and are completely valid on Java 17. Migrate each API family alongside its dependencies and versions.

## 3. Spring Security Servlet touchpoints to inspect

An application might have zero `javax.servlet` imports in its controllers and still require migration because Spring Security Servlet is built on the **Servlet Filter API**.

Key components include:

- **FilterChainProxy** dispatches across **SecurityFilterChain** instances.
- **DelegatingFilterProxy** bridges the servlet container's filter registration to a Spring-managed filter bean.
- **OncePerRequestFilter** is the common base class for custom authentication, audit, and request-wrapper filters.
- **AuthenticationEntryPoint / AccessDeniedHandler** accept Servlet request/response parameters to send 401/403 responses or redirects.
- **RequestCache, SecurityContextRepository, LogoutHandler, SessionAuthenticationStrategy, HttpSession** operate on the Servlet request or session.
- **HttpFirewall / StrictHttpFirewall** inspects the servlet request and rejects non-standard paths.
- **FilterRegistrationBean, ServletContextInitializer, @WebFilter, @WebListener**, and **web.xml** interface directly with the servlet container.
- Custom **CsrfTokenRepository**, custom authentication filters, and SSO/OIDC adapters may expose Servlet API types in public method signatures.

In a large project, also audit modules containing test fixtures, filter frameworks, internal authentication SDKs, tracing libraries, servlet initializers, and third-party integrations.

### 3.1. How does the OncePerRequestFilter signature change?

A Boot 2 / Spring 5 snippet (illustrative only; do not use with Boot 3):

~~~java
// Inside a legacy OncePerRequestFilter subclass:
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain)
        throws ServletException, IOException {
    chain.doFilter(request, response);
}
~~~

On Boot 3 / Spring 6:

~~~java
// Inside a new OncePerRequestFilter subclass:
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain)
        throws ServletException, IOException {
    chain.doFilter(request, response);
}
~~~

Both blocks above are **snippets** inside a class that imports **java.io.IOException**, not standalone source files. If the superclass expects `jakarta.servlet.FilterChain` while the subclass declares `javax.servlet.FilterChain`, the signatures no longer match and **@Override** fails to compile. **Never** work around this by deleting `@Override`; fix the imports and verify the framework actually invokes the method.

### 3.2. Adding javax.servlet-api is not a migration fix

Seeing a compile error and adding:

~~~groovy
// Incorrect approach in a Boot 3 Jakarta application:
implementation 'javax.servlet:javax.servlet-api:4.0.1'
~~~

may let old source compile in a few places, yet it **does not** turn `javax.servlet.Filter` into `jakarta.servlet.Filter`. The runtime may end up carrying both type hierarchies, causing conflicts.

The proper solution is to **upgrade or recompile libraries** against the Jakarta API and let Spring Boot dependency management keep the stack aligned. In standard Boot web apps, `starter-web`/embedded container already provides the required Servlet APIs; do not add extra `servlet-api` JARs arbitrarily.

## 4. Multi-layer upgrade plan

### 4.1. Establish a baseline

Before changing code, record:

1. JDK on **developer machines, CI, Docker images, and production runtime**; Spring Boot 3 requires Java 17+.
2. Actual resolved **Spring Boot, Spring Framework, Spring Security** versions, not just desired versions in build files.
3. Packaging model: **executable JAR/embedded Tomcat** vs **WAR/external servlet container**.
4. Every custom **Filter, listener, servlet, authentication entry point, and request wrapper**.
5. Related libraries: **JSP/JSTL, OAuth2/OIDC adapters, OpenAPI, tracing/observability, Spring Session, internal SDKs**.
6. Key Spring Security rules: public/private routes, 401/403/302, CSRF, CORS, session fixation, remember-me, request matchers.
7. Integration tests and how to roll back both artifact and container.

Without a baseline, it is easy to mistake a **403 from CSRF or a matcher** for a Jakarta error, or a **NoClassDefFoundError** for a filter logic bug.

### 4.2. Sample roadmap

~~~text
Boot 2.x / Security 5.x / javax.servlet
     │
     ├─ Freeze baseline and regression tests
     │
     ├─ Optionally prepare API migration on Boot 2.7/Security 5.8
     │  (if dependency compatibility allows)
     │
     ├─ Upgrade JDK, Gradle/Maven, and CI to Java 17+
     │
     ├─ Select libraries with Jakarta-compatible versions
     │
     ├─ Upgrade to Boot 3 / Framework 6 / Security 6
     │
     ├─ Update the appropriate enterprise API namespaces
     │
     ├─ Migrate SecurityFilterChain and security matchers
     │
     ├─ Test Servlet filters and authentication/authorization
     │
     ├─ Test embedded/external container and real proxy
     │
     └─ Release with monitoring, fallback, and synchronized rollback
~~~

This is a **suggested roadmap**, not a requirement to step through every intermediate version. For unmaintained libraries still tied to `javax.servlet`, prefer replacing or upgrading them rather than hiding risk by mixing both namespaces.

## 5. Complete Spring Boot 3.x / Security 6.x / Java 17+ example

This example shows a custom **OncePerRequestFilter** using the Jakarta Servlet API inside a real **SecurityFilterChain**, plus two HTTP endpoints and four tests.

Files:

~~~text
jakarta-migration-demo/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat (Project's Gradle wrapper)
└── src/
    ├── main/java/com/example/migration/MigrationApplication.java
    └── test/java/com/example/migration/MigrationApplicationTest.java
~~~

### 5.1. Build files

**settings.gradle**:

~~~groovy
rootProject.name = 'jakarta-migration-demo'
~~~

**build.gradle** (versions pinned for a reproducible example; in real deployments choose supported patch releases suitable for your system):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Boot and dependency-management plugin versions in this example are an **illustrative set**, not a requirement to use these exact versions in production. You can use newer patch releases on a supported branch after verifying compatibility. Do not add `javax.servlet-api`.

### 5.2. Application, SecurityFilterChain, filter, and controller

File **src/main/java/com/example/migration/MigrationApplication.java**:

~~~java
package com.example.migration;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class MigrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MigrationApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET,
                                "/private/whoami").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                // Filter placed in the Spring Security chain.
                // Do not also register it as a Servlet bean.
                .addFilterBefore(
                        new RequestMarkerFilter(),
                        BasicAuthenticationFilter.class)
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        // Local demo account; do not ship to production.
        return new InMemoryUserDetailsManager(
                User.withUsername("demo")
                        .password(encoder.encode("test-password"))
                        .roles("USER")
                        .build());
    }
}

final class RequestMarkerFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        response.setHeader("X-Servlet-API", "jakarta.servlet");
        chain.doFilter(request, response);
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/private/whoami")
    public String whoAmI(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

**Why does the example use `new RequestMarkerFilter()`?** This is a simple filter **not declared as `@Bean`/`@Component`**. It is registered only inside the **Spring Security filter chain**. If a Filter is both a Spring bean and added to `SecurityFilterChain`, Boot may automatically register it at the servlet container level as well, causing double invocation or unexpected ordering.

**Do not use this code as an authorization policy for a real project:** the rules here only demonstrate HTTP Basic. For Bearer/OIDC APIs and POST/PUT/DELETE operations, design object-level authorization, CSRF/CORS, and session/token protection separately.

### 5.3. Running from the terminal

The project requires the Gradle wrapper. Run:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Test the public endpoint:

~~~bash
curl -i 'http://localhost:8080/public/ping'
~~~

**Expected:** HTTP 200, body **pong**, and header:

~~~http
X-Servlet-API: jakarta.servlet
~~~

Test the private endpoint without credentials:

~~~bash
curl -i 'http://localhost:8080/private/whoami'
~~~

**Expected:** HTTP 401 (HTTP Basic entry point). Next, test with the demo user:

~~~bash
curl -i -u demo:test-password \
  'http://localhost:8080/private/whoami'
~~~

**Expected:** HTTP 200 and body:

~~~text
demo
~~~

This is expected output from the illustrative configuration, not stdout captured from a live execution environment. Do not expose demo credentials on public services; when testing real endpoints, always use TLS.

## 6. Four MockMvc tests for Jakarta migration

File **src/test/java/com/example/migration/MigrationApplicationTest.java**:

~~~java
package com.example.migration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MigrationApplicationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void customFilterImplementsJakartaServletApi() {
        assertThat(jakarta.servlet.Filter.class
                .isAssignableFrom(RequestMarkerFilter.class))
                .isTrue();
    }

    @Test
    void publicRequestPassesThroughJakartaFilter()
            throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"))
                .andExpect(header().string(
                        "X-Servlet-API", "jakarta.servlet"));
    }

    @Test
    void privateRequestWithoutAuthIs401()
            throws Exception {
        mvc.perform(get("/private/whoami"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void basicAuthWorksAfterMigration()
            throws Exception {
        mvc.perform(get("/private/whoami")
                        .with(httpBasic("demo", "test-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("demo"))
                .andExpect(header().string(
                        "X-Servlet-API", "jakarta.servlet"));
    }
}
~~~

Run:

~~~bash
./gradlew clean test --tests com.example.migration.MigrationApplicationTest
~~~

Windows:

~~~powershell
.\gradlew.bat clean test --tests com.example.migration.MigrationApplicationTest
~~~

**Expected:** 4 passing tests in a valid Spring Boot 3.x project. The tests verify that the Filter implements **jakarta.servlet.Filter**, returns 200 for public, 401 when authentication is missing, and 200 with valid Basic credentials. This is an **expected static check**, not a verified execution log.

### Limitations of MockMvc

MockMvc tests requests through the Spring Test context and `SecurityFilterChain` when filters are registered properly, but **does not fully replicate** external Tomcat WAR classloading, JSP compilation, third-party `ServletContainerInitializer` classes, WAF/proxy rewrites, or TLS termination. After running tests, run the actual application in an HTTP container, and if shipping a WAR, test on the exact external servlet container.

## 7. Dependency analysis: finding JARs that still reference javax.servlet

Do not search only imports under `src/main`; old libraries can carry bytecode referencing `javax` packages and load only when a request hits a specific code path.

### 7.1. Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath \
  --dependency javax.servlet-api
./gradlew dependencyInsight --configuration testRuntimeClasspath \
  --dependency javax.servlet-api
~~~

On PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency javax.servlet-api
.\gradlew.bat dependencyInsight --configuration testRuntimeClasspath --dependency javax.servlet-api
~~~

**Note:** finding no `javax.servlet-api` artifact only proves the dependency graph does not declare an artifact matching that query name. It **does not prove every other JAR was compiled against `jakarta.servlet`**. Audit internal libraries, SSO adapters, tracing agents, servlet filters, JSP/JSTL, and custom test fixtures too.

### 7.2. Maven

If using the Maven wrapper:

~~~bash
./mvnw dependency:tree -Dincludes=javax.servlet:javax.servlet-api
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

In PowerShell:

~~~powershell
.\mvnw.cmd dependency:tree -Dincludes=javax.servlet:javax.servlet-api
.\mvnw.cmd dependency:tree -Dincludes=org.springframework.security
~~~

Pick the build tool your project uses; you do not need both Gradle and Maven.

### 7.3. Searching source, class signatures, and bytecode

Strings to search for in Java source, tests, XML, and config:

~~~text
import javax.servlet.
javax.servlet.Filter
javax.servlet.http.
javax.servlet.annotation.
javax.servlet.jsp.
~~~

If source code is clean yet runtime still throws **NoClassDefFoundError: javax/servlet/Filter**, inspect the JARs:

- **jdeps** to inspect class dependencies of JARs on an appropriate classpath. It does not always detect reflection or string-based class loading.
- **jar tf** to inspect JAR contents.
- **javap -verbose** to locate class names in binary signatures and the constant pool.
- SBOM/dependency reports to identify versions and transitive dependencies.
- Rebuild **internal SDK/filter JARs** against Jakarta dependencies, update test fixtures, and publish compatible versions.

Do not arbitrarily inject `javax.servlet` classes into a Boot 3 runtime “because an old JAR might need them”; that only obscures the problem without guaranteeing compatibility.

## 8. Embedded container vs external WAR

### 8.1. Executable JAR

When Spring Boot 3 uses **spring-boot-starter-web** with the default embedded Tomcat, dependency management selects Jakarta-compatible artifacts. If the project independently overrides Spring/Tomcat/Jakarta API versions, inspect the actual classpath—especially after upgrading Gradle or updating the platform BOM.

**Do not** bring Tomcat 9 back into a Boot 3 Servlet project to keep old binaries working: Tomcat 9 uses `javax.servlet` and does not satisfy the Servlet 6.0/Jakarta API baseline of Boot 3.

### 8.2. WAR on an external container

If deploying a WAR onto **Tomcat 9**, container Servlet classes live in the **javax.servlet** namespace. A Boot 3/Security 6 app using **jakarta.servlet** cannot run as-is simply by changing a few imports. Use a Jakarta-compatible container such as **Tomcat 10.1 (Servlet 6.0)** and verify full-application compatibility.

For a Spring Boot WAR, you typically need:

- Gradle **war plugin** or appropriate Maven WAR packaging.
- Container dependencies marked **providedRuntime/provided** when supplied by the external container.
- **SpringBootServletInitializer** configured to bootstrap the web application per the Boot model.
- A review of **@WebFilter**, **@WebListener**, **ServletContextInitializer**, **web.xml**, session persistence, and JSP/JSTL.
- Smoke tests executed inside the **target container**, not just unit tests.

Not every Boot **executable JAR** app needs `web.xml` or a Servlet initializer. Those belong to WAR/traditional deployments.

### 8.3. Descriptor web.xml

Traditional servlet applications using **WEB-INF/web.xml** should update their namespace/schema when deploying to Servlet 6.0. Example skeleton:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
    <display-name>Jakarta Migration Demo</display-name>
</web-app>
~~~

This snippet only illustrates the **web.xml skeleton** and registers no servlets or filters. An embedded Boot web app like Section 5 needs no `web.xml`.

### 8.4. JSP/JSTL and non-Java resources

A JSP/JSTL project can compile its controllers yet fail while rendering views because of outdated taglibs or JSP engines. You need Jakarta-compatible JSP/Tags API versions, a supporting container, matching taglib URIs, and proper packaging. Pay close attention to login pages, error pages, CSRF forms, and output encoding.

Bytecode/class-name transformation tools can help under a proper verification process, yet they **do not guarantee** full handling of reflection, descriptors, XML, annotations, taglibs, or non-namespace API changes. Prefer JARs with Jakarta support from their maintainers or rebuild from source.

## 9. Spring Security 5 → 6 has changes independent of Jakarta

### 9.1. Replacing WebSecurityConfigurerAdapter and antMatchers

An older Security 5 configuration might read:

~~~java
// Legacy API pattern; does NOT compile directly with Security 6.
class LegacySecurity extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .anyRequest().authenticated();
    }
}
~~~

**WebSecurityConfigurerAdapter** was removed from Spring Security 6 configuration. Use a **SecurityFilterChain** bean and the modern DSL instead:

~~~java
// Snippet inside a @Configuration class; add the corresponding imports.
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public/**").permitAll()
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Do not work around this by forcing an older Spring Security 5.x library into Boot 3. Migrate to Security 6 APIs and verify actual permissions.

### 9.2. securityMatcher vs requestMatchers

- **securityMatcher(...)**: determines which requests belong to a **SecurityFilterChain**.
- **requestMatchers(...)** inside **authorizeHttpRequests(...)**: sets authorization policy for requests that have already entered that chain.

With multiple chains (for instance, Bearer API and web form login), test **@Order precedence**, fallback chains, request/context paths, and `AuthenticationEntryPoint`. Getting 302 instead of 401 can stem from selecting the wrong chain, **not necessarily from Jakarta Servlet**.

### 9.3. @PreAuthorize, sessions, CSRF, CORS, and filter registration

If using method security, inspect **@EnableMethodSecurity**, AOP proxies, and self-invocation; that is a separate layer from the Servlet namespace.

When moving a custom filter from Boot 2 to 3, do not both mark it **@Component/@Bean** (letting the container auto-register it) and also call **http.addFilterBefore(...)** on the same filter. A servlet `Filter` outside the security chain and a filter inside `FilterChainProxy` have different lifecycles, dispatcher mappings, and ordering. Verify session cookies, CSRF, CORS preflight, and HTTP 401/403 after upgrading rather than disabling security to make tests pass.

## 10. Common troubleshooting table

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| **package javax.servlet does not exist** | Old source on a Jakarta build | Update imports and method signatures |
| **method does not override...** | Method still takes `javax` types instead of `jakarta` types | Compare against the actual superclass/interface |
| **NoClassDefFoundError: javax/servlet/Filter** | An old JAR still depends on `javax` | Inspect dependency tree and bytecode, upgrade the JAR |
| **ClassCastException: javax.servlet.Filter / jakarta.servlet.Filter** | Mixed Filter types in the classloader | Standardize on one Jakarta generation |
| **NoSuchMethodError** in Web/Security | Version graph or binary API mismatch | Remove incompatible overrides and rebuild |
| Custom filter does not run | Wrong filter registration/annotation/chain matcher | Check filter chain logs, Spring beans, container mapping |
| Custom filter runs twice | Both auto-registered as servlet filter and added to `SecurityFilterChain` | Pick one proper registration mechanism |
| **HTTP 401/403 differs from before** | Security 6 matcher/entry point/session/CSRF changes | Review policy and test denied requests |
| **WAR fails to start on Tomcat 9** | `javax` container, Jakarta app | Upgrade to a compatible external container |
| JSP error after login | Outdated JSP/JSTL | Upgrade engine/taglib and test real rendering |
| Unit tests pass, production fails | MockMvc does not run external container/JSP/proxy | Add E2E integration tests matching deployment stack |
| Built on JDK 17, runtime JDK 11 | Runtime JVM is too old | Align Java runtime/toolchain/image |
| **404** after proxy path rewrite | Inconsistent path matching/routing | Check proxy, context path, and `securityMatcher` |

Do not treat **adding `javax.servlet-api`**, disabling CSRF, opening `permitAll` on all routes, or downgrading the servlet container as valid fixes. Those shortcuts mask migration errors and leave the application without proper security controls.

## 11. Testing and handoff checklist

**Build and dependencies**

- Use Java 17+ for both build and runtime; verify Gradle/Maven and managed versions.
- No legacy Servlet API sources remain in modules deployed to Boot 3.
- Internal/third-party JARs use Jakarta; no runtime dependency or binary requires `javax.servlet` in the same web app classloader.
- Do not mix Spring Boot 3 with unsupported Spring Security 5 or Jakarta API versions.

**Servlet and SecurityFilterChain**

- Custom filters implement **jakarta.servlet.Filter/FilterChain/ServletException** properly without double registration.
- `SecurityFilterChain` matches the right HTTP routes; public/private cases preserve policy.
- `AuthenticationEntryPoint`, `AccessDeniedHandler`, CSRF, CORS, and method security are verified independently.
- With multiple `SecurityFilterChain` beans, test both the fallback chain and URLs outside matchers.

**Runtime and deployment**

- Spring Boot executable JAR runs on the appropriate embedded container.
- WAR (if used) runs on a Jakarta-compatible external container, not Tomcat 9.
- `web.xml`, JSP/JSTL, listeners, and `ServletContainerInitializer` are compatible if used by the project.
- Behind proxies/gateways, path prefixes, HTTPS/HSTS, session cookies, and request rejections remain accurate.

**Regression tests**

- MockMvc: public 200, missing-auth 401, valid credentials 200, denied scope/role 403 where enforced.
- Test filter/lifecycle, duplicate registration, request dispatches, and behavior after error/async dispatches.
- Run raw HTTP tests through the container and edge proxy in real deployments, not only unit tests.
- Use dedicated test users and secrets; never log production credentials or tokens to console/logs.
- Maintain a rollback plan for **both the application artifact and container/runtime**, not just swapping one JAR.

**Conclusion:** **javax.servlet** and **jakarta.servlet** are two Servlet API generations with different namespaces and binary-incompatible names. Upgrading to **Spring Boot 3 / Spring Security 6** requires aligning **Java 17+, Jakarta-compatible dependencies, custom filters, the Servlet container, Security configuration, and HTTP testing**. Updating imports is a necessary step, while proof of success is that the entire application compiles, starts, and enforces the intended security policy in the target deployment environment.

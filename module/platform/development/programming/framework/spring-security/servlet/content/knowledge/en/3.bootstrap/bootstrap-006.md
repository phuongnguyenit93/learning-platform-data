# Registering Security Filters in a Servlet Application Without Spring Boot

> **Scope:** Traditional Java Servlet applications running on a Servlet container (such as Tomcat) and initializing Spring Framework/Spring Security manually, **without Spring Boot and without Spring Boot auto-configuration**. Content uses the Jakarta Servlet API, Spring Framework 6, and Spring Security 6, requiring Java 17+. The focus is on how to register security filters in the Servlet container, where to create required beans, how to set ordering, and how to verify request routing.

## 1. Why Must Filters Be Registered Manually Without Spring Boot?

In a Servlet application, the **Servlet container** receives HTTP requests, selects servlets, and invokes any `Filter`s with matching mappings. Spring Security provides a filter chain to perform tasks such as loading security context, authentication, exception handling, and authorization before a request reaches a servlet/controller.

When using Spring Boot Web, Boot's integration mechanism typically registers Spring Security's filter with the Servlet container automatically. In an application **without Spring Boot**, you must ensure the link **Servlet container → filter proxy → Spring Security** is declared explicitly via one of three approaches: Servlet 3+ initializer code (Java configuration), `AbstractSecurityWebApplicationInitializer`, or `web.xml`.

Three commonly confused layers:

| Component | Managed by whom? | Responsibility |
| --- | --- | --- |
| `DelegatingFilterProxy` | Registered as a Servlet `Filter` in the container; its delegate lives in the Spring context | Bridge between the container's filter chain and a filter bean in Spring |
| Bean `springSecurityFilterChain` (usually `FilterChainProxy`) | Spring `ApplicationContext` | Selects the `SecurityFilterChain` matching the request and executes the inner security filters |
| Bean `SecurityFilterChain` | Spring `ApplicationContext`, declared with `@Bean` | Describes the group of filters and HTTP protection rules built from `HttpSecurity` |

**The name `springSecurityFilterChain` is critical**: by default `DelegatingFilterProxy` looks up a Spring bean with that exact name. `@EnableWebSecurity` together with Spring Security configuration builds infrastructure that includes a `FilterChainProxy` bearing this name. The `SecurityFilterChain` bean you declare is one component inside that infrastructure; the method name `securityFilterChain` is not the proxy target name to look up.

```text
HTTP request
    |
    v
Servlet container (filter mapping on /*)
    |
    v
DelegatingFilterProxy [Servlet Filter]
    | looks up bean "springSecurityFilterChain" in Spring WebApplicationContext
    v
FilterChainProxy [Spring bean]
    | selects the SecurityFilterChain matching the request
    v
Security filters: SecurityContext -> Authentication -> Authorization -> ...
    |
    v
Servlet / Spring MVC DispatcherServlet
    |
    v
HTTP response (or 401/403 if a security filter denies it)
```

If you only create `@Bean SecurityFilterChain` **without registering the entry point in the Servlet container**, application requests are not protected as expected. Conversely, if you register `DelegatingFilterProxy` without properly initializing the Spring context/`springSecurityFilterChain` bean, the application may fail when the container initializes filters or handles requests.

## 2. Choosing One of Three Registration Paths

| Approach | Registered where? | Suitable when |
| --- | --- | --- |
| **A. Manually register `DelegatingFilterProxy` via `WebApplicationInitializer`** | `ServletContext#addFilter` | You want full visibility into the process and direct control over mapping/dispatchers |
| **B. Extend `AbstractSecurityWebApplicationInitializer`** | Spring Security registers the proxy automatically via a Servlet initializer | The project uses Spring Security Java config and wants minimal bootstrap code |
| **C. Declare `DelegatingFilterProxy` in `web.xml`** | File `WEB-INF/web.xml` | Traditional WAR application already using XML configuration |

**Do not enable A, B, and C at the same time for the same filter.** Each approach above is an alternative way to wire a proxy to the container, not three consecutive steps. All of them require a Spring `WebApplicationContext` containing a bean named `springSecurityFilterChain`.

The next section implements **A** as a runnable example; afterwards, it shows how to switch to **B** or **C** without creating duplicate filters.

## 3. Complete Example: Plain Servlet WAR + Spring Security, Without Boot

The example creates two endpoints, `GET /hello` and `GET /admin`:

- `/hello` requires a validly logged-in user.
- `/admin` allows only users with role `ADMIN`.
- Two test accounts: `alice` with role `USER`, `admin` with role `ADMIN`.

Sample environment: **JDK 17+**, **Maven 3.9+**, **Tomcat 10.1.x** (Jakarta Servlet 6), illustrative versions of **Spring Framework 6.1.x** and **Spring Security 6.3.x**. This is a released illustrative version pair, not a claim of the latest release. You can use centrally managed versions in a real project provided Servlet/JDK compatibility holds.

Project structure:

```text
plain-servlet-security/
├── pom.xml
└── src/main/java/example/security/
    ├── AppInitializer.java
    ├── SecurityConfig.java
    └── GreetingServlet.java
```

### 3.1. `pom.xml`: Packaging a WAR and Using the Right Jakarta Servlet API

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>plain-servlet-security</artifactId>
    <version>1.0</version>
    <packaging>war</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.1.14</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
            <dependency>
                <groupId>org.springframework.security</groupId>
                <artifactId>spring-security-bom</artifactId>
                <version>6.3.4</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-config</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-web</artifactId>
        </dependency>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
            <version>6.0.0</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <finalName>secure-demo</finalName>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-war-plugin</artifactId>
                <version>3.4.0</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-web` provides `WebApplicationInitializer`, `ContextLoaderListener`, and `DelegatingFilterProxy`; `spring-security-config` provides HTTP configuration; `spring-security-web` contains the security filters. The Servlet API has `scope=provided` because **Tomcat supplies the Servlet API at runtime**. Spring Framework 6 uses the `jakarta.servlet.*` namespace, not the `javax.servlet.*` of earlier generations.

By using the Spring Framework BOM and Spring Security BOM, Spring versions across dependencies are managed synchronously; avoid randomly mixing major versions like Spring 5 / Security 6 or Tomcat 9 / Jakarta Servlet 6.

### 3.2. `SecurityConfig.java`: Creating the Security Chain and Illustrative Accounts

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/hello").authenticated()
                .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("demo123"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
```

Explanation:

- `@EnableWebSecurity` activates web security configuration and Spring Security infrastructure beans; as part of this, the framework creates a filter bean named **`springSecurityFilterChain`**.
- `@Bean SecurityFilterChain` supplies the HTTP rules used inside that bean. The method name `securityFilterChain` does not substitute for the `springSecurityFilterChain` name used by `DelegatingFilterProxy`.
- `hasRole("ADMIN")` checks for authority `ROLE_ADMIN` by default; the builder `.roles("ADMIN")` grants that matching authority.
- `httpBasic()` enables verifying credentials sent via `Authorization: Basic ...`. Only use it with HTTPS in environments with real data.
- `anyRequest().denyAll()` blocks undeclared URLs so the example has clear authorization boundaries.
- `BCryptPasswordEncoder` stores passwords in memory as hashes; the `demo123` password and two test accounts are strictly for this hands-on exercise.

The example only performs GET requests; CSRF remains enabled by Spring Security's default configuration. When adding POST/PUT/DELETE, you must handle CSRF tokens and appropriate session/API policies rather than disabling CSRF arbitrarily just to test a demo.

### 3.3. `GreetingServlet.java`: Business Servlet Without Spring MVC

```java
package example.security;

import java.io.IOException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public class GreetingServlet extends HttpServlet {
    @Override
    protected void doGet(HttpServletRequest request,
                         HttpServletResponse response) throws IOException {
        String user = request.getUserPrincipal().getName();
        boolean adminEndpoint = "/admin".equals(request.getServletPath());

        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().write((adminEndpoint ? "admin:" : "hello:") + user);
    }
}
```

The servlet retrieves `getUserPrincipal()` from a request that has already passed through the Spring Security filter chain. On both protected URLs, requests only reach the servlet after satisfying `authenticated()` or the matching role, so the example has a valid principal. For public endpoints, handle the `getUserPrincipal() == null` case; do not reuse this method verbatim for anonymous endpoints without checking.

### 3.4. `AppInitializer.java`: Registering the Context, Proxy Filter, and Servlet

```java
package example.security;

import java.util.EnumSet;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterRegistration;
import jakarta.servlet.ServletContext;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRegistration;
import org.springframework.web.WebApplicationInitializer;
import org.springframework.web.context.ContextLoaderListener;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.filter.DelegatingFilterProxy;

public class AppInitializer implements WebApplicationInitializer {
    @Override
    public void onStartup(ServletContext servletContext) throws ServletException {
        // 1. Create the Spring root WebApplicationContext.
        AnnotationConfigWebApplicationContext root =
                new AnnotationConfigWebApplicationContext();
        root.register(SecurityConfig.class);
        servletContext.addListener(new ContextLoaderListener(root));

        // 2. Attach the proxy filter to the Servlet container.
        FilterRegistration.Dynamic security = servletContext.addFilter(
                "springSecurityFilterChain",
                new DelegatingFilterProxy("springSecurityFilterChain")
        );
        if (security == null) {
            throw new ServletException(
                    "Filter springSecurityFilterChain already registered");
        }
        security.addMappingForUrlPatterns(
                EnumSet.of(DispatcherType.REQUEST),
                false,
                "/*"
        );

        // 3. Register the business servlet and its URLs.
        ServletRegistration.Dynamic greeting = servletContext.addServlet(
                "greetingServlet", new GreetingServlet()
        );
        if (greeting == null) {
            throw new ServletException("Servlet greetingServlet already registered");
        }
        greeting.addMapping("/hello", "/admin");
    }
}
```

This is the core mechanism of the lesson:

1. `AnnotationConfigWebApplicationContext` is the **Spring root context** containing `SecurityConfig` and the Spring Security beans.
2. `ContextLoaderListener` binds the root context's lifecycle to the web application lifecycle; the container initializes the listener before serving requests.
3. `servletContext.addFilter(...)` registers a `DelegatingFilterProxy` **with the Servlet container**. The proxy looks up the Spring bean `springSecurityFilterChain` to delegate at runtime.
4. `addMappingForUrlPatterns(..., "/*")` ensures incoming HTTP requests pass through the proxy; mapping `/hello` or `/admin` individually would easily miss new URLs.
5. `EnumSet.of(DispatcherType.REQUEST)` is a minimal choice sufficient for this example's synchronous HTTP requests. In applications with async/error dispatches, proactively configure the needed dispatcher types and handle security context propagation properly.
6. The `false` argument to `addMappingForUrlPatterns` is `isMatchAfter`: using `false` inserts the mapping ahead of previously declared filter mappings, depending on the order of other initializers/filters. Verify actual ordering when your application has encoding, logging, CORS, or custom filters.

In a WAR containing `spring-web`, Spring's Servlet `ServletContainerInitializer` discovers `WebApplicationInitializer` implementations on Servlet 3+ containers and runs `onStartup`. Hence this setup **does not need `web.xml`**. Ensure the WAR is deployed to Tomcat 10.1+; this WAR cannot be launched directly with `java -jar` like a Spring Boot application.

### 3.5. Building, Deploying, and Verifying via HTTP

In the directory containing `pom.xml`:

```bash
mvn -q clean package

# Output artifact:
# target/secure-demo.war
```

Copy `target/secure-demo.war` into Tomcat 10.1's `webapps/` directory and start Tomcat. Under default deployment settings, a WAR named `secure-demo.war` gets context path `/secure-demo`. If you change the context path in Tomcat configuration, update that segment in the URLs below.

```bash
# Unauthenticated client:
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/secure-demo/hello
# 401

# Regular user accessing an authenticated URL:
curl -s -u alice:demo123 \
  http://localhost:8080/secure-demo/hello
# hello:alice

# Regular user without ROLE_ADMIN:
curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo123 \
  http://localhost:8080/secure-demo/admin
# 403

# Admin with ROLE_ADMIN:
curl -s -u admin:demo123 \
  http://localhost:8080/secure-demo/admin
# admin:admin
```

These outputs are **expected for the sample configuration** when Tomcat runs properly with no other interfering filters/policies. The `curl` commands use POSIX shell syntax. For HTTP Basic endpoints, clients lacking valid credentials normally receive HTTP 401 with a challenge; authenticated users lacking a required role receive HTTP 403.

If both endpoints return 200 even without an Authorization header, suspect that **the proxy was not properly attached to the Servlet container**, filter mappings do not match, or an old WAR is still running. If startup fails with `NoSuchBeanDefinitionException` for `springSecurityFilterChain`, inspect the root context, `@EnableWebSecurity`, and bean name consistency.

## 4. Option B: `AbstractSecurityWebApplicationInitializer` Registers the Proxy Automatically

Instead of **step 2** in `AppInitializer` above, you can use the initializer provided by Spring Security:

```java
package example.security;

import org.springframework.security.web.context.AbstractSecurityWebApplicationInitializer;

public class SecurityInitializer
        extends AbstractSecurityWebApplicationInitializer {
}
```

When using option B:

- **Keep** the root `WebApplicationContext` creation and `SecurityConfig` registration in `AppInitializer`, as well as registering `GreetingServlet`.
- **Completely remove the `servletContext.addFilter(...)` section in step 2 of `AppInitializer`** so you do not register two proxies with the same name.
- Add a separate `SecurityInitializer`. The base class `AbstractSecurityWebApplicationInitializer` registers `DelegatingFilterProxy` named `springSecurityFilterChain` with the container.
- The no-arg constructor of the subclass is appropriate when the **Spring root context is already created elsewhere**. If you use the constructor taking configuration classes, check what else creates the root context so you do not initialize the context twice.

This approach is usually simpler in Spring Security Java-config projects. It does not replace `@EnableWebSecurity`, `SecurityFilterChain`, or loading the Spring context.

**Applications using Spring MVC should note:** the root context and `DispatcherServlet`'s child context are two distinct bean scopes. If you use `MvcRequestMatcher` or matchers integrating `HandlerMappingIntrospector`, Spring Security configuration must see the matching MVC configuration; many designs place both security and MVC configs inside the servlet application context. When doing so, verify how `DelegatingFilterProxy` accesses the context containing the target bean, or configure the target context explicitly; do not assume a bean in a child context will always be found by a proxy looking in the root context. The example in section 3 uses plain Servlets, so it avoids the MVC matcher integration issue.

## 5. Option C: Registering `DelegatingFilterProxy` via `web.xml`

In a traditional WAR application, you can use `src/main/webapp/WEB-INF/web.xml` instead of **the entire `AppInitializer`** from section 3. The example below creates the annotation root context from `SecurityConfig`, registers the proxy, and maps the servlet:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <context-param>
        <param-name>contextClass</param-name>
        <param-value>org.springframework.web.context.support.AnnotationConfigWebApplicationContext</param-value>
    </context-param>
    <context-param>
        <param-name>contextConfigLocation</param-name>
        <param-value>example.security.SecurityConfig</param-value>
    </context-param>

    <listener>
        <listener-class>org.springframework.web.context.ContextLoaderListener</listener-class>
    </listener>

    <filter>
        <filter-name>springSecurityFilterChain</filter-name>
        <filter-class>org.springframework.web.filter.DelegatingFilterProxy</filter-class>
    </filter>
    <filter-mapping>
        <filter-name>springSecurityFilterChain</filter-name>
        <url-pattern>/*</url-pattern>
    </filter-mapping>

    <servlet>
        <servlet-name>greetingServlet</servlet-name>
        <servlet-class>example.security.GreetingServlet</servlet-class>
    </servlet>
    <servlet-mapping>
        <servlet-name>greetingServlet</servlet-name>
        <url-pattern>/hello</url-pattern>
        <url-pattern>/admin</url-pattern>
    </servlet-mapping>
</web-app>
```

With option C, **do not package `AppInitializer` or `SecurityInitializer` from the previous two approaches** inside the WAR, because the Servlet container can still discover and invoke those initializers automatically. Both `SecurityConfig` and `GreetingServlet` remain unchanged; `web.xml` takes responsibility for creating the root context, registering the filter, and mapping the servlet. Keep **`filter-name` exact as `springSecurityFilterChain`**, because that is the bean name the proxy looks up in the Spring context by default.

In this `web.xml`, `<filter-mapping>` does not declare `<dispatcher>`, so the Servlet spec applies the mapping to `REQUEST` by default. If you need to handle `ASYNC`, `ERROR`, or `FORWARD`, declare the appropriate dispatcher mappings and verify async support/filter ordering.

Do not use `javax.servlet` XML schemas or a WAR running on Tomcat 9 for this Spring 6 example: Tomcat 10.1+ uses the Jakarta Servlet namespace.

## 6. When a Real Application Has Multiple Filters and Multiple Security Chains

### 6.1. Servlet Container Filters vs. Filters Inside Spring Security

There are two registration locations that are easily confused:

1. **Container filters**: registered via `ServletContext.addFilter`, `web.xml`, `@WebFilter`, or container mechanisms. `DelegatingFilterProxy` belongs to this group.
2. **Internal security filters**: added to a `SecurityFilterChain` using `HttpSecurity.addFilterBefore`, `addFilterAfter`, `addFilterAt`, and security configuration mechanisms. This group is invoked by `FilterChainProxy` as configured.

For example, a custom JWT-reading filter that needs to run at a specific position inside the Spring Security chain is normally registered **inside `HttpSecurity`**; do not accidentally register that same instance a second time with the Servlet container, or it may execute twice or in the wrong order. If the filter is a Spring bean and uses auto-registration mechanisms from other Servlet infrastructure, control against duplicate registration.

`DelegatingFilterProxy` is typically registered **once** in the container, while `FilterChainProxy` can hold multiple `SecurityFilterChain`s:

```java
// Illustrated inside a @Configuration class with @EnableWebSecurity.
// Both beans are selected via securityMatcher according to configuration order.
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
```

This is a **standalone illustrative fragment** (do not merge these two methods into section 3's `SecurityConfig`). You also need to import `org.springframework.core.annotation.Order`. `FilterChainProxy` selects the **first matching security chain**; if no chain matches, the request may go unprotected by Spring Security. `securityMatcher(...)` selects the scope **of the entire chain**; `requestMatchers(...)` inside `authorizeHttpRequests` selects the **authorization** rules of the chosen chain.

### 6.2. Dispatcher Types and Execution Order

- Registering `/*` for the proxy reduces the risk of missing URLs; `requestMatchers` can still govern fine-grained permissions inside.
- `REQUEST` covers basic synchronous flows. Secondary dispatches like `FORWARD`, `ASYNC`, and `ERROR` require considering both Servlet container mappings and Spring Security's behavior in the version in use; do not assume all dispatches automatically pass through security if the filter only maps `REQUEST`.
- Avoid registering the security filter **after** another filter that already writes a response or mutates security-relevant state; verify the actual order of container filters and security chain filters with controlled logging.
- On Servlet async, in addition to dispatcher mappings, ensure involved servlets/filters support async and the security context propagates properly when processing on another thread.

## 7. Common Deployment Errors and Diagnosis

| Symptom | Cause to check | Remediation |
| --- | --- | --- |
| Endpoint is accessible without auth | Proxy not registered, mapping mismatch, overly broad `permitAll`, or stale WAR running | Check `/*` mapping, `onStartup`, URLs, and selected filter chain |
| Error `No bean named 'springSecurityFilterChain'` | `SecurityConfig` not loaded, missing `@EnableWebSecurity`, wrong context, or wrong filter target name | Check root/child contexts and infrastructure beans |
| Filter already exists when `addFilter` returns `null` | Duplicate registration by Java initializer and `web.xml`, or two initializers | Choose one registration path; remove the duplicate |
| Application does not invoke `onStartup` | Incompatible container/Servlet API or WAR lacks Spring `ServletContainerInitializer` discovery | Check Tomcat version, `spring-web` inside the WAR, and startup logs |
| `ClassNotFoundException: javax.servlet...` or `jakarta.servlet...` | Mixing major Java EE/Jakarta EE versions | Use Spring 6 + Tomcat 10.1+ + `jakarta.servlet` consistently |
| 401 when no credentials provided | Endpoint requires auth; Basic challenge is working | Log in/test with valid credentials; do not assume a filter bug |
| 403 for a logged-in account | Missing `ROLE_ADMIN` or rule not satisfied; sometimes CSRF or another policy | Inspect authorities and rules/method security/CSRF |
| Using Spring MVC but matcher misses MVC config | Security config cannot see `HandlerMappingIntrospector` in the right context | Place matching matcher config in the context and inspect proxy wiring |
| Custom filter runs twice | Registered in both the container and inside `SecurityFilterChain` | Choose the proper management location; avoid duplicate auto-registration |
| Security context lost on async thread | Context is bound to thread/request, not automatically carried across all async mechanisms | Use context propagation mechanisms supported by Spring Security |

When debugging, first verify **whether the container invokes the proxy**; next, **whether the proxy finds `springSecurityFilterChain`**; then **which chain `FilterChainProxy` selects**; and finally **authentication and authorization**. Those are four distinct layers and keep you from altering permission rules when the real bug lies in filter registration.

Never enable debug or trace mechanisms that could log passwords or Bearer tokens in production environments. You may enable appropriate security logging in development to observe filters/chains while masking sensitive information.

## 8. Exercises to Verify Understanding

1. **If I already have a `SecurityFilterChain` bean, why must I still register `DelegatingFilterProxy`?** Because the Servlet container only runs filters it knows about; the proxy bridges the Servlet filter chain to the Spring Security bean.
2. **Do the name `springSecurityFilterChain` and method name `securityFilterChain` serve the same role?** No. `springSecurityFilterChain` is the filter bean looked up by the proxy; the `SecurityFilterChain` bean describes internal rule/filter configuration.
3. **If using `AppInitializer`, do I also need `web.xml` to register the same filter?** No. Pick one registration mechanism and avoid duplicates.
4. **Why does the URL `/secure-demo/hello` still match the `/hello` matcher?** Matchers operate on the application path under Spring Security's matching mechanism, not taking the `/secure-demo` context path as a prefix in the illustrative rule.
5. **Why does `alice` get 200 on `/hello` yet 403 on `/admin`?** Alice authenticated with `ROLE_USER`, but lacks `ROLE_ADMIN` required by `hasRole("ADMIN")`.
6. **When adding a custom security filter into `HttpSecurity`, should you also register the same filter with `ServletContext.addFilter`?** Normally no; doing so may run it twice or at the wrong position in the chain.
7. **If Spring MVC uses matchers depending on `HandlerMappingIntrospector`, what must be checked?** That Spring Security configuration sees the proper MVC application context and the proxy targets the context containing the target bean.

**Closing principle:** In a non-Boot Servlet application, you simultaneously need a **Spring context containing `springSecurityFilterChain`**, **one `DelegatingFilterProxy` registered exactly once with the container**, and **a filter mapping covering the requests to protect**. Only after wiring those three pieces correctly should you evaluate `SecurityFilterChain` rules, `hasRole/hasAuthority` permissions, and 401/403 outcomes.
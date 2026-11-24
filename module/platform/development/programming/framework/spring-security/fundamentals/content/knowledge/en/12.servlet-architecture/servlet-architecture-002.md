# DelegatingFilterProxy Bridges the Servlet Container to Spring Beans

## 1. Why Does Spring Security Need a Bridge Layer?

An HTTP request enters a Spring Boot/Spring MVC application through a **Servlet Container** such as Tomcat, Jetty, or Undertow (depending on configuration) before DispatcherServlet routes it to a Controller. On the Servlet Container side, Servlet Filters are registered and invoked according to the **Servlet API**. Meanwhile, many Spring Security components are configured as **Spring beans** inside an ApplicationContext.

These are two different management models:

- **Servlet Container** understands Filter registrations, URL mappings, dispatcher types, filter ordering, and Servlet lifecycle callbacks.
- **Spring ApplicationContext** understands bean names, dependency injection, configuration, bean lifecycles, profiles, and framework components.
- **Spring Security** needs to run a chain of Spring-configured security filters before the request reaches the Controller.

**DelegatingFilterProxy** bridges this gap. It is a Servlet Filter provided by **Spring Framework**, invoked by the Servlet Container like any regular filter, but at runtime it **looks up a Spring bean implementing Filter and delegates the doFilter(...) call to that bean**.

For Servlet-based Spring Security, the target bean is typically named **springSecurityFilterChain**, whose actual type is **FilterChainProxy**. FilterChainProxy selects a matching **SecurityFilterChain** and executes that chain's security filters. As a result, the Servlet Container only needs to know one entry point, while Spring manages how the security chain is built and ordered.

**Core takeaway:** DelegatingFilterProxy **does not directly verify passwords, does not decide ROLE_ADMIN itself, and is not the list of security filters**. It is primarily a **bridge** allowing the Servlet Container to invoke a Spring Filter bean.

This lesson belongs to the **Servlet Architecture** group of the **Spring Security - fundamentals** module. Examples use **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**, applying the **jakarta.servlet** namespace. web.xml snippets are included as supplemental illustrations for traditional Servlet deployments.

### Learning Objectives

After this lesson, you will be able to:

1. Trace the path from Servlet Container, DelegatingFilterProxy, FilterChainProxy, and SecurityFilterChain to DispatcherServlet.
2. Explain why the Servlet Container cannot manage all Spring Security beans on its own.
3. Understand **springSecurityFilterChain**, **targetBeanName**, and bean lookup by name.
4. Distinguish between the Servlet Filter lifecycle and the Spring bean lifecycle.
5. Explain why Spring Boot typically does not require manually declaring DelegatingFilterProxy or web.xml.
6. Distinguish FilterChainProxy from SecurityFilterChain and the **first matching chain** rule.
7. Recognize how a Servlet Container-level filter differs from a filter inside the Spring Security chain.
8. Run a Boot application demonstrating both filter layers using HTTP headers and embedded-server tests.
9. Avoid the double-invocation bug when registering the same filter bean in both the Servlet Container and Spring Security.
10. Debug cases where the bean is not found, a request hits the wrong chain, security filters do not run, order is wrong, or an endpoint is unintentionally unprotected.

## 2. First: What Does a Regular Servlet Filter Do?

The Servlet API defines the **jakarta.servlet.Filter** interface. The container builds a filter chain for the request, invoking each Filter in sequence and then the matching Servlet. In Spring MVC, the primary handling Servlet is typically **DispatcherServlet**.

Conceptual flow:

~~~text
Browser or API client
        |
        v
Tomcat / Servlet Container
        |
        v
[Container Filter A]
        |
        v
[Container Filter B]
        |
        v
[Servlet: DispatcherServlet]
        |
        v
Spring MVC HandlerMapping
        |
        v
@RestController
~~~

A filter can:

- Read request and response metadata.
- Wrap or replace request/response wrappers.
- Write security headers.
- Reject the request and return an HTTP response immediately.
- Execute logic before or after downstream components process the request.
- Call **chain.doFilter(request, response)** to pass control to the next component.

Minimal Servlet Filter example:

~~~java
import java.io.IOException;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

public final class AuditFilter implements Filter {

    @Override
    public void doFilter(ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, ServletException {
        // Work to do before forwarding.
        chain.doFilter(request, response);
        // Work to do after downstream processing completes.
    }
}
~~~

This is a **standalone Java class file when named AuditFilter.java in a project with the Jakarta Servlet API**; it only illustrates the Filter contract, is not registered yet, and is not a full server application.

**If a filter does not call chain.doFilter**, downstream filters and the Servlet are not called in that branch. An authentication filter can do this on invalid credentials; a 401 response can be generated **before the Controller runs**. That is why filter ordering is a critical part of security architecture.

### 2.1. Servlet Filter Lifecycle

The Servlet Container manages registration and the **init(FilterConfig)**, **doFilter(...)**, and **destroy()** lifecycle of container filters. A filter may be registered via web.xml, ServletContext registration, or Spring Boot auto-registration.

The container does not inherently know how a Spring bean needs DataSource, UserDetailsService, AuthenticationManager, or AuthenticationProvider injected. It only sees a registered Filter class.

### 2.2. Spring Bean Lifecycle

ApplicationContext creates and wires dependencies for Spring beans, invokes relevant lifecycle callbacks, and destroys beans when the context closes. Spring Security typically coordinates multiple beans: SecurityFilterChain, PasswordEncoder, UserDetailsService, AuthenticationManager, AuthenticationProvider, SecurityContextRepository, and more.

If all filters had to be instantiated directly through the Servlet Container, configuring dependency injection and multi-chain security would become cumbersome. DelegatingFilterProxy lets a container Filter **delegate** into the Spring context.

## 3. Diagram Connecting Both Worlds

~~~text
HTTP request
   |
   v
+-----------------------------------------------+
| Servlet Container (Tomcat)                    |
|                                               |
|   Servlet FilterChain                         |
|      |                                        |
|      +-- Other container filters              |
|      |                                        |
|      +-- DelegatingFilterProxy                |
|                  |                            |
+------------------|----------------------------+
                   |
                   | find bean by name
                   | "springSecurityFilterChain"
                   v
+------------------------------------------------+
| Spring ApplicationContext                      |
|                                                |
| Bean "springSecurityFilterChain"               |
|        |                                       |
|        v                                       |
|   FilterChainProxy  (implements Filter)        |
|        |                                       |
|        +-- SecurityFilterChain /api/**         |
|        |      [security filter 1, ...]         |
|        |                                       |
|        +-- SecurityFilterChain fallback        |
|               [security filter A, ...]         |
+------------------------------------------------+
                   |
                   | return to original chain
                   v
           DispatcherServlet
                   |
                   v
             @RestController
~~~

**Several classes share the word "filter" in their names yet belong to different layers**. That is why distinguishing them before debugging is essential.

| Object | Where Does It Live? | Who Invokes/Selects It? | Primary Responsibility |
| --- | --- | --- | --- |
| Servlet Filter | Container's filter chain | Servlet Container | Handle request/response in the Servlet lifecycle |
| DelegatingFilterProxy | Container's filter chain | Servlet Container | Look up a Spring Filter bean and forward the call |
| FilterChainProxy | Spring ApplicationContext | DelegatingFilterProxy | Manage/select security filter chains and apply Spring Security infrastructure steps |
| SecurityFilterChain | Filter list + matcher | FilterChainProxy | Define security filters for matching requests |
| Security filter | Inside SecurityFilterChain | FilterChainProxy's virtual chain | CSRF, authentication, authorization, headers, session, etc. |
| DispatcherServlet | Spring MVC Servlet | Container filter chain | Select Controller/Handler after filters pass |

**FilterChainProxy is a Filter, whereas SecurityFilterChain is not a Servlet Filter registered directly with Tomcat.** A SecurityFilterChain bean is used by Spring Security to configure a list of filters; it is not the object DelegatingFilterProxy invokes directly by name.

### 3.1. What "Delegate" Actually Means

Simplified pseudo-code:

~~~java
public void doFilter(ServletRequest req,
        ServletResponse res,
        FilterChain chain) throws IOException, ServletException {

    Filter springFilter = lookupSpringBean("springSecurityFilterChain");
    springFilter.doFilter(req, res, chain);
}
~~~

This is **explanatory pseudo-code only**, not the exact source of DelegatingFilterProxy. The real implementation also manages ApplicationContext, lazy lookup, synchronized bean access, lifecycle, target name configuration, exceptions, and reusing the delegate.

Key point to remember: **delegate.doFilter(...) is called with the same request, response, and FilterChain from the Servlet Container**. Once FilterChainProxy and its security filters finish and forward, the request continues through the remaining container chain/DispatcherServlet if not blocked.

### 3.2. DelegatingFilterProxy Does Not Create a New Spring Bean per Request

It can perform **lazy lookup** of the bean once the context is ready and cache the resolved delegate reference. It does not instantiate a new FilterChainProxy for every HTTP request or rebuild the entire Spring Security bean graph on each call.

Deferring lookup is useful because the Servlet Container may need to register filters before Spring ApplicationContext initialization completes. The proxy sits at the container–Spring boundary, while the real target is looked up when the context is accessible.

## 4. springSecurityFilterChain: The Target Bean Name, Not a Controller Name

In traditional Servlet integration, the name **springSecurityFilterChain** is commonly used for both:

- The **filter-name** of DelegatingFilterProxy in the Servlet Container.
- The **Spring bean name** of the FilterChainProxy built by Spring Security.

Why should the two names match? By default, DelegatingFilterProxy uses **filter-name** to determine which bean to delegate to, unless **targetBeanName** is explicitly configured.

For example, if the container registers a DelegatingFilterProxy named **springSecurityFilterChain**, the proxy looks up the Spring bean with that same name. That bean must implement **jakarta.servlet.Filter** (with Spring Framework 6/Boot 3).

If you rename the filter to **mySecurityBridge** without specifying a target bean name, the proxy may look for a bean named mySecurityBridge instead of springSecurityFilterChain and fail to find it. Do not try to fix this by arbitrarily renaming a SecurityFilterChain method; understand the difference between the **bridge bean** and **beans configuring individual security chains**.

### 4.1. What Is targetBeanName?

DelegatingFilterProxy provides a targetBeanName setting to specify the Spring bean name to invoke independently of the container registration name. In web.xml, you can set the **targetBeanName** init-param.

Traditional configuration example:

~~~xml
<filter>
    <filter-name>mySecurityBridge</filter-name>
    <filter-class>
        org.springframework.web.filter.DelegatingFilterProxy
    </filter-class>
    <init-param>
        <param-name>targetBeanName</param-name>
        <param-value>springSecurityFilterChain</param-value>
    </init-param>
</filter>

<filter-mapping>
    <filter-name>mySecurityBridge</filter-name>
    <url-pattern>/*</url-pattern>
</filter-mapping>
~~~

This is a **fragment meant to sit inside a valid web.xml of a traditional Servlet application**, not a complete web.xml file. In a typical Boot executable jar, **you do not need to write this fragment**.

If filter-name is already springSecurityFilterChain, the targetBeanName init-param is usually unnecessary. Changing it is only useful in specialized setups or legacy apps that already use a custom filter-name.

### 4.2. Bean Name Mismatch Diagram

~~~text
Servlet filter-name = myProxy
targetBeanName      = not specified
Spring Filter bean  = springSecurityFilterChain

DelegatingFilterProxy tries to find "myProxy"
      |
      v
No Filter bean named "myProxy"
      |
      v
Configuration/initialization error or error on request handling
~~~

**Always inspect the actual error message**, because when bean lookup occurs depends on initialization mode and context state. Never assume the failure always happens at startup or always yields HTTP 500; bean lookup can happen when a request arrives.

### 4.3. DelegatingFilterProxy Is Not Exclusively for Spring Security

Any **Spring bean implementing Filter** can be a target. Spring Security uses this mechanism as its standard entry point, but DelegatingFilterProxy is a **Spring Framework** class, not a special "password-only filter".

For instance, another Filter bean can be delegated by the container under its own name; however, you should not create separate DelegatingFilterProxies for individual Spring Security filters when FilterChainProxy already manages them.

## 5. Lifecycle: Who Calls init and destroy?

This is a subtle distinction often missed when writing custom Servlet Filters.

| Task | Managed By / Target |
| --- | --- |
| Container initializes registered Filter | DelegatingFilterProxy |
| Spring creates FilterChainProxy bean | Spring ApplicationContext |
| Spring wires dependencies for filters/beans | ApplicationContext |
| DelegatingFilterProxy looks up target and invokes doFilter | Upon request |
| Spring closes context/bean lifecycle | ApplicationContext |
| Container destroys filter proxy | Servlet Container |

According to the **DelegatingFilterProxy** Javadoc, the **targetFilterLifecycle** property defaults to **false**. That means **Servlet Filter init/destroy are not delegated to the target Spring bean by default the way the container calls the proxy**. Typical usage lets Spring ApplicationContext manage the target bean's lifecycle.

If targetFilterLifecycle=true is set, the proxy forwards Servlet Filter init/destroy to the target per the container lifecycle; that option is for very specific cases and must avoid conflicting with Spring-managed lifecycles.

~~~xml
<init-param>
    <param-name>targetFilterLifecycle</param-name>
    <param-value>true</param-value>
</init-param>
~~~

This is an **illustrative legacy configuration fragment**, not a recommended default. Do not turn it on just because a custom filter has `@PostConstruct` or wants lifecycle logs; Spring already has its own bean lifecycle.

### 5.1. FilterChainProxy Does Not Call init/destroy for Every Security Filter

Spring Security **does not rely on the Servlet Container to initialize individual filters inside SecurityFilterChain**. Nor does FilterChainProxy call standard Filter lifecycle methods on each filter in the list the way a container initializes them. Use Spring bean initialization or appropriate lifecycle mechanisms when writing custom security filters.

Do not register every security filter as a standalone Servlet Filter in web.xml just to "ensure init is called". Doing so can break ordering, lose HttpFirewall protection, and cause filters to run outside the security chain.

### 5.2. When to Use a Filter Bean vs. new Filter?

In Spring Boot, a custom Filter declared with `@Component` or `@Bean` can be **auto-registered with the Servlet Container**. If you also insert it into SecurityFilterChain via http.addFilterBefore/After, the same filter can run at **both layers**.

Therefore, when you want a filter strictly inside Spring Security, you can usually instantiate it with `new CustomFilter(...)` inside the HttpSecurity configuration, or—if it needs bean injection—declare the bean and **disable container registration** using a disabled FilterRegistrationBean. Section 11 shows an example.

## 6. How Does Boot 3 Differ from a Traditional Servlet Application?

### 6.1. In a Boot Executable Jar Application

With **spring-boot-starter-security** and a valid Servlet Security configuration, Spring Boot typically auto-registers a DelegatingFilterProxy into the embedded Servlet Container via **DelegatingFilterProxyRegistrationBean** targeting the **springSecurityFilterChain** bean.

You only need to declare a SecurityFilterChain bean for your application policy:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is a **snippet inside a configuration class with imports** and an HttpSecurity bean. You do not need to write **new DelegatingFilterProxy()**, you do not need web.xml, and you typically do not need to declare a FilterRegistrationBean for Spring Security.

**Spring Boot SecurityAutoConfiguration, WebSecurityConfiguration, and SecurityFilterAutoConfiguration** have distinct responsibilities when creating beans and registering filters. Do not confuse "I declared a SecurityFilterChain bean" with "I manually registered a servlet filter". Boot wires both infrastructure layers via auto-configuration.

### 6.2. What Happens When You Add a SecurityFilterChain Bean?

Spring Boot typically backs off from its default web security policy when you define your own SecurityFilterChain, yet **the Servlet Container → springSecurityFilterChain bridge still must work**.

Do not manually add a second DelegatingFilterProxy just because you wrote a new SecurityFilterChain bean. Doing so can cause security processing to run twice or create confusing ordering.

### 6.3. Legacy WAR and web.xml

In a classic Servlet-configured WAR application, you may see:

~~~xml
<filter>
    <filter-name>springSecurityFilterChain</filter-name>
    <filter-class>
        org.springframework.web.filter.DelegatingFilterProxy
    </filter-class>
</filter>
<filter-mapping>
    <filter-name>springSecurityFilterChain</filter-name>
    <url-pattern>/*</url-pattern>
</filter-mapping>
~~~

This is a **web.xml snippet**, not a Spring bean definition. It tells the Servlet Container to invoke the proxy for requests matching /*. The Spring ApplicationContext must contain a Filter bean named springSecurityFilterChain.

Modern Servlet applications can use **AbstractSecurityWebApplicationInitializer** or programmatic registration instead of web.xml. However, **never configure both web.xml and auto-registration for the same proxy** unless you intentionally design and account for every registration.

### 6.4. Checking the Bean Directly

Inside a Spring context you can check:

~~~java
Object bean = applicationContext.getBean(
    "springSecurityFilterChain");

System.out.println(bean.getClass().getName());
~~~

This is a snippet inside a method that already has an ApplicationContext. In a standard configuration, you expect an implementation of **FilterChainProxy**. However, checking the Spring bean **does not by itself prove the Servlet Container registered DelegatingFilterProxy**; you need runtime container inspection or real HTTP integration tests.

### 6.5. Controlling Registration Order in Boot

Spring Boot provides configuration properties for filter registration order, including **spring.security.filter.order** in supported versions. This adjusts the **position of the security filter at the Servlet Container level**, not the internal order of security filters.

To change internal ordering, use the HttpSecurity DSL such as addFilterBefore/After/At with deliberate reasoning. Do not tweak the container filter order to fix "BasicAuthenticationFilter runs before AuthorizationFilter", because that order lives **inside FilterChainProxy**.

## 7. FilterChainProxy and SecurityFilterChain: The Next Two Layers

DelegatingFilterProxy merely hands the request into the Spring bean. The rest is handled by **FilterChainProxy**.

FilterChainProxy holds a list of **SecurityFilterChain** instances. Each SecurityFilterChain has a RequestMatcher and a list of Filters; FilterChainProxy evaluates them in order and selects the **first chain matching the request**.

~~~text
DelegatingFilterProxy
       |
       v
FilterChainProxy
       |
       +-- Chain 1: securityMatcher("/api/**") ?
       |         YES -> run Chain 1's filters, STOP checking chains
       |
       +-- Chain 2: securityMatcher("/admin/**") ?
       |         YES -> run Chain 2's filters
       |
       +-- Chain 3: fallback (any request) ?
                 YES -> run fallback filters
~~~

**Filters from all matching SecurityFilterChains are not cumulative.** Only the first chain is selected in standard setups. That is why **@Order** and securityMatcher matter when multiple chains exist.

### 7.1. securityMatcher vs. requestMatchers in authorizeHttpRequests

- **securityMatcher(...)** defines the **scope of the entire SecurityFilterChain**.
- **requestMatchers(...)** inside authorizeHttpRequests defines an **authorization rule** for requests that have already entered that chain.

Example:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll()
        )
        .build();
}
~~~

This is a **snippet containing two beans inside a configuration class**, not a complete project. Spring Security provides an HttpSecurity builder per chain. The api chain takes precedence for /api/**; the fallback denies all other requests.

If no chain matches, **Spring Security does not protect the request with security filters**. The Servlet Container may still invoke DelegatingFilterProxy and FilterChainProxy, yet no SecurityFilterChain applies. This is a major difference between "Spring Security is on the classpath" and "every URL is protected".

### 7.2. permitAll vs. Bypassing FilterChainProxy

A **permitAll()** rule allows the request in terms of authorization, but it **does not mean the request skips all security filters**. FilterChainProxy can still run headers, CSRF, security context, authentication filters, and other configured components.

Conversely, bypassing security via **WebSecurityCustomizer.ignoring(...)** or lacking a matching chain can leave the request without protections provided by Spring Security. For normal public endpoints, using **permitAll** and a proper fallback chain is usually preferable.

### 7.3. What Else Does FilterChainProxy Provide Beyond Selecting a Chain?

According to the official documentation, FilterChainProxy is the central entry point and can:

- Apply **HttpFirewall** to validate/normalize request details for matching.
- Manage the request/response passing through the virtual filter chain.
- Keep security filter ordering consistent.
- Coordinate with filters managing the SecurityContext lifecycle.
- Serve as a convenient breakpoint/inspection point for debugging Spring Security.

**Do not register individual security filters directly with the Servlet Container** to replace FilterChainProxy. Doing so loses flexible chain selection and can bypass HttpFirewall or required security ordering.

## 8. Comparing Servlet Filter and Spring Security Filter

| Characteristic | Servlet Container-Level Filter | Filter Inside SecurityFilterChain |
| --- | --- | --- |
| Registration | web.xml, ServletContext, or FilterRegistrationBean | HttpSecurity, SecurityFilterChain |
| Who selects the filter? | Servlet Container by URL/dispatcher mapping | FilterChainProxy by RequestMatcher |
| Ordering | Container registration order | Security Filter Chain order |
| Dependency injection | Possible via Spring Boot bean, but must manage registration | Typically supplied by Spring Security or HttpSecurity config |
| Runs when request matches no security chain? | May still run per container mapping | Does not run if no matching SecurityFilterChain exists |
| Lifecycle init/destroy | Container responsible for Filter registration | Not automatically invoked by container for each security filter |
| Examples | Logging/tracing Servlet Filter | CsrfFilter, BasicAuthenticationFilter, AuthorizationFilter |
| Debugging approach | Container registration, order, dispatcher type | Spring Security DEBUG, matcher, filter list |

### 8.1. An Actual Request Passing Through Both Filter Types

Suppose there is a **ContainerProbeFilter** and a **SecurityProbeFilter**:

~~~text
GET /private
    |
    v
ContainerProbeFilter (container-level)
    |  adds X-Lab-Container-Filter: hit
    v
DelegatingFilterProxy (container-level)
    |
    v
FilterChainProxy (Spring bean)
    |
    v
SecurityProbeFilter (security-chain-level)
    |  adds X-Lab-Security-Filter: hit
    v
BasicAuthenticationFilter
    |
    v
AuthorizationFilter
    |
    +-- valid credentials/authority -> Controller, 200
    |
    +-- insufficient credentials -> 401
~~~

The diagram shows only the parts relevant to this lesson; many other filters exist between them. In code, SecurityProbeFilter is placed before BasicAuthenticationFilter; for any request blocked by an earlier filter, the probe header may not appear. Therefore **do not treat a lab header as absolute proof that every request goes through every filter**.

### 8.2. Why Not Write One Custom Filter That Handles Everything?

A Servlet Filter can do a lot, yet Spring Security provides standardized infrastructure for credential verification, SecurityContext, CSRF, exception handling, and authorization. Writing a single custom filter that compares Basic headers with String.equals and grants roles from the request easily introduces vulnerabilities.

Use built-in authentication mechanisms unless you have a specific evaluated requirement, and then add custom filters in the proper position only when truly needed.

## 9. Runnable Spring Boot 3.x App Observing Both Filter Layers

To observe the proxy bridge clearly via **HTTP response signals**, we create:

1. **ContainerProbeFilter** registered with FilterRegistrationBean at the Servlet Container level.
2. **SecurityProbeFilter** added solely via HttpSecurity.addFilterBefore(...), inside SecurityFilterChain.
3. **SecurityFilterChain** requiring authentication for /private and role ADMIN for /admin.
4. **Controller** returning short strings without exposing the Authentication object.
5. **Embedded-server integration test** verifying the HTTP response includes both probe headers.

**Goal:** observe that Servlet Filters and Security Filters are registered in different places, not to build DelegatingFilterProxy manually; Boot creates the bridge between the container and the springSecurityFilterChain bean automatically.

### 9.1. Project Setup and Dependencies

Create a Java 17+, Spring Boot 3.x, Gradle Groovy DSL project with Gradle Wrapper via Spring Initializr including Spring Web, Spring Security, and Spring Boot Starter Test.

In the dependencies block of **build.gradle**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the **dependencies section of a project with the Spring Boot plugin, Java toolchain, and dependency management**, not a standalone complete build.gradle file.

### 9.2. Complete Java File

Create **src/main/java/com/example/filterbridge/FilterBridgeApplication.java**:

~~~java
package com.example.filterbridge;

import java.io.IOException;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class FilterBridgeApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterBridgeApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("local-learn-123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("local-admin-123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    FilterRegistrationBean<ContainerProbeFilter> containerProbe() {
        FilterRegistrationBean<ContainerProbeFilter> registration =
            new FilterRegistrationBean<>(new ContainerProbeFilter());

        registration.setName("containerProbe");
        registration.addUrlPatterns("/*");

        // Intentionally placed before Spring Security at the container level
        // in this experiment's default Boot configuration.
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);

        return registration;
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // new: do not create a Filter bean for Boot to auto-register.
            .addFilterBefore(
                new SecurityProbeFilter(),
                BasicAuthenticationFilter.class
            )
            .build();
    }
}

// Invoked by Servlet Container via FilterRegistrationBean.
final class ContainerProbeFilter implements Filter {

    @Override
    public void doFilter(ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, ServletException {

        ((HttpServletResponse) response).setHeader(
            "X-Lab-Container-Filter", "hit");

        chain.doFilter(request, response);
    }
}

// Invoked only by FilterChainProxy, after a chain is selected.
final class SecurityProbeFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        response.setHeader("X-Lab-Security-Filter", "hit");
        chain.doFilter(request, response);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    String privateEndpoint(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

**Self-containedness:** This is **one complete Java file in a Boot project**; the public class FilterBridgeApplication matches the file name, with package-private helper classes in the same package. Java 17 and Spring Security 6.x use **jakarta.servlet** rather than javax.servlet. If copying into Boot 2.x you must account for different versions/namespaces rather than changing imports arbitrarily.

### 9.3. Explaining Each Component

**ContainerProbeFilter:**

- Implements jakarta.servlet.Filter.
- Registered by FilterRegistrationBean with the Servlet Container for /*.
- Adds the header X-Lab-Container-Filter=hit and calls chain.doFilter.
- Is not in the list of Spring Security filters created by HttpSecurity.

**SecurityProbeFilter:**

- Extends OncePerRequestFilter.
- Instantiated with **new** inside SecurityFilterChain, not an auto-registered Spring bean in the Servlet Container.
- Placed **before BasicAuthenticationFilter** via addFilterBefore.
- Adds X-Lab-Security-Filter=hit and invokes the filter chain.

**SecurityFilterChain:**

- /public: permitAll, still passes through the security filter chain.
- /private: requires valid Authentication.
- /admin: requires ROLE_ADMIN.
- httpBasic reads the Authorization header and uses the standard manager/provider to verify.
- formLogin is disabled to avoid login pages/redirects in this lesson.
- Does not manually add/register DelegatingFilterProxy.

**UserDetailsService + PasswordEncoder:**

- InMemoryUserDetailsManager holds local demo accounts only.
- Passwords are BCrypt-encoded before entering the user store.
- Real logins still go through the appropriate AuthenticationManager/DaoAuthenticationProvider.
- Raw demo passwords are for isolated localhost use only; never use sample accounts/passwords in deployed environments.

### 9.4. Why Can Both Headers Appear on /public?

Because **permitAll** does not skip Servlet filters or SecurityFilterChain. A normal GET /public still passes through:

1. ContainerProbeFilter.
2. DelegatingFilterProxy → springSecurityFilterChain bean.
3. FilterChainProxy and SecurityProbeFilter.
4. /public Controller.

In the example setup, the two headers:

~~~http
X-Lab-Container-Filter: hit
X-Lab-Security-Filter: hit
~~~

Are **lab observation markers only**, not standard security headers required by Spring Security. Do not use them as an authentication/authorization mechanism, and do not keep them in production unnecessarily.

### 9.5. Trying It Out

In the project directory with Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell use **.\gradlew.bat bootRun**. Assuming the server runs on http://localhost:8080:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u learner http://localhost:8080/private
curl -i -u learner http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
~~~

With **curl -u learner** or **curl -u admin** without a colon and password on the command line, curl prompts for the password in the terminal. Enter the corresponding demo password from the source when prompted; use **curl.exe** in PowerShell if curl is an alias.

HTTP Basic uses Base64 and **does not protect credentials without TLS**. On real networks you must use HTTPS. Never put real passwords in URLs, logs, or shell history.

### 9.6. Expected HTTP Results

| Request | HTTP status | Expected Body | Meaning |
| --- | --- | --- | --- |
| GET /public anonymous | **200** | public OK | permitAll, chain still runs |
| GET /private anonymous | **401** | depends on Basic entry point | Unauthenticated |
| GET /private learner valid password | **200** | hello learner | Authentication succeeded |
| GET /admin learner valid password | **403** | depends on handler | Authenticated, lacks ROLE_ADMIN |
| GET /admin admin valid password | **200** | admin OK | Has ROLE_ADMIN |

Both X-Lab-* headers are expected on normal paths passing through both probe filters. Do not assume every error dispatch, firewall-blocked request, or exception in a filter before the probe will include both headers.

This table shows **expectations inferred from the code**, not logs measured from a live server run in this article. Container and Spring Security filter ordering can change when an application adds other registrations; always verify actual runtime behavior.

## 10. Testing Through the Embedded Servlet Container Instead of Only MockMvc

MockMvc is very useful for testing SecurityFilterChain and Controllers, yet **it does not necessarily run embedded Tomcat's full Servlet Filter registration mechanism** like a real HTTP server.

To confirm that **both filters at different layers execute**, use an integration test with **webEnvironment=RANDOM_PORT**. Spring Boot starts an embedded server on a random port; TestRestTemplate sends real HTTP requests through the container.

Create **src/test/java/com/example/filterbridge/FilterBridgeApplicationTest.java**:

~~~java
package com.example.filterbridge;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.FilterChainProxy;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterBridgeApplicationTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    ApplicationContext context;

    @Test
    void springSecurityFilterChainIsFilterChainProxyBean() {
        assertInstanceOf(FilterChainProxy.class,
            context.getBean("springSecurityFilterChain"));
    }

    @Test
    void realHttpRequestPassesBothFilterLayers() {
        ResponseEntity<String> response =
            rest.getForEntity("/public", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("public OK", response.getBody());

        assertEquals("hit", response.getHeaders()
            .getFirst("X-Lab-Container-Filter"));
        assertEquals("hit", response.getHeaders()
            .getFirst("X-Lab-Security-Filter"));
    }

    @Test
    void authenticationAndAuthorizationRemainCorrect() {
        ResponseEntity<String> anonymous =
            rest.getForEntity("/private", String.class);
        assertEquals(HttpStatus.UNAUTHORIZED,
            anonymous.getStatusCode());

        ResponseEntity<String> learner =
            rest.withBasicAuth("learner", "local-learn-123")
                .getForEntity("/private", String.class);

        assertEquals(HttpStatus.OK, learner.getStatusCode());
        assertEquals("hello learner", learner.getBody());

        ResponseEntity<String> forbidden =
            rest.withBasicAuth("learner", "local-learn-123")
                .getForEntity("/admin", String.class);
        assertEquals(HttpStatus.FORBIDDEN,
            forbidden.getStatusCode());

        ResponseEntity<String> admin =
            rest.withBasicAuth("admin", "local-admin-123")
                .getForEntity("/admin", String.class);
        assertEquals(HttpStatus.OK, admin.getStatusCode());
        assertEquals("admin OK", admin.getBody());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

On PowerShell: **.\gradlew.bat test**.

### 10.1. What Do the Tests Prove?

- The Spring context has a **springSecurityFilterChain** bean that is a FilterChainProxy.
- A real HTTP request through the embedded server receives the header from **ContainerProbeFilter**.
- The same request receives the header from **SecurityProbeFilter** inside the security chain.
- /public still runs both layers despite permitAll.
- HTTP Basic + hasRole distinguish 401 unauthenticated, 403 missing role, and 200 success.

### 10.2. What Do the Tests Not Prove Yet?

- They do not prove the security chain protects all new URLs when multiple chains are added; test matching separately.
- They do not test all ASYNC/ERROR dispatcher types or third-party Servlet filters.
- They do not test production proxies/load balancers.
- They do not test init/destroy lifecycle events for all filters.
- They do not prove no other custom filter is auto-registered twice.
- They do not evaluate CSRF with POST/PUT/DELETE; the demo only includes GET endpoints.
- They do not test session persistence/logout/MFA/resource-level authorization.

**Never treat lab HTTP header tests as a comprehensive security guarantee.** They only demonstrate the observable path in the configured setup.

## 11. Common Pitfall: Custom Filter Bean Invoked Twice

A frequent mistake in Spring Boot:

1. A developer writes **@Component MyFilter extends OncePerRequestFilter** or **@Bean MyFilter**.
2. Spring Boot sees the Filter bean and auto-registers it with the Servlet Container.
3. The developer also calls **http.addFilterBefore(myFilter, BasicAuthenticationFilter.class)**.
4. The filter can be invoked at both the Container level and inside SecurityFilterChain, at different orders.

Consequences can include:

- Duplicated logs/auditing, extra load, or repeated side effects.
- The filter running before SecurityContext is restored.
- CORS/CSRF/authorization checks occurring at the wrong time.
- Overwritten headers or prematurely committed responses.
- Debugging looks like "filter didn't run" because OncePerRequestFilter detects already-filtered in one branch, yet the registration itself is still wrong.
- Different behavior between REQUEST and ERROR dispatches.

### 11.1. Simplest Way to Avoid This

If a filter is meant only for Spring Security, instantiate it inside HttpSecurity instead of declaring it as a bean Boot will auto-register:

~~~java
http.addFilterBefore(
    new SecurityProbeFilter(),
    BasicAuthenticationFilter.class
);
~~~

In the demo application, SecurityProbeFilter is neither `@Component` nor a `@Bean`, so it **never appears automatically on the container chain**.

### 11.2. When a Filter Needs Dependency Injection as a Spring Bean

You can define the filter bean and a **disabled FilterRegistrationBean** so Boot does not register it at the container level:

~~~java
@Bean
MySecurityFilter mySecurityFilter(MyService service) {
    return new MySecurityFilter(service);
}

@Bean
FilterRegistrationBean<MySecurityFilter> disableContainerRegistration(
        MySecurityFilter filter) {

    FilterRegistrationBean<MySecurityFilter> registration =
        new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}

@Bean
SecurityFilterChain security(HttpSecurity http,
        MySecurityFilter filter) throws Exception {

    http.addFilterBefore(
        filter, BasicAuthenticationFilter.class);

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is a **design snippet** placed in a `@Configuration` class with appropriate imports; MySecurityFilter and MyService are two application classes you must define yourself. It is not a standalone runnable Java file. Meaning of disabled registration: the filter bean still exists for dependency injection, yet **is not auto-registered with the Servlet Container by Boot**; HttpSecurity is the sole path placing it into the security chain.

### 11.3. Never Register BasicAuthenticationFilter Directly on the Container

BasicAuthenticationFilter depends on AuthenticationManager and security context/exception handling; the Spring Security DSL already provides the right placement for HTTP Basic via **httpBasic(Customizer.withDefaults())**.

Do not extract BasicAuthenticationFilter as `@Component` or wrap it in a container FilterRegistrationBean just to make it "run earlier". The same applies to AuthorizationFilter, CsrfFilter, and other standard security filters; configure them through HttpSecurity and follow FilterChainProxy's architecture.

### 11.4. What Happens If addFilterAt Collides with a DSL Filter?

HttpSecurity has addFilterBefore, addFilterAfter, and addFilterAt. When placing a filter at the position of a standard filter, check the version and whether another component already registered a filter at that slot. Do not configure httpBasic(...) and then arbitrarily add a replacement BasicAuthenticationFilter without understanding the chain; some configurations may be rejected or behave unexpectedly.

## 12. Legacy Servlet WAR vs. Spring Boot: Checking the Right Registration Point

| Model | How the Bridge Is Registered | Characteristics |
| --- | --- | --- |
| Servlet WAR with web.xml | filter-name/filter-class DelegatingFilterProxy + mapping | Needs Spring target bean with matching name or targetBeanName |
| Servlet WAR without XML | AbstractSecurityWebApplicationInitializer or programmatic registration | Must avoid duplicate registrations |
| Boot embedded server | Auto-configuration registers DelegatingFilterProxyRegistrationBean | Usually only need to write SecurityFilterChain |
| Custom filter container-only | FilterRegistrationBean or @Component Filter | Not automatically inside SecurityFilterChain |
| Custom filter security-only | HttpSecurity.addFilterBefore/After/At | Must not auto-register on container a second time |
| Reactive WebFlux | WebFilterChainProxy/SecurityWebFilterChain and Reactor context | **Does not use Servlet DelegatingFilterProxy** |

### 12.1. WebFlux Does Not Use the Servlet Filter Chain

If the application uses Spring WebFlux/reactive stack, the security architecture is different: **WebFilter** and SecurityWebFilterChain, not Jakarta Servlet Filter. Do not copy DelegatingFilterProxy or Servlet FilterRegistrationBean into a reactive application and expect HttpSecurity to process requests.

This lesson covers the Servlet stack only. In an application mixing Web + WebFlux dependencies, determine the actual web application type before choosing APIs.

### 12.2. Dispatcher Types REQUEST, ERROR, and ASYNC

Servlet Filter registration can be scoped by dispatcher type. Initial HTTP requests typically have dispatcher type REQUEST; an exception can trigger an ERROR dispatch, or an async dispatch may occur during asynchronous processing.

Therefore:

- Never assume a custom filter automatically runs in all ERROR/ASYNC dispatches.
- When adjusting container-level registration, check the appropriate dispatcher types for your framework version.
- With OncePerRequestFilter, there are also hooks controlling async/error dispatch handling; the word "once" does not mean "strictly once across every operation of the entire HTTP request and every dispatch".
- For authentication and SecurityContext, use proper context propagation/clearing mechanisms in async workloads.

A header added only on REQUEST dispatch is not proof the filter will always run on ERROR dispatch. Write integration tests covering the required dispatcher types if your policy depends on them.

## 13. Debugging DelegatingFilterProxy and FilterChainProxy Layer by Layer

When a request gets an unexpected 401/403 or exposes an endpoint, debug along these boundaries:

~~~text
A. Does the Servlet Container invoke the bridge filter?
             |
             v
B. Does DelegatingFilterProxy find the right target bean?
             |
             v
C. Does FilterChainProxy receive the request and select the right chain?
             |
             v
D. Within that chain, are the required filters present and in the right order?
             |
             v
E. Does the authentication filter receive the right credentials?
             |
             v
F. Does the authorization rule permit the request?
             |
             v
G. Does the request reach DispatcherServlet/Controller?
~~~

### 13.1. Step A — Verify Container Registration

Inspect Boot startup logs, embedded server registrations, or ServletContext.getFilterRegistrations() in a test environment. Never look solely at the SecurityFilterChain Spring bean and conclude the Servlet Container actually invoked the security bridge.

For a WAR app with web.xml, check filter-mapping /*, filter name, dispatcher types, and order. If WebApplicationInitializer coexists with web.xml, verify there are no duplicate registrations.

### 13.2. Step B — Does the Target Bean Have the Right Name?

In the Spring context, the name is normally **springSecurityFilterChain**. Check via ApplicationContext.getBean(...) or inspect DelegatingFilterProxy's delegate lookup error. Failure to find the bean can stem from context initialization failure, filter-name differing from targetBeanName, or the bean residing in a different ApplicationContext.

Do not "quick fix" this by creating another bean named springSecurityFilterChain of a different type instead of FilterChainProxy; that can disable the entire security architecture.

### 13.3. Step C — Which Chain Does FilterChainProxy Select?

With multiple chains, inspect **@Order**, **securityMatcher**, RequestMatcher, and fallback. If a new route matches no chain, Spring Security may not protect it. If an `/api/**` chain matches before the fallback, the fallback's rules do not automatically apply to `/api/**`.

Use appropriate diagnostics/logs and integration tests per route, GET/POST methods, requests with/without credentials, and statuses 200/401/403.

### 13.4. Step D — Filter List and Ordering

Enable appropriate logging in a controlled test environment, for example:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
~~~

This is a **logging configuration snippet for test-environment investigation only**. Exact logger names and detail levels may vary across versions. Spring Security documentation describes printing the filter list at startup under DEBUG.

Do not enable broad TRACE in production if it could log Authorization, Cookies, credentials, or request bodies. A filter can run in the wrong position if you rely on container registration instead of HttpSecurity.

### 13.5. Step E — Authentication

FilterChainProxy running yet still returning 401 can be valid behavior: missing/wrong credentials, HTTP Basic not enabled, invalid session/token, or misconfigured UserDetailsService/PasswordEncoder.

DelegatingFilterProxy does not verify passwords, so do not try to fix this by changing targetBeanName or adding a second bridge when the manager/provider is the real culprit.

### 13.6. Step F — Authorization

An authenticated user with ROLE_USER calling `/admin` requiring ROLE_ADMIN typically gets 403. A 403 does not mean DelegatingFilterProxy is broken. It could also be CSRF, CORS, or business permissions; identify which filter/handler rejected the request.

### 13.7. Step G — Request Does Not Reach the Controller

If a security filter rejects the request and does not invoke the rest of the chain, DispatcherServlet does not run. Never conclude the Servlet Container or DelegatingFilterProxy is broken solely because a breakpoint inside `@RestController` was not hit.

## 14. Symptom and Troubleshooting Table

| Symptom | Possible Cause | First Check |
| --- | --- | --- |
| SecurityFilterChain bean exists yet URL is unprotected | Wrong bridge registration or no matching chain | Container registrations and securityMatcher |
| Bean springSecurityFilterChain not found | Spring context/auto-config failure | ApplicationContext, classpath, @EnableWebSecurity |
| DFP looks for myProxy instead of springSecurityFilterChain | Different filter-name, targetBeanName unset | web.xml or registration target name |
| App startup fails with duplicate filter registrations | Both web.xml and Boot/initializer register it | Remove redundant bridge |
| Custom filter invoked twice | Bean auto-registration + HttpSecurity.addFilter | Disable container registration or instantiate with new in chain |
| Custom filter sees Authentication=null | Runs before context/authentication filter | Check position in FilterChainProxy |
| `/api/**` URL uses fallback web rules | @Order/securityMatcher not as intended | Check first matching chain |
| Public endpoint with bad Basic header gets 401 | Authentication filter still runs before permitAll | Distinguish authentication failure from authorization |
| GET /admin 403 despite valid login | Missing ROLE_ADMIN | Check granted authorities and hasRole |
| POST 403 before Controller | Missing/invalid CSRF token | CsrfFilter and client token |
| Error page lacks probe header | DispatcherType/early short-circuit | Inspect ERROR dispatch |
| Async task loses SecurityContext | ThreadLocal does not propagate automatically | Use proper context propagation |
| Container filter order changed yet internal order unchanged | Edited the wrong filter layer | HttpSecurity order vs FilterRegistrationBean |
| Request to `/unknown` returns 401/403 instead of 404 | Security filter blocked before MVC | Check `anyRequest` rule |
| WebFlux app has no DelegatingFilterProxy | Not using Servlet stack | Check WebFilterChainProxy/SecurityWebFilterChain |

### 14.1. Do Not Add Another Filter Proxy to "Fix" 401/403

If a request already passed through FilterChainProxy and Authn/Authz intentionally returned 401/403, adding another DelegatingFilterProxy only increases processing overhead. Find the actual layer responsible for denying it.

### 14.2. Do Not Push Authorization Logic into Hand-Written Container Filters

A container-level filter may execute before SecurityContext is restored or before AuthenticationFilter. If decisions depend on authorities or tenant/ownership, place logic in method security/service layer or a custom security filter positioned after the necessary steps.

### 14.3. Why Are permitAll and ignoring Not the Same?

With permitAll, FilterChainProxy still selects a chain; headers/CSRF/context filters can still run. When you exclude via ignoring or have no matching chain, many Spring Security protections are skipped. Do not use ignoring for public endpoints just to trim a few log lines while sacrificing essential security headers.

## 15. Performance and Observability Considerations

DelegatingFilterProxy exists to forward calls into a Spring-managed bean. It does not ask the container to recreate security filters or UserDetailsService on every request. Actual throughput typically depends on authentication/token validation, database lookups, sessions, serialization, network, and custom filters.

Key points to watch:

- **Filter bean state:** a filter can process many concurrent requests; avoid storing current user/session in instance fields or static variables.
- **SecurityContext:** scoped per request/session or token; never use a global variable representing "currentUser".
- **Filter order:** container-level logs/tracing and security filters may measure different intervals; know which layer runs first when interpreting metrics.
- **Exception behavior:** filters can short-circuit the chain early, so 401/403 responses might lack markers added by downstream filters.
- **Sensitive data:** never log raw Authorization, Cookie, passwords, JWTs, refresh tokens, or entire Authentication objects.
- **Distributed apps:** proxies/load balancers/session stores can alter behavior; never assume embedded-server integration tests mirror production 100%.

If correlation is needed, use controlled request ID/timing metadata without putting credentials into logs. A tracing Servlet Filter outside the security chain must check dispatcher types and exception handling so it never writes sensitive responses.

## 16. Checklist When Applying Servlet Security Architecture

- [ ] Confirm the app actually uses **Servlet**, not WebFlux.
- [ ] Spring Boot has a valid springSecurityFilterChain/FilterChainProxy bean.
- [ ] The container has only **one expected bridge registration** per security processing path.
- [ ] Do not manually add DelegatingFilterProxy when Boot already auto-registers it.
- [ ] Do not confuse a SecurityFilterChain bean with a Servlet Filter.
- [ ] If using legacy web.xml, filter-name or targetBeanName points to the right bean.
- [ ] Understand targetFilterLifecycle defaults to false; do not enable true unless needed.
- [ ] With multiple chains, @Order and securityMatcher are clear, with a proper fallback.
- [ ] Do not unintentionally leave URLs outside every SecurityFilterChain.
- [ ] Use permitAll for public endpoints that should still receive security filters.
- [ ] Custom security filters are not simultaneously auto-registered on the Servlet Container.
- [ ] Custom filters are placed before/after appropriate filters based on context/authentication needs.
- [ ] Never construct trusted Authentication from unverified user input.
- [ ] Have tests covering GET/POST, anonymous/authenticated/forbidden, and new routes.
- [ ] Have embedded Servlet Container tests when verifying real registration is needed.
- [ ] Verify CSRF/session/ERROR/ASYNC dispatcher behavior in practice.
- [ ] Avoid printing Authorization, cookies, tokens, passwords, or entire SecurityContext while debugging.
- [ ] After deployment, compare container registrations, security chain logs, and real integration tests.

## 17. Self-Check Questions

**Question 1.** Does DelegatingFilterProxy belong to Spring Framework or exclusively to Spring Security?  
**Answer:** Spring Framework. It is a Servlet Filter capable of delegating to a Spring bean implementing Filter.

**Question 2.** Who invokes DelegatingFilterProxy.doFilter?  
**Answer:** The Servlet Container via the Servlet FilterChain.

**Question 3.** What is the target bean usually named in Spring Security?  
**Answer:** springSecurityFilterChain.

**Question 4.** What class is the springSecurityFilterChain bean usually an instance of?  
**Answer:** FilterChainProxy, a Filter managed by Spring Security.

**Question 5.** Is SecurityFilterChain a Servlet Filter invoked directly by Tomcat?  
**Answer:** No. It describes a matcher and security filters for FilterChainProxy to use.

**Question 6.** Does FilterChainProxy run every SecurityFilterChain that matches a request?  
**Answer:** No. It selects the first matching chain in order.

**Question 7.** What is targetBeanName used for?  
**Answer:** Specifies the Filter bean name that DelegatingFilterProxy looks up in the Spring context.

**Question 8.** If targetBeanName is not configured, what name does the proxy normally use?  
**Answer:** The Servlet filter-name.

**Question 9.** Does targetFilterLifecycle default to true or false?  
**Answer:** False, because the target bean's lifecycle is typically managed by Spring.

**Question 10.** In a Boot embedded jar, do you need to manually create a DelegatingFilterProxy bean every time you write a SecurityFilterChain?  
**Answer:** No. Boot normally auto-registers the bridge.

**Question 11.** Why can a `@Component` Filter added to HttpSecurity run twice?  
**Answer:** Boot can auto-register the Filter bean at the Servlet Container level, while HttpSecurity adds it to the security chain.

**Question 12.** How do you keep a Filter bean for DI without letting Boot register it outside the security chain?  
**Answer:** Declare a FilterRegistrationBean for that bean and call setEnabled(false).

**Question 13.** Does permitAll remove the security filter chain?  
**Answer:** No. It is an authorization rule; security filters can still run.

**Question 14.** What happens if no SecurityFilterChain matches a request?  
**Answer:** Spring Security does not apply security filters to that request; the endpoint may be unprotected.

**Question 15.** Is a MockMvc test sufficient to conclude the embedded Servlet Container invoked DelegatingFilterProxy?  
**Answer:** Not automatically. Use an embedded-server integration test or inspect ServletContext registrations.

**Question 16.** Does changing spring.security.filter.order alter the order between BasicAuthenticationFilter and AuthorizationFilter?  
**Answer:** No. That setting applies at the Servlet Container level, whereas security filter order lives inside FilterChainProxy.

**Question 17.** Can an invalid Basic header on a permitAll endpoint return 401?  
**Answer:** Yes, because the authentication filter can attempt to authenticate the credentials sent by the client.

**Question 18.** When a filter blocks a request and does not call chain.doFilter, does the Controller run?  
**Answer:** No, downstream filters and the Servlet are not called in that branch.

**Question 19.** Does Spring Security WebFlux use Servlet DelegatingFilterProxy?  
**Answer:** No. WebFlux uses WebFilter/WebFilterChainProxy and SecurityWebFilterChain.

## 18. Official References

- Spring Security — Servlet Architecture, DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain, custom filters: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Framework 6.1 — DelegatingFilterProxy API: https://docs.spring.io/spring-framework/docs/6.1.9/javadoc-api/org/springframework/web/filter/DelegatingFilterProxy.html
- Spring Security — FilterChainProxy API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html
- Spring Security — HTTP Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — XML Namespace web.xml registration: https://docs.spring.io/spring-security/reference/servlet/configuration/xml-namespace.html
- Spring Boot — Embedded Web Servers and Filter registration: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Boot — Spring Security auto-configuration: https://docs.spring.io/spring-boot/reference/web/spring-security.html

# HttpFirewall: Paths With Semicolons, Encoded Slashes, and Abnormal Characters

## 1. The Problem: A Single URL Can Be Interpreted Multiple Ways

In a Spring Security application running on the **Servlet stack** (Spring MVC, Spring Boot 3.x, Spring Security 6.x), a request traverses multiple components: reverse proxy, servlet container, Spring Security filters, path matchers, and `DispatcherServlet`. They do not necessarily interpret special characters in a URL identically.

For example, a client sends:

~~~http
GET /documents/a%2Fb HTTP/1.1
Host: example.test
~~~

The sequence **%2F** represents **/** when percent-decoded. One layer may treat **a%2Fb** as *one* path segment; another layer may decode it into **a/b** and treat it as *two* segments. When **authorization** logic and **controller routing** logic do not see the same path, the system risks applying security rules to the wrong target.

Other examples:

- **/products;category=books**: **;** can be used for a path parameter or matrix variable. One layer may keep the part after the semicolon while another strips it.
- **/files/a%5Cb**: **%5C** represents a backslash; some environments may treat it as a path separator.
- **/files/%2e%2e/secret**: percent-encoded dots can form a **..** segment after decoding.
- **/files/%252F**: **%25** is an encoded percent sign; if multiple layers decode more than once, the string can turn into **%2F**, and then into **/**.
- **/files//secret**, **/files/../secret**, NUL characters, or control characters: may be normalized, stripped, or rejected at different layers.

The purpose of **HttpFirewall** is to protect Spring Security request processing from unsafe, non-standard, or ambiguous URL or HTTP request forms during matching. Do not treat how a URL looks in a browser as proof that every layer saw the exact same string.

**After this lesson, you will be able to** recognize ambiguous URLs, understand why **StrictHttpFirewall** rejects dangerous character groups by default, configure controlled exceptions, test with mock requests and real HTTP requests, and distinguish firewall errors from 401/403 errors inside `SecurityFilterChain`.

## 2. Where Does HttpFirewall Sit?

**HttpFirewall** is an interface in Spring Security Servlet. **FilterChainProxy** uses it to inspect and wrap the request/response before selecting the list of security filters. In common Spring Security configurations, the default implementation is **StrictHttpFirewall**.

~~~text
Client
  │
  ▼
Reverse proxy / gateway
  │   may block, rewrite, or normalize URL
  ▼
Servlet container (e.g., Tomcat)
  │   may reject request or interpret path
  ▼
DelegatingFilterProxy → FilterChainProxy
  │
  ├── HttpFirewall validates and creates FirewalledRequest
  │     ├── invalid request → RequestRejectedException
  │     └── valid request   → continue
  │
  └── select matching SecurityFilterChain
        ▼
      Authentication / Authorization / CSRF / ...
        ▼
      DispatcherServlet → Controller
~~~

Points to remember:

1. **The firewall runs before `SecurityFilterChain` matching.** A request rejected here never reaches **requestMatchers(...)**, a controller, or **@PreAuthorize**. Adding **permitAll()** does not make a URL blocked by `StrictHttpFirewall` valid.
2. **HttpFirewall does not equate to HTTP status 403.** When the firewall rejects a request, Spring Security may throw **RequestRejectedException**; the **RequestRejectedHandler** mechanism typically turns this into HTTP **400**. However, the servlet container or proxy may reject earlier, so actual status and logs depend on configuration.
3. **The firewall does not replace authorization.** A URL that passes the firewall must still satisfy authentication, authorization, CSRF, and input validation rules.
4. **The firewall sees the request after upstream layers.** If a proxy/container already decoded or normalized it, the firewall cannot reconstruct the original string on its own. Path policy must be consistent from edge to application.
5. **HttpFirewall belongs to the Servlet stack.** Do not take these configuration snippets and apply them directly to `SecurityWebFilterChain` in WebFlux.

### Multiple Perspectives on Paths

In the Servlet API, **getRequestURI()** typically reflects the request URI as represented in the request, whereas **getServletPath()** and **getPathInfo()** may reflect a different view shaped by the container and servlet mapping. Request matchers may use processed representations. Exact encoding, decoding, and normalization depend on container, configuration, and version, so never assume these strings are always equivalent.

The core security goal is to avoid the situation where **the path checked for permissions differs from the path executed**.

## 3. Character Groups Requiring Scrutiny

| Path Example | Why It Needs Attention | Handling Guidance |
| --- | --- | --- |
| **/items;type=book** | **;** may be a path parameter/matrix variable; layers may strip or keep what follows | `StrictHttpFirewall` rejects by default; if matrix variables are truly needed, evaluate a specific exception |
| **/docs/a%2Fb** or **/docs/a%2fb** | Encoded **/**; decoding creates a different segment boundary | Keep default rejection; prefer redesigning the URL |
| **/docs/a%5Cb** | Backslash may be treated as a slash by some layers | Keep rejected; do not treat backslash as an alternate **/** |
| **/docs/%2e%2e/private** | Dots can become **..** after decoding, affecting segment normalization | Reject non-canonical paths; never decode multiple times yourself |
| **/docs/%252F** | Multi-layer encoding risks divergent interpretations | Restrict decoding consistently; do not relax multiple firewall flags just to make it work |
| **/docs//report** or **/docs/../report** | Repeated separators and dot-segments may be normalized | Inspect container/proxy and firewall policies |
| **/docs/%00**, newlines/control characters | Can affect parsing, logging, or header/path handling | Reject; never coerce into a valid ID |
| Malformed **%** encoding, invalid characters | Parsers may return different errors | Let the appropriate layer reject; identify the exact rejecting layer when troubleshooting |

**Note on examples:** This table outlines risks and guidance. Not every URL is seen verbatim by Spring Security; a proxy or container may return an error earlier. The exact characters and methods blocked by `StrictHttpFirewall` can also vary by Spring Security version and configuration flags. Avoid writing end-to-end tests that assume a single HTTP status across all containers.

### Why Are Semicolons Dangerous?

An MVC system might want to handle a URL like:

~~~text
/cars;color=red;year=2026
~~~

Yet a security matcher might strip **;color=red;year=2026** when evaluating rules while another handler still uses it. A historical form of path parameter is **;jsessionid=...** (URL rewriting for sessions). If the system permits these syntaxes inconsistently, resource matching and access policy enforcement can diverge.

**`StrictHttpFirewall` rejects semicolons by default** to prevent that class of ambiguity. Unless matrix variables are truly required, a simpler design uses query parameters:

~~~text
GET /cars?color=red&year=2026
~~~

This keeps the path clean; query parameters must still be validated in the controller/service. Do not enable semicolons solely to make one legacy URL work without checking the entire routing and security matching pipeline.

### Why Are Encoded Slashes More Concerning Than Plain Slashes?

**/files/folder/report** has two clear segments after **/files**. By contrast, **/files/folder%2Freport** tries to embed a slash **inside an encoded segment**. If a container decodes before the router, it can become a two-segment path; otherwise, the controller may read a single segment containing **/**. Double-encoded variants make comparison even harder.

If you need to pass a **data key** containing a slash, it is usually better to:
- place that key in a query parameter and validate the value after binding;
- use a URL-path-safe opaque ID format such as UUID or URL-safe Base64;
- or design explicit multi-segment routes while enforcing authorization on the target resource.

Enable **setAllowUrlEncodedSlash(true)** only when strictly required, when you know exactly how the proxy/container/parser handle it, and when tests prove that routing and authorization share the same interpretation. Allowing it in Spring Security still **does not guarantee** Tomcat or a proxy will let that URI through.

## 4. Configuring StrictHttpFirewall in Servlet Security

The code below illustrates a **strict-default policy**: normal URLs reach the controller, while ambiguous path forms are rejected by `StrictHttpFirewall`. This is a Spring Boot 3.x application using Java 17+.

In a Gradle Spring Boot project, add the dependencies if not already present:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Create **src/main/java/com/example/firewalldemo/FirewallDemoApplication.java**:

~~~java
package com.example.firewalldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.StrictHttpFirewall;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FirewallDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FirewallDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/public/documents/**").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    WebSecurityCustomizer webSecurityCustomizer() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        // Keep strict defaults; do not open blanket exceptions.
        return web -> web.httpFirewall(firewall);
    }
}

@RestController
class DocumentController {
    @GetMapping("/public/documents/by-key")
    String byKey(@RequestParam String key) {
        return "key=" + key;
    }

    @GetMapping("/public/documents/{id}")
    String byId(@PathVariable String id) {
        return "document=" + id;
    }
}
~~~

When sending **GET /public/documents/report**, a normal request reaches the controller and receives body **document=report**. If the real key is **department/2026**, the client can call **GET /public/documents/by-key?key=department%2F2026** instead of putting **%2F** inside the path. The controller example only demonstrates binding; a real application must authorize the key/resource, restrict input, and enforce data access controls.

**Why use WebSecurityCustomizer?** The **web.httpFirewall(firewall)** setting attaches the firewall to the **WebSecurity** configuration managing `FilterChainProxy`. Some Spring Boot/Security setups can auto-detect an `HttpFirewall` bean, but the explicit declaration here makes clear which firewall is active. This is not a mechanism for opening permissions inside **authorizeHttpRequests**.

### Semicolon Exception When Matrix Variables Are Genuinely Required

In an application that **must** use matrix variables, you can create **one** configured `StrictHttpFirewall`:

~~~java
StrictHttpFirewall firewall = new StrictHttpFirewall();
firewall.setAllowSemicolon(true);
~~~

Place those two lines **instead of** the firewall instantiation inside **webSecurityCustomizer**; do not create multiple competing `HttpFirewall` instances. At the same time, audit how Spring MVC processes matrix variables, how security matchers identify endpoints, and how proxies/containers forward paths. In tests, exercise the same resource across corresponding path forms and verify authorization remains unchanged.

**Do not generalize** that enabling semicolons also enables encoded slashes or fixes all URL errors. Those two cases belong to separate rules. Exercise special caution with **setAllowUrlEncodedSlash(true)**, **setAllowBackSlash(true)**, or percent-encoding options; enabling a flag removes only one layer of rejection while other layers may still handle the URL differently.

Never switch from **StrictHttpFirewall** to a less strict firewall merely because you hit a 400 test failure. First determine the valid URL requirement and the risks of the exception.

## 5. Testing Firewall Behaviors Directly

Two complementary types of tests apply:

- **Direct `StrictHttpFirewall` unit tests**: verify the implementation's rejection rules independently of how a container transforms URIs.
- **Integration tests over real HTTP**: exercise the full proxy, container, filter, and MVC chain. Requests may be rejected before reaching `HttpFirewall`, so inspect logs to pinpoint the layer actually raising the error.

Create **src/test/java/com/example/firewalldemo/FirewallPolicyTest.java**:

~~~java
package com.example.firewalldemo;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

class FirewallPolicyTest {
    @Test
    void acceptsOrdinaryPath() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", "/public/documents/report");

        assertThatCode(() -> firewall.getFirewalledRequest(request))
                .doesNotThrowAnyException();
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "/public/documents;version=2",
            "/public/documents/a%2Fb",
            "/public/documents/a%5Cb"
    })
    void rejectsAmbiguousPathsByDefault(String uri) {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", uri);

        assertThatThrownBy(() -> firewall.getFirewalledRequest(request))
                .isInstanceOf(RequestRejectedException.class);
    }

    @Test
    void explicitSemicolonExceptionDoesNotAlsoAllowEncodedSlash() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        firewall.setAllowSemicolon(true);

        MockHttpServletRequest semicolonRequest =
                new MockHttpServletRequest(
                        "GET", "/public/documents;version=2");
        assertThatCode(
                () -> firewall.getFirewalledRequest(semicolonRequest))
                .doesNotThrowAnyException();

        MockHttpServletRequest encodedSlashRequest =
                new MockHttpServletRequest(
                        "GET", "/public/documents/a%2Fb");
        assertThatThrownBy(
                () -> firewall.getFirewalledRequest(encodedSlashRequest))
                .isInstanceOf(RequestRejectedException.class);
    }
}
~~~

Explanation:

1. Normal paths are not blocked by `StrictHttpFirewall`.
2. The three cases **;**, **%2F**, and **%5C** are verified via **RequestRejectedException** on mock requests under default configuration.
3. With **setAllowSemicolon(true)** enabled, the semicolon test passes the firewall, while **%2F** remains rejected.
4. Unit tests do not prove an endpoint is authorized or that the container accepts that URL. Neither the controller nor authorization runs in this test.

Run from the project root with the Gradle wrapper:

~~~bash
./gradlew test --tests com.example.firewalldemo.FirewallPolicyTest
~~~

On Windows, run **gradlew.bat test --tests com.example.firewalldemo.FirewallPolicyTest**. When all tests succeed, Gradle reports a successful build; do not expect HTTP output from a unit test because it only invokes Java methods.

### Observing Over HTTP and Identifying the Rejecting Layer

Start the application:

~~~bash
./gradlew bootRun
~~~

Send a valid request:

~~~bash
curl -i 'http://localhost:8080/public/documents/report'
~~~

With the controller and policy above, the expected result is HTTP **200**, body:

~~~text
document=report
~~~

Use **--path-as-is** to observe how the server handles abnormal paths instead of letting `curl` normalize dot-segments itself:

~~~bash
curl --path-as-is -i 'http://localhost:8080/public/documents;version=2'
curl --path-as-is -i 'http://localhost:8080/public/documents/a%2Fb'
curl --path-as-is -i 'http://localhost:8080/public/documents/a%5Cb'
~~~

Some requests may receive **400** from the servlet container before Spring Security; others may be rejected by **StrictHttpFirewall** after entering `FilterChainProxy`. Cross-check the HTTP response, proxy/container access logs, and Spring Security logs to locate the blocking point. In real environments, avoid logging sensitive data or Authorization headers when analyzing logs.

Do not rely on status 400 alone to assert a firewall error, nor status 403 alone to assert an authorization error. **RequestRejectedException** is a more direct signal when a request actually reaches `HttpFirewall`.

## 6. Evaluation Before Relaxing StrictHttpFirewall

Before changing any **setAllow...** flag, follow this sequence:

1. **Question the business requirement:** does the endpoint truly need semicolons or encoded slashes in the *path*? Could it use a query parameter, a URL-safe ID, or a different route structure?
2. **Reproduce the raw request:** capture the raw request target, HTTP method, context path, reverse proxy, servlet mapping, and HTTP code. Test in the real target environment because proxies/Tomcat may behave differently.
3. **Locate the rejecting layer:** distinguish proxy/container parser errors, Spring Security's **RequestRejectedException**, controller 404 mapping errors, and 401/403 authentication/authorization/CSRF errors.
4. **Compare path views:** verify how components observe the URI and path; inspect decoding, normalization, path-parameter stripping, or slash handling at each layer.
5. **Relax only the single necessary rule:** e.g., consider **setAllowSemicolon(true)** if truly using matrix variables; do not open encoded slashes, backslashes, or control characters just to silence test failures.
6. **Test both accepted and rejected cases:** standard URLs, URLs containing the permitted character, encoded variants, double-encoded variants, unusual separators, and unauthorized requests. Test against privilege escalation on real resources, not just HTTP status codes.
7. **Assess deployment configuration:** check proxy, WAF, Tomcat version, Spring Security, MVC routing, and differences between staging/production. A change in Spring Security alone may not suffice.
8. **Monitor with restraint:** track `RequestRejectedException` counts and rejected character categories; avoid logging or reflecting verbatim sensitive data from abnormal requests.

### Common Misconceptions to Avoid

| Misconception | Fact to Remember |
| --- | --- |
| "If a URL returns 400, I need to add permitAll." | The firewall/container can reject a request **before** authorization |
| "Enabling setAllowUrlEncodedSlash makes every %2F work." | Proxies/containers may still block or decode differently; MVC also has its own rules |
| "Call URLDecoder.decode multiple times to fix the path." | Repeated decoding can introduce new slashes, dot-segments, or control characters; avoid this |
| "Matrix variables are just parameters, so they can't affect security." | If the permission-checking layer and routing layer interpret them differently, risk arises |
| "Switching to DefaultHttpFirewall is always safer/easier." | Lowering firewall strictness can reopen ambiguous paths that must be controlled |
| "Blocked at the firewall means the controller is fully secured." | The controller and permission checks never ran; valid requests still need authorization |
| "Changed Spring Security, so production will behave like unit tests." | The servlet container, proxy, and deployment environment are part of the processing chain |

## 7. Practical Conclusion

For paths containing **semicolons**, **encoded slashes**, or **abnormal characters**, the main question is not how to get every URL string accepted, but whether **every layer interprets and checks the exact same resource**.

The default policy of **StrictHttpFirewall** is a safe starting point. When an exception is genuinely necessary, narrow it to the exact character type, verify routing and authorization in both the servlet container and Spring Security, and add negative tests for variants that must remain rejected. Using simple URL paths, stable IDs, and authorization on clearly identified resources is far easier to secure than loosening the firewall to accept every path encoding.

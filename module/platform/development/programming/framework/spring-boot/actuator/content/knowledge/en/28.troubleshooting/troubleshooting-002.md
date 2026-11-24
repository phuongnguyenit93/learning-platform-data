# Diagnosing 401, 403, and Write Operations Blocked by CSRF

## 1. Understanding the Three Questions Before Changing Configuration

When you can read Actuator information but cannot change log levels, the issue may lie in authentication, authorization, or cross-site request forgery protection. These three mechanisms answer three different questions:

| Mechanism | Question | Data typically checked |
| --- | --- | --- |
| Authentication | Who is calling? | Username/password, login session, or access token |
| Authorization | Is the caller allowed to perform this operation? | Authority, role, endpoint, and HTTP method |
| CSRF protection | Does the state-changing request carry valid anti-forgery proof? | CSRF token and corresponding data stored server-side or per the configured repository mechanism |

CSRF stands for Cross-Site Request Forgery: an attacker causes a victim's browser to send an unintended request while the browser may automatically attach credentials. A valid CSRF token does not prove the caller has administrative privileges; conversely, a valid password and sufficient permissions do not replace a CSRF token.

In the Actuator troubleshooting chapter, the goal is to identify the rejecting layer with evidence. This lesson uses Spring MVC/Servlet, Spring Boot 3.3.13, Spring Security 6.3.x, and Java 21. With WebFlux, the distinguishing principles still apply, but you must use reactive APIs such as SecurityWebFilterChain and ServerHttpSecurity rather than copying Servlet configuration.

## 2. Reading HTTP Status Codes as Signals, Not Final Conclusions

| Observation | Hypothesis to check | Next test |
| --- | --- | --- |
| GET on protected endpoint returns 401 | Missing or unaccepted credentials | Resend the same URL with a valid account; check AuthenticationEntryPoint |
| GET returns 403 when account is authenticated | Missing permission, wrong matcher, or another layer rejecting | Confirm the selected chain, effective authorities, and rule matching GET |
| GET succeeds, POST to same endpoint returns 403 | CSRF or separate write permission | Keep the same user, send a valid token in the same session, and retry |
| POST still returns 403 with a valid token | May lack write permission; token may also mismatch session | Check CSRF logs first, then inspect permissions and POST matcher |
| 302 redirect to login page | Entry point uses form login | Inspect Location and chain instead of looking only for 401 |
| 404, 405, 400, or 415 | Path, endpoint, method, or request payload may be wrong | Check mapping after passing through the security layer |

With the HTTP Basic setup in the lab below, a protected GET with a missing or wrong password returns 401; an authenticated user lacking permissions returns 403. HTTP Basic usually includes a WWW-Authenticate header. A custom entry point, form login configuration, proxy, or error handler can alter the response shape. Therefore, preserve status, headers, method, URL, and relevant logs. [Spring Security HTTP Basic mechanism](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html).

Do not infer that every 403 means "logged in but missing a role." In the default Servlet filter chain, CsrfFilter runs before BasicAuthenticationFilter and AuthorizationFilter. A POST missing a token can be blocked before the password is even processed, even when a wrong password or no credentials are sent. A simplified diagram of the relevant filters is:

```text
Request arrives at right host/port/path
  -> select first matching SecurityFilterChain
  -> CsrfFilter: is a token required, is the token valid?
  -> BasicAuthenticationFilter: verify Basic credentials if sent
  -> AuthorizationFilter: evaluate permissions
  -> Actuator operation
```

That ordering can be verified in [FilterOrderRegistration of Spring Security 6.3.10](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.10/config/src/main/java/org/springframework/security/config/annotation/web/builders/FilterOrderRegistration.java). The diagram omits many intermediate filters and does not cover every login mechanism. The takeaway is: changing credentials may have no effect if an earlier filter is still rejecting the request. CsrfFilter handles missing/invalid tokens via AccessDeniedHandler and halts the chain. [CsrfFilter source in Spring Security 6.3.10](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.10/web/src/main/java/org/springframework/security/web/csrf/CsrfFilter.java).

## 3. Separating Endpoint Reachability from Calling Permissions

Before editing rules, record the endpoint ID, HTTP method, actual URL, management port, and effective base paths. By default, the loggers endpoint uses /actuator/loggers; a reverse proxy or management configuration can change the externally visible URL.

In Spring Boot 3.3, an endpoint must be enabled and exposed over HTTP to have corresponding HTTP operations. Enabling exposure does not grant access permission. Conversely, permitAll does not create mappings for endpoints that are disabled or unexposed. If you declare your own SecurityFilterChain, you take responsibility for configuring security for both Actuator and the rest of the application because the corresponding auto-configured security backs off. [Actuator endpoints and security in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

A 401/403 also does not prove the URL has a valid mapping: a filter can reject the request before Spring MVC looks up mappings. Do not switch a wrong URL to permitAll and conclude you fixed the endpoint.

Common pitfalls when reading configuration:

- securityMatcher determines whether the entire chain applies; requestMatchers inside authorizeHttpRequests select rules within the chosen chain.
- When multiple chains exist, the first matching chain in order is used. A broad rule on a higher-priority chain can prevent the Actuator chain from ever being selected.
- Within the same authorization block, place specific rules before broad ones; inspect both read and write methods.
- hasRole("OPS") corresponds to the authority ROLE_OPS. hasAuthority("OPS") looks for the exact string OPS; the two forms are not equivalent. With the default prefix convention, do not write hasRole("ROLE_OPS").
- Configuring health detail visibility does not replace URL protection rules. Being able to read health does not prove permission to read or write loggers.

To avoid hardcoding /actuator when identifying endpoints, Spring Boot provides EndpointRequest. The example below combines an endpoint matcher with the HTTP method instead of applying admin permissions to every POST in the application. [Multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances).

## 4. Why Does POST Need a CSRF Token Even When GET Succeeds?

CSRF protection ignores GET, HEAD, OPTIONS, and TRACE by default; the remaining methods, including POST, PUT, PATCH, and DELETE, require verification unless exempted. This assumes operations using safe methods do not modify business state. Do not move log-level changes or application shutdown onto GET to bypass the check.

For example, viewing logger configuration is a read operation; setting configuredLevel is a write operation. Read permissions and write permissions can differ. In addition to permission checks, write operations must satisfy CSRF when enabled.

By default on Servlet, HttpSessionCsrfTokenRepository is used. Under that model, you must retain both the session containing the expected token and the token sent in the request. Sending only JSESSIONID without the token, or copying the token into a fresh cookie jar, is not enough. [Default repository configuration in Spring Security 6.3.10](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.10/config/src/main/java/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.java).

In Spring Security 6, tokens can be deferred; an arbitrary GET does not guarantee a session or token has been created. The token value exposed to the client also includes a randomized masking layer against BREACH by default. Therefore, retrieve the token through a mechanism supported by the application and use the returned headerName; do not guess the token from a cookie or decode a value based on its observed shape. The lab provides a /csrf controller to proactively fetch the token; this is an example controller, not a built-in Actuator endpoint. [CSRF for Servlet applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

## 5. Standalone Lab: Reproducing 401, Permission 403, and CSRF 403

The lab runs locally with HTTP Basic, CSRF kept enabled, and two accounts:

| Account | Sample password | Role | Permissions in lab |
| --- | --- | --- | --- |
| viewer | viewer-pass | VIEWER | Read loggers, fetch CSRF token |
| ops | ops-pass | OPS | Read and modify loggers, fetch CSRF token |

Health can be read without logging in; endpoints other than health and loggers are denied. Hardcoded accounts and {noop} are solely for local practice on loopback. Real deployments require proper identity/password management and HTTPS for HTTP Basic.

### 5.1. Creating the Project

Use JDK 21, Maven 3.6.3 or later, and Python 3 to run verification. Connectivity to Maven repositories is required if dependencies are not already cached. This is a Spring Boot project with dependencies, so run it with Maven rather than javac on a single file.

```text
actuator-security-lab/
├── pom.xml
├── verify.py
└── src/main/
    ├── java/example/lab/ActuatorSecurityLab.java
    └── resources/application.properties
```

File pom.xml:

```xml
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
    <groupId>example</groupId>
    <artifactId>actuator-security-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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
```

File src/main/resources/application.properties:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,loggers
management.endpoint.health.show-details=never
```

File src/main/java/example/lab/ActuatorSecurityLab.java:

```java
package example.lab;

import java.util.Map;
import jakarta.servlet.DispatcherType;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@RestController
public class ActuatorSecurityLab {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorSecurityLab.class, args);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer").password("{noop}viewer-pass")
                .roles("VIEWER").build(),
            User.withUsername("ops").password("{noop}ops-pass")
                .roles("OPS").build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuator(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(EndpointRequest.to("health")).permitAll()
            .requestMatchers(new AndRequestMatcher(
                EndpointRequest.to("loggers"),
                request -> "GET".equals(request.getMethod())
            )).hasAnyRole("VIEWER", "OPS")
            .requestMatchers(new AndRequestMatcher(
                EndpointRequest.to("loggers"),
                request -> "POST".equals(request.getMethod())
            )).hasRole("OPS")
            .anyRequest().denyAll()
        );
        http.httpBasic(withDefaults());
        http.csrf(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain application(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .requestMatchers(HttpMethod.GET, "/csrf").authenticated()
            .anyRequest().denyAll()
        );
        http.httpBasic(withDefaults());
        http.csrf(withDefaults());
        return http.build();
    }

    @GetMapping("/csrf")
    public Map<String, String> csrf(CsrfToken csrfToken) {
        return Map.of(
            "headerName", csrfToken.getHeaderName(),
            "token", csrfToken.getToken()
        );
    }
}
```

The first chain evaluates only Actuator. The second chain receives everything else and lets authenticated users fetch the token. Both chains use the default CSRF repository with the same HttpSession. Allowing DispatcherType.ERROR prevents the error response rendering step from being denied again by the denyAll rule; a direct REQUEST to /error is still not permitted by this rule.

Start from the project root directory:

```shell
mvn spring-boot:run
```

Keep the process running and open a second terminal in the same directory. Ensure port 8080 is used by this application and not another service.

### 5.2. Verifying with a Client That Retains Cookies and Tokens

The file verify.py uses the Python standard library, with no need to install requests or jq. Each user has a separate cookie jar. Basic credentials are sent explicitly on each request, while the cookie jar retains the CSRF session; these two serve distinct roles.

```python
import base64
import json
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE = "http://127.0.0.1:8080"
LOGGER = "/actuator/loggers/example.lab.probe"


def client():
    return build_opener(HTTPCookieProcessor(CookieJar()))


def call(opener, method, path, credentials=None, payload=None, token=None):
    headers = {}
    if credentials is not None:
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + encoded
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers[token["headerName"]] = token["token"]
    request = Request(BASE + path, data=data, headers=headers, method=method)
    try:
        response = opener.open(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.code, response.read()


def expect(label, expected, result):
    status, body = result
    assert status == expected, (label, expected, status, body)
    print(f"{label}: {status}")
    return body


anon = client()
viewer = client()
ops = client()
viewer_auth = "viewer:viewer-pass"
ops_auth = "ops:ops-pass"
change = {"configuredLevel": "DEBUG"}

expect("anonymous GET health", 200, call(anon, "GET", "/actuator/health"))
expect("anonymous GET loggers", 401, call(anon, "GET", "/actuator/loggers"))
expect("wrong password GET loggers", 401,
       call(client(), "GET", "/actuator/loggers", "ops:wrong-pass"))
expect("viewer GET loggers", 200,
       call(viewer, "GET", "/actuator/loggers", viewer_auth))
expect("anonymous POST without CSRF", 403,
       call(anon, "POST", LOGGER, payload=change))
expect("ops POST without CSRF", 403,
       call(ops, "POST", LOGGER, ops_auth, change))

status, body = call(viewer, "GET", "/csrf", viewer_auth)
assert status == 200, (status, body)
viewer_token = json.loads(body)
expect("viewer POST with valid CSRF", 403,
       call(viewer, "POST", LOGGER, viewer_auth, change, viewer_token))

status, body = call(ops, "GET", "/csrf", ops_auth)
assert status == 200, (status, body)
ops_token = json.loads(body)
invalid_token = dict(ops_token, token="invalid-token")
expect("ops POST with invalid CSRF", 403,
       call(ops, "POST", LOGGER, ops_auth, change, invalid_token))
expect("ops POST with valid CSRF", 204,
       call(ops, "POST", LOGGER, ops_auth, change, ops_token))

body = expect("ops GET changed logger", 200,
              call(ops, "GET", LOGGER, ops_auth))
assert json.loads(body)["configuredLevel"] == "DEBUG", body
print("configuredLevel=DEBUG")

expect("ops POST reset logger", 204,
       call(ops, "POST", LOGGER, ops_auth, {}, ops_token))
status, body = call(ops, "GET", LOGGER, ops_auth)
assert status == 200 and json.loads(body).get("configuredLevel") is None, body
print("configuredLevel reset")
```

Run:

```shell
python verify.py
```

Stdout with the exact configuration above once the application has started successfully:

```text
anonymous GET health: 200
anonymous GET loggers: 401
wrong password GET loggers: 401
viewer GET loggers: 200
anonymous POST without CSRF: 403
ops POST without CSRF: 403
viewer POST with valid CSRF: 403
ops POST with invalid CSRF: 403
ops POST with valid CSRF: 204
ops GET changed logger: 200
configuredLevel=DEBUG
ops POST reset logger: 204
configuredLevel reset
```

204 means the write operation succeeded with no response body, not an error because JSON is absent. The script re-reads the logger to confirm the actual effect, then sends {} to clear the custom level of the test logger. Clearing configuredLevel lets the logger fall back to its inherited level; it does not mean disabling logging. [Loggers endpoint contract for reading, updating, and resetting log levels](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

### 5.3. Deriving Causes from Controlled Tests

- GET 401 turns into 200 when valid credentials are added: evidence points to authentication, with no need to change exposure or CSRF.
- For the same ops account, POST without a token returns 403 while POST with a token in the same session returns 204: the token is the missing requirement in this lab.
- Viewer obtains a token yet POST still returns 403, whereas ops can perform the same operation: the token does not grant OPS permissions. Confirm that logs no longer report a CSRF error, then inspect authorization.
- Unauthenticated POST still returns 403: this is a concrete counterexample to the inference "403 always proves you are logged in."
- Both an invalid token and a missing token can produce 403. Looking at the HTTP code alone does not distinguish those two cases or separate them from permission errors.

Do not transfer a token fetched with viewer's cookie jar into ops's jar to compare permissions; changing both user and session/token mixes two causes in one test.

## 6. Diagnostic Procedure on a Failing Application

### Step 1: Preserve the Original Request and Identify Where the Rejection Originates

Record timestamp, method, host, port, path, status, and response headers; redact credentials before sharing. Check whether 401/403 is generated by Spring Security, a reverse proxy, an ingress, or a custom filter. If no corresponding application logs appear, check the request routing path first.

You can use the following commands to inspect read status/headers without automatically following redirects:

```shell
curl -i http://127.0.0.1:8080/actuator/loggers
curl -i -u viewer:viewer-pass http://127.0.0.1:8080/actuator/loggers
```

On Windows, use curl.exe if curl points to another command. The accounts in the commands are strictly lab data. In real systems, supply credentials appropriately so secrets are not leaked into terminal history or reports.

### Step 2: Check URL, Exposure, and the Chain Actually Selected

Verify the active profile, effective management configuration, and proxy configuration. If Actuator runs on a separate port, test the right port; do not send a CSRF token to a different service just because both URLs contain /actuator. For cookies with the Secure flag, clients must use HTTPS; host and path also affect cookie transmission.

Read SecurityFilterChain beans in order. Find the first chain matching the actual request and the first rule matching inside it. Do not draw conclusions from an inactive configuration snippet or from source code belonging to another profile.

### Step 3: Use Read Requests to Narrow Down Authentication Errors

Pick a GET on the endpoint being diagnosed, keep the URL fixed, and vary one factor: no credentials, wrong credentials, then valid credentials. If using a bearer token, check token expiration, issuer/audience, and authority mapping according to the application's resource server configuration; do not substitute Basic credentials if the chain does not support Basic.

Do not use a public GET health call as proof that an account is authenticated. Nor should you infer Basic succeeded merely because a session cookie exists: verify the actual Authentication and authorities on the server side in a test environment.

### Step 4: Verify Permissions for the Exact Failing Operation

Check actual authorities, the ROLE_ prefix, case sensitivity, endpoint matchers, and method matchers. If method security, custom filters, or proxy rules are present, they can still reject after URL rules allow the request through.

An account allowed to read metrics or loggers is not implicitly allowed to change log levels. Adjust permissions according to actual operational needs, keeping read permissions separate from state-changing permissions.

### Step 5: For Write Operations, Inspect the CSRF Lifecycle

Verify each point instead of blindly adding a header:

1. Does this chain enable CSRF, and does this request fall within its scope?
2. Which mechanism provides the token: session repository, cookie repository, or a custom approach?
3. Has the token actually been generated and exposed? A GET that does not read the token may not have done so.
4. Is the client sending back both the matching session cookie and the token under the right headerName?
5. Did the session expire, did the application restart, or did login/logout invalidate the old token?
6. With multiple instances, is the session shared or routed properly? Does the expected token exist on the instance receiving the POST?

With CookieCsrfTokenRepository, do not assume token retrieval works like the session example. Follow the configured cookie/header contract and request handler; SPA integration in Spring Security 6 has specific requirements regarding masked tokens. Avoid mixing token-reading patterns from the two repositories.

### Step 6: Temporarily Enable Logging and Read the Exact First Rejection

In a test environment, you can temporarily add the following configuration, then restart if no other log-level mechanism is available:

```properties
logging.level.org.springframework.security=TRACE
```

Observe the selected chain, invoked filters, and rejection point for that exact request. A line containing Invalid CSRF token is evidence of CSRF; to precisely distinguish a missing expected token from a mismatched token, inspect MissingCsrfTokenException or InvalidCsrfTokenException via a debugger or handler in development. The exception name depends on repository state, not merely whether the header is empty.

Do not read only the final /error dispatch error and ignore the earlier root cause. Never log passwords, Authorization headers, session cookies, or CSRF tokens for "easier debugging." Lower the log level once enough evidence is collected.

### Step 7: Re-verify Both What Should Succeed and What Must Be Blocked

After fixing, re-test at least one valid request, one under-privileged account, one missing/invalid token case if CSRF remains enabled, and one unauthenticated request. Confirm the operation actually took effect via a follow-up read; do not stop just because the status changed from 403 to 2xx.

If the error shifts to 400/415, inspect JSON, parameter names, and Content-Type. If 405, check which HTTP methods the operation supports. Passing the security layer does not guarantee the request payload is valid.

## 7. Choosing a Fix Based on the Client Model

### 7.1. When a Browser Is Involved or Credentials Are Attached Automatically

Keep CSRF protection enabled and fix token retrieval and submission alongside the proper session. This is especially necessary when using login sessions or cookies; HTTP Basic in browsers can also participate in automatic credential sending. Do not treat "stateless," "REST," "JSON," or "just tested with curl" as sufficient proof to disable CSRF. [CSRF and apps with automatically sent credentials](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.10/docs/modules/ROOT/pages/features/exploits/csrf.adoc).

CORS and CSRF address different problems. CORS governs cross-origin response access in browsers; it does not replace anti-forgery proof for write operations. Loosening CORS alone usually cannot fix a POST rejected by CsrfFilter.

### 7.2. Machine-Only Management APIs with an Appropriate Authentication Mechanism

Consider a CSRF exemption only after evaluating the authentication model: the client explicitly attaches credentials, the endpoint does not rely on credentials sent automatically by browsers, and access scope is designed for operations. For example, a token in Authorization explicitly attached by a client differs from a token stored in an automatically sent cookie.

If an architectural decision approves exempting CSRF specifically for loggers write operations, the snippet below illustrates narrowing the exception. This is an addition to the existing Actuator chain, not a standalone program, and is not applied to the lab in section 5:

```java
http.csrf(csrf -> csrf.ignoringRequestMatchers(
    new AndRequestMatcher(
        EndpointRequest.to("loggers"),
        request -> "POST".equals(request.getMethod())
    )
));
```

This exception does not bypass authentication or grant OPS permissions. Nor does it prove the lab's Basic configuration is suitable for a CSRF exemption in browser environments. After approving an exemption, test that under-privileged accounts remain blocked and the remaining application routes stay protected as intended.

Do not open permitAll for all endpoints, do not disable CSRF application-wide just to clear one POST error, and do not enable shutdown as a first test. Changing the level of a single logger lets you observe a write operation with reversible impact.

## 8. Self-Check Exercises

1. Ops sends the right password without a token and receives 403. Can you conclude the password was verified successfully? Explain using filter order.
2. Viewer has a valid token in the same session yet still cannot change the log level. Which requirement is missing in the lab?
3. You fetch a token using jar A and send POST using jar B. Why might adding the exact header still fail to fix the error?
4. After adding the token, POST returns 415. Should you inspect the request payload or keep changing roles?
5. A chain with a broad matcher is placed before the Actuator chain. Why might editing rules in the Actuator chain have no effect?

Reference guide: question 1 lacks sufficient evidence because CsrfFilter can block before BasicAuthenticationFilter; question 2 lacks ROLE_OPS; question 3 lacks the session corresponding to the expected token; question 4 checks Content-Type/payload contract once security is confirmed to pass; question 5 the first matching chain already handled the request.

When concluding a diagnosis, you should be able to describe which request was rejected, which layer rejected it, what evidence confirms it, and which test shows the fix both permits the intended operation and preserves access boundaries.

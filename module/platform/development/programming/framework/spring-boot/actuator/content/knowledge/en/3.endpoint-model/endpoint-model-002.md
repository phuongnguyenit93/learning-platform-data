# Distinguishing Enabled, Exposed, and Authorized Endpoints

## 1. An Endpoint Can Be "Available" in Multiple Senses

You add Actuator, see `info.enabled=true` in configuration, yet calling `/actuator/info` returns no data. Then you add `info` to the exposure list, and the request returns `401`. When you sign in with another account, it returns `403`.

These three results are not necessarily contradictory. You are encountering different decision layers:

| Question | Corresponding concept |
| --- | --- |
| Is the endpoint capability enabled by configuration? | Enabled |
| Is the endpoint exposed over HTTP or JMX? | Exposed |
| Does the request from this identity satisfy the access policy? | Authorized |

**Enabled does not mean exposed; exposed does not mean everyone is granted access.**

This lesson uses Spring Boot **3.3.13**, Java **21**, and a Servlet application. The example verifies the three layers using the standard `info` endpoint. There is no need to create a fake business API just to observe data.

The `enabled` properties in this lesson belong to the Boot 3.3 contract. When moving to another major or minor version, consult that version's documentation rather than mixing configuration models.

## 2. Enabled: Decision About Endpoint Capability

### 2.1. Property for a Specific Endpoint

In Boot 3.3:

~~~yaml
management:
  endpoint:
    info:
      enabled: true
~~~

This snippet states that the `info` endpoint is enabled by configuration. Setting `false` disables the corresponding endpoint in the auto-configuration under consideration.

If you want endpoints disabled by default and then pick individual ones:

~~~yaml
management:
  endpoints:
    enabled-by-default: false
  endpoint:
    health:
      enabled: true
~~~

This is a separate illustrative configuration for the enable/disable mechanism, not the configuration file for the hands-on exercise below. [Spring Boot 3.3: enabling endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling).

Pay attention to the two names:

- `management.endpoint.info.enabled` uses singular `endpoint` for a specific endpoint.
- `management.endpoints.enabled-by-default` uses plural `endpoints` for the global policy.

Misspelling a property name can cause you to reason based on a value that was never applied.

### 2.2. enabled=true Does Not Guarantee a Bean Always Exists

For built-in endpoints such as `info`, auto-configuration conditions also apply. Boot evaluates endpoint availability, which includes both enabled state and a suitable exposure technology.

Therefore, you should not use this reasoning:

~~~text
Wrote enabled=true
    -> definitely have an InfoEndpoint bean
    -> definitely have an HTTP URL
~~~

`InfoEndpointAutoConfiguration` uses the `@ConditionalOnAvailableEndpoint` condition; creating the component still depends on that condition. [InfoEndpoint auto-configuration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/info/InfoEndpointAutoConfiguration.html), [ConditionalOnAvailableEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html).

The lesson's example intentionally keeps `info` exposed over JMX in one run. This clearly demonstrates the case where **the bean exists, yet HTTP is not exposed**.

## 3. Exposed: Always Ask "Over Which Mechanism?"

### 3.1. Exposing Over HTTP

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

This selects the endpoint IDs exposed over the web. With the default path in the sample application, `info` can be mapped to `/actuator/info`.

If both `include` and `exclude` are present:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
        exclude: info
~~~

Then `info` is still excluded from HTTP exposure, because `exclude` takes precedence in this decision. [Exposure configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

Adding `info` to `include` does not re-enable an endpoint that has been disabled. Nor does it create the dependencies or beans that the endpoint requires.

### 3.2. Exposing Over JMX Is a Separate Decision

~~~yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include: info
~~~

This configuration chooses to expose `info` over JMX. It does not automatically add `info` to the HTTP list.

Under the lesson's default naming/domain configuration, the ObjectName of the `info` MBean is:

~~~text
org.springframework.boot:type=Endpoint,name=Info
~~~

Enabling JMX support, registering MBeans, and configuring a remote JMX connection are separate concerns. This lesson only verifies via `MBeanServer` in-process and does not open a remote JMX connector. [Actuator over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### 3.3. A Table Listing Each Technology Is Clearer Than the Single Word "exposed"

Instead of writing:

~~~text
info: exposed
~~~

Describe it specifically:

~~~text
info: enabled
HTTP: not exposed
JMX: exposed
~~~

Writing it this way avoids concluding "the URL cannot be called, so the endpoint is disabled."

## 4. Authorized: Belongs to the Request and Identity

An endpoint exposed over HTTP may still require:

- Proving identity — authentication.
- Having the right permission or role — authorization.
- Traversing the designed network path and management mechanism.

In the example:

| Identity | Status | Access to exposed info |
| --- | --- | --- |
| No credentials sent | Unauthenticated | Not allowed to read |
| `reader` | Has role `READER` | Insufficient permission to read |
| `operator` | Has role `OPS` | Allowed to read |

Signing in successfully does not mean having every permission. Conversely, a public endpoint may not require signing in.

Spring Security allows defining per-request rules. When configuring `SecurityFilterChain` yourself, you must define the complete policy for your application's scope. [Authorizing HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).

This lesson uses HTTP Basic so the statuses are clearly visible. This is an in-memory user model for practicing on loopback; when used over a network in a deployed environment, credentials must travel over an appropriately protected transport.

## 5. Three Layers Are a Reasoning Model, Not Physical Processing Order

You can use the following logical model to analyze a request:

~~~text
Is the endpoint enabled?
    + component creation conditions met?
    + exposed over the right technology?
    + matching URL/port/method?
    + request authorized?
    -> only then can the endpoint operation execute
~~~

Do not turn this into a claim that the server always checks strictly from top to bottom. In a Servlet application, security filters can run before Spring MVC searches for the final handler.

Important consequence:

> A 401 status code is not enough to conclude the endpoint exists.

A path with no handler can still be blocked by a catch-all rule requiring authentication. Only after using valid credentials do you see `404`.

Similarly, `404` alone does not tell you whether the endpoint is disabled, unexposed, on the wrong port, or at the wrong path. You need to combine configuration and other evidence.

This model also does not guarantee that "authorized" always returns `200`. For example, `health` can be called successfully yet report an unhealthy condition with code `503`. Permission to execute and the outcome of the operation are two different matters.

## 6. Hands-On Project: Observing info on Both HTTP and JMX

### 6.1. Structure and Goals

~~~text
endpoint-gates/
├── pom.xml
└── src/main/
    ├── java/example/endpointgates/
    │   ├── EndpointGatesApplication.java
    │   └── DemoSecurityConfiguration.java
    └── resources/application.yml
~~~

Requires JDK 21, Maven, and network access for initial dependency downloads.

The application will:

1. Provide a fixed, non-sensitive piece of `info` data.
2. Print the results of checking the `info` bean and JMX MBean at startup.
3. Allow `health` to be read publicly.
4. Require the `OPS` role for other exposed Actuator endpoints.
5. Reuse the same JAR across four configuration runs.

### 6.2. pom.xml

~~~xml
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
    <artifactId>endpoint-gates</artifactId>
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
~~~

### 6.3. Startup Class and In-Process Checks

File `src/main/java/example/endpointgates/EndpointGatesApplication.java`:

~~~java
package example.endpointgates;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.actuate.info.InfoEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EndpointGatesApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointGatesApplication.class, args);
    }

    @Bean
    InfoContributor lessonInfo() {
        return builder -> builder.withDetail("lesson", "endpoint-gates");
    }

    @Bean
    ApplicationRunner inspectInfo(ApplicationContext context, MBeanServer mbeans) {
        return args -> {
            ObjectName name =
                new ObjectName("org.springframework.boot:type=Endpoint,name=Info");
            boolean registered = mbeans.isRegistered(name);
            boolean readable = registered
                && mbeans.invoke(name, "info", new Object[0], new String[0]) != null;

            System.out.println("info.bean=" +
                !context.getBeansOfType(InfoEndpoint.class).isEmpty());
            System.out.println("info.jmx.registered=" + registered);
            System.out.println("info.jmx.read=" + readable);
        };
    }
}
~~~

`InfoContributor` contributes the `lesson` data for the `info` endpoint. It is not a controller and does not expose a URL by itself.

`InfoEndpoint` is a standard endpoint with an `info()` read operation. [InfoEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoEndpoint.html).

The runner checks three pieces of evidence:

- `info.bean`: whether an `InfoEndpoint` bean exists in the context.
- `info.jmx.registered`: whether the `info` MBean has been registered.
- `info.jmx.read`: whether a direct read call through `MBeanServer` returns a result.

This is a JMX check from code running **in the same process**. It does not use HTTP credentials and does not prove that someone outside the machine has remote JMX access.

### 6.4. Configuring Two Accounts and HTTP Permissions

File `src/main/java/example/endpointgates/DemoSecurityConfiguration.java`:

~~~java
package example.endpointgates;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class DemoSecurityConfiguration {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${DEMO_READER_PASSWORD}") String readerPassword,
            @Value("${DEMO_OPERATOR_PASSWORD}") String operatorPassword) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode(readerPassword))
                .roles("READER")
                .build(),
            User.withUsername("operator")
                .password(encoder.encode(operatorPassword))
                .roles("OPS")
                .build()
        );
    }

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(requests -> requests
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
                .anyRequest().authenticated())
            .httpBasic(withDefaults());
        return http.build();
    }
}
~~~

Both passwords are read from environment variables. The program encodes them for the in-memory user store; neither YAML nor source code contains practice passwords.

The rules are ordered:

1. Allow internal error dispatch handling.
2. Allow reading `health`.
3. For other Actuator endpoints matched by the matcher, require the `OPS` role.
4. All remaining requests must be authenticated.

`EndpointRequest` identifies Actuator locations so you do not have to treat every path with a matching prefix as the same kind of resource. [EndpointRequest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

`roles("OPS")` creates an authority with the corresponding role prefix; `hasRole("OPS")` checks that role. Having the username `operator` alone is not enough: the assigned authority determines the authorization result.

The line `dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()` allows internal error dispatches to preserve error reporting behavior. It is not a rule that makes all initial requests public: initial requests still go through the subsequent rules.

`anyRequest().authenticated()` is why a nonexistent URL in the sample can still return `401` when no credentials are sent. After valid authentication, the request proceeds to routing and receives `404`.

Because the lesson declares its own security chain, it does not rely on Boot continuing to retain all default Actuator rules. HTTP Basic is also explicitly enabled via `httpBasic(withDefaults())`. [HTTP Basic in Spring Security](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html).

### 6.5. Initial Configuration

File `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: endpoint-gates
  jmx:
    enabled: true

server:
  address: 127.0.0.1
  port: 18090

management:
  endpoint:
    info:
      enabled: true
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health
    jmx:
      exposure:
        include: info
~~~

In the base configuration:

- `info` is enabled.
- Web exposes only `health`.
- JMX exposes `info`.
- HTTP listens only on `127.0.0.1:18090`.

This provides the baseline to verify that an endpoint can exist and work over JMX while having no corresponding HTTP URL.

Do not add a wildcard to the exposure list to "fix" every error. Each run below changes only the properties needed for that test.

## 7. Build and Prepare Practice Accounts

### 7.1. Build the JAR

In the directory containing `pom.xml`:

~~~powershell
java -version
mvn -v
mvn clean package
~~~

Make sure Maven uses JDK 21. The JAR used for the runs is:

~~~text
target/endpoint-gates-1.0.0.jar
~~~

Maven compiles the two Java files and packages the required libraries. Do not run a single file with `javac` alone without the Spring Boot/Security classpath.

### 7.2. Set Passwords in Terminal A

The following commands are for PowerShell:

~~~powershell
$readerSecret = Read-Host "Practice password for reader" -AsSecureString
$operatorSecret = Read-Host "Practice password for operator" -AsSecureString

$env:DEMO_READER_PASSWORD = [System.Net.NetworkCredential]::new("", $readerSecret).Password
$env:DEMO_OPERATOR_PASSWORD = [System.Net.NetworkCredential]::new("", $operatorSecret).Password
~~~

Do not print these variables to check them. These are practice secrets; do not reuse passwords from other accounts you use.

The values must be present in the terminal that launches Java. In Terminal B, commands using `curl.exe --user reader` or `--user operator` will prompt interactively for the password. Because the password is not written after the username in the command, it is not stored directly in command history.

On Linux or macOS you can use `curl`; the variable input commands above use PowerShell syntax.

## 8. Run A: Disabled Even Though Present in the Exposure List

Use Terminal A:

~~~powershell
java -jar target/endpoint-gates-1.0.0.jar --management.endpoint.info.enabled=false "--management.endpoints.web.exposure.include=health,info"
~~~

The runtime arguments override the corresponding YAML values for this run.

After startup, the three lines printed by the runner are:

~~~text
info.bean=false
info.jmx.registered=false
info.jmx.read=false
~~~

Other Boot log lines may still appear; the three lines above are the fixed output generated by the lesson's verification code.

In Terminal B, read `info` using the `operator` account:

~~~powershell
curl.exe --silent --show-error --user operator --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18090/actuator/info
~~~

Enter the correct `operator` password. The HTTP code is:

~~~text
404
~~~

Conclusion from **both configuration and evidence**: listing `info` in web and JMX exposure does not override `enabled=false` in the auto-configured endpoint under test.

Do not conclude solely from `404` that the endpoint must be disabled. The next run will produce the same HTTP code with a different bean state.

Stop the application with `Ctrl+C` before moving to the next run.

## 9. Run B: Enabled and Usable Over JMX, Not Exposed Over HTTP

Run with the exact base configuration:

~~~powershell
java -jar target/endpoint-gates-1.0.0.jar
~~~

Three result lines:

~~~text
info.bean=true
info.jmx.registered=true
info.jmx.read=true
~~~

Call `info` again using `operator`:

~~~powershell
curl.exe --silent --show-error --user operator --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18090/actuator/info
~~~

The result is still:

~~~text
404
~~~

But this time, `info` exists and the in-process JMX call read a result. What is missing is **HTTP exposure for info**.

Even though `operator` has the `OPS` role, that permission does not create a missing HTTP route.

In the same run, try a request with no credentials:

~~~powershell
curl.exe --silent --show-error --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18090/actuator/info
~~~

Result under the sample's policy:

~~~text
401
~~~

This is concrete evidence that `401` can appear before the caller sees the `404` from routing. It does not prove `info` is exposed over the web.

`NUL` discards the response body on Windows. On Linux/macOS, use `/dev/null` in that position.

Stop the application before moving to the next run.

## 10. Run C: Expose Over HTTP and Distinguish 401, 403, and 200

### 10.1. Expose info Over Web

Terminal A:

~~~powershell
java -jar target/endpoint-gates-1.0.0.jar "--management.endpoints.web.exposure.include=health,info"
~~~

The three result lines are still:

~~~text
info.bean=true
info.jmx.registered=true
info.jmx.read=true
~~~

The difference from Run B is that the HTTP exposure layer now includes `info`.

### 10.2. No Credentials Sent

~~~powershell
curl.exe --silent --show-error --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18090/actuator/info
~~~

Result:

~~~text
401
~~~

Under the sample's HTTP Basic mechanism, this request has no authenticated identity satisfying the policy. A wrong password is also an authentication failure, not a way to prove whether that user has a role.

### 10.3. reader Is Authenticated but Lacks the Role

~~~powershell
curl.exe --silent --show-error --user reader --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18090/actuator/info
~~~

After entering the correct `reader` password:

~~~text
403
~~~

`reader` has a valid account but only has the `READER` role. The rule for exposed endpoints requires `OPS`.

Changing exposure does not turn `READER` into `OPS`. This is an authorization decision, not enabling/disabling the endpoint.

### 10.4. operator Has the Appropriate Role

Read the content:

~~~powershell
curl.exe --silent --show-error --user operator --header "Accept: application/json" http://127.0.0.1:18090/actuator/info
~~~

JSON content:

~~~json
{"lesson":"endpoint-gates"}
~~~

Check the HTTP status code separately using the `--output NUL --write-out` command from previous runs with `operator`; the result is `200`.

The three identities are calling **the same URL of the same process with the same exposure configuration**. The difference in outcome lies in the request and permissions.

### 10.5. Health Is Permitted by Its Own Rule

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:18090/actuator/health
~~~

When the default checks pass:

~~~json
{"status":"UP"}
~~~

Public `health` does not make `info` public. A rule for one endpoint is not a blanket permission for every other endpoint.

Stop the application before moving to the next run.

## 11. Run D: exclude Removes info from HTTP Even When Included

Terminal A:

~~~powershell
java -jar target/endpoint-gates-1.0.0.jar "--management.endpoints.web.exposure.include=health,info" "--management.endpoints.web.exposure.exclude=info"
~~~

Three lines:

~~~text
info.bean=true
info.jmx.registered=true
info.jmx.read=true
~~~

Reading `info` with `operator` over HTTP returns `404`. JMX still works because you only excluded `info` from **web** exposure, without changing the sample's JMX list.

Results table for the entire test series:

| Run | info bean | In-process JMX read | HTTP unauthenticated | HTTP valid reader | HTTP valid operator |
| --- | --- | --- | --- | --- | --- |
| A — enabled=false | No | No | 401 | 404 | 404 |
| B — JMX only | Yes | Yes | 401 | 404 | 404 |
| C — HTTP included | Yes | Yes | 401 | 403 | 200 |
| D — web exclude info | Yes | Yes | 401 | 404 | 404 |

The codes in the table belong to **the exact security and routing rules of the sample**. Do not treat them as rigid rules for every application with proxies, gateways, or different error policies.

The key takeaway is that A and B can look identical over HTTP yet differ in endpoint state; B and C can look identical in bean/JMX yet differ in HTTP exposure; in C, the identity alone changes the outcome.

## 12. Diagnosing at the Right Layer

### When You Cannot Connect

Check the process, address, and port first. Without an HTTP response, there is no basis to blame roles or the exposure list.

Separate connection errors from an HTTP status code returned by the application. A management port different from the application port can also cause you to call the wrong place.

### When You Get 404

Verify the endpoint ID, prefix, port, and exposure technology. Then check `enabled`, `include`/`exclude`, and auto-configuration conditions.

Do not change security to `permitAll` just to find an endpoint that is not exposed. Allowing a route does not create a missing handler.

### When You Get 401

Check the authentication mechanism and credentials sent. Still keep asking whether the endpoint is actually exposed: a fallback security rule can block even a nonexistent path as in Run B.

### When You Get 403

Check the identity's permissions and the request conditions. In Run C of this lesson, the cause is lacking the `OPS` role.

In other situations, `403` can also involve other protections. For instance, a `POST` request may be blocked by CSRF. This lesson uses only `GET` and does not disable CSRF to "fix" every `403`. [Spring Security: CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

### When Access Succeeds but Data Is Missing

Distinguish permission to call an endpoint from the content the endpoint is configured to return. For example, permission to call `health` does not make `health` show details; `info` needs contributors providing meaningful data.

Reducing response detail is also not equivalent to disabling the endpoint or blocking everyone from calling it.

## 13. Confusions to Avoid

| Confusion | More accurate reasoning |
| --- | --- |
| `enabled=true` means there is a URL | Must check component conditions and HTTP exposure |
| Listed in `include` means public | Still depends on authentication and authorization decisions |
| A privileged account can call a disabled endpoint | Permissions do not recreate a disabled capability |
| Removing from web exposure disables the whole endpoint | The endpoint may still be exposed over JMX |
| `permitAll` fixes every 404 | Granting access does not create missing routes or beans |
| 401 proves the endpoint exists | A general policy can block before handler lookup |
| 403 always means wrong password | Must distinguish authentication, roles, and other protections |
| Reading health means reading all Actuator endpoints | Each request group can have its own rules |

In a real system, describe permissions by **operation and identity**. A management endpoint with a write operation should not be treated the same as a read operation just because both belong to Actuator.

## 14. Self-Check with Small Changes

**Exercise 1 — Remove info from JMX in Run B.**

Keep web with only `health` and remove JMX exposure for `info`. With Boot's auto-configured endpoint in the sample, check the bean again instead of holding onto the assumption that `enabled=true` always creates the bean.

The goal is to understand the "available" condition, not just memorize the `enabled` property name.

**Exercise 2 — Keep Run C's configuration but change reader's role.**

If `reader` is assigned `OPS` in the user configuration code and rebuilt, predict `reader`'s HTTP result. You need to change the permission, not the exposure.

**Exercise 3 — Use operator in Run A.**

Explain why `operator` still receives `404` despite having the role required for `info` in Run C. A disabled endpoint and an unauthorized request are two different situations.

**Exercise 4 — Write a bug report covering all three layers.**

Instead of writing "Actuator is not working," record which endpoint, which technology, the checked `enabled`/exposure states, the test identity used, and the response received. Record only necessary data; do not include passwords in the report.

After stopping the application, you can clear the practice password variables from the terminal:

~~~powershell
Remove-Item Env:DEMO_READER_PASSWORD, Env:DEMO_OPERATOR_PASSWORD -ErrorAction SilentlyContinue
Remove-Variable readerSecret, operatorSecret -ErrorAction SilentlyContinue
~~~

What to retain are three independent questions: **is the endpoint enabled by configuration, where is it exposed, and which requests are authorized to perform the operation?** When you can analyze all three, you will know which layer of configuration needs adjustment.

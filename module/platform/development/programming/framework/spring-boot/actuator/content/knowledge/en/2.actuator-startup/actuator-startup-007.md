# Separating Management Configuration Across Development, Testing, and Production Environments

## 1. Why not use the same Actuator configuration everywhere?

When developing on a personal machine, you may need to view the list of metrics and details of a check. When running tests, you need a stable configuration to verify behavior. When deploying to production, every exposed management capability must have a clear consumer and purpose.

If you copy a broad configuration file verbatim from a development machine into production, the application may expose information that monitoring systems do not need. Conversely, if you manually edit the same file before each deployment, it is hard to know which configuration the running instance actually picked up.

The proper way to organize this is:

~~~text
Same source code and same JAR
        +
Shared configuration
        +
Per-environment configuration
        +
Values supplied at runtime
        =
Actual process configuration
~~~

The goal of this lesson is not to create three different programs. You will build one Spring Boot application and use three **Spring profiles** to select the Actuator policy.

The example uses **Spring Boot 3.3.13**, **Java 21**, and **Maven**. All ports bind to loopback for local testing on the same machine; the configuration named `prod` in this lesson is a policy-verification sample that must be paired with real management access controls when deployed.

## 2. Define the policy before writing YAML

Do not start by opening all endpoints and then trying to close some down. First, answer:

- What kind of information does this environment need to read?
- What may unauthenticated users view?
- Do authenticated users need to view health details?
- Which port will inspection tools call?
- Where are credentials supplied from?
- If an environment is accidentally omitted, what will the default scope be?

In this lesson, choose the following policy:

| Property | No profile selected | `dev` | `test` | `prod` |
| --- | --- | --- | --- | --- |
| Application port | 18080 | 18080 | 18081 | 18082 |
| Management HTTP port | Uses application port | Uses application port | Uses application port | 19082 |
| Endpoints exposed over web | health | health, info, metrics | health, info | health |
| Health for unauthenticated users | Status only | Status only | Status only | Status only |
| Health details for valid accounts | No | Yes | No | No |
| Actuator exposure over JMX | No | No | No | No |
| Credential source | External to config files | External to config files | External to config files | External to config files |

This is an example decision, not a mandatory endpoint set for every system. A production setup may need to export metrics to a collection system; when that requirement exists, add the corresponding registry, endpoint, or export mechanism and verify it separately.

The table distinguishes **exposed endpoints** from **permission to use endpoints**. These two aspects must be considered together.

## 3. Configuration layers with distinct responsibilities

### 3.1. Enabled endpoint

An endpoint must have its required components and be enabled before it can be used. For example, an endpoint requiring an additional library will not appear merely by writing its name in YAML.

### 3.2. Endpoints exposed over web

`management.endpoints.web.exposure.include` selects the identifiers exposed over HTTP. This list does not grant caller permissions by itself. If `exclude` is present, evaluate that list as well. [Endpoints and exposure documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

### 3.3. Access permissions and detail level

Blocking access to a path and reducing returned data are two different things. In the sample:

- Health can be read without logging in.
- Other exposed management endpoints require authentication.
- Only `dev` lets authenticated users view additional health details.
- `test` and `prod` still return compact health even for valid accounts.

`show-details: never` does not replace access policy. It only controls how much health data is disclosed.

### 3.4. Address and port

A separate management port helps organize access paths and checks. It does not authenticate callers on its own. Network, port, and application rules must align with operational tools.

With a separate management port, Boot provides `management.server.address` to select the listening address. [ManagementServerProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementServerProperties.html).

## 4. Organizing configuration by Spring profile

Use four files:

~~~text
application.yml
application-dev.yml
application-test.yml
application-prod.yml
~~~

`application.yml` holds the shared part. Profile-suffixed files provide environment-specific values. When `dev` is selected, both the shared configuration and the `dev` section participate; the profile-specific section can override shared values. [Spring Boot: Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html).

The three names `dev`, `test`, and `prod` are project conventions. Boot does not auto-detect "this is production" from the host and pick `prod` for you.

Do not set `spring.profiles.active=dev` as the default in the sample's shared configuration. The runtime environment must explicitly select the profile. When none is selected, the sample exposes only health per the shared section.

Also do not put `spring.profiles.active` inside `application-prod.yml` itself to "self-activate" that file. Profile selection must happen from an appropriate configuration source, not depend on a file loaded only after the profile has already been chosen.

### One primary environment per run

This lesson uses exactly one of the three profiles per run. Avoid running `dev,prod` simultaneously and assuming Boot will automatically pick the stricter policy.

When multiple profiles set the same property, the result depends on loading rules and precedence. There is no universal rule that "production always wins". In a system with multiple functional profiles, clearly define allowed combinations.

## 5. Complete example: one JAR, three policies

### 5.1. Project structure

~~~text
management-profiles/
├── pom.xml
└── src/main/
    ├── java/example/managementprofiles/ManagementProfilesApplication.java
    └── resources/
        ├── application.yml
        ├── application-dev.yml
        ├── application-test.yml
        └── application-prod.yml
~~~

You need JDK 21, Maven, and network access to download libraries on the first build.

### 5.2. pom.xml

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
    <artifactId>management-profiles</artifactId>
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

The Security starter is added so the sample has an authentication mechanism when reading endpoints beyond health. The example does not declare a custom `SecurityFilterChain`, so it uses Boot 3.3's auto-configured policy.

When Spring Security is present and no custom security chain is defined, Boot protects actuator endpoints other than health. If a real application already has a custom security filter chain, inspect that application's own rules rather than assuming the default policy still holds. [Securing Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

### 5.3. Startup class

File `src/main/java/example/managementprofiles/ManagementProfilesApplication.java`:

~~~java
package example.managementprofiles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManagementProfilesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManagementProfilesApplication.class, args);
    }
}
~~~

There is no Java code branching on `dev`, `test`, or `prod`. The differences in this lesson lie in the configuration loaded at runtime.

### 5.4. Shared configuration: application.yml

~~~yaml
spring:
  application:
    name: management-profiles
  jmx:
    enabled: false
  security:
    user:
      name: ${ACTUATOR_USER}
      password: ${ACTUATOR_PASSWORD}

server:
  address: 127.0.0.1
  port: 18080

management:
  endpoints:
    web:
      exposure:
        include:
          - health
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      show-details: never
      show-components: never
  info:
    env:
      enabled: false
~~~

The shared section intentionally selects a narrow scope:

- Only exposes health over web.
- Excludes health details and component names from responses.
- Does not use `info.*` sources in the info response under the shared configuration.
- Does not expose Actuator over JMX in this lesson.
- Reads credentials from two environment variables.

`ACTUATOR_USER` and `ACTUATOR_PASSWORD` are variable names chosen by the sample. They are referenced from two Spring Security properties, not special variables Boot magically knows without mapping configuration.

The two values have no defaults in YAML. The operator must supply them before starting. Do not use a hardcoded development password as a fallback that production might accidentally inherit.

`spring.jmx.enabled` relates to Spring-provided JMX support; `management.endpoints.jmx.exposure` is Actuator's JMX exposure scope. The lesson explicitly sets both to show intent not to use this management channel. [Actuator over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### 5.5. Development environment: application-dev.yml

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
  info:
    env:
      enabled: true

info:
  application:
    environment: dev
~~~

`dev` opens `info` and `metrics` as well for diagnostic practice. Health details are returned only to callers deemed authorized to view details; the sample sets no dedicated role list for health, so an authenticated account satisfies that default condition.

`show-details` and `show-components` are configured together to avoid confusion between detail content and the appearance of the component list.

The `info.application.environment` section is only a label supplied by the lesson itself. It helps verify which configuration file is in effect. Do not treat a `"dev"` string in JSON as sole proof of which profiles are actually active.

`management.info.env.enabled=true` enables the info contributor from properties starting with `info.`. It differs from exposing the `env` endpoint. [EnvironmentInfoContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.html).

### 5.6. Testing environment: application-test.yml

~~~yaml
server:
  port: 18081

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
  endpoint:
    health:
      show-details: never
      show-components: never
  info:
    env:
      enabled: true

info:
  application:
    environment: test
~~~

`test` includes `info` to identify the run, but does not expose `metrics` under the lesson's policy. Health stays compact even when logged in.

A dedicated port makes it easy to distinguish test runs from development runs when inspecting URLs. What matters is still verifying configuration, not the number `18081` itself.

The filename `application-test.yml` does not cause `mvn test` to automatically activate the Spring `test` profile. In tests that create a Spring context, you can choose a profile with a mechanism like `@ActiveProfiles("test")`. Running a JAR in a testing environment also requires selecting the profile. [Spring TestContext: active profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html).

### 5.7. Production environment: application-prod.yml

~~~yaml
server:
  port: 18082

management:
  server:
    address: 127.0.0.1
    port: 19082
  endpoints:
    web:
      exposure:
        include:
          - health
  endpoint:
    health:
      show-details: never
      show-components: never
  info:
    env:
      enabled: false
~~~

In the sample, the application uses port `18082`, while Actuator HTTP moves to `19082`. Health check tools must call the right management port.

Both the application and management addresses are loopback in this lesson for local verification. In a real deployment, select the listening address and access routes based on where agents, proxies, or monitoring tools reside.

Merely changing the port does not turn HTTP Basic into an encrypted credential transport mechanism. If using HTTP Basic over a network in deployment, protect the transport with TLS and apply an appropriate management mechanism. The single in-memory account in the sample is for illustration; production identity design belongs to the real system. [Spring Boot and Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html).

Each environment's `include` list is written out completely so the reader sees the intended policy. Do not just add a `metrics` line in a profile file and assume other names will automatically be appended as intended.

## 6. Build once and supply credentials externally

### 6.1. Build the JAR

Open PowerShell in the directory containing `pom.xml`:

~~~powershell
java -version
mvn -v
mvn clean package
~~~

Ensure the Java used by Maven is JDK 21. A successful build creates:

~~~text
target/management-profiles-1.0.0.jar
~~~

Maven handles classpath, compilation, and packaging. The example requires Boot/Actuator/Security libraries, so a `javac` command on the source file without classpath will not suffice.

From here on, use **that same JAR** for all runs. There is no need to rebuild just to change profiles.

### 6.2. Supply the two environment variables in the launch terminal

In Terminal A:

~~~powershell
$env:ACTUATOR_USER = Read-Host "Management username for the lab"
$enteredSecret = Read-Host "Password for the lab" -AsSecureString
$env:ACTUATOR_PASSWORD = [System.Net.NetworkCredential]::new("", $enteredSecret).Password
~~~

Choose a dedicated account for the lab. Do not print the two variables to the terminal to "check if they are set".

Passing environment variables into the process does not erase the secret from memory; the purpose here is to avoid writing passwords into source code or YAML files. In deployment environments, use the infrastructure-supported secrets delivery mechanism and restrict access to that source.

Another terminal does not inherit variables just set in Terminal A. For cURL commands requiring login in Terminal B, enter the **username** again:

~~~powershell
$operatorName = Read-Host "Username set in Terminal A"
~~~

The `curl.exe --user "$operatorName"` commands below let cURL prompt interactively for the password. Do not embed the password into commands saved in shell history.

## 7. Run and verify each profile

The commands below use Windows PowerShell. `curl.exe` invokes the cURL program, avoiding the `curl` alias. On other operating systems, use the corresponding tool.

Before switching runs, stop the previous process in Terminal A with `Ctrl+C`. Wait for the new application to finish starting before testing.

### 7.1. Development: dev

Terminal A:

~~~powershell
java -jar target/management-profiles-1.0.0.jar --spring.profiles.active=dev
~~~

In the startup log, confirm the active profiles include `dev`. Log lines contain timestamps and PIDs, so they are not fixed stdout to copy verbatim as expected output.

In Terminal B, unauthenticated health:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:18080/actuator/health
~~~

When existing checks pass:

~~~json
{"status":"UP"}
~~~

Read health with a valid account:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" http://127.0.0.1:18080/actuator/health
~~~

The response additionally includes `components` and corresponding health info. Values such as disk space vary by machine, so do not match the entire JSON against fixed numbers.

Check info with a valid account:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" http://127.0.0.1:18080/actuator/info
~~~

JSON body for this exact sample:

~~~json
{"application":{"environment":"dev"}}
~~~

Check the HTTP status code of metrics when authenticated:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18080/actuator/metrics
~~~

Result:

~~~text
200
~~~

If calling `info` or `metrics` unauthenticated, with an `Accept: application/json` request in the sample, the result is `401`. An endpoint being in the exposure scope does not mean any caller is allowed to read it.

### 7.2. Testing: test

Terminal A:

~~~powershell
java -jar target/management-profiles-1.0.0.jar --spring.profiles.active=test
~~~

Unauthenticated health:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:18081/actuator/health
~~~

Result when healthy:

~~~json
{"status":"UP"}
~~~

Authenticated health remains compact because this profile sets `never` for both details and components.

Info with a valid account:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" http://127.0.0.1:18081/actuator/info
~~~

JSON body:

~~~json
{"application":{"environment":"test"}}
~~~

Metrics with a valid account:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18081/actuator/metrics
~~~

Result:

~~~text
404
~~~

Testing with a valid account avoids confusing `401` at the authentication layer with the endpoint not being exposed.

### 7.3. Production: prod

Terminal A:

~~~powershell
java -jar target/management-profiles-1.0.0.jar --spring.profiles.active=prod
~~~

Health must be called on **19082**:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:19082/actuator/health
~~~

Result when healthy:

~~~json
{"status":"UP"}
~~~

Even valid accounts are not returned health details by the sample in this profile.

Check metrics on the exact management port, authenticated:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:19082/actuator/metrics
~~~

Result:

~~~text
404
~~~

Info is also not exposed in the `prod` profile. For this exact sample, calling `/actuator/health` on application port `18082` with a valid account returns `404`: the management endpoint moved to a separate port.

Do not take responses on the old port as evidence about the new profile. Another process may still be listening on the port you forgot to change.

### 7.4. No profile selected

Stop the process and run:

~~~powershell
java -jar target/management-profiles-1.0.0.jar
~~~

When no other configuration source activates a profile, the sample uses the shared policy: health on `18080`, no details; info and metrics are not exposed.

This is the sample's restrictive default choice. It does not prove you deployed production properly. The deployment system still needs to verify the intended profile is selected.

### 7.5. Clean up lab terminal variables

After stopping all runs, you can remove the variables from the terminal that supplied them:

~~~powershell
Remove-Item Env:ACTUATOR_USER, Env:ACTUATOR_PASSWORD -ErrorAction SilentlyContinue
Remove-Variable enteredSecret -ErrorAction SilentlyContinue
~~~

This removes the shell session's variable references; it does not guarantee erasing every copy from memory. Do not delete or alter same-named variables of a running deployed process.

## 8. Selecting profiles and supplying configuration from the runtime environment

In the hands-on commands, the profile is passed via an argument after the JAR name:

~~~powershell
java -jar target/management-profiles-1.0.0.jar --spring.profiles.active=prod
~~~

Another option is for the launch system to supply the `SPRING_PROFILES_ACTIVE` variable:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar target/management-profiles-1.0.0.jar
~~~

Pick one clear approach for the deployment environment; avoid having multiple places set conflicting values.

After testing with an environment variable in a local terminal, remove it if you do not want it affecting subsequent runs:

~~~powershell
Remove-Item Env:SPRING_PROFILES_ACTIVE -ErrorAction SilentlyContinue
~~~

Maven's `-Pprod` is a build tool profile mechanism, not a substitute for `--spring.profiles.active=prod`. Likewise, running a CI step named "test" does not automatically select `application-test.yml`.

Changing a YAML file packaged in source requires rebuilding the JAR to include the change. Simply selecting another profile already inside the JAR does not require rebuilding. With this standard sample, editing the file after the process has started also does not automatically update the running configuration right away.

## 9. Override precedence: check actual values, not just filenames

A value in `application-prod.yml` is not an immutable lock. External configuration or launch arguments can change the effective value.

In typical JAR runs of this lesson, you can keep in mind the simplified chain:

~~~text
Configuration files inside the JAR
    -> configuration files outside the JAR
    -> environment variables
    -> Java system properties
    -> command-line arguments
~~~

Higher-precedence sources can override earlier ones. This is a simplified model; test environments and specialized sources also have their own rules. [Boot configuration source precedence](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

For example, setting the `prod` profile while also passing a different exposure list can make the actual policy no longer match the table at the start of this lesson. Therefore, the profile name does not replace HTTP verification after startup.

Distinguish the syntax:

~~~text
-Dproperty.name=value     placed before -jar: Java system property
--property.name=value     placed after the JAR name: application argument
~~~

The two lines above describe syntax forms, not commands to run the sample.

For externally supplied operational configuration:

- Clearly document which source owns the profile, port, and exposure scope.
- Minimize duplicate values across multiple places.
- Do not print the entire environment or configuration just to look up one property.
- Verify required values with narrow checks.

If adding configuration directories, understand the difference between `spring.config.location` (replaces default locations) and `spring.config.additional-location` (adds locations). Do not add an arbitrary location and assume all packaged configuration still loads the same way.

## 10. Testing the policy via observable behavior

A meaningful test must confirm both what is **allowed to exist** and what is **not exposed**.

For this sample:

| Run | Key checks |
| --- | --- |
| dev | Public health is compact; authenticated health includes components; info has right label; authenticated metrics returns 200 |
| test | Health stays compact; info has right label; authenticated metrics returns 404 |
| prod | Health on port 19082; no details; authenticated info/metrics return 404 |
| No profile | Does not accidentally inherit dev's broad policy |

When comparing:

- Compare meaningful data fields, without hardcoding disk space or timestamps in health.
- Use a valid identity so restricted endpoints can be checked.
- Verify the actual port; if using a random port in tests, read the port from the started server.
- Use temporary secrets for test environments, never production accounts.
- Also check the external configuration sources actually used by the deployment step.

An in-memory test context alone does not prove a separate management port was opened and routed properly. When a separate port is part of the contract, test against a real server.

The sample was designed so the same JAR can be verified across the four runs above. In your own project, verify the final deployed outcome rather than merely finding a file named `application-prod.yml`.

## 11. Common configuration mistakes

### Using dev configuration as the shared base

If you put a broad list in `application.yml` and expect every environment to remember to close it down, a run that forgets the profile may inherit an unwanted scope.

Keep the shared file aligned with the project's default choice; put diagnostic expansions in the environments that need them.

### Adding an endpoint name while forgetting the effective list

When writing configuration across multiple sources, do not assume they merge additively as intended. Put the complete desired list in the layer that owns the policy, then verify the URLs.

If both `include` and `exclude` exist, check both; a name in `include` can still be removed by `exclude`.

### Confusing "authenticated" with "permitted to view all data"

The sample lets authenticated users view health details only in `dev`. `test` and `prod` still choose not to return details. Successful authentication does not nullify configuration restrictions.

### Thinking separating the port completes security

A separate port defines an access path. You must still consider who can connect and which identity is allowed to use management functions.

### Test configuration skewing production results

If tests always override exposure to a broad list or disable security, they may fail to catch deployment policy mistakes. When the goal is checking `prod`, run with the `prod` configuration and change only values needed for test infrastructure.

### Treating the profile name as the sole proof

The `info.application.environment` label is supplied by the configuration author; launch arguments can also override other properties. Cross-check profile, configuration sources, and HTTP results.

### Inheriting environment variables from an old terminal

A `SPRING_PROFILES_ACTIVE` variable remaining in a shell session can cause a "no profile passed" command to still run with the previously set profile. Check how the process was launched before concluding Boot ignored the shared file.

## 12. Self-check exercises

**Exercise 1 — Omitting the profile at startup.**

After clearing the `SPRING_PROFILES_ACTIVE` variable in your practice terminal, run the JAR without `--spring.profiles.active`. Predict health, info, and metrics, then verify with a valid account.

Result to explain: omitting the profile in the sample does not auto-enable `dev` or `prod`; the shared configuration has its own policy.

**Exercise 2 — Moving the monitoring tool.**

An agent moves to another machine, yet the management endpoint still binds to `127.0.0.1`. Why can't the agent connect?

Consider the listening address and network path. Exposing more endpoint names will not fix a network path that does not exist.

**Exercise 3 — Checking 401 and 404.**

In the `test` profile, call `info` without an account, then call `metrics` with a valid account. Explain why the two status codes differ even though neither run returns the data you were looking for.

In the sample, `info` is exposed but requires authentication; `metrics` is not exposed for this profile. Processing order can mask routing outcomes if you have not passed the authentication layer.

**Exercise 4 — Same JAR yet different effective policy.**

Two processes use the same JAR and the same profile name, yet one has an additional environment variable overriding exposure. Must they return the same management results?

No. You must inspect all effective configuration sources. Build artifact consistency is necessary, while runtime configuration still must be verified.

The core of separating environments is **stating the policy clearly, choosing the right configuration layer, and verifying the actual outcome**. Profiles help organize configuration; operational responsibility also covers how values are supplied and how you verify the process used them.

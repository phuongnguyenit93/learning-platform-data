# Build Once, Run in Two Environments, and Document the Configuration Contract

## 1. Practice Objectives

A Spring Boot application can reuse **the exact same JAR** across multiple environments without rebuilding source code. The prerequisite is separating four concerns clearly:

- **Artifact**: compiled Java code, dependencies, and shared non-sensitive resources.
- **Shared configuration**: sensible defaults across environments.
- **Environment configuration**: environment-specific profiles, ports, endpoints, timeouts, and logging levels.
- **Secrets**: API keys, passwords, and tokens supplied outside source/JAR/images at runtime.

This lesson builds a **config-once-demo** application with two runs:

| Property | Development | Production-like |
| --- | --- | --- |
| Profile | dev | prod |
| External config | deploy/dev | deploy/prod |
| Port | 8081 | 8082 |
| Deployment label | development | production |
| Gateway | Disabled | Enabled |
| Request timeout | 12s | 6s |
| Connect timeout | 2s | 2s |
| API key | Not required | Required, provided at runtime |
| Executable JAR | Same file | Same file |

**Learning outcomes:** build a single JAR, record its SHA-256 checksum, run the identical artifact in two environments with externalized configuration outside the JAR, verify bound values, supply secrets properly, and document a **configuration contract**.

The examples use **Java 21**, **Maven**, **Spring Boot 3.3.x**, Spring MVC, and Jakarta Bean Validation. Any URL under **example.invalid** is purely dummy data and performs no real payment transactions.

## 2. The "Build Once, Deploy Many" Mindset

Target workflow:

~~~text
Source + tests
      |
      v
Build once with Maven
      |
      v
config-once-demo-0.0.1-SNAPSHOT.jar
      |
      | Single SHA-256
      |
      +------------------------+
      |                        |
      v                        v
Dev environment           Prod environment
profile=dev               profile=prod
external config           external config
port 8081                 port 8082
gateway disabled          gateway enabled
no secret needed          runtime secret
      |                        |
      +------------------------+
                   |
                   v
       Same binary, different behavior
~~~

Avoid building **app-dev.jar** and **app-prod.jar** merely to swap endpoints or timeouts. If two artifacts differ byte-for-byte, staging does not actually validate the exact binary later deployed to production.

**"Build once"** does not mean configuration never changes or processes never need restarting. It means environment changes do not require recompiling or repackaging the binary.

## 3. Prerequisites

Required tools:

1. Java 21.
2. Maven 3.9 or Maven Wrapper.
3. Two free local ports: 8081 and 8082.
4. A Bash/zsh or PowerShell terminal.
5. Dummy API keys only for this practice.
6. No real production endpoints or credentials.

Verification commands:

~~~bash
java -version
mvn -version
~~~

No running PostgreSQL instance or real gateway is needed. The lesson focuses on externalized configuration, binding, and validation.

## 4. Directory Layout

~~~text
config-once-demo/
├── pom.xml
├── .gitignore
├── src/
│   ├── main/
│   │   ├── java/com/example/configonce/
│   │   │   ├── ConfigOnceApplication.java
│   │   │   ├── config/
│   │   │   │   ├── DeploymentProperties.java
│   │   │   │   └── GatewayProperties.java
│   │   │   └── web/
│   │   │       └── ConfigurationSummaryController.java
│   │   └── resources/
│   │       └── application.yml
│   └── test/
│       └── java/com/example/configonce/
│           ├── ConfigOnceApplicationTest.java
│           └── config/GatewayPropertiesRunnerTest.java
├── deploy/
│   ├── dev/application-dev.yml
│   ├── prod/application-prod.yml
│   └── config-contract.md
└── target/
    └── config-once-demo-0.0.1-SNAPSHOT.jar
~~~

**src/main/resources/application.yml** gets packaged into the JAR. Files inside **deploy/** are supplied outside the artifact at runtime.

Real projects may store external configuration in a GitOps repository, Helm chart, ConfigMap, or mounted files instead of keeping them inside the same source tree. What matters is keeping real secrets out of source control and build artifacts.

## 5. Maven `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
              https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>config-once-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

**Spring Boot 3.3.13** illustrates the 3.3.x release line; real projects should select a maintained/patched release per organizational security policy.

- **starter-web**: Spring MVC and embedded server.
- **starter-validation**: Jakarta Bean Validation implementation.
- **starter-test**: JUnit, AssertJ, Spring Boot Test.
- **spring-boot-maven-plugin**: packages the executable JAR.

Never bake secrets via resource filtering, Maven build properties, or Docker build arguments.

## 6. Main Class and Configuration Registration

File **src/main/java/com/example/configonce/ConfigOnceApplication.java**:

~~~java
package com.example.configonce;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigOnceApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigOnceApplication.class, args);
    }
}
~~~

**@ConfigurationPropertiesScan** discovers types annotated with **@ConfigurationProperties** under the application's subpackages.

Placing the annotation on a record alone is not enough for every context to register a bean automatically. Register it via scanning or **@EnableConfigurationProperties**.

Do not create separate main classes for dev and prod. The exact same `SpringApplication` starts using different external configuration sources.

## 7. `DeploymentProperties`

File **src/main/java/com/example/configonce/config/DeploymentProperties.java**:

~~~java
package com.example.configonce.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.deployment")
public record DeploymentProperties(
        @NotBlank String label) {
}
~~~

Property:

~~~text
demo.deployment.label
~~~

This carries a non-sensitive deployment label. There is no shared default; if `label` is missing, startup should fail because deployment configuration is incomplete.

This design choice demonstrates **required runtime configuration**.

## 8. `GatewayProperties`

File **src/main/java/com/example/configonce/config/GatewayProperties.java**:

~~~java
package com.example.configonce.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.gateway")
public record GatewayProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        boolean enabled,
        String apiKey) {

    @AssertTrue(
        message = "request-timeout must exceed connect-timeout")
    public boolean isTimeoutOrderValid() {
        if (connectTimeout == null || requestTimeout == null) {
            return true;
        }
        return requestTimeout.compareTo(connectTimeout) > 0;
    }

    @AssertTrue(
        message = "gateway api-key is required when enabled")
    public boolean isCredentialPresentWhenEnabled() {
        return !enabled ||
                (apiKey != null && !apiKey.isBlank());
    }

    @AssertTrue(
        message = "enabled gateway requires HTTPS base-url")
    public boolean isHttpsWhenEnabled() {
        return !enabled ||
                (baseUrl != null &&
                "https".equalsIgnoreCase(baseUrl.getScheme()));
    }
}
~~~

Canonical keys:

~~~text
demo.gateway.base-url
demo.gateway.connect-timeout
demo.gateway.request-timeout
demo.gateway.enabled
demo.gateway.api-key
~~~

### 8.1. Why Use `URI` and `Duration` Types?

The Spring Boot Binder converts strings into Java types:

~~~text
https://sandbox.example.invalid -> URI
2s                              -> Duration.ofSeconds(2)
500ms                           -> Duration.ofMillis(500)
true                            -> boolean true
~~~

Comparing converted `Duration` values is far more reliable than comparing differently formatted duration strings.

### 8.2. Timeout Ordering Constraint

Both timeouts may parse cleanly yet violate the illustrative business contract:

~~~text
connect-timeout=8s
request-timeout=3s
~~~

The method **isTimeoutOrderValid()** requires `requestTimeout` to exceed `connectTimeout`. This is a rule chosen by the demo application, not a universal law for every HTTP client.

### 8.3. Mode-Dependent Secrets

- Gateway disabled in dev: no `apiKey` needed.
- Gateway enabled in prod: non-blank `apiKey` is required.
- Gateway enabled: URL must use the HTTPS scheme.

**@AssertTrue** offers a straightforward way to write cross-field constraints. If an application needs field-targeted messages, a custom class-level Bean Validation constraint can be used.

### 8.4. Never Log Records Containing Secrets

Records auto-generate a **toString()** including all components, which can expose `apiKey`.

Do not do:

~~~java
System.out.println(gatewayProperties);
~~~

Never log tokens in exceptions, REST responses, or metric labels. Property names and validation status suffice for most diagnostics.

## 9. Non-Sensitive Configuration Summary Endpoint

File **src/main/java/com/example/configonce/web/ConfigurationSummaryController.java**:

~~~java
package com.example.configonce.web;

import java.util.Arrays;
import java.util.List;

import com.example.configonce.config.DeploymentProperties;
import com.example.configonce.config.GatewayProperties;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ConfigurationSummaryController {

    private final DeploymentProperties deployment;
    private final GatewayProperties gateway;
    private final Environment environment;

    public ConfigurationSummaryController(
            DeploymentProperties deployment,
            GatewayProperties gateway,
            Environment environment) {
        this.deployment = deployment;
        this.gateway = gateway;
        this.environment = environment;
    }

    @GetMapping("/configuration")
    public PublicSummary summary() {
        return new PublicSummary(
                deployment.label(),
                Arrays.asList(environment.getActiveProfiles()),
                gateway.enabled(),
                gateway.connectTimeout().toMillis(),
                gateway.requestTimeout().toMillis());
    }

    public record PublicSummary(
            String deployment,
            List<String> activeProfiles,
            boolean gatewayEnabled,
            long connectTimeoutMs,
            long requestTimeoutMs) {
    }
}
~~~

The demo endpoint exposes only selected non-sensitive fields; **never return `apiKey`, and never dump `Environment`**.

In real production environments, even profile names or feature status can be internal metadata. Protect or remove such endpoints outside learning exercises.

## 10. Base `application.yml`

File **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: config-once-demo

server:
  port: 8080

demo:
  gateway:
    connect-timeout: 2s
    request-timeout: 10s

logging:
  level:
    root: INFO
~~~

Shared configuration contains:

- Application name.
- Fallback port `8080`.
- Default connect timeout `2s`.
- Default request timeout `10s`.
- Log level `INFO`.

Excludes:

~~~text
demo.deployment.label
demo.gateway.base-url
demo.gateway.api-key
~~~

The deployment label and gateway endpoint are provided per environment; the API key must come from a runtime secret source.

If launched without external configuration, **@NotBlank** or **@NotNull** causes startup to fail. That fail-fast behavior is intentional.

## 11. External `dev` File Outside the JAR

File **deploy/dev/application-dev.yml**:

~~~yaml
server:
  port: 8081

demo:
  deployment:
    label: "development"

  gateway:
    enabled: false
    base-url: "https://sandbox-gateway.example.invalid"
    request-timeout: 12s

logging:
  level:
    com.example.configonce: DEBUG
~~~

Dev behavior:

- Port `8081`.
- Profile `dev`.
- Deployment label `development`.
- Gateway disabled.
- Request timeout `12s` overriding default `10s`.
- Connect timeout `2s` inherited from the shared file.
- No API key required because gateway is disabled.

This file does not set **spring.profiles.active=dev**. The active profile is selected by the launcher or a non-profile-specific source.

## 12. External `prod` File Outside the JAR

File **deploy/prod/application-prod.yml**:

~~~yaml
server:
  port: 8082

demo:
  deployment:
    label: "production"

  gateway:
    enabled: true
    base-url: "https://gateway.example.invalid"
    request-timeout: 6s

logging:
  level:
    root: WARN
    com.example.configonce: INFO
~~~

Prod behavior:

- Port `8082`.
- Profile `prod`.
- Deployment label `production`.
- Gateway enabled.
- Request timeout `6s`.
- Connect timeout `2s` from the shared file.
- Gateway URL uses HTTPS scheme.
- API key is **required yet absent from YAML**.

When `enabled=true` without a secret, validation must refuse startup.

## 13. Build Exactly Once

From the project root:

~~~bash
mvn clean verify
~~~

The Spring Boot Maven plugin produces an executable JAR:

~~~text
target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

With Maven Wrapper:

~~~bash
./mvnw clean verify
~~~

Maven **verify** runs all configured lifecycle checks, including appropriate tests. For simpler projects, **mvn clean package** can also build the JAR.

**After building, do not run another separate packaging step for prod.** Both environments run this exact artifact.

## 14. Recording the SHA-256 Checksum

Linux:

~~~bash
sha256sum target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

macOS:

~~~bash
shasum -a 256 target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

PowerShell:

~~~powershell
Get-FileHash -Path target/config-once-demo-0.0.1-SNAPSHOT.jar -Algorithm SHA256
~~~

Save the actual checksum. Re-run this at the end of the practice against the exact same file. Never pre-write a dummy hash into documentation, because checksums must be computed from the real artifact.

**Matching hashes prove the JAR bytes never changed**, yet do not by themselves prove config is valid; pair them with smoke tests.

## 15. Running `dev` Using the Same JAR

At the project root, in a first terminal:

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=file:./deploy/dev/
~~~

Two arguments:

- **spring.profiles.active=dev** selects the `dev` profile.
- **spring.config.additional-location=file:./deploy/dev/** adds an external Config Data directory outside the JAR.

For directory locations, the trailing **/** tells Boot to append filenames derived from **spring.config.name**.

Use **additional-location** to keep the shared `application.yml` inside the JAR; **spring.config.location** can replace the default search locations according to Boot rules.

### 15.1. Verifying the Response

~~~bash
curl -fsS http://localhost:8081/api/configuration
~~~

Illustrative response:

~~~json
{
  "deployment": "development",
  "activeProfiles": ["dev"],
  "gatewayEnabled": false,
  "connectTimeoutMs": 2000,
  "requestTimeoutMs": 12000
}
~~~

**2000ms** comes from the shared `2s`, and **12000ms** comes from the dev override `12s`. The sandbox URL is not called and no secret is returned in the response.

### 15.2. Changing the Timeout Without Rebuilding

Stop the dev application and restart with:

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=file:./deploy/dev/ \
  --demo.gateway.request-timeout=20s
~~~

The response shows **requestTimeoutMs=20000** because CLI overrides take higher precedence than ordinary Config Data.

The JAR remains untouched and requires no new Maven build.

## 16. Supplying the Secret for `prod`

Canonical property:

~~~text
demo.gateway.api-key
~~~

Environment variable name under Spring Boot relaxed binding:

~~~text
DEMO_GATEWAY_APIKEY
~~~

Secrets should come from a secret manager, container runtime, Kubernetes Secret, or approved local secrets tooling.

**Never place literal production API keys into commands saved in shell history.** For this practice, use only a dummy credential with zero permissions on real systems.

If running in a container or CI, make sure the variable is injected **into the Java process itself**, rather than sitting solely in an outer shell or an unparsed `.env` file.

## 17. Running `prod` Using the Exact Same JAR

In another terminal, once the platform has safely injected **DEMO_GATEWAY_APIKEY**:

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:./deploy/prod/
~~~

Do not run Maven a second time.

Check:

~~~bash
curl -fsS http://localhost:8082/api/configuration
~~~

Illustrative response:

~~~json
{
  "deployment": "production",
  "activeProfiles": ["prod"],
  "gatewayEnabled": true,
  "connectTimeoutMs": 2000,
  "requestTimeoutMs": 6000
}
~~~

Comparison:

| Value | Dev | Prod |
| --- | --- | --- |
| deployment | development | production |
| profile | dev | prod |
| HTTP port | 8081 | 8082 |
| gatewayEnabled | false | true |
| connectTimeoutMs | 2000 | 2000 |
| requestTimeoutMs | 12000 | 6000 |
| secret | Not required | Required |

Identical Java classes and artifact were used. Only the effective runtime values differed due to external runtime sources.

### 17.1. Running Both Processes Concurrently

Because ports differ, `dev` and `prod` can run side-by-side on localhost if system resources allow and no other conflicts exist.

Each process has its own `Environment`. Avoid reusing a shell holding prod secrets to test dev without tightly auditing exported variables.

## 18. Testing `prod` Configuration Errors

### 18.1. Missing API Key

Start `prod` in a process without **DEMO_GATEWAY_APIKEY**. Because `enabled=true`, **isCredentialPresentWhenEnabled()** returns `false`; if Validation infrastructure is active, application context startup fails.

This is the intended behavior to prevent launching an enabled integration without credentials.

### 18.2. Invalid `Duration`

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=file:./deploy/dev/ \
  --demo.gateway.request-timeout=not-a-duration
~~~

The Binder cannot convert **not-a-duration** into `Duration`, so binding fails.

### 18.3. Invalid Ordering Between Two `Duration`s

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=file:./deploy/dev/ \
  --demo.gateway.request-timeout=1s
~~~

With `connect-timeout=2s`, `1s` parses cleanly yet violates `requestTimeout > connectTimeout`.

### 18.4. `prod` Using HTTP

If `enabled=true` while `base-url` carries an **http** scheme, the validation rule enforcing HTTPS fails.

**Never remove validation to hide deployment mistakes.** Fix the configuration source.

## 19. Running with OS Environment Variables

Bash/zsh:

~~~bash
SPRING_PROFILES_ACTIVE=dev \
SPRING_CONFIG_ADDITIONALLOCATION=file:./deploy/dev/ \
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

Prod, once the secret has been injected into the Environment:

~~~bash
SPRING_PROFILES_ACTIVE=prod \
SPRING_CONFIG_ADDITIONALLOCATION=file:./deploy/prod/ \
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

PowerShell dev:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:SPRING_CONFIG_ADDITIONALLOCATION = "file:./deploy/dev/"
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

PowerShell prod once the secret is present:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
$env:SPRING_CONFIG_ADDITIONALLOCATION = "file:./deploy/prod/"
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

Afterward, you can clean up the test variables in PowerShell:

~~~powershell
Remove-Item Env:SPRING_PROFILES_ACTIVE -ErrorAction SilentlyContinue
Remove-Item Env:SPRING_CONFIG_ADDITIONALLOCATION -ErrorAction SilentlyContinue
Remove-Item Env:DEMO_GATEWAY_APIKEY -ErrorAction SilentlyContinue
~~~

Depending on the platform, process environments can be inspected by privileged users or tooling. Environment variables are a **runtime injection** mechanism—they do not replace secret management or access control.

## 20. Recomputing the Checksum

After running both dev and prod **without rebuilding**, recompute SHA-256 on the JAR:

~~~bash
sha256sum target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

Or:

~~~powershell
Get-FileHash -Path target/config-once-demo-0.0.1-SNAPSHOT.jar -Algorithm SHA256
~~~

The hash must match the checksum recorded right after the build.

This proves dev and prod did not need two distinct artifacts. Yet checksums alone are insufficient; the smoke responses in Sections 15 and 17 prove behavior actually adapted.

## 21. What Is a Configuration Contract?

A **configuration contract** is the agreement between a code module and the deployment platform:

1. Which canonical keys are supported?
2. What Java type does each key carry?
3. What unit does each value expect?
4. Where do defaults live?
5. Which keys are required and under what conditions?
6. Which sources are permitted to supply values?
7. If multiple sources supply values, what is the precedence?
8. Is the value a secret?
9. Who owns the key/contract and who supplies runtime values?
10. What validation constraints apply?
11. Does changing a value require a restart?
12. If a key is renamed, how does migration occur?
13. How do we test without leaking credentials?

A configuration contract turns scattered strings into a documented and tested API.

## 22. Demo Configuration Contract

A table that can be stored in **deploy/config-contract.md**:

| Canonical key | Type | Default | Dev | Prod | Sensitive |
| --- | --- | --- | --- | --- | --- |
| spring.application.name | String | config-once-demo | Inherited | Inherited | No |
| server.port | int | 8080 | 8081 | 8082 | No |
| spring.profiles.active | Profile | Never hard-coded | dev | prod | No |
| spring.config.additional-location | Location | None | deploy/dev/ | deploy/prod/ | Path may be internal |
| demo.deployment.label | String | None | development | production | No |
| demo.gateway.enabled | boolean | false when absent | false | true | No |
| demo.gateway.base-url | URI | None | Sandbox | Dummy prod HTTPS | Endpoint |
| demo.gateway.connect-timeout | Duration | 2s | 2s | 2s | No |
| demo.gateway.request-timeout | Duration | 10s | 12s | 6s | No |
| demo.gateway.api-key | String | None | Not required | Runtime Secret | **Yes** |
| logging.level.root | Log level | INFO | INFO | WARN | No |

### 22.1. Requiredness

| Key / Constraint | Requirement |
| --- | --- |
| demo.deployment.label | Non-null/non-blank in all environments |
| demo.gateway.base-url | Non-null |
| demo.gateway.connect-timeout | Non-null |
| demo.gateway.request-timeout | Non-null |
| Gateway timeouts | requestTimeout > connectTimeout |
| demo.gateway.api-key | Non-blank when enabled=true |
| Gateway URL | HTTPS scheme when enabled=true |
| server.port | Valid Integer, available port |
| spring.profiles.active | Deployment workflow must intentionally select dev/prod |

Never place a default password like **changeme** or a dummy secret into shared config where it could accidentally allow a production app to boot misconfigured.

### 22.2. Ownership

| Group | Contract owner | Runtime owner |
| --- | --- | --- |
| demo.deployment | Service/Platform | Deployment pipeline |
| demo.gateway | Gateway integration module | Service owner |
| demo.gateway.api-key | Gateway integration defines the key | Secret manager/Platform |
| server.port | Platform | Deployment |
| logging.level.* | SRE/Platform | Deployment |

The contract owner defines types, meanings, and validation. The runtime owner supplies values. The secret owner manages rotation and access permissions.

## 23. Environment Variable Naming Rules

Spring Boot defines env names for canonical properties:

1. Dot **.** → underscore **_**.
2. Dash **-** → removed.
3. Converted to uppercase.

~~~text
demo.gateway.base-url
    -> DEMO_GATEWAY_BASEURL

demo.gateway.connect-timeout
    -> DEMO_GATEWAY_CONNECTTIMEOUT

demo.gateway.request-timeout
    -> DEMO_GATEWAY_REQUESTTIMEOUT

demo.gateway.api-key
    -> DEMO_GATEWAY_APIKEY

demo.deployment.label
    -> DEMO_DEPLOYMENT_LABEL

spring.profiles.active
    -> SPRING_PROFILES_ACTIVE

spring.config.additional-location
    -> SPRING_CONFIG_ADDITIONALLOCATION
~~~

**DEMO_GATEWAY_API_KEY** is not the direct canonical mapping from **demo.gateway.api-key**, because hyphens do not become extra underscores.

Include both canonical and env names in the contract to prevent mistakes when writing Helm charts, Compose files, CI pipelines, or deployment manifests.

## 24. Source Precedence

Spring Boot defines `PropertySources` precedence order. A simplified diagram covers the most common sources:

~~~text
Default properties
      |
Config Data inside JAR
      |
External Config Data / profile-specific
      |
OS environment variables
      |
Java system properties
      |
Command-line arguments
~~~

This is only a relative sketch of selected sources, not the complete Spring Boot order. Test-specific sources, `SPRING_APPLICATION_JSON`, and other sources each have their own positions.

Example:

~~~text
application.yml:               request-timeout=10s
application-prod.yml:          request-timeout=6s
DEMO_GATEWAY_REQUESTTIMEOUT:   9s
CLI:                           --demo.gateway.request-timeout=4s

Illustrative result: 4s
~~~

CLI arguments can override Config Data values. However, if overridden to `1s` while `connect-timeout=2s`, validation still rejects it. **High precedence does not imply validity.**

### 24.1. Java Defaults vs. `Environment` Defaults

When using a Java record with **@DefaultValue**, the default applies during binding and is not automatically written back as a key in `Environment`.

In our example, the default `Duration` lives in **application.yml**, so it is visible as a Config Data property.

The contract must record the source of defaults, not merely the final number.

## 25. Loading Secrets via `configtree`

Instead of env vars, a secret can be mounted as a file:

~~~text
/run/secrets/
└── demo.gateway.api-key
~~~

The filename matches the key; the file contents hold the platform-provided secret and are never committed.

This can be declared in external prod configuration:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Spring Boot's Config Data infrastructure can import the **demo.gateway.api-key** property from that file.

**`configtree` does not encrypt files automatically.** Filesystem permissions, the secret store, workload identity, and the container runtime must protect the secret.

If a secret is required, do not casually add **optional:** and overlook a missing mount. Rely on fail-fast behavior and deployment verification.

### 25.1. Rotation Does Not Mean the Java Record Mutates Automatically

After the bean binds, editing the secret file on disk does not automatically refresh `GatewayProperties`. Adopting new secrets requires a designed restart or refresh mechanism.

For env vars, a running process typically does not see updated values when a deployment secret changes. In Kubernetes, a Pod replacement or rolling restart may be required.

## 26. Shared Docker Image

A simple Dockerfile:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/config-once-demo-0.0.1-SNAPSHOT.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Build the image once:

~~~bash
docker build -t config-once-demo:1.0.0 .
~~~

Dev:

~~~bash
docker run --rm \
  -p 8081:8081 \
  -v "$PWD/deploy/dev:/config:ro" \
  config-once-demo:1.0.0 \
  --spring.profiles.active=dev \
  --spring.config.additional-location=file:/config/
~~~

Prod, when the host provides the env secret securely:

~~~bash
docker run --rm \
  -p 8082:8082 \
  -v "$PWD/deploy/prod:/config:ro" \
  --env DEMO_GATEWAY_APIKEY \
  config-once-demo:1.0.0 \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/config/
~~~

The image contains neither dev/prod config nor any API key. Differences are supplied at runtime via mounts, profiles, and secrets.

**Tags are not inherently immutable**: in production, pin image digests to guarantee identical image bytes across deployments.

## 27. Kubernetes ConfigMap and Secret

Kubernetes can provide non-secret values via a ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: config-once-prod
data:
  SPRING_PROFILES_ACTIVE: "prod"
  SERVER_PORT: "8082"
  DEMO_DEPLOYMENT_LABEL: "production"
  DEMO_GATEWAY_ENABLED: "true"
  DEMO_GATEWAY_BASEURL: "https://gateway.example.invalid"
  DEMO_GATEWAY_CONNECTTIMEOUT: "2s"
  DEMO_GATEWAY_REQUESTTIMEOUT: "6s"
~~~

Never put **DEMO_GATEWAY_APIKEY** inside a ConfigMap.

Once a Secret is provisioned by the platform, a Deployment can reference it:

~~~yaml
env:
  - name: DEMO_GATEWAY_APIKEY
    valueFrom:
      secretKeyRef:
        name: gateway-credentials
        key: apiKey
~~~

This is only a container-spec snippet, not a complete Deployment manifest.

**Base64 inside a Kubernetes Secret is not encryption.** The cluster requires RBAC, encryption at rest, auditing, and workload access controls.

If using ConfigMap env vars instead of profile files, designate a single source of truth and document precedence; avoid layering conflicting sources without clear policy.

## 28. Testing Configuration with `ApplicationContextRunner`

Use `ApplicationContextRunner` to test binding and validation without launching a web server.

File **src/test/java/com/example/configonce/config/GatewayPropertiesRunnerTest.java**:

~~~java
package com.example.configonce.config;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesRunnerTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(GatewayProperties.class)
    static class Config {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(Config.class)
                .withConfiguration(AutoConfigurations.of(
                        ValidationAutoConfiguration.class));

    @Test
    void devDoesNotRequireApiKey() {
        runner.withPropertyValues(
                "demo.gateway.base-url=https://sandbox.example.invalid",
                "demo.gateway.connect-timeout=2s",
                "demo.gateway.request-timeout=12s",
                "demo.gateway.enabled=false"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            GatewayProperties p =
                    context.getBean(GatewayProperties.class);

            assertThat(p.enabled()).isFalse();
            assertThat(p.connectTimeout())
                    .isEqualTo(Duration.ofSeconds(2));
            assertThat(p.requestTimeout())
                    .isEqualTo(Duration.ofSeconds(12));
        });
    }

    @Test
    void prodRejectsMissingApiKey() {
        runner.withPropertyValues(
                "demo.gateway.base-url=https://gateway.example.invalid",
                "demo.gateway.connect-timeout=2s",
                "demo.gateway.request-timeout=6s",
                "demo.gateway.enabled=true"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }

    @Test
    void prodAcceptsTestOnlyCredential() {
        runner.withPropertyValues(
                "demo.gateway.base-url=https://gateway.example.invalid",
                "demo.gateway.connect-timeout=2s",
                "demo.gateway.request-timeout=6s",
                "demo.gateway.enabled=true",
                "demo.gateway.api-key=test-only-placeholder"
        ).run(context -> {
            assertThat(context).hasNotFailed();
        });
    }

    @Test
    void detectsInvalidTimeoutOrder() {
        runner.withPropertyValues(
                "demo.gateway.base-url=https://sandbox.example.invalid",
                "demo.gateway.connect-timeout=8s",
                "demo.gateway.request-timeout=3s",
                "demo.gateway.enabled=false"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }

    @Test
    void detectsInvalidDurationString() {
        runner.withPropertyValues(
                "demo.gateway.base-url=https://sandbox.example.invalid",
                "demo.gateway.connect-timeout=2s",
                "demo.gateway.request-timeout=invalid",
                "demo.gateway.enabled=false"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }
}
~~~

The tests verify:

- Disabled gateway requires no secret.
- Enabled gateway without a secret fails.
- A test-only credential lets the enabled gateway pass.
- Invalid `Duration` ordering is rejected.
- Invalid `Duration` conversion is rejected.

Avoid asserting the full verbatim exception message because wrapping/formatting can change across patch versions. When verifying an exact constraint, inspect the root cause at an appropriate scope.

**`ApplicationContextRunner`** does not by default run `SpringApplication`'s full Config Data bootstrap, so proving that real profile files load requires dedicated smoke/integration tests.

## 29. Integration Test with `SpringBootTest`

File **src/test/java/com/example/configonce/ConfigOnceApplicationTest.java**:

~~~java
package com.example.configonce;

import java.time.Duration;

import com.example.configonce.config.DeploymentProperties;
import com.example.configonce.config.GatewayProperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "demo.deployment.label=test",
    "demo.gateway.base-url=https://sandbox.example.invalid",
    "demo.gateway.connect-timeout=1s",
    "demo.gateway.request-timeout=3s",
    "demo.gateway.enabled=false"
})
class ConfigOnceApplicationTest {

    @Autowired
    DeploymentProperties deployment;

    @Autowired
    GatewayProperties gateway;

    @Test
    void bindsExpectedValues() {
        assertThat(deployment.label()).isEqualTo("test");
        assertThat(gateway.enabled()).isFalse();
        assertThat(gateway.connectTimeout())
                .isEqualTo(Duration.ofSeconds(1));
        assertThat(gateway.requestTimeout())
                .isEqualTo(Duration.ofSeconds(3));
    }
}
~~~

This test supplies isolated dummy properties and therefore needs neither a production Secret nor external files outside the JAR.

It validates wiring and binding inside `ApplicationContext`, while **not proving on its own** that external dev/prod configs are properly mounted. That still requires smoke tests like Sections 15–17.

## 30. Two-Environment Smoke Test

Procedure:

1. Run **mvn clean verify**.
2. Record the JAR's SHA-256.
3. Run dev with the `dev` profile and `dev` additional-location.
4. Call **http://localhost:8081/api/configuration**.
5. Verify label `development`, gateway disabled, and timeout `12s`.
6. Stop dev or keep port `8081` running.
7. Supply a safe dummy token for prod.
8. Run **the exact same JAR** with the `prod` profile and `prod` additional-location.
9. Call **http://localhost:8082/api/configuration**.
10. Verify label `production`, gateway enabled, and timeout `6s`.
11. Test prod missing the secret and observe fail-fast startup failure.
12. Recompute SHA-256; it must match the post-build checksum.

Evidence table:

| Verification item | Dev | Prod |
| --- | --- | --- |
| JAR SHA-256 | Hash X | Hash X |
| Rebuilt between runs | No | No |
| Profile | dev | prod |
| Port | 8081 | 8082 |
| Label | development | production |
| Gateway enabled | false | true |
| Connect timeout | 2s | 2s |
| Request timeout | 12s | 6s |
| Secret | Not required | Runtime secret |

Never look solely at `"Started"` in the logs and assume everything works; verify effective bean values and fail-fast checks.

## 31. Sample Contents of `deploy/config-contract.md`

Alongside the table, document operational details:

~~~text
Service:
  config-once-demo

Artifact:
  config-once-demo-0.0.1-SNAPSHOT.jar
  Java 21
  Spring Boot 3.3.x

Base configuration:
  classpath:/application.yml

External configuration:
  dev:  deploy/dev/application-dev.yml
  prod: deploy/prod/application-prod.yml

Bootstrap:
  SPRING_PROFILES_ACTIVE
  SPRING_CONFIG_ADDITIONALLOCATION

Secret contract:
  canonical key: demo.gateway.api-key
  environment name: DEMO_GATEWAY_APIKEY
  required when: demo.gateway.enabled=true
  storage: secret manager/runtime source
  do not commit actual value

Validation:
  deployment.label not blank
  gateway.baseUrl not null
  requestTimeout greater than connectTimeout
  enabled gateway needs nonblank apiKey
  enabled gateway needs HTTPS baseUrl

Refresh:
  Record configuration does not auto-refresh.
  Restart/rotation procedure needed.

Observability:
  Demo endpoint must not be public in production.
  Never expose API key or full Environment.
~~~

A contract is a living document, not a one-time dump of a single process's values. Update it whenever keys, types, defaults, owners, sources, or security policies change.

## 32. Renaming a Key Is an External API Change

A key such as **demo.gateway.base-url** can appear across YAML files, CLI scripts, ConfigMaps, Helm charts, Terraform modules, CI variables, and test fixtures.

If renamed to **demo.integration.gateway.endpoint**, Spring Boot relaxed binding will not treat two semantically different names as aliases automatically.

A migration plan should specify:

1. Old key and new key.
2. Coexistence support window.
3. Which key takes precedence when both are supplied.
4. Runtime compatibility logic if needed.
5. Rollout sequence across deployments.
6. Tests for old-only, new-only, both, and neither.
7. Deprecation warnings without logging secrets.
8. Announced release removing the old key.

**Configuration metadata** and **@DeprecatedConfigurationProperty** assist tooling, yet do not automatically create runtime aliases.

## 33. Early-Read Properties Need Early Sources

Properties such as **logging.*** and **spring.main.*** are consumed by Spring Boot during startup before context refresh.

**@PropertySource** on a `@Configuration` class is typically processed during refresh, too late for certain logging or `SpringApplication` decisions.

In this lesson, logging levels sit in **application.yml** and **application-prod.yml**, which are Config Data files suited to early-read properties.

Similarly, **spring.config.additional-location** must arrive early enough for Boot to know where to search for Config Data, making CLI or env vars a natural choice.

## 34. Common Mistakes

### 34.1. Building Two JARs Just to Switch Endpoints

Different runtime values do not require different binaries. Use one artifact and externalized configuration.

### 34.2. Placing Real Secrets in `application-prod.yml`

They can end up in Git, backups, or images. Use runtime secret sources and validation.

### 34.3. Placing `spring.profiles.active` Inside `application-prod.yml`

A profile-specific file is the wrong place to activate the very profile selecting that file. Use the launcher or a non-profile-specific source.

### 34.4. Forgetting the Trailing `/` on a Directory Location

For directory locations, use **file:./deploy/prod/** so Boot resolves filenames properly.

### 34.5. Using `spring.config.location` Instead of `additional-location`

That can accidentally replace the default locations and drop the shared `application.yml`. Use `additional-location` when adding directories alongside defaults.

### 34.6. Wrong Env Var Name

Use **DEMO_GATEWAY_APIKEY** per canonical conversion. Do not invent extra underscores for kebab-case dashes.

### 34.7. Seeing One Value in a File While Runtime Uses Another

A higher-precedence source may be overriding it. Inspect `Environment`, active profiles, CLI, env, and Config Data locations.

### 34.8. `Duration` Parses Yet Validation Fails

A `Duration` like `1s` has valid syntax yet can violate the `request`/`connect` relationship. Distinguish conversion from validation.

### 34.9. Gateway Enabled Without a Key

Never disable features or checks just to paper over production mistakes; fix the Secret source.

### 34.10. Assuming Java Automatically Reads a `.env` File

A `.env` file does not automatically enter the process environment unless a shell, IDE, Compose, or tooling parses and exports it.

### 34.11. Rotating a Secret While the Bean Retains the Old Value

Standard configuration records do not auto-refresh. Use controlled restarts or explicit reload support.

### 34.12. Logging a Record's `toString()`

Doing so can expose `apiKey`. Log only allowlisted non-sensitive fields.

### 34.13. Exposing a Public Endpoint That Dumps Config

Even environment metadata can be sensitive internal detail. Protect or remove the demo endpoint.

### 34.14. Treating Base64 as Encryption

Kubernetes Secrets use base64 encoding; you still need RBAC, encryption at rest, auditing, and tight workload permissions.

### 34.15. Checking Only SHA-256

Identical hashes do not prove configuration is valid; combine them with smoke tests and contract assertions.

## 35. Extension Lab A — Adding `staging`

Keeping the JAR unchanged, create **deploy/staging/application-staging.yml**:

~~~yaml
server:
  port: 8083

demo:
  deployment:
    label: "staging"

  gateway:
    enabled: true
    base-url: "https://staging-gateway.example.invalid"
    request-timeout: 7s
~~~

Supply a dummy runtime secret and run:

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=staging \
  --spring.config.additional-location=file:./deploy/staging/
~~~

Check endpoint `8083`, then recompute the JAR hash. If the hash matches, you deployed another environment without building a new variant.

## 36. Extension Lab B — Precedence

1. Shared file sets `request-timeout` to `10s`.
2. Dev file sets `12s`.
3. Env sets **DEMO_GATEWAY_REQUESTTIMEOUT=15s**.
4. CLI sets **--demo.gateway.request-timeout=20s**.
5. Run and observe the value.
6. Remove CLI and run again.
7. Remove env and run again.

Do not edit or rebuild the JAR. Record the observed value at each step to internalize precedence.

## 37. Extension Lab C — Secret Volume

1. Create an uncommitted local secrets directory.
2. Create file **demo.gateway.api-key** containing a dummy credential.
3. Restrict file read permissions.
4. Configure **configtree:** pointing to that folder.
5. Run `prod` with `enabled=true`.
6. Temporarily remove the file and run again to verify fail-fast startup.
7. Never print the secret file contents in logs or screenshots.

This exercise separates **the contract property name** from **the value-supply mechanism**.

## 38. Extension Lab D — Immutable Image

1. Build the JAR once.
2. Build the Docker image once.
3. Mount dev config and run the dev container.
4. Mount prod config/secrets and run the prod container.
5. Keep the exact same image digest.
6. Query the HTTP endpoints and compare responses.
7. Never edit the Dockerfile or rebuild just to change timeouts.

This extends the build-once principle to container deployments.

## 39. Completion Checklist

- [ ] A Java 21 / Spring Boot 3.3.x Maven project is set up.
- [ ] A single executable JAR builds cleanly.
- [ ] SHA-256 is recorded right after the build.
- [ ] `application.yml` contains only shared non-secret defaults.
- [ ] Dev configuration lives outside the JAR.
- [ ] Prod configuration lives outside the JAR.
- [ ] Profiles are selected at runtime.
- [ ] `additional-location` uses valid paths with a trailing `/` for directories.
- [ ] `DeploymentProperties` is registered and bound.
- [ ] `GatewayProperties` is registered and bound.
- [ ] `URI`, `Duration`, and `boolean` convert properly.
- [ ] Dev gateway disabled requires no secret.
- [ ] Prod gateway enabled requires a secret.
- [ ] Prod missing its secret fails fast.
- [ ] Prod uses an HTTPS endpoint.
- [ ] Validation catches invalid timeout ordering.
- [ ] Dev runs on `8081` with label `development`.
- [ ] Prod runs on `8082` with label `production`.
- [ ] Shared `2s` connect timeout applies in both.
- [ ] Dev and prod use different request timeouts.
- [ ] No real API key exists in Git/JAR/image.
- [ ] Demo endpoint exposes no secrets.
- [ ] Smoke tests have been executed.
- [ ] No rebuild occurred between environments.
- [ ] Final SHA-256 matches the initial SHA-256.
- [ ] Contract documents keys, types, units, defaults, and requiredness.
- [ ] Contract documents env variable names and precedence.
- [ ] Contract documents ownership and secret policy.
- [ ] Contract includes restart/rotation guidance.
- [ ] Tests cover missing, invalid, and cross-field values.
- [ ] Can add `staging` without rebuilding.

## 40. Conclusion

With Spring Boot Externalized Configuration, the same artifact can run across many environments when responsibilities are cleanly separated:

1. **One binary** is built, tested, released, and identified by checksum/digest.
2. **Shared configuration** holds non-sensitive defaults.
3. **Environment configuration** comes from profile-specific Config Data, env vars, or external files outside the JAR.
4. **Secrets** come from secure runtime sources.
5. **`@ConfigurationProperties`** maps inputs to strongly typed Java objects.
6. **Validation** catches missing values or violated relationships.
7. **`PropertySource` precedence** explains effective values.
8. **Smoke tests** prove differing runtime behavior despite identical artifacts.
9. **Configuration contracts** align developers, operations, and security teams.
10. **Restart/rotation policies** handle secret changes after startup.

This practice succeeds when dev and prod run **the exact same JAR**, receive environment-specific values via `Environment`, keep real secrets out of source control, and maintain a complete configuration contract.

## Official References

- Spring Boot 3.3 — Externalized Configuration, PropertySource Order, Config Data, and Configuration Trees: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Boot 3.3 — Type-safe Configuration Properties and Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot 3.3 — Testing: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
- Spring Boot 3.3 — Configuration Metadata: https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata/index.html
- Spring Framework — Environment: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- Kubernetes — ConfigMaps: https://kubernetes.io/docs/concepts/configuration/configmap/
- Kubernetes — Secrets: https://kubernetes.io/docs/concepts/configuration/secret/

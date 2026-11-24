# One Build for Multiple Environments: Source Code and Configuration Change Independently

## 1. The Problem to Solve

A Spring Boot application typically moves through multiple environments: developer workstation (local), shared development (dev), testing (staging), and production (prod). These environments may use different database URLs, HTTP ports, log levels, external service addresses, and credentials. However, **the business logic tested and released must be the exact same version**.

A risky approach is editing configuration values in source code and building a separate JAR file for each environment. Doing so makes it hard to prove that what runs in production is identical to what was tested in staging, and even a minor configuration tweak forces recompilation and repackaging.

Spring Boot solves this with **externalized configuration**: source code defines what the application does, while configuration is supplied at application startup to decide where and with what parameters the application connects and operates.

~~~text
One source code commit
       |
       v
Build + test once
       |
       v
   app.jar (single artifact)
       |
       +---- DEV config ------> runs in DEV
       |
       +---- STAGING config --> runs in STAGING
       |
       +---- PROD config -----> runs in PROD
~~~

**Principle:** *Build once, deploy many*. You can deploy the same JAR or the same Docker image to multiple environments by changing configuration at runtime.

## 2. Distinguishing Source Code, Build Artifact, and Configuration

| Component | What Does It Contain? | When Does It Change? |
| --- | --- | --- |
| **Source code** | Controllers, services, business rules, data processing | When application behavior or API contracts change |
| **Artifact** | JAR or Docker image produced from a source code version | When releasing a new application version |
| **Configuration** | Hosts, ports, endpoints, timeouts, pool sizes, appropriate feature flags, connection info | When operational conditions of an environment change |
| **Secrets** | Passwords, tokens, access keys | According to secret provisioning, rotation, and revocation policies |

For example, a service that reads orders still uses the exact same Java method in dev and prod. The difference is that **spring.datasource.url** points to two different databases; credentials are provisioned separately for each environment. There is no need to modify the controller or maintain a "production" source code branch.

Configuration can reside in packaged files to provide **non-sensitive default values**, in files outside the JAR, environment variables, Java system properties, or command-line arguments. Spring Boot combines those sources and applies precedence rules when the same property is declared in multiple places.

## 3. Spring Boot Example: Same Code, Different Configuration Values

Suppose a project uses Java 21, Spring Boot 3.x, and the **spring-boot-starter-web** dependency. We create a **GET /greeting** API to observe the configured output.

**File ConfigDemoApplication.java:**

~~~java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
~~~

**File AppProperties.java:** uses **@ConfigurationProperties** to bind a group of properties into a Java type instead of scattering key strings across multiple classes.

~~~java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(String greeting, String environmentLabel) {
}
~~~

**File GreetingController.java:**

~~~java
package com.example.configdemo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final AppProperties properties;

    public GreetingController(AppProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/greeting")
    public Map<String, String> greeting() {
        return Map.of(
            "message", properties.greeting(),
            "environment", properties.environmentLabel()
        );
    }
}
~~~

All classes reside in the same package **com.example.configdemo**. **@ConfigurationPropertiesScan** tells Spring Boot to register **AppProperties**; the controller depends only on the configuration object and does not inspect environment variables directly.

In **src/main/resources**, add three files:

**application.yml** — default configuration:

~~~yaml
server:
  port: 8080

app:
  greeting: "Hello from default configuration"
  environment-label: "default"
~~~

**application-dev.yml** — configuration for the dev profile:

~~~yaml
server:
  port: 8081

app:
  greeting: "Hello from DEV"
  environment-label: "dev"
~~~

**application-prod.yml** — configuration for the prod profile:

~~~yaml
server:
  port: 8080

app:
  greeting: "Hello from PROD"
  environment-label: "prod"
~~~

**application.yml** and the profile-specific files can all be packaged in the same JAR. What changes at runtime is the **activated profile** and configuration values coming from the deployment environment. In real projects, sensitive parameters and frequently changing parameters should be supplied from outside the artifact.

## 4. Build Once, Run in Two Environments

For a Gradle project with the Spring Boot plugin, build the JAR with:

~~~bash
./gradlew bootJar
~~~

For example, suppose the generated artifact is **build/libs/config-demo-0.0.1-SNAPSHOT.jar**. Replace this path with your project's actual JAR name; in the commands below, **do not rebuild**.

**Run 1 — run with the dev profile:**

~~~bash
java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
~~~

Call the API:

~~~bash
curl http://localhost:8081/greeting
~~~

Sample output:

~~~json
{
  "message": "Hello from DEV",
  "environment": "dev"
}
~~~

Stop this process, then **use the exact same JAR file** to run the prod profile:

~~~bash
java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=prod
~~~

~~~bash
curl http://localhost:8080/greeting
~~~

~~~json
{
  "message": "Hello from PROD",
  "environment": "prod"
}
~~~

Across both runs, the controller, configuration class, and bytecode inside the JAR do not change. Spring Boot reads **spring.profiles.active** at startup and loads the configuration matching that profile. A profile is a way to select a configuration group; it does not create a new artifact.

> In multi-environment systems, **dev**, **staging**, and **prod** are often different profiles or configuration sets, while some shared settings can still live in **application.yml**. Do not treat profiles as an excuse to rewrite business flows per environment.

## 5. Changing Configuration Outside the JAR Using Environment Variables

We do not need to edit any Java or YAML file to override the greeting in the example above. Spring Boot supports mapping property names to environment variables:

| Spring Boot Property | Environment Variable |
| --- | --- |
| **spring.profiles.active** | **SPRING_PROFILES_ACTIVE** |
| **server.port** | **SERVER_PORT** |
| **app.greeting** | **APP_GREETING** |

On Linux/macOS shells, you can run:

~~~bash
SPRING_PROFILES_ACTIVE=prod APP_GREETING="Greeting from environment variable" SERVER_PORT=8082 \
  java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar
~~~

In PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
$env:APP_GREETING = "Greeting from environment variable"
$env:SERVER_PORT = "8082"
java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar
~~~

When calling **http://localhost:8082/greeting**, the **message** attribute comes from **APP_GREETING**, while **environment** remains **prod** from **application-prod.yml**. The service port changes to **8082** because **SERVER_PORT** overrides the value in YAML. This value applies to the newly launched process; modifying shell environment variables afterward typically requires restarting the application to reload them.

Note: the environment variable syntax above is an example for the listed properties; Spring Boot's general conversion rules also handle dots, hyphens, and list indices. When introducing new keys, check the corresponding variable name according to *relaxed binding* rules.

## 6. Externalizing Configuration Files Outside the Artifact

Environment variables are convenient for containers and deployment platforms; configuration files outside the JAR are useful when you need a group of parameters. For example, an operator creates **./config/application.yml** on the target machine:

~~~yaml
app:
  greeting: "Greeting provided by deployment environment"
~~~

Start the application and specify the additional configuration location:

~~~bash
java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./config/
~~~

Spring Boot can load configuration from the additional location and use that value for **app.greeting**. The **optional:** prefix means no error is reported merely because the path does not exist; omit **optional:** when a missing file should be treated as a deployment error.

Two easily confused options:

- **spring.config.additional-location**: adds locations to search for configuration alongside the default locations.
- **spring.config.location**: declares configuration locations to replace the default set; use this when you intentionally want full control over all file sources.

Properties specifying where to look for configuration must be provided early—for example via environment variables, system properties, or startup arguments—so Spring Boot knows where to read files from.

For databases, the same JAR can receive **SPRING_DATASOURCE_URL**, **SPRING_DATASOURCE_USERNAME**, and **SPRING_DATASOURCE_PASSWORD** from each environment (when the application already has the corresponding datasource configuration and dependency). Production points to the production database; staging points to the staging database. **Never put real passwords into a committed application-prod.yml or bake secrets into a Docker image.** Supply secrets using your operational platform's secure mechanism.

## 7. When Multiple Sources Define the Same Property

Spring Boot uses configuration source precedence. For this example, you can understand it in a typical order:

1. Values in **application.yml** act as shared defaults.
2. Values in **application-prod.yml** apply when **prod** is active and can override matching keys from the default file.
3. The environment variable **APP_GREETING** can override the corresponding value in configuration files.
4. Command-line arguments such as **--app.greeting=Hello** normally have higher precedence than environment variables and YAML files.

This is **a subset** of the precedence system, not an exhaustive list of every source Spring Boot supports. Actual order also depends on file locations, source types, and how the application is initialized. When a property behaves unexpectedly, trace backward to find the source that supplied the final value instead of guessing and editing a random YAML file.

Example:

~~~bash
java -jar build/libs/config-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=prod \
  --app.greeting="Value from command line"
~~~

Even though **application-prod.yml** states **Hello from PROD**, the API response will display **Value from command line**.

## 8. Same Docker Image for Staging and Production

In container environments, the same rule holds:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/config-demo-0.0.1-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Build the image from the tested artifact:

~~~bash
docker build -t config-demo:1.0.0 .
~~~

Deploy that image to staging:

~~~bash
docker run --rm -p 8081:8080 \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e APP_GREETING="Staging" \
  config-demo:1.0.0
~~~

Then deploy **the same image** to production with configuration supplied by the production system:

~~~bash
docker run --rm -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e APP_GREETING="Production" \
  config-demo:1.0.0
~~~

Both commands use the same **config-demo:1.0.0**; only the runtime configuration values differ. In practice, use an immutable image identifier (such as an image digest) to guarantee both deployments reference the exact same contents. The Docker commands here only illustrate passing parameters; production systems require appropriate secret management, networking, and resource policies.

## 9. Common Design Mistakes

**Building separately for each environment.** When dev JARs and prod JARs are built from different configurations or code branches, test results in dev no longer accurately represent what runs in prod. Prefer one tested artifact, with environment differences supplied during deployment.

**Hard-coding endpoints, passwords, or feature flags in Java.** This forces operational changes to require code edits and new releases. For environment configuration, use properties and an appropriate secret management mechanism.

**Putting real secrets into Git or logs.** Naming a file **application-prod.yml** does not make its contents safe. Secrets can leak through repositories, images, log copies, or debug configurations. Restrict access, support rotation, and never return secrets in API responses.

**Assuming editing a configuration file updates a running process automatically.** Spring Boot normally loads configuration at startup. Changing environment variables or external files usually requires a restart/redeploy; dynamic configuration refresh requires an intentionally designed mechanism.

**Using profiles to create two different business applications.** Profiles are suitable for selecting environment-specific beans or infrastructure when necessary, but you should not turn production into an untested version of business logic. The goal of this lesson is keeping release behavior consistent.

## 10. How to Verify the "Build Once, Deploy Many" Principle

When deploying a release, you can verify it in sequence:

1. Record the commit, version, and checksum of the built JAR or the digest of the Docker image.
2. Deploy that exact artifact sequentially across environments.
3. Supply **spring.profiles.active**, dependency URLs, secrets, and operational parameters through each environment's managed configuration sources.
4. Verify that the service starts and connects to the right environment resources, for example by calling **GET /greeting** in the demo.
5. If only an endpoint or timeout changes, update the configuration and restart according to the deployment workflow; do not recompile source code.
6. If business logic changes, produce a **new artifact version**, test it, and continue through the release pipeline.

You can note the source of a property when investigating an incident, but avoid printing secret values. In production environments, do not publicly expose diagnostic endpoints that could leak configuration.

## 11. Practice Exercise

Use the demo above to verify for yourself that source code and configuration change independently:

- **Run A:** build the JAR once; run the **dev** profile and observe port **8081** and message **DEV**.
- **Run B:** stop the process; run **the same JAR** with the **prod** profile and observe port **8080** and message **PROD**.
- **Run C:** still using the old JAR; supply **APP_GREETING** and **SERVER_PORT** via environment variables; verify the API response and port changed.
- **Run D:** add **./config/application.yml** outside the JAR and run with **spring.config.additional-location**; verify the external file's contents are used.
- **Run E:** compare the JAR filename and checksum across runs. If the checksum stays unchanged while configuration behavior changes as expected, you have observed the **one build, multiple environments** property.

**Key takeaway:** the source code version determines **what the application is capable of doing**; the configuration supplied at runtime determines **how the application connects, listens, and operates**. Separating these two concerns makes deployments repeatable, keeps tested artifacts traceable, and reduces risk when promoting the same version from dev to production.
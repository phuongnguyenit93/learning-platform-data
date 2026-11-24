# Organizing Common Configuration, Environment Configuration, and Secrets

## 1. Problem and Goal

A Spring Boot application typically has to run in multiple environments: developer machines, testing environments, staging, and production. With the same source code, these environments may use different **databases**, **API endpoints**, **log levels**, **timeouts**, **performance settings**, and **credentials**.

An unseparated design might put all configuration into a single file:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://prod-db.internal:5432/shop
    username: admin
    password: "real-password"
app:
  payment:
    base-url: "https://production-payments.example.invalid"
~~~

Problems appear immediately:

- A file containing **production passwords** can easily be committed to Git or packaged into the JAR.
- Running locally requires editing the file, creating uncommitted changes or accidentally pushing local values to the repository.
- Changing endpoints per environment requires rebuilding or modifying the artifact.
- Staging and production may run two different JARs despite the same source commit, making it hard to prove that the production build is the exact build that was tested.
- It is hard to determine which file, environment variable, or configuration source the effective value comes from.
- There is no clear process for secret rotation and access control.

The organization should separate **three layers**:

1. **Common/base configuration**: values that apply to every environment or serve as non-sensitive defaults, such as application name, default timeouts, request limits, and feature names.
2. **Environment-specific configuration**: differences between local/dev/test/staging/prod, such as integration URLs, log levels, pool sizes, simulation modes, and delays.
3. **Secrets**: passwords, API tokens, private keys, database credentials, or authentication data. They are supplied at runtime from a controlled source, **not an application-prod.yml containing real secrets in Git**.

The goal is **build once, deploy many**: the exact same artifact can be deployed multiple times with appropriate configuration and secrets, without rebuilding for each environment.

This lesson uses **Spring Boot 3.3.x**, Java 21, Spring Config Data, profiles, OS environment, Docker Compose, Kubernetes ConfigMap/Secret, and **configtree:**. All URLs under **example.invalid** and sample account names are dummy data.

## 2. The Three Configuration Layers Are Three Different Kinds of Information

| Layer | Examples | Recommended source | Contains secrets? |
| --- | --- | --- | --- |
| **Common** | application name, allowed actuator endpoints, default timeouts, business limits | packaged application.yml | No |
| **Environment-specific** | non-sensitive database URL, API base URL, log level, pool size, profile | application-dev.yml, application-prod.yml, external files outside JAR, ConfigMap, env | Typically no |
| **Secrets** | password, API key, OAuth client secret, private key | Secret manager, Secret volume, controlled process env | Yes |
| **Build info** | version, commit SHA, build timestamp | Build metadata/CI | No runtime secrets |

It is important to distinguish **environment-specific configuration** from **secrets**. A database URL or hostname may be internal information whose disclosure should be restricted, but it is not automatically a credential. Conversely, **spring.datasource.password** is still a secret even if it is only used in the development environment.

Layering example:

~~~text
Common:
  spring.application.name=shop-api
  app.http.connect-timeout=2s
  app.http.read-timeout=10s

Development:
  app.payment.base-url=https://sandbox-pay.example.invalid
  logging.level.com.example.shop=DEBUG

Production:
  app.payment.base-url=https://payments.example.invalid
  logging.level.com.example.shop=INFO

Per-deployment secrets:
  spring.datasource.password
  app.payment.api-key
~~~

What matters is not only file placement, but the **ownership and lifecycle** of each value.

## 3. Recommended Directory Tree

An application can be organized as follows:

~~~text
shop-api/
├── pom.xml
├── src/
│   └── main/
│       ├── java/com/example/shop/
│       │   ├── ShopApplication.java
│       │   ├── config/ShopProperties.java
│       │   └── payment/PaymentService.java
│       └── resources/
│           ├── application.yml
│           ├── application-dev.yml
│           ├── application-staging.yml
│           └── application-prod.yml
├── deploy/
│   ├── docker-compose.yml
│   ├── k8s/
│   │   ├── configmap.yaml
│   │   └── deployment.yaml
│   └── env.example
├── .gitignore
└── README.md
~~~

**Meaning:**

- **application.yml** defines non-sensitive defaults.
- **application-dev.yml**, **application-staging.yml**, and **application-prod.yml** record *non-secret* differences per profile.
- **deploy/** contains deployment templates, ConfigMaps, and manifests referencing Secrets, but **no real secret content**.
- **env.example** only lists variable names and dummy/instructional values, with no real tokens or passwords.
- Local machine files such as **.env.local** or a **.local-secrets/** directory must not be committed.

Packaging **application-prod.yml** inside the JAR is not mandatory. An organization can keep non-sensitive production configuration in a separate operations repository and mount it at deploy time. The core point is that Spring Boot can load them **from outside the artifact**.

## 4. Common Layer: application.yml

Example **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: shop-api

server:
  port: 8080

app:
  payment:
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      max-attempts: 3
      initial-delay: 250ms

  catalog:
    default-page-size: 25

logging:
  level:
    root: INFO
~~~

These are values the application can use across many environments:

- Application name **shop-api**.
- Default port **8080**.
- Basic payment client timeouts and retry policy.
- Default pagination limit.
- Root log level INFO.

**Do not put real passwords, tokens, or private keys here.** Common values in this file may be packaged with the source and artifact; anyone with read access to the repository or JAR can view them.

### 4.1. Can common configuration include placeholders?

Yes. For example:

~~~yaml
app:
  payment:
    base-url: "${payment.base-url:https://sandbox-pay.example.invalid}"
    connect-timeout: "${payment.connect-timeout:2s}"
~~~

When Spring Boot uses the value, the **${...}** placeholder is resolved through **Environment**. Another source can supply **payment.base-url** or **payment.connect-timeout**.

However, there is no need to add another alias layer if the platform already supplies **APP_PAYMENT_BASEURL** and **APP_PAYMENT_CONNECTTIMEOUT** directly. Keep the number of public names minimal to avoid confusion.

### 4.2. Defaults do not equal production-ready

A default suitable for local runs can be dangerous in production. For example, a sandbox URL can cause a production application to send data to the wrong system if an operator forgets to override it.

For settings required in production, you can **omit a fallback** and use validation so startup fails if they are missing. This applies especially to critical endpoints, credentials, and security rules.

## 5. Environment Layer: application-{profile}.yml

Spring Boot automatically discovers profile-specific configuration files, for example:

~~~text
application.yml
application-dev.yml
application-staging.yml
application-prod.yml
~~~

If the active profile is **dev**, Spring Boot considers both **application.yml** and **application-dev.yml** in the appropriate locations. With profile-specific configuration, values in the corresponding file can **override** common values for the same key.

### 5.1. application-dev.yml

~~~yaml
app:
  payment:
    base-url: "https://sandbox-pay.example.invalid"
    request-timeout: 30s

logging:
  level:
    com.example.shop: DEBUG

spring:
  datasource:
    url: "jdbc:postgresql://localhost:5432/shop_dev"
    username: shop_dev
~~~

These are illustrative **non-secret** values. If the development database still requires a password, the password must be supplied separately. An account username is not necessarily a secret, but internal information disclosure policies should still be checked.

### 5.2. application-staging.yml

~~~yaml
app:
  payment:
    base-url: "https://staging-pay.example.invalid"
    request-timeout: 15s

logging:
  level:
    com.example.shop: INFO

spring:
  datasource:
    url: "jdbc:postgresql://staging-db.example.invalid:5432/shop"
    username: shop_app
~~~

### 5.3. application-prod.yml

~~~yaml
app:
  payment:
    base-url: "https://payments.example.invalid"
    request-timeout: 8s
    retry:
      max-attempts: 2

logging:
  level:
    root: WARN
    com.example.shop: INFO

spring:
  datasource:
    url: "jdbc:postgresql://prod-db.example.invalid:5432/shop"
    username: shop_app
~~~

There are no real password or API key fields in these profile files. Secrets are provided independently at the deployment step.

A useful change-control rule: **environment-specific configuration files can be reviewed like code**, but **secret contents must not appear in pull requests, commits, CI logs, or artifacts**.

## 6. Selecting a Profile via Runtime Sources

You can enable a profile via the command line:

~~~bash
java -jar shop-api.jar --spring.profiles.active=dev
~~~

Or production:

~~~bash
java -jar shop-api.jar --spring.profiles.active=prod
~~~

Environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar shop-api.jar
~~~

PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "staging"
java -jar shop-api.jar
~~~

Java system property:

~~~bash
java -Dspring.profiles.active=prod -jar shop-api.jar
~~~

A few notes:

- **spring.profiles.active** determines the active profiles according to source precedence rules.
- Select the profile **from the deployment environment or launch mechanism**, rather than hard-coding the production profile in Java source code.
- Spring Boot has a default profile named **default** when no specific profile is activated; this can be changed with **spring.profiles.default** in an allowed source.
- When multiple profiles are used, the order of active profiles can affect profile file precedence; in typical cases, a later profile can override an earlier one.
- **spring.profiles.active**, **spring.profiles.default**, and **spring.profiles.include** must not be declared inside a profile-specific document or a YAML document activated by **spring.config.activate.on-profile**.

### 6.1. Why not put spring.profiles.active inside application-prod.yml?

If **application-prod.yml** is only considered when the `prod` profile is active, placing:

~~~yaml
spring:
  profiles:
    active: prod
~~~

into that same file puts the decision in the wrong layer and violates Spring Boot's constraint on profile-specific configuration. Profiles must be selected from a **non-profile-specific source** or via the runtime launcher.

## 7. Precedence Order: Which Source Wins?

Naming files properly is not enough; you need to understand **PropertySource precedence**.

A high-level table for common sources:

| Source | Relative precedence |
| --- | --- |
| SpringApplication default properties | Low |
| In-JAR configuration, application.yml | Low within the Config Data group |
| In-JAR profile configuration | Higher than the common file in the JAR |
| External configuration outside JAR | Usually higher than the same type of Config Data inside the JAR |
| External profile configuration outside JAR | Usually high within the Config Data group |
| OS environment variables | Higher than Config Data in standard order |
| Java system properties | Higher than OS environment variables in standard order |
| SPRING_APPLICATION_JSON | Has its own position, higher than system properties in the standard list |
| Command-line arguments | Higher than the sources above in standard Boot configuration |

This is a **summary of typical sources**, not the complete order in Spring Boot: test properties, servlet init parameters, DevTools, and certain specialized sources have other positions.

Example:

~~~text
application.yml:           app.payment.request-timeout=10s
application-prod.yml:      app.payment.request-timeout=8s
environment:               APP_PAYMENT_REQUESTTIMEOUT=12s
command-line:              --app.payment.request-timeout=6s
------------------------------------------------------------
Illustrative result:       6s
~~~

If the command-line argument is omitted, the environment variable can determine the value as 12s.

**Key point:** you do not need to build a new JAR to change the request timeout. The same JAR runs with different runtime configuration sets.

### 7.1. Profiles do not automatically protect secrets

A file named **application-prod.yml** is not encrypted and has no secret protection just because it contains the word **prod**. If it contains a real password and is committed to Git, the password can still be exposed.

Profiles are a mechanism for **selecting a configuration group**, not a secret management system.

## 8. Secret Layer: Supplied from a Separate Source

Secrets include values such as:

- **spring.datasource.password**.
- **app.payment.api-key**.
- OAuth client secrets or private keys.
- Signing keys, encryption keys, and message broker credentials.
- Access tokens for external systems.

Basic operational requirements:

1. Do not commit real secrets to the repository.
2. Do not bake secrets into JARs, images, filtered resources, or Docker layers.
3. Supply secrets at runtime from a controlled system.
4. Restrict read permissions according to the principle of **least privilege**.
5. Do not log secret values.
6. Have procedures for **rotation**, revocation, and secret exposure incidents.
7. Separate credentials across dev, staging, and production; do not reuse a single password out of convenience.

An application can receive a password via env:

~~~bash
SPRING_DATASOURCE_PASSWORD="<provided by the deployment environment>" \
java -jar shop-api.jar --spring.profiles.active=prod
~~~

This is only a **syntax illustration**. In real workflows, avoid typing secrets directly on the command line or into shell history if the infrastructure provides a safer secret delivery mechanism.

Another option is secret files mounted by the deployment platform and loaded with **configtree:**.

### 8.1. A secret is not safe just because it is in a gitignored .env

Adding **.env** to **.gitignore** reduces the risk of accidental commits, but does not guarantee absolute secret safety. Secrets can still be exposed through:

- Terminal history and process environment.
- CI output, debug logs, and crash dumps.
- Backup files or uploaded artifacts.
- Unrestricted read permissions on the host.
- Docker image layers if **COPY** is used accidentally.
- Variables printed by diagnostic tools.
- Committed Kubernetes Secret manifests containing base64 data.

You must combine protection across Git, runtime, storage, access permissions, and the secret lifecycle.

## 9. Binding Typed Configuration with @ConfigurationProperties

Separating three source layers does not mean application code needs to know which file a property came from. Spring Boot can bind the **final effective value** into a Java object.

Example:

~~~java
package com.example.shop.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration requestTimeout,
        Retry retry,
        String apiKey) {

    public record Retry(
            int maxAttempts,
            Duration initialDelay) {
    }
}
~~~

In this class:

- **baseUrl**, **connectTimeout**, and **requestTimeout** can come from common or profile-specific Config Data.
- **retry.maxAttempts** and **retry.initialDelay** can inherit defaults or be overridden per environment.
- **apiKey** is sensitive data and must be supplied separately from a secret source.

**Do not log the entire PaymentProperties using toString()**, because the record contains `apiKey` and `toString` can print all record components. If diagnostic logging is needed, log only property names or non-sensitive fields approved for disclosure.

### 9.1. Registering the configuration bean

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

**@ConfigurationPropertiesScan** helps Boot discover types in the appropriate packages. For immutable/constructor-bound records, this is an appropriate registration method; another option is **@EnableConfigurationProperties(PaymentProperties.class)**.

Configuration is bound from **Environment**, regardless of whether the final value comes from YAML, env, CLI, or configtree. Business code does not need to build separate cases to read each file.

## 10. Validation So Missing Secrets Do Not Become Late Failures

A required secret property should not have a fallback such as **dummy** or **changeme** in production. If an operator forgets to supply the secret, the application should fail early with a message indicating **which key is missing**, without printing the value.

Example of a validated type:

~~~java
package com.example.shop.config;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentValidatedProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @NotBlank String apiKey) {
}
~~~

Gradle dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

**PaymentValidatedProperties** is an illustrative type replacing the full `PaymentProperties` from the previous section. In a real application, consolidate validation into one chosen model rather than registering multiple models with the same prefix simultaneously.

When `apiKey` is missing, the **@NotBlank** constraint can help fail startup. However, ensure exception logs do not print real secrets; avoid customizing messages in a way that concatenates entire property values into a string.

### 10.1. Profile-dependent required conditions

In development, the application might use a mock payment service and not need an API key. In production, the key is required.

Do not blindly apply **@NotBlank** unconditionally if modes have different contracts. You can:

- Separate mock/live configuration into two subsystems with appropriate beans/profiles.
- Use a class-level constraint conditioned on an **enabled** or **mode** flag.
- Write a startup guard that checks the secret when the live integration is actually enabled.

The goal is not to force every environment to use the same credentials, but to prevent production from running without required values.

## 11. Defining a Common Configuration Contract with Placeholders

A common pattern is declaring a **common configuration contract**, while values are supplied externally:

~~~yaml
app:
  payment:
    base-url: "${payment.endpoint:https://sandbox-pay.example.invalid}"
    connect-timeout: "${payment.connect-timeout:2s}"
    api-key: "${payment.api-key:}"
~~~

In this approach, **payment.endpoint**, **payment.connect-timeout**, and **payment.api-key** are alternative input keys. If `api-key` is left empty, code should validate it according to the active mode.

However, do not set an empty default and accidentally allow production to keep running without a secret. If it is a required key, you can drop the alias placeholder, bind **app.payment.api-key** directly from a secret env/configtree, and use validation.

With profiles:

~~~yaml
app:
  payment:
    base-url: "https://payments.example.invalid"
~~~

you can override the base URL from a profile file while supplying the API key from a separate source. The three layers do not have to correspond to three placeholder layers; they are **three groups of configuration responsibility**.

## 12. External Config Data Outside the JAR

Spring Boot 3.3 automatically searches for Config Data in several default locations, including packaged locations on the classpath and external locations outside the JAR such as the working directory or **config/**.

Example deployment layout:

~~~text
/opt/shop/
├── shop-api.jar
└── config/
    ├── application.yml
    └── application-prod.yml
~~~

The file **/opt/shop/config/application-prod.yml** can contain non-secret production values and is read when the **prod** profile is active.

This allows the same **shop-api.jar** artifact to operate with each environment's own non-sensitive configuration.

### 12.1. Adding locations beyond the defaults

If you want to add a directory, you can run:

~~~bash
java -jar shop-api.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./ops-config/
~~~

**spring.config.additional-location** adds locations while preserving default locations, whereas **spring.config.location** replaces the default location set according to Boot rules.

When a location is a **directory**, the trailing slash **/** matters because Spring Boot appends filenames generated from **spring.config.name** to the path.

### 12.2. Bootstrap properties must be supplied early

Keys such as:

~~~text
spring.config.name
spring.config.location
spring.config.additional-location
~~~

are used very early by Spring Boot to decide where to look for configuration. They are typically supplied via command-line arguments, OS env, or Java system properties.

Do not put **spring.config.location** inside a file that can only be discovered after that location has already been decided.

### 12.3. When to choose external files over packaged profile files?

Consider external files outside the JAR when:

- The operations team owns deployment values.
- Endpoints or timeouts change without needing a new source release.
- A single artifact is shared across multiple clusters or tenants.
- You want a separate deployment review workflow.

Consider packaged profile files when non-sensitive environment values are stable and managed alongside the source code. Both approaches are compatible with Spring Boot; what matters is not embedding secrets and understanding the precedence order.

## 13. spring.config.import for Additional Configuration

Spring Boot supports declaring Config Data imports:

~~~yaml
spring:
  config:
    import: "optional:file:./ops-config/extra.properties"
~~~

If the file exists:

~~~properties
app.payment.request-timeout=15s
app.catalog.default-page-size=40
~~~

it is imported during Config Data processing. Imported values can **override** values in the document that declared the import, according to Boot rules.

This mechanism differs from **@PropertySource** on an `@Configuration` class, which is added later during context refresh.

### 13.1. What does optional mean?

~~~text
optional:file:./ops-config/extra.properties
~~~

allows the app to continue when the location does not exist.

If that configuration is **truly required in production**, do not use **optional** just to hide deployment errors. Ensure the file is present, or apply appropriate validation/fail-fast checks.

### 13.2. Import order is not decorative

If multiple imports declare the same key, the import order and precedence affect the final value. Design only as many import layers as needed and document the override contract clearly; avoid turning `application.yml` into a deep import chain that is hard to trace.

## 14. Configtree: Reading Secrets from Mounted Files

Many cloud environments deliver secrets as **one file per key**, with the file content as the value. Spring Boot supports **configtree:** for this pattern.

Suppose the runtime mounts:

~~~text
/etc/shop-secrets/
├── spring.datasource.password
└── app.payment.api-key
~~~

Here, the **filename** is the property name to provide, and the **file content** is the actual secret. Do not put those contents into README or Git.

You can supply the import at runtime:

~~~bash
java -jar shop-api.jar \
  --spring.profiles.active=prod \
  --spring.config.import=configtree:/etc/shop-secrets/
~~~

Spring Boot uses the config tree mechanism to create properties:

~~~text
spring.datasource.password
app.payment.api-key
~~~

They can be injected via **Environment**, **@Value**, or **@ConfigurationProperties** according to standard rules.

If the directory does not exist and the location does not have **optional:**, Config Data loading may fail; this is usually the desired behavior if the secret is required. If a secret is only optional for a feature, you can use an optional import together with conditional validation.

### 14.1. Subdirectory structure creates hierarchical property names

Suppose:

~~~text
/etc/shop-secrets/
└── app/
    └── payment/
        └── api-key
~~~

with the import **configtree:/etc/shop-secrets/**, the folder/file segments are used to form a property name such as **app.payment.api-key**.

With direct file mounts like **app.payment.api-key**, dots in the filename are also recognized by Spring Boot as part of the property name.

### 14.2. Importing via application.yml

Common configuration can add:

~~~yaml
spring:
  config:
    import: "optional:configtree:/etc/shop-secrets/"
~~~

This is useful if production mounts the directory and local does not. However, if production requires the secret, using **optional** must be paired with validation/guards so the app does not run with an empty secret.

An option with clearer responsibility is **not putting the secret import in the base file**, and instead having the deployment environment supply **SPRING_CONFIG_IMPORT=configtree:/etc/shop-secrets/**. That way, the deployment platform determines the secret location.

### 14.3. Secret file permissions

Configtree does not automatically encrypt or protect files. The platform must:

- Mount them into the right container/process.
- Grant read permission to the identity running the application.
- Not grant access to containers that do not need the secret.
- Not copy the files into the image during build.
- Protect the storage system providing the secrets and access to logs/backups.

**Configtree is a data-loading mechanism**, not a Secret Manager.

## 15. Local Development: Do Not Store Real Passwords in application-dev.yml

For local environments, there are several options:

1. Use non-sensitive local database accounts or a mock database.
2. Use env supplied to the process by development tooling.
3. Use a separate gitignored file, such as **.local-secrets/**, and import it in the local startup command.
4. Use a secret manager or dev vault if provided by the organization.

Example **.gitignore**:

~~~gitignore
.env
.env.*
!.env.example
.local-secrets/
ops-config/local-only/
*.key
*.p12
~~~

This is only a **suggestion**. Do not blindly ignore all **.p12** files if the project needs to track public certificates or test fixtures. Adjust the list to match project policy.

The **.env.example** file is only a guide:

~~~dotenv
SPRING_PROFILES_ACTIVE=dev
SPRING_DATASOURCE_URL=jdbc:postgresql://localhost:5432/shop_dev
SPRING_DATASOURCE_USERNAME=shop_dev
SPRING_DATASOURCE_PASSWORD=<set-locally>
APP_PAYMENT_APIKEY=<set-locally>
~~~

**.env.example must not be treated as a directly loadable file**, because **<set-locally>** placeholders are not credentials. Developers create their own local file or use an approved secret manager.

### 15.1. .env does not automatically become Java's Environment

A file named **.env** in the repository is not always read automatically by Spring Boot. Docker Compose, an IDE, or other launch tools may use this file to supply variables, so you must understand each tool's behavior.

Do not assume "creating `.env`" means the Java process receives **SPRING_DATASOURCE_PASSWORD**. Always verify how variables are passed into the process.

## 16. Docker Compose Example Separating Configuration and Secrets

A Docker Compose example with an external PostgreSQL instance (no database service is created in this example):

~~~yaml
services:
  shop-api:
    image: example/shop-api:1.0.0
    ports:
      - "8080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      SPRING_DATASOURCE_URL: "jdbc:postgresql://db.example.invalid:5432/shop"
      SPRING_DATASOURCE_USERNAME: "shop_app"
      APP_PAYMENT_BASEURL: "https://payments.example.invalid"
      SPRING_CONFIG_IMPORT: "configtree:/run/secrets/"
    secrets:
      - source: db_password
        target: spring.datasource.password
      - source: payment_api_key
        target: app.payment.api-key

secrets:
  db_password:
    file: ./.local-secrets/db-password.txt
  payment_api_key:
    file: ./.local-secrets/payment-api-key.txt
~~~

This example illustrates Compose **secrets** with target mount filenames matching Spring Boot properties. It assumes local source files have been created outside Git and the Compose runtime supports the corresponding secret target syntax.

The secrets are mounted at:

~~~text
/run/secrets/spring.datasource.password
/run/secrets/app.payment.api-key
~~~

**configtree:/run/secrets/** makes Spring Boot receive properties by filename.

Benefits:

- The **example/shop-api:1.0.0** image contains no passwords.
- Endpoints and profiles are selected at runtime.
- Secret files are mounted into the container instead of being written into `application-prod.yml`.
- The same image can be used for staging and production when different configuration sets are supplied.

### 16.1. Do not use Docker ARG/ENV to embed secrets at build time

Example of **what not to do**:

~~~dockerfile
ARG DB_PASSWORD
ENV SPRING_DATASOURCE_PASSWORD=$DB_PASSWORD
~~~

When building an image, build-time values can end up in metadata, layers, or caches depending on the workflow and tools. Instead, supply secrets through an appropriate runtime/secret store mechanism.

### 16.2. Be careful with environment and logs

Even when secrets are only supplied at runtime, other processes with appropriate privileges or diagnostic tools may still access them. Restrict permissions, control logs, avoid dumping `Environment`, and do not expose endpoints that return config values.

## 17. Kubernetes: ConfigMap for Non-Secret Values

Kubernetes has two common resource types:

- **ConfigMap**: for **non-sensitive** configuration data.
- **Secret**: for sensitive data such as passwords, tokens, and keys.

Example ConfigMap containing no real secrets:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: shop-api-config
data:
  SPRING_PROFILES_ACTIVE: "prod"
  SPRING_DATASOURCE_URL: "jdbc:postgresql://db.example.invalid:5432/shop"
  SPRING_DATASOURCE_USERNAME: "shop_app"
  APP_PAYMENT_BASEURL: "https://payments.example.invalid"
  APP_PAYMENT_REQUESTTIMEOUT: "8s"
  LOGGING_LEVEL_ROOT: "WARN"
~~~

This resource can be reviewed and managed alongside deployment manifests depending on organizational policy.

**Do not put passwords or API keys into a ConfigMap**, because a ConfigMap does not provide security mechanisms intended for confidential data. A base64-encoded value in a ConfigMap does not become a secret either.

### 17.1. Secrets must exist separately

Suppose the namespace already has a Secret named **shop-api-credentials** with two keys:

~~~text
spring.datasource.password
app.payment.api-key
~~~

The Secret can be created via an external secrets operator, secret manager integration, or an organizationally approved provisioning workflow. There is no need to put a Secret manifest containing real passwords into the repository.

A **Kubernetes Secret** itself is not absolute encryption either: base64 data is only encoding, and the cluster must be configured with **encryption at rest**, **least-privilege RBAC**, and read restrictions scoped to the proper pods/containers.

## 18. Kubernetes: Mounting a Secret as a Config Tree

Illustrative Deployment snippet:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shop-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shop-api
  template:
    metadata:
      labels:
        app: shop-api
    spec:
      containers:
        - name: shop-api
          image: example/shop-api:1.0.0
          ports:
            - containerPort: 8080
          envFrom:
            - configMapRef:
                name: shop-api-config
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "configtree:/etc/shop-secrets/"
          volumeMounts:
            - name: app-credentials
              mountPath: /etc/shop-secrets
              readOnly: true
      volumes:
        - name: app-credentials
          secret:
            secretName: shop-api-credentials
~~~

In this example:

- **ConfigMap** provides non-sensitive environment variables.
- **Secret** is mounted as files in a volume.
- **SPRING_CONFIG_IMPORT** instructs Boot to import a config tree from the mounted path.
- Filenames **spring.datasource.password** and **app.payment.api-key** produce the exact properties needed.
- There is no need to write password/API key values in the Deployment.

This is an illustrative manifest showing **configuration separation**; it omits readiness probes, liveness probes, `securityContext`, resource limits, Service, and network policy. In production deployments, add the appropriate platform sections.

### 18.1. A Secret mount does not mean the app receives changes immediately

Kubernetes can update Secret volumes via eventual consistency. However, Spring Boot normally does not automatically rebind all **@ConfigurationProperties** beans or reopen datasource connections just because mounted file contents changed.

When rotating secrets, determine:

- Whether the secret volume/agent updates the file contents.
- Whether the application has a mechanism to reload Config Data.
- Whether connection pools or HTTP clients need to be reinitialized.
- Whether a rolling restart or a two-step rotation strategy is required.

If a Secret is supplied as an **environment variable**, a running container typically **does not automatically receive the new env** after the Secret is updated; pod replacement/restart is required.

### 18.2. Avoiding secret exposure through manifests and RBAC

Anyone permitted to read or create Pods in a namespace may be able to access Secrets through multiple paths. Protection does not stop at mounting instead of env. You need least-privilege RBAC, encryption at rest, restricted pod privileges, auditing, and backup system controls.

## 19. Kubernetes: When to Use Env Instead of a Volume?

| Delivery method | Advantages | Limitations to note |
| --- | --- | --- |
| **Secret via env** | Simple when the app already reads from environment variables | Can appear in process environment; updating the Secret does not update the running process env |
| **Secret volume** | Avoids placing secrets in env; fits key/certificate files | Requires mount and file permissions; app does not auto-refresh when files change |
| **External secret manager** | Provides centralized lifecycle/rotation and access control | Requires integration and clear error/refresh strategy |
| **ConfigMap via env** | Easy to supply non-sensitive keys | Not confidential; changing ConfigMap does not change running env |
| **ConfigMap volume** | Fits large file configuration and non-secret config trees | Must define how the app reloads or restarts |

There is no single right choice for every project. For passwords and API keys, prefer the secret source that matches your platform's control capabilities, then **let Spring Boot receive the value through a stable property key**.

## 20. Naming Rules Between YAML and Environment Variables

Suppose Java defines:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration requestTimeout,
        String apiKey) {
}
~~~

Canonical keys:

~~~text
app.payment.base-url
app.payment.request-timeout
app.payment.api-key
~~~

When converted to environment variables under Spring Boot relaxed binding:

~~~text
APP_PAYMENT_BASEURL
APP_PAYMENT_REQUESTTIMEOUT
APP_PAYMENT_APIKEY
~~~

Rules:

1. Dots **.** → underscores **_**.
2. Hyphens **-** → **removed**, not converted to underscores.
3. Letters → uppercase.

Do not assume:

~~~text
APP_PAYMENT_BASE_URL
APP_PAYMENT_REQUEST_TIMEOUT
APP_PAYMENT_API_KEY
~~~

are the canonical conversions. Some setups may accommodate variants, but documentation and manifests should use the consistent form described by Spring Boot.

**The same Java property name** can receive values from YAML or env; that is why you should define a clear, consistent namespace.

## 21. Organizing Multi-Document YAML Instead of Multiple Profile Files

Besides **application-dev.yml**, Spring Boot can use multiple YAML documents in a single file, separated by **---**:

~~~yaml
spring:
  application:
    name: shop-api

app:
  payment:
    connect-timeout: 2s

---
spring:
  config:
    activate:
      on-profile: dev

app:
  payment:
    base-url: "https://sandbox-pay.example.invalid"

---
spring:
  config:
    activate:
      on-profile: prod

app:
  payment:
    base-url: "https://payments.example.invalid"
~~~

The first document applies generally; the remaining documents are only activated when the profile condition matches.

Advantages: you can see common configuration and profile branches in one small file.

Limitations: with too many environments, the file gets long and hard to review. For complex systems, separate profile files or external configuration outside the JAR are usually easier to own.

**Do not declare spring.profiles.active inside a document that has spring.config.activate.on-profile.** Spring Boot restricts where profile activation can be declared to avoid circular configuration and unclear ordering.

### 21.1. on-cloud-platform

Besides `on-profile`, Config Data also has the condition **spring.config.activate.on-cloud-platform**. It can be appropriate when certain values only relate to a cloud platform runtime.

However, platform detection does not replace secret management, and it should not be used to implicitly enable sensitive production configuration. Production still needs a deployment mechanism that explicitly specifies the profile and secret sources.

## 22. Multiple Profiles and the Last-Wins Rule

You can enable multiple profiles:

~~~bash
java -jar shop-api.jar \
  --spring.profiles.active=prod,observability
~~~

The intent might be:

- **prod**: production environment values.
- **observability**: dedicated monitoring/logging options.

If two profile files declare the same key, Spring Boot applies precedence rules where, in the typical case, the later profile can override the earlier one.

This is useful, but also easy to make ambiguous. Do not define **spring.datasource.password** in every profile to rely on last-wins as a secret management mechanism.

### 22.1. Profile groups

Spring Boot supports **spring.profiles.group** to activate a group of related profiles, for example:

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod
        - observability
~~~

Group definitions must be placed in **non-profile-specific** configuration according to Spring Boot rules, not inside a document activated by **on-profile**.

Groups help organize behavior selection but **provide no secret protection**. Activating a profile does not make credentials appear if the secret source has not been provisioned.

## 23. Avoid Hard-Coding Environments in Java Source Code

A hard-to-maintain approach:

~~~java
String url;
if (isProduction()) {
    url = "https://payments.example.invalid";
} else {
    url = "https://sandbox-pay.example.invalid";
}
~~~

Or:

~~~java
String password = "production-password";
~~~

The right approach is usually for the **service to use a configuration object**, while values are selected via Environment/Config Data.

~~~java
package com.example.shop.payment;

import com.example.shop.config.PaymentProperties;
import java.net.URI;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final PaymentProperties properties;

    public PaymentService(PaymentProperties properties) {
        this.properties = properties;
    }

    public URI endpoint() {
        return properties.baseUrl();
    }
}
~~~

As a result:

- Code does not have to guess whether it is running in production or staging just to pick a URL.
- Tests can supply dedicated properties per test.
- No rebuild is needed when changing an endpoint.
- One artifact can run across many environments.

**Note:** you can still use **@Profile** to choose different implementations, such as a mock payment client in dev. However, selecting an implementation and supplying credentials are two separate concerns.

## 24. One Artifact for Multiple Environments

Ideal workflow:

~~~text
Source + tests
      |
      v
Build once
      |
      v
shop-api.jar / container image with a deterministic checksum
      |
      +--------------------+
      |                    |
      v                    v
Staging                Production
      |                    |
      v                    v
Staging profile         Prod profile
Staging config          Production config
Staging secret          Production secret
      |                    |
      v                    v
Same artifact, different effective configuration
~~~

Benefits:

- Staging can test the **exact same artifact bytes** that will be deployed to production.
- Rollback can redeploy a released artifact with the appropriate configuration set.
- Reduces the number of per-environment binary builds.
- Source change history and deploy config change history are controlled separately.
- Secrets do not need to be present in the JAR build pipeline, except for controlled testing needs.

### 24.1. When do environments still need different behavior?

Profiles can be used to enable certain beans or choose specific configurations. That does not contradict the build-once principle. The same binary still contains the required beans/classes and selects them per environment at runtime.

However, avoid using profiles to accidentally introduce experimental code or weakened security controls into production. Test profile behavior and specific deployment constraints thoroughly.

## 25. Updating Secrets Does Not Mean All Beans Auto-Refresh

An important question: "The secret was rotated—does Spring Boot pick it up immediately?"

There is no universal yes answer.

- **Environment** holds the PropertySources loaded during a run.
- **@ConfigurationProperties** is typically bound when the ApplicationContext creates the bean.
- Process environment variables are typically fixed when the process starts.
- Mounted secret files may be updated by the platform, but Spring Boot normally does not automatically reload all Config Data and recreate connection pools.
- Some starters/integrations support dedicated refresh mechanisms, which must be specifically configured and tested.

Therefore, rotation should follow a defined process:

1. Provision the new secret and ensure the target system accepts it.
2. Update the secret source securely.
3. Perform a rolling restart or reload the required applications using the designed mechanism.
4. Verify connections and tasks work with the new secret.
5. Revoke the old secret once all consumers have switched over.
6. Verify logs and audits do not leak values.

Do not automatically promise "when the secret volume changes, Java beans pick it up automatically" if the system does not have a refresh mechanism.

## 26. Avoid Putting Secrets into Logs, Errors, and Actuator

Spring Boot Actuator provides diagnostic endpoints such as **env** and **configprops** when the dependency and exposure are configured appropriately. These endpoints can involve sensitive configuration data.

Guidelines:

- Do not expose full diagnostic endpoints to the public Internet.
- Verify masking/sanitization mechanisms, authorization, and exposure for your exact version.
- Do not log raw `Environment` maps or **toString()** of records containing passwords or tokens.
- Do not include secrets in custom exception messages.
- Do not print secrets in CI commands or `set -x`/verbose scripts.
- Do not return secrets in health or custom debug endpoints.
- Do not post real values to issue trackers, screenshots, or chat logs.

Example of **what not to do**:

~~~java
System.out.println(paymentProperties);
~~~

if the object has an **apiKey** field.

A safer way to log:

~~~java
log.info("Payment endpoint configured: {}",
        paymentProperties.baseUrl());
~~~

Even internal URLs can be sensitive depending on policy. Only log operational information that is sufficient and free of credentials.

### 26.1. Base64 is not encryption

Kubernetes Secrets typically represent `data` in base64. Anyone who can read the value can decode it. Security comes from access controls, storage/transport protection, encryption at rest, and authorization workflows—not from base64.

## 27. Configuration Pattern Across Local, Staging, and Production

A practical operations table:

| Aspect | Local | Staging | Production |
| --- | --- | --- | --- |
| Profile | dev | staging | prod |
| Common config | Inside JAR | Inside JAR | Inside JAR |
| Specific config | application-dev.yml + local override | staging file/ConfigMap | production file/ConfigMap |
| Database URL | localhost/dev DB | staging DB | prod DB |
| Payment endpoint | Sandbox | Sandbox/staging endpoint | Production endpoint |
| Password/token | Local secret or dev credential | Staging Secret | Production Secret |
| Log level | Controlled DEBUG | INFO | INFO/WARN as needed |
| Rotation | Per dev environment | Per staging process | Per production process |
| Artifact | Same build if appropriate | Tested artifact | Approved artifact itself |

**Do not use production secrets in a local environment** just to "run like production." If realistic integration testing is needed, use dedicated test accounts and environments with minimal privileges.

## 28. Organizing Configuration Across Multiple Functional Groups

A large application might have:

~~~text
app.catalog.*
app.checkout.payment.*
app.checkout.shipping.*
app.notifications.email.*
app.integrations.crm.*
~~~

Do not lump all secrets into a single shared property:

~~~text
app.secret
~~~

because it becomes hard to tell which subsystem owns it, who is permitted to read it, and which consumers need rotation.

Secret keys can be placed under the functional namespaces themselves:

~~~text
app.checkout.payment.api-key
app.notifications.email.provider-token
app.integrations.crm.client-secret
~~~

Access permissions should be designed accordingly:

- The payment component only uses payment credentials.
- The email component only uses the provider token.
- The CRM integration only uses the relevant client secret.

If all of them run in the same process, process-level read permissions may be broad; this limitation must be understood during security design. Separating processes/services or runtime identities is sometimes necessary for strict least privilege.

### 28.1. Do not confuse property prefixes with security boundaries

**@ConfigurationProperties(prefix = "app.checkout.payment")** helps organize the Java model, but does not by itself prevent another bean from reading `Environment` or a secret file accessible to the same process. Real security boundaries must be enforced at the OS, container, service account, or secret management infrastructure level.

## 29. Changing Configuration Without Creating Uncontrolled Drift

A change management process:

1. Classify whether the value is **common**, **environment-specific**, or **secret**.
2. Choose an owner: developer, platform team, security team, or service owner.
3. Document the canonical key name and its meaning.
4. Document units, defaults, and allowed value ranges.
5. Put non-secret defaults in the code repository or an approved operations source.
6. Put environment-specific differences in profile Config Data, ConfigMap, or external files outside the JAR.
7. Supply secrets via a separate system.
8. Test in relevant environments before production.
9. Roll out in a controlled manner using appropriate health/readiness checks and metrics.
10. Track changes and maintain rollback capability for both artifact and config.
11. Never treat secret values as data that can live in pull request history.
12. Perform rotation and revocation according to process.

### 29.1. Should ConfigMaps be stored in Git?

Because ConfigMaps are intended for non-secret data, storing manifests in Git can fit GitOps well. However, internal URLs, domains, or topology details can still be organizationally sensitive. Classify and restrict repositories according to policy.

Do not commit a **Kubernetes Secret** containing real passwords in base64 and assume it is protected.

## 30. Testing Environment Configuration

You can test a group of properties using **@SpringBootTest(properties = ...)** without connecting to production.

Example type:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration requestTimeout,
        String apiKey) {
}
~~~

An integration test:

~~~java
package com.example.shop;

import com.example.shop.config.PaymentProperties;
import java.net.URI;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
    "app.payment.base-url=https://test-pay.example.invalid",
    "app.payment.connect-timeout=500ms",
    "app.payment.request-timeout=5s",
    "app.payment.api-key=test-only-placeholder"
})
class PaymentConfigurationTest {

    @Autowired
    PaymentProperties properties;

    @Test
    void bindsRuntimeConfiguration() {
        assertEquals(
                URI.create("https://test-pay.example.invalid"),
                properties.baseUrl());
        assertEquals(
                Duration.ofMillis(500),
                properties.connectTimeout());
        assertEquals(
                Duration.ofSeconds(5),
                properties.requestTimeout());
    }
}
~~~

This test assumes the project has **spring-boot-starter-test**, registers the configuration properties appropriately, and other beans do not require connecting to a real database while creating the test context. The value **test-only-placeholder** is not a real secret.

### 30.1. Tests do not mean deployed secrets are verified

A test with placeholders proves that the Java model binds. It **does not prove** that the Kubernetes Secret exists in the right namespace, is mounted at the right path, or that the process has read permissions.

Add deployment smoke tests and readiness checks to verify real secret sources in a controlled test environment without printing secret contents.

## 31. Using ApplicationContextRunner for Lightweight Configuration Tests

**ApplicationContextRunner** can create a small context and supply property values:

~~~java
package com.example.shop;

import com.example.shop.config.PaymentProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfig.class);

    @EnableConfigurationProperties(PaymentProperties.class)
    static class TestConfig {
    }

    @Test
    void usesValuesFromProvidedPropertySource() {
        runner.withPropertyValues(
                "app.payment.base-url=https://test-pay.example.invalid",
                "app.payment.connect-timeout=2s",
                "app.payment.request-timeout=10s",
                "app.payment.api-key=test-only-placeholder"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            PaymentProperties p =
                    context.getBean(PaymentProperties.class);
            assertThat(p.requestTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(10));
        });
    }
}
~~~

This type of test is useful for configuration models. You can add failure tests when a required key is missing or when a `Duration` cannot be converted.

### 31.1. Testing precedence in the right scope

An **ApplicationContextRunner** does not always simulate the full `SpringApplication` Config Data/profile loading process like a real runtime. When you need to verify the order of profile-specific files or import locations, use an integration test with actual Spring Boot startup mechanics rather than just passing properties to a minimal test context.

## 32. Common Mistakes When Separating the Three Layers

### Mistake 1: Putting passwords in application-prod.yml

**Problem:** the file is often committed or packaged; anyone with read access to Git/JAR can view the values.

**Fix:** move secrets to a Secret Manager, Kubernetes Secret/volume, protected env, or a runtime secret source with proper access policies.

### Mistake 2: Building one JAR per environment just to change URLs

**Problem:** staging may test a different artifact than production.

**Fix:** build once and supply different runtime configurations via profiles and external sources.

### Mistake 3: Thinking profiles are an encryption mechanism

**Problem:** `application-prod.yml` is a plain text file and does not protect passwords.

**Fix:** separate secrets from profile files even if profile files live in a separate repository.

### Mistake 4: Having one shared application.yml containing all production URLs

**Problem:** local/dev accidentally hits real systems or requires manual file edits.

**Fix:** keep only safe defaults, and use profile-specific config or external files outside the JAR.

### Mistake 5: Placing spring.profiles.active in application-prod.yml

**Problem:** wrong place for profile activation and violates Boot rules.

**Fix:** enable profiles from the launcher or a non-profile-specific source.

### Mistake 6: Wrong env variable name

**Problem:** writing **APP_PAYMENT_API_KEY** for canonical key **app.payment.api-key** and expecting the Binder to always interpret it like the standard form.

**Fix:** use **APP_PAYMENT_APIKEY** following the rule: dots → underscores, hyphens → removed, uppercase.

### Mistake 7: Assuming having .env means Java picks it up automatically

**Problem:** the file has not been injected into the process by a launch tool.

**Fix:** verify what variables Docker Compose, the IDE, the shell, or the secret manager integration actually pass to the process.

### Mistake 8: Using ConfigMap to store secrets

**Problem:** ConfigMap is not designed for confidential data; there is no guaranteed secrecy or encryption.

**Fix:** use a Secret or external secret store and enforce RBAC.

### Mistake 9: Assuming base64 is encryption

**Problem:** Kubernetes Secret data can be decoded by anyone with read access.

**Fix:** protect API access, enable etcd encryption at rest, use workload identity, auditing, and secret lifecycle controls.

### Mistake 10: Importing an optional secret location in production and ignoring empty results

**Problem:** the app can start without required credentials.

**Fix:** use required locations or contract-enforced validation/startup guards.

### Mistake 11: Rotating a secret file without reloading the app

**Problem:** the mount changed, but config beans or connection pools may still be using the old value.

**Fix:** design restart/reload procedures and verify consumers as well.

### Mistake 12: Logging the entire Environment

**Problem:** tokens/passwords leak into logs or debug endpoints.

**Fix:** log only key names and non-sensitive values; restrict Actuator exposure.

### Mistake 13: Confusing spring.config.location with additional-location

**Problem:** using `location` replaces and drops the default search locations.

**Fix:** choose **additional-location** when you only want to add locations.

### Mistake 14: Not understanding multi-profile overrides

**Problem:** two profiles declare the same key and the later profile can win according to profile order.

**Fix:** minimize conflicting keys, document ordering, and test actual combinations.

### Mistake 15: Thinking a secret prefix creates a security boundary

**Problem:** a process with read access to a secret source can read multiple values regardless of the annotation prefix.

**Fix:** enforce permissions at the secret store, filesystem, Pod/service account, and runtime infrastructure levels.

## 33. Hands-On Exercises

### Exercise A — Classify common, environment, and secret

Given these keys:

~~~text
spring.application.name
app.payment.connect-timeout
app.payment.base-url
spring.datasource.url
spring.datasource.password
app.payment.api-key
logging.level.com.example.shop
~~~

Classify them:

- **Common**: `spring.application.name`, `app.payment.connect-timeout` (if all environments share the same default).
- **Environment-specific**: `app.payment.base-url`, datasource URL, logging level.
- **Secret**: datasource password, payment API key.

Discussion: should internal usernames or endpoints be restricted from disclosure? Classifying something as "not a password" does not automatically mean it can be made public.

### Exercise B — Create common and profile configuration

1. Create **application.yml** with timeouts, application name, and page size.
2. Create **application-dev.yml** using a sandbox endpoint.
3. Create **application-prod.yml** using a non-sensitive production endpoint.
4. Run the same JAR with **--spring.profiles.active=dev** and **prod**.
5. Call a demo endpoint that only displays dummy URLs and non-sensitive timeouts.

**Goal:** observe one artifact using multiple sets of Config Data.

### Exercise C — Supply a secret from environment

1. Add the **app.payment.api-key** property to the Java configuration model.
2. Do not write the secret in source code.
3. Supply **APP_PAYMENT_APIKEY** via an allowed runtime mechanism (use a dummy token for the exercise).
4. Test omitting the key when the feature requires it.
5. Verify that validation/startup guard rejects the missing configuration.

**Goal:** separate secrets from the JAR and validate them when required.

### Exercise D — configtree from a local directory

1. Create a **.local-secrets/** directory untracked by Git.
2. Create a file **app.payment.api-key** containing a dummy test string.
3. Run with **--spring.config.import=configtree:./.local-secrets/** (if the runtime environment's location resolution supports it; an appropriate absolute file path can be used).
4. Bind the value into the configuration object without printing the secret.
5. Delete or temporarily move the file and observe failure behavior.

**Goal:** see how a mounted file maps to a Spring property.

### Exercise E — Kubernetes configuration

1. Create a ConfigMap with profile, datasource URL, and non-secret settings.
2. Prepare a Secret through the cluster's test process without committing real values.
3. Mount the Secret to **/etc/shop-secrets/**.
4. Supply **SPRING_CONFIG_IMPORT=configtree:/etc/shop-secrets/**.
5. Verify the app starts and the health endpoint responds without exposing secrets.

**Goal:** separate configuration and permissions at the runtime platform level.

### Exercise F — Experiment with overrides and precedence

1. In the base file, set **app.payment.request-timeout=10s**.
2. In the prod file, set **8s**.
3. Supply env **APP_PAYMENT_REQUESTTIMEOUT=12s**.
4. Run with argument **--app.payment.request-timeout=6s**.
5. Observe the final value.
6. Remove each source one by one to understand the role of precedence.

**Goal:** distinguish between a value "in a file" and the effective value when the app runs.

### Exercise G — Practice rotation

1. Supply a dummy secret **version-A**.
2. Start the application in a test environment.
3. Change the secret source to **version-B**.
4. Check whether the running process actually sees the new version.
5. Perform a rolling restart if the architecture requires it.
6. Verify functionality works with the new version, then revoke the old version in the test setup.

**Goal:** understand that rotation is not just editing a secret file.

## 34. Pre-Deployment Checklist

- Is the artifact built once and reused across environments?
- Are common properties genuinely non-sensitive and safe to package?
- Do profile files only contain non-secret environment differences?
- Is the production profile selected by an appropriate launcher/source?
- Are there any real passwords, tokens, or private keys in Git, the JAR, or the Docker image?
- Does the secret source have the right namespace, mount path, filename, and property prefix?
- If using `configtree`, do filenames match canonical keys?
- If using env, do variable names follow relaxed binding rules?
- Do required secrets have validation/fail-fast checks?
- Is `optional` import misused in production?
- Does any ConfigMap accidentally contain secret data?
- Do the secret store/Kubernetes have least-privilege RBAC and encryption at rest configured?
- Are containers that do not need secrets prevented from reading them?
- Do logs, Actuator, or debug endpoints leak values?
- Do file/Secret changes require a restart or refresh?
- Is there a plan for rotating and revoking old secrets?
- Do you know which source and profile each final property comes from?
- Was staging configuration tested before rolling out to production?
- Does operations have rollback instructions for both the artifact and configuration?
- Do configuration sources have clear owners, change logs, and modification permissions?

## 35. Conclusion

A deployable and secure Spring Boot configuration architecture should separate **common values**, **environment differences**, and **secrets**:

- **application.yml** holds non-secret common defaults and conventions.
- **application-{profile}.yml** or external Config Data outside the JAR holds environment-specific values.
- **Secret managers**, Kubernetes Secrets, runtime env, or volumes/configtree supply dedicated passwords/tokens/keys.
- Spring Boot combines sources into `Environment` according to **precedence rules**, then binds them to **@ConfigurationProperties**.
- Profiles select configuration sets; they **do not encrypt secrets**.
- ConfigMaps suit non-secret data; Secrets are for sensitive data, though they still require access controls and storage encryption.
- **configtree:** is a key-based file-reading mechanism, not a replacement for secret management policies.
- A JAR/image should be built once and deployed across multiple environments using different runtime config sets.
- Secret rotation and runtime changes require clear reload/restart, verification, and revocation procedures.
- Treat configuration as an **operational contract** with canonical names, owners, validation, testing, documentation, and auditing.

## Official References

- Spring Boot 3.3 — Externalized Configuration, *PropertySource Order*, *Config Data*, *Profile Specific Files*, *Using Configuration Trees*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Kubernetes — ConfigMaps: https://kubernetes.io/docs/concepts/configuration/configmap/
- Kubernetes — Secrets: https://kubernetes.io/docs/concepts/configuration/secret/
- Kubernetes — Good Practices for Kubernetes Secrets: https://kubernetes.io/docs/concepts/security/secrets-good-practices/

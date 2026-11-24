# Supplying Secrets via Environment Variables or Process-Mounted Files in Spring Boot

## 1. The problem: configuration must vary, but secrets must not be packaged with the application

A Spring Boot service often needs to connect to a database, send requests to partner systems, or sign messages with a secret key. Values that need to be supplied to the application can include:

- Database connection passwords.
- External service API tokens.
- Client secrets for OAuth2.
- Authentication strings for message brokers.
- TLS certificates and private keys.
- Encryption keys issued by a secret management system.

These values share one requirement: **the application must be able to access them when running, yet real secrets should not reside in source code, committed configuration files, container images, or logs**.

Example to avoid:

~~~yaml
# DO NOT do this in a repository containing real secrets:
spring:
  datasource:
    url: jdbc:postgresql://db.example.test:5432/orders
    username: orders_user
    password: real-secret-in-source
~~~

If the file enters Git, build artifacts, Docker images, or backups, the value can spread much further than intended. Removing the line in a new commit does not remove it from Git history, build caches, or other people's copies.

A safer direction is to let code and regular configuration hold **key names**, while secret values are supplied by the runtime environment.

In Spring Boot, two common approaches are:

1. **Environment variables:** the runtime platform injects a variable such as `SPRING_DATASOURCE_PASSWORD` into the process environment. Spring Boot reads it through `Environment`.
2. **Process-mounted files (mounted secret files/volumes):** the platform provides a read-only-permitted file at a path such as `/run/secrets/db.password`. Spring Boot can load a directory of files as properties via `spring.config.import=configtree:/run/secrets/`, or the application can read the file directly when needed.

Both approaches help **separate secrets from code/images**. However, **neither makes secrets completely secure on its own**. Process permissions, container configuration, file read permissions, logging practices, secret sources, lifetimes, and rotation mechanisms still determine the actual level of protection.

## 2. Background: Externalized Configuration and Environment

Spring Boot supports *externalized configuration*: the same artifact can use different configuration values when deployed to different environments.

Common sources:

~~~text
application.properties / application.yaml
profile-specific Config Data
external Config Data
OS environment variables
Java System properties
command-line arguments
certain PropertySources added by platforms or libraries
~~~

Sources are loaded into Spring's property resolution system, commonly referred to as `Environment` or prioritized `PropertySource`s.

Code example:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CredentialLookup {

    private final Environment environment;

    public CredentialLookup(Environment environment) {
        this.environment = environment;
    }

    public boolean hasDatabasePassword() {
        String value =
                environment.getProperty("spring.datasource.password");

        // Do not log the value.
        return value != null && !value.isBlank();
    }
}
~~~

The key name the application needs is:

~~~text
spring.datasource.password
~~~

Yet the value can be supplied by an environment variable:

~~~text
SPRING_DATASOURCE_PASSWORD
~~~

or by a file in a configuration tree named:

~~~text
spring.datasource.password
~~~

The key point: code reads the **logical property name**, without necessarily knowing which file the data came from.

### Conceptual flow

~~~text
             Deployment platform
                    |
        +-----------+-----------+
        |                       |
        v                       v
OS environment variable  Secret volume mount
SPRING_DATASOURCE_       /run/secrets/
PASSWORD                spring.datasource.password
        |                       |
        |                spring.config.import
        |                    configtree:
        |                       |
        +-----------+-----------+
                    |
                    v
         Spring Environment
          PropertySources
                    |
                    v
      spring.datasource.password
                    |
                    v
     DataSource or configuration bean
~~~

Spring Boot **does not provide a full secret lifecycle management system via Environment alone**. It receives values; creating, authorizing, storing, revoking, updating, and auditing secrets belong to the deployment platform and operational policies.

## 3. Secrets must not be confused with regular configuration

Regular configuration example:

~~~yaml
spring:
  application:
    name: order-service
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app

app:
  request-timeout: 15s
  retry-count: 3
~~~

The parameters above can be version-controlled according to system policy. Passwords or tokens, on the other hand, should be supplied independently:

~~~text
spring.datasource.password = <secret supplied at runtime>
~~~

An `application.yaml` file can describe **how to load secrets** without containing **secret values**. For example:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

This is path configuration, not a password.

However, even **secret paths**, partner names, or key names can sometimes reveal infrastructure details. Do not indiscriminately log all configuration just because secret values have been separated out.

## 4. Option A: supplying secrets via environment variables

A simple approach: the operating system/container runtime passes environment variables to the Spring Boot process before the application starts.

Canonical property name:

~~~text
spring.datasource.password
~~~

Corresponding environment variable name:

~~~text
SPRING_DATASOURCE_PASSWORD
~~~

In Spring Boot, environment variables are treated as a configuration source that supports matching naming rules, so data in this variable can be used for `spring.datasource.password`.

If you already configured the URL and username in `application.yaml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    # Does not contain real password
~~~

then the password can come from `SPRING_DATASOURCE_PASSWORD` without being redeclared in YAML.

### 4.1. How Spring Boot reads it

When the application starts:

1. The runtime creates the process with the supplied set of environment variables.
2. Spring Boot builds `Environment` with the system environment property source.
3. Database connection configuration reads `spring.datasource.password` from the appropriate sources.
4. The value from the environment variable can be used without a literal password line in `application.yaml`.

A service can also read via `Environment` or `@ConfigurationProperties`:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.auth")
public record PartnerAuthProperties(
        String clientId,
        String clientSecret) {
}
~~~

Corresponding to canonical names:

~~~text
partner.auth.client-id
partner.auth.client-secret
~~~

If using environment variables following canonical rules:

~~~text
PARTNER_AUTH_CLIENTID
PARTNER_AUTH_CLIENTSECRET
~~~

In Java, the record class uses `clientId` and `clientSecret`. This is a result of relaxed binding; you do not need to rename Java fields to uppercase with underscores.

Register the class with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(PartnerAuthProperties.class)` if you want to inject the bean into services.

### 4.2. Environment variable renaming rules

According to Spring Boot rules for binding from the OS environment:

1. Dots `.` in the canonical name → `_`.
2. Hyphens `-` → removed.
3. Convert to uppercase.

Examples:

| Canonical property name | Environment variable |
| --- | --- |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `partner.auth.client-secret` | `PARTNER_AUTH_CLIENTSECRET` |
| `mail.smtp.api-key` | `MAIL_SMTP_APIKEY` |
| `app.payment.signing-key` | `APP_PAYMENT_SIGNINGKEY` |
| `security.jwt.private-key` | `SECURITY_JWT_PRIVATEKEY` |

Do not assume every hyphen can arbitrarily be turned into an underscore. For example, `partner.auth.client-secret` has the standard variable name `PARTNER_AUTH_CLIENTSECRET` per the rules above, not automatically `PARTNER_AUTH_CLIENT_SECRET`.

### 4.3. Local illustration on a Unix-style shell

With harmless test data, you can run:

~~~bash
export SPRING_DATASOURCE_PASSWORD='DEMO_ONLY_NOT_A_REAL_PASSWORD'
java -jar order-service.jar
unset SPRING_DATASOURCE_PASSWORD
~~~

**This is only a syntax illustration.** With real secrets, do not type values directly into commands saved in shell history, version-controlled scripts, or CI/CD logs.

If you must enter one interactively in a test environment you control, you can read it without echoing characters:

~~~bash
read -r -s -p "Database password: " SPRING_DATASOURCE_PASSWORD
printf '\n'
export SPRING_DATASOURCE_PASSWORD
java -jar order-service.jar
unset SPRING_DATASOURCE_PASSWORD
~~~

This only avoids displaying the password while typing; it **does not guarantee the secret will not appear in memory, child process environments, snapshots, or other diagnostic tools**. In production, let a secret manager, orchestrator, or pipeline with proper secret masking supply variables to the process.

### 4.4. Windows and development environments

On Windows PowerShell, a child process can receive an environment variable supplied via `$env:SPRING_DATASOURCE_PASSWORD`. However, setting a real secret literal in a terminal or script command also carries the risk of being saved.

In an IDE, the "Environment variables" field is often used to supply configuration when running locally. Do not commit run configurations containing secrets, do not share screenshots showing values, and do not put secrets into demo videos.

Syntax and storage mechanisms differ across PowerShell, Bash, Docker, or CI; the general principle remains **supply only at runtime and avoid placing real values in public documentation**.

## 5. Advantages and limitations of environment variables

### Advantages

- Very widespread: supported by most operating systems, orchestrators, and CI systems.
- No need to modify the application artifact when deploying to another environment.
- Spring Boot automatically recognizes matching property names.
- Convenient for a small number of text-based values.
- Easy to integrate with secret-provisioning mechanisms in Kubernetes, container runtimes, or PaaS platforms.

### Limitations

- Environment variables **are not an encrypted secret container** inside the process itself.
- Diagnostic tools, crash reports, process inspection, or improper config logging can expose values.
- Child processes can inherit environment variables if uncontrolled.
- People with appropriate access to the container/host/runtime can read the environment.
- Difficult to use for long binary data or multiline private keys.
- Changing a secret in the management system does not automatically update the environment of a **running process**; recreating/restarting the process is usually needed.
- Some deployment tools can show environments in metadata or admin consoles if permissions are poorly configured.

**Conclusion:** environment variables are easy to operate, but should not be treated as completely secure just because they are not in `application.yaml`.

### Avoid passing secrets as command-line arguments

Example to avoid with real secrets:

~~~bash
java -jar app.jar --spring.datasource.password=REAL_SECRET
~~~

Process arguments can appear in process lists, launcher logs, scripts, or monitoring systems. In Spring Boot, the CLI is also a property source, but a source working technically **does not mean** it is security-appropriate for passwords/tokens.

Also be cautious when using:

~~~bash
java -Dspring.datasource.password=REAL_SECRET -jar app.jar
~~~

Java System properties can be exposed by diagnostic tools or JVM management. For real secrets, prefer the runtime's secret-provisioning channel.

## 6. Option B: mounting secret files into the container/process

Many platforms allow supplying a secret as a file instead of an environment variable.

Example structure inside a container:

~~~text
/run/secrets/
├── spring.datasource.password
├── partner.auth.client-secret
└── mail.smtp.api-key
~~~

Each file contains the **value** of one property. The filename becomes the **key name** when Spring Boot loads this directory as a *configuration tree*.

Illustration of the relationship, without showing real content:

~~~text
/run/secrets/spring.datasource.password
        |
        +-- filename -> spring.datasource.password
        +-- content  -> secret password value
~~~

Because the file lives outside the JAR and is usually mounted by the container runtime/orchestrator at deployment time, the application artifact does not need to contain those values.

### 6.1. Filenames and directories are part of the key

Spring Boot allows dots in filenames.

~~~text
/run/secrets/
    db.password
~~~

when imported properly produces the property:

~~~text
db.password
~~~

Nested directory structures are also valid:

~~~text
/etc/config/
└── myapp/
    ├── username
    └── password
~~~

Importing `configtree:/etc/config/` provides:

~~~text
myapp.username
myapp.password
~~~

While importing `configtree:/etc/config/myapp/` provides:

~~~text
username
password
~~~

Therefore, you must **check the imported root directory**; do not assume key names are automatically identical in both approaches.

## 7. What is the `spring.config.import=configtree:` mechanism?

When a directory contains **multiple files, each file being a key-value pair**, Spring Boot uses the `configtree:` location prefix to know it should load them as a set of properties.

`application.properties` example:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Or `application.yaml`:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

When Spring Boot starts, it inspects the corresponding directory, turns file contents into properties, and allows accessing them via `Environment`, `@Value`, `@ConfigurationProperties`, or related Spring Boot mechanisms.

### 7.1. `configtree:` differs from `file:`

If the path is **a complete YAML file**:

~~~text
/etc/secrets/credentials.yaml
~~~

an import example would be:

~~~properties
spring.config.import=file:/etc/secrets/credentials.yaml
~~~

If the path is **a directory with one file per secret**:

~~~text
/run/secrets/db.password
/run/secrets/partner.auth.client-secret
~~~

then use:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

**Do not use `configtree:` expecting a YAML file's contents to be parsed into multiple fields.** A configuration tree reads keys from path names and values from file contents, whereas YAML import parses YAML syntax structure.

### 7.2. `optional:` does not mean the secret is optional in business logic

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

`optional:` allows the application to proceed past the Config Data loading step if the specified location does not exist. However, a production system may still **require** a password or token to be present.

For example, in an application deployed across multiple environments:

- Local: `/run/secrets/` is not mounted; a separately configured test database system may be used.
- Production: `/run/secrets/` is mounted and `db.password` must have a value.

If the secret is truly required for core functionality to run, you can:

- Omit `optional:` in that environment's configuration to detect a missing directory early.
- Use `@Validated` / `@NotBlank` or an explicit check to detect **empty or missing files/keys**.
- Configure the platform not to start the workload if a required Secret is absent.

**Having the directory does not mean having the right files/keys.** An empty directory or misnamed file can prevent the import from creating the needed property, even when the directory exists.

### 7.3. Which file should the import go in?

`spring.config.import` is processed during Config Data loading. It can be placed inside the packaged `application.yaml` or in a configuration file outside the JAR. Paths starting with `configtree:` and absolute paths are handled according to Spring Boot's location mechanism.

For Linux containers, using absolute paths such as `/run/secrets/` or `/etc/secrets/` is usually more predictable than relative paths affected by the working directory.

## 8. Complete example: supplying a database password from a mounted file

Suppose the application has `application.yaml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
  config:
    import: "configtree:/run/secrets/"
~~~

At runtime, the file exists:

~~~text
/run/secrets/spring.datasource.password
~~~

The file content is the password supplied by the platform, **not located in the image or Git repository**.

When the application starts, the configuration tree creates the property:

~~~text
spring.datasource.password
~~~

Spring Boot DataSource configuration can use it like any regular property.

### 8.1. Benefit of matching the filename to the property

You do not need to write code:

~~~java
Files.readString(
        Path.of("/run/secrets/spring.datasource.password"));
~~~

just to pass the password into the DataSource. Spring Boot already has a mechanism to receive values via `Environment`.

The file path itself can vary across different platforms; the application only needs to declare the correct import directory and keep the logical key names stable.

### 8.2. If the file is only named `password`

Suppose the directory is:

~~~text
/run/secrets/
└── password
~~~

With import root `configtree:/run/secrets/`, the logical key is `password`; it **does not automatically become `spring.datasource.password`**.

There are two approaches:

1. Rename the file in the mount to `spring.datasource.password`.
2. Keep the key `password` and declare an alias property reference:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  datasource:
    password: "${password}"
~~~

If the `password` key exists in Environment, the placeholder can be resolved. However, the name `password` is too generic and prone to collisions; in systems with multiple secrets, use clear namespaces.

### 8.3. A clearer alias

Mount:

~~~text
/run/secrets/db.password
~~~

Declare:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    password: "${db.password}"
~~~

Here:

- The file `db.password` creates the property `db.password`.
- `spring.datasource.password` references that value.
- There is no literal secret in the YAML.

This fits well when you want to keep filenames consistent with platform-managed secrets, yet a framework or library requires a different property name.

## 9. Example with @ConfigurationProperties and configuration validation

If an application module uses its own credentials, you can define:

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "partner.auth")
public record PartnerCredentials(

        @NotBlank String clientId,

        @NotBlank String clientSecret) {
}
~~~

Registration:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

In an environment supplying secrets via environment variables:

~~~text
PARTNER_AUTH_CLIENTID     = <value supplied by platform>
PARTNER_AUTH_CLIENTSECRET = <value supplied by platform>
~~~

In another environment, you can mount:

~~~text
/run/secrets/partner.auth.client-id
/run/secrets/partner.auth.client-secret
~~~

and load using:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

In both cases, the service can receive the exact same bean:

~~~java
package com.example.demo.service;

import com.example.demo.config.PartnerCredentials;
import org.springframework.stereotype.Service;

@Service
public class PartnerService {

    private final PartnerCredentials credentials;

    public PartnerService(PartnerCredentials credentials) {
        this.credentials = credentials;
    }

    public boolean hasCredentials() {
        return !credentials.clientId().isBlank()
                && !credentials.clientSecret().isBlank();
    }
}
~~~

**Do not log the entire `PartnerCredentials` record.** Java records generate `toString()`, which can print the values of all members, including `clientSecret`. If a status message is needed, output only property names or masked booleans.

### Why is @NotBlank important?

Loading the directory does not prove each file has content. An empty file or misnamed key can lead to a missing/empty String.

`@NotBlank` helps detect missing required data when the bean is bound and validation is enabled. The project needs a Jakarta Bean Validation provider, usually via `spring-boot-starter-validation`, for the constraint to be enforced.

A production application should not silently fall back to a public default credential when secret data is missing.

## 10. Docker Compose Secrets: mounting files without environment values

Docker Compose supports declaring top-level secrets and granting them only to listed services. In Linux container environments, secrets are mounted as files under `/run/secrets/`.

Compose example:

~~~yaml
services:
  order-service:
    image: example/order-service:1.0.0
    environment:
      SPRING_CONFIG_IMPORT: "configtree:/run/secrets/"
      PARTNER_AUTH_CLIENTID: "DEMO_CLIENT_ID"
    secrets:
      - source: partner_client_secret
        target: partner.auth.client-secret

secrets:
  partner_client_secret:
    file: ./secrets/partner-client-secret.txt
~~~

Inside the container:

~~~text
/run/secrets/partner.auth.client-secret
~~~

Spring Boot reads the file as the property:

~~~text
partner.auth.client-secret
~~~

and can combine it with:

~~~text
PARTNER_AUTH_CLIENTID
~~~

to bind `PartnerCredentials`.

### Paths in Compose

- `secrets.partner_client_secret.file` is the source file Compose uses during deployment.
- `services.order-service.secrets` grants secret access exclusively to the service.
- `target` determines the filename mounted inside the container.
- `SPRING_CONFIG_IMPORT` tells Spring Boot where to load the configuration tree.

The actual value does not appear in the example Compose YAML; it resides in the secret source file and must be protected by file/directory permissions, CI policies, and secret management.

### Warning about the source file

If using:

~~~yaml
file: ./secrets/partner-client-secret.txt
~~~

do not commit this file to the repository. A relative path on a developer machine is not a secure secret store by default. For production, prefer a platform-managed secret source with access control and provisioning/revocation workflows.

### _FILE is a convention, not a universal capability

Some Docker Official Images support variables like:

~~~text
MYSQL_PASSWORD_FILE=/run/secrets/db_password
~~~

That is a **convention of a specific image/entrypoint**. Do not assume Spring Boot automatically reads every variable ending in `_FILE` and converts the corresponding file into a property.

For example:

~~~text
SPRING_DATASOURCE_PASSWORD_FILE=/run/secrets/db_password
~~~

is not automatically interpreted by Spring Boot as an instruction to "read the file and use its content as the password" just because the name ends in `_FILE`.

If you want to use files in Spring Boot, use `configtree:` with matching file/property names, or write intentional file-reading logic with proper permission controls.

## 11. Kubernetes: supplying secrets via environment variables

Kubernetes has a `Secret` object and a `secretKeyRef` mechanism to supply a key into a container's environment.

Illustrative Pod fragment:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-service
spec:
  containers:
    - name: app
      image: example/order-service:1.0.0
      env:
        - name: SPRING_DATASOURCE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: order-db-credentials
              key: password
~~~

Here:

1. Kubernetes looks up the Secret object named `order-db-credentials` in the appropriate namespace.
2. Takes the `password` key from the Secret.
3. Supplies the content as the `SPRING_DATASOURCE_PASSWORD` environment variable to the container.
4. Spring Boot reads the `spring.datasource.password` property from the environment.

The secret value **is not written literally in the Pod spec**.

### The Secret must be prepared beforehand

Kubernetes requires the Secret object to exist and contain the matching key, unless the resource is marked optional via the corresponding mechanism. When a required Secret is missing, the Pod may fail to start; the failure is reported in the Pod's status or events.

**Do not put a Secret manifest with real values into Git.** Both Kubernetes `stringData` and `data` (base64) carry risk if the file is shared; **base64 only encodes representation, not encryption**. A secret manager/external-secrets workflow or secure provisioning channel is a better choice for production values.

### Variable naming rules inside containers

Kubernetes has restrictions on environment variable names supplied to containers. If a Secret key contains dots or characters invalid for the deployment environment, you can choose a valid variable name in `env.name` and reference the actual key in `secretKeyRef.key`.

For example, the Secret key can be named `spring.datasource.password`, while the environment name should use `SPRING_DATASOURCE_PASSWORD`.

## 12. Kubernetes: mounting a Secret as a volume file

Kubernetes can also mount a Secret as a volume. Pod fragment example:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-service
spec:
  containers:
    - name: app
      image: example/order-service:1.0.0
      env:
        - name: SPRING_CONFIG_IMPORT
          value: "configtree:/etc/secrets/"
      volumeMounts:
        - name: db-credentials
          mountPath: /etc/secrets
          readOnly: true
  volumes:
    - name: db-credentials
      secret:
        secretName: order-db-credentials
        items:
          - key: password
            path: spring.datasource.password
        defaultMode: 0400
~~~

Expected result inside the container:

~~~text
/etc/secrets/spring.datasource.password
~~~

And Spring Boot imports the directory:

~~~text
configtree:/etc/secrets/
~~~

to obtain the property:

~~~text
spring.datasource.password
~~~

### Components to understand

- `volumes[].secret.secretName` selects the source Secret.
- `items[].key` selects the key in the Kubernetes Secret.
- `items[].path` sets the file path created inside the mount.
- `volumeMounts[].mountPath` specifies the mount location inside the container.
- `volumeMounts[].readOnly` expresses the read-only intent for the application.
- `defaultMode: 0400` sets POSIX file permissions in compatible environments (owner read-only).

### Note on `0400` permissions

A file with `0400` permissions is readable only by the owner, so **the actual owner and the user the container runs as must be compatible**. If the workload runs as non-root while the secret file lacks appropriate ownership or group permissions, the application may encounter an `AccessDeniedException` even though the file is mounted.

You must design `runAsUser`, `runAsGroup`, `fsGroup`, or the corresponding permission mechanism for your real environment. Do not open permissions on all secrets to `0777` just to "fix" file-read errors.

Exact permission configuration can vary by runtime, driver, and volume type. Verify on the actual cluster following the principle of least privilege.

## 13. Kubernetes Secrets do not guarantee full encryption and authorization

The Kubernetes `Secret` object integrates with workloads, but does not automatically solve all security issues.

Things to implement at the cluster/platform level:

- **Encryption at rest** for Secret data in the control plane datastore when required.
- **Least-privilege RBAC** so only necessary identities have permission to read Secrets.
- Restrict permission to create Pods/Deployments or run debug containers in namespaces with sensitive secrets.
- Do not casually dump Secrets with `kubectl get secret -o yaml` into logs, tickets, or recorded terminals.
- Consider external secret stores/CSI drivers when infrastructure requires centralized lifecycle management.
- Reduce the number of services receiving the same Secret; split by functional scope.
- Attach rotation schedules, auditing, and revocation processes.

**Base64 is not security encryption.** Values in the `data` field of a Kubernetes Secret can be decoded by anyone with access to the object. Primary protection lies in access control, encryption at rest/in transit, key management, and operational controls.

## 14. Configuration tree: filename is key, file content is value

The `configtree:` feature has technical details to keep in mind.

### 14.1. Filenames with dots

~~~text
/etc/config/
└── service.auth.client-secret
~~~

Import:

~~~properties
spring.config.import=optional:configtree:/etc/config/
~~~

produces the property:

~~~text
service.auth.client-secret
~~~

### 14.2. Nested directories

~~~text
/etc/config/
└── service/
    └── auth/
        └── client-secret
~~~

Importing `configtree:/etc/config/` can also produce the logical property path:

~~~text
service.auth.client-secret
~~~

### 14.3. Changing the import root changes the key

If you import:

~~~properties
spring.config.import=configtree:/etc/config/service/
~~~

then the file in the branch:

~~~text
auth/client-secret
~~~

becomes the logical name:

~~~text
auth.client-secret
~~~

not `service.auth.client-secret`. Choose an import root consistent with the key names the application expects to read.

### 14.4. Multiple configuration trees and wildcards

Suppose:

~~~text
/etc/config/
├── database/
│   └── db/
│       └── password
└── messaging/
    └── mq/
        └── password
~~~

Spring Boot supports wildcard syntax at the immediate subdirectory level under a parent:

~~~properties
spring.config.import=optional:configtree:/etc/config/*/
~~~

The keys can be:

~~~text
db.password
mq.password
~~~

Wildcard directories are processed in name order; if an explicit precedence order is needed, list each import location explicitly. Avoid placing multiple secrets with the same key name across multiple trees without deciding which source takes precedence.

### 14.5. Strings and byte[]

Configuration trees can bind to `String` or `byte[]` according to the target type and Spring Boot's conversion capabilities. This is useful for data that is not simple plain text.

However, do not treat the ability to bind `byte[]` as meaning every certificate/private key should be handled as a String. For binary keys or certificates, choose safe APIs and formats for the consuming library, check encoding, and limit copies of sensitive data in memory.

## 15. Importing a complete YAML file vs. multiple secret files

A platform can mount **a single file containing multiple properties**:

~~~text
/etc/secrets/secure-config.yaml
~~~

Example file in YAML syntax:

~~~yaml
partner:
  auth:
    client-id: DEMO_ID_ONLY
    client-secret: DEMO_SECRET_ONLY
~~~

If the YAML file source sits outside the artifact and is mounted with appropriate permissions, it can be imported as config data:

~~~properties
spring.config.import=file:/etc/secrets/secure-config.yaml
~~~

And if the file has no extension:

~~~text
/etc/secrets/secure-config
~~~

you can provide an extension hint:

~~~properties
spring.config.import=file:/etc/secrets/secure-config[.yaml]
~~~

Spring Boot understands that the extensionless file carries YAML syntax.

### Comparison

| Case | Format | Import syntax |
| --- | --- | --- |
| A YAML file containing multiple keys | YAML structure | `file:/etc/secrets/secure-config.yaml` |
| An extensionless file containing YAML | YAML, without extension | `file:/etc/secrets/secure-config[.yaml]` |
| A directory where each file is one value | Configuration tree | `configtree:/run/secrets/` |
| Value directly in process environment | OS environment variable | No `spring.config.import` needed |

Do not use `configtree:` simply because "the file contains secrets." Choose the loading method that matches **how the platform presents the data**.

## 16. Precedence order: secrets can be overridden by other sources

Spring Boot merges configuration values according to `PropertySource` order. In standard configurations, environment variables have higher precedence than Config Data loaded from `application.yaml` or `configtree:`; command-line properties can take precedence over environment variables.

Example:

~~~text
Config tree:
    /run/secrets/spring.datasource.password
    -> property: spring.datasource.password

Environment:
    SPRING_DATASOURCE_PASSWORD=another-value
~~~

In the default property source ordering, the environment variable can be the final value used instead of the mounted file's contents.

This is **very important when handling secrets**:

- A source existing does not mean that source is being used.
- Mounting a file correctly does not prove the DataSource took its password from that file.
- A leftover old environment variable can cause the application to keep using an old credential.
- A CLI argument accidentally containing the same key can override both.

### Do not invent "the safer source wins automatically"

Spring Boot does not change precedence order just because a value is considered a secret. Which source wins depends on the configuration mechanism and actual ordering.

In production operations:

1. Choose **one primary secret-provisioning channel** per key.
2. Avoid having the same credential exist simultaneously in multiple sources.
3. If migrating from env → mounted file, remove the old env configuration once safely deployed.
4. Verify the effective source **without printing values**.
5. Have startup tests using the exact channel production uses.

### Placeholders also use the effective value

Example:

~~~yaml
spring:
  datasource:
    password: "${db.password}"
~~~

If `db.password` appears in multiple `PropertySource`s, the placeholder uses the value `Environment` finds according to precedence. Therefore, avoid defining the same key in multiple sources without understanding which value wins.

## 17. How to verify a secret was supplied without printing the secret

A health/startup check can simply answer **whether the secret is present**, rather than outputting its contents.

Example:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class SecretAvailability {

    private final Environment environment;

    public SecretAvailability(Environment environment) {
        this.environment = environment;
    }

    public boolean hasPartnerSecret() {
        String secret =
                environment.getProperty("partner.auth.client-secret");

        return secret != null && !secret.isBlank();
    }
}
~~~

**Do not** do:

~~~java
System.out.println(
        environment.getProperty("partner.auth.client-secret"));
~~~

And do not write:

~~~java
log.info("Partner config: {}", credentials);
~~~

if `credentials` is a record/POJO whose `toString()` returns the client secret.

A good observability mechanism can report:

~~~text
partner.auth.client-secret: configured
~~~

without a copy of the value.

### Checking the mount directory

When runtime verification is needed, check:

- Does the directory exist?
- Are the filenames correct?
- Does the process have read permissions?
- Is the mount path wrong?
- Is the file size non-zero?
- Do the path and `spring.config.import` match?

Avoid using commands like `cat /run/secrets/...` to display real contents in terminals/tickets/chats. For permission errors, inspect owner/mode or test readability without printing secret bytes.

## 18. File permissions and the principle of least privilege

A mounted secret file is still a file. If multiple processes or users have permission to read it, the secret can leak.

In a Linux container, factors to determine:

1. Which user runs the JVM?
2. Which owner/group does the secret file belong to?
3. What is the file mode?
4. Do parent directories have appropriate traverse `x` permissions?
5. Is the container mounting the secret read-only?
6. Can other processes in the container/Pod read the same mount?
7. Does the container have privilege escalation or overly broad host filesystem access?

A `0400` file can work if the JVM runs as the exact owner. If the JVM runs as a non-root user that is not the owner, `0400` can prevent the application from reading it.

Do not solve this by granting `0777` everywhere. Instead, adjust identity, ownership, group, or platform permission mechanisms according to the principle of least privilege.

### Permissions at the platform level

In Kubernetes, permission to read a Secret object via the API and permission to read the mounted file inside a Pod are **two different layers**:

- Kubernetes RBAC decides which principals can read Secret objects or manage workloads.
- File permissions and container isolation decide which processes can read mounted files.

Both layers must be protected, rather than configuring only one of them.

## 19. Secret updates/rotation: what changes automatically, what does not?

Secrets usually have a lifecycle:

~~~text
create -> provision -> use -> rotate -> revoke
~~~

However, the platform updating a secret **does not mean the running JVM or every Spring bean automatically receives the new value**.

### 19.1. If the secret is supplied via environment variables

Environment variables are supplied when the process/container starts. If the Secret in the management system changes, the environment of a running process usually **does not change automatically**.

In Kubernetes, when a secret is used via `secretKeyRef` as an environment variable, the process usually must be restarted/recreated to receive the new value.

### 19.2. If the secret is supplied via mounted files

Kubernetes can update secret volume data in an *eventually consistent* manner when the Secret object changes. There can be latency due to sync loops and caching.

**Important exception:** Secret volumes mounted via `subPath` do not automatically receive updates through this mechanism.

Even after **file contents have changed**, Spring Boot normally loads `spring.config.import` during the Config Data phase at startup. An already-created `@ConfigurationProperties` bean, DataSource, or HTTP client **is not guaranteed to rebind/recreate automatically** just because the mounted file changed.

### 19.3. Safe rotation requires coordinating multiple layers

A process can include:

1. Platform creates a new secret and updates/rotates the issued version.
2. Ensure the new workload's mounted file or environment receives the right value.
3. Restart/rolling deploy or trigger a designed, tested, and supported reload mechanism.
4. Update/recreate connection pools or clients if credentials were cached.
5. Verify connectivity by success/failure criteria, **without logging the secret value**.
6. Revoke the old secret after confirming workloads have switched over.

An application with dynamic refresh must handle race conditions between old and new secrets, rollout order, and rollback capability. Do not simply see that a file changed and declare rotation complete.

## 20. Example of a migration workflow from env to mounted file

Suppose the old version used:

~~~text
SPRING_DATASOURCE_PASSWORD
~~~

The new version wants to use:

~~~text
/run/secrets/spring.datasource.password
~~~

and import:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

A controlled migration process:

**Phase 1 — preparation**

- Verify the platform can supply the secret file to the right workload.
- Choose a filename matching the required property.
- Ensure the JVM user can read the file.
- Prepare rollback capability and how to revoke credentials.

**Phase 2 — deployment**

- Add `spring.config.import` configuration in the target environment.
- Mount the secret file under the chosen name.
- **Remove the old environment variable containing the same key** from the deployment specification in the same plan.
- Deploy to a small group of instances first if the system allows.

**Phase 3 — verification**

- Verify the application starts successfully.
- Verify the DataSource/HTTP client actually connects.
- Do not compare or print raw passwords.
- Check logs to ensure no secrets appear.
- Check mount paths and file permissions without extracting contents.

**Phase 4 — completion**

- Expand the rollout.
- Revoke the old credential when safe.
- Remove unused variables/volumes/secret names.
- Update operational documentation to reflect the single source of truth for the secret.

If both environment and mounted file are left existing simultaneously, you must clearly understand precedence. Simply mounting the file does not prove it is overriding the environment value.

## 21. Common mistakes

### Mistake 1 — Leaving real secrets in application.yaml

~~~yaml
partner:
  auth:
    client-secret: REAL_SECRET
~~~

Data can enter Git, JARs, images, and logs. Externalize the value.

### Mistake 2 — Using environment variables but printing the entire Environment

~~~java
System.out.println(System.getenv());
~~~

This can output secrets supplied by the runtime. Only check required key names or presence/absence status.

### Mistake 3 — Putting secrets on the command line

~~~bash
java -jar app.jar --partner.auth.client-secret=REAL_SECRET
~~~

Arguments can be recorded in process lists, scripts, and diagnostic tools. Avoid this for real secrets.

### Mistake 4 — Thinking `_FILE` is automatically supported by Spring Boot for all keys

~~~text
PARTNER_AUTH_CLIENTSECRET_FILE=/run/secrets/token
~~~

There is no general guarantee that Spring Boot will read the file content and attach it to `partner.auth.client-secret`. Use `configtree:` or explicit file-reading logic.

### Mistake 5 — Mounting the file properly but forgetting `configtree:`

File:

~~~text
/run/secrets/partner.auth.client-secret
~~~

Without configuring an import or direct reading mechanism, Spring Boot does not automatically have `partner.auth.client-secret` just because the file exists.

### Mistake 6 — Wrong `configtree` root

~~~text
/etc/config/myapp/password
~~~

Importing root `/etc/config/` can create `myapp.password`, whereas importing root `/etc/config/myapp/` creates `password`. Verify the exact key name.

### Mistake 7 — Mounting a YAML file but importing as `configtree:`

~~~text
/run/secrets/secure-config.yaml
~~~

If you want YAML contents parsed into multiple properties, use `file:/run/secrets/secure-config.yaml` rather than assuming `configtree:` will parse YAML automatically.

### Mistake 8 — Not handling missing keys or empty files

The directory existing does not prove required files exist. Use validation and appropriate orchestration configuration to fail early.

### Mistake 9 — Interpreting `optional:` as "the credential can be missing"

`optional:` only affects how **a nonexistent Config Data location** is handled. If the secret is required, business validation must still ensure the application does not run with a missing credential.

### Mistake 10 — Having two sources with the same key name

Environment and configtree both supply `spring.datasource.password`. The operator assumes the new file is used, but environment takes higher precedence in standard ordering. Remove the old source or control precedence explicitly.

### Mistake 11 — Unreadable file due to owner/mode

The secret has `0400` permissions while the JVM runs as a user that does not own the file. Fix permissions following the principle of least privilege rather than opening permissions too wide.

### Mistake 12 — Assuming Kubernetes Secrets are automatically encrypted at rest

Kubernetes Secrets do not automatically guarantee datastore encryption at rest. Configure appropriate encryption, RBAC, and permission management.

### Mistake 13 — Treating Base64 as secret protection

A `data` value in base64 can be decoded. This is not cryptography protecting data.

### Mistake 14 — Updating a file and expecting Spring beans to refresh automatically

Kubernetes can update mounted files, but already-created `@ConfigurationProperties`/DataSources do not automatically pick up new credentials if the application does not support reload. A clear restart or refresh plan is needed.

### Mistake 15 — Using `subPath` while expecting the volume to auto-update

Kubernetes Secrets mounted via `subPath` do not receive automatic updates under the standard volume mechanism. This affects rotation strategy.

### Mistake 16 — Logging an entire record containing a secret

~~~java
log.info("credentials = {}", credentials);
~~~

Records usually have an auto-generated `toString()` containing secret members too. Do not log objects containing passwords/tokens.

### Mistake 17 — Committing local secret files to "make testing easy"

Files like `./secrets/token.txt` placed in the project folder can be accidentally added to Git, synced to the cloud, or attached to tickets. Use files outside the repository, local secret manager mechanisms, or demo data with no real value.

### Mistake 18 — Treating mounted files as completely secure

A process with permission to read a file can still leak secrets through malicious code, logs, memory dumps, or host privileges. Mounting is only one way to supply data and narrow the exposure surface; security also requires isolation, RBAC, patching, and auditing.

## 22. Testing without real secrets

Never put production credentials into ordinary tests.

### 22.1. Testing with a fake Environment

You can use Spring Boot test properties containing **fake, invalid** strings to verify binding:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "partner.auth.client-id=demo-client",
        "partner.auth.client-secret=DEMO_ONLY_TEST_VALUE"
})
class PartnerAuthBindingTest {

    @Autowired
    PartnerCredentials credentials;

    @Test
    void bindsCredentials() {
        assertEquals(
                "demo-client",
                credentials.clientId());

        // Use completely fake test values only.
        assertEquals(
                "DEMO_ONLY_TEST_VALUE",
                credentials.clientSecret());
    }
}
~~~

Requires the properties class to be properly registered with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

### 22.2. Testing a mounted configuration tree in a temporary environment

An integration test can create a temporary directory, write **fake data** into files with the proper names, and launch the Spring Boot context with `spring.config.import=configtree:<test-dir>/`.

The path must be prepared before Config Data is loaded; therefore when using dynamic tests, implement it with a mechanism appropriate for startup configuration (such as parameters before context creation) rather than writing files after the application has initialized.

Verification points:

1. A file named `partner.auth.client-secret` produces the right property.
2. Test content binds into the class.
3. Missing files or wrong roots are caught by tests.
4. If a higher-precedence environment variable/PropertySource exists, tests verify which source wins without using real secrets.

### 22.3. Testing failure when files are missing

If the import is required:

~~~properties
spring.config.import=configtree:/some/nonexistent/dir/
~~~

the application can fail during the Config Data phase. This is necessary behavior if the environment must not run without a secret directory.

If the import is optional:

~~~properties
spring.config.import=optional:configtree:/some/nonexistent/dir/
~~~

loading can continue, but a configuration bean with `@NotBlank` on a required credential should still report a violation if the key has no value.

### 22.4. Verifying no secrets appear in logs

In CI/integration tests, use an easily recognizable fake marker such as `DEMO_ONLY_SENTINEL_VALUE` and verify log streams do not contain the marker. This does not replace a full audit, but helps catch `Environment` dumps, `toString()` calls, or debug errors accidentally outputting values.

Use only markers that have no access to real systems.

## 23. When does an application need to read files directly instead of `configtree`?

`configtree:` is especially suitable when a secret is **a logical configuration value** that Spring/third-party auto-configuration needs to obtain via `Environment`.

There are cases where you may need the direct file path:

- A TLS library requires a path to a certificate or private key on the filesystem.
- A secret contains binary data consumed via a stream.
- Large file sizes or data that should not be turned into a String property.
- Application-driven rotation where the app watches the file and reloads via the library's API.
- The application needs to verify file permissions/format before passing to a library.

Example checking only the path:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public final class SecretFileCheck {

    public static void requireReadable(Path path) {
        if (!Files.isRegularFile(path) || !Files.isReadable(path)) {
            throw new IllegalStateException(
                    "Secret file does not exist or cannot be read");
        }
    }
}
~~~

The code above does not print file contents. If bytes must be read:

~~~java
byte[] data = Files.readAllBytes(path);
~~~

consider lifecycle, size limits, clearing copies from memory if appropriate, the risk of secrets being converted into immutable Strings, and the contract of the receiving library.

**It is not mandatory to put every private key into Environment.** Spring Boot provides `configtree:` for configuration convenience, yet certificate/key-consuming libraries may have more appropriate direct file/resource APIs.

## 24. Comparison table of the two secret-supply options

| Criterion | Environment variables | Mounted file + configtree |
| --- | --- | --- |
| Data form | Variable name and value pair | Filename/path is key, content is value |
| Provisioning in Kubernetes | `env.valueFrom.secretKeyRef` | Secret volume + `volumeMounts` |
| Provisioning in Compose | Environment passed by runtime/provisioner | Compose `secrets` mounted into `/run/secrets/` |
| How does Spring Boot read it? | Automatically via OS environment source | Requires `spring.config.import=configtree:/.../` or equivalent mechanism |
| Suitable for | Short text values | Text, multiple keys, certificate/file secrets |
| Common risks | Exposure via environment/process metadata, logs, child processes | Wrong file permissions, mount path, file reading, or logs |
| Secret changes at runtime | Usually requires restarting the process | File can change depending on platform; Spring beans do not auto-refresh |
| Access control | Depends on process/runtime isolation | File mode, owner/group, mount, and container isolation |
| PropertySource precedence | Ordered per OS env | Config Data; can be overridden by environment/CLI |
| Typical mistakes | Wrong variable name or variable not supplied | Wrong `configtree:` root, missing file, permission denied |

Neither option wins in every system. The choice depends on operational requirements, data types, secret manager, process permissions, and rotation plans.

## 25. Practice exercises with answers

### Exercise 1 — converting property names to environment variables

Given:

~~~text
spring.datasource.password
partner.auth.client-secret
security.jwt.signing-key
~~~

**Answer:**

~~~text
SPRING_DATASOURCE_PASSWORD
PARTNER_AUTH_CLIENTSECRET
SECURITY_JWT_SIGNINGKEY
~~~

Dots become underscores, hyphens are removed, and characters are uppercased.

### Exercise 2 — configtree structure

The container has:

~~~text
/run/secrets/
└── partner.auth.client-secret
~~~

Spring Boot imports:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

**Answer:** the property `partner.auth.client-secret` is present with the file's content as its value, provided the import succeeds.

### Exercise 3 — directory root

Given:

~~~text
/etc/config/app/password
~~~

**Question:** What key names do these two imports produce?

~~~properties
spring.config.import=configtree:/etc/config/
~~~

and:

~~~properties
spring.config.import=configtree:/etc/config/app/
~~~

**Answer:** the first creates `app.password`, the second creates `password`.

### Exercise 4 — YAML file vs. config tree

There is a file:

~~~text
/etc/secrets/app-secrets.yaml
~~~

containing multiple YAML keys.

**Answer:** use `spring.config.import=file:/etc/secrets/app-secrets.yaml` if you want Spring Boot to parse the YAML file. `configtree:` is for directories containing key-value style files.

### Exercise 5 — is `optional` enough to protect secrets?

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

The application strictly requires `partner.auth.client-secret`.

**Answer:** not enough. `optional:` only permits the import location to be absent; you must enforce missing/blank secrets via validation or an appropriate startup check.

### Exercise 6 — Docker Compose `_FILE`

You set:

~~~text
PARTNER_AUTH_CLIENTSECRET_FILE=/run/secrets/partner-token
~~~

**Question:** Does Spring Boot automatically read the file content as `partner.auth.client-secret`?

**Answer:** do not assume so. `_FILE` is a convention of certain container images/entrypoints, not a general capability for all Spring Boot properties. Use `configtree:` or intentional file-reading logic.

### Exercise 7 — Kubernetes env

In a Pod:

~~~yaml
env:
  - name: SPRING_DATASOURCE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-credentials
        key: password
~~~

**Answer:** Kubernetes reads the `password` key of the Secret and injects it into the container's environment variable; Spring Boot can use it for `spring.datasource.password`.

### Exercise 8 — Kubernetes file mapping

~~~yaml
volumes:
  - name: db
    secret:
      secretName: db-credentials
      items:
        - key: password
          path: spring.datasource.password
~~~

Mounted to `/etc/secrets/`, then import `configtree:/etc/secrets/`.

**Answer:** the file named `spring.datasource.password` supplies the corresponding logical key when Spring Boot loads the tree.

### Exercise 9 — two competing sources

There is a mounted file for `spring.datasource.password`, yet the container still has `SPRING_DATASOURCE_PASSWORD`.

**Answer:** in default source ordering, the environment variable can take precedence over Config Data from the tree. Remove the old source or verify ordering rather than assuming the file is definitely used.

### Exercise 10 — secret rotation

A Kubernetes Secret is updated. The volume mount already has the new file.

**Question:** Is the already-created DataSource guaranteed to use the new password?

**Answer:** not necessarily. The file can update, but Spring Boot loads Config Data at startup and the DataSource may retain the old credential. A rollout/restart or a specifically designed refresh/recreate mechanism is required.

### Exercise 11 — chmod 0400

A Secret file has `0400` permissions and the JVM runs as a user that does not own the file.

**Answer:** the application may be unable to read it. Fix permissions/identity according to least privilege rather than opening `0777`.

### Exercise 12 — preventing log leaks

A record has:

~~~java
public record PartnerCredentials(
        String clientId,
        String clientSecret) {
}
~~~

**Question:** Should you do `log.info("{}", credentials)`?

**Answer:** no. The record's `toString()` can print `clientSecret`. Only log configuration status or masked information.

### Exercise 13 — validating empty files

The Secret file has the right name but empty string content.

**Answer:** directory import may succeed yet the credential is still invalid. Use `@NotBlank` or explicit validation to refuse running if the credential is required.

### Exercise 14 — Base64

Kubernetes `Secret.data` contains base64 values.

**Answer:** that is representational encoding, not a security layer encrypting content. Restrict access, enable encryption at rest, protect the API, and govern secrets.

### Exercise 15 — choosing an approach

A system needs to pass a certificate and private key to a library that only accepts file paths; it also has a text API token.

**Suggested answer:** consider mounting the certificate/private key as files with restricted permissions so the library reads them directly; the token can be supplied via a tree file or environment depending on policy. Not every secret has to be converted into a String in `Environment`.

## 26. Secure deployment checklist

Before deploying a Spring Boot application to production, check the following areas.

### 26.1. Secret sources

- Real values are not in Git, container images, Dockerfiles, or public docs.
- Secrets are supplied through a system with access control and rotation policies.
- No unnecessary secret copies exist in scripts, CI variables, or local files.
- A secret is granted only to workloads that genuinely need it.

### 26.2. Spring Boot configuration

- Property names match canonical/relaxed binding.
- If using env, environment variable names are correct.
- If using mounts, `configtree:` root and filenames are correct.
- If using a complete YAML file, choose the appropriate `file:` import.
- Two sources do not unintentionally define the same key.
- Required configuration has validation or startup checks.
- No public default passwords in production.

### 26.3. Permissions and scope

- Containers run with an appropriate user.
- Mounted secrets are readable only by necessary processes.
- Volumes are read-only where appropriate.
- File modes, owner, group, and directory permissions are valid.
- Kubernetes RBAC follows least privilege, with encryption at rest when required.
- Restrict debug/exec permissions into production containers.

### 26.4. Observability and logs

- Do not print the entire `Environment`, records containing secrets, or secret files.
- Do not enable configuration logging at levels that can expose values without control.
- Actuator endpoints related to `env` / `configprops` are protected; do not assume all data is always masked across all versions/configs.
- Startup errors report **missing or unreadable key names**, not secret contents.
- Tests exist to detect secret markers leaking to logs.

### 26.5. Rotation and recovery

- Know whether the secret updates via environment or volume.
- Understand that `subPath` does not auto-update.
- Know whether Spring Boot requires restart/rebind/recreating clients.
- Have rolling deployment and rollback plans.
- Old credentials are revoked after new workloads successfully use the new ones.
- Have an incident process if a secret leaks or is granted to the wrong target.

## 27. Conclusion

There are two common ways to **supply secrets to Spring Boot at runtime**:

- **Environment variables:** the platform places `SPRING_DATASOURCE_PASSWORD` or a matching variable name into the process environment. Spring Boot reads the value via `Environment`; no literal password is needed in application files.
- **Mounted files:** the platform provides files at paths such as `/run/secrets/spring.datasource.password`, and Spring Boot can import them with `spring.config.import=configtree:/run/secrets/` to map filenames to property names.

Both options help separate **secret values** from **source code and artifacts**, but do not replace secure secret management. Systems still need file/container permissions, RBAC, log controls, encryption at rest when appropriate, validation for missing credentials, configuration precedence awareness, and a clear rotation workflow.

Always verify **where the secret is supplied, which mechanism Spring Boot uses to read it, whether the property name is correct, which source wins, and how the process will receive new secrets**. Those five questions help diagnose most issues when migrating an application from hardcoded passwords to environment variables or mounted secret files.

## References

- [Spring Boot 3.3 — Externalized Configuration and Configuration Trees](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).
- [Docker Compose — Manage secrets securely](https://docs.docker.com/compose/how-tos/use-secrets/).
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).
- [Kubernetes — Distribute Credentials Securely Using Secrets](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/).
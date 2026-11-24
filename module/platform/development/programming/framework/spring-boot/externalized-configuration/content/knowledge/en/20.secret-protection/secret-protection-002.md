# Separating Secrets from Git, Classpath Resources, and Spring Boot Build Artifacts

## 1. Goals and context

Spring Boot supports **externalized configuration** so that a single application build can run in local, staging, and production environments with different configuration values. This mechanism brings an important security benefit: there is no need to embed production credentials into source code or into resource files packaged with the application.

Application configuration can be grouped into:

- **Regular:** ports, timeouts, log modes, feature flags, endpoints without credentials.
- **Secret:** database passwords, API tokens, OAuth client secrets, private keys, signing keys, encryption keys, and credentials for message brokers and external services.
- **Contextually sensitive metadata:** connection strings containing userinfo, secret mount paths, tenant identifiers, internal hostnames, or resource locations with tokens in the query.

A common mistake is putting a real password into `src/main/resources/application-prod.yml`, committing it to Git, and building an executable JAR. At that point, the secret can exist in at least three places: **Git history**, **the JAR's classpath**, and **the distributed artifact/image**. Deleting the secret line in the current version does not automatically revoke the old copies.

**Core principle:**

> Git and the build should contain code, metadata, and non-secret configuration; real secrets are supplied at runtime by a managed source with its own permissions and lifecycle.

This lesson explains:

1. Why `.gitignore` is not enough to protect secrets.
2. Why `src/main/resources` is not a secret store.
3. Places where Maven, Gradle, CI, and Docker builds can cause credentials to be retained.
4. Options for supplying secrets to Spring Boot: environment, mounted files, `configtree:`, and secret managers.
5. Validation, logging, Actuator, rotation, and how to verify secrets do not appear in artifacts.
6. Response steps when credentials have been committed or published.

No single annotation in Spring Boot guarantees all of these on its own. It requires combining application design, the build system, and operational controls.

## 2. Three boundaries: Git, classpath, artifact

### 2.1. Git is a history system, not a vault

Git retains file versions across commits. A file that once contained credentials does not disappear from history simply because the current file no longer has that line.

Insecure example:

~~~properties
# src/main/resources/application-prod.properties
spring.datasource.username=orders_user
spring.datasource.password=REAL_DATABASE_PASSWORD
payment.gateway.api-key=REAL_API_KEY
~~~

These strings are illustrative placeholders, not real login credentials. In a real project, active credentials must never be placed in tracked files.

Even a private repository can be read by many people and systems: collaborators, CI jobs, clones, mirrors, backups, or source analysis tools. Permission to read Git is different from permission to use a secret.

### 2.2. The classpath is distributed software

Files in `src/main/resources` are normally copied into the resources output by Maven or Gradle. In a Spring Boot executable JAR, they usually live under `BOOT-INF/classes/`.

Example:

~~~text
src/main/resources/
  application.yml
  application-prod.yml
  keys/private-signing.pem
~~~

If one of these files contains a real private key, the contents can end up inside the JAR. Anyone who can download/extract the artifact can read the resource without running the application or activating the production profile.

### 2.3. Artifacts are copied and retained

After a build, a JAR can be stored in an artifact repository, CI artifacts, registries, image layers, caches, deployment hosts, and backup systems. An old Docker tag may still hold a JAR carrying an exposed secret. Deleting a new image or fixing source code does not automatically clean those copies.

**Conclusion:** secrets must be protected at the **source**, **build stage**, **output artifact**, and **runtime**.

## 3. Diagram of the insecure model

~~~text
Developer
   |
   v
application-prod.yml contains real password
   |
   v
Git commit / pull request / clone
   |
   v
Maven or Gradle processes resources
   |
   v
target/classes or build/resources/main
   |
   v
Executable JAR / WAR
   |
   v
Docker image / registry / backup
   |
   v
Production runtime
~~~

If credentials are exposed at any step, externalizing the secret at runtime in later releases is not enough to ensure old credentials can no longer be used. You must rotate/revoke the secret and address the scope of exposure.

Situations that further increase risk:

- CI prints configuration values to logs for debugging.
- Test snapshots save objects containing tokens.
- Maven/Gradle expands environment variables into resource output.
- Dockerfile copies a file and deletes it in a later layer.
- Crash reports or heap dumps retain values in memory.
- Binding errors write raw rejected values to the console.

## 4. Diagram of the recommended model

~~~text
Git repository
  ├── Java code
  ├── application.yml (no secret values)
  ├── metadata about property names and import locations
  └── tests with fake data
             |
             v
       CI build + scan
             |
             v
      Clean JAR and OCI image
             |
             v
      Deploy same artifact
             |
      +------+--------------------+
      |                           |
 Runtime identity          Secret manager /
      |                    mounted secret volume
      +-------------+-------------+
                    |
                    v
             Spring Environment
                    |
                    v
           @ConfigurationProperties
                    |
                    v
             Bean using secret
~~~

The goal is an **immutable artifact** that can be deployed to different environments. Production secrets do not need to appear inside that artifact; the deployment injects information from a separate secret source.

Spring Boot itself still has to receive and use the secret value inside the process. Therefore, "no secret in the JAR" does not mean "no secret in memory or the runtime filesystem."

## 5. Classifying what can be committed

| Content | In Git | In classpath/JAR | Alternative source |
| --- | --- | --- | --- |
| `server.port=8080` | Yes | Possible | Base Config Data |
| `app.client.timeout=3s` | Yes | Possible | Base Config Data |
| Property name `payment.gateway.api-key` | Yes | Possible | Schema/config metadata |
| Real API key | No | No | Runtime secret |
| Database password | No | No | Secret manager/volume |
| Private TLS/signing key | No | No | Secret manager/runtime file |
| Public certificate | Depends on policy | Possible | Classpath/external file |
| Build token for downloading private libraries | No | No | CI/build secret |
| Connection string with credentials | No | No | Secret source |
| Fake values used for testing | Yes if harmless | Possible in test resources | Fake fixture |

A URL can be ordinary data if it only contains a service address, but becomes sensitive data if it has a password in userinfo or an access token in a query parameter.

Do not judge sensitivity solely by key name. An `app.endpoint` key might hold a URL with credentials; a `notes` field might accidentally contain a token.

## 6. Why is `.gitignore` necessary but not sufficient?

`.gitignore` tells Git to ignore **untracked** files matching the rules.

Example:

~~~gitignore
.env
.env.*
!.env.example

local-secrets/
config/private/
application-local-secret.properties

*.p12
*.pfx
*.key
~~~

These patterns should be adjusted to fit project policy. A file extension does not prove whether data contains secrets; conversely, a token can live in a file named `notes.txt`.

### 6.1. Already-tracked files are not untracked automatically

If `application-prod.yml` was committed before being added to `.gitignore`, Git can continue managing that file.

You can check:

~~~bash
git ls-files src/main/resources/application-prod.yml
~~~

When you need to stop tracking a file while keeping the local copy, an intentional Git operation can be:

~~~bash
git rm --cached src/main/resources/application-prod.yml
~~~

However, this command **does not delete the secret from Git history**. If credentials were ever pushed, the first priority is usually to revoke or replace that secret per the incident response process.

### 6.2. Paths outside Git

`.gitignore` does not prevent:

- `git add -f` or forcing a file to be staged.
- A previously tracked file.
- Secrets written directly in Java source or tests.
- Tokens written into generated files.
- Docker builds picking up files from the local filesystem.
- Secrets appearing in logs, screenshots, tickets, or CI artifacts.

Therefore you need **pre-commit scans, CI scans, server-side protection, artifact scans**, and code review.

### 6.3. Example template files without real values

Provide:

~~~dotenv
# .env.example
PAYMENT_GATEWAY_APIKEY=
DB_PASSWORD=
APP_CLIENT_TIMEOUT=3s
~~~

The template file shows only **key names** and some non-sensitive values. It contains no real secrets and no sample passwords that could accidentally be used in production.

Note: Spring Boot does not by default load every `.env` file sitting next to a JAR. Tools like Docker Compose have their own `.env` reading mechanisms. Do not build a design assuming Spring automatically understands that file unless a specific loader is configured.

## 7. Do not place secrets in `src/main/resources`

Files under `src/main/resources` are normally copied into the classpath output:

~~~text
src/main/resources/production-credentials.json
src/main/resources/private-key.pem
src/main/resources/application-prod.yml
src/main/resources/config/secrets.properties
~~~

If these files contain secrets, the secrets can travel with the JAR. It is especially dangerous if content is placed in:

~~~text
src/main/resources/static/
src/main/resources/public/
src/main/resources/templates/
~~~

Some static resources can be served over HTTP depending on how the application is configured. Even when not served publicly, they are still not an appropriate place to store private keys and credentials.

### 7.1. Which files should still stay in the classpath?

An `application.yml` containing only normal configuration can safely be version-controlled:

~~~yaml
spring:
  application:
    name: payment-service

payment:
  gateway:
    endpoint: "https://gateway.example.test/v1"
    timeout: 3s
~~~

You can keep information such as:

- permitted default timeouts, retries, log levels;
- property names or prefixes for binding;
- non-secret profile activation;
- publicly permitted runtime import paths;
- public certificates or genuinely public resources when appropriate.

Do not treat `application-prod.yml` as a secret zone simply because its name includes "prod". If packaged into the JAR, its contents sit inside the artifact even when the profile is not activated when running locally.

### 7.2. Placeholders do not contain real values

You can declare:

~~~properties
payment.gateway.api-key=${PAYMENT_GATEWAY_APIKEY}
~~~

This is **a reference to a property at runtime**, not the secret itself. If the environment supplies `PAYMENT_GATEWAY_APIKEY`, Spring can resolve the value via `Environment`.

However, this does not automatically make the environment safer. If deployment or CI prints all environment variables, the secret can still leak. With Spring Boot relaxed binding, in many cases you do not even need an intermediate placeholder because the environment variable can bind directly to `payment.gateway.api-key`.

### 7.3. Do not use secret defaults

Example to avoid:

~~~properties
payment.gateway.api-key=${PAYMENT_GATEWAY_APIKEY:password123}
~~~

A default value may seem to help the application start, but it creates the risk of using a sample credential during a misconfigured deployment. For required secrets, fail startup clearly if missing.

## 8. Typed configuration and validation

A `@ConfigurationProperties` class can define a group of credentials:

~~~java
package com.example.payment.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment.gateway")
public class GatewayCredentials {

    @NotBlank
    private String apiKey;

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }

    @Override
    public String toString() {
        return "GatewayCredentials{apiKey=<redacted>}";
    }
}
~~~

Registration:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PaymentApplication {
}
~~~

With an appropriate Bean Validation provider (commonly via `spring-boot-starter-validation` on Spring Boot 3.x), `@NotBlank` helps detect a missing or blank secret.

**Do not treat a custom `toString()` as a complete solution.** Other places can still expose secrets: exceptions from Binder/converters, object serialization, heap dumps, directly logging `getApiKey()`, Actuator, or tracing attributes.

### 8.1. Do not log configuration beans

Avoid:

~~~java
log.info("Gateway settings: {}", credentials);
log.info("API key: {}", credentials.getApiKey());
~~~

You can use a safe message:

~~~java
log.info("Gateway credentials configuration initialized");
~~~

When an error occurs:

~~~text
[CFG-SECRET-001] Required payment gateway credential is missing.
Property: payment.gateway.api-key
Action: verify runtime secret source and permissions.
~~~

Do not print the rejected value, the contents of the secret file, or the entire `Environment`.

## 9. Approach 1: supplying secrets via runtime environment

Spring Boot supports environment variables as a configuration source. With the canonical name:

~~~text
payment.gateway.api-key
~~~

the typical relaxed-binding environment variable name is:

~~~text
PAYMENT_GATEWAY_APIKEY
~~~

Rule: dots become underscores, hyphens are removed, uppercase. Do not automatically turn `api-key` into `API_KEY` in every context.

Local example **using only a fake token**:

~~~bash
PAYMENT_GATEWAY_APIKEY="FAKE_LOCAL_TOKEN_NOT_FOR_PRODUCTION" \
  java -jar payment.jar
~~~

In production, secrets should be injected by deployment tooling from a managed source, not pasted as real tokens into commands saved in shell history.

### 9.1. Advantages

- No need to modify the JAR.
- Simple integration with many deployment platforms.
- Spring Boot Binder can convert env vars into the appropriate properties.
- The same image can be used in staging and production.

### 9.2. Limitations

- Process environments can be viewed by people/tools with corresponding permissions.
- Container inspection, crash reports, debug dumps, and CI logs can expose values.
- Environment variables are not a secret manager.
- Changing the environment after the process is running usually does not update existing beans automatically.
- Multiline or binary data is inconvenient for env vars.

If a secret has stricter requirements, consider mounted files or secret manager integration.

## 10. Approach 2: mounted files and `configtree:`

Spring Boot supports **Configuration Trees** via `spring.config.import` with the `configtree:` prefix. This fits well when the runtime platform supplies secrets as multiple files, each representing one key.

Runtime volume example:

~~~text
/run/secrets/
└── payment.gateway.api-key
~~~

The file content is the real credential mounted by the deployment system; this file **is not in Git or the image**.

A committable `application-prod.properties` can contain:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

When the `prod` profile is enabled, Boot imports the configuration tree. The filename `payment.gateway.api-key` becomes a property named `payment.gateway.api-key` in `Environment`, and can bind into `GatewayCredentials.apiKey`.

### 10.1. Folder structure also contributes to property names

A tree:

~~~text
/run/secrets/payment/gateway/api-key
~~~

when imported at the proper root can represent the property `payment.gateway.api-key`. Spring Boot also supports filenames containing dots, such as `payment.gateway.api-key`.

Do not assume a Kubernetes Secret object named `payment-gateway` automatically becomes the prefix `payment.gateway`. **The filenames and paths inside the config tree** determine the imported keys.

### 10.2. Use `optional:` or not?

You can declare:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

With `optional:`, if the location does not exist, Config Data loading can continue. This is convenient for optional sources.

If the secret volume is required in production, consider:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

so that a missing location fails early. Even so, an existing directory does not prove that **required files** are present; `@NotBlank` or an explicit required-property check is still needed.

### 10.3. `configtree:` is not an encryption feature

`configtree:` only turns files/folders into properties. It does not encrypt files, grant permissions, or guarantee that the volume is secure. Those concerns belong to the secret backend and runtime platform.

Anyone with permission to read files mounted into the container can access their contents. Therefore, restrict the container user, permissions, volume mounts, and which Pods/containers actually need the secret.

### 10.4. Strings and byte arrays

Spring Boot config trees can support binding to `String` or `byte[]` depending on the content. If a secret is binary data, do not arbitrarily convert it to a UTF-8 string and print it for debugging.

If a library requires a path to a private key/keystore, you can supply the file via a volume and configure a Spring `Resource` or `Path` to that file, rather than reading all contents into a `String` property.

## 11. Kubernetes Secret mount example

A Kubernetes Deployment can request mounting a specific key in a Secret object under the matching filename:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
    spec:
      containers:
        - name: app
          image: registry.example.test/payments:1.0.0
          volumeMounts:
            - name: payment-secrets
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: payment-secrets
          secret:
            secretName: payment-gateway
            items:
              - key: api-key
                path: payment.gateway.api-key
~~~

Assuming the Secret object has been safely provisioned with key `api-key`. Kubernetes projection provides the file:

~~~text
/run/secrets/payment.gateway.api-key
~~~

The application has:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

and a `@ConfigurationProperties(prefix = "payment.gateway")` class to receive the secret.

**Do not commit Kubernetes manifests containing real secret values encoded in base64** just because they are not directly human-readable. Base64 is encoding, not encryption.

### 11.1. Kubernetes Secrets do not guarantee absolute secrecy

Consider:

- RBAC: who has permission to read the Secret API.
- Encryption at rest for data stored in etcd if required.
- Pod/container access permissions on the volume.
- Auditing and lifecycle mechanisms for Secrets.
- Which tools can view environments, mounts, or Pod specs.
- Not sharing production credentials across unrelated workloads.

A Secret object and a Config Tree are two separate layers: Kubernetes supplies data into the filesystem; Spring Boot imports that data into properties.

### 11.2. Rotation does not mean beans update automatically

A volume-mounted Secret can be updated by the platform via its own mechanism. However, `@ConfigurationProperties` beans are usually bound at startup, and HTTP/database clients created from old values are not rebuilt automatically.

For rotation, plan a rolling restart/redeploy or a designed and tested reload mechanism. Some mount modes such as `subPath` have different update behavior than standard volume projections; know your platform's limitations.

## 12. Docker Compose secrets example

A Compose environment supporting secrets can provide runtime files:

~~~yaml
services:
  payment-service:
    image: registry.example.test/payments:1.0.0
    secrets:
      - source: payment_gateway_api_key
        target: payment.gateway.api-key

secrets:
  payment_gateway_api_key:
    file: ./local-secrets/api-key.txt
~~~

The container receives the runtime file according to the appropriate Compose mechanism, typically at:

~~~text
/run/secrets/payment.gateway.api-key
~~~

And Spring Boot imports:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

The repository should include:

~~~gitignore
local-secrets/
~~~

And in the Docker build context:

~~~dockerignore
local-secrets/
.env
.env.*
*.key
*.p12
~~~

**Do not commit `./local-secrets/api-key.txt`.** This Compose pattern is for illustration. In production, secret files/volumes must be managed by an organization-approved deployment mechanism.

## 13. Distinguishing build secrets from runtime secrets

This is a very important distinction.

| Type | Who needs it? | When | Appropriate source |
| --- | --- | --- | --- |
| Build secret | Maven/Gradle/Docker builder needs to authenticate to a private registry | Build | CI secret/build secret mount |
| Runtime secret | Application needs to call an API or database | Runtime | Secret manager/runtime volume |
| Test credential | Integration tests need a sandbox service | Test | Low-privilege CI secret |
| User credential | Users logging into the application | Request/auth runtime | Authentication flow, not application config |

An application should not pass a runtime API token into the build just to have it present in the image. If compilation does not use that token, the builder does not need permission to read it either.

### 13.1. Builds needing a token to download private dependencies

Docker BuildKit supports temporary secret mounts within a single build instruction:

~~~dockerfile
# syntax=docker/dockerfile:1
FROM maven:3-eclipse-temurin-21 AS build
WORKDIR /work
COPY pom.xml .
COPY src ./src
RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml \
    mvn -B -DskipTests package
~~~

The Maven settings file is supplied via `docker build --secret` per Docker documentation, instead of putting tokens into `ARG`/`ENV`. Ensure the build command does not write secrets into artifacts or logs.

A build secret mount **does not automatically become a runtime secret** in the final image. If the application needs a token at runtime, supply it separately through the runtime workflow.

## 14. Why not use Docker `ARG` or `ENV` to store secrets?

Anti-pattern:

~~~dockerfile
ARG API_TOKEN
ENV API_TOKEN=$API_TOKEN
RUN echo "$API_TOKEN" > /tmp/token
~~~

Build arguments and environment variables are unsuitable channels for protecting build secrets. They can leak through image configuration, metadata, history, provenance, cache, or logs depending on the build setup.

Another anti-pattern:

~~~dockerfile
COPY secrets/ /app/secrets/
RUN rm -rf /app/secrets/
~~~

Deleting files in a later layer **does not guarantee removing them from earlier layers or caches**. If secrets were brought into the build context and copied into a layer, the risk still exists.

### 14.1. Runtime images contain only clean artifacts

A simple Dockerfile:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/payment.jar /app/payment.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/payment.jar"]
~~~

This is a technical example and requires environment-specific hardening. It contains no secret-copying instructions.

**Warning:** if `target/payment.jar` already has a password inside, this Dockerfile still puts the password into the image. Protecting the build context does not replace inspecting the input JAR.

### 14.2. Role of `.dockerignore`

`.dockerignore` restricts which files are sent to the Docker build context per its rules. A file ignored by `.gitignore` can still exist on disk and slip into `COPY . .` if not excluded from the context.

Use both:

- `.gitignore` for the Git workflow.
- `.dockerignore` for the Docker build context.

Also scan artifacts built outside Docker; the two ignore files do not by themselves guarantee clean build outputs.

## 15. Maven and Gradle can put secrets into output

### 15.1. Maven resources

Maven normally copies `src/main/resources` to `target/classes`, then packages it into a JAR. If a resource contains real secrets, that content can end up inside the artifact.

A harder-to-spot case is **resource filtering**: the source file contains only placeholders, but Maven is configured to replace placeholders with an environment variable holding real credentials, causing `target/classes/application.yml` to contain secrets.

Do not use Maven filtering to bake runtime passwords into artifacts.

### 15.2. Gradle `processResources`

Similarly, `processResources` can copy, filter, or expand content from source resources into `build/resources/main`.

If a build script is configured to use environment variables to generate an `application-prod.properties` containing real passwords, the output file can enter the JAR. A source filename containing no secrets does not mean the final artifact contains none.

### 15.3. Where copies can remain

- `target/classes`, `build/resources/main`.
- JAR/WAR/native images and other artifacts.
- Docker layers/cache, image metadata/history.
- Generated sources and test reports.
- CI logs and build artifacts.
- Artifact registries, image registries, deployment nodes, backups.
- Crash dumps, heap dumps, structured logging pipelines.

**Inspect the actual artifact**, not just the source repository.

## 16. Inspecting JARs and images safely

You can list the entries of a JAR:

~~~bash
jar tf target/payment.jar
~~~

Examples to watch out for:

~~~text
BOOT-INF/classes/application-prod.yml
BOOT-INF/classes/private-key.pem
BOOT-INF/classes/config/secrets.properties
~~~

Filenames are only signals. A file named `application.yml` may be safe; a file named `notes.txt` may contain a token. Do not run scripts that print entire configuration files to CI logs in search of secrets.

Inspection workflow:

1. List suspicious entries.
2. Scan artifact contents using a secret scanner with redaction.
3. Use a fake canary in a test environment to check copy paths.
4. Inspect build outputs before packaging.
5. Inspect image configuration and layers per policy.
6. Do not upload extracted contents containing credentials to untrusted services.
7. Do not output raw findings containing secrets to logs or tickets.

### 16.1. Scanning source is not enough

If tokens are injected during the build step from the environment, a secret scanner running only on the Git tree may miss them. Scan `target/classes`, the JAR/image, or equivalent outputs before release.

### 16.2. Scanning images requires understanding layers

An image may have no `ENV TOKEN=...` yet still contain secrets in files/JARs or build layers. Conversely, the absence of a file in the final filesystem of a running container does not prove earlier layers and caches are clean.

## 17. Separation of duties in CI/CD

The pipeline should separate responsibilities:

~~~text
Source + PR
   |
Secret scanning and code review
   |
Compile/test with fake values
   |
Package + artifact scan
   |
Build image from clean artifact
   |
Image scan + publish
   |
Deploy: inject runtime secret
   |
Health check and safe observability
~~~

Principles:

- Build jobs must not be granted production runtime secrets unless required.
- Deploy jobs only have permissions in the target environment.
- Use OIDC/workload identities and short-lived tokens when infrastructure supports them.
- Separate staging and production credentials.
- Do not grant production secrets to pull requests running untrusted code.
- Use CI log masking, but do not treat masking as the sole protective layer.
- Restrict commands like `env`, `printenv`, or `set -x` in jobs that have secrets.

If a pipeline downloads private dependencies, supply a separate build credential with read-only permissions scoped to the required repositories. Do not use a production payment token for build tasks.

## 18. Secret scanning and pull requests

A good strategy has multiple layers:

1. Pre-commit hooks checking staged changes.
2. Secret scanning on pull requests and branches.
3. Server-side push protection if supported by the platform.
4. Scanning Git history per policy.
5. Scanning build artifacts and images.
6. False-positive review procedures that do not include raw secrets.
7. Rapid response procedures for detected credentials.

Tools like Gitleaks, git-secrets, or Git hosting secret-scanning features can help. No tool detects every secret; internal tokens with uncommon formats can slip through.

Do not put a raw secret into a scanner's allowlist file just to silence alerts. An exception/suppression should use a non-sensitive identifier and state a reason.

## 19. If a secret was committed: handle it in the right order

Suppose a real token was pushed along with `application-prod.yml`.

**First:** treat the secret as a potentially compromised credential, then address access permissions.

Practical steps:

1. **Stop further spread:** do not paste the token into chat, issues, tickets, or logs.
2. **Revoke/rotate:** invalidate the old credential or issue a new one according to a transition plan.
3. **Determine scope:** branches, commits, PRs, forks, clones, CI logs, artifacts, images, backups.
4. **Check audit logs:** identify unusual activity using the authorization system's mechanisms.
5. **Move the new secret to an appropriate runtime source:** stop hardcoding it.
6. **Build and deploy a clean release:** ensure no real secrets enter the new JAR/image.
7. **Consider cleaning/rewriting Git history:** coordinate with collaborators and use appropriate tools when truly necessary.
8. **Prevent recurrence:** scanners, PR checks, artifact checks, least privilege, and runbooks.

### 19.1. Why is rotation more important than just deleting history?

Someone with a clone/fork or cached copy may still retain the old value. Rewriting history cannot guarantee removing every copy. Once the secret has been revoked, old copies no longer carry the same access rights.

### 19.2. Do not unilaterally rewrite shared history

Tools such as `git-filter-repo` can remove data from commit history, but they change commit IDs, affecting branches, tags, PRs, and other clones. Doing so requires team coordination and adherence to repository governance policies.

### 19.3. Old artifacts are still copies

If an older JAR/image contained a token, do not consider the token safe just because the new image is clean. Revoke the credential and handle copies in registries/caches according to policy.

## 20. Secret managers and Spring Boot integration

A secret manager helps govern:

- workload identities and read permissions;
- secret versions and rotation;
- access auditing;
- short-lived credentials;
- per-environment and per-service secret provisioning;
- controlled storage instead of putting values in Git.

Ecosystem examples: HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Google Cloud Secret Manager, or other secret management services.

**Spring Boot core does not integrate with every secret manager automatically.** Some sources require an appropriate library/starter or Config Data integration. For example, Spring Cloud Vault supports externalized configuration from HashiCorp Vault.

Do not assume `spring.config.import=vault://` works just because you use basic Spring Boot. The right dependency and corresponding resolver mechanism are required.

### 20.1. Runtime identity

A design can look like:

~~~text
Kubernetes Service Account / Cloud Workload Identity
                       |
                       v
                 Authenticate
                       |
                       v
                   Secret manager
                       |
                       v
            Only authorized secrets
                       |
                       v
               Spring Environment
                       |
                       v
                 Application bean
~~~

Do not hardcode a long-lived "master token" in the artifact just to fetch other tokens. Support for identities and temporary credentials depends on the platform.

### 20.2. A secret manager does not fix bad code

If the application still logs `credentials.getApiKey()`, the secret still leaks. Secure storage does not replace safe logging, validation, and consumer-side authorization.

## 21. Config Data and precedence order

Spring Boot has multiple property sources. A key may appear from classpath Config Data, external Config Data, environment, system properties, or the command line. The binder chooses the effective value by precedence.

Example:

~~~properties
# application-prod.properties
spring.config.import=configtree:/run/secrets/
payment.gateway.endpoint=https://gateway.example.test/v1
~~~

If the runtime mount supplies `payment.gateway.api-key`, the Binder can read that key. However, **a higher-precedence source** can still override the property in some configurations.

When debugging, check:

1. Java `@ConfigurationProperties` prefix.
2. Key generated from the config tree file.
3. Active profile.
4. Whether the location was actually imported.
5. Which source is winning.
6. Validation and conversion.

Do not dump every `PropertySource` with raw values just to locate a key. Use permitted metadata and key names.

### 21.1. `spring.config.location` vs. `spring.config.import`

- `spring.config.location`: adjusts where Config Data is searched, typically replacing default locations.
- `spring.config.additional-location`: adds locations in addition to defaults.
- `spring.config.import`: imports additional data from appropriate locations, including `configtree:`.

If the runtime supplies **a complete properties/YAML file**, you can import the file via `file:`. If the runtime supplies **multiple files, one key per file**, using `configtree:` is the right approach.

## 22. Logging, Actuator, and safe observability

Secrets separated from the JAR can still leak through runtime diagnostics:

- `Throwable.getMessage()` and raw stack traces;
- `record.toString()` or Lombok `@ToString`;
- Actuator `/actuator/env` and `/actuator/configprops`;
- HTTP request/response logging;
- tracing span attributes and baggage;
- metrics labels;
- support tickets and crash dumps.

Avoid:

~~~java
log.error("Invalid settings: {}", credentials);
log.error("Rejected API key: {}", credentials.getApiKey());
~~~

Replace with:

~~~text
[CFG-SECRET-001] Required credential is missing.
property=payment.gateway.api-key
source-kind=runtime-secret
action=verify secret mount and access policy
~~~

**Never** print the raw rejected value or secret file contents. Key names may be shown to trusted operators if they are approved static identifiers.

### 22.1. Actuator sanitization

Actuator provides mechanisms to control configuration value display and endpoint exposure depending on the version. Do not assume every custom key will always be masked in every case.

Protect endpoints, restrict access, test with fake secrets, and do not disable sanitization for convenient production debugging.

### 22.2. Strings on the heap

A secret stored as a `String` can reside on the JVM heap and have multiple copies. Using `char[]` or `byte[]` in certain APIs helps control data at specific boundaries, but does not guarantee every copy has been wiped from memory.

Protecting heap/core dumps and restricting debugging tools with permission to read process memory remain necessary.

## 23. Rotation and revocation capability

A credential lifecycle can include:

~~~text
Provision -> Distribute -> Use -> Monitor -> Rotate -> Revoke -> Retire
~~~

Decisions needed:

- Who owns the credential and rotation permissions?
- How long is the secret valid?
- Are there auditing and expiration alerts?
- Can a new value be issued without rebuilding the JAR?
- How are clients currently using the old secret recreated?
- Is there an overlap period accepting both old/new credentials?
- During an incident, who has authority to revoke immediately?

### 23.1. Changing a file does not mean automatic rebinding

`@ConfigurationProperties` are normally bound when the application context starts. Changing a mounted secret file does not cause JavaBeans, HTTP clients, datasources, or message broker clients to pick up the new value automatically.

A simple rotation procedure:

1. Provision the new secret in the runtime source.
2. Ensure the target system accepts the new secret.
3. Rolling restart/redeploy the application.
4. Verify health and transactions.
5. Revoke the old secret.

If hot rotation without restart is required, a separately tested reload, synchronization, and client-recreation mechanism is needed. Do not rely solely on the volume having updated.

## 24. Canary tests to detect leak paths

Use **a fake value**, never a real secret:

~~~text
FAKE_CANARY_SECRET_DO_NOT_SHIP_2026
~~~

In a controlled test environment, supply the canary string through the runtime source and verify:

- Binding into `@ConfigurationProperties` works.
- The canary does not appear in the JAR/image.
- The canary is not in stdout/stderr or startup logs.
- The canary does not appear in Actuator/public APIs.
- The canary is not unintentionally present in pipeline artifacts.

Canaries help verify a single path, but do not replace secret scanning and policies.

### 24.1. Testing missing credentials

Do not supply `payment.gateway.api-key` and expect validation or startup checks to fail with a safe message. Isolate the test environment so it does not accidentally pick up real secrets from a developer's machine.

### 24.2. Testing mounted files

Create a temporary directory containing a `payment.gateway.api-key` file with fake content, import it with `configtree:`, and verify the Binder reads the right property. Clean up the temporary data after the test. Do not include that test folder in production build artifacts.

### 24.3. Testing final outputs

Beyond scanning Git, inspect `target/classes`/`build/resources/main`, the JAR, and the image. If a build plugin expanded secrets from the CI environment into output, a scanner checking only the working tree may miss them.

## 25. A minimal Spring Boot project layout

~~~text
payment-app/
├── src/main/java/com/example/payment/
│   ├── PaymentApplication.java
│   ├── config/GatewayCredentials.java
│   └── service/PaymentGatewayClient.java
├── src/main/resources/
│   ├── application.yml
│   └── application-prod.properties
├── .gitignore
├── .dockerignore
└── Dockerfile
~~~

**`application.yml` — no secrets:**

~~~yaml
spring:
  application:
    name: payment-service

payment:
  gateway:
    endpoint: "https://gateway.example.test/v1"
    timeout: 3s
~~~

**`application-prod.properties` — import location, no values:**

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

**Secret mounted at runtime:**

~~~text
/run/secrets/payment.gateway.api-key
~~~

**Configuration class:**

~~~java
package com.example.payment.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment.gateway")
public class GatewayCredentials {
    @NotBlank
    private String apiKey;

    public String getApiKey() { return apiKey; }
    public void setApiKey(String apiKey) { this.apiKey = apiKey; }

    @Override
    public String toString() {
        return "GatewayCredentials{apiKey=<redacted>}";
    }
}
~~~

**Registration:**

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class PaymentApplication {
}
~~~

When the `prod` profile is active and the runtime secret volume is present, Spring Boot imports the file and the Binder links the property to the JavaBean. This is a configuration-supply mechanism; it does not automatically call the payment gateway API or verify the token is still valid.

Conditions to work:

1. Appropriate Spring Boot and Validation dependencies.
2. `GatewayCredentials` bean is registered.
3. Production profile loads `spring.config.import`.
4. Mount path and filename match the property name.
5. File has read permissions and valid content.
6. No higher-precedence source unintentionally overrides the key.
7. Artifact has been verified to contain no secrets.

## 26. Common mistakes

### 26.1. Deleting a password from a file and thinking Git is clean

Older commits still retain the content; credentials may have been copied. Rotate/revoke per procedure rather than just committing a clean file.

### 26.2. Adding `.gitignore` after committing

`.gitignore` does not automatically untrack files already managed by Git. Check the index and handle intentionally.

### 26.3. Putting secrets in `application-prod.yml` because "only production reads it"

The file can still sit inside the JAR even when the profile is inactive. Profiles select configuration; they are not a security mechanism.

### 26.4. Using build filtering to put runtime passwords into resources

Maven/Gradle can turn a placeholder in source into a real secret in output. Inspect artifacts after building.

### 26.5. Using Docker `ARG`/`ENV` to pass secrets at build time

Build variables can leak via metadata/history/cache and are unsuitable as a secret channel. Use build secret mounts if the build genuinely needs them.

### 26.6. Having `.gitignore` without `.dockerignore`

A local file untracked by Git can still be sent to the Docker build context.

### 26.7. Config tree filename does not match the prefix

`/run/secrets/api-key` does not automatically become `payment.gateway.api-key`. Check the root, folders, and filename.

### 26.8. Using `optional:` for required secrets without validation

This can let the application proceed without credentials. When required, fail fast with a message that does not leak values.

### 26.9. Committing base64 Kubernetes Secret data

Base64 is not encryption. Do not commit real Secret values in encoded form.

### 26.10. Changing a Secret volume and expecting JavaBeans to update automatically

Standard binding does not automatically refresh beans and clients. A restart or tested reload mechanism is needed.

### 26.11. Logging a config object containing secrets

`toString()`, exception causes, and serialization can expose contents. Do not use raw values in diagnostics.

### 26.12. Scanning only source without scanning artifacts

Secrets can be added during the build. Inspect the JAR/image and pipeline logs.

### 26.13. Using production credentials in CI PR jobs

Untrusted code could access secrets. Use fake/test credentials with low privileges and separate environments.

## 27. Pre-release checklist

- [ ] No real credentials in source code or new Git commits.
- [ ] Any secret previously exposed in Git history has undergone incident response.
- [ ] `.gitignore` blocks untracked local files; do not rely on ignore as the sole solution.
- [ ] `src/main/resources` contains no real private keys, passwords, or tokens.
- [ ] Profile-specific files contain only non-secret metadata.
- [ ] Maven/Gradle does not inject runtime secrets into generated resources.
- [ ] JAR, image, and build caches are handled per policy.
- [ ] `.dockerignore` excludes sensitive files from the Docker build context.
- [ ] Build secrets and runtime secrets have separate sources, permissions, and lifecycles.
- [ ] CI jobs are not granted production credentials beyond what is needed.
- [ ] Runtime secrets are supplied through an organization-approved source.
- [ ] `configtree:` root and filenames match Java prefixes.
- [ ] Missing required credentials fail safely.
- [ ] No secrets in logs, Actuator, metrics, tracing, or public APIs.
- [ ] A rotation and revocation plan exists.
- [ ] Secret scanners cover source, history, artifacts, and images.
- [ ] Canary tests do not appear in artifacts/logs.
- [ ] The same JAR/image can deploy across multiple environments with separate credentials.

## 28. Conclusion

**Separating secrets from Git, the classpath, and build artifacts** is not just moving a password line to another file. It is an architectural decision about **where values live, who can access them, when they are supplied, how they are verified, and the credential's lifecycle**.

Spring Boot provides `Environment`, Config Data, `@ConfigurationProperties`, placeholders, and `configtree:` so applications receive configuration from the runtime. Those mechanisms make it possible to build a JAR/image **containing no real secret values**, while the deployment environment supplies secrets independently.

For end-to-end protection:

1. Never commit secrets or store real secrets in `src/main/resources`.
2. Never bake secrets into JARs/images/build layers/generated resources.
3. Use a runtime secret source with least privilege.
4. Do not confuse `.gitignore`, base64, or `configtree:` with an encryption system.
5. Validate required secrets and never print raw values in errors/logs.
6. Design rotation/revocation independently of the artifact lifecycle.
7. If a credential is exposed, **revoke/replace it first**, then clean Git history and artifact copies per procedure.

### References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Configuration Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing-configuration-trees)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Docker Docs — Build Secrets](https://docs.docker.com/build/building/secrets/)
- [Docker Docs — Build Variables](https://docs.docker.com/build/building/variables/)
- [Kubernetes Docs — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [GitHub Docs — Removing Sensitive Data from a Repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
- [GitHub Docs — Secret Scanning](https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning)

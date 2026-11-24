# Preventing Credentials, Private Keys, and Sensitive Configuration from Leaking into Spring Boot Archives or Images

## 1. Objectives and Security Boundaries

A Spring Boot application may be packaged as an executable JAR/WAR or an OCI container image. Along the way, data passes through many places: Git checkout, resource processing, Maven/Gradle builds, archives, Docker build contexts, buildpack builders, caches, image layers, registries, and runtime containers. **A secret appearing at any step can be inadvertently persisted.**

Data that must be protected includes:

- Database passwords, API tokens, OAuth client secrets, session/signing keys.
- SSH private keys, TLS private keys, PKCS12/JKS keystores and passphrases.
- Registry credentials, artifact repository credentials, cloud access keys, CI/CD tokens.
- Production configuration files containing secrets, connection strings, private endpoints, or restricted operational details.
- Credentials used to sign artifacts/images, encryption keys, master keys, and recovery codes.

**The problem is not just avoiding hard-coded passwords in Java.** The entire pipeline must be protected:

~~~text
Source / Git / CI secrets
       |
       v
Maven / Gradle / resource processing
       |
       v
JAR / WAR / generated files
       |
       v
Docker build context / BuildKit / CNB builder
       |
       v
Build cache / image layers / metadata / registry
       |
       v
Runtime container / logs / diagnostics / backups
~~~

This lesson uses **Java 17 and Spring Boot 3.3.13**, with Maven or Gradle, Docker BuildKit, and Cloud Native Buildpacks. This is an illustrative version set; when applying it, check compatibility and security policies for your toolchain versions. The commands in this lesson are instructions for learners to run in authorized environments, not pre-executed build/scan results.

After completing this lesson, you will be able to:

1. Distinguish build-time credentials, runtime secrets, and non-sensitive configuration.
2. Keep secrets out of source code, resource filtering, JARs/WARs, Docker build contexts, and images.
3. Grant read access to artifact repositories/private Git and publish access for images without storing credentials in POMs/Gradle scripts/Dockerfiles.
4. Use Docker BuildKit secret mounts properly and understand why ARG/ENV are unsuitable for passing build secrets.
5. Configure Spring Boot to read secrets from mounted files via configtree.
6. Inspect archives, images, Git history, build logs, and caches for signs of leaks.
7. Respond to leaked-credential incidents by revoking/rotating, rebuilding, replacing images, and auditing older copies.

## 2. Distinguishing Secrets, Private Keys, and Regular Configuration

Not every configuration value is a secret. Classification helps determine which values may be packaged inside an archive.

| Data type | Example | Allowed in JAR/image? | Appropriate delivery mechanism |
| --- | --- | --- | --- |
| Public/non-sensitive config | Service name, port, default feature flags, public URLs | Usually yes, if no restricted internal info is included. | application.properties, environment, or config file. |
| Environment config | Database name, internal host, region, timeout | Depends on internal classification; best externalized so one artifact runs across environments. | Runtime config, ConfigMap, config service. |
| Credential | Password, API token, client secret | **No.** | Secret manager, CI secret store, runtime secret mount. |
| Private key | SSH key, TLS private key, signing key, encryption key | **No.** | HSM/KMS, Vault, secret manager, or secure runtime mount. |
| Public certificate/key | Public TLS certificate, public verification key | Possible, depending on policy and need. | Trust store/CA bundle or public config. |
| Build credential | Maven repository password, Git deploy key, registry token | Must never be packaged into the product. | Build runner secret store, short-lived token, BuildKit secret/SSH mount. |
| Test fixture | Fake token, fake password dedicated to tests | Possible in test sources/resources if guaranteed fake and unusable in real systems. | Dedicated test fixtures; never reuse production secrets. |

**Private keys and certificates are not the same:** certificates/public keys can generally be shared to verify identity; private keys allow signing, decrypting, or impersonating an identity and must be strictly protected. A .p12/.jks file can hold both a certificate and a private key; treat the entire keystore and its passphrase as sensitive data.

### 2.1. Build-Time Secrets vs. Runtime Secrets

**Build-time secrets** are only needed to build the product, such as credentials to download dependencies from a private Maven repository or an SSH key to clone a private Git repository. They should only be present during the exact build step that needs them.

**Runtime secrets** are used by the application once the container is running, such as a database password or API token. They do not need to exist during compilation/packaging or inside the OCI image; the runtime platform supplies them when deploying/starting the container.

| Secret | When needed? | Handling example |
| --- | --- | --- |
| Maven repository token | When Maven resolves dependencies | External settings.xml, CI secret store, or BuildKit secret mount. |
| Private Git SSH key | When cloning source/private submodules during build | SSH agent/BuildKit SSH mount. |
| Docker registry token | When pulling builder/run images or publishing images | Docker credential helper or Spring Boot plugin registry credentials sourced from CI secret store. |
| Database password | When the app opens runtime connections | Secret file mount and Spring Boot configtree. |
| TLS private key | When the app terminates TLS/mTLS | Runtime keystore/PEM mount; never copy into the image. |
| Artifact signing key | When signing JARs/images/releases | HSM/KMS/remote signing service; never store private keys in workspace/image. |

**Never grant a deploy-privileged token just to download dependencies.** Separate credentials by task, keep them short-lived, least-privileged, and revocable. If your CI platform supports workload identity/OIDC to obtain short-lived tokens from a cloud/secret manager, prefer that over long-lived access keys.

## 3. Common Pathways That Leak Secrets into Artifacts

### 3.1. Source Code and Git

Dangerous examples:

~~~java
// DO NOT DO THIS: the value is compiled into the class file.
private static final String API_TOKEN = "prod-token-value";
~~~

~~~yaml
# DO NOT DO THIS: application-prod.yml in the repository contains a real password.
spring:
  datasource:
    username: orders
    password: prod-database-password
~~~

~~~properties
# DO NOT DO THIS: secret in a resource inside src/main/resources.
partner.api.token=prod-token-value
server.ssl.key-store-password=real-keystore-password
~~~

Even if the line or file is deleted in a later commit, the secret can remain in:

- Older Git commits/trees, branches, tags, forks, pull requests, or Git bundles.
- IDE local history, patches, backups, CI artifacts, caches, and logs.
- Docker build contexts, image layers, or image registries.
- Maven/Gradle generated resources and published JARs/WARs.

**.gitignore only prevents untracked files matching ignore rules from being added to Git.** It does not remove already-committed files or historical commits. When a real credential is found in Git, treat it as compromised and rotate/revoke it; merely deleting the file does not revoke access.

### 3.2. Maven/Gradle Resource Processing

Maven Resources Plugin can substitute placeholders with values from project/system properties, filter files, or command-line flags. If a secret enters a filter and that resource is copied to target/classes, the secret can end up inside the JAR.

Gradle can likewise generate resources via processResources, expand, custom tasks, or generated sources. A task writing a token to an output file can send that token into build/resources/main and the archive.

**Never feed secrets into filter files, resource expansion, generated sources, or task outputs.** Only filter an allowlist of non-sensitive variables such as application version or build number. Separate filterable resources from sensitive resources and keep secret files outside the source tree.

### 3.3. Dockerfile and Build Context

Common ways secrets leak:

~~~dockerfile
# DO NOT DO THIS: value persists in image configuration.
ENV DATABASE_PASSWORD=real-password

# DO NOT DO THIS: build args can appear in image history/provenance.
ARG REPOSITORY_TOKEN
RUN curl -H "Authorization: Bearer $REPOSITORY_TOKEN" https://repo.example.invalid/file

# DO NOT DO THIS: secret is stored in a filesystem layer.
COPY settings.xml /root/.m2/settings.xml
COPY secrets/ /app/secrets/
~~~

ENV is saved in the image config and passed into containers. ARG is not stored as a runtime environment variable, but Docker warns that build arguments are unsuitable for passing credentials: they can appear in docker history and provenance attestations. RUN echo secret > file or COPYing a secret into the image writes data into a layer.

**Deleting a file in a later layer does not erase its bytes from earlier layers.** Docker image layers are immutable; a RUN rm /app/secret.txt instruction in a new layer does not remove the secret from the previous layer.

### 3.4. Cloud Native Buildpacks (CNB)

Spring Boot Maven Plugin spring-boot:build-image and Gradle bootBuildImage pass application/build configuration to the builder to create the image.

- environment/env in the plugin passes variables **to the builder/buildpacks**; it does not mean protected runtime secrets.
- Buildpacks may read those variables and write them to generated files, logs, layers, or caches depending on buildpack logic.
- Some variables such as Paketo BPE_* are designed to persist configuration into the image and apply at app launch; never use them for passwords/tokens/private keys.
- bindings bind-mounts directories into the builder container. Mounting read-only from outside the source/build context can be useful when a buildpack supports that service binding, yet **a bind mount does not automatically guarantee the buildpack will not copy contents into a layer/cache**.

Supply build-time credentials only to audited buildpacks, only in the step that needs them, with least privilege. Inspect builder logs, build workspaces/caches, and image outputs.

## 4. Design Principles to Keep Secrets Out of Archives/Images

1. **Never place secrets in source code, POMs, Gradle scripts, Dockerfiles, application resources, or committed filter files.**
2. Separate build-time secrets from runtime secrets; never expose runtime secrets to the build process.
3. Use a CI secret manager or secret vault; obtain short-lived tokens scoped to the exact job/step.
4. For secrets needed during a build, use ephemeral mechanisms such as Docker BuildKit secret/SSH mounts or buildpack-supported bindings.
5. At runtime, mount secret files or use a secret manager/runtime identity; have the app read from external config.
6. Never echo, log, serialize, print in exceptions, or include secrets in build scans/diagnostic reports.
7. Never place secrets into archives, OCI layers, image labels, build metadata, SBOM annotations, provenance, or build caches.
8. Never share build caches/workspaces containing secrets across untrusted runners/tenants.
9. Scan source code, Git history, archives, and images before publishing.
10. If a secret leaks, **revoke/rotate first**, then clean up copies, rebuild, and redeploy.

**The goal is to minimize how long a secret exists during a build and narrow which components can read it.** Environment variables are convenient but not automatically safe: other privileged processes on the host/container can inspect environments, and diagnostic tools may display them. For highly sensitive data, read-only file mounts or secret manager APIs are easier to control.

## 5. Spring Boot Externalized Configuration: Reading Secrets at Runtime

Spring Boot loads configuration from application properties/YAML, environment variables, system properties, command-line arguments, and other config data sources. For secrets, keep **property names or external paths** inside the artifact, while supplying actual values at runtime.

### 5.1. Configtree Example for Secret Files

Suppose the platform mounts a directory into the container:

~~~text
/run/secrets/
├── partner.api.token
├── spring.datasource.username
├── spring.datasource.password
└── server.ssl.key-store-password
~~~

Each filename becomes a property name; the file's content becomes its value. In src/main/resources/application.properties, declare only:

~~~properties
spring.config.import=configtree:/run/secrets/

partner.api.base-url=https://api.partner.example
spring.datasource.url=jdbc:postgresql://db.internal:5432/orders
~~~

spring.config.import=configtree:/run/secrets/ instructs Spring Boot to read the config tree. The files spring.datasource.username and spring.datasource.password supply the corresponding properties. **No passwords are written into resources inside the JAR.**

For Docker Swarm secrets, Spring Boot can read secret files mounted under /run/secrets/ using configtree:. Kubernetes can mount Secret volumes or use a CSI secret provider into a similar path.

**Note on optional:** optional:configtree:/run/secrets/ lets the application continue if the directory does not exist. Use it only when secrets are genuinely optional (e.g., dev environments). If production requires credentials, omit optional: so the app fails fast when secrets are missing, avoiding startup with broken or insecure defaults.

### 5.2. Binding Properties in Java Without Printing Secrets

src/main/java/com/example/security/PartnerApiProperties.java:

~~~java
package com.example.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiProperties {

    private String baseUrl;
    private String token;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getToken() {
        return token;
    }

    public void setToken(String token) {
        this.token = token;
    }
}
~~~

src/main/java/com/example/security/SecretSafeApplication.java:

~~~java
package com.example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class SecretSafeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecretSafeApplication.class, args);
    }
}
~~~

PartnerApiProperties receives partner.api.token from the config tree at runtime. This class **does not override toString() to print the token**. If using Lombok @Data, Java records, or logging entire objects, toString() can leak tokens into logs; exclude secrets from toString() and logged fields.

When calling APIs, place the token only in the HTTP Authorization header on the outbound client. Never log headers, full request objects, or exceptions containing headers. Never return secrets in REST responses or Actuator endpoints.

### 5.3. Tests Use Fake Credentials Only

In unit/integration tests, use dummy values like test-only-token—never copy real staging/production credentials. If testing configtree, create temporary files with dummy data in a dedicated test directory, restrict permissions, and delete them after the test.

Never commit src/test/resources/application-prod.yml containing real credentials. Never share real API tokens between tests and production because test reports, CI artifacts, and failure logs may be retained for a long time.

### 5.4. Environment Variables vs. File Mounts

Non-sensitive configuration can be passed via environment variables, e.g.:

~~~bash
SPRING_PROFILES_ACTIVE=prod
SERVER_PORT=8080
~~~

If you must use an environment variable for a credential, inject it from a secret store at runtime, restrict permissions to inspect process/container metadata, and never run commands that dump the entire environment.

For highly sensitive secrets, prefer read-only file mounts with configtree:. Never inject secrets into application.properties via **build-time** placeholder expansion; runtime placeholders can be safe if values truly come from external config, but verify the final resource contains no substituted values.

## 6. Maven: Keeping Repository Credentials Out of POMs and Archives

### 6.1. Never Store Repository Passwords in pom.xml

Maven separates:

- pom.xml: declares project, dependencies, repositories, plugins, and build behavior.
- settings.xml: machine/user/CI settings such as server authentication, mirrors, and proxies.

For private repositories, declare the matching server ID in user/CI settings. A temporary ~/.m2/settings.xml provisioned on the build runner holds a server entry whose ID matches the repository ID in the POM, with username/password injected by the secret manager at job runtime. **Never store real values in the POM or a committed settings file.**

In pom.xml, the repository uses the same ID:

~~~xml
<repositories>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.invalid/maven/releases</url>
    </repository>
</repositories>
~~~

repo.example.invalid is only an illustrative domain. Replace it with your organization-approved repository. Maven settings supports keeping server authentication separate from the project POM.

**Never commit** ~/.m2/settings.xml, settings-security.xml, private keys, or temporary settings files to the project. Restrict file read permissions, use isolated workspaces/agents, delete temporary files when the job finishes, and avoid printing help:effective-settings, help:effective-pom, or debug logs containing credentials.

### 6.2. Maven 3 Password Encryption Is Not a Secret Vault

Maven 3 can encrypt/obfuscate passwords in settings.xml, but Maven documentation states this mechanism is obfuscation-grade and does not stop a determined attacker who can read both the encrypted values and the master password. It helps avoid exposing passwords in casual screenshots/logs, **and does not replace a secrets manager, file permissions, or CI secret stores**.

Maven 4 introduces a newer encryption/dispatcher mechanism, yet the master key/source still needs protection. Regardless of version, never commit credentials or master keys into source repositories.

### 6.3. Resource Filtering: Allowlist Permitted Values

If Maven must filter version/build metadata, separate the directories:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/main/resources-filtered</directory>
            <filtering>true</filtering>
        </resource>
    </resources>
</build>
~~~

src/main/resources-filtered holds only non-sensitive data such as version or build number. **Never** add passwords/tokens/private keys to filter files or -D properties substituted into resources by Maven. Avoid enabling filtering across the entire resource tree unnecessarily.

Maven Resources Plugin also warns against filtering binary resources like images/PDFs because it can corrupt files. Keep binary resources and filtered text in separate directories.

## 7. Gradle: Supplying Repository Credentials via the Typed Credentials API

Do not write:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.example.invalid/maven')
        credentials {
            username = 'real-user'
            password = 'real-password'
        }
    }
}
~~~

Use a repository name and PasswordCredentials:

~~~groovy
repositories {
    maven {
        name = 'internal'
        url = uri('https://repo.example.invalid/maven')
        credentials(PasswordCredentials)
    }
}
~~~

Gradle looks up project properties derived from the repository name: internalUsername and internalPassword. In CI, supply them via secret-backed environment variables:

~~~bash
ORG_GRADLE_PROJECT_internalUsername
ORG_GRADLE_PROJECT_internalPassword
~~~

Gradle supports ORG_GRADLE_PROJECT_ variables to supply project properties for unattended builds. Developer machines can use GRADLE_USER_HOME/gradle.properties with strict file permissions, but **never commit** a project gradle.properties containing credentials.

The typed credentials API lets Gradle manage credentials by repository identity and redacts values from certain build scans/error outputs. Even so, protect runners, logs, Gradle user home, and configuration/build caches; never println properties or enable --debug and publish the output.

### 7.1. gradle.properties Is Not a Place to Commit Secrets

A project gradle.properties can hold non-sensitive flags, but if it contains internalPassword, never commit it. Use ORG_GRADLE_PROJECT_internalPassword from the CI secret store or a protected file in Gradle user home. Never pass secrets via -P, -D, or command-line flags because shell history, process listings, and CI command logs can capture arguments.

### 7.2. Configuration Cache and Build Cache

The Configuration Cache can persist build configuration state to disk for reuse; Gradle encrypts cache entries, yet read permissions on the cache directory and encryption key must still be restricted. Never copy GRADLE_USER_HOME from a runner holding secrets into public workspaces/artifacts.

Gradle's build cache stores **task outputs**. If a task accidentally writes a token into an output file, that output can be persisted in local/remote caches. Tasks using secrets must ensure their outputs contain no credentials; avoid caching tasks that render config files containing real secrets. For special tasks requiring secrets that produce sensitive outputs, consider disabling caching or redesigning them so outputs exclude secrets.

## 8. Docker BuildKit: Passing Build Secrets Only to the Exact Step That Needs Them

### 8.1. Why ARG and ENV Are Unsuitable

| Mechanism | Suitable for | Why not use for secrets? |
| --- | --- | --- |
| ARG | Non-sensitive build options such as version, architecture. | Can appear in docker history and provenance; unsuitable for passwords/tokens. |
| ENV | Non-sensitive runtime defaults, e.g., SERVER_PORT. | Saved in image config and persists inside containers. |
| COPY settings.xml | Public build input files. | Copied into a layer and may remain in image/cache. |
| RUN --mount=type=secret | Credentials needed only during a single BuildKit RUN step. | Secret mounts are not written to the image automatically; however, commands inside RUN can still copy/echo secrets to files/logs if written carelessly. |
| RUN --mount=type=ssh | SSH agent/socket for cloning private Git repos. | Exposes only the socket during that step; never copies private keys into the context. |

### 8.2. Multi-Stage Maven Dockerfile Example with BuildKit Secrets

The following Dockerfile demonstrates building a Spring Boot JAR in a builder stage. Maven settings.xml is mounted only during the Maven commands that need private repository access:

~~~dockerfile
# syntax=docker/dockerfile:1
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

COPY pom.xml .
RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml,required=true mvn -B -s /root/.m2/settings.xml dependency:go-offline

COPY src ./src
RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml,required=true mvn -B -s /root/.m2/settings.xml package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/target/secret-safe-demo.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

The artifact name secret-safe-demo.jar must match the project's actual finalName/output. The example Dockerfile neither COPYs settings.xml nor uses ARG REPO_PASSWORD.

Build with BuildKit/Buildx:

~~~bash
docker buildx build --secret id=maven_settings,src="$HOME/.m2/settings.xml" -t secret-safe-demo:local .
~~~

The secret file is supplied by the build client and mounted only during the execution of that RUN instruction. There is no need to place settings inside the Docker build context. **Never** run cat /root/.m2/settings.xml, set -x, echo $REPO_PASSWORD, or copy the mounted file into /workspace.

### 8.3. .dockerignore Reduces Risk of Sending Sensitive Files to the Build Context

Example for a Dockerfile that runs Maven inside the build:

~~~text
.git
.gradle
.mvn/wrapper/maven-wrapper.jar
**/.env
**/.env.*
**/secrets/**
**/*.pem
**/*.key
**/*.p12
**/*.jks
**/settings.xml
**/id_rsa*
**/id_ed25519*
target/
build/
~~~

Adjust for your real project: if the Dockerfile copies a prebuilt JAR from target/ or build/, do not exclude that directory. .dockerignore is a **guardrail that shrinks the build context**, not a secret manager, and it does not erase files already committed to Git history.

If a project has .env.example, keep only variable names and dummy/empty values; any .env file containing real credentials must stay outside the context and be ignored.

### 8.4. Multi-Stage Builds Do Not Automatically Erase All Secrets

Multi-stage builds help copy only needed artifacts to the final stage, yet:

- A secret written into the JAR during the build stage still reaches the final image inside the JAR.
- A secret written to a filesystem layer/build cache can persist in cache even if absent from the final stage.
- A RUN step copying a secret to a file and deleting it in a later instruction still leaves bytes in the earlier layer.
- Docker build logs, history, provenance, and exported caches can retain information if build commands handle secrets carelessly.

Therefore **never write secrets to outputs**, scan the final image, and manage builder/cache retention. BuildKit secret mounts protect transit into the build step; they cannot stop a build program that deliberately persists a secret.

## 9. Cloud Native Buildpacks and Spring Boot build-image

Spring Boot can create OCI images from an executable JAR via:

- Maven: spring-boot:build-image.
- Gradle: bootBuildImage.

Builders/buildpacks can accept environment variables to customize Java version, proxies, buildpack behavior, or image generation. Those variables are passed **to the builder** and must not be used as a vault for production secrets.

### 9.1. Use Build Environment Only for Non-Sensitive Values

Gradle Groovy DSL example:

~~~groovy
tasks.named('bootBuildImage') {
    environment['BP_JVM_VERSION'] = '17'
}
~~~

BP_JVM_VERSION is a non-sensitive buildpack option. Never place DATABASE_PASSWORD, API_TOKEN, private keys, or registry tokens in environment. Buildpacks can read the environment and write values into logs, layers, or caches depending on implementation.

Similarly, Spring Boot Maven Plugin has image.env; pass only non-sensitive buildpack values. Never feed runtime production secrets to the builder merely because the plugin accepts environment variables.

### 9.2. Bindings Are Not Automatically Secret-Safe

Spring Boot Gradle bootBuildImage supports bindings to mount volumes/paths into the builder container. When a buildpack supports a corresponding service binding, you can provision a temporary file outside the repository and mount it read-only:

~~~groovy
tasks.named('bootBuildImage') {
    // Bind mount example only; the buildpack must support the contract at this target.
    bindings = ['/run/ci-secrets/repository-binding:/platform/bindings/repository:ro']
}
~~~

The binding directory must follow the structure/metadata expected by that specific buildpack. A :ro mount prevents the builder from writing back to the source; it does **not** stop a buildpack from reading and copying a secret into a layer/cache. Inspect buildpack docs, source, and outputs; use short-lived tokens, read-only permissions, and temporary files outside the build context.

### 9.3. Do Not Confuse Buildpack Variables with Runtime Secrets

Some buildpacks (such as Paketo) support BPE_* variables to bake environment modifications into the image for every deployment. This configures runtime environment variables **stored inside the image**, suitable only for non-secret settings. Supply database passwords/tokens at runtime via a secret manager or file mount.

### 9.4. Registry Credentials When Pulling/Publishing Images

The Spring Boot plugin provides docker.builderRegistry to authenticate pulls of private builder/run images and docker.publishRegistry to publish application images. Credentials must come from the CI secret store—never written as literals in build.gradle or the POM.

Gradle Groovy illustration for the bootBuildImage task:

~~~groovy
tasks.named('bootBuildImage') {
    docker {
        publishRegistry {
            username.set(providers.environmentVariable('REGISTRY_USER'))
            password.set(providers.environmentVariable('REGISTRY_PASSWORD'))
        }
    }
}
~~~

CI must supply REGISTRY_USER/REGISTRY_PASSWORD only in the publish job. Never enable public debug logs/build scans that could expose configuration; restrict access to Gradle caches and CI logs. Better yet, use short-lived tokens scoped exclusively to pushing to the target repository.

The Maven plugin offers equivalent image.publishRegistry configuration. Use environment variables/CI secret mechanisms per plugin configuration—never hard-code them. Docker registry credentials differ from Maven dependency download credentials; never reuse the same token for both.

## 10. Keystores, TLS Private Keys, and Signing Keys

### 10.1. TLS Private Keys

Never place server.p12, server.key, client.key, or passphrases into src/main/resources, as they can end up in BOOT-INF/classes, WEB-INF/classes, or the image filesystem. Instead:

1. Store private keys/keystores in a secret manager or HSM/KMS per policy.
2. At deploy time, mount the file to a path readable only by the app user, e.g., /run/secrets/server.p12.
3. Put only the file path and property names in non-secret configuration.
4. Supply the passphrase via a secret file/runtime secret provider.
5. Restrict filesystem permissions; never copy files into working directories or log their contents.

### 10.2. Signing and Encryption Keys

Private keys used to sign JARs, sign container images, or encrypt data should not reside in builder images, application JARs, or final images. Prefer:

- HSM/KMS/remote signing services where private keys never leave as files.
- CI identities authorized to request signing for the specific artifact only inside release jobs.
- Short-lived keys/delegation via workload identity where supported by the platform.
- Detached signatures/attestations stored as separate release artifacts following verification procedures.
- Auditing who requested signing, which artifact digest was signed, and when.

If file-based private keys are unavoidable, mount them solely during the signing step with strict read permissions, keep them out of workspace caches and artifact outputs, and rotate/revoke them per lifecycle policy. **Never package private keys into an image so the application can sign arbitrarily.**

## 11. Inspecting JARs/WARs Before Publishing

### 11.1. Checking Suspicious Filenames and Paths

List entries in the executable JAR:

~~~bash
jar tf target/secret-safe-demo.jar
~~~

Search for filenames commonly associated with secrets (print paths only, never contents):

~~~bash
jar tf target/secret-safe-demo.jar | grep -Ei '(^|/)(\.env[^/]*|.*\.(pem|key|p12|jks)|settings\.xml|credentials[^/]*|secrets?[^/]*)$'
~~~

This is a preliminary check. Unfamiliar filenames are signals to investigate; secret files can be renamed to .properties, .dat, .bin, or placed inside any package.

### 11.2. Scanning Archive Contents, Including Nested JARs

A Spring Boot executable JAR contains BOOT-INF/classes/ and nested JARs inside BOOT-INF/lib/. jar tf outer.jar only lists nested JAR filenames; **it does not inspect the contents inside those JARs**.

Scan procedure:

1. Extract the outer archive into an isolated temporary directory.
2. Scan resource/class text files using a secret scanner with redaction enabled.
3. Recursively inspect nested JARs/WARs if the scanner does not traverse nested archives automatically.
4. Check application.properties, YAML, JSON, XML, .env, keystore filenames, PEM/SSH key headers, and generated build metadata.
5. Never write matched secrets into CI logs or tickets. Record only file path, rule, commit/artifact digest, and redacted context.
6. Delete the temporary directory per policy after completion.

Never run unzip -p or cat on files suspected of containing secrets with output flowing to CI logs. When confirmation is needed, use a scanner that returns redacted matches or inspect inside a controlled environment.

### 11.3. WARs and Other Archive Formats

For WAR files, inspect WEB-INF/classes/, WEB-INF/lib/, META-INF/, WEB-INF/web.xml, deployment descriptors, and nested libraries. For EARs or distribution ZIPs, scan every inner archive. Never limit checks to BOOT-INF paths because layouts vary across JAR/WAR/executable archives.

## 12. Inspecting OCI Images, History, and Build Caches

Secrets can reside in many places within an image:

- Image config/environment variables.
- Layer filesystems, including layers later hidden by newer layers.
- Dockerfile instructions/history and build provenance.
- Image labels, build metadata, and SBOM/attestations if custom tooling injects values.
- CNB buildpack launch layers, cache layers, or workspaces if a buildpack persisted credentials.
- Older registry artifacts by digest/tag, mirror copies, or runner caches.

### 12.1. Inspection Commands Requiring Caution

The following commands can reveal sensitive data if an image was misconfigured:

~~~bash
docker history --no-trunc secret-safe-demo:local
docker image inspect secret-safe-demo:local
docker save secret-safe-demo:local -o secret-safe-demo-image.tar
~~~

Run them in a terminal/CI job with appropriate access controls. **Never paste raw output** into chat, tickets, or public logs because history/config may contain leaked credentials. Use an image-aware scanner with redaction to check image config and layer filesystems; inspect provenance/attestations separately if generated by the pipeline.

### 12.2. docker save and Earlier Layers

A file deleted in a newer layer can still sit in an older image layer. Inspecting only the container's final filesystem can miss leaked secrets. Use a scanner that understands OCI/Docker layers, or export the image and inspect each layer without printing secret values.

If a secret is discovered in a pushed image, deleting the tag or pushing a new image **does not invalidate the old credential**. Registries may retain old blobs/digests until retention/garbage collection runs; mirrors and runner caches may also hold copies. You must revoke/rotate the secret and handle artifacts/registries under incident policy.

### 12.3. CNB Build Caches and Maven/Gradle Caches

If a buildpack or custom task writes a secret into a cached layer/output, the data may persist in:

- CNB build caches/launch caches/workspace volumes.
- Docker/BuildKit caches.
- Gradle local/remote build caches.
- Maven local repositories or CI workspaces.
- CI artifacts and test reports.

Never write secrets into cached outputs. If it happens, treat the cache as a copy of the secret: restrict access, delete/expire the exact scope, and rotate the credential. Never run docker system prune --volumes or wipe all shared runner caches indiscriminately; follow owner/retention policies and pinpoint the exact cache containing the data.

## 13. Git, .gitignore, .dockerignore, and Secret Scanning

### 13.1. Two Ignore Files Have Different Scopes

| File | Purpose | What it cannot do |
| --- | --- | --- |
| .gitignore | Prevents untracked files matching patterns from being added to Git. | Does not delete committed files, branches/tags/forks, or Git history. |
| .dockerignore | Excludes files from the Docker build context sent to the builder. | Does not block files COPYed from another stage or clean Git/older images. |
| CI artifact exclude | Excludes files from artifact uploads by rule. | Does not erase previously published logs/caches/images. |

A starter .dockerignore might look like:

~~~text
.git
**/.env
**/.env.*
**/secrets/**
**/*.pem
**/*.key
**/*.p12
**/*.jks
**/settings.xml
**/id_rsa*
**/id_ed25519*
~~~

Adapt it to your project structure. Never ignore a file actually required by the build just to make a pipeline pass; replace it with a secret mount or a path outside the build context.

### 13.2. Secret Scanning at Multiple Stages

Run scanners at multiple checkpoints:

- **Pre-commit/IDE:** catch tokens/keys pasted into source early.
- **Pull request/CI:** scan changed files and the source tree.
- **Git history:** scan commit history and branches/tags per policy.
- **Archive:** scan JARs/WARs and nested archives after packaging.
- **Image:** scan config, metadata, layers, and final filesystem before publishing.
- **Runtime/logs:** detect credential patterns, anomalous access, and secrets printed to logs.

Use an organization-approved scanner (such as Gitleaks, TruffleHog, or platform-integrated scanners) with redacted output. Never disable rules just because a secret scanner produces a false positive; triage, suppress narrowly by path/rule with justification, and review periodically.

### 13.3. Do Not Search Only by Filename

Secrets can be serialized as JSON/YAML/properties, base64, URL-encoded, split across parts, or embedded in class constants. Scanners must detect diverse token/key patterns and inspect archives/images. A regex matching .pem will miss a password in application.yml.

## 14. CI/CD: Granting Credentials to the Right Job and Step

### 14.1. Separating Identities by Privilege

A pipeline may need distinct identities:

| Job/step | Permissions needed | Should NOT have |
| --- | --- | --- |
| Resolve dependencies | Read-only access to required repositories. | Deploy/publish permissions. |
| Build application | Only source/build inputs and required build services. | Production database credentials. |
| Build image | Permission to pull builder/base images and build. | Application runtime API tokens. |
| Publish image | Push access to the exact target registry/repository. | Registry-wide admin privileges. |
| Deploy | Permission to deploy workloads/read runtime secrets. | Unrelated private signing keys. |
| Sign release | Request HSM/KMS to sign approved digests. | Export of private keys to the workspace. |

Use workload identity/OIDC or short-lived tokens where supported by the platform. Separate tokens for downloading dependencies, publishing images, and deploying; set strict expirations, audiences, and repository scopes.

### 14.2. Logs and Shells

Never do this in jobs holding secrets:

~~~bash
echo "$REGISTRY_PASSWORD"
env
set -x
mvn -X deploy
./gradlew --debug publish
~~~

env/printenv can dump all variables; shell tracing prints expanded commands; Maven -X/Gradle --debug can print sensitive config/metadata. Use set -eu instead of set -x. If a dynamic secret needs masking, invoke CI's masking mechanism before the value can appear in logs; masking never replaces avoiding logging altogether.

### 14.3. Workspaces and Artifacts

- Use dedicated runners/agents for sensitive jobs; never share writable workspaces with untrusted jobs.
- Place credential files outside the repository and Docker build context.
- Restrict retention of temporary settings, key files, reports, and caches.
- Never upload .m2/settings.xml, gradle.properties, .env, keystores, or secret mount sources as build artifacts.
- Delete temporary files in finally/post-job cleanup, remembering that **deleting files does not replace revoking credentials** if they were ever copied/logged.
- Protect build logs, test reports, Gradle configuration caches, and Docker daemon/registry access.

## 15. Complete Workflow Example: Maven Build, JAR, and Runtime Secret

### 15.1. Source Tree

~~~text
secret-safe-demo/
├── pom.xml
├── Dockerfile
├── .dockerignore
├── src/main/java/com/example/security/SecretSafeApplication.java
├── src/main/java/com/example/security/PartnerApiProperties.java
└── src/main/resources/application.properties
~~~

There are no settings.xml, .env, .pem, .key, keystore, or application-prod.yml files containing credentials in the project.

### 15.2. Resource Containing Only Non-Sensitive Configuration

src/main/resources/application.properties:

~~~properties
spring.config.import=configtree:/run/secrets/
partner.api.base-url=https://api.partner.example
server.port=8080
~~~

This file is packaged inside the JAR without any tokens/passwords. When the runtime platform mounts /run/secrets/partner.api.token, Spring Boot provides the partner.api.token property.

### 15.3. Java Application and Properties Class

SecretSafeApplication.java:

~~~java
package com.example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class SecretSafeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecretSafeApplication.class, args);
    }
}
~~~

PartnerApiProperties.java:

~~~java
package com.example.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiProperties {

    private String baseUrl;
    private String token;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getToken() {
        return token;
    }

    public void setToken(String token) {
        this.token = token;
    }
}
~~~

Application code calls getToken() when constructing the client's Authorization header. **Never log the object, token, Authorization header, or request exceptions carrying the header.** Never implement a toString() that includes the token.

### 15.4. Maven Build Credentials

CI creates/supplies user settings outside the project, using `<server><id>internal-releases</id>`... matching the repository ID. The token has read-only dependency access and expires/is revoked after the job. Never copy settings into src/main/resources or the Docker context.

### 15.5. Building Docker with a Secret Mount

Use the Dockerfile from Section 8.2. The docker buildx build --secret ... command mounts settings only for the Maven commands that resolve private dependencies. The output JAR contains only code and non-secret resources.

### 15.6. Supplying Runtime Secrets

At deployment, the platform mounts the secret file at /run/secrets/partner.api.token, readable only by the user running Java. configtree: loads the value into the Spring Environment. The runtime container needs neither Maven settings nor registry publishing tokens.

If a required token is missing, the app should fail fast per production configuration. Never put default dummy tokens in application.properties to mask deployment errors; tests must use separate fake credentials.

## 16. Example Checking Registry Credentials with Gradle BootBuildImage

A Gradle project can configure bootBuildImage to publish images. Use secret-backed environment variables provided by CI, for example:

~~~groovy
tasks.named('bootBuildImage') {
    docker {
        publishRegistry {
            username.set(providers.environmentVariable('REGISTRY_USER'))
            password.set(providers.environmentVariable('REGISTRY_PASSWORD'))
        }
    }
}
~~~

Never commit real values in build.gradle. CI exposes those two variables only in the publish job; compile/test jobs do not need them. Never print provider values or task configurations to logs. When configuration cache is enabled, protect GRADLE_USER_HOME and the cache encryption key per policy.

If the registry supports workload identity/short-lived tokens, prefer appropriate tokens over long-lived passwords. Builder registry credentials (pulling builder/run images) and publish registry credentials (pushing output images) can be two separate identities; assign matching permissions and scopes.

## 17. Pre-Publish Checks: Multi-Layer Checklist

### 17.1. Source and Repository

- [ ] No literal credentials in Java/Kotlin/Scala source, YAML, properties, XML, shell scripts, Dockerfiles, or tests.
- [ ] No private keys/keystores in the source tree.
- [ ] .gitignore and secret scanners configured; Git history scanned per policy.
- [ ] settings.xml/gradle.properties containing credentials are not committed.
- [ ] CI uses a secret store/short-lived tokens and does not echo values.

### 17.2. Build and Resource Processing

- [ ] Maven filtering applies only to an allowlist of non-secret resources.
- [ ] Gradle processResources/expand never receives secret properties.
- [ ] No task writes secrets into build outputs, generated sources, test reports, or build caches.
- [ ] Private repository credentials have only necessary read permissions.
- [ ] Maven/Gradle debug logs/build scans contain no credentials.

### 17.3. Archives

- [ ] JAR/WAR contains no .env, settings.xml, .pem, .key, .p12, .jks, or production configs with secrets.
- [ ] BOOT-INF/classes, WEB-INF/classes, resources, and nested JARs scanned.
- [ ] Text/config files scanned with a redacted secret scanner, not just checked by filename.
- [ ] No build-generated metadata, manifests, or test resources contain tokens.
- [ ] Archive matches exact version/commit and is signed/attested per release policy.

### 17.4. Docker/CNB Images

- [ ] ARG/ENV never used to pass passwords/tokens/private keys in Dockerfiles.
- [ ] settings/secret files never COPYed into images or build contexts.
- [ ] BuildKit secret/SSH mounts scoped only to required RUN steps; commands never copy/echo secrets.
- [ ] CNB buildpack environment contains only non-sensitive build options.
- [ ] When using bindings, buildpack contracts verified and secrets never written to layers/caches.
- [ ] Image config, history, filesystem layers, labels, and provenance scanned with redacted output.
- [ ] No secrets in build caches/launch caches/workspaces or CI artifacts.
- [ ] Registry credentials have only needed permissions and are granted only to the proper job.

### 17.5. Runtime and Operations

- [ ] Secrets supplied via secret manager or file mount with restricted read permissions.
- [ ] spring.config.import=configtree: points to the exact mount path.
- [ ] Required secrets never use optional: in production.
- [ ] Actuator/diagnostic endpoints protected; Environment/configuration never exposed.
- [ ] Logs contain no passwords, tokens, Authorization headers, private keys, or full connection strings.
- [ ] Rotation/revocation owner, expiration, audit trail, and incident runbook established.

## 18. Failure Scenarios and How to Handle Them

| Symptom | Possible cause | Action |
| --- | --- | --- |
| jar tf shows application-prod.yml or .env. | Production resource was copied into the archive. | Inspect the file in a controlled environment, rotate any secrets, switch to runtime external config, and rebuild. |
| BOOT-INF/classes/application.properties contains a password. | Hard-coded or resource filtering substituted a placeholder with a secret. | Remove secret from filter/source, rescan target/classes and JAR. |
| Secret absent from source yet appears in JAR. | Maven/Gradle task generated a resource or manifest containing the value. | Inspect process-resources, processResources, generated files, and plugin config. |
| Docker history displays a token. | Used ARG, shell command, or RUN with credentials. | Revoke token, migrate to BuildKit secret/SSH mount, rebuild image, and remediate old images/caches. |
| docker inspect shows password in Config.Env. | Used Dockerfile ENV or publish config persisted into runtime env. | Rotate password, remove from image config, inject runtime secret externally. |
| Final image lacks secret file yet scanner finds it in an older layer. | Secret was copied in an earlier layer and deleted in a later layer. | Rebuild from clean context, remediate old images/caches/registry blobs, and rotate credential. |
| BuildKit secret mount used properly yet image still leaks token. | RUN command copied token into output, generated file, or logs. | Fix the build command; mounts cannot stop build tools from writing secrets elsewhere. |
| bootBuildImage logs contain API token. | Token passed via builder environment or buildpack logged variables. | Rotate token, remove secret from builder env, use buildpack-supported binding/secret mechanism. |
| CNB image cache holds private settings. | Buildpack/custom build task saved credential file into cached layer/workspace. | Rotate, purge scoped cache per policy, fix buildpack/task not to cache secrets. |
| Maven fails to resolve private repository. | Wrong server ID, settings not supplied, or expired credential. | Check repository ID/secret injection; never paste passwords into POM or CLI flags. |
| Gradle reports missing repository credentials. | Repository name/property prefix mismatch or CI didn't expose variables. | Verify internalUsername/internalPassword mapping and secret scope; never add literals to scripts. |
| Maven encrypted password assumed fully secure. | Maven 3 encryption is obfuscation-grade only. | Protect settings/master files and use CI secret manager; never commit either. |
| Spring Boot fails to bind token. | Filename/path mismatches property or wrong spring.config.import. | Check mount path, filename/property mapping, and startup errors; never fix by bundling tokens in archive. |
| Container starts yet DB connection fails. | Secret not mounted, wrong permissions, or property source overridden. | Check secret mount/permissions and property precedence without logging passwords. |
| Secret scanner raises false positive. | Test/example file contains token-like string. | Confirm it is a dummy fixture, suppress narrowly by rule/path with rationale, keep scanner enabled. |
| Credential found in Git history. | File committed prior to being ignored. | Revoke/rotate immediately, audit access/logs, then plan history/fork remediation. |
| Old image remains in registry after pushing new version. | New tag does not delete old digests/blobs or mirrors/caches retain copies. | Revoke credential first; enforce retention/garbage collection and check mirrors/caches. |
| Token appears in CI log. | echo, set -x, debug mode, exception, or scanner printing raw matches. | Rotate/revoke, restrict log access, redact/handle logs per policy, and fix the pipeline. |

## 19. Incident Response When a Secret Leaks into an Archive/Image/Git

If a real credential is discovered in a JAR, image, cache, source file, or log, act in this order:

1. **Identify the secret type and permission scope.** A repository read token differs from a production DB admin password; assess privileges, audience, scope, and reachable systems.
2. **Revoke/rotate immediately.** Create new credentials, update the secret manager/deployments, and verify the old credential no longer works. Deleting a file from an image does not revoke the token.
3. **Containment.** Restrict access to registries/artifacts/logs/caches holding the exposure; block the old image from further deploy/pull if policy requires.
4. **Clean rebuild.** Fix source/build configs, build a fresh archive/image from clean inputs, and rescan all layers and nested archives.
5. **Remediate copies.** Audit Git history, branches/forks, registry digests, mirrors, CI artifacts, Docker/BuildKit/CNB caches, Gradle/Maven caches, and logs.
6. **Audit.** Review who could read the secret, exposure window, access logs, and credential activity during that period.
7. **History rewrite if necessary.** Only perform after rotation and coordination with owners/reviewers; rewriting Git history impacts clones/forks/commit references. Never treat rewriting as a substitute for rotation.
8. **Prevent recurrence.** Add scanners/rules, reduce privileges/TTLs, isolate secret stores, fix build tasks, and update runbooks.

When handling secrets in logs, follow audit retention and incident policies; restrict access and redact through proper procedures rather than deleting logs haphazardly to hide traces. Save redacted evidence—never copy plaintext secrets into tickets.

### 19.1. Why “Deleting the Secret from the Image” Is Not Enough

- Earlier image layers may still hold the bytes even if the final filesystem hides the file.
- Registries may retain old digests/blobs after a new tag is pushed.
- Docker daemons/remote caches/CI artifacts may still hold copies.
- Git history, forks, and local clones may retain commits containing the secret.
- Someone may already have read the credential during the exposure window.

**Rotation/revocation is what revokes access.** Purging copies reduces ongoing reuse and recurrence, but never replaces invalidating the exposed credential.

## 20. Hands-On Exercises and Acceptance Criteria

### Exercise A — Runtime Secret with Spring Boot Config Tree

1. Create a Spring Boot Java 17 app with PartnerApiProperties and SecretSafeApplication.
2. Set spring.config.import=configtree:/run/secrets/ in application.properties.
3. Create a dummy secret file in a temporary test folder named partner.api.token; never use a real token.
4. Start the app in a test environment with the config tree mounted.
5. Verify properties bind properly while the token never appears in logs/HTTP responses.
6. Confirm the JAR contains only non-secret config/path names, without any secret files or dummy values copied as resources.

### Exercise B — Maven Resource Filtering and Repository Credentials

1. Configure two resource directories: unfiltered main resources and filtered non-secret build metadata.
2. Place repository credentials in user/CI settings.xml with server ID matching repository ID.
3. Supply credentials via CI secret store/environment without committing settings.
4. Run mvn clean package and scan target/classes plus the executable JAR.
5. Verify filter files, effective settings/logs, and archives contain no passwords/tokens.
6. Document why Maven 3 password encryption does not replace a secret manager.

### Exercise C — Gradle Repository Credentials

1. Declare a private repository using credentials(PasswordCredentials) and an explicit repository name.
2. Supply internalUsername/internalPassword via ORG_GRADLE_PROJECT_... in CI.
3. Never write credentials into project gradle.properties or build scripts.
4. Run dependency resolution and scan build/resources/main/Boot JAR.
5. Protect Gradle user home/configuration cache; confirm build logs do not print credentials.

### Exercise D — Docker BuildKit Secrets

1. Create the multi-stage Maven Dockerfile from Section 8.2.
2. Create .dockerignore excluding settings, .env, secret directories, and private keys.
3. Use docker buildx build --secret ... to mount settings only inside Maven RUN steps.
4. Confirm the final image contains no settings/private keys.
5. Inspect image history/config/layers using a redacted scanner.
6. Test on a separate branch a misconfigured Dockerfile using ARG/ENV with a dummy token to observe scanner detection; never test with real credentials.

### Exercise E — CNB and Registry Auth

1. Configure bootBuildImage/spring-boot:build-image with non-sensitive builder options.
2. Separate buildpack environments from runtime secrets.
3. If bindings are needed, mount a temporary read-only file outside the source tree and verify buildpack support and no cache persistence.
4. Grant registry push tokens solely to the publish job.
5. Scan images/caches/logs after the build; confirm no tokens or private keys exist.

### Final Checklist

- [ ] No literal secrets in source code, POM, Gradle scripts, Dockerfiles, or resources.
- [ ] .gitignore/.dockerignore configured properly without treating them as secret managers.
- [ ] Maven/Gradle resource filtering never injects secrets into outputs.
- [ ] Maven repository credentials live in external settings/CI secret stores.
- [ ] Gradle uses typed credentials and secret-backed properties/environment.
- [ ] Never pass secrets via Docker ARG/ENV, never COPY settings/keys into images.
- [ ] Docker BuildKit secret/SSH mounts scoped to a single build step.
- [ ] Understand multi-stage builds do not automatically remove secrets written to caches/layers.
- [ ] CNB builder environment contains no runtime secrets; bindings verified against buildpack contracts.
- [ ] Spring Boot reads runtime secrets from configtree/file mounts or secret managers.
- [ ] Private keys/keystores absent from BOOT-INF/classes, WEB-INF/classes, and image filesystems.
- [ ] Never log tokens, passwords, Authorization headers, or entire config objects.
- [ ] Scan Git history, JARs/WARs, nested archives, OCI images/configs/history, and caches.
- [ ] Revoke/rotate, audit, and incident response processes established for leaks.
- [ ] Tested with dummy secrets and verified outputs contain no test values.

**Completion criteria:** an inspected executable JAR/WAR and OCI image containing no credentials/private keys/sensitive production configs; the build can resolve private dependencies and publish images using ephemeral external credentials; runtime receives secrets via configtree/secret manager; scan reports are redacted; and the learner can explain how to revoke/rotate if a secret ever leaks. Where real Docker/CI/secret managers are unavailable, note unverified steps and use dummy data rather than marking a security gate PASS from source review alone.

## Official References

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 — Maven Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3 — Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Docker — Build Secrets](https://docs.docker.com/build/building/secrets/)
- [Docker — Dockerfile ARG and ENV](https://docs.docker.com/reference/dockerfile/)
- [Docker — SecretsUsedInArgOrEnv Build Check](https://docs.docker.com/reference/build-checks/secrets-used-in-arg-or-env/)
- [Apache Maven — Settings and Server Credentials](https://maven.apache.org/settings.html)
- [Apache Maven — Password Encryption](https://maven.apache.org/guides/mini/guide-encryption.html)
- [Apache Maven — Resource Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Gradle — Handling Repository Credentials](https://docs.gradle.org/current/userguide/supported_repository_protocols.html)
- [Gradle — Build Environment and Project Properties](https://docs.gradle.org/current/userguide/build_environment.html)
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Cloud Native Buildpacks — Build-time Environment Variables](https://buildpacks.io/docs/for-platform-operators/how-to/build-inputs/build-env/)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)

**Remember:** archives/images are artifacts that can be copied, scanned, cached, pushed, and retained long-term. Therefore **secrets should only be supplied at the exact step that needs them**, runtime secrets must be injected at deploy time, and every archive/image must be scanned before release. If a credential ever leaks into Git, a JAR, an image, a cache, or logs, **revoke/rotate first**, then clean up copies and rebuild the product.
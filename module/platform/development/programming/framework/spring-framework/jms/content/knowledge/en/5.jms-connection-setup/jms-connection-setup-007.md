# Configuring Spring JMS Connections via Environment Variables Without Putting Secrets in Code

## 1. Problem Statement and Principles

A Spring application sending/receiving messages over JMS typically needs these parameters:

- Broker address: hostname, port, protocol, or connection URI.
- Connection credentials: username and password; sometimes tokens or provider-specific authentication details.
- Security settings: TLS, truststore/keystore, certificates, and queue/topic access permissions.
- Operational options: timeouts, reconnect, connection/session caching or pooling.

If you hardcode a password in Java source, a committed `application.yml`, build scripts, a Dockerfile, or project docs, that secret easily ends up in Git history, artifacts, image layers, CI logs, or backups. **The goal of externalized configuration** is: application code stays identical across environments; parameters and secrets are **supplied at deploy/runtime**, managed independently, and rotatable without modifying code.

Examples **to avoid**:

~~~java
// WRONG: real passwords must never be stored in source code.
String username = "admin";
String password = "production-password";
~~~

~~~yaml
# WRONG if this file contains a real password and goes into Git/images.
spring:
  artemis:
    user: admin
    password: production-password
~~~

The right approach with Spring Boot:

~~~text
CI/CD or secret manager / runtime environment
        │ supplies JMS_BROKER_URL, JMS_USERNAME, JMS_PASSWORD
        ▼
Environment variables of the Java process (or mounted secret)
        │ Spring Environment / property placeholders
        ▼
spring.artemis.broker-url / user / password
        │ Spring Boot JMS auto-configuration
        ▼
ConnectionFactory → JMS client library → Artemis broker
        │
        ▼
JmsTemplate / @JmsListener / business code
~~~

**Note:** environment variables separate configuration from source code, yet **they do not automatically encrypt or absolutely protect secrets**. Anyone with privileges to inspect runtime/container metadata or dump the process can read them. In production, use a secret manager, least-privilege access, TLS transport, and a credential rotation process.

## 2. Layers to Distinguish

| Layer | Example | Responsibility |
| --- | --- | --- |
| **JMS / Jakarta Messaging API** | `ConnectionFactory`, `JMSContext`, `Message` | Java contract for sending/receiving messages |
| **Spring JMS** | `JmsTemplate`, `@JmsListener`, listener containers | Manages JMS operations, resources, and consumers |
| **Spring Boot configuration** | `spring.artemis.*`, placeholders, `Environment` | Reads config and creates the `ConnectionFactory` bean via auto-configuration |
| **JMS provider/client** | Apache ActiveMQ Artemis JMS client | Implements the JMS API and communicates with the broker |
| **Secret delivery infrastructure** | OS environment, Docker/Kubernetes Secrets, Vault | Supplies username/password outside source code |
| **Broker** | Apache ActiveMQ Artemis | Authenticates, authorizes, routes, and stores messages |

Do not confuse the **application's broker password** with Git, registry, database, or OS login accounts. Each account should have the minimum permissions needed for its exact queues/topics. Do not mistake `spring.artemis.password` for a standard JMS protocol option: it is a **Spring Boot property for the Artemis provider**, not a universal property across all brokers.

**Distinguishing Spring Framework from Spring Boot:** Spring Framework provides Spring JMS but does not define the `spring.artemis.*` configuration namespace itself. Spring **Boot** (when the Artemis starter and auto-configuration conditions apply) reads those properties to build `ConnectionFactory`. In a plain Spring Framework app, developers configure `ConnectionFactory` themselves from `Environment`/`@Value` or equivalent dependency injection.

## 3. Configuring Spring Boot with Environment Placeholders

With Spring Boot 3.x, the Artemis starter uses the `jakarta.jms.*` namespace and common properties:

| Spring Boot property | Meaning |
| --- | --- |
| `spring.artemis.mode` | `native`: connect to a standalone Artemis broker; `embedded` is another option when dependencies/software support it |
| `spring.artemis.broker-url` | Broker URI used by the Artemis client |
| `spring.artemis.user` | Username for authenticating with the broker |
| `spring.artemis.password` | Corresponding password |
| `spring.jms.template.receive-timeout` | Timeout for synchronous `JmsTemplate` receives; not the default TCP timeout |
| `spring.jms.cache.session-cache-size` | Number of sessions cached in the connection factory wrapper when configured |

### 3.1. Option A: `application.yml` Contains Variable Names Only, No Secret Values

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: ${JMS_BROKER_URL}
    user: ${JMS_USERNAME}
    password: ${JMS_PASSWORD}
~~~

Spring resolves the three placeholders from the application's `Environment`. For example, an operator can supply:

~~~text
JMS_BROKER_URL=tcp://broker.example.internal:61616
JMS_USERNAME=orders-producer
JMS_PASSWORD=[secret value supplied only at runtime]
~~~

This **illustrates variable names**, not a requirement to commit lines with real passwords into the repository. Spring Boot uses `${PROPERTY_NAME}` syntax and supports defaults like `${PROPERTY_NAME:default}`.

- **Broker URL** can sometimes have a safe local default such as `${JMS_BROKER_URL:tcp://localhost:61616}`, though production should configure it explicitly.
- **Password** should use `${JMS_PASSWORD}` **without a weak default** like `changeme` or an empty string. This makes configuration errors surface early if the variable is missing.
- **Username** should also be provided at runtime; avoid implicitly falling back to a shared admin account.
- Avoid passing secrets via Java CLI arguments like `--spring.artemis.password=...` or `-D...` whenever possible, as command lines can show up in process listings and command audit logs.

An important property of `application.yml` in this example: **Git stores only the mapping between property names and environment variables**, never actual passwords.

### 3.2. Option B: Setting Properties Directly via OS Environment Variables

Spring Boot supports **relaxed binding**: environment variables can map directly to `@ConfigurationProperties`. The standard transformation rule: replace dots with underscores, **drop hyphens**, and uppercase. Examples:

~~~text
spring.artemis.user                → SPRING_ARTEMIS_USER
spring.artemis.password            → SPRING_ARTEMIS_PASSWORD
spring.artemis.broker-url          → SPRING_ARTEMIS_BROKERURL
spring.jms.template.receive-timeout→ SPRING_JMS_TEMPLATE_RECEIVETIMEOUT
~~~

Depending on the config source and version, some snake_case names may also bind via environment rules; **to avoid relying on name-normalization subtleties**, the hands-on example below uses `application.yml` with three explicit `JMS_*` placeholders. If you choose Option B, verify the binding with a configuration test on your exact Spring Boot version.

Do not set multiple redundant names simultaneously where one silently overrides another. Pick one project convention and document it in deployment guides.

### 3.3. Property Precedence Is Not a Security Mechanism

Spring Boot loads multiple configuration sources in a defined precedence order. Normally, environment variables override properties inside packaged files, and command-line properties take precedence over many file/env sources. This lets you deploy the same JAR to dev/test/prod.

However, **the highest-precedence source is not necessarily the safest source**. Prevent a stray CLI argument or local file from overriding production credentials. If you need to diagnose property sources, log only **source names and presence/absence**; never print password values.

~~~java
// Illustration: you can check variable presence, DO NOT print secrets.
boolean provided = System.getenv("JMS_PASSWORD") != null;
System.out.println("JMS_PASSWORD provided: " + provided);
~~~

This snippet is only for temporary debugging, not a requirement to log credential status in all environments. Production systems must not expose details about secret-storage mechanics in public responses.

## 4. Hands-On Demo: Spring Boot + Artemis + Docker Compose

This is a complete project for **Java 17+**, **Maven**, **Docker and Docker Compose v2**, and Spring Boot **3.5.7**. The goal is to use one configuration file with placeholders and inject credentials into containers **only at runtime**. The demo sends a simple message to verify `ConnectionFactory` uses the right settings. **No real passwords appear in source, JAR, or Docker images.**

### 4.1. Directory Structure

~~~text
jms-env-demo/
├── pom.xml
├── Dockerfile
├── compose.yaml
├── .dockerignore
├── .gitignore
├── .env.example
└── src/
    └── main/
        ├── java/com/example/jms/EnvJmsApplication.java
        └── resources/application.yml
~~~

`.env.example` holds **dummy placeholders** and may be committed. `.env` holds real values for your local machine only and **must be ignored by Git**. Some organizations forbid plaintext `.env` files even outside Git for production; use a secret manager there instead.

### 4.2. Maven — `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jms-env-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
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

`spring-boot-starter-artemis` lets Spring Boot configure the client and `JmsTemplate`. When using the Artemis provider, properties are `spring.artemis.*`. Do not use ActiveMQ Classic property names (`spring.activemq.*`) expecting them to configure Artemis.

### 4.3. Application Configuration — `src/main/resources/application.yml`

~~~yaml
spring:
  application:
    name: jms-env-demo
  artemis:
    mode: native
    broker-url: ${JMS_BROKER_URL}
    user: ${JMS_USERNAME}
    password: ${JMS_PASSWORD}
~~~

This file can be committed: it **contains no credentials**, only references to the three required variables. Actual URIs can vary between local host, Docker networks, and production infrastructure.

### 4.4. Java Application — `src/main/java/com/example/jms/EnvJmsApplication.java`

~~~java
package com.example.jms;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class EnvJmsApplication {

    public static void main(String[] args) {
        SpringApplication.run(EnvJmsApplication.class, args);
    }

    @Bean
    CommandLineRunner sendOne(JmsTemplate jmsTemplate) {
        return args -> {
            // Sample business payload, NOT a credential.
            jmsTemplate.convertAndSend("demo.env.config", "ping");
            System.out.println("JMS send OK");
        };
    }
}
~~~

There is no `System.getenv("JMS_PASSWORD")`, password, username, or broker address in the Java source. Spring injects `JmsTemplate`; Boot builds `ConnectionFactory` from values in `Environment`. `convertAndSend` operates through the JMS provider; if connection, authentication, or send authorization fails, the call throws an exception. This example checks **send succeeded**, not that a consumer processed the message.

Note that the demo Artemis broker may auto-create queues under default policy. Production should pre-provision queues/addresses and grant specific send/consume rights rather than relying on auto-creation for all destinations.

### 4.5. Dockerfile — Building Without Secrets

~~~dockerfile
FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/target/jms-env-demo-0.0.1-SNAPSHOT.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Do not declare `ARG JMS_PASSWORD` or `ENV JMS_PASSWORD=...` in the Dockerfile**. The build stage needs neither broker access nor secrets. Passwords must be supplied at **runtime**, avoiding image layers and metadata.

### 4.6. Docker Compose — `compose.yaml`

~~~yaml
services:
  broker:
    image: apache/artemis:latest-alpine
    environment:
      ARTEMIS_USER: ${JMS_USERNAME:?Set JMS_USERNAME in the environment}
      ARTEMIS_PASSWORD: ${JMS_PASSWORD:?Set JMS_PASSWORD in the environment}
    ports:
      - "127.0.0.1:61616:61616"

  app:
    build: .
    depends_on:
      - broker
    restart: "on-failure:5"
    environment:
      JMS_BROKER_URL: "tcp://broker:61616"
      JMS_USERNAME: ${JMS_USERNAME:?Set JMS_USERNAME in the environment}
      JMS_PASSWORD: ${JMS_PASSWORD:?Set JMS_PASSWORD in the environment}
~~~

Explanation of these decisions:

1. Compose substitutes `${JMS_USERNAME}` and `${JMS_PASSWORD}` at deployment time. The `:?` syntax in **Compose** causes missing or empty values to fail immediately; this is **not Spring placeholder syntax**.
2. The Artemis broker image accepts `ARTEMIS_USER` and `ARTEMIS_PASSWORD`, while the **app** receives `JMS_USERNAME` and `JMS_PASSWORD` for Spring to resolve placeholders. Both sides share the lab account for this demo.
3. On the Docker network, the broker's hostname is the **service name** `broker`: `tcp://broker:61616`. `localhost` inside the `app` container points to **the `app` container itself**, not the broker.
4. A short `depends_on` only orders container startup; **it does not prove the broker is ready to accept JMS connections**. `restart: "on-failure:5"` lets the app retry by restarting if the broker isn't ready on the first attempt. In production, use readiness/health checks and bounded retries at the appropriate layer.
5. Mapping `127.0.0.1:61616:61616` is only for the host running the demo; the `app` container talks over the internal network and does not require exposing the broker port externally.
6. Environment variables in this Compose config can be seen by anyone with permission to inspect containers/configs. **Compose env does not replace a production secret manager.**

### 4.7. Keeping Secret Files Out of Git and Docker Context

Create `.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
target/
~~~

Create `.dockerignore`:

~~~dockerignore
.git
.env
.env.*
target/
~~~

Ignoring `.env` in Git **is not an absolute guarantee**: a file once committed remains in Git history; `.gitignore` does not erase history. If a credential was exposed, **revoke/rotate** it on the broker and remediate the repository per security policy rather than merely adding an ignore rule.

Create `.env.example` with two placeholders **containing no real values**:

~~~dotenv
JMS_USERNAME=replace-with-local-user
JMS_PASSWORD=replace-with-local-password
~~~

On your local machine, copy that file to `.env`, then replace both placeholders with a username and password for your local lab. Never share `.env` over chat, email, PRs, issues, or build reports. Never put real passwords in screenshots.

Commands to copy on Bash:

~~~bash
cp .env.example .env
# Edit .env with an editor on your local machine, do not commit.
docker compose up --build
~~~

Commands in PowerShell:

~~~powershell
Copy-Item .env.example .env
# Edit .env in an editor before running.
docker compose up --build
~~~

Compose automatically reads `.env` in the project directory to **interpolate** `${JMS_*}` variables. The `.env` file does not automatically become the full environment of every container: the entries under `environment:` in `compose.yaml` explicitly pass values into `broker` and `app`. Do not confuse those two steps.

If the broker is running and the app is authorized to send, the app logs show:

~~~text
JMS send OK
~~~

Docker Compose and Spring Boot print additional logs; log ordering is not fixed. View app logs with:

~~~bash
docker compose logs app
~~~

Stop and clean up the demo containers/network:

~~~bash
docker compose down
~~~

`down` as above does not delete source files or your local `.env`. In a learning setup, to re-run after changing settings use `docker compose up --build`. Once a broker has a persistent volume storing state, check its account-update behavior before assuming changing a variable changes the password immediately: many images apply those variables only on **first broker initialization**, not as a dynamic rotation mechanism.

**Technical limitations of the demo:** the code and files are designed for the image/dependency versions listed above, but the example does not simulate a production secret store or TLS. Slow broker startup can cause the app to fail on its first attempt and require a retry/restart; if a demo depends on a moving image tag, pin the image digest in CI/CD.

## 5. Running the JAR Locally (Without Containerizing the App)

The same `application.yml` from section 4 also works when running Java directly on the host. When the broker runs on or is published to the host, `JMS_BROKER_URL` can be `tcp://localhost:61616`.

**Bash (Linux/macOS)** — setting session environment variables; obtain the password through an organization-approved secret-delivery workflow rather than hardcoding it in committed scripts:

~~~bash
export JMS_BROKER_URL="tcp://localhost:61616"
export JMS_USERNAME="local-user"
# Supply JMS_PASSWORD via secret manager or protected shell input.
mvn spring-boot:run
~~~

**PowerShell (Windows)** — setting non-sensitive variables:

~~~powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "local-user"
# Supply JMS_PASSWORD with a secret management tool before running.
mvn spring-boot:run
~~~

These two snippets are **intentionally incomplete** if `JMS_PASSWORD` has not been provided: the full Docker Compose exercise demonstrates supplying both values from an ignored `.env` file, whereas on the host directly, the secret must come from an appropriate mechanism on that machine.

If you use a secret store with a CLI, prefer a command or wrapper that **injects variables directly into the child process** without printing values to the terminal; exact commands depend on the product and permissions. Avoid pasting passwords into shell history, long CLI commands, or documentation examples. When finished, clear sensitive variables from the session/process per your organization's operational rules.

## 6. When Should You Use Mounted Secrets Instead of Environment Variables?

Environment variables are often a convenient starting point; however, for real production secrets, consider **secret files mounted into containers** or configuration supplied by Vault/Kubernetes/a secret manager. Spring Boot offers **configuration trees**: file names map to property keys, and file contents become property values.

Example mounted at `/run/secrets/`:

~~~text
/run/secrets/
  spring.artemis.user
  spring.artemis.password
~~~

You can import a config tree in `application.yml` (enable only in environments where secrets are mounted):

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  artemis:
    mode: native
    broker-url: ${JMS_BROKER_URL}
~~~

Then `/run/secrets/spring.artemis.user` holds the username and `/run/secrets/spring.artemis.password` holds the password. **Do not place secret contents in YAML.** If the secrets directory is absent, an import without `optional:` fails fast; using `optional:configtree:/run/secrets/` lets startup proceed without the secrets until hitting another error—choose based on your fail-fast policy.

**Distinguishing configtree from env placeholders:** a config using `${JMS_PASSWORD}` requires a `JMS_PASSWORD` property; the file `spring.artemis.password` produces the property **`spring.artemis.password`**. Therefore, when switching to configtree, remove or adjust conflicting placeholders. **Do not declare `spring.artemis.password: ${JMS_PASSWORD}` expecting a mounted file to satisfy a missing env var**, because placeholder values do not rename themselves into another property key.

Kubernetes can inject a Secret into environment variables using `secretKeyRef`, for example a YAML snippet in a container spec:

~~~yaml
env:
  - name: JMS_USERNAME
    valueFrom:
      secretKeyRef:
        name: orders-jms-credentials
        key: username
  - name: JMS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-jms-credentials
        key: password
~~~

This is only a **container config snippet**, not a standalone Deployment manifest. Secrets must be created outside source code by a pipeline or authorized operator. By default, Kubernetes Secrets distribute data through the cluster API and **do not automatically guarantee end-to-end encryption or automatic rotation**. Apply RBAC, encryption at rest, network security, and Pod rollout plans when credentials change.

Some secret managers also issue short-lived tokens or dynamic certificates. If your organization already standardizes on Vault, a cloud secrets manager, or workload identity, prefer the established integration.

## 7. TLS, Authentication, and Authorization: Three Distinct Layers

Secrets kept out of Git can still be leaked if usernames/passwords travel over an unprotected network connection.

1. **Authentication:** the broker verifies the client. The local demo uses `JMS_USERNAME/JMS_PASSWORD`.
2. **Transport security:** TLS encrypts network traffic and typically verifies the server's identity via certificates. Putting passwords in env vars **does not encrypt** JMS traffic.
3. **Authorization:** after authentication, the broker permits or denies specific actions such as send/consume/create on queues, topics, or addresses.

`tcp://broker:61616` in the demo is an internal learning endpoint, **not a production TLS configuration**. With Artemis, configure TLS acceptors/connectors according to the broker and client version docs, deliver trust material via mounts/secret managers, and enable certificate/hostname verification. Avoid putting key passwords or query-string passwords into URLs that might get logged.

Authorization example: a producer service needs only **send** permission on `orders.request`; a consumer needs corresponding **consume** permission; never default every service to an admin user. An `AuthorizationException`/`JMSSecurityException` after connecting should not be "fixed" by granting full broker admin rights.

## 8. Secret Governance Across Environments

### 8.1. Local Development

- Use a dedicated broker or test instance; lab usernames/passwords must differ completely from production.
- Any `.env` file, if permitted, must stay outside version control with restricted read permissions and never be synced to public shares.
- Never put real values into a committed `application-local.yml`. If local overrides are needed, verify the override file is properly ignored and was never committed.
- Non-sensitive settings like host/port/topic names may live in appropriate profiles; credentials are still injected at runtime.

### 8.2. CI Pipelines

- Supply credentials via secret variables/secret managers scoped strictly to the job and environment.
- Never put passwords in `pom.xml`, Maven resource filtering, build arguments, test snapshots, or artifacts.
- Restrict who can trigger pipelines using production secrets; never let pipelines running on untrusted pull requests read secrets.
- Never run `echo$JMS_PASSWORD`, `printenv`, `env`, or `docker compose config` where they might print secrets. Log masking is a mitigation, not a guarantee against every leak vector.
- Separate image building (no secrets) from deployment/running (with secrets). One image can be promoted across environments.

### 8.3. Staging/Production

- Every environment uses its own credentials; better yet, every service/role gets its own.
- Manage provisioning, rotation, revocation, auditing, and alerts for anomalous access.
- Scope secrets to the exact service account/namespace rather than sharing cluster-wide.
- With containers, recognize that environment variables can be inspected by operators with host/container privileges. Restrict access to logs, inspect, and exec.
- Rotating passwords requires coordinating both the application and the broker; applications using cached or pooled connections may need new connections or a restart to pick up new credentials.
- If a credential ever appeared in Git history, screenshots, or logs, **rotate it immediately** and clean up history/retention; deleting a line in a new commit does not remove the old secret from existing clones.

## 9. Common Configuration Errors

| Symptom | Possible cause | Safe check |
| --- | --- | --- |
| `Could not resolve placeholder 'JMS_PASSWORD'` | Variable not passed into **the app process**; Compose `.env` only interpolates and does not auto-inject | Check keys in Compose `environment`/orchestrator; verify presence/absence without printing values |
| `JMSSecurityException` or broker authentication failure | Wrong username/password, rotated account, mismatched TLS/auth settings | Verify secret source, account status, and redacted logs |
| `Connection refused` | Broker not running/not ready, wrong port, network, or firewall | Verify endpoint and readiness; do not try to "fix" by embedding passwords in URLs |
| `UnknownHostException: localhost` / Compose connection failure | App container used `localhost` instead of service `broker` | Use `tcp://broker:61616` on the Compose network |
| App starts up, then `convertAndSend` fails | Lazy connection not established at startup, missing send permission, wrong destination | Inspect the send failure and broker authorization |
| Works locally, fails in production | Different property sources, URI, DNS, TLS, network, or Secret namespace | Compare **config names and sources** without dumping full configs |
| Secret rotated, old connection stays alive | Connection pooling/cache out of sync with rotation | Recycle connections per procedure, shorten lifetimes if needed, perform rolling restarts |
| `@JmsListener` receives nothing despite send success | Wrong destination, missing consume permission, different listener config or routing | Check queue depth, consumer count, ack/transactions, and routing |
| Image build leaked secrets | `.env` copied into Docker context/image or hardcoded `ARG/ENV` | Audit Dockerfile, history, CI logs; rotate credentials and rebuild image |
| App uses unexpected values | CLI/Env/Profile/ConfigData precedence overrides | Verify property source precedence; never print passwords |

**Specifically:** `JmsTemplate` may open connections only when an actual send/receive happens, so an application "starting without errors" **does not prove** credentials work. An authorized send/receive smoke test gives a much stronger signal.

### 9.1. Debugging Without Leaking Secrets

Never print these into logs or public endpoints:

~~~java
// DO NOT do this:
System.out.println(System.getenv("JMS_PASSWORD"));
System.out.println(System.getenv());
~~~

With Spring Boot Actuator, `/actuator/env` and `/actuator/configprops` expose properties and configs. Secure those endpoints, restrict access, and configure proper sanitization; never expose them publicly just to inspect values. Even when values are masked, metadata and config names can still be sensitive.

Some teams check status with a probe **that reveals no values**:

~~~java
boolean hasUser = System.getenv("JMS_USERNAME") != null;
boolean hasPass = System.getenv("JMS_PASSWORD") != null;
if (!hasUser || !hasPass) {
    throw new IllegalStateException(
        "Missing required JMS credentials in runtime configuration");
}
~~~

This is an **illustrative snippet**, not a standalone class; you can place it in startup validation if you want fail-fast behavior. Distinguish **a variable being set** from **a valid value**; an empty string or revoked credential still fails to connect. The Compose `:?` check in section 4 catches both missing and empty variables early.

## 10. Minimum Testing and Acceptance Criteria

Before signing off on an externalized JMS configuration, include meaningful checks:

1. **Missing password:** Compose must refuse to start when `JMS_PASSWORD` is missing/empty; running outside Compose must fail clearly when placeholders are unresolved or authentication fails.
2. **Valid credentials:** broker accepts the connection, service is authorized to send, and the demo prints `JMS send OK`.
3. **Invalid credentials:** broker rejects the login and the app reports an auth error; logs must not contain the password.
4. **Wrong host/port:** connection error appears with controlled retries/readiness; never silently treat it as a successful send.
5. **Insufficient permissions:** if the user lacks send rights on the queue, tests must fail specifically with an authorization error.
6. **Multiple environments:** the same Docker image/JAR runs against different broker URLs and accounts without rebuilding.
7. **Git/Docker:** ensure `.env` is untracked and absent from image layers, artifacts, logs, and error reports; audit history if ever committed previously.
8. **Rotation:** change credentials in the secret store, update Pods/processes/connections per procedure, and verify new connections succeed while old credentials are revoked.
9. **Production TLS:** server certificates are verified and TLS settings are supplied and protected properly, rather than relying on the demo's plaintext TCP.
10. **Access boundaries:** operators hold only required privileges; restrict container inspect, exec, CI secret access, and config endpoints.

Integration tests can use a test/embedded/container broker with dedicated test credentials. Never place production passwords in test sources or fixtures. Verifying code never requires any production credentials.

## 11. Self-Check Questions

**Question 1.** Is it safe to move a password from Java source into `application.yml` and commit it?  
**Answer:** No, if the value in YAML is a real password it is still stored in Git. YAML should hold **placeholders or config paths/keys**, with real secrets supplied at runtime.

**Question 2.** Compose has `.env`, so why doesn't the Java app see `JMS_PASSWORD`?  
**Answer:** `.env` mainly serves Compose variable interpolation; the app only receives a value if Compose passes it into the container via `environment`/`env_file` or an equivalent mechanism.

**Question 3.** Why can `tcp://localhost:61616` work on the host yet fail inside the app container?  
**Answer:** `localhost` inside the app container points to itself. In the Compose example, the broker runs at service hostname `broker`, so the app uses `tcp://broker:61616`.

**Question 4.** Is putting the password in an env var enough for network security?  
**Answer:** No. You must add proper TLS, least-privilege broker permissions, suitable secret storage, and runtime access controls.

**Question 5.** Does the JVM automatically understand `spring.artemis.password` just because it is an env variable?  
**Answer:** Spring Boot's `Environment` and binding/placeholder mechanisms read it for beans/providers. With plain Spring Framework, you must bind properties to `ConnectionFactory` yourself.

**Question 6.** How do you deploy the exact same JAR to staging and prod without editing code?  
**Answer:** Supply each environment its own `JMS_BROKER_URL`, `JMS_USERNAME`, and `JMS_PASSWORD` or mounted secrets. Keep code and YAML placeholders identical while isolating permissions and security policies.

**Question 7.** When using `configtree:/run/secrets/` with file `spring.artemis.password`, do you also need `${JMS_PASSWORD}`?  
**Answer:** Not automatically; those are two different property names. Configure consistently so the secret file provides `spring.artemis.password` directly, or align the secret structure and placeholders.

**Question 8.** If a password was committed once and then removed in a later commit, is it safe?  
**Answer:** No. Git history and clones may still hold the old version; revoke/rotate it and handle the exposure per procedure.

**Question 9.** Should you log the entire `Environment` when a JMS error occurs?  
**Answer:** No. Log only filtered metadata, error codes, and config sources; lock down Actuator and check log sanitization.

**Question 10.** Why does a successful send not guarantee the consumer processed the message?  
**Answer:** A successful send mainly shows the client connected, authenticated/authorized, and the broker accepted the operation per semantics; consumer/ack/transaction/handler execution comes next.

## 12. Official Documentation

1. [Spring Boot Reference — Externalized Configuration: precedence, placeholders, environment variables, and config trees](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Boot 3.5 Reference — JMS/ActiveMQ Artemis configuration](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
3. [Spring Boot — Properties and Configuration](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html)
4. [Spring Framework Reference — JMS, ConnectionFactory, and JmsTemplate](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
5. [Apache ActiveMQ Artemis — Official Docker image and ARTEMIS_USER/ARTEMIS_PASSWORD](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)
6. [Docker Compose — Environment variables and interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
7. [Docker Compose — Define services, environment, depends_on](https://docs.docker.com/reference/compose-file/services/)
8. [Kubernetes — Distribute Credentials Securely Using Secrets](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/)

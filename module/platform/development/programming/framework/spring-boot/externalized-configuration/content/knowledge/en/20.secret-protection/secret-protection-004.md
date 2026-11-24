# Reading Docker Secrets and Kubernetes Secrets with configtree in Spring Boot 3.3

## 1. Goal and problem to solve

Spring Boot applications often need sensitive information to connect to databases, message brokers, or external services: passwords, API tokens, private keys, certificates, and environment-specific credentials. Placing these values directly in `application.properties`, `application.yaml`, or build artifacts can cause them to be saved in Git, images, pipeline logs, or overly shared configurations.

Docker and Kubernetes have mechanisms to supply secrets **as files inside the container**. Spring Boot 3.3 can read these files using Config Data's **configuration tree** feature with the prefix:

```properties
spring.config.import=configtree:/path-inside-container/
```

Core idea:

- Each **file** in the configuration tree carries one value.
- **Filenames and directories** form the property name in Spring `Environment`.
- **File contents** become the property value.
- After importing, the application can access the secret via `Environment`, `@Value`, `@ConfigurationProperties`, or standard auto-configuration.
- Importing **does not grant read permissions**, create secrets, encrypt data, or automatically hot-reload beans when secrets change.

For example, a container has:

```text
/run/secrets/
└── db.password      # a file containing the password, not a directory name
```

Declaring:

```properties
spring.config.import=configtree:/run/secrets/
```

makes the property `db.password` present in `Environment` with its value taken from the contents of `/run/secrets/db.password`. The dotted name `db.password` is valid: Spring Boot can map a filename containing dots directly into a configuration property path.

This is a mechanism provided by **Spring Boot Config Data**; Docker/Kubernetes itself is only responsible for placing files into the volume and managing workload access permissions.

## 2. What is a configuration tree?

Some platforms store configuration in a *single large file* format:

```yaml
db:
  username: user_demo
  password: example-only
```

Other platforms store it in a *one file per key* model:

```text
/etc/config/
└── db/
    ├── username   (content: user_demo)
    └── password   (content: a secret value)
```

Spring Boot supports both styles, but the import syntax differs:

| Input form | Appropriate import directive |
| --- | --- |
| A YAML file | `spring.config.import=file:/etc/config/application.yaml` |
| An extensionless file with YAML content | `spring.config.import=file:/etc/config/settings[.yaml]` |
| Directory with multiple key/value files | `spring.config.import=configtree:/etc/config/` |

**Do not use `file:/etc/config/` in place of `configtree:/etc/config/`.** The `file:` prefix is for configuration files in recognized formats; the `configtree:` prefix is for a tree of files where the filename itself is the key.

### 2.1. Directory structure determines the property name

Suppose the container sees:

```text
/etc/config/
└── myapp/
    ├── username
    └── password
```

With:

```properties
spring.config.import=configtree:/etc/config/
```

the created keys are:

```text
myapp.username
myapp.password
```

If you want the keys to be only `username` and `password`, import the **subdirectory**:

```properties
spring.config.import=configtree:/etc/config/myapp/
```

Here the relative path below the import point is used as the property name. The root directory only determines **which part of the path participates in the key name**, not another secret property name.

### 2.2. Filenames with dots

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

With:

```properties
spring.config.import=configtree:/run/secrets/
```

the application can receive two properties:

```text
spring.datasource.username
spring.datasource.password
```

This is especially useful when you want **direct integration with Spring Boot auto-configuration** without writing extra Java code to read files or concatenate strings. If the application uses Spring JDBC/DataSource and has complete JDBC configuration, the matching property names can be bound into `DataSourceProperties` by the Binder.

### 2.3. Both String and byte[] can be values

Spring Boot 3.3 documentation notes that configuration tree values can be bound as **`String`** or **`byte[]`** depending on the data type the application needs.

- `String` is suitable for usernames, passwords, and text-based tokens.
- `byte[]` is suitable when the application wants to preserve binary data or control the exact bytes of a key/certificate.

Do not assume every secret is clean UTF-8 text without newline characters. The format is determined by whatever creates the secret; when an API requires a string, define the encoding/newline policy of **your application** and produce the input file accordingly.

## 3. Two ways to write spring.config.import

### application.properties

```properties
spring.config.import=optional:configtree:/run/secrets/
```

### application.yaml

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Quotes in YAML help represent the full import string clearly.

Meaning of the prefixes:

- `spring.config.import`: specifies additional Config Data to import.
- `configtree:`: reads **filename → property key**, **file content → property value**.
- `/run/secrets/`: path as seen from **inside the container running the JVM**, not an absolute path on the developer's machine.
- `optional:`: allows skipping a **nonexistent location** rather than always failing startup due to a missing location.

If secrets are required to run production, do not use `optional:` as the default solution. A non-optional configuration detects **when the entire import directory is missing** early. Yet even if the directory exists, a specific key file may still be missing: validation or required checks are needed at the consuming property layer.

### When to use optional?

| Situation | Suggestion |
| --- | --- |
| Development without a secret volume | `optional:configtree:/run/secrets/` can be convenient |
| Production requiring an exact mount | `configtree:/run/secrets/`, combined with required-key checks |
| Certain credentials needed only per profile | Import in the appropriate profile document or configure per environment |
| Multi-environment deployment with different paths | Use standardized locations/volume mounts; control source precedence |
| Wanting to ignore invalid secret content | **Do not** use optional to mask value or permission errors |

`optional:` only controls how **location not found** is handled; it does not mean "if the file is unreadable or data is invalid, Spring will automatically pick another valid value."

## 4. Simplest Docker secrets example

Suppose the container running Spring Boot has the file:

```text
/run/secrets/db.password
```

The file content is the real password, without `db.password=...` syntax. You only need:

```properties
# application.properties inside the application
spring.config.import=configtree:/run/secrets/
```

Then read:

```java
String password = environment.getProperty("db.password");
```

or:

```java
@Value("${db.password}")
private String password;
```

Importantly, **Spring Boot does not look up the password by Docker service name or Docker Secret object**. It reads **the file the container actually sees**. Which file is mounted, at what path, and whether the user running the application can read it are responsibilities of Docker configuration.

### 4.1. Docker Swarm secret

In an initialized Swarm demo, you can create a secret from a file containing illustrative data:

```bash
# Use this demo file only for a test environment; do not commit.
docker secret create db.password ./local-secrets/db.password
```

When granting a secret named `db.password` to a Docker Swarm service, the secret is normally mounted inside the container at:

```text
/run/secrets/db.password
```

Example of granting the secret:

```bash
docker service create \
  --name catalog \
  --secret db.password \
  your-registry/catalog:1.0
```

If the image contains a Spring Boot application declaring `spring.config.import=configtree:/run/secrets/`, at startup it will read the `db.password` property from the mounted file.

**Conditions:** the service has permission to use the secret, the container runs with the right filesystem/mount, the file is readable by the JVM user, and the application actually starts from that image. Creating a Docker Secret without **attaching it to the service** will not make the file appear in every container.

### 4.2. Naming secrets to match properties

A Docker Secret named:

```text
spring.datasource.password
```

can be mounted as a file of the same name in `/run/secrets/`. With the right import, the property will be `spring.datasource.password`, directly matching auto-configuration. This is one way to avoid Java adapter code.

If the organization requires the Docker secret name to differ from the property name, you can use a target filename/alias mechanism supported by the deployment platform to mount it as the filename Spring Boot expects. Do not rename the source object and assume the mount path changes too without verifying.

### 4.3. Do not use `docker secret inspect` to fetch plaintext

Docker Secrets are meant to supply content to authorized workloads, not for querying plaintext arbitrarily via a metadata API. Do not write automation expecting `docker secret inspect` to return the secret value. Inspect from the container side **in a way that does not display contents**: does the file exist, does it have the right name, and is it readable.

## 5. Docker Compose: local example with file-backed secrets

With Docker Compose, you can declare secrets backed by host files:

```yaml
# compose.yaml -- example for local/demo environment
services:
  catalog:
    image: your-registry/catalog:1.0
    environment:
      SPRING_CONFIG_IMPORT: "configtree:/run/secrets/"
    secrets:
      - db.password

secrets:
  db.password:
    file: ./local-secrets/db.password
```

The application receives `SPRING_CONFIG_IMPORT` as the `spring.config.import` property. With a file-backed Compose secret, the contents of `./local-secrets/db.password` are deployed into the container as the corresponding secret file.

**Points to remember:**

1. `./local-secrets/db.password` is **on the host running Compose**, while `/run/secrets/db.password` is **inside the container**.
2. Local Docker Compose and Docker Swarm secrets **do not provide identical management/storage guarantees across all deployment modes**. In local Compose, secrets may rely on host files/bind mounts depending on the implementation.
3. The source file on the host needs appropriate access permissions and must remain outside Git/public artifacts.
4. Do not use `environment: DB_PASSWORD: ...` just to pass plaintext back into an environment variable if the goal is to limit where the secret appears.
5. Verify the image actually executes the Java command and `SPRING_CONFIG_IMPORT` is passed to the right service container.
6. If the application also has `spring.config.import` in a file, understand how configuration sources contribute to the import value. Do not accidentally configure two conflicting import locations.

### 5.1. Creating demo files more safely than echo

Example creating **a fake value** and avoiding unintended newline characters:

```bash
mkdir -p local-secrets
printf '%s' 'example-only-not-a-real-password' \
  > local-secrets/db.password
```

Note: this is a learning example only. When creating real secrets, do not put plaintext on the command line/logs/history, do not commit files containing secrets, and follow your organization's approved secret provisioning system.

In many shells, `echo` adds a newline; if the actual password does not contain a newline, that extra character can cause authentication to fail. Do not assume all libraries will always trim secrets the same way.

### 5.2. Reading multiple Docker secrets

```yaml
services:
  catalog:
    image: your-registry/catalog:1.0
    environment:
      SPRING_CONFIG_IMPORT: "configtree:/run/secrets/"
    secrets:
      - spring.datasource.username
      - spring.datasource.password
      - client.api-token

secrets:
  spring.datasource.username:
    file: ./local-secrets/db-user
  spring.datasource.password:
    file: ./local-secrets/db-password
  client.api-token:
    file: ./local-secrets/client-token
```

If the files are mounted under the declared names, Spring Boot reads:

```text
spring.datasource.username
spring.datasource.password
client.api-token
```

These names reside in `Environment`; the application can bind them into auto-configuration or custom `@ConfigurationProperties`.

## 6. Kubernetes Secrets as a volume

Kubernetes provides `Secret` to store sensitive data usable by workloads. A Secret can be passed into a Pod via environment variables or volumes. For Spring Boot `configtree:`, the appropriate approach is a **volume mount**.

Suppose a Kubernetes Secret named `catalog-db-credentials` has two keys:

```text
username
password
```

We want inside the container:

```text
/etc/secrets/db/
├── spring.datasource.username
└── spring.datasource.password
```

The way to do this is mapping the Kubernetes Secret keys to the **file paths** Spring Boot expects.

### 6.1. Creating a Secret for a demo from files

Illustrative example in a test environment, with two files safely created and not stored in Git:

```bash
kubectl create secret generic catalog-db-credentials \
  --from-file=username=./local-secrets/db-user \
  --from-file=password=./local-secrets/db-password \
  -n demo
```

Depending on organizational policy, Secrets may be created using External Secrets Operator, a CSI driver, GitOps with source encryption, or another secret-management system. The command above only shows the **Kubernetes key ↔ file content** relationship; it is not a recommendation to store real credentials in plaintext in a repo.

Do not share the output of `kubectl get secret ... -o yaml` publicly: data under `data` is normally **base64 encoding, not security encryption**. Apply encryption at rest, RBAC, and appropriate cluster secret governance measures.

### 6.2. Mounting into a Pod with items.path

Minimal complete Deployment section example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
  namespace: demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: app
          image: your-registry/catalog:1.0
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "configtree:/etc/secrets/db/"
          volumeMounts:
            - name: db-credentials
              mountPath: /etc/secrets/db
              readOnly: true
      volumes:
        - name: db-credentials
          secret:
            secretName: catalog-db-credentials
            optional: false
            items:
              - key: username
                path: spring.datasource.username
              - key: password
                path: spring.datasource.password
```

Kubernetes will supply the corresponding files in the volume:

```text
/etc/secrets/db/spring.datasource.username
/etc/secrets/db/spring.datasource.password
```

Spring Boot imports:

```properties
spring.config.import=configtree:/etc/secrets/db/
```

via the `SPRING_CONFIG_IMPORT` environment variable in the Deployment example. The result provides the `spring.datasource.username` and `spring.datasource.password` properties.

**You do not need to declare both an environment variable and a file** if you want a single place configuring the import: pick one consistent management location. In this Kubernetes example, the env var specifies the Config Data import *path*, containing no plaintext credentials.

### 6.3. Secret keys and filenames do not have to match

The section:

```yaml
items:
  - key: password
    path: spring.datasource.password
```

means:

- `password` is **the key inside the Kubernetes Secret object**.
- `spring.datasource.password` is **the filename inside the volume mount**.
- `configtree:` reads **the filename**, not the Secret object name in the Kubernetes API.
- Spring Boot receives the `spring.datasource.password` property because of the file path.

This lets you use one convention for Kubernetes Secret keys and another for Java/Spring property names without modifying the secret content.

### 6.4. Volume paths are container paths

Mount example:

```yaml
mountPath: /etc/secrets/db
```

requires importing:

```properties
spring.config.import=configtree:/etc/secrets/db/
```

If you mistakenly use a node/host path or import at a higher level such as `/etc/secrets/`, keys may gain an extra `db.` prefix:

```text
Import /etc/secrets/     -> db.spring.datasource.password
Import /etc/secrets/db/  -> spring.datasource.password
```

This is one of the most common mistakes: the file is present, yet the effective property name is wrong.

## 7. Kubernetes: mounting keys directly as files instead of `items`

Another approach is naming Kubernetes Secret keys to match Spring Boot property names directly. For example, create the Secret from a file named `spring.datasource.password`, then mount the entire Secret into a directory:

```yaml
volumes:
  - name: db-credentials
    secret:
      secretName: catalog-db-credentials
```

If the Secret contains the key `spring.datasource.password`, Kubernetes mounts the file:

```text
/etc/secrets/db/spring.datasource.password
```

when the Pod has:

```yaml
volumeMounts:
  - name: db-credentials
    mountPath: /etc/secrets/db
    readOnly: true
```

If the Secret uses a short key `password`, you have two choices:

1. Keep the file named `password` and import the root to receive `password`.
2. Use `items[].path` to rename it to `spring.datasource.password` before Spring Boot reads it.

Do not interpret dots in the filename as "a file extension that must be parsed as properties": `configtree:` treats the filename as the property key and does not expect the file to contain `key=value` structure.

## 8. Using `@ConfigurationProperties` to receive secrets

When you do not want to tie a secret directly to `spring.datasource.password`, create an application prefix, for example:

```text
/etc/secrets/app/
└── gateway/
    ├── username
    └── password
```

Importing:

```properties
spring.config.import=configtree:/etc/secrets/app/
```

yields:

```text
gateway.username
gateway.password
```

Java record:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public record GatewayCredentials(
        String username,
        String password) {
}
```

Registration:

```java
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
```

A Spring-managed service can receive the configuration via constructor injection:

```java
package com.example.demo.service;

import com.example.demo.config.GatewayCredentials;
import org.springframework.stereotype.Service;

@Service
public class GatewayClientFactory {

    private final GatewayCredentials credentials;

    public GatewayClientFactory(GatewayCredentials credentials) {
        this.credentials = credentials;
    }

    public void initializeClient() {
        // Pass credentials.username()/password() into
        // the client library the application uses.
        // Do not log or return secrets in HTTP responses.
    }
}
```

`@ConfigurationProperties` binding still has relaxed binding according to Spring Boot rules. Values coming from configtree do not remove prefix-based binding capability, though the model design must match the mounted filenames/paths.

### 8.1. Validation is needed for required secrets

If a credential must have content, use Jakarta Bean Validation:

```java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "gateway")
public record GatewayCredentials(
        @NotBlank String username,
        @NotBlank String password) {
}
```

If missing or only an empty/whitespace string, validation can reject startup when the project has an appropriate Bean Validation provider (commonly `spring-boot-starter-validation`).

A validation such as `@NotBlank` only requires content; **it cannot guarantee the secret is correct, unexpired, or granted access to the target system**. Authentication errors still need to be handled in the client/service.

### 8.2. Do not expose secrets via `record.toString()`

Java records generate `toString()` from their components. If a record contains a password, calling `logger.info("{}", credentials)` can expose the value. **Do not log entire credentials objects**, do not use arbitrary debug serializers, and do not include secrets in exception messages. Use a custom class that does not expose secrets in `toString()`, or mask data when display is unavoidable.

### 8.3. `String` vs. `byte[]` for binary keys

When mounting a binary key that is not text, do not bind it to a String and guess the encoding:

```java
@ConfigurationProperties(prefix = "crypto")
public record CryptoProperties(byte[] keyMaterial) {
}
```

Corresponding file:

```text
/etc/secrets/app/crypto/key-material
```

Configtree can provide data as bytes to the binder when the target expects `byte[]`. Note that the byte array still resides in application memory; this is **not a memory protection mechanism** or automatic zeroization of key material. Do not print Base64/hex of the key to logs.

## 9. Integrating with Spring DataSource auto-configuration

An application using Spring Boot JDBC typically has non-sensitive configuration in a file:

```properties
# src/main/resources/application.properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/catalog
spring.datasource.driver-class-name=org.postgresql.Driver
spring.config.import=configtree:/run/secrets/
```

Secret volume:

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

After Config Data import, Spring can see:

```text
spring.datasource.url               <- application.properties
spring.datasource.driver-class-name <- application.properties
spring.datasource.username          <- configtree
spring.datasource.password          <- configtree
```

If the project has Spring JDBC/DataSource auto-configuration along with an appropriate JDBC driver, these properties can be used according to standard `spring.datasource.*` rules. **Configtree does not create a JDBC driver, guarantee the DB server is running, or grant network access.**

The strength is that **the password does not need to reside in the JAR, source code, or `application.properties`**. Regular Java code does not need to write:

```java
Files.readString(Path.of("/run/secrets/..."));
```

just to pass the password into auto-configuration.

### 9.1. Using an intermediate key and placeholder

If the secret file is named `db.password` yet you want to use it for the Spring datasource:

```properties
spring.config.import=configtree:/run/secrets/
spring.datasource.password=${db.password}
```

Resolution path:

```text
/run/secrets/db.password
   -> Environment db.password
   -> placeholder ${db.password}
   -> spring.datasource.password
   -> DataSourceProperties
```

This is used when secret names follow a custom naming convention while the target is a framework property. Handle a missing `db.password` clearly; a placeholder without a default can fail when unresolved, or cause the configuration not to work as intended.

Another strategy is mounting the file as `spring.datasource.password` and importing directly, reducing alias layers.

### 9.2. Precedence on key collisions

Suppose a file has:

```properties
spring.datasource.password=example-insecure-default
spring.config.import=configtree:/run/secrets/
```

Imported Config Data has **higher precedence than the document declaring the import**. So if configtree supplies `spring.datasource.password`, the secret value can override the value in the file.

However, sources with higher precedence can still override it, such as a command-line option `--spring.datasource.password=...` or a matching OS environment variable. **Do not leave a fake password in a production configuration file** just thinking configtree always beats every source.

To avoid conflicts, supply the real password from only one trusted secret source and establish precedence rules upfront.

## 10. One secret object does not automatically map to a YAML file

Kubernetes Secrets can be volume-mounted in multiple ways. Distinguish:

**A. Multiple files:**

```text
/etc/config/
├── db.username
└── db.password
```

Use:

```properties
spring.config.import=configtree:/etc/config/
```

**B. One file containing complete YAML:**

```text
/etc/config/app-credentials.yaml
```

Illustrative contents:

```yaml
db:
  username: demo
  password: example-only
```

Use:

```properties
spring.config.import=file:/etc/config/app-credentials.yaml
```

If the file has no extension yet **its content is YAML**, use an extension hint:

```properties
spring.config.import=file:/etc/config/app-credentials[.yaml]
```

Do not use `configtree:` for case B expecting Boot to parse YAML **inside** a file: configuration tree treats **the entire file as the value of a single property** named after the file path.

### Extension hints do not replace configtree

`file:/etc/config/app-credentials[.yaml]` is a different syntax from `configtree:/etc/config/`. The `[.yaml]` marker specifies the format type **of the imported file**, not a secret tree structure. When a Secret volume mounts one file per key, do not add `[.properties]` to each key-value file.

## 11. Multiple configuration trees in the same deployment

Sometimes a workload has multiple secret sources:

```text
/etc/config/
├── dbconfig/
│   └── db/
│       ├── username
│       └── password
└── mqconfig/
    └── mq/
        ├── username
        └── password
```

You can import:

```properties
spring.config.import=optional:configtree:/etc/config/*/
```

The `/*/` wildcard syntax imports **immediate subdirectories** of `/etc/config/` as independent config trees. Keys can be:

```text
db.username
db.password
mq.username
mq.password
```

When wildcard importing, Spring Boot 3.3 sorts loaded directories **alphabetically by absolute path**. If there are overlapping keys and you want explicit override control, list the import locations explicitly.

### 11.1. Importing multiple locations explicitly

```properties
spring.config.import=\
  configtree:/etc/config/dbconfig/,\
  configtree:/etc/config/mqconfig/
```

In `application.yaml`, a list can be used:

```yaml
spring:
  config:
    import:
      - "configtree:/etc/config/dbconfig/"
      - "configtree:/etc/config/mqconfig/"
```

Imports are processed in configuration order; per Config Data rules, later imports can take precedence over earlier ones for the same key. Therefore avoid duplicate keys or document the override order clearly.

### 11.2. Using namespaces to avoid collisions

With multiple secrets like `username`/`password`, it is better to have:

```text
db.username
db.password
mq.username
mq.password
```

rather than mounting multiple trees that all supply the generic key `password`. Organize directories and filenames into meaningful property namespaces, then bind with `@ConfigurationProperties(prefix="db")`, `@ConfigurationProperties(prefix="mq")`.

## 12. `optional:`, startup failures, and fail-fast

Scenarios:

| Symptom | Interpretation | Resolution |
| --- | --- | --- |
| Missing directory, non-optional import | Startup can fail with `ConfigDataLocationNotFoundException` | Fix volume/mountPath or create location |
| Missing directory, optional import | Import may be skipped | Reasonable for local if credentials are not required |
| Directory exists, password file missing | Location loads, but required property does not exist | Validate/check required keys |
| File exists, unreadable | File permission/I/O error, not simply missing location | Check UID/GID, mount mode, policy |
| Empty file | Value may be an empty string | Block with validation or logic |
| File contains unintended newline | Actual value may differ from required string | Create secret file with right encoding and format |
| Wrong filename | Wrong property name | Fix `items.path`, Docker secret target, or import root |
| Docker/Kubernetes Secret object exists but Pod lacks mount | Spring does not see the file | Check volumes/volumeMounts/service secret grant |
| Configtree loads yet auto-config ignores value | Key name does not match framework/property expectation | Use canonical property name or placeholder |
| File changes after startup | Bound objects do not reload automatically | Design rollout/restart or explicit refresh |

**Security and fail-fast:** For required credentials, failing startup can be much better than running with a default, empty, or misconfigured connection password. `optional:` helps portability, yet must be used intentionally.

### Adding validation for required keys

Example:

```java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "db")
public record DbCredentials(
        @NotBlank String username,
        @NotBlank String password) {
}
```

Use a compatible Bean Validation provider and register the configuration properties to validate at startup. If the rest of the app does not use `DbCredentials`, do not register it solely to create an unused bean; choose whatever actually owns the configuration contract and validation.

## 13. File access permissions and the principle of least privilege

A secret volume is only useful if the right workload can read the value while unauthorized workloads cannot arbitrarily read it.

### 13.1. Components to distinguish

- **Docker/Kubernetes secret object:** where the platform manages data and secret-granting permissions.
- **Volume mount inside container:** where data is exposed as files.
- **Process user (UID/GID):** the Java process's identity when opening files.
- **Filesystem permissions:** mode, owner, group, and volume policy.
- **Cluster/container authorization:** RBAC, pod security, Docker service grants.
- **Application memory:** where secrets have been read by the Binder after startup.

`configtree:` does not elevate filesystem privileges. If the container runs as non-root while the file is only readable by root, the application may fail to read it. If you loosen permissions with `chmod 777` just to get it to start, you weaken the security boundary; solve it properly in the mount configuration, `runAsUser`/`runAsGroup`/`fsGroup`, and platform policies.

### 13.2. Kubernetes: `readOnly` and Secret volume permissions

```yaml
volumeMounts:
  - name: db-credentials
    mountPath: /etc/secrets/db
    readOnly: true
```

`readOnly: true` clearly expresses that the application **only reads**, never writes back to secrets. For Secret volumes, Kubernetes supplies data through its own volume mechanism; administrators can also adjust the permission mode per pod and driver requirements.

Do not pick an arbitrary `defaultMode` without checking the actual user/group, because setting it too tight can block the process from reading, while setting it too broad increases the exposure scope.

### 13.3. Do not put secrets into the image

Do not use:

```dockerfile
COPY local-secrets/db.password /run/secrets/db.password
```

for real secrets, because the file can persist in image layers/registries. With Docker/Kubernetes, the proper goal is **supplying secrets when the container runs**, not baking them into the image.

Similarly, do not put secrets into Dockerfile `ARG`, `ENV`, or CI output logs unnecessarily. Using `configtree:` at runtime aims to avoid many of these leak paths.

### 13.4. Secrets can appear in memory

Once Boot binds `spring.datasource.password` or `GatewayCredentials.password` into a String, plaintext exists in process memory. The configtree mechanism reduces managing secrets in config text and environment variables, yet **does not make secrets vanish after binding**. Do not claim file mounting is an end-to-end encryption solution.

## 14. Kubernetes: when a Secret changes, does the application pick it up automatically?

Do not treat these two things as equivalent:

1. **Kubernetes updates secret volume contents** via kubelet's mechanism.
2. **Spring Boot reloads Config Data and rebinds beans**.

For Secrets mounted as volumes, Kubernetes updates files after a certain delay in normal mount setups. However, **Spring Boot 3.3 does not automatically reload all Config Data and refresh every `@ConfigurationProperties` bean simply because a file changed**. Beans, connection pools, and clients created from old credentials can keep using those values.

**Kubernetes exception:** if a Secret file is mounted via `subPath`, standard Secret updates **are not reflected** in the container through the volume update mechanism. Account for this when designing rotation.

### 14.1. Practical rotation options

A typical operational workflow:

1. Issue the new secret via the secret management system.
2. Update the Kubernetes Secret or mounted secret source.
3. Perform a controlled rollout/restart of Pods so the application starts and rebinds Config Data.
4. Verify connectivity with the new credential.
5. Revoke the old credential after an appropriate transition window.
6. Monitor error rates, connection pools, and access permissions.

Custom reload can be designed using Spring Cloud/CSI integration or a custom file watcher, but it must manage atomic reads, validation, client connection updates, and retries. **Do not assume Kubernetes volume projection + configtree = live refresh**.

### 14.2. Docker secrets and changing passwords

Docker Swarm secrets are normally managed as immutable secret objects following the platform's versioning/rotation mechanisms. To change a credential, the process may require creating a new secret, updating the service, and replacing tasks/containers. Do not assume editing a host file is enough to update every attached Swarm secret.

Local Docker Compose using file-backed secrets has a different deployment mechanism, so re-verify mounts/contents after changing files and normally restart the service when you want the application to read the new value.

## 15. Newlines, whitespace, and encoding issues

There are cases where a file has:

```text
my-password<newline>
```

yet the actual password is only:

```text
my-password
```

Some tools that create files using `echo` append a newline. Different libraries/drivers may or may not handle whitespace differently; do not rely on Boot or clients arbitrarily trimming it.

**Implementation recommendations:**

- Choose an encoding, usually UTF-8 for text secrets.
- If the value does not need a trailing newline, create the source file without one.
- Do not print the file for debugging; compare length or checksums only after considering information exposure risks and controlling logs.
- For binary keys/certificates, target `byte[]` or use a library that reads the file directly when exact bytes must be preserved.
- Check the secret provisioning system's policy: some secrets legitimately have trailing newlines, and some are multiline JSON/PEM.
- Do not blindly apply `trim()` to every secret; it can alter a value in which the issuer intentionally included whitespace.

### A file containing `key=value` is not the same as a file containing a value

Correct for `configtree:`:

```text
/run/secrets/db.password
  file content: example-password
```

Incorrect:

```text
/run/secrets/db.password
  file content: db.password=example-password
```

The second case makes the `db.password` property have **the entire string `db.password=example-password` as its value**, because configuration tree does not parse individual files in properties format.

## 16. Putting multiple secrets into one Secret volume: naming approach

Example of an application integrating with two systems:

```text
/etc/secrets/
└── app/
    ├── db/
    │   ├── username
    │   └── password
    └── payment/
        └── api-token
```

Import:

```properties
spring.config.import=configtree:/etc/secrets/app/
```

Result:

```text
db.username
db.password
payment.api-token
```

You can bind:

```java
@ConfigurationProperties(prefix = "payment")
public record PaymentCredentials(String apiToken) {
}
```

Matching `payment.api-token`. However, Kubernetes native Secret keys cannot arbitrarily contain `/`; to create nested directory structures you need appropriate `items.path` entries in the volume projection, or multiple volumes arranged in a clear layout.

In Kubernetes, a Pod can also mount multiple Secret volumes at separate mount paths; then use multiple locations or `configtree:` wildcards if appropriate.

### Benefits of namespaces

- Avoids two secrets from different systems both writing the key `password`.
- Enables authorization per workload and function.
- Makes it easy to move from one secret object to another while keeping property names.
- Reduces errors caused by differing import roots.
- Makes describing and validating each property group easier.

Do not use one shared directory holding every credential in the cluster and mount everything into every Pod. The principle of least privilege recommends granting workloads only the secrets they genuinely need.

## 17. Dotted property names and relaxed binding

Spring Boot documentation confirms that a filename `myapp.username` maps directly to the property `myapp.username`. Thus, two layouts can produce the same property name:

**Layout A: nested directories**

```text
/etc/config/myapp/username
```

Import:

```properties
spring.config.import=configtree:/etc/config/
```

**Layout B: dotted filename**

```text
/etc/config/myapp.username
```

Import:

```properties
spring.config.import=configtree:/etc/config/
```

Both can produce `myapp.username`. Pick one convention within the same system; avoid supplying two files with the same property name simultaneously and expecting precedence within a single configtree to always be obvious to operators.

### Canonical property names

For `@ConfigurationProperties`, use lowercase kebab-case for compound words:

```text
service.auth.client-secret
```

You can mount the file `service.auth.client-secret` or create the directory structure `service/auth/client-secret` under the import root. The Binder maps `client-secret` to the Java property `clientSecret` via relaxed binding.

Do not assume arbitrary characters like slashes in keys will always be preserved across all sources. If complex Map keys are needed, design a naming convention and check paths; avoid using filenames with characters unsuitable for filesystems/volumes.

## 18. Where should `spring.config.import` be placed?

There are multiple ways to supply the import location:

### A. Inside the packaged `application.properties`

```properties
spring.config.import=optional:configtree:/run/secrets/
```

Fits when the application always expects a fixed path, while local development may not mount secrets. If production requires it, use validation or a profile-specific configuration rather than trusting `optional` alone.

### B. Inside `application-prod.yaml`

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

Loaded when the appropriate production document/profile applies; understand how active profiles and Config Data work. Do not place properties restricted to non-profile-specific documents into invalid profile regions, though `spring.config.import` can be declared following Config Data import rules and document activation.

### C. Via container environment variable

```yaml
env:
  - name: SPRING_CONFIG_IMPORT
    value: "configtree:/etc/secrets/db/"
```

Here the env var **contains no password**; it only specifies the secret volume path. This is convenient when the same image is deployed to different environments with different mount paths.

### D. Via command-line argument

```bash
java -jar app.jar \
  --spring.config.import=configtree:/run/secrets/
```

Again, this only supplies the path. For startup properties, the source must exist during the stage when Spring Boot loads Config Data; the path must exist in the environment/container when the JVM starts.

**Do not use an `ApplicationRunner` to set `spring.config.import` expecting Boot to go back and load new secrets:** Config Data has already been processed by then.

## 19. Diagnosing when secret files are mounted yet the application does not pick them up

Check in order:

1. **Mount point:** does the file actually exist inside the running container?
2. **Right Pod/service:** was the Secret assigned to that workload or does it only exist in the cluster/Swarm?
3. **Path:** does `spring.config.import` point to the right path inside the container, and end with `/` for directories?
4. **Import root:** is the file directly at the root or in a subdirectory, giving the property a different prefix?
5. **Filename:** does it match the exact property key to read, or is an alias needed?
6. **Read permissions:** can the user running the JVM read the file, not blocked by security context or mount permissions?
7. **File data:** does the file contain the **value**, rather than an unintended `key=value` line?
8. **Higher-precedence sources:** does an env var, CLI, or another Config Data source override the same property?
9. **Missing required key:** the directory may exist even though a critical secret file is missing.
10. **Encoding/newline:** the secret string might contain unintended characters.
11. **Timing:** the import must take effect during Config Data startup, not be set late.
12. **Application configuration:** is the `@ConfigurationProperties` bean registered, do field/record names match, and is validation working?
13. **Rotation:** has the Pod restarted; are beans/connection pools using the new secret?
14. **Is `optional` used appropriately:** `optional` can skip a missing location, causing errors to surface later in clients.
15. **Platform limitations?** Secret volumes with `subPath` do not automatically receive updates like standard mounts.

### Checking only file existence

In a Linux container, for files **whose names are not sensitive**, a conceptual check command is:

```bash
test -r /run/secrets/db.password && echo readable
```

This command does not print plaintext. Under strict policies, even path names can reveal operational details; run only in authorized environments and never use `cat` or `printenv` to dump secrets.

Kubernetes can use `kubectl describe pod` or `kubectl get pod -o yaml` to inspect volume/mount configuration without retrieving secret values. However, these commands can show sensitive infrastructure metadata, so permissions and sharing practices still apply.

### Why not use env to debug passwords?

When importing from configtree, passwords **do not have to become OS environment variables**. Running `printenv` and not seeing `DB_PASSWORD` does not prove Spring has not read the secret. Checking the right property name via Spring `Environment` can show the imported source, yet **raw values must never be logged**. Use presence checks or verify downstream authentication in a secure environment.

## 20. Diagnosing from Spring Environment without exposing values

You can check whether a key resolves to a value **without printing plaintext**:

```java
package com.example.demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class SecretPresenceDiagnostics {

    @Bean
    ApplicationRunner checkSecrets(Environment env) {
        return args -> {
            boolean usernamePresent =
                    env.containsProperty("spring.datasource.username");
            boolean passwordPresent =
                    env.containsProperty("spring.datasource.password");

            System.out.println("DB username configured: "
                    + usernamePresent);
            System.out.println("DB password configured: "
                    + passwordPresent);
        };
    }
}
```

**Limitations of this check:**

- `containsProperty` does not prove the value came from **configtree**; it could be a file, env var, or CLI.
- A present value could be an empty string; presence does not guarantee the secret has content.
- A present secret that is wrong/expired can still cause connection failure.
- `ApplicationRunner` only runs after the context initializes; if Config Data import causes startup failure, diagnose via startup logs instead of a Runner.

If you need to identify the property source during an investigation, use only authorized tools and avoid printing raw values. Actuator endpoints `/actuator/env` and `/actuator/configprops` can contain configuration metadata and must have explicit protection and sanitization; do not expose them publicly for debugging.

## 21. Testing `configtree` without real Docker/Kubernetes

To verify whether the application reads the **filename → property name layout** properly, you can create a fixture directory in test resources or a temporary directory, then launch a context/test app with the import location pointing to it.

Illustrative fixture directory example:

```text
src/test/resources/secret-fixture/
├── gateway.username
└── gateway.password
```

The file values are **fake data for testing**, not production credentials.

In an integration test using `@SpringBootTest`, you can supply the import property explicitly:

```java
package com.example.demo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

@SpringBootTest(properties = {
    "spring.config.import=optional:configtree:classpath:/secret-fixture/"
})
class ConfigTreeFixtureTest {

    @Autowired
    Environment env;

    @Test
    void readsSecretKeyFromTree() {
        assertThat(env.getProperty("gateway.username"))
                .isEqualTo("demo-user");
    }
}
```

**Note on bootstrap in tests:** `spring.config.import` is processed very early in the Config Data pipeline, so test properties added late in a context do not necessarily reproduce every import decision. For reliable integration tests, put the import in an `application-test.properties` file or supply it as an **early Environment property** to the Spring Boot test process, and use a **filesystem path** if configtree loading requires a real directory. Do not conclude from the test annotation example above that every test runner loads a classpath configtree like a filesystem directory.

A more stable way to test exact production behavior is creating a **temporary directory on the filesystem**, writing dummy `gateway.username` and `gateway.password` files, and starting the app/test with `spring.config.import=configtree:/path-to-dir/` supplied from the start. Check key names, values, read permissions, and property precedence. Never copy real secrets into test fixtures.

### 21.1. Testing with `@ConfigurationProperties`

Once the import takes effect in `Environment`:

```java
assertThat(credentials.username()).isEqualTo("demo-user");
assertThat(credentials.password()).isEqualTo("example-only");
```

If you need to test parsing binary contents, target `byte[]` and compare bytes in local unit tests; avoid printing them in assertion messages when data could be sensitive.

### 21.2. What cannot be concluded from pure unit tests

Tests with `MapPropertySource` can verify binding, yet **do not** prove Docker/Kubernetes mounts have the right path, permissions, Secret items, or startup import. For this scenario, have at least one smoke test inside a container with a dummy secret volume.

## 22. Choosing `configtree` or environment variables?

| Criterion | Configtree (volume file) | OS environment variable |
| --- | --- | --- |
| Provisioning mechanism | File mounted in container | Value placed into process environment |
| Docker Swarm/K8s Secret volume fit | Very suitable | Can use other sources |
| Spring Boot access | `spring.config.import=configtree:...` | Default Environment PropertySource |
| Representing binary secrets | Can use files/`byte[]` | Difficult and usually needs encoding |
| Exposure in process environment | Not required | Value present in environment |
| Root/path affects property name | Yes | Variable name affects property name |
| IAM/RBAC/mount permissions needed | Yes | Yes, depending on infrastructure |
| Auto-refreshes Spring beans | No | No |
| Secret rotation | Needs rollout/refresh strategy | Usually needs restart for process to receive new env |
| Risk of accidental logging | Still exists if app logs values | Still exists if env is dumped |

**Do not claim file mounts are always absolutely safer than environment variables.** Protection depends on secret management infrastructure, file permissions, namespace/isolation, processes, logging, and release mechanisms. Configtree is a very convenient integration option for secret volumes; it **does not replace secret governance**.

## 23. Common mistakes and fixes

### Error 1 — Importing the wrong host path

```properties
spring.config.import=configtree:/home/developer/secrets/
```

Yet the container only sees `/run/secrets/`. Fix to the path **inside the container** and configure the corresponding volume.

### Error 2 — Missing `configtree:` prefix

```properties
spring.config.import=file:/run/secrets/
```

A directory containing multiple key/value files must use:

```properties
spring.config.import=configtree:/run/secrets/
```

### Error 3 — File named `password` while code reads `db.password`

```text
/etc/secrets/db/password
```

Import `/etc/secrets/db/` for key `password`; import `/etc/secrets/` for key `db.password`. Choose the root matching the code.

### Error 4 — Kubernetes Secret exists yet is not mounted

Having a `Secret` object in the namespace does not make it automatically visible in every Pod. Add `volumes.secret.secretName` and the corresponding `volumeMounts`.

### Error 5 — Secret key differs from expected file path

Kubernetes key `password` is mounted as-is, yet Spring needs `spring.datasource.password`. Use `items[].path` or placeholder mapping.

### Error 6 — Using `optional` in production and missing a missing mount

`optional:configtree:...` can skip nonexistent directories. When secrets are required, use non-optional and validation for specific keys.

### Error 7 — Filename is `db.password.properties`

Configtree does not strip `.properties` assuming "a file containing the `db.password` property"; it treats the filename as the corresponding key. If you want `db.password`, name the file exactly `db.password` or change how the file is imported based on its format.

### Error 8 — Putting `db.password=...` inside the `db.password` file

The entire string `db.password=...` becomes the **value**, because configtree does not parse individual files as properties documents.

### Error 9 — Secret file only readable by root while app runs non-root

Fix volume permissions and security context; do not bypass security by running all containers as root or opening permissions across the entire filesystem.

### Error 10 — Changing the Secret yet Spring keeps using the old password

A proper restart/rollout or refresh plan is needed. Volume files may update, but `@ConfigurationProperties` objects and DataSources do not update automatically.

### Error 11 — Mounting a Secret via `subPath` and expecting auto-update

Kubernetes `subPath` has update limitations for Secret volumes; avoid it when expecting new file projections to appear without restart.

### Error 12 — Using `ConfigMap` to store passwords because both work with `configtree`

`ConfigMap` is for non-sensitive configuration; to manage credentials, use `Secret` or an organization-approved secret management solution. `configtree:` can read both mount types, yet **does not turn a ConfigMap into a secret**.

### Error 13 — Logging the entire Environment to prove it loaded

Do not log plaintext. Check only presence, non-sensitive keys, and downstream authentication results in a controlled environment.

### Error 14 — Secret double base64-encoded

Kubernetes `data` takes base64-represented bytes, while `stringData` allows passing plaintext for the API server to convert into Secret data; when mounted, the volume file contains **decoded bytes**, not base64 text in normal setups. Do not base64-decode again in Spring if the source already provided the right bytes, unless the application intentionally stores an extra encoding layer.

### Error 15 — Looking only at `@Value` defaults and not checking files

`@Value("${db.password:}")` with an empty default can let the application run with an empty password when the secret is missing. For production credentials, prefer fail-fast and validation over silent fallbacks.

## 24. Recommended production deployment workflow

1. **Design property names** first: e.g. `spring.datasource.username`/`spring.datasource.password` or `gateway.username`/`gateway.password`.
2. **Separate sensitive data from images and source control**; supply secrets via Docker Swarm/Kubernetes or an approved secret-management system.
3. **Standardize container mount paths**: e.g. `/run/secrets/`, `/etc/secrets/db/`.
4. **Define filenames or `items.path`** matching property names; if namespaces are needed, use subdirectories and specify the import root.
5. **Declare `spring.config.import=configtree:...`** in the appropriate startup source. Use `optional:` only when a missing volume is an acceptable scenario.
6. **Restrict secret-granting permissions** to the exact workloads, namespaces, and users/groups needing read access.
7. **Configure validation** for required secrets, avoiding empty defaults in production.
8. **Verify property source precedence** so values are not unintentionally overridden by CLI/env/other configs.
9. **Test inside containers with dummy secrets**, including paths, filenames, newlines/encoding, and non-root users.
10. **Protect logging, Actuator, and diagnostics**, and never put secret values into error responses.
11. **Design rotation**: changing secrets, controlled restart/rollout/refresh, monitoring connections, and revoking old credentials.
12. **Document ownership and operational procedures**: who provisions secrets, rotates secrets, checks permissions, handles missing mounts, and responds to incidents.

### Pre-release checklist

- [ ] Secrets are not in Git, artifacts, Dockerfiles, or image layers.
- [ ] Containers have volume mounts at the right paths.
- [ ] Filenames match the canonical property names the application expects.
- [ ] `spring.config.import` is present from the Config Data phase.
- [ ] Clear rules exist for `optional:` and required keys.
- [ ] The JVM's UID/GID can read the files without excessive permissions.
- [ ] Secret values do not receive unwanted newlines/encoding.
- [ ] No higher-precedence config source holds old credentials.
- [ ] `@ConfigurationProperties`/auto-configuration use the right keys.
- [ ] Validation handles missing/empty secrets.
- [ ] Passwords/tokens/objects containing credentials are not logged.
- [ ] Actuator `env` and `configprops` are properly protected and masked.
- [ ] Secret rotate/revoke scenarios have been tested.
- [ ] K8s `subPath` is not misused for volume-update scenarios.
- [ ] Smoke tests with dummy secrets confirm startup/connectivity.

## 25. Official references

- **Spring Boot 3.3 Reference — Externalized Configuration / Using Configuration Trees / Docker secrets**, `spring.config.import=configtree:...` syntax, multiple files creating key/value pairs, `/*/` wildcard, String/byte[]: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 Reference — Importing Additional Data**, `optional:` semantics, import precedence, and extensionless files: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Kubernetes Documentation — Distribute Credentials Securely Using Secrets**, creating Secrets and supplying them to Pods: https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/
- **Kubernetes Documentation — Secrets**, Secret volumes, projected updates, `subPath` limitations, and security considerations: https://kubernetes.io/docs/concepts/configuration/secret/
- **Docker Docs — Manage sensitive data with Docker secrets**, Docker Swarm secret mounts and lifecycle: https://docs.docker.com/engine/swarm/secrets/
- **Docker Compose Docs — Secrets**, file-backed secrets and mounting into services: https://docs.docker.com/compose/how-tos/use-secrets/

## 26. Lesson takeaway

In Spring Boot 3.3, reading secrets with configtree can be remembered via the formula:

```text
Docker/Kubernetes Secret
    -> volume mount inside container
    -> relative filename/path forms property key
    -> file content forms property value
    -> spring.config.import=configtree:/mount-root/
    -> Environment / @ConfigurationProperties / auto-configuration
```

Shortest example:

```text
File inside container: /run/secrets/spring.datasource.password
Import:                spring.config.import=configtree:/run/secrets/
Created property:      spring.datasource.password
```

**Configtree is a bridge between a filesystem secret volume and Spring Environment**, not a secret manager. Safe deployment requires the right mount paths, the right property names, least-privilege read permissions, validation on missing/empty values, avoiding secret logging, and a clear restart/rotation plan.

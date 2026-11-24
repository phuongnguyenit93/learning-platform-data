# Loading ConfigMap or Secret as Environment Variables or Volumes in Spring Boot on Kubernetes

## 1. The Deployment Problem: One JAR, Multiple Configuration Environments

A Spring Boot application is typically packaged into a single JAR or container image, then deployed to development, testing, and production environments. Application code should remain unchanged while configuration varies by environment:

- HTTP client retry counts and timeouts.
- Topic names, queue limits, or lists of downstream services.
- Feature enable/disable flags.
- Server addresses and connection details.
- Tokens, passwords, client secrets, or authentication keys.

When running on Kubernetes, two common platform objects are:

- **ConfigMap**: holds **non-sensitive** configuration as key-value pairs or file data.
- **Secret**: holds data requiring access control, such as credentials, tokens, keys, and certificates; not by itself a complete security solution.

Kubernetes can supply ConfigMap/Secret values to containers in two main ways:

1. **Environment variables** via `env.valueFrom` or `envFrom`.
2. **Files in a volume** via `volumes` and `volumeMounts`.

Spring Boot receives data from environment variables via `Environment`. With mounted files, Spring Boot can load data using `spring.config.import=file:...` for a complete config file, or `spring.config.import=configtree:...` when each file in a directory represents one property.

**Objective:** understand the full path from ConfigMap/Secret → Pod/container → Spring Boot `Environment` → `@ConfigurationProperties` or auto-configuration; know how to choose the right delivery approach, validate missing data, avoid exposing secrets, and handle configuration updates.

## 2. High-Level Map

~~~text
Kubernetes API
  |
  +-- ConfigMap: app-runtime
  |      APP_JOBS_BATCHSIZE=200
  |      APP_JOBS_TIMEOUT=15s
  |
  +-- Secret: app-credentials
         PARTNER_AUTH_CLIENTSECRET=<secret value>
  |
  v
Pod specification / Deployment
  |
  +------------------------+-----------------------------+
  |                                                      |
  v                                                      v
env / envFrom                                        volumes / volumeMounts
Environment variables                                Files inside container
  |                                                   |
  |                                                   +-- configtree:/etc/app/config/
  |                                                   +-- configtree:/etc/app/secrets/
  |                                                   +-- file:/etc/app/application.yaml
  |                                                      |
  +-------------------------+----------------------------+
                            |
                            v
                    Spring Environment
                      PropertySources
                            |
                            v
                @ConfigurationProperties
                 or auto-configuration
                            |
                            v
                    Service / Client
~~~

Both delivery methods achieve **externalized configuration**: the application does not need to embed per-environment values inside the image. However, they differ in key naming, read permissions, update behavior, and how Spring Boot loads values.

## 3. Distinguishing ConfigMap and Secret

| Aspect | ConfigMap | Secret |
| --- | --- | --- |
| Purpose | Non-sensitive configuration | Confidential data/credentials |
| Examples | `app.jobs.batch-size`, timeouts, feature flags | API tokens, passwords, private keys |
| Text data | `data` | `stringData` or `data` |
| Binary/byte data | `binaryData` | `data` encoded as base64 |
| Delivered via env | `configMapKeyRef`, `configMapRef` | `secretKeyRef`, `secretRef` |
| Delivered via volume | `volumes[].configMap` | `volumes[].secret` |
| Mounted files | Key becomes filename | Key becomes filename |
| Mounted file updates | Usually eventual update | Usually eventual update |
| Process environment when object changes | Does not update automatically | Does not update automatically |
| Protection requirements | Still needs RBAC and access control | Needs strict RBAC, proper encryption at rest, auditing, rotation |

**Do not put real credentials into a ConfigMap** just because it is easy to create. Nor should you put all ordinary configuration into Secrets: that adds operational complexity and does not replace data classification.

### Secret.data is base64, not security encryption

In a Secret manifest, the `data` field holds base64-encoded values, not secure ciphertext. Anyone permitted to read the Secret object can decode it. Therefore:

- Restrict Secret read permissions with Kubernetes RBAC.
- Consider encrypting Secret data in control-plane storage.
- Restrict permissions to create workloads that can mount Secrets.
- Do not commit Secret YAML containing production values, even in base64 form.
- Use a secret management system or dedicated per-environment provisioning workflow.

`stringData` can be convenient in test examples but must not be treated as a way to hide secrets.

## 4. What Keys Can a ConfigMap Have?

Example ConfigMap containing no sensitive data:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-runtime
data:
  APP_JOBS_BATCHSIZE: "200"
  APP_JOBS_TIMEOUT: "15s"
  APP_FEATURE_EXPORT_ENABLED: "false"
~~~

All values under `data` in this manifest are **Strings**. Quotes around `"200"` and `"false"` prevent YAML from parsing them as numbers or booleans incompatible with the Kubernetes schema.

Key names here follow Spring Boot's environment variable syntax so they can be used directly with `envFrom` in the next example. When using volumes + `configtree:`, you can choose **canonical** names like `app.jobs.batch-size` instead of uppercase names.

### Separating naming by delivery method

When using **environment**, prefer names like:

~~~text
APP_JOBS_BATCHSIZE
APP_JOBS_TIMEOUT
APP_FEATURE_EXPORT_ENABLED
~~~

When using a **configuration tree**, prefer filenames like:

~~~text
app.jobs.batch-size
app.jobs.timeout
app.feature.export.enabled
~~~

There is no requirement that every ConfigMap use the same key naming convention across both approaches. However, if migrating from env to volume, **verify and rename keys/files as needed** so Spring Boot recognizes the right properties.

## 5. Approach 1 — Delivering a ConfigMap with env.valueFrom.configMapKeyRef

`env.valueFrom.configMapKeyRef` lets you select **a single key** from a ConfigMap and place it into an environment variable with a name you choose.

Example ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-settings
data:
  batchSize: "250"
  requestTimeout: "20s"
~~~

Deployment fragment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          env:
            - name: APP_JOBS_BATCHSIZE
              valueFrom:
                configMapKeyRef:
                  name: order-settings
                  key: batchSize
            - name: APP_JOBS_TIMEOUT
              valueFrom:
                configMapKeyRef:
                  name: order-settings
                  key: requestTimeout
~~~

Result in the JVM's environment:

~~~text
APP_JOBS_BATCHSIZE=250
APP_JOBS_TIMEOUT=20s
~~~

Spring Boot can bind these as:

~~~text
app.jobs.batch-size = 250
app.jobs.timeout = 20s
~~~

Java example:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.jobs")
public record JobsProperties(
        int batchSize,
        Duration timeout) {
}
~~~

Once `JobsProperties` is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(JobsProperties.class)`, the Binder converts those values to `int` and `Duration`.

### Advantages of picking keys

- The container only receives the properties it actually needs.
- ConfigMap key names can differ from environment variable names.
- You can share a ConfigMap across multiple apps without importing every key.
- Looking at the Deployment makes it easy to see where each variable comes from.

### Points to note

`name` under `configMapKeyRef` is the **ConfigMap name**. `key` is the **key inside the ConfigMap**; `env.name` is the **variable name inside the container**.

Do not confuse them:

~~~text
ConfigMap name: order-settings
ConfigMap key:  batchSize
Environment:    APP_JOBS_BATCHSIZE
Spring property: app.jobs.batch-size
Java member:    batchSize
~~~

These are four naming layers with distinct meanings.

## 6. Approach 2 — Delivering an Entire ConfigMap with envFrom.configMapRef

If a ConfigMap already uses valid environment variable names for its keys, `envFrom` lets you import **many keys at once**.

ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-runtime-env
data:
  APP_JOBS_BATCHSIZE: "200"
  APP_JOBS_TIMEOUT: "15s"
  APP_FEATURE_EXPORT_ENABLED: "false"
~~~

Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          envFrom:
            - configMapRef:
                name: order-runtime-env
~~~

The container receives variables with the same names as the keys in the ConfigMap.

**`envFrom` does not automatically convert key `app.jobs.batch-size` into `APP_JOBS_BATCHSIZE`.** It supplies variables based on key names, while Spring Boot performs environment-name matching per its rules.

Therefore, when intending to use `envFrom`, design the ConfigMap with environment-style keys.

### When to use envFrom?

Appropriate when a ConfigMap is designed **specifically for one workload**, contains only needed variables, and uses standardized variable names.

Less suitable than selecting individual keys when:

- The ConfigMap contains many unrelated entries.
- Multiple teams share the ConfigMap.
- You want to limit which values enter the process.
- You need variable names different from ConfigMap keys.

### Keys invalid as environment variable names

Kubernetes enforces environment variable naming rules and can skip keys from `envFrom` that cannot be used as valid variable names; the Pod may still start while emitting a warning event.

Do not assume that because the ConfigMap exists, **every key made it into the environment**. During diagnostics, check variable names **without printing sensitive values**.

## 7. Environment Variable Names and Spring Boot Relaxed Binding

In `@ConfigurationProperties` binding, the canonical property name:

~~~text
app.jobs.batch-size
~~~

maps to an environment variable name by these rules:

1. `.` → `_`.
2. Remove hyphens `-`.
3. Convert to uppercase.

Result:

~~~text
APP_JOBS_BATCHSIZE
~~~

Example table:

| Canonical name | Corresponding environment variable |
| --- | --- |
| `app.jobs.batch-size` | `APP_JOBS_BATCHSIZE` |
| `app.jobs.timeout` | `APP_JOBS_TIMEOUT` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `partner.auth.client-secret` | `PARTNER_AUTH_CLIENTSECRET` |
| `app.feature.export.enabled` | `APP_FEATURE_EXPORT_ENABLED` |

Be careful when turning hyphens into underscores. For `batch-size`, the canonical environment variable form is `BATCHSIZE`, not `BATCH_SIZE` by default under the documented rules.

If a ConfigMap literally has key `app.jobs.batch-size`, using `configMapKeyRef` is a clean workaround:

~~~yaml
env:
  - name: APP_JOBS_BATCHSIZE
    valueFrom:
      configMapKeyRef:
        name: order-settings
        key: app.jobs.batch-size
~~~

Kubernetes looks up the exact key, while you explicitly set an environment variable name convenient for Spring Boot.

## 8. Secrets as Environment Variables with secretKeyRef

Suppose an application needs a token for a partner service:

~~~java
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

Suppose a Kubernetes Secret named `partner-credentials` was provisioned securely by the platform and contains key `client-secret`.

Deployment fragment:

~~~yaml
env:
  - name: PARTNER_AUTH_CLIENTID
    value: "DEMO_CLIENT_ID"
  - name: PARTNER_AUTH_CLIENTSECRET
    valueFrom:
      secretKeyRef:
        name: partner-credentials
        key: client-secret
~~~

The application receives:

~~~text
partner.auth.client-id
partner.auth.client-secret
~~~

via Spring Boot relaxed binding.

### Do not put real values in the Deployment

Avoid:

~~~yaml
env:
  - name: PARTNER_AUTH_CLIENTSECRET
    value: "REAL_PRODUCTION_TOKEN"
~~~

Even though Kubernetes accepts this configuration, the literal value can end up in Git, Pod specs, and deployment tooling. For secrets, use `valueFrom.secretKeyRef` or a volume.

### Using secretRef with envFrom

If the Secret already uses valid environment variable names:

~~~text
PARTNER_AUTH_CLIENTSECRET
PAYMENT_GATEWAY_PASSWORD
~~~

you can write:

~~~yaml
envFrom:
  - secretRef:
      name: partner-env
~~~

Every valid key is injected into the container. This is concise, though it widens the scope of values the container receives. For shared secrets or when only a few keys are needed, explicit `secretKeyRef` is usually preferable.

### Avoid putting Secret data in documentation

There is no need to include a base64 string of a dummy token that readers might mistakenly copy as a "production template." Manifests in READMEs focus on **referencing a provisioned Secret**, not real data. In real environments, Secrets should be created by a controlled secret management workflow.

## 9. env, envFrom, configMapKeyRef, secretKeyRef: Which to Choose?

| Purpose | Kubernetes syntax | Behavior |
| --- | --- | --- |
| One key from a ConfigMap | `env[].valueFrom.configMapKeyRef` | Selects key, sets env name explicitly. |
| All valid keys from a ConfigMap | `envFrom[].configMapRef` | Imports multiple env vars. |
| One key from a Secret | `env[].valueFrom.secretKeyRef` | Selects secret key, sets env name explicitly. |
| All valid keys from a Secret | `envFrom[].secretRef` | Imports multiple secret env vars. |
| Non-sensitive literal value | `env[].value` | Assigns directly to one variable. |

You can combine these forms in the same container, while avoiding duplicate variable names. In Kubernetes, `env` takes precedence over variables from `envFrom` on name collisions; across multiple `envFrom` entries, list order can determine which value applies on collisions. Do not rely on name collisions as an obscure override mechanism; pick one clear source for each property.

### Kubernetes optional: true does not mean Spring allows it to be absent

`configMapKeyRef`, `secretKeyRef`, `configMapRef`, and `secretRef` support an `optional` flag in the Kubernetes API. When a reference is required and the resource or key is missing, the container may fail to be created or start normally. If marked optional, the platform allows certain missing-source cases.

This **does not replace** Spring Boot configuration validation. An app might start with an optional reference and then lack a required credential; validate at the application layer as well.

## 10. Important Limitation: Environment Variables Do Not Auto-Update When Sources Change

Suppose a Pod is running with:

~~~text
APP_JOBS_BATCHSIZE=200
~~~

An operator edits the ConfigMap to:

~~~text
APP_JOBS_BATCHSIZE=400
~~~

Kubernetes **does not automatically change environment variables of a running process** just because the ConfigMap was updated. The same applies to Secrets supplied via `secretKeyRef`.

In this case:

- The ConfigMap/Secret object has changed.
- The existing Pod's environment can still retain the old value.
- Already-created Spring Boot `@ConfigurationProperties` beans can still hold the old configuration.
- A **new/recreated Pod** receives the new data when created.

A common approach with a Deployment:

~~~bash
kubectl rollout restart deployment/order-service -n demo
kubectl rollout status deployment/order-service -n demo
~~~

These are illustrative commands; replace workload/namespace names for real environments and follow an appropriate rollout plan. Do not arbitrarily restart production without accounting for availability, connection draining, and compatibility between old and new credentials.

### Why not just edit the Secret?

With environment variables, data is provided at container creation time. There is no standard mechanism for Kubernetes to mutate an environment variable inside an already-running JVM process.

Therefore, if zero-downtime secret auto-updates are required, a dedicated design is needed—it cannot be achieved with `envFrom` alone.

## 11. Approach 3 — Mounting a ConfigMap as a Volume

A ConfigMap can be exposed as **files inside the container**.

ConfigMap designed for a volume:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-config-files
data:
  app.jobs.batch-size: "200"
  app.jobs.timeout: "15s"
  app.feature.export.enabled: "false"
~~~

Deployment fragment:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          volumeMounts:
            - name: app-config
              mountPath: /etc/app/config
              readOnly: true
      volumes:
        - name: app-config
          configMap:
            name: order-config-files
~~~

Inside the container, keys become filenames:

~~~text
/etc/app/config/
├── app.jobs.batch-size
├── app.jobs.timeout
└── app.feature.export.enabled
~~~

The contents of each file are the corresponding value.

**Note:** the `spec.template.spec` snippet above only illustrates part of a complete Deployment; it is not a standalone manifest.

### Spring Boot does not read the files unless a loading path is configured

A successful mount only proves the files exist. For Spring Boot to load these files into `Environment` as key-value properties, declare:

~~~yaml
spring:
  config:
    import: "configtree:/etc/app/config/"
~~~

Spring Boot uses filenames as property names:

~~~text
app.jobs.batch-size = 200
app.jobs.timeout = 15s
app.feature.export.enabled = false
~~~

Then the `JobsProperties` record from earlier can bind the values just as with environment variables.

## 12. Configuration Tree: The Core Mechanism When Each File Is One Property

`spring.config.import=configtree:...` is a Spring Boot Config Data mechanism.

It targets structures like:

~~~text
directory/
├── property.one
├── property.two
└── property.three
~~~

Each file represents one value:

~~~text
filename / relative path → property name
file content             → property value
~~~

Example:

~~~text
/etc/app/config/
└── messaging/
    ├── host
    └── timeout
~~~

Import:

~~~properties
spring.config.import=configtree:/etc/app/config/
~~~

Can supply:

~~~text
messaging.host
messaging.timeout
~~~

If you import a deeper root:

~~~properties
spring.config.import=configtree:/etc/app/config/messaging/
~~~

then the corresponding keys are:

~~~text
host
timeout
~~~

**The import root changes the property names.** This is a frequent error when Kubernetes mounts the right files yet Spring Boot fails to bind: the app expects `messaging.host` while the configuration tree provides `host`, or vice versa.

### Filenames containing dots

Spring Boot supports filenames such as:

~~~text
/etc/app/config/app.jobs.batch-size
~~~

and maps them to:

~~~text
app.jobs.batch-size
~~~

Thus, naming files to match canonical property names directly is usually simple, easy to inspect, and avoids aliases.

## 13. Approach 4 — Mounting a Secret as a Volume

Secrets can also be delivered as files.

Suppose Kubernetes Secret `partner-credentials` has key `client-secret`. A volume mount can rename the file using `items`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          volumeMounts:
            - name: app-secrets
              mountPath: /etc/app/secrets
              readOnly: true
      volumes:
        - name: app-secrets
          secret:
            secretName: partner-credentials
            items:
              - key: client-secret
                path: partner.auth.client-secret
~~~

File inside the container:

~~~text
/etc/app/secrets/partner.auth.client-secret
~~~

With:

~~~yaml
spring:
  config:
    import: "configtree:/etc/app/secrets/"
~~~

Spring Boot receives property:

~~~text
partner.auth.client-secret
~~~

and the binder can bind it to `PartnerCredentials.clientSecret`.

### What does `items` do?

If `items` is omitted, Kubernetes normally mounts each selected Secret key as a file with the same name as the key. With `items`, you can pick specific keys and set file paths tailored for the application.

In the example:

~~~text
Secret object: partner-credentials
Secret key:    client-secret
Mounted file:  partner.auth.client-secret
Spring key:    partner.auth.client-secret
Java member:   clientSecret
~~~

Four names can differ. They are connected via `items.key`, `items.path`, and `configtree:`.

### File permissions

For secret volumes, you can set `defaultMode` or per-item mode:

~~~yaml
volumes:
  - name: app-secrets
    secret:
      secretName: partner-credentials
      defaultMode: 0440
      items:
        - key: client-secret
          path: partner.auth.client-secret
~~~

File permissions must be compatible with the user/group running the JVM. Mode `0440` permits owner/group reads in POSIX environments, though a non-root container may still fail to read if owner/group do not match.

Never set `0777` just to bypass permission errors. Configure `runAsUser`, `runAsGroup`, `fsGroup`, or permission policies matching the real runtime, following least privilege.

## 14. A Complete Deployment: ConfigMap Volume + Secret Volume + Spring Boot

In the following example, the ConfigMap/Secret have already been created by the appropriate deployment mechanism.

ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-runtime-files
data:
  app.jobs.batch-size: "250"
  app.jobs.timeout: "20s"
  app.feature.export.enabled: "false"
~~~

Existing Secret named:

~~~text
partner-credentials
  key: client-secret
~~~

Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          ports:
            - containerPort: 8080
          env:
            - name: PARTNER_AUTH_CLIENTID
              value: "DEMO_CLIENT_ID"
          volumeMounts:
            - name: runtime-config
              mountPath: /etc/app/config
              readOnly: true
            - name: credentials
              mountPath: /etc/app/secrets
              readOnly: true
      volumes:
        - name: runtime-config
          configMap:
            name: order-runtime-files
        - name: credentials
          secret:
            secretName: partner-credentials
            items:
              - key: client-secret
                path: partner.auth.client-secret
~~~

Inside the JAR, `application.yaml`:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import:
      - "configtree:/etc/app/config/"
      - "configtree:/etc/app/secrets/"
~~~

Spring Boot loads both trees. Each key maps into `Environment` like a normal property.

Java:

~~~java
package com.example.demo.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.jobs")
public record JobsProperties(
        @Min(1) int batchSize,
        @NotNull Duration timeout) {
}

@Validated
@ConfigurationProperties(prefix = "partner.auth")
public record PartnerCredentials(
        @NotBlank String clientId,
        @NotBlank String clientSecret) {
}
~~~

Registration:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

When needed, a service injects the beans:

~~~java
@Service
public class OrderService {

    private final JobsProperties jobs;
    private final PartnerCredentials credentials;

    public OrderService(
            JobsProperties jobs,
            PartnerCredentials credentials) {
        this.jobs = jobs;
        this.credentials = credentials;
    }

    public int configuredBatchSize() {
        return jobs.batchSize();
    }

    // Do not print or return clientSecret in responses or logs.
}
~~~

**Key highlight:** `JobsProperties` from the ConfigMap mount and `PartnerCredentials` from the Secret mount are handled by the exact same `@ConfigurationProperties` mechanism. Java code does not need to know which Kubernetes object holds the data.

### Required vs. optional imports

The example above uses required paths. If a directory does not exist, Spring Boot normally reports a Config Data error and fails to complete startup.

In a local environment without mounts, you can use:

~~~yaml
spring:
  config:
    import: "optional:configtree:/etc/app/config/"
~~~

However, `optional:` only allows the **Config Data location** to be missing; it does not mean a required credential is allowed to be absent. For secrets used in production, keep `@NotBlank` checks and an explicit startup policy.

## 15. A Complete YAML File Inside a ConfigMap: Import File Instead of configtree

Not every volume uses "one file per key." You can store an entire YAML file as **one entry** of a ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-application-yaml
data:
  application.yaml: |
    app:
      jobs:
        batch-size: 200
        timeout: 15s
~~~

Mount:

~~~yaml
volumeMounts:
  - name: external-yaml
    mountPath: /etc/app/external
    readOnly: true
volumes:
  - name: external-yaml
    configMap:
      name: order-application-yaml
~~~

Inside the container:

~~~text
/etc/app/external/application.yaml
~~~

This is **one YAML file containing multiple properties**, so import it with:

~~~properties
spring.config.import=optional:file:/etc/app/external/application.yaml
~~~

Do not use:

~~~properties
spring.config.import=configtree:/etc/app/external/
~~~

if the goal is to parse the **YAML content** into `app.jobs.batch-size` and `app.jobs.timeout`. With `configtree:`, the filename `application.yaml` itself becomes the key, and the YAML content is not parsed as nested keys.

### If the file has no extension

Some platforms mount a file named:

~~~text
/etc/app/external/application
~~~

that still contains YAML. You can use an extension hint:

~~~properties
spring.config.import=optional:file:/etc/app/external/application[.yaml]
~~~

This tells Spring Boot the format of an extensionless file.

### When `spring.config.import` is not needed

Spring Boot also has default search locations for `application.properties`/`application.yaml` as well as `spring.config.location` and `spring.config.additional-location`. If the volume is mounted directly at a location Spring Boot already searches at startup, a separate import may not be necessary. However, with Kubernetes paths like `/etc/app/external/`, an explicit import is usually clearer and less dependent on the working directory.

## 16. configtree vs. file: and Choosing the Loading Mechanism

| Mount form | Layout | How Spring Boot loads it |
| --- | --- | --- |
| One key per file | `/etc/config/app.jobs.batch-size` | `configtree:/etc/config/` |
| Nested subdirectories representing hierarchical keys | `/etc/config/app/jobs/timeout` | `configtree:/etc/config/` |
| Complete `application.yaml` file | `/etc/config/application.yaml` | `file:/etc/config/application.yaml` |
| Complete `application.properties` file | `/etc/config/application.properties` | `file:/etc/config/application.properties` |
| Extensionless YAML file | `/etc/config/application` | `file:/etc/config/application[.yaml]` |
| ConfigMap via `envFrom` | `APP_JOBS_TIMEOUT=15s` | No import needed; system environment source |
| Secret via `secretKeyRef` | `PARTNER_AUTH_CLIENTSECRET=...` | No import needed; system environment source |

Choose based on **how the data is laid out inside the container**, not solely on whether the source is a ConfigMap or a Secret.

## 17. Projected Volumes: Combining ConfigMap and Secret in One Mount

Kubernetes supports **projected volumes** allowing multiple sources to be projected into the same directory. This can combine data from ConfigMaps, Secrets, and other supported sources.

Example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          volumeMounts:
            - name: app-settings
              mountPath: /etc/app/settings
              readOnly: true
      volumes:
        - name: app-settings
          projected:
            sources:
              - configMap:
                  name: order-runtime-files
                  items:
                    - key: app.jobs.batch-size
                      path: config/app.jobs.batch-size
                    - key: app.jobs.timeout
                      path: config/app.jobs.timeout
              - secret:
                  name: partner-credentials
                  items:
                    - key: client-secret
                      path: secret/partner.auth.client-secret
~~~

Inside the mount:

~~~text
/etc/app/settings/
├── config/
│   ├── app.jobs.batch-size
│   └── app.jobs.timeout
└── secret/
    └── partner.auth.client-secret
~~~

Spring Boot can import:

~~~yaml
spring:
  config:
    import:
      - "configtree:/etc/app/settings/config/"
      - "configtree:/etc/app/settings/secret/"
~~~

Using two separate subtrees avoids a too-broad import root turning keys into `config.app.jobs.batch-size` or `secret.partner.auth.client-secret`, which would no longer match the prefixes to bind.

### Risks to manage

- Avoid having two sources write to the same relative path in a projected volume.
- Permissions and file sensitivity must still be reviewed.
- Mount update mechanics do not mean Spring Boot automatically rebinds when files change.
- If dynamic rotation is required, design explicitly when beans and clients reload.

Projected volumes are useful when reducing mount count or structuring configuration files, not a mandatory requirement of Spring Boot.

## 18. Mounting via subPath: Why Does It Cause Confusion?

Kubernetes allows mounting a single file from a volume using `subPath`:

~~~yaml
volumeMounts:
  - name: config
    mountPath: /etc/app/application.yaml
    subPath: application.yaml
~~~

This lets the application see just one file without masking existing files in the directory. However, **a ConfigMap or Secret mounted via `subPath` does not receive automatic updates from the source object** under standard projected volume sync mechanics.

Distinguish:

| Mount type | Can Kubernetes update the file after the object changes? |
| --- | --- |
| Mounting a ConfigMap/Secret as a normal directory | Usually yes, after a sync delay. |
| Mounting an individual file via `subPath` | Does not receive automatic updates through that mechanism. |

If you expect to receive new configuration after a rollout, a new Pod will normally mount the updated values at creation time. But if you expect a running container to see live updates, `subPath` is the wrong choice.

**Spring Boot note:** even with a normal directory mount and an updated file, the binder does not automatically refresh an already-created bean. There are two update layers: Kubernetes updating the file and the application reloading the value.

## 19. ConfigMap Updates via Volumes: Eventual Consistency

Kubernetes updates mounted ConfigMap files using *eventual consistency*, not instantaneous synchronization.

A typical sequence:

~~~text
ConfigMap updated on Kubernetes API
                 |
                 v
kubelet detects change
      (watch / cache / sync)
                 |
                 v
files in Pod volume update
                 |
                 v
app can read new file contents
                 |
                 v
Do Spring Boot beans update automatically?
                 |
                 +-- No, unless a reload mechanism exists
                     or it is restarted/recreated
~~~

The delay from when the ConfigMap changes to when the mounted file updates depends on kubelet's change detection, caching, and sync period.

Therefore:

- Never treat `kubectl apply` completing as proof that every Pod has read the new value.
- Never expect every Pod to update files in the exact same millisecond.
- Avoid reading stale values if the application caches file contents.
- Never claim secret rotation is complete merely because the source object changed.

When consistency is critical, a rolling restart with a versioned configuration is usually more predictable than relying on undesigned dynamic reloading.

## 20. Secret Volume Updates and the Rotation Process

With a standard Secret volume mount, Kubernetes can also update files via eventual consistency. However, when credentials change, multiple states must be verified:

1. The Secret object contains the new version.
2. Kubelet has updated the mount inside the Pod.
3. The application has read or reloaded the new secret.
4. Connection pools, HTTP clients, TLS contexts, or token caches have been recreated if needed.
5. Downstream services accept the new credential.
6. The old credential can be revoked without disrupting the workload.

Jumping straight from step 1 to step 6 is dangerous.

### Rotation with environment variables

If a Secret is delivered via `secretKeyRef` → env:

- Running containers retain the environment supplied at creation time.
- Pods must be restarted/recreated to pick up new data by default.
- Account for replica counts and overlapping compatibility between old and new credentials during rollout.

### Rotation with volumes

If a Secret is delivered via a file volume:

- Files may be updated by Kubernetes.
- Reading the file directly at use time can see new data if the app is designed for it.
- Spring Boot `configtree:` is processed at startup and **does not automatically refresh `@ConfigurationProperties` or auto-configured clients**.
- If the application requires live updates, it must have a reload/refresh mechanism, concurrency tests, and clear error handling.

### DataSource risk example

When a password in a Secret mount changes, an already-initialized connection pool may still use the old credential. Modifying the file does not force the pool to use the new password on subsequent connections.

A realistic rotation plan usually coordinates changes in the database/secret manager, application rollout, and revoking the old credential only after verification.

## 21. Spring Boot PropertySource Precedence: Which Source Wins?

For a property such as:

~~~text
app.jobs.timeout
~~~

you might accidentally declare it in:

- `application.yaml` packaged inside the image.
- A ConfigMap mounted as YAML or configtree.
- Environment variable `APP_JOBS_TIMEOUT`.
- A Java system property.
- Command-line argument `--app.jobs.timeout=...`.

Spring Boot has a configuration source precedence order. By default, **environment variables** normally have higher precedence than **Config Data**, including imported files; CLI options can normally override environment variables.

Example:

~~~text
application.yaml           app.jobs.timeout = 5s
mounted configtree         app.jobs.timeout = 20s
environment                APP_JOBS_TIMEOUT = 30s
CLI                        --app.jobs.timeout=45s
~~~

Under default loading, the effective value is normally `45s` from CLI.

### Risk when migrating from env to volume

If a Deployment previously used:

~~~yaml
env:
  - name: APP_JOBS_TIMEOUT
    value: "30s"
~~~

and you migrated the ConfigMap to a volume containing:

~~~text
/etc/app/config/app.jobs.timeout → 20s
~~~

yet forgot to delete the old environment variable, Spring Boot may still receive **30s**.

**Mounting properly does not mean the mount wins the property source order.** When switching delivery methods, inventory and remove unwanted duplicate sources.

### Do not pass real secrets in arguments

Even though CLI can have high precedence, never pass production credentials via:

~~~bash
java -jar app.jar --partner.auth.client-secret=REAL_SECRET
~~~

Arguments can appear in process metadata, command history, logs, or monitoring systems. Secrets should be delivered via platform-managed channels.

## 22. Diagnosing Missing Data with ConfigMaps or Secrets

### Symptom A — environment variable is missing

Possible causes:

- ConfigMap/Secret does not exist in the Pod's namespace.
- Typo in `configMapKeyRef` / `secretKeyRef` key name.
- `envFrom` encountered a key unusable as a variable name.
- The Deployment has not created new Pods after updating the source.
- Inspecting the wrong container or namespace.

How to investigate: inspect Pod/Deployment config, events, and provisioned **variable names**; avoid printing the entire environment if secrets are present.

### Symptom B — volume mount has no files

Possible causes:

- Wrong ConfigMap/Secret name.
- Mismatched `volumeMounts.name` vs. `volumes.name`.
- Mount path differs from what the application expects.
- `items.key` does not exist or `items.path` differs from the expected filename.
- File or directory permissions prevent the JVM from reading.

How to investigate: check filenames, permissions, ownership, and mount path. Never run `cat` to print real credentials into logs or tickets.

### Symptom C — files exist, yet Spring Boot fails to bind

Possible causes:

- `spring.config.import` is missing.
- Used `configtree:` on a complete YAML file instead of `file:`.
- `configtree:` root is too shallow or too deep, shifting property names.
- Filenames in the volume do not match canonical `@ConfigurationProperties` names.
- An environment variable or another source overrides it.
- The file was read, yet the value has the wrong type.

### Symptom D — ConfigMap updated, yet app keeps using old values

Possible causes:

- The app uses env, not a volume.
- Mounted via `subPath`.
- Kubelet has not synced the update yet.
- Spring Boot bound configuration at startup and holds old objects.
- Clients or connection pools cache the value.

The solution depends on architecture: rolling restart or a tested, implemented reload mechanism.

## 23. Checking Status Without Exposing Secrets

You can check whether a value is present via an API without printing its content:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CredentialsAvailability {

    private final Environment environment;

    public CredentialsAvailability(Environment environment) {
        this.environment = environment;
    }

    public boolean partnerCredentialConfigured() {
        String secret =
                environment.getProperty("partner.auth.client-secret");

        return secret != null && !secret.isBlank();
    }
}
~~~

Output only a summary like:

~~~text
partner.auth.client-secret: configured
~~~

Never print:

~~~java
System.out.println(
        environment.getProperty("partner.auth.client-secret"));
~~~

And never log a record containing a secret:

~~~java
log.info("auth config = {}", partnerCredentials);
~~~

Java records have an auto-generated `toString()` that prints all members, including `clientSecret`. When logging config status, log only safe metadata and mask values.

### Actuator env/configprops

`/actuator/env` and `/actuator/configprops` can assist diagnostics if Spring Boot Actuator is installed, enabled, and appropriately access-controlled. Never assume every value is perfectly redacted across all versions or settings.

In production, never expose these endpoints publicly just to view configuration values.

## 24. Security When Using Secret Volumes

Secret volumes avoid exposing long values in process environment variables, yet still require protection:

- Mount only on Pods that need the secret.
- Attach `volumeMounts` only to containers that need read access.
- Mount read-only; Secret volumes are typically mounted read-only in practice.
- Configure user/group and file modes just broad enough to read, not overly permissive.
- Restrict `exec` and debug-container access in production.
- Restrict Secret object read permissions with Kubernetes RBAC.
- Consider encryption at rest and access auditing in the control plane.
- Never print contents in logs, crash dumps, traces, or scripts.
- Avoid sharing a single token across all apps/environments when scoped tokens are possible.

A Secret does not become completely safe simply by moving from `env` to a file. Anyone able to read the file or execute code in the container can still extract it.

### Do not overlook ConfigMaps

ConfigMaps are not secret stores, yet they can still hold internal details such as endpoints, hostnames, feature flags, and cluster names. Still restrict read/edit permissions appropriately and protect configuration integrity.

## 25. Validating Required Configuration with @Validated

Suppose a module must have a partner client secret before starting.

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "partner.auth")
public record PartnerAuthProperties(
        @NotBlank String clientId,
        @NotBlank String clientSecret) {
}
~~~

When a Bean Validation provider is present, usually via `spring-boot-starter-validation`, Spring Boot checks constraints during binding.

Whether you use `env` or `configtree:`, if `partner.auth.client-secret` is missing or blank, startup can be blocked when validation is properly configured.

### Config Data `optional:` vs. Kubernetes `optional`

- `optional:configtree:/path/`: lets Spring Boot avoid immediate failure when **the import location does not exist**.
- `secretKeyRef.optional: true`: lets Kubernetes treat a Secret/key reference as optional at the API level.
- `@NotBlank` / custom validation: determines whether **business rules** allow the credential to be missing.

These three layers do not substitute for one another. For required production secrets, establish explicit policies in both Kubernetes and Spring Boot.

## 26. Two Deployment Strategies: Immutable Config vs. Dynamic Updates

### 26.1. Prefer immutable configuration tied to Pod lifecycle

Easy-to-operate model:

1. ConfigMap/Secret is created or updated by the deployment/secret management system.
2. Deployment template changes to create new Pods, or triggers a rollout.
3. New Pods receive the matching env/volume version.
4. Spring Boot reads Config Data at startup and creates beans/clients.
5. Health/readiness passes, and traffic shifts to new Pods.
6. Old Pods are drained and terminated safely.

Advantages:

- Easy to trace which configuration values each Pod started with.
- No need for the program to re-read files itself.
- Easy to verify startup validation and readiness.
- Fits systems with immutable beans or pools holding credentials.

### 26.2. Dynamic updates via volumes

This model is only appropriate when:

- The container mounts the volume without `subPath`.
- Kubernetes can update the files normally.
- The application is designed to re-read files or refresh/rebind beans.
- Every client/connection pool is updated safely.
- Consistency, reload failures, and rollback behavior are tested.

Do not confuse "kubelet updated the file" with "every `@ConfigurationProperties` class updated automatically." Those are two events at two independent layers.

### 26.3. Changes that may require a restart even when new files appear

For instance, changing `server.port`, DataSource credentials, TLS configs, or framework bootstrap settings usually cannot take full effect merely by updating an `Environment` field. Previously constructed components may require reinitialization or restart.

For changes of this kind, a rolling restart is usually the more predictable strategy.

## 27. Hands-On Scenario: Dev Uses Env, Production Uses Volume

Suppose the same image:

~~~text
example/order-service:1.0.0
~~~

### Development

ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-dev-env
data:
  APP_JOBS_BATCHSIZE: "25"
  APP_JOBS_TIMEOUT: "3s"
~~~

Dev Deployment:

~~~yaml
envFrom:
  - configMapRef:
      name: order-dev-env
~~~

Spring Boot picks up these variables from the environment automatically. No `spring.config.import=configtree:` is needed for env alone.

### Production

Volume ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-prod-config
data:
  app.jobs.batch-size: "500"
  app.jobs.timeout: "20s"
~~~

Prod Deployment:

~~~yaml
env:
  - name: SPRING_CONFIG_IMPORT
    value: "configtree:/etc/app/config/"
volumeMounts:
  - name: runtime-config
    mountPath: /etc/app/config
    readOnly: true
~~~

Volume:

~~~yaml
volumes:
  - name: runtime-config
    configMap:
      name: order-prod-config
~~~

Spring Boot reads the directory via `SPRING_CONFIG_IMPORT`, and the Java fields remain identical to development.

**Note:** these snippets are fragments. In a full manifest, place `env` and `volumeMounts` under the right container, and `volumes` under the Pod spec. Do not place `volumes` inside a container.

### Benefits

- Same artifact and `JobsProperties` class.
- No production configuration baked into code.
- Delivery method can vary per environment.
- Keeps the logical property namespace stable.

Changing delivery channels requires checking key names and source ordering, without modifying business services.

## 28. Common Pitfalls with ConfigMaps and Secrets

### Mistake 1 — Using envFrom with canonical property-style keys

ConfigMap contains:

~~~yaml
data:
  app.jobs.batch-size: "100"
~~~

yet Deployment uses:

~~~yaml
envFrom:
  - configMapRef:
      name: app-config
~~~

Do not expect Kubernetes to rename the key to `APP_JOBS_BATCHSIZE`. Use `configMapKeyRef` to set an explicit variable name, or change keys in the ConfigMap to valid environment variable format.

### Mistake 2 — Forgetting quotes for numbers and Booleans in ConfigMap data

~~~yaml
data:
  APP_JOBS_BATCHSIZE: 100
~~~

In YAML, `100` may be parsed as numeric, whereas `ConfigMap.data` requires String values. Use:

~~~yaml
data:
  APP_JOBS_BATCHSIZE: "100"
~~~

### Mistake 3 — Secret exists, yet Pod never references it

A Kubernetes Secret existing in the namespace does not mean every Pod receives it automatically. You need `secretKeyRef`, `secretRef`, or a volume mount.

### Mistake 4 — Wrong namespace

Pods typically reference ConfigMaps/Secrets in the same namespace. Do not assume a same-named Secret in another namespace will be picked up automatically.

### Mistake 5 — Mounting a volume without configuring Spring to read it

Kubernetes may mount the files properly; Spring Boot still needs `configtree:`, `file:`, an appropriate `spring.config.location`, or custom file-reading logic. Having the file alone does not produce properties.

### Mistake 6 — Using configtree on a single YAML file

If only `application.yaml` is in the mount, `configtree:` treats the filename as one key instead of parsing YAML into multiple properties. Import with `file:` or use an appropriate config search location.

### Mistake 7 — Wrong root when importing a directory

File:

~~~text
/etc/config/app/jobs/timeout
~~~

Importing `configtree:/etc/config/` provides `app.jobs.timeout`. Importing `configtree:/etc/config/app/` provides `jobs.timeout`. Shifting the import root changes property names during binding.

### Mistake 8 — Editing a ConfigMap and expecting running Pod env to change

Environment variables do not update automatically when a ConfigMap changes. Pods must be rolled/recreated.

### Mistake 9 — Using subPath and waiting for automatic file updates

ConfigMaps/Secrets mounted via `subPath` do not receive automatic updates. Avoid `subPath` if live updates are required.

### Mistake 10 — File changes, yet Java beans keep old values

Spring Boot normally loads Config Data at startup. Already-created beans do not auto-rebind merely because kubelet updated a file.

### Mistake 11 — Writing Secrets into a ConfigMap or literal manifests

Doing so increases the risk of leaking credentials through Git, APIs, pipelines, and logs. Use managed Secrets with proper access controls, never storing real data directly in examples.

### Mistake 12 — Thinking base64 Secret data is encryption

Base64 does not stop anyone with Secret read permission from decoding values. Security also depends on RBAC and encryption at rest.

### Mistake 13 — File mode 0400 while app runs as a different user

The container may be unable to read it. Fix ownership/group/mode according to least privilege, without opening permissions globally.

### Mistake 14 — Two sources supplying the same property

Env `APP_JOBS_TIMEOUT` can override ConfigMap file `app.jobs.timeout`; pick one authoritative source and remove stale ones.

### Mistake 15 — Logging the entire Environment

`System.getenv()` or `Environment`/record `toString()` calls can leak secrets. Log only presence status and safe key names.

### Mistake 16 — Mounting secret volumes to unnecessary containers

In multi-container Pods, mount only the secrets each container truly needs. Avoid exposing secrets to sidecars or debug containers that do not require them.

### Mistake 17 — Assuming configMapKeyRef creates a file

`configMapKeyRef` supplies **an environment variable**, not a file. When a file is needed, use `volumes[].configMap` and `volumeMounts`.

### Mistake 18 — Ignoring the effective value

YAML may look right while CLI, env, or a higher-precedence source supplies another value. Inspect `PropertySource`s and bound bean state.

## 29. Testing and Verifying Without Real Credentials

### 29.1. Testing binding with dummy env/properties

In a Spring Boot test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "app.jobs.batch-size=42",
        "app.jobs.timeout=6s"
})
class JobsPropertiesTest {

    @Autowired
    JobsProperties jobs;

    @Test
    void bindsValues() {
        assertEquals(42, jobs.batchSize());
        assertEquals(Duration.ofSeconds(6), jobs.timeout());
    }
}
~~~

This test requires `JobsProperties` to be registered in the context, e.g., via `@ConfigurationPropertiesScan`. It checks bound values but does not prove the Kubernetes mount works in production.

### 29.2. Testing volumes with dummy data

An integration test can:

1. Create a temporary directory.
2. Write file `app.jobs.batch-size` with content `42`.
3. Write file `app.jobs.timeout` with content `6s`.
4. Start a context with `spring.config.import=configtree:<test-dir>/` supplied **before the Config Data phase**.
5. Inject `JobsProperties` and assert both values.
6. Clean up the temporary directory after the test.

Production secrets are not needed to test the mechanism. When creating test files, use dummy markers with no real access value.

### 29.3. Testing missing Secrets

Create a test environment without the mounted `partner.auth.client-secret` file while the class has `@NotBlank`.

Expect the application to fail creating the properties bean when validation is properly configured. This tests the **required-property policy** without needing a real token.

### 29.4. Testing update differences between env and volume

In a dev Kubernetes environment:

- Create one Pod consuming a ConfigMap via env, and another via a volume.
- Update the test ConfigMap.
- Observe: old env does not change on its own; volume files may update after a delay.
- If Spring Boot reads the file via `configtree:`, check the bean without restarting to confirm it does not auto-refresh.
- Recreate the Pod and verify startup with the new data.

This is a critical test to avoid confusing Kubernetes sync with application reload.

## 30. Hands-On Exercises with Answers

### Exercise 1 — Choose a mechanism for one key

ConfigMap `app-runtime` has key `batchSize` = `"200"`. You want to supply `APP_JOBS_BATCHSIZE`.

**Answer:**

~~~yaml
env:
  - name: APP_JOBS_BATCHSIZE
    valueFrom:
      configMapKeyRef:
        name: app-runtime
        key: batchSize
~~~

### Exercise 2 — Import an entire ConfigMap

ConfigMap `runtime-env` has keys `APP_JOBS_TIMEOUT` and `APP_JOBS_BATCHSIZE`.

**Answer:**

~~~yaml
envFrom:
  - configMapRef:
      name: runtime-env
~~~

### Exercise 3 — Pick a single secret key

Secret `partner-credentials` has key `client-secret`.

**Answer:**

~~~yaml
env:
  - name: PARTNER_AUTH_CLIENTSECRET
    valueFrom:
      secretKeyRef:
        name: partner-credentials
        key: client-secret
~~~

### Exercise 4 — Mount a ConfigMap as multiple files

ConfigMap `runtime-files` has keys `app.jobs.batch-size` and `app.jobs.timeout`.

**Answer:** set `volumes[].configMap.name=runtime-files`, mount at `/etc/app/config`, and use `spring.config.import=configtree:/etc/app/config/`.

### Exercise 5 — Read a YAML file from a ConfigMap

A ConfigMap has entry `application.yaml` containing multiple keys.

**Answer:** mount that file and import `file:/etc/app/config/application.yaml` or use an appropriate search location; do not use `configtree:` to parse YAML content.

### Exercise 6 — Distinguish key path from property name

Mounted file:

~~~text
/etc/app/secrets/partner.auth.client-secret
~~~

Import `configtree:/etc/app/secrets/`.

**Answer:** property is `partner.auth.client-secret`.

### Exercise 7 — Shifting the root

File:

~~~text
/etc/app/secrets/partner/auth/client-secret
~~~

Import `configtree:/etc/app/secrets/partner/`.

**Answer:** property is `auth.client-secret`, without the `partner` segment because the import root starts deeper.

### Exercise 8 — ConfigMap updated, env unchanged

A Pod has `APP_JOBS_TIMEOUT=10s` via `envFrom`. The ConfigMap is updated to `20s`.

**Answer:** the running Pod does not automatically receive the new environment; recreate/restart the Pod so it picks it up at startup.

### Exercise 9 — Volume changed, yet bean retains old value

Mounted file `app.jobs.timeout` changes from `10s` to `20s`.

**Answer:** Kubernetes can update the file, yet the already-bound `JobsProperties` bean in Spring Boot does not change automatically without a dedicated refresh/restart mechanism.

### Exercise 10 — Secret via subPath

A Secret is mounted as a single file using `subPath`; the Secret object changes.

**Answer:** files mounted this way do not receive automatic updates like normal directory volume mounts.

### Exercise 11 — Keys from multiple sources

ConfigMap file has `app.jobs.timeout=10s`; environment has `APP_JOBS_TIMEOUT=30s`.

**Answer:** under normal Spring Boot source precedence, environment beats Config Data. Remove the redundant source or manage precedence explicitly.

### Exercise 12 — Verify without leaking secrets

You want to know whether `partner.auth.client-secret` was bound.

**Answer:** use `@NotBlank`, startup validation, and a safe status message; never print the secret value or record `toString()`.

### Exercise 13 — ConfigMap key has dots

ConfigMap has key `app.jobs.timeout` yet uses `envFrom`.

**Answer:** do not assume Kubernetes renames it to `APP_JOBS_TIMEOUT`. Use `configMapKeyRef` to select the key and set `env.name` explicitly, or use a `configtree:` volume.

### Exercise 14 — Certificate updates needed

A library only accepts file paths to a certificate and private key.

**Answer:** mounting files with restricted permissions may fit better than stuffing everything into env vars. Check whether the library supports reloading files; if not, restart/recreate the client or Pod.

### Exercise 15 — Explain optional

`spring.config.import=optional:configtree:/etc/app/secrets/` when the secret is required for production.

**Answer:** `optional:` only permits the import location to be absent. Validation and deployment policy are still needed so the app does not run with missing credentials.

## 31. Pre-Production Checklist

### Data classification

- ConfigMaps contain only non-sensitive settings.
- Secrets hold credentials/tokens/keys with appropriate scope.
- No real secrets in Git, images, or literal manifests.
- Secret provisioning and rotation processes are centrally managed when needed.

### Choosing the delivery method

- `envFrom` when many variables are needed and key names are valid.
- `configMapKeyRef` / `secretKeyRef` when picking individual keys or renaming env vars.
- Volumes when files or a tree structure of multiple keys are needed.
- `file:` for a complete YAML/Properties file.
- `configtree:` for a directory with one file per value.

### Spring Boot

- Prefixes and environment variable names map correctly.
- `configtree` root matches the property names to bind.
- `@ConfigurationProperties` beans are registered.
- Required configuration has validation.
- Source precedence does not let old env vars override new volumes.
- No full-secret logging.

### Kubernetes

- Pod and resources are in the matching namespace.
- ConfigMaps/Secrets exist before workloads start.
- `volumes.name` and `volumeMounts.name` match.
- Containers mount the right path and have read permission.
- Do not use `subPath` if automatic file updates are needed.
- Rollout policy exists for when ConfigMaps/Secrets change.
- RBAC, image hardening, runtime isolation, and encryption at rest are addressed.

### Rotation and operations

- Understand env does not auto-update.
- Understand volumes may update after a delay.
- Understand Spring Boot does not auto-rebind all config when files change.
- Know whether clients/connection pools or Pods need recreation.
- Readiness, rollback, and old-credential revocation procedures exist.
- Never verify by printing secret values to logs or terminals.

## 32. Conclusion

Kubernetes offers two paths to deliver ConfigMaps/Secrets to Spring Boot:

**Via environment variables:** use `env.valueFrom.configMapKeyRef` / `secretKeyRef` to select individual keys, or `envFrom.configMapRef` / `secretRef` to supply multiple keys. Spring Boot reads from OS environment under its property naming rules. This is concise and direct, yet **process environment variables do not automatically change when a ConfigMap/Secret is updated**.

**Via volumes:** Kubernetes mounts data as files. Spring Boot can use `configtree:` for a directory of key-value files or `file:` for a complete YAML/Properties file. Mounted files are usually updated by Kubernetes via eventual consistency, except in cases like `subPath`; however, **Spring Boot does not automatically refresh already-initialized beans/clients when files change**.

Whichever approach you choose, distinguish three layers:

1. **Kubernetes delivers data:** selecting ConfigMap/Secret, keys, env, or paths.
2. **Spring Boot loads and binds:** `Environment`/Config Data, prefixes, `PropertySource` precedence, `@ConfigurationProperties`.
3. **Application applies changes:** startup, validation, dependency injection, refresh, or rolling restart.

Understanding these three layers lets you deploy the same Spring Boot artifact across multiple environments without hard-coding config, reduce credential exposure risks, and plan controllable updates and rotations.

## References

- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/).
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).
- [Kubernetes — Volumes](https://kubernetes.io/docs/concepts/storage/volumes/).
- [Kubernetes — Projected Volumes](https://kubernetes.io/docs/concepts/storage/projected-volumes/).
- [Kubernetes — Configure a Pod to Use a ConfigMap](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/).
- [Kubernetes — Distribute Credentials Securely Using Secrets](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/).
- [Spring Boot — Externalized Configuration and Configuration Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html).

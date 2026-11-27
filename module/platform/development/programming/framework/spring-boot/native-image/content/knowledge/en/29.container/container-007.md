# Passing Arguments, Environment Variables, and Secrets at Container Startup

## 1. Runtime Configuration for a Native Container

A Spring Boot Native Image is packaged as a native executable. When the container starts, the process needs the active profile, port, dependent service URLs, timeouts, feature flags, and credentials to connect to databases or external APIs.

These values usually differ across local, staging, and production. Therefore, the image should contain only the executable and the components needed to run it; the deployment environment supplies configuration and secrets at startup time. If an environment-dependent value is read in a static initializer and frozen when the native image is built, the executable may carry values from the build machine. Put configuration into Spring Boot externalized configuration and read it during the application lifecycle.

This lesson belongs to the **Container** chapter of the **SPRING_BOOT_NATIVE_IMAGE** module. It focuses on command-line arguments, environment variables, property precedence, secret file mounts, Docker/Compose/Kubernetes, rotation, and the difference between application arguments and JVM or Native Image runtime options.

## 2. Spring Boot Command-Line Arguments

Spring Boot accepts application arguments as options:

```bash
./orders-api --server.port=8080 --spring.profiles.active=production
```

Arguments of the form `--name=value` are converted into properties by Spring Boot:

| Argument | Property |
| --- | --- |
| `--server.port=8080` | `server.port` |
| `--spring.profiles.active=production` | `spring.profiles.active` |
| `--spring.datasource.url=jdbc:postgresql://db:5432/orders` | `spring.datasource.url` |
| `--management.server.port=8081` | `management.server.port` |

Command-line arguments are useful when overriding a few values for a specific run. Never pass passwords or tokens directly on the command line because they can appear in process listings, shell history, CI logs, or deployment tool metadata.

With a native executable, arguments after the executable name are program arguments and can be processed by Spring Boot as shown above:

```bash
/app/orders-api --server.port=8080 --spring.profiles.active=production
```

You do not write `java -jar` before a native executable.

## 3. Environment Variables and Relaxed Binding

Environment variables are well suited for simple configuration managed by the deployment environment. Spring Boot supports relaxed binding, allowing standard properties to be expressed as uppercase environment variable names with underscores.

| Spring Property | Environment Variable |
| --- | --- |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `server.port` | `SERVER_PORT` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `management.server.port` | `MANAGEMENT_SERVER_PORT` |
| `logging.level.com.example.orders` | `LOGGING_LEVEL_COM_EXAMPLE_ORDERS` |

Example container run:

```bash
docker run --rm \
  -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=production \
  -e SERVER_PORT=8080 \
  -e SPRING_DATASOURCE_URL=jdbc:postgresql://db:5432/orders \
  -e SPRING_DATASOURCE_USERNAME=orders_app \
  orders-api:native
```

Use environment variables for profiles, ports, endpoint URLs, and timeouts. Passwords, private keys, and tokens need a dedicated secret management mechanism; environment variables are not a secret vault.

### 3.1. Structured Configuration

For collections or maps, environment variable names can become hard to read. When configuration grows complex, consider a mounted config file or `SPRING_APPLICATION_JSON` for a structured subset:

```bash
docker run --rm \
  -e 'SPRING_APPLICATION_JSON={"feature":{"invoice-export":true},"clients":{"billing":{"connect-timeout":"2s"}}}' \
  orders-api:native
```

This JSON is still runtime process configuration and should not contain secrets. `SPRING_APPLICATION_JSON` may be exposed through inspection or diagnostic output depending on the platform.

## 4. Spring Boot Configuration Precedence

Spring Boot aggregates properties from multiple sources. When the same key appears in multiple sources, the higher-precedence source overrides the lower-precedence one.

For a typical standalone application, you can remember the simplified order from highest to lowest:

1. Command-line arguments.
2. `SPRING_APPLICATION_JSON`.
3. Java system properties.
4. Operating-system environment variables.
5. Config data such as `application.yaml` and profile-specific files.
6. Default properties.

Spring Boot also has specialized sources such as servlet init parameters, JNDI, and test property sources. Exact ordering depends on the application type and Spring Boot version; when precision is needed, check the externalized configuration documentation for your project's version.

For example, suppose `application.yaml` has:

```yaml
server:
  port: 8080
spring:
  profiles:
    active: local
```

If the container starts with `SERVER_PORT=9090` and `SPRING_PROFILES_ACTIVE=production`, the environment values override the two file values. If `--server.port=7070` is passed on the command line, the command-line value takes precedence over the environment variable.

Do not rely on precedence to manage secrets across multiple copies in different sources. Every secret should have one clearly defined runtime source.

## 5. Distinguishing Build-Time and Runtime Configuration

Native Image has two critical phases:

- **Build time:** GraalVM analyzes and produces the executable. Some classes may be initialized during the build.
- **Runtime:** the container launches the executable; the process receives environment variables, arguments, mounted files, and connects to dependencies.

Values such as database passwords, service URLs, hostnames, ports, secret paths, and feature flags must generally be read at runtime.

Unsafe example:

```java
final class DatabaseSettings {

    static final String PASSWORD =
        System.getenv("DB_PASSWORD");
}
```

If this class is initialized at build time, the value can be read from the build environment and stored inside the image. That can corrupt production configuration and accidentally embed a secret in the artifact.

Instead, let Spring manage configuration:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class DatabaseConnectionSettings {

    private final String password;

    DatabaseConnectionSettings(Environment environment) {
        this.password = environment.getProperty(
            "spring.datasource.password"
        );
    }

    String password() {
        return password;
    }
}
```

Spring injects the property when the application context initializes inside the runtime container. For datasources, prefer letting Spring Boot datasource auto-configuration consume standard properties rather than reading the environment in a static field yourself.

### 5.1. Do Not Bake Secrets into the Image

Never pass secrets through Dockerfile `ARG` or `ENV` at build time:

```dockerfile
# Do not do this
ARG DB_PASSWORD
ENV DB_PASSWORD=secret-value
```

Build arguments or environment variables recorded during image creation can appear in layers, history, caches, or image configuration. Never `COPY` secret files into the image and never commit secret files to the repository.

An image should be built once and promoted across staging/production. Each environment supplies its own runtime configuration and secrets when the container starts.

## 6. Docker ENTRYPOINT and CMD for Native Executables

For a native executable, use exec form so the application process becomes PID 1 in the container. Minimal runtime Dockerfile example:

```dockerfile
FROM debian:bookworm-slim

WORKDIR /app

COPY --chown=10001:10001 target/orders-api /app/orders-api

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["/app/orders-api"]
CMD ["--server.port=8080"]
```

Docker combines `ENTRYPOINT` and `CMD`: default arguments in `CMD` are passed to the executable in `ENTRYPOINT`. When running:

```bash
docker run --rm -p 8080:8080 orders-api:native \
  --spring.profiles.active=production
```

Arguments after the image name replace the default `CMD` and are passed to the executable. `ENTRYPOINT` remains the native binary.

The runtime base image must also match the OS, architecture, and libc that the native executable was built for. For example, a binary linked against glibc will not automatically run on Alpine/musl simply by switching the base image. Testing the executable inside the exact runtime image catches missing shared libraries or ABI mismatches early.

### 6.1. Exec Form vs. Shell Form

Prefer:

```dockerfile
ENTRYPOINT ["/app/orders-api"]
```

Avoid shell form:

```dockerfile
ENTRYPOINT /app/orders-api
```

Shell form runs via an intermediate shell. The process may not receive signals directly as intended if the shell does not forward them. Exec form lets Docker deliver SIGTERM to the native process so Spring has a chance to perform graceful shutdown.

If a wrapper script is needed to prepare files or check mounts before starting, use an executable wrapper script that ends with `exec /app/orders-api "$@"` to replace the shell process with the application.

### 6.2. Distinguishing Application Arguments from Runtime Options

| Type | Example | Where Handled |
| --- | --- | --- |
| Spring application argument | `--server.port=8080` | Spring Boot Environment |
| Environment variable | `SPRING_PROFILES_ACTIVE=production` | OS environment, Spring relaxed binding |
| JVM launcher option | `-XX:...` or `-D...` on the java command | Java launcher when running on JVM |
| Native Image runtime option | Runtime options supported by the GraalVM executable | Native Image runtime |

A native executable is not launched by the Java launcher. Therefore, `JAVA_TOOL_OPTIONS` or `JDK_JAVA_OPTIONS` is not a general way to pass arbitrary JVM options to a native binary. If you need to cap memory or enable runtime monitoring, use options supported by your specific GraalVM Native Image version and check the toolchain's documentation/help. Spring properties can still be passed via environment variables or application arguments.

## 7. Mounting Configuration Files into the Container

When there are many properties or dedicated files must be managed, you can mount files into the container:

```bash
docker run --rm \
  -p 8080:8080 \
  -e SPRING_CONFIG_ADDITIONAL_LOCATION=file:/run/config/ \
  --mount type=bind,src=/opt/orders/config,dst=/run/config,readonly \
  orders-api:native
```

The mounted directory can contain `application.yaml` or profile-specific files. Ensure files are readable by the UID running the application. Mount read-only so the process cannot alter platform-managed configuration.

`SPRING_CONFIG_LOCATION` replaces default config locations. `SPRING_CONFIG_ADDITIONAL_LOCATION` adds locations alongside the defaults. Choose according to your goal and inspect config-loading logs at startup.

## 8. Loading Secrets from Files with Spring Config Tree

A clean container pattern is mounting each secret as a file and using a config tree import. Spring Boot reads each filename as the property key and the file content as the property value.

Example layout inside the container:

```text
/run/secrets/
  spring.datasource.username
  spring.datasource.password
  api.partner.token
```

Declare the import:

```properties
spring.config.import=optional:configtree:/run/secrets/
```

Or via environment variable:

```bash
SPRING_CONFIG_IMPORT=optional:configtree:/run/secrets/
```

The contents of `spring.datasource.password` become the value of the `spring.datasource.password` property. The file `api.partner.token` becomes the `api.partner.token` property. The application continues to use Spring Boot datasource auto-configuration and property injection as usual.

Use `optional:` when the secret mount is not required in certain profiles. If production requires the secrets, consider omitting `optional:` so the application fails fast when a file is missing. Do not let the application start with an empty password only to fail on the first request.

### 8.1. Secret File Permissions

Processes normally run as a non-root user. Ensure the process UID/GID can read the files while unrelated users have no read access. Use read-only mounts, minimal file permissions, and platform-managed secret volumes.

Never print secret contents to logs when verifying mounts. Check only that the file exists, permissions are right, and the property resolves; if confirmation is needed, log a boolean status, never the value.

## 9. Docker Compose: Configuration and Secrets

Docker Compose can pass non-sensitive configuration via environment variables and mount secrets separately:

```yaml
services:
  orders-api:
    image: registry.example.com/orders-api:native
    ports:
      - "8080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: production
      SERVER_PORT: "8080"
      SPRING_CONFIG_IMPORT: optional:configtree:/run/secrets/
      SPRING_DATASOURCE_URL: jdbc:postgresql://db:5432/orders
      SPRING_DATASOURCE_USERNAME: orders_app
    secrets:
      - source: db_password
        target: spring.datasource.password
      - source: partner_token
        target: api.partner.token

secrets:
  db_password:
    file: ./secrets/db_password
  partner_token:
    file: ./secrets/partner_token
```

Compose mounts secrets under the default `/run/secrets` directory; `target` becomes the config tree filename. Never put secret files in Git. Add the secrets directory to `.gitignore` and restrict read permissions on the host.

File-backed secrets in local Docker Compose are typically implemented via bind mounts; UID/GID/mode options may not behave identically to Swarm secrets. Verify actual file permissions inside the container. For production, prefer a secret manager or an orchestration platform with proper secret management and encryption.

Compose's `.env` file mainly supports variable substitution when rendering Compose configuration. It is not a secret manager. Avoid storing real credentials in committed or broadly shared `.env` files.

## 10. Kubernetes: ConfigMap, Secret, and Volume Mounts

Kubernetes commonly uses a ConfigMap for non-sensitive configuration and a Secret for sensitive data. You can mount a Secret as files and use a config tree:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-api-config
data:
  SPRING_PROFILES_ACTIVE: production
  SPRING_CONFIG_IMPORT: optional:configtree:/run/secrets/
  SPRING_DATASOURCE_URL: jdbc:postgresql://postgres:5432/orders
---
apiVersion: v1
kind: Secret
metadata:
  name: orders-api
type: Opaque
stringData:
  db-password: REPLACE_FROM_SECRET_MANAGER
  partner-token: REPLACE_FROM_SECRET_MANAGER
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      securityContext:
        fsGroup: 10001
      containers:
        - name: app
          image: registry.example.com/orders-api:native
          ports:
            - name: http
              containerPort: 8080
          envFrom:
            - configMapRef:
                name: orders-api-config
          volumeMounts:
            - name: app-secrets
              mountPath: /run/secrets
              readOnly: true
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            allowPrivilegeEscalation: false
      volumes:
        - name: app-secrets
          secret:
            secretName: orders-api
            defaultMode: 0440
            items:
              - key: db-password
                path: spring.datasource.password
              - key: partner-token
                path: api.partner.token
```

This example illustrates manifest structure only. Never commit real secret values in YAML. In production, provision Secrets via External Secrets Operator, CSI Secret Store, sealed/encrypted workflows, or protected pipelines. Kubernetes Secrets are base64-encoded in manifests/API representations; base64 is not encryption. Enable encryption at rest for the datastore, restrict RBAC, and prevent arbitrary namespaces/users from reading Secrets.

For volume permissions, verify user 10001 can actually read the files on the cluster. Depending on storage/volume type, `fsGroup` or a CSI driver policy may be required. Never run the container as root just to bypass permission errors.

### 10.1. Secrets as Environment Variables in Kubernetes

Kubernetes also allows injecting a Secret key into an environment variable:

```yaml
env:
  - name: SPRING_DATASOURCE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-api
        key: db-password
```

This approach is simple, but the secret becomes a process environment variable. Environment variables can leak through diagnostic endpoints, process inspection, or uncontrolled dumps. Prefer file mounts when the application supports config trees and the platform can grant appropriate file permissions.

## 11. Rotation and Configuration Updates

Secrets may be rotated when credentials expire, are suspected of compromise, or on a schedule. However, mounting an updated file does not mean Spring Boot automatically updates properties already injected into beans.

When a Secret volume updates, Kubernetes can update file contents via projected volumes; files mounted with `subPath` behave differently and typically do not receive updates like a root volume mount. Even then, Spring Config Data normally reads files when the application context starts. Beans that already received a password/token may keep holding the old value.

Rotation workflow:

1. Create the new credential on the target system and allow an overlap window if possible.
2. Update the secret store or Kubernetes Secret.
3. Wait for the volume update or update the file mount via the platform mechanism.
4. Restart/recreate pods or trigger a supported reload mechanism in the application.
5. Verify connections succeed with the new credential.
6. Revoke the old credential once all instances have switched over.

Do not assume Docker Compose file secrets or bind mounts automatically reload configuration inside the process. For applications requiring zero-downtime rotation, design an intentional secret provider/credential refresh mechanism and test that lifecycle.

## 12. Shutdown Signals and Graceful Termination Time

When a container stops, the runtime sends a signal to PID 1. With an exec-form `ENTRYPOINT`, the native executable receives SIGTERM directly and Spring Boot can close the application context, stop the server, drain or reject new requests, and close connection pools.

Kubernetes sends SIGTERM and then waits for the termination grace period before killing the process. Configure:

- `terminationGracePeriodSeconds` long enough to drain in-flight requests.
- Readiness transitioning to not-ready before or during shutdown via an appropriate mechanism.
- Spring graceful shutdown and timeouts aligned with the Pod's grace period.
- A `preStop` hook only when genuinely needed; hooks also consume time within the termination grace period.

Do not use a shell wrapper that fails to forward signals. If a wrapper is present, end with `exec` so the native binary becomes the main process.

## 13. Checking Effective Configuration at Container Runtime

You can verify configuration through startup logs, a protected health endpoint, or an internal diagnostic endpoint. Never log passwords or tokens to prove a property was loaded.

A safe check is logging configuration presence:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
class RuntimeConfigurationCheck implements ApplicationRunner {

    private static final Logger log =
        LoggerFactory.getLogger(RuntimeConfigurationCheck.class);

    private final Environment environment;

    RuntimeConfigurationCheck(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        boolean hasDatasourceUrl =
            StringUtils.hasText(
                environment.getProperty("spring.datasource.url")
            );

        boolean hasDatasourcePassword =
            StringUtils.hasText(
                environment.getProperty("spring.datasource.password")
            );

        log.info(
            "Runtime configuration: datasourceUrlPresent={}, passwordPresent={}",
            hasDatasourceUrl,
            hasDatasourcePassword
        );
    }
}
```

The example logs booleans only, never values. Still consider whether even property names or presence flags are sensitive in your specific environment.

Never expose the full `env` or `configprops` Actuator endpoints publicly just to check runtime config. If using Actuator, secure endpoints, limit detail exposure, and restrict access to administrative networks.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Container still uses `local` profile | `SPRING_PROFILES_ACTIVE` not passed or overridden by command line | Check effective property and precedence order |
| Port unchanged despite setting `SERVER_PORT` | Entrypoint does not pass env or higher-precedence source overrides it | Check command args, env, and config data |
| Spring fails to read secret file | Wrong mount path, filename does not match property, or missing config import | Check `SPRING_CONFIG_IMPORT`, file path, and read permissions |
| Container starts with empty password | Secret mount missing while import uses `optional:` | Remove `optional:` for mandatory secrets and fail fast |
| Native executable carries build-machine values | Static initializer read environment during build-time initialization | Move to Spring runtime configuration and adjust class initialization |
| Secret appears in image history | Used Dockerfile `ARG`/`ENV` or `COPY` secret at build time | Remove secret from build context/image and supply at runtime |
| Process does not shut down gracefully | Shell form or wrapper fails to forward SIGTERM | Use exec form or `exec` the native binary inside the wrapper |
| Non-root process cannot read secret | Mounted file UID/GID/mode is incompatible | Adjust ownership/permissions or `fsGroup`/CSI policy |
| Secret rotated but app keeps old value | Spring bound the property at startup | Perform a controlled restart/reload or implement credential refresh |
| Local Compose reads secret, cluster fails | Different mount mechanism and permissions | Inspect directly inside the container/Pod under the actual UID |

## 15. Testing Runtime Arguments and Secrets

Testing should verify both property binding and process behavior:

1. Launch the binary with command-line arguments and confirm the matching Spring properties.
2. Launch the container with environment variables and confirm relaxed binding.
3. Supply the same property in a config file and an environment variable to confirm precedence.
4. Mount a config tree and verify properties from secret files resolve.
5. Test omitting a mandatory secret and confirm the application fails fast.
6. Run under a non-root UID and verify file permissions.
7. Verify secrets do not appear in Docker image layers/history or startup logs.
8. Rotate a secret and verify the restart/reload workflow.
9. Send SIGTERM and measure graceful shutdown duration.
10. Run the same tests against the native executable packaged in the final image, not only on the JVM or in the build container.

A smoke test that merely checks HTTP 200 is not enough. Verify the application actually connects to its database or dependencies using the right runtime credentials, while never printing credentials in logs or test reports.

## 16. Hands-On Exercise: Deploying a Native Container with Environment-Specific Config

**Scenario:** A Spring Boot Native Image service connects to PostgreSQL and a partner API. The same image is deployed to staging and production with different URLs, profiles, and secrets.

**Steps:**

1. Build a native executable and Dockerfile using an exec-form `ENTRYPOINT`, running with a non-root UID.
2. Set the profile, port, and datasource URL as environment variables.
3. Never place passwords or partner tokens in the Dockerfile, image, or source control.
4. Create secret files for the datasource password and partner token.
5. Configure `SPRING_CONFIG_IMPORT=optional:configtree:/run/secrets/` if secrets may be absent locally; production must fail fast when missing.
6. Create a Docker Compose service using `environment` for config and Compose secrets for secret files.
7. Create a Kubernetes Secret/ConfigMap and Deployment mounting secrets read-only.
8. Verify UID/GID, file mode, and read permissions inside the container.
9. Test property precedence by setting the same key in a file, environment variable, and command line.
10. Rotate credentials in staging, verify restart/reload, and revoke old credentials.
11. Send SIGTERM to test graceful shutdown.
12. Run smoke/integration tests on the final native container image.

**Acceptance criteria:**

- The native executable receives Spring command-line arguments and environment variables at startup.
- Non-sensitive configuration is separated from secrets.
- Secrets are supplied via runtime file mounts or a secret manager, not embedded in the image.
- Spring Config Tree maps filenames to the exact properties.
- The application runs non-root and reads only necessary files.
- The rotation procedure includes reload/restart and verification steps.
- The process receives SIGTERM and shuts down gracefully within the platform's grace period.
- The same image runs in both staging and production with different runtime configurations.

## 17. Summary

A container should carry only the native executable and the components required to run it. Spring Boot command-line arguments, environment variables, and config files allow configuration to vary per environment; command-line arguments generally take precedence over environment variables, and environment variables override config data according to externalized configuration ordering. Verify effective properties rather than guessing from a single file.

Secrets must be provided at runtime via a secret manager or file mounts. Spring Config Tree maps filenames to properties, though applications normally read configuration at startup so rotation may require a restart or a dedicated refresh mechanism. Never bake secrets into Dockerfiles or images, never log secret values, restrict file permissions, and run the process as a non-root user.

With GraalVM Native Image, distinguish application arguments from JVM launcher options and Native Image runtime options. Avoid reading environment configuration in static initializers that may run at build time. Testing configuration, secret mounts, permissions, rotation, and graceful shutdown on the final native container image ensures the artifact behaves consistently across deployment environments.

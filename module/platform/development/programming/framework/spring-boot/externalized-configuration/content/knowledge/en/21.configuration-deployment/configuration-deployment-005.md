# Passing Configuration into Docker and Distinguishing Compose Variables from Container Variables

## 1. The Problem and a Common Confusion

A Spring Boot application can run locally with `java -jar` and then be packaged into a Docker image and deployed with Docker Compose without modifying code. Settings such as HTTP port, profile, service URLs, timeouts, database URLs, and credentials can come from the deployment environment. However, in Docker Compose there are **two different variable contexts**:

- **Variables used by the Docker Compose CLI when building the service definition**, such as `HOST_HTTP_PORT` or `IMAGE_TAG` in a `.env` file, substituted into expressions like `${HOST_HTTP_PORT:-18080}`.
- **Actual environment variables inside the container**, such as `SPRING_PROFILES_ACTIVE`, `SERVER_PORT`, and `APP_CLIENT_TIMEOUT`. These must be declared via `services.api.environment`, `services.api.env_file`, image `ENV`, or an equivalent runtime mechanism.

**A variable declared only in a `.env` file for Compose interpolation does not automatically appear in the container's environment.** Conversely, a variable present inside the container is not necessarily the final value Spring Boot uses, because Spring has its own `PropertySource`s and precedence rules.

This lesson builds a complete example from `.env` and `compose.yaml` to `@ConfigurationProperties`, explaining `--env-file` vs. `env_file`, Spring Boot variable naming, container networking, host ports, Spring profiles, secret mounts, precedence, diagnostics, and hands-on scenarios. Examples target Docker Compose v2 and Spring Boot 3.x. Specific Docker/Compose behavior may vary depending on the installed version.

## 2. Three Processing Layers to Distinguish

~~~text
Machine running docker compose
   |
   | Shell vars, .env file, --env-file
   v
Docker Compose CLI
   | Interpolates expressions in compose.yaml
   | Computes image, ports, volumes, environment values
   v
Docker Engine / container runtime
   | Dockerfile ENV + services.env_file + services.environment
   v
Process java -jar app.jar
   | System.getenv(...)
   | Spring Boot Environment
   | Config Data, JVM -D, command-line arguments
   v
Spring Boot Binder / @ConfigurationProperties
   |
   v
Typed Java configuration bean
~~~

First layer: **Compose interpolates from file/host**. Second layer: **Docker provides environment to the container**. Third layer: **Spring Boot picks the final property and binds it**.

Do not use a single precedence table to explain all three. For example, a shell variable can beat `.env` during Compose interpolation; `environment` normally beats a service's `env_file`; and inside Spring Boot, command-line properties normally beat OS environment and standard Config Data files.

## 3. Four Similar-Sounding Names with Different Roles

| Concept | Who reads it? | What is it used for? | Auto-injected into container? |
| --- | --- | --- | --- |
| `.env` in Compose context | Compose CLI | Values for `${VAR}` interpolation | No |
| `docker compose --env-file path` | Compose CLI | Specifies variable file for interpolation | No |
| `services.api.env_file` | Compose at container creation | Loads key/values as container environment | Yes |
| `services.api.environment` | Compose at container creation | Sets specific environment variables | Yes |
| `ENV` in Dockerfile | Docker image/runtime | Sets default values inside the image | Yes, unless overridden at runtime |
| `docker run --env-file` | `docker run` | Passes variables from file directly into container | Yes |
| `docker compose run -e` | `compose run` | Overrides env of a one-off service container | Yes, for that run |

**Most important note:** `docker compose --env-file` and `services.api.env_file` are **not equivalent**, even though their names look almost identical. The CLI option supplies interpolation values for the Compose model; the service property injects file variables into the container.

## 4. Example Project Structure

Suppose the repository is:

~~~text
order-service/
  compose.yaml
  .env
  env/
    runtime.env
  Dockerfile
  pom.xml
  src/main/java/com/example/orders/
    OrderApplication.java
    config/ClientProperties.java
    service/RemoteClient.java
  src/main/resources/
    application.yml
    application-dev.yml
    application-prod.yml
~~~

Purpose of the two files:

- `.env`: only configuration for Compose interpolation, containing no real secrets.
- `env/runtime.env`: values intended to be injected into the container via `env_file`.

For production, never commit any file containing real credentials just because it is named `runtime.env` or `.env`. Use a secret manager or permission-restricted mounted files.

## 5. The .env File Used by Compose for Interpolation

~~~dotenv
# .env
HOST_HTTP_PORT=18080
IMAGE_TAG=local
APP_PROFILE=dev
CLIENT_TIMEOUT=5s
COMPOSE_ONLY_NOTE=this-value-is-not-injected
~~~

In `compose.yaml`:

~~~yaml
services:
  api:
    image: "example/order-service:${IMAGE_TAG:-local}"
    ports:
      - "${HOST_HTTP_PORT:-18080}:8080"
~~~

Compose uses `IMAGE_TAG` to compute the image name and `HOST_HTTP_PORT` to create the host port mapping. However, there is no `environment` or `env_file` declaration for `HOST_HTTP_PORT`, so **you must not conclude the container has the `HOST_HTTP_PORT` variable**.

`COMPOSE_ONLY_NOTE` is not even referenced, so it does not automatically appear inside the container either. A `.env` file is not a "verbatim copy of the container environment."

## 6. The env/runtime.env File Loaded into the Container

~~~dotenv
# env/runtime.env
APP_CLIENT_BASEURL=https://api.example.test
APP_FEATURE_ENABLED=true
LOGGING_LEVEL_COM_EXAMPLE_ORDERS=INFO
~~~

Compose:

~~~yaml
services:
  api:
    env_file:
      - ./env/runtime.env
~~~

Now the `api` service container receives the keys from the file according to Compose rules. Spring Boot can see `APP_CLIENT_BASEURL` and `APP_FEATURE_ENABLED` via the process OS environment.

Do not confuse this: merely having `runtime.env` on disk is not enough. **You must reference it under the service with `env_file`** or supply variables another way.

## 7. Sample compose.yaml Combining Both Sources

~~~yaml
services:
  api:
    image: "example/order-service:${IMAGE_TAG:-local}"
    build:
      context: .
    ports:
      - "${HOST_HTTP_PORT:-18080}:8080"
    env_file:
      - ./env/runtime.env
    environment:
      SERVER_PORT: "8080"
      SPRING_PROFILES_ACTIVE: "${APP_PROFILE:-dev}"
      APP_CLIENT_TIMEOUT: "${CLIENT_TIMEOUT:-3s}"
~~~

What actually happens with the `.env` from earlier:

- Compose evaluates image tag = `local`.
- Compose publishes host port `18080` to container port `8080`.
- Compose reads `APP_PROFILE=dev` and passes a **container** variable named `SPRING_PROFILES_ACTIVE=dev`.
- Compose reads `CLIENT_TIMEOUT=5s` and passes a **container** variable named `APP_CLIENT_TIMEOUT=5s`.
- `SERVER_PORT=8080` enters the container from `environment`.
- `APP_CLIENT_BASEURL` and `APP_FEATURE_ENABLED` enter the container from `env_file`.
- `COMPOSE_ONLY_NOTE` is not automatically passed into the container.

The image name `example/order-service:local` illustrates an image you build; this does not claim any public registry hosts this image.

## 8. Minimal Dockerfile to Run Java

Suppose the project already built an executable Spring Boot JAR named `order-service.jar`:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/order-service.jar /app/app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Commands for dev:

~~~bash
./mvnw -DskipTests package
docker compose up -d --build
~~~

For this example to run in practice, `COPY` must match the JAR name Maven produces (you can configure the artifact name or update the Dockerfile). `EXPOSE 8080` is image metadata and **does not publish ports to the host**; `ports` in Compose creates the host mapping.

Do not hard-code passwords or API keys using Dockerfile `ARG`, `ENV`, or `COPY` into the image. Build layers, registries, or image history can retain credentials.

## 9. How Spring Boot Uses Container Environment

`application.yml`:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  client:
    base-url: https://fallback.example.test
    timeout: 2s
  feature:
    enabled: false
~~~

Java record:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration timeout
) {}
~~~

Main class:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Once Docker has supplied:

~~~text
SPRING_PROFILES_ACTIVE=dev
SERVER_PORT=8080
APP_CLIENT_TIMEOUT=5s
APP_CLIENT_BASEURL=https://api.example.test
APP_FEATURE_ENABLED=true
~~~

Spring Boot can bind `ClientProperties` to:

~~~text
baseUrl: https://api.example.test
timeout: Duration.ofSeconds(5)
~~~

Values from the OS environment normally override values in standard `application.yml`. **Compose supplies variables; the Spring Boot Binder converts strings into `URI`, `Duration`, and other Java types.**

## 10. Compose Interpolation Syntax

| Syntax | Meaning |
| --- | --- |
| `${VAR}` | Uses value if present; when missing, may substitute empty string and warn |
| `${VAR:-fallback}` | Uses fallback if variable is unset **or** empty |
| `${VAR-fallback}` | Uses fallback if variable is unset; empty remains its value |
| `${VAR:?message}` | Errors if variable is missing or empty |
| `${VAR?message}` | Errors if variable is unset |
| `$$` | Escapes to preserve a literal dollar sign in Compose context |

Example:

~~~yaml
services:
  api:
    ports:
      - "${HOST_HTTP_PORT:-18080}:8080"
    environment:
      APP_REGION: "${APP_REGION:-ap-southeast-1}"
      DEPLOY_ENV: "${DEPLOY_ENV:?Set DEPLOY_ENV}"
~~~

This syntax is resolved by **Compose** before the container is created. A missing `DEPLOY_ENV` makes Compose fail with a message instead of launching a misconfigured container.

Final environment values are **strings**; Spring Boot converts `"false"` into a boolean or `"2s"` into a `Duration`.

## 11. Default .env and Shell Variables

Suppose `.env` says:

~~~dotenv
CLIENT_TIMEOUT=5s
~~~

but the shell running Compose has:

~~~bash
export CLIENT_TIMEOUT=10s
docker compose up -d
~~~

Compose normally uses the shell value to interpolate `${CLIENT_TIMEOUT}` instead of the value in `.env`. Exact file lookup and precedence rules also depend on the working directory, project directory, and `--env-file`; for complex deployments, run from an explicit context and verify results safely.

If `compose.yaml` does not reference `CLIENT_TIMEOUT` under `environment`, neither the shell variable nor `.env` **automatically enters the container**.

## 12. docker compose --env-file Only Changes the Interpolation Source

~~~bash
docker compose --env-file ./deploy/prod.compose.env up -d
~~~

With file:

~~~dotenv
# deploy/prod.compose.env
APP_PROFILE=prod
HOST_HTTP_PORT=18081
~~~

And Compose:

~~~yaml
services:
  api:
    ports:
      - "${HOST_HTTP_PORT}:8080"
    environment:
      SPRING_PROFILES_ACTIVE: "${APP_PROFILE}"
~~~

The container receives `SPRING_PROFILES_ACTIVE=prod` because of the `environment` declaration, **and does not automatically receive `APP_PROFILE` or `HOST_HTTP_PORT`**.

You can also write `docker compose --env-file path -f compose.yaml up -d` in the same command; the key point is that `--env-file` is at the CLI level and is processed for interpolation.

### Do not confuse with docker run --env-file

~~~bash
docker run --env-file ./env/runtime.env example/order-service:local
~~~

`docker run --env-file` actually injects keys from the file into the container's environment. Same flag name, **different meaning** from `docker compose --env-file`.

## 13. environment and env_file Can Complement or Override Each Other

Suppose:

~~~dotenv
# env/runtime.env
APP_CLIENT_TIMEOUT=5s
APP_FEATURE_ENABLED=false
~~~

And:

~~~yaml
services:
  api:
    env_file:
      - ./env/runtime.env
    environment:
      APP_CLIENT_TIMEOUT: "2s"
~~~

The container receives `APP_CLIENT_TIMEOUT=2s` and `APP_FEATURE_ENABLED=false` in the standard case: `environment` declarations take precedence over matching keys from `env_file`.

If there are multiple env files:

~~~yaml
services:
  api:
    env_file:
      - ./env/common.env
      - ./env/staging.env
~~~

matching keys in later files normally override earlier files in Compose. This is the order **between container env files**, not the order between `.env` and shell variables during CLI interpolation.

### Keys without values

~~~yaml
environment:
  - DEBUG
~~~

differs from:

~~~yaml
environment:
  - DEBUG=
~~~

The first tells Compose to resolve the value from the host/calling environment; if unresolved, it may be omitted from the container environment. The second explicitly represents an empty value. Prefer mapping syntax with explicit values or checked interpolation to avoid ambiguity.

## 14. Three Precedence Layers, Three Questions

| Layer | What to determine | What to remember |
| --- | --- | --- |
| Compose interpolation | Shell, `.env`, `--env-file` | Which variables were used to render the Compose model? |
| Container runtime | `environment`, `env_file`, image `ENV`, run overrides | Which keys and values does the container actually have? |
| Spring Boot | OS env, JVM system props, CLI args, Config Data, other `PropertySource`s | What is the final effective property for binding? |

A simple rule of thumb: **`.env` is not a Spring `PropertySource`** just because it sits next to `compose.yaml`. Only when Compose turns a value into container environment can Spring see it as an OS environment property.

If Spring Boot receives an unexpected value, check the container env, and also check whether `--app.client.timeout=...` or `-Dapp.client.timeout=...` is overriding it.

## 15. Spring Boot Environment Variable Naming and Relaxed Binding

Spring Boot supports relaxed binding with `@ConfigurationProperties`. The standard way to convert a canonical property name to an env variable name:

1. Dots `.` become `_`.
2. Hyphens `-` within a segment are removed.
3. Convert to uppercase.
4. List indices are represented using numbers and appropriate underscores.

| Spring Boot property | Environment variable |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `app.client.timeout` | `APP_CLIENT_TIMEOUT` |
| `app.client.base-url` | `APP_CLIENT_BASEURL` |
| `app.feature.enabled` | `APP_FEATURE_ENABLED` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `app.worker.max-retries` | `APP_WORKER_MAXRETRIES` |
| `app.pipelines[0].name` | `APP_PIPELINES_0_NAME` |
| `app.pipelines[0].retry.backoff` | `APP_PIPELINES_0_RETRY_BACKOFF` |

Pay attention to `app.client.base-url`: its canonical env form is `APP_CLIENT_BASEURL`; **do not assume** `APP_CLIENT_BASE_URL` means the same thing. An extra underscore can represent a different hierarchy level.

When a project uses many custom properties, writing a key-mapping table and verifying it with an integration test substantially reduces deployment mistakes.

## 16. Compose Placeholders vs. Spring Placeholders

In Compose:

~~~yaml
environment:
  APP_CLIENT_TIMEOUT: "${CLIENT_TIMEOUT:-3s}"
~~~

The expression is resolved by Compose. In `application.yml`:

~~~yaml
app:
  client:
    timeout: "${APP_CLIENT_TIMEOUT:2s}"
~~~

This expression is resolved by Spring Boot `Environment` inside the Java process. Flow:

~~~text
Compose .env: CLIENT_TIMEOUT=5s
    |
    v
Compose ${CLIENT_TIMEOUT:-3s} -> "5s"
    |
    v
container APP_CLIENT_TIMEOUT=5s
    |
    v
Spring ${APP_CLIENT_TIMEOUT:2s} -> "5s"
    |
    v
Binder -> Duration.ofSeconds(5)
~~~

Only if Compose does not pass `APP_CLIENT_TIMEOUT` does the Spring placeholder apply its `2s` fallback. Do not accidentally set two different defaults for the same contract without deciding which layer owns it.

### When a literal dollar sign is needed in compose.yaml

Compose has the `$$` rule to skip one round of interpolation when keeping a dollar sign for a later stage. However, if you only need a Spring placeholder, it is usually simpler to keep it in `application.yml` rather than nesting Spring placeholders through multiple Compose/YAML/shell layers.

## 17. Host Port, Container Port, and server.port

~~~yaml
services:
  api:
    ports:
      - "18080:8080"
    environment:
      SERVER_PORT: "8080"
~~~

Read this in three parts:

- `18080`: port published on the **host machine**.
- `8080` to the right of `:`: **container** port that Docker forwards traffic to.
- `SERVER_PORT=8080`: port **Spring Boot** listens on inside the container.

From the host:

~~~text
http://localhost:18080
~~~

From another container on the same Compose network:

~~~text
http://api:8080
~~~

If you change `SERVER_PORT=9090` while keeping `ports: "18080:8080"`, the host still forwards to container port 8080, while Spring listens on 9090. Update the container-side port mapping accordingly.

`EXPOSE 8080` in the Dockerfile only describes metadata; it does not publish ports. There is no need to publish ports of every service to the host if only internal services call one another.

## 18. localhost Inside a Container Is Not the Host Machine

With Compose:

~~~yaml
services:
  api:
    image: example/order-service:local
  db:
    image: postgres:17
~~~

The `api` container calling `localhost:5432` looks for a database inside `api`'s own network namespace, not the `db` container.

To reach the database service across the Compose network, use the service name:

~~~yaml
services:
  api:
    environment:
      SPRING_DATASOURCE_URL: "jdbc:postgresql://db:5432/orders"
~~~

`db` is the service hostname resolved by Docker DNS on the appropriate network. Do not use host-published ports to connect two containers on the same network unless there is a specific architectural reason.

Basic `depends_on` helps with startup order, **not guaranteeing the database is ready**. When needed, use a healthcheck/`condition: service_healthy` supported by your Compose version or appropriate connection retry logic.

## 19. Spring Profiles and Compose Profiles Are Two Different Features

Compose has service profiles:

~~~yaml
services:
  api:
    image: example/order-service:local

  debug-ui:
    image: example/debug-ui:local
    profiles:
      - debug
~~~

The command:

~~~bash
docker compose --profile debug up -d
~~~

controls whether the `debug-ui` service is included in the deployment. **It does not automatically set** `spring.profiles.active=debug` for Spring Boot.

To activate a Spring profile in Java:

~~~yaml
services:
  api:
    environment:
      SPRING_PROFILES_ACTIVE: "${APP_PROFILE:-dev}"
~~~

A `.env` file:

~~~dotenv
APP_PROFILE=prod
~~~

supplies `SPRING_PROFILES_ACTIVE=prod` so Spring Boot can read `application-prod.yml`. `APP_PROFILE` is an arbitrary Compose variable name; `SPRING_PROFILES_ACTIVE` is the name Spring understands.

| Concept | Controls |
| --- | --- |
| Compose `profiles` | Which services run |
| Spring `spring.profiles.active` | Properties/beans/profile conditions in the application |
| Compose `.env` | Variables for model interpolation |
| Compose `env_file` | Variables injected into the container |

## 20. Dockerfile ENV vs. Runtime Overrides

~~~dockerfile
FROM eclipse-temurin:21-jre
ENV SERVER_PORT=8080
ENV APP_CLIENT_TIMEOUT=3s
COPY target/order-service.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

If Compose specifies:

~~~yaml
environment:
  APP_CLIENT_TIMEOUT: "5s"
~~~

the container uses the runtime value `5s` for the matching key, instead of the image default `3s`. `SERVER_PORT` continues to be inherited when no override is given.

Do not put API tokens or passwords in Dockerfile `ENV`. Values can persist in image metadata and copies of the artifact.

Also check `command` in Compose: if `ENTRYPOINT` is `java -jar` and Compose passes `--spring.profiles.active=prod`, Spring Boot normally prioritizes that CLI argument over the OS environment variable `SPRING_PROFILES_ACTIVE`.

## 21. docker run and docker compose run

With Docker directly:

~~~bash
docker run --rm \
  -p 18080:8080 \
  -e SPRING_PROFILES_ACTIVE=dev \
  -e APP_CLIENT_TIMEOUT=5s \
  example/order-service:local
~~~

`-e` passes container environment directly.

~~~bash
docker run --rm \
  --env-file ./env/runtime.env \
  -p 18080:8080 \
  example/order-service:local
~~~

`docker run --env-file` also supplies container environment.

With Compose:

~~~bash
docker compose run -e APP_CLIENT_TIMEOUT=1s api
~~~

`run` creates a **one-off container** and overrides env for that run, without replacing the existing service container created by `docker compose up -d`. `run` also differs in port publishing behavior; do not extrapolate `run` behavior completely to `up`.

## 22. Diagnosing the Compose Model Without Leaking Data

Useful commands:

~~~bash
docker compose config --quiet
docker compose config --services
~~~

`--quiet` validates configuration without printing the full interpolated YAML; `--services` lists service names.

The command:

~~~bash
docker compose config
~~~

typically prints the interpolated model. If `environment` contains credentials from `${SECRET}`, the output can expose secrets. Never paste the raw output into chat, issues, or unprotected CI artifacts.

Some Compose versions support:

~~~bash
docker compose config --environment
~~~

to inspect variables used for interpolation. This output **can also contain sensitive values**. Use only in controlled environments and log streams.

Do not use full debug output by default in CI jobs that have secrets.

## 23. Safely Inspecting Selected Variables Inside a Container

After:

~~~bash
docker compose up -d
~~~

you can inspect **a single non-sensitive variable**:

~~~bash
docker compose exec api sh -lc 'printf "profile=%s\n" "$SPRING_PROFILES_ACTIVE"'
~~~

or:

~~~bash
docker compose exec api sh -lc 'printf "port=%s\n" "$SERVER_PORT"'
~~~

These examples assume the image includes `sh`. For distroless images without a shell, another safe inspection approach is required.

Never run and share `docker compose exec api printenv` in production: it can print passwords, API keys, and tokens. `docker inspect` can also reveal environment variables from container metadata. Restrict access to the Docker socket and corresponding diagnostic tools.

**A variable existing in the container** is not proof Spring Boot picked that value; `--app.client.timeout` or JVM `-D` can override it.

## 24. Why Does .env Have a Value Yet Java Does Not Receive It?

Example:

~~~dotenv
# .env
APP_CLIENT_TIMEOUT=5s
~~~

~~~yaml
services:
  api:
    image: example/order-service:local
~~~

Without `environment` or `env_file`, Spring Boot does not automatically receive `APP_CLIENT_TIMEOUT`.

Two fixes:

~~~yaml
services:
  api:
    environment:
      APP_CLIENT_TIMEOUT: "${APP_CLIENT_TIMEOUT:-3s}"
~~~

or:

~~~yaml
services:
  api:
    env_file:
      - ./.env
~~~

The second approach intentionally loads **the entire `.env` file into the container**, potentially passing Compose-only interpolation variables as well. Separate files and pass only required variables into the container to avoid leaks and runtime environment noise.

## 25. Why Does env_file Have a Value Yet @ConfigurationProperties Still Uses Fallback?

Example file:

~~~dotenv
APP_CLIENT_BASE_URL=https://api.example.test
~~~

yet the model is:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl) {}
~~~

and default YAML:

~~~yaml
app:
  client:
    base-url: https://fallback.example.test
~~~

The variable name may be wrong: the canonical env mapping for `app.client.base-url` is normally `APP_CLIENT_BASEURL`, not `APP_CLIENT_BASE_URL`. Try fixing the name and recreating the container so the runtime variable updates.

Also check:

1. Does the service reference the right `env_file`?
2. Is the file path right in Compose's context?
3. Is `environment` overriding the same key?
4. Was the container recreated after editing the file?
5. Is the `@ConfigurationProperties` bean scanned/enabled?
6. Is a CLI argument or higher-precedence `PropertySource` overriding it?
7. Can the value be converted to `URI`/`Duration`?

Do not edit fallbacks in the JAR to mask a failure to pass variables in Compose.

## 26. Editing .env Does Not Automatically Change an Existing Container's Environment

Container environment is determined when the container is created. When editing `.env` or `env/runtime.env` on the host, the **running Java process does not automatically receive new variables**.

Typically you must:

1. Ensure Compose reads the updated file.
2. Have Compose recompute the service model.
3. Recreate/redeploy the container when runtime settings change.
4. Let the Spring Boot process start up and rebind properties.

The command:

~~~bash
docker compose up -d
~~~

normally lets Compose reconcile services whose configuration changed. To force recreation in a lab:

~~~bash
docker compose up -d --force-recreate api
~~~

Note this command can cause downtime; do not run it blindly in production without a rollout plan.

Similarly, Spring Boot `@ConfigurationProperties` are normally bound at startup and do not auto-refresh merely because an external file was edited.

## 27. Host Shell Variables Are Not Automatically Copied Wholesale into Containers

Suppose the host shell has:

~~~bash
export APP_CLIENT_TIMEOUT=7s
docker compose up -d
~~~

The Compose CLI can use that host value inside `${APP_CLIENT_TIMEOUT}`. However, if the service does not reference that variable, the container does not automatically inherit the entire shell environment.

Explicit forwarding:

~~~yaml
services:
  api:
    environment:
      APP_CLIENT_TIMEOUT: "${APP_CLIENT_TIMEOUT:-3s}"
~~~

This separation is helpful for security: containers do not accidentally inherit cloud credentials, user secrets, or session metadata lying around on the host. Avoid overly broad `env_file` usage or dumping the entire shell env into containers.

## 28. Config Data and PropertySources Have Their Own Precedence

Container has:

~~~text
APP_CLIENT_TIMEOUT=7s
~~~

yet the app starts with:

~~~bash
java -jar app.jar --app.client.timeout=500ms
~~~

In standard Spring Boot, the CLI argument `--app.client.timeout=500ms` has higher precedence than OS environment, so the bound value can be `500 ms`.

A JVM system property:

~~~bash
java -Dapp.client.timeout=1s -jar app.jar
~~~

can also override OS environment when no higher-precedence source is present.

Other sources such as `SPRING_APPLICATION_JSON` or test `PropertySource`s have their own positions. When debugging, determine the **effective Spring property**, not just the Docker variable.

## 29. Compose Override Files and Paths

With multiple files:

~~~bash
docker compose -f compose.yaml -f compose.prod.yaml up -d
~~~

Compose merges models according to its rules and file order. Check:

- Which file sets `services.api.environment`?
- Which file sets `env_file`, and how are file paths resolved relative to the base/project directory?
- Which `ports` apply after merging?
- Which variables are interpolated from shell/`.env`/`--env-file`?
- Which variables does the Spring process ultimately receive?

Do not equate `compose.prod.yaml` with the Spring `prod` profile. A Compose override can set `SPRING_PROFILES_ACTIVE=prod`, but that is an **explicit declaration**, not an automatic feature.

In CI/CD, pin the working directory, `-f` ordering, and env file paths so deployments on different runners do not resolve different values.

## 30. Secrets Should Not Be Arbitrarily Interpolated into Environment

Risky example:

~~~yaml
services:
  api:
    environment:
      SPRING_DATASOURCE_PASSWORD: "${DB_PASSWORD}"
~~~

This may work, yet secrets can appear in Compose config output, container metadata, process diagnostics, or CI logs. `.env` files are not automatically encrypted; never commit secrets to the repo.

Depending on your platform, consider:

- A secret manager with workload identity.
- Docker Compose secrets mounted as files.
- File mounts with appropriate filesystem permissions.
- Runtime provisioning channels managed by the orchestrator.
- Least privilege, rotation, auditing, and restricted logging.

Environment variables still have legitimate uses, but they are not the best default for every credential. Never put real secrets into README examples.

## 31. Docker Compose Secrets with Spring Boot configtree

Spring Boot can load key/values from a file tree via `configtree:`. Compose can mount secrets using target filenames. Illustrative example with PostgreSQL:

~~~yaml
services:
  api:
    image: example/order-service:local
    environment:
      SPRING_DATASOURCE_URL: "jdbc:postgresql://db:5432/orders"
      SPRING_DATASOURCE_USERNAME: "orders_app"
      SPRING_CONFIG_IMPORT: "configtree:/run/secrets/"
    secrets:
      - source: db_password
        target: spring.datasource.password

  db:
    image: postgres:17
    environment:
      POSTGRES_DB: "orders"
      POSTGRES_USER: "orders_app"
      POSTGRES_PASSWORD_FILE: "/run/secrets/db_password"
    secrets:
      - source: db_password
        target: db_password

secrets:
  db_password:
    file: ./secrets/db-password.txt
~~~

Flow:

~~~text
./secrets/db-password.txt (protected host file)
            |
            v
Docker Compose secret mount for api:
   /run/secrets/spring.datasource.password
            |
            v
SPRING_CONFIG_IMPORT=configtree:/run/secrets/
            |
            v
Spring Boot property: spring.datasource.password
~~~

For the `db` container, the PostgreSQL image reads `/run/secrets/db_password` via `POSTGRES_PASSWORD_FILE`.

**The filename in configtree determines the property name.** If the file under `/run/secrets/` is only named `db_password`, Spring Boot does not automatically infer `spring.datasource.password`. Declaring `target: spring.datasource.password` satisfies that requirement.

This example requires a built application image, real secret files outside the repository, and appropriate volume/healthcheck settings for a complete deployment. Host-file-based Docker Compose secrets do not encrypt the source files themselves; filesystem permissions, backups, and secure provisioning remain essential.

## 32. Required vs. Optional configtree

In Spring Boot you can use:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

or:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

`optional:` allows skipping a missing location per Config Data rules. In development, that can be convenient; in production where a password is required, failing fast when the secret mount is missing is usually better.

If a secret volume is rotated, Config Data and already-initialized beans or connection pools do not update immediately unless the application has an appropriate refresh/recreate mechanism. Rotation requires planning rollouts and when to revoke old credentials.

## 33. Mount a Config File Instead of Hundreds of Variables

For deeply nested configuration such as pipeline lists, maps, and multiple endpoints, you can mount a configuration file:

~~~yaml
services:
  api:
    volumes:
      - ./deploy/config:/etc/order-config:ro
    environment:
      SPRING_CONFIG_ADDITIONAL_LOCATION: "optional:file:/etc/order-config/"
      SPRING_PROFILES_ACTIVE: "prod"
~~~

Spring Boot can search for additional Config Data at that location per your version's rules. For directory locations, use a `file:/.../` path with the trailing slash.

Large YAML files are usually far easier to manage than dozens of `APP_PIPELINES_0_...` variables. However, mounted files are not automatically secure: files used for non-secret config may have different access policies than secret files.

Remember precedence: OS environment can still override keys inside an additional file; a mounted file does not automatically beat every source.

## 34. Lists and Maps When Supplied via Environment

Spring Boot list example:

~~~text
APP_PIPELINES_0_NAME=orders
APP_PIPELINES_0_RETRY_MAXATTEMPTS=3
APP_PIPELINES_1_NAME=invoices
~~~

Docker only passes strings. The Spring Boot Binder uses Java types and relaxed binding rules to build `List<Pipeline>`.

However, across multiple `PropertySource`s, **lists are typically replaced by the higher-precedence source rather than deep-merged element by element**. Supplying only one field of element `[0]` via env can leave the final list missing items from lower sources.

If order does not matter and items have stable identifiers, consider `Map<String,Pipeline>`. For lists where order matters, manage the entire list in one controlled configuration source.

## 35. CI/CD: Runner Variables Are Not Automatically Container Variables

A pipeline has:

~~~text
DEPLOY_ENV=prod
HOST_HTTP_PORT=18080
APP_CLIENT_TIMEOUT=2s
~~~

Compose can use them for interpolation. Yet the container only receives variables supplied through service configuration or a runtime mechanism.

~~~yaml
services:
  api:
    environment:
      SPRING_PROFILES_ACTIVE: "${DEPLOY_ENV:?Missing environment}"
      APP_CLIENT_TIMEOUT: "${APP_CLIENT_TIMEOUT:?Missing timeout}"
~~~

In CI, avoid logging the entire shell env or running `docker compose config` and uploading output containing credentials. Do not expose production secrets to untrusted pull requests. Prefer short-lived tokens and grant access only to jobs/services that genuinely need them.

## 36. .gitignore and .env.example

You can organize:

~~~text
.env.example      # contains no real secrets, safe to commit
.env              # local; managed per repo policy
env/runtime.env   # if it contains real secrets, do not commit
secrets/          # local secret files, restricted permissions
~~~

Example `.env.example`:

~~~dotenv
HOST_HTTP_PORT=18080
APP_PROFILE=dev
CLIENT_TIMEOUT=3s
~~~

Adding `.env` and `secrets/` to `.gitignore` helps reduce accidental commits of untracked files, but does not remove already-committed files, copies in Git history, image layers, or CI artifacts. If a real credential leaks, revoke/rotate it per incident response.

## 37. 12-Step Debugging Workflow

1. **Identify the failing container/service**, rather than lumping all env vars of the Compose project together.
2. **Classify the variable**: Compose interpolation only, container environment, or Spring property?
3. **Inspect `compose.yaml`** and any `-f` override files in order.
4. **Inspect interpolation sources**: shell, `.env`, and `--env-file`, without printing secrets.
5. **Inspect `environment` and `env_file`** on the exact service.
6. **Check Spring canonical env naming**, such as `APP_CLIENT_BASEURL`.
7. **Check whether the container needs recreation** after editing files.
8. **Inspect a few non-sensitive variables** inside the container without dumping everything.
9. **Check `ENTRYPOINT`/command** for `--spring.*` or `-D` overrides.
10. **Check active Spring profiles and Config Data**, including `spring.config.import`.
11. **Check networking/ports**: service DNS, `localhost`, host/container ports, and DB readiness.
12. **Check Java binding**: `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`, prefix, types, and validation.

Do not conclude a `@ConfigurationProperties` error is Docker failing to pass variables before checking the remaining layers. Nor should you debug by printing all credentials.

## 38. Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Host port changed, yet Java does not see `HOST_HTTP_PORT` | Variable only interpolated by Compose | Pass explicitly if Java actually needs it |
| `--env-file` has key, yet container does not receive it | Confused CLI flag with service `env_file` | Use `environment`/`env_file` |
| Container gets old timeout | Container not recreated after editing env file | Redeploy in a controlled manner |
| `env_file` says `5s`, yet container has `2s` | `environment` overrides it | Check runtime precedence |
| Java still uses fallback URL | Wrong env name/prefix, or another `PropertySource` wins | Check `APP_CLIENT_BASEURL` and effective value |
| Spring profile unchanged when passing `--profile debug` | Compose profiles are not Spring profiles | Set `SPRING_PROFILES_ACTIVE` |
| Container cannot connect to `localhost:5432` | Calling itself | Use `db:5432` |
| Host mapping `18080:8080` fails after changing `server.port` | App inside no longer listens on 8080 | Update container port mapping |
| Secret shows up in `docker compose config` | Direct credential interpolation | Switch to secret mount/manager; limit debug output |
| Configtree does not create password property | Secret filename does not match key | Use target `spring.datasource.password` |
| Compose starts, yet DB refuses connections | DB not ready or wrong credentials | Healthcheck/retry and verify credentials |
| List config loses elements | Env overrides part of list | Supply entire list or use a map instead |

## 39. Self-Practice Exercises

### Exercise 1 — .env contains HOST_PORT

~~~dotenv
HOST_PORT=18080
~~~

~~~yaml
ports:
  - "${HOST_PORT}:8080"
~~~

**Question:** Does `HOST_PORT` automatically appear in the container? **Answer:** No. Compose only uses it to compute the port mapping.

### Exercise 2 — Mapping APP_PROFILE

~~~dotenv
APP_PROFILE=prod
~~~

~~~yaml
environment:
  SPRING_PROFILES_ACTIVE: "${APP_PROFILE}"
~~~

**Answer:** The container receives `SPRING_PROFILES_ACTIVE=prod`; it does not automatically receive `APP_PROFILE`.

### Exercise 3 — Using only CLI env-file

~~~bash
docker compose --env-file ./deploy/prod.env up -d
~~~

The file has `APP_CLIENT_TIMEOUT=9s`, yet Compose does not reference this key. **Answer:** It does not automatically enter the container.

### Exercise 4 — Service env_file

~~~yaml
services:
  api:
    env_file:
      - ./env/runtime.env
~~~

The file has `APP_CLIENT_TIMEOUT=9s`. **Answer:** This is a runtime container environment source.

### Exercise 5 — environment and env_file share a key

`env_file` has `APP_CLIENT_TIMEOUT=5s`, `environment` has `APP_CLIENT_TIMEOUT=2s`. **Answer:** Expected runtime value is `2s` because `environment` takes precedence.

### Exercise 6 — Host and container ports

`ports: "18080:8080"`, `SERVER_PORT=8080`. **Answer:** The host uses 18080; Spring Boot listens on 8080 inside the container.

### Exercise 7 — Database service DNS

Inside the `api` container, JDBC to `localhost:5432` does not reach the `db` container. **Answer:** Use `db:5432` when on the same Compose network.

### Exercise 8 — Compose profile and Spring profile

Does `docker compose --profile debug up -d` automatically activate Spring profile `debug`? **Answer:** No.

### Exercise 9 — Canonical env name

Which env variable name does property `app.client.base-url` use? **Answer:** `APP_CLIENT_BASEURL` per canonical Spring Boot relaxed binding.

### Exercise 10 — Secrets and configtree

A secret file is named `db_password`, yet Spring Boot imports `configtree:/run/secrets/` and expects `spring.datasource.password`. **Answer:** The filename must be mapped appropriately, e.g., mount target `spring.datasource.password`.

### Exercise 11 — Editing .env

You edit `.env`, yet the old Java process does not change timeout. **Answer:** Update/recreate the container and Spring context per deployment policy.

### Exercise 12 — Safe debugging

Can you paste full `docker compose config` into an issue when secrets are interpolated? **Answer:** No; output may contain credentials.

## 40. Final Reference Cheat Sheet

| Purpose | Mechanism |
| --- | --- |
| Variables used to evaluate Compose model | `.env`, shell, or `docker compose --env-file` |
| Actual variables inside container | `services.environment` or `services.env_file` |
| Image default values | Dockerfile `ENV` |
| Host port from variable | `"${HOST_PORT:-18080}:8080"` |
| Spring active profile | `SPRING_PROFILES_ACTIVE` |
| Java listening port | `SERVER_PORT` or `server.port` |
| Internal database URL | `jdbc:postgresql://db:5432/orders` |
| Custom Spring property | `APP_CLIENT_TIMEOUT`, `APP_CLIENT_BASEURL` |
| Check Compose model without printing full values | `docker compose config --quiet` |
| List service names | `docker compose config --services` |
| Inspect a few non-sensitive variables | `docker compose exec api sh -lc '...'` |
| Secret files for Spring Boot | `configtree:/run/secrets/` |
| Protect production secrets | Secret manager/secret mount and least privilege |
| Avoid accidental host env injection | Pass only an explicit allowlist |
| Update container environment | Recreate/redeploy the container |
| Find final property Spring uses | Check `Environment` precedence and Binder |

## 41. Conclusion

Remember these three statements:

1. **`.env` and `docker compose --env-file` primarily serve Compose interpolation.**
2. **Service `environment` and `env_file` inject actual variables into the container; host or Compose-only variables do not enter automatically.**
3. **Spring Boot `Environment` and Binder determine the final Java properties from container, file, CLI, and other `PropertySource`s.**

When a value is wrong, trace the exact pipeline: **shell/.env → Compose interpolation → service runtime environment → Java process → Spring Environment → @ConfigurationProperties**. When handling secrets, restrict permissions and avoid exposure via Git, `docker compose config`, `printenv`, and Docker metadata. Clearly separating these layers keeps applications consistent across local runs, Docker Compose, and deployed environments.

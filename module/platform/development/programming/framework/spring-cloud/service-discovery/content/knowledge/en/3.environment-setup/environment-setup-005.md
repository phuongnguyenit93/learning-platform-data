# Configuring application.yml, Profiles, and Environment Variables

A Spring Cloud application typically runs across multiple environments: local machine, Docker, staging, and production. Each environment may use a different port, Consul address, database, or logging level. If these values are hardcoded in source code, switching environments is error-prone and can expose sensitive information.

Spring Boot provides externalized configuration so applications can read settings from `application.yml`, profile-specific files, environment variables, command-line arguments, and other external sources. This lesson explains how to organize configuration by environment, activate profiles, and override values with environment variables in a Spring Cloud Service Discovery project.

## 1. The Role of application.yml

Spring Boot automatically looks for configuration files by convention, such as `application.properties` or `application.yml`. YAML files represent configuration as a hierarchy, which fits well when there are many nested property groups like `spring.application`, `spring.cloud.consul`, and `management.endpoints`.

Example base configuration for a service:

```yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      discovery:
        register: true
        health-check-path: /actuator/health
        health-check-interval: 10s

server:
  port: ${SERVER_PORT:8080}

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
```

Meaning of the properties:

- `spring.application.name` sets the service name registered with Consul and used by consumers for discovery.
- `spring.cloud.consul.host` and `port` identify the Consul Agent address or Consul endpoint the application connects to, depending on deployment topology.
- `spring.cloud.consul.discovery.register` enables service registration.
- `health-check-path` and `health-check-interval` specify the health check endpoint and interval.
- `server.port` sets the application's HTTP port.
- `management.endpoints.web.exposure.include` allows access to the listed Actuator endpoints.
- `show-details: never` avoids exposing internal health indicator details via the health endpoint.

The expression `${CONSUL_HOST:localhost}` means reading the `CONSUL_HOST` variable; if unset, `localhost` is used. Similarly, `SERVER_PORT` defaults to `8080`. Default values are helpful for local environments, but you should not use arbitrary fallbacks for required values in production.

YAML relies on indentation. Child levels are typically indented by two spaces; do not use tabs. A property placed at the wrong level can prevent Spring Boot from reading the intended configuration.

## 2. Separating Configuration by Profile

A profile is an environment label or configuration group that Spring Boot can activate at startup. A common organization is keeping shared configuration in `application.yml`, then creating separate files per environment:

```text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-docker.yml
├── application-staging.yml
└── application-prod.yml
```

Spring Boot loads `application.yml` as the base configuration. When the `local` profile is active, properties in `application-local.yml` are applied on top and can override matching values from the base file. Properties not redeclared are still inherited from the base configuration.

### 2.1. Local Configuration

Example `application-local.yml`:

```yaml
spring:
  cloud:
    consul:
      host: localhost
      port: 8500

logging:
  level:
    root: INFO
    org.springframework.cloud.consul: DEBUG
```

The local profile points to a Consul instance running on the developer's machine and enables more detailed logging for the Consul integration. There is no need to copy the entire `application.yml`; only declare the values that need to differ.

### 2.2. Docker Configuration

In Docker Compose, the service name is commonly used as the hostname on the internal network. Example `application-docker.yml`:

```yaml
spring:
  cloud:
    consul:
      host: consul
      port: 8500
```

Here `consul` must match the service name or DNS alias resolvable from the application container. `localhost` inside an application container points to that container itself, not automatically to the Consul container.

### 2.3. Production Configuration

Production typically pulls connection details from the deployment environment or a secret manager. Example `application-prod.yml`:

```yaml
spring:
  cloud:
    consul:
      host: ${CONSUL_HOST}
      port: ${CONSUL_PORT:8500}
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

server:
  port: ${SERVER_PORT:8080}

logging:
  level:
    root: INFO
```

The placeholders `${CONSUL_HOST}`, `${DB_URL}`, `${DB_USERNAME}`, and `${DB_PASSWORD}` have no default values. If the environment does not supply them, the application reports an error during configuration resolution instead of silently connecting to an incorrect address. Never commit passwords, tokens, private keys, or connection strings containing credentials to Git.

Profiles select configuration, but they do not automatically provision the underlying infrastructure. For example, activating the `docker` profile does not start the Consul container; that container must still be declared and running in the deployment environment.

## 3. Activating a Profile When Running the Application

You do not need to edit configuration files every time you switch environments. You can select a profile via command-line arguments or environment variables.

Run the JAR with the local profile:

```bash
java -jar target/order-service.jar --spring.profiles.active=local
```

Run with the Docker profile:

```bash
java -jar target/order-service.jar --spring.profiles.active=docker
```

Or use an environment variable:

```bash
SPRING_PROFILES_ACTIVE=local java -jar target/order-service.jar
```

On Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
java -jar target/order-service.jar
```

To remove the environment variable in the current PowerShell session:

```powershell
Remove-Item Env:SPRING_PROFILES_ACTIVE
```

Do not put `spring.profiles.active` inside `application-local.yml` or `application-prod.yml` to make a file activate itself. Choose the profile from an appropriate base config or from the launch environment. If you want to set a default profile when none is specified, you can use `spring.profiles.default`; however, take care so a production application does not accidentally run with local configuration.

## 4. Overriding Configuration with Environment Variables

Spring Boot maps dot-separated property names to uppercase environment variable names using underscores instead of dots. For most standard properties, you can apply this rule:

| Property in YAML | Environment Variable |
| --- | --- |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `spring.cloud.consul.host` | `SPRING_CLOUD_CONSUL_HOST` |
| `spring.cloud.consul.port` | `SPRING_CLOUD_CONSUL_PORT` |
| `spring.cloud.consul.discovery.register` | `SPRING_CLOUD_CONSUL_DISCOVERY_REGISTER` |
| `server.port` | `SERVER_PORT` |
| `management.endpoints.web.exposure.include` | `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |

Environment variables can override values in configuration files. For example, if `application.yml` sets `server.port: 8080` but the environment supplies `SERVER_PORT=8085`, the application will use port `8085`.

Setting multiple variables on Linux or macOS:

```bash
SPRING_PROFILES_ACTIVE=local \
SERVER_PORT=8081 \
CONSUL_HOST=localhost \
java -jar target/order-service.jar
```

Setting variables in PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SERVER_PORT = "8081"
$env:CONSUL_HOST = "localhost"
java -jar target/order-service.jar
```

Note that `SERVER_PORT` is a common property with a short, convenient name. Longer properties must follow Spring Boot's name-conversion rules accurately. For maps, lists, or complex property names, check the relaxed binding rules for your Spring Boot version instead of guessing variable names.

## 5. Precedence Order When Multiple Configuration Sources Exist

A property can appear in several places. Spring Boot applies a property source precedence order; a higher-priority source overrides a lower-priority one. In a typical application run, you can remember this general order from highest to lowest priority:

1. Command-line arguments, e.g., `--server.port=8082`.
2. `SPRING_APPLICATION_JSON` and external configuration sources of corresponding priority.
3. Java system properties, e.g., `-Dserver.port=8083`.
4. Process environment variables.
5. Loaded configuration files, such as `application.yml` and profile-specific files.
6. Default values declared in the application.

Actual precedence also depends on property source type, file location, config imports, and Spring Boot version. Among configuration files, profile-specific config is applied after non-profile config so it can override base values.

For example, when all of the following exist simultaneously:

```yaml
# application.yml
server:
  port: 8080
```

```yaml
# application-local.yml
server:
  port: 8081
```

And the environment variable:

```text
SERVER_PORT=8082
```

When running with the `local` profile, environment variables take higher precedence than configuration files, so the application uses port `8082`. If you also pass `--server.port=8083`, the command-line argument wins and the application uses port `8083`.

When the effective value is not what you expect, inspect both the active profiles and every overriding source. You can enable appropriate configuration logging in development or use the Actuator `env`/`configprops` endpoints when properly secured. Do not expose these endpoints publicly, as they can leak configuration details.

## 6. Running Multiple Local Instances with Different Configurations

An application can run as multiple processes on the same machine to test registering multiple instances with Consul. Each process needs its own port; the processes can share the local profile and the same service name so Consul recognizes them as instances of one service.

Example running two JARs in two separate PowerShell terminals.

First terminal:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SERVER_PORT = "8081"
java -jar target/order-service.jar
```

Second terminal:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SERVER_PORT = "8082"
java -jar target/order-service.jar
```

Or running on Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=local SERVER_PORT=8081 java -jar target/order-service.jar
SPRING_PROFILES_ACTIVE=local SERVER_PORT=8082 java -jar target/order-service.jar
```

Both processes share `spring.application.name: order-service`, but use different ports. When registration succeeds, Consul can display two instances. Verify that your Spring Cloud Consul version's registration configuration generates a unique instance ID for each process; if configuring `instance-id` manually, ensure values do not collide.

If using Actuator health checks, the endpoint must be exposed and reachable on each port. Check each instance individually:

```bash
curl -i http://localhost:8081/actuator/health
curl -i http://localhost:8082/actuator/health
```

Then check the Consul Catalog/Health API to confirm both instances are registered and passing. Having two processes running does not guarantee they registered successfully; check startup logs, Consul address, health checks, and instance IDs.

## 7. Common Configuration Mistakes

| Symptom | Common Cause | How to Check or Fix |
| --- | --- | --- |
| Application ignores values in `application-local.yml` | `local` profile is not active or file is in the wrong location/name | Check `SPRING_PROFILES_ACTIVE` and place the file in `src/main/resources`. |
| Environment variable does not override YAML | Wrong variable name, wrong data type, or variable not passed to the process | Verify name per relaxed binding and print the variable value in the exact shell running the app. |
| Cannot connect to Consul when running in Docker | Configured `localhost` inside the application container | Use the Consul service hostname on the Docker network, e.g., `consul`. |
| Application reports missing placeholder | Required variable such as `DB_URL` or `CONSUL_HOST` was not provided | Set the variable in the runtime environment or add an appropriate secure config source. |
| Two instances fail to start simultaneously | Sharing the same `server.port` or an unexpected port override | Assign a unique port to each process and check command-line arguments/env vars. |
| Two instances appear under the same ID | `instance-id` is statically configured and collides | Use a per-instance unique ID, e.g., combining hostname and port. |
| Application uses the wrong production/local profile | Leftover `SPRING_PROFILES_ACTIVE` variable in shell, IDE, or run config | Print the active profile in startup logs and clear stale variables when needed. |

Do not solve errors by setting values in more places without knowing which source wins. Find the effective property source first, then fix the single source with clear ownership.

## 8. Safe Configuration Management Principles

- Put shared, non-sensitive configuration in `application.yml`.
- Put only environment-specific differences in `application-{profile}.yml`.
- Use environment variables or a secret manager for passwords, tokens, private keys, and credentials.
- Never commit `.env` files containing secrets or production values into the repository.
- Use placeholders with defaults for local values that genuinely have safe defaults; leave required placeholders without defaults when the app should fail fast on missing config.
- Keep the same service name across instances of the same service; vary port and instance ID per process.
- Restrict exposure of sensitive Actuator endpoints and protect operational endpoints with appropriate security.
- Document required variables in deployment documentation, describing only names and purposes without secret values.

## 9. Key Takeaways

- `application.yml` holds base configuration; `application-{profile}.yml` holds environment-specific differences.
- Activate profiles using `SPRING_PROFILES_ACTIVE` or `--spring.profiles.active`.
- Environment variables override file configuration per Spring Boot's precedence order; command-line arguments typically have higher precedence.
- The `${NAME:default}` placeholder enables environment variables with optional defaults where appropriate.
- Each local process needs its own port and non-colliding instance ID to register multiple instances of the same service.
- Never store credentials in YAML committed to Git; use environment variables or a secret manager.

By separating configuration into profiles and managing varying values through the environment, the same Spring Boot artifact can run consistently locally, in Docker, and in production without modifying source code for each deployment target.

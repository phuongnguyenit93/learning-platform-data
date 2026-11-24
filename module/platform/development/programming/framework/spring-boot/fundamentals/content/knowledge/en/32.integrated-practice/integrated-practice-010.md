# Packaging a JAR Once and Running with External Configuration in Two Environments

A Spring Boot application often runs across multiple environments such as development and production. Both environments may run the same business logic and application version while differing in database, external service endpoints, ports, logging levels, feature flags, and secrets.

A controllable deployment approach is to **build an executable JAR once, then run that exact artifact with different external configuration in each environment**. The JAR packages the application code and dependencies; configuration files and secrets are supplied at runtime. Consequently, you do not need a separate JAR for dev and another for production.

This practice lesson covers the full flow: building an executable JAR with Maven or Gradle, laying out deployment directories, loading external configuration, selecting profiles, supplying environment variables, verifying property precedence, and confirming both environments run with the intended configuration. The examples use a Spring Boot service with a database and partner API; application names, paths, and endpoints are illustrative.

## 1. Deployment Goal and Principles

Suppose we have an application named `orders-service`. It needs the same code version in dev and production, separate databases, separate partner API endpoints, configurable timeouts/logging/feature flags, securely supplied secrets, and the ability to trace exactly which JAR is running.

~~~text
                 Source code
                     |
                     v
             Maven / Gradle build
                     |
                     v
          orders-service.jar (once)
                     |
             +-------+-------+
             |               |
             v               v
         DEV host        PROD host
             |               |
       external config  external config
       DEV profile      PROD profile
       DEV secrets      PROD secrets
             |               |
             v               v
       Spring Boot      Spring Boot
       application      application
             |               |
             v               v
       DEV database     PROD database
       DEV partner      PROD partner
~~~

Key principles:

1. **Build the artifact once:** the JAR is produced from a specific commit/build.
2. **Supply configuration at runtime:** never bake production database URLs, passwords, or endpoints into the JAR.
3. **Same artifact, different environment:** differences live in external config, environment variables, and runtime options.
4. **Each environment has its own secrets:** dev never uses production credentials and vice versa.
5. **Traceable:** record the version, commit SHA, and checksum of the released JAR.

Building a different JAR per environment increases the risk of build drift: two artifacts can contain different code or dependencies while sharing the same release label. The build-once, deploy-many model reduces that risk.

## 2. Separating the Artifact from Configuration

A Spring Boot executable JAR typically contains:

~~~text
orders-service.jar
├── META-INF/
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/orders/...
    │   └── application.yml
    └── lib/
        ├── spring-boot-...
        ├── spring-context-...
        └── ...
~~~

`application.yml` inside the JAR can hold shared defaults or safe local development values. At runtime, Spring Boot can also read files outside the JAR. External configuration takes higher precedence than packaged defaults under Config Data / property source rules.

An easy-to-operate directory layout:

~~~text
deploy/
├── dev/
│   ├── orders-service.jar
│   └── config/
│       ├── application.yml
│       └── application-dev.yml
└── prod/
    ├── orders-service.jar
    └── config/
        ├── application.yml
        └── application-prod.yml
~~~

Both directories hold copies of **the exact same JAR**. Config contents differ per environment. When using an artifact registry, each host pulls the exact same artifact by released version or digest.

Never package database passwords, API tokens, private keys, broker credentials, cloud access keys, or signing secrets into the JAR. Supply them via a secret manager, environment variables, mounted secret files, or your deployment platform's security mechanism.

## 3. Building an Executable JAR with Maven

With Maven and the Spring Boot Maven Plugin, plugin configuration normally sits in the POM:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

If using `spring-boot-starter-parent`, the plugin version is managed alongside the Spring Boot release. If the project only imports the Boot BOM without the parent, you may need to specify the plugin version and configuration explicitly.

Build:

~~~bash
mvn clean package
~~~

For a project configured to repackage an executable JAR, the artifact typically ends up at `target/orders-service-1.0.0.jar`. The exact filename depends on `artifactId`, `version`, and build settings.

Test-run:

~~~bash
java -jar target/orders-service-1.0.0.jar
~~~

This command runs the JAR with the current JVM using its packaged defaults. You do not need to build separate `orders-service-dev.jar` or `orders-service-prod.jar` files.

Inspect JAR contents:

~~~bash
jar tf target/orders-service-1.0.0.jar
~~~

A Spring Boot executable JAR declares the appropriate launcher in its manifest. If `java -jar` reports no main manifest attribute or cannot find the main class, you may be running the plain JAR instead of the Boot executable JAR, or the repackage plugin did not run properly.

## 4. Building an Executable JAR with Gradle

With Gradle and the Spring Boot plugin:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
    java
}
~~~

Build the executable JAR:

~~~bash
./gradlew clean bootJar
~~~

The artifact typically sits in `build/libs/`. For example:

~~~bash
java -jar build/libs/orders-service-1.0.0.jar
~~~

Plugin names and versions in the example are placeholders. Pick versions compatible with your Java version, Gradle wrapper, and Spring Boot release.

If the project produces both a plain JAR and a Boot executable JAR, clearly identify which task/output gets released. Never copy an arbitrary file from `build/libs` into a deployment directory.

| Task | Maven | Gradle |
|---|---|---|
| Build executable JAR | `mvn clean package` with Boot plugin | `./gradlew bootJar` |
| Typical output location | `target/` | `build/libs/` |
| Run | `java -jar path/app.jar` | `java -jar path/app.jar` |
| Dependency inspection | `mvn dependency:tree` | `./gradlew dependencies` |

Once the artifact is built, providing external configuration at runtime works the same way. Runtime configuration mechanics do not depend on whether Maven or Gradle built the JAR.

## 5. Default Configuration Inside the JAR

`src/main/resources/application.yml` can contain shared, non-sensitive defaults:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080

app:
  partner:
    timeout: 3s
  checkout:
    allow-test-cards: false

logging:
  level:
    root: INFO
~~~

This file is packaged onto the JAR's classpath and acts as **default configuration**. Do not put production-specific details here if the artifact is meant to run across multiple environments. Never hard-code production database URLs, internal production hostnames, or passwords.

### Binding Configuration with `@ConfigurationProperties`

~~~java
@ConfigurationProperties(prefix = "app.partner")
@Validated
public record PartnerProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout
) {
    public PartnerProperties {
        if (timeout != null && timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.partner.timeout must not be negative"
            );
        }
    }
}
~~~

Register with `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(PartnerProperties.class)` in a suitable configuration.

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Typed properties centralize configuration, type conversion, and validation. For production, required endpoints should fail fast if missing or malformed rather than silently falling back to an unsuitable default URL.

## 6. Where Does Spring Boot Look for External Configuration?

When running an executable JAR, Spring Boot uses its Config Data mechanism to search default locations for configuration files. Common locations include:

~~~text
classpath:/
classpath:/config/
file:./
file:./config/
~~~

Modern versions also support searching subdirectories under config according to documented location rules. Verify exact behavior against your application's Spring Boot version when relying on fine-grained rules.

Points to remember:

- `classpath:/application.yml` is the file packaged inside the JAR.
- `file:./application.yml` is a file in the process's working directory.
- `file:./config/application.yml` is a file in the `config` directory under the working directory.
- External locations take higher precedence than packaged defaults according to Config Data location order.

### Working Directory Affects Relative Paths

Suppose the JAR lives at `/opt/orders/orders-service.jar`. If you run:

~~~bash
cd /opt/orders
java -jar orders-service.jar
~~~

then `file:./config/application.yml` points to `/opt/orders/config/application.yml`.

If you run the JAR from a different working directory, `./config` is resolved relative to the new working directory, not automatically relative to the JAR's directory. This is a common reason applications "fail to read the config file" even though the file exists.

## 7. Organizing Two Environments with Profiles

Spring Profiles allow selecting configuration bundles per environment.

Config file inside the JAR:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080

app:
  partner:
    timeout: 3s
  checkout:
    allow-test-cards: false
~~~

External file for dev:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_dev
    username: orders_dev
    password: `DOLLAR`{DB_PASSWORD}

app:
  partner:
    base-url: https://partner-dev.example.test
  checkout:
    allow-test-cards: true

logging:
  level:
    root: DEBUG
    com.example.orders: DEBUG
~~~

External file for production:

~~~yaml
spring:
  datasource:
    url: `DOLLAR`{DB_URL}
    username: `DOLLAR`{DB_USERNAME}
    password: `DOLLAR`{DB_PASSWORD}

app:
  partner:
    base-url: `DOLLAR`{PARTNER_BASE_URL}
  checkout:
    allow-test-cards: false

logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

Place the profile-specific files:

~~~text
config/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

`application.yml` holds shared settings; `application-dev.yml` loads only when `dev` is active; `application-prod.yml` loads only when `prod` is active.

You can keep shared defaults in the JAR and place only overrides externally. Then external profile files only contain properties that actually differ.

Set `spring.profiles.active` in a profile-independent configuration source such as command line, environment variables, or the shared `application.yml`. Never place it inside `application-prod.yml` expecting that profile to activate itself. Spring needs to know active profiles before deciding which profile-specific documents to load.

## 8. Running the JAR in the Dev Environment

Suppose the deployment directory is:

~~~text
deploy/dev/
├── orders-service.jar
└── config/
    ├── application.yml
    └── application-dev.yml
~~~

Run from `deploy/dev`:

~~~bash
cd deploy/dev
java -jar orders-service.jar --spring.profiles.active=dev
~~~

Spring Boot reads defaults in the JAR, external configuration under `working_directory/config`, and then loads the profile-specific configuration for `dev`. When `config/application-dev.yml` defines `spring.datasource.url`, it supplies the dev database URL.

Supply dev secrets in Linux/macOS shells:

~~~bash
export DB_PASSWORD='dev-password-from-local-secret-store'
java -jar orders-service.jar --spring.profiles.active=dev
~~~

PowerShell:

~~~powershell
$env:DB_PASSWORD = 'dev-password-from-local-secret-store'
java -jar .\orders-service.jar --spring.profiles.active=dev
~~~

The password above is only for illustrating syntax. Never commit real passwords to a repository or store them in shared deployment scripts.

## 9. Running the Same JAR in the Production Environment

Deployment directory:

~~~text
deploy/prod/
├── orders-service.jar
└── config/
    ├── application.yml
    └── application-prod.yml
~~~

Linux/macOS shell:

~~~bash
cd deploy/prod
export DB_URL='jdbc:postgresql://db.prod.internal:5432/orders'
export DB_USERNAME='orders_app'
export DB_PASSWORD='injected-by-secret-manager'
export PARTNER_BASE_URL='https://partner.example.com'

java -jar orders-service.jar --spring.profiles.active=prod
~~~

PowerShell:

~~~powershell
Set-Location .\deploy\prod
$env:DB_URL = 'jdbc:postgresql://db.prod.internal:5432/orders'
$env:DB_USERNAME = 'orders_app'
$env:DB_PASSWORD = 'injected-by-secret-manager'
$env:PARTNER_BASE_URL = 'https://partner.example.com'

java -jar .\orders-service.jar --spring.profiles.active=prod
~~~

In real production, a secret manager or orchestration platform should inject these environment variables. Never record credentials in shell history, shared batch files, or CI logs.

| Attribute | Dev | Production |
|---|---|---|
| Artifact | Same JAR version | Same JAR version |
| Active profile | `dev` | `prod` |
| Database | Dev database | Production database |
| Partner API | Sandbox/dev endpoint | Production endpoint |
| Logging | May enable DEBUG for app packages | Typically INFO or ops policy |
| Test-only feature | May be enabled with controls | Disabled |
| Secrets | Dev credentials | Production secrets |
| Deploy config | External dev config | External prod config |

Profiles are not a security mechanism. If a dangerous feature must never be active in production, add startup validation/policies and production configuration tests rather than relying solely on profile names.

## 10. Changing External Config Without Rebuilding the JAR

Suppose the JAR contains default:

~~~yaml
server:
  port: 8080
~~~

External config can override it:

~~~yaml
server:
  port: 8090
~~~

At startup, the server uses whichever value has higher precedence per Config Data / property source ordering.

External config can change database URLs, partner API endpoints, connection pool sizes, logging levels, feature flags, timeout/retry values, and management endpoint configuration.

After modifying external config, you normally must restart the process so Spring reads the updated configuration at startup. Spring Boot does not automatically reload every property in every file simply because a file changed on disk. If an application uses a dedicated refresh or config server mechanism, that is a separate design requiring explicit configuration and control.

Never unpack and edit files inside the JAR to switch environments. Unpacking, modifying, and re-archiving alters the artifact and breaks reproducibility. External configuration exists specifically to keep environment settings out of the artifact.

## 11. Property Precedence: Which Value Wins?

Spring Boot uses multiple property sources. The main rule to remember is that **a higher-precedence source overrides lower-precedence sources**.

Among common sources, the general order from lowest to highest is:

~~~text
Packaged application.yml
          |
          v
External application.yml / profile config
          |
          v
OS environment variables
          |
          v
Java system properties (-D...)
          |
          v
Spring command-line arguments (--key=value)
~~~

The complete order also includes default properties, `@PropertySource`, random values, JNDI/servlet sources, and test property sources. Whenever exact precedence matters, consult the property source precedence table for your exact Spring Boot version.

Example with the same key:

Packaged:

~~~yaml
server:
  port: 8080
~~~

External:

~~~yaml
server:
  port: 8081
~~~

Environment:

~~~text
SERVER_PORT=8082
~~~

Command line:

~~~bash
java -jar orders-service.jar --server.port=8083
~~~

The effective result will be `8083` because command-line properties have higher precedence than the sources above in standard setups.

Within Config Data, locations and profile-specific files follow their own ordering rules. After Config Data loads, OS environment variables, system properties, and command-line arguments apply their own precedence on top. When multiple sources define the same key, check both layers.

## 12. Adding External Locations with `spring.config.additional-location`

Default directories are usually sufficient when deployments follow a `./config/` layout. If config lives elsewhere, you can add a location:

~~~bash
java -jar orders-service.jar \
  --spring.config.additional-location=file:./external-config/
~~~

Layout example:

~~~text
deploy/prod/
├── orders-service.jar
└── external-config/
    ├── application.yml
    └── application-prod.yml
~~~

Run:

~~~bash
cd deploy/prod
java -jar orders-service.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:./external-config/
~~~

`spring.config.additional-location` **adds** locations to the default search locations. Properties in added locations can override values from earlier locations per Config Data ordering.

If a directory must exist, specify the location without `optional:` so startup fails when it is missing. If it is genuinely optional, write:

~~~bash
--spring.config.additional-location=optional:file:./external-config/
~~~

Use `optional:` intentionally. If production requires an external config directory yet marks it optional, the application may silently boot with unsuitable default values.

When pointing to a directory, the trailing slash tells Spring it is a directory location and to search for config filenames inside it. Spring Boot handles Config Data, profile-specific files, and property sources automatically; do not manually parse YAML and merge maps into `Environment` when Config Data already supports the use case.

## 13. `spring.config.location` vs. `spring.config.additional-location`

These two properties are easily confused:

| Property | Meaning |
|---|---|
| `spring.config.location` | Specifies config locations to load; can replace default locations |
| `spring.config.additional-location` | Appends locations to the default search locations |

Example:

~~~bash
java -jar orders-service.jar \
  --spring.config.location=file:./only-this-config/
~~~

This command can stop default locations from being searched normally. If the JAR relies on `classpath:/application.yml`, replacing all locations may prevent packaged defaults from loading as expected.

When you only want to add external config while keeping packaged defaults in the JAR, usually use `spring.config.additional-location`. Use `spring.config.location` when you want complete control over every location read and actively supply every location needed.

## 14. `spring.config.name` and `spring.config.import`

By default, Spring Boot looks for the basename `application`. To use a different name:

~~~bash
java -jar orders-service.jar \
  --spring.config.name=orders \
  --spring.config.additional-location=file:./config/
~~~

Spring then looks for files such as `orders.properties`, `orders.yml`, `orders-dev.yml`, and `orders-prod.yml` per Config Data rules. Change the basename only when your organization follows a clear convention.

In the Config Data mechanism, one file can import another:

~~~yaml
spring:
  config:
    import: "optional:file:./secrets/application-secrets.yml"
~~~

`spring.config.import` is processed during Config Data loading. Imports have their own precedence and profile activation rules; do not treat it like a plain YAML include directive.

Putting secrets in a separate file does not make them safe by itself. If the file resides in the repository or gets packaged into the JAR, it can still leak. Control where the file is stored, file permissions, backups, and how it is mounted to the process.

### Config Tree and Mounted Secrets

Some platforms mount secrets as files, and Spring Boot supports config tree imports:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Files inside the directory map to properties matching their filenames. Confirm the exact syntax, mount path, and behavior for your Boot version. Do not mark an import `optional:` if that secret is mandatory for safe operation.

## 15. Environment Variables and Relaxed Binding

Spring Boot maps property names to environment variables using relaxed binding rules. Common examples:

| Property | Environment variable |
|---|---|
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `server.port` | `SERVER_PORT` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `app.partner.base-url` | `APP_PARTNER_BASEURL` |
| `app.partner.timeout` | `APP_PARTNER_TIMEOUT` |

For environment variables, dots become underscores and names are normally uppercased; hyphens inside property names are removed per Boot's mapping rules. For complex properties or collections/maps, verify against relaxed binding documentation.

Production run example:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
export SERVER_PORT=8080
export SPRING_DATASOURCE_URL='jdbc:postgresql://db.prod.internal:5432/orders'
export SPRING_DATASOURCE_USERNAME='orders_app'
export SPRING_DATASOURCE_PASSWORD='injected-secret'
export APP_PARTNER_BASEURL='https://partner.example.com'

java -jar orders-service.jar
~~~

Environment variables are widely used and supported across platforms. However, they can be visible in process inspections, diagnostic dumps, or host operations configs. If your platform supports mounted secret files / config trees or a secret manager integration, evaluate your actual security policy. Never log the entire Environment or print passwords while debugging.

## 16. Using Command-Line Arguments for Runtime Overrides

Spring Boot accepts properties passed as:

~~~bash
java -jar orders-service.jar --server.port=8090
~~~

You can pass multiple properties:

~~~bash
java -jar orders-service.jar \
  --spring.profiles.active=prod \
  --server.port=8080 \
  --logging.level.com.example.orders=INFO
~~~

Command-line properties have high precedence among common sources. They are convenient for intentional overrides, though you should avoid stuffing long lists of production settings into command-line scripts when external config/environment can manage them cleanly.

Spring Boot options like `--name=value` are placed after the JAR path:

~~~bash
java -jar orders-service.jar --spring.profiles.active=dev
~~~

JVM options such as `-Xms`, `-Xmx`, and `-Dname=value` must be placed before `-jar`:

~~~bash
java -Xms256m -Xmx768m \
  -Duser.timezone=UTC \
  -jar orders-service.jar \
  --spring.profiles.active=prod
~~~

Misplacing them can make Java treat JVM options as application arguments or fail to apply them as expected.

## 17. Selecting Profiles with Environment Variables and YAML Documents

You do not have to pass the profile on the command line.

Linux/macOS:

~~~bash
export SPRING_PROFILES_ACTIVE=dev
java -jar orders-service.jar
~~~

PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'dev'
java -jar .\orders-service.jar
~~~

Production platforms can set `SPRING_PROFILES_ACTIVE=prod`. Profiles only select configuration bundles. They do not generate credentials, encrypt passwords, or prevent unauthorized users from reading a prod file.

You can split configurations into separate files:

~~~text
application.yml
application-dev.yml
application-prod.yml
~~~

Or use multi-document YAML with profile activation:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080

---
spring:
  config:
    activate:
      on-profile: dev

logging:
  level:
    root: DEBUG

---
spring:
  config:
    activate:
      on-profile: prod

logging:
  level:
    root: INFO
~~~

Distinguish:

- `spring.profiles.active` chooses which profiles are running.
- `spring.config.activate.on-profile` specifies that a document/file applies only when the matching profile is active.

A document does not activate a profile just because it contains `on-profile`.

## 18. Shared Configuration and Overriding Only What Differs

You do not need to copy the entire `application.yml` into every environment.

Packaged `application.yml`:

~~~yaml
spring:
  application:
    name: orders-service

server:
  port: 8080

app:
  partner:
    timeout: 3s
  checkout:
    allow-test-cards: false

logging:
  level:
    root: INFO
~~~

External `application-dev.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_dev
    username: orders_dev
    password: `DOLLAR`{DB_PASSWORD}

app:
  partner:
    base-url: https://partner-dev.example.test
  checkout:
    allow-test-cards: true

logging:
  level:
    com.example.orders: DEBUG
~~~

External `application-prod.yml`:

~~~yaml
spring:
  datasource:
    url: `DOLLAR`{DB_URL}
    username: `DOLLAR`{DB_USERNAME}
    password: `DOLLAR`{DB_PASSWORD}

app:
  partner:
    base-url: `DOLLAR`{PARTNER_BASE_URL}
  checkout:
    allow-test-cards: false
~~~

Keys in external profile configs override lower-precedence values; omitted keys keep their defaults.

For lists, maps, and some complex structures, profile-specific configs may replace the entire list from a lower-precedence document instead of appending to it as developers sometimes expect. If configuration includes lists such as CORS origins, allowed hosts, or custom routes, verify actual binding behavior and write tests for the final result.

## 19. Validation to Catch Misconfiguration Early at Startup

An application should not start with a blank database URL or malformed partner endpoint when those dependencies are mandatory.

~~~java
@ConfigurationProperties(prefix = "app.partner")
@Validated
public record PartnerProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout
) {
    public PartnerProperties {
        if (timeout != null && timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.partner.timeout must not be negative"
            );
        }
    }
}
~~~

You can use Jakarta Bean Validation annotations when a validation provider is present. Constraints such as `@NotNull` require the corresponding validation dependency.

In production config:

~~~yaml
app:
  partner:
    base-url: `DOLLAR`{PARTNER_BASE_URL}
    timeout: 2s
~~~

If `PARTNER_BASE_URL` is not supplied, the placeholder fails to resolve and startup fails. This is far better than silently using an empty URL or a localhost URL in production.

Reasonable defaults include safe timeouts, default log levels, safe-by-default disabled features, or default ports for local runs. Never provide defaults for production passwords, production database endpoints, private keys, or sensitive tenant IDs.

## 20. Preventing Dev Config from Leaking into Production

A common mistake is packaging `application-dev.yml` inside the JAR and accidentally running production with the `dev` profile. Consequences can include connecting to local/sandbox databases, overly verbose DEBUG logging, enabling test-only features, disabling security, or activating mock implementations.

Control profiles at the deployment boundary:

- Dev deployment explicitly declares the `dev` profile.
- Prod deployment explicitly declares the `prod` profile.
- Production startup scripts/manifests set the profile explicitly.
- Production config uses mandatory endpoints and secrets.
- Startup validation verifies critical invariants.
- CI includes tests confirming production configuration never enables test-only features.

Do not rely on an ambiguous default profile if the application behaves significantly differently across environments. Simply hiding profile files inside the JAR is also no substitute for validating runtime configuration.

## 21. Using External Config Files on Linux and Windows

Linux layout:

~~~text
/opt/orders/
├── current/
│   └── orders-service.jar
├── config/
│   ├── application.yml
│   └── application-prod.yml
└── logs/
~~~

Run:

~~~bash
cd /opt/orders
java -jar current/orders-service.jar \
  --spring.profiles.active=prod
~~~

Spring looks for `./config/` relative to the `/opt/orders` working directory. The JAR's location in `/opt/orders/current` does not dictate relative config locations.

Use an absolute location when a service manager uses a different working directory:

~~~bash
java -jar /opt/orders/current/orders-service.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/opt/orders/config/
~~~

Windows layout:

~~~text
C:\apps\orders\
├── orders-service.jar
└── config\
    ├── application.yml
    └── application-prod.yml
~~~

PowerShell:

~~~powershell
Set-Location C:\apps\orders
$env:SPRING_PROFILES_ACTIVE = 'prod'
java -jar .\orders-service.jar
~~~

To point to another directory, use `--spring.config.additional-location=file:./external-config/`. Ensure the process has read permissions on the config directory and mounted secrets. For URIs on Windows, pay attention to `file:` URI syntax and slashes; test paths on the target OS.

`$env:NAME = 'value'` sets an environment variable for the current PowerShell session and child processes launched from it. It does not persist permanently across reboots. For Windows Services, configure environment variables in the service manager or service wrapper.

## 22. Startup Scripts and systemd

A startup script standardizes the launch command, but should never store static secrets.

Linux `start-dev.sh` example:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/orders-dev"
JAR="$APP_DIR/orders-service.jar"

cd "$APP_DIR"

if [ -z "$DB_PASSWORD" ]; then
  echo "DB_PASSWORD is required" >&2
  exit 1
fi

exec java -jar "$JAR" \
  --spring.profiles.active=dev
~~~

Production scripts can check required variables similarly:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/orders-prod"
JAR="$APP_DIR/orders-service.jar"

cd "$APP_DIR"

if [ -z "$DB_URL" ] || [ -z "$DB_USERNAME" ] ||
   [ -z "$DB_PASSWORD" ] || [ -z "$PARTNER_BASE_URL" ]; then
  echo "Required production configuration is missing" >&2
  exit 1
fi

exec java -jar "$JAR" \
  --spring.profiles.active=prod
~~~

Production commonly uses systemd, a container orchestrator, or a service manager to handle restarts, working directory, environment/secret injection, CPU/memory limits, stdout/stderr collection, and shutdown timeouts.

Illustrative systemd unit file:

~~~ini
[Unit]
Description=Orders Service
After=network.target

[Service]
User=orders
Group=orders
WorkingDirectory=/opt/orders
Environment=SPRING_PROFILES_ACTIVE=prod
EnvironmentFile=/etc/orders/orders.env
ExecStart=/usr/bin/java -jar /opt/orders/current/orders-service.jar
Restart=on-failure
RestartSec=5
SuccessExitStatus=143
TimeoutStopSec=40

[Install]
WantedBy=multi-user.target
~~~

`/etc/orders/orders.env` can store server-provisioned environment variables protected by host permissions. Never commit that file to source control or grant read permissions to unauthorized users.

Because relative paths depend on the working directory, setting `WorkingDirectory` explicitly ensures Spring finds `./config`. Otherwise, the service manager may launch the process from another directory and miss or misload config.

## 23. Supplying Secrets via Files Instead of Environment Variables

Some platforms mount secrets as files:

~~~text
/run/secrets/
├── db-password
└── partner-api-token
~~~

You can use Spring Boot's Config Tree support:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Files in the directory map to properties with matching names. Confirm exact syntax, mount paths, and behavior for your Boot version.

Only the user running the application should be able to read required secrets. Never make them world-readable, never copy secrets into release/artifact directories, never print file contents in logs, and maintain a secret rotation workflow. Updating a secret file on disk does not automatically update every bean already holding credentials; understand your application's lifecycle and refresh behavior.

## 24. Configuring Database, Partner API, and Logging

Dev database example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_dev
    username: orders_dev
    password: `DOLLAR`{DB_PASSWORD}
    hikari:
      maximum-pool-size: 5
~~~

Production database:

~~~yaml
spring:
  datasource:
    url: `DOLLAR`{DB_URL}
    username: `DOLLAR`{DB_USERNAME}
    password: `DOLLAR`{DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
~~~

Pool sizes above are illustrative. Production sizing must reflect database connection limits, instance count, and application concurrency. When moving across environments, also verify JDBC drivers, TLS/SSL, database permissions, schema/migration versions, network/firewall/DNS, transaction isolation, and timezones.

Partner endpoint:

~~~yaml
app:
  partner:
    base-url: `DOLLAR`{PARTNER_BASE_URL}
    timeout: 2s
~~~

Choose timeouts based on SLAs and client behavior. If retries are enabled, total deadline—including retry count, backoff, and per-attempt timeout—must fit within the system's overall request budget.

Dev logging:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
~~~

Production logging:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

DEBUG logs can increase log volume and expose request data or internal details. Enable them temporarily only per operational procedures and ensure sensitive data is redacted. In containers or service managers, stdout/stderr are typically collected by the platform. If logging to files, manage rotation, permissions, disk usage, and retention.

## 25. Changing Ports and Management Endpoints

External config can set the port:

~~~yaml
server:
  port: 8081
~~~

Or via environment variable `SERVER_PORT=8081`.

If using Actuator, review management port/path settings separately:

~~~yaml
management:
  server:
    port: 8082
  endpoints:
    web:
      exposure:
        include: health,info
~~~

The management port differs from the server port when configured independently. Never expose every actuator endpoint to public networks just for convenience. When using readiness/liveness probes, confirm they hit the intended endpoint/port and have proper authorization and network policies.

## 26. Inspecting Effective Configuration Without Leaking Secrets

When two environments behave differently, you need to verify which properties took effect. Never dump the entire `Environment` because doing so can expose credentials.

You can safely log selected non-sensitive values:

~~~java
@Component
public class RuntimeConfigurationLogger {

    private static final Logger log =
            LoggerFactory.getLogger(RuntimeConfigurationLogger.class);

    public RuntimeConfigurationLogger(
            Environment environment,
            PartnerProperties properties
    ) {
        log.info(
                "Active profiles: {}",
                Arrays.toString(environment.getActiveProfiles())
        );
        log.info(
                "Partner timeout: {}",
                properties.timeout()
        );
    }
}
~~~

Never log database passwords, authorization tokens, private keys, full secret-bearing URIs, or whole property sources.

Actuator provides an `env` endpoint to inspect environment/property sources when configured and exposed. It is a sensitive endpoint requiring strict access control and sanitization. Never expose it publicly just to debug config. In many cases, logging a few safe properties or using a debugger is sufficient.

## 27. Checking JAR Contents and Checksums

You can list resources inside the JAR:

~~~bash
jar tf orders-service.jar
~~~

Look for:

~~~text
BOOT-INF/classes/application.yml
BOOT-INF/classes/application-dev.yml
BOOT-INF/classes/application-prod.yml
~~~

If the project intentionally packages profile configs, verify they contain no secrets and that production cannot accidentally activate the dev profile. Another option is packaging only default config and keeping all environment-specific files completely outside the JAR.

After building, compute the checksum:

Linux/macOS:

~~~bash
sha256sum target/orders-service-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\orders-service-1.0.0.jar -Algorithm SHA256
~~~

Record the checksum in build artifact metadata or release notes. After copying/downloading to a server, recompute the checksum and compare. If checksums differ, the file on the server is not byte-for-byte identical to the built artifact.

A version label like `1.0.0` helps humans identify a release, whereas a checksum/digest cryptographically verifies exact contents. In artifact repositories, prefer immutable versions or digests per release policy.

## 28. Verifying Both Environments Truly Run the Same Code

A release workflow might look like:

1. CI builds the JAR from a commit SHA.
2. CI runs tests.
3. CI computes the checksum and publishes the artifact.
4. Dev deployment pulls the artifact by version/digest.
5. Dev smoke tests run.
6. Production deployment promotes the exact tested artifact.
7. Record the artifact digest and runtime configuration version.

Do not rebuild at the production stage when the goal is promoting the same artifact. Only swap configs/secrets and deployment parameters.

The JAR is promoted untouched, whereas external configs vary by environment and follow their own versioning and review process. Record which configuration version accompanied each release so issues can be traced and rolled back.

## 29. Testing Dev and Production Configurations

Write tests for critical invariants of each profile.

~~~java
@SpringBootTest
@ActiveProfiles("dev")
class DevConfigurationTests {

    @Autowired
    PartnerProperties properties;

    @Test
    void usesDevPartnerEndpoint() {
        assertThat(properties.baseUrl().getHost())
                .isEqualTo("partner-dev.example.test");
    }
}
~~~

This test assumes the dev profile is loaded from the test classpath. It does not prove external config on a deployment host will be located properly.

You can write configuration validation tests checking production endpoints, database URLs, test-only flags, timeout/pool settings, and log levels. Never put real production passwords into tests; use placeholders/synthetic values and test format/required constraints.

Some test frameworks support injecting system properties or dynamic properties in tests. Set test values explicitly instead of relying on a developer's local machine environment so tests remain reproducible on CI.

## 30. Smoke Testing the JAR with External Configuration

After deploying to a test directory:

~~~bash
cd deploy/dev
java -jar orders-service.jar \
  --spring.profiles.active=dev
~~~

Verify the process starts cleanly, the right profile is active, database connectivity works, partner endpoints match, server port is right, health endpoint responds, logging behaves as expected, and graceful shutdown works.

If the application exposes health via Actuator:

~~~bash
curl http://localhost:8080/actuator/health
~~~

Not every application exposes this endpoint. Enable the dependency and exposure intentionally first.

A successful health response only confirms a subset of status. It does not prove all business logic, database migrations, authorization, performance, or resilience work properly.

### Graceful Shutdown

When run from a terminal or service manager, the Java process receives stop signals from the environment. Spring Boot can close the `ApplicationContext` and run lifecycle callbacks.

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Wait times must align with process manager / orchestrator timeouts. Use `exec java -jar ...` in shell scripts so the Java process replaces the shell process and receives signals directly.

## 31. Troubleshooting: Spring Does Not Read the External File

Symptom: you edited `config/application.yml`, yet the application still uses values from inside the JAR.

Check in order:

1. What is the process's working directory?
2. Is the file located at `./config/application.yml` relative to that working directory?
3. Does the file have a valid name and supported extension?
4. Is the YAML syntax and indentation valid?
5. Does the user running the app have read permission on the file?
6. Is `spring.config.location` replacing default locations?
7. Is it a profile-specific file whose profile is not active?
8. Is a higher-precedence source overriding the property?
9. Was the config import/location marked optional and skipped?
10. Do startup logs show any Config Data loading failures?

You can test with an explicit location:

~~~bash
java -jar orders-service.jar \
  --spring.config.additional-location=file:./config/
~~~

If it still does not load, use an OS-appropriate absolute `file:` URI and double-check the working directory.

## 32. Troubleshooting: Wrong Profile or Unresolved Placeholder

If the application runs with dev configuration during a production deployment, check `SPRING_PROFILES_ACTIVE`, command-line `--spring.profiles.active`, system properties, deployment manifests/service units, default profiles, and the `application-prod.yml` filename.

Command-line arguments override environment variables. A local launch script might pass `--spring.profiles.active=dev` even if the production service sets `SPRING_PROFILES_ACTIVE=prod`. Inspect the **actual command** executed by the process manager.

If you encounter:

~~~text
Could not resolve placeholder 'DB_PASSWORD'
~~~

common causes include the environment variable not being passed to the process, a misspelled variable name, a service manager not inheriting shell environment variables, an unmounted secret file, or a missing config import.

You can check existence without printing the secret value:

PowerShell:

~~~powershell
[bool]$env:DB_PASSWORD
~~~

Linux/macOS:

~~~bash
test -n "$DB_PASSWORD" && echo "DB_PASSWORD is set"
~~~

Never paste passwords into tickets or logs.

## 33. Troubleshooting: Overridden Properties or JAR Behaves Differently from IDE

If external config sets port 8081 yet the app listens on 8083, a higher-precedence source may set `SERVER_PORT` or `--server.port=8083`. Check command-line args, environment variables, JVM system properties, service units, profile-specific configs, and external config imports/locations.

IDEs may launch with different working directories, environment variables, active profiles, classpaths/resource paths, JDKs, or VM options. When running the JAR, verify the JDK/runtime, Boot executable JAR, external config location, environment variables, runtime dependencies, filesystem permissions, ports, and network access.

Do not assume Spring Boot misbehaves when packaged before comparing the two execution environments.

## 34. Troubleshooting: Build Succeeds Without Running Tests

This is a build/test tooling issue rather than external config. When building a JAR for release, still verify tests were discovered and executed:

~~~bash
mvn clean verify
~~~

or:

~~~bash
./gradlew clean test bootJar
~~~

Never pass `-DskipTests` or `-x test` in release builds unless the pipeline executes tests in a separate dedicated stage with corresponding verification evidence.

Check test reports and test counts. A green build with zero executed tests does not prove the application was tested.

## 35. Complete Practice Checklist

### Before Building

- [ ] Select compatible Spring Boot and Java versions.
- [ ] Verify the Maven/Gradle wrapper.
- [ ] Ensure the Boot plugin builds an executable JAR.
- [ ] Decide which default config belongs packaged inside the JAR.
- [ ] Decide which properties must come from external config.
- [ ] Decide which secrets must come from a secret manager/environment.
- [ ] Include tests for configuration properties and validation.

### During Artifact Build

- [ ] Run a clean build and tests.
- [ ] Produce the executable JAR.
- [ ] Verify artifact path and name.
- [ ] Inspect JAR contents if needed.
- [ ] Compute the checksum/digest.
- [ ] Publish the artifact under an immutable version.

### When Deploying to Dev

- [ ] Copy/pull the right JAR digest.
- [ ] Place external config in the expected location.
- [ ] Supply `DB_PASSWORD` and required dev secrets.
- [ ] Explicitly select the `dev` profile.
- [ ] Verify the working directory.
- [ ] Start the app and check health/logs/database/partner connectivity.

### When Deploying to Production

- [ ] Promote the exact tested artifact.
- [ ] Do not rebuild the JAR for the production profile.
- [ ] Place external production config.
- [ ] Supply secrets via protected mechanisms.
- [ ] Explicitly select the `prod` profile.
- [ ] Verify endpoints do not point to dev/sandbox.
- [ ] Verify pool sizes, timeouts, and resource limits.
- [ ] Verify health/readiness and graceful shutdown.
- [ ] Record the artifact digest and config release/version.

### Post-Deployment

- [ ] Confirm the process runs the intended version.
- [ ] Verify logs contain no secrets.
- [ ] Verify database and partner connections.
- [ ] Verify health and critical use cases.
- [ ] Monitor startup errors, latency, and resource usage.
- [ ] Retain the previous artifact/config version for controlled rollback.

## 36. Practice Exercises

### Exercise 1: Build an Executable JAR

Create a simple Spring Boot application with an endpoint:

~~~java
@RestController
public class EnvironmentController {

    private final Environment environment;

    public EnvironmentController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/environment")
    public Map<String, Object> environment() {
        return Map.of(
                "application", environment.getProperty(
                        "spring.application.name"
                ),
                "activeProfiles", Arrays.asList(
                        environment.getActiveProfiles()
                )
        );
    }
}
~~~

Build with Maven or Gradle and run with `java -jar`.

### Exercise 2: Add Default Configuration

In `application.yml`, configure the application name and default port. Confirm the endpoint returns that name.

### Exercise 3: Create External Dev Config

Create `config/application-dev.yml` and set a property such as `app.environment-name: development`. Run:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

Verify the property is bound properly.

### Exercise 4: Create External Prod Config

Create `config/application-prod.yml` with `app.environment-name: production`. Run the exact same JAR with the `prod` profile.

### Exercise 5: Override with Environment Variables

Set `APP_ENVIRONMENT_NAME=staging`. Confirm the environment variable takes precedence over the config file in a standard setup.

### Exercise 6: Override via Command Line

~~~bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --app.environment-name=command-line
~~~

Confirm the command-line value overrides lower-precedence sources.

### Exercise 7: Test `additional-location`

Place config in `./external-config/` and launch with:

~~~bash
--spring.config.additional-location=file:./external-config/
~~~

Verify Spring loads the external files.

### Exercise 8: Intentionally Omit a Required Variable

Unset `DB_PASSWORD` from the environment and start the app. Observe the placeholder/binding error. Restore the test secret and confirm the context boots.

### Exercise 9: Prove Identical Artifacts

Compute SHA-256 checksums of the JAR in the dev and prod directories. Both checksums must match if it is byte-for-byte the same artifact.

### Exercise 10: Test Rollback

Keep the previous release JAR and its matching external config version. Practice restoring the artifact/config in a test environment and verify the application restarts cleanly.

## Conclusion

Packaging an executable JAR once and running it with external configuration across two environments is a clean, controllable Spring Boot deployment pattern. Maven or Gradle builds one JAR; Spring Boot reads packaged classpath defaults and layers external Config Data, profile-specific files, environment variables, system properties, and command-line arguments according to precedence.

For dev and production, you can place the exact same JAR into two deployment directories, each with its own external `config/` and profile. Launch with `--spring.profiles.active=dev` or `prod`, supply secrets through environment-appropriate security mechanisms, and verify the process runs from the expected working directory. If config resides outside default search paths, use `spring.config.additional-location` to add locations; only use `spring.config.location` when you intentionally want to replace default search locations.

The core principle throughout is that **artifacts and runtime configuration have separate lifecycles**: build and test the JAR once, promote that exact artifact across environments, manage config and secrets per environment, and smoke-test real behavior. Doing so avoids build drift, keeps releases traceable, and lets you adjust endpoints, databases, logging, or timeouts without recompiling the application.

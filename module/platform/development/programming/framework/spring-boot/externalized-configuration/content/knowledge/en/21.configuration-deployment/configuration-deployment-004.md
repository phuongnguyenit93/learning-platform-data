# Different Working Directories and Configuration Lookup Errors When Deploying Spring Boot

## 1. Real-World Scenario: Same JAR, Works Here, Fails Elsewhere

A Spring Boot application may run fine in an IDE or a developer's terminal, yet when moved to a Linux server, Windows Service, Docker, or Kubernetes:

- It cannot find `application-prod.yml` that sits right next to the JAR file.
- It starts up but gets an old database URL, timeout, or profile from the packaged configuration.
- It throws `ConfigDataLocationNotFoundException` on a relative path.
- Adding `--spring.config.additional-location=file:./config/` still does not find the desired file.
- Running the exact same `java -jar /opt/catalog/catalog.jar` command gives different results across two current directories.
- A run via `systemd` or a container fails to read a volume mount, even though it works when invoked from an interactive shell.
- The file is read, yet a property is overridden by a higher-precedence environment variable or command-line argument.

The cause usually is not in the YAML content itself. Many bugs stem from confusing the **directory containing the JAR**, the **process working directory**, **classpath paths**, **absolute filesystem paths**, and **configuration source precedence order**.

> **Key principle:** `file:./...` paths are resolved relative to the current working directory of the Java process. They do not automatically use the directory containing the `.jar` as their root. Configuration inside the JAR with `classpath:` follows classpath resolution, independent of the filesystem's `./config` path.

This lesson targets Spring Boot 3.x with the **Config Data** mechanism introduced in Spring Boot 2.4+. Core rules also appear in newer versions, but always check the reference documentation for the deployed version before using newer options.

## 2. Distinguishing Four Commonly Confused Locations

Imagine a layout on Linux:

~~~text
/opt/catalog/
├── catalog.jar
├── start.sh
└── config/
    └── application-prod.yml

/etc/catalog/
└── application.yml

/var/log/catalog/
└── ...
~~~

There are four independent concepts.

### 2.1. Directory containing the JAR file

In the example, this is `/opt/catalog`. The file `catalog.jar` resides in this directory, but the executable's location **does not automatically determine** the root for all `file:./...` paths.

### 2.2. Working directory or current directory

This is the **current working directory of the process** at execution time. It is usually inherited from the shell, service manager, or container runtime.

Example:

~~~bash
cd /opt/catalog
java -jar catalog.jar
~~~

The working directory is typically `/opt/catalog`.

However:

~~~bash
cd /tmp
java -jar /opt/catalog/catalog.jar
~~~

The working directory is `/tmp`, **not** `/opt/catalog`. Same JAR file, yet `./config/` points to two different locations.

### 2.3. Classpath

The file `src/main/resources/application.yml` is typically packaged in the JAR and found at the classpath root. Resources such as `classpath:/application.yml` and `classpath:/config/application.yml` are not resolved like `file:./...`.

A file `/etc/catalog/application.yml` on the filesystem **does not automatically become a classpath resource** merely because it has the same name. An appropriate external configuration mechanism must be used.

### 2.4. Absolute filesystem path

The path `/etc/catalog/application.yml` points to a fixed location on the runtime environment's filesystem. To point Spring Boot to it:

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/application.yml
~~~

This avoids depending on the current directory, though it still depends on the file existing and the process account having read permission.

## 3. Where Does Spring Boot Look for `application.properties`/`application.yaml` by Default?

Under Config Data, Spring Boot checks the following basic location groups by default, from lower to higher precedence:

| General order | Location | Depends on working directory? |
| --- | --- | --- |
| 1 | `classpath:/` | No |
| 2 | `classpath:/config/` | No |
| 3 | `file:./` | **Yes** |
| 4 | `file:./config/` | **Yes** |
| 5 | `file:./config/*/` | **Yes** |

Entries are ordered by precedence rules; configuration from a higher-precedence location can override same-named properties from a lower-precedence location.

Specifically:

- `classpath:/` typically holds `application.yml` packaged inside the JAR.
- `classpath:/config/` is the `config` directory inside the classpath.
- `file:./` points to the **working directory of the Java process**.
- `file:./config/` points to the `config` subdirectory of the working directory.
- `file:./config/*/` expands to direct subdirectories inside `./config` on the filesystem.

Therefore, when the shell is in `/tmp`, default external files are searched in:

~~~text
/tmp/application.yml
/tmp/config/application.yml
/tmp/config/<subdirectory>/application.yml
~~~

not automatically in `/opt/catalog/config/application.yml` just because the JAR sits in `/opt/catalog`.

### 3.1. Default filenames

Without customization, the basename is `application`. Spring Boot supports Java Properties and YAML formats by their corresponding extensions, for example:

~~~text
application.properties
application.yml
application.yaml
application-prod.properties
application-prod.yml
application-prod.yaml
~~~

Profile-specific files like `application-prod.yml` are considered when the `prod` profile is active.

Do not assume Spring Boot will automatically search for a file named `catalog-config.yml` anywhere. To use a different basename, set `spring.config.name`, or specify a concrete file location.

### 3.2. Defaults do not always raise an error when a file is missing

Spring Boot can start normally without an external `./config/application.yml` file, because default locations are not required to contain files. Configuration from the JAR, environment, system properties, or application defaults may still allow the context to start.

This is why a working-directory mistake may **not surface as an exception**: the application runs, yet uses unintended values.

## 4. Reproducing: Same JAR, Different Working Directory

Suppose the JAR has an internal file:

~~~yaml
# application.yml packaged inside catalog.jar
app:
  region: dev
  mode: sandbox
~~~

On the server there is external config:

~~~text
/opt/catalog/config/application.yml
~~~

Contents:

~~~yaml
app:
  region: apac
  mode: production
~~~

An observer bean:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class StartupInfo {

    @Bean
    ApplicationRunner printConfig(Environment environment) {
        return args -> {
            System.out.println("cwd=" + System.getProperty("user.dir"));
            System.out.println("app.region="
                    + environment.getProperty("app.region"));
            System.out.println("app.mode="
                    + environment.getProperty("app.mode"));
        };
    }
}
~~~

### Run A — inside the application directory

~~~bash
cd /opt/catalog
java -jar catalog.jar
~~~

The working directory is `/opt/catalog`. Spring Boot can find `/opt/catalog/config/application.yml` via `file:./config/`.

Illustrative output, assuming no higher-precedence source overrides it:

~~~text
cwd=/opt/catalog
app.region=apac
app.mode=production
~~~

### Run B — in another directory

~~~bash
cd /tmp
java -jar /opt/catalog/catalog.jar
~~~

Now `file:./config/` is `/tmp/config/`. Without config there, values packaged inside the JAR may be used:

~~~text
cwd=/tmp
app.region=dev
app.mode=sandbox
~~~

**Same JAR file, same source code, same external file.** Only the **working directory** changed, so the effective configuration sources differed.

### 4.1. Java `user.dir` and OS inspection

In a Java application, you can use:

~~~java
String currentDirectory = System.getProperty("user.dir");
~~~

Or:

~~~java
import java.nio.file.Path;

Path cwd = Path.of("").toAbsolutePath().normalize();
System.out.println("cwd=" + cwd);
~~~

This information is for **diagnostics**, and should not be used as the sole basis for security path policies. Nor does it make Spring Boot change its config paths on its own.

In a Unix terminal:

~~~bash
pwd
pwd -P
~~~

`pwd -P` shows the physical path when the shell is inside a path with symbolic links. For symlinks and filesystem mounts, inspect both the path name the process uses and the target location.

In PowerShell:

~~~powershell
Get-Location
~~~

A Java process launched by a service manager does not automatically use the working directory of the **shell you are logged into**; you must inspect the configuration of the service or process itself.

## 5. Why Does the IDE Work While Production Fails?

An IDE such as IntelliJ IDEA, Eclipse, or VS Code typically has a **Working directory** setting in its run/debug configuration. The IDE may default the working directory to the project root, module root, or a user-configured path.

Suppose the source tree is:

~~~text
catalog-service/
├── pom.xml
├── config/
│   └── application-local.yml
├── src/
│   └── main/
│       └── resources/
│           └── application.yml
└── target/
    └── catalog.jar
~~~

If the IDE uses `catalog-service/` as the working directory, `file:./config/` points to `catalog-service/config`. But when deploying the JAR to `/srv/catalog/` and starting the service from `/`, Spring Boot searches `/config/` instead of `/srv/catalog/config`.

Typical differences:

| Environment | Typical or configurable working directory | `file:./config/` points to |
| --- | --- | --- |
| IDE at project root | `.../catalog-service` | `.../catalog-service/config` |
| Shell after `cd /srv/catalog` | `/srv/catalog` | `/srv/catalog/config` |
| Shell in `/tmp` running absolute JAR | `/tmp` | `/tmp/config` |
| systemd | Per unit's `WorkingDirectory=`, if set | Corresponding path |
| Docker | Per `WORKDIR` in image or runtime override | `<container-cwd>/config` |
| Kubernetes | Per container `workingDir` or image/runtime default | `<container-cwd>/config` |
| Windows Service | Depends on service wrapper and startup config | Do not guess |

The solution is to **explicitly specify the working directory or config location** for each deployment, rather than relying on incidental IDE behavior.

## 6. `spring.config.location`: Specifying Where to Find Config and Replacing Defaults

When configuration resides in a specific location, you can provide:

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.config.location=file:/etc/catalog/
~~~

For a **directory location**, end the path with `/`. Spring Boot uses filenames formed from `spring.config.name` and considers profile-specific variants when applicable.

You can specify a single file:

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.config.location=file:/etc/catalog/application.yml
~~~

In that case, this is a **file location**, not a directory. The file is loaded directly; profile-specific variants can also be considered per Config Data rules.

### 6.1. Critical point: `location` replaces the default location list

Setting:

~~~properties
spring.config.location=file:/etc/catalog/
~~~

tells Spring Boot to use the specified locations **instead of the default search locations**, rather than simply appending `/etc/catalog/` to the end.

Consequence: if the application previously relied on `classpath:/application.yml` for defaults, setting `spring.config.location` without a classpath location can cause those defaults **not to be loaded through the default search path anymore**.

If you want to use both classpath and external sources, configure the appropriate locations or choose `spring.config.additional-location`.

Example intentionally declaring both:

~~~bash
java -jar /opt/catalog/catalog.jar \
  '--spring.config.location=classpath:/,file:/etc/catalog/'
~~~

In this example, the later location can override same-named properties from the earlier location. With profile-specific files and multiple location groups, exact ordering is also subject to grouping rules.

### 6.2. Do not put `spring.config.location` inside the file it is meant to find

To decide which files to load, Spring Boot must know `spring.config.location` **very early**.

Therefore, the following usually does not solve the problem:

~~~yaml
# application.yml expected to point to another file itself
spring:
  config:
    location: file:/etc/catalog/
~~~

The `spring.config.location` value used to locate config data must be supplied via a source **available prior to that phase**, such as OS environment, JVM system property, or command-line argument.

Example:

~~~bash
SPRING_CONFIG_LOCATION=file:/etc/catalog/ java -jar catalog.jar
~~~

or:

~~~bash
java -Dspring.config.location=file:/etc/catalog/ -jar catalog.jar
~~~

Setting it too late will not make Spring Boot go back and rescan all skipped files.

## 7. `spring.config.additional-location`: Adding Beyond Defaults

Most applications want to keep packaged default configuration in the JAR while letting a deployment override a few keys. In that case, use:

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/
~~~

Under Config Data, `additional-location` **extends** the default locations rather than replacing them. Properties from additional locations can override matching keys in default config data.

Example JAR:

~~~yaml
# src/main/resources/application.yml
app:
  endpoint: https://sandbox.example.test
  connect-timeout: 3s
  retries: 2
~~~

External file:

~~~yaml
# /etc/catalog/application.yml
app:
  endpoint: https://api.example.test
  connect-timeout: 8s
~~~

When run with `additional-location` and no higher-precedence source:

~~~text
app.endpoint        = https://api.example.test
app.connect-timeout = 8s
app.retries         = 2
~~~

`retries` is still taken from the JAR because the external config did not declare that key. Spring Boot resolves **property by property**, rather than letting "one file win completely."

### 7.1. Brief comparison

| Property | How locations are handled | When appropriate |
| --- | --- | --- |
| `spring.config.location` | **Replaces** default search locations | Want full control over the Config Data source set |
| `spring.config.additional-location` | **Adds** locations to defaults | Keep defaults in JAR and add per-deployment files |
| `spring.config.name` | Changes basename from `application` | Use a name like `catalog` instead of `application` |
| `spring.config.import` | Imports locations from a Config Data document being loaded | Split configuration, import files/secrets/config trees |

Properties controlling file discovery must be present early enough for Config Data processing to use them.

## 8. `optional:`: Is a Missing File an Error or Allowed to Be Skipped?

When an **explicit** location does not exist, Spring Boot by default can throw:

~~~text
ConfigDataLocationNotFoundException
~~~

Example:

~~~bash
java -jar catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/missing.yml
~~~

If the deployment strictly requires that file, fail-fast behavior is helpful: the application will not silently run with unsuitable defaults.

If the file is optional, prepend `optional:`:

~~~bash
java -jar catalog.jar \
  --spring.config.additional-location=optional:file:/etc/catalog/optional.yml
~~~

Or with a directory:

~~~bash
java -jar catalog.jar \
  --spring.config.additional-location=optional:file:/etc/catalog/
~~~

Distinguish:

- `optional:` allows a **missing location** without triggering a location-not-found error.
- `optional:` does **not** ignore malformed YAML syntax, conversion errors, permission errors, or invalid business configuration.
- `optional:` does not verify whether the file contains required keys.
- If the file is not found, the application may continue using other configuration or fail due to a missing required property.

### 8.1. Why can `optional:` be dangerous in production?

A service needs credentials from `/etc/catalog/secret.yml` but is deployed with a wrong path. If configured as:

~~~bash
--spring.config.additional-location=optional:file:/etc/catalog/secret.yml
~~~

the missing-location error may be skipped and the application runs with unintended settings, or fails late when calling a dependency.

For **truly required** sources, do not use `optional:` as a trick to "make the app start anyway." Keep the location required and validate critical properties at startup.

To ignore *all* location-not-found exceptions, Spring Boot offers `spring.config.on-not-found=ignore`, but this is a very broad setting; use it only when you fully understand the missing-file policy.

## 9. `file:`, `classpath:`, and Import-Relative: Three Ways to Resolve Paths

### 9.1. `classpath:` searches resources on the classpath

~~~properties
spring.config.import=optional:classpath:/features.yml
~~~

`features.yml` must be a resource on the classpath, such as in `src/main/resources` to be packaged. It does not automatically search `/etc/catalog/features.yml` outside the JAR.

### 9.2. `file:` searches the filesystem

~~~properties
spring.config.import=optional:file:/etc/catalog/features.yml
~~~

This is a fixed location on the runtime environment's Linux filesystem.

~~~properties
spring.config.import=optional:file:./features.yml
~~~

This form depends on the **working directory**.

### 9.3. Import-relative differs from `file:./...`

A subtle point: in `spring.config.import`, a path **without a location prefix** and not starting with `/` can be treated as **import-relative**, meaning relative to the document declaring `spring.config.import`.

Example:

~~~text
/etc/catalog/
├── application.yml
└── fragments/
    └── database.yml
~~~

If `/etc/catalog/application.yml` contains:

~~~yaml
spring:
  config:
    import: optional:fragments/database.yml
~~~

then the import location can be resolved relative to `application.yml` at `/etc/catalog`, i.e., `/etc/catalog/fragments/database.yml`.

By contrast, configuring:

~~~yaml
spring:
  config:
    import: optional:file:./fragments/database.yml
~~~

is a location with the `file:` prefix and `./`; it is a filesystem path relative to the working directory, **not having the same import-relative semantics**.

This is a common source of errors when a file is moved from the project root to `/etc/catalog` and the deployer keeps `file:./...` thinking it is always relative to the YAML file's location.

## 10. Resolving Paths Correctly When Using `spring.config.import`

Suppose files on disk are:

~~~text
/etc/catalog/
├── application.yml
└── components/
    └── kafka.yml
~~~

In `application.yml`:

~~~yaml
spring:
  config:
    import: optional:components/kafka.yml
~~~

This expresses: "import the adjacent file in the `components` subdirectory," following import-relative rules.

If you want it absolute:

~~~yaml
spring:
  config:
    import: optional:file:/etc/catalog/components/kafka.yml
~~~

Both can point to the same file in the current deployment, with trade-offs:

- Import-relative is convenient when relocating **the entire config folder** elsewhere.
- Absolute filesystem paths are convenient when the environment mandates a fixed path.
- `file:./...` is convenient when the working directory is controlled, but very error-prone if startup is triggered from multiple places.

### 10.1. Files without an extension

Kubernetes and some secret-mount mechanisms can create files without extensions:

~~~text
/etc/catalog/keys/token
~~~

When you need to import a file as YAML without a suffix, Spring Boot provides an **extension hint**:

~~~properties
spring.config.import=optional:file:/etc/catalog/keys/token[.yaml]
~~~

Do not assume an extensionless path is automatically YAML. And if the directory contains multiple key/value files rather than a single YAML document, you likely need `configtree:` rather than an extension hint.

## 11. Default Wildcard `file:./config/*/` and the "Recursive Scan" Misconception

With modern Config Data, Spring Boot can look for configuration files in immediate subdirectories of `./config`.

For example, when the working directory is `/srv/catalog`:

~~~text
/srv/catalog/
└── config/
    ├── database/
    │   └── application.yml
    ├── messaging/
    │   └── application.yml
    └── cache/
        └── application.yml
~~~

The default location `file:./config/*/` can inspect:

~~~text
./config/database/
./config/messaging/
./config/cache/
~~~

However, `*` in this location form **does not mean infinite recursive scanning** across all directory levels. Spring Boot wildcard locations normally expand **one subdirectory level** per supported syntax.

Several rules:

- Wildcards are only supported for **external filesystem locations**, not with `classpath:`.
- A wildcard location has a single `*` in a supported position.
- For directory locations, the pattern has the form `*/`.
- For file locations, it can have the form `*/<filename>`.
- Wildcard matches are processed in a deterministic order, typically alphabetical sorting of absolute paths.

If you have:

~~~text
config/region/eu/application.yml
~~~

do not assume `file:./config/*/` scans down to `region/eu`. When deeper nesting is needed, specify appropriate locations or adjust the mount layout.

### 11.1. Wildcards only help if the working directory is right

When the working directory changes from `/srv/catalog` to `/`, `file:./config/*/` becomes `/config/*/`. Even though wildcard logic works properly, it can scan the **wrong directory tree**.

That is a path error before it is a YAML error.

## 12. Profiles: Right Directory, Wrong Profile File

Another error with symptoms very similar to a working-directory bug: `application-prod.yml` exists in a searched location, yet the `prod` profile is not enabled.

Example:

~~~text
/etc/catalog/
├── application.yml
└── application-prod.yml
~~~

If the application runs with:

~~~bash
java -jar catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/
~~~

without activating `prod`, do not expect properties in `application-prod.yml` to apply.

Enable the profile via CLI:

~~~bash
java -jar catalog.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/catalog/
~~~

Or environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=prod \
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/catalog/ \
java -jar catalog.jar
~~~

When the `prod` profile is active, Spring Boot considers `application-prod.yml`/`.properties` files in the relevant locations.

### 12.1. File paths and profile-specific variants

When specifying a file location such as:

~~~bash
--spring.config.location=file:/etc/catalog/application.yml
~~~

Spring Boot can still consider matching profile-specific variants, according to Config Data rules.

Do not invent a rule that "specifying an exact file definitely skips profile variants." What matters is knowing the location set, active profiles, and which source has higher precedence.

### 12.2. Multiple profiles and precedence

With `prod,live`, profile-specific documents follow a **last-wins** rule at the location group level. When combining multiple locations and groups, ordering can be hard to see by eye.

When diagnosing "the file loaded yet the value is still different," check:

1. Which profiles are actually activated.
2. Whether a same-named file exists in a higher-precedence location.
3. Whether an environment variable/JVM system property/CLI overrides the key.
4. Whether location groups are separated by `,` or `;`.
5. Whether the property itself is declared in multiple YAML documents with profile conditions.

## 13. Multiple Locations: Commas and Location Groups

`spring.config.location` and `spring.config.additional-location` can accept multiple locations.

Example:

~~~bash
java -jar catalog.jar \
  '--spring.config.additional-location=file:/etc/catalog/base/,file:/etc/catalog/override/'
~~~

Normally, later locations can override matching keys from earlier locations.

When handling multiple profiles, Spring Boot has the concept of a **location group**. Items within the same group are separated by `;` rather than `,`.

Illustrative example:

~~~text
file:/etc/catalog/a/;file:/etc/catalog/b/
~~~

Differs from:

~~~text
file:/etc/catalog/a/,file:/etc/catalog/b/
~~~

The difference is how locations are grouped at the same level when Spring Boot applies profile document ordering. It can affect the final value when both locations contain `application-prod.yml` and `application-live.yml`.

In a shell, `;` has special meaning in certain contexts, so **quote the entire argument** containing groups:

~~~bash
java -jar catalog.jar \
  '--spring.config.additional-location=file:/etc/catalog/a/;file:/etc/catalog/b/'
~~~

If you only need one external directory, **do not complicate it with multiple location groups**. Use one clear directory, and add more only when truly required.

## 14. Linux `systemd`: Which Working Directory Does the Service Run With?

When you SSH in yourself and run:

~~~bash
cd /opt/catalog
java -jar catalog.jar
~~~

the working directory is `/opt/catalog`.

However, a `systemd` service is usually launched by the service manager according to unit configuration, **without inheriting the directory you just `cd`-ed into in a shell**.

An illustrative unit:

~~~ini
# /etc/systemd/system/catalog.service
[Unit]
Description=Catalog Spring Boot Service
After=network.target

[Service]
Type=simple
User=catalog
Group=catalog
WorkingDirectory=/opt/catalog
ExecStart=/usr/bin/java -jar /opt/catalog/catalog.jar
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

`WorkingDirectory=/opt/catalog` causes `file:./config/` to resolve to `/opt/catalog/config/`.

If you want to separate runtime config from the JAR directory, you can use:

~~~ini
[Service]
Type=simple
User=catalog
Group=catalog
WorkingDirectory=/opt/catalog
Environment=SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/catalog/
ExecStart=/usr/bin/java -jar /opt/catalog/catalog.jar
~~~

Then the application both keeps classpath defaults and reads config from `/etc/catalog/` without depending on config files being copied next to the JAR.

### 14.1. Diagnosing the actual unit

On a Linux machine:

~~~bash
systemctl cat catalog.service
systemctl show catalog.service -p WorkingDirectory -p Environment
journalctl -u catalog.service -b --no-pager
~~~

These commands help verify the actually applied unit, working directory, and startup logs. Do not put secrets directly into shared output or logs; `Environment=...` variables may expose sensitive data if deployment design is poor.

After editing a unit file, you typically need:

~~~bash
sudo systemctl daemon-reload
sudo systemctl restart catalog.service
~~~

These example commands are for an environment you administer, not mandatory steps just to understand the bug. When modifying a production service, follow change management and rollback procedures.

### 14.2. Read permissions matter too

A file existing at `/etc/catalog/application.yml` that the `catalog` user lacks permission to read can cause startup to fail or prevent proper configuration loading.

Check:

~~~bash
ls -ld /etc/catalog
ls -l /etc/catalog/application.yml
~~~

For nested directories, the process needs traverse permission on parent directories and read permission on the file. Do not fix it with `chmod 777` or by making secrets world-readable. Choose appropriate owner/group, ACLs, or mount permissions.

## 15. Docker: `WORKDIR`, Mounts, and Paths Inside the Container

Suppose the Dockerfile is:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/catalog.jar /app/catalog.jar
ENTRYPOINT ["java", "-jar", "/app/catalog.jar"]
~~~

With `WORKDIR /app`, Spring Boot's default relative locations like `file:./config/` point to `/app/config/` **inside the container**.

Run:

~~~bash
docker run --rm \
  --mount type=bind,source=/srv/catalog/config,target=/app/config,readonly \
  catalog:latest
~~~

If the host has:

~~~text
/srv/catalog/config/application.yml
~~~

then the container can read the file under:

~~~text
/app/config/application.yml
~~~

and Spring Boot can find it via default `file:./config/`.

### 15.1. Same image, different working directory

The container runtime can override the working directory:

~~~bash
docker run --rm -w /tmp catalog:latest
~~~

Now default `file:./config/` corresponds to `/tmp/config/` inside the container, not `/app/config/`. Even though the JAR is still at `/app/catalog.jar`, external config under `/app/config` is no longer found via the relative default path.

Fixes:

- Keep `WORKDIR /app` and do not override it arbitrarily.
- Or specify an absolute external location:

~~~bash
docker run --rm \
  -w /tmp \
  -e SPRING_CONFIG_ADDITIONAL_LOCATION=file:/app/config/ \
  --mount type=bind,source=/srv/catalog/config,target=/app/config,readonly \
  catalog:latest
~~~

`/app/config/` is a path **inside the container**, not a path on the host.

### 15.2. Inspecting from inside the container

While the container is running, you can inspect:

~~~bash
docker exec catalog sh -c 'pwd; ls -la /app/config'
~~~

This verifies three independent things:

1. The container's current directory.
2. Whether the mount is at the right container path.
3. Whether the user running Java can see the files.

A bind mount with the wrong source, wrong target, or wrong file permissions can exhibit symptoms identical to a `spring.config.location` error. Do not troubleshoot merely by renaming files without verifying the mount topology.

## 16. Docker Compose: Use Fixed Paths Instead of Hoping for a Specific CWD

Example Compose:

~~~yaml
services:
  catalog:
    image: catalog:latest
    working_dir: /app
    volumes:
      - ./config:/etc/catalog:ro
    environment:
      SPRING_PROFILES_ACTIVE: prod
      SPRING_CONFIG_ADDITIONAL_LOCATION: file:/etc/catalog/
~~~

Here there are **two different kinds of relative paths**:

- `./config` on the host side in Compose config is the source volume path, resolved by Compose relative to the project/Compose file context.
- `file:/etc/catalog/` is an absolute path **inside the container**, used by Spring Boot to load config.

Do not conflate them. Changing the Java process's working directory inside the container does not change the absolute mount target `/etc/catalog`.

With layout:

~~~text
project/
├── compose.yaml
└── config/
    ├── application.yml
    └── application-prod.yml
~~~

the service will find both files in `/etc/catalog` when the volume is mounted properly.

If using mounts that contain credentials, do not put plaintext secrets in the repository; use an environment-appropriate secret/config mechanism.

### 16.1. Health check note

A container starting successfully does not prove it loaded the right external config. If the fallback inside the JAR is valid, the service may start up yet connect to the wrong environment.

Add readiness checks against actual dependencies, and inspect a **non-sensitive environment identifier** or require a mandatory property representing the deployment.

## 17. Kubernetes: `workingDir`, ConfigMap, and Secret Mounts

In Kubernetes, containers run in their own filesystem. Local paths on a build machine or node do not appear in a pod without an explicit volume mount.

Example ConfigMap containing `application.yml`:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-config
data:
  application.yml: |
    app:
      region: apac
      endpoint: https://api.example.test
~~~

Deployment container (illustrative excerpt):

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
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
        - name: catalog
          image: catalog:latest
          workingDir: /app
          env:
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: "file:/etc/catalog/"
          volumeMounts:
            - name: catalog-config
              mountPath: /etc/catalog
              readOnly: true
      volumes:
        - name: catalog-config
          configMap:
            name: catalog-config
~~~

Here Spring Boot loads from `/etc/catalog/`, independent of `workingDir: /app`. The Kubernetes ConfigMap mount exposes `/etc/catalog/application.yml` inside the container.

A pod with `workingDir: /app` and **without** `SPRING_CONFIG_ADDITIONAL_LOCATION` can still find config if mounted at `/app/config/application.yml`, whereas a `/etc/catalog` mount will not be scanned automatically by default `file:./config/`.

### 17.1. Distinguishing YAML files from configuration trees

If a volume contains:

~~~text
/etc/catalog/secrets/
├── db.username
└── db.password
~~~

each file containing a single value, this is not a normal `application.yml` file.

You can use a config tree import:

~~~properties
spring.config.import=optional:configtree:/etc/catalog/secrets/
~~~

Then filenames `db.username` and `db.password` can become property names under config tree rules. This differs from:

~~~properties
spring.config.additional-location=file:/etc/catalog/secrets/
~~~

which looks for files with Config Data names/formats like `application.properties` or `application.yml` inside the directory.

**Choose the right source type:** for a complete YAML file use a file/directory location; for multiple key/value files consider `configtree:`.

### 17.2. Read permissions and ConfigMap updates

A Pod may mount a ConfigMap/Secret yet the container user can still hit filesystem permission limits depending on `securityContext`, `defaultMode`, groups, and security policies.

Furthermore, updating a ConfigMap volume **does not guarantee** `@ConfigurationProperties` beans rebind immediately. Spring Boot normally binds configuration at startup; applying changes may require a rollout/restart or a purposefully designed refresh mechanism.

Do not treat an updated volume as proof that effective configuration in the process has changed.

## 18. Windows: Working Directory and Cross-Drive Paths

On Windows, when using PowerShell:

~~~powershell
Set-Location C:\apps\catalog
java -jar .\catalog.jar
~~~

The working directory is `C:\apps\catalog`.

However:

~~~powershell
Set-Location C:\Temp
java -jar C:\apps\catalog\catalog.jar
~~~

The working directory is `C:\Temp`. Default `file:./config/` corresponds to `C:\Temp\config`.

To specify an absolute configuration directory in Spring Boot, you can use a URI-style path with `/` separators:

~~~powershell
java -jar C:\apps\catalog\catalog.jar "--spring.config.additional-location=file:C:/apps/catalog/config/"
~~~

File URL syntax, quoting, and drive letters should be tested on your Windows/Java environment. Use proper URI-style absolute paths instead of adding extra backslashes that shells or parsers can misinterpret.

### 18.1. Windows Services differ from terminals

When an application runs via a service wrapper, Scheduled Task, or a process launched by an administrative tool, the current directory may differ from a developer terminal. It may even be a system directory rather than where the JAR is placed.

Reliable solutions:

- Configure the working directory in the service wrapper if supported.
- Use an absolute path for external Config Data.
- Verify the service identity has read permissions on the files.
- Inspect `user.dir` during diagnostics.
- Do not rely on environment variables that only exist in an interactive PowerShell session if the service does not inherit them.

## 19. CI/CD: Ensuring Artifacts and Config Do Not Depend on Build Paths

CI/CD pipelines typically build a JAR at:

~~~text
workspace/project/target/catalog.jar
~~~

and deploy it to:

~~~text
/opt/catalog/catalog.jar
~~~

If code or scripts read:

~~~text
./config/application.yml
~~~

then in CI it may point to `workspace/project/config`, while on the server it points to `/config` or `/opt/catalog/config` depending on the service runner.

A repeatable deployment should explicitly define:

1. Where the JAR is placed.
2. Where Config Data is mounted or copied.
3. Which user runs the process.
4. What the working directory is.
5. Which profiles are enabled.
6. Which `spring.config.location` or `spring.config.additional-location` is supplied.
7. Which files are required and which are optional.
8. Read permissions and precedence order when overrides exist.
9. The reload/restart procedure when configuration changes.

Example explicit startup script:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

APP_HOME=/opt/catalog
CONFIG_DIR=/etc/catalog

cd "$APP_HOME"

exec /usr/bin/java \
  -Dspring.profiles.active=prod \
  -Dspring.config.additional-location="file:$CONFIG_DIR/" \
  -jar "$APP_HOME/catalog.jar"
~~~

`exec` replaces the shell process with the Java process, which is usually convenient for signal handling. Because the Config Data path is absolute, even if `cd` changes in the script, `/etc/catalog` remains unambiguous.

In production, paths, users, and timeouts should follow system conventions. An illustrative script does not automatically verify full security policies or file readability.

## 20. A Reproducible Deployment Configuration Setup

Recommended layout for Linux:

~~~text
/opt/catalog/
└── catalog.jar

/etc/catalog/
├── application.yml
└── application-prod.yml
~~~

The JAR contains non-sensitive default values:

~~~yaml
# classpath:/application.yml
app:
  region: local
  connect-timeout: 3s
  retries: 2
~~~

External file:

~~~yaml
# /etc/catalog/application.yml
app:
  region: apac
  connect-timeout: 8s
~~~

External profile-specific file:

~~~yaml
# /etc/catalog/application-prod.yml
app:
  retries: 4
~~~

Command:

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/catalog/
~~~

Expected result if no higher-precedence source exists:

| Property | Effective value | Source |
| --- | --- | --- |
| `app.region` | `apac` | External `application.yml` |
| `app.connect-timeout` | `8s` | External `application.yml` |
| `app.retries` | `4` | External `application-prod.yml` |

If external `application.yml` lacks `app.retries`, the default `2` in the JAR could still be used, except the profile file `application-prod.yml` overrides it to `4`.

Note that a YAML file sitting in the right place and being loaded does not mean it beats **every** source. An environment variable or CLI option can still override individual properties.

## 21. File Not Found vs. File Loaded but Overridden?

Two situations that must be clearly distinguished.

### 21.1. The file is genuinely not loaded

Example:

~~~text
Expect: /etc/catalog/application-prod.yml
Actual: /etc/catalog/application.yml
Active profiles: default
~~~

Likely caused by the wrong profile or a missing file.

Or:

~~~text
Expect: /opt/catalog/config/application.yml
CWD:    /tmp
Default location resolved to: /tmp/config/
~~~

This is a working-directory error.

### 21.2. The file loaded, but its value did not win

Suppose the file has:

~~~yaml
app:
  region: apac
~~~

Deployment has:

~~~bash
APP_REGION=eu java -jar catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/
~~~

If the OS environment supplies `APP_REGION=eu` with higher precedence than the config file, the effective `app.region` may be `eu`.

Therefore, never conclude "Spring Boot could not find the YAML" merely because a property differs from expectations. Determine **whether the file participated in Config Data** and **which property source won**.

### 21.3. Avoid inferring from `Environment.containsProperty`

~~~java
environment.containsProperty("app.region");
~~~

only answers whether the key resolves to a value. It **does not tell you** whether the key came from external YAML, classpath YAML, an environment variable, or CLI. To debug origin, use property source observability with security restrictions.

## 22. Checking via Spring Boot Config Data Logs

To observe config discovery and loading, Spring Boot has a logger under the namespace:

~~~text
org.springframework.boot.context.config
~~~

You can enable TRACE level during diagnostics:

~~~bash
java -jar catalog.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

Or when specifying a location:

~~~bash
java -jar catalog.jar \
  --logging.level.org.springframework.boot.context.config=TRACE \
  --spring.config.additional-location=file:/etc/catalog/
~~~

Logs typically trace location candidates, documents, and Config Data processing for your Spring Boot version. Message text and detail level can vary between versions; do not build production parsers dependent on exact log wording.

**Security note:** TRACE can produce a large amount of configuration/environment detail. Use it temporarily and avoid copying logs containing secrets to publicly accessible places.

Another option, when Spring Boot Actuator is safely enabled, is inspecting:

~~~text
/actuator/env
/actuator/configprops
~~~

`/actuator/env` helps observe property sources and effective values, while `/actuator/configprops` shows bound configuration objects. These endpoints must be secured and configured with redaction for sensitive data; never expose them publicly just to debug a YAML file.

## 23. Ordered Diagnostic Checklist

When a deployment reports configuration errors, work through this sequence:

1. **Right artifact?** Verify the running JAR file/version; do not assume from service name.
2. **Right working directory?** Inside the process, print `user.dir` or inspect service/container `workingDir`.
3. **Right external path?** For `file:./...`, mentally substitute `.` with the real working directory.
4. **Does the file exist?** Check the filesystem as seen by the process/container, not just the host.
5. **Read permissions?** Verify owner/group/ACL/mount permissions for the process user.
6. **Right filename?** `application.yml` or `application-prod.yml`; is `spring.config.name` overridden?
7. **Right profiles?** Verify `spring.profiles.active` from runtime.
8. **Using `location` or `additional-location`?** `location` replaces defaults; `additional-location` adds to defaults.
9. **Is `optional:` used?** Missing locations may be silently skipped.
10. **Correct import semantics?** `file:./...` follows CWD; import-relative follows the declaring file.
11. **Config tree or YAML?** Multiple key/value files are not a single `application.yml`.
12. **File loaded, yet overridden?** Check CLI, JVM system properties, OS env, and profile-specific sources.
13. **Conversion/validation errors?** Finding the file does not mean every property is valid.
14. **Which version is running?** Config Data loading differs between Boot 2.3 and 2.4+, or newer versions.
15. **Did you restart/refresh properly after editing config?** Spring Boot normally does not rebind automatically when files change.

Walk through this checklist before editing Java code. Many incidents are fixed by correcting the startup command, mount path, or read permissions.

## 24. Specific Errors and Resolutions

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Works in IDE, systemd does not see `./config` | Different working directory | Set `WorkingDirectory` or use absolute `additional-location` |
| Running `java -jar /opt/app.jar` from `/tmp` gets default config | CWD is `/tmp` | `cd` to the right directory or specify `file:/opt/...` |
| File exists on Docker host, app does not see it | Not mounted or wrong target path | Check `--mount`, `volumes`, and container filesystem |
| Kubernetes mounts ConfigMap at `/etc/app`, app uses `./config` | Mismatched paths | Set `SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/app/` |
| `application-prod.yml` has no effect | `prod` profile not active | Supply `SPRING_PROFILES_ACTIVE=prod` |
| Config packaged in JAR is no longer used | `spring.config.location` replaced defaults | Use `additional-location` to keep JAR defaults |
| Startup fails with `ConfigDataLocationNotFoundException` | Explicit location does not exist | Fix path or add `optional:` if genuinely optional |
| File exists but cannot be read | Permissions/ACL/SELinux/mount | Check process identity and access rights |
| App ignores `custom.yml` | Basename is not `application` or not imported | Use `spring.config.name`, file location, or `spring.config.import` |
| Putting `spring.config.location` in YAML to point to another YAML does nothing | Property read too late | Supply from OS env/JVM system property/CLI upfront |
| `file:./child.yml` points to wrong file | CWD differs from file containing import | Use import-relative `child.yml` or absolute path |
| `config/*/` misses files two levels deep | Wildcard is one level only | Change layout or add explicit locations |
| ConfigMap updated, app still uses old values | No automatic refresh | Restart/rollout or apply a designed reload mechanism |
| YAML appears ignored, yet `APP_REGION` is set | Source precedence | Identify effective value and overriding source |
| Added `optional:` so startup succeeds, yet runs in wrong environment | Missing external config skipped | Keep `optional:` only for truly optional files and add validation |
| Multiple profiles behave unexpectedly | Location groups/order | Inspect `,` and `;` ordering alongside active profiles |
| Secret file mounted, yet no property created | Key/value files not using config tree | Use `spring.config.import=configtree:/...` for the right source type |

## 25. Using Validation to Avoid Silently Running in the Wrong Environment

A working-directory error can cause Spring Boot to fall back to default files inside the JAR without raising an error. If the default configuration is valid by type yet **invalid for production**, you need an explicit startup contract.

For example, require deployments to specify an environment ID:

~~~yaml
# External production config
app:
  deployment:
    id: prod-apac-01
  endpoint: https://api.example.test
~~~

A `@ConfigurationProperties` model:

~~~java
package com.example.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.deployment")
public record DeploymentProperties(
        @NotBlank String id) {
}
~~~

Register it with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(DeploymentProperties.class)` and include a suitable Bean Validation implementation (typically `spring-boot-starter-validation` in Spring Boot 3.x).

If no source supplies `app.deployment.id`, the application can fail during bind/validation instead of silently picking an unknown environment.

However, if the JAR already packages a non-blank dummy `id`, `@NotBlank` **will not catch** the wrong environment. When strictness is required, design a rule verifying the deployment ID matches the deployment source or an independently supplied expected value. Never put a dummy production default inside the JAR just to pass validation.

### 25.1. Do not use secrets as diagnostic markers

Do not print database passwords, API tokens, or the entire `Environment` to prove a file was loaded. You can add a **non-sensitive** property like `app.deployment.id` for controlled logging.

Example:

~~~java
@Bean
ApplicationRunner printDeploymentId(DeploymentProperties properties) {
    return args -> System.out.println(
            "deployment.id=" + properties.id());
}
~~~

A production service should use a logging framework with explicit log-level policies; `System.out.println` here only illustrates the idea.

## 26. Hands-On Exercises

### Exercise 1 — Predict the path

Given:

~~~text
JAR: /opt/catalog/catalog.jar
Config: /opt/catalog/config/application.yml
Current directory at run time: /tmp
Command: java -jar /opt/catalog/catalog.jar
~~~

**Question:** Which file path does Spring Boot search by default using `file:./config/`?

**Answer:** the resolved path is `/tmp/config/`. `/opt/catalog/config/application.yml` is not automatically found via that location.

**Fix A:**

~~~bash
cd /opt/catalog
java -jar catalog.jar
~~~

**Fix B:**

~~~bash
java -jar /opt/catalog/catalog.jar \
  --spring.config.additional-location=file:/opt/catalog/config/
~~~

Fix B does not depend on the current directory.

### Exercise 2 — Keep defaults in the JAR

The JAR has `classpath:/application.yml` containing `app.timeout=3s`. `/etc/catalog/application.yml` only contains `app.endpoint`.

**Question:** Should you use `spring.config.location=file:/etc/catalog/` or `spring.config.additional-location=file:/etc/catalog/` to keep `app.timeout` from the JAR?

**Answer:** use `spring.config.additional-location`. `location` replaces default search locations, so it does not automatically keep the classpath file loaded.

### Exercise 3 — Missing location

Command:

~~~bash
java -jar catalog.jar \
  --spring.config.additional-location=file:/etc/catalog/missing.yml
~~~

If the specified location does not exist, what error might the application throw?

**Answer:** `ConfigDataLocationNotFoundException`. Use `optional:file:/etc/catalog/missing.yml` only when the file is genuinely optional. For required files, fix the path and read permissions.

### Exercise 4 — Distinguish import-relative

`/etc/catalog/application.yml` contains:

~~~yaml
spring:
  config:
    import: optional:parts/limits.yml
~~~

Where does it look for the file?

**Answer:** under import-relative semantics, `/etc/catalog/parts/limits.yml`.

If changed to:

~~~yaml
spring:
  config:
    import: optional:file:./parts/limits.yml
~~~

that is a `file:`-prefixed filesystem location dependent on the process working directory. They are not equivalent when the app runs from another directory.

### Exercise 5 — Paths inside Docker

The Dockerfile sets `WORKDIR /app`, config is mounted at `/etc/catalog/application.yml`, and `SPRING_CONFIG_ADDITIONAL_LOCATION` is not set.

**Question:** Does Spring Boot scan `/etc/catalog/` by default?

**Answer:** Not simply because that path exists inside the container. Default external search locations under `/app` are `/app` and `/app/config` (plus direct subdirectories of `config`). Set an absolute additional location or mount into an appropriate default location.

### Exercise 6 — Right file, wrong value

External YAML:

~~~yaml
app:
  region: apac
~~~

The container runs with variable:

~~~bash
APP_REGION=eu
~~~

**Question:** Why can `Environment.getProperty("app.region")` return `eu`?

**Answer:** OS environment is a higher-precedence property source than config data files in standard mode. This is likely an **override**, not a file-lookup bug.

### Exercise 7 — Design a CWD-independent startup

A service runs across multiple environments: IDE, systemd, Docker, Kubernetes. The goal is to keep defaults in the JAR while giving each deployment its own YAML set.

**Suggested answer:**

1. Package non-sensitive defaults in `classpath:/application.yml`.
2. Standardize an explicit path **inside the runtime environment**, such as `/etc/catalog/`.
3. Mount or copy files to that path with proper read permissions.
4. Supply `SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/catalog/` at runtime.
5. Supply `SPRING_PROFILES_ACTIVE` if using profiles.
6. Require a deployment marker or config constraint genuinely needed for production.
7. Verify startup logs, property source priority, and test running from a different working directory.

This makes deploying the same JAR reproducible without depending on whatever directory an operator happens to invoke the command from.

## 27. Quick Operations Checklist

Before concluding a bug is in Spring Boot:

- [ ] Identify which JAR is actually running and the Spring Boot version.
- [ ] Identify `user.dir`/working directory of the exact **process**.
- [ ] Confirm the file exists in the right filesystem, including inside containers/pods.
- [ ] Check `application.yml`/`application-prod.yml` names and active profiles.
- [ ] Verify the right choice of `location`, `additional-location`, or `import`.
- [ ] For directory locations, include a trailing `/`.
- [ ] For required files, do not accidentally add `optional:`.
- [ ] Distinguish `file:./...`, `file:/...`, `classpath:...`, and import-relative.
- [ ] Verify read permissions for the process's exact user/group.
- [ ] Verify precedence order: CLI, JVM system properties, environment, config data.
- [ ] Enable controlled TRACE logging on `org.springframework.boot.context.config` when needed.
- [ ] Avoid logging secret values or exposing config Actuator endpoints publicly.
- [ ] Verify restart/rollout after configuration changes.
- [ ] Put the config-location contract into scripts, Helm charts, or service units instead of relying on manual `cd` habits.

## 28. Takeaways

1. **Current working directory is not the JAR's directory.** `java -jar /opt/app.jar` does not automatically switch the working directory to `/opt`.
2. **Default external locations include `file:./`, `file:./config/`, and `file:./config/*/`**, all resolved relative to the working directory.
3. **`classpath:/` is not filesystem `./`**; resources inside the JAR follow separate lookup rules.
4. **`spring.config.location` replaces default locations**, while **`spring.config.additional-location` adds to them** and allows external config to override defaults.
5. **`spring.config.name/location/additional-location` must be supplied very early**, e.g., via OS environment, JVM system property, or CLI.
6. **`optional:` only permits a location to be absent**; it does not fix parse errors, permissions, or validation failures.
7. **`spring.config.import` supports import-relative paths** when declaring a prefix-free location, unlike `file:./...`.
8. **Docker/Kubernetes have their own filesystems and working directories**; host paths do not automatically become container paths.
9. **systemd and Windows Services do not necessarily inherit an interactive shell's CWD**; configure working directories or absolute locations explicitly.
10. **Reading the wrong value does not necessarily mean the file could not be found**: it can be due to profiles, property-source precedence, a missing restart, or a higher-precedence override.
11. **Production needs an appropriate fail-fast contract** for required sources rather than adding `optional:` merely to suppress exceptions.
12. **Make deployments reproducible:** absolute config locations, read permissions, profiles, startup commands, and diagnostics must be defined together.

### References

- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Config Data Files / Config Data Location: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files
- Spring Boot Reference — Importing Additional Data: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing
- Spring Boot Reference — Type-safe Configuration Properties and Validation: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot How-to — Properties and Configuration: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html

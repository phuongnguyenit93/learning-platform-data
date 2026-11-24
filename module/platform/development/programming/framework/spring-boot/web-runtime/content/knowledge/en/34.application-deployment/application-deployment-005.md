# Externalizing Certificates, Temporary Directories, and Environment Configuration

## 1. Goal: Separating the Artifact from the Runtime

A Spring Boot application packaged as an executable JAR or container image should be able to use **the exact same build** across dev, staging, and production. TLS certificates, private keys, connection settings, temporary directories, uploads, and secrets must not be baked into the JAR. The core principle is **immutable artifact, external configuration, separate writable storage**.

In the **Spring Boot - web-runtime** module, **Application Deployment** topic, you will learn how to:

1. Separate **certificates, private keys, keystores, and truststores** out of `BOOT-INF/classes`, reading them from mounted files and protecting them with permissions.
2. Externalize **environment configuration** using `application.properties`/YAML outside the JAR, env vars, command-line arguments, `spring.config.additional-location`, `spring.config.import`, and `configtree:`.
3. Distinguish **JVM temp** (`java.io.tmpdir`), **Spring MVC multipart temp** (`spring.servlet.multipart.location`), **WebFlux multipart temp** (`spring.webflux.multipart.file-storage-directory`), **Tomcat basedir**, and the **business data directory**.
4. Build and run a **Java 17 + Spring Boot 3.3.5** lab that saves uploads to an external directory, then switches from HTTP to HTTPS using an external PEM bundle without rebuilding the JAR.
5. Map the same model to Docker Compose, Kubernetes volumes/ConfigMap/Secret/PVC, and systemd.
6. Handle least-privilege security, secret rotation, read-only root filesystems, disk quotas, Pod replication, TLS trust, and deployment failures.

**Rule:** The JAR/image holds code and non-sensitive static resources; config, certs/keys, temp, and mutable data live at runtime with their own permissions, access controls, and lifecycles. Moving files out of the JAR is the first step—you must also classify which data is **ephemeral** and which is **durable**.

## 2. Why Not Put Private Keys, Temp Files, and Uploads Inside the JAR?

An executable Spring Boot JAR has a structure similar to:

~~~text
myapp.jar
├── BOOT-INF/
│   ├── classes/
│   │   ├── application.properties
│   │   ├── static/
│   │   └── com/example/...
│   └── lib/
└── META-INF/
~~~

Resources inside the JAR are meant to be **read-only**. Placing `server.key`, `production.p12`, or API tokens in `src/main/resources` copies them into the artifact, risking exposure through registries, CI machines, backups, and Git history. Rotating a certificate would force unnecessary rebuilds and redeploys; leaking the artifact leaks the private key.

Nor should you expect `ClassPathResource.getFile()` to be a writable location: in a nested JAR, resources do not necessarily have an independent writable filesystem path. With a read-only container root filesystem, writing into `/app` or image layers will fail.

~~~java
// ANTI-PATTERN — wrong example, does not run as a standalone class:
File target = new ClassPathResource("uploads/example.bin").getFile();
Files.write(target.toPath(), bytes);
~~~

**Right:** configure the app to accept a runtime `Path`, such as `/var/lib/myapp/uploads`, and operate on it via `Files.createDirectories` and `Files.copy`. Never use a client-supplied filename directly as a storage path.

### 2.1. Resource Classification

| Category | Examples | Lifetime and permissions |
| --- | --- | --- |
| Immutable artifact | JAR/classes/static CSS | Versioned, read-only |
| Nonsecret config | Port, timeouts, feature flags, downstream URLs | Varies by environment, usually read-only |
| Sensitive secrets | TLS private key, DB password, API token | Secret store/mounted file, minimal permissions |
| Temporary work | Multipart spool, transform scratch, JVM temp | Writable, quota-bounded with cleanup, expendable |
| Durable business state | User uploads, reports, metadata | PVC/object storage/DB, backed up |
| Operational logs | stdout, optional access logs | Prefer centralized logs, separate retention |

**Do not place durable uploads on an ephemeral temp volume.** A container restart or Pod replacement can destroy local state. In a multi-replica cluster, files saved on Pod A's private filesystem do not automatically appear on Pod B.

## 3. An Operationally Clean Runtime Layout

~~~text
/opt/myapp/
    app.jar                      # immutable

/etc/myapp/
    application-prod.properties  # external nonsecret config
    tls/
        server.crt                # certificate
        server.key                # private key, strictly protected
    secrets/
        db.password               # secret file

/var/tmp/myapp/
    multipart/                   # Servlet multipart spool
    processing/                  # temporary business work
    tomcat/                      # optional Tomcat basedir

/var/lib/myapp/
    uploads/                     # persistent business data

/var/log/myapp/                  # optional file logs
~~~

In containers, these paths are **volume mount destinations**. On a Linux host, systemd or an administrator creates and sets permissions on these paths. Windows environments use different absolute paths, yet the separation of artifact, config, secrets, temp, and data stays the same.

Some items only need **read-only** access (config, certificates, JAR), whereas temp and uploads need **writable** access. Do not mount everything into a single `/data` folder with `777` permissions: that destroys isolation and increases blast radius if the app is compromised.

### 3.1. Relative Paths Are Not Necessarily Relative to the JAR Directory

~~~bash
cd /opt/myapp
java -jar app.jar --app.storage.root=./runtime/uploads
~~~

`./runtime/uploads` resolves against the **process working directory**, with no guarantee that it matches the JAR's directory. Under Docker `WORKDIR`, systemd `WorkingDirectory`, and IDEs, the working directory can differ. Production should use **absolute paths** and verify the real resolved file location.

## 4. Externalized Configuration in Spring Boot 3.3

Spring Boot 3.3 loads configuration from multiple property sources such as:

- `application.properties`/`application.yaml` packaged inside the JAR (safe defaults).
- Files outside the JAR: `file:/etc/myapp/application.properties` or profile-specific files.
- Environment variables: `SERVER_PORT`, `APP_STORAGE_ROOT`, `SPRING_CONFIG_ADDITIONAL_LOCATION`.
- JVM system properties `-Dkey=value`.
- Spring Boot command-line arguments `--key=value`.
- `spring.config.import` to load files/properties/config trees.
- Other secret/config providers when integrated.

Config values can be injected via `@Value`, Spring `Environment`, or bound into POJOs/records with `@ConfigurationProperties`. When multiple sources define the same key, **property source precedence** determines the final value. Do not guess from a single file if deployment includes env vars, CLI args, ConfigMaps, Helm values, or Config Server.

### 4.1. classpath: and file:

~~~properties
# Read-only resource packaged with code:
app.banner=classpath:/banner.txt

# Runtime file outside JAR:
app.partner-ca=file:/etc/myapp/tls/partner-ca.crt

# Custom property bound to Path:
app.storage.root=/var/lib/myapp/uploads
~~~

`classpath:` searches the classpath; `file:` refers to a filesystem resource. For a custom property typed as `Path`, usually supply a plain filesystem path `/var/lib/...` rather than a Spring `file:...` resource URL; inspect the bean's Java type.

### 4.2. Reading an External application.properties

~~~bash
java -jar /opt/myapp/app.jar \
  --spring.config.additional-location=file:/etc/myapp/
~~~

Assuming `/etc/myapp/application.properties` or `application-prod.properties` exists for the active profile, Boot adds that location to its default search list. Per Spring Boot 3.3, directory locations should end with `/`.

Comparison:

~~~properties
spring.config.additional-location=file:/etc/myapp/
spring.config.location=file:/etc/myapp/
~~~

`additional-location` **adds** to the default locations; `location` **replaces** the default search locations. When overriding safe defaults packaged in the JAR, `additional-location` is usually more convenient.

`spring.config.location`/`additional-location` are evaluated early when Boot searches for config, so supply them via env/CLI/system property at startup rather than inside a file the app has not located yet.

### 4.3. optional and Fail-Fast

~~~bash
# Add optional config location; skip if missing:
java -jar app.jar \
  --spring.config.additional-location=optional:file:/etc/myapp/
~~~

`optional:` makes sense for non-mandatory config. For mandatory TLS private keys or DB credentials, **never use `optional:` or empty default passwords** to mask provisioning errors. Failing fast when required config/secrets are missing is much safer.

### 4.4. Spring Profiles

File `/etc/myapp/application-prod.properties`:

~~~properties
server.port=8443
app.storage.root=/var/lib/myapp/uploads
~~~

Launch:

~~~bash
java -jar /opt/myapp/app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/myapp/
~~~

The `ApplicationContext` loads the matching profile per Config Data rules. Never commit production passwords in profile files inside a repo. They may reference **paths** to external secret files, never raw sensitive material.

## 5. Runtime Environment Variables, Placeholders, and Precedence

Safe defaults packaged in `src/main/resources/application.properties`:

~~~properties
server.port=8080
app.storage.root=${APP_DATA_DIR:./runtime/data}
spring.servlet.multipart.location=${APP_TMP_DIR:./runtime/tmp}
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
~~~

Spring placeholders `${NAME:default}` resolve env/config properties if present, falling back to the default if absent. In real files, the syntax starts with a dollar sign and curly braces. Relative defaults should only be used for **local labs**; production must supply durable/writable deployment paths.

Linux example:

~~~bash
export APP_DATA_DIR=/var/lib/myapp/uploads
export APP_TMP_DIR=/var/tmp/myapp/multipart
java -jar /opt/myapp/app.jar
~~~

Boot relaxed binding can map `APP_STORAGE_ROOT` to `app.storage.root`. Passing **paths** via env vars can be safer than passing raw PEM keys or passwords in env vars. Env-stored secrets risk leaking through process introspection, crash dumps, or debug tools.

**Precedence matters:** CLI args normally outrank environment variables. If `--app.storage.root=/wrong/place` is in the launch script, `APP_STORAGE_ROOT=/var/lib/myapp/uploads` will not take effect. Verify effective properties and override sources while avoiding logging raw secret values.

## 6. Secret Files via configtree:

Kubernetes/Docker/secret providers can mount each secret key as a file:

~~~text
/run/secrets/myapp/
    db.password
    partner.api-key
~~~

To have Boot treat filenames as property names:

~~~properties
spring.config.import=configtree:/run/secrets/myapp/
~~~

Once imported, `db.password` reads from the `db.password` file and `partner.api-key` from its corresponding file. Other properties can reference them:

~~~properties
spring.datasource.password=${db.password}
partner.api-key=${partner.api-key}
~~~

If the secret tree is mandatory, do not prefix `configtree:` with `optional:`. The application must fail if the mount is missing or read permission is denied. Never print password/api-key values in logs.

Example creating **dummy values** for local testing only:

~~~bash
mkdir -p runtime/secrets
printf '%s' 'demo-only-password' > runtime/secrets/db.password
chmod 600 runtime/secrets/db.password
~~~

**`configtree:` does not imply hot-refreshing all beans.** Updating config/secret files does not automatically rebind `@ConfigurationProperties`, `DataSource`, `HttpClient`, or arbitrary components. Usually a rolling restart is needed; SSL PEM bundles have their own reload mechanism when enabled and supported by the consumer.

## 7. TLS Certificates: Certificate, Private Key, Keystore, Truststore

| Resource | Role | Classification |
| --- | --- | --- |
| `server.crt` | Public server certificate and chain | Typically public data |
| `server.key` | Server private key proving identity | **Highly sensitive secret** |
| `server.p12` / JKS | KeyStore potentially holding cert/private key | Secret when containing a private key |
| CA cert / truststore | Protects trusting the right peer | Integrity-critical, not necessarily confidential |
| Keystore password | Unlocks keystore/private key | Secret |
| Outbound client cert/key | App identity for mTLS to downstream | Secret and **distinct** from inbound TLS identity |

Certificates may be issued by a corporate PKI/CA or a public CA. Private keys must never reside in JARs, Git, Dockerfiles, ConfigMaps, or logs. Use secret management, read-only volumes, least-privilege permissions, and rotation/auditing.

### 7.1. HTTPS Server from External PEM

Boot 3.3 supports:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.certificate=file:/etc/myapp/tls/server.crt
server.ssl.certificate-private-key=file:/etc/myapp/tls/server.key
~~~

PEM private keys should be in **PKCS#8** format (typically beginning with `-----BEGIN PRIVATE KEY-----` or `-----BEGIN ENCRYPTED PRIVATE KEY-----`). Older PKCS#1/SEC1 keys may need conversion for OpenSSL/Spring integration.

**Do not expect both HTTP 8080 and HTTPS 8443 simultaneously** simply by setting `server.ssl.*` and `server.port=8443`. Standard Spring Boot auto-config sets up one connector from properties; supporting both requires an explicit extra connector/server setup or an ingress.

### 7.2. HTTPS Server from External PKCS12

~~~properties
server.port=8443
server.ssl.key-store=file:/etc/myapp/tls/server.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
~~~

If the key password differs from the keystore password, configure `server.ssl.key-password` accordingly. Never hardcode real passwords in packaged config; mounted secret files/providers are often preferable to env vars in production.

### 7.3. Outbound Trust Differs from Inbound HTTPS

`server.ssl.*` configures the server identity presented to clients. A `WebClient`/`RestClient` calling a downstream service using a private CA or client mTLS requires its own **client SSL trust/identity** via SSL bundles/HTTP client configuration. Never take the server key assuming every outbound HTTP client will automatically trust CAs or present a client cert.

Never use trust-all, `curl -k`, or disabled hostname verification to work around `PKIX path building failed` in production. Fix the root cause in the CA chain, truststore, SAN/hostname, and certificate validity.

## 8. Spring Boot SSL Bundles: Organizing TLS Material Outside the JAR

Spring Boot 3.3 offers `spring.ssl.bundle.pem.*` and `spring.ssl.bundle.jks.*`, letting you attach a named bundle to the embedded web server.

### 8.1. File-Backed PEM Bundle

~~~properties
server.port=8443
server.ssl.bundle=web

spring.ssl.bundle.pem.web.keystore.certificate=file:/etc/myapp/tls/server.crt
spring.ssl.bundle.pem.web.keystore.private-key=file:/etc/myapp/tls/server.key
~~~

`server.ssl.bundle=web` selects the bundle named `web`. **Do not mix `server.ssl.bundle` with discrete `server.ssl.key-store` or `server.ssl.certificate`/`certificate-private-key`.** Per Boot 3.3 docs, cipher/protocol settings when using bundles must be configured in the appropriate bundle options.

### 8.2. JKS/PKCS12 Bundle

~~~properties
server.port=8443
server.ssl.bundle=web

spring.ssl.bundle.jks.web.keystore.location=file:/etc/myapp/tls/server.p12
spring.ssl.bundle.jks.web.keystore.type=PKCS12
spring.ssl.bundle.jks.web.keystore.password=${TLS_KEYSTORE_PASSWORD}
~~~

This is an **alternative** to the PEM bundle—do not configure both bundle types under the same name expecting the app to pick one. Both certificate file location and keystore password must be valid.

### 8.3. Conditional Certificate Reload

Spring Boot 3.3 supports opt-in reload-on-update for PEM bundles:

~~~properties
server.ssl.bundle=web
spring.ssl.bundle.pem.web.keystore.certificate=file:/etc/myapp/tls/server.crt
spring.ssl.bundle.pem.web.keystore.private-key=file:/etc/myapp/tls/server.key
spring.ssl.bundle.pem.web.reload-on-update=true
~~~

In Boot 3.3 docs, supported consumers include **Tomcat and Netty embedded web servers**. A file watcher detects file changes, and its quiet period can be tuned via `spring.ssl.bundle.watch.file.quiet-period`.

**Automatic application of every certificate update is not guaranteed:** Kubernetes Secret projections can swap symlinks, `subPath` mounts may not receive updates, and watchers can miss expected events. Existing TLS connections also retain session state. Test **new TLS handshakes** after updates, and if reload is not guaranteed, perform a **rolling restart** per release policy.

## 9. Types of Temporary Directories in the Spring Web Runtime

| Component | Property or setting | Role |
| --- | --- | --- |
| JVM general temp | `-Djava.io.tmpdir=/var/tmp/myapp` | `Files.createTempFile`, many Java libraries |
| Spring MVC Servlet multipart | `spring.servlet.multipart.location=/var/tmp/myapp/multipart` | Intermediate uploaded file parts |
| Tomcat base | `server.tomcat.basedir=/var/tmp/myapp/tomcat` | Embedded Tomcat base/work directories |
| Spring WebFlux multipart decoder | `spring.webflux.multipart.file-storage-directory=/var/tmp/myapp/webflux` | Spills file parts exceeding max-in-memory |
| App processing temp | `app.processing.temp-root=/var/tmp/myapp/work` | Temporary business file processing |
| Durable upload root | `app.storage.root=/var/lib/myapp/uploads` | Business files requiring retention/backup |
| Optional access log | `server.tomcat.accesslog.directory` | Separate logs, distinct lifecycle from temp |

**No single property guarantees every library uses the same temp directory.** Changing `java.io.tmpdir` does not override app-specific temp paths; changing the multipart location does not redirect every `Files.createTempFile` call in code.

### 9.1. JVM Temp Is a Startup System Property

~~~bash
mkdir -p /var/tmp/myapp
java -Djava.io.tmpdir=/var/tmp/myapp \
  -jar /opt/myapp/app.jar
~~~

This is a JVM option, not `spring.java.io.tmpdir`. Many libraries read or cache the temp path at initialization; do not treat `System.setProperty("java.io.tmpdir", ...)` inside a request handler as a reliable runtime configuration.

In Docker/Kubernetes, you can use:

~~~text
JAVA_TOOL_OPTIONS=-Djava.io.tmpdir=/var/tmp/myapp
~~~

Never put passwords into `JAVA_TOOL_OPTIONS` because the JVM launcher may log options or tooling may read process arguments.

### 9.2. Spring MVC Multipart Spool

~~~properties
spring.servlet.multipart.location=/var/tmp/myapp/multipart
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
~~~

Boot 3.3 describes `location` as the **intermediate location of uploaded files**. Never use it as permanent storage. The directory must exist and be writable before the application accepts uploads.

~~~bash
mkdir -p /var/tmp/myapp/multipart
chmod 700 /var/tmp/myapp/multipart
~~~

`file-size-threshold=0B` allows the Servlet implementation to write parts to disk almost immediately rather than buffering them completely in memory. Multipart size limits do not replace disk quotas, antivirus scanning, rate limits, or authentication.

### 9.3. WebFlux Multipart (Different from MVC)

In applications using `spring-boot-starter-webflux`:

~~~properties
spring.webflux.multipart.file-storage-directory=/var/tmp/myapp/webflux
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=10MB
spring.webflux.multipart.max-parts=20
~~~

In Boot 3.3, this directory stores file parts exceeding the in-memory size, defaulting to creating `spring-multipart` in system temp. **This property is ignored when using `PartEvent` streaming support.** With `Flux<PartEvent>`, you must consume/release `DataBuffer`s properly, persist files yourself, and manage backpressure/limits.

If the app uses MVC/Tomcat, do not copy `spring.webflux.multipart.*` expecting it to change the Servlet multipart location; if the app uses WebFlux/Reactor Netty, do not expect `spring.servlet.multipart.location` to take effect.

### 9.4. Tomcat basedir, Access Logs, and App Logs

~~~properties
server.tomcat.basedir=/var/tmp/myapp/tomcat
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.directory=/var/log/myapp
~~~

Boot 3.3 uses a temp directory when `server.tomcat.basedir` is unset. `server.tomcat.accesslog.directory` can be an absolute path or relative to Tomcat base. It is distinct from `logging.file.name`/`logging.file.path` for application logs. In containers, prefer stdout/stderr + log aggregators, avoiding extra writable log mounts unless required.

## 10. Java 17 + Spring Boot 3.3.5 Lab: Storing Uploads Outside the JAR

The lab project provides a Spring MVC REST endpoint that receives a `MultipartFile` and writes it with a UUID filename into external `app.storage.root`, without using the original filename or a classpath file. The same JAR then runs with HTTPS via an external PEM bundle.

### 10.1. Project Structure

~~~text
external-runtime-lab/
├── pom.xml
├── runtime/                      # outside src/main/resources, DO NOT commit
│   ├── config/
│   ├── tls/
│   ├── data/
│   ├── tmp/
│   └── secrets/
└── src/main/
    ├── java/com/example/external/
    │   ├── ExternalRuntimeApplication.java
    │   ├── StorageProperties.java
    │   └── UploadController.java
    └── resources/
        └── application.properties
~~~

Files under `runtime/` are runtime config/data sources, **not** part of the JAR. Maven only packages `src/main/resources`, so never place certificates or private keys there.

### 10.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>external-runtime-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

`spring-boot-starter-web` provides MVC/embedded Tomcat/Servlet multipart. `spring-boot-starter-actuator` enables `/actuator/health` when exposed appropriately. Java 17 supports records.

### 10.3. Main Class

**`src/main/java/com/example/external/ExternalRuntimeApplication.java`:**

~~~java
package com.example.external;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ExternalRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExternalRuntimeApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` lets Spring Boot discover config records in the package. Do not manually instantiate the record with a hardcoded path inside the controller.

### 10.4. StorageProperties.java

~~~java
package com.example.external;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(Path root) {
}
~~~

For a record with a single constructor in Boot 3.3, constructor binding is inferred. The `app.storage.root` property is converted to `Path` without writing a custom parser.

### 10.5. UploadController.java

~~~java
package com.example.external;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/files")
public class UploadController {

    private final Path root;

    public UploadController(StorageProperties properties)
            throws IOException {
        if (properties.root() == null) {
            throw new IllegalStateException(
                    "app.storage.root must be configured");
        }

        root = properties.root().toAbsolutePath().normalize();
        Files.createDirectories(root);

        if (!Files.isDirectory(root) || !Files.isWritable(root)) {
            throw new IllegalStateException(
                    "Upload directory is not writable: " + root);
        }
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<UploadReceipt> upload(
            @RequestParam("file") MultipartFile file)
            throws IOException {
        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "empty file");
        }

        // Do not use getOriginalFilename() as a filesystem path.
        String id = UUID.randomUUID().toString();
        Path target = root.resolve(id + ".bin");

        // Write a new file; do not overwrite a user-chosen path.
        try (InputStream in = file.getInputStream()) {
            Files.copy(in, target);
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new UploadReceipt(id, Files.size(target)));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Resource> download(
            @PathVariable String id) {
        try {
            UUID.fromString(id);
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid id");
        }

        Path path = root.resolve(id + ".bin");
        if (!Files.isRegularFile(path)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "file not found");
        }

        Resource resource = new FileSystemResource(path);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename(id + ".bin")
                                .build()
                                .toString())
                .body(resource);
    }

    public record UploadReceipt(String id, long bytes) {
    }
}
~~~

**Analysis:**

1. The controller receives the external storage root via dependency injection, creates the directory if missing, and fails fast if unwritable.
2. `Files.copy(InputStream, Path)` creates the output file using a UUID rather than relying on the client filename. It never writes to `src/main/resources/static` or inside the JAR.
3. `UUID.fromString` filters the route ID, preventing raw path traversal from user input.
4. `ResponseEntity.status(CREATED)` returns only after copying completes; the response body holds the ID and written file size.
5. The GET endpoint sets `application/octet-stream` and `Content-Disposition: attachment` so browsers do not interpret uploaded content as HTML.
6. `Files.isWritable` at startup does not guarantee the volume won't run out of space or be remounted read-only later.
7. This is an **external storage demo**: production requires per-file authz, user quotas, malware/content validation, retention, auditing, and cleanup of partial files if copying fails.
8. Direct copying can leave a partial file on crash. Production can stage on the same filesystem and perform an atomic move where supported; do not assume `Files.move` across `emptyDir` and a PVC on different filesystems is atomic.

### 10.6. Packaged application.properties: Safe Local Defaults

~~~properties
spring.application.name=external-runtime-lab
server.port=8080

app.storage.root=${APP_DATA_DIR:./runtime/data}
spring.servlet.multipart.location=${APP_TMP_DIR:./runtime/tmp}

spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB

management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
~~~

This config **contains no passwords or key material**. Relative paths are for local use only. Production must supply absolute directories via env/config volumes.

### 10.7. Create Runtime Folders and Build

~~~bash
mkdir -p runtime/data runtime/tmp runtime/config runtime/tls runtime/secrets
chmod 700 runtime/data runtime/tmp runtime/tls runtime/secrets
mvn clean package
~~~

Build output:

~~~text
target/external-runtime-lab-0.0.1-SNAPSHOT.jar
~~~

`.gitignore`/`.dockerignore` should exclude secrets and the runtime tree:

~~~gitignore
/runtime/
/target/
*.key
*.p12
*.jks
~~~

Verify resources inside the JAR:

~~~bash
jar tf target/external-runtime-lab-0.0.1-SNAPSHOT.jar \
  | grep -E 'application.properties|server.key|server.p12|runtime/'
~~~

Only safe application properties should appear; **no private keys or runtime data should be present**. Secret scanning must cover Git history and JAR/image layers as well, because ignore rules do not remove already-committed secrets.

## 11. Run Local HTTP and Verify External Upload

From the project root:

~~~bash
APP_DATA_DIR=./runtime/data \
APP_TMP_DIR=./runtime/tmp \
java -Djava.io.tmpdir=./runtime/tmp \
  -jar target/external-runtime-lab-0.0.1-SNAPSHOT.jar
~~~

The snippet above uses POSIX shell syntax; Windows PowerShell has its own `$env:APP_DATA_DIR` syntax. Do not assume identical shell syntax.

In another terminal:

~~~bash
printf 'Hello external storage\n' > runtime/sample.txt
curl -i -F "file=@runtime/sample.txt" \
  http://127.0.0.1:8080/api/files
~~~

Expected HTTP **201 Created** with JSON shaped like:

~~~json
{
  "id": "1c8de7ae-b38c-4f84-98b1-98e1f63ba72c",
  "bytes": 23
}
~~~

The ID is an example since runtime UUIDs are random. The sample string is **23 UTF-8 bytes** when created by the `printf` command above; the actual count may vary if you change the sample or shell/file encoding.

Inspect:

~~~bash
ls -la runtime/data
~~~

The new file appears as `<uuid>.bin` in the external directory, not inside the JAR. To download the file, replace `ACTUAL_UUID` with the ID from the JSON response:

~~~bash
curl -i http://127.0.0.1:8080/api/files/ACTUAL_UUID
~~~

Expected HTTP 200 + `application/octet-stream` + `Content-Disposition: attachment` and the binary body. This demo **does not** prove durability if `runtime/data` is actually an ephemeral container layer; deployment must pick the proper PVC/object storage.

## 12. Run HTTPS with the Same JAR Using External PEM Files

### 12.1. Generate a Self-Signed Certificate for the Localhost Lab Only

~~~bash
mkdir -p runtime/tls
openssl req -x509 -newkey rsa:2048 -sha256 -days 7 -nodes \
  -keyout runtime/tls/server.key \
  -out runtime/tls/server.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 runtime/tls/server.key
~~~

The cert has localhost/loopback SANs and is valid for only 7 days. `-nodes` produces an unencrypted key, **for lab use only**; production uses PKI/key protection/secret managers. If your OpenSSL version does not support `-addext`, use an equivalent extension config file instead of dropping SANs and disabling hostname verification.

View certificate metadata without printing the private key:

~~~bash
openssl x509 -in runtime/tls/server.crt \
  -noout -subject -dates -ext subjectAltName
~~~

### 12.2. External Profile application-prod.properties

Create `runtime/config/application-prod.properties`:

~~~properties
server.port=8443
server.ssl.bundle=web

spring.ssl.bundle.pem.web.keystore.certificate=file:./runtime/tls/server.crt
spring.ssl.bundle.pem.web.keystore.private-key=file:./runtime/tls/server.key

# Optional: try hot reload on supported Tomcat/Netty:
spring.ssl.bundle.pem.web.reload-on-update=true

app.storage.root=./runtime/data
spring.servlet.multipart.location=./runtime/tmp
~~~

Note `file:./runtime/tls/...` resolves relative to the **current working directory**. Production should replace these with absolute paths such as `file:/etc/myapp/tls/...`.

### 12.3. Relaunch Without Rebuilding

Stop the HTTP process and run:

~~~bash
java -Djava.io.tmpdir=./runtime/tmp \
  -jar target/external-runtime-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:./runtime/config/
~~~

Spring Boot reads the external `application-prod.properties` and opens HTTPS on 8443. No code edit or JAR rebuild is needed. Verify the certificate using the lab's trust file:

~~~bash
curl --cacert runtime/tls/server.crt \
  https://localhost:8443/actuator/health
~~~

Expected status 200 and body `{"status":"UP"}` when health indicators are normal. Never use `curl -k` as a production solution. When HTTPS listens on 8443, do not assume HTTP 8080 remains active at the same time through the same Boot auto-config.

### 12.4. Rotation Is More Than Overwriting Files

When replacing a certificate:

- Verify key and certificate match, and that SAN/expiry/chain are valid.
- Update the file pair in a way that prevents watchers from reading a half-written state.
- Check `reload-on-update`, consumer support, and how volume projection emits filesystem events.
- Test a **new TLS handshake** after the update along with client trust.
- If reload is not guaranteed reliable, perform a **rolling restart** using a zero-traffic-disruption rollout strategy.

Do not assume arbitrary `application.properties` edits hot-reload like PEM bundles. Most runtime bindings are initialized at app startup.

## 13. Docker: Mounts Instead of Copying Secrets into the Image

### 13.1. Dockerfile

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
COPY target/external-runtime-lab-0.0.1-SNAPSHOT.jar /app/app.jar
EXPOSE 8080

# Do not COPY runtime/, tls private key, or secrets.
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

The container base image should be pinned/audited, and production should use a non-root user. `EXPOSE` is metadata and does not open host ports. If external config enables HTTPS 8443, align service/container port mappings.

### 13.2. docker-compose.yml for the HTTP Lab

~~~yaml
services:
  app:
    build: .
    ports:
      - "8080:8080"
    environment:
      APP_DATA_DIR: /var/lib/myapp/uploads
      APP_TMP_DIR: /var/tmp/myapp
      JAVA_TOOL_OPTIONS: -Djava.io.tmpdir=/var/tmp/myapp
      SPRING_CONFIG_ADDITIONAL_LOCATION: file:/etc/myapp/config/
    volumes:
      - ./runtime/config:/etc/myapp/config:ro
      - ./runtime/tls:/etc/myapp/tls:ro
      - ./runtime/tmp:/var/tmp/myapp
      - ./runtime/data:/var/lib/myapp/uploads
~~~

On the host:

~~~bash
mkdir -p runtime/config runtime/tls runtime/tmp runtime/data
docker compose up --build
~~~

This example is for local use only: bind-mounted data paths do not provide production backup/replication, the image uses root unless a user is specified, and HTTPS is not enabled in this Compose file yet. When moving ConfigMap/secret paths into containers, `application-prod.properties` must reference **container paths**, not host paths.

### 13.3. Docker Read-Only Root Filesystem

When enabling `read_only: true` or Kubernetes `readOnlyRootFilesystem: true`, the application still needs writable mounts for:

- `java.io.tmpdir` (JVM/libraries).
- Servlet multipart spool `spring.servlet.multipart.location`.
- Tomcat `basedir`/workdir if needed.
- Application processing scratch files.
- Business uploads if written locally.
- File logs if not using stdout.

The JAR, app config, and TLS private keys should stay read-only. **Mounting a cert `:ro` does not mean any process that can read it is safe**—if the app is compromised, the key can still be exfiltrated; enforce least privilege and policies.

## 14. Kubernetes: ConfigMap, Secret, emptyDir, PVC

| Volume/resource | Needed for | Do not use for |
| --- | --- | --- |
| ConfigMap volume | Nonsecret app config, paths, limits | Raw TLS private keys/real passwords |
| Secret volume | TLS key/cert, credentials | Replacing RBAC/encryption/auditing |
| `emptyDir` | Short-lived multipart spill/temp/cache | Durable user uploads |
| PVC | Files needing filesystem retention | Assuming multi-pod RWX when storage class does not support it |
| Object storage | Scalable user data across replicas | JVM/temp workdir needing POSIX temp semantics |
| Env vars | Paths, flags, nonsecret config | Uncontrolled dumping of full secrets |

### 14.1. ConfigMap Example

`application.properties` mounted from a ConfigMap at `/etc/myapp/config/application.properties`:

~~~properties
server.port=8443
server.ssl.bundle=web
spring.ssl.bundle.pem.web.keystore.certificate=file:/etc/myapp/tls/server.crt
spring.ssl.bundle.pem.web.keystore.private-key=file:/etc/myapp/tls/server.key

app.storage.root=/var/lib/myapp/uploads
spring.servlet.multipart.location=/var/tmp/myapp

spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB

management.endpoints.web.exposure.include=health
~~~

Only **paths** to the TLS secret appear in the ConfigMap, never private key contents. If TLS terminates at the ingress, the backend can run HTTP and does not need to mount the inbound server private key.

### 14.2. Deployment Pod Template Fragment

This snippet is a **partial Deployment template**, assuming ConfigMap `myapp-config`, Secret `myapp-tls`, and PVC `myapp-data` already exist. Not a complete manifest:

~~~yaml
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
      containers:
        - name: app
          image: registry.example.com/myapp:1.0
          ports:
            - name: https
              containerPort: 8443
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
          env:
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: file:/etc/myapp/config/
            - name: JAVA_TOOL_OPTIONS
              value: -Djava.io.tmpdir=/var/tmp/myapp
            - name: APP_DATA_DIR
              value: /var/lib/myapp/uploads
            - name: APP_TMP_DIR
              value: /var/tmp/myapp
          volumeMounts:
            - name: config
              mountPath: /etc/myapp/config
              readOnly: true
            - name: tls
              mountPath: /etc/myapp/tls
              readOnly: true
            - name: scratch
              mountPath: /var/tmp/myapp
            - name: data
              mountPath: /var/lib/myapp/uploads
      volumes:
        - name: config
          configMap:
            name: myapp-config
        - name: tls
          secret:
            secretName: myapp-tls
            defaultMode: 0440
        - name: scratch
          emptyDir:
            sizeLimit: 1Gi
        - name: data
          persistentVolumeClaim:
            claimName: myapp-data
~~~

**Verify these assumptions:**

1. The JRE image can run as UID 10001; secret files have filenames `server.crt`/`server.key` at the exact paths.
2. `fsGroup`/volume file mode `0440` actually lets the app read the key without making it world-readable. PVC ownership may require separate preparation.
3. The writable `emptyDir` at `/var/tmp/myapp` suffices for JVM/Servlet temp; the app does not inadvertently write to the read-only root filesystem.
4. The data PVC matches durability and access-mode requirements. Multiple pods/nodes sharing an RWO PVC can fail to mount; use object storage for scale-out.
5. `emptyDir.sizeLimit` and container `ephemeral-storage` resources/eviction budgets are aligned; disks can still fill up.
6. ConfigMap updates do not automatically rebind properties into running Spring beans; cert rotation still depends on watchers/reloads.
7. `subPath` mounts may not update when Secrets change; test actual reload or rolling restarts.
8. Service/Ingress/probes must use HTTPS 8443 when backend TLS is enabled. A plain HTTP probe against an HTTPS port will fail even if the app is healthy.

Kubernetes Secrets still require RBAC, etcd encryption at rest if policy mandates, access auditing, rotation, and separation of duties. Simply using `kind: Secret` does not make everything secure automatically.

### 14.3. Contrasting Temp and Durability

`emptyDir` is suited for multipart buffers because request data only needs to exist while processed on that Pod. However, if an upload returns success after saving into `emptyDir`, Pod replacement will wipe the file. **Durable storage** must match the contract—a PVC with proper backup/availability or an object store. With multiple replicas, a client might GET from a different Pod after uploading; private Pod filesystems will not give consistent results.

## 15. systemd When Running an Executable JAR on Linux

Illustrative systemd unit:

~~~ini
[Unit]
Description=Externalized Spring Boot application
After=network.target

[Service]
Type=simple
User=myapp
Group=myapp
WorkingDirectory=/opt/myapp
StateDirectory=myapp
CacheDirectory=myapp
Environment=APP_DATA_DIR=/var/lib/myapp/uploads
Environment=APP_TMP_DIR=/var/cache/myapp
Environment=SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/myapp/
ExecStart=/usr/bin/java -Djava.io.tmpdir=/var/cache/myapp -jar /opt/myapp/app.jar
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

`StateDirectory=myapp` and `CacheDirectory=myapp` let systemd manage directories under `/var/lib/myapp` and `/var/cache/myapp` on many Linux distributions. The `myapp` user/group and JDK path must exist, and certificates/secrets must be readable by the service identity. This unit is not complete security hardening; when enabling `ProtectSystem=strict` or `ReadWritePaths`, explicitly allow state/cache writes.

Never place raw DB passwords in unit files or CLI arguments. Use secret/credential facilities or root-owned restricted files and define proper loading/rotation policies.

## 16. Terminate TLS at Ingress or in Spring Boot?

### 16.1. TLS Terminating at the Edge

~~~text
Browser -- HTTPS 443 --> Ingress/Gateway (holds public TLS key)
                         |
                         '-- HTTP 8080 --> Spring Boot
~~~

If the organization permits HTTP on a trusted internal segment, the app Pod **does not necessarily need to mount the public server private key**. Cert rotation happens at the ingress. If policy requires encrypting every hop or internal mTLS, separate backend TLS is needed.

### 16.2. End-to-End TLS or mTLS

~~~text
Browser -- HTTPS 443 --> Ingress
                         |
                         '-- HTTPS/mTLS 8443 --> Spring Boot
                                                   server cert/key at runtime
~~~

When the app handles HTTPS itself, `server.ssl.bundle` or `server.ssl.*` must point to external cert/key files. When the app also acts as an outbound HTTPS client, truststores/client certs are a **separate concept**.

Do not confuse “externalizing certificates out of the package” with “every Pod must hold the public domain certificate”. Place each identity on the component that terminates TLS.

## 17. File Uploads and Temp Storage with Multiple Replicas

~~~text
Client -> LB
          |-> Pod A: /tmp/uploads/file-X
          '--> Pod B: /tmp/uploads/ does not have file-X
~~~

Moving uploads to `/tmp` separates them from the JAR, but **does not guarantee data visibility**. If a GET hits Pod B, it can return 404. If the contract requires durable/shared files, use object storage, a shared PVC with the appropriate access mode, database metadata, and retention/backup policies.

### 17.1. Upload Interrupted by Crash Mid-Transfer

The lab controller writes directly to the target path, so a crash can leave a partial file. A production pipeline can do:

~~~text
Upload request
  -> stage temporary file (same FS as final if atomic move is desired)
  -> validate size/type/hash/scan/quota
  -> finalize (atomic move when supported by filesystem)
  -> commit metadata
  -> return success per durability contract
~~~

Do not assume `Files.move(..., ATOMIC_MOVE)` works across two different volumes such as `emptyDir` and a PVC. With object storage, multipart upload/finalize has different semantics. Implement cleanup/expiration of incomplete uploads and auditing.

### 17.2. Preventing Upload Abuse

- Use a server-generated UUID instead of the client's original filename.
- Store outside `static`/`public`; on download, enforce authorization and `Content-Disposition`.
- Enforce request/file size limits, concurrent upload limits, rate limits, and disk quotas.
- Do not trust client-supplied MIME types/extensions; scan/validate when the domain requires it.
- Mitigate symlink/path traversal via storage layout/permissions and UUID paths.
- Apply retention, backups, and encryption at rest to user-uploaded data per policy.

## 18. Secret Rotation and Config Reload: Do Not Misinfer Behavior

Three distinct mechanisms exist:

| Change | Expectation |
| --- | --- |
| Editing external `application.properties` | Spring normally does not rebind all beans automatically; restart/refresh per designed mechanism |
| Updating a mounted Kubernetes Secret file | K8s can update the projection; the app may not automatically re-read it |
| Updating a file-backed PEM SSL bundle with `reload-on-update` | Can reload with supported Tomcat/Netty consumers + watcher; must test in real environment |

**Do not equate** dynamic TLS bundle reload with dynamic updates of `spring.datasource.password`, `server.port`, `app.storage.root`, or arbitrary `@ConfigurationProperties`. Changing the server port almost always requires restarting the web listener, not just editing a text file.

A safe rotation workflow:
1. Stage the new cert/key/config with proper permissions and validate first.
2. Swap atomically/controlled to prevent a window of certificate/key mismatch.
3. Verify certificate SAN/expiry/trust chain and a new handshake.
4. Perform a rolling restart if hot reload is not supported/guaranteed.
5. Monitor health, 5xx errors, and TLS alerts, and keep a rollback plan.

## 19. File Permissions and Non-Root Processes

In production:
- `/opt/myapp/app.jar`: read-only to the process.
- `/etc/myapp/config`: read-only.
- `/etc/myapp/tls/server.key`: readable only by the service identity, never logged.
- `/var/tmp/myapp`: service has read/write/delete; bounded by quotas and cleanup.
- `/var/lib/myapp/uploads`: service has appropriate write permissions; if shared storage, enforce owner/ACL.
- Logging: prefer stdout, or an external logs directory with retention policies.

### 19.1. Do Not Use chmod 777 to Fix Errors

On `AccessDeniedException`:
1. Check process UID/GID and permissions on **all parent directories**.
2. Check Kubernetes volume `readOnly`/read-only rootFS, `fsGroup`, ACLs, and SELinux/AppArmor.
3. Check disk quotas, storage limits, and file inode exhaustion.
4. Check current working directory and absolute vs relative paths.
5. Check secret projection mode/`subPath` updates.

`chmod -R 777` exposes secrets and upload data to unnecessary read/write access. Fix identity/permissions and mounts rather than making the entire filesystem writable.

### 19.2. Certificate/Key Integrity Matters Too

Even though a CA certificate is not confidential, an attacker modifying the truststore could make the app trust a rogue endpoint. Protect **integrity** of truststores/CA bundles using read-only mounts, checksums/signatures, and RBAC.

## 20. Troubleshooting Startup, HTTPS, Multipart, and Storage Errors

| Symptom | Likely cause to check | Resolution |
| --- | --- | --- |
| `FileNotFoundException` on TLS | Wrong `file:` path or unmounted volume | Inspect actual paths and mounts |
| `AccessDeniedException` on key | UID/GID/mode/`fsGroup`/SELinux | Grant minimal read permission |
| Keystore password error | Wrong PKCS12/JKS type or password | Verify keystore with `keytool`; do not log secrets |
| `PKIX path building failed` | Missing client truststore/CA | Configure outbound trust properly |
| Hostname/SAN mismatch | Cert lacks matching hostname | Reissue cert with proper SAN, never trust-all |
| HTTPS not active after adding prod config | Wrong `spring.config.additional-location` or profile | Verify external config load and effective port |
| HTTP request sent to HTTPS port | Scheme mismatch | Use HTTPS and matching port |
| Cert updated but app still serves old cert | SSL reload unsupported/watcher missed event | Test new handshake, rolling restart |
| App fails Config Data import | Missing mandatory location/secret | Mount before startup, check prefix |
| Unresolved placeholder | Wrong env var or `configtree` key | Compare property names and source precedence |
| Upload 500 | `tmp` location unwritable or disk full | Check Servlet multipart spool/quota |
| Upload >5MB | Multipart file-size limit | Adjust policy; do not remove limits completely |
| WebFlux multipart path ignored | Wrong stack or using `PartEvent` | Match config to stack and handle streams explicitly |
| Tomcat temp creation failure | `basedir`/JVM temp read-only | Mount writable scratch |
| Data disappears after Pod replacement | Stored in `emptyDir`/writable layer | Use PVC/object storage |
| Pod A uploaded, Pod B cannot see it | Per-Pod private filesystem | Shared durable store |
| `No space left on device` | Ephemeral/durable disk full | Quotas, cleanup, monitoring |
| New config has no effect | Boot does not auto-rebind | Restart or supported refresh |
| `/actuator/env` exposes values | Overly broad debug/config exposure | Restrict security/exposure |
| Unsure where files are saved | Relative path shifted with `WorkingDirectory` | Configure absolute paths, safe structured logging |

### 20.1. Diagnostic Order

~~~text
Startup fail?
  +--> Property sources loaded properly?
  +--> Cert/key exist, readable, right format?
  +--> Temp/Tomcat base writable?
  '--> Server port/TLS configuration valid?

Upload fail?
  +--> Request exceeds multipart limit?
  +--> Multipart spool has free space?
  +--> Business output writable/durable?
  '--> Name/path validation + cleanup?

TLS handshake fail?
  +--> Protocol/port/scheme?
  +--> SAN/chain/expiry/trust?
  '--> Certificate reload state and ingress termination?
~~~

Never “fix” issues by disabling TLS verification, printing keys to logs, running `chmod 777`, or removing disk quotas. Those only mask root causes or make deployments insecure.

## 21. Exercises and Smoke Tests

### Exercise 1 — One JAR, Two Environments

Build once with Maven. Run HTTP `8080` using local `APP_DATA_DIR`/`APP_TMP_DIR`; then restart the exact same JAR with `--spring.profiles.active=prod` and `--spring.config.additional-location=file:./runtime/config/` to serve HTTPS `8443` with external certs. Verify zero bytecode changes and no rebuild.

### Exercise 2 — Directory Permission Test

Point the temp path to a folder where the service user lacks write permission. Send a multipart upload to observe failure in the spool layer, then restore proper UID/GID/permissions. Never run destructive tests on shared production nodes.

### Exercise 3 — Mandatory Private Key

Set `server.ssl.bundle=web` with an incorrect private-key path and start the app. Record the error safely (without printing keys). Fix the secret mount/path and verify with `curl --cacert`. Never disable TLS to keep a public service running temporarily.

### Exercise 4 — configtree Secrets

Mount `db.password` into `/run/secrets/myapp`, configure `spring.config.import=configtree:/run/secrets/myapp/`. Write a test verifying the property exists/binds **without printing its value**. Remove the required directory to verify fail-fast behavior.

### Exercise 5 — WebFlux vs MVC

In a separate WebFlux project, test `spring.webflux.multipart.file-storage-directory` with a file larger than `max-in-memory-size`; then switch to `Flux<PartEvent>` and explain why the temp property no longer applies. Contrast with MVC's `spring.servlet.multipart.location`.

### Exercise 6 — Secret Rotation

Generate a second local cert with a valid SAN, swap the external PEM pair via controlled update, test Tomcat/Netty `reload-on-update`, and verify a new handshake. If the watcher does not support the mount topology, perform a rolling restart and document the limitation.

### Exercise 7 — Docker/Kubernetes Persistence

Run the app with ephemeral temp + durable PVC/object storage. Upload a file, restart/replace the Pod, and verify old temp is not guaranteed to persist while durable files remain. With 2 replicas, a GET to either replica must read the shared file if the contract requires it.

## 22. Self-Check Questions

**1.** Why should private keys not live in `src/main/resources`?

**2.** How do `classpath:` and `file:` differ?

**3.** How do `spring.config.location` and `spring.config.additional-location` differ?

**4.** When should you use `optional:`? Why should a required secret not be optional?

**5.** How does `configtree:` turn filenames into property names? Does it automatically hot-reload `DataSource`?

**6.** Do `server.ssl.certificate` and `server.ssl.certificate-private-key` configure the client or server side?

**7.** Can you combine `server.ssl.bundle` with discrete `server.ssl.key-store`/`server.ssl.certificate`?

**8.** Is `reload-on-update` guaranteed to work with every embedded server and Kubernetes Secret projection?

**9.** Are `java.io.tmpdir`, `spring.servlet.multipart.location`, `spring.webflux.multipart.file-storage-directory`, and `app.storage.root` the same property?

**10.** Why is the MVC multipart location not a permanent user upload directory?

**11.** When using `PartEvent` streaming, does WebFlux `multipart.file-storage-directory` take effect?

**12.** With a read-only container root filesystem, where are writable mounts needed?

**13.** Is a file uploaded into `emptyDir` durable across Pod replacement?

**14.** If Pod A writes a file locally and Pod B receives the GET request, what can happen?

**15.** When TLS terminates at the ingress, must the app mount the public server key?

**16.** On a cert SAN mismatch, should you disable hostname verification?

**17.** Why are absolute paths safer than relative paths in production?

**18.** What is the risk of passing passwords in CLI args or env dumps?

**19.** Why scan JAR/image layers even when `.dockerignore` is configured?

**20.** How must an upload controller handle a user sending `../filename`?

**Answers:**

1. It gets packaged into the JAR/image, risking leaks and making per-environment rotation hard.
2. `classpath:` resolves packaged/application classpath resources; `file:` points to an external filesystem file.
3. `location` replaces default locations; `additional-location` appends to them.
4. Use for optional config; missing required secrets should fail fast.
5. Filenames become property names and file contents become values; does not automatically rebind `DataSource`.
6. Server-side TLS identity; outbound client trust is separate.
7. No, per the Boot 3.3 SSL bundle contract.
8. No; depends on supported Tomcat/Netty consumers, watchers, and volume behavior.
9. No: JVM temp, Servlet spool, WebFlux spool, and durable storage serve different purposes.
10. Spool files can be cleaned right after the request; use separate storage for durable data.
11. No; docs note it is ignored with `PartEvent` streaming support.
12. JVM/temp, multipart spool, Tomcat work dirs, and business data writable; config/TLS read-only.
13. Not guaranteed; `emptyDir` is tied to the Pod lifecycle.
14. Pod B may return 404; use a shared durable store.
15. No, if TLS terminates only at ingress and the internal HTTP hop is permitted.
16. No; fix the certificate SAN/CA/hostname.
17. Independent of current working directory and easier to audit/mount/apply quotas.
18. Process introspection, logs, shell history, and crash diagnostics can expose secrets.
19. Private keys may already have been packaged into the JAR/`src` resources or earlier build layers.
20. Never use the client filename as a path; generate a server-side ID/name and enforce authorization.

## 23. Pre-Production Checklist

- [ ] Build a single immutable JAR/image; do not package private keys, passwords, or upload data.
- [ ] Scan Git history, JARs, and container image layers for secrets.
- [ ] Separate external config, Secret volumes, writable temp, and durable storage.
- [ ] Configure `spring.config.additional-location`/`spring.config.import` and precedence properly.
- [ ] Mount required secrets before startup; never supply real default passwords.
- [ ] Verify certs have proper SAN/expiry/chain/key and minimal file permissions.
- [ ] Use **one** server SSL approach: either discrete `server.ssl.*` or `server.ssl.bundle`.
- [ ] Do not confuse server SSL identity with outbound HTTP client CA/trust.
- [ ] Test `reload-on-update`/rolling restart and TLS handshakes after rotation.
- [ ] Point JVM `-Djava.io.tmpdir` to a writable volume.
- [ ] Keep MVC `spring.servlet.multipart.location` writable with file/request size limits.
- [ ] Match WebFlux `spring.webflux.multipart.file-storage-directory` to the stack; `PartEvent` has its own lifecycle.
- [ ] Place Tomcat `basedir`/access logs and application logs appropriately.
- [ ] Keep business uploads outside static/public web roots with authz/quotas/scanning.
- [ ] Store durable files on storage with backups, retention, and multi-replica visibility.
- [ ] Test non-root UID/GID, `fsGroup`, permissions, SELinux, and `readOnlyRootFilesystem`.
- [ ] Keep raw secrets out of ConfigMaps; apply RBAC/encryption/auditing to Kubernetes Secrets.
- [ ] Monitor/enforce quotas for ephemeral disk, inodes, concurrent uploads, and cleanup.
- [ ] Never expose Actuator `env`/`configprops` publicly; never log secrets.
- [ ] Smoke test the exact artifact with HTTP/HTTPS and external mounts.
- [ ] Maintain runbooks for missing files, permission denied, wrong port, expired certs, and disk full.
- [ ] Have a redeploy/rollback plan whenever config or certs change.

## 24. Official References

1. Spring Boot 3.3 — Externalized Configuration (Config Data, `additional-location`, `configtree`, placeholders): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
2. Spring Boot 3.3 — SSL Bundles, PEM/JKS, `reload-on-update` (Tomcat/Netty): https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
3. Spring Boot 3.3 — Embedded Web Servers, HTTPS, discrete PEM/keystore, and SSL bundles: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
4. Spring Boot 3.3 — Common Application Properties, multipart/Tomcat temp: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
5. Spring Framework — Servlet Multipart: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html
6. Spring Framework — WebFlux Multipart: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
7. Kubernetes ConfigMaps: https://kubernetes.io/docs/concepts/configuration/configmap/
8. Kubernetes Secrets: https://kubernetes.io/docs/concepts/configuration/secret/
9. Kubernetes Volumes and `emptyDir`: https://kubernetes.io/docs/concepts/storage/volumes/
10. Kubernetes Persistent Volumes: https://kubernetes.io/docs/concepts/storage/persistent-volumes/
11. Kubernetes `ephemeral-storage` limits: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/#local-ephemeral-storage
12. Kubernetes Security Context: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
13. Docker Bind Mounts: https://docs.docker.com/engine/storage/bind-mounts/
14. Docker Volumes: https://docs.docker.com/engine/storage/volumes/
15. Java 17 Files APIs: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
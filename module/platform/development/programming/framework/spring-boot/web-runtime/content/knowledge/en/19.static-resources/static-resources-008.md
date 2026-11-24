# Distinguishing classpath resources from files external to the application

## 1. Two resource sources that look similar yet have different lifecycles

In Spring Boot, an application commonly has both **resources on the classpath** and **files on the filesystem external to the application**. Both can be HTML, CSS, JavaScript, images, JSON, CSV, or plain text files, yet how they are located, packaged, read, exposed over HTTP, and updated differs significantly.

Examples:
- **Classpath:** **`src/main/resources/static/logo.svg`** is packaged into the artifact at build time; when running the JAR, it normally resides at the logical path **`BOOT-INF/classes/static/logo.svg`** inside the JAR.
- **External:** **`/srv/myapp/public/logo.svg`** is deployed or mounted onto the host/container independently of the JAR; updating this file does not require modifying the bytes of the JAR.
- **Being on the classpath does not make a file public:** **`src/main/resources/private/messages.txt`** can be read by the application using `ClassPathResource`, yet Spring Boot **does not automatically expose it as an HTTP URL**.
- **Being an external file does not make it HTTP-accessible:** an external file is only served if the application or proxy has an appropriate mapping or endpoint and permissions allow access.

Lesson goals: pick the right storage location for the purpose; understand **`classpath:`** and **`file:`** prefixes; grasp Spring Boot's static content rules; use Spring `Resource` to read safely after JAR packaging; deploy external files cleanly across environments; and prevent permission, path, caching, or stale-data issues.

Primary example scope: **Spring Boot 3.3.x, Java 17+, Spring MVC, executable JAR**. Spring WebFlux also supports static resources via `WebFluxConfigurer`/WebFlux resource handlers; do not copy Servlet `WebMvcConfigurer` code directly to WebFlux.

## 2. Quick comparison table

| Criterion | Classpath resource | File external to the application |
| --- | --- | --- |
| Typical location during development | `src/main/resources/...` or resources from dependency JARs | Operations-chosen folder, volume, disk, upload directory |
| When packaged as an executable JAR | Typically embedded in `BOOT-INF/classes` or dependency JARs | Not embedded automatically unless build config packages it |
| How referenced in Spring | `classpath:static/app.css`; `ClassPathResource` | `file:/srv/myapp/public/app.css`; `FileSystemResource`; `Path` |
| Backed by `java.io.File`? | **Not guaranteed**, especially inside a JAR | Usually has a physical path on the filesystem |
| Updating content | Usually requires building and redeploying a new artifact | Can change externally; app/caches must reload to see updates |
| Write permissions | Treat packaged JAR/classpath contents as read-only | Readable/writable depending on OS permissions and app policy |
| Execution directory dependence | Primarily depends on class loader and artifact | Relative paths depend on working directory; absolute paths depend on environment |
| Multi-replica deployment | Every replica runs the same artifact version when deployed uniformly | Requires shared mounts or synchronization by design |
| Default HTTP exposure | Only static locations configured by the framework | Not public without a dedicated resource mapping |
| Best suited for | Assets versioned alongside code: CSS, JS, icons, templates, sample files | Independently updated assets, ops-managed files, user uploads |

**Rule of thumb:** resources that belong to a **software release version** should be packaged; resources that represent **environment-specific or post-deploy mutable data** should be managed externally, typically via a volume or object storage. Decisions also depend on access control, data lifecycle, and scaling requirements.

## 3. What is the classpath really?

The **classpath** is the set of locations the Java class loader uses to locate classes and resources at runtime. Locations can be classes directories, the application JAR, or dependency JARs. The classpath is **not synonymous** with the current working directory and is not necessarily a directory traversable via `java.nio.file.Path`.

In standard Maven/Gradle projects, files under **`src/main/resources/`** are copied into resources/classes output during build. When packaged as a Spring Boot executable JAR, contents normally appear under **`BOOT-INF/classes/`**. Example:

~~~text
src/main/resources/
├── static/
│   ├── index.html
│   └── css/site.css
├── private/
│   └── labels.txt
└── application.yml
~~~

Once packaged, these resources travel with the release; startup loads them through the application's class loader. The path **`src/main/resources/static/index.html`** is meaningful only in the source tree. In a production JAR, **never** open files with:

~~~java
// WRONG when relying on the source tree still existing:
Files.readString(Path.of("src/main/resources/private/labels.txt"));
~~~

That call might happen to succeed when launched from the project root on a dev machine, yet once the standalone JAR is deployed, **`src/main/resources`** no longer exists. A relative filesystem path does not become a classpath path.

### 3.1. Properly reading resources packaged inside a JAR

Use **`ClassPathResource`** or **`ResourceLoader`**:

~~~java
Resource resource = new ClassPathResource("private/labels.txt");
try (InputStream stream = resource.getInputStream()) {
    String content = new String(
            stream.readAllBytes(), StandardCharsets.UTF_8
    );
    System.out.println(content);
}
~~~

This is a **fragment**: it requires importing `Resource`, `ClassPathResource`, `InputStream`, `StandardCharsets`, and handling `IOException` in the method; it is not a standalone program. **`getInputStream()`** reads the resource even when it is an entry inside an unextracted JAR. Close streams with try-with-resources.

An equivalent pattern with Spring's `ResourceLoader`:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:private/labels.txt"
);
try (InputStream stream = resource.getInputStream()) {
    // Process content incrementally or read all bytes if the file is small.
}
~~~

### 3.2. Why does `resource.getFile()` often fail after packaging?

**`ClassPathResource.getFile()`** works only when the classpath resource resolves to a physical file on disk. When a file resides **inside a JAR**, there is usually no separate `java.io.File` for it, so `getFile()` can throw **`FileNotFoundException`** (or a corresponding `IOException` along the call chain). This is a classic bug: code passes in the IDE because output classes sit in a real directory, then breaks when run with **`java -jar`**.

~~~java
// UNRELIABLE when the resource is inside an executable JAR:
File file = new ClassPathResource("private/labels.txt").getFile();
~~~

Replace with **`getInputStream()`**; for large data, stream instead of loading everything into RAM. If a third-party library strictly requires a **`Path`/`File`**, you can copy the resource contents to a temporary file with explicit lifecycle/cleanup, though look for an `InputStream` API first. Never rely on unpacking the whole JAR as a workaround.

**Note:** `ClassPathResource.getURL()` usually returns an accessible URL for the resource, including JAR URLs; that does not mean the URL can be converted into a filesystem path for `Path.of(...)`.

## 4. External files: Path, filesystem, mounts, and permissions

An **external** file is identified by a filesystem path, for example:

~~~text
Linux:   /srv/myapp/public/banner.txt
Windows: C:/apps/myapp/public/banner.txt
Local:   ./public-runtime/banner.txt
~~~

An **absolute path** specifies the exact location on the host/container running the process. A **relative path** like **`./public-runtime`** is normally resolved against the JVM process's **working directory (`user.dir`)**, not relative to the JAR's directory and not relative to `src/main/resources`.

For example, launching the exact same `application.jar` from two different directories makes **`./public-runtime/banner.txt`** point to two different places. Therefore, in deployment environments, pass absolute paths via environment/configuration or mount volumes at stable paths.

Java NIO reading an external file:

~~~java
Path path = Path.of("/srv/myapp/public/banner.txt");
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

This fragment illustrates execution on an OS containing that path; if the file is absent or permissions deny access, `Files.readString` throws `IOException`. For large files, use `Files.newInputStream` or streaming APIs.

### 4.1. Distinguishing files and storage backends

- **Files in a disk/container writable layer:** can vanish when a container is replaced or a Pod is deleted.
- **Persistent volumes:** data outlives the process/container lifecycle, yet still depends on provisioning, mount, and sharing policies.
- **Object storage (S3-compatible, GCS...):** accessed over APIs, **not naturally a `Path`**. Never pass object URLs to `FileSystemResource` as if they were local files.
- **Shared network filesystems:** require accounting for latency, permissions, synchronization, locking, availability, and caching.

External files can change at runtime, yet **data already read and cached in RAM by the application** will not reflect updates without reloading; browser/proxy caches may also continue returning stale assets.

## 5. Spring's Resource abstraction: a unified read interface without erasing physical differences

**`org.springframework.core.io.Resource`** abstracts resource access. Key methods:

- **`exists()`**: indicates whether the resource exists at check time; between `exists()` and opening the stream, a file can still be deleted or modified (race condition).
- **`getInputStream()`**: opens a read stream; the caller is responsible for closing it.
- **`contentLength()`**: returns size if supported by the implementation, potentially performing I/O.
- **`lastModified()`**: modification timestamp when obtainable; not all resource types support it identically.
- **`getFilename()`**: logical filename of the resource, not a safe absolute `Path`.
- **`getFile()`**: usable only if the resource is genuinely a physical file.
- **`createRelative(...)`**: resolves relative paths per implementation; do not assume identical rules across all `Resource` types.

Common implementations:

| Type | Used for | Key notes |
| --- | --- | --- |
| `ClassPathResource` | Files on the classpath (potentially inside JARs) | Prefer `getInputStream()`; `getFile()` is not guaranteed |
| `FileSystemResource` | Files from the filesystem | Provides `Path`/`File`; subject to OS and filesystem permissions |
| `PathResource` | Resources backed by `java.nio.file.Path` | Fits NIO well; can also write when permitted |
| `UrlResource` | URLs like `file:` or `https:` | Remote URLs involve networking, timeouts, and security |
| `ServletContextResource` | Paths relative to the web application context | Not synonymous with classpath; WAR/JAR behavior differs |
| `ByteArrayResource` | In-memory `byte[]` content | Usually re-readable; consumes proportional RAM |
| `InputStreamResource` | Pre-opened stream | Typically single-read; cannot be re-read like ordinary descriptors |

**`ResourceLoader`** understands explicit prefixes:

~~~text
classpath:private/labels.txt
file:///srv/myapp/public/banner.txt
https://example.org/sample.txt
~~~

Never pass a bare, unprefixed path and guess what Spring will do. Interpreting **unprefixed** paths can depend on the `ApplicationContext` type, the API called, and how resources are resolved. To make intent explicit, use **`classpath:`** or **`file:`**, or instantiate `ClassPathResource` / `FileSystemResource` directly.

**`classpath*:`** is intended for scanning multiple pattern-matched resources (e.g., `PathMatchingResourcePatternResolver`). It is not equivalent to a normal single resource, and wildcard scanning across multiple JARs has classloader limitations; use it only when you genuinely need to aggregate multiple matches.

## 6. Where does Spring Boot serve static resources automatically?

In **Spring MVC**, Spring Boot searches static content by default in these classpath locations:

1. **`classpath:/META-INF/resources/`**
2. **`classpath:/resources/`**
3. **`classpath:/static/`**
4. **`classpath:/public/`**

In Servlet applications, the `ServletContext` root can also be served. Exact precedence on filename collisions depends on resource location settings and app configuration; **avoid creating multiple files mapping to the same URL path** across locations.

Common URL examples under default configuration:

| Packaged file | Accessible URL |
| --- | --- |
| `src/main/resources/static/index.html` | `GET /` and `GET /index.html` under default welcome page handling when not overridden by another route |
| `src/main/resources/static/css/site.css` | `GET /css/site.css` |
| `src/main/resources/public/images/logo.svg` | `GET /images/logo.svg` |
| `src/main/resources/private/labels.txt` | **Does not automatically expose `GET /private/labels.txt`** |

Notes:
- **A resource being on the classpath** does not mean it is a **public HTTP resource**. Boot maps only static locations by default; never place secrets or configuration files in public areas.
- HTTP URLs omit the static directory prefix on the classpath. A file at **`static/css/site.css`** maps to **`/css/site.css`**, not **`/static/css/site.css`**.
- **`src/main/webapp`** is mainly for WAR/Servlet deployments; **do not use it** for static assets in executable JARs.
- In WebFlux, Boot uses the corresponding resource handler and the URL pattern property **`spring.webflux.static-path-pattern`**; this lesson's examples use MVC with **`spring.mvc.static-path-pattern`**.

### 6.1. Changing spring.web.resources.static-locations

You can replace the list of static lookup locations, for example (illustrated for Linux):

~~~yaml
spring:
  web:
    resources:
      static-locations:
        - "classpath:/static/"
        - "file:/srv/myapp/public/"
~~~

**The declared locations replace the default list**; if you still want classpath assets, list them explicitly. Directory locations need a trailing **`/`**. `file:` paths above tie to the actual OS/container filesystem; the directory must exist with read permissions. With this setup, both locations map onto the root URL **`/`**, increasing collision or accidental exposure risks.

If you only need to expose an external folder under its own prefix, consider **`WebMvcConfigurer.addResourceHandlers`** for a clear URL like **`/public-files/**`**. There is no need to overwrite all `static-locations` in that case.

### 6.2. Changing only the URL pattern without moving files

~~~yaml
spring:
  mvc:
    static-path-pattern: "/assets/**"
~~~

This changes the default static resource URL mapping to **`/assets/**`**, without moving files from classpath to the filesystem. **`spring.mvc.static-path-pattern`** (URL) and **`spring.web.resources.static-locations`** (file source) are two separate concepts.

## 7. Runnable Java 17+ application example: two sources, three HTTP endpoints

The Spring Boot 3.3.x + Spring MVC example below demonstrates simultaneously:

1. A file under **`classpath:/static/`** served automatically over HTTP.
2. A file under **`classpath:/private/`** read by a Controller via `getInputStream()`, without being auto-published.
3. A file outside the JAR in **`./public-runtime/`** accessed via `Path` and published through a **dedicated resource handler**.

### 7.1. Project tree

~~~text
resource-origins/
├── pom.xml
├── public-runtime/
│   └── notice.txt
└── src/
    └── main/
        ├── java/com/example/resources/
        │   └── ResourceOriginsApplication.java
        └── resources/
            ├── application.yml
            ├── private/message.txt
            └── static/style.txt
~~~

**`public-runtime/`** sits **outside `src/main/resources`** and outside the artifact; this folder/file must be created separately in the deployment environment.

**`pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>resource-origins</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**`src/main/resources/application.yml`:**

~~~yaml
server:
  port: 8080

demo:
  external-root: ./public-runtime
~~~

Configuring `external-root` as a **relative path** illustrates local execution. In production, override it with an absolute path or stable mount.

**`src/main/resources/static/style.txt`:**

~~~text
Bundled public v1
~~~

**`src/main/resources/private/message.txt`:**

~~~text
Bundled private v1
~~~

**`public-runtime/notice.txt`:**

~~~text
External public v1
~~~

### 7.2. Complete Java code

**`src/main/java/com/example/resources/ResourceOriginsApplication.java`:**

~~~java
package com.example.resources;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class ResourceOriginsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceOriginsApplication.class, args);
    }
}

@Configuration
class ExternalStaticConfig implements WebMvcConfigurer {
    private final Path publicRoot;

    ExternalStaticConfig(@Value("${demo.external-root}") String root) {
        this.publicRoot = Path.of(root).toAbsolutePath().normalize();
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        String location = publicRoot.toUri().toString();
        if (!location.endsWith("/")) {
            location += "/";
        }
        registry.addResourceHandler("/public-files/**")
                .addResourceLocations(location);
    }
}

@RestController
class CompareResourcesController {
    private final Resource bundled = new ClassPathResource(
            "private/message.txt"
    );
    private final Path externalFile;

    CompareResourcesController(
            @Value("${demo.external-root}") String root
    ) {
        Path dir = Path.of(root).toAbsolutePath().normalize();
        this.externalFile = dir.resolve("notice.txt");
    }

    @GetMapping(
            path = "/api/compare",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    String compare() throws IOException {
        String bundledText;
        try (InputStream stream = bundled.getInputStream()) {
            bundledText = new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8
            ).strip();
        }

        String externalText = Files.readString(
                externalFile, StandardCharsets.UTF_8
        ).strip();

        return "classpath=" + bundledText
                + "\nfilesystem=" + externalText + "\n";
    }
}
~~~

In the Java code above:
- **`ClassPathResource`** reads the packaged resource regardless of whether files reside outside or inside a JAR.
- **`Path`** and **`Files.readString`** read the external resource; every `GET /api/compare` re-reads `notice.txt`. This demo uses tiny files so `readAllBytes` and `readString` are fine; stream larger files.
- **`WebMvcConfigurer`** adds a **`/public-files/**`** mapping to the external directory while Boot's default static handler still serves **`/style.txt`** from the classpath.
- **`Path.toUri()`** constructs an OS-appropriate **`file:`** URI instead of manually concatenating `file:/` onto Windows-style paths. The code guarantees the directory location ends with **`/`**.
- Configuration never uses user input to construct paths. If extending for dynamic downloads, never concatenate raw paths from requests; validate permissions and confine files to the allowed root.

### 7.3. Compiling and running

With the files placed according to the project tree, open a terminal in **`resource-origins/`**:

~~~bash
mvn package
java -jar target/resource-origins-0.0.1-SNAPSHOT.jar
~~~

Requires **JDK 17+**, Maven, and port 8080 free. If port 8080 is occupied, pick another port and adjust the test URLs accordingly.

From another terminal, request:

~~~bash
curl -s http://localhost:8080/style.txt
curl -s http://localhost:8080/public-files/notice.txt
curl -s http://localhost:8080/api/compare
~~~

With the sample data and all three requests succeeding, the response **bodies** in order are:

~~~text
Bundled public v1
~~~

~~~text
External public v1
~~~

~~~text
classpath=Bundled private v1
filesystem=External public v1
~~~

The lines above are **each response's body**, not full terminal stdout or HTTP headers. Use **`curl.exe`** in PowerShell if the shell's `curl` alias does not support standard flags.

Try one more request:

~~~bash
curl -i http://localhost:8080/private/message.txt
~~~

Expect HTTP **404** under the sample application's default configuration: **`private/message.txt`** is on the classpath, yet not in a published static directory. The **`/api/compare`** endpoint can read its contents because code **explicitly** reads it; that does not expose the resource at a public URL.

### 7.4. Inspecting the artifact with jar tf

Run:

~~~bash
jar tf target/resource-origins-0.0.1-SNAPSHOT.jar
~~~

The executable JAR's file list will include entries corresponding to:

~~~text
BOOT-INF/classes/application.yml
BOOT-INF/classes/private/message.txt
BOOT-INF/classes/static/style.txt
~~~

**`public-runtime/notice.txt`** is absent from the JAR because it sits outside the packaged tree in this example. Files inside the JAR can be read via `ClassPathResource.getInputStream()`, but you cannot assume **`getFile()`** yields a standalone physical file.

### 7.5. Testing post-deployment changes

**Experiment A – external file:** while the app is running, update **`public-runtime/notice.txt`** to:

~~~text
External public v2
~~~

Call **`GET /api/compare`** again. Because the code calls `Files.readString` on **every request**, **`filesystem=External public v2`** appears without rebuilding the JAR (assuming the app points to the right directory). Similarly, `GET /public-files/notice.txt` can show the new content, though depending on cache headers, browsers or reverse proxies may serve cached copies; use `curl` or bypass client caching when testing.

**Experiment B – classpath file:** edit **`src/main/resources/static/style.txt`** after the JAR was built, then call `GET /style.txt` against the running old JAR process. The content **does not change automatically** because the file was snapshotted into the artifact. You must **build a new JAR and run/deploy the new version** to update bundled static assets. When running from IDE classpath output, classpath resource behavior can differ; run **`java -jar`** to reflect production artifacts.

**Experiment C – working directory:** run the exact same JAR from a different working directory. The path **`./public-runtime`** now points to the new directory, so `/api/compare` may fail if `notice.txt` is missing there, and `/public-files/notice.txt` may return 404. For stability, override configuration with an absolute path:

~~~bash
java -jar target/resource-origins-0.0.1-SNAPSHOT.jar --demo.external-root=/srv/myapp/public
~~~

The **`/srv/myapp/public`** path is a Linux example; create the directory, place `notice.txt` there, and grant read permissions. On Windows, use a valid absolute path such as **`C:/apps/myapp/public`**, quoted if it contains spaces.

## 8. Commonly confused configuration concepts

### 8.1. Filesystem location differs from public URL

In Spring:
- **`classpath:static/style.txt`** is an internal resource-resolution path; it is not an HTTP URL.
- **`file:///srv/myapp/public/style.txt`** identifies a file on the host/container; it also does not automatically become an HTTP URL.
- **`GET /public-files/style.txt`** is an HTTP route that only works when a handler or proxy maps it to a resource.

The **`/public-files/`** URL prefix is designed by the application; it does not have to match the physical folder name.

### 8.2. Packaged application.yml differs from external configuration

**`src/main/resources/application.yml`** normally resides on the classpath and holds default application settings. Spring Boot loads configuration from multiple sources, including external files and environment variables, with defined precedence rules. That is **ConfigData configuration**; it is unrelated to static file serving.

For example, **`spring.config.additional-location`** can supply extra config sources for the application, yet **does not** automatically serve those config files over HTTP. Conversely, pointing `static-locations` directly at a directory containing secrets or configs risks unintended data exposure.

Distinguish:
- **Runtime configuration:** prefer config/environment/secret managers with narrow access permissions.
- **Public static assets:** store only content intentionally approved for public reading.
- **Business data:** store in databases, object storage, or protected filesystems and serve via controlled APIs when needed.

### 8.3. Resources inside dependency JARs

The classpath can include files from **dependency JARs**, not only the main project. When multiple JARs contain the same resource path, the class loader picks one according to classpath order; behavior may differ between IDEs and executable JARs. Avoid unnecessary path collisions. When you must load multiple matching resources, consider a pattern resolver and test inside the real packaged artifact.

### 8.4. Do not confuse classpath resource with classpath* glob

The **`classpath:`** prefix normally resolves a single named resource. The **`classpath*:`** prefix is used by resolvers capable of finding multiple pattern-matched resources. It does not turn external files into classpath resources, and wildcards inside JARs/custom classloaders have limitations. Do not use globs to “list directories inside a JAR” as if scanning a normal filesystem.

## 9. Security when exposing external file directories

Opening a directory over HTTP has immediate consequences: any file within the mapped scope becomes accessible unless restricted by an appropriate security layer. Treat that directory as a **public directory**, never using it for secrets or internal data.

1. **Limit the root:** map only a dedicated directory reserved for approved public data. Avoid broad roots like **`/`**, **`C:/`**, home directories, or config directories.
2. **Never concatenate arbitrary user paths:** e.g., **`Path.of(root, requestParam)`** is unsafe when users pass **`../`**, absolute paths, or alternate encodings. When building file-reading APIs, resolve and normalize, verify containment under the permitted root, enforce authentication/authorization, restrict file types and sizes, and account for symlinks and concurrent modifications.
3. **Manage symlinks:** a symlink inside a public directory pointing outside can leak files depending on filesystem and resolver policies. Never treat URL string checks as path containment after symlink resolution.
4. **Least-privilege OS permissions:** web processes typically need only **read** access to public static directories. Separate upload/write folders from public folders, using appropriate service users and mounts.
5. **Do not publish uploads immediately upon receipt:** validate actual file types, formats, sizes, malware, filenames, and permissions. To serve user uploads, use an authorized endpoint or storage with signed URLs rather than mapping an entire upload folder as `/**`.
6. **Caching and headers:** set appropriate `Cache-Control`, content types, `Content-Disposition`, `X-Content-Type-Options`, and CSP policies; prevent user-controlled content from executing unexpectedly on a trusted origin.
7. **Do not confuse route names with protection:** a **`/private/`** prefix in a URL does not make files private. Security comes from execution permissions and access control; contents under **`classpath:/static/private/`** can still be publicly served.

In the example above, `/public-files/**` is only for `notice.txt` and approved assets. Never put passwords, tokens, database dumps, `.env` files, or config copies into **`public-runtime/`**.

## 10. Caching, reloading, and packaging mechanics

### 10.1. Updated resources are not automatically seen immediately by clients

Stale data can live in three places:
- **Build artifact:** classpath resources are snapshotted inside the JAR; updates require a new artifact version.
- **Application memory:** an app may read an external file at startup into a singleton or cache; editing the external file will not refresh in-memory objects automatically.
- **HTTP cache:** browsers, CDNs, or proxies use `Cache-Control`, `ETag`, `Last-Modified`, and conditional requests; fresh caches may skip fetching updates.

For versioned classpath assets like CSS/JS, content-hashed URLs permit long caching while refreshing on deployment. For external assets updated at the same URL, pair updates with invalidation/revalidation or URL versioning. Never set a very long TTL on frequently changing files served at fixed URLs.

### 10.2. Atomic updates for critical external files

If a large file is overwritten in place while the server serves it, clients may read **partial contents**. Common practice: write to a temporary file on the same filesystem, verify contents, then perform an atomic rename/replace where supported by the OS/filesystem; manage permissions and rollbacks. In multi-replica deployments, replicas may observe updates at different times without a shared distribution/synchronization mechanism.

### 10.3. Relationship to Docker/Kubernetes

In containers, **files inside the JAR or image** belong to the release. When a Pod or Container is replaced, data written to the container's writable layer does not necessarily survive. For external files with longer lifecycles:
- Use **volumes/PVCs** or object storage as needed.
- Mount at a stable absolute path, such as **`/srv/myapp/public`**.
- Pass the property via environment variables/args so the app points to the exact location.
- Do not assume all replicas share one filesystem.
- Set permissions aligning workload identity, container UID, and storage policies.

External volumes let content change independently of the JAR, yet require consistent provisioning, backups, permission controls, and update strategies.

## 11. Troubleshooting when dev works yet production fails

| Symptom | Common cause | How to verify and fix |
| --- | --- | --- |
| IDE reads file; `java -jar` throws `FileNotFoundException` | Called `ClassPathResource.getFile()` on a resource inside a JAR | Read via `getInputStream()`; verify with `jar tf` |
| `java -jar` cannot find `src/main/resources/...` | Used a `Path` pointing to the source tree | Use `classpath:...` or `ClassPathResource` |
| Static file returns 404 after deploy | Not packaged, wrong path, different URL mapping, or `static-locations` overridden | Run `jar tf`; verify URLs, config, and listening port |
| File exists on classpath yet `/file` returns 404 | Not in a default public static location | Place in `static`/`public` if meant to be public, or expose an endpoint |
| `GET /public-files/...` returns 404 | Wrong `external-root`, missing file, missing trailing `/` in location, or denied read permission | Print/check normalized absolute root; verify existence, permissions, and working directory |
| API reading external file returns 500 | Missing file or `IOException`/permission error | Check stack trace and mount permissions; return safe error info |
| External file updated yet browser shows stale version | Browser/CDN/handler cache or app cached copy in RAM | Check HTTP cache headers, bypass cache, check app reload |
| Works on Windows, fails on Linux | Path separators or case sensitivity differences, different directories/mounts | Use OS-independent `Path`/URI APIs; configure paths externally |
| Changing working directory loses files | Property uses a relative path | Pass an absolute path; inspect `user.dir` |
| Configuration files exposed over HTTP | Mistakenly mapped config/secret folder into `static-locations` | Separate public folder, narrow mappings, rotate exposed secrets |
| One replica returns old copy, another returns new | External files out of sync across replicas | Manage distributed storage/versioning and rollouts |

Concise diagnostic workflow:
1. Identify the **request URL** and expected **physical/logical** resource.
2. Determine whether the resource is **classpath** or **filesystem**, rather than guessing from filenames.
3. For classpath, inspect **`jar tf`** output, the class loader, and how code opens streams.
4. For external files, check the resolved **absolute path**, filesystem permissions, file size, working directory, volume mounts, and symlinks.
5. For HTTP, check static handlers/URL patterns, web ports, security, and cache headers.
6. Reproduce using the **packaged artifact** and the same working directory/mounts as production.

## 12. Self-assessment questions

**Question 1.** **`src/main/resources/static/app.js`** is built into the JAR. In production, if you only edit the file in the Git source repo and re-request the URL, does it change?

**Answer:** No, if the old JAR is still running. You must build and deploy an artifact containing the new contents; HTTP caches may also require invalidation or versioned URLs.

**Question 2.** Why does **`new ClassPathResource("private/a.txt").getInputStream()`** usually work under `java -jar`, while **`getFile()`** can fail?

**Answer:** Streams can read resources directly from JARs/classloaders, whereas `java.io.File` requires a separate physical file on the filesystem.

**Question 3.** A file is mounted at **`/srv/myapp/public/x.png`**. Can users automatically call **`GET /x.png`**?

**Answer:** No; merely existing on disk does not create an HTTP endpoint. A matching static location/resource handler/proxy and read permissions are required.

**Question 4.** Does **`spring.mvc.static-path-pattern=/assets/**`** move files from the classpath into an external directory?

**Answer:** No. That property changes the **URL pattern**; where resources are loaded from is determined by **`spring.web.resources.static-locations`** or resource handlers.

**Question 5.** A Dockerized JAR reads **`./public-runtime/notice.txt`**. When the container restarts with a different working directory, what happens?

**Answer:** The relative path resolves against the new directory and may fail to find the file. Use an absolute path/stable mount passed via configuration.

**Question 6.** If uploaded files are placed in a public external directory, is authentication still enforced on access?

**Answer:** It depends on security rules. A public static mapping may bypass per-user permission checks; private files require an authorized endpoint or protected storage mechanism.

## 13. Conclusion and adoption checklist

**Classpath resources** are tied to the class loader and artifact version; read them via `Resource.getInputStream()`, treat them as read-only, and do not assume they exist as physical files on disk. **External files** reside on a `Path`/volume/storage with an independent lifecycle; they can be updated without rebuilding the JAR, yet require managing working directories, permissions, caching, and consistency. **HTTP static resources** are intentional mappings from URLs to source locations, never implying that every resource is public.

Before deploying, confirm:
- Should the asset ship with code releases or update independently?
- Is it **`classpath:/...`** or **`file:/...`**? Verified via `jar tf` / absolute paths?
- Does code use **`getInputStream()`** when reading classpath resources inside a JAR?
- Are public URLs mapped properly without accidentally exposing folders containing sensitive data?
- Are external paths and mounts consistent across all replicas?
- Have caching, reloading, read/write permissions, and new-version rollout mechanisms been defined?
- Was it verified with **`java -jar`** in a production-like environment, not solely inside an IDE?

## Official references

- Spring Boot 3.3 — Servlet Web Applications, Static Content: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Framework — Resources (`Resource`, `ClassPathResource`, `FileSystemResource`, `ResourceLoader`): https://docs.spring.io/spring-framework/reference/core/resources.html
- Spring Framework — Spring MVC Static Resources: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html

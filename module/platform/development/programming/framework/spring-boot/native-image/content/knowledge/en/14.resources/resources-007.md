# Relative Paths, Working Directory, and Case-Sensitivity Differences

## 1. Why Can Paths Work on a Dev Machine Yet Fail in a Native Container?

Spring Boot applications frequently read classpath resources, configuration files, templates, certificates, or data from the filesystem. A common bug is a program working on a developer machine yet failing to find files when running as a GraalVM Native Image inside a container.

The cause usually lies not in the Java compiler, but in how the application resolves paths:

- Relative paths are calculated from the process's **current working directory (CWD)**.
- Classpath paths are resolved by the classloader by resource name, not by CWD.
- Linux typically distinguishes uppercase and lowercase letters in filenames; Windows is case-insensitive by default.
- A container has its own filesystem, a different layout from the host machine, and may run under a different user.
- Native executables do not automatically bring files external to the binary into the image.

In the **SPRING_BOOT_NATIVE_IMAGE** module, you need to understand these rules so resources are located consistently across the JVM, native executable, and runtime container.

## 2. Absolute and Relative Paths

An **absolute path** specifies a location from the root of a filesystem or volume:

```text
Linux:   /etc/orders/rules.json
Windows: C:\orders\config\rules.json
```

A **relative path** is interpreted relative to a contextual base directory:

```text
config/rules.json
../shared/rules.json
./data/input.csv
```

In Java, when using:

```java
Path path = Path.of("config/rules.json");
```

the relative path is typically resolved against the process's current working directory:

```java
Path absolute = path.toAbsolutePath();
System.out.println(absolute);
System.out.println("cwd = " + System.getProperty("user.dir"));
```

If the process launches from `/app`, the path may become `/app/config/rules.json`. If launched from `/`, the same relative string may become `/config/rules.json`.

Do not assume CWD is always the directory containing the JAR or native executable. CWD is determined by how the process is launched, container `WORKDIR` settings, service managers, or orchestration.

## 3. What Is the Current Working Directory?

CWD is the working directory a process uses to resolve relative paths. On Linux you can inspect it:

```bash
pwd
```

In Java:

```java
System.out.println(System.getProperty("user.dir"));
```

Example Dockerfile:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY application /app/application
COPY config/rules.json /app/config/rules.json
ENTRYPOINT ["/app/application"]
```

With `WORKDIR /app`, the default CWD when the container runs is `/app`, unless the runtime overrides the working directory. Thus, `Path.of("config/rules.json")` can point to `/app/config/rules.json`.

If you run:

```bash
docker run --workdir /tmp orders-service:1.0
```

CWD changes to `/tmp`, causing the same relative path to point to `/tmp/config/rules.json`. The application may fail even though the file still exists at `/app/config/rules.json`.

For critical data, use explicit configured paths or stable mount paths rather than relying implicitly on CWD.

## 4. Classpath Paths Do Not Depend on CWD

Classpath resources are located by the classloader, not by appending filenames to CWD.

Example:

```java
try (InputStream input =
        getClass().getResourceAsStream("/schemas/invoice.json")) {
    if (input == null) {
        throw new IllegalStateException("Classpath resource missing");
    }
    // Read data
}
```

Or Spring:

```java
Resource resource =
        new ClassPathResource("schemas/invoice.json");
```

This resource typically resides in `src/main/resources/schemas/invoice.json`, then gets copied into the build/JAR output. Whether the application runs from `/tmp` or `/app`, the classloader still searches the configured classpath.

Conversely:

```java
new File("schemas/invoice.json")
```

creates a filesystem path relative to CWD; it does not mean reading a resource inside a JAR. The two access approaches can produce different results.

In Native Image, classpath resources must also be detected by Native Image or registered via `RuntimeHints` when they cannot be inferred statically. Changing CWD does not make an already-packaged classpath resource disappear, though a resource lacking metadata may still be absent from the executable.

## 5. Case Sensitivity on the Filesystem

Filenames on Linux are typically case-sensitive:

```text
config/Rules.json
config/rules.json
```

These are two distinct paths on a standard Linux filesystem. On default Windows, they are usually treated as the same filename; macOS can use either case-sensitive or case-insensitive filesystems depending on the volume.

Code example:

```java
Path path = Path.of("config/Rules.json");
```

If the repository actually stores the file as `config/rules.json`, the code may run on Windows yet fail in a Linux container with `NoSuchFileException`.

Classpath resources must also match names exactly. For example:

```java
new ClassPathResource("Templates/invoice.html");
```

does not automatically match `templates/invoice.html` on Linux. `ClassLoader` looks up resources by name and is case-sensitive in common Linux environments.

Safe rule: standardize directory/file names to lowercase, use the exact spelling in code, and test on Linux CI.

## 6. Distinguishing Resource Paths from Filesystem Paths

| Access method | Example | Resolution rule |
|---|---|---|
| Classpath resource | `classpath:schemas/invoice.json` | ClassLoader and packaged resources |
| Relative filesystem | `config/rules.json` | Process CWD |
| Absolute filesystem | `/etc/orders/rules.json` | Root filesystem/volume |
| Spring config data | `file:/etc/orders/` | Spring Boot external configuration mechanism |
| URL resource | `https://config.example/rules.json` | Network client and remote endpoint |

Do not swap one type for another without considering its lifecycle. Classpath resources fit default data shipped with the application; external files fit configuration and data supplied at deployment time.

## 7. Using Path and Files Explicitly

For external files, you can inject the base directory or full path via configuration:

```java
@ConfigurationProperties(prefix = "orders.rules")
public record RulesProperties(Path file) {
}
```

Example application config:

```yaml
orders:
  rules:
    file: /etc/orders/rules.json
```

Service reading the file:

```java
@Service
class RulesLoader {

    private final RulesProperties properties;

    RulesLoader(RulesProperties properties) {
        this.properties = properties;
    }

    String load() throws IOException {
        Path path = properties.file();

        if (!Files.isRegularFile(path)) {
            throw new FileNotFoundException(
                    "Rules file does not exist: " + path);
        }

        return Files.readString(path, StandardCharsets.UTF_8);
    }
}
```

This keeps the path explicit and changeable per environment without rebuilding the native image. Enable configuration properties scanning or register the class with `@EnableConfigurationProperties(RulesProperties.class)`, depending on application structure.

If you want to support relative paths, define an explicit base directory instead of relying on CWD:

```java
Path base = Path.of(
        System.getProperty("orders.config-dir", "/etc/orders"));
Path rules = base.resolve("rules.json").normalize();
```

You can validate the resolved path and apply path-traversal protection if any part of the filename comes from untrusted input.

## 8. Paths Inside a Container

A container has its own filesystem namespace. Host files do not automatically appear in the container unless copied into the image or mounted.

Example:

```bash
docker run --rm \
  -v ./config:/etc/orders:ro \
  -e ORDERS_RULES_FILE=/etc/orders/rules.json \
  orders-service:1.0
```

The application reads `ORDERS_RULES_FILE` at runtime. The host directory `./config` is resolved by Docker relative to where the Docker command runs, then mounted to `/etc/orders` inside the container.

Points to verify:

- The bind mount's source path exists on the host.
- The destination path is inside the container filesystem and matches the application's configuration.
- The file is mounted with read permissions for the user running the process.
- Container CWD is not unexpectedly overridden.
- The runtime image actually has the required parent directories.

Do not use host paths like `C:\Users\...` inside Linux container configurations. Host paths are only for Docker to create the mount; the application inside the container must read the destination path.

## 9. Path Separators and Path Normalization

Windows typically displays backslashes `\`, while Linux uses `/`. Java `Path` and `Paths` help build OS-independent paths:

```java
Path config = Path.of("config", "rules.json");
```

Do not concatenate strings manually:

```java
String path = base + "\\config\\rules.json";
```

Manual string concatenation easily breaks paths on Linux. Use `resolve`:

```java
Path config = Path.of(base).resolve("config").resolve("rules.json");
```

`normalize()` removes `.` segments and some `..` pairs syntactically, but does not check file existence or prevent all symlink/path-traversal cases. If a path comes from a user, verify that the normalized path stays within the allowed directory.

For URL/classpath locations, do not manipulate them arbitrarily with `Path`. `classpath:`, `file:`, and URIs have their own rules; use the appropriate Spring `Resource` or `URI` APIs.

## 10. Interacting with Spring Boot External Configuration

Spring Boot can load config from both the classpath and the filesystem. Example:

```bash
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/orders/ ./application
```

Or specify the location via command line:

```bash
./application --spring.config.additional-location=file:/etc/orders/
```

External configuration can contain properties such as database URLs, rules paths, or feature thresholds. With Native Image, external config files are still read at runtime if Spring Boot's config data loader and the filesystem work properly.

Distinguish external config files from classpath resources. A file `/etc/orders/application.yml` does not need a `RuntimeHints` resource pattern just because Spring Boot reads it from the filesystem. Conversely, `application.yml` on the classpath must be present in the native image and packaged properly.

Do not embed credentials in classpath config or the binary. Use secret mounts/environment variables or a secret manager suited to the deployment platform.

## 11. Inspecting Paths at Runtime

When file-not-found errors happen, log non-sensitive diagnostic details:

```java
Path path = configuredPath.toAbsolutePath().normalize();

logger.info("Working directory: {}", System.getProperty("user.dir"));
logger.info("Resolved rules path: {}", path);
logger.info("Rules file exists: {}", Files.exists(path));
```

Avoid logging file contents or secrets. Useful Linux commands:

```bash
pwd
ls -l /etc/orders
stat /etc/orders/rules.json
```

In minimal containers, `sh`, `ls`, or `stat` may not exist. In that case, inspect mounts/permissions from the host or use a compatible debug image; do not assume a distroless runtime image has a shell.

For classpath resources, inspect the JAR:

```bash
jar tf application.jar
```

With native images, checking the JAR does not prove the resource was embedded. Verify `RuntimeHints`/build metadata and execute the resource-reading code path in the native executable.

## 12. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `NoSuchFileException` in container | Relative path resolved from a different CWD | Log `user.dir`, use absolute/configured path |
| Works on Windows, fails on Linux | Wrong letter casing in filename | Fix code or filename to match exact casing |
| Classpath resource returns null | Wrong resource path or missing packaging/hints | Check classpath/JAR and `RuntimeHints` |
| File exists on host, missing in container | Not copied or mounted | Check bind mount and destination |
| Permission denied | Container user lacks read permission | Fix ownership/mode or appropriate read-only mount |
| Fails only in native | Classpath resource not included in image | Register resource hints and rebuild |
| Path with `\\` fails on Linux | Windows-style string concatenation | Use `Path.resolve` |
| Runtime config not loaded | Wrong config location or precedence | Check Spring Boot config data and logs |

Classify the error before fixing: classpath resource, filesystem path, CWD, case sensitivity, or permissions. Each category requires a different fix.

## 13. Hands-On Exercise: Testing Paths on the JVM and Native Image

**Context:** a Spring Boot service with a fixed schema on the classpath and a rules file mounted into the container.

**Step 1 — Create the classpath resource.** Place `schemas/invoice.json` in `src/main/resources`; read it with `ClassPathResource`.

**Step 2 — Create the external file.** Provide `/etc/orders/rules.json` via a bind mount; pass the path via `ORDERS_RULES_FILE`.

**Step 3 — Log CWD.** Log `user.dir` and the resolved path; launch the process from two different directories to demonstrate how relative paths depend on CWD.

**Step 4 — Check case sensitivity.** Temporarily change the resource name from `invoice.json` to `Invoice.json` in a Linux test environment and confirm exact case matching is required.

**Step 5 — Run on the JVM.** Verify both the classpath resource and external file; test missing files and insufficient read permissions.

**Step 6 — Build native.** Register resource hints if needed, build the executable, and repeat the same test suite.

**Step 7 — Run in a container.** Set `WORKDIR` explicitly, mount the external file, run as a non-root user, and test the endpoint reading both sources.

Completion criteria: classpath resources are resolved independently of CWD; external paths are resolved from explicit configuration; filenames have accurate casing; container mounts and permissions are correct; JVM and native exhibit consistent behavior.

## 14. Conclusion

Relative paths depend on the **current working directory**, whereas classpath resources are located through the classloader. Linux typically treats filenames as case-sensitive, so code running on Windows can fail when moved to a Linux container. Containers also have their own filesystem and working directory; host files only appear inside when copied or mounted.

With Spring Boot Native Image, use `ClassLoader`/Spring `Resource` for classpath resources, `Path`/`Files` for external files, configure CWD and mount paths explicitly, use `Path.resolve` instead of manual string concatenation, and test on the Linux runtime image. These steps prevent path discrepancies across the JVM, native executable, and deployment environments.

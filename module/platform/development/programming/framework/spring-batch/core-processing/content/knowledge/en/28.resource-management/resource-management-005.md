# Resources from Classpath and Filesystem

In Spring Framework and Spring Batch, `Resource` is an abstraction representing a readable data source. That source can be a file on the classpath, a file external to the application, a URL, or another kind of resource. Through this abstraction, a reader can accept a `Resource` without needing to know how to open each source type itself.

Two common types when building batch jobs are:

- **`ClassPathResource`:** reads resources packaged on the classpath, such as configuration files or sample data located in `src/main/resources`.
- **`FileSystemResource`:** reads files existing on the filesystem, such as CSV files placed into an input directory by a scheduler or external system.

Choosing the right resource type affects how the application locates files when running in an IDE, when packaged as a JAR, when deployed on a server, and when a Job is restarted. For batch jobs, a resource must remain stable throughout the run so the reader can read accurate data and restore checkpoints.

## 1. Resource abstraction in Spring

`org.springframework.core.io.Resource` is the interface describing a data source. Commonly used methods:

| Method | Purpose |
|---|---|
| `exists()` | Checks whether the resource exists |
| `isReadable()` | Checks whether the resource can be read |
| `getInputStream()` | Opens a stream to read data |
| `getFilename()` | Gets the filename if the resource has a name |
| `getDescription()` | Gets a resource description for logging or error reporting |
| `contentLength()` | Gets the content size if the resource supports it |
| `lastModified()` | Gets the last-modified timestamp if the resource supports it |
| `getFile()` | Gets a `File` object when the resource actually has a filesystem file representation |

Spring provides several `Resource` implementations, such as:

| Implementation | Source |
|---|---|
| `ClassPathResource` | Resource from classpath/class loader |
| `FileSystemResource` | File or path on the filesystem |
| `PathResource` | Java NIO `Path` |
| `UrlResource` | Resource addressed by a URL |
| `ByteArrayResource` | Byte array in memory |
| `InputStreamResource` | A pre-supplied `InputStream` |

In Spring Batch, readers such as `FlatFileItemReader` accept a `Resource` as input. This allows the same reader definition to read files from either the classpath or the filesystem without rewriting parsing logic.

## 2. What is ClassPathResource?

`ClassPathResource` represents a resource found via the classpath. In typical Maven/Gradle projects, files placed under `src/main/resources` are copied to the classpath during build.

Example project structure:

```text
src/
  main/
    java/
      com/example/batch/
        OrderImportConfiguration.java
    resources/
      data/
        sample-orders.csv
      batch/
        import.properties
```

The `sample-orders.csv` file can be accessed via:

```java
Resource resource = new ClassPathResource("data/sample-orders.csv");
```

Or injected directly:

```java
@Bean
public Resource sampleOrdersResource() {
    return new ClassPathResource("data/sample-orders.csv");
}
```

Classpath resources suit default data, sample files, schemas, templates, or reference data packaged with the application version. They are not suitable for input files that external systems need to replace frequently after the application is built.

## 3. Classpath paths

With `ClassPathResource`, paths are resolved relative to the classpath, not the process's current working directory.

Example:

```java
new ClassPathResource("data/sample-orders.csv");
```

With `ResourceLoader`, the `classpath:` prefix can be used:

```java
@Value("classpath:data/sample-orders.csv")
Resource sampleOrders;
```

Key points to keep in mind:

- The path must match the resource location after build.
- Directory and file names must match case; Linux and JAR environments are typically case-sensitive.
- Do not include `src/main/resources` in the runtime path. That part is the project source directory; runtime resources typically start from the contents inside it.
- Forward slashes `/` can be used as separators in classpath resources across operating systems.
- Standardize on one path convention in configuration to avoid discrepancies between the IDE and deployment environments.

If a file is located at `src/main/resources/data/sample-orders.csv`, the runtime path is `data/sample-orders.csv`, not `src/main/resources/data/sample-orders.csv`.

## 4. What is FileSystemResource?

`FileSystemResource` represents a file or path existing on the filesystem of the machine running the application. This is the common choice for files delivered from external systems, shared directories, or volume mounts.

Example creating a resource from a path:

```java
Resource input = new FileSystemResource("/var/batch/inbound/orders.csv");
```

Or using Java NIO `Path`:

```java
Path inputPath = Path.of("/var/batch/inbound/orders.csv");
Resource input = new FileSystemResource(inputPath);
```

`FileSystemResource` can read files that change independently of application builds. It is the right choice when a scheduler or upstream system places a new file into an input directory before each Job run.

On Windows environments, a filesystem path might be `C:\\batch\\inbound\\orders.csv`; in Java code, prefer `Path.of(...)` or environment-appropriate path configuration rather than manually concatenating strings with path separators.

## 5. Relative and absolute filesystem paths

Relative paths are typically resolved against the process's current working directory (`user.dir`). This directory can differ when running from an IDE, command line, service manager, container, or scheduler.

Example:

```java
Resource input = new FileSystemResource("data/orders.csv");
```

This path might resolve to:

```text
<working-directory>/data/orders.csv
```

If the application runs from a different directory, it may fail to find the file or read the wrong file with the same name. For production batch jobs, configure an explicit root directory or pass absolute paths.

Example using a property:

```yaml
batch:
  input-directory: /var/batch/inbound
```

```java
@Bean
@StepScope
public Resource orderInputResource(
        @Value("${batch.input-directory}") String inputDirectory,
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    Path path = Path.of(inputDirectory).resolve(inputFile).normalize();
    return new FileSystemResource(path);
}
```

In this example, the application property provides the deployment directory, while the JobParameter provides the per-run filename. If `inputFile` comes from a user or external system, verify it does not escape the allowed directory via `..`, an absolute path, or a symbolic link outside the intended scope.

## 6. Comparing classpath and filesystem

Both resource types implement `Resource`, but their lookup mechanisms and lifecycles differ:

| Criterion | `ClassPathResource` | `FileSystemResource` |
|---|---|---|
| Lookup location | Classpath/class loader | Host machine's filesystem |
| Common source | Packaged `src/main/resources` | External inbound/outbound directories |
| Changing after build | Usually requires rebuilding/redeploying to change JAR contents | Files can be replaced without rebuilding the application |
| Running from executable JAR | Can be read directly from inside the JAR | Reads files outside the JAR |
| Best suited for | Templates, sample files, default data | Batch input/output files that vary per run |
| Writing/updating content | Should not be treated as writable storage | Writable if filesystem permissions allow |

Choose the resource based on where the data is managed. If data is released alongside the application artifact and is immutable, classpath is suitable. If data is delivered to the server on a schedule, filesystem is more appropriate.

## 7. Why doesn't ClassPathResource always return a File?

When running the application in an IDE, classpath resources usually reside under a directory like `target/classes` or `build/resources/main`. In that case, the resource may have a `File` representation on the filesystem.

However, when the application is packaged as an executable JAR, the resource may reside inside an archive:

```text
application.jar
  BOOT-INF/classes/
    data/sample-orders.csv
```

The resource is now read via the class loader and a stream. It is not a standalone file with a normal filesystem path.

Therefore, the following code is not portable:

```java
Resource resource = new ClassPathResource("data/sample-orders.csv");
File file = resource.getFile();
```

`getFile()` may work in an IDE but throw `FileNotFoundException` when the resource is inside a JAR. When reading contents, use `getInputStream()` or pass the `Resource` directly to APIs that support Spring Resource.

```java
try (InputStream inputStream = resource.getInputStream()) {
    // Read data from stream.
}
```

Do not solve this by assuming every resource can be converted to a `File`. Use the abstraction suited to the operation being performed.

## 8. Reading resources via ResourceLoader

`ResourceLoader` creates a `Resource` from a location string. The prefix indicates which source to resolve:

```java
@Component
public class BatchResourceFactory {

    private final ResourceLoader resourceLoader;

    public BatchResourceFactory(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource classpathTemplate() {
        return resourceLoader.getResource("classpath:templates/orders.csv");
    }

    public Resource filesystemInput(String path) {
        return resourceLoader.getResource("file:" + path);
    }
}
```

Common locations:

| Location | Resolution |
|---|---|
| `classpath:data/orders.csv` | Resource on the classpath |
| `file:/var/batch/orders.csv` | File on the filesystem |
| `https://example.org/orders.csv` | Resource by URL |
| `data/orders.csv` | Depends on ResourceLoader implementation/context; avoid relying on this when clarity is needed |

For filesystem paths containing spaces or special characters, handle URI/path conversion properly instead of arbitrarily concatenating `file:`. If you already have a `Path`, creating a `FileSystemResource` from `Path` is usually clearer.

## 9. Injecting Resource directly into ItemReader

`FlatFileItemReader` accepts a `Resource`, so both classpath and filesystem can be used without changing parsing configuration.

### Reading a file from the classpath

```java
@Bean
public FlatFileItemReader<Order> sampleOrderReader() {
    return new FlatFileItemReaderBuilder<Order>()
            .name("sampleOrderReader")
            .resource(new ClassPathResource("data/sample-orders.csv"))
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .build();
}
```

The reader uses sample data packaged with the application. This is a reasonable choice for demos, tests, or an immutable reference file.

### Reading a file from the filesystem

```java
@Bean
@StepScope
public FlatFileItemReader<Order> inboundOrderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    Resource resource = new FileSystemResource(inputFile);

    return new FlatFileItemReaderBuilder<Order>()
            .name("inboundOrderReader")
            .resource(resource)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

The reader receives a file per run via JobParameter. `@StepScope` enables late binding of `inputFile` once a StepExecution exists.

In both examples, the reader receives the same `Resource` abstraction. The difference lies only in the implementation and how the location is resolved.

## 10. Injecting Resource with @Value

Spring can convert a location string into a `Resource` when injected via `@Value`:

```java
@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputLocation']}") Resource inputResource) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(inputResource)
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

The JobParameter can contain an explicit source location:

```text
classpath:data/sample-orders.csv
file:/var/batch/inbound/orders-2026-11-15.csv
```

With this approach, the caller decides the resource location. Restrict allowed schemes, especially when the location comes from an API or user. Do not allow an arbitrary parameter to point to any URL or file on the server if the application only needs to read a specific inbound directory.

If you want to fix the source type, inject a `String` and construct `ClassPathResource` or `FileSystemResource` yourself to prevent callers from changing the scheme.

## 11. Validating resources before running a Step

A resource object may be constructed successfully while the file does not exist or lacks read permission. Early checks can use `exists()` and `isReadable()`:

```java
private void validateResource(Resource resource) {
    if (!resource.exists()) {
        throw new IllegalArgumentException(
                "Input resource does not exist: " + resource.getDescription()
        );
    }

    if (!resource.isReadable()) {
        throw new IllegalArgumentException(
                "Input resource is not readable: " + resource.getDescription()
        );
    }
}
```

Validation can be called in the factory creating the reader or in an input validation Tasklet/Step. For very large files or remote resources, some metadata checks can be costly or may not definitively guarantee the entire content can be read. Opening streams and handling I/O errors still must be managed.

With `FlatFileItemReader`, the default `strict` property typically requires the resource to exist when opening the reader. It can be configured explicitly as required, but do not disable strict just so a Job silently skips a missing mandatory input file.

## 12. Encoding and file format

When reading text files, align the encoding between the file-producing system and the batch reader. If a file is UTF-8 encoded while the reader uses a different charset, Vietnamese or special characters may be corrupted.

Example reader configuration:

```java
return new FlatFileItemReaderBuilder<Order>()
        .name("inboundOrderReader")
        .resource(resource)
        .encoding(StandardCharsets.UTF_8.name())
        .linesToSkip(1)
        .delimited()
        .names("orderId", "customerId", "amount")
        .targetType(Order.class)
        .saveState(true)
        .build();
```

`linesToSkip(1)` is commonly used when the first line is a header. Encoding and delimiter format must match the input file contract. Resource only specifies where to obtain content; it does not determine charset or data schema itself.

If files may arrive from multiple sources with different encodings, standardize upstream or expose encoding as a validated parameter rather than guessing based on the host environment.

## 13. Resources and Spring Batch restart

Readers like `FlatFileItemReader` can store progress in the Step `ExecutionContext` when `saveState(true)`. When the Job restarts the same JobInstance, the reader restores its checkpoint to resume reading.

Example:

```java
@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

For reliable restart:

- Keep identifying JobParameters unchanged to restart the right JobInstance.
- Use a stable reader name because the name can participate in building keys in the ExecutionContext.
- Keep the resource and file contents unchanged throughout the execution lifecycle.
- Do not replace the file with different content while a Job is incomplete.
- Ensure the reader supports `ItemStream` and state is saved.
- If the file might change, store a checksum/version or create an immutable snapshot before processing.

Line-count checkpoints are only meaningful when file content and order remain unchanged. If upstream overwrites the old file with new content, the reader may resume from the saved line number while actually reading a different dataset.

Classpath resources are usually immutable per artifact version, but if a new artifact is deployed while an old Job is mid-run, resource content could change. For Jobs needing restart across deployments, version artifacts or store input resources in an immutable, clearly identified location.

## 14. Do not call getFile() on every Resource

Some Java APIs require a `File` or `Path`, but `Resource` does not guarantee a physical file always exists.

Unsafe example:

```java
Resource resource = new ClassPathResource("data/sample-orders.csv");
Path path = resource.getFile().toPath();
```

This code may run in an IDE yet fail when the resource is packaged inside a JAR.

If the API only needs to read, use a stream:

```java
try (InputStream inputStream = resource.getInputStream()) {
    // Read data from stream.
}
```

If an API strictly requires a `Path`, copy the classpath resource to a temporary file:

```java
Path temporaryFile = Files.createTempFile("sample-orders-", ".csv");

try (InputStream inputStream = resource.getInputStream()) {
    Files.copy(inputStream, temporaryFile, StandardCopyOption.REPLACE_EXISTING);
}
```

After use, delete the temporary file according to the appropriate lifecycle. For batch jobs, copying must be designed so restarts can reuse the exact same content; do not create a new random temporary file on every restart if checkpoints depend on the previous file.

## 15. Distinguishing FileSystemResource, PathResource, and UrlResource

These implementations serve similar needs while representing different sources:

- `FileSystemResource` is suitable when code works with filesystem paths or files.
- `PathResource` is suitable when the application already uses Java NIO `Path` and wants to represent a resource from that path.
- `UrlResource` is suitable when the source is addressed by a URL, such as HTTP or a supported URL scheme.

Example:

```java
Path path = Path.of("/var/batch/inbound/orders.csv");
Resource filesystemResource = new FileSystemResource(path);
Resource pathResource = new PathResource(path);
Resource urlResource = new UrlResource(URI.create("https://example.org/orders.csv"));
```

Do not treat `UrlResource` as the default choice for large batch files over HTTP. Consider timeouts, retries, content stability, authentication, repeated downloads on restart, and data snapshot capability. In many systems, downloading files to a controlled inbound directory first and then running the Job on an immutable file is easier to operate.

## 16. Input and output resources

`Resource` is typically used to describe a read source. For output files, Spring Batch provides dedicated writers, and some writers accept `Resource` as a target.

Example of `FlatFileItemWriter` writing to the filesystem:

```java
@Bean
@StepScope
public FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .names("orderId", "amount")
            .shouldDeleteIfExists(false)
            .saveState(true)
            .build();
}
```

For output, clearly decide append, overwrite, restart, and publishing of the completed file. Do not write to a classpath resource because resources inside a JAR are usually not writable storage. Use the filesystem or dedicated storage for output.

If output must be published to another system, write to a temporary file and rename/publish after the Step succeeds. Rename operations can only be considered atomic under suitable filesystem conditions; with object storage or across two different filesystems, a separate publish mechanism is required.

## 17. Protecting filesystem paths

If a JobParameter contains a path passed in by a user or upstream system, restrict which file locations may be read. Do not concatenate input strings directly onto a base directory without normalizing and validating.

Example checking that a path resides inside the inbound directory:

```java
Path baseDirectory = Path.of("/var/batch/inbound").toRealPath();
Path candidate = baseDirectory.resolve(inputFile).normalize();

if (!candidate.startsWith(baseDirectory)) {
    throw new IllegalArgumentException("Input path is outside inbound directory");
}

if (!Files.isRegularFile(candidate) || !Files.isReadable(candidate)) {
    throw new IllegalArgumentException("Input file is missing or unreadable");
}

Resource resource = new FileSystemResource(candidate);
```

In environments with symbolic links, consider `toRealPath()` and your policy on allowing links. Checking a path string with `startsWith` alone before normalizing may be insufficient. Protection rules must match the filesystem and process execution permissions.

## 18. Common misconceptions

**Assuming a classpath resource is always a File.** When running from a JAR, resources may only be accessible via streams. Use `getInputStream()` or pass `Resource` to the reader.

**Including `src/main/resources` in runtime paths.** The runtime classpath starts from the contents copied inside the resources directory, such as `data/orders.csv`.

**Using relative paths without knowing the working directory.** Results may differ between IDE, service, container, and scheduler. Configure a base directory or absolute paths.

**Using ClassPathResource for input files that change daily.** Files packaged inside an artifact are unsuitable when upstream updates content independently. Use filesystem resources or appropriate storage.

**Assuming Resource validates content format itself.** Resource only describes the source. The reader still needs encoding, delimiter, schema, and validation.

**Assuming `@StepScope` alone guarantees restart.** Scope manages bean lifecycle; the reader needs `ItemStream`/`saveState` and a stable data source to restore checkpoints.

**Calling `getFile()` on any resource.** Not every resource has a physical file. Use a stream if you only need to read.

**Allowing arbitrary JobParameters to point to any path.** Restrict directories, schemes, and permissions according to application requirements.

## 19. Testing resources across runtime environments

Resources may work in an IDE yet fail after packaging. Therefore, test at least the following scenarios:

1. Reading a classpath resource from the test/runtime classpath.
2. Packaging the application as a JAR and verifying the reader reads resources inside the JAR without calling `getFile()`.
3. Reading a filesystem resource using an absolute path in a production-like deployment environment.
4. Checking nonexistent files, missing read permissions, and misconfigured directories.
5. Testing paths with `..`, absolute paths outside allowed directories, and symbolic links per security policy.
6. Testing encoding, delimiters, headers, and Vietnamese data/special characters.
7. Restarting the Job after several chunks commit and confirming the input file is unchanged and the reader restores the right checkpoint.
8. Modifying the file between two test runs to confirm checksum/version or validation mechanisms detect the content no longer matches the original.

For classpath resources, integration tests running from the packaged JAR help catch `getFile()` dependencies that IDE tests might miss. For filesystem resources, tests should use temporary directories or explicitly created fixtures so they do not depend on a developer machine's working directory.

## 20. Choosing a Resource for batch jobs

Choose `ClassPathResource` for data released with the application that does not need independent changes after build, such as sample files or templates. Choose `FileSystemResource` for externally managed input/output files that change per run or require checkpoint/restart on the server.

Use the `Resource` abstraction so readers do not depend directly on how files are opened. Use `classpath:` and `file:` when explicit location resolution is needed; avoid relying on undefined relative paths. Do not call `getFile()` if a resource might live inside a JAR. Validate existence, read permissions, encoding, and allowed paths before running.

In Spring Batch, resources are also tied to restartability: keep reader names, JobParameters, and source contents stable; enable state saving when needed; do not swap files mid-Job. Separating packaged classpath resources from external filesystem files helps batch jobs run consistently across development, JAR, and production environments.

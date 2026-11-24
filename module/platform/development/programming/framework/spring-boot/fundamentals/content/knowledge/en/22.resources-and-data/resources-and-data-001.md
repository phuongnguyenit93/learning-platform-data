# Resource, ResourceLoader, and the classpath, file, and URL Prefixes

In a Spring Boot application, not all data comes from a database or an HTTP request. An application may also need to read an email template, a JSON file used as seed data, a certificate mounted into a container, a CSV file provided by operations, or content located at a URL. Those sources have different storage locations, yet the program typically only needs basic operations: **locating the resource, checking readability, and opening a data stream**.

Spring Framework provides two important abstractions:

- **`Resource`**: represents an accessible resource, regardless of whether it resides on the classpath, on the filesystem, or at a URL.
- **`ResourceLoader`**: accepts a location string and creates the appropriate `Resource` object.

In **Spring Boot Fundamentals → Resources and Data**, what you need to master is not only how to write `classpath:`, `file:`, or `https:`, but also how they affect JAR packaging, container deployment, `InputStream` lifecycle, and security when paths come from configuration.

## 1. Why Shouldn't You Always Use java.io.File?

Suppose we want to load content from `src/main/resources/templates/welcome.txt`. When running the application in an IDE, that file exists in the project directory tree, so the following code looks reasonable:

~~~java
File file = new File("src/main/resources/templates/welcome.txt");
String text = Files.readString(file.toPath());
~~~

However, when packaged into an executable JAR, the path `src/main/resources/...` is no longer a reliable runtime path. Resources are copied into the classpath output and usually reside **inside the JAR file**. A file inside an archive does not necessarily have a corresponding `java.io.File` on the filesystem.

Therefore, code relying on source paths may work in the IDE but fail after deployment:

~~~text
Development environment:
  project/src/main/resources/templates/welcome.txt
       |
       +-- build tool copies to classpath

Runtime environment:
  application.jar
       |
       +-- BOOT-INF/classes/templates/welcome.txt
             (entry inside archive, not a standalone file)
~~~

A better approach is to describe the **logical location**:

~~~text
classpath:templates/welcome.txt
~~~

Then ask Spring to read it using `Resource` or `ResourceLoader`. The application no longer has to guess physical paths in each environment.

### Distinguishing "resource" and "file"

A resource can be:

- An actual file on disk.
- An entry inside a JAR.
- Content accessed over HTTP/HTTPS.
- A byte array or input stream object created by the application.
- A resource within a special application context.

Meanwhile, `java.io.File` only describes a location on the running machine's filesystem. Thus, **every file can be represented as a resource, but not every resource is a physical file**.

## 2. What Is Resource?

The `org.springframework.core.io.Resource` interface represents a resource and extends the basic capabilities of `InputStreamSource`.

Commonly used methods:

| Method | Meaning | Notes |
|---|---|---|
| `getInputStream()` | Opens a stream to read data | Close the stream after use; may throw `IOException` |
| `exists()` | Checks whether the resource appears to exist | Does not guarantee a subsequent read will succeed |
| `isReadable()` | Checks whether the resource is considered readable | Result may depend on the resource type |
| `getDescription()` | Description string for the resource, useful for logging | Not necessarily a filesystem path |
| `getFilename()` | File name if determinable | May be `null` |
| `getURL()` / `getURI()` | Representation as a URL/URI if supported | Does not mean it is a physical file |
| `getFile()` | Attempts to obtain a `java.io.File` | Do not use for resources inside a JAR or over HTTP |
| `contentLength()` | Content size if determinable | May incur I/O or be unavailable |
| `lastModified()` | Modification timestamp if retrievable | Should not be relied upon as always-available metadata |

The goal of the abstraction is a shared interface, without forcing every source to have identical capabilities.

Example of a UTF-8 reader method:

~~~java
package com.example.resources;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.Resource;

public final class ResourceTextReader {

    private ResourceTextReader() {
    }

    public static String readSmallUtf8(Resource resource)
            throws IOException {

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

**Why use `getInputStream()` instead of `getFile()`?** Because reading via a stream works across many source types: files, classpath entries inside JARs, and URLs. It is a good default choice when you only need to read content.

Note that `readAllBytes()` is only suitable for small content or content with a clear size limit. For large files, streaming processing, data limits, and memory management are required.

## 3. What Is ResourceLoader?

`org.springframework.core.io.ResourceLoader` is an interface for loading resources by a location string. Its key method is:

~~~java
Resource getResource(String location);
~~~

Example:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:templates/welcome.txt"
);
~~~

The `location` parameter can be:

- An address with the `classpath:` prefix.
- A path with the `file:` prefix.
- A URL with a valid scheme such as `https:`.
- A string without a scheme; how it is interpreted depends on the implementation and context.

`ResourceLoader` only **resolves a location into a Resource**; in most cases, calling `getResource(...)` does not read the entire content yet. Actual I/O operations typically happen when calling `getInputStream()`, `exists()`, or similar methods.

### ResourceLoader in Spring Boot

Spring's `ApplicationContext` acts as a `ResourceLoader`. In a Boot application, you can inject this interface into a bean:

~~~java
package com.example.resources;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class DocumentLocator {

    private final ResourceLoader resourceLoader;

    public DocumentLocator(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource locate(String location) {
        return resourceLoader.getResource(location);
    }
}
~~~

The service does not need to know whether the application is running in an IDE, an executable JAR, or a container. The caller passes in an appropriate location, and the service returns a `Resource`.

However, **do not pass locations directly from untrusted user input**. Schemes like `file:` and `https:` can cause the service to read sensitive files or make outbound network requests. Security is covered in a later section.

## 4. Rule Table: classpath:, file:, URL

The three most common location groups:

| Example location | Where the resource is found | When to use |
|---|---|---|
| `classpath:templates/welcome.txt` | Application classpath | Resources packaged together with code/JAR |
| `file:/opt/app/config/rules.json` | Process filesystem | Files outside the artifact, often mounted into a container |
| `file:///opt/app/config/rules.json` | Filesystem, using full file URI form | When an absolute path needs explicit representation |
| `https://example.org/assets/catalog.json` | Resource over HTTP(S) | Data at an external endpoint, when access and risks are controlled |
| `templates/welcome.txt` | Depends on ResourceLoader/context | Can be ambiguous; prefer explicit prefixes |

You can visualize it as:

~~~text
ResourceLoader.getResource(location)
                   |
        +----------+-----------+
        |          |           |
   classpath:     file:       https:
        |          |           |
        v          v           v
 ClassPath      Local FS      Remote URL
 resource       resource      resource
        \          |           /
         \         |          /
          +--------+---------+
                   |
                   v
           Resource abstraction
                   |
                   v
            getInputStream()
                   |
                   v
             Read data
~~~

For a service author, what matters is that **the data-consuming code can work with `Resource`**, while where the data comes from is determined by the location and configuration.

## 5. The classpath: Prefix

`classpath:` specifies a resource on the Java application's classpath.

Examples:

~~~text
classpath:templates/welcome.txt
classpath:data/countries.json
classpath:config/default-rules.yml
~~~

In a Maven or Gradle project using the standard layout, application resources are typically placed in:

~~~text
src/
  main/
    java/
      com/example/DemoApplication.java
    resources/
      templates/welcome.txt
      data/countries.json
      config/default-rules.yml
~~~

During build, files in `src/main/resources` are placed on the runtime classpath. Therefore, they can be accessed using `classpath:data/countries.json`, regardless of where the source path sits.

### Example of reading a classpath resource

File `src/main/resources/demo/greeting.txt`:

~~~text
Hello from the classpath resource!
~~~

Code:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

Resource resource = new ClassPathResource("demo/greeting.txt");

try (InputStream input = resource.getInputStream()) {
    String message = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
    System.out.println(message);
}
~~~

`ClassPathResource` is a concrete implementation of `Resource`. It is useful when the source is known for certain to be the classpath and does not need to change via configuration.

If you want a flexible location, use:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:demo/greeting.txt"
);
~~~

The second approach has the advantage of allowing you to change the source later without modifying the resource-consuming logic.

### Leading slash in the path

Typically, for a `classpath:` location, the resource is resolved from the **classpath root**:

~~~text
classpath:demo/greeting.txt
~~~

Some APIs may also accept `classpath:/demo/greeting.txt`, but using the form without a redundant `/` after the prefix keeps examples clear.

Unlike filesystem paths, `demo/greeting.txt` here is not relative to the Java process's working directory.

## 6. Runtime Classpath and Executable JARs

An important difference between running in an IDE and running a JAR is how resources are stored.

In an IDE, the file `demo/greeting.txt` might exist as a normal file in the output directory:

~~~text
build/resources/main/demo/greeting.txt
~~~

When packaged into a Spring Boot executable JAR, the resource is usually placed in:

~~~text
app.jar
  |
  +-- BOOT-INF/classes/
        |
        +-- demo/greeting.txt
~~~

At runtime:

~~~bash
java -jar app.jar
~~~

`ClassPathResource` can read a resource inside a JAR via `getInputStream()`. However, a call like the following is **not portable**:

~~~java
Resource resource = new ClassPathResource("demo/greeting.txt");

File file = resource.getFile(); // May fail when the file is inside a JAR
~~~

Because `getFile()` requires a real file on the filesystem, whereas an entry inside a JAR is not a standalone file.

The right way when you only need to read:

~~~java
try (InputStream stream = resource.getInputStream()) {
    // Read, parse, or copy data from the stream.
}
~~~

If a third-party library strictly requires a `Path` or `File`, you may need to copy the content to an application-managed **temporary file**. In that case, handle closing the stream, size limits, temporary directory permissions, and cleaning up the file after use. Do not assume Spring will automatically extract the entire archive just to create a corresponding file.

### classpath resources should generally be read-only content

Resources packaged inside a JAR are suitable as templates, default data, or static documents. Modifying content at runtime inside an executable JAR is not a sound configuration or data-storage strategy.

If content needs to be edited without rebuilding, switch to an external file with `file:`, a configuration service, or an appropriate data store.

## 7. The file: Prefix

`file:` describes a resource on the filesystem accessible to the Java process.

Examples on Linux:

~~~text
file:/opt/app/config/rules.json
file:///opt/app/config/rules.json
~~~

The full URI form with three slashes makes the absolute path explicit in certain contexts:

~~~text
file:///opt/app/config/rules.json
    ^^^
    scheme + absolute path
~~~

On Windows, a file URI can look like:

~~~text
file:///C:/apps/demo/config/rules.json
~~~

The path must reflect the filesystem **of the machine or container running Java**, not the development machine's filesystem if the two environments differ.

### Example of reading a file outside the JAR

Suppose the file has the content:

~~~json
{
  "mode": "safe",
  "maxItems": 100
}
~~~

It is mounted at `/opt/app/config/rules.json`.

Code:

~~~java
Resource resource = resourceLoader.getResource(
        "file:/opt/app/config/rules.json"
);

try (InputStream input = resource.getInputStream()) {
    // Pass the stream to the application's JSON parser.
}
~~~

The code only needs read permission on the file; it does not require the file to be inside the JAR.

### Be careful with relative paths

Locations like:

~~~text
file:./config/rules.json
file:config/rules.json
~~~

can depend on the working directory, URI/URL handling, and implementation. They can easily behave differently across IDEs, JAR launch scripts, containers, and service managers.

When configuring external files in a deployment environment, **prefer explicit absolute paths**:

~~~text
file:/opt/app/config/rules.json
~~~

If a relative path is genuinely needed, actively define the working directory and document the deployment accordingly.

### FileSystemResource for a known path

When you already have a `Path` in Java, there is no need to convert it into a location string:

~~~java
import java.nio.file.Path;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Path path = Path.of("/opt/app/config/rules.json");
Resource resource = new FileSystemResource(path);
~~~

`FileSystemResource` works with a concrete file/path. This approach is convenient when the application has already received a validated path processed with Java NIO.

## 8. URL Prefixes: http: and https:

A location with a valid URL scheme such as:

~~~text
https://example.org/resources/pricing.json
http://localhost:8081/sample.txt
~~~

can be represented by `ResourceLoader` as a URL-based resource, typically `UrlResource` or an implementation appropriate to the loader.

Example:

~~~java
Resource resource = resourceLoader.getResource(
        "https://example.org/resources/pricing.json"
);

try (InputStream input = resource.getInputStream()) {
    // Read content fetched via a connection to the URL.
}
~~~

When calling `getInputStream()` on a remote resource, the operation may require a network connection and can fail due to DNS, TLS, timeouts, HTTP status, or network conditions.

### A URL Resource is not a general-purpose HTTP client

`Resource` is appropriate when the primary intent is **reading content from an abstract location**. It does not replace a dedicated HTTP client when you need:

- Complex authentication and automatic token refresh.
- Specific timeouts, retries, circuit breakers, and connection pool control.
- APIs using POST/PUT/PATCH/DELETE methods.
- Business-level request headers or response headers.
- Status code handling, pagination, and rate limiting.
- Streaming with size limits and protection against hanging connections.

In those scenarios, use the appropriate HTTP client in Spring (such as `RestClient` or `WebClient` where suitable), or an HTTP library capable of explicitly managing network policies.

**Do not use `ResourceLoader.getResource(userInput)` as an unrestricted URL reader.** Allowing users to arbitrarily control the location can create SSRF or local file disclosure risks; the application must restrict valid sources.

## 9. What Happens When a Location Has No Prefix?

Example:

~~~java
Resource resource = resourceLoader.getResource(
        "demo/greeting.txt"
);
~~~

This is not an explicit way to specify a source. The result **depends on the `ResourceLoader` implementation and the context type**.

Some loaders interpret an unprefixed path as a classpath path; web contexts have their own resource resolution rules. You should not treat a schemeless string as a standard across all implementations.

To keep code readable and consistent, choose one of the explicit forms:

~~~text
classpath:demo/greeting.txt
file:/opt/app/demo/greeting.txt
https://example.org/demo/greeting.txt
~~~

If you do not want to repeat the prefix in code, keep the full location in configuration and pass it into the service rather than omitting the scheme.

## 10. Complete Spring Boot Example: A Resource-Reading Service

Let's build a small application that can change where text is read from using configuration alone.

### 10.1. Create the file in resources

Place the file at:

~~~text
src/main/resources/demo/message.txt
~~~

Content:

~~~text
This is the default message packaged with Spring Boot.
~~~

### 10.2. Configure the location

In `src/main/resources/application.properties`:

~~~properties
app.message.location=classpath:demo/message.txt
~~~

The property name is defined by the application; Spring Boot does not have a built-in `app.message.location` property with special meaning.

### 10.3. Service that reads the Resource

~~~java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class MessageResourceService {

    private final ResourceLoader resourceLoader;

    public MessageResourceService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public String readMessage(String location) throws IOException {
        Resource resource = resourceLoader.getResource(location);

        try (InputStream stream = resource.getInputStream()) {
            return new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

The `readMessage(...)` method:

1. Receives the configured location.
2. Calls the loader to create a resource.
3. Opens an input stream.
4. Reads the text as UTF-8.
5. Closes the input stream via try-with-resources.

This example is meant for small text files. When working with large data or untrusted external sources, stream in chunks and enforce size limits.

### 10.4. Run at startup using ApplicationRunner

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    ApplicationRunner showMessage(
            MessageResourceService service,
            @Value("${app.message.location}") String location
    ) {
        return args -> System.out.println(
                service.readMessage(location)
        );
    }
}
~~~

Here `@Value` simply reads a location property to pass to the service. Because the service accepts a prefixed location string, it can access different types of resources without changing its logic.

On startup, the application reads the content:

~~~text
This is the default message packaged with Spring Boot.
~~~

### 10.5. Switch to a file outside the JAR

Create a file outside the JAR, for example `/opt/app/config/message.txt`, then run:

~~~bash
java -jar app.jar --app.message.location=file:/opt/app/config/message.txt
~~~

Now **the exact same Java service** reads data from the filesystem instead of the classpath.

### 10.6. Switch to a URL

In a demo environment with a trusted HTTPS endpoint:

~~~bash
java -jar app.jar --app.message.location=https://example.org/demo/message.txt
~~~

The service can also read through a URL resource if the endpoint exists and is reachable. Because this is a network source, a real-world application must control timeouts, content, size, and allowed hosts.

The example uses an illustrative domain; do not assume `https://example.org/demo/message.txt` is an endpoint serving real data.

## 11. Direct Resource Injection via @Value

If a location is fixed or comes from a single property, Spring can inject a `Resource` object via `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class WelcomeTemplate {

    private final Resource template;

    public WelcomeTemplate(
            @Value("classpath:demo/message.txt") Resource template
    ) {
        this.template = template;
    }

    public Resource getTemplate() {
        return template;
    }
}
~~~

Here Spring converts the location string in the annotation into an appropriate `Resource`.

You can use a property placeholder to select the location:

~~~java
public WelcomeTemplate(
        @Value("${app.message.location:classpath:demo/message.txt}")
        Resource template
) {
    this.template = template;
}
~~~

Notable points:

- The value before `:` in the placeholder is the property name `app.message.location`.
- `classpath:demo/message.txt` is the fallback if the property is absent.
- Spring resolves the location and injects the `Resource`.
- When the bean receives the resource, **it does not mean the content has been fully read**; reading usually happens when calling `getInputStream()`.

When you have multiple configuration groups, use `@ConfigurationProperties` to organize properties better. However, the meaning of a location remains unchanged: it describes where the resource will be accessed.

## 12. Creating a Resource Does Not Necessarily Load Content

A common misconception is thinking:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:missing-file.txt"
);
~~~

will immediately throw an error if the file does not exist. In reality, **`getResource` usually only creates an object describing the location**, without necessarily opening a stream.

Example:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:missing-file.txt"
);

System.out.println(resource.exists());
~~~

`exists()` may return `false`; calling `getInputStream()` may raise a `FileNotFoundException` or an appropriate `IOException`.

Therefore, resource-consuming code must handle I/O errors in the right place:

~~~java
try (InputStream stream = resource.getInputStream()) {
    // Process data.
} catch (IOException exception) {
    // Log context and handle according to application policy.
}
~~~

### exists() does not replace try/catch

Even when `exists()` returns true, the file may be deleted, permissions may change, or a network connection may drop before reading begins. This is a form of time-of-check/time-of-use.

Use `exists()` when you want to produce a friendly message or decide a processing branch, but do not use it to skip handling `IOException`.

### isReadable() is also only an indicator

`isReadable()` can help detect some unreadable resources, but it is not a guarantee that a subsequent stream open will succeed.

Good error messages should include `resource.getDescription()` to identify the source being read without relying on `getFile()`.

## 13. Reading Text, JSON, and Binary Data

`Resource` imposes no content format.

**For small UTF-8 text**, you can read the entire stream:

~~~java
try (InputStream input = resource.getInputStream()) {
    String text = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
}
~~~

**For JSON**, pass the stream into the parser:

~~~java
try (InputStream input = resource.getInputStream()) {
    JsonNode tree = objectMapper.readTree(input);
}
~~~

The second example uses Jackson's `JsonNode` and `ObjectMapper`, assuming `objectMapper` has been injected and the appropriate Jackson library is present in the project.

**For large files**, process sequentially:

~~~java
try (InputStream input = resource.getInputStream()) {
    byte[] buffer = new byte[8192];

    int count;
    while ((count = input.read(buffer)) != -1) {
        // Process buffer from index 0 with length count.
    }
}
~~~

For CSV or text logs, you can use `BufferedReader` to read line by line. For images or binary files, never convert bytes through a charset and expect the content to remain intact.

To avoid `OutOfMemoryError` or unpredictable memory usage, do not call `readAllBytes()` on large or unbounded resources, especially public URLs.

## 14. Closing InputStream Properly

An important contract of `Resource` is that the caller must manage the resource returned by `getInputStream()`.

Recommended pattern:

~~~java
try (InputStream stream = resource.getInputStream()) {
    // Use the stream inside this block.
}
~~~

Upon exiting the block, Java calls `close()`, even if an exception occurs while reading.

Avoid patterns like:

~~~java
InputStream stream = resource.getInputStream();
// Finish reading without closing the stream.
~~~

This can leak file descriptors, sockets, or network resources.

Also, **do not assume the same Resource always allows reopening streams multiple times**. Implementations like `InputStreamResource` may represent a single-use stream. If an API needs to read multiple times, verify the characteristics of the resource type or design appropriate storage/buffering.

## 15. Important Resource Implementations

| Implementation | Common source | Notes |
|---|---|---|
| `ClassPathResource` | File/entry on classpath | Supports reading data packaged inside a JAR via stream |
| `FileSystemResource` | File or Path on filesystem | Suitable when an actual path is already available |
| `UrlResource` | URL, potentially including file/HTTP(S) | I/O behavior depends on scheme and URL handler |
| `ByteArrayResource` | `byte[]` data in memory | Useful for tests or pre-generated content |
| `InputStreamResource` | An existing `InputStream` | Typically not suitable for multiple reads |
| `ServletContextResource` | Resource tied to servlet context | May appear in traditional web applications |

### ClassPathResource

~~~java
Resource resource = new ClassPathResource("data/default.json");
~~~

Explicitly specifies the storage layer as the classpath.

### FileSystemResource

~~~java
Resource resource = new FileSystemResource(
        Path.of("/opt/app/config/default.json")
);
~~~

The resource is a file/path accessible by the OS.

### UrlResource

~~~java
Resource resource = new UrlResource(
        "https://example.org/data/default.json"
);
~~~

Handle exceptions for invalid URL creation as well as content access.

### ByteArrayResource in unit tests

~~~java
byte[] content = "Hello".getBytes(StandardCharsets.UTF_8);
Resource resource = new ByteArrayResource(content);

String message = ResourceTextReader.readSmallUtf8(resource);
~~~

One advantage of designing functions that accept `Resource` is that tests can use `ByteArrayResource` without creating real files or making network calls.

## 16. ResourceLoader Reads One Location; ResourcePatternResolver Finds Multiple Resources

A very important distinction is:

- `ResourceLoader.getResource(location)`: accepts **one location**, returns **one Resource object**.
- `ResourcePatternResolver.getResources(pattern)`: finds **multiple Resources** matching a pattern or search convention.

For example, `ResourceLoader` is not a tool for expanding globs:

~~~java
resourceLoader.getResource("classpath:config/*.yml");
~~~

Do not expect that call to automatically find every `.yml` file. The `*` here does not act as a glob in `getResource(...)` in the conventional sense.

If you need to find multiple resources, use `ResourcePatternResolver`:

~~~java
import java.io.IOException;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;

ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver(resourceLoader);

Resource[] resources = resolver.getResources(
        "classpath*:config/*.yml"
);

for (Resource resource : resources) {
    System.out.println(resource.getDescription());
}
~~~

`PathMatchingResourcePatternResolver` supports common Ant-style patterns and searches across the classpath with `classpath*:`.

### classpath: vs classpath*:

| Prefix | General meaning |
|---|---|
| `classpath:` | A resource located from the classpath |
| `classpath*:` | Finds matching resources across all possible classpath locations |
| `classpath*:config/*.yml` | Combines searching multiple classpath locations and a pattern |

For example, multiple JAR libraries each contain a file:

~~~text
META-INF/demo/plugin.properties
~~~

If you need **all** copies of the resource across multiple classpath roots/JARs, you can use:

~~~java
Resource[] resources = resolver.getResources(
        "classpath*:META-INF/demo/plugin.properties"
);
~~~

Conversely, `classpath:META-INF/demo/plugin.properties` typically resolves only one resource according to the classloader mechanism; it does not guarantee scanning all duplicate-named copies.

**Note:** `classpath*:` is a mechanism intended for `ResourcePatternResolver`. Do not treat it as an interchangeable substitute for `classpath:` in any API that accepts only a single `Resource`.

### Limitations of pattern scanning

Pattern matching across multiple JARs can depend on classpath structure, URL handlers, and the ability to enumerate archive contents. Do not design a mandatory feature assuming every non-standard archive type has identical scanning capabilities.

If an application requires a fixed list of files, configuring an explicit list is sometimes more stable and easier to operate than an overly broad pattern.

## 17. Example Using ResourcePatternResolver in a Service

Suppose we have the files:

~~~text
src/main/resources/
  rules/
    common.yml
    pricing.yml
    security.yml
~~~

We want to load all `.yml` files in the `rules` directory.

~~~java
package com.example.rules;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.stereotype.Service;

@Service
public class RuleResourceService {

    private final ResourcePatternResolver resolver;

    public RuleResourceService(ResourceLoader loader) {
        this.resolver = new PathMatchingResourcePatternResolver(loader);
    }

    public List<Resource> findRuleFiles() throws IOException {
        Resource[] matches = resolver.getResources(
                "classpath*:rules/*.yml"
        );

        List<Resource> result = new ArrayList<>();
        for (Resource resource : matches) {
            if (resource.isReadable()) {
                result.add(resource);
            }
        }
        return result;
    }
}
~~~

The method only **finds the resources**; it does not parse YAML yet. The application must decide processing order, duplicate name handling, reaction when files are missing, and policy when a file fails.

In particular, pattern scan results can depend on the classpath and classloader; do not rely on the default enumeration order to define business configuration precedence.

## 18. Resource and External Application Configuration

An application often has default data on the classpath and wants to allow replacing it with a file outside the JAR.

Example in `application.properties`:

~~~properties
app.rules.location=classpath:rules/default.json
~~~

When deploying:

~~~bash
java -jar app.jar --app.rules.location=file:/opt/app/config/rules.json
~~~

Or using an environment variable:

~~~bash
export APP_RULES_LOCATION=file:/opt/app/config/rules.json
java -jar app.jar
~~~

The name `APP_RULES_LOCATION` corresponds to the property `app.rules.location` in Spring Boot's externalized configuration mechanism.

A resource-reading service can use:

~~~java
@ConfigurationProperties(prefix = "app.rules")
public record RulesProperties(String location) {
}
~~~

After registering `RulesProperties` with Spring, a service receives this object and `ResourceLoader`:

~~~java
@Service
public class RulesService {

    private final RulesProperties properties;
    private final ResourceLoader loader;

    public RulesService(RulesProperties properties, ResourceLoader loader) {
        this.properties = properties;
        this.loader = loader;
    }

    public Resource rulesResource() {
        return loader.getResource(properties.location());
    }
}
~~~

The Java snippets above omit imports to focus on combining the two abstractions. When placing them into a project, import `ConfigurationProperties`, `Service`, `ResourceLoader`, and `Resource` accordingly, and register the configuration properties bean.

### Resource data is different from application config

`application.properties` or `application.yml` are **configuration sources** read by Spring Boot via its Config Data mechanism, with profiles, precedence, and dedicated rules.

Meanwhile, `ResourceLoader` is a general abstraction for accessing resources. Reading a JSON file with `ResourceLoader` **does not automatically turn JSON keys into Spring properties**. Similarly, calling `getResource("file:/.../app.yml")` does not mean Spring Boot will automatically add that file to property sources.

If you want Spring Boot to load an external config file through the official configuration mechanism, use the appropriate options such as `spring.config.location`, `spring.config.additional-location`, or `spring.config.import` where applicable. That is a different purpose from reading business data files via `Resource`.

## 19. Security Risks When Location Comes From Input

Suppose an endpoint is built as:

~~~java
@GetMapping("/read")
public String read(@RequestParam String path) throws IOException {
    Resource resource = resourceLoader.getResource(path);
    return ResourceTextReader.readSmallUtf8(resource);
}
~~~

**This is an unsafe example and should not be deployed.**

A user could try locations such as:

~~~text
file:/etc/passwd
file:/opt/app/secrets/private-key.pem
http://127.0.0.1:8080/admin
http://169.254.169.254/
~~~

If the endpoint allows arbitrary reads, it can lead to:

- **Local File Read / path traversal**: reading files not intended for the user.
- **SSRF**: causing the server to send requests to internal addresses or metadata services.
- **Resource exhaustion**: reading very large files, slow URLs, or never-ending streams.
- **Information disclosure**: returning content containing secrets or internal configuration.

### A safer design

Instead of accepting a location directly from the request, define valid resources via code or trusted configuration:

~~~java
private static final Map<String, String> ALLOWED_RESOURCES = Map.of(
        "guide", "classpath:docs/guide.txt",
        "terms", "classpath:docs/terms.txt"
);

public Resource findDocument(String id) {
    String location = ALLOWED_RESOURCES.get(id);

    if (location == null) {
        throw new IllegalArgumentException("Invalid document");
    }

    return resourceLoader.getResource(location);
}
~~~

For files outside the JAR, additionally verify that the normalized path stays within the allowed directory, enforce OS/container permissions, and restrict file types. For URLs, use a scheme/host allowlist and an HTTP client with policies for timeouts, redirects, DNS, IP ranges, and content size.

**Do not merely check whether the string starts with `classpath:`, `file:`, or `https:` and consider it safe.** The prefix indicates the source type, not that the source is trusted.

## 20. Error Handling When Reading a Resource

Some typical scenarios:

| Symptom | Possible cause | Approach |
|---|---|---|
| Works in IDE, JAR fails on `getFile()` | Resource resides inside an archive | Use `getInputStream()` |
| Cannot find `classpath:...` | Wrong classpath path or file not packaged | Check `src/main/resources`, case-sensitive names, artifact |
| External file cannot be read | Wrong path or process lacks permissions | Check mount, absolute path, read permissions |
| URL resource reads very slowly | Slow DNS, TLS, network, or server | Use a client with clear timeouts and policies |
| `exists()` returns true but read fails | Source changed between check and read | Catch and handle `IOException` |
| Cannot find `*.yml` files | Used `getResource()` instead of pattern resolver | Use `ResourcePatternResolver.getResources(...)` |
| Second read fails | Resource has a single-use stream | Design an appropriate reading flow or buffer |
| Large file causes memory spike | Used unbounded `readAllBytes()` | Read via streaming, limit size |
| Unauthorized URL or file gets read | Location comes from arbitrary input | Allowlist and access control |

### Logging with context without leaking information

Example:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Read resource.
} catch (IOException exception) {
    log.error(
            "Unable to read resource: {}",
            resource.getDescription(),
            exception
    );
    throw exception;
}
~~~

`resource.getDescription()` helps identify the failing source. However, for URLs containing tokens in query strings or sensitive file paths, you may need to **redact or sanitize the description before logging**.

Do not log full URLs with credentials, file contents, or tokens.

## 21. Resource in Unit Tests

Depending on `Resource` makes code easy to test without needing real files in many cases.

Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;

class ResourceTextReaderTest {

    @Test
    void readsUtf8() throws Exception {
        byte[] bytes = "Hello".getBytes(StandardCharsets.UTF_8);
        Resource resource = new ByteArrayResource(bytes);

        String actual = ResourceTextReader.readSmallUtf8(resource);

        assertEquals("Hello", actual);
    }
}
~~~

This test does not need to:

- Create temporary files.
- Read `src/main/resources`.
- Start a Spring ApplicationContext.
- Call an HTTP endpoint.

When you need to test the actual classpath mechanism, put test fixtures in `src/test/resources`:

~~~text
src/test/resources/
  fixtures/sample.json
~~~

Then construct `ClassPathResource("fixtures/sample.json")` in the test. Remember: resources in `src/test/resources` usually belong only to the **test classpath** and do not automatically appear in the production executable JAR.

## 22. Paths Relative to a Class in a Package

`ClassPathResource` has a constructor that creates a resource relative to a `Class<?>`. This differs from a path name starting from the classpath root.

Example:

~~~java
package com.example.report;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public class ReportRenderer {

    public Resource template() {
        return new ClassPathResource(
                "default-template.txt",
                ReportRenderer.class
        );
    }
}
~~~

With the constructor taking `Class<?>`, the relative path is resolved based on that class's package. This is useful if you want to place a resource alongside the Java class in the same package.

If using the simple constructor:

~~~java
new ClassPathResource("com/example/report/default-template.txt");
~~~

the path is interpreted from the classpath root.

**Choose and document a clear convention in the project.** If some resources are organized by package and others sit in standalone config directories, implicit path conventions can cause resource failures when moving classes or refactoring packages.

## 23. Does Using ResourceLoader Require ApplicationContext Directly?

No. A service that only wants to load resources should depend on the narrow abstraction:

~~~java
@Service
public class TemplateService {

    private final ResourceLoader resourceLoader;

    public TemplateService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource template(String name) {
        return resourceLoader.getResource(
                "classpath:templates/" + name
        );
    }
}
~~~

The example above only illustrates dependency injection; **it is unsafe to accept an untrusted `name`** if it could contain path traversal. A real service should pick names from an allowed list or map IDs to fixed locations.

If a service injects the entire `ApplicationContext` just to call `getResource(...)`, it depends on a broader interface than needed. Using `ResourceLoader` as the dependency generally keeps the design clean and easier to swap with a test implementation.

### ResourceLoaderAware

Besides constructor injection, Spring also has `ResourceLoaderAware` for beans that want `ResourceLoader` supplied via a callback. However, constructor injection is usually clearer, easier to test, and more directly expresses dependencies in modern applications.

There is no need to implement `ResourceLoaderAware` when constructor injection already meets your needs.

## 24. Do Not Confuse Resource with Static HTTP Resources Served by Spring MVC

Spring Boot also has a mechanism to serve static content from classpath locations such as:

~~~text
classpath:/static/
classpath:/public/
classpath:/resources/
classpath:/META-INF/resources/
~~~

In a web application with appropriate default configuration, files in those locations can be mapped as HTTP resources via Spring MVC's static content serving mechanism.

For example, a file `src/main/resources/static/logo.svg` can be served under an application URL depending on the mapping.

This is **different** from a service explicitly calling:

~~~java
resourceLoader.getResource("classpath:static/logo.svg");
~~~

Both mechanisms may read data from the classpath, but their purposes differ:

- **ResourceLoader**: helps Java code access a resource.
- **Static resource handling**: helps the web framework map and serve resources to HTTP clients.

Do not assume every file in `src/main/resources` will automatically be exposed publicly over HTTP. Exposure depends on the web stack, mappings, and resource handler configuration.

## 25. Practice Exercises

### Exercise 1: Reading a classpath resource from a JAR

1. Create `src/main/resources/data/banner.txt`.
2. Write a service accepting `ResourceLoader`.
3. Call `getResource("classpath:data/banner.txt")`.
4. Read using `getInputStream()` in try-with-resources.
5. Run in the IDE, then package an executable JAR and run again.

**Observation:** the code should not need to know the `src/main/resources` path at runtime.

### Exercise 2: Switching sources via configuration

Keep the resource-reading service unchanged. Set:

~~~properties
app.banner.location=classpath:data/banner.txt
~~~

Then run:

~~~bash
java -jar app.jar --app.banner.location=file:/opt/app/config/banner.txt
~~~

Note the difference between content packaged in the JAR and the external file.

### Exercise 3: Intentionally calling getFile()

Create a `ClassPathResource` for a file inside the JAR and call `getFile()`. Observe the behavior when running from the IDE and from an executable JAR.

**Key takeaway:** an API may work with real files during development without guaranteeing it works for entries in an archive.

Replace the call with `getInputStream()` so it does not depend on the JAR layout.

### Exercise 4: Reading multiple resources

Create:

~~~text
src/main/resources/rules/
  a.yml
  b.yml
  c.yml
~~~

Use:

~~~java
ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver(resourceLoader);

Resource[] resources = resolver.getResources(
        "classpath*:rules/*.yml"
);
~~~

Compare the result with `resourceLoader.getResource("classpath:rules/*.yml")`.

**Key takeaway:** a method returning a single resource does not automatically find multiple files via a glob.

### Exercise 5: Designing a safe resource-access API

Suppose an API is only allowed to return two document templates `guide` and `terms`. Write an explicit ID → location map instead of taking the entire location directly from an HTTP query parameter.

Then explain why checking only `location.startsWith("file:")` or `location.startsWith("https:")` is not enough to prevent Local File Read or SSRF.

## 26. Common Misconceptions

**"A Resource is always a java.io.File."** False. A Resource can represent an entry inside a JAR or a URL.

**"Calling getFile() on a classpath resource always works."** No. When the resource is packaged in an archive, a physical file may not exist.

**"getResource() loads all data immediately."** Usually not. It mainly creates the location abstraction; reading occurs when opening the stream.

**"If exists() succeeds, there is no need to catch IOException."** False. The source can change or fail when opening the stream.

**"file: is a path on the developer's machine."** False. It is the filesystem seen by the running process, which may be inside a container or another machine.

**"A location without a prefix is always classpath."** Do not assume this, as handling depends on the loader/context.

**"classpath*: can always be used just like classpath:."** False. `classpath*:` belongs to `ResourcePatternResolver`'s multi-resource search mechanism.

**"resourceLoader.getResource can find all *.json."** No. Finding multiple resources by pattern requires an appropriate resolver.

**"ResourceLoader is a full HTTP client."** No. Complex business HTTP calls require a dedicated client with explicit timeout/retry policies.

**"Accepting a location from the user and passing it to getResource is convenient."** Very risky: it can lead to reading sensitive files or SSRF.

**"Resources in src/test/resources are always present in production."** No. They usually exist only on the test classpath.

**"Reading a data file with ResourceLoader automatically adds fields to Environment."** No. The Resource abstraction and Config Data are two mechanisms serving different purposes.

## 27. Guidelines for Choosing a Solution

When designing resource-reading functionality, you can decide using these questions:

| Question | Recommended direction |
|---|---|
| Does the data always ship with the app and need no post-build edits? | `classpath:` |
| Is the data mounted or updated outside the artifact? | `file:` with an explicit path |
| Is the data at a network endpoint needing auth, timeouts, and retries? | Dedicated HTTP client; `Resource` only when needs are simple and controlled |
| Does the code only need to read content? | `Resource.getInputStream()` |
| Does the code need to find multiple files by glob? | `ResourcePatternResolver` |
| Is the code given an already-validated `Path`? | `FileSystemResource` |
| Want to write tests independent of real files? | `ByteArrayResource` |
| Does the location come from an end user? | Do not load directly; restrict allowed sources, paths, and URLs |
| Could the resource be very large? | Streaming, size limits, and I/O error handling |
| Need to switch sources without editing Java? | Put the location in a trusted configuration property |

Keep in mind that data source choices also affect operations: container permissions, volume mounts, deployment history, artifact immutability, security boundaries, and recovery policies when a source is unavailable.

## Conclusion

**`Resource`** is an abstraction for reading a resource without forcing it to exist as a physical file. **`ResourceLoader`** takes a location and resolves it into an appropriate Resource object. The three most important location groups in Spring Boot are:

- **`classpath:`** for resources on the classpath, including files packaged inside an executable JAR.
- **`file:`** for files/paths visible to the Java process on the filesystem.
- **URL schemes like `https:`** for network-accessible sources, subject to security controls and appropriate I/O policies.

When reading, prefer **`getInputStream()` and try-with-resources** rather than forcing a resource into a `java.io.File`. When multiple files are needed, clearly distinguish `ResourceLoader` from `ResourcePatternResolver` and the `classpath*:` prefix. When a source is chosen from configuration, use explicit locations and manage access permissions, data sizes, and I/O errors.

Understanding these abstractions helps Spring Boot applications run consistently from IDE to JAR/container, switch data sources cleanly at deployment, and avoid common path and security pitfalls.

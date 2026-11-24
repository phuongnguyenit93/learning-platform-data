# ResourcePatternResolver When Searching for Multiple Resources

A Spring Boot application does not always know the exact name of every file it needs to read in advance. There are situations where the application must locate **all** configuration files inside a directory, localized email templates, JSON schema files across multiple modules, or identically named resources packaged inside different JARs.

If you already know a single path, `ResourceLoader.getResource(...)` is usually enough. But when the requirement is "find all resources matching this pattern", Spring Framework provides **`ResourcePatternResolver`** and its familiar implementation **`PathMatchingResourcePatternResolver`**.

Example:

~~~java
Resource[] resources = resolver.getResources(
        "classpath*:schemas/**/*.json"
);
~~~

This call asks Spring to find JSON resources in the `schemas` directory and its subdirectories, potentially spanning multiple classpath locations.

This lesson explains the differences among `Resource`, `ResourceLoader`, and `ResourcePatternResolver`; the `classpath:`, `classpath*:`, and `file:` syntax; the wildcards `*`, `?`, and `**`; reading resources when running from an executable JAR; limitations of classpath scanning; service usage, testing, and common pitfalls.

## 1. Scenario: How Does One File Differ from Many Files?

Suppose the project contains:

~~~text
src/main/resources/
└── schemas/
    ├── order.json
    ├── customer.json
    └── versions/
        ├── v1/
        │   └── payment.json
        └── v2/
            └── payment.json
~~~

If reading only `schemas/order.json`, we know the file name upfront:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:schemas/order.json"
);
~~~

But if the requirement is to **find all JSON schemas** to register into a catalog at startup, hard-coding four paths forces code changes every time the project adds a new schema.

A search-pattern solution:

~~~java
Resource[] resources = resolver.getResources(
        "classpath*:schemas/**/*.json"
);
~~~

Schemas can be discovered by file placement convention rather than adding each filename to Java source code.

This is an example of *convention-based discovery*: directories and patterns serve as the convention, and files conforming to that convention are discovered when the program runs its scan.

### 1.1. Real-world use cases

- Finding templates under `classpath*:templates/email/**/*.html`.
- Loading schema files from one or multiple modules.
- Discovering metadata from multiple libraries inside `META-INF`.
- Collecting sample datasets for a test suite.
- Loading rule files, mappings, or definitions sharing a uniform format.
- Finding resources on the filesystem when a directory is mounted into a container.

This mechanism is helpful when multiple resources share a convention and the application can process them as a collection.

## 2. Resource: Abstracting a Single Resource

In Spring Framework, `Resource` is the abstraction of a resource that can be read or described.

~~~java
import org.springframework.core.io.Resource;
~~~

Notable methods:

~~~java
boolean exists();
boolean isReadable();
String getFilename();
String getDescription();
InputStream getInputStream() throws IOException;
URL getURL() throws IOException;
File getFile() throws IOException;
~~~

Meaning:

| API | Meaning |
| --- | --- |
| `exists()` | Does the resource currently exist per the implementation's mechanism? |
| `isReadable()` | Is the resource readable as supported by the implementation? |
| `getFilename()` | Gets the final filename segment if determinable |
| `getDescription()` | Description for logging or diagnostics |
| `getInputStream()` | Opens a stream to read content |
| `getURL()` | Gets the URL when supported by the resource |
| `getFile()` | Converts to `java.io.File` when a corresponding real file exists |

Common `Resource` implementations include:

- `ClassPathResource` for resources on the classpath.
- `FileSystemResource` for files on the filesystem.
- `UrlResource` for URL-backed resources.
- Other resource types depending on the `ResourceLoader` and runtime environment.

**Key point to remember:** not every `Resource` is a separate physical file on disk. Resources inside a JAR can still be read with `getInputStream()`, whereas `getFile()` may not work.

## 3. ResourceLoader: Resolving a Single Resource Location

`ResourceLoader` is a Spring Framework interface:

~~~java
import org.springframework.core.io.ResourceLoader;
~~~

It provides the method:

~~~java
Resource getResource(String location);
~~~

Example:

~~~java
@Component
public class LogoService {

    private final ResourceLoader resourceLoader;

    public LogoService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource logo() {
        return resourceLoader.getResource(
                "classpath:images/logo.png"
        );
    }
}
~~~

`getResource(...)` returns a `Resource` representing the specified location. It **does not automatically search for a list of files matching a wildcard** and does not necessarily read content at call time.

To read the resource:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:data/message.txt"
);

try (InputStream input = resource.getInputStream()) {
    String text = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
    System.out.println(text);
}
~~~

Import `java.io.InputStream`, `java.nio.charset.StandardCharsets`, and handle `IOException` in the enclosing method.

### 3.1. When is ResourceLoader enough?

When the application already knows a single exact resource location:

~~~text
classpath:config/payment-defaults.json
file:/opt/myapp/config/feature-flags.yml
~~~

If the need is to find all `*.json` files or a set of resources present across multiple JARs, we need an API that resolves **patterns**.

## 4. ResourcePatternResolver: Extending to Find a Set of Resources

`ResourcePatternResolver` lives in the package:

~~~java
import org.springframework.core.io.support.ResourcePatternResolver;
~~~

This interface extends `ResourceLoader` and adds:

~~~java
Resource[] getResources(String locationPattern) throws IOException;
~~~

In other words:

- `getResource(String)` handles a single location.
- `getResources(String)` handles a location pattern and returns a **resource array**.

Spring provides a commonly used implementation:

~~~java
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
~~~

Example:

~~~java
ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

Resource[] resources = resolver.getResources(
        "classpath*:schemas/**/*.json"
);
~~~

`PathMatchingResourcePatternResolver` combines Spring's resource resolution with path matching. It does not require Spring Boot; it is a Spring Framework API. Spring Boot brings convenient packaging, configuration, and dependency injection for using it.

### 4.1. Why is the result an array?

A pattern can match:

- Zero resources.
- One resource.
- Multiple resources.
- Multiple resources with the same name residing in different classpath roots or JARs.

Hence the return type is `Resource[]`, even if your pattern happens to match only one file.

When nothing matches, it usually returns an empty array. However, errors while accessing or traversing resources can cause `getResources(...)` to throw `IOException`; the application needs to decide how to handle that.

## 5. Comparing classpath:, classpath*:, and file:

This is the easiest part to mix up when first using `ResourcePatternResolver`.

### 5.1. classpath: — a single classpath path

~~~java
resourceLoader.getResource(
        "classpath:schemas/order.json"
);
~~~

The `classpath:` prefix normally resolves a single matching resource via the classloader/resource loader.

If the same resource name exists in two JARs, an API reading a single resource does not automatically merge content from both JARs.

With `ResourcePatternResolver`, a pattern starting with `classpath:` and containing wildcards may be scanned under one resolved classpath root. **Do not use it when the goal is collecting resources across all JARs.**

### 5.2. classpath*: — searching across multiple classpath locations

~~~java
Resource[] resources = resolver.getResources(
        "classpath*:schemas/**/*.json"
);
~~~

The special `classpath*:` prefix tells the resolver to consider **all matching classpath locations**, including multiple directories and JARs accessible to the classloader.

Suppose there are two libraries:

~~~text
billing-schema.jar
└── schemas/
    └── billing/
        └── invoice.json

shipping-schema.jar
└── schemas/
    └── shipping/
        └── shipment.json
~~~

The pattern:

~~~java
resolver.getResources("classpath*:schemas/**/*.json");
~~~

can locate both schemas when they are genuinely on a scannable classpath and the JAR structure allows the resolver to identify entries.

This is the single biggest difference of `classpath*:`: **it is not restricted to whichever classpath location happens to be chosen first**.

### 5.3. file: — paths on the filesystem

If files reside outside the application:

~~~text
/opt/myapp/config/rules/
├── tax.yml
├── discount.yml
└── archived/
    └── legacy.yml
~~~

you can use:

~~~java
Resource[] resources = resolver.getResources(
        "file:/opt/myapp/config/rules/**/*.yml"
);
~~~

This pattern uses a filesystem location. The path above applies to Linux-like layouts; on Windows, use the appropriate filesystem URI.

Do not confuse `file:` with `classpath:`. A file mounted into a container is not on the classpath just because it sits on the same machine running the JVM.

### 5.4. Prefix selection table

| Prefix | Meaning | Scenario |
| --- | --- | --- |
| `classpath:` | A resource or pattern from a classpath location | Known file or no need to scan all classpath roots |
| `classpath*:` | All matching classpath locations the resolver can find | Scanning resources across multiple modules/JARs |
| `file:` | Resources on the filesystem | Mounted directories or files outside the JAR |
| `https:` and other URLs | URL-based resource, implementation-dependent | A specific URL resource; remote wildcards are not guaranteed |

An HTTP URI does not automatically become a browsable directory tree for Spring. To list batches of files in object storage or external services, you usually need a dedicated listing API rather than speculative URL wildcards.

## 6. Ant-Style Wildcard Syntax

`PathMatchingResourcePatternResolver` uses Ant-style pattern syntax.

Common symbols:

| Symbol | Meaning |
| --- | --- |
| `*` | Matches zero or more characters within a path segment |
| `?` | Matches one character within a path segment |
| `**` | Matches zero or more directory levels when used in compatible path-matcher syntax |

Examples:

~~~text
classpath*:schemas/*.json
classpath*:schemas/**/*.json
classpath*:templates/email/*.html
classpath*:templates/email/**/*.html
classpath*:config/app-?.yml
~~~

Interpretation:

- `schemas/*.json`: finds JSON files directly in the `schemas` directory.
- `schemas/**/*.json`: finds JSON files in `schemas` and subdirectories at any depth.
- `app-?.yml`: names with exactly one character at `?`, such as `app-a.yml`.
- `templates/email/**/*.html`: finds HTML templates in the email directory tree.

### 6.1. Illustrative matching results

Given:

~~~text
schemas/
├── order.json
├── readme.txt
├── v1/
│   ├── invoice.json
│   └── notes.md
└── v2/
    └── archive/
        └── payment.json
~~~

Expected:

| Pattern | Typically matched files |
| --- | --- |
| `schemas/*.json` | `order.json` |
| `schemas/**/*.json` | `order.json`, `invoice.json`, `payment.json` |
| `schemas/v1/*.json` | `invoice.json` |
| `schemas/v?/invoice.json` | `invoice.json` if the path matches |
| `schemas/**/*.txt` | No files if `readme.txt` is the only file directly at root? |

In the last pattern, because `**` can match zero subdirectories, `readme.txt` directly under `schemas` **can still match**. This is why you should verify the exact semantics of `**` rather than assuming at least one subdirectory is required.

### 6.2. Do not confuse with regular expressions

The pattern `schemas/**/*.json` is not a Java regex. Its symbols and semantics follow Ant-style path matching, not `Pattern.compile(...)`.

Do not write regex syntax like `.*` or capture groups expecting the resolver to interpret them as regexes.

### 6.3. Prefer a specific root directory

Use:

~~~text
classpath*:schemas/**/*.json
~~~

instead of scanning too broadly:

~~~text
classpath*:**/*.json
~~~

Broad patterns can match many unrelated resources and slow down startup, especially in applications with large classpaths.

## 7. Classpath Roots, JAR Directories, and Scanning Limits

Unlike reading a known file, wildcard resolution requires the resolver to find a **root directory** and then traverse matching entries.

For example:

~~~text
classpath*:schemas/**/*.json
~~~

has the root `schemas/` before the wildcard portion. The resolver can locate matching classpath roots and then search entries beneath them.

Whereas:

~~~text
classpath*:*.xml
~~~

asks to scan XML files at the classpath root. Wildcard scanning right at the root may fail to find all entries across every JAR/classloader because JAR and classloader root-directory enumeration has limitations.

### 7.1. Practical rule for library resources

If you design a library whose resources need to be auto-discovered, place them inside **a clearly named subdirectory**:

~~~text
META-INF/myapp/schemas/
META-INF/myapp/mappings/
META-INF/myapp/rules/
~~~

Example:

~~~java
Resource[] schemas = resolver.getResources(
        "classpath*:META-INF/myapp/schemas/**/*.json"
);
~~~

This is far easier to manage than putting all JSON files at the classpath root and scanning `classpath*:*.json`.

### 7.2. classpath* does not promise finding every file in every environment

Results also depend on:

- The `ClassLoader` and the URLs it exposes.
- Directory structures and entries inside JARs.
- The application packaging runtime, including executable JARs.
- How URL protocols are handled.
- The resolver's ability to open and traverse the corresponding directories/JARs.

Spring provides broad support for classpath scanning, but when a product relies on auto-discovery inside complex packaged libraries, you should test from the **real packaged artifact**, not just inside the IDE.

### 7.3. Duplicate resource names across multiple JARs

Suppose:

~~~text
plugin-a.jar!/META-INF/myapp/rules/default.yml
plugin-b.jar!/META-INF/myapp/rules/default.yml
~~~

`classpath*:META-INF/myapp/rules/default.yml` can return both locations.

Do not arbitrarily decide to "just take the first file" without a rule. The returned order can depend on the classloader or scanning mechanism and is not a business priority contract.

If each rule must have a unique ID, the application should read the ID and then:

- Detect duplicates and fail fast; or
- Allow an override rule with explicit priority; or
- Keep the two sources separate if names match across two distinct plugins.

Matching physical file names does not mean the logical data inside is non-conflicting.

## 8. Reading Resources via InputStream, Not Depending on getFile()

When running in an IDE, a resource may reside under `target/classes` or `build/resources/main`. In that environment `Resource.getFile()` may work.

But once packaged:

~~~text
app.jar
└── BOOT-INF/classes/
    └── schemas/
        └── order.json
~~~

the resource sits inside an archive and does not necessarily have a corresponding `java.io.File`.

The following code easily fails on deployment:

~~~java
File file = resource.getFile();
String json = Files.readString(file.toPath());
~~~

For a resource inside a JAR, `getFile()` may throw `FileNotFoundException` or a related `IOException`.

Instead, use:

~~~java
try (InputStream input = resource.getInputStream()) {
    String json = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
}
~~~

### 8.1. Why must streams be closed?

`getInputStream()` opens a resource that must be closed after reading. `try-with-resources` guarantees closing the stream even if reading or parsing fails.

When reading many resources, forgetting to close streams can exhaust file descriptors or hold onto archive connections/handles unexpectedly long.

### 8.2. isReadable() does not replace handling IOException

You can filter:

~~~java
if (!resource.isReadable()) {
    return;
}
~~~

but between checking and reading, the resource can change or an I/O error can occur. You must still handle exceptions from `getInputStream()`.

### 8.3. getFilename() does not guarantee a unique identifier

If two locations are both named `default.json`, `resource.getFilename()` returns `default.json` for both even if their contents differ.

Use `getDescription()` or `getURL()` when diagnosing sources; if you need a business identifier, define an ID in the content/schema or extract a relative path according to an explicit convention.

## 9. Using ResourcePatternResolver in a Spring Boot Bean

`ResourceLoader` is provided by Spring as an infrastructure dependency. You can use it to construct a pattern-matching resolver:

~~~java
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.stereotype.Service;

@Service
public class SchemaCatalog {

    private final ResourcePatternResolver resolver;

    public SchemaCatalog(ResourceLoader resourceLoader) {
        this.resolver =
                new PathMatchingResourcePatternResolver(resourceLoader);
    }

    public Resource[] findSchemas() throws IOException {
        return resolver.getResources(
                "classpath*:schemas/**/*.json"
        );
    }
}
~~~

Benefits:

- `ResourceLoader` comes from the Spring context.
- The resolver uses the resource loading infrastructure suited to the application environment.
- Business code interacts only with the `ResourcePatternResolver` contract.
- It is easy to switch the pattern to a controlled configuration property later.

### 9.1. ApplicationContext can also resolve patterns

Spring Framework's `ApplicationContext` extends `ResourcePatternResolver` and exposes these APIs. Example:

~~~java
Resource[] resources = applicationContext.getResources(
        "classpath*:schemas/**/*.json"
);
~~~

This works when code already interacts with `ApplicationContext`. However, a service that only reads resources does not need to depend on the entire `ApplicationContext`. Injecting `ResourceLoader` to build a resolver or declaring a dedicated `ResourcePatternResolver` bean keeps dependencies narrower and easier to test.

### 9.2. Creating a shared ResourcePatternResolver bean

If multiple services need a shared resolver, register one:

~~~java
@Configuration(proxyBeanMethods = false)
public class ResourceConfiguration {

    @Bean
    public ResourcePatternResolver resourcePatternResolver(
            ResourceLoader resourceLoader) {

        return new PathMatchingResourcePatternResolver(resourceLoader);
    }
}
~~~

Then inject it:

~~~java
@Service
public class RuleCatalog {

    private final ResourcePatternResolver resolver;

    public RuleCatalog(ResourcePatternResolver resolver) {
        this.resolver = resolver;
    }
}
~~~

This centralizes the resource-discovery infrastructure in one place rather than having every service instantiate an implementation.

## 10. Complete Example: Finding All JSON Schemas at Startup

Let's build a small Spring Boot application that prints the list of discovered JSON schemas. No web server or database is needed.

### 10.1. Project structure

~~~text
schema-discovery/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/schemas/
    │   │   ├── SchemaDiscoveryApplication.java
    │   │   └── SchemaListingRunner.java
    │   └── resources/
    │       └── schemas/
    │           ├── order.json
    │           ├── customer.json
    │           └── versions/
    │               └── v2/
    │                   └── invoice.json
    └── test/
        └── java/com/example/schemas/
            └── SchemaListingRunnerTest.java
~~~

### 10.2. Spring Boot dependency

Maven example using Java 21, Spring Boot 3.x:

~~~xml
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
    <artifactId>schema-discovery</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

The version above is illustrative for the Boot 3.x line. In a real project, use the Spring Boot version managed by your BOM/project and ensure compatibility with your JDK.

### 10.3. Main class

`SchemaDiscoveryApplication.java`:

~~~java
package com.example.schemas;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SchemaDiscoveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(SchemaDiscoveryApplication.class, args);
    }
}
~~~

### 10.4. Sample resource contents

`src/main/resources/schemas/order.json`:

~~~json
{
  "type": "object",
  "title": "Order",
  "properties": {
    "id": { "type": "string" }
  }
}
~~~

`src/main/resources/schemas/customer.json`:

~~~json
{
  "type": "object",
  "title": "Customer",
  "properties": {
    "name": { "type": "string" }
  }
}
~~~

`src/main/resources/schemas/versions/v2/invoice.json`:

~~~json
{
  "type": "object",
  "title": "Invoice",
  "properties": {
    "amount": { "type": "number" }
  }
}
~~~

The JSON files here are only sample data. `ResourcePatternResolver` does not parse or validate schemas; it simply discovers and supplies the matching `Resource` instances.

### 10.5. ApplicationRunner to list resources

`SchemaListingRunner.java`:

~~~java
package com.example.schemas;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Comparator;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.stereotype.Component;

@Component
public class SchemaListingRunner implements ApplicationRunner {

    private static final String PATTERN =
            "classpath*:schemas/**/*.json";

    private final ResourcePatternResolver resolver;

    public SchemaListingRunner(ResourceLoader resourceLoader) {
        this.resolver =
                new PathMatchingResourcePatternResolver(resourceLoader);
    }

    @Override
    public void run(ApplicationArguments args) throws IOException {
        Resource[] schemas = resolver.getResources(PATTERN);

        // Scan order is not a business contract.
        Arrays.sort(
                schemas,
                Comparator.comparing(Resource::getDescription)
        );

        System.out.println("Found " + schemas.length + " schema(s)");

        for (Resource resource : schemas) {
            if (!resource.isReadable()) {
                throw new IOException(
                        "Schema is not readable: "
                                + resource.getDescription()
                );
            }

            try (InputStream input = resource.getInputStream()) {
                String json = new String(
                        input.readAllBytes(),
                        StandardCharsets.UTF_8
                );

                System.out.println(
                        "Schema: " + resource.getDescription()
                );
                System.out.println(
                        "Characters: " + json.length()
                );
            }
        }
    }
}
~~~

When the application runs, the runner invokes the resolver, sorts resources by description for readable logs, and opens streams to read each file.

**Sorting by `getDescription()` here only stabilizes log ordering in the example; it is not a business priority rule between schemas.** If precedence is required, define IDs/priorities inside the data.

### 10.6. Running locally and from a JAR

From the Maven project directory:

~~~bash
./mvnw spring-boot:run
~~~

if the repository includes the Maven Wrapper; or:

~~~bash
mvn spring-boot:run
~~~

When packaged:

~~~bash
mvn package
java -jar target/schema-discovery-0.0.1-SNAPSHOT.jar
~~~

Code using `getInputStream()` handles resources packaged inside the JAR better than approaches relying on `getFile()`.

### 10.7. If no schemas are found

If this is a module where schemas are **required**, the application should fail fast:

~~~java
Resource[] schemas = resolver.getResources(PATTERN);

if (schemas.length == 0) {
    throw new IllegalStateException(
            "No schemas found for pattern: " + PATTERN
    );
}
~~~

If schemas are **optional**, an empty array can be a valid outcome; the service simply uses an empty catalog or disables the corresponding feature.

That decision belongs to business logic. The resolver itself does not know whether finding zero files is an error or normal behavior.

## 11. Finding Resources Across Multiple JARs

A prominent use case is a modular system: each module packages its own metadata or configuration.

Example:

~~~text
catalog-core.jar
└── META-INF/myapp/catalog/
    └── core.json

catalog-plugin-tax.jar
└── META-INF/myapp/catalog/
    └── tax.json

catalog-plugin-shipping.jar
└── META-INF/myapp/catalog/
    └── shipping.json
~~~

The application includes these JARs on its runtime classpath and runs:

~~~java
Resource[] catalogs = resolver.getResources(
        "classpath*:META-INF/myapp/catalog/**/*.json"
);
~~~

When the resolver can access and scan those classpath roots, it can return resources from all three modules.

### 11.1. A pattern is a contract between modules

If a module packages metadata in the wrong directory:

~~~text
META-INF/other-place/shipping.json
~~~

it will not match the pattern. That is not a bug in the resolver.

A library should document:

- Standard resource directory.
- File extension.
- Content structure.
- ID and versioning rules.
- How duplicate names/IDs are handled.
- When the application scans and loads resources.

### 11.2. Resources may live in nested JARs

Spring Boot executable JARs provide classloader and URL handling tailored for nested dependencies. Let `ResourcePatternResolver` use Spring's resource loading infrastructure rather than manually building `java.io.File` paths into `BOOT-INF/lib`.

If a library uses custom URL protocols or custom classloaders, pattern scanning must be verified on the actual runtime. Do not assume a resource inside a JAR has a filesystem path.

## 12. When to Use classpath*: with an Exact Name and No Wildcard?

`classpath*:` is also useful when you need **every resource sharing the same name**.

For example, two dependencies both contain:

~~~text
META-INF/myapp/extensions.properties
~~~

You can call:

~~~java
Resource[] resources = resolver.getResources(
        "classpath*:META-INF/myapp/extensions.properties"
);
~~~

There is no `*` or `**` in the path after the prefix; nevertheless, `classpath*:` finds multiple resource locations with that same name across the classloader.

That differs from:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:META-INF/myapp/extensions.properties"
);
~~~

The second call returns only one resource location resolved by `ResourceLoader`. When designing a plugin system with multiple identically named files, this distinction is crucial.

## 13. Do Not Assume Result Order and Handle Duplicates Explicitly

The resolver returns `Resource[]`, whose order may depend on:

- Classpath order.
- Classloader behavior.
- Filesystem traversal order.
- Entry order inside archives.
- The runtime environment's URL resolution mechanism.

Do not write:

~~~java
Resource selected = resolver.getResources(pattern)[0];
~~~

to select the "highest-priority resource" when nothing guarantees any meaning for the first element.

### 13.1. If you only need readable logs

You can sort by name/description:

~~~java
Arrays.sort(
        resources,
        Comparator.comparing(Resource::getDescription)
);
~~~

This only produces a more readable order, not business precedence.

### 13.2. If each file defines a rule with an ID

A sound design:

1. Find the resources.
2. Read and parse content.
3. Extract the ID declared inside the content.
4. Detect duplicate IDs.
5. Apply explicit priority rules or fail fast.
6. Build the final catalog.

Pseudo-code example:

~~~java
Map<String, RuleDefinition> rulesById = new HashMap<>();

for (Resource resource : resources) {
    RuleDefinition rule = parseRule(resource);

    RuleDefinition previous = rulesById.putIfAbsent(
            rule.id(),
            rule
    );

    if (previous != null) {
        throw new IllegalStateException(
                "Duplicate rule id: " + rule.id()
        );
    }
}
~~~

`RuleDefinition` and `parseRule` are illustrative abstractions that you define in your implementation. The resolver does not merge or validate content automatically.

### 13.3. The same resource may appear via different scan paths

An application with complex classloaders or module setups may return multiple URLs pointing to the same content or identical copies. If loading twice causes side effects, define a deduplication strategy using a logical ID or controlled normalized URL.

**Do not use the filename as a unique key** when scanning multiple JARs: two independent libraries can easily both contain `config.json`.

## 14. Using a Pattern from Configuration Properties

If an application needs to vary its scan directory by deployment, you do not have to hard-code the pattern into the service.

`application.yml`:

~~~yaml
app:
  schema:
    location-pattern: classpath*:schemas/**/*.json
    required: true
~~~

Configuration properties:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.schema")
public record SchemaProperties(
        String locationPattern,
        boolean required
) {
}
~~~

Registration:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
    // ...
}
~~~

Service:

~~~java
@Service
public class SchemaDiscoveryService {

    private final ResourcePatternResolver resolver;
    private final SchemaProperties properties;

    public SchemaDiscoveryService(
            ResourceLoader resourceLoader,
            SchemaProperties properties) {

        this.resolver =
                new PathMatchingResourcePatternResolver(resourceLoader);
        this.properties = properties;
    }

    public Resource[] find() throws IOException {
        Resource[] found = resolver.getResources(
                properties.locationPattern()
        );

        if (properties.required() && found.length == 0) {
            throw new IllegalStateException(
                    "Required resources not found: "
                            + properties.locationPattern()
            );
        }

        return found;
    }
}
~~~

In production, validate that `locationPattern` is non-empty and its prefix matches the application's intent. If patterns come from untrusted users, never allow scanning arbitrary filesystems or classpaths and returning resource contents to the caller.

### 14.1. When to configure instead of hard-coding

- Directory paths differ between staging and production.
- A module can use resources from a JAR or a mounted directory.
- Tests need to point at fixtures.
- An optional feature is enabled through explicit configuration.

### 14.2. Never allow uncontrolled pattern overrides

If an API accepts a pattern from a request:

~~~text
GET /resources?pattern=file:/**/*
~~~

and the server automatically reads all matching files, the application risks data exposure or resource exhaustion.

Use patterns from trusted administration config, restrict allowed prefixes/directories, and do not expose arbitrary contents via public endpoints. For user-uploaded data, build dedicated storage with authorization rather than turning `ResourcePatternResolver` into a public filesystem browser.

## 15. Reading Large Sets of Resources: Avoid Loading Everything into RAM

The example code used:

~~~java
String content = new String(
        input.readAllBytes(),
        StandardCharsets.UTF_8
);
~~~

This is convenient for small files, but `readAllBytes()` loads the entire file into memory.

If a pattern matches hundreds of large files, risks include:

- High heap usage.
- Increased GC pressure.
- Prolonged startup time.
- A single huge file triggering `OutOfMemoryError`.
- Multiple parsers retaining unnecessary data simultaneously.

For large files, use a streaming-capable parser:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Pass InputStream into a streaming-capable parser.
    parseIncrementally(input);
}
~~~

`parseIncrementally` is an illustrative application function, not a built-in Spring API.

You can set limits on file size, resource count, and timeouts when accessing filesystems/networks. If resources are loaded into an in-memory cache, design clear cache bounds and reload semantics.

### 15.1. Do not re-scan on every request unnecessarily

If the set of resources is effectively static after startup, avoid calling:

~~~java
resolver.getResources("classpath*:schemas/**/*.json");
~~~

on every incoming HTTP request. Repeatedly scanning JARs/directories has overhead.

Build the catalog once at startup, store parsed results in an immutable structure, and inject that catalog into services.

If filesystem resources need runtime updates, design a dedicated reload/versioning mechanism. The resolver only searches for resources when called; it **does not register a file watcher**.

## 16. Combining with @ConditionalOnResource: Similarities and Differences

Spring Boot provides `@ConditionalOnResource`:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(
        resources = "classpath:config/report-template.html"
)
public class ReportAutoConfiguration {
}
~~~

This annotation **conditionally registers configuration/beans** based on the presence of declared resource locations.

`ResourcePatternResolver` is an imperative API that **discovers and returns resources** for the application to use.

| Criterion | `@ConditionalOnResource` | `ResourcePatternResolver` |
| --- | --- | --- |
| Role | Condition on bean/configuration | Resource-discovery API |
| Typical timing | During context configuration processing | When code calls the resolver |
| Output | Condition matches or not | `Resource[]` |
| Primary use | Enable configuration only when a resource exists | Retrieve multiple resources matching a pattern |
| Reads content | No | Caller opens `InputStream` |
| Replaces parse/validate | No | No |

For example, a module should only register if a fixed manifest file is present, and once enabled it scans multiple schemas:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(
        resources = "classpath:META-INF/myapp/manifest.json"
)
public class SchemaModuleConfiguration {

    @Bean
    SchemaCatalog schemaCatalog(ResourceLoader resourceLoader) {
        return new SchemaCatalog(resourceLoader);
    }
}
~~~

In this example `SchemaCatalog` is an application-designed class that uses the resolver to find schemas. Conditional registration and multi-resource discovery are separate responsibilities.

## 17. Comparing with ClassLoader.getResources and Files.walk

While all "find files", each API operates at a different abstraction level.

### 17.1. ClassLoader.getResources

Java's `ClassLoader` provides:

~~~java
Enumeration<URL> urls =
        Thread.currentThread()
                .getContextClassLoader()
                .getResources("META-INF/myapp/extensions.properties");
~~~

It is useful for locating multiple resources with the **exact same name** on the classpath.

However, this API does not directly resolve Ant-style patterns such as:

~~~text
schemas/**/*.json
~~~

`PathMatchingResourcePatternResolver` supplies the matching and resource-scanning layer for those cases.

### 17.2. Files.walk

Java NIO can traverse directories on the filesystem:

~~~java
try (Stream<Path> paths = Files.walk(Path.of("/opt/myapp/rules"))) {
    paths.filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

`Files.walk` fits when data definitely resides in a real directory. It does not descend into JARs on the classpath using `classpath*:` syntax.

### 17.3. Choosing the right tool

| Task | Suitable API |
| --- | --- |
| Read a single classpath file with a known name | `ResourceLoader.getResource` or `ClassPathResource` |
| Find multiple identically named resources across JARs | `ResourcePatternResolver.getResources` with `classpath*:` |
| Search by wildcard across the classpath | `PathMatchingResourcePatternResolver` |
| Traverse local directories with NIO features | `Files.walk` |
| List objects in S3/blob storage | Storage SDK/listing API |
| Register beans based on a resource's existence | `@ConditionalOnResource` |

When a storage system offers a dedicated listing/changelog API, using it is clearer and more reliable than trying to treat it as a filesystem.

## 18. Testing ResourcePatternResolver

Tests should verify that the pattern locates expected resources and that the code can read their content.

A sample test fixture structure:

~~~text
src/test/resources/
└── test-schemas/
    ├── one.json
    ├── two.json
    └── nested/
        └── three.json
~~~

### 18.1. Wildcard test with JUnit 5

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;

class ResourcePatternResolverTest {

    private final ResourcePatternResolver resolver =
            new PathMatchingResourcePatternResolver();

    @Test
    void findsJsonFilesRecursively() throws IOException {
        Resource[] resources = resolver.getResources(
                "classpath*:test-schemas/**/*.json"
        );

        assertThat(resources).hasSize(3);

        assertThat(
                Arrays.stream(resources)
                        .map(Resource::getFilename)
                        .toList()
        ).containsExactlyInAnyOrder(
                "one.json",
                "two.json",
                "three.json"
        );
    }
}
~~~

This test assumes `src/test/resources` contains exactly those three matching JSON files and no other dependency has fixtures matching the same pattern.

### 18.2. Testing an empty array

~~~java
@Test
void returnsEmptyArrayForNoMatches() throws IOException {
    Resource[] resources = resolver.getResources(
            "classpath*:folder-that-does-not-exist-xyz/**/*.json"
    );

    assertThat(resources).isEmpty();
}
~~~

No matches typically results in an empty array. However, if an error occurs reading a root or archive, the resolver can throw `IOException`; tests should also consider I/O failure behavior if the application defines a specific policy.

### 18.3. Testing content reading via stream

~~~java
@Test
void canReadSchemaFromClasspath() throws IOException {
    Resource[] resources = resolver.getResources(
            "classpath*:test-schemas/one.json"
    );

    assertThat(resources).hasSize(1);

    try (InputStream input = resources[0].getInputStream()) {
        String text = new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
        );

        assertThat(text).contains("type");
    }
}
~~~

Remember to import `java.io.InputStream` and `java.nio.charset.StandardCharsets`.

### 18.4. Testing execution from an executable JAR

A unit test in an IDE normally runs against built directory classpaths. To verify resource scanning inside a packaged Boot JAR, include an integration/smoke test running the packaged artifact itself:

~~~bash
java -jar target/schema-discovery-0.0.1-SNAPSHOT.jar
~~~

Check the number of discovered schemas and compare against what was actually packaged. Runtime testing here is especially important if libraries run in environments with nested JARs or custom classloaders.

## 19. Common Errors and How to Fix Them

### 19.1. Using getResource to match wildcards

**Wrong expectation:**

~~~java
resourceLoader.getResource("classpath*:schemas/**/*.json");
~~~

`getResource` has no contract for returning multiple resources from a wildcard.

**Correct API:**

~~~java
resolver.getResources("classpath*:schemas/**/*.json");
~~~

### 19.2. Only finding files in the first module

The code may be using `classpath:` instead of `classpath*:` when it actually needs to scan across all JARs.

**Fix:** use `classpath*:` and place files in a stable subdirectory packaged onto the classpath.

### 19.3. Failing to find files at the JAR root

A pattern like `classpath*:*.json` may not enumerate all root entries across every classloader/JAR.

**Fix:** place resources under `META-INF/myapp/...` or another subdirectory and search by a fixed prefix.

### 19.4. Works in IDE, fails in executable JAR

A common cause is calling `resource.getFile()` or `File` APIs on classpath resources packaged inside an archive.

**Fix:** read via `getInputStream()`; test from the packaged artifact.

### 19.5. Incorrect file count due to duplicate filenames

Two JARs can package resources with the same name. If the code deduplicates by `getFilename()`, a file gets dropped.

**Fix:** use a logical ID or an appropriate URL/source description, not just the trailing filename.

### 19.6. Scan order varies across machines

**Cause:** classpath and filesystem order are not business rules.

**Fix:** sort intentionally for logs; if rule application order matters, store priority/ID in metadata and handle it explicitly.

### 19.7. Missing resources after build

The file sits in `src/test/resources`, whereas the production application runs from `src/main/resources` and runtime dependencies.

**Fix:** verify which artifact contains the file, whether the build copies the resource, and whether the final path in the JAR matches the pattern.

### 19.8. Overly broad scanning slows startup

A pattern like `classpath*:**/*.xml` may scan many JARs and match unrelated files.

**Fix:** narrow the root directory and extension, e.g., `classpath*:META-INF/myapp/mappings/**/*.xml`.

### 19.9. Mistaking parser failures for resolver failures

The resolver only finds and opens resources; JSON/XML parsers, schema validators, or domain logic can raise their own errors.

**Fix:** log the source description and distinguish `IOException`, parsing exceptions, validation exceptions, and duplicate IDs.

### 19.10. Forgetting to close InputStream

**Cause:** code calls `getInputStream()` without `try-with-resources`.

**Fix:** close the stream on each resource after reading, especially for file and network resources.

### 19.11. Using URL wildcards to list remote files

An HTTP endpoint is not guaranteed to support listing files under a path like a filesystem.

**Fix:** use the remote storage's listing API; only use the resolver for location types the implementation actually supports.

### 19.12. Letting clients supply arbitrary file: patterns

**Risk:** leaking filesystem data or forcing the server to scan unrelated directories.

**Fix:** restrict patterns to trusted configuration, validate prefixes/roots, and never expose arbitrary resource contents on public endpoints.

## 20. Designing a Safe Multi-Resource Loading Workflow

When a project needs to discover multiple resources at startup, follow this sequence:

1. **Decide where resources live:** classpath or filesystem?
2. **Define a stable prefix:** e.g., `META-INF/myapp/rules/`.
3. **Choose the right pattern:** prefer an explicit root and `classpath*:` when multiple JARs are involved.
4. **Limit scope:** avoid scanning the entire classpath unnecessarily.
5. **Call `getResources(...)` and handle `IOException`** transparently.
6. **Decide whether zero matches is an error:** fail fast for required data; allow empty when optional.
7. **Read via `getInputStream()`** and close every stream.
8. **Parse/validate contents** using a parser suited to the file format.
9. **Detect duplicate IDs** and define explicit precedence rules.
10. **Store processed data in a catalog** to avoid re-scanning on every request.
11. **Test on the packaged runtime** if resources live inside JARs/nested JARs.
12. **Make failures observable:** log the resource description, pattern, match count, and failure cause.

A good catalog not only finds files, it also has clear rules for missing files, corrupted files, duplicate identifiers, or partially unreadable data.

## 21. Hands-on Exercises

### Exercise A: Finding multiple templates

Create:

~~~text
src/main/resources/templates/email/
├── welcome.html
├── goodbye.html
└── vi/
    └── welcome.html
~~~

Use:

~~~java
resolver.getResources(
        "classpath*:templates/email/**/*.html"
);
~~~

Print the file count, `getFilename()`, and `getDescription()`. Explain why two `welcome.html` files share the same filename yet come from different sources.

### Exercise B: Comparing * and **

With the same structure above, compare:

~~~text
classpath*:templates/email/*.html
classpath*:templates/email/**/*.html
~~~

Note which files are found in each case and explain the role of subdirectories.

### Exercise C: Using file: instead of classpath*:

Create `/tmp/myapp-rules` or a suitable directory on your machine containing two `.yml` files.

Try:

~~~java
resolver.getResources(
        "file:/tmp/myapp-rules/**/*.yml"
);
~~~

Observe the difference between external filesystem files and resources packaged inside a JAR.

### Exercise D: Reading from an executable JAR

Place a JSON file under `src/main/resources/schemas`, use the resolver to locate it, and read it with `getInputStream()`.

Run in the IDE, then package and run `java -jar`. Explain why switching to `getFile()` can break the JAR run.

### Exercise E: Two dependencies sharing a resource name

Create two library modules, each containing:

~~~text
META-INF/myapp/extensions.properties
~~~

Package both and add them to the runtime classpath. Use:

~~~java
resolver.getResources(
        "classpath*:META-INF/myapp/extensions.properties"
);
~~~

Compare with:

~~~java
resourceLoader.getResource(
        "classpath:META-INF/myapp/extensions.properties"
);
~~~

Explain the difference between a single resource location and multiple classpath locations with the same name.

### Exercise F: Detecting duplicate rule IDs

Create two JSON rules with the same `id` in different files. After the resolver locates the resources, parse them and fail fast if the catalog sees a duplicate ID.

Do not use the filename as the unique key.

### Exercise G: Pattern from configuration properties

Create:

~~~yaml
app:
  schema:
    location-pattern: classpath*:schemas/**/*.json
    required: true
~~~

Bind into `SchemaProperties`, inject it into a service, and then test replacing it with a non-matching pattern. When `required=true`, the application must report the missing resources clearly.

### Exercise H: Testing project resources

Add three JSON fixtures under `src/test/resources/test-schemas/`. Write a JUnit test for the recursive pattern, asserting file count and content.

Then add a file in a subdirectory and observe the test adapting without editing any filename in Java source.

## 22. Self-Check Questions

**1. What is `ResourcePatternResolver` used for?**

To resolve a location pattern into an array of `Resource[]`, supporting multi-resource discovery.

**2. How do `ResourceLoader.getResource` and `ResourcePatternResolver.getResources` differ?**

`getResource` returns a single resource location; `getResources` can return multiple resources matching a search pattern.

**3. What does the `classpath*:` prefix mean?**

It allows searching across all matching classpath locations, including resources across multiple modules/JARs.

**4. How do `*` and `**` differ?**

`*` matches within a single path segment; `**` can match across multiple directory levels.

**5. Why place resources under `META-INF/myapp/...`?**

To establish an explicit root directory, avoid wildcards at the JAR root, and limit scanning unrelated resources.

**6. Should you use `Resource.getFile()` for classpath resources in an executable JAR?**

Do not assume it works. Prefer `getInputStream()` to read files inside archives.

**7. Does the resolver automatically parse JSON or validate content?**

No. It only locates resources. The application must apply appropriate parsers and validators.

**8. Is the returned Resource array guaranteed to be sorted by name?**

Do not rely on result order. If ordering is required, sort using an explicit rule.

**9. Does finding no resources always throw an exception?**

No. An unmatched pattern normally returns an empty array. The application decides when an empty array is an error.

**10. Can you use `classpath*:META-INF/myapp/extensions.properties` even without wildcards in the path?**

Yes. The `classpath*:` prefix still locates multiple resources sharing the same name across the classpath.

**11. Should you call the resolver on every request to scan multiple JARs?**

Usually not if resources are static. Load the catalog when appropriate and cache the processed results, unless there is an explicit refresh requirement.

## 23. Conclusion

`ResourcePatternResolver` is Spring Framework's API for situations requiring **discovering multiple resources by path or wildcard**. The `PathMatchingResourcePatternResolver` implementation lets you use patterns like `classpath*:schemas/**/*.json` instead of manually enumerating every file.

The most important distinction is: `classpath:` typically targets a single classpath resource/location, while `classpath*:` searches across multiple classpath roots and JARs. The symbols `*`, `?`, and `**` help match filenames or directory trees. When scanning multiple JARs, use a clear root directory, do not assume result order, and do not treat filenames as unique identifiers.

When reading resources, prefer `getInputStream()` and close streams, because files may be packaged inside an executable JAR without a `java.io.File` path. Finally, remember the resolver only performs **discovery**: parsing, validating, handling duplicates, missing-resource policies, and path security remain the application's responsibility.

When paired with clear directory conventions and a validated catalog, `ResourcePatternResolver` helps Spring Boot systems scale templates, schemas, or metadata across modules without editing code to register each resource individually.

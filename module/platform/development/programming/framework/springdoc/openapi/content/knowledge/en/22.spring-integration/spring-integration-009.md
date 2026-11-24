# Compilation and Dependency Requirements for Javadoc Support

springdoc-openapi can use Javadoc in Java source code to supplement OpenAPI descriptions. This feature requires two Therapi components: the `therapi-runtime-javadoc-scribe` annotation processor running at compile time and the `therapi-runtime-javadoc` library present when the application runs.

The two components have distinct roles. The annotation processor reads Javadoc comments from source code and writes them as resources on the classpath. The runtime library reads those resources so springdoc-openapi can include the content in the OpenAPI document. Adding only the runtime library or only the annotation processor is not enough.

## 1. Where Is Javadoc Used?

According to springdoc-openapi's Javadoc integration, the following contents are mapped into OpenAPI:

| Javadoc location | Location in OpenAPI | Example |
|---|---|---|
| Method comment | `description` of `@Operation` | Describing the endpoint's purpose |
| Method `@return` tag | `description` of response | Explaining response data |
| DTO field/attribute comment | `description` of `@Schema` for the field | Explaining the property's meaning |

Controller example:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    /**
     * Find a product by identifier.
     *
     * @return product details matching the requested identifier
     */
    @GetMapping("/{id}")
    public ProductResponse getById(@PathVariable String id) {
        // Find and return the product
        return productService.findById(id);
    }
}

interface ProductService {
    ProductResponse findById(String id);
}
~~~

The comment on the method is used as the operation description; the `@return` content is used as the response description. To describe path parameter `id`, declare `@Parameter(description = "...")` or a corresponding annotation. Do not assume every Javadoc tag such as `@param` or `@throws` automatically becomes OpenAPI metadata.

The `@return` tag supplies a description for the response inferred by springdoc from the method. If an operation has multiple status codes or multiple response bodies, declare each response with `@ApiResponse` to describe the full contract.

DTO example:

~~~java
public class ProductResponse {

    /** Unique identifier of the product. */
    private String id;

    /** Display name of the product in the catalog. */
    private String name;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Field comments can become descriptions of the corresponding schema properties. Verify the final result in `/v3/api-docs`, because property names and schemas are also influenced by Jackson, accessors, and model converter configuration.

## 2. Why Are Both an Annotation Processor and a Runtime Library Needed?

Therapi splits the work into two phases:

1. **Compile time:** `therapi-runtime-javadoc-scribe` reads comments in Java sources and writes content into classpath resources during compilation.
2. **Runtime:** `therapi-runtime-javadoc` reads the generated resources so the application can retrieve Javadoc when springdoc builds OpenAPI.

| Component | When needed | Role |
|---|---|---|
| `therapi-runtime-javadoc-scribe` | Compile time | Annotation processor extracting Javadoc from source |
| `therapi-runtime-javadoc` | Runtime | Reads Javadoc packaged on the classpath |
| springdoc-openapi starter | Runtime | Uses metadata to generate OpenAPI JSON/YAML |

If the processor is missing, comments are never written into resources. If the runtime library is missing, the application has no component to read those resources. Springdoc documentation warns that the Javadoc feature can fail silently when either component is missing; therefore, do not check only whether the application starts successfully.

There is no need to run the `javadoc` command to generate HTML documentation. This mechanism uses an annotation processor during Java compilation and then reads metadata at runtime.

## 3. Choosing the Matching Springdoc Starter

Javadoc support does not replace the starter for your web stack. Choose the starter based on Spring MVC or WebFlux and UI requirements:

| Requirement | Commonly used starter |
|---|---|
| Spring MVC, OpenAPI JSON/YAML only | `springdoc-openapi-starter-webmvc-api` |
| Spring MVC, including Swagger UI | `springdoc-openapi-starter-webmvc-ui` |
| Spring WebFlux, OpenAPI JSON/YAML only | `springdoc-openapi-starter-webflux-api` |
| Spring WebFlux, including Swagger UI | `springdoc-openapi-starter-webflux-ui` |

Springdoc v2's Javadoc guide lists the `webmvc-api` and `webflux-api` starters when only the OpenAPI endpoint is needed. If the application needs Swagger UI, use the UI starter matching the web stack. Regardless of which starter is chosen, you must still configure the Therapi processor/runtime pair.

Examples below use springdoc v2 for Spring Boot 3 and Therapi version `0.15.0` as illustrated in springdoc v2 documentation. Choose a springdoc starter compatible with your project's Spring Boot line and manage versions consistently via BOM or dependency management.

Do not mix guides across major versions: springdoc v1 documentation previously instructed using the `springdoc-openapi-javadoc` artifact, whereas v2 guides use the `therapi-runtime-javadoc` and `therapi-runtime-javadoc-scribe` pair directly as shown below. For Spring Boot 4/springdoc v3, choose starters from the compatible line and consult the documentation for that exact major version before applying.

## 4. Maven Configuration

### 4.1. Adding the Runtime Library

In `pom.xml`, add the runtime library:

~~~xml
<dependency>
    <groupId>com.github.therapi</groupId>
    <artifactId>therapi-runtime-javadoc</artifactId>
    <version>0.15.0</version>
</dependency>
~~~

This library must be present on the application's runtime classpath. Do not place it in `test` or `provided` scope if the application needs to read Javadoc at runtime.

### 4.2. Registering the Annotation Processor in Maven Compiler Plugin

Add `therapi-runtime-javadoc-scribe` to `annotationProcessorPaths`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.github.therapi</groupId>
                        <artifactId>therapi-runtime-javadoc-scribe</artifactId>
                        <version>0.15.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

When using Spring Boot parent or the project's Maven plugin management, the compiler plugin version can be omitted if managed centrally. What matters is that the processor is actually on the processor path when compiling sources containing Javadoc.

If the project also uses Lombok, MapStruct, or other annotation processors, declare them in the same `annotationProcessorPaths`. When processor paths are configured explicitly, do not assume other processors will still be discovered automatically from the compile classpath.

### 4.3. Running a Clean Build

After changing configuration, run:

~~~bash
mvn clean package
~~~

`clean` removes old build output to avoid inspecting stale metadata from an earlier build. `package` compiles sources, runs annotation processors, and packages the application.

## 5. Gradle Configuration

With the Gradle Java plugin, declare the runtime library in `implementation` and the annotation processor in `annotationProcessor`:

~~~groovy
dependencies {
    implementation "com.github.therapi:therapi-runtime-javadoc:0.15.0"
    annotationProcessor "com.github.therapi:therapi-runtime-javadoc-scribe:0.15.0"
}
~~~

If using Gradle Kotlin DSL (`build.gradle.kts`):

~~~kotlin
dependencies {
    implementation("com.github.therapi:therapi-runtime-javadoc:0.15.0")
    annotationProcessor("com.github.therapi:therapi-runtime-javadoc-scribe:0.15.0")
}
~~~

`annotationProcessor` binds the processor to the Java compilation task. Do not place the processor in `implementation` as a substitute for this configuration; a runtime dependency does not guarantee the annotation processor is invoked.

Run a clean build:

~~~bash
./gradlew clean bootJar
~~~

On Windows you can run:

~~~powershell
.\gradlew.bat clean bootJar
~~~

If the project only builds a standard JAR, use the `jar` task instead of `bootJar` according to the applied plugins.

## 6. Build Environment Requirements

For Javadoc extraction to work reliably, verify the following conditions:

- Java sources containing comments must be compiled with `therapi-runtime-javadoc-scribe` on the processor path.
- Annotation processing is not disabled via compiler flags such as `-proc:none`.
- CI and developer machines use the same Maven/Gradle configuration, avoiding situations where an IDE produces different output than the build server.
- In IntelliJ IDEA, enable annotation processing in compiler settings if the IDE compiles sources itself.
- In multi-module projects, modules containing DTO/controller sources must run the processor during compilation.
- The runtime application must have `therapi-runtime-javadoc`, and resources generated by the processor must be packaged alongside the compiled classes or JAR of the processed sources.

If you build with Maven or Gradle while the IDE runs its own compiler, a successful terminal build does not guarantee the IDE generates the same metadata. Enable annotation processing in the IDE or delegate build/run actions to Maven/Gradle.

### 6.1. Multi-Module Projects

Suppose the project layout is:

~~~text
application/
  pom.xml
domain-api/
  pom.xml
  src/main/java/...
web-app/
  pom.xml
  src/main/java/...
~~~

If DTOs live in `domain-api`, the annotation processor must run when `domain-api` is compiled. Adding the processor only in `web-app` cannot retroactively extract comments from an already-compiled DTO JAR lacking metadata.

The final application needs the runtime library to read metadata from dependency JARs on the classpath. In Maven multi-module builds, compiler plugin configuration can be managed in the parent so modules containing documentable sources inherit it. In Gradle multi-project builds, declare `annotationProcessor` in each subproject with Java sources requiring processing.

## 7. Precedence Rules Between Javadoc and Swagger Annotations

Javadoc supplements descriptions from source code, while Swagger annotations give direct control over OpenAPI content. When both supply a description for the same target, springdoc prioritizes the Swagger annotation value.

Example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

/**
 * Find a product by ID from the catalog.
 */
@Operation(
    summary = "Look up product",
    description = "Official description used in OpenAPI."
)
@GetMapping("/{id}")
public ProductResponse getById(@PathVariable String id) {
    // ...
}
~~~

In this case, `description` from `@Operation` is used instead of the Javadoc comment. You can leverage this rule when you need to override a general comment with more precise contract wording.

Similarly, if a field has `@Schema(description = "...")`, the annotation value takes precedence for the schema property. Avoid maintaining two conflicting descriptions; when using an annotation to override, treat it as the authoritative documentation content.

## 8. Distinguishing Javadoc Extraction from -parameters

Some Java compiler settings are frequently confused with Javadoc reading:

| Configuration | Purpose |
|---|---|
| Therapi annotation processor | Extracts Javadoc comments into classpath resources |
| Therapi runtime library | Reads Javadoc resources when the application runs |
| Compiler option `-parameters` | Preserves method parameter names in bytecode so reflection can read parameter names |

`-parameters` does not extract Javadoc and does not replace `therapi-runtime-javadoc-scribe`. Conversely, Therapi does not replace `-parameters` if the project needs parameter names preserved for other reflection mechanisms.

To document parameters in OpenAPI, use `@Parameter` when precise text is needed. Do not rely on having the Javadoc processor to infer all descriptions for `@PathVariable`, `@RequestParam`, or `@RequestHeader`.

## 9. Verifying That Javadoc Reaches OpenAPI

After building and starting the application:

1. Open `/v3/api-docs`.
2. Locate the operation of a method with Javadoc.
3. Verify `description` contains the method comment text.
4. Verify the response description contains the `@return` text.
5. Locate the DTO schema and verify property descriptions contain field comment text.
6. If Swagger UI is available, open the operation and schema to verify rendered content.

Example partial expected OpenAPI output:

~~~yaml
paths:
  /products/{id}:
    get:
      description: Find a product by identifier.
      responses:
        "200":
          description: product details matching the requested identifier
components:
  schemas:
    ProductResponse:
      type: object
      properties:
        id:
          type: string
          description: Unique identifier of the product.
        name:
          type: string
          description: Display name of the product in the catalog.
~~~

The YAML above illustrates the expected result. Actual schema names, paths, statuses, and JSON structure depend on the controller, DTOs, Jackson, and the application's OpenAPI configuration.

If Javadoc does not appear, check in order:

1. Is the runtime dependency `therapi-runtime-javadoc` on the runtime classpath?
2. Is the annotation processor `therapi-runtime-javadoc-scribe` invoked when compiling the module containing sources?
3. Is annotation processing disabled in the IDE or build profile?
4. Does the JAR containing DTO/controller classes carry the metadata resources generated by the processor?
5. Is the application running the fresh artifact produced after `clean package` or `clean bootJar`?
6. Is a Swagger annotation `description` overriding Javadoc?

Springdoc documentation notes that missing Javadoc components may not prevent the application from starting. Therefore, `/v3/api-docs` returning HTTP 200 alone does not prove Javadoc was read.

## 10. Common Mistakes

**Adding only `therapi-runtime-javadoc`.** The runtime library cannot read source Javadoc if compilation did not run the annotation processor. Add `therapi-runtime-javadoc-scribe` to the processor path.

**Adding only the annotation processor.** The processor can generate resources, but the application lacks the runtime reader. Add `therapi-runtime-javadoc` to the runtime classpath.

**Placing the processor in `implementation`.** A regular dependency does not replace Gradle's `annotationProcessor` or Maven's `annotationProcessorPaths` configuration.

**IDE has annotation processing disabled.** Building from the IDE may fail to produce metadata. Enable annotation processing or build with Maven/Gradle.

**Configuring the processor only in the application module.** If Javadoc lives on DTOs in another module, the processor must run in the module containing those DTOs when it is compiled.

**Incremental builds retaining stale outputs.** Run `clean` and rebuild to verify extraction from current sources.

**Using both Javadoc and `@Operation` and seeing the annotation text.** This is springdoc's precedence rule. Swagger annotation descriptions win when both exist.

**Assuming `-parameters` enables Javadoc support.** That option retains parameter names in bytecode; it does not produce Javadoc resources.

**Assuming generating Javadoc HTML is sufficient.** Javadoc HTML created by the Maven Javadoc Plugin or the `javadoc` command does not replace the runtime metadata Therapi requires.

## 11. Pre-CI Verification Checklist

- [ ] Chose the springdoc starter matching Spring MVC or WebFlux.
- [ ] `therapi-runtime-javadoc` is on the runtime classpath.
- [ ] `therapi-runtime-javadoc-scribe` is on the annotation processor path.
- [ ] Therapi versions are managed consistently.
- [ ] Annotation processing is not disabled.
- [ ] Modules containing controllers/DTOs with Javadoc run the processor.
- [ ] Metadata resources are packaged into artifacts.
- [ ] CI performs a clean build before producing release artifacts.
- [ ] `/v3/api-docs` displays expected method, response, and field descriptions.
- [ ] Swagger annotation descriptions are used intentionally when overriding Javadoc.
- [ ] Javadoc extraction is not confused with the `-parameters` compiler option.

## References

- [springdoc-openapi v2 – Javadoc support](https://springdoc.org/v2/#javadoc-support): mapping Javadoc to operations, responses, and schemas; required dependencies and annotation processor.
- [Therapi Runtime Javadoc](https://github.com/dnault/therapi-runtime-javadoc): how the annotation processor writes Javadoc to classpath resources and the runtime library reads it back.
- [Therapi Runtime Javadoc Scribe on Maven Central](https://central.sonatype.com/artifact/com.github.therapi/therapi-runtime-javadoc-scribe): annotation processor artifact coordinates.
- [Maven Compiler Plugin – Annotation Processor Paths](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html#annotationProcessorPaths): configuring processor paths in Maven.
- [Gradle – Java Plugin dependency configurations](https://docs.gradle.org/current/userguide/java_plugin.html#sec:java_plugin_and_dependency_management): configuring `annotationProcessor` and runtime dependencies.

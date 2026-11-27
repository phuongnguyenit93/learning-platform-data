# Loading a Function from a Standalone JAR and Verifying Type Boundaries

Spring Cloud Function allows packaging business logic into a separate JAR and loading it into a host application. This enables developing and releasing functions independently, then invoking the same function across different adapters or runtimes.

In this hands-on lab, you will build a **pure Java function JAR** with no Spring dependencies, then load that JAR into a Spring Boot application using **spring-cloud-function-deployer**. The host application looks up the function via **FunctionCatalog**, invokes it, and verifies data types across the boundary between two class loaders.

You will perform:

1. Create a Maven project that packages the function as a standalone JAR.
2. Create a host application with the `spring-cloud-function-deployer` dependency.
3. Specify the JAR location and function implementation class using properties.
4. Look up the function from `FunctionCatalog` and invoke it with explicit generic types.
5. Test invalid inputs, wrong class names, and wrong JAR locations.
6. Analyze why two classes with the same fully-qualified name loaded by two different class loaders can still be two distinct runtime types.

> **Environment requirements:** JDK 17 or higher, Maven 3.8+, and a compatible Spring Boot/Spring Cloud pair. Use the Spring Cloud BOM matching your project's Spring Boot version. Never pick an isolated Spring Cloud Function version from an old example and mix it arbitrarily with your current Spring Boot version.

## 1. Expected Outcomes

The lab architecture consists of two independent applications:

```mermaid
flowchart LR
    A["normalize-sku-function.jar<br/>Pure Java JAR"]
    B["Function Host<br/>Spring Boot + deployer"]
    C["FunctionCatalog"]
    D["NormalizeSkuFunction<br/>Function<String, String>"]
    E["Result: SKU-42"]
    A -->|"location + function-class"| B
    B --> C --> D --> E
```

The function JAR contains a class implementing `Function<String, String>`. The host does not need a compile-time dependency on the function JAR; it only needs the artifact location and class name. The deployer starts the function archive in an isolated class loader and registers the function in the host's `FunctionCatalog`.

Expected result when the host invokes the function:

```text
Input : " sku-42 "
Output: "SKU-42"
```

The example uses `String` on both ends of the contract. `String` belongs to the Java platform and is shared across class loaders, allowing us to focus on observing the JAR loading mechanism before trying custom DTOs.

## 2. Preparing the Directory Structure

Create two independent Maven projects side by side:

```text
packaged-function-lab/
├── normalize-sku-function/
│   ├── pom.xml
│   └── src/
│       └── main/
│           └── java/
│               └── functions/
│                   └── NormalizeSkuFunction.java
└── function-host/
    ├── pom.xml
    └── src/
        └── main/
            └── java/
                └── demo/
                    └── host/
                        └── FunctionHostApplication.java
```

The two projects do not need to be a Maven multi-module build. The goal is to prove the function JAR is built independently and the host loads that artifact only at runtime.

## 3. Creating a Pure Java Function JAR

In `normalize-sku-function/pom.xml`, declare a minimal Java project:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lab.functions</groupId>
    <artifactId>normalize-sku-function</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

This project does not need `spring-boot-starter`, `spring-context`, or `spring-cloud-function-context`. It only needs Java's functional interface `java.util.function.Function`.

Create class `normalize-sku-function/src/main/java/functions/NormalizeSkuFunction.java`:

```java
package functions;

import java.util.Locale;
import java.util.function.Function;

public final class NormalizeSkuFunction
        implements Function<String, String> {

    public NormalizeSkuFunction() {
    }

    @Override
    public String apply(String input) {
        if (input == null) {
            throw new IllegalArgumentException(
                "SKU must not be null"
            );
        }

        String normalized = input.strip()
            .toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z0-9-]{1,32}")) {
            throw new IllegalArgumentException(
                "SKU must contain 1-32 letters, digits or hyphens"
            );
        }

        return normalized;
    }
}
```

A few important details:

- The class is `public` so the deployer can load and instantiate it.
- It has a public no-arg constructor so this simple packaging style can instantiate the class.
- The class directly implements `Function<String, String>`, so input/output generics can be discovered from the class declaration.
- The logic has no dependency on Spring, HTTP, brokers, or serverless.
- `Locale.ROOT` ensures consistent uppercase normalization regardless of the host machine's locale.

### Building the JAR

Open a terminal in `packaged-function-lab`:

```bash
mvn -f normalize-sku-function/pom.xml clean package
```

Expected artifact:

```text
normalize-sku-function/target/normalize-sku-function-1.0.0.jar
```

Verify the class is inside the JAR:

```bash
jar tf normalize-sku-function/target/normalize-sku-function-1.0.0.jar
```

You should see:

```text
functions/NormalizeSkuFunction.class
META-INF/
META-INF/MANIFEST.MF
```

This is a plain Java JAR, not a Spring Boot executable JAR. With this packaging format, the deployer must be given the function class name via `spring.cloud.function.function-class`.

## 4. Creating the Host Application

The host is a Spring Boot application. It includes the deployer and `FunctionCatalog`, without declaring any compile-time dependency on `normalize-sku-function`.

Create `function-host/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_COMPATIBLE_SPRING_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>lab.host</groupId>
    <artifactId>function-host</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>REPLACE_WITH_COMPATIBLE_SPRING_CLOUD_RELEASE_TRAIN</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-deployer</artifactId>
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
```

Replace the two version placeholders with a compatible Spring Boot/Spring Cloud release train pair per the official compatibility matrix.

The key dependency is:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-deployer</artifactId>
</dependency>
```

The deployer locates the configured JAR, launches the packaged function, and registers the function in the host's catalog. Without this dependency, setting `spring.cloud.function.location` alone does not enable JAR loading.

### Writing the Host Application

Create `function-host/src/main/java/demo/host/FunctionHostApplication.java`:

```java
package demo.host;

import java.util.function.Function;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootApplication
public class FunctionHostApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            FunctionHostApplication.class,
            args
        );
    }

    @Bean
    ApplicationRunner verifyPackagedFunction(
        FunctionCatalog catalog
    ) {
        return args -> {
            Function<String, String> normalizeSku =
                catalog.lookup("normalizeSkuFunction");

            if (normalizeSku == null) {
                throw new IllegalStateException(
                    "normalizeSkuFunction was not found in FunctionCatalog"
                );
            }

            String actual = normalizeSku.apply(" sku-42 ");
            String expected = "SKU-42";

            if (!expected.equals(actual)) {
                throw new IllegalStateException(
                    "Unexpected result: " + actual
                );
            }

            System.out.println(
                "Packaged function result: " + actual
            );
        };
    }
}
```

The host knows only the `Function<String, String>` contract. It does not import `functions.NormalizeSkuFunction` and does not compile directly against the implementation class in the external JAR.

## 5. Building the Host and Loading the JAR with the Deployer

Build the host:

```bash
mvn -f function-host/pom.xml clean package
```

Then run the host from `packaged-function-lab`:

```bash
java -jar function-host/target/function-host-1.0.0.jar \
  --spring.cloud.function.location=./normalize-sku-function/target/normalize-sku-function-1.0.0.jar \
  --spring.cloud.function.function-class=functions.NormalizeSkuFunction
```

Two important properties:

| Property | Value | Meaning |
| --- | --- | --- |
| `spring.cloud.function.location` | JAR path or resource URL | Specifies the archive containing the function |
| `spring.cloud.function.function-class` | `functions.NormalizeSkuFunction` | Specifies the function implementation class inside a simple JAR |

`location` can be a resource/URL. In this lab, relative paths are resolved from the working directory where you run the command. If running from another directory, use an absolute path or adjust the path.

### Expected Output

In the host logs, look for:

```text
Packaged function result: SKU-42
```

When this line appears, you have verified the entire sequence:

1. The host reads `spring.cloud.function.location`.
2. The deployer loads the standalone JAR.
3. The deployer locates `functions.NormalizeSkuFunction`.
4. The function is registered in `FunctionCatalog`.
5. The host looks up `normalizeSkuFunction` by name.
6. The host invokes the function with a `String` input and receives a `String` output.

The lookup name is derived from the class name following the function component camelCase convention. If you rename the class or bundle multiple functions, verify the exposed names and look up the exact name in the catalog.

## 6. Inspecting the Function in FunctionCatalog

`FunctionCatalog` does not merely return the raw Java object. A function looked up through the catalog is instrumented/wrapped by Spring Cloud Function to support capabilities like type conversion and composition.

Example:

```java
Function<String, String> normalizeSku =
    catalog.lookup("normalizeSkuFunction");

String result = normalizeSku.apply(" book-100 ");
// result = "BOOK-100"
```

Do not confuse retrieving a bean directly from `ApplicationContext` with looking it up through `FunctionCatalog`. Fetching a function bean directly may bypass features provided by the catalog.

### Testing Valid Input

Extend `ApplicationRunner` or write a test to verify:

```java
assertEquals(
    "BOOK-100",
    normalizeSku.apply(" book-100 ")
);
```

### Testing Invalid Business Input

The function explicitly rejects SKUs containing disallowed characters:

```java
assertThrows(
    IllegalArgumentException.class,
    () -> normalizeSku.apply("book/100")
);
```

Here the exception originates from business validation inside the function. In a real adapter, the exception may be mapped to an HTTP error or event failure per adapter policy.

### Automating Verification with Spring Boot Test

Create `src/test/java/demo/host/PackagedFunctionTests.java` in the host project. Run Maven from `function-host` so the relative path to the function project in the parent directory resolves reliably:

```java
package demo.host;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.file.Path;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@SpringBootTest
class PackagedFunctionTests {

    private static final Path FUNCTION_JAR = Path.of(
        "..",
        "normalize-sku-function",
        "target",
        "normalize-sku-function-1.0.0.jar"
    ).toAbsolutePath().normalize();

    @DynamicPropertySource
    static void functionProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.cloud.function.location",
            () -> FUNCTION_JAR.toUri().toString()
        );
        registry.add(
            "spring.cloud.function.function-class",
            () -> "functions.NormalizeSkuFunction"
        );
    }

    @Autowired
    FunctionCatalog catalog;

    @Test
    void loadsAndInvokesPackagedFunction() {
        Function<String, String> function =
            catalog.lookup("normalizeSkuFunction");

        assertNotNull(function);
        assertEquals("SKU-42", function.apply(" sku-42 "));
    }

    @Test
    void rejectsInvalidSku() {
        Function<String, String> function =
            catalog.lookup("normalizeSkuFunction");

        assertThrows(
            IllegalArgumentException.class,
            () -> function.apply("book/100")
        );
    }
}
```

Before running the tests, build the function JAR. Then run from `function-host`:

```bash
mvn test
```

This test verifies that the deployer loads the JAR before the test queries `FunctionCatalog`. If you change the working directory, update how `FUNCTION_JAR` is built so it points to the right artifact.

## 7. Checking Type Boundaries at Compile Time

The declaration:

```java
Function<String, String> normalizeSku =
    catalog.lookup("normalizeSkuFunction");
```

lets the compiler type-check the invocation:

```java
String normalized = normalizeSku.apply("sku-42");
```

The following call fails to compile:

```java
normalizeSku.apply(42);
```

Because `Function` is declared to accept `String`, passing an `int`/`Integer` violates the compile-time signature.

This is a **type boundary in host code**. It does not prove all external data is a `String`: HTTP bodies, broker bytes, or serverless events still must be converted and validated by the adapter before reaching the function.

### Generics Undergo Type Erasure at Runtime

Java generics are primarily checked at compile time and erased at runtime. Therefore, when using a raw type:

```java
@SuppressWarnings("rawtypes")
Function rawFunction = normalizeSku;
```

the compiler no longer protects inputs/outputs as it does for `Function<String, String>`. When passing non-conforming data, behavior depends on conversion wrappers and registered converters; conversion errors or runtime type failures can occur.

Never use raw `Function` in production code just to dodge generic errors. Keep explicit signatures in both the host and implementation classes.

## 8. Class Loader Boundary: Same Class Name Does Not Guarantee Same Type

The deployer runs packaged functions in an isolated class loader by default. This is beneficial when multiple function JARs carry different dependencies or Spring versions.

In Java, a class's runtime identity is tied to:

- Its binary fully-qualified name (e.g., `demo.contract.OrderRequest`).
- The class loader that defined that class.

If two class loaders define two classes both named `demo.contract.OrderRequest`, the JVM treats them as two distinct types. Hence:

```java
hostOrderRequestClass.isInstance(pluginObject)
```

can return `false` even when:

- `hostOrderRequestClass.getName()` and `pluginObject.getClass().getName()` are identical.
- Both classes have identical fields, constructors, and methods.
- Both `.class` files were compiled from the exact same source code.

### Why Did the Lab Start with String?

`String`, `byte[]`, and Java platform types are shared via the Java platform / parent-delegation class loader. They serve as simple boundary types when host and function are loaded independently.

For custom DTOs, you must make a deliberate architectural choice:

1. Use wire contracts such as JSON `String`, `byte[]`, or simple map structures, converting at one side.
2. Place DTOs in a shared contract JAR and ensure the class is loaded once via a shared class loader under a tested delegation configuration.
3. Use a versioned/schema-driven serialization protocol so neither side needs to share Java class identity.

Never simply copy the same DTO JAR into both host and plugin and assume you can cast across them.

### Extended Experiment with a DTO

Create an `OrderSummary` class in the function JAR and a class with the same fully-qualified name in the host. Have the function return an instance of the plugin's class, and receive the result on the host as `Object`:

```java
Object result = function.apply(jsonString);

System.out.println(result.getClass().getName());
System.out.println(result.getClass().getClassLoader());
System.out.println(hostOrderSummaryClass.getClassLoader());
System.out.println(
    hostOrderSummaryClass.isInstance(result)
);
```

Observe the output rather than guessing. If the class is defined by two separate loaders, `isInstance` will print `false`. If delegation causes both to reference the same class definition, the outcome may differ. The key lesson is to verify actual runtime class identity rather than relying on class names.

## 9. Verifying Type Conversion at the FunctionCatalog Boundary

`FunctionCatalog` supports type conversion on looked-up functions. This helps adapters or callers convert incoming payloads to the function's declared type when an appropriate converter exists.

For example, suppose a function declares `Function<String, String>` and an adapter receives a raw request body. Conversion can turn the transport payload into a `String` before invoking the function.

However, conversion does not replace validation:

- `contentType` must accurately describe the payload format.
- A converter must support both source and target types.
- Malformed JSON must still be rejected.
- A DTO across an incompatible class loader will not automatically become the host DTO merely because the class names match.
- Never assume every converter is registered in every adapter.

### Experiment

1. Keep the function contract as `Function<String, String>`.
2. Call the function through `FunctionCatalog` with a valid `String`.
3. Call through a real adapter with a matching JSON/text payload.
4. Try a mismatched content type.
5. Try a malformed payload.
6. Observe conversion errors versus validation exceptions from the function.

Distinguish boundary conversion errors from business validation errors. Adapters may map these two error categories differently.

## 10. Loading Multiple Function Classes from One JAR

A simple JAR can contain multiple function classes. Use `spring.cloud.function.function-class` to list fully-qualified class names separated by semicolons.

Example:

```bash
java -jar function-host/target/function-host-1.0.0.jar \
  --spring.cloud.function.location=./function-bundle/target/function-bundle-1.0.0.jar \
  "--spring.cloud.function.function-class=functions.NormalizeSkuFunction;functions.ReverseTextFunction"
```

Once loaded, look up each function by its respective catalog name:

```java
Function<String, String> normalize =
    catalog.lookup("normalizeSkuFunction");

Function<String, String> reverse =
    catalog.lookup("reverseTextFunction");
```

Function names should be verified against your version's naming conventions and actual logs/catalog output. Never guess function names solely from the JAR artifact name.

## 11. Distinguishing Three Packaged JAR Formats

Spring Cloud Function deployer supports several packaging styles:

| Archive Type | Contents | Function Selection Property |
| --- | --- | --- |
| Simple JAR | Pure Java class implementing `Function`/`Supplier`/`Consumer`, no Spring required | `spring.cloud.function.function-class` |
| Spring Boot JAR containing function class | JAR with Spring Boot dependencies, where the function class is specified directly | `spring.cloud.function.function-class` |
| Spring Boot application JAR | Standalone Spring Boot app where the function is a Spring bean | `spring.cloud.function.definition` |

With a Spring Boot application JAR, the archive contains a main class and function beans:

```java
@SpringBootApplication
public class PackagedFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            PackagedFunctionApplication.class,
            args
        );
    }

    @Bean
    Function<String, String> uppercase() {
        return String::toUpper;
    }
}
```

When loading this type of archive, use:

```bash
java -jar function-host/target/function-host-1.0.0.jar \
  --spring.cloud.function.location=./uppercase-app/target/uppercase-app-1.0.0.jar \
  --spring.cloud.function.definition=uppercase
```

Do not treat every JAR as a simple JAR with `function-class`. In a Spring Boot application JAR, functions are already registered as beans in the target application context; `definition` selects which bean/function to expose.

## 12. Using Maven Coordinates Instead of File Paths

The deployer also supports `maven:` locations to resolve artifacts from a Maven repository:

```text
maven://lab.functions:normalize-sku-function:1.0.0
```

Example run:

```bash
java -jar function-host/target/function-host-1.0.0.jar \
  --spring.cloud.function.location=maven://lab.functions:normalize-sku-function:1.0.0 \
  --spring.cloud.function.function-class=functions.NormalizeSkuFunction
```

The artifact must exist in the local Maven repository or a configured remote repository. For private repositories, configure credentials and repository access via secure Maven mechanisms. Never embed usernames/passwords in command history or source control.

### When to Use File Locations?

- Local labs and quick verification.
- Function JAR mounted from a trusted artifact directory.
- CI tests against a freshly built artifact.

### When to Use Maven Locations?

- Artifacts are already published to a repository.
- You want version management by group/artifact/version.
- You want the host to deploy functions by released artifact version.

In production, prefer immutable artifacts, explicit versions, and checksum/signature verification per supply-chain policy.

## 13. Intentional Error Testing

Perform each experiment and record the observed error messages:

| Experiment | Change | What to Observe |
| --- | --- | --- |
| Wrong JAR path | Point `location` to a non-existent file | Deployer fails to read the archive |
| Wrong class name | Set `function-class` to a non-existent class | Cannot load the function class |
| Wrong package | Omit the package prefix | Class cannot be found |
| Wrong function name | Look up a name absent from catalog | `lookup` returns null or reports missing function per API |
| Invalid domain input | Send an SKU containing `/` | Function throws `IllegalArgumentException` |
| Compile-time type error | Pass `Integer` to `Function<String, String>` | Compiler rejects it |
| Raw type | Use raw `Function` | Loses generic safety; conversion/runtime behavior depends on wrapper |
| Missing dependency | Function class references a library absent from target archive/classpath | May throw `NoClassDefFoundError` or initialization error |

Not all errors happen at the same phase. A class may load successfully and fail only when a method is invoked or a lazy dependency is touched.

### Diagnosing via Logs

When loading a JAR fails:

1. Verify the file exists and the process has read permissions.
2. Run `jar tf` to verify class paths inside the archive.
3. Verify the fully-qualified class name.
4. Confirm the class implements `Supplier`, `Function`, or `Consumer`.
5. Check constructors and instantiation requirements.
6. Verify dependencies inside the function JAR.
7. Enable appropriate logging for Spring Cloud Function deployer if needed.
8. Verify the function is registered before calling `lookup`.

## 14. Security Limitations of Isolated Class Loaders

**An isolated class loader is not a security sandbox.** The function JAR still runs in the same JVM process and typically inherits the OS, filesystem, network, environment, and resource permissions granted to the host process.

Load only trusted artifacts:

- Allow `location` only from controlled directories or repositories.
- Verify artifact checksums or cryptographic signatures.
- Keep approved artifacts immutable.
- Never allow end users to pass arbitrary JAR paths or URLs.
- Do not grant overly broad credentials to the host/function process.
- Restrict filesystem, network, and container permissions at runtime.
- Log the loaded function artifact version and source location.

If you must run untrusted third-party code, use process/container/VM boundaries and appropriate security policies; never rely on class loaders to isolate execution privileges.

## 15. Extension Practice: Verifying DTOs Across Class Loaders

Once the `String → String` lab succeeds, try a function that receives a formatted string and returns a custom DTO:

```java
package functions;

public record OrderSummary(
    String orderId,
    long totalVnd
) {}
```

```java
package functions;

import java.util.function.Function;

public class SummarizeOrderFunction
        implements Function<String, OrderSummary> {

    @Override
    public OrderSummary apply(String json) {
        // Lab input uses orderId:totalVnd format.
        String[] parts = json.split(":", 2);
        if (parts.length != 2) {
            throw new IllegalArgumentException("Expected orderId:totalVnd");
        }
        return new OrderSummary(parts[0], Long.parseLong(parts[1]));
    }
}
```

Package both `SummarizeOrderFunction` and `OrderSummary` into this variant's simple JAR, then run the host with `function-class` pointing to `functions.SummarizeOrderFunction`. On the host, receive the output as `Object`:

```java
import java.util.function.Function;

Function<String, Object> function =
    catalog.lookup("summarizeOrderFunction");

Object output = function.apply("ORD-101:130000");

System.out.println(output.getClass().getName());
System.out.println(output.getClass().getClassLoader());
```

If the host also declares its own `functions.OrderSummary` record with identical source code and fully-qualified name, test:

```java
package functions;

public record OrderSummary(
    String orderId,
    long totalVnd
) {}
```

Then check:

```java
import functions.OrderSummary;

boolean sameRuntimeType =
    OrderSummary.class.isInstance(output);

System.out.println("Same runtime type: " + sameRuntimeType);
```

If the two classes were defined by two different loaders, the result is `false`. Do not cast the output directly to the host's `OrderSummary` DTO; transfer via a wire representation or share the contract class through a properly designed and tested shared loader.

### Analysis Questions

1. Why does `String` cross the boundary more easily than a custom DTO?
2. If two DTOs share a name across different class loaders, will `equals()` or casting work as expected?
3. Where should the shared contract version live?
4. If the function JAR upgrades its JSON schema, can an older host still handle it?
5. Should compatibility be verified via unit tests, contract tests, or integration tests?

Record the class name, class loader, schema version, and conversion behavior. Do not rely solely on `toString()` output because it does not prove type identity.

## 16. Self-Check Exercises

**Exercise 1 — Packaging.** Why does `normalize-sku-function` not need `spring-boot-maven-plugin`?

*Answer:* It is a pure Java simple JAR, not launched as a Spring Boot application. The deployer loads the function class specified by `function-class`.

**Exercise 2 — Loading the archive.** Which property specifies the JAR location?

*Answer:* `spring.cloud.function.location`.

**Exercise 3 — Selecting the class.** For a simple JAR containing `functions.NormalizeSkuFunction`, which property specifies the class to load?

*Answer:* `spring.cloud.function.function-class=functions.NormalizeSkuFunction`.

**Exercise 4 — Lookup.** Why does the host use `FunctionCatalog.lookup(...)` instead of calling `new NormalizeSkuFunction()` directly?

*Answer:* The host has no compile-time dependency on the function class. The catalog provides the function registered and instrumented by Spring Cloud Function, enabling features like conversion and composition.

**Exercise 5 — Spring Boot archive.** If the target JAR is a Spring Boot application containing an `uppercase` bean, which property should select the function?

*Answer:* `spring.cloud.function.definition=uppercase`; that archive runs its own Spring application context and selects function beans by definition.

**Exercise 6 — Function naming.** Why should you not guess the catalog name solely from the artifact name?

*Answer:* Function names are derived from the function class/bean registration and naming conventions, not from `artifactId`. Always verify the class and catalog lookup name.

**Exercise 7 — Generics.** Why is `Function<String, String>` safer on the host than raw `Function`?

*Answer:* The compiler checks input and output types; raw types drop generic safety and push failures into runtime conversion or execution.

**Exercise 8 — Class loader.** Are two classes with the same fully-qualified name guaranteed to be the same runtime type?

*Answer:* No. Class identity also depends on the class loader that defined the class.

**Exercise 9 — DTO contract.** How can you reduce class-identity coupling between the host and function JAR?

*Answer:* Use wire types such as JSON Strings, byte arrays, or maps, or share a contract class loaded once by a common, verified loader.

**Exercise 10 — Maven location.** When using `maven://group:artifact:version`, where must the artifact reside?

*Answer:* In the local Maven repository or a configured Maven repository to which the host has access.

**Exercise 11 — Security.** Does an isolated class loader prevent a function JAR from reading the process's environment variables?

*Answer:* No. A class loader is not a security sandbox; the function runs with the permissions of the host process.

**Exercise 12 — Runtime error.** A function JAR loads successfully, but fails when `apply()` is called. What should you check?

*Answer:* Lazily referenced dependencies, validation, conversion, resource loading, and exceptions inside the function; loading the class successfully does not prove all code paths work.

## 17. Lab Completion Criteria

- [ ] `normalize-sku-function` builds as a pure Java JAR.
- [ ] The JAR contains `functions/NormalizeSkuFunction.class`.
- [ ] The host includes `spring-cloud-function-deployer` with no compile-time dependency on the function JAR.
- [ ] The deployer receives the correct `spring.cloud.function.location`.
- [ ] The deployer receives the correct `spring.cloud.function.function-class`.
- [ ] The function appears in `FunctionCatalog`.
- [ ] The host looks up the function by name and invokes it successfully.
- [ ] Valid input returns `SKU-42`.
- [ ] Business-invalid input is rejected.
- [ ] Understands how generic types and class loaders affect type boundaries.
- [ ] Distinguishes simple JARs from Spring Boot JARs / application JARs.
- [ ] Understands that an isolated class loader is not a security sandbox.

## 18. Key Takeaways

- **A function JAR can be built independently and loaded by the Spring Cloud Function deployer.**
- **`spring.cloud.function.location` specifies the archive; `spring.cloud.function.function-class` selects the class in a simple JAR.**
- **Spring Boot application JARs use `spring.cloud.function.definition` to select function beans.**
- **The deployer registers loaded functions in `FunctionCatalog`; the host can look up and invoke them via the catalog.**
- **Concrete generics such as `Function<String, String>` let the compiler guard type boundaries.**
- **Class identity consists of both class name and class loader; two classes with the same name can still be different runtime types.**
- **Use `String`/`byte[]`/wire schemas or a controlled shared contract loader when crossing class loader boundaries.**
- **An isolated class loader is not a sandbox; load only trusted artifacts and restrict process permissions.**

**Official References:**

- [Spring Cloud Function — Deploying a Packaged Function](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/deploying-a-packaged.html)
- [Spring Cloud Function — Programming Model and FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html)
- [Spring Cloud — Supported Versions and Release Trains](https://spring.io/projects/spring-cloud#overview)
- [Java Language Specification — Classes and Objects](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html)

Paths and APIs in this lab should be re-verified against your project's exact Spring Boot/Spring Cloud release train. This lab demonstrates JAR loading and type boundary checks; it does not imply that arbitrary function archives or untrusted dependencies are safe to run inside the same process.

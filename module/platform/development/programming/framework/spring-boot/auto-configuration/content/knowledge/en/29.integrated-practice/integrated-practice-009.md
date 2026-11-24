# Packaging Autoconfigure with Starter and Consuming from a Standalone Spring Boot Project

## 1. Goals and Expected Outcomes

A Java library might work well inside its own repository, yet users still struggle to integrate it into another Spring Boot application. They must add multiple dependencies manually, declare beans themselves, remember default configurations, and manage compatible versions.

A Spring Boot starter solves that experience with one intentional dependency: the application simply declares the library's starter, and the starter pulls in the core library, the auto-configuration module, and the required foundation dependencies.

This guide builds an example library named `Acme Widget`, packaged into three artifacts:

- `acme-widget-client`: core Java library containing `WidgetClient`.
- `acme-widget-spring-boot-autoconfigure`: contains `@AutoConfiguration`, properties, and the auto-configuration registration resource.
- `acme-widget-spring-boot-starter`: dependency-aggregating artifact so applications can start using the library.

Next, we create an independent consumer project outside the multi-module build, publish the artifacts to the Maven local repository, add just the single starter dependency, and run the application to verify auto-configuration is discovered from the JAR.

**Final result:** the consumer declares only `com.acme:acme-widget-spring-boot-starter`; Spring Boot automatically finds `WidgetClientAutoConfiguration`, binds `acme.widget.*` configuration, and creates the default `WidgetClient`.

## 2. Distinguishing Core Library, Autoconfigure, and Starter

| Artifact | Responsibility | Needs Java classes? |
| --- | --- | --- |
| `acme-widget-client` | API and implementation independent of Spring Boot | Yes |
| `acme-widget-spring-boot-autoconfigure` | Creates default beans, reads properties, conditions, customizers, and imports descriptor | Yes |
| `acme-widget-spring-boot-starter` | Aggregates commonly needed dependencies to use the library | Usually no |

The autoconfigure module is the Spring integration part. It knows how to turn properties and present dependencies into beans inside the ApplicationContext.

The starter is a dependency-oriented artifact. It is typically a JAR nearly empty of code; its main value lies in its POM declaring dependencies on the autoconfigure module, the core library, and `spring-boot-starter`. Therefore, finding no auto-configuration classes when inspecting the starter JAR is completely normal. Classes and the imports resource reside in the autoconfigure JAR.

You can merge the two modules if a library is small, has no optional features, and does not need users to build custom starters. Keeping them separate is beneficial when the library has multiple flavors, web/reactive integrations, or dependencies needed by only some applications.

## 3. Flow from Source Code to Consuming Application

~~~mermaid
flowchart TD
    A["acme-widget-client<br/>WidgetClient"] --> B["acme-widget-spring-boot-autoconfigure<br/>AutoConfiguration + properties + imports"]
    B --> C["acme-widget-spring-boot-starter<br/>Dependency aggregator"]
    A --> C
    D["Independent consumer project"] --> C
    C --> E["Maven/Gradle resolves dependency graph"]
    E --> F["Spring Boot reads AutoConfiguration.imports"]
    F --> G["WidgetClientAutoConfiguration"]
    G --> H["Bind acme.widget.*"]
    H --> I["Create WidgetClient if no custom bean exists"]
~~~

Stages to distinguish:

1. **Build:** Maven/Gradle compiles each module and packages its JAR.
2. **Publish:** artifacts and POMs are placed into a local or remote Maven repository.
3. **Dependency resolution:** the consumer downloads the starter and transitive dependencies.
4. **Auto-configuration discovery:** Spring Boot reads the `AutoConfiguration.imports` resource inside the autoconfigure JAR.
5. **Condition evaluation:** Boot checks the classpath and existing beans.
6. **Bean creation:** the container instantiates beans following the dependency graph after configurations are processed.

The starter solves only dependency resolution. Auto-configuration discovery still depends on the imports resource in the right JAR.

## 4. Naming and Versioning Rules

Use the library's namespace:

- `groupId`: `com.acme`
- Core `artifactId`: `acme-widget-client`
- Autoconfigure `artifactId`: `acme-widget-spring-boot-autoconfigure`
- Starter `artifactId`: `acme-widget-spring-boot-starter`

Do not start module names with `spring-boot-`, as that prefix should be reserved for modules provided by the Spring Boot project itself. Using your own namespace avoids name collisions and clearly identifies artifact ownership.

In the example, the whole library uses version `1.0.0-SNAPSHOT` and Spring Boot `3.3.13`. The consumer also uses Spring Boot `3.3.13`. In real applications, manage a clear compatible version, test across supported Spring Boot versions, and never let individual modules pick differing versions of the core library.

When using a Maven BOM, declare `spring-boot-dependencies` in `dependencyManagement`. A BOM manages versions; it does not automatically add dependencies to modules. Each module must still declare the artifacts its source or runtime requires.

## 5. Multi-Module Repository Structure

Create a repository directory for the library:

~~~text
acme-widget/
├── pom.xml
├── acme-widget-client/
│   ├── pom.xml
│   └── src/main/java/com/acme/widget/client/
│       └── WidgetClient.java
├── acme-widget-spring-boot-autoconfigure/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/com/acme/widget/autoconfigure/
│       │   │   ├── WidgetClientAutoConfiguration.java
│       │   │   └── WidgetClientProperties.java
│       │   └── resources/META-INF/spring/
│       │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│       └── test/java/com/acme/widget/autoconfigure/
│           └── WidgetClientAutoConfigurationTests.java
└── acme-widget-spring-boot-starter/
    └── pom.xml
~~~

The consumer is a separate project, outside the root modules list:

~~~text
workspace/
├── acme-widget/
│   └── ... multi-module library ...
└── widget-consumer/
    ├── pom.xml
    └── src/
        ├── main/
        │   ├── java/com/example/consumer/
        │   │   └── ConsumerApplication.java
        │   └── resources/application.properties
        └── test/java/com/example/consumer/
            └── ConsumerApplicationTests.java
~~~

Keeping the consumer outside the reactor is intentional in this lab. It proves the artifacts were packaged and published properly, rather than working solely because the Maven reactor sees sibling source modules.

## 6. Parent POM Managing Modules and Versions

File `acme-widget/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.acme</groupId>
    <artifactId>acme-widget-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <spring-boot.version>3.3.13</spring-boot.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <modules>
        <module>acme-widget-client</module>
        <module>acme-widget-spring-boot-autoconfigure</module>
        <module>acme-widget-spring-boot-starter</module>
    </modules>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                    <configuration>
                        <release>${maven.compiler.release}</release>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.2.5</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

The root uses `pom` packaging because it is an aggregator and parent. `modules` lists the child modules. The Maven reactor reads dependency relationships to determine build order; the order in the list does not replace dependency declarations.

`dependencyManagement` imports the Spring Boot BOM so modules share consistent versions of `spring-boot-autoconfigure`, `spring-boot-starter`, and test dependencies without repeating versions in every POM.

## 7. Creating the Spring-Independent Core Library

File `acme-widget-client/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-widget-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-widget-client</artifactId>
</project>
~~~

File `WidgetClient.java`:

~~~java
package com.acme.widget.client;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Objects;

public final class WidgetClient {

    private final URI baseUrl;
    private final Duration connectTimeout;
    private final HttpClient httpClient;

    public WidgetClient(URI baseUrl, Duration connectTimeout) {
        this.baseUrl = Objects.requireNonNull(baseUrl, "baseUrl");
        this.connectTimeout = Objects.requireNonNull(
                connectTimeout, "connectTimeout");

        if (connectTimeout.isZero() || connectTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "connectTimeout must be positive");
        }

        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .build();
    }

    public URI baseUrl() {
        return this.baseUrl;
    }

    public Duration connectTimeout() {
        return this.connectTimeout;
    }

    public HttpResponse<String> get(String path)
            throws IOException, InterruptedException {

        URI target = this.baseUrl.resolve(path);
        HttpRequest request = HttpRequest.newBuilder(target)
                .GET()
                .build();

        return this.httpClient.send(
                request, HttpResponse.BodyHandlers.ofString());
    }
}
~~~

This class uses only Java 17 APIs and does not depend on Spring. That allows plain Java applications to use the core library without Spring Boot. The autoconfigure module adds the Spring integration layer in the next step.
## 8. Autoconfigure Module POM

File `acme-widget-spring-boot-autoconfigure/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-widget-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-widget-spring-boot-autoconfigure</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-widget-client</artifactId>
            <version>${project.version}</version>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>${spring-boot.version}</version>
                        </path>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                            <version>${spring-boot.version}</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `acme-widget-client` dependency is marked optional. The autoconfigure module needs the core library to compile, yet depending on autoconfigure does not automatically force every consumer to pull in the core library if they only want to reuse metadata or build their own custom starter.

The standard starter will declare the core library explicitly. This is a key aspect of Maven optional dependencies: it remains a dependency of the autoconfigure module itself, yet is not automatically propagated transitively to consumers.

The two annotation processors have distinct roles:
- `spring-boot-autoconfigure-processor` collects auto-configuration condition metadata so Boot can filter out non-matching configurations early.
- `spring-boot-configuration-processor` generates `META-INF/spring-configuration-metadata.json`, supporting IDE property hints and descriptions.

Processors are declared in `annotationProcessorPaths`, not as runtime dependencies of the application.

## 9. Defining Configuration Properties

File `WidgetClientProperties.java`:

~~~java
package com.acme.widget.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.widget")
public class WidgetClientProperties {

    /**
     * Base URI used by the Widget service.
     */
    private URI baseUrl = URI.create("https://api.example.test");

    /**
     * Timeout for establishing a connection to the Widget service.
     */
    private Duration connectTimeout = Duration.ofSeconds(2);

    public URI getBaseUrl() {
        return this.baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return this.connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Use the dedicated namespace `acme.widget`. Do not place library properties in namespaces reserved for Spring Boot such as `spring`, `server`, or `management`.

Use `Duration` so users can specify clear units such as `1500ms`, `2s`, or `1m`. Default values inside the class let the library run even when consumers do not declare any properties.

## 10. Creating AutoConfiguration and Classpath Conditions

File `WidgetClientAutoConfiguration.java`:

~~~java
package com.acme.widget.autoconfigure;

import com.acme.widget.client.WidgetClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class WidgetClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(WidgetClient.class)
    @EnableConfigurationProperties(WidgetClientProperties.class)
    static class WidgetClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        WidgetClient widgetClient(WidgetClientProperties properties) {
            return new WidgetClient(
                    properties.getBaseUrl(),
                    properties.getConnectTimeout());
        }
    }
}
~~~

Several design choices in this example:

- `@AutoConfiguration` marks the library's entry point.
- `@ConditionalOnClass` ensures client creation applies only when the core library is actually present.
- Conditional configuration is placed in a separate nested `@Configuration`. This separation is useful when methods or return types reference classes from optional dependencies.
- `@EnableConfigurationProperties` registers the properties class.
- `@ConditionalOnMissingBean` lets applications provide their own `WidgetClient` when a different implementation is needed.
- The `@Bean` method returns the concrete type `WidgetClient`, giving conditions and the container complete bean type information.

Do not use `@ComponentScan` inside auto-configuration to locate library classes. Register auto-configurations via imports and use explicit `@Import` if other supporting configurations are needed.

## 11. Registering Auto-Configuration via the Imports Resource

Create the exact file:

~~~text
acme-widget-spring-boot-autoconfigure/
└── src/main/resources/
    └── META-INF/
        └── spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File content, one class per line:

~~~text
com.acme.widget.autoconfigure.WidgetClientAutoConfiguration
~~~

Names in the file are fully qualified class names (FQCNs), without `.java` or `.class` suffixes. This file must be packaged inside the published autoconfigure JAR.

In Spring Boot 3.x, this is the standard resource for publishing auto-configuration candidates. `spring.factories` from older versions is no longer a way to register `EnableAutoConfiguration` in place of this file. `spring.factories` may still be needed for certain other extension points.

Do not add auto-configuration classes to the application's component scan. The imports mechanism is the module's official discovery path.

## 12. Creating the Starter Module Solely to Aggregate Dependencies

File `acme-widget-spring-boot-starter/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-widget-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-widget-spring-boot-starter</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-widget-spring-boot-autoconfigure</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-widget-client</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
~~~

The starter has three dependencies:

1. `spring-boot-starter`: provides foundational Spring Boot components.
2. `acme-widget-spring-boot-autoconfigure`: provides auto-configuration and properties.
3. `acme-widget-client`: provides the core implementation required by auto-configuration.

There is no need to add Java classes to the starter. Maven still produces a JAR and a POM; the POM is the essential piece because it describes the dependency graph consumers receive.

Do not bundle every optional integration into the default starter. If a library has web, reactive, or database modules needed by only a subset of applications, create separate flavor starters or document additional dependencies to avoid pulling in unused libraries.

## 13. Building and Testing Modules in the Repository

From the `acme-widget` directory, run:

~~~bash
mvn clean verify
~~~

`verify` runs earlier phases, including compile, test, and package. If the modules build successfully, proceed to install into the local repository:

~~~bash
mvn clean install
~~~

The Maven reactor builds all modules in the same run. Since the starter depends on autoconfigure and client, Maven determines build order from the dependency graph.

To build only the starter along with its required dependency modules:

~~~bash
mvn -pl acme-widget-spring-boot-starter -am clean install
~~~

The `-pl` option selects projects; `-am` tells Maven to also build projects that the selected project depends on. For multi-module libraries, this is a handy way to publish a starter together with its internal artifacts.

## 14. Inspecting JAR Contents After Building

Inspect the autoconfigure JAR:

~~~bash
jar tf acme-widget-spring-boot-autoconfigure/target/acme-widget-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar
~~~

The listing should include entries similar to:

~~~text
com/acme/widget/autoconfigure/WidgetClientAutoConfiguration.class
com/acme/widget/autoconfigure/WidgetClientProperties.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
META-INF/spring-configuration-metadata.json
~~~

Both metadata files depend on the annotation processors finding metadata to generate. Inspect the actual files after building; do not assume merely declaring a processor guarantees every property has an accurate description.

On Windows PowerShell, filter the imports resource:

~~~powershell
jar tf acme-widget-spring-boot-autoconfigure/target/acme-widget-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar |
    Select-String "AutoConfiguration.imports"
~~~

On macOS/Linux:

~~~bash
jar tf acme-widget-spring-boot-autoconfigure/target/acme-widget-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar |
    grep "AutoConfiguration.imports"
~~~

To read the resource content from the JAR, extract it into a temporary directory:

~~~bash
mkdir inspect-autoconfigure
cd inspect-autoconfigure
jar xf ../acme-widget-spring-boot-autoconfigure/target/acme-widget-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Open the extracted file and verify the FQCN matches the compiled class exactly. If the file exists in source yet is missing from the JAR, check the resource location, includes/excludes settings, and module source sets.

Inspect the starter JAR separately:

~~~bash
jar tf acme-widget-spring-boot-starter/target/acme-widget-spring-boot-starter-1.0.0-SNAPSHOT.jar
~~~

The starter may contain only `META-INF/MANIFEST.MF` and basic JAR metadata. That is normal; classes and imports belong to the autoconfigure JAR.
## 15. Testing the Descriptor and Auto-Configuration in the Module

Add the test `WidgetClientAutoConfigurationTests.java`:

~~~java
package com.acme.widget.autoconfigure;

import java.net.URI;
import java.time.Duration;

import com.acme.widget.client.WidgetClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.annotation.ImportCandidates;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class WidgetClientAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            WidgetClientAutoConfiguration.class));

    @Test
    void descriptorContainsAutoConfigurationClass() {
        ImportCandidates candidates = ImportCandidates.load(
                AutoConfiguration.class, getClass().getClassLoader());

        assertThat(candidates.getCandidates())
                .contains(WidgetClientAutoConfiguration.class.getName());
    }

    @Test
    void createsClientFromProperties() {
        this.runner
                .withPropertyValues(
                        "acme.widget.base-url=https://test.example.test",
                        "acme.widget.connect-timeout=750ms")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(WidgetClient.class);

                    WidgetClient client = context.getBean(WidgetClient.class);
                    assertThat(client.baseUrl())
                            .isEqualTo(URI.create("https://test.example.test"));
                    assertThat(client.connectTimeout())
                            .isEqualTo(Duration.ofMillis(750));
                });
    }

    @Test
    void backsOffWhenApplicationProvidesItsOwnClient() {
        this.runner
                .withUserConfiguration(UserClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(WidgetClient.class);
                    assertThat(context.getBean(WidgetClient.class).baseUrl())
                            .isEqualTo(URI.create("https://custom.example.test"));
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        WidgetClient customWidgetClient() {
            return new WidgetClient(
                    URI.create("https://custom.example.test"),
                    Duration.ofSeconds(1));
        }
    }
}
~~~

The `descriptorContainsAutoConfigurationClass` test verifies that the imports resource contains the right candidate. The remaining two tests verify property binding and back-off behavior of the default bean.

Important note: `ApplicationContextRunner` with `AutoConfigurations.of(WidgetClientAutoConfiguration.class)` loads the class directly. It verifies conditions and bean behavior, yet does not by itself prove the starter delivers the descriptor to a consuming application. Therefore, an integration test in an independent project is needed.

## 16. Publishing Artifacts to the Maven Local Repository

From the library root, run:

~~~bash
mvn clean install
~~~

Maven installs each module's POM, JAR, and metadata into the default local repository, usually:

~~~text
%USERPROFILE%\.m2\repository\com\acme\
~~~

On macOS/Linux, the default location is usually:

~~~text
~/.m2/repository/com/acme/
~~~

The artifact structure may look like:

~~~text
com/acme/
├── acme-widget-parent/1.0.0-SNAPSHOT/
├── acme-widget-client/1.0.0-SNAPSHOT/
├── acme-widget-spring-boot-autoconfigure/1.0.0-SNAPSHOT/
└── acme-widget-spring-boot-starter/1.0.0-SNAPSHOT/
~~~

`mvn install` is appropriate when developing and testing on the same machine. It does not publish to Maven Central or a team-shared repository.

Do not use `install:install-file` for modules just built in a normal Maven reactor. That goal is mainly for installing an external JAR lacking a corresponding build project/POM. With a multi-module project, `mvn install` preserves each module's POM and dependency graph accurately.

## 17. Creating an Independent Consumer Project

Create a `widget-consumer` directory alongside `acme-widget`. The consumer has its own POM and does not declare the library modules in `<modules>`.

File `widget-consumer/pom.xml`:

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
    <artifactId>widget-consumer</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <acme-widget.version>1.0.0-SNAPSHOT</acme-widget.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-widget-spring-boot-starter</artifactId>
            <version>${acme-widget.version}</version>
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

The consumer declares only the custom starter. It does not need to separately declare `spring-boot-autoconfigure` or `acme-widget-client`, because the starter already supplies the required dependencies.

This is a critical packaging test: if the consumer works only when opened in the same reactor as the source modules, yet fails after `mvn install`, dependencies or artifact metadata may be incomplete.

## 18. Using WidgetClient from the Consumer Without Declaring @Bean

File `ConsumerApplication.java`:

~~~java
package com.example.consumer;

import com.acme.widget.client.WidgetClient;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
    }

    @Bean
    CommandLineRunner showWidgetClient(WidgetClient widgetClient) {
        return args -> {
            System.out.println(
                    "WidgetClient baseUrl=" + widgetClient.baseUrl());
            System.out.println(
                    "connectTimeout=" + widgetClient.connectTimeout());
        };
    }
}
~~~

File `src/main/resources/application.properties`:

~~~properties
acme.widget.base-url=https://sandbox.example.test
acme.widget.connect-timeout=1500ms
~~~

The consumer declares neither `@Bean WidgetClient` nor `@Import(WidgetClientAutoConfiguration.class)`. Spring Boot automatically reads imports inside the autoconfigure JAR, registers the configuration, binds properties, and creates the default bean.

Run from the consumer directory:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Application stdout contains two lines printed by `CommandLineRunner`:

~~~text
WidgetClient baseUrl=https://sandbox.example.test
connectTimeout=PT1.5S
~~~

`PT1.5S` is the ISO-8601 representation of `Duration.ofMillis(1500)`. The program sends no HTTP requests, so auto-configuration can be verified without a live external endpoint.

## 19. Writing an Integration Test in the Consumer

Create `ConsumerApplicationTests.java`:

~~~java
package com.example.consumer;

import java.net.URI;
import java.time.Duration;

import com.acme.widget.client.WidgetClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ConsumerApplicationTests {

    @Autowired
    private WidgetClient widgetClient;

    @Test
    void starterMakesWidgetClientAvailable() {
        assertThat(this.widgetClient).isNotNull();
        assertThat(this.widgetClient.baseUrl())
                .isEqualTo(URI.create("https://sandbox.example.test"));
        assertThat(this.widgetClient.connectTimeout())
                .isEqualTo(Duration.ofMillis(1500));
    }
}
~~~

This test runs inside the real consumer application. Because the test does not directly import `WidgetClientAutoConfiguration`, it exercises the starter dependency, autoconfigure JAR, imports resource, and property binding together.

If tests pass yet running the packaged application fails, inspect the dependency tree and contents of the deployed artifact.

## 20. Inspecting the Consumer's Dependency Graph

From `widget-consumer`, run:

~~~bash
mvn dependency:tree -Dincludes=com.acme
~~~

The dependency tree should show at minimum:

~~~text
com.example:widget-consumer
\- com.acme:acme-widget-spring-boot-starter
   +- com.acme:acme-widget-spring-boot-autoconfigure
   \- com.acme:acme-widget-client
~~~

If `acme-widget-client` does not appear, check the starter POM. If autoconfigure does not appear, the consumer might have misdeclared the artifactId or version. If Maven cannot find the artifacts, verify `mvn install` succeeded and the consumer's version matches the installed version.

You can instruct Maven to refresh metadata when using a remote repository:

~~~bash
mvn -U clean test
~~~

With a local repository, `-U` does not replace reinstalling new artifacts. When source changes, re-run `mvn install` from the library root before testing the consumer.

## 21. Publishing to a Remote Maven Repository

When sharing artifacts with a team or CI, publish to a repository manager such as Nexus, Artifactory, or GitHub Packages. Declare `distributionManagement` in the parent POM or configure per your organization's repository standards:

~~~xml
<distributionManagement>
    <repository>
        <id>acme-releases</id>
        <url>https://repo.example.test/maven-releases</url>
    </repository>
    <snapshotRepository>
        <id>acme-snapshots</id>
        <url>https://repo.example.test/maven-snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

Place credentials in Maven's `settings.xml`, matching the repository `id`:

~~~xml
<servers>
    <server>
        <id>acme-releases</id>
        <username>YOUR_USERNAME</username>
        <password>YOUR_TOKEN</password>
    </server>
    <server>
        <id>acme-snapshots</id>
        <username>YOUR_USERNAME</username>
        <password>YOUR_TOKEN</password>
    </server>
</servers>
~~~

The values above are illustrative placeholders; use real credentials issued by your organization and never commit tokens/passwords into source repositories.

After configuring the repository and permissions, publish from root:

~~~bash
mvn clean deploy
~~~

Maven chooses the release repository or snapshot repository based on the version. Consumers on other machines need to declare the corresponding repository in `pom.xml` or `settings.xml`, then depend on the published version.

For production, prefer immutable release versions instead of reusing the same version for different artifact contents. Modifying code while keeping the same release version causes repository and consumer caches to make debugging very difficult.
## 22. Gradle: Equivalent Dependencies and Publishing

If the project uses Gradle, keep the same module boundaries. `settings.gradle.kts`:

~~~kotlin
rootProject.name = "acme-widget"

include(
    "acme-widget-client",
    "acme-widget-spring-boot-autoconfigure",
    "acme-widget-spring-boot-starter"
)
~~~

In the autoconfigure module, use `java-library` to distinguish exposed dependencies from compile-only dependencies:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

dependencies {
    api("org.springframework.boot:spring-boot-autoconfigure:3.3.13")
    compileOnly(project(":acme-widget-client"))

    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor:3.3.13"
    )
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor:3.3.13"
    )

    testImplementation(project(":acme-widget-client"))
    testImplementation(
        "org.springframework.boot:spring-boot-starter-test:3.3.13"
    )
}
~~~

`compileOnly` expresses that the core client is an optional dependency for someone using only the autoconfigure module. The starter will bring the core client into runtime.

In the starter module:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

dependencies {
    api("org.springframework.boot:spring-boot-starter:3.3.13")
    api(project(":acme-widget-spring-boot-autoconfigure"))
    api(project(":acme-widget-client"))
}
~~~

For modules to be published, configure the publication:

~~~kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
~~~

After applying `maven-publish` and configuring publications for the modules to distribute, run:

~~~bash
./gradlew publishToMavenLocal
~~~

A Gradle consumer can declare the repository and dependency:

~~~kotlin
repositories {
    mavenLocal()
    mavenCentral()
}

dependencies {
    implementation("com.acme:acme-widget-spring-boot-starter:1.0.0-SNAPSHOT")
}
~~~

`mavenLocal()` suits single-machine development. For CI or teams, use a shared repository rather than relying on individual developers' local caches. Manage a consistent Spring Boot BOM/plugin so dependency versions do not drift between modules and consumers.

## 23. Compatibility and Design Points to Review

**Auto-configurations must have appropriate conditions.** Use `@ConditionalOnClass` for integrations depending on optional libraries and `@ConditionalOnMissingBean` to let consumers swap the default implementation.

**Properties must have their own namespace.** Use `acme.widget.*`; write Javadoc on every property so the configuration processor generates useful metadata.

**Optional dependencies must be intentional.** If autoconfigure declares the core library optional, the starter must pull the core library in. Do not assume optional dependencies propagate automatically to consumers.

**Do not forget the core Spring Boot starter.** Custom starters should reference `spring-boot-starter` directly or indirectly, so consumers adding only the custom starter still get the Spring Boot foundation they need.

**Do not let auto-configurations rely on component scan.** Register via `AutoConfiguration.imports`; use `@Import` for supporting configuration classes.

**Keep versions synchronized.** Modules in the same library release must share the same version. The Spring Boot version should be managed via a BOM or dependency management.

**Inspect the JAR, not just the source tree.** The imports resource might exist in source yet be excluded during packaging. Only an independent consumer confirms the published artifacts are complete.

**Do not confuse build with publish.** `verify` checks the build; `install` puts artifacts into the local repository; `deploy` publishes to a remote repository.

## 24. Common Issues and How to Fix Them

| Symptom | Common cause | How to check and fix |
| --- | --- | --- |
| Consumer cannot find starter | Not `mvn install`ed or not published remotely | Check versions and local/remote repositories |
| Consumer finds starter yet lacks `WidgetClient` | Starter missing autoconfigure or core client dependency | Check starter POM and `dependency:tree` |
| Autoconfigure JAR lacks imports | Resource in wrong folder or excluded | Place under `src/main/resources/META-INF/spring` and run `jar tf` |
| Imports present yet auto-configuration does not run | Wrong FQCN or class missing from JAR | Compare imports entry against classpath and package |
| Consumer must `@Import` auto-configuration to run | Descriptor not published or dependency lacks right JAR | Inspect autoconfigure JAR and runtime classpath |
| `WidgetClient` missing from runtime classpath | Core dependency in autoconfigure is optional and starter forgot core | Declare core client in starter |
| Auto-configuration does not create bean | `@ConditionalOnClass`, property, or `@ConditionalOnMissingBean` failed | Enable debug and read Condition Evaluation Report |
| Properties not bound | Missing `@EnableConfigurationProperties` or wrong prefix | Check properties class and `acme.widget.*` |
| IDE gives no property hints | Missing configuration processor or Javadoc | Inspect `spring-configuration-metadata.json` |
| Module tests pass yet consumer fails | Tests load auto-configuration directly, bypassing starter | Add integration test in an independent consumer project |
| Consumer gets stale artifact | Snapshot/release version and local cache mismatch | Rebuild/reinstall, check versions and dependency tree |
| Starter JAR has no classes | Confusing starter responsibility with autoconfigure | Inspect classes/resources in autoconfigure JAR; starter is mainly a dependency aggregator |
| CI cannot resolve artifact | Artifact exists only in developer's local Maven repo | Publish to a shared remote repository |
| Dependency versions drift | Modules declare differing versions independently | Use a BOM and shared version property |

## 25. Release and Integration Checklist

1. Verify the core library works standalone and does not depend on Spring unnecessarily.
2. Verify the autoconfigure module contains properties, configurations, and public customizer APIs.
3. Verify the core library dependency is intentionally marked optional.
4. Verify `spring-boot-autoconfigure` is in the autoconfigure module's runtime dependencies.
5. Verify annotation processors are configured for condition and configuration properties metadata.
6. Verify `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` lists the exact FQCN.
7. Verify the starter declares the core library, autoconfigure, and `spring-boot-starter`.
8. Run `mvn clean verify` and auto-configuration tests.
9. Run `mvn clean install` or `mvn deploy` according to the distribution environment.
10. Use `jar tf` to inspect the autoconfigure JAR and the starter's POM dependencies.
11. Create a consumer outside the reactor, adding only the starter dependency.
12. Run consumer integration tests and the application; verify beans and properties.
13. Check the dependency tree, versions, and repository resolution.
14. Publish an immutable release, and update configuration documentation and consumer examples.

## 26. Knowledge Self-Check

1. What does the autoconfigure module contain? **Auto-configuration classes, properties, customizer contracts, and the imports resource.**
2. What does a starter typically contain? **A dependency-aggregating POM and a JAR needing no Java classes.**
3. Which resource registers auto-configurations in Spring Boot 3.x? **`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.**
4. What does each line in imports contain? **The FQCN of an auto-configuration class.**
5. Why must the starter declare the core library if autoconfigure marks it optional? **Optional dependencies are not propagated automatically to consumers.**
6. What is `spring-boot-autoconfigure-processor` used for? **Generating condition metadata for early auto-configuration filtering.**
7. What metadata does `spring-boot-configuration-processor` generate? **`META-INF/spring-configuration-metadata.json`.**
8. How does `mvn verify` differ from `mvn install`? **Verify runs build checks; install also places artifacts into the local Maven repository.**
9. When is `mvn deploy` used? **To publish artifacts to a configured remote repository.**
10. Why are `ApplicationContextRunner` tests alone insufficient to prove a starter works? **They can load classes directly and bypass consumer descriptors/dependencies.**
11. Why is a consumer outside the Maven reactor needed? **To verify installed/published artifacts and the real dependency graph.**
12. Why is a nearly empty starter JAR normal? **The starter only aggregates dependencies; classes and imports live in the autoconfigure module.**

## Official References

- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): imports rules, conditions, testing, autoconfigure and starter modules.
- [Spring Boot 3.3.13 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/): structure and metadata of configuration properties.
- [Spring Boot 3.3.13 — Generating Your Own Metadata by Using the Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html): generating metadata with the configuration processor.
- [Apache Maven Install Plugin — Usage](https://maven.apache.org/plugins/maven-install-plugin/usage.html): installing artifacts into the local repository with `mvn install`.
- [Gradle — The Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publishing Java artifacts to Maven-compatible repositories and Maven local.

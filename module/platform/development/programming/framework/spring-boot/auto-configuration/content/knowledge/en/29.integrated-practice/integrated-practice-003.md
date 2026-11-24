# Designing a Minimal Client Library with Properties, Default Bean, and Enable/Disable Toggle

## 1. Goals and Contract of the Library

A Spring Boot-integrated client library typically needs to solve four things:

1. Provide a standalone Java client.
2. Read endpoint and timeouts from application configuration.
3. Automatically register a default bean when the application uses the library.
4. Allow the application to disable the default bean or replace it with a custom implementation.

This hands-on guide builds an HTTP client named **AcmeClient**, using Java 17 **java.net.http.HttpClient**. Spring Boot automatically creates the client from **AcmeClientProperties**. An application can disable bean creation via **acme.client.enabled=false**, or declare its own bean so the auto-configuration backs off.

The examples use **Java 17 and Spring Boot 3.3.13**. The design focuses on a small, easily testable contract:

| Component | Responsibility |
|---|---|
| acme-client-core | Pure Java client, no Spring dependencies |
| acme-client-spring-boot-autoconfigure | Properties, auto-configuration, and default bean |
| acme-client-spring-boot-starter | Convenience artifact so applications add one dependency |
| AcmeClientProperties | Configures endpoint, timeouts, and enabled flag |
| AcmeClientAutoConfiguration | Creates the default bean when conditions match |
| @ConditionalOnMissingBean | Allows applications to replace the default bean |
| @ConditionalOnProperty | Enables or disables creation of the default bean |

The three modules can reside in the same Maven multi-module repository. For a small exercise, you can place core and auto-configuration in one module first; when publishing a shared library, separating them ensures applications needing only the Java client do not pull in Spring Boot.

## 2. Desired Behavior

We choose concrete rules to avoid having different applications interpret the toggle flag in conflicting ways.

| Configuration | Properties bean | Library-created AcmeClient bean |
|---|---|---|
| acme.client.enabled omitted | Yes | Yes, because enabled by default |
| acme.client.enabled=true | Yes | Yes |
| acme.client.enabled=false | Yes | No |
| Application declares its own AcmeClient | Yes | Default bean backs off |
| Application declares bean and sets enabled=false | Yes | Application bean still exists |

The **enabled** flag in this guide controls the **default bean created by auto-configuration**. It does not delete or disable beans registered by the application itself. This is an important boundary: a library should not silently remove configuration owned by the application.

We make it enabled by default using two consistent mechanisms:

- The **enabled** field in properties has a default value of **true**.
- **@ConditionalOnProperty** sets **matchIfMissing = true**, so a missing property still allows the default bean to be created.

If you want the library disabled by default, change the default value to **false** and set **matchIfMissing = false**; both documentation and tests must be updated.

## 3. Project Structure

Suggested structure:

~~~text
acme-client/
├── pom.xml
├── acme-client-core/
│   ├── pom.xml
│   └── src/main/java/com/acme/client/
│       └── AcmeClient.java
├── acme-client-spring-boot-autoconfigure/
│   ├── pom.xml
│   ├── src/main/java/com/acme/client/autoconfigure/
│   │   ├── AcmeClientProperties.java
│   │   └── AcmeClientAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/acme/client/autoconfigure/
│       └── AcmeClientAutoConfigurationTests.java
└── acme-client-spring-boot-starter/
    └── pom.xml
~~~

Role of each module:

- **core** knows only Java and the JDK HTTP client. It does not import org.springframework.
- **autoconfigure** depends on core and Spring Boot. It translates properties into the client bean.
- **starter** mainly aggregates dependencies. Consuming applications add the starter and receive core and auto-configuration via the dependency graph.

Splitting modules allows core to be used in plain Java applications, while Spring Boot applications only need a single starter dependency.

## 4. Core Module: Creating a Pure Java Client

File **acme-client-core/src/main/java/com/acme/client/AcmeClient.java**:

~~~java
package com.acme.client;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Objects;

public final class AcmeClient {

    private final URI baseUrl;
    private final Duration connectTimeout;
    private final Duration requestTimeout;
    private final HttpClient httpClient;

    public AcmeClient(
            URI baseUrl,
            Duration connectTimeout,
            Duration requestTimeout) {

        this.baseUrl = normalizeBaseUrl(baseUrl);
        this.connectTimeout = requirePositive(
                connectTimeout, "connectTimeout");
        this.requestTimeout = requirePositive(
                requestTimeout, "requestTimeout");

        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(this.connectTimeout)
                .build();
    }

    public HttpResponse<String> get(String path)
            throws IOException, InterruptedException {

        if (path == null || path.isBlank()) {
            throw new IllegalArgumentException(
                    "path must not be blank");
        }

        URI relativeUri = URI.create(path);
        if (relativeUri.isAbsolute()
                || relativeUri.getRawAuthority() != null) {
            throw new IllegalArgumentException(
                    "path must be relative to the configured base URL");
        }

        String relativePath = path.startsWith("/")
                ? path.substring(1)
                : path;

        URI target = this.baseUrl.resolve(relativePath);

        HttpRequest request = HttpRequest.newBuilder(target)
                .timeout(this.requestTimeout)
                .GET()
                .build();

        return this.httpClient.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    public URI getBaseUrl() {
        return this.baseUrl;
    }

    public Duration getConnectTimeout() {
        return this.connectTimeout;
    }

    public Duration getRequestTimeout() {
        return this.requestTimeout;
    }

    private static URI normalizeBaseUrl(URI baseUrl) {
        Objects.requireNonNull(baseUrl, "baseUrl");

        String scheme = baseUrl.getScheme();
        boolean supportedScheme =
                "http".equalsIgnoreCase(scheme)
                || "https".equalsIgnoreCase(scheme);

        if (!baseUrl.isAbsolute()
                || baseUrl.getHost() == null
                || !supportedScheme) {
            throw new IllegalArgumentException(
                    "baseUrl must be an absolute HTTP or HTTPS URI");
        }

        if (baseUrl.getRawQuery() != null
                || baseUrl.getRawFragment() != null) {
            throw new IllegalArgumentException(
                    "baseUrl must not contain a query or fragment");
        }

        String value = baseUrl.toString();
        return URI.create(value.endsWith("/") ? value : value + "/");
    }

    private static Duration requirePositive(
            Duration value, String name) {

        Objects.requireNonNull(value, name);

        if (value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(
                    name + " must be greater than zero");
        }

        return value;
    }
}
~~~

The client has three small responsibilities:

- Normalize **baseUrl** so relative paths are resolved consistently.
- Create **HttpClient** with the connect timeout.
- Send GET with the request timeout and return **HttpResponse<String>** to the caller.

The JDK **HttpClient** can be reused across multiple requests. This client does not open network connections when the bean is created; connections are only established when **get()** is called.

The **get()** method accepts relative paths such as **products/42** or **/products/42**. A leading slash is stripped so the path stays under the configured base path. Absolute URIs and external authorities are rejected so callers do not accidentally use this client for arbitrary URLs.

The client returns both the status code and the response body. HTTP 404 or 500 does not automatically become an exception; the consuming application must inspect **response.statusCode()** and decide how to handle it. The synchronous method may throw **IOException** or **InterruptedException**; the calling layer needs to handle both cases. If catching **InterruptedException** without rethrowing, restore the interrupt flag via **Thread.currentThread().interrupt()**.

## 5. Auto-Configuration Module: Declaring Properties

Properties group the client's configuration under a single prefix. Do not scatter isolated properties across multiple classes.

File **AcmeClientProperties.java**:

~~~java
package com.acme.client.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.client")
public class AcmeClientProperties {

    private boolean enabled = true;

    private URI baseUrl =
            URI.create("https://api.example.test/v1/");

    private Duration connectTimeout = Duration.ofSeconds(2);

    private Duration requestTimeout = Duration.ofSeconds(5);

    public boolean isEnabled() {
        return this.enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

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

    public Duration getRequestTimeout() {
        return this.requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
~~~

Default values:

| Property | Type | Default | Meaning |
|---|---|---|---|
| acme.client.enabled | boolean | true | Allows creating the default client bean |
| acme.client.base-url | URI | https://api.example.test/v1/ | Base endpoint |
| acme.client.connect-timeout | Duration | 2s | Wait time to establish connection |
| acme.client.request-timeout | Duration | 5s | Maximum time for a request |

The .test domain is for examples and is not a real API. Applications must replace it with the endpoint of the service they use.

Spring Boot supports binding **URI** and **Duration** types. Users can write durations in human-readable units such as **1500ms**, **2s**, or **1m**.

The properties class only holds configuration data. It does not create an HttpClient, call services, read files, or inject other beans. Creating the client is the responsibility of the auto-configuration.

## 6. Auto-Configuration: Creating the Default Bean and Enable/Disable Toggle

File **AcmeClientAutoConfiguration.java**:

~~~java
package com.acme.client.autoconfigure;

import com.acme.client.AcmeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.client",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(AcmeClient.class)
    public AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout(),
                properties.getRequestTimeout());
    }
}
~~~

The two conditions serve different roles:

**@ConditionalOnProperty checks the enabled flag.**

- When the property is missing, **matchIfMissing = true** allows creating the default bean.
- When the property is **true**, the condition matches.
- When the property is **false**, the bean method is not registered.

**@ConditionalOnMissingBean checks whether the application has already provided a client.**

- If no **AcmeClient** bean exists, the library creates the default.
- If an **AcmeClient** bean already exists in the application, the default backs off.
- A concrete return type on the method gives Spring Boot accurate type metadata to evaluate conditions.

**@EnableConfigurationProperties** registers **AcmeClientProperties** so Spring binds the configuration. In this example, the properties bean still exists when **enabled=false**, because the toggle is placed on the bean method rather than on the entire auto-configuration class. That allows the application to still read the configuration and display status even when the default client is not created.

Do not call **getBean()** inside auto-configuration or conditions to check for the client. Bean presence checks must rely on condition metadata; Spring injects dependencies when initializing the bean.

## 7. Registering Auto-Configuration in the JAR

Spring Boot 3 uses an imports file to discover auto-configurations from external libraries.

Create the file:

**acme-client-spring-boot-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

Content:

~~~text
com.acme.client.autoconfigure.AcmeClientAutoConfiguration
~~~

Each line is the fully qualified class name of an auto-configuration. Consuming applications do not need to use **@Import(AcmeClientAutoConfiguration.class)** or component-scan the library package.

If the file is missing or has a misspelled class name, the dependency may still appear in the dependency tree, yet the auto-configuration will not be discovered. Therefore, inspect this file inside the packaged JAR, not only in the source tree.

In Spring Boot 3.x, registering auto-configurations via the **EnableAutoConfiguration** key in **spring.factories** has been removed. **spring.factories** is still used for some other SPIs; do not confuse those mechanisms with the **AutoConfiguration.imports** file.

## 8. Maven Dependencies for the Modules

### 8.1. Core module

**acme-client-core** only needs Java 17. Do not add Spring Boot dependencies to this module.

Compiler configuration in core's POM:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

### 8.2. Auto-configuration module

Minimal POM for **acme-client-spring-boot-autoconfigure**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-client-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <spring-boot.version>3.3.13</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>3.3.13</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client-core</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
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
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

In a real project, a root parent can centrally manage versions, plugins, and modules. The POM above illustrates the minimal dependencies of the auto-configuration module.

**spring-boot-configuration-processor** is optional because it provides compile-time metadata for IDEs. The processor can generate metadata from **@ConfigurationProperties**, giving users hints and completion when writing YAML or properties. It is not a required runtime dependency to bind configuration.

### 8.3. Starter module

The starter mainly aggregates dependencies so applications do not have to declare each artifact individually.

Minimal POM of **acme-client-spring-boot-starter**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-client-spring-boot-starter</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client-spring-boot-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

Core is pulled in through the dependency of the auto-configuration module. The starter does not need to contain Java code if its sole role is aggregating dependencies.

Consuming Spring Boot applications add:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-client-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Consuming applications should still use their own Spring Boot BOM to manage Spring dependencies. Libraries should not force a separate Spring Framework version in published POMs.

## 9. Configuring in a Consuming Application

After adding the starter, the application can configure it in **application.yml**:

~~~yaml
acme:
  client:
    enabled: true
    base-url: https://catalog.example.test/api/
    connect-timeout: 1500ms
    request-timeout: 4s
~~~

If **enabled** is omitted, the default client is still created. To disable it:

~~~yaml
acme:
  client:
    enabled: false
~~~

Corresponding environment variables can also be used:

~~~bash
ACME_CLIENT_ENABLED=false
ACME_CLIENT_BASE_URL=https://catalog.example.test/api/
ACME_CLIENT_CONNECT_TIMEOUT=1500ms
ACME_CLIENT_REQUEST_TIMEOUT=4s
~~~

Spring Boot relaxed binding maps environment variable names to properties according to its rules. When deploying, keep the same prefix to avoid duplicate configuration across local, test, and production environments.

### 9.1. Injecting and calling the client

Example service in the application:

~~~java
package com.example.catalog;

import com.acme.client.AcmeClient;

import java.io.IOException;
import java.net.http.HttpResponse;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final AcmeClient client;

    public CatalogService(AcmeClient client) {
        this.client = client;
    }

    public String findProduct() throws IOException, InterruptedException {
        HttpResponse<String> response = this.client.get("products/42");

        if (response.statusCode() >= 400) {
            throw new IllegalStateException(
                    "Catalog API returned HTTP " + response.statusCode());
        }

        return response.body();
    }
}
~~~

If **acme.client.enabled=false** and the application does not provide its own **AcmeClient**, mandatory injection like the example above will prevent the context from creating **CatalogService**. When disabling the client, beans consuming the client must also be made conditional, or the dependency must be designed as optional depending on application needs.

## 10. Allowing Applications to Replace the Default Bean

A good library allows consumers to replace the default implementation without modifying library code.

Example of an application registering its own client:

~~~java
package com.example.catalog;

import com.acme.client.AcmeClient;

import java.net.URI;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomClientConfiguration {

    @Bean
    AcmeClient customAcmeClient() {
        return new AcmeClient(
                URI.create("https://internal-catalog.example.test/api/"),
                Duration.ofSeconds(1),
                Duration.ofSeconds(3));
    }
}
~~~

Because **AcmeClientAutoConfiguration** uses **@ConditionalOnMissingBean(AcmeClient.class)**, the default bean is not registered when a user bean already exists.

Several notes:

- The method returns **AcmeClient** so Spring and conditions have accurate type metadata.
- Do not declare the default bean with an overly broad return type like **Object**.
- **@Primary** is not needed if there is only one bean because the default backs off.
- If the application intentionally registers multiple **AcmeClient** beans, it must resolve ambiguity with **@Primary** or **@Qualifier**.
- The application-declared bean still exists when **acme.client.enabled=false**; this property only disables the library's default bean.

## 11. Testing Auto-Configuration with ApplicationContextRunner

**ApplicationContextRunner** creates a small context to test conditions and bean registration without starting a server or connecting to endpoints.

File **AcmeClientAutoConfigurationTests.java**:

~~~java
package com.acme.client.autoconfigure;

import com.acme.client.AcmeClient;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeClientAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeClientAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultClientWhenEnabledPropertyIsMissing() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeClientProperties.class);
            assertThat(context).hasSingleBean(AcmeClient.class);

            AcmeClient client = context.getBean(AcmeClient.class);
            assertThat(client.getBaseUrl()).isEqualTo(
                    URI.create("https://api.example.test/v1/"));
            assertThat(client.getConnectTimeout())
                    .isEqualTo(Duration.ofSeconds(2));
            assertThat(client.getRequestTimeout())
                    .isEqualTo(Duration.ofSeconds(5));
        });
    }

    @Test
    void bindsEndpointAndTimeoutProperties() {
        this.runner
                .withPropertyValues(
                        "acme.client.base-url=https://catalog.example.test/api",
                        "acme.client.connect-timeout=1500ms",
                        "acme.client.request-timeout=4s")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    AcmeClientProperties properties =
                            context.getBean(AcmeClientProperties.class);
                    AcmeClient client =
                            context.getBean(AcmeClient.class);

                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofMillis(1500));
                    assertThat(properties.getRequestTimeout())
                            .isEqualTo(Duration.ofSeconds(4));
                    assertThat(client.getBaseUrl()).isEqualTo(
                            URI.create("https://catalog.example.test/api/"));
                });
    }

    @Test
    void doesNotCreateDefaultClientWhenDisabled() {
        this.runner
                .withPropertyValues("acme.client.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(AcmeClientProperties.class);
                    assertThat(context)
                            .doesNotHaveBean(AcmeClient.class);
                    assertThat(context
                            .getBean(AcmeClientProperties.class).isEnabled())
                            .isFalse();
                });
    }

    @Test
    void backsOffWhenApplicationProvidesItsOwnClient() {
        this.runner
                .withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class).getBaseUrl())
                            .isEqualTo(URI.create(
                                    "https://custom.example.test/"));
                });
    }

    @Test
    void keepsUserClientWhenDefaultAutoConfigurationIsDisabled() {
        this.runner
                .withPropertyValues("acme.client.enabled=false")
                .withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class).getBaseUrl())
                            .isEqualTo(URI.create(
                                    "https://custom.example.test/"));
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {

        @Bean
        AcmeClient customAcmeClient() {
            return new AcmeClient(
                    URI.create("https://custom.example.test/"),
                    Duration.ofSeconds(1),
                    Duration.ofSeconds(3));
        }
    }
}
~~~

The five tests verify key contracts:

| Test | What it proves |
|---|---|
| Missing property | Default is enabled and client is created with default values |
| Custom properties | URI and Duration are bound and passed into the client |
| Enabled false | Properties bean remains, default client does not exist |
| User bean present | Auto-configuration yields to the application's bean |
| User bean and enabled false | Disable flag does not remove the application-owned bean |

These tests do not send HTTP requests. They verify wiring, binding, bean creation conditions, and back-off behavior. Separate tests for **AcmeClient.get()** can be added using a local HTTP server if request/response verification is needed.

Run the tests in the Maven reactor:

~~~bash
./mvnw -pl acme-client-spring-boot-autoconfigure -am test
~~~

To also verify the starter module and packaged artifacts:

~~~bash
./mvnw -pl acme-client-spring-boot-starter -am verify
~~~

After building, verify the imports resource is inside the auto-configuration JAR:

~~~bash
jar tf acme-client-spring-boot-autoconfigure/target/acme-client-spring-boot-autoconfigure-1.0.0.jar
~~~

The output must contain:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The **ApplicationContextRunner** above loads the class directly with **AutoConfigurations.of(...)**, so checking the JAR resource is an extra step to confirm discovery metadata was packaged.

## 12. Checking Configuration and Common Issues

### 12.1. Default bean not found

Check in order:

1. Does the application have the starter or auto-configuration module dependency?
2. Is the core module on the runtime classpath?
3. Does the **AutoConfiguration.imports** file have the exact class name?
4. Is the **acme.client.enabled** property set to **false**?
5. Is another condition or auto-configuration exclusion excluding the configuration?
6. Has an application-declared **AcmeClient** bean caused the default to back off?

Enable the condition report with:

~~~bash
java -jar application.jar --debug
~~~

Locate the entry for **AcmeClientAutoConfiguration** and the condition match/no-match reasons.

### 12.2. Bean exists but configuration is wrong

Check the prefix and property names. For example, **acme.client.base-url** must match prefix **acme.client** and field **baseUrl**.

Check configuration source precedence: command-line arguments, environment variables, external config files, and packaged **application.yml** can have different priorities. Do not assume the binder is broken before determining which source is winning.

If the URI is invalid or timeouts are zero/negative, **AcmeClient**'s constructor throws **IllegalArgumentException** when creating the default bean. Error messages should pinpoint the property to fix; in larger systems, Jakarta Bean Validation and the corresponding validation dependency can be added to report errors earlier.

### 12.3. Default bean does not back off

- Check whether the custom bean has the exact **AcmeClient** type.
- Declare a concrete return type on the **@Bean** method.
- Ensure the custom configuration is a user configuration loaded before auto-configuration.
- Check context hierarchy if beans live in parent or child contexts.
- Do not use an **Object** bean and expect conditions on **AcmeClient** to infer the runtime implementation.

### 12.4. Disabled yet the application still sees a client

In this design, **enabled=false** only prevents the auto-configuration method from creating the default bean. If the application has its own **@Bean AcmeClient**, that bean still exists. If the goal is to disable the entire feature using the client, business beans consuming the client must also be conditioned or the application must control invocation paths.

### 12.5. Properties lack IDE autocomplete hints

Check for the **spring-boot-configuration-processor** dependency in the auto-configuration module. This is a compile-time processor; it generates metadata for IDEs. Runtime binding is still performed by Spring Boot.

## 13. Design Decisions to Align Before Release

| Question | Decision in example | When to change |
|---|---|---|
| Client enabled or disabled by default? | Enabled if property is missing | Sensitive libraries or ones creating expensive connections may choose disabled by default |
| What does enabled control? | Only the default bean | To control the entire feature, apply conditions at the application feature boundary |
| Does user bean take precedence? | Yes, default backs off | Change only if the library mandates one specific implementation |
| Do properties exist when disabled? | Yes | To turn off the whole integration, place the condition at class level |
| Does client depend on Spring? | No, core uses JDK | Only add Spring APIs to core if that is an intentional part of the public contract |
| Synchronous or reactive HTTP API? | Synchronous with JDK HttpClient | Provide a separate WebClient adapter if consumers run on a reactive stack |
| Do timeouts have defaults? | Yes, 2s connect and 5s request | Adjust based on real-world service latency and SLA |

Do not add retries, authentication, circuit breakers, metrics, or caching into core just to complicate the example. Those capabilities can be separate modules or extensions with clear dependencies and policies.

## 14. Common Mistakes

- **Adding @ConfigurationProperties without registering it:** add @EnableConfigurationProperties(AcmeClientProperties.class) or appropriate configuration properties scanning.
- **Forgetting AutoConfiguration.imports:** the JAR contains the class, yet Boot does not auto-discover the auto-configuration.
- **Using @ConditionalOnProperty and forgetting matchIfMissing:** a missing property will not create the default if the condition defaults to not matching.
- **Properties say enabled=true while condition defaults to off:** two conflicting policies; align the default value and matchIfMissing.
- **Forgetting @ConditionalOnMissingBean:** applications cannot replace the default or easily encounter multiple beans of the same type.
- **Returning Object from a @Bean method:** loses the type metadata needed for bean conditions.
- **Placing the enabled flag at the wrong level:** placing it on the entire class disables the properties bean too; placing it on the method disables only the default bean. Choose according to the published contract.
- **Using @DependsOn to control registration conditions:** it relates to instance initialization order, not bean registration conditions.
- **Creating HTTP connections in the constructor:** can make context startup network-dependent and tests flaky. The constructor should only prepare the client.
- **Calling APIs while binding properties:** properties are configuration data, not a lifecycle hook for performing I/O.
- **Setting zero or negative timeouts:** values must be validated with clear error messages.
- **Letting core depend on Spring Boot:** plain Java applications get dragged into unnecessary framework dependencies.
- **Using latest.release in builds:** dependencies can change without source changes; pin a BOM or explicit version catalog.
- **Testing only the default case:** must also test disabled, custom override, and value binding.
- **Testing only AutoConfigurations.of(...):** must inspect the resource in the JAR to confirm discovery metadata is packaged.
- **Assuming disabled removes user beans:** the condition on the default method does not remove beans registered by the application.
- **Confusing connect timeout with request timeout:** connect timeout bounds establishing the connection; request timeout bounds the duration of a specific request.

## 15. End-to-End Implementation Workflow

1. Finalize the public API of the pure Java client and avoid introducing Spring types into core.
2. Choose a unique prefix, such as **acme.client**.
3. Create **AcmeClientProperties** with clear data types and defaults.
4. Register properties with **@EnableConfigurationProperties**.
5. Create an auto-configuration with a **@Bean** method returning the concrete client type.
6. Add **@ConditionalOnProperty** to control the default bean and explicitly decide behavior when the property is missing.
7. Add **@ConditionalOnMissingBean** to allow applications to replace the implementation.
8. Register the class in **AutoConfiguration.imports**.
9. Configure the configuration processor to generate IDE metadata.
10. Write tests for default, binding, disabled, user override, and custom bean when disabled.
11. Verify the JAR contains the imports resource and the starter pulls the right dependencies.
12. Publish the property table, defaults, enabled semantics, and bean replacement instructions.

## 16. Self-Check Questions

1. Should the core client depend on Spring Boot? **No.** Core should stay independent unless Spring APIs are required.
2. Which annotation binds **AcmeClientProperties**? **@ConfigurationProperties(prefix = "acme.client").**
3. How do you register the properties class from auto-configuration? **Use @EnableConfigurationProperties(AcmeClientProperties.class).**
4. Which annotation creates the default bean when no bean of that type exists yet? **@ConditionalOnMissingBean(AcmeClient.class).**
5. Which annotation enables/disables the default bean by property? **@ConditionalOnProperty.**
6. What does matchIfMissing=true mean? **A missing property still allows the condition to match.**
7. Why is a concrete return type needed on the @Bean method? **So Spring has accurate type metadata when evaluating bean conditions.**
8. Is a user-defined AcmeClient removed when enabled=false? **No.** The flag only disables the auto-configuration's default bean.
9. Does the properties bean still exist when enabled=false in this example? **Yes**, because the condition is placed on the bean method rather than the auto-configuration class.
10. Where is the Boot 3 auto-configuration registration file located? **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports.**
11. Is the configuration processor needed at runtime? **No.** It generates metadata at compile time so IDEs provide completion.
12. How do connectTimeout and requestTimeout differ? **One bounds establishing the connection, while the other bounds the duration of the request.**
13. What test utility checks bean registration without running a server? **ApplicationContextRunner.**
14. Why inspect the JAR after building? **To confirm the imports resource was actually packaged and Boot can discover the auto-configuration.**

## 17. Official References

- [Creating Your Own Auto-configuration — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): conditions, default beans, back-off, ordering, and auto-configuration registration.
- [Externalized Configuration — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): binding @ConfigurationProperties and registering with @EnableConfigurationProperties.
- [ConditionalOnProperty API — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): havingValue, matchIfMissing, and property matching rules.
- [ConditionalOnMissingBean API — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): condition for creating a default when no matching bean exists.
- [AutoConfiguration API — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): auto-configuration annotation and processing order.
- [ApplicationContextRunner API — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): building isolated contexts to test auto-configuration.
- [Configuration Metadata Specification — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html): metadata generated for IDE assistance and code completion.

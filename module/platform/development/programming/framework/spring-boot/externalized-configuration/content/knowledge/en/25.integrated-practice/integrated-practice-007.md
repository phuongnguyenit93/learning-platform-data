# Loading Test Secrets from configtree: with Mock Data in Spring Boot

## 1. Practice Objectives

In a Spring Boot application, sensitive information is typically provided at deployment time rather than packaged inside the JAR. Some platforms such as Kubernetes and Docker can inject secrets into containers via **mounted files**. When each file represents one property and the file contents are its value, Spring Boot can load the entire file tree using the Config Data mechanism with the `configtree:` prefix.

This lesson belongs to the **Integrated Practice** group of Spring Boot Externalized Configuration. The goal is to reproduce how a production application receives secrets from mounted files **without using any real secrets**. All examples use fake tokens, passwords, usernames, and endpoints.

Learning outcomes:

1. Distinguish a config tree from ordinary YAML/properties files and from environment variables.
2. Create a directory containing mock files using Java, Bash, or test utilities.
3. Load data via `spring.config.import=configtree:...` at the proper Config Data phase.
4. Bind values into `@ConfigurationProperties` and verify them with JUnit.
5. Understand how directory/file names become property keys, including dot notation and nested directory trees.
6. Distinguish a missing **directory** from a missing **file/key** inside the directory.
7. Test required imports, optional imports, precedence, string secrets, and binary secrets.
8. Reduce leakage through logs, exceptions, test reports, Git, CI, and build artifacts.
9. Clean up temporary resources after tests, keeping test cases isolated and repeatable.
10. Translate the test model to Docker/Kubernetes without using production credentials.

**Principle:** test the **reading and binding** mechanism with fake data. Never bring real tokens into tests just to prove that a config tree works.

## 2. What Is a Config Tree?

An application configuration is commonly written as:

~~~properties
demo.client.api-key=FAKE_TOKEN_001
demo.client.username=demo-user
demo.client.password=FAKE_PASSWORD_001
~~~

In the configuration tree model, some platforms do not supply a single combined file like the one above. Instead, each key is **one file**:

~~~text
/tmp/demo-secrets/
├── demo.client.api-key
├── demo.client.username
└── demo.client.password
~~~

File contents:

~~~text
demo.client.api-key   -> FAKE_TOKEN_001
demo.client.username  -> demo-user
demo.client.password  -> FAKE_PASSWORD_001
~~~

With a Config Data file:

~~~properties
spring.config.import=configtree:/tmp/demo-secrets/
~~~

Spring Boot maps each filename to a property key, then loads the file contents as the value:

| File | Property in Environment | Mock Value |
| --- | --- | --- |
| `demo.client.api-key` | `demo.client.api-key` | `FAKE_TOKEN_001` |
| `demo.client.username` | `demo.client.username` | `demo-user` |
| `demo.client.password` | `demo.client.password` | `FAKE_PASSWORD_001` |

This is a **Config Data import** mechanism, not a directive to read arbitrary files via `@Value` and not a secret manager.

### 2.1. Difference from a Properties File

A combined properties file:

~~~text
/tmp/demo-secrets/application.properties
~~~

must be loaded as **one Config Data file**:

~~~properties
spring.config.import=file:/tmp/demo-secrets/application.properties
~~~

Whereas a **one-file-per-key** structure uses:

~~~properties
spring.config.import=configtree:/tmp/demo-secrets/
~~~

If you use `configtree:` for a directory containing a file named `application.properties`, that name can be treated as a **property key** rather than automatically parsing the file contents into multiple properties. Choose the import type based on how the data is laid out.

### 2.2. A Config Tree Does Not Encrypt Values

`configtree:` is simply a mechanism for reading data from the filesystem and placing it into `Environment`. It does not encrypt files, configure ACLs, verify that a token is still valid, or rotate secrets.

For production, protecting the files belongs to the mount platform, secret manager, container permissions, and operational procedures. In tests, use only **harmless mock values**.

### 2.3. This Mechanism Belongs to Spring Boot 2.4+ Config Data

Examples using `spring.config.import` and `configtree:` rely on the Config Data mechanism introduced in Spring Boot 2.4 and still used in modern Boot versions. For older projects, check the reference documentation for the running version instead of copying incompatible syntax.

## 3. Practice Scenario

We simulate an application sending requests to an external client. The application needs three values:

- `demo.client.api-key`: mock authentication token.
- `demo.client.username`: mock login username.
- `demo.client.password`: mock password.

No real network requests are made. The objective is to test:

~~~text
Temporary directory
    |
    +-- demo.client.api-key  (FAKE_TEST_KEY_284)
    +-- demo.client.username (demo-user)
    +-- demo.client.password (FAKE_TEST_PASSWORD_284)
    |
    v
spring.config.import=configtree:<temporary-directory>/
    |
    v
Spring Boot Config Data
    |
    v
Environment
    |
    v
@ConfigurationProperties(prefix = "demo.client")
    |
    v
DemoClientSecrets bean
    |
    v
JUnit assertions
~~~

Notably, we do not hard-code fake secrets in `src/main/resources/application.yml` to simulate runtime. We **create the files when the test runs**, then start the application context after the directory is ready.

## 4. Prerequisites

The Java examples use:

- Java 17+.
- Spring Boot with Config Data support.
- Spring Boot Test and JUnit Jupiter.
- AssertJ (usually pulled in transitively by `spring-boot-starter-test`).
- A Maven- or Gradle-based project.
- A filesystem that allows creating temporary directories.

If you want to use Bean Validation with `@NotBlank`, you must add a Jakarta Bean Validation provider; in many Boot projects, `spring-boot-starter-validation` can be used.

With Spring Boot 3.x/4.x, check the specific versions of Spring Framework, Java, and starters because dependency details can vary. The code below focuses on core APIs: `SpringApplicationBuilder`, `@ConfigurationProperties`, `@EnableConfigurationProperties`, `@TempDir`, and Java NIO.

### 4.1. A Suggested Project Structure

~~~text
demo-app/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/demo/config/
│   │   │   └── DemoClientSecrets.java
│   │   └── resources/
│   │       └── application.yml
│   └── test/
│       └── java/com/example/demo/
│           └── ConfigTreeSecretsIntegrationTest.java
└── .gitignore
~~~

There is no need to add a fake secret directory to Git. JUnit can create one in the operating system's temporary directory each time a test runs.

## 5. Defining the Configuration Model

Create `DemoClientSecrets.java`:

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.client")
public record DemoClientSecrets(
        String apiKey,
        String username,
        String password
) {
}
~~~

This is an immutable record receiving values through constructor binding supported by Spring Boot for configuration properties. The record components map as follows:

~~~text
apiKey    -> demo.client.api-key
username  -> demo.client.username
password  -> demo.client.password
~~~

Use lowercase kebab-case canonical keys. The Spring Boot Binder maps `api-key` to the Java component `apiKey` via relaxed binding.

### 5.1. Why Use a Record in This Lesson?

A record prevents tests from mutating credentials after the context is created. It also demonstrates Spring Boot's type-safe configuration properties.

**Warning:** records generate a `toString()` that includes their components. Therefore **do not log the whole `DemoClientSecrets` object** in a real application, because it can contain tokens or passwords. The test only asserts the mock values without printing the object to logs.

### 5.2. Using a JavaBean Instead of a Record

For older libraries or mutable objects, you can use a class:

~~~java
@ConfigurationProperties(prefix = "demo.client")
public class DemoClientSecrets {

    private String apiKey;
    private String username;
    private String password;

    public String getApiKey() { return apiKey; }
    public void setApiKey(String apiKey) { this.apiKey = apiKey; }

    public String getUsername() { return username; }
    public void setUsername(String username) {
        this.username = username;
    }

    public String getPassword() { return password; }
    public void setPassword(String password) {
        this.password = password;
    }
}
~~~

Both target styles can receive data from `Environment`, differing in object construction and mutability. `configtree:` does not specifically require either a record or a JavaBean.

## 6. Creating a Mock File Directory with Bash

On Linux/macOS or inside a container shell:

~~~bash
mkdir -p /tmp/demo-configtree

printf '%s' 'FAKE_TEST_KEY_284' \
  > /tmp/demo-configtree/demo.client.api-key

printf '%s' 'demo-user' \
  > /tmp/demo-configtree/demo.client.username

printf '%s' 'FAKE_TEST_PASSWORD_284' \
  > /tmp/demo-configtree/demo.client.password
~~~

Bash here only creates **fake data**, without touching any authentication system.

### 6.1. Why Use `printf` Instead of `echo`?

`echo` usually appends a trailing newline character to the content. For passwords or tokens, an accidentally added newline can make the value different from what is expected, especially when a library does not trim.

~~~bash
printf '%s' 'FAKE_TEST_KEY_284'
~~~

writes the exact mock string with no trailing newline. If a test intentionally needs to verify trailing-newline handling, create a dedicated case and explicitly assert how the application handles it.

### 6.2. Do Not Commit the Generated Directory

`/tmp/demo-configtree` is only an example on the local machine or container filesystem. In CI, use a separate temporary directory per test instead of a shared path to avoid races when tests run in parallel.

If files live inside the project workspace, add any fixture directory containing **real values** to ignore rules and ensure the pipeline does not copy it into the JAR/image. Even for mock values, creating them at runtime is still preferred to faithfully simulate mounted secrets.

### 6.3. Do Not Use a File Named `application.properties` for This Tree

For example:

~~~text
/tmp/demo-configtree/demo.client.api-key
~~~

is a file named after the **property**, not a file containing `key=value`. If you write:

~~~text
demo.client.api-key=FAKE_TEST_KEY_284
~~~

inside the file `demo.client.api-key`, the Binder may take the entire string including `demo.client.api-key=...` as the **value**. Write only the mock secret content; do not repeat the property name inside the file.

## 7. Loading the Config Tree in the Application

A Config Data file loaded by Boot can declare:

~~~properties
spring.config.import=configtree:/tmp/demo-configtree/
~~~

Or YAML:

~~~yaml
spring:
  config:
    import: "configtree:/tmp/demo-configtree/"
~~~

When Spring Boot starts up, the Config Data import mechanism reads the directory and produces these properties:

~~~text
demo.client.api-key
demo.client.username
demo.client.password
~~~

From there, `@ConfigurationProperties(prefix = "demo.client")` can bind the three values into `DemoClientSecrets`.

### 7.1. Trailing Slash on the Directory

Boot examples and documentation use a location with a trailing `/` for a directory:

~~~text
configtree:/tmp/demo-configtree/
~~~

Always write directory locations explicitly, especially when constructing paths dynamically. A location representing a single file carries different semantics.

### 7.2. The Import Location Is Not a Classpath Path

~~~properties
spring.config.import=configtree:/tmp/demo-configtree/
~~~

is a filesystem tree in the runtime environment. Do not confuse it with:

~~~properties
spring.config.import=classpath:/demo-configtree/
~~~

A Config Tree typically represents a volume mounted outside the JAR. To test mounted secrets, use an external temporary directory or filesystem fixture separated from classpath artifacts.

### 7.3. Command-Line Startup Example

Assuming the application has registered the configuration properties, you can start it with:

~~~bash
java -jar demo.jar \
  --spring.config.import=configtree:/tmp/demo-configtree/
~~~

This approach is useful for manual experiments with fake secrets. In production, the import location is typically declared in an appropriate Config Data file or deployment bootstrap, while the files are mounted by the platform.

Never put **secret values** into command-line arguments. The example passes only the **location**, not a password.

## 8. Integration Test Using `@TempDir` and `SpringApplicationBuilder`

This section is the core hands-on exercise. We do not rely on a fixed directory that could be shared across test runs.

JUnit Jupiter provides `@TempDir` so each test gets its own temporary directory. We:

1. Create mock files using `Files.writeString`.
2. Compute the corresponding import location.
3. Start a Spring context **after the files exist**.
4. Verify the bound bean.
5. Close the context using try-with-resources.
6. Let JUnit manage cleanup of the temporary directory.

### 8.1. Minimal Configuration for Testing

~~~java
package com.example.demo;

import com.example.demo.config.DemoClientSecrets;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootConfiguration(proxyBeanMethods = false)
@EnableConfigurationProperties(DemoClientSecrets.class)
public class FixtureApplication {
}
~~~

`@SpringBootConfiguration` marks a Boot configuration class. `@EnableConfigurationProperties` registers the bean bound under the prefix. This is a small test application that requires no database connection or external service calls.

We use `SpringApplicationBuilder` to go through Spring Boot's bootstrap and Config Data processing instead of manually building an `Environment`.

### 8.2. Helper Method to Build the Import Location

~~~java
import java.nio.file.Path;

static String configTreeLocation(Path directory) {
    String absolute = directory
            .toAbsolutePath()
            .toString()
            .replace('\\', '/');

    return "configtree:" + absolute + "/";
}
~~~

On Linux/macOS, the result looks like:

~~~text
configtree:/tmp/junit123456789/secret-tree/
~~~

On Windows, verify that the location is handled properly by Boot for the drive/root and path in use. The example uses forward slashes for convenience across many environments, though real test harnesses should be verified on every OS the project supports.

### 8.3. Main JUnit Test

~~~java
package com.example.demo;

import com.example.demo.config.DemoClientSecrets;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class ConfigTreeSecretsIntegrationTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void loadsFakeSecretsFromConfigTree() throws IOException {
        Path secrets = Files.createDirectory(
                temporaryDirectory.resolve("secrets")
        );

        Files.writeString(
                secrets.resolve("demo.client.api-key"),
                "FAKE_TEST_KEY_284",
                StandardCharsets.UTF_8
        );

        Files.writeString(
                secrets.resolve("demo.client.username"),
                "demo-user",
                StandardCharsets.UTF_8
        );

        Files.writeString(
                secrets.resolve("demo.client.password"),
                "FAKE_TEST_PASSWORD_284",
                StandardCharsets.UTF_8
        );

        String path = configTreeLocation(secrets);

        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(FixtureApplication.class)
                    .web(WebApplicationType.NONE)
                    .properties(
                        "spring.config.import=" + path,
                        "spring.main.banner-mode=off"
                    )
                    .run()) {

            DemoClientSecrets credentials =
                    context.getBean(DemoClientSecrets.class);

            assertThat(credentials.apiKey())
                    .isEqualTo("FAKE_TEST_KEY_284");
            assertThat(credentials.username())
                    .isEqualTo("demo-user");
            assertThat(credentials.password())
                    .isEqualTo("FAKE_TEST_PASSWORD_284");
        }
    }

    private static String configTreeLocation(Path directory) {
        return "configtree:"
            + directory.toAbsolutePath()
                .toString()
                .replace('\\', '/')
            + "/";
    }
}
~~~

This test demonstrates using `SpringApplicationBuilder.properties(...)` to pass the **import path** into default properties before calling `run()`; Spring Boot Config Data processing then has the opportunity to process the import. This differs from simply adding three fake keys to the context after bootstrap.

**Project note:** the sample code must live in the same package or be able to import `FixtureApplication` and `DemoClientSecrets`; you must also have the test starter matching the Boot version. If the project has other application configuration loaded from default locations, isolate the test app or test environment to avoid unexpected sources.

### 8.4. Purpose of Each Statement

- `@TempDir`: supplies an isolated directory for the test.
- `Files.createDirectory`: creates the real directory to import.
- `Files.writeString`: writes exact mock data without adding a newline.
- `configtree:.../`: explicitly indicates a **directory tree**.
- `SpringApplicationBuilder(...).run()`: starts the Boot context after the files exist.
- `getBean(DemoClientSecrets.class)`: verifies the bean is registered/bound.
- `assertThat(...)`: confirms the exact values in the test.
- `try (...)`: closes the context after the test; JUnit handles cleanup of the temporary directory.

No line needs to call an external API, decrypt a secret, or print credentials to logs.

## 9. Distinguishing a Real Import Test from a Value-Binding-Only Test

Suppose a test is written as:

~~~java
new ApplicationContextRunner()
    .withPropertyValues(
        "demo.client.api-key=FAKE_TEST_KEY_284"
    )
    .run(context -> { /* assertions */ });
~~~

This test can prove that the Binder accepts a property value, yet it **does not prove that Boot read the file from a config tree**. The source is injected directly into the context, bypassing the file import step.

Similarly:

~~~java
@TestPropertySource(properties =
    "demo.client.api-key=FAKE_TEST_KEY_284")
~~~

can test binding, but does not simulate a mounted file.

To genuinely test `configtree`, the test needs to:

1. Create the directory and files on the filesystem.
2. Supply `spring.config.import=configtree:<directory>/` to Boot at the right stage.
3. Run Boot's Config Data processing.
4. Read the bean/property after the context has been created.
5. Avoid simultaneously supplying the same key via a higher-precedence inline test property, because the inline value can mask an import failure.

### 9.1. Avoiding False Positives from Default Values

If the class has a default token equal to the exact fake string the test expects, the test might pass even when the file is not read. Choose a fake value present only in the generated test file and assert it.

### 9.2. A Dedicated Marker Property

You can create an extra file:

~~~text
demo.client.fixture-source
~~~

containing:

~~~text
temporary-config-tree
~~~

Then assert:

~~~java
assertThat(context.getEnvironment()
    .getProperty("demo.client.fixture-source"))
    .isEqualTo("temporary-config-tree");
~~~

This marker confirms the data genuinely came from the test directory. Do not use a marker with sensitive values.

## 10. Filenames and Directory Structure Determine Property Keys

Spring Boot maps folder/file names inside a config tree to keys.

First approach — dot notation in the filename:

~~~text
secrets/
└── demo.client.api-key
~~~

Produces property:

~~~text
demo.client.api-key
~~~

Second approach — nested directories:

~~~text
secrets/
└── demo/
    └── client/
        └── api-key
~~~

Also represents the property under the prefix:

~~~text
demo.client.api-key
~~~

### 10.1. The Import Root Changes Property Names

If the directory is:

~~~text
/tmp/testmount/
└── demo/
    └── client/
        └── api-key
~~~

then:

~~~properties
spring.config.import=configtree:/tmp/testmount/
~~~

can provide `demo.client.api-key`.

However:

~~~properties
spring.config.import=configtree:/tmp/testmount/demo/client/
~~~

typically provides only the key `api-key`, because the `demo/client` segment sits **above the import root**.

This is a common mistake: the file has the right content yet `@ConfigurationProperties(prefix="demo.client")` still receives null because the import root is too deep.

### 10.2. Do Not Confuse the Secret Object Name with the Property Key

A Kubernetes Secret named `gateway-credentials` does not automatically create `gateway.credentials.*` properties. The **mounted file structure** determines the names `configtree` sees. A Deployment can project a key from a Secret object to a different filename to match the Java configuration name.

### 10.3. Prefer Canonical Key Names

For configuration properties, choose lowercase kebab-case names:

~~~text
demo.client.api-key
demo.client.username
demo.client.password
~~~

From there, the Binder maps to Java fields `apiKey`, `username`, and `password` via relaxed binding. Do not name a file after an arbitrary environment variable `DEMO_CLIENT_API_KEY` expecting it to automatically become a canonical dotted key unless you have verified how that source is handled.

## 11. Missing Directory vs. Missing Property: Two Different Errors

This is an essential part of the practice.

### 11.1. Required Import Directory Does Not Exist

~~~properties
spring.config.import=configtree:/path/not-exists/
~~~

If a required Config Data location is missing, Spring Boot can throw `ConfigDataLocationNotFoundException` and startup fails.

Operational messages should indicate the missing location/source type at a non-sensitive level without dumping secret contents.

### 11.2. Optional Directory Does Not Exist

~~~properties
spring.config.import=optional:configtree:/path/not-exists/
~~~

With `optional:`, Boot can continue when the **location** does not exist. This does not mean required properties are automatically generated.

If the application still needs `demo.client.api-key`, it may receive null/blank and needs separate validation.

### 11.3. Directory Exists, but the `api-key` File Is Missing

~~~text
secrets/
├── demo.client.username
└── demo.client.password
~~~

Import:

~~~properties
spring.config.import=configtree:/tmp/demo-secrets/
~~~

The location exists so the import can succeed. Yet the property `demo.client.api-key` is absent. Adding or omitting `optional:` **does not solve a missing key**; you need `@NotBlank`, a required-property check, or application-level validation.

### 11.4. File Exists but Is Empty

~~~text
secrets/
└── demo.client.api-key  (zero bytes)
~~~

This differs from a missing file. The Binder itself may bind an empty string; validation determines whether it is accepted.

### 11.5. Classification Table

| Symptom | Config Data import | Field value | How to handle |
| --- | --- | --- | --- |
| Required directory missing | May fail bootstrap | Not yet bound | Fix mount/location |
| Optional directory missing | May continue | No keys from tree | Validate if required |
| Directory exists, key missing | Import may succeed | Null or not supplied | Validate missing key |
| Key exists, file empty | Imports empty data | Blank per target | Validate non-blank |
| Key exists, file has newline | Imports extra character | May contain newline | Test/define trimming |
| Key in higher-precedence source | Import may still succeed | Higher source wins | Define precedence |
| Filename does not match prefix | Imports file under another key | Target field does not receive it | Fix filename/root |

## 12. Adding Bean Validation for Required Secrets

If the application genuinely requires all three fields, you can declare:

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.client")
public record DemoClientSecrets(
        @NotBlank String apiKey,
        @NotBlank String username,
        @NotBlank String password
) {}
~~~

In Spring Boot 3.x with Jakarta Validation, an appropriate provider must be on the classpath, typically via `spring-boot-starter-validation`. Then missing or blank fields can be caught early during bean binding/validation.

### 12.1. Validation Messages Must Be Safe

If a field holds a token, do not construct a message by concatenating the actual value:

~~~java
throw new IllegalStateException(
    "Invalid API key: " + secrets.apiKey()
);
~~~

Instead, describe the contract:

~~~java
throw new IllegalStateException(
    "demo.client.api-key must be present and non-blank"
);
~~~

Do not assume every conversion error or framework failure report is always redacted; run log checks using fake canaries.

### 12.2. Do Not Hard-Code Fallback Credentials

Avoid:

~~~properties
demo.client.api-key=${DEMO_API_KEY:production-password}
~~~

For required secrets, using a default password can leave the application running in an invalid state. This lesson uses fake tokens only in test fixtures, never as production defaults.

### 12.3. Fail Fast vs. Business-Optional

- If the client cannot operate without credentials, failing startup with a safe message is usually appropriate.
- If a feature is disabled in a profile, credentials may not be needed; in that case use an appropriately scoped condition and validation.
- Do not add `optional:` just to bypass deployment errors without updating the feature contract.

## 13. Testing the Missing-File Case

Use the same `@TempDir` but create only two files:

~~~java
@Test
void missingApiKeyDoesNotAppearInEnvironment(
        @TempDir Path temp
) throws IOException {

    Path secrets = Files.createDirectory(
            temp.resolve("secrets")
    );

    Files.writeString(
            secrets.resolve("demo.client.username"),
            "demo-user",
            StandardCharsets.UTF_8
    );

    Files.writeString(
            secrets.resolve("demo.client.password"),
            "FAKE_TEST_PASSWORD_284",
            StandardCharsets.UTF_8
    );

    try (ConfigurableApplicationContext context =
            new SpringApplicationBuilder(FixtureApplication.class)
                .web(WebApplicationType.NONE)
                .properties(
                    "spring.config.import="
                      + configTreeLocation(secrets)
                )
                .run()) {

        assertThat(context.getEnvironment()
            .containsProperty("demo.client.api-key"))
            .isFalse();
    }
}
~~~

This example assumes `DemoClientSecrets` **does not yet have mandatory validation constraints attached**, allowing the context to start and test property presence. If you use the `@NotBlank` version, the context may fail before assertions run; in that case test the failure separately.

### 13.1. Intentionally Testing Validation Failure

You can write a test with a configuration class that registers the validated bean and does not create the `api-key` file. Expect context creation to fail.

Do not lock tests to a long exception message string, because internal messages and wrapper classes can differ across Spring Boot versions. Instead verify **the appropriate failure category**, the offending key if safely reported, and that no fake secret appears in the logs.

### 13.2. Testing a Non-Existent Directory

Unlike a missing file:

~~~java
Path missingDirectory = temp.resolve("not-created");
String importLocation =
        configTreeLocation(missingDirectory);
~~~

If the location is required, attempt to start Boot and assert failure. With `optional:configtree:...`, Boot can proceed when the location is absent; tests must distinguish those two contracts.

### 13.3. Do Not Swallow Errors with `ignore-on-not-found`

Spring Boot has mechanisms for ignoring missing Config Data locations. Never enable them globally just to make tests pass; doing so can mask critical mount failures in production.

## 14. Optional Import Does Not Mean Optional Secret

A test file:

~~~properties
spring.config.import=optional:configtree:./secrets/
~~~

only lets Boot ignore a missing **location** under the Config Data mechanism.

If the application class requires:

~~~java
@NotBlank String apiKey;
~~~

then validation can still fail. That is the right behavior: the import location is allowed to be absent, yet an enabled feature can still require credentials.

When designing tests, name them clearly:

- `missingLocationIsAllowedWhenOptional`: focuses on Config Data.
- `missingRequiredKeyFailsValidation`: focuses on the bean contract.
- `disabledFeatureDoesNotRequireKey`: focuses on the business condition, if designed that way.

Do not combine all three scenarios into a single vague `"configtree is optional"` test.

## 15. Text Files, Newlines, and Encoding

For mounted secrets, file contents are the data, not `key=value` declarations. Small changes inside a file can corrupt a credential.

### 15.1. Avoiding Unintended Newlines

~~~bash
echo FAKE_TEST_KEY_284 > demo.client.api-key
~~~

typically appends a newline. Meanwhile:

~~~bash
printf '%s' 'FAKE_TEST_KEY_284' > demo.client.api-key
~~~

does not append a newline. Some client/authentication libraries do not trim; a token containing a newline may then be rejected by the remote service.

### 15.2. Testing Whitespace According to Contract

If exact bytes must be preserved, do not blindly call `String.trim()` on every secret. For passwords, trailing spaces may sometimes be part of the credential. If the system wants to strip newlines introduced by platform mounts, define an explicit rule scoped only to that secret type and cover it with tests.

### 15.3. UTF-8 and Multibyte Data

`Files.writeString(..., UTF_8)` creates a test file with an explicit encoding. For text secrets read as `String`, confirm the provider's encoding matches the consumer.

Do not assume every secret is text: certificates, private keys, keystores, and binary tokens may need to be handled as bytes or file resources.

### 15.4. Do Not Log Bytes as Strings

A common debugging mistake:

~~~java
log.info("Loaded key bytes: {}", new String(keyBytes));
~~~

In a real application this leaks secrets and also risks corrupting binary data. Log key type, presence status, or an error code—never the contents.

## 16. Binding a Config Tree Value to `byte[]`

Spring Boot supports binding configuration tree values to either `String` or `byte[]` depending on the target type.

Example class:

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.signing")
public record SigningProperties(byte[] keyMaterial) {}
~~~

Test creates the file:

~~~java
byte[] fakeBytes = new byte[] {
    0x01, 0x23, 0x45, 0x67
};

Files.write(
    secrets.resolve("demo.signing.key-material"),
    fakeBytes
);
~~~

After Config Data import, the bean can receive the byte data. Verification:

~~~java
assertThat(signingProperties.keyMaterial())
    .containsExactly(0x01, 0x23, 0x45, 0x67);
~~~

For the test to compile in Java with AssertJ, byte literals in `containsExactly` must match the target overload; you can use `(byte) 0x01`... when the API overload expects `byte` values.

### 16.1. Do Not Use Binary Tests to Hold Real Private Keys

Even when testing keystore/TLS parsing, use generated test keys with no production privileges or suitable fake bytes. Never copy a production keystore into `src/test/resources` just to test binding.

### 16.2. Distinguishing Raw Bytes from a Base64 String

A file containing base64 characters is a **text encoding**, not automatically identical to a file containing the raw bytes. Verify the target class, converter, and how the secret provider supplies data before writing assertions.

### 16.3. Avoid `String` When Exact Bytes Must Be Preserved

If the consumer requires exact bytes, using `byte[]` or reading a file resource through the proper API is generally cleaner than converting through `String` and re-encoding.

## 17. Filename Conventions and Relaxed Binding

Java model:

~~~java
@ConfigurationProperties(prefix = "demo.client")
public record DemoClientSecrets(String apiKey) {}
~~~

Canonical property name:

~~~text
demo.client.api-key
~~~

Filename in the config tree:

~~~text
demo.client.api-key
~~~

That is the clearest name for testing. A nested directory layout:

~~~text
demo/client/api-key
~~~

can also produce the matching property.

### 17.1. Do Not Confuse with OS Environment Variables

When using environment variables, canonical `demo.client.api-key` typically maps to `DEMO_CLIENT_APIKEY` under Boot's OS environment variable rules.

In a config tree, however, **the filename is the property key** and can contain dots and dashes. Do not create a file named `DEMO_CLIENT_APIKEY` expecting it to automatically be interpreted like an OS environment property source. The two sources follow different rules.

### 17.2. Filenames with Dots

Boot's documentation confirms that a file named with dot notation such as `myapp.username` maps to the same property name. That is the basis for the pattern:

~~~text
demo.client.api-key
demo.client.password
~~~

### 17.3. Filesystem Case Sensitivity

Linux and Windows can differ in case sensitivity. For portable tests, use canonical lowercase names and avoid two files that differ only in letter case. If tests run across multiple OSes, ensure filenames do not rely on filesystem-specific behavior.

## 18. Other Sources Can Override Secrets in the Tree

At startup, a property may appear in multiple sources:

~~~text
classpath application.yml
external application.yml
configtree directory
OS environment
Java system properties
command line arguments
test-specific overrides
~~~

Spring Boot defines source precedence ordering. Typically, environment variables or command-line options can override a key coming from Config Data.

For example, the file already contains:

~~~text
demo.client.api-key -> FAKE_TEST_KEY_284
~~~

yet you launch with:

~~~bash
java -jar demo.jar \
  --spring.config.import=configtree:/tmp/demo-configtree/ \
  --demo.client.api-key=FAKE_OVERRIDE_284
~~~

When Boot's command-line property source is enabled, the value from `--demo.client.api-key` can win and the bean receives `FAKE_OVERRIDE_284`.

### 18.1. Do Not Test an Import While Supplying a Higher-Precedence Source

If a test has:

~~~java
@SpringBootTest(properties =
    "demo.client.api-key=FAKE_OVERRIDE_284")
~~~

and the config tree also contains that key, asserting `FAKE_OVERRIDE_284` **does not prove the config tree was read**. The test-specific source can mask the file source.

To verify the import, pick a canary that exists only in the file, or add a dedicated marker property supplied nowhere else.

### 18.2. Do Not Dump the Whole `Environment` to Find the Winning Source

`Environment` may contain passwords, database URLs, or tokens for the entire application. Inspect only the source name and presence of allowlisted keys. In mock-value tests you may assert the exact mock value, while keeping real data out of logs.

### 18.3. When You Need to Test Precedence

Write a **separate** test with distinct fake values in two sources and assert which source wins according to your Boot version's documentation. Do not make one test verify both basic import and precedence without clarifying its purpose.

## 19. Config Tree Wildcards for Multiple Volumes

Spring Boot allows importing multiple configuration trees from immediate subdirectories using a wildcard:

~~~properties
spring.config.import=optional:configtree:/tmp/config/*/
~~~

Suppose:

~~~text
/tmp/config/
├── database/
│   └── demo/
│       └── db/
│           ├── username
│           └── password
└── messaging/
    └── demo/
        └── mq/
            ├── username
            └── password
~~~

The wildcard import can produce the properties:

~~~text
demo.db.username
demo.db.password
demo.mq.username
demo.mq.password
~~~

Subdirectories matching the wildcard are processed alphabetically according to Boot rules. If a different precedence order is needed, specify each location explicitly rather than relying on wildcard ordering.

### 19.1. Wildcards Match Immediate Children Only

The `*/` syntax selects **immediate subdirectories**. Do not assume it recursively searches directories at arbitrary depth. Nested file structures inside each child can still form nested property keys.

### 19.2. Do Not Use a Wildcard When Only One Specific Secret Should Be Supplied

Scanning a broad directory can inadvertently introduce unrelated values into `Environment`. For secrets, prefer mounting and importing **only the locations the application needs**.

### 19.3. Do Not Rely on Wildcards to Resolve Collisions

If two trees both define `demo.client.api-key`, the outcome depends on import precedence. A cleaner naming strategy is to separate prefixes clearly or grant only one source ownership of that key.

## 20. Applying with Kubernetes Secret Mounts

In Kubernetes, a Secret can be mounted into a container as a volume and project a key to an appropriately named file.

Partial Deployment example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-client
spec:
  replicas: 1
  selector:
    matchLabels:
      app: demo-client
  template:
    metadata:
      labels:
        app: demo-client
    spec:
      containers:
        - name: app
          image: registry.example.test/demo-client:1.0
          volumeMounts:
            - name: credentials
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: credentials
          secret:
            secretName: demo-client-credentials
            items:
              - key: api-key
                path: demo.client.api-key
~~~

Assuming `Secret/demo-client-credentials` is provisioned by a secure deployment workflow, the `api-key` key is projected as the file:

~~~text
/run/secrets/demo.client.api-key
~~~

The application has Config Data:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

When Boot starts, it can bind `demo.client.api-key` into the `DemoClientSecrets` record.

**Never place real Secret values into manifests stored in Git.** If a test requires a manifest, use mock placeholders or a sandbox namespace. Base64-encoded data in a Kubernetes Secret is not secret encryption.

### 20.1. Simulating the Volume with `@TempDir`

The primary goal of this lesson is simulating the filesystem locally with `@TempDir`. Consequently, unit/integration tests need neither permissions to create real Kubernetes Secrets, nor `kubectl`, nor a production cluster.

### 20.2. Secret Mounting and Config Tree Are Two Separate Layers

Kubernetes is responsible for delivering files into the container; Spring Boot merely reads the files and creates configuration properties. If a file is not mounted, the bug lies in the runtime platform or deployment; if the file exists yet the Java bean receives nothing, inspect the import root, filename, prefix, and Binder.

### 20.3. Rotation Does Not Automatically Update Every Bean

A Kubernetes Secret volume may be updated by the platform, yet ordinary `@ConfigurationProperties` beans are bound at startup. Do not assume that a newer file on disk means the running client already uses the new credential. You need a restart/redeploy or an intentional, tested reload mechanism.

## 21. Applying with Docker Compose Secrets

Docker Compose can deliver secret files to a container.

Example:

~~~yaml
services:
  demo-client:
    image: registry.example.test/demo-client:1.0
    secrets:
      - source: demo_api_key
        target: demo.client.api-key

secrets:
  demo_api_key:
    file: ./local-fake-secrets/api-key.txt
~~~

The container typically receives the secret at:

~~~text
/run/secrets/demo.client.api-key
~~~

The application uses:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

For local runs, `./local-fake-secrets/api-key.txt` contains only a **fake token**. Never commit a real local secret or copy it into a Docker image.

### 21.1. Do Not Confuse Docker Build Time with Runtime Secrets

Docker `ARG` and `ENV` are not safe channels for baking secrets into an image. Runtime secrets are supplied after build time, reducing copies of credentials in artifacts and registries.

### 21.2. One Docker Image, Many Environments

An image containing no API keys can run across local, staging, and production; each deployment mounts different secrets. That is the operational goal of Externalized Configuration, and `@TempDir` tests validate the Spring Boot side without depending on a secret backend.

## 22. Comparing Env Vars, Config Data Files, and `configtree`

| Supply mechanism | Data format | Timing | Best fit |
| --- | --- | --- | --- |
| `demo.client.api-key=...` in application.yml | Value inside config file | Build or runtime file | Fake secrets in tests only; avoid real secrets on classpath |
| `DEMO_CLIENT_APIKEY=...` | Environment variable | Process runtime | Simple configuration injected by platform |
| `configtree:/run/secrets/` | File-per-property | Boot Config Data | Mounted secret volumes |
| `file:/etc/app/secret.yml` | Combined YAML/properties file | Boot Config Data | Platform supplies a single config file |
| Secret manager integration | External API/backend | Depends on integration | Versioning, rotation, auditing |
| `@TestPropertySource(properties=...)` | Inline test key/value | TestContext | Testing binding/overrides only, not configtree import |
| `ApplicationContextRunner.withPropertyValues(...)` | Inline runner values | Test runner | Small binding/validation tests, does not test full Config Data |

The key is clarifying **the test objective**. If you only want to test logic consuming an API key, an inline fake value may suffice. If you want to exercise `configtree:` accurately, create files and go through Config Data.

## 23. Reproducing an Incorrect Import Root Error

Directory:

~~~text
/tmp/secrets/
└── demo/
    └── client/
        └── api-key
~~~

Incorrect if the target expects `demo.client.api-key`:

~~~properties
spring.config.import=configtree:/tmp/secrets/demo/client/
~~~

Because importing too deeply leaves the key as only `api-key`.

Correct:

~~~properties
spring.config.import=configtree:/tmp/secrets/
~~~

Or change the layout to a file named `demo.client.api-key` under the imported root.

### 23.1. How to Diagnose

1. Check the exact import root.
2. Check the relative path from the root to the file.
3. Determine the resulting property name.
4. Compare it against the prefix in `@ConfigurationProperties`.
5. Test with a fake file—there is no need to inspect real secret values.

### 23.2. Do Not "Fix" by Arbitrarily Changing Java Fields

If the contract calls for `demo.client.api-key`, do not change the record to `@ConfigurationProperties(prefix = "")` just to make it bind. Fix the mount filename or import root to align with the contract.

## 24. Reproducing an Invalid File-Content Error

Someone creates the file:

~~~text
demo.client.api-key
~~~

and writes:

~~~properties
demo.client.api-key=FAKE_TEST_KEY_284
~~~

This **differs** from the requirement that the file contain only the value:

~~~text
FAKE_TEST_KEY_284
~~~

In a config tree, the filename already acts as the key. Do not repeat `key=value` syntax inside the file.

### 24.1. Diagnosing with a Fake Canary

If a test receives a string starting with `demo.client.api-key=`, inspect how the fixture was created. Tests should assert the exact fake value to catch this.

### 24.2. Diagnosing Newlines

If you receive `FAKE_TEST_KEY_284\n` instead of `FAKE_TEST_KEY_284`, check whether the file was created with `echo`. Fix the fixture to match the real contract; do not silently trim every secret in production.

## 25. Test Isolation and Cleanup

A good test introduces no dependencies across runs.

### 25.1. One Directory per Test

`@TempDir` gives each test its own temporary directory. Do not hard-code `/tmp/app-secrets` when multiple CI jobs run concurrently, or Test A can overwrite Test B's files.

### 25.2. Start the Context After Creating Files

If Spring Boot processes Config Data before the test writes the files, the context will not automatically reload the directory afterward. Thus the proper sequence is:

~~~text
Create @TempDir
   -> Write fake files
   -> Construct import location
   -> Run SpringApplication
   -> Assert values
   -> Close context
   -> Cleanup temp files
~~~

Do not invert the order to "run context first, then write fake files" expecting `@ConfigurationProperties` to update automatically.

### 25.3. Close the Context After Testing

`try (ConfigurableApplicationContext ... )` closes the context. This matters if the application context holds resources or background threads. JUnit can clean up `@TempDir` once the test finishes.

### 25.4. Do Not Write Temporary Files into the Source Repository

Some tests place fixtures in `src/test/resources/secrets`; with purely fake values that can be acceptable, though those files remain in Git and on the test classpath. A temporary directory better models runtime mounted files and reduces the risk of accidentally shipping credentials.

### 25.5. Parallel Test Execution

Each test should have a unique directory and a unique context. Avoid static global system properties holding `spring.config.import`, as they can affect other tests in the same JVM. Pass the import location per test via the bootstrap builder.

## 26. Securing Logs and Assertions

Fake data is harmless, yet we should practice **production-grade safety habits**.

### 26.1. Do Not Print the Entire `Environment`

Incorrect:

~~~java
environment.getPropertySources()
        .forEach(source -> log.info("{}", source));
~~~

Some `PropertySource` instances or diagnostics can contain sensitive information. Inspect only allowlisted keys in tests, using assertions instead of dumping the entire environment.

### 26.2. Do Not Log the Whole Configuration Record

Incorrect:

~~~java
log.info("Secrets: {}", credentials);
~~~

A record can print `apiKey` and `password` via `toString()`. While a test receiving fake values may seem harmless, that code becomes dangerous if copied into production runtime code.

### 26.3. Startup Failure Tests Need Canaries Too

When the Binder, conversion, or validation fails, the framework can include the rejected value in exception messages. When testing with real secrets (which you should avoid), raw exception output would be unsafe. Use fake canaries and verify pipeline logs whenever log security is part of the objective.

### 26.4. Do Not Put Raw Secrets into Metrics or Traces

Never add attributes such as `config.value=FAKE_TEST_KEY_284` in tests intending to replace them with real tokens later. Record error codes, component names, types, or statuses instead.

### 26.5. Test Secrets Must Be Genuinely Fake

Never take a sandbox token capable of calling a real service and label it "fake". Only a mock value such as `FAKE_TEST_KEY_284` unrecognized by any external system qualifies as genuinely fake data.

## 27. Difference Between a Secret Store and `configtree`

There are three independent concerns:

1. **Storage and authorization:** secret manager, Kubernetes Secret, Docker secret, or internal store determines who may read.
2. **Delivery to runtime:** environment injection, mounted volume, sidecar, CSI driver, or API client.
3. **Loading into Spring Boot:** `configtree:`, Config Data files, env vars, or custom integration.

`configtree:` solves only the **third** layer once data is already present on the filesystem.

### 27.1. Do Not Assume Kubernetes Secrets Are Encrypted by Default

Base64 encoding of `Secret.data` is not encryption. API read permissions, volume mount permissions, and encryption at rest must be configured on the platform.

### 27.2. Do Not Assume Read-Only Files Mean Complete Safety

A container permitted to read a file can still accidentally log its contents. A read-only volume prevents modification through the mount, not disclosure by code permitted to read the secret.

### 27.3. Do Not Use `random.value` as a Secret Manager

Spring Boot offers a random property source convenient for certain test values, yet it provides none of the lifecycle, rotation, backup, or governance required for a production signing or encryption key.

## 28. Acceptance Test Scenarios

A test suite should include these cases:

| ID | Fixture data | What to verify |
| --- | --- | --- |
| CT-01 | Three fake files, exact names | Bean receives all three expected values |
| CT-02 | Only the `api-key` file | Property is present; others missing if no defaults exist |
| CT-03 | Import root too deep | Expected prefix receives no properties |
| CT-04 | Filename in dot notation | Property name matches |
| CT-05 | Nested tree `demo/client/api-key` | Same semantics as dot notation |
| CT-06 | Missing required directory | Bootstrap failure |
| CT-07 | Missing optional directory | Config Data ignores missing location |
| CT-08 | Directory exists, missing `api-key` | Validation/required check rejects when mandatory |
| CT-09 | Empty file | Non-blank validation fails when enabled |
| CT-10 | File with trailing newline | Assert exact handling policy |
| CT-11 | Binary file | Binds accurately to `byte[]` |
| CT-12 | CLI fake override | Understand precedence in a separate test |
| CT-13 | Two wildcard trees | Receives all keys with no collision |
| CT-14 | Concurrent tests | No shared temporary directory |
| CT-15 | No secrets in source/artifacts | Pipeline checks in place |
| CT-16 | Context starts after files exist | Import actually executes |

Each case has a clear purpose. Do not cram everything into a single giant `@SpringBootTest`.

### 28.1. When to Assert Context Failure

If testing a missing directory, assert a Config Data error from bootstrap. If testing a missing key, assert a validation failure or required-property check. These are two distinct failure classes—do not collapse them into one assertion that merely checks "the context failed to start".

### 28.2. Testing the Consequence of a Wrong Prefix

When the import location points to `.../demo/client/`, the key may be `api-key`. To prove the root cause, assert the presence of `api-key` and absence of `demo.client.api-key` in a context that does not require the bean, then fix the import root.

## 29. A Command-Line Example for Self-Verification

In a Spring Boot project that already has `DemoClientSecrets` registered as a bean:

~~~bash
mkdir -p /tmp/demo-secret-fixture

printf '%s' 'FAKE_TEST_KEY_284' \
  > /tmp/demo-secret-fixture/demo.client.api-key

printf '%s' 'demo-user' \
  > /tmp/demo-secret-fixture/demo.client.username

printf '%s' 'FAKE_TEST_PASSWORD_284' \
  > /tmp/demo-secret-fixture/demo.client.password

java -jar target/demo-app.jar \
  --spring.config.import=configtree:/tmp/demo-secret-fixture/
~~~

This example only illustrates launching; match the JAR name and entrypoint to your actual project. Never alter application code to log credentials. You can create a test-only bean checking presence or rely on the JUnit assertions shown earlier.

### 29.1. Windows PowerShell

In PowerShell, you can create the directory and files with the appropriate commands. For example:

~~~powershell
$root = Join-Path $env:TEMP "demo-configtree-fixture"
New-Item -ItemType Directory -Force -Path $root | Out-Null

[System.IO.File]::WriteAllText(
    (Join-Path $root "demo.client.api-key"),
    "FAKE_TEST_KEY_284"
)
~~~

Creating the file with .NET `WriteAllText` in this example does not add a newline automatically. Pass the root path into the Config Data import in a location format handled properly by your Spring Boot version and OS. For cross-platform automated tests, prefer Java NIO / `@TempDir` to minimize shell dependencies.

### 29.2. Cleaning Up Files After Manual Experiments

When finished, delete **only the exact fixture directory** you created. Never run a recursive delete against an unverified variable. Automated tests managed by `@TempDir` are generally safer than manual cleanup.

## 30. Common Mistakes

### 30.1. Importing a Single File Instead of a Directory Tree

~~~properties
spring.config.import=configtree:/tmp/secrets/application.properties
~~~

is wrong when trying to parse a combined properties file. Use `file:` for a single file or switch to a per-file tree.

### 30.2. Putting `key=value` Inside the File Contents

In a config tree, the filename is already the key. The file contents must be only the value.

### 30.3. Setting the Import Root Too Deep

If the `demo.client` prefix sits in the folder hierarchy above the root, the property loses its full prefix. Pick the right root.

### 30.4. Using `optional:` Without Validation

`optional:` handles only missing locations; it does not guarantee required fields exist. Add validation.

### 30.5. Expecting `@TestPropertySource` to Exercise `configtree` Import

`@TestPropertySource` places values into the test `Environment` via the TestContext mechanism; it should not be assumed to exercise full early Config Data imports. Boot the application after creating the directory and assert a marker.

### 30.6. Creating Files After the Context Has Started

Already bound beans do not refresh automatically. Create files before calling `run()`.

### 30.7. Tests Passing Due to Another Override

If an inline test property defines the same key, it can shadow the config tree. Use a fake canary present only in the file or verify a marker.

### 30.8. Writing Files with `echo` and Appending Newlines

Some clients treat a newline as part of the credential. Use `printf '%s'` or `Files.writeString` with the exact string.

### 30.9. Putting Real Credentials in Test Fixtures

Use fake data with no real access permissions. Even an active sandbox token must still be treated as a sensitive credential.

### 30.10. Committing Secrets to Git for Testing Convenience

If a project needs real credentials for an integration environment, inject them via an appropriate runtime secret store or CI mechanism; never commit credentials to `src/test/resources`.

### 30.11. Forgetting to Close the Application Context

A context can retain resources, threads, or ports. Use try-with-resources and clean up temp directories.

### 30.12. Checking Only `Environment` Without Checking the Bean

Property presence does not guarantee prefix matching, binding, or validation succeeded. Assert both the marker property and the bound bean values.

### 30.13. Confusing Filenames with OS Environment Names

`demo.client.api-key` is the canonical filename; `DEMO_CLIENT_APIKEY` is the OS environment format. Do not treat the two sources as sharing the same naming syntax.

### 30.14. Uncontrolled Wildcards Across Many Secrets

Wildcards can import more trees than needed and create confusing collisions or precedence issues. Mount and import only the data the application needs.

### 30.15. Assuming `configtree` Encrypts Data

Config trees only read files. Securing the volume belongs to the platform and runtime permissions.

## 31. Pre-Completion Checklist

- [ ] Using a Spring Boot version that supports Config Data and `configtree:`.
- [ ] Using 100% fake tokens/passwords with no real credentials.
- [ ] A dedicated temporary directory is created per test.
- [ ] Files are created **before** starting the context.
- [ ] Filenames match canonical property names.
- [ ] File contents contain only the value, not `key=value`.
- [ ] Import location uses `configtree:<directory>/` with the proper root.
- [ ] Classpath paths are not used when simulating mounted secrets.
- [ ] `@ConfigurationProperties` bean is properly registered.
- [ ] Java target type matches `String` or `byte[]`.
- [ ] Assertions verify the exact mock values.
- [ ] A marker property proves the import actually executed.
- [ ] Missing directory is tested separately from missing property.
- [ ] Validation is enabled when credentials are required.
- [ ] Testing optional imports does not mask missing-secret failures.
- [ ] No higher-precedence source accidentally overrides fake values.
- [ ] Tests never print configuration objects or `Environment` to logs.
- [ ] No fake or real secret files are accidentally copied into the production JAR.
- [ ] Context is closed and temporary files are cleaned up.
- [ ] Tests run independently across multiple JVMs/CI jobs.
- [ ] Able to explain the differences among a config tree, YAML imports, and a secret manager.
- [ ] Reload/restart strategy exists when runtime secrets rotate.

## 32. Extension Exercises

### Exercise A — Dot Filenames vs. Nested Directories

Create two separate fixtures:

~~~text
fixture-one/demo.client.api-key
fixture-two/demo/client/api-key
~~~

Import each root and assert that both produce the `demo.client.api-key` property. Do not create both duplicate forms in the same tree unless you have explicitly defined precedence.

### Exercise B — Optional Directories

For a non-existent directory, compare:

~~~properties
spring.config.import=configtree:/not-found/
~~~

and:

~~~properties
spring.config.import=optional:configtree:/not-found/
~~~

Explain why one case can fail during Config Data bootstrap while the other proceeds yet still lacks credentials.

### Exercise C — Validation

Add `@Validated` and `@NotBlank` to the record. Create a fixture missing `demo.client.api-key`. Assert that context startup fails due to the required property. Never include passwords in error messages.

### Exercise D — Newlines

Create one file with `Files.writeString(path, "FAKE_TEST_KEY_284\n")` and one without a newline. Compare the value bound by the Binder, then determine the contract your real application needs.

### Exercise E — Precedence

Create a file containing `FAKE_FILE_KEY`. Launch the test with a different fake command-line property for the same key. Assert the effective value inside the Boot context and explain why this test should be separate from the pure import test.

### Exercise F — Binary

Create four dummy bytes, bind them to `byte[]`, and assert exact byte equality. Avoid converting contents to `String` for logging.

### Exercise G — Wildcards

Create:

~~~text
config/dbsource/demo/db/password
config/mqsource/demo/mq/password
~~~

Import `configtree:<root>/*/` and assert that both `demo.db.password` and `demo.mq.password` are present. Explain alphabetical ordering and the risk of key collisions.

## 33. Conclusion

The practice **"Loading Test Secrets from configtree: with Mock Data"** illustrates an essential use of Spring Boot Externalized Configuration: **separating sensitive values from the JAR and source code** by reading files provisioned by the runtime environment.

Core workflow:

1. Create a temporary directory where each file represents **one property name**.
2. Write **fake** data to each file without adding `key=value` syntax.
3. Use `spring.config.import=configtree:<directory>/` during the proper Boot Config Data phase.
4. Start the context **after** the files exist.
5. Bind to `@ConfigurationProperties` and assert exact values and a marker.
6. Test missing directories, missing keys, empty files, newlines, and precedence separately.
7. Clean up resources, never log raw secrets, and never include real credentials in tests or artifacts.

Remember that **`configtree:` is a data-loading mechanism**, not a vault, encryption engine, or hot-reload system. Spring Boot handles turning files into properties; the deployment platform handles delivering and protecting secrets. Testing with `@TempDir` and fake canaries verifies that boundary without needing access to a Kubernetes cluster or production credentials.

### References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Using Configuration Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing-configuration-trees)
- [Spring Boot Reference — Importing Additional Data](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing)
- [Spring Boot API — SpringApplicationBuilder](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [JUnit Jupiter — @TempDir](https://junit.org/junit5/docs/current/user-guide/#writing-tests-built-in-extensions-TempDirectory)
- [Kubernetes Documentation — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Docker Documentation — Manage Secrets](https://docs.docker.com/engine/swarm/secrets/)

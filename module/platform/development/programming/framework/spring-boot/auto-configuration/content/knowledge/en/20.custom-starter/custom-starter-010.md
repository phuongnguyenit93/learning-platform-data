# Verifying a Starter from a Consumer Project Independent of the Library Source Code

> **Spring Boot Auto Configuration → Custom Starter.** This lesson guides verifying a starter using a separate consuming project that depends solely on packaged artifacts resolved through Maven. The focus is confirming the dependency graph, JAR contents, auto-configuration registration file, runtime bean behavior, and override capability from the application side. Examples use Java 17+, Maven, and Spring Boot 3.3.13.

## 1. Why Verify From an Independent Project?

A library can run properly inside its own repository yet fail when users install it into real applications. Common causes:

- The auto-configuration class exists in source yet is missing from the JAR.
- The `AutoConfiguration.imports` file is in the wrong directory or has an incorrect fully qualified class name.
- The starter does not declare a dependency on the auto-configuration module.
- The auto-configuration module does not pull the core module along the dependency graph.
- A runtime-needed dependency is declared with an inappropriate scope.
- Demo code accidentally uses `@Import` or component scanning to load configuration, masking broken auto-configuration registration.
- The Maven reactor sees sibling modules in the same build, whereas external users only have published artifacts.
- The Spring Boot or library version resolved in the consumer differs from the version used while developing the starter.

Therefore, running tests inside the library modules alone is insufficient. You need an **independent consumer**:
- Located outside the library's Maven reactor.
- Does not import source files or class outputs from the library.
- Does not declare `systemPath`, `../` paths, or `relativePath` to library modules.
- Depends solely on the starter's Maven coordinates `groupId:artifactId:version`.
- Built after the library has been installed into a local repository or published to a shared repository.

If the consumer builds cleanly without opening the library's source repository, you have much stronger proof that the starter was packaged and published properly.

## 2. What Needs to Be Verified

A starter verification pass should cover four layers:

| Verification layer | Question | Evidence |
| --- | --- | --- |
| Artifact | Are the required JARs built and installed? | Files in `target/` and local Maven repository |
| Metadata | Can Boot discover auto-configuration from the JAR? | `META-INF/spring/...AutoConfiguration.imports` inside the JAR |
| Dependency | Does the consumer receive core, auto-config, and required dependencies? | `mvn dependency:tree` |
| Runtime behavior | Are beans created, disabled, and overridden properly? | Integration tests and consumer application stdout |

Checking that artifacts exist is not enough. A JAR can be installed into a repository yet miss imports metadata. A dependency tree can look complete yet conditions fail to match. A context can start yet fail to create the default bean. Each layer requires its own evidence.

## 3. Distinguishing Three Projects and Two Dependency Resolution Environments

The example uses three library modules and one independent consumer:

~~~text
workspace/
├── notice-library/
│   ├── pom.xml
│   ├── notice-core/
│   ├── notice-autoconfigure/
│   └── notice-spring-boot-starter/
│
└── notice-consumer/
    ├── pom.xml
    └── src/
~~~

`notice-library` is the Maven reactor. It contains modules developed and released together:
- `notice-core`: core API and logic.
- `notice-autoconfigure`: bean definitions and auto-configuration metadata.
- `notice-spring-boot-starter`: artifact bundling dependencies for users.

`notice-consumer` is a separate Maven project. It only sees artifacts installed into the local Maven repository or downloaded from a remote repository.

### 3.1. How Does a Maven Reactor Differ From the Local Repository?

In a Maven reactor build, Maven can resolve module dependencies directly from sibling modules' outputs within the same reactor. This is convenient during development, yet it can hide packaging or publication bugs.

`mvn install` builds and installs artifacts into the default local repository, typically:

~~~text
~/.m2/repository/
~~~

On Windows, the directory typically sits under:

~~~text
%USERPROFILE%\.m2\repository\
~~~

After installing, the consumer can resolve dependencies by Maven coordinates without knowing the library's source directory.

Distinguish between them:
- `mvn package`: builds artifacts in `target/`, without installing into the local repository.
- `mvn install`: builds artifacts and installs them into the local repository.
- `mvn deploy`: uploads artifacts to a configured remote repository, typically used in CI/releases.

In this hands-on exercise, use `install` for local verification. You do not need to publish artifacts externally to prove a consumer can use packaged dependencies.

## 4. Designing the Sample Library

We create a minimal notification library. When the starter is installed, Spring Boot automatically supplies a `NoticeClient` bean. Applications can disable the bean via a property or declare their own replacement bean.

### 4.1. Library Structure

~~~text
notice-library/
├── pom.xml
├── notice-core/
│   ├── pom.xml
│   └── src/main/java/com/acme/notice/core/NoticeClient.java
├── notice-autoconfigure/
│   ├── pom.xml
│   ├── src/main/java/com/acme/notice/autoconfigure/NoticeAutoConfiguration.java
│   └── src/main/resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── notice-spring-boot-starter/
    └── pom.xml
~~~

### 4.2. Library Parent pom.xml

File `notice-library/pom.xml`:

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

    <groupId>com.acme.notice</groupId>
    <artifactId>notice-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <modules>
        <module>notice-core</module>
        <module>notice-autoconfigure</module>
        <module>notice-spring-boot-starter</module>
    </modules>
</project>
~~~

The parent manages Spring Boot, Java, and internal module versions. The Maven reactor orders the build based on dependency relationships; module listing order does not substitute for declaring real dependencies.

### 4.3. Core Module

File `notice-core/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.notice</groupId>
        <artifactId>notice-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>notice-core</artifactId>
</project>
~~~

File `notice-core/src/main/java/com/acme/notice/core/NoticeClient.java`:

~~~java
package com.acme.notice.core;

public class NoticeClient {

    public String send(String message) {
        return "sent:" + message;
    }
}
~~~

The core module needs neither Spring Boot nor Spring Context. It simply provides an independent API for other modules to use. In real projects, this is where interfaces, domain objects, and foundational logic reside without needing to know how Spring registers beans.

### 4.4. Auto-Configuration Module

File `notice-autoconfigure/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.notice</groupId>
        <artifactId>notice-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>notice-autoconfigure</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.acme.notice</groupId>
            <artifactId>notice-core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

File `notice-autoconfigure/src/main/java/com/acme/notice/autoconfigure/NoticeAutoConfiguration.java`:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.core.NoticeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NoticeClient.class)
    NoticeClient noticeClient() {
        return new NoticeClient();
    }
}
~~~

The configuration has two conditions:
- If `acme.notice.enabled` is absent or equals `true`, auto-configuration can apply.
- If the application has not supplied a `NoticeClient`, Spring creates the default bean.

When the property is `false`, the default bean is not created. When the application declares its own `NoticeClient`, the missing-bean condition makes auto-configuration yield to the application's bean.

### 4.5. Registering Auto-Configuration With Imports Metadata

Create the file at the exact path:

~~~text
notice-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Single-line content:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
~~~

This is a critical step when verifying a starter. The `NoticeAutoConfiguration` class can compile and sit inside the JAR, yet Spring Boot will not discover it automatically if imports metadata is missing, in the wrong path, or lists an incorrect FQCN.

Do not rely on the application's component scan to find auto-configuration classes in the library. Spring Boot 3's standard registration mechanism is the `AutoConfiguration.imports` file.

### 4.6. Starter Module

File `notice-spring-boot-starter/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.notice</groupId>
        <artifactId>notice-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>notice-spring-boot-starter</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.acme.notice</groupId>
            <artifactId>notice-autoconfigure</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

The starter is the dependency-aggregating artifact. It brings auto-configuration and needed dependencies into the application. `notice-core` is pulled transitively through `notice-autoconfigure`; because the default dependency scope is `compile`, consumers can import `NoticeClient` in source code.

The starter needs no Java classes if it has no separate logic. The starter JAR can be nearly empty of source code yet remains valuable because its dependency descriptor determines which artifacts enter the consumer.

## 5. Building and Installing the Library into the Local Maven Repository

Open a terminal in `notice-library`, the directory containing the parent `pom.xml`, and run:

~~~bash
mvn clean install
~~~

Maven performs:
1. Build `notice-core`.
2. Build `notice-autoconfigure` with the core dependency.
3. Build `notice-spring-boot-starter` with the auto-config dependency.
4. Package each module's JAR and POM.
5. Install the parent and artifacts into the local Maven repository.

Expected output:

~~~text
notice-core/target/notice-core-1.0.0.jar
notice-autoconfigure/target/notice-autoconfigure-1.0.0.jar
notice-spring-boot-starter/target/notice-spring-boot-starter-1.0.0.jar
~~~

In the local Maven repository, coordinates map to directory paths:

~~~text
com/acme/notice/notice-core/1.0.0/
com/acme/notice/notice-autoconfigure/1.0.0/
com/acme/notice/notice-spring-boot-starter/1.0.0/
~~~

Each directory typically holds the POM, JAR, and Maven-managed metadata.

If the build fails, fix errors in the failing module before creating the consumer. Never use a consumer to test artifacts that have not yet built or installed successfully.

### 5.1. Verifying Generated JARs

From `notice-library`, run:

~~~bash
dir notice-core/target
dir notice-autoconfigure/target
dir notice-spring-boot-starter/target
~~~

On Bash:

~~~bash
ls notice-core/target
ls notice-autoconfigure/target
ls notice-spring-boot-starter/target
~~~

Check that filenames and versions match the dependency coordinates the consumer will use.

### 5.2. Verifying AutoConfiguration.imports Inside the JAR

On Windows PowerShell/CMD:

~~~powershell
jar tf notice-autoconfigure/target/notice-autoconfigure-1.0.0.jar | findstr /I AutoConfiguration.imports
~~~

On Bash:

~~~bash
jar tf notice-autoconfigure/target/notice-autoconfigure-1.0.0.jar | grep AutoConfiguration.imports
~~~

The output must contain:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Next, check the auto-configuration class:

~~~bash
jar tf notice-autoconfigure/target/notice-autoconfigure-1.0.0.jar
~~~

The listing must include the matching class path:

~~~text
com/acme/notice/autoconfigure/NoticeAutoConfiguration.class
~~~

If the class exists yet the imports file is missing, check the file's location under `src/main/resources`. Maven only copies resources from standard locations into the JAR by default.

You can inspect the file contents inside the JAR with:

~~~bash
unzip -p notice-autoconfigure/target/notice-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

If `unzip` is unavailable in your environment, use an appropriate ZIP/JAR tool. The returned line must be the exact FQCN, with no misspelled class name or stale package.

## 6. Creating an Independent Consumer

Now switch to the `notice-consumer` directory alongside `notice-library`:

~~~text
workspace/
├── notice-library/
│   └── pom.xml
└── notice-consumer/
    ├── pom.xml
    └── src/
        ├── main/java/com/acme/consumer/ConsumerApplication.java
        └── test/java/com/acme/consumer/
            ├── NoticeStarterEnabledTest.java
            ├── NoticeStarterDisabledTest.java
            └── NoticeStarterOverrideTest.java
~~~

The consumer is not a submodule of `notice-library`. It has its own Maven parent and declares dependencies strictly by coordinates.

### 6.1. Consumer pom.xml

File `notice-consumer/pom.xml`:

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

    <groupId>com.acme.consumer</groupId>
    <artifactId>notice-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme.notice</groupId>
            <artifactId>notice-spring-boot-starter</artifactId>
            <version>1.0.0</version>
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

Points to verify:
- The consumer declares only `notice-spring-boot-starter`.
- The consumer does not directly declare `notice-core` or `notice-autoconfigure`.
- No JAR file paths via `systemPath`.
- No `file:` dependencies or `../notice-library/...`.
- No source directories added from the library repository.
- The consumer uses Spring Boot 3.3.13 to match the compile version of the sample library.

Declaring only the starter verifies the actual dependency graph users receive.

### 6.2. ConsumerApplication.java

File `notice-consumer/src/main/java/com/acme/consumer/ConsumerApplication.java`:

~~~java
package com.acme.consumer;

import com.acme.notice.core.NoticeClient;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ObjectProvider<NoticeClient> clients) {
        return args -> {
            NoticeClient client = clients.getIfAvailable();

            System.out.println(
                    "noticeClient present: " + (client != null)
            );

            if (client != null) {
                System.out.println(
                        "notice result: " + client.send("hello")
                );
            }
        };
    }
}
~~~

The application resides in package `com.acme.consumer`, separate from the library package `com.acme.notice`. `@SpringBootApplication` does not component-scan the library package. When the bean appears, that is strong evidence Boot discovered auto-configuration through the imports metadata inside the artifact.

`ObjectProvider` allows the runner to handle the case where the feature is disabled. The consumer does not inject `NoticeClient` as a mandatory constructor parameter because the verification needs to observe both bean-present and bean-absent states.

### 6.3. Test Default Starter Bean Creation

File `NoticeStarterEnabledTest.java`:

~~~java
package com.acme.consumer;

import com.acme.notice.core.NoticeClient;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class NoticeStarterEnabledTest {

    @Autowired
    ApplicationContext context;

    @Test
    void starterRegistersNoticeClientInConsumer() {
        assertThat(context).hasSingleBean(NoticeClient.class);
        assertThat(context.getBean(NoticeClient.class).send("hello"))
                .isEqualTo("sent:hello");
    }
}
~~~

This test neither imports `NoticeAutoConfiguration` nor uses `@Import`. It simply boots the consumer like a real application and verifies the bean is present and works.

### 6.4. Test Property Disabling the Default Bean

File `NoticeStarterDisabledTest.java`:

~~~java
package com.acme.consumer;

import com.acme.notice.core.NoticeClient;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "acme.notice.enabled=false")
class NoticeStarterDisabledTest {

    @Autowired
    ApplicationContext context;

    @Test
    void disabledPropertyPreventsDefaultBean() {
        assertThat(context).doesNotHaveBean(NoticeClient.class);
    }
}
~~~

This test confirms the starter's public property is read in the consuming project. It also proves beans are not created merely because the JAR is on the classpath; conditions are still enforced.

### 6.5. Test User Bean Override

Create a test configuration:

~~~java
package com.acme.consumer;

import com.acme.notice.core.NoticeClient;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class CustomNoticeClientConfiguration {

    @Bean
    NoticeClient customNoticeClient() {
        return new NoticeClient() {
            @Override
            public String send(String message) {
                return "custom:" + message;
            }
        };
    }
}
~~~

File `NoticeStarterOverrideTest.java`:

~~~java
package com.acme.consumer;

import com.acme.notice.core.NoticeClient;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = {
        ConsumerApplication.class,
        CustomNoticeClientConfiguration.class
})
class NoticeStarterOverrideTest {

    @Autowired
    ApplicationContext context;

    @Test
    void userBeanMakesStarterBackOff() {
        assertThat(context).hasSingleBean(NoticeClient.class);
        assertThat(context.getBean(NoticeClient.class).send("hello"))
                .isEqualTo("custom:hello");
    }
}
~~~

Because `NoticeClient` is not final and `send` can be overridden, the test creates a custom implementation. If the starter still created a competing default bean, the `hasSingleBean` assertion would fail; if the starter failed to back off, the `custom:hello` result would not appear.

This tests the override contract on the user side. No edits to the library source are needed to run the test.

## 7. Building the Consumer Without Using the Library's Maven Reactor

Once `mvn clean install` has succeeded in `notice-library`, open a new terminal or switch completely into `notice-consumer`.

From `notice-consumer`, run:

~~~bash
mvn clean test
~~~

Maven reads only the consumer's POM and resolves:
- Spring Boot dependencies.
- `com.acme.notice:notice-spring-boot-starter:1.0.0`.
- Transitive dependencies declared by the starter.

Expected three tests PASS:
1. Default starter creates `NoticeClient`.
2. Property `acme.notice.enabled=false` prevents the default bean.
3. Application-supplied bean takes precedence.

Do not run this command from `notice-library` with `-pl notice-consumer` or add the consumer as a parent module just so Maven sees sibling modules. The goal is proving dependencies install and resolve like an external library.

### 7.1. Inspecting the Consumer's Dependency Tree

From `notice-consumer`:

~~~bash
mvn dependency:tree -Dincludes=com.acme.notice
~~~

Representative output must reflect the relationship:

~~~text
com.acme.consumer:notice-consumer:jar:1.0.0
+- com.acme.notice:notice-spring-boot-starter:jar:1.0.0:compile
   +- com.acme.notice:notice-autoconfigure:jar:1.0.0:compile
      +- com.acme.notice:notice-core:jar:1.0.0:compile
~~~

Exact formatting may vary by Maven and plugin version, yet all three artifacts must appear in the dependency graph.

If `notice-core` is absent, the consumer may fail to compile importing `NoticeClient`. Check the POMs of `notice-autoconfigure` and the starter to ensure the dependency was not marked optional or given an unsuitable scope.

If `notice-autoconfigure` is absent, the starter POM did not pull the configuration module. Even if the core API is on the classpath, Boot has no auto-configuration to register the bean.

### 7.2. Verifying the Consumer Does Not Reference the Source Repository

Open `notice-consumer/pom.xml` and source files, confirming:
- No `notice-consumer` module in the library's parent.
- No `relativePath` pointing back to `notice-library`.
- No `systemPath` pointing to JAR files.
- No plugin adding source folders from the library.
- No import of `NoticeAutoConfiguration` in `ConsumerApplication`.
- No `@Import(NoticeAutoConfiguration.class)`.

The consumer only needs to import the public API `NoticeClient`. Spring Boot automatically discovers configuration from the dependency JAR.

This is one of the most important verification criteria: **if you must open the library source or manually import auto-configuration, the starter has not been proven to work as an independent starter.**

## 8. Running the Actual Consumer Application

After tests pass, package the consumer:

~~~bash
mvn -q -DskipTests package
~~~

Run the JAR:

~~~bash
java -jar target/notice-consumer-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Stdout printed by `ApplicationRunner`:

~~~text
noticeClient present: true
notice result: sent:hello
~~~

This proves:
- The consumer compiles against the API from installed artifacts.
- The starter pulls core and auto-configuration into runtime.
- Boot discovers metadata inside the JAR.
- Default conditions match.
- The bean is created and injected into the consumer.
- The API executes.

### 8.1. Running Again With the Property Disabled

~~~bash
java -jar target/notice-consumer-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --acme.notice.enabled=false
~~~

Stdout:

~~~text
noticeClient present: false
~~~

The application still starts because the runner uses `ObjectProvider`. No default bean exists when the property is disabled.

### 8.2. Running With the Property Explicitly Enabled

~~~bash
java -jar target/notice-consumer-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --acme.notice.enabled=true
~~~

Stdout:

~~~text
noticeClient present: true
notice result: sent:hello
~~~

The result matches the default case because auto-configuration uses `matchIfMissing=true`. In real libraries, the default might be disabled; in that case adjust documentation and tests to match the product's policy.

## 9. Verifying With JAR, Dependency Tree, and Condition Evaluation Report

When the consumer fails to create a bean, do not immediately patch application code. Inspect layer by layer.

### 9.1. Was the Artifact Resolved?

~~~bash
mvn dependency:tree -Dincludes=com.acme.notice
~~~

If the starter does not appear, check dependency coordinates:
- `groupId`
- `artifactId`
- `version`
- Repositories Maven is searching
- Whether the local repository contains the corresponding artifact

If it reports `Could not find artifact`, check `mvn install` in the library and the version in the consumer. For remote repositories, verify settings, credentials, and repository URLs per organizational workflow.

### 9.2. Did the Starter Pull Auto-Configuration?

The dependency tree must include `notice-autoconfigure`. If only `notice-spring-boot-starter` appears without this module, the starter POM is incomplete.

Open the POM installed in the local repository to inspect the published dependency declarations:

~~~text
~/.m2/repository/com/acme/notice/notice-spring-boot-starter/1.0.0/notice-spring-boot-starter-1.0.0.pom
~~~

On Windows, replace `~/.m2` with `%USERPROFILE%\.m2`. Verify the dependency has exact coordinates and is not marked optional unintentionally.

### 9.3. Does the Auto-Configuration JAR Contain Metadata?

Check:

~~~bash
jar tf notice-autoconfigure-1.0.0.jar
~~~

The JAR must contain:
- `com/acme/notice/autoconfigure/NoticeAutoConfiguration.class`
- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Read the imports contents and confirm the FQCN is exact. If metadata is missing, fix the resource path and rebuild/reinstall the artifact. Consumers will not guess which class is the auto-configuration.

### 9.4. Using --debug

Run the consumer with:

~~~bash
java -jar target/notice-consumer-1.0.0.jar --debug
~~~

In the Condition Evaluation Report, look for:
- `NoticeAutoConfiguration`
- `@ConditionalOnProperty`
- `@ConditionalOnMissingBean`

Cases:
- Configuration missing from the report: the JAR or imports metadata was likely not loaded.
- Property condition did not match: check property name, profiles, command line, and actual values.
- Missing-bean condition did not match: the application or another library already supplied `NoticeClient`.
- Configuration matched yet bean creation failed: read `BeanCreationException` and `Caused by`.

A positive match only shows conditions were satisfied; it does not prove every operation of the business bean will succeed.

### 9.5. Do Not Rely on Actuator When Startup Fails

The `/actuator/conditions` endpoint is helpful once the context has started and Actuator is added, exposed, and secured properly. If the context fails before the server is ready, use `--debug` and stack traces. Do not treat the endpoint as the sole diagnostic tool.

## 10. Stronger Independent Verification in CI

A local `mvn install` proves consumers can use artifacts from the local repository. CI can verify more strongly by splitting the pipeline into two jobs or two workspaces.

~~~text
Pipeline
   |
   +--> Job A: Build library
   |       |
   |       +--> mvn clean verify
   |       +--> package JARs
   |       +--> publish to staging Maven repository
   |
   +--> Job B: Build consumer
           |
           +--> checkout consumer only
           +--> resolve starter from staging repository
           +--> mvn clean test
           +--> package and run smoke test
~~~

Job B checks out only the consumer repository; it must not use the library's source workspace. This catches bugs that a local reactor can mask.

Options include:
- Publish snapshots to an internal staging repository.
- Use an ephemeral repository inside the pipeline.
- Use a local Maven repository seeded from artifacts built in the previous job.
- Create a separate integration test project, still building from installed artifacts rather than sibling modules.

Do not publish releases to a production repository solely for testing. Use a snapshot or staging repository, then promote verified artifacts through the release process.

### 10.1. Checking Versions and Cache

Maven caches artifacts in the local repository. When modifying the library while keeping the release version `1.0.0` unchanged, the consumer may continue using stale artifacts or cache unexpectedly.

During development:
- Bump snapshot versions such as `1.0.1-SNAPSHOT` while changing APIs.
- Re-run `mvn clean install` after edits.
- Verify the POM/JAR updated in the local repository.
- Use `mvn -U` when needed to update snapshots or metadata from remote repositories.

Do not delete all of `.m2` indiscriminately. When handling cache issues, identify the exact artifact coordinates and why Maven is resolving an old version.

For immutable release versions, never overwrite contents of an already-published artifact. Publish a new version so consumers can reproduce builds.

## 11. Recommended Test Cases for a Real Starter

The lab tests defaults, property disabling, and user overrides. For a production starter, expand the test matrix:

| Test case | What to verify |
| --- | --- |
| Starter on classpath, property absent | Default behavior matches contract |
| Property enabled | Default bean is created |
| Property disabled | Default bean is not created |
| User provides replacement bean | Auto-configuration backs off |
| Optional dependency missing | Corresponding integration does not break core |
| Prerequisite bean missing | Adapter depending on prerequisite bean is not created |
| Multiple beans of same type | `@Primary` / `@Qualifier` and conditions work properly |
| Supported Spring Boot versions | APIs and conditions are compatible |
| Executable JAR | Metadata and dependencies are packaged completely |
| Consumer without library source | Build/tests still succeed |

If a library has multiple integrations, create a consumer test per starter or dependency combination. Do not test only one catch-all starter pulling every feature, as optional dependency bugs become hard to isolate.

### 11.1. Minimal Classpath Tests

You can use Spring Boot test's `FilteredClassLoader` in the auto-configuration module to simulate missing optional libraries. However, tests must avoid directly referencing optional classes in test class signatures or annotations, otherwise classes may be resolved before conditions are evaluated.

For artifact verification, a consumer declaring only the core starter is critical proof that optional dependencies are not pulled unexpectedly. You can add dependency tree assertions in CI to check this.

### 11.2. Testing Metadata and Behavior

An independent consumer integration test should verify all of:
- The bean exists in the context.
- The bean has the right implementation/behavior.
- Enabling/disabling properties take proper effect.
- User overrides take precedence.
- The consumer does not need to import the auto-configuration class.

If a test merely calls `new NoticeClient()` directly, it does not verify the Spring Boot starter. If a test uses `@Import(NoticeAutoConfiguration.class)`, it tests the configuration class yet bypasses Boot's discovery of metadata inside the JAR.

## 12. Common Mistakes When Verifying a Starter

1. **Running tests inside the same Maven reactor and concluding the starter works independently.** The reactor can resolve sibling modules without installed or published artifacts.
2. **Consumer using the library's source directory.** Build succeeds yet fails to prove published JARs are complete.
3. **Missing `AutoConfiguration.imports`.** The class is in the JAR yet Boot does not discover it automatically.
4. **Wrong FQCN in imports.** Metadata exists yet points to a non-existent class.
5. **Starter forgets dependency on auto-config module.** Consumer gets core yet has no configuration to register beans.
6. **Auto-config forgets dependency on core module.** Consumer lacks public APIs or required runtime classes.
7. **Marking the core dependency optional.** Consumers may fail to compile when importing core APIs.
8. **Using `test` scope for runtime drivers or libraries.** Unit tests may pass while executable JARs miss dependencies.
9. **Using `@Import` to fix a missing bean.** This masks starter discovery failures.
10. **Component-scanning the library package.** Configuration appears from scanning rather than imports metadata.
11. **Incompatible versions between library and consumer.** Dependency management may resolve a Spring Boot version different from the compiled version.
12. **Checking only the dependency tree.** Dependency presence does not guarantee conditions match or bean creation succeeds.
13. **Checking only bean count.** You must call methods/verify behavior to confirm the right bean.
14. **Not testing the disabled property.** The starter may create beans despite the user requesting disablement.
15. **Not testing user overrides.** The default bean may collide with application configuration.
16. **Keeping the same release version after changing code.** Consumers may use stale cached artifacts.
17. **Running only inside an IDE.** The runtime classpath of an executable JAR or container may differ.
18. **Running `mvn package` without `install`.** An independent consumer cannot resolve artifacts from the local repository without a remote repository.
19. **Using `systemPath` dependencies.** Ties builds to personal machine paths and breaks reproducibility.
20. **Assuming local `install` proves remote `publish`.** Install only tests the local repository; remote deploy requires verifying repositories, credentials, and uploaded artifacts.

## 13. Standard Verification Workflow Before Release

1. Build all library modules with `mvn clean verify`.
2. Install artifacts into the local repository with `mvn clean install` or deploy to a staging repository.
3. Verify core, auto-config, and starter JARs were generated at the right versions.
4. Open the auto-config JAR and confirm the class and `AutoConfiguration.imports` exist.
5. Verify the imports contents list the exact FQCN.
6. Create/check out an independent consumer outside the reactor.
7. Declare only the starter by Maven coordinates, with no source references.
8. Run `mvn dependency:tree` to confirm core and auto-config are transitive dependencies.
9. Run `mvn clean test` in the consumer to verify default, disabled, and override cases.
10. Package the consumer and run the executable JAR to confirm real behavior.
11. Re-run with `--debug` whenever conditions behave unexpectedly.
12. Repeat in CI with an independent consumer checkout or staging repository before cutting a release.

## 14. Starter Acceptance Checklist

- [ ] Core module exposes public API and has no unnecessary integration dependencies.
- [ ] Auto-configuration module properly depends on core and Spring Boot.
- [ ] Starter declares a dependency on the auto-configuration module.
- [ ] Dependencies transitively required by the public API are not inadvertently marked optional.
- [ ] `AutoConfiguration.imports` sits at the exact path inside the JAR.
- [ ] FQCN in imports matches the actual class.
- [ ] Library was installed or published before building the consumer.
- [ ] Consumer lives outside the reactor and does not use library sources.
- [ ] Consumer declares only the starter by Maven coordinates.
- [ ] Dependency tree contains starter, auto-config, and core.
- [ ] Consumer does not use `@Import` or component scanning to load auto-configuration.
- [ ] Tests verify defaults, property disablement, and user overrides.
- [ ] Executable JAR runs and prints expected output.
- [ ] Spring Boot and Java versions are compatible.
- [ ] CI tests via an independent consumer or staging repository.
- [ ] Release versions are immutable; changes are published under new versions.

## 15. Self-Check Questions

**Question 1.** Why are tests inside the same Maven reactor insufficient to prove a starter works independently?  
**Answer:** The reactor can resolve sibling modules from build outputs without installed or published artifacts. An independent consumer must resolve via Maven coordinates.

**Question 2.** The auto-configuration class is inside the JAR yet the bean does not appear. What should you check first?  
**Answer:** Check `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, the resource path, and the FQCN written in the file.

**Question 3.** A consumer declares only the starter yet cannot see the core API at compile time. What could be the cause?  
**Answer:** The starter or auto-config failed to declare the core dependency properly, or the dependency was marked optional/given an unsuitable scope.

**Question 4.** Why should you not use `@Import(NoticeAutoConfiguration.class)` in consumer tests?  
**Answer:** It bypasses discovery from JAR metadata and can mask starter packaging bugs.

**Question 5.** How does `mvn install` differ from `mvn deploy`?  
**Answer:** `install` places artifacts into the local Maven repository; `deploy` uploads artifacts to a configured remote repository.

**Question 6.** The dependency tree includes the starter and auto-config yet the bean still is not created. What must you check?  
**Answer:** The Condition Evaluation Report, properties, classpath, prerequisite beans, `@ConditionalOnMissingBean`, and exceptions during bean creation.

**Question 7.** Why must you test property disablement and user overrides from the consumer?  
**Answer:** They confirm the public contract works inside a real application, not merely in the library's internal tests.

## 16. Official Documentation

- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
- [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).
- [Spring Boot Javadoc — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html).
- [Spring Boot Javadoc — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-lifecycle.html).
- [Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html).
- [Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html).
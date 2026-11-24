# Isolating Method Signatures and Implementation Code Depending on Optional Libraries

## 1. The Real Problem: An Optional Library Is Absent, Yet the JVM May Still Have to Read Method Signatures

When building **Spring Boot auto-configuration**, a library often wants to enable an integration only if an external dependency is present. For example, a starter may integrate with a notification-sending SDK, a data driver, or another system's client. Applications not using that integration **should not be forced to carry the optional SDK**, nor should they fail to start when the SDK is absent from the runtime classpath.

Spring Boot provides **@ConditionalOnClass** to select configurations based on class presence. However, there is a less obvious risk: **placing @ConditionalOnClass directly on an @Bean method whose return signature or parameters reference an absent class is not the safest isolation boundary**. Spring or the JVM may need to load/introspect the class containing those methods, reading method metadata, return types, parameters, or annotations before the method-level condition can protect the risky reference.

Risky example when the SDK does not exist:

~~~java
// Illustrates the RISK; do not include this class in the demo application.
@AutoConfiguration
class RiskyAutoConfiguration {

    @Bean
    @ConditionalOnClass(ExternalClient.class)
    ExternalClient externalClient() {
        return new ExternalClient("auto");
    }
}
~~~

This snippet assumes **ExternalClient** resides in an optional library. The issue is not that Java cannot compile: at **compile time**, the auto-config project may have the SDK dependency. The issue surfaces **at runtime**, when the SDK is absent from the classpath of an application using the starter. During introspection, accessing the method signature or linking classes can lead to **NoClassDefFoundError**, **TypeNotPresentException**, or related metadata reading errors. Depending on the mechanism/version/framework, the code might work by coincidence, yet you should not rely on that as a library contract.

**Recommended solution:** place all **@Bean methods whose signatures and implementations depend on the SDK** inside a **separate @Configuration class** (typically a **static nested configuration** class) and attach **@ConditionalOnClass** to **the configuration class enclosing the dependent code**, so Spring decides whether to import that configuration class **before needing to reflect on its dependent methods**.

Mental model to remember:

- The outer auto-configuration **candidate** should be processable when the optional library is absent.
- The **classpath condition** sits on the child configuration boundary.
- **@Bean signatures and new/call SDK logic** appear only inside the guarded child configuration.
- The **runtime dependency** can be absent, yet the application and other auto-configurations still start normally.

## 2. Distinguishing Compile-Time Dependencies from the Runtime Classpath

There are two distinct phases:

| Phase | Is the optional SDK required? | Why? |
| --- | --- | --- |
| Compiling the auto-configuration module | Yes, if source directly imports SDK types | The Java compiler must resolve types used in signatures/implementation code |
| Running an app not using the integration | Should not be required | The feature must back off automatically when SDK types are absent |
| Running an app using the integration | Yes | Beans require actual SDK types and implementation classes |
| Running unit tests checking negative classpath | Needs an environment genuinely excluding the SDK from runtime | Having the SDK on the test classpath will not test the absent case |
| Packaging a general-purpose starter | Optional dependencies should not pull into every app automatically | Split libraries or use dependency optionality suited to the build tool |

**Maven optional dependencies** take effect at dependency propagation: the auto-configuration module still has the dependency for **compilation**, yet a dependency marked **optional=true** does not automatically become a mandatory transitive dependency for consumers. Applications wanting to use the integration must declare the SDK directly or via a dedicated feature starter designed for it.

In Gradle, dependency configurations and variant publication differ from Maven. Do not mechanically translate **optional=true** into a Gradle configuration of the same name; inspect api/implementation/compileOnly/runtimeOnly and publishing metadata for the Gradle ecosystem.

### 2.1. Three Possibilities to Verify Independently

1. **Is the class present?** Can check class names on the classpath when building the context.
2. **Is the auto-configuration selected?** Also depends on imports metadata, exclusions, properties, and other conditions.
3. **Is the bean registered/initialized?** Subject to method conditions, user beans, dependencies, and lifecycle.

**@ConditionalOnClass** only answers part of question 1. It does not prove the SDK has endpoint/token configuration, that connections can succeed, or that the feature will always create a bean.

## 3. JVM Linkage: Why Is a Method Signature an Important Boundary?

Consider a class containing:

~~~java
import dev.demo.optionalapi.ExternalClient;

public class MixedConfiguration {
    public ExternalClient create(ExternalClient client) {
        return client;
    }
}
~~~

This is only a Java snippet; **ExternalClient** belongs to another artifact. The method descriptor in bytecode refers to the type **dev.demo.optionalapi.ExternalClient**. If that class is absent at runtime, whenever Java/Spring must link, reflect, or resolve parts of **MixedConfiguration**, errors can occur.

Do not oversimplify to “the JVM always loads every referenced class immediately when loading the main class”: **resolution timing varies by operation, implementation, and JVM**. Yet neither should you conclude “if create() is never called, any signature containing an absent type is safe”. Simply having the framework use reflection such as **getDeclaredMethods()**, read return/parameter types, or process metadata at an inopportune stage can still trigger errors before method logic executes.

Places prone to creating classpath dependencies:

- Direct **return type** of an @Bean method.
- **Parameter types** of an @Bean method, constructor, or certain factory methods.
- **Superclasses/interfaces** or fields of a loaded class.
- **Annotation attributes with Class literals** and annotations/metadata that the framework or reflection tries to resolve.
- **References to SDK classes in static initializers**, field initializers, or code invoked too early.
- **Generic signatures**, method exception types, or nested types that reflection tools may inspect.
- **Implementation code** using new, casts, or invoking SDK APIs when a branch executes.

Not all of the above produce the same error, and not every referenced type is resolved immediately. The design principle is: **do not let classes that must be processed when the SDK is absent carry signatures/initializers that depend on the SDK**.

## 4. Why Is Class-Level @ConditionalOnClass Safer Than Method-Level?

Spring Boot supports optimized annotation metadata reading, where class-level conditions like **@ConditionalOnClass** can be evaluated from the configuration class's metadata (via bytecode metadata reading) before Spring must load all SDK-dependent bean methods.

A pattern-following design:

~~~java
@AutoConfiguration
public class ExternalIntegrationAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "dev.demo.optionalapi.ExternalClient")
    static class ExternalClientConfiguration {

        @Bean
        ExternalClient externalClient() {
            return new ExternalClient("auto");
        }
    }
}
~~~

**This snippet is abbreviated**, omitting import statements and the ExternalClient definition. It illustrates the key boundary:

1. **ExternalIntegrationAutoConfiguration** does not let the outer class's own method signatures or fields directly reference the SDK.
2. The child configuration is a **static nested @Configuration**, carrying the class-level guard **@ConditionalOnClass**.
3. **externalClient()** returns the SDK type directly, yet sits inside a child configuration that should only be processed after the guard passes.
4. The **name** attribute can be used to check by fully qualified class name without needing a class literal on the guard annotation.

For **@ConditionalOnClass** attached directly to an @Configuration or auto-configuration class, using **value=ExternalClient.class** can also be safe in Spring Boot's metadata reading path. Using **name="..."** is especially convenient when avoiding class literal references on the guard annotation or when the dependency is genuinely optional at compile time. In this example, the nested class source still must compile with the SDK, so the module still declares a compile-time dependency.

**Do not conclude that switching value to name on an @Bean method is enough.** The issue in the risky example lies not only in the annotation value, but in the **method signature**. The boundary must be lifted onto a **separate configuration class**, so the framework can discard the entire class before introspecting dependent methods.

### 4.1. Why Use a static Nested @Configuration?

A **static** nested class needs no reference to an instance of the outer configuration. It is easily treated as a standalone configuration unit, holds @ConditionalOnClass right at the boundary, and avoids carrying enclosing-instance dependencies. Spring Boot frequently uses nested configurations to group beans needing extra classpath dependencies.

You can also use a separate **top-level @Configuration class** guarded by a condition and imported only when appropriate. What matters is not the nested keyword, but **separating classes Spring must read on the dependency-absent path** from classes containing dependency-reliant methods.

Do not place SDK initialization logic in a static initializer or constructor of the outer class and expect a guard on a child class to protect it. The outer class can still be loaded when the SDK is absent.

### 4.2. Conditions Do Not Yet Guarantee Bean Correctness

Even when ExternalClient is on the classpath, the bean can be skipped due to properties, a user-declared bean, configuration exclusion, or another unmet condition. If the bean is registered, the factory method can still fail due to misconfigured connections or incompatible SDK APIs.

**Classpath presence differs from dependency compatibility.** For example, the **ExternalClient** class exists at runtime, yet the SDK version lacks a method the integration calls; in that scenario, **@ConditionalOnClass** can pass while code still throws **NoSuchMethodError**, **NoSuchFieldError**, or other linkage errors. Dependency/version alignment and a test matrix are required, not just checking class names.

## 5. Recommended Pattern for Spring Boot Libraries

Suppose a library integrates with an optional **ExternalClient** API. A clean design:

~~~text
IntegrationAutoConfiguration
  - @AutoConfiguration
  - Contains no method signatures referencing ExternalClient
  |
  +-- ExternalClientBeans (static @Configuration)
         - @ConditionalOnClass(name = "...")
         - @ConditionalOnProperty(...)
         - @Bean ExternalClient externalClient()
         - @ConditionalOnMissingBean(ExternalClient.class)
~~~

Processing flow:

~~~text
Application enables @EnableAutoConfiguration
              |
              v
AutoConfiguration.imports lists outer configuration
              |
              v
ExternalIntegrationAutoConfiguration is evaluated
              |
              v
Nested ExternalClientBeans has classpath guard
         /                      \
SDK missing                  SDK present
   |                              |
Skip nested config        Check property & bean
   |                              |
DO NOT introspect bean     Read signatures & methods
methods depending on SDK      using the SDK
   |                              |
No SDK needed at runtime     Can register bean
~~~

The diagram abbreviates execution steps; what is essential is **guarding at the configuration class level before needing to process signatures depending on the SDK**.

### 5.1. Placing Conditions at the Right Boundaries

Distinguish:

- **@ConditionalOnClass**: wraps configuration classes containing optional code.
- **@ConditionalOnProperty**: enables/disables features via configuration.
- **@ConditionalOnMissingBean**: lets users supply a bean instead of the default.
- **@AutoConfiguration(before/after)**: configuration ordering if depending on other auto-configs; does not create optional dependencies.
- **exclude/excludeName** or **spring.autoconfigure.exclude**: excludes selected auto-configurations; does not automatically remove independent imports/registrations.

At the nested configuration level, you can combine class guards and property guards. However, **conditions are not runtime feature flags**: they decide bean definitions when the context is built, rather than watching for new SDKs/JARs appearing after startup.

## 6. Maven Reactor Demo: Actually Running With and Without the SDK on the Runtime Classpath

To practice “optional” in the true sense, the demo does not merely toggle a property; it **packages two applications with different runtime dependencies from the same source**:

- Default build: auto-configuration is present, yet **optional-api is not in the application**, because Maven marks the dependency optional in the auto-config module. The required result is **starting successfully without creating the integration bean**.
- Build enabling Maven profile **with-api**: the application declares **optional-api** directly, so the class is on the runtime classpath; the nested configuration satisfies the condition and creates the bean.
- When the class is present, **--demo.external.enabled=false** prevents the default bean from being registered.
- When the class is present, **spring.autoconfigure.exclude** can disable the entire ExternalIntegrationAutoConfiguration.

Examples use **JDK 21**, **Maven 3.9+**, and **Spring Boot 3.3.13**. No web server is needed and no real SDK connection is made. **ExternalClient** is a mock class placed in a separate optional artifact to test missing-class behavior safely and reproducibly.

### 6.1. Overall Project Structure

~~~text
optional-isolation/
├── pom.xml
├── optional-api/
│   ├── pom.xml
│   └── src/main/java/dev/demo/optionalapi/
│       └── ExternalClient.java
├── starter-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/dev/demo/autoconfig/
│       │   └── ExternalIntegrationAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── demo-app/
    ├── pom.xml
    └── src/main/
        ├── java/dev/demo/app/DemoApplication.java
        └── resources/application.properties
~~~

There are three Maven modules:

| Module | Role | Key dependencies |
| --- | --- | --- |
| **optional-api** | Defines the mock ExternalClient type | JDK only |
| **starter-autoconfigure** | Compiles auto-config and nested config using ExternalClient | spring-boot-autoconfigure, optional-api with optional=true |
| **demo-app** | Consumer using auto-configuration | spring-boot-starter, starter-autoconfigure; only has optional-api via profile |

To keep the lesson readable, the name **starter-autoconfigure** denotes an auto-configuration JAR; it does not pretend to have a separate starter dependencies module. In real published projects, you can split out an additional “starter” artifact depending on distribution requirements.

### 6.2. Parent pom.xml

**optional-isolation/pom.xml**

~~~xml
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
    <groupId>dev.demo</groupId>
    <artifactId>optional-isolation-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>optional-api</module>
        <module>starter-autoconfigure</module>
        <module>demo-app</module>
    </modules>

    <properties>
        <java.version>21</java.version>
    </properties>
</project>
~~~

### 6.3. Module optional-api

**optional-isolation/optional-api/pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.demo</groupId>
        <artifactId>optional-isolation-parent</artifactId>
        <version>1.0.0</version>
    </parent>
    <artifactId>optional-api</artifactId>
</project>
~~~

**optional-isolation/optional-api/src/main/java/dev/demo/optionalapi/ExternalClient.java**

~~~java
package dev.demo.optionalapi;

public final class ExternalClient {
    private final String source;

    public ExternalClient(String source) {
        this.source = source;
    }

    @Override
    public String toString() {
        return "client:" + source;
    }
}
~~~

ExternalClient is a mock optional type. Crucially, **demo-app does not import ExternalClient** in its source, so the application compiles and runs even when this JAR is excluded from runtime.

### 6.4. Module starter-autoconfigure Declaring the SDK as Optional

**optional-isolation/starter-autoconfigure/pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.demo</groupId>
        <artifactId>optional-isolation-parent</artifactId>
        <version>1.0.0</version>
    </parent>
    <artifactId>starter-autoconfigure</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>dev.demo</groupId>
            <artifactId>optional-api</artifactId>
            <version>1.0.0</version>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
~~~

The **optional=true** line is critical: the compiler still sees ExternalClient inside the autoconfigure module, yet Maven does not transitively pull **optional-api** into **demo-app** through the starter-autoconfigure dependency. This is how to build a runtime without the SDK without altering code.

### 6.5. Auto-Configuration Isolating SDK Signatures and Implementation

**optional-isolation/starter-autoconfigure/src/main/java/dev/demo/autoconfig/ExternalIntegrationAutoConfiguration.java**

~~~java
package dev.demo.autoconfig;

import dev.demo.optionalapi.ExternalClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class ExternalIntegrationAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "dev.demo.optionalapi.ExternalClient")
    @ConditionalOnProperty(
        prefix = "demo.external",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    static class ExternalClientBeans {

        @Bean
        @ConditionalOnMissingBean(ExternalClient.class)
        ExternalClient externalClient() {
            return new ExternalClient("auto");
        }
    }
}
~~~

This is the **complete Java file** for the autoconfigure module in the demo project.

Classpath safety analysis:

1. Outer class **ExternalIntegrationAutoConfiguration** is imported by Boot via the imports file. It **has no @Bean methods, fields, or superclasses depending on ExternalClient**; this class can be processed even when optional-api is absent at runtime.
2. Nested class **ExternalClientBeans** is discovered by Spring as a nested configuration. **@ConditionalOnClass(name = "...")** is attached at the nested configuration level.
3. Spring uses condition metadata to **skip the nested configuration when ExternalClient is absent**; thus it does not have to introspect the @Bean method carrying the ExternalClient signature on the SDK-absent path.
4. When ExternalClient exists, Spring can process **externalClient()**; **@ConditionalOnMissingBean(ExternalClient.class)** lets the default bean back off for an application-declared bean of the same type.
5. **@ConditionalOnProperty** illustrates another condition: the class is present, yet if the property is disabled the bean still goes unregistered.
6. Do not place **new ExternalClient(...)** in a static initializer or constructor of the outer class. Logic using the SDK sits inside the guarded configuration.

**Why is the Java import of ExternalClient still at the top of the source file?** A Java import statement is compile-time syntax, not a runtime call that automatically loads a class when reading source. The outer class's bytecode needs no method signature returning that type. ExternalClient is used inside the separate nested class, and the nested class has a metadata guard. What matters is not the placement of the import line in source, but **class loading paths and the scope of references in bytecode**.

### 6.6. Registering the Outer Class in AutoConfiguration.imports

**optional-isolation/starter-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.demo.autoconfig.ExternalIntegrationAutoConfiguration
~~~

List only **ExternalIntegrationAutoConfiguration**. Do not list the nested class as an independent auto-configuration candidate. Boot 3.x reads this file when **@EnableAutoConfiguration** is activated by the application.

Boot's auto-configuration selection mechanism differs from component scanning. In the demo, the autoconfig class's package sits outside the main class's scan scope and is loaded via the imports file.

### 6.7. Module demo-app with a Maven Profile Adding the SDK

**optional-isolation/demo-app/pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.demo</groupId>
        <artifactId>optional-isolation-parent</artifactId>
        <version>1.0.0</version>
    </parent>
    <artifactId>demo-app</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>dev.demo</groupId>
            <artifactId>starter-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>

    <profiles>
        <profile>
            <id>with-api</id>
            <dependencies>
                <dependency>
                    <groupId>dev.demo</groupId>
                    <artifactId>optional-api</artifactId>
                    <version>1.0.0</version>
                </dependency>
            </dependencies>
        </profile>
    </profiles>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Without the **with-api** profile, demo-app only depends directly on starter-autoconfigure; the SDK was marked optional in that module so it does not become a transitive runtime dependency. Enabling **-Pwith-api** makes demo-app declare the SDK directly, so the class is present and the condition can match.

### 6.8. Application That Does Not Import the SDK in Signatures

**optional-isolation/demo-app/src/main/java/dev/demo/app/DemoApplication.java**

~~~java
package dev.demo.app;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showSelection(ApplicationContext context) {
        return args -> {
            boolean classPresent = ClassUtils.isPresent(
                "dev.demo.optionalapi.ExternalClient",
                DemoApplication.class.getClassLoader());
            boolean beanPresent = context.containsBean("externalClient");

            System.out.println("api.present=" + classPresent);
            System.out.println("client.present=" + beanPresent);
            System.out.println("client.value=" +
                (beanPresent
                    ? context.getBean("externalClient").toString()
                    : "none"));
        };
    }
}
~~~

The application class intentionally **does not directly reference ExternalClient** in return types, parameters, or variable declarations. It checks class presence by string name via **ClassUtils.isPresent** and only retrieves the bean by name if registered. Thus a consumer not needing the SDK runs safely.

**optional-isolation/demo-app/src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
~~~

These properties simply keep output concise. When diagnostics are needed, re-enable logs in the debug section.

### 6.9. Building and Running Without the Optional SDK

Open a terminal at the root directory **optional-isolation**. Requires JDK 21, Maven 3.9+, and dependencies reachable from Maven repositories:

~~~bash
mvn -q -pl demo-app -am -DskipTests package
java -jar demo-app/target/demo-app-1.0.0.jar
~~~

Lines printed by ApplicationRunner:

~~~text
api.present=false
client.present=false
client.value=none
~~~

Reason:

- Module starter-autoconfigure was compiled with ExternalClient, yet the optional dependency does not propagate transitively into the app.
- Nested **ExternalClientBeans** is skipped because class-level @ConditionalOnClass does not match.
- No error occurs from reflecting on the **ExternalClient externalClient()** method in the excluded branch.
- The app still builds a normal ApplicationContext without the **externalClient** bean.

**This is the most important check of the lesson:** not just a false property, but **the SDK class truly absent at runtime**.

### 6.10. Building and Running With the SDK

From root, rebuild with the **with-api** profile:

~~~bash
mvn -q -Pwith-api -pl demo-app -am -DskipTests package
java -jar demo-app/target/demo-app-1.0.0.jar
~~~

Expected stdout lines:

~~~text
api.present=true
client.present=true
client.value=client:auto
~~~

Now optional-api is directly declared by demo-app, the nested configuration matches @ConditionalOnClass, and the default property allows it. The @Bean method registers ExternalClient; toString returns **client:auto**.

### 6.11. SDK Present, Yet Feature Disabled via Property

After building with **-Pwith-api**, run:

~~~bash
java -jar demo-app/target/demo-app-1.0.0.jar --demo.external.enabled=false
~~~

Output:

~~~text
api.present=true
client.present=false
client.value=none
~~~

**@ConditionalOnClass still matches** because the class is present, yet **@ConditionalOnProperty** on the nested configuration does not match. The feature is not created even though the SDK is on the classpath.

### 6.12. SDK Present, Yet Auto-Configuration Excluded

Still using the JAR with the SDK:

~~~bash
java -jar demo-app/target/demo-app-1.0.0.jar --spring.autoconfigure.exclude=dev.demo.autoconfig.ExternalIntegrationAutoConfiguration
~~~

Output:

~~~text
api.present=true
client.present=false
client.value=none
~~~

Unlike disabling a property, this excludes **ExternalIntegrationAutoConfiguration** from Boot's auto-config selection path. The SDK remains in the JAR; having the class does not force having the bean.

### 6.13. Practical Results Table

| Runtime SDK | Feature property | Auto-config excluded? | Class present | externalClient bean |
| --- | --- | --- | --- | --- |
| Absent | Default | No | false | false |
| Present | Default | No | true | true |
| Present | false | No | true | false |
| Present | Default | Yes | true | false |

How to tell whether a JAR includes the SDK: for a Spring Boot executable JAR, this command lists entries:

~~~bash
jar tf demo-app/target/demo-app-1.0.0.jar
~~~

In the profiled build, the list normally contains **BOOT-INF/lib/optional-api-1.0.0.jar**. In the default build, this entry should be absent. Do not merely trust a Maven log saying build succeeded; inspect actual runtime dependencies when debugging a starter with classpath options.

**Testing limitation:** the results above are expected stdout inferred from source and configuration; this does not claim Maven was run in the reader's environment. A real project must run both builds and integration tests across target environments.

## 7. Why Not Just Put @ConditionalOnClass on the @Bean Method?

Returning to the risky design:

~~~java
@AutoConfiguration
class RiskyAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "dev.demo.optionalapi.ExternalClient")
    ExternalClient externalClient() {
        return new ExternalClient("auto");
    }
}
~~~

**Snippet illustrating what to avoid** and lacking complete imports/definitions. We changed the class literal in the annotation to a string name, yet **the return signature is still ExternalClient**. When Spring/the JVM must introspect RiskyAutoConfiguration before the method condition is evaluated, the absent type can cause a linkage error. Changing to **name** does not resolve the method signature boundary by itself.

Comparison:

| Design | SDK absent | Evaluation |
| --- | --- | --- |
| @ConditionalOnClass on method returning SDK type in an always-processed class | Risk of method introspection hitting absent type | Should not rely on luck that it works |
| Class-level guard on the auto-configuration itself when the whole class is only for the SDK | Can be safe when metadata is evaluated before class loading | Suitable if the entire auto-config only makes sense when the SDK is present |
| Class-level guard on a static nested configuration holding all SDK methods | Outer class can be processed; nested class is skipped when SDK is absent | Flexible, clean pattern when auto-config also has other beans |
| Separate top-level @Configuration holding SDK, guarded before import | Can be safe if import/condition boundaries are right | Suitable for complex configurations |
| Changing return type to Object while still calling new SDK in outer static initializer | Still risks linkage/side effects | Fails to isolate implementation code properly |
| Wrapping everything in catch(NoClassDefFoundError) | Easily hides version errors and leaves context state confusing | Not a recommended primary design |

**Class-level @ConditionalOnClass can be placed directly on a dedicated auto-configuration** if the entire class implements only that integration and metadata is safely processed by Boot. Nested configurations are especially useful when the outer class must still run with the SDK absent, or when keeping optional feature branches independent.

## 8. Safety Boundaries Include Signatures, Fields, and Initialization Behavior

Fixing only the return type is not enough. When determining which classes must load when the SDK is absent, inspect:

1. **Superclasses/interfaces** of the class: extending an optional SDK interface in an always-loaded class can be dangerous.
2. **Constructor signatures** and method parameter types: Spring may inspect them for autowiring.
3. **Field types** and annotation attributes: some reflection mechanisms may resolve types.
4. **@Bean return types** and factory methods: especially sensitive while Spring determines bean types.
5. **Static fields/initializers**: code creating SDK objects during class initialization can fail before guards apply.
6. **Code calling SDK inside bean factories**: should execute only when the conditional branch is truly selected; keep it inside guarded classes.
7. **Composed annotations**: if writing a custom annotation meta-annotated with @ConditionalOnClass using a **Class literal**, ensure alias/metadata handling fits. For composed annotations, using **name** is generally recommended to avoid issues reading class-valued annotation attributes directly.
8. **Method references/lambdas containing SDK types**: lambdas themselves do not erase bytecode dependencies. If the SDK is resolved before the guard, the risk remains.

The goal is to eliminate **mandatory links to optional classes** from classes the framework must load/reflect on the SDK-absent path.

### 8.1. Do Not Use Linkage Errors as a Classpath Detection Mechanism

An anti-pattern:

~~~java
try {
    // Try instantiating or calling SDK and wait for NoClassDefFoundError.
} catch (NoClassDefFoundError ex) {
    // Assume every error means the SDK is not installed.
}
~~~

This is illustrative pseudocode, not a standalone Java file. **NoClassDefFoundError** can also stem from a **missing transitive dependency**, binary compatibility errors, or failed class initialization. Swallowing the error can hide the real problem and turn a broken integration into a silent fallback state.

Using **@ConditionalOnClass** to select branches, managing dependency versions, and testing classpaths is the primary approach. In runtime code, if genuine optional discovery is needed, only use purposefully designed reflection/APIs with explicit error handling.

### 8.2. @ConditionalOnClass Does Not Prove ABI Compatibility

An SDK class may be present yet have a method changed between versions 1 and 2. The classpath condition can pass because the **ExternalClient name** still matches. When code invokes an incompatible version's method, **NoSuchMethodError**, **IncompatibleClassChangeError**, or similar errors can occur.

Mitigations:

- Pin and verify SDK versions supported by the library.
- Use appropriate dependency management/BOMs.
- Run integration tests on the runtime classpath of each target version.
- If multiple API versions must be supported, split conditional branches and implementation code per version rather than letting one class load both APIs.

## 9. Adding Other Conditions While Preserving Classpath Isolation

A feature may require three condition layers:

~~~java
@AutoConfiguration
public class MessagingAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.messaging.Client")
    @ConditionalOnProperty(
        prefix = "app.messaging",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    static class VendorClientConfiguration {
        // @Bean returning com.vendor.messaging.Client.
        // @ConditionalOnMissingBean if supporting custom clients.
    }
}
~~~

This illustrates structure; the vendor Client does not exist in the demo project. Configuration is evaluated in logical order:

1. Is the required SDK class present?
2. Does the property enable the feature?
3. Has the application already supplied a matching bean?
4. If the bean must be created, is the factory method given full properties/credentials/dependencies?

Do not check the classpath with **@ConditionalOnClass** and neglect feature boundaries; a network-connecting bean also needs URLs, credentials, timeouts, and sound fail-fast/fallback behavior.

## 10. Debugging an Error That Only Occurs When Removing an Optional Dependency

### 10.1. Recognizing the Stack Trace

An error such as:

~~~text
java.lang.NoClassDefFoundError: dev/demo/optionalapi/ExternalClient
~~~

can indicate that a required class was resolved when missing from the classpath. Yet to know why, inspect the full stack trace: did the error appear while Spring introspected an @Bean method, during bean creation, or in code calling the SDK?

If the stack trace shows **getDeclaredMethods**, **ReflectionUtils.getDeclaredMethods**, or configuration parsing, inspect method signatures in auto-configurations Spring must read. If the error occurs inside a factory method after the condition matched, inspect the SDK and its transitive dependencies.

### 10.2. Step-by-Step Diagnosis

1. **Identify the missing class** from the error and find the artifact providing it.
2. **Inspect the final JAR**: is the artifact actually in BOOT-INF/lib or the runtime classpath? Do not only look at the auto-config module's compile classpath.
3. **Inspect the outer configuration**: are there @Bean return types, constructor parameters, fields, or static initializers referencing the SDK?
4. **Place a class-level guard** on the configuration containing all SDK-dependent signatures; static nested configurations work well.
5. **Verify AutoConfiguration.imports** publishes only the right outer class, avoiding component-scanning the whole auto-config package.
6. **Check Maven optional/Gradle publishing semantics**: which dependencies propagate to consumers?
7. **Check combined conditions**: @ConditionalOnProperty, @ConditionalOnMissingBean, and exclusions.
8. **Run negative classpath tests**: ensure that at runtime **without** the SDK, the app still starts.
9. **Run positive classpath tests**: with the SDK, the bean is created and APIs are compatible.
10. **Run disabled tests**: SDK present yet feature disabled; bean does not appear.

### 10.3. Where Does the Condition Evaluation Report Help?

With either the SDK-present or SDK-absent JAR, you can run:

~~~bash
java -jar demo-app/target/demo-app-1.0.0.jar --debug --logging.level.root=INFO
~~~

Look for **ExternalIntegrationAutoConfiguration** and nested class **ExternalClientBeans**. The condition report shows why classpath/property conditions matched or did not match. A candidate skipped due to a missing SDK is **normal behavior**, not a bug.

**The Condition Evaluation Report does not prove all class linkage is safe**: if the app already crashed with NoClassDefFoundError during introspection, the stack trace is the primary evidence. If the SDK is present yet the ABI is wrong, a positive classpath match also does not guarantee the factory method creates the bean successfully.

### 10.4. Testing with Lightweight Contexts and Controlled ClassLoaders

Spring Boot provides **ApplicationContextRunner** and **FilteredClassLoader** in its test utilities for writing auto-configuration tests:

- Positive tests use a runtime classpath with the SDK and assert the bean is created.
- Negative tests use FilteredClassLoader (or an artifact genuinely missing the dependency), ensuring auto-config can build the context without touching SDK classes.
- Test false properties and pre-existing user beans.
- Test target SDK versions.

Conceptual example, not a standalone JUnit file:

~~~java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(
            ExternalIntegrationAutoConfiguration.class))
    .withClassLoader(
        new FilteredClassLoader("dev.demo.optionalapi"))
    .run(context ->
        assertThat(context).doesNotHaveBean("externalClient"));
~~~

Running this test example requires **spring-boot-starter-test** in test scope, imports, and full JUnit/test assertions. In some setups, tests with filtered classloaders must pay special attention to already-loaded data or other classloaders. The **Maven reactor demo in section 6** is the definitive proof that **the optional artifact is genuinely omitted from packaging into the application**.

## 11. Misconceptions to Avoid

| Misconception | Reality |
| --- | --- |
| “Once @ConditionalOnClass is on the @Bean method, any signature using an absent SDK is safe.” | The method signature can be loaded/introspected before the method condition protects it; isolate with a class-level guard. |
| “Using name instead of value on the method eliminates the error.” | name avoids a class literal in the annotation, yet does not remove the SDK type from return/parameter types. |
| “If it compiles, it runs when the dependency is removed.” | Compile classpath differs from runtime classpath; missing SDKs can lead to linkage errors. |
| “Maven optional=true hides the SDK from the module itself during compile.” | The module declaring the dependency still sees the SDK at compile time; optional mainly controls transitive propagation. |
| “Class present means the bean will be created.” | Imports metadata, exclusions, properties, back-off, bean lifecycle, and dependency compatibility still apply. |
| “When the class is missing, @ConditionalOnClass automatically wraps any new SDK outside.” | Guards must enclose the necessary classes, signatures, and code. |
| “Static nested configurations are what Boot reads from AutoConfiguration.imports.” | The imports file publishes the outer auto-config; nested configurations are processed via its config/condition structure. |
| “If a method isn't called, a signature with a missing type is guaranteed harmless.” | Reflection and JVM type resolution can touch signatures before the method is invoked. |
| “Just catching NoClassDefFoundError counts as optional dependency support.” | Can hide wrong SDK versions or missing transitive dependencies. |
| “@ConditionalOnClass also verifies SDK methods match the right version.” | It checks class presence; version alignment and integration tests are needed for ABI. |
| “Setting a property to false can replace missing-classpath tests.” | Disabling a property does not prove the app is safe when the SDK JAR is removed from runtime. |
| “Just use @ComponentScan to find all auto-config classes.” | Boot 3.x uses AutoConfiguration.imports and dedicated conditions/ordering/exclusions. |

## 12. Self-Check Exercises

**Question 1.** An @Bean method returns type **VendorClient**, with @ConditionalOnClass(VendorClient.class) on the method itself. If the vendor JAR is absent, should you treat this as an absolute safety boundary?

**Answer:** No. Reflection may resolve the method return type before the method condition is evaluated. Place the method inside a separate @Configuration with a class-level guard.

**Question 2.** Why is placing @ConditionalOnClass(name="...") on a static nested @Configuration useful?

**Answer:** Spring can read the guard metadata to skip the nested class when the SDK is absent, before needing to introspect methods referencing the SDK inside. Using name requires no class literal on the guard annotation.

**Question 3.** The autoconfigure Maven module uses optional-api with optional=true. Can it compile a method returning ExternalClient?

**Answer:** Yes. The autoconfigure module still receives the dependency at compile time. optional=true prevents the dependency from propagating transitively into an app module that only depends on autoconfigure.

**Question 4.** Why didn't demo-app need to import ExternalClient?

**Answer:** The app only checks the class by string name and the bean by name. It has no SDK-dependent signatures or compile-time code, so the default build runs when the SDK is absent from the runtime classpath.

**Question 5.** SDK is present, yet --demo.external.enabled=false; does the externalClient bean appear?

**Answer:** Not via this auto-config. The class condition passes, yet the property condition on the nested configuration fails.

**Question 6.** SDK and property true are present, yet an older SDK version lacks a method auto-config calls; does @ConditionalOnClass guarantee safety?

**Answer:** No. It does not perform full binary compatibility checks. Dependency management and testing against real versions are needed.

**Question 7.** If only one isolated integration is needed with no other configuration in the outer class, can class-level @ConditionalOnClass be placed on the entire auto-config?

**Answer:** Yes. Spring Boot's class-level guard can be evaluated from metadata before the class is loaded; nested config remains more flexible when the outer class also has SDK-independent branches.

**Question 8.** Why isn't running tests with property=false enough to prove optional dependencies work properly?

**Answer:** Because the SDK can still be present on the classpath and mask signature linkage errors. You must test at least once with a runtime genuinely lacking the SDK.

## 13. Checklist for Developing an Auto-Configuration Using an Optional SDK

Before publishing a library:

1. **Confirm outer auto-config can be processed when the SDK is absent.** Keep the outer class free of mandatory SDK loads in superclasses, method signatures, or static initializers.
2. **Create an isolated @Configuration class**, typically a static nested config, for @Bean methods returning/referencing SDK types.
3. **Place @ConditionalOnClass at the isolated configuration level**, with an appropriate Class literal or name; prefer name in composed annotations and optional scenarios.
4. **Combine properties and @ConditionalOnMissingBean** if the feature needs toggling or user overrides.
5. **Publish the exact auto-config candidate** using Spring Boot 3.x's AutoConfiguration.imports resource.
6. **Declare dependencies for compilation without forcing consumers to carry the SDK unnecessarily**; with Maven verify optional/transitive dependencies and the runtime fat JAR.
7. **Test a genuinely SDK-absent runtime**, not merely property toggles or a test classpath that still contains the SDK.
8. **Test an SDK-present runtime** and verify bean creation, output, and method compatibility.
9. **Test a version matrix** to catch NoSuchMethodError, ClassNotFoundException/NoClassDefFoundError, or transitive dependency failures.
10. **Read stack traces on linkage errors**, distinguishing errors during configuration introspection, bean creation, and SDK usage.
11. **Do not swallow linkage errors as an ordinary fallback**; keep diagnostics clear when binary dependencies are wrong.
12. **Keep consumers free of optional types when the feature may be absent**; use shared abstractions or place optional consumer code in similarly guarded modules.

### Conclusion

**Isolating method signatures and implementation code that use optional libraries is a key design requirement in Spring Boot auto-configuration.** You need more than a classpath-checking annotation; you must organize classes so Spring/the JVM **are not forced to resolve absent SDK types before a configuration-level condition has a chance to skip that branch**.

The practical pattern is **an outer auto-configuration independent of the SDK + a child @Configuration with @ConditionalOnClass + @Bean methods using SDK types placed solely inside the guarded configuration**. Paired with true optional dependencies, testing with and without the JAR, and API version management, your library will operate reliably in applications that do not opt into that integration.

### References

- Spring Boot, *Creating Your Own Auto-configuration*, Class Conditions section: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot API, **@ConditionalOnClass**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Framework, *Conditionally Including @Configuration Classes*: https://docs.spring.io/spring-framework/reference/core/beans/java/conditional.html
- Maven, *Optional Dependencies and Dependency Exclusions*: https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html

# Loading XML Configuration and Classpath Resources

Spring Framework can create and configure an ApplicationContext from various sources. Alongside Java configuration and annotations, Spring still supports XML bean definitions to declare beans, dependencies, component scans, property placeholders, and infrastructure configurations. These XML files are typically placed on the classpath so that applications and tests can load them according to the same rules, whether running from an IDE, Gradle, or a packaged JAR.

To load XML configuration properly, you need to understand three related parts:

1. **ApplicationContext** manages beans and provides resource loading mechanisms.
2. **XML bean definitions** describe beans, dependencies, and Spring configurations.
3. **The Resource abstraction** allows referencing resources via classpath, filesystem, URL, or ServletContext.

In Spring testing, these concepts typically appear when a test needs to initialize a context from an XML file, load fixtures in src/test/resources, or test legacy XML configuration being integrated with Java configuration.

## 1. ApplicationContext and Resource Loading

ApplicationContext is Spring's high-level container. Beyond creating and managing beans, it provides services such as reading messages, publishing application events, and accessing resources. ApplicationContext can act as a ResourceLoader, so code can ask the container to locate a Resource using a location string.

Example:

~~~java
Resource resource = applicationContext.getResource(
    "classpath:/config/application-context.xml"
);
~~~

Resource is an abstraction representing a data source. It can be a file on the classpath, a filesystem file, a URL, or a resource in a web application. Code can open an InputStream to read the contents without needing to know where that source is stored.

Key related APIs:

| API | Role |
|---|---|
| ApplicationContext | Manages beans and provides container services |
| ResourceLoader | Resolves a location string into a Resource |
| Resource | Represents a readable resource |
| ResourcePatternResolver | Finds one or more resources matching a pattern |
| XmlBeanDefinitionReader | Reads XML and registers bean definitions into a registry |

Spring uses these abstractions to decouple bean declarations from how files are stored. An XML file can be loaded from the classpath in a packaged application or from the filesystem in a specific deployment environment.

## 2. Placing XML Configuration on the Classpath

In a typical Java project, application resources usually reside in src/main/resources. The build tool places those files onto the runtime classpath. Resources used only for tests usually reside in src/test/resources and are placed onto the test runtime classpath.

Example structure:

~~~text
src/
├── main/
│   └── resources/
│       └── com/example/config/
│           ├── application-context.xml
│           ├── data-access.xml
│           └── application.properties
└── test/
    └── resources/
        └── fixtures/
            ├── expected-product.json
            └── sample-catalog.xml
~~~

When a file is located at src/main/resources/com/example/config/application-context.xml, its location on the classpath is typically:

~~~text
com/example/config/application-context.xml
~~~

You can use the classpath: prefix to make the source explicit:

~~~text
classpath:/com/example/config/application-context.xml
~~~

Classpath paths use forward slashes as separators. Do not construct paths using OS-specific separators like backslashes, because resources may be read from inside a JAR and have no corresponding filesystem path.

Avoid using absolute paths on a developer machine such as C:/work/project/src/main/resources/... to load application configuration. Those paths do not exist in containers, CI, or teammates' machines. Placing resources on the classpath ensures the build artifact carries the configuration file and the application can find it at runtime.

## 3. Common Resource Prefixes

ResourceLoader understands several prefixes to determine the resource type:

| Prefix | Meaning | Example |
|---|---|---|
| classpath: | Locates a single resource on the classpath | classpath:/config/app.xml |
| classpath*: | Locates matching resources across the entire classpath | classpath*:META-INF/spring/*.xml |
| file: | Resource on the filesystem | file:/etc/myapp/app.xml |
| https: or other URL schemes | Resource from a URL | https://example.test/config.xml |

### 3.1. classpath:

classpath: points to a single resource on the classpath. Example:

~~~java
Resource resource = new ClassPathResource(
    "com/example/config/application-context.xml"
);
~~~

Or:

~~~java
Resource resource = applicationContext.getResource(
    "classpath:/com/example/config/application-context.xml"
);
~~~

ClassPathResource is typically created with a path relative to the classpath root. Leading slashes in paths may be normalized, but using a consistent convention helps avoid confusion.

### 3.2. classpath*:

classpath*: is used when you need to find all matching resources on the classpath, across different locations such as classes directories and JAR dependencies. It is commonly paired with ResourcePatternResolver:

~~~java
ResourcePatternResolver resolver =
    new PathMatchingResourcePatternResolver();

Resource[] resources = resolver.getResources(
    "classpath*:META-INF/spring/*.xml"
);
~~~

Patterns can contain wildcards such as * or **. The example above finds XML files directly inside the META-INF/spring directory across matching classpath locations.

classpath*: is useful when multiple modules or libraries contribute configuration files under a shared convention. However, the order in which resources are found should not be relied upon as an implicit configuration precedence mechanism. If load order matters, specify the list of locations or import order explicitly.

### 3.3. file:

file: references a filesystem path:

~~~java
Resource resource = new FileSystemResource(
    "/etc/myapp/application-context.xml"
);
~~~

Or using a location string:

~~~java
Resource resource = applicationContext.getResource(
    "file:/etc/myapp/application-context.xml"
);
~~~

File resources are suitable for deployment configurations managed outside the artifact. Ensure the file exists, has read permissions, and that the path is supplied via environment configuration. Avoid forcing unit tests to run against a hardcoded system path.

### 3.4. URL Resource

ResourceLoader can create a resource from a URL:

~~~java
Resource remoteConfig = applicationContext.getResource(
    "https://config.example.test/application-context.xml"
);
~~~

Remote resources can be affected by network conditions, authentication, timeouts, and server availability. Routine tests should not fetch configuration from a public URL. If you need to test URL integration, use a controllable test server or local fixtures.

### 3.5. Locations Without a Prefix

When a location has no prefix, its interpretation depends on the ResourceLoader or ApplicationContext implementation. For example, ClassPathXmlApplicationContext searches for XML configuration on the classpath by default; FileSystemXmlApplicationContext interprets locations relative to the filesystem. Therefore, when code may be used with different context types, use explicit prefixes like classpath: or file: to avoid relying on defaults.

## 4. Loading XML with ClassPathXmlApplicationContext

ClassPathXmlApplicationContext is a direct way to create an ApplicationContext from XML on the classpath. Its constructor accepts one or more locations. The context reads bean definitions and completes the refresh process during normal construction.

Example:

~~~java
ApplicationContext context =
    new ClassPathXmlApplicationContext(
        "classpath:/com/example/config/application-context.xml"
    );

ProductService productService =
    context.getBean("productService", ProductService.class);
~~~

You can pass multiple XML files:

~~~java
ApplicationContext context =
    new ClassPathXmlApplicationContext(
        "classpath:/com/example/config/data-access.xml",
        "classpath:/com/example/config/services.xml"
    );
~~~

Beans declared in these files are registered into the same context. If multiple files define the same bean name, the result depends on the bean definition overriding policy and container configuration. Avoid relying on one file accidentally overriding another; name beans clearly and manage load order intentionally.

For a context that needs to be closed when finished, keep a reference to ConfigurableApplicationContext or AbstractApplicationContext to call close:

~~~java
try (ClassPathXmlApplicationContext context =
         new ClassPathXmlApplicationContext(
             "classpath:/com/example/config/application-context.xml"
         )) {

    ProductService service =
        context.getBean("productService", ProductService.class);
}
~~~

Closing the context triggers Spring's bean destruction callbacks and releases resources managed by beans. In web applications or Spring Boot applications, the framework usually manages the context lifecycle; in standalone examples or tests that create a context manually, ensure the context is closed.

## 5. Loading XML with FileSystemXmlApplicationContext

FileSystemXmlApplicationContext loads configuration from the filesystem:

~~~java
ApplicationContext context =
    new FileSystemXmlApplicationContext(
        "file:/etc/myapp/application-context.xml"
    );
~~~

In deployment environments, this is useful when XML is managed outside the application and can be changed without repackaging the artifact. Relative paths in FileSystemXmlApplicationContext are interpreted according to the context's filesystem rules and the working directory. To avoid working-directory-dependent results, prefer absolute paths or pass an explicitly configured file location.

Do not use FileSystemXmlApplicationContext just because an XML file sits in the project's src/main/resources directory. Once packaged into a JAR, it is no longer a regular file that can be opened via a filesystem path. For packaged resources, use the classpath.

## 6. Reading XML with XmlBeanDefinitionReader

When you need control over bean definition registration, you can combine GenericApplicationContext and XmlBeanDefinitionReader. This separates XML reading from context refreshing:

~~~java
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.beans.factory.xml.XmlBeanDefinitionReader;
import org.springframework.core.io.ClassPathResource;

try (GenericApplicationContext context = new GenericApplicationContext()) {
    XmlBeanDefinitionReader reader =
        new XmlBeanDefinitionReader(context);

    reader.loadBeanDefinitions(
        new ClassPathResource(
            "com/example/config/application-context.xml"
        )
    );

    context.refresh();

    ProductService service =
        context.getBean("productService", ProductService.class);
}
~~~

The workflow has three steps:

1. Create the context and bean definition registry.
2. Use XmlBeanDefinitionReader to read the XML, parse bean definitions, and register them into the registry.
3. Call refresh so the context instantiates eager beans, applies post-processors, and becomes ready to serve lookups.

Do not call refresh before registering the XML, because bean definitions loaded after refresh will not automatically participate fully in the already-completed initialization process. If you need to load additional configuration, follow the lifecycle and API of the respective context, or create a new context with the complete configuration set.

XmlBeanDefinitionReader can also load from another Resource:

~~~java
reader.loadBeanDefinitions(
    new FileSystemResource("/etc/myapp/application-context.xml")
);
~~~

The important point is that the reader accepts a Resource; it does not require the content to come from the classpath. This is suitable when an application needs to choose the XML source based on the environment.

## 7. Structure of a Spring XML File

A bean definition file uses Spring's beans namespace. Example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="com.example.service"/>

    <bean id="systemClock" class="java.time.Clock" factory-method="systemUTC"/>

    <bean id="productRepository"
          class="com.example.repository.InMemoryProductRepository"/>

    <bean id="productService"
          class="com.example.service.ProductService">
        <constructor-arg ref="productRepository"/>
        <constructor-arg ref="systemClock"/>
    </bean>
</beans>
~~~

In the example:

- component-scan tells Spring to search for components in the specified package.
- systemClock is created using the static factory method systemUTC.
- productRepository is declared as a bean.
- productService receives two dependencies via constructor injection.

XML bean definitions support constructor arguments, property injection, factory methods, scopes, lifecycle methods, aliases, and many other container configurations. For new applications, Java configuration is usually easier to refactor and better supported by IDEs; XML remains useful when integrating legacy systems, managing configuration externally, or separating configuration from Java code.

### 7.1. Constructor Injection

Dependencies can be declared using ref:

~~~xml
<bean id="notificationService"
      class="com.example.notification.NotificationService">
    <constructor-arg ref="mailGateway"/>
    <constructor-arg value="support@example.test"/>
</bean>
~~~

ref points to another bean in the container; value is a literal value or placeholder expression. Constructor injection keeps dependencies explicit and convenient for testing because objects can be instantiated directly with mock dependencies.

### 7.2. Property Injection

If a bean has matching setters or properties, XML can use property:

~~~xml
<bean id="reportOptions"
      class="com.example.report.ReportOptions">
    <property name="format" value="csv"/>
    <property name="includeHeader" value="true"/>
</bean>
~~~

Do not use property injection merely to avoid a long constructor. Required dependencies should usually be expressed via constructors; properties are better suited for optional settings or JavaBeans that need configuration after creation.

### 7.3. Splitting XML with import

When configuration grows large, it can be split into multiple files:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <import resource="classpath:/com/example/config/data-access.xml"/>
    <import resource="classpath:/com/example/config/services.xml"/>
</beans>
~~~

The import element lets you aggregate configuration groups into a single entry point. Relative paths can be used to reference files in the same location as the current XML; explicit classpath paths help readers recognize the resource origin and prevent confusion when files are moved.

Split files by responsibility, such as data access, integration, services, and web. Avoid creating too many tiny files containing just a single bean if splitting makes configuration relationships hard to follow.

## 8. Loading Property Files from the Classpath in XML

XML can use the context namespace to load properties and substitute placeholders in bean definitions:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:property-placeholder
        location="classpath:/com/example/config/application.properties"/>

    <bean id="reportOptions" class="com.example.report.ReportOptions">
        <property name="currency" value="${report.currency:VND}"/>
        <property name="maximumRows" value="${report.maximum-rows:500}"/>
    </bean>
</beans>
~~~

In a placeholder, the part after the colon is the default value if the property is not found. If a property is required, omit the default so missing configuration is caught during context initialization.

The properties file can reside on the classpath:

~~~properties
report.currency=VND
report.maximum-rows=1000
~~~

Do not place real passwords or secrets in properties files packaged into a JAR. Use environment variables, a secret manager, or a secure configuration mechanism appropriate for the deployment environment.

## 9. Combining XML with Java Configuration

Spring does not force an application to choose exclusively between XML or Java configuration. A Java configuration can import XML using @ImportResource:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportResource;

@Configuration
@ImportResource("classpath:/com/example/config/legacy-services.xml")
class ApplicationConfiguration {
}
~~~

Then, the context can be created from the Java configuration:

~~~java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(
             ApplicationConfiguration.class
         )) {

    ProductService service =
        context.getBean(ProductService.class);
}
~~~

This approach is useful when gradually migrating an application from XML to Java configuration. You can keep some legacy beans in XML while declaring new beans with @Bean or component scanning.

Spring Boot also supports importing XML via @ImportResource on the application configuration:

~~~java
@SpringBootApplication
@ImportResource("classpath:/legacy/application-context.xml")
public class Application {
}
~~~

When using Spring Boot, do not manually create a ClassPathXmlApplicationContext alongside SpringApplication just to load XML. Creating two independent contexts can cause beans to be initialized twice and dependencies not to be shared as expected. Import the XML into the context managed by Spring Boot instead.

## 10. Loading XML in Spring Test

The Spring TestContext Framework allows tests to initialize an ApplicationContext from XML. With JUnit Jupiter, you can use @SpringJUnitConfig or combine @ExtendWith(SpringExtension.class) and @ContextConfiguration.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(locations =
    "classpath:/com/example/config/application-context.xml")
class ProductServiceXmlConfigTest {

    @Autowired
    private ProductService productService;

    @Test
    void loadsProductServiceFromXml() {
        assertNotNull(productService);
    }
}
~~~

@SpringJUnitConfig is a composed annotation for JUnit Jupiter and Spring TestContext. The locations attribute specifies the XML configuration file to load. Spring creates the context, registers beans, and injects dependencies into the test instance.

You can write the equivalent using:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    locations = "classpath:/com/example/config/application-context.xml"
)
class ProductServiceXmlConfigTest {
    // ...
}
~~~

If you need to load multiple XML files:

~~~java
@SpringJUnitConfig(locations = {
    "classpath:/com/example/config/data-access.xml",
    "classpath:/com/example/config/services.xml"
})
class ServiceIntegrationTest {
    // ...
}
~~~

Place XML fixtures or test-only configurations in src/test/resources if they serve tests exclusively. Shared application configurations should reside in src/main/resources and be referenced by tests via the classpath.

### 10.1. XML location and classes

@ContextConfiguration supports both locations and classes. You can use XML together with Java configuration in a single test:

~~~java
@SpringJUnitConfig(
    locations = "classpath:/legacy/legacy-services.xml",
    classes = TestOverrides.class
)
class MixedConfigurationTest {
    // ...
}
~~~

TestContext will load the declared configuration sources. When multiple sources register the same bean name, make sure you understand the overriding policy and processing order of the Spring version in use. It is best to avoid having two sources define the same bean name unless explicitly intended.

### 10.2. Context Caching in Tests

Spring TestContext can cache the ApplicationContext across tests with equivalent configurations. Loading XML does not mean every test method always creates a new context. Caching reduces runtime, but tests must avoid mutating shared singleton state.

If a test alters application-wide state or mutable beans, restore the state after the test or design isolated fixtures. Only use @DirtiesContext when a test makes the context unsafe for reuse; this annotation causes Spring to evict the context from the cache and can slow down the suite.

## 11. Reading a Classpath Resource Directly in a Test

You do not always need to create an ApplicationContext to verify a resource. If the goal is merely to confirm a fixture file exists or is readable, use ClassPathResource directly:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.util.StreamUtils;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;

class ClasspathResourceTest {

    @Test
    void readsExpectedXmlFixture() throws Exception {
        // Arrange
        Resource resource = new ClassPathResource(
            "fixtures/sample-catalog.xml"
        );

        // Act
        String xml;
        try (InputStream input = resource.getInputStream()) {
            xml = StreamUtils.copyToString(
                input,
                StandardCharsets.UTF_8
            );
        }

        // Assert
        assertTrue(resource.exists());
        assertTrue(xml.contains("<catalog"));
    }
}
~~~

In real tests, assertions should inspect XML content using a parser or XPath if structure matters. contains only illustrates a very narrow check and does not prove the entire XML is valid.

### 11.1. Why Use getInputStream?

A Resource may reside in a JAR, a URL, or a source with no filesystem file. getFile() only works when the resource can be represented as a File. getInputStream() is the general way to read contents.

~~~java
Resource resource = new ClassPathResource("fixtures/sample-catalog.xml");

try (InputStream input = resource.getInputStream()) {
    byte[] bytes = StreamUtils.copyToByteArray(input);
}
~~~

Always close the InputStream after reading. Do not keep streams open across multiple tests or rely on garbage collection to release file handles.

### 11.2. Resource Existence and Readability

Resource can provide the following information:

- exists(): whether the resource exists as recognized by the implementation.
- isReadable(): whether the resource can be read.
- getFilename(): the filename if it can be determined.
- contentLength(): the content size if the implementation supports determining it.
- getInputStream(): opens a stream to read the content.
- getURL(): obtains a URL if the resource source can be represented as a URL.

Not every Resource implementation supports getFile, getURL, or contentLength. When writing general-purpose code, rely on guaranteed APIs or handle IOException appropriately.

## 12. ResourcePatternResolver and Multiple Classpath Resources

ResourceLoader typically returns a single Resource for a location. When you need to find multiple files matching a pattern, use ResourcePatternResolver:

~~~java
ResourcePatternResolver resolver =
    new PathMatchingResourcePatternResolver();

Resource[] xmlFiles = resolver.getResources(
    "classpath*:com/example/plugins/*.xml"
);

for (Resource xmlFile : xmlFiles) {
    try (InputStream input = xmlFile.getInputStream()) {
        // Read or process each resource.
    }
}
~~~

ResourcePatternResolver extends ResourceLoader with the ability to find resources by pattern. PathMatchingResourcePatternResolver is the implementation commonly used in Spring.

A few notes:

- classpath*: is useful when searching for resources across multiple classpath entries.
- Wildcard patterns allow matching multiple files by naming or directory rules.
- Do not assume the returned order represents configuration precedence.
- Some patterns may behave differently depending on classloaders, JAR layouts, and packaging.
- If each XML is used to register beans, consider loading them via a controlled reader/context rather than manually processing XML content as text.

When you need to discover XML files contributed by plugins, classpath scanning can help detect extensions. When loading the core application configuration, an explicit list of locations is usually easier to understand and control.

## 13. Relative and Absolute Resource Imports

In XML, the import element can use a relative location or a prefixed location:

~~~xml
<import resource="repositories.xml"/>
<import resource="classpath:/com/example/config/services.xml"/>
~~~

Relative locations are resolved relative to the XML resource containing the import element. This is convenient when files sit alongside each other:

~~~text
config/
├── application-context.xml
├── repositories.xml
└── services.xml
~~~

If application-context.xml imports repositories.xml by relative name, moving the entire group of files together preserves the relationship. If the file resides at a different classpath location, use classpath: to indicate the source clearly.

Do not use relative paths based on the process working directory in XML imports. Working directories can differ between IDEs, Gradle, containers, and production environments.

## 14. Common Mistakes When Loading XML and Classpath Resources

### 14.1. XML File Not on the Runtime Classpath

If the file is placed by mistake in a Java source directory or a folder not treated as a resource by the build tool, Spring will not find it. Place application files in src/main/resources and test fixtures in src/test/resources, or configure source sets/resource directories properly.

### 14.2. Using Filesystem Paths for Files Packaged in a JAR

Resources inside a JAR do not necessarily have a filesystem path. Use classpath: and the Resource API to read them. Do not convert classpath resources to File unless necessary.

### 14.3. Confusing classpath: with classpath*:

classpath: references a single resource. classpath*: finds multiple matching resources across the classpath. If you need to scan files provided across multiple JARs, use classpath*: with ResourcePatternResolver.

### 14.4. Missing Prefix and Implementation Dependence

A location without a prefix may be interpreted differently by ClassPathXmlApplicationContext and FileSystemXmlApplicationContext. Use explicit prefixes when the resource origin must remain consistent.

### 14.5. Incorrect XML Import Path

The import element can use a path relative to the current XML location or a prefixed location. Verify whether the imported file sits next to the current file or at the classpath root. Do not assume all paths are resolved from the project root.

### 14.6. Calling refresh at the Wrong Time

With GenericApplicationContext, load bean definitions first and then call refresh. Refresh finalizes container creation and bean initialization along the lifecycle; do not treat it as an operation that can be called arbitrarily multiple times.

### 14.7. Missing XML Namespace or Schema

When using context:component-scan or context:property-placeholder, you must declare the corresponding namespace and schema. If the parser reports an unrecognized element, verify the namespace URI, schemaLocation, and corresponding Spring dependencies.

### 14.8. Duplicate Bean Names Across Multiple XML Files

When loading multiple files, duplicate bean names can cause errors or overrides depending on configuration. Use distinct names, avoid accidental duplicate definitions, and check the application's bean definition overriding policy.

### 14.9. Properties File Not Found

Placeholder locations are also resource locations. Use classpath: for files in resources; if the properties file sits outside the artifact, use file: and ensure the file is present in the runtime environment.

### 14.10. Resources Only Present on the Test Classpath

A file in src/test/resources can be read when running tests but does not exist in the production application. Do not place required runtime configuration inside test resources.

## 15. Choosing the Right Loading Approach

| Need | Approach |
|---|---|
| Load one or more XML files from classpath in a standalone app | ClassPathXmlApplicationContext |
| Load XML from a file outside the artifact | FileSystemXmlApplicationContext |
| Control bean definition registration and refresh timing | GenericApplicationContext + XmlBeanDefinitionReader |
| Keep legacy XML in an app using Java configuration | @ImportResource |
| Load XML in Spring TestContext | @SpringJUnitConfig or @ContextConfiguration with locations |
| Only read a fixture file on the classpath | ClassPathResource |
| Find multiple resources using wildcards | ResourcePatternResolver |
| Load XML into a Spring Boot ApplicationContext | @ImportResource on Boot configuration |

No single loading approach fits every situation. Choose the API based on who owns the context lifecycle, where the file originates, and what the test needs to verify.

## 16. Pattern for Testing XML Context from Classpath

A test can verify that beans declared in XML and their dependencies are wired together:

~~~java
@SpringJUnitConfig(locations =
    "classpath:/com/example/config/application-context.xml")
class ApplicationXmlContextTest {

    @Autowired
    private ProductService productService;

    @Autowired
    private ProductRepository productRepository;

    @Test
    void loadsServiceAndItsRepositoryDependency() {
        assertNotNull(productService);
        assertNotNull(productRepository);
    }
}
~~~

If you want to verify actual behavior, invoke a public method on the service and assert the business outcome. Merely asserting bean existence proves the container created the beans, but does not guarantee every dependency or setting behaves correctly.

A test can read a Resource directly if it wants to verify the file exists on the test classpath:

~~~java
@Test
void xmlConfigurationIsAvailableOnClasspath() {
    Resource xml = new ClassPathResource(
        "com/example/config/application-context.xml"
    );

    assertTrue(xml.exists());
    assertTrue(xml.isReadable());
}
~~~

These two tests verify different things: the first initializes a Spring context from XML; the second only verifies that the resource can be found and read. Do not replace a context test with a file-existence check if the goal is to verify that Spring understands the bean definitions.

## Conclusion

Spring ApplicationContext can load XML from the classpath, filesystem, or various Resource sources. Use ClassPathXmlApplicationContext for XML configuration packaged with the application, FileSystemXmlApplicationContext for files outside the artifact, XmlBeanDefinitionReader when you need control over bean registration, and @ImportResource when combining XML with Java configuration. In tests, @SpringJUnitConfig or @ContextConfiguration loads XML into Spring TestContext; ClassPathResource and ResourcePatternResolver are suitable when you only need to read or locate fixtures. Explicit location prefixes, proper context lifecycle management, and placing resources in the right source sets keep configuration running consistently across development machines, CI, and deployment environments.

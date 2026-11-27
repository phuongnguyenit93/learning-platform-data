# Adding Templates, Resource Bundles, and ClassLoader-Loaded Resources

A Spring Boot application may run fine on the JVM yet fail when compiled to a GraalVM Native Image: a Thymeleaf page cannot find its template, Vietnamese messages fall back to the default text, or a configuration file read via `ClassLoader.getResourceAsStream()` returns `null`. The cause usually lies in how the native executable packages resources.

Native Image analyzes the application at build time. Files on the classpath are not automatically included in the executable in full; resources accessed by dynamic names or lookup mechanisms that the compiler cannot infer must be declared using **runtime hints**. This practice combines three scenarios in one Spring Boot application: rendering a template, looking up a resource bundle by locale, and reading a file from a path constructed at runtime.

This lesson belongs to the **Integrated Practice** chapter of the **`SPRING_BOOT_NATIVE_IMAGE`** module. The module teaches compiling Spring Boot into a GraalVM Native Image with Spring AOT to evaluate startup and memory, practicing Maven/Gradle, configuring reflection/resources, compatibility testing, container packaging, and operating native builds.

## 1. Expected Outcomes

After completing this practice, you will be able to:

- Place templates, message bundles, and classpath data in the proper locations inside `src/main/resources`.
- Configure Thymeleaf and Spring Boot `MessageSource` for multiple languages.
- Use `ClassLoader.getResourceAsStream()` to read resources whose names are constructed from a locale.
- Distinguish resource patterns from resource bundle hints.
- Register resources using `RuntimeHintsRegistrar` and `@ImportRuntimeHints`.
- Test hints using `RuntimeHintsPredicates`.
- Build and run the native executable to confirm the resources are actually present in the artifact.

## 2. Practice Problem

We will build an endpoint that displays an order receipt:

`GET /orders/{orderId}/receipt`

When receiving a request, the application:

1. Selects the `orders/receipt.html` template to render HTML.
2. Reads the title and footer from the `messages` resource bundle according to the request's locale.
3. Reads the shipping policy from `catalog/vi/shipping-policy.txt` or `catalog/en/shipping-policy.txt` via `ClassLoader`.

On the JVM, the classpath normally contains the resource files so lookups may work without extra configuration. When building native, we declare the resources required by these three flows.

## 3. Project Resource Structure

The example uses Spring MVC and Thymeleaf. Add `spring-boot-starter-web` and `spring-boot-starter-thymeleaf` to the project; test dependencies use `spring-boot-starter-test`.

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/orders/
    │       ├── OrdersApplication.java
    │       ├── ReceiptController.java
    │       ├── ReceiptView.java
    │       ├── ReceiptLabelService.java
    │       ├── ShippingPolicyReader.java
    │       └── OrderResourceHints.java
    └── resources/
        ├── application.properties
        ├── messages.properties
        ├── messages_vi.properties
        ├── templates/
        │   └── orders/
        │       └── receipt.html
        └── catalog/
            ├── en/
            │   └── shipping-policy.txt
            └── vi/
                └── shipping-policy.txt
~~~

Spring Boot automatically discovers templates for supported engines under `src/main/resources/templates` under default configuration. With Thymeleaf, the view name `orders/receipt` typically maps to `classpath:/templates/orders/receipt.html`.

Do not place files meant to be packaged into `src/main/webapp` for executable JAR applications. Place templates and classpath data in `src/main/resources`.

## 4. Configure Spring Boot Message Source

In `application.properties`:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
spring.thymeleaf.encoding=UTF-8
~~~

By default, Spring Boot looks for a resource bundle with base name `messages` at the classpath root. The default `messages.properties` file is crucial: if only locale-specific files like `messages_vi.properties` exist without the default file, auto-configuration may not create a `MessageSource`.

Create `messages.properties` as the fallback file:

~~~properties
receipt.title=Order receipt
receipt.footer=Thank you for your order.
~~~

Create `messages_vi.properties`:

~~~properties
receipt.title=Phiếu xác nhận đơn hàng
receipt.footer=Cảm ơn bạn đã mua hàng.
~~~

Spring Boot resolves messages based on the locale and configured basename. `fallback-to-system-locale=false` prevents `MessageSource` from falling back to the host machine's locale when a translation is missing; `messages.properties` remains the default fallback.

If there are additional bundles, you can list multiple basenames:

~~~properties
spring.messages.basename=messages,config.i18n.labels
~~~

## 5. Create the Thymeleaf Template

File `src/main/resources/templates/orders/receipt.html`:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="#{receipt.title}">Order receipt</title>
</head>
<body>
    <main>
        <h1 th:text="#{receipt.title}">Order receipt</h1>
        <p>
            Order:
            <strong th:text="${receipt.orderId}">ORD-100</strong>
        </p>
        <section>
            <h2>Shipping policy</h2>
            <p th:text="${receipt.shippingPolicy}">
                Shipping policy text
            </p>
        </section>
        <footer th:text="${footer}">Thank you for your order.</footer>
    </main>
</body>
</html>
~~~

The `#{...}` expressions read messages from Spring's `MessageSource`; `${...}` reads attributes from the model. The template is selected by view name from the controller, while the HTML content is read by the template engine during rendering.

A template referenced by a view name string might not be inferred by the compiler in the same way as a `Class.getResourceAsStream()` call with a constant path. If the application manages template paths itself or templates are chosen dynamically, register the corresponding pattern and verify in the native executable.

## 6. Read Messages Using ResourceBundle

Spring `MessageSource` fits beans/controllers and Thymeleaf message expressions well. If a library or Java code needs to use `java.util.ResourceBundle` directly, it can read the same base name:

~~~java
package com.example.orders;

import java.util.Locale;
import java.util.ResourceBundle;

import org.springframework.stereotype.Component;

@Component
public class ReceiptLabelService {

    public String footer(Locale locale) {
        ResourceBundle bundle = ResourceBundle.getBundle(
                "messages", locale, getClass().getClassLoader());
        return bundle.getString("receipt.footer");
    }
}
~~~

The base name is `messages`, without the `.properties` extension and without the `_vi` suffix. The JDK locates the matching locale file, such as `messages_vi.properties`, and applies `ResourceBundle` fallback rules.

The property `spring.messages.fallback-to-system-locale` only controls Spring Boot's `MessageSource`. Direct Java calls to `ResourceBundle.getBundle()` still follow JDK fallback rules; if you need consistent fallback control across the application, prefer injecting and using `MessageSource` instead of mixing both mechanisms.

Native Image needs to know in advance which bundles the application will look up. Register the bundle with `registerResourceBundle("messages")`; merely registering a `.properties` file pattern does not substitute for a resource bundle hint.

If the application uses JDK locale data such as date, number, or currency formatting for locales outside the default set, check Native Image's locale configuration and consider `-H:IncludeLocales=vi,en`. JDK locale data and resource bundle registration are related yet distinct pieces of configuration.

## 7. Read Dynamically Named Resources via ClassLoader

File `src/main/resources/catalog/vi/shipping-policy.txt`:

~~~text
Đơn hàng nội thành được giao trong một đến hai ngày làm việc.
~~~

File `src/main/resources/catalog/en/shipping-policy.txt`:

~~~text
Local orders are delivered within one to two business days.
~~~

Create `ShippingPolicyReader`:

~~~java
package com.example.orders;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import org.springframework.stereotype.Component;

@Component
public class ShippingPolicyReader {

    private final ClassLoader classLoader =
            ShippingPolicyReader.class.getClassLoader();

    public String read(Locale locale) {
        String language = "vi".equals(locale.getLanguage()) ? "vi" : "en";
        String resourcePath =
                "catalog/" + language + "/shipping-policy.txt";

        try (InputStream input =
                     classLoader.getResourceAsStream(resourcePath)) {
            if (input == null) {
                throw new IllegalStateException(
                        "Classpath resource not found: " + resourcePath);
            }
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
        catch (IOException ex) {
            throw new UncheckedIOException(
                    "Cannot read " + resourcePath, ex);
        }
    }
}
~~~

Because the path is constructed from the locale, static analysis cannot infer the exact file that will be opened. The pattern hint `catalog/**` covers both files in the example.

Note the path rules:

| API | How to Pass the Resource Name |
|---|---|
| `ClassLoader.getResourceAsStream("catalog/vi/shipping-policy.txt")` | No leading `/`; path is relative to the classpath root |
| `SomeClass.class.getResourceAsStream("/catalog/vi/shipping-policy.txt")` | Leading `/` indicates the classpath root |
| `SomeClass.class.getResourceAsStream("shipping-policy.txt")` | Path is relative to the class's package |

Never concatenate user-supplied strings directly into resource paths. Map input to an allowlisted set of values such as `vi` and `en` to prevent path traversal or unintended file access.

### ClassLoader and Spring ResourceLoader

If you want to use Spring's abstraction, you can inject `ResourceLoader`:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:catalog/vi/shipping-policy.txt");
try (InputStream input = resource.getInputStream()) {
    // Read resource contents
}
~~~

When you need to retrieve multiple resources across dependency JARs, use `ResourcePatternResolver`:

~~~java
Resource[] resources =
        resourcePatternResolver.getResources("classpath*:catalog/**/*.txt");
~~~

`classpath:` targets a single resolved classpath location; `classpath*:` searches matching resources across the entire classpath. This is Spring resource resolver syntax, not the syntax passed to `RuntimeHints.registerPattern`. In the example above, the hint still uses a classpath path such as `catalog/**`.

## 8. Register Resource Hints with RuntimeHintsRegistrar

Create `OrderResourceHints.java`:

~~~java
package com.example.orders;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OrderResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("templates/**");
        hints.resources().registerPattern("catalog/**");
        hints.resources().registerResourceBundle("messages");

        // Thymeleaf reads model getters through property access.
        hints.reflection().registerType(
                ReceiptView.class, MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
~~~

Patterns are paths relative to the classpath root and do not start with `/`:

- `templates/**` covers templates in the `templates` directory and its subdirectories.
- `catalog/**` covers the locale-specific policy files.
- `registerResourceBundle("messages")` registers the bundle by base name.
- A reflection hint for `ReceiptView` is needed if the template accesses model getters via property access and AOT cannot infer those calls.

Create `ReceiptView.java`:

~~~java
package com.example.orders;

public class ReceiptView {

    private final String orderId;
    private final String shippingPolicy;

    public ReceiptView(String orderId, String shippingPolicy) {
        this.orderId = orderId;
        this.shippingPolicy = shippingPolicy;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getShippingPolicy() {
        return shippingPolicy;
    }
}
~~~

Register the registrar in the application:

~~~java
package com.example.orders;

import org.springframework.aot.hint.annotation.ImportRuntimeHints;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@ImportRuntimeHints(OrderResourceHints.class)
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

`@ImportRuntimeHints` causes Spring AOT to invoke the registrar during build processing. The hints are converted into metadata used by Native Image; you do not need to call `registerHints()` yourself at runtime.

Some starters and libraries may already supply reachability metadata for their internals. Inspect metadata contributed by dependencies and AOT output before adding duplicate hints. Application-managed resources, especially dynamically constructed paths, still need to be inventoried and tested.

## 9. Why Must Resource Patterns and Resource Bundles Be Separate?

`registerPattern` declares regular resource files. `registerResourceBundle` declares bundles that `ResourceBundle.getBundle()` looks up by base name and locale.

| Resource | Example | Hint |
|---|---|---|
| Thymeleaf template | `templates/orders/receipt.html` | `registerPattern("templates/**")` |
| ClassLoader file | `catalog/vi/shipping-policy.txt` | `registerPattern("catalog/**")` |
| Java resource bundle | `messages.properties`, `messages_vi.properties` | `registerResourceBundle("messages")` |
| Another bundle | `config/i18n/labels.properties` | `registerResourceBundle("config.i18n.labels")` |

Registering `registerPattern("*.properties")` is not equivalent to registering a bundle. Conversely, registering a bundle does not automatically cover templates or text files read via `ClassLoader`.

Spring `ResourceHints.registerPattern` follows Spring Framework pattern rules. Use `*`/`**` deliberately and cover only the directories the application needs; avoid including the entire classpath without reason, as that increases executable size.

## 10. Connect the Components with a Controller

`ReceiptController.java`:

~~~java
package com.example.orders;

import java.util.Locale;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@Controller
public class ReceiptController {

    private final ShippingPolicyReader policyReader;
    private final ReceiptLabelService labelService;

    public ReceiptController(
            ShippingPolicyReader policyReader,
            ReceiptLabelService labelService) {
        this.policyReader = policyReader;
        this.labelService = labelService;
    }

    @GetMapping("/orders/{orderId}/receipt")
    public String showReceipt(
            @PathVariable String orderId, Locale locale, Model model) {

        String policy = policyReader.read(locale);
        model.addAttribute("receipt",
                new ReceiptView(orderId, policy));
        model.addAttribute("footer", labelService.footer(locale));
        return "orders/receipt";
    }
}
~~~

For a request with `Accept-Language: vi`, Spring MVC provides the matching locale to the controller; the reader picks the Vietnamese file, and the resource bundle returns Vietnamese messages. Thymeleaf renders the `orders/receipt` template.

## 11. Test Runtime Hints

Create a unit test for the registrar:

~~~java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class OrderResourceHintsTests {

    @Test
    void registersApplicationResources() {
        RuntimeHints hints = new RuntimeHints();
        new OrderResourceHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("templates/orders/receipt.html"))
                .accepts(hints);

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("catalog/vi/shipping-policy.txt"))
                .accepts(hints);

        assertThat(RuntimeHintsPredicates.resource()
                .forBundle("messages"))
                .accepts(hints);
    }
}
~~~

This test verifies that the registrar declares the expected hints. It does not prove that the templates or files were packaged into the native executable. Additional integration testing on the native binary itself is required.

You can check that resources exist on the classpath when running on the JVM:

~~~java
@Test
void resourcesAreOnTheClasspath() {
    ClassLoader loader = getClass().getClassLoader();
    assertThat(loader.getResource(
            "catalog/vi/shipping-policy.txt")).isNotNull();
    assertThat(loader.getResource(
            "templates/orders/receipt.html")).isNotNull();
}
~~~

This classpath test catches misplaced directories or misspelled filenames, but still does not replace a native smoke test.

## 12. Test on the JVM First

Run unit tests:

~~~bash
./mvnw test
~~~

Or with Gradle:

~~~bash
./gradlew test
~~~

Start the application on the JVM and call the endpoint:

~~~bash
curl -H "Accept-Language: vi" \
  http://localhost:8080/orders/ORD-100/receipt

curl -H "Accept-Language: en" \
  http://localhost:8080/orders/ORD-100/receipt
~~~

Verify:

- The page returns HTTP 200.
- The title and footer change according to the locale.
- The order ID appears in the page.
- The shipping policy content comes from the locale-appropriate file.
- There are no `TemplateInputException`, `MissingResourceException`, or missing classpath resource errors.

If the JVM test fails, fix the classpath, view name, or locale configuration before building native. Native Image cannot fix a resource path that is already wrong in the application.

## 13. Build Spring AOT and Native Image

With Maven, use the native profile configured with the Spring Boot Maven Plugin and GraalVM Native Build Tools:

~~~bash
./mvnw -Pnative native:compile
~~~

With Gradle, use the `nativeCompile` task when the Native Build Tools plugin is configured:

~~~bash
./gradlew nativeCompile
~~~

Spring AOT processes the application context and contributes runtime hints. You can inspect the generated resources/hints in the build's AOT output:

- Maven: `target/spring-aot/main/resources/META-INF/native-image/`
- Gradle: `build/generated/aotResources/META-INF/native-image/`

Exact paths may vary by plugin version and project configuration. Only read the output to inspect it; do not edit generated files directly because the next build may overwrite them. Fix `RuntimeHintsRegistrar`, dependency metadata, or source build configuration instead.

After building, locate the executable in the project's native output. The name and path depend on `artifactId`, `imageName`, and Maven/Gradle configuration.

## 14. Test on the Native Executable

Launch the built executable and call the same endpoint again:

~~~bash
./target/orders-service
~~~

The path above is an example for a Maven project whose artifact is named `orders-service`; for Gradle or another artifact, use the actual output path.

~~~bash
curl --fail -H "Accept-Language: vi" \
  http://localhost:8080/orders/ORD-100/receipt

curl --fail -H "Accept-Language: en" \
  http://localhost:8080/orders/ORD-100/receipt
~~~

The native test must render the real template and read every locale file. Checking only the health endpoint is insufficient because that endpoint may not touch templates, resource bundles, or ClassLoader resources.

### Results Table to Record

| Check | JVM | Native Image |
|---|---|---|
| Render `orders/receipt.html` | PASS/FAIL | PASS/FAIL |
| Vietnamese messages | PASS/FAIL | PASS/FAIL |
| English/fallback messages | PASS/FAIL | PASS/FAIL |
| Read `catalog/vi/shipping-policy.txt` | PASS/FAIL | PASS/FAIL |
| Read `catalog/en/shipping-policy.txt` | PASS/FAIL | PASS/FAIL |
| No resource/template errors | PASS/FAIL | PASS/FAIL |

Only mark the native test as PASS when executed on the executable built with release configuration. JVM tests and `RuntimeHintsPredicates` tests are additional verification layers, not substitutes for native testing.

## 15. Common Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `TemplateInputException` or template does not exist | Template in wrong directory or missing resource hint | Place under `src/main/resources/templates`, check view name and `templates/**` |
| Template works on JVM but fails on native | Template resolved dynamically or dependency lacks required metadata | Register pattern and render all templates on native |
| `MissingResourceException` | Bundle not registered or wrong base name | Use `registerResourceBundle("messages")`, check bundle name |
| Only `messages_vi.properties`, no `messages.properties` | Missing default bundle for Spring Boot auto-configuration | Add the default file at the classpath root |
| `ClassLoader.getResourceAsStream()` returns `null` | Wrong path, leading `/`, or resource not packaged | Check path relative to classpath root and register `catalog/**` |
| JVM reads locale file but native cannot | Filename constructed dynamically and not inferred at build time | Register a pattern covering supported locales |
| Bundle returns unexpected language | Request locale, fallback, or default locale differs from expectations | Check `Accept-Language`, default file, and fallback policy |
| Error when calling `URL.getFile()` | Resource in native executable may have `resource:` URL scheme instead of `file:` | Use `getResourceAsStream()`/`openStream()` |
| File exists in builder but missing in final image | Docker build context or packaging step excluded the resource | Inspect artifact and final image; keep resources on the build classpath |
| Thymeleaf reports error accessing model property | Type only referenced in template so reflection hint is missing | Register required members for the model type and re-test native |

## 16. Do Not Assume Classpath Resources Are Filesystem Files

In a native executable, embedded resources may be returned as URLs with the `resource:` scheme. Therefore, the following code is not portable:

~~~java
URL url = getClass().getClassLoader().getResource("catalog/vi/shipping-policy.txt");
File file = new File(url.getFile());
~~~

It assumes the resource always has a real file path on the filesystem. Read the stream instead:

~~~java
try (InputStream input = getClass().getClassLoader()
        .getResourceAsStream("catalog/vi/shipping-policy.txt")) {
    // Read bytes or text from stream
}
~~~

If a third-party API strictly requires a file path, copy the resource to a temporary file at runtime, control permissions and file lifecycle, and pass the temporary path to the API. Do not attempt to convert a `resource:` URL into a `File`.

## 17. When to Use the Tracing Agent?

The GraalVM tracing agent can record resources, reflection, and dynamic accesses actually used by the application while running on the JVM. You can use the agent during integration tests:

~~~bash
java -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/orders-service.jar
~~~

Then execute flows that render templates, look up each locale, and read every type of supported resource. The agent only records paths that were executed. If tests do not render an email template or do not select the `vi` locale, the corresponding metadata may not appear.

Use the agent's output as discovery and cross-reference evidence. For Spring applications, `RuntimeHintsRegistrar` is usually the right place to manage intentional hints alongside code. Do not blindly copy all agent configuration into a release without reviewing it.

## 18. Practice Completion Checklist

- [ ] Templates reside under `src/main/resources/templates`.
- [ ] Default `messages.properties` and supported locale files exist.
- [ ] `spring.messages.basename` and encoding are properly configured.
- [ ] ClassLoader resources reside under `src/main/resources/catalog`.
- [ ] Dynamic paths are built only from allowlisted locales/values.
- [ ] `RuntimeHintsRegistrar` registers `templates/**`.
- [ ] Pattern hint exists for `catalog/**` files.
- [ ] Resource bundle hint exists for base name `messages`.
- [ ] Reflection hint exists if templates access model properties via reflection and AOT cannot infer them.
- [ ] Unit test verifies `RuntimeHintsPredicates`.
- [ ] JVM tests render the template and read all resources.
- [ ] Native executable renders the template and reads all locales.
- [ ] `URL.getFile()` is not used to read embedded resources.
- [ ] AOT/native metadata output is inspected when diagnosing issues.

## 19. Extension Exercises

**Exercise 1 — Add an email template:** create `templates/mail/receipt-notice.html`, add an email rendering flow, and verify that the template is present in the native executable.

**Exercise 2 — Add a locale:** add `messages_ja.properties` and `catalog/ja/shipping-policy.txt`. Update the locale allowlist, hints, and native tests for Japanese.

**Exercise 3 — Multiple bundles:** create `config/i18n/labels.properties` along with locale translations. Register `config.i18n.labels` and read it using `ResourceBundle.getBundle()`.

**Exercise 4 — ResourcePatternResolver:** place multiple rule files across different classpath directories and use `classpath*:` to read them all. Register a pattern covering the required files and verify each file in native.

**Exercise 5 — Check template reflection:** move model properties from simple strings into a DTO. Observe the native failure if the hint is missing, then register only the required public getters and re-run the integration test.

## 20. References

- [Spring Boot — Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): `RuntimeHintsRegistrar`, `@ImportRuntimeHints`, testing custom hints, and static metadata.
- [Spring Framework — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): runtime hints for reflection, resources, resource bundles, and AOT limitations.
- [Spring Framework — ResourceHints API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/aot/hint/ResourceHints.html): `registerPattern`, `registerResourceBundle`, and `registerPatternIfPresent`.
- [Spring Framework — ResourcePatternHint API](https://docs.spring.io/spring-framework/docs/6.0.20/javadoc-api/org/springframework/aot/hint/ResourcePatternHint.html): pattern rules for resource hints.
- [Spring Framework — Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): `ResourceLoader`, `ResourcePatternResolver`, `classpath:`, and `classpath*:`.
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html): default `messages` basename, default files, and locale configuration.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): template engines and default template locations.
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): resource metadata, resource bundles, locales, and `resource:` URLs in native executables.
- [GraalVM — Include Resources in a Native Executable](https://www.graalvm.org/dev/reference-manual/native-image/guides/include-resources/): how to include classpath resources in the executable and inspect the build report.

**Remember:** Templates, resource bundles, and files read via ClassLoader are three distinct resource types. Register the proper pattern for files, the proper base name for bundles, add reflection hints when templates access models via reflection, and then test on the native executable itself. Success on the JVM only confirms the JVM classpath; native smoke tests confirm that resources were packaged and accessed properly at runtime.

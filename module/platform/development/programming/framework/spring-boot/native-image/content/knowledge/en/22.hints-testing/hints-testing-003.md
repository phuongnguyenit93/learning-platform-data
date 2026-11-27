# Testing Resource Patterns, Resource Bundles, and Proxy Interface Lists

## 1. Why test these three hint categories?

Spring Boot Native Image needs to know in advance which resources and dynamic access structures an application will use. Reflection hints describe classes/members; resource hints describe classpath files; resource bundle hints describe locale-based message bundles; proxy hints describe interface combinations used to create JDK dynamic proxies.

A registrar can compile cleanly yet still omit a resource or declare the wrong interface combination. Errors often only surface when running natively: `ClassPathResource` returns not found, `ResourceBundle.getBundle()` cannot locate the required locale, or a JDK proxy cannot be created because the metadata does not match the actual interface list.

In the **SPRING_BOOT_NATIVE_IMAGE** module, you need to test these three metadata types individually with `RuntimeHintsPredicates`, then verify that they are collected during Spring AOT and work in the native executable. This article covers how to build fixtures, write unit tests for the registrar, verify locales and interface ordering, and distinguish metadata tests from native integration tests.

## 2. The three metadata groups and corresponding APIs

The APIs are in the `org.springframework.aot.hint` package:

| Need | Registration API | What to verify |
|---|---|---|
| Classpath file/resource | `hints.resources().registerPattern(...)` | The path/pattern is actually declared |
| Resource bundle | `hints.resources().registerResourceBundle(...)` | The bundle base name is declared |
| JDK dynamic proxy | `hints.proxies().registerJdkProxy(...)` | Exact interface combination and ordering |
| Testing resources | `RuntimeHintsPredicates.resource()` | Predicate matches registered files |
| Testing bundles | `RuntimeHintsPredicates.resource()` | Predicate matches bundle base name |
| Testing proxies | `RuntimeHintsPredicates.proxies()` | Predicate matches interface list |

Predicate APIs may have minor differences across Spring Framework versions. Use IDE/Javadoc for your actual dependency version if overload signatures differ. Do not blindly apply examples from a newer version to an older project without checking.

## 3. Organizing resource fixtures on the classpath

Example structure:

```text
src/main/resources/
├── schemas/
│   ├── order-v1.json
│   └── order-v2.json
├── templates/
│   └── invoice.html
└── i18n/
    ├── messages.properties
    ├── messages_vi.properties
    └── messages_en.properties
```

There are two groups of resources in the example:

- Regular files: JSON schemas and an HTML template.
- Resource bundle: message bundle with base name `i18n.messages` and locale variants.

Classpath resource paths are typically declared relative to the classpath root, such as `schemas/order-v1.json`. Resource bundles use a base name following `ResourceBundle` conventions, such as `i18n.messages`—do not use a file name like `messages_vi.properties` as the base name.

Ensure fixtures reside in `src/main/resources` if they are production resources. Fixtures placed only in `src/test/resources` do not automatically become resources of the production executable.

## 4. Registering resource patterns and bundles

A registrar can declare both:

```java
final class ApplicationResourceHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern(
                "schemas/order-*.json");

        hints.resources().registerPattern(
                "templates/*.html");

        hints.resources().registerResourceBundle(
                "i18n.messages");
    }
}
```

Attach the registrar to a configuration processed by Spring AOT:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ApplicationResourceHints.class)
class ResourceConfiguration {
}
```

Patterns should be specific enough to cover the resources the application actually reads. If there are only two fixed schema versions, you can register each file explicitly instead of opening the whole directory. Resource bundles are registered by base name; matching locale variants are handled according to the bundle mechanism.

Resource hints do not package files external to the binary, such as `/etc/orders/rules.json`. External files must be mounted/provided at runtime and read using filesystem APIs.

## 5. Testing the registrar independently of a Spring context

You can invoke the registrar directly in a unit test to verify the metadata:

```java
class ApplicationResourceHintsTest {

    @Test
    void registersSchemaAndMessageBundle() {
        RuntimeHints hints = new RuntimeHints();

        new ApplicationResourceHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("schemas/order-v1.json")
                .test(hints))
                .isTrue();

        assertThat(RuntimeHintsPredicates.resource()
                .forBundle("i18n.messages")
                .test(hints))
                .isTrue();
    }
}
```

The test uses JUnit and AssertJ. The `forResource` predicate checks the registered resource path; `forBundle` checks the bundle base name. Some Spring versions may provide overloads or predicates with slightly different call styles, so verify against the dependency you are using.

This unit test verifies that the registrar declared hints in the `RuntimeHints` object. It does not prove that Spring AOT discovered the registrar or that Native Image packaged the actual resources.

## 6. Testing multiple resource paths

If the registrar registers a pattern:

```java
hints.resources().registerPattern("schemas/order-*.json");
```

You can test the expected production paths:

```java
@Test
void registersSupportedOrderSchemas() {
    RuntimeHints hints = new RuntimeHints();
    new ApplicationResourceHints().registerHints(
            hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.resource()
            .forResource("schemas/order-v1.json")
            .test(hints)).isTrue();

    assertThat(RuntimeHintsPredicates.resource()
            .forResource("schemas/order-v2.json")
            .test(hints)).isTrue();
}
```

Do not test only one representative path if the application has multiple resources selected via properties. Create test cases representing all valid versions/schemas/templates.

If a pattern is too broad, the predicate might report a resource path match even when that file does not exist in the artifact. Therefore, add a test verifying that the real resource can be read from the classloader:

```java
@Test
void orderSchemaExistsOnClasspath() {
    assertThat(getClass().getClassLoader()
            .getResource("schemas/order-v1.json"))
            .isNotNull();
}
```

The classpath existence test verifies that the file is on the test runtime classpath; ensure the resource belongs to the main output if the goal is to include it in the native application.

## 7. Resource bundles and base names

Java `ResourceBundle` uses a base name to locate locale-specific files. Given:

```text
i18n/messages.properties
i18n/messages_vi.properties
i18n/messages_en.properties
```

the base name is:

```text
i18n.messages
```

Example of reading a bundle:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "i18n.messages",
        Locale.forLanguageTag("vi"));

String greeting = bundle.getString("greeting");
```

Contents of `messages_vi.properties`:

```properties
greeting=Xin chào
order.created=Tạo đơn hàng thành công
```

Contents of `messages_en.properties`:

```properties
greeting=Hello
order.created=Order created successfully
```

When testing, use an explicit locale rather than relying on the test runner's default locale. This prevents tests from passing on a developer machine but failing in CI/containers due to a different default locale.

## 8. Testing resource bundle hints

You can verify that the bundle base name is registered:

```java
@Test
void registersMessageBundle() {
    RuntimeHints hints = new RuntimeHints();
    new ApplicationResourceHints().registerHints(
            hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.resource()
            .forBundle("i18n.messages")
            .test(hints))
            .isTrue();
}
```

This predicate verifies the bundle registration metadata. To verify contents and locales, add an actual behavior test:

```java
@Test
void loadsVietnameseAndEnglishMessages() {
    ResourceBundle vi = ResourceBundle.getBundle(
            "i18n.messages",
            Locale.forLanguageTag("vi"));

    ResourceBundle en = ResourceBundle.getBundle(
            "i18n.messages",
            Locale.forLanguageTag("en"));

    assertThat(vi.getString("greeting")).isEqualTo("Xin chào");
    assertThat(en.getString("greeting")).isEqualTo("Hello");
}
```

This test verifies that the bundle is found on the JVM test classpath and the keys contain the expected text. A native integration test is still needed to confirm that the bundle was included in the executable.

You should also test fallback locales per product requirements. Java `ResourceBundle` follows fallback rules for locales and the default bundle; if the application needs specific behavior, write tests for a locale without its own file and for the default bundle.

## 9. Do not confuse the bundle base name with a resource filename

A common mistake is registering:

```java
hints.resources().registerResourceBundle(
        "i18n/messages_vi.properties");
```

This is not a standard `ResourceBundle` base name. You must register:

```java
hints.resources().registerResourceBundle(
        "i18n.messages");
```

The base name uses dots to separate package/path segments according to `ResourceBundle` conventions. Locale suffixes like `_vi` or `_en` are used by the runtime to locate variants; do not append suffixes to the base name when you want to support multiple locales of the same bundle.

If the application uses Spring `MessageSource` instead of calling `ResourceBundle` directly, verify the `MessageSource` basename configuration and test natively using the actual API. Do not assume Spring's basename always matches custom resource configurations if multiple bundles exist.

## 10. Testing proxy interface lists

A JDK dynamic proxy is identified by an ordered list of interfaces. For example:

```java
hints.proxies().registerJdkProxy(
        OrderOperations.class,
        Auditable.class);
```

Unit test:

```java
@Test
void registersOrderProxyInExpectedOrder() {
    RuntimeHints hints = new RuntimeHints();
    new OrderProxyHints().registerHints(
            hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.proxies()
            .forInterfaces(
                    OrderOperations.class,
                    Auditable.class)
            .test(hints))
            .isTrue();
}
```

Use the exact same order in both the registrar and the predicate. Do not replace `containsExactly` with `containsExactlyInAnyOrder` when checking runtime proxies; ordering is part of the proxy definition.

A hint for `[OrderOperations, Auditable]` should not be assumed to cover `[Auditable, OrderOperations]`. If the application truly creates both variants, register and test each combination.

## 11. Comparing metadata with actual runtime proxies

In addition to checking predicates, create the proxy on the JVM and verify the interface list:

```java
Object proxy = Proxy.newProxyInstance(
        OrderOperations.class.getClassLoader(),
        new Class<?>[] {
                OrderOperations.class,
                Auditable.class
        },
        (instance, method, args) -> null);

assertThat(proxy.getClass().getInterfaces())
        .containsExactly(
                OrderOperations.class,
                Auditable.class);
```

For proxies created by Spring AOP, retrieve the bean from the `ApplicationContext` and inspect the actual object. Advisors, introductions, or framework wrappers can add interfaces; do not infer the final list solely from the interfaces on the implementation class.

When writing a registrar, compare the actual interface list observed in tests with the registered list. If the list is constructed dynamically, identify all valid combinations at build time or standardize the factory to use a single consistent order.

## 12. Organizing tests for a composite registrar

An application may have multiple separate registrars for resources, bundles, and proxies. You can test each registrar individually to make failures easy to locate, and then have a composite test confirming all critical metadata.

Example test structure:

```text
src/test/java/
└── com/example/nativeconfig/
    ├── ResourceHintsTest.java
    ├── MessageBundleHintsTest.java
    ├── ProxyHintsTest.java
    └── ApplicationHintsTest.java
```

Avoid putting every assertion into one long test without context. When a resource test fails, you need to know which resource path failed; when a proxy test fails, you need to know which interface combination was wrong.

A composite test is useful to ensure the application's AOT configuration still includes all hint groups after refactoring. However, it does not replace detailed tests for each registrar.

## 13. Distinguishing the three testing layers

| Test layer | What is verified | What is not yet proven |
|---|---|---|
| Registrar unit test | `RuntimeHints` contains expected entries | That AOT collected the registrar |
| Classpath/bundle/proxy JVM test | Resources and proxies work on the JVM | That metadata is included in the native executable |
| Native integration test | Native binary reads resources/bundles and creates real proxies | That all other runtime branches are covered |

A passing predicate test does not guarantee a successful native build. A passing native build also does not guarantee that rare resource bundle locales or infrequently used proxy combinations work. You must test on the actual executable and run meaningful scenarios.

## 14. Native integration tests for resources and bundles

Create a simple service that uses resources:

```java
@Component
class OrderSchemaLoader {

    String load(String version) throws IOException {
        String path = "schemas/order-" + version + ".json";

        try (InputStream input =
                getClass().getClassLoader()
                        .getResourceAsStream(path)) {
            if (input == null) {
                throw new FileNotFoundException(path);
            }
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
```

Native tests should invoke the service with every valid version and verify that the content parses properly. For bundles, exercise both `vi`/`en` locales and check keys. For proxies, create the proxy via the same production factory, verify its interfaces, and invoke methods.

You can use the native test task if the plugin supports it, or launch the native executable and send HTTP requests. A black-box approach verifies packaging, resources, `ApplicationContext`, and runtime behavior together.

## 15. Diagnosing common failures

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Resource predicate fails | Wrong path or registrar does not register pattern | Compare classpath path and registrar |
| Predicate passes but native resource is null | Registrar not collected by AOT or resource not in main artifact | Inspect AOT output and JAR/resource inputs |
| Bundle not found in native | Wrong base name or missing bundle hint | Register correct base name and test locales |
| Only `vi` locale fails | Missing variant, wrong filename, or unexpected fallback | Check `messages_vi` and test locale explicitly |
| Proxy predicate fails | Wrong interface list or ordering | Compare runtime list and registrar |
| Predicate passes but native proxy fails | AOT did not collect hint or runtime proxy has different interfaces | Inspect generated metadata and actual proxy class |
| JVM passes, native fails | Metadata not packaged or different path | Run native integration and check build diagnostics |
| CI test differs from dev machine | Default locale or case-sensitive path | Set explicit locale, normalize resource names |

When investigating, identify which test is failing: predicate, JVM resource/proxy behavior, AOT collection, or native runtime. Do not add broad metadata before knowing which layer is missing.

## 16. Hands-on exercise: testing resources, bundles, and proxies

**Context:** the Order API service reads two JSON schemas, displays Vietnamese/English messages, and creates a JDK proxy implementing `OrderOperations` and `Auditable`.

**Step 1 — Create fixtures.** Place `schemas/order-v1.json`, `schemas/order-v2.json`, `i18n/messages.properties`, `messages_vi.properties`, and `messages_en.properties` in main resources.

**Step 2 — Write the registrar.** Register the schema pattern, bundle base name `i18n.messages`, and proxy interface list in the exact order.

**Step 3 — Write predicate tests.** Use `RuntimeHintsPredicates.resource()` to check each schema/bundle; use `RuntimeHintsPredicates.proxies()` to check the exact interface combination.

**Step 4 — Write behavior tests on the JVM.** Read schemas, fetch messages for `vi`/`en` locales, create the proxy, and assert the interface list with `containsExactly`.

**Step 5 — Verify AOT collection.** Attach the registrar to a configuration in `ApplicationContext` and run Spring AOT.

**Step 6 — Build native.** Use the appropriate Native Build Tools, verify metadata is collected, and confirm the executable builds successfully.

**Step 7 — Run native integration.** Exercise the schema-reading, locale-based message display, and proxy-creation flows; use the same fixtures as the JVM tests.

**Step 8 — Test failure variants.** Try a nonexistent resource version, a locale without its own variant, and a different proxy interface order to verify fallback/error behavior.

Completion criteria: registrar unit tests pass; classpath resources and bundles have the right contents; runtime proxies have the exact interface list and order; the same behavior is verified on the native executable.

## 17. Conclusion

Testing resources, resource bundles, and proxies requires verifying both **registered metadata** and **actual behavior**. `RuntimeHintsPredicates.resource()` checks resource paths and bundle base names; `RuntimeHintsPredicates.proxies()` checks interface combinations. For JDK proxies, the interface order must match the runtime proxy. For resource bundles, use the proper base name and test locales explicitly.

Registrar unit tests help catch declaration mistakes early, but only native integration tests confirm that Spring AOT collected the metadata and the executable can use the resources/proxies. Use the same fixtures, test every important locale/interface combination, and run inside the target runtime container before releasing.

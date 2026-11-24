# Convention for Locating Editor Classes by Target Type Name in Spring Framework

In the **JavaBeans PropertyEditor** mechanism, each Java data type can have an **editor** class dedicated to converting between a text representation and an object of that type. Instead of having to register an editor for every single case, JavaBeans defines a naming convention to locate an editor class based on the **name of the target type**. Spring Framework supports and uses this JavaBeans infrastructure when handling many bean configuration and data binding scenarios.

The easiest rule to remember:

> If the data type is `com.example.domain.TicketCode`, then `com.example.domain.TicketCodeEditor`, in the **same package** and named **type name + `Editor`**, can be discovered automatically by JavaBeans without manually registering the editor name.

That convention **does not** mean every class ending in `Editor` is automatically used by Spring MVC/JSON, it is not a component-scan mechanism, and it does not replace all modern conversion paths such as `ConversionService`.

## 1. Why Locate a PropertyEditor?

A property has a concrete Java type, yet the data source may be a String:

~~~text
application property / XML bean definition / form parameter
                         |
                         v
                 "tkt-007"  (String)
                         |
                         v
            Select editor for TicketCode
                         |
                         v
               TicketCodeEditor
                         |
                         v
               TicketCode("TKT-007")
                         |
                         v
             property of type TicketCode
~~~

The `java.beans.PropertyEditor` interface describes the ability to manipulate a value and its text representation. In real-world code, you usually extend `java.beans.PropertyEditorSupport` and override:

- `setAsText(String)`: parses text into a value of the target type, typically calling `setValue(...)`.
- `getAsText()`: outputs the current value as a String.
- `getValue()` / `setValue(Object)`: reads/writes the value held by the editor.

Editors are **stateful**: the current value lives inside the editor instance. Therefore, do not take a mutable instance and use it concurrently across multiple requests/threads. When registering via a factory/registrar, provide a fresh instance for each appropriate binding pass.

In Spring, `BeanWrapperImpl` and `DataBinder` can use `PropertyEditor`. However, **finding an editor class** and **a Spring subsystem choosing to use that editor** are two distinct steps.

## 2. Lookup Order of `PropertyEditorManager`

JavaBeans provides `java.beans.PropertyEditorManager` in JDK module `java.desktop`, with the method:

~~~java
PropertyEditor editor = PropertyEditorManager.findEditor(TargetType.class);
~~~

According to the Java SE 17 API, the manager applies three techniques in order:

| Order | Lookup mechanism | Example for `com.example.domain.TicketCode` |
| --- | --- | --- |
| 1 | Explicitly registered editor via `registerEditor(targetType, editorClass)` | Editor class registered for `TicketCode.class` |
| 2 | Take the **fully qualified class name** of the target type and append suffix `Editor` | `com.example.domain.TicketCodeEditor` |
| 3 | Take the **simple class name** plus `Editor` and search packages in the **editor search path** | `com.example.editors.TicketCodeEditor` if `com.example.editors` is in the search path |

If no matching editor is found, `findEditor(...)` can return **`null`**. This is not a guarantee that every type can convert itself automatically.

### 2.1. The same-package rule is the most common case

With the structure:

~~~text
src/main/java/
  com/example/domain/
    TicketCode.java
    TicketCodeEditor.java
~~~

JavaBeans can find `com.example.domain.TicketCodeEditor` for `TicketCode.class`. You do not need to write a single line of `PropertyEditorManager.registerEditor(...)` in this case, provided the editor class is valid, can be loaded/instantiated, sits on the appropriate classpath/module path, and encounters no module-encapsulation obstacles.

Precisely put: **the editor lives next to the type it edits**, not necessarily next to the class using that type. If `OrderForm` is in `com.example.web` while property `code` has type `com.example.domain.TicketCode`, the name-based lookup path is `com.example.domain.TicketCodeEditor`, **not** `com.example.web.TicketCodeEditor`.

The name must match including the suffix:

- `TicketCode` -> `TicketCodeEditor`.
- `CustomerId` -> `CustomerIdEditor`.
- `MoneyAmount` -> `MoneyAmountEditor`.

Names like `TicketCodeConverter`, `TicketCodePropertyEditor`, or `CodeEditor` **do not match by default** under the `TicketCodeEditor` rule, though those classes can still work if explicitly registered via the corresponding mechanism.

### 2.2. Explicit registration takes precedence

You can bypass the same-package rule by declaring:

~~~java
PropertyEditorManager.registerEditor(
        TicketCode.class, TicketCodeEditor.class);
~~~

`registerEditor` takes **the target type's class and the editor's class**, not a pre-built editor instance. Subsequent `findEditor(...)` lookups prioritize registered entries before trying name guessing. You can unregister by passing `null` as `editorClass` per the JavaBeans API.

Note: `PropertyEditorManager` manages registrations/search paths at the runtime's JavaBeans mechanism scope, which is not equivalent to a controller-scoped bean. Avoid making global modifications inside request handlers. Tests sharing a JVM must also avoid polluting each other's registration state.

### 2.3. Searching in the editor search path

If the editor is placed in a separate package:

~~~text
src/main/java/
  com/example/domain/TicketCode.java
  com/example/editors/TicketCodeEditor.java
~~~

and this class is not in the same package as the target type, it can still be found via the search path:

~~~java
String[] original = PropertyEditorManager.getEditorSearchPath();
PropertyEditorManager.setEditorSearchPath(
        new String[] { "com.example.editors" });
~~~

Then `findEditor(TicketCode.class)` can locate `com.example.editors.TicketCodeEditor` in the third step.

**Important:** `setEditorSearchPath(...)` **replaces the entire current list**; it does not append a package to the existing list. If you want to preserve previous paths, construct a new array containing the original elements plus the needed package. The default list is **JDK-implementation dependent**; do not hardcode or depend on internal `sun.*` packages as a stable application API.

In modern Spring projects, it is usually easier to track if editors are registered on the specific `DataBinder`, `BeanWrapper`, or container instead of modifying the JVM-wide search path.

## 3. Runnable Java 17+ Example Without Spring

This example directly verifies the **JavaBeans rule**, avoiding confusion between auto-discovery and Spring's default registered editors. Create **three files** with the exact names and packages below.

### 3.1. Data type: `TicketCode`

File `src/main/java/com/example/domain/TicketCode.java`:

~~~java
package com.example.domain;

public record TicketCode(String value) {

    public TicketCode {
        if (value == null || !value.matches("TKT-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "Ticket code must match TKT-nnn");
        }
    }
}
~~~

`TicketCode` is a Java record with immutable format invariants. The `TicketCodeEditor` naming convention does not depend on the target type being a JavaBean with setters: the manager looks up the editor using the **target type's `Class`**.

### 3.2. Same-package editor: `TicketCodeEditor`

File `src/main/java/com/example/domain/TicketCodeEditor.java`:

~~~java
package com.example.domain;

import java.beans.PropertyEditorSupport;
import java.util.Locale;

public final class TicketCodeEditor extends PropertyEditorSupport {

    public TicketCodeEditor() {
    }

    @Override
    public void setAsText(String text) {
        if (text == null || text.isBlank()) {
            setValue(null);
            return;
        }
        String normalized = text.strip().toUpperCase(Locale.ROOT);
        setValue(new TicketCode(normalized));
    }

    @Override
    public String getAsText() {
        TicketCode code = (TicketCode) getValue();
        return code == null ? "" : code.value();
    }
}
~~~

The editor is in the **same package** as `TicketCode`, named **exactly** `TicketCodeEditor`, is a public class, and has a **public no-argument constructor**. These conditions let JavaBeans infrastructure instantiate it once found.

Conversion rules in the example:

- `" tkt-007 "` -> `TicketCode("TKT-007")`.
- `"TKT-007"` -> `TicketCode("TKT-007")`.
- `null` or whitespace-only string -> `null`.
- `"bad"` -> `IllegalArgumentException` from `TicketCode`'s constructor.

Using `Locale.ROOT` for technical identifiers ensures uppercase conversion does not depend on the machine's default locale. For display data depending on language/region, consider using a `Locale`-aware formatter rather than applying this normalization policy to every String.

### 3.3. Main: looking up and calling the editor with `PropertyEditorManager`

File `src/main/java/com/example/app/EditorLookupDemo.java`:

~~~java
package com.example.app;

import java.beans.PropertyEditor;
import java.beans.PropertyEditorManager;
import com.example.domain.TicketCode;
import com.example.domain.TicketCodeEditor;

public final class EditorLookupDemo {

    public static void main(String[] args) {
        // Do not register an editor before the first findEditor call.
        PropertyEditor editor =
                PropertyEditorManager.findEditor(TicketCode.class);

        if (editor == null) {
            throw new IllegalStateException("No editor for TicketCode");
        }

        System.out.println("automatic: "
                + editor.getClass().getSimpleName());

        editor.setAsText(" tkt-007 ");
        TicketCode code = (TicketCode) editor.getValue();

        System.out.println("value: " + code.value());
        System.out.println("text: " + editor.getAsText());

        // Explicit registration: an alternative way to declare an editor.
        PropertyEditorManager.registerEditor(
                TicketCode.class, TicketCodeEditor.class);

        PropertyEditor registered =
                PropertyEditorManager.findEditor(TicketCode.class);

        System.out.println("registered: "
                + registered.getClass().getSimpleName());
    }
}
~~~

Run on Linux/macOS from the project root directory:

~~~bash
mkdir -p out
javac -d out src/main/java/com/example/domain/TicketCode.java src/main/java/com/example/domain/TicketCodeEditor.java src/main/java/com/example/app/EditorLookupDemo.java
java -cp out com.example.app.EditorLookupDemo
~~~

On Windows PowerShell, create the directory first with:

~~~powershell
New-Item -ItemType Directory -Force out
~~~

The `javac -d ...` and `java -cp ...` commands work identically once JDK 17+ is on PATH.

Expected stdout:

~~~text
automatic: TicketCodeEditor
value: TKT-007
text: TKT-007
registered: TicketCodeEditor
~~~

The `automatic` line proves the **same-package name lookup** mechanism, since no explicit registration had occurred yet at the start. The `registered` line illustrates class registration at the highest priority step.

The files have matching imports and are self-contained; no Spring dependency is needed. If you try renaming the file to `TicketCodeConverter.java` or moving the editor to another package without configuring the search path, `findEditor(TicketCode.class)` can return `null`. **Create a separate test** when testing mismatched names rather than altering the standard example code and treating it as Spring's default behavior.

## 4. Where Does Spring Use This Convention?

Spring Framework includes JavaBeans infrastructure `BeanWrapperImpl` and `PropertyEditorRegistry` to read/write properties and apply conversions when needed. Spring provides **many built-in editors** such as editors for numbers, locales, URLs, or classes, and can fall back to JavaBeans editor discovery for types without a matching rule.

However, distinct scopes exist:

| Usage point | Where an editor can come from | Keep in mind |
| --- | --- | --- |
| Direct JavaBeans | `PropertyEditorManager.findEditor(T.class)` | Name lookup rules defined by JavaBeans |
| `BeanWrapperImpl` | Built-in editors, custom editors, Spring conversion infra, and JavaBeans mechanisms as appropriate | Specific editors can be registered on the wrapper |
| `DataBinder` / `WebDataBinder` | Default editors, binder-registered editors, configured converters/formatters | Must test on the actual binding path |
| `BeanFactory` / `ApplicationContext` | Built-in editors, custom editor configurers/registrars, and JavaBeans mechanisms | Does not imply every controller uses one editor instance |
| `@RequestBody` JSON | Usually `HttpMessageConverter` + Jackson | Does not automatically use `TicketCodeEditor` merely due to naming convention |

Spring documentation explicitly mentions JavaBeans discovery of editor classes in the same package with the `Editor` suffix. Still, never assume **every subsystem** goes through `PropertyEditorManager` identically. For instance, having a `ConversionService` bean does not mean JSON request bodies invoke `PropertyEditor.setAsText()`.

A stable design approach: use this convention when explaining JavaBeans mechanics, and **explicitly register editors at the Spring boundary where they apply** when that behavior is part of the application contract.

## 5. Spring Example: Registering Editors on BeanWrapper and DataBinder

When an editor must apply in a well-defined binding flow, Spring allows **direct registration**. This makes clear where the rule is active and avoids relying on JVM-wide search paths.

Keep the three Java files from section 3, then add `src/main/java/com/example/app/SpringBindingDemo.java`:

~~~java
package com.example.app;

import java.util.Map;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import com.example.domain.TicketCode;
import com.example.domain.TicketCodeEditor;

public final class SpringBindingDemo {

    public static final class TicketForm {
        private TicketCode code;

        public TicketCode getCode() {
            return code;
        }

        public void setCode(TicketCode code) {
            this.code = code;
        }
    }

    public static void main(String[] args) {
        TicketForm form1 = new TicketForm();
        BeanWrapper wrapper = new BeanWrapperImpl(form1);

        // Explicitly register the editor for type TicketCode.
        wrapper.registerCustomEditor(
                TicketCode.class, new TicketCodeEditor());
        wrapper.setPropertyValue("code", " tkt-008 ");

        System.out.println("wrapper: " + form1.getCode().value());

        TicketForm form2 = new TicketForm();
        DataBinder binder = new DataBinder(form2, "ticketForm");

        binder.registerCustomEditor(
                TicketCode.class, new TicketCodeEditor());
        binder.setAllowedFields("code");
        binder.bind(new MutablePropertyValues(
                Map.of("code", " tkt-009 ")));

        System.out.println("binder: " + form2.getCode().value());
        System.out.println("errors: "
                + binder.getBindingResult().hasErrors());
    }
}
~~~

Create `settings.gradle`:

~~~groovy
rootProject.name = 'spring-editor-lookup-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
}

application {
    mainClass = 'com.example.app.SpringBindingDemo'
}
~~~

Here `spring-context` brings in required Spring modules like `spring-beans`; version `6.2.0` is a concrete choice for the Java 17 example. Real-world projects should manage Spring versions uniformly via a BOM or Spring Boot dependency management to avoid mixing versions.

Run from the root directory:

~~~bash
./gradlew run
~~~

If no Gradle Wrapper exists, use a compatible installed Gradle with `gradle run`. On Windows with wrapper:

~~~powershell
.\gradlew.bat run
~~~

Excluding Gradle logs, expected stdout:

~~~text
wrapper: TKT-008
binder: TKT-009
errors: false
~~~

Unlike the JavaBeans example in section 3, here both `BeanWrapper` and `DataBinder` receive **explicit type-based editor registration** via `registerCustomEditor(TicketCode.class, ...)`. This approach does not depend on name-based auto-discovery to complete binding.

### Distinguishing two registration styles

- `PropertyEditorManager.registerEditor(TicketCode.class, TicketCodeEditor.class)`: registers the **editor class** in the JavaBeans mechanism and affects how the manager looks up editors.
- `binder.registerCustomEditor(TicketCode.class, new TicketCodeEditor())`: attaches an **editor instance** to a **specific binder**. It does not turn that editor into an application-wide setting.

Because `PropertyEditorSupport` can store a mutable value, with multiple independent binders instantiate a fresh editor per binder or register via a `PropertyEditorRegistrar` that creates fresh editors per registry.

### Recording type conversion errors

If the binder is invoked with `"bad"` instead of `" tkt-009 "`, `TicketCode` throws `IllegalArgumentException` from its constructor. In standard binding flows, Spring can record a `FieldError` in `BindingResult` (typically base code `typeMismatch`). Controllers must handle errors cleanly and never leak editor stack traces to clients.

Conversely, when using `BeanWrapper.setPropertyValue(...)` directly, conversion errors are not automatically wrapped into an HTTP response; the code calling the wrapper must handle the exception appropriately.

An editor running successfully only proves a `TicketCode` can be built from text; it does not prove that ticket code exists in the database or that the caller is authorized to view/edit the ticket.

## 6. Other Ways to Register Custom Editors in Spring

### 6.1. `@InitBinder`: Spring MVC scope

Inside a controller or `@ControllerAdvice`, you can declare:

~~~java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder
public void configureBinder(WebDataBinder binder) {
    binder.registerCustomEditor(
            TicketCode.class, new TicketCodeEditor());
}
~~~

This is an **illustrative method snippet**; it must sit inside a valid controller/advice and import `TicketCode` and `TicketCodeEditor`. `@InitBinder` applies to binding within the corresponding MVC scope, not to `@RequestBody` JSON in general.

If an endpoint accepts `@ModelAttribute` or `@RequestParam` of type `TicketCode`, Spring MVC may need conversion according to the endpoint's resolver/binder setup. Always test in practice since handling differs across argument types and configured converters/formatters.

For untrusted form requests, editors must not decide which properties the caller may modify. Use explicit DTOs, `setAllowedFields(...)` for property binding, and enforce authorization in the application layer.

### 6.2. `PropertyEditorRegistrar`: grouping multiple editors

Instead of scattering registrations across multiple places, create a reusable registrar:

~~~java
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;

public final class DomainEditorRegistrar
        implements PropertyEditorRegistrar {

    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
                TicketCode.class, new TicketCodeEditor());
    }
}
~~~

The snippet above is **an illustrative class** that belongs in an appropriate package with `TicketCode`/`TicketCodeEditor` imported. Key point: `registerCustomEditors(...)` **creates a new editor** for the passed-in registry, rather than reusing a mutable singleton instance. The same registrar can be used by multiple binders/bean factories if integrated accordingly.

One way to use it with `DataBinder`:

~~~java
DataBinder binder = new DataBinder(target, "ticketForm");
new DomainEditorRegistrar().registerCustomEditors(binder);
~~~

This snippet needs a valid `target` variable and the corresponding `DataBinder` imports. Since `DataBinder` implements `PropertyEditorRegistry`, the registrar can register editors directly. When used inside a container, the registrar can be wired into the bean factory's editor configuration mechanism.

### 6.3. `CustomEditorConfigurer`: registering for BeanFactory

Spring provides `org.springframework.beans.factory.config.CustomEditorConfigurer`, a `BeanFactoryPostProcessor` to configure custom property editors or registrars for the container. Illustrative configuration:

~~~java
@Bean
public static CustomEditorConfigurer customEditorConfigurer() {
    CustomEditorConfigurer configurer = new CustomEditorConfigurer();
    configurer.setPropertyEditorRegistrars(
            new PropertyEditorRegistrar[] {
                    new DomainEditorRegistrar()
            });
    return configurer;
}
~~~

This snippet must sit inside a `@Configuration` class; add imports for `Bean`, `CustomEditorConfigurer`, `PropertyEditorRegistrar`, and your registrar. Declaring `static @Bean` is appropriate for a BeanFactoryPostProcessor to avoid inadvertently instantiating configuration classes too early. It applies to BeanFactory property resolution; it **does not automatically** become a rule for all MVC requests or Jackson.

When you only need to normalize one field in one controller, `@InitBinder` or an appropriate converter can be simpler than configuring the entire BeanFactory.

### 6.4. `BeanInfo`: declaring an editor for a specific property

JavaBeans also has `BeanInfo`/`PropertyDescriptor` metadata. Rather than letting the manager look up an editor by **type**, a bean can designate an editor for a **specific property** via JavaBeans metadata, for example via `PropertyDescriptor.setPropertyEditorClass(...)` or an equivalent mechanism.

This is a separate path for choosing an editor; **do not confuse it** with auto-discovering `TicketCodeEditor` from the `TicketCode` class name. In modern Spring applications, registries or type converters are usually easier to verify than building custom BeanInfo per property.

## 7. Distinguishing PropertyEditor and ConversionService/Formatter

When learning PropertyEditor, it helps to understand why Spring introduced modern conversion mechanisms:

| Aspect | JavaBeans `PropertyEditor` | Spring `Converter<S,T>` | Spring `Formatter<T>` |
| --- | --- | --- | --- |
| Model | Mutable editor holding current value; typically text <-> object | Type-conversion function for a source/target pair | Parse/print with `Locale` context |
| Common API | `setAsText`, `getAsText`, `getValue` | `convert(source)` | `parse(text, locale)`, `print(object, locale)` |
| Registration | Manager naming/registry, `@InitBinder`, registrar, configurer | `ConversionService` / `ConverterRegistry` | `FormattingConversionService` / `FormatterRegistry` |
| Scope | Depends on where editor is discovered or registered | Wherever that service is used | Wherever that formatting service is used |
| Thread-safety | Avoid sharing stateful instances | Typically written as stateless converters | Formatters should be stateless or concurrency-safe |
| Best fit | JavaBeans/legacy binding compatibility, container config | Shared type conversion across code and binders | Locale-dependent dates, numbers, currency |

Example `Converter<String, TicketCode>`:

~~~java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToTicketCodeConverter
        implements Converter<String, TicketCode> {

    @Override
    public TicketCode convert(String source) {
        return new TicketCode(
                source.strip().toUpperCase(Locale.ROOT));
    }
}
~~~

This snippet is **for separate illustration**, requiring `TicketCode` to be imported; it is not a standalone runnable file and only takes effect when registered on a `ConversionService` used by the processing pipeline. The name `StringToTicketCodeConverter` **does not** follow the JavaBeans `TicketCodeEditor` convention and is not automatically discovered by `PropertyEditorManager.findEditor(TicketCode.class)`.

For modern Spring MVC, `ConversionService` and `FormatterRegistry` are usually the natural choice for type conversion and formatting; `PropertyEditor` remains useful in legacy JavaBeans or when binding-specific customization is required.

**Do not conflate them:** Jackson `@RequestBody` JSON, Spring `@ConfigurationProperties`, MVC form binding, and BeanFactory may use **different conversion systems**. Registering an editor via naming convention does not automatically affect all of them.

## 8. Common Errors When an Editor Class Is Not Found

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `findEditor(TicketCode.class) == null` | Wrong editor name or different package | Check fully qualified names of both classes |
| Editor named `TicketCodeConverter` | Suffix is not `Editor` | Rename per convention or register explicitly |
| Editor in `com.example.editors` | Different package and search path lacks that package | Inspect `getEditorSearchPath()` or register explicitly |
| Editor class exists yet fails instantiation | Unsuitable constructor/accessibility/module packaging | Verify `public` class, no-arg constructor, module exports/opens if using JPMS |
| `setAsText(...)` performs no conversion | Forgot to override or forgot `setValue(...)` | Check implementation and unit tests |
| `getAsText()` returns unexpected output | Desired text format not defined | Override `getAsText()` and test round-trip |
| Spring ignores editor even though `findEditor(...)` works | Binding path uses a different conversion service/JSON handler or registry | Test against actual `BeanWrapper`/`DataBinder`/MVC |
| Same code behaves differently between tests and server | Different classloader/module/JDK; global registration affected by another test | Check runtime classpath and avoid mutating global manager in shared tests |
| Invalid input crashes request | `setAsText` throws valid exception | Return clear binding/validation error without leaking stack traces |
| Editor behaves inconsistently across requests | Mutable editor shared | Instantiate fresh instance per registry/request/binding lifecycle |

### 8.1. Ordered diagnosis

1. Read `targetType.getName()` and `targetType.getSimpleName()` to see which type Spring/JavaBeans is handling.
2. Verify the expected full name: `com.example.domain.TicketCodeEditor`.
3. Verify the editor actually exists on the classpath/JAR, has an accessible no-arg constructor, and implements `PropertyEditor`.
4. Call `PropertyEditorManager.findEditor(TicketCode.class)` in a minimal JDK test without mixing in Spring issues.
5. If the editor is in another package, check `getEditorSearchPath()`—yet prefer explicit registration over mutating runtime-wide search paths.
6. If JavaBeans finds it but Spring fails to bind, inspect the **actual binder** and conversion mechanism used by that endpoint.
7. Test valid input, empty string, null, malformed input, concurrent requests, and `setAsText/getAsText` round-trip.
8. Pick the narrowest sufficient registration scope; never mutate the global manager inside request-handling code.

### 8.2. Subtle mistakes

**Mistake 1: placing the editor in the controller's package.**  
JavaBeans looks in the **target data type's package**, not the controller's package or the enclosing property owner's package.

**Mistake 2: renaming the data type while forgetting the editor name.**  
If `TicketCode` is renamed to `IssueCode`, the old editor class `TicketCodeEditor` no longer matches `IssueCode`'s convention. Rename the editor or register it for the new type.

**Mistake 3: assuming proper naming guarantees every Spring API will invoke it.**  
The JavaBeans convention only applies when editor lookup is invoked. For JSON bodies, a Jackson deserializer may need separate configuration. For ConversionService, a converter must be registered separately.

**Mistake 4: sharing a singleton PropertyEditorSupport.**  
Editors store values via `setValue/getValue`; if one editor instance handles two interleaved requests, they can overwrite each other's state. Use a registrar and create fresh editors in the proper lifecycle.

**Mistake 5: putting business logic inside the editor.**  
Editors are meant for parse/format, not querying databases or authorizing ticket codes. Existence, permissions, and business limits belong to domain/service/authorization layers.

## 9. Testing Practices

A JavaBeans unit test can verify lookup directly:

~~~java
PropertyEditor editor =
        PropertyEditorManager.findEditor(TicketCode.class);

assertNotNull(editor);
editor.setAsText(" tkt-007 ");
assertEquals(new TicketCode("TKT-007"), editor.getValue());
assertEquals("TKT-007", editor.getAsText());
~~~

This is an **illustrative JUnit snippet**, requiring imports for `java.beans.PropertyEditor`, `PropertyEditorManager`, `TicketCode`, and static `Assertions`. With Gradle/Maven, JUnit is required; meanwhile, the plain Java program in section 3 verifies behavior without JUnit.

A Spring integration test should also cover:

- Binding `TicketForm.code` from a String in `BeanWrapperImpl` or `DataBinder` after editor registration.
- Invalid input recording a proper binding error instead of turning bad input into an arbitrary object.
- Two binders receiving **two distinct editor instances** when built via a registrar.
- Actual controller receiving form/query data and returning the expected response, especially alongside another `ConversionService`.
- Ensuring editor rules do not inadvertently apply to JSON bodies or out-of-scope requests.

When refactoring package names or data types, a test calling `PropertyEditorManager.findEditor(...)` catches broken naming conventions earlier than waiting for a real request to fail.

## 10. Adoption Checklist and Self-Check Questions

**Checklist:**

- Editor class name = **target type simple name + `Editor`** in the same package if relying on the common JavaBeans auto-discovery convention.
- Editor class is public, has an accessible no-arg constructor, and implements `PropertyEditor` (usually via `PropertyEditorSupport`).
- Test `setAsText/getAsText`, null, bad input, and error messages.
- If the editor is in a different package, choose explicit registration or controlled search paths.
- Do not confuse global `PropertyEditorManager.registerEditor` with per-binder `PropertyEditorRegistry.registerCustomEditor`.
- Never reuse mutable editor instances across multiple requests; use registrars/factories to create instances as needed.
- Test the actual Spring processing path rather than inferring MVC or JSON uses the editor solely from its class name.
- Choose `Converter`/`Formatter` for suitable new type conversion needs; use editors when JavaBeans/legacy compatibility is required.
- Separate parsing, validation, and authorization; keep business I/O out of editors.

**Questions:**

1. For type `com.myapp.money.Amount`, what same-package editor class name does JavaBeans look for?
2. If the editor is placed in `com.myapp.editors`, what mechanism allows `findEditor(Amount.class)` to locate it?
3. Among `PropertyEditorManager`'s three lookup strategies, which has the highest priority?
4. Why does `AmountPropertyEditor` not match automatically when the type is `Amount`?
5. What is the difference between registering an editor class via `PropertyEditorManager.registerEditor` and an editor instance via `DataBinder.registerCustomEditor`?
6. When should you use `PropertyEditorRegistrar` instead of holding a singleton editor?
7. Why might `@RequestBody` JSON ignore an `AmountEditor` even if JavaBeans finds it?
8. Does a `PropertyEditor` returning a properly typed object guarantee the data is valid under business rules?

**Conclusion:** The convention for locating editor classes by target type name is a **JavaBeans** mechanism: prioritizing explicitly registered editors, next searching **`<FullyQualifiedTargetType>Editor`**, and finally searching **`<SimpleTargetType>Editor`** across packages in the search path. In Spring, this underpins `PropertyEditor`, yet reliable usage requires understanding `BeanWrapper`/`DataBinder`/container scopes and not conflating it with `ConversionService` or Jackson.

### References

- Java SE 17 — `PropertyEditorManager`: https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditorManager.html
- Java SE 17 — `PropertyEditor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditor.html
- Java SE 17 — `PropertyEditorSupport`: https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditorSupport.html
- Spring Framework — Data Binding, PropertyEditors and Custom PropertyEditors: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework — Type Conversion / Converter: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework — Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html

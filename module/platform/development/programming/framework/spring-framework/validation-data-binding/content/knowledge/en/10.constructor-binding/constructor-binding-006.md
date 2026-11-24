# Role of the `-parameters` Compiler Option When Spring Binds Data via Constructors

In Java, source code can declare a constructor `RegistrationForm(String username, Integer age)`, yet the names `username` and `age` **do not necessarily survive in metadata readable by Java Reflection after compilation**. By default, the Java compiler may only retain parameter types and positions. For regular code compiled without `-parameters`, Reflection typically sees synthetic names like `arg0`, `arg1`.

The **Java compiler** option `javac -parameters` instructs the compiler to store **actual method and constructor parameter names in bytecode** so frameworks can retrieve them at runtime. This is especially important for **constructor binding** in Spring: Spring needs to match constructor parameter names with input data names such as `username=Mai&age=21`. Without proper names or another explicit naming mechanism, instantiating objects from requests may not work as expected.

**Core point:** `-parameters` helps Spring *know which parameter receives which data*. It **does not perform type conversion, validate data, generate constructors, grant field-modification permissions, or replace binding configuration**.

## 1. From Names in Java Code to Data Needed for Constructor Binding

Suppose an immutable DTO:

~~~java
public final class RegistrationForm {
    private final String username;
    private final Integer age;

    public RegistrationForm(String username, Integer age) {
        this.username = username;
        this.age = age;
    }

    public String getUsername() {
        return username;
    }

    public Integer getAge() {
        return age;
    }
}
~~~

For an HTTP request:

~~~http
GET /registrations/preview?username=Mai&age=21 HTTP/1.1
Host: localhost:8080
~~~

Spring MVC may need to follow this sequence:

~~~text
Request values
  username = "Mai"
  age      = "21"
        |
        v
Discover constructor RegistrationForm(String username, Integer age)
        |
        v
Read each parameter name: "username", "age"
        |
        v
Look up input values by name
        |
        v
Convert "21" from String to Integer via conversion mechanism
        |
        v
new RegistrationForm("Mai", 21)
        |
        v
Apply validation if configured/triggered
        |
        v
Controller receives RegistrationForm
~~~

Here there are **three separate tasks**:

1. **Discovering names:** `username`, `age` on the constructor. `-parameters` can supply them.
2. **Binding and conversion:** finding `username=...`, `age=...`; converting input values to the required Java types.
3. **Validation:** checking constraints such as minimum age or non-blank name, if a validator is configured and triggered.

Having a field named `age` is **not enough** for constructor Reflection to infer the `Integer age` parameter automatically. Field names and **constructor parameter names** are two distinct kinds of metadata.

## 2. What Does `-parameters` Do in `.class` Files?

The `-parameters` option was introduced in Java 8. During compilation, it tells `javac` to emit the **`MethodParameters`** class-file attribute (when applicable) containing names and certain metadata for method/constructor parameters. Java Reflection accesses it via:

~~~java
Constructor<?> ctor = MyType.class.getDeclaredConstructors()[0];
Parameter[] parameters = ctor.getParameters();

for (Parameter parameter : parameters) {
    System.out.println(parameter.getName());
    System.out.println(parameter.isNamePresent());
}
~~~

This is an **illustrative snippet**, requiring imports for `java.lang.reflect.Constructor`, `java.lang.reflect.Parameter` and an appropriate `MyType`; section 3 provides a standalone runnable program.

Two key APIs:

- `Parameter.getName()` returns the name seen by Reflection. If no real name is stored, Java can synthesize names such as `arg0`.
- `Parameter.isNamePresent()` indicates whether real name metadata is available via Reflection. If `false`, **do not** treat `getName()` as part of a request contract.

Comparison table:

| Aspect | `-parameters` | `-g` / debug symbols |
| --- | --- | --- |
| Primary metadata | `MethodParameters` | `LineNumberTable`, `LocalVariableTable`, and related debug info |
| Purpose | Preserve parameter names for Reflection/frameworks | Support debuggers, source mapping, and local variables |
| `Parameter.isNamePresent()` for regular Java classes | Can be `true` | Not guaranteed |
| Viability for Spring Framework 6.1+ | Right approach when parameter names are needed | **Does not replace** `-parameters` |

**Why emphasize Spring 6.1?** `LocalVariableTableParameterNameDiscoverer` was removed in Spring Framework 6.1. Spring no longer relies on parsing the bytecode Local Variable Table to guess Java parameter names. Standard Reflection-based mechanisms, such as `StandardReflectionParameterNameDiscoverer`, require accessible metadata; typically that comes from compiling with `-parameters`.

Do not confuse `-parameters` with a **JVM runtime** flag. It is an option for **`javac` at build time**, not an argument to `java` when starting the service. Passing flags on the startup command cannot restore metadata omitted from `.class` files.

## 3. Java 17+ Program Verifying with Reflection

This example uses the plain JDK; **no Spring, Gradle, or Maven is needed**. Create `ParameterNamesDemo.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public final class ParameterNamesDemo {

    public static final class RegistrationInput {
        private final String username;
        private final int age;

        public RegistrationInput(String username, int age) {
            this.username = username;
            this.age = age;
        }

        public String username() {
            return username;
        }

        public int age() {
            return age;
        }
    }

    public static void main(String[] args) throws Exception {
        Constructor<RegistrationInput> constructor =
                RegistrationInput.class.getDeclaredConstructor(
                        String.class, int.class);

        for (Parameter parameter : constructor.getParameters()) {
            System.out.println(parameter.getName()
                    + " / " + parameter.isNamePresent());
        }
    }
}
~~~

### 3.1. Compiling Without `-parameters`

On Linux/macOS, create output directories then compile/run:

~~~bash
mkdir -p out/plain out/named out/debug
javac -d out/plain ParameterNamesDemo.java
java -cp out/plain ParameterNamesDemo
~~~

Program stdout:

~~~text
arg0 / false
arg1 / false
~~~

The JVM still knows the constructor takes `String` then `int`, but Reflection does not know they are `username` and `age`.

### 3.2. Compiling With `-parameters`

~~~bash
javac -parameters -d out/named ParameterNamesDemo.java
java -cp out/named ParameterNamesDemo
~~~

Stdout:

~~~text
username / true
age / true
~~~

The Java methods and constructor logic did not change. The difference lies in bytecode metadata.

### 3.3. Enabling Only `-g` Is Not Equivalent

~~~bash
javac -g -d out/debug ParameterNamesDemo.java
java -cp out/debug ParameterNamesDemo
~~~

For this regular class example, stdout is still:

~~~text
arg0 / false
arg1 / false
~~~

Be sure to recompile into **separate directories** as shown above. Running a class from a stale output directory or a classpath mixed with other JARs can mislead verification.

On Windows PowerShell, replace the directory creation step with:

~~~powershell
New-Item -ItemType Directory -Force -Path out/plain,out/named,out/debug
~~~

The `javac -d ...` and `java -cp ...` commands still work in PowerShell when the JDK is on `PATH`.

This is direct evidence of `-parameters`'s role: same source code, same JDK, changing only the compiler flag alters the parameter names read by Reflection.

## 4. When Does Spring MVC Actually Use Those Names?

In Spring MVC, a controller method like:

~~~java
@GetMapping("/registrations/preview")
public RegistrationResponse preview(
        @ModelAttribute("registration") RegistrationForm form) {
    return new RegistrationResponse(
            form.getUsername(), form.getAge());
}
~~~

can ask Spring to build `RegistrationForm` from request data. If the model does not already contain a corresponding object, Spring can instantiate it via its **primary constructor** and use the discovered parameter names to read the required values. By default, Spring MVC supports both constructor binding and property binding during `@ModelAttribute` processing, though immutable objects without setters limit property-write paths.

When the input source is query/form parameters, path variables, or suitable headers, Spring can bind resolved values; source precedence and constructor selection depend on Spring MVC context. You cannot simply add `-parameters` and expect the framework to bind any request type into any constructor.

Missing metadata errors may surface as exceptions about failing to determine constructor parameter names, failing to instantiate a model attribute, or binding failures. **Exact messages and HTTP statuses depend on the Spring version, exception handlers, and where the failure occurs.** Inspect the actual `.class` files loaded at runtime instead of randomly tweaking response handlers.

### 4.1. Be Careful with JSON `@RequestBody`

With:

~~~java
@PostMapping("/registrations")
public void create(@RequestBody RegistrationForm form) {
    // ...
}
~~~

the processing path is different: an HTTP message converter, typically Jackson, deserializes JSON into the object. Jackson has its own mechanisms for constructors/records, `@JsonCreator`, `@JsonProperty`, and parameter-name support modules. **Spring MVC's `@ModelAttribute` constructor binding does not automatically apply in the same way to `@RequestBody`.** Building with `-parameters` can help certain libraries, yet it does not guarantee Jackson will instantiate every immutable type without proper configuration.

### 4.2. Do Not Confuse Constructor Binding with Constructor Injection

Both cases use constructors, but their meanings differ:

| Case | Constructor receives | What parameter names are used for |
| --- | --- | --- |
| `@ModelAttribute` constructor binding | Request/form data values | Matching parameter names to input field/parameter names |
| Spring bean constructor injection | Container-managed dependencies | Can assist resolution when multiple beans share a type or by-name wiring |
| `@ConfigurationProperties` constructor binding | Application configuration properties | Matching config keys to constructor parameters where applicable |
| `@RequestBody` JSON deserialization | JSON values decoded by message converter | Depends on deserializer strategy; not identical to `DataBinder` |

For dependency injection, if multiple beans of the same type exist, preserving constructor parameter names can assist certain by-name resolution rules; `@Qualifier` is the clearer approach when explicit selection is desired. For request constructor binding, names form part of the data mapping and must remain stable per the API contract.

## 5. Complete Spring Boot Example: Immutable Form Constructed via Constructor

This example uses Java 17 and Spring Boot 3.3.x / Spring Framework 6.1.x, explicitly declaring the Gradle compiler flag. This is a standalone application runnable once JDK/Gradle are set up.

Create `settings.gradle`:

~~~groovy
rootProject.name = 'parameters-binding-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

In some Spring Boot Gradle projects, the plugin already configures `-parameters` on `JavaCompile`. The explicit configuration line in this example clarifies the build contract; verify actual values on the compile tasks when a project uses multiple plugins or multi-module setups. Note that versions here are only for reproducibility; real projects should use versions aligned with their own stack.

Create `src/main/java/com/example/parameters/ParametersApplication.java`:

~~~java
package com.example.parameters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ParametersApplication {

    public static void main(String[] args) {
        SpringApplication.run(ParametersApplication.class, args);
    }
}
~~~

Create `src/main/java/com/example/parameters/RegistrationForm.java`:

~~~java
package com.example.parameters;

public final class RegistrationForm {
    private final String username;
    private final Integer age;

    public RegistrationForm(String username, Integer age) {
        this.username = username;
        this.age = age;
    }

    public String getUsername() {
        return username;
    }

    public Integer getAge() {
        return age;
    }
}
~~~

This is a DTO **immutable in field references/values**, with only a two-parameter constructor, **no no-arg constructor and no setters**. For Spring to create a new instance, it must resolve the constructor arguments.

Create `src/main/java/com/example/parameters/RegistrationController.java`:

~~~java
package com.example.parameters;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @GetMapping("/preview")
    public Map<String, Object> preview(
            @ModelAttribute("registration") RegistrationForm form) {

        return Map.of(
                "username", form.getUsername(),
                "age", form.getAge());
    }
}
~~~

Run the project if Gradle Wrapper is present:

~~~bash
./gradlew clean bootRun
~~~

Or on Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootRun
~~~

If no wrapper has been generated yet, use an installed compatible Gradle to run `gradle bootRun` or generate the wrapper first. Request:

~~~bash
curl --get --data-urlencode "username=Mai" --data-urlencode "age=21" http://localhost:8080/registrations/preview
~~~

Expected result: HTTP `200 OK`; JSON containing these two key-value pairs (JSON key order is not fixed):

~~~json
{
  "username": "Mai",
  "age": 21
}
~~~

Spring learns `username` and `age` from constructor metadata, retrieves the corresponding parameters, and converts `"21"` to `Integer`. The controller receives the already-created object. Being able to instantiate the object from the request **does not prove** the username is valid or the caller is authorized to create an account; the example only demonstrates constructor binding without business validation.

If `-parameters` is removed from the build and regular Java classes like `RegistrationForm` are cleanly recompiled with no alternative naming mechanism, resolving the two names can fail. **Do not rely on a single run when stale classes remain in the output directory**: clean/recompile, verify metadata, and test again.

## 6. Automated Testing of Both Metadata and HTTP Behavior

With the `spring-boot-starter-test` dependency in the example above, create `src/test/java/com/example/parameters/ParameterBindingTest.java`:

~~~java
package com.example.parameters;

import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ParameterBindingTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void constructorParametersRetainTheirNames() throws Exception {
        Constructor<RegistrationForm> ctor =
                RegistrationForm.class.getDeclaredConstructor(
                        String.class, Integer.class);

        Parameter[] params = ctor.getParameters();

        assertEquals(2, params.length);
        assertTrue(params[0].isNamePresent());
        assertTrue(params[1].isNamePresent());
        assertEquals("username", params[0].getName());
        assertEquals("age", params[1].getName());
    }

    @Test
    void mvcBindsFormThroughConstructor() throws Exception {
        mvc.perform(get("/registrations/preview")
                .param("username", "Mai")
                .param("age", "21"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("Mai"))
                .andExpect(jsonPath("$.age").value(21));
    }
}
~~~

Run:

~~~bash
./gradlew clean test
~~~

The first test confirms **the compiled class produced by the build** preserves parameter names for Reflection. The second test confirms **Spring MVC** actually binds values by name and invokes the controller. Both are necessary: having valid metadata alone does not guarantee complete MVC configuration, and a passing HTTP test alone does not prove every build preserves parameter names (especially if code changes to a record or explicit name declarations).

If a test fails due to missing names, inspect the compile task and loaded classes first. If a test fails due to conversion or validation, distinguish that from metadata errors and address the proper root cause layer.

## 7. Configuring `-parameters` Across Build Systems

### 7.1. Using `javac` Directly

~~~bash
javac -parameters -d out/classes src/main/java/com/example/parameters/RegistrationForm.java
~~~

Create `out/classes` beforehand if it does not exist. The flag applies to **that compilation invocation**. When a constructor is declared in module A while the application runs from module B, configure compilation on **module A** so metadata travels with A's classes.

### 7.2. Gradle Groovy DSL

In the `build.gradle` of the module containing bound classes:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
~~~

In multi-module projects, each Java module can have `compileJava`, `compileTestJava`, or custom compile tasks. Do not enable the flag only in the final runnable app if DTOs are compiled in a library submodule. With Java toolchains or custom compile tasks, verify the effective compiler args instead of only reading a root build script.

### 7.3. Gradle Kotlin DSL

In `build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Place the import at the top of the Gradle Kotlin DSL file. This flag targets **Java** compilation tasks; if using Kotlin sources, Kotlin compiler flags and Kotlin metadata require separate configuration/investigation.

### 7.4. Maven

In `pom.xml`, configure `maven-compiler-plugin` (plugin snippet inside `<build><plugins>`):

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Setting `<parameters>true</parameters>` corresponds to `javac -parameters`. When a project inherits from `spring-boot-starter-parent`, Spring Boot typically sets this default, but that does not guarantee every POM importing only a BOM or every submodule shares the same compiler configuration. Inspect the effective POM and built classes when troubleshooting.

### 7.5. IDEs, CI, and Final Artifacts

A very common failure is working locally in an IDE while failing in CI, or vice versa:

- The IDE may use its own compiler while CI invokes Gradle/Maven.
- Multi-module builds may compile DTO classes in another module/artifact.
- Incremental compilation optimizations can retain stale classes.
- Shading, obfuscation, AOT, or bytecode transformation steps can affect metadata; inspect the **final** JAR.
- Differences between test runtime and application runtime may stem from classpath picking up a different copy of a class.

Therefore, use a unified build pipeline, run clean builds when investigating, and verify parameter names via Reflection on **the actual runnable artifact**.

## 8. What If You Cannot Change Compiler Args?

Depending on the situation, you can supply name metadata explicitly. However, those approaches have specific scopes and are not equivalent to enabling `-parameters` for all methods.

### 8.1. `@BindParam` for Constructor Binding Input Names in Spring MVC

Suppose an external request sends key `user-name`, differing from the Java identifier `username`:

~~~java
import org.springframework.web.bind.annotation.BindParam;

public final class RegistrationForm {
    private final String username;
    private final Integer age;

    public RegistrationForm(
            @BindParam("user-name") String username,
            @BindParam("age") Integer age) {
        this.username = username;
        this.age = age;
    }

    public String getUsername() {
        return username;
    }

    public Integer getAge() {
        return age;
    }
}
~~~

This is an **alternative `RegistrationForm.java` implementation** for the MVC example, with the matching Spring Web MVC import; it must not sit alongside the old class of the same name. Requests can then use `user-name=Mai&age=21`. `@BindParam` specifies input keys; this annotation is particularly helpful when APIs use hyphens, snake_case, or stable external names differing from Java parameter names.

Enabling `-parameters` remains good practice for Spring Java projects. `@BindParam` describes **the naming contract of individual inputs**, whereas `-parameters` makes Java names broadly available to Reflection/frameworks.

### 8.2. `@ConstructorProperties` When Declaring Constructor Name Lists

Java provides `java.beans.ConstructorProperties`:

~~~java
import java.beans.ConstructorProperties;

public final class Coordinate {
    private final int x;
    private final int y;

    @ConstructorProperties({"x", "y"})
    public Coordinate(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int getX() {
        return x;
    }

    public int getY() {
        return y;
    }
}
~~~

Certain Spring/JavaBeans mechanisms read this annotation when resolving constructor parameter names. **Do not misunderstand:** `@ConstructorProperties` is explicit declarative metadata for a constructor; it **does not cause** `Parameter.isNamePresent()` to change from `false` to `true` if the class was still compiled by `javac` without `-parameters`. Verify the exact binding path before choosing an annotation as a substitute.

### 8.3. Annotated Method Arguments

In a controller, `@RequestParam("age") Integer age` or `@PathVariable("id") Long id` already declares the name for that argument binding mechanism. Those annotations **do not supply names for constructor parameters of a separate DTO**. Editing an `@RequestParam` in the controller will not fix missing metadata on `RegistrationForm(String username, Integer age)`.

### 8.4. Records and Kotlin

Java records, Kotlin primary constructors, and related annotations can rely on **separate metadata mechanisms**. They are not proof that every regular Java class retains parameter names. For Java classes inspected by Spring via Reflection, still enable `-parameters`; for Kotlin, configure and check the Kotlin compiler (such as `-java-parameters` when Java reflection interop is needed) and Kotlin reflection mechanisms per your framework. Do not mix Java `javac` flags with Kotlin compiler flags.

## 9. When Renaming Parameters, the API Contract Can Change Too

Suppose the constructor is currently:

~~~java
public RegistrationForm(String username, Integer age) { ... }
~~~

With `-parameters` enabled and Spring reading names directly from the constructor, the request key `username` binds properly. After refactoring to:

~~~java
public RegistrationForm(String loginName, Integer age) { ... }
~~~

parameter types and positions remain identical, yet the metadata has become `loginName`. Clients still sending `username` may no longer match. This is a **runtime contract behavior change**, even though the Java compiler reports no errors for HTTP clients.

When an API needs stable names:

1. Choose parameter names consistent with the input contract.
2. Use `@BindParam("username")` if external names must stay stable even when Java variable names change.
3. Write integration tests sending the exact keys clients use.
4. Evaluate backward compatibility just like renaming JSON/form fields.
5. Never bind sensitive client-supplied fields directly onto persistence entities.

**Security note:** `-parameters` only retains names and metadata; it does not prevent mass assignment. With `@ModelAttribute`, Spring can use both constructor and property binding by default. Use input DTOs containing only permitted fields, or restrict property binding with mechanisms like `allowedFields`/constructor-only binding when appropriate. Authorization and business invariant checks must occur at the proper layer.

## 10. Diagnosing Missing Parameter Name Issues

| Symptom | Cause to check | Verification step |
| --- | --- | --- |
| Spring reports unable to determine parameter names | Class lacks metadata or name resolution path mismatches | Run `Parameter.isNamePresent()` on the exact runtime class constructor |
| Runtime shows `arg0`, `arg1` | Regular Java bytecode lacks `MethodParameters` | Clean compile with `-parameters` |
| Enabled `-g` yet still failing | Debug info does not replace Reflection metadata | Switch to `-parameters` |
| Added compiler args with no effect | Stale build output, IDE/CI using different compiler | Clean build, check output/JAR and compile tasks |
| Only one module fails | DTO lives in a module without the flag or prebuilt dependency | Configure compilation in the module owning the class |
| Constructor has proper names yet binding still fails | Request key differs, missing converter, or wrong constructor | Compare keys, `@BindParam`, signatures, and ConversionService |
| Data binding succeeds, validation fails | Data constraint violations after object creation | Inspect validators and `BindingResult` |
| `@RequestBody` behaves differently from `@ModelAttribute` | Jackson uses its own deserialization mechanism | Check Jackson annotations/modules and message conversion |
| IDE works, CI JAR fails | Different compiler output or bytecode transformation | Compare actual artifacts, test metadata in CI |

A low-cost troubleshooting order:

~~~text
1. Identify the target type and the exact constructor Spring is using.
2. Identify the actual request keys (username, age, ...).
3. Run Reflection on the exact loaded class: getParameters(), isNamePresent().
4. If names are missing, check compiler args in the module owning the class.
5. Clean/recompile and inspect the new runtime artifact.
6. If names are present, investigate conversion, validation, allowed fields, and binding errors.
7. Write tests so the regression cannot return when build plugins or code change.
~~~

**Distinguish metadata errors from data errors:** if input `age="abc"` fails to convert to `Integer`, enabling `-parameters` will not fix it. If Spring does not know which Java parameter corresponds to key `age`, adding validators will not fix the root cause either. Check each stage in order.

## 11. Common Misconceptions

- **"Having a field `username` guarantees the constructor receives the `username` key."** No: to bind constructor arguments, Spring needs the constructor parameter name (or explicit naming metadata).
- **"Adding `-parameters` when running `java -jar` is enough."** False: it must be passed when compiling Java code.
- **"Compiling with `-g` already provides names for Reflection."** Not guaranteed; Spring 6.1+ no longer relies on `LocalVariableTableParameterNameDiscoverer`.
- **"Only the web module needs the flag."** False if target constructors reside in a separately built library module.
- **"`Parameter.getName()` is always the original name."** When `isNamePresent() == false`, names like `arg0` are merely synthetic placeholders.
- **"With `-parameters`, every `@RequestBody` JSON deserializes into immutable objects."** False: JSON converters use their own mechanisms.
- **"`-parameters` enables validation automatically."** False: validation requires validators/constraints and a trigger point.
- **"Refactoring parameter names never affects clients."** It can affect clients if Spring relies on parameter names to bind forms/queries.
- **"Data bound via constructors is automatically safe."** False: you must still restrict input fields, validate, and enforce permissions.
- **"Enabling `-parameters` adds parameter names to all dependency JARs."** No: each JAR carries bytecode from its own build.

## 12. Practice Questions

1. What metadata does `javac -parameters` emit and what does `Parameter.isNamePresent()` return?
2. Why does `javac -g` not replace `-parameters` for Spring Framework 6.1+?
3. In `RegistrationForm(String username, Integer age)`, what information does Spring need to match request `age=21` to the second argument?
4. If an external library class lacks parameter metadata, can adding the compiler flag to the consumer module fix the already-built JAR?
5. Why is `@ModelAttribute` constructor binding different from `@RequestBody` JSON deserialization?
6. When renaming `username` to `loginName`, how can you preserve the old input key?
7. Which test proves metadata is retained? Which test proves Spring MVC uses that metadata properly?
8. If metadata is present yet `age=abc` fails, which step should you investigate?
9. Why do immutable input DTOs still require validation and authorization?
10. In multi-module Gradle/Maven builds, where must the compiler configuration reside?

**Takeaway:** `-parameters` is part of the **Java bytecode build contract**: it preserves constructor/method parameter names so Spring can retrieve them via Reflection when needed. In constructor binding, this metadata connects **input name → constructor argument → Java object**. Configure it on the right module, recompile, verify metadata via Reflection, and confirm behavior with binding tests. Conversion, validation, authorization, and JSON formatting remain separate responsibilities.

### References

- Spring Framework — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework — `@ModelAttribute`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.1 Release Notes — Parameter Name Retention: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes
- Spring Boot — Gradle plugin reference: https://docs.spring.io/spring-boot/gradle-plugin/
- Spring Boot — Maven plugin configuration: https://docs.spring.io/spring-boot/maven-plugin/using.html
- Java SE — `java.lang.reflect.Parameter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html
- Java `javac` documentation: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html

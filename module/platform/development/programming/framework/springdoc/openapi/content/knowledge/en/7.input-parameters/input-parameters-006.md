# Role of the -parameters Compiler Option

When writing Spring Boot controllers, developers often declare parameters like **@RequestParam String keyword** or **@PathVariable UUID bookId** without specifying a name in the annotation. Spring can retrieve the name from the Java parameter if that name is stored in the **.class** file. The **-parameters** compiler option instructs the Java compiler to store parameter name metadata so reflection and frameworks like Spring can read it.

For **springdoc-openapi**, this metadata is also helpful when the library analyzes controller signatures to generate parameters in the OpenAPI specification. If parameter names are absent from bytecode and Spring MVC annotations do not declare explicit names, the application may fail to bind requests as intended or the documentation may show unhelpful names.

This article explains where **-parameters** operates, why it matters for Spring MVC and springdoc-openapi, how to enable it in Maven and Gradle, and how to verify **.class** files after compilation.

## 1. Parameter Names in Source Code and Bytecode

Consider a Java method:

~~~java
public class BookController {

    public void search(String keyword, int page) {
        // ...
    }
}
~~~

In source code, the names **keyword** and **page** are always present. After compilation, however, the **.class** file does not automatically store these names in a way readable by Java Reflection. Without parameter name metadata, reflection may only return generic names like **arg0** and **arg1**.

When compiled with **-parameters**, **javac** writes parameter name information into the **MethodParameters** attribute of the class file. Java Reflection can read that information via **java.lang.reflect.Parameter**.

~~~java
Method method = BookController.class.getMethod(
    "search",
    String.class,
    int.class
);

for (Parameter parameter : method.getParameters()) {
    System.out.printf(
        "name=%s, present=%s%n",
        parameter.getName(),
        parameter.isNamePresent()
    );
}
~~~

Typical output:

| Compilation Method | getName() | isNamePresent() |
|---|---|---|
| Without -parameters | arg0, arg1 | false |
| With -parameters | keyword, page | true |

**Parameter.isNamePresent()** is the direct way to check whether parameter names are available in reflection metadata. It is a more reliable indicator than merely seeing variable names in source code or debug logs.

### -parameters Differs from Debug Information

Java has compiler options serving different purposes:

- **-parameters** stores method and constructor parameter names for reflection.
- **-g** generates debugging information, such as line numbers and local variable info.
- **-g:vars** requests debugging information for local variables.

Local variable information in **LocalVariableTable** is not equivalent to the **MethodParameters** attribute. A framework using standard reflection cannot default to reading parameter names from debug info.

Specifically with Spring Framework 6.1 and later, do not rely on reading parameter names from **LocalVariableTable**: local-variable-table-based name discovery was removed after deprecation. Enable **-parameters** so Java parameter names are available to reflection.

## 2. Why Does Spring MVC Need Parameter Names?

Spring MVC must map HTTP data to controller method parameters. When an annotation does not explicitly specify a name, Spring may need to read the Java parameter name to know which value to extract.

Example:

~~~java
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping("/search")
    public List<BookResponse> search(
        @RequestParam String keyword,
        @RequestParam(defaultValue = "0") int page
    ) {
        // Search books by keyword and page
        return List.of();
    }

    @GetMapping("/{bookId}")
    public BookResponse findById(
        @PathVariable UUID bookId
    ) {
        // Find book by bookId
        return null;
    }
}
~~~

Spring needs to know:

- **keyword** comes from the query parameter named **keyword**.
- **page** comes from the query parameter named **page**.
- **bookId** comes from the path variable named **bookId**.

If annotations omit **name** or **value**, Spring can infer the name from parameter metadata. When names are unavailable, binding may fail with an error indicating that the parameter name was not specified and no name information was available via reflection.

For annotations that accept data by name, you can declare the name explicitly:

~~~java
@GetMapping("/search")
public List<BookResponse> search(
    @RequestParam(name = "keyword") String searchText,
    @RequestParam(name = "page", defaultValue = "0") int page
) {
    // ...
    return List.of();
}
~~~

In this case, Spring binds **searchText** from query key **keyword**. The Java variable name can differ from the HTTP parameter name because the annotation supplies an explicit name.

Common annotations with name attributes:

| Annotation | Name Declaration Attribute | Data Location |
|---|---|---|
| @RequestParam | name or value | Query string or form parameter |
| @PathVariable | name or value | Path segment |
| @RequestHeader | name or value | HTTP header |
| @CookieValue | name or value | Cookie |

**-parameters** allows Spring to infer names when annotations leave them blank. Explicitly declared names in annotations make the binding contract clear and less dependent on bytecode metadata.

## 3. Impact on springdoc-openapi

springdoc-openapi reads Spring MVC metadata, handler method signatures, and OpenAPI annotations to build operations and parameter lists. For a parameter declared as **@RequestParam String keyword**, the name **keyword** is essential to generate a parameter with **name: keyword** in OpenAPI.

Example of the expected specification:

~~~yaml
paths:
  /api/books/search:
    get:
      parameters:
        - name: keyword
          in: query
          required: true
          schema:
            type: string
        - name: page
          in: query
          required: false
          schema:
            type: integer
            format: int32
            default: 0
      responses:
        "200":
          description: List of books
~~~

When parameter name metadata is available, springdoc can generate meaningful parameter names. When metadata is missing and annotations do not supply names, inference results may fall short of expectations or analysis may error depending on version, parameter type, and configuration.

It is important to distinguish three roles:

- **-parameters** stores parameter names in bytecode so reflection and frameworks can read them.
- **@Parameter** from swagger-annotations adds descriptions to OpenAPI documentation.
- **@RequestParam(name = "...")**, **@PathVariable(name = "...")**, and corresponding Spring annotations determine the name Spring MVC uses to bind requests.

Merely placing **@Parameter(name = "keyword")** does not cause Spring MVC to bind query key **keyword**. If the controller needs to bind by that name, declare the name in the Spring MVC annotation or ensure parameter names are retained via **-parameters**.

Combined example:

~~~java
@Operation(summary = "Search books")
@GetMapping("/search")
public List<BookResponse> search(
    @Parameter(description = "Search keyword", example = "Spring")
    @RequestParam(name = "keyword")
    String searchText
) {
    // ...
    return List.of();
}
~~~

Here, Spring MVC uses the name **keyword** for binding; **@Parameter** supplies description and example for documentation. The Java variable **searchText** does not have to match the query parameter name.

## 4. Enabling -parameters in Maven

With Maven, the option is configured in **maven-compiler-plugin**. Add the following configuration under **build/plugins** in **pom.xml**:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

If the project uses **spring-boot-starter-parent**, it can inherit the plugin version from the parent and add the configuration to the managed plugin. Avoid declaring an older plugin version solely to turn on one option if the project already has centralized version management.

Another approach is setting the property supported by Maven Compiler Plugin:

~~~xml
<properties>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

Verify that the project's **maven-compiler-plugin** version supports this property. Configuring **<parameters>true</parameters>** directly in the plugin clearly conveys intent and is easy to read when inspecting **pom.xml**.

After updating, run a build to recompile:

~~~bash
mvn clean compile
~~~

**clean** is important when verifying a new option: it removes old class files that might lack **MethodParameters**, then recompiles sources with the current configuration.

## 5. Enabling -parameters in Gradle

With Gradle Groovy DSL (**build.gradle**), configure all JavaCompile tasks:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

With Gradle Kotlin DSL (**build.gradle.kts**):

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

If the build file does not recognize **JavaCompile**, add the import:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
~~~

Then recompile:

~~~bash
./gradlew clean compileJava
~~~

On Windows you can use **gradlew.bat clean compileJava**. In multi-module projects, confirm the configuration applies to modules containing controllers and modules containing classes whose parameter names frameworks need to read. Configuring one module does not automatically alter compiled **.class** files in other modules.

### Checking Whether Configuration Applies to the Right Task

Do not just check whether the build file contains the string **-parameters**. Verify that the Java compilation task actually receives this option. In Gradle, inspect task logs or task configuration; in Maven, inspect the effective POM and compiler logs if needed. Then check the output bytecode to confirm.

Some plugins or convention plugins may override compiler arguments. If a project has multiple modules or multiple source sets, verify the exact task producing class files for the affected controller.

## 6. Verifying with Java Reflection

You can create a simple method to test:

~~~java
public class ParameterNameProbe {
    public void search(String keyword, int page) {
    }
}
~~~

Run the probe snippet:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class InspectParameterNames {
    public static void main(String[] args) throws Exception {
        Method method = ParameterNameProbe.class.getMethod(
            "search",
            String.class,
            int.class
        );

        for (Parameter parameter : method.getParameters()) {
            System.out.printf(
                "%s: %s (present=%s)%n",
                parameter.getType().getSimpleName(),
                parameter.getName(),
                parameter.isNamePresent()
            );
        }
    }
}
~~~

When compiling the probe class with **-parameters**, output should show:

~~~text
String: keyword (present=true)
int: page (present=true)
~~~

If the output shows **arg0 (present=false)** and **arg1 (present=false)**, the inspected class lacks reflection parameter name metadata. Check compiler options, executed tasks, and the loaded class file path.

### Direct Inspection with javap

The JDK provides **javap** to inspect bytecode. Run:

~~~bash
javap -v -p target/classes/com/example/ParameterNameProbe.class
~~~

With Gradle, classes typically reside under **build/classes/java/main/...**. In the output, look for the **MethodParameters** section and the names **keyword** and **page**.

Example of expected output:

~~~text
MethodParameters:
  Name                           Flags
  keyword
  page
~~~

Exact names and formatting may vary by JDK, but the MethodParameters attribute containing the parameter names must appear. Seeing only **LocalVariableTable** does not prove **-parameters** was applied.

## 7. Verifying in a Spring Boot App and OpenAPI Documentation

After enabling the option and recompiling, verify both runtime binding and generated documentation.

Sample controller:

~~~java
@RestController
@RequestMapping("/api/books")
@Tag(name = "Books")
public class BookController {

    @Operation(summary = "Search books")
    @GetMapping("/search")
    public List<BookResponse> search(
        @RequestParam String keyword,
        @RequestParam(defaultValue = "0") int page,
        @RequestHeader(required = false) String requestId
    ) {
        // ...
        return List.of();
    }
}
~~~

Test calling the endpoint:

~~~http
GET /api/books/search?keyword=spring&page=1
X-Request-Id: req-123
~~~

Verify:

1. Spring binds **keyword**, **page**, and **requestId** accurately.
2. Endpoint **/v3/api-docs** contains operation **GET /api/books/search**.
3. Parameters are documented with names **keyword**, **page**, and **requestId**.
4. Locations are respectively query, query, and header.
5. **page** has the appropriate default and **requestId** is documented as optional.

If the application binds properly but documentation shows wrong names, check OpenAPI annotations and how springdoc reads metadata. If documentation looks right but real requests fail, check names declared in Spring MVC annotations, compiler options, and the actual running class files.

## 8. Confusing Scenarios and Resolutions

| Scenario | Cause | Resolution |
|---|---|---|
| Variable name is right in source but Spring reports missing parameter name | Name is not stored in class file | Enable **-parameters** and run clean compile |
| Reflection returns **arg0** | Class was compiled without MethodParameters | Check compiler task and correct classpath |
| Only **-g** enabled, still no reflection names | Debug metadata differs from MethodParameters | Enable **-parameters** |
| Using **@Parameter(name = "...")** but Spring still binds wrong | OpenAPI annotation does not govern binding | Declare **name** in Spring MVC annotation |
| Works locally but fails in deployed environment | Server artifact was built with a different config or module | Inspect class files inside deployed artifact |
| Added option but result unchanged | Incremental build still using stale class files or config not applied | Clean and recompile the right module |
| Java controller has names, external dependency does not | Library compiled separately without storing metadata | Configure compiler for dependency module or declare explicit names in APIs as needed |

For public endpoints, consider declaring explicit names in Spring MVC annotations for important parameters. This keeps the HTTP contract stable even if Java variable names are changed during internal refactoring.

## 9. When to Use Explicit Names vs. -parameters?

The two approaches complement each other:

| Option | Suitable When | Advantage |
|---|---|---|
| Enable **-parameters** | Spring project uses parameter names for binding or metadata analysis across many places | Configured once for all compiled classes in a module |
| Declare **name** in Spring MVC annotation | HTTP name is part of a contract needing stability or Java name should differ from HTTP name | Clear right at the binding point, independent of variable names |
| Combine both | Project uses reflection broadly and APIs need stable HTTP names | Retains reflection metadata while keeping binding names explicit |

For APIs documented with springdoc-openapi, a practical convention is enabling **-parameters** across all Java modules and declaring explicit names for public-facing parameters or parameters whose names differ from Java variables. Use **@Parameter** to add descriptions, examples, and schemas; do not use it as a substitute for Spring MVC binding annotations.

## 10. Checklist Before Concluding Configuration Is Correct

- [ ] Maven or Gradle has enabled **-parameters** for the appropriate Java compile tasks.
- [ ] Ran clean and recompiled class files after changing configuration.
- [ ] Reflection returns the expected parameter names and **isNamePresent()** is **true**.
- [ ] **javap -v** shows **MethodParameters** containing the expected names.
- [ ] Controller binds query, path, header, or cookie correctly when sending real requests.
- [ ] OpenAPI JSON at **/v3/api-docs** has accurate parameter names and locations.
- [ ] Names declared in Spring MVC annotations match the HTTP contract.
- [ ] Deployed artifacts are built from the verified compiler configuration.

## Conclusion

**-parameters** is a Java compiler option that stores parameter names in the **MethodParameters** attribute of **.class** files. Spring MVC can use this metadata when binding annotations omit explicit names; springdoc-openapi can also rely on parameter names when generating parameters in the specification. Enable the option in Maven or Gradle, recompile, and verify with Reflection or **javap** to ensure names exist in bytecode. For HTTP names requiring stability, explicitly declare **name** in Spring MVC annotations and reserve OpenAPI annotations for documentation descriptions.

# Display Name, Binding Name, and Parameter Name Discovery

When springdoc-openapi generates documentation for a Spring Boot endpoint, the parameter names appearing in OpenAPI must accurately reflect the names that clients must send. However, three different names can coexist in Java code: the Java parameter variable name, the binding name Spring uses to read HTTP data, and the display name in OpenAPI documentation.

These three names are often identical in simple examples, though not always consistent. Understanding where names come from helps avoid bugs when renaming variables, compiling without metadata, or using documentation annotations that diverge from actual binding behavior.

## 1. Three Types of Names to Distinguish

Consider a customer search endpoint:

~~~java
@GetMapping("/customers")
List<CustomerResponse> searchCustomers(
        @RequestParam(name = "keyword") String query) {
    // ...
}
~~~

In the example:

- <code>query</code> is the parameter name in Java code.
- <code>keyword</code> is the binding name. Spring reads the value from the query parameter named <code>keyword</code>.
- <code>keyword</code> is also the name published in OpenAPI so clients send requests properly.

| Name Type | Where Is It Used? | Example |
|---|---|---|
| Java variable name | In the method signature and implementation | <code>query</code> |
| Spring binding name | Reading values from path, query, header, or cookie | <code>keyword</code> |
| OpenAPI display name | Published for documentation readers and client generators | <code>keyword</code> |

The Java variable name can be changed during refactoring without altering the HTTP contract, provided the binding name stays unchanged. The OpenAPI display name must match the actual contract: if documentation tells clients to send <code>keyword</code> while the controller reads <code>q</code>, API callers may follow the docs yet receive wrong results or errors.

## 2. Where Is the Binding Name Determined?

In Spring MVC and Spring WebFlux, annotations such as <code>@RequestParam</code>, <code>@PathVariable</code>, <code>@RequestHeader</code>, and <code>@CookieValue</code> allow declaring the binding name via the <code>name</code> attribute or its alias <code>value</code>.

### 2.1. Explicit Binding Name Declaration

~~~java
@GetMapping("/customers/{customerId}")
CustomerResponse getCustomer(
        @PathVariable(name = "customerId") String id,
        @RequestParam(name = "includeOrders", required = false) Boolean includeOrders,
        @RequestHeader(name = "X-Tenant-Id") String tenantId,
        @CookieValue(name = "locale", required = false) String locale) {
    // ...
}
~~~

The binding names in the example are respectively:

| Annotation | HTTP Location | Binding Name |
|---|---|---|
| <code>@PathVariable(name = "customerId")</code> | Path | <code>customerId</code> |
| <code>@RequestParam(name = "includeOrders")</code> | Query | <code>includeOrders</code> |
| <code>@RequestHeader(name = "X-Tenant-Id")</code> | Header | <code>X-Tenant-Id</code> |
| <code>@CookieValue(name = "locale")</code> | Cookie | <code>locale</code> |

The Java variable name is an internal detail. In the example, variable <code>id</code> is bound from path variable <code>customerId</code>, and variable <code>tenantId</code> is bound from header <code>X-Tenant-Id</code>.

Explicitly declaring names provides two benefits: Spring always knows the exact HTTP field to read, and maintainers can rename Java variables without changing what clients must send.

### 2.2. The name and value Attributes

Many Spring binding annotations define <code>name</code> and <code>value</code> as two aliases with the same meaning. The following two forms are equivalent:

~~~java
@RequestParam(name = "page") int pageNumber

@RequestParam(value = "page") int pageNumber
~~~

The shorthand form can be used when the annotation has only a single value attribute:

~~~java
@RequestParam("page") int pageNumber
@PathVariable("customerId") String id
~~~

In a project with a consistent convention, pick one style and apply it throughout. Using <code>name</code> often helps readers clearly recognize the value's purpose.

## 3. When Explicit Binding Names Are Omitted, Spring Discovers Java Parameter Names

Spring allows concise syntax by omitting the name inside the annotation:

~~~java
@GetMapping("/customers")
List<CustomerResponse> searchCustomers(
        @RequestParam String keyword) {
    // ...
}
~~~

In this case, Spring must discover the Java parameter name to know the query parameter is named <code>keyword</code>. Discovery relies on metadata embedded in bytecode, specifically parameter names stored by the Java compiler.

Java can store parameter names in class files when compiled with the <code>-parameters</code> option. If a class is compiled without this metadata, reflection may only return generic names such as <code>arg0</code> and fail to identify the source name. Consequently, annotations that rely on name inference may not work as expected.

### 3.1. Enabling Parameter Name Metadata in Maven

With the Maven Compiler Plugin, you can enable the <code>parameters</code> option:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

If the project uses a Spring Boot parent or a BOM/plugin that already manages compiler configuration, check the effective configuration before adding duplicate settings. What matters is that packaged classes contain the parameter name metadata Spring needs.

### 3.2. Enabling Parameter Name Metadata in Gradle

With the Gradle Java plugin, you can add the compiler argument:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

After changing compiler configuration, rebuild the classes and deploy the new artifact. Configuration changes do not retroactively add metadata to previously compiled class files.

### 3.3. When Should Discovery Be Used?

Parameter name discovery keeps code concise and suits projects that consistently enable <code>-parameters</code>. However, it makes binding dependent on compiler metadata. For public endpoints or contracts requiring stability, declaring explicit binding names is generally easier to maintain.

Do not rely on parameter names preserved in debug information as a general guarantee. Debug metadata and parameter name metadata for reflection are separate mechanisms.

## 4. OpenAPI Display Name with springdoc-openapi

springdoc-openapi reads Spring mappings and annotations to create Parameter Objects in OpenAPI. Normally, the binding name from the Spring annotation is used as the parameter name in the documentation.

Swagger Core's <code>@Parameter</code> annotation allows adding or adjusting OpenAPI descriptive metadata such as name, description, location, example, and required status:

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerSearchController {

    @GetMapping("/customers")
    List<CustomerResponse> search(
            @Parameter(
                description = "Keyword to search by name or email",
                example = "lan@example.com"
            )
            @RequestParam(name = "keyword") String query) {
        // ...
    }
}
~~~

In the example, <code>@RequestParam(name = "keyword")</code> defines the runtime binding name. <code>@Parameter</code> adds a description and example for the parameter in the documentation. This is a good way to separate HTTP behavior from explanatory text for readers.

If you truly need to specify the OpenAPI name using <code>@Parameter(name = "...")</code>, ensure that name matches the Spring binding name. <code>@Parameter</code> only documents the contract; it does not change how Spring extracts data from the request.

Example of an inconsistent configuration:

~~~java
@Parameter(name = "customerId")
@PathVariable("id") String id
~~~

Here Spring binding uses the name <code>id</code>, whereas OpenAPI metadata publishes <code>customerId</code>. A client sending <code>customerId</code> according to the documentation may fail to bind to the path variable in Spring. The fix is to align both:

~~~java
@Parameter(name = "customerId")
@PathVariable("customerId") String id
~~~

When the Spring annotation already declares the exact binding name, repeating <code>name</code> in <code>@Parameter</code> is usually unnecessary. Only add it when there is a clear reason, and always inspect the generated documentation.

## 5. Examples for Each Parameter Type

### 5.1. Path Variable

The placeholder name in the mapping and the binding name must correspond:

~~~java
@Operation(summary = "Get customer details")
@GetMapping("/customers/{customerId}")
CustomerResponse getCustomer(
        @PathVariable("customerId") String id) {
    // ...
}
~~~

OpenAPI must publish the parameter at location <code>path</code>, named <code>customerId</code>, with <code>required: true</code>. Path parameters are always mandatory per OpenAPI rules.

Do not rename the placeholder to <code>{id}</code> while leaving the binding as <code>customerId</code> without a corresponding mapping. Path placeholders are part of the URL template handled by Spring.

### 5.2. Query Parameter

~~~java
@GetMapping("/orders")
List<OrderResponse> listOrders(
        @RequestParam(name = "status", required = false) String orderStatus,
        @RequestParam(name = "page", defaultValue = "0") int pageNumber) {
    // ...
}
~~~

The published names are <code>status</code> and <code>page</code>, not <code>orderStatus</code> or <code>pageNumber</code>. The <code>status</code> parameter can be absent; <code>page</code> has a default value applied by Spring when omitted by the client.

### 5.3. Header and Cookie

~~~java
@GetMapping("/profile")
ProfileResponse getProfile(
        @RequestHeader(name = "X-Request-Id", required = false) String requestId,
        @CookieValue(name = "session", required = false) String sessionToken) {
    // ...
}
~~~

In the documentation, the header is placed at location <code>header</code> with name <code>X-Request-Id</code>; the cookie is placed at location <code>cookie</code> with name <code>session</code>. Java variable names only improve code readability and do not replace HTTP names.

## 6. Organizing Naming Conventions

Adopt clear conventions to minimize discrepancies across controllers, OpenAPI, and integration documentation:

| Location | Recommended Convention | Example |
|---|---|---|
| Path variable | camelCase, describing the resource | <code>customerId</code> |
| Query parameter | camelCase, describing filters or pagination | <code>pageSize</code>, <code>sortBy</code> |
| Header | Follow the system's HTTP header convention | <code>X-Request-Id</code> |
| Cookie | Short, stable name per function | <code>session</code> |
| Java variable | camelCase per Java conventions | <code>customerId</code>, <code>pageSize</code> |

Java variable names do not need to match HTTP names. For example, the header <code>X-Request-Id</code> is commonly mapped to the Java variable <code>requestId</code>. What must remain consistent is the binding annotation and the name published in OpenAPI.

For query or header names with specific conventions, declare them explicitly. Never force clients to guess names from source variable names or generator naming rules.

## 7. Verifying the Generated OpenAPI Output

After writing controllers and annotations, inspect the JSON document at the default endpoint:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Example of expected partial output:

~~~yaml
paths:
  /customers:
    get:
      parameters:
        - name: keyword
          in: query
          required: true
          description: Keyword to search by name or email
          schema:
            type: string
~~~

The value of <code>required</code> in the example depends on the actual binding configuration. If <code>@RequestParam</code> is mandatory with no default value, the documentation typically marks the parameter as required. If <code>required = false</code> or a default value is declared, verify the generated output matches accordingly.

When verifying, check these points:

1. Does <code>parameters[].name</code> match the name the client must send?
2. Is <code>in</code> properly set to <code>path</code>, <code>query</code>, <code>header</code>, or <code>cookie</code>?
3. Does the path parameter match the placeholder name and appear as required?
4. Do description, example, data type, and required status match endpoint behavior?
5. Did renaming a Java variable unintentionally alter a display or binding name?

If documentation displays generic names like <code>arg0</code>, <code>arg1</code> or misses parameter names, check whether binding annotations declare names and whether classes were compiled with <code>-parameters</code>.

## 8. Common Issues and Resolutions

**Renaming a Java variable changes the query parameter name.** If the annotation does not declare a name explicitly, Spring may infer it from bytecode. Declare <code>@RequestParam("keyword")</code> or enable <code>-parameters</code> metadata according to project conventions.

**Documentation shows a different name from Spring binding.** Check <code>@Parameter(name = ...)</code> and the binding annotation. Both values must align because the OpenAPI annotation does not govern request binding.

**Unable to discover parameter names at runtime.** Check the <code>-parameters</code> compiler option, rebuild the module, and ensure the deployed artifact is up to date. For critical APIs, eliminate this dependency with explicit binding names.

**Confusing variable names with header names.** A Java name like <code>requestId</code> does not mean clients send header <code>requestId</code>. If the contract requires <code>X-Request-Id</code>, specify that exact name in <code>@RequestHeader</code>.

**Path placeholder and @PathVariable mismatch.** Inspect the string in <code>@GetMapping</code> or the corresponding mapping along with the <code>@PathVariable</code> value. The placeholder name must be bound accurately.

## 9. Pre-Publication Review Checklist

- [ ] Each parameter has an explicit binding name suited to the HTTP protocol.
- [ ] The name published in OpenAPI matches the name Spring actually reads.
- [ ] Java variable names are treated as internal details that can be refactored independently when binding is explicit.
- [ ] If relying on name discovery, the build enables <code>-parameters</code> and artifacts are recompiled.
- [ ] Path placeholders match <code>@PathVariable</code> binding names.
- [ ] Headers, cookies, and query parameters have the right locations, names, and required statuses.
- [ ] <code>@Parameter</code> only supplements descriptive metadata and is not misused to alter runtime binding.
- [ ] Inspected <code>/v3/api-docs</code> after modifying controllers or compiler configuration.

## References

- [Spring Framework – StandardReflectionParameterNameDiscoverer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/StandardReflectionParameterNameDiscoverer.html): discovering parameter names from Java reflection metadata.
- [Spring Framework – @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): binding query parameters in Spring MVC.
- [Spring Framework – @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): binding method parameters to URI template variables.
- [Java Compiler – javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): the <code>-parameters</code> option to store parameter name metadata.
- [Swagger Core – Parameter annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/Parameter.html): OpenAPI metadata for parameters.
- [springdoc-openapi](https://springdoc.org/): generating OpenAPI documentation from Spring Boot applications.

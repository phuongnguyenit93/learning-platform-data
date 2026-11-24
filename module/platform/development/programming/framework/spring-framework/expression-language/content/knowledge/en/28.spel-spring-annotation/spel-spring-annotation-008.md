# Method parameter names and metadata for expressions in Spring

Several Spring features allow writing SpEL expressions directly on method annotations. For example, cache annotations can use method parameters to generate cache keys, while method security can inspect parameters before allowing a method call:

~~~java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(ISBN isbn) {
    // ...
}

@PreAuthorize("#owner == authentication.name")
public Account getAccount(String owner) {
    // ...
}
~~~

In these examples, #isbn and #owner are method parameter names. SpEL does not infer those names solely from the expression string. Spring needs method metadata and a parameter name discovery mechanism (ParameterNameDiscoverer) to populate parameters into the EvaluationContext.

When parameter names are unavailable, many Spring integrations also provide positional variables such as #p0 or #a0. Supported syntax and variables depend on the annotation feature evaluating the expression; not every Spring annotation provides the same evaluation context.

## 1. Why do expressions need method metadata?

A Java method can be declared as:

~~~java
public Book findBook(ISBN isbn, boolean includeReviews) {
    // ...
}
~~~

When the framework evaluates an expression attached to a method invocation, it needs to know:

- Which method is being invoked.
- Which target object receives the call.
- The runtime arguments and their order.
- The name, type, and annotations of each parameter if needed.
- The return type and metadata related to the method.
- The context of the annotation or interceptor handling the call.

This metadata helps Spring bind the expression to the exact data of the current invocation. For example, #isbn can be bound from the first argument of findBook, while #includeReviews takes the second argument if parameter names are discovered successfully.

If the framework cannot retrieve parameter names, the expression may still parse, but variables with those names may not be placed into the context. In that case, use positional aliases or configure appropriate metadata.

## 2. Java parameter names are not always present in bytecode

In source code, parameter names always appear:

~~~java
public Account getAccount(String owner, Long tenantId) {
    // ...
}
~~~

However, the names owner and tenantId are not necessarily stored in the .class file in a way reflection can read. The Java compiler may omit parameter names unless instructed to retain metadata.

For reflection to read parameter names, compile Java with the option:

~~~text
-parameters
~~~

Example with javac:

~~~bash
javac -parameters -d out src/main/java/com/example/AccountService.java
~~~

When a class is compiled with this metadata, Java reflection can read names via Parameter:

~~~java
Method method =
    AccountService.class.getMethod(
        "getAccount",
        String.class,
        Long.class
    );

for (Parameter parameter : method.getParameters()) {
    System.out.println(parameter.getName());
    System.out.println(parameter.isNamePresent());
}
~~~

If parameter name metadata is stored, isNamePresent() returns true and getName() returns names like owner or tenantId.

Without metadata, reflection may return synthetic names such as arg0, arg1 and isNamePresent() is false. These names are not the business parameter names in source code.

## 3. Configuring the compiler to retain parameter names

With the Maven Compiler Plugin, the parameters option can be enabled:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

With the Gradle Java plugin:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

After changing the configuration, recompile the classes containing methods used by expressions. Only editing the build file while continuing to run old bytecode will not add metadata to previously compiled classes.

In multi-module projects, enable the option on the module that actually compiles the class containing the invoked method. If the method resides in an external library, metadata must be present in that library's artifact or the integration must use another naming mechanism.

## 4. What does ParameterNameDiscoverer do?

Spring Core provides the ParameterNameDiscoverer abstraction to discover parameter names from methods or constructors.

A common implementation is StandardReflectionParameterNameDiscoverer. It uses Java reflection and requires parameter name metadata stored in bytecode, typically via javac -parameters.

DefaultParameterNameDiscoverer is the composite option Spring provides for many scenarios. It can combine mechanisms suited to the environment, such as supporting Kotlin metadata when present and Java's reflection parameter metadata.

Other integrations may use their own discoverers or add strategies for reading parameter-naming annotations. Therefore, check the documentation of the feature in use to know the exact metadata sources supported.

Do not assume every Spring version infers parameter names from the debug local-variable table in the same way. In modern Java, compiling with -parameters is the clear and reliable way to provide names for reflection.

## 5. MethodParameter and per-parameter metadata

Spring Core has the MethodParameter class to describe a specific parameter of a method or constructor.

MethodParameter can provide information such as:

- The method or constructor containing the parameter.
- The parameter position (parameter index).
- The Java type of the parameter.
- The generic type when determinable.
- Annotations on the parameter.
- The parameter name via an appropriate name discovery mechanism.

For example, the method:

~~~java
public void update(
        @NotNull String accountId,
        @Valid UpdateRequest request) {
    // ...
}
~~~

has two parameters at index 0 and 1. Metadata helps the framework know each parameter's type and the annotations attached to them.

This metadata does not serve SpEL only. Spring also uses method and parameter information in data binding, validation, argument resolution, dependency injection, and many other AOP mechanisms.

## 6. Parameter names in annotation expressions depend on the integration

SpEL is a general-purpose expression language. However, which variables an annotation provides is the responsibility of the Spring feature processing that annotation.

Example:

- Spring Cache creates a context containing information about the method, target, arguments, and caches.
- Spring Security method authorization creates a context containing authentication, principal, and method invocation information.
- Spring Data can use parameter metadata in query expressions according to its own conventions.
- @Value typically evaluates expressions in a bean/configuration environment and does not automatically have method arguments like cache or method security.

Therefore, do not take the variable list of @Cacheable and assume that @Value or every other annotation provides those same variables.

When writing an expression for an annotation, identify which module the annotation belongs to, how that module's documentation describes the evaluation root and variables, and then choose variable names accordingly.

## 7. Positional variables: #p0 and #a0

Many method-based Spring evaluation contexts provide positional aliases for arguments:

- #p0: parameter at position 0.
- #a0: parameter at position 0.
- #p1 and #a1: parameter at position 1.
- Subsequent positions increment from 0.

Example:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(ISBN isbn) {
    // ...
}
~~~

The expression uses the first argument without needing parameter names in bytecode.

For a method with two parameters:

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0 + ':' + #p1"
)
public Book findBook(ISBN isbn, String language) {
    // ...
}
~~~

#p0 represents isbn and #p1 represents language in declaration order.

These aliases are populated into the context by the framework; they are not special syntax that SpEL automatically creates for every method in every context type. Check whether the annotation feature in use provides them.

## 8. #root.args and root metadata in Spring Cache

Spring Cache provides a dedicated evaluation context for expressions in cache annotations. This context's root object has useful properties such as:

| Property | Meaning |
|---|---|
| #root.method | The method being invoked |
| #root.methodName | The method name |
| #root.target | The target object |
| #root.targetClass | The target type |
| #root.args | Array of method arguments |
| #root.caches | The Caches being used |

Example:

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#root.methodName + ':' + #root.args[0]"
)
public Book findBook(ISBN isbn) {
    // ...
}
~~~

The expression builds a key from the method name and the first argument.

#root.args[0] can be used when wanting to explicitly show accessing the argument by index. #p0 and #a0 are usually shorter when the integration provides those aliases.

Cache root objects and metadata are Spring Cache conventions. Do not assume the root of another annotation has these same properties.

## 9. Example with @Cacheable: parameter names and index fallback

~~~java
@Service
public class BookService {

    @Cacheable(cacheNames = "books", key = "#isbn")
    public Book findBook(ISBN isbn) {
        return loadBook(isbn);
    }
}
~~~

If the name isbn is discovered successfully, the expression can use #isbn.

When the build does not store parameter names or the integration cannot discover that name, positional aliases supported by Spring Cache can be used:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(ISBN isbn) {
    return loadBook(isbn);
}
~~~

Or use root metadata:

~~~java
@Cacheable(cacheNames = "books", key = "#root.args[0]")
public Book findBook(ISBN isbn) {
    return loadBook(isbn);
}
~~~

All three approaches target the first argument, though parameter names are more readable when metadata is stable. Index-based aliases do not depend on source code names, at the cost that the expression must be updated if parameter order changes.

## 10. Example with method security

Spring Security supports SpEL in method authorization annotations such as @PreAuthorize and @PostAuthorize.

Example:

~~~java
@PreAuthorize("#owner == authentication.name")
public Account getAccount(String owner) {
    // ...
}
~~~

The expression compares owner with the authenticated principal's name. Using #owner depends on Spring Security's parameter name discovery mechanism and available metadata.

Index aliases can be used when appropriate for Spring Security's context:

~~~java
@PreAuthorize("#p0 == authentication.name")
public Account getAccount(String owner) {
    // ...
}
~~~

Spring Security also supports a dedicated parameter-naming annotation, such as @P, in cases where explicit naming is needed:

~~~java
@PreAuthorize("#userId == authentication.name")
public Account getAccount(@P("userId") String owner) {
    // ...
}
~~~

@P belongs to Spring Security. It is not a universal annotation that every Spring expression integration automatically understands. Use the exact annotation supported by the module in use.

## 11. Explicit parameter-naming annotations

Some Spring modules support annotations to declare parameter names without relying entirely on compiler metadata.

For example, Spring Security provides @P:

~~~java
public Account getAccount(@P("userId") String owner) {
    // ...
}
~~~

Spring Data has the @Param annotation in corresponding query APIs:

~~~java
@Query("select u from User u where u.email = :email")
User findByEmail(@Param("email") String address);
~~~

These annotations belong to specific integrations. Annotation names, packages, and how expressions/queries use metadata must follow the respective module.

If a feature supports a parameter-naming annotation, this is an explicit way to declare the name an expression or query needs. If not supported, merely adding a similarly named annotation from another module will not make ParameterNameDiscoverer recognize it.

## 12. Method parameter metadata and proxy/AOP

Many annotations are enforced through proxies or interceptors. The framework may receive the method from an interface, an implementing method, or a method resolved through a proxy.

This can affect metadata lookup, especially when:

- Interface and implementation declare different parameter names.
- The method is inherited from a superclass.
- The compiler generates bridge methods due to generics or overrides.
- The proxy calls the method through an interface.
- The runtime artifact differs from the source code currently open in the IDE.

When parameter names are not found as expected, inspect the actual method handled by the interceptor and the bytecode of the running class. Enabling -parameters on the implementation module is a good choice; if the framework supports a parameter-name annotation, place it in the right location and on the right method kind.

## 13. Inspecting parameter name metadata with Java reflection

You can directly inspect the bytecode the JVM is loading:

~~~java
Method method =
    BookService.class.getMethod(
        "findBook",
        ISBN.class
    );

Parameter parameter =
    method.getParameters()[0];

System.out.println(parameter.getName());
System.out.println(parameter.isNamePresent());
~~~

If isNamePresent() is true, the parameter name is stored and reflection can read it. If false, a name like arg0 is not evidence that the source code declared a parameter named arg0; it may just be a synthetic name supplied by reflection.

This is a useful diagnostic step when an expression does not receive #isbn as expected. It checks the metadata of the runtime class, not directly every ParameterNameDiscoverer that a specific module is using.

## 14. Distinguishing parsing errors from parameter resolution errors

An expression can be parsed successfully even if a parameter-name variable is not provided during evaluation.

Example:

~~~spel
#owner == authentication.name
~~~

The parser understands the #owner syntax. However, when the framework evaluates it, if there is no owner variable in the EvaluationContext, the result may not be as expected or subsequent property access may raise an error.

Therefore, separate two stages:

- **Parsing:** is the SpEL syntax valid?
- **Evaluation context construction:** does the framework place the right method arguments and variable names into the context?
- **Evaluation:** can the expression read the variables, root properties, and authentication data?

If the expression parses but #owner has no value, fixing syntax will not solve the metadata problem. Check compiler flags, parameter-name discovery, and the conventions of the annotation integration.

## 15. Naming and ordering parameters for maintainable expressions

Expressions attached to annotations often live long alongside the method signature. A few principles help reduce errors:

- Use parameter names with business meaning; avoid generic names like x or value when there are multiple parameters.
- Enable -parameters consistently in Java modules that need metadata.
- Use #p0 or #a0 aliases when wanting to avoid name dependency, keeping in mind that parameter order is part of the expression contract.
- For modules supporting parameter-naming annotations, consider using the annotation when build metadata cannot be guaranteed.
- When changing parameter order or types, re-check all annotation expressions referencing by index.
- Keep expressions short and reference only parameters that are truly needed.

If an expression must access many parameters, consider grouping business data into a clearly structured object if the API and annotation integration allow it.

## 16. Common misconceptions

**Misconception 1: Parameter names in source are always available at runtime.**  
Names might not be stored in bytecode. Use -parameters or an annotation mechanism supported by the integration.

**Misconception 2: #p0 and #a0 are global variables of every SpEL context.**  
These are aliases typically added to the context by method-based integrations. Availability depends on the specific annotation/module.

**Misconception 3: Every Spring annotation has the same root object and method arguments.**  
Each integration defines its own evaluation context. An annotation might not even support SpEL.

**Misconception 4: Adding @P or @Param anywhere makes parameter names work.**  
Only an integration whose ParameterNameDiscoverer supports that annotation uses the corresponding metadata.

**Misconception 5: Successful expression parsing means parameter names were resolved.**  
Variable names are supplied when building the EvaluationContext and looked up during evaluation.

**Misconception 6: Renaming Java parameters never affects expressions.**  
If an expression uses parameter names, renaming can lose the corresponding variable. Index-based aliases avoid name dependency but still depend on order.

## 17. Key takeaways

- Spring needs method metadata and a ParameterNameDiscoverer mechanism to supply parameter names to annotation expressions.
- Java reflection reads parameter names reliably when classes are compiled with -parameters.
- DefaultParameterNameDiscoverer and module-specific discoverers can combine multiple metadata sources.
- MethodParameter describes the method, index, type, and annotations of a parameter.
- Many method-based contexts provide positional aliases such as #p0 and #a0; verify aliases per annotation integration.
- Spring Cache has root metadata such as #root.method, #root.methodName, #root.target, #root.args, and #root.caches.
- Spring Security method expressions have their own context, which can provide authentication and support parameter names per module rules.
- Annotations such as @P from Spring Security or @Param from Spring Data only take effect in their respective integrations.
- #name is a variable placed into the EvaluationContext by the framework; it is not automatically inferred by SpEL from source code.
- When debugging, check runtime bytecode, compiler options, the actual method behind proxies, and the context created by the annotation.

When writing SpEL for method annotations, clearly identify the integration in use, check which variables and root metadata the integration provides, enable -parameters for relevant classes or use a supported parameter-naming annotation, and then choose variable names or index aliases that fit the method contract.

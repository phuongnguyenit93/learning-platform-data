# `argNames`, Parameter Names, and the `-parameters` Compiler Option in Spring Aspect

## 1. Real-world problem: how does advice receive the right arguments?

A Spring `@Aspect` often needs to know **argument values**, **method annotations**, **return values**, or **exceptions** of an advised Spring bean. To pass those values into advice method parameters, Spring must solve one problem: **which parameter name in the Java advice method does a variable name used in the pointcut expression map to?**

Example:

```java
@Before("execution(* com.example.service..*.*(..)) && args(account,..)")
public void check(Account account) {
    System.out.println(account.id());
}
```

Here, `account` in `args(account,..)` is a **binding name**; `Account account` in the advice signature is the **parameter receiving the actual argument**. Spring must know those two names correspond to each other. If `.class` files do not retain parameter names, or if the pointcut/advice has multiple parameters of the same type, binding can fail or become ambiguous.

In Spring AOP there are two proactive, most common approaches:

1. **Explicitly declare names with `argNames`** on the advice annotation or `@Pointcut`.
2. **Compile Java with `-parameters`** to retain parameter-name metadata for reflection, allowing Spring to discover names automatically from the method signature.

Spring also has fallback inference mechanisms, but they have limitations; do not rely on "it can sometimes be inferred" when designing a system that must run reliably across builds.

**Lesson scope:** parameter names and binding in Spring Framework `@AspectJ` **under Spring AOP proxy mechanics**, not a general guide to Java reflection or AspectJ weaving outside Spring.

### After this lesson, you will be able to

- Understand three distinct concepts: **pointcut variable name**, **Java parameter name**, and **runtime argument value**.
- Use `argNames` for `@Before`, `@Around`, `@AfterReturning`, `@AfterThrowing`, and `@Pointcut`.
- Know when `JoinPoint`/`ProceedingJoinPoint` can be omitted from `argNames`.
- Enable `-parameters` when building with Gradle, Maven, or `javac`.
- Inspect `Parameter.isNamePresent()` metadata and distinguish it from debug information.
- Catch errors caused by variable renames, missing binding names, multiple parameters of the same type, or mismatches between named pointcuts and advice.
- Run a Java 17/Spring Framework project with **one aspect using `argNames`** and **one aspect relying on `-parameters`**, and compare the results.
- Distinguish name binding from normal Spring AOP proxy limitations such as self-invocation.

## 2. Two kinds of names and actual values

Consider the call:

```java
orderService.submit("P-42", 3);
```

Suppose the target method is:

```java
public String submit(String code, int amount) {
    return "accepted:" + code + ":" + amount;
}
```

A Spring advice can declare:

```java
@Before("execution(* demo.binding.OrderService.submit(..))"
      + " && args(code,amount)")
public void before(String code, int amount) {
    System.out.println(code + ":" + amount);
}
```

Three parts play distinct roles:

| Component | Example | Meaning |
| --- | --- | --- |
| **Pointcut binding identifier** | `code` in `args(code,amount)` | Variable introduced by the expression to capture the matching argument value |
| **Advice Java parameter name** | `String code` | Name that Spring must discover or have explicitly declared |
| **Actual runtime value** | `"P-42"` | Real argument passed into the invocation by the caller |
| **Declared Java parameter type** | `String` / `int` | Type constraint for advice binding and method signature |
| **Spring bean proxy** | injected `orderService` | Where Spring evaluates pointcuts/advisors before calling the target |

Renaming the target parameter from `code` to `sku` **does not necessarily** break `args(code,amount)`. `args(...)` uses binding identifiers of the **pointcut/advice**, not a lookup of target parameters by source-code name. Even if the target interface/implementation is compiled without `-parameters`, `args(code,amount)` advice can still bind actual argument values as long as Spring resolves the **advice's parameter names** via one of its supported strategies.

However, if you rename the advice parameter `String code` to `String sku` while keeping `args(code,amount)` without updating `argNames`, Spring may fail to link the variable properly; that is when the direct issue covered in this lesson occurs.

### Distinguishing name binding from index access

`JoinPoint.getArgs()[0]` retrieves the first element by **position**, without reading advice parameter names. `args(code,amount)` binds by **symbol names** declared in the pointcut expression so Spring passes values to advice parameters of matching types.

When an advice only needs raw arguments for simple logging, `JoinPoint.getArgs()` is sometimes more suitable. When type-safe binding or annotation/result/exception binding is needed, `argNames`/`-parameters` provides clear semantics.

## 3. How does Spring discover parameter names?

Per the Spring Framework reference, advice binding relies on `ParameterNameDiscoverer` strategies tried in priority order. Whichever strategy retrieves valid names first is used.

### 3.1. Key strategies

| Spring strategy | Information source | When is it effective? |
| --- | --- | --- |
| `AspectJAnnotationParameterNameDiscoverer` | `argNames` declared in advice/pointcut annotation | When the author specifies names explicitly |
| `KotlinReflectionParameterNameDiscoverer` | Kotlin reflection | With Kotlin code and the appropriate reflection library |
| `StandardReflectionParameterNameDiscoverer` | Java reflection `Parameter.getName()` | When Java code is compiled with `javac -parameters` |
| `AspectJAdviceParameterNameDiscoverer` | Inference from pointcut, `returning`, `throwing`, method types | Fallback in cases with sufficient, unambiguous information |

If the required names cannot be discovered, Spring may throw an exception when initializing the Spring AOP advisor or preparing advice binding. **Fallback inference is not guaranteed to work for every complex expression.**

When multiple parameters share the `String` type, inferring "which parameter corresponds to which name" may not be unique; that is a major reason to use `-parameters` or `argNames`.

### 3.2. Cases where parameter names are not needed

Advice that binds no contextual data:

```java
@Before("execution(public * com.example.service..*.*(..))")
public void count() {
    // No parameter needs to be bound.
}
```

No `argNames` is needed because the advice takes no parameters.

Advice receiving only the join point:

```java
@Before("execution(public * com.example.service..*.*(..))")
public void inspect(JoinPoint jp) {
    System.out.println(jp.getSignature().getName());
}
```

If the first parameter is `JoinPoint` (or `ProceedingJoinPoint` in `@Around`), Spring handles this parameter specially. Advice with only `JoinPoint` does not need to declare `argNames`.

**Do not conclude from these two simple cases that name metadata is unimportant when advice takes multiple parameters to bind.**

## 4. First approach: explicit `argNames`

### 4.1. On `@Before` with `args`

```java
@Before(
    value = "execution(public * com.example.service..*.*(..))"
          + " && args(code,amount)",
    argNames = "code,amount"
)
public void before(String code, int amount) {
    System.out.println("code=" + code + ", amount=" + amount);
}
```

`argNames` takes a comma-separated list of names placed in the **order of bound parameters in the advice signature**. `String code` receives the `code` binding; `int amount` receives `amount`.

If Java source renames the parameters to `String sku, int qty` while the annotation keeps `argNames="code,amount"`, Spring can still bind properly by position as long as the pointcuts and parameter types match. With this approach, **the names declared by `argNames` are the source of truth for the expression**, and do not strictly have to match the Java source parameter names.

For readability and fewer mistakes, good practice is still to **keep `argNames` identical to the actual parameter names**.

### 4.2. Combining `@annotation` and `args`

```java
@Before(
    value = "execution(public * com.example.service..*.*(..))"
          + " && args(code,amount) && @annotation(marker)",
    argNames = "code,amount,marker"
)
public void before(
        String code, int amount, Tracked marker) {
    System.out.println(marker.value() + ":" + code + ":" + amount);
}
```

`marker` is an annotation object bound from the annotation on the method; `code` and `amount` come from actual method arguments. `Tracked` in the snippet is a runtime-retained method annotation requiring an appropriate definition/import. The complete runnable project in section 9 defines it.

Here there are **three binding names** and three advice parameters. You cannot write only `argNames="marker"` if Spring has no other way to discover `code` and `amount`.

### 4.3. Omitting `JoinPoint` from `argNames`

Spring has a convenient rule: if the **first parameter** of an advice is `JoinPoint`, `ProceedingJoinPoint`, or `JoinPoint.StaticPart`, you **may omit that parameter's name** from `argNames`.

```java
@Before(
    value = "execution(public * com.example.service..*.*(..))"
          + " && args(code,amount) && @annotation(marker)",
    argNames = "code,amount,marker"
)
public void before(
        JoinPoint jp, String code, int amount, Tracked marker) {

    String method = jp.getSignature().getName();
    System.out.println(method + ":" + marker.value());
}
```

Here there are **four Java parameters**, while `argNames` lists only **three names**; this is not an error. Spring recognizes the leading `JoinPoint jp`, and the three names apply to the binding variables.

This rule does not mean you can arbitrarily omit any parameter's name. If the first parameter is `String code`, you cannot omit `code` and expect Spring to guess the rest.

### 4.4. With `@Around` and `ProceedingJoinPoint`

```java
@Around(
    value = "execution(public String com.example.service.NameService.hello(..))"
          + " && args(name)",
    argNames = "name"
)
public Object around(ProceedingJoinPoint pjp, String name)
        throws Throwable {

    return pjp.proceed(new Object[] { name.trim() });
}
```

`pjp` comes first and is omitted from `argNames`; `name` is bound from the method argument. This is an illustrative snippet requiring `NameService` and proper AOP setup.

In **Spring AOP**, `proceed(Object[])` takes the **target method's argument array** matching the exact count, order, and types; it is not tied directly to `argNames`, an important distinction compared to the AspectJ compiler/weaver.

### 4.5. With `@AfterReturning` and `returning`

```java
@AfterReturning(
    pointcut = "execution(public String com.example.service..*.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterReturning(String result) {
    System.out.println("returned=" + result);
}
```

`returning="result"` sets the **binding name** for the return value; `argNames="result"` maps that binding to the advice parameter. Advice runs only when the target invocation finishes normally and the result satisfies the `String` type constraint.

**`result` is not a target method parameter name.** It is the symbol name for the return value at the advice layer.

### 4.6. With `@AfterThrowing` and `throwing`

```java
@AfterThrowing(
    pointcut = "execution(* com.example.service..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterThrowing(Throwable error) {
    System.out.println("thrown=" + error.getClass().getSimpleName());
}
```

`throwing="error"` binds the throwable thrown by the method invocation to the advice parameter. `Throwable` covers both checked and unchecked exceptions. If `IllegalArgumentException` is used, the advice receives only throwables compatible with that type.

Changing `throwing="error"` to `throwing="cause"` without synchronizing the corresponding binding name can prevent Spring from resolving the advice parameters.

## 5. Second approach: enabling `javac -parameters`

### 5.1. Does Java keep parameter names by default?

When compiling Java with `javac` without `-parameters`, `.class` files normally **do not contain the `MethodParameters` metadata required for `java.lang.reflect.Parameter` to reliably provide source-level names**.

Example:

```java
public void before(String code, int amount) {}
```

If compiled without `-parameters`, Java reflection may return synthetic names such as `arg0` and `arg1`; `Parameter.isNamePresent()` is typically `false`. Those names do not necessarily match `code`/`amount` used in the pointcut.

With:

```bash
javac -parameters -d out MyAspect.java
```

`javac` retains parameter names in class metadata; reflection can see `code` and `amount`, along with `isNamePresent() == true`.

The command above illustrates compiler-option syntax and **is not enough to compile a standalone Spring aspect** without the Spring/AspectJ classpath and source dependencies. The runnable project in section 9 configures Gradle completely.

### 5.2. Gradle

If using Gradle with the Java plugin:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

This adds `-parameters` to Java compilation tasks. If you want to enable it only for a specific source set or module containing aspects, you can configure that specific task, ensuring **the aspect classes needing name discovery** are actually compiled with the flag.

In modern Gradle, you can use the equivalent form:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
```

Do not assume a flag configured in module A automatically applies to module B. In multi-module Gradle builds, configuration must apply to the module containing the aspect code being compiled. Also check whether the Gradle daemon or IDE selects a different JDK from the configured toolchain if builds fail.

### 5.3. Maven

With a Maven Compiler Plugin supporting this option, you can declare:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>17</release>
        <parameters>true</parameters>
      </configuration>
    </plugin>
  </plugins>
</build>
```

This is a Maven POM configuration snippet to merge into a real project, **not a complete POM**. `<parameters>true</parameters>` instructs the plugin to pass the flag preserving parameter-name metadata during Java compilation; use the plugin version approved by your project team.

### 5.4. Checking metadata via reflection

```java
Method method =
    MyAspect.class.getDeclaredMethod("before", String.class, int.class);

for (Parameter parameter : method.getParameters()) {
    System.out.println(parameter.getName()
            + ":" + parameter.isNamePresent());
}
```

This snippet requires `java.lang.reflect.Method`, `Parameter`, and a real `MyAspect` class. If compiled with `-parameters` and the method has two parameters named `code` and `amount`, it can print:

```text
code:true
amount:true
```

When the flag is absent, **the specific names returned by reflection should not be relied upon as an API contract**; check `isNamePresent()` rather than guessing variable names from a debugger.

## 6. `-parameters` is not the same as debug information (`-g`)

A common misconception is that compiling with debug symbols guarantees Spring will know advice parameter names.

| Mechanism | Information | Is it a reliable substitute for `-parameters`? |
| --- | --- | --- |
| `javac -parameters` | `MethodParameters` metadata readable via `java.lang.reflect.Parameter` | **Yes**, designed for Java reflection parameter-name discovery |
| `javac -g` | Debug information for debuggers, possibly including local variable tables | **Should not be treated as an equivalent substitute** |
| `@Before(argNames="...")` | Binding names declared explicitly in the annotation | **Yes** for that advice binding, independent of reflection names |
| AspectJ `ajc` | Mechanism retaining required names of `@AspectJ` advice | May not need `argNames` if names are supplied by the compiler |
| Spring's compiler inference fallback | Inference from expression/parameter types | Only in cases with sufficient info; prone to ambiguity |

For modern Spring Framework, the official documentation **recommends `-parameters`** for Java reflection. Do not treat behavior observed in older versions or legacy build tools as an immutable contract.

**Subtle detail:** `-parameters` metadata must be present on the **advice/pointcut method** for Spring to find the advice/pointcut parameter names. You do not strictly need `-parameters` on every target method if your sole goal is binding `args(code,amount)` to advice parameters; however, retaining target method names is also useful for other Spring features like data binding, validation, and reflection. Decide the scope based on your dependencies and project characteristics.

## 7. Named pointcuts also have parameter names

A reusable named pointcut can carry parameters:

```java
@Pointcut(
    value = "execution(public * com.example.service..*.*(..))"
          + " && args(code,amount)",
    argNames = "code,amount"
)
public void orderOperation(String code, int amount) {}
```

When an advice uses the named pointcut:

```java
@Before(
    value = "orderOperation(code,amount)",
    argNames = "code,amount"
)
public void before(String code, int amount) {
    // ...
}
```

Two mapping layers exist:
1. `@Pointcut` method: the `args(code,amount)` expression and the named pointcut's signature receive the proper binding.
2. Advice method: the `orderOperation(code,amount)` expression supplies bindings to the advice signature.

**Do not confuse** `argNames` on `@Pointcut` with `argNames` on the advice. If declared explicitly in one place while the other lacks suitable name information, binding can still fail.

### Sharing across another aspect

When a named pointcut resides in `com.example.aop.CommonPointcuts`, advice in another `@Aspect` can reference it:

```java
@Before(
    value = "com.example.aop.CommonPointcuts.orderOperation(code,amount)",
    argNames = "code,amount"
)
public void record(String code, int amount) {
    // ...
}
```

These are illustrative snippets for visibility/name binding; the classes must be defined and used with proper Spring bean/pointcut configuration. Usually, make named pointcuts `public` when referenced from other classes/packages.

## 8. Common mistakes when using `argNames` and `-parameters`

### 8.1. Missing names causing binding failure

```java
@Before("execution(* com.example.service..*.*(..))"
      + " && args(code,amount)")
public void before(String x, int y) {
}
```

Without `-parameters` and without declaring `argNames`, Spring can infer names in some simple cases, yet **there is no consistent guarantee across all expressions**. If inference fails, AOP startup may fail with a missing or inconsistent binding-parameter error.

Fix:

```java
@Before(
    value = "execution(* com.example.service..*.*(..))"
          + " && args(code,amount)",
    argNames = "code,amount"
)
public void before(String x, int y) {
}
```

This gives the parser explicit binding names in parameter order. Or keep `String code,int amount` in source and build with `-parameters`.

### 8.2. Two parameters of the same type causing ambiguity

```java
@Before("execution(* com.example.service..*.*(..))"
      + " && args(first,second)")
public void before(String first, String second) {
}
```

Without `argNames`/`-parameters`, the inference algorithm cannot always determine which symbol maps to which parameter. Do not risk "swapping" the meanings of `first` and `second` simply because both parameters are `String`.

Set explicitly:

```java
@Before(
    value = "execution(* com.example.service..*.*(..))"
          + " && args(first,second)",
    argNames = "first,second"
)
public void before(String first, String second) {
}
```

### 8.3. Returning results and errors differently: `returning`/`throwing`

Name mismatch error:

```java
@AfterReturning(
    pointcut = "execution(* com.example.service..*.*(..))",
    returning = "value",
    argNames = "result"
)
public void after(String result) {}
```

`returning` wants to bind symbol `value`, while `argNames` declares `result`. This is a **name inconsistency** that must be fixed.

Correct:

```java
@AfterReturning(
    pointcut = "execution(* com.example.service..*.*(..))",
    returning = "value",
    argNames = "value"
)
public void after(Object result) {}
```

The actual Java parameter can be named `result`, because explicit `argNames` describes binding names in order. However, for maintainability, it is best to rename the Java parameter consistently to `value`.

For `throwing`, the exact same principle applies.

### 8.4. Miscounting names because of `JoinPoint`

Wrong assumption:

```java
@Before(
    value = "execution(* com.example.service..*.*(..))"
          + " && args(code,amount)",
    argNames = "jp,code"
)
public void before(JoinPoint jp, String code, int amount) {}
```

This sample **omits `amount`** for binding, while `jp` is listed as an ordinary name even though Spring handles it specially. Correct and readable:

```java
@Before(
    value = "execution(* com.example.service..*.*(..))"
          + " && args(code,amount)",
    argNames = "code,amount"
)
public void before(JoinPoint jp, String code, int amount) {}
```

### 8.5. Assuming `-parameters` fixes every pointcut error

`-parameters` **does not solve**:
- A pointcut `execution(...)` with the wrong package/type/method signature;
- A Spring aspect not registered as a bean;
- A target that is not proxied;
- Self-invocation `this.method()` bypassing the proxy;
- CGLIB inability to override `final`/`private` methods;
- An annotation missing `RetentionPolicy.RUNTIME`;
- Incompatible binding types, or an `args(...)` expression requiring a different arity from the actual method;
- An exception or return value whose type does not match the advice binding;
- Multiple advisors in the context participating and altering the outcome.

Those are separate issues, not name discovery.

## 9. Complete runnable example: explicit `argNames` and `-parameters` name discovery

This example creates **one Spring service** with `submit(String code, int amount)` and **two aspects**:
- `ExplicitAspect` explicitly declares `argNames`, binds both `args` and `@annotation`, and counts `@Before`, `@AfterReturning`, and `@AfterThrowing`.
- `InferredAspect` **does not use `argNames`**, relying on `javac -parameters` so Spring reads parameter names `code`/`amount` from bytecode.

We avoid logging inside each advice so results do not depend on ordering between the two aspects. Each aspect increments its own counters, and `main` prints a snapshot after calling the service.

**Environment:** Java 17+, Spring Framework `6.1.14`, AspectJ Weaver `1.9.22.1`, Gradle. Plain Spring Framework, no Spring Boot, web server, or database needed.

### 9.1. Project structure

```text
spring-aop-parameter-names/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/binding/
    ├── Tracked.java
    ├── OrderService.java
    ├── ExplicitAspect.java
    ├── InferredAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 9.2. Gradle enabling `-parameters`

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-parameter-names'
```

`build.gradle`:

```groovy
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

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.binding.DemoApplication'
}
```

The decisive setting is `options.compilerArgs += ['-parameters']`: `InferredAspect.before(String code, int amount)` preserves the two names required for Spring reflection name discovery.

### 9.3. Annotation used in `@annotation` binding

`src/main/java/demo/binding/Tracked.java`:

```java
package demo.binding;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Tracked {
    String value();
}
```

`@Retention(RUNTIME)` ensures Spring can read the method annotation during pointcut/advice matching. `@Tracked` is placed on the **method**, not on an argument type.

### 9.4. Target Spring service

`src/main/java/demo/binding/OrderService.java`:

```java
package demo.binding;

public class OrderService {

    @Tracked("orders")
    public String submit(String code, int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException(
                "amount must be positive");
        }
        return "accepted:" + code + ":" + amount;
    }
}
```

The method is not `final` and the target class is not `final`, so it can be proxied by Spring CGLIB. Both calls in `main` use `code="P42"`, with different `amount` values.

### 9.5. Aspect declaring explicit `argNames`

`src/main/java/demo/binding/ExplicitAspect.java`:

```java
package demo.binding;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ExplicitAspect {

    private int beforeCalls;
    private int returnedCalls;
    private int thrownCalls;
    private String lastBinding = "";

    @Before(
        value = "execution(public String demo.binding.OrderService.submit(..))"
              + " && args(code,amount) && @annotation(tag)",
        argNames = "code,amount,tag"
    )
    public void before(JoinPoint jp, String code, int amount, Tracked tag) {
        beforeCalls++;
        lastBinding = jp.getSignature().getName()
            + ":" + code + ":" + amount + ":" + tag.value();
    }

    @AfterReturning(
        pointcut = "execution(public String demo.binding.OrderService.submit(..))",
        returning = "result",
        argNames = "result"
    )
    public void returned(String result) {
        returnedCalls++;
    }

    @AfterThrowing(
        pointcut = "execution(public String demo.binding.OrderService.submit(..))",
        throwing = "error",
        argNames = "error"
    )
    public void thrown(IllegalArgumentException error) {
        thrownCalls++;
    }

    public int beforeCalls() { return beforeCalls; }
    public int returnedCalls() { return returnedCalls; }
    public int thrownCalls() { return thrownCalls; }
    public String lastBinding() { return lastBinding; }
}
```

In `before`:
- `args(code,amount)` binds actual arguments by position and type.
- `@annotation(tag)` binds the `@Tracked("orders")` instance from the method execution.
- `JoinPoint jp` is the **leading** parameter, so `argNames="code,amount,tag"` intentionally **omits `jp`**.
- `@AfterReturning` increments only on normal return.
- `@AfterThrowing` uses `IllegalArgumentException`, matching the error type in the example.

The counters are mutable fields on a singleton aspect; the example calls sequentially to keep output simple. In concurrent production code, use thread-safe counters or a concurrency-capable metrics system; do not treat these `int` counters as a production template.

### 9.6. Aspect relying on `-parameters`

`src/main/java/demo/binding/InferredAspect.java`:

```java
package demo.binding;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class InferredAspect {

    private int beforeCalls;

    @Before(
        "execution(public String demo.binding.OrderService.submit(..))"
        + " && args(code,amount)"
    )
    public void before(String code, int amount) {
        beforeCalls++;
    }

    public int beforeCalls() {
        return beforeCalls;
    }
}
```

There is no `argNames` in `@Before`. Because the build enables `-parameters`, Spring can read the names `code` and `amount` directly from `InferredAspect.before(...)` via `StandardReflectionParameterNameDiscoverer`. If you remove `-parameters` and rebuild, Spring may fall back to inference or throw an error depending on expression clarity; **do not rely on a single simple experiment to guarantee all complex advice will still run**.

### 9.7. Creating the context and registering aspects

`src/main/java/demo/binding/AppConfig.java`:

```java
package demo.binding;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public ExplicitAspect explicitAspect() {
        return new ExplicitAspect();
    }

    @Bean
    public InferredAspect inferredAspect() {
        return new InferredAspect();
    }
}
```

`@Aspect` **does not register a bean automatically**; the three `@Bean` methods put the service and aspects into the Spring context. `@EnableAspectJAutoProxy(proxyTargetClass = true)` enables Spring AOP and creates a class-based proxy suitable for `OrderService`, which implements no interface.

### 9.8. Main verifying Java reflection and advice binding

`src/main/java/demo/binding/DemoApplication.java`:

```java
package demo.binding;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) throws Exception {
        Method method = InferredAspect.class.getDeclaredMethod(
            "before", String.class, int.class);

        boolean namesPresent = Arrays.stream(method.getParameters())
            .allMatch(Parameter::isNamePresent);
        System.out.println("namesPresent=" + namesPresent);

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService service = context.getBean(OrderService.class);
            ExplicitAspect explicit =
                context.getBean(ExplicitAspect.class);
            InferredAspect inferred =
                context.getBean(InferredAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            System.out.println("result=" + service.submit("P42", 3));

            try {
                service.submit("P42", 0);
            } catch (IllegalArgumentException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println(
                "explicitBefore=" + explicit.beforeCalls());
            System.out.println(
                "explicitReturned=" + explicit.returnedCalls());
            System.out.println(
                "explicitThrown=" + explicit.thrownCalls());
            System.out.println(
                "inferredBefore=" + inferred.beforeCalls());
            System.out.println(
                "lastBinding=" + explicit.lastBinding());
        }
    }
}
```

### 9.9. Running and expected stdout

In the directory containing `build.gradle`:

```bash
gradle run
```

If the project already has Gradle Wrapper, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows. Use a Gradle version supporting the Java 17 toolchain.

**Lines printed by the Java code itself**, excluding Gradle output or Spring loggers:

```text
namesPresent=true
proxy=true
result=accepted:P42:3
caught=amount must be positive
explicitBefore=2
explicitReturned=1
explicitThrown=1
inferredBefore=2
lastBinding=submit:P42:0:orders
```

Explanation:
- `namesPresent=true` confirms **`InferredAspect.before`** carries Java parameter-name metadata.
- `proxy=true` shows `OrderService` is Spring AOP-proxied, so calls in `main` are actually intercepted.
- `explicitBefore=2`: explicit `argNames` bound successfully on both calls.
- `inferredBefore=2`: `-parameters` name discovery also bound successfully twice.
- `explicitReturned=1`: the `amount=3` call returned normally.
- `explicitThrown=1`: the `amount=0` call threw `IllegalArgumentException`.
- `lastBinding=submit:P42:0:orders` proves the binding captured the exact method name, actual `code`/`amount`, and `@Tracked` value on the method.

**Do not infer anything about the ordering of the two `@Before` advice methods** from this example: they do not print logs during invocation, so the counts stay stable even if Spring changes advisor ordering. If business logic depends on advice ordering, declare and test `@Order`/`Ordered` explicitly.

## 10. When to prefer `argNames` vs. `-parameters`?

| Situation | Recommendation |
| --- | --- |
| Modern Spring Framework Java project where you control the build | Enable `-parameters` consistently in modules containing aspects |
| Complex advice, multiple same-type parameters, clear public documentation desired | Add explicit `argNames` and use consistent names |
| Java classes built by external libraries without control over compiler options | Use `argNames` when writing your advice to avoid depending on stripped names |
| Advice only receives `JoinPoint` | Usually no `argNames` needed |
| Advice only logs beforehand and binds no parameters | Neither `argNames` nor reflection metadata needed |
| Advice binds `returning`/`throwing` | Keep symbols consistent with `argNames` and properly typed advice parameters |
| Named pointcut passes parameters to advice | Ensure name metadata or explicit `argNames` on both the pointcut method and advice |
| Features needing **target method parameter names** for API/docs/data binding | Enable `-parameters` in modules containing the relevant **target classes** |
| Moving code across Gradle modules or CI differing from IDE | Check compiler flags on the exact compile task; avoid assuming flags propagate automatically |
| Eliminating hard-to-reproduce ambiguity | Write Spring AOP proxy integration tests against the actual build artifact |

You do not need to simultaneously declare `argNames` on every advice once `-parameters` is enabled. Nevertheless, for public libraries or complex expressions, explicit names help readers understand the binding contract and avoid depending on flags in external build environments.

## 11. Step-by-step debugging of parameter-name errors

1. **Read the exact exception root cause.** Errors may occur when Spring builds advisors or initializes the context; do not lump every exception into "wrong pointcut".
2. **Check the Spring bean.** Is the aspect registered and is `@EnableAspectJAutoProxy` active in the right context?
3. **Check the expression.** Do `args(x,y)` / `@annotation(tag)` / `returning` / `throwing` define all expected binding variables?
4. **Check the advice signature.** Do parameter count, order, types, and names match the expression?
5. **Check the leading `JoinPoint` parameter.** If present, you do not need to declare its name in `argNames`.
6. **Check actual compiler flags.** A build config containing `-parameters` does not mean the source class was recompiled successfully. Clean/rebuild when needed.
7. **Inspect `Parameter.isNamePresent()` directly** on the advice method in the compiled class.
8. **Do not check only Debug/LineNumberTable.** `-g` is not a contract replacing Java reflection parameter metadata.
9. **When multiple parameters share the same type**, use explicit `argNames` rather than relying on inference fallback.
10. **Check named pointcuts separately.** Does the class holding the pointcut have matching parameter names and `argNames`, and is the expression referenced with valid scope/visibility?
11. **Check the Spring proxy and call path.** If startup succeeds without error yet advice does not run, the issue may be a non-matching method or self-invocation rather than parameter names.
12. **Write positive and negative tests.** Call methods with matching and non-matching actual arguments/annotations; assert the actual advice values, not just call counts.

### Quick snippet to check reflection metadata

```java
Method m = InferredAspect.class.getDeclaredMethod(
    "before", String.class, int.class);

for (Parameter p : m.getParameters()) {
    System.out.println(p.getName() + ":" + p.isNamePresent());
}
```

In the project from section 9, this snippet prints:

```text
code:true
amount:true
```

When using multiple build systems, add an automated test/assertion to catch `-parameters` being disabled in the module containing aspects.

## 12. Practice checklist

- [ ] Confirm this is a **Spring Aspect binding** problem, without confusing it with target method parameter names.
- [ ] Every variable in `args(...)`, `@annotation(...)`, `target(...)`, `this(...)`, etc. has a matching advice parameter type and name.
- [ ] If using `argNames`, the count and order of names match the parameters to bind.
- [ ] Leading `JoinPoint`/`ProceedingJoinPoint`/`JoinPoint.StaticPart` is handled properly and may be omitted from `argNames`.
- [ ] `returning`/`throwing` names match the advice's binding names.
- [ ] `javac -parameters` is enabled on the right module/compile task when relying on reflection names.
- [ ] Do not equate `-g` with `-parameters`.
- [ ] For named pointcuts taking parameters, check names on both the pointcut declaration and the advice caller.
- [ ] Aspect has `@Aspect` and is a Spring bean; target is Spring-managed.
- [ ] Spring AOP proxy is created and method invocations actually pass through the proxy.
- [ ] Tests cover multiple same-type parameters to catch ambiguity.
- [ ] Do not expect `-parameters` to fix self-invocation, `final` methods, wrong pointcuts, or missing annotation retention.

## 13. Conclusion

**`argNames` and `-parameters` solve the same core need in a Spring Aspect: giving Spring the names required to link pointcut variables to advice parameters.**

- **`argNames`:** declares binding names **explicitly** in advice/pointcut signature order, suited when clarity is desired or compiler flags are outside your control.
- **`-parameters`:** retains Java method parameter names in bytecode so Spring discovers them via reflection; the approach recommended by Spring for modern Java code.
- **Fallback inference:** only an aid in cases with enough information; should not be treated as a guarantee for every complex advice.

Both approaches concern **name binding** only. They do not change the semantics of `args`, `@annotation`, `returning`, or `throwing`, nor do they remove the Spring AOP boundary that **only method invocations through a Spring-managed proxy can be advised**.

### Official Spring documentation

- [Spring Framework — Declaring Advice, Determining Argument Names](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): list of `ParameterNameDiscoverer` strategies, `argNames`, `-parameters`, rule for omitting leading `JoinPoint`, and `returning`/`throwing`.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): `args`, `@annotation`, binding pointcuts, and named pointcut declarations.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): registering Spring `@Aspect` beans and auto-proxy infrastructure.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, self-invocation, and proxy limitations.
- [Spring Framework API — AspectJAdviceParameterNameDiscoverer](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/aop/aspectj/AspectJAdviceParameterNameDiscoverer.html): fallback name-discovery algorithm and ambiguity cases.
- [Java 17 — javac Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-parameters` option to generate `MethodParameters` metadata.

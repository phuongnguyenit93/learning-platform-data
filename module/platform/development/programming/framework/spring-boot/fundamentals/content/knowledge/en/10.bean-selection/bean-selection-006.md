# Parameter Names, Compilation Metadata, and Version Differences

When a Spring constructor requires a bean by Java type, Spring normally searches for matching beans **by type**. If multiple beans share that type, the container needs extra information to decide which bean gets injected. One fallback signal is the **parameter name**: if the parameter name matches the bean name or alias of an eligible candidate, Spring can choose that candidate.

This mechanism easily causes surprises during Spring upgrades. Source-code parameter names are not always preserved in bytecode. Starting with **Spring Framework 6.1**, Spring no longer reads parameter names by parsing the local-variable debug table; Java code must be compiled with the **`-parameters`** flag so parameter names are available via Java Reflection. In **Spring Framework 6.2**, the bean selection algorithm was refined further, adding a fast shortcut for name matches and introducing the `@Fallback` annotation.

This lesson belongs to the **Bean Selection** chapter of **Spring Boot Fundamentals**. We will go from by-name bean selection rules through compiler-generated metadata to configuring Gradle/Maven and understanding differences across Spring versions.

## 1. At which step is the parameter name used?

Suppose an application has two implementations of the same type:

```java
public interface PaymentGateway {
    String charge(long amount);
}
```

```java
import org.springframework.stereotype.Component;

@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amount) {
        return "Paid by card: " + amount;
    }
}
```

```java
import org.springframework.stereotype.Component;

@Component("bankGateway")
public class BankPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amount) {
        return "Paid via bank: " + amount;
    }
}
```

Now a service requires a `PaymentGateway`:

```java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Spring finds two matching beans:

| Bean name | Implementation type | Type satisfied by bean |
|---|---|---|
| `cardGateway` | `CardPaymentGateway` | `PaymentGateway` |
| `bankGateway` | `BankPaymentGateway` | `PaymentGateway` |

The constructor requires **one** `PaymentGateway`, yet lacks information indicating which bean to use. Without another selection rule, Spring reports an ambiguity error, typically containing `NoUniqueBeanDefinitionException` inside an `UnsatisfiedDependencyException` chain.

If the parameter is changed to:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

then the name `bankGateway` can serve as a signal for Spring to select the bean with the same name, **if the parameter name exists in runtime metadata and other precedence rules do not decide another candidate**.

This is a fallback step in the autowiring mechanism. It does not turn `@Autowired` into a pure by-name lookup mechanism.

### 1.1. Distinguishing three kinds of names

| Name kind | Example | What is it used for? |
|---|---|---|
| Class name | `BankPaymentGateway` | Identifies the Java type, usually inside a package |
| Bean name | `bankGateway` | Identifies the bean inside the Spring container |
| Parameter name | `bankGateway` in constructor | Injection point metadata, usable for resolving candidates |

The three names may match, but do not have to match.

For example:

```java
@Service("bankGateway")
public class BankPaymentGateway implements PaymentGateway {
    // ...
}
```

```java
public CheckoutService(PaymentGateway selectedGateway) {
    this.gateway = selectedGateway;
}
```

The class name is `BankPaymentGateway`, the bean name is `bankGateway`, and the parameter name is `selectedGateway`. In this case, the parameter name does not match the bean name; Spring can still inject if only one bean matches, or if another selection rule applies.

### 1.2. Name rules do not bypass types

Suppose a bean named `bankGateway` exists, but it does not implement `PaymentGateway`. The constructor:

```java
public CheckoutService(PaymentGateway bankGateway) {
    // ...
}
```

cannot receive an incompatible object merely because the names match. `@Autowired` still starts from candidates matching the dependency type; parameter names only assist in distinguishing among matching candidates.

This is a key difference from certain direct by-name lookup mechanisms.

## 2. Conceptual bean selection flow

When Spring resolves a single dependency, the main steps can be envisioned as:

```text
Injection point
  Constructor / method / field
          │
          ▼
Find beans matching required type
          │
          ▼
Filter by qualifier and autowire-candidate conditions
          │
          ▼
Check priority directives:
  @Primary, @Fallback (since 6.2), @Priority...
          │
          ▼
If further resolution is needed:
  match injection-point name
  against bean name or alias
          │
          ▼
Single bean chosen?
     ┌────┴────┐
     │         │
    Yes        No
     │         │
     ▼         ▼
  Inject    Report missing or
            ambiguous bean
```

This is a conceptual diagram, not an immutable internal order across every version. Spring has specific rules regarding qualifiers, primary, fallback, priority, and dependency names; some precedences changed between 6.1 and 6.2.

Points to remember:

- **Type** determines the initial candidate set.
- **`@Qualifier`** narrows the candidate set by matching qualifiers.
- **`@Primary`** designates a preferred bean when a single bean is needed.
- **`@Fallback`** (since Spring Framework 6.2) marks a fallback bean.
- **Parameter name** can help select a same-named bean among matching candidates.
- If a unique candidate still cannot be determined, Spring reports an error instead of picking randomly.

## 3. Example: parameter name matches bean name

Keep the two beans `cardGateway` and `bankGateway`. Change the constructor to:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway bankGateway) {
        this.gateway = bankGateway;
    }

    public String checkout(long amount) {
        return gateway.charge(amount);
    }
}
```

Under these conditions:

1. Both beans are candidates of type `PaymentGateway`.
2. There is no `@Qualifier` at the injection point selecting another candidate.
3. There is no `@Primary` or `@Fallback` altering selection.
4. The parameter name `bankGateway` is preserved in the class file.
5. The `bankGateway` bean is an eligible candidate and autowirable.

Spring can select the `bankGateway` bean by parameter name.

The flow can then be understood as:

```text
CheckoutService(PaymentGateway bankGateway)
                    │
                    ▼
          Required type: PaymentGateway
                    │
             ┌──────┴──────┐
             ▼             ▼
        cardGateway    bankGateway
                            ▲
                            │
                parameter name = bankGateway
                            │
                            ▼
                     Select this bean
```

If the parameter is renamed to `PaymentGateway gateway`, the name matches neither bean. Without another signal, Spring has no basis to choose between them and may report `NoUniqueBeanDefinitionException`.

### 3.1. When only one bean of the type exists

If the container only has `bankGateway`, the constructor:

```java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

still injects successfully even though the parameter name is `gateway` and the bean name is `bankGateway`. Spring already has a single type candidate, so it does not need parameter names to disambiguate.

Therefore, when troubleshooting errors, distinguish:

- **One matching bean:** parameter name does not need to match bean name.
- **Multiple matching beans:** parameter name can serve as a disambiguation signal if metadata is available.
- **No matching beans:** a matching name does not create a new bean and cannot fix a missing-bean error.

### 3.2. Bean aliases can also be considered

A bean can have aliases:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean(name = {"bankGateway", "preferredBankGateway"})
    public PaymentGateway bankPaymentGateway() {
        return new BankPaymentGateway();
    }
}
```

In the example, `bankGateway` is the primary name and `preferredBankGateway` is an alias for the same bean. The injection point name can match either the bean name or an alias in situations where name matching applies.

Aliases do not create independent bean instances; they are names referring to the same bean definition/bean.

## 4. Why must parameter names be stored in bytecode?

The Java compiler is not required by default to retain source parameter names for Java Reflection in every compilation mode.

For example:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

The name `bankGateway` appears in the source code. However, when compiled without requesting parameter metadata preservation, reflection may only see a generic name like `arg0` and `Parameter.isNamePresent()` returns `false`.

Spring cannot reliably infer the name `bankGateway` solely from text in a `.java` file once source code is absent at runtime.

### 4.1. The `-parameters` flag

The Java compiler has an option:

```bash
javac -parameters ...
```

The `-parameters` flag instructs the compiler to write parameter name information into the class file so the Java Reflection API can read it. Then:

```java
Parameter parameter = constructor.getParameters()[0];

System.out.println(parameter.getName());
System.out.println(parameter.isNamePresent());
```

can return:

```text
bankGateway
true
```

If metadata is not preserved, the output typically looks like:

```text
arg0
false
```

The name `arg0` is a generic name provided by Reflection when source names are not saved via this mechanism. Spring should not rely on it to locate the `bankGateway` bean.

### 4.2. `-parameters` is not a JVM runtime flag

`-parameters` must be set at the **Java compilation stage**.

Correct:

```bash
javac -parameters -d out src/main/java/com/example/CheckoutService.java
```

Incorrect for this purpose:

```bash
java -parameters -jar application.jar
```

`java` is the application launcher; `-parameters` is a `javac` compiler option. Passing it to the JAR launch command cannot add metadata to already-compiled class files.

Similarly, changing compiler configuration after a JAR is built does not retroactively give the old JAR parameter names. Relevant classes must be recompiled and a new artifact packaged.

### 4.3. `MethodParameters` vs `LocalVariableTable`

A Java class file can hold several kinds of metadata:

- **`MethodParameters`**: an attribute storing names and flags of method/constructor parameters; this is what standard reflection uses when generated by the compiler with `-parameters`.
- **`LocalVariableTable`**: debug metadata describing local variables and their scopes in bytecode. Some older Spring versions used to parse this table to infer parameter names.
- **`LineNumberTable`**: maps bytecode to source line numbers for debugging.

Do not confuse building with debug symbols with building that preserves parameter names via `-parameters`.

The `-g` flag or IDE generation of debug info does not replace `-parameters` in Spring versions that removed `LocalVariableTable` reading.

## 5. Differences by Spring Framework version

This is crucial when an application worked previously but fails to find a unique bean after an upgrade.

| Spring Framework | How parameter names are discovered | Implications for applications |
|---|---|---|
| 6.0 and earlier | Can use `LocalVariableTableParameterNameDiscoverer` to infer names from debug metadata; `-parameters` also provides names via reflection | Some projects worked without `-parameters` enabled, as long as bytecode had suitable local-variable debug information |
| 6.1 | Removed `LocalVariableTableParameterNameDiscoverer`; uses names via Java Reflection, requiring `-parameters` for Java parameter names | Do not rely on `-g`/debug local variable tables; if name matching is needed, compile with `-parameters` |
| 6.2 | Continues requiring `-parameters`; adds a fast shortcut when parameter name matches bean name and other conditions do not override; adjusts resolution order involving `@Priority`; adds `@Fallback` | Adds fallback mechanisms and some differences in bean selection order when multiple candidates share a type |

### 5.1. Spring Framework 6.0 and earlier

In older versions, Spring could use `LocalVariableTableParameterNameDiscoverer` to read the local variable table from bytecode. If the compiler/IDE produced suitable debug metadata, Spring could learn parameter names even when Java Reflection reported `isNamePresent()` as false.

This made some projects appear not to need `-parameters`. However, behavior depended on how the compiler emitted debug information, build configuration, and packaging tools. It should not be treated as a stable contract for new code.

`-parameters` has existed since Java 8 and remains the explicit way to retain names for reflection.

### 5.2. Spring Framework 6.1

Starting in 6.1, `LocalVariableTableParameterNameDiscoverer` was removed. Spring and ecosystem projects no longer attempt to parse bytecode to infer parameter names from debug information.

If dependency resolution needs parameter names, enable `-parameters`. This can affect:

- Constructor injection and method injection when name matching is needed.
- Property binding or features using parameter names.
- SpEL or integrated frameworks relying on parameter names.
- Other mechanisms in the Spring ecosystem needing runtime access to parameter names.

If an application previously worked thanks to local-variable debug metadata, upgrading to 6.1 can trigger `NoUniqueBeanDefinitionException` because Spring no longer knows the parameter is named `bankGateway` to pick the matching bean.

**Debug symbols remain useful for debugging**, but are no longer a substitute for the parameter metadata required in Spring 6.1+.

### 5.3. Spring Framework 6.2

Spring 6.2 still requires `-parameters` for Java parameter-name matching. It adds a fast shortcut when a parameter name matches a bean name and no other type/qualifier/primary/fallback condition takes precedence.

6.2 also adjusts the autowiring algorithm: among candidates of the same type, matching parameter names and matching `@Qualifier` against the target bean name can be considered ahead of `@Priority` ranking; in prior versions, priority was checked before those signals. **`@Primary` always takes precedence.**

Additionally, Spring Framework 6.2 introduces `@Fallback` to mark fallback beans. When multiple beans share a type and all but one are marked fallback, the non-fallback bean is chosen for a single dependency.

These changes do not make `-parameters` optional. If parameter names are missing from metadata, Spring still cannot use source names for matching under that rule.

### 5.4. How Spring Boot maps to Spring Framework versions

Spring Boot manages a compatible set of Spring Framework versions via dependency management. Common version lines:

| Spring Boot | Managed Spring Framework line |
|---|---|
| 3.1.x | 6.0.x |
| 3.2.x | 6.1.x |
| 3.3.x | 6.1.x |
| 3.4.x | 6.2.x |

This table only shows general corresponding lines. Specific patch versions vary by Spring Boot release and active dependency management. If a project overrides Spring Framework or uses a different BOM, actual results may differ.

Therefore, when investigating a name-matching error, determine **the actual resolved Spring Framework version**, rather than relying on a line memorized from old documentation.

## 6. Configuring Gradle to retain parameter names

With Gradle Groovy DSL, add configuration to Java compile tasks:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

If using Gradle Kotlin DSL:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
```

This configuration tells `JavaCompile` tasks to apply the `-parameters` compiler option.

### 6.1. Configuring the right project/module

In a multi-project Gradle build, putting configuration at the root can apply to all subprojects if written with proper scoping. If it applies to only one module, place it in that module's `build.gradle`.

Example applying from root:

```groovy
subprojects {
    tasks.withType(JavaCompile).configureEach {
        options.compilerArgs.add("-parameters")
    }
}
```

Do not duplicate configuration across both root and modules unnecessarily. Verify that the module's actual compile task receives this option.

If a module compiles Java code using a separate compiler task or custom plugin, ensure that task also receives `-parameters`.

### 6.2. Not only the application module

Parameter names must be saved in the class file **containing the injection point**.

For example, if `CheckoutService`'s constructor resides in the application module, that module's compile task must enable `-parameters`. If an external library contains the injection point and is compiled independently, the flag must be enabled when compiling that library; the application module cannot fix already-compiled class metadata merely by adding the flag to itself.

If a module has `@Bean` factory methods receiving dependencies by parameter name, check the compile task producing the class containing those factory methods as well.

### 6.3. Rebuilding old class files

After adding the option, recompile so new class files carry the metadata:

```bash
./gradlew clean compileJava
```

Or build the artifact:

```bash
./gradlew clean bootJar
```

On Windows PowerShell:

```powershell
.\gradlew.bat clean compileJava
.\gradlew.bat clean bootJar
```

`clean` clears old outputs that may have been produced with previous compiler options. It does not alter source code and is not required on every routine build; here it is useful to confirm compilation metadata changes.

## 7. Configuring Maven to retain parameter names

With the Maven Compiler Plugin, configure:

```xml
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
```

The `parameters` property instructs the compiler to record parameter names for reflection access.

Then recompile:

```bash
./mvnw clean compile
```

Or package:

```bash
./mvnw clean package
```

If using a Spring Boot Maven parent or BOM, inspect inherited compiler configuration and the effective POM before adding a plugin block. The configuration may already be set at the parent level; what matters is **whether the compiler task actually generating the injection point's class file receives `-parameters`**.

## 8. IDE configuration and differences between IDE Run and JAR

A confusing source of bugs is when two ways of running use two different sets of compiler options:

```text
Run in IDE
   │
   └── IDE compiler / build delegation
           └── may have -parameters enabled

Gradle/Maven build JAR
   │
   └── build tool compiler
           └── may not have -parameters enabled
```

If the IDE compiles classes with parameter names while Gradle/Maven packages different classes without metadata, behavior can differ between the two ways of running. The reverse can also happen.

### 8.1. IntelliJ IDEA

If the IDE delegates build and run to Gradle/Maven, configuring the compiler option in the build tool is central.

If using the IntelliJ compiler directly, you can configure the Java compiler to pass `-parameters` in **Additional command line parameters** under Java Compiler settings. Menu names and locations may vary by IDE version.

### 8.2. Eclipse

Eclipse has an option to store method parameter names in its Java Compiler settings. Enable the corresponding option so the compiler emits metadata usable via reflection.

### 8.3. Kotlin and Groovy

For the Kotlin compiler, Spring Framework recommends the `-java-parameters` flag when Java parameter names need to be preserved for reflection.

For the Groovy compiler, there is a corresponding `-parameters` option. The configuration must apply to the Groovy compile task if injection points are declared in Groovy sources.

### 8.4. Practical rules

- Configure the compiler at the place that **actually compiles the source code**.
- If the IDE delegates builds to Gradle/Maven, avoid configuring two divergent sets of options.
- After changing options, rebuild classes and JARs.
- Inspect class files in the output or artifact, not just IDE checkboxes.
- Do not add `-parameters` to the `java -jar` command because it is not a compiler option.

## 9. Inspecting parameter metadata in class files

When encountering errors because Spring fails to match parameter names, verify metadata before changing bean configuration.

### 9.1. Inspecting via Java Reflection

For example:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class ParameterMetadataInspector {

    public static void main(String[] args) throws Exception {
        Constructor<CheckoutService> constructor =
                CheckoutService.class.getDeclaredConstructor(
                        PaymentGateway.class
                );

        Parameter parameter = constructor.getParameters()[0];

        System.out.println("Name: " + parameter.getName());
        System.out.println("Present: " + parameter.isNamePresent());
    }
}
```

If compiled with `-parameters`, expected output:

```text
Name: bankGateway
Present: true
```

If output is `arg0` and `false`, source names are absent from reflection metadata. In that case, you cannot rely on Spring 6.1+'s parameter-name fallback.

This is a small technical check runnable in a test or diagnostic program. It does not test the entire bean selection algorithm; it only confirms the name information visible to reflection.

### 9.2. Inspecting via `javap`

After compiling, run:

```bash
javap -v -p build/classes/java/main/com/example/shop/CheckoutService.class
```

Look for the attribute:

```text
MethodParameters:
  Name
  bankGateway
```

Class file paths vary by project and build tool. With Gradle, main Java output usually sits under `build/classes/java/main`; with Maven, usually `target/classes`.

If the class file lacks `MethodParameters`, check the compiler command/configuration. The presence of `LineNumberTable` or `LocalVariableTable` does not prove `-parameters` was enabled.

## 10. How do `@Qualifier`, parameter names, and `@Resource` differ?

All three can help identify a bean, yet their semantics differ.

### 10.1. `@Qualifier`: filtering candidates by type

For example:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("bankGateway") PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }
}
```

`@Qualifier("bankGateway")` explicitly specifies the qualifier needed at the injection point. Spring still considers candidates by type, then uses the qualifier to narrow that set.

A qualifier does not have to be a bean name; it can be a dedicated semantic label attached to a bean. If a bean name is used as the qualifier value, Spring can match against the bean name under the corresponding fallback rule.

This is the clear choice when business logic genuinely requires a specific implementation.

### 10.2. Parameter names: convention-based fallback

For example:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

Without `@Qualifier`, the parameter name can serve as a fallback signal when multiple beans share a type. This style is concise, though coupled to compiler metadata and bean names.

If someone renames the parameter from `bankGateway` to `gateway` without changing the bean name, selection behavior can change after recompilation. Therefore, do not treat parameter names as a strong configuration contract when bean selection is critical to business logic.

### 10.3. `@Resource(name = "...")`: identifying by name

Example on a field:

```java
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    @Resource(name = "bankGateway")
    private PaymentGateway gateway;
}
```

`@Resource` under Jakarta semantics is a **name-based** target identification mechanism. The declared type must still be compatible with the injected object, yet target lookup starts from the specified name.

In Spring, `@Resource` is commonly used on fields or single-parameter setters; it is not an option for constructor parameters like `@Qualifier`. With Spring Boot 3.x, the annotation package is `jakarta.annotation.Resource`.

### 10.4. Choosing a style

| Approach | Primary signal | Depends on `-parameters`? | When suitable? |
|---|---|---|---|
| `@Autowired` by type, single candidate | Type | No | Only one bean matches |
| `@Autowired` with parameter-name fallback | Type then parameter/bean name | Yes for Java parameters in Spring 6.1+ | Simple naming convention with controlled metadata |
| `@Qualifier` on constructor parameter | Type + qualifier | Does not need parameter name to pick qualifier | Explicit selection needed at one injection point |
| `@Primary` | Type + primary candidate | No | One default bean for multiple injection points |
| `@Resource(name = "...")` | Bean name | No | Need by-name lookup of one bean on a field/setter |
| `List<T>` / `Map<String, T>` | Bean set by type | No | Want to receive multiple implementations |

For constructor injection, `@Qualifier` is generally the clear and stable choice when a specific bean must be selected.

## 11. Priority annotations and differences in Spring 6.2

### 11.1. `@Primary`

`@Primary` marks the preferred bean when multiple beans of the same type match a single injection point:

```java
@Primary
@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {
    // ...
}
```

If a constructor parameter is named `bankGateway` while `cardGateway` is marked `@Primary`, Spring prioritizes the primary bean per container rules. Do not assume parameter names always override every other directive.

`@Primary` does not remove the remaining beans from the container; collection injection can still receive all matching candidates.

### 11.2. `@Priority`

`@Priority` belongs to Jakarta Annotations:

```java
import jakarta.annotation.Priority;
import org.springframework.stereotype.Component;

@Priority(10)
@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {
    // ...
}
```

With numeric priority, lower values indicate higher priority according to Spring's order comparator rules.

Spring Framework 6.1 and 6.2 changed the ordering between priority ranking and parameter-name / qualifier-name matching. If an application relies simultaneously on these mechanisms, outcomes may change upon upgrading.

Do not mix multiple competing selection signals expecting to rely on internal ordering. Use `@Qualifier` or explicit configuration when an injection point must receive one exact implementation.

### 11.3. `@Fallback` since Spring Framework 6.2

`@Fallback` was introduced in Spring Framework 6.2:

```java
import org.springframework.context.annotation.Fallback;
import org.springframework.stereotype.Component;

@Fallback
@Component("defaultGateway")
public class DefaultPaymentGateway implements PaymentGateway {
    // ...
}
```

Idea: provide a default implementation that the application can override with its own bean without having to mark the new bean `@Primary`.

For example:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @Fallback
    public PaymentGateway defaultGateway() {
        return new DefaultPaymentGateway();
    }
}
```

If only the fallback bean matches, that bean can still be injected. If multiple candidates exist and all but one are marked fallback, the non-fallback bean is chosen. If multiple non-fallback candidates remain, further guidance is needed to resolve them.

`@Fallback` applies to single dependencies; it does not exclude fallback beans from arrays, collections, maps, or candidate streams.

**Spring Framework 6.1 does not have `@Fallback`.** Do not import this annotation in projects still using Framework 6.1.

### 11.4. `@Order` is not a general substitute for `@Qualifier`

`@Order` is normally used to sort beans in collection injection, such as `List<PaymentGateway>`. It does not mean "always inject the bean with the lowest order number" into every constructor accepting a single bean.

Singleton initialization order is also a separate concern, driven mainly by dependency relationships and `@DependsOn`. Do not use `@Order` as a way to rename beans or replace qualifiers.

## 12. Autowiring algorithm differences between 6.1 and 6.2

An example illustrating why version can affect outcomes:

```java
@Component("cardGateway")
@Priority(1)
public class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component("bankGateway")
@Priority(5)
public class BankPaymentGateway implements PaymentGateway {
    // ...
}
```

Injection point:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

Suppose the name `bankGateway` has metadata and both beans match by type. There are two competing signals:

- `cardGateway` has higher priority (lower number).
- `bankGateway` has a name matching the parameter.

According to the changes documented in the Spring Framework 6.2 release notes, parameter-name matches and `@Qualifier` matches against the target bean name take precedence over `@Priority` ranking; previously, priority was checked before those signals. `@Primary` still comes first.

This example illustrates **version differences**, not a recommendation to rely on multiple competing annotations. If the business requirement is to select the bank gateway, write it explicitly:

```java
public CheckoutService(
        @Qualifier("bankGateway") PaymentGateway gateway
) {
    this.gateway = gateway;
}
```

That way intent is expressed directly at the injection point and does not depend on parameter names or priority ordering.

### 12.1. Fast shortcut in Spring Framework 6.2

Framework 6.2 optimizes cases where a parameter name matches a bean name via a fast shortcut, when no other type, qualifier, primary, or fallback conditions override selection. This lets the container skip part of the full candidate lookup process in applicable cases.

This is a container optimization. Do not design code assuming parameter names can always substitute for type safety, qualifiers, or bean registration conditions.

### 12.2. Reviewing name-based dependencies during upgrades

If a project previously used parameter names as an implicit bean selection mechanism, inventory injection points of the form:

```java
SomeService(SomeInterface someBeanName)
```

Then check:

- Is the actual bean name still `someBeanName`?
- Are parameter names stored in bytecode?
- Do `@Primary`, `@Qualifier`, `@Fallback`, or `@Priority` affect the outcome?
- Does the new Framework version change selection order?
- Can it be switched to `@Qualifier` to make the selection clearer?

Do not blame the compiler for an upgrade error before checking dependency candidates; nor change qualifiers if the real issue is class files lacking parameter metadata.

## 13. Checking the actual Spring Framework version in a project

Spring Boot dependency management normally picks the corresponding Spring Framework version. When investigating, inspect the dependency tree of the module that actually runs the application.

Gradle:

```bash
./gradlew dependencyInsight \
    --dependency spring-beans \
    --configuration runtimeClasspath
```

Or:

```bash
./gradlew dependencyInsight \
    --dependency spring-context \
    --configuration runtimeClasspath
```

Maven:

```bash
./mvnw dependency:tree \
    -Dincludes=org.springframework:spring-beans,org.springframework:spring-context
```

Important dependencies here include `spring-beans` (housing most core bean resolution) and `spring-context`. Check the **resolved version**, not just the version declared in one dependency block.

If the project uses the Spring Boot BOM/parent, prefer letting dependency management choose a compatible set of versions. Overriding individual Spring Framework modules can create an inconsistent combination.

### 13.1. Checking versions by Spring Boot line

Some common milestones:

- Spring Boot 3.2 and 3.3 manage Spring Framework 6.1.
- Spring Boot 3.4 manages Spring Framework 6.2.

Specific patch versions change with each Boot release. For example, Boot 3.3 system requirements specify the corresponding Framework 6.1.x; Boot 3.4 specifies the corresponding Framework 6.2.x.

If the application has a custom BOM or dependency overrides, trust the dependency tree output rather than inferring from the Boot version name.

## 14. Diagnosing errors when parameter names are not recognized

Suppose before upgrading, the application ran with two beans of the same type. After moving to Spring Framework 6.1, startup reports:

```text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'PaymentGateway' available:
expected single matching bean but found 2
```

Parameter names may previously have been inferred from the local-variable debug table, whereas new class files lack `MethodParameters`.

### 14.1. Signs to check

| Sign | What to inspect |
|---|---|
| Fails only when two beans share a type | Name fallback may have previously resolved the candidate |
| Parameter reflection returns `arg0` | Class file does not retain parameter names for reflection |
| `Parameter.isNamePresent()` returns `false` | `-parameters` was not applied to that class |
| Works in IDE but fails in JAR | IDE and build tool may compile with different options |
| Fails only after 6.1 upgrade | Project may have relied on LVT debug parameter discovery |
| Outcome changed after 6.2 upgrade | Check name match, `@Qualifier`, `@Priority`, and `@Fallback` |

### 14.2. Troubleshooting workflow

1. **Identify the injection point**: which constructor or method receives the type with multiple beans?
2. **List candidates**: bean names, types, qualifiers, primary/fallback/priority.
3. **Check runtime parameter names** using reflection or `javap`.
4. **Identify the resolved Framework version**.
5. If parameter-name fallback is needed, enable `-parameters` on the right module's compile task and rebuild.
6. If bean selection has business significance, consider `@Qualifier` so code expresses intent clearly.
7. Re-run the exact build/launch flow and verify the injected bean is the desired one.

Do not fix this by enabling bean definition overriding. That mechanism handles bean name collisions at registration, not multiple differently named beans sharing a type.

### 14.3. Do not confuse with missing-bean errors

Three messages have different meanings:

| Message | Meaning |
|---|---|
| `NoSuchBeanDefinitionException` | No matching bean exists |
| `NoUniqueBeanDefinitionException` | Multiple matching beans exist, and a single one cannot be determined |
| `BeanDefinitionOverrideException` | Multiple definitions try to register the same bean name in a registry disallowing overrides |

Parameter-name fallback mainly helps resolve the second case. It does not create beans and does not solve the third case.

## 15. Special cases to watch out for

### 15.1. Field names and parameter names

Spring can use the name of an injection point, such as a field name or parameter name, in name matching.

Field example:

```java
@Autowired
private PaymentGateway bankGateway;
```

Field names can be read from class metadata without `-parameters`. However, a constructor parameter:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

requires compiler parameter-name metadata when using Spring 6.1+.

This is one reason field injection can behave differently from constructor injection in the same project. Still, constructor injection is generally preferred because dependencies are explicit, objects can be immutable, and testing is easier.

### 15.2. `@Bean` method parameters are also injection points

For example:

```java
@Configuration(proxyBeanMethods = false)
public class CheckoutConfiguration {

    @Bean
    public CheckoutService checkoutService(
            PaymentGateway bankGateway
    ) {
        return new CheckoutService(bankGateway);
    }
}
```

Spring must resolve the `bankGateway` parameter when calling the `checkoutService` factory method. Qualifier, type, and parameter-name rules apply at this injection point as well.

Therefore, if a `@Bean` method is used to pick among multiple beans of the same type via parameter name, the class containing the configuration method must also be compiled with appropriate metadata.

### 15.3. Parameter names in external libraries

If the injection point lives in an already-compiled library, the application cannot add parameter metadata to that class merely by enabling `-parameters` in the consuming project.

You need one of these options:

- Use a library version compiled and released with parameter metadata.
- Upgrade or rebuild the library if you control its source.
- Use another configuration/extension point to supply the dependency.
- If the injection point belongs to your own code, use explicit `@Qualifier` to avoid depending on parameter names.

### 15.4. Overloaded constructors

Parameter names are only considered after Spring has decided which constructor or method to use for injection. It is **not a constructor overload selection mechanism**.

For classes with multiple constructors, explicitly declare the autowiring constructor according to appropriate Spring rules, or design a single simple constructor. Only then is parameter metadata on the selected constructor evaluated.

### 15.5. Generic types can reduce candidate count

Spring can use generic type information when looking up beans. For example, `Handler<String>` and `Handler<Integer>` can be distinguished by generic signature if type information is fully preserved in bean definitions and injection points.

This is a type-based filtering mechanism, distinct from parameter-name fallback. Do not add parameter names merely to compensate for a wrongly declared or overly broad generic signature.

## 16. Conventions to adopt in projects

Some principles to keep code stable across upgrades:

1. **Enable `-parameters`** in compiler configuration for Java modules containing Spring injection points, especially with Spring Framework 6.1+.
2. **Use `@Qualifier`** for bean choices that carry business meaning and should be immediately readable in code.
3. Use parameter names matching bean names as a convenient fallback when naming conventions are simple and controlled.
4. Do not rely on `-g` or the local-variable debug table to guarantee parameter names.
5. Do not treat `@Primary`, `@Priority`, `@Fallback`, and `@Order` as interchangeable annotations.
6. When upgrading Spring, check release notes and actual dependency versions before assuming the bean selection algorithm is unchanged.
7. Rebuild class files and JARs after changing compiler options; old class files do not automatically gain metadata.
8. Keep IDE and Gradle/Maven compile configurations consistent if both are used to run the application.

### 16.1. Clear code patterns for important choices

If checkout strictly requires the bank gateway, the clear way to express it:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("bankGateway") PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }
}
```

If a service can use any gateway and only one bean matches in each environment, a type-based constructor suffices:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

If multiple gateways are intentionally used together, accept a collection:

```java
@Service
public class PaymentRouter {

    private final Map<String, PaymentGateway> gateways;

    public PaymentRouter(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }
}
```

Do not use parameter names to hide an under-specified selection requirement.

## 17. Practice exercises

### Exercise 1 — Observing parameter names via reflection

Create a constructor:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

Compile once without `-parameters` and once with `-parameters`. Use `Parameter.getName()` and `Parameter.isNamePresent()` to compare. Observe that source code stays identical while class file metadata differs.

### Exercise 2 — Two beans of same type, matching parameter name

Register `cardGateway` and `bankGateway`. Set the constructor parameter to `bankGateway`. Enable `-parameters` and run the application with Spring Framework 6.1+. Observe the name fallback.

Then change the parameter to `gateway`, recompile, and check the result. Without `@Primary` or `@Qualifier`, two candidates can cause Spring to report ambiguity.

### Exercise 3 — Trying explicit qualifier

Keep the parameter named `gateway` but add:

```java
@Qualifier("bankGateway")
```

Run again with `-parameters` disabled. The qualifier is stored as annotation metadata on the injection point and does not need the parameter name to select the bean by that qualifier.

### Exercise 4 — Comparing 6.0 with 6.1

Use the same project and same bean configuration. Test an old build having local-variable debug information without `-parameters`, then compare with Framework 6.1+. The goal is to understand why older projects could work via LVT discovery and why that mechanism is gone after upgrading.

Do not keep old debug configuration as a long-term solution; enabling `-parameters` is what Spring recommends.

### Exercise 5 — Observing 6.2

With a project running Spring Framework 6.2, create two beans of the same type and try `@Primary`, `@Priority`, parameter-name matching, and `@Qualifier` signals. Then try `@Fallback` on a default bean.

Note differences when changing Framework versions and explain why `@Qualifier` is clearer than letting multiple priority signals compete.

### Exercise 6 — Comparing IDE and JAR

Build and run the application from the IDE, then build a JAR with Gradle/Maven and run `java -jar`. Use reflection or `javap` to verify class files in both outputs contain `MethodParameters`. If behavior differs, compare compiler options between the two build flows.

## 18. Official references

- [Spring Framework 6.2 — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html): type matching rules, qualifiers, parameter-name fallback, `-parameters`, and the 6.2 fast shortcut.
- [Spring Framework 6.1 Release Notes — Parameter Name Retention](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes): removal of `LocalVariableTableParameterNameDiscoverer` and compiler configuration.
- [Spring Framework 6.2 Release Notes — Core Container](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes): autowiring algorithm changes, priority ranking, and `@Fallback`.
- [Spring Boot 3.3 System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): compatible Spring Framework 6.1 line.
- [Spring Boot 3.4 System Requirements](https://docs.spring.io/spring-boot/3.4/system-requirements.html): compatible Spring Framework 6.2 line.

Parameter names can help Spring pick the right bean when multiple candidates share a type, yet they only work when names exist in runtime metadata and the version's precedence rules allow that signal. With Java and Spring Framework 6.1+, compile with `-parameters`. When bean selection matters to business logic, express the choice with `@Qualifier` so intent does not depend on parameter names or algorithm changes across versions.

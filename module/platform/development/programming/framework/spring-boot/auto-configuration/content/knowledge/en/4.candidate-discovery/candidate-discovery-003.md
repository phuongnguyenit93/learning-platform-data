# Registering Nested Classes Using Binary Names with `$` in Spring Boot Auto-Configuration

## 1. Why Do Nested Class Names Contain `$`?

When an `@AutoConfiguration` class is declared **inside** another Java class, source code normally uses a dot to reference it, whereas Spring Boot's auto-configuration candidate declaration file must use the **binary name**. The boundary between the *outer class* and the *nested member class* in a binary name is represented by the `$` character.

Java class example:

```java
package com.example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;

public final class OuterAutoConfigurations {
    private OuterAutoConfigurations() {}

    @AutoConfiguration
    public static class GreetingAutoConfiguration {
    }
}
```

Three different representations of the `GreetingAutoConfiguration` class:

| Concept | Exact String | When Used |
| --- | --- | --- |
| Simple name | `GreetingAutoConfiguration` | `getSimpleName()`; display |
| Canonical / source syntax name | `com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration` | Type references in Java source code, `getCanonicalName()` |
| **Binary name** | `com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration` | `Class.getName()`, `Class.forName(...)`, **`AutoConfiguration.imports`** |

The `.` separators between **package** segments remain unchanged. Only the separator between the **outer class and nested class** changes to `$`. With multiple levels of nesting such as `Outer.Middle.Inner`, the binary name is `Outer$Middle$Inner` (with the appropriate package prefix).

This rule comes from the Java specification (JLS §13.1). **Spring Boot did not invent a custom syntax**; Boot uses Java's binary class identifier when reading the class names listed in the imports file.

Lesson goals: accurately determine the name to declare, understand the candidate discovery mechanism, build a runnable illustrative project, know how to inspect classfiles/resources after packaging, and diagnose naming errors.

## 2. Why Does the Dot from Java Source Not Work in Imports?

In source code, Java allows:

```java
OuterAutoConfigurations.GreetingAutoConfiguration.class
```

Because the compiler knows `GreetingAutoConfiguration` is a **member class** of `OuterAutoConfigurations`. However, a resource file outside source code only contains **class name strings**; there is no Java source name-resolution syntax there. Class-loading utilities by binary name such as `Class.forName(...)` require `$` at the member class position.

With the example above:

```java
Class<?> nested = OuterAutoConfigurations.GreetingAutoConfiguration.class;
System.out.println(nested.getCanonicalName());
System.out.println(nested.getName());
```

Two lines of output:

```text
com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration
com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
```

This is a snippet executed **inside a Java class that can access the type above**, not a standalone Java file.

Also distinguish between a binary name and a file path:

- **Binary name:** `com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration`.
- **Classfile path:** `com/example/autoconfig/OuterAutoConfigurations$GreetingAutoConfiguration.class`.
- **JVM internal name elsewhere:** may use `/` instead of package dots.
- **Spring bean name:** e.g., `defaultGreeter`, which is the identifier of the **bean**, not the auto-config class name.

Do not replace every `.` with `$`: doing so turns the package portion into an invalid string.

## 3. Pure Java 17 Example to Inspect Binary Names

This is a program **with no Spring dependencies**. Create file `src/com/example/NestedNamesDemo.java`:

```java
package com.example;

public class NestedNamesDemo {
    public static class Nested {
        public static class Deep {
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> nested = Nested.class;
        Class<?> deep = Nested.Deep.class;

        System.out.println("SIMPLE=" + nested.getSimpleName());
        System.out.println("CANONICAL=" + nested.getCanonicalName());
        System.out.println("BINARY=" + nested.getName());
        System.out.println("DEEP_BINARY=" + deep.getName());

        Class<?> loaded = Class.forName("com.example.NestedNamesDemo$Nested");
        System.out.println("CLASS_FOR_NAME=" + (loaded == nested));

        try {
            Class.forName("com.example.NestedNamesDemo.Nested");
            System.out.println("DOTTED_LOOKUP=found");
        } catch (ClassNotFoundException ex) {
            System.out.println("DOTTED_LOOKUP=not-found");
        }
    }
}
```

In the directory containing `src`, using JDK 17+:

```bash
javac -encoding UTF-8 -d out src/com/example/NestedNamesDemo.java
java -cp out com.example.NestedNamesDemo
```

**Exact** stdout:

```text
SIMPLE=Nested
CANONICAL=com.example.NestedNamesDemo.Nested
BINARY=com.example.NestedNamesDemo$Nested
DEEP_BINARY=com.example.NestedNamesDemo$Nested$Deep
CLASS_FOR_NAME=true
DOTTED_LOOKUP=not-found
```

`Class.getName()` returns the binary name, while `getCanonicalName()` returns the canonical name for an ordinary named member class. `Class.forName("...$Nested")` finds the exact class, whereas `Class.forName("...NestedNamesDemo.Nested")` does not treat that dot as a member-class separator.

In Java source, `$` is inside a **string literal**, so no special escaping is needed. If a command is typed directly into a shell, `$` may be interpreted as a variable by the shell: command quoting is covered in the troubleshooting section.

Note: `Class.forName` does not instantiate a Spring bean, does not create an `ApplicationContext`, and does not evaluate `@ConditionalOnMissingBean`. It only illustrates how Java identifies/loads classes.

## 4. Where Does Spring Boot Discover Auto-Configuration Candidates?

In **Spring Boot 3.x**, a library publishes auto-configuration via the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Basic format: **one binary class name per line**, optionally with comment lines starting with `#`.

**Correct for the nested auto-configuration in section 1:**

```text
com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
```

**Wrong: canonical name with Java source dots:**

```text
com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration
```

**Wrong: classfile path:**

```text
com/example/autoconfig/OuterAutoConfigurations$GreetingAutoConfiguration.class
```

**Wrong: Java import statement instead of class name:**

```java
import com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration;
```

In the imports file, Boot needs the exact **name of the class carrying `@AutoConfiguration`**, not its enclosing class (unless the enclosing class is also designed and registered as an auto-config in its own right).

A discovered auto-configuration candidate is **not guaranteed to create a bean**. Conditions such as `@ConditionalOnClass`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean` can cause the configuration or certain `@Bean` methods not to be applied. Clearly distinguish **candidate found** from **bean registered**.

### 4.1. Why Should a Nested Class Be Declared `static`?

An ordinary non-static inner class carries an implicit reference to an instance of the outer class. A nested auto-configuration should be a **named static member class**, e.g., `public static class GreetingAutoConfiguration`, so that Spring can instantiate it independently without needing an outer instance.

`static` on the class declaration **does not mean** every `@Bean` method inside must be static. It only states that the nested class does not depend on an outer instance.

Do not use local/anonymous classes as auto-config candidates. Compiler-generated names may include numbers like `Outer$1` or `Outer$1Local`, which are unsuitable as public, stable identifiers in an imports file.

### 4.2. Auto-Configuration Should Not Be Discovered by Component Scanning

Spring Boot documentation requires auto-configurations to be loaded via the imports list, placed in a separate package, and kept away from being discovered by component scanning as an application component. Placing auto-config in a scanned area can alter the condition/import path designed by Boot.

In the runnable example below, the application main class is in `com.example.app` while the auto-configuration is in `com.example.autoconfig`. Because it is not a subpackage of the app package, the nested configuration will be considered via the **imports file**.

## 5. Complete Spring Boot Example: Nested Class Registered via Binary Name

The example uses **Java 17+**, **Maven**, and **Spring Boot 3.3.13**. It provides a default bean via a nested auto-configuration, prints the binary/canonical names, and tests back-off behavior when the application provides its own bean.

### 5.1. Project Structure

```text
nested-auto-config-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/Greeter.java
    │   ├── app/DemoApplication.java
    │   └── autoconfig/OuterAutoConfigurations.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>nested-auto-config-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. `src/main/java/com/example/api/Greeter.java`

```java
package com.example.api;

@FunctionalInterface
public interface Greeter {
    String greet(String name);
}
```

`Greeter` is a plain Java API; `@FunctionalInterface` does not automatically register a bean.

### 5.4. `src/main/java/com/example/autoconfig/OuterAutoConfigurations.java`

```java
package com.example.autoconfig;

import com.example.api.Greeter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

public final class OuterAutoConfigurations {
    private OuterAutoConfigurations() {
    }

    @AutoConfiguration
    public static class GreetingAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(Greeter.class)
        Greeter defaultGreeter() {
            return name -> "AUTO: Hello, " + name + "!";
        }
    }
}
```

- The outer class `OuterAutoConfigurations` is an ordinary Java **container**.
- The nested static class `GreetingAutoConfiguration` carries `@AutoConfiguration`, so it is the class to list in imports.
- `defaultGreeter` is the default method/bean name; it is **different from the binary name** of the nested class.
- `@ConditionalOnMissingBean(Greeter.class)` allows the default bean to yield if the application already declares a matching `Greeter`.
- To test within a single Maven project, the auto-configuration and API interface live in the same source tree. When publishing a real library, the API and auto-config/starter modules are usually separated according to the appropriate architecture.

### 5.5. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.api.Greeter;
import com.example.autoconfig.OuterAutoConfigurations;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner show(Greeter greeter, ApplicationContext context) {
        return args -> {
            Class<?> type =
                OuterAutoConfigurations.GreetingAutoConfiguration.class;

            System.out.println("BINARY=" + type.getName());
            System.out.println("CANONICAL=" + type.getCanonicalName());
            System.out.println("DEFAULT_BEAN="
                    + context.containsBean("defaultGreeter"));
            System.out.println("MESSAGE=" + greeter.greet("Spring Boot"));
        };
    }
}
```

`OuterAutoConfigurations.GreetingAutoConfiguration.class` is **valid Java source syntax**. `type.getName()` reflects the exact binary name listed in the imports file, while `type.getCanonicalName()` produces the Java source form.

The runner is created when the context starts; Spring uses DI to inject the `Greeter` bean. If no matching bean exists (for example, because the imports file is wrong), runner creation can fail.

### 5.6. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
```

Non-web mode lets the application run the runner and exit. Turning off logging makes the illustrative output easier to read and does not govern auto-configuration.

### 5.7. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

**Single-line** content:

```text
com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
```

The file must exist with the exact name/path when **packaging resources onto the runtime classpath**. Do not add `import`, `;`, `.class`, `/`, or replace `$` with a dot between outer/nested.

### 5.8. Compiling and Running

From the directory containing `pom.xml`:

```bash
mvn -q -DskipTests package
java -jar target/nested-auto-config-demo-1.0.0.jar
```

Stdout printed by the application itself (excluding messages from tools/environment):

```text
BINARY=com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
CANONICAL=com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration
DEFAULT_BEAN=true
MESSAGE=AUTO: Hello, Spring Boot!
```

**Explanation:** Boot finds the exact nested configuration via its binary name, conditions are satisfied, the `defaultGreeter` bean is registered and injected into the runner. Because `com.example.autoconfig` is not under `com.example.app`, this is practical proof of registration via the imports file rather than application package scanning.

### 5.9. Override Experiment to Distinguish Candidate Discovery from Bean Creation

Add the following snippet **inside the `DemoApplication` class**, alongside the `show(...)` method, then rebuild and re-run:

```java
@Bean
Greeter customGreeter() {
    return name -> "CUSTOM: Hi, " + name + "!";
}
```

This is an **addition snippet**, not a standalone runnable file. Expected stdout:

```text
BINARY=com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
CANONICAL=com.example.autoconfig.OuterAutoConfigurations.GreetingAutoConfiguration
DEFAULT_BEAN=false
MESSAGE=CUSTOM: Hi, Spring Boot!
```

The nested auto-configuration is still **recognized**, but `@ConditionalOnMissingBean(Greeter.class)` does not match because an application-declared bean already exists, so the default is **not registered**. The `$` sign only solves candidate identification; it does not force the default bean to always exist.

## 6. Inspecting Classfiles and the Imports Resource After Packaging

After Maven package, the two related classfiles typically look like:

```text
target/classes/com/example/autoconfig/OuterAutoConfigurations.class
target/classes/com/example/autoconfig/OuterAutoConfigurations$GreetingAutoConfiguration.class
```

Note that outer and nested are **two classfiles**. Do not put the outer class name into imports instead of the nested one just because you see an outer class.

You can list the JAR:

```bash
jar tf target/nested-auto-config-demo-1.0.0.jar
```

In the Spring Boot application JAR, look for these entries:

```text
BOOT-INF/classes/com/example/autoconfig/OuterAutoConfigurations.class
BOOT-INF/classes/com/example/autoconfig/OuterAutoConfigurations$GreetingAutoConfiguration.class
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Other entries may appear; the goal is to verify that the nested classfile and the imports file **are both packaged**.

Using JDK `javap` (after compiling):

```bash
javap -classpath target/classes 'com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration'
```

In **Bash/Zsh and PowerShell**, single quotes protect `$` from being interpreted as part of a variable. If double quotes are used in a shell with variable expansion, a string like `Outer$GreetingAutoConfiguration` can be altered before reaching `javap`. Windows `cmd.exe` has different variable expansion rules, so apply quoting according to the actual shell.

There is no need to guess the name manually when you can call `OuterAutoConfigurations.GreetingAutoConfiguration.class.getName()` in Java. That is the direct way to retrieve the binary name for comparison.

## 7. Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `Outer.Nested` not found when Boot reads imports | Used canonical name instead of binary name | Write `Outer$Nested`, keeping package dots intact |
| `Outer$Nested.class` exists yet auto-config does not work | Wrong imports filename/path, resource not packaged, or condition failed | Inspect JAR and condition report |
| Wrote `Outer` in imports | Pointed to enclosing class instead of nested class with `@AutoConfiguration` | Use the exact binary name of the nested candidate |
| Wrote `Outer$Nested` in Java source for member access | Confused binary identifier with Java syntax | Use `Outer.Nested` in source |
| Imports is correct yet `@Bean` bean does not exist | Bean/class/property condition did not match | Check `@Conditional...` and bean definitions |
| Used non-static inner class | Inner instance requires outer instance | Convert to a named static nested class |
| Shell command looks right yet `javap` fails | `$` expanded by shell | Quote the literal properly |
| Wrote `com$example$Outer$Nested` | Replaced package dots too | Use `$` only at nested class boundaries |
| Wrote `Outer$Nested.class` in imports | Confused class name with filename | Remove the `.class` extension |
| Only added name to imports without an actual classfile | Declared candidate without compiling a Java class | Compile and package the actual class |

### 7.1. Nested Auto-Config vs. Nested Configuration Inside an Auto-Config

A `@Configuration` class nested **inside an already-registered auto-configuration** can be processed as an internal configuration if Spring imports/parses it properly and conditions permit. That case **does not by default require every nested helper to appear as a separate line in imports**.

The problem in this lesson is the scenario where **the nested class itself is the auto-configuration candidate to be listed**. In that case, `Outer$NestedAutoConfiguration` must be declared properly in the imports file.

### 7.2. Binary Names in Other Configurations

APIs that take a **class literal** (such as `@Import(Outer.Nested.class)`) use normal Java source syntax. APIs that take a **class name as a string** (such as `@AutoConfiguration(afterName = "...")` or excluding an auto-config by name) must identify the target class accurately, especially when nested. Do not pass a bean name or a file path to an attribute expecting a class name.

For `spring.autoconfigure.exclude`, to exclude a nested auto-config, you can declare it by binary name:

```properties
spring.autoconfigure.exclude=com.example.autoconfig.OuterAutoConfigurations$GreetingAutoConfiguration
```

In a properties file, this is a literal `$`. If passed via the command line, consider shell quoting rules. If excluded while the application still requires `Greeter` without providing another bean, dependency injection can fail at startup.

## 8. Systematic Application and Troubleshooting Workflow

1. **Identify the class carrying `@AutoConfiguration`:** is it a top-level class or a named nested member? Do not look only at the outer container name.
2. **Obtain the binary name:** ideally from `SomeNested.class.getName()` or by checking the classfile. For multiple levels, watch every `$`.
3. **Write imports:** one standard class name per line in the `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` resource.
4. **Verify classfiles:** is the nested class compiled, actually present in the runtime JAR, and in the right package?
5. **Verify the resource:** is the imports file packaged at the exact path?
6. **Start a consuming application:** do not just check that Maven compiles successfully; check whether the context starts and picks up the candidate.
7. **Inspect the condition report:** enable `--debug` to view the *Condition Evaluation Report* if the class was loaded yet the bean is missing; a non-matching condition can be intentional behavior.
8. **Test override:** declare an application bean of the same type to confirm the default's `@ConditionalOnMissingBean` works.
9. **When renaming outer/nested classes:** update the imports file, ordering/exclusion strings, and consider the auto-configuration replacements mechanism when publishing a library with consumers.

With the demo example, you can run:

```bash
java -jar target/nested-auto-config-demo-1.0.0.jar --debug --logging.level.root=DEBUG
```

The condition report can then display details about `GreetingAutoConfiguration` and `defaultGreeter`. If an incorrect binary name was entered in imports, a class-loading error may occur **before a full condition report is produced**; not every missing-bean situation is a missing-bean condition.

## 9. Knowledge Self-Check

**Question 1.** Class `MyAutoConfiguration` is declared `public static` inside `com.acme.Outer`. Which name goes into imports?

**Answer:** `com.acme.Outer$MyAutoConfiguration`.

**Question 2.** What if the class is nested two levels deep as `Outer.Middle.Inner`?

**Answer:** `Outer$Middle$Inner`, with the package prefix using `.` as usual.

**Question 3.** Why is `Class.getCanonicalName()` not the safest way to generate an imports line for a nested class?

**Answer:** For a named member class, it uses `.` between outer and member, whereas imports needs the **binary name** with `$`. Use `Class.getName()`.

**Question 4.** Must every nested class inside an auto-config have its own line in imports?

**Answer:** No. Only classes designed as **separate auto-configuration candidates** need to be listed via this mechanism. Nested helper configurations can be processed within an already-imported configuration.

**Question 5.** The imports file is correct yet `defaultGreeter` does not exist; does that mean `$` is wrong?

**Answer:** You cannot conclude that. The auto-config may have been imported properly while the bean was not registered due to `@ConditionalOnMissingBean` or another condition.

**Question 6.** When using `@Import(Outer.Nested.class)` in Java, must it be changed to `Outer$Nested.class`?

**Answer:** No. `@Import` takes a class literal from Java source, so use `Outer.Nested.class` syntax.

**Question 7.** Why did the example use `public static class GreetingAutoConfiguration`?

**Answer:** A static nested class can be treated by Spring as an independent configuration without needing an outer instance; its binary name is fixed, easy to register, and easy to package.

## 10. References

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): the *Locating Auto-configuration Candidates* section explicitly shows the official example `com.example.Outer$NestedAutoConfiguration`.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName()` returns the binary name of the class; `getCanonicalName()` returns the canonical name when available.
- [Java Language Specification §13.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1): binary name rules for member classes.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): candidate discovery mechanism, conditions, and user configuration overriding defaults.

**Remember:** `Outer.Nested` is the natural reference syntax in **Java source**; `Outer$Nested` is the identifier for a nested member class in **binary name** form. For `AutoConfiguration.imports` in Spring Boot 3.x, write the **binary name**, package the classfiles/resource properly, and then separately verify that the candidate is discovered and whether the bean is created.

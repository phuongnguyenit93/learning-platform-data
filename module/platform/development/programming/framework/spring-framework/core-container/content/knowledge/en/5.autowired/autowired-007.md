# Selecting Beans by Name with `jakarta.annotation.Resource` in the Spring Core Container

## 1. What Problem Does `@Resource` Solve?

In the Spring IoC Container, an application may register **multiple beans of the same Java type**, for example two implementations of `Channel`: `emailChannel` and `smsChannel`. When requesting injection of a `Channel`, a rule is needed to determine **which bean** will be supplied to the object.

The **`jakarta.annotation.Resource`** annotation allows describing a dependency **primarily by bean name**, commonly applied to an **instance field** or **JavaBean property setter** of a Spring-managed bean. This is a standard Jakarta Annotations annotation (JSR-250 lineage), not `org.springframework.beans.factory.annotation.Resource`.

The clearest syntax:

~~~java
// Snippet: these types/beans are defined in the complete project in section 6.
@Resource(name = "smsChannel")
private Channel selected;
~~~

When Spring creates a bean containing this field, it looks up the bean with **name `smsChannel`** and assigns the matching reference to the field. Spring **does not create a new `Channel`** merely because it sees the annotation. If the `smsChannel` bean is not registered, injection typically fails rather than automatically picking another bean name.

**Core topics of this article:**
- How to specify an explicit name using `@Resource(name="...")`;
- How the **default** name is derived from the field or setter property name;
- How **aliases** are handled;
- **The type-fallback exception when no explicit name is specified**;
- Differences from `@Autowired`, `@Qualifier`, and `@Primary`;
- Principles for selecting type-compatible beans, handling missing/duplicate/wrong names, and verifying with Java 17+.

**Scope**: Pure Spring Framework Core Container, Java 17, Maven; no Spring Boot, database, HTTP server, or auto-configuration mechanisms.

## 2. Selection Rules: Explicit Name, Default Name, Then Conditional Fallback

Follow the conceptual flow:

~~~text
          Injection point carrying @Resource
                        |
                 Has name="..."?
                /                \
              YES                 NO
               |                   |
               v                   v
      Use specified name   Use field/setter property name
               |                   |
               v                   v
       Look up bean by name  Bean with default name exists?
               |              /           \
          Name exists?      YES            NO
          /    \             |              |
        YES    NO            v              v
         |      |      Use that named   Fall back by type
         v      v          bean         (enabled by default)
    Check type ERROR         |              |
         |               Check type     Resolve candidate
         v                   |          by type/primary
       Inject              Inject           |
                                            v
                                          Inject
~~~

**Case 1 — Explicit `name` given.** With `@Resource(name="smsChannel")`, Spring looks up **the bean with that exact name** (or a valid alias). If that bean does not exist, it **does not** silently switch to `emailChannel` even if email carries `@Primary`. If the bean with that name has an **incompatible type**, injection also fails.

**Case 2 — No `name` specified.** With `@Resource private Channel smsChannel;`, the default name is **`smsChannel`**, derived from the field name. With `@Resource void setArchiveChannel(Channel c)`, the default name is the JavaBean property name **`archiveChannel`**, not the parameter name `c`.

**Case 3 — Default name does not exist.** In standard Spring configuration, `CommonAnnotationBeanPostProcessor` allows falling back from the default name to **type matching** (the `fallbackToDefaultTypeMatch` flag, `true` by default). If a standout candidate exists via `@Primary` or there is only one matching bean, fallback can resolve successfully. If multiple candidates are ambiguous, it can fail.

**Accurate conclusion:** `@Resource` is **by-name first**, yet saying "`@Resource` only ever looks up by name and can never look up by type" is **inaccurate** when `name` is left blank. Conversely, do not rely on fallback to mask an intentionally misspelled bean name; specify an explicit name when the contract genuinely requires one specific bean.

## 3. How Do `@Resource` and `@Autowired`/`@Qualifier` Differ?

| Criterion | `@Resource` | `@Autowired` + `@Qualifier` |
| --- | --- | --- |
| Annotation | `jakarta.annotation.Resource` | `org.springframework.beans.factory.annotation.Autowired`, `Qualifier` |
| Primary meaning | **References a bean by name** | **Type-based dependency**, qualifier narrows candidates |
| Specified name | `@Resource(name="smsChannel")` | `@Autowired @Qualifier("smsChannel")` |
| If explicit `name` is not found | Name lookup error, does not auto-switch to another bean | Type+qualifier candidate matching may fail |
| If name is omitted | Field/setter property name, then fallback by type if no bean has that name | Resolution by type, metadata, and precedence rules; field/parameter name may assist candidate selection |
| Constructor injection | **Do not use `@Resource` to mark constructors** | `@Autowired` supports constructors; a single constructor usually needs no annotation |
| Multi-parameter methods | Do not use `@Resource` as generic arbitrary multi-argument method injection | `@Autowired` supports multi-parameter methods |
| Multiple beans of same type | Selected directly by name, final type checked | `@Qualifier`, `@Primary`, generics/metadata help resolve |
| Best suited for | Integration points, fixed bean names, alias migration, property-name setters | Constructor DI, programming to interfaces, candidate selection by role/type |

`@Qualifier("smsChannel")` is **not strictly synonymous** with `@Resource(name="smsChannel")`. Spring describes a qualifier as a **filtering criterion within the set of type-matching beans**, not a standalone primary-name lookup decoupled from type. Meanwhile, `@Resource(name=...)` explicitly expresses **identification by bean name**.

**Do not confuse imports:**

~~~java
import jakarta.annotation.Resource;
// Completely different from:
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
~~~

These three imports only illustrate API locations, not a standalone Java program. A project needs **`jakarta.annotation-api`** on the compile classpath to import `@Resource`. Do not use the legacy `javax.annotation.Resource` import for modern Spring Framework 7/Jakarta code.

### Is `@Primary` Needed When Using `@Resource(name="...")`?

No: if the specified name exists and the bean has a compatible type, Spring selects by that name **even when another bean of the same type carries `@Primary`**. `@Primary` matters in situations requiring type-based resolution, such as fallback when no default name exists. The example in section 6 intentionally declares `emailChannel` as primary, yet `@Resource(name="smsChannel")` still picks **SMS**.

## 4. Annotation Locations Supported by Spring

### 4.1. Field (Including Private Instance Fields)

~~~java
@Resource(name = "smsChannel")
private Channel selectedChannel;
~~~

Spring can assign the field after the Java constructor instantiates the bean. No public setter is needed to use field injection. However, an object created with `new Client()` outside Spring does **not** have annotations processed. If the field remains unassigned, accessing it can throw a `NullPointerException`.

Field injection hides dependencies from the constructor and is unsuitable for supplying required dependencies into `final` fields. For new code needing invariants and easy unit testing, consider constructor injection (via `@Autowired` or a single constructor) instead of using `@Resource` just to avoid a few constructor lines.

### 4.2. JavaBean Setter and Default Property Name

~~~java
// Requires a bean named "archiveChannel".
private Channel selected;

@Resource(name = "archiveChannel")
public void setSelected(Channel selected) {
    this.selected = selected;
}
~~~

When an explicit `name` is present, bean name **`archiveChannel`** is chosen. The setter name `setSelected` does not have to match the bean name.

Conversely:

~~~java
// No name specified. Inferred property name is "smsChannel".
private Channel selected;

@Resource
public void setSmsChannel(Channel channel) {
    this.selected = channel;
}
~~~

Spring uses **`smsChannel`** from the property corresponding to method name `setSmsChannel` per JavaBeans convention; it does **not** use the local parameter name `channel` as the default name.

**Limitation:** `@Resource` follows the field/bean property setter contract — unlike `@Autowired`, which can arbitrarily annotate a `configure(A, B)` taking multiple parameters. If a constructor or arbitrary multi-parameter config method is needed, prefer `@Autowired`/factory-method injection with explicit types.

### 4.3. An Alias Is a Valid Name

When a bean is registered with a primary name and an alias:

~~~java
@Bean(name = {"archiveChannel", "oldArchiveChannel"})
Channel archiveChannel() {
    return () -> "ARCHIVE";
}
~~~

`@Resource(name="oldArchiveChannel")` still resolves **the same bean** as `getBean("archiveChannel")`. An alias does not create a second bean definition, duplicate the instance, or turn a singleton into a prototype.

## 5. Spring Infrastructure Processing `@Resource` and Important Errors

The `@Resource` annotation is recognized by Spring via **`CommonAnnotationBeanPostProcessor`**, unlike `AutowiredAnnotationBeanPostProcessor`, which primarily handles `@Autowired` and related injection annotations.

~~~text
Register @Bean / target class
             |
       context.refresh()
             |
       Create Java instance
             |
 CommonAnnotationBeanPostProcessor
       detects @Resource
             |
  Resolve by bean name / type fallback
             |
   Assign field or call property setter
             |
          Init hooks
             |
    Bean returned to client
~~~

`AnnotationConfigApplicationContext` normally pre-registers this annotation infrastructure when the corresponding Jakarta classes **are present on the classpath**. With manually configured XML contexts, `<context:annotation-config/>` or suitable component scanning can help activate the necessary bean post-processors.

**Do not forget the compile/runtime dependency**: `spring-context` is the Spring Core Container, whereas the API declaring `jakarta.annotation.Resource` is provided by **`jakarta.annotation:jakarta.annotation-api`**. The hands-on example declares both directly rather than relying accidentally on transitive dependencies.

Several other important rules:

- **Required by specified name:** `@Resource(name="missingChannel")` has no `required=false` option like `@Autowired`; missing a bean by name usually causes bean creation to fail.
- **Wrong type:** the bean bearing the specified name must be **compatible with the field/property type**. Spring does not inject a `String` into a `Channel` field merely because the bean name matches.
- **Duplicate type:** multiple `Channel` beans are not an error if `@Resource(name=...)` specifies a valid name.
- **No auto-creation:** `@Resource` on a class not managed by Spring or an unregistered bean class does not automatically generate a bean definition.
- **JNDI:** `mappedName`/JNDI configurations in Jakarta EE environments are a separate story. In a normal Spring Core Container, `name` resolves to a **bean name**; do not assume `@Resource(name=...)` always invokes JNDI. If `SimpleJndiBeanFactory` or specific JNDI options are configured, the path can differ.
- **Do not confuse with Spring's `Resource` API:** `jakarta.annotation.Resource` is a **DI annotation**; `org.springframework.core.io.Resource` is an **interface abstracting data sources** such as classpath/file/URL. Both share the word "Resource" yet serve different purposes.

Errors typically appear when eager singletons are created during `refresh()`; if lazy/prototype, they may appear only when the bean is requested. Do not run regex on exception messages instead of reading the root cause and verifying actual names/types.

## 6. Standalone Runnable Java 17 Maven Project: Name Selection and Fallback

The demo includes:
- Three `Channel` beans: `emailChannel` (**`@Primary`**), `smsChannel`, and `archiveChannel` with alias `oldArchiveChannel`.
- **ExplicitNameClient** with `@Resource(name="smsChannel")` → selects SMS even though EMAIL is primary.
- **DefaultFieldClient** with field named `smsChannel` → selects SMS by field name.
- **ExplicitSetterClient** with `@Resource(name="archiveChannel")` on `setSelected` → selects ARCHIVE.
- **DefaultSetterClient** with setter `setArchiveChannel` → selects ARCHIVE by property name.
- **AliasClient** using the alias name → same archive bean instance.
- **FallbackClient** with a field name matching no bean → falls back by type, choosing `emailChannel` due to `@Primary`.
- Two separate error scenarios: nonexistent name and a bean with the right name yet wrong type.

The project only creates a console context and prints identity verifications. **No network, file I/O, Spring Boot, or HTTP.**

### 6.1. Structure

~~~text
resource-by-name-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ResourceByNameDemo.java
~~~

Requirements: **JDK 17+**, Maven 3.9+, and Maven Central/mirror repository to download dependencies on the first run.

### 6.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>resource-by-name-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
        </dependency>
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>3.0.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ResourceByNameDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`maven.compiler.release=17` requests compilation targeting Java 17; the Maven Compiler Plugin invokes `javac` with the proper classpath. Use the `jakarta.annotation.Resource` import with dependency 3.0.0, not `javax.annotation.Resource`. There is no need to enable a Java compiler annotation processing plugin: injection executes **at runtime by Spring**, not via compile-time code generation.

### 6.3. `src/main/java/demo/ResourceByNameDemo.java`

~~~java
package demo;

import jakarta.annotation.Resource;
import org.springframework.beans.BeansException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

public final class ResourceByNameDemo {
    private ResourceByNameDemo() {
    }

    @FunctionalInterface
    public interface Channel {
        String label();
    }

    public static final class ExplicitNameClient {
        @Resource(name = "smsChannel")
        private Channel selected;

        public String selected() {
            return selected.label();
        }

        public boolean same(Channel expected) {
            return selected == expected;
        }
    }

    public static final class DefaultFieldClient {
        @Resource
        private Channel smsChannel;

        public String selected() {
            return smsChannel.label();
        }
    }

    public static final class ExplicitSetterClient {
        private Channel selected;
        private int calls;

        @Resource(name = "archiveChannel")
        public void setSelected(Channel selected) {
            this.selected = selected;
            calls++;
        }

        public String selected() {
            return selected.label();
        }

        public int calls() {
            return calls;
        }
    }

    public static final class DefaultSetterClient {
        private Channel selected;

        @Resource
        public void setArchiveChannel(Channel value) {
            selected = value;
        }

        public String selected() {
            return selected.label();
        }
    }

    public static final class AliasClient {
        @Resource(name = "oldArchiveChannel")
        private Channel selected;

        public boolean same(Channel expected) {
            return selected == expected;
        }
    }

    public static final class FallbackClient {
        @Resource
        private Channel noSuchDefaultName;

        public String selected() {
            return noSuchDefaultName.label();
        }

        public boolean same(Channel expected) {
            return noSuchDefaultName == expected;
        }
    }

    public static final class MissingNameClient {
        @Resource(name = "missingChannel")
        private Channel selected;
    }

    public static final class WrongTypeClient {
        @Resource(name = "labelBean")
        private Channel selected;
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("emailChannel")
        @Primary
        public Channel emailChannel() {
            return () -> "EMAIL";
        }

        @Bean("smsChannel")
        public Channel smsChannel() {
            return () -> "SMS";
        }

        @Bean(name = {"archiveChannel", "oldArchiveChannel"})
        public Channel archiveChannel() {
            return () -> "ARCHIVE";
        }

        @Bean("labelBean")
        public String labelBean() {
            return "NOT_A_CHANNEL";
        }
    }

    public static void main(String[] args) {
        // 1) Valid context: three beans of the same Channel type.
        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(AppConfig.class);
            context.registerBean(ExplicitNameClient.class);
            context.registerBean(DefaultFieldClient.class);
            context.registerBean(ExplicitSetterClient.class);
            context.registerBean(DefaultSetterClient.class);
            context.registerBean(AliasClient.class);
            context.registerBean(FallbackClient.class);
            context.refresh();

            Channel sms = context.getBean("smsChannel", Channel.class);
            Channel archive =
                    context.getBean("archiveChannel", Channel.class);
            Channel email = context.getBean("emailChannel", Channel.class);

            ExplicitNameClient explicit =
                    context.getBean(ExplicitNameClient.class);
            ExplicitSetterClient setter =
                    context.getBean(ExplicitSetterClient.class);
            FallbackClient fallback =
                    context.getBean(FallbackClient.class);

            System.out.println("explicit.name=" + explicit.selected());
            System.out.println("explicit.sameSms=" + explicit.same(sms));
            System.out.println("default.field="
                    + context.getBean(DefaultFieldClient.class).selected());
            System.out.println("setter.explicit=" + setter.selected());
            System.out.println("setter.calls=" + setter.calls());
            System.out.println("setter.default="
                    + context.getBean(DefaultSetterClient.class).selected());
            System.out.println("alias.sameArchive="
                    + context.getBean(AliasClient.class).same(archive));
            System.out.println("alias.hasDefinition="
                    + context.containsBeanDefinition("oldArchiveChannel"));
            System.out.println("fallback.primary=" + fallback.selected());
            System.out.println("fallback.sameEmail=" + fallback.same(email));
            System.out.println("context.beanByType="
                    + context.getBean(Channel.class).label());
        }

        // 2) Channel beans exist, but the requested explicit name does not.
        try (var missing = new AnnotationConfigApplicationContext()) {
            missing.register(AppConfig.class);
            missing.registerBean(MissingNameClient.class);
            missing.refresh();
        } catch (BeansException expected) {
            System.out.println("missingExplicit.failed=true");
        }

        // 3) Bean named labelBean exists, but it is a String, not a Channel.
        try (var wrong = new AnnotationConfigApplicationContext()) {
            wrong.register(AppConfig.class);
            wrong.registerBean(WrongTypeClient.class);
            wrong.refresh();
        } catch (BeansException expected) {
            System.out.println("wrongType.failed=true");
        }
    }
}
~~~

### 6.4. Why Does This Demo Properly Test By-Name Selection?

1. Spring sees both `emailChannel` and `smsChannel` are `Channel`s, yet `@Resource(name="smsChannel")` explicitly picks **SMS**. Email's `@Primary` does not alter the requested name.
2. `DefaultFieldClient.smsChannel` specifies no `name`, so the default name from the **field** matches `smsChannel`. Even though email is primary, the **bean name match** is used first.
3. `setSelected(...)` has the annotation name `archiveChannel`, so the Java setter name **does not dictate** the bean name.
4. `setArchiveChannel(...)` specifies no `name`, so the JavaBeans property name **`archiveChannel`** matches the bean.
5. `oldArchiveChannel` is an **alias** for bean `archiveChannel`. Spring recognizes the alias during lookup; `==` confirms it is the same singleton object.
6. `noSuchDefaultName` has no bean with that name. Only then does lookup fall back by **type**; `emailChannel` carries `@Primary`, so EMAIL is selected.
7. In `MissingNameClient`, the **explicit name does not exist** even though three beans of that type exist. Spring does not discard `name` to arbitrarily pick another bean.
8. In `WrongTypeClient`, bean `labelBean` exists yet is a `String`; it cannot be assigned to a `Channel` field. `@Resource` does not force a Java field to accept a wrong type.
9. `@Bean` and `registerBean` provide metadata sources for the context; the `Client` classes are not required to have `@Component` once **explicitly registered**. Spring processes `@Resource` on instances created by the container.

**This is an intentional console demo:** the two failing contexts may emit startup failure messages from the logger. Expected stdout counts only `System.out.println` statements in `main`, without asserting Spring's exact stack trace.

## 7. Run Commands and Expected Stdout

Open a terminal in the `resource-by-name-demo` directory, check:

~~~bash
java -version
javac -version
mvn -version
~~~

Java/Maven versions displayed depend on the environment. From the directory with `pom.xml`, run:

~~~bash
mvn -q clean compile exec:java
~~~

**13 stdout lines printed by the Java program itself**, excluding Maven/backend logging:

~~~text
explicit.name=SMS
explicit.sameSms=true
default.field=SMS
setter.explicit=ARCHIVE
setter.calls=1
setter.default=ARCHIVE
alias.sameArchive=true
alias.hasDefinition=false
fallback.primary=EMAIL
fallback.sameEmail=true
context.beanByType=EMAIL
missingExplicit.failed=true
wrongType.failed=true
~~~

These values are deterministic: independent of timezone, randomness, network, `hashCode()`, or Spring internal names. In `==` comparisons, only **reference identity** of singletons retrieved from **the same context** is checked; `String.equals` is used when comparing content values.

Note that `context.getBean(Channel.class)` chooses primary because multiple candidates share the type. If `@Primary` were removed and no qualifier/other discriminator existed, type-based lookup itself could become ambiguous, whereas `@Resource(name="smsChannel")` could still find SMS by name.

## 8. Plain Java 17: Distinguishing Lookup by Name from Lookup by Type

To see what by-name means without confusing it with runtime annotations, create a standalone file **`ManualNameSelection.java`** and run it with `javac`/`java` (no Spring/Jakarta needed):

~~~java
import java.util.Map;

public class ManualNameSelection {
    interface Channel {
        String label();
    }

    public static void main(String[] args) {
        Map<String, Channel> beans = Map.of(
                "emailChannel", () -> "EMAIL",
                "smsChannel", () -> "SMS");

        Channel chosen = beans.get("smsChannel");
        System.out.println("selected=" + chosen.label());
        System.out.println("missingName="
                + (beans.get("unknownChannel") == null));
        System.out.println("otherAvailable="
                + beans.containsKey("emailChannel"));
    }
}
~~~

Run from the directory containing the file:

~~~bash
javac ManualNameSelection.java
java ManualNameSelection
~~~

Stdout:

~~~text
selected=SMS
missingName=true
otherAvailable=true
~~~

The Java map here is **not a Spring BeanFactory**; it simply helps visualize that looking up name `smsChannel` differs from looking up `emailChannel`, and a nonexistent name does not mean no other objects exist. Spring adds type checking, bean definitions, scope, lifecycle, aliases, and optional fallback for the **case where no explicit name is specified**.

**Do not infer from the Java map that Spring always requires `@Primary`**. For an explicit name, even with multiple implementations of the same type, a valid name match suffices to identify the bean to inject (provided the type is compatible).

## 9. Advanced Cases and Limitations to Remember

### `@Resource` Is Not a General Optional Annotation

The `jakarta.annotation.Resource` annotation **does not have** a `required=false` attribute like Spring's `@Autowired`. If a dependency is genuinely optional in business terms, consider `Optional<T>`/providers or a Spring-compatible default strategy design; do not assume a misspelled `@Resource(name="...")` will stay silent.

A Spring bean with multiple `@Resource` fields still depends on those resources at each injection point. If one required resource fails to resolve, bean creation can fail even if earlier fields were already injected.

### Fallback Can Be Configured

`CommonAnnotationBeanPostProcessor` has the `setFallbackToDefaultTypeMatch(boolean)` setting, `true` by default. In a custom configuration set to `false`, `@Resource` **without an explicit name** must also look up by its default name; there is no longer a type fallback when the default name is absent. Do not build business behavior around a custom setting without verifying it.

### Referencing Infrastructure Provided Automatically by Spring

Spring documentation notes that when `@Resource` has no `name`, type fallback can also resolve certain well-known dependencies such as `ApplicationContext`, `BeanFactory`, `ResourceLoader`, or `ApplicationEventPublisher`. This does not mean you registered an additional bean definition under any arbitrary field name.

### Duplicate Bean Names Are Not the Same as Aliases

Registering two bean definitions with the same name can cause overriding errors or depend on overriding policy. Conversely, an alias like `oldArchiveChannel` points to **a single definition**. When debugging, `containsBean("oldArchiveChannel")` can return `true` while `containsBeanDefinition("oldArchiveChannel")` is `false`.

### `lookup`, `mappedName`, JNDI

`@Resource` also has attributes serving Jakarta/JNDI environments depending on configuration. They are **not** a reason to turn `@Resource(name=...)` into a JNDI lookup in an ordinary Spring application. Consult Spring documentation and the annotation API if the application runs on a Jakarta EE server.

### Bean Name Stability Is a Configuration Contract

If a service is written with `@Resource(name="smsChannel")`, renaming that bean can prevent the application from starting. When renaming during refactoring, use a controlled alias during transition or update injection points and tests in sync. Do not add aliases arbitrarily to work around design ambiguity.

## 10. Common Errors and Diagnostic Directions

| Symptom | Possible Cause | Check / Fix |
| --- | --- | --- |
| `package jakarta.annotation does not exist` | Missing Jakarta Annotations API on compile classpath | Add `jakarta.annotation:jakarta.annotation-api` dependency and sync Maven |
| `@Resource` field stays null when object is `new`'d | Object is outside the Spring IoC Container | Fetch a Spring bean or pass dependencies via constructor in unit tests |
| Bean exists yet `@Resource(name="...")` reports not found | Explicit name does not match actual bean name or alias | Check `@Bean(name=...)`, scan names, aliases, active context |
| Matching bean name exists yet injection fails on type | Field/setter type is incompatible with actual bean | Fix the bean name or declared type; do not force an invalid cast |
| `@Resource` matches a `String` bean name, field expects `Channel` | Name matches but wrong type | Fix the field name/`name` or corresponding definition |
| Unnamed `@Resource` unexpectedly picks primary | Default field/property name has no bean → type fallback | Specify `name` explicitly or clarify the field name |
| Cannot pick bean due to multiple fallback candidates | No suitable primary/selection rule | Specify an explicit name on `@Resource`, or configure type resolution |
| `@Primary` does not override `@Resource(name=...)` | Explicit by-name takes precedence; this is expected behavior | Do not rely on primary to override an explicit name |
| Setter method is not called | Not a Spring-managed bean, processor missing, or method is not a valid property setter | Check registration, annotation, JavaBean setter signature |
| `@Resource` on constructor/multi-param method does not work | Annotation location is unsupported for that DI style | Use `@Autowired`/constructor/factory-method injection |
| `javax.annotation.Resource` present on Spring 7 yet fails to work | Legacy package, not the supported `jakarta.annotation.Resource` | Use the proper Jakarta import/dependency version |
| Startup error log appears despite catching exception | Spring logger may log failure when refresh fails | Compare application-printed stdout lines, inspect actual root cause |
| XML context does not process `@Resource` | Annotation processor not registered | Use `<context:annotation-config/>` or appropriate configuration |
| `@Resource` confused with file resource | Both contain "Resource" yet are different APIs | Compare `jakarta.annotation.Resource` and `org.springframework.core.io.Resource` |
| Beans share interface yet `@Autowired` picks wrong one | Type/qualifier candidate resolution differs from by-name | Use qualifier/primary matching contract or explicit `@Resource` |

**Ordered checks:** (1) is the target bean managed by Spring; (2) is the Jakarta import right; (3) is `CommonAnnotationBeanPostProcessor` running; (4) what is the explicit/default name; (5) does the bean name/alias exist; (6) is the type compatible; (7) is there a fallback/type ambiguity? Distinguish Maven/classpath errors from Spring bean resolution errors.

Do not infer that matching a Java class name results in matching a bean name; class `EmailChannel` and registered name `emailChannel` can be two separate identifier layers. When testing by name, changing component scan strategies or renaming `@Bean` methods can also break contracts if names are not declared explicitly.

## 11. Predict-and-Verify Practice

Make **each independent change** on a copy of the project and restore the original source before comparing with section 7's expected stdout:

1. **Change explicit name:** `@Resource(name="emailChannel")` on `ExplicitNameClient`. Predict `explicit.name=EMAIL`, `explicit.sameSms=false`.
2. **Remove `@Primary`:** leave three `Channel` beans of the same type. Which by-name lookups still succeed, and how will `FallbackClient`/type-based lookup change?
3. **Rename field:** change `DefaultFieldClient.smsChannel` to `selectedChannel` without adding `name`. Predict falling back to primary instead of picking SMS.
4. **Specify field name:** add `@Resource(name="smsChannel")` after renaming the field. Verify explicit name brings behavior back to SMS.
5. **Rename setter:** change `setArchiveChannel` to `setSmsChannel` in `DefaultSetterClient`, keeping one parameter and no `name`. Predict `setter.default=SMS`.
6. **Explicit setter:** rename `setSelected` to another setter name while keeping `@Resource(name="archiveChannel")`. Does the selected bean change?
7. **Alias:** remove `oldArchiveChannel` from the `@Bean(name={...})` list. Observe `AliasClient` failing bootstrap; no second bean was deleted.
8. **Wrong type:** change `WrongTypeClient.selected`'s field type to `String`. Predict the scenario where name matching `labelBean` becomes valid.
9. **Missing bean:** try `@Resource(name="missingChannel")`, then add that exact bean name in configuration; observe the context no longer reporting a missing name.
10. **Customize fallback:** investigate `CommonAnnotationBeanPostProcessor.setFallbackToDefaultTypeMatch(false)`, predict the impact on `FallbackClient` while leaving explicit names unaffected.
11. **Verify identity:** print `context.getBean("oldArchiveChannel")==context.getBean("archiveChannel")`; with default singleton scope it will be `true`.
12. **Constructor injection:** write a class with a constructor accepting `Channel` and created by a `@Bean` method; use `@Qualifier` on the factory-method argument instead of putting `@Resource` on the constructor.
13. **Plain Java unit test:** pass a fake `Channel` into a business class constructor. Compare testability against a field-injected class requiring context/reflection.
14. **Multiple contexts:** create two contexts from `AppConfig`, compare `smsChannel` instances; Spring singletons default per bean definition/context, not global JVM singletons.

### Checklist

- [ ] Import **`jakarta.annotation.Resource`** properly, not `javax.annotation.Resource`.
- [ ] Know `@Resource(name="x")` looks up **bean name/alias x** and checks the type.
- [ ] Know default names come from the **field name** or **JavaBean setter property name**.
- [ ] Know type fallback **only applies when no explicit name is given**, when the default name does not exist and configuration permits.
- [ ] Understand `@Primary`'s effect during fallback, without confusing it with explicit by-name.
- [ ] Use `@Resource` in supported field/property setter locations, without applying it like `@Autowired` on constructors/multi-param methods.
- [ ] Distinguish an alias from a new bean definition.
- [ ] Know that when a name is missing or type mismatches, bean creation can fail.
- [ ] Run the Java 17 Maven demo producing the exact 13 stdout lines, and plain Java `javac`/`java` producing 3 lines.
- [ ] Know the role of `CommonAnnotationBeanPostProcessor` and the `jakarta.annotation-api` dependency.

## 12. Summary and Official Documentation

`@Resource` expresses **a bean reference by name** in the Spring Core Container:

- **With `name`:** resolves the bean by that name/alias; does not arbitrarily switch to another bean of the same type when the name does not exist.
- **Without `name`:** uses the field name or setter's JavaBean property name. If no bean with that name exists, Spring can fall back to type matching per default processor policy.
- **Data type always matters:** a name match does not bypass Java's type-safety rules.
- **`@Primary` and `@Qualifier` do not replace `@Resource`'s name definition**; they belong primarily to dependency selection by type/qualifier.
- Beans must belong to the Spring context and the annotation processor must be present. Creating an object manually via `new` performs no injection.

Documentation:
- [Spring Framework — Injection with @Resource](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/resource.html)
- [Spring Framework — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework — Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Bean Definition Naming and Aliasing](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring API — CommonAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/CommonAnnotationBeanPostProcessor.html)
- [Jakarta Annotations API — `Resource`](https://jakarta.ee/specifications/annotations/3.0/apidocs/jakarta.annotation/jakarta/annotation/resource)
- [Maven Central — Jakarta Annotations API 3.0.0](https://central.sonatype.com/artifact/jakarta.annotation/jakarta.annotation-api/3.0.0)

**Practical takeaway:** When `@Resource` selects a surprising bean, do not rush to change `@Primary`. First check **whether the name is explicit or default**, verify whether the bean/alias exists, check the **type**, and only then examine **type fallback**. Following that order helps you use `@Resource` consistently, keep code testable, and prevent wiring bugs in Spring applications.
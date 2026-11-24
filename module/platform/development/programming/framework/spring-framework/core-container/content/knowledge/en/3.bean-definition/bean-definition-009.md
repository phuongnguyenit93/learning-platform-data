# Name Collisions and Bean Definition Overriding Policies — Spring Framework Core Container

## 1. Objective: The Same Bean Name Is an Identity Collision

In the Spring IoC container, each **bean definition** is registered under a **bean name**. If two configuration sources attempt to register **two different definitions under the same name** in the same registry, a **bean definition name collision** occurs. Spring may allow the later registration to replace the older definition, or reject the override operation, depending on the **container's policy**.

Key points:

- **Name collision:** multiple bean definitions attempt to use the same **name**, regardless of whether their classes differ or match.
- **Multiple beans of the same type:** two beans with **different names** and the same Java type are valid, though a type-based injection point may fail to **select a single candidate**. That is an *autowiring ambiguity* issue, not a duplicate-name error.
- **Bean alias:** a secondary name pointing to **one bean**; it does not create an independent bean definition. Aliases can interact with name collision checks, but must not be confused with overriding two definitions.
- **Definition override:** when allowed, the new definition replaces the old definition under the **same registry key**. It is neither a "merge of two beans" nor creating two competing instances under the same name.

By the end of this lesson, you will be able to:

1. Distinguish `BeanDefinitionOverrideException` from `NoUniqueBeanDefinitionException`.
2. Understand `DefaultListableBeanFactory.setAllowBeanDefinitionOverriding(boolean)` and how to control the policy via `AnnotationConfigApplicationContext`.
3. Explain the difference between the **Spring Framework default** and the **Spring Boot default**.
4. Run a Java 17+ program verifying both branches — **REJECTED** when disallowed and **SECOND** when overriding is allowed — with deterministic output.
5. Understand the effects of registration order, aliases, bean names, `@Bean`/component scanning, bean scope, and refresh timing.
6. Know how to choose a policy and troubleshoot real projects without arbitrarily enabling overriding just to get the application to start.

**Scope:** focuses on bean names and bean definition overriding in the Spring Core Container. Spring Boot is not required to run the main example.

## 2. Bean Name, Bean Definition, Instance, and Alias

A bean definition provides **metadata** for Spring to create/manage an object: class or factory method, scope, laziness, dependencies, init/destroy metadata, and other attributes. The registry maps a **name** to a definition.

~~~text
BeanDefinitionRegistry
  "notificationClient" -> BeanDefinition #A -> new ChannelClient("FIRST")
  "metricsClient"      -> BeanDefinition #B -> new ChannelClient("METRICS")
  
Bean aliases (if registered)
  "preferredClient" -> "notificationClient"
~~~

In the example above, `notificationClient` and `metricsClient` are **two different bean names**, even though both have class `ChannelClient`. `preferredClient` is merely an **alias**, with no third definition.

If you subsequently register:

~~~text
registerBeanDefinition("notificationClient", BeanDefinition #C)
~~~

then the registry must handle the fact that `notificationClient` **already exists**. Depending on the policy, it either rejects definition #C or replaces the old mapping with definition #C.

### Table Distinguishing Four Cases

| Situation | Is it a definition name collision? | Primary Outcome |
| --- | --- | --- |
| Two bean definitions with the same bean name in the same registry | Yes | Rejected or replaces old definition according to policy |
| Two beans with different names, same Java class | No | Two valid beans; may cause ambiguity when injecting by type alone |
| One bean name with one or more aliases | Not two definitions on its own | All names point to the same bean |
| Two bean definitions with the same name in two independent contexts | Not necessarily | Each context has its own registry; consider parent-child relationships if present |

`NoUniqueBeanDefinitionException` indicates that the container cannot resolve **one candidate from multiple beans** during a type-based lookup/injection. By contrast, `BeanDefinitionOverrideException` occurs during the **registration phase when a duplicate bean name is disallowed**. The fixes differ; do not tweak qualifiers to mistakenly treat a registry name collision.

## 3. Spring Framework and Spring Boot Have Different Defaults

In **Spring Framework 6.2**'s `DefaultListableBeanFactory`, the default **allows bean definition overriding**; when registering another definition under the same name, the later definition can replace the earlier one.

Spring provides the API:

~~~java
context.setAllowBeanDefinitionOverriding(false);
context.setAllowBeanDefinitionOverriding(true);
~~~

These are **alternative choices**, not two lines to call consecutively in the same program to "combine" policies. `AnnotationConfigApplicationContext` inherits this API from `GenericApplicationContext`; you can also configure the underlying `DefaultListableBeanFactory` directly.

**Spring Boot disallows bean definition overriding by default** in standard configuration. Boot provides the property:

~~~properties
spring.main.allow-bean-definition-overriding=false
~~~

This is a **Spring Boot property example**; it has no effect when using plain Spring Framework's `new AnnotationConfigApplicationContext()` without Boot as the host. If you genuinely want to change the policy in Boot, you can configure:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

However, **you should not use `true` as a blanket fix for every duplicate-name error**: it can hide configuration bugs, silently replacing an expected bean with an unintended implementation.

| Context | Typical Default | How to Set Explicitly |
| --- | --- | --- |
| Spring Framework `DefaultListableBeanFactory` | Overriding allowed | `setAllowBeanDefinitionOverriding(false/true)` |
| Plain Spring `GenericApplicationContext` / `AnnotationConfigApplicationContext` | Follows BeanFactory, allowed by default | `context.setAllowBeanDefinitionOverriding(false/true)` |
| Spring Boot | Disallowed by default | Property `spring.main.allow-bean-definition-overriding` or equivalent Boot API |

**Recommendation for demos and tests:** always **set the policy explicitly** right when creating the context, before registering definitions that might collide. This prevents results from depending on assumptions about the host framework and version.

## 4. Disallowing Overriding: Fail Fast at Registration Time

Suppose the registry currently holds:

~~~java
context.registerBeanDefinition(
        "notificationClient",
        createDefinition("FIRST"));
~~~

When the policy is `false`, attempting to register again:

~~~java
context.registerBeanDefinition(
        "notificationClient",
        createDefinition("SECOND"));
~~~

will **be rejected** because of the duplicate bean name. When calling `registerBeanDefinition` programmatically, `BeanDefinitionOverrideException` is thrown immediately on the second registration call, **before `refresh()` is called**. The original definition remains intact, unreplaced by the failed new definition.

Benefits of disallowing overriding:

- Catches duplicate-name errors across modules/configurations early.
- Reduces the risk of a component being silently replaced during refactoring, library upgrades, or expanded component scanning.
- Makes the registration contract predictable: a taken name cannot be hijacked by another definition.
- Suits environments requiring strict configuration and explicit startup testing.

This does **not** prevent having multiple beans of the same class under **different names**, nor does it solve type-based dependency ambiguity. A Spring registry can disallow overriding while still holding two differently named `MailSender` beans.

## 5. Allowing Overriding: Later Definition Replaces the Older One

When setting `setAllowBeanDefinitionOverriding(true)`:

~~~java
context.registerBeanDefinition(
        "notificationClient",
        createDefinition("FIRST"));

context.registerBeanDefinition(
        "notificationClient",
        createDefinition("SECOND"));
~~~

in the sequential pre-`refresh()` registration shown in the example, the second definition replaces the first **under the same name**. When the context instantiates the `notificationClient` bean, it uses the active definition and creates an object with source `SECOND`.

Distinguish clearly:

- This is **replacing a definition**, not creating two singleton beans with the same name.
- The old definition is **no longer** reachable by that bean name. Because the example registers both **before refresh**, no old singleton existed first and got mutated afterward in this program.
- **Do not arbitrarily mutate metadata or override bean definitions after the context has refreshed and instances have been created.** Caches, dependency graphs, and lifecycles may already be established; mutating configuration at runtime is not equivalent to a fresh bootstrap.
- In configurations combining `@Configuration`, `@Bean`, component scanning, imports, and post-processors, Spring runs multiple configuration-processing steps. **Do not rely on accidental ordering across multiple sources** to pick "who wins". Registration conditions and duplicate-detection mechanisms can affect the exact outcome. The demo uses sequential API registration so the result is deterministic.

### Why Should Overriding Not Be Used as a Normal Implementation-Selection Mechanism?

If you need to choose between two implementations per environment, it is usually better to design explicitly with **distinct bean names, qualifiers, primary, profiles, conditions, or intentional factory methods**, depending on context; do not intentionally register duplicate names hoping source load order remains consistent. Overriding can be useful for test overrides or controlled infrastructure, provided the registration site and verified evidence are explicitly documented.

## 6. Standalone Runnable Java 17+ Program

The example uses **JDK 17+**, Maven, and **Spring Framework 6.2.19** (`spring-context` module). This version is pinned for reproducibility, not a claim of being the latest Spring release.

The demo creates **two independent contexts**:

- The first context has policy **false**: the second registration is rejected; the active bean remains FIRST.
- The second context has policy **true**: the second registration replaces the definition; the active bean is SECOND.
- The second context also registers an alias to prove that an alias **is not a new bean definition**.

No Spring Boot, database, network server, or Spring MVC is required.

~~~text
bean-override-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanOverridePolicyDemo.java
~~~

### 6.1. `pom.xml` File

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-override-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.BeanOverridePolicyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven downloads `spring-context` and its dependent modules according to the POM configuration. With manual `javac`/`java`, those JARs must be added to the compile/runtime classpaths.

### 6.2. `src/main/java/demo/BeanOverridePolicyDemo.java` File

~~~java
package demo;

import java.util.Objects;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionOverrideException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class BeanOverridePolicyDemo {
    private BeanOverridePolicyDemo() {}

    public static final class ChannelClient {
        private final String source;

        public ChannelClient(String source) {
            this.source = Objects.requireNonNull(source);
        }

        public String source() {
            return source;
        }
    }

    private static BeanDefinition definition(String source) {
        return BeanDefinitionBuilder
                .genericBeanDefinition(ChannelClient.class)
                .addConstructorArgValue(source)
                .getBeanDefinition();
    }

    private static void demonstrateDenied() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            context.setAllowBeanDefinitionOverriding(false);

            context.registerBeanDefinition(
                    "notificationClient", definition("FIRST"));

            System.out.println("denyPolicy=" +
                    context.getDefaultListableBeanFactory()
                            .isAllowBeanDefinitionOverriding());

            try {
                context.registerBeanDefinition(
                        "notificationClient", definition("SECOND"));
                System.out.println("denyResult=UNEXPECTED");
            } catch (BeanDefinitionOverrideException ex) {
                System.out.println("denyResult=REJECTED");
                System.out.println("denyName=" + ex.getBeanName());
            }

            context.refresh();
            ChannelClient retained =
                    context.getBean("notificationClient", ChannelClient.class);
            System.out.println("denyActiveDefinition=" + retained.source());
        }
    }

    private static void demonstrateAllowed() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            context.setAllowBeanDefinitionOverriding(true);

            context.registerBeanDefinition(
                    "notificationClient", definition("FIRST"));
            context.registerBeanDefinition(
                    "notificationClient", definition("SECOND"));
            context.registerAlias("notificationClient", "preferredClient");
            context.refresh();

            ChannelClient selected =
                    context.getBean("notificationClient", ChannelClient.class);
            ChannelClient byAlias =
                    context.getBean("preferredClient", ChannelClient.class);

            System.out.println("allowPolicy=" +
                    context.getDefaultListableBeanFactory()
                            .isAllowBeanDefinitionOverriding());
            System.out.println("allowResult=" + selected.source());
            System.out.println("beanNamesForType=" +
                    context.getBeanNamesForType(ChannelClient.class).length);
            System.out.println("aliasSameInstance=" +
                    (selected == byAlias));
            System.out.println("aliasIsDefinition=" +
                    context.containsBeanDefinition("preferredClient"));
            System.out.println("sameSingleton=" +
                    (selected == context.getBean(
                            "notificationClient", ChannelClient.class)));
        }
    }

    public static void main(String[] args) {
        demonstrateDenied();
        demonstrateAllowed();
    }
}
~~~

**Why the example's output is reliable:**

- `ChannelClient` is a public static nested class with a public constructor taking a String; the definition builder stores constructor argument `FIRST` or `SECOND`.
- `context.setAllowBeanDefinitionOverriding(...)` is called **before registration**, and the policy never changes mid-way.
- In the denied branch, the **exact exception type** is caught; after the error, the first definition remains intact. Calling `refresh()` afterward creates an instance from the FIRST definition.
- In the allowed branch, both registrations occur sequentially **before refresh**, so the SECOND definition is active when the bean is created.
- The `preferredClient` alias points to `notificationClient`; it does not create a second definition, so looking up by alias returns the same singleton object.
- `getBeanNamesForType(ChannelClient.class).length` in the allowed context is 1: **one primary bean name** of that type; the alias does not appear as a separate definition in this list.
- Both contexts are closed via `try-with-resources`. Output does not depend on logging frameworks, random values, timestamps, or class hash codes.

### 6.3. Running with Maven and Stdout

In the `bean-override-demo` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact 10 lines of stdout printed by Java code upon a successful run:**

~~~text
denyPolicy=false
denyResult=REJECTED
denyName=notificationClient
denyActiveDefinition=FIRST
allowPolicy=true
allowResult=SECOND
beanNamesForType=1
aliasSameInstance=true
aliasIsDefinition=false
sameSingleton=true
~~~

`java -version`, `javac -version`, `mvn -version`, and any Maven/Spring logs are not part of the **10 lines emitted by the application**. Internal exception chains may include varying metadata/logs; the demo **does not print stack traces** and instead prints only the caught result and bean name, keeping stdout deterministic.

### 6.4. Running Directly with `javac` and `java`

So the Java compiler can find Spring APIs, generate the classpath via Maven:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BeanOverridePolicyDemo.java
java -cp "out:$(cat classpath.txt)" demo.BeanOverridePolicyDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BeanOverridePolicyDemo.java
java -cp "out;$deps" demo.BeanOverridePolicyDemo
~~~

Note the classpath separator **`:`** on Unix and **`;`** on Windows. Both ways of running execute the same `demo.BeanOverridePolicyDemo` class, so stdout follows the exact same script.

## 7. Interpreting Each Verification

| Output line | Meaning |
| --- | --- |
| `denyPolicy=false` | The first context explicitly disallows overriding via configuration |
| `denyResult=REJECTED` | Registering a second definition under the same name is rejected |
| `denyName=notificationClient` | The exception identifies the exact colliding bean name |
| `denyActiveDefinition=FIRST` | After the rejected registration, the first definition remains in use |
| `allowPolicy=true` | The second context explicitly enables overriding |
| `allowResult=SECOND` | The new definition replaces the old definition before refresh |
| `beanNamesForType=1` | The registry retains one primary bean name of type ChannelClient |
| `aliasSameInstance=true` | The alias resolves to the same bean object, not a second bean |
| `aliasIsDefinition=false` | The alias does not create an additional BeanDefinition |
| `sameSingleton=true` | Within the same context, retrieving a singleton multiple times returns the same reference |

**What this output does NOT prove:** that every conflicting registration via annotations/scanning/XML shares the exact same winning order or exception type at the exact same moment; those involve additional metadata sources and processing steps that must be tested separately.

## 8. Where Can Collisions Come from in Real Projects?

- **Two `@Bean` methods in different configuration classes** using the same default bean name because of matching method names, or explicitly repeating `@Bean("notificationClient")`.
- **Component scanning** discovering multiple components with the same name (per the naming strategy) or colliding with a bean already declared in JavaConfig.
- **Library and application registering the same name**, e.g. project code reusing an infrastructure name already claimed by a library.
- **XML bean declarations** or programmatic registrations colliding on keys with JavaConfig metadata.
- **Renaming methods/classes/packages or changing scan scope**, causing beans to start colliding after a refactor or dependency upgrade.
- **An already-used alias** colliding with another registration's name, or two alias definitions competing; inspect conflicts in the relevant registry/alias mechanism.
- **Child context and parent context:** not necessarily registering into the same registry. A child context can shadow a bean name in the parent along the lookup hierarchy; that is not two definitions overriding each other in the **same bean factory**. Distinguish registry scope before concluding it is a collision.

### Behavior of `@Bean` Methods with the Same Name

Spring processes `@Bean` methods through configuration parsing and bean definition registration. Do not oversimplify this as "whichever method appears lower in the file always wins". Depending on definition sources, processing order, collisions between methods and components, and metadata rules, a configuration may be rejected, skipped during registration, or handled under specific rules.

**To be certain of the outcome**, inspect the registered bean definitions, bootstrap logs, and actual context tests rather than guessing from method order in source files.

## 9. Name Collision vs. Type-Based Conflict

~~~java
@Bean("firstChannel")
ChannelClient firstChannel() {
    return new ChannelClient("FIRST");
}

@Bean("secondChannel")
ChannelClient secondChannel() {
    return new ChannelClient("SECOND");
}
~~~

This is an **illustrative snippet**, not a complete file. The two beans have **different names**, even though they share the same class. This does not violate `allowBeanDefinitionOverriding=false` because the registry does not have to overwrite an existing name.

However:

~~~java
ChannelClient client = context.getBean(ChannelClient.class);
~~~

if no candidate is prioritized according to matching rules, a single-valued type lookup can fail with `NoUniqueBeanDefinitionException`. The solution is to choose **the right candidate**, not to enable bean overriding:

- `@Qualifier("firstChannel")` at an injection point needing the first bean.
- `@Primary` when one bean genuinely should be the default choice.
- Lookup by bean name at the composition root, e.g. `context.getBean("firstChannel", ChannelClient.class)`.
- List/map injection when the business logic needs all strategies or channels.

Conversely, `BeanDefinitionOverrideException` concerns **the same bean name** being registered again when the policy forbids it. There is no reason to use `@Qualifier` to allow overriding an occupied name.

## 10. Policy and When to Set It

For application-created contexts, set the policy **before register/refresh**:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.setAllowBeanDefinitionOverriding(false);
    context.register(AppConfig.class);
    context.refresh();
    // Use beans while the context is still active.
}
~~~

This is an **illustrative snippet**; `AppConfig` must be defined in a separate program. Using the no-argument constructor and configuring afterward is advantageous when you need to set the policy **before the bootstrap step**. Calling `new AnnotationConfigApplicationContext(AppConfig.class)` directly typically refreshes the context before you get a chance to call the policy setter on the constructed instance; avoid that syntax when the problem requires setting the policy before registration.

With Spring Boot, `spring.main.allow-bean-definition-overriding` belongs to Boot startup configuration, **not a `@Bean` String property that automatically applies to a plain Spring context**.

### Can You Change a Running Bean by Re-Registering It?

Do not treat overriding as a post-startup bean hot-swap mechanism. Once a singleton has been created, it may already be injected into multiple consumers, have cached metadata, post-processors, lifecycles, and active resources. Changing the definition afterward **does not guarantee replacing every existing reference**, and can leave inconsistent state. If you need to reconfigure a running service, choose a supported reconfiguration mechanism, create a new context, or design an appropriate provider.

**Safety rule:** bean definitions should have their full intended configuration **before refresh**, the policy should be explicit, and startup tests should verify the actual implementation supplied.

## 11. Diagnostic Process for Duplicate Names

1. **Read the bean name in the exception** (e.g. `notificationClient`), not just "could not start".
2. **Identify both registration sources:** `@Bean` methods, component scanning, XML, library auto-registration, or API calls.
3. **Identify the registry/context:** are they genuinely going into the same BeanFactory, or is one bean in the parent and one in the child?
4. **Check the policy:** does the context/host framework currently allow or disallow overriding? Do not guess from experience on a Spring Boot project if you are currently running plain Framework.
5. **Inspect bean definition metadata:** factory method, bean class, resource/source, role, scope, and qualifiers (if any).
6. **Make the right architectural decision:** should these be two independent differently named beans, or should there be only one bean? Did you accidentally double-scan?
7. **Rename or consolidate configuration intentionally**; choose qualifiers/primary when the real issue is type ambiguity.
8. **Run a startup smoke test and verify runtime state**: bean name, object type, configuration/identity, and behavior; do not rely solely on logs lacking exceptions.
9. **Check other modules/environments:** test/prod may add configurations or scanned packages that expose different collisions.

### Useful APIs

~~~java
context.containsBeanDefinition("notificationClient");
context.isBeanNameInUse("notificationClient");
context.getBeanDefinition("notificationClient");
context.getAliases("notificationClient");
context.getBean("notificationClient");
~~~

These snippets are **illustrative within a scope holding a valid context**, not a full Java file. Note that `isBeanNameInUse` accounts for related aliases/bean names in the registry; `containsBeanDefinition` checks for a **directly registered definition**, while `getBean` retrieves an **instance** (potentially creating the bean if it does not yet exist).

Using definition-lookup APIs **does not mean** you should mutate running definitions: metadata inspection is different from mutation.

## 12. Common Errors and How to Fix Them

| Issue | Common Mistake | How to Fix |
| --- | --- | --- |
| `BeanDefinitionOverrideException` | Same bean name registered twice under a disallowing policy | Find both sources, rename sensibly, or remove duplicate registration |
| `NoUniqueBeanDefinitionException` | Two differently named beans causing ambiguous single-type injection | Qualifier/primary/redesign selection, do not enable overriding |
| "Set it to true yet runtime is still wrong" | Desired bean was silently replaced by another definition | Check registration sources, actual implementation, startup tests |
| "An alias counts as a second bean" | Counting an alias as a new definition | Use `isAlias`, `containsBeanDefinition`, compare identity |
| "The last bean in source order always wins" | Relying on textual ordering in JavaConfig | Check ordering/registration pipeline, do not form implicit contracts |
| Duplicate names from component scanning | Two components given the same simple name or wrong scan scope | Rename beans/change naming strategy or narrow scan scope |
| Library and application config name collision | Reusing a generic bean name | Namespace/module-prefix names, check official extension points |
| Parent/child context sharing a bean name | Confusing lookup shadowing with single-registry override | Check context hierarchy and lookup rules in the actual context |
| "Change policy after refresh to fix error" | Setting policy too late | Configure before register/refresh and restart |
| Overriding after a singleton is created | Expecting already-injected consumers to update references | Do not use overriding as hot reload; design lifecycle/reconfiguration |
| Spring Framework and Boot have different defaults | Applying another framework's assumptions | Verify the actual runtime policy and set it explicitly |
| Matching bean type but different names | Treating it as a registry error | Select the bean by appropriate type/qualifier |
| Matching bean name but different classes | Thinking different classes avoid collision | Registry keys by name, so different classes still collide |

**Operational principle:** "the application starts" does not prove the right bean was selected. When overriding is enabled, **it is especially important to verify the actual bean**, because accidentally replacing a definition might not fail startup.

## 13. When Might Overriding Be Intentional?

There are cases where a system needs to register an implementation replacing a default definition: a test environment providing a fake, framework integration intentionally allowing custom registration, or a configuration system permitting replacement. However, you must establish:

- Who owns that bean name and who is permitted to replace it?
- Is there an explicit contract/documentation for overriding?
- Is registration order well-defined in this scenario?
- What lifecycle/resources/configuration does the replaced bean have?
- Which test proves the final bean has the right type and behavior?
- Is the policy consistent across environments (dev/test/prod)?

In Spring Boot tests, there may be **specialized bean-overriding mechanisms provided by the test ecosystem**; they do not mean you should enable the overriding property application-wide. For production code, prefer official configuration/extension points rather than accidental name collisions.

**Lower-risk alternative example:** instead of registering two beans with the same name, configure a single `@Bean` method that chooses the implementation based on a validated property and returns the common interface; or register two distinct names and select via qualifier/profile as needed.

## 14. Exercises and Answers

**Exercise 1.** Two `@Bean` methods share the name `client`, yet one returns `MailClient` and the other returns `SmsClient`. Is there a name collision?

**Answer:** Potentially yes if both definitions are submitted to **one registry under the name `client`**; having different classes does not eliminate the collision. Actual processing through `@Bean` parsing can involve distinct steps; inspect registration results rather than assuming a guaranteed winning order.

**Exercise 2.** Two beans named `firstClient` and `secondClient` both implement the `Client` interface. Does `allowBeanDefinitionOverriding=false` block them?

**Answer:** No, because their names differ. If injecting a single `Client` lacks a unique choice, that is autowiring ambiguity and requires qualifiers/primary/redesign.

**Exercise 3.** In the denied branch, why do we still get `FIRST` after the error?

**Answer:** The SECOND registration was rejected before refresh, leaving the FIRST definition intact. The context can still refresh with the remaining valid definition.

**Exercise 4.** In the allowed branch, why is there only one bean name `notificationClient` despite registering twice?

**Answer:** The new definition replaced the old definition **under the same key** before refresh, rather than creating two separate beans with the same name in the registry.

**Exercise 5.** Is the `preferredClient` alias a new bean?

**Answer:** No. It is a secondary name pointing to the same bean; `aliasSameInstance=true` and `aliasIsDefinition=false` prove that.

**Exercise 6.** Why does a Spring Boot application report an override error while a plain Framework demo can allow it?

**Answer:** Their default policies differ. Framework's `DefaultListableBeanFactory` allows it by default; Boot disallows it by default. Verify the policy in your real environment and enable overriding only intentionally.

**Exercise 7.** Should you switch the policy to `true` after the context is already running to swap implementations?

**Answer:** Do not treat this as a hot-swap mechanism. Metadata and singleton references may already be cached/injected; configure properly from bootstrap or use an appropriate reconfiguration mechanism.

## 15. Practical Application Checklist

- [ ] Give every bean a clear name, avoiding generic names another library might claim.
- [ ] Know that bean name is the registry key, not class name, alias, or type.
- [ ] Distinguish same-name collision from same-type multi-bean ambiguity.
- [ ] Understand `setAllowBeanDefinitionOverriding(false/true)` and Framework/Boot defaults.
- [ ] Set the policy **before registering/refreshing** when you own the context.
- [ ] When disallowed: know how to read `BeanDefinitionOverrideException` and the colliding name.
- [ ] When allowed: verify the runtime bean actually comes from the intended definition.
- [ ] Understand that aliases do not produce a second bean definition.
- [ ] Do not assume source-code order across multiple configurations guarantees who wins.
- [ ] Do not use overriding as a mechanism to replace already-initialized beans.
- [ ] Inspect `@Bean`, scanning, XML/API, and framework integration sources.
- [ ] Run Java 17+ Maven/`javac`/`java` and match the **10 lines of stdout**.
- [ ] Have a startup smoke test to catch unexpected collisions when adding modules.
- [ ] Allow overriding only with a clear contract and tests verifying the right implementation.

**Conclusion:** A name collision in Spring is a collision on **the same `BeanDefinition` registry key**. When overriding is disallowed, duplicate registration is rejected; when allowed, a later definition can replace an earlier one according to registration rules. Use an **explicit policy**, distinguish aliases from multiple beans of the same type, and prioritize **fixing registration design** over enabling overriding just to get an application to boot.

### Official Documentation

- [DefaultListableBeanFactory — Bean Definition Overriding](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/DefaultListableBeanFactory.html)
- [GenericApplicationContext — registerBeanDefinition / setAllowBeanDefinitionOverriding](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/GenericApplicationContext.html)
- [BeanDefinitionOverrideException API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionOverrideException.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)

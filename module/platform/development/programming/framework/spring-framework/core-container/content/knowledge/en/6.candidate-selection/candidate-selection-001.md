# Looking Up Candidates by Assignable Type in Spring Core Container

## 1. From the Required Type to the Set of Candidate Beans

Spring Dependency Injection often starts with the question: **“Which beans have a type that is *assignable* to the type requested by the injection point?”** For example, a service has a constructor taking `Channel`, while the container has two classes `EmailChannel` and `SmsChannel` that both implement `Channel`. Both can **match by type** without yet allowing a single bean to be selected.

Distinguish three things:

1. **Type matching:** is the bean declared or inferred to have a type compatible with the requested interface/superclass?
2. **Autowire candidate filtering:** is that type-matching bean permitted to participate in dependency autowiring at the injection point? Is it excluded by `autowireCandidate=false`, a qualifier, or another condition?
3. **Single-candidate selection:** if multiple eligible candidates remain, Spring uses `@Primary`, `@Qualifier`, metadata, and other precedence rules to choose one or report ambiguity.

**A bean that matches by type is not necessarily a valid autowire candidate; a list of multiple type matches does not mean injection always fails either.** With collection injection, Spring can even pass **multiple suitable beans** into the same `List<T>` or `Map<String,T>`.

| Question | API/Mechanism | Answer |
| --- | --- | --- |
| Can a Java class be assigned to an interface or superclass? | `isAssignableFrom`, `instanceof` | Type relationship in **Java** |
| Which bean names does the container know match a type? | `getBeanNamesForType(Type.class)` | List of **type-matching bean names**, not necessarily filtered for a specific injection point |
| Need instances of beans matching a type? | `getBeansOfType(Type.class)` | Map of **bean name → bean object**, which may instantiate beans |
| Does a specific bean match a type? | `isTypeMatch("beanName", Type.class)` | Type check on the specified bean |
| Need exactly one bean by type? | `getBean(Type.class)` | Returns a bean or fails if missing/ambiguous, applying the corresponding precedence rules |
| Does a constructor require type `T`? | `@Autowired`/factory-method parameter | Resolution of an **injection point**, which still requires candidate filtering |
| Need all beans allowed to be autowired for type `T`? | `@Autowired List<T>`, `Map<String,T>` | Set of eligible dependency candidates, which can be ordered |

Lesson goal: read **assignable type** relationships accurately, verify the impact of inheritance/interfaces/generics, clearly see the difference between **type lookup** and **autowire candidate filtering**, and determine when `@Primary`/`@Qualifier` must be used.

This lesson uses **Java 17+**, **Spring Framework 7.0.9**, Maven, and the CLI. This is pure Spring Core Container, requiring neither Spring Boot nor a web environment.

## 2. What Does “Assignable” Mean in Java?

In Java, `Child extends Parent` and `Implementation implements Contract` create type relationships. If a method requires `Parent`, a valid `Child` object can be passed in; if it requires `Contract`, an object of a class implementing `Contract` is also valid.

~~~java
// Illustrative snippet, not a standalone compilable file.
interface Channel {
    String id();
}
abstract class BaseChannel implements Channel { }
class EmailChannel extends BaseChannel {
    public String id() { return "EMAIL"; }
}
class SmsChannel extends BaseChannel {
    public String id() { return "SMS"; }
}
~~~

The following expressions have specific meanings:

~~~java
Channel a = new EmailChannel();        // Valid: EmailChannel implements Channel indirectly.
BaseChannel b = new SmsChannel();      // Valid: SmsChannel extends BaseChannel.
boolean yes = Channel.class.isAssignableFrom(SmsChannel.class);
boolean no = SmsChannel.class.isAssignableFrom(Channel.class);
~~~

**Read the direction of `Class.isAssignableFrom` correctly:**

`Target.class.isAssignableFrom(Source.class)` asks: can a value of **Source** be used at a location expecting **Target** under standard type compatibility rules? Therefore:
- `Channel.class.isAssignableFrom(EmailChannel.class)` → `true`;
- `BaseChannel.class.isAssignableFrom(SmsChannel.class)` → `true`;
- `EmailChannel.class.isAssignableFrom(Channel.class)` → `false`.

This is an example of **reference type compatibility**, not arbitrary value conversion. If an actual bean is `SmsChannel`, Spring cannot inject it into a field of type `EmailChannel` merely because both share the `Channel` interface. They are sibling classes, with no assignability relationship from SMS to Email.

**Remember the matching direction**: if an injection point requires `Channel`, `SmsChannel` can match; if an injection point requires `SmsChannel`, a bean known only as `Channel` **is not implicitly treated as** `SmsChannel`.

Spring also uses **type metadata, factory methods, generics, and proxy information**. Consequently, how Spring knows or predicts a type before creating an object can be more involved than a single `isAssignableFrom` call against the object's runtime class.

## 3. Where Does Spring Get Type Information From?

There is more than one source of type information:

- **Component-scanned class:** from the discovered bean class (`@Component`, `@Service`, …), its class hierarchy, interfaces, and registration metadata.
- **`@Bean` factory method:** Spring can rely on the **declared return type** of the factory method before the actual instance is created.
- **XML bean definitions:** from `class`, factory-method/factory-bean metadata, and information inferred by the container.
- **Already-created bean instance:** Spring can use the known type of the instance when appropriate; however, a proxy may alter the runtime class/type visible to callers.
- **`FactoryBean<T>`:** the bean name typically represents the **product** `T`, while the factory itself is referenced with the `&beanName` prefix. Type prediction also involves `getObjectType()`.
- **Generic metadata:** `ResolvableType` and generic signatures help distinguish `Store<String>` from `Store<Integer>`.

An example to pay attention to when configuring `@Bean`:

~~~java
// Illustrative snippet, not a standalone project:
@Bean
Channel smsChannel() {
    return new SmsChannel();
}
~~~

Even though the method **returns an instance** of `SmsChannel`, its *declared return type* is `Channel`. Before the bean is created, Spring **does not necessarily know** it has the concrete type `SmsChannel` to resolve an injection point requesting the subclass. Therefore, Spring documentation recommends making `@Bean` signatures **sufficiently specific** when you intend to inject by implementation type:

~~~java
@Bean
SmsChannel smsChannel() {
    return new SmsChannel();
}
~~~

When injection only requires `Channel`, either declaration can satisfy it; however, if injection requires `SmsChannel`, a concrete return type makes the metadata clearer and more reliable.

**Do not use runtime `getClass()` results as a reason to ignore public API signatures**. With generics, proxies, `FactoryBean`, and lazy beans, relying solely on the runtime class makes it easy to mispredict the type matches Spring can know at each phase.

## 4. Two API Groups: Discovering Types vs. Retrieving Dependencies

### 4.1. `getBeanNamesForType`: Discovering Names

~~~java
String[] names = context.getBeanNamesForType(Channel.class);
~~~

This `ListableBeanFactory` API (exposed by `ApplicationContext`) returns the names of beans whose type is compatible with `Channel`, **including subclasses/implementations**.

- Do not assume it only looks for beans with `getClass() == Channel.class`: interfaces usually cannot be instantiated directly.
- It returns **names**, not `Channel` objects.
- The result may include beans that **autowire-candidate filtering** will exclude when resolving an injection point.
- It is not a list of aliases: aliases do not multiply bean definitions or instances.
- The returned order may reflect registration order; to assert deterministically in exercises, **sort** before printing.
- Internally, the container holds many infrastructure beans; list only the **specific type relevant to the topic**, rather than printing all `getBeanDefinitionNames()` and assuming a fixed count.

### 4.2. `getBeansOfType`: Retrieving Instances

~~~java
Map<String, Channel> beans = context.getBeansOfType(Channel.class);
~~~

This API returns a name→instance map and can trigger bean instantiation and related callbacks. It **differs** from Spring injecting `Map<String,Channel>` at an injection point:

- `getBeansOfType(Channel.class)` **lists all beans matching the type** according to the API's contract.
- `@Autowired Map<String,Channel>` is additionally subject to **autowire candidate rules**: a bean with `autowireCandidate=false` can be omitted from the injected map, even though it still appears in discovery or get-by-name APIs.

This is a common debugging trap: “`getBeanNamesForType` found three beans, why does the injected `List<Channel>` only have two?” — because **type matching and injectability are two separate steps**.

### 4.3. `isTypeMatch`, `getBean(Class)`, and `getBean(name, Class)`

- `context.isTypeMatch("smsChannel", BaseChannel.class)` checks whether the named bean is compatible with this superclass.
- `context.getBean(Channel.class)` must select **one bean** assignable to that type; multiple candidates without an applicable precedence rule can throw `NoUniqueBeanDefinitionException`.
- `context.getBean("smsChannel", Channel.class)` retrieves the **bean by name** while verifying type compatibility; it does not arbitrarily pick another bean.

`@Primary`, `@Qualifier`, bean name, and other policies participate in resolution depending on the specific context. Do not assume a bean is returned because “the exact type matches a method name” without inspecting metadata.

## 5. Type Matching Does Not Equal Autowire Candidate Selection

**`autowireCandidate=false`** lets you keep a bean in the context for explicit lookup while **excluding it from standard type-based autowiring**.

~~~java
// Snippet inside an appropriate @Configuration:
@Bean(name = "localChannel", autowireCandidate = false)
LocalChannel localChannel() {
    return new LocalChannel();
}
~~~

Consequences:
1. The `localChannel` bean still has a name and definition, and Spring can still instantiate the object through the bean mechanism.
2. `getBean("localChannel")` can still access it by name.
3. `getBeanNamesForType(Channel.class)` can still **detect** its type match.
4. However, Spring **does not use it as an autowiring candidate** for `@Autowired Channel`, `@Autowired List<Channel>`, or a constructor parameter requiring `Channel`.

In Spring 7, `@Bean` also has `defaultCandidate` metadata, `@Primary`, `@Fallback`, and other ways to fine-tune precedence when selecting beans. Do not collapse all of them into a single boolean “match or not match”. `autowireCandidate=false` **excludes a bean from autowiring candidates**, whereas `@Primary` states that a candidate is preferred in certain **single-dependency** selection scenarios.

| Bean state | Type match? | Can appear in discovery? | Standard autowiring candidate? |
| --- | --- | --- | --- |
| Normal `EmailChannel` | Yes, for `Channel` and `BaseChannel` | Yes | Yes |
| Normal `SmsChannel` | Yes | Yes | Yes |
| `LocalChannel` with `autowireCandidate=false` | Yes | Yes | **No** |
| `EmailChannel` marked `@Primary` | Yes | Yes | Yes, typically preferred when a single bean is needed |
| Class that does not implement `Channel` at all | No | No for type `Channel` | No for type `Channel` |

**Note:** `getBeanNamesForType` is an API for **discovering type-compatible beans**, not an API for “fetching the exact final candidate set for every injection point”. `@Qualifier`, generic types, and injection point metadata can filter the result set in ways a single `getBeanNamesForType(Channel.class)` call cannot express.

## 6. When Multiple Assignable Candidates Exist, How Does Spring Choose?

The result of `getBeanNamesForType(Channel.class)` may contain multiple type-compatible beans, yet an injection point for `Channel` accepts only **one** bean. In that case, Spring also checks autowiring eligibility, qualifiers, precedence rules, and injection point metadata. If multiple equal candidates remain, single-valued selection can fail with `NoUniqueBeanDefinitionException`.

| Need | Approach | Boundary |
| --- | --- | --- |
| A default implementation | `@Primary` | Does not remove other candidates and does not order initialization |
| A role-specific implementation | `@Qualifier` at the injection point | Only filters beans that are still type-compatible and eligible |
| A fallback bean | `@Fallback` (Spring 6.2+) | Lowers precedence; does not provide runtime failover |
| All implementations | `List<Channel>` / `Map<String, Channel>` | Selects a collection; does not require a single unique candidate |

The next lesson analyzes each resolution branch with isolated contexts. In this lesson, the key takeaway is that **type discovery is an input condition, not the final result of dependency injection**.

## 7. Generic Types Also Participate in Candidate Determination

When an injection point requests `Store<Channel>`, Spring can use the known generic signature of the bean definition or factory method to filter beyond raw type checking. `Store<Channel>` and `Store<String>` share the raw type `Store`, but are not interchangeable by default. A signature like `@Bean Store<Channel> channelStore()` expresses the contract more clearly than `@Bean Store rawStore()`.

This is declaration-level metadata; Spring cannot “recover” all type arguments from an object after type erasure. If a factory method declares a raw type, generic metadata may be missing and require investigation based on the actual declarations. Generic filtering also **does not** resolve ambiguity when two beans share the exact same full type. The dedicated lesson on generic qualifiers tests this case with single beans, collections, and additional qualifiers.

## 8. Complete Demo with Java 17 + Maven + Spring 7.0.9

The demo shows:
- Two classes `EmailChannel` and `SmsChannel` **extend `BaseChannel` and implement `Channel`**, with SMS additionally implementing `Auditable`.
- `LocalChannel` still matches type `Channel` but declares `autowireCandidate=false`; it **appears in type discovery but is absent from the injected list/map**.
- `EmailChannel` is `@Primary`; single-dependency `Channel` selects EMAIL.
- Injection by `Auditable` receives SMS; generic `Vault<String>` is distinct from `Vault<Integer>`.
- Another context without a primary leads to ambiguity when looking up a single `Channel` by type.

All code resides in **a single Java file**, requiring no database, web server, or Spring Boot. List-printing operations always use `Arrays.sort`/`sorted()` for **deterministic stdout**, independent of bean registration order.

### 8.1. Project Structure

~~~text
assignable-candidates-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AssignableCandidatesDemo.java
~~~

Requires **JDK 17+**, **Maven 3.9+**, and access to Maven Central/a mirror if dependencies are not yet in the local cache.

### 8.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>assignable-candidates-demo</artifactId>
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
                    <mainClass>demo.AssignableCandidatesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` brings in the core Spring modules via Maven transitive dependency resolution. `maven.compiler.release=17` targets Java 17 bytecode and APIs. The example uses Java configuration only.

### 8.3. `src/main/java/demo/AssignableCandidatesDemo.java`

~~~java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.ResolvableType;

public final class AssignableCandidatesDemo {
    private AssignableCandidatesDemo() {
    }

    interface Channel {
        String id();
    }

    interface Auditable {
        String auditTag();
    }

    abstract static class BaseChannel implements Channel {
    }

    static final class EmailChannel extends BaseChannel {
        @Override public String id() {
            return "EMAIL";
        }
    }

    static final class SmsChannel extends BaseChannel implements Auditable {
        @Override public String id() {
            return "SMS";
        }

        @Override public String auditTag() {
            return "SMS-AUDIT";
        }
    }

    static final class LocalChannel extends BaseChannel {
        @Override public String id() {
            return "LOCAL";
        }
    }

    @FunctionalInterface
    interface Vault<T> {
        String kind();
    }

    static final class Consumer {
        private final Channel primary;
        private final Auditable audit;
        private final List<Channel> channels;
        private final Map<String, Channel> channelMap;
        private final Vault<String> stringVault;
        private final List<Vault<Integer>> integerVaults;

        Consumer(Channel primary, Auditable audit,
                List<Channel> channels, Map<String, Channel> channelMap,
                Vault<String> stringVault, List<Vault<Integer>> integerVaults) {
            this.primary = primary;
            this.audit = audit;
            this.channels = channels;
            this.channelMap = channelMap;
            this.stringVault = stringVault;
            this.integerVaults = integerVaults;
        }

        String primaryName() {
            return primary.id();
        }

        String auditTag() {
            return audit.auditTag();
        }

        String channelList() {
            return channels.stream().map(Channel::id)
                    .sorted().collect(Collectors.joining(","));
        }

        String mapKeys() {
            return channelMap.keySet().stream()
                    .sorted().collect(Collectors.joining(","));
        }

        String textKind() {
            return stringVault.kind();
        }

        String integerKinds() {
            return integerVaults.stream().map(Vault::kind)
                    .sorted().collect(Collectors.joining(","));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("emailChannel")
        @Primary
        public EmailChannel email() {
            return new EmailChannel();
        }

        @Bean("smsChannel")
        public SmsChannel sms() {
            return new SmsChannel();
        }

        @Bean(name = "localChannel", autowireCandidate = false)
        public LocalChannel local() {
            return new LocalChannel();
        }

        @Bean
        public Vault<String> stringVault() {
            return () -> "STRING";
        }

        @Bean
        public Vault<Integer> integerVault() {
            return () -> "INTEGER";
        }

        @Bean
        public Consumer consumer(
                Channel selected,
                @Qualifier("smsChannel") Auditable audit,
                List<Channel> channels,
                Map<String, Channel> channelsByName,
                Vault<String> stringVault,
                List<Vault<Integer>> integerVaults) {
            return new Consumer(selected, audit, channels,
                    channelsByName, stringVault, integerVaults);
        }
    }

    // Intentionally omit @Primary to illustrate ambiguity.
    @Configuration(proxyBeanMethods = false)
    public static class AmbiguousConfig {
        @Bean
        public EmailChannel first() {
            return new EmailChannel();
        }

        @Bean
        public SmsChannel second() {
            return new SmsChannel();
        }
    }

    private static String names(String[] values) {
        Arrays.sort(values);
        return String.join(",", values);
    }

    private static String keys(Map<String, ?> map) {
        return map.keySet().stream()
                .sorted().collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        System.out.println("java.channelFromEmail="
                + Channel.class.isAssignableFrom(EmailChannel.class));
        System.out.println("java.emailFromChannel="
                + EmailChannel.class.isAssignableFrom(Channel.class));
        System.out.println("java.baseFromSms="
                + BaseChannel.class.isAssignableFrom(SmsChannel.class));
        System.out.println("java.auditFromSms="
                + Auditable.class.isAssignableFrom(SmsChannel.class));

        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            System.out.println("type.channel="
                    + names(context.getBeanNamesForType(Channel.class)));
            System.out.println("type.base="
                    + names(context.getBeanNamesForType(BaseChannel.class)));
            System.out.println("type.email="
                    + names(context.getBeanNamesForType(EmailChannel.class)));
            System.out.println("type.audit="
                    + names(context.getBeanNamesForType(Auditable.class)));
            System.out.println("type.unknown="
                    + context.getBeanNamesForType(Runnable.class).length);
            System.out.println("type.smsIsBase="
                    + context.isTypeMatch("smsChannel", BaseChannel.class));
            System.out.println("type.localRegistered="
                    + context.containsBeanDefinition("localChannel"));
            System.out.println("type.localByName="
                    + context.getBean("localChannel", Channel.class).id());
            System.out.println("type.allObjects="
                    + keys(context.getBeansOfType(Channel.class)));

            Consumer consumer = context.getBean(Consumer.class);
            System.out.println("wire.primary=" + consumer.primaryName());
            System.out.println("wire.audit=" + consumer.auditTag());
            System.out.println("wire.list=" + consumer.channelList());
            System.out.println("wire.map=" + consumer.mapKeys());
            System.out.println("wire.stringVault=" + consumer.textKind());
            System.out.println("wire.integerVaults=" + consumer.integerKinds());

            ResolvableType textType =
                    ResolvableType.forClassWithGenerics(
                            Vault.class, String.class);
            ResolvableType intType =
                    ResolvableType.forClassWithGenerics(
                            Vault.class, Integer.class);
            System.out.println("type.vault.text="
                    + names(context.getBeanNamesForType(textType)));
            System.out.println("type.vault.integer="
                    + names(context.getBeanNamesForType(intType)));
        }

        // With two candidates of the same type but no primary.
        try (var context = new AnnotationConfigApplicationContext(
                AmbiguousConfig.class)) {
            context.getBean(Channel.class);
            System.out.println("unexpected");
        } catch (NoUniqueBeanDefinitionException expected) {
            System.out.println("ambiguousLookup.failed=true");
        }
    }
}
~~~

### 8.4. Why Is This Example a Valid Comparison?

- `emailChannel`, `smsChannel`, and `localChannel` all have Java classes extending `BaseChannel`. Since `BaseChannel implements Channel`, **all three types** are assignable to `Channel`.
- Only `SmsChannel` implements `Auditable`, so `getBeanNamesForType(Auditable.class)` contains exactly one bean named `smsChannel`.
- `EmailChannel` and `SmsChannel` are eligible for autowiring; `LocalChannel` is excluded via `@Bean(autowireCandidate=false)`.
- `getBeanNamesForType(Channel.class)` can detect **all three**, because this API performs **type discovery**, not autowiring candidate resolution for an injection point.
- Injecting a single `Channel` into `consumer(...)` selects **EMAIL** because `@Primary` designates a preferred bean among the remaining eligible candidates.
- Injecting `List<Channel>` and `Map<String,Channel>` receives only **EMAIL/SMS**, without `LOCAL`; this is evidence that autowiring filtering differs from type discovery.
- Type `Auditable` + `@Qualifier("smsChannel")` selects **SMS** via both the interface contract and the qualifier.
- `Vault<String>`/`Vault<Integer>` share the same raw interface but are separated by **generic argument** thanks to metadata from the `@Bean` return signatures.
- In `AmbiguousConfig`, two `Channel` beans both match by type with no primary; `getBean(Channel.class)` cannot arbitrarily pick one and therefore fails.

**Runtime note:** `@Bean("emailChannel")` declares the concrete return type `EmailChannel`; `@Bean("smsChannel")` returns `SmsChannel`. This allows Spring to recognize the respective types before the objects are instantiated. The demo does not force Spring to guess the implementation from a factory method that only declares return type `Channel`.

## 9. Run Commands and Expected Stdout

Inside the `assignable-candidates-demo` directory containing `pom.xml`, run:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

The first three version commands produce machine-dependent output. The final Maven command invokes `javac` through the Compiler Plugin and uses the dependency classpath to run `demo.AssignableCandidatesDemo`.

**22 stdout lines printed by the program itself** (excluding Maven/backend logging):

~~~text
java.channelFromEmail=true
java.emailFromChannel=false
java.baseFromSms=true
java.auditFromSms=true
type.channel=emailChannel,localChannel,smsChannel
type.base=emailChannel,localChannel,smsChannel
type.email=emailChannel
type.audit=smsChannel
type.unknown=0
type.smsIsBase=true
type.localRegistered=true
type.localByName=LOCAL
type.allObjects=emailChannel,localChannel,smsChannel
wire.primary=EMAIL
wire.audit=SMS-AUDIT
wire.list=EMAIL,SMS
wire.map=emailChannel,smsChannel
wire.stringVault=STRING
wire.integerVaults=INTEGER
type.vault.text=stringVault
type.vault.integer=integerVault
ambiguousLookup.failed=true
~~~

**Key observations:**
1. The four `java.*` lines verify Java `Class.isAssignableFrom`: an interface/superclass accepts a subclass/implementation, while the reverse direction is invalid.
2. `type.channel` and `type.base` both contain three beans, whereas `type.audit` has only SMS — Spring evaluates **type relationships**, not merely equal class names.
3. `type.localRegistered=true` and `type.localByName=LOCAL` prove that a bean excluded from autowiring **still exists and can be looked up**.
4. `type.allObjects` includes LOCAL, whereas `wire.list`/`wire.map` **do not contain LOCAL**. This is the most important distinction in the example.
5. `wire.primary=EMAIL`: Spring picks one candidate thanks to `@Primary`, yet `wire.list` still contains SMS; primary does not remove other beans from injected collections.
6. `type.vault.*` cleanly separates the two generic specializations; `Vault<String>` is not treated as `Vault<Integer>`.
7. `ambiguousLookup.failed=true` is the **intentional** failure of a lookup without a primary; the program catches `NoUniqueBeanDefinitionException`.

Note: if you intentionally alter the bean configuration or change the generic return signatures, **the expected stdout will no longer match**. If a logger emits additional startup failure notices, compare only the 22 application lines listed above; do not pin assertions to arbitrary terminal stack traces.

## 10. Plain Java 17 with `javac`/`java`

Create a standalone file **`JavaAssignableTypes.java`**, without Maven or Spring, to observe the Java foundation of the *assignable* concept.

~~~java
public class JavaAssignableTypes {
    interface Sender {
        String send();
    }

    abstract static class BaseSender implements Sender {
    }

    static final class SmsSender extends BaseSender {
        @Override
        public String send() {
            return "SMS";
        }
    }

    static final class EmailSender extends BaseSender {
        @Override
        public String send() {
            return "EMAIL";
        }
    }

    public static void main(String[] args) {
        Sender sms = new SmsSender();
        BaseSender email = new EmailSender();

        System.out.println("senderFromSms="
                + Sender.class.isAssignableFrom(SmsSender.class));
        System.out.println("baseFromEmail="
                + BaseSender.class.isAssignableFrom(EmailSender.class));
        System.out.println("smsFromSender="
                + SmsSender.class.isAssignableFrom(Sender.class));
        System.out.println("values=" + sms.send() + "," + email.send());
    }
}
~~~

Run inside the directory containing the file:

~~~bash
javac JavaAssignableTypes.java
java JavaAssignableTypes
~~~

Exact stdout:

~~~text
senderFromSms=true
baseFromEmail=true
smsFromSender=false
values=SMS,EMAIL
~~~

This is **pure Java type compatibility**. Spring leverages Java class/interface metadata and layers on BeanDefinitions, qualifiers, scopes, proxies, and autowire candidate rules. Understand the Java relationship before reasoning about how the container picks a bean from multiple registrations.

## 11. Special Cases and Limitations of Type Lookup

### 11.1. Scopes and Lazy Beans

`getBeanNamesForType(Class)` can find names based on type metadata of singletons, prototypes, and other beans insofar as they can be inferred. The overload:

~~~java
context.getBeanNamesForType(Channel.class, true, false);
~~~

takes two flags:
- `includeNonSingletons=true`: allows including prototype or scoped beans;
- `allowEagerInit=false`: avoids certain kinds of eager initialization to determine types, such as initializing a `FactoryBean` or factory reference needed for type inspection.

**The results of the two overloads can differ**, especially when a type cannot be known without instantiating metadata-producing objects. Do not call a type-query with `allowEagerInit=true` in code you assume is purely an “inspection” and then assume there are no side effects or startup costs.

### 11.2. `FactoryBean` and the `&` Prefix

Suppose `widgetFactory` is a `FactoryBean<Widget>`:
- `getBean("widgetFactory")` may return the **Widget product**;
- `getBean("&widgetFactory")` returns the **FactoryBean instance**;
- `getBeanNamesForType(Widget.class)` aims to match the **product** type, if the container has sufficient metadata;
- Type prediction can rely on `getObjectType()` and the `allowEagerInit` policy.

Therefore, if while debugging you see a bean name matching an interface even though the factory class does not implement that interface, check whether a `FactoryBean` is involved. Do not confuse a `@Bean` factory method with a class implementing `FactoryBean<T>`: these are two different mechanisms.

### 11.3. AOP Proxies and Type Prediction

AOP can wrap a target object in a proxy. With a **JDK dynamic proxy**, the proxy may expose only interfaces rather than the concrete target class; with a class-based proxy, type relationships can differ. When an injection point requires an implementation class while the proxy exposes only interfaces, type matching/injection can fail.

**Practice:** inject via a **contract interface** when appropriate, declare factory method return types clearly, and check the proxy mode. Do not rely on `bean.getClass() == Implementation.class` to conclude a bean is incompatible, as it may be a valid proxy.

### 11.4. Parent/Child Application Contexts

A `ListableBeanFactory` lookup may inspect only **local bean definitions**; the API documentation notes that `getBeanNamesForType` methods do not always merge the parent factory. When you genuinely need names from ancestor contexts, Spring provides `BeanFactoryUtils.beanNamesForTypeIncludingAncestors(...)`.

Do not confuse a **parent ApplicationContext** with `parent="templateBean"` in bean definition inheritance. One is a hierarchy of containers; the other is metadata inheritance between definitions.

### 11.5. Aliases, Visibility, and No Candidate

A bean alias does not create an additional bean definition. A bean carrying the alias `backupSender` still represents a single bean, and does not multiply instances in type-match lists.

`autowireCandidate=false` affects autowiring; it does not make a bean “non-existent”. Conversely, a class merely present on the classpath without being registered with Spring via `@Bean`, component scanning, or another API **does not automatically appear in type queries**.

**Do not interpret “only one bean found by type” as meaning the bean is guaranteed valid at every injection point**: a qualifier may require a different specific name, a generic type may not match, or the candidate may be excluded by metadata. Those conditions must be evaluated in the context of the injection point.

## 12. Debugging Type Matching and Common Errors

| Symptom or misconception | Root cause / proper investigation |
| --- | --- |
| `getBeanNamesForType(Channel.class)` returns multiple names | Multiple subclasses/implementations are assignable; not necessarily an error |
| `getBean(Channel.class)` throws `NoUniqueBeanDefinitionException` | Lookup requires **one** instance, yet multiple candidates exist without a selection policy |
| `@Autowired Channel` lacks a bean even though the implementation class exists in the project | Class is not registered as a bean, scope/profile/config is inactive, or it was filtered out |
| Type discovery finds the bean, but `List<Channel>` omits it | Possibly `autowireCandidate=false` or qualifier/generic filtering |
| `@Primary` enables single-bean injection, yet the list still has multiple | Primary only prioritizes **single-valued resolution**; it does not remove candidates from collections |
| Injection by implementation class fails | `@Bean` return type is too broad, proxy exposes only interfaces, or metadata is insufficient |
| `getBeanNamesForType(SmsChannel.class)` misses a factory-created bean | Check declared return type, `FactoryBean`/type prediction, and lazy init |
| Generic injection `Vault<String>` selects the wrong bean or finds none | Check return type signatures, generic metadata, and `ResolvableType` |
| Bean excluded from autowiring is still accessible by name | `autowireCandidate=false` only excludes the candidate, without removing the bean |
| `isAssignableFrom` returns the opposite of what was expected | Reversed Target/Source direction: `Target.isAssignableFrom(Source)` |
| Lookup by type warns of a non-unique type | Inspect candidate names with `getBeanNamesForType`, then apply primary/qualifier |
| Bean exists, but its class is proxied | Check interface/class proxy behavior; do not compare runtime classes by equality |
| `getBeansOfType` causes early application initialization | The API returns **instances**, which can trigger bean creation and lifecycle callbacks |
| Bean name matches field name, yet type does not match | Name matching does not make a Java reference assignable; fix the type contract |
| Bean from parent context is not visible | Check the context hierarchy and `BeanFactoryUtils` |
| Hard to read autowiring error logs | Inspect `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException`, and the cause chain |

**Recommended debugging workflow:**
1. Verify the active context, bean registrations, and `@Bean` declared return types.
2. Test `getBeanNamesForType(RequiredType.class)`; sort the result if you need a deterministic snapshot.
3. If type matches exist but injection is missing, check **`autowireCandidate`** metadata, qualifiers, generic types, primary/fallback, and visibility.
4. If multiple candidates exist, determine whether the injection point expects a single bean or a collection/map.
5. When ambiguity occurs, use `@Primary` or a qualifier **intentionally**, rather than merely renaming a field to rely on fallback matching.
6. For factories, proxies, or generics, inspect `ResolvableType`, `isTypeMatch`, bean factory APIs, and use a debugger when needed.
7. Test Java class behavior, container wiring, and integration boundaries separately; do not expect type matching alone to prove business behavior.

## 13. Self-Verification Exercises and Checklist

Perform each experiment on a copy and restore the code before comparing against expected stdout:

1. **Add a subclass:** create `PushChannel extends BaseChannel` and register `@Bean PushChannel`. Predict how the type lists and injected list/map change.
2. **Switch @Primary:** move primary from Email to SMS; predict `wire.primary=SMS` while `wire.list` still contains both.
3. **Remove @Primary:** in `AppConfig`, two eligible `Channel` candidates become ambiguous at factory method `consumer(Channel selected,...)`; the context can fail early.
4. **Change autowireCandidate:** remove `autowireCandidate=false` from Local. Predict that discovery still yields three beans, while the injected list/map now includes LOCAL.
5. **Look up Local by name:** run `context.getBean("localChannel", Channel.class)` and explain why it still works when Local is excluded from autowiring.
6. **Change injection type:** replace `Channel` with `SmsChannel` in a method parameter and explain why only SMS qualifies.
7. **Try a separate interface:** inject `Auditable` and observe that only `SmsChannel` implements that interface.
8. **Change `@Bean` return type:** change `SmsChannel sms()` to `Channel sms()` and compare type prediction before instantiation.
9. **Add a qualifier:** use `@Qualifier("smsChannel")` on the consumer's `Channel` parameter instead of relying on primary; confirm the filtering behavior.
10. **Generic mismatch:** change `Vault<String>` to `Vault<Integer>` for the `stringVault` parameter, and investigate why generic metadata leads to selecting another candidate or failing due to incompatibility.
11. **Add Vault<Long>:** register an additional `Vault<Long>` bean; inspect `getBeanNamesForType(ResolvableType.forClassWithGenerics(...))` for each type argument.
12. **Try prototype scope:** place `@Scope("prototype")` on a channel and compare `getBeanNamesForType` with repeated `getBean` calls; type membership does not imply singleton identity.
13. **No unique bean:** run `AmbiguousConfig` and explain why `getBean(Channel.class)` does not pick the “first” bean despite explicit registration order.
14. **Self-reference edge case:** try autowiring the bean currently being created and observe why self-injection is a fallback rather than a normal primary choice.
15. **Standalone Java:** modify `JavaAssignableTypes` so `EmailSender` implements a new interface, and use `Class.isAssignableFrom` to check which types are assignable.
16. **FactoryBean:** create a sample `FactoryBean<Channel>`, distinguish lookup by bean name vs. `&beanName`, and inspect `getObjectType()` before interpreting type-query results.

### Checklist

- [ ] Understand `Target.class.isAssignableFrom(Source.class)` in the **correct direction**.
- [ ] Know that an implementation/subclass bean can match an interface/superclass injection point.
- [ ] Do not confuse `getBeanNamesForType` with the candidate set filtered by autowiring rules.
- [ ] Know that `autowireCandidate=false` still allows lookup by name or type discovery.
- [ ] Know that `@Primary` resolves single-valued injection without removing beans from lists/maps.
- [ ] Know that `@Qualifier`, generic types, and `@Fallback` can affect selection.
- [ ] Read `getBeanNamesForType`, `getBeansOfType`, `isTypeMatch`, and `getBean(Class)` accurately.
- [ ] Distinguish raw generic types from `ResolvableType` and declared `@Bean` return types.
- [ ] Accurately predict the 22 Spring Maven stdout lines and 4 plain Java lines.
- [ ] Know the limitations of `FactoryBean`, lazy/scoped beans, proxies, and parent contexts.

## 14. Conclusion and Official Documentation

**Conclusion:** *Assignable type* is the **step that identifies the set of beans with a compatible type**, yet candidate selection in Spring also depends on **autowire eligibility, qualifiers, generics, primary/fallback, scope, and injection point context**. A bean with a matching type is **not automatically** injected; conversely, multiple type matches can be intentionally resolved by Spring into a single bean or a collection.

References:
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-autowire.html)
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Primary and Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html)
- [Spring API — `ListableBeanFactory`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html)
- [Spring API — `ResolvableType`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ResolvableType.html)
- [Java 17 — `Class.isAssignableFrom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isAssignableFrom(java.lang.Class))

**Rule of thumb to apply:** When debugging an un-injected dependency, trace in order: **Java type compatibility → Spring type discovery → autowire filtering → single or multi-candidate selection → instance lifecycle**. This mental model is far more accurate than saying “Spring sees the same interface and automatically injects it.”
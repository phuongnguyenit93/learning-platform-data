# Creating Domain-Meaningful Qualifier Annotations — Spring Framework Core Container

## 1. The Problem: Picking the Right Bean by Meaning, Not by Accidental Name

A notification system has multiple beans implementing the `Sender` interface:

- **EMAIL** channel for the **VN** market.
- **EMAIL** channel for the **GLOBAL** market.
- **SMS** channel for the **VN** market.

If a service only has the constructor:

~~~java
public NotificationService(Sender sender) {
    this.sender = sender;
}
~~~

Spring finds three beans compatible with type `Sender`. Without a unique selection cue, this single-object dependency can encounter `NoUniqueBeanDefinitionException`. Arbitrarily marking one bean `@Primary` creates a global default, yet fails to express that **a service in the VN market needs EMAIL**, while another service needs **SMS**.

A domain-meaningful approach is **creating custom qualifier annotations**:

~~~java
public NotificationService(
        @ChannelTag(Channel.EMAIL) @MarketTag("VN") Sender sender) {
    this.sender = sender;
}
~~~

This is an **illustrative snippet**, without the annotation/type definitions yet; the full runnable project is in section 7.

The two annotations at the injection point express: “Among beans of type `Sender`, choose the bean with **channel EMAIL** and **market VN**.” The intent stays clear even when developers rename `@Bean` methods or implementation classes.

**Learning objectives:**

1. Understand a qualifier as **type-scoped candidate filtering metadata**, which neither creates beans nor necessarily points to a unique bean name.
2. Create domain annotations using `@Qualifier` as a **meta-annotation**, with `@Retention(RUNTIME)` and `@Target` on the right locations.
3. Place custom qualifiers on **bean declarations** (`@Bean` methods or component classes) and on **injection points** (constructor/field/method parameters).
4. Combine **multiple qualifiers simultaneously** to express channel/market constraints; or use **one annotation with multiple attributes**.
5. Understand the rule that “a bean must match all requested attributes,” with no implicit wildcard or OR logic.
6. Know how to apply a qualifier to `List<Sender>` to filter **multiple beans of the same channel**, and use `@Order` to sort collections.
7. Distinguish `@Primary`, `@Fallback`, `@Named`, `@Resource`, generic qualifiers, and selection by bean name.
8. Run a **Java 17+ / Spring Framework 6.2.19** example with Maven and `javac`/`java`, verifying deterministic stdout.
9. Diagnose missing candidates, multiple candidates sharing a qualifier, missing `RUNTIME`, misplaced annotations, or unregistered beans.

**Scope:** custom annotation qualifiers for **domain-based bean selection** in Spring Core Container. No Spring Boot, MVC, persistence, networking, or real email/SMS integration is required.

## 2. Foundation: From `@Qualifier("beanName")` to a Domain Contract

Out of the box, Spring provides:

~~~java
public BillingClient(@Qualifier("vnEmailSender") Sender sender) {
    this.sender = sender;
}
~~~

With constructor injection, `@Qualifier("vnEmailSender")` can narrow down to the corresponding bean. However, the name `vnEmailSender` reflects **registration** details more than an evolving domain model.

Another requirement:

- One consumer needs an **EMAIL** sender regardless of specific market.
- Another consumer needs a sender serving **VN**, whether EMAIL or SMS.
- A single-valued consumer needs specifically **EMAIL + VN**.

Use two meaningful annotations:

~~~java
@ChannelTag(Channel.EMAIL)
@MarketTag("VN")
Sender sender
~~~

instead of bean name strings such as `"vnEmailSender"` or `"sender1"`. They express **traits that can remain stable even when bean names change**.

| Expression | Meaning | Notable point |
| --- | --- | --- |
| `Sender sender` | Requests a bean of type `Sender` | Can be ambiguous if multiple candidates exist |
| `@Qualifier("vnEmailSender") Sender sender` | Narrows by qualifier/bean name | Tends to couple to a specific wiring name |
| `@ChannelTag(EMAIL) Sender sender` | Accepts only `Sender` of channel EMAIL | Multiple markets may still exist |
| `@MarketTag("VN") Sender sender` | Accepts only `Sender` for market VN | Multiple channels may still exist |
| `@ChannelTag(EMAIL) @MarketTag("VN") Sender sender` | `Sender` satisfying **both** conditions | Unique if only one candidate remains |
| `@ChannelTag(EMAIL) List<Sender> senders` | All `Sender` beans tagged EMAIL | Does not require a unique qualifier |

**Keyword:** qualifiers **narrow** the set of candidates already compatible with the Java type. An annotation cannot cause a `PaymentGateway` to be injected into a `Sender` parameter if the class is not type-compatible. Nor does it turn a bean name into an object when non-Spring code simply calls `new`.

## 3. What Parts Does a Custom Annotation Need?

A custom qualifier for notification channels:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.beans.factory.annotation.Qualifier;

enum Channel {
    EMAIL, SMS
}

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.METHOD,
        ElementType.TYPE,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface ChannelTag {
    Channel value();
}
~~~

**This is an illustrative annotation sample**, not a complete Java file: a single Java file cannot contain both this public annotation and another public demo class. In section 7, the annotations are declared **nested inside a public class**, avoiding any error about multiple public top-level types.

### Three Essential Components

**`@Qualifier`:** this is the meta-annotation Spring recognizes, placed **on your annotation declaration**. It tells Spring that `@ChannelTag` must be treated as a qualifier annotation during candidate selection. You do not need to write a custom `BeanPostProcessor` just for basic custom qualifiers.

**`@Retention(RetentionPolicy.RUNTIME)`:** ensures the annotation remains present at runtime so Spring can read it via metadata/reflection. If left at the default `CLASS` or set to `SOURCE`, candidate selection by that annotation may fail to work when the container runs.

**`@Target(...)`:** selects which locations may carry the annotation. In the demo:
- `PARAMETER` for constructor/factory-method parameters.
- `METHOD` to annotate `@Bean` factory methods.
- `TYPE` to place on component classes when using component scanning.
- `FIELD` for Spring-managed field injection.
- `ANNOTATION_TYPE` if you want to build another layer of composed annotations.

You do not have to include every target; declare only the **locations you actually support**. For example, declaring only `FIELD, PARAMETER` and later placing the qualifier on a `@Bean` method **will fail to compile** because `METHOD` is disallowed.

**The `value()` member:** lets you write `@ChannelTag(Channel.EMAIL)`, passing a **strongly typed enum value**. Thanks to the enum, a typo like `Channel.EMIAL` is caught immediately by the Java compiler, unlike a string literal `"EMIAL"` that could slip through to runtime.

### Another Qualifier for the Market

~~~java
@Target({
        ElementType.FIELD, ElementType.PARAMETER,
        ElementType.METHOD, ElementType.TYPE,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface MarketTag {
    String value();
}
~~~

A similar **illustrative snippet**. Using Strings like `"VN"`/`"GLOBAL"` may suffice for small exercises; larger systems should consider a `Market.VN` enum or value object to prevent typos and protect the contract.

**Java note:** `ChannelTag` and `MarketTag` here are **annotation types**, distinct from `ChannelTag.class` (the annotation's `Class` object) and distinct from bean instances. Spring **does not create a bean instance** merely because it sees an annotation.

## 4. Using Qualifiers at Both Ends: Bean Definition and Injection Point

Attach metadata to the beans:

~~~java
@Configuration(proxyBeanMethods = false)
class SenderConfig {
    @Bean("vnEmailSender")
    @ChannelTag(Channel.EMAIL)
    @MarketTag("VN")
    Sender vnEmailSender() {
        return new InMemorySender("VN_EMAIL");
    }

    @Bean("globalEmailSender")
    @ChannelTag(Channel.EMAIL)
    @MarketTag("GLOBAL")
    Sender globalEmailSender() {
        return new InMemorySender("GLOBAL_EMAIL");
    }

    @Bean("vnSmsSender")
    @ChannelTag(Channel.SMS)
    @MarketTag("VN")
    Sender vnSmsSender() {
        return new InMemorySender("VN_SMS");
    }
}
~~~

**Configuration snippet**, requiring the types/imports and implementation; the complete example is in section 7.

View the beans as rows of tagged records:

| Bean name | Java type | Channel qualifier | Market qualifier |
| --- | --- | --- | --- |
| `vnEmailSender` | `Sender` | EMAIL | VN |
| `globalEmailSender` | `Sender` | EMAIL | GLOBAL |
| `vnSmsSender` | `Sender` | SMS | VN |

When a consumer requests:

~~~java
public VnEmailClient(
        @ChannelTag(Channel.EMAIL)
        @MarketTag("VN")
        Sender sender) {
    this.sender = sender;
}
~~~

Spring filters beans matching type `Sender`, then checks the required qualifier metadata; only `vnEmailSender` remains. **There is no reason to rely on method declaration order**.

### Two Simultaneous Annotations Form a Combined Condition

`@ChannelTag(Channel.EMAIL) @MarketTag("VN")` requires candidates matching **both dimensions**. Spring does not arbitrarily choose EMAIL *or* VN. In the table:

- `vnEmailSender` matches **both** → eligible.
- `globalEmailSender` matches EMAIL, but not VN → excluded.
- `vnSmsSender` matches VN, but not EMAIL → excluded.

If you request only `@ChannelTag(Channel.EMAIL) Sender sender` at a **single-valued** injection point, **two EMAIL beans** exist, so ambiguity can still occur. A qualifier does not guarantee uniqueness; it is strictly a filter condition.

**Good practice:** annotations should describe **domain traits** of a bean. Avoid naming an annotation `@ExactBeanWithNameVnEmailSender` and treating it as a bean-name-independent architecture.

## 5. Place Qualifiers on `@Component` or on `@Bean`?

Spring supports qualifier metadata on scanned component beans:

~~~java
@Component
@ChannelTag(Channel.EMAIL)
@MarketTag("VN")
public final class VietnamEmailSender implements Sender {
    // Implement Sender...
}
~~~

For beans created by `@Bean` methods, place qualifiers on the **factory method / bean definition** as in section 4:

~~~java
@Bean("vnEmailSender")
@ChannelTag(Channel.EMAIL)
@MarketTag("VN")
Sender sender() {
    return new InMemorySender("VN_EMAIL");
}
~~~

**These two snippets are alternatives**, not run together in the demo. Distinguish them:

- Class-level qualifiers are useful when a component class corresponds to one fixed set of traits.
- Method-level qualifiers allow a single implementation class to produce **multiple distinct beans**, each definition carrying its own channel/market traits.
- Do not annotate the `InMemorySender` class alone with `@ChannelTag(EMAIL)` and expect two SMS/VN and EMAIL/VN beans created from that class to automatically carry different metadata. When variants are configured via factory methods, put the annotations **on each method**.
- `@Component` and `@Bean` are registration mechanisms; `@ChannelTag` alone **is not a bean-creating stereotype**.
- A `@Component` class outside component-scan scope will not appear automatically either; the runnable example calls `context.register(...)` explicitly.

### Is `@Autowired` Required on the Constructor?

If a component class has **only one constructor**, Spring 4.3+ automatically chooses that constructor without requiring `@Autowired`:

~~~java
@Component
public final class VnEmailClient {
    private final Sender sender;

    public VnEmailClient(
            @ChannelTag(Channel.EMAIL)
            @MarketTag("VN")
            Sender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }
}
~~~

This snippet requires the corresponding types and imports. Spring still reads **parameter annotations** on that single constructor when resolving collaborators. `@Autowired` is optional in that case; custom qualifiers do not replace bean registration.

If there are **multiple constructors**, explicitly designate the constructor to use via `@Autowired` or an appropriate definition. Do not assume placing a qualifier on a parameter forces Spring to pick the overload containing that parameter.

## 6. Lesson on Collections and `@Order`

A service needs to send messages through **all EMAIL channels**, without restricting to a single market:

~~~java
public EmailBatch(
        @ChannelTag(Channel.EMAIL) List<Sender> senders) {
    this.senders = List.copyOf(senders);
}
~~~

Spring can inject **two beans** matching `@ChannelTag(Channel.EMAIL)`: VN_EMAIL and GLOBAL_EMAIL. Here, the qualifier acts as a **collection filter**, not a request to pick a single bean.

Another service wants only all senders for the VN market:

~~~java
public VnBatch(
        @MarketTag("VN") List<Sender> senders) {
    this.senders = List.copyOf(senders);
}
~~~

It receives VN_EMAIL and VN_SMS.

**`@Order` can sort beans in List/array injection**. With annotations on `@Bean` methods:

~~~java
@Bean
@Order(1)
@ChannelTag(Channel.EMAIL)
Sender firstEmail() { /* implementation */ }

@Bean
@Order(2)
@ChannelTag(Channel.EMAIL)
Sender secondEmail() { /* implementation */ }
~~~

these snippets **illustrate metadata only**; the methods must return actual `Sender` instances inside a configuration class. When Spring injects `List<Sender>`, ordering can follow `@Order`. **Do not use `@Order(1)` in place of `@Primary` when a single bean is required**.

**Caution:** `@Order` does not guarantee that singletons are instantiated in that same order, nor does it alter qualifier matching. It provides sorting metadata for collection results. When business logic requires a strict order, attach explicit metadata/tests; when only an unordered set is needed, avoid creating unnecessary dependence on registration order.

## 7. Complete Example with Java 17+ / Spring Framework 6.2.19

**Idea:** keep one `Sender` interface and three beans of the same type carrying domain labels. Three consumers use two custom qualifiers on their constructors, and two batch consumers filter collections along one dimension. Everything is Spring-managed; there is no real networking.

Runs with **JDK 17+**, Maven, and Spring Framework **6.2.19** (pinned for reproducibility, not claimed as the latest Spring release). Requires no Spring Boot or real sending service.

### 7.1. Project Structure

~~~text
custom-business-qualifier/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BusinessQualifierDemo.java
~~~

### 7.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>custom-business-qualifier</artifactId>
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
                    <mainClass>demo.BusinessQualifierDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring dependencies are resolved by Maven. If running `javac`/`java` directly, the compile/runtime classpath must include `spring-context` and its required transitive JARs.

### 7.3. `src/main/java/demo/BusinessQualifierDemo.java`

~~~java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

public final class BusinessQualifierDemo {
    private BusinessQualifierDemo() {}

    public enum Channel {
        EMAIL, SMS
    }

    @Documented
    @Retention(RetentionPolicy.RUNTIME)
    @Target({
        ElementType.FIELD, ElementType.PARAMETER,
        ElementType.METHOD, ElementType.TYPE,
        ElementType.ANNOTATION_TYPE
    })
    @Qualifier
    public @interface ChannelTag {
        Channel value();
    }

    @Documented
    @Retention(RetentionPolicy.RUNTIME)
    @Target({
        ElementType.FIELD, ElementType.PARAMETER,
        ElementType.METHOD, ElementType.TYPE,
        ElementType.ANNOTATION_TYPE
    })
    @Qualifier
    public @interface MarketTag {
        String value();
    }

    public interface Sender {
        String send(String recipient);
    }

    public record InMemorySender(String label) implements Sender {
        public InMemorySender {
            Objects.requireNonNull(label);
        }

        @Override
        public String send(String recipient) {
            if (recipient == null || recipient.isBlank()) {
                throw new IllegalArgumentException("recipient required");
            }
            return label + ":" + recipient.strip();
        }
    }

    @Component
    public static final class VnEmailClient {
        private final Sender sender;

        public VnEmailClient(
                @ChannelTag(Channel.EMAIL)
                @MarketTag("VN")
                Sender sender) {
            this.sender = Objects.requireNonNull(sender);
        }

        public Sender sender() {
            return sender;
        }

        public String notify(String recipient) {
            return sender.send(recipient);
        }
    }

    @Component
    public static final class GlobalEmailClient {
        private final Sender sender;

        public GlobalEmailClient(
                @ChannelTag(Channel.EMAIL)
                @MarketTag("GLOBAL")
                Sender sender) {
            this.sender = Objects.requireNonNull(sender);
        }

        public String notify(String recipient) {
            return sender.send(recipient);
        }
    }

    @Component
    public static final class VnSmsClient {
        private final Sender sender;

        public VnSmsClient(
                @ChannelTag(Channel.SMS)
                @MarketTag("VN")
                Sender sender) {
            this.sender = Objects.requireNonNull(sender);
        }

        public String notify(String recipient) {
            return sender.send(recipient);
        }
    }

    @Component
    public static final class EmailBatch {
        private final List<Sender> senders;

        public EmailBatch(@ChannelTag(Channel.EMAIL)
                          List<Sender> senders) {
            this.senders = List.copyOf(senders);
        }

        public int size() {
            return senders.size();
        }

        public String sendAll(String recipient) {
            return senders.stream()
                    .map(sender -> sender.send(recipient))
                    .collect(Collectors.toList()).toString();
        }
    }

    @Component
    public static final class VnBatch {
        private final List<Sender> senders;

        public VnBatch(@MarketTag("VN") List<Sender> senders) {
            this.senders = List.copyOf(senders);
        }

        public String sendAll(String recipient) {
            return senders.stream()
                    .map(sender -> sender.send(recipient))
                    .toList().toString();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SenderConfig {
        @Bean("vnEmailSender")
        @ChannelTag(Channel.EMAIL)
        @MarketTag("VN")
        @Order(1)
        public Sender vnEmailSender() {
            return new InMemorySender("VN_EMAIL");
        }

        @Bean("globalEmailSender")
        @ChannelTag(Channel.EMAIL)
        @MarketTag("GLOBAL")
        @Order(2)
        public Sender globalEmailSender() {
            return new InMemorySender("GLOBAL_EMAIL");
        }

        @Bean("vnSmsSender")
        @ChannelTag(Channel.SMS)
        @MarketTag("VN")
        @Order(3)
        public Sender vnSmsSender() {
            return new InMemorySender("VN_SMS");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            // Explicit registration; no package scanning assumptions.
            context.register(SenderConfig.class,
                    VnEmailClient.class, GlobalEmailClient.class,
                    VnSmsClient.class, EmailBatch.class, VnBatch.class);
            context.refresh();

            VnEmailClient vnEmail =
                    context.getBean(VnEmailClient.class);
            GlobalEmailClient globalEmail =
                    context.getBean(GlobalEmailClient.class);
            VnSmsClient vnSms =
                    context.getBean(VnSmsClient.class);
            EmailBatch emailBatch = context.getBean(EmailBatch.class);
            VnBatch vnBatch = context.getBean(VnBatch.class);

            System.out.println("vnEmail=" +
                    vnEmail.notify(" Lan "));
            System.out.println("globalEmail=" +
                    globalEmail.notify(" Minh "));
            System.out.println("vnSms=" + vnSms.notify(" An "));
            System.out.println("emailBatch=" +
                    emailBatch.sendAll(" Mai "));
            System.out.println("vnBatch=" +
                    vnBatch.sendAll(" Hoa "));
            System.out.println("sameVnEmail=" +
                    (vnEmail.sender()
                     == context.getBean("vnEmailSender", Sender.class)));
            System.out.println("senderNames=" +
                    java.util.Arrays.stream(
                            context.getBeanNamesForType(Sender.class))
                            .sorted().toList());

            try {
                context.getBean(Sender.class);
                System.out.println("rawTypeLookup=UNEXPECTED");
            } catch (NoUniqueBeanDefinitionException expected) {
                System.out.println("rawTypeLookup=AMBIGUOUS");
            }

            System.out.println("emailBatchCount=" +
                    emailBatch.size());
        }
    }
}
~~~

**Why the example is clear and runs standalone:**

- There is exactly one public top-level class `BusinessQualifierDemo`; annotations, enum, records, config, and consumer classes are nested types. File name and package match the CLI commands.
- `@ChannelTag` and `@MarketTag` are declared as nested `public @interface` types with `@Qualifier`, `@Retention(RUNTIME)`, `@Target`, and `@Documented`.
- `SenderConfig` registers three beans sharing the declared return type `Sender` yet carrying different qualifier metadata, via three separate `@Bean` methods.
- The three client components each have a single constructor, so Spring detects the injection constructor without `@Autowired`, while parameter qualifiers still apply.
- `EmailBatch`/`VnBatch` are also registered directly. `@ChannelTag(EMAIL) List<Sender>` filters the two EMAIL beans; `@MarketTag("VN") List<Sender>` filters the two VN beans.
- `@Order(1)`/`@Order(2)`/`@Order(3)` on the `@Bean` methods make collection ordering explicit. With only three labels, stdout does not depend on any `HashMap` order.
- `java.util.Arrays.stream(...).sorted().toList()` sorts bean names before printing, independent of incidental registration order.
- `InMemorySender` is a Java 17 record replacing a real sender with simple logic; there is no networking, timer, randomness, or I/O besides stdout.
- Because three `Sender` beans coexist, `getBean(Sender.class)` has no qualifier or primary; the demo properly catches `NoUniqueBeanDefinitionException`.
- Beans are singletons by default within this context; `sameVnEmail=true` proves bean identity only within **one context**, making no promises about prototypes, scoped proxies, or other contexts.

### 7.4. Running via Maven

Inside the `custom-business-qualifier` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exactly nine stdout lines printed by `main` on a successful run:**

~~~text
vnEmail=VN_EMAIL:Lan
globalEmail=GLOBAL_EMAIL:Minh
vnSms=VN_SMS:An
emailBatch=[VN_EMAIL:Mai, GLOBAL_EMAIL:Mai]
vnBatch=[VN_EMAIL:Hoa, VN_SMS:Hoa]
sameVnEmail=true
senderNames=[globalEmailSender, vnEmailSender, vnSmsSender]
rawTypeLookup=AMBIGUOUS
emailBatchCount=2
~~~

Java/Maven version lines, artifact downloads, or Spring/Maven logs (if any) are not part of the nine lines emitted by `System.out.println` in the code above.

### 7.5. Running Directly with `javac`/`java`

Generate the classpath from Maven-resolved dependencies:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Linux/macOS (bash/zsh):

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BusinessQualifierDemo.java
java -cp "out:$(cat classpath.txt)" demo.BusinessQualifierDemo
~~~

Windows PowerShell:

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BusinessQualifierDemo.java
java -cp "out;$deps" demo.BusinessQualifierDemo
~~~

On Unix, the classpath separator is `:`; on Windows, it is `;`. Both commands invoke the same `main`, so the nine lines printed by the code are identical. If `javac` cannot find `org.springframework.*`, inspect build/classpath setup before concluding custom annotations or bean resolution failed.

## 8. Explaining the Output: Qualifiers Truly Select by Domain Meaning

| Stdout line | Meaning |
| --- | --- |
| `vnEmail=VN_EMAIL:Lan` | Combined EMAIL + VN conditions pick the right sender |
| `globalEmail=GLOBAL_EMAIL:Minh` | EMAIL + GLOBAL picks the other implementation |
| `vnSms=VN_SMS:An` | SMS + VN picks the VN_SMS bean |
| `emailBatch=[VN_EMAIL:Mai, GLOBAL_EMAIL:Mai]` | Collection filters by EMAIL without restricting market |
| `vnBatch=[VN_EMAIL:Hoa, VN_SMS:Hoa]` | Collection filters by VN without restricting channel |
| `sameVnEmail=true` | Bean resolved via custom qualifiers is the Spring bean named `vnEmailSender` |
| `senderNames=[...]` | All three `Sender` beans are registered side by side |
| `rawTypeLookup=AMBIGUOUS` | Bare type lookup needs one bean yet has no unique choice |
| `emailBatchCount=2` | The EMAIL filter yields exactly two candidates |

On the client constructors, `@ChannelTag(Channel.EMAIL)` and `@MarketTag("VN")` are **injection-point metadata**. In `SenderConfig`, those same annotations are **candidate metadata**. Spring matches them when resolving a `Sender` dependency.

**Key point:** no client calls `ApplicationContext.getBean("vnEmailSender")` inside a business method. Spring resolves the dependency during the **composition/wiring phase**; clients invoke only the `Sender` interface.

## 9. Multiple Conditions Can Be Combined into One Multi-Attribute Annotation

Instead of two annotations:

~~~java
@ChannelTag(Channel.EMAIL)
@MarketTag("VN")
Sender sender
~~~

you can define one domain qualifier with two members:

~~~java
@Target({
    ElementType.FIELD, ElementType.PARAMETER,
    ElementType.METHOD, ElementType.TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface RouteTag {
    Channel channel();
    String market();
}
~~~

And apply it:

~~~java
@Bean
@RouteTag(channel = Channel.EMAIL, market = "VN")
Sender vnEmailSender() {
    return new InMemorySender("VN_EMAIL");
}

public VnClient(
        @RouteTag(channel = Channel.EMAIL, market = "VN")
        Sender sender) {
    this.sender = sender;
}
~~~

**These are alternative snippets, not a second file to run.** In practice, import/define `Channel`, `Sender`, `InMemorySender`, `VnClient`, and the corresponding `@Configuration`. In a custom qualifier with multiple attributes, a candidate bean must **match the requested attributes**. Any default value on an attribute (if present) is an actual metadata value, **not automatically a wildcard**.

### Choose One Multi-Attribute Annotation or Multiple Independent Annotations?

| Design | When suitable | Pitfall to avoid |
| --- | --- | --- |
| `@ChannelTag(EMAIL) @MarketTag("VN")` | Channel and market are independent dimensions that may be filtered individually or combined | Leaving off one constraint when a consumer requires both |
| `@RouteTag(channel=EMAIL, market="VN")` | Channel + market form a cohesive domain concept | Assuming omitting an attribute or setting a default creates a wildcard |
| `@Qualifier("vnEmailSender")` | Small system or consumer needs an exact bean with a stable name | Coupling to hard-to-rename bean names |
| `@Primary` | There is one valid default for most consumers | Does not properly express per-market selection |
| Inject `List<Sender>` filtered by qualifier | Consumer needs multiple strategies sharing a trait | Never grab the first element as an arbitrary single choice |

If the business domain uses a standardized taxonomy of channels or markets, prefer **enums** for finite value sets. If metadata spans multiple independently varying dimensions, small separate qualifiers offer more flexible composition.

## 10. Good Annotation Contracts: Naming, Types, Scope

### 10.1. Name by Semantics

Names like `@ChannelTag` and `@MarketTag` state traits clearly. An annotation like `@EmailSenderBean42` or `@BeanImplA` forces business code to know implementation registration details. Qualifiers should describe **roles** rather than internal bean identities.

Examples of meaningful domain names:

- `@StorageTier(Storage.COLD)` / `@StorageTier(Storage.HOT)`.
- `@Region(Region.APAC)` / `@Region(Region.EMEA)`.
- `@DeliveryChannel(Channel.EMAIL)` / `@DeliveryChannel(Channel.SMS)`.
- `@ReadReplica` / `@PrimaryStore`, when database routing genuinely needs that distinction.

Those examples are merely **illustrative names**, not built-in Spring annotation types.

### 10.2. Clarify Cardinality

A qualifier **does not have to be unique** across the entire context. Two EMAIL beans may exist for two markets. For injecting a single `Sender`, ensure the combination of qualifiers/candidate selection narrows down to one. For collection injection, multiple matches are intentional.

If a domain contract demands **at most one implementation**, write a startup test to catch having two beans with identical type and qualifiers after adding a new module.

### 10.3. Choose Strongly Typed Data

Using `Channel.EMAIL` instead of the string `"EMAIL"` prevents typos at compile time. For `String market`, standardize on constants or an enum when the catalog is finite; watch out for casing and locale. Spring does not treat `"VN"` as equivalent to `"vn"` inside a qualifier string.

### 10.4. Do Not Encode Runtime Logic Inside Annotations

Annotations carry static metadata; they are not the place to compute dynamic decisions based on user, request, or time. If a customer can switch channels per runtime input, injecting one fixed `Sender` at startup may not suffice. Inject a **Map/list/provider** of eligible strategies and select via a tested **domain routing policy**. Never expect an annotation to change per HTTP request.

### 10.5. Scope and Lifecycle Are Not Controlled by Qualifiers

Custom qualifiers only participate in **candidate selection**. They do not make a bean singleton/prototype, make an object thread-safe, open transactions, or alter initialization timing. Picking the right bean still requires checking lifecycle, scope, and concurrency safety when the same instance is shared across threads.

## 11. Where Does Spring Look for Custom Qualifier Metadata?

**Component class:**

~~~java
@Component
@ChannelTag(Channel.EMAIL)
public class EmailSender implements Sender {
    // ...
}
~~~

**`@Bean` factory method:**

~~~java
@Bean
@ChannelTag(Channel.EMAIL)
Sender sender() {
    return new InMemorySender("EMAIL");
}
~~~

**Constructor parameter:**

~~~java
public Client(@ChannelTag(Channel.EMAIL) Sender sender) {
    this.sender = sender;
}
~~~

**Field injection:**

~~~java
@Autowired
@ChannelTag(Channel.EMAIL)
private Sender sender;
~~~

**Setter/method parameter:**

~~~java
@Autowired
public void setSender(
        @ChannelTag(Channel.EMAIL) Sender sender) {
    this.sender = sender;
}
~~~

**Illustrative snippets**; each requires its own class/imports and definitions. Do not paste them directly into the main project, as they could create unintended extra beans with the same qualifier. For mandatory collaborators, constructor injection shows dependencies more clearly than field or setter injection and is easier to unit test in plain Java.

**You do not need `@Autowired` on every parameter**. In Spring, once a method or constructor is chosen as the injection point, metadata such as custom qualifiers is read from its parameters. On a component with a single constructor, Spring automatically uses that constructor without `@Autowired`.

If a class is instantiated via Java `new` outside the container, placing `@ChannelTag` and `@Autowired` on its fields **does not cause the JVM to inject them**; it remains an unmanaged object that must be processed by Spring or wired via manual DI.

## 12. How Do `@Primary`, `@Fallback`, and Qualifiers Interact?

| Mechanism | Role |
| --- | --- |
| `@Qualifier("...")` | Narrows candidates by matching metadata/bean name |
| Custom `@ChannelTag`/`@MarketTag` | Narrows by strongly typed domain meaning |
| `@Primary` | Marks a preferred default candidate when eligible |
| `@Fallback` | Lowers candidate precedence in Spring Framework 6.2+ |
| `@Order` | Sorts collection injection; does not implicitly resolve a single bean |
| `@Bean(defaultCandidate=false)` | Eligible only when the injection point provides an explicit cue such as a matching qualifier |
| `@Bean(autowireCandidate=false)` | Excludes bean from type-driven autowiring; not merely lower priority |

The key mindset is **selecting from type-compatible candidates that satisfy metadata**, rather than assuming every annotation registers, instantiates, or completely removes a bean.

**Example:** if `globalEmailSender` is marked `@Primary`, an injection point requiring **EMAIL+VN** must not silently receive GLOBAL. The GLOBAL bean fails `@MarketTag("VN")`. Conversely, an injection point requesting only EMAIL can receive primary GLOBAL under the standard resolution rules.

**Do not put `@Primary` on multiple beans of the same type** and expect Spring to resolve ambiguity. Pick one default for a sound domain reason or use explicit qualifiers on consumers.

## 13. Two Main Errors After Creating Custom Qualifiers: Missing Bean or Multiple Beans

### No Matching Candidate

For instance, a consumer requests `@ChannelTag(Channel.SMS) @MarketTag("GLOBAL") Sender`, while only VN_SMS, VN_EMAIL, and GLOBAL_EMAIL are registered.

Spring sees no bean satisfying **both SMS and GLOBAL**, so the required dependency fails. You may see `UnsatisfiedDependencyException` caused by `NoSuchBeanDefinitionException` or a “No qualifying bean” message depending on creation path and version.

**Fix:** register the SMS_GLOBAL bean if the domain expects one, or fix the consumer's intent if you requested the wrong combination. **Do not** switch to `@Autowired(required=false)` merely to let startup succeed when the dependency is actually mandatory.

### Multiple Candidates with the Same Qualifier

If you accidentally register two `Sender` beans both carrying `@ChannelTag(EMAIL)` and `@MarketTag("VN")`, single-valued injection can still **be ambiguous**. Different bean names do not make the qualifiers unique.

**Fix:** decide whether two implementations are truly needed for the same route. If yes, the consumer needs a more specific selection rule or collection/provider injection. If not, fix registration so only one bean matches that contract. `@Primary` can be an option if there truly is a default, though tests are needed to avoid hiding misconfiguration.

### Annotation Missing Due to Forgotten `@Retention(RUNTIME)`

A custom annotation without runtime retention appears in source code yet is invisible to Spring when resolving metadata. Check the annotation declaration itself, not only the injection point.

### `@Target` Too Narrow

Declaring `@Target(FIELD)` and placing the annotation on a `@Bean` method causes a compile error. When an annotation is used on both bean definitions and parameters, include `METHOD` and `PARAMETER` (alongside any other needed targets).

### Missing `@Qualifier` on the Annotation Declaration

A custom annotation lacking Spring's `@Qualifier` meta-annotation (or not otherwise registered via a Spring-supported mechanism) is usually just arbitrary Java metadata and **does not automatically act as an autowiring qualifier**. For Spring-based qualifiers, place `@Qualifier` in the right place.

Spring also offers `CustomAutowireConfigurer` for annotation types you cannot edit to add Spring `@Qualifier`; that is an infrastructure tool **not needed in this demo**.

### Annotation Placed Only on the Injection Point

If the candidate bean lacks corresponding qualifier metadata, Spring cannot match that domain annotation to the route. Inspect **both the bean declaration and the injection site**, especially when beans come from `@Bean` factory methods.

### Bean Registration and Component Scan Mistakes

A `@Component` class that is never scanned or registered does not become a bean. A class annotated with `@ChannelTag` without a stereotype or `@Bean` declaration does not become a bean either. Verify which beans actually exist in the context.

### Type / Generic Metadata Errors

A qualifier cannot turn a `Sender<Email>` into a `Sender<Sms>` if generic specializations are incompatible. Factory methods declaring overly broad return types can also hinder matching; keep declared return types expressive of the full contract.

## 14. Systematic Diagnosis

| Symptom | What to check | Fix |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` | Multiple `Sender` beans satisfy the same qualifiers | Add a meaningful constraint or change consumer to `List`/`Map` |
| `NoSuchBeanDefinitionException` | No candidate matches type + qualifier | Inspect metadata on both bean and injection point |
| `UnsatisfiedDependencyException` | Constructor/factory parameter cannot be resolved | Read `Caused by`, bean names, and qualifiers |
| Annotation is ignored | Missing `@Qualifier` meta-annotation or `RUNTIME` retention | Fix the custom annotation declaration |
| Annotation cannot be placed on `@Bean` | Missing `METHOD` in `@Target` | Add the required target |
| Class has `@Component` yet no bean exists | Not scanned or registered | Configure component scan or register explicitly |
| One consumer gets the right bean, another gets the wrong one | Different qualifier, wrong name, or string typo | Compare attribute values and casing at each injection point |
| List receives two beans when only one is wanted | Injection point uses `List` instead of single `Sender` | Match cardinality to business intent |
| Wrong List order | Missing or misplaced `@Order` | Place `@Order` on the right `@Bean` methods or components |
| String qualifier finds no match | Wrong value or case mismatch | Use enums/constants and add wiring tests |
| Bean disappears when switching profiles | Bean definition excluded by profile/condition | Check active profiles and bean registrations |
| Using `@Primary` routes to the wrong bean | Assuming primary bypasses qualifiers | Verify type/qualifier sets and test bean identity |
| Unit test instantiates class with `new` and `@Autowired` field is null | Unmanaged object outside Spring | Use constructor injection or context tests for wiring |
| `javac` missing Spring packages | Build/classpath missing dependencies | Check Maven POM and `javac -cp` |

**Reliable debugging workflow:**

1. Identify the **injection point**: what type does it need, how many qualifiers does it have, and what are their attribute values?
2. List the **actually registered bean definitions**; verify names, declared return types, scopes, and qualifier metadata.
3. Verify **type/generic compatibility** first, then compare **each qualifier**.
4. Check `@Primary`/`@Fallback`/candidate flags and any relevant profile conditions.
5. If multiple beans remain, ask whether a single candidate or a collection is needed. If zero remain, find the registration or metadata mismatch.
6. Reproduce with a minimal Spring context test containing as few beans as possible; never rely on source-code order.
7. Verify **bean object identity and behavior**, not merely that the context refreshed without throwing.

### Quick Context Inspection

~~~java
String[] names = context.getBeanNamesForType(Sender.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
~~~

This **snippet** reveals bean names of the same type; run it in a scope with `context` and the `Sender` interface. **Presence in this list does not guarantee a bean satisfies any custom qualifier**. To verify the exact condition, test actual injection or inspect the corresponding bean definition metadata.

## 15. Testing to Protect the Domain Contract

**Plain Java unit test:** the `VnEmailClient` constructor takes a `Sender` object. Using a fake:

~~~java
Sender fake = recipient -> "TEST:" + recipient;
VnEmailClient client = new VnEmailClient(fake);
System.out.println(client.notify("Lan")); // TEST:Lan
~~~

This is a **snippet** with access to the demo's nested types. Parameter annotations do not block a caller invoking `new`; the Java unit test passes the desired dependency directly. It tests consumer behavior, not Spring qualifier selection.

**Spring wiring test:** using a configuration like the demo, verify:

- `VnEmailClient.sender() == context.getBean("vnEmailSender", Sender.class)`.
- `GlobalEmailClient` returns `GLOBAL_EMAIL`, `VnSmsClient` returns `VN_SMS`.
- `EmailBatch` contains only the two EMAIL senders and `VnBatch` contains only the two VN senders, in expected `@Order`.
- Bare type lookup `context.getBean(Sender.class)` fails due to ambiguity.
- Adding a candidate for another market does not alter a client whose qualifiers are sufficiently tight.
- Missing a mandatory candidate causes the context to fail in a **separate negative test**.
- Registering two beans for the same route makes single injection fail with ambiguity when no other disambiguator exists.

**Do not rely on Java's `assert` keyword as a mandatory guarantee** when the JVM may run without `-ea`; in integration tests, use test-framework assertions or explicit `if`/`throw`. Do not pin tests to the full verbatim stack trace because Spring may wrap exceptions or reword messages across versions.

### When Are Custom Qualifiers Overkill?

A project with exactly **one** `Sender` implementation does not need three distinct annotations and enums. With just two beans and one consumer, `@Qualifier("mainSender")` may be enough. Custom qualifiers shine when there is **a stable domain concept** shared across multiple consumers where bean names alone do not convey full intent.

The “value” of an abstraction should be judged by readability, reuse, and fewer wiring bugs—**not by how many annotations were written**.

## 16. Self-Check Exercises

**Exercise 1.** Three beans: VN_EMAIL, GLOBAL_EMAIL, VN_SMS. What does injection point `@ChannelTag(EMAIL) @MarketTag("VN") Sender` receive?

**Answer:** The VN_EMAIL bean. It satisfies type `Sender`, channel EMAIL, and market VN.

**Exercise 2.** Only `@ChannelTag(EMAIL) Sender` appears on a constructor needing one object. Is it guaranteed unique?

**Answer:** No. Both VN_EMAIL and GLOBAL_EMAIL match the channel, so ambiguity can occur.

**Exercise 3.** How many elements does `@ChannelTag(EMAIL) List<Sender>` receive?

**Answer:** The two EMAIL `Sender` beans in the demo; the qualifier filters the collection rather than picking one.

**Exercise 4.** Why is `@Retention(RUNTIME)` needed?

**Answer:** So the qualifier metadata remains available when Spring performs bean candidate resolution at runtime.

**Exercise 5.** Placing `@ChannelTag` only on the injection parameter and not on bean definitions—is that enough?

**Answer:** Not in the demo setup; for Spring to match by channel, candidate beans must carry the matching qualifier metadata. Check both producer and consumer sides.

**Exercise 6.** Does `@ChannelTag(EMAIL) @MarketTag("VN")` mean EMAIL or VN?

**Answer:** No. These qualifiers combine to require that a candidate satisfies all stated constraints; they do not form an automatic OR expression.

**Exercise 7.** Does `@Order(1)` on SMS cause single injection to always pick SMS?

**Answer:** No. `@Order` sorts multiple beans in collections; single-valued injection needs its own selection rule such as a qualifier or primary.

**Exercise 8.** Can the same `InMemorySender` class be reused for multiple distinct bean routes?

**Answer:** Yes. Place qualifier metadata on each `@Bean` factory method to distinguish each bean definition.

**Exercise 9.** If the market name changes from VN to VIETNAM on the producer while the injection point still says VN, what happens?

**Answer:** Metadata no longer matches, so required injection can fail. Use enums/constants and wiring tests to protect the contract.

**Exercise 10.** When a service must pick a channel per runtime request, can a fixed constructor qualifier solve it?

**Answer:** Not by itself. Design a runtime router/strategy selector, such as injecting multiple `Sender` beans and mapping them by a validated domain key.

**Exercise 11.** Does a custom qualifier automatically create a new bean?

**Answer:** No. It is strictly metadata that filters bean definitions registered through supported Spring mechanisms.

**Exercise 12.** When should you use a single multi-attribute qualifier instead of two independent qualifiers?

**Answer:** When channel + market represent a single cohesive concept that always travels together. If each dimension needs to filter collections independently, two small qualifiers are usually more flexible.

## 17. Application Checklist

- [ ] Annotation names clearly state domain roles rather than encoding a bean name.
- [ ] `@Qualifier` is present on the **annotation declaration**.
- [ ] `@Retention(RetentionPolicy.RUNTIME)` is present.
- [ ] `@Target` allows `PARAMETER`, `METHOD`, `TYPE`, or `FIELD` as needed.
- [ ] `value()` / named members are strongly typed, preferring enums when appropriate.
- [ ] Qualifiers are attached to each `@Bean` method or component class that needs distinction.
- [ ] Matching qualifiers are placed on injection points, not only on producers or only on consumers.
- [ ] When multiple qualifiers are combined, treat them as **AND**, not OR.
- [ ] For single-valued injection, verify exactly one eligible candidate remains.
- [ ] For collections, verify expected members and ordering.
- [ ] Do not use `@Order` in place of `@Qualifier`/`@Primary` for single injection.
- [ ] Do not rely on incidental bean/parameter names when domain semantics must stay stable.
- [ ] Do not slap `@Primary` indiscriminately to hide two duplicate-route beans.
- [ ] Do not confuse qualifiers with stereotypes, scopes, or lifecycle.
- [ ] Maintain unit tests for logic and integration tests for wiring.
- [ ] Run Java 17+ Maven/`javac`/`java` and verify the **9 stdout lines**.
- [ ] In large applications, document the channel/market taxonomy and annotation ownership.
- [ ] When upgrading Spring versions, re-check candidate selection policies and tests before deployment.

**Conclusion:** Custom qualifier annotations bring **domain language** directly to the dependency injection boundary. Instead of asking for a bean named `vnEmailSender`, a consumer can request a **Sender for channel EMAIL in market VN**. Spring filters type-compatible beans by qualifier metadata and selects either one candidate or a collection of matches per contract. Sound annotation design requires proper Java retention/target, consistent producer/injection metadata, and wiring tests to prevent regressions as new implementations are added.

### Official Spring Documentation

- [Spring Framework 6.2 — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework 6.2 — Providing Qualifier Metadata with Annotations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html)
- [Spring Framework 6.2 — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html)
- [Spring API — Qualifier](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/annotation/Qualifier.html)
- [Spring Framework 6.2 — CustomAutowireConfigurer](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/custom-autowire-configurer.html)

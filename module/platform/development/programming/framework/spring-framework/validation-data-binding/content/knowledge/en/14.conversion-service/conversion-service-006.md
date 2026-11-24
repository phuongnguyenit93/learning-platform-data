# ConversionServiceFactoryBean and the conversionService Bean Name

In Spring Core, `ConversionService` is the central API for converting a value from one type to another. An application can register one instance for the entire `ApplicationContext`, after which Spring uses it whenever data conversion is needed; other beans can also inject and invoke that service directly.

In traditional XML configuration, the common declaration is:

~~~xml
<bean id="conversionService"
      class="org.springframework.context.support.ConversionServiceFactoryBean"/>
~~~

There are two very important details:

1. `ConversionServiceFactoryBean` is a **Spring FactoryBean**. The bean exposed by the application context under the name `conversionService` is the `ConversionService` product that the factory creates.
2. The bean name `conversionService` is a **special convention name** that Spring recognizes to locate the shared conversion service. Merely creating a bean with an arbitrary name such as `myConversions` is not automatically equivalent to registering the context's default conversion service.

This guide explains the factory bean's role, why the `conversionService` name must be used, how to add custom converters, how to inject and use it, how it integrates with MVC, and common misconceptions. The main example uses Java 17+ and Spring Framework 6.2.

## 1. What Is ConversionService and Where Is It Used?

`ConversionService` lives in the `org.springframework.core.convert` package. It is the abstraction for querying and performing type conversions:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);
~~~

In addition to those two overloads, the API supports `TypeDescriptor` to describe generic types, annotations, and field/property metadata.

Example:

~~~java
Integer quantity = conversionService.convert("12", Integer.class);
LocalDate date = conversionService.convert("2026-11-02", LocalDate.class);
Priority priority = conversionService.convert("HIGH", Priority.class);
~~~

Specific conversions depend on the converters/formatters registered. A typical conversion service supports common groups such as strings, numbers, enums, collections, maps, and other standard data types.

Spring uses the conversion system in many scenarios, such as:

- Binding property values into JavaBeans via `DataBinder`/`WebDataBinder`.
- Converting request parameters to parameter types in Spring MVC.
- Performing certain type coercions in Spring Expression Language.
- Allowing application beans to call `ConversionService.convert(...)` directly.

For example, a form submits the string `"12"` for property `Integer quantity`. During property binding, Spring must find an appropriate converter to turn the string into an integer. If no conversion service is registered through the appropriate mechanism, Spring still has a legacy conversion mechanism based on `PropertyEditor`; therefore, do not conclude that without a `conversionService` bean all binding stops working.

## 2. What Does ConversionServiceFactoryBean Do?

`org.springframework.context.support.ConversionServiceFactoryBean` is a class implementing `FactoryBean<ConversionService>`. It creates a pre-configured conversion service and registers that product into the Spring container.

~~~text
ApplicationContext starts
           |
           v
 Create ConversionServiceFactoryBean
           |
           v
  Read configured converters
           |
           v
  Create internal ConversionService
           |
           v
 ApplicationContext exposes the product
    under bean name "conversionService"
           |
      +----+----------------+
      |                     |
      v                     v
 framework needs       application bean injects
 type conversion       ConversionService
~~~

Distinguishing the components:

| Name/concept | Role |
| --- | --- |
| `ConversionService` | API called by application code and Spring to check/perform conversion. |
| `ConversionServiceFactoryBean` | Spring factory that creates a `ConversionService`. |
| `ConversionServiceFactory` | Utility factory in Spring Core that can create services programmatically; not the same kind of `FactoryBean` used in XML bean declarations. |
| `conversionService` | Conventional bean name for Spring to look up the conversion service in the application context. |
| `Converter<S,T>` / `ConverterFactory<S,R>` / `GenericConverter` | SPIs implementing conversion logic registered into the conversion service. |

Because `ConversionServiceFactoryBean` is a `FactoryBean`, the lookup:

~~~java
ConversionService service =
        context.getBean("conversionService", ConversionService.class);
~~~

returns the **product** provided by the factory.

To obtain the factory bean instance itself instead of its product, prefix the bean name with `&`:

~~~java
Object factory = context.getBean("&conversionService");
~~~

Normally application code needs `ConversionService`, without interacting directly with the factory. The `&conversionService` lookup is useful when inspecting the container, debugging, or needing access to the factory bean itself.

## 3. Why Must the Bean Be Named conversionService?

Spring designates `conversionService` as the special name to auto-discover the application context's conversion service. XML example:

~~~xml
<bean id="conversionService"
      class="org.springframework.context.support.ConversionServiceFactoryBean"/>
~~~

Once the context starts, whenever a Spring component needs the default conversion service, the framework can look up the bean by this conventional name.

This differs from ordinary dependency injection:

~~~xml
<bean id="myConversions"
      class="org.springframework.context.support.ConversionServiceFactoryBean"/>
~~~

The `myConversions` bean can still be retrieved and injected by name or by type (if unambiguous), yet **do not assume Spring automatically treats it as the default conversion service** merely because its product type is `ConversionService`. When the framework needs to recognize the shared service, use the exact conventional name or register via the configuration mechanism required by that framework component.

### Inject by Type or by Name?

When there is only one product bean of type `ConversionService`, constructor injection by type is usually clear:

~~~java
public PricingService(ConversionService conversionService) {
    this.conversionService = conversionService;
}
~~~

If multiple beans share the same type, identify the right bean with `@Qualifier` or configure `@Primary` per the application contract. **The special name used for internal framework lookup does not automatically resolve every ambiguous injection case** in the application context.

## 4. Basic XML Configuration

Minimal example:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="conversionService"
          class="org.springframework.context.support.ConversionServiceFactoryBean"/>

</beans>
~~~

This configuration creates a conversion service with the default converters supplied by Spring. The application can inject the service into another bean:

~~~xml
<bean id="pricingService" class="example.PricingService">
    <constructor-arg ref="conversionService"/>
</bean>
~~~

Java:

~~~java
package example;

import org.springframework.core.convert.ConversionService;

public class PricingService {
    private final ConversionService conversionService;

    public PricingService(ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    public Integer parseQuantity(String raw) {
        return conversionService.convert(raw, Integer.class);
    }
}
~~~

This is a direct way for a business service to use the conversion service. Business code does not need to call the factory bean; the factory already finished creating the product during container initialization.

## 5. Registering Custom Converters via the converters Property

`ConversionServiceFactoryBean` allows adding custom converters through the `converters` property. Elements in the collection can implement:

- `Converter<S,T>`: a single source/target type pair.
- `ConverterFactory<S,R>`: one source type converting to multiple target types in the same family.
- `GenericConverter`: supports multiple type pairs and can use `TypeDescriptor` to read metadata.

Example of a custom converter converting `String` to an internal currency type:

~~~java
package example;

import java.math.BigDecimal;
import java.util.Currency;

public record Money(BigDecimal amount, Currency currency) {
}
~~~

~~~java
package example;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Locale;

import org.springframework.core.convert.converter.Converter;

public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Money input is required");
        }

        String[] parts = source.trim().split("\\\\s+");
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Expected amount and currency, for example: 125.50 USD");
        }

        BigDecimal amount = new BigDecimal(parts[0]);
        Currency currency =
                Currency.getInstance(parts[1].toUpperCase(Locale.ROOT));

        return new Money(amount, currency);
    }
}
~~~

Suppose the input is `"125.50 USD"`. The converter splits the numeric amount and currency code, constructing a `Money` record. Format errors or invalid currency codes are reported via exceptions; the conversion service surfaces conversion errors according to its mechanism.

XML registering the converter:

~~~xml
<bean id="conversionService"
      class="org.springframework.context.support.ConversionServiceFactoryBean">
    <property name="converters">
        <set>
            <bean class="example.StringToMoneyConverter"/>
        </set>
    </property>
</bean>
~~~

Spring instantiates the converter bean declared in the set and adds it to the conversion service. From there, code can call:

~~~java
Money money =
        conversionService.convert("125.50 USD", Money.class);
~~~

### Replacing or Supplementing Default Converters?

Declaring the `converters` property **adds custom converters to the service created by the factory**; it does not mean Spring's default converters are all wiped out. Custom converters participate in the same registry, and which converter is selected also depends on source/target types, metadata, and registered converters.

Do not register multiple competing converters for the exact same type pair expecting XML order to always pick the winner. If two converters have overlapping conversion capabilities, redesign their supported scopes to avoid ambiguity.

## 6. Complete Runnable Java 17+ Program with ApplicationContext

The program below demonstrates all three points: the `conversionService` bean name, the factory bean producing the product, and a custom converter registered via XML.

Project structure:

~~~text
conversion-service-factory-bean/
├── pom.xml
└── src
    └── main
        ├── java/example/Money.java
        ├── java/example/StringToMoneyConverter.java
        ├── java/example/PricingService.java
        ├── java/example/FactoryBeanDemo.java
        └── resources/conversion-context.xml
~~~

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>conversion-service-factory-bean</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>example.FactoryBeanDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Money.java

~~~java
package example;

import java.math.BigDecimal;
import java.util.Currency;

public record Money(BigDecimal amount, Currency currency) {
}
~~~

### 6.3. StringToMoneyConverter.java

~~~java
package example;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Locale;

import org.springframework.core.convert.converter.Converter;

public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Money input is required");
        }

        String[] parts = source.trim().split("\\\\s+");
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Expected: amount currency, for example 125.50 USD");
        }

        BigDecimal amount = new BigDecimal(parts[0]);
        Currency currency =
                Currency.getInstance(parts[1].toUpperCase(Locale.ROOT));

        return new Money(amount, currency);
    }
}
~~~

### 6.4. PricingService.java

~~~java
package example;

import org.springframework.core.convert.ConversionService;

public class PricingService {
    private final ConversionService conversionService;

    public PricingService(ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    public Money parse(String raw) {
        return conversionService.convert(raw, Money.class);
    }
}
~~~

### 6.5. conversion-context.xml

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="conversionService"
          class="org.springframework.context.support.ConversionServiceFactoryBean">
        <property name="converters">
            <set>
                <bean class="example.StringToMoneyConverter"/>
            </set>
        </property>
    </bean>

    <bean id="pricingService" class="example.PricingService">
        <constructor-arg ref="conversionService"/>
    </bean>

</beans>
~~~

### 6.6. FactoryBeanDemo.java

~~~java
package example;

import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.core.convert.ConversionService;

public class FactoryBeanDemo {

    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext(
                "conversion-context.xml")) {

            ConversionService service =
                    context.getBean("conversionService",
                            ConversionService.class);

            PricingService pricingService =
                    context.getBean(PricingService.class);

            Money direct =
                    service.convert("125.50 USD", Money.class);
            Money throughBean = pricingService.parse("20 EUR");

            Object factory =
                    context.getBean("&conversionService");

            System.out.println("isConversionService="
                    + (service instanceof ConversionService));
            System.out.println("direct="
                    + direct.amount().toPlainString() + " "
                    + direct.currency().getCurrencyCode());
            System.out.println("injected="
                    + throughBean.amount().toPlainString() + " "
                    + throughBean.currency().getCurrencyCode());
            System.out.println("factoryType="
                    + factory.getClass().getSimpleName());
        }
    }
}
~~~

### 6.7. Compile and Run

From the `conversion-service-factory-bean` root directory, JDK 17+ and Maven are required:

~~~bash
mvn -q compile exec:java
~~~

Expected stdout:

~~~text
isConversionService=true
direct=125.50 USD
injected=20 EUR
factoryType=ConversionServiceFactoryBean
~~~

Explanation:

1. `ClassPathXmlApplicationContext` reads `conversion-context.xml` and creates the application context.
2. The bean defined using `ConversionServiceFactoryBean` is named `conversionService`. When looking up the bean by type `ConversionService`, we receive the product supplied by the FactoryBean.
3. `StringToMoneyConverter` is placed into the `converters` set and registered into the conversion service.
4. `PricingService` is injected with the same service via its constructor and calls `convert(...)` just like direct lookup code.
5. `context.getBean("&conversionService")` returns the factory bean itself; hence the printed type name is `ConversionServiceFactoryBean`.

The sample output depends on the conversion steps of the declared converter. The program above is a small example with complete classes, XML, and dependencies; the Maven command uses `exec-maven-plugin` to assemble the classpath with Spring dependencies automatically without manually building the classpath.

## 7. The conversionService Bean Name in Spring MVC

Spring MVC also needs conversion/formatting for request parameters and model attributes. However, **conversion and formatting have a broader scope than a pure set of converters**: dates, locale-sensitive numbers, formatting annotations, and bidirectional formatters may participate.

Therefore, MVC documentation uses `FormattingConversionServiceFactoryBean` in classic XML configuration:

~~~xml
<mvc:annotation-driven conversion-service="conversionService"/>

<bean id="conversionService"
      class="org.springframework.format.support.FormattingConversionServiceFactoryBean">
    <property name="converters">
        <set>
            <bean class="example.StringToMoneyConverter"/>
        </set>
    </property>
</bean>
~~~

`FormattingConversionServiceFactoryBean` also creates a conversion service, but one that supports Spring's formatter/formatting system. In Java-based MVC configuration, the modern approach typically uses `WebMvcConfigurer.addFormatters`:

~~~java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToMoneyConverter());
    }
}
~~~

There is no need to define both configurations. Choose the single right registration mechanism per application context and avoid unnecessary duplicate registries.

| Requirement | Choice |
| --- | --- |
| Shared conversion service in Spring Core, mainly Converter/ConverterFactory/GenericConverter | `ConversionServiceFactoryBean` |
| Classic MVC configuration needing converters and formatters | `FormattingConversionServiceFactoryBean` |
| MVC Java configuration | `WebMvcConfigurer.addFormatters(FormatterRegistry)` |
| Application wants to invoke conversion directly in code | Inject `ConversionService` |
| Conversion needed only for one specific point | Consider a dedicated binder/service rather than a global registry |

The name `conversionService` is a useful convention in XML/Java container configurations. For MVC, explicit configuration via `conversion-service="conversionService"` or `addFormatters(...)` clarifies which registry is used. Do not confuse the bean used for core context property binding with every conversion step of every HTTP message converter.

## 8. Spring Boot and Java Configuration

In pure Java-configured applications:

~~~java
@Configuration
public class CoreConversionConfiguration {

    @Bean
    public ConversionService conversionService() {
        DefaultConversionService service =
                new DefaultConversionService();
        service.addConverter(new StringToMoneyConverter());
        return service;
    }
}
~~~

This directly declares a service via `@Bean`; **there is no need to wrap it in `ConversionServiceFactoryBean`** if you instantiate it directly. However, distinguish ordinary bean declaration from how Spring Framework or MVC discovers registries by specific name/contract.

In web MVC configuration:

~~~java
@Configuration
public class WebConversionConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToMoneyConverter());
    }
}
~~~

This registers the converter into the registry used by MVC. In Spring Boot, auto-configuration may manage the application conversion service and web conversion service according to that Boot version's rules. Prefer the extension points documented for your exact Boot version instead of adding a manual `ConversionServiceFactoryBean` alongside auto-configuration and creating two divergent conversion suites.

Before declaring a bean:

1. Check whether the application already has a `ConversionService` bean.
2. Determine whether the bean is for the core/application context or for MVC.
3. Determine whether `Formatter`/locale support is needed or just plain converters.
4. Pick a single extension point and test the actual bean/service used by the framework.

## 9. Lifecycle, Thread Safety, and ApplicationContext Scope

Spring describes `ConversionService` as an object that does not hold mutable state for a single conversion (stateless), created at application startup and shared across threads. Therefore:

- Do not create a new conversion service on every request.
- Converters should not hold per-user mutable state.
- Do not put database writes, API calls, or permission checks inside converters.
- Custom converters must behave consistently under concurrent invocation.
- When request/locale-dependent behavior is needed, use the formatter mechanism or pass appropriate context rather than storing the current locale in a mutable field of a singleton converter.

An `ApplicationContext` typically has its own conversion service. In applications with parent/child contexts, determine which context owns the `conversionService` bean used by the component. Do not assume declaring it in an arbitrary context automatically configures every child context; that depends on how the web application is initialized and configured.

### Does ConversionService Replace Validation?

No. Converters solve converting data between two types:

~~~text
"12" -> Integer.valueOf(12)
~~~

Validation checks data after it has been converted:

~~~text
quantity = 12 -> must quantity be greater than 0?
~~~

Business services check business conditions:

~~~text
valid quantity -> does inventory have enough stock?
~~~

The three layers have distinct responsibilities. A value that converts successfully can still be invalid or disallowed by business rules. In the DataBinder flow, inspect `BindingResult` and run validation before calling state-changing services.

## 10. Common Pitfalls When Configuring FactoryBean

**Pitfall 1 — Using an arbitrary bean name and expecting Spring to auto-select it.**

~~~xml
<bean id="myConversions"
      class="org.springframework.context.support.ConversionServiceFactoryBean"/>
~~~

This bean can still be injected, but it is not equivalent to the `conversionService` convention bean. If you need to register the context's shared conversion service, use the conventional name or the extension point required by the framework.

**Pitfall 2 — Confusing the factory bean with its product.**

~~~java
Object factory = context.getBean("conversionService");
~~~

Normal lookup returns the **product**. Only `context.getBean("&conversionService")` retrieves the factory bean. Do not inject `ConversionServiceFactoryBean` into services just to run conversions; services should depend on `ConversionService`.

**Pitfall 3 — Thinking the conversionService name auto-generates custom converters.**

The factory bean supplies Spring's default converter set plus converters you register via the `converters` property. Custom logic like `StringToMoneyConverter` still must be written and registered.

**Pitfall 4 — Registering a converter with the wrong generic types.**

A `String -> Money` converter cannot automatically handle `String -> Priority` unless another appropriate converter or factory exists. Define the exact source and target types for each converter.

**Pitfall 5 — Using ConversionServiceFactoryBean when formatting is actually needed.**

If MVC must parse/format dates or numbers by locale or support `Formatter`, look at `FormattingConversionServiceFactoryBean` or `WebMvcConfigurer.addFormatters`. A Converter performs one-way type conversion, whereas a Formatter typically handles both parsing and printing.

**Pitfall 6 — Creating two out-of-sync conversion services.**

If the core context has a `conversionService` bean while MVC has a separate registry, a converter might work when called directly yet not be used by MVC. Test the actual integration point and avoid duplicate configurations.

**Pitfall 7 — Assuming canConvert guarantees convert will succeed for every value.**

~~~java
conversionService.canConvert(String.class, Money.class)
~~~

The call above checks convertibility by type. It does not check whether a concrete string like `"abc"` is valid money. Only `convert(...)` with an actual value runs the converter.

**Pitfall 8 — Throwing unclear exceptions or silently returning null.**

Invalid input should produce an observable conversion error. Do not return `null` as a way to hide bad data when the contract does not allow it.

**Pitfall 9 — Forgetting dependencies and classpath.**

`ConversionServiceFactoryBean` belongs to Spring Framework; an application using XML contexts needs the proper dependencies, typically via `spring-context`. When running a Java main with Spring dependencies, the classpath must include all relevant JARs; supplying only `target/classes` will not suffice.

**Pitfall 10 — Conflating the Core API with Jackson.**

`ConversionService` does not replace Jackson JSON deserializers. A `@RequestBody` endpoint typically goes through HTTP message converters; a `@ModelAttribute` form uses WebDataBinder/ConversionService. Test the actual data path.

## 11. How to Test the Configuration

Configuration tests should verify three layers:

1. **Right bean name and right product:** `context.getBean("conversionService", ConversionService.class)` returns a conversion service.
2. **Custom converter is registered:** sample values actually convert to the expected target type.
3. **Injection works:** application beans receive the same conversion service and can invoke it.

JUnit 5 example (snippet requiring test dependencies and the XML context created earlier):

~~~java
@Test
void customConverterIsAvailableFromNamedService() {
    try (var context = new ClassPathXmlApplicationContext(
            "conversion-context.xml")) {

        ConversionService service =
                context.getBean("conversionService",
                        ConversionService.class);

        Money money =
                service.convert("125.50 USD", Money.class);

        assertEquals(new BigDecimal("125.50"), money.amount());
        assertEquals("USD", money.currency().getCurrencyCode());
    }
}
~~~

Useful additional test cases:

| Test | What to verify |
| --- | --- |
| Bean name | `conversionService` bean exists and can be retrieved as `ConversionService`. |
| Factory dereference | `&conversionService` returns the factory bean, not the product. |
| Built-in conversion | String to number/enum converts properly with the configured service. |
| Custom converter | String to Money works. |
| Invalid input | Invalid currency code produces a clear conversion error. |
| Injection | Business service receives ConversionService via constructor. |
| MVC integration | Form requests with target types needing conversion actually use the configured MVC registry. |
| Multiple contexts | Core/web contexts have appropriate services without duplicate conflicting configs. |

When testing errors, you can assert `ConversionException` or the specific exception for that call path. In `DataBinder`/MVC, conversion errors are usually recorded as `FieldError`s for user display rather than always propagating exceptions outward.

## 12. Implementation Workflow

1. Identify where in the application shared type conversion is needed.
2. Choose the right converter SPI: `Converter`, `ConverterFactory`, or `GenericConverter`.
3. If using an XML core context, declare `ConversionServiceFactoryBean` under bean name `conversionService`.
4. Register custom converters in the factory's `converters` property.
5. Inject the product as `ConversionService`, without depending directly on the factory bean.
6. If configuring Spring MVC and formatting is needed, consider `FormattingConversionServiceFactoryBean` or `WebMvcConfigurer.addFormatters`.
7. Start the context and verify the bean name, registered converters, and actual binding path.
8. Ensure converters are stateless/thread-safe; handle conversion errors before validation and business logic proceed.

**Remember:** `ConversionServiceFactoryBean` is the vehicle for configuring/creating a conversion service; `conversionService` is the conventional bean name for Spring to recognize the shared service; custom converters are the components added to that registry. Distinguishing these three parts clearly makes configuring, injecting, and testing type conversion much easier to control.

### Official Spring Documentation

- [Spring Framework — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework — ConversionServiceFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/ConversionServiceFactoryBean.html)
- [Spring Framework — ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework — ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
- [Spring MVC — Type Conversion and FormatterRegistry](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html)
- [Spring Framework — FormattingConversionServiceFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/support/FormattingConversionServiceFactoryBean.html)

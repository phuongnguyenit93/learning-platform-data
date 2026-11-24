# Custom Converters and Scope of Application in SpEL

## 1. Why Custom Converters Are Needed

Spring Expression Language (SpEL) can convert values between data types while evaluating expressions. Spring already supports many common conversions such as String to numbers, conversions between numeric types, and String to enum. Applications also frequently have custom business domain types such as Money, ProductCode, or Temperature with specific conversion rules.

A custom converter defines how to convert one source type into one target type. For example, the string "125.50" can be converted into a Money object so an expression can assign it to a property, pass it as a method argument, or return a specific result type.

SpEL uses a TypeConverter in the EvaluationContext to perform required conversions. StandardEvaluationContext uses StandardTypeConverter by default. StandardTypeConverter can work with Spring ConversionService, so converters can be registered in ConversionService and that service attached to the context used by expressions.

## 2. Distinguishing Converter, ConversionService, and TypeConverter

Three components have distinct responsibilities:

| Component | Role |
|---|---|
| Converter<S, T> | Defines how to convert a source type S into a target type T |
| ConversionService | Manages and locates the appropriate converter for a type pair |
| TypeConverter | The interface SpEL calls to convert values during expression evaluation |

A converter does not automatically take effect across every expression in the entire JVM. The converter must be registered in the active ConversionService, and that ConversionService must be wired into the evaluation context's TypeConverter or the Spring mechanism evaluating the expression.

In typical applications, use StandardTypeConverter as the adapter between SpEL and ConversionService. Only implement a custom TypeConverter when a special conversion policy is needed that ConversionService does not satisfy.

## 3. Creating a Business Domain Data Type

The example below uses the Money type as the target type. Money holds a BigDecimal value and exposes a getter so SpEL can read the property:

~~~java
import java.math.BigDecimal;

public class Money {
    private final BigDecimal amount;

    public Money(BigDecimal amount) {
        this.amount = amount;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    @Override
    public String toString() {
        return amount.toPlainString();
    }
}
~~~

An Invoice object with a Money property:

~~~java
public class Invoice {
    private Money amount;

    public Money getAmount() {
        return amount;
    }

    public void setAmount(Money amount) {
        this.amount = amount;
    }
}
~~~

The goal is to let an expression accept a String and assign it to the amount property of type Money. Java cannot assign a String directly to Money; a custom converter provides that conversion step.

## 4. Writing Converter<S, T>

Spring provides the Converter<S, T> interface for a conversion between two specific types:

~~~java
import java.math.BigDecimal;
import org.springframework.core.convert.converter.Converter;

public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        if (source == null) {
            return null;
        }

        String normalized = source.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Money value must not be empty");
        }

        return new Money(new BigDecimal(normalized));
    }
}
~~~

The converter receives a String and returns Money. String parsing uses BigDecimal to preserve decimal precision better than double.

A converter should focus on a single conversion with clear meaning. If input is invalid, raise an error with useful context instead of silently returning a default value that could mask invalid data.

If the source format has complex rules such as currency codes, thousand separators, or locale, define the format explicitly and test those cases. Avoid relying on the server's default locale when inputs require a stable format.

## 5. Registering a Converter in ConversionService

DefaultConversionService is a built-in implementation of ConversionService and ConverterRegistry. You can create a dedicated instance and register the converter:

~~~java
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(new StringToMoneyConverter());

boolean supported =
        conversionService.canConvert(String.class, Money.class);
~~~

After registration, ConversionService knows how to convert String to Money. You can check conversion capability using canConvert beforehand if the application needs to verify configuration.

Converters should be registered during application configuration, before expressions are evaluated. Avoid continuously mutating the converter list during request processing because that makes conversion behavior unpredictable and hard to test.

Do not arbitrarily add converters to a global shared ConversionService just to make one expression work. Using an explicitly managed instance limits where the converter applies and prevents unintended impact on other parts of the application.

## 6. Attaching ConversionService to StandardEvaluationContext

StandardEvaluationContext uses a TypeConverter to perform conversions. You can attach a StandardTypeConverter created from the configured ConversionService:

~~~java
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
import org.springframework.expression.spel.support.StandardTypeConverter;
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService conversionService =
        new DefaultConversionService();
conversionService.addConverter(new StringToMoneyConverter());

Invoice invoice = new Invoice();

StandardEvaluationContext context =
        new StandardEvaluationContext(invoice);
context.setTypeConverter(new StandardTypeConverter(conversionService));

ExpressionParser parser = new SpelExpressionParser();
parser.parseExpression("amount").setValue(context, "125.50");

Money amount = parser.parseExpression("amount")
        .getValue(context, Money.class);

System.out.println(amount); // 125.50
~~~

When calling setValue, SpEL needs to assign a String to the amount property of type Money. The context's TypeConverter asks ConversionService to convert the value before calling the setter.

The parser does not own the converter. The same parser can evaluate expressions across multiple contexts with different conversion policies. Which converter is used depends on the TypeConverter of the context passed to that evaluation.

## 7. Converters Can Also Apply to Method Arguments

SpEL can convert arguments when calling methods on the root object or an object referenced from the context. If a method expects Money while the expression passes a String literal, a custom converter can supply the target type:

~~~java
public class PriceFormatter {
    public String describe(Money money) {
        return "Amount: " + money.getAmount().toPlainString();
    }
}
~~~

Registering the formatter in the context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("formatter", new PriceFormatter());
context.setTypeConverter(new StandardTypeConverter(conversionService));

Expression expression = parser.parseExpression(
        "#formatter.describe('42.75')");

String description = expression.getValue(context, String.class);

System.out.println(description); // Amount: 42.75
~~~

The describe method accepts Money. The expression supplies a String, so SpEL uses the context's TypeConverter to convert the argument to the type required by the method if that conversion is supported.

This mechanism is useful when expressions invoke methods taking business domain parameters. The method should still maintain a clear contract and avoid unexpected side effects when invoked inside an expression.

## 8. Converting Expression Result Types

The getValue(context, TargetType.class) overload allows requesting a specific result type. If the expression's value does not have the exact target type yet can be converted, the context's TypeConverter can perform the conversion:

~~~java
Expression expression = parser.parseExpression("'125.50'");

Money amount = expression.getValue(context, Money.class);
~~~

In this example, the expression returns a String; SpEL is asked to return Money. This succeeds only when the context's TypeConverter has a String-to-Money converter.

You can check ConversionService directly beforehand:

~~~java
assertTrue(conversionService.canConvert(String.class, Money.class));
~~~

The expected result type should reflect the contract of the code invoking the expression. If an expression sometimes returns String and sometimes Money depending on a branch, make the result type and conversion capabilities explicit instead of letting implicit conversion create unpredictable behavior.

## 9. GenericConverter for Multiple Source and Target Types

Converter<S, T> fits a single concrete type pair. When handling multiple type pairs or needing generic/annotation information from a property, GenericConverter can be used.

GenericConverter provides a set of ConvertiblePairs and receives TypeDescriptors for both source and target:

~~~java
public final class StringToMoneyGenericConverter
        implements GenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Collections.singleton(
                new ConvertiblePair(String.class, Money.class));
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {

        if (source == null) {
            return null;
        }

        return new Money(new BigDecimal(source.toString().trim()));
    }
}
~~~

TypeDescriptor carries additional information about the property's type and metadata, including generic types and annotations. This is useful when the converter needs to know the target is a specific property or a collection type with explicitly declared elements.

For a simple String-to-Money conversion, Converter<S, T> is usually shorter and easier to read. Choose GenericConverter only when additional type information or multiple conversion pairs are genuinely needed.

## 10. ConditionalGenericConverter and Applicability Conditions

ConditionalGenericConverter allows a converter to be selected only when a condition matches. For example, the same source/target types might convert differently depending on an annotation on the target property.

~~~java
public final class AnnotatedMoneyConverter
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Collections.singleton(
                new ConvertiblePair(String.class, Money.class));
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return targetType.hasAnnotation(SpecialMoneyFormat.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return parseSpecialMoney(source.toString());
    }
}
~~~

This is an illustrative structure: the application must define the annotation, parse function, and corresponding error handling policy. matches decides whether the converter applies to the current pair of TypeDescriptors.

Conditional converters are useful when applicability depends on metadata. If different formats carry distinct meanings, separate the converters or name the condition very clearly.

## 11. ConverterFactory for a Family of Target Types

If one source type can convert to multiple target types belonging to the same family, Spring provides ConverterFactory<S, R>. A typical example is converting String to different enums.

~~~java
public class StringToEnumConverterFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {

        return source -> Enum.valueOf(targetType, source.trim());
    }
}
~~~

You can register the factory in ConversionService:

~~~java
conversionService.addConverterFactory(
        new StringToEnumConverterFactory());
~~~

Spring selects the concrete converter based on the target enum type. A factory fits when conversion logic is shared across a type family; if there is only one specific target type, Converter<S, T> is simpler.

For enum inputs that do not match a constant name, the converter must define how case, aliases, and invalid values are handled. Do not guess constants automatically when doing so could alter the meaning of the data.

## 12. Scope of Application Across EvaluationContexts

A converter only takes effect within the scope of the ConversionService attached to the TypeConverter of the active evaluation context.

| Where Expression Is Evaluated | Converter Used |
|---|---|
| Self-created StandardEvaluationContext | TypeConverter attached via setTypeConverter |
| Multiple StandardEvaluationContexts sharing one ConversionService | Converters in the shared ConversionService instance |
| SimpleEvaluationContext | ConversionService configured in the builder |
| Expression evaluated by Spring BeanFactory | ConversionService used by the BeanFactory expression resolver |
| Another independently created SpEL context | Conversion policy of that independent context |

Example of two contexts with different policies:

~~~java
StandardEvaluationContext moneyContext =
        new StandardEvaluationContext(invoice);
moneyContext.setTypeConverter(
        new StandardTypeConverter(moneyConversionService));

StandardEvaluationContext defaultContext =
        new StandardEvaluationContext(invoice);
~~~

Expressions running with moneyContext can use the custom String-to-Money converter. Expressions running with defaultContext use only that context's default TypeConverter. Registering a converter in one ConversionService does not automatically affect contexts already created with another ConversionService.

If multiple contexts need the same rules, create a shared ConversionService, configure it completely, and attach it to each relevant context. Sharing the same instance must be an explicit configuration decision, not an assumption that every parser or context automatically picks up the converter.

## 13. Scope in Spring Applications Managed by BeanFactory

In a Spring application, the bean factory can be configured with a ConversionService. By Spring convention, a ConversionService bean named conversionService can be used by BeanFactory for container conversions. StandardBeanExpressionResolver also uses the BeanFactory's ConversionService when creating evaluation contexts for expressions in bean definitions.

You can declare a ConversionService containing custom converters:

~~~java
@Configuration
public class ConversionConfiguration {

    @Bean
    public ConversionService conversionService() {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(new StringToMoneyConverter());

        return service;
    }
}
~~~

When using bean factory expression evaluation, this registration allows expressions evaluated by the BeanFactory resolver to use the configured ConversionService. Exact behavior should be verified with integration tests against the application's actual Spring configuration, especially when multiple ApplicationContexts or multiple ConversionServices exist.

A manually instantiated StandardEvaluationContext in code still needs the corresponding TypeConverter attached. Do not assume that merely having a ConversionService bean in the application causes every manually created context to use that bean automatically.

## 14. Distinguishing from Spring MVC FormatterRegistry

Spring MVC has its own mechanism for registering converters and formatters through FormatterRegistry, such as in WebMvcConfigurer.addFormatters. Converters registered in MVC typically serve data binding and data conversion within the MVC scope.

~~~java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToMoneyConverter());
    }
}
~~~

Do not assume by default that a converter added to the MVC FormatterRegistry will appear in every StandardEvaluationContext or every expression resolver. Actual scope depends on the ConversionService instances used by MVC and BeanFactory.

If the same converter is needed for both MVC and SpEL, structure configuration so both mechanisms share the appropriate ConversionService, or register the converter in each respective registry. Then write integration tests for both the MVC data binding flow and the SpEL flow to confirm configuration is actually shared as intended.

## 15. SimpleEvaluationContext and Conversion Service

SimpleEvaluationContext is a more restricted choice when expressions only need data binding or property access within an allowed scope. Its builder supports configuring a ConversionService:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

If writing properties is needed, choose the appropriate read/write builder:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

ConversionService here remains the source of conversion rules for the context created by the builder. SimpleEvaluationContext's restrictions on property access, method resolution, and type access still apply; adding a converter does not automatically expand other expression permissions.

Choose the context according to the capabilities expressions truly need. If only reading/writing properties and type conversion are needed, SimpleEvaluationContext may be more appropriate than a StandardEvaluationContext with broader capabilities than necessary.

## 16. Null, Invalid Data, and Conversion Errors

A converter should clearly define how it handles null input, empty strings, and malformed data. These are three distinct cases:

- Null may be handled by the conversion mechanism before the converter is invoked, depending on the conversion path.
- An empty string is a String of length 0; the converter must decide whether to accept it or throw an error.
- An invalid string, such as abc when BigDecimal is expected, should produce an error with a clear cause.

The Money converter example above rejects empty strings, and BigDecimal rejects invalid numeric data. When an error occurs during evaluation, SpEL may wrap the conversion error in an exception under the evaluation hierarchy. Inspect the cause to locate the converter or input data that failed.

If business logic requires a default value for null, express it explicitly in the expression or Java rather than letting the converter silently turn every invalid input into zero. For example:

~~~text
#amountText ?: '0.00'
~~~

Then let the converter process valid strings. Separating defaulting from conversion keeps each responsibility clear and easy to test.

## 17. Testing Custom Converters and Scope of Application

You should test the converter independently, the ConversionService after registration, and the expression context using that service.

Testing the converter:

~~~java
@Test
void convertsStringToMoney() {
    StringToMoneyConverter converter =
            new StringToMoneyConverter();

    Money result = converter.convert("125.50");

    assertEquals(
            new BigDecimal("125.50"),
            result.getAmount());
}
~~~

Testing ConversionService:

~~~java
@Test
void conversionServiceKnowsCustomMoneyConverter() {
    DefaultConversionService service =
            new DefaultConversionService();

    service.addConverter(new StringToMoneyConverter());

    assertTrue(service.canConvert(String.class, Money.class));

    Money result = service.convert("42.75", Money.class);

    assertEquals(new BigDecimal("42.75"), result.getAmount());
}
~~~

Testing SpEL context:

~~~java
@Test
void spelUsesCustomConverterWhenSettingRootProperty() {
    DefaultConversionService service =
            new DefaultConversionService();
    service.addConverter(new StringToMoneyConverter());

    Invoice invoice = new Invoice();

    StandardEvaluationContext context =
            new StandardEvaluationContext(invoice);
    context.setTypeConverter(new StandardTypeConverter(service));

    ExpressionParser parser = new SpelExpressionParser();
    parser.parseExpression("amount").setValue(context, "42.75");

    assertEquals(
            new BigDecimal("42.75"),
            invoice.getAmount().getAmount());
}
~~~

In addition to success cases, test empty strings, malformed data, null, and a context without the custom TypeConverter attached. That last test confirms the converter appears only within the configured scope.

If the converter is used via BeanFactory or Spring MVC, add integration tests for those specific mechanisms. Unit testing a manually created StandardEvaluationContext does not prove that MVC or BeanFactory configuration received the same ConversionService.

## 18. Common Pitfalls

**Writing a Converter but forgetting to register it**

SpEL does not auto-discover converters. Add it to ConversionService and ensure the context uses a TypeConverter connected to that service.

**Registering in the wrong ConversionService**

A converter added to the MVC registry or one context's service does not necessarily apply to another context. Verify the exact instance used by the expression resolver.

**Confusing the parser with the evaluation context**

The parser creates an Expression from source. Conversion behavior belongs to the context's TypeConverter during evaluate or setValue.

**Using an overly broad converter**

A converter applying to many types can alter behavior across many parts of the application. Restrict source/target types and use ConditionalGenericConverter when metadata-based conditions are truly required.

**Using a converter to mask bad data**

Returning default values for invalid data can make business errors hard to detect. Distinguish null, empty strings, and malformed data.

**Assuming MVC converters automatically apply to SpEL**

MVC FormatterRegistry and SpEL EvaluationContext may use different ConversionServices. Sharing a service must be explicitly configured and tested in each flow.

**Mutating the registry while the application is running**

Registering converters during configuration keeps behavior stable. Avoid dynamically changing converters while processing expressions unless there is a clear synchronization design.

## 19. When to Use Which Kind of Converter?

| Need | Choice |
|---|---|
| One explicit source/target type pair | Converter<S, T> |
| A family of target types sharing one rule | ConverterFactory<S, R> |
| Multiple type pairs or requiring TypeDescriptor | GenericConverter |
| Apply only when metadata/annotations match a condition | ConditionalGenericConverter |
| Conversion with formatting and locale | Formatter in FormattingConversionService |
| Conversion rule depending on complex business context | Explicitly named Java method/service |

Choose the smallest abstraction that meets the requirement. A simple converter is easier to read, test, and scope than an unnecessarily general GenericConverter.

## 20. Key Takeaways

- Custom converters define conversions between a source type and a target type.
- SpEL calls the EvaluationContext's TypeConverter when values need conversion.
- StandardTypeConverter is the adapter for using Spring ConversionService with SpEL.
- Register converters in the exact ConversionService used by the active context or expression resolver.
- A manually created StandardEvaluationContext needs StandardTypeConverter attached; the parser does not own converters.
- Converters can participate during setValue, method arguments, or requested result types.
- BeanFactory expression evaluation and MVC data binding may use ConversionServices with their own configuration scopes.
- SimpleEvaluationContext can accept a ConversionService via its builder.
- Use Converter for one type pair, ConverterFactory for a type family, GenericConverter when TypeDescriptor is needed, and ConditionalGenericConverter when applicability conditions are needed.
- Test the converter, service, expression context, and each integration scope separately.

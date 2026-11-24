# SpEL in XML Bean Definitions

## Objectives

Spring Expression Language (SpEL) can be used inside XML bean definition values. When a value starts with the **#{** delimiter and ends with **}**, Spring evaluates the inner part as an expression and uses the result to configure a property, constructor argument, or collection element during bean creation.

This approach is useful when configuration requires a calculation, reading a system property, referencing another bean, or combining multiple values without writing a separate bean factory. However, it is important to distinguish SpEL expressions from property placeholders, understand when expressions are evaluated, and follow XML escaping rules.

After this lesson, you can:

- Use #{...} in XML bean definitions.
- Place SpEL expressions in property values and constructor arguments.
- Reference system properties, static members, and Spring beans.
- Use expressions in lists, sets, maps, and nested values.
- Distinguish SpEL expressions from property placeholders.
- Escape special characters according to XML syntax.
- Understand when an expression is evaluated in the bean lifecycle.
- Diagnose parsing, bean resolution, conversion, and XML parsing errors.

## 1. SpEL Syntax in XML

In an XML bean definition, a SpEL expression is typically placed within the **#{** and **}** delimiters:

~~~xml
<bean id="welcomeMessage" class="com.example.WelcomeMessage">
    <property name="text" value="#{'Hello from SpEL'}"/>
</bean>
~~~

Spring detects strings with expression delimiters in bean definition values, evaluates the SpEL part, and assigns the result to the text property.

An example using a system property:

~~~xml
<bean id="applicationRegion" class="com.example.RegionSettings">
    <property name="region"
              value="#{systemProperties['user.region']}"/>
</bean>
~~~

The expression reads the user.region entry from system properties. The result is converted to the property type if a suitable conversion is configured.

Not every XML string automatically becomes SpEL. The text to be evaluated must use the expression delimiter and be processed by Spring inside an ApplicationContext that has a bean expression resolver.

## 2. Using Expressions in Property Values

One of the most common uses is computing a property value when a bean is created.

~~~xml
<bean id="pricingSettings" class="com.example.PricingSettings">
    <property name="maximumPrice"
              value="#{T(java.math.BigDecimal).valueOf(500)}"/>
    <property name="defaultCurrency"
              value="#{T(java.util.Currency).getInstance('USD')}"/>
</bean>
~~~

The first expression calls the static method valueOf of BigDecimal. The second expression retrieves the Currency corresponding to the USD code.

You can reference a property or method of another bean:

~~~xml
<bean id="checkoutSettings" class="com.example.CheckoutSettings">
    <property name="taxRate"
              value="#{@taxPolicy.currentRate}"/>
</bean>
~~~

Here, @taxPolicy references the bean named taxPolicy. The expression reads the currentRate property on that bean and assigns the result to taxRate.

If you only need to inject a bean directly into a property of a compatible type, the ref attribute is usually simpler and clearer:

~~~xml
<property name="taxPolicy" ref="taxPolicy"/>
~~~

Use SpEL when you need to extract a value, perform a calculation, or combine a bean with other data. Use ref when the goal is simply direct bean injection.

## 3. Using Expressions in Constructor Arguments

SpEL can also supply values for constructor arguments:

~~~xml
<bean id="retryPolicy" class="com.example.RetryPolicy">
    <constructor-arg value="#{3 * 2}"/>
    <constructor-arg value="#{T(java.time.Duration).ofSeconds(30)}"/>
</bean>
~~~

This example passes the calculation result 6 and a 30-second Duration to the corresponding constructor.

You can reference a bean in a constructor argument:

~~~xml
<bean id="reportService" class="com.example.ReportService">
    <constructor-arg value="#{@reportSettings.outputDirectory}"/>
</bean>
~~~

Spring evaluates the expression value while resolving bean definitions and uses the result as the argument. The target type of the constructor parameter and the conversion service affect how the result is converted to the required type.

If there are multiple overloaded constructors, make sure the number and types of arguments are clear enough for Spring to choose the right constructor. For complex configurations, you can use constructor-arg index or type to clarify the mapping, and test context startup.

## 4. Referencing Beans with @beanName

In SpEL, the **@** symbol is used to reference a bean by name:

~~~text
@taxPolicy
@systemClock
@featureSettings.enabled
~~~

Example:

~~~xml
<bean id="invoiceSettings" class="com.example.InvoiceSettings">
    <property name="taxPolicy" value="#{@taxPolicy}"/>
    <property name="taxRate" value="#{@taxPolicy.currentRate}"/>
</bean>
~~~

The first expression returns the taxPolicy bean. The second expression reads currentRate from that bean.

A bean reference in an expression requires a bean expression context with an appropriate BeanResolver. In a Spring ApplicationContext, bean definition evaluation is integrated with the bean factory to resolve bean references.

Distinguish between:

- ref="taxPolicy" is the direct XML dependency reference mechanism.
- value="#{@taxPolicy}" is a SpEL expression that returns the taxPolicy bean.
- value="#{@taxPolicy.currentRate}" is a SpEL expression that accesses a property of the bean.

Do not use a bean reference via SpEL merely to replace a simple ref. Expressions are useful when you need to combine a bean with a calculation or extract part of a bean's value.

## 5. Using Static Type References in XML

SpEL allows using **T(...)** to reference a Java class, enabling access to static fields, enum constants, or static methods.

~~~xml
<bean id="mathSettings" class="com.example.MathSettings">
    <property name="pi" value="#{T(java.lang.Math).PI}"/>
    <property name="maxInteger" value="#{T(java.lang.Integer).MAX_VALUE}"/>
</bean>
~~~

Enum constants can be used:

~~~xml
<bean id="jobSettings" class="com.example.JobSettings">
    <property name="roundingMode"
              value="#{T(java.math.RoundingMode).HALF_UP}"/>
</bean>
~~~

Or static methods can be called:

~~~xml
<property name="defaultDate"
          value="#{T(java.time.LocalDate).of(2026, 11, 12)}"/>
~~~

For classes outside java.lang, use the fully qualified package name to avoid relying on TypeLocator import prefixes. A type reference only resolves the class; the class must be on the runtime classpath and the context must support type resolution.

## 6. Expressions in Collections and Maps

SpEL can be used inside child values of collections in XML bean definitions.

List example:

~~~xml
<bean id="notificationSettings"
      class="com.example.NotificationSettings">
    <property name="channels">
        <list>
            <value>EMAIL</value>
            <value>SMS</value>
            <value>#{@featureSettings.defaultChannel}</value>
        </list>
    </property>
</bean>
~~~

Map example:

~~~xml
<bean id="thresholdSettings"
      class="com.example.ThresholdSettings">
    <property name="thresholds">
        <map>
            <entry key="standard" value="#{100 * 2}"/>
            <entry key="premium"
                   value="#{@pricingPolicy.premiumThreshold}"/>
        </map>
    </property>
</bean>
~~~

Expressions can provide either the key or the value if the target type and XML structure allow:

~~~xml
<entry key="#{@regionSettings.code}"
       value="#{@regionSettings.displayName}"/>
~~~

When using collections, determine the expected element type and key/value types. Spring can perform conversion for elements when needed, but invalid data or a missing converter can still cause bean creation to fail.

With nested collections, expressions are evaluated at each position whose value is resolved by Spring. If the configuration becomes long or involves many calculations, consider creating a Java configuration bean with clearly named properties.

## 7. Distinguishing SpEL #{...} from Property Placeholders

Spring XML commonly has two mechanisms that are easily confused:

| Syntax | Purpose | Example |
|---|---|---|
| PLACEHOLDER | Retrieve a value from a property source or placeholder configurer | service.timeout |
| SPEL | Evaluate a SpEL expression | 30 * 2 |

Property placeholders typically retrieve configuration values from properties files, the environment, or registered configuration sources. SpEL performs calculations, accesses objects, calls methods, or combines data within an expression.

Example using a placeholder:

~~~xml
<property name="timeout" value="${service.timeout}"/>
~~~

Example using SpEL:

~~~xml
<property name="timeout" value="#{30 * 2}"/>
~~~

If the application has placeholder resolution configured, a configuration value can be used as input to an expression:

~~~xml
<property name="timeout"
          value="#{${service.timeout:30} * 2}"/>
~~~

In this example, the placeholder supplies the configuration value or default 30; then SpEL multiplies the substituted value by 2. This combination should be tested with the exact PropertySourcesPlaceholderConfigurer or placeholder mechanism used by the application.

Do not mechanically replace placeholders with SpEL. If you only need to read a configuration property, a placeholder is usually more appropriate. Use SpEL when you need an expression or object access.

## 8. Escaping Special Characters in XML

A SpEL expression placed inside XML must still obey XML syntax. The XML parser processes characters before Spring evaluates the expression.

Some characters to watch out for:

| Character needed in expression | Written in XML |
|---|---|
| < | &lt; |
| & | &amp; |
| > | Can be written as &gt; for clarity |
| " inside a double-quoted attribute | &quot; |
| ' inside a single-quoted attribute | &apos; |

Example of a less-than comparison inside a value attribute:

~~~xml
<property name="eligible"
          value="#{#root.score &lt; 80}"/>
~~~

After the XML parser decodes the entity, SpEL receives the expression with the less-than operator.

Example using AND:

~~~xml
<property name="eligible"
          value="#{#root.active and #root.score &gt;= 80}"/>
~~~

Using the `and` keyword helps avoid writing a double ampersand operator in XML. If you need to use `&&`, it must be written as `&amp;&amp;` in the XML document so the XML parser reconstructs `&&` before SpEL processes it.

For string literals inside a double-quoted XML attribute, use SpEL's single quotes:

~~~xml
<property name="label" value="#{'Ready'}"/>
~~~

If a literal value needs to contain double quotes, you can use the appropriate XML entity or switch to an XML element with text content. Always distinguish the XML escaping layer from SpEL's string literal syntax.

## 9. XML Element Content and CDATA

An expression can appear in an XML attribute or in an element's text content, depending on the bean definition structure. XML still applies the corresponding escaping rules.

Example of a value inside an element:

~~~xml
<property name="description">
    <value>#{'A &amp; B'}</value>
</property>
~~~

The XML parser converts &amp; into an ampersand character before Spring processes the value.

CDATA can preserve certain XML characters as literal text without writing entities, but you should not assume CDATA changes SpEL syntax or disables expression evaluation. Spring still receives the string value after the XML parser processes the document and can evaluate expression delimiters within that string.

For XML with many special characters, choose a representation that is easy to read and testable. Avoid mixing multiple layers of escaping without verifying the actual string Spring receives.

## 10. When Are Expressions Evaluated?

SpEL in bean definitions is evaluated when Spring resolves bean definition values during bean creation. Therefore, an expression is not necessarily evaluated every time the application calls a method on the bean.

For a singleton bean, the expression value is typically resolved when the bean is created and kept in the singleton instance. For a prototype bean, repeated bean creation can cause the expression value to be re-evaluated each time an instance is created.

For example, if a singleton property is configured with:

~~~xml
<property name="startupTime"
          value="#{T(java.time.Instant).now()}"/>
~~~

the value is assigned when the bean is created. It does not automatically update on every property read.

If an expression references another bean or a mutable object, the referenced bean may change state later; however, a scalar value already computed and assigned to the property is not automatically recomputed just because the source changes.

If you need a dynamic value computed on each use, call a bean method in Java instead of relying on an expression resolved at bean initialization time.

## 11. Configuring the Bean Expression Resolver

Spring's ApplicationContext normally configures a bean expression resolver by default for bean definition values. When using a manually created BeanFactory or a custom configuration, ensure a bean expression resolver is registered if you want `#{...}` to be evaluated.

The bean expression resolver provides the evaluation context for expressions in bean definitions, including access to the bean factory and environment variables supplied by the integration.

If an expression in XML is not evaluated and is instead assigned literally as the string `#{...}` to the property, check:

- Whether the application uses an appropriate ApplicationContext.
- Whether a BeanExpressionResolver is configured.
- Whether the value actually goes through the bean definition string resolution mechanism.
- Whether the XML is loaded by a Spring container or only read as a plain XML document.
- Whether a custom configuration replaces the default resolver.

Do not create a standalone EvaluationContext and expect XML bean definitions to use that context automatically. The bean factory's expression resolver is the component that processes expressions during bean creation.

## 12. Common Errors and Diagnosis

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Value #{...} is kept literally as text | Bean expression resolver is not applied | Check the ApplicationContext and resolver |
| XML fails to parse | Characters <, &, or quotes are not escaped | Fix the XML entity or attribute structure |
| Expression parsing fails | Invalid SpEL syntax or unbalanced delimiters | Inspect the content inside #{...} |
| Bean not found | Wrong bean name or bean is not registered | Check the bean definition and @beanName reference |
| Class not found | Wrong fully qualified name or missing dependency | Check the runtime classpath and TypeLocator |
| Constructor/property rejects result type | Incompatible conversion | Check the target type and ConversionService |
| Placeholder is not substituted | Placeholder configurer or property source is not configured | Check placeholder resolution separately from SpEL |
| Expression returns a stale value | Value is computed at bean creation, not on every read | Check the bean scope and creation timing |
| Bean initialization fails | Expression throws an error while resolving property/constructor value | Read the cause chain and inspect the expression and data |

When diagnosing, separate errors by layer:

1. XML parsing.
2. Property placeholder resolution.
3. SpEL parsing.
4. Bean/type resolution.
5. Evaluation and conversion.
6. Bean instantiation or property assignment.

This separation helps identify whether the error belongs to XML, Spring configuration, or the expression instead of changing multiple parts at once.

## 13. Testing SpEL in XML Bean Definitions

You should test by loading the actual XML configuration in an ApplicationContext test. This verifies XML parsing, placeholder processing, SpEL evaluation, and bean creation together.

Example:

~~~java
@Test
void evaluatesSpelInXmlBeanDefinition() {
    try (ClassPathXmlApplicationContext context =
            new ClassPathXmlApplicationContext(
                "spel-beans.xml")) {

        PricingSettings settings =
            context.getBean("pricingSettings", PricingSettings.class);

        assertEquals(
            BigDecimal.valueOf(500),
            settings.getMaximumPrice()
        );
    }
}
~~~

Beyond testing that the bean is created successfully, you should check:

- A property value from a simple expression.
- A constructor argument computed by an expression.
- Bean references and property access via @beanName.
- Static fields, enum constants, and static methods.
- Collection entries containing expressions.
- XML entities for <, &, and quotes.
- Standalone placeholders and placeholders combined with SpEL.
- Errors when a bean or class does not exist.
- Conversion errors when the result type is incompatible.
- When expressions are evaluated for singleton vs. prototype if that affects business behavior.

If using XML namespaces or a placeholder configurer, the test must load the same namespace configuration and property sources as production. Simply parsing an expression with SpelExpressionParser is not enough to verify the full XML bean definition path.

## 14. Best Practices

- Use #{...} when you need SpEL in a bean definition value.
- Use ref for direct dependency injection; use @beanName when an expression needs to reference a bean as part of a calculation.
- Use placeholders for configuration properties and #{...} for SpEL.
- Use fully qualified class names in type references when clarity is needed.
- Keep expressions short, readable, and free of multi-step business logic.
- Escape XML characters before Spring receives the expression.
- Use `and`/`or` when you want to avoid double ampersands in XML.
- Do not assume an expression is recomputed on every property read.
- Check the bean scope and creation timing when an expression depends on changing data.
- Use ApplicationContext tests to verify that XML, placeholders, SpEL, and bean creation work together.
- Do not put untrusted expressions into bean definitions with broad access.
- Move dynamic or complex logic to a testable Java service/method.

## 15. Review Checklist

Before using SpEL in XML bean definitions, check:

- [ ] The expression uses the correct #{...} delimiter.
- [ ] The XML parses validly before Spring processes it.
- [ ] Characters <, &, and quotes are escaped at the proper layer.
- [ ] Property values and constructor arguments have compatible result types.
- [ ] Bean references use the correct name and the beans are registered.
- [ ] Type references use the correct classes available on the runtime classpath.
- [ ] Collection keys/values have the expected types and conversions.
- [ ] Placeholders are distinguished from SpEL.
- [ ] Placeholder configurer and property sources are configured if needed.
- [ ] A bean expression resolver is applied.
- [ ] Expression evaluation timing matches the bean's scope.
- [ ] An integration test loads the XML via ApplicationContext.

## Conclusion

SpEL in XML bean definitions uses the **#{...}** delimiter to evaluate expressions and supply results to properties, constructor arguments, or collection values when Spring creates beans. Expressions can read system properties, call static members, and reference beans via @beanName. Distinguish SpEL from property placeholders, escape characters according to XML rules, and remember that values are typically computed during bean creation rather than automatically updated on every read. Test by loading the XML in an ApplicationContext to verify the entire parsing, resolution, conversion, and bean creation pipeline.
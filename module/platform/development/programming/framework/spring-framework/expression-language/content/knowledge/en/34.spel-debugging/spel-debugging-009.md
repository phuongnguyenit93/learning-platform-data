# Diagnosing differences between test and runtime environments

A Spring Expression Language (SpEL) expression may run properly in unit tests yet fail in the live application. There are also cases where tests return one result while runtime produces another even though the expression source has not changed.

The cause usually does not lie in SpEL syntax alone. Evaluation results depend on many components: the parser and parser configuration, EvaluationContext, root object, variables, property accessors, method resolvers, bean resolvers, TypeConverter, actual data, profiles, classpath, and evaluation timing.

To diagnose accurately, you need to compare all execution conditions of the expression between the two environments. Do not merely copy the expression source from runtime into a test and assume both places are running the same configuration.

## 1. Understanding why test and runtime can differ

### 1.1. The same expression does not guarantee the same result

Example:

~~~java
Expression expression =
        parser.parseExpression("customer.active && total >= #minimum");
~~~

In a test, the root object might be a simple DTO:

~~~java
OrderView order = new OrderView(true, new BigDecimal("150"));
context.setVariable("minimum", new BigDecimal("100"));
~~~

At runtime, the root object might be an ORM-managed entity, a proxy, a DTO mapped from a request, or an object containing null properties. The minimum variable might also come from another environment's configuration.

The same expression string can yield different results because:

- Properties have different values or are null.
- Runtime types of properties differ.
- Getters execute different logic.
- Collections are empty or ordered differently.
- Context variables are missing or have different types.
- Accessors or resolvers are registered differently.
- ConversionService differs.
- Referenced beans have different configurations or state.
- The parser uses a different configuration.
- The expression is evaluated at a different time or on a different thread.

Therefore, when comparing test and runtime, record the source along with context and data rather than comparing only the final outcome.

### 1.2. Separating execution phases

A typical SpEL flow can be broken into phases:

1. Receive the expression source or template.
2. Parse the source using ExpressionParser and ParserContext.
3. Create or retrieve the parsed Expression.
4. Prepare EvaluationContext, root object, and variables.
5. Evaluate the expression.
6. Convert the result or use it in business logic.

Errors at each phase have different causes:

| Phase | Common difference | Symptom |
|---|---|---|
| Source | Test uses a different string than runtime | Different AST or parse message |
| Parse | Different parser configuration or parser context | ParseException or different expression structure |
| Context | Different accessor, resolver, converter | Property/method/bean not resolved |
| Input | Different root object or variables | Different Boolean result or value |
| Evaluate | Different getter, method, proxy, or backend | EvaluationException or business error |
| Result | Different target type or converter | ConversionException or cast error |

Identify the first phase where the two environments diverge. This narrows the investigation scope and avoids altering the expression when the cause lies in configuration or data.

## 2. Comparing expression source and parser

### 2.1. Record the exact parsed source

If the expression is loaded from configuration, a database, or a request, tests may be using a hardcoded literal while runtime uses a loaded or dynamically assembled value.

Keep the source before parsing:

~~~java
String source = rule.getExpression();

Expression expression = parser.parseExpression(source);
~~~

When diagnostics are needed, record:

- Rule ID or name.
- Rule/configuration version.
- Source length.
- Hash of the source.
- Redacted source if logging is permitted.
- ParserContext if using a template.

Do not record only a generic rule name. A rule may have been updated in the database or cache while test fixtures still use an older version.

### 2.2. Parse separately before evaluating

Separating parsing from evaluation helps determine whether the error is syntactic or runtime:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
} catch (SpelParseException ex) {
    logger.error(
            "Cannot parse ruleId={}, position={}, code={}",
            ruleId,
            ex.getPosition(),
            ex.getMessageCode(),
            ex
    );
    throw ex;
}

try {
    Object result = expression.getValue(context);
    return result;
} catch (SpelEvaluationException ex) {
    logger.error(
            "Cannot evaluate ruleId={}, position={}, code={}",
            ruleId,
            ex.getPosition(),
            ex.getMessageCode(),
            ex
    );
    throw ex;
}
~~~

If tests parse successfully yet runtime parsing fails, compare the exact source, Spring version, and parser context before inspecting data.

If both parse successfully yet results differ, move on to comparing context and inputs.

### 2.3. Comparing ParserContext and templates

A plain expression and a template expression do not share the same parse rules:

~~~java
parser.parseExpression("total >= #minimum");
~~~

~~~java
parser.parseExpression(
        "Order total: #{total}",
        new TemplateParserContext()
);
~~~

If runtime uses TemplateParserContext while tests use the default parser, the same string can be interpreted differently or fail to parse.

Record the ParserContext type, custom template prefix/suffix if any, and the actual parser implementation.

### 2.4. Comparing SpelParserConfiguration

SpelParserConfiguration can alter evaluation behavior:

- Auto-grow null references.
- Auto-grow collections.
- Maximum auto-grow size.
- Compiler mode.
- Several other options depending on Spring version.

Example:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                false,
                false,
                128
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

If tests use the default parser while runtime enables auto-grow, expressions accessing nested paths or collection indexes can yield different outcomes. One environment may auto-create intermediate objects while the other throws a null error.

Record the parser configuration in both places rather than inferring it from the expression source.

## 3. Comparing Spring version and classpath

### 3.1. Spring Framework and Spring Boot versions

Version differences can affect:

- Supported SpEL syntax or features.
- Builder APIs and default behaviors.
- PropertyAccessor, MethodResolver, and TypeConverter.
- The compiler and execution limits.
- How Spring integrates expressions in annotations or binding.
- Bugs fixed across releases.

Check the actual dependencies in test and runtime. Do not look only at declared versions in build files; dependency management, transitive dependencies, or packaging can cause the deployed artifact to use a different version.

With Maven, you can inspect the dependency tree:

~~~bash
mvn dependency:tree
~~~

With Gradle:

~~~bash
./gradlew dependencies
~~~

Compare the relevant modules, especially spring-expression, spring-core, spring-context, and Spring Boot dependency management. Spring Framework modules should be managed as a compatible aligned set.

### 3.2. Checking overridden dependencies

Another library may pull in an unwanted Spring version. The test runtime classpath and packaged application classpath can also differ.

When you need to confirm where a class was loaded from, you can log its code source:

~~~java
static void logClassOrigin(Class<?> type) {
    var protectionDomain = type.getProtectionDomain();
    var codeSource = protectionDomain == null
            ? null
            : protectionDomain.getCodeSource();

    logger.info(
            "class={}, origin={}",
            type.getName(),
            codeSource == null
                    ? "unknown"
                    : codeSource.getLocation()
    );
}
~~~

Use this for classes like SpelExpressionParser, StandardEvaluationContext, or a custom converter. This helps spot unexpected classpaths or packaging.

### 3.3. ClassLoader and deployment environment

Plugins, application servers, module systems, or custom class loaders can make a class findable in tests yet missing at runtime.

This often affects:

- TypeLocator and constructor expressions.
- Reflection on classes or methods.
- Converters with custom domain types.
- Beans loaded from modules or plugins.
- Proxies and dynamically generated classes.

If errors involve type resolution or reflection, record the ClassLoader of the target and the class the expression attempts to access.

## 4. Comparing EvaluationContext

EvaluationContext decides what an expression can see and do. Two environments using the same source while constructing different contexts is a very common cause of errors.

### 4.1. StandardEvaluationContext and SimpleEvaluationContext

Tests might use StandardEvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);
~~~

While runtime uses SimpleEvaluationContext:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

The two context types do not share the same feature set. SimpleEvaluationContext restricts type references, constructors, and bean references; method invocation is also not enabled by default in common builders.

If tests succeed calling a method or referencing a bean yet runtime fails, check the actual context before changing the expression.

Do not switch runtime to a permissive context merely to make test and production produce the same result. Choose the context matching the permissions the use case actually requires.

### 4.2. Root object

Compare:

- Actual class of the root object.
- Whether the object is a proxy.
- Values and types of properties accessed by the expression.
- Whether intermediate objects are null.
- Whether getters might access lazy data.
- Whether the object was mutated between preparation and evaluation.

You can log the root type:

~~~java
Object root = rootObject;

logger.debug(
        "SpEL root type={}",
        root == null ? "null" : root.getClass().getName()
);
~~~

Do not log the entire root object if it contains personal data, tokens, or sensitive information. Instead, log necessary fields in redacted form.

### 4.3. Context variables

Tests often set variables directly:

~~~java
context.setVariable("minimum", new BigDecimal("100"));
~~~

Runtime may obtain variables from a request, configuration, or another component. Compare:

- Whether variable names are identical.
- Whether variables exist.
- Runtime types of values.
- Whether values are null.
- Whether values were normalized before evaluation.

For example, Integer 100 and BigDecimal 100 can participate differently in arithmetic or overload resolution. Do not log only display values; also log the class of the value.

You can use a safe helper:

~~~java
static String describeValue(Object value) {
    if (value == null) {
        return "null";
    }

    return value.getClass().getName();
}
~~~

For sensitive data, log only the type and metadata, not the value.

### 4.4. PropertyAccessor and registration order

A context can register custom accessors:

~~~java
context.addPropertyAccessor(customAccessor);
~~~

If test and runtime register different accessors or in different orders, the same property may be read through different paths.

Compare:

- Accessor types.
- Target classes supported by each accessor.
- Registration order.
- canRead/read/canWrite/write behavior.
- Whether the accessor calls a backend or another getter.

Custom accessors should scope getSpecificTargetClasses() accurately. Do not declare support for all targets if only handling one object type.

### 4.5. MethodResolver, ConstructorResolver, and BeanResolver

Method calls, constructor expressions, and bean references depend on the context's resolvers.

Bean reference example:

~~~java
@pricingService.calculate(order)
~~~

This only works if the context has an appropriate BeanResolver. Tests may use a context configured with BeanFactoryResolver while runtime lacks a resolver or uses a different allowlist.

Custom method resolvers can also alter which overload is chosen. Constructor resolvers and TypeLocator can make constructor expressions work in tests yet fail in the deployed artifact.

Compare the actual resolvers and the lists of allowed beans/types/methods. Do not log secrets or the entire ApplicationContext structure.

## 5. Comparing TypeConverter and ConversionService

### 5.1. Type conversion affects results

SpEL may need conversion when:

- Assigning a value to a property.
- Calling a method with differently typed arguments.
- Calling a constructor.
- Requesting getValue with a target result type.

StandardEvaluationContext normally uses StandardTypeConverter. Applications can replace TypeConverter with a converter backed by a custom ConversionService.

Example:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);
~~~

If tests register the CustomerCode converter while runtime does not, an expression may pass in tests yet fail when evaluated in production.

### 5.2. Comparing registered converters

Do not compare only the ConversionService bean name. Verify the converter configuration:

- Custom Converter and ConverterFactory instances.
- GenericConverter and ConditionalGenericConverter.
- Related Formatters.
- Converters depending on TypeDescriptor or annotations.
- Rules for null and malformed data.

A ConversionService can support the same type pair yet yield different results due to custom converters or locales.

### 5.3. Values that look the same yet have different types

For example, the string "100", Integer 100, and BigDecimal 100 can render identically yet are not the same type.

In tests, fixture data might construct BigDecimal directly. Runtime receives a string from JSON or a request and converts it into Integer. This can affect comparisons, overloads, or getValue results.

Record source type and target type when investigating conversion errors.

## 6. Comparing data and object models

### 6.1. Test fixtures are often simpler than real data

Tests may use objects constructed directly:

~~~java
Order order = new Order("O-100", "PAID", new BigDecimal("150"));
~~~

Runtime may receive objects via:

- JSON deserialization.
- Database/ORM.
- Mapping between DTO and entity.
- Message broker.
- Cache.
- Another service.

These sources can produce different nulls, default values, collection types, or states.

Use a redacted data snapshot to reproduce errors instead of hand-crafting a roughly similar object.

### 6.2. Null, empty, and missing are not the same

Distinguish:

- Property absent from payload.
- Property present with value null.
- Empty collection.
- Uninitialized collection.
- Map missing key.
- Map containing key with null value.

These cases can lead to different SpEL results, especially when using safe navigation, selection, projection, or indexers.

### 6.3. Collection types and ordering

Tests often use List.of or LinkedHashMap with deterministic ordering. Runtime may use HashSet, HashMap, or collections from ORM.

If an expression uses first/last selection or relies on iteration order, results can differ. Selection does not automatically sort data.

When order carries business meaning, sort data before evaluating or use collection structures with an explicit ordering contract.

### 6.4. Proxies and lazy loading

ORM-managed entities can be proxies. Property getters may trigger lazy loading or require an active transaction/session.

Tests using non-proxied DTOs read properties successfully. Runtime using proxies after the transaction closes can raise errors when getters access lazy relationships.

When in doubt, log the actual class of the object and check whether getters trigger queries. Do not call extra getters arbitrarily in diagnostic logging because the logging itself can trigger lazy loading.

A more stable approach is creating a DTO/view holding needed data inside the transaction and evaluating expressions against that DTO.

## 7. Comparing profiles and environment configuration

### 7.1. Active profiles

Spring profiles can change beans, converters, property sources, or parser configuration:

~~~java
@Profile("test")
@Configuration
class TestExpressionConfiguration {
}
~~~

~~~java
@Profile("prod")
@Configuration
class ProductionExpressionConfiguration {
}
~~~

If tests use the test profile while runtime uses the production profile, beans with the same name or role can have different implementations.

Record active profiles and selected configurations. Do not put secret values into logs.

### 7.2. Property sources and Environment

Values in expressions can depend on property placeholders or configuration beans:

~~~java
@Value("$" + "{rules.minimum-total:100}")
private BigDecimal minimumTotal;
~~~

Tests might use application-test.yml or @TestPropertySource. Runtime might read values from environment variables, ConfigMaps, secret stores, or external configuration services.

Compare property names and configuration sources, not just final values. Also check whether default values apply in one environment but not the other.

### 7.3. Property placeholders and SpEL are different

Two common syntaxes:

~~~java
@Value("${app.minimum-total:100}")
private BigDecimal minimumTotal;
~~~

~~~java
@Value("#{pricingPolicy.minimumTotal}")
private BigDecimal minimumTotal;
~~~

Placeholders `${...}` fetch values from Environment/property sources. SpEL `#{...}` evaluates expressions, capable of accessing objects or beans per context.

If tests only declare a property while runtime references a bean, the two flows can have different initialization order and dependencies.

### 7.4. Environment variables and naming conventions

Environment variable names can be mapped to properties according to Spring Boot rules. Check actual post-binding values, especially when keys have hyphens, dots, or nested configuration.

Do not log secrets; only record that the property is present, which source was chosen, and the post-binding type.

## 8. Locale, timezone, and data formatting

### 8.1. Locale

Locale can affect Formatters or conversions between String and date/number types. Tests running with a developer machine's default locale can differ from a production container.

For instance, numeric strings with commas or decimal points can be parsed differently depending on formatter and locale.

If an expression depends on formatting, configure the locale explicitly instead of relying on the JVM default locale.

### 8.2. Timezone and date/time

Compare values:

- Default ZoneId.
- JVM default TimeZone.
- Injected Clock.
- Date/time types in use.
- Formatter and parser patterns.

Tests often use fixed dates or a fake Clock. Runtime uses system time and the container's timezone. A date comparison condition can flip results near day boundaries or daylight saving transitions.

Inject Clock into business logic and use Instant/OffsetDateTime/LocalDate per required semantics. Avoid calling system time directly inside getters or methods used by expressions.

### 8.3. Precision and rounding

Monetary amounts or decimals can differ because data is deserialized, converted, or rounded at different layers.

Use BigDecimal with explicit scale and rounding policy. Do not convert to double just to make expressions easier to write.

## 9. Compiler mode and caching

### 9.1. Interpreted and compiled modes

SpEL supports compiler modes with options such as OFF, IMMEDIATE, and MIXED depending on the Spring version.

Tests may use the default parser in interpreted mode while runtime enables the compiler. Some expressions may be ineligible for compilation or have behaviors that must be tested per mode.

When an error only occurs at runtime, reproduce it with the exact compiler mode and parser configuration. To isolate the cause, run a test comparing interpreted and compiled modes with identical source, context, and data.

Do not treat compiler mode as a security mechanism or assume compiled is always faster for every expression.

### 9.2. Caching Expression instances

Applications often cache parsed Expressions to avoid repeated parsing. Tests might re-parse each time while runtime uses an expression cache.

Verify whether the cache key includes the exact source, parser context, and relevant configuration. If rule source changes while the cache still returns the old Expression, runtime can execute content different from current configuration.

Do not cache an Expression under an overly broad key if sources or parser configurations can vary.

### 9.3. Do not arbitrarily share mutable EvaluationContexts

Expressions can be cached and reused; EvaluationContext usually holds the root object, variables, and resolvers/accessors. Do not share a mutable context across requests if each request needs its own root or variables.

A shared context can cause one request to see variables or a root object set by another request. Separate immutable configuration from per-evaluation data and create contexts per request or operation.

## 10. Threads, transactions, and security context

### 10.1. Thread-local context

Some application data is retrieved from ThreadLocal, SecurityContextHolder, RequestContextHolder, or MDC. Tests running synchronously on a single thread can see that context, whereas runtime switching to another executor loses it.

If a getter or method called by an expression relies on thread-local state, results can differ under async execution.

Do not assume thread-locals propagate automatically across all executors. Pass required data explicitly via arguments/context or configure appropriate context propagation.

### 10.2. Transaction boundaries

Expressions may call getters or methods accessing repositories. Tests might run inside a @Transactional test while runtime calls after the transaction ends.

This affects lazy loading, sessions, and data readability. Check which transaction is active at evaluation time, especially if expressions run in event listeners or async tasks.

### 10.3. Security principal and tenant

Tests might use an administrative user or mock SecurityContext. Runtime uses actual principals and tenants.

If an expression calls a policy bean or getter depending on the security context, results can differ due to roles, tenants, or data scopes.

Do not use expressions to replace authorization. Check permissions in services and include only data within the principal's scope in the root object.

## 11. Inspecting referenced beans and proxies

### 11.1. Same bean name, different implementation

Profiles or conditional configuration can register different implementations under the same name or interface. Tests might use a fake/mock bean; runtime uses the real service.

If an expression calls a method on a bean, record:

- Bean name.
- Actual target class.
- Whether it is a Spring proxy.
- Method signature invoked.
- Method result and error.
- Dependencies and profile that created that bean.

### 11.2. Proxies and method invocation

Spring AOP can wrap beans in proxies. A method call in an expression can pass through a proxy and trigger transactions, security, caching, or other advice.

Tests using direct unproxied objects do not reproduce interceptors.

When needing to inspect proxies, log the runtime class and use AopUtils in diagnostic code if the dependency is available. Avoid forcing proxy unwrapping in business logic just to make an expression work.

### 11.3. Do not log sensitive objects

Do not log entire beans, root objects, or arguments. Record bean names, classes, redacted technical IDs, and necessary metadata. Log method arguments only when data is non-sensitive and permitted by policy.

## 12. Creating a reproducible diagnostic record

A useful diagnostic record should contain enough details to reconstruct the evaluation without exposing sensitive data.

You can record:

| Group | Information |
|---|---|
| Rule | ID, version, source hash, length |
| Runtime | Application version, Spring version, Java version |
| Parser | Parser class, ParserContext, compiler mode, auto-grow settings |
| Context | Standard/Simple context, root class, variables and variable types |
| Resolver | Accessors, method/constructor resolvers, bean resolver |
| Conversion | TypeConverter and ConversionService implementation |
| Environment | Active profiles, locale, timezone, non-sensitive configuration |
| Execution | Timestamp, thread, transaction state if needed |
| Result | Result type, success/failure status |
| Error | Exception class, SpEL position, message code, cause chain |

You do not need to log every field for every request. Enable diagnostics selectively by rule ID or only when errors occur.

### 12.1. Helper for recording types and metadata

~~~java
static String typeOf(Object value) {
    return value == null
            ? "null"
            : value.getClass().getName();
}
~~~

~~~java
logger.debug(
        "ruleId={}, sourceLength={}, rootType={}, minimumType={}",
        ruleId,
        source.length(),
        typeOf(rootObject),
        typeOf(context.lookupVariable("minimum"))
);
~~~

The example logs only types and length, not actual values. Choose metadata matching the application's data protection policy.

### 12.2. Saving a source hash

You can compute a hash to compare expressions between test and runtime:

~~~java
MessageDigest digest =
        MessageDigest.getInstance("SHA-256");

byte[] hash = digest.digest(
        source.getBytes(StandardCharsets.UTF_8)
);

String sourceHash =
        HexFormat.of().formatHex(hash);
~~~

Hashes verify that both environments use the same source without writing the entire source to logs. If a source contains secrets or sensitive literals, still protect the data in storage and diagnostic records.

## 13. Workflow to reproduce test/runtime discrepancies

Proceed in order to locate the first divergence:

1. **Verify source.** Compare source hash, rule ID, and version.
2. **Verify dependencies.** Compare Spring Framework, Spring Boot, Java, and actual classpath.
3. **Verify parser.** Compare ParserContext and SpelParserConfiguration.
4. **Verify context.** Compare context type, accessors, resolvers, and TypeConverter.
5. **Verify root.** Compare runtime class, proxy, null, and relevant property states.
6. **Verify variables.** Compare names, types, and value ranges of each variable.
7. **Verify environment.** Compare profiles, property sources, locale, timezone, and security context.
8. **Verify timing.** Compare thread, transaction, lifecycle phase, and async behavior.
9. **Reproduce with redacted fixtures.** Use a real data snapshot instead of an approximate mock object.
10. **Separate parse/evaluate.** Determine whether the error occurs before or during evaluation.
11. **Compare compiler mode/cache.** Only after preceding conditions are equivalent.
12. **Fix the root cause.** Align needed configurations or adjust data/context design; do not widen all permissions just to stop errors.

Record the first difference that can explain the outcome. Multiple simultaneous changes make it hard to tell which change actually solved the problem.

## 14. Example: verifying parser and context configuration

You can centralize parser creation into a factory so test and runtime share the same configuration:

~~~java
@Configuration
public class SpelConfiguration {

    @Bean
    public ExpressionParser expressionParser() {
        SpelParserConfiguration configuration =
                new SpelParserConfiguration(
                        false,
                        false,
                        128
                );

        return new SpelExpressionParser(configuration);
    }

    @Bean
    public ConversionService expressionConversionService() {
        return new DefaultConversionService();
    }
}
~~~

Creating context per evaluation:

~~~java
@Component
public class RuleEvaluator {

    private final ExpressionParser parser;
    private final ConversionService conversionService;

    public RuleEvaluator(
            ExpressionParser parser,
            ConversionService conversionService) {
        this.parser = parser;
        this.conversionService = conversionService;
    }

    public Boolean evaluate(
            String source,
            Object rootObject,
            BigDecimal minimum) {

        StandardEvaluationContext context =
                new StandardEvaluationContext(rootObject);

        context.setVariable("minimum", minimum);
        context.setTypeConverter(
                new StandardTypeConverter(conversionService)
        );

        Expression expression = parser.parseExpression(source);

        return expression.getValue(context, Boolean.class);
    }
}
~~~

Tests should use RuleEvaluator itself or the same configuration factory instead of constructing a divergent parser and context:

~~~java
@Test
void evaluatesRuleWithProductionConfiguration() {
    Boolean result = evaluator.evaluate(
            "status == 'PAID' && total >= #minimum",
            orderView,
            new BigDecimal("100")
    );

    assertTrue(result);
}
~~~

Shared configuration reduces the chance that tests accidentally exercise a different feature set than runtime. Test data still needs to represent cases runtime can encounter.

## 15. Layered testing

### 15.1. Unit tests for expressions

Unit tests should verify source, root object, and variables with deterministic data. They are suited for testing expression logic quickly and reproducibly.

Do not over-mock the parser or context if the goal is to verify that SpEL actually parses and evaluates the expression.

### 15.2. Integration tests for the Spring context

Integration tests need bean, converter, profile, and resolver configurations close to runtime. If expressions reference beans, tests should build an ApplicationContext and use real beans or properly scoped test doubles.

Also check initialization order if expressions are used in @Value or bean definitions.

### 15.3. Testing with profiles and property sources

Use profiles and property sources matching each important environment. Do not assume application-test.yml and deployment configuration have identical values.

You can use @ActiveProfiles and @TestPropertySource to create targeted tests. With Spring Boot, verify property source precedence when multiple configuration sources exist.

### 15.4. Testing on the deployed artifact

Some errors only appear after packaging due to classpath, resources, class loaders, or environment settings. When in doubt, run integration tests or smoke tests against an artifact/container built close to deployment.

There is no need to copy all production data into tests. Use redacted fixtures and equivalent configuration at points affecting expressions.

## 16. Common errors and resolution directions

| Symptom | Possible discrepancy | Investigation direction |
|---|---|---|
| Test parses, runtime parse fails | Different source, Spring version, or ParserContext | Compare source hash and parser |
| Property exists in test but missing at runtime | Different root class, proxy, or accessor | Log actual class and inspect getter |
| Test calls method, runtime cannot | Different Simple/Standard context or MethodResolver | Compare context and resolvers |
| Bean reference fails only at runtime | Different BeanResolver, profile, or bean name | Inspect resolver and bean configuration |
| String conversion fails only in production | Unregistered converter or different TypeDescriptor | Compare ConversionService |
| Selection result differs | Different collection data or ordering | Compare data and collection implementation |
| Nested path fails only outside test | Different null, lazy proxy, or auto-grow | Inspect object graph and parser configuration |
| Numeric threshold yields different result | Different Integer/Long/BigDecimal or rounding | Log source/target types and converter |
| Date/time condition shifts | Different locale, timezone, or Clock | Configure time explicitly |
| Fails only when running async | Thread-local, transaction, or security context not propagated | Inspect executor and context propagation |
| Fails only with compiler enabled | Different interpreted/compiled mode | Reproduce with same compiler mode |
| Old rule still runs after update | Wrong expression cache key or invalidation | Inspect cache and version |
| Startup fails during bean creation | SpEL bean lookup creates circular dependency | Inspect @Value and dependency graph |
| Logs lack sufficient info | Only outer message logged | Log position, message code, and cause chain |

Do not fix by catching every exception and returning false/null. Preserve the cause and classify parse failures, evaluation failures, conversion failures, backend errors, and permission errors.

## 17. Operational principles

To reduce differences between test and runtime:

- Centralize parser and TypeConverter configuration when flows need the same policy.
- Create EvaluationContext per evaluation with explicit root and variables.
- Use DTOs/views instead of passing entities or services with large object graphs.
- Register converters/accessors/resolvers in testable configuration.
- Lock dependency versions via the project's dependency management.
- Control profiles and property sources.
- Use explicit Clock, locale, and timezone when rules depend on time or formatting.
- Test both interpreted and compiled modes if runtime uses the compiler.
- Maintain an expression cache and version-based invalidation policy.
- Do not share mutable contexts across requests.
- Do not log sensitive data when enabling diagnostics.
- Keep authorization and validation in the business layer.

A good test is not the one with the most mocks; tests must faithfully reproduce the parser, context, and data conditions affecting the expression.

## 18. Summary

Differences between test and runtime usually stem from the SpEL execution environment rather than the expression source alone.

When investigating, compare sequentially:

- Expression source, rule version, and ParserContext.
- Spring/Java versions, classpath, and ClassLoader.
- SpelParserConfiguration and compiler mode.
- StandardEvaluationContext or SimpleEvaluationContext.
- Root object, proxies, properties, and variables.
- PropertyAccessor, MethodResolver, ConstructorResolver, and BeanResolver.
- TypeConverter, ConversionService, and Formatters.
- Profiles, property sources, locale, timezone, and data.
- Threads, transactions, security context, cache, and evaluation timing.

Separate parsing from evaluation, record reproducible metadata, use redacted fixtures, and find the first difference that explains the error. When test and runtime share parser/context configurations where needed and data is prepared under clear contracts, SpEL behavior becomes predictable and easy to diagnose.
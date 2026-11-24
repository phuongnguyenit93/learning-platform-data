# Reading Configuration from Environment and System Properties

In Spring, configuration can come from multiple sources such as configuration files, operating system environment variables, JVM system properties, or application-provided data. SpEL can read several of these sources directly within Spring's expression context, while combining configuration values with conditions and calculations.

Distinguish two mechanisms that often appear side by side: property placeholders use the syntax ${app.region:local} to retrieve a configuration value by name; SpEL uses the syntax #{...} to evaluate an expression. When you only need to pass configuration into a bean, placeholders are usually the simpler choice. When you need to access the system properties map, environment variables, or compute from those values, SpEL can handle the expression part.

## 1. What Are Environment, System Property, and Environment Variable?

The three concepts are related but not synonymous.

**JVM system property** is a name/value pair stored in the Java process's property system. Applications read it with System.getProperty() or System.getProperties(). Example:

    java -Dapp.region=apac -jar application.jar

In code:

    String region = System.getProperty("app.region");

**Environment variable** is an environment variable supplied by the operating system or deployment environment to the process. Java reads it with System.getenv():

    String path = System.getenv("PATH");

An environment variable can be set before launching the application, in containers, service managers, or deployment pipelines.

**Spring Environment** is Spring's abstraction for accessing PropertySources. It can aggregate multiple configuration sources such as system properties, environment variables, configuration files, and application-registered sources:

    String region = environment.getProperty("app.region");

Spring Environment helps the application read configuration by a logical name without checking each source manually. Precedence among sources depends on Environment configuration and the application platform, such as how Spring Boot orders PropertySources. Do not assume a fixed order for all applications without checking the actual configuration.

## 2. Distinguishing Placeholders from SpEL

In Spring configuration, two syntaxes are often used side by side:

- ${app.region:local} is a property placeholder. Spring looks up the property named app.region and uses local if no value is found.
- #{...} is a SpEL expression. Spring parses and evaluates the inner content as an expression.

Example injecting a simple configuration:

    @Value("${app.region:local}")
    private String region;

Example reading a JVM system property with SpEL in the bean expression context:

    @Value("#{systemProperties['user.timezone']}")
    private String timeZone;

Example reading an environment variable:

    @Value("#{systemEnvironment['APP_REGION']}")
    private String regionFromProcess;

Example using a fallback with Elvis:

    @Value("#{systemEnvironment['APP_REGION'] ?: 'local'}")
    private String region;

Placeholders are generally appropriate when the goal is to retrieve a configuration value by name and optionally declare a default. SpEL is useful when you need to access maps, call permitted methods, combine multiple values, or apply logic before injection.

Do not swap delimiters by mistake: ${...} is not a SpEL expression, and #{...} is not automatically a property placeholder.

## 3. Reading JVM System Properties in Bean Expressions

In Spring's bean definition expression context, Spring provides access to system property values. The common syntax is:

    #{systemProperties['user.timezone']}

Example injecting into a bean:

    @Component
    public class RuntimeSettings {

        private final String timeZone;

        public RuntimeSettings(
                @Value("#{systemProperties['user.timezone']}")
                String timeZone) {
            this.timeZone = timeZone;
        }

        public String getTimeZone() {
            return timeZone;
        }
    }

If the application is started with:

    java -Duser.timezone=Asia/Ho_Chi_Minh -jar application.jar

the expression reads the corresponding value from JVM system properties.

Another key can be accessed:

    #{systemProperties['app.region']}

Using square brackets helps read keys by name, especially when keys contain dots or characters unsuitable for property paths. If the key does not exist, the lookup result may be null; define an explicit fallback rather than assuming the key is always declared.

Example:

    #{systemProperties['app.region'] ?: 'local'}

## 4. Reading Environment Variables in Bean Expressions

Process environment variables are exposed as a map readable in the bean expression context:

    #{systemEnvironment['APP_REGION']}

Example:

    @Component
    public class DeploymentSettings {

        private final String region;

        public DeploymentSettings(
                @Value("#{systemEnvironment['APP_REGION'] ?: 'local'}")
                String region) {
            this.region = region;
        }

        public String getRegion() {
            return region;
        }
    }

If the deployment environment sets APP_REGION=apac, the bean receives the value apac. If the variable does not exist, Elvis selects local.

Environment variable names must match how the operating system and runtime provide keys. On some operating systems, case-sensitivity rules differ; check the actual name in the runtime environment. With Spring Boot configuration, it is usually best to use property placeholders and binding mechanisms to leverage the platform's configuration mapping rules.

Do not confuse environment variables with properties of the Spring Environment object. systemEnvironment is the process environment map; environment is Spring's configuration abstraction if provided in the corresponding context.

## 5. Using Spring Environment to Read Configuration by Property Name

If Java code needs to access configuration across multiple PropertySources, inject Environment:

    @Component
    public class ApplicationSettings {

        private final String region;
        private final int timeout;

        public ApplicationSettings(Environment environment) {
            this.region =
                    environment.getProperty(
                            "app.region", "local");

            this.timeout =
                    environment.getProperty(
                            "app.timeout", Integer.class, 30);
        }
    }

getProperty can accept a target type so Spring converts the value from the configuration source. A default can be provided if the property does not exist.

Property placeholders also use Spring's configuration resolution mechanism:

    @Value("${app.timeout:30}")
    private int timeout;

Meanwhile, SpEL can use systemProperties or systemEnvironment directly in the bean expression context. If the goal is to read a logical configuration such as app.timeout across all PropertySources following Spring's rules, prefer Environment or placeholders rather than reading a single OS map directly.

## 6. Combining System Properties with Fallbacks and Type Conversion

System properties and environment variables are normally represented as Strings. When injected into a field or constructor parameter of another type, Spring's conversion service can convert the value accordingly.

Example using a placeholder for an integer:

    @Value("${app.retry-count:3}")
    private int retryCount;

If you want to use SpEL to read a system property directly and supply a fallback:

    @Value("#{systemProperties['app.retry-count'] ?: '3'}")
    private int retryCount;

Elvis handles the case where the lookup result is null or an empty string. The result is then converted by Spring to int when injected into the field.

For booleans:

    @Value("#{systemProperties['feature.enabled'] ?: 'false'}")
    private boolean featureEnabled;

For dates, times, or domain types, use Environment#getProperty with a target type, configuration properties, or an explicitly configured converter. Do not stuff complex parsing logic into a SpEL string if it can live in a tested Java configuration class.

If the value exists but has an invalid format, conversion may fail at bean initialization. Check the configuration format and provide a clear enough error message so operators know which property needs fixing.

## 7. Comparing Multiple Configuration Sources

An application may need to prioritize logical configuration properties, then fall back to system properties or environment variables. That logic can be written in Java via Environment:

    String region = environment.getProperty("app.region");

    if (region == null || region.isBlank()) {
        region = System.getProperty("app.region");
    }

    if (region == null || region.isBlank()) {
        region = System.getenv("APP_REGION");
    }

    if (region == null || region.isBlank()) {
        region = "local";
    }

This clearly expresses an application-defined fallback order. However, if Spring Environment already aggregates the desired sources and precedence order, you only need:

    String region =
            environment.getProperty("app.region", "local");

Do not rewrite source ordering separately in every bean, as this easily creates inconsistent behavior across components. Configure PropertySources centrally or use the application's standard configuration mechanism.

In SpEL, multiple maps can be combined if truly needed:

    #{systemProperties['app.region']
        ?: systemEnvironment['APP_REGION']
        ?: 'local'}

The expression above prioritizes the system property, then the environment variable, and finally local. This order is defined by the expression itself; it may differ from the precedence in Spring Environment or Spring Boot. Only use this approach when that exact ordering is an intentional rule.

## 8. Reading Configuration in XML Bean Definitions

SpEL can be used directly in XML bean definitions:

    <bean id="runtimeSettings"
          class="com.example.RuntimeSettings">
        <property name="timeZone"
                  value="#{systemProperties['user.timezone']}"/>
        <property name="region"
                  value="#{systemEnvironment['APP_REGION'] ?: 'local'}"/>
    </bean>

Here, Spring evaluates the expressions in attribute values when creating the bean. Content inside #{...} is processed as SpEL; if you only want to fetch a configuration property by name, you can use a placeholder:

    <property name="region" value="${app.region:local}"/>

For XML, follow XML escaping rules if values contain special characters. In addition, make sure the bean expression resolver and ApplicationContext placeholder mechanism are configured appropriately for how the application initializes the container.

## 9. Standalone Evaluation with ExpressionParser

When using SpEL outside bean definitions, do not assume the names systemProperties and systemEnvironment are automatically available as they are in Spring's bean expression context. A standalone StandardEvaluationContext must be supplied with data explicitly.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable(
            "systemProperties", System.getProperties());

    context.setVariable(
            "systemEnvironment", System.getenv());

    Expression expression =
            parser.parseExpression(
                    "#systemProperties['user.timezone']");

    String timeZone =
            expression.getValue(context, String.class);

Here, the application explicitly registers both maps as variables. Therefore, the syntax in the expression has the # prefix:

    #systemProperties['user.timezone']
    #systemEnvironment['APP_REGION']

If you want to read Spring Environment in a standalone expression, you can register Environment as a variable:

    context.setVariable("environment", environment);

    Expression expression =
            parser.parseExpression(
                    "#environment.getProperty('app.region')");

This makes it explicit that Environment is supplied into the context by the application. It also enables the expression to use the same PropertySource mechanism as the rest of the Java code.

## 10. When to Use systemProperties, systemEnvironment, or Environment?

| Need | Suitable Approach |
|---|---|
| Reading a specific JVM system property | systemProperties in bean expressions or System.getProperty() |
| Reading a specific process environment variable | systemEnvironment in bean expressions or System.getenv() |
| Reading a logical property across Spring config sources | Environment.getProperty() or ${...} |
| Injecting a simple config value into a bean | @Value("${key:default}") |
| Computing or choosing fallbacks with an expression | SpEL #{...} |
| Binding a structured config group with many fields | @ConfigurationProperties |

Prefer Spring's standard configuration mechanisms for business properties such as app.region, app.timeout, or feature flags. Reading systemProperties/systemEnvironment directly is appropriate when you genuinely need access to a specific JVM or OS source.

## 11. Value Read Timing and Configuration Changes

When using @Value in a constructor or field, the value is usually resolved during bean creation. The bean receives a value at injection time; if a process system property or environment changes afterward, the injected field does not update automatically.

System properties can be modified in the JVM via System.setProperty(), but mutating global properties at runtime easily creates inconsistent state across beans. Process environment variables are also not a reliable dynamic configuration channel for an application to self-update after startup.

If the application needs configuration that changes at runtime, use a refresh/configuration mechanism aligned with your architecture, or query Environment at the time of use if the PropertySource supports updates. Do not assume a value injected via @Value always reflects the latest configuration.

For frequently used values, bind them into a configuration object with a clear lifecycle and update that object according to the application's configuration management mechanism.

## 12. Common Errors When Reading Configuration

| Expression or Situation | Cause | Resolution |
|---|---|---|
| Using #{app.region} to read a property | This is an identifier/property expression, not a placeholder | Use ${app.region} or access via Environment |
| Using ${...} when computation is needed | Placeholders only resolve values, not SpEL logic | Use #{...} for the expression part |
| systemProperties not found in a standalone context | No auto-configured Spring bean expression context | Register the map with setVariable and use #systemProperties |
| Value is null | Key does not exist or source is not configured | Verify the key and set a fallback |
| Type mismatch when injecting | String value cannot be converted | Check the format or use an appropriate target type |
| Environment variable name mismatch | Naming rule differences by OS/runtime | Check the actual key in the process |
| @Value does not change after editing configuration | Bean already received the value at initialization | Use a refresh mechanism or read Environment when needed |
| SpEL uses a different source order than expected | Expression picks maps manually instead of Spring PropertySource precedence | Use Environment or define fallback order explicitly |

When debugging, determine where the expression runs: inside Spring bean definitions or in an application-created StandardEvaluationContext. Then check the data source, key, result type, and when the value is resolved.

## 13. Security and Configuration Operations

System properties and environment variables often contain deployment information, endpoints, feature flags, or secrets. The fact that a value can be read in SpEL does not mean every rule should be allowed to access it.

Some principles:

- Expose to the context only the configuration sources the expression needs to use.
- Do not place passwords, access tokens, or secrets into templates/rules that can be edited by untrusted users.
- Do not log all of System.getProperties() or System.getenv(); they may contain sensitive data.
- Set reasonable defaults for optional configuration and fail fast on required configuration.
- Validate configuration values before using them in business logic.
- Do not use mutable system properties as a synchronized configuration store across requests.
- Use a secret manager or platform secret management instead of hard-coding secrets in expressions.

If expressions come from users or external configurations, restrict EvaluationContext and which properties/methods expressions can access. Even an expression that only reads system properties can still leak operational information if the context grants overly broad access.

## 14. Testing Configuration and Fallbacks

Test both cases where a value is present and where a value is missing:

- System property is set: verify the expression reads the right key.
- Environment variable is present: verify the exact name and value.
- Both sources are missing: verify the fallback is used.
- Empty value: verify whether it is treated as missing according to the rules.
- Malformed value: verify the application reports a clear error.
- PropertySource has multiple sources declaring the same key: verify precedence matches Environment configuration.
- Value injected at initialization: verify timing and bean lifecycle.
- Expression running in a standalone context: verify the map or Environment is explicitly registered.

Example testing a fallback expression with a directly provided system property map:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    Properties properties = new Properties();
    properties.setProperty("app.region", "apac");

    context.setVariable("systemProperties", properties);

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "#systemProperties['app.region'] ?: 'local'");

    String region = expression.getValue(context, String.class);

The result is apac. If the app.region key is removed, the result is local. This test does not modify the JVM's global system properties, so it can run independently and repeatably.

## Conclusion

SpEL can read JVM system properties and environment variables in Spring's bean expression context via systemProperties and systemEnvironment. With a standalone StandardEvaluationContext, the application must register these maps as variables and reference them with the # prefix. Spring Environment provides a unified abstraction for reading properties from multiple PropertySources.

Use ${...} when you only need to resolve configuration by name, use #{...} when you need expression logic, and use Environment or configuration properties for multi-source business configuration. Clearly define fallback order, read timing, data types, and access rights; avoid letting expressions or logs expose secrets from the deployment environment.
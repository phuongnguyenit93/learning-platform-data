# Do Not Use Test Configuration to Mask Broken Production Configuration

A test suite can pass green while the application still fails to start in production. A common cause is that the test environment supplies properties, profiles, or replacement beans that prevent Spring from using the configuration production actually needs.

For example, production requires the payment gateway URL and an API key from environment variables. The test sets a fake URL and sample key with `@TestPropertySource`. The test passes, yet it does not prove that the production environment provides those two values. Similarly, the `test` profile may register `FakePaymentGateway` while the `production` profile is missing the real `PaymentGateway` bean.

This is a form of **false confidence caused by test configuration masking production configuration errors**. The test only proves the application works with the properties and beans assembled for testing. To verify production configuration, clearly separate what is being tested, what is intentionally replaced, and what must be verified in the deployment environment.

## 1. Why Can Passing Tests Still Mask Production Failures?

Spring loads configuration from multiple sources: `application.yml`, profile-specific files, environment variables, system properties, command-line arguments, programmatically added property sources, and Spring Test configuration sources.

These sources have a precedence order. A value placed in a higher-precedence source can override values in `application.yml` or `application-prod.yml`.

Example:

~~~yaml
# application-prod.yml
payment:
  base-url: https://payments.example.com
  api-key: ${PAYMENT_API_KEY}
  connect-timeout: 2s
  read-timeout: 5s
~~~

A test might declare:

~~~java
@SpringBootTest
@ActiveProfiles("prod")
@TestPropertySource(properties = {
        "payment.base-url=http://localhost:9099",
        "payment.api-key=test-key",
        "payment.connect-timeout=10s"
})
class PaymentServiceTest {
}
~~~

This test runs with the `prod` profile, yet three critical properties have been overridden by the test's property source. If `application-prod.yml` is missing `base-url`, has an invalid timeout setting, or `PAYMENT_API_KEY` is not deployed, the test can still pass.

Distinguish between two conclusions:

- A passing test proves the service works with the values supplied by the test.
- A passing test does not prove that packaged production values or deployment environment values are correct.

Putting the `prod` profile name in an annotation is not enough to prove the test uses the full production configuration. Inspect all property sources and replacement beans in the context.

## 2. Ways Test Configuration Commonly Masks Production Errors

### 2.1. Using the test profile instead of the production profile

Suppose a project has two files:

~~~yaml
# application-test.yml
payment:
  enabled: false
  base-url: http://localhost:9099
~~~

~~~yaml
# application-prod.yml
payment:
  enabled: true
  base-url: ${PAYMENT_API_URL}
~~~

The test uses:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentServiceTest {
}
~~~

When the `test` profile is active, Spring loads `application-test.yml`. The test does not verify `application-prod.yml`. That is completely reasonable when the goal is testing business logic in a test environment, but those results cannot be used to conclude production configuration is valid.

Several discrepancies can be missed:

- Production payment beans are not registered under the `test` profile.
- The `payment.enabled` flag in production is set incorrectly.
- The production URL is missing or malformed.
- Timeouts, retries, or TLS differ from production requirements.
- The production profile is not activated during deployment.
- A production-only bean is missing a dependency.

Tests per profile remain necessary. What matters is having a separate verification step for production or production-like configuration.

### 2.2. Using @TestPropertySource to supply every missing value

`@TestPropertySource` lets you add fixed properties into the test `Environment`. These values have high precedence and can hide missing or broken properties in configuration files.

~~~java
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:postgresql://localhost/testdb",
        "spring.datasource.username=test",
        "spring.datasource.password=test",
        "payment.api-key=dummy",
        "payment.base-url=http://localhost:9099"
})
class ApplicationIntegrationTest {
}
~~~

This is convenient for isolating dependencies, but if the test is used as evidence for production configuration, it has replaced the very values that needed verification.

Before adding a property to a test, state its purpose explicitly:

- Does this value only help the test run safely against a test database or mock server?
- Is this value part of the production configuration contract?
- If the production property is missing, should this test fail?
- Does setting a test value remove the ability to detect the bug being sought?

If a property is the subject under test, do not override it in that test. If an external dependency must be replaced to avoid calling real systems, replace only the connection properties outside the scope being verified.

### 2.3. Using @DynamicPropertySource to replace real configuration

`@DynamicPropertySource` is very useful when a test uses Testcontainers or a mock server and needs a URL determined at runtime.

~~~java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

These dynamic properties have high precedence in Spring TestContext. That helps the test use a container database, but it also means the test does not check production database URLs and credentials.

This is not a reason to avoid Testcontainers. Use them for the right purpose:

- Repository integration tests verify the application works with real PostgreSQL in a test environment.
- Configuration contract tests verify production properties are supplied and bound properly.
- Deployment validation verifies manifests, secret references, and environment variables are attached to the workload.

One test does not have to prove everything at once. However, do not take a passing test that replaced the production database with a container as proof that production database configuration is correct.

### 2.4. Mocking or replacing production beans with test implementations

For example, production uses:

~~~java
@Component
@Profile("prod")
class HttpPaymentGateway implements PaymentGateway {
    // Call external payment service.
}
~~~

In tests, configuration replaces the bean:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PaymentTestConfiguration {

    @Bean
    @Primary
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

A test using `FakePaymentGateway` does not test `HttpPaymentGateway`. Nor does it verify the dependencies, HTTP client, timeouts, TLS, or properties required by the production adapter.

Replacing beans is a valid isolation technique when testing service business logic. But if the goal is to verify wiring or configuration of the production adapter, do not replace that bean itself.

You can split into separate tests:

- Unit tests for `PaymentService` with a mocked `PaymentGateway`.
- Adapter tests for `HttpPaymentGateway` with a mock HTTP server.
- Context tests verifying the production bean is registered and receives the right configuration.
- Selective system tests verifying communication through a safe integration environment.

### 2.5. Disabling features so tests can boot

Some test configurations set production features to `false`:

~~~properties
payment.enabled=false
messaging.enabled=false
scheduler.enabled=false
security.enabled=false
~~~

This can help the context start quickly, but it can hide errors such as:

- Production beans not being registered.
- Misconfigured `@ConditionalOnProperty` conditions.
- Missing or unapplied `SecurityFilterChain`.
- Message listeners not being created.
- Schedulers missing required dependencies.
- Important integrations unintentionally disabled.

If a test only exercises an unrelated service, disabling those features may be appropriate. Still, a separate test must verify the features required to be enabled in production.

## 3. Property Precedence: Understanding the Final Value Spring Actually Uses

Spring `Environment` aggregates properties from multiple `PropertySource`s. When the same key appears in multiple sources, the higher-precedence source is used.

In Spring Boot, higher-precedence sources such as command-line arguments, system properties, environment variables, and test-added property sources can override values in configuration files. The exact ordering also depends on the source type and how the application is launched.

Some common sources:

| Source | Example | Effect |
|---|---|---|
| `application.yml` | `payment.connect-timeout: 2s` | Packaged default value |
| `application-prod.yml` | `prod` profile-specific configuration | Overrides shared configuration when `prod` profile is active |
| Environment variable | `PAYMENT_CONNECT_TIMEOUT=3s` | Configuration supplied by the deployment environment |
| System property | `-Dpayment.connect-timeout=4s` | JVM-level configuration |
| Command-line argument | `--payment.connect-timeout=5s` | Override when running the application |
| `@TestPropertySource` | `payment.connect-timeout=10s` | Test-specific property |
| `@DynamicPropertySource` | Container URL retrieved from supplier | Dynamic property for tests |

Do not look solely at YAML files to conclude what the actual value is. Production may receive values from environment variables or a secret/config store. Conversely, tests may be using a higher-precedence source that leaves YAML files untested.

You can read the resolved value from `Environment`:

~~~java
@SpringBootTest
@ActiveProfiles("prod")
class PaymentConfigurationTest {

    @Autowired
    private Environment environment;

    @Test
    void shouldResolvePaymentTimeout() {
        assertEquals(
                Duration.ofSeconds(2),
                environment.getProperty(
                        "payment.connect-timeout",
                        Duration.class
                )
        );
    }
}
~~~

The assertion above verifies the final value returned by `Environment` in the test context. It still does not prove the value came from the right source. If a test property or environment variable is overriding the production file, the assertion might pass for a different reason.

When you need to verify the configuration source, inspect which `PropertySource` contains the key or use Spring Boot's origin metadata for property sources that support origin tracking. Do not log secret values when checking configuration.

## 4. Separating Application Configuration, Deployment Configuration, and Secrets

Not every production value should be stored in `application-prod.yml`.

Configuration can be divided into three groups:

| Group | Example | Typical Source |
|---|---|---|
| Application configuration | Timeouts, retries, feature flags, queue names | Configuration files or config stores |
| Environment configuration | Database hosts, API URLs, bucket names | Environment, deployment config, ConfigMap |
| Secrets | Passwords, API keys, private keys, tokens | Secret manager, Kubernetes Secret, or secret management platform |

A test should not require real production secrets. Using real secrets in tests can expose sensitive data in logs, artifacts, or inappropriate CI environments.

However, using dummy values does not prove production secrets are provisioned either.

Separate responsibilities:

1. **Configuration contract tests** verify property names, data types, required values, and validation rules using safe configuration.
2. **Deployment configuration validation** checks that manifests or pipelines reference the right secrets and environment variables.
3. **Runtime startup validation** verifies the workload receives required values upon starting in staging or production.
4. **Secret availability checks** verify only that secrets exist and are accessible by the workload, without printing values to logs.

Do not put secrets into source code, test reports, or assertion messages. When checking that a secret is present, assert only existence or valid binding outcomes.

## 5. Testing Production Configuration Without Connecting to Production

A common mistake is thinking that testing the `prod` profile requires booting the application with all production services. That is unnecessary and can cause unintended side effects.

You can build a **production-like** environment: using the same configuration structure, the same property names, and the same critical bean conditions, while pointing external dependencies to safe databases/containers or mock servers.

The goal is to keep the values being verified intact and replace only boundaries outside the test scope.

For example:

- Keep the `prod` profile to load `application-prod.yml`.
- Keep `payment.enabled` and production timeouts.
- Keep the production beans to be verified.
- Use a PostgreSQL container instead of the production database.
- Use a mock HTTP server instead of the real payment gateway.
- Supply a validly formatted dummy secret if the test only needs to instantiate beans.
- Verify real production secrets in the deployment pipeline or a separate runtime environment.

Explicitly document in the test that the database URL and payment endpoint are intentionally replaced values. Those properties must not be used as evidence for production configuration.

### Example verifying production profile properties

Suppose `application-prod.yml` contains:

~~~yaml
payment:
  enabled: true
  connect-timeout: 2s
  read-timeout: 5s
  retry:
    max-attempts: 3
  api-key: ${PAYMENT_API_KEY}
~~~

We can write a test that initializes a context with the `prod` profile, supplies a dummy value for the secret so beans can bind, and verifies the non-overridden properties:

~~~java
@SpringBootTest(properties = {
        "payment.api-key=configuration-test-placeholder"
})
@ActiveProfiles("prod")
class ProductionProfileContractTest {

    @Autowired
    private Environment environment;

    @Autowired
    private PaymentProperties paymentProperties;

    @Test
    void shouldLoadProductionPaymentSettings() {
        assertTrue(environment.acceptsProfiles(Profiles.of("prod")));
        assertTrue(paymentProperties.enabled());
        assertEquals(Duration.ofSeconds(2),
                paymentProperties.connectTimeout());
        assertEquals(Duration.ofSeconds(5),
                paymentProperties.readTimeout());
        assertEquals(3, paymentProperties.retry().maxAttempts());
    }
}
~~~

In this example, `api-key` is replaced with a placeholder because the test does not use real secrets. Therefore, the test does not prove `PAYMENT_API_KEY` is configured in production. It only verifies that other production profile settings are loaded in the test context.

If the full context would initialize real datasources or clients, configure safe dependencies for testing or create a minimal contract context loading only the configuration under test. Do not run this test against real production endpoints.

### Validating required properties with validation

You can use `@ConfigurationProperties` and Bean Validation to detect missing or invalid configuration at startup:

~~~java
@ConfigurationProperties(prefix = "payment")
@Validated
public record PaymentProperties(
        boolean enabled,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Valid Retry retry,
        @NotBlank String apiKey
) {
    public record Retry(
            @Min(1) int maxAttempts
    ) {
    }
}
~~~

When a required property is missing or has the wrong type, the context can fail during binding/validation. This is better than letting the failure surface only when the first request calls the payment gateway.

However, validation only proves that properties are present and satisfy declared constraints. It does not prove an API key is valid or an endpoint actually serves the right service. Those must be checked at the appropriate integration layer or health check.

## 6. Separating Logic Tests from Configuration Tests

A test suite can be divided by the evidence it needs to produce:

| Test Type | Profile/Beans Used | What It Proves |
|---|---|---|
| Unit test | No Spring context needed; mock dependencies | Business logic |
| Service integration test | Test context and controlled mock dependencies | Coordination between a service and related components |
| Production profile contract test | Loads production or production-like profile; overrides only safe boundaries | Production properties, profiles, beans, and conditions |
| Adapter integration test | Real adapter with mock server or container | HTTP, SQL, serialization, timeouts, and retries |
| Deployment validation | Manifests, env, secret references of the deployment | Actual configuration attached to the workload |
| Staging smoke test | Staging configuration close to production | Application boots and integrates in a near-production environment |

Do not try to turn a unit test into a configuration test merely by adding `@SpringBootTest`. Nor should you call a test a production configuration test if it has replaced all important beans and properties with test values.

Each test should clearly state what is kept real, what is simulated, and the limits of its conclusions.

## 7. Verifying That the Production Profile Is Properly Activated

A separate issue is that an application may be packaged with `application-prod.yml` yet fail to activate the `prod` profile when deployed.

You can verify active profiles in a test context:

~~~java
@SpringBootTest
@ActiveProfiles("prod")
class ActiveProductionProfileTest {

    @Autowired
    private Environment environment;

    @Test
    void shouldActivateProductionProfile() {
        assertTrue(environment.acceptsProfiles(Profiles.of("prod")));
    }
}
~~~

This test proves the test context activated the `prod` profile per the annotation. It does not prove the actual deployment manifest sets `SPRING_PROFILES_ACTIVE=prod`.

Add deployment configuration checks:

- Check environment variables or launch arguments declared in manifests.
- Check that the profile is passed into the right container or process.
- Check whether default profiles could accidentally override or add unintended profiles.
- Check that startup logs show only active profile names, without printing secrets.
- Verify the runtime environment in staging after deploying.

If profiles are configured from multiple sources, determine the precedence order and final result in the real workload.

## 8. Checking Bean Registration Conditions Without Accidentally Replacing Production Beans

Spring Boot often registers beans conditionally:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "payment",
        name = "enabled",
        havingValue = "true"
)
PaymentGateway paymentGateway(PaymentClient client) {
    return new HttpPaymentGateway(client);
}
~~~

If a test sets `payment.enabled=false`, the `PaymentGateway` bean is not created. If the test then uses `@MockBean` to supply `PaymentGateway`, the test can pass even if production configuration fails to register the real adapter.

A configuration contract test should verify critical conditions:

~~~java
@SpringBootTest
@ActiveProfiles("prod")
class ProductionPaymentBeanTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void shouldRegisterProductionPaymentGateway() {
        assertThat(context)
                .hasSingleBean(PaymentGateway.class);

        assertThat(context.getBean(PaymentGateway.class))
                .isInstanceOf(HttpPaymentGateway.class);
    }
}
~~~

This example is appropriate only when the test context is configured not to call production services at startup. If the bean opens connections upon creation, replace the transport with a mock server or use a scoped test context that verifies only bean wiring.

Do not add `@MockBean PaymentGateway` to this test itself, because then the test no longer verifies that the production adapter is registered.

You can use `ApplicationContextRunner` for standalone conditional configurations. When you need to verify profiles, properties, and beans of the complete application, use a test context matching the real configuration.

## 9. Do Not Let Test Properties Override Configuration Under Verification

A helpful organizational practice is categorizing properties by goal:

~~~text
Production configuration to verify
    |
    +-- payment.enabled
    +-- payment.connect-timeout
    +-- payment.read-timeout
    +-- payment.retry.max-attempts
    +-- payment.tls.enabled

Dependencies replaced for safe testing
    |
    +-- spring.datasource.url
    +-- spring.datasource.username
    +-- spring.datasource.password
    +-- payment.base-url (when testing business settings,
         but not testing the production endpoint)
    +-- payment.api-key (placeholder when not testing secrets)
~~~

Create a scope table for each test suite:

| Property | Allowed to Override in Tests? | Reason |
|---|---|---|
| `payment.connect-timeout` | No in production profile verification tests | The production value is the subject under verification |
| `payment.retry.max-attempts` | No in production retry policy tests | Must detect misconfiguration |
| `spring.datasource.url` | Yes | Use a container database instead of production |
| `spring.datasource.password` | Yes | Use test database credentials |
| `payment.base-url` | Yes in adapter tests | Point to a mock server to avoid calling real services |
| `payment.api-key` | Only when tests are not verifying secrets | Placeholders do not prove production secrets exist |
| `payment.enabled` | No in conditional bean verification tests | Must verify production beans are registered |

If a property is both a dependency endpoint and the subject under test, split the tests. For instance, one test verifies the production endpoint binds properly from packaged configuration; another adapter test uses a mock server to test the HTTP client. Do not override the endpoint and then use the result to conclude the production endpoint is correct.

## 10. Using Configuration Sources Similar to the Deployment Environment

Another reason tests fail to reflect production is that tests read only configuration files in source code, while production receives configuration from external systems.

For example, a production workload might receive:

~~~text
SPRING_PROFILES_ACTIVE=prod
PAYMENT_API_URL=https://payments.example.com
PAYMENT_API_KEY=<secret injected from secret manager>
SPRING_DATASOURCE_URL=<production database endpoint>
~~~

If CI runs tests solely against `application-prod.yml` in the repository, it does not prove that deployment manifests attach the right environment variables or secret references.

Check layer by layer:

**Source/configuration artifact layer**

- Are `application.yml` and `application-prod.yml` packaged?
- Do required keys have the exact names and data types?
- Do placeholders point to the right environment variable names?
- Are profile-specific configurations placed in the right locations?

**Deployment manifest layer**

- Does the workload activate the right profile?
- Are environment variables passed into the container?
- Do secret references have the right name, namespace, and key?
- Are ConfigMaps or config stores mounted/imported correctly?
- Are values overridden by charts, manifests, or command-line arguments?

**Runtime layer**

- Does the `ApplicationContext` start successfully?
- Do required beans exist?
- Are bound values within valid ranges?
- Do staging connections succeed?
- Do health indicators accurately reflect integration status?

Source code tests and deployment checks complement each other. No single JUnit annotation can replace verifying manifests and the real environment.

## 11. Be Careful with @SpringBootTest and @ActiveProfiles("prod")

A test like the following can start many application components:

~~~java
@SpringBootTest
@ActiveProfiles("prod")
class ProductionProfileContextTest {
}
~~~

If `application-prod.yml` configures production databases, message brokers, schedulers, or APIs, the context may initialize the corresponding beans. Some beans may open connections immediately upon initialization or run startup tasks.

Therefore:

- Do not run tests with real production connection details on developer machines or normal CI.
- Do not assume merely loading the `prod` profile will produce no side effects.
- Do not use the production profile for integration tests without first isolating external dependencies.
- Disable or replace startup tasks with side effects appropriately, while keeping the configuration under verification intact.
- If you only need to verify properties, use a minimal context or configuration reading/validation tools instead of booting the whole application.
- If you need to verify the full context, use a staging or production-like environment with safe dependencies.

You can create a separate `production-like` profile, but be clear about what is shared and what is overridden. If a `production-like` profile overrides all important production properties, it can create the same false confidence as a `test` profile.

A good convention is keeping the same business configurations and bean conditions, while replacing external endpoints/credentials with test resources. Explicitly list replaced properties and do not use that test to validate the replaced values.

## 12. Inspecting Property Values and Origins

When a test fails or a value is unexpected, find out which property source provides the key.

You can print property source names and check only for key presence:

~~~java
@Autowired
private ConfigurableEnvironment environment;

@Test
void shouldInspectPaymentPropertySource() {
    String key = "payment.connect-timeout";

    for (PropertySource<?> source : environment.getPropertySources()) {
        if (source.containsProperty(key)) {
            System.out.println(
                    source.getName() + " provides " + key
            );
        }
    }
}
~~~

This example prints only the source name and key name, not the value. This helps diagnose overridden properties.

In Spring Boot, several property sources support origin metadata to trace the file and location providing a property. You can use `OriginLookup` or appropriate Actuator tools in secured environments. Do not expose `env`/`configprops` endpoints publicly in production without access control and secret sanitization.

When reporting configuration errors, display only the key, source, and validity status. Do not print passwords, API keys, tokens, or secret contents.

## 13. Failing Fast on Invalid Production Configuration

Critical configuration should be validated immediately when the context initializes rather than letting errors appear when a user performs a rare action.

Example:

~~~java
@ConfigurationProperties(prefix = "payment")
@Validated
public record PaymentProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Min(1) int maxAttempts,
        @NotBlank String apiKey
) {
}
~~~

Register the properties:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
class PaymentConfiguration {
}
~~~

Business constraints can be added with custom validators, for example:

- Timeouts must be greater than zero.
- `maxAttempts` is within the allowed range.
- `baseUrl` must use HTTPS in the production profile.
- Retries must not be enabled for non-idempotent operations if the system lacks idempotency keys.
- A required feature flag must be enabled in the production profile.
- Queue or topic names must follow deployment conventions.

Validation should reflect the real contract, avoiding brittle checks for values that only happen to hold in one environment.

For secrets, verify only presence and non-emptiness if required. Do not log contents. Verifying whether a secret is valid with a provider should be done through a controlled integration or smoke test, not by printing values for debugging.

## 14. Practical Workflow to Prevent Test Configuration from Masking Production Errors

You can structure the workflow into these steps:

1. **Identify critical configuration.** List the properties, profiles, bean conditions, and secret references production needs.
2. **Classify properties.** Mark which values are subjects under test and which are merely external dependencies to replace for testing.
3. **Keep properties under test intact.** Do not reset them in `@TestPropertySource`, `@SpringBootTest(properties)`, or `@DynamicPropertySource`.
4. **Separate tests by purpose.** Unit tests check logic; adapter tests check communication; configuration contract tests check profiles/properties/beans; deployment validation checks manifests and secret references.
5. **Use safe dependencies.** Database containers, mock HTTP servers, and fake services keep tests from calling production.
6. **Test invalid configuration cases too.** Missing required properties, wrong types, inactive profiles, wrong feature flags, or unregistered beans should produce clear errors.
7. **Verify deployment artifacts.** Check packaged configuration and environment variables/secret references attached to workloads.
8. **Run smoke tests in staging.** Verify context startup, connections, and health indicators in a near-production environment.
9. **Keep logs safe.** Log only keys, sources, and binding errors; never print secrets.
10. **Document test limitations.** State which properties were replaced and what conclusions cannot be drawn from the test.

This workflow ensures tests produce evidence within the right scope. Tests do not need real production credentials to catch most structural and binding bugs, yet deployment must still verify values supplied by the real environment.

## 15. Example Test Strategy for Payment Configuration

Suppose an application has three configuration groups:

~~~yaml
# application.yml
payment:
  enabled: false
  connect-timeout: 2s
  read-timeout: 5s
  retry:
    max-attempts: 1
~~~

~~~yaml
# application-prod.yml
payment:
  enabled: true
  base-url: ${PAYMENT_API_URL}
  api-key: ${PAYMENT_API_KEY}
  retry:
    max-attempts: 3
~~~

You can design multiple tests:

**Unit tests for business logic**

- Mock `PaymentGateway`.
- Verify orders succeed or are rejected.
- Do not test production URLs.

**Adapter tests**

- Instantiate the real `HttpPaymentGateway`.
- Use a mock HTTP server.
- Verify request path, headers, timeouts, and response mapping.
- Pointing the URL to the mock server is an intentional override.

**Production profile contract tests**

- Load `application-prod.yml`.
- Do not override `payment.enabled`, timeouts, or `retry.max-attempts`.
- Provide a placeholder for the API key if needed for binding, without testing secrets.
- Verify the `prod` profile, bean conditions, and business configuration values.
- Do not open connections to production payment services.

**Deployment validation**

- Verify manifests activate `prod`.
- Verify `PAYMENT_API_URL` is supplied.
- Verify `PAYMENT_API_KEY` references the right secret.
- Do not read or print secret values in test reports.

**Staging smoke tests**

- Start the application using staging configuration.
- Check health and connectivity with the sandbox payment provider.
- Verify test requests receive valid responses.

When a test in the unit or adapter group passes, do not conclude the production profile is correct. When a configuration contract test passes, do not conclude the production secret is valid or the payment provider is operational. Each test answers only the question within its designed scope.

## 16. Questions to Ask When Reading an Existing Test

When reviewing Spring tests, examine:

- Which profiles does the test activate?
- Which `application-{profile}.yml` files are loaded?
- Are there `@TestPropertySource` or `properties` in `@SpringBootTest`?
- Does `@DynamicPropertySource` override URLs or credentials?
- Are `@MockBean`, `@Primary`, or `@TestConfiguration` replacing production beans?
- Which values are critical `@ConditionalOnProperty` conditions being evaluated with?
- Which properties are the subjects under verification, and which are merely test dependencies?
- Does the test accidentally disable required security, messaging, payment, or scheduler features?
- Are deployment manifests and secret references checked in another step?
- If a production property is missing, which test will fail?

If these questions cannot be answered, a passing result is not enough to assert that production configuration is protected.

## 17. Conclusion

Test configuration helps create a stable, fast, and safe environment. Yet every property, profile, or replacement bean can change what a test is actually verifying.

Distinguish clearly:

- Test profiles prove the application runs with test configuration.
- Integration tests prove real components collaborate within the chosen boundaries.
- Production profile contract tests prove production properties and beans load in a test context, with overrides transparently declared.
- Deployment validation proves manifests, environment variables, and secret references are attached to workloads properly.
- Staging smoke tests prove the application starts and integrates in a near-production environment.

Do not use test values to replace properties currently under verification. Replace external dependencies only when isolation is needed, document test limitations clearly, and verify deployment-supplied configuration separately. When property sources and test boundaries are explicit, passing tests reflect the level of confidence the team genuinely needs.


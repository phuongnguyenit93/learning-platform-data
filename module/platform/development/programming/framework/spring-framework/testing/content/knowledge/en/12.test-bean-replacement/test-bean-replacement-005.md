# Selecting Beans by Type, Name, and Qualifier

In Spring, multiple beans can implement the same interface or share the same type. For example, a payment application might register `CardPaymentGateway`, `BankTransferGateway`, and `WalletPaymentGateway`, all implementing `PaymentGateway`. When a service requests a `PaymentGateway`, Spring needs to determine which bean to inject.

In testing, the same issue arises when you need to replace the exact right bean with a mock or spy. If a test replaces the wrong implementation, the service may still call the real bean; if multiple beans of the same type exist without specifying the target, Spring can fail because it cannot disambiguate the candidate.

To select a bean accurately, you need to understand three commonly used pieces of information:

- **Type:** the class or interface type required by the dependency.
- **Name (bean name):** the identifier of the bean in the ApplicationContext.
- **Qualifier:** an additional label or criterion to narrow down the matching group of beans.

Spring typically finds candidates by type first, then applies qualifiers and precedence rules. The bean name can be used as a selection criterion in certain situations. Annotations such as `@Primary`, `@Fallback`, `@Qualifier`, `@Autowired`, and `@Resource` express that intent. For tests, `@MockitoBean` and `@MockitoSpyBean` use the same type, name, and qualifier information to identify the bean to replace or observe.

## 1. Why Can One Type Have Multiple Beans?

An interface describes a shared contract, while an application may have multiple implementations for different environments or methods.

Example:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentCommand command);
}
~~~

Two implementations:

~~~java
@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Send request to the card payment gateway.
        return PaymentResult.approved();
    }
}
~~~

~~~java
@Component("bankGateway")
public class BankTransferGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Create a bank transfer request.
        return PaymentResult.pending();
    }
}
~~~

A service declares its dependency only by the interface:

~~~java
@Service
public class PaymentService {

    private final PaymentGateway gateway;

    public PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public PaymentResult pay(PaymentCommand command) {
        return gateway.charge(command);
    }
}
~~~

When Spring creates `PaymentService`, two beans satisfy the `PaymentGateway` type. Without additional information to choose between them, Spring cannot automatically decide which implementation is right and may throw `NoUniqueBeanDefinitionException`.

This is not a flaw of interfaces. Having multiple implementations of the same type is normal design. The configuration simply needs to express clearly which service uses which implementation.

## 2. Bean Type, Bean Name, and Alias

### Selecting by Type

Type is the primary criterion when Spring resolves dependencies. An injection point declaring `PaymentGateway` can receive a bean registered as a class implementing `PaymentGateway`, or a bean factory method with a compatible return type.

Example:

~~~java
@Bean
PaymentGateway cardGateway() {
    return new CardPaymentGateway();
}
~~~

This bean has an actual type of `CardPaymentGateway` and a declared type of `PaymentGateway`. Spring can find this bean when a dependency requests `PaymentGateway`.

If there is only one matching candidate, injection by type is usually sufficient:

~~~java
@Autowired
private PaymentGateway paymentGateway;
~~~

When multiple candidates share the same type, you need to narrow down the choice with a qualifier, name, or precedence rule.

### Bean Name

Every bean registered in a `BeanFactory` has a primary name. With component scanning, the default name is usually derived from the class name according to Spring's bean naming rules. You can specify a name explicitly:

~~~java
@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {
}
~~~

With `@Bean`, the default name is the factory method name:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    PaymentGateway bankGateway() {
        return new BankTransferGateway();
    }
}
~~~

In this example, the default bean name is `bankGateway`. You can declare a name or aliases:

~~~java
@Bean(name = {"bankGateway", "primaryBankGateway"})
PaymentGateway bankGateway() {
    return new BankTransferGateway();
}
~~~

Both the primary name and aliases can be used to look up the bean in the context. However, when designing injection, prefer a single meaningful, consistent name rather than creating unnecessary aliases.

### Direct Lookup by Name

When you need to retrieve a bean by name, you can use `ApplicationContext`:

~~~java
PaymentGateway gateway =
        applicationContext.getBean("bankGateway", PaymentGateway.class);
~~~

This approach requires knowing the bean name at the call site. It suits certain dynamic selection mechanisms, whereas in ordinary application code, constructor injection by type and qualifier is usually easier to test.

Do not call `getBean` by name in every service just to avoid multiple-candidate errors. Doing so hides dependencies inside method bodies and prevents Spring from validating configuration early during bean creation.

## 3. `@Qualifier`: Narrowing Candidates by Label

`@Qualifier` is used alongside type-based injection to specify the matching subset of beans.

You can attach a qualifier to a bean:

~~~java
@Component
@Qualifier("card")
public class CardPaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component
@Qualifier("bank")
public class BankTransferGateway implements PaymentGateway {
}
~~~

And select it when injecting:

~~~java
@Service
public class CardCheckoutService {

    private final PaymentGateway gateway;

    public CardCheckoutService(
            @Qualifier("card") PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }
}
~~~

Spring first finds beans compatible with the `PaymentGateway` type, and then the `card` qualifier narrows the candidate set. If only one candidate remains, that bean is injected.

The value of `@Qualifier` is generally treated as a semantic label. It does not have to match the bean name, though Spring can use the bean name as a fallback when matching qualifiers in appropriate cases. Think of a qualifier as describing the role of the dependency, such as `card`, `bank`, `remote`, or `local`.

### A Qualifier Does Not Have to Be the Bean Name

You can assign a qualifier different from the bean name:

~~~java
@Component("stripeGateway")
@Qualifier("externalCard")
public class StripePaymentGateway implements PaymentGateway {
}
~~~

Injection:

~~~java
public CheckoutService(
        @Qualifier("externalCard") PaymentGateway gateway
) {
    this.gateway = gateway;
}
~~~

The bean name is `stripeGateway`, while the qualifier is `externalCard`. This lets the code express the role the service requires, while the bean name reflects the implementation or provider.

### Using Typed Custom Qualifiers

If a qualifier is used in many places, you can create a custom annotation:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.METHOD,
        ElementType.TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface RemotePayment {
}
~~~

Annotate the bean:

~~~java
@Component
@RemotePayment
public class RemotePaymentGateway implements PaymentGateway {
}
~~~

Inject the bean:

~~~java
public CheckoutService(
        @RemotePayment PaymentGateway gateway
) {
    this.gateway = gateway;
}
~~~

A custom annotation avoids scattering raw qualifier strings across the codebase and makes the dependency's meaning clearer. You can add attributes to a custom qualifier if you need to distinguish multiple values, such as region or tenant. In that case, the attribute values also participate in candidate matching.

## 4. How Does Spring Resolve Dependencies?

When Spring encounters a single-valued injection point, it needs to find one candidate matching the dependency's type and metadata.

You can think of the process in broad steps:

1. Find beans with a type compatible with the dependency.
2. Apply qualifiers to eliminate candidates that do not meet the criteria.
3. If multiple candidates remain, consider precedence rules such as `@Primary`, `@Fallback`, or `@Priority`.
4. In some cases, the dependency name or parameter name can help select a bean with a matching name.
5. If multiple tied candidates still remain, Spring fails because it cannot determine a unique bean.

This is a conceptual model for reading configurations and diagnosing issues. The actual algorithm has additional details depending on dependency type, metadata, and Spring version.

### `@Primary` Chooses the Default Candidate

Mark a bean with `@Primary` so Spring prefers it when multiple candidates share the same type and the injection point does not specify another qualifier:

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component
public class BankTransferGateway implements PaymentGateway {
}
~~~

The following dependency receives `CardPaymentGateway`:

~~~java
public PaymentService(PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

`@Primary` is useful when an application has a default implementation. However, it does not remove other beans from the context. An injection point with a qualifier matching another bean can still select that other bean.

If multiple candidates are marked `@Primary` for the same type and qualifier, Spring still cannot determine a single unique bean.

### `@Fallback` in Spring Framework 6.2 and Later

Spring Framework 6.2 added `@Fallback` to mark a lower-priority candidate. When there is a normal candidate and a fallback candidate for the same dependency, the normal candidate takes precedence.

Example:

~~~java
@Component
@Fallback
public class DefaultPaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component
public class ProductionPaymentGateway implements PaymentGateway {
}
~~~

When injecting `PaymentGateway` without another qualifier, `ProductionPaymentGateway` is selected because `DefaultPaymentGateway` is a fallback.

`@Fallback` is useful when you want to supply a backup implementation without marking every primary implementation with `@Primary`. If all candidates are fallbacks or multiple tied primary candidates remain, the dependency can still be ambiguous.

### `@Priority` and Candidate Ordering

In some cases when selecting one bean among multiple candidates, priority metadata can participate in resolution. Spring also supports bean ordering in collection injections. Distinguish carefully:

- `@Priority` can be used when selecting a single-valued candidate according to Spring's rules.
- `@Order` or `Ordered` typically controls the order of beans when injecting a collection or when the framework sorts them.
- Order in a `List` does not mean the first element automatically becomes the default bean for every single-valued dependency.

If a dependency requires a specific implementation for business reasons, an explicit qualifier or name usually expresses intent better than relying on ordering.

### Parameter Name and Field Name as Fallback Criteria

In certain situations, when multiple candidates share the same type and qualifiers/primary are insufficient to resolve them, Spring can use the dependency name to look for a bean with a matching name.

Example:

~~~java
@Service
public class PaymentService {

    private final PaymentGateway bankGateway;

    public PaymentService(PaymentGateway bankGateway) {
        this.bankGateway = bankGateway;
    }
}
~~~

If a bean named `bankGateway` exists, the parameter name can help Spring select that candidate via the corresponding fallback mechanism. For constructor parameters, parameter names must be preserved in bytecode; Java projects typically enable the `-parameters` compiler option so Spring can read names reliably. Field names can be read directly by Spring at field injection points.

Do not rely on name fallback when the dependency's meaning is critical. Using `@Qualifier` explicitly makes the code easier to read and less dependent on compiler configuration.

## 5. Distinguishing `@Autowired`, `@Qualifier`, and `@Resource`

These three annotations often appear together, yet they express different intents.

| Annotation | Primary Selection | Role |
|---|---|---|
| `@Autowired` | By type | Asks Spring to inject a matching dependency |
| `@Qualifier` | Narrows candidates | Selects beans with a matching label/metadata among the same type |
| `@Resource` | By name first | Injects a resource by bean name; can derive the name from the field or setter if unspecified |

### `@Autowired` by Type

~~~java
@Autowired
private PaymentGateway gateway;
~~~

Spring looks for a bean compatible with `PaymentGateway`. If only one candidate exists, injection is unambiguous. If multiple candidates exist, additional metadata is needed to resolve them.

### `@Autowired` Combined with `@Qualifier`

~~~java
@Autowired
@Qualifier("bank")
private PaymentGateway gateway;
~~~

This is type-based injection with a qualifier. In constructor injection, `@Qualifier` can be placed on the parameter:

~~~java
public PaymentService(
        @Qualifier("bank") PaymentGateway gateway
) {
    this.gateway = gateway;
}
~~~

With a single constructor, Spring usually does not require `@Autowired` on the constructor. `@Qualifier` is still needed to narrow down candidates.

### `@Resource` by Name

`@Resource` belongs to Jakarta Annotations in modern Spring versions. When `name` is specified, it looks up the resource by that name:

~~~java
@Resource(name = "bankGateway")
private PaymentGateway gateway;
~~~

If `name` is omitted, the field or property name can be used as the resource name according to `@Resource` rules. Therefore, `@Resource` often expresses name-based resource selection more explicitly than `@Autowired`.

If the requirement is to select a bean by role from a group of implementations sharing an interface, `@Autowired` with `@Qualifier` usually fits Spring's type-first model well. If the requirement is to look up a resource by a specific name, `@Resource(name = "...")` is a suitable option.

## 6. Injecting Multiple Beans of the Same Type

Not every dependency requires choosing a single bean. If a service needs to invoke all implementations, Spring can inject a collection.

### `List` or Array

~~~java
@Service
public class PaymentGatewayRegistry {

    private final List<PaymentGateway> gateways;

    public PaymentGatewayRegistry(List<PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public List<PaymentGateway> all() {
        return gateways;
    }
}
~~~

Spring places matching beans into the `List`. If `@Order` or `Ordered` is present, the collection order can be sorted according to that metadata.

### `Map` Keyed by Bean Name

~~~java
@Service
public class PaymentGatewayRegistry {

    private final Map<String, PaymentGateway> gateways;

    public PaymentGatewayRegistry(
            Map<String, PaymentGateway> gateways
    ) {
        this.gateways = gateways;
    }

    public PaymentGateway get(String name) {
        return gateways.get(name);
    }
}
~~~

With `Map` injection, the key is the bean name and the value is the bean instance. This works well when the application maintains a registry choosing implementations by a controlled key.

If you only need a single implementation, do not inject an entire `Map` and look up an element inside the service just to work around `NoUniqueBeanDefinitionException`. Express the specific dependency with a qualifier instead.

### `ObjectProvider` When Conditional Lookup Is Needed

`ObjectProvider` allows deferring bean retrieval or handling cases where candidates may or may not exist:

~~~java
public class OptionalPaymentService {

    private final ObjectProvider<PaymentGateway> gateways;

    public OptionalPaymentService(
            ObjectProvider<PaymentGateway> gateways
    ) {
        this.gateways = gateways;
    }

    public PaymentGateway gatewayOrNull() {
        return gateways.getIfAvailable();
    }
}
~~~

`ObjectProvider` offers APIs such as `getIfAvailable`, `getIfUnique`, and `stream`. It is useful when a dependency is genuinely optional or resolved at runtime. If the application always requires exactly one bean, direct injection usually catches configuration errors earlier.

## 7. Selecting Beans When Replacing Them in Tests

In a Spring test, simply having a Mockito mock field is not enough to replace the bean that a service uses inside the `ApplicationContext`.

Example:

~~~java
@ExtendWith(MockitoExtension.class)
class PaymentServiceUnitTest {

    @Mock
    PaymentGateway gateway;

    private PaymentService service;

    @BeforeEach
    void setUp() {
        service = new PaymentService(gateway);
    }
}
~~~

This is a plain unit test: the test instantiates `PaymentService` itself and passes the mock to its constructor.

If `PaymentService` is created by Spring inside an `ApplicationContext`, a mock field managed by `MockitoExtension` does not automatically replace the `PaymentGateway` bean in the context. When you need to replace a bean in the context, Spring Framework provides `@MockitoBean`; when you need to observe a real bean, it provides `@MockitoSpyBean`.

These bean override annotations are provided in Spring Framework 6.2 and later. For Spring Boot projects, the older `@MockBean` was deprecated starting in Spring Boot 3.4 in favor of Spring Framework's `@MockitoBean` mechanism.

### `@MockitoBean` Selecting by Type

Example test using a Spring context:

~~~java
@SpringJUnitConfig(PaymentTestConfiguration.class)
class PaymentServiceSpringTest {

    @MockitoBean
    private PaymentGateway gateway;

    @Autowired
    private PaymentService paymentService;

    @Test
    void returnsApprovedResult() {
        when(gateway.charge(any()))
                .thenReturn(PaymentResult.approved());

        PaymentResult result =
                paymentService.pay(new PaymentCommand("ORDER-01"));

        assertTrue(result.approved());
        verify(gateway).charge(any());
    }
}
~~~

Here:

- The field type is `PaymentGateway`, so Spring uses that type to find the bean to override.
- `@MockitoBean` creates a Mockito mock and registers it in the `ApplicationContext` via the bean override mechanism.
- The field in the test receives the same mock so the test can stub and verify.
- `PaymentService` in the context receives the replacement bean when it is created or resolves its dependencies from the context.

If there is only one `PaymentGateway` bean, the type alone is enough to identify the target.

### When Multiple Beans Share the Same Type: Use `@Qualifier`

Suppose the context contains `cardGateway` and `bankGateway`. The test only wants to replace `bankGateway`:

~~~java
@SpringJUnitConfig(PaymentTestConfiguration.class)
class BankPaymentServiceTest {

    @MockitoBean
    @Qualifier("bank")
    private PaymentGateway gateway;

    @Autowired
    private BankPaymentService bankPaymentService;

    @Test
    void usesMockedBankGateway() {
        when(gateway.charge(any()))
                .thenReturn(PaymentResult.pending());

        PaymentResult result =
                bankPaymentService.pay(new PaymentCommand("ORDER-02"));

        assertEquals(PaymentStatus.PENDING, result.status());
        verify(gateway).charge(any());
    }
}
~~~

The qualifier on the field helps Spring narrow down candidates based on bean metadata. If the `bankGateway` bean is annotated with `@Qualifier("bank")`, the test targets that exact implementation.

You can use a custom qualifier:

~~~java
@MockitoBean
@RemotePayment
private PaymentGateway gateway;
~~~

The requirement is that the bean to replace also carries the corresponding qualifier.

### Using the Field Name as a Fallback Qualifier

If multiple beans share the same type, the field name on `@MockitoBean` can be used as a fallback qualifier. For example, if the context has a bean named `bankGateway`:

~~~java
@MockitoBean
private PaymentGateway bankGateway;
~~~

The field name `bankGateway` helps identify the bean to override when other qualifiers do not provide clearer information.

Although this fallback mechanism is convenient, tests should use meaningful field names and keep them stable. When bean selection is an important decision or the field name does not match the bean name, declare `@Qualifier` explicitly.

### Specifying the Bean Name Directly

`@MockitoBean` supports the `name` attribute to specify the exact bean to replace:

~~~java
@MockitoBean(name = "bankGateway")
private PaymentGateway gateway;
~~~

`name` can be used alongside the field type. This is useful when a test field has a generic name like `gateway` while the context contains multiple `PaymentGateway` beans.

Another approach is placing `@Qualifier` on the field:

~~~java
@MockitoBean
@Qualifier("bankGateway")
private PaymentGateway gateway;
~~~

Pick one style that clearly expresses intent and keep it consistent across the test suite. If the bean has a semantic qualifier like `bank`, using that qualifier typically makes the test less tied to implementation names. If you need to replace an exact bean by technical identifier, `name` is the direct choice.

## 8. Does `@MockitoBean` Create a New Bean If No Candidate Is Found?

By default, `@MockitoBean` can create a mock bean if the context does not yet have a matching bean to replace. That behavior is useful when a test slice needs to supply a dependency that the slice configuration does not create.

However, if the goal is to prove that an existing bean was replaced, having the annotation silently create a new bean can mask configuration errors or selecting the wrong context.

You can enable `enforceOverride`:

~~~java
@MockitoBean(
        name = "bankGateway",
        enforceOverride = true
)
private PaymentGateway gateway;
~~~

With `enforceOverride = true`, the test requires the target bean to already exist to be replaced. If no matching bean is found, Spring fails when creating the context.

You should use `enforceOverride` when:

- The test needs to verify that a specific bean is configured in the application.
- Multiple implementations of the same type exist and picking the wrong one is a risk.
- You want to catch misspelled bean names or qualifiers early.
- The test verifies the application's integration configuration.

If a test slice intentionally omits the real implementation and needs a new mock added, the default create-if-missing behavior may be what you want.

## 9. Replacing Beans by Type at the Test Class Level

`@MockitoBean` can be declared at the class level with the `types` attribute to specify the types to replace:

~~~java
@SpringJUnitConfig(PaymentTestConfiguration.class)
@MockitoBean(types = NotificationClient.class)
class NotificationServiceTest {
    // Tests
}
~~~

Class-level declarations are useful when you want to register mocks for one or more types without needing separate mock fields. You can use its repeatable form to declare multiple overrides.

When a type has multiple bean candidates, additional information is needed to identify the exact bean. In cases needing a specific qualifier or name per dependency, field-level declarations with `@Qualifier` or `name` are usually easier to read and more direct.

When using type-level declarations for multiple types, check the `name` attribute and registration rules for your project's Spring Framework version. Do not assume a single name can describe multiple distinct beans of the same type.

## 10. `@MockitoSpyBean` and Selecting the Bean to Observe

`@MockitoSpyBean` creates a spy wrapping an existing bean so the test can invoke real behavior and observe interactions. Identifying the target bean also relies on type and qualifiers just like other bean overrides.

Example:

~~~java
@SpringJUnitConfig(PaymentTestConfiguration.class)
class BankGatewaySpyTest {

    @MockitoSpyBean
    @Qualifier("bank")
    private PaymentGateway bankGateway;

    @Autowired
    private PaymentService paymentService;

    @Test
    void observesBankGatewayCall() {
        paymentService.pay(new PaymentCommand("ORDER-03"));

        verify(bankGateway).charge(any());
    }
}
~~~

The spy preserves the real behavior of the selected bean unless the test stubs a specific method. Therefore, account for side effects of real methods such as network calls, database writes, or message publishing.

`@MockitoSpyBean` requires an existing bean to wrap. If the context has no matching bean, context creation fails. When you want to replace a dependency completely with a mock, `@MockitoBean` is usually more suitable.

If multiple beans share the same type, use `@Qualifier` or a clear field name to avoid spying on the wrong implementation.

## 11. Complete Example: Selecting the Right Implementation in Services and Tests

Suppose the application configuration registers two gateways:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    @Qualifier("card")
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @Qualifier("bank")
    PaymentGateway bankGateway() {
        return new BankTransferGateway();
    }

    @Bean
    PaymentService cardPaymentService(
            @Qualifier("card") PaymentGateway gateway
    ) {
        return new PaymentService(gateway);
    }

    @Bean
    PaymentService bankPaymentService(
            @Qualifier("bank") PaymentGateway gateway
    ) {
        return new PaymentService(gateway);
    }
}
~~~

The test replaces the exact bank gateway:

~~~java
@SpringJUnitConfig(PaymentConfiguration.class)
class BankPaymentServiceTest {

    @MockitoBean
    @Qualifier("bank")
    private PaymentGateway bankGateway;

    @Autowired
    private PaymentService bankPaymentService;

    @Test
    void delegatesToBankGateway() {
        when(bankGateway.charge(any()))
                .thenReturn(PaymentResult.pending());

        PaymentResult result =
                bankPaymentService.pay(new PaymentCommand("ORDER-10"));

        assertEquals(PaymentStatus.PENDING, result.status());
        verify(bankGateway).charge(any());
    }
}
~~~

The test replaces the exact candidate because both the bean definition and the injection point carry the `bank` qualifier. `CardPaymentGateway` remains a separate bean in the context and is not replaced by this mock.

If a test needs to verify that the card gateway is still the real implementation, it can look up the bean by qualifier in an appropriate test context. However, avoid checking too many wiring details in a test whose sole purpose is verifying `BankPaymentService` behavior.

## 12. Common Errors When Selecting Beans in Tests

### `NoUniqueBeanDefinitionException`

The cause is that multiple beans of the same type remain after Spring applies the available criteria, leaving no single unique candidate.

How to handle it:

- Add `@Qualifier` to the injection point.
- Mark the default implementation with `@Primary` if that reflects application policy.
- Use `@Fallback` for a backup implementation on Spring Framework 6.2 or later.
- Use clear dependency names when name fallback is appropriate.
- Check whether component scanning accidentally registered an implementation twice.

### `NoSuchBeanDefinitionException` When Using a Qualifier

A bean may exist without the qualifier required by the test, or the test may be using a context slice that does not load that bean.

Check annotations on the bean, qualifier names, package scanning, and test configuration. If the goal is to replace an existing bean, use `enforceOverride` to catch cases where no replacement candidate exists.

### Mock Is Created, Yet the Service Still Calls the Real Implementation

A `@Mock` field from `MockitoExtension` does not automatically replace a bean in the `ApplicationContext`. Use `@MockitoBean` or an appropriate bean override mechanism to register the mock in the context.

If `@MockitoBean` is already used, check whether the qualifier/name selects the exact bean injected into the service. Another service might be using a different implementation of the same type.

### `@MockitoBean` Replaces the Wrong Bean of the Same Type

When multiple candidates exist, type alone is not enough. Add `@Qualifier` to the field, use an explicit `name`, or match the field name to the bean name under the fallback mechanism.

Do not rely on `@Bean` declaration order or component scan order to determine which bean is replaced.

### `@MockitoBean` Unexpectedly Creates a New Bean

By default, the annotation can create a mock if no matching bean is found. If the test needs to confirm that the real bean was already configured, set `enforceOverride = true`.

### `@MockitoSpyBean` Cannot Find a Bean

A spy needs an existing bean to wrap. Check that the test context loads the right configuration and that a candidate matching the type/qualifier/name exists.

### Qualifier on Bean and Injection Point Do Not Match

Qualifiers are metadata. The value on the bean and at the injection point must be compatible. If using a custom qualifier, ensure the annotation is meta-annotated with `@Qualifier` and has `RUNTIME` retention.

### Confusing `@Primary` with `@Qualifier`

`@Primary` picks a default candidate within a matching group. `@Qualifier` narrows the group by label. If a service strictly requires the bank gateway, writing `@Qualifier("bank")` expresses that requirement better than hoping the bank gateway happens to be `@Primary`.

### Using Generic Field Names

A field named `gateway` may not help distinguish beans of the same type. Name it `bankGateway` or `cardGateway`, or add an explicit `@Qualifier`/`name` so the test is easy to understand.

## 13. How to Diagnose Which Candidate Spring Selects

When injection produces the wrong result, investigate in order:

1. Identify the dependency type at the injection point.
2. List the beans in the context with a compatible type.
3. Check bean names and aliases.
4. Check `@Qualifier` on the beans and the injection point.
5. Check `@Primary`, `@Fallback`, and priority metadata.
6. Check field/parameter names if Spring is using name fallback.
7. For test overrides, confirm `@MockitoBean`/`@MockitoSpyBean` targets the right candidate.
8. If the bean must exist, enable `enforceOverride` to prevent silent mock creation from hiding errors.
9. Verify the test uses the expected `ApplicationContext` or test slice.

You can inspect bean names and types in a context using:

~~~java
String[] names =
        applicationContext.getBeanNamesForType(PaymentGateway.class);

for (String name : names) {
    PaymentGateway gateway =
            applicationContext.getBean(name, PaymentGateway.class);

    System.out.println(name + " -> " + gateway.getClass().getName());
}
~~~

This is a useful diagnostic snippet when you need to see the actual candidates. Do not turn this lookup logic into a routine bean-selection pattern inside services when dependencies can be declared clearly via constructors.

## 14. When to Use Type, Name, or Qualifier?

| Situation | Appropriate Expression |
|---|---|
| Only one implementation of an interface | Inject by type |
| One default implementation and secondary implementations | `@Primary` or `@Fallback` |
| Service needs an implementation by business role | `@Qualifier` or custom qualifier |
| Need an exact bean with a specific identifier | `@Resource(name = ...)` or `@Qualifier`/`name` |
| Need to replace a bean in a Spring test, single candidate | `@MockitoBean` by type |
| Need to replace one of multiple beans of the same type | `@MockitoBean` with `@Qualifier` or `name` |
| Need to guarantee the target bean exists before replacing | `@MockitoBean(enforceOverride = true)` |
| Need to observe real bean behavior | `@MockitoSpyBean` with qualifier/name when needed |
| Need to use all implementations | `List`, array, or `Map` injection |

Several principles make configurations easier to follow:

- Use type to describe the dependency contract.
- Use qualifiers to describe the role or candidate group.
- Use bean names when you need to identify one exact bean.
- Use `@Primary` for application defaults, not as a substitute for qualifiers where specific business requirements exist.
- Use `@Fallback` for backup implementations if supported by your Spring version.
- In tests, select the target bean using the same metadata the application uses for injection.
- Enable `enforceOverride` when the test must prove an existing bean was replaced.
- Distinguish Mockito mock fields from mock beans registered in the `ApplicationContext`.

Selecting beans by type, name, and qualifier is both part of dependency injection and the foundation for replacing the right bean in Spring tests. When multiple implementations share the same type, qualifiers express the dependency's role, names identify specific beans, and precedence rules help Spring pick a default candidate. With `@MockitoBean` and `@MockitoSpyBean`, that same information determines exactly which bean is replaced or observed. Declaring targets clearly in both application configuration and tests helps prevent ambiguity errors, mocking the wrong implementation, and tests that accidentally continue calling real dependencies.


# proxyBeanMethods=true vs. false and Impact on the Used Instance

In Spring Boot, a configuration class often declares multiple beans using methods annotated with `@Bean`. One method might create a `Formatter`, another creates a `GreetingService`, and that service needs the formatter.

The critical question is: if the `greetingService()` method calls `formatter()` directly, does it receive the exact `Formatter` bean managed by Spring, or does it create another new object?

The answer depends on the `proxyBeanMethods` attribute of the `@Configuration` annotation:

- `proxyBeanMethods = true`: Spring enhances the configuration class with a CGLIB proxy to coordinate calls between `@Bean` methods. When one `@Bean` method invokes another `@Bean` method on the managed configuration instance, the call is routed through the container to return the bean according to its scope.
- `proxyBeanMethods = false`: Spring does not create a proxy for the configuration class merely to intercept `@Bean` method calls. A direct call between methods is a regular Java call; it can create a new object separate from the bean instance managed by the container.

The default for `@Configuration` is `proxyBeanMethods = true`. Choosing `false` does not stop Spring from managing beans and does not disable Dependency Injection. It only changes how **direct calls between `@Bean` methods inside the configuration class** are handled.

This lesson uses a small example to demonstrate the difference in object identity, then explains how to write configurations safely in both modes.

## 1. A @Bean Method Is a Spring Factory Method

Consider this configuration:

~~~java
@Configuration
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService() {
        return new GreetingService(messageFormatter());
    }
}
~~~

The two methods have specific roles:

- `messageFormatter()` provides a bean of type `MessageFormatter`.
- `greetingService()` provides a bean of type `GreetingService`.

Spring registers bean definitions from the configuration class metadata. When the container creates a bean, it invokes the corresponding factory method and manages the returned object.

However, inside `greetingService()` there is a Java call:

~~~java
messageFormatter()
~~~

This is the point to pay attention to. If that call is handled via a configuration proxy, Spring can return the managed `messageFormatter` bean. If it is not intercepted, Java simply executes the method body and creates an object according to the `new` statement inside it.

Consequently, the exact same code can lead to two different outcomes depending on `proxyBeanMethods`.

## 2. proxyBeanMethods=true: Full Configuration Mode

`@Configuration` defaults to `proxyBeanMethods = true`:

~~~java
@Configuration(proxyBeanMethods = true)
public class AppConfig {
    // @Bean methods
}
~~~

It can be written more concisely because `true` is the default:

~~~java
@Configuration
public class AppConfig {
    // @Bean methods
}
~~~

In this mode, Spring uses a CGLIB-based enhancement mechanism to generate a proxy subclass for the configuration class. The proxy intercepts eligible `@Bean` method calls, especially calls between bean methods within the same configuration class.

Example:

~~~java
@Configuration(proxyBeanMethods = true)
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        System.out.println("Create MessageFormatter");
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService() {
        System.out.println("Create GreetingService");
        return new GreetingService(messageFormatter());
    }
}
~~~

When Spring creates `greetingService` and executes `messageFormatter()` on the configuration proxy, the call is intercepted. The container looks up the `messageFormatter` bean and returns the managed instance according to the bean's scope.

With the default `singleton` scope:

~~~text
Spring container
      │
      ├── creates bean messageFormatter
      │         │
      │         ▼
      │   MessageFormatter #1
      │
      └── creates bean greetingService
                │
                └── calls messageFormatter()
                       │
                       ▼
                Configuration proxy intercepts
                       │
                       ▼
                Container returns MessageFormatter #1
~~~

Result: the `GreetingService` bean uses the exact same `MessageFormatter` instance provided by the container. There is no second singleton formatter created just because the configuration method was called again.

### 2.1. Why Is Proxying Needed?

In pure Java, calling a method:

~~~java
messageFormatter()
~~~

always executes the method body according to Java rules. With a CGLIB-enhanced configuration class, Spring can alter the behavior of calls on the proxy instance to perform a bean lookup in the container.

This mechanism ensures that calls between bean methods respect the lifecycle and scope of Spring-managed beans.

In other words, `proxyBeanMethods=true` lets `@Bean` methods call one another in a manner close to referencing an injected bean, even though the syntax inside the method is a direct Java call.

### 2.2. Conditions and Limitations of Configuration Proxying

Because Spring must generate a subclass with CGLIB:

- The configuration class must be subclassable; `final` classes are incompatible with full configuration proxying.
- Instance `@Bean` methods must be overridable/interceptable; do not declare such methods `private` or `final` if interception is needed.
- A call on a configuration object manually instantiated via `new AppConfig()` does not pass through the Spring-managed proxy.
- The proxy mechanism does not turn every Java call to any arbitrary method into a bean lookup; it focuses on eligible `@Bean` methods.

These constraints are why some configurations choose `proxyBeanMethods=false` when inter-bean method calls are unnecessary.

## 3. proxyBeanMethods=false: Lite Configuration Mode

When declaring:

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfig {
    // @Bean methods
}
~~~

Spring does not enhance the configuration class with CGLIB solely to intercept calls between `@Bean` methods.

Spring still:

- Discovers the configuration class.
- Registers bean definitions for the `@Bean` methods.
- Calls the factory methods to create the corresponding beans.
- Manages the returned instances according to their scope.
- Performs dependency injection and lifecycle callbacks for container-managed beans.

What changes is that a direct call from one method to another inside the configuration class becomes a **regular Java call**.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        System.out.println("Create MessageFormatter");
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService() {
        System.out.println("Create GreetingService");
        return new GreetingService(messageFormatter());
    }
}
~~~

When the container creates the `messageFormatter` bean, it calls the factory method and manages the returned object, say `MessageFormatter #1`.

When the container creates `greetingService`, the `greetingService()` method calls `messageFormatter()` directly like a normal Java method. The `new MessageFormatter()` statement runs again, creating `MessageFormatter #2`.

`GreetingService` receives `MessageFormatter #2`, while the `messageFormatter` bean managed by the container remains `MessageFormatter #1`.

~~~text
Spring container
      │
      ├── calls @Bean messageFormatter()
      │         │
      │         ▼
      │   MessageFormatter #1
      │   (managed bean)
      │
      └── calls @Bean greetingService()
                │
                └── directly calls messageFormatter()
                       │
                       ▼
                 Java executes method body
                       │
                       ▼
                MessageFormatter #2
                (directly created object)
                       │
                       ▼
                GreetingService uses #2
~~~

This is the most important difference of `proxyBeanMethods=false`: **the container still manages the bean created by the factory method, but direct calls between factory methods do not automatically retrieve the bean back from the container**.

## 4. Illustrating with Object Identity

To see the two modes clearly, let us define two simple classes.

`MessageFormatter.java`:

~~~java
public class MessageFormatter {
    public String format(String name) {
        return "Hello, " + name;
    }
}
~~~

`GreetingService.java`:

~~~java
public class GreetingService {
    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    public MessageFormatter formatter() {
        return formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = true) // Try changing to false
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService() {
        return new GreetingService(messageFormatter());
    }
}
~~~

Checking in the context:

~~~java
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {

    MessageFormatter beanFormatter =
            context.getBean(MessageFormatter.class);

    GreetingService service =
            context.getBean(GreetingService.class);

    System.out.println(
            beanFormatter == service.formatter()
    );
}
~~~

Expected output:

| Configuration | Comparison result | Meaning |
| --- | --- | --- |
| `proxyBeanMethods = true` | `true` | Service receives the same formatter bean instance |
| `proxyBeanMethods = false` | `false` | Direct call creates a formatter different from the bean in the context |

`==` compares the identity of two references, not the object contents. Two objects with identical data can still be two distinct instances.

This is an illustration for a simple configuration with default singleton scope and direct method calls as shown above. When other scopes, different factory methods, or other proxies are involved, the corresponding rules must also be analyzed.

## 5. The Safe Approach: Passing Dependencies via @Bean Method Parameters

If you want to use `proxyBeanMethods=false` while still ensuring beans receive container-managed dependencies, declare dependencies in the factory method parameters.

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService(
            MessageFormatter messageFormatter) {
        return new GreetingService(messageFormatter);
    }
}
~~~

Spring sees the `MessageFormatter messageFormatter` parameter and resolves the dependency through the container. It passes the managed `messageFormatter` bean into the factory method.

Flow:

~~~text
Spring creates bean messageFormatter
              │
              ▼
      MessageFormatter #1
              │
              │ container resolves parameter
              ▼
Spring calls greetingService(messageFormatter)
              │
              ▼
GreetingService receives #1
~~~

With this approach:

- No direct call to `messageFormatter()` is needed.
- No configuration proxy is needed to share dependencies.
- Beans are managed according to container scope.
- The configuration works properly whether `proxyBeanMethods=true` or `false`.
- Dependency relationships are expressed explicitly in the factory method signature.

This is the preferred style whenever a `@Bean` method needs another bean.

### 5.1. @Bean Method Parameters Support Qualifiers

If there are multiple beans of the same type, you can use `@Qualifier` on the parameter:

~~~java
@Bean
public GreetingService greetingService(
        @Qualifier("vietnameseFormatter")
        MessageFormatter formatter) {
    return new GreetingService(formatter);
}
~~~

The container selects the bean with the matching qualifier. This does not depend on whether the configuration class is proxied.

### 5.2. Multiple Dependencies Can Be Passed

~~~java
@Bean
public GreetingService greetingService(
        MessageFormatter formatter,
        GreetingRepository repository,
        Clock clock) {
    return new GreetingService(formatter, repository, clock);
}
~~~

`GreetingRepository` and `Clock` are assumed types that must be registered appropriately. Spring resolves each parameter as a dependency of the bean being created.

This lets the factory method act as a composition point: it receives container-managed dependencies and constructs the new object with them.

## 6. Comparing Both Modes in One Table

| Aspect | `proxyBeanMethods=true` | `proxyBeanMethods=false` |
| --- | --- | --- |
| Default value of `@Configuration` | Yes | No |
| Configuration class enhanced with CGLIB to intercept bean method calls | Yes | No |
| Direct call `otherBean()` from a `@Bean` method | Intercepted and looks up appropriate bean | Regular Java call |
| Guaranteed to receive same singleton on cross-bean method call | Yes, according to bean scope | Not guaranteed; usually creates a new object if method body uses `new` |
| Beans created by container calling factory method | Managed | Managed |
| Constructor/parameter injection | Yes | Yes |
| Dependencies via `@Bean` parameters | Yes | Yes |
| Suitable for configurations without cross-bean method calls | Usable | Very well suited |
| Requires configuration class enhancement | Yes | Not needed for inter-bean method interception |

What matters is not which mode "manages beans better." Both allow the container to manage bean definitions and instances. The difference lies in **method calls inside the configuration class**.

## 7. @Component with @Bean Methods Normally Runs in Lite Mode

`@Bean` methods do not only appear in `@Configuration` classes. Spring also allows declaring them in ordinary components.

Example:

~~~java
@Component
public class FormatterFactory {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }
}
~~~

The `FormatterFactory` class is not a full `@Configuration` class. The `@Bean` methods inside it are processed under lite configuration semantics; there is no configuration class proxy to intercept calls between bean methods.

If written as:

~~~java
@Component
public class FormatterFactory {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService() {
        return new GreetingService(messageFormatter());
    }
}
~~~

calling `messageFormatter()` inside `greetingService()` is a regular Java call. It may create a different object from the `messageFormatter` bean in the context.

It can be rewritten as:

~~~java
@Component
public class FormatterFactory {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService(
            MessageFormatter messageFormatter) {
        return new GreetingService(messageFormatter);
    }
}
~~~

Then the container resolves the parameter and supplies the right bean.

Note: `proxyBeanMethods` is an attribute of `@Configuration`. You cannot place that attribute on a regular `@Component` to ask Spring to intercept bean methods. If a class is simply a component containing factory methods, use method parameters to express dependencies.

## 8. Impact of Bean Scope

The earlier examples used the default `singleton` scope. However, Spring also supports other scopes such as `prototype` and web scopes.

In full configuration mode, when a `@Bean` method is called through the configuration proxy, the call is routed through the container. As a result, the container can apply the corresponding scope instead of directly running the method body.

Example:

~~~java
@Configuration(proxyBeanMethods = true)
public class PrototypeConfiguration {

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public TaskContext taskContext() {
        return new TaskContext();
    }

    @Bean
    public TaskRunner taskRunner() {
        return new TaskRunner(taskContext());
    }
}
~~~

In this example, `taskContext()` is intercepted and the container resolves the bean according to prototype scope. Each time the container needs to obtain a prototype bean, it can create a new instance.

However, if switched to `proxyBeanMethods=false` while still calling `taskContext()` directly inside `taskRunner()`, Java executes the method normally. The directly constructed object does not go through the container's scope resolution like a `getBean` call.

This does not apply only to singleton or prototype. A direct call in lite mode also bypasses the full bean creation pipeline, dependency injection, `BeanPostProcessor`s, and lifecycle callbacks for the object created outside the container.

### 8.1. Prototypes Injected into Singletons Require Special Attention

Even with constructor injection:

~~~java
@Bean
public TaskRunner taskRunner(TaskContext taskContext) {
    return new TaskRunner(taskContext);
}
~~~

if `TaskRunner` is a singleton and `TaskContext` is a prototype, the container normally resolves `TaskContext` once when creating the singleton `TaskRunner`. It does not automatically fetch a new prototype on every method call of the runner.

If a fresh instance is needed each time, consider `ObjectProvider<TaskContext>`:

~~~java
@Bean
public TaskRunner taskRunner(ObjectProvider<TaskContext> taskContexts) {
    return new TaskRunner(taskContexts);
}
~~~

Then `TaskRunner` calls `taskContexts.getObject()` whenever it needs a new object. `ObjectProvider` is Spring's API for on-demand dependency retrieval.

This is a scope/prototype injection concern, not a reason to rely on cross-`@Bean` method calls.

## 9. How Can a @Bean Method Obtain Another Bean?

There are three common styles:

### Style A: Calling the Method Directly

~~~java
@Bean
GreetingService greetingService() {
    return new GreetingService(messageFormatter());
}
~~~

- With `proxyBeanMethods=true` in a full configuration class: the call is intercepted.
- With `proxyBeanMethods=false` or lite configuration: the call is direct Java.

This style is prone to misunderstanding when switching modes.

### Style B: Injecting via Factory Method Parameter

~~~java
@Bean
GreetingService greetingService(MessageFormatter formatter) {
    return new GreetingService(formatter);
}
~~~

The container resolves the dependency and passes the appropriate bean. This works consistently in both modes.

### Style C: Injecting via Component Constructor

~~~java
@Service
public class GreetingService {
    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
    }
}
~~~

Spring creates the service bean and injects the formatter via its constructor. This is usually the cleanest choice for regular services, controllers, and components.

**Prefer B or C when there are dependencies between beans.** Style A remains valid in full configuration mode when you intentionally want inter-bean method calls, though it introduces coupling to proxy configuration.

## 10. Does @Configuration(proxyBeanMethods=false) Mean Spring Stops Doing DI?

No. This is a common misconception.

With:

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService(
            MessageFormatter formatter) {
        return new GreetingService(formatter);
    }
}
~~~

Spring still:

1. Discovers the configuration class.
2. Registers bean definitions for `messageFormatter` and `greetingService`.
3. Creates objects via the factory methods.
4. Resolves the `formatter` parameter from the container.
5. Injects dependencies and manages beans according to scope.
6. Performs the corresponding lifecycle processing.

It only omits the CGLIB enhancement that turns a `messageFormatter()` call inside another method body into a bean lookup.

Furthermore, `proxyBeanMethods=false` does not disable AOP proxies for services, does not disable transaction proxies, and does not change bean injection into controllers. Those mechanisms belong to other parts of Spring.

## 11. Is @Configuration(proxyBeanMethods=false) Always Faster?

You should not decide based on speed alone.

`false` avoids enhancing the configuration class to intercept inter-bean method calls. That can reduce some overhead and allow simpler configurations, though the performance difference is rarely the biggest factor in typical applications.

The more important factor is semantics:

- If `@Bean` methods call each other directly and you want the container to return the proper scoped bean, `true` fits.
- If dependencies are passed via method parameters or constructors, `false` is usually simpler and clearer.
- If you do not need inter-bean method calls, there is no need to enable proxying merely out of fear that Spring will not manage beans without it.

Many Spring Boot auto-configurations use non-proxied configurations when dependencies are already expressed via method parameters. This reduces reliance on interception and makes configurations easier to follow.

## 12. Limitations When Using Full Configuration Proxying

### 12.1. Final Configuration Classes

CGLIB needs to subclass the configuration class. A `final` class cannot be subclassed:

~~~java
@Configuration
public final class AppConfig {
    // Incompatible with full configuration proxy.
}
~~~

If the class does not need inter-bean method interception, you can consider:

~~~java
@Configuration(proxyBeanMethods = false)
public final class AppConfig {
    // Lite configuration semantics.
}
~~~

However, changing modes is only safe when not relying on cross-`@Bean` method calls to retrieve container-managed beans.

### 12.2. Private or Final @Bean Methods

In full configuration mode, Spring needs to intercept `@Bean` method calls via overriding. `private` or `final` methods cannot be overridden the way CGLIB requires.

If full mode is needed, keep bean methods overridable. If you want private/final methods or a final configuration class, evaluate lite mode and use parameter dependencies.

### 12.3. Manually Instantiating Configuration with `new`

Example:

~~~java
AppConfig config = new AppConfig();
MessageFormatter formatter = config.messageFormatter();
~~~

This is a manually created Java object, not the Spring-managed configuration proxy instance. Method calls simply execute the method body; you cannot expect the container to intercept them and return a singleton bean.

If you need a Spring-managed bean, obtain it from the context or inject it into consumers. Do not manually instantiate configuration classes to access bean methods.

## 13. Distinguishing Configuration Proxies from AOP Proxies

Both can use proxies, but their goals differ.

| Mechanism | Goal |
| --- | --- |
| `@Configuration(proxyBeanMethods=true)` | Intercepts calls between `@Bean` methods to return beans according to container/scope |
| Spring AOP proxy | Wraps bean method calls to apply advice such as transactions, security, or logging |
| `@Lazy` proxy | Defers dependency resolution/initialization in appropriate situations |

Do not confuse `proxyBeanMethods=false` with disabling AOP or disabling all proxies in the application. It only controls proxy enhancement of the configuration class.

For example, a service can still use `@Transactional` in an application with `@Configuration(proxyBeanMethods=false)`. The two mechanisms do not directly enable or disable each other.

## 14. Testing the Difference Between true and false

You can use Spring Test or `AnnotationConfigApplicationContext` to verify object identity.

### 14.1. Configuration Using true

~~~java
@Configuration(proxyBeanMethods = true)
static class SharedConfiguration {

    @Bean
    MessageFormatter formatter() {
        return new MessageFormatter();
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService(formatter());
    }
}
~~~

Test:

~~~java
@Test
void fullConfigurationUsesContainerManagedSingleton() {
    try (var context =
            new AnnotationConfigApplicationContext(
                    SharedConfiguration.class)) {

        MessageFormatter formatter =
                context.getBean(MessageFormatter.class);

        GreetingService service =
                context.getBean(GreetingService.class);

        assertSame(formatter, service.formatter());
    }
}
~~~

`assertSame` confirms both references point to the same object.

### 14.2. Configuration Using false While Still Calling Directly

~~~java
@Configuration(proxyBeanMethods = false)
static class LiteConfiguration {

    @Bean
    MessageFormatter formatter() {
        return new MessageFormatter();
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService(formatter());
    }
}
~~~

Test:

~~~java
@Test
void liteConfigurationDirectCallCreatesDifferentObject() {
    try (var context =
            new AnnotationConfigApplicationContext(
                    LiteConfiguration.class)) {

        MessageFormatter formatter =
                context.getBean(MessageFormatter.class);

        GreetingService service =
                context.getBean(GreetingService.class);

        assertNotSame(formatter, service.formatter());
    }
}
~~~

`assertNotSame` confirms the instance inside the service differs from the formatter bean in the context. This is the consequence of a direct Java method call in lite mode.

### 14.3. Configuration Using false and Parameter Injection

~~~java
@Configuration(proxyBeanMethods = false)
static class ParameterInjectionConfiguration {

    @Bean
    MessageFormatter formatter() {
        return new MessageFormatter();
    }

    @Bean
    GreetingService greetingService(MessageFormatter formatter) {
        return new GreetingService(formatter);
    }
}
~~~

Test:

~~~java
@Test
void liteConfigurationInjectsManagedDependencyThroughParameter() {
    try (var context =
            new AnnotationConfigApplicationContext(
                    ParameterInjectionConfiguration.class)) {

        MessageFormatter formatter =
                context.getBean(MessageFormatter.class);

        GreetingService service =
                context.getBean(GreetingService.class);

        assertSame(formatter, service.formatter());
    }
}
~~~

This is an explicit way to express dependencies without needing inter-bean method proxying.

The tests above assume `MessageFormatter` and `GreetingService` are classes defined earlier with matching constructors and getters. The tests use JUnit 5 and Spring Context on the test classpath.

## 15. When to Choose true, When to Choose false?

You can use the following decision table:

| Situation | Appropriate choice |
| --- | --- |
| One `@Bean` method directly calls another `@Bean` method and needs the container-managed bean | `true` |
| Configuration has classes/methods requiring CGLIB interception | `true`, provided the class/methods can be proxied |
| All dependencies between beans are passed via `@Bean` parameters | `false` is usually suitable |
| Configuration class only groups independent factory methods | `false` is usually suitable |
| Want to avoid configuration class enhancement | `false` |
| Using `@Component` containing `@Bean` methods | Lite semantics; use parameter injection |
| Unsure whether cross-`@Bean` method calls exist | Inspect the configuration before changing from `true` to `false` |

An easy rule of thumb:

- **Choose `true`** when you need full configuration semantics and have direct calls between `@Bean` methods.
- **Choose `false`** when the configuration is written independently or passes dependencies through parameters.
- **Prefer parameter injection** because it expresses dependencies explicitly and does not depend on the proxy mode.

Do not mass-change `true` to `false` without checking for cross-calls inside configuration classes. Changing the attribute can cause objects to be created outside the container, leading to differences in state, lifecycle, and scope.

## 16. Common Errors and Symptoms

### 16.1. Service Uses a Different Instance Than the Bean Retrieved from the Context

**Symptom:** When comparing identities, `context.getBean(MessageFormatter.class)` and `service.formatter()` are not the same.

**Common cause:** `proxyBeanMethods=false` or lite configuration, while one `@Bean` method directly calls another and creates an object with `new`.

**How to resolve:** Move the dependency to a factory method parameter or enable full configuration if direct calls are genuinely needed.

### 16.2. Multiple Instances Exist and State Is Out of Sync

**Symptom:** The bean retrieved directly from the context holds one state, while the service uses a different object with a different state.

**Cause:** The second object was created by a direct Java call and is not a container-managed singleton bean.

**How to resolve:** Do not call factory methods directly to obtain dependencies in lite mode. Inject the bean instead.

### 16.3. Final Configuration Class Fails to Start in Full Mode

**Symptom:** Spring reports that it cannot enhance/proxy the configuration class.

**Cause:** CGLIB cannot subclass a `final` class.

**How to resolve:** Remove `final` if full proxying is needed, or switch to `proxyBeanMethods=false` and eliminate direct inter-bean calls.

### 16.4. Changing true to false Causes Bugs Only in Certain Configurations

**Symptom:** A bean is still created, but its dependency or object state changes.

**Cause:** Some `@Bean` methods were calling one another and had previously been intercepted by the proxy.

**How to resolve:** Find configuration method calls inside factory methods, convert them to parameter injection, and verify scope/identity after changing.

### 16.5. Thinking false Disables @Bean

**Symptom:** Developers remove `@Bean` or instantiate everything manually with `new` after disabling proxying.

**Explanation:** There is no need to do this. Spring still registers and manages beans declared with `@Bean`; only inter-bean method calls are no longer intercepted.

### 16.6. Using proxyBeanMethods to Fix Dependency Injection Errors

If a bean is missing, multiple beans of the same type exist, or there is a circular dependency, changing `proxyBeanMethods` is not a general solution. Properly diagnose the candidate, package scan, condition, qualifier, or dependency graph issue.

## 17. Practice Exercises

### Exercise A: Comparing Instances

Create two `@Bean` methods:

~~~java
@Bean
MessageFormatter formatter() {
    return new MessageFormatter();
}

@Bean
GreetingService greetingService() {
    return new GreetingService(formatter());
}
~~~

Run tests with `proxyBeanMethods=true` and then `false`. Use `assertSame` and `assertNotSame` to verify object identity.

Explain why the formatter bean in the context still exists in both cases.

### Exercise B: Switching to Parameter Injection

Update the method:

~~~java
@Bean
GreetingService greetingService(MessageFormatter formatter) {
    return new GreetingService(formatter);
}
~~~

Set `proxyBeanMethods=false` and re-run the test. Confirm that the service receives the exact formatter bean from the context.

### Exercise C: Adding a Second Dependency

Create `GreetingRepository` and have `GreetingService` accept both `MessageFormatter` and `GreetingRepository`.

Write the factory method:

~~~java
@Bean
GreetingService greetingService(
        MessageFormatter formatter,
        GreetingRepository repository) {
    return new GreetingService(formatter, repository);
}
~~~

Identify which dependencies are resolved by the container and which object is constructed directly inside the method.

### Exercise D: Observing Prototype Scope

Register a `TaskContext` bean with prototype scope. Compare:

- Retrieving `TaskContext` multiple times from `ObjectProvider`.
- Calling `taskContext()` directly from a `@Bean` method when proxying is `false`.
- Calling `taskContext()` from a `@Bean` method when proxying is `true`.

Explain which cases go through the container's scope resolution.

### Exercise E: Distinguishing Configuration Proxies from AOP Proxies

Create a service with `@Transactional` in a project with `@Configuration(proxyBeanMethods=false)`. Observe that transaction proxying can still work if dependencies and transaction configuration are properly set up.

Explain why the `proxyBeanMethods` attribute does not control transaction proxies.

## 18. Self-Check Questions

**1. What is the default value of `proxyBeanMethods`?**

`true`. `@Configuration` uses full configuration semantics and enhancement by default to intercept calls between eligible `@Bean` methods.

**2. When `proxyBeanMethods=true`, what is special about calling `formatter()` from `greetingService()`?**

The call goes through the configuration proxy and is routed to the container to retrieve the bean according to its scope instead of always executing the method body as plain Java.

**3. When `proxyBeanMethods=false`, does Spring still manage beans?**

Yes. Bean definitions are still registered, factory methods are still invoked by the container, and returned objects are still managed. Only inter-bean method calls are not intercepted by a proxy.

**4. Why can a service receive a different formatter from the formatter bean in the context when using false?**

Because calling `formatter()` directly executes `new MessageFormatter()` again and creates an object outside the container.

**5. Which approach works consistently for both true and false?**

Passing dependencies through `@Bean` method parameters or component constructor injection.

**6. Does `proxyBeanMethods=false` disable AOP/transaction proxies?**

No. It only disables enhancement of the configuration class for inter-bean method interception.

**7. When should false be used?**

When there is no need to call `@Bean` methods directly from one another, especially when dependencies are expressed via method parameters. This is usually a simpler and clearer configuration.

## 19. Conclusion

`proxyBeanMethods` determines how Spring handles direct calls between `@Bean` methods in a configuration class. With `true`, Spring uses CGLIB enhancement so cross-calls pass through the container, ensuring beans receive instances matching their scope. With `false`, method calls are regular Java calls and can create new objects outside the container, even though beans provided directly by factory methods remain Spring-managed.

If a configuration needs to share dependencies, the reliable approach is to **declare dependencies in `@Bean` method parameters** or use constructor injection. This ensures dependencies are explicitly resolved by the container, independent of configuration proxying, and easier to test.

Remember: `proxyBeanMethods=false` does not turn off Spring IoC, does not skip bean registration, and does not disable AOP. It only removes interception of `@Bean` method calls between configuration methods. Understanding this difference helps avoid accidental duplicate instances, unsynchronized state, and helps choose the right configuration mode for how your application organizes beans.

# DEFAULT, LAZY, and DEFERRED Repository Bootstrap Modes in Spring Data JPA

Spring Data JPA creates repository beans from interfaces such as JpaRepository. This process includes bean registration, proxy creation, repository metadata analysis, query method preparation, and wiring repositories to JPA infrastructure. When an application has many repositories, query methods, or entities, when these steps run can noticeably impact startup.

Spring Data provides three repository bootstrap modes: DEFAULT, LAZY, and DEFERRED. They determine when repository implementations are initialized and validated during the ApplicationContext lifecycle. They do not alter how Hibernate executes SQL, transaction semantics, entity fetch strategies, or JPA/JDBC's blocking model.

## 1. What Does Repository Initialization Involve?

Example repository interface:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);
}
```

Spring Data creates an implementation proxy for the interface. Elements processed during initialization typically include:

- The repository proxy and interceptors dispatching method calls.
- Repository metadata: domain type, ID type, parent interfaces, and repository fragments.
- Entity information and mapping metadata.
- Parsing method names such as findByEmail into queries.
- Query lookup strategy to locate declared queries, named queries, or derived queries.
- Components executing queries via EntityManager.
- Infrastructure dependencies such as EntityManager, EntityManagerFactory, and transaction infrastructure.

Not every query is executed when a repository is created. However, Spring Data can parse methods and construct query objects during repository initialization. For queries declared with @Query, syntax errors or invalid property names can be detected during this phase, depending on query type, provider, and version.

Therefore, repository initialization is part of startup cost. The bootstrap mode determines at which stage that cost occurs.

## 2. Quick Comparison of the Three Modes

| Mode | When Implementation Initializes | When Bootstrap Errors Typically Surface | Goal |
|---|---|---|---|
| DEFAULT | Eagerly during ApplicationContext startup | While the context is starting up | Fail fast |
| LAZY | When the repository is first used | When the repository is accessed for the first time | Defer unneeded work |
| DEFERRED | Lazy initially, then triggered when ContextRefreshedEvent fires | After the context refresh phase | Coordinate initialization order while still verifying repositories during startup |

Short summary to remember:

- DEFAULT: initialized immediately when Spring builds the context.
- LAZY: initialized on the first call to the repository.
- DEFERRED: registers proxies first, then proactively initializes repositories when the context refreshes.

## 3. DEFAULT — Eager Initialization

DEFAULT is the default mode. Spring Data initializes repository singletons during startup, without waiting for the first business request.

General flow:

1. Spring scans packages and discovers repository interfaces.
2. Spring registers bean definitions.
3. While instantiating singleton beans, the repository factory creates the repository proxy and configures required components.
4. Query methods and repository metadata are processed per the query lookup strategy.
5. If a repository cannot be initialized, ApplicationContext startup typically fails.

Advantages:

- Detects many repository declaration, query method, and mapping errors early.
- The first repository call after startup typically does not pay the full repository creation cost.
- Simple, predictable, and easy-to-test behavior.
- Successful startup is a fairly strong signal that repository infrastructure has been built.

Disadvantages:

- Startup must wait for repository initialization.
- Applications with many repositories or query methods may take longer to start.
- If EntityManagerFactory takes time to bootstrap, repositories may wait for JPA infrastructure to become ready.

DEFAULT is usually the best choice when startup time is acceptable and the system prioritizes failing fast.

## 4. LAZY — Initialization on First Use

With LAZY, Spring Data registers a lazy proxy for the repository. The actual repository implementation is initialized on the first operation that needs to use it.

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Optional<Customer> findByEmail(String email) {
        return repository.findByEmail(email);
    }
}
```

In LAZY mode, CustomerService's constructor can receive the proxy without fully initializing the repository implementation yet. When findByEmail is invoked for the first time, the proxy triggers initialization and delegates the call to the real repository.

Advantages:

- Can reduce startup time if there are unused repositories.
- Useful for optional modules or rarely executed features.
- Defers initialization cost until the feature is actually needed.

Disadvantages:

- The first access incurs additional initialization latency.
- Query, mapping, or repository configuration errors may only appear at runtime.
- Errors may surface during a rare production request.
- If a startup bean calls a repository in its constructor, lifecycle callback, or runner, the repository is still initialized early.

LAZY does not guarantee faster startup. If the application calls most repositories during startup, the cost is merely shifted to those call points.

## 5. DEFERRED — Initialization After ContextRefreshedEvent

DEFERRED initially registers repository proxies lazily, but differs from LAZY in how it triggers initialization. Spring Data registers a listener to trigger repository initialization when ApplicationContext publishes ContextRefreshedEvent.

General sequence:

1. Spring scans repositories and registers lazy proxies.
2. Other beans in ApplicationContext are created.
3. The context reaches the refreshed state and publishes ContextRefreshedEvent.
4. Spring Data triggers initialization of deferred repositories.
5. Repositories are verified during normal startup, rather than waiting for the first business request.

Advantages:

- Decouples repository initialization from initial bean registration and instantiation.
- Coordinates better with infrastructure bootstrapped asynchronously.
- Still provides an opportunity to detect repository errors during startup.
- Useful when EntityManagerFactory is created on a background executor.

Disadvantages:

- Startup still waits for the deferred initialization step.
- Does not help much if EntityManagerFactory and repositories already initialize very quickly.
- Does not skip validation; repository errors can still cause startup to fail.
- If another bean calls a repository before ContextRefreshedEvent, the repository may be initialized early.

DEFERRED is typically considered when you need to defer initial creation while still verifying repositories before the application finishes starting up.

## 6. Configuration in Spring Boot

With Spring Boot using Spring Data JPA auto-configuration, select the mode via property:

```properties
# Default: eager initialization
spring.data.jpa.repositories.bootstrap-mode=default

# Initialize when the repository is used for the first time
spring.data.jpa.repositories.bootstrap-mode=lazy

# Initialize when ApplicationContext is refreshed
spring.data.jpa.repositories.bootstrap-mode=deferred
```

If the property is omitted, the default mode is DEFAULT. Start with the default and change it only when startup metrics or specific bootstrap requirements warrant it.

The property can be set in application.properties or per profile. Example:

```properties
# application.properties
spring.data.jpa.repositories.bootstrap-mode=default
```

```properties
# application-prod.properties
spring.data.jpa.repositories.bootstrap-mode=deferred
```

This example only illustrates per-environment configuration; there is no production rule requiring DEFERRED.

The Boot property applies to repository infrastructure managed by auto-configuration. If the project manually declares repository scanning with @EnableJpaRepositories, set bootstrapMode directly on the annotation so the setting is clear where repositories are enabled.

## 7. Configuration via @EnableJpaRepositories

You can select the mode on the annotation:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.repository.config.BootstrapMode;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.customer.repository",
    bootstrapMode = BootstrapMode.DEFERRED
)
public class JpaRepositoryConfig {
}
```

Change the value to BootstrapMode.DEFAULT or BootstrapMode.LAZY to select the other two modes.

LAZY example:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.customer.repository",
    bootstrapMode = BootstrapMode.LAZY
)
public class LazyRepositoryConfig {
}
```

Notes:

- BootstrapMode resides in the org.springframework.data.repository.config package.
- @EnableJpaRepositories is typically used when customizing package scanning, factory beans, EntityManagerFactory, or transaction manager.
- If Spring Boot already auto-configures repositories, avoid adding duplicate annotation configuration just to change a single property.
- With multiple persistence units, each repository group must bind to the correct EntityManagerFactory and transaction manager.
- Avoid configuring both the Boot property and multiple manual repository configurations without clearly knowing which configuration takes precedence.

## 8. Why Is DEFERRED Useful with Asynchronous EntityManagerFactory Bootstrap?

EntityManagerFactory has significant initialization cost. Providers like Hibernate must process entity metadata, mappings, dialect, connection metadata, and related persistence components.

Spring Framework allows EntityManagerFactory to be bootstrapped asynchronously via LocalContainerEntityManagerFactoryBean and AsyncTaskExecutor. In this setup, factory creation can happen on a background executor.

If eager repository initialization requires EntityManagerFactory too early, the startup thread may block waiting for the factory to be ready. A common coordination setup to consider:

- EntityManagerFactory is bootstrapped on an executor.
- Repositories use LAZY or DEFERRED to avoid forcing full initialization too early.
- With DEFERRED, ContextRefreshedEvent triggers repository initialization after the initial bean registration phase.
- Repositories are still verified during startup rather than waiting for the first request.

Example EMF configuration snippet:

```java
@Configuration
public class JpaBootstrapConfiguration {

    @Bean
    public AsyncTaskExecutor jpaBootstrapExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setThreadNamePrefix("jpa-bootstrap-");
        executor.initialize();
        return executor;
    }

    @Bean
    public LocalContainerEntityManagerFactoryBean entityManagerFactory(
            DataSource dataSource,
            JpaVendorAdapter vendorAdapter,
            AsyncTaskExecutor jpaBootstrapExecutor) {

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();

        factory.setDataSource(dataSource);
        factory.setPackagesToScan("com.example.customer.domain");
        factory.setJpaVendorAdapter(vendorAdapter);
        factory.setBootstrapExecutor(jpaBootstrapExecutor);

        return factory;
    }
}
```

This is a snippet of EMF configuration, not a full Boot configuration. The application must supply appropriate DataSource, JpaVendorAdapter, transaction manager, and repository configuration. When defining EMF manually, understand which Boot auto-configurations have backed off.

It can be combined with:

```properties
spring.data.jpa.repositories.bootstrap-mode=deferred
```

Async bootstrap only changes how EntityManagerFactory is created during startup. JPA/JDBC afterward remains a blocking model. It does not turn repository methods into Mono or Flux, does not make SQL non-blocking, and does not replace R2DBC.

Do not enable async bootstrap purely for speed without measuring startup. This configuration complicates initialization order and requires verifying compatibility with the provider, datasource, executor, and repository infrastructure.

## 9. Differences Between Repository LAZY and Other Types of LAZY

The word lazy appears at several different layers:

| Concept | What Does It Control? | Example |
|---|---|---|
| Repository BootstrapMode.LAZY | When Spring Data initializes the repository implementation | Repository proxy is created; implementation is created on first call |
| Spring @Lazy | When Spring initializes a bean dependency | A bean is created when the dependency is requested |
| JPA FetchType.LAZY | When an association or entity attribute is loaded | Accessing order.getItems() may trigger a query |
| Hibernate lazy proxy/collection | How the provider represents unloaded association data | Entity proxy or persistent collection |

Three key points:

1. BootstrapMode.LAZY does not change entity FetchType.
2. FetchType.LAZY does not determine when a repository bean is created.
3. Spring's @Lazy is a general bean mechanism; BootstrapMode is an option of Spring Data repository infrastructure.

An eagerly initialized repository can still return entities with FetchType.LAZY associations. Conversely, a LAZY-bootstrapped repository can still execute queries that load eager associations when invoked.

## 10. Dependency Injection and Bean Startup

Repositories are typically injected into services via constructor:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }
}
```

With LAZY or DEFERRED, dependency injection can receive the repository proxy before the actual implementation is initialized. However, if a constructor or lifecycle callback invokes the repository, the lazy proxy is triggered immediately:

```java
@Service
public class StartupInitializer {

    public StartupInitializer(OrderRepository repository) {
        // This call triggers repository initialization.
        long count = repository.count();
    }
}
```

In this example, LAZY no longer defers the repository until the first request. The repository is initialized while the initializer bean is constructed. Avoid querying the database inside constructors.

If data preparation is needed on startup, ApplicationRunner or CommandLineRunner can be used, but transaction, error, and readiness behavior must be clearly defined. A runner calling a repository will also trigger LAZY repositories.

DEFERRED separates bean creation from repository initialization, though another bean calling a repository early can still trigger it before ContextRefreshedEvent.

## 11. Impact on Startup Time and First Request

You cannot conclude which mode is fastest without measuring the whole application:

- DEFAULT puts repository cost into startup. The first request usually avoids paying the full repository creation cost.
- LAZY can reduce startup if unused repositories remain, though the first request to each uninitialized repository incurs extra latency.
- DEFERRED shifts part of the work out of bean registration, while still initializing repositories before startup completes. Benefit depends on overlap with other bootstrap tasks.

Contributing factors:

- Number of repository interfaces and query methods.
- Number of entities, mappings, converters, and repository fragments.
- EntityManagerFactory bootstrap time.
- Whether DataSource needs to connect to the database to read metadata.
- Provider and Spring Data JPA/Hibernate versions.
- Whether startup beans call repositories.
- How the application implements readiness and health checks.

When measuring, record:

1. Time from process start to ApplicationContext refreshed.
2. Time from context refresh to ApplicationReady.
3. EntityManagerFactory initialization time.
4. Repository initialization time.
5. First-request latency for each repository.
6. Startup errors and first-use errors in logs.

Do not measure only total startup time and conclude LAZY is better. If startup drops while first-request latency spikes sharply, evaluate actual latency objectives.

## 12. Choosing a Mode by Scenario

### Choose DEFAULT When

- The application has a moderate number of repositories.
- You want repository errors to surface immediately at startup.
- Startup time is not a major bottleneck.
- Async EntityManagerFactory bootstrap is not used.
- Simple and easy-to-test behavior is preferred.

This is the appropriate default choice for most applications.

### Choose LAZY When

- There are repositories belonging to optional modules or only used in rare flows.
- Metrics show repository initialization significantly impacts startup.
- Latency on first access is acceptable.
- Critical repositories are verified before serving traffic, or errors surfacing upon use are acceptable.
- Monitoring is in place to catch first-use errors.

Do not pick LAZY just because the name sounds optimized. If most repositories are used as soon as the application runs, the benefit may be negligible.

### Choose DEFERRED When

- EntityManagerFactory is bootstrapped asynchronously.
- Repository initialization needs to be deferred past bean registration.
- You still want repositories initialized and checked during startup.
- You want to verify repositories before the application finishes normal startup.

DEFERRED is usually more reasonable than LAZY when the goal is coordinating initialization order while still failing fast before the application accepts traffic.

## 13. Testing and Verification

You can set the bootstrap mode in Spring Boot tests:

```java
@SpringBootTest(properties = {
    "spring.data.jpa.repositories.bootstrap-mode=deferred"
})
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void canFindCustomerByEmail() {
        // Seed data according to test configuration before querying.
        assertThat(repository.findByEmail("a@example.com"))
                .isPresent();
    }
}
```

The example requires a test database, seed data, and an appropriate assertion library. The code snippet demonstrates how to set the property; setup details depend on the project.

Testing directions:

- DEFAULT: start the context and verify repositories are created; detected bootstrap errors fail context startup.
- LAZY: start the context without calling the repository, then call the repository and observe initialization timing; test first-use errors.
- DEFERRED: verify repositories are triggered after ContextRefreshedEvent; errors surface during the deferred initialization phase.
- Integration tests: run critical queries against the matching database to catch errors that only occur when SQL executes.
- Startup tests: measure with identical profiles, database, JVM, and dataset for a fair comparison.

A test that only starts ApplicationContext will not necessarily check every SQL statement. A query may be valid in JPA while the database is missing a column, lacks permissions, or differs in dialect. Maintain integration tests on a database engine matching production whenever schema/dialect differences matter.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Fast startup, but first request hits repository error | LAZY deferred the error until the repository was triggered | Switch to DEFAULT/DEFERRED or add startup validation |
| Startup remains slow despite choosing LAZY | Initializer bean, runner, or health check called the repository | Search for calls in constructors, @PostConstruct, listeners, and runners |
| Selected DEFERRED, yet startup still waits on repositories | Deferred initialization runs at ContextRefreshedEvent | This is expected behavior; re-measure total startup time |
| Query error appears after ContextRefreshedEvent | Repository was initialized during the deferred phase | Check query methods, entity properties, and declared queries |
| Error appears only when running SQL | Mismatched schema, permissions, dialect, or data | Run integration tests and inspect actual SQL |
| Property has no effect | Repositories configured manually or auto-configuration overridden | Check @EnableJpaRepositories and scanning config |
| Repository initialized earlier than expected | Another bean invoked a method through the lazy proxy | Search call sites in constructors, init callbacks, listeners, and runners |
| Multiple repository factories or EMFs | Multiple overlapping repository scan configurations | Separate packages and specify factory/transaction manager explicitly |

Not all database errors are caught during repository initialization. For example, a missing column or denied SELECT privilege may only surface when the query executes.

## 15. Checklist Before Changing Bootstrap Mode

- [ ] Measured startup time under identical environment and configuration.
- [ ] Identified whether cost lies in EntityManagerFactory or repository initialization.
- [ ] Checked the number of repositories and query methods.
- [ ] Checked for constructors, @PostConstruct, listeners, runners, or health checks calling repositories.
- [ ] Determined whether async EntityManagerFactory bootstrap is used.
- [ ] Understood whether errors surface at startup, context refresh, or first use.
- [ ] Considered first-use latency if selecting LAZY.
- [ ] Identified whether the effective configuration is the Boot property or @EnableJpaRepositories.
- [ ] Tested critical repositories against the corresponding database.
- [ ] Confirmed readiness reports the application ready only after required infrastructure is initialized.

## 16. Conclusion

DEFAULT initializes repositories eagerly during startup, catching errors early and serving as a safe choice for most applications. LAZY uses proxies and initializes repositories only on first call, potentially reducing startup time while shifting cost and some errors to runtime. DEFERRED defers initial creation and triggers repositories when ApplicationContext publishes ContextRefreshedEvent, making it suitable when coordinating repositories with async EntityManagerFactory bootstrap while still verifying repositories during startup.

Choose according to operational goals:

- Use DEFAULT when simplicity and fail-fast behavior are prioritized.
- Use LAZY when on-demand initialization is needed and first-use latency is acceptable.
- Use DEFERRED when initial creation must be deferred while still validating repositories before startup completes.

The three modes only alter the repository initialization lifecycle. They do not change transaction semantics, the SQL execution model, entity fetch strategies, or JPA's non-blocking capabilities.
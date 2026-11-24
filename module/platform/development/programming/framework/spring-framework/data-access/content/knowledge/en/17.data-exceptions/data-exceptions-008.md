# @Repository and PersistenceExceptionTranslationPostProcessor: Translating Data Exceptions Properly

When the data access layer calls JDBC, JPA, Hibernate, or another persistence provider, errors typically surface as exceptions from the library or driver in use. For example, a save operation may throw a unique constraint violation, connection drop, optimistic locking failure, or invalid query error. If the service layer must know every provider-specific exception type, business code becomes tightly coupled to the storage technology.

Spring Framework provides a **persistence exception translation** mechanism to convert *eligible exceptions* into classes within the `org.springframework.dao.DataAccessException` hierarchy. For repositories directly using JPA/Hibernate or custom persistence APIs, the declarative mechanism is built around three elements:

1. `@Repository` marks a data-access-layer bean and serves as the point where advice applies.
2. `PersistenceExceptionTranslationPostProcessor` registers a **Spring AOP advisor** on eligible repository beans.
3. One or more beans implementing `PersistenceExceptionTranslator` understand native exceptions and decide which `DataAccessException` they can translate into.

These are three distinct roles. **Merely putting `@Repository` on a class does not guarantee every exception is automatically translated.** Conversely, a repository using `JdbcTemplate` usually already receives `DataAccessException` directly from `JdbcTemplate`, because the template translates many `SQLException`s internally during JDBC execution.

This lesson explains **when to use `@Repository` with `PersistenceExceptionTranslationPostProcessor`, operating conditions, configuration, key limitations, and how to verify behavior with a Java 17+ example**.

## 1. Why Is Persistence Exception Translation Needed?

Consider a scenario: a service calls a repository to add a product code, but the database rejects it because the code already exists. Across providers, the native exception can differ:

- JDBC drivers usually report SQL errors via `SQLException` or its subclasses.
- JPA has runtime exceptions belonging to the API/provider, such as variants of `jakarta.persistence.PersistenceException`.
- Hibernate has its own exception hierarchy, such as `org.hibernate.exception.ConstraintViolationException` (distinct from Bean Validation's `ConstraintViolationException`).
- A custom persistence library might throw `VendorUniqueKeyException`.

If the service catches each provider exception directly, switching providers or data access approaches forces the service layer to change. Spring offers the **unchecked `DataAccessException`** hierarchy to express common failures in language closer to the application.

Common types:

| Spring exception | Typical meaning | Context-dependent handling |
| --- | --- | --- |
| `DuplicateKeyException` | Unique/primary key violation | Return an appropriate duplicate-data message; do not auto-retry the identical operation |
| `DataIntegrityViolationException` | Integrity constraint violation (broader than duplicate key) | Validate input and specific constraint; avoid exposing DB details |
| `OptimisticLockingFailureException` | Version conflict during optimistic update | Consider conflict reporting or controlled retry |
| `DataAccessResourceFailureException` | Data access resource failure, e.g. unable to connect | Check infrastructure and recoverability |
| `QueryTimeoutException` | Query exceeded wait timeout | Evaluate timeout, query plan, and retry policy |
| `InvalidDataAccessResourceUsageException` | Invalid usage of data resources | Usually an SQL/configuration/code bug to fix |

This list shows **examples of class semantics**, not a rigid mapping guaranteed for every driver. A provider may throw an overly generic error so the translator can only choose a broad `DataAccessException` class, or fail to translate it at all.

`DataAccessException` is a `RuntimeException`, so it requires no `throws` declaration in Java method signatures. It preserves `cause` to assist root-cause diagnostics. **Translating an error does not mean the error is handled**: the service still needs to decide response, transaction, and retry behavior based on business semantics.

## 2. What Does @Repository Actually Do?

`@Repository` lives in:

~~~java
import org.springframework.stereotype.Repository;
~~~

Example:

~~~java
@Repository
public class ProductRepository {
    // Database access methods.
}
~~~

This is an **illustrative code fragment**, not yet containing DB access logic. In Spring:

- `@Repository` is a **stereotype annotation**, specifically designating the DAO/repository layer.
- It is meta-annotated with `@Component`. When component scanning is enabled for the appropriate package, Spring can detect the class and create a bean.
- For exception translation, `PersistenceExceptionTranslationPostProcessor` uses this annotation to identify **which beans are eligible to receive the advisor**.
- `@Repository` is **not** a transaction annotation; it does not start, commit, or roll back transactions by itself.
- Nor does `@Repository` specify schemas, drivers, or translation rules for individual exceptions.

Compared to `@Component`: both can register beans via component scanning, but `PersistenceExceptionTranslationPostProcessor`'s default configuration looks for **`@Repository`**. A class annotated only with `@Component` should not be assumed to receive the same advice. `@Service` designates the business layer and is normally not the attachment point for the persistence translation advisor.

A class can also be registered via `@Bean` without component scanning; as long as the actual object is an eligible repository passing through the Spring bean lifecycle, the post-processor still has the opportunity to process it. The key condition is that **Spring owns the bean**, rather than the application instantiating it directly with `new` and calling it standalone.

## 3. How Does PersistenceExceptionTranslationPostProcessor Work?

`org.springframework.dao.annotation.PersistenceExceptionTranslationPostProcessor` is a specialized `BeanPostProcessor`. When Spring initializes a repository bean, the post-processor applies `PersistenceExceptionTranslationAdvisor` to eligible beans. The advisor uses `PersistenceExceptionTranslationInterceptor` as its advice and queries `PersistenceExceptionTranslator` beans.

Conceptual flow:

~~~text
Service
  │ calls method on repository bean obtained from Spring
  ▼
Spring AOP proxy of the repository
  │
  ├─ invokes actual repository method
  │      └─ JPA/Hibernate/native persistence API may throw RuntimeException
  │
  └─ if an exception exits through the proxy:
         PersistenceExceptionTranslationInterceptor
           ├─ queries matching PersistenceExceptionTranslators
           ├─ translator returns DataAccessException → throws translated exception
           └─ no translator can translate it → keeps original exception
  ▼
Service sees Spring exception (if translated) or original exception
~~~

Key steps:

1. **Bean initialization:** Spring registers the post-processor in the application context and inspects eligible beans.
2. **Create or augment proxy:** The post-processor may add the advisor onto an existing AOP proxy or create a new proxy. The actual proxy type depends on interfaces, AOP configuration, and bean constraints.
3. **Invoke repository:** Callers must go through the Spring proxy. Advice can intercept runtime exceptions thrown out of advised methods.
4. **Translate exception:** The interceptor delegates to `PersistenceExceptionTranslator.translateExceptionIfPossible(RuntimeException)`. A translator may return a `DataAccessException` or `null` if it does not recognize the exception.
5. **Return to caller:** If translation succeeds, the caller receives the new exception potentially carrying the original `cause`; if untranslated, the native exception continues propagating.

Spring does not adopt a "turn every `RuntimeException` into `DataAccessException`" approach. Non-persistence errors, such as a `NullPointerException` from buggy code, **must not** be mislabeled as database errors by a custom translator.

### Essential Conditions

| Component | If missing or wrong |
| --- | --- |
| Repository is a Spring bean | Direct instantiation with `new` bypasses BeanPostProcessor/AOP |
| Class/bean is annotated with `@Repository` appropriately | Default setup does not automatically advise every `@Component`/`@Service` |
| Active `PersistenceExceptionTranslationPostProcessor` bean exists | Annotation remains a stereotype but generates no exception-translation advisor |
| A translator understands the current exception | Interceptor cannot guess the right `DataAccessException` type from an arbitrary error |
| Call goes through an advised method/proxy | Self-invocation or calls on the raw target object bypass advice |
| Exception actually escapes the repository method | Exceptions caught/swallowed inside the method or thrown after returning are not seen by advice there |

## 4. PersistenceExceptionTranslator Is the Most Critical Contract

Interface:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.support.PersistenceExceptionTranslator;
~~~

Core method:

~~~java
DataAccessException translateExceptionIfPossible(RuntimeException ex);
~~~

This is an **illustrative signature**, not a standalone runnable top-level Java method. The contract requires:

- If this native exception can be converted, return a specific, appropriate `DataAccessException`.
- If it cannot be converted, **return `null`**. Do not turn every runtime exception into `DataAccessException`.
- Try to keep the original exception as `cause` to support stack-trace and SQL state/vendor-code diagnostics when valid.
- A context can have **multiple translators**; Spring can chain them, and ordering depends on dependency ordering/`Ordered` rules where applicable.

A Spring adapter bean for JPA, such as `LocalContainerEntityManagerFactoryBean`, can supply a built-in `PersistenceExceptionTranslator` implementation. For technologies without a built-in adapter, the application may need to write its own translator.

**Note:** When a translator returns `null`, it means "I do not handle this error type", not "there is no error". The original exception can still be thrown out of the proxy.

## 5. Explicit Configuration in Plain Spring Framework

When not relying on Spring Boot auto-configuration, register the post-processor as a bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.annotation.PersistenceExceptionTranslationPostProcessor;

@Configuration(proxyBeanMethods = false)
public class PersistenceTranslationConfig {
    @Bean
    public static PersistenceExceptionTranslationPostProcessor
            persistenceExceptionTranslationPostProcessor() {
        return new PersistenceExceptionTranslationPostProcessor();
    }
}
~~~

This is a **complete Spring configuration class**, saved as `PersistenceTranslationConfig.java` in an appropriate package. `@Bean static` is useful for a `BeanPostProcessor` because it lets Spring register infrastructure early without instantiating the configuration class prematurely. At the same time, repositories must be Spring beans, e.g., discovered via `@ComponentScan` or declared via `@Bean`.

When using **Spring Boot 3.x**, `PersistenceExceptionTranslationAutoConfiguration` can usually register the post-processor when auto-configuration conditions are satisfied. Boot 3.x releases have the `spring.dao.exceptiontranslation.enabled` property enabled by default. Avoid blindly adding a second bean in a Boot project that already has one; inspect the actual context and configuration first.

Having the post-processor **is still not enough** without a matching translator. When connecting JPA/Hibernate via Spring's standard integration, the translator is usually provided by the adapter/persistence factory; when using a custom client library, you must verify this.

## 6. Runnable Java 17+ Example: Translating Simulated Native Exceptions

The following example uses **Spring Framework 6.2.14** and needs no database. Its goal is to prove precisely:

- `@Repository` is recognized;
- `PersistenceExceptionTranslationPostProcessor` creates an AOP proxy;
- `PersistenceExceptionTranslator` converts a simulated native error into `DuplicateKeyException`;
- runtime errors unrecognized by the translator **remain unchanged**;
- calls go through the bean interface returned by Spring.

**Note:** `VendorUniqueConstraintException` is a simulated exception for this lesson, not a real Hibernate/JPA or JDBC driver class. In real projects, translators must map based on errors/causes/codes documented by the provider.

Create directory:

~~~text
repository-translation-demo/
├── build.gradle
└── src/main/java/demo/
    └── RepositoryTranslationDemo.java
~~~

File `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-aop:6.2.14'
    implementation 'org.springframework:spring-tx:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.RepositoryTranslationDemo'
}
~~~

File `src/main/java/demo/RepositoryTranslationDemo.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.annotation.PersistenceExceptionTranslationPostProcessor;
import org.springframework.dao.support.PersistenceExceptionTranslator;
import org.springframework.stereotype.Repository;

public final class RepositoryTranslationDemo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            Store store = context.getBean(Store.class);
            System.out.println("proxied=" + AopUtils.isAopProxy(store));

            store.save("ok");
            System.out.println("ok");

            try {
                store.save("duplicate");
            } catch (DuplicateKeyException ex) {
                System.out.println(
                        "translated=" + ex.getClass().getSimpleName());
                System.out.println(
                        "cause=" + ex.getCause().getClass().getSimpleName());
            }

            try {
                store.save("unknown");
            } catch (VendorUnknownException ex) {
                System.out.println(
                        "untranslated=" + ex.getClass().getSimpleName());
            }
        }
    }

    public interface Store {
        void save(String code);
    }

    @Repository
    public static class StoreImpl implements Store {
        @Override
        public void save(String code) {
            if ("duplicate".equals(code)) {
                throw new VendorUniqueConstraintException("duplicate code");
            }
            if ("unknown".equals(code)) {
                throw new VendorUnknownException("unknown vendor error");
            }
        }
    }

    public static class VendorUniqueConstraintException
            extends RuntimeException {
        public VendorUniqueConstraintException(String message) {
            super(message);
        }
    }

    public static class VendorUnknownException extends RuntimeException {
        public VendorUnknownException(String message) {
            super(message);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public static PersistenceExceptionTranslationPostProcessor
                persistenceExceptionTranslationPostProcessor() {
            return new PersistenceExceptionTranslationPostProcessor();
        }

        @Bean
        public PersistenceExceptionTranslator vendorTranslator() {
            return exception -> {
                if (exception instanceof VendorUniqueConstraintException) {
                    return new DuplicateKeyException(
                            "Duplicate catalog code", exception);
                }
                return null;
            };
        }

        @Bean
        public Store store() {
            // @Bean registers the instance; @Repository annotation sits on the class.
            return new StoreImpl();
        }
    }
}
~~~

Run in the directory containing `build.gradle` with Gradle installed:

~~~bash
gradle run
~~~

If the project has a Gradle Wrapper, run `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows). Gradle will fetch dependencies if not yet cached. With the configuration above, **program** stdout is:

~~~text
proxied=true
ok
translated=DuplicateKeyException
cause=VendorUniqueConstraintException
untranslated=VendorUnknownException
~~~

Gradle produces its own build logs. These lines illustrate the difference between translated and untranslated errors. `AopUtils.isAopProxy(store)` verifies the returned bean is an AOP proxy; it **does not by itself prove every native exception type will be translated**.

### Step-by-Step Walkthrough of the Example

1. `AnnotationConfigApplicationContext(Config.class)` starts the context and registers beans via `@Configuration`.
2. The `@Bean static` method brings `PersistenceExceptionTranslationPostProcessor` into bean creation.
3. Bean `store()` returns a `StoreImpl` annotated with `@Repository`. The program invokes it via the `Store` interface, avoiding assuming the proxy can always be accessed by concrete implementation class.
4. Bean `vendorTranslator()` recognizes only `VendorUniqueConstraintException` and returns `DuplicateKeyException`; all other errors return `null`.
5. `store.save("ok")` passes through the proxy without throwing, so it succeeds.
6. `store.save("duplicate")` throws the native error from the target. The interceptor queries the translator and returns `DuplicateKeyException` to the caller, with `cause` set to the original error.
7. `store.save("unknown")` throws another native error. The translator returns `null`, so the caller receives the original `VendorUnknownException`.

If you call `new StoreImpl().save("duplicate")` directly, the call bypasses the Spring proxy and throws the original **`VendorUniqueConstraintException`**. This is a way to verify the proxy's role; no translator code changes are needed.

### Limitations of the Demo

The example intentionally **does not use a database**, because the goal is to test the AOP mechanism and translator contract deterministically. It does not prove mappings from any specific JDBC/JPA/Hibernate driver version. For real systems, add integration tests hitting a real DB, triggering real constraints, and observing exceptions/causes through the injected repository bean.

## 7. When a Repository Uses JDBC: Distinguishing Two Translation Mechanisms

For Spring JDBC, `JdbcTemplate` already translates `SQLException`s encountered during statement execution. The following DAO class is a **repository code fragment**, assuming the table and `JdbcTemplate` are configured:

~~~java
@Repository
public class UserJdbcRepository {
    private final JdbcTemplate jdbcTemplate;

    public UserJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int insert(String username) {
        return jdbcTemplate.update(
                "INSERT INTO app_user (username) VALUES (?)",
                username);
    }
}
~~~

To compile separately, import `org.springframework.stereotype.Repository` and `org.springframework.jdbc.core.JdbcTemplate`. This is not a standalone `main`. If `username` violates a unique key, `JdbcTemplate` may throw `DuplicateKeyException` or `DataIntegrityViolationException` depending on SQL state/vendor error code interpretation.

**Key point:** in the example above, `SQLException` translation normally happens **right inside `JdbcTemplate`**, before the exception leaves `insert`. Do not conclude "`@Repository` automatically translated the SQLException" merely because the class carries the annotation and the thrown exception is `DataAccessException`.

| Case | Who normally performs translation? |
| --- | --- |
| `JdbcTemplate.update/query(...)` catches `SQLException` | `SQLExceptionTranslator` used internally by Spring JDBC's template |
| DAO calls JPA/Hibernate APIs directly and receives native `RuntimeException` | `PersistenceExceptionTranslationInterceptor` can consult `PersistenceExceptionTranslator` when calls go through the proxy |
| DAO uses plain JDBC, method declares `throws SQLException` | `SQLException` is a checked exception; the persistence interceptor considers runtime exceptions, so you cannot rely on the post-processor to auto-translate it like `JdbcTemplate` |
| DAO catches native exception and throws `IllegalStateException` | Only the wrapper exits the proxy; translators may fail to recognize it or pick wrong semantics if poorly written |
| Native exception is thrown after the repository method already returned | Advice at the repository boundary does not necessarily have an opportunity to see the exception |

For plain JDBC code, use `JdbcTemplate`/`NamedParameterJdbcTemplate` to get standard exception translation, or explicitly invoke `SQLExceptionTranslator` when low-level JDBC work is required. Do not write a catch-all translator like "every `RuntimeException` → `DataAccessException`" that masks programming bugs.

## 8. When a Repository Uses JPA or Hibernate

In a repository calling `EntityManager` directly, the following is a **code fragment used in a JPA application with valid `EntityManager` bean and `Product` entity**:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class JpaProductRepository {
    @PersistenceContext
    private EntityManager entityManager;

    public void save(Product product) {
        entityManager.persist(product);
    }
}
~~~

`@PersistenceContext` requires appropriate JPA infrastructure, and `Product` is a mapped entity; this snippet will not run standalone without an entity/persistence unit. When a native runtime exception is thrown during a repository call and an appropriate JPA translator exists in the Spring context, `PersistenceExceptionTranslationPostProcessor` can help convert the error into `DataAccessException`.

Several points to understand carefully:

- `EntityManager.persist(...)` might **not execute the SQL INSERT immediately**. A unique constraint violation may only surface at `flush` or transaction commit time.
- If the exception occurs **after the repository method has returned** (for instance, flush/commit driven by transaction infrastructure in another layer), you cannot assume the repository advisor alone will see that exception.
- Opening/committing transactions is controlled by the transaction manager and `@Transactional`; `@Repository` does not grant transactions on its own.
- `JpaTransactionManager` and the JPA adapter have their own error conversion mechanisms during transaction flows; that is another path to understand when diagnosing.

**Do not scatter `entityManager.flush()` arbitrarily just to "make @Repository translate errors immediately"**. Early flushing alters SQL timing and performance. If business logic needs immediate validation (e.g. detecting duplicates before the next step), design transaction boundaries, flush timing, and error handling deliberately.

## 9. AOP Proxy: Four Easily Missed Situations

### 9.1. Internal Calls on the Same Object (Self-Invocation)

~~~java
@Repository
public class ProductDao {
    public void outer() {
        inner(); // calls on 'this', bypassing the bean's own proxy
    }

    public void inner() {
        // May throw a native persistence RuntimeException.
    }
}
~~~

This illustrates call-scope behavior. When a service calls `proxy.outer()`, the advice wrapping `outer` can translate a runtime exception **if the exception ultimately escapes `outer`**. However, the `this.inner()` call **does not trigger a separate interception for `inner`**. This distinction matters if code expects advice specifically on `inner`, especially when methods catch/rethrow exceptions differently.

Do not oversimplify as "self-invocation always prevents exception translation": if the exception escapes the outer method that is intercepted by the proxy, the outer advisor still has a chance to translate it. Watch **which boundary receives the exception**.

### 9.2. Manually Instantiating the Repository with `new`

~~~java
ProductDao direct = new ProductDao();
direct.inner();
~~~

There is no bean lifecycle or proxy. No post-processor intercepts calls on this `direct` instance. Inject repository beans from the container whenever Spring infrastructure should apply.

### 9.3. Catching Exceptions Inside the Repository

~~~java
public void save() {
    try {
        callNativePersistenceApi();
    } catch (RuntimeException ex) {
        logFailure(ex);
        // If swallowed here, the proxy sees the method finish normally.
    }
}
~~~

This is **Java pseudocode**, not independently compilable: `callNativePersistenceApi` and `logFailure` represent real methods. If the repository catches the error and returns normally, outer advice has nothing to translate. If the repository needs to process an exception, preserve semantics and never turn a data-write failure into a false success.

### 9.4. Proxy Type and Method Signatures

With JDK dynamic proxies, callers typically access via an interface implemented by the proxy. With class-based proxies, callers may access via the concrete class subject to AOP constraints. Compatibility is affected by `final` classes/methods, visibility, proxy type, and framework settings. Do not assume a concrete class can always be cast from a Spring-created bean proxy.

When debugging, you can check `AopUtils.isAopProxy(bean)` or `AopUtils.getTargetClass(bean)`. This proves proxy structure, **not** that an exception actually goes through the advisor; still test exception translation directly.

### A Little-Noticed Detail: Exception Declarations in Method Signatures

By default, `PersistenceExceptionTranslationInterceptor` **leaves a runtime exception untouched if the target method declares that the exception can be thrown**, even if the signature declares a compatible superclass like `Exception`; the interceptor has an `alwaysTranslate` setting if you need to change this behavior. In practice, repository interfaces rarely declare generic `throws Exception`, and you should not rely on automatic translation when a signature intentionally permits native exceptions to pass through.

## 10. Writing a Semantically Accurate Translator for a Custom Persistence Provider

Suppose a custom client throws:

~~~java
public class VendorConstraintException extends RuntimeException {
    private final String errorCode;

    public VendorConstraintException(
            String errorCode, String message, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
    }

    public String getErrorCode() {
        return errorCode;
    }
}
~~~

This is a complete Java class if saved as `VendorConstraintException.java`, intended as an illustration. Assuming the vendor documents `UK_DUPLICATE` as a **unique constraint** and `FK_MISSING` as a **foreign key violation**, we can create a translator:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.support.PersistenceExceptionTranslator;

public final class VendorConstraintTranslator
        implements PersistenceExceptionTranslator {
    @Override
    public DataAccessException translateExceptionIfPossible(
            RuntimeException ex) {
        if (!(ex instanceof VendorConstraintException vendor)) {
            return null;
        }

        return switch (vendor.getErrorCode()) {
            case "UK_DUPLICATE" ->
                    new DuplicateKeyException("Unique key conflict", vendor);
            case "FK_MISSING" ->
                    new DataIntegrityViolationException(
                            "Referenced row does not exist", vendor);
            default -> null;
        };
    }
}
~~~

This is a standalone Java 17+ class at source level, **depending** on `VendorConstraintException` above and Spring `spring-tx`. Error code names are hypothetical **examples defined here**, not error codes of PostgreSQL, MySQL, Oracle, SQL Server, or any specific provider.

Register as a bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class VendorTranslationConfig {
    @Bean
    public PersistenceExceptionTranslator vendorConstraintTranslator() {
        return new VendorConstraintTranslator();
    }
}
~~~

This configuration fragment needs imports for `Configuration`/`Bean` and the translator classes; it adds the translator, while `PersistenceExceptionTranslationPostProcessor` must still be registered per section 5 or via active auto-configuration.

### Why Must Mappings Be Precise?

- Do not map every constraint error to `DuplicateKeyException`; foreign key, check constraint, and not-null have different meanings.
- If the vendor has codes equivalent to "deadlock", "timeout", or "connection refused", consider the appropriate Spring subclass and transient nature per the provider's contract, **not guessing solely from text messages**.
- Preserve the original exception in `cause`, while never stuffing SQL with sensitive info into messages returned to HTTP clients.
- Do not translate `NullPointerException`, input validation errors, or business errors into `DataAccessException` unless there is a genuinely clear data contract for doing so.
- When an error code is unknown or its meaning is undocumented by the provider, return `null` so the original exception passes through; that is safer than misclassifying it.

For JDBC, `SQLErrorCodeSQLExceptionTranslator`/standard translators and Spring's SQL state mappings may already cover common error codes; avoid reinventing that mechanism when using `JdbcTemplate`.

## 11. Checking Configuration and Runtime Behavior

A practical checklist when `@Repository` is present yet exceptions remain native:

1. **Is the bean created by Spring?** Check registration via `@ComponentScan`, `@Import`, `@Bean`, or auto-configuration. Avoid instantiating with `new` in services.
2. **Is the right annotation used?** `@Repository` sits on the proper implementation/proxy target; not just `@Service` or `@Component`.
3. **Is `PersistenceExceptionTranslationPostProcessor` registered?** In plain Spring Framework, configure the bean; in Spring Boot, verify auto-configuration is active.
4. **Is the invoked bean an AOP proxy?** Use `AopUtils.isAopProxy(...)` to verify. If not, check BeanPostProcessor setup, class/interfaces, and initialization lifecycle.
5. **Is an appropriate `PersistenceExceptionTranslator` present?** For JPA, verify the entity manager factory/Spring adapter; for custom clients, supply a translator that knows the native exceptions.
6. **When is the exception thrown?** Directly inside the repository method, during flush, during transaction commit, or inside an async task? Where it occurs determines which advisor can see it.
7. **Actual exception type and cause?** Inspect the stack trace and original chain; if already wrapped by application code, the translator may not recognize it.
8. **Method signature/call path?** Do not assume self-invocation or a `throws Exception` declaration shares the same translation behavior as an interface call through the proxy.
9. **Are other interceptors/advisors involved?** Transaction, caching, async, retry, or security advisors can also create proxies. Inspect their order and boundaries if tests show unexpected behavior.

You can inspect the actual bean in a Spring test:

~~~java
Object repositoryBean = context.getBean(Store.class);
boolean proxied = AopUtils.isAopProxy(repositoryBean);
System.out.println(proxied);
~~~

This is a **code fragment in a context with `context`, the `Store` interface, and `AopUtils` imported** as in section 6's demo. Do not use proxy status alone to claim the translator selected the right exception type: **assert the actual exception thrown when invoking the API**.

## 12. Testing Exception Translation Properly

Using the same repository and production provider version, tests should distinguish at least three scenarios:

| Test | What to assert |
| --- | --- |
| Mapped native error | Via the bean proxy, receives the right `DataAccessException` subclass with original `cause` |
| Runtime error unrecognized by translator | Original error is preserved, not misclassified as a data error |
| Calling target directly bypassing Spring | Post-processor is not expected to intervene |
| Unique/foreign key violation on real DB | Accurate semantic outcome for DB + provider + driver + flush timing |
| Error at transaction commit | Test at the transaction boundary; do not confuse with repository-method translation |
| Repository using `JdbcTemplate` | Verify the template already translated the exception and root cause is `SQLException` when appropriate |

### Manual Verification for Section 6 Demo

In the program:

- `store.save("ok")` runs normally.
- `store.save("duplicate")` throws `DuplicateKeyException`, with `cause` being `VendorUniqueConstraintException`.
- `store.save("unknown")` throws `VendorUnknownException`.
- `AopUtils.isAopProxy(store)` returns `true` under the AOP configuration used.

This tests the **proxy + translator mechanism**, not a persistence-provider integration test. DB tests must exercise real constraints and assert post-rollback state, not just the exception class.

### Differences to Cover in Integration Tests

- Provider's native exception types on `persist`, `flush`, and commit.
- SQL state/vendor codes associated with constraints, unique keys, or transaction conflicts.
- Which translators exist in the context when multiple factories or DBs are configured.
- How Spring's transaction manager rolls back when unchecked `DataAccessException` escapes the transaction boundary.
- Original exception remains preserved in `cause`, without exposing sensitive messages in API responses.
- Whether the system uses reactive data access or regular AOP proxies: apply this guidance strictly to the bean/interceptor model in use; do not extrapolate automatically to different reactive pipelines.

## 13. Exception Translation Differs from Transactions, HTTP Error Mapping, and Retries

These are independent concerns that are frequently confused:

**Exception translation:** a native error can be represented as a subclass of `DataAccessException`. Doing so does not make the SQL succeed or automatically recover the connection.

**Transaction rollback:** when an unchecked exception escapes a `@Transactional`-managed method, Spring marks rollback by default per standard rollback rules (unless configured otherwise). Translating errors helps upper layers recognize the failure, but `@Repository` itself does not decide commit or rollback.

**HTTP response:** `DuplicateKeyException` does not automatically mean HTTP 409 or an application-formatted JSON response. The API layer can use `@ControllerAdvice`/exception handlers to map it to an appropriate status code without exposing SQL/stack traces.

**Retry:** do not automatically retry every `DataAccessException`. For example, retrying a unique constraint violation with the same data only produces pointless duplicate requests; for connection drops or deadlocks, retries also require verifying idempotency and transaction state. Transient/non-transient subclasses aid classification, not replace business decisions.

A maintainable organization:

~~~text
HTTP/Controller
    ↓
Service (@Transactional when business work spans multiple steps)
    ↓
Repository (@Repository)
    ↓
JDBC/JPA/Hibernate/provider
    ↑ native exception
Spring JDBC translator or Repository AOP translator
    ↑ DataAccessException (if mappable)
Service decides business rules / rollback / bounded retry
    ↑
API exception handler decides HTTP response
~~~

The translation paths in the diagram vary by technology: `JdbcTemplate` and repository AOP are not always two sequential steps, and certain transaction errors may be converted at the transaction manager.

## 14. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Adding `@Repository` turns all errors into `DataAccessException`" | Requires BeanPostProcessor/advisor, matching translator, proxy boundary, and compatible exception type |
| "The post-processor knows every database's error codes" | It coordinates translators; actual mapping is handled by translators/providers |
| "`@Component` and `@Repository` are completely identical" | Same component-scan capability, but `@Repository` is the dedicated marker for persistence translation |
| "`@Repository` equals `@Transactional`" | Annotation marks the DAO layer; transactions require separate infrastructure/config |
| "Spring always translates exceptions when `EntityManager.persist` is called" | DB may detect errors later at flush/commit, outside the repository AOP boundary |
| "Proxy intercepts every call on the same object" | Self-invocation does not open another advice round; external calls through the proxy are intercepted |
| "`JdbcTemplate` needs the post-processor to translate `SQLException`" | `JdbcTemplate` translates `SQLException` internally inside the template |
| "Translators should catch all `RuntimeException`s" | Translators should handle only error types they understand; return `null` for others |
| "Getting `DataAccessException` means the operation rolled back" | Rollback depends on transaction boundaries and transaction configuration |
| "`DuplicateKeyException` automatically returns HTTP 409" | HTTP error mapping is the responsibility of the API/handler layer |

## 15. Practical Adoption Workflow

When building a repository backed by a persistence API that throws native runtime exceptions:

1. Annotate the implementation with `@Repository` so Spring manages the object via component scanning or bean declaration.
2. Verify the context has `PersistenceExceptionTranslationPostProcessor` (plain Spring Framework: add config; Spring Boot: check auto-configuration).
3. Verify a `PersistenceExceptionTranslator` compatible with your technology exists; add a custom translator only when needed.
4. Write a test where a service calls the injected repository bean and intentionally triggers a well-defined native error.
5. Assert the right `DataAccessException` subclass and original `cause`; also test that unmapped errors remain intact.
6. Check where errors surface during flush/commit and verify transaction policies.
7. Only then design retries, business messages, and HTTP mappings. Keep diagnostic logs server-side and avoid exposing SQL or sensitive data to end users.

**Core principle to remember:** `@Repository` selects **the right layer and bean**; `PersistenceExceptionTranslationPostProcessor` sets up the **AOP advice**; `PersistenceExceptionTranslator` decides **which errors can be translated and into which `DataAccessException`**. If one link is missing or calls bypass the proxy, the application may still see native exceptions. Accurate translation must be proven through tests with your actual technology and transaction boundaries.

## References

- [Spring Framework Reference — Exception Translation in ORM integration](https://docs.spring.io/spring-framework/reference/data-access/orm/general.html): purpose, `@Repository`, and post-processor.
- [Spring Framework Javadoc — PersistenceExceptionTranslationPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/dao/annotation/PersistenceExceptionTranslationPostProcessor.html): advised bean scope, AOP proxy, and translator discovery.
- [Spring Framework Javadoc — PersistenceExceptionTranslator](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/dao/support/PersistenceExceptionTranslator.html): mapping or returning `null` contract.
- [Spring Framework Javadoc — PersistenceExceptionTranslationInterceptor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/dao/support/PersistenceExceptionTranslationInterceptor.html): advice and preservation of exceptions declared in method signatures.
- [Spring Framework Reference — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate` and `SQLException` translation mechanism.
- [Spring Boot 3.2 API — PersistenceExceptionTranslationAutoConfiguration](https://docs.spring.io/spring-boot/docs/3.2.12/api/org/springframework/boot/autoconfigure/dao/PersistenceExceptionTranslationAutoConfiguration.html): Spring Boot 3.x auto-configuration conditions.

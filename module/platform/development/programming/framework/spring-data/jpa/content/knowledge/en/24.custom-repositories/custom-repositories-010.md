# Testing Repository Fragments and Ensuring Configuration Is Applied

Repository fragments let you add custom behavior to a Spring Data JPA repository by composing an interface with a matching implementation class. A good test needs to prove three things: Spring Data composed the fragment into the repository proxy, the custom repository configuration was loaded in the application context, and the fragment method actually queries data through JPA.

This article uses Java 17+, Spring Boot 3.x, Spring Data JPA, JUnit 5, AssertJ, and H2 for the test example. The classes below belong to a Spring Boot project with the appropriate JPA and test dependencies; they are not a standalone Java program that can be executed with `javac` alone.

## 1. Understanding Repository Fragments Properly

A fragment consists of two parts:

- An interface declaring the custom behavior.
- An implementation class fulfilling that behavior.

The main repository extends both `JpaRepository` and the fragment interface. Spring Data creates the repository proxy by combining the default CRUD implementation with discovered fragments.

Example package structure:

```text
com.example.customer
├── Customer.java
├── CustomerRepository.java
├── CustomerSearch.java
├── CustomerSearchExtension.java
└── CustomerJpaRepositoryConfig.java
```

The implementation class name is formed from the fragment interface name plus the configured postfix. The default postfix is `Impl`; for instance, `CustomerSearch` typically pairs with `CustomerSearchImpl`. If the postfix is configured as `Extension`, the implementation class must be named `CustomerSearchExtension`.

The implementation class must lie within a package scanned by Spring Data for repository implementations. The easiest layout to control places the repository, fragment interface, and implementation class in the same package or in subpackages within the scan scope.

Fragments differ from a custom repository base class. A fragment adds a group of behaviors to specific repositories; `repositoryBaseClass` changes the shared foundation class for configured repositories. Do not use these two mechanisms interchangeably.

## 2. Creating the Entity, Fragment, and Repository

**Customer.java**

```java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
        // JPA requires a no-arg constructor.
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

**CustomerSearch.java** — fragment interface:

```java
package com.example.customer;

import java.util.List;

public interface CustomerSearch {
    List<Customer> findByNamePrefix(String prefix);
}
```

The method name `findByNamePrefix` intentionally does not correspond to an entity property: `Customer` only has a `name` property, not `namePrefix`. Consequently, the method succeeds only if Spring Data discovers and composes the fragment implementation properly. This helps the test catch wiring mistakes instead of accidentally executing a derived query.

**CustomerSearchExtension.java** — fragment implementation class:

```java
package com.example.customer;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;

public class CustomerSearchExtension implements CustomerSearch {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public List<Customer> findByNamePrefix(String prefix) {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalArgumentException("prefix must not be blank");
        }

        return entityManager.createQuery(
                "select c from Customer c "
                    + "where c.name like :pattern "
                    + "order by c.name",
                Customer.class
            )
            .setParameter("pattern", prefix + "%")
            .getResultList();
    }
}
```

Spring manages fragment classes discovered during repository creation. Thus, `EntityManager` can be injected via `@PersistenceContext`; never instantiate the implementation manually with `new CustomerSearchExtension()`. If the implementation needs extra dependencies, let Spring inject them through the appropriate mechanism.

**CustomerRepository.java** — composing the fragment into the repository:

```java
package com.example.customer;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerSearch {
}
```

Once the repository is created, calls to `findByNamePrefix` are routed to the `CustomerSearch` fragment. Standard CRUD methods remain supplied by `JpaRepository`.

## 3. Declaring the Repository Configuration to Test

In this example, we change the implementation postfix from the default `Impl` to `Extension`. That configuration must match the class name `CustomerSearchExtension`.

**CustomerJpaRepositoryConfig.java**

```java
package com.example.customer;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackageClasses = CustomerRepository.class,
    repositoryImplementationPostfix = "Extension"
)
public class CustomerJpaRepositoryConfig {
}
```

`basePackageClasses` instructs Spring Data to scan the package containing `CustomerRepository`. In the example, the fragment interface and implementation reside in the same package, so they fall within the discovery scope as well. If the implementation is placed in another package, adjust the structure or scan scope so Spring Data can find it.

In a Spring Boot application, `@EnableJpaRepositories` may already live in production configuration. In that case, the test should load that exact production configuration class. Do not create a second repository scanning configuration if the application already has one.

## 4. Writing the Integration Test for the Fragment

Use `@DataJpaTest` to test the repository inside a JPA-focused Spring context. This annotation configures entities, repositories, and test transactions; when H2 is on the test classpath, Spring Boot typically uses an embedded database. Tests roll back after each test method.

**CustomerRepositoryTest.java**

```java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.annotation.Import;

@DataJpaTest
@Import(CustomerJpaRepositoryConfig.class)
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void composesCustomFragmentAndUsesConfiguredPostfix() {
        entityManager.persist(new Customer("Anna"));
        entityManager.persist(new Customer("Bao"));
        entityManager.persist(new Customer("An"));

        // Flush changes to the database before executing the query.
        entityManager.flush();

        // Clear the persistence context so results must be reloaded via JPA.
        entityManager.clear();

        List<String> actualNames = repository.findByNamePrefix("An")
            .stream()
            .map(Customer::getName)
            .toList();

        assertThat(actualNames).containsExactly("An", "Anna");
    }
}
```

Three key points in this test:

1. `@Import(CustomerJpaRepositoryConfig.class)` loads the repository configuration under test into the test context. A test slice has a narrow scope, so a regular application configuration class might not be loaded automatically.
2. The configuration sets the postfix to `Extension`, while the implementation is named `CustomerSearchExtension`. Changing one while forgetting the other causes Spring Data to miss the right implementation.
3. The test calls `repository.findByNamePrefix("An")` directly and checks the query result. Because the entity has no `namePrefix` property, succeeding with accurate data proves the fragment was composed and executed. `flush()` ensures test data is sent to the database; `clear()` evicts entities held in the persistence context prior to querying.

The expected outcome is a passing test with the ordered list `An`, `Anna`. There is no need to add `System.out.println`; assertions are the test evidence. This is an integration test running inside a Spring context, not a pure Java unit test.

## 5. Ensuring the Test Uses the Intended Configuration

When testing repository configuration, clarify which configuration must be proven:

- To verify fragment discovery, confirm the repository extends the fragment interface, the implementation uses the right postfix name, and it sits in a scanned package.
- If the application sets `repositoryImplementationPostfix`, the test must load the configuration declaring that attribute. In the example, `@Import` does this explicitly.
- If repository configuration lives in main application configuration and you need to verify full application wiring, you can use `@SpringBootTest`. This loads the full application context and is usually slower than `@DataJpaTest`.
- When using `@DataJpaTest` with production configuration, import the exact configuration under test. Do not declare a new `@EnableJpaRepositories` inside the test just to make it pass, as that would test a different configuration from production.
- To verify database-specific behavior, run tests against the same database engine or Testcontainers. H2 is useful for fast tests, yet it does not prove all differences in dialect, collation, data types, or locking found in production databases.

If the application uses a custom base class instead of a fragment, the configuration normally sets `repositoryBaseClass` on `@EnableJpaRepositories`. In that case, the test should invoke a behavior present only in the base class or assert that behavior's effect. Merely verifying the context starts does not prove the intended base class was applied.

## 6. Common Errors and Narrowing Down Causes

| Symptom | Common Cause | How to Check |
|---|---|---|
| Context fails to create query or cannot find property `namePrefix` | Fragment implementation was not discovered, so Spring Data attempts to parse the method as a derived query | Verify repository extends `CustomerSearch`, implementation name matches postfix, and package lies in scan scope |
| Fragment not composed even though class exists | Wrong class name, mismatched configured postfix, or class outside scan package | Compare interface name, implementation name, and `repositoryImplementationPostfix`; check `basePackageClasses` or `basePackages` |
| `EntityManager` or dependencies in implementation are not injected | Implementation is not properly managed by Spring or dependency lacks a bean | Let Spring Data discover the implementation; use `@PersistenceContext` or constructor injection; never instantiate with `new` |
| Test passes in `@SpringBootTest` but fails in `@DataJpaTest` | Test slice does not load the required application configuration class | Use `@Import` for the specific configuration or `@SpringBootTest` when full context is needed |
| Test results do not reflect newly persisted data | Missing flush or persistence context still caches entities | Call `flush()` before querying; use `clear()` when verifying database reload |
| Test passes even when fragment is ignored | Fragment method collides with a valid derived query or repository was mocked | Use a method name handled only by the fragment and keep the real repository in integration tests |

Do not mock `CustomerRepository` in this test. Mocking the repository only tests mock behavior and fails to verify Spring Data composition, JPA queries, or discovery configuration. You may mock an external service that the fragment depends on, while keeping the repository and JPA context real whenever wiring is the goal.

## 7. Running and Extending the Tests

With Maven Wrapper:

```bash
./mvnw -Dtest=CustomerRepositoryTest test
```

On Windows:

```bat
mvnw.cmd -Dtest=CustomerRepositoryTest test
```

With Gradle Wrapper:

```bash
./gradlew test --tests "com.example.customer.CustomerRepositoryTest"
```

The expected result is one executed test with zero failures. Exact output depends on Maven/Gradle versions and project settings, so rely on the test report status and assertions.

You can expand the test suite for meaningful scenarios:

- Empty or `null` prefix: verify the fragment's validation rules.
- No matching records: verify the result is an empty list.
- Multiple records sharing a prefix: verify result ordering and stability.
- Data containing Vietnamese characters or special collation rules: test against the corresponding database if behavior depends on the engine.
- Fragment using additional configuration beans: verify those beans are imported or created in the application context and assert observable behavior when invoking methods.

A fragment test is adequate when it proves the repository proxy composed the right implementation, the actual discovery configuration was loaded, and the custom behavior returns accurate results from the persistence layer.
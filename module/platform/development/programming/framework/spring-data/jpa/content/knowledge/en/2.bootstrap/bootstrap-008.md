# Package Organization and Entity / Repository Scanning Scope in Spring Data JPA

## 1. Why Package Organization and Scan Configuration Matter

In a Spring Boot application using Spring Data JPA, classes are typically organized by responsibility: controllers handle requests, services handle business logic, repositories handle data access, and entities represent data mapped to database tables.

Spring does not automatically scan every class on the entire classpath under a single rule. Different scanning mechanisms have distinct scopes and purposes:

- **Component scanning** discovers beans such as `@Component`, `@Service`, `@Controller`, `@RestController`, `@Configuration`, and component-style annotations.
- **Entity scanning** discovers JPA classes annotated with `@Entity`, along with related mapping metadata such as `@Embeddable` and `@MappedSuperclass`.
- **Repository scanning** discovers Spring Data interfaces (typically extending `Repository`, `CrudRepository`, or `JpaRepository`) to generate proxy objects that execute data access.

Proper package organization helps Spring Boot locate beans, entities, and repositories at startup. If these scopes do not cover the packages containing the corresponding classes, the application may fail to start or fail to create required beans.

## 2. Placing the Entry Point Class in the Root Package

`@SpringBootApplication` is typically placed on the main class in the application's root package. Feature packages should be subpackages of this root package.

Example feature-based structure:

~~~text
com.example.shop
├── ShopApplication.java
├── config
│   └── SecurityConfig.java
├── customer
│   ├── api
│   │   └── CustomerController.java
│   ├── application
│   │   └── CustomerService.java
│   ├── domain
│   │   └── Customer.java
│   └── persistence
│       └── CustomerRepository.java
└── order
    ├── api
    ├── application
    ├── domain
    └── persistence
~~~

Entry point class:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

When `ShopApplication` resides in `com.example.shop`, subpackages such as `com.example.shop.customer` and `com.example.shop.order` fall within the default scope. Spring Boot can locate components, entities, and repositories in this subpackage structure using their respective scanning mechanisms.

Avoid placing the main class in a deeply nested leaf package, such as `com.example.shop.bootstrap`, if `customer` and `order` are sibling packages outside `bootstrap`. Default scanning from `bootstrap` will not walk upward to `com.example.shop` to find sibling packages.

Also avoid placing the main class in the **default package** (without a `package` declaration). That layout makes scan boundaries difficult to control and may force Spring to inspect too many classes on the classpath.

## 3. Three Scanning Scopes to Distinguish

### 3.1. Component Scanning: Discovering Spring Beans

`@SpringBootApplication` includes `@ComponentScan`. By default, component scanning starts from the annotated class's package and traverses downward into subpackages.

Commonly detected stereotypes:

- `@Component`: general-purpose bean.
- `@Service`: business logic class.
- `@Repository`: manually implemented data access bean.
- `@Controller` and `@RestController`: web request handler classes.
- `@Configuration`: Spring configuration class.

For example, `CustomerService` located in `com.example.shop.customer.application` and annotated with `@Service` will be detected if the root package is `com.example.shop`.

~~~java
package com.example.shop.customer.application;

import org.springframework.stereotype.Service;

@Service
public class CustomerService {
    // Customer business logic.
}
~~~

Component scanning is not meant to register every Java class as a bean. An entity annotated only with `@Entity` does not become a `@Component` bean. Spring Data repository interfaces are also backed by proxies created through repository scanning, not merely through standard component scanning.

### 3.2. Entity Scanning: Discovering JPA Entity Classes

Entities are classes managed by JPA and mapped to relational data. Example:

~~~java
package com.example.shop.customer.domain;

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

    private String name;

    protected Customer() {
        // Constructor required by JPA.
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
~~~

In a standard Spring Boot setup, entity packages are determined from the application's root package (the auto-configuration base package). Therefore, if `Customer` resides under `com.example.shop`, `@EntityScan` is usually unnecessary.

If entities reside outside the root package, you can specify the scope explicitly using `@EntityScan`:

~~~java
import org.springframework.boot.autoconfigure.domain.EntityScan;

@EntityScan(basePackages = {
    "com.example.shop.customer.domain",
    "com.example.shared.persistence.entity"
})
~~~

`basePackages` accepts the package names to scan. You can use `basePackageClasses` to reference a marker class in each package, avoiding typos in package names during code refactoring.

For example, if you have the `Customer` class in the entity package and a `SharedEntityMarker` marker class in the shared entity package:

~~~java
@EntityScan(basePackageClasses = {
    Customer.class,
    SharedEntityMarker.class
})
~~~

The declared scope will include the packages of those representative classes and their subpackages.

### 3.3. Repository Scanning: Discovering Interfaces and Creating Repository Proxies

Spring Data JPA locates repository interfaces and generates proxy objects so the application can invoke data operations. Interfaces do not need manual implementation classes for CRUD methods inherited from `JpaRepository`.

Example:

~~~java
package com.example.shop.customer.persistence;

import com.example.shop.customer.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

With packages located under `com.example.shop`, Spring Boot usually detects repositories in the root package and its subpackages automatically. If repositories lie outside the default scope, configure `@EnableJpaRepositories`:

~~~java
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@EnableJpaRepositories(basePackages = {
    "com.example.shop.customer.persistence",
    "com.example.shared.persistence.repository"
})
~~~

Or reference representative classes/interfaces in a more type-safe way:

~~~java
@EnableJpaRepositories(basePackageClasses = {
    CustomerRepository.class,
    SharedRepositoryMarker.class
})
~~~

`@EnableJpaRepositories` specifies packages containing repository interfaces to register. It does not replace `@EntityScan`: Spring may find `CustomerRepository` yet still fail to manage `Customer` if the entity package lies outside the entity scan scope.

## 4. Configuring When Entities and Repositories Live Outside the Root Package

Suppose the application's main package is `com.example.shop`, while a shared module lives in `com.example.shared`:

~~~text
com.example.shop
├── ShopApplication.java
├── customer
│   ├── application
│   ├── domain
│   └── persistence
└── order
    ├── domain
    └── persistence

com.example.shared
├── service
├── persistence
│   ├── entity
│   └── repository
└── config
~~~

Three scopes must be considered separately:

1. Components in `com.example.shared` must be found by component scanning.
2. Entities in `com.example.shared.persistence.entity` must be found by entity scanning.
3. Repositories in `com.example.shared.persistence.repository` must be found by repository scanning.

Illustrative configuration for Spring Boot 3+:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication(scanBasePackages = {
    "com.example.shop",
    "com.example.shared"
})
@EntityScan(basePackages = {
    "com.example.shop.customer.domain",
    "com.example.shop.order.domain",
    "com.example.shared.persistence.entity"
})
@EnableJpaRepositories(basePackages = {
    "com.example.shop.customer.persistence",
    "com.example.shop.order.persistence",
    "com.example.shared.persistence.repository"
})
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

In this example:

- `scanBasePackages` expands the **component scanning** scope.
- `@EntityScan` expands the **entity scanning** scope.
- `@EnableJpaRepositories` expands the **repository scanning** scope.

A common misconception: the `scanBasePackages` attribute on `@SpringBootApplication` is an alias for component scan scope. It **does not automatically expand the auto-configuration base package** used as the default for discovering entities and Spring Data repositories. Therefore, simply adding `com.example.shared` to `scanBasePackages` is often insufficient for JPA to discover entities and repositories in that module.

If all entities, repositories, and components reside under the root package, prefer the default configuration and keep the main class in the proper location. Only declare extra scopes when the architecture genuinely places packages outside the root.

## 5. Comparison Table of the Three Mechanisms

| Mechanism | Typical Annotation | What Does It Find? | When Is Custom Configuration Needed? |
|---|---|---|---|
| Component scanning | `@ComponentScan`, `@SpringBootApplication` | Beans such as service, controller, component, configuration | Beans lie outside the default root package |
| Entity scanning | `@EntityScan` | JPA mapping classes such as entities and related metadata | Entities lie outside the default auto-configuration package |
| Repository scanning | `@EnableJpaRepositories` | Spring Data interfaces for creating repository proxies | Repositories lie outside the default package or need explicit scoping |

You can remember this with three questions:

- Can Spring find `CustomerService` to inject? Check component scan.
- Can JPA manage the `Customer` class? Check entity scan.
- Can Spring Data create the `CustomerRepository` bean? Check repository scan.

The three mechanisms can share the same root package, but they are not a single mechanism.

## 6. Common Errors and How to Diagnose the Cause

### 6.1. `Not a managed type: ...`

Example:

~~~text
Not a managed type: class com.example.shared.persistence.entity.Customer
~~~

This message usually means the current JPA `EntityManager` does not recognize the class referenced by the repository as a managed entity.

What to check:

1. Is the class annotated with `@Entity` using the right namespace?
2. Is the package containing the class within the entity scan scope?
3. Does `@EntityScan` point to the right package?
4. If multiple `EntityManagerFactory` beans exist, is the entity bound to the right persistence unit?

Adding `@ComponentScan` generally does not solve this error because component scanning does not replace entity scanning.

### 6.2. Repository Bean Not Found

Example:

~~~text
No qualifying bean of type 'CustomerRepository' available
~~~

What to check:

1. Does the interface extend `Repository`, `CrudRepository`, `JpaRepository`, or an appropriate Spring Data repository?
2. Is the interface's package within the repository scanning scope?
3. Does the application have the Spring Data JPA dependency and valid JPA configuration?
4. If using `@EnableJpaRepositories`, are the declared packages accurate?
5. If multiple datasources exist, is the repository configured with the right `EntityManagerFactory` and transaction manager?

A repository interface does not get a bean created merely by sitting in a component-scanned package. Spring Data's repository scanning mechanism is required.

### 6.3. Service or Controller Bean Not Found

If the error occurs when injecting `CustomerService` or a controller, check the class's package and corresponding component annotation. This falls under component scanning, not entity scanning.

### 6.4. Overly Broad or Overlapping Scanning

Scanning from an overly broad package such as `com` can cause the application to pick up components, repositories, or configurations that do not belong to the application. This can lead to bean conflicts, unintended configurations, and slower startup times.

Choose a sufficiently specific root package, such as `com.example.shop`, and explicitly declare external packages when needed. Avoid declaring the same scope multiple times without a specific architectural reason.

## 7. Practical Package Organization Guidelines

A small application can be organized by layer:

~~~text
com.example.shop
├── ShopApplication.java
├── controller
├── service
├── repository
├── entity
└── config
~~~

This is easy to start with for small applications, though as features grow, layer packages can end up containing many unrelated classes.

For larger applications, organizing by feature keeps related parts close together:

~~~text
com.example.shop
├── ShopApplication.java
├── customer
│   ├── api
│   ├── application
│   ├── domain
│   └── persistence
├── order
│   ├── api
│   ├── application
│   ├── domain
│   └── persistence
└── config
~~~

Whichever layout you choose, follow these principles:

- Place the `@SpringBootApplication` class in a root package covering the main modules.
- Keep entities and repositories in subpackages of the root whenever possible to leverage default scanning.
- Name packages to reflect responsibility; avoid dumping every class into a single shared package.
- Expand component, entity, and repository scans to external packages only when truly needed.
- Use `basePackageClasses` when you want to reference packages via Java types instead of package name strings.
- Do not add `@Component` to an entity just to try making component scan see it.
- Do not confuse Spring finding a repository interface with JPA recognizing that repository's entity.

If the application has multiple datasources or multiple persistence units, configuration also needs to separate repository packages, entity manager factories, and transaction managers accordingly. In such cases, explicitly configure each repository group with `entityManagerFactoryRef` and `transactionManagerRef` rather than relying entirely on defaults.

## 8. Application Startup Checklist

When creating a Spring Data JPA module or reorganizing packages, check in this order:

1. **Root package:** Is the main class in a common parent package of the modules to be scanned?
2. **Components:** Are services, controllers, and configurations within component scan scope with the right annotations?
3. **Entities:** Do classes have `@Entity` and lie within entity scan scope?
4. **Repositories:** Do interfaces extend a Spring Data repository and lie within repository scan scope?
5. **Repository/entity pairing:** Are the entity type and ID type in `JpaRepository<Entity, IdType>` accurate?
6. **Namespace and dependencies:** Spring Boot 3+ uses `jakarta.persistence`; older Spring Boot 2 projects usually use `javax.persistence`. Do not mix the two namespaces in the same application.
7. **Datasource:** Are the connection configuration and driver valid? Database connection failures are distinct from package-scanning errors.
8. **Multiple datasources:** Are repositories bound to the right entity manager factory and transaction manager?

For Spring Boot 3+ projects, the JPA imports in these examples use `jakarta.persistence`. If maintaining an older Spring Boot 2 project, use that version's corresponding namespace and verify compatibility across Spring Boot, Spring Data JPA, and the JPA provider.

## 9. Takeaways

Package organization determines the default scope from which Spring Boot begins scanning. Placing the main class in the root package allows subpackage structures to be discovered naturally with minimal configuration.

When expanding into external packages, clearly identify the type of object you need to find:

- Spring beans: `@ComponentScan` or `scanBasePackages`.
- JPA entities: `@EntityScan`.
- Spring Data repositories: `@EnableJpaRepositories`.

Never assume expanding one scope automatically expands the other two. Checking the right mechanism pinpoints the root cause quickly when a service fails to inject, a repository proxy fails to be created, or JPA reports an unmanaged entity.
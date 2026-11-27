# RepositoryDetectionStrategy: DEFAULT, ALL, VISIBILITY, and ANNOTATED

## 1. Objective

Spring Data REST can automatically expose Spring Data repositories as HTTP resources. For example, a repository managing Customer can generate a collection resource at `/customers`, an item resource at `/customers/{id}`, and search endpoints if the repository declares matching query methods.

Not every repository in an application should become a public API. **RepositoryDetectionStrategy** determines which repositories are detected and exposed by Spring Data REST. This strategy is configured in `RepositoryRestConfiguration`.

There are four commonly used options:

- **DEFAULT**: exposes public repositories by default; non-public repositories can be explicitly opted in with an annotation.
- **ALL**: exposes every repository recognized by Spring Data, regardless of visibility or annotation.
- **VISIBILITY**: only exposes repository interfaces with the `public` modifier.
- **ANNOTATED**: only exposes repositories explicitly marked with an appropriate annotation.

The default in Spring Data REST is **DEFAULT**.

## 2. Distinguishing the Four Strategies

### DEFAULT

This is the default option and fits typical Spring Data REST usage.

- Repository interfaces with the `public` modifier are exposed.
- Non-public repository interfaces are hidden, unless explicitly marked with `@RepositoryRestResource` with `exported = true` (the default value of this attribute).
- If a repository is marked with `@RepositoryRestResource(exported = false)`, that repository is not exposed, even if the interface is public.

Example:

    public interface CustomerRepository extends JpaRepository<Customer, Long> {
    }

With DEFAULT, `CustomerRepository` is exposed because the interface is public.

An internal repository may be non-public:

    interface InternalAuditRepository extends JpaRepository<AuditLog, Long> {
    }

With DEFAULT, this repository is not exposed. If you genuinely want to expose it, you can mark it explicitly:

    @RepositoryRestResource(path = "internal-audits")
    interface InternalAuditRepository extends JpaRepository<AuditLog, Long> {
    }

### ALL

ALL selects every repository recognized by Spring Data, without considering Java modifiers or annotation configuration.

This means package-private repositories can also be exposed. The `exported = false` annotation does not act as a filter under this strategy; when ALL is selected, a repository with that annotation is still considered for exposure.

For example, both of the following interfaces are selected:

    public interface CustomerRepository extends JpaRepository<Customer, Long> {
    }

    interface InternalAuditRepository extends JpaRepository<AuditLog, Long> {
    }

ALL can be useful during experimentation or when you truly want to expose every repository. In applications with many internal repositories, this strategy can easily expose unintended endpoints.

### VISIBILITY

VISIBILITY only checks the visibility of the repository interface:

- Public interfaces are exposed.
- Package-private interfaces or those with lower visibility are not exposed.
- Annotations do not alter this strategy's decision. Therefore, a package-private repository remains hidden even with `@RepositoryRestResource`; conversely, a public repository is still selected even if the annotation sets `exported = false`.

Example:

    @RepositoryRestResource(path = "internal-audits")
    interface InternalAuditRepository extends JpaRepository<AuditLog, Long> {
    }

The repository above is still not exposed under VISIBILITY because the interface is not public.

VISIBILITY fits when the application's rules rely solely on Java visibility. If you need to actively select individual repositories, consider ANNOTATED.

### ANNOTATED

ANNOTATED uses an opt-in approach: a repository must be explicitly marked to be exposed.

- A public repository without an appropriate annotation will not be exposed.
- A repository marked with `@RepositoryRestResource` and without `exported = false` will be exposed.
- A repository with `@RepositoryRestResource(exported = false)` is excluded from exposure.
- A marked repository can be exposed even if the interface is not public.

Example:

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository extends JpaRepository<Customer, Long> {
    }

The repository above is exposed at collection path `/customers`.

The following repository is not exposed:

    @RepositoryRestResource(exported = false)
    public interface SecretRepository extends JpaRepository<Secret, Long> {
    }

The enum Javadoc also mentions `@RestResource` in the annotation criteria. For repository-level configuration, `@RepositoryRestResource` is the most direct, readable, and commonly used marker.

## 3. Comparison Table

The table below assumes all repositories are recognized by Spring Data and lie within the package scanning scope.

| Repository interface | DEFAULT | ALL | VISIBILITY | ANNOTATED |
|---|---:|---:|---:|---:|
| public, no annotation | Yes | Yes | Yes | No |
| package-private, no annotation | No | Yes | No | No |
| public, with `@RepositoryRestResource` | Yes | Yes | Yes | Yes |
| package-private, with `@RepositoryRestResource` | Yes | Yes | No | Yes |
| public, `exported = false` | No | Yes | Yes | No |
| package-private, `exported = false` | No | Yes | No | No |

Two easily confused points:

1. **DEFAULT and ANNOTATED** respect the annotation's `exported` attribute. DEFAULT also automatically selects public repositories; ANNOTATED requires explicit marking.
2. **ALL and VISIBILITY** ignore annotation settings when deciding whether to select a repository. Therefore, do not rely on `exported = false` to hide a repository when using ALL or VISIBILITY.

## 4. Configuring the Strategy

You can configure the strategy via a bean implementing `RepositoryRestConfigurer`. The example below switches the entire application to ANNOTATED so that only explicitly marked repositories are exposed.

    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
    import org.springframework.data.rest.core.mapping.RepositoryDetectionStrategy.RepositoryDetectionStrategies;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
    import org.springframework.web.servlet.config.annotation.CorsRegistry;

    @Configuration
    public class SpringDataRestConfig implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            config.setRepositoryDetectionStrategy(
                    RepositoryDetectionStrategies.ANNOTATED
            );
        }
    }

Change the enum value to select another strategy:

    RepositoryDetectionStrategies.DEFAULT
    RepositoryDetectionStrategies.ALL
    RepositoryDetectionStrategies.VISIBILITY
    RepositoryDetectionStrategies.ANNOTATED

A shorter way, in versions that support `RepositoryRestConfigurer.withConfig`, is:

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return RepositoryRestConfigurer.withConfig(config ->
            config.setRepositoryDetectionStrategy(
                RepositoryDetectionStrategies.ANNOTATED
            )
        );
    }

**Version note:** the signature of `configureRepositoryRestConfiguration` varies across Spring Data REST generations. The example above uses the current signature with the `CorsRegistry` parameter. If your project uses an older version, check the Javadoc matching your installed dependency and use the signature provided by that version.

## 5. Example of Selecting Repositories as Needed

Suppose an application has three repositories:

    public interface ProductRepository extends JpaRepository<Product, Long> {
    }

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository extends JpaRepository<Customer, Long> {
    }

    @RepositoryRestResource(exported = false)
    public interface CredentialRepository extends JpaRepository<Credential, Long> {
    }

Expected results:

- With DEFAULT: ProductRepository and CustomerRepository are exposed; CredentialRepository is hidden.
- With ALL: all three repositories are exposed, including CredentialRepository.
- With VISIBILITY: all three are public so all three are exposed; the annotation does not exclude CredentialRepository.
- With ANNOTATED: only CustomerRepository is exposed; ProductRepository has no annotation and CredentialRepository is marked exported=false.

If you add a package-private repository with `@RepositoryRestResource`, that repository is exposed under DEFAULT and ANNOTATED, exposed under ALL, and hidden under VISIBILITY.

## 6. Verifying Results After Configuration

After restarting the application, inspect the Spring Data REST root resource. The HAL root typically lists relation links to exposed collection resources.

    curl -i http://localhost:8080/

If the application has CustomerRepository with path `customers`, try:

    curl -i http://localhost:8080/customers

When checking, confirm:

1. Expected exposed repositories have links in the root resource and their collection endpoints respond.
2. Expected hidden repositories do not appear in the link list and their endpoints are not served.
3. Package-private repositories match the chosen strategy's behavior.
4. If the application configures a base path, prepend the base path to the test URLs.

Exact HTTP results may depend on application configuration and Spring Security. Not exposing a repository via Spring Data REST does not replace authentication and authorization. Exposed endpoints still require appropriate security configuration.

## 7. Which Strategy Should You Choose?

| Requirement | Suitable Choice |
|---|---|
| Keep default behavior: public repositories are exposed | DEFAULT |
| Expose only repositories explicitly opted in | ANNOTATED |
| Rely solely on Java public/package-private visibility | VISIBILITY |
| Expose every recognized repository | ALL |

In production APIs, ANNOTATED is often an easy-to-control choice when you want per-repository opt-in. DEFAULT fits when most public repositories are meant to become REST resources. ALL requires careful consideration because it may expose internal repositories as well.

If exposure rules are more complex than these four options, you can implement `RepositoryDetectionStrategy` yourself and define the logic in the `isExported(RepositoryMetadata metadata)` method.

## 8. Practice Exercise

An application has the following repositories:

- `OrderRepository`: public, no annotation.
- `PaymentRepository`: public, with `@RepositoryRestResource`.
- `InternalLogRepository`: package-private, with `@RepositoryRestResource`.
- `AdminRepository`: public, with `@RepositoryRestResource(exported = false)`.

Determine which repositories are exposed when selecting DEFAULT, ALL, VISIBILITY, and ANNOTATED in turn. Then configure ANNOTATED, start the application, and inspect the root resource to confirm only the selected repositories appear.

**Answer key for self-check:**

| Repository | DEFAULT | ALL | VISIBILITY | ANNOTATED |
|---|---:|---:|---:|---:|
| OrderRepository | Yes | Yes | Yes | No |
| PaymentRepository | Yes | Yes | Yes | Yes |
| InternalLogRepository | Yes | Yes | No | Yes |
| AdminRepository | No | Yes | Yes | No |

## 9. Key Takeaways

- RepositoryDetectionStrategy decides which repositories Spring Data REST exposes as HTTP resources.
- DEFAULT is the default: public repositories are selected; annotations can opt in non-public repositories or exclude repositories with `exported = false`.
- ALL selects all recognized repositories.
- VISIBILITY selects only public interfaces and ignores annotations.
- ANNOTATED requires repositories to be explicitly marked and not set to `exported = false`.
- Repository detection strategies are not API authentication or authorization mechanisms.

## References

- Spring Data REST Reference — Customizing repository exposure: https://www.springframework.org/spring-data/rest/reference/5.1/customizing-sdr.html
- Spring Data REST Javadoc — RepositoryDetectionStrategies: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/mapping/RepositoryDetectionStrategy.RepositoryDetectionStrategies.html
- Spring Data REST Javadoc — RepositoryRestConfigurer: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html

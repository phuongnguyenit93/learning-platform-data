# Rules for Deriving Default Paths from Domain Type Names

## Objectives

Spring Data REST automatically generates the path for a repository's collection resource based on the **domain type** managed by that repository. When no custom path is configured, the collection name is derived from the domain class name: lowercasing the first letter and pluralizing the name according to English rules.

For example, a repository managing `Order` is typically exposed at `/orders`; a repository managing `Person` is exposed at `/people`.

## Where Does Spring Data REST Get the Name?

The default path is derived from the simple name of the domain type—that is, the class name without its package. Spring Data REST does not derive the name from the repository interface, database table name, or column names.

For example:

    @Entity
    public class PurchaseOrder {
        @Id
        private Long id;
        // ...
    }

    public interface PurchaseOrderRepository
            extends JpaRepository<PurchaseOrder, Long> {
    }

The repository's domain type is `PurchaseOrder`, so the default collection name is `purchaseOrders`. The interface name `PurchaseOrderRepository` does not become the path `purchaseOrderRepositories`.

The rule can be understood in the following steps:

1. Identify the domain type in the repository's generic parameter; for example, `JpaRepository<PurchaseOrder, Long>` has the domain type `PurchaseOrder`.
2. Take the simple name of the class, excluding the package.
3. Lowercase the first letter of the class name.
4. Pluralize that name according to English pluralization rules.

Internal uppercase letters in camel-case names are typically preserved. Therefore, `PurchaseOrder` becomes `purchaseOrders`.

## Examples of Default Collection Names

| Domain Type | Default Collection Path |
| --- | --- |
| `Order` | `/orders` |
| `Person` | `/people` |
| `Category` | `/categories` |
| `Address` | `/addresses` |
| `PurchaseOrder` | `/purchaseOrders` |

Do not assume an `s` is simply appended to every class name. English nouns with irregular plural forms, such as `Person` becoming `people`, are handled by pluralization rules. For complex domain names or abbreviations, verify the actual path published by the application.

## Collection and Item Paths

The path derived above is the collection path. Spring Data REST uses this path as the prefix for the repository's resources:

    GET /orders
    GET /orders/42

`GET /orders` accesses the collection; `GET /orders/42` accesses the item with ID `42` if the repository supports item resources and the record exists. Exposed query methods are typically located under the `/search` branch of the collection, such as `/orders/search`.

The paths in the example do not include a custom base path. If the application configures `spring.data.rest.base-path=/api`, the corresponding URLs will be `/api/orders` and `/api/orders/42`.

## Overriding the Default Path

If you want URLs to be stable, readable, or aligned with custom API conventions, set the `path` attribute on `@RepositoryRestResource` at the repository level:

    import org.springframework.data.jpa.repository.JpaRepository;
    import org.springframework.data.rest.core.annotation.RepositoryRestResource;

    @RepositoryRestResource(path = "sales-orders")
    public interface PurchaseOrderRepository
            extends JpaRepository<PurchaseOrder, Long> {
    }

The repository above is exposed at `/sales-orders` instead of `/purchaseOrders` (or `/api/sales-orders` if the base path is `/api`). `path` is the URL path segment of the collection resource; use a clear, unique value without needing a leading `/`.

The `collectionResourceRel` attribute controls the relation name (`rel`) in HAL links at the API root. It serves a different purpose from `path`: `path` determines the URL, whereas `collectionResourceRel` determines the link relation name. Both can be configured together:

    @RepositoryRestResource(
        path = "sales-orders",
        collectionResourceRel = "salesOrders"
    )
    public interface PurchaseOrderRepository
            extends JpaRepository<PurchaseOrder, Long> {
    }

In this example, the collection is accessed via `/sales-orders`; the link relation at the API root is named `salesOrders`.

For a specific query method, `@RestResource(path = "...")` can change the path segment of that search resource. A method-level annotation does not replace the collection path configured at the repository level.

## Factors That Do Not Determine the Default Path

- Repository interface name: `PurchaseOrderRepository` is not the source for generating the collection name.
- JPA table name in `@Table(name = "...")`: changing the table name does not automatically change the REST URL.
- Package name of the domain class: the package is not appended to the default path.
- JSON property names or database column names: these names do not determine the collection path.

If two domain types in different packages share the same simple class name, their default collection names may collide. Explicitly set `@RepositoryRestResource(path = "...")` for repositories that need to be distinguished.

## Verifying Paths in the Application

Do not rely solely on class names to guess URLs when the application has custom configurations. After starting the application:

1. Call the API root, usually `GET /` or `GET /api/` if a base path is configured.
2. Inspect the collection links returned by Spring Data REST. The link relation indicates the relation name; `href` shows the actual URL.
3. Call the collection URL from `href`, then test an item URL with a valid ID.
4. If the URL differs from the default name, check `@RepositoryRestResource(path = "...")` and the `spring.data.rest.base-path` configuration.

For example, with a base path of `/api` and a `PurchaseOrderRepository` that does not override `path`, the default collection URL is `/api/purchaseOrders`. If the repository declares `path = "sales-orders"`, the URL becomes `/api/sales-orders`.

## Notes

A path is only published when the repository is exported by Spring Data REST. If a repository is marked with `@RepositoryRestResource(exported = false)`, Spring Data REST does not create the corresponding collection endpoint, even though a default name could still be derived from the domain type.

Default paths are a convention-based convenience, not a mandatory URL contract for every application. For public APIs or clients that depend long-term on URLs, consider declaring `path` explicitly and verifying the returned links after every configuration change.

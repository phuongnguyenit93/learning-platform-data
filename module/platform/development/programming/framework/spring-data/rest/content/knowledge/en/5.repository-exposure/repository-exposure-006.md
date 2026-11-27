# Choosing Exposed Methods with Repository, CrudRepository, and JpaRepository

Spring Data REST builds a REST API from Spring Data repositories. The interface a repository extends determines which data operations are available in the repository layer; Spring Data REST uses those operations to serve collection, item, and search resources. Choosing the right interface therefore helps control the API surface right from the start.

## 1. How Do the Three Interfaces Differ?

| Interface | Provided Methods | When to Choose |
|---|---|---|
| Repository<T, ID> | Minimal marker interface. Does not provide a built-in CRUD suite; you declare the methods your application needs. | When you want to restrict the API, such as read-only access or exposing only a few queries. |
| CrudRepository<T, ID> | General CRUD operations such as save, saveAll, findById, findAll, existsById, count, deleteById, delete, and deleteAll. | When the resource needs standard create, read, update, and delete operations. |
| JpaRepository<T, ID> | CRUD operations plus paging/sorting capabilities and JPA-specific utilities, such as flush, saveAndFlush, getReferenceById, or batch deletes. Exact method lists and return types depend on the Spring Data version. | When using JPA and the business layer needs additional JPA utilities. |

Repository<T, ID> is the minimalist choice. It lets you declare the exact method signatures the repository requires. For example, a repository declaring only findById and findAll can serve reads without bringing save or delete into the repository contract.

CrudRepository adds the standard CRUD contract. When a repository extends this interface, Spring Data REST has the common operations needed to serve read and write resources.

JpaRepository typically fits applications using Spring Data JPA. It inherits CRUD and paging/sorting capabilities while adding operations aimed at EntityManager and JPA persistence mechanics. Choose JpaRepository because the business layer needs those utilities; using this interface does not mean every JPA method becomes a separate REST URL.

## 2. How Does Spring Data REST Expose Resources?

Spring Data REST organizes the API around resources:

- **Collection resource** represents a set of entities, e.g., /api/products.
- **Item resource** represents a single entity, e.g., /api/products/42.
- **Search resource** represents an exposed query method, e.g., /api/products/search/by-category.

For a CRUD-capable repository, HTTP operations typically look like:

| HTTP | Resource | Meaning |
|---|---|---|
| GET | /api/products | Retrieve the product list; the response may include paging info and navigation links. |
| GET | /api/products/42 | Retrieve the product with ID 42. |
| POST | /api/products | Create a new product in the collection. |
| PUT | /api/products/42 | Replace the product's data at the item resource. |
| PATCH | /api/products/42 | Partially update the product's data. |
| DELETE | /api/products/42 | Delete the product at the item resource. |

This is the resource-and-HTTP perspective. Do not assume each Java method such as save, findAll, or deleteById generates an endpoint carrying that exact method name. Spring Data REST maps repository operations onto collection and item resources according to REST conventions.

Custom query methods are exposed under the search resource. For example, findByCategory can be called via a URL like /api/products/search/by-category?category=books. Path names and parameter names can be customized with annotations.

## 3. Declaring Only Needed Methods with Repository

Use Repository<T, ID> when you want to define the repository contract yourself rather than inheriting full CRUD:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.Repository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.repository.query.Param;

@RepositoryRestResource(path = "products", collectionResourceRel = "products")
public interface ProductRepository extends Repository<Product, Long> {

    Optional<Product> findById(Long id);

    List<Product> findAll();

    @RestResource(path = "by-category", rel = "by-category")
    List<Product> findByCategoryIgnoreCase(@Param("category") String category);
}
~~~

In this example, the repository declares two basic read methods and one query by category. It does not inherit save or delete from CrudRepository, so the repository contract does not provide those write operations.

The custom query is exposed at the search resource under path by-category. The category parameter appears in the query string. Using explicit @Param keeps API parameter names stable and readable.

If you create a generic parent interface for multiple repositories to extend, mark the parent interface with @NoRepositoryBean so Spring Data does not try to create a standalone repository for that generic type:

~~~java
@NoRepositoryBean
public interface ReadOnlyRepository<T, ID> extends Repository<T, ID> {
    Optional<T> findById(ID id);
    List<T> findAll();
}
~~~

A concrete repository can then extend ReadOnlyRepository<Product, Long> and declare additional custom queries.

## 4. Using CrudRepository for Standard CRUD

When a resource needs normal create, read, update, and delete operations, CrudRepository is a clear choice:

~~~java
import java.util.List;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.repository.query.Param;

@RepositoryRestResource(path = "products", collectionResourceRel = "products")
public interface ProductRepository extends CrudRepository<Product, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    List<Product> findByNameContainingIgnoreCase(@Param("name") String name);

    @Override
    @RestResource(exported = false)
    void deleteById(Long id);
}
~~~

The repository inherits the standard CRUD suite. The name query is exposed under the search resource; deleteById is hidden from the REST API using exported = false. The Java method remains part of the repository contract and can still be used by the application layer.

For example, the search resource can be invoked as:

~~~http
GET /api/products/search/by-name?name=keyboard
~~~

If you want to hide the entire repository from Spring Data REST, set exported = false at the repository level:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalProductRepository extends CrudRepository<Product, Long> {
}
~~~

The repository can then still be injected and used in the application, while Spring Data REST does not expose its resources.

## 5. Using JpaRepository in JPA Applications

For JPA-based applications, JpaRepository provides a richer set of repository operations:

~~~java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.repository.query.Param;

@RepositoryRestResource(path = "products", collectionResourceRel = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {

    @RestResource(path = "active", rel = "active")
    List<Product> findByActiveTrue();

    @RestResource(path = "by-category", rel = "by-category")
    List<Product> findByCategoryIgnoreCase(@Param("category") String category);
}
~~~

Spring Data REST can expose custom queries such as active and by-category under the search resource. JPA operations such as flush, saveAndFlush, or deleteAllInBatch serve the persistence layer; do not assume they create separate REST endpoints. The REST API remains organized around resources and HTTP conventions.

If the application only needs basic CRUD, CrudRepository often expresses the requirement more accurately. If the application genuinely uses JPA utilities, JpaRepository is an appropriate choice. In newer Spring Data versions, some paging and CRUD interfaces have been split or supplemented with List return types; check the API matching your dependency version when declaring repository types.

## 6. Controlling Naming and Exposure Scope

There are two primary levels of control:

**Repository level — @RepositoryRestResource**

- path sets the collection resource path.
- collectionResourceRel sets the relation name in the HAL response.
- exported = false hides the entire repository from Spring Data REST.

**Method level — @RestResource**

- path sets the path for the search resource.
- rel sets the relation name in the response.
- exported = false hides the method from the REST API.

Example renaming a query path:

~~~java
@RestResource(path = "recent", rel = "recent")
List<Product> findTop10ByOrderByCreatedAtDesc();
~~~

The corresponding search resource has a path like /api/products/search/recent.

To hide an inherited method, you can override that method in the concrete repository and attach @RestResource(exported = false), as in the deleteById example above. This controls exposure through Spring Data REST; it does not replace application access control.

## 7. Choosing an Interface Based on Requirements

- **Expose only a small set of methods:** extend Repository<T, ID>, then explicitly declare the needed read or query methods.
- **Standard CRUD API:** extend CrudRepository<T, ID>.
- **Using JPA and needing extra persistence utilities:** extend JpaRepository<T, ID>.
- **Keep a repository internal:** use @RepositoryRestResource(exported = false).
- **Hide a specific operation:** use @RestResource(exported = false) on the method.

Do not pick JpaRepository just because it has more methods. Every exposed repository is part of an API contract that clients can discover and invoke. Start from the business operations clients actually need, then choose the appropriate interface and annotations.

## 8. Common Pitfalls

1. **Assuming CRUD method names are URLs.** Spring Data REST exposes collection/item resources by convention; only eligible queries appear under the search resource.
2. **Extending an overly broad interface.** A repository extending CrudRepository or JpaRepository has a broader operation contract than one extending only Repository.
3. **Forgetting to hide sensitive methods.** Use exported = false at the repository or method level if an operation should not be exposed.
4. **Not naming query paths clearly.** Use path, rel, and @Param to keep the API readable and stable.
5. **Treating endpoint hiding as authorization.** exported = false controls resource publication in Spring Data REST; access permissions still need to be configured via application security mechanisms.
6. **Confusing JPA utilities with REST endpoints.** Methods such as flush or batch deletes serve the persistence layer and do not implicitly create separate URLs.

## 9. How to Verify the API After Configuration

1. Start the application with Spring Data REST and the configured repositories.
2. Open the root endpoint, e.g., /api, to inspect the resource links exposed by Spring Data REST.
3. Open a collection resource, e.g., /api/products, then test GET and the write operations the repository is permitted to support.
4. Open /api/products/search to view exposed queries.
5. Call a custom query, e.g., /api/products/search/by-category?category=books.
6. Verify that repositories or methods with exported = false do not appear in the API.

When an API serves multiple clients, document clearly which repositories are exposed, which HTTP operations are supported, and which search queries are provided. This helps keep repository interface changes intentional, since changing an interface can change the REST contract clients rely on.

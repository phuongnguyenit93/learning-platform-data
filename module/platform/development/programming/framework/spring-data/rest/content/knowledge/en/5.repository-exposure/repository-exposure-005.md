# Hiding CRUD or Query Methods with @RestResource(exported = false)

Spring Data REST can automatically export repository methods as REST resources. In practice, repositories often contain methods meant only for internal processing or that should not become part of the public API. You can use **@RestResource(exported = false)** on individual methods to instruct Spring Data REST not to export those methods.

This keeps the repository intact for the service layer and other Java components, while restricting the operations clients can invoke through Spring Data REST.

## 1. How It Works

**@RestResource** belongs to the **org.springframework.data.rest.core.annotation** package. The **exported** attribute determines whether a method or resource is exported over HTTP by Spring Data REST:

- Default value is **true**: eligible methods are exported according to Spring Data REST rules.
- Set **exported = false**: the method is not exported as a REST endpoint.
- The method still exists on the repository interface and can still be called from services or other Java code.

Import example:

~~~java
import org.springframework.data.rest.core.annotation.RestResource;
~~~

Place the annotation directly on the method declaration inside a repository interface managed by Spring Data REST.

## 2. Hiding a Query Method

Query methods declared following Spring Data naming conventions, such as **findByEmail** or **findByStatus**, can be exported under the repository's **search** resource.

If a query serves only internal business logic, annotate that method:

~~~java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "customers")
public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @RestResource(exported = false)
    Optional<Customer> findByEmail(String email);
}
~~~

Without the hiding annotation, the query method can typically be called via a path like:

~~~http
GET /customers/search/findByEmail?email=alice@example.com
~~~

After setting **@RestResource(exported = false)**, Spring Data REST does not export this query endpoint and does not include the method in the published search links. The **findByEmail** method can still be called in Java:

~~~java
Optional<Customer> customer = customerRepository.findByEmail(email);
~~~

Thus, the service layer can continue using the query while REST clients cannot directly call the Spring Data REST-generated endpoint.

## 3. Hiding Inherited CRUD Methods

Repositories commonly inherit CRUD methods from **CrudRepository**, **ListCrudRepository**, or **JpaRepository**. When you want to hide an inherited method, redeclare that method in the concrete repository and attach **@RestResource(exported = false)**.

For example, hiding delete-by-ID and find-one-by-ID operations:

~~~java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "customers")
public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @Override
    @RestResource(exported = false)
    void deleteById(Long id);

    @Override
    @RestResource(exported = false)
    Optional<Customer> findById(Long id);
}
~~~

Key points to remember:

1. You must redeclare the method in the repository interface scanned by Spring Data REST.
2. The redeclared signature must be compatible with the inherited method: name, parameters, and return type must match the parent interface contract.
3. The annotation applies only to the annotated method. Other CRUD methods may still be exported.
4. If you want to hide multiple operations, annotate each corresponding method. For example, hiding **deleteById** does not automatically hide other delete methods such as **delete**, **deleteAll**, or custom delete methods.

Available methods can differ across repository interfaces and Spring Data versions. Pick the exact methods your repository inherits and needs to hide.

## 4. Distinguishing Hiding One Method vs. Hiding the Entire Repository

There are two different configuration scopes:

| Annotation | Scope | Purpose |
|---|---|---|
| **@RestResource(exported = false)** | A single repository method | Hides only the endpoint corresponding to that method |
| **@RepositoryRestResource(exported = false)** | The entire repository | Prevents exporting that repository as a REST resource |

Example hiding the entire repository:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalCustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Only use the repository-level configuration when you do not want Spring Data REST to expose any resource from that repository. If you still need to expose other operations, use method-level configuration.

## 5. Verifying Results

After starting the application, inspect the resources exposed by Spring Data REST. If the application configures a base path, prepend that base path to the URLs below.

**For query methods:**

1. Call the collection resource, for example **GET /customers**.
2. Inspect the **GET /customers/search** resource.
3. Confirm that **findByEmail** no longer appears in the search links.
4. Try calling **GET /customers/search/findByEmail?email=alice@example.com**. The endpoint managed by Spring Data REST must no longer be served; typically the request receives a 404 response.

**For CRUD methods:**

1. Inspect the item resource and the CRUD operations currently exposed.
2. Try calling the endpoint corresponding to the hidden method, such as deleting by ID.
3. Confirm that the annotated method is no longer provided by Spring Data REST.
4. If needed, verify separately in a service or Java test that the repository method still works when called internally.

Exact HTTP outcomes can be affected by application configuration and other controllers. The goal of verification is to confirm that Spring Data REST no longer exports the endpoint for the annotated method.

## 6. Common Issues and How to Fix Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Query endpoint still appears | Annotation is not placed on the right method in a managed repository | Check package import and annotation placement |
| Inherited CRUD method is still exported | Method was not redeclared in the child repository or signature does not match | Override the exact method and place the annotation on that declaration |
| Some operations can still be called | Only one method was hidden while other CRUD methods remain exported | Identify and individually hide each method to exclude from the API |
| URL still works even though repository method is hidden | A custom controller or endpoint provides the same functionality | Check controller configuration and custom REST routes |

Be sure to use **org.springframework.data.rest.core.annotation.RestResource**. An annotation with the same name or from another package does not replace Spring Data REST configuration.

## 7. Limitations and Security Notes

**exported = false** controls whether Spring Data REST exports a method as an endpoint. It does not remove the method from the repository, does not prevent Java code from calling it, and does not automatically create authorization rules for the application.

If the functionality is still provided through a custom controller or another API, you must configure security on that path. For sensitive operations, use Spring Security and enforce permission checks at the appropriate layer; do not treat endpoint hiding as the sole authorization mechanism.

When designing an API, export only the operations clients genuinely need. Using **@RestResource(exported = false)** on internal methods keeps the repository useful for business logic without exposing unnecessary endpoints.

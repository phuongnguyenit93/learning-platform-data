# Customizing Resource Identifier URIs with EntityLookup and withEntityLookup in Spring Data REST

## Objectives

By default, Spring Data REST builds single-resource URIs from the collection path plus the entity's identifier key in the datastore. For example, a `User` with primary key `id = 42` is typically accessed at:

~~~text
GET /api/users/42
~~~

In many systems, the primary key is only meaningful internally. An API may want to identify resources using a stable and unique business value such as `username`, `slug`, employee code, or customer code. Spring Data REST supports this via `EntityLookup`.

`EntityLookup` tells Spring Data REST a two-way mapping:

1. Extract the public identifier from an entity to build URIs and self links.
2. Look up the entity again when a client sends a request to a URI containing that public identifier.

You can register the mapping using the `RepositoryRestConfiguration.withEntityLookup()` configuration API, or provide your own bean implementing `EntityLookup` (typically extending `EntityLookupSupport`).

## 1. Understanding URI Identifiers and Primary Keys

Suppose the User table has the following data:

| id (primary key) | username | fullName |
| ---: | --- | --- |
| 42 | an.nguyen | An Nguyen |
| 57 | binh.tran | Binh Tran |

Without customization, Spring Data REST generates item URIs based on the primary key:

- `/api/users/42`
- `/api/users/57`

After mapping by username, the URIs can become:

- `/api/users/an.nguyen`
- `/api/users/binh.tran`

This changes how resources are identified in the REST API. It **does not change the database primary key**, does not alter JPA relationships, and does not replace `@Id`. The repository can still use `Long` as its primary key type for internal operations.

The value used as a URI must uniquely identify a single entity within the repository scope, remain stable for as long as clients may store or share the URI, and be suitable for placement in a single path segment.

## 2. Preparing the Entity and Repository

Example using `username` as the public identifier:

~~~java
@Entity
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, updatable = false)
    private String username;

    private String fullName;

    protected User() {
    }

    public String getUsername() {
        return username;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

`unique = true` ensures the database does not allow two records to share the same username. `updatable = false` is an option to keep the URI stable after creation; if business requirements allow changing username, you must explicitly design URI migration and handle clients holding old links.

The repository needs a method to find an entity by the exact value that will appear in the URI:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByUsername(String username);
}
~~~

The `findByUsername` method can be used strictly internally by the lookup mechanism. You are not required to expose it as a separate search endpoint.

## 3. Recommended Approach: Registering with withEntityLookup()

With modern Java, the most concise approach is using method references. Register a `RepositoryRestConfigurer` bean:

~~~java
@Configuration
public class UserRestConfiguration {

    @Bean
    RepositoryRestConfigurer userEntityLookup() {
        return RepositoryRestConfigurer.withConfig(config -> {
            config.withEntityLookup()
                    .forRepository(UserRepository.class)
                    .withIdMapping(User::getUsername)
                    .withLookup(UserRepository::findByUsername);
        });
    }
}
~~~

Main imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
~~~

The configuration chain has three parts:

- `withEntityLookup()`: retrieves the registrar to declare how entities are identified and looked up.
- `forRepository(UserRepository.class)`: scopes the mapping to the User repository.
- `withIdMapping(User::getUsername)`: maps from the entity to the public identifier value.
- `withLookup(UserRepository::findByUsername)`: maps back from the value in the URI to the entity.

In the example, `User::getUsername` returns `String`; `UserRepository::findByUsername` accepts `String` and returns `Optional<User>`. The mapping output type and lookup parameter type must be compatible.

If the project uses a Spring Data REST version with a single-parameter configuration method, you can write a class implementing `RepositoryRestConfigurer` and override the corresponding method. With API 5.1.x, you can use `RepositoryRestConfigurer.withConfig(Consumer<RepositoryRestConfiguration>)` as in the example above to avoid depending on the callback signature that includes `CorsRegistry`.

## 4. Role of EntityLookup

`org.springframework.data.rest.core.support.EntityLookup<T>` is an SPI (Service Provider Interface) describing how Spring Data REST recognizes a domain type and looks up an entity by the requested identifier.

Two core operations:

| Method | Mapping Direction | Responsibility |
| --- | --- | --- |
| `getResourceIdentifier(T entity)` | Entity → URI identifier | Returns the value used in the item URI and self link. |
| `lookupEntity(Object id)` | URI identifier → Entity | Finds the entity matching the value sent by the client in the URL. |

Modern APIs also provide `getLookupProperty()` to supply the property name used for lookup when determinable. If it returns `Optional.empty()`, Spring Data REST assumes the identifier property is also the property used for lookup.

You can extend `EntityLookupSupport<T>` instead of implementing the entire plugin contract manually. The base class infers the supported domain type from the generic parameter `T`, so you do not have to write `supports(Class<?>)` logic yourself.

## 5. Registering EntityLookup as a Spring Bean

If you need mapping logic more complex than method references, you can create a dedicated bean:

~~~java
@Component
public class UserEntityLookup extends EntityLookupSupport<User> {

    private final UserRepository repository;

    public UserEntityLookup(UserRepository repository) {
        this.repository = repository;
    }

    @Override
    public Object getResourceIdentifier(User entity) {
        return entity.getUsername();
    }

    @Override
    public Optional<User> lookupEntity(Object id) {
        return repository.findByUsername(String.valueOf(id));
    }

    @Override
    public Optional<String> getLookupProperty() {
        return Optional.of("username");
    }
}
~~~

Main imports:

~~~java
import java.util.Optional;

import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.support.EntityLookupSupport;
~~~

When component scan detects this bean, Spring Data REST can use it for the `User` domain type. `EntityLookupSupport<User>` indicates the bean applies to User.

In the example:

- `getResourceIdentifier` returns the username to construct the URI.
- `lookupEntity` calls the repository to find the User by username.
- `getLookupProperty` declares the lookup property as `username`.

Method signatures may differ in older Spring Data REST versions. In API 5.1.x, Javadoc declares `getResourceIdentifier(T)` returning `Object` and `lookupEntity(Object)` returning `Optional<T>`. When working on a specific project, always check the Javadoc for the dependency version in use.

Choose one configuration approach per domain type: the registrar via `withEntityLookup()` or an `EntityLookup` bean. Avoid declaring multiple competing lookups for the same entity type, as this makes determining the active mapping confusing.

## 6. Processing Flow for Creating and Reading URIs

Suppose User has `id = 42`, `username = "an.nguyen"`.

<escape>
Entity in repository
        |
        | getResourceIdentifier(user)
        v
"an.nguyen"
        |
        v
/api/users/an.nguyen
</escape>

When a client calls `GET /api/users/an.nguyen`, Spring Data REST extracts the identifier `an.nguyen`, invokes the corresponding lookup, and receives the User entity. Both directions must follow the same rule:

~~~text
User -> username -> URI path
URI path -> username -> UserRepository.findByUsername(...)
~~~

If the two directions are inconsistent, the API can generate a self link that it cannot read back itself. For example, if `getResourceIdentifier` returns a lowercase username while lookup performs a case-sensitive comparison against a differently normalized value, the request may fail to find the entity.

## 7. Impact on the REST API

Assume the base path is `/api` and the repository is exported at `/users`.

Reading the collection:

~~~http
GET /api/users
Accept: application/hal+json
~~~

The HAL response may contain item self links using usernames:

~~~json
{
  "_embedded": {
    "users": [
      {
        "username": "an.nguyen",
        "fullName": "An Nguyen",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/users/an.nguyen"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/users"
    }
  }
}
~~~

Reading an item using the new identifier:

~~~http
GET /api/users/an.nguyen
Accept: application/hal+json
~~~

Spring Data REST uses `findByUsername("an.nguyen")` to retrieve the entity. If no matching username exists, the item request will fail to find the resource and return the corresponding error response (typically HTTP 404).

Links to User generated by Spring Data REST from that entity may also use the new identifier. Therefore, clients should follow `_links.self` and returned hypermedia links rather than keeping rules that construct URIs from numeric primary keys.

## 8. Scope of Impact and What Does Not Change

`EntityLookup` focuses on the identifier of the **item resource** for the configured repository.

| Component | Does It Change? | Explanation |
| --- | --- | --- |
| Item URI, e.g. `/users/{id}` | Yes | The identifier segment is replaced with the value from `getResourceIdentifier` or `withIdMapping`. |
| Self link in HAL | Yes | Item links are built using the custom identifier. |
| How items are looked up by URL | Yes | Lookup uses the URI identifier to find the entity. |
| Database primary key (`@Id`) | No | The entity keeps its primary key and the repository keeps its original ID type. |
| Collection path (`/users`) | No | Use `@RepositoryRestResource(path = ...)` to change the collection path. |
| Relation names in HAL | No | Use resource mapping configuration or `@RestResource` for relations. |
| Exposing ID field in JSON | Not directly | `exposeIdsFor(...)` is a separate configuration to show the ID as a property. |

Do not confuse `EntityLookup` with `BackendIdConverter`. `EntityLookup` changes the resource identifier value via the repository and a business property. `BackendIdConverter` serves cases where you need to customize how a backend ID is converted to a URI representation and back, typically tied to specific ID/datastore types.

## 9. Choosing a Public Identifier

A property suitable as a URI identifier should meet the following criteria:

1. **Unique:** the database should have a unique constraint or equivalent mechanism to prevent two entities from sharing the same identifier.
2. **Stable:** if a username or slug changes, old URIs may become inaccessible. Consider an immutable public code if clients need to store URIs long-term.
3. **Non-sensitive:** do not use personal emails, phone numbers, confidential internal codes, or data that could leak user information.
4. **URL-safe:** avoid slashes `/` and characters requiring special handling in path segments. If free-form values are needed, encode properly or use a URL-safe public identifier format.
5. **Normalized consistently:** clearly define casing, whitespace, Unicode handling, and comparison rules at both creation and lookup time.

Do not use display names (`fullName`) as identifiers if names can duplicate or change. A unique `slug`, immutable username, or public UUID is usually more suitable.

## 10. Testing the Mapping

Test both URI generation and lookup directions. Example with Spring MVC Test:

~~~java
mockMvc.perform(get("/api/users/an.nguyen")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.username").value("an.nguyen"))
    .andExpect(jsonPath("$._links.self.href")
            .value(containsString("/api/users/an.nguyen")));
~~~

Also check the collection to confirm each item's self link uses the new identifier:

~~~java
mockMvc.perform(get("/api/users")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.users[0]._links.self.href")
            .value(containsString("/api/users/")));
~~~

For a non-existent identifier:

~~~java
mockMvc.perform(get("/api/users/unknown-user")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isNotFound());
~~~

Cases to verify in the application:

- GET item by username returns the right entity.
- Collection HAL generates self links using username.
- Non-existent identifier returns 404.
- Two entities cannot have the same identifier.
- Association links to User still point to valid URIs.
- PUT/PATCH/DELETE operations on items still work with the new URI.
- Base path and reverse proxy do not corrupt generated links.
- If identifiers can change, behavior for old URIs is defined and tested.

## 11. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| GET by username returns 404 | `findByUsername` finds nothing, data is not normalized, or bidirectional mapping mismatches | Check values in the database and lookup logic. |
| Self link still contains numeric ID | Bean/configurer not scanned or mapping registered for wrong repository | Check component scan, configurer bean, and `forRepository`. |
| Two entities generate the same URI | Identifier value is not unique | Add a unique constraint and choose a unique business key. |
| URI breaks with special characters | Identifier is not path-segment safe or client does not encode properly | Use a URL-safe identifier and verify URL encoding. |
| Some endpoints work while others do not | Mapping applies only to the registered repository/domain type | Identify which repositories need custom lookup and register accordingly. |
| Older clients cannot find items | Clients still use URIs based on old primary keys | Plan API migration, update clients, or provide a compatibility mechanism. |

## 12. References

- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): section “Customizing Item Resource URIs”, examples of `withEntityLookup()`, `withIdMapping`, and `withLookup`.
- [Spring Data REST 5.1.2 API — EntityLookup](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/support/EntityLookup.html): SPI contract for mapping entities to identifiers and reverse lookup.
- [Spring Data REST 5.1.x API — EntityLookupSupport](https://docs.spring.io/spring-data/rest/docs/5.1.x/api/org/springframework/data/rest/core/support/EntityLookupSupport.html): base class that infers domain type from generics.
- [Spring Data REST 5.1.2 API — EntityLookupRegistrar](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/EntityLookupRegistrar.html): API for registering lookup per repository.
- [Spring Data REST 5.1.2 API — RepositoryRestConfigurer](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html): configuration extension point for Spring Data REST.

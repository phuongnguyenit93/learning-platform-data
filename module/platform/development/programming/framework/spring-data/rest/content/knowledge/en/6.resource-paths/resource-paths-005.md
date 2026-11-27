# Customizing the Path and Rel of Search Methods in Spring Data REST

Spring Data REST can automatically expose repository query methods under the \`/search\` resource. Each exported method appears as a link for clients to discover and invoke the API. When the default URL name or link relation name does not fit the API design, you can use the **\`@RestResource\`** annotation to customize each query method individually.

Two attributes must be distinguished:

- **\`path\`** determines the URL path segment that clients call.
- **\`rel\`** determines the link relation name published in the HAL document so clients can identify that link.

Changing \`path\` and \`rel\` does not alter the query conditions defined by the method name or \`@Query\`. They control how Spring Data REST exposes and identifies the endpoint.

## 1. Location of Query Methods in Spring Data REST

Suppose the application has a repository:

~~~java
public interface PersonRepository extends CrudRepository<Person, Long> {

    List<Person> findByLastName(String lastName);
}
~~~

When query methods are exported, Spring Data REST places the search methods under the collection resource's \`search\` resource. If the collection resource has the path \`/people\`, clients discover search methods at:

~~~http
GET /people/search
~~~

This resource returns links to the exported query methods. Clients follow the corresponding link to invoke a search method. For example, the \`findByLastName\` method taking one parameter can be called using a query parameter:

~~~http
GET /people/search/findByLastName?lastName=Nguyen
~~~

The default path name is generated from the query method metadata. If you want URLs that are stable, concise, and clearly meaningful to clients, declare \`path\` explicitly with \`@RestResource\`.

## 2. Customizing path and rel with @RestResource

Place \`@RestResource\` directly on the query method:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RestResource;

import java.util.List;

public interface PersonRepository extends CrudRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findByLastName(@Param("lastName") String lastName);
}
~~~

With the repository exposed at \`/people\`, the search endpoint has the path:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
~~~

In the example:

- \`path = "by-last-name"\` creates the URL segment \`by-last-name\` after \`/people/search\`.
- \`rel = "byLastName"\` sets the link relation name that clients see in HAL.
- \`@Param("lastName")\` specifies the query parameter name in the URL. This name must match the parameter accepted by the query method.
- \`findByLastName\` remains a Spring Data derived query. The annotation only changes REST exposure metadata, not the query semantics.

### path and rel Have Different Responsibilities

| Attribute | Effect | Example |
|---|---|---|
| \`path\` | URL segment of the endpoint | \`by-last-name\` |
| \`rel\` | Link name in HAL | \`byLastName\` |
| \`@Param\` | Query parameter name | \`lastName\` |

Thus, clients call the URL using \`path\`, while clients read the HAL document using \`rel\`. The two values can be identical, but they are not required to match.

## 3. Clients Discovering Search Links

When a client requests:

~~~http
GET /people/search
Accept: application/hal+json
~~~

Spring Data REST returns the search resource with links to the exported query methods. After configuring the annotation in the example above, an illustrative HAL excerpt might look like:

~~~json
{
  "_links": {
    "byLastName": {
      "href": "http://localhost:8080/people/search/by-last-name{?lastName}",
      "templated": true
    }
  }
}
~~~

This is a simplified example to illustrate how \`rel\` and \`path\` work; actual responses may contain additional links and metadata.

Clients proceed in two steps:

1. Read the link with the relation \`byLastName\` from the \`/people/search\` resource.
2. Fill in the value for the URI template variable \`lastName\`, then call the search endpoint.

Example request after filling in the parameter:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
Accept: application/hal+json
~~~

Discovering via links keeps clients from having to construct URLs from repository names or Java method names. If the path changes later while the relation remains stable, clients can continue locating the link through the same relation.

## 4. Customizing Only One of the Two Attributes

You can use \`path\` and \`rel\` independently as needed. For example:

~~~java
@RestResource(path = "by-city")
List<Person> findByCity(@Param("city") String city);
~~~

This example sets only an explicit path; the relation is determined by the framework using the query method's default metadata.

Or:

~~~java
@RestResource(rel = "peopleInCity")
List<Person> findByCity(@Param("city") String city);
~~~

This example customizes the relation name in HAL; the path still follows the query method's default mapping.

In APIs consumed by multiple clients, consider setting both values explicitly to control both the URL and the link contract. Using lowercase and hyphens for paths generally makes URLs easier to read; using short, meaningful, and stable relations makes discovery easier for clients.

## 5. Combining with @RepositoryRestResource

\`@RestResource\` customizes a single repository method. At the repository level, \`@RepositoryRestResource\` lets you customize the path and relations of the collection resource and item resource.

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

import java.util.List;

@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people",
    itemResourceRel = "person"
)
public interface PersonRepository extends CrudRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findByLastName(@Param("lastName") String lastName);
}
~~~

In this example:

- \`path = "people"\` customizes the collection resource path.
- \`collectionResourceRel = "people"\` sets the relation for the collection.
- \`itemResourceRel = "person"\` sets the relation for the item resource.
- \`@RestResource\` on \`findByLastName\` customizes that specific search endpoint.

The search endpoint still lives under the repository's search resource:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
~~~

Do not confuse \`collectionResourceRel\` with a query method's \`rel\`: the first sets the relation for the collection resource, while the second sets the relation for the search link.

## 6. Hiding a Query Method from the REST API

If a query method is for internal use only and should not be callable by clients via Spring Data REST, you can disable exporting directly on the method:

~~~java
@RestResource(exported = false)
List<Person> findByInternalCode(String code);
~~~

In this case, the method is not exposed as a search endpoint. The application can still use the method through the repository in Java code if it is implemented and invoked appropriately.

At the repository level, \`@RepositoryRestResource(exported = false)\` can be used to prevent that repository from being exposed via Spring Data REST. Choose the right scope: hiding a single query method or hiding the entire repository.

## 7. Search Parameters and Result Types

\`@RestResource\` does not replace parameter declarations or the return type of a query method.

Example with multiple parameters:

~~~java
@RestResource(path = "by-name-and-city", rel = "byNameAndCity")
List<Person> findByFirstNameAndCity(
    @Param("firstName") String firstName,
    @Param("city") String city
);
~~~

The client calls:

~~~http
GET /people/search/by-name-and-city?firstName=An&city=Hanoi
~~~

For each parameter, use \`@Param\` to give a clear name in the URL template. This is especially useful when Java parameter names are refactored or when you want to maintain a consistent API contract.

Query methods can also use a return type suited to your needs, such as \`List<Person>\`, \`Collection<Person>\`, or a pagination-supporting type like \`Page<Person>\` when supported by the corresponding module and configuration. If the method accepts \`Pageable\` or \`Sort\`, clients can pass pagination/sorting parameters following Spring Data REST conventions.

## 8. Considerations When Designing path and rel

- **Keep paths unique within the same search resource.** Two query methods should not expose the same path because clients will not be able to distinguish the endpoints clearly and mappings may conflict.
- **Keep rels meaningful and stable.** HAL clients typically rely on relations to find features, so avoid arbitrarily changing a rel just because a Java method name changed.
- **Do not mix parameter names with the path.** The path defines the endpoint; \`@Param\` defines the query parameter passed to the endpoint.
- **Verify both the search resource and the endpoint.** Open \`/people/search\` to confirm the relation is published, then call the endpoint URL with actual query parameters.
- **Check export status.** Both the query method must be exported and the repository must be exposed by Spring Data REST for clients to discover the link.
- **Watch for API contract changes.** Changing \`path\` can break clients calling the old URL; changing \`rel\` can break clients relying on the old relation so they can no longer find the link.

## 9. Verification Workflow After Customization

1. Start the application and confirm the repository is recognized by Spring Data REST.
2. Send a request to the collection resource, e.g., \`GET /people\`, to verify the base path.
3. Send \`GET /people/search\` and check for the link with the expected relation.
4. Expand the URI template in the link, pass all parameters declared with \`@Param\`, and call the endpoint.
5. Verify the query results, HTTP status code, and response body.
6. If the endpoint does not appear, check \`exported\`, repository REST configuration, path names, and whether the query method is recognized.

## 10. Key Takeaways

- Spring Data REST query methods are discovered via the repository's \`/search\` resource.
- Use \`@RestResource(path = "...", rel = "...")\` on the method to control the URL and relation of the search link.
- \`path\` is the endpoint path segment; \`rel\` is the link name in HAL; \`@Param\` is the query parameter name.
- Use \`@RepositoryRestResource\` to customize path and relations at the collection/item resource level.
- Use \`exported = false\` to hide a method or repository from the REST API depending on where the annotation is placed.
- After making changes, verify both the published link at \`/search\` and actual requests to the endpoint.

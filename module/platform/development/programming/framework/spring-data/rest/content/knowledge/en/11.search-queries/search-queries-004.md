# Customizing Query path and rel with @RestResource

## Objectives

After this lesson, you will be able to:

- Locate query methods within the Spring Data REST search resource.
- Use **@RestResource(path = ...)** to change the URL of a query method.
- Use **@RestResource(rel = ...)** to change the hypermedia relation name in HAL.
- Distinguish between path, rel, and query parameter names.
- Combine **@Param** to expose stable search parameters.
- Inspect search links in HAL and invoke endpoints with appropriate parameters.

## 1. Where are query methods exposed?

Spring Data REST can automatically expose valid query methods of a Spring Data repository as search resources. Given the repository:

~~~java
public interface MemberRepository extends JpaRepository<Member, Long> {

    List<Member> findByLastName(String lastName);
}
~~~

When the repository is exposed under the path **/api/members**, the query method can be accessed under the search resource:

~~~text
/api/members/search/findByLastName
~~~

The search resource provides an index endpoint for clients to discover the exposed query methods:

~~~http
GET /api/members/search
Accept: application/hal+json
~~~

The HAL response can contain links to each finder method. When a client calls a search link, the method is executed with the corresponding query parameters.

This is how Spring Data REST creates a search API from a repository without writing a controller for each query. The exact path depends on the repository path, base path configuration, and annotations on the method.

## 2. @RestResource controls method-level resources

The **@RestResource** annotation can be placed on a query method to customize how the method is exposed.

~~~java
import java.util.List;

import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RestResource;

public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-surname", rel = "surname")
    List<Member> findByLastName(@Param("lastName") String lastName);
}
~~~

In this example:

- **path = "by-surname"** sets the URL segment for the query method.
- **rel = "surname"** sets the relation name that clients see in HAL.
- **@Param("lastName")** sets the query parameter name that clients send.
- The Java method name remains **findByLastName**; the annotation does not rename the method in code.

If the base path is **/api** and the repository path is **members**, the search endpoint looks like:

~~~text
GET /api/members/search/by-surname?lastName=Nguyen
~~~

The three names **by-surname**, **surname**, and **lastName** have three distinct roles. Do not use them interchangeably when writing clients.

## 3. Distinguishing path, rel, and @Param

| Setting | Controls | Example |
|---|---|---|
| **path** | URL segment of the finder method | **by-surname** |
| **rel** | Relation name in HAL | **surname** |
| **@Param** | Query parameter name | **lastName** |

### path: which URL does the client call?

**path** changes the final URL segment of the query method under **/search**. With **path = "by-surname"**, the client calls:

~~~text
/api/members/search/by-surname
~~~

If the path is changed to **surname-search**, the method URL changes according to the new configuration. Clients that stored the old URL may no longer hit the right endpoint.

Paths should be short, understandable, stable, and not collide with the path of another finder method in the same search resource.

### rel: by which name does the client look up the link?

**rel** controls the relation name in HAL. For example, a response might contain:

~~~json
{
  "_links": {
    "surname": {
      "href": "http://localhost:8080/api/members/search/by-surname{?lastName}",
      "templated": true
    }
  }
}
~~~

The client looks up the **surname** relation in **_links**, retrieves **href**, and expands the template. If only rel is changed to **membersBySurname**, the relation key changes; the URL in href can remain the same if path did not change.

The relation name is part of the hypermedia contract. If a client discovers the API via HAL, use the rel returned by the server rather than guessing the relation from the Java method name.

### @Param: what is the query parameter named?

**@Param** sets the variable name the client sends in the query string. With:

~~~java
List<Member> findByLastName(@Param("lastName") String surname);
~~~

the client sends:

~~~text
?lastName=Nguyen
~~~

The Java variable name **surname** does not determine the HTTP parameter name in this example; the advertised name is **lastName**. Use **@Param** so the HTTP contract does not depend on whether the compiler preserves Java parameter names.

Changing **@Param("lastName")** to **@Param("familyName")** changes the query parameter name. That affects clients even if path and rel remain unchanged.

## 4. Example customizing path and rel independently

You can set path and rel to different values to separate the URL from the relation name:

~~~java
@RepositoryRestResource(path = "members")
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-surname", rel = "membersBySurname")
    List<Member> findByLastName(@Param("lastName") String lastName);
}
~~~

The search index may return:

~~~json
{
  "_links": {
    "membersBySurname": {
      "href": "http://localhost:8080/api/members/search/by-surname{?lastName}",
      "templated": true
    }
  }
}
~~~

The client follows three steps:

1. Look up the **membersBySurname** relation in **_links**.
2. Extract the URI template from **href**.
3. Fill in the **lastName** variable and send the request.

Example request after filling in the variable:

~~~http
GET /api/members/search/by-surname?lastName=Nguyen
Accept: application/hal+json
~~~

If the client only knows the relation name, it can still locate the endpoint even when the URL path differs from the relation name. That is why path and rel should be treated as two independent parts of the API contract.

## 5. URI templates of query methods

When a query method has parameters, the HAL link is typically represented as a URI template:

~~~json
{
  "href": "http://localhost:8080/api/members/search/by-surname{?lastName}",
  "templated": true
}
~~~

The expression **{?lastName}** indicates that the client can populate the **lastName** query parameter. When expanded with the value **Nguyen**, the URI becomes:

~~~text
http://localhost:8080/api/members/search/by-surname?lastName=Nguyen
~~~

For data containing diacritics or special characters, let a URI template processor or HTTP client encode the parameters properly. Do not concatenate strings manually and do not encode once and then encode again.

Example with curl:

~~~bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "lastName=Nguyễn" \
  "http://localhost:8080/api/members/search/by-surname"
~~~

The **--data-urlencode** flag encodes the query parameter value. In an application, the client should read the href and variable names from the HAL response and expand the template instead of building URLs from hardcoded strings.

## 6. Customizing multiple query methods

A repository can expose multiple finder methods with distinct paths and rels:

~~~java
@RepositoryRestResource(path = "members")
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-surname", rel = "membersBySurname")
    List<Member> findByLastName(@Param("lastName") String lastName);

    @RestResource(path = "by-status", rel = "membersByStatus")
    List<Member> findByStatus(@Param("status") MemberStatus status);

    @RestResource(path = "recent", rel = "recentMembers")
    List<Member> findTop10ByOrderByCreatedAtDesc();
}
~~~

The search index can provide three corresponding relations:

- **membersBySurname**: searches by last name.
- **membersByStatus**: searches by status.
- **recentMembers**: retrieves up to the 10 most recent members.

Finder methods with parameters will have URI templates for their query parameters. Parameterless methods can have a complete link. The final relation names and URLs must be verified against the actual HAL response.

Do not assign duplicate paths to finder methods in the same search resource. If two methods share a path, routing or link discovery becomes ambiguous and hard to maintain.

## 7. Hiding a query method from the REST API

If a query method is only for internal processing, you can set **exported = false**:

~~~java
@RepositoryRestResource(path = "members")
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-surname", rel = "membersBySurname")
    List<Member> findByLastName(@Param("lastName") String lastName);

    @RestResource(exported = false)
    List<Member> findByInternalReviewFlagTrue();
}
~~~

The method **findByInternalReviewFlagTrue()** remains a repository method and server-side code can still call it. Spring Data REST does not expose that method as a search endpoint.

Hiding a query method is not an authorization rule. If data is accessible through the collection resource, item resource, associations, or another controller, the application must still enforce server-side access control.

## 8. Describing a query method

**@RestResource** also supports descriptive metadata via the **description** attribute:

~~~java
import org.springframework.data.rest.core.annotation.Description;
import org.springframework.data.rest.core.annotation.RestResource;

@RestResource(
    path = "by-surname",
    rel = "membersBySurname",
    description = @Description("Find members by last name")
)
List<Member> findByLastName(@Param("lastName") String lastName);
~~~

The description helps explain the purpose of the finder method in Spring Data REST/ALPS metadata. It does not automatically replace comprehensive API documentation or the project's OpenAPI generation mechanism.

Write descriptions that are concise, accurate, and match the actual behavior of the query method. If a method matches exact last names, do not describe it as fuzzy search or full-text search.

## 9. Verifying the search resource

Start by reading the collection or API root to discover the **search** link:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/members
~~~

Next, read the search index:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/members/search
~~~

Inspect the customized relation, such as **membersBySurname**, and confirm the href contains the **by-surname** path along with the **lastName** variable. Then invoke the finder:

~~~bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "lastName=Nguyen" \
  http://localhost:8080/api/members/search/by-surname
~~~

Check the following:

1. Does the search index contain the expected relation?
2. Does the relation name match the **rel** value?
3. Does the href have the path matching **path**?
4. Does the URI template contain the exact **@Param** variable name?
5. Does the response have the appropriate status code, Content-Type, and data?

Whenever you change path or rel, inspect the search index again. That is where you verify the contract that clients actually see.

## 10. Common errors

### Changing rel while the client still calls the old URL

Rel is the link name in HAL; path is what determines the URL. Clients should look up the link by the new relation and extract href instead of hardcoding the URL.

### Changing path while still looking up the relation by method name

Path and rel are independent. If rel is customized, the key in **_links** may no longer be the Java method name. Inspect the search index.

### Using the wrong query parameter name

The path is **by-surname** and the rel is **membersBySurname**, yet the query parameter is still **lastName**. Using **surname** or **name** instead of **lastName** can cause the request to miss the required parameter.

### Forgetting @Param

If the contract requires a stable parameter name, explicitly declare **@Param**. Do not rely on Java parameter names being retained by the compiler.

### Duplicate finder method paths

Two query methods sharing the same path can cause conflicts when exposing the search resource. Choose a unique and meaningful path for each method.

### Finder method does not appear

Check whether the repository is detected by Spring Data REST, whether the method has **exported = false**, whether the query method is valid, and whether any path configuration conflicts.

### Confusing rel/path with security

Renaming or hiding a link only controls how the API is advertised. Authorization must still be enforced on the server for every resource and operation.

## 11. Key takeaways

- Query methods are exposed under the repository's search resource.
- **@RestResource(path = ...)** customizes the URL of a finder method.
- **@RestResource(rel = ...)** customizes the relation name in HAL.
- **@Param(...)** sets the query parameter name; it is independent of path and rel.
- Clients should discover the search index, extract href, and expand the URI template.
- Use a unique path for each exposed finder method.
- **exported = false** hides a finder method from the REST API without removing the method from the repository.
- Path, rel, and metadata do not replace validation or authorization.

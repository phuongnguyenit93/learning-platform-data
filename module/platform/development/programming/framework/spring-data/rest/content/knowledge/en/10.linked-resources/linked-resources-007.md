# POST to Add an Element to a Collection Association in Spring Data REST

## Objectives

Use HTTP **POST** on an association resource to add an existing resource to a multi-valued relationship, such as adding a **Tag** to the **tags** set of an **Article**.

After this lesson, you can:

- Recognize the association resource of a collection-typed property.
- Find the exact association URL from the parent resource's HAL links.
- Send the URI of the related resource using **text/uri-list**.
- Read the association back to confirm the change was persisted.

## 1. Understanding the Right Endpoint to Call

Spring Data REST can expose association resources for entity relationship properties. For a collection property such as **Set<Tag> tags** or **List<Comment> comments**, the association endpoint represents the list of links for a parent resource.

For example, an article resource:

~~~http
GET /articles/42
Accept: application/hal+json
~~~

can return a HAL representation with links like these:

~~~json
{
  "title": "Spring Data REST",
  "_links": {
    "self": {
      "href": "http://localhost:8080/articles/42"
    },
    "tags": {
      "href": "http://localhost:8080/articles/42/tags"
    }
  }
}
~~~

The link with relation **tags** points to the association resource. Send **POST** to this URL to append a resource to the **tags** association of article 42.

The paths above are examples under the default configuration. Use the actual URL in **_links** of the response. **@RepositoryRestResource** can change the repository path; **@RestResource** on the relationship property can also change the relation or path. Therefore, do not construct URLs manually when the response already provides the link.

**Distinguish the two types of endpoints:**

- **/tags** is the collection resource of the Tag repository, typically used to create or list Tags.
- **/articles/42/tags** is the association resource of a specific Article, used to manage the Tags linked to that Article.

**POST** to an association resource only adds a link. It does not create a new target entity.

## 2. Preparing Entities and Repositories

This example uses a many-to-many relationship between **Article** and **Tag**. **Article.tags** is the owning side of the relationship and stores the join keys in the **article_tag** table.

~~~java
@Entity
public class Article {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @ManyToMany
    @JoinTable(
        name = "article_tag",
        joinColumns = @JoinColumn(name = "article_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private Set<Tag> tags = new LinkedHashSet<>();

    // constructors, getters, and setters
}
~~~

~~~java
@Entity
public class Tag {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToMany(mappedBy = "tags")
    private Set<Article> articles = new LinkedHashSet<>();

    // constructors, getters, and setters
}
~~~

The repositories must be exported by Spring Data REST so clients can discover and reference the resources:

~~~java
@RepositoryRestResource
public interface ArticleRepository
        extends JpaRepository<Article, Long> {
}
~~~

~~~java
@RepositoryRestResource
public interface TagRepository
        extends JpaRepository<Tag, Long> {
}
~~~

Package names, base path configuration, and annotations depend on the application. What matters is that the parent resource has an exported association link and the target entity's URI can be resolved by Spring Data REST.

With bidirectional JPA, pay attention to the owning side of the relationship. In this example **Article.tags** owns the join table, so updating this association writes the link to the join table. If the property exposed as an association endpoint is only the inverse side with **mappedBy**, modifying only the inverse collection may not update the foreign key or join table as expected. Design the mapping and synchronize the owning side properly.

## 3. Ensuring Both Resources Already Exist

Before adding a relationship, both the Article and the Tag must exist. You can create them via each repository's collection resource.

Example creating a Tag:

~~~http
POST /tags
Content-Type: application/json

{
  "name": "spring-data-rest"
}
~~~

Example creating an Article:

~~~http
POST /articles
Content-Type: application/json

{
  "title": "Working with association resources"
}
~~~

Read the **Location** response header or use the **self** link to obtain the actual URI of each resource. Suppose the Article has URI **/articles/42** and the Tag has URI **/tags/7**.

If the Tag already exists, there is no need to recreate it. Just use the existing Tag's URI.

## 4. Sending POST to Add an Element to the Association

Send the request to the Article's association URL:

~~~http
POST /articles/42/tags
Content-Type: text/uri-list
Accept: application/hal+json

http://localhost:8080/tags/7
~~~

Example with cURL:

~~~bash
curl -i -X POST "http://localhost:8080/articles/42/tags" \
  -H "Content-Type: text/uri-list" \
  -H "Accept: application/hal+json" \
  --data "http://localhost:8080/tags/7"
~~~

The parts that must be right:

1. **HTTP method:** **POST**, because the goal is to add an item to a collection association.
2. **Request URL:** the association URL taken from the parent resource's links, here **/articles/42/tags**.
3. **Content-Type:** **text/uri-list**.
4. **Request body:** an absolute URI or valid URI that the application can resolve to the target resource. The body is a plain URI, not a JSON object, and do not wrap the URI in quotes.

Do not send a body like the following:

~~~json
{
  "id": 7,
  "name": "spring-data-rest"
}
~~~

That is entity data, whereas the association endpoint expects a reference to an existing resource by URI. Also do not use **Content-Type: application/json** for a URI-list body.

## 5. Result and Verification

When the request is valid and the association is updated, Spring Data REST typically returns:

~~~http
HTTP/1.1 204 No Content
~~~

**204** means the request was processed and the response has no body. Having no JSON response body does not mean the operation failed.

Read the parent resource or the association resource again:

~~~http
GET /articles/42
Accept: application/hal+json
~~~

Verify that the **tags** link is still present, then read the association contents:

~~~http
GET /articles/42/tags
Accept: application/hal+json
~~~

The result should show the Tag with URI **/tags/7** in Article 42's list of linked tags. You can also inspect the database if you are debugging persistence.

A practical workflow should be:

1. Read the parent resource to obtain the association link.
2. Read or create the target resource to obtain a valid URI.
3. Send **POST** with **Content-Type: text/uri-list**.
4. Read the association resource again to confirm the item was added.

## 6. Common Errors

| Symptom | Causes to check |
|---|---|
| **404 Not Found** | Wrong association URL, parent resource does not exist, or the URI in the body does not point to a resolvable target resource. |
| **415 Unsupported Media Type** | Missing or wrong **Content-Type**; association requests require **text/uri-list**. |
| **400 Bad Request** | Body is not a valid URI or the URI could not be parsed properly. |
| **405 Method Not Allowed** | Endpoint does not support this method, or the property is not an exported collection association. |
| Relationship link missing in HAL | Check whether the repository/entity is exported, whether the relation is hidden with **@RestResource(exported = false)**, and check relation/path configuration. |
| Response succeeds but relationship is missing in database | Check transactions, JPA mapping, and the owning side; pay special attention to inverse properties with **mappedBy**. |
| Duplicate elements | Check collection type (**List** vs. **Set**), **equals**/**hashCode**, unique constraints, and client retries. |

When debugging, check in order: the association URL from HAL, the target resource URI, **Content-Type**, the HTTP status, and then the mapping and persistence state.

## 7. API and Client Design Notes

- **Do not create target entities with an association POST.** If the Tag does not exist yet, create the Tag via its repository resource first and then use its URI.
- **Use server-provided links.** This avoids depending on customized base paths, repository paths, or relation paths.
- **Respect collection types.** **Set** is appropriate when an association should not contain duplicates; **List** preserves order and may allow duplicates depending on mapping.
- **Do not assume POST is idempotent.** If a client times out and retries, read the association first before deciding to resend; also design collections and data constraints to handle duplicates appropriately.
- **Check access permissions.** If the application uses Spring Security, the caller needs permission to read the related resource and permission to modify the association per application policy.
- **Do not confuse with repository collection operations.** **POST /tags** creates a Tag; **POST /articles/42/tags** links an existing Tag to Article 42.

## Key Takeaway

To append an element to a collection association in Spring Data REST, get the association URL from the parent resource's HAL links, send **POST** to that URL with **Content-Type: text/uri-list**, and place the existing target resource's URI in the body. After the request, read the association resource again to confirm the link was persisted.
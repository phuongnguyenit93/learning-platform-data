# Removing an Element from a Collection Association Using a Member URI

Spring Data REST exposes relationships between entities as **association resources**. For a multi-member association, a client can remove a single member by sending HTTP **DELETE** to the association member's URI. This URI includes the member entity's ID as the final path segment.

For example, a project has many tags. If you want to remove the tag with ID `7` from the project with ID `42`, the request looks like:

~~~http
DELETE /projects/42/tags/7
~~~

This operation unbinds the link between the project and the tag. It does not mean deleting the tag from the repository. Whether the tag entity itself gets deleted depends on JPA mapping, cascades, and the application's entity lifecycle rules.

## Objectives

After this lesson, you can:

- Identify an association collection resource and the URI of each member.
- Use `DELETE` with the member ID in the path to remove a specific element from a collection association.
- Distinguish removing a single link, clearing the entire association, and deleting an entity.
- Understand the roles of HAL links, member URIs, and the `text/uri-list` media type.
- Verify results over HTTP and persistence while handling mapping, permission, and consistency issues.

## 1. Example Model

Suppose an application manages projects and tags. A project can have many tags; a tag can also be used by many projects.

~~~java
@Entity
public class Project {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToMany
    private Set<Tag> tags = new HashSet<>();
}
~~~

Tag entity:

~~~java
@Entity
public class Tag {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
}
~~~

Repositories exposed by Spring Data REST:

~~~java
@RepositoryRestResource(path = "projects")
public interface ProjectRepository
        extends JpaRepository<Project, Long> {
}

@RepositoryRestResource(path = "tags")
public interface TagRepository
        extends JpaRepository<Tag, Long> {
}
~~~

With default configuration, Spring Data REST creates:

- Project collection resource: `/projects`.
- Project item resource: `/projects/{projectId}`.
- Association resource for the `tags` property: `/projects/{projectId}/tags`.
- Tag item resource: `/tags/{tagId}`.

The default association name and path are based on the relationship property name. You can customize them with `@RestResource` on that property.

## 2. Discovering the Association and Member URI

The client should start from the project's item resource:

~~~http
GET /projects/42
Accept: application/hal+json
~~~

The HAL representation can contain a link to the association collection:

~~~json
{
  "name": "Learning Platform",
  "_links": {
    "self": {
      "href": "http://localhost:8080/projects/42"
    },
    "tags": {
      "href": "http://localhost:8080/projects/42/tags"
    }
  }
}
~~~

The client follows the `tags` link to read the tags currently attached to the project:

~~~http
GET /projects/42/tags
Accept: application/hal+json
~~~

The result can represent the collection with item links pointing to each tag:

~~~json
{
  "_embedded": {
    "tags": [
      {
        "name": "java",
        "_links": {
          "self": {
            "href": "http://localhost:8080/tags/7"
          }
        }
      },
      {
        "name": "spring",
        "_links": {
          "self": {
            "href": "http://localhost:8080/tags/8"
          }
        }
      }
    ]
  }
}
~~~

In this example:

- The association collection URI is `/projects/42/tags`.
- The member URI for the `java` tag is `/tags/7`.
- The ID of the member to remove is `7`.

The client can use the member's `self` link to identify the exact related resource. Spring Data REST's member-removal endpoint uses the member's ID as the final path segment.

## 3. DELETE a Specific Member

To remove tag ID `7` from project `42`, call:

~~~http
DELETE /projects/42/tags/7 HTTP/1.1
Accept: application/hal+json
~~~

Or using `curl`:

~~~bash
curl -i -X DELETE http://localhost:8080/projects/42/tags/7
~~~

The path has three parts after the base path:

| Part | Meaning |
| --- | --- |
| `/projects/42` | Item resource of the parent project |
| `/tags` | Association collection resource |
| `/7` | ID of the member to remove from the association |

Spring Data REST's controller has a member-specific route of the form:

~~~text
/{repository}/{id}/{property}/{propertyId}
~~~

Where `propertyId` is the ID of the member entity in the association. In the example above, the route resolves to:

~~~text
/projects/42/tags/7
~~~

This `DELETE` request does not need a JSON body and does not need `text/uri-list`. The member URI is represented by the path segment containing its ID at the end of the URL.

When the operation succeeds, the response is typically `204 No Content`. Clients should not depend on a response body; read the association again to confirm the member has been removed.

## 4. Distinguishing Three Operations

This distinction is essential to avoid deleting the wrong data:

| Intent | Endpoint | Effect |
| --- | --- | --- |
| Remove one member from a collection association | `DELETE /projects/42/tags/7` | Unbind tag 7 from project 42 |
| Operate on the association resource at the property level | `DELETE /projects/42/tags` | Targets the entire association property; not the member-specific route |
| Delete the tag entity | `DELETE /tags/7` | Deletes the tag 7 resource from the repository if permitted |

For collection associations, use the route with the member ID appended to remove a single element. Do not send `DELETE` to the association collection URI expecting it to remove just one member.

`DELETE` on the item resource `/tags/7` has a completely different meaning: it asks to delete the tag entity from the repository. If the tag is referenced by multiple projects, that action can affect many relationships and be blocked by foreign keys or cascades.

## 5. How Does DELETE Differ from POST and PUT on an Association?

Spring Data REST supports different operations on association resources:

| Method | Purpose | Request body / media type |
| --- | --- | --- |
| `GET` | Read the association state | `Accept: application/hal+json` or `application/json` |
| `POST` | Add a member to a collection association | `Content-Type: text/uri-list` |
| `PUT` | Bind member URI(s) to the association; for collections, submit the URI set to link per the endpoint contract | `Content-Type: text/uri-list` |
| `DELETE` | Unbind an association or a specific member via the member-specific URI | No body needed when removing a single member |

Example adding tag 9 to project 42:

~~~http
POST /projects/42/tags HTTP/1.1
Content-Type: text/uri-list

http://localhost:8080/tags/9
~~~

Example with `curl`:

~~~bash
curl -i -X POST -H "Content-Type: text/uri-list" --data "http://localhost:8080/tags/9" http://localhost:8080/projects/42/tags
~~~

`POST` sends the URI of the entity to add in the body. Member-specific `DELETE` puts the ID of the entity to remove in the path. These two protocols are not interchangeable.

If you need to replace the entire set of collection links, review the semantics of `PUT` and send the URI list according to the contract of your Spring Data REST version. Do not use `PUT` just to remove one element if the actual goal is deleting a single member link.

## 6. How to Use the Member URI

In HAL, a member usually has a `self` link pointing to the member entity's URI, for example:

~~~text
http://localhost:8080/tags/7
~~~

This URI tells the client the exact member to act on. With Spring Data REST's member-specific route, the trailing ID (`7`) is placed after the association path:

~~~text
DELETE /projects/42/tags/7
~~~

Do not send the full URL `http://localhost:8080/tags/7` in the `DELETE` request body. Also do not send a JSON object like:

~~~json
{
  "uri": "http://localhost:8080/tags/7"
}
~~~

The member-specific `DELETE` contract is the URI path containing `propertyId`. The member URI is used to discover/identify the resource, while the ID is placed in the final path segment per the controller's route.

If the application uses a base path, reverse proxy, or custom repository path, obtain the association link from the HAL response and build the request according to the actual route. If the ID contains characters requiring URL encoding or the application uses a custom ID mechanism, verify the URI advertised by the server and the behavior of your Spring Data REST version.

## 7. Customizing the Association Path

The default association name comes from the property name. You can customize the path with `@RestResource`:

~~~java
@ManyToMany
@RestResource(path = "labels", rel = "labels")
private Set<Tag> tags = new HashSet<>();
~~~

Then the association collection has the path:

~~~text
/projects/42/labels
~~~

The corresponding member-specific `DELETE` is:

~~~http
DELETE /projects/42/labels/7
~~~

`path` controls the URL segment of the association. `rel` controls the link relation name in HAL. If `path` has been changed, clients must use the new `href` returned by the server; do not continue assembling URLs using the old Java field name.

## 8. Unbinding Does Not Mean Deleting the Entity

When calling:

~~~http
DELETE /projects/42/tags/7
~~~

the meaning of the operation is to remove the relationship between project 42 and tag 7 from the association collection. The tag 7 entity can still exist and continue to be used by other projects.

You can inspect both resources separately after the operation:

~~~http
GET /projects/42/tags
~~~

Tag 7 no longer appears in project 42's association.

~~~http
GET /tags/7
~~~

Tag 7 can still be read through its own repository.

However, the final persistence state also depends on the domain model mapping:

- With `@ManyToMany`, removing a member usually removes the link row in the join table; the referenced entity should not be deleted simply because it was removed from one collection.
- With `@OneToMany`, removing a child from the collection may interact with `orphanRemoval = true`.
- Cascade remove and database constraints can affect entity lifecycle.
- If the relationship is bidirectional, both sides of the object graph must be kept consistent.

Do not deduce that an entity definitely still exists solely from the HTTP status of an association `DELETE`. Check the JPA mapping and re-read the member's item resource if you need to guarantee the entity was not deleted.

## 9. Notes on the JPA Owning Side

In a bidirectional relationship, JPA only persists relationship changes based on the owning side.

Example:

~~~java
@Entity
public class Project {

    @ManyToMany
    @JoinTable(
        name = "project_tag",
        joinColumns = @JoinColumn(name = "project_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private Set<Tag> tags = new HashSet<>();
}

@Entity
public class Tag {

    @ManyToMany(mappedBy = "tags")
    private Set<Project> projects = new HashSet<>();
}
~~~

In this example, `Project.tags` is the owning side; `Tag.projects` is the inverse side because it has `mappedBy`.

When removing a tag from a project, ensure the change is made on the owning side. If clients operate on an association exposed from the inverse side, test join-table persistence carefully and consider updating both sides with appropriate domain logic.

A helper method can keep the object graph consistent:

~~~java
public void removeTag(Tag tag) {
    tags.remove(tag);
    tag.getProjects().remove(this);
}
~~~

This example illustrates keeping both collections synchronized in domain logic. Do not assume every mapping needs this exact helper; adjust according to the owning side, cascades, and entity design of your application.

## 10. Required Relationships and Common Errors

Spring Data REST describes association `DELETE` as an unbind operation. If the association is a single-valued relationship that does not allow null or cannot be unbound, `DELETE` may return `405 Method Not Allowed`.

For collection associations, removing a single member uses the member-specific URI. Common errors:

| Symptom | Possible causes | How to check |
| --- | --- | --- |
| `404 Not Found` | Parent item does not exist, wrong association path, or invalid member URI/ID | Follow HAL links, check parent ID, path, and member ID |
| `405 Method Not Allowed` | Endpoint does not support `DELETE`, association cannot be unbound, or wrong route | Check mapping, repository exposure, and route with `propertyId` |
| Member still appears after `DELETE` | Change was not persisted, operated on inverse side, or transaction rolled back | Re-read the association and check owning side and persistence logs |
| Member entity unexpectedly deleted | Cascade or orphan removal affected entity lifecycle | Check cascades, `orphanRemoval`, and mapping |
| Wrong member removed | Client built the wrong ID or used an ID from another collection | Use the member `self` link and verify the member belongs to the right association |
| Collection link not found | Repository/association is not exported or path was customized | Read the item resource and follow links returned by the server |

Exact HTTP status codes also depend on configuration, exception handlers, repository modules, and the Spring Data REST version.

## 11. Testing Member Removal

A test should verify both the association and the independent entity:

1. Create project 42 with tags 7 and 8.
2. Read `/projects/42` and follow the `tags` association link.
3. Confirm the collection contains the URIs of tag 7 and tag 8.
4. Send `DELETE /projects/42/tags/7`.
5. Confirm a successful response, typically `204 No Content`.
6. Re-read `/projects/42/tags`; tag 7 must no longer be in the collection, while tag 8 remains.
7. Read `/tags/7`; confirm the entity still exists if the mapping does not specify orphan removal or cascade delete.
8. Read `/projects/42`; confirm other links and representation fields remain correct.
9. Inspect the join table or corresponding stored data if persistence verification is needed.
10. Try removing a member that does not belong to the association and record the behavior of your application version.

Before/after verification example:

~~~text
Before:
Project 42 -> tags [7, 8]

Request:
DELETE /projects/42/tags/7

After:
Project 42 -> tags [8]
Tag 7 -> still exists in /tags/7 (when no lifecycle rule deletes it)
~~~

Do not rely solely on reading the collection JSON once. If the application has caching, transactions, or read replicas, re-read after the transaction completes and use a data source capable of confirming the committed state.

## 12. Security and Consistency

Association `DELETE` is a write operation. The API must enforce permissions on both the parent resource and the association.

- The caller must have permission to modify project 42's associations.
- Do not infer authorization simply because the client knows a tag ID.
- Check the tenant/owner of both parent and member to prevent cross-tenant unbinding.
- Validate that the member belongs to the right association before mutating.
- Consider optimistic locking or conflict handling when multiple clients concurrently modify the same collection.
- Record an audit log if business requirements need to track who removed which link and when.

The fact that a member exists in its own repository does not mean the caller is allowed to attach or detach it from every parent resource.

## 13. Quick Checklist

- [ ] Obtained the association `href` from the parent's HAL representation.
- [ ] Obtained the exact member URI from the association collection.
- [ ] Identified the member ID to use as the final path segment.
- [ ] Request uses `DELETE /{repository}/{parentId}/{property}/{propertyId}`.
- [ ] Did not send a JSON body or `text/uri-list` body for member-specific `DELETE`.
- [ ] Distinguished unbinding an association member from deleting the member entity.
- [ ] Checked `@RestResource(path = "...")` if the association path is customized.
- [ ] Checked JPA owning side, cascades, and orphan removal.
- [ ] Checked permission to edit the association and access the member.
- [ ] Re-read the association after the operation and confirmed the member was removed.

## 14. Key Takeaways

To remove a single element from a collection association, use the member-specific URI:

~~~http
DELETE /projects/42/tags/7
~~~

- `/projects/42/tags` is the project's association collection.
- `/7` is the ID of the member to remove.
- The `DELETE` request needs no body; the ID is in the URI.
- `POST` and `PUT` use `text/uri-list` to add or bind URIs; that is a different contract from member-specific `DELETE`.
- Unbinding a link does not automatically mean deleting the entity. Check the mapping, cascades, orphan removal, and owning side.

## References

- Spring Data REST Reference — Repository resources, The Association Resource: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST source — RepositoryPropertyReferenceController: https://github.com/spring-projects/spring-data-rest/blob/main/spring-data-rest-webmvc/src/main/java/org/springframework/data/rest/webmvc/RepositoryPropertyReferenceController.java
- Spring Data REST Reference — Customizing Spring Data REST: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr.html
- Jakarta Persistence Specification — Entity Relationships and owning side: https://jakarta.ee/specifications/persistence/

# PUT to Set or Replace an Association

In Spring Data REST, an entity can link to other entities through associations such as **@ManyToOne**, **@OneToOne**, **@OneToMany**, or **@ManyToMany**. These relationships are exposed as association resources so clients can read, bind, or unbind links over HTTP.

**PUT on an association resource** is used to bind the resource(s) specified by URI to the relationship. For one-to-one or many-to-one relationships, `PUT` sets a new target and replaces the currently linked target. For collection relationships, `PUT` submits a list of URIs for the resources to bind to the collection; if you only want to add a new item to the collection, use `POST`.

The key point is that a `PUT` request to an association resource uses **Content-Type: text/uri-list** and a body containing the URI(s) of the related resource(s). This is a link-updating operation, not sending the entity's full JSON.

## 1. What Is an Association Resource?

Spring Data REST creates an association resource for each exported relationship on an item resource. The default path of an association resource is based on the relationship property name in the entity. You can customize the name and path using **@RestResource** placed on that property.

Example of a **Person** entity that has one department and multiple roles:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne
    private Department department;

    @ManyToMany
    private Set<Role> roles = new HashSet<>();

    // getters and setters
}
~~~

Suppose the repositories for all entities are exported by Spring Data REST. When a client reads a person:

~~~http
GET /people/1
Accept: application/hal+json
~~~

The HAL representation can contain association links:

~~~json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/1"
    },
    "department": {
      "href": "http://localhost:8080/people/1/department"
    },
    "roles": {
      "href": "http://localhost:8080/people/1/roles"
    }
  }
}
~~~

In this example:

- **`/people/1/department`** is the association resource for the single-department relationship.
- **`/people/1/roles`** is the association resource for the roles collection.
- URIs such as **`/departments/3`** or **`/roles/2`** are item resources of the linked entities.

Clients should obtain these URLs from the HAL links in the response rather than assembling paths manually. Default link names come from the association property names; **@RestResource** on the property can customize that name and path.

## 2. Using PUT to Set a One-to-One or Many-to-One Relationship

For single-valued relationships such as **@OneToOne** or **@ManyToOne**, the association resource links to only one resource at a time.

For example, a person has a **department** association. To bind person 1 to department 3, send:

~~~http
PUT /people/1/department
Content-Type: text/uri-list
~~~

The body is the URI of the department:

~~~text
http://localhost:8080/departments/3
~~~

This can be called using `curl`:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/departments/3" \
  http://localhost:8080/people/1/department
~~~

If the person is currently linked to another department, `PUT` sets the link to department 3. Do not send a JSON object for the department to the association resource body; this endpoint expects a URI in **text/uri-list** format.

To replace the department with another department, send `PUT` to the same association resource with the new URI:

~~~http
PUT /people/1/department
Content-Type: text/uri-list
~~~

~~~text
http://localhost:8080/departments/5
~~~

For one-to-one or many-to-one associations, send only one URI. Sending multiple URIs for a to-one relationship causes Spring Data REST to return **400 Bad Request**.

## 3. Using PUT with Collection Relationships

For multi-valued relationships such as **@OneToMany** or **@ManyToMany**, the association resource represents a collection. `PUT` can accept multiple URIs, each pointing to a resource to bind to the association.

For example, person 1 has roles. Send a URI list:

~~~http
PUT /people/1/roles
Content-Type: text/uri-list
~~~

~~~text
http://localhost:8080/roles/2
http://localhost:8080/roles/4
~~~

Each URI is on its own line. The URI list describes the resources submitted to bind to the association. Read the association back after the request to verify the actual relationship state in the application.

Example with `curl`:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data-binary $'http://localhost:8080/roles/2\nhttp://localhost:8080/roles/4' \
  http://localhost:8080/people/1/roles
~~~

If you want to add a role to the existing collection, `POST` is the more appropriate operation. The next section clearly distinguishes these methods.

## 4. Comparing PUT, POST, and DELETE on an Association Resource

Spring Data REST supports `GET`, `PUT`, `POST`, and `DELETE` for association resources. Each method has a specific purpose:

| HTTP method | Scope | Effect |
|---|---|---|
| **GET** | Association resource | Read the current relationship state |
| **PUT** | Single-valued or collection relationship | Bind the resource(s) specified by URI to the relationship |
| **POST** | Collection associations only | Add a new item to the collection |
| **DELETE** | Association resource | Unbind the association |

### POST to add an item to a collection

For example, person 1 already has role 2 and wants to add role 5 without resubmitting the whole list with `PUT`:

~~~http
POST /people/1/roles
Content-Type: text/uri-list
~~~

~~~text
http://localhost:8080/roles/5
~~~

`POST` is supported only for collection associations. It appends the specified new item to the collection.

### DELETE to unbind an association

For example, unbinding the `department` link from a person:

~~~http
DELETE /people/1/department
~~~

`DELETE` on an association resource asks Spring Data REST to unbind the association. For associations that do not allow null or are not optional, this operation may be rejected with **405 Method Not Allowed**.

Check the relationship state after calling `DELETE`. If the goal is simply to replace one department with another, `PUT` with the new URI usually expresses that intent more clearly.

## 5. Comparing PUT on an Entity Resource vs. PUT on an Association Resource

Both endpoints use HTTP `PUT`, but they take different bodies and have different meanings.

| Endpoint | Content-Type | Body | Meaning |
|---|---|---|---|
| **PUT /people/1** | **application/json** or **application/hal+json** | Representation of Person | Replace entity state |
| **PUT /people/1/department** | **text/uri-list** | URI of Department | Set or replace the target of the `department` relationship |
| **PUT /people/1/roles** | **text/uri-list** | One or more Role URIs | Bind the specified resources to the collection association |

For example, do not send this payload to **`/people/1/department`**:

~~~json
{
  "id": 3,
  "name": "Engineering"
}
~~~

The association resource expects the URI of the related entity:

~~~text
http://localhost:8080/departments/3
~~~

Distinguishing the endpoints properly avoids media type errors or binding failures when a client wants to update a relationship.

## 6. Reading and Confirming an Association

Before updating, read the item resource to discover links:

~~~http
GET /people/1
Accept: application/hal+json
~~~

Follow the **department** or **roles** link in **_links** to access the association resource.

Reading the state of a single-valued relationship:

~~~http
GET /people/1/department
Accept: application/hal+json
~~~

Reading the state of a collection association:

~~~http
GET /people/1/roles
Accept: application/hal+json
~~~

After `PUT`, `GET` the association resource again to verify that the link points to the expected entity. You can also `GET` the related item resource to confirm that the target URI exists.

When verifying a collection, compare all returned links against the submitted URIs. Do not rely solely on the HTTP status code to conclude that the relationship was saved properly.

## 7. Customizing an Association Resource

The default name and path of an association resource are based on the relationship property name. You can use **@RestResource** on the property to customize `rel` and `path`.

Example:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne
    @RestResource(path = "team", rel = "team")
    private Department department;
}
~~~

In this example, the association resource can be exposed with the **team** link and path **`/people/1/team`** instead of the default property name **department**.

Clients should follow the `href` returned in HAL. When changing an association name or path, clients directly calling the old URL will need to be updated.

## 8. Conditions to Verify

For a `PUT` association operation to succeed, verify that:

1. The repositories of both the source entity and target entity are exported by Spring Data REST.
2. The relationship is declared properly on the entity and is accessible via an association resource.
3. The URI(s) in the body point to existing, accessible item resources.
4. The request uses **Content-Type: text/uri-list**.
5. For a to-one relationship, the body contains only one URI.
6. For a collection association, each URI is placed on its own line.
7. The JPA mapping updates the owning side of the relationship, especially for bidirectional relationships using **mappedBy**.
8. Application access permissions and validation rules allow modifying that relationship.

Spring Data REST cannot bind a non-existent resource. A wrong URI, an unexported target resource, or insufficient permissions can cause the request to fail.

With JPA, you need to understand the owning side of the relationship. In bidirectional relationships, updating only the collection on the inverse side may produce no database changes if the owning side is not synchronized. Design setters or domain logic to keep both sides consistent when your application requires it.

## 9. Common Errors and How to Fix Them

| Symptom | Possible cause | Resolution |
|---|---|---|
| Association `PUT` returns `415 Unsupported Media Type` | Using **application/json** instead of **text/uri-list** | Change `Content-Type` and send plain URIs |
| To-one `PUT` returns `400 Bad Request` | Body contains multiple URIs for a single-valued relationship | Send only one target URI |
| Relationship does not change | URI does not point to a valid item resource or property is not exported | Check the `href` in HAL and repository configuration |
| Collection `POST` is rejected | Association is not a collection | Use `PUT` for single-valued relationships |
| `DELETE` returns `405 Method Not Allowed` | Relationship is declared non-optional | Check `nullable`/`optional` and the business contract |
| Request succeeds but database does not reflect expected relationship | Bidirectional mapping did not sync the owning side | Check `mappedBy` and two-way update logic |
| Client calls the wrong association URL | Constructing paths manually instead of following HAL links | Read the item resource and use the `href` in `_links` |

## 10. Practice Workflow

You can practice with **Person**, **Department**, and **Role**:

1. Create a person with a known ID and read **GET /people/{id}**.
2. From **_links**, retrieve the `href` values of the **department** and **roles** associations.
3. Send `PUT` to the **department** association with a Department URI to set or replace the department.
4. Send `PUT` to the **roles** association with a list of Role URIs to bind.
5. Send `POST` to **roles** with another URI to add a role.
6. `GET` each association resource again to confirm its state.
7. Try `DELETE` on an optional association in a development environment and verify the link has been removed.

Core example requests:

~~~http
PUT /people/1/department
Content-Type: text/uri-list

http://localhost:8080/departments/3
~~~

~~~http
PUT /people/1/roles
Content-Type: text/uri-list

http://localhost:8080/roles/2
http://localhost:8080/roles/4
~~~

~~~http
POST /people/1/roles
Content-Type: text/uri-list

http://localhost:8080/roles/5
~~~

In summary, use `PUT` on an association resource to set or replace a relationship's target by URI, use `POST` to add an item to a collection association, and use `DELETE` to unbind a link when the association permits it. Always follow HAL links, send the correct media type, and `GET` the association again after updating to confirm the result.

Official references:

- [Spring Data REST — Repository resources, Association Resource](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)

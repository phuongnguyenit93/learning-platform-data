# Customizing path, collectionResourceRel, and itemResourceRel

Spring Data REST automatically exports repositories as REST resources. For each repository, the application provides a path for clients to access the collection and items, while Spring Data REST generates HAL-compliant links to describe discoverable resources.

You can use **`@RepositoryRestResource`** to customize three important properties:

- **`path`**: the URL path segment used to access the collection.
- **`collectionResourceRel`**: the link relation name (abbreviated as `rel`) of the link pointing to the collection resource.
- **`itemResourceRel`**: the link relation name of the item resources represented inside the collection.

These three attributes solve two different concerns: **`path`** controls the URL, while the two **`rel`** attributes control relation names in the hypermedia representation.

## 1. Where Is @RepositoryRestResource Used?

**`@RepositoryRestResource`** belongs to the package:

~~~java
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
~~~

Place the annotation on the repository interface managed by Spring Data REST. For example:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

If no custom attributes are specified, Spring Data REST automatically derives the mapping from the domain type and default relation configuration. For example, with the **`Employee`** entity, the collection is typically exported at a path like **`/employees`**.

When you need to control the URL path or link names exposed to clients, explicitly declare the corresponding attributes.

## 2. Customizing path

**`path`** specifies the path segment of the collection resource. This is the URL portion following the Spring Data REST base path.

For example:

~~~java
@RepositoryRestResource(path = "staff-directory")
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

If the application does not configure a global base path, the collection resource has the URL:

~~~http
GET /staff-directory
~~~

Each item is accessed via a URL of the form:

~~~http
GET /staff-directory/{id}
~~~

If the application configures a base path, such as **`/api`**, the full URL will have the form **`/api/staff-directory`**.

Notes:

- **`path`** is a path segment, for example **`staff-directory`**.
- Choose short, meaningful, and stable path names so clients can integrate over the long term.
- Avoid duplicate paths across exported repositories, as resource mappings may conflict.
- Changing **`path`** alters the URL clients call. If the API is already in use, consider backward compatibility and a client migration plan.

## 3. Customizing collectionResourceRel

**`collectionResourceRel`** specifies the relation name of the link pointing to the collection resource in the HAL representation.

For example:

~~~java
@RepositoryRestResource(
    path = "staff-directory",
    collectionResourceRel = "staff"
)
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

When a client sends **`GET /`** to the Spring Data REST root, the link to the collection may appear as follows:

~~~json
{
  "_links": {
    "staff": {
      "href": "http://localhost:8080/staff-directory"
    }
  }
}
~~~

In this example:

- Clients access the collection using the URL **`/staff-directory`**.
- The HAL link name is **`staff`**.
- Changing **`collectionResourceRel`** does not automatically change the collection URL.

HAL clients should follow links described in **`_links`** instead of constructing URLs from relation names. This allows the server to preserve resource discoverability even when URL structures change.

## 4. Customizing itemResourceRel

**`itemResourceRel`** specifies the relation name pointing to an item resource inside a collection representation.

For example:

~~~java
@RepositoryRestResource(
    path = "staff-directory",
    collectionResourceRel = "staff",
    itemResourceRel = "staffMember"
)
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

When a client sends **`GET /staff-directory`**, the **`_embedded`** section of HAL may look like this:

~~~json
{
  "_embedded": {
    "staffMember": [
      {
        "id": 1,
        "name": "An"
      },
      {
        "id": 2,
        "name": "Binh"
      }
    ]
  }
}
~~~

The name **`staffMember`** describes the relation to each item in the collection. The item URL still follows **`/staff-directory/{id}`**; this attribute does not change the URL structure.

You can choose singular, readable relation names that accurately reflect the resource type, such as **`person`**, **`order`**, or **`staffMember`**. Use a consistent naming convention across the entire API.

## 5. Combining All Three Attributes

In practice, all three attributes are often declared on the same repository:

~~~java
package com.example.demo.repository;

import com.example.demo.entity.Employee;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "staff-directory",
    collectionResourceRel = "staff",
    itemResourceRel = "staffMember"
)
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

With this configuration, the values have the following meanings:

| Attribute | Value | Effect |
|---|---|---|
| **`path`** | **`staff-directory`** | The collection URL is **`/staff-directory`** |
| **`collectionResourceRel`** | **`staff`** | Rel of the link to the collection |
| **`itemResourceRel`** | **`staffMember`** | Rel of items in the collection representation |

You can remember this by looking at two different places in HAL:

- **`_links`** at the application root contains the collection link with rel **`staff`**.
- **`_embedded`** of the collection contains the items with rel **`staffMember`**.

A relation name is hypermedia metadata, not a Java class name, database table name, or entity property name.

## 6. Distinguishing path and rel

The three attributes serve separate roles. They should not be used interchangeably.

| Change | Collection URL | HAL Link Name |
|---|---|---|
| Change only **`path`** | Changes | Keeps the current rel mapping |
| Change only **`collectionResourceRel`** | Unchanged | Changes the collection's rel |
| Change only **`itemResourceRel`** | Unchanged | Changes the item's rel inside the collection |
| Change all three | Changes according to the new path | Updates both rels |

For example, with:

~~~java
@RepositoryRestResource(
    path = "employees",
    collectionResourceRel = "team",
    itemResourceRel = "member"
)
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

Clients access the collection via **`/employees`**, look up the collection link by rel **`team`** at the root, and read the item list under rel **`member`** in the collection representation.

If you only want to change the URL while keeping the default link names, you only need to configure **`path`**. If you want to keep the URL while changing how clients identify resources, configure the corresponding rel attributes.

## 7. Verifying the Mapping After Configuration

After starting the application, verify using an HTTP client, browser, or HAL Explorer.

**Step 1 — Check the root resource**

~~~http
GET http://localhost:8080/
Accept: application/hal+json
~~~

Find the link with rel **`staff`** and confirm that `href` points to **`/staff-directory`**.

**Step 2 — Check the collection resource**

~~~http
GET http://localhost:8080/staff-directory
Accept: application/hal+json
~~~

Verify that:

- The collection returns successfully.
- The **`_embedded`** section uses rel **`staffMember`** for the items.
- **`self`**, pagination, and navigation links are still generated properly if present.

**Step 3 — Check the item resource**

~~~http
GET http://localhost:8080/staff-directory/1
Accept: application/hal+json
~~~

Confirm that the item can be accessed through the new path. The ID value must exist in the test data.

You can use curl:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
curl -i -H "Accept: application/hal+json" http://localhost:8080/staff-directory
curl -i -H "Accept: application/hal+json" http://localhost:8080/staff-directory/1
~~~

If the application has a base path, replace the test URLs with the full URLs including that base path.

## 8. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Old URL returns 404 after changing **`path`** | The collection has moved to the new path | Check `path` in the annotation and update clients |
| Root still has a different rel than expected | **`collectionResourceRel`** is not placed on the right repository or configuration has not been loaded | Check imports, annotations, and restart the application |
| **`_embedded`** has an unexpected key | **`itemResourceRel`** is not configured or default mapping is being used | Check the annotation and collection response |
| Rel changed but URL did not change | This is expected behavior because rel and path are independent | Follow `href` in **`_links`** to see the actual URL |
| Application fails to start or mapping conflicts | Two repositories may declare conflicting paths | Ensure each collection resource has a distinct path |

## 9. API Design Considerations

- Choose business-meaningful paths that are consistent in singular/plural usage and casing.
- Use relation names that describe the resource type so clients understand link contents without relying on Java class names.
- Keep rel names stable because HAL clients may rely on rels to locate resources.
- Check both the root resource and collection representations after each change.
- When an API already has external clients, changing `path` can break existing URLs; consider forwarding support or API versioning.
- Only use **`@RepositoryRestResource`** on repositories that require customization. These attributes do not replace security configuration, projections, or method-level export rules.

Official documentation:

- [RepositoryRestResource API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)

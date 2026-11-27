# Customizing Association Resource Paths on Relationship Properties

In Spring Data REST, an entity's relationship property can be exposed as an **association resource** so clients can read or modify links between resources. The **@RestResource** annotation placed directly on the relationship property lets you customize two parts of that link: **path** determines the URL path segment, while **rel** determines the relation name in the HAL link.

This lesson belongs to the **Resource Paths** group of Spring Data REST. The focus is on how to customize an association's endpoint without changing the repository's collection/item paths.

## Objectives

After this lesson, you can:

- Recognize the association resource generated from an entity's relationship property.
- Use **@RestResource(path = ..., rel = ...)** on a property to customize the endpoint and HAL link relation.
- Distinguish an association path from a repository path, and distinguish rel from a Java property name.
- Verify the actual path via HAL representations and HTTP requests.
- Understand the scope of exported = false, bidirectional relationships, and what to check when updating an association.

## 1. Association Resources in Spring Data REST

Suppose the employees repository manages the Employee entity. An employee can reference their manager:

~~~java
@Entity
public class Employee {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne
    private Employee manager;
}
~~~

When the repository is exposed by Spring Data REST, an employee resource has a URI of the form:

~~~text
/employees/{id}
~~~

The manager property is a relationship to another entity. Spring Data REST can represent this relationship as a link in the employee's representation and provide an association resource to access that relationship.

With default naming, the association is typically accessed in the form:

~~~text
/employees/{id}/manager
~~~

This path has the following structure:

- /employees: the collection path exposed by the repository.
- /{id}: the item resource of an employee.
- /manager: the association resource corresponding to the manager relationship property.

An association resource is an endpoint for the relationship between resources. It differs from the item resource of the related entity: the manager's item resource has its own URI, whereas the association resource represents the link from the current employee to the manager.

## 2. Using @RestResource to Customize path and rel

Import the annotation:

~~~java
import org.springframework.data.rest.core.annotation.RestResource;
~~~

Place the annotation directly on the relationship property:

~~~java
@ManyToOne
@RestResource(path = "supervisor", rel = "reportsTo")
private Employee manager;
~~~

Then:

- path = "supervisor" customizes the URL segment of the association resource.
- rel = "reportsTo" customizes the link relation name in the HAL representation.
- The Java property name remains manager.
- The JPA relationship remains manager; the annotation does not change the relationship type, foreign key, or table structure.

Example repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "employees")
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

The customized association path has the form:

~~~text
/employees/{id}/supervisor
~~~

Meanwhile, the link relation is represented by the name reportsTo.

Simplified HAL representation example for the employee with ID 42:

~~~json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "https://api.example.com/employees/42"
    },
    "reportsTo": {
      "href": "https://api.example.com/employees/42/supervisor"
    }
  }
}
~~~

HAL clients should look up the link by the reportsTo relation and then use the href returned by the server. Clients do not need to construct URLs from property names or assume path structures.

## 3. Distinguishing path and rel

The two attributes serve two different purposes:

| Attribute | Role | Example | Result |
| --- | --- | --- | --- |
| path | URL path segment of the association resource | path = "supervisor" | /employees/42/supervisor |
| rel | Relation name in HAL _links | rel = "reportsTo" | _links.reportsTo |

Another example:

~~~java
@ManyToOne
@RestResource(path = "lead", rel = "teamLead")
private Employee manager;
~~~

The returned link may look like:

~~~json
{
  "_links": {
    "teamLead": {
      "href": "https://api.example.com/employees/42/lead"
    }
  }
}
~~~

In this example, the URL ends with /lead, while the key in _links is teamLead.

Do not treat rel as a URL name or path as a field name. When designing an API, path should be short, stable, and readable; rel should express the relationship semantics that clients need to understand.

## 4. Customizing One-to-Many or Many-to-Many Relationships

The same mechanism applies to collection-valued associations. For example, an employee can belong to multiple teams:

~~~java
@Entity
public class Employee {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToMany
    @RestResource(path = "teams", rel = "memberOf")
    private Set<Team> teams = new HashSet<>();
}
~~~

With the repository:

~~~java
@RepositoryRestResource(path = "employees")
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

The association resource has a path of the form:

~~~text
/employees/{id}/teams
~~~

And the link in HAL has the relation memberOf:

~~~json
{
  "_links": {
    "memberOf": {
      "href": "https://api.example.com/employees/42/teams"
    }
  }
}
~~~

Clients can follow this link to read the related collection. Operations that modify the association depend on cardinality, mapping configuration, and the HTTP methods supported by Spring Data REST for that resource. When integrating, inspect actual association requests/responses rather than assuming an association collection endpoint behaves identically to a repository collection endpoint.

@RestResource only customizes how the association is exposed. It does not create a JPA relationship, does not replace @ManyToMany, @OneToMany, @ManyToOne, or @OneToOne, and does not configure cascade or fetch strategies.

## 5. Scope of the Property-Level Annotation

When @RestResource is placed on a relationship property, the annotation affects the resource/link representing that relationship.

It does not automatically change:

- The repository collection path, such as /employees.
- The item resource path, such as /employees/42.
- The Java property name, such as manager.
- Column or foreign key names in the database.
- JSON property names serialized by Jackson under separate configuration.
- Ownership in JPA or how Hibernate persists data.

To distinguish configurations:

| Need | Common Mechanism |
| --- | --- |
| Change repository collection path | @RepositoryRestResource(path = "...") on the repository |
| Change association path/rel | @RestResource(path = "...", rel = "...") on the relationship property |
| Hide an association resource | @RestResource(exported = false) on the relationship property |
| Rename a JSON property | Jackson configuration, e.g., @JsonProperty, if appropriate for the representation used |
| Rename a column or foreign key | JPA mapping such as @Column, @JoinColumn |
| Control who is allowed to access | Spring Security and corresponding security configuration |

Do not use @RepositoryRestResource(path = ...) to individually change the path of an association. The repository annotation controls the repository's resources; the property annotation controls the corresponding association resource.

## 6. Hiding an Association Resource

If you do not want to expose a particular relationship, you can set exported = false:

~~~java
@ManyToOne
@RestResource(exported = false)
private Employee manager;
~~~

When this property is not exported, Spring Data REST does not expose that association resource as a regular association endpoint, and the corresponding link is not emitted in the default association exposure manner.

This does not mean the entity or repository is hidden completely. The employees repository can still be exposed, and other properties/relationships can still appear according to their configurations.

exported = false is also not an authorization mechanism. If clients must not view or modify data, configure authentication, authorization, and corresponding data-protection policies.

## 7. Bidirectional Relationships

A bidirectional JPA relationship typically has two Java properties. For example:

~~~java
@Entity
public class Employee {

    @ManyToOne
    @RestResource(path = "supervisor", rel = "reportsTo")
    private Employee manager;

    @OneToMany(mappedBy = "manager")
    private Set<Employee> directReports = new HashSet<>();
}
~~~

manager and directReports are two separate properties. Each property can be represented by Spring Data REST as its own association if exported and mapped appropriately.

Customizing manager does not automatically change the path or rel of directReports. If you need to name both associations, declare the annotation on each property:

~~~java
@ManyToOne
@RestResource(path = "supervisor", rel = "reportsTo")
private Employee manager;

@OneToMany(mappedBy = "manager")
@RestResource(path = "reports", rel = "directReports")
private Set<Employee> directReports = new HashSet<>();
~~~

In JPA, mappedBy identifies the inverse side of the relationship; the owning side still determines how link updates are persisted to the database. Changing path/rel does not alter owning-side rules. When updating associations over REST, inspect both the object graph state and the persisted data.

## 8. Naming Considerations

When choosing path and rel, consider:

1. **Avoid path collisions:** an association path should avoid conflicting with other resources or mappings under the item resource.
2. **Stability over time:** URLs are part of the API contract. Changing a path can break existing clients holding stored endpoints.
3. **Business clarity:** supervisor or teams is easier to understand than technical names like employeeRef.
4. **Singular vs. plural distinction:** single-valued associations typically use singular names; collection associations typically use plural names.
5. **Meaningful rel:** the relation should describe the relationship from the current resource, such as reportsTo, memberOf, or directReports.
6. **Avoid coupling to internal field names:** if a Java field is renamed but you want to keep the API stable, set path and rel explicitly.
7. **Check path characters:** use path names compliant with URI rules and application routing conventions.

path and rel names should be treated as part of the public contract. If clients already consume the API, evaluate compatibility impact before changing them.

## 9. Verifying an Association Resource Over HTTP

With the employees repository and the manager property customized to path = "supervisor" and rel = "reportsTo", you can verify in sequence:

**Step 1 — Fetch the item resource**

~~~http
GET /employees/42
Accept: application/hal+json
~~~

Confirm the response includes the _links.reportsTo link with href pointing to /employees/42/supervisor.

**Step 2 — Follow the association link**

~~~http
GET /employees/42/supervisor
Accept: application/hal+json
~~~

Confirm the response represents the linked employee or corresponding association state.

**Step 3 — Check the default path**

Test against /employees/42/manager in a test environment to verify clients must use the configured path. Do not rely on field names to build URLs when the server already publishes HAL links.

**Step 4 — Check collection relationships**

If the property is a collection like teams, fetch the item resource, follow the memberOf link relation, and confirm the association resource returns the related elements.

**Step 5 — Check writing and deleting relationships**

Test association operations supported by Spring Data REST using the proper media type and relationship cardinality. Verify the HTTP response, HAL links, and persisted data after the request. Use recoverable test data to avoid altering real relationships.

Example using curl to inspect the link:

~~~bash
curl -H "Accept: application/hal+json" \
  http://localhost:8080/employees/42
~~~

If the application has a base path or runs behind a reverse proxy, the actual URL will include the corresponding prefix. Use the href returned by the server rather than assuming the host and base path.

## 10. Common Errors

| Symptom | Possible Cause | Troubleshooting Direction |
| --- | --- | --- |
| Link still uses the old field name | Annotation placed in the wrong location, not recognized in persistent property mapping, or app has not loaded the new build | Verify the annotation is on the right relationship property and restart/rebuild the application |
| URL changed but HAL relation did not | Only path was configured, rel was not configured | Declare both attributes if you want explicit control over both the URL and link name |
| HAL relation changed but client calls the wrong URL | Client used rel as a path segment | Read href inside the link relation and call that exact URL |
| Association does not appear | Relationship is not exported, repository is not exposed, or mapping is not recognized | Check repository exposure, relationship property, exported flag, and Spring Data REST configuration |
| Annotation changed but endpoint still does not work | Request uses wrong base path or item ID; another route occupies the path; client is using cache | Check self link, association href, HTTP status, and routing logs |
| Association update does not persist as expected | Incorrect JPA mapping, owning side, cascade, or transaction | Check owning side, update both sides of the object graph when needed, and verify persisted data |
| Inverse relationship has an unexpected path | Only one of the two properties in a bidirectional relationship was customized | Place @RestResource separately on each property to be exposed |

## 11. Implementation Workflow

1. Identify the root repository and item resource containing the relationship property.
2. Determine whether the relationship is single-valued or collection-valued, unidirectional or bidirectional.
3. Inspect existing JPA mappings and ensure the property is actually an association.
4. Place @RestResource(path = "...", rel = "...") on the exact property to customize.
5. Keep @RepositoryRestResource(path = "...") on the repository to manage the collection path independently.
6. Start the application and fetch the item resource with Accept: application/hal+json.
7. Read _links to confirm the new relation and href.
8. Call the association href to verify the resource is routed properly.
9. If the relationship is writable, test update operations suited to its cardinality and confirm persisted data.
10. Verify client compatibility before releasing path/rel changes.

## 12. Quick Checklist

- [ ] @RestResource is placed on the right relationship property.
- [ ] path reflects the desired association endpoint name.
- [ ] rel reflects the relationship semantics clients should follow.
- [ ] Association path/rel are distinguished from the repository path.
- [ ] HAL representation returns the expected relation and href.
- [ ] Clients use href from HAL instead of constructing URLs manually.
- [ ] Bidirectional relationships are configured individually on each exposed property.
- [ ] exported = false is used only when you genuinely want to hide the association.
- [ ] JPA owning side and persistence behavior remain correct after updates.
- [ ] Security is handled separately from association exposure.

## 13. Key Takeaways

To customize an association resource on a relationship property, place **@RestResource** directly on that property:

~~~java
@ManyToOne
@RestResource(path = "supervisor", rel = "reportsTo")
private Employee manager;
~~~

- path creates the /supervisor URL segment for the association resource.
- rel creates the _links.reportsTo name in the HAL representation.
- @RepositoryRestResource(path = "employees") still manages the /employees collection resource.
- The annotation does not change the field name, JPA mapping, foreign key, or authorization rules.

Let clients discover the API through link relations and hrefs published by the server. That way, the server can adjust internal paths while clients continue relying on a meaningful link contract.

## References

- Spring Data REST Reference — Associations: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST Reference — Customizing the REST endpoint paths: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr.html
- Spring Data REST — RestResource API: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RestResource.html
- Spring Data REST — RepositoryRestResource API: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html

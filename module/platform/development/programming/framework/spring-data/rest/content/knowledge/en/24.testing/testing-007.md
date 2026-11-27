# Testing Adding, Replacing, Unlinking, and Required Associations

## 1. Goal

Spring Data REST publishes entity associations as association resources. Clients can read link state, attach an existing entity, replace an association, or remove links using the appropriate HTTP methods.

Distinguish two groups of associations:

- **Single-valued association (to-one):** a property pointing to at most one entity, typically using ManyToOne or OneToOne.
- **Collection-valued association (to-many):** a property containing multiple entities, typically using OneToMany or ManyToMany.

Operations carry different meanings depending on cardinality:

- GET reads the state of the association.
- PUT binds a resource URI to the association; for a to-one relationship, this replaces the currently linked resource with the new resource.
- POST is only for collection associations and adds an item.
- DELETE unlinks the association if the relationship is nullable/optional. For required relationships, Spring Data REST may reject it with 405 Method Not Allowed.

Removing a link does not mean deleting the entity on the other side. This lesson walks through verifying the HAL response, HTTP status, and persisted data after each operation.

## 2. Illustrative Data Model

Suppose a Person always belongs to a Department and has multiple Roles:

    @Entity
    public class Person {

        @Id
        @GeneratedValue
        private Long id;

        private String name;

        @ManyToOne(optional = false)
        @JoinColumn(name = "department_id", nullable = false)
        private Department department;

        @ManyToMany
        @JoinTable(
            name = "person_role",
            joinColumns = @JoinColumn(name = "person_id"),
            inverseJoinColumns = @JoinColumn(name = "role_id")
        )
        private Set<Role> roles = new LinkedHashSet<>();

        // getters and setters
    }

    @Entity
    public class Department {

        @Id
        @GeneratedValue
        private Long id;

        private String name;
    }

    @Entity
    public class Role {

        @Id
        @GeneratedValue
        private Long id;

        private String name;
    }

Person.department is a required to-one relationship. Person.roles is a collection relationship. The collection is initialized with LinkedHashSet to avoid null states and prevent duplicate elements per equals/hashCode.

Repositories:

    public interface PersonRepository
            extends JpaRepository<Person, Long> {
    }

    public interface DepartmentRepository
            extends JpaRepository<Department, Long> {
    }

    public interface RoleRepository
            extends JpaRepository<Role, Long> {
    }

Spring Data REST generates item resources for Person and association resources for each exported association. Default relation/path names are usually derived from property names; they can be customized with RestResource on the property or RepositoryRestResource on the repository.

## 3. Discovering Association Links Before Modifying

First, GET the item resource:

    GET /people/42
    Accept: application/hal+json

Illustrative response:

    {
      "name": "An",
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        },
        "department": {
          "href": "http://localhost:8080/people/42/department"
        },
        "roles": {
          "href": "http://localhost:8080/people/42/roles"
        }
      }
    }

These two hrefs are association resources:

- department represents the single-valued Person.department relationship.
- roles represents the Person.roles collection association.

Clients should follow the hrefs provided by the server. If paths or rels have been customized, do not manually construct URLs from entity names, IDs, or property names.

Read association state with GET:

    GET /people/42/department
    Accept: application/hal+json

    GET /people/42/roles
    Accept: application/hal+json

To-one relationships typically return the representation or link of the currently linked entity. Collection relationships typically return a collection representation, possibly with `_embedded` and self links for each Role. Use the actual response to identify the resource URIs to send in modification requests.

## 4. The text/uri-list Media Type

Spring Data REST association binding operations use the text/uri-list media type. The body contains URIs of existing resources, one URI per line:

    http://localhost:8080/departments/7
    http://localhost:8080/roles/3
    http://localhost:8080/roles/5

Do not send a JSON object for Department or Role to an association endpoint when the contract expects text/uri-list. URIs must point to valid, accessible target resources within the application.

Prefer taking URIs from the self link of target resources. This avoids relying on default paths and supports custom base paths or item URIs.

## 5. Attaching or Replacing a To-One Relationship with PUT

To bind a Department to a Person, send PUT to the association resource with a single URI:

    PUT /people/42/department
    Content-Type: text/uri-list

    http://localhost:8080/departments/7

PUT binds the specified resource to the association. For a to-one relationship, if Person currently belongs to Department 4, sending PUT with Department 7 replaces the existing link with Department 7.

Re-read the association to confirm:

    GET /people/42/department
    Accept: application/hal+json

The response should reflect Department 7. You can GET Person again to verify the department link still exists; if you need to check target data, follow the self link or association href.

A to-one association accepts only one URI. If the body contains multiple URIs for a single-valued relationship, Spring Data REST returns 400 Bad Request per the association resource contract. Do not use PUT with multiple URIs to turn a to-one relationship into a collection.

If the Department URI does not exist or the caller lacks permission, the operation can fail. Check the status code and actual error response; do not assume a request succeeded just because the client sent a body.

## 6. Removing an Optional To-One Relationship with DELETE

If a to-one association is optional, you can remove the link by calling DELETE on the association resource:

    DELETE /people/42/mentor

This example assumes Person has a nullable `mentor` association. Calling DELETE on the association resource removes the link; it does not delete the Mentor entity from its repository.

After the operation, GET Person or the association resource again to confirm the link is gone. Depending on the association type and framework version, a successful response may be 204 No Content or another configured success status.

Do not send a body containing the entity URI to delete alongside DELETE on the association resource. The request targets unlinking the association at the target URI.

If the relationship is not nullable, Spring Data REST may return 405 Method Not Allowed on DELETE association. This indicates unbinding is not supported for required associations. To move Person to another Department, use PUT with the new Department URI.

## 7. Adding Elements to a Collection Association with POST

For a collection association like Person.roles, POST adds a Role to the collection:

    POST /people/42/roles
    Content-Type: text/uri-list

    http://localhost:8080/roles/3

POST is only for collection associations. It appends the specified resource to the current collection rather than replacing the entire list.

Multiple URIs can be sent in the same body to add multiple items:

    POST /people/42/roles
    Content-Type: text/uri-list

    http://localhost:8080/roles/3
    http://localhost:8080/roles/5

After POST, GET the association resource again and confirm the new Roles appear. If the collection uses a Set, duplicate elements may not increase link count; exact behavior also depends on equals/hashCode and persistence mappings.

Do not use POST on to-one associations. For single-valued relationships, use PUT to attach or replace the linked resource.

## 8. Replacing All Links in a Collection with PUT

PUT can submit the desired list of URIs for a collection association:

    PUT /people/42/roles
    Content-Type: text/uri-list

    http://localhost:8080/roles/3
    http://localhost:8080/roles/5

Use this operation when the client wants to synchronize the set of links to the exact list sent. The URIs in the body become the bound resources after the operation; do not send a JSON array if the endpoint expects text/uri-list.

Unlike POST, PUT binds the specified URI list to the association and is typically used to replace the current link set. Clients must know the exact final list desired, because omitting a URI from the body can remove that link from the set after the update.

If the collection is large, avoid fetching the entire list to the client just to change one element. Using a dedicated business endpoint to add/remove a single member can be more appropriate, especially when pagination, concurrency control, or per-item permission checks are needed.

## 9. Removing a Single Element from a Collection Association

Standard association resources publish POST to add items and PUT to bind a list of URIs. DELETE on an association resource means unbinding the association; do not assume DELETE with a body removes just a single item from the collection.

One reconciliation approach is:

1. GET the collection association and extract self URIs of existing elements.
2. Build a new URI list excluding the URI of the element to remove.
3. PUT the remaining URI list to the association resource with Content-Type text/uri-list.
4. GET the association again to confirm the element was removed.

For example, Person 42 has Role 3, Role 5, and Role 8. To remove Role 5, PUT the remaining list:

    PUT /people/42/roles
    Content-Type: text/uri-list

    http://localhost:8080/roles/3
    http://localhost:8080/roles/8

This replaces the link set with the new list; it does not delete Role 5 from RoleRepository. If your application or framework version provides a member-specific association endpoint, only use it when explicitly published/documented and tested.

For very large collections, fetching all items and PUTting back can be costly and prone to overwriting concurrent updates. In such cases, create a custom controller/service operation with explicit semantics, such as removeRole(personId, roleId), to handle a single link inside a transaction.

## 10. Distinguishing Unlink from Deleting an Entity

The following two requests have completely different meanings:

    DELETE /people/42/department

    DELETE /departments/7

The first request unlinks the department relationship from Person 42 if the association is nullable. The second request deletes Department 7 from the repository. Do not use DELETE on an item resource just to unlink one Person.

Similarly, removing Role 5 from Person 42 does not mean deleting Role 5 if other People still use that Role. With ManyToMany, a Role is often shared across multiple People; deleting the Role entity can corrupt data belonging to multiple aggregates.

Watch JPA mappings:

- CascadeType.REMOVE can cause parent deletion to cascade to related entities.
- orphanRemoval=true can cause child entities to be deleted when removed from the parent's collection.
- Unlinking and orphan deletion are two distinct business decisions.

Do not add cascade remove or orphanRemoval merely to make association endpoints work. Choose mappings based on true entity ownership and lifecycle.

## 11. Required Relationships at the JPA Layer

For a required to-one relationship, declare optional=false and appropriate column constraints:

    @ManyToOne(optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;

optional=false indicates the association cannot be missing per JPA mapping. nullable=false requires the foreign key column to be non-null in the generated or updated schema. You can add @NotNull if you want Bean Validation to check before persistence.

Do not rely solely on the UI to require users to choose a Department. The server must validate the association before saving, and the database should have appropriate foreign key/not-null constraints.

If the association is required, DELETE on the association resource cannot be used to set the property to null; Spring Data REST may return 405 Method Not Allowed. If Person needs to switch to another Department, use PUT with the new Department URI instead of DELETE followed by re-linking.

## 12. Required Collection Relationships and Minimum-One-Element Rules

A collection-valued association always exists as a collection object in the object model, though it can be empty. That differs from a to-one association having a null value.

If business rules require Person to have at least one Role, define a minimum-count rule. For example:

    @ManyToMany
    @Size(min = 1, message = "Person must have at least one role")
    private Set<Role> roles = new LinkedHashSet<>();

@Size(min=1) expresses the requirement that the collection has at least one element when Bean Validation runs. @NotEmpty can also be used for non-empty collections.

Do not assume every association resource operation automatically triggers the entity's exact validation path. If an invariant must hold across every update path, check Spring Data REST lifecycle events, validation listeners, or actual service/domain operations and write integration tests for association PUT/POST/DELETE.

For complex rules like requiring at least one active Role or requiring Person to have a Role within the same tenant, use a validator/service that inspects association contents rather than merely counting elements.

## 13. Synchronizing Both Sides of a JPA Relationship

With bidirectional associations, JPA has an owning side and an inverse side. Modifying a collection on one side without updating the owning side can prevent the database from saving the relationship as intended.

Example helper methods:

    public void addRole(Role role) {
        roles.add(role);
        role.getPeople().add(this);
    }

    public void removeRole(Role role) {
        roles.remove(role);
        role.getPeople().remove(this);
    }

The example above assumes Role has a people collection and Person.roles is mapped accordingly. Adjust helpers to match mappedBy and the owning side of your actual entities.

When Spring Data REST handles association resources, the framework uses persistent metadata to update associations. Verify mappings, reload entities in a fresh persistence context, and inspect both sides if the domain model has bidirectional relationships.

Do not inspect only in-memory objects from the request. Re-read data after the transaction completes to verify the foreign key or join table actually changed.

## 14. Operation Ordering and Response Statuses

An association verification flow should follow this sequence:

1. GET the parent resource to obtain the association href.
2. GET the association resource to read current state.
3. GET the target entity's item resource to confirm the URI is valid and accessible.
4. Send PUT or POST with text/uri-list per cardinality.
5. Verify the success status code.
6. GET the association resource again and confirm the new link.
7. Reload parent/child via the repository to confirm persistence.

Response status can depend on the Accept header and Spring Data REST's return-body configuration. Association endpoints may return 2xx with a body or 204 No Content. Verify against your application version's contract instead of hard-coding a single success status if configuration permits multiple response styles.

Notable errors:

- 400 Bad Request: e.g. sending multiple URIs for a to-one association.
- 404 Not Found: nonexistent parent or target URI, or wrong path.
- 405 Method Not Allowed: unexported method or required association disallowing unbind.
- 401/403: caller is unauthenticated or lacks permission.
- 409 or other persistence errors: may arise from constraints/concurrency/custom exception handling; check actual error contract.

## 15. Concurrency Control When Replacing Collections

When two clients concurrently GET Person.roles, each client may hold a stale list. If client A PUTs a new list first, client B might PUT another list built from the stale snapshot and accidentally lose A's changes.

For large or frequently updated collection associations:

- Use ETag/If-Match if the resource and API enable version-based conditional requests.
- Keep add/remove operations element-by-element in a service/controller to avoid replacing the whole set.
- Enforce permissions and invariants within the same transaction.
- Consider optimistic locking on the aggregate root or versioning on a join entity.
- Return an explicit conflict when the client snapshot is stale.

Do not automatically re-GET and re-PUT an old payload with a new version without merging changes. That can overwrite another client's updates.

## 16. Testing Associations with MockMvc

You can write an integration test for attaching a Department:

    mockMvc.perform(put("/people/{id}/department", personId)
            .contentType("text/uri-list")
            .content(departmentUri))
        .andExpect(status().is2xxSuccessful());

Then re-read the association and verify the new Department's href is present.

Testing adding a Role:

    mockMvc.perform(post("/people/{id}/roles", personId)
            .contentType("text/uri-list")
            .content(roleUri))
        .andExpect(status().is2xxSuccessful());

Testing replacing the Role set:

    mockMvc.perform(put("/people/{id}/roles", personId)
            .contentType("text/uri-list")
            .content(roleUri3 + "\n" + roleUri8))
        .andExpect(status().is2xxSuccessful());

The snippets above are skeletons. In real tests, create Person, Department, and Role first; use URIs from self link responses instead of assuming paths if the API is customized.

Tests should cover:

- PUT to-one replaces the old association with the new association.
- PUT to-one with multiple URIs is rejected.
- DELETE optional to-one unlinks the association.
- DELETE required to-one is rejected.
- POST collection adds an element while preserving prior elements.
- PUT collection synchronizes to the desired URI set.
- Removing one member from a collection using the remaining list or a custom remove operation.
- Target entity is not deleted when only unlinking an association.
- Disallowing an empty collection if a business rule requires at least one element.
- Unauthorized callers cannot modify associations.

After each operation, verify both GET association and repository/database state. Asserting 2xx alone is not enough to prove the link actually updated properly.

## 17. Manual Testing with curl

Replace the current Department:

    curl -i -X PUT \
      -H "Content-Type: text/uri-list" \
      -H "Accept: application/hal+json" \
      --data "http://localhost:8080/departments/7" \
      http://localhost:8080/people/42/department

Add a Role to the collection:

    curl -i -X POST \
      -H "Content-Type: text/uri-list" \
      -H "Accept: application/hal+json" \
      --data "http://localhost:8080/roles/3" \
      http://localhost:8080/people/42/roles

Remove an optional to-one association:

    curl -i -X DELETE \
      -H "Accept: application/hal+json" \
      http://localhost:8080/people/42/mentor

These URLs are examples. Replace them with actual hrefs from HAL responses. Do not send DELETE to Department or Role item resources when the goal is only to remove a link.

## 18. Common Mistakes

**Using JSON instead of text/uri-list**

Association resources bind URIs of target resources. Use the right Content-Type and the URI of an exported item.

**Using POST for to-one relationships**

POST only supports collection associations. Use PUT to attach or replace a single-valued relationship.

**Using DELETE to delete the target entity**

DELETE on an association resource removes the link; DELETE on an item resource deletes the entity. Pick the right URI for your goal.

**Deleting a required association**

A to-one optional=false relationship or non-null foreign key column cannot be set to null. Spring Data REST may return 405 for DELETE on non-optional associations.

**Assuming a collection cannot be empty because OneToMany is declared**

Collections can be empty. If business logic requires at least one element, declare and enforce a separate invariant.

**Deleting one item by calling DELETE on the entire collection**

DELETE on an association resource is not a selective delete of one member. Use PUT with the remaining list or an explicit custom operation.

**Confusing unlink with orphan removal**

If orphanRemoval=true, removing an element from a collection can delete the child entity upon saving. Check mappings before using association endpoints.

**Checking only response status**

A 2xx response does not prove the owning side or join table updated. Reload the entity and inspect saved links.

**Ignoring concurrent updates**

PUTting an entire collection from a stale snapshot can lose another client's changes. Use ETag/If-Match or per-item operations with version checks.

## 19. Hands-On Exercise

Given a Person with a required Department and multiple Roles:

1. Declare Department using ManyToOne(optional=false) and JoinColumn(nullable=false).
2. Declare roles as a collection initialized with an empty Set.
3. Create Department, Role, and Person data via repositories or fixtures.
4. GET the Person resource and read the association hrefs for department and roles.
5. GET the association resources to inspect initial state.
6. PUT a different Department URI to the department association; confirm the new Department replaces the old Department.
7. Try PUTting two URIs for department and confirm the request is rejected.
8. Try DELETE on the required department association and observe status/error.
9. POST a new Role to roles; confirm existing Roles remain.
10. PUT a desired list of Role URIs to replace the link set.
11. Remove one Role from the collection by PUTting the remaining list or using a custom operation.
12. Confirm the removed Role still exists in the Role repository if no orphan-removal rule is present.
13. Add a Size(min=1) constraint or business validator if Person must have at least one Role.
14. Attempt an update that empties the collection and confirm the invariant is enforced.
15. Write MockMvc integration tests for add, replace, remove, required-association rejection, and authorization.
16. Reload data in a fresh transaction/persistence context to confirm the relationship was persisted.

Self-check questions:

- How do PUT and POST differ on association resources?
- Why is PUT appropriate for replacing a to-one relationship?
- Why is POST only for collection associations?
- How does DELETE on an association differ from DELETE on an item resource?
- When does DELETE on an association return 405?
- How do you remove a single element from a collection without deleting the target entity?
- Why does OneToMany not automatically guarantee a collection has at least one element?
- How can orphanRemoval and CascadeType.REMOVE affect unlinking?
- Why is reloading the entity after a request necessary to verify persistence?
- How do you avoid lost updates when two clients concurrently PUT a collection?

## 20. Takeaways

- Read HAL links before modifying; use hrefs advertised by the server.
- Association resources support GET, PUT, POST, and DELETE depending on cardinality and configuration.
- PUT binds URIs to an association; for to-one, use one URI to attach or replace.
- POST is only for collection associations and appends elements.
- DELETE unlinks an association if optional; required relationships may return 405.
- Use text/uri-list and URIs of target resources.
- Unlinking does not mean deleting the target entity.
- Remove a collection item by PUTting the remaining list or using a per-item custom operation.
- optional=false, nullable=false, and Bean Validation enforce required relationships at appropriate layers.
- Collections can be empty; minimum-one-element rules require dedicated validation/domain logic.
- Check owning side, cascade, and orphanRemoval before modifying associations.
- Test HAL responses, HTTP statuses, and persisted data.

## References

- Spring Data REST Reference — Repository resources and Association Resource: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST Reference — Customizing supported HTTP methods: https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html
- Jakarta Persistence Specification — Relationships and optional associations: https://jakarta.ee/specifications/persistence/
- Spring Framework Reference — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html

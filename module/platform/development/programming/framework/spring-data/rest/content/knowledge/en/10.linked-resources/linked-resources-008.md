# DELETE to Unbind a Link vs. Deleting the Target Entity in Spring Data REST

Spring Data REST can expose both entity resources and association resources (links between entities). Both resource types can involve HTTP `DELETE`, but their business meanings are different:

- **DELETE on an association resource** asks to unbind a relationship between two resources. Example: removing an address from a person's profile.
- **DELETE on an item resource** asks to delete the entity itself identified by the URI. Example: deleting an address record from the repository.

Unbinding a link does not mean deleting the entity on the other side of the link. When designing a client, identify the exact URI advertised by HAL and choose the right target resource for the `DELETE` operation.

## 1. Entity Resources and Association Resources

Suppose an application manages people and addresses. A person has one address:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne
    private Address address;

    // getters and setters
}
~~~

An address is an independent entity:

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue
    private Long id;

    private String city;

    private String street;

    // getters and setters
}
~~~

Both repositories can be exposed via Spring Data REST:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}

@RepositoryRestResource(path = "addresses")
public interface AddressRepository extends JpaRepository<Address, Long> {
}
~~~

Suppose the person has ID `42` and the address has ID `7`. Illustrative URIs:

- Person entity resource: `/people/42`.
- Address entity resource: `/addresses/7`.
- Association resource for the `address` property on the person: `/people/42/address`.

The last two URIs serve two different targets. `/addresses/7` identifies the `Address` entity; `/people/42/address` identifies Person 42's `address` association.

Actual URIs depend on repository paths, base paths, association mappings, export configuration, and the links advertised by Spring Data REST. Clients should discover links from responses instead of deriving URLs manually.

## 2. DELETE on an Association Resource: Unbinding the Relationship

Suppose the response of `GET /people/42` advertises the link:

~~~json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~

If the client wants this person to no longer be linked to the current address, the client calls `DELETE` on the association resource:

~~~http
DELETE /people/42/address
~~~

This operation asks Spring Data REST to unbind the relationship between Person 42 and the currently linked Address. For a to-one association, this can be represented after unbinding as having no value—for instance, the `address` property is set to `null` if the domain model and data constraints allow it.

The request above is not a request to delete the `Address` entity. The target entity still has its own URI `/addresses/7` and can continue to be accessed if it still exists and is exported.

For example, after unbinding the association, the person's representation may no longer contain the `address` link:

~~~json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

The actual response also depends on representation configuration and other associations. The key point is that deleting the relation changes Person's link to Address; it does not automatically delete the Address from the datastore.

## 3. DELETE an Element in a Collection Association

An entity can link to multiple other entities. For example, a person has multiple groups or roles:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany
    private Set<Role> roles = new HashSet<>();

    // getters and setters
}
~~~

If the collection association is exposed under the `roles` relation, the item resource can provide a link to the association resource:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "roles": {
      "href": "http://localhost:8080/people/42/roles"
    }
  }
}
~~~

To unbind a specific role from that person, Spring Data REST typically exposes an association item URI with the element identifier appended, for example:

~~~http
DELETE /people/42/roles/7
~~~

This operation unbinds the link between Person 42 and Role 7. If Role 7 is still used by other people, the `Role` entity continues to exist and its other relationships remain intact.

For collection associations, distinguish three intents:

- View the currently linked items via the association resource.
- Unbind one specific item from the collection association.
- Delete the item entity from its own repository.

Clients must use the exact links advertised by the API for the association and the element to unbind. The illustrative URI structure may vary depending on association type and application mapping.

## 4. DELETE on an Item Resource: Deleting the Entity Itself

If the actual goal is to delete Address 7 from the system, the client sends `DELETE` to the Address entity resource:

~~~http
DELETE /addresses/7
~~~

This deletes the `Address` entity with ID `7` through the Address repository. It is different from:

~~~http
DELETE /people/42/address
~~~

The first request targets the `Address` record. The second request targets Person 42's `address` relationship.

When an entity is deleted, associations pointing to that entity can be affected by foreign key constraints, ORM mappings, cascades, reference handling, and business logic. The application may need to unbind links first, reject deletion because references remain, or process related relationships inside a transaction.

Do not use `DELETE` on an item resource merely because you want to remove an entity from another entity's collection. If the entity still needs to exist for other relationships or business flows, unbind the corresponding association instead.

## 5. Table Comparing the Two Operations

| Request | Affected resource | Meaning |
|---|---|---|
| `DELETE /people/42/address` | Association resource | Unbind the address from Person 42 |
| `DELETE /people/42/roles/7` | One association in a collection | Unbind Role 7 from Person 42 |
| `DELETE /addresses/7` | Address item resource | Delete entity Address 7 |
| `DELETE /people/42` | Person item resource | Delete entity Person 42 |

Look at the URI and the relation the client is following. If the URI sits under the owner's item resource and represents an association, the operation targets the relationship. If the URI is an item resource of the target repository, the operation targets the entity.

## 6. Unbinding an Association Does Not Guarantee the Entity Is Always Kept

At the API level, deleting an association requests removing the relationship. However, the entity's state after unbinding is also influenced by the domain model and persistence configuration.

Cases to keep in mind:

- **Many-to-many:** typically removes the join row from the join table; entities on both sides still exist.
- **Many-to-one:** typically clears the reference from the owner entity to the referenced entity; the target entity still exists unless other logic deletes it.
- **One-to-many with orphanRemoval:** if a child element is removed from the relationship and the mapping enables `orphanRemoval = true`, JPA can delete the child entity when the transaction is flushed/committed.
- **Cascade remove:** deleting an owner entity can cascade to related entities if configured accordingly. This is persistence behavior that must be distinguished from the HTTP semantics of association `DELETE`.
- **Foreign key constraints and validation:** the database or domain can reject unbinding an association if the relationship is required or unsatisfied constraints remain.

For example, a required relationship may not allow setting the foreign key to `null`. In that case, an unbind request may fail due to validation or persistence errors. If business rules require removing the link while keeping the target entity, configure the mapping and domain rules appropriately.

With bidirectional associations in JPA, you must update the owning side of the relationship. Many domain models provide helper methods to update both sides, such as removing a role from a collection and synchronizing the back-reference. Check how the application's repositories and association handlers update the object graph so persisted data matches expectations.

## 7. Why Should Clients Discover Association Links?

Spring Data REST uses hypermedia to advertise associations. Instead of building URLs by string concatenation, clients should read the relations in `_links` of the item resource.

Example:

~~~http
GET /people/42
Accept: application/hal+json
~~~

The response may contain:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    },
    "roles": {
      "href": "http://localhost:8080/people/42/roles"
    }
  }
}
~~~

Clients can use the `address` or `roles` relation to identify the association resource. For collection associations, the client continues discovering the collection representation and links to individual items if exposed by the API.

This allows the client to follow the hypermedia contract when the server changes host, context path, or URL structure. Clients still need to understand each relation's meaning and only send `DELETE` when the user or business flow genuinely intends to unbind the relationship.

If an association is hidden or not exported, clients should not guess endpoints. Check export configuration and the exposed representation.

## 8. Association DELETE vs. Adding/Replacing Links

To clarify the meaning of `DELETE`, you can place it alongside operations that create or replace associations.

For a to-one association, the client can bind a related resource using the target resource's URI:

~~~http
PUT /people/42/address
Content-Type: text/uri-list

http://localhost:8080/addresses/7
~~~

Here `PUT` sets Person 42's `address` association to point to Address 7 per the association resource contract.

For a collection association, clients typically add an item using `POST` to the collection association resource:

~~~http
POST /people/42/roles
Content-Type: text/uri-list

http://localhost:8080/roles/7
~~~

Once the link has been created, `DELETE` on the association item can be used to unbind that specific element:

~~~http
DELETE /people/42/roles/7
~~~

These examples show common Spring Data REST mappings. Use the exact method, URI, and media type exposed or supported by the actual application version; associations can vary by cardinality, mapping, and configuration.

## 9. Permissions, Validation, and HTTP Responses

Association `DELETE` is still a data-mutating operation. The application must verify client permissions on both the owner entity and the relationship being unbound. Do not only check permission to delete the target entity and infer that the client can unbind every association.

Scenarios to handle:

- The user lacks permission to modify the owner entity.
- The association does not exist or the element does not belong to the owner's collection.
- A required association is not permitted to be unbound.
- The target entity is still referenced by other data.
- The transaction fails due to database constraints or persistence errors.
- The entity has already been deleted or modified by a concurrent request.

Exact HTTP status codes depend on the endpoint, Spring Data REST version, and error-handling configuration. Clients should not assume every `DELETE` returns the same status or response body. Handle success and error responses according to the API contract, and `GET` the resource again when state confirmation is needed.

## 10. Testing to Ensure Entities Are Not Accidentally Deleted

An integration test should verify both the association and the target entity's continued existence.

Example for a to-one association:

1. Create Address 7 and Person 42 referencing Address 7.
2. Call `DELETE` on Person 42's association resource.
3. Re-read Person 42 and confirm the `address` association has been unbound.
4. Directly read `/addresses/7` or query the repository to confirm Address 7 still exists when the mapping has no orphan-removal or related delete logic.
5. Call `DELETE` on `/addresses/7` in a separate test to verify entity deletion behavior and related constraints.

Example for a collection association:

1. Create Person 42 with Role 7 and another Role.
2. Call `DELETE` on Role 7's association item.
3. Re-read Person 42's `roles` collection and confirm Role 7 is no longer linked.
4. Confirm Role 7 still exists and its relationships with other owners are preserved if business rules require it.
5. Test unbinding a role that does not belong to Person 42 and verify the appropriate response.

If JPA enables `orphanRemoval`, write a dedicated test to verify whether the child entity is deleted after removal from the collection. This outcome depends on mapping and cannot be deduced from the HTTP method name alone.

## 11. Choosing the Endpoint in Your Application

Use `DELETE` on an association resource when the goal is to unbind the relationship between two entities while keeping the target entity independent. For example: removing an address from a user's profile or removing a role from their list of roles.

Use `DELETE` on an item resource when the goal is to delete the entity itself from the repository and the application permits that operation. For example: permanently deleting an address that is no longer managed.

Before sending a request, determine:

- Whether the URI belongs to an item resource or an association resource.
- Which entity is the owner and which is the target.
- Whether the relationship is to-one or a collection.
- Whether the mapping has `orphanRemoval`, cascades, or required constraints.
- Whether the client is authorized to unbind the association or delete the corresponding entity.

## 12. Key Takeaways

- `DELETE` on an association resource unbinds the relationship; `DELETE` on an item resource deletes the entity identified by the URI.
- `DELETE /people/42/address` illustrates unbinding the address from Person 42; `DELETE /addresses/7` illustrates deleting Address 7.
- For collection associations, use the association resource and element identifier per the mapping exposed by Spring Data REST to unbind a single link cleanly.
- Unbinding an association does not automatically mean deleting the target entity, though `orphanRemoval`, cascades, validation, and persistence mappings can affect data state.
- Clients should discover relations from HAL instead of constructing URLs manually.
- Tests should verify both that the link was removed and that the target entity still exists when business rules require keeping it.

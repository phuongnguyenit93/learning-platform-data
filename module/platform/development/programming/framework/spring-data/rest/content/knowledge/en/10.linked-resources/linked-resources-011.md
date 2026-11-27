# Impact of the Owning Side and Transactions When Updating Associations

## Objectives

When a client modifies an association through Spring Data REST, sending the right URI to the association resource is only part of the operation. With JPA, the owning side of the relationship determines which changes are written to the foreign key or join table. Transactions determine whether related changes are committed together or can leave inconsistent state behind.

Therefore, when designing association endpoints, you must identify which property is the owning side, update that side properly, and ensure changes to both ends of the relationship happen within the same transaction.

## Owning Side and Inverse Side in JPA

In a bidirectional relationship, JPA distinguishes:

- **Owning side:** the side declaring the mapping that writes the relationship to the database, typically the side with `@JoinColumn` or the join table declaration. Changes on this side determine whether the foreign key or join record is updated.
- **Inverse side:** the side declaring `mappedBy` pointing to the property on the owning side. This side enables navigating the relationship in the object model, but does not govern foreign key updates.

Common rules:

| Relationship type | Typical owning side |
| --- | --- |
| Bidirectional `@ManyToOne` / `@OneToMany` | The `@ManyToOne` side owns the foreign key; `@OneToMany(mappedBy = ...)` is the inverse side |
| Bidirectional `@OneToOne` | The side declaring `@JoinColumn` owns it |
| Bidirectional `@ManyToMany` | The side declaring `@JoinTable`; the other side uses `mappedBy` |

Do not determine the owning side by looking at which entity is the business parent. Read the JPA mapping: `mappedBy` points to the property referenced on the owning side.

## Example: Person and Address

Suppose a person has many addresses and each address belongs to one person. The `person_id` foreign key resides in the `address` table, so `Address.person` is the owning side:

    @Entity
    public class Person {
        @Id
        private Long id;

        @OneToMany(mappedBy = "person")
        private List<Address> addresses = new ArrayList<>();

        public void addAddress(Address address) {
            addresses.add(address);
            address.setPerson(this);
        }

        public void removeAddress(Address address) {
            addresses.remove(address);
            address.setPerson(null);
        }
    }

    @Entity
    public class Address {
        @Id
        private Long id;

        @ManyToOne(fetch = FetchType.LAZY)
        @JoinColumn(name = "person_id")
        private Person person;

        public void setPerson(Person person) {
            this.person = person;
        }
    }

`Person.addresses` is the inverse side because it has `mappedBy = "person"`. `Address.person` owns the relationship because it declares `@JoinColumn(name = "person_id")`.

When assigning an address to a person, simply adding it to `person.getAddresses()` is not enough to instruct JPA to update `person_id`. You must set `address.setPerson(person)` on the owning side. The `addAddress` helper updates both sides so the in-memory object graph stays consistent.

Similarly, when removing an address from the relationship, you must update `Address.person` according to business rules. Removing an element only from the inverse collection can leave the old foreign key value intact in the database.

## How Do Spring Data REST Association Resources Relate?

Spring Data REST exposes associations based on the relationships that repositories and mappings make accessible. Clients should take the association URL from `href` in `_links`, rather than assembling URLs manually.

For example, the representation of `/people/1` may include a link to the `addresses` association. The client can send a URI list in `text/uri-list` format to that link:

    PUT /api/people/1/addresses HTTP/1.1
    Content-Type: text/uri-list

    http://localhost:8080/api/addresses/10
    http://localhost:8080/api/addresses/11

This request expresses the addresses the client wants to link to that person. However, what gets persisted in the database still depends on the mapping's owning side. If the association endpoint mutates the inverse property `Person.addresses` without updating `Address.person`, JPA may not write the foreign keys as the client expects.

For bidirectional relationships, make sure server-side logic updates the owning side. You can place two-way synchronization logic in entity helper methods and call them from services or custom endpoints. If you need to hook into Spring Data REST's association lifecycle, you can use appropriate event handlers such as `BeforeLinkSaveEvent` to apply business rules before saving. Do not assume that modifying the inverse-side collection will automatically synchronize the other property.

## Updating Relationships Within the Same Transaction

When changing an association, there are usually at least two logical steps: loading the related entities and updating the necessary properties. If the application must synchronize both ends of a relationship, those changes should happen within the same transaction.

Example service updating the relationship on the owning side `Address.person`:

    @Service
    public class PersonAddressService {
        private final PersonRepository personRepository;
        private final AddressRepository addressRepository;

        public PersonAddressService(
                PersonRepository personRepository,
                AddressRepository addressRepository) {
            this.personRepository = personRepository;
            this.addressRepository = addressRepository;
        }

        @Transactional
        public void assignAddress(Long personId, Long addressId) {
            Person person = personRepository.findById(personId)
                    .orElseThrow();
            Address address = addressRepository.findById(addressId)
                    .orElseThrow();

            person.addAddress(address);
            // Address.person is the owning side.
            addressRepository.save(address);
        }
    }

In this transaction, the entities are loaded and modified within the same unit of work. JPA writes the changes on flush or commit. For managed entities inside a persistence context, dirty checking can detect changes automatically; calling `save` on the owning side's repository makes explicit which entity carries the mapping governing the relationship.

If the transaction fails before commit, changes within the transaction are rolled back according to the application's transaction mechanism. This prevents a situation where one end of the relationship was saved while the other end was not updated.

## Transactions When Calling Association Endpoints

Spring Data REST executes operations through repositories and the application's transaction configuration. Repository operations are transactional according to Spring Data configuration; custom repository methods or services may need explicit transaction declarations.

Do not treat multiple consecutive HTTP requests as a single shared transaction. For example, one `PUT` request updating a link and another `POST` request updating related data are normally two separate units of work. If business rules require all changes to succeed or roll back together, combine them into a single `@Transactional` service method and expose an appropriate business endpoint.

Transactions also do not fix a wrong owning side. `@Transactional` ensures commit/rollback boundaries for the changes performed; it does not make mutating only a `mappedBy` property a valid foreign key update.

## Cascade and Orphan Removal

Cascades and the owning side solve two different problems:

- `cascade = ...` determines whether persistence operations propagate from one entity to related entities.
- The owning side determines which property controls the relationship in the database.
- `orphanRemoval = true` can cause a child entity to be deleted when it is removed from the relationship under an appropriate mapping.

Adding cascades does not replace updating the owning side. Before using `orphanRemoval`, clearly determine the business meaning of removing a link: merely unbinding the link, or deleting the child entity as well. For shared relationships, inappropriate orphan removal can delete data that other resources still need.

## Concurrent Updates and Optimistic Locking

Two clients can read the same resource and then update an association based on stale state. If both rewrite the collection, the later write can overwrite the earlier write's changes.

You can use `@Version` on an entity to enable optimistic locking:

    @Version
    private Long version;

When two transactions update the same version, the transaction using stale data can fail with an optimistic locking error instead of silently overwriting. Clients need to handle conflicts by re-reading the latest representation, inspecting current links, and resubmitting an appropriate change. If the API uses ETags/conditional requests, clients should also send validators per the endpoint contract.

## Safe Association Update Workflow

1. Read the HAL representation of the source resource and retrieve the association `href`.
2. Inspect the JPA mapping to identify which property is the owning side and which has `mappedBy`.
3. Send the association request with properly formatted URIs, or call a business service if multiple properties must be synchronized.
4. Within the same transaction, update the owning side and keep both sides of the relationship consistent in the object model.
5. Save the entity owning the relationship when needed; let JPA flush and commit the transaction.
6. Re-read the association or resource to verify the saved state.
7. Handle transaction, validation, or optimistic locking errors by reading the latest state before retrying.

The decisive factors are the application's JPA mapping and transaction boundaries. The association URI tells which resources the client wants to link; the owning side determines whether the relationship change is written to the database, and the transaction ensures related changes commit or roll back together.
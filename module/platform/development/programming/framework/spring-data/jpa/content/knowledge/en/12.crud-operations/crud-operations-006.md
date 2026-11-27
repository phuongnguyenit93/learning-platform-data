# getReferenceById, Proxies, and When Existence Is Checked in Spring Data JPA

`getReferenceById(id)` obtains a JPA reference to an entity by primary key without necessarily reading all columns of that row right away. This is useful when the application only needs to establish a relationship by ID. However, receiving a reference object does not prove that the target record exists.

The error-prone aspect is that existence checking can be deferred. The application can create a proxy, assign it to another entity, and only encounter an error when reading a property, flushing, or committing the transaction. This lesson focuses on the proxy lifecycle, the points where a missing ID is detected, API selection, and how to test so errors are handled at the right layer.

## 1. A Practical Scenario

Suppose a system manages support tickets. Each ticket has an assigned staff member:

~~~java
@Entity
@Table(name = "support_tickets")
public class SupportTicket {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "assignee_id", nullable = false)
    private StaffMember assignee;

    protected SupportTicket() {
    }

    public SupportTicket(StaffMember assignee) {
        this.assignee = assignee;
    }

    public Long getId() {
        return id;
    }

    public StaffMember getAssignee() {
        return assignee;
    }

    public void setAssignee(StaffMember assignee) {
        this.assignee = assignee;
    }
}
~~~

When creating a ticket, the application receives staff ID 27. There are two different needs:

- Need to verify whether staff member 27 exists, is active, and is authorized to receive tickets.
- The workflow has already verified the staff member and only needs to assign their ID to the relationship to write the foreign key.

The first need requires reading data and applying business rules. The second need may only require a JPA reference. Choosing the wrong API causes errors to surface late, creates redundant queries, or makes business logic unpredictable.

## 2. Three APIs That Serve Different Purposes

### 2.1. findById — Get the Entity or Know for Sure It Was Not Found

~~~java
StaffMember assignee = staffRepository.findById(27L)
        .orElseThrow(() -> new StaffNotFoundException(27L));
~~~

`findById` returns `Optional<StaffMember>`. When no row exists, the caller receives `Optional.empty()`. When a row exists, the entity is loaded according to the query's fetch plan.

Use this API when:

- The ID comes from an external request.
- You need to return a clear "not found" error.
- You need to read the target entity's status, name, or permissions.
- You need to validate business conditions before writing.

### 2.2. existsById — Only Need a Boolean Answer

~~~java
boolean exists = staffRepository.existsById(27L);
~~~

`existsById` is appropriate if the caller only needs to know whether it exists or not. If you still need the entity afterward, calling `existsById` then `findById` usually creates two database round-trips. When you need the entity and must handle the missing case, `findById` typically accomplishes both in a single read.

### 2.3. getReferenceById — Obtain a Reference by Primary Key

~~~java
StaffMember assignee =
        staffRepository.getReferenceById(27L);
~~~

Spring Data JPA delegates this operation to `EntityManager.getReference`. The provider may create a proxy or an enhanced object to hold the identifier information and defer loading state.

Use this API when:

- The caller only needs to attach the target entity to a relationship.
- The ID has already been verified in a controlled step or is protected by an FK.
- There is no need to read properties of the target entity in the current use case.
- You want to avoid a SELECT just to obtain an object to use as a relationship value.

Do not use `getReferenceById` as validation for user-submitted IDs. Receiving a reference object does not prove the record exists.

| Need | Suitable API |
|---|---|
| Verify an ID exists and return a clear error | `findById` |
| Only need an existence boolean | `existsById` |
| Set up a relationship using a trusted ID | `getReferenceById` |
| Need to read target entity properties | `findById` or a dedicated query |
| Return a DTO containing target entity data | Query/projection selecting the exact fields |

The older names `getOne` and `getById` have been deprecated in newer Spring Data JPA versions. New code should use `getReferenceById` and consult the Javadoc for the dependency version in use.

## 3. How Are Proxies Created and Initialized?

A proxy is an object representing an entity. With Hibernate, a ToOne association can typically be represented by a proxy subclass. The proxy knows the entity type and ID, but does not necessarily contain the full state yet.

~~~java
@Transactional
public void inspectAssignee(Long id) {
    StaffMember reference =
            staffRepository.getReferenceById(id);

    Long knownId = reference.getId();

    // This getter usually needs actual state and may issue a SELECT.
    String displayName = reference.getDisplayName();
}
~~~

Typical workflow:

1. The application requests a reference by entity type and ID.
2. The provider returns a proxy or indirection object.
3. The reference holds the identifier information.
4. When code reads a property requiring state, the proxy asks the provider to initialize it.
5. The provider reads the row by ID and populates the state.
6. Subsequent accesses in the same persistence context can use the loaded state.

With traditional Hibernate proxies, `getId()` can usually return the ID without initializing the proxy; `getDisplayName()` typically requires loading the data. This is common Hibernate behavior, not a uniform guarantee across every provider, enhancement mode, or mapping.

### 3.1. A Proxy Is Not a DTO

Do not return proxies directly to the presentation layer or serializers. A proxy may require an active persistence context to load data. If a serializer invokes a getter after the transaction closes, the application can encounter errors.

In addition, `reference.getClass()` can return a dynamically generated proxy class instead of the original entity class. Avoid exact class equality comparisons or putting proxy class names into business logic.

With subclass proxies, final entities or final methods can restrict traditional proxying. Bytecode enhancement can change how lazy loading works, but requires proper build/runtime configuration.

## 4. When Is the Record Checked?

### 4.1. When Calling getReferenceById

JPA allows the provider to defer reading state. Even so, a provider may detect an error early and throw an exception immediately when creating the reference. Do not assume this call always succeeds for every ID.

### 4.2. When the Proxy Needs State

If the proxy is not yet initialized, calling a getter such as `getDisplayName()` can trigger a SELECT. If no matching row exists, the provider can throw `EntityNotFoundException` or a provider-specific exception.

~~~java
StaffMember reference =
        entityManager.getReference(StaffMember.class, 999999L);

// This may be where the provider SELECTs and discovers the row does not exist.
String name = reference.getDisplayName();
~~~

JPA defines `EntityNotFoundException` for cases where an entity's state is requested but no matching entity exists. Detection timing can vary; Spring may also translate certain persistence exceptions into the `DataAccessException` hierarchy.

### 4.3. When Only Assigning the Reference to a Relationship

~~~java
@Transactional
public Long openTicket(Long staffId) {
    StaffMember assignee =
            staffRepository.getReferenceById(staffId);

    SupportTicket ticket = new SupportTicket(assignee);
    return ticketRepository.save(ticket).getId();
}
~~~

If the proxy is not initialized, the provider can use the ID to write `assignee_id` without SELECTing the staff table.

If `staffId` does not exist:

- With an FK in the database: the INSERT may be rejected when the database checks the FK.
- Deferred constraint: the error may only appear at commit.
- Without an FK: the database may accept the value and create an orphaned reference.
- The provider may detect it earlier if it had to initialize the reference for another reason.

Therefore, `getReferenceById` does not replace validation or FK constraints.

### 4.4. At Flush and Commit

`flush` synchronizes pending changes in the persistence context to the database. It does not end the transaction. `commit` ends the transaction and tells the database to confirm the changes.

~~~java
@Transactional
public void assign(Long ticketId, Long staffId) {
    SupportTicket ticket = ticketRepository.findById(ticketId)
            .orElseThrow();

    StaffMember reference =
            staffRepository.getReferenceById(staffId);

    ticket.setAssignee(reference);

    entityManager.flush(); // FK violation may appear here.
    // Commit happens when the transaction ends successfully.
}
~~~

If the FK is checked immediately on the statement, the error can occur during flush. If the database uses deferred constraints, the error can appear at commit. If the proxy was initialized earlier, the error can occur right at the getter.

### 4.5. Summary of Error Timing

| Usage | Detection point | Possible outcome |
|---|---|---|
| `findById` | SELECT | `Optional.empty()` |
| Provider checks immediately when creating reference | `getReferenceById` | JPA/provider exception |
| Proxy created then property read | Proxy initialization | `EntityNotFoundException` or provider exception |
| Reference assigned then FK written | Flush/commit | Constraint violation |
| No FK, proxy uninitialized | No guaranteed check point | Orphaned FK may be saved |

JPA `EntityNotFoundException` and FK errors are two distinct kinds of errors. The first occurs when the provider needs entity state but cannot find it. The second occurs when the database rejects written data that violates a constraint.

## 5. Choosing an API Based on the Origin of the ID

### 5.1. ID from an External Request

When a user sends `staffId`, the service should verify the ID and apply business rules:

~~~java
@Transactional
public Long openTicket(CreateTicketRequest request) {
    StaffMember assignee = staffRepository.findById(request.staffId())
            .orElseThrow(() ->
                    new StaffNotFoundException(request.staffId()));

    if (!assignee.isActive()) {
        throw new StaffCannotReceiveTicketException(request.staffId());
    }

    SupportTicket ticket = new SupportTicket(assignee);
    return ticketRepository.save(ticket).getId();
}
~~~

This allows returning a clear 404 or business error before writing. Do not let a late proxy failure at the end of the transaction dictate how the request is responded to.

### 5.2. Already Trusted ID

If an internal workflow has already verified the staff member and only needs to establish the relationship, a reference can be used:

~~~java
@Transactional
public void assignTicket(Long ticketId, Long staffId) {
    SupportTicket ticket = ticketRepository.findById(ticketId)
            .orElseThrow(() -> new TicketNotFoundException(ticketId));

    StaffMember reference =
            staffRepository.getReferenceById(staffId);

    ticket.setAssignee(reference);
}
~~~

The example assumes `staffId` comes from a trusted source and the database has an FK. If late write errors cannot be tolerated, use `findById` to verify.

### 5.3. Do Not Double-Check with existsById Followed by getReferenceById

~~~java
if (!staffRepository.existsById(staffId)) {
    throw new StaffNotFoundException(staffId);
}

StaffMember reference =
        staffRepository.getReferenceById(staffId);
~~~

This pattern typically produces two round-trips. It also has a race condition: the record can be deleted after the first check but before the reference is used.

If you need the entity, `findById` both checks and returns the entity. If you only need a reference and the database has an FK, use `getReferenceById` and let the FK protect integrity on write.

## 6. Protecting Relationships with Foreign Keys

If a support ticket must have an assigned staff member, the mapping can be:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "assignee_id", nullable = false)
private StaffMember assignee;
~~~

The database should also enforce this condition:

~~~sql
alter table support_tickets
    alter column assignee_id set not null;

alter table support_tickets
    add constraint fk_ticket_assignee
    foreign key (assignee_id) references staff_members(id);
~~~

ALTER COLUMN syntax varies by database. `NOT NULL` forbids empty relationships; the FK ensures the referenced ID has a target row. These two constraints complement each other.

If the system has legacy data, find orphaned references before adding the FK:

~~~sql
select t.id, t.assignee_id
from support_tickets t
left join staff_members s on s.id = t.assignee_id
where t.assignee_id is not null
  and s.id is null;
~~~

Clean up the data according to business rules before adding the constraint. Avoid using `@NotFound(IGNORE)` to mask data errors; that annotation changes how Hibernate reads the relationship and does not fix invalid FK values in the table.

## 7. Lazy Loading and the JPA Contract

`FetchType.LAZY` is a hint to the provider; `FetchType.EAGER` is a requirement. That means a LAZY mapping does not guarantee the provider will always defer loading.

Common defaults:

| Mapping | Default fetch |
|---|---|
| `@ManyToOne` | `FetchType.EAGER` |
| `@OneToOne` | `FetchType.EAGER` |
| `@OneToMany` | `FetchType.LAZY` |
| `@ManyToMany` | `FetchType.LAZY` |
| `@ElementCollection` | `FetchType.LAZY` |
| `@Basic` | `FetchType.EAGER` |

For ToOne relationships, it is generally best to declare LAZY and choose a fetch plan on queries when needed. The provider can still load eagerly depending on mapping, query, or technical limitations.

### 7.1. Hibernate

Hibernate typically uses proxies for ToOne and persistent collection wrappers for ToMany. Practical limitations:

- Traditional subclass proxies are restricted by final entities or final methods.
- Bytecode enhancement can support lazy attribute loading.
- The inverse side of One-to-One may need an eager query to determine whether the association is null.
- Accessing an uninitialized proxy after the Session closes typically causes `LazyInitializationException`.
- `@NotFound` on ToOne forces Hibernate to load the relationship eagerly, even if LAZY is declared.

Hibernate provides batch fetching to reduce query count when initializing multiple proxies/collections:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Or via a per-entity annotation:

~~~java
@BatchSize(size = 32)
@Entity
public class StaffMember {
    // fields
}
~~~

Batch size must be measured against real workloads. It does not replace fetch plans and does not guarantee every query emits only one SELECT.

### 7.2. EclipseLink

EclipseLink uses indirection. Lazy ToOne in Java SE depends on weaving:

- Dynamic weaving transforms bytecode when classes are loaded.
- Static weaving transforms bytecode prior to runtime.
- If weaving is inactive, ToOne may load eagerly despite a LAZY mapping.

EclipseLink-specific configuration example:

~~~xml
<property name="eclipselink.weaving" value="true"/>
<property name="eclipselink.weaving.lazy" value="true"/>
~~~

This is EclipseLink-specific configuration and does not apply to Hibernate. Verify both build setup and how the JVM is launched; simply adding properties without performing proper weaving is not enough.

### 7.3. Hibernate's @NotFound

For legacy data without physical FKs, Hibernate provides `@NotFound`:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "legacy_assignee_id")
@NotFound(action = NotFoundAction.IGNORE)
private StaffMember assignee;
~~~

- `NotFoundAction.EXCEPTION` reports an error when Hibernate discovers the target row does not exist; modern Hibernate may throw `FetchNotFoundException`.
- `NotFoundAction.IGNORE` treats invalid associations as `null`.

This is a Hibernate-specific extension, not Jakarta Persistence. ToOne relationships with `@NotFound` are loaded eagerly. Only use it when supporting legacy data and you understand the consequences; new schemas should be protected by FKs.

## 8. Keeping Proxies Within Transaction Boundaries

An entity may be returned from a service while an association is still an uninitialized proxy:

~~~java
public SupportTicket findTicket(Long id) {
    return ticketRepository.findById(id).orElseThrow();
}

// Transaction has already closed before the caller runs:
String name =
        findTicket(12L).getAssignee().getDisplayName();
~~~

If `assignee` has not been loaded yet, Hibernate usually throws `LazyInitializationException`. A safe approach is to load the needed data inside the service and return a DTO:

~~~java
public record TicketView(Long id, String assigneeName) {
}

@Transactional(readOnly = true)
public TicketView getView(Long id) {
    SupportTicket ticket =
            ticketRepository.findById(id).orElseThrow();

    return new TicketView(
            ticket.getId(),
            ticket.getAssignee().getDisplayName()
    );
}
~~~

If a query always needs the assignee, use an EntityGraph:

~~~java
@EntityGraph(attributePaths = "assignee")
Optional<SupportTicket> findWithAssigneeById(Long id);
~~~

Or a JPQL fetch join:

~~~java
@Query("""
       select t
       from SupportTicket t
       left join fetch t.assignee
       where t.id = :id
       """)
Optional<SupportTicket> findWithAssignee(@Param("id") Long id);
~~~

DTO projections are suitable if only a few columns are needed. You can disable OSIV so the service must explicitly determine required data before returning a response:

~~~properties
spring.jpa.open-in-view=false
~~~

OSIV can cause serializers to initialize proxies and issue SQL while building JSON, hiding queries from the service layer and causing unintended N+1 issues.

## 9. N+1 and Pagination

Suppose you load multiple tickets and then read each staff member's name:

~~~java
List<SupportTicket> tickets = ticketRepository.findAll();

for (SupportTicket ticket : tickets) {
    System.out.println(ticket.getAssignee().getDisplayName());
}
~~~

If each proxy is initialized individually, there can be one SELECT for the ticket list plus one SELECT for each staff member. This is the N+1 query problem.

How to handle it:

1. EntityGraph if the query always needs the assignee.
2. JOIN FETCH for a specific relationship.
3. DTO projection if only a few fields are needed.
4. Batch fetching if multiple proxies/collections need initialization.
5. Enable SQL logging or Hibernate statistics in tests to count queries.

For pagination, you can declare:

~~~java
Page<SupportTicket> findByStatus(
        TicketStatus status,
        Pageable pageable
);
~~~

Do not fetch-join multiple collections simultaneously in a paginated query without examining how SQL row counts multiply. For large lists, paginate IDs first and then load the needed relationships for that ID batch, or use DTO projections.

## 10. Testing Missing IDs and Proxy Initialization Timing

### 10.1. findById Returns an Empty Optional

~~~java
@DataJpaTest
class StaffRepositoryTest {

    @Autowired
    private StaffRepository staffRepository;

    @Test
    void missingIdReturnsEmpty() {
        assertThat(staffRepository.findById(999999L)).isEmpty();
    }
}
~~~

This is a predictable contract: a nonexistent ID returns an empty Optional.

### 10.2. getReference May Fail When State Is Accessed

~~~java
@Test
void missingReferenceCanFailOnInitialization() {
    assertThatThrownBy(() -> {
        StaffMember reference =
                entityManager.getReference(StaffMember.class, 999999L);

        reference.getDisplayName();
    }).isInstanceOf(EntityNotFoundException.class);
}
~~~

Exact timing and exception types depend on the provider/version. Some providers may detect the error as soon as the reference is obtained. Therefore, run tests on the actual provider in use and do not assume a single exception wrapper is portable.

### 10.3. Checking Load State with PersistenceUnitUtil

~~~java
PersistenceUnitUtil util =
        entityManagerFactory.getPersistenceUnitUtil();

SupportTicket ticket =
        entityManager.find(SupportTicket.class, ticketId);

boolean assigneeLoaded =
        util.isLoaded(ticket, "assignee");
~~~

This API checks whether a property has been loaded. The result reflects the actual mapping and fetch plan; LAZY is a hint, so do not assume it is always false.

## 11. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| getReferenceById returns object but getter fails | Proxy points to a nonexistent row | Use findById when verification is needed |
| Error only surfaces at commit | FK checked at flush/commit | Catch and translate errors at the appropriate transaction boundary |
| Orphaned ID saved | Database lacks FK | Clean up data and add constraint |
| LazyInitializationException | Proxy uninitialized after persistence context closed | Load data inside service or return a DTO |
| LAZY still loads eagerly | Provider is allowed to load eagerly; query/fetch plan requested it | Inspect SQL, provider, and mapping |
| N+1 when iterating list | Each proxy initialized individually | EntityGraph, JOIN FETCH, projection, or batching |
| getClass() does not equal entity class | Runtime object is a proxy subclass | Do not rely on exact class equality |
| Tests behave differently from production | Different provider/version/weaving | Use integration tests with production configuration |

## 12. Selection Checklist

- [ ] ID from a request needing a 404 response: use `findById`.
- [ ] Only need a reference for a trusted ID: consider `getReferenceById`.
- [ ] Do not treat proxy creation as confirmation that the row exists.
- [ ] Have database FKs for relationships requiring integrity.
- [ ] Distinguish proxy initialization errors from constraint violations.
- [ ] Know that LAZY is a hint and EAGER is a requirement.
- [ ] Check provider proxy/weaving limitations.
- [ ] Do not let serializers initialize proxies outside transactions.
- [ ] Choose EntityGraph, JOIN FETCH, or projection per use case.
- [ ] Measure SQL and test against the deployed provider/version.

## 13. References

- [Jakarta Persistence 3.1 Specification](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.pdf) — contract of `EntityManager.getReference` and fetch types.
- [Spring Data JPA — JpaRepository Javadoc](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/JpaRepository.html) — `findById` and `getReferenceById`.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/6.2/userguide/html_single/) — proxies, lazy fetching, `@NotFound`, and batch fetching.
- [EclipseLink Concepts](https://eclipse.dev/eclipselink/documentation/4.0/concepts/concepts.html) — indirection and weaving.
- [EclipseLink JPA Extensions](https://eclipse.dev/eclipselink/documentation/4.0/jpa/extensions/jpa-extensions.html) — lazy weaving properties.

Choose `findById` when the application needs to verify that an entity exists and needs data to make decisions. Choose `getReferenceById` when you only need to establish a relationship using a trusted ID. Always rely on FKs to protect data, understand when the provider initializes proxies, and design fetch plans within transactions rather than letting unexpected errors occur during response serialization.
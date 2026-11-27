# Owner-Based Access Control and Preventing Cross-Record Access

## Objective

Authentication identifies who is calling the API; authorization decides what that caller is allowed to do with each record. For APIs exposed via Spring Data REST, merely requiring login or checking a broad role is not enough: user A must not read, edit, delete, or link to a record owned by user B unless business rules permit it.

A common risk is IDOR/BOLA (Insecure Direct Object Reference / Broken Object Level Authorization): a client changes an ID in the URL, for instance from `/api/orders/42` to `/api/orders/43`, and accesses someone else's record. Unpredictable IDs or UUIDs do not replace server-side permission checks.

## Modeling ownership

Include ownership relationships in the data model and clearly identify which user or tenant each record belongs to. Example:

    @Entity
    public class Order {
        @Id
        @GeneratedValue
        private Long id;

        @ManyToOne(fetch = FetchType.LAZY, optional = false)
        @JoinColumn(name = "owner_id", nullable = false, updatable = false)
        private User owner;

        private String description;

        // getters and business methods
    }

`owner_id` is critical authorization data. If access depends on tenant, store the corresponding tenant association or tenant key and include it in every query. For systems allowing record sharing, model an explicit permissions/sharing table rather than assuming only a single owner may access a record.

Do not accept the owner from client-submitted data. When creating a record, obtain the authenticated user from `SecurityContext` or a `CurrentUser` service and assign the owner on the server. You can use an input DTO without an `ownerId` field; if exposing entities directly, mark the owner property read-only or avoid exporting that association. `updatable = false` locks column updates in JPA, but does not replace permission checks and request-binding controls.

## Authentication and URL authorization

Configure Spring Security so endpoints require an authenticated identity and enable method security for services:

    @Configuration
    @EnableMethodSecurity
    public class SecurityConfiguration {
        @Bean
        SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
            return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/**").authenticated()
                    .anyRequest().permitAll())
                .build();
        }
    }

The URL rule above only requires login for `/api/**`. It does not prove the caller owns the record whose ID appears in the URL. Role checks like `hasRole('USER')` are also insufficient when all users share the same role yet each may only view their own data.

## Filtering records directly in queries

For collections, filter by owner in the database before pagination. Example repository:

    public interface OrderRepository extends JpaRepository<Order, Long> {
        Page<Order> findAllByOwnerId(Long ownerId, Pageable pageable);

        Optional<Order> findByIdAndOwnerId(Long id, Long ownerId);
    }

The service reads the owner ID from the authenticated identity and calls the scoped queries:

    @Service
    public class OrderAccessService {
        private final OrderRepository orders;
        private final CurrentUser currentUser;

        public OrderAccessService(OrderRepository orders,
                                  CurrentUser currentUser) {
            this.orders = orders;
            this.currentUser = currentUser;
        }

        @PreAuthorize("isAuthenticated()")
        public Page<Order> listMine(Pageable pageable) {
            return orders.findAllByOwnerId(
                currentUser.requireUserId(), pageable);
        }

        @PreAuthorize("isAuthenticated()")
        public Order getMine(Long id) {
            return orders.findByIdAndOwnerId(
                    id, currentUser.requireUserId())
                .orElseThrow(() -> new NotFoundException());
        }
    }

`CurrentUser` is an application service that reads the authenticated principal and maps it to an internal user ID. Do not take `ownerId` from a query parameter or request body and pass it straight to the repository.

The `findAllByOwnerId` query ensures filtering happens before `LIMIT/OFFSET`, so pagination metadata accurately reflects the subset of records the user is allowed to see. Avoid loading all records and using `@PostFilter` to strip out others' records: that wastes resources, can skew total page counts, and risks leaking information via metadata.

## Integrating with Spring Data REST

Automatically exported Spring Data REST repositories typically expose collection, item, and association endpoints. Each path type must be protected:

- **Collection GET:** return only records belonging to the current owner/tenant.
- **Item GET:** return only records the caller is permitted to read.
- **POST:** the server assigns the owner from the principal; do not accept a client-specified owner.
- **PUT/PATCH:** verify the persisted record's owner before applying changes; prevent requests from reassigning the owner to the caller.
- **DELETE:** check permissions on the persisted record before deleting.
- **Association PUT/POST/DELETE:** check permissions on both source and target resources, along with sharing or tenant rules.

Spring Data REST repository event handlers such as `@HandleBeforeCreate`, `@HandleBeforeSave`, `@HandleBeforeDelete`, `@HandleBeforeLinkSave`, and `@HandleBeforeLinkDelete` are useful for validating write operations through REST endpoints. Example:

    @Component
    @RepositoryEventHandler(Order.class)
    public class OrderOwnerHandler {
        private final CurrentUser currentUser;
        private final OrderOwnershipLookup ownership;

        public OrderOwnerHandler(CurrentUser currentUser,
                                 OrderOwnershipLookup ownership) {
            this.currentUser = currentUser;
            this.ownership = ownership;
        }

        @HandleBeforeCreate
        public void beforeCreate(Order order) {
            order.setOwner(currentUser.requireUser());
        }

        @HandleBeforeSave
        public void beforeSave(Order incoming) {
            Long storedOwnerId = ownership.requireOwnerId(incoming.getId());
            currentUser.requireOwnerOrAdmin(storedOwnerId);
            if (!storedOwnerId.equals(incoming.getOwner().getId())) {
                throw new AccessDeniedException("Owner cannot be changed.");
            }
        }

        @HandleBeforeDelete
        public void beforeDelete(Order storedOrder) {
            currentUser.requireOwnerOrAdmin(storedOrder.getOwner().getId());
        }
    }

`OrderOwnershipLookup` should read the persisted owner ID via a dedicated query. When validating updates, do not check only `incoming.getOwner()`: the payload may have already altered the owner before the handler ran. Compare against the owner stored in the database and reject ownership transfers outside authorized business flows.

**Important limitation:** REST event handlers do not protect GET requests and do not automatically filter collections. Adding only `@HandleBeforeSave`/`@HandleBeforeDelete` still leaves users able to read others' records or see them in lists. Protect read paths with method security/query scoping or replace automatic endpoints with controlled endpoints.

## When owner-scoping is required across the entire API

If you cannot prove that every automatically exposed collection, item, and association endpoint is scoped to the caller, disable repository exporting and provide controlled controllers/services:

    @RepositoryRestResource(exported = false)
    public interface OrderRepository extends JpaRepository<Order, Long> {
        Page<Order> findAllByOwnerId(Long ownerId, Pageable pageable);
        Optional<Order> findByIdAndOwnerId(Long id, Long ownerId);
    }

The controller calls `OrderAccessService` instead of calling unscoped `findAll()` or `findById()`. Example:

    @RestController
    @RequestMapping("/api/orders")
    public class OrderController {
        private final OrderAccessService access;

        public OrderController(OrderAccessService access) {
            this.access = access;
        }

        @GetMapping
        public Page<Order> list(Pageable pageable) {
            return access.listMine(pageable);
        }

        @GetMapping("/{id}")
        public Order get(@PathVariable Long id) {
            return access.getMine(id);
        }
    }

Apply the same principle to create, update, delete, and associations: the controller receives the request, the service resolves the principal, queries records within scope, and performs business logic inside a transaction. Ensure no other default Spring Data REST route still exposes an unfiltered repository.

If you keep repository exporting enabled, verify specifically how Spring Data REST invokes each repository method in your version. Method security on `findById` can help protect item lookups, but does not automatically turn `findAll(Pageable)` into an owner-scoped query. A separate filtered search method does not protect the collection root if the root still returns global data.

## Protecting associations and preventing cross-linking

Check permissions on both ends of an association. For example, user A owns `Order/42` and tries to attach it to `Customer/99` belonging to tenant B. Checking the order's owner alone is insufficient; the service must verify the customer is also within the scope the user is permitted to link.

Rules may include:

- Source resource belongs to the current user or the user holds an appropriate administrative role.
- Target resource belongs to the same tenant or is explicitly shared with the caller.
- The association type and business state allow linking.
- Never allow assigning a target resource merely because the client knows its URI or ID.
- When unlinking, verify permission to modify the association; do not confuse removing a link with deleting the target entity.

For REST associations, use `@HandleBeforeLinkSave`/`@HandleBeforeLinkDelete` to check REST flows if the repository remains exported. For custom controllers, enforce the same checks in the service. Keep shared rules in the service/domain layer so you do not rely solely on REST events.

## Administrative permissions and sharing

If admins are allowed to view all records, express that branch explicitly in the service/query rather than relaxing checks in multiple places. For instance, the service can choose an owner-scoped query for regular users and a global query only after verifying an administrative role.

If a record can be accessed by multiple users, model an ACL or sharing table (record, user, permission). Read and write queries must check the corresponding permissions such as `READ`, `UPDATE`, `DELETE`, and `LINK`. Do not treat knowing a URL or having a HAL link as proof of authorization.

For multi-tenancy, add the tenant ID to query predicates alongside owner or ACL checks. Every read and write path must be tenant-scoped; do not check tenant only in the UI or at creation time.

## Responses when unauthorized

When an ID does not belong to the caller, the API can return `404 Not Found` to avoid disclosing whether the record exists, or `403 Forbidden` if policy permits disclosing existence. Choose one consistent approach per API and never return owner data, tenant info, or record contents in error responses.

Querying `findByIdAndOwnerId(...).orElseThrow(NotFoundException)` is a common pattern to conceal the existence of out-of-scope records. If the application uses `403`, ensure the response exposes no sensitive fields. For unauthenticated callers, return `401 Unauthorized` per the authentication mechanism.

## Design mistakes to avoid

- Requiring only login or role `USER` and allowing access to any ID.
- Trusting `ownerId`, `tenantId`, or user ID sent in JSON or query parameters.
- Checking permissions only in the UI or relying on unpredictable IDs/UUIDs.
- Using REST events to protect GETs or filter collections; write events do not cover read paths.
- Fetching records globally and then checking or filtering in memory.
- Checking ownership on a request-bound entity without verifying against the persisted owner.
- Allowing owner updates via normal PUT/PATCH requests.
- Checking the source resource while ignoring permissions on the association's target resource.
- Using caches keyed only by record ID when responses depend on user/tenant; cache keys must include permission scope or properly filtered data.

## Verifying with integration tests

Create at least two independent users, A and B, each with their own records. Send HTTP requests through the exact endpoints exposed by the application and verify:

1. User A sees only A's records in the collection; pagination and `totalElements` also count only A's records.
2. User A GETs B's item by changing the ID in the URL; the response is 404 or 403 per policy and contains none of B's data.
3. User A PUTs/PATCHes B's item; the request is denied and the database is unchanged.
4. User A DELETEs B's item; the request is denied and the record remains.
5. User A POSTs a record with B's `ownerId` in the payload; the server ignores or rejects that field and the saved owner is A.
6. User A PUTs/PATCHes attempting to change A's record's owner to B; the request is denied and the owner in the database remains A.
7. User A attaches record A to a target resource belonging to tenant B; the association is denied.
8. User A cannot remove an association they are not authorized to manage.
9. Admins perform global operations strictly according to policy.
10. Unauthenticated requests receive 401; authenticated unauthorized requests receive 403/404 per policy.

Check both status codes and database state after every failed request. Collection tests must confirm no cross-user records appear in the body, embedded links, total element counts, or pagination metadata. If caching is used, run tests after one user reads data to ensure cached responses are not mistakenly served to another user.

## Implementation workflow

1. Identify owner/tenant and sharing rules in the data model.
2. Obtain identity and owner ID from the authenticated principal; never trust client-supplied owner data.
3. Write repository queries filtering by owner/tenant before pagination.
4. Put read, update, delete, and link permission checks in shared services and enable method security.
5. If automatic repository exporting cannot guarantee all read paths are scoped, set `exported = false` and use controlled controllers/services.
6. If still using repository REST, add event handlers for create/save/delete/link while separately protecting item GET and collection GET.
7. Check both source and target resources when changing associations.
8. Keep owner immutable during update requests; use database constraints and transactions for integrity.
9. Write integration tests with at least two users/tenants to test IDOR, owner tampering, and cross-linking.

Owner-based access control must be enforced server-side on every record and every association. Authentication establishes who is calling; owner-scoped queries and authorization decide which data they may read or modify. REST events assist with validating write operations through Spring Data REST, while read paths and collections must be protected separately.

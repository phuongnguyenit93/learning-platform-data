# Interface Batch Mapping

A GraphQL interface describes a shared set of fields provided by multiple object types. For example, an activity management system might have several types of activities such as workshops and book launches. All of them have an identifier, title, and coordinator, while each type also carries its own data.

When a client queries a list of interfaces and selects a shared field like `coordinator`, the server needs to resolve that field for objects belonging to multiple subtypes. If each object loads its coordinator with a separate query, the number of database calls grows with the number of elements, creating an N+1 problem.

Spring for GraphQL supports declaring a single `@BatchMapping` for an interface field. Starting in Spring for GraphQL 1.3, this mapping is automatically expanded into corresponding mappings for each object type implementing the interface. This mechanism applies to both `@SchemaMapping` and `@BatchMapping`. As a result, a single batch resolver can load related data for multiple subtypes in one pass.

This lesson explains how interface batch mapping works, how to implement it, how to override it for a specific subtype, and how to test batching in Spring for GraphQL.

## 1. Interfaces and Implementing Object Types

An interface defines a shared field contract. Object types implementing the interface must provide those fields, and may also add their own fields.

Example schema for activities:

~~~graphql
type Query {
  activities: [Activity!]!
}

interface Activity {
  id: ID!
  title: String!
  coordinator: User!
}

type WorkshopActivity implements Activity {
  id: ID!
  title: String!
  coordinator: User!
  room: String!
}

type BookLaunchActivity implements Activity {
  id: ID!
  title: String!
  coordinator: User!
  bookIsbn: String!
}

type User {
  id: ID!
  name: String!
}
~~~

A query can return a list containing both `WorkshopActivity` and `BookLaunchActivity`:

~~~graphql
query ActivityList {
  activities {
    id
    title
    coordinator {
      id
      name
    }
    ... on WorkshopActivity {
      room
    }
    ... on BookLaunchActivity {
      bookIsbn
    }
  }
}
~~~

The client selects `coordinator` through the `Activity` contract without needing to know the concrete object in advance. At execution time, GraphQL still processes the field on the actual object type of each element. Spring for GraphQL can map a single interface handler into mappings for each object type implementing it.

## 2. The N+1 Problem When Resolving Shared Fields

Suppose the root resolver returns 30 activities:

~~~java
@QueryMapping
public List<Activity> activities() {
    return activityService.findAll();
}
~~~

If each resolution of `Activity.coordinator` makes its own database call:

~~~java
@SchemaMapping
public User coordinator(Activity activity) {
    return userService.findById(activity.coordinatorId());
}
~~~

The server may run one query to fetch the list of activities and 30 more queries to fetch coordinators. This is N+1: one query for the parent set, followed by one query per child element.

The returned result may be correct, but I/O cost scales with the number of activities. When the list is large or the resolver calls a remote service, latency and system load rise significantly.

DataLoader solves this problem by deferring individual loads, collecting keys into a batch, and dispatching results back to the original callers. `@BatchMapping` is the concise syntax for this common pattern in Spring for GraphQL.

## 3. How Does Interface Batch Mapping Work?

When a controller method is mapped to a field of a schema interface, Spring for GraphQL by default replaces that mapping with multiple mappings, one for each object type implementing the interface.

For example:

- `Activity.coordinator` is a shared field on the interface.
- `WorkshopActivity` implements `Activity`.
- `BookLaunchActivity` implements `Activity`.
- One `@BatchMapping` method for `Activity.coordinator` can serve both object types.

Spring registers the corresponding data fetchers on the concrete types. When GraphQL executes the `coordinator` field on concrete objects, the data fetcher passes the source object to DataLoader and the batch resolver receives a group of source objects to load the related data.

Interface mapping support was added in Spring for GraphQL 1.3. If the application uses an older version, check its capabilities; you may need to register mappings for each concrete type or use `BatchLoaderRegistry` directly.

## 4. Building Java Models for Subtypes

Java models can use a shared interface and records implementing it:

~~~java
public interface Activity {

    String id();

    String title();

    String coordinatorId();
}
~~~

~~~java
public record WorkshopActivity(
        String id,
        String title,
        String coordinatorId,
        String room) implements Activity {
}
~~~

~~~java
public record BookLaunchActivity(
        String id,
        String title,
        String coordinatorId,
        String bookIsbn) implements Activity {
}
~~~

Records provide `equals` and `hashCode` based on the record components. This is useful when using source objects as `Map` keys in batch results. If using regular classes, implement stable equality suited for key usage.

The coordinator type:

~~~java
public record User(String id, String name) {
}
~~~

The activity service can return a list containing different implementations under the same declared type `List<Activity>`:

~~~java
@Service
public class ActivityService {

    public List<Activity> findAll() {
        return repository.findActivities();
    }
}
~~~

GraphQL needs to determine the concrete object type when a resolver returns an interface. Configure an appropriate type resolver or use class names matching the GraphQL object type names according to the application's schema inspection conventions. If Java and GraphQL names differ, register explicit mappings through runtime wiring.

## 5. Writing @BatchMapping for an Interface Field

The controller can declare a batch mapping that receives a list of source objects typed with the interface:

~~~java
@Controller
public class ActivityController {

    private final ActivityService activityService;
    private final UserService userService;

    public ActivityController(
            ActivityService activityService,
            UserService userService) {
        this.activityService = activityService;
        this.userService = userService;
    }

    @QueryMapping
    public List<Activity> activities() {
        return activityService.findAll();
    }

    @BatchMapping
    public Map<Activity, User> coordinator(List<Activity> activities) {
        Set<String> coordinatorIds = activities.stream()
                .map(Activity::coordinatorId)
                .collect(Collectors.toSet());

        Map<String, User> usersById =
                userService.findAllByIds(coordinatorIds);

        return activities.stream().collect(Collectors.toMap(
                Function.identity(),
                activity -> Objects.requireNonNull(
                        usersById.get(activity.coordinatorId()),
                        "Coordinator must exist for activity " + activity.id())
        ));
    }
}
~~~

In this example:

1. `@QueryMapping` returns objects belonging to multiple subtypes of `Activity`.
2. `@BatchMapping` is mapped to the `coordinator` field based on the method name.
3. Spring registers a batch loader and a data fetcher using DataLoader for the corresponding field.
4. The method receives the list of source objects, collects unique coordinator IDs, and calls the service once.
5. The result is returned as `Map<Activity, User>`, with each activity as a key and its corresponding coordinator as the value.

The default field name inferred from the method name is `coordinator`. The parent type name is inferred from the element type in `List<Activity>`; here it is the `Activity` interface. You can specify them explicitly if needed:

~~~java
@BatchMapping(typeName = "Activity", field = "coordinator")
public Map<Activity, User> loadCoordinators(List<Activity> activities) {
    // ...
}
~~~

When declaring a mapping on an interface, Spring for GraphQL expands it to the object types implementing the interface. Thus the method does not need to be written separately for each subtype if the data-loading logic is identical.

### Choosing the Right Return Type

`@BatchMapping` supports several common return types:

| Return Type | Rule |
| --- | --- |
| `Map<K, V>` | Maps source objects/keys to loaded values |
| `Mono<Map<K, V>>` | Reactive version of a mapped result |
| `List<V>` or `Collection<V>` | Result list must correspond in order to the source list |
| `Flux<V>` | Result sequence must have the same count and order as the sources |

`Map` is often easier to verify when the batch loader fetches data from a database by a set of IDs and database result ordering is not guaranteed. If using `List` or `Flux`, the method must sort results to match the exact order of the input source list.

When using source objects as Map keys, those objects must have consistent `equals` and `hashCode`. Do not mutate fields participating in equality after an object has been used as a key.

## 6. Overriding the Mapping for a Specific Subtype

Sometimes subtypes have different ways of loading a shared field. For example, a workshop's coordinator is fetched from the HR system, while a book launch's coordinator is fetched from the events system.

You can declare a default mapping for the interface and then override the mapping for a specific subtype:

~~~java
@Controller
public class ActivityController {

    private final UserService userService;
    private final WorkshopService workshopService;

    public ActivityController(
            UserService userService,
            WorkshopService workshopService) {
        this.userService = userService;
        this.workshopService = workshopService;
    }

    @BatchMapping
    public Map<Activity, User> coordinator(List<Activity> activities) {
        Set<String> ids = activities.stream()
                .map(Activity::coordinatorId)
                .collect(Collectors.toSet());

        Map<String, User> users = userService.findAllByIds(ids);
        return activities.stream().collect(Collectors.toMap(
                Function.identity(),
                activity -> Objects.requireNonNull(
                        users.get(activity.coordinatorId()))
        ));
    }

    @BatchMapping(typeName = "WorkshopActivity", field = "coordinator")
    public Map<Activity, User> workshopCoordinators(
            List<WorkshopActivity> activities) {

        Set<String> ids = activities.stream()
                .map(WorkshopActivity::coordinatorId)
                .collect(Collectors.toSet());

        return workshopService.findCoordinators(ids);
    }
}
~~~

The specific mapping for `WorkshopActivity` takes precedence for that subtype; the interface mapping continues serving the remaining subtypes, such as `BookLaunchActivity`. This keeps shared logic intact and isolates only what truly differs.

When overriding, make sure the field name and type name are exact. If a specific mapping duplicates or conflicts with another mapping, the application may encounter a data fetcher registration error during schema initialization.

## 7. When Should You Use BatchLoaderRegistry Directly?

`@BatchMapping` fits straightforward cases: loading a related field based on a list of parent objects. However, a batch mapping method does not accept every parameter that `@SchemaMapping` supports. If loading data depends on field arguments, parent-specific local context, or other complex parameters, using `BatchLoaderRegistry` and `DataLoader` directly is more flexible.

A batch mapping method accepts a list of source objects and may additionally accept `Principal`, `@ContextValue`, `GraphQLContext`, or `BatchLoaderEnvironment`. It does not accept `@Argument` like a standard schema mapping. If you need argument values, let `@SchemaMapping` read the argument and include the data affecting the result in the DataLoader key.

Example schema with a filter field:

~~~graphql
interface Activity {
  id: ID!
  participantCount(includeGuests: Boolean = false): Int!
}

type WorkshopActivity implements Activity {
  id: ID!
  participantCount(includeGuests: Boolean = false): Int!
  room: String!
}

type BookLaunchActivity implements Activity {
  id: ID!
  participantCount(includeGuests: Boolean = false): Int!
  bookIsbn: String!
}
~~~

If the participant count varies with the `includeGuests` argument, a batch loader receiving only the list of parent objects will not know each field call's argument. You can use `@SchemaMapping` to receive `@Argument` and invoke `DataLoader` with a key containing both the activity ID and the filter:

~~~java
public record ParticipantKey(
        String activityId,
        boolean includeGuests) {
}
~~~

~~~java
@Controller
public class ActivityParticipantController {

    @SchemaMapping(typeName = "Activity", field = "participantCount")
    public CompletableFuture<Integer> participantCount(
            Activity activity,
            @Argument boolean includeGuests,
            DataLoader<ParticipantKey, Integer> loader) {

        return loader.load(new ParticipantKey(
                activity.id(),
                includeGuests));
    }
}
~~~

With interface mapping, this method can be expanded to subtypes according to Spring for GraphQL rules. The DataLoader key must include every factor that changes the result; using only the activity ID could cause two requests for the same activity with different `includeGuests` values to mistakenly receive a cached result.

Register a mapped batch loader using `BatchLoaderRegistry`:

~~~java
registry.forTypePair(ParticipantKey.class, Integer.class)
        .registerMappedBatchLoader((keys, environment) ->
                participantService.countByKeys(keys));
~~~

Here the batch loader returns the participant count, so the value type is `Integer` and can be registered directly. If the field needs to return a collection, use a value wrapper compatible with the GraphQL list type and register the DataLoader with the appropriate generic type; avoid using raw `List.class` and suppressing type warnings.

`BatchLoaderRegistry` supports GraphQL context access and context propagation. The Spring Boot starter provides a registry for registering request-scoped DataLoaders. Prefer this mechanism over manually registering ad-hoc DataLoaders if the application needs context propagation and request-scoped lifecycle management.

## 8. Batching Does Not Automatically Mean One SQL Query in All Cases

A batch resolver receives many source objects in a single call, yet the actual number of queries depends on the service and repository implementation.

Good example:

~~~java
Map<String, User> usersById =
        userRepository.findAllById(coordinatorIds).stream()
                .collect(Collectors.toMap(User::id, Function.identity()));
~~~

Example that still creates N+1 inside the batch method:

~~~java
Map<Activity, User> result = new HashMap<>();
for (Activity activity : activities) {
    result.put(activity, userRepository.findById(
            activity.coordinatorId()).orElseThrow());
}
~~~

In the second example, the method is called only once yet still issues one query per activity. Fetch by a set of IDs, use an appropriate join/projection, or call an API supporting bulk lookup.

Batching also has practical limits:

- Databases limit the number of elements in an IN clause; split batches into smaller chunks when needed.
- External services may cap the number of IDs per request.
- Duplicate IDs should be deduplicated to avoid redundant loading.
- Missing keys in results must be handled explicitly, especially when the schema declares a non-null field.
- Overly large batch sizes can increase memory usage and processing time.

`@BatchMapping` supports a `maxBatchSize` attribute to cap the number of parent keys in one batch:

~~~java
@BatchMapping(maxBatchSize = 100)
public Map<Activity, User> coordinator(List<Activity> activities) {
    // Load at most 100 activities in a single batch.
}
~~~

If a list has 250 parent objects, DataLoader can split them into multiple dispatches according to the configured limit. Choose the limit based on the capacity of the database or downstream service and measure with realistic data.

## 9. Nullability and Missing Results in Batches

The example schema declares:

~~~graphql
interface Activity {
  coordinator: User!
}
~~~

The `coordinator` field is non-null. If the batch loader does not find a user for an activity and returns null, GraphQL produces an execution error and applies null propagation according to the schema. If business logic permits an activity without a coordinator, the schema should express that with a nullable field:

~~~graphql
interface Activity {
  coordinator: User
}
~~~

If the field is non-null, the batch loader should detect missing data and handle it according to business rules: report a controlled error, fix data integrity, or use a valid fallback object if the domain allows it. Do not silently assign an unrelated default user.

When using a `Map`, a key absent from the `Map` is generally treated by DataLoader as having no corresponding result. Understand that behavior and make sure it aligns with schema nullability. For a nullable field, null can be a valid result; for a non-null field, null leads to an error.

## 10. Caching and Scope of DataLoader

DataLoaders are typically registered and created per GraphQL request. They can coalesce loads with duplicate keys within a request and cache results to avoid repeated fetching. This cache does not replace an application-wide shared cache or database cache.

Some principles:

- Do not store a request-scoped DataLoader in a singleton field and reuse it across requests.
- Keys must fully represent all inputs affecting the result.
- If data changes during a mutation, consider clearing or priming the relevant keys to avoid reading stale values within the same request.
- Do not use DataLoader's cache as a long-lived data store.
- Evaluate memory footprint if a query could load a very large number of entities.

With interface batch mapping, subtypes sharing a field can go through the expanded mappings. This does not mean every subtype must use the same batch service; you can override the mapping for a specific subtype or use separate keys and loaders when requirements differ.

## 11. Testing Interface Batch Mapping

You should test both the interface query response and that the service is invoked in batch. You can use `@GraphQlTest` with the controller and mock services:

~~~java
@GraphQlTest(ActivityController.class)
class ActivityControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    ActivityService activityService;

    @MockBean
    UserService userService;

    @Test
    void loadsCoordinatorForDifferentActivitySubtypes() {
        Activity workshop = new WorkshopActivity(
                "a-1", "Spring Workshop", "u-1", "Room A");
        Activity launch = new BookLaunchActivity(
                "a-2", "Book Launch", "u-2", "9780000000001");

        given(activityService.findAll())
                .willReturn(List.of(workshop, launch));
        given(userService.findAllByIds(Set.of("u-1", "u-2")))
                .willReturn(Map.of(
                        "u-1", new User("u-1", "An"),
                        "u-2", new User("u-2", "Bình")));

        graphQlTester.document("""
                query {
                    activities {
                        id
                        title
                        coordinator {
                            id
                            name
                        }
                        ... on WorkshopActivity {
                            room
                        }
                        ... on BookLaunchActivity {
                            bookIsbn
                        }
                    }
                }
                """)
                .execute()
                .path("activities[0].coordinator.name")
                .entity(String.class)
                .isEqualTo("An");

        then(userService).should()
                .findAllByIds(Set.of("u-1", "u-2"));
    }
}
~~~

This is an illustrative example; type resolver configuration and mocks must match the actual models. Beyond the response, verify:

- The batch method receives source objects from both subtypes.
- The service bulk lookup is called once for the batch's set of IDs.
- Each coordinator result is attached to the right activity.
- Subtype-specific fields still work via inline fragments.
- An overridden mapping for a subtype takes precedence when explicitly declared.
- Missing coordinator cases obey schema nullability.
- For batches returning `List` or `Flux`, result ordering matches source object ordering.

To verify the actual number of database queries, use integration tests with repositories or datasource spies/metrics. A unit test verifying only that a service bulk method was called once does not prove the database inside the service ran only a single SQL statement.

## 12. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Batch method is not invoked | Field name or type name does not match the schema | Check interface name, field name, and annotation attributes |
| Only one subtype is batched | Mapping points to a concrete type instead of the interface, or another subtype does not implement the interface | Check SDL and the method's parent type |
| Interface mapping does not expand automatically | Older Spring for GraphQL version does not yet support interface mapping | Check version; declare mappings per concrete type or upgrade carefully |
| Two resolvers compete for one field | Interface mapping and subtype mapping accidentally conflict | Override a subtype only when there is a clear need |
| Results attached to wrong parents | Unstable Map key equality or wrong key used | Use immutable keys with proper `equals`/`hashCode` or return an ordered sequence |
| One batch still runs many SQL queries | Service loops queries per parent | Use a bulk query over the set of IDs |
| One parent receives another parent's result | DataLoader key omits a factor affecting the result | Expand the key to include relevant filter/tenant/locale |
| Non-null field produces a null error | Batch result is missing a required value | Check data, nullability, and error rules |
| Batch method cannot receive filter arguments | `@BatchMapping` does not support all method arguments of `@SchemaMapping` | Use `@SchemaMapping` calling `DataLoader` and `BatchLoaderRegistry` |

## 13. Design Principles for Interface Batch Mapping

- Place shared fields on the interface when all subtypes share the same semantics and data contract.
- Use a single `@BatchMapping` on the interface when subtypes can be loaded using the same rule.
- Override the mapping on a concrete type when a subtype has its own data source or business rule.
- Use a `Map` keyed by source object when repository result ordering is unstable; ensure keys have stable `equals`/`hashCode`.
- Use `List`/`Flux` only when result ordering can be guaranteed to strictly match the source list.
- Use `BatchLoaderRegistry` when composite keys, field arguments, or detailed context logic are needed.
- Keep `DataLoader` request-scoped and design keys specific enough to distinguish results.
- Measure actual database queries; the batch annotation does not by itself guarantee a single query.
- Design nullability consistently with real data guarantees.
- Test all subtypes, mapping overrides, and missing-data cases.

## 14. Practice Exercise

Build an API for activity types:

1. Declare an `Activity` interface with `id`, `title`, and `coordinator`.
2. Create `WorkshopActivity` and `BookLaunchActivity` implementing the interface.
3. Create a query returning a list of `Activity` containing both subtypes.
4. Write a `@BatchMapping` for the `coordinator` field on the interface.
5. Use a bulk lookup service to load all users by coordinator ID.
6. Override the mapping for `WorkshopActivity` to load the coordinator from a separate service.
7. Write a `GraphQlTester` test verifying both subtypes receive the right coordinator.
8. Measure the SQL query count before and after batch mapping.
9. Try changing `coordinator: User!` to nullable and verify behavior when a user is missing.

When finished, be able to explain why a mapping on an interface can be expanded by Spring to subtypes, how `DataLoader` batches loads, when a specific mapping needs to be overridden, and why a batch method can still cause N+1 if the underlying service keeps querying per parent.

## 15. References

- [Spring for GraphQL — Annotated Controllers: Interface Batch Mappings](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL 1.4.2 — BatchMapping API](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/data/method/annotation/BatchMapping.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL 1.3 RC1 — Schema Interface Mapping](https://spring.io/blog/2024/04/16/spring-for-graphql-1-3-rc1-released/)

Spring for GraphQL and GraphQL Java versions determine several API details. When upgrading, check the Javadoc for the exact version, especially for interface mapping, controller method signatures, and reactive return types.

# Batch mapping on interfaces

In GraphQL, an interface describes a shared field contract for multiple object types. For example, an activity system might return FooActivity and BarActivity. Both have an identifier and a coordinator, while each type has its own specific data. When a client queries a list of Activities and selects the coordinator field, GraphQL needs to resolve that field for each concrete object.

If the coordinator resolver queries the user separately for each activity, a query fetching many activities can produce multiple data access calls. **Batch mapping on interfaces** allows grouping source objects belonging to multiple implementations of the same interface into a single batch operation. Spring for GraphQL supports this with the **@BatchMapping** annotation: a batch handler declared on an interface field can be applied to each object type implementing the interface.

## Interface fields and implementing object types

Suppose the schema has an Activity interface and two implementations:

~~~graphql
type Query {
  activities: [Activity!]!
}

interface Activity {
  id: ID!
  coordinator: User
}

type FooActivity implements Activity {
  id: ID!
  coordinator: User
  fooCode: String!
}

type BarActivity implements Activity {
  id: ID!
  coordinator: User
  barCategory: String!
}

type User {
  id: ID!
  name: String!
}
~~~

The coordinator field is part of the shared Activity contract. Because FooActivity and BarActivity both implement Activity, both must provide the coordinator field with a compatible output type. Each type can still have its own fields such as fooCode or barCategory.

Clients can query shared fields and use inline fragments for type-specific data:

~~~graphql
query {
  activities {
    id
    coordinator {
      id
      name
    }
    __typename
    ... on FooActivity {
      fooCode
    }
    ... on BarActivity {
      barCategory
    }
  }
}
~~~

The coordinator field is requested for every element, regardless of whether the element is a FooActivity or a BarActivity. This is an ideal case for writing a shared batch mapping on the interface.

## Why must batch mapping on an interface be expanded?

When GraphQL executes a field on an object, the runtime operates on the concrete object type determined for that object. In the schema, the coordinator field is declared on the interface and implemented by the object types. Spring for GraphQL supports interface schema mappings by expanding the mapping to the object types that implement the interface.

With batch mapping, the same mechanism applies: when a batch handler is mapped to an interface field, Spring creates corresponding mappings for each implementing object type. Thus, a method receiving a list of Activities can handle elements from multiple subtypes.

This avoids writing duplicate batch logic separately for FooActivity and BarActivity when both share the same coordinator lookup rule. When a new subtype implements Activity, the shared mapping can apply to that subtype once the schema and type resolution are configured properly.

## Java models for the interface and subtypes

On the Java side, you can model the Activity contract with an interface:

~~~java
public interface Activity {
    String id();
    String coordinatorId();
}

public record FooActivity(
        String id,
        String coordinatorId,
        String fooCode) implements Activity {
}

public record BarActivity(
        String id,
        String coordinatorId,
        String barCategory) implements Activity {
}

public record User(String id, String name) {
}
~~~

The records share the two properties id and coordinatorId while carrying their own fields. The coordinatorId field is a Java model detail used to look up the User; it does not have to appear in the GraphQL schema.

The query resolver can return a list of the interface type:

~~~java
@Controller
public class ActivityController {

    private final ActivityService activityService;

    public ActivityController(ActivityService activityService) {
        this.activityService = activityService;
    }

    @QueryMapping
    public List<Activity> activities() {
        return activityService.findAll();
    }
}
~~~

Because the Query returns an interface, the GraphQL runtime still needs to determine the concrete object type of each Java value, such as FooActivity or BarActivity. Ensure interface type resolution is configured properly. Batch mapping only solves bulk loading of related fields; it does not replace a TypeResolver.

## A shared @BatchMapping for the interface

Spring for GraphQL lets you declare a batch handler on an interface field. For example:

~~~java
@Controller
public class ActivityBatchController {

    private final UserService userService;

    public ActivityBatchController(UserService userService) {
        this.userService = userService;
    }

    @BatchMapping
    public Map<Activity, User> coordinator(List<Activity> activities) {
        Set<String> coordinatorIds = activities.stream()
                .map(Activity::coordinatorId)
                .collect(Collectors.toSet());

        Map<String, User> usersById =
                userService.findByIds(coordinatorIds);

        Map<Activity, User> result = new HashMap<>();
        for (Activity activity : activities) {
            result.put(
                    activity,
                    usersById.get(activity.coordinatorId()));
        }
        return result;
    }
}
~~~

In the example, the method name coordinator defaults to the GraphQL field name. The element type of the List<Activity> parameter tells Spring the mapping belongs to the Activity interface. Spring expands this mapping to the object types implementing Activity, so the batch handler can receive a list containing both FooActivity and BarActivity.

The method collects unique coordinatorIds, calls the service once to load Users, and then builds a map from each source Activity to its corresponding User. The map uses the source object itself as the key and User as the value. With records, equals and hashCode are generated from the record components; if using regular classes, ensure keys have stable equality so the map locates source objects properly.

In the example schema, coordinator is nullable. If an activity has no coordinator or the corresponding user does not exist, the map can hold a null value. If the schema contract changes to coordinator: User!, the service must ensure every activity has a valid User or return an appropriate business error.

## How Spring infers typeName and field

When attributes are omitted in @BatchMapping:

- The default field name is taken from the method name.
- The default type name is inferred from the element type of the List of source objects.
- If the source type is a GraphQL interface, Spring expands the mapping to the object types implementing that interface.

You can declare them explicitly to clarify the mapping:

~~~java
@BatchMapping(typeName = "Activity", field = "coordinator")
public Map<Activity, User> loadCoordinators(List<Activity> activities) {
    return userService.findCoordinators(activities);
}
~~~

Here the Java method name is loadCoordinators while the GraphQL field remains coordinator. typeName explicitly points to the Activity interface. Using explicit names is helpful when the method name differs from the field name or when a controller contains multiple batch handlers.

## Overriding the mapping for a subtype

Normally, one shared batch handler is enough. However, a subtype may require its own data loading rule. For example, FooActivity fetches coordinators from an internal system while other subtypes fetch from the general UserService.

You can declare the shared mapping and override the mapping for a specific subtype:

~~~java
@Controller
public class ActivityBatchController {

    private final UserService userService;
    private final FooCoordinatorService fooCoordinatorService;

    public ActivityBatchController(
            UserService userService,
            FooCoordinatorService fooCoordinatorService) {
        this.userService = userService;
        this.fooCoordinatorService = fooCoordinatorService;
    }

    @BatchMapping
    public Map<Activity, User> coordinator(List<Activity> activities) {
        return userService.findCoordinators(activities);
    }

    @BatchMapping(field = "coordinator")
    public Map<FooActivity, User> fooCoordinators(
            List<FooActivity> activities) {
        return fooCoordinatorService.findFor(activities);
    }
}
~~~

The second mapping is inferred for FooActivity and the coordinator field. It takes over the field for this subtype, while the shared mapping continues to serve the remaining subtypes. This is useful when one implementation has a distinct data source or business rule.

When overriding, verify that only one handler is responsible for a specific type/field pair. Two competing mappings for the same schema coordinates can cause startup errors or ambiguous behavior.

## Return values: Map or ordered sequence

Batch mapping supports two common ways to return results:

**Map from source object to value**

~~~java
@BatchMapping
public Map<Activity, User> coordinator(List<Activity> activities) {
    return userService.findCoordinators(activities);
}
~~~

A Map links each source object directly to its corresponding value. Element order in the map does not matter, but keys must match the source objects. When using object map keys, ensure equals and hashCode are stable.

**Flux ordered to match the source list**

~~~java
@BatchMapping
public Flux<User> coordinator(List<Activity> activities) {
    return userService.findCoordinatorsInOrder(activities);
}
~~~

With Flux, the sequence of values must have the exact same count and order as the input list of source objects. If the input is [activity-1, activity-2, activity-3], the values must sequentially be the coordinators of activity-1, activity-2, and activity-3. Do not return a list directly from the repository if the repository does not guarantee that order.

A Map is usually easier to control when the service queries by a set of IDs and the database returns results in its own order. Flux or an ordered collection works well when the service can produce exactly one value per source object in exact position.

## Batch mapping and DataLoader under the hood

@BatchMapping is a concise shorthand for common DataLoader usage. Spring registers the batch function and creates a data fetcher for the corresponding field. This data fetcher takes the current source object, calls DataLoader, and returns the result to the GraphQL runtime.

With the Activity interface, Spring applies the mapping to each implementing object type. Within the same query, coordinator field calls on FooActivity and BarActivity can be batched via their respective mappings for the batch handler to process.

Overview diagram:

~~~mermaid
flowchart TD
    A["Query activities"] --> B["List<Activity>"]
    B --> C["FooActivity"]
    B --> D["BarActivity"]
    C --> E["coordinator field"]
    D --> F["coordinator field"]
    E --> G["Batch mapping on Activity interface"]
    F --> G
    G --> H["Load Users by ID group"]
    H --> I["Map<Activity, User>"]
    I --> J["GraphQL response"]
~~~

You do not need to create a singleton DataLoader manually. Spring manages the registry and DataLoaders per GraphQL request, ensuring caches are not shared across requests. If you need to share the same loader across multiple resolvers or need finer control over keys, context, and caching, register directly via BatchLoaderRegistry.

## When should you use BatchLoaderRegistry directly?

@BatchMapping fits well when a batch handler only needs the list of source objects and supported context. However, if logic needs to read field arguments or requires per-call data from each parent mapping invocation, using BatchLoaderRegistry directly is often more suitable.

For example, clients may request coordinator by locale:

~~~graphql
interface Activity {
  id: ID!
  coordinator(locale: String): User
}
~~~

If each activity can be called with a different locale argument, a batch handler receiving only List<Activity> cannot represent all combinations of source objects and arguments. You can use @SchemaMapping accepting @Argument and call DataLoader with a composite key:

~~~java
public record CoordinatorKey(String userId, String locale) {
}
~~~

Registering a mapped loader with the composite key:

~~~java
@Configuration
public class CoordinatorLoaderConfiguration {

    public CoordinatorLoaderConfiguration(
            BatchLoaderRegistry registry,
            UserService userService) {

        registry.forTypePair(CoordinatorKey.class, User.class)
                .registerMappedBatchLoader((keys, environment) ->
                        Mono.fromSupplier(() ->
                                userService.findByCoordinatorKeys(keys)));
    }
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Activity", field = "coordinator")
public CompletableFuture<User> coordinator(
        Activity activity,
        @Argument String locale,
        DataLoader<CoordinatorKey, User> coordinatorLoader) {
    return coordinatorLoader.load(
            new CoordinatorKey(activity.coordinatorId(), locale));
}
~~~

In this case, the loader is registered via BatchLoaderRegistry with key CoordinatorKey and value User. Spring expands interface schema mappings to implementing object types, so the resolver can receive Activity source objects of each subtype. Test to confirm that subtype resolvers share the right loader. This approach provides greater control over keys and arguments at the cost of extra configuration.

## Limiting batch size

An overly large batch can generate queries with too many IDs or cause traffic spikes on downstream services. @BatchMapping supports the maxBatchSize attribute to limit the number of source objects per batch:

~~~java
@BatchMapping(maxBatchSize = 100)
public Map<Activity, User> coordinator(List<Activity> activities) {
    return userService.findCoordinators(activities);
}
~~~

If there are 250 activities needing coordinators, Spring can split them into multiple batches not exceeding the configured limit. Choose a size aligned with database query limits, downstream API limits, and memory. maxBatchSize does not replace pagination on the root Query; it only limits the size of each batch loader invocation.

## Security and context in batch mapping

A batch handler can accept additional Spring-supported context parameters such as Principal, GraphQLContext, @ContextValue, or BatchLoaderEnvironment. This is useful when data must be filtered by tenant, user, or access permissions.

Example reading tenant from GraphQL context:

~~~java
@BatchMapping
public Map<Activity, User> coordinator(
        List<Activity> activities,
        @ContextValue("tenantId") String tenantId) {
    return userService.findCoordinators(activities, tenantId);
}
~~~

The tenant must be established at the request/interceptor layer and verified from a trusted principal. Never take tenantId directly from a client-submitted field and use it as an authorization boundary. The batch query must enforce the same access policy for every key in the batch.

If a batch contains source objects belonging to different tenants, the service must filter by the respective tenant per key or group by tenant before querying. Never use a single shared tenant context to return another tenant's data.

## Handling missing data and nullability

When a batch handler returns a Map, a source object without a corresponding key is treated as having no value. If the map contains the key with a null value, the field also receives null. This behavior must match schema nullability.

| Schema field | When User is not found |
| --- | --- |
| coordinator: User | Can return null |
| coordinator: User! | Must return a valid User or raise an error |

If coordinator is non-null but the batch handler returns null, GraphQL generates an execution error and applies null propagation. Determine whether missing data is a normal case or a domain violation. If normal, the schema should allow null; if it is a data error, return an error with clear semantics and log it for investigation.

Do not substitute a missing User with an arbitrary User just to avoid null. Doing so can misassign activity data and create hard-to-detect business bugs.

## Testing batch mapping on interfaces

Tests should include at least two implementations of the interface in the same Query result:

~~~java
graphQlTester.document("""
        query {
            activities {
                id
                coordinator {
                    id
                    name
                }
                __typename
            }
        }
        """)
    .execute()
    .path("activities")
    .entityList(ActivityView.class)
    .hasSize(3);
~~~

Beyond the response, verify the batch service is invoked in bulk rather than once per source object. Important scenarios include:

- A list containing multiple subtypes implementing the interface.
- A subtype overriding the shared batch mapping.
- Multiple source objects sharing the same coordinatorId.
- Repository returning Users in a different order from the source list.
- A source object with no corresponding User.
- A batch exceeding maxBatchSize and splitting into multiple calls.
- Tenant or principal context enforced properly.
- A newly added subtype implementing the interface still inheriting the shared mapping.

You can use Mockito to verify service or repository call counts, and you should also include an integration test with the GraphQL runtime to confirm interface mappings expand properly to concrete object types.

## Common pitfalls

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Batch handler does not run for subtype | Type name or field mapping does not match interface SDL | Check interface name, field, and implementing objects |
| Only one implementation receives results | Mapping registered only for a concrete object type | Declare the batch mapping on the interface field |
| Subtype override does not work | Incorrect type/field coordinates or inferred method name | Specify field explicitly and check inferred type from List element |
| User assigned to wrong Activity | Map key does not match source object or unstable equals/hashCode | Use stable source keys and construct the map properly |
| Flux returns wrong relationships | Value sequence does not match source list order | Reorder values to match source list or return a Map |
| Nullable field produces GraphQL error | Schema declares non-null while batch returns null | Adjust schema or handle missing data per domain rules |
| Batch query is too large | No limit on batch size | Configure maxBatchSize |
| Wrong tenant data returned | Batch handler ignores authorization context | Pass trusted context and filter by tenant |

## Design principles for batch mapping on interfaces

When building batch mappings for interfaces, apply these principles:

1. **Place shared fields on the interface.** Only put fields in the contract that make sense for every implementation.
2. **Use a single shared batch handler when logic is the same.** Spring expands the mapping to each object type implementing the interface.
3. **Override subtypes when rules differ.** Ensure each type/field coordinate has only one active mapping.
4. **Choose Map when explicit matching is needed.** Keys must be the corresponding source objects; ensure stable equals/hashCode.
5. **Choose Flux when order can be preserved.** Values must match the size and order of the source list.
6. **Use BatchLoaderRegistry when custom arguments or keys are needed.** @BatchMapping does not replace all advanced DataLoader scenarios.
7. **Limit batch size.** Choose maxBatchSize according to database and downstream service limits.
8. **Protect data using context.** Enforce tenant and access permissions for each key.
9. **Test multiple implementations.** Verify shared mapping, overrides, missing values, and query counts.

Batch mapping on interfaces allows a shared field to be loaded in bulk across multiple object types implementing the same contract. Spring for GraphQL expands @BatchMapping on an interface to its subtypes while still permitting per-subtype overrides when necessary. By choosing proper source keys, returning a Map or sequence conforming to the contract, and controlling nullability and security context, applications can reduce N+1 while keeping results consistent across a polymorphic system.

## References

- [Spring for GraphQL - Annotated Controllers and Interface Batch Mappings](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - BatchMapping API](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/data/method/annotation/BatchMapping.html)

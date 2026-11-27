# Interface Mapping in Controllers

## Objectives

After this lesson, you will be able to:

- Explain how a GraphQL interface describes shared fields across multiple object types.
- Return a list of interface-implementing types from a Query in Spring for GraphQL.
- Use a single controller method to map an interface field for all implementing types.
- Override a shared mapping for a specific subtype when custom logic is needed.
- Distinguish interface field mapping from concrete type resolution with TypeResolver.
- Use inline fragments and __typename to query data per subtype.
- Consider @BatchMapping when a shared field needs to batch-load related data.

## 1. What Problem Do Interfaces in GraphQL Solve?

An API may return multiple kinds of objects that share a number of fields. For example, an activity management system has several activity types such as workshops, meetings, and training sessions. All have an identifier and a coordinator, yet each type carries additional specific information.

Without interfaces, the schema would repeat shared fields on each object type. GraphQL interfaces allow declaring a shared contract and requiring object types to implement that contract.

For example:

~~~graphql
interface Activity {
  id: ID!
  coordinator: User!
}

type Workshop implements Activity {
  id: ID!
  coordinator: User!
  topic: String!
}

type Meeting implements Activity {
  id: ID!
  coordinator: User!
  room: String!
}

type User {
  id: ID!
  name: String!
}
~~~

In this schema:

- Activity declares two shared fields: id and coordinator.
- Workshop and Meeting must provide the fields required by Activity.
- Workshop additionally has topic.
- Meeting additionally has room.

Interfaces allow clients to query a list of Activity items without knowing each concrete object type in advance. When type-specific data is needed, clients can use inline fragments to request subtype fields.

## 2. Declaring Java Models for Subtypes

On the Java side, you can represent the GraphQL interface with a shared Java interface and implementing classes.

~~~java
public interface Activity {
    String getId();
    String getCoordinatorId();
}

public class Workshop implements Activity {

    private final String id;
    private final String coordinatorId;
    private final String topic;

    public Workshop(
            String id,
            String coordinatorId,
            String topic) {
        this.id = id;
        this.coordinatorId = coordinatorId;
        this.topic = topic;
    }

    @Override
    public String getId() {
        return id;
    }

    @Override
    public String getCoordinatorId() {
        return coordinatorId;
    }

    public String getTopic() {
        return topic;
    }
}

public class Meeting implements Activity {

    private final String id;
    private final String coordinatorId;
    private final String room;

    public Meeting(
            String id,
            String coordinatorId,
            String room) {
        this.id = id;
        this.coordinatorId = coordinatorId;
        this.room = room;
    }

    @Override
    public String getId() {
        return id;
    }

    @Override
    public String getCoordinatorId() {
        return coordinatorId;
    }

    public String getRoom() {
        return room;
    }
}
~~~

The Java interface helps services and controllers handle subtypes through a single abstraction. Concrete classes still retain fields specific to each type.

The service can return a mixed list:

~~~java
public List<Activity> findActivities() {
    return List.of(
            new Workshop("w-01", "u-01", "GraphQL basics"),
            new Meeting("m-01", "u-02", "Room A")
    );
}
~~~

An important point: a Java interface and a GraphQL interface are two separate mechanisms. Having a Java class implement an interface does not automatically tell GraphQL which concrete GraphQL type that object corresponds to. The GraphQL runtime still needs to determine the actual object type when a field returns an interface.

## 3. Queries Returning an Interface in Spring for GraphQL

Declare the Query in SDL:

~~~graphql
type Query {
  activities: [Activity!]!
}
~~~

The controller can return a list typed with the Java interface:

~~~java
@Controller
public class ActivityController {

    private final ActivityService activityService;

    public ActivityController(ActivityService activityService) {
        this.activityService = activityService;
    }

    @QueryMapping
    public List<Activity> activities() {
        return activityService.findActivities();
    }
}
~~~

The activities method is mapped to the Query.activities field. The return value is List<Activity>, where each actual element can be a Workshop or a Meeting.

When GraphQL executes the activities field, the engine needs to know the concrete type of each element to continue resolving the selected fields. That is the responsibility of abstract type resolution, typically configured using a TypeResolver or a default type-inference mechanism matching class names.

## 4. Mapping a Shared Field for All Subtypes

This is a key aspect of interface mapping in annotated controllers.

Suppose the Activity interface has a coordinator field. Every subtype has a coordinatorId and needs to load the corresponding User. Creating one resolver for Workshop and another for Meeting would duplicate logic.

Spring for GraphQL supports mapping a controller method to a field of a schema interface. By default, that mapping is replaced by corresponding mappings for each object type implementing the interface.

Controller:

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
        return activityService.findActivities();
    }

    @SchemaMapping
    public User coordinator(Activity activity) {
        return userService.findById(activity.getCoordinatorId());
    }
}
~~~

Because the source parameter has the Java type Activity and the method name is coordinator, Spring infers the mapping for the coordinator field on the Activity schema interface.

Spring for GraphQL expands this interface mapping into mappings for each object type implementing Activity, such as Workshop.coordinator and Meeting.coordinator. Thus, the same method is invoked for every matching subtype.

You can visualize the flow as follows:

~~~mermaid
flowchart TD
    A[Query activities] --> B[List<Activity>]
    B --> C[Workshop]
    B --> D[Meeting]
    C --> E[Workshop.coordinator]
    D --> F[Meeting.coordinator]
    E --> G[coordinator(Activity)]
    F --> G
    G --> H[UserService]
    H --> I[User]
~~~

This is particularly useful when a shared field has the same meaning and handling across all subtypes. The controller only needs a single method, while the GraphQL runtime registers mappings for the concrete object types.

### When Do You Need to Declare typeName Explicitly?

If the Java interface name does not match the GraphQL interface name, or if you want to avoid relying on inference conventions, you can declare the type name explicitly:

~~~java
@SchemaMapping(typeName = "Activity", field = "coordinator")
public User resolveCoordinator(Activity activity) {
    return userService.findById(activity.getCoordinatorId());
}
~~~

In this example:

- typeName specifies the GraphQL interface as Activity.
- field specifies the target field to map as coordinator.
- The Activity parameter is the source object passed into the method.

The field name can be inferred from the method name if the field attribute is omitted. The type name can be inferred from the source parameter type if the Java type matches the GraphQL interface.

## 5. Overriding a Mapping for a Specific Subtype

There are cases where a shared field requires different handling on one subtype. For example, Workshop fetches its coordinator from the HR service, whereas Meeting uses a coordinator stored in a separate meeting calendar source.

You can declare a general mapping for the interface and a specific mapping for the subtype:

~~~java
@Controller
public class ActivityController {

    private final UserService userService;
    private final MeetingService meetingService;

    public ActivityController(
            UserService userService,
            MeetingService meetingService) {
        this.userService = userService;
        this.meetingService = meetingService;
    }

    @SchemaMapping
    public User coordinator(Activity activity) {
        return userService.findById(activity.getCoordinatorId());
    }

    @SchemaMapping
    public User coordinator(Meeting meeting) {
        return meetingService.findCoordinator(meeting.getId());
    }
}
~~~

The mapping taking Activity applies to subtypes in general, except for subtypes that already have a specific mapping. The mapping taking Meeting is used specifically for Meeting.

This rule allows sharing default behavior and customizing only where truly necessary. When adding a new subtype implementing Activity, the general mapping can still serve that subtype's coordinator field.

Keep field names and return types compatible with the SDL. If a subtype has a completely different representation or the field no longer carries the same business meaning, reconsider the schema design rather than forcing all cases into a shared resolver.

## 6. Querying Interfaces and Inline Fragments

Clients can query shared fields directly on the interface. To retrieve subtype-specific fields, use inline fragments.

For example:

~~~graphql
query ActivityList {
  activities {
    __typename
    id
    coordinator {
      id
      name
    }
    ... on Workshop {
      topic
    }
    ... on Meeting {
      room
    }
  }
}
~~~

In this query:

- id and coordinator are fields declared on the Activity interface.
- __typename returns the concrete GraphQL type name of each element.
- ... on Workshop requests topic only when the element is a Workshop.
- ... on Meeting requests room only when the element is a Meeting.

Illustrative response:

~~~json
{
  "data": {
    "activities": [
      {
        "__typename": "Workshop",
        "id": "w-01",
        "coordinator": {
          "id": "u-01",
          "name": "Lan"
        },
        "topic": "GraphQL basics"
      },
      {
        "__typename": "Meeting",
        "id": "m-01",
        "coordinator": {
          "id": "u-02",
          "name": "Minh"
        },
        "room": "Room A"
      }
    ]
  }
}
~~~

__typename is very useful for clients when rendering UI per subtype, caching data by concrete type, or handling different data branches.

## 7. TypeResolver and Concrete Type Resolution

An interface only describes the fields supported by all implementing object types. When a resolver returns a Java object, GraphQL still needs to determine whether that object is a Workshop or a Meeting.

If Java class names and GraphQL object type names match Spring for GraphQL's default inference conventions, ClassNameTypeResolver can determine the concrete type. If names do not correspond, or the application uses complex Java object hierarchies, declare an explicit TypeResolver.

For example:

~~~java
@Bean
RuntimeWiringConfigurer activityTypeResolver() {
    return wiringBuilder -> wiringBuilder.type(
            "Activity",
            typeBuilder -> typeBuilder.typeResolver(environment -> {
                Object source = environment.getObject();

                if (source instanceof Workshop) {
                    return environment.getSchema()
                            .getObjectType("Workshop");
                }

                if (source instanceof Meeting) {
                    return environment.getSchema()
                            .getObjectType("Meeting");
                }

                throw new IllegalStateException(
                        "Unsupported Activity type: "
                                + source.getClass().getName());
            })
    );
}
~~~

TypeResolver is solely responsible for selecting the concrete GraphQL object type. It does not load the coordinator field and does not replace @SchemaMapping methods.

Distinguish between the roles:

| Component | Responsibility |
|---|---|
| TypeResolver | Determines which concrete GraphQL type the current Java object belongs to |
| @SchemaMapping | Fetches the value for a field on an object type |
| @QueryMapping | Fetches data for a field on Query |
| @BatchMapping | Batch-loads related data for multiple source objects |

If TypeResolver returns the wrong object type, specific fields in inline fragments may not execute as expected. If TypeResolver is correct but a mapping is missing for a field that must be loaded from a separate source, that field may still return null or lack expected data.

## 8. Using @BatchMapping for Shared Interface Fields

The coordinator field in the previous example can cause an N+1 issue if each Activity calls UserService individually. When the list has many activities, the coordinator resolver may be called once per element.

Spring for GraphQL supports interface batch mapping. Just like interface schema mapping, a @BatchMapping method bound to an interface field is expanded into mappings for each object type implementing the interface.

For example:

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
        return activityService.findActivities();
    }

    @BatchMapping
    public Mono<Map<Activity, User>> coordinator(
            List<Activity> activities) {

        List<String> userIds = activities.stream()
                .map(Activity::getCoordinatorId)
                .distinct()
                .toList();

        return userService.findAllByIds(userIds)
                .collectMap(
                        User::getId,
                        Function.identity()
                )
                .map(usersById -> {
                    Map<Activity, User> result = new HashMap<>();

                    for (Activity activity : activities) {
                        User user = usersById.get(
                                activity.getCoordinatorId());
                        result.put(activity, user);
                    }

                    return result;
                });
    }
}
~~~

The method receives a list of source objects and returns a map from each Activity to the corresponding User. Spring registers the batch loader and DataFetcher for the coordinator field.

This example assumes UserService.findAllByIds returns Flux<User> and every Activity has a matching coordinator. Because the SDL declares coordinator as User!, if a User could be missing, handle that case in business logic or change the field to nullable.

When using source objects as Map keys, those objects need stable equals and hashCode implementations to serve as unique keys. If the model lacks suitable equality, consider another batching approach based on identifier keys or using BatchLoaderRegistry and DataLoader explicitly.

Another option is returning Flux<User>, but the order of returned elements must exactly match the order of the input source object list. If ordering cannot be guaranteed, use a Map to link results to source objects unambiguously.

Not every interface field needs batch mapping. If the data is already present on the source object or only requires a lightweight calculation, PropertyDataFetcher or a simple @SchemaMapping may suffice. Only use batching when the field must load related data for many parent objects and needs to reduce data-source calls.

## 9. Testing Interface Mapping

Tests should verify shared mappings, overridden mappings, and concrete type resolution.

Example with GraphQlTester:

~~~java
@Test
void shouldResolveCommonAndSubtypeFields() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                activities {
                    __typename
                    id
                    coordinator {
                        name
                    }
                    ... on Workshop {
                        topic
                    }
                    ... on Meeting {
                        room
                    }
                }
            }
            """)
            .execute();

    response.path("activities[0].__typename")
            .entity(String.class)
            .isEqualTo("Workshop");

    response.path("activities[0].coordinator.name")
            .entity(String.class)
            .isEqualTo("Lan");

    response.path("activities[0].topic")
            .entity(String.class)
            .isEqualTo("GraphQL basics");

    response.path("activities[1].__typename")
            .entity(String.class)
            .isEqualTo("Meeting");

    response.path("activities[1].room")
            .entity(String.class)
            .isEqualTo("Room A");
}
~~~

Scenarios to test:

1. Query returns multiple subtypes within the same interface list.
2. Shared fields like id and coordinator resolve for all subtypes.
3. Inline fragments return only fields belonging to the corresponding subtype.
4. __typename reflects the exact concrete GraphQL type.
5. The shared mapping is used for subtypes without a custom mapping.
6. The specific mapping overrides the shared mapping for the intended subtype.
7. TypeResolver rejects or explicitly handles unsupported Java objects.
8. Batch mapping returns the right result for each source object, including when a related record is missing.

Beyond resolver tests, include integration tests using the actual SDL schema. This helps catch cases where Java models look right, yet the GraphQL schema does not declare the field, a subtype does not implement the interface, or the type resolver fails to locate the object type.

## 10. Common Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Shared field does not run on subtype | Interface mapping was not detected or type name does not match | Check the source argument and typeName |
| Specific field does not appear | Client did not use an inline fragment or SDL does not declare the field | Check the fragment and object type |
| Abstract type cannot be resolved | TypeResolver fails to determine the concrete type | Check the mapping between Java class and GraphQL object type |
| Subtype uses the wrong resolver | Specific mapping was not declared or type does not match | Declare @SchemaMapping for the subtype source |
| Multiple calls to UserService | Field mapping queries per parent object | Use @BatchMapping or DataLoader |
| Batch result attached to wrong parent | Unstable Map keys or wrong Flux order | Use stable key equality or guarantee ordering |
| Code duplicated across shared field | Each subtype declares the same logic individually | Move mapping to the interface if semantics truly match |

## 11. Design Principles for Interface Mapping

When designing controllers for GraphQL interfaces, keep in mind:

- Place fields with the same business meaning on the interface.
- Use a Java interface or suitable abstraction so the controller accepts a common source object.
- Create one @SchemaMapping for a shared field when all subtypes share the same logic.
- Create subtype-specific mappings when distinct behavior is required.
- Ensure GraphQL determines the concrete type via TypeResolver or default mechanisms.
- Use inline fragments to query subtype-specific fields.
- Use __typename when clients need to distinguish subtypes.
- Consider @BatchMapping for shared fields that need to batch-load related data.
- Test scenarios where multiple subtypes appear together in a single response.

Do not place a field on an interface merely because subtypes happen to share the same field name. Shared fields should share the same semantics and contract. If two subtypes have significantly different data rules, separate mappings are usually clearer and safer.

## Conclusion

Spring for GraphQL supports mapping GraphQL interface fields directly in annotated controllers. A @SchemaMapping method taking a Java interface source can be expanded into mappings for each object type implementing the interface. When needed, a controller can declare a specific mapping for a subtype to override the shared behavior.

Combining interface mapping with TypeResolver, inline fragments, and __typename enables an API to return multiple object types through a unified contract. For shared fields that need to load related data, @BatchMapping also batches retrieval and reduces N+1 queries. Designing the right boundary between shared and specific fields keeps the schema easy to extend and controllers easy to maintain.

## References

- [Spring for GraphQL — Annotated Controllers, Interface Schema Mappings](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Batch Loading, Interface Batch Mappings](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.batch-mapping)
- [Spring for GraphQL — Schema Mapping Annotation API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/SchemaMapping.html)
- [GraphQL Specification — Interfaces](https://spec.graphql.org/October2021/#sec-Interfaces)

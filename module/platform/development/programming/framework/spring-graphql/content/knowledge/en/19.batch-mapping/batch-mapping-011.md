# Batch loading with arguments in Spring for GraphQL

In GraphQL, the same field can be invoked multiple times with different arguments within a single operation. When that field needs to load data in batches, the server must preserve both pieces of information: which parent object is being resolved and which arguments the client passed for that specific call.

`@BatchMapping` is a concise way to batch load nested fields, yet its method cannot accept `@Argument` like a standard `@SchemaMapping`. When arguments affect the data to be loaded, use `@SchemaMapping` combined with a `DataLoader` registered through `BatchLoaderRegistry`. You can include the arguments in the DataLoader key so the cache distinguishes different requests, or load a broader dataset and filter inside the resolver depending on data characteristics.

## 1. Why must batch loading care about arguments?

Suppose each person has a list of friends and the client can filter that list by favorite beverage:

```graphql
input FriendsFilter {
    favoriteBeverage: String
}

type Query {
    me: Person
    person(id: ID!): Person
    people: [Person!]!
}

type Person {
    id: ID!
    name: String!
    favoriteBeverage: String
    friends(filter: FriendsFilter): [Person!]!
}
```

A client can request the same field with different filters:

```graphql
query {
    me {
        friends(filter: { favoriteBeverage: "tea" }) {
            id
            name
        }
    }
    people {
        id
        friends(filter: { favoriteBeverage: "coffee" }) {
            id
            name
        }
    }
}
```

The `Person.friends` resolver must know both the parent `Person` and the `filter`. If batching only by `personId`, two `friends` calls on the same person with different filters could be treated as the same load. The cached result would no longer match each field's arguments.

This is the core point: **an argument is part of the data request whenever it alters the field result**. When batching, keys and caching strategies must reflect those factors.

## 2. Limitations of `@BatchMapping`

`@BatchMapping` accepts a list of source/parent objects and returns batch-loaded results. Simple example:

```java
@Controller
public class BookController {

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        // Load authors for all books in one batch.
    }
}
```

Spring for GraphQL automatically registers the batch loader and data fetcher for the `Book.author` field. For straightforward cases, this reduces boilerplate compared to registering a `DataLoader` manually and writing a `@SchemaMapping` just to call `loader.load(...)`.

However, a `@BatchMapping` method only supports parameters defined by the batch contract, such as:

| Parameter | Meaning |
| --- | --- |
| `List<K>` | The source/parent objects requiring field resolution. |
| `Principal` | Current principal if provided by Spring Security. |
| `@ContextValue` | Value from `GraphQLContext` of the batch environment. |
| `GraphQLContext` | Shared context of the GraphQL execution. |
| `BatchLoaderEnvironment` | Context and metadata of the batch dispatch. |

A `@BatchMapping` method does not support `@Argument` to obtain per-field arguments. The reason is that the batch loader operates at the DataLoader layer: it receives keys and the batch environment, without a separate `DataFetchingEnvironment` for each field call. A single batch can combine multiple parents and multiple field calls with different arguments.

Therefore, if a field depends only on the parent object and shared request context, `@BatchMapping` is usually appropriate. If the field depends on arguments such as `filter`, `sort`, `first`, `after`, or display mode, design a DataLoader key that includes those factors or choose a load-then-filter strategy.

When `@BatchMapping` returns `Map<K,V>` with parent objects as keys, the parent type must have stable `equals` and `hashCode` so the map matches each source accurately. If returning a positional `Flux<V>` or `List<V>`, results must have the exact same size and order as the incoming parent list.

## 3. Approach 1: Use `@SchemaMapping` and filter after DataLoader loads

The first strategy has DataLoader load all related entities by ID, and then `@SchemaMapping` applies arguments to filter the results.

### 3.1. Registering DataLoader by ID

```java
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class PersonDataLoaderConfiguration {

    public PersonDataLoaderConfiguration(
            BatchLoaderRegistry registry,
            PersonService personService) {

        registry.forTypePair(Integer.class, Person.class)
                .registerMappedBatchLoader((personIds, environment) ->
                        personService.findByIds(personIds)
                                .collectMap(Person::id));
    }
}
```

`findByIds` accepts a set of IDs and returns `Flux<Person>`. `collectMap(Person::id)` produces `Mono<Map<Integer, Person>>`, fitting a mapped batch loader. Because the loader returns results by key, there is no need to sort the list to match input order.

### 3.2. Receiving arguments in `@SchemaMapping`

```java
import java.util.Objects;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class FriendsController {

    @SchemaMapping(typeName = "Person", field = "friends")
    public CompletableFuture<List<Person>> friends(
            Person person,
            @Argument("filter") FriendsFilter filter,
            DataLoader<Integer, Person> personLoader) {

        return personLoader.loadMany(person.friendIds())
                .thenApply(friends -> filter == null
                        ? friends.stream().filter(Objects::nonNull).toList()
                        : friends.stream()
                                .filter(Objects::nonNull)
                                .filter(filter::matches)
                                .toList());
    }
}
```

Input record:

```java
public record FriendsFilter(String favoriteBeverage) {

    public boolean matches(Person person) {
        return favoriteBeverage == null
                || favoriteBeverage.equals(person.favoriteBeverage());
    }
}
```

Here:

- `Person person` is the parent source object.
- `@Argument("filter")` is the argument of the `friends` field.
- `DataLoader<Integer, Person>` loads friends by ID and caches entities by ID within the request.
- `thenApply` filters the loaded list according to the current field call's filter.

### 3.3. When should you filter after loading?

This strategy fits when the related set is relatively small or common filters share a lot of overlapping data. For instance, a person has a few dozen friends and clients may query multiple different filters in the same operation. Loading each person once and filtering in the resolver lets you reuse the ID-based cache.

Advantages:

- Simple DataLoader key, just the entity ID.
- An entity can be reused across multiple filters within the same request.
- Batch queries depend little on the number of argument combinations.
- Easy to implement if the related dataset is small and already bounded.

Limitations:

- May load many entities that the client does not need.
- Consumes more memory when a parent has many relationships.
- Filtering happens after data enters the application, failing to leverage database indexes or query planners.
- Unsuitable when each parent has thousands of relationships or filters are highly selective.

## 4. Approach 2: Put parent and arguments into a composite key

If the filter changes the dataset to load and loading all relationships is too expensive, create a key combining the parent and the arguments.

```java
public record FriendsFilterKey(
        Integer personId,
        FriendsFilter filter) {

    public FriendsFilterKey {
        // In this API, omitting the filter and passing an empty filter have the same meaning.
        filter = filter == null ? new FriendsFilter(null) : filter;
    }
}
```

Normalizing `null` to an empty filter allows an omitted argument and `{}` to produce the same cache key if they share the same business meaning. If the API distinguishes the two cases, omit this normalization step.

Java records automatically generate `equals` and `hashCode`, so two keys with the same `personId` and filter values are treated as equal. `FriendsFilter` itself should also be an immutable type with stable `equals`/`hashCode`, such as a record.

### 4.1. Registering a batch loader with a composite key

The example below uses `Person[]` as the DataLoader result type to avoid generic type ambiguity caused by Java type erasure. GraphQL Java can resolve an array as a list field.

```java
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class FilteredFriendsBatchLoader {

    public FilteredFriendsBatchLoader(
            BatchLoaderRegistry registry,
            FriendsQueryService friendsQueryService) {

        registry.forTypePair(FriendsFilterKey.class, Person[].class)
                .registerMappedBatchLoader((keys, environment) ->
                        friendsQueryService.findByKeys(keys)
                                .map(results -> results.entrySet().stream()
                                        .collect(Collectors.toMap(
                                                Map.Entry::getKey,
                                                entry -> entry.getValue()
                                                        .toArray(Person[]::new)))));
    }
}
```

`FriendsQueryService.findByKeys` is an application service accepting a set of `FriendsFilterKey`s and returning `Mono<Map<FriendsFilterKey, List<Person>>>`. It must return an entry for every requested key, even when the result list is empty. You can adapt the service's return type to fit your actual data model.

If the query needs a tenant or principal, the batch loader can read `GraphQLContext` via `BatchLoaderEnvironment` and pass the authenticated value to the service. Never take a tenant from a client-sent filter and treat it as an authorization boundary.

### 4.2. Resolver passing arguments into the DataLoader key

```java
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class FriendsController {

    @SchemaMapping(typeName = "Person", field = "friends")
    public CompletableFuture<Person[]> friends(
            Person person,
            @Argument("filter") FriendsFilter filter,
            DataLoader<FriendsFilterKey, Person[]> friendsLoader) {

        FriendsFilterKey key = new FriendsFilterKey(person.id(), filter);
        return friendsLoader.load(key);
    }
}
```

DataLoader now caches by both parent ID and filter. The same person with `tea` and `coffee` filters generates two distinct keys, preventing wrong cache reuse. Two calls for the same person with the same filter can share the cached result within the request.

### 4.3. Structuring batch queries in the service

The service can group keys by filter and query multiple parents simultaneously:

```java
public Mono<Map<FriendsFilterKey, List<Person>>> findByKeys(
        Set<FriendsFilterKey> keys) {

    // Group keys by filter to reuse a single query across multiple personIds.
    Map<FriendsFilter, Set<Integer>> personIdsByFilter = keys.stream()
            .collect(Collectors.groupingBy(
                    FriendsFilterKey::filter,
                    Collectors.mapping(
                            FriendsFilterKey::personId,
                            Collectors.toSet())));

    return repository.findFriendsGroupedByFilter(personIdsByFilter)
            .collectMap(FriendQueryResult::key, FriendQueryResult::friends)
            .map(found -> keys.stream().collect(Collectors.toMap(
                    key -> key,
                    key -> found.getOrDefault(key, List.of()))));
}
```

`findFriendsGroupedByFilter` represents an application-specific repository query. The key point is that the service must produce results for all keys, using `List.of()` for keys with no matching friends. If a key is completely omitted from the mapped result, DataLoader may return null for that key while the SDL may require a non-null list.

## 5. Comparing the two strategies

| Criterion | Load all then filter | Composite key with parent + filter |
| --- | --- | --- |
| DataLoader key | Entity ID only | Parent ID and arguments |
| Caching | Reuses entities across filters | Cached separately per argument combination |
| Data volume loaded | Can be larger than needed | Can load only the exact data needed |
| Query count | Often fewer queries when data is heavily shared | May increase when many different filters are used |
| Memory | Can be high from retaining unreturned entities | Less excess data, though entities may repeat across keys |
| Best suited for | Small relationship sets, heavily shared filters | Large sets, selective filters, arguments changing result sets |

Neither strategy is universally better. Measure parent count, average relationship count, filter overlap, batch size, and query cost before choosing.

## 6. Why can't you just add `@Argument` to `@BatchMapping`?

A `@BatchMapping` is invoked when DataLoader dispatches a group of parent keys. If the same `friends` field appears with different filters, the batch loader needs to know which filter belongs to which parent. A single `@Argument` parameter cannot express that relationship when a batch combines multiple calls.

Example query:

```graphql
query {
    personA: person(id: "1") {
        friends(filter: { favoriteBeverage: "tea" }) { name }
    }
    personB: person(id: "2") {
        friends(filter: { favoriteBeverage: "coffee" }) { name }
    }
}
```

The batch loader can receive parents from multiple field invocations in the same request. It needs a corresponding key or metadata for each invocation. `@BatchMapping` has no `@Argument` parameter to supply that information; `BatchLoaderRegistry` with `DataLoader` lets resolvers construct the right key before loading.

`@BatchMapping` can still receive `GraphQLContext` or `@ContextValue` because those represent shared execution/batch metadata. Distinguish clearly:

- Arguments are per-field-call inputs, such as `filter`, `first`, `sort`.
- Context is shared metadata per request or execution, such as authenticated tenant, principal, and locale.

## 7. Arguments, context, and keys serve different roles

| Component | Example | Role in batching |
| --- | --- | --- |
| Parent key | `personId` | Identifies the parent object whose field is being resolved. |
| Field argument | `FriendsFilter`, `first`, `sort` | Changes the dataset or ordering to return. |
| GraphQL context | `tenantId`, principal, locale | Supplies shared metadata for the execution/batch. |
| DataLoader key | `FriendsFilterKey(personId, filter)` | Identifies a separately cacheable result. |

If the tenant is constant across the whole request, you typically do not need to include the tenant in the composite key because DataLoader is created per request. However, if a loader or cache is shared across multiple tenants, the tenant must be partitioned in the key/cache or an equivalent isolation mechanism.

## 8. How arguments affect DataLoader caching

DataLoader caches by key within request scope by default. If a resolver only calls `loader.load(personId)`, two calls for the same person with different filters will share the same key and risk receiving the same result.

Incorrect caching model example:

```java
// Insufficient if results depend on the filter.
return friendsLoader.load(person.id());
```

When the filter affects the data, the key must include the filter or the resolver must filter after loading:

```java
// Key includes every factor that changes the result.
return friendsLoader.load(new FriendsFilterKey(person.id(), filter));
```

Rules to remember:

- Use immutable keys with stable `equals` and `hashCode`.
- Normalize arguments before building the key if different representations share the same business meaning.
- If `null` and an empty filter mean different things, keep them distinct in the key.
- If SDL defaults make two requests semantically identical, normalize them to avoid unnecessary cache key fragmentation.
- Never use mutable objects as keys, because changing fields after inserting into the cache can break hash lookups.

## 9. Batch loading with pagination, sorting, and limits

Arguments are not limited to filters. Relational fields frequently have pagination or sorting:

```graphql
type Person {
    id: ID!
    posts(first: Int = 20, after: String, sort: PostSort): [Post!]!
}
```

If `first`, `after`, or `sort` affect the result, they must also be accounted for in the batch/cache strategy. For example, a key could be:

```java
public record PostsKey(
        Integer personId,
        int first,
        String after,
        PostSort sort) {
}
```

When batching multiple parents, do not apply a single `LIMIT 20` to the entire query if the requirement is up to 20 posts per person. Limit per parent instead, for example using a window function `ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY created_at DESC)` and filtering `row_number <= first`. With cursors, the query must apply the post-cursor condition per parent.

If pagination uses opaque cursors, decode/validate cursors at the appropriate layer before constructing keys. Do not use unnormalized raw cursors if different cursor strings represent the same position and fragment the cache needlessly.

## 10. Limiting batch size and handling large key sets

Batch loading reduces service/database calls, yet an overly large batch can produce huge SQL queries, excessive bind parameters, or high memory usage. `@BatchMapping` has a `maxBatchSize` attribute to limit the number of source keys per batch:

```java
@BatchMapping(typeName = "Book", field = "author", maxBatchSize = 100)
public Mono<Map<Book, Author>> author(
        List<Book> books,
        @ContextValue("tenantId") String tenantId) {
    return authorService.findForBooks(tenantId, books);
}
```

This example shows `@BatchMapping` can still receive shared context via `@ContextValue`, even though it cannot accept per-field `@Argument`. `maxBatchSize` has been available since Spring for GraphQL 1.1.0. When using `BatchLoaderRegistry`, configure `DataLoaderOptions` or the batch loader in the manner supported by your library version to cap batch size. Splitting batches does not replace pagination in the GraphQL schema; it only limits keys per dispatch.

With composite keys, batch size is counted by the number of parent/argument combinations, not just parent objects. One parent can appear multiple times with different filters and generate multiple keys.

## 11. Handling keys with no results, nulls, and errors

A batch loader must return results conforming to the schema contract:

- For a `[Person!]!` field, having no matching friends should return an empty list, not null.
- For a nullable `[Person!]` field, returning null is allowed if null carries distinct business meaning; distinguish it clearly from an empty list.
- Never emit null elements if elements are declared Non-Null.
- If a key has no data, a mapped loader should return the appropriate value, such as an empty list or null per the schema.
- Batch query errors should be converted into GraphQL errors according to application policy, rather than silently returning unfiltered data.

If the batch loader returns `Map<K,V>`, the map needs results for every key being processed. If using a positional `Flux<V>` or `List<V>`, element count and order must match the input key list exactly.

## 12. Security when arguments are used to filter data

Arguments can carry filter criteria, but they are never proof of access permissions. For instance, client-sent `tenantId`, `ownerId`, or `includePrivate` must never automatically be treated as a valid data scope.

Principles:

1. Authenticate the principal before executing fields.
2. Obtain the tenant/organization from server-verified context.
3. Combine authorization conditions with client-sent filters in the repository/service.
4. Do not load another tenant's data and filter in Java if you can restrict it directly in the query.
5. Include every factor affecting the result in the cache key or ensure DataLoader is request-scoped.
6. Test two users/tenants with the same parent ID and identical arguments to confirm there is no cache leakage.

For example, a batch loader can read the tenant from `BatchLoaderEnvironment`:

```java
registry.forTypePair(FriendsFilterKey.class, Person[].class)
        .registerMappedBatchLoader((keys, environment) -> {
            GraphQLContext context = (GraphQLContext) environment.getContext();
            String tenantId = context.get("tenantId");
            return friendsQueryService.findByTenantAndKeys(tenantId, keys)
                    .map(this::toArrayMap);
        });
```

`tenantId` must be populated into `GraphQLContext` by the authentication/authorization layer. If a required context value is missing, reject the request rather than querying without tenant restrictions.

## 13. Testing batch loading with arguments

Tests must prove both the returned data and cache key correctness. A test that only checks query count reduction is insufficient if different filters end up returning the same list.

Example GraphQL document calling the same field with two different filters:

```graphql
query {
    person(id: "1") {
        teaFriends: friends(filter: { favoriteBeverage: "tea" }) {
            name
        }
        coffeeFriends: friends(filter: { favoriteBeverage: "coffee" }) {
            name
        }
    }
}
```

Example test with `GraphQlTester`:

```java
@Test
void sameParentCanBeLoadedWithDifferentFilters() {
    var response = graphQlTester.document("""
            query {
                person(id: "1") {
                    teaFriends: friends(filter: { favoriteBeverage: "tea" }) {
                        name
                    }
                    coffeeFriends: friends(filter: { favoriteBeverage: "coffee" }) {
                        name
                    }
                }
            }
            """)
        .execute();

    response.path("person.teaFriends[0].name")
        .entity(String.class)
        .isEqualTo("An");

    response.path("person.coffeeFriends[0].name")
        .entity(String.class)
        .isEqualTo("Binh");
}
```

The test assumes the fixture has a friend named `An` who likes tea and a friend named `Binh` who likes coffee. You should also test omitted filter, null filter, empty filter, two different parents, repeated identical keys, empty results, and batches split due to `maxBatchSize`. Verify repository call counts to ensure keys are batched.

## 14. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Cannot bind `@Argument` in `@BatchMapping` | `@BatchMapping` does not support field arguments | Use `@SchemaMapping` with `DataLoader` and `@Argument`. |
| Same parent with different filters receives same result | DataLoader key contains only the parent ID | Filter after loading or include the filter in a composite key. |
| Batch loader loads too much data | Loading all relationships then filtering even for large datasets | Use a composite key and filter inside the batch query. |
| Batch loader returns wrong order | Using positional `List`/`Flux` without preserving key order | Use a mapped loader or order results to match exact key order. |
| DataLoader cache misses | Key object lacks stable `equals`/`hashCode` | Use a record or immutable key class. |
| Same filter creates multiple cache keys | Argument values are not normalized | Normalize defaults, sorting, and filters before creating the key. |
| Non-Null field errors when no results exist | Batch loader returns null instead of an empty list | Return values matching SDL nullability. |
| Data mixed across tenants | Cache or key is not isolated by tenant | Use request-scoped DataLoaders and verified context; check cache scope. |

## 15. Checklist for designing batch loading with arguments

1. Identify which arguments actually change the result set or sorting.
2. Use `@BatchMapping` for fields depending only on parent keys and shared request context.
3. When field arguments are needed, use `@SchemaMapping` to read `@Argument`.
4. Choose load-all-then-filter if the dataset is small with high reuse potential.
5. Choose a composite key of parent ID and arguments when loading the exact requested subset.
6. Use immutable keys with stable `equals`/`hashCode`.
7. Normalize arguments/defaults before creating keys.
8. Put tenant/principal in verified context and filter data in the service/repository.
9. Maintain the batch loader's count, order, nullability, and empty-result contracts.
10. Limit batch size and per-parent pagination when data volumes are large.
11. Test the same parent with multiple arguments in the same GraphQL operation.
12. Measure query counts, loaded data volume, and cache hit rates to choose the right strategy.

Batch loading with arguments must preserve the exact relationship between parent objects and individual field calls. `@BatchMapping` suits simple cases where a field depends only on parents and shared context. When arguments alter the result, `@SchemaMapping` combined with `DataLoader` enables filtering after loading or using a composite key to cache each parent/argument combination. Choosing a strategy based on data size, overlap, and security requirements reduces N+1 while returning accurate results for every field invocation.

References: [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.batch-mapping) and [Spring for GraphQL — Batch Loading Recipes](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution-batching).

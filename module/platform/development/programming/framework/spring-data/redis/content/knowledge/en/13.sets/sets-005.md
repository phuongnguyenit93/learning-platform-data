# Designing Unique Member Lists with Redis Set

In many business domains, an application needs to manage **a non-duplicate set of members**: users in a group, event registrants, favorited product IDs, permissions assigned to an account, or a list of already-seen tasks. With an ordinary list, the application must search for and deduplicate elements itself; when multiple requests write concurrently, checking and then adding as two separate operations easily creates concurrency bugs.

**Redis Set** is designed for this problem: every element (**member**) in a Set is unique based on the representation stored by Redis. `SADD` adds an element if it does not yet exist, `SISMEMBER` checks membership, `SREM` removes an element, and `SCARD` counts members. Spring Data Redis maps these operations via `SetOperations`, typically obtained from `StringRedisTemplate.opsForSet()`.

This lesson covers how to choose Redis Sets, define what counts as "the same member", build safe add/check/remove APIs under concurrent access, design keys and data lifecycles, enforce member limits, scan large Sets, and evaluate needs that Sets do not address directly such as ordering, pagination, or per-element TTLs.

## 1. What Is a Redis Set?

A Redis Set is a collection of binary-safe string members (**binary-safe strings**) stored under a single Redis key. Members have no guaranteed order, and each member value appears at most once within the same Set.

Suppose Redis stores account IDs participating in group `42`:

```redis
SADD group:42:members user-101 user-202 user-303
# 3: added three new members

SADD group:42:members user-202
# 0: user-202 is already in the Set

SISMEMBER group:42:members user-101
# 1: present in the Set

SCARD group:42:members
# 3: number of members in the Set
```

Model:

```text
Redis key: group:42:members        (type: set)
  ├── user-101
  ├── user-202
  └── user-303

SADD group:42:members user-202
   → Does not create a duplicate copy of user-202

SADD group:42:members user-404
   → The set gains one member, SCARD becomes 4
```

**Core point:** Redis eliminates duplicates at **the member level within a single Set**. If two different Redis keys both contain `user-202`, that is not a duplicate within the same Set. If the system requires "each user may belong to at most one group across the entire system", an additional cross-group invariant at the data design layer or another atomic operation is needed.

### How Set Differs from List and Sorted Set

| Redis Structure | Duplicate Members? | Ordering | Typical Queries | When to Choose |
| --- | --- | --- | --- | --- |
| **Set** | No, for the same member representation | No stable order | Is in set? Add/remove? Count? Intersect/union/diff? | Unique ID lists, membership checks |
| **List** | Can duplicate | Ordered by position in list | Push/pop at both ends, read by position | Maintained queues/ordered lists |
| **Sorted Set** | Unique members | Ordered by score and tie-break comparison rules | Top N, ranking, range by score | Need both uniqueness and ordered ranking/pagination |
| **Hash** | Unique field names | No guaranteed field order | Field → value, read/write values by field | Each ID has its own fields/attributes under one key |

In a Redis List, a pattern like "`LPOS` to check then `RPUSH` if absent" **is not atomic**: two clients can both see it missing and both append. With a Set, a single `SADD` command solves uniqueness per member.

Sorted Sets also enforce unique members, yet require managing a **score**; they fit better when you need newest members, top scores, or ordered pagination. Do not use a Sorted Set if the business logic only needs existence checks and has no natural score.

## 2. What Counts as "The Same Member"?

Redis compares member values by stored bytes, without understanding Java objects, usernames, or business rules. With `StringRedisTemplate`, a Java String member is converted to UTF-8 bytes. Two strings with different bytes are treated by Redis as **two distinct members**, unless the application normalizes them before writing.

```redis
SADD demo:members user-42
# 1

SADD demo:members USER-42
# 1: different letter case

SADD demo:members " user-42 "
# 1: leading/trailing whitespace

SCARD demo:members
# 3
```

If the business considers those three values to represent the same user, a Redis Set **cannot infer that automatically**.

### Identity Rules to Establish Upfront

1. **Use stable IDs** rather than display names. Display names can change, collide across users, or contain Unicode variants.
2. **Normalize only according to an agreed contract.** For example, if user IDs are designed as canonical lowercase UUIDs, apply that consistently in every producer. Do not arbitrarily lowercase emails or trim business codes if doing so could alter identifier meaning.
3. **Preserve meaningful characters.** IDs `"0012"` and `"12"` may be two distinct IDs; do not parse to integers and convert back to strings unless permitted.
4. **Standardize serializers.** A Java producer using JDK binary serialization for members and a Python producer writing UTF-8 text may both think of `"user-42"` in code while storing **different bytes**.
5. **Distinguish uniqueness scope.** `group:42:members` and `group:43:members` are two membership domains; the same user appearing in both groups may be valid behavior.

Example ID validation function for an illustrative system where IDs only contain letters, digits, underscores, and hyphens:

```java
import java.util.Objects;
import java.util.regex.Pattern;

public final class MemberId {
    private static final Pattern VALID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private MemberId() {}

    public static String requireValid(String id) {
        Objects.requireNonNull(id, "memberId");
        if (!VALID.matcher(id).matches()) {
            throw new IllegalArgumentException("Invalid memberId");
        }
        return id;
    }
}
```

The character rule here is an **example contract**, not a Redis limitation. If the system uses ULIDs, UUIDs, customer codes, or external identifiers, design an appropriate validator. Normalized values must also remain consistent across all services reading and writing the same set.

## 3. Essential Set Commands and Complexity

| Operation | Redis Command | Result / Meaning | Typical Complexity |
| --- | --- | --- | --- |
| Add one member | `SADD key member` | `1` if newly added, `0` if already present | Average `O(1)` per member |
| Add multiple members | `SADD key a b c` | Number of **new** members added | `O(M)` in input member count |
| Check one member | `SISMEMBER key member` | `1` present, `0` absent | Average `O(1)` |
| Check multiple members | `SMISMEMBER key a b c` | One 0/1 result per member | `O(M)`; requires Redis command support |
| Remove members | `SREM key member...` | Number of members actually removed | `O(M)` in requested member count |
| Count members | `SCARD key` | Current element count | `O(1)` |
| Return all members | `SMEMBERS key` | Entire set, no guaranteed order | **`O(N)`** in cardinality |
| Intersect two/more sets | `SINTER key1 key2...` | Set of members present in all sets | Depends on set counts/sizes; can be costly for large sets |
| Union of multiple sets | `SUNION key1 key2...` | Set of members present in at least one set | Scales with total elements examined |
| Set difference | `SDIFF key1 key2...` | Members in the first set absent from subsequent sets | Depends on set sizes and count |
| Incremental scan | `SSCAN key cursor ...` | A subset of members plus next cursor | Full scan typically scales with `N` |
| Random peek, no remove | `SRANDMEMBER key` | One random member | Good for sampling, does not guarantee weighted business distribution |
| Random pop, with remove | `SPOP key` | Removes and returns one member | Mutates the Set; distinguish from sampling |
| Move member between two Sets | `SMOVE source destination member` | Moves if member exists in source | Usually `O(1)`, requires compatible routing in Cluster |

In the table, `N` is the number of members in the Set under consideration; `M` is typically the number of members passed to a single command. "Average" matters because Redis uses optimized internal structures for membership lookups, yet real-world latency still depends on member string lengths, network, CPU load, and Redis's internal Set encoding.

### What Does `SADD` Guarantee?

When two clients concurrently send:

```redis
SADD group:42:members user-999
```

Redis processes each command as an atomic operation on the Set. If the member did not exist initially, under normal execution **one** command succeeds in adding it and receives `1`, while the other sees the member already exists and receives `0`. Two identical members are never created.

`SADD` is **idempotent with respect to membership state**: resending the same command with the same key/member does not create a duplicate copy. However, a response lost due to timeout still leaves the application unsure whether the first command succeeded; never infer "timeout means not added".

### Is Check-Then-Add Necessary?

You do not need code like:

```java
if (!Boolean.TRUE.equals(redis.opsForSet()
        .isMember("group:42:members", "user-999"))) {
    redis.opsForSet().add("group:42:members", "user-999");
}
```

The `isMember` check adds no atomic guarantee and wastes an extra round trip. If the sole requirement is ensuring uniqueness, **call `SADD` directly** and inspect the count of newly added elements.

## 4. Key Design for Unique Member Lists

For the question "which users belong to this group?", a key structured directly by group is a natural choice:

```text
group:{groupId}:members

group:team-42:members
  user-101
  user-202
  user-303
```

Note that `{groupId}` in this notation is a **placeholder**, not necessarily literal braces in the key. In Redis Cluster, curly braces act as a **hash tag** if present in an actual key, so distinguish the two uses carefully.

A key design should answer:

- **Who owns the Set?** A group, event, resource, tenant, or session?
- **What type of identifier is the member?** User ID, product ID, permission name, or special string?
- **Can one member appear in multiple Sets?** If yes, it is a many-to-many relationship.
- **Who writes and removes?** Do multiple writers share the same canonical ID contract?
- **Does the set have a maximum cap?** How many members can a group hold?
- **Does the set expire?** If yes, does the whole Set expire or does each membership expire individually?
- **Are ordering or reverse lookups required?** Finding users from a group is a different query from finding groups from a user.

### One-Way vs. Two-Way Membership

Simple model:

```text
group:42:members → {user-101, user-202}
group:43:members → {user-101, user-303}
```

The query "is user-101 in group 42?" can call `SISMEMBER group:42:members user-101` very quickly.

However, the query "which groups does user-101 belong to?" is difficult with only group-keyed Sets: the application should not scan every group to find one user. You can maintain a **reverse index**:

```text
user:user-101:groups → {42, 43}
user:user-202:groups → {42}
user:user-303:groups → {43}
```

When a user joins a group, the application must update both `group:42:members` and `user:user-101:groups`. These are **two Redis keys**, so uniqueness inside each Set does not automatically keep both indexes consistent. If one write succeeds and the other fails, the two directions can drift.

Possible solutions depending on business needs:

1. Store only one direction and query the reverse direction from the primary database if reverse lookups are rare.
2. Store both directions while defining a clear source of truth; accept eventual consistency, idempotent retries, and a reconciliation job.
3. If atomic updates are mandatory, use an appropriate transaction/script **with all keys placed in the same hash slot when running Redis Cluster**.
4. For authorization data or memberships needing strong constraints and multi-table transactions, keep canonical state in a transactional database and use Redis Sets as a projection/cache.

Do not slap a shared hash tag onto every group just to allow multi-key scripts: that can funnel all data into a single Redis Cluster slot and node, defeating load distribution.

## 5. Spring Data Redis: Using `SetOperations`

In Spring Boot with `spring-boot-starter-data-redis`, you can use `StringRedisTemplate` when keys and members are UTF-8 strings.

Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Redis configuration for Spring Boot 3.x in a test environment:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

Inside containers or Kubernetes, `localhost` points to the current process's own environment; choose the host matching the actual application topology. Dependencies and connection settings only configure communication with Redis; they do not start a Redis server automatically.

### 5.1. Service for Managing Unique Members

```java
import java.util.Objects;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class GroupMembershipService {

    private final SetOperations<String, String> members;

    public GroupMembershipService(StringRedisTemplate redis) {
        this.members = redis.opsForSet();
    }

    public boolean join(String groupId, String userId) {
        String key = keyFor(groupId);
        String member = MemberId.requireValid(userId);

        Long added = members.add(key, member); // SADD
        if (added == null) {
            throw new IllegalStateException("No SADD result available");
        }
        return added == 1L;
    }

    public boolean isMember(String groupId, String userId) {
        Boolean found = members.isMember(
                keyFor(groupId),
                MemberId.requireValid(userId)
        ); // SISMEMBER
        return Boolean.TRUE.equals(found);
    }

    public boolean leave(String groupId, String userId) {
        Long removed = members.remove(
                keyFor(groupId),
                MemberId.requireValid(userId)
        ); // SREM
        if (removed == null) {
            throw new IllegalStateException("No SREM result available");
        }
        return removed == 1L;
    }

    public long count(String groupId) {
        Long size = members.size(keyFor(groupId)); // SCARD
        return Objects.requireNonNull(size, "No SCARD result available");
    }

    private static String keyFor(String groupId) {
        return "group:" + MemberId.requireValid(groupId) + ":members";
    }
}
```

In this example, `MemberId.requireValid` is the ID validation/normalization helper introduced in section 2. In real logic, use distinct naming and validation rules tailored to `groupId` and `userId`.

Meaning of return values:

- `join(...) == true`: in a normal completed call, the member was **newly added** to the Redis Set.
- `join(...) == false`: the member was already in the Set, so the final state is still satisfied.
- `leave(...) == true`: a member was removed.
- `leave(...) == false`: the member did not exist at the time the command ran.
- `isMember(...)`: reflects membership state at the moment of the check command.
- `count(...)`: current number of members; this is a point-in-time count snapshot and does not lock out later changes.

This code is meant for normal Spring Data Redis calls, not inside a pipeline/transaction callback where certain APIs temporarily return `null` because results are processed later. In critical workflows, handle connection errors or timeouts according to application policy; do not turn every Redis failure into `false`, which confuses "not a member" with "unable to check".

### 5.2. Adding a Group of Members in One Command

```java
Long added = stringRedisTemplate.opsForSet().add(
        "group:42:members",
        "user-101",
        "user-202",
        "user-101"
);
```

If the Set was initially empty, `added` equals `2`, because `user-101` was repeated in the input list but stored only once. With Redis Sets, **the `SADD` result is the number of newly added members**, not the total member count afterward and not the number of passed arguments.

For large imports, split into bounded batches. A single command carrying hundreds of thousands of members still generates heavy CPU load and huge payloads; combining appropriate batching/pipelining controls resource usage, though the total number of members to process remains.

## 6. Reading Members: Pick the Right Query Instead of Loading the Whole Set

Suppose a group has one million members and the application only wants to know whether `user-101` is in the group. Avoid reading the entire list and searching in Java:

```java
// Unsuitable when you only need to check one member:
Set<String> all = stringRedisTemplate.opsForSet()
        .members("group:42:members"); // SMEMBERS

boolean exists = all != null && all.contains("user-101");
```

`SMEMBERS` costs `O(N)` and returns **all** members. With one million members, Redis builds a massive reply, the network transfers all that data, and Java allocates a collection holding every received value.

Instead:

```java
Boolean exists = stringRedisTemplate.opsForSet()
        .isMember("group:42:members", "user-101"); // SISMEMBER
```

To count, use `SCARD`:

```java
Long total = stringRedisTemplate.opsForSet()
        .size("group:42:members");
```

Do not call `members(key).size()` just to count, since that downloads the entire Set even though Redis already tracks cardinality and provides `SCARD`.

### Is `SMEMBERS` Ever Appropriate?

Yes, if the Set is **small, strictly bounded**, and the business genuinely needs all members—for instance, a role containing at most 10 permissions or a room with at most 30 participants. Then loading everything can be simpler and cheaper than complex designs.

Still, set clear bounds. A "fetch all members" API that works fine with 20 elements today can become a bottleneck when data grows to 200,000 elements later.

### Redis Sets Do Not Have Pagination Order

`SMEMBERS` returns members **with no guaranteed order**. Do not build an API like:

```java
List<String> page = new ArrayList<>(allMembers).subList(0, 20);
```

and label it "the first 20 members", because Set order has no stable meaning, not to mention downloading the entire dataset.

If you need a member list **by join time**, consider adding a Sorted Set:

```redis
ZADD group:42:joinedAt 1762930000000 user-101
ZADD group:42:joinedAt 1762932000000 user-202
ZRANGE group:42:joinedAt 0 19
```

Sorted Sets enforce unique members inside the Sorted Set itself while carrying a score for ordered reads. If keeping both a Set and a Sorted Set, define the source of truth and synchronization strategy; in some cases, **only a Sorted Set** satisfies both membership and ordering without duplicate storage.

Do not assume timestamp scores guarantee absolute ordering when multiple members share the exact same timestamp: Redis applies lexicographical member comparison on score ties; if custom business ordering is needed, design a tie-breaker or composite sort key.

## 7. Traversing Large Sets with `SSCAN`

When maintenance jobs or exports must process hundreds of thousands of members, use `SSCAN` to break up the traversal:

```redis
SSCAN group:42:members 0 COUNT 200
# Redis returns [new cursor, member list]

SSCAN group:42:members <new-cursor> COUNT 200
# Continue until Redis returns cursor 0
```

Key points to understand accurately:

- `COUNT 200` is a **hint** for how much work to do per scan pass, not a hard cap on returned members.
- A scan pass can return **empty** while the cursor is not yet `0`; you must still continue.
- A full scan cycle generally scales in total cost with the member count; `SSCAN` breaks the work into chunks rather than turning one million members into an `O(1)` job.
- When a Set mutates during scanning, there is no transactional snapshot. A member can appear twice; members added/removed during the scan may or may not be observed depending on timing.
- Some compact internal encodings can cause Redis to return most or all members in a single scan pass, even with a low `COUNT`.
- `MATCH` can filter members by pattern, yet does not turn a Redis Set into a prefix search index.

### `SetOperations.scan` Example

```java
import java.util.function.Consumer;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class GroupMemberScanner {
    private final StringRedisTemplate redis;

    public GroupMemberScanner(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void forEachMember(
            String groupId,
            Consumer<String> processor
    ) {
        String key = "group:" + MemberId.requireValid(groupId) + ":members";
        ScanOptions options = ScanOptions.scanOptions()
                .count(200)
                .build();

        try (Cursor<String> cursor =
                     redis.opsForSet().scan(key, options)) {
            while (cursor.hasNext()) {
                processor.accept(cursor.next());
            }
        }
    }
}
```

`try-with-resources` ensures the cursor and associated connection resources are closed. `processor` should handle items individually or buffer into bounded batches, rather than collecting every member into a giant `List`. If work must avoid duplicate processing, `processor` must be idempotent or maintain a separate checkpoint/processing identifier.

Do not use `SSCAN` as a stable "page 1, 2, 3" API while the Set mutates concurrently. The cursor is traversal state, not a sorted offset. If ordered pagination and durable cursors are required, choose an ordered data model and matching consistency policy.

## 8. Combining Member Lists with Set Operations

Redis Sets shine when business logic asks questions about **set relationships**:

- Users in both group A **and** group B.
- Users in at least one of the two groups.
- Users in group A who are not yet in group B.

Suppose:

```redis
SADD group:A:members u1 u2 u3
SADD group:B:members u2 u3 u4
```

| Question | Command | Logical Result |
| --- | --- | --- |
| Common members of A and B | `SINTER group:A:members group:B:members` | `{u2, u3}` |
| Members in A or B | `SUNION group:A:members group:B:members` | `{u1, u2, u3, u4}` |
| Members in A not in B | `SDIFF group:A:members group:B:members` | `{u1}` |

In Spring Data Redis:

```java
Set<String> both = stringRedisTemplate.opsForSet()
        .intersect("group:A:members", "group:B:members");

Set<String> either = stringRedisTemplate.opsForSet()
        .union("group:A:members", "group:B:members");

Set<String> onlyA = stringRedisTemplate.opsForSet()
        .difference("group:A:members", "group:B:members");
```

With large sets, commands returning **the full result** can consume substantial CPU/network/memory, even when the business question is merely "do they overlap?" or "how many common members are there?". On Redis versions supporting it, `SINTERCARD` can compute intersection cardinality without transmitting member lists, and supports a `LIMIT` option to stop counting at a threshold per command semantics. Verify your Redis version and client support before using it.

### Redis Cluster and Multi-Key Set Operations

In Redis Cluster, multi-key commands such as `SINTER`, `SUNION`, `SDIFF`, or `SMOVE` must obey appropriate hash slot rules; cross-slot requests are normally rejected by Redis. Two keys `group:A:members` and `group:B:members` are not guaranteed to fall in the same slot.

If you frequently need intersections across sets belonging to **the same tenant**, consider controlled hash tags:

```text
tenant:{t42}:group:A:members
tenant:{t42}:group:B:members
```

Redis Cluster maps these two keys to the same hash slot thanks to `{t42}`. In return, every key sharing that hash tag concentrates load on one slot/node. Choose hash tags based on concrete query needs rather than lumping the whole system under one tag.

If Sets reside on different nodes and multi-key operations are needed, you may have to redesign the data model, perform bounded aggregation at the application layer, or maintain an appropriate index/materialized view. Those carry their own costs and consistency trade-offs; do not assume Redis Cluster Set operations work seamlessly across slots.

## 9. Capping Member Count: `SCARD` Followed by `SADD` Is Not Enough

Suppose a group may hold at most **100 members**. A mistake-prone implementation is:

```java
Long count = redis.opsForSet().size("group:42:members");
if (count != null && count < 100) {
    redis.opsForSet().add("group:42:members", "user-999");
}
```

The problem: `SCARD` and `SADD` are two separate commands. If the group has 99 members and two concurrent requests check simultaneously, both can observe `99` and each add a different member. The result is 101 members, breaking the limit.

When the 100-member cap is a **strict business invariant**, "already a member?", "room left?", and "add member" must execute as **one atomic operation**.

### 9.1. Lua Script for Bounded Member Addition

```lua
-- KEYS[1]: Set key
-- ARGV[1]: member ID
-- ARGV[2]: max members (positive integer)

if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1 then
    return 0 -- Already a member: does not consume capacity
end

if redis.call('SCARD', KEYS[1]) >= tonumber(ARGV[2]) then
    return -1 -- Group is full
end

return redis.call('SADD', KEYS[1], ARGV[1])
-- 1: added successfully
```

Redis executes a Lua script atomically relative to commands from other clients on the instance running the script. Thus two requests cannot interleave `SADD` between the cardinality check and the add step of this script.

This is a **single-Set solution**. If you also need to check database state, update a reverse index, or publish an event to a broker, atomicity does not automatically extend across those systems.

### 9.2. Calling the Script from Spring Data Redis

```java
import java.util.List;
import java.util.Objects;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class CapacityLimitedGroupService {

    private static final int MAX_MEMBERS = 100;

    private static final RedisScript<Long> ADD_IF_ROOM =
            RedisScript.of(
                    """
                    if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1 then
                        return 0
                    end
                    if redis.call('SCARD', KEYS[1]) >= tonumber(ARGV[2]) then
                        return -1
                    end
                    return redis.call('SADD', KEYS[1], ARGV[1])
                    """,
                    Long.class
            );

    private final StringRedisTemplate redis;

    public CapacityLimitedGroupService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public JoinResult join(String groupId, String userId) {
        String key = "group:" + MemberId.requireValid(groupId) + ":members";
        String member = MemberId.requireValid(userId);

        Long value = Objects.requireNonNull(
                redis.execute(
                        ADD_IF_ROOM,
                        List.of(key),
                        member,
                        Integer.toString(MAX_MEMBERS)
                ),
                "No Redis script result"
        );

        if (value == 1L) return JoinResult.ADDED;
        if (value == 0L) return JoinResult.ALREADY_MEMBER;
        if (value == -1L) return JoinResult.FULL;
        throw new IllegalStateException("Unexpected Redis script result");
    }

    public enum JoinResult {
        ADDED,
        ALREADY_MEMBER,
        FULL
    }
}
```

The script accesses only one key via `KEYS[1]`, so it has no multi-key cross-slot issue in Redis Cluster. The Java code uses a text block suitable for Java 17+; `RedisScript.of(...)` specifies the `Long` return type for the integer returned by Lua.

When the member is already present, returning `ALREADY_MEMBER` even when the group is full makes sense because that idempotent operation **does not consume an extra slot**. This is an intentional business rule; if the business wants different behavior, design the API explicitly.

### 9.3. Limits Do Not Replace Authorization Rules

The Lua script only enforces the count limit. The application still must verify:

- Is the caller allowed to add members to the group?
- Is the member ID valid, active, and eligible to join?
- Does removing and re-adding a member need to trigger events or billing?
- If Redis is only a cache, does the authoritative database enforce the equivalent invariant?

A Redis Set does not know those rules. Also, if a client times out after Redis already executed the script, the caller may need to re-read membership to confirm state before retrying or emitting business events.

## 10. TTL and Lifecycle of a Set

Standard Redis TTL applies to **the entire Set key**, not to individual members:

```redis
SADD event:42:checkin user-101 user-202
EXPIRE event:42:checkin 86400
TTL event:42:checkin
```

That means the whole check-in set expires according to the key's TTL. If one user's membership needs to expire after 15 minutes while other users remain, a standard Set model **has no per-member TTL**.

Alternative designs depending on needs:

| Requirement | Design to Consider |
| --- | --- |
| Temporary Set expiring all at once | Set TTL on the Set key |
| Long-lived membership | Key without TTL, with explicit removal workflow on leave |
| Each member has an individual expiration | Sorted Set with expiration timestamp as score + expired-member checks/cleanup |
| Membership tied to per-session TTL | Separate key per member/session, optionally paired with a group index |
| Core membership requiring durability | Primary database as source of truth; Redis as cache/index as needed |

### Setting TTL When Creating a Set: Avoid the Gap Between Commands

```redis
SADD event:42:checkin user-101
EXPIRE event:42:checkin 86400
```

These two commands **are not atomic together**. If the application crashes after `SADD` but before `EXPIRE`, the Set can persist without a TTL. When temporary lifetime is mandatory, use a suitable transaction/script to create and set TTL in one atomic unit, or adopt a design that reliably reapplies TTLs.

Likewise, calling `SADD` on an existing Set normally **does not refresh** the key's TTL. Decide the policy upfront: "expire 24 hours after creation" differs from "expire 24 hours after the latest update".

When `SREM` removes the last member, the Set becomes empty and Redis typically deletes the key rather than keeping an empty Set forever. Thus `SCARD key` returning 0 can mean the Set never existed, was deleted, expired via TTL, or currently has no members. If business logic must distinguish "group exists with zero members" from "group does not exist", store **separate group metadata** instead of relying purely on the existence of the Set key.

### Do Not Use Plain Sets for Per-User Expiring Membership Without Controls

A common pattern for time-bounded membership is a Sorted Set:

```redis
ZADD group:42:expiry 1762938000000 user-101
ZADD group:42:expiry 1762939000000 user-202
```

The application checks a user with `ZSCORE` and compares against current time; a maintenance job uses `ZREMRANGEBYSCORE` to purge expired items. **The mere presence of a member in the Sorted Set does not prove it is still active** if the cleanup job has not run yet. You must verify expiration in read logic or handle it atomically when business rules require strict enforcement.

## 11. Redis Sets, Memory, and Big Keys

A Set is a single Redis key yet can store millions of members. Counting keys with `DBSIZE` does not reveal the cardinality of a huge Set; inspect the Set itself.

Commands:

```redis
TYPE group:42:members
SCARD group:42:members
MEMORY USAGE group:42:members
OBJECT ENCODING group:42:members
TTL group:42:members
```

- `SCARD` returns the current member count, not total byte size.
- `MEMORY USAGE` estimates Redis memory consumption; for collection types, sampling behavior can affect cost/accuracy.
- `OBJECT ENCODING` shows the internal representation Redis uses, depending on version and data. Small integer-only Sets can use a more compact encoding than large string Sets.
- `TTL` shows the whole Set's remaining lifetime, though a Set with a TTL can still grow very large before expiring.

For example, suppose one million member IDs average 20 bytes each: **raw ID contents alone** take roughly 20 MB, before Redis overhead, network, protocol, and Java memory. `SMEMBERS` would return that entire payload on every call; if an endpoint is hit frequently, costs rise rapidly.

### When Should You Split a Set?

Consider partitioning by:

- **Owning entity:** one Set per group/event/tenant.
- **Time window:** `event:42:attendees:2026-11` to bound history by period, if queries accept time partitioning.
- **Buckets:** `group:42:members:bucket:00..31` via a stable hash of the member, when a single Set grows too large or becomes a hot key.

With buckets, membership checks must route to the right bucket from the member ID; total counts must sum across buckets, and intersection/union operations must account for sharded data. Bucket count, hash function, and migration rules must remain consistent across producers and consumers.

In Redis Cluster, **one Set is one key in one hash slot**, so Redis never spreads a single Set's members across nodes. Splitting into multiple keys helps distribute load, at the cost of complicating multi-key updates, TTL management, and consistency.

Do not split Sets prematurely when data is small and access patterns are simple. Increasing key count also raises management overhead and Redis command volume.

## 12. Common Design Scenarios

### 12.1. Users Who Favorited a Product

```text
product:sku-42:followers → {u101, u202, u303}
```

Requirements:

- "Is this user already following?" → `SISMEMBER`.
- "Follow" → `SADD`, where the 0/1 return indicates whether state actually changed.
- "Unfollow" → `SREM`.
- "How many followers?" → `SCARD`.

If you only display the count and the current user's status, **you do not need `SMEMBERS`**. If the follower list must be ordered by follow time, a Set lacks that information; use a scored index or another query source.

### 12.2. Role Permission List

```text
role:editor:permissions → {article:read, article:write, comment:moderate}
```

A Set fits because permissions are naturally unique and moderate in number. Authorization checks can call `SISMEMBER`. However, if this is a critical authorization system, design update rules, auditing, cache invalidation, and fallbacks when Redis is unavailable. Never treat a standalone cache value as the entire authentication/authorization mechanism when the canonical source lives elsewhere.

### 12.3. Processed Message IDs

```text
consumer:billing:processed:2026-11-12 → {message-1, message-2, ...}
```

A Set can help detect duplicate IDs. However, if business logic both **records membership** and **performs external side effects** (such as billing or database updates), `SADD` succeeding does not prove the external side effect finished. Persist processing state, idempotency keys, or transaction/outbox records in a system capable of providing the required guarantees.

For very high volume and long retention, keeping a Set of IDs forever can create a big key and consume excessive memory; consider time-based partitioning, appropriate TTLs, or durable storage.

### 12.4. Online Chat Room Participants

```text
room:42:online → {session-a, session-b, session-c}
```

If members represent user IDs, a user on two devices appears once; if members represent **session IDs**, each session is tracked independently. Decide this before choosing a unique list: "online users" and "online connections" are two differently defined sets.

A plain Redis Set does not automatically detect which sessions disconnected due to a crash. You need per-session heartbeats/TTLs or a proper presence mechanism; calling `SADD` when a socket opens is not enough on its own to keep an online list accurate.

## 13. Migrating Data from a List to a Set

A legacy system stored members in a List, potentially with duplicates:

```redis
RPUSH legacy:group:42:members u1 u2 u1 u3
LRANGE legacy:group:42:members 0 -1
# u1, u2, u1, u3
```

When migrating to a Set:

```redis
SADD group:42:members u1 u2 u1 u3
SCARD group:42:members
# 3
```

Before migrating, verify:

1. **Did the old order carry meaning?** Lists preserve order; Sets do not. If order matters, consider a Sorted Set or another structure.
2. **What did legacy duplicates mean?** If duplicates represented attendance count or weight, migrating straight to a Set drops that information.
3. **Do IDs share one format?** Normalize IDs before or during migration; handle dirty values intentionally.
4. **Are producers still writing to the legacy List during migration?** If yes, a single backfill misses subsequent changes; a controlled dual-write/reconciliation phase or cutover is needed.
5. **What about lifecycle and TTL?** Do not accidentally turn an expiring List into a Set with no TTL.
6. **When to stop reading the List?** Retire the old path only after all consumers and relevant data have switched to the new contract.

For very large Lists, do not run `LRANGE 0 -1` and load everything into the JVM just to convert. Use bounded range batching, write `SADD` in batches, track progress, and handle concurrent mutations. If elements are added/removed in the List while paging by offset, pages can shift; use a snapshot/cutover plan or a stable source of truth when exactness is required.

## 14. Observability and Diagnostics

When a membership API is slow or returns unexpected results, inspect from Redis data through Spring Data Redis:

| Symptom | Common Cause | Appropriate Check |
| --- | --- | --- |
| User added but count does not rise | User already existed in Set | `SADD` return may be 0; check `SCARD` |
| Same user appears twice in UI | App merges data from multiple sources, or distinct IDs map to the same person | Check canonical IDs and UI aggregation; do not blame Redis Set for storing duplicates |
| `SISMEMBER` returns 0 though producer claims write succeeded | Wrong key/namespace, different serializer, casing/whitespace mismatch, key TTL expired | `TYPE`, `TTL`, inspect exact bytes/encoding and key |
| `WRONGTYPE` | Another writer used the key for a List/Hash/String | `TYPE key`, separate namespaces if needed |
| List page gets progressively slower | `SMEMBERS` loads a growing Set | Measure `SCARD`, response bytes, p95/p99, and redesign pagination |
| `SSCAN` emits duplicate members | Set changed during scan, or inherent scan behavior | Process idempotently; do not use scan as a snapshot |
| Intersecting two groups fails in Cluster | Keys live in different hash slots | Check key slots/topology; adjust design/hash tags carefully |
| Group exceeds 100-member limit | `SCARD` followed by `SADD` as two separate commands | Use a script combining check and write atomically |
| Set does not exist even though group exists | Set is empty, TTL expired, or not yet created | Store separate group metadata to distinguish states |
| Redis memory grows sharply | Set holds too many members or large member values | `SCARD`, `MEMORY USAGE`, track per-key growth |

Useful diagnostic commands:

```redis
TYPE group:42:members
SCARD group:42:members
SISMEMBER group:42:members user-101
TTL group:42:members
MEMORY USAGE group:42:members
INFO commandstats
SLOWLOG GET 10
```

`SLOWLOG` reflects command execution time inside Redis, excluding full network time or Java deserialization. If a large `SMEMBERS` slows down an API without tripping the slowlog threshold, still measure transferred bytes, connection wait time, heap allocation, and Java GC.

In production, avoid running `SMEMBERS` on huge Sets just to poke around and avoid keyspace-scanning `KEYS *` on normal paths. Diagnostic tools also consume resources; plan sampling and rate limits.

## 15. Mistakes to Avoid

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Using a List and checking existence before pushing | Race condition across writers, creating duplicates | Use `SADD` on a Set |
| Assuming Redis Set merges `user-42` and `USER-42` | One person appears as multiple members | Normalize IDs by shared contract |
| Calling `SMEMBERS` to check one user | Downloads entire set, raising latency and memory | `SISMEMBER` |
| Calling `SMEMBERS` to count | Downloads everything then calls `size()` | `SCARD` |
| Using a Set for time-ordered pagination | No stable ordering | Sorted Set / ordered index |
| Treating `SSCAN COUNT 100` as an exact cap | A pass can still return more or empty | Handle cursor, bound processing, and watch memory |
| Assuming `SADD` returns total member count | Incorrect counting | Return value is the count of **newly** added members |
| Assuming `SCARD` then `SADD` enforces max size | Concurrent writers can exceed the limit | Appropriate script/transaction |
| Assuming TTL applies per user | Entire Set expires together | Choose Sorted Set or separate keys for per-member expiry |
| Maintaining Set and reverse index without reconciliation | Bidirectional links drift after partial failures | Pick source of truth and add update/recovery mechanisms |
| Treating a Redis Set as a FIFO queue | `SPOP` picks/removes randomly, not FIFO | List or Stream matching queue requirements |
| Assuming a Set in Redis Cluster shards members across nodes | One Set is one key in one slot | Intentionally partition keys if load spreading is needed |

## 16. Self-Practice Exercises

**Question 1.** Run sequentially:

```redis
SADD members:a u1 u2
SADD members:a u2 u3
SCARD members:a
```

What do the two `SADD` commands return? What is `SCARD`?

*Hint:* the first adds 2, the second only newly adds `u3` so it returns 1; final cardinality is 3.

**Question 2.** Two services concurrently try to add `u9` to `group:42:members`. Do you need a Redis lock before sending `SADD` to prevent storing the member twice?

*Hint:* for the same member in the same Set, Redis guarantees uniqueness via the atomicity of `SADD`.

**Question 3.** A group has one million users. The API only needs to return "has the current user joined?" and "total member count". Which two Redis commands should you choose?

*Hint:* `SISMEMBER` and `SCARD`, no need for `SMEMBERS`.

**Question 4.** An API needs the **20 most recent** participants. Why not use `SMEMBERS` or `SSCAN` and take the first 20 elements?

*Hint:* Sets have no chronological order; consider a Sorted Set with timestamp scores and tie-breaking handling.

**Question 5.** A group is capped at 100 people and currently has 99. Two requests add two different users simultaneously. Why can `SCARD` followed by `SADD` result in 101 people?

*Hint:* two separate commands do not form an atomic check-and-add operation; a `SISMEMBER + SCARD + SADD` script solves this for a single key.

**Question 6.** One user has two active sessions. If the online Set stores user IDs, is `SCARD` 1 or 2? What if it stores session IDs?

*Hint:* member definition determines what cardinality means.

**Question 7.** The system needs each user's membership to expire 30 minutes after joining, while the group remains. Why doesn't `EXPIRE group:42:members 1800` satisfy this?

*Hint:* standard Redis Set TTL belongs to the entire key, not individual members.

**Question 8.** Why does maintaining both `group:42:members` and `user:u1:groups` complicate join/leave? If Redis Cluster places those two keys in different slots, what is the impact?

*Hint:* both indexes must stay consistent, while multi-key transactions/scripts in Cluster impose slot requirements.

## 17. Key Takeaways

**A Redis Set is the right structure for storing unique member lists when business logic does not require ordering.** `SADD` prevents storing duplicate copies of the same member within a Set; `SISMEMBER` and `SCARD` check and count efficiently without loading all data. With Spring Data Redis, use `StringRedisTemplate.opsForSet()` and standardize identifiers and serializers across producers so "uniqueness" preserves its exact meaning.

Good design does not stop at picking Set. Define membership scope, key naming, cardinality bounds, reverse-query needs, TTL, and the source of truth. Avoid `SMEMBERS` on large Sets, use `SSCAN` for batch processing, and pick Sorted Sets when ordering is needed. When enforcing a **maximum of N members**, checking and then adding via two commands is insufficient under concurrent writers; place the check and mutation inside one appropriate atomic operation. These choices keep unique member lists semantically sound as your Spring Boot application scales in data volume and instance count.

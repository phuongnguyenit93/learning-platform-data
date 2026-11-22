# TTL, expiration time, and invalidating stale data

TTL (Time To Live) specifies how long a piece of data is considered valid. In a continuously running Java application, a cache typically checks TTL on read or uses a background task to refresh data. With CRaC, a process can be checkpointed and paused for some time. During that time, clocks still advance and external systems continue changing, while threads, schedulers, and in-heap caches do not necessarily perform refresh work as when the application is running.

Upon restore, cache objects and saved timestamps may still exist. An entry that was valid before checkpoint may have expired; a lease may have been reassigned by another system; a token may have been revoked; an invalidation event may have been emitted while the application was inactive. Therefore, the application should not treat data in the heap as fresh merely because it was just restored. It must check expiration times, verify versions, and invalidate or refresh data before reusing it.

## 1. TTL and expiration time

TTL is the duration for which data is allowed to live or be considered usable. The expiration time (`expiresAt`) is the specific point in time after which the data is no longer valid according to policy.

For example, an application reads a configuration at 10:00 with a 5-minute TTL:

```text
fetchedAt = 10:00
TTL       = 5 minutes
expiresAt = 10:05
```

If the application checkpoints at 10:02 and restores at 10:20, the entry has already expired even though the object remains in the heap. Do not calculate TTL from the restore time and extend it to 10:25, unless business policy explicitly states that TTL restarts when data is freshly loaded.

Some common terms:

| Term | Meaning |
| --- | --- |
| TTL | Validity duration measured from a defined milestone, usually when data is created or fetched. |
| `fetchedAt` / `createdAt` | Time when data was fetched or created. |
| `expiresAt` | Time when data expires according to an authoritative source or cache policy. |
| Soft TTL | Milestone when data should be refreshed; under some policies, stale data may still be served temporarily. |
| Hard TTL | Mandatory expiration point; after this mark data must not be used as valid. |
| Lease | Right to use a resource for a period of time, usually granted by an external system and subject to expiration or reassignment. |
| Invalidation | Action of marking or removing cached data because source data changed, was revoked, or is no longer permitted for use. |

TTL is a validity policy, not just a memory cleanup mechanism. A cache may still hold an expired entry in the heap, yet must refuse to return that entry to the caller. Physical removal can take place afterward.

## 2. Relative TTL vs. absolute expiration time

There are two common ways to represent expiration.

**Relative TTL:** stores the remaining validity duration or a deadline computed from a monotonic clock. This works well for wait intervals within a single runtime lifecycle because it is unaffected by forward or backward adjustments to the system clock.

**Absolute expiration time:** stores a point in time such as an `Instant` or epoch timestamp. This fits when the expiration is determined by an external system, e.g., JWT tokens, credentials, leases, or cache records shared across multiple processes.

| Need | Appropriate representation | Notes on restore |
| --- | --- | --- |
| Wait up to 5 seconds for an operation in a callback | Deadline based on `System.nanoTime()` | Use only within the current operation; do not store a monotonic deadline as long-lived validity across checkpoints. |
| Token with issuer-supplied `exp` | `Instant expiresAt` | Compare with current time after restore; do not auto-extend the token. |
| Cache entry with application-set TTL | Store `fetchedAt` and TTL or `expiresAt` | Recompute remaining time after restore, or evict and reload cache. |
| Lease granted by database/service | Expiry/version defined by the lease grantor | Re-verify with the grantor before continuing side-effecting operations. |
| Scheduled refresh | Store refresh/expiry mark in absolute time or recompute from policy | Cancel or rebuild schedule after restore; do not assume old timers ran during checkpoint. |

Do not confuse `System.nanoTime()` with calendar time. Its value is meaningful only when comparing reads within the same runtime clock domain; it does not represent date/time and cannot be converted into a timestamp shared across machines. When data must survive checkpoints, store an externally meaningful expiry timestamp or sufficient metadata to recompute the deadline.

## 3. Using the right clock for the purpose in Java

### Monotonic clock for intervals

`System.nanoTime()` is suitable for measuring elapsed time and deadlines within an ongoing operation:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);

if (System.nanoTime() - deadline >= 0) {
    throw new TimeoutException("Operation deadline exceeded");
}
```

Subtracting in this way avoids directly comparing two deadline values when the counter might wrap around, provided the measured interval is smaller than the valid range of the comparison. Do not use `nanoTime` values as expiration times stored in a database or sent over the network.

In CRaC, do not assume a `nanoTime` deadline saved in the heap retains the same meaning after restore. Checkpoint duration can render an old deadline unrepresentative of the required interval; the restore implementation and platform clock behavior must also be considered. For TTLs that must count application pause time, store an absolute `expiresAt` and rebuild a new monotonic deadline after restore.

### Wall-clock for absolute expiry

`Instant.now()` or `Clock` enables comparing against a calendar timestamp:

```java
Instant expiresAt = Instant.parse("2026-11-13T10:30:00Z");

if (!Clock.systemUTC().instant().isBefore(expiresAt)) {
    throw new IllegalStateException("Credential has expired");
}
```

The common boundary rule is that if `now >= expiresAt`, the data has expired. Prefer injecting `Clock` into services for easy testing, rather than scattering `Instant.now()` calls throughout code.

The wall clock can be affected by clock skew, NTP adjustments, or host misconfiguration. For server-issued tokens/leases, use a reliable time source, allow an appropriate safety margin, and handle clock drift. Do not extend token validity merely because the local clock might be slow.

## 4. Fixed TTL, sliding TTL, and hard expiry

TTL can be applied under different policies:

| Policy | Calculation | Suitable cases | Risks |
| --- | --- | --- | --- |
| Fixed TTL | Expires after a fixed interval from when data is fetched/created | Configuration, metadata, query result caches | Data can expire even if frequently accessed. |
| Sliding TTL | Each valid access extends the expiration time | Session inactivity timeout or internal cache under specific policies | An entry can live very long if continuously accessed, even if source data changed. |
| Absolute expiry | Expires at a timestamp set by an issuer or business system | Tokens, credentials, certificates, leases, and time-bounded data | Must not shift the expiry mark upon restore or when the cache is read again. |
| Soft TTL + hard TTL | Refresh starting at soft TTL, but allow serving stale only until hard TTL if policy permits | Reference data that can tolerate short staleness | Easy to accidentally serve revoked data if data types are not distinguished. |

For authentication data, access permissions, lock leases, or revocation status, apply hard expiry and check authoritative state. Do not use sliding TTL to turn an expired token into a valid one.

## 5. Why must TTL be rechecked after restore?

A checkpoint preserves memory state at image creation time. It does not freeze external system clocks, nor does it prevent other actors from modifying source data.

For example, an access permissions cache with a 10-minute TTL is loaded at 08:00. The application checkpoints at 08:04. At 08:06, an administrator revokes a user's permissions. The application restores at 08:15. If only the in-heap cache object is used, the application might continue allowing actions based on stale permissions.

Reasons data becomes stale after restore include:

- TTL expired during checkpoint.
- Source data updated, but cache invalidation events were missed.
- Secrets, tokens, or certificates were rotated/revoked.
- Leases expired and were granted to another instance.
- Endpoints or service versions changed.
- Scheduled refresh fell due, but the scheduler did not run while the process was checkpointed.
- A request running before checkpoint produced an old result that got written to the cache after the source system changed versions.

Therefore, restore needs a freshness-checking phase before caches or resources are used to serve requests.

## 6. Storing expiry in cache entries

For cache entries with an absolute expiration, store the value along with metadata about fetch and expiration times:

```java
import java.time.Instant;

public record CacheEntry<V>(
        V value,
        Instant fetchedAt,
        Instant expiresAt,
        long sourceVersion) {

    public boolean isExpired(Instant now) {
        return !now.isBefore(expiresAt);
    }
}
```

When reading the cache:

```java
import java.time.Clock;
import java.util.Optional;

public <V> Optional<V> getFresh(
        CacheEntry<V> entry,
        Clock clock) {
    if (entry == null || entry.isExpired(clock.instant())) {
        return Optional.empty();
    }
    return Optional.of(entry.value());
}
```

If TTL is provided by the source, store `expiresAt` or enough metadata to accurately reconstruct that point in time. Do not reset `fetchedAt = Instant.now()` on restore for an old entry, because doing so inadvertently grants extra TTL.

If the source only provides a relative TTL, clearly determine whether TTL starts from when the source created the data, when the response was emitted, or when the client received the response. When preserving across checkpoints, convert that milestone into `expiresAt` according to an agreed convention.

## 7. Rebuilding monotonic deadlines after restore

A cache may need a monotonic deadline for fast runtime checks. Keep the absolute `expiresAt` as recoverable metadata, then recompute the monotonic deadline when loading the cache after restore:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class RuntimeDeadline {
    private final long deadlineNanos;

    private RuntimeDeadline(long deadlineNanos) {
        this.deadlineNanos = deadlineNanos;
    }

    public static RuntimeDeadline fromExpiry(
            Instant expiresAt,
            Clock clock) {
        Duration remaining = Duration.between(clock.instant(), expiresAt);
        if (remaining.isNegative() || remaining.isZero()) {
            throw new IllegalArgumentException("Entry already expired");
        }
        return new RuntimeDeadline(
                System.nanoTime() + remaining.toNanos());
    }

    public boolean isExpired() {
        return System.nanoTime() - deadlineNanos >= 0;
    }
}
```

In this example, `RuntimeDeadline` is recreated after restore from `expiresAt`. Do not serialize or keep `deadlineNanos` as the source of truth across checkpoints. If time has elapsed, the entry must be evicted or refreshed before use.

For extremely large TTLs, handle overflow when converting `Duration` to nanoseconds and choose an appropriate representation. Practical lifetimes are usually much shorter, yet shared library code should not assume every Duration converts safely.

## 8. Invalidation: eviction, marking stale, and version change

TTL is only a time-based expiration mechanism. Invalidation occurs when an event indicates that data is no longer valid even before TTL ends.

Three common approaches:

1. **Remove:** delete the entry from the cache. The next read must fetch again from the source.
2. **Mark stale:** keep the entry for observation or serving under a stale-while-revalidate policy, without treating the entry as fresh.
3. **Version/generation change:** increment the source's version or generation; an entry is valid only if its version matches the current version.

Example of a cache that can store version:

```java
import java.time.Instant;

public record VersionedValue<V>(V value, long version, Instant expiresAt) {}

public boolean isUsable(
        VersionedValue<?> entry,
        long currentVersion,
        Instant now) {
    return entry != null
            && entry.version() == currentVersion
            && now.isBefore(entry.expiresAt());
}
```

Versions help detect stale entries even when TTL has not expired. This is important when managing access permissions, versioned configurations, or metadata that changes per release.

Not every source has a monotonically increasing version. You can use an ETag, revision, generation id, sequence number, or token version provided by the source system. If no version exists, refresh the snapshot or invalidate the entire relevant cache after restore.

## 9. Invalidation events may be missed during checkpoint

Many systems emit invalidations via message brokers, pub/sub, or event streams. When an application is checkpointed, consumer threads may stop; events emitted during that window may not be processed immediately. Depending on the broker mechanism, messages might be retained, exceed retention, have been acknowledged before checkpoint, or fail to replay if the offset has moved too far.

Do not assume an in-heap listener will automatically receive all events emitted while the process was inactive.

Recovery strategies:

- **Durable event replay:** save the offset/sequence and re-read all events after the processed watermark.
- **Snapshot refresh:** fetch the latest snapshot from the authoritative source after restore, then resume consuming events.
- **Invalidate the entire local cache:** suitable when the cache can be reloaded at acceptable cost.
- **Version check on read:** compare the entry's version against the current version from the source or a metadata service.
- **Generation switch:** increment the cache generation upon restore; entries belonging to old generations are not returned.

When using an event stream, handle the race between fetching a snapshot and subscribing. One approach is to obtain a watermark from the source, register the consumer starting from that watermark, then fetch the corresponding snapshot and apply events in sequence. Another approach is to subscribe first, buffer events, fetch a snapshot with a clear version, and then apply events newer than the snapshot. The specific design depends on the capabilities of the event platform; the goal is not to miss changes occurring between the two steps.

## 10. Clear the cache after restore or refresh partially?

There is no single strategy for every cache. Choose based on the nature of the data, reload cost, and the consequences if stale data is used.

| Data type | Typically suitable strategy | Reason |
| --- | --- | --- |
| Permissions, policy, and revocation status cache | Invalidate or verify version before permitting actions | Stale data can allow unauthorized access. |
| Credentials, access tokens, signing keys | Re-read from authoritative source and check expiry/revocation | Must not extend validity of old secrets. |
| DNS/service discovery | Refresh endpoints or let clients re-resolve under current policy | IPs and instances may change. |
| Versioned configuration cache | Load a new snapshot or compare generations | Must ensure all instances use compatible configuration. |
| Reference data cache tolerant of brief staleness | Soft TTL and background refresh if policy allows | Balances latency and freshness. |
| Pure computation result cache independent of time/changing sources | Can be retained if input data/version remains valid | No need to clear solely because restore occurred. |

For large caches, partial refreshing by key or partition is possible. However, before opening traffic, define which data groups must be fresh and which groups are allowed to be stale for a specific duration.

## 11. Stale-while-revalidate and stale-if-error

Some caches allow continuing to return stale data while refreshing (`stale-while-revalidate`) or continuing to return stale data when the source temporarily fails (`stale-if-error`). These strategies can improve availability, yet must have clear bounds.

Define:

- Soft TTL: when to begin refreshing.
- Hard TTL: absolute point after which serving the entry is no longer allowed.
- Max stale age: maximum allowed staleness duration, if any.
- Data types allowed to be stale: for example, reference catalogs may be acceptable, whereas access permissions are not.
- Behavior when refresh fails: return stale, return an error, or transition the application to `NOT_READY`.

Do not use stale-while-revalidate for expired credentials, revoked permissions, exclusive leases, or data requiring strong consistency. After restore, if the current policy or version has not been verified, reject sensitive operations instead of using stale data.

## 12. Leases, distributed locks, and fencing tokens

A lease is the right to use a resource for a period of time. A process may hold a lease before checkpoint, yet the lease expires while it is paused. During that time, the coordination system may grant the lease to another process.

After restore, the old process must not assume it still owns the lease. It must verify or acquire a new lease before continuing side-effecting operations.

For distributed locks, checking expiration only on the client is insufficient. An old process could wake up after its lease expired and keep writing data. A **fencing token** protects the resource: each time a new lease is granted, the system issues an increasing token/sequence number; the target storage or service rejects operations carrying a token older than the highest accepted token.

Example logic:

```text
Instance A receives lease with fencing token 41
          |
          v
       Checkpoint
          |
          v
Lease A expires; Instance B receives token 42
          |
          v
Instance A restores and tries to write with token 41
          |
          v
Storage rejects token 41 because token 42 was accepted
```

The fencing token must be checked at the system actually protecting the data, not only on the client. If checked only in the old process, an already-sent request or a running background task could bypass the local check.

## 13. Scheduling refreshes and timers after restore

A scheduled task created before checkpoint may be waiting for refresh time or in the middle of a refresh. When the process is checkpointed, do not assume the scheduler continues running on schedule while the application is paused.

Before checkpoint:

- Stop creating new refresh jobs.
- Wait for or cancel in-flight refresh tasks subject to a deadline.
- Record necessary version/expiry information, without relying solely on timer state in the heap.

After restore:

- Recompute current time and identify expired entries.
- Immediately refresh data that must be fresh.
- Recreate the refresh schedule based on `expiresAt` or current policy.
- Open traffic only after critical data/credentials have been verified.

If a task is already overdue upon restore, it usually needs to run the refresh immediately or transition to `NOT_READY`; do not simply schedule anew from the restore time and inadvertently extend stale data's validity.

## 14. Example Resource invalidating cache after restore

The example below illustrates a Resource holding a local cache. Before checkpoint, it stops background refreshes and waits for running tasks to finish. After restore, it clears the cache and loads a new snapshot from an authoritative source before opening for requests.

```java
import org.crac.Context;
import org.crac.Resource;

public final class CacheResource implements Resource {
    private final LocalCache cache;
    private final SnapshotProvider snapshotProvider;
    private final RefreshScheduler refreshScheduler;

    public CacheResource(
            LocalCache cache,
            SnapshotProvider snapshotProvider,
            RefreshScheduler refreshScheduler) {
        this.cache = cache;
        this.snapshotProvider = snapshotProvider;
        this.refreshScheduler = refreshScheduler;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        refreshScheduler.stopAcceptingRefreshes();
        refreshScheduler.awaitCurrentRefreshWithTimeout();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        cache.invalidateAll();
        CacheSnapshot snapshot = snapshotProvider.fetchCurrentSnapshot();
        cache.load(snapshot);
        refreshScheduler.startFrom(snapshot.nextRefreshAt());
    }
}
```

`LocalCache`, `SnapshotProvider`, `RefreshScheduler`, and `CacheSnapshot` are application abstractions. In a real implementation, `fetchCurrentSnapshot()` requires bounded timeout/retry, the snapshot requires a version or watermark, and `load()` must complete before traffic opens. If the source is unreachable, the callback should report an error or keep the component `NOT_READY` according to policy, instead of silently retaining stale cache.

If checkpoint is aborted after `beforeCheckpoint` already stopped the scheduler, the original process may resume without passing through `afterRestore`. The lifecycle coordinator needs a rollback/resume scheduler branch for aborts, or must ensure the application stays `NOT_READY` until the refresh schedule is restored. Do not use `afterRestore` as a rollback callback for a failed checkpoint.

For a cache too large to clear completely, increment the generation and reload only necessary partitions. However, every read must check generation/version to avoid returning stale entries.

## 15. Avoiding overwriting newer data with stale refresh results

A race condition can happen when a refresh starts before checkpoint or before invalidation, yet completes afterward. The old result can overwrite newer data.

Example:

1. Refresh A reads version 10.
2. The source updates to version 11 and emits invalidation.
3. Refresh B reads version 11 and writes to the cache.
4. Refresh A completes late and overwrites version 11 with version 10.

To avoid this, the cache should accept only results with a newer version or use generation-based compare-and-set. You can cancel refresh tasks before checkpoint and drain before closing resources; still, keep a version guard because cancellation does not guarantee the task stopped immediately.

Example:

```java
public void putIfNewer(CacheSnapshot incoming) {
    current.updateAndGet(existing -> {
        if (existing == null || incoming.version() >= existing.version()) {
            return incoming;
        }
        return existing;
    });
}
```

In a distributed system, versions must be meaningful relative to the source and must not be incremented independently per instance when global comparison is needed. Use a revision, sequence, or generation issued by the authoritative source.

## 16. Common errors after restore

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Cache returns expired data | Entry remains in heap and code only checks null | Check `expiresAt` on read; invalidate expired entries. |
| Token rejected even though object exists | Token TTL expired or token was revoked while process was checkpointed | Request a new token and verify expiry/revocation before use. |
| Old access permissions still applied | Invalidation event missed or cache policy does not check version | Replay events, refresh policy snapshot, or fail closed. |
| Background refresh does not run after restore | Scheduler/task state not restarted properly | Rebuild schedule from expiry metadata and run overdue refresh immediately. |
| Cache gets refreshed then becomes stale again | Old refresh task overwrites newer version | Use a version/generation guard and cancel/drain old tasks. |
| Old lease keeps writing data | Restored process did not verify lease or storage did not check fencing token | Acquire a new lease and validate fencing token at the target resource. |
| Cache is stale only on some instances | Invalidation stream, offset, or snapshot inconsistent across instances | Reconcile watermarks/versions and monitor consumer lag. |
| Application fails to restore due to transient refresh source error | Callback depends on external source without bounded retry/deadline | Use bounded timeout/backoff and keep component `NOT_READY` until mandatory data is verified. |

## 17. Observing TTL and invalidation

Record metadata to know why an entry was used or rejected:

- Appropriately masked/hashed cache key or identifier; avoid logging sensitive data.
- `fetchedAt`, `expiresAt`, remaining TTL, and latest refresh timestamp.
- Source version, generation, or event sequence.
- Checkpoint/restore timestamps and restore attempt id.
- Counts of expired entries, invalidated entries, and refreshed entries after restore.
- Invalidation event offset/watermark and consumer lag.
- Counts of refresh failures, timeouts, and retries.
- Number of reads rejected due to stale/expired data.
- Readiness status while mandatory caches are being refreshed.

Useful metrics include cache hit/miss, expired-entry count, stale-served count (if policy permits), refresh duration, refresh failure, invalidation lag, and version mismatch. Avoid using cache keys or user IDs as high-cardinality metric labels.

## 18. Testing TTL and invalidation across checkpoint–restore

An integration test should simulate elapsed time and external data changes:

1. Load a cache entry with a known TTL and record `fetchedAt`, `expiresAt`, and version.
2. Create a checkpoint while the entry is still valid.
3. While the process is checkpointed, wait past expiry or update the source version and emit an invalidation event.
4. Restore the application.
5. Verify that expired entries are not returned and the cache is refreshed or invalidated.
6. Verify that invalidation events emitted during checkpoint are replayed or covered by the new snapshot.
7. Verify that an old refresh task cannot overwrite data with a newer version.
8. For leases, verify that the old process cannot write after the lease is granted to another instance; check fencing token at the target storage/service.
9. Verify that the application does not open sensitive traffic before mandatory data has been verified.

Additional cases:

- Restore before and after the hard TTL mark.
- Host clock skewed or adjusted.
- Skew between token issuer/time source and local clock.
- Delayed, duplicate, or out-of-order invalidation events.
- Secret/config version changed multiple times during checkpoint.
- Secret provider or snapshot source temporarily unreachable.
- Scheduler has overdue tasks at restore time.
- Old refresh completes after a newer refresh already wrote to cache.
- Cache allows stale-while-revalidate but disallows stale after hard expiry.

Inject `Clock` to test expiry logic with simulated time rather than waiting many real minutes. However, verifying CRaC callbacks, schedulers, and event replay still requires integration testing on the target runtime and deployment environment.

## 19. Implementation checklist

- [ ] Each data type has a clear TTL/hard expiry policy.
- [ ] Know whether TTL starts from source creation, client receipt, or cache load time.
- [ ] Use `Instant`/timestamps for externally meaningful expiry; use `nanoTime` for elapsed time within the current runtime.
- [ ] Do not rely on a monotonic deadline saved in the heap as the source of truth across restore.
- [ ] After restore, recompute deadlines or invalidate caches requiring refresh.
- [ ] Check expiry at usage time, not only when background cleanup runs.
- [ ] Permission, credential, token, and lease data have hard expiry/revocation checks.
- [ ] Have version/generation or snapshot mechanisms to detect missed invalidations.
- [ ] Replay events from a durable watermark or refresh snapshot after restore.
- [ ] Handle races between subscribe and snapshot so no events are missed.
- [ ] Prevent old refreshes from overwriting newer data.
- [ ] Cancel/drain scheduled tasks before checkpoint and rebuild schedules after restore.
- [ ] Apply stale-while-revalidate only to data permitted to be stale and with a hard TTL.
- [ ] Re-verify distributed leases; protect write operations with fencing tokens when needed.
- [ ] Apply timeouts/deadlines to refreshing data after restore.
- [ ] Open traffic only when mandatory data is fresh or verified valid.
- [ ] Have metrics/logs for expiry, invalidation lag, version mismatch, and refresh failures.
- [ ] Tested TTL expiration and invalidation occurring during checkpoint.

## 20. Conclusion

TTL defines how long data is allowed to be used; expiry is the point when data becomes invalid; invalidation handles cases where data must be removed or marked stale before TTL ends. In CRaC, cache state is restored from an earlier point in time while clocks, secrets, permissions, leases, and source data continue changing.

Store externally meaningful absolute expiry for data surviving across checkpoints, use the monotonic clock for runtime deadlines, check freshness on read, and reconcile caches/versions/events after restore. For credentials, permissions, and leases, fail closed until current status is verified. For refreshable caches, invalidate or load a fresh snapshot, rebuild schedulers, and prevent old refresh results from overwriting newer data. Consequently, the application will not confuse data still residing in the heap with data that is still valid.
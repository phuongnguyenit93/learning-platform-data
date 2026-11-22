# Request deadlines, login sessions, and expired tokens

A Java application can be checkpointed after startup and warm-up, then restored seconds, minutes, or longer afterward. While the process is not running, the outside world keeps changing: requests reach their deadlines, sessions get revoked, access tokens expire, refresh tokens are rotated, distributed leases hit their TTL, and certificates can reach their expiration time.

Therefore, time state stored in the heap cannot always be considered still valid after restore. That an object still exists does not mean its validity period is extended by the time the process was stopped.

When integrating CRaC (Coordinated Restore at Checkpoint), the application must clearly define the semantics of each kind of deadline:

- Absolute time continues elapsing during checkpoint.
- Time intervals measured within a single execution run of the process.
- Deadlines/expirations managed by external systems.
- Durations intentionally paused while the application is inactive.

This lesson presents how to manage deadlines, sessions, and tokens so the application does not continue using expired state after checkpoint/restore.

## 1. Time keeps passing while the application is checkpointed

Checkpointing saves the state of a process at a point in time. It does not freeze the clock of the operating system, database server, authentication server, or remote services.

Example:

1. The application receives an access token valid until 10:30.
2. The application creates a checkpoint at 10:20.
3. The image is kept in storage for 25 minutes.
4. An instance is restored at 10:45.
5. The token object in the heap still exists, yet the token has expired.

If the application only checks a boolean variable such as tokenLoaded or authenticated, it may continue calling APIs with the old token. The remote service will reject the request or require re-authentication.

Similarly, a request with deadline 10:25 should not continue running after restoring at 10:45. A session with a 30-minute idle timeout may have been revoked by the authentication system or session store. A lease with a 60-second TTL may have been granted to another process.

CRaC does not automatically extend those deadlines. The application must re-evaluate them against the current time and authoritative state from the relevant systems.

## 2. Distinguishing absolute time and monotonic time

Java has two time concepts commonly used for two different purposes.

### 2.1 Wall-clock time: calendar point in time

APIs such as Instant.now() or Clock.systemUTC() provide points in time from the system clock, typically represented in UTC.

Example:

~~~java
Instant expiresAt = Instant.parse("2026-11-13T10:30:00Z");

if (!Instant.now().isBefore(expiresAt)) {
    // Deadline has arrived or already passed.
}
~~~

Absolute points in time are suitable for:

- Tokens with an exp field.
- Server-defined session expiration.
- Request deadlines propagated across services.
- Contract, lease, or reservation expirations with an absolute end timestamp.
- Timestamps stored in a database or message.

Instant can be stored in a checkpoint image because it is an epoch-based point-in-time value. After restore, comparing Instant against current time indicates whether the deadline has passed, provided system clocks are synchronized and deadline semantics are properly defined.

### 2.2 Monotonic time: measuring intervals

System.nanoTime() is designed to measure elapsed time within the JVM. The returned value is not a calendar timestamp and has no meaningful epoch origin.

~~~java
long started = System.nanoTime();

// Perform an operation.

long elapsedNanos = System.nanoTime() - started;
~~~

Use nanoTime() for:

- Measuring latency.
- Internal timeouts within a single execution run.
- Computing the interval between two events.
- Avoiding effects of wall clock adjustments during measurement.

Do not save a nanoTime value and treat it as a timestamp comparable against another machine's clock or another execution environment. The origin of nanoTime is arbitrary; only the difference between reads within the same execution context is meaningful according to the API contract.

When the application restores on a different host, do not assume the target host's monotonic clock origin matches the source host's. Even when restoring on the same host, verify runtime semantics and do not use a stored nanoTime value as an absolute deadline.

### 2.3 Converting a deadline into storable data

A safe approach is to store an absolute expiration timestamp, then recompute the remaining time after restore:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class Deadline {

    private final Instant expiresAt;

    public Deadline(Instant expiresAt) {
        this.expiresAt = expiresAt;
    }

    public boolean isExpired(Clock clock) {
        return !clock.instant().isBefore(expiresAt);
    }

    public Duration remaining(Clock clock) {
        Duration duration =
                Duration.between(clock.instant(), expiresAt);

        return duration.isNegative()
                ? Duration.ZERO
                : duration;
    }
}
~~~

If the deadline passed during checkpoint, remaining() returns Duration.ZERO. The application can reject the work or mark it expired rather than continuing to process it.

For timeouts that need accurate measurement within one run, you can convert the remaining time into a nanoTime deadline after restore:

~~~java
Duration remaining = deadline.remaining(clock);

if (remaining.isZero()) {
    throw new TimeoutException("Request deadline expired");
}

long localDeadline =
        System.nanoTime() + remaining.toNanos();
~~~

The localDeadline value is for the current execution run only. Do not save it for use across the next checkpoint.

### 2.4 Do not use Duration alone as a long-lived deadline

Duration only represents the length of an interval. For example, Duration.ofMinutes(15) does not tell you when those 15 minutes started.

If only a Duration is stored in the heap and restore occurs 40 minutes later, the application cannot tell whether checkpoint time should count toward those 15 minutes.

Store one of two forms depending on semantics:

- An absolute timestamp expiresAt if time continues elapsing during checkpoint.
- A remaining duration remaining if business logic intentionally pauses the clock during checkpoint.

Do not use one form for both policies.

## 3. Deciding deadline semantics

Before writing code, determine whether checkpoint time counts toward the deadline.

| Deadline type | Usually counts checkpoint time? | Appropriate storage |
|---|---|---|
| HTTP request deadline | Yes | Instant deadline propagated across services |
| Access token exp | Yes | Absolute expiration timestamp from token or token response |
| Refresh token expiration | Yes | Expiration managed by the authorization server |
| Session idle timeout | Yes, based on activity recorded by the server | Session store/server is the authoritative source |
| Distributed lease TTL | Yes | Lease expiration and fencing token from the lease-granting system |
| Reservation or payment authorization | Yes | Absolute expiration from the business service |
| Pausing an internal task during maintenance | Possibly not | Store remaining duration and restart intentionally |
| Latency measurement duration | Not applicable as a deadline | nanoTime within a single measurement |

For example, a payment deadline is typically not extended merely because an instance was checkpointed. If a transaction must complete before a specific point in time, that point in time stays fixed.

Conversely, an internal batch job might be designed to pause when the system stops running. In that case, the application can save remaining time before checkpoint and recreate the timer after restore. This is a business policy that must be explicitly chosen.

## 4. Request deadlines and in-flight tasks

A distributed request often traverses multiple services. If each service creates a fresh timeout on its own, total processing time can exceed the client's deadline.

Example:

~~~text
Client deadline: 12:00:05
  -> API Gateway
  -> Order Service
  -> Payment Service
  -> Inventory Service
~~~

Each service needs to use the remaining deadline, not grant a new full timeout interval.

### 4.1 Propagating absolute deadlines

The deadline can be propagated as a UTC timestamp in an internal header, such as a system-defined header:

~~~text
X-Request-Deadline: 2026-11-13T12:00:05Z
~~~

This header name is only an example; use a consistent convention across the system. Upon receiving a request, the service parses the timestamp into an Instant and computes remaining time using Clock.

~~~java
Instant deadline = Instant.parse(deadlineHeader);
Duration remaining = Duration.between(clock.instant(), deadline);

if (remaining.isNegative() || remaining.isZero()) {
    throw new TimeoutException("Request deadline expired");
}
~~~

If the service is restored after the deadline has passed, the request must be rejected or terminated according to API rules. Do not set a new deadline starting from restore time, because that extends the deadline requested by the client.

### 4.2 Storing the deadline with the work item

If the application has an internal queue or pending workflow, store the deadline alongside the work metadata:

~~~java
public record PendingWork(
        String workId,
        Instant deadline,
        String idempotencyKey) {
}
~~~

After restore, the worker checks the deadline before picking up the work:

~~~java
if (!clock.instant().isBefore(work.deadline())) {
    markExpired(work.workId());
    return;
}

process(work);
~~~

The check must happen right before any significant side effect. A single check when enqueueing the work is not enough if the item may wait in the queue for a long time.

### 4.3 Canceling expired work

If a request's deadline has expired, the application must:

- Stop steps that have not started.
- Cancel downstream calls if the client or library supports cancellation.
- Do not resend an expired write operation merely because the worker just resumed.
- Release resources and update workflow state.
- Return an appropriate error if a response channel is still open.

Not every operation already sent to an external service can be canceled. If a payment request might have been processed before checkpoint, query its status or use an idempotency key before retrying. A client timeout does not prove the server-side operation failed.

### 4.4 Do not continue a request merely because its thread was restored

A thread may resume from checkpointed state, yet the business deadline may already have expired. Before performing an I/O step or side effect after restore, confirm the request is still valid.

For long requests, you can choose not to checkpoint while requests are still in flight: set readiness to false, drain requests, and only then create the image. If the application supports saving in-progress workflows, persist state durably and recover the workflow from that state against the original deadline.

## 5. Login sessions and idle timeouts

Login sessions may be managed in application memory, a database, Redis, an identity provider, or a dedicated session service.

The checkpoint image saves only the Java process state. It does not freeze an external session store.

### 5.1 Sessions can expire while the process is stopped

Suppose a session has a 30-minute idle timeout. The application checkpoints after 5 minutes of inactivity and restores 40 minutes later.

If the external session store kept running, the session may have expired and been deleted. A session object in the heap or a cookie in a request does not prove the session is still valid.

After restore, the application should:

- Reconnect to the session store.
- Check that the session ID still exists and has not been revoked.
- Check idle timeout and absolute expiration.
- Verify the session has not been logged out or revoked.
- Accept the session only if server-side state is still valid.

Do not recreate the session automatically merely because a session object is already in the heap.

### 5.2 Idle timeout and absolute timeout differ

| Timeout type | Meaning | Example |
|---|---|---|
| Idle timeout | Expires if there is no activity within an interval | 30 minutes with no valid request |
| Absolute timeout | Expires at a fixed point in time, regardless of activity | Session ends after 12 hours |
| Sliding expiration | Expiration shifts forward on valid activity | Each valid request updates expiration time |
| Revocation | Session is actively revoked | User logs out or administrator locks account |

If a session was checkpointed in the heap with an old lastAccessedTime, do not set lastAccessedTime to the current time upon restore just to keep the session alive. Doing so can inadvertently extend the session and violate security policy.

Sliding expiration should only be updated by valid user activity according to system rules, not by the process being restored.

### 5.3 Cookies are not sessions

Cookies may contain a session ID, token, or identity information. Cookie lifetime in the browser and session lifetime on the server are two distinct policies.

- A cookie may still exist in the browser while the server session has expired.
- The server session may still exist while the cookie has expired or been deleted.
- Restoring the application does not cause browsers to automatically receive new cookies.
- A revoked session ID does not become valid merely because it remains in the heap.

The application must verify session state with the authoritative manager.

### 5.4 Do not checkpoint inconsistent session state

If the session store is updated concurrently with an in-heap session object, a checkpoint may capture the state mid-change. Synchronize session operations or checkpoint only at a safe point.

With an external session store, re-read necessary state after restore rather than assuming the in-heap cache is always up to date. If session state can be modified by multiple instances, the server-side store must be the authoritative source.

## 6. Access tokens and exp expiration

Access tokens are typically used to call APIs or access resources. A token may be a JWT or an opaque token. Regardless of format, expiration is governed by the authorization server or resource server.

### 6.1 JWT exp

In JWT, the exp claim represents the time when the token expires as a NumericDate, i.e., seconds since the Unix epoch in UTC.

A resource server must not accept a token at or after its expiration time, except for a small leeway if policy allows for handling clock skew.

Common time claims:

| Claim | Meaning |
|---|---|
| iat | Time when the token was issued |
| nbf | Token is not valid before this time |
| exp | Token expires at this time |
| auth_time | Time when the user authenticated, if provided by the issuer |

After restore, check both exp and nbf if the application validates JWTs itself. However, if the token is verified at a resource server, that server remains the final authority.

### 6.2 OAuth expires_in

In OAuth 2.0, a token response usually includes an expires_in field representing the access token's validity duration in seconds from when the token response was generated.

Upon receiving the response, the application should convert that duration into an absolute expiration timestamp:

~~~java
Instant receivedAt = clock.instant();
Instant expiresAt = receivedAt.plusSeconds(expiresIn);
~~~

You can subtract a safety margin to avoid starting requests right near token expiration:

~~~java
Instant refreshAt = expiresAt.minusSeconds(30);
~~~

The margin depends on latency, clock skew, and issuer policy. Do not hard-code a single number for all systems.

If only expiresIn=3600 is saved in the image and the process restores 50 minutes later and starts counting 3600 seconds from scratch, the application has inadvertently extended the token by 50 minutes. Save expiresAt or obtain fresh token state from the token provider after restore.

### 6.3 Checking tokens before use

A client can check expiration before sending a request:

~~~java
public boolean needsRefresh(
        Instant expiresAt,
        Clock clock,
        Duration refreshSkew) {

    return !clock.instant()
            .plus(refreshSkew)
            .isBefore(expiresAt);
}
~~~

If the token has expired or is close to expiring, refresh according to the issuer's protocol. If refresh fails, do not send requests with the old token and do not mark the client as authenticated.

Do not rely on a pre-checkpoint boolean like authenticated=true. Authentication status must be evaluated against the current token and server-side policy.

### 6.4 Opaque tokens

An opaque token does not contain an exp claim that the client can read directly. The client typically receives expires_in in the token response or must query the authorization server/resource server for status.

Do not attempt to parse an opaque token as a JWT. Use metadata returned by the issuer and handle 401/invalid_token responses according to system standards.

## 7. Refresh tokens and rotation after restore

A refresh token usually has a longer lifetime than an access token. It is used to request new access tokens, yet it can be revoked, expire, or be rotated.

### 7.1 Refresh tokens may have expired or been revoked

If a checkpoint image contains a refresh token, that token may no longer be valid upon restore because:

- Absolute expiration has been reached.
- The user logged out or revoked consent.
- An administrator revoked the session.
- The issuer rotated the refresh token.
- Reuse detection policy triggered.
- Credentials or client registration changed.

The application should treat a refresh token as a credential that must be re-verified with the authorization server. Do not assume a refresh token in the heap is always still usable.

### 7.2 Refresh token rotation and multiple restores

A specific risk arises when one image is restored into multiple instances.

Suppose the image contains refresh token R1. Two instances A and B are restored from the same image:

~~~text
Checkpoint image contains R1
       /          \
      v            v
 Instance A     Instance B
      |            |
 Refresh R1     Refresh R1
      |            |
 Issuer issues R2  Issuer sees R1 already used
      |            |
 Succeeds        May detect reuse/revoke family
~~~

With refresh token rotation, the authorization server may issue a new token on each use and invalidate the old one. Some issuers also detect reuse of an old token and revoke the entire token family.

Thus, two replicas restoring the same refresh token can create a race condition and break refresh capability for the entire group.

Appropriate design approaches:

- Do not place shared refresh tokens inside an image that gets cloned.
- Have each instance obtain its own credentials after restore via workload identity or the platform's credential-issuing mechanism.
- Use a token broker or single component owning the refresh token and synchronizing refreshes.
- If supported by the issuer, use concurrency-controlled refreshing and persist newly rotated tokens atomically.
- Handle invalid_grant or reuse detection with a re-authentication flow rather than infinitely retrying the old token.

Review the specific policy of the authorization server. Not every issuer implements rotation or reuse detection in the same way.

### 7.3 Storing rotated tokens safely

When refresh succeeds and the issuer returns a new refresh token, the application must update token state atomically. If a crash occurs after the issuer rotated the token but before the application persisted the new one, the old token may no longer be reusable.

If tokens are stored in an external store, use versioned updates or compare-and-set to avoid overwriting a newer token with an older one from another instance.

Do not log access tokens, refresh tokens, or authorization headers. Because a checkpoint image contains the heap, it may contain credentials; enforce access control, encryption, retention limits, and cleanup procedures for old images according to security policy.

## 8. Clock skew and time sources

Services may run across multiple hosts whose clocks are not completely identical. If issuer and client clocks differ, a token may be treated as not yet valid or prematurely expired.

### 8.1 Synchronizing system time

Use the platform's time synchronization mechanism, typically NTP or a cloud time synchronization service. After restoring on a different host, ensure the target host's clock is synchronized.

Do not manually adjust the application clock to make tokens valid. If clock skew occurs, handle it according to the leeway policy supported by the issuer and resource server.

### 8.2 Leeway must be bounded

A small leeway can help handle clock differences when checking exp or nbf. However, too large a leeway extends how long a token is accepted and weakens expiration policy.

If the server validates JWTs, use a consistent configuration across resource servers. If the client needs to refresh early, use a dedicated refresh skew to avoid sending tokens right on the edge of expiration.

### 8.3 Do not use local timestamps as the authoritative source for all sessions

If a session or token is managed by an external service, the external state is the authoritative source. Local timestamps can optimize refresh decisions, yet the server can still reject revoked tokens or sessions.

Handle responses such as 401, invalid_token, invalid_grant, or session_not_found according to protocol. Passing a local expiration check does not guarantee server state has not changed.

## 9. Distributed leases, locks, and reservations

Expirations do not occur only in authentication. An application may hold a lease to process a job, act as leader, or protect shared resources.

For example, a worker acquires a lease with a 60-second TTL. After 10 seconds, the process is checkpointed for 5 minutes. Upon restore, the lease has expired and may have been acquired by another worker.

Do not continue operating merely because the Lease object in the heap still says state=ACTIVE.

### 9.1 Checking and reacquiring leases

After restore:

1. Re-read the lease from the lease-granting system.
2. Check expiresAt or current TTL.
3. Verify owner and fencing token.
4. If the lease has expired, stop the work.
5. If continuation is needed, reacquire the lease via an atomic operation.
6. Perform side effects only after ownership is verified.

### 9.2 Fencing tokens

A lease can expire while the old worker keeps running if it does not know it lost ownership. A fencing token enables the target system to reject operations from an old owner.

Each time a lease is granted, the system increments a token or generation. The protected resource records the latest token and rejects requests carrying an older token.

After restore, do not use a checkpointed fencing token if the lease has expired or been reassigned. Obtain the current token from the lease service before proceeding.

### 9.3 Reservations and payment authorizations

Seat reservations, inventory holds, or payment authorizations can expire while an image is stored. The application must query the business service for current state before confirming or continuing.

A Reservation object in the heap is not proof that inventory is still held. Use idempotency keys and status queries to avoid unintentionally creating duplicate reservations or payments.

## 10. Schedulers, timers, and periodic tasks

A ScheduledExecutorService or scheduler may hold tasks with delays and internal state. Do not assume every timer will have the desired semantics when the process checkpoints and restores.

### 10.1 Store the run timestamp, not only the delay

If a report must run at 02:00 UTC, save the Instant of the next run. After restore, recompute the remaining time:

~~~java
Duration delay = Duration.between(
        clock.instant(),
        nextRunAt);

if (delay.isNegative() || delay.isZero()) {
    runOrSkipAccordingToPolicy();
} else {
    scheduler.schedule(
            this::runJob,
            delay.toMillis(),
            TimeUnit.MILLISECONDS);
}
~~~

If the job is overdue, decide whether to catch up, skip, or coalesce multiple runs depending on business logic. Do not automatically execute all missed runs if they have side effects.

### 10.2 Avoiding running a job twice

If the scheduler saved job state in the heap and afterRestore registers the same job again, the application may run two copies. Manage registration with a clear owner, cancel or rebuild the scheduler per lifecycle, and use job IDs/leases to prevent duplicate runs across replicas.

### 10.3 Fixed rate and fixed delay

- fixedRate attempts to maintain a periodic schedule.
- fixedDelay measures the pause interval after the previous run completes.

After checkpoint, multiple fixedRate runs may have been missed. Decide whether to catch up or skip. For fixedDelay, determine when the previous run actually completed and whether checkpoint time counts toward the next delay.

Do not let the scheduler's implicit timing logic dictate business policy.

## 11. Managing expirations inside a CRaC Resource

Resource callbacks can help the application prepare before checkpoint and re-verify after restore. Not every token or deadline needs its own Resource; have a lifecycle management component per dependency group.

Example:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CredentialResource implements Resource {

    private final Clock clock;
    private final TokenProvider tokenProvider;
    private final AtomicReference<AccessToken> token =
            new AtomicReference<>();

    public CredentialResource(
            Clock clock,
            TokenProvider tokenProvider) {
        this.clock = clock;
        this.tokenProvider = tokenProvider;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // Do not extend the token merely to checkpoint.
        // May stop the refresh task and save non-sensitive state.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        AccessToken current = token.get();

        if (current == null
                || !clock.instant().isBefore(current.expiresAt())) {
            token.set(tokenProvider.acquireOrRefresh());
        } else {
            tokenProvider.validateOrRefreshIfNeeded(current);
        }
    }
}
~~~

AccessToken and TokenProvider here are application abstractions. In practice, do not write a custom refresh protocol if an OAuth/OIDC library already handles rotation, concurrency, and error handling. The example only illustrates that after restore, expiration must be checked and valid credentials obtained.

If the token provider requires network access, the afterRestore callback may fail because the authentication service is not yet ready. In that case, the application must keep readiness false or use a controlled asynchronous recovery mechanism if allowed by the runtime/framework. Never pretend authentication succeeded.

### 11.1 Do not wait indefinitely on the network inside callbacks

Callbacks must have finite timeouts. If the authorization server does not respond, a reconnecting callback can stall restore indefinitely or cause it to fail.

Use connect timeouts, request timeouts, bounded retries, and backoff. If the application supports starting in a not-ready state and recovering afterward, implement an explicit lifecycle rather than blocking the callback forever.

### 11.2 Avoid non-idempotent side effects in callbacks

Do not create new sessions, register new webhooks, or issue new credentials in afterRestore if that operation could repeat when restore retries or multiple instances restore together.

If per-instance credentials must be created, use an idempotency key or the instance's workload identity. Store instance identity metadata in a way that is not accidentally shared across replicas.

## 12. Testing time without real waiting

Use Clock injection to deterministically test deadlines and token expiry. Clock.fixed() lets you simulate the current point in time.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock checkpointTime = Clock.fixed(
        Instant.parse("2026-11-13T10:00:00Z"),
        ZoneOffset.UTC);

Clock restoreTime = Clock.fixed(
        Instant.parse("2026-11-13T10:45:00Z"),
        ZoneOffset.UTC);

Instant expiresAt =
        Instant.parse("2026-11-13T10:30:00Z");

boolean validAtCheckpoint =
        checkpointTime.instant().isBefore(expiresAt);

boolean validAfterRestore =
        restoreTime.instant().isBefore(expiresAt);

// validAtCheckpoint = true
// validAfterRestore = false
~~~

You can write tests for cases such as:

- Token valid before checkpoint but expired after restore.
- Request deadline elapsed during checkpoint.
- Session revoked while the application was not running.
- Refresh token rotated by another instance.
- Lease expired and reassigned to a new worker.
- Scheduler with multiple missed runs.
- Local clock skewed relative to the issuer.
- A credential that is not yet expired but has been revoked.

For code using nanoTime(), separate time calculation from business logic and use a clock/ticker abstraction for testing. Do not use Clock.fixed() to mock nanoTime directly; the two clock types have different semantics.

## 13. Operational scenarios to handle

| Scenario after restore | Appropriate behavior |
|---|---|
| Request deadline still valid | Compute remaining time and continue if workflow supports it |
| Request deadline passed | Cancel or mark expired; do not create a new deadline |
| Access token near expiration | Refresh according to policy and concurrency control |
| Access token expired | Do not send old token; refresh or re-authenticate |
| Refresh token revoked | Require re-authentication or issue new credentials |
| Server session expired | Reject session and require re-login |
| Session not expired yet but logged out/revoked | Honor the server's revocation state |
| Lease expired | Reacquire and obtain a new fencing token |
| Reservation expired | Query status and redo idempotently |
| Scheduled job overdue | Catch up, skip, or coalesce per policy |
| Large clock skew | Keep status undetermined and resolve via authoritative time source |

An application should have an explicit state for each dependency: VALID, EXPIRED, REVOKED, REFRESHING, or UNKNOWN. State UNKNOWN should not be treated as VALID. If verification cannot succeed due to a network failure, keep readiness false for functionality depending on that credential.

## 14. Common mistakes

### Storing expiresIn and counting again from zero after restore

expiresIn is the duration at the time the token was received. If restore occurs after that duration has elapsed, restarting from scratch artificially extends validity. Store expiresAt instead.

### Using nanoTime as a timestamp

nanoTime is not epoch time. Do not store this value as a deadline comparable across different hosts or across a different execution lifecycle.

### Trusting a checkpointed authenticated boolean

Tokens can expire or be revoked. Re-verify credentials after restore and before use.

### Extending a session merely because of restore

Restore is not user activity. Do not update lastAccessedTime or sliding expiration merely because the process started running again.

### Sharing a refresh token in a cloned image

Multiple instances may concurrently use a rotated refresh token. Use per-instance credentials or a single token owner with concurrency control.

### Continuing to hold an old lease

A lease can expire during checkpoint. Revalidate ownership and fencing token before side effects.

### Re-running every scheduler task

Overdue jobs do not necessarily all need to run. Define a catch-up policy and ensure no duplicate execution.

### Using the local clock as the final verification authority

Clock skew, revocation, and server-side changes can make local state stale. Authoritative services still decide whether a token/session/lease is valid.

### Logging tokens or session secrets

Both checkpoint images and logs can contain sensitive data. Do not log credentials, and protect images with access control, encryption, and retention policies.

## 15. Implementation workflow

When onboarding a Java application with deadlines, sessions, and tokens to CRaC, you can apply the following sequence:

**Step 1 — Inventory expirations.** Locate request timeouts, workflow deadlines, session TTLs, access/refresh tokens, leases, reservations, and schedulers.

**Step 2 — Choose semantics.** Decide whether checkpoint time counts toward each expiration. Prefer absolute deadlines for requests, tokens, and leases managed by external systems.

**Step 3 — Separate wall clock and monotonic clock.** Use Instant/Clock for expiration timestamps and nanoTime for elapsed-time measurement within a single execution run. Do not persist nanoTime deadlines across restore.

**Step 4 — Re-verify external state.** After restore, check the session store, token issuer, lease service, and reservation service. Do not treat objects in the heap as the final source of truth.

**Step 5 — Handle refreshes under control.** Manage rotation, concurrency, idempotency, and per-instance credentials. Avoid sharing refresh tokens inside an image restored across multiple replicas.

**Step 6 — Recover schedulers and workflows.** Recompute remaining time from the original deadline; explicitly decide whether to catch up, skip, or continue.

**Step 7 — Keep readiness accurate.** Do not accept traffic or perform credential-dependent side effects until expirations and ownership are verified.

**Step 8 — Test time behavior.** Use a fixed Clock to simulate elapsed time, and also test real restores on the target environment along with revocation/rotation scenarios.

**Step 9 — Observe and trace.** Log timestamps, checkpoint ID, instance ID, non-sensitive token issuer or session references, refresh outcomes, and expiration reasons. Never log secrets.

## References

- [Java API — Instant](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/Instant.html): absolute point in time relative to epoch.
- [Java API — Clock](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/Clock.html): replaceable time source for testing.
- [Java API — System.nanoTime()](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.html#nanoTime()): measuring elapsed time using a monotonic clock.
- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore model and application lifecycle.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): managing Resources via beforeCheckpoint and afterRestore.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): NumericDate and claims iat, nbf, exp.
- [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): expires_in, access token, and refresh token.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): refresh token rotation, replay detection, and token protection.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): request, response, and timeout semantics at the HTTP layer.

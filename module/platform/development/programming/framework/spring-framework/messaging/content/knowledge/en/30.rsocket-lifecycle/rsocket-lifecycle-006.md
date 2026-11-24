# RSocket Resume: Recovering Sessions After Disconnection

Resume is an optional extension of the RSocket protocol that allows both ends to continue an existing RSocket session after the transport connection is interrupted. The client opens a new transport connection and asks the server to reattach the old session. If both parties still retain sufficient state and frames to replay, running streams can continue without recreating the entire session.

Resume addresses temporary network interruptions such as Wi-Fi handoffs, TCP connection resets, or brief path drops. This capability depends on both client and server supporting it, retaining session state, and still storing the necessary frames. Resume is not a durable message store and does not guarantee a session can always be recovered.

## 1. Distinguishing Resume, Reconnect, and Creating a New Session

These three behaviors are often confused:

| Behavior | What Happens After Disconnection | State of Old Streams |
|---|---|---|
| Resume | Client opens a new transport and sends a request to continue the old session | Restored if the server accepts and both sides still have sufficient state/frames |
| Regular reconnect | Client creates a new RSocket connection | Running streams are not automatically restored; the application must decide to re-request or resubscribe |
| Creating a new session | Client sends SETUP like an initial connection | Is a new session; may require re-authentication, setup, and restoring business state from the application |

Resume is a feature at the protocol/connector layer. The application still uses familiar interaction models such as request-response, request-stream, fire-and-forget, and request-channel. Spring handlers using `@MessageMapping` do not have to implement frame storage or replay themselves.

## 2. Session State That Must Be Retained

An RSocket session is more than a TCP socket. It also holds protocol state so both sides know which streams are active and which frames have been received.

Important data for Resume includes:

- **Resume Identification Token:** an opaque token used by the server to locate the exact old session. The client reuses the token sent in the initial SETUP when sending RESUME. The server should not infer structure from the token.
- **Per-direction frame position:** each side tracks the implied position of frames sent and received. Position is counted by frame order, not a sequence number field repeated in every frame.
- **Frames to replay:** each side keeps frames it sent that have not yet been confirmed as received by the peer. The frame store must retain enough data to replay from the position reported by the peer.
- **Stream and protocol state:** stream IDs, requester/responder state, interaction progress, and information needed to continue the session.
- **Session lifetime and expiration:** the server must retain the session long enough for the client to have a chance to reconnect. Once the session expires or is evicted from memory, the token can no longer restore the session.

Per the protocol, REQUEST, CANCEL, ERROR, and PAYLOAD frames have implied positions. Other frames do not participate in this position sequence. KEEPALIVE can carry the received position so the peer can update its state and evict parts of the frame store that are no longer needed.

Do not confuse the Resume Identification Token with user authentication credentials. The token serves to identify the session; the application must still enforce authentication and authorization per its security design. The token should be unpredictable, unique per session, and valid only for that session's lifetime.

## 3. RESUME and RESUME_OK Flow

### 3.1. Initial Session Establishment

When starting a connection, the client sends SETUP. If the client wants to use Resume, SETUP enables the Resume flag and carries the Resume Identification Token. The server must support Resume to accept this capability.

Once the session is established, the client and server begin tracking per-direction frame positions and storing frames needed for replay.

### 3.2. Transport Connection Loss

When the transport connection breaks, the logical session can still be preserved. Both sides keep the state and frame store for the allowed Resume duration. Transport closure does not immediately imply the session has been destroyed; this depends on the implementation's session lifecycle policy.

### 3.3. Client Opens a New Connection and Sends RESUME

The client creates a new transport connection to an endpoint that can locate the old session state, then sends RESUME with:

1. Protocol version.
2. Resume Identification Token matching the token in the initial SETUP.
3. Last Received Server Position: the last position the client successfully received from the server.
4. First Available Client Position: the earliest client frame position still retained for potential replay.

While awaiting the Resume result, the client must not send other regular frame types. RESUME is the first step on the new transport connection.

### 3.4. Server Checks and Responds

The server uses the token to look up the session, then checks whether session state and the frame store can satisfy the positions provided by the client.

- If continuation is possible, the server sends RESUME_OK. This frame carries Last Received Client Position, i.e., the last position the server received from the client.
- If the server does not support Resume, does not recognize the token, or no longer holds enough frames/state, the server can reject with ERROR[REJECTED_RESUME].
- Transient connection errors can be handled per the implementation's retry policy. Upon receiving ERROR[REJECTED_RESUME], the client must not keep retrying Resume for that same request.

### 3.5. Replaying Frames and Continuing Streams

After RESUME_OK, both sides use the exchanged positions to determine missing frames:

- The client replays frames starting from Last Received Client Position returned by the server.
- The server replays frames starting after Last Received Server Position reported by the client in RESUME.

Frames are replayed in protocol order. Once the missing data is processed, streams continue on the new transport connection. The application does not need to create a new request for each frame recovered by Resume.

## 4. Support Conditions on Both Client and Server

Resume works only when the following conditions are met simultaneously.

### Client

- The client implementation supports Resume and enables it when sending SETUP.
- The client preserves the original session's token.
- The client still retains outbound frames needed for replay; First Available Client Position must satisfy the server's requirement.
- The client has a retry policy to establish a new transport connection while the session is still valid.
- The client continues using protocol settings compatible with the original session, including data and metadata encoding.

### Server

- The server implementation supports Resume and is configured to enable it.
- The server still retains the session matching the token.
- The server still retains enough outbound frames since the last position acknowledged by the client.
- The session manager has not expired or evicted the session.
- The new transport connection is routed to a server that can access the exact session state.

### Both Sides

- Both sides must retain state throughout the disconnection period. Enabling Resume only on the client is not enough.
- Protocol version and connection settings must be compatible. Resume assumes parameters such as data/metadata formats have not changed between the old session and the reattachment.
- The frame store must have enough capacity for traffic generated during disconnection. If a frame must be replayed but was evicted from the store, Resume cannot complete.
- Session retention time must match the network interruption window the system aims to tolerate.
- In multi-node systems, the load balancer must route the Resume request to the node holding the session, or nodes must use a compatible shared/synchronized session state mechanism. Sticky sessions alone will not restore a session if the node lost its state.

## 5. Configuration in Spring Framework and RSocket Java

Spring provides RSocketRequester to send requests at the application level. The builder has an rsocketConnector callback to customize io.rsocket.core.RSocketConnector, including Resume configuration. Thus, Resume is enabled at the connector layer, not by adding recovery logic into each `@MessageMapping` method.

### 5.1. Client-Side Configuration

This is an illustrative configuration snippet for Spring Framework with RSocket Java. Required imports include RSocketRequester, Resume, Retry, and Duration. The example assumes TCP transport at localhost:7000.

~~~java
Resume resume = new Resume()
        .sessionDuration(Duration.ofMinutes(5))
        .retry(Retry.fixedDelay(6, Duration.ofSeconds(1)));

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector.resume(resume))
        .tcp("localhost", 7000);
~~~

This is a configuration fragment, not a standalone program: the application still needs the appropriate RSocket dependency, transport configuration, error handling, and actual requests. sessionDuration defines how long the implementation retains the session for potential reattachment. retry defines the reconnection retry policy; choose attempt counts and delays according to operational goals.

### 5.2. Server-Side Configuration

The server must also enable Resume. With RSocket Java, it can be configured on RSocketServer before binding the transport:

~~~java
Resume resume = new Resume()
        .sessionDuration(Duration.ofMinutes(5));

RSocketServer.create(acceptor)
        .resume(resume)
        .bind(serverTransport);
~~~

This is also a fragment: acceptor and serverTransport are supplied by the application. If Spring Boot creates the RSocket server automatically, apply the configuration to RSocketServer through the customization hook supported by the Spring Boot version in use. Client and server configuration must be deployed independently; enabling Resume on the client does not automatically enable Resume on the server.

### 5.3. Roles of Spring Components

- **RSocketRequester:** high-level API for sending requests and converting payloads to objects. It uses RSocketConnector underneath.
- **RSocketConnector:** establishes the client-side connection and configures Resume via resume(...).
- **RSocketServer:** sets up the server side and must have corresponding Resume configuration.
- **@MessageMapping:** handles messages by route at the application layer. Handlers do not replace the session manager or frame store.
- **RSocketStrategies:** configures encoders/decoders and how data and metadata are converted. On reattachment, encoding must stay compatible with the original session.

API names and server customization hooks may vary across Spring Framework, Spring Boot, and RSocket Java versions. Verify the Javadoc for the exact dependency version in your project before applying configuration.

## 6. Session Lifetime, Retries, and Frame Store Capacity

### sessionDuration

sessionDuration is how long the implementation keeps a session after transport disconnection while waiting for Resume. Too short a value deprives the client of recovery chances during longer network drops. Too long a value keeps session objects and frame stores around longer, consuming memory and resources.

Choose the duration based on the interruption window to tolerate, frame generation rate, and resource limits. You need an expiration cleanup mechanism to avoid retaining state indefinitely.

### Retry Policy

The retry policy determines how the client attempts to re-establish the transport. Use controlled backoff, appropriate attempt limits, and contextual logging. Retrying too aggressively can create heavy load while the server is recovering. Retrying longer than the session lifetime does not help either, since the server may have already evicted the state.

Connection retries do not mean every error can be Resumed. When the server returns REJECTED_RESUME, the client must treat the old session as unresumable and switch to creating a new session.

### Frame Store

Frame store capacity depends on traffic rate and disconnection duration. You can roughly estimate the required storage volume with:

~~~text
Minimum data capacity ≈ outbound frame rate × disconnect duration
~~~

This is only a baseline payload/frame estimate; real deployments also incur overhead, metadata, multiple concurrent sessions, and safety margins. Monitor retained session counts, frames awaiting replay, store size, Resume successes/failures, and rejections due to missing state.

KEEPALIVE and received positions help the implementation determine which frames the peer has received in order to trim the store. However, frame eviction must rely on valid position information; trimming too early can leave insufficient data for a subsequent Resume.

## 7. Cases Where Resume Fails

| Cause | Why Continuation Is Impossible | Remediation |
|---|---|---|
| Server does not support Resume | Server rejects this connection type | Enable Resume on the server or use reconnect and handle retries at the application layer |
| Unrecognized token | Server cannot find the old session | Check token, routing, and session manager lifecycle |
| Session expired | Session state was already evicted | Adjust sessionDuration if appropriate; create a new session once expired |
| Frame store lacks data | One or more frames needed for replay are no longer retained | Tune store capacity/lifetime and frame emission rate |
| Client or server restarted | State in process memory may have been lost | Need persistent session state storage and recovery if restarts must be supported |
| Load balancer routed to another node | New node lacks the session state | Use session affinity or an appropriate state sharing/recovery mechanism |
| Protocol configuration changed | New session settings are incompatible with the original session | Keep configuration compatible while the session can be Resumed |
| Client exhausted retry window | Transport was not re-established within the session lifetime | Tune retries and sessionDuration to match real SLOs |

When Resume is rejected, the application can create a new session via SETUP. If a business data stream must continue, the application should send a cursor, offset, or business session ID so the server resumes from the saved checkpoint. Never assume a new RSocket session automatically knows the business position processed by the old session.

## 8. What Does Resume Guarantee and What Does It Not Guarantee?

Resume restores protocol state and supports frame replay within the bounds of data still retained by both sides. It helps active streams continue after certain transport failures without reinitializing the entire interaction.

Resume itself is not a message broker or durable store. If the server process stops and the session/frame store only lives in RAM, state can be lost. Resuming across restarts or failovers requires an implementation that persists and recovers session state, frame stores, token mappings, and routing accordingly. Do not assume enabling Resume alone provides fault tolerance in multi-node deployments.

Resume also does not define atomicity, transactions, or exactly-once semantics for business side effects. Applications still need idempotency keys, transaction boundaries, cursors/offsets, and business state persistence when operations may be resent or when a new session must be created. For critical event data, persist business checkpoints durably rather than relying solely on RSocket frame positions.

Lease also does not implicitly carry over from the previous connection. Per the protocol, Lease semantics must be restarted on the new connection via a LEASE frame from the server if Leases are in use.

## 9. Implementation and Operations Checklist

- [ ] Client enables Resume in SETUP and saves the session token.
- [ ] Server enables Resume and can resolve the token back to the right session.
- [ ] Both sides retain frame stores and stream state long enough.
- [ ] Retry policy aligns with sessionDuration and expected recovery time.
- [ ] Load balancer routes RESUME to the right node or session state is shared/recovered.
- [ ] Data MIME type, metadata MIME type, and protocol settings stay compatible with the original session.
- [ ] Memory limits, expired session cleanup, and frame store monitoring are in place.
- [ ] Fallback exists to create a new session along with business cursor/offset recovery.
- [ ] Business operations that may be resent are protected by appropriate idempotency or transactions.
- [ ] Logs and metrics distinguish transport errors, retry failures, RESUME_OK, and REJECTED_RESUME.

## 10. Quick Diagnostics

**Client keeps reconnecting but streams do not continue:** check whether the client actually configured resume(...) or only reconnect(...), whether the server enabled Resume, and whether the new transport reaches the node holding the session.

**Resume works for short drops but fails after longer outages:** check sessionDuration, the retry policy, and when the session manager evicts sessions. Also check whether the frame store filled up or evicted frames needed for replay.

**Resume fails after deploy/restart:** if state lives only in RAM, the new server lacks the old session. You need shared/persistent session state, or accept creating a new session and recovering from a business cursor.

**Application processes duplicate business side effects:** inspect transaction boundaries and handler idempotency. RSocket frame positions do not replace idempotency keys or business checkpoints.

**Lease is no longer valid after Resume:** restart Lease per protocol on the new connection and check server-side lease issuance configuration.

## References

- RSocket Protocol — Resuming Operation, RESUME and RESUME_OK: https://github.com/rsocket/rsocket/blob/master/Protocol.md#resuming-operation
- Spring Framework Reference — RSocket Support and RSocketRequester configuration: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Framework Javadoc — RSocketRequester.Builder.rsocketConnector(...): https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html
- RSocket Java — RSocketConnector and resume(Resume): https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java

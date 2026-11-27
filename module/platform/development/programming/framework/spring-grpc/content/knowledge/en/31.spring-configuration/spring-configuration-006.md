# Configuring Keepalive and Message Size

In **SPRING_GRPC**, keepalive and message size limits directly affect HTTP/2 connection stability, the ability to transmit large payloads, and resource consumption. Keepalive helps detect lost connections or keep connections alive through proxies/load balancers that enforce idle timeout policies. Message size limits the amount of data a single RPC message is allowed to receive.

Spring Boot provides separate properties for the gRPC client and server. Both sides must be configured in coordination: the server controls messages received from the client and the ping policy the client is allowed to send; the client controls messages received from the server and the channel's keepalive cadence. This lesson covers how to choose values, apply them in YAML, and test the limits in practice.

## 1. Distinguishing keepalive from health checks and deadlines

gRPC keepalive uses HTTP/2 PING frames to check the transport connection. One endpoint sends a PING after a period with no read activity; the peer responds with an ACK. If no response arrives within the timeout, the transport closes the connection.

Keepalive solves transport-layer problems:

- Detecting connections that are no longer responsive.
- Keeping connections alive when a proxy or load balancer closes connections after too long without traffic.
- Supporting streaming RPCs or long-lived channels.

It does not verify that the service can still process business logic. Distinguish between:

| Mechanism | What does it check? | Scope |
| --- | --- | --- |
| gRPC keepalive | Whether the HTTP/2 connection responds to PING/ACK | Transport connection |
| gRPC Health | Whether the service is in `SERVING` state | Service/application |
| RPC deadline | Maximum time a single call is allowed to run | Per RPC |
| TCP keepalive | Whether the TCP socket still responds at the OS level | TCP connection |

Do not use PING to replace health checks or deadlines. A connection can still respond to PING even when the database is down; conversely, an idle connection with no RPCs can remain healthy without frequent PINGs.

## 2. Keepalive has two sides and two directions of operation

Both client and server can send PINGs. Key parameters:

| Parameter | Meaning |
| --- | --- |
| `keepalive.time` | Duration without read activity before the sender issues a PING |
| `keepalive.timeout` | Time to wait for a response after sending a PING; closes the connection on expiry |
| `keepalive.without-calls` | On the client, whether to allow sending PINGs when no RPCs are active |
| `keepalive.permit.time` | On the server, minimum interval between client PINGs allowed when there is no data/header activity |
| `keepalive.permit.without-calls` | On the server, whether to allow the client to send PINGs when no RPCs are active |

Common defaults in gRPC are:

- Client keepalive time is disabled by default; timeout is typically `20s`; does not send PINGs when there are no active RPCs.
- Server keepalive time defaults to `2h`; timeout is `20s`.
- Server permit time defaults to `5m`; by default, clients are not permitted to PING without active RPCs.

Spring Boot 4.1 provides properties to tune these values. Effective behavior also depends on the transport, version, and proxy/load balancer configuration.

**Do not configure the client to send PINGs too frequently.** If a client sends PINGs faster than the server's permit policy allows or sends PINGs when the server disallows them without active calls, the server may send an HTTP/2 `GOAWAY` with debug data `too_many_pings` and close the connection. gRPC guidelines recommend avoiding enabling PINGs without active calls and avoiding overly short client intervals; coordinate with the server owner before changing these settings.

## 3. Configuring keepalive for the gRPC client

Each channel can have its own policy. Example of an `inventory` client calling a server over an internal network:

```yaml
spring:
  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal:9090
          keepalive:
            time: 5m
            timeout: 20s
            without-calls: false
```

Meaning:

- `time: 5m`: when the connection has no read activity for this duration, the client may send a PING.
- `timeout: 20s`: the client waits up to 20 seconds for a PING ACK.
- `without-calls: false`: the client does not proactively send PINGs when no RPC is active.

This example fits scenarios where a long-lived connection needs to be maintained. If the server keeps the default permit time of `5m`, the client should not set `time` lower than that value. If the server sets a different permit time, the client must comply with the server's actual policy.

Configuration in `application.properties`:

```properties
spring.grpc.client.channel.inventory.target=static://inventory.internal:9090
spring.grpc.client.channel.inventory.keepalive.time=5m
spring.grpc.client.channel.inventory.keepalive.timeout=20s
spring.grpc.client.channel.inventory.keepalive.without-calls=false
```

If the application has multiple channels, they do not all have to use the same interval. A channel used for long-lived streaming through a load balancer may need keepalive; a channel making short, frequent unary calls may not need additional configuration.

## 4. Configuring the keepalive policy on the server

The server controls the PING cadence it sends itself and the limits on PINGs from clients:

```yaml
spring:
  grpc:
    server:
      keepalive:
        time: 2h
        timeout: 20s
        permit:
          time: 5m
          without-calls: false
```

In this example:

- `time: 2h`: the server sends a PING when there is no read activity for two hours.
- `timeout: 20s`: the server waits up to 20 seconds for a response.
- `permit.time: 5m`: the server does not accept client PINGs more frequently than the five-minute minimum policy when there is no data/header activity.
- `permit.without-calls: false`: the server does not allow clients to send PINGs when the connection has no active RPCs.

`permit.time` is not an RPC timeout. It is a policy protecting the server from excessive PINGs. If you need to change this value, coordinate with client configuration and network infrastructure.

### 4.1. Managing connection lifetime

The server can also set limits on connection age and idle time:

```yaml
spring:
  grpc:
    server:
      keepalive:
        connection:
          max-age: 30m
          max-idle-time: 10m
          grace-period: 30s
```

- `connection.max-age`: maximum age of a connection before the server requests a controlled termination.
- `connection.max-idle-time`: duration a connection can have no active RPCs before being gracefully terminated.
- `connection.grace-period`: maximum duration allowed for graceful termination.

This is a connection lifecycle policy, distinct from PING/ACK. When setting `max-age`, long-lived channels and active streams need an appropriate reconnect/resume strategy. Do not choose an overly short duration if the application has long-running streams or clients cannot resume processing position.

## 5. Message size limits are inbound limits

gRPC enforces message limits on the **receiving** side. Each endpoint controls the size of messages it accepts:

- The server inbound limit controls request messages sent by the client.
- The client inbound limit controls response messages sent by the server.

Therefore, increasing the limit on the server does not automatically increase the response limit on the client. If both requests and responses are large, you must configure the receiving side properly in both directions.

gRPC Java typically defaults to about `4 MiB` for inbound messages. Spring Boot 4.1 provides `inbound.message.max-size` to adjust this value.

## 6. Configuring message size for server and client

Example allowing messages up to `8MB` on both sides:

```yaml
spring:
  grpc:
    server:
      inbound:
        message:
          max-size: 8MB

    client:
      channel:
        inventory:
          target: static://inventory.internal:9090
          inbound:
            message:
              max-size: 8MB
```

The corresponding properties:

| Receiving side | Property |
| --- | --- |
| Server receiving requests | `spring.grpc.server.inbound.message.max-size` |
| Client receiving responses on channel `inventory` | `spring.grpc.client.channel.inventory.inbound.message.max-size` |

This can be declared in `application.properties`:

```properties
spring.grpc.server.inbound.message.max-size=8MB
spring.grpc.client.channel.inventory.inbound.message.max-size=8MB
```

The property accepts a `DataSize`, so suffixes such as `KB`, `MB`, or `B` can be used. If the suffix is omitted, the value is interpreted as bytes. Write the unit explicitly to avoid confusing bytes with megabytes.

This limit applies per individual message, not the total size of an entire stream. A server-streaming RPC can send many messages; each message must stay within the client's inbound limit. Similarly, client-streaming has multiple requests, and each request must stay within the server's inbound limit.

## 7. Message size, metadata size, and compression

Do not confuse message size with metadata size:

- Messages hold protobuf payloads such as fields, bytes, or nested messages.
- Metadata holds control information such as authorization tokens, trace context, and custom headers.

Spring Boot has separate properties for inbound metadata, which typically have much smaller default limits than messages. Raising the message limit does not raise the metadata limit. If errors are caused by oversized headers/metadata, check the metadata properties and reduce the amount of data placed in metadata.

Message size is also not the total memory limit for a request. A large message may require memory for network buffers, parsed protobuf objects, and copies in application logic. Compression can reduce bytes transmitted over the network, but the receiving side still must decompress and process the payload. Therefore, choose limits based on actual decompressed payload size and the workload's memory capacity.

## 8. Choosing a safe message size

Do not set a huge or unlimited size just to avoid `RESOURCE_EXHAUSTED` errors. Determine the maximum valid payload size based on business requirements and add a controlled margin.

Some principles:

- Keep the default if normal payloads are much smaller than `4 MiB`.
- Only increase to `8MB`, `16MB`, or another level when backed by a use case and measurements.
- Align the contract between sender and receiver; verify requests and responses independently.
- Consider metadata size, memory limits, concurrency, and the number of open streams at the same time.
- For files or very large data, prefer chunked streaming instead of sending a single message containing the entire payload.
- Use flow control and backpressure so the producer does not push data faster than the consumer can process.

Example schema for chunked file transfer:

```proto
message UploadChunk {
  string upload_id = 1;
  int64 sequence = 2;
  bytes data = 3;
  bool last = 4;
}

service FileService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}
```

Each `UploadChunk` has a bounded size; the total file can be many times larger than that limit. The application needs to validate sequence numbers, handle retry/resume, and limit how many chunks are held in memory.

## 9. Combined configuration for a real-world service

The example below sets policies for an inventory server and its corresponding client channel:

```yaml
spring:
  grpc:
    server:
      port: 9090
      keepalive:
        time: 2h
        timeout: 20s
        permit:
          time: 5m
          without-calls: false
      inbound:
        message:
          max-size: 8MB

    client:
      channel:
        inventory:
          target: static://inventory.internal:9090
          keepalive:
            time: 5m
            timeout: 20s
            without-calls: false
          inbound:
            message:
              max-size: 8MB
```

This configuration illustrates client pings at an interval matching the server's permit policy and allows each side to receive messages up to `8MB`. Values should be tuned to actual traffic, proxy idle timeouts, and payload sizes; this is not a universal default for every system.

## 10. When is ServerBuilderCustomizer needed?

Standard properties fit common keepalive and inbound message size settings. If you need a transport-specific option not exposed by Spring Boot, you can use a `ServerBuilderCustomizer` bean to customize the server builder before the server is created. The exact builder type and available options depend on the transport and `grpc-java` version.

Do not set the same value in both properties and a customizer without clarifying the configuration order/source. With servlet transport, the servlet container manages the network layer and some native builder options may not be available. Confirm the transport before using a customizer.

## 11. Testing keepalive and message size

### 11.1. Testing message size

Create a test server and client with a small limit, such as `1MB`, and test:

1. Requests smaller than the limit are processed.
2. Requests larger than the server inbound limit are rejected.
3. Responses larger than the client inbound limit are rejected by the client.
4. Raising the limit on the correct receiving side makes the corresponding test pass.
5. Streaming many small chunks still works when total data exceeds `1MB`.

Exceeding the limit is usually reported as gRPC status `RESOURCE_EXHAUSTED` or a corresponding transport error. Identify which side rejected the message from logs and exception causes rather than blindly raising limits on both ends.

### 11.2. Testing keepalive

Keepalive should be tested on a real network transport because in-process transport does not fully simulate HTTP/2 PINGs:

- Open a channel and execute an RPC.
- Leave the connection idle or maintain a long-lived stream per the test scenario.
- Verify that client/server keep the connection open for the expected duration.
- Shut down the server or block the network path in the test environment to confirm ping timeout detects the lost connection.
- Test a client ping interval shorter than the server permit policy in an isolated environment to recognize policy errors; never run this test in production.
- Verify reconnection and stream recovery when the connection is closed due to max age or network interruption.

Do not use a single fast unary RPC to conclude that keepalive works; the RPC may finish before the PING timer triggers.

## 12. Diagnosing common errors

| Symptom | Causes to check |
| --- | --- |
| Connection closed by server with `too_many_pings` | Client pings too often or pings without active RPCs when server forbids it |
| Channel loses connection after idle period | Proxy/load balancer idle timeout, keepalive not enabled, or mismatched timeout |
| PING timeout | Unresponsive network path, overloaded server, or broken connection |
| Request rejected because message is too large | Server inbound message limit is lower than request size |
| Client receives `RESOURCE_EXHAUSTED` reading response | Client inbound message limit is lower than response size |
| Small message still rejected | Possible metadata size error rather than message size |
| Stream broken after some time | Server connection `max-age`, idle policy, proxy timeout, or network interruption |
| Limit increased, but error persists | Edited the wrong receiving side, wrong channel, or config not bound to running server/client |

During investigation, record payload size, channel target, transport, effective property sources, and full status/exception details. Do not log sensitive content just to measure size; log byte counts and the RPC method instead.

## 13. Practice exercises

1. Keep the default configuration and record the largest request/response size of an RPC.
2. Configure the server inbound message size to `8MB`; send a `6MB` request and confirm it succeeds.
3. Keep the client inbound limit at `4MB`; return a `6MB` response and confirm the client rejects it.
4. Increase the client inbound limit to `8MB`; re-run the response test.
5. Configure client keepalive `time: 5m`, `timeout: 20s`, `without-calls: false`.
6. Configure server `permit.time` and `permit.without-calls`; confirm the client complies with the policy.
7. Observe a connection through a proxy with an idle timeout; compare with keepalive enabled vs. disabled.
8. Set `connection.max-age` in a test and verify client reconnection after the server gracefully closes the connection.
9. Convert a large payload into streamed chunks and measure memory usage when multiple uploads run concurrently.
10. Document which properties belong to the client, which belong to the server, and which message direction each limit controls.

### Key Takeaways

**Keepalive governs transport connection health; message size limits each message accepted by a receiving endpoint.** Client ping configuration must align with the server's permit policy and network infrastructure. Request limits must be set on the server, response limits on the client; both must be tested independently. For large payloads, choose reasonable limits or split them into streamed chunks with flow control instead of opening unlimited sizes.

## References

- [Spring Boot — gRPC Channel Properties](https://docs.spring.io/spring-boot/reference/io/grpc.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot API — GrpcClientProperties.Channel.Keepalive](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/grpc/client/autoconfigure/GrpcClientProperties.Channel.Keepalive.html)
- [Spring gRPC — Server and ServerBuilderCustomizer](https://docs.spring.io/spring-grpc/reference/server.html)
- [gRPC — Keepalive](https://grpc.io/docs/guides/keepalive/)
- [gRPC Java — ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html)

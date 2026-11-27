# Using grpcurl to Narrow Down Root Causes

`grpcurl` is a command-line tool that sends gRPC requests directly to an endpoint. It can read Protocol Buffers contracts from the server via reflection or from `.proto`/descriptor files supplied by the project. This lets you test connectivity, TLS, services, methods, metadata, deadlines, and RPC responses without writing another Java client program.

In a Spring gRPC service, `grpcurl` helps isolate whether an error lies in the network path, server configuration, protobuf contract, authentication, or business processing. Its output is a point-in-time snapshot; correlate it with application logs, traces, and metrics to pinpoint the root cause.

## 1. Identify the Exact Endpoint Before Calling

A Spring application can simultaneously open an HTTP port for REST/Actuator and a separate port for gRPC. These two ports are not interchangeable. Obtain the actual gRPC host and port from the effective configuration, startup logs, deployment manifests, or environment Service/Ingress configuration.

Do not assume the gRPC port is `9090`: that value merely appears in many examples. Different Spring gRPC integration libraries may use different property names and default values. Also check the bind address: a server listening only on loopback will not accept connections from other containers or machines.

The example below assumes the server listens with plaintext at `localhost:9090`. Replace this address with the endpoint of the environment under test.

```bash
grpcurl -plaintext localhost:9090 list
```

This command simultaneously checks the gRPC connection and asks the server for its list of services via reflection. If the server uses TLS, omit `-plaintext` and configure appropriate certificates in the next step.

Run tests from the same network location as the failing client. Running from a laptop can produce different results than running inside a Kubernetes pod, container, or application host because DNS, routes, firewalls, and service discovery differ.

## 2. Distinguish Connectivity, HTTP/2, and TLS Errors

gRPC uses HTTP/2. An open TCP port alone does not prove an endpoint serves gRPC: a proxy might route traffic incorrectly, only support HTTP/1.1 upstream, or forward requests to a REST port.

### Plaintext Server

For an internal endpoint without TLS enabled:

```bash
grpcurl -plaintext localhost:9090 list
```

`-plaintext` tells `grpcurl` to use an unencrypted connection. Use this only when the endpoint is genuinely configured for plaintext, such as an internal connection in a development environment. If the server requires TLS, this command will fail at the transport layer.

### TLS Server

If the server uses a certificate issued by an internal CA, pass the trusted CA:

```bash
grpcurl -cacert ./certs/ca.pem api.example.internal:443 list
```

If the server requires mutual TLS (mTLS), also pass the client certificate and private key:

```bash
grpcurl \
  -cacert ./certs/ca.pem \
  -cert ./certs/client.pem \
  -key ./certs/client.key \
  api.example.internal:443 list
```

When traversing an ingress or host-routing proxy, you may need to specify the authority:

```bash
grpcurl -authority api.example.internal api.example.internal:443 list
```

`-authority` sets the authority value of the gRPC request. Use the exact hostname expected by proxy configuration; do not use this option to mask DNS or certificate errors.

During isolation, `-insecure` can help determine whether the failure relates to certificate verification:

```bash
grpcurl -insecure api.example.internal:443 list
```

This flag skips server certificate verification. Use it only in short, controlled tests; never put it in client configurations or long-term operational procedures. If a command only succeeds with `-insecure`, fix the CA chain, SAN/hostname, certificate validity, or TLS configuration rather than keeping that flag.

### Reading Transport Errors

| Symptom | Layer to Check Next |
| --- | --- |
| `connection refused` | No process listening at that host/port, wrong port, wrong port mapping, or server has not finished starting. |
| Hostname resolution error | DNS, service name, namespace, or resolver configuration of the environment running `grpcurl`. |
| Timeout or `Unavailable` before receiving a server status | Network route, firewall, load balancer, unhealthy endpoint, or proxy failing to forward connections. |
| Handshake failure, unknown authority, or hostname mismatch | Trusted CA, certificate SAN, accessed hostname, expired certificate, and mTLS configuration. |
| Unusual HTTP status such as 404/415 | Possibly calling the wrong HTTP port, proxy misrouting, or upstream not speaking HTTP/2 as gRPC requires. |

If TLS terminates at the ingress while ingress-to-service uses plaintext, test each hop separately. Success when calling a pod directly does not prove the path through the ingress works, and vice versa.

## 3. Inspect Services and Describe Methods

When the server enables gRPC reflection, you can list services:

```bash
grpcurl -plaintext localhost:9090 list
```

Then inspect the methods and request/response types of a service:

```bash
grpcurl -plaintext localhost:9090 describe acme.greeter.v1.Greeter
```

The full service name is formed from the `package` in the `.proto` file and the service name. This name does not necessarily match the Java package, implementation class name, or Spring bean name. Methods are invoked in the case-sensitive form `package.Service/Method`.

Example contract:

```protobuf
syntax = "proto3";

package acme.greeter.v1;

service Greeter {
  rpc SayHello (HelloRequest) returns (HelloReply);
}

message HelloRequest {
  string name = 1;
}

message HelloReply {
  string message = 1;
}
```

With the contract above, the RPC name is `acme.greeter.v1.Greeter/SayHello`.

### When Reflection Is Not Enabled

A message saying the server does not support reflection does not prove the service is stopped or unregistered. Reflection is a separate service that may be disabled in configuration or blocked by security policy. In that case, pass the `.proto` files of the right API version to `grpcurl`:

```bash
grpcurl \
  -plaintext \
  -import-path . \
  -proto proto/greeter/v1/greeter.proto \
  localhost:9090 \
  list
```

`-import-path` specifies the root directory for resolving `import` statements; `-proto` specifies the file describing the service. If the file depends on other protos, add the necessary import paths or proto files.

You can bundle descriptors along with dependencies using `protoc`:

```bash
protoc -I . \
  --include_imports \
  --descriptor_set_out=build/api.protoset \
  proto/greeter/v1/greeter.proto
```

Then use the descriptor set:

```bash
grpcurl -plaintext \
  -protoset build/api.protoset \
  localhost:9090 \
  describe acme.greeter.v1.Greeter
```

The descriptor must match the running server version. If you use an outdated proto, `grpcurl` may generate requests missing fields, use wrong data types, or call methods that no longer exist. Obtain proto/protoset files from the exact deployed commit or artifact.

## 4. Test Calling a Unary RPC

Once you have verified the right service, method, and descriptor, send a small request with valid data:

```bash
grpcurl -plaintext \
  -import-path . \
  -proto proto/greeter/v1/greeter.proto \
  -d '{"name":"An"}' \
  localhost:9090 \
  acme.greeter.v1.Greeter/SayHello
```

If reflection is enabled and no local proto files are needed, omit `-import-path` and `-proto`:

```bash
grpcurl -plaintext \
  -d '{"name":"An"}' \
  localhost:9090 \
  acme.greeter.v1.Greeter/SayHello
```

`grpcurl` accepts requests in JSON following Protocol Buffers' JSON mapping rules. Field names typically use lowerCamelCase; enums use enum names; `bytes` are Base64-encoded; 64-bit integer types are usually represented as strings in protobuf JSON. Refer to the schema when hitting parse or type errors.

When the result returned is a valid gRPC status, the request traveled far enough to get a response from a gRPC peer. At that point, focus on status, metadata, descriptor, and handler logs instead of continuing to change DNS or ports at random.

## 5. Test Metadata and Authentication

Many services require a token, tenant ID, or routing metadata. Pass metadata with `-H`; repeat this flag for multiple headers:

```bash
grpcurl -plaintext \
  -H 'authorization: Bearer <access-token>' \
  -H 'x-tenant-id: team-a' \
  -d '{"name":"An"}' \
  localhost:9090 \
  acme.greeter.v1.Greeter/SayHello
```

Testing the same request with and without metadata helps distinguish authentication failures from business errors. `UNAUTHENTICATED` typically indicates missing, invalid, or expired credentials; `PERMISSION_DENIED` typically indicates the identity was recognized yet lacks permission to perform the action.

If reflection is also protected, `list` or `describe` commands may require the same authentication metadata. A reflection check failing due to a missing token does not mean the business RPC does not exist.

Never put real tokens into documentation, shared logs, or shared shell histories. Use short-lived test credentials and revoke them after testing.

## 6. Test Deadlines and Response Times

gRPC clients should set deadlines to bound wait times. `grpcurl` supports `-max-time`; the example below caps the call at five seconds:

```bash
grpcurl -plaintext \
  -max-time 5s \
  -d '{"name":"An"}' \
  localhost:9090 \
  acme.greeter.v1.Greeter/SayHello
```

If the request fails with `DEADLINE_EXCEEDED`, compare server processing time, dependency wait times, executor queues, database connections, and the deadline propagated by upstream gateways/clients. Trying a longer deadline can tell whether the request merely needs more time or is hanging; never treat raising deadlines as a performance fix.

A deadline expiring on the client also does not prove the server stopped working. A handler or blocking call can keep running if it ignores cancellation state and fails to propagate deadlines/cancellations to dependencies. Inspect logs and traces to see whether the request continues consuming resources after the client stops waiting.

## 7. Test Server Streaming and Client Streaming

For a server-streaming RPC, send the request once and observe each returned message:

```bash
grpcurl -plaintext \
  -d '{"topic":"news"}' \
  localhost:9090 \
  acme.feed.v1.Feed/Subscribe
```

If the stream does not end, use `-max-time` to limit observation duration during the test. Distinguish between a server that has not emitted any message yet, a server waiting for new events, and a server that terminated with an error status.

For a client-streaming RPC, `-d @` reads requests from standard input. For example, in a Unix-like shell, pass JSON messages one per line:

```bash
printf '%s\n' '{"id":"a"}' '{"id":"b"}' |
  grpcurl -plaintext \
    -d @ \
    localhost:9090 \
    acme.batch.v1.Batch/Upload
```

For bidirectional streaming, check both directions: whether the server received all messages, whether it emitted responses before the client closed input, and what the final stream status is. Standard input interaction may vary across `grpcurl` versions and shells; check `grpcurl -help` on your installed version when sending interactive message sequences.

If unary succeeds while streaming fails, focus on the method type in `.proto`, how the client sends/closes input, flow-control logic, timeouts, message size limits, and whether proxies keep HTTP/2 connections open long enough.

## 8. Use Health Checks Properly

If the server registered the gRPC Health Checking Protocol, you can invoke `Check`:

```bash
grpcurl -plaintext \
  -d '{"service":"acme.greeter.v1.Greeter"}' \
  localhost:9090 \
  grpc.health.v1.Health/Check
```

The health service is optional. `UNIMPLEMENTED` here may simply mean the application has not registered the health service; it does not prove business services are broken. If the health service exists, inspect `SERVING`/`NOT_SERVING` status and how the application updates status when dependencies fail.

## 9. Interpret gRPC Statuses

Once connected to a gRPC server, the status is a key clue for categorizing errors. The table below offers initial investigation directions; the final meaning also depends on how the application maps exceptions to gRPC statuses.

| Status | Direction to Check |
| --- | --- |
| `UNAVAILABLE` | Server temporarily unavailable, connection closed, proxy/upstream error, or server starting/stopping. Check endpoint and transport logs. |
| `UNAUTHENTICATED` | Token or authentication info missing, invalid, or expired; check metadata and authentication interceptors. |
| `PERMISSION_DENIED` | Identity lacks permission; check policies, roles, tenants, and authorization interceptors. |
| `INVALID_ARGUMENT` | Invalid payload or failed validation; check protobuf schema and business rules. |
| `NOT_FOUND` | Resource or business entity does not exist; check data and identifiers in the request. |
| `FAILED_PRECONDITION` | Current state does not satisfy preconditions for the operation; check domain lifecycle and state. |
| `UNIMPLEMENTED` | Method/service not implemented or not registered, or client using wrong name/descriptor. Reflection being disabled is a separate situation. |
| `DEADLINE_EXCEEDED` | Deadline expired before completion; check latency, dependencies, queues, and deadline propagation. |
| `RESOURCE_EXHAUSTED` | Rate limit, quota, message size, memory, or processing capacity hit its limit. |
| `CANCELLED` | Client or intermediary cancelled the request; check cancel actions, stream closure, and client lifecycle. |
| `INTERNAL` | Internal error or unmapped exception; use request ID/trace to locate server-side stack traces. |

Status codes can include messages, details, and trailing metadata. Use verbose mode when you need more details:

```bash
grpcurl -v -plaintext localhost:9090 list
```

Do not expose verbatim internal error messages to clients if they contain sensitive information. In production, server-side logs should retain enough detail for investigation while strictly controlling secret data.

## 10. Narrow Down Errors Inside a Spring Application

Once `grpcurl` reaches the endpoint, check the application layers sequentially:

1. **Server and service registration:** inspect startup logs, bind port, and whether implementation/service beans were created and registered. A Java class existing in source does not guarantee the service is bound to the running gRPC server.
2. **Protobuf contract:** compare package, service name, method, and `grpcurl` descriptor against the actual deployed artifact. The Java package may differ from the `package` in `.proto`.
3. **Interceptors and metadata:** confirm authentication, authorization, tracing, or tenant interceptors receive the right metadata. If direct calls succeed yet gateway calls fail, compare headers and authority across both paths.
4. **Business processing and dependencies:** use statuses, request-ID logs, and traces to see how far the handler ran; check databases, HTTP clients, message brokers, or dependent services.
5. **Deadlines and resources:** compare timings across spans, executors/thread pools, message limits, and cancellation status. For streaming, inspect connection lifetime and how proxies handle HTTP/2.

A useful comparison is calling the same RPC with the same descriptor and metadata at three points: localhost inside the process/host, internal service address, and ingress endpoint. If only one point fails, the investigation scope usually sits at that hop's network boundary or configuration. If all three return the same business status, focus on handlers, data, and dependencies.

## 11. Concise Investigation Workflow

When triaging a gRPC error, record findings in the following order:

| Step | Test | Conclusion to Record |
| --- | --- | --- |
| 1 | Connect to the right host/port with `-plaintext` or appropriate TLS | Can TCP/TLS/HTTP2 be established? |
| 2 | `list` or load local proto/protoset | Does reflection work? Is the descriptor the right version? |
| 3 | `describe` service and method | Do RPC name and request/response match the contract? |
| 4 | Call unary with a minimal payload | Does the server return a response or which gRPC status? |
| 5 | Add metadata and deadline | Does the error depend on authentication, authorization, or wait time? |
| 6 | Call streaming/health if applicable | Does the error appear only on streaming or health services? |
| 7 | Correlate logs, traces, and metrics at the same timestamp | Which Spring component or dependency produced the status or latency? |

When sharing investigation results, record the endpoint (with sensitive info masked), timestamp, `grpcurl` version, proto version, exact command run, status/message, non-sensitive metadata, and request ID/trace ID. This information helps others reproduce the test and look up the right logs.

`grpcurl` narrows down errors by testing each layer of a gRPC call. The most reliable conclusions come from keeping the request and descriptor constant, changing one factor at a time, and correlating `grpcurl` responses with Spring server logs and traces.

# grpcurl and Endpoint Inspection

grpcurl is a command-line tool for invoking and inspecting gRPC endpoints. It can discover services via server reflection, read contracts from .proto files or descriptor sets, construct JSON requests, and invoke RPCs. This enables developers to verify that a Spring gRPC server has opened the right port, exposed the right services, passed TLS/authentication, and executed business methods.

In the SPRING_GRPC module, endpoints must be checked across multiple layers: address and transport, service descriptors, health state, access permissions, and RPC results. A successful list command only proves reflection can respond; it does not prove business methods work. Similarly, a successful TCP/TLS connection does not guarantee the client is calling the right service path.

## 1. What can grpcurl inspect?

grpcurl is a general-purpose gRPC client. It uses descriptors to encode JSON requests into Protobuf and decode responses back into JSON. Common tasks:

- Checking connectivity to a gRPC host and port.
- Listing services and methods published by the server.
- Inspecting message structures, fields, and data types.
- Invoking unary RPCs using JSON requests.
- Sending metadata for authentication, tenant, or tracing.
- Connecting over plaintext in local/test environments or TLS/mTLS in secured environments.
- Calling health checking RPCs if the server has registered a health service.
- Using .proto files or descriptor sets when the server disables reflection.

grpcurl is not a replacement for load testing, continuous health monitoring, or full business workflow testing. It is suited for smoke tests, troubleshooting, and verifying one endpoint at a time.

## 2. Specifying the right address and service path

A gRPC endpoint is typically specified by hostname/IP and port, for example:

```text
localhost:9090
orders.default.svc.cluster.local:8443
orders.example.internal:443
```

In grpcurl, pass the host:port address. URI resolvers like dns:///orders.default.svc.cluster.local:8443 are typically configured for an application's ManagedChannel; when calling grpcurl, use the actual hostname/port:

```bash
grpcurl orders.default.svc.cluster.local:8443 list
```

The address only identifies where to connect. Service and method names are formed from the Protobuf contract. For example, if the proto declares:

```proto
package acme.orders.v1;

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}
```

The full service name is acme.orders.v1.OrderService, and the RPC path is:

```text
/acme.orders.v1.OrderService/GetOrder
```

Do not use the Java package from java_package instead of the proto package when calling RPCs. Also do not use DNS names or registry names instead of the fully qualified service name. If the client connects successfully but calls the wrong path, the server can return UNIMPLEMENTED.

## 3. Discovering services with reflection

When the server enables reflection, grpcurl can fetch descriptors directly:

```bash
# List services
grpcurl -plaintext localhost:9090 list

# List methods of a service
grpcurl -plaintext localhost:9090 list acme.orders.v1.OrderService

# Inspect service descriptor
grpcurl -plaintext localhost:9090 describe acme.orders.v1.OrderService

# Inspect message descriptor
grpcurl -plaintext localhost:9090 describe acme.orders.v1.GetOrderRequest
```

-plaintext requests a non-TLS connection; use it only for local or controlled test networks. If the endpoint uses TLS, omit this flag and configure the appropriate CA/certificate.

The list output shows which services the server exposes. describe shows methods, input/output types, and message structures. If a service exists in a proto file but has not been registered on the server, reflection will not list it automatically.

## 4. When reflection is disabled: using proto or protoset

Production may disable reflection to restrict descriptor disclosure. grpcurl can still invoke RPCs if supplied with the contract:

```bash
# Using a proto file and import path
grpcurl -plaintext \
  -import-path ./src/main/proto \
  -proto orders.proto \
  localhost:9090 \
  describe acme.orders.v1.OrderService

# Using a pre-built descriptor set
grpcurl -plaintext \
  -protoset orders.protoset \
  localhost:9090 \
  describe acme.orders.v1.OrderService
```

You can generate a descriptor set in the build pipeline:

```bash
protoc -I proto \
  --include_imports \
  --descriptor_set_out=orders.protoset \
  orders.proto
```

--include_imports packages dependent descriptors so grpcurl has complete schemas when decoding messages. Protoset files must be versioned with each release; using an outdated descriptor can cause requests not to match the live running API.

Reflection and schema files serve two different needs: reflection shows the descriptors the server is publishing; .proto/protoset lets you verify against the built and reviewed contract. If the two sources disagree, investigate contract drift instead of modifying requests by guesswork.

## 5. Invoking a unary RPC with JSON

Once descriptors are available, send a JSON request with -d:

```bash
grpcurl -plaintext \
  -d '{"orderId":"ORD-42"}' \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder
```

grpcurl converts JSON into a Protobuf message based on the descriptor. Common rules:

- JSON field names are typically lowerCamelCase corresponding to Protobuf snake_case fields.
- Enums use the symbol names from the contract.
- bytes are represented as Base64 in Protobuf's JSON mapping.
- Nested messages use JSON objects.
- repeated fields use JSON arrays.
- Fields with presence need to be handled according to schema semantics.

You can preview a request template from the descriptor before calling:

```bash
grpcurl -plaintext \
  -msg-template \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder
```

Smoke tests should pick safe methods with deterministic test data that cause no unintended side effects. For write methods, use a test tenant/database or an idempotent request designed for testing.

## 6. Sending metadata and credentials

Many endpoints require a bearer token, API key, or tenant metadata. grpcurl lets you add headers to RPCs:

```bash
grpcurl -plaintext \
  -H 'authorization: Bearer OPERATOR_TOKEN' \
  -H 'x-tenant-id: test-tenant' \
  -d '{"orderId":"ORD-42"}' \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder
```

If the reflection service also requires authentication, grpcurl provides the -reflect-header option to send metadata for reflection requests. Headers for reflection and headers for RPC invocation are two distinct phases; configure them according to server policy.

Do not hardcode long-lived tokens directly in scripts or commit them to repositories. Command lines can appear in shell history or process inspection; use short-lived tokens, CI secret injection, or an organization-approved credential mechanism. Do not log authorization metadata.

Metadata does not by itself establish a trusted identity. The server must verify credentials before attaching principal/role/tenant to the context. An x-tenant-id sent by the caller is only input, not proof that the caller is authorized to access that tenant.

## 7. Testing TLS and mTLS

With TLS, grpcurl must trust the CA that signed the server certificate and connect using a hostname matching a SAN:

```bash
grpcurl -cacert ca.pem \
  orders.example.internal:8443 \
  list
```

If the server requires mutual TLS, also pass the client certificate and private key:

```bash
grpcurl -cacert ca.pem \
  -cert operator-client.pem \
  -key operator-client-key.pem \
  orders.example.internal:8443 \
  list
```

If connecting by IP or a hostname differing from the SAN, configure certificates/authority according to the system's PKI design; do not use -insecure to bypass verification. -plaintext is not a fix for TLS handshake failures in staging/production.

When diagnosing TLS, check:

- Does the CA bundle contain the right trust anchor?
- Is the server certificate valid (unexpired) and does its SAN match the hostname?
- Does the server require a client certificate?
- Is the client certificate signed by a CA trusted by the server?
- Does the proxy/ingress terminate TLS or pass through HTTP/2?
- Does the authority/SNI sent by the client match the listener configuration?

A successful TLS handshake verifies one layer of transport identity; RPC-layer authentication/authorization is still required if the application mandates it.

## 8. Checking the gRPC health service

gRPC has a standard health checking protocol in the grpc.health.v1 package. If the server registers the health service, you can call Check to query the status of the whole server or a specific service:

```bash
# Check overall server status
grpcurl -plaintext \
  -d '{"service":""}' \
  localhost:9090 \
  grpc.health.v1.Health/Check

# Check a specific service
grpcurl -plaintext \
  -d '{"service":"acme.orders.v1.OrderService"}' \
  localhost:9090 \
  grpc.health.v1.Health/Check
```

Responses typically include statuses such as SERVING or NOT_SERVING. For the Check RPC, a service name unknown to the health manager is usually returned as status NOT_FOUND; the SERVICE_UNKNOWN status is used in Watch responses. If the server has not registered the health service, grpcurl will not find the health method even if business services still work.

Health SERVING is a readiness signal per health manager logic, not proof that all business RPCs succeed. Combine health checks with an authorized smoke RPC using appropriate test data.

## 9. Distinguishing endpoint reachability, readiness, and business behavior

An endpoint can pass one check layer while failing at another:

| Layer | How to check | What is proven |
| --- | --- | --- |
| DNS/network | Resolve hostname, open TCP connection | Address is reachable |
| TLS/transport | grpcurl connects over TLS and completes HTTP/2 handshake | Basic transport and trust work |
| Reflection | list/describe | Reflection service returns descriptors |
| Health | grpc.health.v1.Health/Check | Health service publishes status |
| Authentication | Call with valid/invalid credentials | Identity policy is active |
| Business RPC | Call real method with valid request | Routing, handler, and required dependencies work for that case |

Service discovery finds endpoints; health checking reports status; reflection describes APIs; grpcurl combines them into active checks. Do not treat a successful list as proof of readiness, and do not substitute a health response for business testing.

With Kubernetes, service DNS typically points to a ClusterIP or cluster-managed endpoints. grpcurl run from a developer machine, an in-cluster pod, and a CI runner may traverse different network paths. When endpoints are internal-only, run checks from the appropriate network boundary or a controlled operator pod.

## 10. Reading statuses and diagnosing failures

grpcurl results often help isolate failures by layer:

| Symptom/status | Possible cause | Direction to check |
| --- | --- | --- |
| Connection refused | No listener at host/port or wrong port mapping | Service port, target port, pod/listener |
| DNS lookup failure | Wrong hostname or DNS cannot resolve | Namespace, service DNS, resolver/network |
| TLS handshake/certificate error | Wrong CA, SAN, expiry, client certificate, or SNI | Trust chain and TLS configuration |
| Reflection not supported | Reflection not registered or blocked | Use proto/protoset or check policy |
| UNIMPLEMENTED | Wrong service/method path or server did not register method | Proto package, service name, deployed version |
| UNAUTHENTICATED | Missing or invalid credentials | Token, metadata key, expiry, and auth interceptor |
| PERMISSION_DENIED | Valid identity but insufficient permissions | Role, scope, tenant policy |
| INVALID_ARGUMENT | JSON/request violates contract or validation | Field name/type, presence semantics, and validation |
| NOT_FOUND | Business resource does not exist | Test data and resource identifier |
| DEADLINE_EXCEEDED | RPC exceeded deadline or queued/network too slow | Deadline, latency, dependencies, and server load |
| UNAVAILABLE | Server/backend/transport unavailable | Endpoint, health, reconnect, and load balancer |
| RESOURCE_EXHAUSTED | Quota, message limit, or capacity limit | Payload size, rate limit, concurrency, and heap |

Status is only a starting signal for investigation. For example, UNAVAILABLE can originate from client transport, a proxy, or the server; cross-check server logs, metrics, and traces. Do not automatically retry every failure: a write RPC may have already been processed before the response was lost.

## 11. Creating repeatable endpoint smoke tests

A post-deploy smoke test should have a clear order and criteria:

1. Connect to the right hostname/port from the caller's network boundary.
2. Verify TLS/mTLS and operator credentials.
3. Discover services via reflection or use the release-matched descriptor set.
4. Confirm required services/methods exist.
5. Call health Check for the full service name if the health service is enabled.
6. Call a safe unary RPC with test data.
7. Verify status, response, and completion time.
8. Record endpoint, release/version, timestamp, status, and correlation ID; do not log tokens or sensitive payloads.

Minimal shell script example for local plaintext:

```bash
#!/usr/bin/env bash
set -euo pipefail

TARGET="localhost:9090"
SERVICE="acme.orders.v1.OrderService"

grpcurl -max-time 5 -plaintext "$TARGET" list
grpcurl -max-time 5 -plaintext "$TARGET" describe "$SERVICE"
grpcurl -max-time 5 -plaintext \
  -d '{"service":"'"$SERVICE"'"}' \
  "$TARGET" grpc.health.v1.Health/Check
```

This is only a skeleton: replace endpoint, auth, schema, and smoke method per environment. Production-like CI should use TLS, short-lived secrets, finite timeouts, and pinned descriptors/versions. Ensure the script exits non-zero when any step fails so the pipeline does not falsely mark a deployment successful.

Do not invoke a method with side effects merely to prove an endpoint is alive. If you need to verify a business path, create a dedicated health/smoke method or test data that can be safely cleaned up.

## 12. Practice exercise

A Spring gRPC application deploys OrderService on Kubernetes. Local uses plaintext and reflection; staging uses TLS with bearer tokens; production disables reflection and allows only operators via mTLS to inspect the endpoint. After deployment, QA needs to confirm the right service version, health state, and a safe unary method.

**Requirements:**

1. Write grpcurl list and describe commands for local using reflection.
2. Generate a descriptor set with imports to inspect staging/production when reflection is disabled.
3. Invoke GetOrder with a JSON request and appropriate authentication/tenant metadata.
4. Call health Check with the fully qualified service name.
5. Configure grpcurl with CA and mTLS; verify hostname/SAN.
6. Classify the errors UNIMPLEMENTED, UNAUTHENTICATED, PERMISSION_DENIED, DEADLINE_EXCEEDED, and UNAVAILABLE.
7. Create a post-deploy smoke test with timeouts, exit codes, release identifier, and no secret logging.
8. Verify checks run from a network boundary matching real operators/clients.

**Self-check questions:**

- What does grpcurl use reflection for?
- When reflection is disabled, what descriptor sources must be supplied?
- Why is a proto service name different from a DNS target?
- Does a successful list prove business RPCs are ready?
- How does Health SERVING differ from a unary smoke call?
- Which two phases do -H and -reflect-header serve?
- Why should you not use -insecure to fix TLS errors?
- When receiving UNIMPLEMENTED, which service path should you check?
- Why must endpoint tests run from the right network boundary?

**Remember:** grpcurl helps inspect gRPC endpoints from connectivity and descriptors to health and business RPCs. Use reflection where permitted, or pin .proto/protoset files per release; send metadata per contract; verify TLS/mTLS and hostnames; call health alongside a safe smoke method. Read statuses layer by layer and automate checks with proper timeouts, exit codes, versioning, and auditing.

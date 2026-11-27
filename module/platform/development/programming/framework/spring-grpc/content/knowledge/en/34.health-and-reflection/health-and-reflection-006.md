# Server Reflection for Service Discovery

Server reflection is a gRPC protocol that allows clients and operational tools to query a server for the services, methods, and message types it exposes. With reflection, tools such as grpcurl can list APIs, inspect service descriptions, and invoke RPCs without requiring the user to supply the corresponding .proto files in advance.

In Spring gRPC, reflection is useful during development, integration testing, and troubleshooting in deployed environments. It publishes **descriptors of the APIs registered on the server**; it does not locate server addresses, confirm server health, or replace the contract source in a repository. Understand what data reflection returns, how to enable it in the server lifecycle, and its security scope before exposing this endpoint in production.

## 1. What problem does reflection solve?

Normally, clients are generated from known .proto files. However, when inspecting a remote server, an operator may not have the exact proto version or know the service name yet. Reflection lets you query descriptors directly from the server:

- List the services exposed by the server.
- View which RPC methods a service provides.
- Fetch the file descriptor containing a symbol/service.
- Follow dependent proto files to decode request/response types.
- Use discovered schemas to construct JSON requests and invoke RPCs via CLI tools.

For example, instead of finding the proto file in a repository first, an operator can query the server:

```text
grpcurl -plaintext localhost:9090 list
grpcurl -plaintext localhost:9090 describe acme.orders.v1.OrderService
```

The first command lists services; the second shows the service structure published by the server. Reflection helps discover running APIs, which is very useful when comparing staging and production environments or verifying that a rollout deployed the new descriptors to the server.

## 2. What data does the reflection protocol return?

gRPC reflection defines a special service ServerReflection, where the RPC ServerReflectionInfo is a bidirectional streaming call. The client sends discovery requests; the server returns corresponding responses on the same stream.

Common request types:

| Request | Purpose |
| --- | --- |
| list_services | List services published by the server |
| file_containing_symbol | Find the file descriptor containing a service, message, or symbol |
| file_by_filename | Fetch descriptor by proto file name |
| file_containing_extension | Find the file defining an extension |
| all_extension_numbers_of_type | List extension numbers of a message type |

Responses can contain a serialized FileDescriptorProto. Descriptors describe packages, messages, field numbers/types, enums, services, methods, input/output types, and dependencies on other proto files. Tools need to build a descriptor graph from the returned files to fully understand the data types.

Reflection returns schemas/descriptors, not business data from requests or databases. Nor does it guarantee verbatim reconstruction of the .proto files in the repository: formatting, comments, and source details may not be present in the published descriptors.

## 3. Enabling server reflection in grpc-java

The grpc-java reflection implementation resides in the grpc-services artifact. Use a version compatible with the rest of the grpc-java libraries in the application; avoid mixing different grpc API versions.

With a server created directly using grpc-java:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.ProtoReflectionService;

Server server = ServerBuilder.forPort(9090)
    .addService(new OrdersService())
    .addService(new InventoryService())
    .addService(ProtoReflectionService.newInstance())
    .build()
    .start();
```

ProtoReflectionService.newInstance() registers the reflection service on the server. Business services must also be registered on that same server for their descriptors to appear in the list. A service that only exists in a proto file without being registered does not automatically become an active serving service.

If the application uses a Spring gRPC starter to manage the server, register reflection via the BindableService addition or server customizer mechanism supported by your starter version. Do not create a second server just to enable reflection; doing so can open an extra port, use different TLS/auth settings, and cause tools to discover the wrong endpoint. Keep the server and reflection service on the same lifecycle, transport configuration, and access policy.

## 4. Discovering services with grpcurl

When reflection is enabled and the local server uses plaintext:

```bash
# List services
grpcurl -plaintext localhost:9090 list

# List methods of a service
grpcurl -plaintext localhost:9090 list acme.orders.v1.OrderService

# Inspect a service descriptor
grpcurl -plaintext localhost:9090 describe acme.orders.v1.OrderService

# Inspect a message structure
grpcurl -plaintext localhost:9090 describe acme.orders.v1.GetOrderRequest
```

To invoke a unary method, grpcurl can build a message from JSON:

```bash
grpcurl -plaintext \
  -d '{"orderId":"ORD-42"}' \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder
```

JSON field names typically use lowerCamelCase corresponding to Protobuf snake_case fields. grpcurl uses descriptors to resolve fields, data types, and method signatures, then encodes the request into Protobuf wire format.

If the server enables authentication, the tool must send valid credentials according to server policy:

```bash
grpcurl -plaintext \
  -H 'authorization: Bearer TOKEN' \
  localhost:9090 list
```

Do not use plaintext outside controlled local/test environments. In production, configure TLS trust and hostnames matching the certificate.

## 5. Using reflection over TLS and mTLS

Reflection is an RPC on the same gRPC server, so it is governed by the transport security and interceptors/authentication enforced by the server. TLS protects the wire and authenticates the server; TLS by itself does not decide which callers are allowed to read descriptors.

Example querying a server using a certificate trusted by a CA:

```bash
grpcurl -cacert ca.pem \
  orders.example.internal:8443 \
  list
```

If the server requires client certificates (mTLS), provide the certificate and private key as configured for grpcurl:

```bash
grpcurl -cacert ca.pem \
  -cert client.pem \
  -key client-key.pem \
  orders.example.internal:8443 \
  list
```

The hostname used to connect must match a SAN in the certificate or an intentionally configured authority. Do not use -insecure, disable hostname verification, or switch to plaintext to bypass certificate errors. If reflection is protected by an authentication interceptor, send the metadata credentials issued to operational tooling.

## 6. Reflection differs from service discovery and health checking

These three mechanisms answer three different questions:

| Mechanism | Question | Data provided |
| --- | --- | --- |
| Service discovery | Which instance to connect to? | DNS name, IP/port address, or endpoint from registry |
| Health checking | Is the service ready to accept RPCs? | Status such as SERVING or NOT_SERVING |
| Server reflection | Which APIs does the server provide? | Service/method/message descriptors |

Reflection does not locate endpoints and does not report readiness. Successful DNS resolution does not prove the server has the service the client needs; reflection listing a service does not prove business dependencies are healthy. When investigating errors, check target/transport, health state, and service descriptors separately.

Reflection also does not replace generated stubs. Production applications typically continue using clients generated from versioned contracts; reflection is better suited for dynamic discovery, CLI usage, debugging, and administrative tools.

## 7. Security and deciding whether to enable reflection in production

Descriptors can reveal internal service names, administrative methods, request/response structures, and capabilities offered by the system. That information is helpful to operators, but also aids reconnaissance if the endpoint is public.

Before enabling reflection in production, determine:

- Who is allowed to list services and download descriptors?
- Is reflection placed behind TLS/mTLS and authentication?
- Is authorization restricted by operator group or environment?
- Should reflection be exposed on a dedicated internal listener/port?
- Does auditing log the caller, timestamp, and discovery activity as needed?
- Are health probing tools affected by interceptors protecting reflection?

Common choices:

| Environment | Typical appropriate setup |
| --- | --- |
| Local development | Enable reflection so grpcurl and IDEs/tools can discover easily |
| CI/integration test | Enable on test servers to verify registered descriptors and contracts |
| Staging | Enable in a controlled way for dev/QA teams, using production-like TLS and authentication |
| Public-facing production | Disable if there is no operational need; if needed, restrict access tightly |
| Internal production | Can be enabled on internal endpoints, requiring appropriate identity and audit |

Do not treat hiding reflection as an API security measure replacing authentication/authorization. Clients can still invoke known methods if the endpoint allows it; every business RPC must enforce its own access policy.

## 8. When reflection is unavailable

Reflection may be disabled, blocked by authentication, or incompatible across tool versions. In that case, grpcurl can still use proto files or a pre-built descriptor set:

```bash
# Using a proto file and import path
grpcurl -plaintext \
  -import-path ./src/main/proto \
  -proto orders.proto \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder

# Using a compiled descriptor set
grpcurl -plaintext \
  -protoset orders.protoset \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder
```

Descriptor sets are useful for CI and production environments where reflection is disabled. They also ensure tools use the exact contract version that was built and reviewed. However, descriptor set files must be managed/versioned alongside the client; an outdated descriptor may not reflect the live running API.

The reflection protocol has different API versions across ecosystems and release dates. Verify that grpc-java grpc-services and grpcurl are compatible with each other. If the server and tool do not agree on a reflection protocol version, using proto/protoset is a clear way to continue testing.

## 9. Checking descriptors and contract drift

Reflection is very useful for comparing the running API against the expected contract. You can automate a post-deploy smoke test:

1. Connect to the endpoint using TLS and test operator credentials.
2. Call list and confirm required services appear.
3. Call describe for critical services.
4. Confirm expected method names, input types, and output types.
5. Verify required imported descriptors can be queried.
6. Invoke a safe smoke test RPC to verify routing and behavior.

Example CLI check:

```bash
grpcurl -cacert ca.pem \
  -H 'authorization: Bearer TEST_OPERATOR_TOKEN' \
  orders.example.internal:8443 \
  describe acme.orders.v1.OrderService
```

Output should be compared against the reviewed contract or descriptor set. Do not compare raw text output byte-for-byte if grpcurl formatting may change; check the required services/methods/types or compare structured descriptors.

Reflection shows which descriptors the server publishes, but does not prove all methods work properly. A service may be registered and appear in list while methods return UNIMPLEMENTED, UNAVAILABLE, or business errors. Combine descriptor checks with integration/smoke tests.

## 10. Common errors

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| grpcurl list reports reflection not supported | Reflection service not registered or disabled on server | Check server registration and exact endpoint |
| Reflection service appears, but business service is missing | Service not registered on the queried server | Check server instance, port, and service registration |
| describe cannot find symbol | Wrong fully qualified name or dependency descriptor not published | Cross-check proto package/service and imported files |
| TLS handshake fails | Wrong CA, SAN, authority, or client certificate | Check trust chain and hostname |
| UNAUTHENTICATED/PERMISSION_DENIED | Reflection is subject to interceptor/auth policy | Send proper credentials or check operator permissions |
| list succeeds, but calling method fails | Descriptor exists, yet handler/backend fails or request is invalid | Check method path, status, and service logs |
| Works locally, fails in staging | Reflection disabled, network policy, or different protocol version | Check profile-specific config and compatibility |
| Reflection exposes internal APIs | Endpoint exposed more broadly than the operator group | Restrict listener, identity, and authorization |

Always confirm the exact hostname/port you are checking. A successful grpcurl command locally only proves the local server registered reflection; it does not prove staging/production has the same configuration.

## 11. Testing reflection in Spring gRPC

You should test both reflection registration and descriptor content:

| Test case | What to verify |
| --- | --- |
| Reflection registered | list_services returns the reflection service and expected business services |
| Service registration | Unregistered services do not appear |
| Descriptor lookup | describe/symbol lookup returns the right service, methods, and message types |
| Imported proto | Dependency descriptors can be queried completely |
| Unary smoke call | Discovered method can be invoked with the right path/request |
| Reflection disabled | Tools receive a clear reflection error; proto/protoset still works |
| Authentication | Callers missing credentials are rejected per policy |
| Authorization | Operators can discover; unauthorized callers cannot download descriptors if policy requires |
| TLS/mTLS | Trust chain and client identity are verified properly |
| Spring lifecycle | Reflection service is registered on the Spring-managed server and stops with it |
| Version compatibility | grpc-java reflection and CLI tools are compatible |

In-process server tests are suitable for checking registration and the descriptor protocol. Add TCP/TLS integration tests when you need to verify certificates, ingress, service mesh, or authentication metadata over the network. Do not use a test that builds its own standalone ServerBuilder to conclude that the production Spring starter registered reflection properly; call the endpoint via the server/channel created by the Spring context.

## 12. Practice exercise

An operations team needs to verify OrderService in staging after every deployment. Currently the team has to hunt for the right .proto version across multiple repositories; several times grpcurl called the wrong method because the service package changed. Production only allows authenticated operators to view API descriptors.

**Requirements:**

1. Enable ProtoReflectionService on the staging server via Spring gRPC's lifecycle/configuration hook.
2. Use grpcurl to list services and describe acme.orders.v1.OrderService.
3. Invoke a unary smoke method using a JSON request based on the descriptor.
4. Configure production reflection behind TLS/mTLS and operator authorization.
5. Verify that health checking and service discovery continue operating independently of reflection.
6. Create a post-deploy smoke test to verify services/methods/types and detect contract drift.
7. Prepare a descriptor set as a fallback verification method when reflection is disabled or tools are incompatible.

**Self-check questions:**

- What problem does reflection solve when operators lack the matching proto file version?
- Which descriptor query types does ServerReflectionInfo support?
- Why does reflection only list services registered on the server?
- How does reflection differ from service discovery and health checking?
- Does TLS automatically restrict who can download descriptors?
- When should reflection be disabled or restricted in production?
- When reflection is unavailable, what schema sources can grpcurl use?
- Why does a successful list/describe not prove that business RPCs work?

**Remember:** Server reflection allows tools to discover services and descriptors published by a gRPC server. In Spring gRPC, register reflection on the proper server lifecycle, use grpcurl to list/describe/smoke-call, and protect descriptors with TLS and appropriate authentication/authorization. Reflection does not replace service discovery, health checking, or contract sources; test descriptors after deployment and maintain proto/protoset files as versioned contract sources.

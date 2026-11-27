# Unable to Connect to the gRPC Port

## 1. Identify the Failing Layer

In **SPRING_GRPC**, a client calls a service over gRPC using HTTP/2 and a Protocol Buffers contract. When the client reports that it cannot connect to the port, you need to determine whether the error occurs at DNS, TCP, TLS, HTTP/2, or the RPC itself. Each layer has different symptoms and different fixes.

Connection flow:

~~~mermaid
flowchart TD
    A["Client target: host:port"] --> B["DNS / name resolution"]
    B --> C["TCP connection"]
    C --> D["TLS handshake (if TLS is enabled)"]
    D --> E["HTTP/2 + ALPN h2"]
    E --> F["gRPC protocol / service method"]
    F --> G["Application handler"]
    B -->|fail| X["DNS / target error"]
    C -->|refused / timeout| Y["Listener / route / firewall"]
    D -->|fail| Z["Certificate / TLS mode"]
    E -->|fail| H["Proxy / HTTP2 configuration"]
    F -->|status error| I["Authentication / method / application"]
~~~

Do not start by modifying the service implementation when TCP has not even been established. A connection refused error will not be solved by changing protobuf definitions or handler logic.

## 2. Read the Error Message Properly

Messages from gRPC often contain UNAVAILABLE, but this status only indicates that the transport/service is currently unavailable; the specific root cause may lie in DNS, TCP, TLS, a proxy, or a server restart.

| Symptom | Common Meaning | First Check |
|---|---|---|
| Connection refused | The host is reachable, but the port has no listener or a firewall is actively rejecting it | Check the port and bind address on the server |
| Connection timed out | Packets did not receive a response within the wait period | Route, firewall, network policy, destination IP/port |
| UnknownHostException / DNS lookup failed | Hostname cannot be resolved from the client environment | DNS, namespace, service name |
| UNAVAILABLE: io exception | Connection or transport error; read the nested cause | Look for ConnectException, timeout, TLS exception |
| SSLHandshakeException | TCP usually connected, but the TLS handshake failed | Trust chain, SAN, SNI, client certificate |
| ALPN failed to select h2 | TLS may succeed, but HTTP/2 negotiation failed | TLS terminator, proxy, and ALPN |
| UNIMPLEMENTED | Reached a gRPC server, but the method/service does not exist or is not registered | Package, service name, generated stub, server registration |
| UNAUTHENTICATED / PERMISSION_DENIED | Request reached the server or security layer and was rejected | Credential, token, authorization policy |
| DEADLINE_EXCEEDED | Call deadline expired before a result was returned | Slow connection, slow server, queue, or deadline too short |

You must read the nested exceptions as well. Looking only at StatusRuntimeException: UNAVAILABLE is not enough to conclude that the port is closed.

## 3. Confirm the Target Host and Port from the Client Side

First, record the actual target that the client uses, for example grpc.internal.example:9090. Check:

- Does the hostname match the right environment (local, test, staging, production)?
- Is the port the gRPC port or just the Spring Boot HTTP port?
- Is the client running inside a container or Kubernetes pod with its own DNS/network?
- Is the target overridden by an environment variable, profile, or service discovery?
- Is the client using localhost while the server is in another container/pod?

Inside a container, localhost points to that container itself. In Kubernetes, localhost points to the current pod, not automatically to another service. Use the DNS service name and the port exposed by the service.

For example, an application might serve HTTP actuator on 8080 and gRPC on 9090. Calling localhost:8080 with a generated gRPC stub will not turn the HTTP port into a gRPC port. Check the startup logs and effective configuration to see which port is actually opened by the gRPC server.

## 4. Check DNS from the Exact Client Runtime Environment

A hostname resolving on a developer's machine does not prove that a container or pod can resolve it as well. Run the check directly inside the environment hosting the client.

PowerShell:

~~~powershell
Resolve-DnsName grpc.internal.example
~~~

Linux:

~~~bash
getent hosts grpc.internal.example
nslookup grpc.internal.example
~~~

If DNS returns multiple addresses, check that each address has an appropriate route and listener. Service discovery may return stale IPs after an instance changes; check TTL, DNS cache, and endpoint registration.

In Kubernetes, use the DNS name with the correct namespace, for example orders-grpc.backend.svc.cluster.local. If the client and service are in the same namespace, the short name orders-grpc is usually sufficient when cluster DNS is configured normally.

## 5. Confirm the gRPC Server Is Actually Listening

Check the application startup logs. Look for the line indicating that the gRPC server has started and bound to the port successfully. If the server did not start, check exceptions caused by port conflict, misconfiguration, unreadable TLS certificates, or bean/service registration errors.

On Linux:

~~~bash
ss -lntp
ss -lntp | grep ':9090'
~~~

You can use lsof -nP -iTCP:9090 -sTCP:LISTEN if that tool is installed.

On Windows PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 9090 -State Listen
netstat -ano | findstr :9090
~~~

If there is no socket in the LISTEN state, the client cannot connect to that port. Identify the process owning the port and check whether the server started with the right profile/configuration.

If the port is already occupied by another process, the server may fail to bind or be configured to use a different port. Do not look only at server.port; the HTTP server and the gRPC server may have separate port configurations.

## 6. Check the Bind Address

A server bound to 127.0.0.1 or ::1 only accepts loopback connections on the corresponding stack. Clients on another machine, another container, or another pod cannot reach it over an external network interface.

In environments that need to accept connections from the network, the gRPC server typically must bind to an appropriate interface, such as 0.0.0.0 for IPv4 or a specific interface address. Only widen the bind address when network policies and firewalls properly restrict access sources.

Distinguish between:

- 127.0.0.1:9090: IPv4 loopback only.
- [::1]:9090: IPv6 loopback only.
- 0.0.0.0:9090: listens on all IPv4 interfaces.
- [::]:9090: IPv6 wildcard; whether it accepts IPv4 depends on socket/OS configuration.

A common mistake is a server running in a container and binding only to loopback. The port is published to the host, but the process inside the container does not accept connections coming from the container interface. Check both the bind address inside the container and the port mapping.

## 7. Test TCP from the Client to the Exact host:port

Once DNS is right and the server has a listener, test TCP from the same network namespace as the client.

PowerShell:

~~~powershell
Test-NetConnection grpc.internal.example -Port 9090
~~~

Linux:

~~~bash
nc -vz -w 3 grpc.internal.example 9090
~~~

A successful TCP check only proves that a socket can be opened. It does not prove that the server speaks gRPC, has valid TLS, or has working HTTP/2.

If Connection refused, go back to the listener, bind address, port mapping, and firewall. If timeout, check routes, security groups, firewalls, Kubernetes NetworkPolicy, load balancers, and destination address. Do not increase the client deadline to mask a blocked route.

## 8. Check the Port and Configuration in Spring gRPC

Property names depend on the starter and the Spring gRPC version in use. Some systems use properties under the spring.grpc.server.* namespace; older starters or other libraries may use grpc.server.*. Do not copy properties from another project without verifying the dependency actually running.

Check the configuration sources:

1. application.yml/application.properties.
2. Active profiles, for example application-prod.yml.
3. Environment variables and command-line arguments.
4. ConfigMaps/secrets or configuration injected at deployment time.
5. Startup logs and effective configuration if actuator/configuration diagnostics are safely enabled.

Illustrative configuration example for the newer Spring gRPC starter:

~~~yaml
spring:
  grpc:
    server:
      port: 9090
~~~

Illustrative example of the property style commonly found in older starters:

~~~yaml
grpc:
  server:
    port: 9090
~~~

The two examples above belong to different starter ecosystems; do not declare both at the same time just to try to make it run. Determine the exact starter, property binding, and default port in your actual version.

In addition to the port, verify that the server starter is included on the runtime classpath, that the service implementation is registered via the appropriate annotation/configuration, and that there are no startup errors hidden in the logs.

## 9. Containers and Kubernetes: Check Each Layer of Port Mapping

In containers, distinguish between:

1. The port the gRPC process listens on inside the container.
2. The port published/mapped to the host if accessed from outside.
3. The Kubernetes Service port.
4. The targetPort pointing to the container port.

Docker example:

~~~bash
docker ps
docker port orders-service
docker logs orders-service
~~~

If the server listens on 9090 inside the container but does not publish the port, a client from the host cannot reach it via the host port. When using an internal Docker network, the client container should call the service/container name and container port; there is no need to loop through the host's localhost.

In Kubernetes:

~~~bash
kubectl get svc orders-grpc -n backend -o yaml
kubectl get endpointslice -n backend -l kubernetes.io/service-name=orders-grpc
kubectl get pods -n backend -o wide
kubectl logs deploy/orders-service -n backend
~~~

Check the port, targetPort, selector, whether EndpointSlice has Ready endpoints, and whether the pod IP is right. A Service that exists with no Ready endpoints usually leads to failed or rejected connections depending on the network implementation.

Run a probe from a pod under the same network policy:

~~~bash
kubectl exec -n backend deploy/orders-client -- \
  sh -c 'nc -vz orders-grpc 9090'
~~~

If the container image does not have nc, use an ephemeral debug container or tools approved for the environment. Do not arbitrarily install utilities into production images just for diagnostics.

## 10. Distinguish Plaintext from TLS

After TCP connects, client and server must agree on the security mode:

- Server is plaintext but client uses TLS: handshake fails.
- Server is TLS but client uses plaintext: handshake/protocol bytes mismatch, usually reporting a transport error.
- Both use TLS but trust chain, SAN, or SNI is wrong: certificate validation/handshake fails.
- Using mTLS but client certificate is missing or wrong: server rejects the handshake.

Use grpcurl to probe:

~~~bash
# Only use when the server is configured for plaintext.
grpcurl -plaintext grpc.internal.example:9090 list

# TLS with certificate verification against the default trust store.
grpcurl grpc.internal.example:9090 list

# Only for controlled test environments; skips certificate verification.
grpcurl -insecure grpc.internal.example:9090 list
~~~

-insecure is not a production fix. It only helps determine whether the error is related to certificate verification; you must fix trust roots/SAN/SNI and re-enable verification.

If the server does not enable reflection, the list command may report that reflection is unavailable even when the gRPC connection succeeded. In that case, use .proto or a protoset with grpcurl -import-path ... -proto ... describe ... or -d ... to invoke a method. Reflection being disabled does not mean the port is unreachable.

## 11. Check Certificate, SNI, and HTTP/2 ALPN

With TLS, the hostname the client uses to connect must match a Subject Alternative Name (SAN) in the certificate, or there must be an intentional authority override configuration. The certificate chain must be trusted by the client. With mTLS, the server also needs to trust the client certificate.

You can check the handshake and ALPN with OpenSSL:

~~~bash
openssl s_client \
  -connect grpc.internal.example:9090 \
  -servername grpc.internal.example \
  -alpn h2
~~~

Check:

- Is the certificate still valid and is the chain complete?
- Does the SAN contain the hostname used by the client?
- Is SNI sent properly to the TLS terminator?
- Does ALPN select h2?
- If a proxy/load balancer terminates TLS, does it forward upstream over HTTP/2?
- If mTLS, does the client send the corresponding certificate and private key?

gRPC uses HTTP/2. A proxy may open TCP and TLS successfully yet forward upstream using HTTP/1.1, causing the gRPC call to fail after the handshake. Listener/upstream protocol configuration must support HTTP/2 end-to-end or HTTP/2 on each hop according to the topology.

## 12. Use grpcurl to Verify Actual gRPC

Once TCP and TLS are right, use grpcurl to verify the protocol and service:

~~~bash
# List services if reflection is enabled.
grpcurl -plaintext localhost:9090 list

# Inspect a service descriptor via a proto file.
grpcurl -plaintext \
  -import-path ./src/main/proto \
  -proto orders.proto \
  localhost:9090 describe orders.v1.OrdersIngress
~~~

Test calling a method:

~~~bash
grpcurl -plaintext \
  -import-path ./src/main/proto \
  -proto orders.proto \
  -d '{"customerId":"customer-9"}' \
  localhost:9090 \
  orders.v1.OrdersIngress/GetOrder
~~~

The package, service, and method names must match the actual descriptor. If grpcurl connects but the method returns UNIMPLEMENTED, check whether the server registered the right generated service implementation. If it returns UNAUTHENTICATED, transport has reached the security layer; switch to checking credentials instead of continuing to change ports.

Do not use curl http://host:port as the sole test for gRPC. HTTP/2 prior knowledge, TLS, and gRPC framing differ from a regular REST endpoint.

## 13. Check Firewall, Routes, and Load Balancer

If the server is listening properly and TCP probes still time out, inspect the network path:

- Firewall on the server host and client host.
- Cloud security groups/network ACLs.
- Kubernetes NetworkPolicy ingress/egress.
- VPN, subnet routes, NAT, and DNS returning the appropriate internal/external address.
- Load balancer listener, backend pool, health check, and port mapping.
- Does the proxy require HTTP/2, TLS passthrough, or proper TLS termination?

Test from near to far: loopback on the server, server interface IP, container network, pod-to-pod, service DNS, then from the actual client. This helps isolate the first failing layer.

Do not open ports to the entire Internet as a default troubleshooting step. Only allow the necessary client sources, right protocol, and right environment.

## 14. Use Health Checks to Distinguish an Alive Server from Working Methods

An open TCP port only shows that a process is accepting connections. It does not prove that the service is ready to handle business requests.

The gRPC Health Checking Protocol can provide SERVING/NOT_SERVING status for a service. If using health checks, verify:

- The health service is registered and the client/probe calls the right port.
- The status reflects actual readiness, such as required dependencies being ready.
- Kubernetes gRPC probes or load balancer health checks use the right port and service name.
- The health check does not report SERVING too early before the server finishes startup.

NOT_SERVING is a valid gRPC response after a connection has been established. It differs from TCP connection refused. Health checks also do not replace probes for individual RPC methods or authorization checks.

## 15. Step-by-Step Isolation Workflow

Proceed sequentially to avoid changing multiple layers at once:

1. **Record the target and full error:** hostname, port, timestamp, nested exceptions, TLS/plaintext, and client runtime environment.
2. **Check DNS:** resolve from the client's exact container/pod/host.
3. **Check the listener:** did the server start and listen on the right port and right interface?
4. **Probe TCP:** use Test-NetConnection or nc from the same network namespace as the client.
5. **Check port mapping/routes:** container, Kubernetes Service/EndpointSlice, firewall, and load balancer.
6. **Check TLS/ALPN:** certificate, SAN, SNI, mTLS, and h2.
7. **Probe gRPC:** use grpcurl with the right plaintext/TLS mode and descriptor.
8. **Check service/security:** service registration, reflection, authentication, and authorization.

After each step, record the result and only modify the layer where you have evidence of an error. If the TCP probe already succeeded, stop tweaking firewall rules when the actual fault is in the certificate or HTTP/2.

## 16. Symptom and Resolution Table

| Symptom | Common Cause | Resolution |
|---|---|---|
| Works locally, fails from container | Loopback bind, DNS, or port mapping | Bind to the appropriate interface, call the service name, and check mapping |
| Works in container, fails from another pod | Kubernetes Service, NetworkPolicy, or endpoint | Check Service, EndpointSlice, and policy |
| TCP refused | No listener or wrong port | Check startup logs, port, bind address, and process |
| TCP timeout | Firewall, route, security group, or network policy | Probe hop by hop and inspect rules |
| TLS handshake fail | Plaintext/TLS mismatch, certificate, or mTLS | Align modes, check trust chain/SAN/client cert |
| TLS succeeds but gRPC fails | ALPN is not h2, proxy uses HTTP/1.1 | Fix HTTP/2 upstream/ALPN |
| grpcurl list reports reflection unavailable | Reflection is not enabled | Use .proto/protoset or enable reflection in an appropriate environment |
| UNIMPLEMENTED | Wrong package/service/method or implementation not registered | Check descriptor and server registration |
| UNAUTHENTICATED | Missing/invalid credential | Check token, TLS identity, and interceptor |
| DEADLINE_EXCEEDED | Connect or processing exceeded deadline | Measure time per layer; set a reasonable deadline |

## 17. Common Diagnostic Mistakes

| Wrong Practice | Why It Is Ineffective | Right Practice |
|---|---|---|
| Changing server.port without identifying the gRPC port | HTTP and gRPC may use separate ports | Verify the property of the right starter |
| Calling localhost from a container to reach the host/another service | Loopback points to the container itself | Use DNS/service name or proper host mapping |
| Only checking the port on the server machine | Client may be blocked by a route/firewall | Probe from the client's exact network namespace |
| Seeing UNAVAILABLE and concluding the server is down | Status covers many transport errors | Read nested causes and break down by layer |
| Using curl to conclude gRPC works | Does not verify gRPC framing/service | Use grpcurl or a gRPC client |
| Disabling TLS verification as a production fix | Masks trust/SAN issues and weakens security | Install proper trust chain and certificates |
| Assuming grpcurl list error means the port is closed | Reflection may just be disabled | Call a method using proto/protoset |
| Increasing deadline on TCP timeout | Does not fix routes or listeners | Fix the connectivity root cause |

**Remember:** Diagnose gRPC ports layer by layer: DNS → TCP → TLS/ALPN h2 → gRPC service → application. Verify the right target, listener, and bind address from the server environment; probe TCP from the client environment; check port mappings, routes, firewalls, and Kubernetes endpoints; then use grpcurl to confirm gRPC. Distinguish connection refused, timeout, TLS failure, and gRPC status to fix the right layer without changing configuration blindly.

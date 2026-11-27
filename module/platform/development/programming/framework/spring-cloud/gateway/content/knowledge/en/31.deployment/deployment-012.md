# Distinguishing Kubernetes Ingress, Gateway API, and Spring Cloud Gateway

## 1. Three Easily Confused Names, Three Distinct Roles

In a microservices system, there are multiple ways to route HTTP/HTTPS traffic from the Internet to services running on Kubernetes. Three terms often appear side by side: **Kubernetes Ingress**, **Kubernetes Gateway API**, and **Spring Cloud Gateway**. All three relate to request routing, yet they are **not three names for the same technology**.

- **Kubernetes Ingress** is a **standard Kubernetes API resource** describing basic rules for exposing HTTP/HTTPS traffic from outside the cluster to internal `Service` objects. It requires an **Ingress controller** to execute those rules.
- **Kubernetes Gateway API** is a more modern **family of API resources and role-oriented traffic configuration model**, featuring objects such as `GatewayClass`, `Gateway`, `HTTPRoute`, and `ReferenceGrant`. It also requires a supporting **controller/data plane implementation**.
- **Spring Cloud Gateway (SCG)** is an **API Gateway application/framework built on Spring Boot**, where developers declare route predicates, filter chains, path/header rewriting, service discovery, authentication, rate limiting, circuit breakers, retries, and request policies. It can run **inside or outside Kubernetes**, behind Ingress/Gateway API or directly behind a load balancer.

The first two describe **Kubernetes routing infrastructure**; the third is an **application gateway** operated as a workload. Despite sharing the word "Gateway", a Gateway API `Gateway` resource is **not** a bean, route, or Deployment of Spring Cloud Gateway.

~~~mermaid
flowchart TD
    Internet["Internet client"] --> Edge{"Choose an edge entrypoint"}
    Edge --> Ingress["Ingress resource + Ingress controller"]
    Edge --> KG["Gateway API resources + Gateway controller"]
    Ingress --> Svc["Kubernetes Service: spring-gateway"]
    KG --> Svc
    Svc --> SCG["Spring Cloud Gateway application"]
    SCG --> Catalog["Catalog service"]
    SCG --> Orders["Orders service"]
    SCG --> Identity["Identity service"]
~~~

The diagram illustrates **two alternative architectures at the edge**: you typically do not run both Ingress and Gateway API competing for the same public hostname/listener in a production environment. Spring Cloud Gateway is an **optional application layer** behind the edge controller, not a mandatory component for Ingress or Gateway API to function.

### Learning Objectives

After this lesson, you will be able to:

1. Explain how an API resource differs from a **controller** and a **data plane**.
2. Read `Ingress`, `GatewayClass`, `Gateway`, `HTTPRoute` YAML, and Spring Cloud Gateway route YAML.
3. Identify where responsibilities lie for **public DNS, TLS termination, host/path routing, authentication, rewriting, retries, circuit breaking, and traffic observability**.
4. Design both cases: **Ingress/Gateway API routing directly to services** and **edge -> Spring Cloud Gateway -> backend**.
5. Understand role separation between **platform teams and application teams**, `allowedRoutes`, `parentRefs`, `backendRefs`, and `ReferenceGrant`.
6. Avoid confusing SCG's `lb://service` with `backendRefs` pointing to a Kubernetes `Service`.
7. Analyze TLS/headers/path flows to avoid double rewrites, auth bypasses, spoofed forwarding headers, and proxy loops.
8. Test route acceptance, backend reachability, failover, canary, rollout/rollback, and operate within actual controller capabilities.

> **Scope:** This lesson belongs to the **Deployment** chapter of the **SPRING_CLOUD_GATEWAY** module. Spring Cloud Gateway examples focus on **Server WebFlux**, while explicitly noting differences for **Server Web MVC**. Kubernetes APIs and extension/controller features vary by version; never assume every Ingress or Gateway API controller supports the same features, annotations, or CRDs.

## 2. Architectural Model: API, Controller, and Data Plane

A Kubernetes resource is a **declaration of desired state**, not a running process that receives HTTP requests on its own.

~~~mermaid
flowchart LR
    User["Platform/App team"] -->|"kubectl apply"| API["Kubernetes API server"]
    API -->|"watch resources"| Ctrl["Ingress/Gateway controller"]
    Ctrl -->|"reconcile config"| Proxy["Reverse proxy / cloud LB / data plane"]
    Client["HTTP client"] --> Proxy
    Proxy --> Ksvc["Kubernetes Service"]
    Ksvc --> Pods["Workload Pods"]
~~~

### 2.1. An Ingress resource is not an Ingress controller

A `kind: Ingress` only declares hosts/paths/backends, TLS, and a few standard fields. An **Ingress controller** watches that resource and configures NGINX, Envoy, HAProxy, a cloud load balancer, or another data plane depending on the product. If a cluster has no controller handling the matching `IngressClass`, the YAML may still be accepted by the Kubernetes API server, **yet Internet requests will not be routed**.

### 2.2. A Gateway API resource is not a Gateway controller

A `kind: Gateway` declares listeners/addresses/TLS and how routes attach; `kind: HTTPRoute` declares HTTP routing rules. A **Gateway controller** interprets and reconciles those objects, potentially provisioning a data plane from a cloud LB, proxy, or service mesh. Gateway API does not mandate that all controllers use the same underlying proxy.

**Installing CRDs without a controller does not create a working Gateway**. Likewise, having a controller installed does not activate a `GatewayClass` whose `controllerName` belongs to a different controller.

### 2.3. Spring Cloud Gateway is the actual HTTP-receiving process

SCG is a Spring Boot application deployed as a `Deployment`/`Pods` (or container/VM). It receives HTTP requests directly, selects a route using **Spring Cloud Gateway route definitions**, and calls upstream backends via its HTTP client. A Kubernetes `Service` provides a stable address so the edge controller can forward requests to SCG Pods.

~~~text
Kubernetes control plane:
  Ingress or Gateway/HTTPRoute objects
           |
           v
  Controller reconciles edge proxy

Request data path:
  Client -> Edge proxy -> K8s Service -> Spring Cloud Gateway Pod
                                         -> Catalog/Orders Service -> Pods
~~~

**Crucial distinction:** Having an `HTTPRoute` accepted by the Kubernetes API server does not guarantee the Spring Cloud Gateway application has a matching route configured. Conversely, having an SCG route loaded in the JVM does not prove Internet clients can reach SCG through the Service/Ingress/Gateway API.

## 3. Quick Comparison by Responsibility

| Criterion | Kubernetes Ingress | Kubernetes Gateway API | Spring Cloud Gateway |
| --- | --- | --- | --- |
| Nature | Kubernetes API resource `Ingress` | Family of Kubernetes API resources/CRDs | Java/Spring Boot application and library |
| Needs implementation? | **Ingress controller** | **Gateway API controller** + data plane | **Spring Boot runtime**, outbound HTTP client |
| Runs outside Kubernetes? | Not in the Kubernetes API sense | Not in the Kubernetes API sense | Yes |
| Platform/app role split | Relatively limited in core API; often relies on RBAC/annotations | Explicitly designed across `GatewayClass`, `Gateway`, and `HTTPRoute` | Depends on repository, team, and deployment layout |
| Public entrypoint | Usually provisioned by controller/LB | Provisioned by Gateway controller/data plane | Via Service/LB/Ingress/Gateway API or directly if exposed |
| Host/path HTTP routing | Yes, basic level | Yes, richer route rules by type and conformance | Yes, via route predicates |
| Header/method/query matching | Depends on controller/annotations; core Ingress is limited | `HTTPRoute` supports structured matching | Yes, via predicate factories |
| Rewrites/redirects/response headers | Usually controller-specific annotations | Filters per Gateway API feature/conformance | Gateway filter factories/custom code |
| Service target | Kubernetes `Service` | `backendRefs` (typically `Service`) | HTTP URIs, `lb://` with discovery integration |
| JWT/auth/business authorization | Usually depends on controller/extensions | Depends on controller/policy extensions, not built-in by default | Spring Security + backend authorization |
| Retry/rate limit/circuit breaker | Controller-specific | Depends on supported features/policies | Version-appropriate integrations and filter factories |
| TLS termination | Controller/LB per TLS configuration | Gateway listener/certificate refs | Can terminate TLS itself if exposed; outbound TLS is independent |
| Configuration updates | `kubectl apply` Ingress | `kubectl apply` Gateway API objects | App config/route source, rollout or refresh by design |
| Observability unit | Ingress controller, LB metrics/logs | Gateway controller/data plane metrics/status | Actuator/Micrometer/traces/HTTP client/route ID |
| Typical use | Standardized HTTP/HTTPS ingress | Shared edge routing, delegated ownership, explicit policies | API gateway needing app logic, security, and deep filters |

**No single technology automatically replaces the other two in all cases.** An organization can migrate from Ingress to Gateway API while keeping SCG applications behind it, or omit SCG for APIs where the edge controller already handles all required policies.

## 4. Kubernetes Ingress: Basic HTTP/HTTPS Routing

Ingress is provided by the `networking.k8s.io/v1` Kubernetes API. At the standard level, an Ingress describes **host/path -> Kubernetes Service** mappings and TLS configuration referencing a Secret. It requires an Ingress controller, typically selected via `ingressClassName`.

### 4.1. Example Ingress to Spring Cloud Gateway

Assume SCG already has a `Service` named `spring-gateway` in namespace `edge` exposing port `8080`. The cluster's Ingress controller advertises an `IngressClass` named `public-nginx` (an **illustrative** name; replace it with your cluster's actual class).

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-entry
  namespace: edge
spec:
  ingressClassName: public-nginx
  tls:
    - hosts:
        - api.example.test
      secretName: api-tls
  rules:
    - host: api.example.test
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: spring-gateway
                port:
                  number: 8080
~~~

Expected path:

~~~text
GET https://api.example.test/api/catalog/items/42?lang=vi
         |
Ingress controller, host + Prefix /api
         |
Kubernetes Service edge/spring-gateway:8080
         |
Spring Cloud Gateway Pod, receives /api/catalog/items/42
         |
SCG route selects Catalog service
~~~

**Notes:**

1. `pathType: Prefix` uses **path-segment** semantics, not arbitrary byte-string prefix matching. For example, `/api` matches `/api` and `/api/catalog`, and should not be assumed to match arbitrary strings beginning with `api` like `/apix`.
2. This Ingress YAML **does not rewrite the path**. The client path is forwarded to SCG per controller behavior; **do not assume the `/api` prefix is stripped automatically**.
3. `secretName: api-tls` points to a TLS Secret in the same namespace as the Ingress per Kubernetes/controller rules; the Secret must exist, match the certificate host, and be readable by the controller. Never commit private keys to documentation or unprotected Git repositories.
4. `ingressClassName` must match an actual controller; do not copy NGINX class names when using a different cloud provider controller.
5. Public DNS must point to the address provisioned by the controller/load balancer. **A successful `kubectl apply` does not automatically create DNS records**.

### 4.2. What are the limitations of core Ingress?

The core Ingress API focuses on relatively basic HTTP host/path routing and TLS. Capabilities such as complex rewrites, JWT validation, rate-limit policies, header modification, or canaries are **typically implemented via controller-specific annotations, CRDs, or proxy settings**. The exact same annotation can be ignored or behave differently when switching controllers.

Kubernetes has announced that the Ingress API is **feature-frozen**, meaning new routing features are not being added there; Gateway API was created to model broader requirements. That **does not mean existing Ingress deployments stop working** or that every cluster must migrate immediately. Migration decisions depend on controller support, operational goals, and system risk.

### 4.3. When is Ingress still a valid choice?

Ingress remains reasonable if your organization already operates a well-maintained controller, needs primarily **TLS termination + straightforward host/path routing**, meets requirements with existing policies, and gains little from migrating. Still verify vendor version support and roadmaps to avoid relying on unmaintained annotations.

## 5. Kubernetes Gateway API: Key Objects

Gateway API uses a **role-oriented** model for ingress and mesh traffic. For HTTP ingress, common objects include:

| Resource | Typical owner | Role |
| --- | --- | --- |
| `GatewayClass` | Platform/cluster operator | Selects controller implementation via `spec.controllerName` |
| `Gateway` | Platform/network team | Defines listeners, ports, hostnames, TLS, and how routes attach |
| `HTTPRoute` | App/API-owning team | HTTP matching, filters, backend refs; attaches via `parentRefs` |
| `ReferenceGrant` | Owner of the **referenced target** namespace | Permits specific cross-namespace object references |
| `Service` | App/platform team | Kubernetes destination called by an `HTTPRoute` or edge proxy |

**Gateway API is a set of APIs, not a standalone Gateway binary.** Installing CRDs and creating a `GatewayClass` or `HTTPRoute` without a supporting controller/data plane will not forward traffic.

### 5.1. Relationship: GatewayClass -> Gateway -> HTTPRoute

~~~mermaid
flowchart TD
    GC["GatewayClass: controllerName"] --> GW["Gateway: HTTPS listener :443"]
    GW -->|"parentRefs + allowedRoutes"| R1["HTTPRoute: /api/catalog"]
    GW -->|"parentRefs + allowedRoutes"| R2["HTTPRoute: /api/orders"]
    R1 --> S1["Kubernetes Service: catalog"]
    R2 --> S2["Kubernetes Service: orders"]
~~~

`GatewayClass` identifies which gateway controller is responsible. `Gateway` is a **declarative instance** defining specific listeners and endpoints. `HTTPRoute` only describes **request matching and routing behavior**, allowing multiple teams to manage their own `HTTPRoute`s attached to a shared `Gateway` under platform policy.

### 5.2. Control plane vs. data plane roles

When an operator updates an `HTTPRoute`, the Kubernetes API server stores the object, the Gateway controller reconciles state, and it updates the reverse proxy or LB. Live requests pass through the **data plane** (Envoy, NGINX, cloud LB, etc.), **not through the Kubernetes API server** on every HTTP request.

A **controller-managed Gateway** still requires monitoring, Kubernetes RBAC, and operational care. Reconciliation failures can leave a resource stored in Kubernetes without being programmed into the data plane; inspect status conditions rather than trusting the exit code of `kubectl apply`.

## 6. Gateway API Example: Same Goal as Ingress, Different Structure

Assume the organization has installed **Gateway API CRDs** and a controller supporting `GatewayClass`, `Gateway`, and `HTTPRoute`. The example below uses `controllerName: example.net/gateway-controller` **strictly as a placeholder**; replace it with the value published by your real controller.

### 6.1. Platform-managed GatewayClass

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: public-http
spec:
  controllerName: example.net/gateway-controller
~~~

`GatewayClass` is **cluster-scoped**, not namespaced. A real controller must claim that `controllerName`; otherwise, creating the resource **creates no active listener or proxy**. Some controllers also require additional parameters, installation steps, or config beyond this manifest.

### 6.2. Platform-managed Gateway HTTPS listener

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: public-api
  namespace: edge
spec:
  gatewayClassName: public-http
  listeners:
    - name: https
      hostname: api.example.test
      port: 443
      protocol: HTTPS
      tls:
        mode: Terminate
        certificateRefs:
          - kind: Secret
            name: api-tls
      allowedRoutes:
        namespaces:
          from: Same
~~~

This setup requires a valid TLS Secret named `api-tls` in namespace `edge` and a controller configured to serve the listener. `allowedRoutes.namespaces.from: Same` allows only `HTTPRoute`s from the **same namespace as the Gateway** to attach to that listener under this policy. It does not grant broad cross-namespace permissions.

### 6.3. Application HTTPRoute

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: app-api
  namespace: edge
spec:
  parentRefs:
    - name: public-api
      sectionName: https
  hostnames:
    - api.example.test
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api
      backendRefs:
        - name: spring-gateway
          port: 8080
~~~

This `HTTPRoute` has the **same basic intent** as the Ingress in Section 4: HTTPS traffic for `api.example.test/api/**` is forwarded by the controller to Kubernetes Service `edge/spring-gateway:8080`. However, **do not treat it as a 100% identical translation** for route precedence, redirects, TLS policies, proxy timeouts, headers, or metrics across implementations.

### 6.4. Reading each HTTPRoute field

| Field | Purpose | Common mistake |
| --- | --- | --- |
| `parentRefs` | Selects the Gateway/listener to attach the `HTTPRoute` | Assuming referencing a Gateway means the Gateway permits attachment |
| `sectionName: https` | Selects the listener named `https` | Mistaking it for `protocol` or a `Service` name |
| `hostnames` | Constrains hostnames served by the route | Assuming this field provisions public DNS or TLS certs |
| `matches.path.type: PathPrefix` | Matches path prefix per Gateway API semantics | Assuming the Gateway strips the prefix automatically |
| `backendRefs.name` | Selects the Kubernetes backend `Service` | Confusing it with Spring Cloud Gateway's `lb://` service ID |
| `backendRefs.port` | Port on the referenced **Service** | Entering `containerPort` even when the `Service` does not expose it |

**Never deploy both the Section 4 Ingress and the Section 6 Gateway API targeting the same `api.example.test` in a live system and let two edge load balancers compete.** During migration, use a DNS/canary plan, a separate test endpoint, or phased traffic shifting; the sample YAML manifests demonstrate **each option independently**.

### 6.5. Gateway API does not guarantee every advanced filter

Gateway API models structured HTTP matching and filters more richly than core Ingress, yet **feature support depends on the Gateway API release and controller conformance**. Features are categorized as Core, Extended, or Implementation-specific. For instance, URL rewriting, header modification, request mirroring, or timeout/retry policies may vary in conformance and implementation support.

Check your **controller's conformance report and status** before relying on a feature—never assume a controller implements a filter simply because the API server accepts the CRD field.

## 7. Gateway API Role Separation Between Platform and Application Teams

A core architectural benefit of Gateway API is separating two layers clearly:

- **Platform team** owns listeners, ports, TLS termination, public addresses, `GatewayClass`, and route attachment policies.
- **Application team** owns path/method/header/backend rules inside `HTTPRoute` within its permitted namespace and RBAC scope.

Example:

~~~mermaid
flowchart TD
    P["Platform team: edge namespace"] --> GW["Gateway + HTTPS listener"]
    P --> AR["allowedRoutes policy"]
    A["Catalog team: apps namespace"] --> R["HTTPRoute /api/catalog"]
    AR -->|"allows namespace attachment"| R
    R -->|"backendRefs"| S["Catalog Service in apps"]
    GW --> DP["Gateway controller data plane"]
    R --> DP
~~~

By default, `allowedRoutes.namespaces.from: Same` from the earlier example blocks routes in `apps` from attaching. For **selective delegation**, the platform can use a **namespace selector** paired with controlled namespace labels.

### 7.1. Allowing an application namespace to attach routes

Example **replacing** the `allowedRoutes` block on the Gateway listener:

~~~yaml
allowedRoutes:
  namespaces:
    from: Selector
    selector:
      matchLabels:
        gateway-access: "approved"
~~~

Namespace `apps` is allowed to attach only when it carries the label `gateway-access=approved` managed by an **authorized owner**. Never let arbitrary developers apply sensitive namespace labels if those labels control access to public Gateways.

An `HTTPRoute` in namespace `apps` can then attach to the Gateway in `edge`:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: catalog-api
  namespace: apps
spec:
  parentRefs:
    - name: public-api
      namespace: edge
      sectionName: https
  hostnames:
    - api.example.test
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api/catalog
          method: GET
      backendRefs:
        - name: catalog-service
          port: 8080
~~~

Here, the `HTTPRoute` and `catalog-service` live in the **same `apps` namespace**, so `backendRefs` does not require a cross-namespace `ReferenceGrant` just to reference that `Service`. Still, the route must be allowed to attach to the listener via `allowedRoutes`.

### 7.2. How allowedRoutes differs from ReferenceGrant

These two mechanisms enforce **two distinct boundaries**:

| Mechanism | Question answered | Where does it live? |
| --- | --- | --- |
| `Gateway.spec.listeners[].allowedRoutes` | Which namespaces/route kinds may **attach to this Gateway listener**? | On the platform-managed `Gateway` |
| `ReferenceGrant` | May an `HTTPRoute`/object in another namespace **reference a backend/object in the target namespace**? | Inside the **referenced target namespace** |
| Kubernetes RBAC | Who may create/edit `Gateway`/`HTTPRoute`/`Secret`/`ReferenceGrant`? | Cluster/namespace permissions |
| NetworkPolicy | Which Pods may connect to which Pods/services over the network? | Network enforcement plugin |
| Spring Security | Which principals may call business APIs? | SCG/application runtime and backends |

**Being allowed to attach to a Gateway does not grant permission to target any cross-namespace Service**, and **`ReferenceGrant` does not replace Spring Security**.

## 8. ReferenceGrant When the Backend Is in Another Namespace

A common scenario: the Catalog team manages an `HTTPRoute` in `apps`, yet wants to route to the platform-owned `Service edge/spring-gateway`. This is a **cross-namespace backend reference**.

### 8.1. HTTPRoute in apps referencing a Service in edge

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: catalog-via-spring-gateway
  namespace: apps
spec:
  parentRefs:
    - name: public-api
      namespace: edge
      sectionName: https
  hostnames:
    - api.example.test
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api/catalog
      backendRefs:
        - name: spring-gateway
          namespace: edge
          port: 8080
~~~

### 8.2. ReferenceGrant in the Service-owning namespace

The resource below must be **approved by the owner of namespace `edge`**, not created by an `apps` developer inside `apps`:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1beta1
kind: ReferenceGrant
metadata:
  name: allow-catalog-routes-to-gateway-service
  namespace: edge
spec:
  from:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      namespace: apps
  to:
    - group: ""
      kind: Service
      name: spring-gateway
~~~

`ReferenceGrant` has its own API version depending on the **installed Gateway API CRDs** (many releases use `v1beta1` for `ReferenceGrant` even when `Gateway`/`HTTPRoute` use `v1`). Before applying, check `kubectl api-resources` or the CRD versions served by your cluster rather than assuming all resources share `v1`.

### 8.3. Both independent conditions must hold

1. **Gateway listener attachment**: `edge/public-api` allows namespace `apps` and matching `HTTPRoute`s to attach via `allowedRoutes`.
2. **Backend cross-namespace reference**: `edge` permits `HTTPRoute`s in `apps` to reference `Service spring-gateway` via `ReferenceGrant`.

If either is missing, the `HTTPRoute` may exist in the cluster without being programmed by the controller with a valid backend; inspect `status.parents[].conditions` such as `Accepted` and `ResolvedRefs` per your controller/API version. Never grant `cluster-admin` privileges as a "quick fix" for rejected attachments or references.

### 8.4. Least-privilege scoping

`ReferenceGrant` restricts by source group/kind/namespace and target kind/name in the schema—it is **not per-HTTP-path RBAC**. Layered controls are still required:

- Limit attachable namespaces using platform-controlled labels.
- Permit references only to **explicitly named `Service` objects** rather than all Services.
- Use RBAC to prevent application teams from modifying platform `Gateway`, Certificate `Secret`, or `ReferenceGrant` objects.
- Review `HTTPRoute` rules to avoid shadowing administrative paths owned by other teams.
- NetworkPolicy and backend authentication continue enforcing connectivity and authorization even when a route reference is permitted.

## 9. HTTPRoute Can Target Backends Directly or Route Through Spring Cloud Gateway

The same public API can follow **two patterns**.

### Pattern A — Gateway API directly to business services

~~~mermaid
flowchart LR
    C["Client"] --> E["Gateway API data plane"]
    E -->|"HTTPRoute /api/catalog"| Catalog["Catalog Service"]
    E -->|"HTTPRoute /api/orders"| Orders["Orders Service"]
~~~

This pattern works well when the controller and policy ecosystem satisfy requirements: TLS, HTTP routing, header handling, and verified edge policies. Benefits include **one fewer proxy hop** and fewer application workloads to operate.

### Pattern B — Gateway API/Ingress to Spring Cloud Gateway

~~~mermaid
flowchart LR
    C["Client"] --> E["Ingress or Gateway API data plane"]
    E --> S["Service spring-gateway:8080"]
    S --> G["Spring Cloud Gateway"]
    G -->|"Route/Filters"| Catalog["Catalog Service"]
    G -->|"Auth/Rate limit"| Orders["Orders Service"]
~~~

This pattern fits when SCG supplies **application-specific routing/filters/security**, leverages existing Java/Spring integrations, or transforms varied API contracts. However, it adds an HTTP hop along with potential **TLS handshakes, buffering, queueing, connection pools, telemetry, and another failure point**.

### No single universal winner

| Question | If the answer is "yes" | Design implication |
| --- | --- | --- |
| Need only simple host/path routing and TLS? | Yes | Ingress or Gateway API may be sufficient |
| Need delegated route ownership across namespaces/teams? | Yes | Gateway API usually provides a clearer model |
| Need custom Java filters or deep Spring Security/business integration? | Yes | Consider Spring Cloud Gateway |
| Does the edge controller already support audited auth/rate limiting? | Yes | Avoid duplicating those policies in SCG |
| Need route predicates/rewrites tightly coupled to application contracts? | Yes | SCG may be the right layer |
| Extremely latency/resource-sensitive and SCG adds no value? | Yes | Evaluate removing the extra proxy hop |
| Running across multiple deployment environments or outside Kubernetes? | Yes | SCG carries portable app logic, though edge infra is still needed |

**Never treat Spring Cloud Gateway as "mandatory" just because this module focuses on SCG**; good deployment architecture justifies each layer's distinct responsibility and value.

## 10. How Spring Cloud Gateway Executes Routes

In **Server WebFlux**, SCG runs on the Spring WebFlux/reactive runtime: route predicates match incoming requests, `GatewayFilter`/`GlobalFilter` chains process them, and an outbound HTTP client calls the backend.

An example configuration **on a release supporting `spring.cloud.gateway.server.webflux.routes`**:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-read
              uri: http://catalog-service.apps.svc.cluster.local:8080
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie

            - id: orders-read
              uri: http://orders-service.apps.svc.cluster.local:8080
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
~~~

Assumed flow:

~~~text
Client GET /api/catalog/items/42?lang=vi
  -> Ingress/Gateway API (NO rewrite)
  -> Service spring-gateway:8080
  -> SCG Path=/api/catalog/**; Method=GET
  -> StripPrefix=1: /catalog/items/42?lang=vi
  -> RemoveRequestHeader Authorization and Cookie
  -> GET http://catalog-service.apps.svc.cluster.local:8080/catalog/items/42?lang=vi
~~~

In Kubernetes, a URI such as `http://catalog-service.apps.svc.cluster.local:8080` resolves directly via **Kubernetes Service DNS**. Switching to `lb://catalog-service` requires a matching **Spring Cloud LoadBalancer + `ServiceInstance`/discovery integration**. `lb://` **does not work automatically merely because the app runs on Kubernetes**.

### 10.1. Configuration namespaces vary by version

In earlier releases, you may encounter `spring.cloud.gateway.routes` instead of `spring.cloud.gateway.server.webflux.routes`. For Server Web MVC, it may be `spring.cloud.gateway.server.webmvc.routes` or `spring.cloud.gateway.mvc.routes` depending on the release. **Never copy configuration from one variant into another and assume routes are registered**.

### 10.2. WebFlux vs. Web MVC differ fundamentally

| Gateway Server WebFlux | Gateway Server Web MVC |
| --- | --- |
| Spring WebFlux, Reactor-based routing/filter chain | Spring MVC/Servlet, WebMvc.fn |
| Reactive `GatewayFilter`/`GlobalFilter` | MVC before/handler/after filters, Servlet Filters |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| Reactor Netty outbound HTTP in standard setups | HTTP client/request factory per MVC version |
| Reactive backpressure, `Mono`/`Flux` | Servlet request processing/async/streaming semantics |

Both variants can be exposed behind Ingress or Gateway API, yet they **do not share the same dependencies, APIs, or config contract**. Never mix reactive `GlobalFilter`s into a Gateway Server Web MVC project.

### 10.3. SCG routes alone do not protect backends

`Path=/api/orders/**` and `Method=GET` are **routing predicates**, not proof that a caller is authorized to read orders. SCG needs proper Spring Security rules, and the Orders backend must still enforce token audience, scope, tenant, and resource ownership; if backends are reachable directly inside the cluster, network and security layers must block bypasses.

## 11. Which Layer Should Match Paths, Rewrite Paths, and Set Headers?

In a two-hop gateway architecture, an HTTP request undergoes **two route selections and two passes of path/header processing**. The most common pitfall is having both Ingress/Gateway API and SCG strip the same prefix without an explicit contract.

### 11.1. Simple rule: one owner per transformation

Suppose the client calls:

~~~text
GET https://api.example.test/api/catalog/items/42?lang=vi
~~~

The Catalog backend only exposes:

~~~text
GET /catalog/items/42?lang=vi
~~~

An easily testable design:

~~~mermaid
flowchart LR
    C["Client /api/catalog/items/42"] --> E["Ingress or Gateway API: match /api, NO rewrite"]
    E --> G["SCG: Path=/api/catalog/**; StripPrefix=1"]
    G --> U["Catalog receives /catalog/items/42"]
~~~

Then:

| Layer | Incoming path | Action | Outgoing path |
| --- | --- | --- | --- |
| Edge Ingress/Gateway API | `/api/catalog/items/42` | Match host/path only | `/api/catalog/items/42` |
| Spring Cloud Gateway | `/api/catalog/items/42` | `StripPrefix=1` | `/catalog/items/42` |
| Catalog backend | `/catalog/items/42` | Handle business GET | Response |

**Anti-pattern:** The Gateway API controller rewrites `/api/catalog` to `/catalog`, while SCG still expects `Path=/api/catalog/**`. The result may be a 404 at SCG rather than from the backend. Worse, if SCG has a catch-all route, the request could be routed to the **wrong backend**.

### 11.2. Is Gateway API URLRewrite always available?

Gateway API defines filters such as `URLRewrite` in `HTTPRoute`, though actual support and exact semantics must be verified against **controller feature conformance**. A conditional example:

~~~yaml
# A snippet inside an HTTPRoute rule; use only when the controller supports URLRewrite.
matches:
  - path:
      type: PathPrefix
      value: /api/catalog
filters:
  - type: URLRewrite
    urlRewrite:
      path:
        type: ReplacePrefixMatch
        replacePrefixMatch: /catalog
backendRefs:
  - name: catalog-service
    port: 8080
~~~

This snippet fits the **Gateway API calling Catalog directly** pattern when Catalog expects `/catalog/...`. Do not combine it with an SCG route expecting `/api/catalog` unless you update SCG's contract accordingly. For core Ingress, rewriting usually relies on controller-specific annotations or extensions rather than a single portable cross-controller syntax.

### 11.3. Matching methods, headers, and queries at each layer

Gateway API `HTTPRoute` offers structured HTTP matchers for methods, headers, and query parameters per spec/controller support; Spring Cloud Gateway provides predicate factories such as `Method`, `Header`, and `Query`. If the edge only matches `PathPrefix=/api` while SCG only permits `GET` for Catalog, a POST passes the edge and fails to match at SCG; the resulting status depends on security/error handlers and any fallback routes.

**Never treat an unmatched route at the edge as an authorization control**. Always enforce Spring Security/backend checks for private/admin APIs, and test base paths, trailing slashes, encoded slashes, case normalization, and unexpected HTTP methods.

### 11.4. Which layer owns which headers?

| Header/metadata | Suggested control point | Why |
| --- | --- | --- |
| `X-Forwarded-Proto`, `Forwarded` | **Trusted** proxy/ingress at the network edge | Never trust client-supplied values |
| `X-Request-ID`/trace context | One owner for correlation + controlled propagation | Avoid conflicting IDs |
| `Authorization` | Spring Security, token audience policy | Never forward tokens blindly to every upstream |
| `X-Gateway-Source` | SCG post-authentication or edge per contract | Static headers alone do not prove identity |
| `Host` | HTTP client/proxy routing rules | Do not copy public `Host` to arbitrary upstreams |
| `Content-Length`, `Transfer-Encoding` | Per-hop HTTP transport layer | Avoid framing errors when rewriting/buffering bodies |
| `Cache-Control`, `Set-Cookie`, `Location` | True response-policy owner | Avoid leaking cookies, internal redirects, or bad caching |

If two proxies both inject `Access-Control-Allow-Origin` or `Strict-Transport-Security`, responses may contain duplicates or contradictions. Assign **one primary owner** per security/HTTP response header group and verify final headers from an Internet client perspective.

## 12. TLS Termination: HTTPS May Protect Only One Hop

An Ingress `tls.secretName` or Gateway listener `protocol: HTTPS` + `tls.mode: Terminate` protects **client -> edge proxy**. It **does not imply** subsequent hops are encrypted.

~~~mermaid
flowchart LR
    C["Internet client"] -->|"TLS #1"| Edge["Ingress/Gateway API proxy"]
    Edge -->|"HTTP or TLS #2"| G["Spring Cloud Gateway Pod"]
    G -->|"HTTP or TLS #3"| B["Orders backend"]
~~~

### 12.1. Reading the real TLS topology

| Hop | Example from this lesson | Is HTTPS active? |
| --- | --- | --- |
| Client -> edge | `https://api.example.test` | Yes, when the listener and cert are live |
| Edge -> SCG Service 8080 | `BackendRef` or Ingress Service port 8080 | **Not HTTPS automatically** just because the public listener is HTTPS |
| SCG -> Catalog | `uri: http://catalog-service.apps.svc.cluster.local:8080` | No; URI scheme is HTTP |
| SCG -> Orders | `uri: https://orders-service.apps.svc.cluster.local:8443` | Yes, if the client verifies CA/hostname and connects cleanly |

Where the edge controller supports backend TLS origination or policy CRDs, you can configure TLS on the Edge -> SCG hop; exact capabilities depend on the controller and Gateway API version. Likewise, a service mesh may provide mTLS between sidecars. **Never infer whether mTLS is active solely from an `HTTPRoute` manifest**.

### 12.2. TLS security essentials

- Certificates must match the hostname/SNI, have a valid trust chain, and remain unexpired.
- For SCG outbound HTTPS, enforce **hostname verification and CA trust**—never use trust-all SSL configurations.
- For mTLS, distinguish client certificate identities across SCG, edge, and sidecars per hop.
- Store TLS Secrets/keystores in an organization-approved secret manager with least-privilege RBAC, rotation, and auditing.
- During certificate rotation, verify how existing connections and pools are recycled or closed per policy.
- Never log private keys, bearer tokens, or cookies in debug or wiretap logs.

### 12.3. Multi-layer TLS impacts latency

In an Edge -> SCG -> Catalog topology, new connections may incur multiple TCP/TLS handshakes. Keep-alive, HTTP/2, pooled outbound clients, and TLS resumption amortize part of that cost, yet **each proxy layer adds a potential bottleneck**. When profiling latency, break down client->edge, edge->SCG, and SCG->Catalog; never blame "slow Spring Cloud Gateway processing" if an edge connection pool is actually queueing.

### 12.4. Redirecting HTTP to HTTPS

HTTP -> HTTPS redirects can be handled by either the edge controller or SCG. Pick one owner to avoid redirect loops:

~~~text
Client HTTP -> Edge redirects HTTPS -> Edge HTTPS -> SCG HTTP internal
~~~

If SCG does not trust the proxy's forwarded scheme and observes `http` on the internal hop, it may emit another redirect even though the external client already used HTTPS. Normalize `Forwarded`/`X-Forwarded-Proto` at trusted edge proxies and configure Spring forwarded-header handling to match your deployment—never trust forwarding headers straight from the Internet.

## 13. Where Do Authentication and Authorization Live?

All three technologies can participate in an authenticated system, yet **their exact responsibilities differ**.

### 13.1. Kubernetes Ingress and Gateway API do not handle business authorization natively

Core Ingress and core `HTTPRoute` select backends; they **do not natively implement full OAuth2/OIDC logins, JWT validation, ownership checks, or business RBAC**. Specific controllers may offer external auth hooks, JWT policies, or extensions, but those are **implementation-specific features**, never something to assume simply from `kind: Gateway`.

For example, matching `/api/admin` in an `HTTPRoute` does not restrict callers to admins. If the Orders service fails to verify permissions, unauthorized users could read protected resources even over public HTTPS.

### 13.2. Spring Cloud Gateway applies runtime security

With **Server WebFlux**, Spring Security typically uses a `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        // Only allow health probes at the exact check endpoints.
                        // Still restrict network access to the application port.
                        .pathMatchers(
                                HttpMethod.GET,
                                "/actuator/health/liveness",
                                "/actuator/health/readiness").permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/catalog/**").permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/orders/**")
                                .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                // Only for Bearer-only stateless APIs; do not use cookie auth.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

With **Server Web MVC**, the corresponding security setup uses `SecurityFilterChain` and Servlet `HttpSecurity`—**do not copy `SecurityWebFilterChain` and `Mono` types into an MVC gateway**.

This example only illustrates public/private routes:

- `/api/catalog/**` allows public GETs.
- `/api/orders/**` requires `SCOPE_orders.read`.
- Everything else is denied by default unless explicitly permitted by approved rules.

Proper JWT validation requires trusted issuer/JWKS configuration, expiration checks, **API-specific audience checks**, and accurate authority mapping. A Resource Server does not automatically validate custom business audiences solely from an issuer setting. Disabling CSRF (`csrf(...disable)`) here applies only to Bearer-only stateless APIs; if browsers rely on session/cookie auth, evaluate and enable appropriate CSRF protection.

The two GET exceptions `/actuator/health/liveness` and `/actuator/health/readiness` are meant for Kubernetes probes **inside a controlled network**. Because public Ingress/`HTTPRoute` only matches `/api`, **never expose Actuator on a public host**. If your organization uses a separate management port or different probe paths, align your security/probe policy instead of calling `permitAll()` on `/actuator/**`. Note also that sending a malformed Bearer token to a `permitAll()` Catalog endpoint can still be rejected by Resource Server authentication filters inspecting the client-supplied credential.

### 13.3. Backends must still enforce resource-level authorization

A caller holding `SCOPE_orders.read` is **not automatically entitled** to view another user's orders. The Orders backend must verify identity, tenant, resource ownership, and action permissions. Relying purely on an `X-User-Id` header populated from untrusted input risks IDOR or auth-bypass vulnerabilities.

### 13.4. Token forwarding is an explicit architectural decision

If SCG's Resource Server accepts access tokens issued for the Gateway audience, do not blindly forward those same tokens to Catalog or Orders simply to avoid extra validation steps. Design explicit trust/token exchange or audience-scoped backend validation, forwarding credentials only over TLS to authorized services matching the required scope. For public APIs like Catalog that need no user credentials, strip `Authorization`/`Cookie` as shown in Section 10.

**Note:** Route filters that strip headers **do not replace** port isolation or network egress controls. Clients could still try calling backend Services directly if cluster networking allows it; backends and `NetworkPolicy` must block unauthorized paths.

## 14. Client IP, Host, and Forwarded Headers Across Multiple Proxies

When Ingress or Gateway API sits in front of SCG, the source IP seen on SCG's incoming socket may belong to the edge proxy, a node, a sidecar, or a NAT gateway—it is **not automatically the client's public IP**.

~~~text
Client: 198.51.100.27
  -> Ingress/Gateway API edge proxy
     X-Forwarded-For: ... (reconstructed by trusted proxy per policy)
  -> Spring Cloud Gateway
     TCP hop remoteAddress may be the edge proxy address
  -> Backend
~~~

Addresses in this diagram are illustrative documentation examples, not measured traffic.

### 14.1. Never trust client-supplied Forwarded headers

A client might send:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
X-Forwarded-For: 127.0.0.1
X-Forwarded-Host: internal-admin.example.test
X-Forwarded-Proto: https
X-User-Role: ADMIN
~~~

If SCG or a backend trusts this `X-Forwarded-For` to bypass rate limits or authorization, or uses `X-Forwarded-Host` to select an upstream URI, the system is vulnerable to bypass or SSRF.

Safer design practices:

1. Configure **trusted proxies/networks** at the network edge; strip or sanitize client-supplied forwarding headers.
2. Trust forwarded metadata chains only from managed proxies.
3. Configure Spring forwarded-header handling according to your trusted-proxy topology—never blindly trust all `X-Forwarded-*` headers.
4. Do not rely solely on client IP for authentication, especially behind NAT, CDNs, or shared IPs.
5. Base rate-limiter keys on verified principals or API keys when appropriate, combined with trusted-IP policies if needed.
6. Test **direct access to the SCG Service** (in an authorized test environment) to check whether edge policies can be bypassed.

### 14.2. Preserve Host and backend virtual hosting

An HTTP proxy may preserve `Host: api.example.test` or rewrite it to an upstream hostname depending on route config and HTTP client settings. If a backend uses virtual-host routing, define an explicit contract for `Host` and SNI. **Never copy a public `Host` header blindly to every backend**; TLS hostname verification must validate the intended backend identity rather than trusting client-supplied SNI/Host headers.

### 14.3. Hop-by-hop headers

`Connection`, `Transfer-Encoding`, `Keep-Alive`, `Upgrade`, and headers listed in `Connection` belong to **each individual hop** and must never be blindly forwarded across two proxies. Let each transport hop manage framing, while testing `Content-Length`, `Content-Encoding`, `Location`, `Set-Cookie`, CORS, and caching on the **final response**.

## 15. Deploying the Spring Cloud Gateway Pod Behind Ingress or Gateway API

Earlier Ingress/`HTTPRoute` manifests assumed a Kubernetes `Service edge/spring-gateway:8080`. Below is an illustrative Deployment/Service completing the picture. **Always use an image built and approved by your organization**, not a placeholder image name.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spring-gateway
  namespace: edge
spec:
  replicas: 2
  selector:
    matchLabels:
      app: spring-gateway
  template:
    metadata:
      labels:
        app: spring-gateway
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: gateway
          image: registry.example.test/platform/spring-gateway:1.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 24
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 768Mi
---
apiVersion: v1
kind: Service
metadata:
  name: spring-gateway
  namespace: edge
spec:
  type: ClusterIP
  selector:
    app: spring-gateway
  ports:
    - name: http
      port: 8080
      targetPort: http
~~~

### 15.1. Application configuration required for probes

Spring Boot example (verify property names against your release):

~~~yaml
server:
  port: 8080
  shutdown: graceful

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
~~~

This **assumes** Actuator is on the classpath, health probes are enabled, and Actuator listens on the **same application port 8080**. If you use a separate `management.server.port` or custom `management.endpoints.web.base-path`, update probe ports/paths accordingly; keep in mind a separate management port can appear healthy even when the 8080 data plane is degraded, so consider **testing the data-plane listener** in readiness checks.

### 15.2. Liveness is not readiness

| Probe | Goal | Anti-pattern |
| --- | --- | --- |
| **Liveness** | Is the process deadlocked and unable to recover? | Tying liveness to Catalog DB so a backend glitch restarts all Gateway pods |
| **Readiness** | Is the pod ready to accept live traffic? | Always reporting OK before routes load or while the HTTP listener is broken |
| **Startup** | Gives the JVM/app warm-up time before liveness kicks in | Setting threshold too low, causing endless Boot/JVM restart loops |

Resource requests and limits in the YAML are **illustrative syntax values**, not production sizing recommendations. Measure latency, CPU, JVM heap, Netty event loops or Servlet threads, outbound pools, and error rates before sizing.

### 15.3. Shutdown/rollout must not sever in-flight requests

During a rolling update:

1. An old Pod transitions to Terminating and must leave `Service` endpoints per Kubernetes/controller propagation.
2. The Gateway stops accepting new requests once unready, while **allowing in-flight requests to finish** within the grace period.
3. Outbound HTTP pools, streaming responses, SSE/WebSocket connections, and in-flight retries need aligned lifecycles.
4. Edge controllers/Service data planes may experience brief propagation lag before stopping traffic to the terminating Pod.

Spring Boot's `server.shutdown: graceful` is only one piece—it **does not replace** readiness probes, termination grace periods, load-balancer draining, PDBs, or real testing. Do not copy `preStop: sleep 5` as a "magic number" across every cluster.

### 15.4. Scaling the gateway differs from scaling a business service

Increasing SCG `replicas` increases inbound gateway capacity, yet every replica maintains its own DNS cache, connection pools, and local states. With an in-memory rate limiter, adding replicas changes effective per-user quotas; with a shared Redis limiter, ensure Redis handles the added load. Plan HPA, `PodDisruptionBudget`, topology spread, and multi-zone availability around edge SLOs.

## 16. Kubernetes Service/DNS Differs from Spring Cloud Gateway Service Discovery

This lesson mentions at least **four ways of expressing a target**, and they are not identical:

| Where configured | Reference syntax | What picks the target? |
| --- | --- | --- |
| Ingress | `backend.service.name: spring-gateway`, `port.number: 8080` | Ingress controller -> Kubernetes Service/endpoints |
| Gateway API | `backendRefs: [{name: spring-gateway, port: 8080}]` | Gateway API controller/data plane -> Service/endpoints |
| SCG static URI | `uri: http://catalog-service.apps.svc.cluster.local:8080` | SCG HTTP client -> Kubernetes DNS/Service |
| SCG discovery URI | `uri: lb://catalog-service` | Spring Cloud LoadBalancer + `ServiceInstance` supplier |

### 16.1. Service and Endpoints/EndpointSlices

A Kubernetes `Service` stabilizes name/port inside the cluster and selects matching Pod endpoints based on labels and readiness (depending on Service settings). `EndpointSlice` holds the active endpoints managed by Kubernetes. In many setups, kube-proxy or an eBPF data plane balances connections to Pods, whereas Ingress/Gateway API controllers may either connect directly to Pod endpoints or route via Service VIPs depending on implementation.

**Never assume a Service with a DNS record has healthy Pods behind it.** A Service can exist with empty `EndpointSlice`s when Pods are not Ready, selectors mismatch, or backend ports are wrong; the edge may return 503/502 depending on controller behavior.

### 16.2. Spring Cloud LoadBalancer does not automatically discover Kubernetes Services

`lb://catalog-service` is a Spring Cloud Gateway routing abstraction. To resolve it, your application needs an integration providing `ServiceInstance` records from a compatible discovery/registry source; it is not standard Kubernetes DNS syntax.

For straightforward in-cluster deployments, an HTTP URI targeting the Service FQDN is clear and predictable:

~~~yaml
uri: http://catalog-service.apps.svc.cluster.local:8080
~~~

When an application genuinely needs client-side discovery or zone-aware selection, `lb://` can fit—provided you verify the `ServiceInstance` supplier, LoadBalancer caching, TLS/host verification, and no-instance fallback behavior. Pick one load-balancing model deliberately instead of accidentally stacking two layers.

### 16.3. Why latency and failover behavior can differ

When SCG connects to a Service VIP over pooled HTTP connections, existing persistent connections may stay pinned to an older Pod until closed or reset. With client-side `lb://`, instance selection, DNS, and HTTP pool lifecycles follow different caching, health, and failover rules.

Therefore during rollouts:

- Verify actual request distribution across Pods rather than only checking `Service` existence.
- Monitor connection idle lifetimes, TLS handshakes, and stale connection resets.
- Do not assume removing an `EndpointSlice` entry immediately moves already-open TCP sockets.
- Restrict retries to safe operations with clear idempotency and deadlines.
- Never allow clients to supply arbitrary service IDs or URIs, avoiding SSRF or token leakage.

## 17. Headers, Rewrites, Canaries, and Resilience Policies: Clear Ownership

An Ingress or Gateway API controller may provide rich L7 features alongside Spring Cloud Gateway's extensive route filters. Enabling the same policy in both layers can cause requests to be **rewritten, retried, rate-limited, or redirected twice**.

### 17.1. HTTPRoute weighted backends vs. SCG route weights

An `HTTPRoute` can configure weighted `backendRefs` when supported by the controller:

~~~yaml
# Snippet inside HTTPRoute.spec.rules[]
matches:
  - path:
      type: PathPrefix
      value: /api/catalog
backendRefs:
  - name: catalog-v1
    port: 8080
    weight: 90
  - name: catalog-v2
    port: 8080
    weight: 10
~~~

This shows **Gateway API routing directly to two Service versions**. It does not guarantee that **every 10 requests** split deterministically as 9 to v1 and 1 to v2. Actual splits depend on the controller, sample size, hashing/stickiness, endpoint health, and retries. Never combine a 10% canary in `HTTPRoute` **with** a 10% canary in SCG and call it "10% production traffic"—the effective split becomes hard to reason about and audit.

### 17.2. Splitting policies along trust boundaries

| Policy | Usually best placed at | What to verify |
| --- | --- | --- |
| Public DNS/TLS certificates | Edge controller/ingress | Certificate/SANs, listener/address |
| Perimeter HTTP admission | Edge + network controls | Allowed hosts, methods, max body size |
| Public HTTP->HTTPS redirect | Single owner at the edge | Zero redirect loops |
| App-route rewrites/header edits | SCG or Gateway API; **pick one owner** | Backend receives expected URL/headers |
| JWT validation and scopes | SCG/Spring Security or approved edge auth | Backend still checks resource permissions |
| Rate limiting | Edge for abuse protection, or SCG for per-API/user quotas | Verified key identity, distributed quota, no double limiting |
| Retries | One primary layer per operation | Total attempt budget, idempotency |
| Circuit breaking | Close to dependency with telemetry and fallback | Retries/fallbacks do not mask outages |
| Service discovery | K8s Service/data plane or SCG LB | Healthy targets, failover, TLS identity |
| CORS | One owner for browser-facing origins | `OPTIONS` preflight and non-conflicting headers |
| Access logging/tracing | Both layers with selective correlation | No double-counting or leaked tokens |

**Retry amplification example:** If the edge performs two retries (3 total attempts) and SCG also performs two retries (3 total attempts), one client request can trigger **up to 9 upstream attempts** across sequential branches—before counting any downstream retries. Keep retries bounded by **overall deadlines, finite attempts, backoff/jitter, and idempotency guards**.

### 17.3. Request mirroring does not mean the canary serves business traffic

Gateway API controllers may support request mirroring (or extensions), and SCG has version-dependent filters/mechanisms too. Mirroring copies selected requests to an observation backend **without returning the mirrored backend's response** to the client. For mutating POSTs, mirroring into a live service can **create duplicate transactions**. Mirror only sanitized traffic into non-mutating sinks with explicit authorization.

### 17.4. Extended filters require conformance testing

Gateway API filters like `RequestHeaderModifier`, `ResponseHeaderModifier`, `URLRewrite`, `RequestRedirect`, `RequestMirror`, and advanced policies vary across **Core/Extended/Implementation-specific** conformance tiers and versions. Similarly, SCG filter factories vary between Server WebFlux and Server Web MVC releases. Never equate features solely by name—run HTTP tests against your target controller and runtime.

## 18. Securing the Kubernetes Control Plane and Management Plane

A sound Gateway security posture protects **who can modify configuration** as well as **who can call APIs**, not merely client HTTPS.

### 18.1. Three planes to protect

~~~mermaid
flowchart TD
    Admin["Platform admins"] --> KAPI["Kubernetes API / RBAC"]
    KAPI --> GWC["Ingress or Gateway API resources"]
    GWC --> EDGE["Edge data plane"]
    Client["Client"] --> EDGE
    EDGE --> SCG["Spring Cloud Gateway application"]
    Ops["Ops personnel"] --> ACT["Protected Actuator/metrics"]
    ACT --> SCG
    SCG --> SVC["Backend services with own authorization"]
~~~

| Plane | Who has access? | High-risk exposure |
| --- | --- | --- |
| **Kubernetes control plane** | Platform/owners via RBAC and admission control | `HTTPRoute` pointing to unauthorized backends; Ingress/Gateway hijacking hosts/TLS |
| **HTTP data plane** | Clients authorized by authn/authz policy | Auth bypass, SSRF, unintended token forwarding, abuse |
| **SCG management plane** | Operators with least privilege | Route listings exposing internals, route create/refresh/delete, sensitive metric labels |

Never expose API server credentials, service account tokens, or Actuator admin endpoints. Modifying an `HTTPRoute` can redirect live traffic to another backend, so **GitOps reviews and Kubernetes RBAC** must be guarded with the same rigor as firewall and routing policies.

### 18.2. Namespaces, RBAC, and ReferenceGrant do not replace NetworkPolicy

Even if a Gateway listener blocks an untrusted namespace's `HTTPRoute` from attaching, Pods in that namespace could still attempt calling SCG or backend Services directly over cluster networking. **NetworkPolicy** (when enforced by the CNI) constrains Pod-to-Pod traffic, though it still does not replace JWT/mTLS/application authorization because it does not inspect user resource permissions.

### 18.3. Securing the SCG Actuator

Spring Cloud Gateway exposes actuator endpoints and management features varying by version. Never configure `management.endpoints.web.exposure.include: "*"` on a public listener. Isolate the management port/network when needed, enforce Spring Security operator permissions, restrict write capabilities, and expose only required health/metrics endpoints.

An edge Gateway might block `/actuator/**` on public hosts, yet an internal `Service` exposing the management port to every Pod in the cluster remains a bypass path. Audit **Service types, exposed ports, NetworkPolicy, and application-level authentication** together.

### 18.4. Kubernetes Secrets and TLS certificates

Ingress and Gateway listeners reference TLS `Secret` objects by name—never hardcode private keys in manifests or tutorials. In production, provision and rotate certificates via an approved secrets manager with least-privilege RBAC, audit logging, and expiration/revocation procedures. Storing data in a Kubernetes `Secret` does not automatically secure it end to end; review etcd encryption at rest, RBAC grants, and secret injection paths.

### 18.5. Preventing route takeover and shadowing

A new `HTTPRoute` can overlap hostnames or paths with existing routes. Across multiple teams, policies must prevent shadowing admin, identity, or internal routes. While Gateway API defines conflict and precedence rules, **never rely on unverified assumptions about resource apply order**. Use conformance tests, linting/admission policies, and route ownership reviews.

## 19. Observability: Debugging Requires Knowing Which Layer Generated the Response

In a two-layer gateway architecture, a 404 or 503 status can originate from any of three layers:

~~~text
Client
  |
  v
Ingress/Gateway API data plane  ---> 404/503 before reaching SCG
  |
  v
Spring Cloud Gateway             ---> 401/403/404/429/503/504 inside Gateway
  |
  v
Catalog/Orders backend           ---> Genuine HTTP 404/503 from backend
~~~

Status codes overlap while root causes differ; never look at `curl -i` alone and immediately conclude "the SCG route is broken".

### 19.1. Which metrics belong at each layer?

| Layer | Recommended signals | Purpose |
| --- | --- | --- |
| Public edge | Requests, host/route, status, TLS errors, target selection | Confirm whether requests reached the edge and were forwarded |
| Ingress/Gateway controller | Reconciliation errors, accepted/programmed status | Confirm whether config programmed the data plane |
| Kubernetes Service | Ready endpoints, `EndpointSlice`s, pod restarts | Confirm healthy backing Pods exist |
| SCG | Route ID, Spring Security outcome, filters, response status | Distinguish route match vs. auth vs. fallback |
| SCG outbound client | Connection pool, DNS/connect/TLS, upstream status/attempts | Separate transport issues from backend 503s |
| Backend | Request count, trace span, handling duration, app status | Confirm whether the backend actually received the request |

Use **stable route IDs / Service IDs** as metric labels rather than raw URLs containing entity IDs or user tokens, avoiding cardinality explosions and PII exposure. Distributed tracing can propagate `traceparent` or compatible headers when configured—never put bearer tokens or cookies in trace baggage.

### 19.2. Start with controller status

When troubleshooting Gateway API:

- Was the `GatewayClass` accepted by the controller?
- Do `Gateway` status conditions confirm listeners and config are programmed?
- Does `HTTPRoute.status.parents[]` report `Accepted` attachment and `ResolvedRefs` for backends?
- Are the Gateway's address, port, and certificate ready and aligned with public DNS?
- Do route `parentRefs`, `hostnames`, and listener `allowedRoutes` agree?

Exact names and semantics of **status conditions** vary slightly across releases and controllers; read live status outputs against your implementation docs. **A resource saved in the API server does not guarantee live traffic has an active route.**

### 19.3. Safe inspection commands

~~~bash
# Ingress: inspect class, hosts, status, and events.
kubectl -n edge get ingress api-entry -o yaml
kubectl -n edge describe ingress api-entry

# Gateway API: inspect class, listeners, and routes.
kubectl get gatewayclass public-http -o yaml
kubectl -n edge get gateways
kubectl -n edge describe gateway public-api
kubectl -n edge get httproutes
kubectl -n edge get httproute app-api -o yaml

# Kubernetes Service and Pod state.
kubectl -n edge get svc spring-gateway
kubectl -n edge get endpointslices \
  -l kubernetes.io/service-name=spring-gateway
kubectl -n edge get pods -l app=spring-gateway

# Run only with proper authorization; logs may contain sensitive details.
kubectl -n edge logs deployment/spring-gateway --tail=100
~~~

These commands assume illustrative resource names and RBAC permissions; **they are not captured execution output**. When querying an `HTTPRoute` in namespace `apps`, switch `-n edge` to `-n apps`, while keeping `-n edge` for the `Gateway` and `ReferenceGrant`. Errors may indicate missing CRDs or controllers rather than invalid YAML syntax.

### 19.4. End-to-end HTTP testing across both proxies

~~~bash
# Domain must resolve to the edge listener deployed in your test environment.
curl -i \
  --connect-timeout 3 --max-time 10 \
  'https://api.example.test/api/catalog/items/42?lang=vi'
~~~

To prove the backend received the expected request, inspect a **backend stub/request journal** logging method, raw path, raw query, and **allowlisted** headers. In a lab environment, you might expose a read-only test endpoint to identify which Pod/instance responded—never expose internal hostnames, tokens, or full cluster topology on public production APIs.

**Four distinct failure states can arise:** the edge accepts the request but SCG lacks a route; SCG matches a route but the Service has no ready endpoints; the backend returns an HTTP error; or traffic misses the intended edge due to DNS/TLS listener mismatches. Each state requires distinct evidence.

## 20. Evaluating Performance and Resource Cost with Two Gateway Layers

Adding an extra proxy layer on the request path introduces costs:

- L7 routing and filter execution.
- Additional network hop and potential TCP/TLS handshakes on fresh connections.
- Outbound connection pools, queues, and timeout management.
- HTTP header/body processing; certain filters buffer bodies.
- SCG JVM heap/CPU/GC, Reactor Netty event loops, or Servlet threads.
- Metrics, tracing, and secret/certificate handling.

Still, **removing Spring Cloud Gateway does not automatically make a system faster** if the edge controller ends up running heavy extensions to replicate those policies, or if every backend must re-implement auth and filtering that SCG previously centralized.

### 20.1. Conceptual two-hop latency breakdown

\[
T_{\text{client-visible}} \approx
T_{\text{client-edge}}
+T_{\text{edge-processing}}
+T_{\text{edge-SCG}}
+T_{\text{SCG-processing}}
+T_{\text{SCG-backend}}
+T_{\text{response-transfer}}
\]

This is a **conceptual latency budget**, not a rule for adding individual p95 numbers together. Pooled connections skip TCP/TLS handshakes on reused sockets; retries add extra outbound attempts; some phases overlap. Explaining p99 behavior requires correlated traces and transport metrics for the **same operation**.

### 20.2. Controlled comparison benchmark

| Variable | Option A: Edge direct | Option B: Edge -> SCG |
| --- | --- | --- |
| Public edge/controller | Same implementation | Same implementation |
| Backend service/version | Same Catalog | Same Catalog |
| Public TLS | Same certificate/protocol | Same certificate/protocol |
| Backend TLS | Documented per hop | Documented per hop |
| API auth/policies | Functionally equivalent | Functionally equivalent |
| Response size/QPS | Identical | Identical |
| Retry/breaker behavior | Same contract | Same contract |
| Metrics | p50/p95/p99, 4xx/5xx, CPU | p50/p95/p99, 4xx/5xx, CPU |

**Never compare Option A without auth or retries against Option B with JWT validation, rate limiting, and retries and then claim "SCG adds X ms of overhead".** When policies differ, benchmarks fail to isolate the proxy-hop cost.

### 20.3. Capacity and availability

When SCG serves as a shared entrypoint across multiple domains, evaluate its blast radius: a buggy custom filter, memory leak, or slow Redis rate limiter can affect every API. Size replicas, readiness probes, timeouts, admission controls, and circuit breakers carefully. Splitting SCG per domain or BFF improves team isolation, balanced against the operational overhead of running multiple gateway deployments.

## 21. Migrating from Ingress to Gateway API While Keeping SCG

In many organizations, the migration goal is **changing how the edge is configured**, not rewriting all Spring Cloud Gateway logic. A safe plan keeps API contracts and SCG backends stable first, evaluating later whether any routes or filters make sense to shift up to the edge.

### 21.1. Pre-migration inventory table

| Current component | What to record | Why it matters |
| --- | --- | --- |
| `IngressClass` and controller | Name, version, supported annotations | Annotations rarely translate 1:1 across controllers |
| Public host/DNS/LB | IP/hostname, DNS TTL, certificate | Avoid downtime or broken HTTPS |
| Ingress rules | Host, `PathType`, path priority, backend port | Ensure `HTTPRoute` selects identical requests |
| Ingress annotations | Rewrites, redirects, CORS, auth, timeouts, upload limits | Map to Gateway API, SCG, or controller extensions |
| Kubernetes `Service` | Namespace, port, selectors, `EndpointSlice`s | Avoid routing to Services with zero ready Pods |
| SCG routes | Route IDs, predicates, filters, URIs, ordering | Prevent accidental double rewrites or bypasses |
| Spring Security | Public/private/admin rules, JWT issuer/audience | Keep access rights identical across edge change |
| Rate limits/retries/breakers | Owner, deadlines, idempotency | Avoid double policy enforcement |
| Operational SLOs | Latency, availability, rollback triggers | Evaluate migration with hard evidence |

### 21.2. Multi-stage migration path

~~~mermaid
flowchart TD
    A["Inventory Ingress + SCG contract"] --> B["Choose Gateway API controller and check conformance"]
    B --> C["Install CRDs/controller, configure GatewayClass/Gateway"]
    C --> D["Create isolated test listener/hostname"]
    D --> E["Point HTTPRoute to existing SCG Service"]
    E --> F["Compare auth, path/header, TLS, 2xx/4xx/5xx"]
    F --> G{"Parity + SLO met?"}
    G -->|No| H["Adjust Gateway API policy / roll back test"]
    H --> E
    G -->|Yes| I["Controlled canary/DNS cutover"]
    I --> J["Observation & rollback window"]
    J --> K["Retire legacy Ingress once stable"]
~~~

**Note:** For a single public hostname, you generally cannot attach two independent public load balancers and expect route order to resolve between them. Use a **dedicated test hostname**, separate address, infrastructure traffic shifting, or an approved DNS strategy. During DNS cutovers, account for client DNS TTL caching, certificates on both endpoints, sticky sessions/WebSockets, and the overlap window when **both entrypoints receive live traffic**.

### 21.3. Do not migrate by copying annotations verbatim

An Ingress annotation often encodes **vendor-specific** rewrite, canary, auth, or load-balancer settings. Gateway API may offer a comparable filter or policy, yet:

- Syntax often differs.
- The feature may be Extended or Implementation-specific and unsupported by your controller.
- Execution order across rewrites, headers, and auth may differ.
- `Location`, `Host`, and forwarded-header rewriting behavior may differ.
- Status codes returned for invalid routes or missing backends may differ.

Build a mapping table from **business requirement -> controller capability -> HTTP verification test**, rather than mapping field names blindly.

### 21.4. Testing before cutover

Exercise both endpoints (old Ingress and new Gateway API) with the **same** methods, paths, query strings, headers, test tokens, and payloads, confirming via the backend stub that requests leaving SCG are identical. Test:

- `GET /api/catalog/items/42` plus UTF-8 and URL-encoded query parameters.
- POST to GET-only routes, unmatched-route 404s, and backend 404s.
- Anonymous calls and under-scoped JWTs to Orders.
- Redirects, cookies, CORS, and `OPTIONS` preflight per browser contracts.
- HTTPS certificates/SNI, `Host` headers, and forwarded metadata.
- Large uploads or streaming endpoints if supported.
- Backend 503s, connect timeouts, retries/fallbacks, and rate limiting.

After cutover, monitor **Accepted/Programmed status**, ready endpoint counts, HTTP 4xx/5xx rates, route-level p95/p99 latency, and backend request counts. Maintain rollback plans for both DNS/addresses and controller resources—never disable auth or TLS during an incident.

### 21.5. Must Spring Cloud Gateway be removed?

No. After switching from Ingress to Gateway API, SCG can continue owning business-aware routes, Spring Security, and custom filters. Consider removing SCG only after proving its responsibilities are covered cleanly by the edge and backends with **equivalent functionality, security, observability, and performance**—not merely because both layers contain the word "Gateway".

## 22. Layer-by-Layer Troubleshooting

Every failed request should be traced to the responsible boundary: **DNS/TLS listener, Gateway API attachment, Kubernetes Service, SCG route/filter, or backend**.

| Symptom | First suspect layer | Evidence to inspect |
| --- | --- | --- |
| `kubectl apply` Ingress succeeds, yet zero public traffic arrives | IngressClass/controller/LB/DNS | Did controller claim Ingress? Service address/status? DNS? |
| `HTTPRoute` exists, yet traffic does not match | Gateway API attachment/hostname/listener | `parentRefs`, `allowedRoutes`, `Accepted` |
| `HTTPRoute` backend ref invalid | `ReferenceGrant`/Service namespace/port | `ResolvedRefs`, `ReferenceGrant` in target namespace |
| Gateway HTTPS listener fails to start | `GatewayClass`/controller/TLS `Secret` | Status, listener conditions, cert/SAN/SNI |
| Client reports certificate mismatch | Public DNS/SNI/TLS `Secret` | Certificate hostnames, ingress/Gateway address |
| `/api/catalog` returns 404 at SCG post-migration | Double rewrite or wrong route namespace | Backend hits, actual SCG route match and incoming path |
| Edge returns 404, SCG hits = 0 | Host/path/method failed to match edge | Ingress/Gateway controller routes and logs |
| Backend returns 404 after SCG matched | Wrong SCG `StripPrefix`/`RewritePath` or missing item | Backend raw path and business response |
| Edge returns 503 while SCG receives nothing | Service lacks ready endpoints or edge health fails | Service/`EndpointSlice`s/Pods |
| SCG returns 503 when Catalog has no instances | SCG discovery/load balancer | `ServiceInstance` cache/HTTP client errors |
| 502/504 spike when backend slows down | Outbound connect/TLS/read timeouts | HTTP client metrics and error classes |
| Ingress matches, yet `Authorization` disappears | Header stripping at edge or SCG | Request journal (without secret values) |
| User accesses Orders without permission | Spring Security/backend authorization | JWT rules/validation, backend ownership tests |
| 401 only on valid tokens post-migration | Proxy/header/issuer/audience mismatch | Auth propagation, sanitized JWT decoder logs |
| Browser CORS fails while `curl` returns 200 | Preflight/`Origin` policy | `OPTIONS` response, CORS header owner, credentials |
| HTTP->HTTPS redirect loop | `Forwarded` Proto/redirects across two layers | Edge HTTPS termination and SCG trusted-proxy config |
| Wrong cookie domain/path | Response rewrite/`Set-Cookie` policy | Final browser-facing headers past both proxies |
| Rate limits shift when scaling Pods | Per-instance state/keying | Shared store, key resolver, request attempts |
| Retries overload backends | Both edge and SCG retrying | Upstream attempts per inbound request |
| Single SCG replica fails sporadically | Config/deployment/pool mismatch | Per-Pod revision, route IDs, and metrics |
| Weighted `HTTPRoute` 90/10 does not split 9/1 in 10 calls | Small sample size / distribution algorithm | Controller algorithm, larger test sample |
| Actuator admin endpoints exposed | Management `Service`/ingress/security policy | Exposures, RBAC/network isolation, ops auth |
| Public TLS works, yet backend hop is unencrypted | Edge->SCG or SCG->Service config | URI schemes, backend TLS policy, packet path |

### 10-Step Debugging Checklist

1. **DNS and listener:** Is the client hitting the right IP/LB, SNI, certificate, and port?
2. **Controller ownership:** Is an active controller reconciling the `IngressClass`/`GatewayClass`?
3. **Route acceptance:** Are host, path, `parentRefs`, `allowedRoutes`, and `ReferenceGrant` valid?
4. **Edge response provenance:** Did the edge generate the error before calling SCG?
5. **Kubernetes Service:** Do Service ports and ready `EndpointSlice`s target the right Pod `targetPort`?
6. **SCG inbound:** Did the Pod receive the request, or did Spring Security reject it pre-route?
7. **SCG routing:** Which route ID matched, and what path/headers survived filters?
8. **Outbound:** Did DNS/TCP/TLS/`ServiceInstance`/connection pools reach the backend cleanly?
9. **Backend:** Did the backend receive the request, what status did it return, and how many retries arrived?
10. **Final response:** Did the edge alter headers, cookies, `Location`, CORS, or body?

What matters most is **gathering evidence at each boundary**. Never "fix" issues by switching to `pathType: ImplementationSpecific`, enabling wildcard CORS, disabling TLS verification, or marking all Gateway routes public—those mask symptoms while introducing vulnerabilities.

### Testing SCG independently from the edge

In a test environment with valid RBAC permissions, you can port-forward directly to the Kubernetes `Service`:

~~~bash
kubectl -n edge port-forward svc/spring-gateway 18080:8080
~~~

Then in another terminal:

~~~bash
curl -i 'http://127.0.0.1:18080/api/catalog/items/42'
~~~

If direct port-forwarding succeeds while the public hostname fails, the fault likely lies in the edge, TLS, or edge rewrites; if both fail, inspect SCG, the `Service`, or the backend. **Port-forwarding is a privileged Kubernetes debugging path**, not proof that production edge paths, `NetworkPolicy`, or TLS work identically; never use it to bypass auth or manipulate live data against policy.

## 23. Edge-to-Backend Test Matrix

| ID | Test case | Outcome to verify |
| --- | --- | --- |
| T01 | Ingress/Gateway API listener has a public address | DNS/LB resolves to the expected listener |
| T02 | `HTTPRoute` `Accepted`/`ResolvedRefs` | Controller accepted route and resolved valid backend |
| T03 | `HTTPRoute` in namespace disallowed by `allowedRoutes` | Route fails to attach |
| T04 | Cross-namespace `backendRef` without `ReferenceGrant` | Backend reference fails to resolve |
| T05 | Owner grants `ReferenceGrant` for exact `Service` name | Valid `backendRef` without exposing unrelated Services |
| T06 | ASCII GET Catalog | 200 response from the right backend |
| T07 | GET Catalog with UTF-8/encoded-plus query | Backend receives raw path/query matching contract |
| T08 | Prefix `/api` vs. `/apix` | `/apix` does not falsely match `/api` prefix rules |
| T09 | Disallowed HTTP method | Never proxies to backend on GET-only routes |
| T10 | Intentional double rewrite in sandbox | Tests catch 404/path mismatch |
| T11 | Backend returns HTTP 404 | Distinguished from edge/SCG route-miss 404 |
| T12 | Missing SCG route | Edge forwards yet SCG reports route miss |
| T13 | Service has no ready `EndpointSlice`s | Edge/Gateway fails per controller contract |
| T14 | SCG outbound connection refused | Does not hang indefinitely; returns safe error |
| T15 | Backend returns 503 | Final response is not silently converted into fake 200 |
| T16 | Wrong hostname in public TLS cert | Client rejects connection |
| T17 | Invalid TLS certificate on backend | SCG/client fails closed |
| T18 | HTTP->HTTPS redirect | Zero redirect loops |
| T19 | Client spoofs `X-Forwarded-*`/`Host` | No SSRF or policy bypass |
| T20 | Anonymous request to Orders | 401/deny per policy; backend hits = 0 |
| T21 | JWT missing required scope | 403/deny per policy; backend hits = 0 |
| T22 | JWT with valid issuer/audience/scope | Reaches route; backend still enforces ownership |
| T23 | Public Catalog receives token/cookie | Credentials are not leaked to unneeded backends |
| T24 | CORS `OPTIONS` preflight | Exact headers/origin, single clear owner |
| T25 | 2xx response carrying `Set-Cookie`/`Location` | No internal host leaks or broken contracts |
| T26 | Weighted canary `backendRefs` 90/10 | Traffic distribution validated over sufficient sample size |
| T27 | Edge + SCG retries | Combined attempts stay within overall budget |
| T28 | Circuit breaker OPEN | Stops hitting backend; returns valid fallback |
| T29 | SCG rolling update | Readiness/draining prevents noticeable outages |
| T30 | Multi-replica SCG | Routes and security config remain consistent across Pods |
| T31 | Large upload/streaming | Bodies, headers, and graceful termination behave cleanly |
| T32 | Actuator admin endpoints | Unreachable from public clients |
| T33 | Single edge/controller replica failure | Availability stays within SLO without widespread route loss |
| T34 | Migration cutover/rollback | Old and new entrypoints satisfy equivalent HTTP contracts |

**You do not need to automate every test immediately**, though tests guarding trust boundaries (T03–T05, T19–T25, T32) and core business paths (T06–T17) belong before production rollout. Execute destructive tests (creating/deleting routes or stopping backends) strictly inside **sandbox environments**, never production.

### Two complementary test categories

- **Kubernetes acceptance test:** resources accepted by controllers, listener allocated an address, `Service` has ready endpoints, and cross-namespace policies behave properly.
- **HTTP contract test:** real client hits the listener down to a backend stub; asserts method, path, headers, status, body, and upstream hit count.

A clean `kubectl apply` **does not replace** an HTTP integration test. Conversely, a single passing `curl` 200 **does not prove** cross-namespace isolation, authentication, or rollback readiness.

## 24. Hands-on Lab: One API, Two Edge Options

**Scenario:** Your organization runs Spring Cloud Gateway serving Catalog and Orders inside Kubernetes. You must expose a public HTTPS endpoint and evaluate **Ingress vs. Gateway API**, keeping SCG as the application gateway. Afterward, compare a direct edge-to-Catalog setup in an isolated lab to evaluate trade-offs.

### Part A — Prepare the test cluster

1. Select an organization-supported **Kubernetes version and controller implementation**. Verify Gateway API CRDs and controller availability if testing Gateway API.
2. Create namespaces `edge` and `apps` with scoped permissions—avoid giving `cluster-admin` to application developers.
3. Deploy Catalog and Orders stubs in `apps` with deterministic HTTP methods/paths and a safe request journal.
4. Deploy Spring Cloud Gateway (choose either Server WebFlux or Server Web MVC) with both routes and proper security rules.
5. Create `Service edge/spring-gateway:8080` and verify ready `EndpointSlice`s.
6. Provision a valid test TLS certificate for `api.example.test` or another lab host without committing private keys to public docs.
7. Configure DNS/test host entries pointing separately to **each option's** edge address so two controllers never fight over the same endpoint.

### Part B — Deploy Ingress

1. Apply the Section 4 Ingress YAML, adjusting `ingressClassName` for your cluster controller.
2. Inspect `kubectl describe ingress`, assigned address, TLS Secret, and sanitized controller logs.
3. Issue GET requests to Catalog and Orders with valid test tokens. Confirm Ingress only matches host/path without rewriting.
4. Check backend request journals to verify SCG `StripPrefix=1` and header stripping.
5. Test unmatched URLs, wrong hostnames, and POST requests to GET-only routes; check response statuses and backend hit counts.

### Part C — Deploy Gateway API **Instead of** Ingress

1. Apply controller-supported `GatewayClass`, `Gateway`, and `HTTPRoute` manifests from Section 6, setting `controllerName` for your cluster.
2. Use a dedicated test listener/hostname/address (or temporarily tear down Ingress in your sandbox) so the same public hostname is never routed ambiguously.
3. Verify `GatewayClass` acceptance, `Gateway` listener status, and `HTTPRoute.status.parents[]`.
4. Send the exact same HTTP test suite and compare paths, statuses, bodies, and headers against Ingress.
5. Create an `HTTPRoute` in namespace `apps` and prove `allowedRoutes.from: Same` blocks attachment.
6. Switch to a **platform-controlled** namespace selector and verify the route attaches.
7. Point the `apps` `HTTPRoute` at `Service edge/spring-gateway`, confirm resolution fails without a `ReferenceGrant`, then add a narrowly scoped `ReferenceGrant` as the `edge` owner and confirm attachment/resolution succeeds.
8. Delete the grant in your sandbox and confirm the backend route stops resolving with no bypass path remaining.

### Part D — Compare Direct Edge Routing vs. Routing via SCG

1. Create a new `HTTPRoute` on a **test hostname** sending `/api/catalog` directly to the Catalog `Service` in the same namespace.
2. If Catalog expects `/catalog/**`, use `URLRewrite` (if supported by your controller) or adjust the lab backend consistently without relying on unsupported features.
3. Compare against Gateway API -> SCG -> Catalog while **holding auth, request/response policies, TLS, and payloads constant**.
4. Measure throughput, p95/p99 latency, CPU/memory, TLS/connections, and error rates.
5. Document which policies SCG provides that the edge controller lacks or handles poorly—never drop JWT/auth checks just to make a benchmark look faster.

### Part E — Security, Faults, and Lifecycle

1. Send spoofed `X-Forwarded-For`/`X-Forwarded-Host` headers; verify neither principal, backend target, nor trusted client IP is subverted.
2. Test under-scoped JWTs and wrong-audience JWTs; confirm the backend never receives unauthenticated/unauthorized calls.
3. Present an expired TLS cert or hostname mismatch on a **test listener**; verify connections fail closed.
4. Mark the Catalog backend unready; distinguish edge 503s, SCG 503s, and backend HTTP 503s.
5. Perform a rolling update across SCG replicas and observe readiness and graceful draining.
6. Verify route listings and Actuator endpoints remain unreachable outside the management network.
7. Test canary splits or single-layer retries against a backend stub; count attempts and **never retry non-idempotent POSTs**.

### Part F — Report and Passing Criteria

Your report should cover:

- A three-layer diagram: **Kubernetes config/controller/data plane - SCG application - backend**.
- Adjusted Ingress and `GatewayClass`/`Gateway`/`HTTPRoute` manifests matching your controller.
- Exact Kubernetes version, Gateway API CRD/controller conformance, and Spring Boot/SCG starter versions.
- Authorization breakdown across `allowedRoutes`, `ReferenceGrant`, RBAC, and `NetworkPolicy`.
- TLS termination per hop plus cert rotation and trust model.
- Backend request journal results for GET/POST, path rewrites, headers, response codes, and hit counts.
- Security verification across anonymous/user/admin/JWT calls, CORS, and forwarding-header spoofing.
- Metrics, fault injection, rolling update observations, and rollback plan.
- Architectural decision on Ingress vs. Gateway API and whether to retain SCG, backed by evidence.

**Passing criteria:** Learners can explain **which resource declares infrastructure, which controller executes it, and what SCG owns**, deploy at least one edge option wired to tested HTTP backends, demonstrate namespace boundaries and security cannot be bypassed, and document a canary/rollback plan.

## 25. Decision Framework and Common Misconceptions

Do not start by asking "Which is best: Ingress, Gateway API, or Spring Cloud Gateway?" Start with **three separate questions**:

1. **What receives public traffic?** An Ingress controller, Gateway API controller, or another public load balancer?
2. **Which policies belong at the edge?** TLS termination, host/path routing, header policies, built-in auth, traffic splitting, cross-namespace delegation?
3. **Do you need an application gateway?** Custom Java filters, Spring Security, service discovery, domain-specific API transformations, fallbacks, or policies your edge controller cannot handle?

### 25.1. Situational recommendations

| Situation | Configuration to consider | Why |
| --- | --- | --- |
| A few HTTP services, simple TLS + host/path | **Ingress + controller** | Straightforward when an Ingress stack already runs reliably |
| Shared cluster where multiple teams own routes independently | **Gateway API + controller** | Clear role split across `Gateway`/`GatewayClass`/`HTTPRoute` and attachment rules |
| Structured path/header matching, delegated routes, supported canaries | **Gateway API** | Clean L7 configuration with conformance verification |
| Spring Security logic and custom Java filters across APIs | **Ingress/Gateway API -> Spring Cloud Gateway** | Keeps application-level policies inside the app gateway |
| Backends/edge already cover policies; extra hop adds cost with no gain | **Edge controller -> Service directly** | Fewer moving parts while preserving security/observability parity |
| Need Spring Cloud Gateway outside Kubernetes | **SCG behind a suitable LB/reverse proxy** | Independent of Kubernetes routing APIs |
| Special TCP/UDP/gRPC routing needs | **Inspect protocol-specific Gateway API resources and controller support** | Neither core Ingress nor SCG supports every L4/L7 protocol automatically |
| Current controller lacks a needed feature | **SCG or another controller extension** | Weigh security, vendor support, and operational cost |
| Existing Ingress is rock-solid and migration carries high risk | **Keep Ingress with targeted improvements** | Avoid migrating purely for hype |

### 25.2. Gateway API includes more than HTTPRoute, though not every controller implements all kinds

Gateway API defines route types across protocols and channels, including **HTTPRoute**, **GRPCRoute**, and TCP/TLS/UDP routes in supporting channels/releases. That **does not turn an `HTTPRoute` into a raw TCP load balancer**, nor guarantee your installed controller supports every kind. Always check:

- Which CRDs and API versions are actually installed in the cluster.
- Controller conformance and supported filters for your target protocol.
- TLS credential handling, passthrough vs. termination, and backend protocols.
- Access control, cross-namespace policies, and status/telemetry coverage for that route kind.

**Spring Cloud Gateway Server WebFlux/Web MVC is primarily an application-layer HTTP gateway**, with WebSocket support depending on stack, version, and configuration. It does not replace a generic L4 controller for raw TCP/UDP routing. Never pick a tool solely because its name contains "gateway".

### 25.3. Common misconceptions vs. reality

| Misconception | Reality |
| --- | --- |
| "Ingress is the Ingress controller." | `Ingress` is an API object; the controller/data plane performs the routing. |
| "Applying Ingress YAML turns on HTTPS automatically." | You also need a controller, LoadBalancer/address, public DNS, and a valid TLS Secret/cert. |
| "Gateway API is a proxy built into Kubernetes." | Gateway API is a spec and set of CRDs/resources; a controller/data plane is required. |
| "Creating a GatewayClass makes routes work." | A controller must claim the class, configure the Gateway listener, and attach/resolve `HTTPRoute`s. |
| "`GatewayClass`/`Gateway`/`HTTPRoute` are Spring Cloud Gateway objects." | They are Kubernetes Gateway API resources, not SCG route definitions. |
| "An attached `HTTPRoute` can target any namespace's Services." | `allowedRoutes` governs attachment; cross-namespace backend references also require `ReferenceGrant`. |
| "`ReferenceGrant` grants HTTP access to users." | It permits Kubernetes object references—it does not grant JWT scopes or network access. |
| "Gateway API includes built-in JWT, rate limits, retries, and mirroring everywhere." | Support varies by controller conformance, extensions, and API release. |
| "Ingress annotations port cleanly between controllers." | Annotations are typically implementation-specific. |
| "Matching `/api` in Ingress/Gateway API strips the prefix." | Path matching and URL rewriting are distinct actions. |
| "If Gateway API rewrites the path, SCG should also `StripPrefix`." | Double rewriting causes conflicts; designate one clear owner. |
| "A Kubernetes Service with a matching port means the backend is Ready." | You need ready `EndpointSlice`s and matching container/`Service` ports. |
| "`lb://catalog` automatically queries Kubernetes `Service`s." | SCG LoadBalancer requires a `ServiceInstance`/discovery integration. |
| "Public HTTPS means internal hops are also HTTPS." | Each Edge->SCG->backend hop manages its own protocol and TLS. |
| "`X-Forwarded-For` is always the trustworthy client IP." | Trust it only after proper trusted-proxy normalization. |
| "A private SCG route prevents direct backend access." | Backends still require authentication/authorization and `NetworkPolicy`. |
| "Spring Cloud Gateway replaces an Ingress controller on its own." | SCG is an application; you still need public exposure, TLS, DNS, and network ingress. |
| "Adding SCG automatically improves security." | Only when auth/token policies are solid and don't add bypass/SSRF/management exposure. |
| "Removing SCG always cuts latency significantly." | Benchmark under identical policies; bottlenecks often live in backends or edge pools. |
| "Migrating to Gateway API requires deleting SCG." | You can swap only the edge layer while keeping SCG for business/API policies. |
| "An HTTP 404 pinpoints which route failed." | Edge, SCG, and backend can all return 404; check provenance and metrics. |
| "Actuator behind `ClusterIP` needs no protection." | Other Pods in the cluster can still call it; enforce auth and network isolation. |
| "Per-Pod rate limits act as a cluster-wide quota." | Distributed quotas normally require a shared store and consistent policy. |
| "A 90/10 weighted `HTTPRoute` splits 10 requests strictly 9 and 1." | Traffic splits are statistical and depend on controller algorithms and sample volume. |

### 25.4. Pre-production architecture review checklist

~~~text
[ ] Exact Ingress controller or Gateway API controller/data plane identified.
[ ] GatewayClass/controllerName and supported CRDs/conformance verified.
[ ] Each public hostname has one unambiguous entrypoint, DNS, and rollback plan.
[ ] TLS termination and mTLS mapped per hop; trust-all disabled everywhere.
[ ] Ingress/HTTPRoute host/path/method matching aligned with zero double rewrites.
[ ] Namespace route attachment and cross-namespace ReferenceGrants follow least privilege.
[ ] Kubernetes RBAC, NetworkPolicy, and secret management reviewed.
[ ] Service ports, targetPorts, ready EndpointSlices, and SCG probes verified.
[ ] SCG starter and route YAML namespace match Server WebFlux or Web MVC.
[ ] Both SCG and backends enforce authorization and validate JWT audiences.
[ ] Trusted proxies/Forwarded headers and rate-limit keys hardened against spoofing.
[ ] Auth, CORS, redirects, and response headers each have one owner per boundary.
[ ] Retries, circuit breakers, and canaries do not stack unintentionally.
[ ] Actuator/admin/metrics endpoints are never publicly exposed or unprotected.
[ ] Backend HTTP request journal verifies final path, method, headers, and hit counts.
[ ] Automated tests cover 2xx/3xx/4xx/5xx, TLS failures, empty endpoints, and rollouts.
[ ] Metrics and traces distinguish edge, SCG, outbound HTTP, and backend.
[ ] Canary, SLO gates, runbooks, rollout, and rollback plans are rehearsed.
~~~

## 26. Summary

- **Kubernetes Ingress** is a Kubernetes HTTP/HTTPS routing API resource; an **Ingress controller** reconciles it and runs the request-handling data plane.
- **Kubernetes Gateway API** is a family of Kubernetes APIs—typically `GatewayClass`, `Gateway`, `HTTPRoute`, and `ReferenceGrant`—with clearer platform/app separation, yet it **still requires a controller/data plane**, CRDs, and feature conformance.
- **Spring Cloud Gateway** is a **Java/Spring Boot application** that receives and proxies HTTP requests, adding route predicates, filter chains, header/path rewriting, service discovery, Spring Security, rate limiting, retries, circuit breaking, and observability; it is **not a Kubernetes Gateway resource**.
- **Ingress/Gateway API and SCG can work together**: the edge owns public TLS/hosts/entry traffic while SCG owns application/API policies—or the edge can route **directly** to business Services when SCG is unnecessary.
- **`allowedRoutes`** governs which `HTTPRoute`s attach to a Gateway, while **`ReferenceGrant`** governs allowed cross-namespace object references. Neither replaces Kubernetes RBAC, `NetworkPolicy`, or API authorization.
- **Kubernetes `Service`**, `backendRefs`, and **SCG `lb://`** are distinct routing/discovery abstractions; using `lb://` requires an integration supplying `ServiceInstance`s.
- **TLS termination at the edge does not encrypt in-cluster hops**. Secure each hop and verify hostnames/CA/mTLS per policy; never trust client-supplied forwarding headers or `Host` for authorization or upstream selection.
- **Every path/header transformation, CORS rule, redirect, retry, or rate limit needs one clear owner**. Duplicating them across two proxies invites double rewrites, redirect loops, retry storms, credential leaks, and broken quotas.
- **A valid deployment requires three kinds of evidence:** Kubernetes resource/controller status, healthy Services/Pods, and verified client-to-backend HTTP paths. A passing `kubectl apply` or a single `curl 200` proves neither security nor rollout readiness.
- **Migrating from Ingress to Gateway API** can replace only the edge layer **without requiring the removal of Spring Cloud Gateway**. Evaluate functionality, security, performance, SLOs, and operations against your real controller before deciding.

Final principle: **make explicit who owns traffic configuration, who executes HTTP forwarding, who enforces identity, and who owns the API contract**. Once those boundaries are crystal clear, you can deploy Ingress, Gateway API, and Spring Cloud Gateway in their proper roles—avoiding redundant proxy layers while keeping your microservices API gateway observable, upgradeable, and safe to roll back.

### Version-Specific References

- **Kubernetes Ingress:** https://kubernetes.io/docs/concepts/services-networking/ingress/
- **Kubernetes Service:** https://kubernetes.io/docs/concepts/services-networking/service/
- **Kubernetes Gateway API:** https://gateway-api.sigs.k8s.io/
- **Gateway API HTTPRoute:** https://gateway-api.sigs.k8s.io/api-types/httproute/
- **Gateway API ReferenceGrant:** https://gateway-api.sigs.k8s.io/api-types/referencegrant/
- **Spring Cloud Gateway reference:** https://docs.spring.io/spring-cloud-gateway/reference/

Match documentation to your **Kubernetes/Gateway API CRD versions, Gateway/Ingress controller, Spring Boot/SCG starters, and target runtime**. This lesson provides patterns and examples for testing; controller names, hosts, namespaces, Services, and container images in the manifests are **illustrative only** and must not be applied verbatim to production without approval.

# ServiceAccount and Resource Read Permissions for Discovery

When Spring Cloud Kubernetes uses the Kubernetes API to discover services, the application running inside a Pod needs an identity to authenticate with the API server. That identity is typically the **ServiceAccount** assigned to the Pod. Kubernetes RBAC determines which resources the ServiceAccount can read, in which namespaces, and using which operations.

A ServiceAccount only provides identity; it does not automatically grant permissions to read Services, Endpoints, or Pods. For discovery to work, you must grant the right `get`, `list`, and `watch` permissions on the resources used by the implementation. Granting insufficient permissions usually causes `Forbidden` errors; granting overly broad permissions can let a microservice read topology from unrelated namespaces.

## 1. A ServiceAccount is the workload's identity

A Kubernetes ServiceAccount represents an application or workload when it calls the Kubernetes API. Every namespace has a `default` ServiceAccount, but production environments should create a dedicated ServiceAccount per application or per group of applications sharing identical permissions.

When a Pod declares `spec.serviceAccountName`, kubelet provides authentication credentials to the container according to the ServiceAccount configuration. With modern projected tokens, tokens have an expiration time and are automatically refreshed by kubelet. Clients inside the Pod use the token along with the cluster CA certificate for TLS authentication to the API server.

Kubernetes identifies the identity in the form:

```text
system:serviceaccount:<namespace>:<service-account-name>
```

For example, a Pod in the `commerce` namespace using the `checkout-discovery` ServiceAccount has the identity:

```text
system:serviceaccount:commerce:checkout-discovery
```

When the Spring Cloud Kubernetes discovery client calls the API to list Services or Endpoints, the API server authenticates the token and then checks RBAC for this identity. If no matching binding exists, the API server returns `403 Forbidden`.

### Creating a dedicated ServiceAccount

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: checkout-discovery
  namespace: commerce
automountServiceAccountToken: true
```

`automountServiceAccountToken: true` allows Kubernetes to automatically mount the token into Pods using this ServiceAccount. This setting is required when an application uses an in-cluster Kubernetes client by default. If an application does not call the Kubernetes API, auto-mounting can be disabled to reduce unnecessary credentials.

Do not use the `default` ServiceAccount for all workloads. When multiple applications share one identity, it becomes hard to enforce least privilege and hard to trace which application issued an API query.

## 2. Attaching a ServiceAccount to a Pod

The Pod or Deployment must declare the right ServiceAccount. Example Deployment for `checkout-service`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-service
  namespace: commerce
spec:
  replicas: 2
  selector:
    matchLabels:
      app: checkout-service
  template:
    metadata:
      labels:
        app: checkout-service
    spec:
      serviceAccountName: checkout-discovery
      containers:
        - name: application
          image: example/checkout-service:1.0.0
          ports:
            - name: http
              containerPort: 8080
```

`serviceAccountName` must match the ServiceAccount name in the same namespace as the Pod. If omitted, the Pod normally uses the namespace's `default` ServiceAccount; RBAC permissions bound to `checkout-discovery` will have no effect.

If a Pod sets `automountServiceAccountToken: false`, the Pod-level setting can prevent the token from mounting automatically even if the ServiceAccount allows it. Only disable auto-mount when the application does not need to call the Kubernetes API or has an intentional alternative credential mechanism configured.

## 3. Which resources does the discovery client read?

Kubernetes represents services and backend addresses with multiple resources. Spring Cloud Kubernetes may use Services, Endpoints, EndpointSlices, or Pods depending on discovery mode, library version, and configuration. Permissions must match the exact data types the application actually queries.

| Resource | API group | Data used for discovery | When permission is needed |
| --- | --- | --- | --- |
| `services` | Core API (`""`) | Service name, selector, ports, namespace, and metadata | When the client lists or reads Kubernetes Services |
| `endpoints` | Core API (`""`) | Backend addresses and ports selected by a Service | When the implementation reads legacy Endpoints |
| `endpointslices` | `discovery.k8s.io` | Endpoint list split into slices | When the implementation reads EndpointSlices |
| `pods` | Core API (`""`) | Pod IP, labels, readiness, metadata, or Pod-based discovery | When the discovery mode or filter needs to read Pods directly |
| `namespaces` | Core API (`""`) | List of namespaces when discovering across multiple namespaces | When the client actually lists namespaces |

Not every application needs all of the resources above. For example, if a client only looks up Services and Endpoints in the current namespace, it does not need permissions to read Pods or Namespaces. If the discovery client version reads EndpointSlices, `endpoints` permission alone may be insufficient.

### How do Service and Endpoint differ?

- **Service** defines a stable endpoint, selector, ports, and access policy.
- **Endpoints** or **EndpointSlice** reflect the actual backends the Service points to.
- **Pod** holds the status and metadata of an individual workload. Some discovery modes read Pods for detailed metadata or status filtering.

A Service can exist without Endpoints yet if its selector matches no Pods, Pods are not Ready, or the workload has not produced endpoints. That case is not necessarily an RBAC error.

## 4. Required RBAC verbs

RBAC differentiates permissions by resource and verb. For service discovery, the commonly used read permissions are:

| Verb | Meaning | Scenario |
| --- | --- | --- |
| `get` | Read a specific resource | Fetch details of a Service, Endpoint, or Pod |
| `list` | List resources within the granted scope | Find Services or backends in a namespace |
| `watch` | Watch resource changes | Update lists when Services, Endpoints, or Pods change |

Many clients perform `list` to get an initial snapshot and then `watch` to receive updates. If only `get` is granted, the client can read a known object by name but cannot dynamically discover lists. If `watch` is missing, the application might start yet fail to receive timely updates or have to fall back to polling depending on the implementation.

For read-only discovery, verbs such as `create`, `update`, `patch`, or `delete` on Services, Endpoints, EndpointSlices, or Pods are generally not needed. Write permissions belong to controllers, deployment pipelines, or administrative components that create resources.

## 5. Granting permissions within one namespace using Role and RoleBinding

If `checkout-service` only discovers services in the `commerce` namespace, use a Role and RoleBinding inside that same namespace.

Example Role for discovery via Services and Endpoints:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-service-discovery-reader
  namespace: commerce
rules:
  - apiGroups: [""]
    resources:
      - services
      - endpoints
    verbs:
      - get
      - list
      - watch
```

If the implementation needs EndpointSlices, add the corresponding rule:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-endpointslice-reader
  namespace: commerce
rules:
  - apiGroups: ["discovery.k8s.io"]
    resources:
      - endpointslices
    verbs:
      - get
      - list
      - watch
```

If the discovery mode needs to read Pods, add a `pods` rule under the core API group:

```yaml
rules:
  - apiGroups: [""]
    resources:
      - pods
    verbs:
      - get
      - list
      - watch
```

Add only the rules actually needed. The separate Role snippets above are illustrative examples; in deployment manifests, rules can be combined into a single Role for centralized management.

### Binding the Role to the ServiceAccount

A Role does not grant permissions to a Pod by itself. You need a RoleBinding referencing the Role and ServiceAccount:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-service-discovery
  namespace: commerce
subjects:
  - kind: ServiceAccount
    name: checkout-discovery
    namespace: commerce
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: checkout-service-discovery-reader
```

A RoleBinding restricts permissions to the `commerce` namespace. The ServiceAccount only has permission to read the resources listed in the Role within that namespace.

## 6. Discovering services in another namespace

An application may run in the `commerce` namespace while needing to find services in the `catalog` namespace. Cluster-wide permissions are not necessarily required. You can create a Role in the target namespace and a RoleBinding in that namespace referencing the ServiceAccount from the source namespace.

Example RoleBinding placed in the `catalog` namespace:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-read-catalog-services
  namespace: catalog
subjects:
  - kind: ServiceAccount
    name: checkout-discovery
    namespace: commerce
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: catalog-discovery-reader
```

The `catalog-discovery-reader` Role must also exist in the `catalog` namespace. This binding grants the `commerce/checkout-discovery` identity permission to read resources in `catalog`, without granting similar permissions in other namespaces.

If querying several specific namespaces is required, you can create corresponding RoleBindings in each target namespace. This approach makes access clearer and easier to audit than a cluster-wide ClusterRoleBinding.

## 7. When are ClusterRole and ClusterRoleBinding needed?

If the discovery client is configured to list Services/Endpoints across the entire cluster, or needs to list Namespaces, a single-namespace Role is insufficient. In that case, you can create a ClusterRole and ClusterRoleBinding.

Example ClusterRole granting read-only access to Services and Endpoints across all namespaces:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: checkout-global-discovery-reader
rules:
  - apiGroups: [""]
    resources:
      - services
      - endpoints
    verbs:
      - get
      - list
      - watch
```

Bind those permissions to the ServiceAccount:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: checkout-global-discovery
subjects:
  - kind: ServiceAccount
    name: checkout-discovery
    namespace: commerce
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: checkout-global-discovery-reader
```

A ClusterRoleBinding grants cluster-wide permissions to this ServiceAccount. Use it only when the application truly needs that scope. If only a few namespaces are needed, prefer RoleBindings in each target namespace.

If listing namespaces is required to search services across multiple namespaces, add read permission for `namespaces` in the core API. Do not grant this permission simply because an online example includes it; verify that the discovery client actually calls the namespace API.

## 8. EndpointSlice and version compatibility

Modern Kubernetes supports EndpointSlice via the `discovery.k8s.io` API group. EndpointSlice splits a Service's endpoints into multiple objects, handling services with large backend counts more efficiently.

A discovery client may read Endpoints, EndpointSlices, or both depending on version and configuration. Therefore:

- Check the documentation for the exact Spring Cloud Kubernetes version in use.
- Check API client logs to identify which resources and API groups are called.
- Grant `get`, `list`, `watch` for `endpointslices` if the implementation actually uses them.
- Do not grant `*` on all resources or all API groups just to work around a `Forbidden` error.

Example EndpointSlice rule:

```yaml
- apiGroups: ["discovery.k8s.io"]
  resources:
    - endpointslices
  verbs:
    - get
    - list
    - watch
```

Note that permissions on `endpoints` belong to the core API group `""`, whereas `endpointslices` belong to `discovery.k8s.io`. Specifying the wrong API group prevents RBAC from matching even if the resource name looks right.

## 9. Configuring Spring Cloud Kubernetes Discovery

When an application runs in a Pod, the Kubernetes client can normally auto-detect in-cluster configuration, reading the API server address, mounted token, and CA certificate. The application needs the appropriate discovery starter and a ServiceAccount attached to the Pod.

Example Maven dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-client</artifactId>
</dependency>
```

Spring Cloud Kubernetes has variants based on Kubernetes Client or Fabric8; choose the starter matching the implementation used by the project and manage versions via the Spring Cloud BOM. Exact starter names may vary across release trains.

Example configuring discovery within a single namespace:

```yaml
spring:
  application:
    name: checkout-service
  cloud:
    kubernetes:
      discovery:
        enabled: true
        all-namespaces: false
```

With namespace-scoped configuration, the client normally discovers services in the application's namespace or configured namespaces. If enabling discovery across multiple namespaces, verify the properties for the version in use and grant corresponding RBAC in each namespace or at cluster scope.

Namespace and discovery mode properties can change across Spring Cloud Kubernetes versions. Do not copy configuration from another release train without checking the reference docs for the dependency in use. RBAC must reflect the exact resources queried by the specific implementation.

## 10. Does service discovery with Kubernetes DNS require RBAC?

Not every way of calling services in Kubernetes requires Spring Cloud Kubernetes DiscoveryClient.

If a consumer calls a Kubernetes Service via internal DNS, for example:

```text
http://inventory-service.commerce.svc.cluster.local:8080
```

Kubernetes DNS resolves the Service name and the Kubernetes dataplane forwards traffic to backends. The application only needs functioning networking and DNS; it does not need to read Services or Endpoints via the Kubernetes API on each call.

If the application uses `DiscoveryClient` to list services, read metadata, or select instances itself, it needs access to the Kubernetes API and an appropriate ServiceAccount/RBAC. The two models have different goals:

| Call method | Resolution component | Needs API read permissions? |
| --- | --- | --- |
| Kubernetes Service DNS | CoreDNS and Kubernetes Service dataplane | No, when only using standard DNS/networking |
| Spring Cloud Kubernetes DiscoveryClient | Kubernetes API and discovery implementation | Yes, for the queried resources/verbs |
| Spring Cloud LoadBalancer with Kubernetes discovery | DiscoveryClient supplies instances, LoadBalancer picks an instance | Yes, if the discovery source queries the API |

Choose the simplest option that satisfies your requirements. If you only need to call a stable Service within the same cluster, DNS is usually enough. If you need an instance list, metadata, or client-side backend selection logic, DiscoveryClient may be a better fit.

## 11. Verifying permissions with kubectl

After applying the ServiceAccount, Role, and RoleBinding, test permissions using the actual identity. For example:

```bash
# Can the ServiceAccount list Services in the commerce namespace?
kubectl auth can-i list services \
  --as=system:serviceaccount:commerce:checkout-discovery \
  -n commerce

# Can it watch Endpoints?
kubectl auth can-i watch endpoints \
  --as=system:serviceaccount:commerce:checkout-discovery \
  -n commerce

# Can it read EndpointSlices?
kubectl auth can-i list endpointslices.discovery.k8s.io \
  --as=system:serviceaccount:commerce:checkout-discovery \
  -n commerce

# List effective permissions in the namespace
kubectl auth can-i --list \
  --as=system:serviceaccount:commerce:checkout-discovery \
  -n commerce
```

The `kubectl auth can-i --as=...` command requires the caller to have permission to impersonate the specified identity. If you do not have impersonation permission, run the check with an appropriate administrative account or verify from inside the Pod itself.

Check that the Pod is using the right ServiceAccount:

```bash
kubectl get pod -n commerce -l app=checkout-service \
  -o jsonpath='{.items[*].spec.serviceAccountName}'
```

Check the Service and Endpoints:

```bash
kubectl get service inventory-service -n commerce
kubectl get endpoints inventory-service -n commerce
kubectl get endpointslices -n commerce \
  -l kubernetes.io/service-name=inventory-service
```

If the API returns `Forbidden`, verify the identity, namespace, resource, API group, and verb. If permissions are right yet the Endpoint list is empty, check the Service selector, Pod labels, and backend readiness.

## 12. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `system:serviceaccount:... cannot list services` | Missing `list services` or Pod uses the wrong ServiceAccount | Check `serviceAccountName`, Role, and RoleBinding |
| Can read Services but sees no backends | Missing Endpoints/EndpointSlices read permission or backends not Ready | Grant right endpoint permissions; check selector and readiness |
| Starts up but does not receive updates | Missing `watch` or implementation is polling per config | Check watch RBAC and discovery client logs |
| Works locally but gets 403 in cluster | Local environment uses personal kubeconfig with broad permissions | Check ServiceAccount token and RBAC in the Pod |
| Created Role yet still denied | Missing RoleBinding or wrong namespace/name in binding | Check `subjects` and `roleRef` in the RoleBinding |
| RoleBinding in app namespace cannot read other namespaces | RoleBinding only grants permissions in the namespace where it resides | Create Role/RoleBinding in target namespaces or use ClusterRole as needed |
| Enabled all-namespaces yet only sees one namespace | RBAC is still restricted or lacks permissions to list namespaces/resources in scope | Check scope config and bindings per namespace |
| `endpointslices` gets Forbidden even though `endpoints` is allowed | EndpointSlice belongs to a different API group | Add a `discovery.k8s.io` rule for `endpointslices` |
| No token in Pod | Auto-mount disabled or misconfigured projected token | Check ServiceAccount and Pod `automountServiceAccountToken` |
| Service exists yet `DiscoveryClient` returns empty list | Service has no backends, wrong namespace, or filter excludes instances | Check Endpoints, readiness, namespace, and discovery mode |

## 13. Security and the least-privilege principle

Read permissions on Kubernetes resources can also expose internal topology: service names, Pod addresses, ports, labels, and metadata. Limit permissions to actual needs.

- Create a dedicated ServiceAccount for each application that needs the Kubernetes API.
- Use Role/RoleBinding when discovering within a single namespace.
- Use RoleBindings in each target namespace if access to only a few specific namespaces is needed.
- Use ClusterRoleBinding only when the application genuinely needs cluster-wide read access.
- Grant only `get`, `list`, `watch` for the required discovery resources.
- Do not grant create, update, or delete permissions on Services, Endpoints, EndpointSlices, or Pods to discovery consumers.
- Do not mount tokens into workloads that do not call the Kubernetes API.
- Do not copy ServiceAccount tokens into configuration files or bake them into container images.
- Secure the API server with TLS and maintain appropriate network policies.
- Monitor audit logs to track which ServiceAccount read resources and from where.

Do not use `resources: ["*"]`, `verbs: ["*"]`, or broad ClusterRoleBindings just to make discovery "work". If an implementation requires another resource, identify the exact API call and add the minimal rule.

### Note on `resourceNames`

RBAC supports `resourceNames` for certain operations on specific objects, but this restriction generally does not fit dynamic discovery. `list` and `watch` operations can only be restricted by name when requests use a matching field selector; not every discovery client sends that selector. Therefore, do not add `resourceNames` and assume the client can still list any new service.

## 14. Deployment checklist

- [ ] Create a dedicated ServiceAccount in the workload's namespace.
- [ ] Set the right `serviceAccountName` on the Pod template.
- [ ] Confirm the token is mounted if the application needs to call the Kubernetes API.
- [ ] Identify whether the discovery client reads Services, Endpoints, EndpointSlices, Pods, or Namespaces.
- [ ] Grant only `get`, `list`, `watch` on the resources actually needed.
- [ ] Use Role/RoleBinding for single-namespace scope.
- [ ] Use RoleBindings in target namespaces if only a few other namespaces are needed.
- [ ] Use ClusterRoleBinding only when cluster-wide scope is needed.
- [ ] Verify permissions with `kubectl auth can-i` for the exact ServiceAccount.
- [ ] Verify Endpoints have backends and Pods are Ready.
- [ ] Verify `watch` works so updates arrive when services or endpoints change.
- [ ] Protect tokens and limit permissions under the least-privilege principle.

A ServiceAccount identifies which application is calling the Kubernetes API; RBAC determines which resources that application can read and within what scope. With Spring Cloud Kubernetes Discovery, start from the actual resources queried by the discovery implementation, then grant least-privilege read access using Roles/RoleBindings. Expand to multiple namespaces or cluster scope only when there is an explicit requirement. This approach keeps service instances up to date while preserving proper access boundaries for each microservice.

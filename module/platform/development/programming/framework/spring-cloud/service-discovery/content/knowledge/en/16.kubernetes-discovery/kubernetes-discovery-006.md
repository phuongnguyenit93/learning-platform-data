# Readiness State and the Ready Endpoint List

## 1. What role does readiness play in service discovery?

In Kubernetes, a Pod may be running yet not ready to accept requests. For example, an application may have just started and still be loading configuration, connecting to a database, or warming up initial data. If a Service sends traffic to the Pod during this phase, requests can fail even though the container is in the Running state.

Kubernetes uses **readiness** to indicate whether a Pod should receive traffic. Readiness results are reflected in the Pod's status and the list of endpoints published by the Service. As a result, clients or proxies can select only ready addresses.

In Spring Cloud Service Discovery, three concepts should be distinguished:

- **Pod readiness:** the readiness state of a Pod according to probe results and readiness gates.
- **Service endpoint:** the IP/port address of a Pod managed by a Service, along with conditions such as ready, serving, and terminating.
- **Discovery result:** the list of instances an application obtains from the Kubernetes API or the DiscoveryClient abstraction.

Readiness keeps unready Pods out of the set of endpoints receiving normal traffic. It does not prove every business operation will succeed and does not replace timeouts, retries, or health checks on the caller side.

## 2. Readiness probe, liveness probe, and startup probe

Kubernetes has three common probe types. Each probe answers a different question:

| Probe | Question | When it fails |
|---|---|---|
| Readiness | Can the container accept traffic right now? | Pod is marked NotReady; normal endpoints are not selected to receive traffic |
| Liveness | Is the container still healthy or stuck in a state requiring a restart? | Kubelet restarts the container after reaching the failure threshold |
| Startup | Has the application finished initial startup? | Kubelet continues checking startup; liveness/readiness are delayed until startup succeeds |

A failing readiness probe does not restart the container. The container can keep running, handle internal tasks, or recover dependencies, and then return to Ready when the probe succeeds.

A liveness probe should not check external dependencies in a way that causes a database outage to make Kubernetes restart Pods en masse. Readiness is better suited to temporarily stop routing traffic to a Pod that cannot serve requests.

## 3. Configuring a readiness probe for a Spring Boot application

A Spring Boot application typically exposes health endpoints via Spring Boot Actuator. When the health endpoint is enabled, you can configure an HTTP readiness probe pointing to the readiness health group:

~~~yaml
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

In a Kubernetes Deployment, the readiness probe configuration can look like this:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
    spec:
      containers:
        - name: payment-service
          image: example/payment-service:2.5.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~

The parameters above are examples only. Tune startup time, response latency, and failure thresholds for your application. If the application needs a long startup time, consider a startup probe so readiness and liveness do not evaluate the container too early.

### 3.1. Choosing health indicators for readiness

Spring Boot Actuator can provide health groups such as liveness and readiness. An application should include in the readiness group the conditions that genuinely determine its ability to accept requests.

For example:

- An application cannot process requests if it fails to load mandatory configuration.
- A service depending on a synchronous database may need to check database connectivity.
- A worker that does not accept HTTP traffic may need different readiness criteria than a web API.

Do not include every optional dependency in readiness. If a non-essential auxiliary service has a temporary outage while the Pod can still handle most requests, marking the entire Pod NotReady can unnecessarily reduce capacity.

## 4. From Pod readiness to EndpointSlice

A Kubernetes Service selects Pods through a label selector. The EndpointSlice controller watches Pods matching the selector and creates or updates EndpointSlices containing endpoint addresses.

When a Pod's readiness changes:

1. Kubelet updates the Pod status after the probe is evaluated.
2. The Pod Ready condition changes.
3. The EndpointSlice controller observes the Pod change.
4. Endpoint conditions in the EndpointSlice are updated.
5. Kube-proxy, ingress controllers, or clients using the Kubernetes API can update the set of addresses they use.

~~~mermaid
flowchart TD
    PROBE[Container readiness probe] --> POD[Pod Ready condition]
    POD --> CTRL[EndpointSlice controller]
    CTRL --> SLICE[EndpointSlice conditions and addresses]
    SLICE --> PROXY[Kube-proxy / Ingress / Gateway]
    SLICE --> DISC[Spring Cloud Kubernetes Discovery]
    PROXY --> TRAFFIC[Traffic to eligible endpoints]
    DISC --> CLIENT[DiscoveryClient / LoadBalancer]
~~~

EndpointSlice is the modern API for representing Service endpoints. Kubernetes still maintains the legacy Endpoints resource for compatibility, but EndpointSlice is better suited when there are many endpoints or the list must be split into multiple slices.

## 5. Reading endpoint conditions

An endpoint in an EndpointSlice can have the following conditions:

| Condition | Meaning |
|---|---|
| ready | Whether the endpoint is ready to receive traffic per Service rules |
| serving | Whether the endpoint is currently serving; useful for distinguishing serving state from termination |
| terminating | Whether the endpoint is in the process of terminating |

The `ready` field may be omitted in some older responses or compatibility cases. When the `ready` condition is not set, clients must apply the API's default rules rather than treating a missing value as false.

A terminating endpoint may still be kept in an EndpointSlice during graceful shutdown. Depending on policy and version, the endpoint may no longer be considered ready for new traffic while still marked serving while finishing existing connections.

For a Service configured with `publishNotReadyAddresses`, endpoints can be published even when a Pod is not Ready. This is intentional behavior in some peer discovery or bootstrap systems; do not enable this option for standard HTTP Services if you want readiness to exclude unready Pods from traffic.

## 6. Service selector and endpoint list

Example of a Service selecting Pods with the label `app=payment-service`:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: payment-service
spec:
  selector:
    app: payment-service
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
~~~

The Deployment must attach matching labels to its Pod template. If the selector does not match the labels, the Service will have no endpoints even if Pods are Running and Ready.

The Service port and container port can differ. In the example, clients call port 80 on the Service, while traffic is forwarded to the container port named `http` (8080). When inspecting EndpointSlices, check the published target port rather than assuming it always equals the Service port.

### 6.1. Checking with kubectl

List the Service:

~~~bash
kubectl get service payment-service
~~~

Read EndpointSlices:

~~~bash
kubectl get endpointslices -l kubernetes.io/service-name=payment-service
~~~

View address and condition details:

~~~bash
kubectl describe endpointslice -l kubernetes.io/service-name=payment-service
~~~

Read Pods and readiness:

~~~bash
kubectl get pods -l app=payment-service
kubectl describe pod <pod-name>
~~~

To view structured output:

~~~bash
kubectl get endpointslices -l kubernetes.io/service-name=payment-service -o yaml
~~~

In the output, inspect:

- `addresses`: IP addresses of the endpoints.
- `ports`: published target ports.
- `conditions.ready`: whether the endpoint is ready.
- `conditions.serving`: whether the endpoint is serving.
- `conditions.terminating`: whether the endpoint is terminating.
- `targetRef`: the Pod or object the endpoint represents.

## 7. EndpointSlice and the legacy Endpoints resource

The following command is still commonly used to inspect the compatibility endpoint list:

~~~bash
kubectl get endpoints payment-service
~~~

The legacy Endpoints resource can show addresses under subsets:

- `addresses`: endpoint addresses considered ready.
- `notReadyAddresses`: addresses not ready.
- `ports`: ports exposed by the Service for the endpoints.

EndpointSlice divides the list into smaller slices and supports richer endpoint conditions. When debugging modern Kubernetes, inspect EndpointSlice; you can cross-check Endpoints if an older tool or client still reads that API.

Do not assume Endpoints and EndpointSlice output always share the same format. The two resources have different data models, and EndpointSlice is Kubernetes's preferred source for many modern networking components.

## 8. Spring Cloud Kubernetes using ready endpoints

Spring Cloud Kubernetes Discovery integrates with the Kubernetes API to locate Services and their corresponding Pods/endpoints. Depending on discovery mode, version, and configuration, the application may obtain information from Services, Endpoints, or EndpointSlices.

At the application level, Spring Cloud provides the `DiscoveryClient` abstraction to look up instances by service ID. Example:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class ServiceLookup {
    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findPaymentInstances() {
        return discoveryClient.getInstances("payment-service");
    }
}
~~~

When running in Kubernetes, the service ID is usually tied to the Kubernetes Service name. Exact results depend on the discovery provider and how the application is configured. If the application simply calls Kubernetes Service DNS, endpoint selection is normally handled by Kubernetes networking; if the application uses Spring Cloud Kubernetes Discovery and LoadBalancer, it can receive an instance list to select from on the client side.

These two models behave differently:

| Model | Who selects the target Pod? | What data does the client see? |
|---|---|---|
| Calling Service DNS/ClusterIP | Kube-proxy or corresponding data plane | One stable Service address |
| DiscoveryClient + client-side LoadBalancer | Application and LoadBalancer | The instance list returned by the discovery provider |

If using client-side discovery, verify that the provider filters out unready endpoints under your current configuration. Do not infer solely from Pod `Ready=false` that every third-party discovery library will exclude the endpoint identically across all versions.

## 9. Configuration and Kubernetes API permissions

Spring Cloud Kubernetes Discovery needs access to the API server to read discovery resources. Inside the cluster, applications typically authenticate using the ServiceAccount attached to the Pod. Follow the principle of least privilege, allowing read access only to the resource types needed by the discovery mode.

Basic RBAC example to read Services, EndpointSlices, Endpoints, and Pods in a single namespace:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: payment-discovery-reader
  namespace: app
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Bind the Role to the ServiceAccount used by the application:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: payment-discovery-reader
  namespace: app
subjects:
  - kind: ServiceAccount
    name: payment-service
    namespace: app
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: payment-discovery-reader
~~~

This is an example of read permissions for several discovery modes. Actual required resources depend on provider, version, and configuration; if only using Kubernetes Service DNS, the application may not need read permissions on Pods or EndpointSlices. Do not grant cluster-wide permissions if discovery only operates within one namespace.

Verify permissions with:

~~~bash
kubectl auth can-i list services --as=system:serviceaccount:app:payment-service -n app
kubectl auth can-i watch endpointslices.discovery.k8s.io --as=system:serviceaccount:app:payment-service -n app
~~~

## 10. Readiness in rolling updates

When a Deployment updates its image, Kubernetes creates new Pods and waits for them to become Ready before treating them as ready endpoints. With a rolling update, `maxSurge` and `maxUnavailable` determine how many extra new Pods can be created and how many old Pods may temporarily be unavailable.

Example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
~~~

With this configuration, the Deployment can create at most one extra Pod above the replica count and will not intentionally reduce available Pods below the replica count during the rollout. If the readiness probe is configured too leniently, new Pods may enter endpoints before truly serving well. If the probe is too strict, the rollout can slow down or stall.

When old Pods are deleted, Kubernetes can mark endpoints as `terminating` and coordinate stopping new traffic with graceful shutdown. The application should handle `SIGTERM`, stop accepting new requests, finish in-flight requests within `terminationGracePeriodSeconds`, and close connections cleanly.

## 11. Readiness gates and custom serving states

Beyond probes, a Pod can use readiness gates to add Ready conditions from an external controller or system. A Pod is only considered Ready when all required readiness gate conditions transition to `True` alongside container readiness.

Example declaring a custom readiness gate:

~~~yaml
spec:
  readinessGates:
    - conditionType: "example.com/registration-ready"
~~~

An external controller is responsible for updating the corresponding Pod condition. Simply declaring a readiness gate without a component updating the condition will keep the Pod from ever becoming Ready.

Readiness gates are useful when an application must wait for a step outside an HTTP probe, such as registering with a custom orchestrator or completing data synchronization. Do not add a gate unless a reliable controller is responsible for updating its state.

## 12. Common scenarios

| Symptom | Possible cause | How to check |
|---|---|---|
| Pod Running but Service has no ready endpoints | Readiness probe failing or selector mismatch | Describe Pod, Service, and EndpointSlice |
| Pod Ready but endpoint does not appear | Wrong Service selector, controller lag, or wrong namespace | Check labels, selector, and namespace |
| EndpointSlice has address but `ready=false` | Pod not Ready or endpoint in transition | Check Pod conditions and probe events |
| Spring Discovery does not see instances | Missing RBAC permissions, discovery mode, or stale cache | Check API logs, Role/RoleBinding, and discovery configuration |
| Client still calls a Pod that just became NotReady | Client-side cache, LoadBalancer, or data plane not yet updated | Compare EndpointSlice, DiscoveryClient, and supplier list |
| Rollout stuck in Progressing | New Pods fail readiness or insufficient capacity | Describe Deployment/Pod and read probe events |
| Terminating Pod still has active connections | Graceful shutdown and endpoint termination in progress | Check `terminationGracePeriodSeconds`, `preStop`, and connection draining |
| Service has no endpoints at all | No Pods match selector or all Pods are NotReady | Compare selector, labels, and conditions |

## 13. Diagnostic workflow for unready endpoints

When a service receives no traffic or clients cannot find instances, check from the source of truth to the consumer:

1. Read Pod labels and conditions to determine whether the Pod is Ready.
2. Check probe events and logs to find why readiness failed.
3. Check whether the Service selector matches Pod labels.
4. Read EndpointSlices to verify addresses, ports, and `ready`/`serving`/`terminating` conditions.
5. Cross-check the legacy Endpoints resource if an older component uses that API.
6. Check the ServiceAccount, Role, and RoleBinding if Spring Cloud Kubernetes reads the Kubernetes API directly.
7. Inspect `DiscoveryClient` and the instance list supplied by the LoadBalancer supplier.
8. If the list is right yet requests still fail, check NetworkPolicy, ports, protocol, TLS, and business endpoint health.

~~~mermaid
flowchart TD
    START[Client sees no ready endpoints] --> POD[Check Pod Ready and probes]
    POD -->|NotReady| PROBE[Read events, logs, and health group]
    POD -->|Ready| SVC[Check Service selector and namespace]
    SVC -->|Mismatch| LABEL[Fix selector or Pod labels]
    SVC -->|Match| EPS[Check EndpointSlice conditions]
    EPS -->|Missing or unready| CTRL[Check controller, publishNotReadyAddresses, and Pod state]
    EPS -->|Ready| DISC[Check RBAC and DiscoveryClient]
    DISC -->|Not visible| CACHE[Check API watch, cache, and provider]
    DISC -->|Visible| NET[Check LoadBalancer, network, and port]
~~~

## 14. Readiness design principles

- Readiness should reflect the application's actual ability to process requests.
- Include only essential dependencies in readiness; avoid making the whole fleet NotReady due to an optional dependency.
- Use startup probes for slow-starting applications instead of loosening all probes.
- Set timeouts and failure thresholds based on real metrics.
- Ensure Service selectors and Pod labels follow clear conventions.
- Inspect EndpointSlice conditions rather than looking only at a Pod's Running phase.
- Design graceful shutdown so endpoints stop receiving new traffic before the process terminates.
- If using Spring Cloud Kubernetes Discovery, verify RBAC, discovery mode, and endpoint filtering behavior for your running version.
- Do not treat the discovery cache as instantaneous state; clients must still handle connection errors and endpoints that just lost serving capacity.

## 15. Summary

Readiness indicates whether a Pod should receive traffic. Kubelet evaluates readiness probes and readiness gates, and then the EndpointSlice controller updates the Service's endpoint list. EndpointSlices store addresses along with `ready`, `serving`, and `terminating` conditions; the legacy Endpoints resource may still be used by compatibility tools.

Spring Cloud Kubernetes Discovery can read Services and endpoint lists from the Kubernetes API to supply instances to DiscoveryClient and LoadBalancer. Distinguish calling via ClusterIP from client-side discovery, and verify that the provider filters unready endpoints as expected. When investigating, trace from Pod readiness, Service selector, EndpointSlice, and RBAC to DiscoveryClient and LoadBalancer to pinpoint where the endpoint list is missing or stale.

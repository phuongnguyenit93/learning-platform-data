# Analyzing Probes Succeeding While the Application Receives No Requests

## 1. What Does a Successful Probe Prove?

A successful probe only proves **the configured check succeeded at the moment it ran**. It does not automatically prove that every user request traverses the entire system.

In a Spring Boot deployment on Kubernetes, the two paths are usually different:

```text
Probe path:
kubelet -> Pod IP -> probe port and path

Serving path:
user -> DNS / load balancer -> Ingress or Gateway
     -> Service -> Pod endpoint -> application port
     -> filters -> controller -> business logic
```

Under standard HTTP probe configuration, kubelet calls the Pod IP with the declared port and path. It does not automatically pass through Service or Ingress. The `httpGet.host` field can change the connection target; its default is the Pod IP. See [HTTPGetAction in the Kubernetes API](https://kubernetes.io/docs/reference/kubernetes-api/core/pod-v1/#HTTPGetAction).

Therefore, saying "probes are green yet no requests arrive" is not yet a root cause. You must determine:

- Which probe succeeded: liveness, readiness, or startup?
- Which exact process, port, path, and protocol did it call?
- Does "receiving no requests" mean no connections, not entering the controller, or arriving yet failing to finish?
- On which Pod, at what timestamp, and on which deployed version was success observed?

This lesson uses **Spring Boot 3.3.x** properties and a Kubernetes model where a Service selects Pods by label. Configuration snippets are fragments for an existing application, not a complete Java project or deployment manifest bundle.

## 2. Do Not Equate the Three Probe Types

| Probe | Main question | Effect to distinguish |
| --- | --- | --- |
| Liveness | Is the process in a state that requires restarting to recover? | Upon reaching failure threshold, kubelet may restart the container |
| Readiness | Is the container ready to serve traffic? | Contributes to Pod readiness and routing traffic to the Pod |
| Startup | Has the application finished starting up? | When configured, delays liveness/readiness until startup succeeds |

These roles are described in the [Kubernetes probes documentation](https://kubernetes.io/docs/concepts/workloads/pods/probes/). Passing liveness does not replace readiness; passing startup does not test the full user request path either.

An HTTP probe evaluates success based on response codes between 200 and below 400, along with redirect handling rules. It does not interpret business JSON on its own. With Actuator, ensure unready states map to an appropriate error code rather than relying on a JSON field that looks right. See [Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Some reasoning examples:

- `/actuator/health/liveness` returns 200: the process passed the liveness check; this does not confirm the Pod is selected by the Service.
- `/actuator/health/readiness` returns 200: the readiness group passed its check; this does not confirm Ingress routes properly.
- A TCP probe opens a connection: this does not confirm HTTP responds on the right path or business logic works.
- An exec probe calling `localhost` succeeds: this does not confirm a source outside the Pod can reach the same resource.

If redirects or `ProbeWarning` appear, inspect the redirect target and events. Do not use a `curl` run with different redirect-following options as proof that kubelet checked the exact same resource.

## 3. Typical Cause: The Probe Only Checks the Management Port

Consider `application.yml`:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
```

The application serves APIs on 8080, while Actuator uses 8081. The container snippet below is a probe configuration with a narrow check scope:

```yaml
ports:
  - name: http
    containerPort: 8080
  - name: management
    containerPort: 8081

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: management
    scheme: HTTP
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
```

Kubelet is checking 8081. If port 8080 stops accepting new connections or request-handling infrastructure on that port has issues, 8081 can still answer probes.

Spring Boot notes that a separate management context can use different web infrastructure from the main port, including ports, connection pools, and framework components. Consequently, probe results there may not reflect the main server's ability to serve traffic. See [Kubernetes Probes in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

This is a **hypothesis to verify**, not the default conclusion for every incident. Useful evidence comes from a side-by-side comparison:

| Call target | Question tested |
| --- | --- |
| Port 8081, readiness | Are the management infrastructure and readiness group responding? |
| Port 8080, probe on main port | Can the serving server handle a health check request? |
| Port 8080, failing API | Are the API route and related processing steps working? |

You do not need to break the management port to prove the main port has a problem. You only need to show the two requests traverse different infrastructure and yield different outcomes.

## 4. Exposing Probes on the Main Serving Port

With Spring Boot 3.3, you can add probe paths on the main server using `management.endpoint.health.probes.add-additional-paths`.

Replace the application config in section 3 with:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

In this example using the root context path and no custom mappings, port 8080 gains `/livez` and `/readyz`. Port 8081 keeps the corresponding Actuator health paths.

Afterwards, you **must update the probe configuration itself** to the main port. Enabling the property while leaving probes pointed at 8081 does not change the check path.

Configuration snippet inside the Pod template container:

```yaml
ports:
  - name: http
    containerPort: 8080
  - name: management
    containerPort: 8081

readinessProbe:
  httpGet:
    path: /readyz
    port: http
    scheme: HTTP
  periodSeconds: 5
  timeoutSeconds: 2
  successThreshold: 1
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /livez
    port: http
    scheme: HTTP
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
```

The thresholds above are illustrative values and should be chosen based on actual response times and startup characteristics. If the application takes a long time to start, consider a startup probe; do not arbitrarily raise liveness thresholds to mask post-startup issues.

Three points to verify when applying this:

1. **Declaring a port does not make Java listen on it.** `containerPort: 8080` is manifest metadata; the process must actually bind and serve on that port.
2. **The path must match the running application.** If there is a context path, custom additional path, TLS, or security layer, verify the real URL instead of copying the example verbatim. Port and base path rules are explained in [Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).
3. **Probes on the main port still do not test the entire system.** They bind tighter to the serving server, but do not automatically test public DNS, Service, Ingress, or all business dependencies.

Keep check endpoints fast, bounded by finite timeouts, and clearly meaningful. An endpoint that always returns 200 regardless of actual state provides no useful readiness signal.

## 5. Probes Are Right, Yet Service Sends Traffic Elsewhere

Suppose the Pod template of Deployment `orders` has labels:

```yaml
metadata:
  labels:
    app: orders
```

These are labels on the **Pod template**, not merely labels on the outer Deployment object.

Corresponding Service in namespace `learning`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: learning
spec:
  selector:
    app: orders
  ports:
    - name: http
      port: 80
      targetPort: http
```

Here:

- `port: 80` is the port the Service listens on.
- `targetPort: http` references the Pod's port named `http`, which is 8080 in the example.
- The selector must match the Pods intended to serve traffic.

Kubernetes lets a Service map an incoming port to a different target port or use a port name. See [Service port definitions](https://kubernetes.io/docs/concepts/services-networking/service/#port-definitions).

One possible mistake is a Service using:

```yaml
ports:
  - name: http
    port: 80
    targetPort: management
```

In that case, probes on 8081 can pass and the Service also sends traffic to 8081, while the API requires port 8080. Naming the Service port `http` does not change the meaning of `targetPort`.

Another mistake is a selector matching the wrong version or matching no Pods at all. Probes succeeding on one Pod do not prove the users' Service points to that Pod.

Do not look only at the `Running` column: that is not proof that endpoints are serving the right Service.

## 6. One Container's Readiness Is Not Every Routing Condition

Even when the application container's readiness passes, the Pod can still be not `Ready` due to another container or an unmet readiness gate. Custom readiness gates also participate in the decision; see [Pod readiness](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-readiness).

Next, inspect the EndpointSlice for that Service:

- Is the address of the Pod being analyzed present?
- Is the endpoint port the exact API port?
- What are the `ready`, `serving`, and `terminating` conditions?
- Is the Pod being deleted or rolled over during observation?

Do not apply "never ready means never receives traffic" across every configuration. For example, `publishNotReadyAddresses` affects endpoint publishing; the `ready` condition in EndpointSlice has exceptions when that property is enabled. These conditions are described in [EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/#conditions).

Timing matters too. A successful probe run, Pod status update, and routing-table update are not a single atomic instant. Compare data from close timestamps on the exact same Pod; avoid stitching snapshots from different times into one conclusion.

## 7. Evidence-Based Isolation Procedure

### 7.1. Setting the Context for Commands

The commands below use an illustrative scenario:

- Namespace: `learning`.
- Deployment and Service: `orders`.
- Pod label: `app=orders`.
- Application port: 8080; management port: 8081.
- The application exposes API `GET /api/orders`.

These are diagnostic commands for an environment with those resources; they do not create resources and do not assume every cluster's output looks identical. Substitute the values of the deployment you are inspecting.

### 7.2. Inspecting Actual Configuration and Runtime State

```shell
kubectl -n learning get deployment orders -o yaml
kubectl -n learning get pods -l app=orders -o wide
kubectl -n learning describe pods -l app=orders
kubectl -n learning get service orders -o yaml
kubectl -n learning get endpointslices -l kubernetes.io/service-name=orders -o yaml
```

Read the probe configuration of the running Pod, not only manifest files in source code. Check:

- `httpGet.path`, `port`, `scheme`, headers, and `host` if set.
- Readiness of each container, Pod conditions, and probe events.
- Whether Pod labels match the Service selector.
- Whether the EndpointSlice has the right addresses/ports of the serving Pods.
- Whether multiple replicas or versions are selected together.

If a workload has multiple replicas, do not treat one healthy Pod as representative of all. Failures appearing on only a fraction of requests can point to a heterogeneous backend set.

### 7.3. Comparing the Management Port with the Application Port

A convenient check is port-forwarding to the Deployment:

```shell
kubectl -n learning port-forward deployment/orders 18080:8080 18081:8081
```

Keep this terminal open and call from another terminal:

```shell
curl -i --max-time 3 http://127.0.0.1:18081/actuator/health/readiness
curl -i --max-time 3 http://127.0.0.1:18080/readyz
curl -i --max-time 3 http://127.0.0.1:18080/api/orders
```

On Windows PowerShell, use `curl.exe` if `curl` is an alias. `-i` displays status/headers alongside the body; `--max-time` bounds the test duration.

Interpret results by condition:

| If observed | Initial inference |
| --- | --- |
| Readiness 18081 succeeds, `/readyz` on 18080 times out | Check main port infrastructure and additional-paths config |
| `/readyz` succeeds, API returns error | Main port answers probes; inspect API route and business steps |
| All three succeed, users still see errors | Continue checking Service, Ingress/Gateway, and external path |
| Probe receives 404 | Check path, port, version, and exposure config; do not conclude process is hung |

Port-forwarding to a Deployment picks one Pod. Note which Pod was chosen and repeat when checking other replicas. In particular, **port-forward bypasses the normal path through Service and Ingress**; success here does not confirm the normal network path from kubelet or other clients works.

If `/readyz` has not been enabled yet, a 404 there cannot evaluate the main port's serving ability. First verify the additional-paths config is effective.

### 7.4. Checking Each Hop Along the Serving Path

From a suitable diagnostic vantage point inside the cluster with the required tools, compare in sequence:

```text
Pod IP + application port + API path
Service DNS + Service port + same API path
Ingress/Gateway address + user's exact Host/path
```

Keep relevant factors equivalent: method, path, `Host` header, supplied credentials, and protocol. Do not compare an unauthenticated public GET with an authenticated POST and blame the network path alone.

If direct Pod works while Service does not, prioritize selector, EndpointSlice, targetPort, and Service networking. If Service works while Ingress does not, check backend Service/port, host/path, path rewrite rules, and TLS.

This narrows scope rather than asserting every error code has a single cause. Refer to the official [Debug Services](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/) guide.

### 7.5. Determining Whether Requests Stop Before or After the Controller

"No logs in the controller" does not prove the process received no requests. Requests can be blocked by a security filter, router, or error handler before reaching the controller; or the app may not enable the log category you are searching for.

You can read logs near the test timestamp:

```shell
kubectl -n learning logs -l app=orders --all-containers=true --prefix=true --since=10m --tail=2000 --max-log-requests=10
```

Cross-check access logs, proxy/gateway logs, and request IDs if supported by the system. With many Pods or more than 10 log streams, narrow the query scope appropriately; one command is not guaranteed to capture every log line.

Distinguish at least three situations:

1. Requests never reach the application port.
2. Requests reach HTTP infrastructure but do not enter the controller.
3. The controller runs, yet waits on threads, database connections, or another service.

Each needs a different fix. Increasing probe timeouts does not fix a wrong selector; editing Ingress does not free an exhausted database connection pool.

## 8. Probes on the Main Port Succeed Yet Business Requests Still Fail

A lightweight readiness endpoint can still answer while a business operation fails because:

- The database connection pool is exhausted or queries block.
- A downstream service is unreachable.
- A dedicated business execution thread pool is full.
- The API path is misconfigured or denied by authorization.
- The API requires data or capability that the readiness group does not check.

Do not infer backward from a probe result that all such issues must exist. Inspect active request counts, wait times, thread/connection pool state, and logs for the exact operation.

In Spring Boot, readiness is based on application availability state and can be extended. `ACCEPTING_TRAFFIC` represents application availability state, not a synthetic business transaction re-executed on every probe. See [Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

If a dependency is truly required to serve requests, consider including its check in readiness. The config example below is only valid when contributor `db` actually exists:

```properties
management.endpoint.health.group.readiness.include=readinessState,db
```

Keep `readinessState` if you still want the group to reflect Spring-managed availability state. Also check the HTTP code, cost, and timeout of the indicator. Do not put every external system into liveness: restarting the app will not necessarily restore a shared failing database.

Taking every replica out of service when a shared dependency fails is also an architectural decision, not a formula for every system. Weigh partial-degradation capability and existing fallbacks.

An external synthetic check traversing the real DNS/Ingress/API can supplement evidence about user experience. It serves a different goal from kubelet probes; you do not need to turn every liveness probe into a heavy business transaction.

## 9. Choosing a Fix Based on Evidence

| Key evidence | Appropriate fix direction |
| --- | --- |
| Probe calls only management port while main port stops responding | Add probe on main port and resolve why the main server is blocked |
| Readiness healthy, Service selects wrong labels | Fix selector/labels on the right resource |
| EndpointSlice points to wrong port | Fix targetPort or matching port name |
| App container ready, Pod not Ready | Inspect remaining containers and readiness gates |
| Internal Service works, Ingress path fails | Fix route, backend, Host/path, rewrite, or TLS per logs |
| Request enters controller and stalls | Address resource limits or downstream dependencies on the business path |
| Probe gets 200 from an unintended resource | Fix probe target and verify meaningful response |

Do not point every probe at `/actuator/health`, expose all endpoints, drop security, or raise all thresholds just to make status colors change. Adjusting a probe should make it test real serving conditions and trigger appropriate recovery actions.

## 10. Reasoning Self-Check

**A. Liveness returns 200, yet the Service has no ready endpoints. Is that contradictory?**

No. Liveness does not replace readiness, fix selectors, or guarantee Pod status meets serving conditions.

**B. Actuator 8081 responds fine, API 8080 times out. Has the probe proven port 8080 is healthy?**

No. Inspect the two separate ports and consider adding a probe path on the main port.

**C. `/readyz` on 8080 succeeds, yet users still receive errors from Ingress.**

Continue checking Service/EndpointSlice and Ingress/Gateway. Main-port probes still do not traverse the full external route.

**D. No controller logs, yet the gateway shows 401/403 or 404 responses.**

Check where the request stopped: gateway, filter, or mapping. Lack of controller logs does not mean no requests reached the system.

**E. After enabling `add-additional-paths`, the manifest still probes the `management` port. Has check coverage expanded?**

No. You must update the probe target to the additional path and main port, then verify the running Pod's configuration.

**F. Port-forwarding to a Pod succeeds. Can you conclude all replicas and the Service path work?**

No. That test only confirms the single Pod and forwarding tunnel used. Check the remaining replicas and the real traffic network path.

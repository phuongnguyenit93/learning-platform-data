# Distinguishing Command Completion from True Application Readiness

A pipeline can run a deployment command and receive exit code 0, yet users still cannot reach the application. The command may only confirm that configuration was submitted to the platform, a container was created, or a rollout request was accepted. Afterward, the application still has to load configuration, initialize connections, run migrations, populate data, register with service discovery, and pass checks before receiving traffic.

Therefore, **a successful deployment command does not mean the application is ready to serve**. The pipeline must verify at least three layers: the deployment command or API completed, the platform brought the new version into the desired state, and the application actually satisfies service requirements. For critical systems, you also need to observe errors, latency, and business behavior after traffic starts reaching the new version.

## 1. Distinguishing Post-Deployment States

Several distinct states are often lumped together as "deploy succeeded," even though they describe different things:

| State | What Happened? | What Is Not Yet Proven |
|---|---|---|
| Command completed | The command process finished and returned exit code 0 | Whether the platform finished deploying or the app can serve |
| Deployment accepted | The API or control plane accepted the change request | Whether new replicas are running or receiving traffic |
| Rollout completed | The controller met its configured rollout conditions | Whether real business flows actually work |
| Process started | The application process started | Whether network ports are listening and dependencies are ready |
| Readiness passed | The instance is judged capable of receiving traffic | Whether every feature or every request succeeds |
| Smoke test passed | A representative set of requests succeeded | Whether all load, error, and business cases are correct |
| Operationally healthy | Telemetry and operational metrics are within thresholds | Whether zero risk remains under all conditions |

### Command completion

A shell command typically returns an exit code. Code 0 generally indicates the program considers its operation completed successfully; non-zero indicates an error according to the program's convention. An exit code does not by itself describe the state of the underlying application.

For example:

- kubectl apply returns success when the Kubernetes API accepts the submitted objects.
- An upload command may return success once the file has been uploaded to the registry.
- docker compose up -d may finish after the container startup request has been issued.
- systemctl restart may return success when systemd accepts or completes the restart request, yet the application may still be unable to handle requests.

The exact meaning depends on the specific command and flags used. Always read the tool documentation and never assume exit code 0 always means the entire service is ready.

### Rollout completion

A rollout is the process of introducing a new version into the system according to a deployment strategy. In Kubernetes, the Deployment controller tracks ReplicaSets and Pods to bring the replica count to the desired state. When a rollout reports completion, it means the controller's rollout conditions have been satisfied.

Rollout completion is stronger than merely submitting configuration, yet it still does not guarantee every endpoint, permission, data flow, or business operation works. A Pod may be Ready while a business endpoint still returns errors due to misconfiguration or a dependency in another region.

### Application readiness

Readiness is an instance's ability to accept and process traffic at the time of inspection. An instance can be running yet not ready because it is:

- Loading initial configuration or data.
- Initializing connection pools.
- Finishing migrations or cache warming.
- Unable to reach a required dependency.
- Not yet registered with service discovery.
- Overloaded or lacking sufficient resources to serve.

Readiness must be checked at a layer that accurately reflects serving capability. An open TCP port only proves a process is listening; it does not prove endpoints or business logic are functioning properly.

## 2. Why a Deployment Command Can Succeed While the Application Fails

### Deployment is an asynchronous operation

Many platforms accept a request and then perform the deployment in the background. The submission command finishes quickly, whereas pulling images, creating containers, mounting volumes, assigning IPs, and starting the application can take several minutes.

If the pipeline exits right after the submission command, it may report success before the new version is actually running. You need a rollout wait step or a mechanism to track deployment progress.

### Slow startup processes

A Java application may need time to load classes, initialize its framework, connect to the database, build pools, and populate caches. The container can be in Running state while the application still returns 503 or has not opened its endpoints.

If health checks start too early with overly tight thresholds, the system may mark the application unhealthy or restart it repeatedly. If thresholds are too loose, startup failures are detected late.

### Invalid configuration or secrets

The image may be pulled and the container created successfully, yet the application fails to initialize due to missing environment variables, wrong secrets, wrong endpoints, or missing access permissions. A deployment command does not necessarily validate every runtime configuration.

### Dependencies not yet ready

The application may start but fail to connect to a database, message broker, cache, or identity service. Depending on its design, the application may:

- Fail to start if the dependency is mandatory.
- Start in a not-ready state and wait for the dependency.
- Serve partial functionality in degraded mode.
- Start successfully, but individual requests fail when calling the dependency.

The pipeline needs to know which dependencies are truly mandatory for readiness and which features can operate independently.

### New version runs without receiving traffic

Load balancers, ingress controllers, service discovery, or routing rules may not have updated properly. Pods or processes can be Ready yet receive no routed traffic; conversely, traffic may reach unready instances if health checks are misconfigured.

### Application is ready but business logic still fails

A health endpoint returning 200 only proves that the conditions checked by that endpoint passed. It does not prove login, checkout, order creation, message publishing, or data queries work correctly. You need smoke tests representing critical flows.

## 3. Designing Meaningful Health Endpoints

Applications should expose separate health endpoints or mechanisms for different purposes. A common naming convention:

- /health/live: the process is alive and not in a state requiring restart.
- /health/ready: the instance can receive normal requests.
- /health/startup: initialization has completed.

You do not have to use these exact three URLs. What matters is that each endpoint's contract is clear and properly understood by the deployment platform.

### Liveness: does the process need to be restarted?

Liveness answers whether the process can still make progress or has entered a state unrecoverable without a restart—for example, application deadlock, an unresponsive event loop, or a permanently stuck core component.

Liveness should not depend directly on every external service. If the database temporarily drops connections, failing liveness across all instances can trigger mass restarts. Restarting will not fix a database outage and can add load while the system recovers.

### Readiness: should traffic be sent to this instance?

Readiness answers whether the instance can process requests right now. It can check:

- Application startup is complete.
- Required configuration is loaded.
- Critical connection pools or clients are ready.
- Dependencies required for core serving paths are reachable.
- The instance is not shutting down or draining.

If a dependency only affects a secondary feature, you do not necessarily need to mark the entire instance NotReady. The application can continue serving the remaining functionality and return controlled errors for the affected feature. This decision should follow the service contract and user expectations.

### Startup: has the application finished initializing?

A startup probe is intended for applications with long or variable startup times. It tells the system how long to wait before running regular liveness and readiness checks. While the startup probe has not succeeded, Kubernetes does not run that container's liveness and readiness probes.

A startup probe prevents liveness from killing a valid application that is still initializing. However, if the startup probe never succeeds, the container can still be restarted once it exceeds the failure threshold.

### Comparison Table of the Three Probe Types

| Probe Type | Question | On Failure | Purpose |
|---|---|---|---|
| Startup | Has the application finished starting? | Container may be restarted once threshold is exceeded | Allow extended startup |
| Readiness | Can the instance receive traffic? | Pod is removed from serving endpoints | Control traffic routing |
| Liveness | Is the process still healthy and recoverable? | Container is restarted | Recover stuck processes |

Do not reuse a single endpoint for all three purposes if they carry different semantics. A transient dependency failure may fail readiness without failing liveness.

## 4. Rules for Building Reliable Health Checks

A good health check must be fast, stable, time-bounded, and accurately reflect the state being measured.

### Fast response with timeouts

Probes are called repeatedly. Never let a health endpoint execute heavy queries, scan entire tables, or wait indefinitely on dependencies. Set timeouts on check operations and choose appropriate intervals.

If every health check runs an expensive database query, a large fleet of instances can overload the database. Use managed connections or lightweight, bounded checks, caching status when appropriate.

### Do not expose sensitive information

Health endpoints must not return stack traces, connection strings, tokens, usernames, secret contents, or unnecessary infrastructure details. Usually an overall status and component codes are sufficient.

If a detailed operational diagnostics endpoint requires authentication, separate it from the endpoint accessed by load balancers or kubelets. Never expose a full diagnostics page to the public Internet just to make health checks work.

### Distinguish application failures from probe failures

A health check can fail because:

- The application is genuinely unready.
- The probe targets the wrong path or port.
- A network policy blocks the probe traffic.
- The timeout is too short.
- TLS or authentication is misconfigured.
- The probe runs from a different environment than real requests.

When investigating, inspect both application logs and probe logs. Never automatically raise timeouts or disable checks without identifying the root cause.

### Check from the right perspective

An internal health endpoint may return 200 while external ingress or DNS is broken. Therefore, multiple layers may be needed:

1. Process/container health inside the instance.
2. Instance readiness in the orchestrator.
3. Load balancer or ingress health.
4. External synthetic checks along the user access path.
5. Smoke tests of selected APIs or business flows.

Not every system needs every layer. Choose check points based on boundaries that can fail independently.

## 5. Example Health Endpoint Configuration in a Java Application

With Spring Boot Actuator, an application can expose health endpoints along with readiness/liveness states. Example configuration:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health
~~~

Depending on the Spring Boot version and deployment setup, health groups may be exposed at paths such as /actuator/health/liveness and /actuator/health/readiness. Check your framework version, management port configuration, and actual paths before configuring probes.

A health endpoint can return an overall status:

~~~json
{
  "status": "UP"
}
~~~

This result is only as meaningful as the enabled health indicators and how the framework aggregates them. If readiness excludes a required dependency, status UP does not prove that dependency is working. If every dependency is folded into liveness, transient external outages can trigger unnecessary restarts.

### Separating readiness and liveness by contract

An application can define:

- Liveness UP when the process and core internal components continue making progress.
- Readiness UP when startup is complete, required configuration is valid, and minimal dependencies for serving primary requests are ready.
- Startup UP when initialization has finished.

This is a conceptual classification. Specific implementations can use Spring Boot availability states, health groups, custom indicators, or dedicated endpoints. Avoid running a heavy database query on every liveness request.

## 6. Kubernetes: Deployment, Rollout, and Readiness

Kubernetes provides container probes and controllers that manage rollouts. Example Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: registry.example.com/order-service:2.4.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 36
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

This is an illustrative example; paths must match the application's actual endpoints. The startup probe in the example uses the liveness group to determine when the application has initialized enough to begin checks; a dedicated startup health group can be created if the application has a separate initialization flow. Do not use a health endpoint that aggregates every dependency as a startup probe if that dependency may be temporarily unavailable. The example startup probe allows up to roughly 180 seconds of startup time based on the configured failure threshold and period, excluding scheduling and response latency factors. Choose thresholds based on startup times measured under realistic load.

When the readiness probe fails, the Pod is not marked Ready and is removed from the corresponding serving endpoints. When the liveness probe fails enough consecutive times, kubelet restarts the container according to its restart policy. While the startup probe has not yet succeeded, liveness and readiness probes are not executed.

### Apply command and rollout status

Command to submit the manifest:

~~~bash
kubectl apply -f deployment.yaml
~~~

This command usually returns as soon as the Kubernetes API accepts the update. To wait for the Deployment rollout:

~~~bash
kubectl rollout status deployment/order-service --timeout=180s
~~~

If rollout status returns success, the controller reports that the rollout completed according to Deployment status. Even so, the pipeline should still run smoke tests through the path users will take and observe errors after traffic shifts.

You can inspect Pod and endpoint state:

~~~bash
kubectl get pods -l app=order-service
kubectl get endpointslices -l kubernetes.io/service-name=order-service
kubectl describe deployment order-service
~~~

These commands help investigate workload status and published endpoints. Resource names, selectors, and APIs may differ depending on cluster configuration.

### Readiness does not replace rollout policy

A Deployment can fail to complete its rollout because new Pods are not Ready, image pulls fail, quotas are exhausted, or scheduling fails. Readiness probes control adding Pods to serving endpoints; the rollout controller uses replica status to decide update progression.

If maxUnavailable, maxSurge, or the update strategy is poorly configured, a rollout can reduce capacity or stall. Design replica counts, resources, and update strategies to match load.

## 7. Waiting for Readiness and Running Smoke Tests in CI

A pipeline should include a wait step after submitting a deployment request. Simply waiting a fixed sleep duration is unreliable: fast machines waste time waiting, while slow machines may still not be ready when the sleep expires.

A better approach is polling the health endpoint with a deadline and per-request timeout:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

HEALTH_URL="https://staging.example.com/actuator/health/readiness"
DEADLINE=$((SECONDS + 180))

until curl --fail --silent --show-error --max-time 5 "$HEALTH_URL"; do
  if (( SECONDS >= DEADLINE )); then
    echo "Application did not become ready before the deadline."
    exit 1
  fi
  sleep 5
done

echo "Readiness check passed."
~~~

This example assumes the staging endpoint is reachable from the runner. In real environments, use the appropriate URL, TLS certificates, and authentication mechanism. If the health endpoint returns JSON, inspect the status field as well rather than relying solely on HTTP 2xx.

### Smoke tests after readiness

Once the readiness endpoint passes, run a small set of requests representing critical flows:

~~~bash
curl --fail --silent --show-error \
  --max-time 10 \
  https://staging.example.com/api/version

curl --fail --silent --show-error \
  --max-time 10 \
  https://staging.example.com/api/orders/health-check
~~~

The paths in this example are illustrative only. Real smoke tests should validate response bodies, status codes, headers, or returned data against the API contract. If a request has side effects, use test data, idempotency keys, or an isolated environment to avoid creating real transactions.

A good smoke test should:

- Run fast and reliably.
- Cover a few representative critical flows.
- Cause no irreversible side effects.
- Have clear timeouts and error messages.
- Run through the same ingress, DNS, and authentication path clients use when appropriate.
- Verify the exact newly deployed version.

Smoke tests are not a full regression suite. They are a fast post-deployment verification to catch major breakage before broader rollout.

## 8. Verifying the Exact Newly Deployed Version

An endpoint returning 200 could be answering from an old version, a cache, or another instance. Therefore, confirm the actual serving version:

- An API version endpoint or response header containing commit/build ID.
- The deployed image digest or artifact digest.
- Deployment revision and Pod template image.
- Deployment record from the release system.

Example API response:

~~~json
{
  "service": "order-service",
  "version": "2.4.0",
  "commit": "a1b2c3d4e5f6",
  "buildId": "18452"
}
~~~

Do not expose all internal details on a public Internet endpoint. Use an internal endpoint or header restricted to operational checks. Version data must come from trusted build metadata, not from an uncontrolled arbitrary runtime variable.

For containers, deploying by image digest precisely identifies the content. Tags can be overwritten or moved to a new image; content-addressable immutable digests provide stronger verification.

## 9. Verifying Dependencies and Business Flows

Health endpoints typically check a few technical components. They may not fully validate business flows. After deploying, choose smoke tests that reflect critical risks:

| Application Type | Suggested Smoke Test |
|---|---|
| REST API | Call a read endpoint and validate schema/response |
| Order processing service | Create a test order, read status, and verify state transition |
| Worker/message consumer | Send a test message and confirm processing or ack |
| Payment service | Use a sandbox to verify simulated flows without real transactions |
| Web frontend | Load the page, check assets, and perform a primary action |
| Service with database | Run a safe query or operation against test data |

You do not need to check every dependency in a single health request. If an auxiliary service can fail independently, decide whether the application should operate degraded, reject one feature, or stop accepting all traffic.

### Readiness and dependencies

An important question is which dependencies are required for an instance to be considered Ready. If the application can serve read requests while the message broker is temporarily unavailable, readiness does not necessarily have to flip to NotReady for the whole service. If the database underpins every request, database unavailability may be a mandatory readiness condition.

Design around real serving capability and the service contract rather than putting every dependency into a rigid list. Placing an optional dependency into readiness can take down capacity across the entire system when that dependency fails.

## 10. Post-Deploy Monitoring with Telemetry

Readiness and smoke tests are immediate signals. Once the new version receives traffic, monitor telemetry to catch issues that appear only under load or real interactions.

Metrics commonly monitored:

- Request success and error rates by HTTP status code.
- Latency p50, p95, and p99.
- Timeout and retry rates.
- Request volume, throughput, and queue depth.
- CPU, memory, garbage collection, and restart counts.
- Database connections, pool saturation, and query errors.
- Message lag, dead-letter queues, and consumer errors.
- Business metrics such as transaction or order completion rates.

Compare against the pre-deployment baseline and use an observation window long enough for representative traffic. A low-traffic service may not generate enough data in the first few seconds; in that case, use synthetic tests or extend the verification window per policy.

### Do not look only at Pod status

Pod Ready does not mean users experience zero errors. All Pods can be Ready while:

- Ingress points to the wrong service.
- DNS or TLS certificates fail.
- One API route returns 500.
- A database migration slows down queries.
- The new version has a memory leak that only appears under higher load.
- A message consumer receives messages but processes data incorrectly.

Therefore, combine platform status, health checks, smoke tests, and telemetry from real requests.

## 11. Progressive Delivery: Increasing Traffic Step by Step

For critical services, you do not have to shift all traffic to the new version immediately. You can use:

- **Rolling update:** replaces instances incrementally, preserving part of the old capacity during rollout.
- **Canary:** sends a small percentage of traffic to the new version and increases it gradually if metrics pass.
- **Blue-green:** maintains two environments and shifts traffic after the new environment is verified.
- **Feature flag:** deploys code while enabling new behavior per user group or condition.

A conceptual canary flow:

~~~text
Deploy version N+1
       |
       v
Wait for startup and readiness
       |
       v
Send small traffic share
       |
       v
Run smoke tests + observe SLI
       |
       +---- Within thresholds? ---- No ----> Stop rollout / rollback
       |
      Yes
       |
       v
Increase traffic gradually
       |
       v
Verify full rollout and observe
~~~

Decision thresholds must be grounded in baselines, SLOs, and risk levels. Never increase traffic simply because an endpoint returns 200 if error rates or latency are degrading.

## 12. Timeouts, Retries, and Handling Unreadiness

The pipeline must set deadlines for each step:

| Step | Limit to Define | On Timeout |
|---|---|---|
| Submit deploy request | API or CLI timeout | Determine whether the request was accepted before resending |
| Rollout | Maximum time per strategy | Collect status, events, and logs |
| Readiness | Deadline waiting for instances ready | Do not shift traffic or advance release |
| Smoke test | Per-request and suite timeouts | Record failing requests and halt gate |
| Observation window | Duration to monitor telemetry | Proceed, halt rollout, or roll back per policy |

### Bounded retries

Retries help with transient network errors or endpoints still starting up. However, retries must never turn a persistent failure into a false success. Use a bounded attempt count or finite deadline, reasonable backoff intervals, and log each failure.

If the deploy command can create resources or trigger non-idempotent operations, never re-send blindly after a timeout. First verify whether the previous request was already processed. This avoids triggering duplicate deployments or duplicate migration jobs.

### Do not erase traces when a deploy fails

When readiness fails, preserve:

- Deployment run ID and commit/artifact digest.
- Deployment command and parameters.
- Rollout status, Pod events, and application logs.
- Health check and smoke test results.
- Timestamps for each step.
- Decisions to retry, halt, or roll back.

This information helps distinguish failures caused by the artifact, configuration, infrastructure, or dependencies.

## 13. Rolling Back After Readiness or Smoke Test Failure

If the new version does not become ready or exceeds error thresholds, the system can halt the rollout and revert to the previous version. However, rollback is only safe when data and contracts between versions remain compatible.

### Conceptual rollback procedure

1. Stop increasing traffic or halt the rollout.
2. Identify the version and artifact digest that were active before the change.
3. Redeploy the known-good artifact or switch traffic back to the blue environment.
4. Wait for rollout/endpoint readiness of the previous version.
5. Run smoke tests and observe telemetry.
6. Record the reason, timestamp, and rollback outcome.

In Kubernetes, rollout history and undo can be used if release policy allows:

~~~bash
kubectl rollout history deployment/order-service
kubectl rollout undo deployment/order-service
kubectl rollout status deployment/order-service --timeout=180s
~~~

Undo reverts the workload revision based on Deployment history. It does not automatically roll back database migrations, message schemas, secret rotations, or changes in external services outside the cluster.

### Database migrations need backward compatibility

A new version may add columns or alter schema. If a migration drops an old column immediately, the previous version may fail to run during a rollback. Use the expand-and-contract strategy:

1. Add new structures while existing code continues to work.
2. Deploy the application able to read/write compatibly.
3. Migrate data or traffic in phases.
4. Verify no components still use the old structure.
5. Delete the old structure only in a separate change after the rollback window closes.

Application rollback does not always equal data rollback. For irreversible data changes, you may need a forward fix or restoration from backup following a tested plan.

## 14. Common Design Mistakes

### Checking only the deploy command exit code

The pipeline stops right after the deployment command and reports green even though the application has not started. Add a rollout wait step and readiness verification.

### Using fixed sleeps instead of polling

Sleep does not reflect real state. Use polling with deadlines, timeouts, and clear error messages.

### Using an open TCP port as readiness

An open port does not prove the application can process requests. Use an HTTP health endpoint or protocol-appropriate verification mechanism.

### Using liveness to check all dependencies

A transient dependency outage can restart all instances, worsening the incident. Use liveness only for unrecoverable process states; use readiness to control traffic.

### Health endpoints that always return 200

An endpoint that does not check essential state creates false green signals. Define a readiness contract and update it alongside architectural changes.

### Running smoke tests only on localhost

Localhost may work while ingress, DNS, TLS, authentication, or external routing is broken. Test through a user-representative access path when appropriate.

### Not verifying the exact version

The health endpoint could be responding from an old instance or cache. Cross-check the commit/build ID or artifact digest actually serving traffic.

### Rolling back without considering data

The old version may be incompatible with the new schema. Design compatible migrations and test rollback before releasing.

## 15. Post-Deployment Application Verification Checklist

- [ ] Deployment command exited with the expected exit code.
- [ ] Platform accepted and recorded the intended version.
- [ ] Rollout reached completion within the deadline.
- [ ] New instances passed startup and readiness checks.
- [ ] Liveness probe reflects process recoverability rather than all external services.
- [ ] Readiness includes only conditions genuinely needed to receive traffic.
- [ ] Load balancer, ingress, or service discovery routes traffic to new instances.
- [ ] Smoke tests passed through the appropriate access path.
- [ ] Commit/build ID or artifact digest matches the intended version.
- [ ] Telemetry stays within error, latency, and resource thresholds.
- [ ] Rollout halt and rollback plans are defined.
- [ ] Database migrations and data changes are compatible with the recovery plan.
- [ ] Deployment record stores status, logs, timestamps, and final decision.

Automated deployment is only complete when the pipeline has evidence that the new version has entered a serving state per policy. Exit code 0 indicates the command reported success; rollout status indicates the platform met update conditions; readiness and smoke tests verify the application from a serving perspective; and telemetry shows whether the version stays stable under live traffic. Combining these verification layers prevents pipelines from declaring victory too early and provides clear grounds to halt or roll back when the application is not truly ready.

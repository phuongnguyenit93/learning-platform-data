# Placing a Group of Machines Behind a Load Balancer and Testing Health Checks

An application running across multiple virtual machines achieves availability only when traffic is distributed to machines capable of serving requests. A load balancer sits in front of a backend group, accepts client connections, and forwards requests to an appropriate backend. Health checks enable the load balancer to recognize which backends are functioning, which must temporarily stop receiving traffic, and when a machine can return to the serving pool.

In this lab, you will prepare a group of backend machines, create a backend pool/target group, attach the pool to a load balancer listener, configure health checks, and test healthy/unhealthy states. You will also inspect firewalls, traffic draining, logging, and how to troubleshoot when health checks fail even though the application is running.

This lesson belongs to the **CLOUD_CORE_SERVICES_COMPUTE** module, **Deployment and Operations Labs** chapter. The focus is the workflow for placing a group of VMs/instances behind a load balancer and validating behavior through practical tests. Resource names and configuration screens differ across AWS, Azure, Google Cloud, and other platforms; this lab uses general concepts accompanied by Linux and HTTP command examples applicable across environments.

## 1. Objectives and Expected Outcomes

After this lab, you will be able to:

- Explain the relationship between load balancer, listener, backend pool/target group, and health checks.
- Prepare at least two backend machines running identical applications and health endpoints.
- Register backends into a pool and configure a listener to forward traffic to the pool.
- Select appropriate protocol, port, path, interval, timeout, and healthy/unhealthy thresholds.
- Verify backend health from both the load balancer's perspective and the client's perspective.
- Introduce controlled failures to confirm an unhealthy backend is removed from serving traffic.
- Recover the backend and confirm the machine returns to the pool.
- Perform draining before stopping or updating a backend.
- Inspect logs and metrics to diagnose why probes fail.

Expected outcomes: clients access a stable frontend address; the load balancer distributes requests across multiple healthy backends; when one backend fails, new requests continue to be served by the remaining healthy backend; after recovery, the backend returns to a healthy state.

## 2. Lab Architecture

The model consists of a load balancer and two backends in the same network or properly routed networks. Clients access only the load balancer frontend. Backends receive application traffic from the load balancer and health probes from the platform-defined probe sources.

~~~mermaid
flowchart LR
    C["Client"] -->|HTTP/HTTPS| LB["Load balancer"]
    LB --> L["Listener :80 or :443"]
    L --> P["Backend pool / target group"]
    P --> B1["Backend VM 1"]
    P --> B2["Backend VM 2"]
    LB -. "Health probe" .-> B1
    LB -. "Health probe" .-> B2
    B1 --> APP1["Application + /health"]
    B2 --> APP2["Application + /health"]
~~~

Components:

| Component | Role |
|---|---|
| Frontend | IP address or DNS name accessed by clients |
| Listener | Accepts connections on a protocol/port and applies rules |
| Rule | Selects a backend pool by host, path, or default rule |
| Backend pool/target group | List of VMs, IPs, or endpoints receiving traffic |
| Health probe | Sends periodic requests to evaluate backend status |
| Backend application | Processes requests and returns responses |
| Security group/firewall | Restricts clients, load balancer, and probes permitted to connect |

Whether it is called target group, backend pool, backend set, or server pool depends on the provider. In this lesson, the terms backend pool and target group both refer to the destination group receiving traffic.

## 3. Request Flow and Health Check Flow

These two flows are related but distinct:

1. The client opens a connection to the frontend.
2. The listener receives the connection and applies rules.
3. The load balancer picks a healthy backend according to its distribution algorithm.
4. The backend processes the request and returns the response through the load balancer.
5. Independently of client requests, health probes send periodic requests to each backend.
6. Probe results update the backend's state in the pool.
7. A backend failing to meet thresholds is marked unhealthy and stops receiving new requests per service behavior.

~~~mermaid
sequenceDiagram
    participant Client
    participant LB as Load Balancer
    participant VM1 as Backend VM 1
    participant VM2 as Backend VM 2
    Client->>LB: GET /
    LB->>VM1: Forward request
    VM1-->>LB: 200 OK
    LB-->>Client: 200 OK
    LB->>VM1: GET /health
    VM1-->>LB: 200 healthy
    LB->>VM2: GET /health
    VM2-->>LB: 200 healthy
~~~

Do not conclude a backend is healthy simply because the home page returns 200 on a single request. Health checks are repeated measurements with timeouts and thresholds; pool status reflects results according to probe configuration and provider mechanics.

## 4. Preparing the Environment

The lab requires:

- A virtual network/VPC/VNet with subnets for the load balancer and backends.
- Two Linux VMs accessible via SSH or administrative tools.
- A Layer 7 load balancer for HTTP/HTTPS, or Layer 4 if the application requires TCP.
- Permissions to create listeners, backend pools/target groups, and health probes.
- Permissions to modify security groups/network security groups/firewalls.
- A client that can reach the frontend and run curl.

Use recognizable names:

| Resource | Lab name |
|---|---|
| Load balancer | lb-compute-lab |
| Backend pool | pool-app-lab |
| Backend 1 | app-vm-01 |
| Backend 2 | app-vm-02 |
| Listener | listener-http |
| Health endpoint | /health |

Do not use example IP addresses or resource names as actual values unless provisioned in your environment. Record each backend's private IP and the frontend DNS/IP after creating resources.

### 4.1. Checking Networking Before Configuration

Confirm:

- Backends reside in a subnet/VPC/VNet reachable by the load balancer.
- Route tables have valid paths.
- Network ACLs or firewalls do not block traffic between the load balancer and backends.
- Backends can resolve DNS or reach dependencies required by the health endpoint.
- Clients have a path to the frontend.
- Backends do not use public IPs if the architecture does not require them.

If the load balancer is internal, clients must be on a network with a route to the frontend. If it is internet-facing, only the frontend should be public; backends should remain in private subnets where appropriate.

## 5. Preparing Two Uniform Backends

Both machines must run the same application, same version, and same endpoint contract. If app-vm-01 returns a different response from app-vm-02, load distribution tests become hard to interpret.

The example below uses Nginx on Ubuntu/Debian to create a simple HTTP backend. On both machines:

~~~bash
sudo apt-get update
sudo apt-get install -y nginx
sudo systemctl enable --now nginx
~~~

On the first backend, create identifying content:

~~~bash
echo "served-by=app-vm-01" | sudo tee /var/www/html/index.html
echo "healthy" | sudo tee /var/www/html/health
sudo systemctl status nginx --no-pager
~~~

On the second backend, change only the node name:

~~~bash
echo "served-by=app-vm-02" | sudo tee /var/www/html/index.html
echo "healthy" | sudo tee /var/www/html/health
sudo systemctl status nginx --no-pager
~~~

Verify directly on each machine:

~~~bash
curl -i http://127.0.0.1/
curl -i http://127.0.0.1/health
~~~

Expected result: the home page returns HTTP 200 with the respective node name; `/health` returns HTTP 200 with body `healthy`. If the service is not running, inspect logs:

~~~bash
sudo journalctl -u nginx -n 50 --no-pager
sudo tail -n 50 /var/log/nginx/error.log
~~~

In real applications, the `/health` endpoint must be implemented in the application server or reverse proxy according to the readiness contract. Static files are suitable only for basic network lab steps; they do not prove the application, database, or dependencies are ready.

## 6. Designing the Health Endpoint

A health endpoint is a lightweight interface for another component to inspect the application's ability to serve traffic. It should be fast, stable, require no interactive login, and return no sensitive information.

Common endpoint types:

| Endpoint | Purpose | What it checks |
|---|---|---|
| /health/live | Process is alive | Event loop/process is not hung |
| /health/ready | Can accept traffic | App is initialized and mandatory dependencies are ready |
| /health | Simple endpoint for load balancer | Serving status per chosen contract |
| /metrics | Collect metrics | Should not be used as a normal health probe |

For VMs behind a load balancer, a readiness endpoint is generally more appropriate than liveness because the question to answer is whether the machine can serve new requests. If the application starts slowly, a startup probe or grace period may be needed to avoid removing the machine during valid initialization.

### 6.1. Readiness Differs from Liveness

- **Liveness:** Is the process still alive and capable of continuing to run?
- **Readiness:** Is the application ready to receive requests?
- **Startup:** Has the application finished its startup phase?

Load balancers usually need readiness. Using liveness as the probe can route traffic too early to a live process that has not yet loaded configuration or connected to its database.

### 6.2. Dependency Checks

Include a dependency in readiness only if lacking that dependency genuinely prevents serving requests. For example:

- Primary database is unreachable and every request requires the database: readiness should fail.
- Auxiliary analytics service is temporarily down while primary requests still work: do not necessarily mark the entire backend unhealthy.
- A node depends on a cache that has a fallback: readiness should reflect actual serving capability, not merely cache state.

If all backends simultaneously mark themselves unhealthy because of a shared dependency, the load balancer may have no healthy targets left. Consider how the provider behaves when all targets are unhealthy and design probes to avoid taking down the entire fleet due to a non-essential dependency.

### 6.3. Response Contract

Clearly define:

- Success HTTP status code, usually 200.
- Maximum timeout to complete a probe.
- Whether the response body is inspected or only the status code.
- Whether redirects are accepted.
- Whether the endpoint supports the exact HTTP method sent by the probe.
- Any Host header, TLS, and virtual host requirements.

Do not return 200 for every path. The health endpoint must reflect meaningful state; a generic error page must never be mistaken for healthy.

## 7. Creating the Backend Pool and Registering Machines

A backend pool stores the list of targets to which the listener can forward requests. Depending on the service, members may be declared by instance ID, NIC, private IP, hostname, or an instance group/scale set. Choose a member type compatible with the load balancer type and network.

General workflow:

1. Create the backend pool/target group.
2. Select the backend protocol (HTTP or HTTPS) and application port (e.g., 80).
3. Choose the appropriate target type: instance, IP, or group.
4. Register the private IPs or instances of app-vm-01 and app-vm-02.
5. Confirm both machines appear in the backend list.
6. Configure the listener/rule to forward requests to the pool.

### 7.1. Choosing Ports and Protocols

Frontend and backend do not have to use the same port. For example, clients connect over HTTPS on 443, the load balancer terminates TLS, and forwards HTTP to backend port 80. If end-to-end encryption is required, use HTTPS between the load balancer and backends, managing certificates and appropriate hostname verification.

| Hop | Example | Notes |
|---|---|---|
| Client → frontend | HTTPS 443 | TLS certificate attached to listener |
| Load balancer → backend | HTTP 80 | TLS termination at load balancer |
| Health probe → backend | HTTP 80, /health | Probe uses configured port/path |

Do not open backend ports to the Internet just to make health checks work. Probes typically originate from the load balancer infrastructure or provider-published probe ranges.

### 7.2. Registering via Instance Group or Autoscaling Group

If backends are managed by an instance group, VM scale set, or autoscaling group, prefer integrating the pool with the machine group when supported by the platform. New members are registered automatically and terminated members are removed from the pool.

If registering individual IPs manually, you must update the pool whenever a VM changes addresses or gets replaced. This manual process easily creates stale targets and misses new machines during scale-out.

### 7.3. Load Distribution

Common algorithms:

- Round robin: selects backends sequentially in turn.
- Least connections: prefers backends with fewer active open connections.
- Weighted distribution: distributes according to capacity weights.
- Consistent hashing: keeps requests with the same key on the same backend, useful for certain session affinity patterns.

Session persistence/stickiness can keep a client pinned to one backend for a period of time. It affects how load distribution is observed; repeated requests from one client will not necessarily alternate across nodes. When testing round robin, disable stickiness if permitted by policy and the application.

## 8. Configuring Listeners and Rules

A listener receives traffic at the frontend according to protocol and port. Rules determine which pool receives the traffic. For a simple application, use a default rule forwarding all requests to pool-app-lab.

Verify:

- Frontend IP/DNS is provisioned.
- Listener is in enabled state.
- Frontend protocol/port matches clients.
- Certificate is valid if using HTTPS.
- Default action points to the right backend pool.
- Host/path rules do not accidentally route requests to another pool.
- Backend protocol/port matches the listening service.

With Layer 7, you can route by host or path—such as `/api` to the API pool and `/static` to the web pool. With Layer 4, the load balancer typically distributes TCP/UDP connections without inspecting HTTP paths.

## 9. Configuring Health Probes

Probes should simulate closely enough the minimum conditions for a backend to serve real requests, without becoming too heavy or dependent on non-essential services.

### 9.1. Key Parameters

| Parameter | Meaning | How to choose |
|---|---|---|
| Protocol | HTTP, HTTPS, or TCP | Match backend protocol and check method |
| Port | Port the probe connects to | Use application port or dedicated health port |
| Path | HTTP path | E.g., `/health` or `/health/ready` |
| Interval | Time between probes | Balance failure detection speed and probe overhead |
| Timeout | Wait time for one probe | Larger than normal response time, smaller than interval |
| Healthy threshold | Consecutive successes needed to recover | Avoid flapping when app just started |
| Unhealthy threshold | Consecutive failures needed to mark unhealthy | Balance removal speed and false positives |
| Success codes | HTTP statuses considered successful | Usually just 200 or a defined code range |
| Grace period | Wait time after startup | For apps needing warm-up |

Exact values depend on the load balancer. Do not copy one parameter set blindly across all applications; base them on startup duration, normal latency, SLAs, and provider behavior.

### 9.2. Lab Configuration Example

| Attribute | Illustrative value |
|---|---|
| Protocol | HTTP |
| Port | 80 |
| Path | /health |
| Interval | 10 seconds |
| Timeout | 3 seconds |
| Unhealthy threshold | 3 consecutive times |
| Healthy threshold | 2 consecutive times |
| Success code | 200 |

With a 10-second interval and unhealthy threshold of 3, failure detection time is not always exactly 30 seconds. Timing relative to the next probe, timeouts, how the provider counts thresholds, and the number of concurrent health checkers all influence actual detection time.

### 9.3. HTTP Probe vs. TCP Probe

- A TCP probe only confirms a connection can be established to the port; it does not prove the HTTP handler or application returns valid results.
- An HTTP probe confirms the endpoint responds matching the configured status/path.
- An HTTPS probe checks both TLS and HTTP paths; certificates, SNI, or trust chains can cause probes to fail if misconfigured.

When you need to verify the application can serve requests, an HTTP readiness probe is usually far more meaningful than a TCP port check. For non-HTTP protocols, a TCP probe may be appropriate.

## 10. Configuring Firewalls and Security Groups

A backend may run the application normally yet still be marked unhealthy if probes cannot reach the port. This is a common issue when moving from localhost testing to load balancer testing.

Design rules to allow only necessary sources:

| Destination | Source | Port | Purpose |
|---|---|---|---|
| Frontend load balancer | Permitted clients/networks | 80/443 | Application requests |
| Backend VM | Load balancer security group/subnet or probe ranges | 80 | Application traffic and health probes |
| Backend VM | Bastion/management network | 22 | Administrative SSH if needed |

If the provider supports security group references, prefer specifying the load balancer's security group as the source. If health probes originate from dedicated IP ranges, add the exact provider-published probe ranges. Do not open ports 80/443 to the entire Internet on backends.

### 10.1. Checking the Listening Service

On each backend:

~~~bash
sudo ss -lntp
sudo systemctl is-active nginx
curl -i http://127.0.0.1/health
~~~

Confirm Nginx is listening on an interface reachable by the load balancer, not only loopback. Check both OS firewalls like `ufw`/`firewalld` and cloud security groups; either layer can block connections.

### 10.2. Testing from Another Machine in the Same Network

From a test VM with a route to the backend:

~~~bash
curl -i --connect-timeout 3 http://BACKEND_PRIVATE_IP/health
~~~

Replace `BACKEND_PRIVATE_IP` with the actual private IP. If curl from a machine in the same network cannot connect, resolve routing/firewall/service issues before investigating load balancer configuration.

### 10.3. Health Probes May Have Separate Sources

Some platforms send probes from load balancer nodes/instances, while others use dedicated probe IP ranges or service tags. Do not assume probe source IPs equal client request source IPs. Check provider documentation and firewall logs to identify the actual source.

## 11. Attaching the Backend Pool to the Listener

After creating the backend pool and probe:

1. Open the load balancer's listener configuration.
2. Select the HTTP/HTTPS listener clients will access.
3. Set the default action or routing rule to forward to `pool-app-lab`.
4. Confirm the backend protocol/port is HTTP:80 in this example.
5. Save the configuration and wait for the provider to apply it.
6. Open the pool's backend health/target health view.
7. Confirm `app-vm-01` and `app-vm-02` transition to healthy.

If the pool has no healthy backends, some load balancers return gateway/service unavailable errors; others may have fail-open behavior or still attempt routing to unhealthy targets depending on product and configuration. Check actual behavior; do not treat seeing a request hit an unhealthy backend as proof that probes are broken.

### 11.1. Common States

| State | Common meaning | Action |
|---|---|---|
| Initial/Unknown | Not enough probe attempts yet or no result yet | Wait for probes and inspect events |
| Healthy | Meets success criteria | Eligible to receive traffic |
| Unhealthy | Probes failed past threshold | Check reason, port, path, app, and firewall |
| Draining | Finishing existing connections | Wait for connection drain to complete |
| Unused/Not in service | Not attached to a listener/rule or not active | Check pool-listener association |

Exact status names and semantics vary across providers.

## 12. Testing Load Distribution via the Frontend

Begin only after both backends are healthy. From a client with a route to the frontend:

~~~bash
curl -i http://LOAD_BALANCER_DNS_OR_IP/
~~~

Repeat multiple requests to observe which backend is chosen:

~~~bash
for i in {1..20}; do
  curl -s http://LOAD_BALANCER_DNS_OR_IP/
done
~~~

Replace `LOAD_BALANCER_DNS_OR_IP` with the actual frontend DNS or IP. With round robin and session stickiness disabled, results typically show both `app-vm-01` and `app-vm-02`. Do not expect an exact 50/50 split because connection reuse, algorithms, health state, weights, and concurrent traffic can skew distribution.

### 12.1. Checking Responses and Logs

- Client responses must be HTTP 200.
- The response body should indicate which backend handled the request.
- Access logs on both machines should show requests when the distribution algorithm permits.
- The health dashboard should continue showing both machines healthy.
- No unexpected 5xx spikes or timeouts.

If only one backend appears, inspect pool membership, weights, stickiness, algorithm, listener rules, and health state before concluding the load balancer is not distributing traffic.

### 12.2. Testing Multiple Connections

HTTP keep-alive can send multiple requests over the same backend connection. To observe backend selection more clearly, open separate connections or use a client that does not reuse connections during testing. Do not rely on a single curl command to evaluate the algorithm.

## 13. Controlled Unhealthy Backend Testing

The goal is to prove the load balancer detects when a backend is no longer ready and stops sending new requests to that machine. Perform this only in a lab environment or an approved testing window.

### 13.1. Breaking the First Backend's Health Endpoint

On `app-vm-01`:

~~~bash
sudo mv /var/www/html/health /var/www/html/health.disabled
curl -i http://127.0.0.1/health
~~~

The direct curl should receive 404. The home page may still return 200; this illustrates that the application page and readiness endpoint can report different outcomes.

Wait for enough failed probes per the configured interval, timeout, and unhealthy threshold. Watch the backend health dashboard or events to confirm `app-vm-01` transitions to unhealthy.

### 13.2. Confirming Traffic Avoids the Failing Backend

From the client, send multiple requests to the frontend:

~~~bash
for i in {1..20}; do
  curl -s http://LOAD_BALANCER_DNS_OR_IP/
done
~~~

In standard configurations, new requests will be sent only to `app-vm-02` once `app-vm-01` is marked unhealthy. Check logs on both machines and pool status to confirm.

### 13.3. Recovering the Backend

On `app-vm-01`:

~~~bash
sudo mv /var/www/html/health.disabled /var/www/html/health
curl -i http://127.0.0.1/health
~~~

Wait for consecutive successful probes matching the healthy threshold. Confirm `app-vm-01` returns to healthy, then send requests through the frontend to verify it receives traffic again.

### 13.4. Testing Process Failure

You can also test by stopping Nginx on one backend:

~~~bash
sudo systemctl stop nginx
~~~

When finished, restart it:

~~~bash
sudo systemctl start nginx
sudo systemctl is-active nginx
~~~

This test disrupts real requests on that backend. Do not run it in production without a maintenance window and sufficient capacity on the remaining backends.

## 14. Testing Thresholds and Failure Detection Time

Health checks are periodic measurements, not instantaneous detection. Measure the time from when the endpoint begins failing until the pool marks it unhealthy, and from when the endpoint recovers until the pool marks it healthy.

Record:

- Timestamp when the failure started.
- Timestamps of individual probes if provided by the platform.
- Timestamp when status switched to unhealthy.
- Number of client requests receiving 5xx/timeouts during the transition window.
- Timestamp when the endpoint recovered.
- Timestamp when the backend switched back to healthy.

### 14.1. Impact of Interval, Timeout, and Threshold

A short interval detects failures faster but generates more probes. Too short a timeout can falsely mark slow backends unhealthy; too long a timeout delays failure detection. A low unhealthy threshold reacts quickly but risks false positives; a higher threshold is more stable but slower to remove failing backends.

For example, with a 10-second interval, 3-second timeout, and threshold of 3, detection time may span several probe cycles plus timeout duration, depending on when the failure occurred relative to the next probe and how the provider counts failures.

### 14.2. Avoiding Health Flapping

Health flapping occurs when a backend repeatedly oscillates between healthy and unhealthy. Causes can include CPU overload, GC pauses, intermittent dependencies, overly tight probe timeouts, or endpoints depending on unstable services.

To reduce flapping:

- Use a large enough threshold to filter transient glitches.
- Base timeouts on normal latency and endpoint p99.
- Keep health endpoints lightweight with minimal dependencies.
- Separate readiness from liveness.
- Monitor CPU, memory, connection pools, and dependency latency.
- Do not raise intervals/thresholds merely to mask persistent application errors.

## 15. Connection Draining and Deregistration

When updating or stopping a backend, stop sending new connections to that machine and give in-flight connections enough time to finish. This mechanism is commonly called connection draining, deregistration delay, or graceful removal.

Workflow:

1. Place the backend into draining state or deregister it from the pool.
2. The load balancer stops selecting that backend for new requests/connections per service behavior.
3. Existing connections are allowed to complete within the drain timeout.
4. Monitor active connections and in-flight requests.
5. Once draining finishes, stop the service or replace the VM.
6. Register the new backend or return the updated backend to the pool.

### 15.1. Choosing a Drain Timeout

The drain timeout must accommodate the longest supported request, upload/download duration, WebSockets, or streaming. Too short a timeout cuts off requests; too long slows down rollouts and holds resources longer.

If the application supports unbounded long-lived requests, bound request durations or implement client reconnect logic. WebSockets/streaming require separate testing because draining behavior differs from short HTTP requests.

### 15.2. Do Not Rely on Health Failure Instead of Draining

Abruptly killing a process causes health probes to fail but can sever active connections. Draining is a proactive step to stop accepting new connections while allowing current connections to finish.

## 16. Rolling Deployment and Autoscaling Integration

When updating an application version, avoid updating all backends simultaneously if availability must be maintained.

A simple rollout:

1. Create or update one new backend.
2. Wait for the service to start and its readiness endpoint to succeed.
3. Register the new backend in the pool.
4. Wait for the backend to become healthy.
5. Shift a portion of traffic or add the backend to the pool per policy.
6. Drain and remove an old backend.
7. Repeat for remaining backends.
8. Inspect error rates, latency, and health states after rollout.

~~~mermaid
flowchart TD
    A["Create or update one backend"] --> B["Start application"]
    B --> C["Local readiness passes"]
    C --> D["Register in backend pool"]
    D --> E["Load balancer marks healthy"]
    E --> F["Serve traffic / observe"]
    F --> G["Drain old backend"]
    G --> H["Deregister and replace"]
    H --> I["Repeat for next backend"]
~~~

### 16.1. Autoscaling Groups

When backends are managed by an autoscaling group or VM scale set:

- New instances should receive traffic only after bootstrapping finishes and readiness passes.
- Scale-in instances should be drained before termination.
- Load balancer health checks can integrate with autoscaling group health states.
- Distinguish EC2/VM instance health from application health.
- Configure grace periods so instances have enough time to boot.

If autoscaling treats a transient probe failure as an unhealthy instance and automatically replaces the machine, it can trigger a terminate/recreate loop. Check the platform's health check type, grace period, and lifecycle hooks.

### 16.2. Do Not Scale Solely on Health State

Health checks tell whether a backend can serve; they do not directly measure load demand. Autoscaling usually relies on CPU, request count, queue depth, latency, or custom application metrics. Combine health state to keep faulty machines out of the pool with capacity metrics to determine the right backend count.

## 17. Securing Health Checks and Backend Traffic

The health endpoint needs enough signal for verification without becoming a leak for internal configuration or dependencies.

Practices:

- Expose probe endpoints only within necessary networks.
- Never return credentials, connection strings, secrets, or stack traces.
- Never allow the endpoint to mutate system state.
- Restrict allowed HTTP methods, typically GET or HEAD depending on the probe.
- Use TLS for backend traffic when end-to-end security is required.
- Manage certificates, trust chains, and hostname validation.
- Allow only exact load balancer/probe sources in firewalls.
- Protect administrative pages and debug endpoints separately.
- Log probes at a moderate level to avoid excessive log volume.

### 17.1. Host Headers and Virtual Hosts

Some HTTP servers select sites based on the Host header. If the probe sends an IP or hostname different from the application's hostname, the server may return 404/421 even when the app is running.

Check whether the probe configuration allows setting a Host header. If not, serve a default virtual host endpoint or design a hostname-independent health route.

### 17.2. Authentication

Health probes typically do not authenticate with user credentials. Do not guard the endpoint behind an OAuth login flow or redirect to a login page. Instead, restrict network sources and return minimal status. If the platform supports custom headers or authenticated probes, manage secrets through dedicated rotation mechanisms.

## 18. Metrics and Operational Observability

Health state shows whether a backend is considered healthy or unhealthy. To understand root causes and impact, combine load balancer, backend, and application metrics.

| Layer | Metrics to monitor |
|---|---|
| Load balancer | Healthy host count, unhealthy host count, request count, 4xx/5xx, target response time |
| Backend | CPU, memory, disk, network, active connections, process status |
| Application | Request rate, error rate, latency p50/p95/p99, queue depth |
| Dependency | Database connections/errors, cache latency, external API failures |
| Deployment | Instance launch time, bootstrap duration, drain duration, rollout status |

### 18.1. Alerting

Set alerts when:

- Healthy backend count falls below the minimum threshold.
- All backends in the pool become unhealthy.
- A backend flaps repeatedly within a short window.
- Target 5xx or latency spikes sharply.
- Request rate concentrates abnormally on a single backend.
- Autoscaling launches machines repeatedly that fail to become healthy.
- Drain timeouts expire frequently.

### 18.2. Correlation

When investigating a failed probe, correlate timestamps across:

- Load balancer health check events.
- Application access/error logs.
- System journal.
- Firewall/security group flow logs.
- CPU/memory/network metrics.
- Deployments or configuration changes.

If the failure timestamp aligns with a rollout, firewall change, or certificate rotation, that is a strong lead to isolate the cause.

## 19. Symptom-Based Troubleshooting

| Symptom | Common cause | How to check |
|---|---|---|
| Backend always unhealthy | Wrong port/path, service stopped, firewall blocking | Curl localhost, curl private IP, inspect probe reason and firewall logs |
| Local health returns 200 but LB reports unhealthy | Route, security group, probe source, Host header, or TLS | Test from same network, flow logs, probe configuration |
| Backend healthy but clients get 502/503 | App errors on real routes, wrong backend protocol, wrong pool/rule | Call app path directly, check target response and listener rules |
| Only one backend receives traffic | Other backend unhealthy, stickiness, weights, or connection reuse | Check target states, algorithm, and session affinity |
| Backend flaps continuously | Low timeout, high load, flaky dependencies | Correlate p99 latency, CPU, dependencies, and thresholds |
| No healthy backends after deploy | Slow bootstrap, health path not ready, short grace period | Check startup logs, readiness, and lifecycle events |
| Backend never returns to healthy | Endpoint not recovered, cached state, wrong probe, or threshold not met | Curl directly, inspect probe history, and wait for healthy threshold |
| Scale-in drops requests | No draining or drain timeout too short | Check deregistration lifecycle and request durations |

### 19.1. Investigation Order

Work from bottom to top to avoid changing multiple layers at once:

1. Is the process/service running?
2. Is the port listening on the right interface?
3. Does the endpoint return the right status code on localhost?
4. Is the endpoint reachable from another VM in the same network?
5. Do firewalls/security groups allow the probe source?
6. Are probe protocol/port/path/Host header accurate?
7. Is the backend registered in the right pool?
8. Is the pool attached to the listener/rule?
9. Are clients hitting the right frontend?

Do not raise thresholds or switch probes to TCP just to turn the dashboard green if the root cause is that the application cannot serve requests.

## 20. Mapping Across Cloud Platforms

Platforms use different names and capabilities. The table below helps map equivalent concepts; when deploying, check features and limits of the specific service in use.

| Concept | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| Layer 7 load balancer | Application Load Balancer | Application Gateway | Application Load Balancer |
| Layer 4 load balancer | Network Load Balancer | Azure Load Balancer | Network Load Balancer |
| Backend pool | Target group | Backend pool | Backend service / instance group |
| Backend membership | EC2 instance, IP, or matching target type | VM/NIC/IP depending on SKU and config | Instance group or NEG |
| Health check | Target group health check | Probe | Health check |
| Listener/rule | Listener and listener rules | Listener and routing rules | Forwarding rule, target proxy, URL map |
| Scale integration | Auto Scaling group | Virtual Machine Scale Sets | Managed instance group |

Not every Layer 4 load balancer inspects HTTP paths. For example, a Network Load Balancer may use TCP health checks instead of an HTTP readiness path depending on target group configuration. Select the service type based on protocol, routing, TLS, source IP preservation, and health check capabilities.

### 20.1. AWS Application Load Balancer

A common setup includes an ALB, HTTP/HTTPS listener, instance- or IP-type target group, and an HTTP health check to `/health`. EC2 instances are registered directly or integrated with an Auto Scaling group.

When verifying, inspect target health reason codes and ensure the EC2 security group permits traffic from the ALB's security group on the application port. If deregistration delay is enabled, test draining duration before terminating instances.

### 20.2. Azure Application Gateway or Load Balancer

Layer 7 Application Gateway uses backend pools, listeners, routing rules, and HTTP/HTTPS health probes. Layer 4 Azure Load Balancer uses backend pools and health probes over supported protocols like TCP, HTTP, or HTTPS depending on SKU/configuration.

Network Security Groups must permit traffic from Application Gateway/health probe service tags per service guidelines. Inspect probe status, backend health, and effective routes.

### 20.3. Google Cloud Load Balancing

Google Cloud Load Balancing uses backend services and health checks, with backends as managed instance groups or network endpoint groups depending on the load balancer type. Firewall rules must allow health check source ranges and proxy-only subnets if required by the architecture.

Check backend service status, health checks, and firewall rules. With some proxy load balancers, backend traffic originates from proxy-only subnets; do not allow only the health check ranges while forgetting the proxy traffic ranges.

## 21. Lab Verification Report

Record configurations and results so subsequent deployments can be compared:

| Field | Value to record |
|---|---|
| Environment | Account/project/subscription and environment |
| Load balancer | Resource ID, service type, frontend DNS/IP |
| Listener | Protocol, port, certificate, and routing rules |
| Backend pool | Name, protocol, port, and target type |
| Backend nodes | Instance IDs, private IPs, zones, and machine types |
| Health check | Protocol, port, path, interval, timeout, thresholds |
| Firewall | Security group/NSG/firewall rules and probe sources |
| Healthy test | Timestamp, backend states, and client responses |
| Failure test | Failure type, start timestamp, unhealthy timestamp |
| Recovery test | Recovery timestamp, healthy timestamp |
| Drain test | Drain timeout, active connections, and outcome |
| Evidence | Screenshots/dashboard, logs, request IDs, and metrics |

### 21.1. Recommended Test Matrix

| Test | Action | Expected result |
|---|---|---|
| T1 - Baseline | Both backends running and health endpoint returns 200 | Both healthy |
| T2 - Traffic | Send multiple requests via frontend | Requests distributed across healthy backends |
| T3 - Probe failure | Make `/health` on VM1 return 404 | VM1 turns unhealthy after threshold |
| T4 - Failover | Continue sending requests while VM1 is unhealthy | VM2 keeps serving new requests |
| T5 - Recovery | Restore `/health` on VM1 | VM1 returns to healthy |
| T6 - Process stop | Stop service on VM1 | Probes fail and VM1 is removed after threshold |
| T7 - Draining | Deregister VM2 during active requests | In-flight requests complete per drain policy |
| T8 - Rollout | Add new backend to pool then remove old backend | Sufficient healthy backends remain per capacity plan |

For each test, record pass/fail and evidence. If outcomes differ from expectations, save probe reasons and timestamps before altering configuration.

## 22. Common Mistakes When Placing Machines Behind a Load Balancer

- Backend listens only on 127.0.0.1 so the load balancer cannot connect.
- Security group allows clients but blocks load balancer/probe sources.
- Probe uses the wrong port or path.
- Endpoint returns 301/302, 401, 403, or 404 while success codes only allow 200.
- Host header does not match the virtual host.
- HTTPS probes fail due to certificates, SNI, or trust chains.
- Health endpoint depends on too many services and marks the whole pool unhealthy when an auxiliary dependency fails.
- Grace period is shorter than actual bootstrap time.
- Session stickiness causes load distribution tests to be misinterpreted.
- Backend pool is not properly attached to the listener/rule.
- VM is terminated before connection draining completes.
- Autoscaling group does not synchronize membership with the backend pool.
- Checking only VM running status without verifying application readiness.
- Increasing thresholds to mask a slow application instead of fixing bottlenecks.

## 23. Lab Completion Checklist

Before finishing, verify:

- [ ] At least two backends run the same application version.
- [ ] Each backend returns HTTP 200 on the health endpoint.
- [ ] Application listens on an interface/port reachable by the load balancer.
- [ ] Backend pool contains the exact instances/IPs and right port.
- [ ] Listener/rules point to the right backend pool.
- [ ] Firewalls permit only required sources, including probes.
- [ ] Both backends are marked healthy by the load balancer.
- [ ] Client accesses the frontend and receives successful responses.
- [ ] Observed requests reaching multiple backends.
- [ ] Triggered a controlled probe failure and verified the backend turned unhealthy.
- [ ] Healthy backend continued serving new requests.
- [ ] Restored the backend and verified it returned to healthy.
- [ ] Tested draining before stopping or replacing a backend.
- [ ] Saved configuration, timestamps, logs, and evidence.
- [ ] Verified no unintended firewall rules or lab resources were left behind.

## 24. Cleaning Up Lab Resources

After saving evidence:

1. Remove or disable listeners/frontends if no longer used.
2. Deregister backends from the pool following draining procedures.
3. Stop and delete lab VMs if they do not need to be retained.
4. Delete target groups/backend pools, health checks, and load balancers when no dependencies remain.
5. Remove temporary security rules and unnecessary public IP addresses.
6. Check for remaining disks, snapshots, logs, and billable IPs.
7. Confirm you do not accidentally delete shared resources or resources belonging to other workloads.

If the lab uses a shared environment, delete only resources with confirmed lab owners/tags. Do not delete shared networks, security groups, or images merely because they were created during the same lab session.

## 25. Key Takeaways

Placing a group of machines behind a load balancer involves preparing uniform backends, creating a backend pool, registering VMs/instances, configuring listeners/rules, and allowing the right network paths. Health checks must test real serving capability via a readiness endpoint, with suitable protocol, port, path, timeout, interval, and thresholds.

Testing does not stop at healthy status. Introduce controlled failures, confirm unhealthy backends stop receiving new requests, observe healthy backends continuing to serve, then recover and verify machines return to the pool. During maintenance, use draining to protect existing connections. Combine health states with metrics, logs, and inventory to detect faults, avoid false positives, and run rolling deployments safely.
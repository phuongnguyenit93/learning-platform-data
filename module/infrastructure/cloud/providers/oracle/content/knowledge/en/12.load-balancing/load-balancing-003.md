# Listeners, Backend Sets, and Backend Servers

In the **Application Load Balancing** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson explains the three components that form a request's path through an OCI Load Balancer: listener, backend set, and backend server. Learners connect load balancing configuration with IAM, compartments, VCN, Compute, monitoring, and deployment workflows for highly available applications.

The running example is an application deployed on two Compute instances in a private network. Users access a single load balancer address; the service picks an application endpoint to handle the request. For the system to work properly, you must configure the connection entry point, distribution group, and traffic-receiving endpoints together.

## 1. Objectives and Scope

After this lesson, learners will be able to:

- Describe the responsibilities and relationships among listeners, backend sets, and backend servers.
- Distinguish the client-facing port, application port, and health check port.
- Create a backend set, add two backends, and attach a listener using the OCI CLI.
- Verify configuration state, health checks, and business requests.
- Establish procedures for adding instances, maintaining an instance, and troubleshooting common configuration issues.

This lesson uses **OCI Load Balancer**, with the **oci lb** command group. OCI Network Load Balancer has its own model and options; do not apply commands or assumptions from this lesson verbatim to that service.

The lab begins with a prepared load balancer and two Compute instances. Building an entire VCN or installing a complete Java application is not a prerequisite for understanding these three components.

## 2. The Three-Component Model

| Component | Question the component answers | Example |
| --- | --- | --- |
| Listener | Where do clients connect, using which protocol and port? | HTTP on port 8088 of the load balancer |
| Backend set | Which group to distribute to, using which policy and health check? | `app_bs` using `ROUND_ROBIN` and HTTP `/ready` |
| Backend server | Which specific endpoint receives connections from the load balancer? | `10.0.2.10:8080` or `10.0.3.10:8080` |

The listener handles incoming traffic on the load balancer's address. The backend set contains the distribution policy, health check, and list of backends. A backend server is identified by the service address and port that the load balancer can connect to. [Source: Listeners](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managinglisteners.htm), [Backend Sets](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendsets.htm), [Backend Servers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendservers.htm).

~~~mermaid
flowchart LR
    Client["Test client in VCN"] -->|"HTTP :8088"| Listener["Listener app_http"]
    Listener -->|"Default backend set"| Set["Backend set app_bs"]
    Set -->|"Select endpoint"| A["Backend A: 10.0.2.10:8080"]
    Set -->|"Select endpoint"| B["Backend B: 10.0.3.10:8080"]
    Check["HTTP health check /ready"] -.-> A
    Check -.-> B
~~~

The diagram shows configuration relationships; it does not mean every request passes through an extra server named "backend set". A backend set is a logical configuration object inside the load balancer.

The two example addresses represent two independent machines. Registering the same machine under multiple addresses does not add capacity or an independent fault domain.

## 3. Listener: The Traffic Entry Point

### Core Configuration

A listener must define:

- A name for management within the load balancer.
- The protocol and port accepting connections.
- The default backend set.
- TLS configuration when accepting secure connections.
- Routing or request-handling configuration if the application requires it.

For example, **app_http** accepts HTTP on port **8088**, then uses **app_bs** as the default group. A listener name is neither a DNS name nor the address of a Compute instance.

The listener port and backend port serve two different sides of the connection. Clients can call HTTPS on 443 while the application only listens on HTTP 8080. You do not need to move the application to port 443 just because clients use that port.

### Default Backend Set and Conditional Routing

A listener has one default backend set. When a routing policy is added, certain requests can be routed to other groups based on conditions, for example:

| Illustrative request | Expected backend set |
| --- | --- |
| Path starts with `/api/` | `api_bs` |
| Path starts with `/assets/` | `assets_bs` |
| Matches no rule | Listener's default group |

OCI evaluates routing rules in order and stops at the first matching rule; unmatched requests go to the default backend set. This is the decision that selects the **group**; the policy inside the group then selects the **server**. [Source: Routing Policies](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/routing-policy_management.htm).

In the basic lab, no routing policy is attached yet so we can observe the default path clearly. When adding rules later, test both matching and non-matching cases.

### Two TLS Legs Requiring Separate Decisions

| Illustrative option | Client → load balancer | Load balancer → backend |
| --- | --- | --- |
| Terminate TLS at load balancer | HTTPS :443 | HTTP :8080 |
| Encrypt both legs | HTTPS :443 | HTTPS :8443 |
| Private network lab in this lesson | HTTP :8088 | HTTP :8080 |

Certificate configuration on the listener handles the client side. To encrypt the backend leg as well, you must configure corresponding SSL settings on the backend set and ensure the application accepts TLS connections. Enabling HTTPS on the listener does not automatically encrypt the downstream leg. [Source: Configuring SSL Handling](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingcertificates.htm).

When deploying HTTPS, verify the domain name, certificate expiration, trust chain, and backend configuration. Do not solve production certificate errors by asking users to disable TLS verification.

## 4. Backend Set: Policy for a Group of Endpoints

### Group-Level Settings

A backend set combines a list of servers with the distribution method and readiness criteria. Options such as SSL to backends and session persistence can also be set at this level. A backend set can be associated with one or more listeners in an OCI Load Balancer. [Source: Backend Sets for Load Balancers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendsets.htm).

For example, an **orders_bs** group for the ordering service can have a different health check and policy than **reports_bs** serving long-running reports. Separating groups by operational needs prevents a health check change from affecting all services.

Do not split groups merely to label individual servers. The servers in a group should all be capable of serving the requests sent to them by the listener or routing policy.

### Distribution Policies

Three common policies in OCI Load Balancer:

| Config value | Primary meaning | Considerations |
| --- | --- | --- |
| `ROUND_ROBIN` | Sequential distribution across eligible backends, respecting weights | Useful for servers with relatively similar capacity and load |
| `LEAST_CONNECTIONS` | Prefers the backend with fewer active connections | Connection count does not fully represent CPU or request weight |
| `IP_HASH` | Uses the source IP address to keep selecting the same backend while available | Many users behind NAT may share the same source IP |

These policy values are described by Oracle in [configuring policies for Load Balancers](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengconfiguringloadbalancersnetworkloadbalancers-subtopic.htm).

Do not refresh a browser ten times and insist traffic must split strictly 5–5. Connection reuse, session persistence, weights, and backend health all affect what you observe. Evaluate with many controlled requests alongside server-side logs.

### Session Persistence

An application may need requests from the same session to land on the same backend. However, session stickiness does not make data in one server's memory available on another server.

For example, if a shopping cart resides only in backend A's RAM, backend A failing can still lose the cart even if the load balancer shifts requests to B. The architecture must decide where shared state lives or how sessions recover, rather than merely toggling a backend set option.

For distribution testing labs, keep session persistence configuration simple and explicitly record whether it is enabled. When results differ from expectations, check cookies and connections before changing the policy.

## 5. Backend Server: The Endpoint That Actually Serves

### IP and Port Identity

The following backends are three distinct endpoints:

~~~text
10.0.2.10:8080
10.0.2.10:9090
10.0.3.10:8080
~~~

The first two endpoints may be two processes on the same machine. The load balancer needs the exact application port, not just which Compute instance is running.

Within the same VCN, using appropriate private IPs lets the load balancer reach internal services. Network permissions, routes, and firewalls must still allow the path. Adding an address to a backend set does not automatically open a port on the OS. [Source: Backend Servers for Load Balancers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendservers.htm).

If an application binds only to `127.0.0.1`, local requests on the machine may succeed while the load balancer still cannot reach it. Configure the bind address appropriately for the private network and restrict access using network control layers.

### Weight, Drain, Offline, and Backup

| Attribute | Operational meaning |
| --- | --- |
| Weight | Adjusts distribution proportion per policy; not a CPU allocation percentage |
| Drain | Stops new TCP connections and non-sticky HTTP requests to the backend for maintenance |
| Offline | Prevents the load balancer from sending traffic to that backend |
| Backup | Used only when all normal (non-backup) backends fail health checks |

With drain, pay attention to sticky requests and existing connections. Do not treat enabling drain as proof that all work on the server has finished. Backup backends are also incompatible with the `IP_HASH` policy. [Source: Editing a Backend Server](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/update_backend_server.htm).

Backup inside a backend set is a failover role for standby servers within the set; it does not automatically implement cross-region disaster recovery for the application.

A backend with a passing health check may still receive no requests as expected because it is offline, draining, backup, or not in the group the listener is using. Diagnosis must therefore read both health and configuration.

## 6. Health Checks: Measuring True Readiness to Serve

### What Do TCP and HTTP Checks Verify?

A TCP health check verifies the ability to establish a TCP connection. An HTTP health check sends a request to a configured path and validates the response code or body. The result is used to remove backends from and return them to rotation as status changes. [Source: Health Check Policies](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/load_balancer_health_management.htm).

A process can open a port without being ready to serve transactions. Therefore, choose a check appropriate for the service type rather than simply the easiest check to pass.

In the example, each backend exposes:

~~~text
GET /ready
HTTP status: 200 when ready to accept requests
HTTP status other than 200 when intentionally reporting not ready

GET /
Synthetic body containing node name, such as app-a or app-b
~~~

The path **/ready** is a contract of the example application, not an endpoint created automatically by OCI. The application must actually implement that path.

### Three Ports Commonly Confused

| Port role | Value in lab | Where used |
| --- | --- | --- |
| Listener port | 8088 | Clients call the load balancer |
| Backend traffic port | 8080 | Load balancer forwards requests to the application |
| Health check port | 8080 | Service checks `GET /ready` |

Health checks can use a separate port if the architecture requires it, but success on a separate management port does not prove the user-facing port works. When no health check port is specified, the OCI CLI allows using each backend's configured port. [Source: backend-set create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set/create.html).

In this lesson, explicitly set health check port 8080 for easier verification and only include backends sharing that port in the group.

### Choosing Conditions and Sensitivity

Illustrative configuration:

~~~text
protocol = HTTP
port = 8080
path = /ready
expected status = 200
interval = 10000 ms
timeout = 3000 ms
retries = 3
~~~

Interval is the time between checks; timeout limits how long to wait for a response; retries affect when backend status changes. Do not multiply these numbers naively and treat the result as an SLA for application failure detection time. [Source: backend set health check configuration](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendsets_topic-Creating_Backend_Sets.htm).

A readiness endpoint should be cheap to call, have predictable response times, and expose no sensitive data. Avoid using login pages, endpoints that always redirect, or static pages that always return 200 even when the application is broken.

If a health check depends on a shared database, evaluate the scenario where a database outage marks every server unready simultaneously. Deciding which dependencies to check must be based on what requests the application can still serve when a dependency fails.

## 7. Preparing the Lab in OCI

### Resources and Application Contract

Prepare:

- A **private OCI Load Balancer** in the lab VCN, already in active state.
- Two Compute instances with sample private IPs **10.0.2.10** and **10.0.3.10**; replace with real IPs.
- HTTP application listening on port 8080 on both instances.
- Path `/ready` and node-identifying body as described above.
- A test machine with network reachability to the load balancer's private address.
- OCI CLI and an identity authorized in the appropriate compartment.

Do not run commands to recreate a listener or backend set if that name is already used by another application. The examples below use new names in a defined lab environment.

### IAM and Network Permissions Are Two Separate Layers

Example policy granting load balancer management permissions in a dedicated compartment:

~~~text
Allow group Default/LoadBalancerLabOperators to manage load-balancers in compartment LoadBalancingLab
~~~

Substitute domain, group, and compartment for your real environment. If you also need to manage networks, Compute, certificates, or logs, corresponding permissions are required. Granting load balancer permissions does not automatically grant all of those permissions. Oracle provides dedicated authorization examples for managing and updating load balancers in [Common Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm).

For networking, verify the following paths:

| Source → destination | Allowed in lab |
| --- | --- |
| Test machine → load balancer | TCP 8088 |
| Load balancer → two backends | TCP 8080 |
| Health check flow → two backends | TCP 8080 for `/ready` check |
| Return path | Allowed via stateful model or matching return rules |

You can use a load balancer NSG and an application NSG to restrict connections within the VCN. Also check security lists, routes, and OS firewalls; one permissive layer cannot compensate for another layer blocking traffic.

You do not need to open backend port 8080 to the entire Internet for clients to reach it through the listener. With a private load balancer, a machine running the CLI or a browser outside the network does not gain network reachability merely by holding OCI credentials.

## 8. Creating Backend Set, Backends, and Listener with PowerShell

The following commands are lab instructions; replace sample variables before running against OCI. Run them sequentially, waiting for each previous change to finish before submitting dependent changes on the same load balancer.

### Declare Variables

~~~powershell
$Region = 'REPLACE_WITH_REGION'
$LoadBalancerId = 'REPLACE_WITH_LOAD_BALANCER_OCID'
$BackendSetName = 'app_bs'
$ListenerName = 'app_http'
$BackendIps = @('10.0.2.10', '10.0.3.10')
$BackendPort = 8080
$ListenerPort = 8088
~~~

The load balancer OCID and region must belong to the same resource. The backend set name is a name inside the load balancer, not a compartment OCID.

### Create the Backend Set

~~~powershell
$CreateSetArgs = @(
    'lb', 'backend-set', 'create',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--name', $BackendSetName,
    '--policy', 'ROUND_ROBIN',
    '--health-checker-protocol', 'HTTP',
    '--health-checker-port', '8080',
    '--health-checker-url-path', '/ready',
    '--health-checker-return-code', '200',
    '--health-checker-interval-in-ms', '10000',
    '--health-checker-timeout-in-ms', '3000',
    '--health-checker-retries', '3',
    '--wait-for-state', 'SUCCEEDED',
    '--max-wait-seconds', '300'
)
oci @CreateSetArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Backend set creation was not confirmed successful'
}
~~~

The health checker parameters belong to the backend set. At this point the group has no servers receiving traffic; creating the group successfully does not prove the application is ready. [OCI CLI Reference: backend-set create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set/create.html).

### Add Two Backends

~~~powershell
foreach ($BackendIp in $BackendIps) {
    $CreateBackendArgs = @(
        'lb', 'backend', 'create',
        '--region', $Region,
        '--load-balancer-id', $LoadBalancerId,
        '--backend-set-name', $BackendSetName,
        '--ip-address', $BackendIp,
        '--port', "$BackendPort",
        '--weight', '1',
        '--backup', 'false',
        '--drain', 'false',
        '--offline', 'false',
        '--wait-for-state', 'SUCCEEDED',
        '--max-wait-seconds', '300'
    )
    oci @CreateBackendArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Adding backend $BackendIp was not confirmed successful"
    }
}
~~~

Both instances have weight 1 and participate normally in serving when eligible. Adding a backend registers an address and port; it does not start or install the application on Compute. [OCI CLI Reference: backend create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend/create.html).

### Create Listener Linked to the Group

~~~powershell
$CreateListenerArgs = @(
    'lb', 'listener', 'create',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--name', $ListenerName,
    '--protocol', 'HTTP',
    '--port', "$ListenerPort",
    '--default-backend-set-name', $BackendSetName,
    '--wait-for-state', 'SUCCEEDED',
    '--max-wait-seconds', '300'
)
oci @CreateListenerArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Listener creation was not confirmed successful'
}
~~~

The **--default-backend-set-name** field completes the link from the listener to the group. Port 8088 must be allowed on the client-to-load-balancer path. [OCI CLI Reference: listener create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/listener/create.html).

If the CLI times out waiting, check the work request before retrying. A client-side timeout does not prove the OCI operation was canceled; retrying immediately may encounter an already-existing resource or an in-progress change.

### Look Up Work Requests When Needed

Retrieve the operation's work request ID from the CLI output or Console:

~~~powershell
$WorkRequestId = 'REPLACE_WITH_WORK_REQUEST_ID'
$WorkRequestArgs = @(
    'lb', 'work-request', 'get',
    '--region', $Region,
    '--work-request-id', $WorkRequestId
)
oci @WorkRequestArgs
~~~

Only proceed once the related operation has reached the expected completion state. If it failed, inspect the error details before fixing or resubmitting. [OCI CLI Reference: work-request get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/work-request/get.html).

## 9. Verifying Across Three Layers

### Configuration Layer

In the Console, verify:

1. Listener `app_http` has HTTP, port 8088, and default backend set `app_bs`.
2. `app_bs` has the right policy, `/ready` path, and health check port.
3. The backend list contains the exact two `IP:8080` pairs.
4. The weight, backup, drain, and offline flags match the lab intent.

A typo in a group name can leave a listener validly existing while routing traffic to a different group than expected. Verification evidence must explicitly state the group name, not just capture overall load balancer status.

### Backend Health Layer

~~~powershell
$SetHealthArgs = @(
    'lb', 'backend-set-health', 'get',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--backend-set-name', $BackendSetName
)
oci @SetHealthArgs

$BackendHealthArgs = @(
    'lb', 'backend-health', 'get',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--backend-set-name', $BackendSetName,
    '--backend-name', '10.0.2.10:8080'
)
oci @BackendHealthArgs
~~~

Use the group result to identify which backends to investigate, then inspect individual backend details. Check results from both the primary and standby components of the load balancer can contribute to health status; when you see Warning, read the details rather than just calling the application once from one machine. [Backend set health reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set-health/get.html), [backend health details](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/get_backend-server-health.htm).

Do not equate green backend health with clients being able to reach the listener. Those two flows have different sources, ports, and network conditions.

### Application Request Layer

Run from a test machine with a network path to the private load balancer:

~~~powershell
$LoadBalancerAddress = 'REPLACE_WITH_PRIVATE_LOAD_BALANCER_IP'
$ApplicationUri = 'http://{0}:{1}/' -f $LoadBalancerAddress, $ListenerPort

1..20 | ForEach-Object {
    $Response = Invoke-WebRequest -Uri $ApplicationUri -UseBasicParsing
    [pscustomobject]@{
        StatusCode = $Response.StatusCode
        Body = $Response.Content
    }
}
~~~

Cross-check the `app-a`/`app-b` responses against application access logs. This test helps observe distribution; it does not require the two servers to strictly alternate on every call.

With HTTPS and a domain name, test using the exact hostname covered by the certificate. Calling an IP directly while bypassing certificate verification does not replace testing the real user access path.

## 10. Step-by-Step Maintenance of a Backend

Suppose you want to upgrade `app-a` while `app-b` continues serving traffic. First confirm `app-b` is healthy and has sufficient capacity to absorb the remaining load.

### Place the Backend in Drain

In this lab, backend A initially has weight 1 and both backup/offline set to false:

~~~powershell
$DrainArgs = @(
    'lb', 'backend', 'update',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--backend-set-name', $BackendSetName,
    '--backend-name', '10.0.2.10:8080',
    '--weight', '1',
    '--backup', 'false',
    '--offline', 'false',
    '--drain', 'true',
    '--wait-for-state', 'SUCCEEDED',
    '--max-wait-seconds', '300'
)
oci @DrainArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Re-check the drain operation before starting maintenance'
}
~~~

`UpdateBackend` requires passing weight, backup, offline, and drain values. For real resources, read the current configuration and preserve the exact values that should remain unchanged; do not blindly copy lab defaults. You can use ETag and **--if-match** when needed to avoid overwriting concurrent changes. [OCI CLI Reference: backend update](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend/update.html).

### Wait and Deploy

After draining:

1. Observe active connections and in-flight requests on `app-a`.
2. Handle sticky sessions, WebSockets, or long-running tasks according to the application design.
3. Stop the service cleanly once maintenance conditions are met.
4. Upgrade and restart the application.
5. Verify `/ready`, the application version, and a business request.
6. Clear drain via an update operation with verified values.
7. Monitor error rates and latency as the machine resumes taking load.

Do not merely wait an arbitrary number of seconds and shut down the server. Transition criteria must be based on actual application behavior and agreed time limits.

In production, changing the policy of an entire backend set also requires planning: Oracle notes that this operation can disrupt traffic and drop active connections. [Source: Editing a Backend Set](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendsets_topic-Editing_Backend_Sets.htm).

## 11. Troubleshooting Along the Request Path

| Symptom | Suggested inspection order |
| --- | --- |
| Client cannot connect to listener | DNS or IP, private/public visibility, routes, listener ingress, right port |
| Backend health OK but access fails | Listener, default backend set, routing policy, client-to-listener path |
| All backends marked unhealthy | Health check port/path/protocol, application bind address, NSGs, firewalls, and routes |
| Only one backend fails | Process and `/ready` on that server, registered IP/port, subnet network rules |
| Backend OK but receives no requests | Offline, drain, backup, session persistence, policy, and actual selected group |
| Only a specific path fails | Routing rules, match order, and URL contract of receiving service |
| HTTPS fails even though internal HTTP works | Listener certificate, domain name, trust chain; backend SSL if enabled |
| Errors under increased load | Remaining backend capacity, connections, timeouts, and load balancer limits |

Oracle documents cases where health checks are all OK yet the listener cannot pass traffic, as well as cases where security rules block the health check source. You can inspect the health check source address in backend health details for investigation. [Source: Understanding Load Balancer Health Issues](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/understanding_health_issues.htm).

HTTP error codes must be correlated with logs to see which component generated them. Do not assume every 5xx response comes from the load balancer or every timeout is caused by health checks.

A helpful investigation sequence:

~~~text
Client
  → listener address and port
  → listener and routing policy
  → selected backend set
  → backend status and attributes
  → network connectivity to IP:port
  → application and dependencies
~~~

Change only one intentional factor at a time and record timestamps. Widening every security rule at once can mask the real root cause and remove necessary network restrictions.

## 12. Availability Design and Cost Control

Two backends let service continue when one server stops taking requests, provided the remaining server has enough capacity and dependencies remain healthy. Place instances across fault domains appropriate to your region and test single-instance loss scenarios.

You can evaluate standby capacity using this assumption:

~~~text
Load when one instance stops
  must be less than the safe serving capacity
  of the remaining backends eligible to receive traffic
~~~

As a hypothetical example, suppose each machine should handle at most 100 requests/second within the application's latency budget. At a total load of 150 requests/second, two machines can run normally, but one remaining machine cannot meet the target while the other is under maintenance. That is a capacity problem, not a listener bug.

The load balancer also does not automatically synchronize in-memory sessions, local data, or transaction state across servers. For Oracle Database applications, inspect connection pools and behavior when the database dependency fails or slows down.

Regarding cost and operations:

- Size load balancer bandwidth capacity according to traffic metrics and redundancy targets.
- Include Compute, logs, monitoring, and data transfer appropriate to the architecture.
- Separate backend set or listener names when there is a clear routing and operational reason.
- Set appropriate log retention periods while keeping evidence needed for investigations.
- Clean up lab resources once you confirm no dependencies remain.

Do not assume "adding a listener" means "adding another load balancer appliance" or incurring a fixed independent charge. Evaluate cost based on actual resources and current pricing at deployment time.

## 13. Consolidation Lab Exercise

Use the lab environment to complete the following:

1. Diagram the path from client through listener to a specific backend, noting all three ports.
2. Create `app_bs`, register two instances, and attach `app_http`.
3. Save evidence of configuration, health checks, and responses from both nodes.
4. Make `/ready` on one instance return a failing code; observe the status transition and application behavior.
5. Restore the instance, then test drain to compare with intentional maintenance.
6. Change only the default backend set in a test environment that has a second group; explain before and after results.
7. Assess load-handling capacity when only one backend remains.

Deliverables should include the architecture diagram, endpoint list, network/IAM scope, test results, and maintenance runbook. A screenshot of an active load balancer status alone does not substitute for that evidence.

When finished, revert configurations modified for failure testing, identify resources to keep, and clean up only the lab resources you manage.

## 14. Key Takeaways

The listener defines where connections are received and the default group. The backend set defines how to select and health-check a group of servers. A backend server is the specific application address with its port and serving attributes.

When deploying or troubleshooting, follow those exact relationships while checking both network and application layers. A reliable configuration must be proven by requests traversing the right listener, reaching the right group, and receiving valid responses from ready backends.

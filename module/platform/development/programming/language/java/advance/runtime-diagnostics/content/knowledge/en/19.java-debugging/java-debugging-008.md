# 19.8. Securing Debug Ports and Limiting Debugger Usage on Live Serving Processes

## 1. Why Is a Debug Port Sensitive?

For a Java application serving requests, a debugger lets you inspect execution flows, stack frames, variable values, exceptions, and error causes. Yet a debugger connection **is not read-only access**. Through the JVM control interface, anyone with debug access can pause threads, inspect in-memory data, modify values, evaluate expressions, or invoke methods. The impact goes far beyond reading logs and directly affects **data confidentiality, integrity, and availability**.

Commonly involved technologies:

- **JPDA** (*Java Platform Debugger Architecture*) is the architecture encompassing JVM and debugger interfaces.
- **JDWP** (*Java Debug Wire Protocol*) exchanges commands/events between the JVM's debug agent and the debugger program.
- **JDI** (*Java Debug Interface*) is the Java-level API used by many tools/IDEs to drive debug sessions.
- **JVM TI** provides JVM-level capabilities to agents, including those required by debuggers.
- **`dt_socket`** is the mechanism transporting JDWP over a TCP socket; this listener port is what must be protected.

**Default principle:** do not enable JDWP on live serving production processes. If an exception is required for a severe incident, it must be approved, time-bounded, narrowly reachable, actively coordinated by an owner, and have a port-closing plan. The fact that a debugger is convenient for developers **does not** make it safe in multi-user environments.

### Learning Objectives

After this lesson, you will be able to:

1. Explain why JDWP is a sensitive control channel rather than a password-protected HTTP API.
2. Distinguish `address=127.0.0.1:5005`, `address=5005`, and `address=*:5005` on modern JDKs; verify actual bound ports.
3. Understand `server=y`, `suspend=n`, `allow`, firewalls, SSH tunnels, and authorization layers; know the limits of each layer.
4. Assess the impact of breakpoints, `Suspend All`/`Suspend Thread`, stepping, watchpoints, and expression evaluation on a running service.
5. Run a debug session with an owner, scope, time limit, stop criteria, and verified closure.
6. Run a Java 17+ example without exposing debug ports to the network: demonstrate the program still handles requests when unpaused, and recognize risks when pausing threads.
7. Prefer JFR, metrics, traces, logs, or thread dumps whenever they suffice to answer the question without opening JDWP.

**Scope:** securing debug ports and controlling impact when attaching a debugger to a serving JVM. This lesson does not teach exploiting exposed ports or treat accessing processes you do not administer as an exercise.

## 2. Risk Model: All Three Security Properties Can Be Impacted

| Asset | How someone with debugger access can impact it | Scenario |
| --- | --- | --- |
| **Confidentiality** | Inspect objects, local variables, headers, tokens, connections, config values, customer data on heap | An access token variable or SQL string appears in the IDE |
| **Integrity** | Evaluate side-effecting code; modify field values or state per debugger/JVM capabilities | Evaluating a getter that writes cache; altering an order status |
| **Availability** | Pause all threads, pause lock-holding threads, cause timeouts and health-check failures | A breakpoint on a hot request path causes requests to pile up |
| **Investigation reliability** | Debugger alters timing and scheduling, making race conditions vanish or appear | Deadlock/race occurs only outside a debug session |
| **Governance** | Connecting over unaudited paths; attachments/screenshots containing real data | IDE screenshot leaks PII in a ticket |

Standard HotSpot JDWP sockets **do not provide built-in user authentication or TLS encryption like an enterprise admin channel**. There is no username/password field in the JDWP config string acting as account authentication. Therefore, anyone who can connect must be treated as having powerful control over the process. You must rely on **restricted network reachability, OS/infrastructure authorization, and secure transport channels**.

> Keep distinct: `allow=...` on JDWP's socket transport is an **IP/subnet address** filter, not identity authentication or encryption. Having a firewall and private subnet is also insufficient if untrusted workloads/users can reach it from that subnet.

### Difference Between Debug Port and Service Port

~~~text
                     Normal business traffic
Client -----------> :8080 (HTTP/TLS; routed through gateway)
                      |
                      v
                   Java service
                      ^
                      |  JDWP controls the JVM, not a REST endpoint
                      |
                  :5005 (JDWP)
                      ^
                      |
                Authorized debugger only, ideally via localhost
                and a controlled SSH/VPN channel, short-lived session
~~~

Never place `:5005` behind a public LoadBalancer, Ingress, NodePort, or wide-open firewall rule just so an IDE "connects easily." JDWP does not become safe merely because service port `:8080` uses HTTPS.

## 3. JDWP Options on JDK 17/21

Syntax to launch a JVM with the agent:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 MyApplication
~~~

Here `MyApplication` is **the Java class name with `main`**, or replaced with `-jar app.jar` for the corresponding app. This command is an example for **authorized environments**, not a default production config.

| Option | Meaning | Practical rule |
| --- | --- | --- |
| `-agentlib:jdwp` | Loads the JDWP agent into the JVM | Do not load without an approved request |
| `transport=dt_socket` | Uses a TCP socket | Manage the socket as a sensitive port asset |
| `server=y` | JVM **listens** for debugger attaches | Listen only on the strictly required network interface |
| `server=n` | JVM connects **outbound** to a waiting debugger | Not automatically secure; inspect topology, auth, and remote permissions |
| `address=127.0.0.1:5005` | Binds IPv4 loopback, port 5005 | Suits labs/internal ports with controlled access paths |
| `address=5005` | Per JDK 17/21 docs, empty host uses **local loopback** | Writing the host explicitly still makes operator audits easier |
| `address=*:5005` | Binds **all network interfaces** | Never use on production services; high port-exposure risk |
| `suspend=n` | Does not pause VM at startup waiting for debugger | Avoids delaying startup; does not stop breakpoints from pausing later |
| `suspend=y` | `VMStartEvent` suspends entire VM before `main` runs | Easily makes services fail startup/health checks before attaching |
| `allow=IP/subnet` | Restricts permitted source IPs in JDWP socket transport | Defense-in-depth, **not** authentication or TLS |
| `timeout=...` | Attach/connect wait timeout per transport mode | Not a debug session TTL or breakpoint duration limit |

**Crucial version warning:** syntax and default addresses changed across Java versions. JDK 17/21 docs show `address=8000` listening only on loopback; do not blindly apply that rule to JDK 8 or other VMs. Before configuring, check:

~~~bash
java -version
java -agentlib:jdwp=help
~~~

The help command checks JDWP options supported by the current JVM without opening an application debug session. On a running JVM, you must also inspect the actual deployed command line and **real listening ports**, rather than trusting unverified YAML/templates.

### 3.1. Why Does `suspend=n` Still Not Make a Debugger "Non-Intrusive"?

`suspend=n` only describes **VM startup behavior**. Once attached, breakpoints can apply thread-suspend or VM-suspend policies. A flag reading `suspend=n` does not stop someone in an IDE from clicking Pause, adding a breakpoint on a high-traffic function, stepping hundreds of times, or evaluating side-effecting expressions.

Nor is `server=n` inherently safer than `server=y`: with `server=n`, the JVM actively connects to the debugger endpoint; if the remote side is unmanaged or unprotected, whoever receives the connection still holds powerful debug privileges.

### 3.2. Difference Between `allow` and a Firewall

- `allow` is enforced by the JDWP socket transport based on source IP/subnet.
- Firewalls or security groups restrict ingress/egress of hosts/pods/nodes per network policy.
- SSH/VPN/bastions can provide an authenticated, encrypted, and audited transport channel.
- Kubernetes RBAC decides who can perform admin actions like port-forward, yet does not replace permissions inside the JVM itself.
- OS users, pod security contexts, and process permissions affect who can configure, start, stop, or attach admin tools.

None of these layers turn JDWP into a "read-only" role API. Once connected to JDWP, a debugger can exercise full process control. **Defense in depth** means shrinking reachability, documenting who has access, and stopping quickly if anything deviates.

## 4. Choosing an Approach by Risk Level

| Environment | Recommended stance | How to organize |
| --- | --- | --- |
| Personal study machine / isolated test env | Acceptable with basic controls | `127.0.0.1`, temporary port, no real data, close after session |
| Staging close to production | Allowed when authorized | Isolated namespace/network, sanitized data, tight schedule |
| Live serving production | **No JDWP by default** | Prefer metrics/logs/traces/JFR/thread dumps; reproduce on canary |
| Production with severe irreproducible incident | Controlled exception | Incident approval, owner/on-call, bounded time & scope, rollback/cleanup |
| Pod or VM holding highly sensitive data | Avoid direct attach | Isolated replica/canary with minimal data; dedicated security review |

Choose the approach by **diagnostic question**. If you only need to know which threads are waiting on locks, a thread dump from an appropriate tool is usually safer than pausing the entire VM in a debugger. If you need to know which method burns CPU, JFR or a sampling profiler generally has far less impact than single-stepping. If you need a value missing from telemetry, check whether a filtered custom metric/log can be added on a canary before opening production JDWP.

Do not assume "JFR has zero overhead" or "thread dumps have zero impact": every diagnostic tool has cost, yet a debugger's control power and ability to stall the system are typically much greater.

## 5. Securing the Port Across Network and Infrastructure Layers

### 5.1. Bind Loopback and Verify the Real Listener

For JDK 17+ HotSpot, a safer single-machine lab command is:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 DebugPortSafetyDemo 30
~~~

The JVM opens JDWP on the loopback **of the network namespace where the JVM runs**. On a Linux host, verify inside the right namespace:

~~~bash
# Observation only; does not modify the service.
ss -lntp | grep ':5005'
~~~

Expected local address is **`127.0.0.1:5005`**, not `0.0.0.0:5005`, `*:5005`, or a public IP. Socket listings also depend on user privileges and OS; missing process names do not prove a listener is safe. On Windows, inspect with PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 5005 -State Listen |
  Select-Object LocalAddress, LocalPort, OwningProcess
~~~

**The listening address is one check, not the entire verification.** Reverse proxies, NAT, port mappings, SSH forwarding, container port publishing, or `hostNetwork` can create unexpected paths to the port. Trace the full path from workstation → bastion → host → container/pod → JVM and verify effective rules at every hop.

Run network observation commands only on systems you are authorized to administer; do not scan ports or try attaching to unauthorized processes.

### 5.2. Controlled SSH Tunnel Path

On an operations-managed host where the JVM listens only on the **remote host's** loopback and the debugger runs on an authorized engineer's machine, SSH local port forwarding avoids exposing JDWP publicly:

~~~bash
# Run on the workstation of an engineer authorized to SSH into the target host.
# Exposes only local 127.0.0.1; remote end targets the SSH server's loopback.
ssh -N -L 127.0.0.1:5005:127.0.0.1:5005 debug-user@approved-host
~~~

The IDE connects to `127.0.0.1:5005` **on the workstation**. The tunnel's remote end is forwarded by the SSH server to `127.0.0.1:5005` **on the remote host**.

Mandatory conditions:

1. Use an authenticated SSH channel with verified host keys; restrict `debug-user` privileges and retain logs/audits per policy.
2. Confirm the JVM listens on the right loopback on the remote host; SSHing to a host does not automatically reach loopback **inside a container** if network namespaces differ.
3. Ensure the local side does not bind `0.0.0.0`; check for other forwards, proxies, or port conflicts.
4. Keep the tunnel open only during the incident window; close the tunnel and remove debug agent/configs when finished.
5. An SSH tunnel **protects the network hop over SSH**, without adding authentication to JDWP itself behind it; anyone permitted to open the tunnel gains high control over the JVM.

A private VPN can also protect transport without making JDWP inherently safe; if many machines/users share the VPN, a JDWP listener directly on a private IP remains highly sensitive. Never "fix" reachability by opening `*:5005` across the whole VPN assuming only engineers are there.

### 5.3. Containers and Kubernetes

Three distinct concepts:

- **Bind address inside the pod:** `127.0.0.1:5005` means the pod network namespace's loopback, not necessarily the node's or workstation's loopback.
- **Port publishing:** Docker `-p 5005:5005` can create a host listener or NAT; check which host interface is published. Never use that as a default for JDWP.
- **Kubernetes port-forward:** `kubectl port-forward` is an administrative action via the Kubernetes API, governed by RBAC and cluster admin paths. When permitted, it can reach a pod port without opening external Ingress/Services.

Example **solely for an approved staging namespace and pod**:

~~~bash
# Run from a workstation logged into the cluster with matching permissions.
# kubectl binds to localhost by default; specify explicitly for clarity.
kubectl port-forward --address localhost pod/staging-java-pod 5005:5005
~~~

Never change to `--address 0.0.0.0` so multiple people on the LAN can share it; that exposes the local endpoint on all interfaces. Never create a `NodePort`/`LoadBalancer` Service or Ingress just for debugging. Account for `pods/portforward` RBAC, service accounts, audit logs, network namespaces, host permissions, and approval scope.

**Critical limitation:** permission to `port-forward` into a pod is a strong access path. Do not assume "NetworkPolicy blocks port 5005 so anyone with port-forward rights cannot debug"; admin API traffic has different characteristics and requires checking actual policies. If you do not understand the network topology, stop and consult the platform/security team.

### 5.4. Debug Channels on Shared Machines

Binding loopback **reduces network exposure**, yet does not isolate users or processes sharing loopback access on the same host. On multi-tenant machines, untrusted accounts running in the same network namespace pose a risk. Isolate environments by user/container/VM and process permissions. On systems holding confidential data, **localhost does not mean "only me."**

## 6. Limiting Debugger Impact on a Live Serving Process

Securing the port answers **who can take control**. Limiting debugger operations answers **how much an authorized user can disrupt the system**.

### 6.1. Breakpoints Can Freeze the Whole JVM

In JDI, every event request has a `suspendPolicy`:

| Policy | Meaning | Risk |
| --- | --- | --- |
| `SUSPEND_ALL` | Suspends all threads when the event fires | Service stops processing requests/health checks, triggering cascading timeouts |
| `SUSPEND_EVENT_THREAD` | Suspends only the thread firing the event | Provides partial isolation, yet that thread may hold critical locks or resources |
| `SUSPEND_NONE` | Does not suspend threads on that event | Suitable for non-pausing observation on certain event requests, not a "read-only security mode" |

Per JDI `EventRequest`, the default is `SUSPEND_ALL` unless changed. IDEs may show "Suspend All" or "Suspend Thread" in the UI; **verify the actual breakpoint setting** rather than relying on IDE defaults. When a debugger pauses a thread holding a monitor or lock, other threads can block waiting on that lock and service behavior still stalls despite choosing single-thread suspend.

~~~text
Request A -> Thread-17 holds lock OrderCache
                     |
                     +--- BREAKPOINT (Suspend Thread) --- [paused]
                     |
Request B -> Thread-22 waits for OrderCache ------------> timeout
Health check -> Thread-24 if needing same lock ---------> may timeout
~~~

Thus **"Suspend Thread" reduces scope without guaranteeing safety**. Never place breakpoints inside global locks, transactions, high-volume request code, or while holding long-lived connections/leases.

### 6.2. Operations Prone to Causing Incidents

| Action | What can happen | Recommendation |
| --- | --- | --- |
| Unconditional breakpoint on hot path | Every request hits the breakpoint; requests pile up paused | Avoid in production; if forced, use very narrow conditions |
| Conditional breakpoint | IDE may evaluate condition on target JVM, burning CPU and causing side effects | Never call side-effecting methods; watch condition cost |
| Evaluate Expression | Can invoke methods, mutate objects/DB/cache, or trigger unintended code | By default **do not evaluate** arbitrary expressions in production |
| Set Value / Change State | Mutates live data, breaking logical integrity | Forbidden when the goal is solely diagnosis; use separate change procedures if needed |
| Repeated Step Into/Over | Breaks timing, prolongs lock holding, times out requests | Reproduce on staging/canary; try sampling/tracing first |
| Broad watchpoint/method-entry | High event volume and heavy overhead | Limit package/thread/instance, disable as soon as evidence is gathered |
| HotSwap / Reload class | May fail or leave running code inconsistent; JVM-limited | Never treat as a production hotfix tool; use standard deploys |
| Inspecting sensitive variables | Secrets may appear in IDE, history, screenshots, logs | Inspect only necessary data; never capture/save/attach secrets |
| Manual VM Pause | Stops all application threads | Never perform without explicit impact approval |

**There is no "side-effect-free debug window" merely because the operator intends to observe.** An expression like `order.getTotal()` might be benign if purely a getter, yet a Java method can lazy-load, allocate, query a DB, or update caches. You cannot prove a getter has no side effects just from the `get` prefix.

### 6.3. Pause Budgets and Cascading Failure Scenarios

Suppose a service handles 500 requests/second. A `SUSPEND_ALL` breakpoint pauses for 10 seconds under steady load: by simple math, **roughly 5,000 request arrivals** occur during that pause. Actual impact depends on load balancers, queue capacities, timeouts, retries, and routing to healthy replicas; 5,000 merely illustrates `rate × duration`, not a guaranteed failure count.

Effects extend beyond the JVM:

- Clients time out and automatically retry, amplifying load after Resume.
- Circuit breakers can trip open; health/liveness probes can mark pods unhealthy.
- Lock/transaction/lease timeouts trigger rollbacks, deadlocks, or contention storms.
- Pausing one replica in a small cluster can overload the remaining replicas.
- The debugger does not automatically restore all state if the network drops or the operator steps away.

**Live debug session goal:** if approved, perform only brief observation within SLO bounds; the coordinator must ensure immediate resume readiness, know how to close the connection, and abort the experiment if needed. If pausing exceeds budget or error rates rise, prioritize restoring service health.

### 6.4. Practical "Read-Only" Policies

A team rule saying "only inspect variables" works only when backed by participant permissions, training, checklists, and oversight; JDWP does not offer fine-grained RBAC like "allow inspect but forbid set value/evaluate." Never invent `readonly=true` in a config assuming it enforces restrictions.

When the need is strictly observation, replacing JDWP with **JFR, metrics, tracing, filtered logs, thread dumps**, or approved snapshots is usually better. Match the tool to the question rather than letting every engineer attach debuggers to live processes.

## 7. Java 17+ Practice Example: A Small HTTP Service Showing Blast Radius

This lab runs entirely on **loopback**, starts a temporary HTTP server with `/health` and `/work` endpoints, sends two internal requests, and shuts down. Data is synthetic; **never use in production or expose debug ports publicly**.

Goals:

- Normally: `/health` and `/work` return HTTP 200, request count equals 1.
- When intentionally enabling loopback JDWP with an authorized debugger: set a breakpoint in `/work`, observe the difference between `Suspend All` and `Suspend Thread`; run only on an **isolated test machine**.
- Observe that `suspend=n` does not prevent breakpoints from pausing once attached.
- Use `try/finally` to stop the HTTP server and worker executor so the demo never lingers indefinitely.

Create file **`DebugPortSafetyDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public final class DebugPortSafetyDemo {
    private static final AtomicInteger COMPLETED = new AtomicInteger();

    private static void respond(HttpExchange exchange, String value)
            throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        try (exchange) {
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        int attachWindowSeconds = args.length == 0 ? 0 : Integer.parseInt(args[0]);
        if (attachWindowSeconds < 0 || attachWindowSeconds > 120) {
            throw new IllegalArgumentException("Attach window must be 0..120 seconds");
        }

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        server.setExecutor(workers);
        server.createContext("/health", e -> respond(e, "OK"));
        server.createContext("/work", e -> {
            int id = COMPLETED.incrementAndGet(); // Breakpoint location.
            respond(e, "work-" + id);
        });
        server.start();

        try {
            if (attachWindowSeconds > 0) {
                System.out.println("attachWindowSeconds=" + attachWindowSeconds);
                Thread.sleep(Duration.ofSeconds(attachWindowSeconds).toMillis());
            }
            int port = server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();
            HttpRequest health = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:" + port + "/health"))
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpRequest work = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:" + port + "/work"))
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<String> r1 =
                    client.send(health, HttpResponse.BodyHandlers.ofString());
            HttpResponse<String> r2 =
                    client.send(work, HttpResponse.BodyHandlers.ofString());
            System.out.println("health=" + r1.statusCode() +
                               " body=" + r1.body());
            System.out.println("work=" + r2.statusCode() +
                               " body=" + r2.body());
            System.out.println("completed=" + COMPLETED.get());
        } finally {
            server.stop(0);
            workers.shutdownNow();
            System.out.println("stopped=true");
        }
    }
}
~~~

### 7.1. Running Without a Debugger

~~~bash
javac DebugPortSafetyDemo.java
java DebugPortSafetyDemo
~~~

Stdout verified on **JDK 24** (the Java APIs in this example are compatible with JDK 17+ including module `jdk.httpserver`):

~~~text
health=200 body=OK
work=200 body=work-1
completed=1
stopped=true
~~~

The HTTP server binds `127.0.0.1` with port **0** so the OS assigns an unused port. This port is not the JDWP port; it is used solely for lab data exchange. The actual port number is omitted as it varies across runs.

### 7.2. Running with JDWP on Loopback Only

On a controlled test machine, in one terminal:

~~~bash
# Run only in test environments; never use this command in production.
# Fixed JDWP port 5005, no wildcard.
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 DebugPortSafetyDemo 30
~~~

The JVM prints a debug-agent status line similar to:

~~~text
Listening for transport dt_socket at address: 5005
attachWindowSeconds=30
~~~

The program then waits up to 30 seconds for you to attach a debugger **from the same test machine** via IDE using host `127.0.0.1` port `5005`, before sending the two HTTP requests. If no debugger attaches, the final lines match section 7.1. If you place a breakpoint in `/work` and do not resume in time, the HTTP client can time out and the program will not print the same stdout; **that is the expected behavior to observe, not a lab bug**.

**Verification note:** JDK 24 ran this example with loopback JDWP, including `address=127.0.0.1:0` for an OS-assigned port; `:5005` above lets the IDE know the port ahead of time. If port 5005 is in use, do not kill/overwrite another process: pick a free loopback port and update the IDE accordingly.

Steps in the IDE:

1. Create a *Remote JVM Debug/Attach* config per your IDE, host `127.0.0.1`, port `5005`. Connect only to the running lab process.
2. Place a breakpoint on `int id = COMPLETED.incrementAndGet();`. Check the breakpoint's *Suspend* policy.
3. On the first try, pick `Suspend Thread` to observe scope; remember pausing even one thread can still cause disruption via locks/resources in real code.
4. Pause only briefly and **Resume** right away, without evaluating side-effecting expressions; note timestamps and request behavior.
5. Then detach, confirm the process exits, and verify with OS tools that the JDWP listener is gone.

The code configures `HttpClient` with a 5-second timeout to highlight the consequences of holding a breakpoint too long. **However, under `Suspend All`, timer-handling threads can also be paused**, so there is no guarantee the timeout triggers strictly after 5 seconds wall-clock; the operator must actively resume. In real services, timeouts at load balancers or systems outside the JVM can still fire while the JVM is frozen.

### 7.3. Meaning of the Results

| Observation | Right conclusion | Wrong conclusion to avoid |
| --- | --- | --- |
| No debugger attached, two HTTP 200s | Normal lab path works | "Production app will definitely be safe with JDWP on" |
| JDWP prints "Listening ... 5005" | Agent is listening on socket per config | "Default password/encryption exists" |
| `suspend=n`, yet breakpoint still pauses | Startup did not wait for debugger; breakpoints are a separate mechanism | "`suspend=n` means all breakpoints are observe-only" |
| Pausing `/work` thread slows the request | Request-handling thread was held | "Suspend Thread does not affect other users" |
| Service keeps running after detach | Current control session ended | "JDWP port closed permanently while JVM stays up" |
| Process exited and no listener remains | That process's JDWP port is gone | "No other instance is still running JDWP" |

A crucial point: **detaching a debugger is not equivalent to removing the JDWP agent from startup configuration**. If the service stays alive with `server=y`, the listener can remain or accept new connections per JDWP implementation/config; verify and use a standard rollout/restart to strip the debug flag. Never treat clicking Disconnect in an IDE as proof the risk is gone.

## 8. Process for Approving Exceptions on a Live Serving System

This is a **controlled runbook**. Default to non-debugger alternatives; proceed only with proper operational sign-off.

### 8.1. Pre-Session: Approval and Scope Setup

Record at minimum in the incident/change record:

| Attribute | Required content |
| --- | --- |
| Purpose | Specific technical question unsolvable via JFR/logs/metrics/traces |
| Scope | Service, cluster, namespace/pod/VM, instance/PID, JDK/vendor |
| Owners | Debugging engineer, monitoring SRE/on-call, approver |
| Time window | Start/stop window and mandatory cutoff; never leave open indefinitely |
| Data | Sensitivity classification; what may be viewed/recorded/attached and what is off-limits |
| Network | Loopback/tunnel/RBAC/firewall, which source hosts are permitted |
| Accepted impact | p95/p99/error rate, in-flight requests, pause budget |
| Rollback | How to detach/resume, kill tunnels, remove JDWP flag via standard deploy |
| Audit | Where logs of approval, session, attach/detach times, and outcomes are stored |

Never paste credentials/secrets into tickets or command logs. In multi-replica production, consider isolating a **canary replica** and routing minimal load or draining traffic on that replica (per policy) to shrink blast radius. Do not randomly disable liveness probes or resize pools just to make debugging easier; each tweak adds operational risk.

### 8.2. Pre-Session: Technical Checks

1. Identify the **exact** process/PID and container/network namespace. Do not use the PID of a sidecar or a different JVM.
2. Check version via `java -version` and syntax via `java -agentlib:jdwp=help` on an equivalent image; inspect current debug flags.
3. Verify the JDWP listener binds only the intended interface inside the JVM's namespace with no public port publishing; check security groups, firewalls, and service mesh/proxies if present.
4. Verify an **authorized** admin channel (SSH tunnel / RBAC-scoped port-forward) targeting local loopback; audit user identity.
5. Agree on max breakpoint duration, zero evaluate/state mutation, who watches SLOs, and who holds abort authority.
6. Test Resume/Disconnect/rollback mechanics before the operator opens the debugger.
7. If JDWP is not yet enabled on the JVM, do not "experiment" with arbitrary `jcmd` commands or dynamic agent attaches in production. Enabling the agent may require launch/restart changes depending on JVM and policy; open a dedicated change instead of assuming dynamic enabling is supported.

### 8.3. During Session: Bounded Evidence Collection

- Place breakpoints only at pre-vetted locations/conditions; avoid hot paths, locks, long transactions, and synchronized blocks.
- Prefer narrowly conditioned breakpoints or logpoints/tracepoints **only after understanding overhead and expression evaluation**. Never assume logpoints are completely safe.
- If multiple threads need simultaneous observation, inspect thread dumps/traces rather than pause-all.
- Watch p99, throughput, error rate, health/readiness, request queues, transaction timeouts, and downstream alarms.
- If SLOs breach, pauses drag out unexpectedly, or data leaks, **Resume/Abort immediately** per runbook; do not wait to grab another screenshot.
- Record only the details needed to establish root cause; never store tokens, PII, memory dumps, or full object graphs in public channels.

### 8.4. Post-Session: Closure, Verification, and Reporting

1. Resume all paused threads, remove breakpoints/watchpoints, and detach the IDE.
2. Tear down SSH tunnels/port-forwards and revoke temporary access per the change record.
3. Remove `-agentlib:jdwp` from deployment configuration; if needed, execute a controlled rollout/restart so **no agent listener remains**. Never abruptly restart a production JVM.
4. Re-verify binds/ports in the actual namespace (e.g., `ss -lntp` or `Get-NetTCPConnection`), combined with config inventory and infrastructure checks.
5. Confirm traffic, error rate, p99, health, and queues return within acceptable bounds. Watch for post-session lag caused by accumulated retries/backlogs.
6. Document participants, timestamps, minimal evidence, actual impact, root cause/hypothesis, and long-term remediation.
7. Delete or apply policy-compliant retention to screenshots, debug logs, and diagnostic copies.

**Completion criterion is not "the debugger disconnected."** Completion means the session ended, temporary permissions are revoked, the listener is no longer exposed, the flag is gone from deployment targets, SLOs are back to normal, and sensitive data is properly handled.

## 9. Scenarios and Decisions

### Scenario A: Port 5005 Listening on `0.0.0.0`

Symptom: inside the JVM's namespace, `ss` or an equivalent tool reports the debug listener bound to all IPv4 interfaces. This is a **high-priority configuration incident**, especially if security groups/firewalls/port publishing allow access from other networks.

Action: restrict network access under authorized emergency procedures, assess who could have reached it, and remove the wildcard configuration through an approved deploy. Never try "proving safety" by attempting to connect from an unknown machine. If unauthorized control is suspected, follow security incident procedures instead of investigating by sending debug commands yourself.

### Scenario B: Port Bound to Loopback, Yet Pod Allows `kubectl port-forward`

Loopback inside the pod shrinks public exposure; however, anyone with RBAC to port-forward can open an access path. Audit `pods/portforward` permissions, API server audit logs, access tools, and session duration. Never add a LoadBalancer Service to "avoid needing port-forward."

### Scenario C: Breakpoint Uses `Suspend Thread`, Yet p99 Still Spikes

The paused thread may hold a lock, connection, or transaction. Other threads waiting for that resource suffer a domino effect. Inspect lock owners, thread stacks, pool saturation, and timeout logs; resume immediately. Never assume only `Suspend All` can cause an outage.

### Scenario D: Engineer Only Needs to Know Which Thread Is Blocked

Use appropriate thread dump tools (`jcmd <pid> Thread.print` on HotSpot when authorized), thread states, JFR lock events, and metrics first. If those already distinguish blocked/runnable/waiting threads, **do not enable JDWP** merely to open a thread view in an IDE.

### Scenario E: Need to Inspect a Variable Existing Only in Production

Consider a filtered event/log or minimal snapshot on a canary, bounding cardinality and sensitive fields. If a debugger is mandatory, the owner must explicitly approve observation scope and impact. Never "test evaluate" methods directly in the JVM to fetch variables because that can execute unintended business logic.

## 10. Common Mistakes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Using `address=*:5005` so the IDE attaches easily | Port may be reachable over unintended networks | Loopback + controlled admin path; ideally disabled in production |
| Assuming `suspend=n` prevents all pauses | Breakpoints/IDE can still pause the VM or threads | Check `suspendPolicy` and set a pause budget |
| Assuming private VPC = authenticated JDWP | Workloads/users in the same subnet can reach it | Segmentation, RBAC, SSH, audit, remove listener |
| Using `allow=...` like a password | IP filtering neither authenticates identity nor encrypts | Keep secure tunnel/VPN and source controls |
| Binding loopback in pod while publishing host port | Effective exposure may differ from expectation | Verify namespaces, NAT/port mapping, and firewalls |
| Detaching IDE and assuming the port is closed | Agent/JVM can keep listening | Strip debug flags and verify listeners after rollout |
| Setting breakpoints on every request | Increases latency, can stall whole cluster | Avoid hot paths; use logs/traces/JFR |
| Choosing Suspend Thread and assuming 100% safety | Thread holding lock/connection still blocks others | Pick safe sites and bound duration |
| Evaluating a getter "just to look" | Getter may lazy-load/query DB/mutate cache | Never execute arbitrary code in production |
| Taking screenshots containing tokens for tickets | Leaks sensitive data | Redact/minimize, restrict view permissions and retention |
| Enabling debug flag via cluster-wide `JAVA_TOOL_OPTIONS` | Can spread across many JVMs and open multiple ports | Narrowly scoped, reviewed changes with rollback |
| Nobody monitoring the service while debugging | Timeouts/outages go unnoticed | SRE/on-call watches SLOs with abort authority |
| Opening debug port first and asking approval later | Risk already materialized, hard to audit | Obtain approval and set controls **beforehand** |
| Trying to hotfix bugs via HotSwap in production | Hard to audit/rollback; behavior diverges from tested build | Fix via CI/CD and standard rollout |

## 11. Self-Check and Scenario Exercises

**Question 1.** A JVM uses `-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005`. Does `suspend=n` make the connection secure? **Not yet.** It only skips waiting for a debugger at startup, while `*:5005` can listen on all interfaces and JDWP is a powerful control channel.

**Question 2.** Is `address=5005` on Oracle/OpenJDK 21 the same as `address=*:5005`? **No.** JDK 21 docs state an empty host binds local loopback; wildcard listens on all interfaces. Still verify the actual listener and specific JDK.

**Question 3.** A debugger selects `Suspend Thread`. If a breakpoint pauses a thread holding a monitor on `OrderCache`, are other requests guaranteed to proceed normally? **No.** They can block waiting on that monitor.

**Question 4.** Can you add `allow=10.0.0.0/8` and publish the JDWP port publicly? **No.** `allow` only filters IPs; it neither authenticates nor encrypts, and a subnet can host many untrusted sources. In production, disable JDWP or use a tightly bounded exception window.

**Question 5.** An operator only needs a thread dump. Is opening a debug port necessary? **No.** On HotSpot you can use `jcmd <pid> Thread.print` when authorized; assess cost and permissions, but no JDWP listener is needed.

**Question 6.** During a 12-second pause-all, traffic averages 200 req/s. Roughly how many requests arrive under the simple model? **2,400 arrivals**. Not necessarily 2,400 failed requests: outcome also depends on timeouts, queues, load balancing, and retries.

**Question 7.** If the debugger disconnects, is JDWP completely removed from the JVM? **Not by default.** Verify debug agent/config and listeners; remove via formal deployment procedures.

**Question 8.** A pod has listener `127.0.0.1:5005`, yet the platform team granted `pods/portforward` to all developers. Is this equivalent to "internal staff can only view logs"? **No.** Port-forwarding to JDWP can grant JVM control privileges; review RBAC and restrict permitted users.

**Question 9.** An engineer evaluates `service.refreshCache()` while inspecting variables. Is this read-only? **No.** It can execute state-mutating code and trigger I/O; never treat it as a harmless inspection step.

**Question 10.** A new manifest removed `-agentlib:jdwp`, yet the old process is still running. Is "the port is off" accurate? **No.** Verify running instances, rollout status, and actual listeners; manifests do not equal runtime state.

## 12. Decision and Session-Closure Checklist

Before approving a live-debug exception:

- [ ] Tried logs/metrics/traces/JFR/thread dumps or staging reproduction first.
- [ ] Recorded incident, target JVM, engineer, SRE, approver, and justification.
- [ ] Bounded time window; defined pause budget, SLO guardrails, and abort authority.
- [ ] JDWP bound to loopback inside the right network namespace—no wildcard/public/NodePort/LoadBalancer.
- [ ] Authenticated access path (SSH/VPN/bastion/cluster RBAC) with corresponding audit logging.
- [ ] Did not treat `allow`, `suspend=n`, or "private network" as JDWP authentication.
- [ ] Breakpoints/conditions reviewed; no evaluate/set state/hot swap during observation sessions.
- [ ] Accounted for secrets/PII in variables and minimal recording policies.
- [ ] Prepared Resume, Disconnect, rollback, and agent-removal steps for session end.

After the session:

- [ ] No paused threads remain; breakpoints/watchpoints and tunnels are closed.
- [ ] JDWP launch flag removed from target workload; standard rollout/restart completed if needed.
- [ ] Re-verified actual listener is no longer exposed, not relying solely on Disconnect.
- [ ] Latency, error rate, throughput, and health stabilized, with downstream debug-induced backlogs cleared.
- [ ] Temporary permissions and sensitive artifacts revoked/deleted on schedule.
- [ ] Report documents conclusions, impact, and measures to avoid production JDWP next time.

**Conclusion:** a JDWP port is a **sensitive JVM control path**. Relying solely on port numbers, private subnets, or `suspend=n` is insufficient. Leave it off by default on serving processes; if approved as an exception, **restrict reachability, restrict actions, bound duration, monitor actively, and verify clean closure**.

## References

- Oracle Java SE 21: [JPDA Connection and Invocation Details](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html) — `-agentlib:jdwp`, `dt_socket`, `server`, `address`, `allow`, `suspend`, `timeout`, and loopback vs. wildcard differences.
- Oracle Java SE 17: [JDWP/JPDA Connection and Invocation Details](https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html) — verify JDK 17 behavior.
- Oracle Java SE 17: [JDI EventRequest](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jdi/com/sun/jdi/request/EventRequest.html) — `SUSPEND_ALL`, `SUSPEND_EVENT_THREAD`, `SUSPEND_NONE`.
- Oracle Java SE 21: [Java Debug Wire Protocol](https://docs.oracle.com/en/java/javase/21/docs/specs/jdwp/jdwp-protocol.html) — debugger command set and JVM manipulation capabilities.
- Kubernetes: [kubectl port-forward](https://kubernetes.io/docs/reference/generated/kubectl/kubectl-commands#port-forward) — default localhost bind, `--address`, and forwarding examples.
- Oracle Java SE 21: [jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) — diagnostic commands such as `Thread.print` when authorized.

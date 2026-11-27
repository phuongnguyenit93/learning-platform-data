# JMX, Metric Export Mechanisms, and Access Controls in Apache Cassandra

## 1. Goal: observe the cluster without opening an administrative vulnerability

In **Apache Cassandra**, a **distributed wide-column** database management system, a CQL query from a Java application can involve a coordinator, multiple replicas, memtables, SSTables, caches, compaction, and repair. When latency or timeouts spike, engineers need visibility into those components. One primary telemetry source is **Java Management Extensions (JMX)**.

JMX exposes state and metrics from a Java process through **MBeans** (*managed beans*). Cassandra uses this mechanism to publish internal metrics and power administrative tools, including `nodetool`. Systems such as Prometheus usually do not read JMX natively; they rely on an **exporter** to convert MBean data into a scrapeable format.

However, **JMX is not just a read-only metric endpoint**. Some MBeans also expose administrative operations that can alter cluster behavior. Enabling remote JMX, opening exporter ports, or granting access must therefore be designed as part of the **system security surface**, not treated as an afterthought when building dashboards.

After this lesson, you will be able to:

- Explain the relationship across **JVM → MBean → JMX → exporter → monitoring system**.
- Distinguish **Cassandra metrics, JVM metrics, OS metrics**, and **Java Driver/application metrics**.
- Choose a collection architecture suited to nodes, datacenters, keyspaces, tables, and request classes.
- Understand the access boundaries of **local JMX**, **remote JMX**, and **HTTP metrics endpoints**.
- Perform controlled connection/metric checks and troubleshoot RMI, firewall, authentication, TLS, and missing-metric issues.
- Build deployment checklists, alerts, and operational answers for real-world scenarios.

> **Version scope:** How JMX is enabled, MBean names, metric names, ports, and TLS/authentication capabilities vary across Cassandra 3.x, 4.x, 5.x, distributions, and JDK/JMX Exporter versions. Configurations in this lesson are educational examples to cross-check against documentation for your **exact deployment**, not copy-paste production templates.

## 2. What is JMX? How does an MBean differ from a metric?

**JMX** is a Java API and mechanism for managing and monitoring Java applications. A JVM process registers **MBeans** inside an `MBeanServer`. Each MBean has an **ObjectName** and may expose:

1. **Attributes:** readable values such as request counts, latencies, or pending tasks.
2. **Operations:** callable actions that can sometimes **mutate application state**.
3. **Notifications:** management events emitted by certain MBeans.

A metric is typically **one attribute or a meaningful group of measurable attributes**. One MBean does not automatically map 1:1 to a single Prometheus series; the exporter determines how attributes are mapped.

Example of a common Cassandra ObjectName:

```text
org.apache.cassandra.metrics:
    type=ClientRequest,
    scope=Read,
    name=Latency
```

Here `type` categorizes the metric group, `scope` identifies the request type, and `name` specifies the metric. Attributes may include `Count` or latency statistics; always verify the **actual units and metric types** for your version before plotting charts.

For table-level metrics, a typical form is:

```text
org.apache.cassandra.metrics:
    type=Table,
    keyspace=telemetry_ks,
    scope=readings_by_device_day,
    name=LiveDiskSpaceUsed
```

This illustrates structure only: **each node maintains its own local MBeans/values**, not a cluster-wide total. A keyspace with RF = 3 does not mean one JMX endpoint sums across all replicas.

## 3. Four telemetry sources you must not conflate

| Source | Where does it measure? | Examples | Limitations |
|---|---|---|---|
| **Cassandra JMX** | Inside the Cassandra node JVM | ClientRequest, Table, Keyspace, ThreadPools, Compaction | Does not directly know the latency of a specific API |
| **JVM metrics** | Cassandra's JVM | Heap, GC, threads, buffer pools | Does not fully reflect host disk capacity or I/O |
| **Host/container metrics** | OS, VM, or container | CPU, disk available, I/O latency, network | Does not know which CQL query drives load |
| **Java Driver/application** | Application JVM calling Cassandra | Logical request latency, retries, in-flight, timeouts | Does not by itself identify which replica is bottlenecked |

A good dashboard combines these sources while preserving **scope, units, and measurement-source labels**.

For example, a slow API while `ClientRequest.Read.Latency` on coordinators looks normal may point to the **driver connection pool**, application JVM, or network. Conversely, high coordinator latency can be caused by a single slow replica even when the coordinator's CPU is low.

**Never claim low CPU = healthy Cassandra, and never claim JMX returning data = users see no errors.** Inspect request rate, errors, p95/p99 latency, and saturation together.

## 4. Metric flow from a Cassandra node to the monitoring stack

```text
            +----------------------+
            |   Cassandra JVM      |
            |                      |
            |   MBeanServer        |
            |   + Cassandra MBeans |
            |   + JVM MBeans       |
            +----------+-----------+
                       |
                   JMX attributes
                       |
          +------------+----------------+
          |                             |
          v                             v
   Local JMX access              JMX exporter/agent
   nodetool / JConsole           maps MBean -> metric
   (authorized admin)                    |
                                         v
                                 HTTP /metrics endpoint
                                         |
                              Prometheus or collector
                                         |
                                Dashboards / alerts / SLOs
```

Separate **two control planes**:

- **Administrative plane:** JMX can read attributes and invoke operations. Access must be tightly restricted.
- **Monitoring plane:** an exporter converts selected attributes into measurements and publishes them over HTTP(S) or a collector pipeline. The goal is **metric read-only access**, never granting MBean execution powers to dashboard viewers.

A working Prometheus scrape **does not prove** the collector holds JMX admin privileges, nor should you expose remote JMX to the whole monitoring network if an in-JVM agent can be used.

## 5. JMX access models: local, remote, and Java agent

| Model | Access path | Advantages | Risks/limitations |
|---|---|---|---|
| **Local JMX** | Tools on the node itself via local loopback/connector | No need to expose JMX over the network | Still requires host access controls and account protection |
| **Remote JMX over RMI** | Client from another host connects to an allowed JMX connector | Allows remote admin tools/collectors | Expands admin attack surface; RMI, firewalls, TLS, and auth are complex |
| **Java agent exporter** | Exporter runs inside Cassandra JVM, reading local MBeans | No need to expose remote JMX just for metrics | Agent and HTTP metrics port still require protection; adds JVM overhead |
| **Standalone exporter** | Separate process connecting via remote JMX | Decouples collector lifecycle from Cassandra | Requires secure remote JMX setup; extra network hop |
| **Local agent/sidecar** | Collector reads local endpoint and forwards metrics | Fits container models, limits exposed ports | Must secure network namespace, service account, and telemetry pipeline |

**Common practical choice:** if the goal is purely Prometheus metrics, prefer an exporter that **reads MBeans locally on the node** and exposes metrics on an isolated monitoring network rather than opening a privileged remote JMX port across multiple systems.

Deploying an agent or sidecar must account for Cassandra version, JDK, container setup, collector architecture, and operational cost. No single pattern fits every deployment.

## 6. Common ports and their security meaning

| Example port | Typical role | Interchangeable? |
|---|---|---|
| `9042` | Native CQL transport for client drivers in many Cassandra configs | **Not** JMX |
| `7199` | JMX port used by `nodetool` in many default configs | **Not** CQL or HTTP metrics |
| `9404` | Common example port for JMX exporter `/metrics` endpoint | **Not** a mandatory standard port |
| Configured internode ports | Node-to-node Cassandra communication | Should not be opened just for dashboard scraping |

Ports vary by environment. Always check service/JDK configuration and collector configs rather than assuming a port number alone identifies the protocol.

### JMX RMI often uses more than one port

With **remote JMX over RMI**, the connection may hit the **RMI registry** first and then be redirected to a remote object advertised on another address/port. Unless the JDK/connector is pinned properly, opening only the registry port in a firewall may not suffice.

JVM properties frequently seen in JMX/RMI documentation include:

```text
com.sun.management.jmxremote.port
com.sun.management.jmxremote.rmi.port
java.rmi.server.hostname
```

**Do not treat these three lines as a complete configuration.** Check JDK behavior, Cassandra settings, TLS, and network policy. In particular, never “fix” an exporter connection failure by **disabling authentication or encryption**.

## 7. `nodetool` uses JMX: diagnostics and administrative privileges

In many Cassandra versions, `nodetool` is a JMX client that reads state and triggers administrative operations. Common **read-only diagnostic** commands:

```bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool tablestats telemetry_ks.readings_by_device_day
```

| Command | What it observes | Caveat |
|---|---|---|
| `status` | Node state and cluster token/routing view | Point-in-time snapshot, not continuous alerting |
| `info` | Node summary, select JVM/storage details | Output format varies by version |
| `tpstats` | Thread pools, pending and dropped tasks/messages | Correlate with workload at the same timestamp |
| `compactionstats` | Running and pending compactions | Does not imply tombstones will clear immediately |
| `tablestats` | Per-table metrics/stats on that node | Not total cluster-wide logical reads |

While those commands are observational, `nodetool` also exposes **state-changing** operations such as repair, flush, compact, decommission, or runtime config changes depending on version. Therefore, **JMX access can mean cluster administrative control**, not mere metric reading.

**Never grant a dashboard service account full administrative JMX rights** just so a scraper can read metrics. Separate Cassandra operational permissions from telemetry collection permissions.

## 8. MBean names, metric groups, and export limitations

Cassandra typically organizes MBeans under groups with names similar to:

| Common group | What it measures | Notes |
|---|---|---|
| `ClientRequest` | Read/write request count, latency, timeouts | Coordinator-level; not guaranteed to have a keyspace label |
| `Table` | SSTables, memtables, disk, row/cell scans, latency | Single table on a **single node** |
| `Keyspace` | Keyspace-level workload/metrics | Supported attributes vary by version |
| `ThreadPools` | Active/pending/completed tasks | Aimed at detecting saturation |
| `Compaction` | Pending/completed compactions | Does not imply immediate disk reclamation |
| `Cache` | Hits, misses, size/capacity | Distinguish cache type and workload |
| `DroppedMessage` | Dropped internal messages | Often linked to queueing/saturation |
| JVM `java.lang` | Heap, GC, threads | Does not know which partition drives load |

For example, an ObjectName like `ClientRequest.Read.Latency` may expose `Count`, `Mean`, `50thPercentile`, `99thPercentile`, or other statistics. **Latency units can differ** across JMX exposure, Cassandra conventions, and exporter transforms: verify units before presenting values in milliseconds or seconds.

An exporter can:

- **Preserve** raw metric names/groups (leading to long, inconsistent names).
- **Rename** via mapping rules, such as turning a count attribute into a `..._total` counter.
- **Filter out** unneeded MBeans to reduce series count.
- **Attach labels** like `cluster`, `datacenter`, `node`, `keyspace`, `table`, and `request_type` as configured.

However, never assume every percentile gauge in JMX is a Prometheus histogram. Without valid `*_bucket` series, **do not call `histogram_quantile()`** on that data.

## 9. Java agent exporter: illustrative lab deployment

A common approach uses the **JMX Exporter Java agent** to read MBeans directly inside the Cassandra process and serve a metrics endpoint.

**Illustrative** JVM argument example:

```text
-javaagent:/opt/monitoring/jmx_prometheus_javaagent.jar=127.0.0.1:9404:/etc/cassandra/jmx-exporter.yaml
```

The intent here is to **bind loopback only** for local testing, assuming the exporter version supports this `host:port` syntax. Verify the JAR name, JVM injection mechanism, and config location against your exporter version and Cassandra packaging. Adding an argument to an already-running process has no effect: **Java agents load at JVM startup**, so a controlled rolling restart is normally required.

### Illustrative mapping configuration

```yaml
# Example mapping rule only; verify actual ObjectNames
# against your Cassandra and JMX Exporter versions.
lowercaseOutputName: true
lowercaseOutputLabelNames: true
rules:
  - pattern: 'org.apache.cassandra.metrics<type=ClientRequest, scope=(.*), name=Latency><>Count'
    name: cassandra_client_request_latency_count
    type: COUNTER
    labels:
      operation: "$1"
```

This rule illustrates extracting the `Count` attribute from a matching MBean and exposing it as a counter with an `operation` label. **Do not treat the pattern as a universal contract**: ObjectName key ordering, MBean names, value types, and exporter parsing must be tested. When troubleshooting, inspect the actual `/metrics` output instead of assuming Cassandra has no activity.

### Testing the local endpoint

```bash
# Run on an authorized test node/container
# with the exporter bound to loopback only.
curl --fail --silent http://127.0.0.1:9404/metrics
```

The response uses Prometheus text exposition format, showing `# HELP`, `# TYPE`, and numeric series when configured properly. Confirm that **expected Cassandra metrics** appear, not only internal exporter metrics.

**Access protection:** loopback binding works for local node tests; if Prometheus runs on another host, it **cannot reach** this loopback endpoint directly. In production, route scrapes through an **isolated monitoring network or an authenticated/TLS proxy** with firewall rules—never immediately switch to binding `0.0.0.0` with zero protection.

## 10. Standalone exporter: when it makes sense and security trade-offs

A standalone exporter runs as a separate process, connects to **remote JMX**, and serves HTTP metrics for a collector.

```text
Prometheus                   Exporter                  Cassandra node
    |  GET /metrics              |                           |
    +-------------------------->|                           |
    |                           |--- JMX/RMI + auth/TLS ---->|
    |                           |<--- MBean attributes ------|
    |<---- metrics text --------|
```

Trade-offs:

1. **Advantage:** exporter lifecycle is decoupled from Cassandra's JVM; it can be upgraded or restarted independently in some setups.
2. **Dependencies:** requires remote JMX enabled, reachable registry and RMI ports/addresses, and valid credentials/trust material.
3. **Security:** the exporter may hold JMX credentials; leaked credentials could grant node administrative access depending on role scope.
4. **Reliability:** if the exporter or JMX link fails, dashboards go blind even though Cassandra continues serving CQL normally.
5. **Overhead:** scraping too often or querying too many MBeans adds load to both the Cassandra JVM and the collector.

A standalone exporter is not “secure by default” merely because it is a separate process. You must secure **both hops**: exporter → Cassandra JMX and Prometheus → exporter metrics.

## 11. Prometheus scraping: example and correctness checks

A **local lab** scrape config when Prometheus runs on the same host/network namespace as the exporter:

```yaml
scrape_configs:
  - job_name: cassandra-jmx-lab
    scrape_interval: 30s
    scrape_timeout: 10s
    static_configs:
      - targets: ['127.0.0.1:9404']
        labels:
          cluster: 'cassandra-lab'
          datacenter: 'dc1'
```

In production, Prometheus typically runs elsewhere; targets must use **routable addresses over a protected channel**, never blindly copying `127.0.0.1` from a lab. On Kubernetes/VMs, configure Services, NetworkPolicies/ACLs, mTLS, or proxies to match your architecture.

Sample PromQL queries, assuming the exporter maps the corresponding series:

```promql
# Check whether the collector successfully scrapes the target.
up{job="cassandra-jmx-lab"}

# Compute rate from a counter; metric name below is an illustrative mapping.
sum by (instance, operation) (
  rate(cassandra_client_request_latency_count_total[5m])
)
```

**Metric naming warning:** exporters may append `_total` to counters depending on version, or name metrics differently. Inspect `/metrics` and use the **exact** emitted name. Never build alerts on guessed names.

**Do not equate scraped series counts with business request counts:** one client write can touch multiple replicas, and an exporter might emit counter, rate, and gauge metrics for the same MBean group. Verify semantics before computing cluster-wide throughput.

## 12. Minimum security rules for remote JMX

**Remote JMX is a high-risk administrative interface.** Baseline security controls include:

1. **Do not enable remote JMX unless required.** Prefer local JMX or an in-process Java agent for metrics where feasible.
2. **Restrict listen addresses and network ACLs/firewalls.** Only authorized bastion hosts or collectors should reach the JMX port.
3. **Enable authentication and authorization** supported by your JDK/Cassandra version; use dedicated least-privilege accounts.
4. **Encrypt connections with TLS** whenever admin traffic crosses a network; validate certificates, hostnames, truststores, and rotation policies.
5. **Block unintended admin paths:** JMX can invoke operations, not just read metrics. Audit which MBeans an account is actually allowed to call.
6. **Protect secrets:** never hard-code passwords in scripts, JVM args, URLs, git repositories, dashboards, or Prometheus labels. Use a secrets manager or equivalent.
7. **Audit access and config changes:** track who enabled remote JMX, opened firewall rules, modified roles, and from where connections originate.
8. **Re-verify after upgrades:** JDK, Cassandra, and exporter updates can change defaults or authentication parameters.

Some deployments configure JMX permissions via JDK files or Cassandra authentication hooks. **Exact filenames, syntax, and permissions vary by version.** Never copy a `jmxremote.password` or `jmxremote.access` snippet without verifying your active integration and OS file permissions (readable only by the required service user).

> What not to do: enable remote JMX and disable TLS/authentication just to make `nodetool` or an exporter connect easily. That can allow anyone on the network to read sensitive metadata or disrupt the Cassandra process.

## 13. Protecting HTTP `/metrics` and the collection pipeline

Even when an exporter **only exposes metrics**, `/metrics` can reveal:

- **Keyspace/table** names, node counts, datacenter/rack layout, and exporter or JVM versions.
- Traffic volumes, request mixes, data sizes, error rates, and load patterns.
- Internal architecture or incident timing if labels are overly granular.

Therefore, “read-only metrics” **does not mean harmless public data**.

| Component | Protection requirement |
|---|---|
| **Exporter listener** | Bind loopback/private IP or constrained socket; avoid public Internet |
| **Scrape path** | Firewall, NetworkPolicy, mTLS/TLS proxy, or auth fitting topology |
| **Collector** | Dedicated service account, restricted egress, managed credentials/secrets |
| **Prometheus storage** | Query RBAC, retention, encryption/backups per policy |
| **Grafana/dashboards** | SSO/RBAC, restrict who can view infrastructure details |
| **Labels/logs** | Exclude credentials, tokens, raw CQL parameters, arbitrary user/session IDs |
| **Config changes** | Peer review, audit trail, staging validation before rollout |

**Watch out for network namespaces:** `127.0.0.1` inside an exporter container is not Prometheus's loopback unless they share a network namespace (e.g., sidecars in the same Kubernetes Pod). Understand the real network path instead of exposing the endpoint cluster-wide to “make it work”.

To centralize metrics across multiple datacenters, use Prometheus federation, `remote_write`, or local collectors suited to your network—never open administrative JMX across the WAN just to place one scraper centrally.

## 14. Role-based access: who needs what?

| Role | Need | Minimum privileges to grant |
|---|---|---|
| **On-call SRE/DBA** | Inspect JMX/`nodetool`, investigate incidents | Admin access over protected channel with auditing and procedures |
| **Metrics collector** | Read indicators | Read only required telemetry; no state-mutating JMX operations where separable |
| **Application developer** | View service latency/errors | Filtered dashboards/traces; no remote JMX access |
| **Data analytics team** | Business statistics | Dedicated data/business metrics; no admin endpoints |
| **Repair/maintenance automation** | Run Cassandra maintenance tasks | Dedicated service account, scoped targets/tasks, confirmation and logging |

**Least-privilege principle:** someone viewing charts does not inherently need permission to invoke MBean operations; someone allowed to run `nodetool status` should not automatically have rights to alter cluster topology if your authorization layer can separate them.

When your JMX version/setup cannot enforce fine-grained read-only permissions, **place a read-only exporter/proxy in front** and keep remote JMX locked down for metric consumers.

## 15. Controlled observability without cardinality explosion

A per-table MBean can generate many series across `instance`, `keyspace`, `table`, `metric`, `quantile`, and so on. With hundreds of tables and many nodes, overly broad mappings strain CPU, network, and Prometheus storage.

Compare two label sets:

```text
Managed labels:
  cluster="prod-a"
  datacenter="dc1"
  instance="cassandra-03"
  keyspace="telemetry_ks"
  table="readings_by_device_day"
  operation="read"

Labels to keep out of metrics:
  partition_key="specific device"
  user_id="specific user"
  request_id="unique per request"
  token="secret"
  raw_cql="parameterized query text"
```

Select metrics based on **operational goals** rather than enabling every MBean upfront and deciding dashboards later. For a new table, start with read/write latency, tombstone scans, SSTables/memtable, disk, and compaction, then expand as needed.

Multi-rule exporter configs can also accidentally map **duplicate metric names or colliding labels**, corrupting data. Validate metric families, counter/gauge types, units, labels, and series counts after every config change.

## 16. Metrics are not commands: counter, gauge, timer, and histogram

| Type | Conceptual example | Usage |
|---|---|---|
| **Counter** | Total read requests processed | Compute `rate()`/`increase()` over a window |
| **Gauge** | Pending compactions at scrape time | Track current value and trend |
| **Timer** | Read latency | Read count and latency distribution in verified units |
| **Histogram** | Observation counts by bucket | Compute quantiles from buckets if exporter truly emits histograms |
| **Snapshot percentile** | MBean `99thPercentile` | Per-node gauge/snapshot; never average to get cluster p99 |

For example, an exporter might publish `Latency.Count`, `Latency.99thPercentile`, and `Latency.MeanRate` as three separate series. **They do not share the same unit** and are not all monotonically increasing.

When aggregating:

- Handle **counter resets across restarts** using proper rate functions.
- Pending-task gauges can drop; never plot a raw cumulative counter as queue depth.
- Per-node percentiles cannot be summed or averaged into a cluster percentile.
- Application-side latency includes driver/network time; coordinator latency covers a different boundary.
- One logical Java write can trigger multiple replica operations, especially as RF, CL, and retries vary.

**A `200 OK` from `/metrics` is not enough**: verify the exact semantics of at least the core metrics powering your dashboards.

## 17. Troubleshooting JMX and exporter connectivity

| Symptom | Likely causes to check | Safe remediation |
|---|---|---|
| Local `nodetool` fails | JMX not running, wrong port/host, auth failure | Check local node logs/config; do not blindly open remote JMX |
| Remote JMX reaches registry but session fails | RMI advertises different IP/port, firewall, or NAT | Verify RMI address/ports with the network team |
| `Authentication failed` | Wrong credentials/role or changed JMX auth policy | Verify secrets and permissions per JDK/Cassandra version; never disable auth |
| TLS handshake error | Bad cert, hostname mismatch, truststore, or protocol | Fix chain/trust/hostname; never disable TLS |
| `/metrics` not listening | Agent not loaded, bad JVM option, exporter/rule error | Check startup logs, agent JAR path, and listener config |
| `/metrics` returns HTTP 200 but Cassandra metrics missing | MBean pattern mismatch, renamed MBean, filtered rule | Compare real ObjectNames against rules in a lab |
| Metric off by huge unit factor | Microseconds read as milliseconds, counter/gauge mismatch | Check MBean attribute units and exporter mapping |
| Prometheus `up=0` | HTTP scrape failure, network, or target down | Check target health, DNS, TLS/auth, and ACLs |
| No targets discovered | Discovery/collector config error or metric renamed | Check service discovery, exporter, and mapping rules |
| Node healthy but dashboard blank | Collector/exporter outage or missing series | Distinguish telemetry loss from zero traffic |
| Cassandra JVM load jumps after enabling metrics | Scrape interval too tight or overly broad rules | Trim scrape frequency/rules, measure overhead, re-rollout |

### Three-layer troubleshooting flow

1. **Cassandra/JMX layer:** do the MBeans exist, does local JMX work, and can an authorized operator read the attributes?
2. **Exporter layer:** does the agent/standalone process connect, serve `/metrics`, and emit accurate names and units?
3. **Collector/dashboard layer:** is `up=1`, is Prometheus ingesting samples, and are labels/recording rules/dashboard permissions correct?

Never raise Prometheus scrape timeouts indefinitely when scrapes are slow; identify which MBeans or rules are driving scrape cost and cardinality.

## 18. Java example: reading a JMX attribute in a lab

In **Java**, the standard `javax.management` API can query an MBean from another JVM if a connector is configured and authorized. This is an **authorized diagnostic tool**, not a pattern for production application services to open JMX connections to Cassandra.

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class LocalCassandraJmxProbe {
    public static void main(String[] args) throws Exception {
        // Run only on a lab host where loopback JMX is permitted.
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"
        );

        // If TLS/auth is required, configure connector via secure
        // environment settings and secrets for your exact version.
        try (JMXConnector connector = JMXConnectorFactory.connect(url)) {
            MBeanServerConnection server =
                connector.getMBeanServerConnection();

            ObjectName latencyBean = new ObjectName(
                "org.apache.cassandra.metrics:" +
                "type=ClientRequest,scope=Read,name=Latency"
            );

            if (!server.isRegistered(latencyBean)) {
                System.out.println("MBean not available in this version");
                return;
            }

            Object count = server.getAttribute(latencyBean, "Count");
            System.out.println("Read latency observation count = " + count);
        }
    }
}
```

This is a **read-only** attribute lookup; it invokes no state-mutating operations. `Count` represents the observation count on the timer MBean when provided by that Cassandra version. Never assume identical ObjectNames or attributes exist across all versions.

**Security:** the example connects to `127.0.0.1` with no hardcoded credentials. For remote connections, enforce authentication, TLS, and least privilege using official mechanisms. Never build a public API that lets users pass arbitrary ObjectNames or JMX operation names to invoke against Cassandra.

For Java Driver application metrics, instrument the service directly (e.g., Micrometer/OpenTelemetry) instead of opening JMX connections to the cluster per API request.

## 19. Choosing dashboards and alerts from operational goals

A useful JMX dashboard supports **concrete actions**, not hundreds of decorative lines.

| Operational question | Observation source | Suggested alert/investigation |
|---|---|---|
| Which node is unresponsive? | Node reachability, `nodetool`, exporter health | Check topology, RF/CL, and node health |
| Why did read p99 rise? | App/driver latency, ClientRequest, table/JVM metrics | Drill down coordinator → replica → table/disk/GC |
| Which table has tombstone pressure? | Table MBeans, sampled tracing | Check TTL, DELETEs, partitions, and compaction |
| Is compaction falling behind writes? | Compaction pending/throughput, disk I/O | Review workload, disk saturation, and strategy |
| Is the metric collector broken? | `up`, scrape duration/errors | Fix exporter/collector before drawing conclusions |
| Is any node low on disk headroom? | OS exporter, Cassandra disk usage | Check volumes, snapshots, SSTables, backlogs |
| Do repairs impact requests? | Repair/streaming, node metrics, app SLOs | Annotate repair runs alongside p99/errors |

**Do not alert purely on transient spikes or dips.** A few seconds of high CPU is not an incident if request latency stays stable; a blank dashboard does not mean zero traffic. Prioritize user-facing SLOs, baseline-calibrated thresholds, sustained duration, and runbooks.

### Ensure post-incident investigability

Retain metrics long enough to correlate with deployments, schema changes, repairs, compactions, and topology shifts. Remember that Prometheus metric retention is **separate** from Cassandra data TTL; do not assume both lifecycles share one setting.

## 20. Phased rollout workflow for a safe exporter deployment

A sound rollout follows a clear sequence:

1. **Inventory versions:** Cassandra/JDK versions, JMX mode, actual ports, MBean names, and administrative policy.
2. **Select architecture:** in-node Java agent vs standalone exporter; avoid remote JMX if unnecessary.
3. **Define network boundaries:** nodes, exporters, collectors, datacenters, and permitted ingress/egress paths.
4. **Enforce least privilege** for JMX and metrics, using TLS/auth over networks, secret rotation, and dashboard RBAC.
5. **Author minimal mapping rules:** request rate/errors, latency, compaction, thread pools, table SSTables/tombstones, JVM/GC.
6. **Test on a canary node:** verify `/metrics`, labels, counter/gauge types, units, and scrape overhead.
7. **Test failure modes:** exporter down while Cassandra stays up, collector scrape outage, bad credentials, MBean renames across upgrades.
8. **Roll out safely** by rack/datacenter; if JVM restarts are required, follow RF/CL requirements and maintenance windows.
9. **Monitor continuously:** scrape failures, JMX auth failures, cardinality, CPU/heap overhead, Prometheus storage, and alert noise.
10. **Maintain a runbook:** who has access, how to check local JMX, where secrets live, how to roll back the agent, and how to revoke access.

In production clusters, even a small monitoring config change may require a node restart or security policy update. **Never restart all replicas in a datacenter simultaneously** just to enable an exporter; always follow an RF/CL-safe rolling maintenance plan.

## 21. Scenario exercises and answers

**Question 1.** Is JMX a read-only metrics protocol safe to expose publicly on the Internet?

**Answer:** **No.** JMX can expose administrative MBean operations. Enforce network isolation, auth/TLS, and authorization; prefer leaving remote JMX disabled when not needed.

**Question 2.** Why does `nodetool status` succeeding on a node not prove remote JMX is properly secured?

**Answer:** `nodetool` may connect locally over loopback or a local config. Whether a remote listener, firewall, credentials, and TLS are properly secured is a separate question.

**Question 3.** Prometheus on host A targets `127.0.0.1:9404`, while the exporter listens on host B. Why does scraping fail?

**Answer:** `127.0.0.1` on A refers to A itself, not B. Scraping requires a routable path over a secure monitoring network, or a collector sharing the appropriate network namespace.

**Question 4.** A client reaches the JMX registry port, yet the RMI session still fails. What are the common causes?

**Answer:** RMI may advertise a different hostname or port; firewall/NAT rules, bound host address, TLS, or connector configuration may be mismatched.

**Question 5.** `/metrics` returns HTTP 200 without the expected `ClientRequest` series. Can you conclude Cassandra is handling zero requests?

**Answer:** **No.** Check MBean names, exporter rules, `Count` attribute mapping, collector config, and version differences before concluding.

**Question 6.** Can you attach every `session_id` as a Prometheus label to track slow queries per user?

**Answer:** You should not. It causes severe cardinality explosion and may expose sensitive data; use bounded operation names and controlled logs/traces for specific IDs.

**Question 7.** Why can you not average p99 latency MBean values from three nodes to get cluster p99?

**Answer:** Percentiles are non-linear. You need an aggregatable histogram/distribution or per-node p99 inspection.

**Question 8.** When using an in-JVM Java agent on Cassandra, do you still need remote JMX open for Prometheus to collect metrics?

**Answer:** **Not necessarily.** The agent reads MBeans internally and serves its own HTTP metrics endpoint. That HTTP endpoint and scrape path must still be secured.

**Question 9.** If the JMX exporter hits a TLS error, should you disable TLS/authentication to keep monitoring running?

**Answer:** **No.** Troubleshoot certificates, hostnames, truststores, secrets, and protocol compatibility; never downgrade security to bypass connection errors.

**Question 10.** Does `up=0` in Prometheus mean the Cassandra node has stopped serving CQL?

**Answer:** **No.** Only the exporter, proxy, or collector may be failing. Verify node health and the client CQL path independently.

**Question 11.** Why can enabling every JMX MBean in the exporter slow down Prometheus?

**Answer:** Overly broad mappings generate excessive series and labels, increasing scrape, network, CPU, and storage costs; select metrics purposefully.

**Question 12.** Why should a dashboard service account not share remote JMX admin credentials with SREs?

**Answer:** Dashboard viewers only need metric read access. Administrative JMX credentials can invoke cluster-mutating operations; sharing them violates least privilege and weakens auditing.

---

**Remember:** JMX exposes **MBeans and attributes/operations** inside Cassandra's JVM; exporters translate selected attributes into **metrics** for collectors and dashboards. **Remote JMX is an administrative surface**, never equivalent to read-only HTTP `/metrics`. Prefer local JMX or an in-process agent where suitable, enforce network controls, auth/TLS, least privilege, and secret protection on every path. When building observability, verify **ObjectNames, metric types, units, labels, cardinality, and collector health** before using them to judge node, keyspace, table, or application-request status.

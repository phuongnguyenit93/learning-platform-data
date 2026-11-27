# Firewall Logging and Reviewing Blocked Traffic

In a Google Cloud environment, an application may deploy successfully on Compute Engine or GKE yet still fail to reach a database, internal API, or management service. When that happens, a `timeout` message is not enough to tell whether the cause is a **firewall denial**, **incorrect routing**, a **non-listening service**, or an **authentication failure**. Operations teams need evidence showing which connections were permitted, which were blocked, and which rule produced that decision.

Google Cloud's **Firewall Rules Logging** provides logs of network connections matching firewall rules with logging enabled. This enables administrators to investigate incidents, audit overly permissive rules, verify that unauthorized flows are blocked, and monitor post-deployment changes.

This lesson belongs to the **Network Security and Access** chapter in the **CLOUD_PROVIDERS_GCP** module, connecting knowledge of IAM, VPC, and routing with Compute Engine, GKE, Cloud Run, storage, and database workloads. The focus is on **network-layer blocked traffic**, how to collect evidence, and how to respond in a controlled manner.

After this lesson, you will be able to:

1. Distinguish Firewall Rules Logging, VPC Flow Logs, Cloud Audit Logs, and application logs.
2. Explain why a blocked connection might produce **no** firewall log.
3. Enable logging on appropriate VPC firewall rules, identify the active governing rule, and read key log fields.
4. Write Cloud Logging filters by `DENIED`, source/destination IP, port, network, timestamp, and rule.
5. Audit blocked flows without overly broadening access, then re-test both valid flows and flows that should be denied.
6. Design log retention, access permissions, and investigation workflows aligned with security, reliability, and cost requirements.

## 1. What Does the Firewall Decide Before Logging Occurs?

VPC firewalls control supported traffic types arriving at or leaving network resources based on **direction (ingress/egress)**, **protocol and port**, **source/destination**, **target**, and rule/policy **priority order**. Routing answers "where to send packets?", whereas the firewall answers "is traffic permitted along that path?".

Example:

~~~mermaid
flowchart LR
    WEB["Web VM<br/>10.10.1.10"] -->|"TCP 8080"| FW["Firewall evaluation<br/>at destination workload"]
    FW -->|"ALLOW"| API["API VM<br/>10.10.2.10"]
    FW -->|"DENY"| DROP["Denied"]
    FW -. "Rule has logging enabled" .-> LOG["Cloud Logging<br/>Firewall Rules Logging"]
~~~

The diagram only illustrates the logic for a connection matching a rule with logging enabled; not every denial produces a log entry. A request can fail before reaching the expected rule, or be decided by a higher-priority policy.

### 1.1. Concepts to Distinguish

| Concept | Meaning | Example |
| --- | --- | --- |
| **Ingress** | Traffic entering the protected target. | Client calls TCP 8080 on the API VM. |
| **Egress** | Traffic leaving the protected target. | VM calls TCP 443 to a service outside the VPC. |
| **ALLOW** | Rule permitting traffic that meets its criteria. | Only the Web subnet may call the API on port 8080. |
| **DENY** | Rule rejecting traffic that meets its criteria. | Block the test network from calling the database on port 5432. |
| **Priority** | Parameter determining rule precedence per evaluation mechanism and policy tier. | A specific rule may take precedence over a broad rule within the same evaluation tier. |
| **Target** | Set of resources to which the rule applies. | VMs carrying the selected network tag or service account. |
| **Firewall logging** | Records details about connections evaluated by a rule with logging enabled. | Log contains disposition `DENIED` and the referenced rule. |

Google Cloud provides **VPC firewall rules**, **hierarchical firewall policies**, and **network firewall policies**. Creation and management syntax differ, so during an investigation you must examine the **effective policy evaluation order**, not just the direct rule list in the project. For each policy type, check supported logging capabilities and IAM permissions.

### 1.2. Implied Rules and Why "No Log" Does Not Tell the Whole Story

A VPC has implied behaviors, commonly summarized as:

- **Implied deny ingress:** when no matching allow rule exists, inbound connections may be blocked.
- **Implied allow egress:** unless restricted by another rule/policy, outbound traffic is permitted by default.

These **implied rules** are not ordinary rules on which you can directly turn on Firewall Rules Logging. Therefore, **a connection rejected by implied deny ingress may generate no firewall log**. Similarly, if a connection is permitted by implied allow egress, you will not get a record from "enabling logging on the implied rule."

To capture a set of blocked connections for investigation, you may need to create an appropriately scoped **explicit deny rule**, enable logging, and verify that the rule is actually the one deciding the traffic. Never create a deny rule purely to log traffic on a critical path without evaluating its impact.

### 1.3. Logging a "Rule Match" Differs from Logging Every Packet

Firewall Rules Logging records information about **connections** per product behavior, particularly for supported protocols like TCP and UDP. It should not be mistaken for a per-packet capture tool, payload collector, or complete log of every HTTP request.

Practical implications:

- Logs typically provide network **metadata** and the `ALLOWED` or `DENIED` disposition; they do not automatically contain HTTP body content, cookies, or SQL queries.
- A long-lived connection or multiple retries may generate records differently from a single request; **do not use log line counts to accurately count HTTP requests or packets**.
- If traffic does not traverse a component supported by logging, or matches another rule/policy without logging enabled, you may not see the expected entries.
- Logs can arrive in Cloud Logging with some delay; verify time ranges, log viewing permissions, log buckets, and filters before concluding "there was no traffic."

## 2. Comparing Log Sources During Network Incident Investigations

No single log source explains every connectivity failure. The table below helps choose the right source of evidence.

| Source | What it reflects | When to use | Limitations |
| --- | --- | --- | --- |
| **Firewall Rules Logging** | Match decision of a firewall rule with logging enabled, plus connection/rule details. | Need to know which rule **DENY**ed or **ALLOW**ed a flow. | Not packet capture; implied rules do not directly emit logs; requires a rule with logging enabled. |
| **VPC Flow Logs** | Network flow telemetry provided via sampling/collection. | Observe traffic trends, sources/destinations, and traffic volume. | Sampled and aggregated; not complete proof of every deny. |
| **Cloud Audit Logs** | Who/what changed configuration or invoked admin APIs per audit log type. | Investigate who modified firewalls, VPCs, IAM, or related resources. | Does not replace per-connection network decision logs. |
| **Cloud Armor request logs** | HTTP(S) security policy decisions at the load balancer per configuration. | Investigate WAF, IP filtering, or rate limiting on web requests. | Not the VPC firewall on a VM's NIC. |
| **Application / OS logs** | Socket errors, timeouts, TLS failures, authentication, application errors. | Verify whether the server is listening and whether the app responded. | May not know which VPC firewall blocked the connection. |
| **Connectivity Tests** | Path, routing, and firewall config analysis per tool capabilities. | Locate potential blocking points along a specific path. | Static analysis does not replace observing live requests or app health. |

For example, if a client receives HTTP 403: if Cloud Armor rejected the request at the load balancer, look for evidence in **load balancer/Cloud Armor logs**. An application `403` can also stem from API authorization. Never assume every `403` comes from the VPC firewall; a VPC firewall **DENY** normally fails the connection at the network layer and often manifests as a timeout.

### 2.1. Scope Across Compute Engine, GKE, and Managed Services

- **Compute Engine:** firewall rules and policies targeting VM NICs/destinations are the standard place to investigate connectivity.
- **GKE:** node traffic, Pod traffic, and network policies must be analyzed according to the **cluster networking model**. VPC firewalls do not replace Kubernetes NetworkPolicy or specific pod protection modes.
- **Cloud Run:** inbound serverless connections, VPC egress, and HTTPS ingress have their own mechanisms. Do not assume every Cloud Run request produces VPC firewall rule logs like a VM.
- **Cloud SQL:** private connectivity paths, connectors, IAM database authentication, and database permissions are separate layers. Firewall Rules Logging can help analyze the relevant network portion, but will not tell you a SQL statement failed due to missing `GRANT`.
- **Load balancing and CDN:** a request may be blocked by an L7 policy or served at the edge before reaching the backend. Cross-check logs from the component that actually handled the request.

In multi-tier architectures, identify the **decision point** of the failure before choosing where to look for logs.

## 3. Preparation Before Enabling Firewall Rules Logging

### 3.1. Choosing Which Rules to Log

Logging **every** rule in a high-throughput system can generate substantial data volume. Prioritize where logs serve a clear operational or security decision:

1. **Explicit denies** protecting databases, production environments, or sensitive data zones.
2. **Sensitive allow rules** for SSH, RDP, administrative systems, or critical data paths, to detect anomalous access.
3. **Newly modified rules** needing monitoring during a validation window to confirm legitimate apps continue working.
4. **Controlled egress paths** when auditing connections to restricted IPs/ports.
5. **Rules under investigation** during `timeout` reports or architecture changes where live behavior is unclear.

For high-volume allow rules, weigh log costs, retention periods, filters, or alternative observability options. **Enabling logging does not alter ALLOW/DENY decisions**, but it does change the volume of data sent to Cloud Logging.

### 3.2. IAM Permissions and Resource Scope

To perform these tasks, the identity needs appropriate permissions:

| Task | Permission / approach |
| --- | --- |
| View VPC firewall rules configuration | Role with read access to Compute Engine firewalls, such as an appropriate network viewer role. |
| Enable/disable logging or edit rules | Principal with permission to update firewall rules, e.g., a network security admin role scoped appropriately. |
| Read logs in Cloud Logging | Log reader role such as `roles/logging.viewer` within authorized scope, plus extra permissions if required by log type/access conditions. |
| View IAM/firewall config changes | Permission to view Admin Activity audit logs and related resource details. |
| Edit log retention, sinks, buckets | Separate Cloud Logging management permissions per data governance assignment. |

**Separation of duties:** engineers viewing and analyzing logs typically do not need permission to alter firewalls. Operators allowed to edit firewalls do not automatically need permission to delete sinks, shorten retention, or destroy audit evidence. IAM at project, folder, or organization level can be inherited; always check **effective permissions**.

### 3.3. Capturing Baseline State

Before modifying a rule, record baseline details for comparison:

- Project ID, VPC, region/subnet, and target VM/resource.
- Rule name and rule/policy type, ingress/egress direction, priority, ALLOW/DENY.
- Source/destination ranges, target tags/service accounts, protocol/port, and related criteria.
- Current logging flag, target log bucket, and observation window.
- Application owner, valid business flows, and rollback steps if the rule is modified.

Avoid changing firewall behavior and enabling logging in the exact same step when your primary goal is to measure current behavior. If both must change, document both changes explicitly and test independently.

## 4. Enabling Logging on a VPC Firewall Rule

This section uses standard **VPC firewall rules** and illustrative gcloud commands. For hierarchical firewall policies or network firewall policies, rule management syntax differs; consult the corresponding documentation rather than using VPC firewall-rules commands.

### 4.1. Inspect Existing Rule

In Cloud Shell or Bash configured with gcloud:

~~~bash
export PROJECT_ID="YOUR_PROJECT_ID"
export RULE_NAME="deny-app-to-db"

# Read-only: select the right project and inspect the rule
gcloud config set project "$PROJECT_ID"
gcloud compute firewall-rules describe "$RULE_NAME" \
  --format="yaml(name,network,direction,priority,disabled,denied,allowed,sourceRanges,targetTags,logConfig)"
~~~

`YOUR_PROJECT_ID` and `deny-app-to-db` are placeholder values. Confirm the rule belongs to the **right VPC** and targets the **right resource group** before making writes. If the rule does not exist, do not create an ad-hoc rule with that name in production.

### 4.2. Enable Logging on an Approved Rule

~~~bash
# Write operation: run only on a firewall rule you own
gcloud compute firewall-rules update "$RULE_NAME" \
  --enable-logging

# Read back after update
gcloud compute firewall-rules describe "$RULE_NAME" \
  --format="yaml(name,network,direction,priority,logConfig)"
~~~

In the Console, you can navigate to **VPC firewall rules**, select the target rule, edit **Logs/Logging**, and save. Menu locations may vary across UI updates and policy types.

The `logConfig` block confirms whether logging is enabled. Some logging options also let you select **included metadata**, depending on rule/policy type; verify support and impact on storing sensitive metadata.

If you simply want to **disable logging** after completing an investigation, run:

~~~bash
# Write operation; does not change the rule's ALLOW/DENY behavior
gcloud compute firewall-rules update "$RULE_NAME" \
  --no-enable-logging
~~~

When logging is disabled, previously collected logs still follow Cloud Logging retention and access controls; disabling logging does not delete historical records.

### 4.3. Creating an Explicit Deny with Logging in a Lab Environment

To observe `DENIED` logs, learners can use an **authorized** test VPC and VMs without affecting production. The illustrative example below assumes:

- VPC named `lab-sec-vpc`.
- Source VM with an IP in `10.90.10.0/24`.
- Destination VM with network tag `lab-sec-db` listening on TCP 8080.
- No higher-priority policy or rule deciding this flow differently.

~~~bash
# Run ONLY in an authorized LAB PROJECT after verifying VPC/tag/IP
gcloud compute firewall-rules create lab-deny-db-8080 \
  --network=lab-sec-vpc \
  --direction=INGRESS \
  --priority=900 \
  --deny=tcp:8080 \
  --source-ranges=10.90.10.0/24 \
  --target-tags=lab-sec-db \
  --enable-logging
~~~

This rule not only logs traffic—it **blocks** matching connections. Creating it by mistake in a live environment causes real user impact. Always use an isolated lab VPC, verify source/target, and plan rule cleanup after the exercise.

An action from the source VM such as:

~~~bash
# Run INSIDE the lab source VM; replace with actual destination IP
curl -v --connect-timeout 3 --max-time 5 \
  http://10.90.20.10:8080/
~~~

is expected to fail due to the firewall **if** the flow traverses the newly created rule. A timeout alone **is not conclusive proof**: check for a `DENIED` log or analyze effective policies/rules to confirm the root cause.

After practice, delete only the rule created by the lab:

~~~bash
gcloud compute firewall-rules delete lab-deny-db-8080 --quiet
~~~

Perform deletion in the exact lab project; if unsure whether a rule belongs to the lab, inspect it first before cleaning up. Deleting the rule does not open all traffic to the destination VM; implied deny ingress and other rules/policies still remain.

## 5. Reading and Interpreting a Firewall Rules Logging Record

Depending on connection type and log entry, a log may contain fields such as:

| Common field | How to read it | Analysis pitfalls to avoid |
| --- | --- | --- |
| `timestamp` | Time the event was recorded. | Do not treat `receiveTimestamp` as the exact time the packet was transmitted. |
| `logName` | Log source in Cloud Logging. | Do not confuse with audit logs or application logs. |
| `resource.type`, `resource.labels` | Attached resource, e.g., subnetwork/project. | Do not assume it is the destination VM name; inspect instance metadata as well. |
| `jsonPayload.disposition` | Evaluation outcome, typically `ALLOWED` or `DENIED`. | `DENIED` means traffic matched a deny rule, not an application login failure. |
| `jsonPayload.connection.src_ip` | Source IP of the recorded connection. | May be a post-NAT/proxy IP; verify the observation point. |
| `jsonPayload.connection.dest_ip` | Destination IP of the connection. | May be an internal IP rather than the hostname entered by the user. |
| `jsonPayload.connection.src_port` | Source port. | Ephemeral client ports vary per connection. |
| `jsonPayload.connection.dest_port` | Destination port. | Essential to distinguish SSH 22, HTTPS 443, database 5432, etc. |
| `jsonPayload.connection.protocol` | Numeric IP protocol identifier recorded, e.g., TCP 6, UDP 17. | Do not assume the displayed value is always the string `TCP`/`UDP`. |
| `jsonPayload.rule_details` | Details of the deciding rule, potentially including reference, direction, priority, action. | Do not infer full multi-layer policy order from a single field alone. |
| `jsonPayload.instance`, `jsonPayload.vpc` | Additional VM/VPC metadata when present. | Metadata richness varies by configuration and scenario. |

An **illustrative** log record, abbreviated with anonymized identifiers:

~~~json
{
  "timestamp": "2026-11-19T01:15:00Z",
  "logName": "projects/lab-project/logs/compute.googleapis.com%2Ffirewall",
  "resource": {
    "type": "gce_subnetwork"
  },
  "jsonPayload": {
    "disposition": "DENIED",
    "connection": {
      "src_ip": "10.90.10.10",
      "dest_ip": "10.90.20.10",
      "src_port": 51642,
      "dest_port": 8080,
      "protocol": 6
    },
    "rule_details": {
      "reference": "network:lab-sec-vpc/firewall:lab-deny-db-8080",
      "direction": "INGRESS",
      "priority": 900,
      "action": "DENY"
    }
  }
}
~~~

This example is for practicing field interpretation, **not an actual captured Google Cloud log**. Real schemas and metadata may vary by rule type, environment, and logging configuration.

**Interpretation:** a TCP connection (protocol 6) from `10.90.10.10` to `10.90.20.10:8080` was denied on ingress by the referenced rule. Cross-check the IPs against subnets, NICs, VM names, destination resources, and the exact timestamp to determine whether a legitimate flow was mistakenly blocked or unwanted access was properly stopped.

### 5.1. Meaning of Source and Destination with NAT or Load Balancers

IPs appearing in logs reflect connection details at the **observation point where the product records them**. When load balancers, proxies, Cloud NAT, private connectivity, or multiple NICs are involved, observed source/destination IPs can differ from the original browser IP.

For example, when an Internet user calls an HTTPS load balancer: backend VPC firewall logs may show connections from the load balancer/proxy infrastructure to the VM, not necessarily the end user's IP at the network layer. To investigate which user sent the request, correlate with **load balancer request logs**, trusted headers processed by the system, and application logs.

### 5.2. A DENIED Disposition Can Be Expected Behavior

Not every `DENIED` log indicates an outage. A well-designed firewall **intentionally rejects** out-of-policy flows:

- Web tier must not access the database directly.
- VMs in a test network must not call production environments.
- The Internet must not open direct SSH sessions to private backends.
- A workload that only calls an API over TCP 443 may have unneeded egress ports blocked.

During audits, classify `DENIED` entries into **legitimate policy enforcement**, **legitimate traffic blocked by mistake**, and **anomalous activity needing investigation**. Simply driving DENIED log counts down is not a security goal.

## 6. Finding Blocked Traffic in Cloud Logging

Two convenient methods exist: using **Logs Explorer** in the Cloud Console for visual filtering, or **gcloud logging read** for repeatable queries during incident response. The examples below assume you have log viewer permissions, Firewall Rules Logging is enabled on the active rule, and records are routed to a location you can access.

### 6.1. Basic Query in Logs Explorer

Open **Logging → Logs Explorer**, select the proper project and time range, and enter the filter:

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
~~~

Matching results show Firewall Rules Logging entries on that log source with a deny disposition. `log_id()` filters by log ID without spelling out the full project-scoped log name, though you still must select the right project/log scope.

**Common filters:**

**Blocks from a specific source IP:**

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
jsonPayload.connection.src_ip="10.90.10.10"
~~~

**Blocks to a specific destination IP/port:**

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
jsonPayload.connection.dest_ip="10.90.20.10"
jsonPayload.connection.dest_port=8080
~~~

**Search a specific rule by partial reference:**

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.rule_details.reference:"lab-deny-db-8080"
~~~

In Logging filters, `:` typically performs substring/has-value matching, while `=` performs exact equality matching per the Logging query language. When a field does not exist in the inspected log entry type, filtering on that field returns no results even if other entries exist. Start with the three basic lines and add conditions step by step.

### 6.2. Narrowing by Time and Observation Scope

During incidents, users often report: "At 10:15 AM today it couldn't connect." Do not search the entire day and blame every DENIED on that error. Convert to **UTC or a consistent display timezone**, then inspect a few-minute window around the event:

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
timestamp>="2026-11-19T03:10:00Z"
timestamp<="2026-11-19T03:20:00Z"
~~~

The timestamp range above is purely for syntax illustration. Before querying, substitute the verified incident timestamp. Compare `timestamp` and `receiveTimestamp` if you suspect delayed delivery to Cloud Logging.

When applications run in a **Shared VPC**, the workload project and the network host project may differ. Check where logs are actually written, viewing permissions, log scope, log sinks, and centralized log storage rather than picking only the project whose name resembles the application.

### 6.3. Reading Logs with gcloud

Bash/Cloud Shell example:

~~~bash
export PROJECT_ID="YOUR_PROJECT_ID"

# Read-only: fetch up to 30 firewall-denied log records
gcloud logging read \
  'resource.type="gce_subnetwork" AND log_id("compute.googleapis.com/firewall") AND jsonPayload.disposition="DENIED"' \
  --project="$PROJECT_ID" \
  --limit=30 \
  --format=json
~~~

To display only key fields, format the output:

~~~bash
gcloud logging read \
  'resource.type="gce_subnetwork" AND log_id("compute.googleapis.com/firewall") AND jsonPayload.disposition="DENIED"' \
  --project="$PROJECT_ID" \
  --limit=30 \
  --format="table(timestamp,jsonPayload.connection.src_ip,jsonPayload.connection.dest_ip,jsonPayload.connection.dest_port,jsonPayload.rule_details.reference)"
~~~

These commands are **read-only**; they do not alter firewalls. If no results return, the filter may be too narrow, permissions/log scope may be wrong, or no matching records exist. Never grant Administrator permissions or change policies simply because a query returned empty results.

### 6.4. Tracing a DENIED Log Back to the Deciding Rule

Suppose you find a log entry:

~~~text
10.90.10.10:51642 -> 10.90.20.10:8080 TCP
disposition: DENIED
rule: lab-deny-db-8080
direction: INGRESS
priority: 900
~~~

Answer these questions in order:

1. **What is the source?** Does `10.90.10.10` belong to a subnet/VM/Pod or a NAT path? Should this workload be calling that destination?
2. **What is the destination?** Is `10.90.20.10` the exact VM and NIC of the failing service? Is it actually listening on TCP 8080?
3. **What was the rule's intent?** Was `lab-deny-db-8080` created to protect the Data tier or as a temporary incident block?
4. **Is the flow valid by design?** If Web is only allowed to call App and not Data, a blocked Web → Data connection is the expected result.
5. **Were there recent changes around the failure time?** Cross-check firewall edits, deployments, IPs, DNS, routes, service accounts, network tags, and app configs via audit/config history.
6. **What is the right action?** Keep the deny, fix the client to call the proper endpoint, or propose a scoped rule change with approval.

If a firewall update is genuinely needed, prioritize **allowing only the exact source, destination, protocol/port**, and target resource. Never fix timeouts with an `ALLOW all` rule from `0.0.0.0/0`.

## 7. Procedure for Investigating Connectivity Incidents with Blocked Traffic

A reusable workflow for dev, staging, or production environments:

~~~mermaid
flowchart TD
    START["Connectivity error reported<br/>source, destination, port, time"] --> OBS{"Matching Firewall Rules Log<br/>found?"}
    OBS -->|Yes: DENIED| RULE["Identify rule/policy<br/>and target resource"]
    OBS -->|No| OTHER["Check implied deny,<br/>priority, log scope, routing,<br/>service, and other layers"]
    RULE --> EXPECT{"Connection permitted<br/>by design?"}
    EXPECT -->|No| KEEP["Keep block; classify event<br/>and increase monitoring if needed"]
    EXPECT -->|Yes| FIX["Propose minimal change<br/>with approval"]
    FIX --> TEST["Re-test positive<br/>and negative cases"]
    OTHER --> TEST
    TEST --> END["Record evidence,<br/>monitor, and close incident"]
    KEEP --> END
~~~

### 7.1. Step 1 — Gather Connection Facts

A well-formed investigation ticket should capture:

| Attribute | Example |
| --- | --- |
| Failure time (with timezone) | 10:15 ICT, 2026-11-19 |
| Client/source | VM `web-01`, IP `10.10.1.10` |
| Destination | VM `app-01`, IP `10.10.2.10` |
| Protocol/port | TCP 8080 |
| Project/VPC/subnet | `shop-prod` / `prod-vpc` / `app-subnet` |
| Business expectation | Web is allowed to call internal API |
| Observed result | `curl` timed out after 5 seconds |
| Test attempts and trace ID | If available, helps correlate with application logs |

Not all logs contain every attribute above. Some details must be gathered from the reporter, deployment configs, and network management tools.

### 7.2. Step 2 — Search for DENIED, Then Inspect Effective Policy

Filter by time range, IP, port, and `DENIED`. If logs exist, read `rule_details` and inspect the rule where it is managed. Then cross-check:

- VPC scope, ingress/egress direction, and rule target.
- Priority and upper policy layers, including related denies/allows.
- Whether the network resource changed network tags or service accounts in a recent deploy.
- Whether source ranges shifted due to autoscaling, proxies, NAT, GKE nodes, or subnet configs.
- Whether that rule actually caused the outage or the DENIED entry was unrelated scanning traffic.

If source/destination passes through a load balancer or managed endpoint, also inspect logs of the intermediary component. Never draw conclusions from an IP without knowing whether it belongs to a client, proxy, or backend.

### 7.3. Step 3 — What to Check When No DENIED Log Appears

**Finding no logs is not proof that the firewall allowed the traffic.** Check in order:

1. Did the suspect rule have **logging enabled** and was it active at the time of failure?
2. Was traffic dropped by **implied deny ingress** with no explicit logged deny rule?
3. Was a **higher-precedence rule or hierarchical/network firewall policy** evaluated earlier so the inspected rule never matched?
4. Did the query specify the wrong **project, log scope, log bucket, resource type, time window**, or log type?
5. Were logs filtered by a **router/sink/exclusion**, expired past retention, or hidden due to insufficient log permissions?
6. Did the connection actually traverse the inspected **VPC/NIC**, or stop at Cloud Armor, load balancer, Cloud Run ingress, GKE NetworkPolicy, or the application?
7. Are routing, DNS, NAT, destination host, local firewall, and listening port all healthy?
8. Is there a TLS, database authentication, IAM, or application response error that the user loosely called a "network error"?

For example, when no route exists to the destination IP, traffic may never reach the point where you expect an ingress firewall log. When an application returns HTTP 401 or 403, investigate application-layer authentication/authorization before modifying firewall rules.

### 7.4. Step 4 — Classify and Decide

| Classification | Indicators | Action |
| --- | --- | --- |
| **Correct policy block** | Web calls Data directly even though architecture only permits Web → App → Data. | Keep rule; fix client if calling the wrong target; save design-compliance evidence. |
| **Legitimate traffic blocked** | New rule blocks App → database on an approved port. | Narrow change to minimal scope, review, and run before/after tests. |
| **Anomalous access attempt** | Unlisted IP scanning multiple targets or ports with no business need. | Keep blocked, investigate source, evaluate alerts, and audit related configs/identities. |
| **Insufficient evidence** | No matching logs, connection still times out or fails across layers. | Gather diagnostics, configs, and logs from other components; do not rush rule edits. |

### 7.5. Step 5 — Test Before and After Remediation

A firewall change is complete only when both test suites pass:

**Positive test:** authorized workloads can reach the target IP, port, and protocol, and the application responds validly.

**Negative test:** unauthorized workloads **remain blocked**. Specifically test from another subnet, a VM without the allowed service account, or a direct path that the architecture requires to pass through a gateway.

After the change, record the change ID, old/new rules, impact, timestamp, test results, and approver. Observe logs over a representative application window, because pre-existing established connections can behave differently from **new** connections after a policy change.

## 8. Real-World Scenario: Web Cannot Reach App

A team deploys a course management system:

- **Web tier:** VMs in subnet `10.20.10.0/24`.
- **Application tier:** VMs in subnet `10.20.20.0/24`, listening on TCP 8080.
- **Data tier:** database allowing connections only from the App tier over the designed network path.
- **VPC:** `learning-prod-vpc` with rules restricting inter-tier connectivity.

After a firewall update, users encounter HTTP 502 from Web. The on-call engineer checks from a Web VM:

~~~bash
# Run on the Web VM in accordance with organizational access policy
curl --verbose --connect-timeout 3 --max-time 5 \
  http://10.20.20.10:8080/health
~~~

Suppose the command times out. An illustrative log shows:

~~~text
timestamp: 2026-11-19T04:15:03Z
connection: 10.20.10.12:54230 -> 10.20.20.10:8080 TCP
disposition: DENIED
direction: INGRESS
rule: deny-web-to-app-temporary
~~~

### 8.1. Reading the Evidence

The engineering team confirms three facts before making edits:

1. IP `10.20.10.12` is indeed a Web VM NIC, and `10.20.20.10` is an App VM listening on port 8080.
2. Architecture docs authorize Web to call App on port 8080; Web must not connect directly to Data.
3. Rule `deny-web-to-app-temporary` was recently added near the incident time, applies to the App VM, and logged `DENIED`.

With that evidence, this is **legitimate traffic blocked by mistake**. The system owner and network administrator can propose removing or narrowing the offending rule while preserving the Data-tier denies. The exact fix depends on actual policy ordering: adding an allow rule lower in the evaluation order may **have no effect** if a higher-precedence deny already decides the flow.

### 8.2. Post-Remediation Test Matrix

| Test case | Expected result |
| --- | --- |
| Web VM → App VM TCP 8080 | Succeeds; `/health` responds. |
| Web VM → Data TCP 5432 | Continues to be blocked by design. |
| App VM → Data TCP 5432 | Works if approved business flow and database is ready. |
| Test VM outside Web subnet → App TCP 8080 | Continues to be blocked. |
| Internet → App internal IP | No direct public endpoint; verify hybrid/peering paths if present. |

After testing, the team confirms 502 errors are resolved, `DENIED` logs from the offending rule no longer appear for **new valid connections**, and unauthorized traffic remains blocked. Results are saved in the incident record along with root cause and safeguards to prevent repeat mistakes.

**Design takeaway:** Firewall Rules Logging confirms *which rule* blocked a TCP path, but deciding whether to permit it still rests on architecture, data classification, IAM, and the accountable system owner.

## 9. Long-Term Monitoring, Log-Based Metrics, and Alerting

In large environments, manually reading logs is insufficient. You can create **logs-based metrics** from matching records, then use Cloud Monitoring to visualize trends and trigger conditional alerts.

### 9.1. Choosing Meaningful Signals

| Signal | Why monitor | Interpretation risk |
| --- | --- | --- |
| DENIED to admin ports from unlisted sources | May detect port scanning or unauthorized access attempts. | High counts do not mean a breach succeeded. |
| DENIED from App tier to a critical dependency | May indicate a deployment or IP/firewall change causing an outage. | Correlate with SLOs, traces, and application logs. |
| Sudden spike in DENIED after policy change | Signals risk of accidentally blocking legitimate traffic. | Legitimate traffic spikes can also increase log volume. |
| ALLOWED to sensitive ports from unusual sources | Surfaces **currently permitted** flows needing review. | A firewall allow does not mean application auth succeeded. |
| Count of rules with logging disabled | Detects loss of visibility on paths designated for monitoring. | This is **configuration** data; combine with audit/inventory rather than traffic logs alone. |

A logs-based counter metric might use this filter:

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
jsonPayload.connection.dest_port=22
~~~

This metric counts **log entries matching the filter** processed by the Logging pipeline per policy and timing—not exact packet counts or unique users. Alerts require thresholds tuned to baseline, an evaluation window, and a runbook for handling false positives.

### 9.2. Designing an Actionable Alert

A useful alert specifies:

1. **Condition:** e.g., DENIED count to admin ports exceeding a threshold derived from baseline load.
2. **Scope:** project, VPC, subnet, application, or target group.
3. **Evidence link:** link to Logs Explorer with the right filter and instructions for inspecting details.
4. **Recipient:** networking, security, or on-call team accountable for the flow.
5. **First action:** verify source/destination to tell unauthorized scanning apart from blocked legitimate traffic.
6. **Closure criteria:** resolve the root cause and re-verify positive/negative tests, not merely silencing the alert.

If sustained blocked traffic is identified as known, managed noise, adjust observability policies to reduce alert fatigue. **Never delete blocking rules or turn off all logging just to lower alert counts.**

### 9.3. Log Retention, Log Buckets, and Access Control

Firewall logs can contain IP addresses, VM names, subnets, and operational metadata considered sensitive in certain contexts. When designing log management:

- **Grant read access strictly on a need-to-know basis**, separating network operations, security monitoring, and Logging admin accounts.
- **Select retention based on need:** incident response, security investigations, archival requirements, and data policies. Do not keep logs indefinitely by default.
- **Consider log storage location:** especially when the organization has data residency constraints or centralized log buckets.
- **Reduce unnecessary volume:** consider supported logging metadata levels, log routing, or exclusions. Never accidentally exclude critical DENIED evidence.
- **Track cost:** ingestion, storage, query/routing/export destination costs vary by product and config; verify current pricing.
- **Preserve change evidence:** audit logs for firewall edits, log routing updates, retention changes, and log-view IAM grants.

In a multi-project organization, logs can be routed centrally or to a SIEM via supported mechanisms. Ensure **log sinks, destination IAM, quotas, retention, transport, and organization scope** are properly configured. When logs are dropped by exclusions, historical investigations may lack necessary data.

## 10. Guided Exercise: Evaluating a DENIED Case

Suppose you manage networking for a three-tier application and receive a request from the development team:

> "From the Web VM, we can't call the internal TCP 8080 API. Please open all traffic inside the VPC to test if that fixes the error."

You are given sample facts:

| Fact | Illustrative value |
| --- | --- |
| VPC | `training-prod-vpc` |
| Web subnet | `10.50.10.0/24` |
| App subnet | `10.50.20.0/24` |
| Data subnet | `10.50.30.0/24` |
| Web VM IP | `10.50.10.11` |
| App VM IP | `10.50.20.11` |
| App port | TCP 8080 |
| Data port | TCP 5432 |
| Security requirement | Web must not connect directly to Data |

### 10.1. Tasks

1. Write a Logs Explorer filter to find `DENIED` entries from `10.50.10.11` to `10.50.20.11:8080` during the failure window.
2. List the fields you need to read to determine the rule, traffic direction, priority, and source/destination IPs.
3. If no logs appear, list at least **four causes** to check before requesting a policy change.
4. Assuming a `DENIED` log exists from an explicit deny on the App VM: propose the **minimal** change so Web can validly call the API without opening Web → Data.
5. Write two test cases—one that **must succeed** and one that **must fail**—after the fix.
6. Explain the role of VPC Flow Logs and Cloud Audit Logs in this scenario.
7. Propose a log-based metric to detect anomalous denied connections from App → Data after a release.

### 10.2. Suggested Solution

**Filter for task 1:**

~~~text
resource.type="gce_subnetwork"
log_id("compute.googleapis.com/firewall")
jsonPayload.disposition="DENIED"
jsonPayload.connection.src_ip="10.50.10.11"
jsonPayload.connection.dest_ip="10.50.20.11"
jsonPayload.connection.dest_port=8080
~~~

For task 2, read `timestamp`, `disposition`, `connection`, and `rule_details` (if present), then cross-check effective policies. For task 3, check implied deny, logging disabled, another rule/policy deciding earlier, wrong project/time/log scope, or routing/application errors.

For task 4, you cannot simply say "add an allow rule" while ignoring **priority order**: if the deny has higher priority, a new allow won't take effect. Adjust the policy through an approved workflow to allow **only** Web → App TCP 8080 while keeping Data protected. For task 5, confirm Web → App succeeds and Web → Data continues to fail, adding App → Data succeeds if that is a valid path.

For task 6, VPC Flow Logs helps evaluate traffic trends within collection limits, Cloud Audit Logs helps identify who modified rules; Firewall Rules Logging reports the rule decision for matching connections. For task 7, build a metric on `DENIED` traffic to Data's IP/port and alert when post-deploy volume exceeds baseline.

### 10.3. Self-Check Questions

**1. Does finding no firewall log for a timed-out connection prove the firewall ALLOWed the traffic?**  
No. It could be implied deny, logging disabled, decided by another policy, wrong log filter, or a non-firewall issue.

**2. Can DENIED log counts be used to count the exact number of blocked packets or HTTP requests?**  
No. Firewall Rules Logging is a connection log per product collection behavior, not a packet or HTTP request counter.

**3. Why is an ALLOW rule with logging enabled also worth reviewing?**  
Because spotting **allowed** connections from unexpected sources can reveal rules that are broader than needed, even before any DENIED appears.

**4. Do firewall changes require re-running blocked-flow test cases?**  
Yes. Testing only that the application works again can miss accidentally opening access to other networks.

**5. Why combine Cloud Audit Logs with firewall logs when investigating a new outage?**  
Audit logs help identify configuration changes and the actor/identity behind them, while firewall logs point to the observed network decision.

## Google Cloud Official References

- **Firewall Rules Logging overview:** https://cloud.google.com/firewall/docs/firewall-rules-logging — how logging works, traffic types, and metadata.
- **Use Firewall Rules Logging:** https://cloud.google.com/firewall/docs/using-firewall-rules-logging — enabling/disabling logging and viewing methods.
- **VPC firewall rules:** https://cloud.google.com/firewall/docs/firewalls — evaluation order, ingress/egress directions, and implied rules.
- **Cloud Logging query language:** https://cloud.google.com/logging/docs/view/logging-query-language — Logs Explorer filters.
- **VPC Flow Logs:** https://cloud.google.com/vpc/docs/flow-logs — network flow data, collection limits, and observability.
- **Cloud Audit Logs:** https://cloud.google.com/logging/docs/audit — investigating resource administration actions.
- **Connectivity Tests:** https://cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview — path and connectivity configuration analysis.
- **Cloud Logging pricing:** https://cloud.google.com/stackdriver/pricing — checking Logging costs, storage, and related features.

Technical documentation, Cloud Console UI, supported policy types, and pricing may change. When applying in a live organization, verify permissions, logging configuration, data scope, and approval workflows. A successful audit explains **why a connection was blocked**, proves the remediation is properly scoped, and **preserves the deny controls protecting the system**.

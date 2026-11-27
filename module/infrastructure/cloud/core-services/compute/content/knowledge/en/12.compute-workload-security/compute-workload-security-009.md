# Runtime protection, anomaly detection, and incident response

## Lesson objectives

Workload security does not end once a virtual machine, container, or function is deployed. While an application runs, attackers can exploit vulnerabilities, steal credentials, spawn abnormal processes, alter files, access data, or hijack compute resources for unauthorized activities. Organizations therefore need runtime protection, visibility into live behavior, and response procedures fast enough to contain damage.

After this lesson, you can:

- Apply hardening measures for VMs, containers, Kubernetes, and serverless workloads.
- Distinguish protections across build time, deploy time, and runtime.
- Choose telemetry sources to monitor processes, files, networking, identities, and cloud control-plane activity.
- Build baselines and detect anomalous behavior with context.
- Triage alerts, investigate incidents, and isolate workloads safely.
- Recover services from clean artifacts, fresh credentials, and verified data.

## 1. What is runtime security?

Runtime is the phase when a workload is actively executing. For VMs, runtime encompasses the guest OS, processes, services, kernel, agents, and network connections. For containers, runtime also includes the container engine, runtime class, namespaces, cgroups, capabilities, volume mounts, and orchestration control plane. For serverless, the provider manages most of the underlying runtime, while the user remains responsible for application code, dependencies, configuration, access permissions, and data.

Runtime protection focuses on keeping workloads in an authorized state, observing what is actually happening, and responding when behavior deviates from design.

A security program typically spans three control layers:

| Phase | Core question | Example controls |
|---|---|---|
| Build time | Are artifacts safe before release? | Dependency scanning, image scanning, artifact signing, IaC checks |
| Deploy time | With what permissions and configurations is the workload deployed? | Admission policies, least privilege, network policies, image allowlists |
| Runtime | What actions is the workload performing right now? | EDR, process/file/network telemetry, runtime detection, audit logs |

No single layer replaces the others. A clean image can still be exploited at runtime; a runtime sensor can detect abnormal behavior but cannot fix an overly permissive IAM policy. Combine preventive controls, detective controls, and response controls.

~~~mermaid
flowchart LR
    A["Build: source code and artifacts"] --> B["Deploy: configuration and permissions"]
    B --> C["Runtime: processes, files, network"]
    C --> D["Telemetry and detection"]
    D --> E["Alert triage"]
    E --> F["Containment and investigation"]
    F --> G["Recovery and improvement"]
    G --> A
~~~

## 2. Building a secure workload baseline

A baseline defines the acceptable configurations and behaviors for a workload. A strong baseline aligns with the workload's role, environment, and business requirements. Normal behavior for a web server, database, batch worker, and bastion host differs significantly.

Baseline elements to define:

- Supported OS, kernel, runtime, and versions.
- Permitted processes/services and how they launch.
- Users/groups, service accounts, and resource access permissions.
- Writable directories, configuration files, and data storage paths.
- Permitted inbound/outbound network connections, DNS, and dependent endpoints.
- Typical CPU, memory, disk I/O, and network profiles over time.
- Required logs, retention periods, and workload ownership.
- Update mechanisms, rollback plans, and accountable contacts.

A baseline must not be a static snapshot. Traffic and resource usage vary by hour, day, campaign, or batch window. Record multiple normal load cycles and correlate observability data with application versions, deployment events, and configuration changes.

For example, a queue worker may experience higher CPU and network load during peak hours. Relying solely on a fixed CPU threshold triggers false positives. Combine queue depth, processed message counts, deployment type, and operating schedules to interpret fluctuations.

## 3. Virtual machine hardening

Virtual machines have their own OS boundary but still rely on the hypervisor, base image, networking, and cloud identity. Hardening measures should include:

### 3.1. Operating system and services

- Use approved base images still within their support window.
- Apply security patches for OS, kernel, runtimes, and agents within SLA.
- Remove or disable unneeded services, packages, ports, and accounts.
- Enable Secure Boot or appropriate integrity mechanisms if supported by the instance type.
- Enable host firewalls and permit only required network flows.
- Enforce filesystem permissions, SELinux, or AppArmor where appropriate.
- Synchronize clocks so logs and events from multiple sources correlate accurately.
- Run EDR/endpoint protection compatible with the OS and workload.

### 3.2. Identity and permissions

- Run each service under a dedicated account; avoid local administrator or root unless required.
- Never share credentials across VMs.
- Attach instance roles or managed identities with least privilege.
- Never store long-lived access keys in scripts, images, or configuration files.
- Restrict interactive logins and remote administration rights.
- Monitor changes to admin groups, scheduled tasks, services, and startup items.

### 3.3. Protecting data and configuration

- Encrypt volumes and backups per data policy.
- Restrict write permissions on executable and configuration directories.
- Store secrets in a secret manager and fetch them via workload identity.
- Protect logs from modification or deletion by application accounts.
- Separate data volumes from OS volumes when architecture requires independent recovery.

Audit hardening state periodically and after every image or configuration change. A machine configured cleanly today can drift from baseline after emergency support work or ad-hoc agent installations.

## 4. Container and Kubernetes hardening

Containers package applications cleanly, yet are not an absolute security boundary. Containers share the host kernel; permissions, namespaces, runtimes, and volume configurations directly govern isolation strength.

Common controls include:

| Control | Purpose |
|---|---|
| Run as non-root | Reduces impact if a process inside the container is compromised |
| Read-only root filesystem | Restricts modifications to the container filesystem |
| Drop Linux capabilities | Removes unnecessary kernel privileges |
| Seccomp | Restricts allowed syscalls |
| AppArmor/SELinux | Enforces access policies on processes and files |
| Resource requests/limits | Bounds CPU and memory, limiting impact on sibling workloads |
| NetworkPolicy | Restricts connections across Pods and namespaces |
| Image pinning and signature verification | Prevents running unapproved or tampered images |
| Admission policies | Rejects policy-violating manifests before workloads are created |

Example Kubernetes security context:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-worker
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: worker
      image: registry.example.com/orders-worker:2.4.1
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
      resources:
        requests:
          cpu: 250m
          memory: 256Mi
        limits:
          cpu: "1"
          memory: 512Mi
~~~

Tailor this example to the application. Some processes need to write to temporary directories or require specific capabilities; mount dedicated writable volumes and add back only proven-necessary capabilities. Never enable privileged mode, `hostPID`, `hostNetwork`, or container runtime socket mounts without approved justification.

In Kubernetes, secure both the control plane and nodes:

- Scope RBAC by namespace and resource; avoid `cluster-admin` for application service accounts.
- Disable automatic service account token mounting when workloads do not call the Kubernetes API.
- Enable an appropriate audit policy and ship audit logs centrally.
- Secure kubelet, node OS, container runtime, and cluster access credentials.
- Use NetworkPolicies or equivalents to restrict east-west traffic.
- Protect secrets with encryption at rest and external secret managers.
- Verify image provenance, registry permissions, and admission pipelines.

## 5. Protecting serverless workloads

For serverless functions or services, the provider typically manages the host OS, hypervisor, and parts of runtime infrastructure. Users still must protect:

- Source code, packages, and dependencies.
- Execution roles or service identities.
- Access permissions to event sources, databases, object storage, and secrets.
- Network egress, VPC connectors, and outbound endpoints.
- Environment variables, function layers, and artifacts.
- Triggers, invocation permissions, API authorization, and logging.

Recommended practices:

1. Assign a dedicated execution role per function or group of functions sharing the same responsibility.
2. Permit functions to read/write only strictly required resources.
3. Authenticate event sources and restrict who can invoke functions.
4. Avoid placing long-lived secrets in environment variables when a secret manager fits.
5. Update runtimes and dependencies ahead of provider deprecation dates.
6. Set appropriate timeouts, memory, concurrency, and retry policies to avoid loops or unexpected costs.
7. Monitor unusual invocation patterns, error spikes, and out-of-pattern data access.

Serverless reduces guest OS management burden, yet does not eliminate risks from application code, dependencies, IAM permissions, or spoofed events. Review the specific service's shared responsibility model to know which layers the provider protects.

## 6. Telemetry to collect at runtime

Detecting anomalous behavior requires enough data to answer who did what, on which workload, when, and through which path.

| Telemetry group | Example fields | Signals to watch |
|---|---|---|
| Process | Name, path, parent process, user, command metadata, hash | Unexpected shells or tools spawned from services, unusual process trees |
| File | Create, modify, delete, permissions, owner, hash | Changes to binaries, startup scripts, config files, or sensitive directories |
| Network | Outbound/inbound connections, DNS, destination, port, bytes | Connections to rare hosts, periodic beaconing, sudden traffic spikes |
| Identity | Logins, tokens, role assumptions, privilege changes | Unusual privilege increases, unfamiliar identities, logins from new sources |
| Resource | CPU, memory, disk, process count, network throughput | Usage spikes uncorrelated with business load |
| Container/Kubernetes | Container exec, image, Pod creation, secret access, RBAC changes | Unpipelined containers, interactive shells, privileged Pods |
| Cloud control plane | API calls, resource creation, security group edits, key operations | Infrastructure or permission changes outside change windows |

Typical data sources include:

- EDR/endpoint agents on VMs.
- Linux audit framework, `journald`, system logs, and kernel telemetry.
- Windows Security logs, Sysmon, and Microsoft Defender for Endpoint where deployed.
- Container runtime sensors or eBPF-based sensors.
- Kubernetes audit logs, admission events, and workload metadata.
- Cloud audit trails, IAM logs, flow logs, and threat detection services.
- Application logs, traces, metrics, and business events.

Collect only necessary data and protect logs as sensitive assets. Command lines, file paths, IPs, usernames, and event payloads can contain personal data or internal secrets. Enforce read permissions, retention limits, masking, and log access auditing.

## 7. Detecting anomalous behavior

A single signal rarely confirms an incident. CPU spikes can come from legitimate batch jobs; shell processes can come from maintenance scripts; new outbound connections can come from updates. Detection should correlate multiple signals and context.

### 7.1. Behaviors worth monitoring

**Unusual process execution**

- Child processes rarely seen under a service account.
- Shells or admin tools spawned by a web server, database, or application container.
- Binaries executing from temporary directories, user directories, or paths outside the image.
- Elevated-privilege processes lacking a corresponding change record.

**Persistence or configuration changes**

- New scheduled tasks, cron jobs, systemd services, or startup items.
- Modifications to binaries, SSH authorized keys, Windows services, or registry autoruns.
- Changes to security policies, firewalls, or protection agents.
- Container images or deployments modified outside the pipeline.

**Network and data activity**

- Workloads connecting to rare domains/IPs or regions outside the operating model.
- Sudden outbound traffic surges unexplained by request volume.
- A workload scanning multiple internal addresses or ports.
- An application account reading unusually large volumes of data.

**Identity and privileges**

- Sensitive permissions added to an instance role or service account.
- Tokens or credentials used from an unexpected workload.
- Repeated failed authentications followed by a successful login.
- Unusual spikes in secret or key access.

### 7.2. Incorporating context

To reduce false positives, enrich events with:

- Workload owner, environment, and business criticality.
- Image version, container image digest, and release ID.
- Change windows, deployment events, and approved tickets.
- Service accounts, roles, and expected permissions.
- Baselines by hour, day, and load level.
- Network topology, dependencies, and allowlisted endpoints.

For example: a web container spawns a shell process, then downloads a binary from a new domain and opens an outbound connection to a never-before-seen IP. Three events within a short window warrant far higher investigation priority than any one alone.

~~~mermaid
flowchart TD
    A["Telemetry: process / file / network / identity"] --> B["Normalize and attach workload context"]
    B --> C["Compare against baseline and policy"]
    C --> D{"Anomalous signal?"}
    D -->|No| E["Store logs and continue monitoring"]
    D -->|Yes| F["Correlate multiple signals"]
    F --> G{"Severity and confidence"}
    G -->|Low| H["Monitor / enrich"]
    G -->|High| I["Create incident and respond"]
~~~

### 7.3. Example detection logic

A conceptual detection rule:

~~~text
IF
  workload.role = "web-api"
  AND process.parent = "web-server"
  AND process.name IN ("sh", "bash", "powershell")
  AND NOT event.matches_approved_maintenance
THEN
  raise alert "Unexpected interactive shell from web workload"
  enrich with workload owner, image digest, user and network activity
~~~

This is illustrative logic, not syntax for a specific SIEM/EDR product. When implementing, map real telemetry fields, maintain time-bounded exception lists, and tune thresholds. Never create overly broad exceptions like ignoring every shell across an entire namespace.

## 8. Alert triage and prioritization

Not every runtime alert demands immediate isolation. Operations teams must weigh severity, confidence, and blast radius.

| Priority | Examples | Initial action |
|---|---|---|
| Critical | Production credentials abused, active malware execution, signs of sensitive data exfiltration | Trigger incident response, perform controlled isolation, and notify response team |
| High | Abnormal processes/persistence on critical workloads, evidenced privilege escalation | Investigate immediately, restrict network/identity, and preserve evidence |
| Medium | An isolated unusual signal without proof of compromise, out-of-window change | Enrich telemetry, verify with owner and change records |
| Low | Misconfiguration or baseline deviation with a valid explanation | Document and adjust baselines/policies if warranted |

When triaging an alert, record:

- Affected workload and assets.
- Associated identity or process.
- First-seen and last-seen timestamps.
- Specific behavior, log source, and confidence.
- Potentially impacted data or downstream systems.
- Isolation status and assigned responder.
- Next steps and update deadline.

Never auto-close an alert solely because an owner confirms a deployment occurred. Cross-check image digest, pipeline run, commit, timestamps, and actual behavior.

## 9. Runtime incident response workflow

An incident response workflow typically covers preparation, detection/analysis, containment, eradication, recovery, and lessons learned.

~~~mermaid
flowchart TD
    A["Preparation: owners, logs, runbooks, emergency access"] --> B["Detection and verification"]
    B --> C["Assess scope and severity"]
    C --> D["Containment: controlled isolation"]
    D --> E["Preserve evidence and investigate"]
    E --> F["Eradication: remove root cause"]
    F --> G["Recovery from clean artifacts"]
    G --> H["Monitor for re-compromise"]
    H --> I["Lessons learned and update baselines"]
~~~

### 9.1. Pre-incident preparation

- Designate incident commanders, security contacts, platform owners, and emergency approvers.
- Maintain inventories of VMs, containers, clusters, functions, roles, and dependencies.
- Enable centralized logging, clock sync, and verify queryability.
- Prepare procedures for network isolation, credential revocation, and workload recovery.
- Test runbooks and break-glass access in safe environments.
- Keep clean images, deployment manifests, backups, and restore guides ready.

### 9.2. Verification and scoping

When an alert arrives:

1. Verify the alert originates from trusted telemetry with accurate timestamps.
2. Identify the workload, host, container, namespace, function, and identities involved.
3. Cross-check deployments, change records, owners, and baselines.
4. Trace parent/child processes, modified files, network connections, and identity activity.
5. Check other workloads sharing the same image, role, or credentials for similar signs.
6. Assess what data may have been read, altered, encrypted, or exfiltrated.

Maintain timelines in UTC or one unified time standard so logs across VMs, cloud control planes, EDR, and applications correlate cleanly.

### 9.3. Containment: isolate while preserving investigation capability

The goal is stopping harmful activity and limiting lateral movement. Actions depend on workload type:

- VM: move to a quarantine security group, block egress, or isolate via EDR per playbook.
- Container: stop receiving traffic, isolate via namespace/network policy, or replace replicas with clean workloads after preserving needed evidence.
- Kubernetes: revoke abused service accounts/tokens, restrict networking, and block unapproved rollouts.
- Serverless: temporarily disable triggers, throttle invocations, revoke permissions, or shift to a safe function version.
- Identity: invalidate tokens/sessions, rotate secrets, and revoke role bindings based on impact assessment.

Immediate shutdown or container deletion is not always best, as it can destroy volatile data, process state, and forensic evidence. For severe incidents, coordinate security and platform teams to choose among network isolation, snapshots, memory capture, and shutdown per runbook. If data is actively being exfiltrated or destroyed, fast containment takes priority; document decisions and preserved evidence.

### 9.4. Evidence preservation

- Record alert ID, host/Pod/function ID, image digest, and timestamps.
- Export relevant EDR, OS, Kubernetes, and cloud audit logs.
- Preserve snapshots or disk images under organization-approved forensic procedures.
- Record collector identity, source, timestamp, hash, and storage location of evidence.
- Restrict evidence access and maintain chain of custody.
- Avoid analyzing original evidence directly when working copies can be created.

Forensic snapshots must be encrypted, access-controlled, and retained per forensic policy. Never attach snapshots containing production data to unisolated analysis hosts.

### 9.5. Eradication and recovery

Once root cause and scope are established:

1. Remove persistence mechanisms, malware, and compromised workloads or configurations.
2. Patch the vulnerability and fix the root cause.
3. Revoke or rotate potentially exposed credentials, tokens, keys, and certificates.
4. Rebuild VMs/containers/functions from verified clean images or artifacts.
5. Apply reviewed IAM permissions and network policies.
6. Restore data from trusted backups; verify integrity before reopening traffic.
7. Monitor processes, networking, identities, and resources post-recovery for signs of re-compromise.

Never copy the entire filesystem of a compromised workload verbatim onto a new host before knowing where persistence resides. Recover needed data via separate validation workflows and retain evidence for investigation.

## 10. Example playbook: container exhibiting abnormal behavior

Suppose an EDR/runtime sensor detects an API service container spawning a shell. The container then creates an executable in a temporary directory and opens an outbound connection to an unbaselined address.

A playbook can execute:

1. Open an incident recording owner, namespace, Pod UID, node, image digest, and timestamp.
2. Check recent deployment events, pipeline runs, commits, and change tickets.
3. Collect process trees, file metadata/hashes, network connections, and application logs.
4. Check whether sibling Pods sharing the same image digest or service account show similar activity.
5. If compromise probability is high, block egress or isolate the Pod/namespace per playbook while preserving evidence copies.
6. Determine whether the service account/token was used to access the Kubernetes API or cloud resources.
7. Revoke potentially exposed tokens/secrets and audit IAM logs.
8. Redeploy from a signed clean image, update dependencies, and tighten admission policies.
9. Run smoke tests, confirm legitimate network egress, and monitor for recurring alerts.
10. Document root cause, scope, time to detect, time to contain, and preventive actions.

If the shell was spawned by a legitimate init script, verify the script contents, image digest, and pipeline. Add an exception only after verification and scope it narrowly to the specific workload, process path, or version.

## 11. Integrating detection with SIEM and operations systems

EDR, runtime sensors, cloud audits, and application telemetry emit varied formats. A centralized SIEM or detection platform normalizes, correlates, and routes alerts.

Reference architecture:

~~~mermaid
flowchart TD
    VM["VM: EDR / OS audit"] --> COL["Collector / telemetry pipeline"]
    K8S["Container: runtime sensor / audit"] --> COL
    SF["Serverless: function / IAM logs"] --> COL
    CLOUD["Cloud control plane / flow logs"] --> COL
    APP["Application logs / traces"] --> COL
    COL --> SIEM["SIEM / detection engine"]
    SIEM --> SOAR["Incident workflow / SOAR"]
    SOAR --> TEAM["Security + Platform + App owner"]
    SOAR --> CASE["Case, evidence, and timeline"]
~~~

When integrating, standardize fields such as timestamp, cloud account/project, region, resource ID, workload name, namespace, image digest, principal, source IP, and event category.

An actionable alert should include:

- Behavior summary and detection rationale.
- Affected workload/identity and criticality.
- Timestamp, telemetry source, and log query link.
- Deployment/change context.
- Suggested next checks and relevant playbook.
- Accountable person or team.

Enable automated containment only under explicit conditions, bounded scope, and blast-radius safeguards. For instance, auto-blocking an egress connection may be safe for a stateless workload, whereas isolating a primary database can cause a major outage. Production-impacting actions require approval or pre-tested policies.

## 12. Measuring detection and response effectiveness

Operational metrics help evaluate the system:

| Metric | Meaning | How it is used |
|---|---|---|
| MTTD | Mean Time to Detect, average time to discover an issue | Evaluates observability and detection quality |
| MTTA | Mean Time to Acknowledge, average time until someone claims triage | Evaluates on-call readiness and routing |
| MTTC | Mean Time to Contain, average time to limit incident spread | Evaluates runbooks and response permissions |
| MTTR | Mean Time to Recover/Respond, explicitly defined by the organization | Tracks recovery or resolution speed |
| False positive rate | Share of alerts that are not real incidents | Evaluates rule quality and baselines |
| Coverage | Share of critical workloads with appropriate telemetry and policies | Surfaces monitoring blind spots |
| Restore success rate | Share of recovery drills that succeed | Evaluates recoverability |

Never optimize metrics by suppressing alert severity or auto-closing tickets. Measure detection quality, missed detections, operational impact, and recovery capability together.

## 13. Common mistakes

**Securing only images without monitoring runtime:** clean artifacts can still be exploited after deployment. Pair image scanning with runtime telemetry and response playbooks.

**Collecting massive logs without context:** makes prioritizing alerts slow and investigations painful. Tag logs with workload owner, image digest, deployment, and identity.

**Setting fixed resource thresholds:** batch jobs or autoscaling can trigger false alarms. Base baselines on workload type, time of day, and business load.

**Assuming containers are complete security boundaries:** containers share the host kernel and may hold excessive host permissions. Run non-root, drop capabilities, restrict mounts, and secure nodes.

**Sharing service accounts or instance roles:** one compromised workload can access unrelated resources. Separate identities per workload with least privilege.

**Auto-deleting workloads on alert:** can destroy forensic evidence or cause downtime. Define isolation, evidence capture, and automation conditions beforehand.

**Isolating without revoking credentials:** attackers can reuse stolen tokens from elsewhere. Audit identities and rotate impacted credentials.

**Restoring from unverified images or backups:** can reintroduce persistence. Use clean artifacts, verify provenance, and validate data before restoring.

**Never testing runbooks:** isolation permissions or log queries may fail during emergencies. Run regular drills and update runbooks as architecture evolves.

## 14. Runtime protection and incident response checklist

- [ ] Every workload has a documented owner, environment, criticality, and baseline.
- [ ] VMs are patched, hardened, service-minimized, and running appropriate EDR.
- [ ] Containers run non-root with restricted capabilities, syscalls, filesystems, and networking.
- [ ] Kubernetes RBAC, service accounts, audit logs, and admission policies are governed.
- [ ] Serverless functions use dedicated execution roles and authenticated triggers.
- [ ] Secrets are delivered via workload identity/secret managers and are rotatable.
- [ ] Telemetry covers processes, files, networking, identities, and the cloud control plane.
- [ ] Alerts correlate with deployments, change windows, and workload owners.
- [ ] Playbooks exist for triage, isolation, evidence collection, eradication, and recovery.
- [ ] Procedures isolate VMs/containers/functions without destroying critical evidence.
- [ ] Logs and evidence are protected, time-synchronized, and access-controlled.
- [ ] Workloads rebuild from clean artifacts and data integrity is verified.
- [ ] Incident response and break-glass access are periodically drilled.
- [ ] MTTD, MTTA, MTTC, MTTR, and coverage are measured using consistent definitions.
- [ ] Lessons learned feed directly into baseline, policy, and pipeline updates.

Runtime protection combines hardening, telemetry, context-aware detection, and executable response procedures. Define normal behavior for each workload, monitor processes, files, networking, and identities, and correlate signals with deployment changes. When an incident occurs, assess scope, isolate safely, preserve evidence, revoke affected credentials, and recover from clean artifacts. Regular drills help teams respond rapidly while preserving forensic capability and service availability.

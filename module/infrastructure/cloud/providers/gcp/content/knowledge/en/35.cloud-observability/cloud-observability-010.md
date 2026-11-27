# Ops Agent for Compute Engine

Ops Agent is Google Cloud's primary telemetry collection agent for Compute Engine virtual machines. The agent runs directly on the VM, reads OS and application logs, collects resource metrics, and can receive custom traces and metrics over the OpenTelemetry Protocol (OTLP). Data is then sent to the corresponding Cloud Observability services for querying, building dashboards, alerting, and incident investigation.

In the CLOUD_PROVIDERS_GCP module, Ops Agent serves as the bridge between Compute Engine VMs and Google Cloud's reliability, performance, and operational monitoring capabilities. When deploying a workload on a VM, operators need to know what data types the agent collects, how to install and authorize it, how to configure pipelines, how to manage the agent across a fleet of VMs, and how to verify data delivery.

After this lesson, you will be able to:

- Explain the role of Ops Agent and the flow of logs, metrics, and traces.
- Verify IAM, API, OS, and network prerequisites before installing the agent.
- Install and verify Ops Agent on Linux or Windows.
- Extend configuration using receivers, processors, and pipelines.
- Collect application logs, custom metrics, and OTLP traces.
- Manage the agent across a VM fleet, monitor health, and troubleshoot data collection failures.

## 1. Where Does Ops Agent Fit in the Observability Architecture?

Observability answers three categories of questions when operating systems:

- **Logs**: What happened? Logs record events, errors, requests, and application activity.
- **Metrics**: How is the system performing? Metrics represent numeric values over time such as CPU, memory, disk usage, latency, and request count.
- **Traces**: Which components did a request traverse and where was time spent? Traces link spans together to observe a request's path across the application.

Ops Agent collects these signals on Compute Engine. The log-processing component uses Fluent Bit; the metric and trace collection component uses the OpenTelemetry Collector.

~~~mermaid
flowchart LR
    subgraph VM["Compute Engine VM"]
        OS["Operating System"]
        APP["Application"]
        OTel["OpenTelemetry SDK"]
        Agent["Ops Agent"]
        OS -->|system logs, host metrics| Agent
        APP -->|application logs| Agent
        OTel -->|OTLP gRPC| Agent
    end
    Agent -->|Logs| CL["Cloud Logging"]
    Agent -->|Metrics| CM["Cloud Monitoring"]
    Agent -->|OTLP traces| CT["Cloud Trace"]
    CL --> LE["Logs Explorer / log-based metrics"]
    CM --> ME["Metrics Explorer / dashboards / alerts"]
    CT --> TE["Trace Explorer"]
~~~

| Signal | Common Sources | Google Cloud Destination |
|---|---|---|
| Logs | Syslog, journald, Windows Event Log, application log files, receiver logs | Cloud Logging |
| Metrics | CPU, memory, disk, network, process, IIS, SQL Server, Prometheus, or OTLP | Cloud Monitoring |
| Traces | Applications instrumented with OpenTelemetry SDK sending OTLP | Cloud Trace |

Ops Agent uses a unified YAML configuration and supports the Linux distributions and Windows versions listed in the compatibility documentation. The agent can collect logs from files, systemd journal, Windows Event Log, TCP, Fluent Forward, and third-party application integrations. Common system metrics are collected under the default configuration.

Important limitations to remember:

- Ops Agent is designed for Compute Engine; documentation also provides separate guidance for Bare Metal Solution. Do not install this agent on Amazon EC2 or on-premises servers as if they were Compute Engine VMs.
- Logs go to Cloud Logging and metrics go to Cloud Monitoring. To forward logs to BigQuery, Cloud Storage, or other destinations, configure log sinks in Cloud Logging.
- Custom traces require an OTLP receiver, an instrumented application, and Cloud Trace write permissions.
- The agent does not automatically generate business traces if the application has not emitted spans via OpenTelemetry.

## 2. Pre-Installation Preparation

### 2.1. Choosing Supported VMs and Operating Systems

Check the VM's operating system against Google Cloud's supported operating systems list before installing. End-of-life Linux or Windows versions may lack compatible packages in the installation repository.

Container-Optimized OS has its own built-in Cloud Logging integration; follow the OS-specific guidance rather than manually installing Ops Agent as on Debian, Ubuntu, or Windows Server.

### 2.2. Enabling Required APIs

The project must enable the Cloud Logging API and Cloud Monitoring API:

~~~bash
gcloud services enable logging.googleapis.com monitoring.googleapis.com --project=PROJECT_ID
~~~

Replace PROJECT_ID with the project hosting the VMs to monitor. If using OTLP to send traces, also verify Cloud Trace permissions and configuration per section 7.

When enabling OTLP trace collection, also enable the Cloud Trace API:

~~~bash
gcloud services enable cloudtrace.googleapis.com --project=PROJECT_ID
~~~

### 2.3. Assigning Identity to the VM

Ops Agent uses the service account identity attached to the Compute Engine VM via Application Default Credentials (ADC). This service account needs permissions to write observability data:

| IAM Role | Purpose |
|---|---|
| roles/logging.logWriter | Write logs to Cloud Logging |
| roles/monitoring.metricWriter | Write metrics to Cloud Monitoring |
| roles/cloudtrace.agent | Write traces to Cloud Trace when OTLP trace collection is enabled |

The first two roles are the baseline permissions for logs and metrics. The Cloud Trace Agent role is needed only when the agent sends traces. Attach a dedicated service account per workload or workload group, then grant only the required roles at the appropriate project scope.

Example granting permissions to the VM's service account:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:vm-observability@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:vm-observability@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"
~~~

If OTLP tracing is enabled, also grant:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:vm-observability@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudtrace.agent"
~~~

The VM also needs OAuth access scopes for the corresponding APIs. For new VMs, the cloud-platform scope is typically the simplest choice when IAM roles already restrict permissions on the service account. On older VMs with narrow scopes, check Logging and Monitoring scopes before assuming IAM roles alone are sufficient.

Never download a service account JSON key onto the VM to run the agent. VM-attached identity and ADC avoid managing long-lived keys on disk.

### 2.4. Checking Legacy Agents and Connectivity

Before installing, verify whether the VM already has the legacy Cloud Logging agent or Cloud Monitoring agent installed. Running the new agent alongside legacy agents can duplicate logs or cause metric conflicts. If migrating, back up the old configuration, plan the receiver/pipeline migration, and uninstall legacy agents per Google Cloud documentation.

The VM must be able to reach the Cloud Logging and Cloud Monitoring APIs over the network. If workloads route through a proxy or egress firewall, ensure the required endpoints are reachable. Ops Agent supports proxies, though configuration must match the VM's environment.

## 3. Installing Ops Agent on a VM

### 3.1. Installing on Linux

SSH into the VM, change to a writable directory, and run the official installation script:

~~~bash
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
sudo bash add-google-cloud-ops-agent-repo.sh --also-install
~~~

The script adds the Google Cloud repository and installs the latest agent version. After installation, the agent starts automatically.

You can pass --dry-run to preview the commands the script intends to execute. For production deployments, consider pinning by major version to avoid automatically upgrading across major releases with breaking changes. Script syntax:

~~~bash
sudo bash add-google-cloud-ops-agent-repo.sh --also-install --version="MAJOR_VERSION.*.*"
~~~

Choose a major version tested and supported by your organization; do not copy arbitrary old example versions without checking the current release lifecycle.

### 3.2. Installing on Windows

Open PowerShell as Administrator on the VM, download, and run the installation script:

~~~powershell
(New-Object Net.WebClient).DownloadFile(
  "https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.ps1",
  "$env:UserProfile\add-google-cloud-ops-agent-repo.ps1"
)
Invoke-Expression "$env:UserProfile\add-google-cloud-ops-agent-repo.ps1 -AlsoInstall"
~~~

After installation, check the service in Windows Services or using PowerShell in section 4.

### 3.3. Installing the Agent at VM Creation

To ensure every new VM emits telemetry from boot, install Ops Agent during VM provisioning via startup scripts or your organization's configuration management tooling. For large fleets, consider VM Extension Manager policies to deploy, version-pin, and apply configurations centrally.

For a few test VMs, installing directly is a quick way to verify logs and metrics. As VM count grows, transition to a repeatable deployment method that enforces version control and checks per-machine status.

## 4. Checking Agent Status and Operations

### 4.1. Checking the Service

On Linux:

~~~bash
sudo systemctl status "google-cloud-ops-agent*"
~~~

To restart the agent after editing configuration:

~~~bash
sudo systemctl restart google-cloud-ops-agent
~~~

On Windows, check the service:

~~~powershell
Get-Service google-cloud-ops-agent*
~~~

Restart:

~~~powershell
Restart-Service google-cloud-ops-agent -Force
~~~

The agent includes sub-components handling logs and metrics. When checking status, verify that all relevant components started cleanly and are not crash-looping.

### 4.2. Verifying Data Reaches Google Cloud

A Running service alone is not enough to conclude telemetry is ingesting successfully. Verify the output data as well:

- In Logs Explorer, filter by resource type gce_instance and the VM name, then look for recent OS or application logs.
- In Metrics Explorer, search for system metrics prefixed with agent.googleapis.com, select the target VM, and confirm fresh time series appear.
- If using OTLP traces, open Trace Explorer and search for traces by service or test time range.
- Verify timestamp, project, zone, and instance_id to be certain data comes from the intended VM.

You can emit a test log with an easily identifiable string and query it in Logs Explorer. For metrics, chart CPU or memory for the VM and verify data points update at the collection interval.

## 5. Understanding Ops Agent YAML Configuration

Ops Agent ships with a built-in default configuration for common logs and metrics. Do not edit the built-in defaults directly; instead, create a user configuration file to add or override components.

Configuration file paths:

| Operating System | Configuration File |
|---|---|
| Linux | /etc/google-cloud-ops-agent/config.yaml |
| Windows | C:\Program Files\Google\Cloud Operations\Ops Agent\config\config.yaml |

The user configuration file is merged with the built-in configuration when the agent restarts. To override a built-in receiver, processor, or pipeline, declare the same identifier to replace that component's configuration.

Notable default settings:

- Linux collects logs from /var/log/messages and /var/log/syslog, and collects host metrics on a 60-second interval.
- Windows collects the System, Application, and Security Event Log channels; the agent also collects host metrics along with IIS and SQL Server metrics when those components are present.

Because user configuration merges with the built-in configuration, adding a new pipeline generally preserves default pipelines. To alter a default pipeline, redeclare its exact pipeline identifier.

Three main blocks:

| Block | Role |
|---|---|
| receivers | Declares log or metric sources the agent should collect from |
| processors | Parses, transforms, filters, or enriches data fields |
| service.pipelines | Wires receivers and processors into processing pipelines |

A receiver can be used across multiple pipelines. Receiver order in a pipeline does not matter, whereas processor order matters because each record passes through processors in the declared sequence.

~~~mermaid
flowchart LR
    R["Receiver<br/>Data source"] --> P1["Processor 1<br/>Parse / filter"]
    P1 --> P2["Processor 2<br/>Transform"]
    P2 --> PL["Pipeline"]
    PL --> DEST["Cloud Logging or<br/>Cloud Monitoring"]
~~~

After modifying config.yaml, restart the agent for changes to take effect. Invalid YAML syntax or invalid receiver declarations may prevent the agent from starting.

## 6. Collecting Application Logs

### 6.1. Adding Log Files to a Pipeline

Suppose the Orders application writes each event as a single-line JSON object to /var/log/orders/orders.json. You can declare a file receiver and a parse_json processor:

~~~yaml
logging:
  receivers:
    orders_json:
      type: files
      include_paths:
        - /var/log/orders/*.json

  processors:
    parse_orders_json:
      type: parse_json

  service:
    pipelines:
      orders_pipeline:
        receivers: [orders_json]
        processors: [parse_orders_json]
~~~

In this example:

1. The orders_json receiver reads files matching the path pattern.
2. The parse_orders_json processor parses JSON contents into fields inside jsonPayload.
3. The orders_pipeline connects the source and processing step.
4. Ops Agent forwards the processed logs to Cloud Logging.

The account running the agent must have read access to the log files. If the application creates files with overly restrictive permissions, the agent may skip them or fail to read data. Check directory permissions, ownership, and how the application rotates files.

### 6.2. Processing Structured Logs

JSON logs enable far more accurate queries than long plain-text strings. For example, an application record might contain:

~~~json
{
  "timestamp": "2026-11-19T08:30:00Z",
  "severity": "ERROR",
  "service": "orders-api",
  "request_id": "req-12345",
  "message": "Database connection timeout",
  "duration_ms": 3200
}
~~~

After parsing, fields sit inside jsonPayload and can be queried in Logs Explorer. To map a field into standard LogEntry metadata, the modify_fields processor can move values from jsonPayload into top-level fields such as severity or httpRequest.

For plain-text logs, parse_regex can extract fields using named capture groups. For multi-line Java stack traces, the parse_multiline processor can combine exception lines into a single readable LogEntry.

### 6.3. Choosing Appropriate Log Sources

Ops Agent supports several log sources:

- files: reads files by path and wildcard.
- systemd_journald: reads logs from systemd journal on Linux.
- syslog: receives Syslog over TCP or UDP on Linux.
- windows_event_log: reads Windows Event Log channels.
- tcp: receives JSON logs over TCP.
- fluent_forward: receives logs via the Fluent Forward protocol.

Avoid collecting every file under /var/log with broad wildcards unless there is a clear need. Select specific files, suppress repetitive or unnecessary logs at the source, and avoid sending sensitive data such as passwords, tokens, or personal data to Cloud Logging.

## 7. Collecting Custom Metrics and Traces

### 7.1. Host Metrics

On Linux, the default configuration uses the hostmetrics receiver with a 60-second collection interval. You can override the receiver using the same identifier to change the interval:

~~~yaml
metrics:
  receivers:
    hostmetrics:
      type: hostmetrics
      collection_interval: 30s
~~~

This example changes host metrics collection from 60 seconds to 30 seconds. Shorter intervals detect changes faster but increase metric sample volume and may impact cost. Choose intervals based on alerting sensitivity and required visibility granularity.

System metric groups typically include CPU, memory, disk, network, swap, and processes. Some metrics exist only on Linux; Windows adds receivers such as IIS and MSSQL.

### 7.2. Application and Prometheus Metrics

Ops Agent can collect metrics from supported third-party applications, Prometheus receivers, or OTLP receivers. Before adding a receiver, confirm which format the application exposes and check whether your agent version supports that receiver.

When expanding metrics, manage high-cardinality labels. Never put request IDs, user IDs, or continuously changing values into metric labels because time series counts can grow rapidly. For per-request identifiers, logs or traces are usually better suited.

### 7.3. Collecting Traces via OTLP

To receive metrics and traces from applications instrumented with OpenTelemetry, Ops Agent requires version 2.37.0 or later and an OTLP receiver configuration. Example configuring the receiver and two pipelines:

~~~yaml
combined:
  receivers:
    otlp:
      type: otlp

metrics:
  service:
    pipelines:
      otlp:
        receivers: [otlp]

traces:
  service:
    pipelines:
      otlp:
        receivers: [otlp]
~~~

The application uses the OpenTelemetry SDK or corresponding agent to send OTLP to the receiver on the VM. Ops Agent's OTLP receiver supports gRPC; HTTP transport is not supported in this configuration. The OTLP receiver does not collect logs directly, so application logs still require a separate logging pipeline.

OTLP metrics are sent to Cloud Monitoring, and spans are sent to Cloud Trace. The VM's service account needs trace write permission via roles/cloudtrace.agent; logWriter and metricWriter do not include this permission by default.

If you only need metrics or only need traces, configure the pipeline for the corresponding signal. If an application sends a signal without a matching configured pipeline, the agent drops that data.

## 8. Managing Ops Agent Across Multiple VMs

Manual installation works when testing a single machine. With dozens or hundreds of VMs, operations teams need uniform installation, upgrade, and configuration policies.

### 8.1. VM Extension Manager Policies

VM Extension Manager allows creating extension policies to install Ops Agent across a Compute Engine fleet. Policies can apply project-wide or within a zone, keep the agent pinned to a desired version, and distribute custom configurations. Folder- and organization-level policies are currently in Preview per current documentation; check support status before adopting in production workflows.

A fleet management workflow can include:

1. Choose policy scope: project or zone.
2. Identify compatible VMs and operating systems.
3. Remove conflicting legacy observability agents.
4. Configure agent version and config.yaml contents.
5. Roll out the policy by VM group.
6. Verify extension status, running version, and health of each VM.
7. Expand rollout once the canary group emits complete logs and metrics.

VM Extension Manager provides gcloud commands to inspect extension status. For example, checking extension status on a VM:

~~~bash
gcloud beta compute instances list-vm-extension-states INSTANCE_NAME \
  --project=PROJECT_ID \
  --zone=ZONE
~~~

The output helps verify which extensions are installed, enforcement status, health, and active version. Preview/beta gcloud commands may change; verify current documentation and your Google Cloud CLI version before embedding into automation.

### 8.2. Automation Tools

Google Cloud documentation also covers managing Ops Agent with Ansible, Chef, and Puppet. These tools fit organizations that already run server configuration management systems and want shared playbooks, cookbooks, or modules to install the agent, deploy YAML configs, and manage restarts.

With Terraform or the Google Cloud CLI, agent policies and related infrastructure can be managed declaratively. Store configurations in Git, review changes, test on a representative VM group, and track released versions.

### 8.3. Controlling Versions and Configuration Changes

A strong fleet policy should answer:

- Which VMs must run Ops Agent?
- Which versions are approved?
- Which configuration applies to each workload group?
- Who is authorized to modify policies?
- How do we detect VMs that lack the agent, failed installation, or stopped sending telemetry?

Maintain a canary group before full rollout. Monitor service errors, log volume, and metrics after updates. Keep versioned configurations so you can roll back if a receiver or processor change introduces errors.

## 9. Health Checks and Troubleshooting

### 9.1. Startup and Runtime Health Checks

Ops Agent performs startup checks to catch conditions preventing normal operation, such as connectivity failures, occupied ports, missing permissions, or disabled APIs. Newer versions also include runtime health checks reporting errors that arise during operation.

On Linux, local health check logs typically reside at:

~~~text
/var/log/google-cloud-ops-agent/health-checks.log
~~~

On Windows:

~~~text
C:\ProgramData\Google\Cloud Operations\Ops Agent\log\health-checks.log
~~~

If the agent is installed and managed by VM Extension Manager, health-check logs may reside in the Google Guest Agent state directory. In that case, the path includes the instance ID and differs from standard installation paths; consult VM Extension Manager troubleshooting docs to locate the exact file.

Health check details can also be sent to Cloud Logging under log ID ops-agent-health. You can query:

~~~text
log_id("ops-agent-health")
~~~

When troubleshooting, read health check messages first before altering IAM, networking, or configuration. After resolving the issue, restart the agent to re-run startup checks.

### 9.2. Verifying Whether the Agent Is Sending Metrics

Ops Agent exposes an agent uptime metric. In Metrics Explorer, you can query it with PromQL:

~~~promql
rate({"__name__"="agent.googleapis.com/agent/uptime", monitored_resource="gce_instance"}[1m])
~~~

Select the right project and VM. If the agent is running but the time series is not updating, check health checks, metric write permissions, access scopes, and the Monitoring API.

### 9.3. Fleet-Wide Checks with gcpdiag

gcpdiag includes rules checking whether Ops Agent is installed and emitting logs/metrics across Compute Engine VMs. This is an open-source tool maintained by Google Cloud Support engineers, not an official Google Cloud product.

Example generating a fleet report:

~~~bash
gcpdiag lint --project=PROJECT_ID --show-skipped --include=gce/ERR/2024_004
~~~

Add --name=INSTANCE_NAME to restrict to a single VM. The report distinguishes VMs missing the agent, VMs ineligible for checks, and VMs successfully sending logs/metrics.

To run gcpdiag in Cloud Shell, the ADC identity needs roles/viewer and roles/serviceusage.serviceUsageConsumer on the project. The Cloud Resource Manager, IAM, Cloud Logging, and Service Usage APIs must be enabled; VM Manager must also be enabled for the tool to detect agents on VMs. If the command reports missing permissions or skips VMs, check these prerequisites first.

### 9.4. Common Issues

| Symptom | Possible Cause | How to Check and Resolve |
|---|---|---|
| Installation fails | Unsupported OS or package repository unreachable | Check OS compatibility list, DNS, proxy, firewall, and sudo/Administrator privileges |
| Agent fails to start | Invalid YAML, invalid receiver, port in use, or legacy agent conflict | Read health-check logs, validate config.yaml, and uninstall legacy agents per docs |
| Metrics present but no logs | Missing roles/logging.logWriter, broken logging pipeline, or unreadable file | Check IAM, log receiver, file paths, and file read permissions |
| Logs present but no metrics | Missing roles/monitoring.metricWriter or metrics pipeline disabled | Check IAM, Monitoring API, access scopes, and metrics service |
| Neither logs nor metrics | VM lacks service account, missing access scope, or disabled APIs | Check VM identity, IAM roles, OAuth scopes, and APIs |
| Agent running but data not updating | Lost connectivity, runtime error, or pipeline dropping data | Check ops-agent-health, uptime metric, and send test log/metric |
| Traces missing in Cloud Trace | OTLP not configured, agent too old, or missing roles/cloudtrace.agent | Check version >= 2.37.0, traces pipeline, gRPC transport, and IAM |
| Duplicate logs | Legacy agent and Ops Agent collecting the same source | Plan migration and uninstall the legacy agent |
| Console stuck at Pending | Extension policy still applying or agent has not emitted metrics yet | Check VM Extension Manager, service status, and gcpdiag report |

## 10. Security, Reliability, and Cost

### 10.1. Protecting Log Data

Logs can contain sensitive data even when an application does not intentionally log secrets. Avoid logging passwords, access tokens, session cookies, private keys, personal data, and unnecessary request payloads. If sensitive data already appears in logs, fix it at the application source and assess retention/deletion obligations per organizational policy.

Grant the VM's service account only the telemetry write roles required. Never grant Owner or Editor solely so the agent can ship logs and metrics. If traces are enabled, add the Cloud Trace Agent role as needed.

### 10.2. Reducing Telemetry Loss Risk

To keep observability data flowing reliably:

- Install the agent via images, startup scripts, or fleet policies so new VMs are never missed.
- Monitor agent health and alert when the uptime metric or health logs stop updating.
- Re-verify service account permissions, APIs, and access scopes whenever modifying VM configurations.
- Test configuration updates on a canary group before fleet-wide rollout.
- Monitor agent status after OS upgrades or network/proxy changes.

### 10.3. Controlling Costs

Observability costs depend on ingested log volume, metric/time series volume, retention, and destination service usage. You can control costs by:

- Collecting only log files and log types genuinely needed for operations.
- Eliminating repetitive debug logs in the application or applying targeted log exclusions.
- Choosing collection_interval according to required alerting sensitivity.
- Avoiding high-cardinality labels in custom metrics.
- Reviewing Metrics Management to spot metrics with high ingestion volume, cardinality, or query usage.
- Choosing log buckets and retention aligned with investigative and compliance requirements.

Do not disable all default logs or metrics just to cut costs before evaluating the impact on alerting and incident investigation.

## 11. Real-World Scenario: Monitoring a VM Running Orders API

A team operates the Orders API service on Compute Engine Linux VMs. The goals are tracking VM health, detecting application errors, and tracing slow requests.

Design:

1. Attach the vm-observability service account to the VMs.
2. Grant roles/logging.logWriter and roles/monitoring.metricWriter to the service account.
3. Enable the Logging API and Monitoring API.
4. Install Ops Agent and confirm the service is active.
5. Keep default hostmetrics to monitor CPU, memory, disk, and network.
6. Add a file receiver reading /var/log/orders/*.json and parse JSON.
7. Instrument Orders API with the OpenTelemetry SDK and configure the OTLP receiver if traces are needed.
8. Grant roles/cloudtrace.agent when enabling traces.
9. Use Logs Explorer to filter by service and request_id; Metrics Explorer to chart CPU/memory; Trace Explorer to locate high-latency requests.
10. Create alerts when CPU, memory, application errors, or agent data staleness cross operational thresholds.

Investigating a slow request can start from a log containing request_id, jump to the corresponding trace to pinpoint the slow span, and then correlate VM CPU/memory/disk metrics over the same window. Combining all three signals enables the operations team to distinguish application bugs, resource bottlenecks, and downstream connectivity issues.

## 12. Production Deployment Checklist

- [ ] VM runs an OS supported by Ops Agent.
- [ ] Cloud Logging API and Cloud Monitoring API are enabled.
- [ ] VM has an appropriate service account and OAuth access scopes for required APIs.
- [ ] Service account has roles/logging.logWriter and roles/monitoring.metricWriter.
- [ ] If sending traces, service account has roles/cloudtrace.agent and agent version meets requirements.
- [ ] Ops Agent is not running concurrently with legacy Logging/Monitoring agents on the same sources.
- [ ] Agent is installed, service is running, and health checks report no errors.
- [ ] Logs Explorer receives fresh logs and Metrics Explorer shows time series for the exact VM.
- [ ] config.yaml is managed in Git and tested on a staging VM.
- [ ] Application log pipeline collects only required files without exposing secrets or personal data.
- [ ] Collection interval and metric labels match operational requirements and budget.
- [ ] Fleet has consistent mechanisms for installation, upgrades, and status monitoring.
- [ ] Alerts exist for when the agent stops sending telemetry or health checks report errors.

## 13. Self-Check Questions

**1. Which services does Ops Agent send logs and metrics to?**

Logs are sent to Cloud Logging; metrics are sent to Cloud Monitoring. OTLP traces are sent to Cloud Trace when the receiver and traces pipeline are configured.

**2. Which internal components does Ops Agent use to process telemetry?**

The agent uses Fluent Bit for logs and the OpenTelemetry Collector for metrics and traces.

**3. Why does the VM's service account need roles/logging.logWriter and roles/monitoring.metricWriter?**

These roles grant permission for the agent to write logs and metrics to the target services. Missing one role can cause one telemetry type to be lost even while the agent keeps running.

**4. When adding an application log file, what are the three main YAML sections?**

Receivers define log sources, processors transform contents, and pipelines connect receivers and processors into a collection flow.

**5. Why must Ops Agent be restarted after editing config.yaml?**

The agent merges user configuration with the built-in defaults at startup. Restarting reloads the configuration and initializes new pipelines.

**6. How do you verify the agent is successfully sending data?**

Check the service and health checks on the VM, then confirm logs in Logs Explorer and time series in Metrics Explorer. For traces, check Cloud Trace.

## 14. References

- [Ops Agent overview](https://cloud.google.com/monitoring/agent/ops-agent)
- [Install the Ops Agent on individual VMs](https://cloud.google.com/logging/docs/agent/ops-agent/installation)
- [Configure the Ops Agent](https://cloud.google.com/monitoring/agent/ops-agent/configuration)
- [Install the Ops Agent by using VM Extension Manager policies](https://cloud.google.com/monitoring/agent/ops-agent/install-agent-vmem-policies)
- [Install the Ops Agent by using automation tools](https://cloud.google.com/logging/docs/agent/ops-agent/fleet-installation)
- [Troubleshoot Ops Agent installation and start-up](https://cloud.google.com/stackdriver/docs/solutions/agents/ops-agent/troubleshoot-install-startup)
- [Find Ops Agent troubleshooting information](https://cloud.google.com/monitoring/agent/ops-agent/troubleshoot-find-info)
- [Troubleshoot Ops Agent data ingestion](https://cloud.google.com/monitoring/agent/ops-agent/troubleshoot-run-ingest)
- [Use the Ops Agent and OpenTelemetry Protocol (OTLP)](https://cloud.google.com/trace/docs/otlp)

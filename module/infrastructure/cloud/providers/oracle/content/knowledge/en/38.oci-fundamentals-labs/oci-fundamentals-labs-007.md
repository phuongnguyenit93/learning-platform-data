# Lab: Building Monitoring Alarms and Collecting Logs

Within the **OCI Fundamentals Labs** chapter, this lab guides you through building an observability pipeline for an Oracle Cloud Infrastructure virtual machine: collecting Compute metrics, ingesting application logs, detecting anomalies, and sending notifications. The scope belongs to the **CLOUD_PROVIDERS_ORACLE** module, connecting tenancy, compartment, IAM, and VCN knowledge to infrastructure operations with access control, monitoring, and cost management.

The lab scenario is a virtual machine running an internal application. Operators need to know when CPU spikes persistently, when the metrics stream is interrupted, and what application events occurred around that time. The lab uses synthetic logs so everything runs on a single Linux VM without deploying extra applications or databases.

## 1. Expected Outcomes and Architecture

Upon completion, learners will be able to:

- Identify the exact region, compartment, metric namespace, and instance to monitor.
- Create a Notifications topic with a confirmed email subscription.
- Collect a log file via Custom Logs Monitoring and query records by run ID.
- Create a high-CPU alarm and a missing-metrics alarm, explaining their trigger conditions.
- Verify the `OK → FIRING → OK` lifecycle through alarm history and notifications.
- Correlate metrics with logs, isolate ingestion failures, and clean up lab resources.

Allocate about 90–120 minutes, plus agent and configuration propagation wait time if the environment is not yet prepared.

~~~mermaid
flowchart LR
    subgraph VM["Compute VM in lab compartment"]
        C["Compute Instance Monitoring"]
        F["Application log file"]
        U["Custom Logs Monitoring / Unified Monitoring Agent"]
        F --> U
    end
    C --> M["OCI Monitoring: metrics"]
    M --> A["Alarms: high CPU / missing metrics"]
    A --> N["Notifications topic"]
    N --> E["Confirmed email"]
    U --> L["OCI Logging: custom log"]
    L --> S["Logging Search"]
~~~

There are two independent data paths. Compute Instance Monitoring provides metrics such as `CpuUtilization`; Custom Logs Monitoring uses the Unified Monitoring Agent to collect custom logs. Enabling one plugin does not substitute for configuring the other. Plugin names and enable/disable controls are described in [Oracle Cloud Agent](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/manage-plugins.htm).

| Component | Question to answer |
| --- | --- |
| Metric | What percentage of CPU is the VM using? |
| Alarm | Has the anomalous condition persisted long enough to fire? |
| Notifications | Did the responsible person receive the alert? |
| Custom log | What events did the application record around that time? |
| Log group | Which logs share the same management and search scope? |

An `ERROR` log entry in Logging does not automatically become a metric or a Monitoring alarm. In this lab, alarms evaluate metrics; logs provide investigation context.

## 2. Environment Preparation and Conventions

### 2.1. Required resources

Prepare a lab compartment, such as `lab-observability`, along with a running Oracle Linux VM that has Oracle Cloud Agent on a supported image. Use a test host where you are permitted to generate CPU load and toggle plugin states. Ensure sufficient RAM for the OS, agents, and SSH sessions.

You need:

1. Console access and the IAM permissions listed in the next section.
2. An SSH session to the VM with `sudo` privileges.
3. An email address you control to confirm the subscription.
4. Network connectivity from the VM to OCI APIs in the active region, including Monitoring and Logging.
5. Synchronized OS clock and working DNS.
6. Authenticated OCI CLI if completing the optional automation section.

For private subnets, check routes, the service gateway to supported OCI services in the region, and appropriate HTTPS egress rules. If the agent needs to fetch packages from external software repositories, an appropriate outbound path such as a NAT gateway is also required. Emitting metrics/logs does not require opening extra inbound ports from the Internet. Compute metric emission prerequisites are stated in [Managing Alarms](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/managingalarms.htm).

### 2.2. Record identifiers

| Value | Meaning |
| --- | --- |
| `REGION` | VM region, e.g., a region subscribed by the tenancy |
| `COMPARTMENT_OCID` | OCID of the compartment holding the VM and lab resources |
| `INSTANCE_OCID` | Exact OCID of the VM to monitor |
| `TOPIC_OCID` | OCID of the Notifications topic to be created |
| `LOG_GROUP_OCID` | OCID of the log group to be created |
| `LOG_OCID` | OCID of the custom log receiving data |
| `ALARM_OCID` | OCID of the CPU alarm, used if inspecting via CLI |

Strings inside `<...>` below are placeholders to be replaced with real values. Do not use the instance display name in place of `INSTANCE_OCID`.

In this lab, the VM, metrics, alarms, topic, log group, and agent configuration all reside in the same compartment and region for straightforward verification. If deploying centrally into another compartment, separate permissions must be granted at both the data source and configuration storage locations.

### 2.3. Distinguish where commands run

| Action type | Where executed |
| --- | --- |
| Create policies, dynamic groups, topics, logs, and alarms | OCI Console |
| Create log file, emit markers, generate CPU load, check systemd | Bash session over SSH on the VM |
| Commands starting with `oci` | Cloud Shell or a terminal with OCI CLI installed and configured |
| MQL and Logging Search | Query input of the corresponding service in the Console |

Do not run the load generator or `/var/log/oci-lab` writes in Cloud Shell, as you would be operating on a different environment from the monitored VM.

## 3. IAM Permissions for Operators and the Agent

Console users and the agent process on the VM are two separate principals. Permissions of the person creating the log do not automatically grant the instance permission to ingest logs.

### 3.1. Permissions for the learner group

An administrator creates or uses group `LabObservers` and assigns learners to the group. The policy example below scopes data and configuration actions to the lab compartment:

~~~text
Allow group LabObservers to read metrics in compartment lab-observability
Allow group LabObservers to manage alarms in compartment lab-observability
Allow group LabObservers to manage ons-topics in compartment lab-observability
Allow group LabObservers to manage log-groups in compartment lab-observability
Allow group LabObservers to manage unified-configuration in compartment lab-observability
Allow group LabObservers to read log-content in compartment lab-observability
Allow group LabObservers to read instances in compartment lab-observability
Allow group LabObservers to read instance-agent-plugins in compartment lab-observability
Allow group LabObservers to inspect dynamic-groups in tenancy
Allow group LabObservers to inspect compartments in tenancy
~~~

The group has permissions to manage alarms, read metrics, and manage topics to set up notification targets. If an administrator pre-creates the topic, topic permissions can be narrowed to match the task. Monitoring and Notifications permissions follow [Policy Builder Policy Templates](https://docs.oracle.com/en-us/iaas/Content/Identity/policiescommon/commonpolicies.htm).

`read log-content` grants content viewing; `manage log-groups` handles log group and log management; `unified-configuration` handles agent configurations. Selecting a host group requires inspect access on the corresponding groups. See [Logs and Log Groups](https://docs.oracle.com/en-us/iaas/Content/Logging/Task/managinglogs.htm).

The policy above does not yet allow updating the VM. If learners toggle plugins themselves during the lab, an administrator may add the following permission in the lab compartment, or perform the plugin state switches directly:

~~~text
Allow group LabObservers to use instances in compartment lab-observability
~~~

`use instances` also permits other VM operational actions; grant it only within an appropriate lab scope. Creating dynamic groups and policies remains part of administrator preparation. When a group belongs to a specific identity domain, use the proper domain-qualified syntax, such as `'YourDomain'/'LabObservers'`.

### 3.2. Dedicated dynamic group for the VM

Create dynamic group `LabLogInstances` with the matching rule:

~~~text
ALL {instance.id = '<INSTANCE_OCID>'}
~~~

Targeting a single specific VM avoids out-of-scope log collection. Instance-ID matching syntax is illustrated in [Managing Agent Configurations](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/agent-configurations.htm).

Create the policy for the instance principal:

~~~text
Allow dynamic-group LabLogInstances to use log-content in compartment lab-observability
~~~

This grants the agent permission to fetch configurations and push logs into Logging under the custom logs model without copying personal API signing keys onto the VM. Oracle documents this grant in [Selecting Target Hosts with Dynamic Groups](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/custom_logs_multihost.htm).

Do not interpret `use log-content` as strictly write-only: it also includes related read capabilities defined by Logging. A dedicated lab compartment keeps the scope bounded. After IAM changes, wait for propagation and retest before making further policy edits.

## 4. Set Up Notifications and Verify Baseline Metrics

### 4.1. Create topic and email subscription

In the Console, navigate to **Notifications**, choose the right region and compartment, then:

1. Create topic `lab-ops-alerts`.
2. Inside the topic, create a subscription with protocol **Email** and your target email address.
3. Open the confirmation email and click the confirmation link.
4. Return to the Console and confirm the subscription transitions to `ACTIVE`.
5. Use the topic's **Publish message** feature to send a test message, e.g., `OCI lab notification path ready`.
6. Verify the test email arrives, checking the spam folder if necessary.

An email subscription in `PENDING` state is not yet eligible to receive operational alerts. The confirmation flow is described in [Creating a Subscription](https://docs.oracle.com/en-us/iaas/Content/Notification/Tasks/create-subscription-basic.htm).

The test message only verifies the topic → email segment. Afterward, you must still test the alarm → topic → email segment.

### 4.2. Enable plugins and confirm incoming data

Open **Compute → Instances → lab VM → Oracle Cloud Agent**. Enable **Compute Instance Monitoring** and **Custom Logs Monitoring**, then wait for the appropriate running state. If a plugin is unsupported on your image, switch to a supported image before continuing; do not treat flipping the toggle alone as proof the agent is active.

Open **Monitoring → Metrics Explorer**, select the compartment containing the VM, and configure:

| Property | Value |
| --- | --- |
| Metric namespace | `oci_computeagent` |
| Metric name | `CpuUtilization` |
| Dimension | `resourceId = <INSTANCE_OCID>` |
| Interval | `1m` |
| Statistic | `mean` |
| Time range | Last 15–30 minutes |

In MQL mode, the baseline query is:

~~~text
CpuUtilization[1m]{resourceId = "<INSTANCE_OCID>"}.mean()
~~~

Confirm fresh data points appear and record the normal baseline CPU level. `CpuUtilization` is a case-sensitive metric name measured in percent; `resourceId` is the dimension used to select the resource. See [Compute Instance Metrics](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computemetrics.htm).

If the chart is empty, stop here and fix the metrics source. Never lower alarm thresholds to work around missing data.

## 5. Collect Custom Logs from the VM

OCI Logging distinguishes Audit logs, service logs, and custom logs. This lab uses a **custom log** that you explicitly write to a file. Audit records OCI API activity; service logs originate from supported services when enabled. Do not substitute Audit for in-VM application logs. See [Logging Overview](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm).

### 5.1. Prepare the log file and run identifier

Run in a Bash session over SSH on the VM:

~~~bash
sudo install -d -m 0755 -o "$(id -un)" -g "$(id -gn)" /var/log/oci-lab

export LOG_FILE=/var/log/oci-lab/app.log
touch "$LOG_FILE"
chmod 0644 "$LOG_FILE"

export LAB_RUN="lab-$(date -u +%Y%m%dT%H%M%SZ)"

lab_log() {
  printf '%s level=%s app=oci-lab run_id=%s event=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$LAB_RUN" "$2" \
    >> "$LOG_FILE"
}

lab_log INFO file-created
printf 'RUN_ID=%s\n' "$LAB_RUN"
tail -n 5 "$LOG_FILE"
~~~

Record `LAB_RUN` to filter specifically for this practice run. If you open a new SSH session, re-export `LOG_FILE` and `LAB_RUN` with the recorded values and redefine the `lab_log` function.

`0644` permissions here are solely for synthetic data, allowing the agent account to read the file without granting world write access. For real logs containing internal data, design a dedicated group or ACL and verify the agent service account's permissions. The agent must be able to read the file and traverse all parent directories.

### 5.2. Create the log group and custom log

In **Logging → Log Groups**, create `lab-observability-logs` in the lab compartment.

Inside the log group, create custom log `lab-app-log` with a **30-day** retention. You may add an agent configuration directly inside the custom log wizard or add it afterward. For this lab, add the configuration afterward so each resource is clearly observed. The custom log creation flow is described in [Creating a Log](https://docs.oracle.com/en-us/iaas/Content/Logging/Task/create-logging-log.htm).

A log group is a management container; a custom log is the ingestion destination. Creating those two objects alone does not automatically push the file on the VM into Logging.

### 5.3. Create the agent configuration

Open **Logging → Agent Configurations** and create `lab-app-agent-config` with:

| Configuration item | Lab value |
| --- | --- |
| Compartment | `lab-observability` |
| State | Enabled |
| Host group type | Dynamic group |
| Host group | `LabLogInstances` |
| Input type | Log path / Log Directory (Tail), depending on UI label |
| Input name | `lab-app-file` |
| File path | `/var/log/oci-lab/app.log` |
| Parser | `None` |
| Message key | `message` if prompted by UI |
| Destination log group | `lab-observability-logs` |
| Destination log | `lab-app-log` |

Save the configuration and wait for the agent to pull it. The configuration must simultaneously specify the right host group, input, and destination; the workflow is covered in [Creating an Agent Configuration](https://docs.oracle.com/en-us/iaas/Content/Logging/Task/create-logging-agent-configuration.htm).

Choosing the **None** parser preserves each raw text line inside the message field. Strings like `level=INFO` and `run_id=...` remain inside the message text rather than becoming standalone JSON fields. If switching to a JSON parser in another deployment, emit valid JSON and standardize timestamp handling. Supported parsers are listed in [Log Inputs and Parsers](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/log_inputs_and_parsers.htm).

If the configuration offers an option to enable dedicated logging-agent operational metrics, leave it disabled for this foundational lab. That option requires designing a separate metric namespace and metric emission permissions; it is not needed to collect the log file here.

### 5.4. Emit fresh entries once the agent is ready

Keep the SSH session containing `lab_log`, then run:

~~~bash
lab_log INFO collector-ready
lab_log WARN synthetic-retry
lab_log ERROR synthetic-failure
tail -n 5 "$LOG_FILE"
~~~

Emitting markers after the agent receives the configuration avoids depending on whether the agent backfills older lines. If data does not appear yet, inspect the agent first and then emit a fresh marker.

On Oracle Linux, basic diagnostic commands are:

~~~bash
sudo systemctl status unified-monitoring-agent --no-pager
sudo journalctl -u unified-monitoring-agent -n 50 --no-pager
sudo journalctl -u unified-monitoring-agent_config_downloader -n 50 --no-pager
~~~

When you need to explicitly trigger a configuration reload:

~~~bash
sudo systemctl restart unified-monitoring-agent_config_downloader
~~~

Do not reboot the entire VM just to reload agent config. Automatic config pulls can take some time; the systemd units and inspection steps are documented in [Troubleshooting Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/troubleshooting.htm).

### 5.5. Query records in Logging Search

Open **Logging → Search**, select the right region and a time range covering when you emitted the markers, such as the last 30 minutes. First query all data in the custom log:

~~~text
search "<COMPARTMENT_OCID>/<LOG_GROUP_OCID>/<LOG_OCID>"
| sort by datetime desc
~~~

Expand one record in JSON view and inspect the `data.message` field and source metadata. Then filter by your run ID, replacing the illustrative value with your actual `LAB_RUN`:

~~~text
search "<COMPARTMENT_OCID>/<LOG_GROUP_OCID>/<LOG_OCID>"
| where data.message = '*run_id=lab-20261121T030000Z*'
| sort by datetime desc
~~~

To view only the simulated error entries for that exact run:

~~~text
search "<COMPARTMENT_OCID>/<LOG_GROUP_OCID>/<LOG_OCID>"
| where data.message = '*run_id=lab-20261121T030000Z*'
  and data.message = '*level=ERROR*'
| sort by datetime desc
~~~

The `compartment/log-group/log` scope structure and field references belong to the Logging Query Language, documented in [Logging Query Language Specification](https://docs.oracle.com/en-us/iaas/Content/Logging/Reference/query_language_specification.htm). This is a different language from MQL; do not paste `search ...` queries into an alarm condition field.

If the actual message field differs due to parser settings, adjust the field path based on the observed JSON record. Because the `None` parser keeps raw text, querying `data.level = 'ERROR'` does not apply under the current config.

**Checkpoint:** find all three markers—`collector-ready`, `synthetic-retry`, and `synthetic-failure`—for the same `LAB_RUN`. Seeing the file on the VM only proves local file writes, not ingestion into OCI.

## 6. Create a High-CPU Threshold Alarm

### 6.1. Build the MQL condition

Starting from the baseline query, add a threshold:

~~~text
CpuUtilization[1m]{resourceId = "<INSTANCE_OCID>"}.mean() > 60
~~~

Explanation:

- `[1m]` is the one-minute aggregation interval.
- `resourceId` scopes data to the lab VM.
- `mean()` computes the average within the interval.
- `> 60` checks whether CPU exceeds 60 percent.

The 60% threshold is only for this lab. In real operations, choose thresholds based on normal baseline behavior, impact severity, and required response time.

Distinguish **interval** from **trigger delay**. The interval sets the statistical aggregation window; the trigger delay, or `pendingDuration`, requires the breach condition to persist long enough before the alarm transitions to `FIRING`. A two-minute trigger delay does not mean only a single data point from a two-minute window is sampled. Evaluation mechanics are explained in [Overview of Monitoring](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Concepts/monitoringoverview.htm).

### 6.2. Create the alarm definition

In **Monitoring → Alarm Definitions**, select **Create Alarm**:

| Property | Value |
| --- | --- |
| Alarm name | `lab-cpu-high` |
| Alarm compartment | `lab-observability` |
| Metric compartment | Compartment containing the VM |
| Namespace | `oci_computeagent` |
| Query | CPU MQL expression above |
| Trigger delay | 2 minutes, equivalent to `PT2M` |
| Severity | `WARNING` |
| Destination | Topic `lab-ops-alerts` |
| Repeat notifications | Disabled for initial testing |
| Enable alarm | Enabled |

If the UI asks how to group notifications, grouping per metric stream of one VM is sufficient for this lab. There is no need to bundle every instance in the compartment into one condition.

Enter a notification body, for example:

~~~text
LAB: VM CPU exceeded 60% continuously for the 2-minute trigger delay.
Check instance OCID, CpuUtilization chart, and logs in UTC.
If running synthetic load, stop test processes and monitor recovery.
~~~

This template gives remediation guidance and states the lab scope. Never put passwords or sensitive application data in the alarm body. Alarm creation fields are documented in [Creating a Basic Alarm](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/create-alarm-basic.htm).

Save the alarm. If baseline CPU is below the threshold and data is arriving, the expected steady state is `OK`. Confirm the saved query still contains the exact `INSTANCE_OCID`; picking a VM name on another screen does not automatically rewrite a saved query.

### 6.3. Evaluation timeline example

Assuming the metric stream arrives completely:

| One-minute window | Average CPU | Condition `> 60` | Interpretation |
| --- | --- | --- | --- |
| 09:00–09:01 UTC | 12% | False | Normal |
| 09:01–09:02 UTC | 78% | True | Breach streak begins |
| 09:02–09:03 UTC | 82% | True | May satisfy trigger delay upon evaluation |
| 09:03–09:04 UTC | 80% | True | Breach continues |
| 09:04–09:05 UTC | 15% | False | Recovery condition appears |

This table illustrates evaluation logic and is not a guarantee that an email arrives at the exact second a window closes. Collection latency, metric ingestion, alarm evaluation, and notification delivery all add delay. Once the breach clears, the alarm can return to `OK` without waiting another full trigger-delay duration.

## 7. Test the CPU Alarm and Correlate with Logs

### 7.1. Generate time-bound CPU load

Execute only on the prepared lab VM. The snippet below spawns one busy loop per logical CPU and stops automatically after roughly seven minutes; it caps at four logical CPUs to avoid unexpected load on large machines. You can press `Ctrl+C` in the running session to stop early.

Run inside the SSH Bash session where `lab_log` is defined:

~~~bash
lab_log WARN cpu-load-started

(
  lab_cores=$(nproc)
  if [ "$lab_cores" -gt 4 ]; then
    printf 'Must use a lab VM with at most 4 logical CPUs.\n' >&2
    exit 1
  fi

  lab_cpu_pids=""

  stop_lab_load() {
    if [ -n "$lab_cpu_pids" ]; then
      kill $lab_cpu_pids 2>/dev/null || true
    fi
  }

  trap stop_lab_load EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  for lab_worker in $(seq 1 "$lab_cores"); do
    timeout --signal=TERM 420s sh -c 'while :; do :; done' &
    lab_cpu_pids="$lab_cpu_pids $!"
  done

  wait || true
  lab_cpu_pids=""
)

lab_log INFO cpu-load-ended
~~~

The `kill` command in the cleanup handler targets only PIDs of `timeout` processes spawned by this run. Never use `killall` or `pkill` with generic process names.

While generating load, use a second Console window to watch `CpuUtilization` and the alarm. If the VM uses shared CPU or burstable performance limits, observed CPU levels may differ from expectations. Adjust the test threshold below actual load and above baseline if needed, documenting the exact setting used. Do not resize the VM larger just to force an alarm to fire.

### 7.2. Verify each link in the chain

Capture the following evidence:

1. The CPU chart shows data for the right VM exceeding the threshold long enough.
2. History for `lab-cpu-high` records a `FIRING` state.
3. The email from Notifications contains the exact alarm name and corresponding state.
4. Logging Search locates `cpu-load-started` for the exact `LAB_RUN`.
5. After the load ends, CPU drops and the alarm returns to `OK`.
6. A corresponding recovery notification arrives and the `cpu-load-ended` marker is found.

If the load stopped before the breach lasted long enough, staying `OK` may be completely expected behavior. Inspect the chart before editing the alarm.

Log and alarm timestamps do not need to match to the exact second. Logs record when a marker was emitted; metrics reflect windowed aggregations; notifications carry delivery timestamps. Use UTC to align them on a single timeline.

### 7.3. Results recording template

| Event | Observed UTC timestamp | Evidence |
| --- | --- | --- |
| Load started | Fill during run | Log `cpu-load-started` |
| CPU exceeded threshold | Fill from chart | Query with exact `resourceId` |
| Alarm FIRING | Fill from history | Alarm name and OCID |
| FIRING email received | Fill from inbox | Notification body |
| Load ended | Fill during run | Log `cpu-load-ended` |
| Alarm returned to OK | Fill from history | Fresh metrics below threshold |

This template is to be filled with real results from your run, not pre-filled output. High CPU proves host load; concluding an application is failing additionally requires logs, functional checks, or application-level metrics.

## 8. Create a Missing-Metrics Alarm

### 8.1. Separate missing data from zero values

0% CPU is a measured value. Having no new metric points is a different condition: it may indicate an agent plugin, connectivity, IAM, or stopped-instance issue. A high-CPU alarm cannot replace monitoring data continuity.

Create a second alarm `lab-compute-metrics-missing`, using the same metric compartment, namespace, and destination topic, with the query:

~~~text
CpuUtilization[1m]{resourceId = "<INSTANCE_OCID>"}.groupBy(resourceId).absent()
~~~

Set a **5-minute** trigger delay and severity `WARNING`. The notification body should explicitly state "metrics are not being received", along with steps to check the plugin and connectivity. Do not claim the VM has definitely crashed.

`absent()` returns whether metrics are missing in the interval; `groupBy(resourceId)` groups streams per instance. A five-minute trigger delay requires the absence condition to persist as configured. The default two-hour **absence detection period** bounds how long absence values continue to emit during prolonged outages, not a two-hour wait before the first alert fires. Oracle explains these details in [Creating an Absence Alarm](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/create-alarm-absence.htm).

### 8.2. Simulate interrupting one metrics source

Perform this only after both alarms have baseline data and the CPU load test has finished:

1. Emit a marker on the VM: `lab_log WARN metrics-plugin-test-started`.
2. On the **Oracle Cloud Agent** tab, temporarily disable only **Compute Instance Monitoring** for the lab VM.
3. Leave **Custom Logs Monitoring** running.
4. Watch Metrics Explorer until new CPU data points stop arriving; historical data remains visible.
5. Wait for `lab-compute-metrics-missing` to transition to `FIRING` and check email.
6. Meanwhile, run `lab_log INFO logging-still-working` and find that marker in Logging.
7. Re-enable Compute Instance Monitoring immediately after capturing sufficient evidence.
8. Wait for fresh CPU points and confirm the missing-metrics alarm returns to `OK`.
9. Emit `lab_log INFO metrics-plugin-test-ended`.

Changing plugin state requires the instance-update permission mentioned in the IAM section. If your environment does not grant that permission, have an administrator perform the disable/enable steps during the same lab session while you create and verify the alarm.

Disabling only the target plugin keeps the logging path intact for observation. After the lab, confirm the plugin is running again, even if you had to abort testing mid-way.

If a metrics outage lasts longer than the absence detection period, do not treat alarm state alone as proof that the metric source recovered. Verify timestamps of new metric points as well. Likewise, receiving new logs only proves the logging path works, not that the metrics path works.

## 9. Automate Alarm Definition with OCI CLI

This section is an alternative to creating the CPU alarm in the Console, helping practice repeatable configuration. If you already created `lab-cpu-high` above, use the read command to inspect it or skip creation; do not create a duplicate copy just to test syntax.

Run in Bash inside Cloud Shell or a terminal with authenticated OCI CLI:

~~~bash
export REGION='<REGION>'
export COMPARTMENT_OCID='<COMPARTMENT_OCID>'
export INSTANCE_OCID='<INSTANCE_OCID>'
export TOPIC_OCID='<TOPIC_OCID>'

oci monitoring alarm create \
  --region "$REGION" \
  --compartment-id "$COMPARTMENT_OCID" \
  --metric-compartment-id "$COMPARTMENT_OCID" \
  --display-name 'lab-cpu-high' \
  --namespace 'oci_computeagent' \
  --query-text "CpuUtilization[1m]{resourceId = \"$INSTANCE_OCID\"}.mean() > 60" \
  --pending-duration 'PT2M' \
  --severity 'WARNING' \
  --destinations "[\"$TOPIC_OCID\"]" \
  --is-enabled true \
  --body 'LAB: Check CPU, instance OCID, and application logs in UTC.' \
  --query 'data.id' \
  --raw-output
~~~

Save the returned OCID in your lab records. To inspect the created definition:

~~~bash
export ALARM_OCID='<ALARM_OCID>'

oci monitoring alarm get \
  --region "$REGION" \
  --alarm-id "$ALARM_OCID"
~~~

`--compartment-id` selects where the alarm resource lives; `--metric-compartment-id` selects where metrics are read from. This lab intentionally passes the same value, though the two roles are distinct. `--destinations` takes a JSON array of topic OCIDs; `PT2M` is the ISO 8601 duration for two minutes. Parameters are documented at [OCI CLI: monitoring alarm create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/monitoring/alarm/create.html).

The `create` command creates a new resource rather than reconciling desired state. Across multiple environments, manage OCIDs, update existing resources, and parameterize configurations by region/compartment. Never embed personal lab OCIDs in shared templates.

## 10. Troubleshoot Along the Data Pipeline

A useful inspection order is **source → agent → permissions and network → receiving service → query → notification**. Change only one setting at a time so each effect is observable.

| Symptom | What to check first | How to resolve |
| --- | --- | --- |
| No `oci_computeagent` or CPU chart is empty | Region, compartment, plugin, and time window | Confirm right VM, running plugin, and service connectivity |
| VM CPU is high yet alarm stays OK | Window mean, threshold, dimension, and trigger delay | Read the saved query; cross-check with Monitoring data |
| Alarm is FIRING yet no email arrives | Target topic and subscription state | Verify `ACTIVE`, check spam, and publish a test message to the exact topic |
| Agent configuration created yet no logs arrive | Host group, matching rule, destination, and file path | Cross-check instance OCID, group, and absolute path |
| File has data yet Search shows nothing | File read permissions, agent status, and new entries | Inspect journald, then emit a fresh marker after config loads |
| Agent API access errors | Dynamic group, policy, and compartment scope | Verify VM principal and where config/destination log live |
| Search is empty yet agent looks healthy | Region, time range, scope, and field filter | Search the whole log first, then add filters one by one |
| Missing-metrics alarm fails to fire | Baseline data, plugin actually stopped, and interval | Check latest data point timestamp and wait enough evaluation cycles |
| Duplicate log entries appear | Multiple configurations or patterns tailing one file | Remove overlapping ingestion configurations |
| Alarm flaps continuously | Threshold too close to baseline or spiky load | Tune against observed data while preserving incident detection |

Useful log paths when troubleshooting on Oracle Linux:

~~~bash
sudo tail -n 50 /var/log/unified-monitoring-agent/unified-monitoring-agent.log
sudo tail -n 50 /var/log/oracle-cloud-agent/plugins/unifiedmonitoring/unifiedmonitoring.log
ls -ld /var/log/oci-lab
ls -l /var/log/oci-lab/app.log
date -u
~~~

Agent and plugin log locations are documented in [Troubleshooting Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/troubleshooting.htm). Diagnostic output may contain infrastructure identifiers; share only necessary excerpts when requesting support.

A CPU alarm and a `synthetic-failure` log entry at the same timestamp do not prove CPU caused an application error. In this lab, the error marker was emitted intentionally. In real incidents, gather request IDs, application state, and pre/post-event telemetry to test hypotheses.

## 11. Controlling Cost, Data Volume, and Availability

### 11.1. Bound collected data

This lab reads one file and emits a handful of markers. Avoid broadening inputs to `/var/log/**` before understanding volume and contents. Every added log source needs a defined purpose, authorized readers, and an appropriate retention policy.

Custom log retention in this lab is 30 days. Logging supports retention from 30 to 180 days; lowering retention can make older data unsearchable. Never increase retention afterward expecting to recover data that has already expired. See [Editing a Log](https://docs.oracle.com/iaas/Content/Logging/Task/update-logging-log.htm).

Monitor actual Compute usage, log volume, and companion services in your tenancy. Never assume the entire lab is always free. If adding long-term archival storage, define the target destination, retention duration, and data transfer costs before deploying.

### 11.2. Design actionable alerts

Every operational alarm needs an owner, resource context, and concise remediation steps. A test email arriving in an inbox does not prove someone is on call to act on it in time.

For scheduled maintenance, use time-bound suppression windows to control alerts and schedule a post-maintenance check. Suppression silences notifications; it does not heal agents, networks, or applications. After maintenance, inspect data sources and resource health.

In high-availability environments, deploy per-instance monitoring alongside functional service checks. A CPU metric on one VM reflects only one piece of the system; it does not represent end-user experience or the state of an underlying Oracle database.

### 11.3. Keep logs useful without leaking secrets

Markers in this lab contain no user data. In real applications, avoid writing tokens, passwords, private keys, or full sensitive payloads to logs. Standardize timestamps, severity levels, service names, and correlation IDs so issues can be investigated without over-collecting raw content.

## 12. Acceptance and Resource Cleanup

### 12.1. Lab completion criteria

| Item | Passing condition |
| --- | --- |
| Scope | Accurate region, compartment, and instance OCID recorded |
| IAM | Operator has scoped permissions; agent belongs to target dynamic group |
| Baseline metrics | Fresh `CpuUtilization` data points present for the VM |
| Notifications | Subscription `ACTIVE` and test message received |
| Custom log | Fresh markers found by `LAB_RUN` in Logging Search |
| CPU alarm | Evidence of `FIRING` and returning to `OK` after load test |
| Missing-metrics alarm | Evidence of firing when source stops and recovering when metrics resume |
| Post-test state | No synthetic CPU load running; required plugins re-enabled |
| Records | UTC timestamps, queries, threshold configs, and related evidence recorded |

Save actual results in your lab notes, masking identifying information if shared publicly. Never mark a step as passed merely because a resource was created.

### 12.2. Clean up in dependency order

After saving evidence:

1. Stop any remaining test load and confirm CPU returns to baseline.
2. Re-enable Compute Instance Monitoring if retaining the VM; confirm fresh metric points arrive.
3. Disable or delete both lab alarms to stop test notifications.
4. Disable and then delete agent configuration `lab-app-agent-config` to stop tailing the file.
5. Delete custom log `lab-app-log` and log group `lab-observability-logs` when data is no longer needed.
6. Delete the subscription and `lab-ops-alerts` topic if used solely for this lab.
7. Remove policies and dynamic groups created solely for this lab once no resources depend on them.
8. If retaining the VM, delete `/var/log/oci-lab/app.log` and the lab directory only after confirming the ingestion configuration is stopped and no data needs to be kept.
9. If the VM was created solely for this lab, terminate it per lab procedures and check boot volumes, extra volumes, or networking resources created alongside it.

Never delete shared groups, topics, policies, or VMs just because their names resemble lab resources. Deleting logs or VMs must happen only after required evidence is saved.

At wrap-up, you should be able to point to four verified links via observational evidence: **the VM emits signals, OCI ingests the telemetry, alarms evaluate conditions, and an operator receives notifications**. That foundation scales cleanly to multi-instance Compute fleets and other OCI services.

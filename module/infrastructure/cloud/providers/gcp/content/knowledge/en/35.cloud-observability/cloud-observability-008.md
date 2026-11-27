# Alerting Policies, Notification Channels, and Uptime Checks

A system can remain running while already starting to degrade: sustained high CPU, APIs returning errors, growing queues, TLS certificates nearing expiration, or endpoints becoming unresponsive. If operations teams only discover issues through user reports, downtime stretches out. Cloud Monitoring detects these signs using alerting policies, delivers alerts through notification channels, and verifies availability from multiple locations using uptime checks.

In Google Cloud, these three components work together. An alerting policy defines the condition requiring attention; a notification channel routes the alert to the responsible person or system; an uptime check actively sends periodic requests to an endpoint to confirm whether the service is reachable and returns expected content.

This lesson places these components in the context of Cloud Observability: monitoring the reliability of Compute Engine, GKE, Cloud Run, databases, APIs, and interconnected services. You will learn how to design meaningful alert conditions, select appropriate notification channels, and test public or internal endpoints.

In the CLOUD_PROVIDERS_GCP module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners practice choosing services, protecting resources, automating releases, and tracking reliability and cost. Alerting policies, notification channels, and uptime checks form the operational layer that turns observability data into timely action.

## Learning Objectives

After this lesson, you will be able to:

- Explain the relationship between an alerting policy, an alert/incident, and a notification channel.
- Distinguish between metric-based, log-based, and SQL-based alerting policies.
- Design thresholds, retest windows, alignment periods, triggers, and missing-data handling.
- Create policies using Google Cloud Console or the Google Cloud CLI.
- Select, verify, and protect notification channels.
- Distinguish between public uptime checks and private uptime checks.
- Configure HTTP, HTTPS, or TCP checks, response validation, and alerts when an endpoint is down.
- Investigate alerts, handle false positives, and establish reliable on-call workflows.

## 1. Three Components of the Alerting System

Cloud Monitoring uses three core components:

| Component | Role | Question Answered |
|---|---|---|
| Alerting policy | Defines the condition and how data is evaluated | When should an alert fire? |
| Alert or incident | Records an occurrence when a policy's condition is met | What event happened, when, and which resource is involved? |
| Notification channel | Defines where notifications are sent | Who or which system needs to know? |

An alerting policy can monitor metrics, log entries, or SQL query results. When the condition is satisfied, Cloud Monitoring opens an alert and sends notifications to the notification channels attached to the policy. A policy can attach multiple channels, such as email for the on-call team and Pub/Sub for automation systems.

Uptime checks serve as another data source in Cloud Monitoring. They send periodic HTTP, HTTPS, or TCP requests from multiple checker locations. The check results are stored as time series; alerting policies can use those time series to alert when an endpoint fails.

### Workflow

~~~mermaid
flowchart TD
    A[Applications and infrastructure] --> B[Cloud Monitoring metrics]
    A --> C[Cloud Logging entries]
    D[Uptime check: HTTP / HTTPS / TCP] --> B
    B --> E[Alerting policy]
    C --> E
    E --> F{Condition met?}
    F -->|No| G[Continue evaluating]
    F -->|Yes| H[Open alert / incident]
    H --> I[Notification channels]
    I --> J[Email / SMS / Slack / PagerDuty]
    I --> K[Webhook / Pub/Sub]
    J --> L[On-call engineer]
    K --> M[Ticketing / automation / SOC]
~~~

A notification channel only delivers alerts; it does not fix application bugs. An uptime check only verifies responsiveness as configured; it does not test the entire user experience or every internal business flow inside the application.

## 2. How Alerting Policies Work

An alerting policy is a configuration describing a condition indicating the system may be in an unhealthy state. A policy typically contains:

- **Display name:** a recognizable name, such as `API latency above 2 seconds`.
- **Conditions:** one or more conditions to evaluate.
- **Combiner:** how multiple conditions are combined.
- **Notification channels:** list of channels receiving notifications.
- **Severity:** priority level, such as WARNING, ERROR, or CRITICAL.
- **Documentation:** troubleshooting instructions attached to the notification.
- **User labels:** labels supporting filtering, grouping, and routing in operational workflows.
- **Alert strategy:** options for auto-close, notify on closure, and notification repetition for metric-based policies.

An alert can represent a single violating time series. If a policy monitors multiple VMs, multiple series can open multiple separate alerts. Therefore, decide whether you want per-instance alerts or data aggregated by zone, service, or application.

### Types of Monitorable Data

| Policy Type | Data Source | Example |
|---|---|---|
| Metric-based | Time series in Cloud Monitoring | CPU exceeds 80% for 5 minutes |
| Log-based | Log entries in Cloud Logging | An ERROR log matches a filter |
| SQL-based | SQL query results in Observability Analytics | Query counting errors per service exceeds threshold |
| PromQL-based | PromQL expressions over time series | Ratio of HTTP 5xx errors to total requests exceeds 5% |
| Metric absence | Absence of metric data over a defined window | Pipeline fails to emit a heartbeat for 30 minutes |
| Forecasted metric value | Time series forecast | Disk capacity is forecasted to exceed 80% within the next day |

Condition types and configuration capabilities can differ across the Console, API, and policy types. In particular, log-based alerting policies monitoring log entries directly differ from metric-based policies monitoring log-based metrics. To alert whenever a specific log entry appears, use a log-based alert. To alert on the count or rate of logs over a time window, create a log-based metric and use a metric-threshold policy.

### Metric Threshold and Metric Absence

**Metric threshold** opens an alert when a metric value rises above or drops below a threshold over a retest window. For example, CPU utilization greater than 0.8 for 300 seconds.

**Metric absence** opens an alert when a metric that previously reported data stops appearing for a configured duration. For example, a scheduled job that emits a heartbeat every 10 minutes fails to send data for 30 minutes.

Metric absence requires previously recorded data to identify the tracked time series. If a resource is deleted or shut down, Monitoring may not fire an absence alert as expected; understand resource states and metric semantics.

## 3. Designing Conditions: Threshold, Alignment, and Retest Window

A policy can alert too early if a condition relies on a single data sample. Conversely, it can alert too late if the evaluation window is too long. Three key concepts control that behavior.

### Alignment Period

The alignment period (rolling window in the Console) is the interval used to normalize raw points in a time series into aggregated points. For example, choosing 60 seconds with a mean aligner computes the average of points within each 60-second window.

Common aligners:

| Aligner | Meaning | Use Case |
|---|---|---|
| ALIGN_MEAN | Mean within the alignment period | CPU utilization or latency |
| ALIGN_MAX | Maximum value | Detecting spikes |
| ALIGN_MIN | Minimum value | Tracking remaining free capacity |
| ALIGN_SUM | Sum of values | Request or byte counts per interval |
| ALIGN_DELTA | Difference between start and end values | Counters or DELTA metrics |
| ALIGN_RATE | Rate of change over time | Throughput or error generation rate |

Choose an aligner matching the metric kind and value type. For example, applying mean to a DELTA metric may not carry the intended meaning; when tracking totals or rates, select an aligner suited to the data type.

### Retest Window

The retest window (condition duration) is how long the condition must remain continuously satisfied before the policy opens an alert. If CPU crosses 80% in a single sample and drops immediately, a policy with a 5-minute retest window avoids alerting on brief spikes.

- No retest: a single violating sample can open an alert immediately.
- 5-minute retest: data must continue violating throughout the entire evaluation window.
- Longer retest: reduces alerts from brief fluctuations, but increases detection latency.

Alignment period and retest window solve two distinct tasks: alignment aggregates data within each time series; retest determines how long the condition must persist.

### Trigger and Aggregation

The trigger specifies how many time series must violate for the condition to be met:

- **Any time series violates:** a single violating time series suffices.
- **Number of time series violates:** a specific count of time series must violate.
- **Percent of time series violates:** a percentage of time series must violate.
- **All time series violate:** every time series must violate.

Cross-series aggregation can merge multiple time series into one or group them by labels. For example, averaging CPU by zone reduces alert count but can mask a single overloaded VM. If the goal is catching a troubled instance, keep individual series or group by instance. If the goal is catching overall service degradation, group by service or zone.

### Combiner with Multiple Conditions

A policy can include multiple conditions. The combiner defines the logic across them:

- **OR:** any satisfied condition can open an alert.
- **AND:** all conditions must be satisfied.
- **AND_WITH_MATCHING_RESOURCE:** all conditions must be satisfied on the exact same monitored resource.

For example, a policy may watch high CPU and nearly full disk. Use OR if each problem requires independent handling. Use AND if you only want an alert when both symptoms occur together on one resource.

Do not bundle unrelated issues into one policy just to reduce policy count. Each alert should have a clear investigative focus and remediation path.

### Missing Data

When a metric stops sending data, Monitoring must decide whether to treat the condition as still met, unmet, or transitioning to missing-data state. Missing-data settings affect when alerts open and close.

Examples:

- For a CPU policy, a stopped VM may stop emitting metrics; treating missing data as a violation could create unnecessary alerts.
- For a heartbeat policy, missing data is precisely what you want to detect; use metric absence or configure missing-data handling appropriately.
- For a latency policy, stopped data may indicate a telemetry failure or application crash; maintain a separate policy monitoring data completeness.

Do not assume missing data means the system is healthy. Identify which data sources must always be present and which can legitimately disappear.

### Auto-Close, Acknowledgement, and Snooze

- **Auto-close:** Monitoring closes an alert when the condition is no longer met or when no new data arrives within the configured auto-close duration. The default for metric-based policies is 7 days; the minimum is 30 minutes.
- **Notify on alert closure:** optional notification sent when an alert closes. For policies created via Console, notifications are sent only when alerts open by default.
- **Acknowledge:** the on-call engineer confirms they have seen and started investigating the alert.
- **Snooze:** temporarily mutes notifications from a policy for a period, such as while operations handles an active outage. Snoozing does not fix the condition or resolve the incident.

When an alert closes, it may simply mean the condition returned to normal or auto-close expired. Check metric data and application health before concluding the incident is resolved.

## 4. Creating a Metric-Based Alerting Policy

Example: alert whenever CPU utilization on any Compute Engine VM stays above 80% continuously for 5 minutes.

### Preparation

- Select the project containing the VMs to monitor.
- Enable the Cloud Monitoring API if not already enabled.
- Confirm the `compute.googleapis.com/instance/cpu/utilization` metric has data.
- Prepare a notification channel.
- Grant Monitoring Editor (`roles/monitoring.editor`) to users creating or editing policies in the Console. For API usage, specialized roles such as Monitoring AlertPolicy Editor (`roles/monitoring.alertPolicyEditor`) can be used.

### Creating in Google Cloud Console

1. Open Google Cloud Console and select the project.
2. Go to Monitoring > Alerting.
3. Click Create policy.
4. Select the `CPU utilization` metric on resource type `VM instance`.
5. Add filters if monitoring only a specific zone, instance, or workload group.
6. Under Transform data, set rolling window to 60 seconds and function to mean.
7. Under Configure alert trigger, select Threshold, Above threshold, and value 0.8.
8. Set Retest window to 5 minutes.
9. Choose trigger Any time series violates to alert when any VM crosses the threshold.
10. Select notification channels, severity, and enable Notify on alert closure if operations teams want closure notifications.
11. Enter a name, add Documentation with VM inspection instructions, and create the policy.

### Creating with JSON and gcloud

A policy can be saved in a JSON file and created via the Google Cloud CLI. The example below uses an existing notification channel. Replace placeholders with actual project ID and channel ID:

~~~json
{
  "displayName": "VM CPU above 80 percent for 5 minutes",
  "combiner": "OR",
  "enabled": true,
  "severity": "WARNING",
  "conditions": [
    {
      "displayName": "CPU utilization above 80 percent",
      "conditionThreshold": {
        "filter": "metric.type=\"compute.googleapis.com/instance/cpu/utilization\" AND resource.type=\"gce_instance\"",
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0.8,
        "duration": "300s",
        "aggregations": [
          {
            "alignmentPeriod": "60s",
            "perSeriesAligner": "ALIGN_MEAN"
          }
        ],
        "trigger": {
          "count": 1
        }
      }
    }
  ],
  "notificationChannels": [
    "projects/PROJECT_ID/notificationChannels/CHANNEL_ID"
  ],
  "alertStrategy": {
    "autoClose": "604800s"
  },
  "documentation": {
    "mimeType": "text/markdown",
    "content": "CPU utilization has exceeded 80 percent for 5 minutes. Check the VM workload, recent deployments, CPU throttling, and request volume. Follow the service runbook before resizing or restarting the instance."
  }
}
~~~

Save the contents as `cpu-alert-policy.json`, then run:

~~~bash
gcloud monitoring policies create \
  --policy-from-file="cpu-alert-policy.json" \
  --project=PROJECT_ID
~~~

To list existing policies:

~~~bash
gcloud monitoring policies list --project=PROJECT_ID
~~~

To view details of a policy:

~~~bash
gcloud monitoring policies describe POLICY_ID \
  --project=PROJECT_ID
~~~

In JSON, `notificationChannels` holds the full resource name of the channel. Obtain the ID by listing notification channels in the project; do not guess channel IDs.

### Verifying the Policy

After creation:

- View the policy under Monitoring > Alerting.
- Confirm the metric has data and the filter selects the right resources.
- Check threshold, alignment period, retest window, and trigger.
- Verify channels are attached to the policy.
- Verify Documentation contains actionable instructions.
- Run a safe test scenario in a staging environment to confirm alert firing and notification delivery.

Do not artificially spike CPU on production VMs solely to test a policy. If you cannot reproduce test conditions, use historical data, a test metric, or an isolated lab VM.

## 5. Notification Channels

A notification channel specifies where Cloud Monitoring sends notifications when a policy opens an alert. Channels are created within a Google Cloud project and can be attached to one or more alerting policies within supported scopes.

Common channel types:

| Channel | Usage | Operational Notes |
|---|---|---|
| Email | Send to individuals or on-call groups | Groups must accept emails from `alerting-noreply@google.com` |
| SMS | Send text messages to verified phone numbers | Should not be used as the sole channel; delivery depends on region and carrier |
| Google Cloud console Mobile App | Push notifications to app devices or users | Channel scope is defined at creation |
| Slack | Post alerts to a Slack channel | Requires OAuth; private channels must invite the Google Cloud Monitoring app |
| PagerDuty | Integrate on-call paging and escalation | Partial two-way sync; resolving in PagerDuty does not close the alert in Monitoring |
| Webhook | Send HTTP requests to an external endpoint | Endpoint must be publicly reachable; HTTPS requires a valid certificate |
| Pub/Sub | Publish notifications to a topic for downstream systems | Requires service account publish permissions and a subscription to receive messages |
| Google Chat | Post alerts to a Chat space | Preview/Pre-GA feature; verify organizational eligibility before adopting |

### Choosing Channels by Purpose

- Email fits detailed notifications, audit history, and broad recipient groups.
- SMS or mobile apps fit waking on-call engineers for urgent attention; pair with a backup channel.
- Slack, Google Chat, or PagerDuty fit on-call workflows and team coordination.
- Webhook or Pub/Sub fits automated integrations such as ticket creation, enrichment, or workflow triggers.
- Pub/Sub fits when the receiving system resides in a private network or requires asynchronous processing.

Google recommends using multiple channel types for redundancy. Cloud Mobile App, PagerDuty, webhooks, and Slack share an underlying Google Cloud internal notification service, creating a common dependency. When using any of these channels, pair them with email or Pub/Sub as a backup channel. SMS should likewise never be used alone.

### Creating a Channel in the Console

1. Open Monitoring > Alerting.
2. Select Edit notification channels or Manage notification channels.
3. Choose the channel type to create.
4. Enter destination details and display name.
5. Complete provider authentication or authorization steps if prompted.
6. Click Send test notification if supported by the channel.
7. Save the channel and verify its status.
8. Return to the alerting policy, refresh the channel list, and attach the channel to the policy.

### Per-Channel Considerations

**Email**

Enter one email address per channel. When using a Google Group, configure the group to accept mail from `alerting-noreply@google.com`. Check spam/quarantine folders and organizational mail filtering rules.

**SMS**

Enter a phone number, send a verification code, and verify it. Only select verified phone numbers in policies. SMS may be unavailable in some regions and is not considered a guaranteed delivery channel.

**Slack**

Sign in to the workspace and authorize Cloud Monitoring. For private channels, invite the app with the following command in Slack:

~~~text
/invite @Google Cloud Monitoring
~~~

Send a test notification and confirm the message appears in the intended channel.

**PagerDuty**

Create or select a service in PagerDuty, add an Events API v1 integration, and copy the integration key into Cloud Monitoring's notification channel. Monitoring opens an incident in PagerDuty when an alert fires. Resolving the incident in PagerDuty while Monitoring's alert remains open may cause PagerDuty to reopen it. Do not assume closure state is fully synchronized between both systems.

**Webhook**

Webhook notifications support only public endpoints reachable by the notification service over the Internet. For HTTPS, the endpoint must present a TLS certificate verifiable by the service. Basic Authentication or URL tokens can be used per integration docs. Secure the endpoint, rotate tokens, and never log secrets. If an endpoint is reachable only inside a private network, use Pub/Sub and place a subscriber inside the appropriate network.

**Pub/Sub**

When creating a Pub/Sub channel for the first time in a project, Cloud Monitoring provisions a notification service account formatted as:

~~~text
service-PROJECT_NUMBER@gcp-sa-monitoring-notification.iam.gserviceaccount.com
~~~

This service account needs `roles/pubsub.publisher` on the topic. Prefer granting the role on the specific topic rather than project-wide whenever possible. Create a pull, push, or BigQuery subscription to consume notifications. If the topic lives in another project, enable APIs and configure IAM in that target project.

Example granting publish permission on a topic:

~~~bash
gcloud pubsub topics add-iam-policy-binding notification-topic \
  --project=PUBSUB_PROJECT_ID \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-monitoring-notification.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
~~~

If the topic enforces a message storage policy or data residency restrictions, Monitoring may fail to publish due to incompatible location requirements. Check for `FAILED_PRECONDITION` errors and topic policies before deployment.

### Protecting Notification Contents

Notifications can contain resource names, projects, metric info, labels, log context, and internal links. Therefore:

- Never put passwords, API keys, access tokens, or personal data in policy documentation.
- Send notifications only to groups and channels with appropriate access permissions.
- For webhooks, authenticate incoming requests and protect secrets.
- For Pub/Sub, restrict subscribers and topic read permissions.
- Review organizational data storage, retention, and compliance requirements.
- Never treat notifications as a long-term evidence archive; retain logs and incident records under dedicated policies.

## 6. Uptime Checks

An uptime check is an active probe: Cloud Monitoring sends periodic requests to an endpoint from multiple checker locations and evaluates the responses. It answers "is the endpoint responding according to configured criteria?" rather than merely "is the server running?".

Uptime checks can target:

- Public URLs.
- Compute Engine instances.
- App Engine applications.
- Kubernetes Services of type LoadBalancer.
- Cloud Run revisions.
- Certain AWS resources such as EC2 instances and Elastic Load Balancers.

Uptime checks use HTTP GET, HTTP POST, HTTPS, or TCP. They do not load images, CSS, or JavaScript, nor execute JavaScript on the page. Default configurations use no authentication.

### Public Uptime Checks

Public uptime checks test endpoints reachable over the Internet. They can target URLs, hostnames, or public IP addresses; for VMs or load balancers behind a firewall, allow traffic from uptime checker IP ranges.

Checkers are distributed across multiple regions. An uptime check requires at least three checkers. The USA region has three separate checkers in Oregon, Iowa, and Virginia; Europe, South America, and Asia Pacific have one checker per region. Selecting Global uses all available regions.

If only one checker fails due to transient network issues, the default policy does not send an alert. When creating an alerting policy from an uptime check, by default at least two regions must report continuous failure for at least one minute to trigger a notification.

Public uptime checks are not supported inside VPC Service Controls perimeters. If an endpoint resides in a private network or is restricted by a perimeter, use a private uptime check.

### Private Uptime Checks

Private uptime checks probe internal resources such as VMs or internal load balancers without exposing endpoints to the Internet. Private checks use Service Directory to resolve internal IP addresses and send HTTP, HTTPS, or TCP requests to endpoints inside a VPC.

Key prerequisites:

- Configure a Service Directory service with private network access.
- Enable required APIs such as Cloud Monitoring, Service Directory, Service Networking, and Compute Engine per documentation.
- Determine the project hosting the uptime check, the project hosting the Service Directory service, and the metrics scope if resources span multiple projects.
- Configure appropriate IAM permissions and VPC Service Controls.
- Ensure the internal endpoint actually responds to the configured request and port.

Private uptime checks can operate inside VPC Service Controls perimeters. They do not support ICMP pings. To test public endpoints, use public checks.

### HTTP, HTTPS, and TCP

| Protocol | What Is Checked | Example |
|---|---|---|
| HTTP | Sends GET or POST and checks status/content | `https://api.example.com/health` via HTTPS or an HTTP URL |
| HTTPS | Checks HTTP response and TLS certificate | API gateway or website with a TLS certificate |
| TCP | Checks whether a connection can be opened to the port | TCP service port, load balancer, or allowed database endpoint |

For HTTP/HTTPS, redirects are followed to the final response before evaluating success criteria. By default, 2xx status codes are considered successful. Accepted status codes can be customized if the application follows different conventions.

HTTPS checks validate SSL certificates as configured. Expired, self-signed, or hostname-mismatched certificates can cause the check to fail. Revoked certificates are not treated identically to invalid certificates in all cases; verify current checker behavior. The `monitoring.googleapis.com/uptime_check/time_until_ssl_cert_expires` metric can alert before a certificate expires.

Content matching verifies that the response contains expected content. For example, `/health` must return the string `ok`; the check succeeds only if the response matches per the chosen matcher. Matched content is limited to 1,024 bytes. For TCP checks, content matching must be enabled if response content verification is desired.

### Key Parameters

| Parameter | Meaning | Guidance |
|---|---|---|
| Check frequency | Interval between check runs | 1, 5, 10, or 15 minutes; default 1 minute |
| Checker regions | Locations sending requests | Select at least 3 checker locations; Global uses all |
| Response timeout | Time to wait for response | Set according to actual latency; increase to 30 seconds or more when following complex redirects |
| Path | HTTP/HTTPS request path | Prefer a lightweight, stable health endpoint |
| Port | Connection port | Default HTTP 80, HTTPS 443; must specify for TCP |
| Authentication | Credentials for HTTP/HTTPS | Basic Auth or Service Agent Authentication over HTTPS |
| Custom headers | Custom HTTP headers | Use when endpoints require headers; values can be masked/encrypted |
| Content matcher | Response body check | Choose strings or matchers aligned with a stable response |

Uptime checks can take up to 5 minutes for initial results to appear in Monitoring after configuration creation. During that period, dashboards may display no data available.

## 7. Creating an Uptime Check and Endpoint Alert

Example probing a public HTTPS endpoint of an API with a health route. Replace `YOUR_PUBLIC_HOST` with your application's hostname configured to respond from the Internet.

### Creating via Google Cloud Console

1. Select the project storing the uptime check.
2. Open Monitoring > Uptime checks.
3. Click Create Uptime Check.
4. Select protocol HTTPS and resource type URL.
5. Enter the hostname and path `/health`.
6. Choose Global or at least three checker locations.
7. Confirm SSL certificate validation is enabled.
8. Select response status 2xx and content matching if the endpoint returns a stable response body.
9. Choose an appropriate response timeout.
10. Click Test to verify configuration before saving.
11. Enable creating an alerting policy and select notification channels.
12. Name the uptime check and create it.

### Creating via gcloud

The following command creates a public HTTPS uptime check running every minute, probing `/health` and validating the TLS certificate:

~~~bash
gcloud monitoring uptime create "api-health-check" \
  --resource-type=uptime-url \
  --resource-labels=host=YOUR_PUBLIC_HOST,project_id=PROJECT_ID \
  --protocol=https \
  --path=/health \
  --period=1 \
  --timeout=10 \
  --validate-ssl \
  --project=PROJECT_ID
~~~

If the endpoint requires HTTP headers, add `--headers` and enable `--mask-headers` to conceal sensitive values in the configuration. Never place real secrets directly in shared shell command lines or unprotected shell history. If the endpoint requires authentication, consider Service Agent Authentication using OIDC tokens over HTTPS or configure Basic Authentication per organizational policy.

After creation, list checks to retrieve the ID:

~~~bash
gcloud monitoring uptime list --project=PROJECT_ID
~~~

The check ID is the final segment of the resource name in the configuration. Alerting policies use the `monitoring.googleapis.com/uptime_check/check_passed` metric and the `check_id` label to target the specific check.

### Creating an Alert for an Uptime Check

When creating an uptime check via the Console, you can enable alerting policy creation directly in the wizard. By default, the policy notifies when at least two regions report failed checks continuously for at least one minute.

If creating a policy separately, use the `monitoring.googleapis.com/uptime_check/check_passed` metric to track status. A value of 1 indicates a successful check; 0 indicates failure. Filter by `metric.label.check_id` to avoid mixing multiple uptime checks in one condition.

Example filter for a check with ID `api-health-check`:

~~~text
metric.type="monitoring.googleapis.com/uptime_check/check_passed"
AND metric.label.check_id="api-health-check"
AND resource.type="uptime_url"
~~~

To alert on an upcoming certificate expiration, create a separate policy using `monitoring.googleapis.com/uptime_check/time_until_ssl_cert_expires` and set the threshold in remaining days. Availability policies and certificate-expiry policies serve different goals, so give them separate names, severities, and runbooks.

## 8. Workflow for Investigating Alerts and Uptime Failures

When a notification arrives, the on-call engineer should quickly determine whether the alert reflects a service outage, a telemetry issue, or a checker issue.

### Investigating a Metric Alert

1. Open the incident link in the notification.
2. Review the policy, condition, severity, open timestamp, and state.
3. Inspect the time series in Alert details or Metrics Explorer.
4. Identify the monitored resource and labels, such as project, zone, instance ID, or service.
5. Check deployments, traffic, error rate, latency, CPU, memory, disk, and dependencies around the alert timestamp.
6. Correlate with logs and traces to pinpoint root cause.
7. Update the incident with owner and remediation actions.

If charts do not show the data point that triggered the alert, check ingestion delay, alignment period, and missing-data behavior. Log-based metric data can arrive delayed or be backfilled; overly short retest windows can cause erratic alerts.

### Investigating Uptime Failures

| Result | Possible Cause | What to Check |
|---|---|---|
| Connection refused | Web server not running or wrong port | Check service process, port, and listener |
| Name or service not found | Incorrect hostname or DNS | Check DNS records and resolvers |
| HTTP 403 | Endpoint requires auth or rejects checker | Check authentication, IAM, and access policies |
| HTTP 404 | Wrong path or nonexistent route | Check `/health` and routing |
| HTTP 5xx | Application or dependency error | Check application logs, backend, and load balancer |
| Timeout | Slow service, firewall block, or timeout too short | Check latency, firewall rules, and checker IPs |
| TLS/SSL error | Expired, self-signed, or hostname-mismatched certificate | Check certificate chain, hostname, expiry, and SSL config |
| Only one checker region failing | Transient network or regional routing issue | Compare results from other regions before declaring a global outage |

If the endpoint sits behind a firewall, allow traffic from Google's documented uptime-check server IP ranges. Do not open firewalls more broadly than necessary. On Cloud Run, ensure the principal or service agent used by the check holds `run.routes.invoke` permission when required by configuration.

### Acknowledge, Close, and Snooze

- Acknowledge when the on-call engineer begins investigating.
- Close the alert once the condition is no longer met or after verification and remediation.
- Snooze the policy when temporarily suppressing repeated notifications during a maintenance window or active incident response.
- Never mute or snooze to hide an uninvestigated failure.
- Record timestamps, root cause, impact, actions taken, and recovery outcome in the incident record.

## 9. Example Design for a Cloud Run Application

Suppose an e-commerce application runs on Cloud Run with a public `/health` endpoint and an API backed by Cloud SQL. An alerting design could include:

| Signal | Policy | Severity | Channels |
|---|---|---|---|
| Uptime check fails across multiple regions | Check fails continuously for at least 1 minute | CRITICAL | PagerDuty + email |
| HTTP 5xx increase | Error rate exceeds threshold for 5 minutes | ERROR | PagerDuty + Pub/Sub |
| High request latency | P95 latency exceeds SLO for 10 minutes | WARNING | Slack + email |
| CPU or instance pressure | Workload metric exceeds threshold | WARNING | Slack |
| Cloud SQL connection errors | Connection error count rises steadily | ERROR | PagerDuty + Pub/Sub |
| TLS certificate nearing expiration | Fewer than 15 days remaining | WARNING | Email + ticket |

This design separates availability, latency, error rate, and certificate-expiry alerts. Each policy has a dedicated owner and runbook. Uptime checks verify external user reachability; metrics and logs explain why requests are failing.

If the API has internal endpoints reachable only via VPC, create a private uptime check for those endpoints. Do not use a public uptime check to probe an internal IP. For authenticated Cloud Run services, use Service Agent Authentication over HTTPS and grant the necessary invoke permission.

## 10. Hands-On Testing and Cleanup

A small lab helps verify the full flow from telemetry data to notification delivery.

### Part A: Metric Alert

1. Use a lab VM emitting CPU metrics.
2. Create an email or Slack notification channel.
3. Create a short-duration low CPU threshold policy scoped solely to the lab VM.
4. Observe the time series and alert state.
5. Confirm notification receipt.
6. Restore the threshold to an appropriate operational level or delete the lab policy.

Do not generate artificial load on production VMs to trigger alerts.

### Part B: Uptime Check

1. Select a test endpoint with public access and a health route.
2. Create an HTTPS uptime check from at least three checker locations.
3. Configure response status and content matching.
4. Create an alerting policy for the uptime check and attach a channel.
5. Confirm notification when the test endpoint stops responding, if feasible in the lab.
6. Restore the endpoint and confirm the alert closes.
7. Delete the uptime check, policy, and channel if created solely for the lab.

### Part C: Pub/Sub

1. Create a topic and subscription in a sandbox project.
2. Create a Pub/Sub notification channel.
3. Grant `roles/pubsub.publisher` to the Monitoring notification service account on the topic.
4. Attach the channel to a lab policy.
5. Send a test notification or trigger a lab condition.
6. Confirm the message arrives in the subscription and inspect the payload.
7. Clean up lab resources when finished.

## 11. Common Configuration Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| Policy never opens an alert | Wrong metric filter or no data | Check metric type, resource type, and labels |
| Alert opens too early | Missing or overly short retest window | Choose a retest window matching metric cadence |
| Duplicate or noisy alerts | Multiple time series violating or multiple policy conditions | Check aggregation, trigger, and combiner |
| Alert never closes | Inappropriate missing-data behavior or auto-close setting | Check condition state, new data, and auto-close |
| Email notification not delivered | Group blocks sender or lands in spam | Allow `alerting-noreply@google.com` and check mail routing |
| SMS not delivered | Unverified number or unsupported region | Verify phone number and use a backup channel |
| Slack channel receives nothing | App not installed or not invited to private channel | Check OAuth and invite the Google Cloud Monitoring app |
| Wrong PagerDuty severity | Default mapping doesn't match Monitoring severity | Configure Event Orchestration rules |
| Webhook connection error | Private endpoint or invalid TLS certificate | Use a public HTTPS endpoint or switch to Pub/Sub |
| Pub/Sub receives no messages | Missing Pub/Sub Publisher role or wrong topic/project | Check service account, IAM, and subscription |
| Uptime check fails while site loads | Checker blocked, wrong path/auth, or single-region error | Compare checker locations, firewalls, and response criteria |
| Uptime check has no data | Newly created check or wrong target | Wait a few minutes and verify configuration |
| Private check fails | Service Directory lacks private network access or missing API/IAM | Check Service Directory, VPC, and metrics scope |
| TLS check fails | Expired, self-signed, or hostname-mismatched certificate | Inspect certificate chain and DNS name |

## 12. Best Practices for Designing Alerting

- **Alert on user impact:** prioritize availability, latency, error rate, and saturation over raw resource utilization alone.
- **Map severity to action:** CRITICAL should page on-call; WARNING can go to a team channel or ticket.
- **Write actionable documentation:** specify symptoms, dashboards, log queries, owner, and runbook.
- **Use intentional retest windows:** balance detection speed against false positives.
- **Monitor telemetry pipelines:** policies depend on incoming data; monitor separately when metrics or logs stop arriving.
- **Scope alerts per service:** avoid overly broad policies with unclear ownership.
- **Configure backup channels:** combine channels with independent delivery mechanisms.
- **Test channels:** send test notifications and confirm on-call engineers actually receive them.
- **Protect notification payloads:** never put secrets or sensitive information inside alert messages.
- **Respect public/private boundaries:** use public uptime checks only for public endpoints; use private checks for internal resources.
- **Do not automate remediation on every alert:** start with enrichment, ticketing, and notifications; automate infrastructure changes only with guardrails, approvals, and rollback.
- **Review periodically:** remove unused policies, broken channels, outdated recipients, and stale thresholds.

## Conclusion

Alerting policies turn metrics, logs, and query results into incident detection conditions. Notification channels deliver alerts to on-call engineers or automated systems. Uptime checks actively verify endpoint responsiveness from multiple locations and pair with alerting policies to warn when services become unreachable.

A useful alerting system requires reliable data, conditions tuned to application behavior, redundant notification channels, and clear runbooks. Start from indicators that directly affect users, test the entire notification pipeline in a separate environment, and review regularly so every alert has clear accountability.

## References

- [Cloud Monitoring alerting overview](https://cloud.google.com/monitoring/alerts)
- [Create metric-threshold alerting policies](https://cloud.google.com/monitoring/alerts/using-alerting-ui)
- [Create alerting policies by using the API](https://cloud.google.com/monitoring/alerts/policies-in-api)
- [Sample alerting policies in JSON](https://cloud.google.com/monitoring/alerts/policies-in-json)
- [Create and manage notification channels](https://cloud.google.com/monitoring/support/notification-options)
- [Control access with IAM](https://cloud.google.com/monitoring/access-control)
- [Create public uptime checks](https://cloud.google.com/monitoring/uptime-checks)
- [Create private uptime checks](https://cloud.google.com/monitoring/uptime-checks/private-checks)
- [gcloud monitoring uptime create](https://cloud.google.com/sdk/gcloud/reference/monitoring/uptime/create)
- [Troubleshoot alerting policies](https://cloud.google.com/monitoring/alerts/troubleshooting-alerts)

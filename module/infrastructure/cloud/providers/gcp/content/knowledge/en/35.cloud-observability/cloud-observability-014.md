# Error Reporting and Application Error Aggregation

When an application running on Google Cloud throws an exception, the error may appear in logs from Cloud Run, GKE, Compute Engine, or another service. Reading individual log lines in isolation makes it hard for operations teams to tell which errors recur, which ones are newly introduced, and which deserve priority. **Error Reporting** solves this by detecting error events and grouping them into error groups based on signatures close to the root cause.

In the **CLOUD_PROVIDERS_GCP** module, Error Reporting is part of observing and operating cloud services. It helps development and SRE teams spot application errors, track recurrence trends, link errors to logs, and notify responsible owners. Error Reporting works alongside Cloud Logging and Cloud Monitoring; each service provides a different view of system health.

After this lesson, you will be able to:

- Distinguish between an error event, an error group, and error group stats.
- Choose an error collection approach suited to your deployment environment.
- Format logs so Error Reporting recognizes exceptions and stack traces.
- Explain how Error Reporting groups errors and estimates occurrence counts.
- Establish workflows for reviewing, assigning, resolving, and tracking recurring errors.
- Configure access permissions, notifications, and evaluate limitations in multi-project setups.

## 1. Error Reporting in the Cloud Observability Architecture

Error Reporting is a service that aggregates and displays application errors across cloud workloads. Data can enter via two paths:

1. **Log analysis**: the application writes exceptions or stack traces to Cloud Logging. Error Reporting scans matching log entries to extract error events.
2. **Direct reporting**: the application or a client library calls the Error Reporting API to report an error event.

The data model consists of three components:

| Component | Meaning | Example |
|---|---|---|
| Error event | A single occurrence of an error, including timestamp, execution context, and error message | A checkout request throws `NullPointerException` |
| Error group | A group of events sharing indicators of a common root cause | `NullPointerException` occurrences on the same call path in `CartService` |
| Error group stats | Statistics for an error group over time | First/last seen timestamps, occurrence count, affected user count |

High-level processing flow:

~~~mermaid
flowchart TD
    A["Apps on Cloud Run, GKE, Compute Engine..."] --> B{"Error delivery method"}
    B --> C["Log exception / stack trace"]
    B --> D["Client library or Error Reporting API"]
    C --> E["Cloud Logging"]
    D --> E
    E --> F["Error Reporting analyzes error events"]
    F --> G["Group by root-cause signature"]
    G --> H["Error Reporting: view, filter, triage"]
    H --> I["Link issues and track fixes"]
    H --> J["Cloud Monitoring notification channels"]
    E --> K["Logs Explorer: inspect individual log entries"]
~~~

Error Reporting does not replace Cloud Logging or Cloud Monitoring:

- **Error Reporting** answers: which application errors are repeating, which groups are newly appearing, and which previously resolved groups have regressed?
- **Cloud Logging** stores and queries detailed log entries, including requests, traces, payloads, and operational context.
- **Cloud Monitoring** tracks metrics, uptime, SLOs, and alerting policies. It alerts when error rates, latency, or other metrics cross thresholds.

An error group helps surface an issue, while logs and traces provide the context to identify the cause. For Android and iOS mobile apps, Google recommends Firebase Crashlytics to track device-side crashes.

## 2. Collecting Error Events

### 2.1. Automatic Collection via Cloud Logging

This is usually the simplest option when the runtime already ships logs to Cloud Logging:

- Cloud Run automatically forwards exceptions and stack traces written to `stdout` or `stderr` into Cloud Logging. Error Reporting detects supported stack traces.
- Cloud Run functions write unhandled exceptions to Cloud Logging; Error Reporting can detect stack traces from those entries.
- On GKE and Compute Engine, applications must write logs in supported formats and the environment must ship logs to Cloud Logging, such as through an appropriate logging agent or built-in platform integration.
- App Engine has built-in collection per standard and flexible environment behavior.

Do not assume every log line containing `ERROR` automatically becomes an error event. Error Reporting needs a stack trace in a supported language format or a payload structured as a `ReportedErrorEvent`.

### 2.2. Instrumenting Applications with Client Libraries

Client libraries are helpful when:

- The application catches exceptions and handles them before the runtime logs a stack trace.
- You need to attach service name, version, or request details.
- Existing logs lack a format recognized by Error Reporting.
- You want to proactively emit error events from a shared component.

Google Cloud provides guides and libraries for languages including Java, Go, Node.js, Python, .NET, PHP, and Ruby. Use the library matching your runtime and authenticate with a service account or Application Default Credentials. Never embed service account keys in source code or container images.

### 2.3. Sending Directly via the Error Reporting API

Applications can call the `report` method of the Error Reporting API with a `ReportedErrorEvent` object. This fits when applications need explicit control over event creation or cannot rely on automatic log parsing.

Enable the API in the project:

~~~bash
gcloud services enable clouderrorreporting.googleapis.com \
  --project=PROJECT_ID
~~~

Enabling the API requires `serviceusage.services.enable`. When using the Error Reporting API, properly formatted log entries are also written to Cloud Logging under a log name like:

~~~text
projects/PROJECT_ID/clouderrorreporting.googleapis.com%2Freported_errors
~~~

Log entries generated via the API can incur Cloud Logging ingestion charges. You can control ingested log volume with log exclusion filters aligned with your organization's retention and investigation policies.

Note: having the API disabled does not stop Error Reporting from displaying all errors. Error Reporting can still infer error events from log entries if logs satisfy parsing conditions. The API must be enabled when applications directly call the reporting endpoint.

## 3. Formatting Logs for Error Reporting Detection

When logging via Cloud Logging, a `LogEntry` must contain a stack trace or a `ReportedErrorEvent`-structured payload.

### 3.1. Logging Stack Traces

Error Reporting can extract stack traces from:

- Multi-line `textPayload`.
- `jsonPayload` containing one of the fields `message`, `stack_trace`, or `exception`.
- Another field in `jsonPayload` containing a stack trace in a supported language format.

If a payload contains multiple fields, parsing priority is `stack_trace`, then `exception`, then `message`. When parsing the `message` field, its content must include a stack trace in a supported format. Malformed stack traces may go unrecognized.

Example JSON payload for a Java application:

~~~json
{
  "serviceContext": {
    "service": "checkout-api",
    "version": "2026.11.19"
  },
  "message": "java.lang.IllegalStateException: Cannot complete checkout\n\tat com.example.checkout.OrderService.submit(OrderService.java:84)\n\tat com.example.checkout.CheckoutController.create(CheckoutController.java:51)",
  "context": {
    "httpRequest": {
      "method": "POST",
      "url": "/v1/checkout",
      "responseStatusCode": 500
    }
  }
}
~~~

`serviceContext.service` is a required field of `ReportedErrorEvent`; `version` helps identify the associated release. HTTP metadata helps operators understand the failing request. When a log includes a valid stack trace inside `message`, `@type` does not need to be added.

### 3.2. Logging Error Messages Without a Stack Trace

If you only have an error message, mark the payload as `ReportedErrorEvent` using the exact `@type` value:

~~~json
{
  "@type": "type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.ReportedErrorEvent",
  "serviceContext": {
    "service": "inventory-worker",
    "version": "2026.11.19"
  },
  "message": "Inventory reservation failed: warehouse is unavailable",
  "context": {
    "reportLocation": {
      "filePath": "src/inventory/reservation.ts",
      "lineNumber": 42,
      "functionName": "reserveInventory"
    }
  }
}
~~~

When no stack trace exists, `context.reportLocation` supplies the error origin. For payloads containing only a plain text message, `@type` tells Cloud Logging to treat the entry as an error event. If `@type` has another value or is missing, Cloud Logging looks for `serviceContext` to decide whether the payload represents a `ReportedErrorEvent`.

Set log severity to `ERROR` for exceptions needing investigation. Choose a monitored resource type matching your environment, such as `cloud_run_revision`, `k8s_container`, `k8s_pod`, or `gce_instance`. Some resource types have specific constraints; for example, `global` does not support `textPayload`.

### 3.3. Keeping Information Consistent and Safe

Data quality governs grouping accuracy:

- Use stable service names like `checkout-api`; never generate a new service name per request.
- Record version or revision to compare errors before and after releases.
- Keep stack traces intact, preserving the exception type and application code frames.
- Avoid placing request IDs, timestamps, emails, order IDs, or random values at the start of the message. Variable prefixes split identical errors into separate groups.
- Never write access tokens, session cookies, passwords, payment details, or unnecessary personal data into logs and error events.
- Attach trace ID or request ID in appropriate context fields to find related logs; never use them as service names or primary error messages.

## 4. How Error Reporting Aggregates Errors

Error Reporting applies grouping rules in order. Grouping behavior depends on error event content:

| Event Type | Grouping Method |
|---|---|
| Environment errors or certain specific exceptions | By exception type |
| Events with a stack trace | By exception type and the top five stack frames; for nested exceptions, evaluates the innermost exception |
| Events without a stack trace but with a message | By message and function name if present; only the first three literal tokens of the message are considered |

Before grouping, Error Reporting may collapse repeated stack frame sequences and strip compiler-generated methods or symbols. Frames belonging to public libraries rather than user code may be ignored during analysis.

For example, multiple requests throw `java.lang.NullPointerException` along the same call path `CartService.loadCart()` and `CheckoutController.create()`. Even though each request has a different request ID and timestamp, the exception type and top frames match, so events are grouped into one error group. Grouping focuses attention on the shared cause instead of creating an item per request.

For messages without a stack trace, only the first three tokens are used for grouping. For example:

- `Payment gateway unavailable for order 123` and `Payment gateway unavailable for order 456` share the same opening tokens and can be grouped together.
- `Order 123 payment gateway unavailable` and `Order 456 payment gateway unavailable` start with different tokens and can split into separate groups.

Therefore, place the stable error description at the beginning of the message and move variable data into context or separate fields. Do not alter stack traces to force distinct root causes into the same group.

### Sampling and Displayed Counts

To optimize performance, Error Reporting samples up to 1,000 errors per hour and estimates counts once that threshold is reached. When event volume exceeds processing capacity, the system samples up to 100 errors per hour and continues extrapolating displayed counts. An error group retains up to 1,000 sample events; to inspect individual occurrences, query related logs in Logs Explorer.

Because of sampling, counts shown on the Error Reporting page can be estimates. When investigating an exact request, cross-check log entries, traces, and service metrics. Error events submitted via the API are guaranteed to remain accessible for at least 30 days from creation.

## 5. Viewing and Managing Error Groups

In Google Cloud Console, open **Error Reporting** and select the project to investigate. The overview lets you sort, filter, and browse error groups by error name, resolution status, HTTP response code, and occurrence count over time.

Opening an error group reveals:

- History of error events and occurrence timestamps.
- Occurrence counts and resolution status.
- Sample events, messages, and stack traces if present.
- Links to corresponding log entries in Logs Explorer.
- Links to an issue tracker or remediation documentation.

Logs Explorer allows filtering by error group ID, for example:

~~~text
errorGroups.id="ERROR_GROUP_ID"
~~~

The `errorGroups` field appears only on log entries stored in log buckets and enriched by the bucket destination. Do not assume every log entry sent to a project or passing through a log sink carries this field.

### Resolution Status

| Status | Meaning | When to Use |
|---|---|---|
| Open | Default status, awaiting handling | New errors or errors needing investigation |
| Acknowledged | Assigned/claimed by someone | On-call team has acknowledged and begun triage |
| Resolved | Fixed and not expected to recur | After verifying a fix |
| Muted | Hidden from the error list | Group assessed as not needing tracking here |

If an error group marked Resolved receives a new event, Error Reporting transitions it back to Open. For Muted groups, new events are not recorded and trigger no notifications. Therefore, think carefully before muting errors; muting can hide recurrence signals from monitoring workflows.

## 6. Configuring Notifications and Triage Workflows

Error Reporting can send notifications via Cloud Monitoring notification channels, including email, the Google Cloud mobile app, Slack, and webhooks. Channels are created in Monitoring and selected in Error Reporting's notification settings.

Notifications are sent in two cases:

1. An error event does not match any existing error group, meaning a new error group appeared.
2. A Resolved error group emits an error again, meaning a regression occurred.

Error Reporting does not send notifications for every repeated event inside an Open or Acknowledged group. The system also enforces notification rate limits: at most 20 notifications per project within a 60-minute window. If exceeded, operations receives a notice that notifications are paused for six hours and a `WARNING` log entry is recorded. Immediately after marking a group Resolved, notifications for that group are paused for five minutes.

Recommended triage workflow:

1. **Identify**: inspect the new error group, impact level, start time, and affected service/version.
2. **Assess scope**: check occurrence counts, upward trends, HTTP status codes, and impacted workloads.
3. **Investigate**: open sample events, stack traces, log entries, and traces for affected requests.
4. **Assign**: transition status to Acknowledged, link an issue tracker ticket, and assign the owning team.
5. **Remediate**: fix code or configuration, test, and deploy the patch.
6. **Verify**: inspect post-release logs and metrics; once errors stop recurring, mark Resolved.
7. **Watch for regressions**: if the error returns, Error Reporting reopens the group and notifies per configuration.

Error Reporting notifications help catch newly emerging error groups or regressions. To alert on error rates, failed request counts, latency, or SLOs, create dedicated alerting policies in Cloud Monitoring.

## 7. IAM and Multi-Project Architecture

Assign permissions according to real operational roles rather than granting broad admin roles to everyone:

| Role | Purpose |
|---|---|
| `roles/errorreporting.viewer` | Read-only viewing of error groups and events |
| `roles/errorreporting.user` | Read, update metadata, and manage error groups; excludes permission to report new events |
| `roles/errorreporting.writer` | Grants a service account permission to report error events via the API |

Current IAM documentation marks these Error Reporting roles as Beta. Enabling the API requires `serviceusage.services.enable`. When configuring notifications, the user needs `roles/errorreporting.user`, `roles/monitoring.viewer` to view channels, and `roles/monitoring.editor` to create channels if needed. Verify permissions per project and use custom roles when narrower scoping is needed.

### Aggregating Errors in a Multi-Project Model

An organization may separate projects by environment or domain:

- `app-dev`: development environment.
- `app-staging`: integration testing environment.
- `app-prod`: production environment.
- `observability-prod`: centralized logging and observability project.

Each application needs a clear service context, such as `checkout-api` and release version. Cloud Logging sinks can route logs to a centralized project. For Error Reporting to analyze logs, the log bucket must belong either to the project where the log originated or to the receiving project after routing, stored in a bucket owned by that receiving project itself. If a sink forwards logs to another project but stores them in a bucket owned by a third project, Error Reporting may fail to analyze those logs.

Clearly define which project owns the log bucket, sink write permissions, log read permissions, and where on-call engineers open Error Reporting. Do not assume one Error Reporting page automatically aggregates errors across every project in the organization; intentionally design log routing paths and target projects.

### CMEK, Assured Workloads, and Regional Limitations

Error Reporting is a global service built on Cloud Logging. For log-based collection, the following conditions must hold:

- Assured Workloads must not be enabled for the workload. When Assured Workloads is configured for data residency or Impact Level 4, Google Cloud automatically disables Error Reporting.
- Log buckets storing entries to be analyzed must not use customer-managed encryption keys (CMEK). Error Reporting cannot store log entries in CMEK-enabled buckets.
- Log buckets must reside in the originating project or in the receiving project after routing, inside a bucket owned by that project.

VPC Service Controls supports Error Reporting. If your organization enforces data-perimeter controls, include Error Reporting in the appropriate service perimeter design. Log buckets can be regionalized; Error Reporting displays error groups by bucket region, though Error Reporting itself is a global service and error groups remain accessible from any region. If residency rules forbid this behavior, evaluate Error Reporting suitability before deployment.

## 8. Real-World Scenario: Post-Release Checkout Error Spike

A `checkout-api` service running on Cloud Run just deployed version `2026.11.19`. Minutes later, the HTTP 500 rate rises. On-call opens Error Reporting and spots a new `IllegalStateException` group climbing rapidly in occurrences.

Response workflow:

1. Open the error group and identify the failing version. If errors occur solely on the new version, prioritize diffing changes from that release.
2. Open the stack trace and jump to the linked log entry in Logs Explorer. Use trace ID or request ID to inspect logs before and after the failed request.
3. Check request count, HTTP 5xx, and latency metrics in Cloud Monitoring to measure impact.
4. Link the error group to an issue tracker ticket, mark it Acknowledged, and assign it to the checkout team.
5. If caused by a cart-handling change, ship a fix or roll back following release procedures.
6. Monitor the error group and metrics after the change. Once errors cease over a window representative of real traffic, mark the group Resolved.
7. If the error returns, notifications flag the regression and the group reopens to Open.

Processing flow diagram:

~~~mermaid
flowchart TD
    A["Release new version"] --> B["HTTP 500 spikes"]
    B --> C["Error Reporting creates / updates error group"]
    C --> D["Read stack trace and related logs"]
    D --> E["Correlate metrics, traces, and release changes"]
    E --> F["Fix bug or roll back"]
    F --> G["Verify via logs and metrics"]
    G --> H{"Error still recurring?"}
    H -->|Yes| D
    H -->|No| I["Mark Resolved"]
    I --> J["Monitor regression notifications"]
~~~

### Quick Verification in a Test Environment

You can send a test error using the Google Cloud CLI to confirm delivery to Error Reporting:

~~~bash
gcloud beta error-reporting events report \
  --service checkout-api \
  --service-version test-1 \
  --message="java.lang.IllegalStateException: Test checkout failure
    at com.example.checkout.OrderService.submit(OrderService.java:84)
    at com.example.checkout.CheckoutController.create(CheckoutController.java:51)"
~~~

Open Error Reporting in that project and locate the `IllegalStateException: Test checkout failure` group. Check Logs Explorer to verify the log entry was created. Run this command only in test projects or approved testing workflows; never inject fake errors into production just to test notifications.

## 9. Troubleshooting Common Issues

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Error Reporting page is empty | No error groups yet or no matching logs | Send a test error event; verify the selected project |
| Called API but no event appears | API disabled, missing permissions, or invalid payload | Check `clouderrorreporting.googleapis.com`, event reporting permissions, and `ReportedErrorEvent` format |
| Log has stack trace but isn't grouped | Malformed stack trace or placed in non-prioritized field | Check `message`, `stack_trace`, `exception`; format stack trace per supported language |
| Log has message without stack trace | Plain text payload missing `@type` or valid `serviceContext` | Format payload as `ReportedErrorEvent`; provide `reportLocation` if lacking stack trace |
| Cloud Run errors missing | Exceptions not written to `stdout`/`stderr` or logs lack stack traces | Check runtime logs; consider client library or structured logging |
| Cross-project errors unanalyzed | Log sink routes to bucket owned by another project or CMEK enabled | Check sink destination, bucket owning project, and CMEK settings |
| Occurrence counts don't match log counts | Error Reporting samples and extrapolates counts | Use Logs Explorer to inspect individual log entries |
| Notifications not received | Group is Open/Acknowledged, Muted, or hit rate limit | Check group status, notification channels, and rate-limit warning logs |

When debugging log-based collection, also check:

1. Whether the log entry was actually written to Cloud Logging.
2. Whether severity and monitored resource type are appropriate.
3. If `jsonPayload` contains `stack_trace`, `exception`, and `message`, which field is parsed according to priority order.
4. Whether the project owning the log bucket matches the originating project or the post-routing receiving project.
5. Whether CMEK is enabled on any bucket storing that log entry.
6. Whether the workload belongs to Assured Workloads.
7. Run `gcloud logging sinks list` to verify where logs are routed.

## 10. Best Operational Practices

- Standardize service names, versions, and log schemas across services.
- Log exceptions with stack traces and useful context; avoid generic messages like `Something went wrong`.
- Keep opening error messages consistent so failures with the same cause group together.
- Never log secrets, tokens, or unnecessary personal data.
- Combine Error Reporting with Logs Explorer, Cloud Trace, and Cloud Monitoring to determine root cause and impact.
- Set up notifications for new groups and regressions; use alerting policies for error rates and SLOs.
- Link issue tracker tickets to error groups to preserve history and ownership.
- Mark groups Resolved only after verification; use Muted only once you understand the effect of suppressing new events in that group.
- In multi-project architectures, test log routing, IAM permissions, bucket ownership, and CMEK constraints before production rollout.
- Monitor Cloud Logging costs when reporting events via the API and tune log exclusion filters to match investigative needs.

## 11. Self-Check

1. Distinguish between an error event and an error group. Why can an error group contain many events?
2. What are the ways to send application errors to Error Reporting?
3. Given a `jsonPayload` containing `stack_trace`, `exception`, and `message`, which field does Error Reporting prioritize?
4. Why should error messages begin with a stable description of the failure?
5. When an error group marked Resolved reappears, how does Error Reporting handle it?
6. Why might Error Reporting fail to analyze logs stored in a CMEK-enabled log bucket?
7. When occurrence counts in Error Reporting differ from log entry counts, which tool should you use for exact verification?

**Suggested Answers**

1. An error event is a single error occurrence; an error group aggregates events sharing root-cause signatures to aid investigation.
2. Automatic collection via Cloud Logging, client libraries, the Error Reporting API, or logging properly formatted entries via the Cloud Logging API.
3. `stack_trace`, then `exception`, then `message`.
4. Grouping for messages without stack traces evaluates only the first three literal tokens; variable data at the start splits identical errors into multiple groups.
5. The group transitions back to Open and can trigger a regression notification per configuration.
6. Error Reporting cannot store log entries in CMEK-enabled buckets; log-based collection cannot parse those entries.
7. Use Logs Explorer to query individual log entries and correlate timestamps, requests, or traces.

## References

- [Google Cloud: Error Reporting overview and grouping](https://docs.cloud.google.com/error-reporting/docs/grouping-errors)
- [Google Cloud: Collect error data](https://docs.cloud.google.com/error-reporting/docs/setup)
- [Google Cloud: Format a log entry to report error events](https://docs.cloud.google.com/error-reporting/docs/formatting-error-messages)
- [Google Cloud: View and filter error groups](https://docs.cloud.google.com/error-reporting/docs/viewing-errors)
- [Google Cloud: Manage error groups](https://docs.cloud.google.com/error-reporting/docs/managing-errors)
- [Google Cloud: Configure and manage notifications](https://docs.cloud.google.com/error-reporting/docs/notifications)
- [Google Cloud: Troubleshoot Error Reporting](https://docs.cloud.google.com/error-reporting/docs/troubleshooting)
- [Google Cloud: Error Reporting roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/errorreporting)

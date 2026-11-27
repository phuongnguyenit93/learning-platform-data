# Synthetic Monitoring and User Transaction Monitoring

## 1. Operational Goal and Scenario

An ordering portal running on Oracle Cloud Infrastructure (OCI) has a Load Balancer, a Java application on Compute, and an Oracle database inside a private network. CPU stays low and hosts remain up, yet users log in and cannot view their orders. Running infrastructure alone is not enough to conclude that a business transaction is usable.

In the **Logs, Metrics, and Tracing** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson connects infrastructure health to application user experience. After this lesson, learners can:

- Choose critical transactions for periodic checks and define expected outcomes clearly.
- Distinguish synthetic monitoring from Real User Monitoring (RUM).
- Design monitors in OCI APM and select vantage points suited to public or VCN networks.
- Combine check results with metrics, traces, and logs to isolate incidents.
- Operate monitors with appropriate access controls, test data, and cost management.

Synthetic monitoring generates controlled test traffic in place of real customer actions. In OCI Application Performance Monitoring (APM), the feature set formerly named **Synthetic Monitoring** was renamed **Availability Monitoring**. This lesson still uses the term "synthetic" to refer to the active probing methodology. [Oracle Rename Announcement](https://docs.oracle.com/en-us/iaas/releasenotes/apm/availability-monitoring.htm).

Application names, URLs, thresholds, and schedules in this lesson are illustrative design examples. They must be adapted to real systems.

## 2. Three Perspectives on a Transaction

**Synthetic monitoring** answers: "From the chosen location, can a standard scenario complete right now?" Monitors can run even when the application has zero active visitors.

**Real User Monitoring** answers: "What experience are real users currently having with the application?" Results reflect devices, browsers, networks, and the actual paths real users take.

**Server-side tracking** answers: "Which components did a request pass through, and where was time spent?" Traces explain slow requests; logs add concrete processing details.

| Perspective | Input data | Typical question | Limitation to remember |
| --- | --- | --- | --- |
| Synthetic | Selected scenario and test data | Can a user log in and look up an order? | Reflects only configured paths and vantage points |
| RUM | User activity generating telemetry | Which user segment sees slow pages or JavaScript errors? | Zero visibility when traffic is absent or the agent is blocked |
| Server-side traces and logs | Instrumented requests and operational logs | Is the failure in auth, app logic, or Oracle Database queries? | Does not fully capture browser rendering and interaction |

A REST monitor returning HTTP 200 does not prove the "Confirm" button works. A browser monitor passing from a data center does not prove mobile-network customers have a good experience.

Synthetics typically generate light scheduled traffic to observe service health. Active load testing generates high traffic and concurrency to find capacity limits. Never spin up masses of monitors as a substitute for a load-testing plan.

## 3. Components in OCI

An observability path can be designed as follows:

~~~mermaid
flowchart LR
    PUB["Public Vantage Point"] --> EDGE["WAF / Load Balancer"]
    USER["User browser"] --> EDGE

    subgraph VCN["Application VCN"]
        DVP["Dedicated Vantage Point"] --> PRIVATE["Private endpoint"]
        EDGE --> APP["Java app on Compute"]
        PRIVATE --> APP
        APP --> DB["Oracle Database"]
    end

    PUB -. "Monitor results" .-> APM["APM domain"]
    DVP -. "Monitor results" .-> APM
    USER -. "APM Browser Agent / RUM" .-> APM
    APP -. "Traces when instrumented" .-> APM
    APP -. "Collected logs" .-> LOG["OCI Logging"]
    APM -. "Metrics" .-> MON["OCI Monitoring"]
    MON --> ALARM["Alarm"]
    ALARM --> NOTIFY["Notifications"]
~~~

Telemetry arrows represent flows you must configure; creating a monitor does not automatically instrument applications or collect all logs.

**APM domain** is the organizational scope for APM data. **Monitor** defines the target and check method; **script** describes steps for multi-action transactions; **vantage point** is where checks execute. Oracle's setup workflow starts with permissions and an APM domain, followed by preparing scripts if needed, selecting vantage points, and creating the monitor. [Setting Up Availability Monitoring](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/synthetic-monitoring.html).

In a tenancy with multiple environments, clarify the compartment holding observability resources, the target endpoint's environment, and the owning team. A dashboard mixing staging and production results makes metrics hard to interpret even when data collection works fine.

### Choosing Vantage Points Based on the Question

- **Public Vantage Point:** suited to observing public access paths used by customers.
- **Dedicated Vantage Point:** deployed inside your tenancy to test private endpoints or internal network paths.
- **On-premise Vantage Point:** useful when needing visibility from a corporate network or controlled deployment environment. [Vantage Point Options](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/synthetic-monitoring.html).

Dedicated Vantage Points can be deployed using OCI Resource Manager templates. This introduces infrastructure and networking you must manage. For private DNS, verify name resolution from the monitor's runtime environment; an admin workstation resolving a name does not prove the monitor can resolve it. [Dedicated Vantage Points](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/use-dedicated-vantage-points.html).

A vantage point inside the VCN near the app isolates Internet noise, yet bypasses public DNS, WAF, and the public Load Balancer ingress path. Internal and public vantage points therefore answer two different observational questions.

## 4. Designing the Transaction Before Creating a Monitor

Start with the outcome the user needs to achieve. For an ordering portal, "view sample order details after logging in" is a far clearer objective than "website is alive."

A check contract might contain:

| Component | Illustrative design |
| --- | --- |
| Transaction name | Log in and view sample order |
| Target | Lab environment, dedicated test account |
| Start point | Login page with no active session |
| End point | Expected sample order details rendered |
| Pass criteria | Right user, right sample order ID, expected order status |
| Time limits | Complete within 12 seconds; hard technical timeout 30 seconds |
| Frequency | Every 5 minutes from two vantage points |
| Owner | Ordering portal operations team |
| Mutated data | Creates no orders, sends no customer notifications |

These thresholds are lab assumptions, not OCI defaults or limits.

### Breaking the Transaction into Checkpoints

| Step | Action | Verification condition |
| --- | --- | --- |
| 1 | Open login page | Form is interactive |
| 2 | Log in with test account | Authenticated workspace renders |
| 3 | Open order list | Prepared sample order is present |
| 4 | Open details | Sample order ID and status match |
| 5 | Log out | Session terminates per application design |

Verify outcomes after actions. A button being clicked or the URL changing is not enough to prove business logic succeeded.

When testing data-creation flows, design unique run markers, safe repeatability, and cleanup routines. For example, create orders only in a test tenant using a sandbox payment gateway. Never let scheduled monitors trigger real payments, real emails, or real inventory deductions accidentally.

A mid-run failure can also leave stray sessions, carts, or temporary records behind. Cleanup should rely on test tags and TTLs rather than depending solely on the script's final step.

## 5. Choosing Monitor Types by Verification Depth

Four common choices for web and API applications are:

| Type | Suitable scope |
| --- | --- |
| REST | Single request to a URL and response validation |
| Scripted REST | Sequence of dependent API calls |
| Browser | Loading a single URL in a browser |
| Scripted Browser | Multi-step UI interactions across a transaction |

OCI supports these types; documentation also lists other monitors such as Network, DNS, SQL, and FTP. For this lesson, the focus is web/API transactions. [Create a Monitor and Supported Types](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-monitor.html).

Pair simple checks with business checks. A lightweight API probe catches ingress outages faster; a browser transaction also catches rendering bugs, JavaScript errors, and navigation breaks. When the API succeeds while the browser check fails, the investigation scope narrows immediately.

### Example REST Check Design

The lab app exposes a sample-data read endpoint:

~~~http
GET /api/monitoring/sample-order HTTP/1.1
Host: orders.lab.example.com
Accept: application/json
~~~

Expected response:

~~~json
{
  "orderCode": "SYNTHETIC-DEMO-001",
  "status": "READY",
  "readable": true
}
~~~

These URLs and JSON fields are defined by the lab application, not an OCI API.

Monitors must verify HTTP status codes and response payloads enough to prove the tested function actually ran. If an endpoint merely returns a hardcoded string from memory, passing it says nothing about the Oracle Database read path.

OCI offers response code validation, content checks, and SSL verification across corresponding monitor types. Keep TLS certificate validation enabled for routine checks; disabling validation can hide certificate errors that real customer browsers will hit. [Response Validation Options](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-monitor.html).

For multiple JSON assertions or chained requests, use a script to express checks cleanly. Avoid blindly substring-matching `"READY"` anywhere in the body when the same payload might contain error messages or multiple objects.

## 6. Writing Low-Noise Browser Scripts

A good script passes consistently when the app works properly and fails cleanly when business outcomes break.

You can use Selenium IDE to record journeys and export `.side` files for Scripted Browser monitors. Oracle documents other browser scripting options as well, though this lab picks the Selenium flow for consistency. Script parameters can be marked **Value is secret**; still avoid printing secrets into logs, screenshots, or page content. [Create and Parameterize Scripts](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-script.html).

The pseudocode below describes requirements, not a file you can upload directly to OCI:

~~~text
Start with a clean browser session
Open login page
Wait for form readiness
Fill test username and password from secret parameters
Submit form
Wait for authenticated confirmation signal
Open sample order
Wait for details section to appear
Verify expected order code and status
Record transaction completion time
Log out
~~~

### Wait for Conditions Instead of Hard Sleeps

Suppose a page loads in 0.8–2.5 seconds. Inserting a fixed 1-second sleep makes the monitor fail intermittently; inserting a fixed 10-second sleep slows every run needlessly.

Wait for a specific element or business condition with a bounded timeout. As soon as the condition is met, proceed. Use stable test attributes like `data-testid="order-detail"` instead of fragile DOM positions. This convention requires coordination with application developers.

Never use step wait times to mask performance regressions. Distinguish:

- **Timeout:** upper bound to abort a stuck run.
- **Quality threshold:** maximum duration within which the transaction still meets expectations.
- **Intentional wait:** deliberate pause simulating user think time or synchronization, which must be justified.

For example, a transaction finishing in 18 seconds may not hit a 30-second technical timeout yet still breaches a 12-second quality target.

### Controlling State and Identity

Each run needs a deterministic starting state. If a monitor inherits an already-authenticated session, it may completely miss broken login flows.

Test accounts need minimal business privileges, stable fixture data, and credential rotation procedures. If sharing one account across multiple vantage points, check account lockout policies, concurrent session limits, and session invalidation rules. Those controls can make concurrent runs interfere with one another.

For MFA, CAPTCHA, or anti-bot defenses, design testing approaches jointly with security and application teams. Never disable protections system-wide just to make a monitor turn green.

### Measuring Meaningful Segments

Total transaction time can be split into page load, authentication, and reading details. When total duration climbs, segmentation tells you which phase to inspect first.

OCI supports custom markers in scripts to record custom timings. Add markers only for decision-critical steps, using stable names with no personal data. [Custom Markers in Scripts](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-script.html).

A post-login segment measurement is not automatically pure server processing time: it can include redirects, asset downloads, JavaScript execution, and UI readiness waits.

## 7. Preparing Compartments, IAM, and Connectivity

For the lab, you can use a dedicated compartment illustratively named `LearnObservability`. Assign who creates the APM domain, who edits monitors, and who only views results.

Two example policies for a read-only group using an identity domain named `Default`:

~~~text
Allow group 'Default'/'OciObservers' to read apm-domains in compartment LearnObservability
Allow group 'Default'/'OciObservers' to read metrics in compartment LearnObservability
~~~

Replace domain, group, and compartment names with your tenancy's resources. These two policies cover viewing; creating domains, editing monitors, managing alarms, or using Notifications require their respective permissions. Oracle separates APM permissions from Monitoring and Notifications permissions. [APM Prerequisites and Policies](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/perform-oracle-cloud-infrastructure-prerequisite-tasks.html).

OCI administrative identities and application login accounts are two separate permission layers. Someone authorized to create a monitor does not thereby gain access to view every customer order in the application.

For private endpoints inside a VCN, verify step by step:

1. The endpoint hostname resolves from the monitor's execution environment.
2. Route tables carry traffic to the right target network.
3. NSGs, security lists, and host firewalls allow the required flow.
4. The service listens on the expected port with a certificate matching the hostname.
5. The vantage point can send telemetry back to required OCI endpoints.

Restrict rules by source, destination, and required ports. Never expose an internal application publicly just so a Public Vantage Point can reach it.

Also distinguish two failure paths: the monitor failing to reach the app versus the vantage point failing to report results back. The latter may leave only a data gap.

## 8. Hands-On: Creating Monitors on OCI

### 8.1. Starting Prerequisites

Prepare an HTTPS lab application, test account, sample order, and an operator with appropriate OCI permissions. For cross-tier investigation, also prepare server-side instrumentation and application log collection.

You do not need to deploy a Dedicated Vantage Point just to test a public endpoint. Choose vantage point types based on the access path you need to observe and your lab budget.

### 8.2. Create a Simple Probe First

In the OCI Console, open **Observability & Management → Application Performance Monitoring → Availability Monitoring**. Select the right compartment and APM domain.

Create a REST monitor for the sample read endpoint. Give it a name describing environment and function, such as `lab-orders-read-api`; configure the URL, response assertions, schedule, and vantage points. Monitor selection, domain setup, and options are documented in [Create a Monitor](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-monitor.html).

Once results arrive, confirm the monitor is actually testing the intended application. A URL redirecting to a login screen or maintenance page can return a valid HTTP response while missing the business target completely.

### 8.3. Add a Multi-Step Transaction

1. Record the login and sample-order lookup flow with Selenium IDE.
2. Remove redundant actions; add condition waits and outcome assertions.
3. Export a `.side` script and create a script resource in APM.
4. Configure parameters for environment and test data; mark sensitive inputs as secret.
5. Create a Scripted Browser monitor using that script.
6. Run an on-demand test execution before enabling the recurring schedule.
7. Verify results at each vantage point before configuring alerts.

Whenever updating script versions, record the owner and purpose of the change. Updating a selector can alter historical interpretation even when the application itself didn't change.

### 8.4. Controlled Failure Testing

Perform this strictly on lab apps and resources within your authorized test scope:

| Test change | Expected signal |
| --- | --- |
| Use a nonexistent sample order ID | Business assertion fails |
| Slow down the details endpoint | Transaction duration climbs, potentially breaching threshold |
| Change a selector on the lab page | Script fails at the element-lookup step |
| Sever the lab's private network path | Internal monitor reports connection failure or inability to run |
| Restore configuration | Passing runs resume |

The goal is proving your probe catches the failures it was built to detect. Never conclude alerting works simply because a dashboard once showed a red dot.

## 9. Reading Metrics and Designing Alerts

In OCI Monitoring, synthetic metrics reside in the `oracle_apm_synthetics` namespace; RUM uses `oracle_apm_rum`. Useful fields include:

| Metric or dimension | Meaning |
| --- | --- |
| `Availability` | Success 1, failure 0 |
| `MonitorExecutionTime` | Monitor run duration in milliseconds |
| `MonitorLoadTime` | Run duration excluding pause intervals |
| `CustomMetric` | Values emitted from custom markers |
| `MonitorId`, `VantagePoint` | Identifies the monitor and vantage point |

Verify exact metric names, units, and dimensions in [APM Metrics](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/application-performance-monitoring-metrics.html).

Example MQL expression after selecting the synthetic namespace and substituting real dimension values:

~~~text
Availability[5m]{MonitorId = "<monitor_ocid>", VantagePoint = "<vantage_point>"}.mean() < 1
~~~

This expression finds windows where the observed success rate falls below 100% for the selected stream. It does not mean "three consecutive runs failed." Verify real data behavior, aggregation intervals, and alarm pending duration before putting it into use.

### Separating Functional Failures, Slowdowns, and Missing Data

| Group | Illustrative design condition | Action |
| --- | --- | --- |
| Transaction fails to complete | Failures confirmed across multiple runs or appropriate vantage points | Investigate availability and business outcomes |
| Slow | Transaction succeeds but exceeds target within an observation window | Investigate performance |
| Missing data | No results after multiple expected intervals | Check schedule, vantage point, and telemetry path |

An empty window with no samples cannot be interpreted as either 100% success or 0% success. Design a dedicated missing-data alert with an appropriate grace window.

With two vantage points, you can escalate urgency when both fail simultaneously; a single failing vantage point still warrants review as it may indicate a regional issue. If combining multiple alarms to express this rule, configure an explicit aggregation mechanism rather than assuming one alarm understands the entire vantage-point matrix.

When a retry succeeds, preserve traces of the initial failed attempt so transient outages aren't hidden. During maintenance, apply a time-bound notification suppression plan and verify monitoring resumes afterward.

### Computing Success Ratios with Clear Denominators

For one monitor and one vantage point:

~~~text
Observed success ratio
  = successful runs / runs with valid results × 100%
~~~

For example, 286 successes out of 288 valid runs yields roughly 99.31%. That number describes the probe samples—it is not automatically the transaction success rate of all real customers.

Always report scheduled runs, runs with valid results, and missing runs alongside the percentage. If 100% success rests on only 20 out of 288 expected runs, there isn't enough evidence to evaluate full-day availability.

With a 5-minute interval, an outage occurring right after a probe runs can wait nearly 5 minutes before the next probe observes it. Total detection time also includes run duration, telemetry export, alarm evaluation, and notification delivery. Never quote the probe interval alone as a guaranteed detection SLA.

## 10. Supplementing with Real User Monitoring

Synthetics provide a repeatable path; RUM adds observation from real users' actual environments.

The OCI APM Browser Agent collects browser spans and RUM data such as page loads, JavaScript errors, and AJAX calls. You can deploy the Browser Agent without the APM Java Agent; full server-side breakdown still requires corresponding server instrumentation. [Configure APM Browser Agent](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/configure-browser-agent-real-user-monitoring.html).

### 10.1. Minimal Illustrative Configuration

The snippet below illustrates page integration in a lab app. Replace `APM_UPLOAD_ENDPOINT` with your APM domain's HTTPS endpoint without a trailing slash; replace `APM_PUBLIC_DATA_KEY` with the **public data key** issued for browser collection.

~~~html
<script>
  window.apmrum = window.apmrum || {};
  window.apmrum.serviceName = "orders-web-lab";
  window.apmrum.webApplication = "Orders-Lab";
  window.apmrum.ociDataUploadEndpoint = "APM_UPLOAD_ENDPOINT";
  window.apmrum.OracleAPMPublicDataKey = "APM_PUBLIC_DATA_KEY";
</script>
<script
  async
  crossorigin="anonymous"
  src="APM_UPLOAD_ENDPOINT/static/jslib/apmrum.min.js">
</script>
~~~

Follow placement and integration guidance for your app structure in [Deploy the APM Browser Agent](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/deploy-browser-agent-your-application.html). Never embed private data keys, OCI API signing keys, or application passwords into browser code.

After deployment, open the lab page and verify the script loads, telemetry requests aren't blocked, and data lands under the right application in APM. When using Content Security Policy, proxies, or consent managers, test those configurations too instead of merely seeing the `<script>` tag in HTML.

### 10.2. Reading Data by Meaningful Segments

Start with concrete operational questions:

- Are users hitting errors on the same page the synthetic monitor checks?
- Does slowness affect only a specific browser, network group, or UI version?
- Is the page slow waiting for server responses or during browser processing and rendering?
- Did errors start before or after the latest deployment?

When querying RUM metrics in OCI Monitoring, Oracle documentation specifies selecting `MetricGroupName = "No Group"` and `WebApplicationName` set to the target app or `All Web Applications`. [RUM Metric Query Dimension Requirements](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/application-performance-monitoring-metrics.html).

Never assume RUM covers 100% of customers. Content blockers, dropped mobile networks, or pages failing before the agent loads create blind spots. Cross-check against server-side request counts or business records to gauge coverage.

A system where synthetics pass while RUM looks poor may suffer from device constraints, real-world network conditions, or user flows outside the synthetic script. Conversely, synthetics failing during off-peak hours still provide early availability warning even before RUM collects enough samples to confirm impact.

If the Browser Agent also observes synthetic probe traffic, ensure you can distinguish test traffic when analyzing customer experience. Verify tagging or filtering directly in the app; never assume all synthetic traffic is automatically excluded from RUM.

### 10.3. Controlling Collected Data

URLs, rendered text, error screenshots, and diagnostics can contain sensitive data. Avoid placing tokens or personal information in URLs by design.

Oracle notes that default PII-masking rules do not cover every scenario. Audit masking rules against your application's actual data; session tracking and consent settings must also align with how your application operates. [Hide Personally Identifiable Information (PII) in RUM](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/hide-personally-identifiable-information-pii.html).

For monitors, favor synthetic fixture data and restrict who can view diagnostic outputs. Marking a script parameter as secret does not guarantee its value cannot appear on a rendered screen, URL, or application log line emitted by the app itself.

## 11. From Failed Transaction to Root Cause

A failed synthetic check is the starting point for investigation, not the final verdict on which component broke.

A practical workflow:

1. **Confirm scope:** which monitor, vantage point, environment, and step failed.
2. **Pin down timing:** record UTC timestamp, observation window, and active deployment version; avoid matching logs using unconverted local times.
3. **Inspect run evidence:** error messages and diagnostic captures available for that monitor type.
4. **Cross-check RUM:** inspect the same page or transaction group over the same window.
5. **Follow traces:** if instrumented with correlation, isolate slow or failing spans.
6. **Read related logs:** pivot using trace ID, request ID, or safe test identifiers for processing details.
7. **Verify recovery:** re-run the exact transaction and observe subsequent scheduled cycles after fixing.

APM supports correlating Availability Monitoring results with collected traces, though visibility depends on which telemetry sources are configured. [OCI APM Capabilities](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/application-performance-monitoring.html).

End-to-end traces do not appear automatically just because both Browser Agent and monitors exist. Verify server-side instrumentation, cross-hop context propagation, browser settings, and sampling policies. When direct linking is absent, state clearly that correlation rests on timestamps and request IDs.

### Sample Analysis Scenario

Suppose the "log in and view order" monitor jumps from 3 seconds to 16 seconds after a deployment. Observations show:

| Observation | Sound investigation step |
| --- | --- |
| Both public and internal vantage points are slow on the details step | Focus on shared application processing |
| Details REST check is slow too | Focus on the API and its dependencies |
| Trace shows waiting to acquire a database connection | Inspect connection pool and database connectivity |
| Logs show connection-pool timeouts while Compute CPU stays low | Check pool limits, long-held connections, or downstream contention |

This is reasoning from the scenario's hypothetical evidence, not an automatic rule. The database might be slow, or the app might be leaking connections or running with misconfigured pool settings. Inspect wait patterns and supporting metrics before scaling up resources.

If the API is healthy while Scripted Browser fails immediately after a UI change, check assertions and selectors. If old selectors broke while the real feature still works, update the script to match the new UI contract and log the change to explain historical charts.

## 12. Schedules, Availability, and Cost

### Estimating Run Volume

Assuming each monitor runs at **every vantage point on every cycle**, with zero retries and no pauses:

~~~text
Runs/day
  = monitor count × vantage points per monitor × 1,440 / interval in minutes
~~~

For example, 4 monitors with 2 vantage points each on a 5-minute interval:

~~~text
4 × 2 × 1,440 / 5 = 2,304 runs/day
~~~

This estimates execution volume under those schedule assumptions—it is not an OCI billing formula. With retries, custom schedules, or alternate distribution, calculate from real configuration and usage metrics.

Total observability cost may also include APM data volume, private vantage point infrastructure, logs, and diagnostics. Dedicated Vantage Points run on infrastructure inside your tenancy, so track stack resources and lifecycle costs. [Dedicated Vantage Point Deployment Architecture](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/use-dedicated-vantage-points.html).

Start with your highest-value transactions. Run simple API checks more frequently and longer browser journeys at a cadence matched to detection goals. Never cut costs by stripping assertions until a monitor loses its ability to detect real failures.

### Monitoring the Monitoring System Itself

If a monitor depends entirely on the exact same failure domain as the application, one outage can break both the app and its probes simultaneously.

Maintain sufficient independence, missing-data alerts, and verified notification channels. Multiple vantage points sitting side by side do not guarantee independence; check whether they share DNS, network paths, identities, or underlying infrastructure.

Expired test accounts, unrotated secrets, deleted fixture data, and stale UI selectors all silently degrade monitoring. Include these checks in routine operational maintenance.

### Controlled Automation

When managing monitors as code, version-control monitor configs, schedules, vantage points, owners, and alert thresholds. Reference secrets securely rather than committing them to code repositories.

Any monitor change should support diffing against live config, post-deploy test runs, and rollback. Whenever changing schedules or adding vantage points, update your daily run-volume estimates accordingly.

## 13. Signals Commonly Misinterpreted

| Signal | What you cannot conclude yet | Next step to take |
| --- | --- | --- |
| HTTP 200 | Business transaction succeeded | Validate response content and end state |
| Login page loads | Users can log in successfully | Execute authentication and verify session |
| Internal probe passes | Public Internet access works fine | Cross-check public vantage points |
| No data | Service is healthy or completely broken | Check schedule and telemetry shipping path |
| One run failed then retry passed | No incident occurred | Keep failure logs and monitor recurrence |
| Low average duration | Every user has a good experience | Inspect distributions, segments, and sample counts |
| No matching trace | Request never reached the system | Check instrumentation, sampling, and ingestion lag |
| Low CPU | No server-side bottleneck | Check I/O, locks, pools, and dependencies |
| Monitor passes after disabling TLS verification | Certificate error is resolved | Re-enable verification and fix the trust chain |

## 14. Lab Exercise and Artifacts to Save

On your lab application, deploy one REST monitor and one Scripted Browser monitor covering the same sample-order read flow. If your app supports Browser Agent integration, add RUM to observe a manual user session.

Lab deliverables:

- Transaction contract: inputs, checkpoints, pass criteria, timeouts, and quality thresholds.
- Access-path diagram from each vantage point and required IAM scope.
- Passing run evidence, controlled failure evidence, and recovery evidence.
- Dashboard or queries for availability, transaction duration, and missing data.
- Investigation write-up with timestamps, evidence, and scope limitations.
- Daily run-volume estimate, owner, and response playbook when the monitor fails.

The lab succeeds when you can explain what the monitor proves, what it leaves unverified, and which dataset to open next when it fails.

After the lab, pause or delete unused monitors, revoke test credentials, and clean up sample data per your plan. If you deployed Dedicated Vantage Point infrastructure, inspect all stack resources and dependencies before concluding the lab.

# SLO Dashboard and Alerting Project for a Java System

In the `CLOUD_PROVIDERS_GCP` module, learners explore Google Cloud from projects, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners practice choosing services, protecting resources, automating releases, and monitoring reliability and cost. In the **GCP Hands-On Projects** chapter, this lesson turns observability concepts into a practical measurement system for operating a **Java/Spring Boot** application.

You will build the `orders-api` API on **Cloud Run**, use **Cloud Monitoring** to track traffic, errors, and latency; define **Service Level Indicators (SLIs)** and 28-day **Service Level Objectives (SLOs)**; build an operations dashboard; and alert on **error-budget burn rate**. The work is divided into Java code, Terraform resources, and acceptance test steps. This architecture can extend to GKE/Compute Engine, while the primary example uses Cloud Run to avoid operating Prometheus/metrics collectors from scratch upfront.

> **Lab Limits:** This exercise documents illustrative commands and infrastructure; placeholders must be replaced before running. No deployment, resource, or alert is created merely by reading this lesson. All service creation, load generation, or notification channel activation must occur in a **staging project** with proper IAM, cost alerts, and approvals. Never enable fault-injection endpoints in production.

## 1. Problem Statement, Scope, and Acceptance Criteria

Suppose the Orders team is releasing a Java API. Previously, the team watched only CPU and instance counts; a database outage caused many requests to return HTTP 503 while CPU stayed low. The team needs a **user-experience-centered dashboard** and early warnings before burning through the error budget.

| Deliverable | Output to Produce | How to Verify |
| --- | --- | --- |
| Java API | Success endpoint and fault/slow test endpoints restricted to the `lab` profile | Real requests return 200, 503, or 200 after intentional delay |
| Cloud Run service | `orders-api` running in staging region with authentication enabled | Service URL and metrics appear |
| Availability SLI/SLO | Ratio of good requests / eligible requests, 99.9% target over 28 days | SLO details display definition and compliance |
| Latency SLI/SLO | Ratio of successful requests under 400 ms, 95% target over 28 days | SLO details display latency distribution cut |
| Dashboard | Request rate, 5xx rate, p95 latency, SLO compliance/error budget | Charts have time series for the exact project/service/region |
| Alerting | Fast-burn and slow-burn alerts on availability error budget | Valid alert policies, verified channel, concrete runbook |
| Incident exercise | Generate controlled error traffic; observe latency/errors/SLOs | Metric/alert evidence or clear explanation why alerts did not fire yet |
| Operations | Owner, escalation, anti-alert-fatigue controls, cost control, and cleanup | Runbook, checklist, and `terraform plan` output |

No real database, Pub/Sub, or GKE is required in the MVP. They can be added once baseline HTTP metrics work. This lesson also does not require injecting massive failures to breach a real SLO: the goal is validating the observability pipeline without causing a production incident.

## 2. Observability Architecture and Data Flow

~~~mermaid
flowchart LR
  CLIENT[Tester / Synthetic Client] -->|HTTPS + ID token| API[Cloud Run: orders-api\nSpring Boot]
  API -->|stdout/stderr| LOG[Cloud Logging]
  API -->|Built-in request metrics| METRIC[Cloud Monitoring Metrics]
  METRIC --> SERVICE[Monitoring custom service]
  SERVICE --> AV[Availability SLO\n99.9% / rolling 28d]
  SERVICE --> LAT[Latency SLO\n95% <= 400ms / rolling 28d]
  METRIC --> DASH[Monitoring Dashboard\nRPS / 5xx / p95]
  AV --> BURN[Burn rate selector]
  BURN --> FAST[Fast-burn alert]
  BURN --> SLOW[Slow-burn alert]
  FAST --> CHANNEL[Verified notification channel]
  SLOW --> CHANNEL
  CHANNEL --> ONCALL[Owner / runbook / incident]
  LOG --> ONCALL
~~~

**Distinguishing data sources:**

- **Cloud Run platform metrics:** `run.googleapis.com/request_count` and `run.googleapis.com/request_latencies` appear in Cloud Monitoring for Cloud Run revisions without installing any agent.
- **Cloud Logging:** Cloud Run captures stdout/stderr and request logs, used to investigate root causes after a metric signals an issue.
- **Spring Boot Actuator/Micrometer:** exposes JVM health and internal metrics. They are **not automatically exported to Cloud Monitoring** just by adding the dependency; using them as SLIs requires an export pipeline such as OpenTelemetry Collector or Google Cloud Managed Service for Prometheus.
- **Monitoring service:** a logical object in Cloud Monitoring acting as parent for SLOs. It differs from a `Cloud Run service`; one Monitoring custom service can group SLIs by business capability.
- **SLO:** comprises an SLI, quantitative goal, and compliance period. An SLO does not page on its own; separate alert policies are required.

The MVP uses **platform request metrics** because they measure most request successes and failures regardless of how deeply Java code is instrumented. In exchange, platform metrics have limits on scope, sampling, and which requests are recorded.

## 3. Understanding SLI, SLO, SLA, and Error Budget

### 3.1. Concepts to Keep Separate

| Concept | Meaning | Example |
| --- | --- | --- |
| **SLI** | Observed quantitative measure of service quality | 99.94% of eligible HTTP requests were good |
| **SLO** | Target objective for an SLI over a window | At least 99.9% of eligible requests good over 28 days |
| **SLA** | Commitment to customers/partners, potentially with penalties | Contractual obligation, distinct from internal engineering targets |
| **Error budget** | Acceptable fraction or count of bad events under the SLO | 0.1% of eligible requests for a 99.9% SLO |
| **Burn rate** | Rate of error-budget consumption relative to ideal sustainable pace | 10x: if sustained, consumes the budget 10 times faster than planned |

### 3.2. Project Availability SLI

Conventions for this API:

- **Good requests:** HTTP 1xx or 2xx.
- **Eligible total requests:** all requests excluding **4xx**, because client errors are typically not backend operational outages.
- **Bad requests:** eligible requests outside the good group (typically 5xx; if the API emits 3xx, this definition also counts them as bad).

\[
\text{Availability SLI}=\frac{\text{Good requests}}{\text{Eligible total requests}}
\]

Example: over the window there are 1,000,000 eligible requests, 999,200 good, and 800 bad, yielding 99.92% availability. A 99.9% target permits at most **1,000 bad requests** per 1,000,000 eligible requests in the window, leaving 200 bad requests in the error budget. If eligible request volume changes, the absolute budget changes accordingly.

**This is a request-based SLO, not "40 minutes of downtime".** You cannot convert bad requests into downtime minutes without knowing traffic rates over time. Likewise, zero requests does not automatically mean 100% availability.

### 3.3. Project Latency SLI

Uses `run.googleapis.com/request_latencies` (**milliseconds**) for **2xx** requests, with a good threshold of **0–400 ms**:

\[
\text{Latency SLI}=\frac{\text{2xx requests completing within 400 ms}}{\text{Total 2xx requests with latency}}
\]

Target is **95%** over a rolling 28-day window. Out of 100,000 successful requests, at most 5,000 may exceed 400 ms while still meeting the objective. This SLI differs from `p95 latency` reported as a **time duration**: per-minute p95 on a dashboard fluctuates, whereas the SLO computes a cumulative ratio across distribution samples.

Cloud Run `request_latencies` measures from when a request reaches a running container until the response returns; **it excludes container startup latency**. Dashboards should therefore add external/synthetic views if users experience cold starts, Load Balancer errors, or requests rejected before reaching the container.

### 3.4. Why 28 Days?

`rolling_period_days = 28` is a sliding window: at any point, Monitoring evaluates the most recent 28 days. Unlike `calendar_period = "MONTH"`, a rolling window does not reset at month boundaries. Using 28 days aligns neatly with full weeks; this is a **lab target**, not mandatory for every system.

### 3.5. Calculating Burn Rate by Example

A 99.9% availability SLO has an error budget ratio of `0.001`.

~~~text
Error budget fraction = 1 - 0.999 = 0.001 (0.1%)

If bad request rate in the lookback window = 1.0%:
  Burn rate ≈ 0.01 / 0.001 = 10x

If bad request rate = 0.2%:
  Burn rate ≈ 0.002 / 0.001 = 2x
~~~

A high burn rate does not necessarily mean the 28-day SLO is already breached; it warns that **at the current error rate**, the budget will be exhausted far too fast. Under low traffic, account for minimum sample sizes and sparse data to avoid unreliable conclusions.

## 4. Tooling, IAM, and Costs

### 4.1. Prerequisites

- Java **21** or a JDK version supported by your organization's Spring Boot stack; Maven/Gradle.
- A billing-enabled staging Google Cloud project with permissions to deploy Cloud Run and use Cloud Monitoring.
- `gcloud` and `terraform` on your workstation/CI; ADC or Workload Identity Federation for automation.
- A principal authorized to invoke Cloud Run and a **verified** on-call email address to receive alerts.
- Cost budgets/alerts on the staging project; never use production projects or customer resources.

### 4.2. Separated IAM

| Principal | Permissions Needed by Task | Recommendation |
| --- | --- | --- |
| **Build/deploy CI** | Deploy Cloud Run and attach runtime service account; build/push related artifacts | Pipeline-appropriate roles, including `iam.serviceAccounts.actAs` to attach runtime SA |
| **Cloud Run runtime SA** | Call downstream Google APIs used by code | **Does not need Monitoring Editor just for Cloud Run to emit built-in request metrics/logs** |
| **Monitoring author** | Create Monitoring custom service, SLOs, dashboards, alert policies, notification channels | `roles/monitoring.editor` suffices for lab; split into custom/least-privilege roles in prod |
| **Dashboard viewer** | View Monitoring dashboards, metrics/SLOs, and logs if granted | `roles/monitoring.viewer` and separate Logging role as needed |
| **HTTP tester** | `roles/run.invoker` on the auth-protected staging service | Call with OIDC ID token; never allow public anonymous access just for easy testing |
| **FinOps owner** | View Billing, budgets, and quotas | Never grant Billing Admin by default to dashboard authors |

Never commit long-lived JSON service account keys in source repositories. Cloud Run uses workload-bound service accounts; CI uses short-lived credentials. Never log or display ID tokens, access tokens, or customer emails in logs, traces, or dashboards.

### 4.3. Telemetry Cost and Latency

Cloud Run, Cloud Build, Artifact Registry, Logging, Monitoring, and notification channels can incur charges depending on usage. Cloud Monitoring platform metrics are not billed like custom metrics, whereas **custom metrics, log ingestion/retention, trace ingestion, uptime checks, notification delivery, and dashboard API traffic** should be checked against current pricing. Never add unbounded-cardinality labels like `orderId`, `userId`, or `requestId` to metrics.

Cloud Run request metrics are sampled roughly every **60 seconds** and can take additional time to appear. Per current metric documentation, some request metrics take up to roughly **120 seconds** after sampling to show up. Do not mistake an empty dashboard right after one request for a Terraform error.

## 5. Building the Illustrative Spring Boot API

### 5.1. Initializing the Application

Use Spring Initializr to generate a Maven Spring Boot project with:

- Java 21.
- Dependencies: **Spring Web**, **Spring Boot Actuator**.
- Group `com.example`, artifact `orders-api`, base package `com.example.orders`.

Dependency section in `pom.xml` with Spring Boot parent:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Do not pick a Spring Boot version incompatible with your JDK/buildpacks. Pin BOM and versions in real projects. Cloud Run runs containers/buildpacks, so the app must listen on the configured port; the MVP uses **8080**, the default container port for many Cloud Run deployments.

### 5.2. Application Entrypoint

`src/main/java/com/example/orders/OrdersApplication.java`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

### 5.3. Normal API

`OrdersController.java`:

~~~java
package com.example.orders;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {
    @GetMapping("/{id}")
    public Map<String, String> getOrder(@PathVariable String id) {
        return Map.of(
            "id", id,
            "status", "ACCEPTED"
        );
    }
}
~~~

The MVP uses no database. The endpoint returns HTTP 200 and JSON, sufficient to generate successful SLI data.

### 5.4. Fault/Slow Endpoints **Strictly in the `lab` Profile**

`LabFaultController.java`:

~~~java
package com.example.orders;

import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("lab")
@RequestMapping("/__lab")
public class LabFaultController {
    @GetMapping("/fail")
    public ResponseEntity<Map<String, String>> fail() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(Map.of("error", "simulated downstream outage"));
    }

    @GetMapping("/slow")
    public Map<String, String> slow() {
        LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(700));
        return Map.of("result", "delayed for observability lab");
    }
}
~~~

**Security:** `@Profile("lab")` registers this controller only when the `lab` profile is active. Never enable this profile on a production revision. In staging, enforce Cloud Run authentication, restrict `roles/run.invoker`, cap max instances, and set budgets. Never expose fault-injection endpoints publicly, as that invites self-inflicted denial of service.

### 5.5. Actuator and Logging Configuration

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: orders-api

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: never

logging:
  level:
    root: INFO
~~~

The lab enables `/actuator/metrics` for **inspection in a protected environment**; production should restrict Actuator endpoints via Spring Security/networking or avoid exposing `metrics` publicly. Never expose `env`, `heapdump`, or `configprops` to the Internet.

Spring Boot stdout/stderr logs are forwarded by Cloud Run to Cloud Logging. You can add the OpenTelemetry Java Agent to export traces, though lacking the agent **does not remove** the Cloud Run `request_count`/`request_latencies` used in these SLOs.

### 5.6. Running Locally

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=lab

curl -i http://localhost:8080/api/orders/1001
curl -i http://localhost:8080/__lab/fail
curl -i http://localhost:8080/__lab/slow
curl -i http://localhost:8080/actuator/health
~~~

Expected: `/api/orders/1001` returns 200; `/__lab/fail` returns 503; `/__lab/slow` returns 200 after ~700 ms due to the intentional wait. These local results **do not generate** Cloud Run metrics yet.

## 6. Deploying Cloud Run in the Staging Project

### 6.1. Enabling Required APIs

Using an authorized, billing-enabled project:

~~~bash
gcloud config set project PROJECT_ID
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  --project=PROJECT_ID
~~~

CI may need additional APIs and roles for your build pipeline/source deployment setup. Attach a dedicated service account when the app calls downstream APIs; the MVP does not need a database or Secret Manager.

### 6.2. Deploying from Application Source

Run from the directory containing `pom.xml`:

~~~bash
gcloud run deploy orders-api \
  --source=. \
  --region=asia-southeast1 \
  --no-allow-unauthenticated \
  --ingress=all \
  --set-env-vars=SPRING_PROFILES_ACTIVE=lab \
  --max-instances=2 \
  --min-instances=0 \
  --memory=512Mi \
  --cpu=1 \
  --concurrency=20 \
  --timeout=30s \
  --project=PROJECT_ID
~~~

`--source` requires build/deploy permissions and may create/build images in Artifact Registry. If Cloud Build picks the wrong JDK/Spring Boot version, adjust buildpack configuration or use an organization-approved Dockerfile. Never switch to `--allow-unauthenticated` just to bypass IAM errors.

**The `lab` profile must be removed for production releases.** Upon finishing, do not delete only the Terraform Monitoring resources while leaving a `lab`-profile Cloud Run revision serving unchecked traffic.

### 6.3. Retrieving the URL and Calling with an ID Token

~~~bash
SERVICE_URL="$(gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --format='value(status.url)')"

TOKEN="$(gcloud auth print-identity-token)"

curl -i -H "Authorization: Bearer $TOKEN" \
  "$SERVICE_URL/api/orders/1001"

unset TOKEN
~~~

The caller must hold `roles/run.invoker` on the service. Under certain environments/credential types, a user's ID token lacks the right audience; operators authorized to mint tokens can use service account impersonation with `--audiences` set to the Cloud Run URL. Never substitute a Google API OAuth access token for an ID token when calling a private Cloud Run HTTP endpoint.

Verify the service has a ready revision with accurate region/name metadata. **You do not need public access** for Monitoring to collect platform metrics.

## 7. Selecting and Verifying Cloud Monitoring Metrics

### 7.1. Metrics Used

| Metric Type | Monitored Resource | Kind / Type | Purpose |
| --- | --- | --- | --- |
| `run.googleapis.com/request_count` | `cloud_run_revision` | DELTA / INT64 | Request volume, 5xx rate, availability good/total |
| `run.googleapis.com/request_latencies` | `cloud_run_revision` | DELTA / DISTRIBUTION, **ms** | p95 latency, ratio of requests under 400 ms |
| `run.googleapis.com/container/instance_count` or matching instance metric | Cloud Run resource per metric | GAUGE | Autoscaling diagnostics |
| Cloud Logging request log | `cloud_run_revision` | Log entries | Status, URL, and request trace details |
| Java Actuator app metrics | JVM/app internals | Local-only unless exported | Heap, GC, thread pools, custom business SLIs |

**Important limitation of Cloud Run `request_count`:** the metric only counts requests **reaching a revision/container**; it may **miss** requests rejected for missing authentication or rejected before entering a container when max instances is reached. The `route` label on Cloud Run request metrics also omits useful route paths (usually empty). SLOs built on this metric are **backend service SLOs**, not full proof of edge user experience. If the service sits behind an Application Load Balancer, add load balancer request metrics, uptime checks, or custom user-journey metrics.

### 7.2. Testing Filters Before Creating SLOs

Open **Monitoring → Metrics Explorer**:

1. Select resource **Cloud Run Revision**.
2. Select metric **Request Count**.
3. Filter `service_name = orders-api`, `location = asia-southeast1`.
4. Apply an appropriate alignment rate or sum to view requests/second.
5. Group by `response_code_class` to separate 2xx, 4xx, and 5xx.
6. Select **Request Latency** and align at the 95th percentile, unit `ms`.

If no data appears, send a few 200/503 requests in staging and wait for sampling ingestion. Do not define SLOs before confirming `Metrics Explorer` shows the exact series and labels; mistyped project/location filters can create empty SLOs even when `terraform apply` succeeds.

## 8. Terraform: Monitoring Service and Two SLOs

The `monitoring/` folder lives in the **learner's lab workspace** (not in this lesson's source module):

~~~text
monitoring/
  versions.tf
  variables.tf
  slos.tf
  dashboard.tf
  alerts.tf
  outputs.tf
  terraform.tfvars
~~~

### 8.1. Provider and Variables

`versions.tf`:

~~~hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
~~~

In production, use protected remote state and a provider lockfile; never use shared ad-hoc local Terraform state.

`variables.tf`:

~~~hcl
variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "asia-southeast1"
}

variable "cloud_run_service" {
  type    = string
  default = "orders-api"
}

variable "alert_email" {
  type        = string
  description = "Verified email address for staging alerts."
}
~~~

Sample `terraform.tfvars`:

~~~hcl
project_id        = "REPLACE_WITH_STAGING_PROJECT_ID"
region            = "asia-southeast1"
cloud_run_service = "orders-api"
alert_email       = "platform-oncall@example.com"
~~~

The `example.com` address is a placeholder, not a real recipient. If the email channel is unverified or blocked by org policy, an alert can exist yet **fail to deliver notifications**.

### 8.2. Cloud Run Filters Scoped to Exact Service and Region

`slos.tf`:

~~~hcl
locals {
  request_count_base = join(" AND ", [
    "metric.type=\"run.googleapis.com/request_count\"",
    "resource.type=\"cloud_run_revision\"",
    format("resource.label.\"service_name\"=\"%s\"", var.cloud_run_service),
    format("resource.label.\"location\"=\"%s\"", var.region),
  ])

  request_good = format(
    "%s AND (metric.label.\"response_code_class\"=\"1xx\" OR metric.label.\"response_code_class\"=\"2xx\")",
    local.request_count_base
  )

  request_eligible = format(
    "%s AND metric.label.\"response_code_class\"!=\"4xx\"",
    local.request_count_base
  )

  request_5xx = format(
    "%s AND metric.label.\"response_code_class\"=\"5xx\"",
    local.request_count_base
  )

  latency_2xx = join(" AND ", [
    "metric.type=\"run.googleapis.com/request_latencies\"",
    "resource.type=\"cloud_run_revision\"",
    format("resource.label.\"service_name\"=\"%s\"", var.cloud_run_service),
    format("resource.label.\"location\"=\"%s\"", var.region),
    "metric.label.\"response_code_class\"=\"2xx\"",
  ])
}
~~~

All four filters ensure the **exact same service and region** are measured. Do not filter by `revision_name`: every revision serving traffic for the service should participate in the SLO. If you change the service name or region on deploy, update these variables and verify data flows.

### 8.3. Creating the Monitoring Custom Service

~~~hcl
resource "google_monitoring_custom_service" "orders" {
  project      = var.project_id
  service_id   = "orders-api-observability"
  display_name = "Orders API - Java / Cloud Run"
}
~~~

A **Monitoring custom service** groups SLOs. It does not create a Cloud Run service and does not instrument Java code. The SLO filters below determine which metrics are evaluated.

### 8.4. Availability SLO: 99.9% Over 28 Days

~~~hcl
resource "google_monitoring_slo" "availability" {
  project      = var.project_id
  service      = google_monitoring_custom_service.orders.service_id
  slo_id       = "availability-999-28d"
  display_name = "Orders API availability >= 99.9% / 28d"

  goal                = 0.999
  rolling_period_days = 28

  request_based_sli {
    good_total_ratio {
      good_service_filter  = local.request_good
      total_service_filter = local.request_eligible
    }
  }

  user_labels = {
    environment = "staging"
    team        = "orders"
  }
}
~~~

**The denominator definition is intentional**: 4xx is excluded, 1xx/2xx are good, and 5xx plus any 3xx count as not-good. For APIs emitting valid 3xx redirects, adjust the SLI definition to avoid false errors. Good/total filters must use compatible DELTA/CUMULATIVE metric kinds, and **good must be a subset of total**.

### 8.5. Latency SLO: 95% of Successful Requests Under 400 ms

Also in `slos.tf`:

~~~hcl
resource "google_monitoring_slo" "latency" {
  project      = var.project_id
  service      = google_monitoring_custom_service.orders.service_id
  slo_id       = "latency-95-under-400ms"
  display_name = "Orders API p(under 400ms) >= 95% / 28d"

  goal                = 0.95
  rolling_period_days = 28

  request_based_sli {
    distribution_cut {
      distribution_filter = local.latency_2xx

      range {
        min = 0
        max = 400
      }
    }
  }

  user_labels = {
    environment = "staging"
    team        = "orders"
  }
}
~~~

Here **400 is milliseconds**, not 0.4 seconds, because Cloud Run `request_latencies` is a distribution metric in `ms`. `distribution_cut` counts samples inside the good bucket relative to total samples in the distribution rather than averaging per-minute p95s. The latency SLO evaluates 2xx requests; 5xx errors are already covered by the availability SLO.

## 9. Terraform: Dashboard for Request Rate, 5xx, and p95 Latency

Dashboards serve **investigation and trend analysis**, whereas SLOs measure **quality commitments**. Both are needed.

`dashboard.tf`:

~~~hcl
resource "google_monitoring_dashboard" "orders" {
  project = var.project_id

  dashboard_json = jsonencode({
    displayName = "Orders API | Java SLO and Reliability"

    gridLayout = {
      columns = 2
      widgets = [
        {
          title = "HTTP request rate (req/s)"
          xyChart = {
            dataSets = [
              {
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = local.request_count_base
                    aggregation = {
                      alignmentPeriod     = "60s"
                      perSeriesAligner    = "ALIGN_RATE"
                      crossSeriesReducer = "REDUCE_SUM"
                    }
                  }
                }
                plotType = "LINE"
              }
            ]
            yAxis = {
              label = "requests per second"
              scale = "LINEAR"
            }
          }
        },
        {
          title = "HTTP 5xx rate (req/s)"
          xyChart = {
            dataSets = [
              {
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = local.request_5xx
                    aggregation = {
                      alignmentPeriod     = "60s"
                      perSeriesAligner    = "ALIGN_RATE"
                      crossSeriesReducer = "REDUCE_SUM"
                    }
                  }
                }
                plotType = "LINE"
              }
            ]
            yAxis = {
              label = "5xx requests per second"
              scale = "LINEAR"
            }
          }
        },
        {
          title = "Successful request latency p95 (ms, per series)"
          xyChart = {
            dataSets = [
              {
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = local.latency_2xx
                    aggregation = {
                      alignmentPeriod  = "60s"
                      perSeriesAligner = "ALIGN_PERCENTILE_95"
                    }
                  }
                }
                plotType = "LINE"
              }
            ]
            yAxis = {
              label = "milliseconds"
              scale = "LINEAR"
            }
          }
        }
      ]
    }
  })
}
~~~

Because `request_count` is a DELTA count, `ALIGN_RATE` computes per-second rate and `REDUCE_SUM` sums across revisions. For p95 latency, **never average separate p95 values** and call it system-wide p95; this example keeps series separate. If you need percentiles aggregated across revisions, use distribution-aware aggregation supported by Monitoring or design appropriate metrics—never apply `REDUCE_MEAN` to percentiles.

The dashboard still lacks a crucial piece: **SLO widgets**. After the SLOs are created, in the Console:

1. Go to **Monitoring → Dashboards** and select `Orders API | Java SLO and Reliability`.
2. Click **Add widget → SLO**.
3. Choose Monitoring service `Orders API - Java / Cloud Run`.
4. Select SLO `Orders API availability >= 99.9% / 28d`; display **compliance** and add a **remaining error budget** widget.
5. Select the latency SLO and add **compliance**; set clear time ranges and chart titles.
6. **Apply/Save**; confirm charts load and compare SLO compliance against the p95 chart.

**Drift warning:** if a dashboard is managed by Terraform and you edit it manually in the Console, the next `terraform plan/apply` may overwrite manual edits. For long-term IaC management, export the dashboard JSON after adding SLO widgets and commit those widgets into `dashboard_json` under code review. Never add an SLO widget by hand and assume Terraform will preserve it forever.

## 10. Terraform: Notification Channel and Burn-Rate Alerts

### 10.1. Preparing the Email Channel

`alerts.tf`:

~~~hcl
resource "google_monitoring_notification_channel" "oncall" {
  project      = var.project_id
  display_name = "Orders staging on-call"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }
}
~~~

The address must be verified per Cloud Monitoring's workflow. Prefer an on-call team/group email over a single personal inbox. You can swap email for Slack, PagerDuty, or another channel if already integrated and verified in your organization. Notification channels may incur charges depending on type/plan; check pricing docs.

### 10.2. Fast Burn: Greater Than 10x Over a 60-Minute Lookback

~~~hcl
resource "google_monitoring_alert_policy" "fast_burn" {
  project      = var.project_id
  display_name = "Orders API - availability error budget fast burn"
  combiner     = "OR"

  conditions {
    display_name = "Burn rate > 10x over 60m"

    condition_threshold {
      filter = format(
        "select_slo_burn_rate(\"%s\", \"60m\")",
        google_monitoring_slo.availability.name
      )
      comparison      = "COMPARISON_GT"
      threshold_value = 10
      duration        = "0s"
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.oncall.name
  ]

  documentation {
    mime_type = "text/markdown"
    content   = "Orders API fast burn: inspect 5xx, recent deploys, Cloud Run revision health, downstream failures and current error budget. Follow staging incident runbook."
  }

  alert_strategy {
    auto_close = "1800s"
  }
}
~~~

`select_slo_burn_rate` takes the **full SLO resource name** and a `60m` lookback period. `duration = "0s"` does not mean the alert triggers on a single request: burn rate is already computed over the **60-minute window**. The 10x threshold is an illustrative fast-burn starting point that must be tuned to real service traffic and SLO levels.

### 10.3. Slow Burn: Greater Than 2x Over a 24-Hour Lookback

~~~hcl
resource "google_monitoring_alert_policy" "slow_burn" {
  project      = var.project_id
  display_name = "Orders API - availability error budget slow burn"
  combiner     = "OR"

  conditions {
    display_name = "Burn rate > 2x over 24h"

    condition_threshold {
      filter = format(
        "select_slo_burn_rate(\"%s\", \"24h\")",
        google_monitoring_slo.availability.name
      )
      comparison      = "COMPARISON_GT"
      threshold_value = 2
      duration        = "0s"
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.oncall.name
  ]

  documentation {
    mime_type = "text/markdown"
    content   = "Orders API slow burn: inspect trend across day, compare deploys, traffic shift, 5xx by revision and remaining SLO budget. Raise action item before budget exhaustion."
  }
}
~~~

Per Google Cloud guidance, pairing fast-burn (short lookback, high threshold) with slow-burn (long lookback, lower threshold) catches both major acute outages and prolonged gradual degradation. Under low traffic, a 24h lookback takes time to accumulate samples; do not assume an alert is broken merely because it does not fire immediately after creation.

**Never substitute a regular metric threshold for the SLO selector in this condition.** With an SLO burn-rate filter, do not add `aggregations` or ordinary metric denominator filters. Terraform references `google_monitoring_slo.availability.name`, ensuring the SLO is created before the policy.

### 10.4. Additional Alerts to Consider

The project may need **uptime/synthetic checks** or absolute 5xx alerts from an external load balancer when traffic fails before reaching the container. SLOs built on Cloud Run request metrics may **miss** pre-container rejections. With zero requests, a request-based SLO does not prove the system is actually up. Never treat `no data` as `all good`.

You can add an uptime check in staging targeting an **endpoint reachable from probe locations**. Private Cloud Run services require synthetic tests configured with appropriate auth/networking; never enable public access solely so uptime checks can pass.

## 11. Terraform Outputs, Review, and Apply

`outputs.tf`:

~~~hcl
output "monitoring_service_name" {
  value = google_monitoring_custom_service.orders.name
}

output "availability_slo_name" {
  value = google_monitoring_slo.availability.name
}

output "latency_slo_name" {
  value = google_monitoring_slo.latency.name
}

output "dashboard_id" {
  value = google_monitoring_dashboard.orders.id
}

output "fast_burn_policy_id" {
  value = google_monitoring_alert_policy.fast_burn.id
}

output "slow_burn_policy_id" {
  value = google_monitoring_alert_policy.slow_burn.id
}
~~~

From the lab `monitoring/` directory:

~~~bash
terraform init
terraform fmt -recursive
terraform validate
terraform plan -out=monitoring.tfplan
terraform show monitoring.tfplan
terraform apply monitoring.tfplan
terraform output
~~~

**Plan review checklist:** resources are created in the right project; SLO filters target `orders-api` and the staging region; email channel is accurate; no policy will page production on-call; no Monitoring resources owned by other teams are deleted or replaced. When using remote Terraform state, enforce access controls and versioning, and never commit state to Git.

Note that this code is a **Terraform sample** that must be tested against your chosen provider version and project API permissions. APIs may evolve schemas or validation rules; if errors occur, read the provider/Monitoring API message and fix per official docs rather than granting Owner or disabling audits.

## 12. Verifying Dashboard and SLOs in the Google Cloud Console

After `terraform apply`, open **Monitoring → SLOs**:

1. Verify custom service `Orders API - Java / Cloud Run` exists.
2. Open the availability SLO and check **99.9% / rolling 28d** and its good/eligible definition.
3. Open the latency SLO and check **95% under 400ms** and millisecond units.
4. In the Service Monitoring dashboard, inspect the SLI chart, compliance, and error-budget consumption.
5. If charts are blank, compare filters against Metrics Explorer, send a few requests, and wait for metric ingestion.
6. In **Monitoring → Dashboards**, check request rate, 5xx rate, and p95.
7. In **Alerting**, verify both fast/slow policies and that the notification channel shows verified status.

A helpful acceptance table:

| Check | Method | PASS Condition |
| --- | --- | --- |
| METRIC-01 | Metrics Explorer `request_count` | Data present for right `service_name` and `location` |
| METRIC-02 | Filter 5xx | Lab 503 requests recorded after sampling delay |
| METRIC-03 | `request_latencies` | Lab slow requests produce elevated latency samples |
| SLO-01 | Availability SLO details | Accurate good/total, 99.9% goal, 28-day window |
| SLO-02 | Latency SLO details | 2xx distribution, 400 ms threshold, 95% goal |
| DASH-01 | Dashboard | Charts load cleanly without mixing multiple services |
| DASH-02 | SLO widgets | Compliance and remaining budget shown for exact SLOs |
| ALERT-01 | Policies | Fast 10x/60m and slow 2x/24h reference right SLO name |
| ALERT-02 | Notification channel | Email/channel verified with assigned owner/runbook |
| SEC-01 | Cloud Run service | Auth required; `lab` profile restricted to staging |
| COST-01 | Billing/budget | Scoped cost review and cleanup plan documented |

Capture dashboard screenshots and export `terraform plan`/SLO definitions as evidence; never capture or log tokens. **A PASS on code/UI does not mean pager delivery was tested**; testing the channel requires its own verification step.

## 13. Controlled Fault Testing and Reading Results

### 13.1. Generating Baseline Traffic

Before injecting faults, send a batch of 200 requests from a caller holding `roles/run.invoker`:

~~~bash
SERVICE_URL="$(gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --format='value(status.url)')"

TOKEN="$(gcloud auth print-identity-token)"

for i in $(seq 1 50); do
  curl -s -o /dev/null \
    -H "Authorization: Bearer $TOKEN" \
    "$SERVICE_URL/api/orders/$i"
done
~~~

Small traffic volumes may not reliably trigger burn-rate alerts. The purpose of this step is to verify **metrics ingestion** and rising request counts. Bound request rate, instance count, and cost; never launch sudden heavy load.

### 13.2. Testing 503 Errors and High Latency

~~~bash
for i in $(seq 1 10); do
  curl -s -o /dev/null \
    -H "Authorization: Bearer $TOKEN" \
    "$SERVICE_URL/__lab/fail"
done

for i in $(seq 1 5); do
  curl -s -o /dev/null \
    -H "Authorization: Bearer $TOKEN" \
    "$SERVICE_URL/__lab/slow"
done

unset TOKEN
~~~

This must run against the service with the `lab` profile active. If endpoints return 404, check profile, URL, and revision; if HTTP 401/403, check ID token and IAM—**never** enable anonymous invocation. Stop immediately if request counts or costs exceed expectations.

### 13.3. Inspecting Telemetry Response

After a few minutes, verify:

- Request chart reflects the traffic bump from the loop.
- 5xx chart shows the 10 HTTP 503 responses.
- Successful request p95 latency increases in the window containing `/__lab/slow` (depending on request distribution).
- Availability SLI and SLO compliance/error budget shift based on requests across the **full window**.
- Logs Explorer holds error request details for investigation.

**Do not assume fast/slow alerts must fire** from 10 errors over a few minutes: the fast selector looks back 60 minutes, the slow selector looks back 24 hours, denominators depend on real traffic, and newly created SLOs may lack historical data. To test notification delivery, use the channel's test feature or an approved short-lived sandbox test alert, then delete it afterward.

### 13.4. Querying Logs for Investigation

In **Logs Explorer**, filter:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
httpRequest.status>=500
~~~

Add time bounds, region, trace ID, and revision as needed. Request logs may show only HTTP status/latency; finding business root causes requires structured application logs/traces. Never log user PII or sensitive payloads merely for easier debugging.

## 14. Runbooks for Fast-Burn and Slow-Burn Alerts

### 14.1. Fast-Burn: Incident Response

1. **Acknowledge** the alert; confirm project, service, region, SLO, and lookback window.
2. Check **traffic volume** to avoid overreacting to tiny sample sizes.
3. Open request rate, 5xx, and latency charts; classify symptoms.
4. Open Cloud Run **Revisions/Traffic** to check recent deploys and changes to max instances, concurrency, or CPU/memory.
5. Query Cloud Logging by status, trace, exception, and request ID; check dependencies (Cloud SQL, Pub/Sub, Secret Manager).
6. If tied to a recent revision, consider **rolling back traffic** per the approved runbook.
7. Check remaining error budget and verify metrics recover; notify customer-facing teams if severity warrants.
8. Record timeline, root cause, impact, and follow-up actions. Never silence an alert while the underlying failure persists.

### 14.2. Slow-Burn: Sustained Quality Improvement

- Compare the current 24 hours against the same day-of-week baseline.
- Separate 5xx causes: downstream failures, timeouts, quotas, 429s, and business contract errors.
- Examine p95/p99 latency, cold starts, memory pressure, instance concurrency, DB connection pools, and retry storms.
- Propose configuration improvements, performance tests, or capacity planning; never throw more CPU at a problem just because an alert fired.
- Adjust SLO/alert thresholds **via review** when targets no longer match user expectations—never merely to make a dashboard look "green".

### 14.3. Actionable Notification Template

~~~text
[SEV-2] Orders API availability fast burn
Project: STAGING_PROJECT_ID
Service: orders-api
SLO: availability-999-28d
Lookback: 60m
Burn-rate threshold: > 10x

First checks:
1. Verify eligible request volume and 5xx trends.
2. Compare current revision to last successful deployment.
3. Open Cloud Run request logs and downstream dependency dashboards.
4. Escalate to on-call platform owner if not recovering.
5. Record incident ID and mitigation; verify error-budget trend after rollback.
~~~

The sample message contains technical metadata only. Never attach ID tokens, credentials, or personal data.

## 15. Distinguishing SLO Dashboards from Internal Java Metrics

Cloud Run metrics are a great start, yet larger systems often require more:

| Need | Additional Telemetry | How to Use |
| --- | --- | --- |
| JVM heap/GC/threads | Spring Boot Micrometer + exporter | Diagnose Java-specific bottlenecks |
| Per-endpoint p95 | Application metrics with stable route templates | Build SLIs specifically for `POST /api/orders` |
| Database latency | JDBC spans/metrics + Cloud SQL metrics | Inspect connection wait, query time, pool saturation |
| Async workflows | Pub/Sub backlog, oldest unacked age, processing lag | Define event-processing latency SLOs instead of HTTP-only |
| Real user journeys | Synthetic browser/HTTP probes + LB/edge metrics | Cover blind spots before the Cloud Run container |
| Distributed traces | OpenTelemetry Java agent + Collector/OTLP | Correlate requests with downstream service calls |

**Never** put `userId`, `orderId`, request UUIDs, or emails into **metric labels**: cardinality explodes and drives up cost. Use route templates or bounded label sets like `operation`, `status_class`, and `environment`. High-cardinality identifiers belong in logs/traces governed by data policies.

When migrating to GKE, you can use Managed Service for Prometheus to collect `http_server_requests_seconds_count` and histograms from instrumented apps. SLOs then rely on those custom metrics; **never** reuse `run.googleapis.com/request_count` filters unchanged on GKE/VMs.

## 16. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Cloud Run metrics blank | No requests reached container, wrong project/service/region, or sampling lag | Send valid staging requests; check Metrics Explorer and wait for ingestion |
| SLO always shows `No data` | Wrong SLI filters or nonexistent label; new service has zero traffic | Verify filters and resource labels first, then test SLO |
| Fast-burn alert did not fire after 10 errors | 60m lookback, actual bad ratio, and sample volume did not exceed 10x | Inspect burn-rate chart; avoid jumping to conclusions from a handful of requests |
| Slow-burn alert has not fired | 24h lookback on a brand-new SLO | Wait for data accumulation; test notification channel separately |
| Dashboard p95 looks off | Measuring per-revision/class percentiles without merging distributions | Check filters/grouping; distinguish p95 from request-based SLOs |
| SLO captures unrelated traffic | Cloud Run metrics lack useful route labels | Use custom business metrics or dedicated services |
| Users see 429/401 while SLO stays green | Pre-container rejections are omitted from revision metrics | Add LB/edge metrics, uptime checks, and user-journey tests |
| Cloud Run `503` missing | Failed before container or wrong service/revision | Check request logs, metric scope, and max instances |
| Terraform `403` creating Monitoring resources | Missing Monitoring role or API | Grant role at exact scope; avoid Owner |
| Email channel fails to send | Unverified email, org policy block, or wrong channel | Test notification channel and routing |
| Terraform wants to revert Console dashboard edits | Drift between manual UI JSON and Terraform state | Export JSON, put changes into code, and review |
| Low metric latency yet users feel slowness | Cloud Run request latency excludes startup and edge | Add end-to-end latency/synthetic monitoring |
| Too many demo alerts | Policy wired to prod channel or overly sensitive thresholds | Use staging email, time-box labs, clean up |
| Cloud Run build/deploy fails | Source buildpack, Java version, IAM, or Artifact Registry issue | Inspect Cloud Build logs and build/deploy permissions |
| SLO stays red despite normal API | Good/total definition mismatch on 3xx, auth, redirects, response classes | Align SLI contract, inspect samples, update via review |

## 17. Cost, Security, and Lifecycle at Lab End

### 17.1. Containing Blast Radius

- Use a dedicated staging project, `max-instances = 2`, `min-instances = 0`, and small request loads.
- Require Cloud Run auth; restrict lab fault endpoints strictly to `SPRING_PROFILES_ACTIVE=lab`.
- Point email channels solely at the lab group; never page production on-call without approval.
- Apply least-privilege IAM: separate Monitoring author, dashboard viewer, deployer, runtime SA, and HTTP caller.
- Maintain a Billing Budget and accountable owner, remembering **budget alerts are not hard spending caps**.

### 17.2. Ordered Cleanup

1. Save verified screenshots and SLO/dashboard/alert policy JSON.
2. In `monitoring/`, run `terraform plan -destroy` and confirm it targets only the lab's custom service, SLOs, alert policies, dashboard, and channel.
3. After approval, run `terraform destroy`; if widgets or policies were created manually outside Terraform, clean them up separately per ownership. Never delete shared ops channels.
4. Delete the Cloud Run **staging lab service** `orders-api` via proper workflow; avoid touching same-named production services in other projects.
5. Check Cloud Build artifacts/Artifact Registry images and logging retention per policy; some charges may persist through the billing cycle.
6. Confirm alert policies no longer send demo emails. Retain redacted evidence without tokens.

Never run `destroy` if unsure which project or Terraform workspace you are in. Review the full plan first, especially when multiple Monitoring services share a notification channel.

### 17.3. Moving to Production

- Remove the `lab` profile and all intentional fault-injection endpoints.
- Define SLOs around user experience, exclude intentional 4xx responses as appropriate, and review with the product owner.
- Add synthetic/user-journey checks if pre-container errors matter.
- Measure baseline traffic before paging on burn rate; tune thresholds and durations to fit on-call rotations.
- Attach alert owners and runbooks; test escalation, deduplication, auto-close, and notification latency.
- Enforce IaC, code review, and rollback for all Monitoring resources; never let dashboards live solely in manual Console clicks.

## 18. Final Acceptance Checklist

- [ ] Spring Boot Java app returns 200, with lab-only endpoints returning 503 and a 700 ms delay.
- [ ] Cloud Run service `orders-api` deployed in staging project/region with authentication required.
- [ ] `run.googleapis.com/request_count` and `request_latencies` metrics verified.
- [ ] Understood that `request_count` omits certain pre-container rejections and `route` is not useful.
- [ ] Availability SLI defines good as 1xx/2xx, eligible excluding 4xx, and agreed handling for 3xx.
- [ ] Availability SLO set to 99.9% over rolling 28 days.
- [ ] Latency SLO set to 95% of 2xx requests under 400 ms, with units in ms.
- [ ] Terraform custom service and both SLOs created in the right project.
- [ ] Dashboard displays request rate, 5xx rate, p95 latency, and SLO/error-budget widgets.
- [ ] Per-revision p95s are not naively averaged into a fake service-wide p95.
- [ ] Verified email/notification channel and accountable owner in place.
- [ ] Fast burn (10x/60m) and slow burn (2x/24h) configured via `select_slo_burn_rate`.
- [ ] Alert definitions, notification wiring, and runbook thoroughly reviewed.
- [ ] Baseline, fault, and slow traffic run in lab with observed metric changes after ingestion delay.
- [ ] Understood why a small burst of errors does not necessarily fire alerts immediately.
- [ ] Logs/traces or clear investigation path from charts to root cause in place.
- [ ] No credentials, personal data, or high-cardinality labels in metrics/logs.
- [ ] Cost plan, max instances, least-privilege IAM, `lab` profile isolation, and safe cleanup covered.
- [ ] Post-apply `terraform plan` shows zero unexpected drift.
- [ ] Acceptance evidence, owner, and production release alerting policy documented.

## References

- [Cloud Run: Monitor health and performance](https://docs.cloud.google.com/run/docs/monitoring) — platform metrics, Cloud Monitoring, and Cloud Run resource types.
- [Cloud Monitoring metrics: `run.googleapis.com`](https://docs.cloud.google.com/monitoring/api/metrics_gcp_p_z) — request count, latency, units, labels, and sampling limits.
- [Cloud Monitoring: Request-response services](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/sli-metrics/req-resp-metrics) — availability good/total ratios and latency distribution SLIs.
- [Cloud Monitoring: Define a service](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/define-svc) — Monitoring custom services and candidate services.
- [Cloud Monitoring: Create an SLO](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/create-slo) — SLIs, goals, compliance periods, and validation.
- [Cloud Monitoring: Display SLOs on a dashboard](https://docs.cloud.google.com/monitoring/dashboards/slos) — compliance, health, and remaining error-budget widgets.
- [Cloud Monitoring: Alerting on error-budget burn rate](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/alerting-on-budget-burn-rate) — fast/slow burn principles.
- [Cloud Monitoring: Create SLO alert policies with API](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/api/create-policy-api) — `select_slo_burn_rate` filters, thresholds, and notification channels.
- [Cloud Monitoring: Retrieve SLO data](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/api/timeseries-selectors) — SLO time-series selectors and lookback periods.
- [Terraform: `google_monitoring_custom_service`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_custom_service) — service resource and metadata.
- [Terraform: `google_monitoring_slo`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_slo) — request-based SLI, distribution cut, goal, and rolling period.
- [Terraform: `google_monitoring_dashboard`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_dashboard) — dashboard JSON representation and chart widgets.
- [Terraform: `google_monitoring_alert_policy`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_alert_policy) — condition thresholds, documentation, and channels.
- [Terraform: `google_monitoring_notification_channel`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_notification_channel) — channel types/labels and verification.
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html) — health, Micrometer, and observability endpoints.

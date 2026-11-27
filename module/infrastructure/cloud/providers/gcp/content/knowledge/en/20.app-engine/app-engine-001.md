# App Engine application, services, and versions

## Learning Objectives

After this lesson, learners will be able to:

1. Explain the **Google Cloud project → App Engine application → services → versions → instances** relationship, and distinguish an App Engine service from a Cloud Run service or Kubernetes Service.
2. Create an App Engine application in a project, choose the right region from the start, and deploy the **default service** before other services.
3. Configure **app.yaml**, deploy a Java application, view services/versions, and use a version-specific URL to test a version that is not yet receiving traffic.
4. Orchestrate **traffic splitting, traffic migration, rollback**, and understand the conditions for using **--no-promote**, **--split-by**, and **--migrate**.
5. Choose the **standard/flexible** environment, scaling, workload identity, logging, and cost optimization approaches.
6. Troubleshoot deployment, routing, cold start, IAM, and release issues; complete exercises tied to real-world systems.

## 1. Resource model: application → service → version → instance

In the **CLOUD_PROVIDERS_GCP** module, learners organize projects, IAM, VPCs, and deploy to Compute Engine, GKE, Cloud Run, storage, and databases, while protecting resources and tracking costs. **App Engine** is a **PaaS** option: the development team focuses on web service code and declarative configuration, while the platform handles most of the infrastructure provisioning, routing, and scaling work.

~~~mermaid
flowchart TD
    P["Google Cloud project: shop-dev-001"] --> A["App Engine application<br/>region chosen once"]
    A --> D["Service: default<br/>frontend / Java API"]
    A --> W["Service: worker<br/>processing backend"]
    D --> D1["Version: web-v1<br/>traffic 90%"]
    D --> D2["Version: web-v2<br/>traffic 10%"]
    W --> W1["Version: worker-v4<br/>traffic 100%"]
    D1 --> I1["1..N instances"]
    D2 --> I2["1..N instances"]
    W1 --> I3["1..N instances"]
~~~

| Level | Nature | Example | Configuration scope |
|---|---|---|---|
| **Project** | Google Cloud boundary for IAM, APIs, billing, quotas | shop-dev-001 | IAM, APIs, budgets, other resources |
| **Application** | One App Engine application in a project, bound to one region | app of shop-dev-001 | Location, app-level routing |
| **Service** | An independent logical component, typically frontend/API/worker | default, worker | Own set of versions and traffic |
| **Version** | A release of code + configuration of a service | web-v2 | Runtime, instance class, scaling, env, code version |
| **Instance** | Running process/unit serving requests for a version | 3 instances of web-v2 | Created/stopped based on scaling and load |

**Core relationship:** one **service has multiple versions**, and one **version can run on multiple instances**. Deploying an additional version **does not** create a new application or project. The term *service* in App Engine is **not** a GKE Kubernetes Service object.

### 1.1. Example of separation of responsibilities

An e-commerce system has two services:

- **default**: receives HTTP requests from browsers, runs Java/Spring Boot, and reads Cloud SQL and Cloud Storage.
- **report-worker**: processes report generation requests through supported application flows.

The two services can use **different runtimes, instance classes, and scaling configurations**. Each service releases versions and splits traffic **independently**; shifting frontend traffic does not automatically shift report-worker traffic.

Do not treat the service boundary as an absolute security boundary: both still belong to the same project, may inherit project-level IAM policies, or share the App Engine default service account if not configured separately.

## 2. App Engine application: created once, choose the region carefully

**A Google Cloud project can only have one App Engine application.** When creating the app, you choose a **region**; once created, **you cannot change the region** of the app. An App Engine application resides in a region and Google operates it across multiple zones within that region, but this does not replace backup, data residency, or disaster recovery design.

### 2.1. How to choose a region?

Evaluate simultaneously:

- Where users are located, network latency targets, and where **Cloud SQL**, Cloud Storage, and Memorystore are placed.
- Whether the region supports **App Engine** and the runtime/features you plan to use.
- Data residency regulations, cross-region data transfer, network pricing, and availability requirements.
- The environment migration process if you must change regions later: **create a new project/app, migrate configuration and data, and switch DNS/traffic** rather than modifying the region of the existing app.

**Do not choose a region solely because it is closest to users:** if the database is in another region, a Java API making frequent DB calls may incur higher latency, egress costs, and HA complexity.

### 2.2. Check before creating

~~~bash
gcloud config get-value project
gcloud auth list
gcloud app describe --project=shop-dev-001
gcloud app regions list
~~~

If **gcloud app describe** returns application information, **do not create the app again**. If the app does not exist yet, run the creation command only after verifying the region, billing, APIs, and administrative permissions.

~~~bash
# ONLY run once on an approved lab project.
gcloud app create \
  --project=shop-dev-001 \
  --region=asia-southeast1

gcloud app describe --project=shop-dev-001
~~~

The project name and region are examples; confirm that **the region appears in the supported App Engine regions list** before running. Initializing the app is a long-term location decision. Do not use a production project to test a random region.

### 2.3. The default service must be deployed first

Every application has a **default service**. **You must deploy the first version to default before creating/deploying other services.**

If the **app.yaml** file does not declare a **service**, App Engine treats it as **default**. When declaring another service (for example **service: report-worker**), that name identifies a separate component.

**You cannot delete the default service** in the same way as a regular service. You can manage its versions and traffic; if you want to stop the entire application, you need to disable the application or manage the project through a separate procedure.

## 3. App Engine standard and flexible: which environment to choose?

Both environments share the **application/services/versions** model, but the underlying runtime infrastructure and scaling differ.

| Criterion | **Standard environment** | **Flexible environment** |
|---|---|---|
| Runtime | Supported Google-managed runtimes, e.g. Java 21/25 | Custom/supported container runtimes on Compute Engine VMs |
| Scaling | Automatic, basic, or manual depending on configuration | Automatic/manual depending on environment capabilities |
| Scale very low | Suitable for workloads with many low-traffic periods | Typically maintains a minimum number of instances, unlike standard scale-to-zero |
| Startup | May experience cold starts | Instances usually live longer, with infrastructure overhead |
| Configuration | Runtime + app.yaml, lower-level environment restrictions | Greater freedom to customize OS/container and dependencies |
| Free tier | Certain standard resources have conditional free quotas | Does not have the same free tier as standard |
| Cost | Instance hours, requests, bandwidth, and related resources | VM/container resources, storage, network, and related services |
| Traffic migration | Has a gradual mechanism when warmup is enabled and conditions are met | **Does not support gradual migration**; switches immediately |

**Recommendation:** start with **standard** when the Java app uses a supported runtime and does not need OS/container-level customization. Consider **flexible** when you need binary/system dependencies or environment customization that standard does not satisfy. For pure HTTP container applications that do not need the App Engine services/versions model, **Cloud Run** is also an option to compare.

**Never claim “standard is always cheaper”:** cost depends on workload, minimum instances, requests, CPU/memory, egress, builds, and databases.

## 4. Service: deployment and routing boundary

A service is a logical component of an application, owning multiple versions and an independent configuration set. You can:

- Choose separate **runtime/instance class/scaling** settings.
- Distribute traffic among versions **of that same service**.
- Access via the service URL or route using **dispatch.yaml**.
- Deploy and roll back independently without necessarily synchronizing with other services.

### 4.1. When to split services?

| Need | Decision |
|---|---|
| A small Java web app with a shared deployment lifecycle | **default** alone is usually sufficient |
| Frontend and reporting have different load patterns, SLOs, and lifecycles | Can split into **default** / **report-worker** |
| Need strong IAM/trust boundary isolation, separate budgets/quotas, sensitive data | Consider **splitting projects**, not just App Engine services |
| Already using GKE or Cloud Run for workers | No need to move everything into App Engine just to create uniformly named services |

### 4.2. Suggested Java project structure

~~~text
shop-web/
  pom.xml
  src/main/java/...                 # Java frontend
  src/main/appengine/app.yaml      # service: default

shop-report/
  pom.xml
  src/main/java/...                 # Java reporting
  src/main/appengine/app.yaml      # service: report-worker

app-routing/
  dispatch.yaml                    # application-level routing
~~~

This is an **illustrative diagram**, not files created in the lesson repository. Each **app.yaml** declares a different service. **dispatch.yaml** is a shared configuration for the entire app, not duplicated per version.

## 5. Version: unit of release, testing, and rollback

Deploying a bundle of code + configuration to a service creates a **version**. When no ID is specified, gcloud generates a version ID; when specifying **--version**, you can assign an easily traceable release ID, such as **v20261119-01**.

### 5.1. Versions differ from instances

~~~text
Service default
├── Version v1: runtime/java21 configuration, instance class F1
│   ├── Instance A
│   └── Instance B
└── Version v2: runtime/java25 configuration, instance class F2
    ├── Instance C
    └── Instance D
~~~

A version can scale out more instances **without creating a new version**. Deploying source code or changing scaling settings in **app.yaml** through a normal release creates a new version with the new configuration; changing traffic allocation **does not modify the binary contents of a version**.

### 5.2. Version IDs and promotion

| Action | Meaning |
|---|---|
| Deploy without **--version** | gcloud auto-generates a version ID |
| Deploy with **--version=v2** | Creates a version with the specified ID |
| Default deploy | Depending on CLI config, typically **promotes the new version to receive 100% of traffic** in the service |
| Deploy with **--no-promote** | Deploys the version but **keeps traffic on existing versions** |
| Redeploy with the same **version ID** | Can **overwrite** the old version, affecting rollback; use a new ID instead |
| Shift traffic back to an old version | **Routing rollback**, does not automatically restore database schema or data |

**Best practice:** use a **new version ID for every release**, test via the version-specific URL, and promote only after smoke tests and readiness checks pass. If releasing version v2 includes a non-backward-compatible database migration, routing traffic back to v1 may not restore the application; you must design **expand/contract database migrations** and corresponding rollback procedures.

### 5.3. A version receiving 0% traffic can still incur costs

Do not assume **0% incoming traffic = no running instances or charges**. Basic/manual scaling, minimum instances, background processing, or flexible environment characteristics can keep versions running and incurring charges. Always inspect **App Engine Versions/Instances, billing, and scaling configuration** before deleting or stopping.

## 6. app.yaml: describing a service version

**app.yaml** is the deployment descriptor for a service version: runtime, service, scaling, instance class, and environment variables. Its contents differ by **standard/flexible** and runtime; do not reuse Cloud Run or GKE YAML directly.

### 6.1. Standard Java example

In a Maven project, place **src/main/appengine/app.yaml**:

~~~yaml
runtime: java21
service: default
instance_class: F2

automatic_scaling:
  min_instances: 0
  max_instances: 10

env_variables:
  APP_ENV: "lab"
  REPORT_SERVICE_NAME: "report-worker"
~~~

**Explanation:** **runtime: java21** selects a supported Java standard runtime; current documentation also includes **java25**. **service: default** selects the frontend. **F2** selects the instance class; **automatic_scaling** manages the instance count; **min_instances: 0** keeps no minimum instances configured. **env_variables** is for non-sensitive configuration and must not contain passwords/API keys.

**New default:** since March 2025, the **default max_instances is 20** for new App Engine standard applications; older apps may differ. Explicitly declare max_instances according to load/budget limits and verify during deployment rather than relying on defaults from older docs.

### 6.2. Configuring a second service

~~~yaml
runtime: java21
service: report-worker
instance_class: F2
automatic_scaling:
  min_instances: 0
  max_instances: 4
env_variables:
  REPORT_MODE: "batch"
~~~

**service: report-worker** creates another logical service; it **does not** automatically turn an HTTP handler into a worker queue. For asynchronous work, integrate **Cloud Tasks, Pub/Sub**, or an appropriate batch processing platform rather than expecting auto-scaled instances to stay alive indefinitely running a loop.

### 6.3. Automatic, basic, and manual scaling

| Type | Behavior | Suitable for | Risks |
|---|---|---|---|
| **Automatic** | Scales instances up/down based on load, latency, concurrency | HTTP APIs, websites | Cold starts, bursts, quotas; requires sensible max/min |
| **Basic** | Starts when requests arrive, stops when idle | Intermittent workloads | Startup delay, do not store state on local disk |
| **Manual** | Fixed number of instances always running | Needs persistent processes or consistent latency | Charges when idle; requires HA planning |

Manual scaling example **instead of** automatic (do not declare both):

~~~yaml
runtime: java21
service: report-worker
instance_class: B2
manual_scaling:
  instances: 2
~~~

With **flexible**, scaling mechanisms, VM types, and cost models differ from standard. When multiple versions use different environments, do not assume **gradual migration** is supported between them.

## 7. Java/Spring Boot example: identifying the serving version

The app returns **service** and **version** to observe canary behavior. The **GAE_SERVICE** and **GAE_VERSION** system variables are provided by App Engine; do not manually set them in app.yaml.

~~~java
package example.appengine;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }

    @RestController
    static class ReleaseController {
        @GetMapping("/health")
        Map<String, String> health() {
            return Map.of(
                "status", "ok",
                "service", System.getenv().getOrDefault("GAE_SERVICE", "local"),
                "version", System.getenv().getOrDefault("GAE_VERSION", "local")
            );
        }
    }
}
~~~

This code assumes a Maven project using **Spring Boot Starter Web**. Minimal **pom.xml** example:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>shop-app</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

This is an **illustrative version** so learners understand the Maven structure; production must pin dependencies to tested versions, monitor CVEs, and check runtime support schedules. App Engine Java gen2 supports deploying Maven source via **gcloud app deploy pom.xml**, using Google Cloud's build process.

Ensure the HTTP server listens on the **PORT** provided by App Engine. In **src/main/resources/application.properties**:

~~~properties
server.port=${PORT:8080}
~~~

**PORT** must not be declared in **app.yaml env_variables** because the platform sets its value automatically. With a custom entrypoint or another web server, bind to the proper address/port. When running in local development, the fallback value 8080 is used.

**Why return the version?** When splitting traffic, the **/health** response helps verify which version served the request. However, cookie splitting can pin each client to one version; this check is illustrative only and does not replace request/error metrics. In production, do not expose sensitive metadata on public endpoints.

## 8. Hands-on Lab A — Deploy default then add a service

### 8.1. Prerequisites

Assume the App Engine application **shop-dev-001** already exists in the right region with two Maven projects. Deploy commands **modify resources and can incur costs**; only execute them on an authorized lab project and confirm IAM/billing/CI first.

~~~bash
gcloud config get-value project
gcloud auth list
gcloud app describe --project=shop-dev-001
gcloud app services list --project=shop-dev-001
gcloud app versions list --project=shop-dev-001
~~~

### 8.2. Deploy the first version to default

Inside the **shop-web** directory containing pom.xml, with **src/main/appengine/app.yaml** declaring the default service:

~~~bash
gcloud app deploy pom.xml \
  --project=shop-dev-001 \
  --version=web-v1

gcloud app services list --project=shop-dev-001
gcloud app versions list --service=default --project=shop-dev-001
~~~

In a new project, **default** must have a version before adding other services. Check the command output and **target service**; by default, deploy usually promotes the new version (unless gcloud configuration has been changed).

### 8.3. Deploy report-worker

After default is running, inside the **shop-report** directory:

~~~bash
gcloud app deploy pom.xml \
  --project=shop-dev-001 \
  --version=report-v1

gcloud app services list --project=shop-dev-001
gcloud app versions list \
  --service=report-worker \
  --project=shop-dev-001
~~~

The app.yaml file in **shop-report** **must contain** the line **service: report-worker**. Forgetting this declaration may accidentally deploy to default. Use a service-specific release checklist and dedicated IAM/deploy identities in real environments.

### 8.4. Get the actual URL

~~~bash
gcloud app browse --project=shop-dev-001 \
  --service=default --no-launch-browser

gcloud app browse --project=shop-dev-001 \
  --service=report-worker --version=report-v1 \
  --no-launch-browser
~~~

Call HTTP **/health** on the frontend if the deployed version exposes that endpoint. If report-worker has no /health endpoint, a 404 at that path does not by itself prove the service is broken.

## 9. Routing: default URL, service URL, and version URL

App Engine routes traffic using **hostnames**, **dispatch.yaml**, or in combination with **Cloud Load Balancing**.

### 9.1. Three hostname types

| Purpose | Illustrative URL format | Behavior |
|---|---|---|
| Application/default | **https://PROJECT_ID.REGION_ID.r.appspot.com** | Goes to default service per traffic allocation |
| A specific service | **https://SERVICE-dot-PROJECT_ID.REGION_ID.r.appspot.com** | Goes to the service per its own traffic allocation |
| A specific version | **https://VERSION-dot-SERVICE-dot-PROJECT_ID.REGION_ID.r.appspot.com** | Targets the version directly, **bypassing traffic splits** |

**REGION_ID** is a short region code assigned by Google, **not necessarily identical** to the string **asia-southeast1** passed to gcloud app create. Use **gcloud app browse --no-launch-browser** to get the actual URL instead of manually constructing hostnames.

For **HTTPS appspot.com**, service/version labels use **-dot-** as a separator when targeting specifically. Custom domains have separate host rules; do not assume custom domain URLs receive identical routing behavior.

### 9.2. A version URL is not a secret

A version **web-v2** deployed with **--no-promote** still has its own URL:

~~~bash
gcloud app browse \
  --project=shop-dev-001 \
  --service=default \
  --version=web-v2 \
  --no-launch-browser
~~~

If the application is public and lacks additional authentication controls, anyone who knows the version URL can still call it. **0% traffic from the service URL does not mean a private endpoint**. Do not leave unprotected debug/admin routes just because the version has not been promoted yet.

### 9.3. dispatch.yaml: selecting a service by path

Example **dispatch.yaml** file applied to the application:

~~~yaml
dispatch:
  - url: "*/reports/*"
    service: report-worker
  - url: "*/api/*"
    service: default
~~~

After both services have been deployed:

~~~bash
gcloud app deploy dispatch.yaml --project=shop-dev-001
~~~

**dispatch.yaml is an app-wide configuration**, not tied to a specific version. Rules are evaluated **in order**, and the first matching rule wins; pattern/host limits must follow documentation. **Targeted routing URLs** addressing a specific service/version directly can bypass dispatch rules. With an external HTTPS Load Balancer, there may be another routing layer in front of App Engine.

### 9.4. Soft routing

If an **appspot.com hostname** targets a non-existent service/version, some requests may **soft route** to the default service. Therefore, HTTP 200 does not prove the intended worker/version was called. Verify the actual hostname, **GAE_SERVICE/GAE_VERSION**, Cloud Logging, and the versions currently receiving traffic. Invalid hostnames on custom domains typically have different 404 behavior.

## 10. Traffic splitting: canary and A/B testing

**Traffic splitting** distributes requests among **versions of the same service** by weight. It applies to the **service URL** or routes targeting a service without specifying a version; it **does not** apply to URLs targeting a specific version directly.

### 10.1. 90/10 example

Assume the **default** service has:

- **web-v1**: already released, currently receiving 100%.
- **web-v2**: newly deployed, directly tested.

Run:

~~~bash
gcloud app services set-traffic default \
  --project=shop-dev-001 \
  --splits=web-v1=0.9,web-v2=0.1 \
  --split-by=cookie
~~~

Then verify:

~~~bash
gcloud app services describe default --project=shop-dev-001
gcloud app versions list --service=default --project=shop-dev-001
~~~

**Weights** are normalized; 0.9/0.1 corresponds to a **90% / 10%** target. Short-term observed results may vary due to small request samples, cookie stickiness, caches, and IP distribution.

### 10.2. Split by IP, cookie, or random

| Method | Characteristics | Things to watch |
|---|---|---|
| **ip** (default) | Hashes sender IP address, usually keeps a sender on the same version | NAT/proxies cause many users to share an IP; mobile devices change IPs |
| **cookie** | **GOOGAPPUID** cookie pins a user to a version bucket | Good for user A/B testing, requires clients to store/forward cookies; consider caching |
| **random** | Assigns each request independently by weight | Does not guarantee a user stays on the same version |

Cookie example:

~~~text
User A has web-v1 bucket cookie:
  request 1 → web-v1
  request 2 → web-v1

User B has web-v2 bucket cookie:
  request 1 → web-v2
  request 2 → web-v2
~~~

In an e-commerce system, cookie splitting helps give users a consistent A/B experience; however, if APIs are called by mobile/native clients or between services, cookies must be properly managed/forwarded. If all traffic flows through the same proxy IP, **IP splitting** can skew significantly from the desired ratio.

### 10.3. Conditions for safe canary releases

Before shifting 10% traffic:

1. **Version v2** is deployed with **--no-promote** and smoke-tested via its version URL.
2. **Database schema, message formats, and session state** are compatible between v1/v2; do not keep unique state only in an instance's memory.
3. Metrics/alerts exist for **HTTP 5xx, p95/p99 latency, business errors, and billing**, with service/version labels.
4. A fast rollback plan using **set-traffic** is prepared.
5. An impact mitigation plan exists if v2 fails even for just 10% of customers.

**Traffic splitting is not a per-API-route feature flag.** If you want only staff members to see a feature based on identity, you need application logic or an appropriate feature flag tool; cookie splitting only pins versions at the request/client level.

## 11. Traffic migration, rollback, and zero-downtime releases

### 11.1. Deploy v2 without receiving traffic

~~~bash
# Inside the Java project containing pom.xml / app.yaml for the right service.
gcloud app deploy pom.xml \
  --project=shop-dev-001 \
  --version=web-v2 \
  --no-promote

# Print v2 version URL for smoke testing
gcloud app browse \
  --project=shop-dev-001 \
  --service=default \
  --version=web-v2 \
  --no-launch-browser
~~~

**--no-promote** preserves the current split; it **does not** mean the new version is secured or consumes zero resources. Every test must confirm the exact targeted version and the application version actually serving.

### 11.2. Shift 100% traffic immediately

~~~bash
gcloud app services set-traffic default \
  --project=shop-dev-001 \
  --splits=web-v2=1
~~~

This is a routing operation and does not create a new build. When v2 does not yet have ready instances, a **latency spike** due to cold starts may occur. Monitor readiness, load, and warmup before switching.

### 11.3. Gradual migration differs from traffic splitting

In **App Engine standard**, **--migrate** can gradually shift traffic from an old version to a new version when **warmup requests** and appropriate conditions are met, helping the autoscaler spin up instances before receiving full load:

~~~bash
gcloud app services set-traffic default \
  --project=shop-dev-001 \
  --splits=web-v2=1 \
  --migrate
~~~

**Do not assume --migrate always shifts gradually.** If warmup requests are not enabled, traffic may shift **immediately**. **The flexible environment does not support gradual traffic migration**; it switches immediately to the target version. When switching between versions in different standard/flexible environments, conditions may also force an immediate cutover.

For Spring Boot/Java, check the Java runtime's **warmup requests** documentation to enable and test properly; do not copy warmup configuration meant for another runtime without verification.

### 11.4. Routing rollback

If canary metrics degrade, shift all traffic back to v1:

~~~bash
gcloud app services set-traffic default \
  --project=shop-dev-001 \
  --splits=web-v1=1

gcloud app versions list \
  --service=default \
  --project=shop-dev-001
~~~

This is a **routing rollback**, which is usually faster than redeploying code, but is only safe if v1 still exists/runs and **databases, event schemas, secrets, and external APIs** remain compatible. If v2 deleted data or made incompatible schema changes, rolling back the code version may not recover the system.

### 11.5. Phased deployment runbook

~~~mermaid
flowchart TD
    A["Java build/test + config check"] --> B["Deploy v2 --no-promote"]
    B --> C["Smoke test v2 version URL"]
    C --> D{"Health, IAM, DB migrations OK?"}
    D -->|No| X["Keep v1 traffic, fix and deploy new version"]
    D -->|Yes| E["Split 90% v1 / 10% v2"]
    E --> F{"Error rate and latency OK?"}
    F -->|No| R["Rollback --splits=v1=1"]
    F -->|Yes| G["Increase to 50% then 100%"]
    G --> H["Monitor SLOs, clean up unused versions"]
~~~

**Note:** for a public endpoint with many requests per user, **10% of requests** does not necessarily equal **10% of users**. Choose the right splitting method and observation criteria before running an A/B experiment with business conclusions.

## 12. Managing services, versions, and instances after deployment

### 12.1. Useful read-only commands

~~~bash
gcloud app services list --project=shop-dev-001
gcloud app versions list --service=default --project=shop-dev-001
gcloud app versions list --hide-no-traffic --project=shop-dev-001
gcloud app instances list --service=default --project=shop-dev-001
gcloud app services describe default --project=shop-dev-001

gcloud app logs read \
  --service=default \
  --version=web-v2 \
  --limit=50 \
  --project=shop-dev-001
~~~

**gcloud app versions list --hide-no-traffic** filters out versions not receiving traffic via routing; this is not enough to conclude those versions are stopped and incurring zero cost.

### 12.2. Stop and delete are not the same

~~~bash
# Caution: stop a version (depends on scaling type)
gcloud app versions stop \
  --service=default \
  web-v2 \
  --project=shop-dev-001

# Delete a version only after removing it from traffic allocation.
gcloud app versions delete \
  --service=default \
  web-v2 \
  --project=shop-dev-001
~~~

**Delete is a destructive operation**; you cannot restore that version's source/config merely by shifting traffic. You cannot delete a version **currently receiving traffic**. If planning to delete an entire non-default service, inspect all versions of that service and preserve policies/configs under change control. **You cannot delete the default service** using standard service deletion commands.

For auto-scaled standard versions, **stop** has limitations; confirm the scaling type and proper stopping method in actual runtime documentation. Do not treat stop as a “guaranteed cost-cutting fix” without checking Instances/Billing afterward.

### 12.3. Why avoid keeping too many versions?

- **Manual/basic/flexible/min_instances** can keep instances consuming resources.
- Many versions make routing info, IAM, config drift, and ownership harder to track.
- Staging/build artifacts, logs, and related storage may incur costs.
- Deleting too early loses the **rollback** target.

**Good process:** keep versions per a deliberate retention policy, tag reliable releases, clean up only versions with no remaining traffic/rollback dependencies, and reconcile costs after cleanup.

## 13. IAM, service identity, and connecting to GCP resources

An App Engine version can call **Cloud Storage**, **Cloud SQL**, **Secret Manager**, and other Google Cloud APIs. You must separate the **deployment identity** from the **application runtime identity**.

| Principal | What does it need to do? | Suggested permissions |
|---|---|---|
| **Developer/CI deployer** | Create versions, configure services | App Engine Deployer and permission to act as service account; may need Cloud Build/staging permissions per project |
| **Build service account** | Build Java code and upload required artifacts | Appropriate Cloud Build, Artifact Registry, and staging permissions |
| **App Engine runtime service account** | Access data APIs while the application runs | Bucket Object Viewer, Secret Accessor, Cloud SQL Client as actually needed |
| **Release operator** | Shift traffic, roll back, clean up versions | Appropriate App Engine traffic/version management permissions |
| **Security/auditor** | View IAM, deployments, logs | Scoped read-only/audit roles |

### 13.1. The default service account should not have broad permissions by default

App Engine has a traditional default service account of the form **PROJECT_ID@appspot.gserviceaccount.com**, though default permission policies in newer projects have changed. **Do not assume this account has Editor**, nor grant Editor just to “make the app work”.

During deployment, you can specify a dedicated service account for the version:

~~~bash
gcloud app deploy pom.xml \
  --project=shop-dev-001 \
  --version=web-v3 \
  --no-promote \
  --service-account=shop-web-runtime@shop-dev-001.iam.gserviceaccount.com
~~~

The service account must exist; the deploying principal must have permission to **act as (use)** it. The runtime account should only hold roles on the required resources:

- **roles/storage.objectViewer** on the bucket containing read-only images.
- **roles/secretmanager.secretAccessor** on the specific secret, if the Java SDK reads secrets.
- **roles/cloudsql.client** if connecting to Cloud SQL via a supported connector/proxy model; database authentication is a separate step.

**IAM alone does not guarantee network access** to a private-IP database. For VPC/private service connectivity, check VPC egress, serverless connectors, firewalls, and the appropriate Cloud SQL architecture for standard/flexible.

### 13.2. Do not embed long-lived keys in app.yaml or images

**env_variables** in app.yaml can be visible to anyone with permission to read configurations. Avoid placing access tokens, private keys, or DB passwords there. Use **Secret Manager** with **Application Default Credentials** and grant secretAccessor appropriately; restrict access to source/CI logs. Consider secret injection mechanisms approved by your organization for the runtime/tooling.

**Services/versions sharing a project are not automatically IAM-isolated**: assign dedicated service accounts, review inherited principals, and verify actual API permissions. IAM changes can cause an already deployed version to fail at runtime without a redeploy.

## 14. Monitoring performance, cost, and availability

### 14.1. Metrics to observe per service/version

| Group | Metrics | When action is needed |
|---|---|---|
| **HTTP** | Request count, 4xx/5xx, p50/p95/p99 latency | Canary v2 increases errors or latency |
| **Scaling** | Instance count, instance class, cold-start/startup latency | Too many instances or load rises without scaling |
| **Runtime** | JVM heap, GC pauses, exceptions, health/readiness | Java app runs out of memory, slow startup |
| **Database/storage** | Cloud SQL connection count, query latency, object errors | App only fails when backend bottlenecks |
| **Release** | Traffic distribution, deployed versions, log labels | New version receives unintended traffic |
| **Cost** | Instance hours, egress, requests, build/staging, database | Sudden quota or budget spike |

Check the **App Engine dashboard**, **Cloud Monitoring**, **Cloud Logging**, **Error Reporting**, and **Cloud Billing reports**. For A/B experiments, distinguish **version logs**; aggregate service latency can mask errors occurring only on v2.

### 14.2. Easily overlooked costs

- A service with multiple **manual/flexible/min_instances** versions can keep billable resources running even when a version receives 0% traffic.
- High **max_instances** can drive up costs during peak/bot traffic while opening too many Cloud SQL connections and overloading the DB.
- Changing **instance_class** and scaling thresholds affects CPU/memory costs.
- Static files, Cloud Storage, Cloud SQL, network egress, Cloud Build, and logging have separate pricing/quotas.
- Standard has a **conditional free usage quota**, not unlimited free usage; flexible does not have the same free tier.

Set **Cloud Billing budget alerts**, monitor per-service costs, and configure alerts for request/instance spikes. **A budget alert is not an automatic resource kill switch.** Before raising min instances to eliminate cold starts, weigh the SLO improvement against the added cost.

### 14.3. Statelessness and rollout safety

App Engine instances can be restarted, replaced, or stopped. For Java:

1. **Do not store sessions/carts/orders solely in memory or the local filesystem** of an instance.
2. Store transactional data in **Cloud SQL/Firestore/Spanner** per use case; store objects in **Cloud Storage**.
3. Use bounded connection pooling so multiple instances do not exceed Cloud SQL maximum connections.
4. Make APIs **idempotent** for retries/timeouts where appropriate to avoid duplicate orders.
5. Configure **graceful shutdown**, timeouts, health checks, and rollback capability.
6. Prefer **backward-compatible database migrations** across versions sharing traffic.

## 15. Troubleshooting App Engine application, services, and versions

| Symptom | Common cause | Check |
|---|---|---|
| **gcloud app create** reports already exists | A project can only have one application | **gcloud app describe**, current region |
| Want to change App Engine region | Region is immutable once created | Need a new project/app and migration plan |
| Deploying a new service fails | **default** was not deployed first | App versions list, deploy default first |
| Deployed report-worker but only see default | Missing **service: report-worker** in app.yaml | Actual app.yaml in Maven build/staging |
| Java deploy succeeds but app returns 5xx | Wrong port, startup error, missing env/IAM, or dependency | Cloud Build output, **gcloud app logs read**, JVM logs |
| /health returns unexpected version | URL/dispatch/traffic split/cookie | app browse, service describe, GAE_VERSION |
| **--no-promote** yet version URL is reachable | Expected behavior; version URL is not blocked by traffic split | Check endpoint auth, do not rely on 0% traffic |
| Canary 90/10 but only one version seen | Cookie/IP stickiness, small request sample, cache | --split-by, client cookies, version metrics |
| **--migrate** switches immediately | Warmup not enabled or environment does not support gradual | Warmup, standard/flexible, traffic migration docs |
| Request to non-existent service returns 200 | Appspot **soft routing** to default | Check hostname, service/version in response |
| Old 0% version still incurs charges | Manual/basic/flexible, min instances, or other resources | Instances, version scaling, Billing |
| Cannot delete version | Version still receives traffic | Set-traffic to another version first; verify |
| App gets 403 reading GCS/Secret Manager | Runtime service account lacks permissions | Service identity, bucket/secret IAM; do not grant Owner |
| Image/deploy build fails | Build service account, staging bucket, dependency/runtime error | Cloud Build logs, deployer IAM, Maven dependencies |
| App overloaded while Cloud Run/GKE remain healthy | max_instances, DB pool, instance class, quota | Per-service/version and backend metrics |

**Isolation workflow:**

1. **Confirm project and App Engine application**: do not look at the wrong project or region.
2. **Confirm target service/version**: app.yaml, gcloud output, and hostname.
3. **Distinguish deployment errors from request errors**: Cloud Build/deployment logs differ from runtime HTTP logs.
4. **Inspect traffic allocation** and versions receiving requests; watch out for cookies/IPs.
5. **Check identity/IAM** and connectivity to databases/storage if Java fails at runtime.
6. **Measure instance count/cold starts**, quotas, and billing if errors occur only under traffic spikes.
7. **Roll back traffic** when a canary fails, preserving logs/release artifacts for investigation and retrying with a new version ID.

## 16. End-to-end scenario: releasing a Java API on App Engine

The **Sao Mai** product team has a Java frontend accessing Cloud SQL and Cloud Storage:

| Component | Choice | Reason |
|---|---|---|
| Web/API | App Engine standard, **default** service | Java code fits managed runtime |
| Reporting | **report-worker** service | Independent scaling and releases |
| Order data | Cloud SQL PostgreSQL | Managed transactions and backups |
| Invoice images | Private Cloud Storage bucket | Object storage and IAM |
| Release versions | **web-v1**, **web-v2** | Canary deployment and rollback |
| Runtime identity | Dedicated service account per workload | Least privilege; no JSON keys |

### 16.1. Safe release

~~~mermaid
flowchart TD
    B["Build + tests + security review"] --> D["Deploy web-v2 --no-promote"]
    D --> T["Test direct version URL"]
    T --> C{"Smoke/DB/IAM OK?"}
    C -->|No| FIX["Fix code then deploy new version"]
    C -->|Yes| S["Split web-v1:90 / web-v2:10"]
    S --> O["Observe 5xx, p99, DB connections"]
    O --> DEC{"SLOs met?"}
    DEC -->|No| R["Roll back traffic to web-v1"]
    DEC -->|Yes| P["Promote 100% web-v2"]
    P --> K["Keep v1 for rollback, clean up per retention"]
~~~

Suppose at 10% traffic, v2 increases p95 latency from 150 ms to 900 ms because it opens a new DB connection per request. The team halts the rollout, shifts traffic back to v1, fixes connection pooling, and deploys **web-v3** instead of overwriting version v2.

### 16.2. Acceptance matrix

| Test | Expected result |
|---|---|
| Deploy default first | Application has a default version |
| Deploy report-worker | Second service appears without altering default |
| web-v2 --no-promote | Default traffic still goes to v1 |
| Call web-v2 version URL | Reaches v2 regardless of service split |
| 90/10 split by cookie | Maintains affinity within cookie scope |
| web-v2 missing Storage IAM | Backend error detected without granting project-wide permissions |
| Traffic rollback | All new requests via service URL return to v1, except targeted URLs/caches |
| Database migration | v1 and v2 both work with the schema during canary |
| Version cleanup | Do not delete versions receiving traffic or retained for rollback |
| Billing | Measure impact of instances and non-App Engine resources |

## 17. Exercises with answers

### Exercise A — Determine the structure

A project has **one App Engine application**, two services **default** and **analytics**, each service with three versions; at a given moment each version runs two instances.

**Question:** How many App Engine applications, services, versions, and instances are there?

**Answer:** **1 application, 2 services, 6 versions, 12 instances**. Instances are runtime execution units, not releases.

### Exercise B — Error when creating region

A project already created an application in region A. The operations team wants to use region B because Cloud SQL is in B.

**Question:** Can they run **gcloud app create --region=B** to change it?

**Answer:** No. **Once chosen, the region cannot be changed**; they must create an application in another project and migrate source code, configuration, data, and DNS/traffic according to plan.

### Exercise C — Find the app.yaml error

~~~yaml
runtime: java21
instance_class: F2
automatic_scaling:
  max_instances: 5
~~~

The file is meant for report-worker, but after deploying only **default** appears.

**Answer:** Missing **service: report-worker**, so the version was deployed to default. Add the correct service field and **deploy a new version**; check traffic affected by the accidental deployment.

### Exercise D — Canary and version-specific URL

web-v1 receives 90%, web-v2 receives 10% by cookie. A tester keeps calling the URL **web-v2-dot-default-dot-...** and only sees v2.

**Question:** Is traffic splitting malfunctioning?

**Answer:** No. A **version URL** targets v2 directly, **bypassing the service-level traffic split**. Test splitting via the URL without a version prefix and measure across multiple clients/cookies.

### Exercise E — Choose a splitting method

A mobile app calls an HTTP API through a single NAT gateway; user-level A/B testing is needed, and each user has their own session.

**Question:** Is IP split or cookie split more suitable?

**Answer:** **Cookie split** is more suitable for maintaining user affinity if the mobile client manages/forwards GOOGAPPUID. IP split behind a NAT gateway may lump many users into one bucket; random split may switch versions between requests from the same user.

### Exercise F — Deploy without changing traffic

**Requirement:** Write the command to deploy Maven version **web-v3** while keeping all traffic on web-v1.

**Answer:**

~~~bash
gcloud app deploy pom.xml --project=shop-dev-001 \
  --version=web-v3 --no-promote
~~~

Then use **gcloud app browse --service=default --version=web-v3 --no-launch-browser** for isolated smoke testing.

### Exercise G — Rollback and database compatibility

web-v2 modified a required column in Cloud SQL so web-v1 can no longer write to it. When v2 fails, the team plans to run **set-traffic default --splits=web-v1=1**.

**Question:** Is this a complete rollback?

**Answer:** No. The command only changes routing; the **database schema** remains altered. You need an **expand/contract** plan, dual-version compatible migrations, or DB schema/data restoration procedures. Test rollback in staging before releasing.

### Exercise H — Cost and deleting versions

An old App Engine flexible version receives 0% traffic but still runs instances. The team wants to delete it immediately to save money.

**Question:** What needs to be checked?

**Answer:** Confirm there are no targeted URLs, jobs, dependencies, rollback fallback needs, or traffic still hitting it; inspect instances/billing and prepare replacement artifacts/rollback plans. **0% traffic does not guarantee zero cost**, and deleting a version is a destructive operation.

## 18. Summary and references

**Six principles to remember:**

1. **Project → application → services → versions → instances** is the App Engine hierarchy; a project has only one application and its region **cannot be changed** after creation.
2. **Default service** must be deployed first; add services with the **service** field in app.yaml, each with independent versions and traffic.
3. **Version** is the release unit; create a new version ID for each release and use **--no-promote** to test safely before shifting traffic.
4. **Traffic splitting** distributes requests at the service level; **version URLs** target a release directly. Cookie/IP/random each have different affinity behaviors.
5. **Migration/rollback** is a routing change and does not reverse schema/data changes; gradual migration has constraints regarding warmup and flexible environments.
6. **Scaling, IAM, logs, budgets, and release discipline** determine reliability and total cost; App Engine does not replace application security or data backups.

**Official Google Cloud documentation:**

1. [An overview of App Engine](https://docs.cloud.google.com/appengine/docs/an-overview-of-app-engine) — app/services/versions/instances model.
2. [Set up a project and App Engine application](https://docs.cloud.google.com/appengine/docs/standard/managing-projects-apps-billing) — regions and the one-application-per-project limit.
3. [Structuring web services](https://docs.cloud.google.com/appengine/docs/standard/configuration-files) — default service, multiple services, and YAML files.
4. [Java standard runtime](https://docs.cloud.google.com/appengine/docs/standard/java-gen2/runtime) — Java runtimes, PORT, Maven/JAR startup.
5. [Java app.yaml configuration](https://docs.cloud.google.com/appengine/docs/standard/java-gen2/configuring-your-app-with-app-yaml) — service, version, and Java config.
6. [app.yaml reference](https://docs.cloud.google.com/appengine/docs/standard/reference/app-yaml) — scaling, env, and handlers.
7. [Deploy an App Engine application](https://docs.cloud.google.com/appengine/docs/standard/testing-and-deploying-your-app) — deploy, no-promote, and version behavior.
8. [How requests are routed](https://docs.cloud.google.com/appengine/docs/standard/how-requests-are-routed) — service/version URLs and dispatch.
9. [Splitting traffic](https://docs.cloud.google.com/appengine/docs/standard/splitting-traffic) — IP/cookie and canary ratios.
10. [Migrating traffic](https://docs.cloud.google.com/appengine/docs/standard/migrating-traffic) — gradual/immediate and warmup.
11. [How instances are managed](https://docs.cloud.google.com/appengine/docs/standard/how-instances-are-managed) — scaling and version management.
12. [gcloud app deploy reference](https://docs.cloud.google.com/sdk/gcloud/reference/app/deploy) — --version/--no-promote flags.
13. [gcloud app services set-traffic](https://docs.cloud.google.com/sdk/gcloud/reference/app/services/set-traffic) — splits and --migrate.
14. [gcloud app versions delete](https://docs.cloud.google.com/sdk/gcloud/reference/app/versions/delete) — restrictions on deleting traffic-serving versions.

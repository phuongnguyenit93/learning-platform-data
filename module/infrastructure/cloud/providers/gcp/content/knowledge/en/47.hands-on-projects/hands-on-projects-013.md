# Failover and Data Recovery Drill Project on GCP

An e-commerce system can run smoothly for months and then stop accepting orders when its database loses connectivity, a zone fails, or a bad deployment corrupts data. To prove resilience, an operations team needs more than a "backup enabled" checkbox: it must know **when to switch to a standby region, how to avoid creating two independent writers, how much data a replica could lose, and how to verify the service truly works again**.

This project walks through building a **Java 21 + Spring Boot test app on Cloud Run** storing synthetic orders in **Cloud SQL for PostgreSQL**, with a primary instance in Region A and an asynchronous read replica in Region B. Learners practice **in-region failover with Cloud SQL HA**, **cross-region failover by promoting the replica**, **data recovery via Point-in-Time Recovery (PITR)**, and **object recovery using Cloud Storage soft delete**. Every drill requires recording timestamps, measured RPO/RTO, and evidence.

This lesson belongs to the **GCP Hands-On Projects** chapter of the **CLOUD_PROVIDERS_GCP** module. The module explores Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases; through deployment scenarios, learners practice selecting services, protecting resources, automating releases, and monitoring reliability and cost. This lesson pulls those concepts into a DR drill covering cutover, verification, cleanup, and reporting.

> **Safety:** This is a **staging/lab** design. Promoting a read replica, switching database writers, shifting traffic, deleting data, or creating a PITR clone can disrupt service and incur costs. Never run impactful commands on production, never practice by causing a real outage in a region, and never delete data outside synthetic resources you own. Real-world drills require an Incident Commander, Security, DBA, and change approver.

## Objectives and Deliverables

After completing this project, you must be able to explain and demonstrate:

- The differences between **in-region HA**, **cross-region DR**, **backup/restore**, and **PITR for logical write errors**.
- Why a Cloud SQL cross-region read replica **does not automatically fail over** in the basic model and why asynchronous replication can lose data.
- How to deploy the same Cloud Run image across two regions, enforce a single-writer guard, and update connection configs after promotion.
- How to verify replica lag, preserve synthetic data, run smoke tests, and decide when to open traffic.
- How to simulate data loss and recover via PITR or Cloud Storage soft delete.
- How to calculate RTO/RPO from actual timestamps rather than assuming success because a CLI command returned zero.
- How to write a runbook, capture logs, manage costs, fail back, and reconcile unsynchronized data.

**Submission package:** architecture diagram, assumptions table, source/image config, drill execution log, before/after data comparison, measured RPO/RTO, security checklist, and failback/cleanup plan. Never submit passwords, tokens, or customer data.

## 1. Hypothetical Model and Non-Functional Requirements

The demo app, `dr-orders`, stores three fields: a UUID `id`, a positive integer `amount`, and `created_at`. Clients can create and look up orders. Each order uses a client-supplied ID to prevent duplicate inserts on retry. The lab involves no real payments or customer data.

| Requirement | Target Assumption | How to Verify |
|---|---|---|
| Business journey | POST order → read back via GET | Compare ID/amount before and after drill |
| Normal availability | 99.9% monthly objective | Define an SLI; do not confuse with GCP's SLA |
| DR RTO | No more than 45 minutes | From simulated incident start until POST/GET succeeds |
| DR RPO | No more than 5 minutes | Last write on primary vs. writes present on standby |
| Data recovery | Recover prior to data-corrupting operation | PITR clone and row reconciliation |
| Isolation | Dedicated staging project, synthetic data | IAM, billing, and resource inventory |
| Write safety | Only one database receives app writes at any time | App guard and traffic/DB fencing |
| Security | Secret Manager, runtime SA, IAM invoker | Inspect permissions and Cloud Audit Logs |
| Cost | Estimates, budget alerts, cleanup plan | Billing report by SKU |

These RTO/RPO values are **lab targets**, not guarantees provided automatically by Cloud SQL replication or Cloud Run. In particular, asynchronous replication cannot guarantee RPO = 0 if the primary region suddenly becomes unreachable.

### 1.1. Test Scope

The project includes four distinct drills:

1. **Zonal HA:** trigger a test failover on a Cloud SQL HA instance within the same region; the application connection name normally stays unchanged.
2. **Regional DR:** halt writes to A, evaluate lag, **promote** read replica B, reconfigure Cloud Run B to write to B, and shift the client.
3. **Logical recovery:** on an active primary with a valid PITR window, simulate corrupting a row and create a PITR clone into a **new instance**.
4. **Object recovery:** in a lab bucket, delete a synthetic object, locate its soft-deleted generation, and restore it.

You do not need to run all four drills in a single session or on a single instance; **run PITR before promotion or on another primary with existing backup/PITR history**, rather than assuming a newly promoted instance immediately holds full PITR history.

## 2. Lab Architecture: Active/Standby, Single Writer

| Component | Region A | Region B |
|---|---|---|
| Cloud Run | `dr-orders` active revision | `dr-orders` standby revision, same image |
| Cloud SQL | `dr-pg-primary`, PostgreSQL HA | `dr-pg-replica`, cross-region read replica |
| Application | `APP_WRITES_ENABLED=true` | `APP_WRITES_ENABLED=false` |
| Connection | A → primary A | B → primary A initially; switched to B after promotion |
| Client | Calls Cloud Run A URL | Switches to B only after release gates pass |
| Backup/restore | Automated backups + PITR | Replicas do not replace backups/PITR |
| Monitoring | Metrics and logs for A | Metrics and logs for B |

~~~mermaid
flowchart TD
    C["Client / traffic routing"] -->|"Normal"| RA["Cloud Run A: writer"]
    C -.->|"Only after DR cutover"| RB["Cloud Run B: standby"]
    RA -->|"JDBC + Cloud SQL Connector"| DBA[("Cloud SQL A: primary HA")]
    RB -.->|"Initially points to A, write guard OFF"| DBA
    DBA -->|"Asynchronous replication"| DBB[("Cloud SQL B: read replica")]
    RB -->|"Post-promotion: switch connection + enable writes"| DBB
    DBA --> BK["Backups + PITR logs"]
    RA --> OBS["Cloud Logging / Monitoring"]
    RB --> OBS
    DBB --> OBS
    BK -.->|"Restore into separate instance"| REC[("PITR recovery instance")]
~~~

**Critical control point:** having Cloud Run services in two regions **does not mean the database supports multi-region automatic failover**. Never route clients to B while B still points at an unavailable primary A. Before B starts accepting writes, **fence** A: block/drain incoming requests to the old writer, confirm in-flight requests have drained, and prevent A from accepting writes if it returns.

An environment toggle `APP_WRITES_ENABLED=false` lets you **rehearse while A is still reachable**; it is not strong fencing for a real regional outage where you might be unable to update A's config. Production requires traffic routing/fencing, permission controls, and procedures to handle the old primary upon recovery to prevent **split brain**. Never allow concurrent writes to two independent primaries.

### 2.1. Traffic Routing Approach

To keep the lab easy to verify, we use **manual URL cutover**: the test client calls URL A before the simulated outage and URL B after DR conditions are met. This simulates redirection, not automatic global failover.

Production setups can use a global external Application Load Balancer with regional serverless NEGs and Cloud Run service health or an appropriate failover mechanism. **Merely placing two regional Cloud Run services behind a load balancer does not guarantee automatic failover when a region fails.** With manual failover, backend/URL map edits and verification belong in an approved runbook.

## 3. Preparation and Cost Layers

### 3.1. Prerequisites

- A **dedicated GCP lab project** with billing enabled; never use production.
- Operator bootstrap permissions across Cloud SQL, Cloud Run, Artifact Registry, Secret Manager, IAM, and Cloud Storage.
- `gcloud` CLI, Java 21, Maven, Git, and read access to Cloud Monitoring/Logging.
- Two regions supporting Cloud SQL PostgreSQL, Cloud Run, and the required machine types.
- Budget alerts and cost estimates; a Cloud SQL HA + cross-region replica setup is **much more expensive** than a pure Cloud Run lab.
- Designated approvers for promotion, PITR cloning, writer changes, and post-lab resource deletion.

Example variable setup in Cloud Shell/Linux:

~~~bash
export PROJECT_ID="YOUR-DR-LAB-PROJECT"
export REGION_A="asia-southeast1"
export REGION_B="asia-southeast2"
export PRIMARY="dr-pg-primary"
export REPLICA="dr-pg-replica"
export DB_NAME="orders"
export SERVICE="dr-orders"
export REPO="dr-lab"
export IMAGE="${REGION_A}-docker.pkg.dev/${PROJECT_ID}/${REPO}/dr-orders:v1"

gcloud config set project "${PROJECT_ID}"
gcloud config get-value project
gcloud auth list
~~~

Regions are illustrative. Check data residency, quotas, VPCs, latency, and pricing before creating data. If your account is read-only, perform the **tabletop** portion rather than bypassing controls to request Editor/Owner.

### 3.2. Enabling APIs

~~~bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  --project="${PROJECT_ID}"
~~~

Services may need extra setup depending on app packaging and organizational policy. API enablement and IAM grants should be performed by administrators or an authorized IaC pipeline.

### 3.3. Cost Items to Estimate

| Cost Source | Why It Accrues Even with Low Traffic | Control |
|---|---|---|
| Cloud SQL HA A | Compute, HA standby, storage, backups | Time-box the lab, size minimally |
| Cloud SQL replica B | Continuously running replication instance, storage | Never leave lab replicas running indefinitely |
| Cloud Run A/B | Requests, CPU/memory, min instances if set | `min-instances=0` in lab when cold starts are acceptable |
| Cross-region replication | Network transfer per pricing and data volume | Keep test data tiny, monitor egress |
| Cloud Storage | Objects, soft-delete retention, operations | Dedicated lab bucket, TTLs, deliberate cleanup |
| Cloud Build/Artifact Registry | Build minutes and image storage | Build once, reuse image digest |
| Logging/Monitoring | Log and metric volume/retention | Structured logging, avoid log spam |
| PITR clone | **New instance** and separate storage | Delete after reconciliation, gate with approval |

A Cloud Billing **budget alert is not a spending cap**. You can reduce costs via a **read-only tabletop mode** without provisioning a real Cloud SQL replica. Execute the live-resource hands-on steps only once budget and approvals are ready.

## 4. Decision Log Before Each Operation

Every action affecting data or routing needs a log entry:

| Field | Example |
|---|---|
| Drill ID | `DRILL-2026-11-LAB` |
| Change owner | SRE on-call |
| Data owner | Orders team |
| Security reviewer | Security engineer |
| Test start time | UTC timestamp |
| Baseline | Image digest, instance IDs, row IDs, LSN/lag |
| RPO/RTO goals | 5 minutes / 45 minutes |
| Action gate | Entry criteria, approver |
| Recovery target | Region B or new PITR instance |
| Fencing | Old writer stopped with zero remaining traffic |
| Rollback plan | Return to defined safe state |

**Never equate "`gcloud` succeeded" with "service recovered".** Successful cutover requires verifying end-to-end writes/reads, data accuracy, IAM, networking, latency, logging, and ongoing backup capability.

## 5. Creating Cloud SQL PostgreSQL and Protecting Data

### 5.1. Primary A with HA and PITR

The example uses PostgreSQL 16 Enterprise, 2 vCPUs, and in-region HA. **This command creates billable resources**; verify machine type/region/edition validity and quotas:

~~~bash
# LAB ONLY WITH BILLING/BUDGET AND APPROVAL.
gcloud sql instances create "${PRIMARY}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_A}" \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --cpu=2 \
  --memory=7680MB \
  --storage-type=SSD \
  --storage-size=20 \
  --availability-type=REGIONAL \
  --backup-start-time=03:00 \
  --enable-point-in-time-recovery \
  --retained-backups-count=7 \
  --deletion-protection
~~~

Verify after creation:

~~~bash
gcloud sql instances describe "${PRIMARY}" \
  --project="${PROJECT_ID}" \
  --format="yaml(name,region,databaseVersion,settings.availabilityType,settings.backupConfiguration,connectionName)"

gcloud sql operations list \
  --instance="${PRIMARY}" \
  --project="${PROJECT_ID}"
~~~

- `REGIONAL` provides HA across two **zones within one region**, not DR across two regions.
- `--enable-point-in-time-recovery` must be explicitly enabled in many `gcloud` creation flows; never assume it is on by default.
- PITR requires active backup/log history within the window and a valid recovery point.
- `--deletion-protection` guards against accidental instance deletion; it **does not replace backups**.
- Private IP/PSC, Cloud KMS CMEK, firewalls, or org policies may require different flags and design. This sample uses the Cloud SQL Connector and instance connection name rather than detailing a full production network.

### 5.2. Creating the Database and Least-Privilege User

~~~bash
gcloud sql databases create "${DB_NAME}" \
  --instance="${PRIMARY}" \
  --project="${PROJECT_ID}"
~~~

In **Cloud SQL Console → primary → Users**, create user `dr_app` with a strong random password and appropriate database roles. Avoid passing `--password=...` on shared terminals where shell history or process listings can leak it.

In **Cloud SQL Studio** or a DBA-managed authenticated `psql` session, run DDL in the `orders` database:

~~~sql
CREATE TABLE IF NOT EXISTS dr_orders (
  id UUID PRIMARY KEY,
  amount INTEGER NOT NULL CHECK (amount > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- In production, separate DDL and DML roles.
-- Grant only required privileges to the application user.
GRANT SELECT, INSERT, UPDATE ON TABLE dr_orders TO dr_app;
~~~

Database privileges live at the **PostgreSQL** layer, separate from IAM `roles/cloudsql.client` used to connect to Cloud SQL. In a lab, depending on how a user is created, defaults might grant broader roles than needed; review and narrow them before treating anything as a production baseline. Never let Cloud Run run DDL on startup; that prevents a standby from accidentally mutating the primary.

### 5.3. Secret Manager and Service Account

Store the password in Secret Manager via a protected workflow—either the Console or CLI without leaking the secret into logs. In this example, the secret ID is `dr-db-password`. If created via Console, pick replication matching data residency; if via CLI, never commit plaintext into a repository.

~~~bash
gcloud iam service-accounts create dr-runtime \
  --project="${PROJECT_ID}" \
  --display-name="DR lab Cloud Run runtime"

export RUNTIME_SA="dr-runtime@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/cloudsql.client"

gcloud secrets add-iam-policy-binding dr-db-password \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor"
~~~

The binding command requires the secret to exist already. Use a **user-managed runtime SA** rather than granting permissions to the default Compute Engine service account. The deployer identity needs separate deploy permissions plus `actAs` on the runtime SA; avoid Owner or static JSON keys.

## 6. Creating the Read Replica in Region B

A Cloud SQL cross-region read replica is an **asynchronous copy**. It is read-only until promoted. Replicas do not automatically become primary when Region A goes down in the basic model.

~~~bash
# LAB ONLY: creating a cross-region replica incurs continuous charges.
gcloud sql instances create "${REPLICA}" \
  --master-instance-name="${PRIMARY}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_B}" \
  --availability-type=ZONAL
~~~

`ZONAL` on the replica minimizes lab setup compared to HA in B and is not a production DR recommendation. For critical systems, plan for **HA in the standby region**, adequate right-sizing, capacity/quotas, private connectivity, and backup policies on the newly promoted primary.

Verify:

~~~bash
gcloud sql instances describe "${REPLICA}" \
  --project="${PROJECT_ID}" \
  --format="yaml(name,region,state,masterInstanceName,replicaConfiguration,connectionName)"

gcloud sql instances list \
  --project="${PROJECT_ID}"
~~~

To assess replication health, check Cloud SQL → replica → Monitoring for **Replication state**, **Lag Bytes**, and related metrics. Never rely on instance status `RUNNABLE` alone to claim all writes have replayed. Newly created replicas also need time to finish initial database seeding.

### 6.1. Permission and Connection Characteristics

The replica has a **different** connection name from the primary because it is a distinct instance in another region. App B initially **points to primary A with writes disabled**, acting merely as a standby container. After promotion, reconfiguring Cloud Run B and approving routing are explicit DR steps.

If App B connected directly to read replica B before promotion, PostgreSQL would reject `INSERT/UPDATE` statements as read-only, and any write-based readiness check would fail. In this lab, we intentionally avoid targeting replica B before promotion.

## 7. Building a Small Java/Spring Boot App to Observe Data

The demo app exposes these endpoints:

| Endpoint | Role | Guarantee |
|---|---|---|
| `GET /ready` | Checks DB connectivity via `SELECT 1` | Not proof that the whole system has zero data loss |
| `POST /orders` | Inserts an order with an idempotency key | Rejected when `APP_WRITES_ENABLED=false` |
| `GET /orders/{id}` | Reads back an order by UUID | Used to reconcile before/after promotion |
| `GET /whoami` | Displays region label and writer mode | Not an authoritative source of cloud routing |

Create the sample directory tree in the learner's project (not in the knowledge documentation repo):

~~~text
dr-orders/
├── pom.xml
├── Dockerfile
└── src/main/
    ├── java/lab/dr/
    │   └── DrOrdersApplication.java
    └── resources/
        └── application.yml
~~~

### 7.1. Maven pom.xml

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
  <groupId>lab.dr</groupId>
  <artifactId>dr-orders</artifactId>
  <version>0.0.1</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
    </dependency>
    <dependency>
      <groupId>com.google.cloud.sql</groupId>
      <artifactId>postgres-socket-factory</artifactId>
      <version>1.30.0</version>
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

The example uses published Spring Boot 3.5.x and Cloud SQL JDBC Socket Factory versions; in real projects, verify JVM/dependency compatibility, scan for vulnerabilities, and pin security updates.

### 7.2. Spring Boot application.yml

~~~yaml
server:
  port: ${PORT:8080}
spring:
  datasource:
    url: "jdbc:postgresql:///orders?cloudSqlInstance=${DB_INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory"
    username: "${DB_USER:dr_app}"
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 4
      connection-timeout: 5000
      minimum-idle: 0
  sql:
    init:
      mode: never
~~~

Cloud SQL JDBC Socket Factory authenticates the app to Cloud SQL via the service account's ADC and sets up an encrypted tunnel; **it does not replace the PostgreSQL username/password or database privileges** in this example. Never put secrets into code, Docker images, or logs.

Connection budget formula to keep in mind:

~~~text
Application DB connections can reach:
  Cloud_Run_max_instances × maximumPoolSize_per_instance
  + admin connections / background workers / other tools
~~~

Using `--max-instances=5` and pool size 4 gives a design ceiling of **roughly 20 pooled connections if every instance fills its pool**; it does not strictly prevent spikes caused by scaling/revision rollouts or other clients. When Region B becomes the writer, verify DB connection limits on B.

### 7.3. Java Controller and Write Guard

~~~java
package lab.dr;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@SpringBootApplication
public class DrOrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(DrOrdersApplication.class, args);
    }
}

@RestController
class OrdersController {
    private final JdbcTemplate jdbc;

    @Value("${APP_WRITES_ENABLED:false}")
    private boolean writesEnabled;

    @Value("${REGION_LABEL:unknown}")
    private String region;

    OrdersController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    record OrderRequest(String id, int amount) {}

    @GetMapping("/whoami")
    Map<String, Object> whoami() {
        return Map.of("region", region,
                      "writesEnabled", writesEnabled);
    }

    @GetMapping("/ready")
    Map<String, Object> ready() {
        Integer one = jdbc.queryForObject("SELECT 1", Integer.class);
        return Map.of("db", one == 1 ? "reachable" : "unexpected",
                      "region", region);
    }

    @PostMapping("/orders")
    ResponseEntity<Map<String, Object>> create(
            @RequestBody OrderRequest order) {
        if (!writesEnabled) {
            return ResponseEntity.status(503)
                .body(Map.of("error", "standby_writer_disabled"));
        }

        if (order == null || order.id() == null || order.amount() <= 0) {
            return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid_order"));
        }

        final UUID id;
        try {
            id = UUID.fromString(order.id());
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid_uuid"));
        }

        int inserted = jdbc.update(
            "INSERT INTO dr_orders(id, amount) VALUES (?, ?) "
                + "ON CONFLICT (id) DO NOTHING",
            id, order.amount());

        // Replaying the same id does not insert an extra row.
        return ResponseEntity.status(inserted == 1 ? 201 : 200)
            .body(Map.of("id", id.toString(),
                         "created", inserted == 1,
                         "region", region));
    }

    @GetMapping("/orders/{id}")
    ResponseEntity<?> get(@PathVariable String id) {
        final UUID uuid;
        try {
            uuid = UUID.fromString(id);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid_uuid"));
        }

        List<Map<String, Object>> rows = jdbc.queryForList(
            "SELECT id::text AS id, amount, created_at "
                + "FROM dr_orders WHERE id = ?",
            uuid);

        return rows.isEmpty()
            ? ResponseEntity.notFound().build()
            : ResponseEntity.ok(rows.get(0));
    }
}
~~~

**Demo limitations:**

- The `APP_WRITES_ENABLED` check lives only inside the app revision, not a distributed lease or fencing token. In a real incident, ensure every old writer is disabled and cannot resume writing if Region A recovers.
- `ON CONFLICT DO NOTHING` blocks duplicate inserts by ID, whereas production apps must also detect when a client re-sends the same ID with different content. This lesson focuses strictly on recovery.
- `GET /ready` proves only that a basic query succeeded; validating cutover requires running both POST and GET on the same record, checking permissions, and verifying business invariants.
- The demo omits payments, Pub/Sub, caches, and complex schema migrations. Real systems need dedicated runbooks for those dependencies.
- High-traffic workloads need application-level customer authN/authZ and bounded-retention idempotency keys; Cloud Run IAM protects only lab callers here.

### 7.4. Dockerfile and Building the Image Once

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
COPY src ./src
RUN mvn -B -ntp -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/target/dr-orders-0.0.1.jar /app/app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Create the Artifact Registry repository:

~~~bash
gcloud artifacts repositories create "${REPO}" \
  --location="${REGION_A}" \
  --repository-format=docker \
  --project="${PROJECT_ID}"

# Run only inside the lab project's dr-orders directory.
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE}" .
~~~

The image is built once and then deployed using the **exact same image digest** to A and B where Artifact Registry location and permissions allow cross-region pulls. After building, capture the real digest from Artifact Registry or build output; in production, pin `@sha256:...` to eliminate tag-overwrite risk. Tag `v1` is used here solely to keep the lab simple.

## 8. Deploying Least-Privilege Cloud Run A and B

### 8.1. Cloud Run A as Writer

~~~bash
export CONN_A="${PROJECT_ID}:${REGION_A}:${PRIMARY}"

gcloud run deploy "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_A}" \
  --image="${IMAGE}" \
  --service-account="${RUNTIME_SA}" \
  --add-cloudsql-instances="${CONN_A}" \
  --set-env-vars="DB_INSTANCE_CONNECTION_NAME=${CONN_A},DB_USER=dr_app,APP_WRITES_ENABLED=true,REGION_LABEL=${REGION_A}" \
  --set-secrets="DB_PASSWORD=dr-db-password:latest" \
  --max-instances=5 \
  --min-instances=0 \
  --memory=512Mi \
  --no-allow-unauthenticated
~~~

All database connections go through the Cloud SQL Connector using the runtime SA; secrets are injected only at runtime. Callers need `roles/run.invoker` to call endpoints with an ID token.

### 8.2. Cloud Run B in Standby Mode

~~~bash
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_B}" \
  --image="${IMAGE}" \
  --service-account="${RUNTIME_SA}" \
  --add-cloudsql-instances="${CONN_A}" \
  --set-env-vars="DB_INSTANCE_CONNECTION_NAME=${CONN_A},DB_USER=dr_app,APP_WRITES_ENABLED=false,REGION_LABEL=${REGION_B}" \
  --set-secrets="DB_PASSWORD=dr-db-password:latest" \
  --max-instances=5 \
  --min-instances=0 \
  --memory=512Mi \
  --no-allow-unauthenticated
~~~

Initially **B points to primary A**, with its write guard disabled. This lets you compare readiness across both regions while A's primary is healthy. If primary A fails, B also loses DB read/write capability **until the replica is promoted and the connection name is updated**; B is not yet an independent standby database before that point.

To keep warm containers ready in B, raise `min-instances` above 0 and evaluate the cost. The lab uses 0 to avoid idle charges; cold starts can lengthen measured RTO.

### 8.3. Retrieving URLs and Checking Identity

~~~bash
export URL_A="$(gcloud run services describe "${SERVICE}" \
  --project="${PROJECT_ID}" --region="${REGION_A}" \
  --format='value(status.url)')"

export URL_B="$(gcloud run services describe "${SERVICE}" \
  --project="${PROJECT_ID}" --region="${REGION_B}" \
  --format='value(status.url)')"

printf "A=%s\nB=%s\n" "${URL_A}" "${URL_B}"
~~~

The test operator account must hold `roles/run.invoker` on **both** services A and B:

~~~bash
# Lab admin applies this for the approved tester.
gcloud run services add-iam-policy-binding "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_A}" \
  --member="user:APPROVED_OPERATOR_EMAIL" \
  --role="roles/run.invoker"
~~~

Repeat the binding for B within the tester's scope; never switch to `--allow-unauthenticated` just to skip 403 errors.

Smoke test:

~~~bash
export TOKEN="$(gcloud auth print-identity-token)"

curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_A}/ready"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_B}/ready"

curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_A}/whoami"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_B}/whoami"
~~~

Expected: A reports `writesEnabled=true`, B reports `false`, and both read primary A while the DB is healthy. Regenerate tokens when they expire; never paste tokens into shared tickets or logs. If `/ready` fails, check the Cloud SQL connection name, runtime SA, `roles/cloudsql.client`, secret permissions, DB user/password, and network/IP mode.

## 9. Recording Baseline and Synthetic Data Before the Drill

Use a unique UUID per drill and document exact provenance:

~~~bash
export ORDER_ID="11111111-1111-4111-8111-111111111111"

curl -fsS -X POST "${URL_A}/orders" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data "{\"id\":\"${ORDER_ID}\",\"amount\":120}"

curl -fsS "${URL_A}/orders/${ORDER_ID}" \
  -H "Authorization: Bearer ${TOKEN}"
~~~

In a lab shell session, capture timestamps:

~~~bash
date -u +"%Y-%m-%dT%H:%M:%SZ"

gcloud sql instances describe "${PRIMARY}" \
  --project="${PROJECT_ID}" \
  --format="yaml(state,region,connectionName,settings.availabilityType)"

gcloud sql instances describe "${REPLICA}" \
  --project="${PROJECT_ID}" \
  --format="yaml(state,region,masterInstanceName,connectionName)"
~~~

Save the ID, amount, `created_at`, UTC timestamps, image digest, Cloud Run revisions, replication metrics, query times, and dashboard screenshots. Never save `gcloud` stdout alone and assume all data is synced.

### 9.1. Verifying Replica Replay

From an authorized Cloud SQL Studio/psql session on **replica B**, run read-only queries:

~~~sql
SELECT pg_is_in_recovery() AS is_standby;

SELECT
  pg_last_wal_receive_lsn() AS received_lsn,
  pg_last_wal_replay_lsn() AS replayed_lsn,
  pg_last_xact_replay_timestamp() AS last_replayed_commit;
~~~

While still a replica, `pg_is_in_recovery()` normally returns `true`. Interpret LSNs and timestamps alongside **Replication state** and **Lag Bytes**; never infer "completely caught up" from a timestamp alone, especially when a database has been idle. Operators must verify expected writes/markers replayed on B before a planned promotion.

## 10. Drill 1: In-Region Cloud SQL HA Failover

**Objective:** observe App A handle a brief disconnect and recover when Cloud SQL HA fails over to the standby zone in the same region. Do not switch clients to Region B in this drill.

### Gate 1 — Before Failover

- [ ] Primary A is `REGIONAL`, with both primary and standby zones healthy.
- [ ] No long-running operation, backup, or maintenance is blocking the test.
- [ ] Backups/PITR and baseline data are verified.
- [ ] Cloud Run A is healthy; tester records UTC start time.
- [ ] Operation approved and running strictly in the lab project.

HA test command, after approval:

~~~bash
# LAB DRILL: can cause a brief connection drop.
gcloud sql instances failover "${PRIMARY}" \
  --project="${PROJECT_ID}"
~~~

In-region Cloud SQL HA can fail over automatically during a zone outage, and Google Cloud supports manual failover testing via CLI. During the test, app connections may drop; JDBC/Hikari must reconnect, and failed requests need client-side retries/idempotency. **This is not regional DR** and does not promote B.

### Gate 2 — After Failover

- Inspect Cloud SQL operation state, Cloud Run GET/POST results, and 5xx counts.
- Verify A's database connection name **did not need to change** in this HA model.
- Record actual downtime, application errors, and recovery duration.
- Confirm the baseline record is intact, then create a new record with a fresh ID.
- Document retry behavior and confirm the client did not create duplicate orders on timeout.

If the test fails or the instance remains stuck in an operation, **do not spam repeated failover commands**; inspect Cloud SQL logs and Monitoring first.

## 11. Drill 2: Regional DR Cutover to Region B

**Objective:** test a controlled manual failover procedure. We **do not shut down a Google Cloud region**. Instead, we assume Region A can no longer serve clients, deliberately halt writes on A, and switch to replica B.

### Phase A — Lock Down State and Fence A

1. Confirm replica B is healthy with valid recent data.
2. Stop A's test writers/producers. Wait for in-flight requests to finish and stop background writers.
3. Switch Cloud Run A to read-only/no-write mode **while A is still reachable**, and verify POSTs are rejected.
4. Verify marker/LSN replay on B; if lag remains, wait within lab bounds or record the RPO risk.
5. Record `T0` (RTO clock start) and the promotion approver.

Command to disable writes on A (without causing a real regional outage):

~~~bash
gcloud run services update "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_A}" \
  --update-env-vars="APP_WRITES_ENABLED=false"
~~~

Once the new revision is Ready and old traffic has drained, test:

~~~bash
export TOKEN="$(gcloud auth print-identity-token)"

curl -sS -o /dev/null -w "HTTP %{http_code}\n" \
  -X POST "${URL_A}/orders" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"id":"22222222-2222-4222-8222-222222222222","amount":50}'
~~~

Expect `503` from the write guard. If it still returns `201`, **STOP**: A is not fenced; do not promote B. Account for Cloud Run revision/traffic routing and any other producers; an in-app guard is insufficient during an unreachable outage. Real failover needs **stronger fencing runbooks** confirming every write source is blocked to prevent two independent primaries.

### Phase B — Evaluate Lag and Promote B

Check Cloud SQL replication state and lag on B. For a planned drill, wait until the replica **has replayed every write accepted on A**. Pick a final marker and read it directly from B as proof. If it is missing, do not proceed under a zero-data-loss planned promotion.

After DBA and Incident Commander approval, run the **topology-changing operation**:

~~~bash
# LAB DR ONLY; never run while A still accepts writes!
gcloud sql instances promote-replica "${REPLICA}" \
  --project="${PROJECT_ID}"
~~~

Promotion turns B into a **standalone writable instance**. This is a manual DR action, not zonal HA. Cloud SQL Enterprise Plus offers a separate **advanced DR** model with designated DR replicas and `replica failover/switchover`; never confuse that model with classic promotion shown here.

Verify:

~~~bash
gcloud sql instances describe "${REPLICA}" \
  --project="${PROJECT_ID}" \
  --format="yaml(name,state,region,masterInstanceName,connectionName)"
~~~

On B's PostgreSQL, query post-promotion:

~~~sql
SELECT pg_is_in_recovery() AS is_standby;
~~~

Expect `false`. That only confirms database B is out of recovery mode; run write/read smoke tests and verify data integrity as well.

**Important:** after promotion, A and B can act as **two independent writable databases**. If A resumes accepting writes when connectivity returns, data will diverge. Never automatically route clients or background jobs back to A. Keep A fenced, and make explicit decisions on data reconciliation, re-replication, and failback.

### Phase C — Point Cloud Run B to the New Primary

Set B's connection name:

~~~bash
export CONN_B="${PROJECT_ID}:${REGION_B}:${REPLICA}"
~~~

Update both the **Cloud SQL instance attachment** and environment variables; enable writes on B only after confirming B is promoted:

~~~bash
gcloud run services update "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_B}" \
  --set-cloudsql-instances="${CONN_B}" \
  --update-env-vars="DB_INSTANCE_CONNECTION_NAME=${CONN_B},APP_WRITES_ENABLED=true"
~~~

Check status and wait for the revision to become Ready:

~~~bash
gcloud run services describe "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION_B}" \
  --format="yaml(status.url,status.conditions,metadata.name)"
~~~

### Phase D — Smoke Test and Manual Cutover

~~~bash
export TOKEN="$(gcloud auth print-identity-token)"
export DR_ORDER_ID="33333333-3333-4333-8333-333333333333"

curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_B}/ready"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL_B}/whoami"

curl -fsS -X POST "${URL_B}/orders" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data "{\"id\":\"${DR_ORDER_ID}\",\"amount\":230}"

curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${URL_B}/orders/${DR_ORDER_ID}"

curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${URL_B}/orders/${ORDER_ID}"
~~~

Passing conditions:

- B accepted writes only after DBA approved promotion.
- New POST succeeds and GET returns matching ID and amount.
- Pre-DR baseline record exists on B, or any gap is **measured and explicitly documented**.
- App B runs the exact image, identity, secret, and DB instance, with active logs/alerts.
- A stays fenced and no other producers write to A.
- Incident Commander approves switching the **test client** to URL B.

Calling URL B directly here is **client-side manual cutover**. Production switches URLs via planned load balancer/DNS/traffic cutovers accounting for TTL, connection draining, caches, and client retries. Never add `--allow-unauthenticated` to "fix" a 403 during failover.

## 12. Measuring RTO/RPO in the Regional DR Drill

### 12.1. Sample Timestamp Log

| UTC Timestamp (Hypothetical) | Event |
|---|---|
| 08:59:40 | Last marker order confirmed by primary A |
| 08:59:41 | Marker verified on replica B |
| 09:00:00 | T0: drill begins, writes halted on A |
| 09:04:00 | Lag evaluated, promotion approved |
| 09:11:00 | B promoted and instance state verified |
| 09:14:00 | Cloud Run B revision Ready |
| 09:17:00 | POST/GET succeeds via URL B, T-restore |

Measuring RTO from 09:00 to 09:17 yields **measured RTO = 17 minutes** in this example. Seeing the last marker replay does not prove **every** other write replayed unless properly reconciled; in a planned drill, quiesce writes, verify replication state/lag, and validate data before promoting. When zero write loss is verified, **observed RPO = 0 for verified test data**; never extrapolate that into an RPO = 0 promise for sudden regional outages.

~~~text
Actual RTO = first verified healthy business transaction
             - incident/drill start time

Observed RPO = latest committed data accepted by old primary
               that is absent on promoted primary,
               expressed as time window or lost transaction set
~~~

In your report, record both **minutes** and **lost/preserved record counts**. Never blindly equate the replication lag metric with measured RPO: metrics have reporting lag, and non-database state (Pub/Sub, caches, objects) also affects business RPO.

### 12.2. Report Template

~~~yaml
drill_id: DRILL-EXAMPLE-01
environment: staging
scenario: cross_region_manual_promotion
start_time_utc: "2026-11-19T09:00:00Z"
restore_time_utc: "2026-11-19T09:17:00Z"
rto_target_minutes: 45
rto_observed_minutes: 17
rpo_target_minutes: 5
data_validation:
  last_committed_id: "11111111-1111-4111-8111-111111111111"
  present_on_recovery: true
  suspected_missing_records: 0
  confirmation_scope: "test marker only"
write_fencing:
  old_writer_blocked: true
  outstanding_producers_reviewed: true
security_approval: "pending evidence link"
cutover_approval: "pending evidence link"
~~~

Use sample figures only as a formatting guide. Real reports must record verified UTC timestamps and evidence links; never mark a step "pass" if it was not executed.

## 13. Drill 3: PITR Data Recovery After a Faulty Write

Failover and data recovery solve different problems:

- **Failover** handles an unavailable database/region by switching to another primary.
- **PITR** creates a new instance reflecting data as of a timestamp before the bad write; it **does not automatically restore lost data into the live instance**.

Run this drill on an active primary that **already has backups and a valid PITR window**. Use an instance that had PITR enabled before the data was written. Do not assume you can run it immediately on a freshly promoted B.

### Phase A — Create Synthetic Data and Inject Controlled Corruption

1. Create two synthetic orders with distinct IDs via the lab API.
2. Save the JSON of both and their UTC timestamps.
3. In Cloud SQL Studio/psql on the lab database, verify rows and logical state before editing.
4. Pick a recoverable timestamp `T_SAFE` inside the PITR window.
5. Perform a controlled erroneous update **strictly on a lab row**, e.g., changing `amount` from 120 to 999.
6. Never run `DROP DATABASE` or delete an instance just to demonstrate PITR.

~~~sql
-- Lab database only, using the ID created specifically for this drill.
SELECT id, amount, created_at
FROM dr_orders
WHERE id = '11111111-1111-4111-8111-111111111111';

-- Simulated fault exercise; must be authorized by the Data owner:
UPDATE dr_orders
SET amount = 999
WHERE id = '11111111-1111-4111-8111-111111111111';
~~~

If running this after regional promotion, target the **current primary** (which may be B) and **verify that specific primary's PITR window**; never blindly reuse A's timestamps or instance name.

### Phase B — Checking the PITR Window

~~~bash
# Change SOURCE to the primary with valid PITR; in an isolated lab this may be A.
export SOURCE="${PRIMARY}"
export PITR_TARGET="dr-pitr-verify"

gcloud sql instances describe "${SOURCE}" \
  --project="${PROJECT_ID}" \
  --format="yaml(name,settings.backupConfiguration)"

gcloud sql instances get-latest-recovery-time "${SOURCE}" \
  --project="${PROJECT_ID}"
~~~

Record `earliestRecoveryTime` and `latestRecoveryTime` if returned, then pick `T_SAFE` **within that window and before the data modification**. Use UTC RFC3339 timestamps, not unconverted local wall-clock times. If the data was created too recently and PITR lacks a valid recovery point, pause rather than guessing a timestamp.

### Phase C — Cloning to a New Instance

~~~bash
# T_SAFE is a valid UTC timestamp, e.g., 2026-11-19T08:50:00Z.
export T_SAFE="YYYY-MM-DDTHH:MM:SSZ"

# LAB ONLY / after approval; creating a new instance incurs costs.
gcloud sql instances clone "${SOURCE}" "${PITR_TARGET}" \
  --project="${PROJECT_ID}" \
  --point-in-time="${T_SAFE}"
~~~

**Never overwrite production** just to save one instance. PITR clone creates a new instance with its own connection name and IP. With standard backups, `instances clone --point-in-time` is the standard flow. With **Enhanced backups** in Backup and DR vaults, PITR uses `gcloud sql instances point-in-time-restore` and a different data source; check your backup type/edition before choosing commands.

### Phase D — Verifying and Choosing a Remediation Path

Query **`PITR_TARGET`** via authorized Cloud SQL Studio/psql:

~~~sql
SELECT id, amount, created_at
FROM dr_orders
WHERE id = '11111111-1111-4111-8111-111111111111';
~~~

Expect the clone at `T_SAFE` to show the original amount. Seeing the instance `RUNNABLE` alone is not enough. Verify other records, schema migrations, sequences/transactions, and consistency with external events.

In real applications, there are two main paths:

- **Selective extract and repair:** extract the right rows from the PITR clone, verify transactions, and conditionally update the live primary while ensuring valid writes after `T_SAFE` are not overwritten.
- **Full cutover to the PITR clone:** only when authorized to discard all writes from `T_SAFE` onward and after auditing all consumers/dependencies; update connections, routing, and account policies.

This lab stops at **verifying the PITR clone** and does not overwrite the primary automatically. External data outside PostgreSQL (Pub/Sub, Cloud Storage, payment gateways) does not rewind alongside a Cloud SQL PITR command.

## 14. Drill 4: Recovering a Cloud Storage Object

Cloud Storage often holds invoices, reports, and app-generated objects. On buckets with **soft delete** enabled, deleted objects can be restored within the retention duration. Do not confuse soft delete, Object Versioning, and bucket retention policies.

### Phase A — Creating the Bucket and Synthetic Data

~~~bash
export BUCKET="${PROJECT_ID}-dr-object-lab"

# LAB ONLY; bucket names must be globally unique.
gcloud storage buckets create "gs://${BUCKET}" \
  --project="${PROJECT_ID}" \
  --location="${REGION_A}" \
  --uniform-bucket-level-access \
  --soft-delete-duration=7d

printf '%s\n' '{"order":"lab-only","total":120}' \
  | gcloud storage cp - "gs://${BUCKET}/receipts/sample.json"
~~~

Verify the object and its generation before deleting:

~~~bash
gcloud storage ls -L "gs://${BUCKET}/receipts/sample.json"
gcloud storage cat "gs://${BUCKET}/receipts/sample.json"
~~~

### Phase B — Deleting the Test Object and Finding the Soft-Deleted Copy

Only after confirming the exact bucket and path:

~~~bash
# DELETE ONLY THE LAB OBJECT; never use wildcards in production.
gcloud storage rm "gs://${BUCKET}/receipts/sample.json"

gcloud storage ls "gs://${BUCKET}/receipts/sample.json" --soft-deleted
~~~

The listing shows the deleted object's generation. Record the generation number and deletion time.

### Phase C — Controlled Generation Restore

~~~bash
gcloud storage restore \
  "gs://${BUCKET}/receipts/sample.json#GENERATION_NUMBER"

gcloud storage cat "gs://${BUCKET}/receipts/sample.json"
gcloud storage ls -L "gs://${BUCKET}/receipts/sample.json"
~~~

Passing criteria: synthetic JSON content matches, metadata/checksums match, and authorized readers can access the object. If a live object already exists at that path, **do not blindly add `--allow-overwrite`**; protect the current object first and pick a safe verification path.

Soft delete protects only within the retention window. If the entire bucket is deleted, the bucket must be restored first; via CLI/API, restoring a bucket does not automatically restore all objects inside it. For CMEK-encrypted Cloud Storage, readability of backups also depends on key material, key version, and service agent permissions.

## 15. Failback Procedure After Region A Recovers

**Failback is not the reverse of `promote-replica`.** In classic Cloud SQL cross-region replication, once B is promoted, B is an independent primary and old instance A does not automatically become a synced replica of B.

A responsible runbook must:

1. **Keep A fenced** while B is the active writer. Never let clients drift back to A merely because the old endpoint comes back online.
2. Inspect data, transactions, and events/outboxes on B. Identify any divergence between old A and new B.
3. Provision a **new read replica of B in Region A** or an approved data sync mechanism; never repurpose old A with diverged data as a replica by renaming it.
4. Wait for replay to catch up and verify data and metrics.
5. Schedule a **planned switchover/failback** during a maintenance window, halt writes on B, and safely transition back to A.
6. After failback, verify single-writer enforcement, client impact, replica/backup/HA topology, and future runbooks.
7. Delete old instances only after Data owner approval and backup retention checks.

With **Cloud SQL Enterprise Plus advanced DR**, designated DR replicas and replica failover/switchover operations have different semantics that can simplify failback. Never mix commands or runbooks across the two models.

### 15.1. Why Must Split Brain Be Controlled?

If A keeps accepting 100 orders while B accepts 50 different orders after promotion, the two databases have diverged. Pointing DNS back to A will not merge B's orders. Recovery then requires transaction reconciliation, event replay, conflict resolution, and idempotency keys—a business decision, not merely an infrastructure command.

Strong fencing includes: blocking ingress paths to the old writer, revoking write permissions on surviving producers, coordinating connection cutover, and ensuring the old primary cannot resume serving writes without re-synchronization. When Region A becomes unreachable, fencing must already be designed **before an incident**, never relying on a command that only works while A is healthy.

## 16. End-to-End Post-Recovery Testing

| Group | Test | Passing Evidence |
|---|---|---|
| Database | GET pre-failover marker | Matching ID/amount; no data lost beyond approved RPO |
| Database | POST new marker after failover | 201/200 per idempotency rules; read back same ID |
| Writer isolation | POST to old writer A | Rejected; zero active old producers |
| App | Cloud Run B revision and health | Ready; logs and metrics show right region |
| Identity | Runtime SA, secret, DB user | No 403s or privilege escalation |
| Replication | Topology after promotion | B is primary; no dependency on old A |
| Recovery | PITR clone | Data matches target timestamp |
| Cloud Storage | Soft-delete generation restore | Hash/contents match |
| Observability | Logs, dashboards, alerts | Complete timestamps, 5xx/latency visible |
| Business | No double-charges/duplicate events | Reviewed by Data owner if live workload |

Tie every test to UTC timestamps and approvers. "Health 200" is not enough, since an app could read a DB while writing to the wrong instance or duplicating records.

## 17. Logs, Metrics, and Alerts to Collect

### 17.1. Signals to Measure

- Cloud Run: request count, 5xx rate, p95/p99 latency, active revisions, and instance count per region.
- Cloud SQL primary/replica: replication state, lag bytes, CPU, memory, connections, transaction rate, and operations.
- Backup/PITR: backup success, PITR window, restore operation duration.
- Cloud Storage: soft-delete configuration, object generations, restore outcomes.
- IAM: who deployed, promoted, rotated secrets, or altered DB permissions.
- Business: recorded test orders, duplicate IDs, row reconciliation.
- Billing: runtime instance-hours, database HA/replica, network egress, storage, logs, and PITR clone.

### 17.2. Sample Application Logs

~~~text
event=dr_write_guard_enabled region=asia-southeast1
event=replication_validation_started source=dr-pg-primary target=dr-pg-replica
event=promotion_approved change_id=DRILL-EXAMPLE-01
event=promotion_completed primary=dr-pg-replica
event=cloud_run_revision_ready region=asia-southeast2
event=dr_smoke_passed region=asia-southeast2 order_id=...
event=client_cutover_approved region=asia-southeast2
~~~

These lines are **illustrative events to log**, not verbatim logs automatically emitted by Google Cloud. Use correlation IDs/change IDs and avoid logging passwords, tokens, or sensitive data.

### 17.3. When Should Alerts Fire?

| Situation | Alert / Action |
|---|---|
| Rising replica lag or stopped replication | Investigate before DR; assess RPO exposure |
| Cloud SQL primary unavailable | Trigger incident triage; distinguish zonal vs. regional |
| Rising Cloud Run 5xx | Inspect app/DB/logs before shifting traffic |
| DB connections near limit | Lower concurrency; inspect max instances/pool size |
| PITR/backup failure | Block DR plans if required recovery window is lost |
| Replica/clone cost over budget | Halt lab expansion and clean up approved resources |
| Old writer still receives POST after cutover | **High severity: split-brain risk**, isolate and investigate |

## 18. Common Lab Pitfalls

| Symptom | Likely Cause | Safe Resolution |
|---|---|---|
| Cloud Run A returns 403 | Caller lacks `run.invoker` | Grant role on specific service; never open publicly |
| App fails connecting to Cloud SQL | Runtime SA lacks `Cloud SQL Client`, wrong connection name, secret, or network | Check config, IAM, Secret Manager, and logs |
| Replica still read-only after promotion | Operation still running or app still points to old instance | Check instance state, `pg_is_in_recovery()`, connection config |
| High replica lag | I/O/capacity/network bottleneck or long transactions | Reduce write load, wait, or document RPO risk |
| A still writes after switching to B | Missing fencing; traffic still hits A | Halt cutover, isolate write source, check data divergence |
| PITR reports invalid timestamp | Wrong timezone or outside recovery window | Query earliest/latest recovery time; use UTC RFC3339 |
| PITR clone missing expected row | Wrong `T_SAFE` or WAL not yet archived | Inspect audit timeline and backup history |
| Soft-deleted object not listed | Soft delete disabled on bucket or retention expired | Check policy/generation and permissions; never promise recovery |
| Restored GCS object has wrong content | Wrong generation selected or overwritten | Compare hashes/metadata and restore the exact version |
| Cloud SQL failover hangs | Another instance operation active or standby zone unhealthy | Check operations; never spam failover commands |
| Client writes duplicates after timeout | Retries without idempotency | Use client-generated IDs, unique keys, reconciliation |
| Cost keeps rising after lab | Two Cloud SQL instances + PITR clone/backups still exist | Run inventory, delete with approval, check backup retention |

## 19. Security and Drill Boundaries

- **Never use production data:** seed synthetic IDs; never copy PII or secrets.
- **Separate identities:** deployer, runtime, DBA, incident commander, and auditor.
- **Least-privilege IAM:** runtime needs only `Cloud SQL Client` and `Secret Manager Secret Accessor` on the specific secret; instance create/delete/promote rights belong only to authorized operators.
- **Retain audit evidence:** store change IDs, Cloud Audit Logs, Cloud SQL operations, and test logs in a controlled location.
- **CMEK:** when using customer-managed encryption keys, backups and replicas still depend on key material, key versions, location, service agents, and IAM; backups become unreadable if required keys are destroyed.
- **Never cause a real outage:** simulate region-down using client routing and writer guards in staging; never disable shared networks or resources.
- **Do not confuse continuity with confidentiality:** DR restores service availability, whereas ransomware or credential compromise requires security containment, forensics, and clean-room restoration.
- **IAM invoker:** Cloud Run IAM restricts lab testers; production app endpoints still need domain authentication and authorization.
- **Single-writer:** an app toggle is a lab guard; production needs engineered fencing and failback procedures.

## 20. Post-Lab Resource Cleanup

Do not delete resources until:

1. All logs, measured RTO/RPO, screenshots, and required evidence are saved.
2. No clients or testers are still hitting the URLs or DB.
3. Data owner confirms only synthetic data exists and nothing must be kept for re-verification.
4. An authorized approver has reviewed the deletion inventory.
5. Remaining backup retention, CMEK, Secret Manager, and lingering cost items are accounted for.

Read-only inventory check:

~~~bash
gcloud run services list --project="${PROJECT_ID}"
gcloud sql instances list --project="${PROJECT_ID}"
gcloud artifacts repositories list --project="${PROJECT_ID}"
gcloud storage buckets list --project="${PROJECT_ID}"
gcloud secrets list --project="${PROJECT_ID}"
~~~

Destructive commands are **controlled suggestions only**, never run automatically:

~~~bash
# CAUTION: delete lab services in each region only after approval.
# gcloud run services delete dr-orders --region=asia-southeast1 --project=PROJECT_ID
# gcloud run services delete dr-orders --region=asia-southeast2 --project=PROJECT_ID

# CAUTION: PITR clones and promoted replicas are billable DB instances.
# Review deletion protection and retained/final backups before deleting.
# gcloud sql instances delete dr-pitr-verify --project=PROJECT_ID
# gcloud sql instances delete dr-pg-replica --project=PROJECT_ID
# gcloud sql instances delete dr-pg-primary --project=PROJECT_ID
~~~

If `--deletion-protection` is enabled, follow a separate approved step to disable protection before deleting; never bake `--no-deletion-protection` into automated cleanup scripts. Soft-deleted Storage objects, backup retention, Artifact Registry images, secret versions, and logs may remain retained or incur charges after compute is deleted; check Billing over the following days.

## 21. Evaluation Matrix and Submission Rubric

| Criterion | Max Points | Evidence |
|---|---:|---|
| Architecture and SLO/RTO/RPO | 15 | Diagram and requirements table |
| Cloud SQL HA and cross-region topology | 15 | Screenshots/describe outputs/metrics |
| Write fencing, single-writer, and promotion gates | 15 | Runbook and rejected POST on old writer |
| Smoke tests and data reconciliation | 15 | Before/after IDs/amounts, error rates |
| PITR + GCS restore | 15 | Timestamps, clone, and object generation |
| IAM, secrets, audit | 10 | Security checklist, role review |
| Cost/cleanup | 5 | Estimates and post-lab inventory |
| Drill report and reflection | 10 | T0, T-restore, RTO/RPO, improvements |
| **Total** | **100** | |

A submission cannot pass "production readiness" if split-brain risk, missing recovery data, or lack of working backup/PITR evidence remains, regardless of total score.

### Concepts Learners Must Explain

- How in-region HA failover preserves the instance connection name, and how applications handle connection resets.
- Why cross-region replica promotion can lose data and why write quiescing/replay validation are necessary.
- Why shifting Cloud Run traffic before promoting the database fails.
- If Region A recovers after B accepted writes, why traffic must not automatically revert to A.
- How PITR differs from restoring the latest backup and from failover.
- Why soft delete requires verifying object generation and retention duration.
- Why observed RTO/RPO are measured metrics rather than fixed properties of a cloud service.

## 22. Final Checklist

- [ ] Lab project, budget alerts, and quotas verified; production untouched.
- [ ] Runtime SA, Secret Manager, and IAM invoker configured with least privilege.
- [ ] Cloud SQL A HA + PITR/backups enabled and verified.
- [ ] Replica B in right region, healthy, with verified replay evidence.
- [ ] Cloud Run A and B share the exact image with separate configs and standby write guard.
- [ ] At least one marker record verified on both source and standby.
- [ ] In-region HA failover logged with operation status, connection recovery, and 5xx counts.
- [ ] Regional promotion ran only after fencing, replay validation, and approval.
- [ ] Cloud Run B pointed to connection name B after promotion.
- [ ] Post-DR POST/GET succeeded and baseline records reconciled.
- [ ] Old writer A fenced; no primary split brain possible.
- [ ] PITR clone used a valid UTC timestamp and data was verified.
- [ ] Cloud Storage object restored at the exact generation with matching checksum/content.
- [ ] Report documents measured RTO/RPO, timestamps, missing records, and owners.
- [ ] Failback/replica-rebuild plan documented without blindly reusing old A.
- [ ] Logs/metrics and evidence archived; lab data cleaned up with approval.

## Conclusion

This project proves that **failover is not the same as data recovery**. Cloud SQL HA handles zone-level failures within a region; cross-region replicas support DR yet require promotion, lag checks, and fencing to avoid creating two independent writers; PITR recovers from logical data corruption at a point in time via a new instance; and Cloud Storage soft delete restores objects within retention. A drill succeeds only when operators prove **data integrity, working business transactions, measured RTO/RPO, intact security boundaries, and zero lingering old writers able to cause divergence**.

## References

- [Cloud SQL for PostgreSQL — About disaster recovery](https://docs.cloud.google.com/sql/docs/postgres/intro-to-cloud-sql-disaster-recovery)
- [Cloud SQL for PostgreSQL — Promote cross-region replicas](https://docs.cloud.google.com/sql/docs/postgres/replication/cross-region-replicas)
- [Cloud SQL for PostgreSQL — Create read replicas](https://docs.cloud.google.com/sql/docs/postgres/replication/create-replica)
- [Cloud SQL for PostgreSQL — Manage replicas and promotion](https://docs.cloud.google.com/sql/docs/postgres/replication/manage-replicas)
- [Cloud SQL for PostgreSQL — High availability](https://docs.cloud.google.com/sql/docs/postgres/high-availability)
- [Cloud SQL for PostgreSQL — Configure HA and test failover](https://docs.cloud.google.com/sql/docs/postgres/configure-ha)
- [Cloud SQL for PostgreSQL — Configure PITR](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/configure-pitr)
- [Cloud SQL for PostgreSQL — Perform PITR](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/pitr)
- [Cloud SQL for PostgreSQL — Restore overview](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/restore)
- [Cloud SQL for PostgreSQL — Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud Run — Serve traffic from multiple regions](https://docs.cloud.google.com/run/docs/multiple-regions)
- [Cloud Run — Configure Cloud SQL connections](https://docs.cloud.google.com/run/docs/configuring/services/cloud-sql)
- [Cloud Storage — Use soft-deleted objects](https://docs.cloud.google.com/storage/docs/use-soft-deleted-objects)
- [Cloud Storage — Configure soft delete](https://docs.cloud.google.com/storage/docs/use-soft-delete)
- [Cloud Storage — Restore soft-deleted objects](https://docs.cloud.google.com/sdk/gcloud/reference/storage/restore)
- [Cloud Billing — Create budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Google Cloud — Architecture Framework: Reliability](https://docs.cloud.google.com/architecture/framework/reliability)

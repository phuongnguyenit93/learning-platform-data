# Java Microservices System Project on GKE

An initial Spring Boot application may display a product catalog while also accepting orders and persisting data. Once split into independently deployed microservices, new challenges emerge around network communication, database management, identity security, and cross-service error tracking. This hands-on exercise builds **catalog-service** and **orders-service** with Java 21/Spring Boot, pushes container images to Artifact Registry, and runs them on **Google Kubernetes Engine (GKE) Autopilot**. Orders calls catalog over Kubernetes Service DNS, stores orders in **Cloud SQL for PostgreSQL** via a Cloud SQL Auth Proxy sidecar, and authenticates using **Workload Identity Federation for GKE**.

This is a capstone project in the **GCP Hands-On Projects** chapter of the **CLOUD_PROVIDERS_GCP** module: applying projects, IAM, VPC, GKE, databases, container delivery, resource protection, reliability monitoring, and cost management. All illustrative commands are for the **learner's sandbox project**, not operations already executed in the documentation workspace.

## Learning Objectives and Acceptance Criteria

- Design boundaries between two Spring Boot services while avoiding shared database tables.
- Author Java 21 code, multi-stage Dockerfiles, and push images to Artifact Registry.
- Provision GKE Autopilot, a Kubernetes Namespace, Deployments, Services, and health probes.
- Connect to Cloud SQL using Workload Identity + Cloud SQL Auth Proxy without JSON service account keys inside Pods.
- Test the API, rolling updates, scaling, connection failures, and inspect logs/events.
- Identify remaining gaps for production readiness: authorization, secrets, migrations, CI/CD, tracing, backups, and resilience.

| Requirement | Acceptance Evidence |
|---|---|
| Two independent workloads | `catalog` and `orders` Deployments are both Ready |
| Catalog returns products | `GET /api/products/sku-01` returns ID, name, and unit price |
| Internal service call | Orders calls `http://catalog:8080` via ClusterIP Service |
| Data persistence | POST orders returns an ID; GET by ID reads back from Cloud SQL |
| Secure GCP identity | GKE KSA linked to IAM service account; proxy uses no JSON key |
| Operational workflow | Observed rollout, logs, resource usage, and cleanup capability |

## 1. Architecture Diagram and Scope

~~~mermaid
flowchart TB
  USER[Tester via kubectl port-forward] --> ORD[orders-service: Java/Spring Boot]
  ORD -->|Internal HTTP| CAT[catalog-service: Java/Spring Boot]
  ORD -->|TCP localhost:5432| PROXY[Cloud SQL Auth Proxy sidecar]
  PROXY -->|IAM and TLS| SQL[(Cloud SQL PostgreSQL)]
  AR[Artifact Registry] -->|Pull images| ORD
  AR -->|Pull images| CAT
  WIF[Workload Identity Federation for GKE] -->|GCP credentials| PROXY
  ORD --> OBS[Cloud Logging and Monitoring]
  CAT --> OBS
  subgraph GKE["GKE Autopilot · namespace shop"]
    ORD
    CAT
    PROXY
  end
~~~

**Catalog** returns a fixed set of products for the exercise; it does not use a database. **Orders** receives purchase requests, calls catalog to look up unit prices, and persists records to a database owned exclusively by orders. There is no real inventory, payment processing, distributed transaction, or idempotency mechanism, so the sample API is **not suitable for real transactions**. Test access uses `kubectl port-forward` rather than exposing an unauthenticated API to the Internet.

Cloud SQL does not run inside the cluster; it is a separate managed service. The Cloud SQL Auth Proxy runs in the same Pod as orders and listens on `127.0.0.1:5432`, authenticating connections to Cloud SQL via IAM/TLS. The proxy **does not replace PostgreSQL login**: orders still uses a database username/password in this lab.

## 2. Prerequisites and Budget

Run the **Bash commands in Google Cloud Shell** (do not apply this syntax directly in PowerShell). You need a sandbox Google Cloud project with Billing, GKE/Cloud SQL quota, and permissions to enable APIs, create resources, and grant IAM roles. Cloud Shell includes `gcloud`, `kubectl`, Docker, and standard tools; use local JDK/Maven or build via Docker/Cloud Build.

**Cost warning:** GKE Autopilot, Cloud SQL, Artifact Registry, networking, and logs can incur charges. Cloud SQL continues charging even without traffic. Configure a Budget alert, limit lab duration, and **clean up at the end**. Respect organization policies; if your organization requires private networking/no public IP, use private VPC/Cloud NAT instead of disabling guardrails.

~~~bash
export PROJECT_ID="YOUR_PROJECT_ID"
export REGION="asia-southeast1"
export CLUSTER="java-shop-gke"
export SQL_INSTANCE="java-shop-pg"
export REPO="java-shop"
export NAMESPACE="shop"
export GSA_NAME="orders-sql"
export GSA_EMAIL="${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud config set compute/region "$REGION"
gcloud services enable \
  container.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  iam.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com
~~~

The example uses a single region to reduce complexity and does not design cross-region HA/DR. `PROJECT_ID` is the string project ID, not the numeric project number.

## 3. Preparing Two Spring Boot Projects

Create a **learner workspace** (separate from the STEP 4 documentation directory):

~~~text
java-shop/
├── catalog/
│   ├── pom.xml
│   ├── src/main/java/dev/demo/catalog/
│   │   ├── CatalogApplication.java
│   │   └── CatalogController.java
│   ├── src/main/resources/application.yaml
│   └── Dockerfile
├── orders/
│   ├── pom.xml
│   ├── src/main/java/dev/demo/orders/
│   │   ├── OrdersApplication.java
│   │   └── OrdersController.java
│   ├── src/main/resources/application.yaml
│   ├── src/main/resources/schema.sql
│   └── Dockerfile
└── k8s/
    └── stack.yaml
~~~

Use [Spring Initializr](https://start.spring.io/) with Java 21/Maven and a supported stable Spring Boot version; select `Spring Web` and `Actuator` for catalog, and add `JDBC API` and `PostgreSQL Driver` for orders. You can call the Initializr API from Cloud Shell:

~~~bash
mkdir -p java-shop && cd java-shop
curl -fsSL -G https://start.spring.io/starter.tgz \
  --data-urlencode "type=maven-project" \
  --data-urlencode "language=java" \
  --data-urlencode "javaVersion=21" \
  --data-urlencode "groupId=dev.demo" \
  --data-urlencode "artifactId=catalog" \
  --data-urlencode "packageName=dev.demo.catalog" \
  --data-urlencode "dependencies=web,actuator" \
  -o catalog.tgz
mkdir -p catalog && tar -xzf catalog.tgz -C catalog

curl -fsSL -G https://start.spring.io/starter.tgz \
  --data-urlencode "type=maven-project" \
  --data-urlencode "language=java" \
  --data-urlencode "javaVersion=21" \
  --data-urlencode "groupId=dev.demo" \
  --data-urlencode "artifactId=orders" \
  --data-urlencode "packageName=dev.demo.orders" \
  --data-urlencode "dependencies=web,actuator,jdbc,postgresql" \
  -o orders.tgz
mkdir -p orders && tar -xzf orders.tgz -C orders
mkdir -p k8s
~~~

Initializr generates `CatalogApplication.java` and `OrdersApplication.java` with `@SpringBootApplication` and `main`; **do not overwrite** those files. Inspect dependencies in `pom.xml` rather than copying an older POM incompatible with the version chosen by Initializr.

### Request Flow

1. Client sends `POST /api/orders` with `{"productId":"sku-01","quantity":2}`.
2. Orders calls `GET http://catalog:8080/api/products/sku-01` via internal Service DNS.
3. Catalog returns the price; orders validates quantity and writes one row into PostgreSQL.
4. Orders returns the ID; `GET /api/orders/{id}` reads the record back from Cloud SQL.

## 4. Writing catalog-service

Create `catalog/src/main/java/dev/demo/catalog/CatalogController.java`:

~~~java
package dev.demo.catalog;

import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/products")
public class CatalogController {
    public record Product(String id, String name, long priceCents) {}

    private static final Map<String, Product> PRODUCTS = Map.of(
        "sku-01", new Product("sku-01", "Java Handbook", 129900),
        "sku-02", new Product("sku-02", "GKE Field Guide", 249900)
    );

    @GetMapping
    public List<Product> all() {
        return List.copyOf(PRODUCTS.values());
    }

    @GetMapping("/{id}")
    public Product get(@PathVariable String id) {
        Product product = PRODUCTS.get(id);
        if (product == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Unknown SKU");
        }
        return product;
    }
}
~~~

Create `catalog/src/main/resources/application.yaml`:

~~~yaml
server:
  port: 8080
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

**Design choice:** Catalog has no database, so every replica serves identical data. In reality, catalog may own its own database, publish events on price changes, and use caching; orders should never read the catalog database directly for "faster reads" because that breaks data ownership boundaries. The unit price is snapshotted into each order at creation time so historical orders remain accurate if catalog prices change later.

## 5. Writing orders-service and PostgreSQL Schema

Create `orders/src/main/resources/schema.sql`. The lab uses Spring Boot's schema initializer, suitable for a simple table:

~~~sql
CREATE TABLE IF NOT EXISTS orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

In production, **do not let multiple replicas arbitrarily alter schema on startup**. Use Flyway/Liquibase inside a controlled migration job/pipeline, accounting for backward compatibility across app and database versions. This lab uses `CREATE TABLE IF NOT EXISTS` to simplify the initial run.

Create `orders/src/main/resources/application.yaml`:

~~~yaml
server:
  port: 8080
spring:
  datasource:
    url: ${SPRING_DATASOURCE_URL:jdbc:postgresql://127.0.0.1:5432/shop}
    username: ${SPRING_DATASOURCE_USERNAME:shop_app}
    password: ${SPRING_DATASOURCE_PASSWORD:}
    hikari:
      maximum-pool-size: 5
  sql:
    init:
      mode: always
catalog:
  base-url: ${CATALOG_URL:http://catalog:8080}
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

The default JDBC address targets `127.0.0.1:5432`, which can be a local PostgreSQL container or the proxy sidecar in the same Pod. `HikariCP maximum-pool-size=5` limits connections **per orders replica**, not system-wide: scaling to 10 replicas can open up to roughly 50 pooled DB connections before counting other clients. Measure and size limits to match Cloud SQL capacity.

Create `orders/src/main/java/dev/demo/orders/OrdersController.java`:

~~~java
package dev.demo.orders;

import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {
    private final JdbcTemplate db;
    private final RestClient catalog;

    public OrdersController(
            JdbcTemplate db,
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String catalogUrl) {
        this.db = db;
        this.catalog = builder.baseUrl(catalogUrl).build();
    }

    public record NewOrder(String productId, int quantity) {}
    public record Product(String id, String name, long priceCents) {}
    public record OrderView(
            long id, String productId, int quantity, long unitPriceCents) {}

    @PostMapping
    public ResponseEntity<OrderView> create(@RequestBody NewOrder request) {
        if (request == null || request.productId() == null
                || request.productId().isBlank()
                || request.quantity() < 1 || request.quantity() > 10) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid product or quantity");
        }

        Product product;
        try {
            product = catalog.get()
                .uri("/api/products/{id}", request.productId())
                .retrieve().body(Product.class);
        } catch (RestClientResponseException ex) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY, "Catalog returned an error", ex);
        } catch (RuntimeException ex) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY, "Catalog unavailable", ex);
        }
        if (product == null) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY, "Empty catalog response");
        }

        Long id = db.queryForObject(
            "INSERT INTO orders(product_id, quantity, unit_price_cents) "
                + "VALUES (?, ?, ?) RETURNING id",
            Long.class, product.id(), request.quantity(),
            product.priceCents());
        if (id == null) {
            throw new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR, "Insert failed");
        }
        return ResponseEntity.status(HttpStatus.CREATED).body(
            new OrderView(id, product.id(),
                          request.quantity(), product.priceCents()));
    }

    @GetMapping("/{id}")
    public OrderView get(@PathVariable long id) {
        List<OrderView> rows = db.query(
            "SELECT id, product_id, quantity, unit_price_cents "
                + "FROM orders WHERE id = ?",
            (rs, rowNum) -> new OrderView(
                rs.getLong("id"), rs.getString("product_id"),
                rs.getInt("quantity"), rs.getLong("unit_price_cents")),
            id);
        if (rows.isEmpty()) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Unknown order");
        }
        return rows.get(0);
    }
}
~~~

**Practical warning:** the POST endpoint currently lacks authentication, rate limiting, and an **idempotency key**. If a client retries after a lost response, the system may create duplicate orders. A production design requires a unique idempotency key, storing results in the same database transaction, checking business invariants, and bounding timeouts/retries on catalog calls. Never retry POST requests blindly.

### Quick Local Test on Development Machine (Optional)

If Docker is available locally, run PostgreSQL solely for the lab:

~~~bash
docker run --name shop-pg-local -d \
  -e POSTGRES_DB=shop \
  -e POSTGRES_USER=shop_app \
  -e POSTGRES_PASSWORD=local-dev-only \
  -p 127.0.0.1:5432:5432 \
  postgres:15
~~~

In terminal 1, run `cd catalog && ./mvnw spring-boot:run`. Terminal 2:

~~~bash
cd orders
export SERVER_PORT=8081
export CATALOG_URL=http://127.0.0.1:8080
export SPRING_DATASOURCE_PASSWORD=local-dev-only
./mvnw spring-boot:run
~~~

In terminal 3, test `curl http://127.0.0.1:8080/api/products/sku-01` and `curl -X POST http://127.0.0.1:8081/api/orders -H 'Content-Type: application/json' -d '{"productId":"sku-01","quantity":2}'`. The password `local-dev-only` is only for local testing PostgreSQL and **must never be used on Cloud SQL**. If Docker is unavailable locally, skip this step and build images directly with Cloud Build in the next section.

## 6. Containerizing and Building to Artifact Registry

Create a `Dockerfile` with **identical contents** in both `catalog/` and `orders/`:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/*.jar /app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

The multi-stage build uses JDK/Maven during compilation and JRE at runtime. `USER 10001` avoids running as root by default. In CI, **run `mvn test` before build/push**, pin base images by digest, scan for vulnerabilities, generate an SBOM, and sign or verify provenance per policy. `-DskipTests` in this Dockerfile only shortens the demo and is not advice to skip tests.

Create the Artifact Registry repository:

~~~bash
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Java microservices lab"

export CATALOG_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/catalog:v1"
export ORDERS_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/orders:v1"

# Run inside the java-shop/ directory:
gcloud builds submit ./catalog --tag="$CATALOG_IMAGE"
gcloud builds submit ./orders  --tag="$ORDERS_IMAGE"
~~~

Cloud Build needs permission to write images to the repository. In projects where policy does not grant broad permissions to the default build service account, identify the **active build service account** and grant `roles/artifactregistry.writer` **on that specific repository** (or use a dedicated CI SA per guidance) instead of project-wide Owner. Without Cloud Build, Cloud Shell has Docker and can run `gcloud auth configure-docker ${REGION}-docker.pkg.dev` followed by `docker build`/`docker push` using an identity authorized to write to the repo.

Verify the images exist:

~~~bash
gcloud artifacts docker images list \
  "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}" \
  --include-tags
~~~

Tag `v1` keeps the lesson easy to follow; for production deployments, obtain the `sha256:...` digest from Artifact Registry and configure `image: path@sha256:...` so Pods receive the exact verified content. **Never use `latest` as the sole release identifier.**

## 7. Creating Cloud SQL PostgreSQL for orders-service

In the sandbox, create a small **Enterprise edition** Cloud SQL instance to minimize costs, running PostgreSQL 15 in a single zone. This is a learning configuration **without High Availability or DR**. `db-g1-small` is a shared-core tier for small workloads; if your region/project does not support this tier, choose a Cloud SQL-supported tier and re-check costs.

~~~bash
gcloud sql instances create "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --database-version=POSTGRES_15 \
  --edition=ENTERPRISE \
  --tier=db-g1-small \
  --region="$REGION" \
  --storage-size=10GB

gcloud sql databases create shop \
  --instance="$SQL_INSTANCE" \
  --project="$PROJECT_ID"

# Create a dedicated DB principal and set password via non-echoed prompt.
gcloud sql users create shop_app \
  --instance="$SQL_INSTANCE" \
  --project="$PROJECT_ID"
gcloud sql users set-password shop_app \
  --instance="$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --prompt-for-password

export SQL_CONN="$(gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --format='value(connectionName)')"
echo "$SQL_CONN"
~~~

The connection name has the form `PROJECT_ID:REGION:INSTANCE_NAME`; **it is not a public IP**. In the lab setup, Cloud SQL Auth Proxy connects via the instance's public IP over a TLS- and IAM-protected channel; there is no need to open PostgreSQL port 5432 to the Internet or add authorized networks for the proxy. Verify the Cloud SQL instance has a public IP and GKE workloads have proper egress. In production, prefer private IP/Private Service Connect, private networking, and restricted egress; when using private IP, the proxy needs `--private-ip` and Pods must have routing to the instance's VPC.

### Granting Database Schema Ownership to the App User

With PostgreSQL 15, the `public` schema no longer grants default `CREATE` privileges to every user as in older setups. Because the example runs `schema.sql` at startup, **solely in the sandbox**, a DBA needs to sign in to Cloud SQL Studio for database `shop` as the `postgres` admin role and run:

~~~sql
GRANT USAGE, CREATE ON SCHEMA public TO shop_app;
~~~

This grants `shop_app` permission to create tables in the `public` schema for the lab. **Do not grant DDL privileges to runtime services in production**; there, a DBA or migration job owns DDL, while the runtime user only receives the necessary `SELECT`/`INSERT`/`UPDATE`/`DELETE` privileges. If your organization blocks Cloud SQL Studio access, ask a DBA to run the equivalent step over an approved admin connection; never open public authorized networks just for a one-time connection.

## 8. Creating GKE Autopilot and Workload Identity

Create a regional cluster in the project. Use Autopilot's default public networking to minimize setup steps in the sandbox; **do not alter organizational network policies if public networking is prohibited**:

~~~bash
gcloud container clusters create-auto "$CLUSTER" \
  --location="$REGION" \
  --project="$PROJECT_ID"

gcloud container clusters get-credentials "$CLUSTER" \
  --location="$REGION" \
  --project="$PROJECT_ID"

kubectl create namespace "$NAMESPACE"
kubectl create serviceaccount orders-ksa -n "$NAMESPACE"
kubectl get nodes
~~~

Autopilot enables Workload Identity Federation for GKE so Pods can receive IAM identities without mounting JSON keys. In this lab, the orders Pod uses **Kubernetes ServiceAccount (KSA)** `shop/orders-ksa` bound to **IAM service account (GSA)** `orders-sql@...`. Only the GSA receives `Cloud SQL Client`.

~~~bash
gcloud iam service-accounts create "$GSA_NAME" \
  --project="$PROJECT_ID" \
  --display-name="Orders Cloud SQL runtime"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$GSA_EMAIL" \
  --role="roles/cloudsql.client"

gcloud iam service-accounts add-iam-policy-binding "$GSA_EMAIL" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[shop/orders-ksa]"

kubectl annotate serviceaccount orders-ksa \
  --namespace="$NAMESPACE" \
  "iam.gke.io/gcp-service-account=$GSA_EMAIL"
~~~

**Both steps are required**: the IAM policy allowing the KSA to impersonate the GSA, and the annotation linking the KSA to the GSA. The **catalog** service account uses the default KSA and has no Cloud SQL Client permissions. If Cloud SQL lives in a different project, `roles/cloudsql.client` must be granted on the **project containing the instance**, not only on the cluster project.

### Granting Image Pull Permissions to the Right Identity

The GKE node identity must read images from Artifact Registry. If you hit `ImagePullBackOff` with permission denied, check the actual node service account and grant `roles/artifactregistry.reader` on the appropriate repository. Do not grant `roles/artifactregistry.admin` to every Pod. When the repo and cluster share a project, default configurations often have sufficient access; do not assume this if your organization enforces restrictive policies.

## 9. Provisioning a Kubernetes Secret for the DB Password (Lab Only)

To keep the example concise and focused on GKE/Cloud SQL, create a Kubernetes Secret directly in `shop`. **Never put passwords into YAML, Git, documentation, or images.** Re-enter the password set for `shop_app`:

~~~bash
read -r -s -p "Enter shop_app DB password again: " DB_PASSWORD
echo
kubectl -n "$NAMESPACE" create secret generic orders-db \
  --from-literal=username=shop_app \
  --from-literal=password="$DB_PASSWORD"
unset DB_PASSWORD
~~~

This command is for sandbox use only: even though shell history omits the variable value, `kubectl` arguments can briefly appear in process listings, and default Kubernetes Secrets are not a dedicated secret management service. **Production should use GKE's Secret Manager add-on** to mount secrets as files via CSI, or a Secret Manager-to-Kubernetes-Secret sync mechanism if the app must read environment variables; combine with IAM, encryption, and rotation. Restrict who can `get/list secrets` or `exec` into Pods. When rotating a Secret Manager password, design how Pods/apps pick up the new version safely.

## 10. Writing Kubernetes Manifests for Both Services

Create `k8s/stack.yaml`. The placeholders `${CATALOG_IMAGE}`, `${ORDERS_IMAGE}`, and `${SQL_CONN}` will be substituted by `envsubst` before applying. Each Deployment has a Service in the same namespace. Set `requests`/`limits` per Autopilot rules and keep the JVM heap lower than the memory limit.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: catalog
          image: ${CATALOG_IMAGE}
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=65.0"
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 20
---
apiVersion: v1
kind: Service
metadata:
  name: catalog
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: catalog
  ports:
    - name: http
      port: 8080
      targetPort: http
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: shop
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      serviceAccountName: orders-ksa
      initContainers:
        - name: cloud-sql-proxy
          image: gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.28.0
          restartPolicy: Always
          args:
            - "--structured-logs"
            - "--port=5432"
            - "${SQL_CONN}"
          securityContext:
            runAsNonRoot: true
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
      containers:
        - name: orders
          image: ${ORDERS_IMAGE}
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: CATALOG_URL
              value: "http://catalog:8080"
            - name: SPRING_DATASOURCE_URL
              value: "jdbc:postgresql://127.0.0.1:5432/shop"
            - name: SPRING_DATASOURCE_USERNAME
              valueFrom:
                secretKeyRef:
                  name: orders-db
                  key: username
            - name: SPRING_DATASOURCE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-db
                  key: password
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=65.0"
          resources:
            requests:
              cpu: 500m
              memory: 768Mi
            limits:
              cpu: "2"
              memory: 1536Mi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 36
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 20
---
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: orders
  ports:
    - name: http
      port: 8080
      targetPort: http
~~~

In modern GKE/Kubernetes, `initContainers` with `restartPolicy: Always` acts as a **native sidecar container** that remains running for the lifetime of the Pod; Cloud SQL recommends this pattern when not using a service mesh/Istio. This requires a cluster version supporting native sidecars (recent Autopilot versions support it); on older clusters, configure a regular sidecar under `containers` and manage startup ordering. By default the proxy listens only on `127.0.0.1`, so do not point a kubelet `tcpSocket` probe at the Pod IP: that probe will not check the right listener. The Pod starts the sidecar before the app, yet connecting to Cloud SQL can still take time; the app needs appropriate startup/retry settings. Cloud SQL Auth Proxy image `2.28.0` is an illustrative version from documentation; in production, pin the digest, monitor releases/security fixes, and update deliberately.

Note that Spring Boot's default `readinessProbe` checks app liveness/readiness and **does not always reflect Cloud SQL writeability or catalog reachability**. When database-dependent readiness is needed, design health groups carefully to avoid cascading failures. `orders` starts with one replica to reduce race risks during demo table creation; once the schema exists, you can scale out to multiple replicas.

## 11. Applying, Observing Pods, and End-to-End Testing

After creating the Secret, KSA/IAM, and images, from the `java-shop/` root directory:

~~~bash
export CATALOG_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/catalog:v1"
export ORDERS_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/orders:v1"
export SQL_CONN="$(gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" --format='value(connectionName)')"

test -n "$CATALOG_IMAGE" && test -n "$ORDERS_IMAGE" && test -n "$SQL_CONN"
kubectl get secret orders-db -n "$NAMESPACE"

# Substitute only the three placeholders in the manifest; never write passwords to YAML.
envsubst < k8s/stack.yaml | kubectl apply -f -

kubectl rollout status deployment/catalog -n "$NAMESPACE"
kubectl rollout status deployment/orders -n "$NAMESPACE"
kubectl get deployments,pods,services -n "$NAMESPACE" -o wide
~~~

`envsubst` is part of `gettext` and is typically installed in Cloud Shell; if missing, install the tool or use Kustomize/Helm to render an equivalent manifest. **Inspect the rendered output before applying** to confirm no `${CATALOG_IMAGE}`, `${ORDERS_IMAGE}`, or `${SQL_CONN}` remains and that the right project/images are used. Never run `kubectl apply` against a production context during a lab.

### Testing HTTP Without Exposing a Public Load Balancer

In Cloud Shell terminal 1, port-forward to the orders Service:

~~~bash
kubectl -n shop port-forward service/orders 8082:8080
~~~

In terminal 2 (same machine/Cloud Shell session), call:

~~~bash
# Catalog data can be tested via a separate port-forward if needed.
curl -i http://127.0.0.1:8082/actuator/health

curl -i -X POST http://127.0.0.1:8082/api/orders \
  -H "Content-Type: application/json" \
  -d '{"productId":"sku-01","quantity":2}'

# Replace 1 with the actual id from the POST response.
curl -i http://127.0.0.1:8082/api/orders/1
~~~

On success, POST returns `201 Created` and JSON similar to:

~~~json
{
  "id": 1,
  "productId": "sku-01",
  "quantity": 2,
  "unitPriceCents": 129900
}
~~~

`unitPriceCents` represents the **smallest unit** of an illustrative currency in this lesson, avoiding `double` for prices. Do not use this pricing model for real taxes, fees, or monetary transactions; production requires currency codes, `BigDecimal`/decimal types, explicit rounding rules, and invariant checks.

### Verifying Internal Communication

With the port-forward above, the client only reaches orders from the machine running `kubectl`; orders calls catalog via Kubernetes DNS `catalog.shop.svc.cluster.local` (short form `catalog` within the same namespace). You can verify catalog directly with:

~~~bash
kubectl -n shop port-forward service/catalog 8083:8080
# In another terminal:
curl -i http://127.0.0.1:8083/api/products/sku-01
~~~

Port-forward is a debugging/lab tool, not a production ingress mechanism. Production requires Gateway/Ingress, TLS certificates, Cloud Armor where appropriate, authentication/authorization, rate limiting, and exposing only necessary APIs. Keep Service type `ClusterIP` for internal communication.

## 12. Scaling, Rollout, and Basic Resilience

Once the schema has been created, scale orders to two replicas and observe the Pods sharing the database:

~~~bash
kubectl -n shop scale deployment/orders --replicas=2
kubectl -n shop rollout status deployment/orders
kubectl -n shop get pods -l app=orders -o wide
kubectl -n shop get pods -l app=catalog -o wide
~~~

**What to observe:** each orders Pod runs one JVM and one Cloud SQL Auth Proxy sidecar, so total DB connections scale with replicas. Both orders replicas must hold no local session or in-memory order state; durable data lives in Cloud SQL. Kubernetes Services load-balance internal traffic across ready Pods, but do not automatically provide API retries or idempotency.

### Versioned Image Rolling Update

Suppose `sku-03` is added to catalog and built as tag `v2`:

~~~bash
export CATALOG_IMAGE_V2="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/catalog:v2"
gcloud builds submit ./catalog --tag="$CATALOG_IMAGE_V2"
kubectl -n shop set image deployment/catalog "catalog=$CATALOG_IMAGE_V2"
kubectl -n shop rollout status deployment/catalog
kubectl -n shop rollout history deployment/catalog
~~~

If the new version fails, roll back:

~~~bash
kubectl -n shop rollout undo deployment/catalog
kubectl -n shop rollout status deployment/catalog
~~~

**Do not overwrite tag `v1` and expect Kubernetes to always re-pull it.** Each build should use a unique tag (such as commit SHA) or digest. In production, use progressive delivery/canary, versioned schema migrations, automated smoke tests, and approvals rather than editing images manually in production.

### Horizontal Pod Autoscaler (HPA) and Requests

Example scaling catalog based on CPU usage relative to CPU requests:

~~~bash
kubectl -n shop autoscale deployment catalog \
  --cpu-percent=70 --min=2 --max=5
kubectl -n shop get hpa
~~~

CPU-based HPA does not directly measure business demand or guarantee request latency. Without metrics or CPU requests, HPA cannot compute utilization. For orders, unbounded scaling can saturate Cloud SQL: cap max replicas, connection pools, database capacity, and API concurrency. After testing, run `kubectl delete hpa catalog -n shop` if no longer needed.

### NetworkPolicy as an Advanced Step

By default, many clusters permit broad Pod-to-Pod traffic. On GKE Autopilot with GKE Dataplane V2/NetworkPolicy, you can restrict ingress to catalog exclusively from Pods labeled `app=orders` in the namespace:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: catalog-only-from-orders
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: catalog
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: orders
      ports:
        - protocol: TCP
          port: 8080
~~~

Apply this policy in the sandbox after understanding how health probes interact with it and how to debug; it does not set egress restrictions on orders or enforce service-to-service identity. For production, consider namespace default-deny and explicitly allow DNS, health checks, Cloud SQL/Google APIs, and approved endpoints.

## 13. Logs, Metrics, Traces, and SLOs

GKE integrates with Cloud Logging/Monitoring according to cluster configuration. Use `kubectl` to inspect at deploy time:

~~~bash
kubectl get pods -n shop
kubectl logs -n shop deployment/catalog --tail=100
kubectl logs -n shop deployment/orders -c orders --tail=100
kubectl logs -n shop deployment/orders -c cloud-sql-proxy --tail=100
kubectl describe pod POD_NAME -n shop
kubectl top pods -n shop
~~~

Replace `POD_NAME` with an actual Pod; `kubectl top` requires an active metrics pipeline. Even when the proxy runs as a native sidecar `initContainer`, still reference container name `cloud-sql-proxy` to read its logs. Look in proxy logs for IAM errors, instance connection name issues, DNS/egress, and connection errors; in Java logs, check JDBC/Hikari, exceptions, threads, and GC.

### Application Observability

Spring Boot Actuator exposes `/actuator/health`, `/actuator/health/liveness`, and `/actuator/health/readiness`. With the Micrometer Prometheus registry dependency and GKE Managed Service for Prometheus (configured separately), you can collect JVM metrics such as heap, GC pauses, and thread counts alongside HTTP server metrics. Use OpenTelemetry to propagate `traceparent` between orders and catalog; this lab does not configure automatic tracing yet, so **do not claim distributed tracing is active just from Actuator**.

A production dashboard should cover:

| Layer | Suggested Metrics/SLOs |
|---|---|
| HTTP | Request rate, 4xx/5xx, p95/p99 latency per service and route |
| Spring Boot/JVM | Heap used/max, GC pauses, thread count, connection pool usage |
| GKE | Pod ready/restart counts, CPU/memory, OOMKilled, HPA replicas |
| Cloud SQL | CPU/memory/storage, active connections, slow queries, backup/PITR |
| Cloud SQL Proxy | Proxy connection errors, restarts/OOM, IAM/metadata failures |
| Security | IAM binding changes, secret accesses, image vulnerabilities, unexpected network egress |

Example learning SLO: **99.5% of valid `POST /api/orders` requests complete in under 1 second while Cloud SQL and catalog are healthy**, measured over a defined window. Do not confuse internal SLOs with Google Cloud's SLA commitments. When error rates rise, correlate request logs, trace context, Pod status, and Cloud SQL metrics before adding replicas.

### Resilience and Backups

A GKE regional cluster does not automatically make a single-zone Cloud SQL instance HA. For production, plan for Cloud SQL HA, automated backups/PITR, regional DR, backups of GKE manifests/PVCs if stateful, and recovery of secrets/images/IAM/networking. Rehearse restoring the `orders` table and verify row counts/idempotency rather than only checking whether Pods are `Running`.

## 14. CI/CD and Deployment Change Management

Manual `gcloud builds submit` works for a lab, whereas microservices systems need independent builds, tests, and approvals. For every commit/PR:

1. Run unit tests, contract tests, and schema migration compatibility checks.
2. Build images independently and store them in Artifact Registry by digest.
3. Scan dependencies/images for vulnerabilities, produce SBOM/provenance, and enforce image policies as required.
4. Deploy to a dev namespace or dev cluster via Kustomize/Helm/GitOps and run smoke tests.
5. Promote the **exact same image digest** to staging/production with rollout strategies, monitoring gates, and approvals.
6. When code rollback is needed, verify whether database migrations are backward-compatible.

### Sample Cloud Build Pipeline (Extension)

Create `cloudbuild.yaml` in your lab workspace (not required to finish the manual deployment steps):

~~~yaml
substitutions:
  _REGION: asia-southeast1
  _REPO: java-shop
  _TAG: lab-v2
steps:
  - name: maven:3.9-eclipse-temurin-21
    id: test-catalog
    dir: catalog
    entrypoint: mvn
    args: ["-B", "test"]
  - name: maven:3.9-eclipse-temurin-21
    id: test-orders
    dir: orders
    entrypoint: mvn
    args: ["-B", "test"]
  - name: gcr.io/cloud-builders/docker
    id: build-catalog
    args: ["build", "-t", "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/catalog:${_TAG}", "./catalog"]
    waitFor: ["test-catalog"]
  - name: gcr.io/cloud-builders/docker
    id: build-orders
    args: ["build", "-t", "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/orders:${_TAG}", "./orders"]
    waitFor: ["test-orders"]
images:
  - "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/catalog:${_TAG}"
  - "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/orders:${_TAG}"
~~~

~~~bash
gcloud builds submit . --config=cloudbuild.yaml \
  --substitutions=_REGION="$REGION",_REPO="$REPO",_TAG=lab-v2
~~~

In Cloud Build, `$PROJECT_ID` is a built-in substitution while variables starting with `_` are user substitutions. The Cloud Build service account needs permissions to push images; that permission **does not automatically include production GKE admin privileges**. This pipeline only builds and publishes images, **not automated deployment**; to extend it, use Cloud Deploy delivery pipelines/Skaffold or GitOps with approvals separated from commit permissions.

**Note on unit tests:** projects freshly generated by Initializr may include a test that boots the Spring context. If the orders test tries to connect to PostgreSQL because of `schema.sql`, configure a test profile using Testcontainers PostgreSQL or an appropriate embedded DB, decoupling schema init/migration from default context startup. Never disable tests just to turn a pipeline artificially green.

## 15. Troubleshooting Table and Operational Playbook

| Symptom | Common Cause | What to Check |
|---|---|---|
| `ImagePullBackOff` | Wrong image path/tag, not pushed, node SA lacks Artifact Registry Reader | `kubectl describe pod`, repo IAM, digest |
| `CreateContainerConfigError` | Missing `orders-db` Secret or `username/password` keys | `kubectl get secret -n shop` and Deployment env |
| Orders `CrashLoopBackOff` | Spring datasource cannot connect, user lacks schema privileges | Orders logs, Cloud SQL Proxy logs, DB ownership |
| Proxy returns 403 | Wrong Workload Identity binding/annotation or GSA missing `roles/cloudsql.client` | KSA name/namespace, GSA email, IAM policy, Cloud SQL Admin API |
| Proxy `connection refused` / timeout | Wrong Cloud SQL instance name, missing public/private route, Cloud NAT/firewall | Instance connection name, network egress, IP mode |
| PostgreSQL reports `permission denied for schema public` | `shop_app` not granted DDL privileges in lab | DBA connects to `shop` DB and runs `GRANT USAGE, CREATE ON SCHEMA public TO shop_app` |
| Orders returns 502 calling catalog | Catalog Pod not ready, wrong Service selector, or policy blocking | `kubectl get endpointslices`, catalog logs, NetworkPolicy |
| Orders returns 500 after creating order | SQL constraint, schema mismatch, or DB connection error | Orders stack trace, SQL logs, Cloud SQL metrics |
| Pod `OOMKilled` | JVM heap + non-heap + proxy exceeds container limit | `kubectl describe pod`, memory metrics, `JAVA_TOOL_OPTIONS` |
| HPA does not scale | Missing CPU metrics/requests or invalid HPA config | `kubectl describe hpa`, Metrics Server, requests |
| Port-forward fails | Pod not ready, wrong kubeconfig context, local port already in use | `kubectl config current-context`, Pod status, change local port |
| After rollout, API still serves old version | Reused tag and image pull cache | Unique tag per build or image digest |

### Catalog Outage Drill

**Sandbox only:** temporarily stop catalog to observe dependency failure:

~~~bash
kubectl -n shop scale deployment/catalog --replicas=0
kubectl -n shop rollout status deployment/catalog --timeout=60s

# Send POST orders and observe error response/latency in another Cloud Shell terminal.
kubectl -n shop logs deployment/orders -c orders --tail=100

# Restore immediately:
kubectl -n shop scale deployment/catalog --replicas=2
kubectl -n shop rollout status deployment/catalog
~~~

With no catalog endpoints available, orders may return `502` on downstream failure; this exercise shows what happens when a dependency is unavailable. The Java sample does not yet configure explicit connect/read timeouts or a circuit breaker, so failure duration depends on HTTP client defaults. Production requires bounded timeouts, jittered retries only for idempotent operations, bulkheads, and sensible fallbacks. Never test failure via scale-to-zero in production.

### Matrix Testing

| Test case | Input / Condition | Expected Result |
|---|---|---|
| CATALOG-01 | `GET /api/products/sku-01` | 200, includes `priceCents` |
| CATALOG-02 | `GET /api/products/unknown` | 404 |
| ORDERS-01 | Valid product, quantity 2 | 201, accurate ID and unit price |
| ORDERS-02 | Quantity 0 or greater than 10 | 400 |
| ORDERS-03 | `GET /api/orders/{id}` just created | 200, persisted data |
| ORDERS-04 | Non-existent ID | 404 |
| NETWORK-01 | Catalog scaled to 0 | Orders reports dependency error; does not fake success |
| IAM-01 | GSA loses Cloud SQL Client (sandbox, with rollback) | Proxy cannot connect; logs identify IAM failure |
| ROLLOUT-01 | Faulty catalog v2 then undo | v1 becomes ready again |
| RESOURCE-01 | Increase orders replicas within limit | Total DB connections do not exceed Cloud SQL capacity |

In the advanced exercises, add a **duplicate POST test** to observe the duplicate-orders flaw; then have learners add `X-Idempotency-Key` and a unique constraint inside a transaction.

## 16. Changes Required Before Production Use

| Aspect | Lab Implementation | Production Recommendation |
|---|---|---|
| Authentication | Unauthenticated API, port-forward only | OIDC/JWT, authorization, mTLS if needed, API Gateway/Ingress |
| Database | Single-zone Cloud SQL PostgreSQL, app user owns schema | HA, backups/PITR, private networking, least-privilege runtime DB user |
| Secrets | Manually created Kubernetes Secret | Secret Manager add-on/CSI, Workload Identity, rotation, and audit |
| HTTP resilience | Simple `RestClient` call | Explicit timeouts, circuit breaker, bulkhead, contract testing |
| Data correctness | POST can duplicate on retry | Idempotency key, transactions, unique constraints, outbox for events |
| Schema | `schema.sql` on app startup | Flyway/Liquibase in a migration job with DBA approval |
| Runtime | Basic JRE and JVM flags | Memory budgets, GC/heap metrics, non-root/read-only FS, base image digest |
| Scheduling | Basic requests/limits | HPA, PodDisruptionBudget, topology spread, SLO-aware capacity |
| Networking | ClusterIP in same namespace | Namespace isolation, NetworkPolicy, TLS/Gateway, egress control |
| Delivery | Manual build/deploy, `v1`/`v2` tags | CI/CD with immutable digests, SBOM, scanning, signing, promotion |
| Observability | Logs and Actuator health | Structured logs, OpenTelemetry traces, Micrometer, alerts, error budgets |
| DR | No cross-region DR | Restore drills, backup plan, RTO/RPO, config/secret recovery |

Do not "microservice-ize" everything on day one. For small applications, a modular monolith reduces operational overhead. Splitting services pays off only with clear domain boundaries, independent owning teams, and matching scaling/release needs. GKE fits when Kubernetes orchestration is needed; if the workload is mostly simple stateless HTTP services, evaluate Cloud Run and its corresponding operational costs as well.

## 17. Resource Cleanup and Cost Control

**Execute after finishing the exercise and confirming no data needs to be kept.** The delete commands below are **destructive**; double-check `gcloud config get-value project` and resource names, and never run them in a shared project without approval.

~~~bash
gcloud config get-value project
kubectl config current-context

# Clean up namespace and workloads inside the sandbox cluster.
kubectl delete namespace shop --ignore-not-found

# Check cluster and Cloud SQL names before confirming deletion.
gcloud container clusters list --project="$PROJECT_ID"
gcloud sql instances list --project="$PROJECT_ID"

gcloud container clusters delete "$CLUSTER" \
  --location="$REGION" --project="$PROJECT_ID"
gcloud sql instances delete "$SQL_INSTANCE" --project="$PROJECT_ID"

# Delete the repository only if it belongs exclusively to this lab.
gcloud artifacts repositories delete "$REPO" \
  --location="$REGION" --project="$PROJECT_ID"
~~~

Before deleting the IAM service account, clean up the bindings created:

~~~bash
gcloud iam service-accounts remove-iam-policy-binding "$GSA_EMAIL" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[shop/orders-ksa]"

gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$GSA_EMAIL" \
  --role="roles/cloudsql.client"

gcloud iam service-accounts delete "$GSA_EMAIL" --project="$PROJECT_ID"
~~~

If the service account was already deleted or the IAM binding does not exist, binding removal may report not found; verify and continue rather than **granting extra permissions to "fix cleanup errors"**. For local Docker, remove `shop-pg-local` if created: `docker rm -f shop-pg-local`. Check Cloud Build staging buckets/source archives, retained Cloud SQL backups, log retention, and lingering Budget alerts; only delete other buckets/artifacts once confirmed not to be shared resources.

## 18. Advanced Exercises and Grading Rubric

1. **Idempotent API:** add `X-Idempotency-Key`, persist it in the same database transaction, and return the same order when retried with the same payload. Test 20 concurrent POSTs with the same key and verify they do not create 20 orders.
2. **Service-to-service tracing:** use OpenTelemetry Java instrumentation to propagate trace context from orders to catalog; display a trace spanning at least two services.
3. **Asynchronous messaging:** add a `notification-worker` consuming Pub/Sub messages after order creation, using a transactional outbox or reliable publish pattern and an idempotent consumer.
4. **Secret management:** migrate the password from a manual Kubernetes Secret to the Secret Manager add-on/CSI, scope permissions to the exact secret, and rehearse rotation.
5. **CI/CD:** build a pipeline to test, build/push immutable images, deploy to dev, verify metrics, and promote via Cloud Deploy or GitOps.
6. **SLO/DR:** create dashboards and alerts for 5xx errors and DB failures; rehearse restoring Cloud SQL in the sandbox and measure RPO/RTO.

| Criterion Group | Max Points | Evaluation Method |
|---|---:|---|
| Architecture / Java code | 20 | Clean service boundaries, clear API, runnable code |
| Containers / build | 15 | Dockerfiles, versioned/digest images, tests before build |
| Kubernetes | 20 | Deployments/Services/health/resource limits, rollout and scaling |
| Cloud SQL / IAM | 20 | Auth Proxy and Workload Identity, no JSON service account keys |
| Testing / observability | 15 | API tests, logs, dependency failure, and metrics explained |
| Security / cost / cleanup | 10 | Least privilege, no exposed secrets, clean teardown in right project |
| **Total** | **100** | Require command evidence and sanitized screenshots/dashboards |

### Submission Package

Submit the architecture diagram, Java source code, Dockerfiles, **secret-free** manifests, build IDs and image digests, `kubectl get`/rollout outputs, sample API responses, test matrix, supporting logs/metrics, and cost estimate. Never include service account keys, tokens, passwords, sensitive connection strings, or customer data in reports.

## 19. Final Checklist

- [ ] Correct sandbox project, region, Billing/quotas confirmed.
- [ ] Both Spring Boot services have compatible dependencies and Java version.
- [ ] Catalog and orders run on two Deployments with ClusterIP Services matching selectors.
- [ ] Orders calls catalog only through its service API, never accessing catalog's data store.
- [ ] PostgreSQL schema exists with proper user and DB permissions, avoiding an admin user at runtime.
- [ ] Workload Identity binding and KSA annotation match namespace/service account.
- [ ] Cloud SQL Auth Proxy connects via IAM/TLS without mounting JSON credentials.
- [ ] Secrets are not committed to Git/YAML/images and a plan exists for Secret Manager.
- [ ] Requests/limits and startup/readiness/liveness probes are reasonable and tested.
- [ ] POST/GET orders work; invalid input tests and catalog outage drill executed.
- [ ] Image tags/digests are traceable; rollout/rollback tested.
- [ ] Logs/metrics distinguish Java, Kubernetes, IAM, and Cloud SQL errors.
- [ ] Plan exists for data protection, migrations, backups, and recovery before production.
- [ ] Costs reviewed and all unused lab resources deleted.

## 20. Conclusion

This two-microservice Java project on GKE demonstrates that running apps on Kubernetes is only one part of cloud architecture. Success depends equally on **data ownership boundaries, network service discovery, workload identity, Cloud SQL permissions, image management, health checks, and operational testing**. After completing this lab, learners have the foundation to expand into asynchronous messaging, API gateways, CI/CD with Cloud Deploy, Secret Manager, distributed tracing, and resilience engineering while maintaining security, reliability, and cost control.

## References

- [Create an Autopilot cluster — GKE](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/creating-an-autopilot-cluster)
- [GKE Autopilot overview](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview)
- [Authenticate to Google Cloud APIs from GKE workloads — Workload Identity](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)
- [Connect from Google Kubernetes Engine — Cloud SQL for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres/connect-kubernetes-engine)
- [Connect using the Cloud SQL Auth Proxy](https://docs.cloud.google.com/sql/docs/postgres/connect-auth-proxy)
- [Create Cloud SQL PostgreSQL instances](https://docs.cloud.google.com/sql/docs/postgres/create-instance)
- [Create and manage Cloud SQL database users](https://docs.cloud.google.com/sql/docs/postgres/create-manage-users)
- [Build container images with Cloud Build](https://docs.cloud.google.com/build/docs/building/build-containers)
- [Push and pull Docker images with Artifact Registry](https://docs.cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling)
- [Authenticate to Artifact Registry](https://docs.cloud.google.com/artifact-registry/docs/docker/authentication)
- [GKE Secrets from Secret Manager](https://docs.cloud.google.com/secret-manager/docs/secret-manager-managed-csi-component)
- [Synchronize secrets to Kubernetes Secrets](https://docs.cloud.google.com/secret-manager/docs/sync-k8-secrets)
- [Configure HTTP probes in GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/ingress#health_checks)
- [Spring Boot Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes Services](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes startup, liveness and readiness probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Kubernetes Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)

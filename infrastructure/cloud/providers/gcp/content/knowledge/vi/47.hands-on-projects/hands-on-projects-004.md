# Dự án hệ thống microservices Java trên GKE

Một ứng dụng Spring Boot ban đầu có thể vừa hiển thị danh mục sản phẩm vừa nhận đơn hàng và lưu dữ liệu. Khi tách thành các microservices triển khai độc lập, ta có thêm bài toán giao tiếp mạng, quản lý database, bảo mật danh tính và theo dõi lỗi xuyên dịch vụ. Bài thực hành này xây dựng **catalog-service** và **orders-service** bằng Java 21/Spring Boot, đưa container images vào Artifact Registry và chạy trên **Google Kubernetes Engine (GKE) Autopilot**. Orders gọi catalog qua Kubernetes Service DNS, lưu đơn hàng trong **Cloud SQL for PostgreSQL** qua Cloud SQL Auth Proxy sidecar và xác thực bằng **Workload Identity Federation for GKE**.

Đây là dự án tổng hợp của chương **Dự án thực hành GCP**, module **CLOUD_PROVIDERS_GCP**: vận dụng project, IAM, VPC, GKE, database, phát hành container, bảo vệ tài nguyên, theo dõi độ tin cậy và quản lý chi phí. Tất cả lệnh minh họa dành cho **project sandbox của người học**, không phải thao tác đã được thực hiện trong workspace sinh tài liệu.

## Mục tiêu học tập và tiêu chí hoàn thành

- Thiết kế ranh giới giữa hai Spring Boot services, tránh chia sẻ trực tiếp bảng database.
- Tạo mã Java 21, Dockerfile nhiều giai đoạn và push images vào Artifact Registry.
- Tạo GKE Autopilot, Kubernetes Namespace, Deployment, Service và health probes.
- Kết nối Cloud SQL bằng Workload Identity + Cloud SQL Auth Proxy, không có service account key JSON trong Pod.
- Kiểm thử API, rolling update, scale, lỗi kết nối và đọc logs/events.
- Xác định những bước còn thiếu để production-ready: authorization, secrets, migrations, CI/CD, tracing, backup và resilience.

| Yêu cầu | Bằng chứng nghiệm thu |
|---|---|
| Hai workloads độc lập | Deployments `catalog`, `orders` đều Ready |
| Catalog trả sản phẩm | `GET /api/products/sku-01` có mã, tên và đơn giá |
| Gọi nội bộ | Orders gọi `http://catalog:8080` qua ClusterIP Service |
| Lưu dữ liệu | POST orders trả ID, GET theo ID đọc lại từ Cloud SQL |
| Định danh GCP an toàn | GKE KSA liên kết IAM service account, proxy không dùng JSON key |
| Có quy trình vận hành | Quan sát rollout, logs, resource usage và khả năng cleanup |

## 1. Sơ đồ kiến trúc và phạm vi

~~~mermaid
flowchart TB
  USER[Người kiểm thử qua kubectl port-forward] --> ORD[orders-service: Java/Spring Boot]
  ORD -->|HTTP nội bộ| CAT[catalog-service: Java/Spring Boot]
  ORD -->|TCP localhost:5432| PROXY[Cloud SQL Auth Proxy sidecar]
  PROXY -->|IAM và TLS| SQL[(Cloud SQL PostgreSQL)]
  AR[Artifact Registry] -->|Pull images| ORD
  AR -->|Pull images| CAT
  WIF[Workload Identity Federation for GKE] -->|GCP credentials| PROXY
  ORD --> OBS[Cloud Logging và Monitoring]
  CAT --> OBS
  subgraph GKE["GKE Autopilot · namespace shop"]
    ORD
    CAT
    PROXY
  end
~~~

**Catalog** trả bộ sản phẩm cố định phục vụ bài tập; không dùng database. **Orders** nhận yêu cầu mua hàng, gọi catalog để lấy đơn giá và lưu bản ghi vào một database do chính orders sở hữu. Không có tồn kho thực, thanh toán, distributed transaction hay cơ chế idempotency, nên API mẫu **không phù hợp xử lý giao dịch thật**. Truy cập thử qua `kubectl port-forward` thay vì công khai API chưa có xác thực ra Internet.

Cloud SQL không chạy trong cluster; nó là dịch vụ managed riêng. Cloud SQL Auth Proxy nằm cùng Pod với orders và lắng nghe `127.0.0.1:5432`, xác thực kết nối tới Cloud SQL qua IAM/TLS. Proxy **không thay thế đăng nhập PostgreSQL**: orders vẫn dùng database user/password trong bản lab này.

## 2. Điều kiện tiên quyết và ngân sách

Chạy các lệnh **Bash trong Google Cloud Shell** (không áp dụng trực tiếp cú pháp này cho PowerShell). Cần Google Cloud project sandbox có Billing, quota GKE/Cloud SQL, quyền enable API, tạo resources và grant IAM. Cloud Shell có `gcloud`, `kubectl`, Docker và các công cụ cơ bản; dùng JDK/Maven cục bộ hoặc build qua Docker/Cloud Build.

**Cảnh báo chi phí:** GKE Autopilot, Cloud SQL, Artifact Registry, network và log có thể tính phí. Cloud SQL vẫn phát sinh chi phí ngay cả khi không có traffic. Thiết lập Budget alert, giới hạn thời gian thực hành và **thực hiện cleanup cuối bài**. Tôn trọng organization policy; nếu tổ chức yêu cầu private networking/không public IP, dùng phương án private VPC/Cloud NAT thay vì tắt guardrail.

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

Ví dụ sử dụng một region để giảm độ phức tạp, chưa thiết kế HA xuyên region/DR. `PROJECT_ID` là ID dự án, không phải numeric project number.

## 3. Chuẩn bị hai Spring Boot projects

Tạo workspace riêng của **người thực hành** (khác thư mục tài liệu STEP 4):

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

Dùng [Spring Initializr](https://start.spring.io/) với Java 21/Maven và Spring Boot phiên bản ổn định được hỗ trợ; catalog chọn `Spring Web`, `Actuator`, orders thêm `JDBC API` và `PostgreSQL Driver`. Có thể gọi Initializr API từ Cloud Shell:

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

Initializr tạo sẵn `CatalogApplication.java` và `OrdersApplication.java` với `@SpringBootApplication` và hàm `main`; **không cần ghi đè** các file đó. Kiểm tra các dependency trong `pom.xml` thay vì sao chép một POM cũ không tương thích với version mà Initializr chọn.

### Đường đi của request

1. Client gửi `POST /api/orders` với `{"productId":"sku-01","quantity":2}`.
2. Orders gọi `GET http://catalog:8080/api/products/sku-01` qua Service DNS nội bộ.
3. Catalog trả giá; orders kiểm tra số lượng, lưu một dòng vào PostgreSQL.
4. Orders trả ID; `GET /api/orders/{id}` đọc lại record từ Cloud SQL.

## 4. Viết catalog-service

Tạo `catalog/src/main/java/dev/demo/catalog/CatalogController.java`:

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

Tạo `catalog/src/main/resources/application.yaml`:

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

**Lựa chọn thiết kế:** Catalog không có database, nên mọi replica có cùng dữ liệu. Trong thực tế, catalog có thể sở hữu database riêng, publish sự kiện khi giá thay đổi và dùng cache; orders không nên truy cập database catalog để “đọc nhanh hơn” vì sẽ phá ranh giới sở hữu dữ liệu. Giá được lưu vào mỗi order tại thời điểm tạo để về sau catalog đổi giá vẫn giữ lịch sử.

## 5. Viết orders-service và schema PostgreSQL

Tạo `orders/src/main/resources/schema.sql`. Bản lab dùng schema initializer của Spring Boot, phù hợp bảng đơn giản:

~~~sql
CREATE TABLE IF NOT EXISTS orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Trong production, **không để nhiều replica cùng tùy ý thay đổi schema lúc startup**. Dùng Flyway/Liquibase trong một migration job/pipeline có kiểm soát, xét backward compatibility giữa các phiên bản ứng dụng và database. Bản lab dùng `CREATE TABLE IF NOT EXISTS` để đơn giản hóa việc chạy lần đầu.

Tạo `orders/src/main/resources/application.yaml`:

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

Địa chỉ JDBC mặc định trỏ vào `127.0.0.1:5432`, có thể là container PostgreSQL local hoặc proxy sidecar trong cùng Pod. `HikariCP maximum-pool-size=5` là giới hạn kết nối **mỗi orders replica**, không phải toàn hệ thống: nếu scale lên 10 replicas thì tối đa có khoảng 50 DB connections từ pool, chưa tính các client khác. Đo và chỉnh giới hạn theo Cloud SQL capacity.

Tạo `orders/src/main/java/dev/demo/orders/OrdersController.java`:

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

**Cảnh báo thực tế:** endpoint POST hiện chưa có auth, rate limit hoặc **idempotency key**. Nếu client retry khi phản hồi bị mất, hệ thống có thể tạo hai đơn. Trong một thiết kế production cần unique idempotency key, lưu kết quả cùng transaction database, kiểm tra business invariants và giới hạn timeout/retry của catalog call. Không retry POST tùy tiện.

### Test nhanh tại máy phát triển (tùy chọn)

Nếu có Docker cục bộ, chạy PostgreSQL chỉ cho lab:

~~~bash
docker run --name shop-pg-local -d \
  -e POSTGRES_DB=shop \
  -e POSTGRES_USER=shop_app \
  -e POSTGRES_PASSWORD=local-dev-only \
  -p 127.0.0.1:5432:5432 \
  postgres:15
~~~

Trong terminal 1 chạy `cd catalog && ./mvnw spring-boot:run`. Terminal 2:

~~~bash
cd orders
export SERVER_PORT=8081
export CATALOG_URL=http://127.0.0.1:8080
export SPRING_DATASOURCE_PASSWORD=local-dev-only
./mvnw spring-boot:run
~~~

Terminal 3 kiểm tra `curl http://127.0.0.1:8080/api/products/sku-01` và `curl -X POST http://127.0.0.1:8081/api/orders -H 'Content-Type: application/json' -d '{"productId":"sku-01","quantity":2}'`. Mật khẩu `local-dev-only` chỉ dành cho PostgreSQL trên máy thử và **không được dùng trên Cloud SQL**. Nếu không có Docker local, bỏ qua bước này; build image trực tiếp bằng Cloud Build ở phần tiếp theo.

## 6. Container hóa và build lên Artifact Registry

Tạo **cùng nội dung** `Dockerfile` trong thư mục `catalog/` và `orders/`:

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

Multi-stage build dùng JDK/Maven ở bước biên dịch và JRE để chạy. `USER 10001` tránh mặc định root. Trong CI, **chạy `mvn test` trước build/push**, pin base image bằng digest, quét vulnerability, tạo SBOM và ký hoặc kiểm tra provenance theo policy. `-DskipTests` ở Dockerfile này chỉ để rút ngắn quá trình demo, không phải lời khuyên bỏ kiểm thử.

Tạo Artifact Registry repository:

~~~bash
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Java microservices lab"

export CATALOG_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/catalog:v1"
export ORDERS_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/orders:v1"

# Chạy tại thư mục java-shop/:
gcloud builds submit ./catalog --tag="$CATALOG_IMAGE"
gcloud builds submit ./orders  --tag="$ORDERS_IMAGE"
~~~

Cloud Build cần quyền ghi image vào repository. Với project có policy không cấp quyền rộng cho default build service account, hãy xác định **build service account đang dùng** và cấp `roles/artifactregistry.writer` **trên đúng repository** (hoặc dùng SA CI riêng theo hướng dẫn) thay vì cấp Owner toàn project. Nếu không dùng Cloud Build, Cloud Shell có Docker và có thể dùng `gcloud auth configure-docker ${REGION}-docker.pkg.dev` rồi `docker build`/`docker push` bằng danh tính được quyền ghi repo.

Kiểm tra image đã tồn tại:

~~~bash
gcloud artifacts docker images list \
  "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}" \
  --include-tags
~~~

Tag `v1` làm bài dễ theo dõi; khi triển khai production hãy lấy digest `sha256:...` từ Artifact Registry và cấu hình `image: path@sha256:...` để Pod nhận đúng nội dung đã được kiểm tra. **Không dùng `latest` làm định danh duy nhất của release.**

## 7. Tạo Cloud SQL PostgreSQL cho orders-service

Trong sandbox, tạo instance Cloud SQL **Enterprise edition** nhỏ để giảm phí, dùng PostgreSQL 15 và một zone. Đây là cấu hình học tập, **không có High Availability hoặc DR**. `db-g1-small` là shared-core tier phục vụ workload nhỏ; nếu region/project không hỗ trợ cấu hình này, chọn tier được Cloud SQL hỗ trợ và kiểm tra lại chi phí.

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

# Tạo principal DB riêng và đặt password qua prompt không echo.
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

Connection name có dạng `PROJECT_ID:REGION:INSTANCE_NAME`; **không phải public IP**. Trong mô hình lab, Cloud SQL Auth Proxy dùng public IP của instance qua kênh bảo vệ bằng TLS và IAM; không cần mở PostgreSQL port 5432 cho Internet hoặc thêm authorized networks cho proxy. Kiểm tra Cloud SQL instance có public IP và GKE workload có egress thích hợp. Ở production, ưu tiên private IP/Private Service Connect, private networking và hạn chế egress; proxy khi dùng private IP cần `--private-ip` và Pod phải có tuyến tới VPC chứa instance.

### Chuyển quyền sở hữu database cho user ứng dụng

Với PostgreSQL 15, schema `public` không còn cho mọi user quyền CREATE mặc định như các thiết lập cũ. Vì ví dụ dùng `schema.sql` lúc startup, một DBA cần **chỉ trong sandbox** đăng nhập Cloud SQL Studio vào database `shop` bằng role quản trị `postgres` và chạy:

~~~sql
GRANT USAGE, CREATE ON SCHEMA public TO shop_app;
~~~

Điều này cho user `shop_app` quyền tạo bảng trong schema `public` phục vụ lab. **Không cấp quyền DDL cho runtime service ở production**; tại đó DBA/migration job sở hữu DDL, còn runtime user chỉ có quyền SELECT/INSERT/UPDATE/DELETE cần thiết. Nếu organization không cho truy cập Cloud SQL Studio, nhờ DBA thực hiện bước tương đương bằng kết nối quản trị đã phê duyệt; không mở public authorized networks chỉ để kết nối một lần.

## 8. Tạo GKE Autopilot và Workload Identity

Tạo cluster khu vực trong project. Chọn cluster có public networking theo mặc định của Autopilot để giảm bước cấu hình trong sandbox; **không đổi network policy tổ chức nếu public networking bị cấm**:

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

Autopilot bật Workload Identity Federation for GKE để Pod có thể nhận danh tính IAM mà không mount JSON key. Ở lab này, orders Pod dùng **Kubernetes ServiceAccount (KSA)** `shop/orders-ksa` liên kết với **IAM service account (GSA)** `orders-sql@...`. Chỉ GSA có quyền Cloud SQL Client.

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

**Cần cả hai bước**: IAM policy cho phép KSA impersonate GSA và annotation liên kết KSA với GSA. Service account của **catalog** dùng KSA mặc định không được cấp Cloud SQL Client. Đối với Cloud SQL nằm ở project khác, quyền `roles/cloudsql.client` phải được cấp ở **project chứa instance**, không phải chỉ ở project cluster.

### Cấp quyền image pull đúng danh tính

GKE node identity cần đọc image trong Artifact Registry. Nếu gặp `ImagePullBackOff` với thông báo permission denied, kiểm tra service account thực tế của node và cấp `roles/artifactregistry.reader` trên repository phù hợp. Không cấp `roles/artifactregistry.admin` cho mọi Pod. Khi repo và cluster cùng project, một số cấu hình có quyền mặc định đủ; không giả định điều đó nếu organization áp dụng policy hạn chế.

## 9. Cấp Kubernetes Secret cho password database (chỉ dành cho lab)

Để giữ ví dụ ngắn và tập trung vào GKE/Cloud SQL, tạo Kubernetes Secret trực tiếp trong `shop`. **Không đưa mật khẩu vào YAML, Git, tài liệu hoặc image**. Nhập lại password đã đặt cho `shop_app`:

~~~bash
read -r -s -p "Enter shop_app DB password again: " DB_PASSWORD
echo
kubectl -n "$NAMESPACE" create secret generic orders-db \
  --from-literal=username=shop_app \
  --from-literal=password="$DB_PASSWORD"
unset DB_PASSWORD
~~~

Lệnh trên chỉ phục vụ sandbox: dù shell history không chứa giá trị biến, argument của `kubectl` có thể lộ thoáng qua trong process listing; Kubernetes Secret mặc định không phải dịch vụ quản lý bí mật chuyên biệt. **Production nên dùng Secret Manager add-on của GKE** để mount secret thành file qua CSI, hoặc cơ chế đồng bộ Secret Manager sang Kubernetes Secret nếu ứng dụng buộc đọc env var; kết hợp IAM, mã hóa và rotation. Hạn chế người có quyền `get/list secrets` hoặc `exec` vào Pod. Khi dùng Secret Manager và password đổi, cần thiết kế cách Pod/app lấy phiên bản mới an toàn.

## 10. Viết Kubernetes manifests cho hai services

Tạo `k8s/stack.yaml`. Các placeholder `${CATALOG_IMAGE}`, `${ORDERS_IMAGE}`, `${SQL_CONN}` sẽ được `envsubst` thay trước khi apply. Mỗi Deployment có Service cùng namespace. Đặt `requests`/ `limits` theo quy định Autopilot và giới hạn heap JVM thấp hơn memory limit.

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

Ở GKE/Kubernetes hiện đại, `initContainers` với `restartPolicy: Always` là **native sidecar container**, tiếp tục chạy trong suốt vòng đời của Pod; Cloud SQL khuyến nghị mô hình này khi không sử dụng service mesh/Istio. Cần phiên bản cluster hỗ trợ native sidecar (Autopilot mới hỗ trợ); với cluster cũ, cần cấu hình sidecar thông thường dưới `containers` và kiểm soát thứ tự startup. Proxy mặc định chỉ lắng nghe ở `127.0.0.1`, nên không đặt `tcpSocket` probe từ kubelet tới Pod IP: probe đó không kiểm tra đúng listener. Pod khởi động sidecar trước ứng dụng nhưng việc kết nối Cloud SQL vẫn có thể chậm; ứng dụng phải có startup/retry phù hợp. Image Cloud SQL Auth Proxy `2.28.0` là ví dụ phiên bản có trong tài liệu; trong production pin digest, giám sát release/security fixes và cập nhật có kiểm soát.

Chú ý `readinessProbe` mặc định của Spring Boot kiểm tra liveness/readiness ứng dụng, **không luôn phản ánh khả năng ghi Cloud SQL hay truy cập catalog**. Khi cần readiness phụ thuộc database, thiết kế health group có kiểm soát để tránh cascading failures. `orders` ban đầu chỉ một replica để giảm rủi ro đồng thời tạo bảng demo; sau khi đã tạo schema có thể scale lên nhiều replicas.

## 11. Apply, quan sát Pods và kiểm thử end-to-end

Sau khi tạo Secret, KSA/IAM và image, từ thư mục gốc `java-shop/`:

~~~bash
export CATALOG_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/catalog:v1"
export ORDERS_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/orders:v1"
export SQL_CONN="$(gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" --format='value(connectionName)')"

test -n "$CATALOG_IMAGE" && test -n "$ORDERS_IMAGE" && test -n "$SQL_CONN"
kubectl get secret orders-db -n "$NAMESPACE"

# Chỉ thay ba placeholder trong file manifest, không ghi password vào YAML.
envsubst < k8s/stack.yaml | kubectl apply -f -

kubectl rollout status deployment/catalog -n "$NAMESPACE"
kubectl rollout status deployment/orders -n "$NAMESPACE"
kubectl get deployments,pods,services -n "$NAMESPACE" -o wide
~~~

Lệnh `envsubst` thuộc `gettext` và thường có trong Cloud Shell; nếu thiếu, cài công cụ hoặc dùng Kustomize/Helm để render một manifest tương đương. **Trước khi apply, xem output render** để chắc không còn `${CATALOG_IMAGE}`, `${ORDERS_IMAGE}`, `${SQL_CONN}` và đang dùng đúng project/image. Không chạy `kubectl apply` vào context production khi đang thực hành.

### Kiểm thử HTTP không mở public Load Balancer

Trong Cloud Shell terminal 1, dùng port-forward đến orders Service:

~~~bash
kubectl -n shop port-forward service/orders 8082:8080
~~~

Trong terminal 2 (cùng máy/Cloud Shell session), gọi:

~~~bash
# Dữ liệu catalog có thể test qua port-forward riêng nếu cần.
curl -i http://127.0.0.1:8082/actuator/health

curl -i -X POST http://127.0.0.1:8082/api/orders \
  -H "Content-Type: application/json" \
  -d '{"productId":"sku-01","quantity":2}'

# Thay 1 bằng id thực tế ở response POST.
curl -i http://127.0.0.1:8082/api/orders/1
~~~

Nếu thành công, POST trả `201 Created` và JSON tương tự:

~~~json
{
  "id": 1,
  "productId": "sku-01",
  "quantity": 2,
  "unitPriceCents": 129900
}
~~~

`unitPriceCents` là **đơn vị nhỏ nhất** của một đồng tiền giả định trong bài, tránh dùng `double` để lưu giá. Không dùng mô hình giá này để tính thuế, phí hoặc giao dịch tiền tệ thật; production cần currency code, decimal/BigDecimal, định nghĩa rounding và kiểm tra bất biến.

### Kiểm tra giao tiếp nội bộ

Với port-forward trên, client chỉ truy cập orders qua máy đang chạy `kubectl`; orders gọi catalog thông qua Kubernetes DNS `catalog.shop.svc.cluster.local` (dạng ngắn `catalog` trong cùng namespace). Bạn có thể xác nhận catalog riêng bằng:

~~~bash
kubectl -n shop port-forward service/catalog 8083:8080
# Trong terminal khác:
curl -i http://127.0.0.1:8083/api/products/sku-01
~~~

Port-forward là công cụ debug/lab, không dùng làm cơ chế ingress production. Production cần Gateway/Ingress, TLS certificate, Cloud Armor khi phù hợp, authentication/authorization, rate limiting và chỉ expose API cần thiết. Hãy giữ Service type `ClusterIP` cho giao tiếp nội bộ.

## 12. Scale, rollout và khả năng phục hồi cơ bản

Sau khi schema đã được tạo thành công, tăng orders lên hai replicas và theo dõi các Pods dùng chung database:

~~~bash
kubectl -n shop scale deployment/orders --replicas=2
kubectl -n shop rollout status deployment/orders
kubectl -n shop get pods -l app=orders -o wide
kubectl -n shop get pods -l app=catalog -o wide
~~~

**Điểm cần quan sát:** ở mỗi orders Pod có một JVM và một Cloud SQL Auth Proxy sidecar, nên tổng số DB connections tăng theo replicas. Hai orders replicas phải không giữ session local hoặc in-memory order state; dữ liệu bền vững nằm ở Cloud SQL. Các Kubernetes Services load-balance traffic nội bộ đến những Pods ready, nhưng không tự cung cấp retry/idempotency cho API.

### Rolling update theo phiên bản image

Giả sử bổ sung `sku-03` vào catalog và build thành tag `v2`:

~~~bash
export CATALOG_IMAGE_V2="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/catalog:v2"
gcloud builds submit ./catalog --tag="$CATALOG_IMAGE_V2"
kubectl -n shop set image deployment/catalog "catalog=$CATALOG_IMAGE_V2"
kubectl -n shop rollout status deployment/catalog
kubectl -n shop rollout history deployment/catalog
~~~

Nếu phiên bản mới lỗi, rollback:

~~~bash
kubectl -n shop rollout undo deployment/catalog
kubectl -n shop rollout status deployment/catalog
~~~

**Không ghi đè tag `v1` rồi kỳ vọng Kubernetes luôn pull lại.** Mỗi lần build nên dùng tag duy nhất (ví dụ commit SHA) hoặc digest. Với production, dùng progressive delivery/canary, versioned schema migration, automated smoke tests và approval thay vì thay image thủ công ngay trên production.

### Horizontal Pod Autoscaler (HPA) và requests

Ví dụ scale catalog theo CPU sử dụng so với CPU request:

~~~bash
kubectl -n shop autoscale deployment catalog \
  --cpu-percent=70 --min=2 --max=5
kubectl -n shop get hpa
~~~

HPA dựa trên CPU không trực tiếp biểu thị business demand hay đảm bảo request latency. Nếu thiếu metrics hoặc CPU request, HPA không tính đúng utilization. Với orders, scale không giới hạn có thể bão hòa Cloud SQL: cần giới hạn max replicas, connection pools, database capacity và API concurrency. Sau thử nghiệm, `kubectl delete hpa catalog -n shop` nếu không còn dùng.

### NetworkPolicy như bước nâng cao

Mặc định nhiều cluster cho phép Pod-to-Pod traffic khá rộng. Trên GKE Autopilot có GKE Dataplane V2/NetworkPolicy, có thể giới hạn ingress của catalog chỉ từ Pods mang label `app=orders` trong namespace:

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

Áp dụng policy này ở sandbox sau khi hiểu effect của health probes và cách debug; nó không tự thiết lập egress restrictions cho orders hoặc quản lý service-to-service identity. Đối với production, xem xét default-deny ở namespace và cho phép DNS, health checks, Cloud SQL/Google APIs và các endpoint được phê duyệt.

## 13. Logs, metrics, traces và SLO

GKE có tích hợp Cloud Logging/Monitoring theo cluster configuration. Dùng `kubectl` để điều tra tại thời điểm deploy:

~~~bash
kubectl get pods -n shop
kubectl logs -n shop deployment/catalog --tail=100
kubectl logs -n shop deployment/orders -c orders --tail=100
kubectl logs -n shop deployment/orders -c cloud-sql-proxy --tail=100
kubectl describe pod POD_NAME -n shop
kubectl top pods -n shop
~~~

Thay `POD_NAME` bằng Pod thực tế; `kubectl top` cần metrics pipeline đang hoạt động. Nếu proxy chạy dạng native sidecar initContainer, vẫn tham chiếu đúng tên container `cloud-sql-proxy` để xem log. Tìm trong proxy log các lỗi IAM, instance connection name, DNS/egress và kết nối; với Java logs, kiểm tra JDBC/Hikari, exception, thread và GC.

### Observability từ ứng dụng

Spring Boot Actuator cung cấp `/actuator/health`, `/actuator/health/liveness`, `/actuator/health/readiness`. Với dependency Micrometer Prometheus registry và GKE Managed Service for Prometheus (cấu hình riêng), có thể thu thập JVM metrics như heap, GC pauses, số thread cùng HTTP server metrics. Dùng OpenTelemetry để truyền `traceparent` giữa orders và catalog; trong bản lab chưa triển khai tracing tự động, nên **không tuyên bố đã có distributed tracing chỉ nhờ Actuator**.

Dashboard production nên có:

| Tầng | Metrics/SLO gợi ý |
|---|---|
| HTTP | Request rate, 4xx/5xx, p95/p99 latency theo service và route |
| Spring Boot/JVM | Heap used/max, GC pauses, thread count, connection pool usage |
| GKE | Pod ready/restart, CPU/memory, OOMKilled, HPA replicas |
| Cloud SQL | CPU/memory/storage, active connections, slow queries, backup/PITR |
| Cloud SQL Proxy | Proxy connection errors, restart/OOM, IAM/metadata failures |
| Bảo mật | Thay IAM bindings, secret access, image vulnerabilities, unexpected network egress |

Ví dụ SLO học tập: **99,5% `POST /api/orders` hợp lệ hoàn thành trong dưới 1 giây khi Cloud SQL và catalog hoạt động**, đo qua một cửa sổ đã định. Không lẫn SLO nội bộ với SLA cam kết của Google Cloud. Khi lỗi tăng, đối chiếu request logs, trace context, Pod status và Cloud SQL metrics trước khi tăng replica.

### Khả năng phục hồi và backup

GKE regional cluster không tự biến Cloud SQL một zone thành HA. Với production, cân nhắc Cloud SQL HA, automated backups/PITR, DR theo region, backup GKE manifests/PVC nếu có dữ liệu, và khôi phục cả secrets/images/IAM/network. Diễn tập restore bảng orders và kiểm tra số lượng/idempotency của đơn hàng, không chỉ kiểm tra Pod trạng thái Running.

## 14. CI/CD và quản lý thay đổi triển khai

Quy trình manual `gcloud builds submit` phù hợp lab, nhưng hệ thống microservices cần build độc lập, kiểm thử và phê duyệt. Với mỗi commit/PR:

1. Chạy unit tests, contract tests và kiểm tra schema migration tương thích.
2. Build images độc lập và lưu ở Artifact Registry bằng digest.
3. Quét lỗ hổng dependency/image, tạo SBOM/provenance và áp dụng image policy theo yêu cầu.
4. Deploy lên dev namespace hoặc cluster dev bằng Kustomize/Helm/GitOps, thực hiện smoke tests.
5. Promote **cùng image digest** đến staging/production; dùng rollout strategy, monitoring gate và quyền phê duyệt.
6. Khi cần rollback code, kiểm tra database migration có backward compatible hay không.

### Cloud Build pipeline mẫu (phần mở rộng)

Tạo một `cloudbuild.yaml` ở workspace thực hành (không cần để hoàn thành bước triển khai manual):

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

Ở Cloud Build, `$PROJECT_ID` là built-in substitution, còn các biến bắt đầu bằng `_` là user substitutions. Cần quyền cho Cloud Build service account để push image; quyền đó **không tự bao gồm quyền quản trị GKE production**. Pipeline chỉ build và publish images, **chưa tự deploy**; để mở rộng có thể dùng Cloud Deploy delivery pipeline/Skaffold hoặc GitOps, với approval tách khỏi quyền commit code.

**Lưu ý về unit tests:** các project vừa tạo từ Initializr có thể có test khởi động Spring context. Nếu orders test cố kết nối PostgreSQL vì `schema.sql`, cấu hình test profile dùng Testcontainers PostgreSQL hoặc embedded DB phù hợp, tách schema init/migration khỏi context startup. Không tắt test để làm xanh pipeline giả tạo.

## 15. Bảng xử lý lỗi và playbook thực hành

| Hiện tượng | Nguyên nhân thường gặp | Điều cần kiểm tra |
|---|---|---|
| `ImagePullBackOff` | Sai image path/tag, chưa push, node SA thiếu Artifact Registry Reader | `kubectl describe pod`, repo IAM, digest |
| `CreateContainerConfigError` | Thiếu Secret `orders-db` hoặc key `username/password` | `kubectl get secret -n shop` và Deployment env |
| Orders `CrashLoopBackOff` | Spring datasource không kết nối, user thiếu quyền schema | Orders logs, Cloud SQL Proxy logs và DB ownership |
| Proxy trả 403 | Workload Identity binding/annotation sai hoặc GSA thiếu `roles/cloudsql.client` | KSA name/namespace, GSA email, IAM policy, Cloud SQL Admin API |
| Proxy `connection refused` / timeout | Cloud SQL instance name sai, không có public/private route, Cloud NAT/firewall | Instance connection name, network egress và IP mode |
| PostgreSQL báo `permission denied for schema public` | User `shop_app` chưa được cấp quyền DDL trong lab | DBA kết nối database `shop` và `GRANT USAGE, CREATE ON SCHEMA public TO shop_app` |
| Orders trả 502 khi gọi catalog | Catalog Pod chưa ready, Service selector sai hoặc policy chặn | `kubectl get endpointslices`, catalog logs, NetworkPolicy |
| Orders trả 500 sau khi tạo order | SQL constraint, schema hoặc kết nối database lỗi | Orders stack trace, SQL logs, Cloud SQL metrics |
| Pod bị `OOMKilled` | Tổng JVM heap + non-heap + proxy vượt container limit | `kubectl describe pod`, memory metrics, `JAVA_TOOL_OPTIONS` |
| HPA không scale | CPU metrics/request hoặc HPA configuration không hợp lệ | `kubectl describe hpa`, Metrics Server, requests |
| Port-forward thất bại | Pod chưa ready, kubeconfig sai context, port local bị chiếm | `kubectl config current-context`, Pod status, đổi local port |
| Sau rollout, API vẫn dùng phiên bản cũ | Reuse tag và image pull cache | Tag riêng cho mỗi build hoặc image digest |

### Một bài diễn tập sự cố catalog

**Chỉ trên sandbox:** tạm ngừng catalog để quan sát lỗi dependency:

~~~bash
kubectl -n shop scale deployment/catalog --replicas=0
kubectl -n shop rollout status deployment/catalog --timeout=60s

# Gửi POST orders và quan sát phản hồi lỗi/độ trễ ở Cloud Shell terminal khác.
kubectl -n shop logs deployment/orders -c orders --tail=100

# Khôi phục ngay:
kubectl -n shop scale deployment/catalog --replicas=2
kubectl -n shop rollout status deployment/catalog
~~~

Khi không có catalog endpoints, orders có thể trả `502` do downstream failure; bài tập cho thấy điều gì xảy ra khi một service không sẵn sàng. Mẫu Java chưa thiết lập connect/read timeout và circuit breaker rõ ràng, nên thời gian lỗi có thể phụ thuộc default của HTTP client. Bản production cần bounded timeouts, retry có jitter chỉ cho thao tác idempotent, bulkheads và fallback phù hợp. Không dùng scale-to-zero để thử lỗi trên production.

### Kiểm thử theo ma trận

| Test case | Input/điều kiện | Kết quả mong muốn |
|---|---|---|
| CATALOG-01 | `GET /api/products/sku-01` | 200, có `priceCents` |
| CATALOG-02 | `GET /api/products/unknown` | 404 |
| ORDERS-01 | Product hợp lệ, quantity 2 | 201, ID và đơn giá chính xác |
| ORDERS-02 | Quantity 0 hoặc lớn hơn 10 | 400 |
| ORDERS-03 | `GET /api/orders/{id}` vừa tạo | 200, dữ liệu lưu bền |
| ORDERS-04 | ID không tồn tại | 404 |
| NETWORK-01 | Catalog scale về 0 | Orders báo dependency error; không giả tạo thành công |
| IAM-01 | GSA mất Cloud SQL Client (sandbox, có rollback) | Proxy không thể kết nối; logs nhận diện IAM |
| ROLLOUT-01 | Catalog v2 lỗi rồi undo | v1 sẵn sàng trở lại |
| RESOURCE-01 | Tăng replicas orders theo giới hạn | Kiểm tra tổng DB connections không vượt Cloud SQL capacity |

Trong phần thực hành nâng cao, thêm **test hai POST giống nhau** để quan sát nhược điểm duplicate orders; sau đó yêu cầu người học thêm `X-Idempotency-Key` và unique constraint trong transaction.

## 16. Những điều cần thay đổi trước khi dùng cho production

| Khía cạnh | Bản thực hành | Khuyến nghị production |
|---|---|---|
| Authentication | API không có auth, chỉ port-forward | OIDC/JWT, authorization, mTLS khi cần, API Gateway/Ingress |
| Database | Cloud SQL PostgreSQL đơn zone, user sở hữu schema | HA, backups/PITR, private networking, least-privilege runtime DB user |
| Secret | Kubernetes Secret tạo thủ công | Secret Manager add-on/CSI, Workload Identity, rotation và audit |
| HTTP resilience | RestClient call đơn giản | Explicit timeout, circuit breaker, bulkhead, contract testing |
| Data correctness | POST có thể trùng khi retry | Idempotency key, transaction, unique constraints, outbox cho events |
| Schema | `schema.sql` khi app startup | Flyway/Liquibase trong migration job với DBA approval |
| Runtime | JRE và JVM flags cơ bản | Memory budgets, GC/heap metrics, non-root/readonly FS, base image digest |
| Scheduling | Requests/limits cơ bản | HPA, PodDisruptionBudget, topology spread, SLO-aware capacity |
| Networking | ClusterIP trong cùng namespace | Namespace isolation, NetworkPolicy, TLS/Gateway, egress control |
| Delivery | Manual build/deploy, tags v1/v2 | CI/CD với immutable digests, SBOM, scanning, signing, promotion |
| Observability | Logs và Actuator health | Structured logs, OpenTelemetry traces, Micrometer, alerts và error budgets |
| DR | Không có DR xuyên region | Restore drill, backup plan, RTO/RPO, config/secret recovery |

Không nên “microservices hóa” mọi chức năng ngay từ đầu. Với ứng dụng nhỏ, modular monolith có thể giảm overhead vận hành. Tách dịch vụ chỉ có lợi khi có ranh giới nghiệp vụ rõ, nhóm sở hữu độc lập và nhu cầu scale/release phù hợp. GKE phù hợp khi cần điều phối Kubernetes; nếu chủ yếu là HTTP service stateless đơn giản, hãy đánh giá cả Cloud Run và chi phí vận hành tương ứng.

## 17. Dọn tài nguyên và kiểm soát chi phí

**Thực hiện sau khi hoàn thành bài và xác minh không có dữ liệu cần giữ.** Các lệnh delete bên dưới là thao tác **phá hủy**; kiểm tra lại `gcloud config get-value project` và tên tài nguyên, không chạy trong project dùng chung nếu chưa có phê duyệt.

~~~bash
gcloud config get-value project
kubectl config current-context

# Dọn namespace và workloads trong cluster sandbox.
kubectl delete namespace shop --ignore-not-found

# Kiểm tra tên cluster và Cloud SQL trước khi xác nhận xóa.
gcloud container clusters list --project="$PROJECT_ID"
gcloud sql instances list --project="$PROJECT_ID"

gcloud container clusters delete "$CLUSTER" \
  --location="$REGION" --project="$PROJECT_ID"
gcloud sql instances delete "$SQL_INSTANCE" --project="$PROJECT_ID"

# Xóa repository chỉ khi nó thuộc riêng bài lab này.
gcloud artifacts repositories delete "$REPO" \
  --location="$REGION" --project="$PROJECT_ID"
~~~

Trước khi xóa IAM service account, dọn binding đã tạo:

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

Nếu service account đã bị xóa hoặc IAM binding không tồn tại, lệnh dọn binding có thể báo không tìm thấy; xác minh rồi tiếp tục, **không cấp thêm quyền để “sửa lỗi cleanup”**. Với local Docker, xóa `shop-pg-local` nếu bạn đã tạo: `docker rm -f shop-pg-local`. Kiểm tra Cloud Build staging buckets/source archives, Cloud SQL retained backups, log retention và Budget alert còn tồn tại; chỉ xóa bucket/artifact khác sau khi xác định không phải tài nguyên dùng chung.

## 18. Bài tập nâng cao và thang đánh giá

1. **Idempotent API:** thêm `X-Idempotency-Key`, lưu cùng transaction database và trả lại cùng order khi retry cùng payload. Test 20 POST concurrent cùng key không sinh 20 orders.
2. **Service-to-service tracing:** dùng OpenTelemetry Java instrumentation, truyền trace context từ orders sang catalog; hiển thị một trace có ít nhất hai services.
3. **Bất đồng bộ:** thêm `notification-worker` nhận message Pub/Sub sau khi tạo order, dùng transactional outbox hoặc cơ chế publish đáng tin cậy và consumer idempotent.
4. **Quản lý secrets:** chuyển password từ Kubernetes Secret thủ công sang Secret Manager add-on/CSI, phân quyền trên đúng secret, diễn tập rotation.
5. **CI/CD:** pipeline test, build/push immutable images, deploy dev, kiểm tra metrics và promote qua Cloud Deploy hoặc GitOps.
6. **SLO/DR:** lập dashboard, cảnh báo 5xx và DB failures; diễn tập restore Cloud SQL trong sandbox và đo RPO/RTO.

| Nhóm tiêu chí | Điểm tối đa | Cách đánh giá |
|---|---:|---|
| Kiến trúc/mã Java | 20 | Tách đúng service boundary, API rõ, mã chạy được |
| Container/build | 15 | Dockerfiles, images có version/digest, tests trước build |
| Kubernetes | 20 | Deployments/Services/health/resource limits, rollout và scaling |
| Cloud SQL/IAM | 20 | Auth Proxy và Workload Identity, không dùng service account JSON key |
| Kiểm thử/quan sát | 15 | API tests, logs, dependency failure và metrics được giải thích |
| Bảo mật/chi phí/cleanup | 10 | Least privilege, không lộ secret, cleanup đúng project |
| **Tổng** | **100** | Nên yêu cầu bằng chứng lệnh và screenshot/dashboard đã làm sạch dữ liệu nhạy cảm |

### Hồ sơ nộp bài

Nộp sơ đồ kiến trúc, mã nguồn Java, Dockerfiles, manifests đã **loại secrets**, build IDs và image digests, kết quả `kubectl get`/rollout, các response API tiêu biểu, bảng test case, log/metric minh chứng và ước tính chi phí. Không đưa service account keys, token, password, connection string nhạy cảm hoặc dữ liệu khách hàng vào báo cáo.

## 19. Checklist cuối cùng

- [ ] Dùng đúng project sandbox, region, Billing/quota đã được xác nhận.
- [ ] Hai Spring Boot services có dependency và Java version phù hợp.
- [ ] Catalog và orders chạy trên hai Deployments, ClusterIP Services đúng selector.
- [ ] Orders chỉ gọi catalog qua service API, không truy cập data store của catalog.
- [ ] PostgreSQL schema tồn tại, user và quyền DB đúng, không dùng admin user runtime.
- [ ] Workload Identity binding và KSA annotation khớp namespace/service account.
- [ ] Cloud SQL Auth Proxy kết nối qua IAM/TLS, không mount credential JSON.
- [ ] Secret không được commit vào Git/YAML/image và đã có kế hoạch đưa vào Secret Manager.
- [ ] Requests/limits, startup/readiness/liveness probes hợp lý và được thử.
- [ ] POST/GET orders hoạt động, test lỗi đầu vào và catalog outage đã thực hiện.
- [ ] Image tags/digests có thể truy vết, rollout/rollback đã thử.
- [ ] Logs/metrics giúp phân biệt lỗi Java, Kubernetes, IAM và Cloud SQL.
- [ ] Có phương án bảo vệ dữ liệu, migration, backup và khôi phục khi lên production.
- [ ] Đã rà soát chi phí và xóa mọi tài nguyên lab không còn dùng.

## 20. Kết luận

Dự án hai microservices Java trên GKE cho thấy việc đưa ứng dụng lên Kubernetes chỉ là một phần của kiến trúc cloud. Thành công phụ thuộc đồng thời vào **ranh giới sở hữu dữ liệu, network service discovery, danh tính workload, quyền Cloud SQL, quản lý image, health checks và kiểm thử vận hành**. Sau khi hoàn tất lab, người học có nền tảng để mở rộng lên messaging bất đồng bộ, API gateway, CI/CD với Cloud Deploy, Secret Manager, distributed tracing và thiết kế phục hồi mà vẫn giữ kiểm soát bảo mật, độ tin cậy và chi phí.

## Tài liệu tham khảo

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

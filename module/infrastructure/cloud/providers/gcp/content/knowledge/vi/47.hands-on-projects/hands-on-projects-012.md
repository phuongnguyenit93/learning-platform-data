# Dự án dashboard SLO và cảnh báo cho hệ thống Java

Trong module `CLOUD_PROVIDERS_GCP`, người học khám phá Google Cloud từ project, IAM và VPC đến Compute Engine, GKE, Cloud Run, các dịch vụ lưu trữ và cơ sở dữ liệu. Qua tình huống triển khai, người học học cách lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Ở chương **Dự án thực hành GCP**, bài này biến các khái niệm observability thành một hệ thống đo lường có thể sử dụng để vận hành ứng dụng **Java/Spring Boot**.

Bạn sẽ xây API `orders-api` trên **Cloud Run**, dùng **Cloud Monitoring** để theo dõi lưu lượng, lỗi và độ trễ; định nghĩa **Service Level Indicators (SLIs)**, **Service Level Objectives (SLOs)** theo cửa sổ 28 ngày, tạo dashboard cho nhóm vận hành và cảnh báo theo **error-budget burn rate**. Các thao tác được chia thành code Java, tài nguyên Terraform và bước kiểm thử nghiệm thu. Kiến trúc này có thể mở rộng sang GKE/Compute Engine, nhưng ví dụ chính sử dụng Cloud Run để tránh phải tự vận hành Prometheus/metrics collector ngay từ đầu.

> **Giới hạn lab:** Đây là bài thực hành mô tả lệnh và hạ tầng mẫu; các placeholder phải được thay trước khi chạy. Không có deployment, tài nguyên hay alert nào được tạo chỉ bằng việc đọc bài. Tất cả thao tác tạo dịch vụ, gửi tải hoặc mở kênh thông báo phải được thực hiện trong **project staging** với IAM phù hợp, cảnh báo chi phí và quyền phê duyệt. Không bật endpoint gây lỗi trong production.

## 1. Đề bài, phạm vi và tiêu chí nghiệm thu

Giả sử nhóm Orders đang phát hành API Java. Trước đây nhóm chỉ quan sát CPU và số instance; một đợt lỗi database làm nhiều request trả HTTP 503 nhưng CPU vẫn thấp. Nhóm cần một **dashboard lấy trải nghiệm người dùng làm trung tâm** và cảnh báo sớm trước khi hết error budget.

| Deliverable | Kết quả cần tạo | Cách xác minh |
| --- | --- | --- |
| Java API | Endpoint thành công và endpoint kiểm thử lỗi/chậm chỉ ở profile `lab` | Request thật trả 200, 503, hoặc 200 sau thời gian chờ có chủ đích |
| Cloud Run service | `orders-api` chạy ở region staging, bật authentication | URL và service metrics xuất hiện |
| Availability SLI/SLO | Tỷ lệ good requests / eligible requests, mục tiêu 99,9% trong 28 ngày | SLO details hiển thị definition và compliance |
| Latency SLI/SLO | Tỷ lệ request thành công dưới 400 ms, mục tiêu 95% trong 28 ngày | SLO details hiển thị latency distribution cut |
| Dashboard | Request rate, 5xx rate, p95 latency, SLO compliance/error budget | Chart có time series, đúng project/service/region |
| Alerting | Fast burn và slow burn theo availability error budget | Alert policies hợp lệ, channel được verify, runbook cụ thể |
| Incident exercise | Tạo traffic lỗi có kiểm soát, quan sát latency/error/SLO | Evidence về metric và alert hoặc lý do chưa trigger |
| Operations | Owner, escalation, chống alert fatigue, kiểm soát chi phí và cleanup | Runbook, checklist và kết quả `terraform plan` |

Không yêu cầu database thật, Pub/Sub hay GKE trong MVP. Chúng có thể bổ sung sau khi các chỉ số HTTP cơ bản hoạt động. Bài cũng không đặt điều kiện phải gây lỗi đủ lớn để vượt SLO thật: mục đích là kiểm tra pipeline observability mà không tạo sự cố sản xuất.

## 2. Kiến trúc quan sát và đường đi của dữ liệu

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

**Phân biệt nguồn dữ liệu:**

- **Cloud Run platform metrics:** `run.googleapis.com/request_count` và `run.googleapis.com/request_latencies` xuất hiện trong Cloud Monitoring cho Cloud Run revisions. Không cần cài agent để có chúng.
- **Cloud Logging:** Cloud Run thu stdout/stderr và request logs; dùng để điều tra nguyên nhân sau khi một metric báo có vấn đề.
- **Spring Boot Actuator/Micrometer:** hiển thị health và các metrics bên trong JVM. Chúng **không tự động được xuất vào Cloud Monitoring** chỉ vì thêm dependency. Muốn dùng làm SLI thì phải cài pipeline export như OpenTelemetry Collector hoặc Google Cloud Managed Service for Prometheus.
- **Monitoring service:** đối tượng logic trong Cloud Monitoring, làm parent cho SLO. Nó khác với `Cloud Run service`; một Monitoring custom service có thể gom SLIs theo mục tiêu nghiệp vụ.
- **SLO:** gồm SLI, mục tiêu định lượng và compliance period. SLO không tự động tạo pager; cần alert policy riêng.

MVP dùng **platform request metrics** vì chúng có thể đo phần lớn request thành công/thất bại mà không phụ thuộc code Java có instrument đầy đủ hay chưa. Đổi lại, metric có những giới hạn về scope, sampling và loại request được ghi nhận.

## 3. Hiểu SLI, SLO, SLA và error budget

### 3.1. Những khái niệm phải tách biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **SLI** | Một phép đo chất lượng dịch vụ theo kết quả quan sát | 99,94% eligible HTTP requests được coi là tốt |
| **SLO** | Mục tiêu cho SLI trong một kỳ | Ít nhất 99,9% eligible requests tốt trong 28 ngày |
| **SLA** | Cam kết với khách hàng/đối tác, có thể kèm chế tài | Cam kết trong hợp đồng, không đồng nghĩa với mục tiêu kỹ thuật nội bộ |
| **Error budget** | Tỷ lệ hoặc số sự kiện xấu có thể chấp nhận theo SLO | 0,1% eligible requests cho SLO 99,9% |
| **Burn rate** | Tốc độ tiêu thụ error budget so với tốc độ lý tưởng | 10x: nếu kéo dài sẽ dùng budget nhanh hơn dự định 10 lần |

### 3.2. Availability SLI của dự án

Quy ước cho API này:

- **Good requests:** HTTP 1xx hoặc 2xx.
- **Eligible total requests:** tất cả request trừ **4xx**, do lỗi client thường không phải sự cố vận hành backend.
- **Bad requests:** phần eligible không nằm trong nhóm good (thường 5xx; nếu API phát sinh 3xx thì theo định nghĩa này cũng bị xem là bad).

\[
\text{Availability SLI}=\frac{\text{Good requests}}{\text{Eligible total requests}}
\]

Ví dụ: trong kỳ có 1.000.000 eligible requests, 999.200 good và 800 bad, tỷ lệ availability là 99,92%. Mục tiêu 99,9% cho phép tối đa **1.000 bad requests** trên 1.000.000 eligible requests trong kỳ, nên còn 200 request trong error budget. Nếu số eligible requests thay đổi, absolute budget cũng thay đổi.

**Đây là request-based SLO, không phải 40 phút downtime.** Không thể đổi số bad requests thành phút downtime nếu không biết lưu lượng theo thời gian. Ngoài ra, không có request không có nghĩa availability tự động 100%.

### 3.3. Latency SLI của dự án

Dùng `run.googleapis.com/request_latencies` (đơn vị **mili giây**) cho các request **2xx**, với good threshold **0–400 ms**:

\[
\text{Latency SLI}=\frac{\text{Số request 2xx hoàn tất trong 400 ms}}{\text{Tổng request 2xx có latency}}
\]

Mục tiêu **95%** trong rolling 28 ngày. Với 100.000 successful requests, tối đa 5.000 request có latency trên 400 ms mà vẫn đạt mục tiêu. SLI này khác với `p95 latency` biểu diễn một **giá trị thời gian**: p95 của từng phút trên dashboard có thể biến động, trong khi SLO dùng tỷ lệ tích lũy từ distribution samples.

Cloud Run `request_latencies` đo từ khi request đến container đang chạy tới khi trả lời; **không bao gồm container startup latency**. Vì vậy, dashboard cần bổ sung góc nhìn external/synthetic nếu trải nghiệm của người dùng có cold starts, lỗi tại Load Balancer hoặc request không đến container.

### 3.4. Vì sao chọn 28 ngày?

`rolling_period_days = 28` là cửa sổ tính toán di động: tại thời điểm hiện tại, Monitoring xét 28 ngày gần nhất. Khác `calendar_period = "MONTH"`, kỳ rolling không reset vào đầu tháng. Ví dụ dùng 28 ngày để thuận lợi khi đo theo tuần; đây là **mục tiêu lab**, không phải giá trị bắt buộc cho mọi hệ thống.

### 3.5. Tính burn rate bằng ví dụ

SLO availability 99,9% có error budget ratio `0.001`.

~~~text
Error budget fraction = 1 - 0.999 = 0.001 (0.1%)

Nếu tỷ lệ bad requests trong cửa sổ lookback = 1.0%:
  Burn rate ≈ 0.01 / 0.001 = 10x

Nếu tỷ lệ bad requests = 0.2%:
  Burn rate ≈ 0.002 / 0.001 = 2x
~~~

Burn rate cao không nhất thiết có nghĩa SLO 28 ngày đã vi phạm; nó cảnh báo rằng **nếu duy trì cùng tốc độ lỗi**, budget sẽ bị tiêu thụ quá nhanh. Với ít traffic, cần cân nhắc số mẫu tối thiểu và dữ liệu thiếu để tránh đưa ra kết luận không đáng tin.

## 4. Công cụ, IAM và chi phí

### 4.1. Điều kiện đầu vào

- Java **21** hoặc phiên bản JDK được Spring Boot của tổ chức hỗ trợ; Maven/Gradle.
- Một Google Cloud project staging đã liên kết Billing, có quyền triển khai Cloud Run và dùng Cloud Monitoring.
- `gcloud` và `terraform` trên máy phát triển/CI; ADC hoặc Workload Identity Federation cho automation.
- Một principal có quyền gọi Cloud Run và một địa chỉ email on-call **được xác nhận** để nhận cảnh báo.
- Budget/alerts chi phí ở project staging; không dùng project production hoặc tài nguyên khách hàng.

### 4.2. IAM tách biệt

| Principal | Quyền cần theo tác vụ | Khuyến nghị |
| --- | --- | --- |
| **Build/deploy CI** | Deploy Cloud Run và dùng runtime service account; quyền build/push artifact liên quan | Role phù hợp với pipeline, cần `iam.serviceAccounts.actAs` khi attach runtime SA |
| **Cloud Run runtime SA** | Quyền gọi downstream Google APIs mà code dùng | **Không cần Monitoring Editor chỉ để Cloud Run xuất built-in request metrics/logs** |
| **Monitoring author** | Tạo Monitoring custom service, SLO, dashboard, alert policies và notification channel | `roles/monitoring.editor` đủ để làm lab, production tách thành custom roles/least privilege |
| **Dashboard viewer** | Xem Monitoring dashboard, metrics/SLO và logs nếu được cấp | `roles/monitoring.viewer` và role Logging riêng khi cần |
| **Tester HTTP** | `roles/run.invoker` trên service staging yêu cầu auth | Gọi bằng OIDC ID token; không cho public anonymous chỉ để dễ test |
| **FinOps owner** | Xem Billing, ngân sách và quota | Không mặc định cấp Billing Admin cho người làm dashboard |

Không tạo service account key JSON dài hạn trong source repository. Cloud Run dùng service account gắn với workload; CI dùng short-lived credentials. Không đưa ID token, access token hoặc email khách hàng vào log, trace và dashboard.

### 4.3. Chi phí và độ trễ của telemetry

Cloud Run, Cloud Build, Artifact Registry, Logging, Monitoring và các channel gửi thông báo có thể phát sinh chi phí tùy mức sử dụng. Cloud Monitoring platform metrics không nhất thiết tính phí như custom metrics, nhưng **custom metrics, logs ingest/retention, trace ingestion, uptime checks, notification delivery và dashboard traffic** cần xem bảng giá hiện hành. Không tạo nhiều labels có cardinality vô hạn như `orderId`, `userId`, `requestId` trong metric.

Cloud Run request metrics được lấy mẫu khoảng **60 giây** và có thể cần thêm thời gian mới hiển thị. Trong tài liệu metric hiện hành, một số request metrics mất tới khoảng **120 giây** sau sampling để xuất hiện. Không coi việc dashboard trống ngay sau một request là lỗi Terraform.

## 5. Tạo Spring Boot API minh họa

### 5.1. Khởi tạo ứng dụng

Dùng Spring Initializr để tạo một Spring Boot project Maven với:

- Java 21.
- Dependencies: **Spring Web**, **Spring Boot Actuator**.
- Group `com.example`, artifact `orders-api`, base package `com.example.orders`.

Phần dependency trong `pom.xml` của project đã có Spring Boot parent:

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

Không tự chọn một phiên bản Spring Boot không tương thích với JDK/buildpack đang dùng. Ghi rõ BOM và version trong project thực tế. Cloud Run sử dụng container/buildpacks, nên ứng dụng phải lắng nghe trên cổng được cấu hình; MVP chọn **8080**, cũng là container port mặc định của nhiều Cloud Run deployments.

### 5.2. Application entrypoint

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

### 5.3. API thông thường

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

MVP không dùng database. Endpoint trả HTTP 200 và JSON, đủ để sinh dữ liệu thành công cho SLI.

### 5.4. Endpoint gây lỗi/chậm **chỉ trong profile lab**

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

**Bảo mật:** `@Profile("lab")` chỉ đăng ký controller khi profile lab được bật. Tuyệt đối không bật profile này trên revision production. Trong staging, dùng Cloud Run authentication, giới hạn người có `roles/run.invoker`, max instances và ngân sách. Đừng để endpoint gây lỗi công khai vì có thể biến thành một hình thức tự tạo denial of service.

### 5.5. Cấu hình Actuator và logs

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

Bài lab bật `/actuator/metrics` để **xem trong môi trường được bảo vệ**; production nên giới hạn Actuator endpoints bằng Spring Security/network hoặc không expose `metrics` công khai. Không đưa `env`, `heapdump`, `configprops` ra Internet.

Logs của Spring Boot trên stdout/stderr sẽ được Cloud Run chuyển sang Cloud Logging. Có thể bổ sung OpenTelemetry Java Agent để xuất traces, nhưng việc thiếu agent **không làm mất** Cloud Run request_count/request_latencies dùng trong SLO này.

### 5.6. Chạy local

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=lab

curl -i http://localhost:8080/api/orders/1001
curl -i http://localhost:8080/__lab/fail
curl -i http://localhost:8080/__lab/slow
curl -i http://localhost:8080/actuator/health
~~~

Kỳ vọng: `/api/orders/1001` trả 200; `/__lab/fail` trả 503; `/__lab/slow` trả 200 sau khoảng 700 ms do ứng dụng chủ động chờ. Đây là kết quả local **chưa tạo** Cloud Run metrics.

## 6. Triển khai Cloud Run trong project staging

### 6.1. Bật API cần thiết

Dùng project đã được cấp quyền và có billing:

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

Trên CI có thể cần thêm các API và role theo build pipeline/source deployment của project. Gắn service account riêng khi ứng dụng gọi API downstream; MVP không cần database hay Secret Manager.

### 6.2. Deploy từ source của ứng dụng

Chạy lệnh trong thư mục có `pom.xml`:

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

`--source` yêu cầu build/deploy permissions và có thể tạo/build image trong Artifact Registry. Nếu Cloud Build không nhận đúng JDK/Spring Boot version, sửa cấu hình buildpack hoặc dùng Dockerfile đã được tổ chức duyệt. Không thay sang `--allow-unauthenticated` chỉ để vượt lỗi IAM.

**Lab profile phải được gỡ khi release production.** Khi hoàn tất, đừng chỉ xóa resource Terraform Monitoring mà để Cloud Run revision `lab` còn phục vụ traffic không kiểm soát.

### 6.3. Lấy URL và gọi với ID token

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

Caller phải có `roles/run.invoker` trên service. Từ một số môi trường/credential types, ID token của user không có audience phù hợp; có thể dùng service account impersonation với `--audiences` đặt bằng URL Cloud Run khi operator có quyền mint token. Không sử dụng OAuth access token cho Google APIs để thay thế ID token khi gọi private Cloud Run HTTP endpoint.

Kiểm tra service có revision ready và metadata region/name đúng. **Không cần bật public access** để Monitoring thu platform metrics.

## 7. Chọn và kiểm tra đúng Cloud Monitoring metrics

### 7.1. Các metric được sử dụng

| Metric type | Monitored resource | Kind/type | Dùng cho |
| --- | --- | --- | --- |
| `run.googleapis.com/request_count` | `cloud_run_revision` | DELTA / INT64 | Request volume, 5xx rate, availability good/total |
| `run.googleapis.com/request_latencies` | `cloud_run_revision` | DELTA / DISTRIBUTION, **ms** | p95 latency, tỷ lệ request dưới 400 ms |
| `run.googleapis.com/container/instance_count` hoặc metric instance tương ứng | Cloud Run resource tùy metric | GAUGE | Chẩn đoán autoscaling |
| Cloud Logging request log | `cloud_run_revision` | Log entries | Chi tiết status, URL, request trace |
| Application Java Actuator metrics | JVM/app internals | Chỉ local trừ khi có exporter | Phân tích heap, GC, thread pool, custom business SLIs |

**Giới hạn quan trọng của Cloud Run request_count:** metric chỉ đếm các request **đến revision/container**; có thể **không đếm** request bị chặn vì chưa xác thực hoặc khi maximum instances limit khiến request bị từ chối trước khi vào container. `route` của Cloud Run request metric cũng không cung cấp route path hữu dụng (thường rỗng). SLO dựa trên metric này là **backend service SLO**, không phải bằng chứng đầy đủ về trải nghiệm ở public edge. Nếu service đặt sau Application Load Balancer, cân nhắc load balancer request metrics và uptime checks hoặc business metrics riêng cho đường người dùng.

### 7.2. Test filter trước khi tạo SLO

Mở **Monitoring → Metrics Explorer**:

1. Chọn resource **Cloud Run Revision**.
2. Chọn metric **Request Count**.
3. Lọc `service_name = orders-api`, `location = asia-southeast1`.
4. Dùng alignment rate hoặc sum phù hợp để biểu diễn requests/second.
5. Group theo `response_code_class` để phân biệt 2xx, 4xx, 5xx.
6. Chọn **Request Latency** và align theo percentile 95, đơn vị ms.

Nếu không có dữ liệu, gửi vài request 200/503 trong staging và chờ đủ thời gian sampling. Không định nghĩa SLO trước khi xác nhận `Metric Explorer` thấy đúng series và labels; filter sai project/location có thể tạo SLO trống dù Terraform apply thành công.

## 8. Terraform: Monitoring service và hai SLO

Thư mục `monitoring/` trong **workspace lab** của người học (không phải trong module nguồn bài học):

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

### 8.1. Provider và biến

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

Trong production, dùng protected remote state và provider lockfile; không dùng local Terraform state chia sẻ tùy tiện.

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

`terraform.tfvars` mẫu:

~~~hcl
project_id        = "REPLACE_WITH_STAGING_PROJECT_ID"
region            = "asia-southeast1"
cloud_run_service = "orders-api"
alert_email       = "platform-oncall@example.com"
~~~

Địa chỉ `example.com` là placeholder, không phải người nhận thực. Nếu email channel chưa xác minh hoặc bị chặn bởi organizational policy, alert có thể tồn tại mà **không gửi được thông báo**.

### 8.2. Filter Cloud Run được giới hạn đúng service và region

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

Bốn filters được dùng để đảm bảo **cùng một service/region** được đo. Không lọc theo `revision_name`: mọi revision đang nhận traffic của service đều phải tham gia SLO. Nếu người học thay đổi service name hoặc region khi deploy, phải sửa đúng variables và kiểm tra metric có dữ liệu.

### 8.3. Tạo Monitoring custom service

~~~hcl
resource "google_monitoring_custom_service" "orders" {
  project      = var.project_id
  service_id   = "orders-api-observability"
  display_name = "Orders API - Java / Cloud Run"
}
~~~

**Monitoring custom service** là một nhóm SLO. Nó không tạo Cloud Run service và không tự instrument code Java. Các filters của SLO bên dưới mới xác định metric nào được dùng.

### 8.4. Availability SLO: 99,9% trong 28 ngày

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

**Định nghĩa denominator được chọn có chủ ý**: 4xx được bỏ qua, 1xx/2xx là good; 5xx và 3xx được tính là not-good nếu có. Với API redirect 3xx hợp lệ, cần sửa định nghĩa SLI để tránh báo lỗi sai. Bộ lọc good/total phải có metric kind DELTA/CUMULATIVE phù hợp, và **good phải là tập con của total**.

### 8.5. Latency SLO: 95% successful requests dưới 400 ms

Cũng trong `slos.tf`:

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

Ở đây **400 là mili giây**, không phải 0,4 giây, vì Cloud Run `request_latencies` là distribution metric có đơn vị `ms`. DistributionCut đếm số phần tử ở khoảng good so với tổng phần tử trong distribution, không lấy giá trị p95 ở mỗi phút rồi tính trung bình. SLO latency dùng request 2xx; lỗi 5xx đã có SLO availability bao phủ.

## 9. Terraform: dashboard request rate, 5xx và latency p95

Dashboard là công cụ **điều tra và nhìn xu hướng**, còn SLO là thước đo **cam kết chất lượng**. Cần cả hai.

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

Với `request_count` là DELTA count, `ALIGN_RATE` biểu diễn tốc độ theo giây và `REDUCE_SUM` cộng across revisions. Với latency p95, **không lấy trung bình các p95 khác nhau** để coi là p95 toàn hệ thống; ví dụ giữ các series riêng. Nếu cần percentiles gộp across revisions, dùng distribution-aware aggregation được Monitoring hỗ trợ hoặc thiết kế metric phù hợp, không dùng `REDUCE_MEAN` trên percentile.

Bảng dashboard còn thiếu một phần rất quan trọng là **SLO widget**. Sau khi SLO được tạo, thực hiện trong Console:

1. Vào **Monitoring → Dashboards**, chọn `Orders API | Java SLO and Reliability`.
2. Bấm **Add widget → SLO**.
3. Chọn Monitoring service `Orders API - Java / Cloud Run`.
4. Chọn SLO `Orders API availability >= 99.9% / 28d`; hiển thị **compliance** và thêm một widget **remaining error budget**.
5. Chọn latency SLO và thêm **compliance**; đặt thời gian và tên biểu đồ dễ hiểu.
6. **Apply/Save**; xác nhận chart load và khác biệt giữa SLO compliance với p95 chart.

Lưu ý **drift**: nếu dashboard được Terraform quản lý mà bạn chỉnh tay trong Console, lần `terraform plan/apply` sau có thể ghi đè thay đổi thủ công. Để duy trì bằng IaC dài hạn, export JSON dashboard sau khi đã thêm SLO widgets rồi đưa phần widget đó vào `dashboard_json` dưới review code. Không nhập một widget SLO bằng tay rồi giả định Terraform sẽ giữ mãi.

## 10. Terraform: notification channel và cảnh báo burn rate

### 10.1. Chuẩn bị email channel

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

Địa chỉ phải được xác minh theo quy trình Cloud Monitoring. Cân nhắc group/team email với người trực chịu trách nhiệm thay vì hộp thư cá nhân duy nhất. Có thể thay email bằng Slack, PagerDuty hoặc kênh khác nếu tổ chức đã kết nối và kiểm tra thực tế. Mỗi notification channel có thể phát sinh phí theo loại/kế hoạch, cần xem tài liệu giá.

### 10.2. Fast burn: lớn hơn 10x trong lookback 60 phút

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

Selector `select_slo_burn_rate` lấy **tên resource SLO đầy đủ** và khoảng nhìn lại 60m. `duration = "0s"` không có nghĩa cảnh báo chỉ dùng một request: burn rate đã được tính bằng dữ liệu trong **cửa sổ 60 phút**. Ngưỡng 10x là ví dụ gợi ý cho fast-burn, phải tune theo service traffic và mức SLO thực.

### 10.3. Slow burn: lớn hơn 2x trong lookback 24 giờ

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

Theo hướng dẫn Google Cloud, kết hợp fast-burn (lookback ngắn, ngưỡng cao) và slow-burn (lookback dài, ngưỡng thấp) giúp cảnh báo cả sự cố lớn lẫn suy giảm kéo dài. Trong hệ thống có traffic ít, lookback 24h cần thời gian để đủ mẫu; không đánh giá alert bị hỏng chỉ vì vừa tạo xong chưa firing.

**Không dùng metric threshold thông thường thay cho SLO selector trong condition này.** Với SLO burn-rate filter, không thêm `aggregations` hoặc denominator filter của metric type thông thường. Terraform phải phụ thuộc vào `google_monitoring_slo.availability.name`, nên tài nguyên SLO sẽ được tạo trước policy.

### 10.4. Một cảnh báo bổ sung nên cân nhắc

Dự án có thể cần **uptime/synthetic check** hoặc cảnh báo absolute 5xx từ external load balancer khi traffic không đến container. SLO dùng Cloud Run request metrics có thể **không ghi nhận** một số lỗi từ chối trước container. Nếu không có requests, request-based SLO không chứng minh hệ thống còn sẵn sàng. Không lấy `no data` làm `all good`.

Có thể tạo thêm uptime check ở project staging đối với **endpoint có thể truy cập từ vị trí kiểm tra**. Cloud Run private service cần thiết kế synthetic test có auth/network phù hợp; không bật public access chỉ để uptime check đi qua.

## 11. Terraform output, review và apply

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

Trong thư mục `monitoring/` của lab:

~~~bash
terraform init
terraform fmt -recursive
terraform validate
terraform plan -out=monitoring.tfplan
terraform show monitoring.tfplan
terraform apply monitoring.tfplan
terraform output
~~~

**Kiểm tra plan:** resource được tạo đúng project; SLO filters dùng `orders-api` và region staging; channel email đúng; không có policy sẽ spam production on-call; không có xóa/replace tài nguyên Monitoring do team khác quản lý. Khi dùng remote Terraform state, bật phân quyền/phiên bản phù hợp và không commit state vào Git.

Lưu ý code là **mẫu Terraform** cần kiểm thử với phiên bản provider đã chọn và API permissions trong project thực tế. Các API có thể thay đổi schema hoặc validation; nếu nhận lỗi, đọc thông báo provider/Monitoring API và sửa theo tài liệu chính thức, không cấp Owner hoặc vô hiệu hóa audit để làm lệnh chạy.

## 12. Xác minh dashboard và SLO từ Google Cloud Console

Sau `terraform apply`, vào **Monitoring → SLOs**:

1. Xác minh custom service `Orders API - Java / Cloud Run` tồn tại.
2. Mở availability SLO, xem **99,9% / rolling 28d** và định nghĩa good/eligible.
3. Mở latency SLO, xem **95% under 400ms** và metric đơn vị ms.
4. Trong Service Monitoring dashboard, kiểm tra SLI chart, compliance, error-budget consumption.
5. Nếu chart trống, so sánh filter với Metrics Explorer và chạy vài requests; chờ metrics ingestion.
6. Trong **Monitoring → Dashboards**, kiểm tra request rate, 5xx rate và p95.
7. Trong **Alerting**, kiểm tra fast/slow policies và trạng thái channel verified.

Một bảng nghiệm thu hữu ích:

| Kiểm tra | Phương pháp | PASS khi |
| --- | --- | --- |
| METRIC-01 | Metrics Explorer `request_count` | Có dữ liệu cho đúng `service_name`, `location` |
| METRIC-02 | Filter 5xx | Request lab 503 được ghi nhận sau sampling delay |
| METRIC-03 | `request_latencies` | Request lab slow tạo mẫu latency tăng |
| SLO-01 | SLO availability details | Good/total đúng, mục tiêu 99,9%, cửa sổ 28 ngày |
| SLO-02 | SLO latency details | 2xx distribution, ngưỡng 400 ms, mục tiêu 95% |
| DASH-01 | Dashboard | Các chart tải được và không trộn nhiều service |
| DASH-02 | SLO widgets | Compliance và remaining budget hiển thị cho đúng SLO |
| ALERT-01 | Policies | Fast 10x/60m và slow 2x/24h dùng đúng SLO name |
| ALERT-02 | Notification channel | Email/kênh đã xác minh, có owner/runbook |
| SEC-01 | Cloud Run service | Yêu cầu auth, lab profile chỉ ở staging |
| COST-01 | Billing/budget | Có phạm vi cost review và cleanup plan |

Lấy screenshot dashboard và xuất `terraform plan`/SLO definition làm bằng chứng; không chụp/log token. **PASS của code/UI không đồng nghĩa đã thử pager delivery**; channel test cần bước xác nhận riêng.

## 13. Kiểm thử lỗi có kiểm soát và đọc kết quả

### 13.1. Sinh baseline traffic

Trước khi thử lỗi, gửi một số request 200 từ một caller có `roles/run.invoker`:

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

Một lượng nhỏ traffic có thể không đủ tạo burn-rate alert đáng tin. Mục tiêu của bước này là xác minh **metrics ingestion** và request count tăng. Giới hạn request rate, instance count và chi phí, không dùng tải lớn bất chợt.

### 13.2. Thử lỗi 503 và latency cao

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

Bài lab phải chạy trên service bật profile `lab`. Nếu endpoint 404 thì kiểm tra profile, URL và revision; nếu HTTP 401/403 thì kiểm tra ID token và IAM, **không** thêm anonymous invocation. Dừng ngay khi thấy request count/cost ngoài dự kiến.

### 13.3. Kiểm tra phản ứng

Sau vài phút, kiểm tra:

- Request chart có traffic tăng sau đoạn loop.
- 5xx chart có dấu hiệu của 10 responses 503.
- Latency p95 của successful requests tăng trong cửa sổ có `/__lab/slow` (tùy phân phối request).
- Availability SLI và SLO compliance/error budget thay đổi theo số requests ở **toàn cửa sổ**.
- Logs Explorer có thông tin request lỗi giúp điều tra.

**Không được giả định fast/slow alert bắt buộc firing** từ 10 lỗi trong vài phút: selector fast xem 60 phút, selector slow xem 24 giờ, denominator phụ thuộc traffic thực và SLO được tạo gần đây có thể thiếu dữ liệu lịch sử. Để kiểm tra kênh thông báo, dùng tính năng test channel/sandbox alert hoặc một alert test có thời gian hoạt động ngắn được phê duyệt, rồi xóa nó sau test.

### 13.4. Tra log để điều tra

Trong **Logs Explorer**, filter:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
httpRequest.status>=500
~~~

Bổ sung thời gian, region, trace ID và revision khi cần. Request logs có thể chỉ cho thấy HTTP status/latency; để tìm nguyên nhân nghiệp vụ phải dùng structured application logs/traces. Không log thông tin người dùng hoặc payload nhạy cảm chỉ để tăng khả năng debug.

## 14. Runbook cho fast-burn và slow-burn

### 14.1. Fast-burn: phản ứng sự cố

1. **Acknowledge** alert, xác nhận project, service, region, SLO và cửa sổ lookback.
2. Kiểm tra **traffic volume** để tránh kết luận từ sample nhỏ.
3. Mở dashboard request rate, 5xx, latency; phân loại triệu chứng.
4. Mở Cloud Run **Revisions/Traffic** để xem deploy mới, thay đổi max instances, concurrency, CPU/memory.
5. Tra Cloud Logging theo status, trace, exception và request ID; kiểm tra dependencies (Cloud SQL, Pub/Sub, Secret Manager).
6. Nếu liên quan revision mới, cân nhắc **rollback traffic** theo runbook được phê duyệt.
7. Kiểm tra error budget còn lại và xác nhận chỉ số phục hồi; liên hệ customer-facing team nếu sự cố đủ nghiêm trọng.
8. Ghi timeline, nguyên nhân, tác động và follow-up. Đừng chỉ tắt alert khi lỗi chưa được khắc phục.

### 14.2. Slow-burn: cải thiện chất lượng kéo dài

- So sánh 24 giờ hiện tại với baseline cùng ngày trong tuần.
- Phân biệt 5xx do downstream, timeouts, quota, 429 và lỗi business contract.
- Xem p95/p99, cold starts, memory pressure, instance concurrency, DB connection pool, retry storms.
- Đề xuất cải tiến cấu hình, performance test hoặc capacity planning; không mua thêm CPU chỉ vì alert tồn tại.
- Điều chỉnh SLO/alert threshold **qua review** khi mục tiêu không phản ánh nhu cầu người dùng; không thay vì muốn làm dashboard “xanh”.

### 14.3. Mẫu thông báo có thể hành động

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

Bản nhắn ở trên chỉ chứa metadata kỹ thuật. Không đính kèm ID token, credentials hoặc thông tin cá nhân.

## 15. Phân biệt dashboard SLO với các metrics nội bộ Java

Cloud Run metrics phù hợp để bắt đầu, nhưng khi hệ thống lớn hơn, có thể cần:

| Nhu cầu | Telemetry bổ sung | Cách sử dụng |
| --- | --- | --- |
| JVM heap/GC/threads | Spring Boot Micrometer + exporter | Chẩn đoán Java-specific bottlenecks |
| p95 một endpoint nghiệp vụ | Application metrics có route template ổn định | Tạo SLI chỉ cho `POST /api/orders` |
| Database latency | JDBC spans/metrics và Cloud SQL metrics | Xem connection wait, query time, pool saturation |
| Async workflows | Pub/Sub backlog, oldest unacked age, processing lag | SLO cho thời gian xử lý sự kiện thay vì chỉ HTTP |
| User journey thực tế | Synthetic browser/HTTP probes + LB/edge metrics | Bổ sung blind spots trước Cloud Run container |
| Distributed traces | OpenTelemetry Java agent + Collector/OTLP | Liên kết request với calls tới service khác |

**Không** đưa `userId`, `orderId`, request UUID, email vào **metric labels**: cardinality có thể bùng nổ và làm tăng chi phí. Dùng route templates hoặc một tập labels hữu hạn như `operation`, `status_class`, `environment`. Các định danh riêng lẻ phù hợp hơn với logs/traces có chính sách dữ liệu.

Khi chuyển sang GKE, có thể dùng Managed Service for Prometheus để thu `http_server_requests_seconds_count` và histograms từ ứng dụng đã cấu hình exporter. Lúc đó SLO dựa trên custom metrics khác; **không** tái sử dụng nguyên filter `run.googleapis.com/request_count` cho GKE/VM.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Cloud Run metrics trống | Không có request vào container, sai project/service/region hoặc trễ sampling | Gửi request staging hợp lệ; xem Metrics Explorer, chờ ingestion |
| SLO luôn `No data` | SLI filters sai hoặc metric label không tồn tại; service mới chưa có traffic | Xem filters và resource labels trước, rồi thử SLO |
| Alert fast burn không kích hoạt sau 10 lỗi | Lookback 60m, tỷ lệ bad thực và lượng mẫu chưa vượt 10x | Xem burn-rate chart, tránh suy luận bằng một số requests |
| Alert slow burn chưa kích hoạt | Lookback 24h và mới tạo SLO | Chờ dữ liệu, test channel riêng |
| Dashboard p95 không đúng dự báo | Đang đo percentile per revision/class, không gộp distributions | Kiểm tra filter/grouping, phân biệt p95 và request-based SLO |
| SLO nhận nhiều traffic không liên quan | Cloud Run metric không có route label hữu dụng | Dùng custom business metric hoặc service riêng |
| Một số người dùng 429/401 nhưng SLO xanh | Request bị chặn trước container không nằm trong metric | Bổ sung LB/edge metric, uptime checks, user journey |
| Cloud Run `503` không xuất hiện | Request fail trước container hoặc sai service/revision | Xem request logs và metric scope, kiểm tra max instances |
| Terraform `403` khi tạo Monitoring | Thiếu Monitoring role/API | Cấp quyền đúng scope; không dùng Owner |
| Email channel không gửi cảnh báo | Chưa verify email, chính sách org chặn, sai channel | Test notification channel và routing |
| Sau sửa dashboard UI, Terraform muốn rollback | Drift giữa dashboard JSON và resource ngoài Terraform | Export JSON, đưa thay đổi vào code và review |
| Kết quả latency rất thấp nhưng user vẫn thấy chậm | Cloud Run request latency bỏ qua startup và edge | Dùng end-to-end latency/synthetic monitoring |
| Alert quá nhiều khi demo | Tạo policy trên production channel hoặc thresholds không phù hợp | Dùng email staging, giới hạn thời gian lab, cleanup |
| Cloud Run build/deploy thất bại | Source buildpack, Java version, IAM, artifact registry | Xem Cloud Build logs và quyền build/deploy |
| SLO liên tục đỏ dù API bình thường | Definition good/total không khớp: 3xx, auth, redirect, response classes | Thống nhất hợp đồng SLI, phân tích sample và cập nhật có review |

## 17. Chi phí, bảo mật và vòng đời khi kết thúc lab

### 17.1. Chặn blast radius

- Dùng project staging riêng, max instances = 2, min instances = 0 và request load nhỏ.
- Cloud Run yêu cầu auth; lab fault endpoints chỉ bật với `SPRING_PROFILES_ACTIVE=lab`.
- Email channel chỉ đến nhóm lab; không gửi pager tới trực production khi chưa phê duyệt.
- Dùng IAM tối thiểu: Monitoring author, dashboard viewer, deployer, runtime SA và HTTP caller khác nhau.
- Có Billing Budget và chủ sở hữu chịu trách nhiệm, nhưng **budget alerts không phải hard spending cap**.

### 17.2. Dọn dẹp theo thứ tự

1. Lưu screenshot và JSON SLO/dashboard/alert policy đã được kiểm chứng.
2. Trong `monitoring/`, chạy `terraform plan -destroy` và xác nhận chỉ bao gồm custom service, SLOs, alert policies, dashboard và channel **của lab**.
3. Sau approval, chạy `terraform destroy`; nếu có widgets hoặc policies được tạo tay ngoài Terraform, dọn chúng riêng theo ownership. Không xóa channel dùng chung của đội vận hành.
4. Xóa Cloud Run **staging lab service** `orders-api` qua quy trình thích hợp; tránh đụng production service trùng tên ở project khác.
5. Kiểm tra Cloud Build artifacts/Artifact Registry images và logging retention theo chính sách; một số chi phí có thể còn đến hết kỳ.
6. Xác nhận alert policies không còn gửi mail demo. Giữ bằng chứng đã redact, không lưu tokens.

Đừng chạy destroy khi bạn không chắc đang đứng trong project hoặc Terraform workspace nào. Xem toàn bộ plan trước, đặc biệt khi nhiều dịch vụ Monitoring cùng chia sẻ một notification channel.

### 17.3. Khi chuyển sang production

- Bỏ profile `lab` và mọi endpoint chủ động gây lỗi.
- Định nghĩa SLO theo trải nghiệm người dùng và loại trừ 4xx có chủ đích, review với product owner.
- Thêm synthetic/user-journey checks nếu các lỗi trước container quan trọng.
- Tính baseline traffic trước khi page theo burn rate; điều chỉnh threshold/duration để phù hợp trực on-call.
- Gắn alert owner và runbook; kiểm tra escalation, deduplication, auto-close và thời gian thông báo.
- Có IaC, review và rollback cho tất cả Monitoring resources; không để dashboard chỉ sống trên thao tác Console.

## 18. Checklist nghiệm thu cuối bài

- [ ] Có ứng dụng Spring Boot Java trả 200, kèm lab-only endpoints trả 503 và chậm 700 ms.
- [ ] Cloud Run service `orders-api` trong project/region staging và yêu cầu authentication.
- [ ] Có thể lấy metrics `run.googleapis.com/request_count` và `request_latencies`.
- [ ] Hiểu `request_count` bỏ qua một số request bị chặn trước container và `route` không hữu dụng.
- [ ] Availability SLI có good 1xx/2xx, eligible loại 4xx và đã thống nhất xử lý 3xx.
- [ ] Availability SLO 99,9% trên rolling 28 ngày.
- [ ] Latency SLO: 95% request 2xx dưới 400 ms; metric units đúng ms.
- [ ] Terraform custom service và hai SLO được tạo trong đúng project.
- [ ] Dashboard có request rate, 5xx rate, p95 latency và SLO/error-budget widgets.
- [ ] Không lấy trung bình p95 các revisions để coi là p95 toàn service.
- [ ] Có email/notification channel đã verified và người chịu trách nhiệm.
- [ ] Có fast burn 10x/60m và slow burn 2x/24h theo `select_slo_burn_rate`.
- [ ] Kiểm tra hoàn chỉnh alert definitions, notification wiring và runbook.
- [ ] Đã chạy traffic baseline/lỗi/chậm trong lab và thấy metric thay đổi sau ingestion delay.
- [ ] Hiểu vài request lỗi không bắt buộc làm alert firing ngay.
- [ ] Có logs/trace hoặc cách điều tra từ chart đến root cause.
- [ ] Không đưa credentials, personal data hoặc high-cardinality labels vào metrics/logs.
- [ ] Có plan chi phí, max instances, IAM tối thiểu, profile lab và cleanup an toàn.
- [ ] Lần Terraform plan sau apply không có resource drift ngoài dự kiến.
- [ ] Có bằng chứng nghiệm thu, owner và chính sách cảnh báo khi release production.

## Tài liệu tham khảo

- [Cloud Run: Monitor health and performance](https://docs.cloud.google.com/run/docs/monitoring) — platform metrics, Cloud Monitoring và Cloud Run resource types.
- [Cloud Monitoring metrics: `run.googleapis.com`](https://docs.cloud.google.com/monitoring/api/metrics_gcp_p_z) — request count, latency, units, labels và sampling limits.
- [Cloud Monitoring: Request-response services](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/sli-metrics/req-resp-metrics) — availability good/total ratio và latency distribution SLIs.
- [Cloud Monitoring: Define a service](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/define-svc) — Monitoring custom service và candidate services.
- [Cloud Monitoring: Create an SLO](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/create-slo) — SLI, goal, compliance period và validation.
- [Cloud Monitoring: Display SLOs on a dashboard](https://docs.cloud.google.com/monitoring/dashboards/slos) — compliance, health và remaining error-budget widgets.
- [Cloud Monitoring: Alerting on error-budget burn rate](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/alerting-on-budget-burn-rate) — fast/slow burn principles.
- [Cloud Monitoring: Create SLO alert policies with API](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/api/create-policy-api) — `select_slo_burn_rate` filter, threshold và notification channel.
- [Cloud Monitoring: Retrieve SLO data](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/api/timeseries-selectors) — SLO time-series selectors và lookback periods.
- [Terraform: `google_monitoring_custom_service`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_custom_service) — service resource và metadata.
- [Terraform: `google_monitoring_slo`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_slo) — request-based SLI, distribution cut, goal và rolling period.
- [Terraform: `google_monitoring_dashboard`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_dashboard) — dashboard JSON representation và chart widgets.
- [Terraform: `google_monitoring_alert_policy`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_alert_policy) — condition threshold, documentation và channels.
- [Terraform: `google_monitoring_notification_channel`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_notification_channel) — channel type/labels và verification.
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html) — health, Micrometer và observability endpoints.


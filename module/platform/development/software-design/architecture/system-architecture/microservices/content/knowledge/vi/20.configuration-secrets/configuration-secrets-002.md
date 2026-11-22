# Quản lý cấu hình theo môi trường và phiên bản

## 1. Mục tiêu

Trong hệ thống nhiều dịch vụ, cùng một mã nguồn thường được triển khai ở local, development, test, staging và production; đôi khi mỗi môi trường lại có nhiều vùng, cluster và phiên bản ứng dụng đang hoạt động đồng thời. Mỗi service cần các giá trị phù hợp cho kết nối, thời gian chờ, giới hạn tài nguyên, chính sách retry, topic, tính năng đang bật và tham chiếu đến bí mật. Nếu các giá trị này thiếu hợp đồng và lịch sử thay đổi, một lần sửa timeout cũng có thể làm gián đoạn cả luồng đặt hàng hoặc thanh toán.

**Quản lý cấu hình theo môi trường và phiên bản** là thiết kế cách định nghĩa, phân phối, xác thực, theo dõi và khôi phục cấu hình, sao cho có thể trả lời: instance nào đang chạy giá trị nào, lấy từ đâu, ai phê duyệt, tương thích với phiên bản code nào và rollback ra sao.

Sau bài này, bạn có thể:

1. Phân biệt cấu hình ứng dụng, cấu hình triển khai, bí mật, feature flag và dữ liệu nghiệp vụ.
2. Thiết kế hợp đồng cấu hình có kiểu, default, phạm vi, quy tắc override và kiểm tra hợp lệ.
3. Đặt một release ứng dụng trong quan hệ với config revision, schema version và secret version.
4. Xây dựng pipeline kiểm tra, promote, rollout và rollback cấu hình giữa nhiều môi trường.
5. Vận hành cấu hình tĩnh/động, quản lý secrets, phát hiện configuration drift và điều tra sự cố.

Ví dụ xuyên suốt dùng Order Service, Payment Service, Inventory Service, API Gateway và message broker, với Java/Spring Boot và Kubernetes. Các giá trị, URL và version trong ví dụ chỉ mang tính minh họa.

## 2. Đúng loại dữ liệu, đúng nơi quản lý

| Loại | Ví dụ | Nơi quản lý thích hợp | Điểm cần kiểm soát |
|---|---|---|---|
| Cấu hình ứng dụng | Timeout, connection pool, max retry, log level | Tệp non-secret, Git/config service | Kiểu, phạm vi, an toàn, tương thích |
| Cấu hình môi trường | DNS upstream, tên topic, region, namespace | Overlay hoặc tham số deploy | Tách biệt dev/staging/prod |
| Cấu hình hạ tầng | Replica, resource limits, Ingress, NetworkPolicy | IaC/manifest GitOps | Review, policy, lịch sử deploy |
| Bí mật (secret) | API key, password, private key, signing key | Secret manager hoặc cơ chế tương đương | Quyền đọc, bảo mật, rotation, audit |
| Feature flag | Checkout mới cho 5% traffic, kill switch | Flag service/config động có phân quyền | Scope, owner, expiry, rollback |
| Dữ liệu nghiệp vụ | Giá đơn hàng, trạng thái tồn kho, hồ sơ khách | Database và domain service | Authorization, transaction, audit |
| Runtime state | Trạng thái circuit breaker, số kết nối đang mở | Bộ nhớ/metrics/state store phù hợp | Quan sát, tính nhất quán, vòng đời |

**Bí mật không phải cấu hình thông thường.** Cùng là tham số được truyền vào service, nhưng bí mật có chính sách đọc, thời hạn và vòng đời luân chuyển riêng. Không lưu giá trị secret trong repository hay tệp cấu hình plain text của bản phát hành.

**Feature flag không thay thế contract của API.** Một flag có thể bật logic khác, nhưng phải bảo đảm các phiên bản producer/consumer còn hiểu dữ liệu và message được tạo trong giai đoạn rollout.

**Business data không nên trở thành environment variable.** Giá bán, điều kiện hợp đồng hoặc hạn mức từng khách hàng phải được quản lý theo quy tắc domain, có phân quyền và audit, tránh buộc restart service mỗi khi dữ liệu thay đổi.

## 3. Chọn môi trường và ranh giới

| Môi trường | Mục đích | Dữ liệu và quyền | Cách thay đổi |
|---|---|---|---|
| Local | Phát triển/debug từng service | Dữ liệu giả, sandbox, quyền thấp | File mẫu + override local không commit |
| Development | Tích hợp thường xuyên | Secret riêng dev, dịch vụ test | Đổi nhanh nhưng có revision |
| CI/Test | Chạy test lặp lại được | Fixtures, credential thử nghiệm | Cấu hình tái tạo được và được pin |
| Staging/Preprod | Xác nhận gần production | Dữ liệu kiểm thử/sanitized, quyền riêng | Review, smoke/integration/rollout thử |
| Production | Phục vụ người dùng thật | Credential và dữ liệu production | Policy, approval, canary, audit, rollback |

Môi trường cần được cách ly bằng **credential, IAM role, network policy và quyền dữ liệu**, ngoài việc đặt tên. Nếu staging vô tình trỏ sang database hoặc PSP production, chỉ thay tên tệp cấu hình không bảo vệ được dữ liệu.

Một cấu hình không chỉ có trục `environment`. Nó có thể phụ thuộc service, region, cluster/cell, tenant, phiên bản và release cohort. Ví dụ:

~~~text
payment-service
├── common
├── development
├── staging
└── production
    ├── apac
    │   ├── cell-a
    │   └── cell-b
    └── eu
        └── cell-a
~~~

Sử dụng cấu hình chung rồi override những giá trị thực sự khác nhau. Tránh nhân bản nguyên một tệp cho mọi tổ hợp nếu phần lớn giá trị trùng lặp, nhưng cũng không tạo quá nhiều lớp override khiến người vận hành không xác định được giá trị cuối.

## 4. Hợp đồng cấu hình theo service

Mỗi service nên công bố một danh mục tham số có thể kiểm tra:

| Key | Kiểu và đơn vị | Giá trị minh họa | Chính sách |
|---|---|---|---|
| `payment.connect-timeout-ms` | Integer, mili giây | 800 | Từ 100 đến 30000 |
| `payment.read-timeout-ms` | Integer, mili giây | 3000 | Từ 100 đến 60000 |
| `payment.max-retries` | Integer | 2 | Từ 0 đến 5, retry theo loại lỗi |
| `payment.provider-base-url` | HTTPS URL | Không có | Required; allowlist host/region |
| `payment.idempotency-enabled` | Boolean | true | Không được tắt ở production |
| `order.event-topic` | String | Không có | Required; topic đúng env |
| `inventory.reserve-ttl-seconds` | Integer, giây | 900 | Phù hợp order lifecycle |
| `observability.log-level` | Enum | INFO | DEBUG production có thời hạn |

Ngoài kiểu và đơn vị, ghi thêm owner, mô tả nghiệp vụ, sensitivity, cách reload, khả năng rollback, điều kiện tương thích và phạm vi ảnh hưởng.

### 4.1. Required hay default?

- **Default an toàn:** thời gian chờ và kích thước pool ở mức hợp lý, không làm tăng quyền.
- **Required/fail fast:** host thanh toán, issuer/audience, tenant policy, topic bắt buộc. Thiếu hoặc sai phải dừng startup/không nhận traffic.
- **Không cho override tùy ý:** các bất biến như bắt buộc authorization, idempotency cho thao tác thu tiền, bảo vệ audit log.
- **Derived:** giá trị tra từ service discovery hoặc metadata đáng tin cậy thay vì copy tay.
- **Secret reference:** key cấu hình trỏ đến định danh bí mật, không chứa nội dung bí mật.

Cần ghi rõ ý nghĩa của `0`, `null` và chuỗi rỗng. Chẳng hạn `timeout=0` có thể nghĩa là ngay lập tức hoặc vô hạn tùy thư viện; một contract phải loại bỏ sự mơ hồ này.

### 4.2. Ràng buộc liên key

Validation từng trường chưa đủ. Nếu API Gateway timeout 4 giây, Order deadline 3,5 giây nhưng Payment read timeout 10 giây với ba lần retry, service sẽ cạn thời gian trước khi kết thúc. Phải kiểm **ngân sách thời gian end-to-end**, tổng số connection khi tăng replica, quota của database, host phù hợp môi trường và điều kiện tương thích schema.

Một quy tắc an toàn cần được thực thi bằng code, test hoặc deployment policy. Chỉ viết “không được tắt auth ở production” trong README chưa tạo ra bảo vệ.

## 5. Quy tắc nguồn và thứ tự ưu tiên

Cùng một key có thể xuất hiện trong source, `application-prod.yaml`, env var, Helm values, Kubernetes ConfigMap và config service. Nếu không quy định precedence, hai người sẽ nhìn hai nguồn khác nhau và nghĩ hệ thống chạy cùng một giá trị.

Một **chính sách ví dụ** cho dự án có thể là:

~~~text
common non-secret defaults
   ↓ override bởi
environment configuration
   ↓ override bởi
region / deployment-cell configuration
   ↓ override bởi
approved release-specific values
   ↓ override trong key cho phép bởi
dynamic config / feature flags
~~~

Đây là precedence do dự án chọn, **không phải thứ tự mặc định của Spring Boot, Helm hay Kubernetes**. Mỗi công cụ có quy tắc riêng; khi kết hợp nhiều công cụ phải kiểm tra thứ tự hiệu lực.

Ví dụ:

| Key | Common | Staging | Prod | Prod/APAC | Hiệu lực Prod/APAC |
|---|---|---|---|---|---|
| `payment.read-timeout-ms` | 3000 | 4000 | 2500 | 2800 | 2800 |
| `payment.max-retries` | 2 | 1 | 2 | — | 2 |
| `observability.log-level` | INFO | DEBUG | INFO | — | INFO |
| `order.event-topic` | Bắt buộc | stg.order.placed | prod.order.placed | prod.apac.order.placed | prod.apac.order.placed |

Dấu “—” là không override. Secret được phân phối qua vòng đời riêng.

### 5.1. Chọn một source of truth

Nếu một tham số đồng thời sửa được bằng GitOps, dashboard runtime và lệnh `kubectl edit`, hệ thống rất dễ drift. Cần:

1. Chỉ rõ nguồn quyền lực cho từng loại key.
2. Giới hạn nơi được phép sửa và người có quyền sửa.
3. Mọi thay đổi đều có revision, owner và audit.
4. Có khả năng xem **effective config đã che bí mật** cùng nguồn từng giá trị.
5. Override khẩn cấp có hạn, sau sự cố phải đồng bộ lại với nguồn chính thức.

## 6. Tổ chức repository

Ví dụ monorepo:

~~~text
repo/
├── services/
│   ├── order-service/
│   │   ├── src/main/resources/application.yaml
│   │   └── src/main/java/.../OrderProperties.java
│   ├── payment-service/
│   │   ├── src/main/resources/application.yaml
│   │   └── src/main/java/.../PaymentProperties.java
│   └── inventory-service/
├── deploy/
│   ├── base/
│   │   ├── order/
│   │   └── payment/
│   └── overlays/
│       ├── dev/
│       ├── staging/
│       └── prod/
│           ├── apac/
│           └── eu/
└── docs/
    ├── configuration-contract.md
    ├── environment-matrix.md
    └── runbooks/config-rollback.md
~~~

Tệp trong service mô tả **khả năng và default an toàn**; manifest/overlay mô tả **môi trường triển khai**. Secret manager chứa secret thật. Một service không tự ý sở hữu và sửa config nội bộ của service khác.

Nếu dùng nhiều repository, mô hình tương đương có thể nằm trong repo deployment riêng. Quan trọng là ownership, khả năng trace version và quy trình promote, không phải tên thư mục chính xác.

## 7. Java/Spring Boot: Typed Configuration

### 7.1. Ví dụ cấu hình non-secret

~~~yaml
spring:
  application:
    name: payment-service

payment:
  connect-timeout-ms: 800
  read-timeout-ms: 3000
  max-retries: 2
  idempotency-enabled: true

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Không hardcode PSP credential trong tệp này; `provider-base-url` được cung cấp qua môi trường/manifest đã kiểm tra, còn API key lấy bằng secret reference.

### 7.2. Bind vào object có kiểu và validation

Ví dụ dùng Spring Boot với Jakarta Bean Validation:

~~~java
package example.payment.config;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
    @Min(100) @Max(30000) int connectTimeoutMs,
    @Min(100) @Max(60000) int readTimeoutMs,
    @Min(0) @Max(5) int maxRetries,
    boolean idempotencyEnabled,
    @NotBlank String providerBaseUrl
) {}
~~~

~~~java
package example.payment;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PaymentApplication {
    public static void main(String[] args) {
        SpringApplication.run(PaymentApplication.class, args);
    }
}
~~~

Cần dependency validation tương ứng. `@NotBlank` chỉ chặn chuỗi rỗng, **chưa chứng minh URL dùng HTTPS hoặc host hợp lệ**; hãy có custom validator/policy cho endpoint và môi trường.

Ví dụ biến môi trường:

~~~text
PAYMENT_CONNECT_TIMEOUT_MS=800
PAYMENT_READ_TIMEOUT_MS=3000
PAYMENT_MAX_RETRIES=2
PAYMENT_IDEMPOTENCY_ENABLED=true
PAYMENT_PROVIDER_BASE_URL=https://payments-sandbox.example.invalid
~~~

Spring Boot hỗ trợ relaxed binding, nhưng phải chạy smoke test với phiên bản framework và môi trường triển khai thực tế để kiểm tra ánh xạ tên và precedence. Đặc biệt tránh im lặng dùng giá trị default khi một biến môi trường viết sai.

### 7.3. Startup validation và readiness

Khởi động service nên theo chuỗi:

~~~text
Load config
  -> bind typed object
  -> check required/ranges
  -> check security invariants
  -> check critical dependency configuration
  -> initialize clients
  -> expose readiness when ready
~~~

Nếu cấu hình bắt buộc sai, fail startup sớm. Với sự cố phụ thuộc tạm thời, cân nhắc readiness không nhận traffic và retry có giới hạn; không dùng fail fast cho mọi trường hợp mà bỏ qua khả năng phục hồi.

## 8. Version code, version cấu hình và release record

Một bản triển khai cần phân biệt:

| Khái niệm | Ví dụ | Điều cần trả lời |
|---|---|---|
| Application version | `payment-service 2.7.3` | Logic code nào chạy? |
| Image digest | `sha256:...` | Chính xác artifact nào được triển khai? |
| Config revision | `git:6f1a2bc` | Bộ non-secret config nào được apply? |
| Config schema version | `4` | Phiên bản code hiểu những key nào? |
| Secret reference version | `psp-api-key:v9` | Đang tham chiếu tới bản secret nào? |
| Feature flag revision | `flags:834` | Rule rollout nào có hiệu lực? |
| Deployment generation | `184` | Instance thuộc đợt rollout nào? |

Giữ **release record** để debug và rollback. Ví dụ:

~~~yaml
release:
  service: payment-service
  appVersion: "2.7.3"
  imageDigest: "sha256:EXAMPLE_REPLACE_WITH_REAL_DIGEST"
  configRevision: "git:6f1a2bc"
  configSchemaVersion: 4
  secretReferenceVersion: "psp-api-key:v9"
  environment: "prod-apac"
  deploymentGeneration: 184
  rollout: "canary"
~~~

Đây là metadata minh họa, không chứa secret thật. Khi triển khai, pin digest hợp lệ thay vì chỉ dựa vào image tag mutable như `latest`.

### 8.1. Tương thích giữa phiên bản code và config

| Thay đổi | Rủi ro | Chiến lược |
|---|---|---|
| Thêm key optional có default an toàn | Thường thấp | Kiểm cả phiên bản cũ/mới |
| Thêm key bắt buộc | Code mới có thể không khởi động | Phân phối config và release theo thứ tự phù hợp |
| Đổi tên key | Code cũ và mới không cùng hiểu | Hỗ trợ cả hai trong giai đoạn chuyển tiếp |
| Đổi đơn vị giây sang mili giây | Sai giá trị 1000 lần | Tạo key mới, migration rõ ràng |
| Đổi ý nghĩa key mà giữ tên | Lỗi ngầm khó phát hiện | Version/schema mới, tránh reuse key |
| Đổi event topic hoặc schema | Producer và consumer mất tương thích | Dual-read/dual-publish hoặc expand-migrate-contract |
| Thu hồi secret version cũ | Pod cũ vẫn dùng và mất quyền | Rotation nhiều giai đoạn |
| Bật flag cho logic dùng schema mới | Data mới có thể không đọc bởi app cũ | Kiểm rollback và dữ liệu được tạo |

Đối với rolling deploy, **hai phiên bản code có thể chạy cùng lúc**. Pipeline không chỉ kiểm config với app mới; còn phải kiểm các pod app cũ sống được đến khi rollout kết thúc.

### 8.2. Expand → Migrate → Contract

Ví dụ v1 dùng `payment.provider-url`, v2 dùng `payment.provider-base-url`:

1. **Expand:** code phiên bản chuyển tiếp hỗ trợ cả tên mới và cũ, có rule ưu tiên rõ; manifest có cả hai nếu cần.
2. **Migrate:** rollout toàn bộ pod sang phiên bản có hỗ trợ tên mới, kiểm effective values.
3. **Contract:** khi không còn instance/job cũ, bỏ tên cũ và validation liên quan.
4. **Rollback:** nếu phải quay về v1, bảo đảm config phục vụ v1 vẫn còn hiệu lực trong thời gian cho phép.

Dùng cách này cả cho schema event, endpoint và dữ liệu khi thay đổi cấu hình kéo theo thay đổi hợp đồng service.

## 9. Kubernetes: ConfigMap, Secret reference và rollout

ConfigMap dành cho cấu hình non-secret. Ví dụ:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: payment-config-v4
  namespace: payment-staging
  labels:
    app: payment-service
data:
  PAYMENT_CONNECT_TIMEOUT_MS: "800"
  PAYMENT_READ_TIMEOUT_MS: "3000"
  PAYMENT_MAX_RETRIES: "2"
  PAYMENT_IDEMPOTENCY_ENABLED: "true"
  PAYMENT_PROVIDER_BASE_URL: "https://payments-sandbox.example.invalid"
~~~

Fragment Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
  namespace: payment-staging
spec:
  replicas: 2
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
      annotations:
        config.example/revision: "git-6f1a2bc"
    spec:
      containers:
        - name: payment
          image: registry.example.invalid/payment-service@sha256:EXAMPLE_DIGEST
          envFrom:
            - configMapRef:
                name: payment-config-v4
          env:
            - name: PSP_API_KEY
              valueFrom:
                secretKeyRef:
                  name: payment-psp-credential
                  key: api-key
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
~~~

Đường image, digest và hostname là placeholder. Fragment tập trung vào cấu hình; deployment production còn cần security context, tài nguyên, policy, liveness, trust, observability và các chi tiết triển khai khác.

### 9.1. Những chi tiết dễ nhầm

- Với **env var**, giá trị được đưa vào container lúc khởi động; sửa ConfigMap không tự thay đổi env đang tồn tại. Cần restart/rollout khi muốn áp dụng.
- Với **ConfigMap mount dạng volume**, kubelet có thể cập nhật file sau độ trễ; ứng dụng vẫn phải đọc lại hoặc reload. Mount bằng `subPath` không nhận cập nhật theo cơ chế thường dùng.
- **Kubernetes Secret không được bảo mật chỉ nhờ base64.** Cần quyền RBAC, bảo vệ etcd/encryption at rest theo môi trường và secret manager khi phù hợp.
- Có thể đặt tên ConfigMap theo phiên bản hoặc cập nhật annotation checksum của Pod template để trigger rollout có thể quan sát. Khi dùng checksum, không đưa giá trị secret ra metadata.
- Nếu GitOps quản lý tài nguyên, sửa trực tiếp bằng `kubectl edit` có thể bị controller ghi đè. Cần nguồn quyền lực và quy trình break-glass rõ.
- Chia ConfigMap theo service/trách nhiệm để đổi Payment không gây rollout ngoài ý muốn cho Order và Inventory.

### 9.2. Helm/Kustomize overlays

Base giữ resource chung, overlay chỉ thay giá trị của môi trường và region. Trong CI, cần render manifest cuối cùng rồi so sánh **effective diff**, vì thay một biến Helm có thể tạo hàng loạt thay đổi Kubernetes không rõ khi chỉ xem template.

Với GitOps, ghi rõ desired revision, revision controller đã sync và revision process thực sự áp dụng. Ba trạng thái này có thể khác nhau trong rollout hoặc khi config reload thất bại.

## 10. Bí mật và secret version

Thay vì lưu API key trong Git, repo giữ **tham chiếu** và secret manager giữ giá trị.

~~~text
Approved config in Git
    └── secret reference: prod/payment/psp-api-key
                     |
                     v
          Workload identity + policy
                     |
                     v
           Secret Manager / audit
                     |
                     v
             Payment Service
~~~

Nguyên tắc:

1. Không commit token, password, private key, signing key hay credential vào repository, image, template hoặc build log.
2. Identity của Payment chỉ đọc secret Payment cần; Notification và Inventory không có quyền, staging không dùng secret production.
3. Tách secret theo service, môi trường, mục đích và khu vực khi cần; tránh credential toàn quyền chia sẻ cho mọi service.
4. Ghi audit actor/workload, secret reference, hành động và thời điểm; không ghi **giá trị** secret.
5. Có rotation, thu hồi, cơ chế khôi phục và kế hoạch xử lý secret đã bị lộ. Xóa secret khỏi commit mới không thu hồi secret đã rò.
6. Quan tâm cả đường lộ qua exception, debug endpoint, trace, metrics label, command history, backup và cấu hình CI.

### 10.1. Cách phân phối secret

| Phương thức | Điểm mạnh | Hạn chế |
|---|---|---|
| Environment variable | Tích hợp đơn giản | Cần restart để đổi, dễ lộ qua dump/debug sai cách |
| Mounted secret file | Tách khỏi env, phù hợp certificate/key file | Cần quyền file, refresh/reload, giới hạn thời gian cập nhật |
| SDK gọi secret manager | Version, audit, identity và rotation rõ | Xử lý lỗi mạng, cache, startup và latency |
| Sidecar/agent/external-secret controller | Tách logic phân phối khỏi app | Tăng thành phần vận hành, cần kiểm quyền và sync |

Không có phương án tối ưu cho mọi hệ thống. Phải chọn theo vòng đời secret, yêu cầu của ứng dụng và mô hình đe dọa.

### 10.2. Ví dụ rotation không ngắt dịch vụ

Giả sử PSP cho phép hai API key hoạt động song song:

1. Tạo secret version mới và kiểm quyền đọc của đúng workload.
2. Cập nhật version reference hoặc logic refresh cho Payment.
3. Rollout từng phần, xác nhận toàn bộ instance và job nền sử dụng key mới.
4. Kiểm tỉ lệ lỗi xác thực, khả năng gọi PSP và kết quả thanh toán.
5. Thu hồi key cũ sau khi chắc chắn không còn consumer, bao gồm region dự phòng.
6. Ghi audit và hoàn tất runbook.

Nếu PSP chỉ cho phép một khóa, cần chiến lược cutover riêng; không tự giả định được overlap.

## 11. Static config, dynamic config và reload

Mỗi key phải có hợp đồng về **khi nào thay đổi có hiệu lực**:

| Loại | Ví dụ | Cách áp dụng thường phù hợp |
|---|---|---|
| Startup-only | Identity issuer, database URL, cấu trúc partition | Restart/rolling deploy |
| Restart-required | Pool size, thread count, client wiring | Tái khởi tạo tài nguyên qua rollout |
| Dynamic-safe | Log level có thời hạn, hạn mức rate limit, feature flag | Config service với schema, audit, rollback |
| Security-critical | Bypass auth, vô hiệu audit, đổi allowlist | Cấm override tùy ý hoặc policy chặt |
| Secret rotation | Credential, certificate | Refresh riêng, kiểm kết nối và expiry |

### 11.1. Vì sao reload từng key có thể nguy hiểm?

Giả sử cấu hình cần cặp `retry.max-attempts=3` và `retry.total-budget-ms=1000`. Nếu nhận cập nhật từng key, service có thể tạm dùng tổ hợp chưa hề được review. Với các key liên quan, nên tải một **snapshot cấu hình nguyên vẹn**, validate tất cả rồi hoán đổi cấu hình một cách nguyên tử cho request mới.

~~~text
onConfigRevision(revision):
    candidate = loadFullSnapshot(revision)
    validateSchema(candidate)
    validateCrossKeyInvariants(candidate)
    validateSecurityPolicy(candidate)
    if candidate is valid:
        publishAtomically(candidate, revision)
        emitConfigApplied(revision)
    else:
        keepLastKnownGood()
        emitConfigRejected(revision, sanitizedReason)
~~~

Phải xác định rõ last-known-good, TTL và hành vi nếu config service không truy cập được. Với thao tác thanh toán và định danh, fallback có thể cần fail closed, tùy bất biến nghiệp vụ và an ninh.

### 11.2. Cấu hình động có thể phân kỳ giữa replica

Khi poll hoặc push, pod A có thể dùng revision 14 còn pod B dùng 13. Có chấp nhận được không? Nếu việc đổi config ảnh hưởng schema event hoặc thuật toán định giá, hai phiên bản chạy song song có thể tạo kết quả trái ngược. Tùy mức rủi ro, chọn one-shot generation, staged rollout, quiesce traffic, sticky cohort hoặc chỉ apply bằng restart.

Luôn ghi applied revision ở từng process, không chỉ “config service đã publish revision”.

## 12. Feature flag: rollout hành vi với phạm vi cụ thể

Feature flag có thể bật checkout mới cho 5% khách hàng, một tenant thử nghiệm hoặc một region. Mẫu khái niệm:

~~~yaml
feature: checkout-v2
owner: order-team
environment: production
default: false
rollout:
  mode: percentage
  percentage: 5
  stableBucketKey: customer-id
safety:
  killSwitch: true
  expiresAfter: "2026-12-31"
~~~

Cú pháp cụ thể tùy flag platform. Điều cần lưu:

- Default an toàn, cùng người dùng được gán vào cohort ổn định.
- Owner và thời hạn xóa; flag đã hoàn thành rollout phải được dọn để giảm nhánh code.
- Audit ai đổi flag, thay cho môi trường, region, cohort nào.
- Tương thích old/new service, schema và dữ liệu trong thời gian rollout.
- Kill switch đã kiểm thử trước sự cố, không dùng để bỏ qua authorization hoặc logging bắt buộc.
- Metric theo cohort/revision để phân biệt lỗi code, flag và backend dependency.

## 13. Pipeline thay đổi cấu hình

~~~mermaid
flowchart TD
    A[Config change in Git] --> B[Pull request and owner review]
    B --> C[Syntax, schema, secret and policy scans]
    C --> D[Render final manifest and diff]
    D --> E[Compatibility and smoke tests]
    E --> F[Deploy dev and staging]
    F --> G[Observe end-to-end behavior]
    G --> H[Approve specific revision]
    H --> I[Canary or rolling production]
    I --> J{Health and invariants hold?}
    J -->|Yes| K[Record release and effective revision]
    J -->|No| L[Stop rollout and rollback]
~~~

### 13.1. Trước khi merge

**Static validation:** parse YAML/JSON, kiểm schema/required/ranges, duplicate keys, URL scheme, secret scanning, tên môi trường, policy quyền, endpoint không bị trỏ lẫn staging/prod.

**Rendered validation:** render Helm/Kustomize; đối chiếu giá trị cuối, resource, Secret/ConfigMap reference, selector và policy, không chỉ diff của template.

**Compatibility validation:** kiểm schema config với image sắp deploy, cả image cũ còn sống trong rolling update; kiểm API/event topic và ngân sách timeout giữa các service.

**Security validation:** cấm tắt các bất biến bảo mật, không có secret thật trong artifact/log, kiểm quyền đọc theo workload và môi trường.

**Operational validation:** có owner, change ID, kế hoạch canary, metric và rollback; kiểm ngay ở staging nơi có môi trường gần production.

### 13.2. Promote không đồng nghĩa copy môi trường

Dùng cùng artifact đã kiểm tra khi promote nếu phù hợp, nhưng mỗi môi trường lấy endpoint và secret **riêng**. Không copy nguyên `.env` staging sang production. Release record cần xác định rõ cặp image/config version cho từng môi trường.

Ví dụ:

| Service | Code version | Schema version | Config staging | Config production |
|---|---|---:|---|---|
| Order | 2.4.0 | 3 | git:a81... | git:b14... |
| Payment | 2.7.3 | 4 | git:de2... | git:6f1... |
| Inventory | 1.9.1 | 2 | git:cb7... | git:d08... |

Hai môi trường có config revision khác nhau là điều bình thường. Điều cần kiểm tra là policy, contract và khả năng giải thích mọi khác biệt quan trọng.

## 14. Cấu hình phải tính tác động liên service

Timeout, retry và concurrency thường được tối ưu riêng từng service, nhưng phụ thuộc chồng nhau trong request. Ví dụ ngân sách minh họa:

~~~text
Client deadline:                     8,000 ms
API Gateway timeout:                7,500 ms
Order local work:                   1,000 ms
Payment call budget:                3,000 ms
Inventory reservation:              2,000 ms
Network/serialization/other:        1,500 ms
~~~

Nếu Payment retry 3 lần, mỗi lần timeout 3 giây, nó có thể vượt deadline toàn luồng. Cần deadline propagation, backoff có giới hạn, phân biệt request idempotent và non-idempotent. Cùng logic này áp dụng cho:

- Connection pool giữa nhiều replica so với DB max connections.
- Quota và rate limit giữa Gateway, service và PSP.
- Tên topic, group ID, DLQ, retention và schema khi chuyển môi trường/phiên bản.
- Region và DNS khi failover; credential region mới có được cấp quyền không.
- Cache TTL và invalidation khi key/config schema đổi.

Không chấp nhận một config value chỉ vì service khởi động được; cần kiểm bất biến trên đường đi end-to-end.

## 15. Cấu hình nhiều region, cell và tenant

Với hệ thống nhiều region, nên phân loại:

- **Chung toàn hệ thống:** chính sách bảo mật, contract chung, schema version.
- **Theo region:** endpoint, nơi lưu dữ liệu, độ trễ, zone, bản sao dữ liệu, secret region.
- **Theo cluster/cell:** namespace, service discovery, quota, deployment generation.
- **Theo service:** timeout, broker topic, pool, dependency và credential.
- **Theo tenant:** quyền, quota hoặc tùy chỉnh nghiệp vụ; thường nên lưu trong domain policy store có authorization, thay vì tạo vô số ConfigMap thủ công.

Một thay đổi global được áp dụng đồng thời toàn fleet có thể gây outage toàn cầu. Khi blast radius lớn, dùng staged rollout theo vùng/cell, so sánh metric và chỉ mở rộng khi điều kiện đạt.

Tenant configuration cần validation, audit và giới hạn theo tài khoản; không dùng tenantId do client tự khai làm nguồn tin cậy cho quyết định policy.

## 16. Effective config, audit và phát hiện drift

Mỗi instance nên công bố metadata **đã loại bỏ bí mật** để người vận hành trả lời: “Pod này đang chạy revision nào?”

~~~json
{
  "service": "payment-service",
  "environment": "prod-apac",
  "appVersion": "2.7.3",
  "imageRevision": "sha256:EXAMPLE",
  "configSchemaVersion": 4,
  "configRevision": "git:6f1a2bc",
  "featureFlagRevision": "flags:834",
  "secretReferenceVersion": "psp-key:v9",
  "configStatus": "APPLIED"
}
~~~

Tránh xuất raw secret hoặc giá trị nhạy cảm; nếu hash config, chỉ hash cấu hình non-secret chuẩn hóa. Hash các bí mật ít entropy có thể lộ manh mối về giá trị.

Phân biệt:

- **Desired revision:** revision trong Git/config service đã được phê duyệt.
- **Synced revision:** controller triển khai đã nhận revision nào.
- **Applied revision:** process thực sự dùng revision nào.
- **Effective configuration:** giá trị sau precedence và runtime flag, đã mask phần nhạy cảm.

Drift xảy ra khi các trạng thái lệch nhau vì rollout dang dở, pod cũ, cập nhật thủ công, refresh thất bại hoặc dynamic override còn hiệu lực.

Nên cảnh báo khi: replica cùng release dùng revision khác ngoài dự kiến; staging endpoint xuất hiện ở prod; secret version hết hạn; override quá TTL; config liên tục bị GitOps ghi đè; lỗi tăng ngay sau thay đổi.

Log các sự kiện `config_requested`, `config_validated`, `config_applied`, `config_rejected`, `config_rolled_back` kèm revision, actor, thời gian và lý do được sanitize. Không dùng giá trị secret, raw token hoặc tenant ID không giới hạn làm metric labels.

## 17. Rollout và rollback có kiểm soát

### 17.1. Runbook: đổi timeout Payment ở production

1. Ghi change ID, mục tiêu, service owner và phạm vi ảnh hưởng.
2. Tính lại deadline và retry budget của checkout; kiểm quota PSP.
3. Sửa source of truth qua PR, review và static validation.
4. Render diff cấu hình hiệu lực, xác định các tham số liên quan.
5. Deploy staging với test lỗi mạng/PSP timeout.
6. Promote revision cụ thể và canary một phần fleet, theo region/cell nếu cần.
7. Quan sát p95/p99 latency, rate timeout, payment error rate, retry count, queue depth và metric nghiệp vụ.
8. Nếu vượt ngưỡng, dừng rollout và rollback về release/config revision đã được xác nhận an toàn.
9. Xác nhận **process đã thực sự áp dụng revision cũ** và không còn pod lỗi; ghi audit.

### 17.2. Tại sao rollback config chưa chắc đảo được hậu quả?

Nếu một thay đổi đã ghi dữ liệu sang database khác, phát message schema mới, bật migration, thu hồi secret cũ hoặc tạo side effect ở PSP, chỉ revert Git commit không khôi phục trạng thái ban đầu. Cần kế hoạch forward fix, dual-read/write, đối soát hoặc migration ngược có kiểm soát.

Do đó change quan trọng phải ghi rõ: có đảo ngược được không, điều kiện rollback, dữ liệu đã thay đổi, dependency ảnh hưởng và cách xác nhận hệ thống an toàn sau rollback.

## 18. Tình huống sự cố: production gọi nhầm PSP sandbox

Giả sử sau deploy, Payment Service trả lỗi khi checkout; staging vẫn chạy tốt. Cách điều tra:

1. Phân vùng sự cố: pod mới/cũ, một region/toàn vùng, một payment method/tất cả.
2. Tra image digest, config revision, secret ref version, feature flag revision và deployment generation.
3. So sánh effective config đã che secret: provider URL, issuer/audience, timeout và network egress.
4. Kiểm startup validation, readiness, lỗi 401/403 từ PSP, chứng cứ từ audit và runtime config.
5. Dừng canary, rollback revision nếu hợp lệ; bảo đảm endpoint prod không trỏ sandbox.
6. Xác nhận toàn bộ replica dùng revision mong muốn; đối soát giao dịch ở trạng thái chưa rõ để tránh duplicate charge.
7. Bổ sung policy chặn host sandbox trong production và test tương thích nếu thiếu.

| Triệu chứng | Giả thuyết nên kiểm |
|---|---|
| Chỉ pod mới lỗi | Config revision, secret injection hoặc startup khác |
| Chỉ một region lỗi | DNS, egress, endpoint/credential theo region |
| PSP báo 401/403 | Secret sai/hết hạn, identity hoặc quyền |
| Timeout cao, auth bình thường | Retry budget, DNS/TLS, saturation, endpoint |
| Broker backlog tăng | Topic, consumer group, retry, poll, concurrency |
| Revert Git nhưng lỗi còn | Pod chưa restart, dynamic override, secret đã thu hồi |

## 19. Sai lầm phổ biến

**Một file .env chung cho mọi môi trường.** Dễ copy credential sai và không có audit. Dùng `.env.example` chỉ với tên biến/giá trị giả, secret riêng theo môi trường và quy tắc không commit file local.

**Hardcode mọi config trong code.** Thay tham số nhỏ phải build lại; khó promote cùng artifact. Tách giá trị thay đổi khỏi logic, nhưng giữ validation và bất biến bảo mật ở ứng dụng.

**Nhiều lớp override không kiểm soát.** Xem YAML thấy 3 giây nhưng pod chạy 30 giây. Công bố precedence, giới hạn nguồn và xuất effective revision/value đã mask.

**Tin rằng sửa ConfigMap là process tự reload.** Với env vars, thường phải rollout; với volume, app cần cơ chế đọc lại. Xác nhận applied revision tại process.

**Commit Kubernetes Secret dạng base64.** Base64 không phải mã hóa bí mật. Dùng secret manager hoặc quy trình bảo vệ phù hợp, hạn chế quyền và bảo vệ backup.

**Cho phép startup khi thiếu key bảo mật.** Dễ fallback nhầm staging/prod hoặc vô hiệu chức năng quan trọng. Fail fast với các key bắt buộc.

**Rollback code mà quên config.** Code cũ có thể không hiểu schema mới. Lưu cặp artifact–config và compatibility matrix.

**Credential dùng chung toàn bộ microservices.** Một service bị lộ kéo theo mọi service. Phân quyền theo workload, service và môi trường, rotation riêng.

**Chỉnh production thủ công rồi không cập nhật Git.** Tạo drift, audit thiếu và bị GitOps ghi đè. Dùng break-glass có hạn và reconcile lại nguồn chính thức.

**Feature flag sống mãi.** Tăng tổ hợp code khó test. Có owner, expiry, metric và cleanup.

## 20. Bài tập

### Bài A — Hợp đồng cho Order Service

Danh sách key: `ORDER_TOPIC`, `PAYMENT_URL`, `ORDER_RETRY_MAX`, `INVENTORY_TIMEOUT_MS`, `AUTH_ISSUER`, `AUTH_AUDIENCE`.

Lập bảng type/unit, required/default, owner, scope, validation và cơ chế apply. Chỉ ra key cần fail fast, key liên quan security và các ràng buộc liên service.

### Bài B — Ba môi trường

Thiết kế common + dev/staging/prod overlay cho Payment. Tạo sơ đồ nguồn của từng key, dùng secret reference khác nhau, đề xuất test chặn staging kết nối production và xác định thứ tự override.

### Bài C — Schema version và rolling deploy

Payment v1 dùng `payment.provider-url`; v2 dùng `payment.provider-base-url`. Trình bày expand–migrate–contract khi hai phiên bản cùng chạy; nêu cả cách rollback sang v1 sau rollout một phần.

### Bài D — Configuration drift

Hai pod cùng image digest nhưng timeout lần lượt 3 giây và 30 giây. Git chỉ có 3 giây. Hãy liệt kê cách kiểm env var, mounted file, generation, dynamic config, startup log, checksum annotation và thời điểm restart; đề xuất cảnh báo trước khi xảy ra sự cố.

### Bài E — Rotation secret

PSP cho phép hai API key cùng hoạt động trong 24 giờ. Lập trình tự tạo key mới, phân phối, rollout, xác nhận các job nền/region DR, thu hồi key cũ và xử lý rollback nếu một vùng vẫn dùng phiên bản cũ.

## 21. Checklist triển khai thật

- [ ] Phân loại rõ non-secret config, secret, feature flags, business data và hạ tầng.
- [ ] Mỗi key quan trọng có owner, type/unit, scope, required/default, validation và cách apply.
- [ ] Dev/staging/prod dùng identity, database, endpoint, secret tách biệt; có policy chặn nhầm môi trường.
- [ ] Có precedence xác định được và kiểm thử hiệu quả giá trị cuối.
- [ ] Mỗi release có image digest, config revision, schema version, secret reference version và generation.
- [ ] CI kiểm syntax, schema, security invariant, secret leak và rendered diff.
- [ ] Tương thích rolling deploy của old/new code, event/API và schema cấu hình được kiểm.
- [ ] Secret có quyền đọc tối thiểu, rotation, audit, không lộ vào Git/log/metrics.
- [ ] Xác định key nào cần restart, key nào reload được và cách xử lý cập nhật thất bại.
- [ ] Có canary/rollback và xác nhận applied revision trên từng instance.
- [ ] Có dashboard và cảnh báo configuration drift, override quá hạn, secret version cũ.
- [ ] Feature flags có owner, thời hạn, default an toàn và chiến lược gỡ bỏ.
- [ ] Đã diễn tập cấu hình sai, rollback và rotation một secret quan trọng.

## 22. Kết luận

Quản lý cấu hình theo môi trường và phiên bản là **quản lý hợp đồng vận hành** giữa application, nền tảng triển khai và các service phụ thuộc. Một hệ thống được quản lý tốt phải biết giá trị nào đang hiệu lực, nguồn nào tạo ra nó, phiên bản nào tương thích, ai có quyền đổi, khi nào process áp dụng và làm sao quay lại trạng thái an toàn. Git/ConfigMap/Helm/secret manager là phương tiện; tính đúng đắn được quyết định bởi schema, phân quyền, kiểm tra end-to-end, release record, observability và rollback có thể chứng minh.
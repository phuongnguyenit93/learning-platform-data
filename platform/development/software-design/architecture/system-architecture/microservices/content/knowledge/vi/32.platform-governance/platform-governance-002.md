# Mẫu dịch vụ và những cấu hình mặc định cần thiết

## 1. Mục tiêu

Khi một tổ chức có hàng chục hoặc hàng trăm Microservices, việc mỗi nhóm tự khởi tạo ứng dụng, chọn thư viện, viết Dockerfile, cấu hình log, định nghĩa health check và tạo pipeline CI/CD theo cách riêng sẽ dẫn tới các hệ quả quen thuộc:

- Một service có tracing nhưng không propagate trace context; service khác chỉ ghi log text không thể tìm theo request.
- Có service bật HTTPS, giới hạn timeout và quản lý secrets đúng cách; service khác vô tình dùng cấu hình phát triển ở production.
- Mỗi nhóm đặt tên metrics, route, lỗi API và environment khác nhau, làm dashboard và on-call thiếu nhất quán.
- Cùng một vấn đề bảo mật hoặc dependency phải được vá riêng ở rất nhiều repository.
- Nhân sự mới mất nhiều ngày chỉ để tạo bộ khung, triển khai môi trường và biết phải tìm tài liệu ở đâu.
- Một bản phát hành qua CI thành công nhưng thiếu readiness, graceful shutdown hoặc rollback, gây gián đoạn khi chạy thật.

**Mẫu dịch vụ (service template)** là bộ khung và hợp đồng mặc định giúp nhóm phát triển tạo dịch vụ mới theo một **golden path** đã được nền tảng hỗ trợ: có cấu trúc repository, cấu hình chạy, khả năng quan sát, kiểm thử, bảo mật, triển khai và thông tin sở hữu ngay từ đầu.

Một template tốt không biến mọi dịch vụ thành bản sao cứng nhắc. Nó cung cấp **mặc định an toàn, có thể kiểm chứng và dễ tùy chỉnh trong ranh giới rõ ràng**, để nhóm sản phẩm tập trung vào logic nghiệp vụ thay vì lặp lại công việc nền tảng.

Sau bài học, người đọc có thể:

1. Phân biệt service template, scaffold, starter/library và nền tảng self-service.
2. Xác định những cấu hình cần bắt buộc ở mức tổ chức, những giá trị phải lấy từ workload thực và những phần tùy chọn.
3. Thiết kế skeleton Java/Spring Boot cho một dịch vụ HTTP hoặc message consumer.
4. Đặt chuẩn về API, validation, errors, idempotency và data ownership.
5. Chuẩn hóa cấu hình môi trường, secret management và identity.
6. Đưa logs, metrics, distributed traces, SLI/SLO, probes và runbook vào mặc định.
7. Thiết kế container, Kubernetes manifests, autoscaling, rollout và graceful shutdown.
8. Xây CI/CD với kiểm thử, kiểm tra bảo mật, provenance, policy và rollback.
9. Quản trị phiên bản template, ownership, ngoại lệ và khả năng nâng cấp cho các service đã sinh ra.
10. Đánh giá hiệu quả nền tảng qua thời gian tạo service, độ tin cậy và công sức bảo trì.

Bối cảnh là Software Design, System Architecture và Microservices, với ví dụ chủ yếu ở Java/Spring Boot, container và Kubernetes. Các YAML/Java/Dockerfile bên dưới là **mẫu giải thích**, phải điều chỉnh và kiểm tra với phiên bản framework, nền tảng, chính sách bảo mật và tải thực trước khi chạy production.

## 2. Service template khác gì một ứng dụng mẫu?

Một repository demo thường cho thấy cách chạy một endpoint trả Hello World. Service template cần giải quyết **vòng đời lâu dài** của một service.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Template/scaffold | Tạo repository mới và điền tên/metadata | catalog-service với Maven, src, deploy, docs |
| Starter/library | Đóng gói code dùng chung để nhiều service cập nhật theo dependency version | HTTP client defaults, logging/tracing config |
| Platform capability | Dịch vụ nền tảng được vận hành tập trung | Kubernetes, secret manager, API Gateway, telemetry backend |
| Golden path | Quy trình được khuyến nghị và hỗ trợ đầu-cuối | Create → build → test → deploy → observe → operate |
| Policy/guardrail | Giới hạn hoặc kiểm tra bắt buộc | Không dùng image chạy root, không hardcode secret |
| Service catalog | Tập trung metadata và ownership | Owner, repository, runbook, SLO, tier |
| Reference implementation | Ví dụ chạy được, minh họa contract | Service HTTP cùng một consumer mẫu |

Nếu sao chép toàn bộ logging, retry và security code vào mỗi repo, việc sửa sau này sẽ khó vì các bản copy tách rời. Template chỉ phù hợp cho **khung khởi tạo và những quyết định tại thời điểm sinh repo**. Logic cần cập nhật đồng loạt thường nên nằm trong **thư viện/starter có version rõ** hoặc cơ chế platform được vận hành tập trung.

Ngược lại, một starter quá lớn tự động thêm mọi dependency, filter và annotation cũng khiến service khó hiểu, khó nâng cấp. Nên ưu tiên **module nhỏ, chức năng rõ, có cấu hình và tài liệu**.

## 3. Nguyên tắc của golden path

Một golden path tốt thường có các thuộc tính:

- **Dễ đi theo hơn đi đường vòng:** một vài thao tác tạo service chạy được, deploy được và có telemetry.
- **Secure by default:** không bật debug endpoints nguy hiểm hoặc secret trong mã.
- **Observable by default:** có metrics, logs, traces, health checks và deployment metadata.
- **Operable by default:** có ownership, alerts, runbook, rollout/rollback và capacity baseline.
- **Có ranh giới rõ:** contract API/data và quyền truy cập được định nghĩa.
- **Có escape hatch:** workload đặc biệt được chọn cấu hình khác qua quy trình ngoại lệ minh bạch.
- **Tự phục vụ được:** nhóm ứng dụng không phải mở nhiều ticket để tạo service cơ bản.
- **Có đường nâng cấp:** template/starter thay đổi, các service có thể nhận fix mà không phải viết lại dự án.
- **Được đo bằng kết quả:** giảm thời gian tạo repo/triển khai, giảm lỗi cấu hình và giảm sự cố lặp.

**Golden path không phải một quy định tuyệt đối rằng mọi service phải dùng cùng database hoặc cùng chiến lược autoscaling.** Những mặc định phụ thuộc loại workload cần được gắn với service profile.

## 4. Phân loại mặc định: bắt buộc, tùy theo workload, tùy chọn

Nên tách rõ ba mức để tránh biến template thành gánh nặng.

| Mức | Ví dụ | Cách quản trị |
|---|---|---|
| **Bắt buộc / guardrail** | Owner, secret không hardcode, non-root container, tracing correlation, artifact provenance, vulnerability checks | Kiểm tra trong pipeline và policy; ngoại lệ có phê duyệt |
| **Theo service profile** | HPA target, resource requests, DB pool, retry policy, queue concurrency, SLO ngưỡng | Có giá trị khởi đầu nhưng phải hiệu chỉnh từ workload |
| **Tùy chọn / opt-in** | Scheduler, Kafka consumer, cache, search, batch processing, gRPC, GraphQL | Chỉ thêm khi nhu cầu nghiệp vụ thực sự tồn tại |

Ví dụ **request timeout** phải có trong mọi service gọi dependency, nhưng giá trị 500 ms hay 3 giây không thể dùng chung máy móc. Cần budget theo end-to-end deadline và đặc tính dependency.

Một template nên tránh hai cực đoan: bỏ trống mọi cấu hình khiến nhóm tự đoán, hoặc nhúng hàng trăm tùy chọn vào repo mới khiến không ai hiểu giá trị đang có tác dụng.

## 5. Metadata tối thiểu trước khi tạo service

Scaffold cần một số thông tin ở thời điểm tạo, không dựa vào tên repo để suy đoán:

| Trường | Ví dụ | Mục đích |
|---|---|---|
| service_name | catalog-service | Tên logic ổn định cho catalog/telemetry |
| domain | product-catalog | Ngữ cảnh nghiệp vụ |
| team_owner | catalog-team | Nhóm chịu trách nhiệm |
| operational_tier | tier-2 | Mức yêu cầu vận hành theo chính sách |
| runtime_profile | java-http | Bộ mặc định phù hợp workload |
| repository | org/catalog-service | Nguồn mã |
| api_style | rest | Kiểu giao tiếp |
| data_store | postgres | Chỉ bật dependency cần thiết |
| environment_targets | dev, staging, production | Những môi trường quản lý |
| contact/on_call | đường dẫn nhóm trực | Điều phối sự cố |
| data_classification | internal | Phân quyền, retention |
| cost_center | product-platform | Quản lý chi phí nếu tổ chức sử dụng |

Tên metric service.name, image, repository, Kubernetes labels, service catalog và dashboard phải dẫn về **cùng một service identity**. Không để catalog gọi catalog-service, traces gọi inventory-api và deployment gọi product-backend vì copy-paste.

Tên hiển thị có thể khác tên kỹ thuật, nhưng mapping phải rõ.

## 6. Cấu trúc repository mẫu

Một service Java/Spring Boot có thể bắt đầu bằng:

~~~text
catalog-service/
├── README.md
├── pom.xml
├── mvnw
├── .mvn/
├── .gitignore
├── .editorconfig
├── .dockerignore
├── Dockerfile
├── .github/
│   ├── workflows/
│   │   ├── ci.yml
│   │   └── release.yml
│   └── CODEOWNERS
├── src/
│   ├── main/
│   │   ├── java/com/example/catalog/
│   │   │   ├── CatalogApplication.java
│   │   │   ├── api/
│   │   │   ├── application/
│   │   │   ├── domain/
│   │   │   ├── infrastructure/
│   │   │   └── configuration/
│   │   └── resources/
│   │       ├── application.yaml
│   │       ├── db/migration/
│   │       └── logback-spring.xml
│   └── test/
│       ├── java/
│       └── resources/
├── deploy/
│   ├── base/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── hpa.yaml
│   │   └── kustomization.yaml
│   └── overlays/
│       ├── dev/
│       ├── staging/
│       └── production/
├── api/
│   └── openapi.yaml
├── docs/
│   ├── architecture.md
│   ├── runbook.md
│   ├── operations.md
│   ├── decisions/
│   └── slos.md
└── scripts/
    ├── local-up.sh
    └── smoke-test.sh
~~~

Có thể dùng Gradle, Helm hoặc một mono-repo nếu tổ chức đã chuẩn hóa. Không cần đồng thời tạo Maven và Gradle, Helm và Kustomize, hoặc nhiều CI providers cho một service. **Một đường mặc định chạy được** tốt hơn nhiều bộ cấu hình gần giống nhau.

### 6.1. Phân lớp code

- **api:** controllers, request/response DTOs, validation, error mapping, API contract.
- **application:** use cases, transaction boundaries, orchestration.
- **domain:** entities/value objects, invariants, policies nghiệp vụ.
- **infrastructure:** persistence adapters, HTTP clients, messaging, cache.
- **configuration:** wiring, settings validation, telemetry và security.

Phân lớp này không bắt buộc cho mọi service nhỏ, nhưng giúp domain code không phụ thuộc trực tiếp vào framework/HTTP/DB và dễ kiểm thử. Tránh tạo hàng chục abstract classes chỉ để đúng sơ đồ.

## 7. Chọn service profile trước khi sinh cấu hình

Một template có thể cung cấp nhiều profile:

| Profile | Mục đích | Mặc định đáng chú ý |
|---|---|---|
| java-http | REST/gRPC API phục vụ người dùng | Readiness, timeouts, HTTP metrics, request validation |
| java-worker | Consumer hàng đợi | Ack/retry/DLQ, idempotency, shutdown drain |
| java-scheduler | Tác vụ định kỳ | Concurrency/leader election, job history |
| java-batch | Batch hữu hạn | Checkpoint, retries, deadline, Job controller |
| java-streaming | Xử lý stream có state | Lag, partition ownership, checkpoint/recovery |
| java-library | Thư viện dùng chung | Không tạo Deployment, kiểm tra API compatibility |
| gateway-adapter | Kết nối bên thứ ba | Quota, circuit breaker, credential rotation |

Không ép worker có cùng probes, HTTP port, HPA CPU target và routing như API. Cũng không bật Kafka/PostgreSQL/Redis mặc định nếu service không dùng. Mọi thành phần mới tăng chi phí vận hành và bề mặt bảo mật.

## 8. Cấu hình ứng dụng: externalized, typed và kiểm tra từ đầu

Cấu hình khác nhau theo môi trường nên được cung cấp từ môi trường runtime, config service, Kubernetes ConfigMap hoặc secret manager, thay vì hardcode.

Nhóm cấu hình thường gặp:

- service identity và environment.
- HTTP port, server timeouts, graceful shutdown.
- Endpoint của dependency và connection pool.
- Retry/backoff/circuit breaker/bulkhead.
- Metrics/traces/log sampling.
- Database pool/migration, nếu có.
- Feature flags, rollout cohorts.
- Business constraints không nhạy cảm.
- Secrets và credentials chỉ qua kênh bảo mật.

Ví dụ application.yaml cho profile HTTP:

~~~yaml
spring:
  application:
    name: catalog-service
  lifecycle:
    timeout-per-shutdown-phase: 25s
  threads:
    virtual:
      enabled: false

server:
  port: 8080
  shutdown: graceful

management:
  server:
    port: 8081
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,prometheus

app:
  http:
    upstream-connect-timeout: 500ms
    upstream-response-timeout: 2s
  pagination:
    max-page-size: 100
~~~

Đây là cấu hình mẫu. Tên property, hỗ trợ virtual threads và actuator endpoints tùy Spring Boot version/dependencies; những thuộc tính chưa có hiệu lực trong runtime đang dùng cần được xác nhận trước production. Không tự bật mọi management endpoint ở Internet.

### 8.1. Typed configuration

Một cách để không rải giá trị magic string trong code là bind vào đối tượng cấu hình:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

@Validated
@ConfigurationProperties(prefix = "app.http")
public record UpstreamHttpProperties(
    @NotNull Duration upstreamConnectTimeout,
    @NotNull Duration upstreamResponseTimeout
) {}

@Validated
@ConfigurationProperties(prefix = "app.pagination")
public record PaginationProperties(
    @Min(1) @Max(1000) int maxPageSize
) {}
~~~

Cần enable configuration properties scanning/binding theo dự án. Với property không có binding hoặc validation sai, **fail fast lúc startup** để tránh service chạy với một mặc định nguy hiểm mà người vận hành không biết.

Không thay sự quản trị cấu hình bằng cách đặt default cho secret rỗng rồi cho service tiếp tục hoạt động với quyền bất định.

### 8.2. Mô hình ưu tiên cấu hình

Quy định rõ nguồn nào có quyền ghi đè, ví dụ:

~~~text
Artifact defaults (an toàn, không chứa secret)
          |
          v
Environment config / ConfigMap
          |
          v
Secret manager / mounted secret
          |
          v
Documented rollout-specific overrides
~~~

Hệ thống framework có thứ tự precedence riêng; cần ghi rõ thứ tự thực tế và tránh trộn command-line, system properties và file theo cách khó truy dấu. Mỗi thay đổi config production nên có audit record/config revision; version code có thể không đổi nhưng hành vi thay đổi đáng kể.

## 9. Secret management: tuyệt đối không mặc định secret cố định

Những giá trị như DB password, API token, private key, signing secret hoặc OAuth client secret không nên đặt trong:

- application.yaml được commit vào Git.
- Dockerfile với ENV chứa secret.
- CI logs hoặc artifact metadata công khai.
- URL query parameter.
- Exception message và structured logs.
- Kubernetes ConfigMap không có kiểm soát truy cập phù hợp.
- Ví dụ tài liệu có secret thật.

Một hướng mặc định:

1. Nguồn secret là secret manager hoặc cơ chế tích hợp tổ chức.
2. Service có workload identity/service account với quyền tối thiểu.
3. Secret được inject qua file mount hoặc cơ chế được chấp thuận.
4. Có version/rotation policy và khả năng reload/restart phù hợp.
5. Quyền đọc chỉ cấp cho namespace/workload cần dùng.
6. Logs và traces redaction thông tin nhạy cảm.
7. Production không có fallback sang credential phát triển.

Kubernetes Secret không mặc nhiên bảo đảm mã hóa at rest hoặc least privilege; điều đó phụ thuộc cấu hình cluster, RBAC, KMS và quy trình. Template nên sử dụng cách tích hợp secret của platform thay vì yêu cầu mỗi team tự chọn.

## 10. Authentication và authorization phải có ranh giới rõ

Một service cần biết **người gọi là ai** và **người đó có được thực hiện hành động trên tài nguyên cụ thể hay không**.

- Authentication: xác minh principal, workload identity hoặc token.
- Authorization: áp dụng scope/role, tenant boundary và các quy tắc theo tài nguyên.
- Service-to-service: ưu tiên workload identity/mTLS hoặc token có audience/scope phù hợp tùy nền tảng.
- User-facing: xác thực qua gateway/identity provider, nhưng dịch vụ sở hữu dữ liệu vẫn cần kiểm tra quyền nghiệp vụ.
- Audit: ghi kết quả từ chối quyền với ID có kiểm soát, không ghi raw token.

**Gateway đã xác thực không thay thế authorization tại service sở hữu dữ liệu**. Ví dụ GET /orders/123 phải kiểm tra đơn đó thuộc principal/tenant có quyền xem, không chỉ kiểm tra có JWT.

Các default nên có:

- Deny by default cho đường không được public.
- Một danh sách endpoint public được khai báo rõ.
- Token validation gồm issuer, audience, expiry, signature theo contract.
- Không tin X-User-Id hoặc X-Tenant-Id do client tự gửi trừ khi được gateway tin cậy ký/xác nhận theo kiến trúc.
- Có cơ chế tách service identity và end-user identity.
- Kiểm tra truy cập cấp resource và tenant.
- Không sử dụng authorization bằng tên route đơn thuần khi domain policy phức tạp.
- Security tests cho 401/403, tenant isolation và direct object access.

Template không thể đoán mọi quy tắc nghiệp vụ, nên cung cấp **extension points cho domain policy** và test helpers thay vì hardcode một role ADMIN có quyền tất cả.

## 11. API contract: nhất quán mà không làm nghèo nghiệp vụ

Mẫu HTTP API nên cung cấp:

- OpenAPI specification và đường quản lý version.
- Route naming và HTTP semantics.
- Request validation tại boundary.
- Response/error contract thống nhất.
- Correlation/request ID, trace context.
- Pagination/filtering/sorting có giới hạn.
- Deadline/timeout và giới hạn kích thước payload.
- Khả năng xử lý idempotent requests khi cần.
- Compatibility rules và deprecation process.
- Test contract và schema.

### 11.1. Dùng HTTP status đúng nghĩa

Một số ví dụ:

| Mã | Ý nghĩa điển hình | Lưu ý |
|---|---|---|
| 200 | Truy vấn/cập nhật thành công có body | Không thay cho mọi kết quả nghiệp vụ |
| 201 | Tạo resource | Có thể kèm Location |
| 202 | Đã chấp nhận xử lý async | Không đồng nghĩa job hoàn tất |
| 204 | Thành công không cần body | Không gửi body giả |
| 400 | Request không hợp lệ về cú pháp/semantics đầu vào | Mô tả rõ lỗi |
| 401 | Chưa xác thực hợp lệ | Không lộ token |
| 403 | Đã biết principal nhưng không đủ quyền | Không tiết lộ tài nguyên nhạy cảm |
| 404 | Resource không tìm thấy hoặc theo policy che giấu | Phải nhất quán |
| 409 | Conflict với trạng thái hiện tại | Ví dụ cập nhật version cũ |
| 422 | Không xử lý được nội dung hợp lệ về cú pháp | Theo API contract |
| 429 | Vượt rate limit | Có thể dùng Retry-After |
| 500 | Lỗi không mong đợi của server | Dùng error correlation |
| 503 | Tạm không thể phục vụ | Không che thành HTTP 200 |

Một template có thể hỗ trợ kiểu Problem Details cho lỗi HTTP, nhưng không đè toàn bộ lỗi domain thành một mã 500.

### 11.2. Ví dụ problem response

~~~json
{
  "type": "https://api.example.invalid/problems/invalid-page-size",
  "title": "Invalid page size",
  "status": 400,
  "detail": "pageSize must be between 1 and 100",
  "instance": "/catalog/items",
  "traceId": "example-trace-id"
}
~~~

Trace ID là một extension field minh họa, không phải field chuẩn bắt buộc của Problem Details. Không đưa stack trace, SQL statement hoặc credential vào body production.

### 11.3. Validation tại biên

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateCatalogItemRequest(
    @NotBlank String sku,
    @NotBlank String displayName,
    @Min(0) @Max(1000000000) long priceMinor
) {}
~~~

Validation cơ bản bảo vệ shape/range đầu vào. Domain phải tiếp tục kiểm tra các invariant như SKU unique, currency hợp lệ, quyền thao tác và state transition. Giá tiền nên dùng kiểu đơn vị rõ (minor units/Decimal theo contract), không dùng float tùy tiện.

## 12. Pagination và bảo vệ tài nguyên

Một mặc định nên giới hạn lượng dữ liệu trả về:

~~~text
GET /catalog/items?pageSize=50&cursor=opaque-token
~~~

Gợi ý:

- Max page size có giới hạn được document.
- Cursor-based pagination phù hợp với tập dữ liệu lớn/thay đổi liên tục khi thiết kế đúng.
- Đảm bảo ordering ổn định và cursor không cho phép vượt quyền tenant.
- Không chấp nhận sort theo trường bất kỳ nếu tạo query không có index.
- Query timeout, body size và search complexity phải có ngân sách.
- Với export lớn, dùng asynchronous jobs và object storage thay vì một HTTP request giữ mở nhiều phút.

Không tạo default trả toàn bộ bảng khi request không truyền limit. Một API ban đầu chỉ có 100 hàng có thể trở thành triệu hàng sau vài năm.

## 13. Idempotency và tính đúng đắn giao dịch

POST không tự idempotent. Trong hệ phân tán, client timeout có thể xảy ra **sau khi server commit thành công nhưng trước khi client thấy response**. Khi client retry, cùng một thao tác có thể được thực hiện hai lần.

Với operation tạo đơn hoặc thanh toán, template nên cung cấp hướng dẫn hỗ trợ idempotency key:

~~~text
Client:
  POST /orders
  Idempotency-Key: 9bd6-example

Service:
  1. Xác thực người gọi và scope
  2. Kiểm tra key trong phạm vi tenant/principal
  3. Kiểm tra payload fingerprint nếu key đã tồn tại
  4. Nếu đã hoàn tất, trả lại kết quả phù hợp
  5. Nếu chưa có, thực hiện transaction một lần
  6. Lưu kết quả/commit theo thiết kế
~~~

Cần xác định TTL của key, phạm vi uniqueness, hành vi khi request cùng key chạy đồng thời và policy khi payload khác. Không coi Redis SET đơn giản là đủ ngăn duplicate đối với mọi thao tác tài chính.

**Transaction boundary** phải thuộc use case. Không để template tự bọc tất cả HTTP requests trong transaction vì có thể giữ DB connection suốt thời gian gọi external dependency.

## 14. Mặc định khi gọi dependency: timeout và deadline

Một trong những thiếu sót thường gặp ở dịch vụ mới là client HTTP không có timeout hợp lý. Khi dependency chậm, số request đang chờ có thể tăng đến khi cạn thread pool, connection pool hoặc bộ nhớ.

Mỗi outbound client nên định nghĩa:

- Connect timeout.
- Response/read timeout.
- Overall request deadline.
- Connection pool max/idle timeout.
- Concurrency/bulkhead limit.
- Retry policy theo operation và failure class.
- Metrics per dependency: latency, errors, retries, active/waiting connections.
- Correlation/tracing context và propagation policy.
- TLS/server identity theo yêu cầu.

Ví dụ:

~~~text
End-to-end request deadline: 2000 ms

Gateway overhead:            100 ms
Checkout local work:         200 ms
Inventory dependency:        300 ms
Payment dependency:          800 ms
Order persistence:           300 ms
Dự phòng:                    300 ms
~~~

Đây là ngân sách minh họa cho một đường đi lý tưởng; phải xét bước song song và phân bố tail latency. **Không để mỗi tầng gọi nhau đặt timeout 5 giây trong khi yêu cầu ngoài cùng chỉ cho phép 2 giây**.

### 14.1. Retry có giới hạn

Không retry vô hạn và không retry mọi 4xx. Một ví dụ policy cho request idempotent:

~~~text
maxAttempts: 2
initialBackoff: 100 ms
backoffMultiplier: 2
jitter: enabled
retryable: timeout kết nối tạm thời hoặc 503 theo contract
notRetryable: input validation, 401, 403, 409 theo business semantics
deadline: phải còn đủ ngân sách trước khi retry
~~~

Policy phải dựa trên dependency contract. HTTP 429 có thể kèm Retry-After và quota cần tôn trọng; retry ngay có thể làm outage nặng hơn. Với thao tác có side effect, phải bảo đảm idempotency trước khi retry.

### 14.2. Tránh retry amplification

Nếu Gateway, Checkout và Payment mỗi tầng retry 3 lần, trong kịch bản xấu một request có thể dẫn tới rất nhiều attempts ở dependency cuối. Template nên cung cấp hướng dẫn retry **ở một tầng có thông tin đầy đủ nhất**, dùng deadline propagation và retry budget chung khi khả thi.

### 14.3. Circuit breaker, bulkhead và rate limiting

Đây là các cơ chế giảm blast radius:

- Circuit breaker ngừng gọi dependency đang lỗi nhiều.
- Bulkhead giới hạn công việc đồng thời để một dependency không chiếm hết tài nguyên.
- Rate limiting bảo vệ cả service lẫn upstream quota.
- Load shedding từ chối hoặc giảm chất lượng dịch vụ có kiểm soát khi quá tải.
- Fallback chỉ khi có semantics an toàn.

Không tự bật fallback trả dữ liệu giả cho Payment hoặc Inventory. Fallback phải được domain owner quyết định, test và ghi nhận độ suy giảm chất lượng.

## 15. Structured logging: bản ghi có thể tìm kiếm

Một template nên xuất structured logs (ví dụ JSON) với tên field thống nhất:

~~~json
{
  "timestamp": "2026-11-12T07:20:00Z",
  "level": "ERROR",
  "service": "catalog-service",
  "serviceVersion": "2.1.0",
  "environment": "production",
  "region": "region-a",
  "traceId": "example-trace-id",
  "spanId": "example-span-id",
  "operation": "catalog.get-item",
  "errorClass": "DependencyTimeout",
  "message": "Inventory lookup timed out"
}
~~~

Giá trị ví dụ không phải log sự kiện thật.

Các nguyên tắc:

- Timestamp UTC hoặc có timezone; thống nhất format.
- Không cần thêm trace ID thủ công ở mọi statement nếu logger/collector có thể lấy từ MDC/context.
- Có error code/class ổn định thay vì dựa hoàn toàn trên text.
- Không log password, token, cookie, dữ liệu thẻ và payload cá nhân.
- Log level theo môi trường và feature, tránh bật DEBUG production vô thời hạn.
- Log sampling/rate limiting cho lỗi lặp gây bùng log và chi phí.
- Không nuốt exception im lặng; tránh log cùng exception 5 lần ở các tầng.
- Không dùng user ID, order ID làm metric label, nhưng có thể đưa một mã correlation đã được kiểm soát vào log theo chính sách.
- Có retention, access control và audit ở backend logging.

Template có thể thêm middleware tự động gắn service/version/request outcome và một structured exception mapper, còn message nghiệp vụ nên do đội service viết.

## 16. Distributed tracing là mặc định kiến trúc

Một request có thể đi qua:

~~~text
Client -> Gateway -> Catalog -> Pricing -> Inventory
                          |
                          +----> Database
~~~

Nếu trace context không được propagate, đội vận hành chỉ có những spans rời rạc. Nên tích hợp OpenTelemetry SDK/agent phù hợp và kiểm chứng:

- Inbound SERVER spans.
- Outbound HTTP/gRPC CLIENT spans.
- Database/messaging spans khi thích hợp.
- W3C Trace Context propagation cho HTTP nếu đó là chuẩn đã chọn.
- Context propagation qua async executor, reactive flow hoặc messaging.
- service.name, service.version và environment metadata.
- Sampling policy và exporter/collector health.
- Span attributes/operation names ổn định, không chứa ID động.
- Span events cho transaction milestones, retries hoặc queue wait cần thiết.

Ví dụ cấu hình môi trường:

~~~text
OTEL_SERVICE_NAME=catalog-service
OTEL_RESOURCE_ATTRIBUTES=service.version=2.1.0,deployment.environment.name=production
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1
~~~

Các biến chỉ minh họa một cách cấu hình OpenTelemetry; cần xác minh agent/SDK, sampling policy và endpoint thực tế. Tỷ lệ 0,1 không phải lựa chọn mặc định cho mọi ứng dụng: service ít traffic hoặc cần incident tracing có thể phải dùng sampling khác, kết hợp tail sampling khi hạ tầng hỗ trợ.

Không tạo custom span cho mỗi vòng lặp/item, gây overhead và chi phí. Trace phải giúp tìm critical path, không biến thành bản sao đầy đủ của log.

## 17. Metrics và SLI/SLO: đo kết quả thay vì chỉ đo CPU

Template HTTP thường nên có một số métrics cốt lõi:

| Loại | Metric/định nghĩa gợi ý | Câu hỏi |
|---|---|---|
| Request traffic | RPS theo route template | Bao nhiêu request đến? |
| HTTP reliability | 5xx/timeouts/tỷ lệ request không đạt contract | Có lỗi kỹ thuật không? |
| Latency | Histogram theo route/status | p50/p95/p99 thay đổi ra sao? |
| Saturation | CPU, memory, thread/connection pool | Có chạm giới hạn? |
| Dependency | Client calls, latency, retry, 429 | Service nào gây chậm? |
| Messaging | Consumer lag, queue age, redelivery | Job có trễ không? |
| Business correctness | Tỷ lệ hoàn tất use case đúng | Có kết quả sai dù HTTP 200? |
| Runtime | GC pause, JVM heap, restarts | Có vấn đề runtime? |

Prometheus metric labels nên có số giá trị hữu hạn: service, environment, route template, method, status class, dependency. **Không gắn userId, orderId, raw URL, timestamp hay traceId vào metric labels** vì cardinality và rủi ro dữ liệu.

### 17.1. Ví dụ PromQL

Giả định Spring/Micrometer exporter cung cấp classic histogram http_server_requests_seconds theo labels job và status. Tên metric/nhãn cần điều chỉnh theo exporter thực tế.

Request rate:

~~~promql
sum(rate(http_server_requests_seconds_count{job="catalog-service"}[5m]))
~~~

5xx ratio:

~~~promql
sum(rate(http_server_requests_seconds_count{
  job="catalog-service",status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{job="catalog-service"}[5m]))
~~~

p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{job="catalog-service"}[5m])
  )
)
~~~

Mẫu số 0 hoặc series thiếu không có nghĩa "không lỗi". Khi dùng native histogram hoặc metric naming khác, cú pháp query đổi; template nên cung cấp dashboard dựa trên những metric thật sự được ứng dụng xuất.

### 17.2. Không định nghĩa SLO giống nhau cho mọi service

Ví dụ cho một endpoint tương tác:

~~~text
SLI: tỷ lệ GET /catalog/items hợp lệ trả kết quả đúng dưới 500 ms.
SLO: 99% good requests trong 28 ngày.
~~~

Với worker xử lý queue, SLI nên là tỷ lệ jobs hoàn tất trong deadline và đúng kết quả, không phải chỉ enqueue HTTP 202 nhanh.

Template nên yêu cầu service owner điền SLI/SLO và impact tier, cung cấp dashboard/runbook skeleton; không tự chốt một con số p95 500 ms cho mọi hệ thống.

## 18. Health probes: startup, readiness, liveness

Health checks cần có semantics thống nhất:

**Startup probe:** ứng dụng đã vượt giai đoạn khởi động hay chưa; hữu ích cho Java service cold start lâu.

**Readiness probe:** instance sẵn sàng nhận request mới chưa. Khi chưa ready, load balancer không nên gửi request tới Pod.

**Liveness probe:** tiến trình bị kẹt nghiêm trọng và cần restart không. Không nên phụ thuộc cứng vào mọi dependency ngoài, để tránh restart storm khi database hay provider chung outage.

Một ví dụ cấu hình Actuator (có thể khác theo framework version):

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Đường readiness/liveness cụ thể phụ thuộc actuator path và cổng quản lý. Nếu management port khác application port, kiểm tra readiness trên port quản lý có thể không phát hiện app listener bị lỗi; cần cân nhắc exposed probe endpoint trên app port hoặc một kiểm tra bổ sung phù hợp.

Không biến readiness thành bài integration test gọi tất cả downstream mỗi vài giây. Hàng trăm pod có thể cùng đánh dependency rơi vào trạng thái xấu. Readiness nên phản ánh điều kiện có thể phục vụ request **an toàn theo hợp đồng**.

## 19. Graceful shutdown để deploy/scale không cắt công việc

Khi Kubernetes terminate Pod, hệ thống cần chuyển request khỏi Pod và chờ công việc đang thực hiện hoàn tất hoặc được hủy có kiểm soát.

~~~text
SIGTERM / termination begins
          |
          v
Ngừng nhận request/job mới
          |
          v
Load balancer/queue coordinator cập nhật routing
          |
          v
Drain in-flight requests / hoàn tất hoặc checkpoint jobs
          |
          v
Flush telemetry và đóng pool/resources
          |
          v
Process exit trước grace period
~~~

Các yếu tố cần kiểm tra:

- terminationGracePeriodSeconds phù hợp.
- Spring graceful shutdown và timeout phase.
- HTTP keep-alive/HTTP2, gRPC stream hoặc WebSocket.
- Message ack chỉ sau khi xử lý thành công theo semantics.
- Bounded in-flight jobs và checkpoint/resume nếu job dài.
- Tránh đóng connection pool trước khi request cuối hoàn tất.
- Readiness và việc loại endpoint khỏi router có thể có độ trễ.
- Shutdown không làm mất dữ liệu hoặc tạo side effects trùng.

Đặt sleep cố định vài giây có thể giúp một trường hợp nhưng không thay thế thiết kế drain và kiểm thử thực tế.

## 20. Container: image nhỏ, bất biến và không chạy root

Một Dockerfile mẫu từ artifact jar đã build:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app

COPY target/catalog-service.jar /app/app.jar

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ chỉ nêu các nguyên tắc; image tag và artifact path phải khớp build thực. Production nên pin base image digest, cập nhật CVEs, tạo SBOM, thiết lập image signing/provenance và xây ở CI có nguồn tin cậy.

Các defaults:

- Không chạy root nếu không cần.
- Không bake secrets vào image hoặc build args bị lưu trong layers.
- Không cần package manager/shell trong runtime image nếu có thể loại bỏ an toàn.
- Có .dockerignore để tránh gửi target, .git, secrets hoặc dữ liệu không liên quan.
- Chỉ mở port thật sự cần.
- Graceful shutdown khi nhận SIGTERM.
- Build artifact reproducible/traceable theo chính sách.
- Tách runtime và build environment.
- Có read-only root filesystem nếu ứng dụng chịu được, mount tmp dir cần thiết.
- Capabilities tối thiểu, seccomp/AppArmor theo cluster policy.
- Không bắt buộc một runtime image cụ thể cho mọi ngôn ngữ/workload.

Non-root user cần quyền đọc jar và thư mục tạm nếu runtime sử dụng; cấu hình đúng filesystem permissions để không khiến Pod crash khi khởi động.

## 21. Kubernetes Deployment mẫu

Một Deployment khởi đầu có thể chứa các guardrails vận hành quan trọng:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
  labels:
    app.kubernetes.io/name: catalog-service
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app.kubernetes.io/name: catalog-service
  template:
    metadata:
      labels:
        app.kubernetes.io/name: catalog-service
        app.kubernetes.io/version: "2.1.0"
    spec:
      terminationGracePeriodSeconds: 40
      serviceAccountName: catalog-service
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: catalog-service
          image: registry.example.invalid/catalog-service:2.1.0
          ports:
            - name: http
              containerPort: 8080
            - name: management
              containerPort: 8081
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              memory: 512Mi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 5
            failureThreshold: 24
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: management
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 10
            failureThreshold: 3
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
~~~

YAML này chỉ là mảnh Deployment minh họa, chưa đủ để apply nếu service account, cluster policy, artifact và cấu hình management port chưa có. Runtime dùng filesystem tạm phải được cấp writable volume khi bật readOnlyRootFilesystem. CPU/memory values chỉ là điểm khởi đầu, không phải năng lực đã được kiểm thử.

Có thể thêm:

- Service và Gateway/Ingress routing.
- ConfigMap/Secret references theo chính sách.
- PodDisruptionBudget cho critical services.
- Topology spread để tránh dồn Pod vào một node/AZ.
- HPA/VPA theo workload profile.
- NetworkPolicy cho ingress/egress tối thiểu.
- ServiceMonitor/PodMonitor hoặc collector scraping theo platform.
- External secret injection, workload identity.
- ResourceQuota/LimitRange và namespace governance.

Không thêm tất cả cấu hình Kubernetes vào một Deployment file khó duy trì. Tách base và environment overlays, tránh drift giữa staging/production.

## 22. Service và network policies

Một Service nội bộ có thể có dạng:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-service
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: catalog-service
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Chỉ các service cần public Internet mới nên có Gateway/Ingress public và policy rõ. Những API quản trị, actuator hoặc database không nên tự động public theo mặc định.

NetworkPolicy có thể giới hạn các chiều ingress/egress, nhưng hiệu lực phụ thuộc CNI và cluster configuration. Một rule "deny all" mà chưa mở DNS, telemetry, secret manager hoặc dependency hợp lệ có thể khiến service không khởi động. Nên cung cấp policy profile đã kiểm thử, không phát tán một YAML "bảo mật" chưa biết có thực thi không.

### 22.1. TLS và service identity

Các default có thể gồm TLS từ edge tới ingress và mTLS cho service-to-service khi nền tảng hỗ trợ và rủi ro cần thiết. Chỉ mã hóa đường truyền chưa đủ: phải xác thực peer identity, rotate certificate và giới hạn authorization.

Không hardcode việc bỏ kiểm tra certificate trong HTTP client để môi trường dev chạy nhanh. Việc thay trust store cần quản trị theo từng environment.

## 23. Resource requests, limits và autoscaling

Template có thể đưa **resource baseline** để scheduler đặt Pod, nhưng phải yêu cầu đội service hiệu chỉnh bằng load test và workload characteristics.

Ví dụ một API CPU-bound và một API I/O-bound có thể cần scale signals khác nhau:

| Workload | Tín hiệu scale nên xem | Giới hạn cần kiểm tra |
|---|---|---|
| HTTP CPU-heavy | CPU utilization so với requests, RPS/Pod | CPU throttling, startup time |
| HTTP I/O-bound | In-flight requests, concurrency, RPS/Pod | DB/provider quota, connection pool |
| Queue consumer | Queue depth, oldest age, processing rate | Partition count, idempotency, DLQ |
| Long-lived connections | Active sessions, memory, concurrency | Sticky sessions, drain |
| Batch | Remaining work, deadline, throughput/worker | Shared dependency quota |
| Stateful service | Workload-specific, có controller phù hợp | Quorum/storage consistency |

Ví dụ HPA với CPU làm tín hiệu khởi đầu cho API phù hợp:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: catalog-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: catalog-service
  minReplicas: 3
  maxReplicas: 15
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
~~~

CPU 65%, min 3 và max 15 là ví dụ, không phải tổ chức nào cũng dùng được. Thêm Pod không giải quyết dependency bị nghẽn và còn làm tăng DB connections hoặc request tới provider. Phải đo SLO và capacity end-to-end.

### 23.1. PodDisruptionBudget

PDB giúp giới hạn gián đoạn tự nguyện theo chính sách Kubernetes, ví dụ khi bảo trì node. Nó **không** bảo đảm tránh mọi dạng outage hoặc mọi thao tác deletion/rollout. Cần hiểu tương tác giữa PDB, rolling update, maxUnavailable và cluster capacity.

### 23.2. Multi-zone placement

Dịch vụ quan trọng có thể cần topology spread hoặc anti-affinity để không đặt mọi replica trên một node/failure domain. Tuy nhiên nếu ràng buộc quá cứng khi cluster thiếu node, Pod có thể Pending. Phải cân bằng availability với khả năng schedule và node autoscaler.

## 24. Database: migrations, pool và ownership

Không phải service nào cũng cần database. Nếu có, template nên cung cấp một module/pattern:

- Schema do service sở hữu.
- Migration tool phù hợp như Flyway/Liquibase hoặc cơ chế chuẩn tổ chức.
- Migration versioned, reviewable và được chạy có kiểm soát.
- Connection pool với min/max/timeout theo capacity database.
- Transaction boundaries ở use case.
- Retry cho database theo semantics, không retry toàn bộ transaction vô giới hạn.
- Backup/restore và disaster recovery thuộc owner/platform rõ.
- Data access với least privilege.
- DB telemetry: pool wait, active connections, query latency, locks.
- Test bằng DB engine tương thích với production, không chỉ in-memory fake cho mọi case.

### 24.1. Expand-and-contract migration

Trong rolling/canary, version cũ và mới có thể cùng chạy. Một schema change phá vỡ backward compatibility sẽ gây lỗi hoặc khiến rollback bất khả thi.

Quy trình phổ biến:

1. Expand: thêm column/table/constraint ở dạng cả v1 và v2 dùng được.
2. Deploy code biết đọc/ghi thích ứng giai đoạn chuyển tiếp.
3. Backfill dữ liệu có kiểm soát và reconciliation.
4. Chuyển traffic/feature flag.
5. Xác nhận không còn consumer phụ thuộc schema cũ.
6. Contract: loại bỏ phần cũ ở một lần thay đổi riêng.

Template nên đưa checklist và migration testing, không mặc định "startup app tự chạy ALTER TABLE production" cho mọi tổ chức.

### 24.2. Connection pool không scale vô hạn

Ví dụ 20 Pods, mỗi Pod pool tối đa 40 connections tạo tiềm năng 800 DB connections. Nếu database chịu được 300 kết nối, autoscaling service có thể gây saturation. Max pool/Pod phải được chọn cùng maxReplicas và capacity database.

## 25. Messaging profile: event contracts và xử lý at-least-once

Một consumer skeleton cần khác HTTP controller.

Những mặc định quan trọng:

- Event envelope có eventId, eventType, version, occurredAt và correlation context.
- Consumer group/partition key theo domain.
- Schema versioning/compatibility và contract tests.
- Bounded concurrency và processing timeout.
- Ack/offset chỉ theo semantics sau khi xử lý thành công.
- Retry có giới hạn, backoff/jitter và DLQ/quarantine.
- Idempotency khi broker redeliver.
- Xử lý poison message và khả năng replay.
- Metrics processing rate, lag, queue age, retry/DLQ.
- Graceful shutdown và checkpoint nếu công việc dài.
- Kiểm soát PII/retention trong event payload.

Ví dụ event envelope:

~~~json
{
  "eventId": "d6d6-example-id",
  "eventType": "CatalogItemPublished",
  "eventVersion": 1,
  "aggregateId": "item-90021",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-12T07:20:00Z",
  "traceContext": "example-propagated-context",
  "payload": {
    "itemId": "item-90021",
    "category": "BOOKS"
  }
}
~~~

Đây là schema minh họa. Không mặc định broker cho exactly-once end-to-end, ngay cả khi nó hỗ trợ transaction trong phạm vi broker. External side effects và database sink vẫn cần idempotency hoặc coordinated processing.

### 25.1. Transactional outbox

Nếu một use case commit database state và publish event, cần tránh dual-write không nguyên tử. Template có thể cung cấp một outbox module/pattern, nhưng đừng ép mọi service phải có outbox table khi không phát domain event.

Khi outbox relay phát lại sau crash, consumer có thể nhận event trùng; event_id và deduplication vẫn cần thiết.

## 26. CI/CD mặc định: từ source tới artifact có bằng chứng

Một pipeline chuẩn có thể có:

~~~text
Pull request
    |
    +--> Lint / format / static analysis
    +--> Unit tests
    +--> Contract / integration tests
    +--> Dependency vulnerability / secret scan
    +--> API schema compatibility checks
    |
    v
Merge to protected branch
    |
    v
Build artifact + immutable image digest
    |
    +--> SBOM / provenance / signing policy
    +--> Container scan
    |
    v
Deploy staging
    |
    +--> Smoke / migration / basic resilience checks
    |
    v
Production rollout (rolling/canary/blue-green)
    |
    +--> Deployment markers
    +--> Readiness and SLO guardrails
    +--> Pause/rollback on failure
    |
    v
Post-deploy observation + catalog update
~~~

Một pipeline tốt là **một đường phát hành có kiểm soát**, không phải chỉ build jar và push image.

Các thiết lập:

- Protected branch và code review.
- Least-privilege CI identity, không dùng secret dài hạn nếu có lựa chọn identity federation phù hợp.
- Dependencies được lock hoặc quản trị phiên bản.
- Build artifact traceable tới commit/run.
- Không dùng image tag mutable để làm bằng chứng rollback.
- Kết quả scanner có policy xử lý severity và false positive rõ.
- Secrets không in ra logs.
- Không chạy untrusted code với quyền truy cập production secret.
- Deployment cần đúng environment, approver và audit trail theo risk tier.
- Rollback target và runbook có thể tìm ngay khi có sự cố.

Không được tin chỉ vì CI xanh là service đúng với production traffic và data. Cần thêm observability, progressive rollout và business correctness.

## 27. Testing pyramid và các kiểm thử bắt buộc

| Lớp kiểm thử | Trả lời câu hỏi |
|---|---|
| Unit tests | Domain logic và validation đúng? |
| Component tests | Controller/application behavior đúng? |
| Integration tests | DB/messaging/external adapters hoạt động? |
| Contract tests | API/event tương thích producer-consumer? |
| Security tests | Authn/authz, tenant isolation, input boundary? |
| Migration tests | Schema cũ/mới cùng hoạt động khi rollout? |
| Smoke tests | Artifact vừa deploy có phục vụ các luồng cơ bản? |
| Load/performance tests | SLO/throughput dưới tải đại diện? |
| Resilience tests | Khi dependency timeout/429, service giảm tác động đúng? |
| Recovery tests | Rollback, replay và restore có hoạt động? |

### 27.1. Unit test không cần chạy cả cluster

Service template nên cho phép domain/application tests chạy nhanh và độc lập. Những bài cần DB hoặc broker thực có thể dùng Testcontainers hoặc môi trường integration được chuẩn hóa. Không test SQL production chỉ với một in-memory DB có semantics khác rồi tin rằng migrations và locks đã được kiểm chứng.

### 27.2. Contract tests giảm lỗi version chéo

Trong Microservices, mỗi service triển khai độc lập, nên consumer v1 có thể gọi producer v2 và ngược lại. Kiểm thử contract giúp phát hiện field bị xóa/đổi nghĩa hoặc event schema không tương thích trước khi rollout.

### 27.3. Kiểm thử sự cố như một phần chất lượng

Một service HTTP cần kiểm tra không treo vô hạn khi upstream ngừng phản hồi. Một queue consumer cần kiểm tra redelivery không tạo side effect trùng. Một service có database cần kiểm tra transaction/rollback và connection pool exhaustion ở mức phù hợp.

Template tạo **khung test và helpers**, còn failure modes cụ thể phải do team dựa trên dependency thật để viết.

## 28. IaC, deployment và quản trị môi trường

Một nguyên tắc quan trọng: cấu hình dev, staging và production cần có quan hệ và khác biệt được giải thích.

Có thể dùng:

- Kustomize base + overlays.
- Helm chart với values/schema.
- Terraform/Pulumi hoặc IaC tương ứng cho cloud resources.
- GitOps controller để reconcile workload.
- Policy as code cho guardrails.
- External secret operator/workload identity.

Một layout:

~~~text
deploy/
├── base/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── hpa.yaml
│   └── kustomization.yaml
└── overlays/
    ├── dev/
    ├── staging/
    └── production/
~~~

Không để cùng một giá trị maxReplicas/timeout/DB pool áp dụng mù cho ba môi trường. Nhưng cũng không cho từng môi trường cấu hình theo kiểu không thể truy vết. Mỗi override cần có lý do, owner và khả năng review.

### 28.1. Promotion cùng artifact

Lý tưởng là cùng một immutable artifact được kiểm thử rồi promote qua các môi trường; chỉ cấu hình môi trường thay đổi có kiểm soát. Tránh rebuild từ source vào phút cuối khi triển khai production rồi sử dụng binary khác với staging.

### 28.2. Version và rollback

Deployment record nên lưu source SHA, build ID, image digest, config revision, deployment ID, region và rollout stage. Rollback artifact không nhất thiết rollback database migration hay dữ liệu đã ghi; runbook phải nêu giới hạn.

### 28.3. Progressive delivery

Đối với service quan trọng, template có thể tạo mặc định canary/rollout guardrails; nhưng policy tăng traffic theo tỷ lệ và thời gian cần hiệu chỉnh với SLO, lưu lượng và risk tier.

Ví dụ một canary 1% của service có 20 request/ngày không có đủ mẫu để suy luận an toàn trong 5 phút. Ngược lại, lỗi correctness trong thanh toán có thể buộc dừng ngay dù ít request.

## 29. Service ownership và catalog

Mọi service nên có một hồ sơ tối thiểu:

~~~yaml
apiVersion: platform.example.invalid/v1
kind: ServiceMetadata
metadata:
  name: catalog-service
spec:
  domain: product-catalog
  owner: catalog-team
  lifecycle: production
  runtimeProfile: java-http
  operationalTier: tier-2
  repository: org/catalog-service
  runbook: docs/runbook.md
  apiContract: api/openapi.yaml
  sloDocument: docs/slos.md
  dataClassification: internal
~~~

Đây là **schema metadata minh họa**, không phải Kubernetes CustomResource có sẵn. Nền tảng có thể dùng Backstage catalog hoặc hệ thống riêng; cần chuyển đổi field/schema theo tool được chọn.

Hồ sơ nên chỉ ra:

- Ai chịu trách nhiệm khi service lỗi.
- Service phục vụ nghiệp vụ nào.
- Repository, dashboard, traces, alert rules ở đâu.
- API/event contract và dependencies.
- Runbook và rollback strategy.
- SLO, tier, on-call rotation.
- Data owner và phân loại thông tin.
- Deployment environments.
- Thời điểm review ownership gần nhất.

Không để owner là tên một nhân viên đã rời tổ chức mà không có nhóm kế thừa. Ownership cần được review định kỳ và cập nhật khi tái tổ chức.

## 30. Runbook được tạo ngay từ ngày đầu

Một runbook mặc định không nên là file rỗng chỉ có chữ TODO. Nó có thể cung cấp cấu trúc với các thao tác và đường dẫn cần điền trước production:

~~~markdown
# Catalog Service Runbook

## Overview
- Service owner:
- Operational tier:
- Source repo:
- Production dashboard:
- Tracing search:
- Log search:
- Deployment history:
- SLO:

## Common alerts
- High error rate:
- High latency:
- Dependency timeout:
- Pod not ready:
- DB pool exhaustion:

## Triage
1. Xác nhận user/business impact.
2. Kiểm tra deployment/config/flag gần đây.
3. So traffic, error, latency, saturation theo version.
4. Mở trace lỗi/chậm đại diện.
5. Kiểm tra dependencies.

## Mitigation
- Pause rollout:
- Shift canary traffic:
- Turn feature flag off:
- Scale capacity safely:
- Apply fallback only when approved:

## Recovery
- Rollback target:
- Data compatibility caveats:
- Queue/in-flight work:
- Verify business SLI:
- Escalation contacts:
~~~

Trong chính service README không nên gắn status nội bộ của worker; đây là ví dụ cấu trúc runbook thuộc bài học. Các lệnh thật cần có xác nhận quyền và môi trường, không đặt câu lệnh xóa dữ liệu production vào runbook tự động chạy khi chưa qua phê duyệt.

### 30.1. Operational readiness review

Trước production, team nên biết ai nhận alert, có khả năng rollback và có ít nhất một dashboard giúp trả lời "người dùng có đang thành công không?".

## 31. Template versioning và nâng cấp

Đây là phần nhiều tổ chức bỏ sót: tạo service mới rất nhanh nhưng sau hai năm có hàng chục service khác nhau do template được copy tại nhiều thời điểm.

Phân biệt:

- **Template version:** phiên bản skeleton và generator.
- **Starter/library version:** phiên bản code dùng chung được cập nhật như dependency.
- **Runtime version:** JDK/Spring Boot/container base.
- **Platform API version:** contract của CI, deploy manifests, telemetry, secret manager.
- **Service release version:** phiên bản business service cụ thể.

Một bản template mới không tự cập nhật những repository được sinh ra trước đó.

### 31.1. Chiến lược nâng cấp

1. Giữ phần dùng chung trong thư viện/starter có semantic version và changelog.
2. Dùng dependency update automation có kiểm soát, kèm test matrix.
3. Định nghĩa upgrade guides cho breaking changes.
4. Có codemod/migration scripts cho thay đổi cấu trúc repository, nhưng chạy có review.
5. Theo dõi service nào dùng version quá cũ và rủi ro tương ứng.
6. Giữ compatibility window rõ, không buộc mọi service nâng ngay trong một đêm.
7. Với security patch nghiêm trọng, có quy trình rollout nhanh và xác minh.
8. Deprecate template profile cũ theo lịch thông báo và lối chuyển đổi.

### 31.2. Kiểm thử chính template

Một service generator cần test:

- Sinh repo với các tên/dấu gạch hợp lệ.
- Không để placeholder chưa được thay vào artifact cuối.
- Dùng được với tên package nhiều cấp.
- Build/test sạch trên CI.
- Chạy local với profile dev được hỗ trợ.
- Container khởi động non-root.
- Probes trả kết quả đúng.
- Metrics/traces/logs xuất tới test collector.
- Deploy staging theo pipeline mẫu.
- Không có secret hardcoded hoặc permission quá rộng.
- Mọi profile opt-in đều có smoke test.

Template là **một sản phẩm của platform team**, cần version, release notes, tests và support giống một thư viện sản xuất.

## 32. Governance: policy như code, ngoại lệ có thời hạn

Quản trị hiệu quả phải trả lời "điều gì bắt buộc, kiểm tra ở đâu, và ai có thể chấp nhận ngoại lệ?".

Ví dụ policy:

| Quy tắc | Nơi kiểm tra | Bằng chứng |
|---|---|---|
| Không commit secrets | PR pipeline | Secret scan report |
| Image không chạy root | Build/deploy policy | Security context scan |
| Artifact có provenance | Release pipeline | Build attestation |
| Service có owner | Catalog validation | Metadata hợp lệ |
| Có health probes | Manifest validation | Runtime smoke test |
| Resource requests | Admission/manifest lint | Deployment configuration |
| Có CI kiểm thử | Branch protection/pipeline | Test result |
| Có SLO và runbook cho tier cao | Readiness review | Links và reviewer |
| Không public admin endpoints | Network/security policy | Route validation |
| Không dùng dependency đã bị cấm | Dependency policy | Audit report |

Không biến policy thành một tập "checkbox" không liên quan tới rủi ro. Ví dụ bắt buộc HPA cho một cronjob chạy 10 phút mỗi đêm có thể không có ý nghĩa.

### 32.1. Quản lý ngoại lệ

Một ngoại lệ tốt có:

- Service, policy và lý do kỹ thuật.
- Risk assessment và tác động.
- Biện pháp giảm thiểu tạm thời.
- Owner và người phê duyệt đúng thẩm quyền.
- Ngày hết hạn và thời điểm review.
- Kế hoạch trở lại golden path.

Không dùng một biến môi trường SKIP_SECURITY_CHECKS=true không giới hạn trên mọi repository để "đơn giản hóa". Exception phải rõ ràng, có thời hạn và được audit.

### 32.2. Ranh giới tự chủ của team sản phẩm

Platform team sở hữu cơ chế và guardrails chung. Service team sở hữu logic nghiệp vụ, SLO và lựa chọn phù hợp trong không gian được phép. Không nên buộc mọi thay đổi nhỏ phải có platform team viết hộ, vì điều đó làm giảm lợi ích self-service.

## 33. Developer experience: chạy local và tạo service mới

Một luồng tự phục vụ lý tưởng:

~~~text
Developer mở service generator / internal developer portal
       |
       v
Chọn profile: java-http
       |
       v
Nhập service name, domain, owner, environment
       |
       v
Generator tạo repository từ template version cụ thể
       |
       v
CI build/test và kiểm tra policy
       |
       v
Chạy local với dependency test
       |
       v
Deploy staging sandbox
       |
       v
Nhận link API docs, dashboard, traces, logs
       |
       v
Service readiness review và production rollout
~~~

Các trải nghiệm nên có:

- Hướng dẫn bắt đầu ngắn, chính xác và chạy được.
- Một lệnh build/test/local run ổn định.
- Không cần credential production để phát triển local.
- Dev secrets hoặc local mocks có scope an toàn.
- Dữ liệu mẫu không chứa thông tin khách hàng thật.
- Lỗi generator có thông báo và cách xử lý rõ.
- Hướng dẫn thêm dependency profile mà không phá cấu hình chung.
- Cơ chế hỗ trợ, feedback và đề xuất cải tiến template.

Time-to-first-deploy có thể là KPI hữu ích, nhưng phải tính từ lúc user khởi tạo service đến khi service thực sự có thể phục vụ và quan sát được ở staging, không chỉ lúc repository được tạo.

## 34. Tạo service mới không có nghĩa tạo Microservice mới là đúng

Một nền tảng thuận tiện có thể dẫn đến "microservice sprawl": mỗi chức năng nhỏ sinh một service riêng dù chưa có ranh giới domain tốt, tăng chi phí mạng, deploy, dữ liệu và on-call.

Trước khi dùng template, nên hỏi:

- Đây là bounded context độc lập hay một module của service hiện tại?
- Có nhu cầu release/scale/ownership độc lập thật không?
- Dữ liệu thuộc service nào và có transaction liên kết phức tạp không?
- API giữa hai module có ổn định không?
- Số lượng service mới có làm tăng call graph và latency đáng kể không?
- Team có khả năng vận hành 24/7 và xử lý incident không?
- Có thể đạt mục tiêu bằng modular monolith hoặc thư viện không?

**Template chuẩn hóa cách tạo và vận hành service; nó không thay thế quyết định kiến trúc nên hay không nên tách service.**

## 35. Các chỉ số để đánh giá service template

Một chương trình platform nên đo hiệu quả thay vì chỉ đếm số repo sinh ra.

| Chỉ số | Điều cần biết |
|---|---|
| Time to first successful staging deploy | Service mới mất bao lâu để chạy và có telemetry? |
| Golden path adoption | Bao nhiêu service dùng profile được hỗ trợ? |
| Upgrade lag | Bao nhiêu service chậm cập nhật runtime/starter security? |
| Security guardrail coverage | Tỷ lệ service có policy và bằng chứng đúng? |
| Observability coverage | Bao nhiêu service có traces/metrics/logs theo chuẩn? |
| Operational readiness | Tier phù hợp có owner, SLO, runbook, on-call? |
| Incident recurrence | Những lỗi cấu hình lặp lại có giảm? |
| Deployment rollback success | Có thể khôi phục khi bản mới lỗi? |
| Developer satisfaction | Template có dễ dùng, lỗi khó hiểu ở đâu? |
| Maintenance cost | Bao nhiêu công sức platform phải hỗ trợ/correct drift? |
| Production SLO | Khả năng tin cậy thật của các service dùng template |
| Exception aging | Ngoại lệ nào quá hạn hoặc không được review? |

Cần xem chất lượng và độ khó của workload khi so sánh. Một service high-tier với payment integration có thể cần nhiều bước kiểm thử hơn một internal service đơn giản; time-to-deploy chậm hơn không nhất thiết phản ánh template kém.

## 36. Anti-patterns thường gặp

1. **Copy một repo cũ làm template:** mang theo secret, cấu hình lỗi, dependency không dùng.
2. **Template chỉ có Hello World:** thiếu deployment, observability, ownership.
3. **Bắt buộc mọi service dùng một database/broker:** coupling và vận hành thừa.
4. **Hardcode production defaults vào source:** thay môi trường khó và nguy hiểm.
5. **Bật actuator/admin endpoints public:** tăng bề mặt tấn công.
6. **Không đặt timeout cho HTTP clients:** thread/pool exhaustion khi dependency lỗi.
7. **Retry vô hạn hoặc retry tất cả lỗi:** khuếch đại outage.
8. **Chỉ có HTTP error metric:** bỏ qua business correctness và queue completion.
9. **Chỉ dùng liveness không có readiness:** nhận traffic quá sớm khi pod khởi động.
10. **Readiness phụ thuộc tất cả external systems:** một outage chung rút mọi pod khỏi routing.
11. **Container chạy root mặc định:** không đáp ứng least privilege khi không cần.
12. **Không có resource requests:** scheduling/HPA thiếu cơ sở.
13. **Mỗi service tự chọn log fields và trace protocol:** observability phân mảnh.
14. **Không có migration compatibility:** rolling update phá version cũ.
15. **Tất cả errors trả HTTP 200:** alert và client semantics sai.
16. **Template tạo Kafka consumer nhưng không idempotent:** redelivery gây side effects trùng.
17. **Không có rollback target bất biến:** không biết đang quay về image nào.
18. **Không có ownership và runbook:** service orphaned khi incident.
19. **Copy code dùng chung thay vì versioned library:** sửa bug phải ghép thủ công hàng chục repo.
20. **Template không có migration path:** repo mới tốt, repo cũ lạc hậu mãi.
21. **Policy chỉ chạy trong pipeline tùy chọn:** dễ bỏ qua guardrails.
22. **Gắn quá nhiều policy cứng:** đội phát triển phải tìm workaround thay vì theo golden path.
23. **Không kiểm thử generator:** service mới không build hoặc placeholders chưa thay.
24. **Đo template bằng số lượng services tạo ra:** khuyến khích chia nhỏ vô nghĩa.
25. **Không xác định data classification:** log/warehouse sao chép PII không kiểm soát.

## 37. Bài tập thực hành

### Bài 1 — Chọn defaults theo workload

Một service A là REST API CPU-heavy, service B là Kafka worker có 8 partitions, service C là cron job chạy mỗi đêm. Có nên để cả ba mặc định HPA CPU 65%, maxReplicas 20, Service/Ingress public?

**Đáp án:** Không. API A có thể dùng CPU HPA nếu benchmark chứng minh phù hợp; Kafka B nên xem consumer lag, số partition, throughput, idempotency và DLQ; cron C thường dùng Job/CronJob với concurrency/deadline/checkpoint, không cần public ingress. Template nên có profile khác nhau.

### Bài 2 — Timeout

Gateway có deadline 1,5 giây, Checkout gọi Inventory (300 ms), Payment (1.000 ms), Order DB (200 ms), còn local processing 250 ms theo trình tự tuần tự.

Tổng tối thiểu xấp xỉ 1.750 ms, lớn hơn deadline 1.500 ms. Cần xem lại thiết kế, song song hóa bước không phụ thuộc, cache hợp lệ, tăng SLO có cơ sở hoặc đổi workflow async. Không sửa bằng cách cho mỗi dependency timeout 5 giây.

### Bài 3 — Retry và idempotency

Một payment POST có khả năng tạo side effect. Client timeout trước khi nhận response nhưng server có thể đã commit. Template có nên retry tự động?

**Đáp án:** Chỉ khi contract hỗ trợ idempotency/retry an toàn. Phải giữ cùng idempotency key, có overall deadline và xử lý trường hợp trạng thái không chắc chắn bằng tra cứu/reconciliation phù hợp.

### Bài 4 — Config drift

Staging dùng provider sandbox, production dùng provider thật. Một developer commit endpoint sandbox vào application.yaml làm default và production không override.

**Câu hỏi:** Thiết kế template tránh lỗi này thế nào?

**Gợi ý:** Tách externalized config theo environment, validate các required properties tại startup, cấm fallback nguy hiểm ở production, test manifest và cấu hình policy trong CI, dùng config revision/audit.

### Bài 5 — Non-root container

Template chạy non-root nhưng framework cần ghi temp files vào /tmp, còn Pod bật readOnlyRootFilesystem.

**Câu hỏi:** Hướng xử lý đúng?

**Gợi ý:** Cấp writable emptyDir cho temp path được kiểm soát, đặt quyền phù hợp, không tắt toàn bộ security context chỉ để app chạy. Kiểm tra disk usage và cleanup.

### Bài 6 — Ownership

Một service mới đã deploy nhưng không có runbook, owner hoặc dashboard; sau ba tháng xảy ra lỗi và không ai biết tìm ai.

**Câu hỏi:** Guardrail nào nên nằm trong golden path?

**Gợi ý:** Service catalog metadata/owner bắt buộc, links telemetry, runbook skeleton và operational readiness check trước production; không chỉ xác nhận CI build.

### Bài 7 — Template version drift

Platform đã sửa một lỗi security trong starter. 30 service dùng starter phiên bản cũ.

**Câu hỏi:** Chỉ sửa template generator có đủ không?

**Đáp án:** Không. Generator ảnh hưởng repo mới; cần đường nâng cấp dependency, automation tạo PR, compatibility tests, tracking adoption và quy trình ưu tiên patch.

### Bài 8 — API correctness

Một service trả HTTP 200 với body message="error" khi database timeout.

**Câu hỏi:** Hậu quả?

**Gợi ý:** Client có thể coi request thành công; metrics/alerts theo HTTP status bỏ lọt sự cố; retries/circuit breaker và SLO tính sai. Cần dùng status/error semantics nhất quán với domain outcome.

### Bài 9 — Quản lý ngoại lệ

Một legacy service không thể chạy non-root ngay vì thư viện cũ cần ghi vào một thư mục chỉ root có quyền.

**Câu hỏi:** Nên bỏ policy cho toàn tổ chức không?

**Đáp án:** Không. Tạo exception có owner, lý do, risk, thời hạn, biện pháp tạm và kế hoạch cải tạo, trong khi mặc định non-root vẫn áp dụng cho phần còn lại.

### Bài 10 — Chọn service hay module

Một team muốn tách một lớp formatter nhỏ thành microservice vì generator tạo repo chỉ mất vài phút. Điều gì cần cân nhắc?

**Gợi ý:** Bounded context, ownership, scaling, call overhead, latency, reliability, deploy/on-call/data boundaries. Có thể giữ như một module hoặc thư viện thay vì tạo một failure domain mới.

## 38. Checklist service template trước khi phát hành

### Cấu trúc và contract

- [ ] Generator tạo repository từ metadata tên/domain/owner hợp lệ.
- [ ] Có một hệ build chuẩn và không chứa placeholder chưa thay.
- [ ] Build sạch, unit/integration tests chạy được.
- [ ] API/event contract được version và có compatibility rules.
- [ ] Có validation, error mapping và pagination/input limits.
- [ ] Có cơ chế idempotency/pattern cho operation có side effects.
- [ ] Không bắt buộc dependencies không liên quan tới profile.

### Runtime và bảo mật

- [ ] Cấu hình externalized và fail fast với required settings.
- [ ] Không có secret hardcoded hoặc secret production fallback.
- [ ] Identity/authentication/authorization theo policy.
- [ ] Outbound clients có timeout, retries bounded và telemetry.
- [ ] Container non-root và least privilege.
- [ ] Image artifact traceable, có vulnerability scan.
- [ ] Management endpoints không public ngoài ý muốn.
- [ ] Resource requests, lifecycle/shutdown và probes phù hợp.

### Quan sát và vận hành

- [ ] Logs cấu trúc, không chứa token/PII nhạy cảm.
- [ ] Metrics theo route và dependency, có cardinality policy.
- [ ] Tracing xuyên HTTP/async và service metadata.
- [ ] SLO/runbook/owner/catalog links được điền trước production.
- [ ] Deployment markers và rollback target có thể tìm.
- [ ] HPA/queue profile được cấu hình theo tải thực, không copy target mù.
- [ ] Graceful shutdown không làm mất request/job.
- [ ] Smoke tests và test resilience failure mode quan trọng.

### Delivery và governance

- [ ] PR checks, branch protection và release pipeline được kiểm thử.
- [ ] Artifact được promote với provenance/digest rõ.
- [ ] Staging deployment chạy được và có telemetry.
- [ ] Production rollout có guardrail/approval theo tier.
- [ ] Manifests/IaC và policy checks có owner.
- [ ] Có đường nâng cấp template/starter và changelog.
- [ ] Có ngoại lệ được phê duyệt và thời hạn.
- [ ] Có người nhận feedback và hỗ trợ phát sinh từ template.

## 39. Gợi ý quy trình áp dụng trong tổ chức

### Giai đoạn 1 — Chọn một golden path hẹp

Bắt đầu bằng profile HTTP Java/Spring Boot dùng nhiều nhất. Phỏng vấn vài team, thu thập lỗi cấu hình/sự cố đã gặp, chọn guardrails có giá trị rõ. Không tạo một "universal microservice framework" ngay từ đầu.

### Giai đoạn 2 — Tạo reference service và kiểm thử như sản phẩm

Generator phải tạo một service có thể build, chạy local và deploy staging, có request validation, telemetry, probes, non-root image và README đúng. Chạy kiểm thử template qua mọi đường tạo repo.

### Giai đoạn 3 — Thí điểm với service thật

Cho một hoặc hai team tạo service mới, ghi time-to-first-deploy, lỗi họ gặp, bước cần hỗ trợ, nơi nào muốn escape hatch. Sửa template theo feedback có cơ sở.

### Giai đoạn 4 — Tách reusable libraries khỏi scaffold

Đưa retry/logging/telemetry/security helpers phù hợp vào versioned starters hoặc platform capabilities. Không copy cùng 1.000 dòng vào mọi repo nếu có thể cập nhật qua dependency version.

### Giai đoạn 5 — Mở rộng profiles có chọn lọc

Thêm queue-worker, scheduler, batch khi nhu cầu lặp đủ lớn. Mỗi profile có tests, docs, dashboard và owner.

### Giai đoạn 6 — Quản trị nâng cấp và độ lệch

Đặt minimum supported versions, dependency automation, security patch rollout và service catalog. Theo dõi service nào dùng defaults cũ và hỗ trợ nâng theo mức độ rủi ro.

### Giai đoạn 7 — Đo tác động

Theo dõi time-to-production, incident patterns, adoption, upgrade lag, platform support burden, security compliance và developer feedback. Loại bỏ cấu hình gây phiền mà không giảm rủi ro, bổ sung guardrail khi có bằng chứng từ sự cố.

## 40. Ghi nhớ

**Service template** không chỉ là bộ file để tạo endpoint đầu tiên. Nó là điểm bắt đầu của hợp đồng vận hành một Microservice: identity, API, data ownership, configuration, secrets, security, observability, resource planning, deployment, rollback, tests và trách nhiệm hỗ trợ.

Có những mặc định nên bắt buộc như non-root container, không hardcode secret, tracing correlation, cấu hình có validation, artifact provenance và ownership. Có những thông số phải dựa trên workload, chẳng hạn CPU/memory requests, HPA target, connection pool size, retry budget và SLO. Có những thành phần chỉ được opt-in khi thực sự cần như Kafka, cache, scheduler hoặc database.

Một golden path tốt phải giảm công việc lặp mà không giấu complexity thiết yếu, dễ nâng cấp theo phiên bản, có kiểm thử của chính template và có cơ chế ngoại lệ có trách nhiệm. Nó giúp các team **tự chủ trong logic nghiệp vụ nhưng cùng tuân theo những chuẩn an toàn và vận hành có giá trị**.

**Nguyên tắc cốt lõi: chuẩn hóa phần lặp lại và các ranh giới rủi ro, không chuẩn hóa mù mọi quyết định kiến trúc. Mọi service mới nên bắt đầu với bảo mật, quan sát, triển khai và ownership đáng tin cậy — rồi được hiệu chỉnh theo thực tế của workload và SLO.**
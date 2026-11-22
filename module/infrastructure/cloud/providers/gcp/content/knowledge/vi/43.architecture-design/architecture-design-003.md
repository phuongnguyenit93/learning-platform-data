# Kiến trúc ứng dụng web ba tầng trên Google Cloud

Trong module `CLOUD_PROVIDERS_GCP`, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học học cách lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Chương **Thiết kế kiến trúc GCP** kết nối những kiến thức này thành phương án có thể triển khai, kiểm tra và vận hành.

Bài học này thiết kế một ứng dụng web **ba tầng (three-tier web application)** với ví dụ hệ thống quản lý đơn hàng. Kiến trúc tham chiếu dùng **External Application Load Balancer**, **Cloud Run** cho tầng trình bày và tầng nghiệp vụ, cùng **Cloud SQL for PostgreSQL** ở tầng dữ liệu. Thiết kế ưu tiên workload mới, quy mô nhỏ đến vừa, đội vận hành muốn giảm việc quản trị máy chủ. Bạn cũng sẽ biết khi nào cần đổi sang GKE, Compute Engine hoặc dịch vụ khác.

## 1. Ba tầng là gì và vì sao cần tách?

Ba tầng là ba **trách nhiệm logic**, không nhất thiết tương ứng với ba máy ảo hoặc ba VPC khác nhau:

| Tầng | Trách nhiệm | Những điều không nên làm |
| --- | --- | --- |
| **Presentation (web/UI)** | Trả HTML, CSS, JavaScript; hiển thị dữ liệu; thu thập đầu vào; quản lý trải nghiệm phiên người dùng. | Chứa mật khẩu database, cho trình duyệt kết nối database trực tiếp, tự quyết định quyền nghiệp vụ chỉ bằng UI. |
| **Application (business/API)** | Kiểm tra xác thực/phân quyền người dùng; kiểm tra dữ liệu; thực hiện use case, transaction, gọi downstream; cung cấp API. | Tin tưởng input từ browser; lưu session hoặc trạng thái nghiệp vụ chỉ trong memory của một instance. |
| **Data (persistence)** | Lưu trữ, truy vấn, đảm bảo tính nhất quán và khôi phục dữ liệu. | Trực tiếp lộ cổng database ra Internet; để public browser hoặc frontend có quyền SQL quản trị. |

Tách tầng mang lại bốn lợi ích chính:

1. **Ranh giới tin cậy rõ ràng:** người dùng chỉ tiếp cận endpoint web/API; quyền database chỉ được cấp cho backend.
2. **Mở rộng độc lập:** web tăng theo lượng truy cập tài nguyên tĩnh; API tăng theo số request; database có chiến lược connection, CPU, storage và replica riêng.
3. **Triển khai và bảo trì độc lập:** sửa UI không nhất thiết phải di chuyển schema; nâng database không buộc thay frontend.
4. **Quan sát và kiểm soát chi phí:** mỗi tầng có metric, owner, SLO, service account và mức tài nguyên phù hợp.

Một hệ thống có ba package trong cùng một process cũng có thể phân lớp logic, nhưng không có khả năng triển khai độc lập. Ngược lại, ba dịch vụ triển khai độc lập mà chia sẻ mọi credential và truy cập thẳng database vẫn có ranh giới bảo mật kém.

## 2. Kiến trúc tham chiếu trên Google Cloud

### 2.1. Sơ đồ tổng thể

~~~mermaid
flowchart TB
    USER[Browser / Mobile client]
    DNS[Cloud DNS / domain]
    LB[Global external Application Load Balancer\nHTTPS + managed certificate]
    ARMOR[Cloud Armor security policy]
    WEB[Cloud Run web-frontend\nPresentation tier]
    API[Cloud Run orders-api\nApplication tier]
    VPC[Direct VPC egress\nPrivate subnet]
    SQL[(Cloud SQL PostgreSQL\nPrivate IP + HA option)]
    SECRET[Secret Manager]
    OBS[Cloud Logging / Monitoring / Trace]
    ART[Artifact Registry / CI/CD]

    USER --> DNS
    DNS --> LB
    LB --- ARMOR
    LB -->|path: / and static files| WEB
    LB -->|path: /api/*| API
    API --> VPC
    VPC --> SQL
    API -->|runtime IAM| SECRET
    ART -.-> WEB
    ART -.-> API
    WEB -.-> OBS
    API -.-> OBS
    SQL -.-> OBS
    LB -.-> OBS
~~~

**Đường xử lý chính:** browser truy cập `https://shop.example.com` qua HTTPS Load Balancer. URL map chuyển `/` và tài nguyên web đến `web-frontend`, còn `/api/*` đến `orders-api`. Hai Cloud Run services được gắn vào hai **serverless network endpoint groups (NEGs)** riêng và hai backend services của load balancer. Chỉ `orders-api` cần kết nối đến Cloud SQL bằng private IP.

Trong phương án này, frontend và API nằm **sau cùng một hostname**. Browser gọi API qua đường dẫn `/api` cùng origin, giúp giảm cấu hình CORS và nhất quán cookie/session. URL map mặc định giữ nguyên đường dẫn khi chuyển tiếp; nếu backend chỉ hỗ trợ `/orders`, bạn phải cấu hình URL rewrite hoặc để API phục vụ `/api/orders`.

### 2.2. Vai trò của từng dịch vụ

| Thành phần Google Cloud | Tầng / vai trò | Quyết định kiến trúc |
| --- | --- | --- |
| **Cloud DNS** hoặc DNS của nhà cung cấp khác | Trỏ domain đến IP của load balancer. | DNS chỉ phân giải tên, không phải firewall hoặc cơ chế xác thực. |
| **Global external Application Load Balancer** | Điểm vào HTTPS; URL map, managed certificate, routing. | Chọn khi cần domain chung, Cloud Armor và định tuyến nhiều backend. |
| **Serverless NEGs** | Liên kết backend service của LB với Cloud Run. | Mỗi NEG trỏ đến Cloud Run service ở region tương ứng. |
| **Cloud Armor** | Rule WAF, rate limiting, chặn pattern đáng ngờ tại edge. | Là lớp bổ sung; không thay kiểm tra quyền nghiệp vụ. |
| **Cloud Run `web-frontend`** | Tầng presentation, SSR hoặc serve SPA assets. | Stateless; tránh lưu session chỉ ở RAM. |
| **Cloud Run `orders-api`** | Tầng application, REST/GraphQL, logic đơn hàng. | Dùng service account riêng, concurrency/instances theo tải. |
| **Direct VPC egress** | Đường đi outbound từ API đến địa chỉ private. | Cloud Run services hỗ trợ **egress** qua Direct VPC, không biến thành VM trong VPC. |
| **Cloud SQL for PostgreSQL** | Tầng data có transaction và managed operations. | Private IP, backup, PITR, regional HA khi cần. |
| **Secret Manager** | Lưu DB password hoặc cấu hình nhạy cảm. | Cho phép riêng API runtime SA đọc đúng secret; tránh hard-code. |
| **Artifact Registry + Cloud Build/CI** | Xây, lưu image, triển khai các revision. | Pin image digest, review thay đổi và rollout có kiểm soát. |
| **Cloud Logging / Monitoring / Trace** | Quan sát request, lỗi, latency, database và chi phí. | Correlation/alerts phản ánh trải nghiệm người dùng. |

Không phải ứng dụng nào cũng cần chạy frontend trên Cloud Run. Nếu giao diện là SPA hoàn toàn tĩnh, có thể đặt assets trong **Cloud Storage + Cloud CDN** và chỉ giữ Cloud Run cho API. Lúc này tầng presentation được phân phối như static content thay vì có web process chạy riêng.

## 3. Luồng request và ranh giới tin cậy

### 3.1. Đọc danh sách đơn hàng

Ví dụ trình tự một yêu cầu:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant L as HTTPS Load Balancer
    participant W as Cloud Run Frontend
    participant A as Cloud Run API
    participant D as Cloud SQL
    B->>L: GET /orders (HTTPS)
    L->>W: Forward UI request
    W-->>B: HTML/JS/CSS
    B->>L: GET /api/orders (cookie/session)
    L->>A: Forward original path
    A->>A: Authenticate + authorize user
    A->>D: Parameterized SELECT (private TCP)
    D-->>A: Rows
    A-->>B: JSON response
~~~

**Không** đưa database credentials vào JavaScript trả cho browser. Browser gửi credential phiên/token dùng cho người dùng cuối; API xác thực danh tính người dùng, kiểm tra quyền truy cập từng đơn hàng rồi mới thực hiện SQL. Service account Cloud Run dùng để gọi API của Google Cloud, **không tự xác định user nào được xem đơn hàng**.

### 3.2. Ghi một đơn hàng

Luồng `POST /api/orders` cần có:

1. Kiểm tra phiên đăng nhập, CSRF nếu dùng cookie trong ngữ cảnh phù hợp, quyền tạo đơn và dữ liệu đầu vào.
2. Sinh idempotency key hoặc dùng request identifier để tránh tạo đơn trùng khi browser retry.
3. Mở transaction ngắn tại database, ghi đơn hàng và các dòng liên quan rồi commit.
4. Trả `201 Created` cùng ID sau khi commit.
5. Nếu cần gửi email hoặc đồng bộ kho, đặt công việc bất đồng bộ vào Pub/Sub/Cloud Tasks bằng cơ chế tin cậy như **transactional outbox**; không giữ transaction SQL mở trong lúc gọi dịch vụ ngoài.

Nếu dùng Pub/Sub, hệ thống bắt đầu mở rộng thành kiến trúc event-driven, nhưng vẫn có ba tầng cốt lõi. Event processing nên idempotent vì message có thể giao lại.

### 3.3. Public endpoint không đồng nghĩa public database

Load balancer và web/API có thể nhận request từ Internet theo chính sách sản phẩm, nhưng:

- Cloud SQL chỉ có private IP và không được truy cập trực tiếp từ browser.
- Chỉ API được kết nối đến private DB.
- API runtime service account nhận quyền cần thiết, không dùng user/deployer credential.
- UI không có quyền đọc DB secret.
- Tầng application vẫn phải kiểm tra authorization cho từng resource/tenant.

Thiết kế network, IAM và application authorization là các lớp riêng; thiếu một lớp không thể bù bằng một lớp khác.

## 4. Thiết kế ingress, load balancing và cache

### 4.1. Global external Application Load Balancer

Một external Application Load Balancer có thể cung cấp:

- External IP toàn cục và domain của website.
- HTTPS termination với Google-managed certificate.
- URL map theo host/path để chuyển `/api/*` tới API và các path khác tới frontend.
- Cloud Armor policy trên backend service.
- Cloud CDN cho nội dung được phép cache.
- Khả năng mở rộng sang nhiều region, với việc cấu hình backend và traffic policy bổ sung.

Để dùng Cloud Run làm backend, tạo **serverless NEG** trỏ tới mỗi service và đưa NEG vào backend service. Serverless NEG **không dùng health check của backend service theo kiểu VM/GKE NEG thông thường**. Hãy dùng synthetic checks, Cloud Run service health/outlier detection khi phù hợp với load balancer đã chọn, cùng Monitoring/alerting. Đừng cố thêm health-check resource vào backend service chỉ chứa serverless NEG.

### 4.2. Chặn bypass qua URL Cloud Run

Cloud Run có URL `run.app` riêng. Nếu service vẫn cho phép ingress từ mọi nguồn, người dùng có thể gọi thẳng URL này và **bỏ qua Cloud Armor/LB**.

Với backend dùng external Application Load Balancer, cấu hình Cloud Run `ingress=internal-and-cloud-load-balancing`. Cấu hình này cho phép lưu lượng từ external Application Load Balancer và các nguồn internal hợp lệ, đồng thời chặn truy cập trực tiếp từ Internet tới `run.app`. Có thể cân nhắc tắt default `run.app` URL khi chắc chắn không có Cloud Tasks, Scheduler, Pub/Sub push hoặc dịch vụ khác cần gọi URL đó; việc tắt URL có các ảnh hưởng tích hợp cần kiểm tra.

IAM Cloud Run Invoker và chính sách ingress **khác nhau**: nếu website mở cho khách công cộng qua LB, phải cho phép đường gọi HTTP đó ở tầng Cloud Run IAM (ví dụ public invocation được tổ chức cho phép), hoặc dùng Identity-Aware Proxy (IAP)/mô hình xác thực phù hợp. Ngay cả khi Cloud Run cho phép unauthenticated invocation ở tầng hạ tầng, API vẫn cần xác thực và phân quyền **người dùng cuối** tại ứng dụng.

### 4.3. Caching và HTTP headers

| Nội dung | Cache đề xuất | Lý do |
| --- | --- | --- |
| JS/CSS/assets có hash trong tên file | `public, max-age=31536000, immutable` nếu asset thực sự bất biến | Tận dụng CDN và browser cache, không sợ thay đổi nội dung dưới cùng URL. |
| Trang HTML entrypoint cập nhật thường xuyên | `no-cache` hoặc TTL ngắn | Khách nhanh nhận phiên bản frontend mới. |
| `GET /api/catalog` dữ liệu công khai | Có thể cache TTL ngắn khi thiết kế invalidation rõ | Giảm request đến API và DB. |
| `/api/orders`, profile, giỏ hàng theo người dùng | `private, no-store` khi chứa dữ liệu nhạy cảm | Không cache dùng chung giữa các người dùng. |
| Response có `Set-Cookie` hoặc authorization | Chỉ cache nếu đã thiết kế cache key và policy cẩn thận; mặc định không cache công khai | Tránh lộ dữ liệu phiên/tenant. |

Cloud CDN không tự biết response nào là dữ liệu cá nhân. Cấu hình cache mode, TTL, request/response headers và URL routing phải được kiểm tra bằng request của hai user khác nhau. Một lỗi cache nhầm thường nghiêm trọng hơn việc trang web chậm.

## 5. Application tier: Cloud Run API

### 5.1. Stateless service và scale

`orders-api` nên là container stateless, có khả năng phục vụ nhiều request đồng thời và tự phục hồi bằng cách tạo instance mới.

- Session ở cookie đã ký/mã hóa hoặc kho session ngoài (nếu cần server-side session), không lưu chỉ trong một instance.
- Upload lớn nên gửi trực tiếp đến Cloud Storage bằng signed URL thích hợp, không giữ byte array quá lớn trong RAM API.
- CPU/memory, request concurrency, min/max instances, request timeout và startup time cần dựa trên load test.
- Chỉ nhận input đã được validate và giới hạn kích thước, đặc biệt với JSON, file và query paging.

Cloud Run có thể tự động tăng instance theo tải nhưng không tự tăng giới hạn kết nối Cloud SQL. Nếu một instance tạo connection pool lớn, lượng kết nối tổng cộng có thể vượt khả năng DB.

### 5.2. Kiểm soát kết nối database

Giả sử API được giới hạn tối đa 20 instances và mỗi instance có pool 5 kết nối:

\[
\text{DB connections tối đa do API tạo} \approx 20 \times 5 = 100
\]

Đây là giới hạn lý thuyết của **pool ứng dụng**, chưa tính migration job, admin sessions, replica hoặc các service khác. Đừng thiết kế `max instances × max pool size` vượt số kết nối database có thể phục vụ an toàn.

Với Spring Boot + HikariCP, ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://PRIVATE_DB_IP:5432/orders
    username: orders_app
    hikari:
      maximum-pool-size: 5
      minimum-idle: 0
      connection-timeout: 5000
      max-lifetime: 1800000
server:
  port: 8080
~~~

DB password được truyền qua Secret Manager và biến môi trường `SPRING_DATASOURCE_PASSWORD` của **API container** (hoặc cơ chế secret mounting phù hợp). Không commit password vào `application.yml`. `PRIVATE_DB_IP` chỉ là placeholder: thay bằng IP private của Cloud SQL và bảo vệ DB connection theo yêu cầu TLS/authentication.

Cân nhắc timeout riêng cho HTTP client, database acquire/query và job bất đồng bộ. Đặt retry có giới hạn, có jitter và chỉ retry thao tác có tính idempotent hoặc được bảo vệ khỏi duplicate.

### 5.3. API contract

Ví dụ API tối thiểu:

| Endpoint | Ý nghĩa | Bảo mật cần thiết |
| --- | --- | --- |
| `GET /health/live` | Liveness, không kiểm tra DB bằng thao tác tốn kém. | Trả ít thông tin; không tiết lộ environment. |
| `GET /health/ready` | Readiness của logic dịch vụ. | Không công khai thông tin nhạy cảm hoặc tạo tải lớn. |
| `GET /api/orders` | Trả danh sách đơn hàng của user. | Authentication và tenant-aware authorization. |
| `POST /api/orders` | Tạo đơn hàng. | Validation, CSRF/cookie policy, idempotency. |
| `GET /api/orders/{id}` | Xem một đơn. | Object-level authorization; tránh IDOR. |

Một pseudocode Spring controller minh họa ranh giới nghiệp vụ:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderDto> getOrder(
            @PathVariable long id, Principal principal) {

        // Service truy vấn với userId/tenantId từ principal đã xác thực,
        // không tin tưởng userId do browser tự gửi.
        OrderDto order = service.findAccessibleOrder(id, principal.getName());
        return ResponseEntity.ok(order);
    }
}
~~~

Đoạn code chỉ minh họa. Production cần Spring Security filter chain, authentication provider, handling `404/403`, DTO mapping và query đã kiểm tra tenant. Không chỉ lọc đơn hàng ở frontend rồi trả toàn bộ đơn hàng qua API.

## 6. Data tier: Cloud SQL PostgreSQL

### 6.1. Private IP và đường egress từ Cloud Run

Cloud SQL dùng **private IP** để API truy cập qua VPC. Với Cloud Run service, cấu hình **Direct VPC egress** tới VPC/subnet có thể kết nối đến Cloud SQL, hoặc dùng Serverless VPC Access connector nếu có lý do tương thích.

Những tiền điều kiện cần xác minh:

1. Cloud SQL instance được cấu hình private networking (ví dụ Private Services Access hoặc lựa chọn private connectivity được hỗ trợ).
2. Cloud Run Direct VPC egress trỏ đúng network và subnet.
3. VPC routing và firewall cho phép kết nối từ API đến Cloud SQL private IP.
4. API dùng địa chỉ private IP và port `5432` của PostgreSQL.
5. DB user có quyền ứng dụng tối thiểu; password/identity được quản lý riêng.
6. DNS, TLS và connection timeout phù hợp.

`private-ranges-only` gửi lưu lượng đến địa chỉ private/internal phù hợp qua VPC; `all-traffic` đưa mọi egress qua VPC và có thể cần Cloud NAT/route nếu API còn gọi Internet công cộng. **Direct VPC egress không tự tạo private ingress cho Cloud Run service**; hai hướng lưu lượng được cấu hình riêng.

### 6.2. Data model và migration

Ví dụ schema đơn giản:

~~~sql
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_orders_user_created
    ON orders (user_id, created_at DESC);
~~~

Không tạo SQL schema bằng cách chạy câu lệnh tự phát mỗi lần request. Dùng **Flyway** hoặc Liquibase với migration versioned và pipeline được phê duyệt. Đối với cập nhật không tương thích, dùng **expand-and-contract**: thêm cột/bảng mới tương thích trước, cập nhật code đọc/ghi, backfill, xác minh và chỉ sau đó xóa schema cũ.

Transaction nên ngắn; tránh giữ transaction mở khi gọi dịch vụ thanh toán bên ngoài. Thiết kế index theo query thực tế và phân quyền DB account chỉ trên schema cần dùng.

### 6.3. HA, backup và DR

Cloud SQL **regional high availability** có primary và standby ở hai zone trong cùng region, giúp giảm thời gian gián đoạn khi có sự cố zone/instance. HA **không đồng nghĩa** chống mất cả region hoặc chống lỗi xóa dữ liệu do con người. Vì vậy:

- Bật automated backups và **point-in-time recovery (PITR)** theo yêu cầu RPO.
- Chọn retention hợp lý, cân nhắc backup ở location khác khi có yêu cầu disaster recovery.
- Thực hành restore vào instance mới và đo thời gian khôi phục.
- Xác nhận application tự reconnect khi DB failover, vì kết nối đang mở có thể bị ngắt.
- Nếu yêu cầu phục hồi khi cả region ngừng hoạt động, thiết kế DR đa region với replica/backup và quy trình promotion/failover riêng; không gọi Cloud SQL regional HA là multi-region DR.

RPO (Recovery Point Objective) là lượng dữ liệu có thể mất tối đa theo mục tiêu, RTO (Recovery Time Objective) là thời gian khôi phục mục tiêu. Các giá trị này cần được kiểm chứng bằng diễn tập, không suy đoán chỉ từ việc bật HA hoặc backup.

## 7. Bảo mật từ edge đến database

| Lớp | Biện pháp |
| --- | --- |
| DNS/TLS | Managed certificate, redirect HTTP→HTTPS, HSTS sau khi xác nhận domain phục vụ HTTPS ổn định. |
| Edge | Cloud Armor WAF/rate limiting, chính sách chặn abuse, monitoring HTTP 4xx/5xx. |
| Cloud Run ingress | `internal-and-cloud-load-balancing` để hạn chế bypass LB; xem xét disable default URL có kiểm soát. |
| Authentication | OIDC/OAuth, session cookie `HttpOnly`, `Secure`, `SameSite` phù hợp; MFA nếu yêu cầu; IAP nếu ứng dụng nội bộ. |
| Authorization | API kiểm tra user/tenant/resource; không dựa vào ẩn nút trên UI. |
| Service identity | Web và API dùng **hai** service accounts; API nhận quyền đọc secret và gọi API Google Cloud cần thiết. |
| Network | API có Direct VPC egress, DB private IP, firewall giới hạn lưu lượng; không expose DB public endpoint. |
| Secrets | DB password/API keys trong Secret Manager, IAM `secretAccessor` trên từng secret cần dùng. |
| Data | DB role tối thiểu, TLS/auth, backup và audit. |
| Supply chain | Artifact Registry, image scanning/signing policy khi phù hợp, pin digest, pipeline review, rollback. |

Cloud Armor bảo vệ edge nhưng không thay được input validation, object-level authorization hoặc logic chống gian lận. Tương tự, Cloud SQL private IP giảm bề mặt tấn công mạng nhưng không thay database credentials.

**Ranh giới IAM:** Cloud Run `orders-api` runtime service account chỉ cần quyền truy cập Secret Manager và các Google APIs mà code gọi. Cloud Run deployer/CI identity có quyền triển khai và `iam.serviceAccounts.actAs` khi gắn service account. End-user identity là một chủ thể khác được ứng dụng kiểm tra ở tầng HTTP. Không cấp quyền Owner/Editor chỉ để pipeline chạy được.

## 8. Khả năng mở rộng và độ tin cậy

### 8.1. Những điểm nghẽn chính

| Triệu chứng | Thành phần có thể gây nghẽn | Cách khắc phục có kiểm soát |
| --- | --- | --- |
| UI phản hồi chậm nhưng API khỏe | Render frontend, static asset, TLS roundtrip, cache miss. | Cache asset có fingerprint, giảm bundle size, SSR/SPA tối ưu. |
| API p95 tăng khi traffic tăng | Concurrency, cold starts, CPU, pool wait, downstream. | Tune concurrency/min instances, profile, load test. |
| Database hết connections | `max instances × pool size` quá lớn. | Giảm pool, đặt max instances, tối ưu query hoặc proxy/pooling khi phù hợp. |
| SQL query chậm | Index thiếu, lock wait, N+1 queries. | Query plans, index, transaction ngắn và caching đúng. |
| Lưu lượng đột biến gây 429/5xx | Quota hoặc downstream saturation. | Rate limiting, backpressure, queue, load test và alert. |
| Một region gặp sự cố | Workload và DB cùng một region. | Thiết kế multi-region/failover khi RTO/RPO yêu cầu. |

Không tăng max instances của Cloud Run vô hạn trong khi Cloud SQL là điểm nghẽn chung. Nhiều instance API có thể khuếch đại tải lên database và làm tình hình tệ hơn.

### 8.2. Khả dụng theo vùng

Cloud Run managed service chạy trong một **region**; Cloud Run quản lý hạ tầng trong region, nhưng một triển khai một region không tự động cung cấp DR sang region khác. Với yêu cầu cao, cân nhắc deploy frontend/API ở nhiều region và cấu hình external load balancer với serverless backends tương ứng. Tuy nhiên, **data tier** vẫn quyết định RTO/RPO: cần chiến lược replication, consistency, promotion và routing cho DB trước khi tuyên bố kiến trúc multi-region có khả năng khôi phục.

Đừng đồng nhất load balancer toàn cục với ứng dụng multi-region. Load balancer có external global IP nhưng nếu tất cả backend và database ở một region, failure của region đó vẫn ảnh hưởng dịch vụ.

### 8.3. SLO minh họa

Ví dụ cho hệ thống đơn hàng:

- Availability của `GET /api/orders`: 99,9% request hợp lệ hoàn thành thành công trong cửa sổ 30 ngày.
- Latency: 95% request `GET /api/orders` hoàn thành dưới 400 ms (ngưỡng minh họa).
- Tỷ lệ lỗi tạo đơn: `5xx` thấp hơn 0,1% trong điều kiện tải dự kiến.

SLO phải bắt nguồn từ trải nghiệm người dùng và baseline thực tế. Nên cảnh báo theo **error budget burn**, 5xx, p95/p99 latency, database connection saturation và synthetic user journey.

## 9. Triển khai mẫu từng bước

Ví dụ dùng project `PROJECT_ID`, region `asia-southeast1`, repository Artifact Registry `web-apps`, network `app-vpc`, subnet `app-subnet` và domain `shop.example.com`. Đây là **quy trình tham chiếu**: trước khi chạy phải tạo project, billing, network/private connectivity, Cloud SQL, secret, images và IAM. Không copy các placeholder trực tiếp sang production.

### Bước 1: Chuẩn bị API và tài nguyên nền

~~~bash
gcloud config set project PROJECT_ID

gcloud services enable \
  run.googleapis.com \
  compute.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  --project=PROJECT_ID
~~~

Chuẩn bị Cloud SQL PostgreSQL private IP trên VPC tương thích. Tạo database và DB user tối thiểu, đưa password vào Secret Manager, cấp `roles/secretmanager.secretAccessor` cho **API service account** trên đúng secret. Tạo image frontend/API trong Artifact Registry bằng CI; deploy theo **image digest** hoặc tag bất biến để rollback được.

### Bước 2: Deploy tầng frontend

~~~bash
gcloud run deploy web-frontend \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/web-apps/frontend:VERSION \
  --region=asia-southeast1 \
  --service-account=frontend-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --ingress=internal-and-cloud-load-balancing \
  --allow-unauthenticated \
  --project=PROJECT_ID
~~~

`--allow-unauthenticated` chỉ phù hợp nếu website **công khai** và organization policy cho phép. Với ứng dụng nội bộ, cân nhắc IAP và cấu hình Cloud Run invoker phù hợp thay vì công khai toàn bộ service. Frontend không cần quyền đọc DB secret hoặc kết nối DB.

### Bước 3: Deploy API với private egress

~~~bash
gcloud run deploy orders-api \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/web-apps/api:VERSION \
  --region=asia-southeast1 \
  --service-account=orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --ingress=internal-and-cloud-load-balancing \
  --network=app-vpc \
  --subnet=app-subnet \
  --vpc-egress=private-ranges-only \
  --set-secrets=SPRING_DATASOURCE_PASSWORD=orders-db-password:1 \
  --set-env-vars=SPRING_PROFILES_ACTIVE=production \
  --allow-unauthenticated \
  --project=PROJECT_ID
~~~

Ở public web architecture này, `--allow-unauthenticated` tại Cloud Run cho phép load balancer chuyển request của browser vào API; **Spring Security của API vẫn phải xác thực và phân quyền user**. Nếu không chấp nhận public invocation ở tầng hạ tầng, cần thiết kế thêm IAP hoặc lớp xác thực phù hợp trước API, đồng thời kiểm tra cách LB chuyển danh tính.

Cấp `roles/compute.networkUser` hoặc các quyền mạng cần thiết cho deployment/runtime identities theo yêu cầu của Direct VPC/Shared VPC đã chọn. Với Cloud SQL private IP, đặt JDBC URL đến private IP trong cấu hình do môi trường cung cấp. Không đặt DB password trong `--set-env-vars` hoặc commit vào Git. Nếu API dùng Cloud SQL Java Connector, kiểm tra thêm Cloud SQL Admin API và `roles/cloudsql.client` theo phương thức connector; **đường TCP trực tiếp đến private IP và connector-based auth không giống nhau**.

### Bước 4: Thiết lập load balancer

Trong Google Cloud Console hoặc Terraform, tạo theo thứ tự:

1. Một **global external Application Load Balancer** và reserved global external IP.
2. Google-managed TLS certificate cho domain; cấu hình DNS record trỏ về IP LB.
3. Một regional serverless NEG trỏ `web-frontend`, một NEG trỏ `orders-api`; mỗi NEG đặt trong cùng project/region phù hợp với Cloud Run backend.
4. Hai backend services tương ứng; gắn Cloud Armor policy theo yêu cầu.
5. URL map: `/api/*` đến backend API, mặc định `/*` đến backend frontend. Nếu cần, cấu hình rewrite và kiểm tra ứng dụng hiểu đúng path.
6. HTTPS target proxy và forwarding rule cổng 443; HTTP redirect nếu thiết kế yêu cầu.
7. Cloud CDN **chỉ** cho backend/response tĩnh phù hợp, không bật cache công khai cho response theo session.

Serverless NEG có những giới hạn riêng về health checks, timeout và cấu hình backend. Không cấu hình health check theo mẫu VM backend. Đối với hành vi failover/health, kiểm tra tính năng Cloud Run service health/outlier detection trên loại load balancer sử dụng và bổ sung synthetic monitoring.

### Bước 5: Kiểm chứng truy cập

~~~bash
curl -I https://shop.example.com/
curl -I https://shop.example.com/assets/app-HASH.js
curl -i https://shop.example.com/api/health/live
curl -i https://shop.example.com/api/orders
~~~

Kỳ vọng:

- Web phục vụ HTML/assets qua HTTPS với certificate hợp lệ.
- API health trả kết quả đã định nghĩa.
- API đơn hàng yêu cầu phiên hợp lệ; anonymous user bị từ chối theo thiết kế.
- Không thể mở PostgreSQL private IP từ Internet.
- Truy cập thẳng URL `run.app` từ Internet bị chặn bởi Cloud Run ingress.
- Thời gian response và log request có thể theo dõi trong Monitoring/Logging.

Đừng dùng `HEAD` để kiểm chứng API nếu controller chỉ hỗ trợ `GET`; một `405` khi dùng `curl -I` không đồng nghĩa backend hỏng. Phải kiểm tra đúng method/path.

## 10. Quản lý cơ sở hạ tầng bằng mã và CI/CD

Đưa resource vào Terraform, Pulumi hoặc công cụ IaC phù hợp với tổ chức. Với Terraform, có thể tách state/module thành:

~~~text
infrastructure/
  foundation/         # project, APIs, IAM, VPC, private connectivity
  data/               # Cloud SQL, backups, secrets, DB access
  applications/       # service accounts, Cloud Run services
  edge/               # serverless NEGs, backend services, URL map, TLS, Armor
  observability/      # dashboards, alerts, log sinks
~~~

Tách state tránh một pipeline ứng dụng vô tình có quyền xóa DB hoặc thay đổi toàn bộ DNS. Tuy nhiên, cần quản lý dependency giữa các state rõ ràng qua outputs, versioned modules và review.

Một pipeline triển khai đơn giản:

~~~mermaid
flowchart LR
    CODE[Git commit] --> TEST[Unit + integration tests]
    TEST --> BUILD[Build container + scan]
    BUILD --> REG[Artifact Registry]
    REG --> STAGE[Deploy staging revision]
    STAGE --> SMOKE[Smoke + security + load checks]
    SMOKE --> APPROVAL[Approval]
    APPROVAL --> PROD[Traffic rollout]
    PROD --> OBS[SLI/SLO verification]
    OBS -->|Regression| ROLLBACK[Rollback revision]
~~~

Áp dụng deploy theo revision và traffic splitting của Cloud Run cho frontend/API. Đưa migrations tương thích trước khi chuyển traffic. Với database migration gây breaking change, rollback code thường **không** thể rollback dữ liệu tự động; cần kế hoạch schema forward/backward compatibility.

## 11. Logging, metrics, traces và SLO

Trong hệ thống ba tầng, một HTTP 500 có thể xuất phát từ frontend, API hoặc database. Thiết kế telemetry đồng bộ giúp tìm đúng tầng:

| Tầng | Metrics/logs nên theo dõi | Câu hỏi vận hành |
| --- | --- | --- |
| Edge | HTTPS request rate, 4xx/5xx, Cloud Armor blocks, TLS errors, cache hit ratio. | Có vấn đề tại ingress, WAF hoặc cache không? |
| Frontend | SSR latency, instance count, cold starts, memory, JS errors (RUM nếu có). | UI chậm do render hay thiếu tài nguyên? |
| API | Request rate, p50/p95/p99 latency, exceptions, concurrency, retries, auth failures. | Endpoint nào hoặc version nào suy giảm? |
| Data | CPU, memory, disk, connection count, active transactions, query latency, lock waits. | Database là bottleneck hay connection pool hết? |
| E2E | Synthetic checkout journey, SLI success/latency, error budget burn. | Người dùng có thật sự hoàn thành thao tác không? |

Dùng **OpenTelemetry** để gắn trace context qua frontend/server-side call, API và các dependency. Ghi log JSON có `traceId`, `spanId`, `service.name`, version và request ID không nhạy cảm. Không đưa access token, cookie, password hoặc dữ liệu cá nhân vào log/trace. Khi DB chậm, trace cho thấy thời gian chờ ở SQL span và metrics cho biết connection pool hoặc CPU bị nghẽn.

Thiết lập alert theo triệu chứng người dùng (5xx, p95, burn rate, journey failure), kèm alert phụ trợ cho disk space, pool saturation, backup failure và chứng thư TLS sắp hết hạn. Mỗi alert phải có owner, mức độ ưu tiên và runbook.

## 12. Chi phí và tối ưu theo tải

Tổng chi phí không chỉ là Cloud Run requests. Bản thiết kế phải xét các nhóm:

| Thành phần | Nhóm chi phí | Đòn bẩy tối ưu |
| --- | --- | --- |
| External ALB + Cloud Armor | Load balancer, rule/policy, request processing. | Kiểm tra nhu cầu routing/WAF, hạn chế cấu hình không dùng. |
| Cloud CDN | Cache lookup, data serving/egress. | Cache assets phù hợp, tránh cache dữ liệu nhạy cảm. |
| Cloud Run frontend/API | CPU, memory, requests, instance-based options/min instances. | Tune concurrency, cold-start tradeoff, min/max instances. |
| Cloud SQL | Instance CPU/RAM, storage, HA, backup/PITR, egress. | Chọn tier theo quan sát, index/query tuning, retention hợp lý. |
| Networking | VPC egress, data transfer, Cloud NAT nếu dùng. | Route phù hợp, tránh truyền dữ liệu qua region không cần thiết. |
| Observability | Log ingest/storage, metrics và trace ingestion. | Structured logs, sampling, retention, cardinality. |
| Artifact Registry/CI | Image storage, build, scan và deployment operations. | Retention policy, xóa image cũ theo phê duyệt. |

Cloud Run có thể scale-to-zero ở một số workload, nhưng **Cloud SQL và load balancer thường tạo chi phí nền** kể cả khi ít request. Với ứng dụng tải rất nhỏ, có thể đánh giá cấu hình đơn giản hơn; với tải ổn định cao, cần so sánh chi phí với GKE hoặc Compute Engine dựa trên số liệu thực, không suy từ đơn giá một tài nguyên.

Một bài toán giả định: 10.000 user mỗi ngày, mỗi người 10 API requests thì có khoảng 100.000 API requests/ngày. Đây **không đủ** để tính bill: còn phân phối thời gian, CPU/memory per request, cache hit rate, SQL queries, data egress, HA và backup. Dùng Google Cloud Pricing Calculator với giả định có nguồn và đo thực tế sau triển khai.

## 13. Các lựa chọn thay thế và trade-off

| Kiến trúc | Khi nên chọn | Trade-off |
| --- | --- | --- |
| **Cloud Run frontend + Cloud Run API + Cloud SQL** (bài này) | Web/API container stateless; đội nhỏ muốn vận hành đơn giản. | Cold start, giới hạn runtime/concurrency, database connections cần quản lý chặt. |
| **Cloud Storage + CDN frontend + Cloud Run API + Cloud SQL** | SPA/static site; không cần SSR. | Hosting rất gọn nhưng auth, SEO/SSR và cache invalidation cần thiết kế. |
| **GKE frontend/API + Cloud SQL** | Nhiều microservices, cần Kubernetes primitives/service mesh, điều khiển scheduling sâu. | Chi phí vận hành cluster và networking phức tạp hơn. |
| **Managed Instance Group + Load Balancer + Cloud SQL** | Workload legacy hoặc cần OS/custom agents, long-running processes. | Quản trị image, patching, autoscaling, VM health. |
| **Cloud Run API + Firestore** | Dữ liệu phù hợp document model và truy vấn đã thiết kế. | Khác transaction/query model PostgreSQL, index và pricing theo operations. |

Ba tầng không bắt buộc luôn dùng quan hệ SQL; chọn data tier dựa trên consistency, query patterns, transaction boundaries, RPO/RTO và team expertise. Cũng không cần tách thành nhiều microservices chỉ để “đủ ba tầng”: một API service modular có thể dễ vận hành hơn.

## 14. Hai tình huống điều tra thực tế

### 14.1. API tăng 5xx khi có khuyến mãi

1. Monitoring cho thấy p95 tăng và 5xx tập trung ở `POST /api/orders`.
2. Cloud Run API tăng instance nhanh, nhưng Cloud SQL active connections gần trần.
3. Trace chỉ ra phần lớn latency là chờ connection pool, không phải frontend.
4. Kiểm tra `max instances × maximum-pool-size`, query plan và transaction duration.
5. Giảm burst bằng rate limit/queue, điều chỉnh concurrency/pool có kiểm soát, tối ưu transaction/query.
6. Kiểm chứng p95 và error budget hồi phục, tránh chỉ nâng Cloud Run max instances.

### 14.2. Website “mất” sau khi đổi load balancer

1. Kiểm tra DNS và certificate đã provision, HTTP→HTTPS redirect.
2. Kiểm tra URL map có route `/api/*` đúng backend API hay không.
3. Kiểm tra serverless NEG trỏ đúng Cloud Run service và region.
4. Kiểm tra Cloud Run ingress `internal-and-cloud-load-balancing` và quyền Invoker/auth model.
5. Mở Cloud Armor logs để xem rule có chặn traffic hợp lệ không.
6. Với serverless NEG, không tìm lỗi “health check firewall” giống VM backend; ưu tiên logs, synthetic probes và LB/serverless behavior.
7. Kiểm tra URL `run.app` trực tiếp từ Internet phải bị chặn theo thiết kế và không được coi đó là dấu hiệu ứng dụng lỗi.

## 15. Checklist đánh giá thiết kế

- [ ] Định nghĩa rõ UI, business/API và data tiers, cùng owner và trust boundary.
- [ ] Web/API dùng domain chung qua HTTPS Load Balancer, URL map không route sai path.
- [ ] Cloud Armor được cấu hình và kiểm thử rule trước khi enforce chặn diện rộng.
- [ ] Cloud Run ingress chặn bypass LB; Cloud Run IAM/public-access model khớp sản phẩm.
- [ ] Frontend không có DB credential hoặc quyền đọc DB secret.
- [ ] API dùng runtime service account chuyên biệt và authorization theo user/tenant.
- [ ] Cloud SQL dùng private connectivity; Direct VPC egress/subnet/routing/firewall được kiểm chứng.
- [ ] Database account chỉ có SQL privileges cần thiết; secret không nằm trong Git/image.
- [ ] Có connection pooling và giới hạn `max instances × pool size` an toàn.
- [ ] Cache policy không cache nhầm nội dung phiên hoặc dữ liệu cá nhân.
- [ ] Có Cloud SQL backup, PITR và diễn tập restore; cân nhắc regional HA theo RTO/RPO.
- [ ] Không nhầm regional HA với multi-region DR; có runbook khi region outage.
- [ ] CI/CD triển khai image bất biến, migration tương thích, traffic rollout và rollback.
- [ ] Có logs, metrics, traces, SLO, alerting và synthetic user journey.
- [ ] Đã đánh giá chi phí load balancer, Cloud Run, Cloud SQL, network, backup và logs.
- [ ] Đã thử bằng request thật: UI, API auth, database write/read, failure và recovery.

## Tài liệu tham khảo

- [Google Cloud: Set up a global external Application Load Balancer with serverless backends](https://docs.cloud.google.com/load-balancing/docs/https/setup-global-ext-https-serverless) — load balancer, serverless NEG, HTTPS và cấu hình backend.
- [Serverless network endpoint groups overview](https://docs.cloud.google.com/load-balancing/docs/negs/serverless-neg-concepts) — serverless NEGs, giới hạn backend và health checks.
- [Cloud CDN with Cloud Run and other serverless backends](https://docs.cloud.google.com/cdn/docs/setting-up-cdn-with-serverless) — CDN qua external Application Load Balancer.
- [Cloud Run ingress settings](https://docs.cloud.google.com/run/docs/securing/ingress) — `internal-and-cloud-load-balancing` và chặn gọi trực tiếp từ Internet.
- [Cloud Run security design](https://docs.cloud.google.com/run/docs/securing/security) — IAM, authentication, ingress và các biện pháp edge.
- [Cloud Run Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc) — network, subnet, egress mode và firewall.
- [Cloud SQL PostgreSQL: Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run) — private IP và kết nối PostgreSQL.
- [Cloud SQL PostgreSQL high availability](https://docs.cloud.google.com/sql/docs/postgres/high-availability) — regional HA, zone failover và recovery considerations.
- [Cloud SQL PostgreSQL point-in-time recovery](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/configure-pitr) — backup và PITR.
- [Cloud Run: Configure service identity](https://docs.cloud.google.com/run/docs/configuring/services/service-identity) — quyền và service accounts của workload.
- [Secret Manager overview](https://docs.cloud.google.com/secret-manager/docs/overview) — quản lý bí mật ứng dụng.
- [Cloud Monitoring SLO monitoring](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring) — thiết kế SLI/SLO và error budget.


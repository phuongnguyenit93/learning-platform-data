# Phân phối cấu hình tập trung và giới hạn phụ thuộc khi khởi động

> **Bối cảnh:** Software Architecture · Microservices · Cấu hình và bí mật  
> **Mục tiêu:** Thiết kế cách phân phối cấu hình nhất quán cho nhiều dịch vụ, đồng thời kiểm soát rủi ro khi Config Server, Secret Manager hoặc mạng chưa sẵn sàng lúc ứng dụng khởi động.

## 1. Vì sao quản lý tập trung có thể tạo phụ thuộc khởi động?

Giả sử một hệ thống thương mại điện tử gồm **Order Service**, **Payment Service**, **Inventory Service** và **Notification Service**. Mỗi dịch vụ cần cấu hình theo môi trường: URL kết nối, timeout, giới hạn retry, tên topic, ngưỡng nghiệp vụ, feature flag, chứng chỉ và bí mật.

Khi đặt từng giá trị thủ công trong từng container, người vận hành khó biết phiên bản nào đang chạy, ai đã thay đổi và vì sao hai instance xử lý khác nhau. **Quản lý cấu hình tập trung** giúp thống nhất nguồn dữ liệu, phân quyền, theo dõi thay đổi, xác thực và phân phối phiên bản.

Tuy nhiên, nếu mọi Pod đều phải kết nối Config Server trước khi tạo application context, **Config Server trở thành phụ thuộc cứng khi khởi động**. Khi một node bị mất hoặc cluster autoscale đúng lúc Config Server ngừng hoạt động, các Pod mới có thể không lên được dù Pod cũ đang chạy bình thường với cấu hình đã tải.

> **Phân biệt quan trọng:** Config Server không nằm trên đường phục vụ mỗi request nhưng vẫn có thể quyết định **khả năng khởi động và thay thế instance**. Đó là rủi ro về khả năng phục hồi mà chỉ kiểm thử request khi hệ thống đã chạy sẽ không phát hiện.

Mục tiêu kiến trúc là **centralized governance** nhưng không bắt buộc mọi ứng dụng phải phụ thuộc trực tiếp vào một remote configuration endpoint trong mọi giai đoạn vận hành.

## 2. Phân loại cấu hình trước khi chọn cơ chế phân phối

Không nên coi mọi giá trị là cùng một loại dữ liệu.

| Loại | Ví dụ | Đặc điểm | Hướng phân phối |
|---|---|---|---|
| **Cấu hình triển khai ổn định** | Service name, region, port, endpoint nền tảng | Ít thay đổi theo từng release | Deployment manifest, env, file gắn version |
| **Cấu hình hành vi** | HTTP timeout, retry budget, batch size | Có thể làm thay đổi nghiệp vụ | Config repository có schema và rollout |
| **Feature flag** | Bật checkout flow mới cho 10% khách hàng | Thay đổi thường xuyên, theo cohort | Flag SDK/service có cache và fallback |
| **Bí mật** | Database password, API credential, private key | Nhạy cảm, có quyền đọc và vòng đời rotation | Secret Manager hoặc secret provision được bảo vệ |
| **Policy bảo mật** | Issuer/audience tin cậy, yêu cầu MFA, denylist | Thiếu/sai có thể tạo lỗ hổng | Nguồn xác thực, validation và fail-closed |
| **Service discovery động** | Danh sách instance Order API còn healthy | Thay đổi theo topology | DNS, service discovery, mesh |
| **Dữ liệu nghiệp vụ** | Tồn kho, giá đơn, trạng thái thanh toán | Là nguồn sự thật giao dịch | Database/domain service, không đưa vào Config Server |

**Cấu hình thường không đồng nghĩa với bí mật.** Các timeout có thể nằm trong Git repository; mật khẩu và private key cần cơ chế quản lý riêng. Mã hóa một secret trong Git chưa đủ nếu không xác định rõ quyền giải mã, vị trí khóa, lịch sử rotation và thu hồi.

**Cấu hình cũng không đồng nghĩa với dữ liệu nghiệp vụ.** Không nên dùng Config Server thay thế Order Database chỉ vì cần thay đổi nội dung theo thời gian.

## 3. Vai trò kiến trúc: Control plane và data plane

~~~text
             +-------------------------------+
             | Approved config source        |
             | Git / policy repository       |
             +---------------+---------------+
                             |
                             v
             +-------------------------------+
             | Config control plane          |
             | review, validate, version     |
             | authorize, publish, audit     |
             +------+----------------+-------+
                    |                |
          config snapshots      secret references
                    |                |
                    v                v
          +----------------+  +------------------+
          | Config API /   |  | Secret Manager   |
          | GitOps / agent |  | issuance/rotation|
          +-------+--------+  +--------+---------+
                  |                    |
            push/pull/inject      trusted identity
                  |                    |
             +----+--------------------+-----+
             |          |                   |
             v          v                   v
          Order       Payment            Inventory
          Service     Service            Service
          active      active             active
          snapshot    snapshot           snapshot
             |          |                   |
             +----------+-------------------+
                       data plane
~~~

- **Nguồn sự thật:** nơi chủ sở hữu phê duyệt từng key, schema và môi trường sử dụng.
- **Control plane:** chịu trách nhiệm xây dựng phiên bản, kiểm tra policy, phân quyền đọc và ghi, ghi audit và phân phối.
- **Consumer:** mỗi service xác minh nguồn, schema, phiên bản và những ràng buộc của cấu hình trước khi áp dụng.
- **Active snapshot:** tập giá trị đã xác minh mà service đang thực sự sử dụng. Request nghiệp vụ nên đọc snapshot trong bộ nhớ hoặc local runtime thay vì truy vấn Config Server liên tục.
- **Secret plane:** cấp bí mật dựa trên workload identity, thời hạn và quyền. Nó có thể độc lập với kho cấu hình thường.

Quản lý tập trung giúp **quản trị** một nguồn cấu hình; điều đó không buộc **runtime lookup** phải tập trung. Một service có thể nhận cấu hình từ artifact đã kiểm tra trong quy trình deploy và tiếp tục phục vụ ngay cả khi Config Server đang gián đoạn.

## 4. Các mô hình phân phối thường gặp

| Mô hình | Cách hoạt động | Ưu điểm | Giới hạn |
|---|---|---|---|
| **Build/deploy-time injection** | Pipeline/controller chuẩn bị file, env, manifest hoặc volume trước khi Pod boot | Khởi động không cần gọi remote config trực tiếp; rollback dễ gắn với release | Thay đổi thường cần rollout/restart |
| **Pull khi khởi động** | Application gọi Config Server để tạo property sources | Quản trị thống nhất, cấu hình theo profile | Config Server/network trở thành dependency boot |
| **Pull định kỳ** | Client poll hoặc long poll phiên bản | Có thể cập nhật khi đang chạy | Cần cache, TTL, xử lý stale và poll storm |
| **Push/event-driven** | Publisher thông báo có version mới, consumer tải và apply | Cập nhật nhanh, giảm polling | Event mất/trùng/đảo thứ tự; cần resync |
| **Sidecar/agent** | Agent lấy config và đặt snapshot qua file/socket local | Tách distribution khỏi application | Agent cũng phải bootstrap, xác minh và cache đúng |
| **Kubernetes ConfigMap/Secret** | Kubernetes inject env hoặc mount file | Tích hợp orchestration | Env không tự cập nhật; file cập nhật không đồng nghĩa app reload |
| **Feature flag SDK** | SDK đọc evaluation rules và giữ cache | Có cohort/rollout/kill switch | Offline default và tính nhất quán cần thiết kế |

Chọn cơ chế theo **tần suất đổi**, **mức độ nhạy cảm**, **độ trễ phân phối**, **yêu cầu nhất quán**, **khả năng chấp nhận cấu hình cũ** và **SLO khởi động**.

Một hệ thống có thể kết hợp: ConfigMap versioned cho timeout, Secret Manager cho credential, DNS/mesh cho service discovery và flag SDK cho rollout tính năng.

## 5. Bootstrap dependency và vòng phụ thuộc

Một ứng dụng cần những giá trị tối thiểu để truy cập kho cấu hình: URL Config Server, environment, CA/trust bundle, danh tính workload, thời hạn kết nối và có thể cả credential.

Nếu các giá trị đó chỉ có ở chính Config Server, sẽ tạo vòng phụ thuộc:

~~~text
Ứng dụng phải biết URL + identity để truy cập Config Server
                         |
                         v
URL + identity lại chỉ có thể tải từ Config Server
                         |
                         v
Không thể bootstrap một cách xác định
~~~

Cần một **bootstrap root** nhỏ, ổn định và được cấp từ nguồn tin cậy độc lập: deployment metadata, DNS nội bộ, workload identity, trust bundle, volume do hạ tầng provision hoặc cơ chế tương đương. Tránh phụ thuộc dây chuyền dài **app → service discovery → config service → secret service → app khác** khi mọi mắt xích đều phải thành công lúc khởi động.

Ví dụ mô tả cấu hình bootstrap do ứng dụng tự định nghĩa:

~~~yaml
app:
  bootstrap:
    environment: prod
    config-endpoint: https://config.internal.example
    connection-timeout: 2s
    read-timeout: 3s
~~~

Các thuộc tính **app.bootstrap.\*** là ví dụ minh họa, không phải thuộc tính được Spring Boot tự hiểu. Code của ứng dụng hoặc thư viện bootstrap phải xử lý chúng.

Một bootstrap root tốt trả lời được: **đang kết nối đúng cấu hình của service và môi trường nào, bằng danh tính gì, và bằng cách nào xác minh server là nguồn tin cậy?**

## 6. Phân loại phụ thuộc: Bắt buộc hay có thể thiếu tạm thời?

### 6.1. Hard dependency: Thiếu thì không được phục vụ

Ví dụ:

- Ứng dụng phải xác thực JWT nhưng chưa có issuer/audience tin cậy.
- Không có credential hợp lệ để thực hiện giao dịch ghi lên database.
- Thiếu địa chỉ/payment provider của đường thanh toán bắt buộc.
- Cấu hình tenant/region sai có thể ghi dữ liệu vào nhầm vùng.
- Thiếu schema version bắt buộc để hiểu dữ liệu.

Khi thiếu hard dependency, service phải **fail closed** cho chức năng liên quan: không tự chấp nhận mọi token, không bỏ qua TLS certificate, không chọn nhầm môi trường. Tùy kiến trúc, process có thể dừng boot hoặc lên process nhưng **readiness = false**/disable tính năng tương ứng.

Hard dependency về **dữ liệu cấu hình** không nhất thiết đồng nghĩa phải gọi **remote Config Server** khi boot: một snapshot đã được provision từ pipeline và qua validation có thể là nguồn hợp lệ.

### 6.2. Soft dependency: Có fallback an toàn

Ví dụ: logging level, UI flags, sampling, HTTP timeout mặc định đã được kiểm thử hoặc batch size của background job không thiết yếu.

Nếu remote source không truy cập được, có thể dùng **default đã kiểm thử** hoặc **last-known-good snapshot (LKG)** đúng policy, ghi degraded state và hẹn cập nhật tiếp.

**Không được coi một cấu hình là optional chỉ để Pod lên trạng thái Running.** Giá trị fallback phải có nghĩa nghiệp vụ, giới hạn thời gian và đủ bảo đảm an toàn.

### 6.3. Readiness theo năng lực phục vụ thực tế

Một instance có thể **liveness = UP** nhưng **readiness = DOWN**. Liveness hỏi process còn sống hay không; readiness hỏi có đủ điều kiện nhận traffic hay chưa.

Ví dụ Notification Service không lấy được flag của giao diện email mới nhưng vẫn có thể gửi email bằng bản hiện hành. Có thể tiếp tục phục vụ nếu policy cho phép. Trái lại, Payment Service không có khóa xác minh danh tính nguồn gọi đến thì không được nhận yêu cầu thanh toán như thể mọi thứ bình thường.

## 7. Thiết kế để không tạo remote dependency cho mọi lần boot

Một số biện pháp có thể kết hợp:

1. **Pre-provision cấu hình trong release:** pipeline lấy, validate và đóng gói/đính kèm snapshot phù hợp trước khi tạo Pod.
2. **Giữ cấu hình active local:** request nghiệp vụ đọc snapshot đã kiểm tra, không phụ thuộc Config Server trong luồng request.
3. **Tách runtime refresh khỏi startup:** refresh config không thiết yếu chạy sau boot hoặc qua agent riêng; timeout fetch không mặc nhiên giết process.
4. **Bảo vệ hard dependency bằng readiness:** thiếu/sai cấu hình bắt buộc thì không nhận traffic.
5. **Giới hạn deadline bootstrap:** remote fetch cần timeout rõ; retry có backoff+jitter và tổng số lần giới hạn.
6. **Tách policy cho từng nhóm key:** logging có fallback khác secret, authentication và financial policy.
7. **Bảo toàn khả năng scale:** pod mới cần có đường lấy snapshot hợp lệ khi remote source không sẵn sàng.

Ví dụ nếu Config Server đang down, 12 Pod cũ có bản config hợp lệ trong RAM sẽ tiếp tục nhận request theo policy. Nhưng khi node mất, Pod thay thế **không tự có snapshot RAM đó**. Thiết kế phải chuẩn bị một local artifact/volume/cache hợp lệ cho **cold start**, hoặc chấp nhận Pod mới not-ready cho tới khi nguồn bắt buộc phục hồi.

## 8. Last-known-good snapshot và các giới hạn

**LKG** là snapshot đã từng được tải từ nguồn tin cậy và **thành công qua validation** trước khi kích hoạt. Nó giảm độ phụ thuộc vào một dịch vụ cấu hình trong thời gian mất kết nối.

Một LKG tốt có metadata:

~~~json
{
  "service": "order-service",
  "environment": "prod",
  "region": "ap-southeast-1",
  "configVersion": "order-prod-v17",
  "schemaVersion": 3,
  "generatedAt": "2026-11-12T00:30:00Z",
  "values": {
    "paymentTimeoutMs": 1500,
    "paymentMaxAttempts": 2,
    "inventoryTimeoutMs": 800
  }
}
~~~

Thông tin cần được kiểm tra:

- **Đúng service/environment/tenant/region:** không dùng nhầm config staging cho production hoặc tenant khác.
- **Tương thích với phiên bản binary:** schema v2 có thể không đáp ứng code chỉ hiểu schema v3.
- **Chưa vượt TTL/max staleness:** hạn stale phải phù hợp từng key, không dùng một TTL chung cho mọi loại dữ liệu.
- **Integrity và nguồn:** kiểm tra hash, chữ ký hoặc cơ chế bảo vệ theo threat model; file có thể bị sửa nếu chỉ tin tên.
- **Không chứa secret hết hạn:** lease/revocation của secret vẫn có hiệu lực dù file snapshot còn tồn tại.
- **Có cơ chế lưu cho pod mới:** bộ nhớ của pod cũ không giúp cold start của pod mới; cần artifact/volume/agent được thiết kế.

**LKG không phải phương án mặc định cho toàn bộ bí mật và security policy.** Nếu một credential đã bị thu hồi hoặc policy yêu cầu version mới trước deadline, việc tiếp tục dùng bản cũ có thể không an toàn; cần fail closed hoặc disable chức năng.

### Kích hoạt snapshot nguyên tử

Quy trình:

~~~text
Download một snapshot version N
          |
          v
Verify source + integrity + service/environment binding
          |
          v
Parse + schema validation + cross-field constraints
          |
          v
Build immutable in-memory configuration object
          |
          v
Atomic swap (activeVersion = N)
          |
          v
Audit + metrics, giữ bản trước để rollback khi được phép
~~~

Nếu snapshot mới lỗi ở bước nào, **không apply một phần**: giữ toàn bộ bản cũ hợp lệ và báo tình trạng. Tránh một request thấy timeout v17 nhưng retry budget v18 vì thay từng field rời rạc.

## 9. Versioning, rollout và tính nhất quán

Cấu hình có hai lớp nhất quán:

- **Trong một instance:** key liên quan cần được đọc từ cùng một snapshot.
- **Giữa các instance:** nhiều Pod có thể chạy version khác nhau trong thời gian rolling update.

Đối với logging hoặc một số timeout, **eventual consistency** có thể chấp nhận được. Đối với phí giao dịch, encoding message, partition mapping hoặc chính sách bảo mật, việc chạy lẫn version có thể sinh lỗi dữ liệu.

Cần xác định **compatibility window**:

- Binary mới phải hiểu config cũ còn hợp lệ trong thời gian rollout, hoặc chỉ được deploy khi config mới đã provision.
- Cấu hình mới phải tương thích với các instance cũ đang nhận traffic.
- Thay đổi phá vỡ hợp đồng nên dùng **expand → migrate → contract**, giao thức versioned hoặc rollout có cổng kiểm tra.
- Với nghiệp vụ chạy lâu, có thể phải **pin configVersion** trong workflow để không thay đổi giữa chừng.

Ví dụ checkout tính phí theo tariff v7 từ lúc tạo đơn; không nên tính phần cuối theo tariff v8 chỉ vì runtime refresh xảy ra giữa giao dịch. Đây có thể là **business policy version** cần lưu vào giao dịch, không chỉ là một key cấu hình động.

Không giả định publisher có thể cập nhật nhiều microservice một cách **atomic**. Hệ thống nên chịu được **mixed-version interval** có quan sát rõ ràng.

## 10. Spring Boot và Spring Cloud Config

Với Spring Boot 3 và phiên bản Spring Cloud tương thích, Config Client có thể tải cấu hình từ Config Server qua cơ chế **Config Data import**.

Ví dụ Order Service với remote config là phụ thuộc bắt buộc:

~~~yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      label: release-2026-11-12
~~~

Nếu remote config là nguồn tùy chọn **và ứng dụng đã có một bộ default/snapshot đủ dùng**, có thể sử dụng:

~~~yaml
spring:
  config:
    import: "optional:configserver:https://config.internal.example"
~~~

**Cần hiểu chính xác giới hạn của optional import:**

- Nó **không tự cung cấp LKG cache**.
- Nó **không tự xác thực schema, compatibility hoặc tenant binding** thay logic ứng dụng.
- Nó **không biến mọi giá trị từ remote thành optional**. Các thuộc tính bắt buộc vẫn phải được validate.
- Nó **không tự bảo đảm runtime refresh** cho bean đã tạo.
- Retry, fail-fast và timeout thực tế phụ thuộc phiên bản Spring Boot/Spring Cloud, dependency và cấu hình. Cần kiểm chứng trên stack đang dùng.

Nếu config bắt buộc không có, ứng dụng nên fail startup hoặc not-ready theo chính sách thay vì mặc nhiên dùng một giá trị nguy hiểm.

### 10.1. Validation khi bind cấu hình

Có thể thiết kế một object immutable:

~~~java
@ConfigurationProperties(prefix = "payment")
@Validated
public record PaymentProperties(
    @NotNull Duration timeout,
    @Min(1) @Max(3) int maxAttempts,
    @NotNull URI providerUrl
) {}
~~~

Ứng dụng cần bật đăng ký **@ConfigurationProperties**, dependency validation thích hợp và xây dựng validation liên trường. Ví dụ tổng thời gian retry phải nhỏ hơn deadline của nghiệp vụ; URL provider phải thuộc môi trường đúng; timeout phải dương.

Một cấu hình syntactically valid nhưng **payment.maxAttempts = 99** vẫn có thể làm hệ thống quá tải. Validation nên tồn tại cả ở **publisher** lẫn **consumer**, vì consumer là nơi cuối cùng quyết định hành vi thực tế.

### 10.2. Tránh gọi Config Server trong request path

Ví dụ nên tránh:

~~~java
@GetMapping("/orders/{id}")
OrderDto getOrder(@PathVariable UUID id) {
    int timeout = configServer.fetch("payment.timeout");
    return orderService.load(id, timeout);
}
~~~

Mỗi request nay phụ thuộc độ trễ/availability của control plane. Thay bằng một **active configuration snapshot** đã validate trong bộ nhớ; fetch/refresh đi theo luồng riêng.

## 11. Kubernetes ConfigMap và Secret: Các hành vi cần biết

**Inject qua environment variables:**

~~~yaml
env:
  - name: PAYMENT_TIMEOUT_MS
    valueFrom:
      configMapKeyRef:
        name: order-service-config
        key: paymentTimeoutMs
~~~

Giá trị được đưa vào process khi khởi động. **Sửa ConfigMap không tự thay biến môi trường của process đã chạy.** Cần restart/rollout hoặc cơ chế cấu hình runtime khác.

**Mount qua file volume:** nội dung ConfigMap/Secret có thể được Kubernetes cập nhật sau một độ trễ, nhưng ứng dụng phải **chủ động đọc lại và apply an toàn**. Các kiểu mount như **subPath** có hành vi cập nhật khác; không tự coi mọi file đã đổi là bean Spring đã refresh.

**Secret:** Base64 encoding trong Kubernetes Secret **không phải mã hóa bảo mật**. Cần kiểm soát RBAC, quyền truy cập etcd/API, encryption at rest, audit và chính sách log. Nếu dùng External Secrets Operator hoặc CSI driver, phải hiểu secret backend/controller down sẽ ảnh hưởng **provision** hay **rotation** ra sao.

**Versioned immutable ConfigMap:** thay vì sửa một key dưới tên cố định, pipeline có thể tạo ConfigMap có suffix version/hash và sửa deployment reference trong rollout. Bằng cách đó Pod nào dùng cấu hình nào trở nên rõ và rollback dễ theo release.

## 12. Bí mật và giới hạn của caching

Secret Manager giải quyết vấn đề khác Config Server thường: quản lý **thông tin nhạy cảm**, danh tính workload, ACL, thời hạn, rotation, audit và revocation.

Một ứng dụng muốn lấy payment credential nên:

1. Dùng **workload identity** hoặc cơ chế xác thực máy phù hợp, không hardcode token bootstrap trong image.
2. Chỉ có quyền đọc secret của service, environment và tenant được phép.
3. Không gửi credential trong query string, log, metric tag hoặc exception text.
4. Giữ credential trong bộ nhớ/cơ chế lưu bảo vệ phù hợp, giảm số nơi sao chép.
5. Hỗ trợ **rotation**: cập nhật connection pool/client theo kế hoạch, có overlap nếu provider hỗ trợ.
6. Xác định ứng xử khi secret backend down và khi secret đã hết lease/revoke.
7. Không bao giờ dùng default credential, tắt TLS hay bỏ qua authentication chỉ vì fetch thất bại.

Bí mật có thể có **lease ngắn** hoặc bị revoke giữa lúc hệ thống đang chạy. Một LKG snapshot cho timeout vẫn có thể hợp lệ, trong khi secret cũ trong cùng snapshot đã hết hạn. Do đó retention, TTL và fallback của **secret** phải tách khỏi **non-sensitive config**.

## 13. Runtime refresh: Tải và xác minh trước khi áp dụng

Nếu service cần thay đổi cấu hình mà không restart, phân biệt **event có phiên bản mới** và **chấp nhận phiên bản đó**.

~~~mermaid
flowchart TD
  A["Publisher công bố configVersion N"] --> B["Polling hoặc notification"]
  B --> C["Consumer tải snapshot N"]
  C --> D["Kiểm tra nguồn, schema, compatibility"]
  D --> E{"Snapshot hợp lệ?"}
  E -->|Có| F["Atomic activation N"]
  F --> G["Ghi activeVersion + metrics"]
  E -->|Không| H["Giữ snapshot cũ + cảnh báo"]
~~~

Yêu cầu:

- **Idempotent:** nhận notification trùng không gây side effect lặp.
- **Có thứ tự:** nhận event v6 sau v7 không tự downgrade.
- **Có resync:** mất một event không làm instance mãi kẹt; định kỳ so version với nguồn.
- **Atomic apply:** các key liên quan dùng chung snapshot.
- **Validation trước commit:** kiểu dữ liệu, dải giá trị, schema, tính tương thích.
- **Rollback có kiểm soát:** quay về bản đã được phê duyệt; không để notification cũ vô tình rollback.
- **Có kế hoạch rebuild resource:** đổi database connection, truststore hoặc consumer config có thể yêu cầu tái tạo client/restart thay vì đổi một biến trong RAM.

Một số cấu hình có thể update trong request kế tiếp; một số nên **pin theo transaction/workflow**. Không có một cơ chế refresh chung an toàn cho mọi class thuộc tính.

## 14. Quản lý thay đổi cấu hình như thay đổi phần mềm

Một thay đổi YAML có thể gây sự cố lớn như một thay đổi code. Ví dụ timeout về 0, retry tăng 50 lần, bật flag cho toàn bộ user hoặc thay nhầm endpoint production.

Một pipeline nên có:

~~~text
Propose + owner review
        |
        v
Schema / policy / secret scan
        |
        v
Type + range + cross-field validation
        |
        v
Compatibility check với service binary
        |
        v
Staging / synthetic tests
        |
        v
Publish immutable configVersion
        |
        v
Canary theo instance/region/tenant
        |
        v
Observe metrics, progressive rollout hoặc rollback
~~~

Cần audit: ai sửa, lý do, ticket/change ID, service/env, phiên bản trước/sau, thời gian áp dụng và kết quả kiểm tra. Không đưa plaintext secret vào diff/log.

Với thay đổi có nguy cơ lớn, rollout trước một phần nhỏ instance hoặc region. **Blast radius** phải tương ứng với phạm vi sở hữu: config của Notification Service không tự động đổi Payment Service trừ khi có hợp đồng chung rõ ràng.

## 15. Failure modes khi khởi động và phục hồi

| Sự cố | Hiện tượng thường gặp | Cách xử lý phù hợp |
|---|---|---|
| Config Server unreachable | Pod mới không hoàn tất boot | Deadline, local snapshot hợp lệ hoặc not-ready, không retry vô hạn |
| Config Server 5xx | Hàng trăm Pod retry cùng lúc | Backoff + jitter, limit concurrency, không gây retry storm |
| Config trả 200 nhưng dữ liệu không hợp lệ | Boot lỗi hoặc hành vi sai | Schema validation, từ chối activate, giữ bản trước |
| Config nhầm environment | Prod chạy endpoint staging | Kiểm tra service/env/tenant/region binding |
| Snapshot stale quá policy | Dùng quy tắc quá hạn | Disable chức năng/fail closed, alert |
| Secret Manager unavailable | Pod mới không lấy credential | Provision hợp lệ từ trước hoặc không nhận traffic |
| Secret đã revoke | Connection/auth thất bại | Refresh/rotate theo policy; không giữ cache vô hạn |
| Event config đảo thứ tự | Version cũ ghi đè version mới | Kiểm tra ordering và explicit rollback |
| Pod mới và cũ khác version | Hành vi tạm khác nhau | Mixed-version compatibility window và telemetry |
| Cluster restart khi remote down | Cold start hàng loạt thất bại | Pre-provision snapshot, rolling update an toàn |
| Controller cấu hình bị lỗi | File không refresh | Giữ active snapshot hợp lệ, alert theo staleness |
| Key toàn cục bị sửa sai | Nhiều service lỗi đồng thời | Namespace, owner, ACL và canary |

**Cấu hình trung tâm bị lỗi không nhất thiết đồng nghĩa ứng dụng hiện có phải tắt.** Đó là lý do cần active snapshot và chính sách stale. Ngược lại, **một secret hết hạn hoặc một policy an ninh bị thu hồi không được dùng mãi chỉ để duy trì availability**.

## 16. Liveness, readiness và startup probes

Khi deploy trên Kubernetes, cần phân biệt:

- **Startup probe:** quá trình khởi tạo cơ bản của ứng dụng đã hoàn thành chưa? Có thể dành đủ thời gian cho một quá trình khởi động hợp lệ, nhưng không thay việc đặt deadline rõ ràng.
- **Liveness probe:** process có còn hoạt động và có cần restart không? Không nên gọi remote Config Server trong liveness để tránh Config Server chậm biến thành restart loop.
- **Readiness probe:** instance có đủ điều kiện phục vụ request theo hợp đồng hiện tại không? Có thể phản ánh thiếu config bắt buộc, connection thiết yếu hoặc key hết hạn.

Tránh đưa tình trạng của một service cấu hình phụ vào liveness của toàn hệ thống. Nếu refresh feature flag lỗi, một instance vẫn có thể khỏe và tiếp tục phục vụ bằng snapshot hợp lệ; đánh dấu degraded/metric riêng phù hợp hơn.

Với payment endpoint thiếu issuer tin cậy hoặc thiếu secret bắt buộc, readiness phải phản ánh **không an toàn để nhận traffic**, ngay cả khi JVM vẫn trả HTTP health response.

## 17. Giảm thundering herd khi nhiều Pod khởi động

Nếu 300 Pod cùng yêu cầu config và secret sau một đợt autoscale hoặc node restart, Config Server/Secret Manager có thể quá tải, kéo dài lỗi.

Biện pháp:

- **Exponential backoff + jitter** và tổng deadline có giới hạn.
- Tôn trọng **Retry-After/429** nếu service cung cấp.
- Giới hạn concurrency trên client và controller; tránh deploy/restart toàn bộ replica đồng thời.
- Chuẩn bị artifact cấu hình versioned trước rollout nếu phù hợp.
- Sử dụng agent/cache local được bảo vệ đúng integrity/TTL.
- Giữ đủ instance cũ trong rolling deployment; cấu hình **maxUnavailable/maxSurge** theo SLO.
- Theo dõi thời gian bootstrap và số instance đang chờ cấu hình.

Backoff không sửa tận gốc phụ thuộc kiến trúc nếu **mọi Pod bắt buộc phải fetch remote thành công**. Nó chỉ giảm tải và cải thiện phục hồi khi Config Server trở lại.

## 18. Tình huống thực tế: Config Server down đúng lúc rollout

Order Service có 8 Pod đang chạy bản **configVersion=v17**. Nhóm triển khai image mới, nhưng Config Server mất kết nối 20 phút.

### Thiết kế A: Luôn fetch remote khi boot

~~~text
Config Server DOWN
        |
        v
Pod mới không thể fetch config
        |
        v
Startup fail hoặc readiness không lên
        |
        v
Rollout mắc kẹt; capacity giảm nếu Pod cũ bị thay quá nhiều
~~~

Trong khi đó Pod cũ vẫn có thể chạy với v17 trong RAM. Nếu toàn bộ Pod bị xóa hoặc node drain cùng lúc, khả năng phục hồi kém dù business service không có lỗi code.

### Thiết kế B: Config artifact đã provision

~~~text
Pipeline xác minh config v18 tương thích với image-42
        |
        v
Deploy reference: image-42 + immutable config v18
        |
        v
Pod mới đọc snapshot local đã provision
        |
        v
Parse/verify/validate → activeVersion=v18
        |
        v
Ready khi dependency thiết yếu đạt yêu cầu
        |
        v
Remote refresh lỗi → giữ v18 nếu policy còn cho phép
~~~

Ở thiết kế B, **v18 phải tồn tại và được provision thành công trước sự cố**. Một local cache nằm trong RAM của Pod cũ không giúp Pod mới. Nếu binary mới yêu cầu schema 4 nhưng artifact chỉ schema 3, phải từ chối chạy chứ không gắng dùng bản không tương thích.

### Thiết kế C: Remote import optional và default

Chỉ an toàn nếu default/snapshot đã được kiểm tra và không thiếu key thiết yếu. Nếu thiếu authentication issuer mà app chấp nhận mọi JWT để boot cho xong thì availability đạt được bằng cách phá bảo mật.

**Kết luận tình huống:** Khả năng khởi động của một Pod mới phải được thiết kế và kiểm thử riêng. Khả năng sống sót của Pod cũ không chứng minh cold start chịu được outage của Config Server.

## 19. Observability: Mỗi instance đang dùng bản nào?

Một instance nên trả lời được:

- **activeConfigVersion**, **schemaVersion**, source và thời điểm kích hoạt?
- Có đang dùng **live snapshot**, **deployment artifact** hay **LKG**?
- Lần fetch/validation gần nhất thành công lúc nào?
- Nhóm cấu hình nào đang **stale, missing, expired hoặc incompatible**?
- Bản mới nào bị reject và vì sao?
- Tình trạng config có làm instance not-ready hay disable tính năng nào?
- Có sự khác biệt version giữa các replica ngoài cửa sổ cho phép?

Ví dụ metrics tự định nghĩa:

~~~text
config_active_version_info{service,environment,version} 1
config_refresh_success_total{service} ...
config_refresh_failure_total{service,reason} ...
config_snapshot_age_seconds{service} ...
config_validation_failure_total{service,group} ...
config_bootstrap_duration_seconds{service} ...
config_fallback_total{service,source} ...
config_stale_instances{service,environment} ...
~~~

Đây là **tên metrics minh họa**, không phải tên mặc định từ Spring/Kubernetes. Không đưa secret, token, credential URL hoặc giá trị cấu hình nhạy cảm vào log/metric. Tránh nhãn cardinality cao.

Alert theo **stale quá deadline**, nhiều pod fail startup, bootstrap latency cao, mixed-version kéo dài hoặc integrity failure. Một lần refresh lỗi nhưng active snapshot còn hợp lệ có thể chỉ cần cảnh báo mức thấp hơn.

## 20. Kịch bản kiểm thử có fault injection

| Kịch bản | Kỳ vọng |
|---|---|
| Config Server down khi Pod cũ đang phục vụ | Pod giữ active snapshot hợp lệ theo policy |
| Config Server down khi Pod mới khởi động | Boot từ snapshot đã provision hoặc not-ready/fail rõ nguyên nhân |
| Remote trả YAML thiếu key bắt buộc | Validation reject, không im lặng dùng giá trị nguy hiểm |
| Remote trả key sai schema/ngoài giới hạn | Reject snapshot, không apply một phần |
| Snapshot đúng format nhưng nhầm service/env | Reject bằng identity binding |
| Local cache stale quá TTL | Fail closed hoặc disable chức năng liên quan |
| Secret hết lease/revoked | Không tiếp tục dùng ngoài policy |
| Notification v9 đến trước v8 | Không ghi lùi về v8 ngoài quyết định rollback rõ ràng |
| Hai event cùng version | Activation idempotent |
| ConfigMap đổi nhưng được inject qua env | Process chưa đổi giá trị nếu không restart |
| File volume cập nhật | App chỉ đổi active snapshot sau verify/validation |
| Hai Pod chạy version khác nhau | Hệ thống tuân thủ compatibility window |
| 200 Pod cùng boot khi remote chậm | Jitter/backoff/limit concurrency làm giảm storm |
| Config mới không tương thích binary cũ | Canary/compatibility gate chặn rollout |
| Đổi timeout giữa một workflow dài | Workflow dùng snapshot nhất quán hoặc pin version |
| Gateway/config source trả token/secret của tenant khác | Consumer từ chối, audit theo trust boundary |

Kiểm thử cả **cold start**, **warm restart**, **rollout**, **network partition**, **outage kéo dài** và **secret rotation**. Test một Pod đang sống khi Config Server down là chưa đủ.

## 21. Những anti-pattern cần tránh

**1. Gọi Config Server cho mỗi request.** Biến control plane thành dependency của data plane; dùng active snapshot local.

**2. Coi mọi giá trị có cùng mức quan trọng.** Timeout có default khác với credential hoặc issuer bảo mật; dùng policy riêng.

**3. Coi tải được YAML là hợp lệ.** Phải kiểm tra schema, range, cross-field, environment, integrity và compatibility.

**4. Refresh từng key rời rạc.** Dẫn đến trạng thái nửa cũ nửa mới; dùng snapshot nguyên tử.

**5. Bật import optional nhưng không thiết kế default.** Pod có thể boot sai hành vi; optional không thay validation.

**6. Cache bí mật vô thời hạn.** Credential có thể hết hạn hoặc bị thu hồi; respect lease và rotation.

**7. Không gắn version với runtime.** Không biết instance nào dùng cấu hình nào hoặc thay đổi nào gây incident.

**8. Dùng key toàn cục thiếu namespace/owner.** Tăng blast radius giữa service và môi trường.

**9. Coi ConfigMap volume update là Spring bean tự refresh.** Application cần cơ chế reload/activation thật.

**10. Chỉ test khi đã chạy.** Bỏ sót phụ thuộc khởi động khi deploy, autoscale hoặc restart toàn cluster.

## 22. Checklist lựa chọn kiến trúc

Trước khi phân phối một key mới, trả lời:

1. **Ai sở hữu key?** Service, team, environment, tenant và người phê duyệt nào?
2. **Đây là config, secret, discovery hay business data?** Chọn đúng source of truth.
3. **Có bắt buộc ở boot không?** Thiếu thì process dừng, not-ready hay chỉ disable một feature?
4. **Có default hoặc LKG an toàn không?** Giới hạn stale và nguồn được xác minh thế nào?
5. **Pod mới lấy dữ liệu từ đâu khi Config Server down?** Không dựa vào RAM của Pod cũ.
6. **Có cần runtime refresh không?** Nếu không, versioned deploy + rollout có thể đơn giản hơn.
7. **Giới hạn consistency là gì?** Có chấp nhận mixed version trong quá trình rollout?
8. **Cấu hình có ràng buộc cross-field hoặc cross-service không?** Có compatibility test?
9. **Secret có lease/rotation/revocation không?** Fallback khác non-sensitive config thế nào?
10. **Nguồn và dữ liệu được xác thực ra sao?** Identity, ACL, trust chain, integrity.
11. **Có thể rollback không?** Snapshot cũ còn được phép dùng và tương thích chứ?
12. **Làm sao biết config đã active?** Version, audit, metrics, readiness và alert.
13. **Nếu 200 Pod cùng khởi động thì sao?** Deadline, jitter, cache/provision và capacity.
14. **Đã kiểm thử cold start khi control plane unavailable chưa?** Không chỉ kiểm thử request.

## 23. Kết luận và câu hỏi tự kiểm tra

**Cấu hình tập trung nên tập trung quyền quản trị và nguồn sự thật, không nhất thiết tập trung mọi lần đọc tại runtime.** Để giảm phụ thuộc khởi động, service cần biết rõ bootstrap root, hard/soft dependencies, khả năng dùng snapshot hợp lệ, giới hạn stale, kiểm tra version và chính sách readiness.

Một giải pháp an toàn thường có ba lớp:

- **Control plane:** review, validate, version, audit và phân phối config/secret theo quyền.
- **Startup/runtime:** đọc snapshot tương thích, xác minh và kích hoạt nguyên tử; giữ request path độc lập với Config Server khi phù hợp.
- **Recovery:** boot Pod mới, rollout/rollback, xử lý staleness, secret rotation và lỗi nguồn cấu hình theo policy rõ ràng.

**Câu hỏi quyết định:** *Nếu Config Server mất kết nối đúng lúc toàn bộ Pod cần được thay mới, instance mới sẽ lấy bản cấu hình nào, từ nguồn tin cậy nào, và chứng minh bản đó còn hợp lệ bằng cách nào?*

Một thiết kế trả lời được câu hỏi này theo từng loại cấu hình sẽ giảm đáng kể nguy cơ sự cố Config Server làm gián đoạn cả hệ microservices.

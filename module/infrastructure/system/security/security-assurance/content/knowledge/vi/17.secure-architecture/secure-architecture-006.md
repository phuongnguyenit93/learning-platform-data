# Fail secure – Thiết kế hệ thống giữ an toàn khi thành phần gặp lỗi

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **fail secure** và phân biệt với fail-open, fail-closed, fail-safe và graceful degradation.
- Xác định trạng thái an toàn cần duy trì khi authentication, authorization, network, KMS, database, logging, policy engine hoặc dịch vụ phụ thuộc gặp lỗi.
- Thiết kế hành vi lỗi theo **mức rủi ro của hành động**, phân biệt thao tác nhạy cảm, thao tác thông thường, chức năng công khai và chức năng khẩn cấp.
- Nhận diện các lỗi thường dẫn tới fail-open: catch exception rồi allow, dùng default permissive, cache quyền quá cũ, fallback HTTP, bỏ kiểm tra certificate, bỏ qua tenant context hoặc chạy tiếp khi thiếu policy.
- Xây dựng degraded mode có giới hạn, circuit breaker, timeout, bounded retry, durable audit queue, idempotency và recovery path.
- Áp dụng fail-secure cho ứng dụng Java/Spring Boot đa tenant, service-to-service, xử lý bất đồng bộ, transaction và storage.
- Viết security requirements, failure-injection tests và hồ sơ bằng chứng để chứng minh hệ thống giữ được security invariants khi dependency lỗi.
- Quản lý finding, exception, residual risk và retest trong chương trình **SECURITY_SECURITY_ASSURANCE**.

## 1. Fail secure là gì?

**Fail secure** là nguyên tắc thiết kế trong đó khi một thành phần, cơ chế kiểm soát hoặc dependency gặp lỗi, hệ thống phải chuyển sang hoặc duy trì **trạng thái không làm suy giảm mục tiêu bảo mật ngoài mức đã được phê duyệt**. Hệ thống không tự cấp thêm quyền, bỏ xác minh, tiết lộ dữ liệu hoặc mở một đường truy cập mới chỉ để tiếp tục hoạt động.

Ví dụ, một API dùng policy engine để quyết định user có được đọc báo cáo hay không. Nếu policy engine không phản hồi, ứng dụng không thể chứng minh quyền đọc. Hành vi an toàn là **không trả báo cáo**; có thể trả lỗi tạm thời và cho phép thử lại. Hành vi nguy hiểm là bắt lỗi timeout rồi coi như user được phép.

Trong module **SECURITY_SECURITY_ASSURANCE**, fail secure là một thuộc tính kiến trúc cần được đánh giá bằng chứng. Phải trả lời được: **khi control lỗi, điều gì xảy ra, dữ liệu/quyền nào còn được bảo vệ, ai phát hiện, cách phục hồi ra sao và bằng chứng nào chứng minh hành vi đó**. Chỉ có sơ đồ hoặc policy ghi “deny by default” chưa đủ; cần test và quan sát runtime.

### Một ví dụ ngắn

| Tình huống | Hành vi fail-open | Hành vi fail-secure phù hợp |
| --- | --- | --- |
| Authorization service timeout | Cho phép request để giữ availability | Từ chối thao tác cần quyền hoặc trả trạng thái tạm thời; chỉ dùng fallback đã được thẩm định |
| Không xác minh được certificate server | Bỏ kiểm tra TLS rồi tiếp tục | Không gửi credential/payload; báo lỗi kết nối an toàn |
| KMS không khả dụng | Dùng key mặc định hoặc key hardcode | Không giải mã dữ liệu cần key; phục hồi KMS theo runbook |
| Audit pipeline ngừng nhận event | Bỏ qua audit cho mọi thao tác | Buffer bền vững, cảnh báo mất nguồn; giới hạn hoặc dừng hành động rủi ro cao theo policy |
| Feature flag service lỗi | Bật tất cả tính năng để tránh lỗi UI | Dùng default an toàn, thường là tắt tính năng nhạy cảm |
| Tenant context bị thiếu | Truy vấn không có filter tenant | Từ chối; không suy đoán tenant từ input không tin cậy |

**Fail secure không có nghĩa mọi lỗi đều phải làm tắt toàn bộ hệ thống.** Một trang nội dung công khai có thể vẫn phục vụ khi hệ thống analytics lỗi. Một endpoint health không chứa dữ liệu nhạy cảm có thể vẫn hoạt động. Cần xác định rõ hành động nào được phép tiếp tục, hành động nào phải bị giới hạn và lý do.

## 2. Phân biệt fail-secure, fail-closed, fail-open và fail-safe

Các thuật ngữ này thường bị dùng thay thế nhau, nhưng không hoàn toàn giống nhau.

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Fail-secure** | Khi lỗi, trạng thái bảo mật không suy giảm ngoài policy được duyệt | Authorization không xác minh được thì không tiết lộ dữ liệu |
| **Fail-closed** | Khi không thể xác định điều kiện cho phép, đóng quyền truy cập/đường thực hiện | Firewall hoặc authorization gate từ chối khi policy engine lỗi |
| **Fail-open** | Khi control lỗi, hệ thống cho phép tiếp tục mà không có kiểm soát dự kiến | Không kết nối được rate limiter nên bỏ giới hạn mọi request |
| **Fail-safe** | Thuật ngữ thường dùng trong safety engineering: lỗi đưa hệ thống về trạng thái an toàn đối với nguy cơ được xét | Máy dừng chuyển động khi cảm biến an toàn báo lỗi |
| **Graceful degradation** | Giảm chức năng có kiểm soát để duy trì phần dịch vụ còn an toàn | Cho xem nội dung công khai nhưng tạm dừng export dữ liệu nhạy cảm |

**Fail-closed thường là một cách triển khai fail-secure**, nhất là với access control, nhưng không phải lúc nào cũng là lựa chọn đúng cho mọi chức năng. Một hệ thống điều khiển an toàn hoặc dịch vụ thiết yếu có thể cần chế độ vận hành suy giảm được thiết kế và phê duyệt. Khi đó, mục tiêu là **giữ an toàn trong khi duy trì chức năng tối thiểu**, không đơn giản đóng tất cả.

Fail-safe cũng không tự đồng nghĩa fail-secure. Một hệ thống có thể dừng ở trạng thái an toàn về vật lý nhưng lại để lộ dữ liệu trong log hoặc mở quyền quản trị. Cần nêu rõ **loại an toàn, hazard/risk và thuộc tính đang bảo vệ**.

### Ma trận quyết định theo hành động

| Hành động | Dependency lỗi | Hướng hành vi |
| --- | --- | --- |
| Đọc tài liệu công khai | Analytics không khả dụng | Có thể tiếp tục, bỏ analytics và không mở thêm quyền |
| Đọc hồ sơ cá nhân | Authorization không phản hồi | Không trả dữ liệu; thông báo thử lại |
| Tạo thanh toán | Idempotency store hoặc fraud control lỗi | Không tự tạo giao dịch không kiểm soát; đưa vào trạng thái xử lý an toàn đã thiết kế |
| Export toàn bộ dữ liệu tenant | Audit store không sẵn sàng | Có thể chặn hoặc hoãn cho đến khi audit được ghi bền vững |
| Health check không nhạy cảm | SIEM lỗi | Có thể trả health status giới hạn, không tiết lộ cấu hình bí mật |
| Thu hồi token bị lộ | IdP chính không khả dụng | Dùng quy trình khẩn cấp/containment đã được thiết kế; không bỏ qua revocation |

## 3. Bắt đầu từ security invariant

Không thể quyết định fail secure nếu chưa biết **điều gì tuyệt đối không được xảy ra** khi hệ thống gặp lỗi.

Một *security invariant* là điều kiện bảo mật phải luôn được giữ trong phạm vi kiến trúc và giả định đã xác định. Ví dụ:

- User tenant A không đọc được dữ liệu tenant B.
- Chỉ principal đã được xác thực và cấp quyền mới thực hiện action nhạy cảm.
- Khi không xác minh được server identity, client không gửi credential hoặc payload.
- Workload không có quyền vượt khỏi resource scope đã cấp.
- Không ghi raw secret vào log, kể cả trong nhánh xử lý lỗi.
- Một giao dịch không bị thực hiện hai lần do retry hoặc failover.
- Audit evidence quan trọng không bị âm thầm bỏ mất khi collector ngừng nhận.

### Viết invariant có thể kiểm tra

| Invariant ID | Điều kiện phải giữ | Failure condition |
| --- | --- | --- |
| **INV-FS-01** | Chỉ quyết định ALLOW đã được xác minh mới cho phép đọc sensitive resource | Policy engine timeout nhưng request vẫn trả dữ liệu |
| **INV-FS-02** | Mọi query dữ liệu tenant phải có trusted tenant scope | Tenant context null dẫn tới query không filter |
| **INV-FS-03** | TLS peer không hợp lệ thì kết nối không được tiếp tục | Certificate verification exception bị bỏ qua |
| **INV-FS-04** | Quyền workload không tăng khi IAM/STS không khả dụng | Fallback dùng shared admin credential |
| **INV-FS-05** | Action yêu cầu audit bền vững phải có evidence theo policy | Audit publish lỗi nhưng action vẫn hoàn tất không dấu vết |
| **INV-FS-06** | Retry không nhân đôi side effect | Timeout sau commit khiến payment được tạo lần nữa |
| **INV-FS-07** | Dữ liệu/credential không xuất hiện trong error response hoặc log trái policy | Stack trace/payload/token được trả ra client hoặc log |
| **INV-FS-08** | Khôi phục dependency không tự mở lại quyền đã bị thu hồi | Cache policy cũ tiếp tục cho phép sau khi policy mới có hiệu lực |

Invariant phải gắn với **asset, actor, action, resource, boundary và điều kiện**. Câu “hệ thống luôn an toàn” không có tiêu chí nghiệm thu.

## 4. Threat model: lỗi có thể biến thành đường bypass như thế nào?

Fail-secure review không chỉ xem lỗi kỹ thuật; cần phân tích **lỗi đó thay đổi quyết định bảo mật ra sao**.

| Risk ID | Lỗi ban đầu | Cách hệ thống có thể fail-open | Tác động |
| --- | --- | --- | --- |
| **RISK-FS-01** | Policy engine timeout | Catch exception và trả **true** | Truy cập trái quyền |
| **RISK-FS-02** | Cache authorization quá cũ | Tiếp tục dùng quyền đã bị thu hồi | Cửa sổ truy cập trái phép |
| **RISK-FS-03** | Tenant context thiếu | Query bỏ điều kiện tenant | Cross-tenant data leak |
| **RISK-FS-04** | Certificate/CA validation lỗi | Tắt hostname/CA verification | Gửi credential tới endpoint giả |
| **RISK-FS-05** | KMS/secret manager outage | Dùng key mặc định hoặc hardcode | Lộ dữ liệu/credential |
| **RISK-FS-06** | Audit pipeline lỗi | Bỏ audit rồi tiếp tục thao tác đặc quyền | Mất khả năng truy vết |
| **RISK-FS-07** | Rate limiter lỗi | Không giới hạn request | Brute force, scraping hoặc DoS |
| **RISK-FS-08** | Queue consumer retry | Xử lý cùng job nhiều lần | Giao dịch trùng hoặc gửi dữ liệu lặp |
| **RISK-FS-09** | Feature flag service lỗi | Mặc định bật chức năng admin/export | Lộ chức năng nhạy cảm |
| **RISK-FS-10** | Config/policy không tải được | Dùng cấu hình permissive hoặc giá trị rỗng | Tắt control mà không ai biết |
| **RISK-FS-11** | Logging/monitoring mất nguồn | Dashboard coi không có event là không có sự cố | Không phát hiện lạm dụng |
| **RISK-FS-12** | Failover database split-brain | Ghi vào replica sai trạng thái | Mất toàn vẹn hoặc bỏ qua kiểm tra |

### Attack path ví dụ

~~~mermaid
flowchart TD
    A["Attacker gửi request đọc report tenant B"] --> B["API gọi policy engine"]
    B --> C{"Policy engine phản hồi?"}
    C -- "Không" --> D["Code catch lỗi và mặc định ALLOW"]
    D --> E["API query database"]
    E --> F["Trả report tenant B"]
    C -- "Có" --> G{"Decision được xác minh?"}
    G -- "ALLOW" --> E
    G -- "DENY / INDETERMINATE" --> H["Từ chối hoặc trả lỗi tạm thời"]
~~~

Điểm lỗi không nằm ở việc policy engine bị timeout đơn thuần. **Lỗi thiết kế nghiêm trọng là biến “không biết” thành “được phép”.** Cần giữ riêng ba kết quả: ALLOW, DENY và INDETERMINATE.

## 5. Thiết kế trạng thái quyết định rõ ràng

Một lỗi phổ biến là dùng boolean cho mọi kết quả. **false** có thể là deny hợp lệ, nhưng timeout, dữ liệu không hợp lệ và policy không tải được lại là tình huống khác. Nếu code chuyển mọi lỗi thành **true** hoặc dùng giá trị mặc định thiếu rõ ràng, hệ thống có thể mở quyền.

### Ba trạng thái tối thiểu

| Decision | Ý nghĩa | Hành động |
| --- | --- | --- |
| **ALLOW** | Có quyết định cho phép từ policy/nguồn tin cậy và đủ context | Chỉ tiếp tục đúng action/resource/scope |
| **DENY** | Policy xác định hành động không được phép | Từ chối, ghi event phù hợp |
| **INDETERMINATE** | Không thể đưa ra quyết định đáng tin: timeout, dependency lỗi, context thiếu hoặc response sai | Không coi là ALLOW; xử lý theo risk policy |

**INDETERMINATE** không nhất thiết luôn trả cùng một HTTP status. Với thao tác nhạy cảm, thường nên từ chối và trả lỗi tạm thời nếu nguyên nhân là dependency unavailable; với policy xác định DENY, trả từ chối. Response bên ngoài phải tránh tiết lộ chi tiết nội bộ hoặc sự tồn tại của tài nguyên.

### Trạng thái của control cũng cần phân biệt

- **ENFORCED:** control đang được áp dụng và có evidence.
- **DEGRADED:** control còn một phần năng lực, theo fallback được phê duyệt.
- **UNAVAILABLE:** không thể thực hiện kiểm tra cần thiết.
- **BYPASSED:** control bị bỏ qua theo cấu hình hoặc lỗi.
- **UNKNOWN:** thiếu telemetry/evidence để xác nhận.

Không được hiển thị **UNKNOWN** như **HEALTHY** hoặc **PASS**. Nếu không đo được tình trạng policy enforcement, đó là một khoảng trống assurance.

## 6. Quyết định fail secure theo mức rủi ro

Không phải dependency nào lỗi cũng cần dừng mọi hoạt động. Hãy phân loại action và đặt **failure behavior** trước khi triển khai.

### Ví dụ ma trận

| Mức hành động | Ví dụ | Khi control quyết định lỗi | Hướng xử lý |
| --- | --- | --- | --- |
| Công khai/không nhạy cảm | Trang giới thiệu, health status giới hạn | Analytics hoặc recommendation lỗi | Tiếp tục phần công khai, bỏ tính năng phụ |
| Dữ liệu người dùng thông thường | Xem đơn của chính mình | Authorization service unavailable | Dùng cache chỉ khi policy cho phép rõ, còn freshness và scope; nếu không thì từ chối tạm thời |
| Dữ liệu nhạy cảm | Hồ sơ tài chính, export | Policy/tenant context không xác minh được | Không tiết lộ; trả lỗi an toàn |
| Privileged/admin | Thay IAM, cấu hình, khóa | MFA/approval/audit không sẵn sàng | Chặn hoặc yêu cầu kênh khẩn cấp có kiểm soát |
| Giao dịch không thể lặp | Thanh toán, hoàn tiền | Idempotency/fraud dependency lỗi | Không thực hiện side effect không kiểm soát; lưu trạng thái pending nếu thiết kế |
| Incident response | Thu hồi credential bị compromised | IdP chính lỗi | Dùng break-glass/containment path đã phê duyệt, audit độc lập |
| Safety/essential operation | Chức năng có nguy cơ gây hại khi dừng | Security dependency lỗi | Dùng degraded mode đã phân tích safety/security và được phê duyệt |

### Các câu hỏi ra quyết định

1. Nếu cho phép tiếp tục, dữ liệu/quyền/tài sản nào có thể bị ảnh hưởng?
2. Nếu từ chối, tác động availability/safety/continuity là gì?
3. Có fallback nào vẫn giữ invariant và giới hạn rõ scope không?
4. Fallback dựa trên identity, policy hoặc key nào; có cùng điểm lỗi với control chính không?
5. Fallback có thời hạn, giới hạn số lần, owner và audit trail không?
6. Khi dependency phục hồi, làm sao đối soát các action trong thời gian degraded?
7. Ai có thẩm quyền phê duyệt exception và khi nào phải dừng fallback?

**Không chọn fail-open chỉ vì sợ ảnh hưởng SLA.** Cũng không chọn fail-closed một cách máy móc nếu có thể tạo rủi ro an toàn hoặc làm mất chức năng thiết yếu. Phải đánh giá risk trade-off, xác định chế độ suy giảm và kiểm thử.

## 7. Dependency failure: hành vi cần thiết theo từng lớp

### 7.1. Authentication và identity provider

Khi IdP không khả dụng:
- Không cấp session/token mới dựa trên danh tính chưa xác minh.
- Token đã phát hành có thể tiếp tục được chấp nhận **chỉ theo chính sách validation, expiry, revocation và risk đã được duyệt**.
- Không tự bỏ kiểm tra issuer, signature, audience hoặc expiry.
- Với admin/high-risk action, cần xem độ mới của trạng thái MFA/revocation; nếu không đủ tin cậy thì từ chối hoặc chuyển sang break-glass có kiểm soát.
- Health endpoint có thể tiếp tục cung cấp thông tin giới hạn, không trả user data.

### 7.2. Authorization/policy engine

Khi PDP (Policy Decision Point) hoặc policy store lỗi:
- Giữ ba trạng thái ALLOW/DENY/INDETERMINATE.
- Không biến timeout thành allow.
- Cache decision chỉ khi có policy rõ: key gồm principal/action/resource/context cần thiết, version, TTL, revocation behavior và giới hạn rủi ro.
- Quyền đặc quyền, cross-tenant, export và hành động phá hủy thường cần freshness chặt hơn.
- Ghi nhận degraded mode và source health; không báo PASS khi policy evaluation không thực hiện được.

### 7.3. KMS và secret manager

Khi không lấy được key/secret:
- Không dùng giá trị mặc định, key hardcode hoặc secret từ môi trường khác.
- Không tự xuất plaintext ra log hoặc file tạm để “khắc phục”.
- Thao tác cần decrypt/sign/authenticate có thể bị từ chối hoặc đưa vào hàng chờ an toàn.
- Secret cache nếu được phép phải có TTL, scope, protection, revocation và behavior khi hết hạn.
- Theo dõi key access/rotation; phân biệt KMS unavailable với key revoked hoặc access denied.

### 7.4. Database và data store

Khi database không khả dụng:
- Không trả dữ liệu cũ từ cache nếu freshness/authorization không được bảo đảm.
- Không bỏ tenant filter hoặc chuyển sang tài khoản DB quyền cao.
- Transaction chưa rõ commit status phải được kiểm tra idempotency trước retry.
- Failover phải bảo vệ consistency, ownership và quyền trên replica.
- Read-only degraded mode chỉ áp dụng khi nguồn dữ liệu, quyền và độ mới được xác minh.

### 7.5. Network/TLS và service-to-service

Khi TLS handshake hoặc certificate validation lỗi:
- Không tắt hostname verification, trust-all hoặc fallback HTTP.
- Retry có giới hạn và backoff; không lặp request có side effect nếu chưa idempotent.
- Kiểm tra endpoint, DNS, CA bundle, expiry và rotation theo runbook.
- Nếu mTLS identity không xác minh được, không coi peer là service đáng tin.
- Direct route hoặc proxy bypass không được mở để “đi vòng” control.

### 7.6. Logging, audit và SIEM

Khi log collector/SIEM lỗi:
- Phân biệt event vận hành thường với audit event bắt buộc cho hành động nhạy cảm.
- Dùng buffer bền vững có giới hạn dung lượng, chống sửa/xóa theo khả năng; theo dõi backlog và mất nguồn.
- Với thao tác đặc quyền cần audit trước/synchronously, không thực hiện nếu không thể ghi bằng chứng theo requirement.
- Các hoạt động ít rủi ro có thể tiếp tục nếu có cơ chế lưu cục bộ và đối soát được phê duyệt.
- Không ghi raw secret hoặc payload để bù cho thiếu log.
- Khi khôi phục, replay/đối soát event và ghi rõ khoảng thời gian không có coverage.

### 7.7. Rate limiter và abuse detection

Nếu rate limiter phân tán lỗi:
- Không tự bỏ toàn bộ giới hạn ở endpoint nhạy cảm.
- Có thể dùng local conservative limit hoặc quota dự phòng có giới hạn.
- Ưu tiên bảo vệ login, reset credential, export, search rộng và endpoint tiêu tốn tài nguyên.
- Nếu fallback local không bảo đảm global quota, ghi rõ risk và theo dõi.
- Khi không thể giữ giới hạn cần thiết, chặn hoặc hạn chế chức năng có nguy cơ cao theo policy.

### 7.8. Queue và asynchronous worker

Nếu queue, consumer hoặc dependency downstream lỗi:
- Không đánh dấu job hoàn thành khi chưa xác nhận side effect.
- Retry phải có backoff, giới hạn và idempotency key.
- Kiểm tra lại authorization/ownership khi worker thực thi, không chỉ lúc job được tạo.
- Dead-letter queue cần quyền, retention và quy trình replay riêng.
- Message hết hạn hoặc không còn owner không tự được xử lý bằng quyền cũ.
- Khi replay, không bỏ qua tenant, state hoặc approval hiện tại.

### 7.9. Feature flag và configuration service

Nếu không tải được feature flags/config:
- Các chức năng nhạy cảm mới, admin, export rộng hoặc experimental nên có default an toàn đã được xác định.
- Không dùng giá trị null/empty làm trạng thái “bật”.
- Cấu hình bảo mật không hợp lệ cần khiến startup/readiness thất bại hoặc service vào degraded mode đã định nghĩa.
- Không cho phép config cũ tiếp tục vô hạn; phải có version, age limit và alert.
- Không để một config service outage tự động tắt validation hoặc mở route.

## 8. Graceful degradation: duy trì phần an toàn

Một degraded mode tốt có **phạm vi chức năng rõ, thời hạn, dependency và invariant**.

### Ví dụ: report platform

| Chế độ | Chức năng | Điều kiện |
| --- | --- | --- |
| **NORMAL** | Read, create, export theo authorization bình thường | IdP, policy, DB, storage, audit hoạt động |
| **LIMITED_READ** | Đọc dữ liệu không nhạy cảm từ nguồn/cache được xác minh | Policy freshness và tenant scope còn đạt |
| **NO_EXPORT** | Tạm dừng export/download file | Storage signing, audit hoặc policy unavailable |
| **PUBLIC_ONLY** | Chỉ phục vụ nội dung công khai/health giới hạn | Identity/policy dependency unavailable |
| **RECOVERY** | Đối soát job, audit backlog, token và quyền sau outage | Dependency đã phục hồi, owner xác nhận |

~~~mermaid
stateDiagram-v2
    [*] --> NORMAL
    NORMAL --> LIMITED_READ: Dependency phụ lỗi, fallback đã duyệt
    NORMAL --> NO_EXPORT: Storage / audit / export control lỗi
    NORMAL --> PUBLIC_ONLY: Identity hoặc policy không thể xác minh
    LIMITED_READ --> RECOVERY: Dependency phục hồi
    NO_EXPORT --> RECOVERY: Dependency phục hồi
    PUBLIC_ONLY --> RECOVERY: Identity/policy phục hồi
    RECOVERY --> NORMAL: Reconciliation + verification PASS
    RECOVERY --> LIMITED_READ: Chưa đủ điều kiện mở toàn bộ
~~~

Không tự chuyển **RECOVERY → NORMAL** chỉ vì health check xanh. Cần:
- Xác nhận policy/config version mới nhất đã đồng bộ.
- Đối soát job, transaction và audit backlog.
- Xác nhận credential/keys bị revoke vẫn không hoạt động.
- Chạy smoke và negative tests trọng yếu.
- Có owner/monitoring phê duyệt mở lại chức năng theo risk.

### Fallback phải có giới hạn

Một fallback có thể chấp nhận khi:
- Mục tiêu bảo mật vẫn được giữ.
- Dữ liệu/quyền/resource scope được giới hạn.
- Thời gian và số lượng action có giới hạn.
- Có owner, monitoring, audit và điều kiện dừng.
- Có cách quay về trạng thái chuẩn và xác minh.
- Không dựa vào cùng dependency đang lỗi hoặc một credential mạnh hơn không kiểm soát.

Nếu không chứng minh được các điều kiện này, fallback là **một exception hoặc gap**, không tự coi là lớp dự phòng an toàn.

## 9. Cache authorization và policy freshness

Cache có thể tăng availability nhưng là một trong những nơi dễ làm fail-secure sai.

### Những lỗi thường gặp

- Cache key chỉ dùng userId, bỏ action/resource/tenant.
- Cache một quyết định ALLOW rồi tái sử dụng cho resource khác.
- Không gắn policy version hoặc thời điểm đánh giá.
- Cache không invalidated khi quyền bị revoke.
- Khi PDP timeout, fallback dùng bất kỳ entry nào còn trong cache, không xét độ nhạy.
- Một cache shared giữa tenant không phân tách đúng context.

### Quy tắc thiết kế

1. Key phải bao gồm các thuộc tính cần để quyết định đúng: principal, action, resource, tenant/context và policy version phù hợp.
2. Đặt TTL theo **risk và tốc độ thay đổi quyền**, không dùng một TTL chung.
3. Quyền đặc quyền, export, quản trị và dữ liệu nhạy cảm cần freshness chặt hơn hoặc không cho fallback.
4. Xử lý revoke/deny update theo cơ chế invalidation/version.
5. Khi cache miss hoặc entry hết hạn, không suy ra ALLOW.
6. Nếu dùng stale-while-revalidate, xác định chính xác action nào được phép dùng stale decision và điều kiện dừng.
7. Test cross-tenant và revoke ngay sau khi cache được tạo.

### Ví dụ ma trận cache

| Loại quyết định | PDP lỗi | Hành vi cache có thể cân nhắc |
| --- | --- | --- |
| Trang công khai | Không cần PDP | Tiếp tục theo policy công khai |
| Read-only dữ liệu ít nhạy cảm | Policy có thể hỗ trợ bounded stale read | Chỉ dùng entry còn trong TTL/version/scope được duyệt |
| Customer private data | Không xác minh được quyền | Từ chối tạm thời nếu không có fallback đủ tin cậy |
| Privileged/admin | Policy/revocation không rõ | Không dùng stale ALLOW |
| Export/delete/financial action | Quyền thay đổi có tác động lớn | Yêu cầu decision mới hoặc workflow dự phòng được phê duyệt |

## 10. Transaction, retry và side effect an toàn

Fail secure không chỉ là từ chối quyền. Một hệ thống có thể tạo **side effect một phần** rồi gặp lỗi và vô tình cho phép lặp hoặc để trạng thái không nhất quán.

### Ví dụ payment

1. API ghi nhận thanh toán vào database.
2. Gửi request tới payment provider.
3. Provider xử lý thành công nhưng response timeout.
4. API retry và tạo giao dịch thứ hai vì không có idempotency.
5. Audit event cũng không ghi được.

Kênh TLS và authentication có thể hoạt động hoàn hảo, nhưng tính toàn vẹn nghiệp vụ đã thất bại.

### Các nguyên tắc

- Dùng idempotency key ổn định cho action có side effect.
- Gắn trạng thái rõ: **PENDING**, **CONFIRMED**, **FAILED**, **UNKNOWN/RECONCILIATION_REQUIRED**.
- Không suy từ timeout rằng giao dịch chưa xảy ra.
- Dùng transaction/outbox pattern khi cần bảo đảm trạng thái DB và event có thể đối soát.
- Retry có backoff, jitter và giới hạn; tránh retry storm.
- Revalidate authorization và business state khi worker xử lý.
- Có reconciliation job và audit record để xử lý kết quả không xác định.

~~~mermaid
sequenceDiagram
    participant API as Spring Boot API
    participant DB as Database
    participant OUT as Outbox
    participant W as Worker / Provider
    API->>DB: Tạo operation PENDING với idempotency key
    API->>OUT: Ghi event trong cùng transaction
    DB-->>API: Commit
    OUT-->>W: Publish event
    W->>W: Kiểm tra authorization và idempotency
    W->>W: Gọi provider theo operation ID
    W-->>DB: Cập nhật trạng thái và kết quả
    Note over W,DB: Nếu timeout, reconcile trước khi retry side effect
~~~

Sơ đồ minh họa một pattern; tính nguyên tử giữa DB/outbox, broker delivery và provider side effect phụ thuộc implementation. Không tuyên bố “exactly once” chỉ vì queue hoặc transaction được bật.

## 11. Audit và logging khi dependency bị lỗi

Một chương trình fail-secure phải bảo vệ cả **khả năng truy vết**. Nhưng không nên chặn mọi chức năng khi SIEM lỗi nếu có phương án lưu và đối soát an toàn.

### Phân loại event

| Loại event | Ví dụ | Hành vi khi collector unavailable |
| --- | --- | --- |
| Debug/performance | Timing, cache hit, trace span | Có thể sampling/drop theo policy; không chứa sensitive payload |
| Security telemetry | Login failure, policy deny, anomalous request | Buffer/queue có giới hạn, alert source-health |
| Audit quan trọng | Thay IAM, export dữ liệu nhạy cảm, key operation | Yêu cầu ghi bền vững trước/sát side effect nếu requirement đòi hỏi |
| Incident evidence | Dấu vết liên quan compromise/abuse | Bảo toàn theo incident process, access/integrity kiểm soát |
| Public health | Service liveness không nhạy cảm | Có thể tiếp tục, response không lộ cấu hình/secret |

### Durable audit queue

Một buffer audit cục bộ cần:
- Giới hạn dung lượng và thời gian; có cảnh báo backlog.
- Bảo vệ tính toàn vẹn và quyền đọc/ghi.
- Không chứa raw credential hoặc payload thừa.
- Có event ID, sequence/time, source identity, version và correlation.
- Có replay/deduplication và đối soát sau phục hồi.
- Có hành vi khi buffer đầy được quy định trước.

Nếu thao tác privileged cần audit trước khi thực hiện, buffer phải **được ghi bền vững thành công** theo yêu cầu. Nếu không, từ chối hoặc hoãn action. Với thao tác ít rủi ro có thể chấp nhận tiếp tục trong giới hạn và ghi nhận evidence gap.

## 12. Java 17: giữ trạng thái INDETERMINATE khi policy service lỗi

Ví dụ sau minh họa cách tránh biến lỗi dependency thành ALLOW. AuthorizationPolicyClient đại diện cho client tới policy engine; nó có thể timeout hoặc trả kết quả không hợp lệ.

~~~java
import java.util.Objects;

public final class AuthorizationGuard {

    public enum Decision {
        ALLOW,
        DENY,
        INDETERMINATE
    }

    public record PolicyDecision(
            Decision decision,
            String reasonCode) {}

    public interface AuthorizationPolicyClient {
        PolicyDecision evaluate(
                String principalId,
                String action,
                String resourceId,
                String tenantId) throws Exception;
    }

    private final AuthorizationPolicyClient client;

    public AuthorizationGuard(AuthorizationPolicyClient client) {
        this.client = Objects.requireNonNull(client);
    }

    public PolicyDecision evaluate(
            String principalId,
            String action,
            String resourceId,
            String tenantId) {

        if (principalId == null || action == null
                || resourceId == null || tenantId == null) {
            return new PolicyDecision(
                    Decision.INDETERMINATE, "MISSING_CONTEXT");
        }

        try {
            PolicyDecision result = client.evaluate(
                    principalId, action, resourceId, tenantId);

            if (result == null || result.decision() == null) {
                return new PolicyDecision(
                        Decision.INDETERMINATE, "INVALID_POLICY_RESPONSE");
            }
            return result;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return new PolicyDecision(
                    Decision.INDETERMINATE, "POLICY_INTERRUPTED");
        } catch (Exception ex) {
            // Không log token, request body hoặc dữ liệu nhạy cảm.
            // Ghi correlation ID và error category ở tầng tích hợp.
            return new PolicyDecision(
                    Decision.INDETERMINATE, "POLICY_UNAVAILABLE");
        }
    }

    public static boolean mayProceed(PolicyDecision result) {
        return result != null && result.decision() == Decision.ALLOW;
    }
}
~~~

**Điểm quan trọng:**
- Chỉ ALLOW mới cho phép tiếp tục.
- DENY và INDETERMINATE đều không được cấp quyền.
- Context thiếu hoặc response sai định dạng không biến thành ALLOW.
- Lỗi dependency được phân loại để tầng API có thể trả response phù hợp và tạo telemetry.
- Ví dụ không quy định timeout/retry của HTTP client; implementation cần timeout hữu hạn, circuit breaker và retry có giới hạn.
- Không dùng một exception catch rộng để che lỗi lập trình rồi tiếp tục side effect. Trong hệ thống thật, cần phân biệt lỗi dự kiến, lỗi không dự kiến và giữ correlation/observability an toàn.

### 12.1. Ánh xạ quyết định vào API

Một service/controller có thể ánh xạ kết quả theo cách tổng quát:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

public final class AccessResponseMapper {

    public static ResponseEntity<Void> response(
            AuthorizationGuard.PolicyDecision decision) {

        if (decision == null) {
            return ResponseEntity.status(
                    HttpStatus.SERVICE_UNAVAILABLE).build();
        }

        return switch (decision.decision()) {
            case ALLOW -> ResponseEntity.ok().build();
            case DENY -> ResponseEntity.status(
                    HttpStatus.FORBIDDEN).build();
            case INDETERMINATE -> ResponseEntity.status(
                    HttpStatus.SERVICE_UNAVAILABLE).build();
        };
    }
}
~~~

Đây là ví dụ ánh xạ cho API nội bộ. API công khai có thể cần response đồng nhất để tránh tiết lộ resource existence; controller chỉ gọi data service **sau khi** decision ALLOW. Không trả reasonCode, stack trace hay policy details cho client không có quyền.

### 12.2. JUnit tests cho ba trạng thái

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class AuthorizationGuardTest {

    @Test
    void onlyAllowMayProceed() {
        assertTrue(AuthorizationGuard.mayProceed(
                new AuthorizationGuard.PolicyDecision(
                        AuthorizationGuard.Decision.ALLOW, "MATCH")));
        assertFalse(AuthorizationGuard.mayProceed(
                new AuthorizationGuard.PolicyDecision(
                        AuthorizationGuard.Decision.DENY, "NO_PERMISSION")));
        assertFalse(AuthorizationGuard.mayProceed(
                new AuthorizationGuard.PolicyDecision(
                        AuthorizationGuard.Decision.INDETERMINATE,
                        "POLICY_UNAVAILABLE")));
    }

    @Test
    void missingContextIsIndeterminate() {
        var guard = new AuthorizationGuard(
                (principal, action, resource, tenant) -> null);

        var result = guard.evaluate(
                "user-01", "report:read", "report-01", null);

        assertTrue(result.decision()
                == AuthorizationGuard.Decision.INDETERMINATE);
        assertFalse(AuthorizationGuard.mayProceed(result));
    }

    @Test
    void policyExceptionNeverBecomesAllow() {
        var guard = new AuthorizationGuard(
                (principal, action, resource, tenant) -> {
                    throw new IllegalStateException("simulated outage");
                });

        var result = guard.evaluate(
                "user-01", "report:read", "report-01", "tenant-A");

        assertTrue(result.decision()
                == AuthorizationGuard.Decision.INDETERMINATE);
        assertFalse(AuthorizationGuard.mayProceed(result));
    }
}
~~~

Các test xác minh logic guard với client giả. Cần thêm integration tests để chứng minh **HTTP timeout, circuit breaker, cache, Spring Security filter, controller và data access** đều giữ nguyên hành vi fail-secure.

## 13. Spring Boot: thiết kế degraded mode có kiểm soát

### 13.1. Không cho application khởi động với security config sai

Nếu cấu hình bắt buộc như issuer, trust store, audience hoặc policy version bị thiếu/sai, ứng dụng nên:
- Fail startup/readiness nếu không thể đảm bảo yêu cầu bảo mật thiết yếu.
- Hoặc vào một degraded mode được định nghĩa trước, chỉ phục vụ chức năng không nhạy cảm.
- Không tự bỏ authentication, authorization, TLS validation hoặc audit để khởi động thành công.

Liveness và readiness cần có ý nghĩa khác nhau:
- **Liveness:** process còn sống và không bị deadlock.
- **Readiness:** instance có đủ điều kiện nhận loại traffic đã định.
- Một instance có thể liveness healthy nhưng **không ready cho export/admin** vì dependency bảo mật đang lỗi.

### 13.2. Feature flag nhạy cảm

Không nên mặc định bật tính năng privileged khi flag service không trả lời. Có thể lưu default an toàn trong artifact/config đã được phê duyệt, với:
- Version và thời hạn config cache.
- Danh sách feature được phép chạy trong degraded mode.
- Cơ chế tắt nhanh độc lập nhưng không mở quyền trái policy.
- Audit thay đổi flag và người phê duyệt.
- Test khi config source mất kết nối và khi config sai định dạng.

### 13.3. Circuit breaker không phải quyền fallback

Circuit breaker giúp ngừng gọi dependency liên tục khi nó lỗi; nó **không quyết định quyền được cấp**. Khi circuit mở, caller cần nhận trạng thái unavailable/indeterminate và áp dụng policy theo action. Không đặt fallback function trả ALLOW trong cấu hình circuit breaker.

### 13.4. Timeout, retry và bulkhead

- Timeout hữu hạn ngăn request treo vô hạn.
- Retry chỉ dùng cho lỗi có thể thử lại, có backoff/jitter và giới hạn.
- Bulkhead ngăn một dependency lỗi chiếm hết thread/connection pool.
- Circuit breaker giúp ngăn retry storm.
- Idempotency bảo vệ side effect khi request được gửi lại.
- Queue/buffer cần bounded capacity để không biến outage ngắn thành mất kiểm soát tài nguyên.

Các kỹ thuật này hỗ trợ availability và resilience; **hành vi security khi dependency lỗi vẫn phải được thiết kế và kiểm chứng riêng**.

## 14. Network, TLS và service identity: không fallback sang kênh yếu

Khi client không xác minh được certificate hoặc mTLS identity, hệ thống không được tự chuyển sang:
- HTTP plaintext.
- TLS trust-all.
- Bỏ hostname verification.
- Dùng certificate/secret của môi trường khác.
- Gọi trực tiếp IP/backend để bỏ proxy policy.
- Chấp nhận header identity do client tự gửi.

Một degraded mode có thể tạm dừng outbound request, xếp job vào queue an toàn hoặc chỉ phục vụ endpoint công khai. Nếu cần thay CA/certificate, thực hiện theo quy trình rotation và kiểm chứng.

### Checklist cho từng trust boundary

| Boundary | Khi xác minh lỗi | Hành vi cần giữ |
| --- | --- | --- |
| Browser → Gateway | Cert/hostname không hợp lệ | Client từ chối, không gửi credential |
| Gateway → API | Backend TLS/mTLS không hợp lệ | Không chuyển request qua plaintext |
| Service → Service | Workload identity không xác minh | Không coi peer là trusted |
| App → Database | CA/hostname verification lỗi | Không dùng kết nối plaintext hoặc trust-all |
| Producer/Consumer → Broker | TLS/peer auth lỗi | Không gửi/nhận payload qua listener yếu |
| Worker → Object Storage | Endpoint/signature/trust lỗi | Không upload/download qua endpoint giả |
| Service → Vendor | Vendor cert đổi không đúng trust policy | Dừng/queue hoặc xử lý theo runbook, không bypass |

## 15. Fail secure trong multi-tenant và background jobs

### 15.1. Tenant context không được tự suy đoán

Nếu request không có tenant context đáng tin:
- Không lấy tenant từ header/body rồi tin trực tiếp.
- Không truy vấn toàn bộ tenant.
- Không dùng tenant mặc định có quyền rộng.
- Không tái sử dụng context từ thread/request trước.
- Từ chối hoặc yêu cầu xác minh lại identity/context.

### 15.2. Kiểm tra lại khi worker thực thi

Một job được tạo lúc user còn quyền có thể chạy sau khi:
- User bị revoke.
- Tenant bị khóa.
- Report chuyển owner/classification.
- Job hết hạn.
- Policy thay đổi.

Worker phải xác định policy cho **thời điểm thực thi** theo business rule. Có thể snapshot authorization tại lúc tạo job trong một số workflow, nhưng phải có purpose, scope, expiry và cơ chế thu hồi rõ ràng; không giữ quyền vô hạn chỉ vì message đã vào queue.

### 15.3. Cache và thread-local context

Các lỗi như tái sử dụng tenant context trong thread pool, request context không được clear hoặc cache key thiếu tenant có thể khiến dữ liệu của request trước lẫn sang request sau. Fail-secure review phải test:
- Request A kết thúc, request B dùng cùng worker thread.
- Cache hit từ tenant A không được trả cho tenant B.
- Tenant context null hoặc invalid dẫn đến deny.
- Async task mang context đã xác minh và không tin input tùy ý.
- Job retry không giữ quyền từ một session đã hết hiệu lực.

## 16. Backup, recovery và break-glass

Fail secure phải tính đến **khi hệ thống cần khôi phục**, vì đây là lúc đội vận hành có thể chịu áp lực bỏ qua kiểm soát.

### Backup/recovery

- Backup credential tách khỏi quyền thường xuyên của production khi rủi ro yêu cầu.
- Restore không làm sống lại credential, permission hoặc dữ liệu đã bị thu hồi/xóa mà không qua reconciliation.
- Khóa mã hóa backup có owner và quy trình phục hồi.
- Restore test kiểm tra integrity, authorization, tenant boundary và log/audit.
- Runbook nêu hành vi nếu KMS, IdP hoặc network policy chưa phục hồi.
- Không dùng một bản backup chưa xác minh như nguồn tin cậy để mở lại production.

### Break-glass

Quyền khẩn cấp cần:
- Identity riêng và scope giới hạn.
- Điều kiện kích hoạt, lý do và thẩm quyền phê duyệt.
- Credential/time-bound access và kiểm soát sau sử dụng.
- Audit độc lập hoặc durable evidence path.
- Alert và review hậu sự kiện.
- Revoke/rotate, kiểm tra quyền còn tồn tại và retest.
- Cơ chế khi IdP chính lỗi nhưng vẫn không tạo shared admin password vô thời hạn.

Break-glass là **degraded operating path có kiểm soát**, không phải ngoại lệ để bỏ mọi control. Nếu audit system chính lỗi, phải có phương án ghi nhận độc lập được phê duyệt và đối soát sau đó.

## 17. Security requirements cho fail secure

| Requirement ID | Yêu cầu có thể kiểm chứng | Control | Evidence/Test |
| --- | --- | --- | --- |
| **FS-REQ-01** | Chỉ decision ALLOW có nguồn tin cậy mới cho phép action được bảo vệ | Authorization guard với ALLOW/DENY/INDETERMINATE | PDP timeout/invalid-response negative tests |
| **FS-REQ-02** | Thiếu identity, tenant hoặc resource context không tạo quyền mặc định | Context validation, deny-by-default | Missing/null/spoofed context tests |
| **FS-REQ-03** | TLS/certificate verification lỗi không dẫn đến plaintext hoặc trust-all fallback | Secure transport client policy | Wrong-CA/hostname và fallback tests |
| **FS-REQ-04** | Dependency KMS/secret lỗi không dẫn đến key/secret mặc định | Secret/KMS integration và lifecycle | KMS outage, key access denied tests |
| **FS-REQ-05** | Sensitive action có audit requirement không hoàn tất khi không thể bảo toàn evidence theo policy | Durable audit/outbox control | Collector outage, buffer full, pre-action audit test |
| **FS-REQ-06** | Retry/replay không tạo side effect trùng | Idempotency, transactional state, reconciliation | Duplicate delivery/timeout-after-commit tests |
| **FS-REQ-07** | Stale authorization cache không cấp quyền vượt freshness rule | Versioned cache, bounded TTL, invalidation | Revoke/cache expiry tests |
| **FS-REQ-08** | Degraded mode chỉ cho phép chức năng đã định, có owner và thời hạn | Mode policy, feature defaults | Dependency failure matrix tests |
| **FS-REQ-09** | Service recovery không tự mở lại quyền đã revoke hoặc bỏ đối soát | Recovery gate, policy refresh, reconciliation | Restore/recovery tests |
| **FS-REQ-10** | Source/monitoring failure được phát hiện và trạng thái UNKNOWN không báo PASS | Health, synthetic event, coverage checks | Collector outage/source loss tests |
| **FS-REQ-11** | Break-glass có scope, approval, expiry và post-use review | JIT privileged access | Expiry/revoke/audit tests |
| **FS-REQ-12** | Failure behavior có threat/risk owner và được review khi dependency hoặc action thay đổi | Architecture review, change gate | ADR, risk register, approval and retest |

Mỗi requirement cần được gắn vào **security standard, risk appetite và service scope thực tế**. Các ID là ví dụ học tập, không phải mã điều khoản của một framework bên ngoài.

## 18. Failure-injection test plan

### Ma trận test trọng yếu

| Test ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **FS-T01** | Policy engine timeout khi user đọc dữ liệu nhạy cảm | Không trả dữ liệu; trạng thái INDETERMINATE/unavailable |
| **FS-T02** | Policy engine trả response null/sai schema | Không ALLOW; tạo telemetry |
| **FS-T03** | Tenant context null hoặc bị spoof qua header | Từ chối; không query cross-tenant |
| **FS-T04** | Authorization cache còn ALLOW sau revoke | Không dùng stale decision vượt policy freshness |
| **FS-T05** | TLS server certificate sai CA/hostname | Client từ chối, không HTTP fallback |
| **FS-T06** | KMS timeout khi decrypt | Không dùng key mặc định hoặc xuất plaintext |
| **FS-T07** | Secret manager trả access denied | Không fallback sang secret hardcode/khác môi trường |
| **FS-T08** | Audit collector outage khi export privileged | Buffer bền vững hoặc chặn/hoãn theo requirement |
| **FS-T09** | Audit buffer đầy | Không âm thầm drop event bắt buộc; cảnh báo và áp dụng mode đã duyệt |
| **FS-T10** | Queue giao cùng payment job nhiều lần | Một side effect logic; duplicate được deduplicate |
| **FS-T11** | Provider timeout sau khi đã commit giao dịch | Reconcile status trước retry |
| **FS-T12** | Feature flag/config service unavailable | Tính năng nhạy cảm ở default an toàn |
| **FS-T13** | Rate limiter dependency down | Không bỏ giới hạn toàn bộ endpoint rủi ro cao |
| **FS-T14** | Database failover hoặc split-brain simulation | Không đọc/ghi từ node không được xác minh; không mất invariant |
| **FS-T15** | Worker chạy job sau khi user/tenant bị revoke/disable | Quyền được đánh giá lại theo policy |
| **FS-T16** | Restore backup chứa policy/credential cũ | Không mở lại quyền đã revoke; reconciliation trước khi mở |
| **FS-T17** | Break-glass được dùng khi IdP chính lỗi | Đúng approval/scope/expiry, audit và post-review |
| **FS-T18** | Log collector ngừng nhận một nguồn | Source-health alert và coverage gap được ghi |
| **FS-T19** | Dependency phục hồi nhưng cache/config chưa đồng bộ | Không chuyển NORMAL cho action nhạy cảm trước verification |
| **FS-T20** | Readiness check thất bại nhưng liveness còn sống | Instance không nhận traffic nhạy cảm trái điều kiện |
| **FS-T21** | Circuit breaker mở | Caller nhận unavailable/indeterminate, không gọi fallback ALLOW |
| **FS-T22** | Retry storm hoặc buffer gần đầy | Backpressure/limit hoạt động; không cạn tài nguyên và mở control |
| **FS-T23** | Exception handler tạo error response | Không lộ stack trace, secret, policy detail hoặc PII |
| **FS-T24** | Source evidence/scanner thiếu quyền | Assessment INCONCLUSIVE/FAIL theo rule, không tự PASS |

### Kiểm thử ở nhiều lớp

- **Unit:** decision mapping, default values, policy guard và idempotency.
- **Integration:** HTTP client timeout, Spring Security filter, KMS, database, broker và cache.
- **Component:** circuit breaker, bulkhead, retry, audit buffer và queue.
- **System:** degraded mode, failover, recovery gate và reconciliation.
- **Security negative:** bypass, stale access, missing context, wrong identity, duplicate action.
- **Operational exercise:** runbook, alert, escalation, owner và approval.

Không cần gây outage thật ở production để chứng minh mọi failure mode. Ưu tiên test environment, mock/fault injection được giới hạn, canary hoặc read-only runtime verification. Nếu một failure scenario chưa thể mô phỏng, ghi **untested/INCONCLUSIVE**, phương pháp đánh giá thay thế và residual risk.

## 19. Assurance case và evidence register

Một kết luận fail-secure tốt phải chứng minh **cả hành vi khi lỗi lẫn hành vi sau phục hồi**.

### Chuỗi truy vết mẫu

~~~text
RISK-FS-01: Policy engine timeout làm request trái quyền được cho phép
  -> INV-FS-01: Chỉ verified ALLOW mới tiếp tục
  -> FS-REQ-01: DENY/INDETERMINATE không cấp quyền
  -> CTRL-FS-01: Authorization guard + timeout + circuit breaker
  -> FS-T01/T02: Timeout và invalid response negative tests
  -> EV-FS-01: Policy client config + test run + runtime deployment
  -> FIND-FS-01: Exception handler cũ vẫn trả ALLOW
  -> REMED-FS-01: Sửa guard, deploy và retest
  -> RECOVERY-FS-01: Refresh policy/cache và kiểm tra quyền sau outage
~~~

### Mẫu YAML evidence record

Các giá trị placeholder trong mẫu là dữ liệu cần thay bằng tham chiếu thực tế; chúng không phải bằng chứng đã được thu thập:

~~~yaml
assessment_id: FS-ASSURANCE-001
module: SECURITY_SECURITY_ASSURANCE
service: report-api
environment: production
claim: "Protected report reads do not proceed without a verified allow decision"
risk_ids: [RISK-FS-01, RISK-FS-03]
invariant_ids: [INV-FS-01, INV-FS-02, INV-FS-08]
requirement_ids: [FS-REQ-01, FS-REQ-02, FS-REQ-07, FS-REQ-08]
control_ids: [CTRL-FS-AUTHZ, CTRL-FS-CACHE, CTRL-FS-DEGRADED-MODE]
scope:
  actions: ["report:read", "report:export"]
  resources: ["tenant-scoped-report"]
  dependencies: ["policy-engine", "identity-provider", "database"]
  failure_modes: ["timeout", "invalid-response", "cache-stale", "recovery"]
implementation:
  source_commit: "<COMMIT_ID>"
  artifact_digest: "<ARTIFACT_DIGEST>"
  deployment_id: "<ACTUAL_DEPLOYMENT_ID>"
  policy_version: "<POLICY_VERSION>"
  timeout_config_ref: "<RUNTIME_TIMEOUT_AND_CIRCUIT_BREAKER>"
  cache_config_ref: "<TTL_VERSION_AND_INVALIDATION>"
verification:
  assessed_at: "<ISO_8601_UTC>"
  test_refs:
    - "<POLICY_TIMEOUT_TEST>"
    - "<INVALID_RESPONSE_TEST>"
    - "<CROSS_TENANT_NEGATIVE_TEST>"
    - "<REVOKE_CACHE_TEST>"
    - "<RECOVERY_RECONCILIATION_TEST>"
  observed_decision_counts: "<SANITIZED_COUNTS>"
  source_health_ref: "<DEPENDENCY_AND_TELEMETRY_HEALTH>"
  result: "<PASS_FAIL_INCONCLUSIVE>"
  reviewer: "<AUTHORIZED_ASSESSOR>"
degraded_mode:
  allowed_functions: ["<APPROVED_LOW_RISK_FUNCTIONS>"]
  blocked_functions: ["<SENSITIVE_ACTIONS>"]
  owner: "<DEGRADED_MODE_OWNER>"
  expiry_or_review_trigger: "<TIME_OR_RECOVERY_EVENT>"
findings: ["<FINDING_IDS_IF_ANY>"]
exceptions: ["<APPROVED_EXCEPTION_IDS_IF_ANY>"]
residual_risk: "<REVIEWED_RATIONALE>"
limitations: "<UNTESTED_DEPENDENCIES_OR_FAILURE_MODES>"
reassessment_triggers:
  - "Policy, identity, cache, KMS, audit or network behavior change"
  - "New sensitive action, service or dependency"
  - "Incident, failed recovery, drift or exception expiry"
~~~

Không lưu raw token, private key, password hoặc dữ liệu khách hàng đầy đủ vào evidence. Dùng **decision code, correlation ID, config version, sanitized result, counts và deployment reference**. Evidence repository cũng cần quyền, integrity và retention riêng.

### Design, implementation, operating và recovery evidence

| Loại | Điều chứng minh | Ví dụ |
| --- | --- | --- |
| **Design** | Failure behavior đã được phân tích và phê duyệt | Threat model, failure matrix, ADR |
| **Implementation** | Code/config triển khai hành vi đã định | Authorization guard, timeout, circuit breaker, safe defaults |
| **Operating effectiveness** | Runtime thực sự giữ invariant khi dependency lỗi | Failure tests, telemetry, source-health, policy snapshot |
| **Recovery effectiveness** | Sau khi dependency phục hồi, hệ thống không mở lại quyền sai | Cache refresh, reconciliation, retest, reviewer sign-off |

Một unit test chứng minh mayProceed(INDETERMINATE) == false chưa đủ để kết luận production fail-secure nếu controller khác vẫn có fallback ALLOW hoặc endpoint legacy bỏ qua guard.

## 20. Trạng thái đánh giá và quản lý finding

| Trạng thái | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| **PASS** | Failure behavior và recovery đã được kiểm chứng trong scope | Ghi version, dependency, thời gian, test và reviewer |
| **FAIL** | Quan sát thấy lỗi làm suy giảm invariant | Finding, owner, deadline, containment và retest |
| **INCONCLUSIVE** | Không thể inject/quan sát lỗi hoặc thiếu evidence/coverage | Không tự PASS; nêu limitation và kế hoạch kiểm chứng |
| **DEGRADED_APPROVED** | Chế độ suy giảm được phê duyệt trong scope/thời hạn | Theo dõi function limits, owner, expiry và residual risk |
| **NOT_RUN/OVERDUE** | Test/review chưa thực hiện hoặc quá hạn | Escalate theo risk |
| **RECOVERY_PENDING** | Dependency đã phục hồi nhưng chưa đối soát/retest xong | Giữ giới hạn cho action nhạy cảm |
| **EXCEPTION_APPROVED** | Risk owner chấp nhận sai lệch theo thẩm quyền | Không tự chuyển control FAIL thành PASS |

### Ví dụ finding

**FIND-FS-01:** Khi policy engine timeout, một exception handler cũ trả **true**, cho phép export report.

1. Xác minh endpoint, action, principal, resource và code path bị ảnh hưởng.
2. Đánh giá có request nào được allow trong khoảng policy unavailable không; phối hợp incident response nếu có dấu hiệu lạm dụng.
3. Chặn/giới hạn export trong thời gian sửa; không thay bằng shared admin credential.
4. Sửa logic thành ALLOW/DENY/INDETERMINATE và timeout hữu hạn.
5. Test policy timeout, malformed response, cross-tenant, circuit open và recovery.
6. Đối chiếu runtime artifact/config/deployment; tìm các endpoint/worker khác dùng cùng helper.
7. Kiểm tra log source health và lưu evidence đã làm sạch.
8. Reviewer xác nhận acceptance criteria, limitation và residual risk trước khi đóng.

**Ticket đã merge không có nghĩa finding đã được khắc phục.** Cần xác minh bản chạy thực tế và retest failure path.

## 21. Metrics và giám sát liên tục

Các chỉ số có ích:
- Số request bị từ chối do INDETERMINATE, phân theo dependency/action.
- Tỷ lệ policy evaluation timeout, malformed response và circuit breaker open.
- Tuổi của cache authorization, số decision dùng fallback và tỷ lệ revoke invalidation.
- Số hành động nhạy cảm bị chặn do audit/KMS/identity unavailable.
- Audit buffer backlog, drop count, oldest event age và collector source health.
- Số retry, duplicate message, idempotency conflict và operation cần reconciliation.
- Số degraded-mode activation, thời lượng, chức năng bị giới hạn và owner.
- Thời gian từ dependency recovery tới verification và trở lại NORMAL.
- Findings/exception quá hạn và tỷ lệ retest thành công.

### Tránh diễn giải metric sai

| Metric | Có ích để đo | Không chứng minh |
| --- | --- | --- |
| Nhiều request INDETERMINATE | Dependency/decision path có vấn đề | Tất cả request đã được bảo vệ đúng |
| Không có request DENY | Có thể ít truy cập trái phép hoặc thiếu log/policy | Không có hành vi trái quyền |
| Circuit breaker đóng | Dependency có vẻ phản hồi | Policy decision đúng hoặc fresh |
| Audit backlog bằng 0 | Buffer không tồn đọng | Collector nhận đủ mọi nguồn |
| Degraded mode chưa từng kích hoạt | Chưa thấy sự cố trong dữ liệu quan sát | Failure behavior đã được test |
| Tỷ lệ uptime cao | Availability | Security invariants được giữ |
| Test suite xanh | Test cases đã chạy đạt | Runtime không drift hoặc không có bypass |

Cần có **synthetic failure tests** theo lịch, không chờ dependency outage thật mới biết fallback đang làm gì.

## 22. Case study: report-api khi policy engine và audit store lỗi

### Bối cảnh

Nền tảng báo cáo đa tenant sử dụng:
- Spring Boot report-api cho user read/export.
- OIDC identity provider.
- Authorization policy engine.
- PostgreSQL chứa report.
- Worker tạo file và object storage.
- Audit event store/SIEM.
- Redis cache cho policy decisions.

Trong một sự cố:
1. Policy engine bị timeout do network partition.
2. Redis vẫn chứa ALLOW decision của một số user từ nhiều giờ trước.
3. API có fallback dùng cache bất kể action/resource.
4. Audit collector cũng mất kết nối.
5. Export worker tiếp tục nhận job đã được tạo trước outage.
6. Dashboard hiển thị API availability vẫn cao vì request trả HTTP 200.

### Phân tích

| Vấn đề | Invariant bị đe dọa | Hành vi cần có |
| --- | --- | --- |
| PDP timeout | Chỉ verified ALLOW mới cho phép | INDETERMINATE, không export |
| Cache stale | Revoke phải có hiệu lực theo freshness policy | Không dùng stale ALLOW cho export/privileged |
| Audit collector mất | Hành động nhạy cảm có audit theo requirement | Buffer bền vững hoặc hoãn/chặn action cần audit trước |
| Worker job cũ | Quyền tại execution time | Revalidate job/tenant/resource theo policy |
| Dashboard chỉ xem HTTP 200 | Control health phải phản ánh security state | Tách availability khỏi security/degraded status |

### Kế hoạch remediation

1. Đặt timeout và circuit breaker cho PDP; phân biệt ALLOW/DENY/INDETERMINATE.
2. Xây cache key theo principal/action/resource/tenant và policy version; đặt freshness theo risk.
3. Tắt fallback stale ALLOW cho export và privileged action.
4. Tạo durable audit buffer, source-health alert và rule khi buffer đầy.
5. Worker revalidate job authorization và expiry khi thực thi.
6. Khi recovery, refresh policy/cache, đối soát export jobs và audit backlog.
7. Chạy negative tests, duplicate/replay tests và synthetic alert.
8. Gắn kết quả với source commit, artifact digest, deployment ID và reviewer.
9. Đánh giá log/audit trong khoảng outage; tạo incident/finding nếu có khả năng đã cho phép trái quyền.
10. Chỉ mở lại NORMAL sau verification, không chỉ sau khi health check dependency xanh.

### Assurance claim có thể kiểm chứng

> Trong phạm vi report-api và export-worker production deployment được đánh giá, khi policy engine timeout hoặc trả response không hợp lệ, thao tác đọc dữ liệu nhạy cảm và export không tiếp tục nếu không có decision ALLOW hợp lệ; worker kiểm tra lại quyền theo job khi thực thi; audit event quan trọng được lưu theo cơ chế durable buffer hoặc action bị hoãn theo policy; sau phục hồi, cache và job backlog được đối soát trước khi mở lại chức năng.

Claim này chỉ đạt khi có test/runtime evidence cho **từng nhánh lỗi và recovery**. API availability cao không phải bằng chứng fail-secure.

## 23. Bài tập thực hành

**Tình huống:** một hệ thống Java/Spring Boot xử lý đơn hàng, thanh toán và hồ sơ khách hàng. Các dependency gồm IdP, authorization service, Redis, PostgreSQL, KMS, Kafka, SIEM và payment provider. Khi outage xảy ra:

- IdP không cấp token mới.
- Authorization service timeout.
- Redis chứa policy decision cũ.
- KMS không thể giải mã dữ liệu khách hàng.
- Kafka consumer retry cùng một payment job.
- SIEM không nhận audit event.
- Feature flag service không phản hồi.
- Một break-glass admin cần xử lý incident.

### Yêu cầu

1. Xác định ít nhất **sáu security invariants** cần giữ.
2. Phân loại từng action thành public, low-risk, sensitive, privileged hoặc critical business operation.
3. Viết failure behavior cho từng dependency, nêu action nào tiếp tục, bị giới hạn, bị chặn hoặc chuyển pending.
4. Thiết kế cache policy freshness và revoke behavior; giải thích vì sao không dùng stale ALLOW cho mọi action.
5. Đề xuất durable audit/outbox và idempotency cho payment/queue.
6. Thiết kế break-glass khi IdP chính lỗi, gồm approval, scope, expiry, audit và post-use review.
7. Viết tối thiểu **tám failure-injection tests**, có recovery/reconciliation và source-health.
8. Lập evidence register với risk, invariant, requirement, control, test, deployment, reviewer và limitation.
9. Phân biệt availability failure, security failure và evidence failure; nêu trường hợp nhiều loại cùng xảy ra.
10. Đưa ra điều kiện để hệ thống rời DEGRADED và quay lại NORMAL.

### Hướng giải mẫu

| Dependency | Hành vi cần xem xét | Bằng chứng |
| --- | --- | --- |
| IdP | Không cấp session mới; session hiện hữu theo expiry/revocation policy | Invalid/expired token tests, identity outage exercise |
| PDP | INDETERMINATE không cho phép sensitive action | Timeout/malformed response tests |
| Redis | Stale decision chỉ được dùng theo bounded policy; revoke không bị bỏ qua | Cache age/version/revoke tests |
| KMS | Không dùng key mặc định; thao tác decrypt pending/failed theo policy | KMS outage/access denied tests |
| Kafka | Deduplicate và reconcile trước side effect lặp | Duplicate delivery/timeout tests |
| SIEM | Durable buffer hoặc chặn action yêu cầu audit bền vững | Buffer full/source loss/alert tests |
| Feature flags | Default an toàn cho admin/export | Config outage and invalid config tests |
| Break-glass | Kênh khẩn cấp độc lập có giới hạn và audit | Approval/expiry/revoke/post-review exercise |

**Câu hỏi nâng cao:** Một hệ thống từ chối mọi request khi SIEM lỗi. Cách làm này có luôn là fail secure không?

**Định hướng:** chưa chắc. Nó có thể bảo vệ audit requirement cho action nhạy cảm nhưng tạo outage không cần thiết cho chức năng công khai/ít rủi ro, hoặc ảnh hưởng an toàn nghiệp vụ. Phải phân loại event/action, có durable buffer, giới hạn và degraded mode. Kết luận cần chứng minh cả security invariant lẫn continuity/safety requirement phù hợp.

## 24. Những sai lầm thường gặp

| Ngộ nhận | Vì sao nguy hiểm? | Thực hành phù hợp |
| --- | --- | --- |
| “Fail secure nghĩa là tắt toàn bộ hệ thống khi có lỗi.” | Có thể gây outage không cần thiết và tạo rủi ro khác | Degraded mode theo action và risk |
| “Authorization service lỗi thì cứ cho phép user đã login.” | Authentication không thay authorization | Chỉ verified ALLOW mới tiếp tục |
| “Không có response nghĩa là không có DENY, vậy cho phép.” | Biến unknown thành quyền | Dùng ALLOW/DENY/INDETERMINATE |
| “Cache còn entry thì dùng được.” | Cache có thể thiếu tenant/action/version và quyền đã revoke | Key đầy đủ, bounded TTL, invalidation |
| “KMS lỗi thì dùng key dự phòng hardcode.” | Mở đường secret/crypto bypass | Managed key lifecycle và recovery path |
| “TLS lỗi thì tạm bỏ hostname check.” | Có thể gửi credential tới endpoint giả | Không fallback yếu, xử lý trust/rotation |
| “SIEM down thì drop audit rồi tiếp tục.” | Mất evidence và khả năng điều tra | Durable buffer, source-health, risk-based gate |
| “Retry nhiều lần sẽ tự khắc phục.” | Duplicate side effect, retry storm và cạn tài nguyên | Idempotency, bounded retry, reconciliation |
| “Feature flag không tải được thì bật cho đủ tính năng.” | Có thể mở admin/export ngoài policy | Secure defaults và versioned config |
| “Worker được authorize khi tạo job thì mãi được phép.” | Quyền có thể bị revoke trước khi execution | Revalidate hoặc snapshot policy có scope/expiry |
| “HTTP 200 nghĩa là service healthy.” | Có thể trả dữ liệu khi policy unavailable | Tách application availability và security state |
| “Fail-closed luôn đúng với mọi chức năng.” | Có thể ảnh hưởng safety/continuity | Phân tích action và degraded mode |
| “Break-glass là tài khoản admin dùng chung.” | Không truy vết, không giới hạn, khó revoke | Identity riêng, approval, expiry và review |
| “Health check xanh thì mở lại NORMAL.” | Cache/job/audit có thể chưa đối soát | Recovery gate và retest |
| “Không có alert nghĩa là không có lỗi.” | Collector hoặc detector có thể mất nguồn | Synthetic events và source completeness |
| “Unit test guard xanh là đủ.” | Controller/legacy path có thể bypass | Integration/system/runtime tests |
| “Exception được duyệt là control PASS.” | Risk acceptance không sửa trạng thái kỹ thuật | Theo dõi exception và residual risk riêng |

## Ghi nhớ

- **Fail secure** yêu cầu lỗi không làm hệ thống tự cấp thêm quyền, bỏ xác minh, mở plaintext path hoặc tiết lộ dữ liệu ngoài policy.
- **Chỉ một quyết định ALLOW đáng tin mới được phép tiếp tục**; DENY và INDETERMINATE phải được phân biệt, không biến timeout hoặc context thiếu thành quyền.
- Fail-secure thường dùng fail-closed ở hành động nhạy cảm, nhưng hệ thống có thể cần **graceful degradation** để duy trì chức năng ít rủi ro hoặc thiết yếu.
- Cache, retry, queue, audit, KMS, IdP, feature flags và recovery đều có thể tạo đường bypass nếu không thiết kế failure behavior.
- Degraded mode cần **scope, owner, expiry, monitoring, audit, điều kiện dừng và reconciliation**; recovery không tự động đồng nghĩa có thể mở lại NORMAL.
- Java/Spring Boot phải giữ security invariants qua controller, policy guard, database, worker, cache và service-to-service; unit tests không thay integration/runtime evidence.
- Security assurance cần **risk → invariant → requirement → control → failure test → evidence → finding → remediation/retest**, với PASS/FAIL/INCONCLUSIVE và residual risk rõ ràng.
